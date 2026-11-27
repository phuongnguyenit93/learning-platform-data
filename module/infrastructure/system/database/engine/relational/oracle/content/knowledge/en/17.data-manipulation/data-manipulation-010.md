# LOG ERRORS and Isolating Failed Rows During Data Loading

When loading data in batches, a few bad rows should not necessarily ruin the entire batch. For instance, out of 100,000 products from a source system, perhaps only a handful violate `NOT NULL`, `CHECK`, column length, or data rules. If the DML statement stops at the very first error, operators have to locate and fix individual rows and re-run the whole batch.

Oracle Database provides **DML error logging** via the `LOG ERRORS` clause. This mechanism allows `INSERT`, `UPDATE`, `DELETE`, or `MERGE` statements to record row-level errors into a log table while continuing to process other rows within a configured limit.

Two commonly used components:

- `DBMS_ERRLOG.CREATE_ERROR_LOG`: creates an error logging table matching the target table's structure.
- `LOG ERRORS INTO ... REJECT LIMIT ...`: specifies the error table, a run-identifying tag, and the maximum tolerated error count.

`LOG ERRORS` separates rejected rows from successfully processed rows. It does not replace source data validation, cannot catch every statement-level SQL error, and does not fix bad data automatically. To load data safely, distinguish row-level errors from statement-failing errors, track batches using tags, and reconcile results before committing.

## 1. How Does DML Error Logging Work?

A normal DML statement stops when encountering a row error. Adding `LOG ERRORS` lets Oracle write error details into the error logging table and continue processing the remaining rows.

~~~text
                 SOURCE ROWS
                      |
                      v
                DML statement
                      |
          +-----------+-----------+
          |                       |
       Row succeeds            Row error
          |                       |
          v                       v
    Change target row       Write error details
                                  |
                                  v
                          Continue within reject limit
~~~

For example, when `INSERT ... SELECT` loads 1,000 rows into a target table:

- 990 valid rows can be inserted.
- 10 rows violating constraints can be written to the error log table.
- The statement continues as long as the error count does not exceed `REJECT LIMIT`.

Actual results depend on error type and DML error logging limitations. Statement-level errors, infrastructure errors, or certain unique constraint violations are not handled as normal row errors; they still cause the statement to fail.

## 2. Error Log Tables Created with DBMS_ERRLOG

Oracle does not automatically create a log table every time `LOG ERRORS` runs. First, create the table using the `DBMS_ERRLOG` package.

### 2.1. CREATE_ERROR_LOG Syntax

~~~sql
BEGIN
    DBMS_ERRLOG.CREATE_ERROR_LOG(
        dml_table_name      => 'TARGET_TABLE',
        err_log_table_name  => 'ERR$_TARGET_TABLE',
        err_log_table_owner => 'APP_SCHEMA',
        err_log_table_space => 'USERS',
        skip_unsupported    => TRUE
    );
END;
/
~~~

Common parameters:

| Parameter | Meaning |
| --- | --- |
| `dml_table_name` | Name of the target table whose DML errors are logged |
| `err_log_table_name` | Name of the log table; if omitted, Oracle defaults to `ERR$_...` |
| `err_log_table_owner` | Schema owning the log table; defaults to package caller context |
| `err_log_table_space` | Tablespace for the log table if explicitly specified |
| `skip_unsupported` | Allows skipping columns with data types unsupported in error log tables |

Table names passed to the package are typically written as stored in the data dictionary—uppercase if created without quoted identifiers. If a table was created with a case-sensitive quoted identifier, follow that exact naming rule.

The executor needs table creation privileges in the target schema and execute privilege on `DBMS_ERRLOG`. In centrally managed environments, DBAs may pre-create error log tables and grant required privileges to batch accounts.

### 2.2. System Columns in the Error Log Table

Oracle creates several technical columns:

| Column | Meaning |
| --- | --- |
| `ORA_ERR_NUMBER$` | Oracle error number |
| `ORA_ERR_MESG$` | Error message |
| `ORA_ERR_ROWID$` | ROWID of the related target row if available |
| `ORA_ERR_OPTYP$` | DML operation type causing the error |
| `ORA_ERR_TAG$` | Tag supplied by the DML statement |

