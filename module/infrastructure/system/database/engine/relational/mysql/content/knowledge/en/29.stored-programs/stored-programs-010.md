# DETERMINISTIC, Data Access Characteristics, and Binary Logging

## Objectives

After this lesson, you will be able to:

- Distinguish `DETERMINISTIC` from `NOT DETERMINISTIC` in stored functions.
- Explain the four data access characteristics: `NO SQL`, `CONTAINS SQL`, `READS SQL DATA`, and `MODIFIES SQL DATA`.
- Understand why routine characteristics are declarations committed to by the author, rather than the result of MySQL analyzing and verifying the entire routine body.
- Choose declarations that accurately match actual function behavior.
- Explain the risks of statement-based replication when a function has inconsistent results or side effects.
- Distinguish `STATEMENT`, `ROW`, and `MIXED` binary log formats.
- Check `log_bin`, `binlog_format`, and `log_bin_trust_function_creators`.
- Understand the requirements for creating stored functions when binary logging is enabled and trusting creators is disabled.
- Evaluate test cases needed on source/replica before releasing.

Examples target MySQL 8.0/8.4. Binary logging, administrative privileges, and certain replication behaviors may vary by version or configuration; always verify on the exact server you operate.

## 1. Why must stored functions declare characteristics?

A stored function is a routine returning a single value that can be called inside SQL expressions, such as in `SELECT`, `WHERE`, `ORDER BY`, or write-statement expressions.

Example:

```sql
CREATE FUNCTION fn_line_total(
    p_quantity INT,
    p_unit_price DECIMAL(12,2)
)
RETURNS DECIMAL(14,2)
DETERMINISTIC
NO SQL
RETURN p_quantity * p_unit_price;
```

The function above computes its result solely from two parameters. Identical parameter pairs yield identical results, with no table reads or writes. Hence declaring `DETERMINISTIC` and `NO SQL` accurately describes its behavior.

MySQL lets you declare routine characteristics to describe determinism and data access level. These declarations matter for routine administration and binary logging rules, but they do not replace reading and testing the function's body.

The two characteristic groups are independent:

- **Determinism:** do identical inputs always produce the same result?
- **Data access:** does the routine contain SQL, read data, or potentially modify data?

A function can be `DETERMINISTIC` yet `READS SQL DATA` if the data it reads is truly immutable under the system's contract. Conversely, a function can be `NOT DETERMINISTIC` and `NO SQL` if its result depends on current time without accessing tables.

## 2. DETERMINISTIC and NOT DETERMINISTIC

### 2.1. DETERMINISTIC

`DETERMINISTIC` means the function always returns the same result when called with the same input parameter values.

Example:

```sql
DELIMITER $$

CREATE FUNCTION fn_normalize_code(p_code VARCHAR(40))
RETURNS VARCHAR(40)
DETERMINISTIC
NO SQL
BEGIN
    RETURN UPPER(TRIM(p_code));
END$$

DELIMITER ;
```

For the same input string, the function normalizes using the same transformation. It does not depend on tables, current time, random numbers, or session state.

Pure arithmetic calculations, fixed-rule string normalization, or value conversions independent of external state typically suit `DETERMINISTIC`.

### 2.2. NOT DETERMINISTIC

`NOT DETERMINISTIC` describes a function that can return different results even when given identical input parameters.

Example:

```sql
CREATE FUNCTION fn_days_since(p_created_at DATE)
RETURNS INT
NOT DETERMINISTIC
NO SQL
RETURN DATEDIFF(CURRENT_DATE, p_created_at);
```

The result changes with the current date. Calling the function with the same `p_created_at` on two different days can return different results, so declaring `NOT DETERMINISTIC` is appropriate.

### 2.3. Sources of dependency making a function non-deterministic

Common dependency sources:

- `CURRENT_DATE`, `CURRENT_TIME`, `NOW()`, or current time.
- `SYSDATE()` under typical configuration.
- Random numbers or freshly generated identifiers such as `UUID()`.
- Table data that may change between invocations.
- Session variables, user variables, timezone, or connection state.
- External state not fully represented by input parameters.

