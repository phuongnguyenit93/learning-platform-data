# Warnings vs. Errors and Reading SHOW WARNINGS

This lesson belongs to the **SQL Modes and Semantics** chapter of the `DATABASE_MYSQL` module. The module aims to master MySQL from table design, data types, keys, and SQL queries to indexes, transactions, concurrency control, reading execution plans, query tuning, authorization, backups, and handling relational database operational issues. When MySQL receives data or executes statements, the server can generate errors, warnings, or notes. Understanding the severity of each condition helps determine whether a statement failed, whether data was adjusted, and how to proceed.

After this lesson, you will be able to distinguish Error, Warning, and Note; understand the impact of SQL mode and strict mode; read `SHOW WARNINGS` and `SHOW ERRORS` output; check condition counts; and handle malformed, out-of-range, or converted data scenarios.

## 1. How Do Errors, Warnings, and Notes Differ?

MySQL classifies conditions generated during statement execution into three common severity levels:

| Level | Meaning | Typical Impact |
|---|---|---|
| **Error** | The statement encountered a condition preventing the server from continuing as requested | The statement is aborted or incomplete; with InnoDB, changes made by that statement are typically rolled back |
| **Warning** | The server detected a problem yet can continue executing | The statement may complete; data may have been adjusted, truncated, skipped, or substituted |
| **Note** | Supplemental information about processing | Usually does not fail the statement or abnormally alter data |

Example:

- Inserting 300 into a `TINYINT UNSIGNED` column in strict mode can cause an Error because the value exceeds the limit.
- Inserting the same value when strict mode is off may adjust it to 255 and generate a Warning.
- Using `DROP TABLE IF EXISTS` on a nonexistent table can generate a Note indicating there was no table to drop.

Do not interpret a Warning as "no problem". A statement can return `Query OK` yet still store truncated or converted data. If an application ignores Warnings, invalid data can propagate into downstream processing steps.

Conversely, an Error does not necessarily mean the entire transaction has been rolled back. With InnoDB, a single statement error typically rolls back that statement's changes; the transaction may still remain open. With non-transactional storage engines, a multi-row statement may leave partial changes depending on the error type and SQL mode.

## 2. SQL Mode Determines How Certain Invalid Data Is Handled

`sql_mode` is a system variable that specifies a set of SQL syntax and semantic rules. Several modes directly influence whether MySQL raises a Warning or an Error when encountering invalid values.

Check configuration:

~~~sql
SELECT
    @@GLOBAL.sql_mode AS global_sql_mode,
    @@SESSION.sql_mode AS session_sql_mode;
~~~

- **Global SQL mode** is the default value applied to new sessions.
- **Session SQL mode** governs behavior in the current connection.
- Session changes affect only the current connection.
- Global changes affect only new connections; already open sessions retain their own values.

In MySQL 9.7, the default SQL mode includes modes such as:

- `ONLY_FULL_GROUP_BY`
- `STRICT_TRANS_TABLES`
- `NO_ZERO_IN_DATE`
- `NO_ZERO_DATE`
- `ERROR_FOR_DIVISION_BY_ZERO`
- `NO_ENGINE_SUBSTITUTION`

Actual configurations can differ due to startup options, configuration files, or administrative operations. Therefore, check `@@SESSION.sql_mode` in the exact connection executing the statement under diagnosis.

### Strict Mode

MySQL treats strict mode as a state where at least one of these two modes is enabled:

- `STRICT_TRANS_TABLES`
- `STRICT_ALL_TABLES`

Strict mode controls how invalid or missing values are handled in data-modifying statements such as `INSERT`, `UPDATE`, `LOAD DATA`, as well as certain DDL operations.

Examples of invalid data:

- Numeric values outside the column type's range.
- Strings that cannot be properly converted to a numeric type.
- Strings longer than the column limit.
- Missing value for a `NOT NULL` column without a `DEFAULT`.
- Invalid dates/times according to active modes.

If strict mode is disabled, MySQL may adjust the value to fit the column and emit a Warning. If strict mode is enabled, similar cases are elevated to Errors.