Besides system columns, the log table contains columns matching the supported columns of the target table. This lets operators inspect the offending row values alongside ORA error details.

`ORA_ERR_ROWID$` can be NULL, especially on INSERT errors where no target row was created yet. Do not use this column as a unique tracing key across all DML types.

### 2.3. Columns with Unsupported Data Types

Some target table data types cannot be represented in an error logging table normally, such as LOBs, `LONG`, object types, or collections. Without skipping unsupported columns, creating the log table fails.

`skip_unsupported => TRUE` lets you create the log table while omitting unsupported columns. In that case, values from skipped columns are absent from the error log table. If those columns must be traced, design an auxiliary source-retention mechanism or quarantine table.

Create the log table **once** per target table and reuse it across batches. There is no need to call `CREATE_ERROR_LOG` on every load.

## 3. Lab Data: Target Table and Staging Table

Let us load product catalog data from staging into an inventory table. Staging allows longer strings and NULLs to simulate unnormalized data. The target table enforces stricter constraints.

Run the statements in a practice schema you own, with `CREATE TABLE` privileges and tablespace quota.

### 3.1. Create the Target Table

~~~sql
CREATE TABLE lab_inventory (
    item_id       NUMBER PRIMARY KEY,
    item_name     VARCHAR2(40 CHAR) NOT NULL,
    category_code VARCHAR2(10 CHAR) NOT NULL,
    unit_price    NUMBER(9, 2) NOT NULL,
    CONSTRAINT ck_lab_inventory_price
        CHECK (unit_price >= 0)
);
~~~

Target table rules:

- `ITEM_ID` must be unique.
- `ITEM_NAME`, `CATEGORY_CODE`, and `UNIT_PRICE` cannot be NULL.
- `UNIT_PRICE` cannot be negative.
- Item name max 40 characters; category code max 10 characters.

### 3.2. Create the Staging Table

~~~sql
CREATE TABLE lab_inventory_stage (
    stage_row_id  NUMBER PRIMARY KEY,
    batch_id      NUMBER NOT NULL,
    item_id       NUMBER NOT NULL,
    item_name     VARCHAR2(100 CHAR),
    category_code VARCHAR2(20 CHAR),
    unit_price    NUMBER(12, 2)
);
~~~

`STAGE_ROW_ID` identifies each row received from the source. The staging table is wider and less constrained to retain data needing inspection. The target table enforces the official data rules.

### 3.3. Create the Error Log Table

~~~sql
BEGIN
    DBMS_ERRLOG.CREATE_ERROR_LOG(
        dml_table_name     => 'LAB_INVENTORY',
        err_log_table_name => 'ERR$_LAB_INVENTORY',
        skip_unsupported   => TRUE
    );
END;
/
~~~

After succeeding, the schema has `ERR$_LAB_INVENTORY`. Inspect its structure:

~~~sql
DESC err$_lab_inventory;
~~~

Do not manually create log tables by guessing system column lists. Use the package so Oracle generates the exact structure matching the target table.

### 3.4. Load Source Data for Batch 100

~~~sql
INSERT INTO lab_inventory_stage VALUES
    (1001, 100, 101, 'USB Hub', 'ACCESSORY', 25.00);

INSERT INTO lab_inventory_stage VALUES
    (1002, 100, 102, 'Monitor', 'DISPLAY', 220.00);

INSERT INTO lab_inventory_stage VALUES
    (1003, 100, 103, NULL, 'AUDIO', 30.00);

INSERT INTO lab_inventory_stage VALUES
    (1004, 100, 104, 'Cable', 'ACCESSORY', -2.00);

INSERT INTO lab_inventory_stage VALUES
    (1005, 100, 105, 'Keyboard', NULL, 45.00);

INSERT INTO lab_inventory_stage VALUES
    (1006, 100, 106,
     'This product name is longer than forty characters',
     'ACCESSORY', 10.00);

INSERT INTO lab_inventory_stage VALUES
    (1007, 100, 107, 'Speaker', 'VERY_LONG_CATEGORY', 20.00);

COMMIT;
~~~

The batch has two valid rows and five rows violating target rules:

| STAGE_ROW_ID | ITEM_ID | Issue |
| ---: | ---: | --- |
| 1001 | 101 | Valid |
| 1002 | 102 | Valid |
| 1003 | 103 | `ITEM_NAME` is NULL |
| 1004 | 104 | `UNIT_PRICE` is negative |
| 1005 | 105 | `CATEGORY_CODE` is NULL |
| 1006 | 106 | Name exceeds 40 characters |
| 1007 | 107 | Category code exceeds 10 characters |

## 4. INSERT ... SELECT with LOG ERRORS

This is the common pattern for loading a batch from staging:

~~~sql
INSERT INTO lab_inventory (
    item_id,
    item_name,
    category_code,
    unit_price
)
SELECT
    item_id,
    item_name,
    category_code,
    unit_price
FROM lab_inventory_stage
WHERE batch_id = 100
LOG ERRORS INTO err$_lab_inventory ('LOAD_100')
REJECT LIMIT UNLIMITED;
~~~

Explanation:

- `INSERT INTO` specifies target columns.
- `SELECT` pulls data belonging to batch 100.
- `LOG ERRORS INTO err$_lab_inventory` specifies the error log table.
- `'LOAD_100'` is the tag identifying the run.
- `REJECT LIMIT UNLIMITED` allows continuing while recording all row errors within DML error logging scope.

With the lab dataset, rows 101 and 102 are inserted; the remaining rows are logged into the error table due to `NOT NULL`, `CHECK`, or column length violations.

`UNLIMITED` does not mean the statement can ignore every error. It only removes the cap on tolerated row errors. Statement-level errors, errors unsupported by DML error logging, or resource errors still cause the statement to fail.

## 5. Inspecting Rejected Rows

### 5.1. Querying Errors by Tag

~~~sql
SELECT
    ora_err_number$ AS error_number,
    ora_err_mesg$   AS error_message,
    ora_err_optyp$  AS operation_type,
    ora_err_tag$    AS batch_tag,
    ora_err_rowid$  AS target_rowid,
    item_id,
    item_name,
    category_code,
    unit_price
FROM err$_lab_inventory
WHERE ora_err_tag$ = 'LOAD_100'
ORDER BY item_id;
~~~

Details to examine:

- **Error number/message** shows the violation type and cause reported by Oracle.
- **Operation type** identifies whether the error occurred during INSERT, UPDATE, DELETE, or MERGE.
- **Tag** separates batches/runs.
- Business columns help identify which source row caused the error.

Do not rely on error message text to drive business logic. Messages can change across versions, languages, or contexts; use error numbers and defined handling rules while retaining details for investigation.

### 5.2. Counting Succeeded vs. Failed Rows

~~~sql
SELECT COUNT(*) AS rejected_rows
FROM err$_lab_inventory
WHERE ora_err_tag$ = 'LOAD_100';
~~~

Source rows in the batch:

~~~sql
SELECT COUNT(*) AS source_rows
FROM lab_inventory_stage
WHERE batch_id = 100;
~~~

Current rows in target:

~~~sql
SELECT COUNT(*) AS target_rows
FROM lab_inventory;
~~~

Initially in the lab, the target is empty; after batch 100, expect two valid rows and five errors. In production workflows, do not treat target `COUNT(*)` as the batch's inserted count if the target already held prior data. Record source row counts, error counts per tag, and DML rows processed (such as `SQL%ROWCOUNT` in PL/SQL) in context.

### 5.3. Tracing Back to Staging

Error log tables are built from the **target structure**, not by automatically copying every staging-only column. In the lab, `STAGE_ROW_ID` is not a column of `LAB_INVENTORY`, so it does not appear automatically in `ERR$_LAB_INVENTORY`.

You can locate staging rows by business key if that key uniquely identifies a row:

~~~sql
SELECT
    s.stage_row_id,
    s.batch_id,
    s.item_id,
    s.item_name,
    s.category_code,
    s.unit_price
FROM lab_inventory_stage s
JOIN err$_lab_inventory e
  ON e.item_id = s.item_id
WHERE s.batch_id = 100
  AND e.ora_err_tag$ = 'LOAD_100'
ORDER BY s.stage_row_id;
~~~