Do not look only at the `RETURN` statement. Inspect the entire routine, nested functions called inside it, and every piece of state the output depends on.

### 2.4. Table reads can still be non-deterministic

Example function looking up the current tax rate:

```sql
CREATE TABLE tax_rates (
    region_code CHAR(2) NOT NULL,
    valid_from DATE NOT NULL,
    rate DECIMAL(6,4) NOT NULL,
    PRIMARY KEY (region_code, valid_from)
) ENGINE = InnoDB;
```

```sql
DELIMITER $$

CREATE FUNCTION fn_current_tax_rate(p_region_code CHAR(2))
RETURNS DECIMAL(6,4)
NOT DETERMINISTIC
READS SQL DATA
BEGIN
    DECLARE v_rate DECIMAL(6,4) DEFAULT NULL;

    SELECT rate
      INTO v_rate
      FROM tax_rates
     WHERE region_code = p_region_code
       AND valid_from <= CURRENT_DATE
     ORDER BY valid_from DESC
     LIMIT 1;

    RETURN v_rate;
END$$

DELIMITER ;
```

The function reads data (`READS SQL DATA`). Tax rates can change when the table is updated, and `CURRENT_DATE` also changes daily. Therefore, declaring `NOT DETERMINISTIC` reflects its true semantics.

If a function reads a configuration table guaranteed to be immutable, its output might remain stable for given parameters across the system's lifetime. However, that immutability contract must be proven and all other dependencies checked. Do not declare `DETERMINISTIC` merely because data rarely changes.

### 2.5. Defaults when declarations are omitted

If determinism is omitted, MySQL defaults the routine to `NOT DETERMINISTIC`. If data access is omitted, it defaults to `CONTAINS SQL`.

When binary logging is enabled and `log_bin_trust_function_creators` is off, these defaults may fail to satisfy function creation declaration requirements. Therefore, specify the accurate characteristics explicitly instead of relying on defaults.

## 3. Four SQL data access characteristics

Data access characteristics describe the kinds of SQL statements a routine contains. They are neither SQL privileges granted to an account nor do they determine `SQL SECURITY`.

| Characteristic | Meaning | Behavioral example |
|---|---|---|
| `NO SQL` | Routine contains no SQL statements | Computing from parameters |
| `CONTAINS SQL` | Contains SQL statements but neither reads nor modifies SQL data | Assigning local variables, evaluating expressions |
| `READS SQL DATA` | May read data but does not modify data | `SELECT` from a table |
| `MODIFIES SQL DATA` | May modify data | `INSERT`, `UPDATE`, `DELETE` |

### 3.1. NO SQL

`NO SQL` applies to routines containing no SQL statements. Example function computing purely from parameters:

```sql
CREATE FUNCTION fn_discounted_price(
    p_price DECIMAL(12,2),
    p_percent DECIMAL(5,2)
)
RETURNS DECIMAL(12,2)
DETERMINISTIC
NO SQL
RETURN ROUND(p_price * (1 - p_percent / 100), 2);
```

The function neither queries tables nor writes data. Do not declare `READS SQL DATA` just because the function will be invoked inside an SQL query; this characteristic describes the routine's own data-access content.

### 3.2. CONTAINS SQL

`CONTAINS SQL` describes a routine that contains SQL statements without reading or modifying data. Example routine manipulating local variables:

```sql
DELIMITER $$

CREATE FUNCTION fn_format_code(p_code VARCHAR(40))
RETURNS VARCHAR(40)
DETERMINISTIC
CONTAINS SQL
BEGIN
    DECLARE v_code VARCHAR(40);
    SET v_code = UPPER(TRIM(p_code));
    RETURN v_code;
END$$

DELIMITER ;
```

`CONTAINS SQL` does not mean the routine is permitted to read or write tables. If a `SELECT` reads data, declare `READS SQL DATA`; if there are data-modifying operations, declare `MODIFIES SQL DATA`.

### 3.3. READS SQL DATA

`READS SQL DATA` is used when a routine contains statements that read data, such as `SELECT ... INTO`:

```sql
DELIMITER $$

CREATE FUNCTION fn_product_price(p_product_id BIGINT)
RETURNS DECIMAL(12,2)
NOT DETERMINISTIC
READS SQL DATA
BEGIN
    DECLARE v_price DECIMAL(12,2) DEFAULT NULL;

    SELECT price
      INTO v_price
      FROM products
     WHERE product_id = p_product_id;

    RETURN v_price;
END$$

DELIMITER ;
```

The function reads the `products` table. If prices can change, the same `product_id` can return different results at different times. Hence `NOT DETERMINISTIC` fits a mutable price table.

### 3.4. MODIFIES SQL DATA

`MODIFIES SQL DATA` is used when a routine can execute data-modifying operations such as `INSERT`, `UPDATE`, or `DELETE`.

Example illustrating a function recording an event into an audit table:

```sql
CREATE TABLE function_audit (
    audit_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    event_code VARCHAR(40) NOT NULL,
    created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (audit_id)
) ENGINE = InnoDB;
```

```sql
DELIMITER $$

CREATE FUNCTION fn_record_event(p_event_code VARCHAR(40))
RETURNS BIGINT UNSIGNED
NOT DETERMINISTIC
MODIFIES SQL DATA
BEGIN
    INSERT INTO function_audit (event_code)
    VALUES (p_event_code);

    RETURN LAST_INSERT_ID();
END$$

DELIMITER ;
```

This is an example of data-access declaration, not a recommendation to put side effects into functions called arbitrarily from `SELECT`. Stored functions have strict limits: for example, they cannot modify a table already used by the statement calling the function, cannot control transactions via `COMMIT`/`ROLLBACK`, and cannot return result sets the way stored procedures can. Consider a stored procedure or explicit DML when writing data is the primary goal.

Binary logging note: when `log_bin_trust_function_creators = 0`, declaring `MODIFIES SQL DATA` alone does not satisfy function creation checks. This example may be rejected when binary logging is enabled without appropriate configuration/privileges. Never change the declaration to `NO SQL` or `DETERMINISTIC` to evade checks; reflect true behavior and follow DBA procedures.

### 3.5. Characteristics are descriptive, not enforcement barriers

These characteristics are advisory: MySQL does not use them to restrict which statements a routine is allowed to execute, nor does it verify that the entire body obeys the declaration. For instance, a routine declaring `NO SQL` whose body reads a table is misdeclared; do not assume the server verified compliance simply because `CREATE FUNCTION` succeeded.

Likewise, `READS SQL DATA` is not a read-only privilege grant. Actual permissions depend on `DEFINER`/`INVOKER`, account privileges, and the statements inside.

## 4. Determinism and data access are two independent axes

Do not infer `DETERMINISTIC` solely from `NO SQL`, or infer `NOT DETERMINISTIC` solely from `READS SQL DATA`. Inspect both the logic and the data the function uses.

| Example | Appropriate determinism | Appropriate data access | Reason |
|---|---|---|---|
| Multiply two parameters | `DETERMINISTIC` | `NO SQL` | Depends only on inputs |
| Normalize a string with fixed rules | `DETERMINISTIC` | `NO SQL` or `CONTAINS SQL` depending on body | Reads no external state |
| Count days since current date | `NOT DETERMINISTIC` | `NO SQL` | Depends on time |
| Read current price from a table | Usually `NOT DETERMINISTIC` | `READS SQL DATA` | Table can change |
| Write an audit row | Usually `NOT DETERMINISTIC` | `MODIFIES SQL DATA` | Has data-writing side effects |
| Read a guaranteed immutable table | Potentially `DETERMINISTIC` if all dependencies are stable | `READS SQL DATA` | Requires an explicit immutability contract |

For instance, a function reading a config table that also calls `CURRENT_DATE` cannot be considered deterministic just because the config table rarely changes. A purely arithmetic function using `RAND()` is also not deterministic.

## 5. Binary logging and replication

The binary log records data changes and schema changes for replication, point-in-time recovery, and other operational needs.

When a function is invoked inside an SQL statement that modifies data, the binary logging format affects how replicas apply those changes.