Strict mode does not turn every Warning into an Error. It applies to specific categories of data errors defined by MySQL. For example, a SELECT statement performing division by zero still returns NULL and a Warning, even when strict mode is enabled.

### STRICT_TRANS_TABLES and STRICT_ALL_TABLES

These two modes have notable differences with storage engines that do not support transactions.

| Scenario | STRICT_TRANS_TABLES | STRICT_ALL_TABLES |
|---|---|---|
| Transactional table like InnoDB | Invalid value causes an Error and the statement is rolled back | Same |
| Non-transactional table, error on the first row | Aborts the statement | Aborts the statement |
| Non-transactional table, error on the second or later row in a multi-row statement | May adjust the invalid value to the closest valid value, emit a Warning, and continue | Reports an Error and stops; earlier rows may already be written, producing a partial result |

Thus, strict mode is no substitute for storage engine choice. For business data requiring atomic rollback, use InnoDB and avoid relying on non-transactional table behavior.

## 3. IGNORE Can Downgrade Certain Errors to Warnings

Some statements support the `IGNORE` keyword, for example:

- `INSERT IGNORE`
- `UPDATE IGNORE`
- `DELETE IGNORE`
- `LOAD DATA ... IGNORE`

In scenarios permitted by MySQL, `IGNORE` downgrades certain Errors to Warnings so the statement continues.

Example:

- Out-of-range values may be adjusted to the nearest valid value.
- Overly long strings may be truncated.
- Rows violating a unique key may be skipped instead of failing the entire statement.

`IGNORE` can be used alongside strict mode. In that case, for ignorable errors, `IGNORE` takes precedence and conditions that would normally raise an Error can become Warnings.

However, not all Errors can be ignored. Syntax errors, connection errors, missing privileges, and errors outside the ignorable set can still fail the statement.

Do not add `IGNORE` merely to make a batch import "finish running". If data is truncated, substituted, or skipped, the application needs a workflow to inspect and report affected rows.

## 4. What Information Does SHOW WARNINGS Read?

Syntax:

~~~sql
SHOW WARNINGS;
SHOW WARNINGS LIMIT 10;
SHOW WARNINGS LIMIT 5, 10;
SHOW COUNT(*) WARNINGS;
~~~

`SHOW WARNINGS` is a diagnostic statement that displays conditions generated by the most recent non-diagnostic statement in the current session.

The output has three columns:

| Column | Meaning |
|---|---|
| `Level` | Condition severity: Note, Warning, or Error |
| `Code` | MySQL numeric error code |
| `Message` | Text describing the condition |

Example output:

~~~text
+---------+------+------------------------------------------------------+
| Level   | Code | Message                                              |
+---------+------+------------------------------------------------------+
| Warning | 1264 | Out of range value for column 'quantity' at row 1    |
| Warning | 1265 | Data truncated for column 'label' at row 1           |
+---------+------+------------------------------------------------------+
~~~

An entry with `Level = Error` can also appear in `SHOW WARNINGS` after a failed statement. Despite its name, this command does not display only Warnings; it displays Errors, Warnings, and Notes.

### Viewing Errors Only

If you only want to view Errors:

~~~sql
SHOW ERRORS;
SHOW ERRORS LIMIT 10;
SHOW COUNT(*) ERRORS;
~~~

`SHOW ERRORS` is similar to `SHOW WARNINGS` but returns only conditions at the Error level.

### Limiting Displayed Rows

`LIMIT` works like SELECT syntax:

~~~sql
-- Show at most the first 10 conditions
SHOW WARNINGS LIMIT 10;

-- Skip the first 5 conditions, fetch the next 10
SHOW WARNINGS LIMIT 5, 10;
~~~

When a statement generates many Warnings, the displayed output may not contain every message. Understand the `max_error_count` variable before concluding there were only a handful of data errors.

## 5. Read Warnings Immediately After the Statement That Caused Them

Information in the diagnostics area is tied to the most recent statement. A subsequent ordinary SQL statement can clear previous conditions and replace them with its own conditions.

Example of what not to do:

~~~sql
INSERT INTO warning_demo (id, quantity)
VALUES (1, 300);

SELECT * FROM warning_demo;