If the source can contain multiple rows with the same `ITEM_ID`, joining on `ITEM_ID` alone cannot pinpoint the exact offending row. When exact traceability is required, include a unique correlation key stored in the target/log or maintain a quarantine/validation table holding `STAGE_ROW_ID`, batch, and raw payload. Never assume DML error logs preserve all staging columns automatically.

## 6. Tags Separate Load Runs

A tag is a simple expression passed to `LOG ERRORS`. Use tags to distinguish batches, ETL steps, or operation types:

~~~sql
LOG ERRORS INTO err$_lab_inventory ('BATCH_2026_001')
REJECT LIMIT UNLIMITED
~~~

Example convention:

| Tag | Meaning |
| --- | --- |
| `LOAD_100` | Load batch 100 |
| `PRICE_UPDATE_100` | Price update in batch 100 |
| `MERGE_200` | MERGE sync for batch 200 |
| `REPAIR_2026_01` | Controlled data repair run |

Do not reuse tags ambiguously if historical investigation is needed. Tags should carry enough info to link to an ETL batch/run ID, while avoiding putting sensitive data inside tags.

Query errors grouped by tag:

~~~sql
SELECT
    ora_err_tag$,
    ora_err_number$,
    COUNT(*) AS error_rows
FROM err$_lab_inventory
GROUP BY ora_err_tag$, ora_err_number$
ORDER BY ora_err_tag$, ora_err_number$;
~~~

Error log tables hold long-lived operational data; establish retention, access control, archiving, and batch cleanup policies. Never truncate the log table right after a run before saving or resolving errors needing investigation.

## 7. REJECT LIMIT: Capping Accepted Errors

Syntax:

~~~sql
LOG ERRORS INTO error_table ('tag')
REJECT LIMIT integer
~~~

Or:

~~~sql
LOG ERRORS INTO error_table ('tag')
REJECT LIMIT UNLIMITED
~~~

| Setting | Meaning |
| --- | --- |
| `REJECT LIMIT 0` | Tolerates zero row errors; this is the default when reject limit is omitted |
| `REJECT LIMIT 5` | Allows up to 5 row errors before the statement exceeds the threshold |
| `REJECT LIMIT 100` | Allows up to 100 row errors |
| `REJECT LIMIT UNLIMITED` | No numeric cap on row errors |

Example:

~~~sql
INSERT INTO lab_inventory (item_id, item_name, category_code, unit_price)
SELECT item_id, item_name, category_code, unit_price
FROM lab_inventory_stage
WHERE batch_id = 100
LOG ERRORS INTO err$_lab_inventory ('LOAD_LIMIT_5')
REJECT LIMIT 5;
~~~

If errors exceed the limit, the statement terminates with an error rather than continuing as with `UNLIMITED`. Treat that as a failed load requiring investigation and transactional handling per runbook. Do not assume the statement partially completed in a way the application expects.

Setting `UNLIMITED` fits batches that must collect every loggable row error, yet it does not replace alerts when failure rates spike. A batch with 90% bad rows can still finish syntactically; ETL pipelines must enforce their own data quality thresholds to decide whether to accept the result.

## 8. LOG ERRORS with UPDATE

DML error logging is not limited to INSERT. It works with UPDATE when updating some rows may violate constraints.

Illustrative example: raising prices by 10% where some post-update values might violate target rules:

~~~sql
UPDATE lab_inventory
SET unit_price = unit_price * 1.10
WHERE category_code = 'ACCESSORY'
LOG ERRORS INTO err$_lab_inventory ('PRICE_UP_10')
REJECT LIMIT UNLIMITED;
~~~

In the current lab, valid prices do not turn negative here, so this primarily illustrates syntax. In real systems, errors can arise when updating constrained columns, foreign keys, or data limits. Error logs capture row errors within Oracle's supported scope; unique constraint violations in UPDATE have specific restrictions and should not be assumed to always be logged.

Inspect UPDATE errors by tag:

~~~sql
SELECT
    ora_err_number$,
    ora_err_mesg$,
    ora_err_optyp$,
    item_id,
    item_name,
    unit_price