### 5.1. Statement-based logging

With `binlog_format = STATEMENT`, the binary log records the SQL statement. The replica re-executes that statement.

If the function depends on time, random numbers, session state, or data differing between source and replica, re-execution results may diverge. This can cause replica data to drift from the source.

Conceptual example:

```sql
UPDATE orders
SET reference_code = fn_generate_reference(order_id)
WHERE status = 'PENDING';
```

If the function produces different values on each call and the statement is replayed on a replica, the result may differ from the source unless MySQL applies special logging handling for specific functions or the statement is handled safely.

### 5.2. Row-based logging

With `binlog_format = ROW`, the binary log records row-level changes. The replica applies the logged row events rather than re-executing the original DML statement to recompute row values.

This generally lowers the risk of divergence caused by non-deterministic functions in row-logged DML operations. However, row-based logging does not turn a false routine declaration into a correct one, nor does it eliminate all issues related to DDL, routine definitions, side effects, or statements logged as statements.

### 5.3. Mixed logging

With `binlog_format = MIXED`, MySQL chooses statement-based or row-based logging per statement according to server rules. Certain statements deemed unsafe for statement-based logging can automatically switch to row-based logging.

Mixed mode is helpful, but should not be treated as automatic detection of every misdeclared function. Routine characteristics must still be truthful and tested on the actual topology.

### 5.4. Comparing the three formats

| Format | Primary content in binary log | Impact with non-deterministic functions |
|---|---|---|
| `STATEMENT` | SQL statements | Replica re-executes; special care needed for safety and state dependencies |
| `ROW` | Row changes | Replica applies row events; typically avoids recomputing function expressions for that DML |
| `MIXED` | Combination of statement and row | Server automatically switches certain unsafe statements to row |

Do not choose a binlog format based on a single function. Consider binary log volume, auditing needs, workload, replication topology, MySQL version, and recovery requirements.

## 6. Built-in functions and non-determinism

Certain built-in functions have special behavior under binary logging. Do not lump every time-varying or random function into a single "replication is always broken" bucket.

| Function / group | Characteristic | Replication notes |
|---|---|---|
| `CURRENT_DATE` | Depends on current date | Non-deterministic for same inputs across days; evaluate how statements are logged and source/replica timezones |
| `NOW()`, `CURRENT_TIMESTAMP`, and synonyms | Depends on current time | Binary log records timestamp so source/replica share the same clock for the statement; still non-deterministic across invocations over time |
| `RAND()` | Generates random numbers | MySQL logs the seed to support statement-based replication; inside a stored routine, `RAND()` reproduces accurately only when called once per routine execution |
| `UUID()`, `UUID_SHORT()`, `USER()`, `CURRENT_USER()`, `VERSION()`, `LOAD_FILE()` | Depends on server, connection, or external state | Some functions are not reproduced identically on replicas; statement-based replication can be unsafe, while Mixed switches certain cases to row |
| `SYSDATE()` | Returns exact function execution time | Not governed by the statement timestamp in the binary log, so it can be unsafe with statement-based replication; `--sysdate-is-now` makes it behave like `NOW()` and requires consistent source/replica configuration |

Key point: a function may receive special handling by MySQL in the binary log yet still fail the `DETERMINISTIC` definition of identical inputs always producing identical results. Never use special built-in safety rules as an excuse to misdeclare custom functions.

## 7. Conditions for creating stored functions when binary logging is enabled

MySQL enforces safeguards when binary logging is enabled to limit functions that could cause source/replica divergence.

### 7.1. log_bin_trust_function_creators

The `log_bin_trust_function_creators` system variable controls whether the server trusts stored function/trigger creators to take responsibility for binary logging safety.

Check status:

```sql
SELECT
    @@GLOBAL.log_bin AS log_bin,
    @@GLOBAL.binlog_format AS binlog_format,
    @@GLOBAL.log_bin_trust_function_creators
        AS log_bin_trust_function_creators;
```