-- Information from the INSERT may already be lost
SHOW WARNINGS;
~~~

After INSERT, SELECT is a non-diagnostic statement. It replaces the diagnostics area before `SHOW WARNINGS` is called.

Correct approach:

~~~sql
INSERT INTO warning_demo (id, quantity)
VALUES (1, 300);

SHOW WARNINGS;
~~~

If you need to count conditions, you can use a diagnostic statement:

~~~sql
INSERT INTO warning_demo (id, quantity)
VALUES (1, 300);

SHOW COUNT(*) WARNINGS;
SHOW WARNINGS;
~~~

`SHOW COUNT(*) WARNINGS` is also a diagnostic statement, so it does not clear the condition list. Conversely, `SELECT @@warning_count` is non-diagnostic; it can replace the diagnostics area. Read Warnings before executing SELECT or any other regular query.

### What Is the Diagnostics Area?

The diagnostics area is the information structure MySQL uses to store conditions from the most recently executed statement. It holds the condition count and detailed information for each stored condition.

Diagnostic statements such as:

- `SHOW WARNINGS`
- `SHOW ERRORS`
- `GET DIAGNOSTICS`

can read this information without clearing existing conditions.

Ordinary SQL statements such as SELECT, INSERT, UPDATE, DELETE, or DDL create a new diagnostics area when executed. Therefore, inspect immediately after the statement being diagnosed.

## 6. warning_count, error_count, and max_error_count

MySQL provides variables and statements to count conditions.

| Item | Meaning |
|---|---|
| `SHOW COUNT(*) WARNINGS` | Total Errors, Warnings, and Notes from the most recent statement |
| `@@warning_count` | Number of conditions, including Errors, Warnings, and Notes (excluding Notes if `sql_notes=0`) |
| `SHOW COUNT(*) ERRORS` | Total Errors from the most recent statement |
| `@@error_count` | Number of Errors from the most recent statement |
| `max_error_count` | Maximum number of conditions MySQL stores in detail in the diagnostics area |
| `sql_notes` | Controls storing and counting Notes |

The name `warning_count` can be misleading: this value does not count Warnings alone. It counts total conditions including Errors, Warnings, and Notes. To count Errors specifically, use `error_count` or `SHOW COUNT(*) ERRORS`.

### max_error_count

In MySQL 9.7, `max_error_count` defaults to 1024, with a range from 0 to 65535.

This variable only limits how many conditions are stored in detail for display by `SHOW WARNINGS`, `SHOW ERRORS`, or reading via `GET DIAGNOSTICS`. It does not limit how many conditions are counted.

For example, if a statement generates 20 Warnings while `max_error_count = 5`:

- `warning_count` is still 20.
- The diagnostics area retains at most 5 conditions.
- `SHOW WARNINGS` can only display the conditions that were stored.

If `max_error_count = 0`, MySQL still counts conditions but stores no detailed messages for review.

Check:

~~~sql
SHOW VARIABLES LIKE 'max_error_count';
~~~

Only increase this variable when analyzing a statement that generates many conditions. Do not default it to the maximum across every session.

### sql_notes

`sql_notes` defaults to 1. When set to 0, MySQL does not store Notes and does not include Notes in `warning_count`.

~~~sql
SELECT @@SESSION.sql_notes;

SET SESSION sql_notes = 0;
SET SESSION sql_notes = 1;
~~~

Disabling Notes does not suppress Warnings or Errors. During diagnostics, keep `sql_notes = 1` to retain complete information.

## 7. Example: Strict Mode Produces Errors, IGNORE Produces Warnings

This lab exercise demonstrates an out-of-range value and an overly long string.

### Step 1: Create the Table

~~~sql
CREATE DATABASE IF NOT EXISTS mysql_diagnostics_lab;
USE mysql_diagnostics_lab;

CREATE TABLE warning_demo (
    id INT NOT NULL PRIMARY KEY,
    quantity TINYINT UNSIGNED NOT NULL,
    label VARCHAR(5) NOT NULL
) ENGINE=InnoDB;
~~~

The `quantity` column only accepts values from 0 to 255. The `label` column accepts at most 5 characters.