FROM err$_lab_inventory
WHERE ora_err_tag$ = 'PRICE_UP_10';
~~~

## 9. LOG ERRORS with MERGE

`MERGE` also supports error logging. This is useful during synchronization: some source rows update/insert cleanly while others violate target constraints.

### 9.1. Load Batch 200

Add two rows:

~~~sql
INSERT INTO lab_inventory_stage VALUES
    (2001, 200, 101, 'USB Hub Pro', 'ACCESSORY', -5.00);

INSERT INTO lab_inventory_stage VALUES
    (2002, 200, 103, 'Headset', 'AUDIO', 55.00);

COMMIT;
~~~

ID 101 already exists from batch 100. Its new row has a negative price, violating CHECK on UPDATE. ID 103 does not exist yet and has valid data, so it can be inserted.

### 9.2. MERGE with LOG ERRORS

~~~sql
MERGE INTO lab_inventory t
USING (
    SELECT
        item_id,
        item_name,
        category_code,
        unit_price
    FROM lab_inventory_stage
    WHERE batch_id = 200
) s
ON (t.item_id = s.item_id)
WHEN MATCHED THEN
    UPDATE SET
        t.item_name = s.item_name,
        t.category_code = s.category_code,
        t.unit_price = s.unit_price
WHEN NOT MATCHED THEN
    INSERT (
        item_id,
        item_name,
        category_code,
        unit_price
    )
    VALUES (
        s.item_id,
        s.item_name,
        s.category_code,
        s.unit_price
    )
LOG ERRORS INTO err$_lab_inventory ('MERGE_200')
REJECT LIMIT UNLIMITED;
~~~

Expected result in the lab:

- Row 101 enters MATCHED and UPDATE fails due to negative `UNIT_PRICE`; the error is logged since it falls under Oracle-supported row errors.
- Row 103 enters NOT MATCHED and is inserted.

Verify:

~~~sql
SELECT
    ora_err_number$,
    ora_err_mesg$,
    ora_err_optyp$,
    ora_err_tag$,
    item_id,
    unit_price
FROM err$_lab_inventory
WHERE ora_err_tag$ = 'MERGE_200';

SELECT item_id, item_name, category_code, unit_price
FROM lab_inventory
ORDER BY item_id;
~~~

`LOG ERRORS` does not change MERGE's matching logic. `ON` still decides MATCHED vs. NOT MATCHED; UPDATE/INSERT branches still run as declared. Error logging only handles supported row errors raised during DML execution.

### 9.3. Duplicate Source Keys Still Must Be Resolved First

If the source has multiple rows matching a single target row, `MERGE` can hit `ORA-30926`. DML error logging is not a source-deduplication tool and does not replace building a deterministic source set.

Check duplicates:

~~~sql
SELECT item_id, COUNT(*) AS source_rows
FROM lab_inventory_stage
WHERE batch_id = :batch_id
GROUP BY item_id
HAVING COUNT(*) > 1;
~~~

If you need the latest version, use `ROW_NUMBER()` with a stable tie-breaker in the source subquery before MERGE. If multiple source rows represent transactions to accumulate, aggregate them by target key before MERGE.

## 10. LOG ERRORS with DELETE

DELETE can also use error logging:

~~~sql
DELETE FROM lab_inventory t
WHERE t.category_code = 'OBSOLETE'
LOG ERRORS INTO err$_lab_inventory ('DELETE_OLD')
REJECT LIMIT UNLIMITED;
~~~

If a row cannot be deleted due to a referential constraint or supported row error, Oracle can log the corresponding error. However, deferred constraint violations, statement errors, or cases outside DML error logging scope still fail the statement.

Do not run DELETE examples on business tables just to test error logging. Create dedicated lab data and check foreign key relationships before practicing.

## 11. Separating Failed Data from the Main Load Stream

An error log table stores **DML error information**. For operational handling, failed rows are usually categorized into groups:

1. **Automatically fixable:** such as trimming whitespace or mapping category codes via lookup tables.
2. **Requires source owner fix:** such as missing identifiers, missing mandatory names, or invalid business values.
3. **Unloadable per policy:** permanently rejected or obsolete records.

A common pipeline:

~~~text
Receive source batch
        |
        v