`log_bin` indicates whether binary logging is enabled. `binlog_format` shows the current format. `log_bin_trust_function_creators` is a global variable, `OFF` by default; it is marked deprecated in MySQL 8.4, so consult target-version documentation and upgrade policies before designing long-term dependencies on it.

### 7.2. When trusting creators is off

When binary logging is enabled and `log_bin_trust_function_creators = 0`, MySQL enforces extra checks when creating stored functions:

- The creator needs `CREATE ROUTINE` (when creating) or `ALTER ROUTINE` (when altering characteristics), and also requires the `SUPER` privilege under MySQL's binary logging checks in this mode.
- The function must declare at least one of `DETERMINISTIC`, `NO SQL`, or `READS SQL DATA`.

For example, a function missing an accepted characteristic declaration can hit error 1418:

```text
ERROR 1418 (HY000): This function has none of DETERMINISTIC,
NO SQL, or READS SQL DATA in its declaration and binary logging
is enabled (you *might* want to use the less safe
log_bin_trust_function_creators variable)
```

If the creator lacks the required administrative privilege, error 1419 related to `SUPER` and binary logging can occur.

These checks validate declarations and privileges. The server does not prove the function is genuinely deterministic or read-only.

### 7.3. Which characteristics satisfy the declaration check?

With trust disabled, any one of the following satisfies the characteristic requirement:

```sql
DETERMINISTIC
```

or:

```sql
NO SQL
```

or:

```sql
READS SQL DATA
```

Declaring only `CONTAINS SQL` or `MODIFIES SQL DATA` does not satisfy this list. That does not mean you should falsely declare a routine as `NO SQL` just to create the function. Describe true behavior and handle privileges/settings per DBA policy.

### 7.4. When trusting creators is on

If `log_bin_trust_function_creators = 1`, the server relaxes special privilege and characteristic checks when creating stored functions/triggers under binary logging.

This does NOT:

- Make a function deterministic.
- Verify whether the function is safe for statement-based replication.
- Disable binary logging.
- Change `binlog_format`.
- Replace routine code reviews or replication testing.

This is a server-level configuration decision. Only DBAs or appropriately authorized administrators should change it after evaluating security and replication policies.

### 7.5. Changing variables under control

Example syntax for changing the global variable:

```sql
SET GLOBAL log_bin_trust_function_creators = 1;
```

This command requires appropriate system-variable administration privileges; in modern MySQL, `SYSTEM_VARIABLES_ADMIN` covers many system variable operations. Stored function creation/alteration checks under binary logging still have specific `SUPER` messages and conditions, so do not conflate the two privileges.

Do not run this command merely to make a function creation error disappear. If policy keeps trust creators off, declare routines properly and request proper privileges through process. If a DBA decides to enable it, document the configuration change, scope of impact, and persistence across restarts.

### 7.6. Creation-time checks vs. call-time checks

These are two separate checks that are easy to confuse:

| Stage | With binary logging enabled and trust creators off |
|---|---|
| `CREATE FUNCTION`/`ALTER FUNCTION` | Requires server-mandated admin privileges and at least one of `DETERMINISTIC`, `NO SQL`, or `READS SQL DATA` |
| Calling function when `binlog_format = STATEMENT` | Function must declare `DETERMINISTIC`; otherwise, the statement may be rejected at execution time |
| Calling function when `binlog_format = ROW` or `MIXED` | Server accepts and replicates the statement in row-based format in cases documented by the manual; routine and side effects must still be safe |

For example, a function declaring `NOT DETERMINISTIC READS SQL DATA` satisfies the characteristic check at creation time, yet that does not mean it can be invoked in every statement-based logging context. If `binlog_format = STATEMENT`, the execution-time `DETERMINISTIC` requirement can still reject the call.

Conversely, declaring `DETERMINISTIC` does not guarantee the body is genuinely deterministic. If the server detects or warns about an unsafe statement, address the root cause; do not rely on keywords to silence warnings. When `log_bin_trust_function_creators = 1`, these checks are relaxed, but data integrity risk remains the responsibility of designers and operators.

## 8. Scope of rules: functions, triggers, and procedures

Do not mechanically apply function creation rules to all stored programs.