### Step 2: Enable Strict Mode for the Session

Save the current configuration before changing:

~~~sql
SET @saved_sql_mode = @@SESSION.sql_mode;

SET SESSION sql_mode =
    'STRICT_TRANS_TABLES,NO_ENGINE_SUBSTITUTION';
~~~

Verify:

~~~sql
SELECT @@SESSION.sql_mode;
~~~

### Step 3: Attempt to Insert Out-of-Bounds Data

~~~sql
INSERT INTO warning_demo (id, quantity, label)
VALUES (1, 300, 'OK');
~~~

Since `quantity` is `TINYINT UNSIGNED`, the value 300 is out of range. In strict mode, the statement raises an Error and aborts.

Read conditions immediately after the statement:

Run the failing INSERT statement individually first. When the client reports an Error, send `SHOW WARNINGS` or `SHOW ERRORS` next in the same session. Some script/batch execution modes halt immediately on Error; in that case, open an interactive connection or configure the runner to continue on error so you can read diagnostics.

~~~sql
SHOW WARNINGS;
SHOW ERRORS;
~~~

You will see an Error corresponding to the out-of-range value, typically code 1264.

Verify the data:

~~~sql
SELECT * FROM warning_demo;
~~~

Because the table uses InnoDB, the failed INSERT statement leaves no row.

### Step 4: Try INSERT IGNORE

Insert data again, this time using `IGNORE`:

~~~sql
INSERT IGNORE INTO warning_demo (id, quantity, label)
VALUES (1, 300, 'TOOLONG');
~~~

In this case, MySQL may adjust:

- `quantity`: from 300 down to the maximum valid value of 255.
- `label`: truncated to 5 characters.

The statement may complete with Warnings instead of an Error.

Read the messages immediately:

~~~sql
SHOW WARNINGS;
~~~

Check the data that was written:

~~~sql
SELECT * FROM warning_demo;
~~~

You will see a row with `quantity = 255` and `label = 'TOOLO'`. This is a classic example showing that `Query OK` does not guarantee data was stored intact as supplied.

### Step 5: Try a SELECT That Generates a Warning

Strict mode does not elevate every Warning to an Error. Example:

~~~sql
SELECT 1 / 0 AS division_result;
SHOW WARNINGS;
~~~

Division by 0 in SELECT returns NULL and emits a Warning. The SELECT statement still completes.

### Step 6: Restore SQL Mode and Clean Up

Restore the original mode in the same session:

~~~sql
SET SESSION sql_mode = @saved_sql_mode;
~~~

Once finished, drop the lab database:

~~~sql
DROP DATABASE mysql_diagnostics_lab;
~~~

Run DROP only on the lab database just created. This command deletes all practice tables and data.

## 8. Example: Distinguishing Warnings and Notes

### Warnings from Data Conversion

If strict mode is off, malformed data can be adjusted and generate a Warning:

~~~sql
SET @saved_sql_mode = @@SESSION.sql_mode;
SET SESSION sql_mode = '';

CREATE TABLE conversion_demo (
    id INT PRIMARY KEY,
    amount INT
) ENGINE=InnoDB;

INSERT INTO conversion_demo (id, amount)
VALUES (1, 'abc');

SHOW WARNINGS;
~~~

MySQL may convert the string `abc` to a matching default numeric value (0) and emit a Warning about invalid numeric conversion.

Inspect the stored row:

~~~sql
SELECT * FROM conversion_demo;
~~~

Restore configuration and drop the table:

~~~sql
DROP TABLE conversion_demo;
SET SESSION sql_mode = @saved_sql_mode;
~~~

Run this example in an isolated lab session. Never leave SQL mode empty in applications or shared systems just to allow bad data to be accepted.

### Notes from IF EXISTS Statements

Example:

~~~sql
DROP TABLE IF EXISTS table_that_does_not_exist;
SHOW WARNINGS;
~~~

If the table does not exist, the statement still completes and MySQL may return a Note with code 1051. The Note indicates the object does not exist, yet `IF EXISTS` prevented that condition from failing the statement.

If `sql_notes = 0`, the Note is neither stored nor counted in `warning_count`.