Load into staging (preserve raw values)
        |
        v
Validate and normalize
        |
        v
INSERT / MERGE ... LOG ERRORS
        |
        +----------------------+
        |                      |
        v                      v
Rows accepted             Rows in ERR$_ table
        |                      |
        v                      v
Reconcile counts          Classify by error
        |                      |
        v                      v
Commit/release batch      Repair, quarantine, or reject
~~~

Do not delete failed rows from staging immediately after logging to the error table unless a complete copy is preserved for repair and reload. Error logs may omit source-only columns, making staging critical for traceability.

### 11.1. Grouping Errors by Type

~~~sql
SELECT
    ora_err_number$ AS error_number,
    COUNT(*) AS error_count
FROM err$_lab_inventory
WHERE ora_err_tag$ = 'LOAD_100'
GROUP BY ora_err_number$
ORDER BY error_count DESC, error_number;
~~~

You can group by error number, while mapping error numbers to actions should be managed in application/ETL logic. Never classify errors purely by substring matching inside error messages.

### 11.2. Dedicated Quarantine Table

If you need to preserve the full source payload and resolution status, design a quarantine table:

~~~sql
CREATE TABLE lab_inventory_quarantine (
    stage_row_id      NUMBER PRIMARY KEY,
    batch_id          NUMBER NOT NULL,
    error_code        NUMBER,
    error_message     VARCHAR2(2000),
    received_at       TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
    resolved_at       TIMESTAMP,
    resolution_status VARCHAR2(20) DEFAULT 'PENDING' NOT NULL
);
~~~

A quarantine table can reference staging via `STAGE_ROW_ID`, decoupling data-repair workflows from whether the error log table retains all source columns. In real workflows, define appropriate foreign keys, retention policies, and access permissions.

## 12. Which Errors Are Logged vs. Which Fail the Entire Statement?

`LOG ERRORS` is designed for **row errors** during DML. Not every Oracle error can be converted into a row in the error log.

### 12.1. Examples of Row-Level Errors

Errors caused by a single row's values violating target rules can be logged, depending on operation type and Oracle restrictions:

- `NOT NULL` violations.
- `CHECK` constraint violations.
- String values exceeding column length (`ORA-12899`).
- Certain conversion/column value errors raised while applying DML.
- Certain key or constraint violations within Oracle's supported scope.

Example:

~~~sql
INSERT INTO lab_inventory (item_id, item_name, category_code, unit_price)
VALUES (999, NULL, 'MISC', 10)
LOG ERRORS INTO err$_lab_inventory ('ONE_ROW_TEST')
REJECT LIMIT UNLIMITED;
~~~

This row violates `ITEM_NAME NOT NULL`; when handled by DML error logging, it is written to the error table instead of halting the whole batch.

### 12.2. Examples of Statement-Level or Out-of-Scope Errors

Do not expect the following errors to be written as rows in an error log:

- SQL syntax errors or nonexistent table/column names.
- Insufficient object privileges.
- Unexecutable source queries, such as referencing a missing table or a subquery returning invalid cardinality.
- Resource errors like out-of-tablespace or system failures.
- Violations of `DEFERRABLE` constraints checked only at commit time.
- Certain unique constraint/index violations during UPDATE/MERGE or direct-path INSERT/MERGE per Oracle restrictions.
- Errors that prevent the entire DML from continuing per engine rules.

In particular, never rely on `LOG ERRORS` to handle `ORA-00001` in every scenario. Oracle has documented cases where unique constraint/index violations are not logged by this mechanism; test your exact DML type and execution path on your version.

### 12.3. Errors Inside Source Query Expressions

Distinguish errors while applying a row to the target from errors occurring while Oracle evaluates the source query. For example, if the source query calls `TO_NUMBER(raw_price)` and an unparseable string raises an error inside the expression, the statement can fail before the row reaches target/error-log writing.

For raw source data, validate beforehand:

~~~sql
SELECT stage_row_id, raw_price
FROM lab_inventory_raw_stage
WHERE raw_price IS NOT NULL
  AND VALIDATE_CONVERSION(raw_price AS NUMBER) = 0;
~~~