- Stored functions have `DETERMINISTIC` and SQL data access characteristics; they can be called inside SQL expressions.
- Triggers run when table events occur. Triggers do not declare `DETERMINISTIC` or the four data access characteristics in routine syntax like functions; MySQL assumes triggers are deterministic by default, even if the body contains non-deterministic behavior.
- Stored procedures can declare routine characteristics, but special binary logging rules on creators and function declarations focus on stored functions and triggers.

Stored procedures generally fit multi-step DML business workflows, transaction control, or returning result sets. Functions fit single-value calculations and should minimize side effects for readability, testability, and safe replication.

## 9. Inspecting declared routine characteristics

### 9.1. SHOW CREATE FUNCTION

```sql
SHOW CREATE FUNCTION app_db.fn_line_total;
```

Output shows the function definition, definer, SQL mode, and declared characteristics. This is the direct way to cross-check against source control.

### 9.2. INFORMATION_SCHEMA.ROUTINES

```sql
SELECT
    ROUTINE_SCHEMA,
    ROUTINE_NAME,
    ROUTINE_TYPE,
    IS_DETERMINISTIC,
    SQL_DATA_ACCESS,
    SECURITY_TYPE,
    DEFINER,
    SQL_MODE
FROM information_schema.ROUTINES
WHERE ROUTINE_SCHEMA = 'app_db'
  AND ROUTINE_TYPE = 'FUNCTION'
ORDER BY ROUTINE_NAME;
```

Columns to note:

| Column | Content |
|---|---|
| `IS_DETERMINISTIC` | `YES` or `NO` per saved declaration |
| `SQL_DATA_ACCESS` | `NO SQL`, `CONTAINS SQL`, `READS SQL DATA`, or `MODIFIES SQL DATA` |
| `SECURITY_TYPE` | `DEFINER` or `INVOKER` |
| `DEFINER` | Account used for security context execution |
| `SQL_MODE` | SQL mode saved when the routine was created |

Metadata reflects declarations. It is not proof that MySQL verified the entire body obeys those declarations.

### 9.3. SHOW FUNCTION STATUS

```sql
SHOW FUNCTION STATUS
WHERE Db = 'app_db';
```

This command helps inventory routines, definers, creation timestamps, and modification timestamps. To see the full body and characteristics, pair it with `SHOW CREATE FUNCTION`.

### 9.4. Checking binary logging variables

```sql
SHOW GLOBAL VARIABLES
WHERE Variable_name IN (
    'log_bin',
    'binlog_format',
    'log_bin_trust_function_creators'
);
```

Check on both source and relevant replicas. Never infer every node's configuration from a single server's output.

## 10. Complete examples: pure function and table-reading function

### 10.1. Pure computation function

```sql
DELIMITER $$

CREATE FUNCTION fn_net_amount(
    p_gross_amount DECIMAL(14,2),
    p_discount_percent DECIMAL(5,2)
)
RETURNS DECIMAL(14,2)
DETERMINISTIC
NO SQL
SQL SECURITY INVOKER
BEGIN
    RETURN ROUND(
        p_gross_amount * (1 - p_discount_percent / 100),
        2
    );
END$$

DELIMITER ;
```

Test:

```sql
SELECT fn_net_amount(1000.00, 10.00) AS net_amount;
```

For identical parameters, the result does not depend on tables or time. `NO SQL` and `DETERMINISTIC` are appropriate.

### 10.2. Configuration-table reading function

```sql
CREATE TABLE shipping_rates (
    zone_code VARCHAR(10) NOT NULL,
    effective_from DATE NOT NULL,
    fee DECIMAL(12,2) NOT NULL,
    PRIMARY KEY (zone_code, effective_from)
) ENGINE = InnoDB;
```

```sql
DELIMITER $$

CREATE FUNCTION fn_shipping_fee(p_zone_code VARCHAR(10))
RETURNS DECIMAL(12,2)
NOT DETERMINISTIC
READS SQL DATA
BEGIN
    DECLARE v_fee DECIMAL(12,2) DEFAULT NULL;

    SELECT fee
      INTO v_fee
      FROM shipping_rates
     WHERE zone_code = p_zone_code
       AND effective_from <= CURRENT_DATE
     ORDER BY effective_from DESC
     LIMIT 1;

    RETURN v_fee;
END$$

DELIMITER ;
```