## 9. Retrieving Conditions with GET DIAGNOSTICS

Besides `SHOW WARNINGS`, MySQL supports `GET DIAGNOSTICS` for reading conditions in SQL, which is particularly useful when writing stored procedures or structured error handling.

Count conditions:

~~~sql
GET DIAGNOSTICS @condition_count = NUMBER;
~~~

Retrieve details of the first condition:

~~~sql
GET DIAGNOSTICS CONDITION 1
    @sqlstate = RETURNED_SQLSTATE,
    @mysql_errno = MYSQL_ERRNO,
    @message = MESSAGE_TEXT;
~~~

Commonly used items:

| Item | Meaning |
|---|---|
| `NUMBER` | Number of conditions in the diagnostics area |
| `RETURNED_SQLSTATE` | SQLSTATE of the condition |
| `MYSQL_ERRNO` | MySQL numeric error code |
| `MESSAGE_TEXT` | Message text |
| `ROW_NUMBER` | Associated row number if the condition includes this info |

Complete example after a statement with Warnings:

~~~sql
INSERT IGNORE INTO warning_demo (id, quantity, label)
VALUES (2, 300, 'TOOLONG');

GET DIAGNOSTICS @condition_count = NUMBER;

GET DIAGNOSTICS CONDITION 1
    @sqlstate = RETURNED_SQLSTATE,
    @mysql_errno = MYSQL_ERRNO,
    @message = MESSAGE_TEXT;

SELECT
    @condition_count AS condition_count,
    @sqlstate AS sqlstate,
    @mysql_errno AS mysql_errno,
    @message AS message;
~~~

Here, `GET DIAGNOSTICS` captures the information before SELECT executes. The final SELECT displays the saved variables.

If a statement produces multiple conditions, you can loop from 1 to `NUMBER` to retrieve each condition. Check the condition count before accessing a specific position.

## 10. Viewing Warnings Automatically in the mysql Client

When working with the `mysql` command-line client, you can enable displaying Warnings automatically right after statements:

~~~text
mysql> \W
Show warnings enabled.
~~~

Afterward, whenever a statement generates Warnings, the client prints the messages right after the result.

Disable this mode:

~~~text
mysql> \w
Show warnings disabled.
~~~

You can use the corresponding client commands `warnings` and `nowarning`.

This is a feature of the command-line client, not an SQL statement, and does not change the server's SQL mode. If using Workbench or another connector, check the tool's message pane and run `SHOW WARNINGS` right after the statement under inspection.

## 11. Workflow for Diagnosing Warnings/Errors in Applications

When a statement returns an Error or Warning, follow this sequence:

1. **Record the statement and session:** save the executed SQL, parameters, database, user, and `@@SESSION.sql_mode`. Do not write passwords or secrets to logs.
2. **Read client results:** determine whether the statement succeeded or failed, the affected row count, and the reported Warning count.
3. **Run SHOW WARNINGS immediately:** do not run SELECT or any other ordinary SQL statement before this step.
4. **Classify the condition:** inspect Level, Code, and Message; if SQLSTATE is needed, use `GET DIAGNOSTICS`.
5. **Inspect actual data:** determine whether any value was truncated, converted, substituted, or skipped.
6. **Check SQL mode:** confirm strict mode, `IGNORE`, `sql_notes`, and related modes.
7. **Fix the root cause:** examine column types, lengths, input values, charset, dates/times, and data constraints.
8. **Re-test:** run against representative data, verifying row counts and stored contents.
9. **Log structurally:** record error code, SQLSTATE, message, statement identifier, and relevant row counts for investigation.

Do not rely solely on the driver's return status. Some drivers return success when a statement emits Warnings; the application must check warning counts or enable appropriate diagnostic retrieval.

### Distinguishing Statement Errors from Transaction Errors

With InnoDB, a multi-row INSERT statement hitting a strict-mode Error is typically rolled back at the statement level. The outer transaction may still remain active.

Example:

~~~sql
START TRANSACTION;

INSERT INTO warning_demo (id, quantity, label)
VALUES (10, 10, 'valid');