`VALIDATE_CONVERSION` is available starting in Oracle 12.2. It helps detect values that cannot convert to the target type before running DML. On older releases, use appropriate validation rules or row-by-row PL/SQL handling; do not assume this function exists on every version.

One option is separating convertible and unconvertible rows directly in staging:

~~~sql
-- Convertible rows.
SELECT stage_row_id, TO_NUMBER(raw_price) AS unit_price
FROM lab_inventory_raw_stage
WHERE raw_price IS NOT NULL
  AND VALIDATE_CONVERSION(raw_price AS NUMBER) = 1;

-- Rows needing inspection/repair.
SELECT stage_row_id, raw_price
FROM lab_inventory_raw_stage
WHERE raw_price IS NOT NULL
  AND VALIDATE_CONVERSION(raw_price AS NUMBER) = 0;
~~~

Preserve original values in staging so data can be explained and fixed, rather than overwriting raw values with arbitrary defaults without an audit trail.

## 13. REJECT LIMIT and Transactions

DML error logging is not an independent per-row auto-commit mechanism. Target changes still belong to the statement's transaction, managed by the application or session.

Workflows should:

1. Run DML with a unique tag per batch.
2. Fetch error counts by tag alongside source row counts.
3. Verify target state and error log state.
4. Decide whether to commit or roll back based on data quality criteria.
5. Save batch/run status and mark complete only after transaction handling finishes.

If a statement exceeds `REJECT LIMIT`, it terminates with an error. Do not treat that outcome as a successfully completed batch. Handle the statement error and transaction per runbook; never assume successful rows prior to the threshold were committed.

In multi-step pipelines, avoid committing prematurely between loading the target and recording batch status. Committing target changes before marking the batch complete makes reruns struggle to tell what was already processed.

## 14. Managing Error Log Tables

Error log tables accumulate rows across batches. Manage them like operational tables:

- Use standardized tags linked to run/batch IDs.
- Grant read access only to roles investigating errors; logs may contain personal or sensitive data.
- Define retention periods matching audit and operational requirements.
- Archive/save errors needing resolution before purging.
- Monitor storage size and indexes if log tables grow large.
- Do not recreate log tables on every run; recreating wipes history.

Example cleaning up old data after archiving and authorization:

~~~sql
DELETE FROM err$_lab_inventory
WHERE ora_err_tag$ = 'LOAD_100';
~~~

Run cleanup only per retention policy. In production systems, delete by age or completed batch status rather than deleting by a shared tag.

## 15. Common Errors

| Symptom | Cause | Resolution |
| --- | --- | --- |
| `LOG ERRORS` reports error table not found | Table not created yet or wrong schema/name | Use `DBMS_ERRLOG.CREATE_ERROR_LOG` and verify owner |
| No error rows visible after DML | Query tag mismatch, zero row errors, or unsupported statement failure | Check tag, error code, and statement status |
| `CREATE_ERROR_LOG` fails on column type | Target table has types unsupported in error tables | Use `skip_unsupported => TRUE` and store traceable data separately |
| Batch stops on first error | Missing LOG ERRORS or default reject limit of 0 | Add error logging and set an appropriate reject limit |
| `UNLIMITED` set, yet statement still fails | Error outside row-level logging scope or resource/statement failure | Fix root cause; do not treat UNLIMITED as ignoring all errors |
| Cannot trace `STAGE_ROW_ID` | Error table mirrors target columns, not source-only columns | Use a unique correlation key or quarantine table |
| Source has conversion errors not logged to error table | Error happened inside source expression before DML | Validate/normalize staging data first |
| `ORA-30926` during MERGE | Source has multiple rows hitting one target row | Deduplicate or aggregate source before MERGE |
| Unique violation not logged as expected | Certain unique constraint/index violations fall outside DML error logging | Design keys, check duplicates, handle separately; check release restrictions |
| Error log table grows without bound | Missing retention/archiving | Manage by batch and retention window |
| Target data changed while batch not marked complete | Commit and batch status update uncoordinated | Design consistent transaction and checkpoint boundaries |

## 16. Practice Exercises

Use `LAB_INVENTORY`, `LAB_INVENTORY_STAGE`, and `ERR$_LAB_INVENTORY` from section 3.