The function reads a table and depends on the current date. Declaring `NOT DETERMINISTIC READS SQL DATA` accurately describes both traits.

### 10.3. Inspecting definitions and metadata

```sql
SHOW CREATE FUNCTION fn_net_amount;
SHOW CREATE FUNCTION fn_shipping_fee;

SELECT
    ROUTINE_NAME,
    IS_DETERMINISTIC,
    SQL_DATA_ACCESS
FROM information_schema.ROUTINES
WHERE ROUTINE_SCHEMA = DATABASE()
  AND ROUTINE_TYPE = 'FUNCTION';
```

Compare results against actual logic. Whenever the body changes, review both characteristics—do not only update the SQL statements.

## 11. Process for evaluating functions before enabling binary logging

Before creating or releasing a function in a replicated system, follow these steps:

1. **Identify purpose:** does the function merely compute a value, read tables, or have data-writing side effects?
2. **List actual inputs:** parameters, time, session state, tables, other routines, and any external state.
3. **Select determinism:** declare `DETERMINISTIC` only if identical parameters truly always yield identical results; otherwise use `NOT DETERMINISTIC`.
4. **Select SQL data access:** use the exact match from `NO SQL`, `CONTAINS SQL`, `READS SQL DATA`, `MODIFIES SQL DATA`.
5. **Check binary logs:** verify `log_bin`, `binlog_format`, and `log_bin_trust_function_creators`.
6. **Check privileges:** confirm `CREATE ROUTINE`, admin privileges required by current configuration, and definer/invoker privileges.
7. **Test on staging:** create the function, call it from representative `SELECT` and DML statements, and verify outputs and side effects.
8. **Test replication:** inspect data on source and replica under the exact production binlog format.
9. **Deploy definitions consistently:** ensure routine definitions, definers, and privileges exist on all required nodes.
10. **Monitor:** track replication errors, lag, and data discrepancies after release.

## 12. Replication scenarios to watch carefully

### 12.1. Time-dependent functions

Functions relying on `CURRENT_DATE` or current time are non-deterministic for identical inputs across time. Declare accurately and understand how built-ins are recorded in the binary log. If business logic needs the same date applied across an entire batch, passing that date as an explicit parameter is usually easier to test.

### 12.2. Functions reading configuration tables

If a function reads price, exchange rate, or tax tables, source and replica must hold consistent data state when the statement is applied. When configuration data updates via a separate process, ensure proper replication ordering and avoid relying on tables excluded from binary logging.

### 12.3. Functions generating UUIDs or random values

Results can differ across calls. For critical DML, consider row-based logging and test on your exact version. Never falsely mark `DETERMINISTIC` to bypass function creation checks.

### 12.4. Functions with side effects

Functions modifying tables create side effects beyond their return value. If an SQL statement is retried, replayed, or executed under a different format, write counts and side-effect ordering must be evaluated. Prefer explicit DML or procedures when side effects are the primary goal.

### 12.5. Configuration differences between source and replica

Check timezones, SQL mode, collation, routine definitions, definers, and privileges across nodes. A function can succeed on the source yet fail on a replica if the routine or definer account is missing there.

## 13. Common errors and fixes