INSERT INTO warning_demo (id, quantity, label)
VALUES (11, 300, 'invalid');

-- The second statement failed.
-- The first statement may still be active inside the transaction.
ROLLBACK;
~~~

If an application simply catches the exception and continues without deciding to COMMIT or ROLLBACK, the transaction can hold locks or remain in an incomplete state. Define clear transaction-handling rules whenever a statement fails.

## 12. Common Mistakes

| Mistake | Consequence | Resolution |
|---|---|---|
| Seeing `Query OK` and assuming data is intact | Values may have been truncated or adjusted | Read Warnings and inspect stored data |
| Running SELECT before SHOW WARNINGS | Diagnostics area was overwritten | Run SHOW WARNINGS right after the original statement |
| Thinking SHOW WARNINGS only shows Warnings | Missing Errors or Notes | Check the Level column; use SHOW ERRORS when only Errors are needed |
| Confusing `warning_count` with pure Warning count | Miscounting total conditions | Remember it includes Errors, Warnings, and Notes |
| Setting `max_error_count=0` to cut overhead and expecting details | No condition details remain to display | Keep a limit suited to diagnostic needs |
| Using INSERT IGNORE for every batch | Bad data may be modified or rows silently skipped | Use only with explicit data-acceptance rules and error-row reporting |
| Disabling strict mode in production to avoid errors | Bad data may be saved in adjusted form | Fix source data and maintain appropriate strict mode |
| Assuming an Error always rolls back the entire transaction | Transaction may remain open holding locks | Handle COMMIT/ROLLBACK explicitly in the application |
| Assuming strict mode promotes every Warning to an Error | Misunderstanding SELECT and other condition behavior | Review strict mode rules by operation group and error type |

## 13. Pre-Production Data Processing Checklist

- [ ] Checked `@@GLOBAL.sql_mode` and `@@SESSION.sql_mode`.
- [ ] Understood the impact of `STRICT_TRANS_TABLES` and `STRICT_ALL_TABLES`.
- [ ] Avoided using `IGNORE` without a policy for handling adjusted or skipped data.
- [ ] Application records both affected row count and Warning count.
- [ ] Critical statements include a step to read Warnings/Errors when needed.
- [ ] No ordinary SQL statements run between the inspected operation and `SHOW WARNINGS`.
- [ ] Configured `max_error_count` large enough to diagnose workloads.
- [ ] Did not disable `sql_notes` if Note details need to be retained.
- [ ] Distinguished statement-level errors from transaction-level errors.
- [ ] Verified data after imports/updates to catch truncation or conversion.
- [ ] Logged SQLSTATE, MySQL code, and message without exposing secret data.
- [ ] Tested out-of-range values, wrong types, and NULL values.

## Official References

Behaviors in this lesson were verified against the **MySQL 9.7 Reference Manual** as of **19-11-2026**:

1. [SHOW WARNINGS Statement](https://dev.mysql.com/doc/refman/9.7/en/show-warnings.html): syntax, output, warning_count, max_error_count, sql_notes, and diagnostic behavior.
2. [SHOW ERRORS Statement](https://dev.mysql.com/doc/refman/9.7/en/show-errors.html): reading only Error-level conditions.
3. [Server SQL Modes](https://dev.mysql.com/doc/refman/9.7/en/sql-mode.html): strict mode, STRICT_TRANS_TABLES, STRICT_ALL_TABLES, IGNORE, and handling invalid data.
4. [The MySQL Diagnostics Area](https://dev.mysql.com/doc/refman/9.7/en/diagnostics-area.html): how the diagnostics area is populated, cleared, and read.
5. [GET DIAGNOSTICS Statement](https://dev.mysql.com/doc/refman/9.7/en/get-diagnostics.html): reading condition counts, SQLSTATE, error codes, and messages.
6. [Server System Variables](https://dev.mysql.com/doc/refman/9.7/en/server-system-variables.html): scopes and values of `max_error_count`, `sql_notes`, and `sql_mode`.
7. [mysql Client Commands](https://dev.mysql.com/doc/refman/9.7/en/mysql-commands.html): toggling automatic Warning display in the command-line client.