### Exercise 1 — Create Error Log Table

Call `DBMS_ERRLOG.CREATE_ERROR_LOG` for `LAB_INVENTORY`. Use `DESC` to identify the five system columns and target data columns.

### Exercise 2 — Load Batch with Bad Rows

Run `INSERT ... SELECT ... LOG ERRORS` for batch 100. Record:

- Total source rows.
- Row count in target after loading.
- Error count under tag `LOAD_100`.
- Error codes and messages of each rejected row.

### Exercise 3 — Classify Errors

Classify the five failed rows by NOT NULL, CHECK, and column length. Write an aggregation query counting errors by `ORA_ERR_NUMBER$`.

### Exercise 4 — Trace Back to Staging

Join the error log with staging on `ITEM_ID`. Then insert two staging rows sharing the same `ITEM_ID` and explain why that key is no longer sufficient to trace a single row. Propose using `STAGE_ROW_ID` in a quarantine table.

### Exercise 5 — Reject Limit

Run a copy of the lab data with `REJECT LIMIT 1`, then with `UNLIMITED`. Observe behavior when errors exceed the threshold. Inspect target and error log state inside your transaction before committing.

### Exercise 6 — MERGE with Error Logging

Run batch 200 from section 9. Identify which row enters MATCHED, which enters NOT MATCHED, and which error is logged under tag `MERGE_200`.

### Exercise 7 — Source Conversion Errors

Create a raw staging table with `RAW_PRICE VARCHAR2`. Insert one valid numeric string and one unparseable string. Use `VALIDATE_CONVERSION` to separate both groups before inserting into the target.

### Exercise 8 — Complete Batch Workflow

Design the steps for receiving a batch, validating, running DML with LOG ERRORS, checking error rates, quarantining, committing/rolling back, and marking batch completion. State clearly when an entire batch must be aborted even with `REJECT LIMIT UNLIMITED`.

## 17. Clean Up Lab Data

Run only in the practice schema you created, after saving any needed results:

~~~sql
DROP TABLE err$_lab_inventory PURGE;
DROP TABLE lab_inventory_stage PURGE;
DROP TABLE lab_inventory PURGE;
~~~

The error log table has no foreign key dependency on the target, though dropping it first keeps cleanup order intuitive. `PURGE` bypasses the recycle bin; never use it on business tables or data needing recovery.

## Summary

`DBMS_ERRLOG.CREATE_ERROR_LOG` creates an error-capture table for a target table; `LOG ERRORS INTO ... ('tag') REJECT LIMIT ...` attaches that table to a DML statement and identifies the run. When an error within row-level logging scope occurs, Oracle records the error code, message, operation type, tag, and supported target columns, then continues up to the reject limit.

Always distinguish row errors from errors that fail the entire statement. `REJECT LIMIT UNLIMITED` does not bypass syntax errors, source query errors, resource errors, deferred constraints, or all unique violations. For staging data, validate conversion expressions before DML; normalize sources before MERGE; preserve correlation keys for tracing; and maintain error logs by batch to repair or quarantine failed rows. Only commit when target counts, error counts, and batch status are reconciled according to data-loading policy.

## Oracle Reference Documentation

- [Oracle Database SQL Language Reference — INSERT (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/INSERT.html) — DML error logging clause and reject limit syntax.
- [Oracle Database PL/SQL Packages and Types Reference — DBMS_ERRLOG (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_ERRLOG.html) — `CREATE_ERROR_LOG` and error table structure.
- [Oracle Database SQL Language Reference — MERGE (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/MERGE.html) — using error logging in MERGE.
- [Oracle Database SQL Language Reference — UPDATE (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/UPDATE.html) — error logging in UPDATE.
- [Oracle Database SQL Language Reference — DELETE (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/DELETE.html) — error logging in DELETE.
- [Oracle Database SQL Language Reference — VALIDATE_CONVERSION (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/VALIDATE_CONVERSION.html) — checking conversion validity before loading.

When deploying on an Oracle release other than 19c, check the SQL Language Reference and PL/SQL Packages Reference for that exact version, particularly regarding data type restrictions, unique constraints, direct-path DML, and reject limits.