| Error or misconception | Cause | How to handle |
|---|---|---|
| Error 1418 on `CREATE FUNCTION` | Binary logging is on, trust creators is off, and function lacks an accepted declaration | Declare `DETERMINISTIC`, `NO SQL`, or `READS SQL DATA` accurately if genuinely true; verify policy/privileges |
| Error 1419 regarding `SUPER` | Creator lacks admin privilege required by binary logging settings | Check `log_bin_trust_function_creators` and version-specific privileges; coordinate with DBA |
| Marking `DETERMINISTIC` so `CREATE` succeeds despite reading mutable data | Mistaking a declaration for server verification | Fix declaration to match actual logic; evaluate replication safety |
| Table-reading function declared `NO SQL` | Confusing SQL data access with privileges or SQL call context | Use `READS SQL DATA` |
| Function with `INSERT` declared `CONTAINS SQL` | Characteristic does not reflect write operation | Use `MODIFIES SQL DATA` and review side-effect design |
| Identical parameters produce different results | Depends on time, tables, session, or external state | Declare `NOT DETERMINISTIC`; pass dependencies as parameters if appropriate |
| Source and replica diverge | Statement re-executed with different state/values | Check binlog format, function body, built-ins, and data state |
| Thinking `ROW` makes all declarations irrelevant | Row logging only changes how DML is logged, without verifying routines | Still declare accurately; test DDL and replication topology |
| Turning on trust creators to bypass errors | Relaxes checks without making the function safe | Change only per DBA decision with review and testing |
| Checking metadata and assuming the body complies | Metadata only reflects declarations | Read `SHOW CREATE FUNCTION` and inspect actual logic |

## 14. Pre-production checklist

- [ ] Identified every input and state the function truly depends on.
- [ ] `DETERMINISTIC`/`NOT DETERMINISTIC` reflects exact semantics.
- [ ] SQL data access characteristic matches actual statements in the routine.
- [ ] `DETERMINISTIC` or `NO SQL` was not used merely to bypass creation errors.
- [ ] Understood that routine characteristics are advisory and the server does not verify the entire body.
- [ ] Checked `@@GLOBAL.log_bin`.
- [ ] Checked `@@GLOBAL.binlog_format` on the relevant nodes.
- [ ] Checked `@@GLOBAL.log_bin_trust_function_creators`.
- [ ] Confirmed `CREATE ROUTINE` and required administrative privileges.
- [ ] Evaluated impact of `STATEMENT`, `ROW`, or `MIXED` on the workload.
- [ ] Tested functions using time, randomness, UUIDs, or mutable table reads.
- [ ] Tested side effects and stored function restrictions.
- [ ] Checked routine definitions, definers, and privileges on replicas.
- [ ] Verified source/replica data after representative DML statements.
- [ ] Prepared a plan to monitor replication errors and handle data discrepancies.

## 15. Conclusion

`DETERMINISTIC` describes a function that always returns the same result for the same parameters; `NOT DETERMINISTIC` applies when outputs can vary due to time, table data, or other state. `NO SQL`, `CONTAINS SQL`, `READS SQL DATA`, and `MODIFIES SQL DATA` describe the routine's data access level. Both characteristic groups are independent and must accurately reflect the routine body.

Binary logging determines whether replicas receive SQL statements or row changes. Statement-based logging can cause functions to re-execute on replicas; row-based logging records row changes and typically reduces divergence risks for DML; mixed mode combines both. When binary logging is enabled and `log_bin_trust_function_creators` is off, MySQL enforces additional privilege and declaration requirements when creating stored functions. Characteristics are advisory, not proof that the server verified the function is safe. Verify configuration, privileges, routine definitions, and source/replica data before releasing.

## References

- [MySQL 8.4 Reference Manual: CREATE PROCEDURE and CREATE FUNCTION Statements](https://dev.mysql.com/doc/refman/8.4/en/create-procedure.html)
- [MySQL 8.4 Reference Manual: Stored Program Binary Logging](https://dev.mysql.com/doc/refman/8.4/en/stored-programs-logging.html)
- [MySQL 8.4 Reference Manual: Binary Log Formats](https://dev.mysql.com/doc/refman/8.4/en/binary-log-formats.html)
- [MySQL 8.4 Reference Manual: Stored Program Restrictions](https://dev.mysql.com/doc/refman/8.4/en/stored-program-restrictions.html)
- [MySQL 8.4 Reference Manual: Replication and Binary Logging Options and Variables](https://dev.mysql.com/doc/refman/8.4/en/replication-options-binary-log.html)
- [MySQL 8.4 Reference Manual: Replication and System Functions](https://dev.mysql.com/doc/refman/8.4/en/replication-features-functions.html)
