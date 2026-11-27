# INSERT IGNORE, Warnings, and the Risk of Masking Invalid Data

MySQL provides the INSERT IGNORE modifier to continue processing when certain errors occur during data insertion. For rows that violate a PRIMARY KEY or UNIQUE key, MySQL typically skips the conflicting row and emits a warning. For certain data conversion errors, values may be adjusted or truncated into a storable form and then inserted along with a warning.

This mechanism is useful when intentionally importing duplicate data, syncing by source key, or running batches that need to skip already-existing records. However, INSERT IGNORE can allow invalid data to enter a table while the statement still reports success. If you only check whether the statement threw an error, the system can miss truncated values, out-of-range numbers, invalid dates, or skipped records.

In the **DATABASE_MYSQL** module, INSERT IGNORE must be understood alongside key constraints, SQL mode, warning diagnostics, transactions, and import data controls. This lesson distinguishes duplicate skipping from type coercion, shows how to read warnings, handle them in Java/JDBC, and build a reconcilable import workflow.

## 1. What Is INSERT IGNORE?

INSERT IGNORE is a variant of INSERT. The IGNORE keyword instructs MySQL to downgrade certain insert-time errors to warnings and continue processing the remaining rows, rather than aborting the entire statement on errors in the ignorable category.

Basic syntax:

```sql
INSERT IGNORE INTO table_name (column_a, column_b)
VALUES
    (value_a1, value_b1),
    (value_a2, value_b2);
```

It can also be used with INSERT ... SELECT:

```sql
INSERT IGNORE INTO target_table (id, name)
SELECT source_id, source_name
FROM staging_table;
```

Crucially, IGNORE does not mean "ignore all errors." Invalid SQL syntax, missing tables, insufficient privileges, connection failures, and many fatal execution errors still cause the statement to fail. For each constraint and data type, verify the exact behavior on your MySQL version and storage engine.

## 2. Two Behaviors to Distinguish: Skipping Rows vs. Adjusting Values

INSERT IGNORE is commonly used in two very different categories of situations:

| Situation | Typical Behavior | Risk |
|---|---|---|
| Duplicate PRIMARY KEY or UNIQUE | New row is skipped, existing row remains unchanged | You will not know how many rows were skipped without reading warnings and reconciling |
| Invalid or out-of-range value | Some errors become warnings; values may be clamped to the nearest boundary or truncated and inserted | Altered data still ends up in the table |
| Other constraint violations | May be rejected, skip the row, or follow error- and version-specific rules | Do not assume every constraint is handled by IGNORE the same way as duplicates |
| Syntax or infrastructure errors | Statement still fails | IGNORE does not replace application error handling |

### 2.1. Duplicate Key: Skipping the Conflicting Row

Suppose a table has a unique key on email:

```sql
CREATE TABLE members (
    member_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    email VARCHAR(254) NOT NULL,
    display_name VARCHAR(100) NOT NULL,
    PRIMARY KEY (member_id),
    UNIQUE KEY uk_members_email (email)
) ENGINE = InnoDB;
```

Insert a member:

```sql
INSERT INTO members (email, display_name)
VALUES ('an@example.com', 'An');
```

Insert the same email again:

```sql
INSERT IGNORE INTO members (email, display_name)
VALUES ('an@example.com', 'An Nguyen');

SHOW WARNINGS;
```

Because the email already exists, the new row is skipped. The existing row is not updated to An Nguyen. This is a critical difference between INSERT IGNORE and INSERT ... ON DUPLICATE KEY UPDATE.

If the table has no appropriate PRIMARY KEY or UNIQUE KEY, two rows with identical contents can still be inserted. MySQL does not automatically compare all columns to decide whether rows are duplicates.

### 2.2. Duplicate on Any Unique Key

If a table has multiple unique indexes, a row can conflict with any one of them. For example, if a table has unique keys on external_id and email, having just one of those two values already present can cause the new row to be skipped.

```sql
CREATE TABLE imported_accounts (
    account_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    external_id VARCHAR(40) NOT NULL,
    email VARCHAR(254) NOT NULL,
    PRIMARY KEY (account_id),
    UNIQUE KEY uk_external_id (external_id),
    UNIQUE KEY uk_email (email)
) ENGINE = InnoDB;
```

For imported data, clearly define which key determines whether a record already exists. A row with a new external_id whose email belongs to another account is not necessarily a duplicate that should be skipped from a business standpoint. INSERT IGNORE does not understand the business meaning of keys; it simply enforces unique constraints.

## 3. INSERT IGNORE Can Turn Bad Data into Warnings

This is the biggest risk when using IGNORE as a way to "make the batch succeed."

Suppose a table has an age column of type TINYINT UNSIGNED:

```sql
CREATE TABLE import_probe (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    source_key VARCHAR(40) NOT NULL,
    email VARCHAR(254) NOT NULL,
    age TINYINT UNSIGNED NOT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uk_source_key (source_key),
    UNIQUE KEY uk_email (email)
) ENGINE = InnoDB;
```

Insert multiple rows using INSERT IGNORE:

```sql
INSERT IGNORE INTO import_probe (source_key, email, age)
VALUES
    ('src-001', 'linh@example.com', 30),
    ('src-002', 'linh@example.com', 28),
    ('src-003', 'mai@example.com', 300),
    ('src-004', 'not-an-email', 22);

SHOW WARNINGS;
```

Notable outcomes:

- Row src-001 is inserted if it does not already exist.
- Row src-002 conflicts on the unique email with src-001 and is skipped; the name or other columns of the existing row are not updated.
- age = 300 exceeds the TINYINT UNSIGNED range (0 to 255). When numeric conversion errors are downgraded to warnings by IGNORE, the value may be clamped to the boundary 255 and the row is still inserted.
- not-an-email is still a valid string for VARCHAR. Without a schema constraint or email validation rule, MySQL does not recognize it as a malformed email.

This example highlights two distinct issues: one row can be skipped due to a duplicate, while another row is still inserted after its value is altered. A warning does not mean every row producing a warning was excluded from the table.

Exact behavior for invalid values also depends on column type, SQL mode, constraints, storage engine, and version. Test on the actual target environment, especially with dates/times, ENUMs, overly long strings, negative numbers in UNSIGNED columns, and CHECK constraints.

## 4. Relationship Between INSERT IGNORE and Strict SQL Mode

Strict SQL mode is designed to reject many invalid values rather than silently coercing them. Two common modes:

- STRICT_TRANS_TABLES: strict behavior for transactional tables, with specific rules for non-transactional tables.
- STRICT_ALL_TABLES: broader strict behavior across all storage engines.

Check the server and session SQL mode:

```sql
SELECT
    @@GLOBAL.sql_mode AS global_sql_mode,
    @@SESSION.sql_mode AS session_sql_mode;
```

With strict mode enabled, a regular INSERT fails when data is truncated or out of range. When IGNORE is added, some data errors that would normally fail under strict mode can be downgraded to warnings, with values adjusted so the insert continues.

Example:

```sql
INSERT INTO import_probe (source_key, email, age)
VALUES ('src-005', 'hoa@example.com', 300);
```

In strict mode, this operation is normally rejected because age is out of range. If changed to INSERT IGNORE, MySQL may emit a warning and store an adjusted value.

Do not disable strict mode just to let a batch pass. Nor should you assume strict mode provides absolute data protection when a statement uses IGNORE. To guarantee valid data, validate before writing and inspect warnings afterward.

## 5. Reading Warnings Immediately After the Statement

After INSERT IGNORE, run SHOW WARNINGS immediately to view diagnostic information:

```sql
INSERT IGNORE INTO members (email, display_name)
VALUES
    ('an@example.com', 'Another An'),
    ('binh@example.com', 'Binh');

SHOW WARNINGS;
```

SHOW WARNINGS returns these columns:

| Column | Meaning |
|---|---|
| Level | Severity: Note, Warning, or Error |
| Code | MySQL error code |
| Message | Descriptive text |

Some common codes encountered during data import:

| Code | Common Situation |
|---:|---|
| 1062 | Duplicate entry for PRIMARY KEY or UNIQUE |
| 1264 | Numeric value out of range |
| 1265 | Data truncated |
| 1366 | Incorrect value or data type conversion error in certain contexts |

Actual codes and messages must be read from the server; do not rely solely on a hardcoded list to classify across all versions.

You can check the total warning count for the most recent statement:

```sql
SHOW COUNT(*) WARNINGS;
```

Or view a subset of the list:

```sql
SHOW WARNINGS LIMIT 100;
```

### 5.1. Read Warnings Before Running Another Statement

Call SHOW WARNINGS immediately after INSERT IGNORE. A subsequent statement can replace the diagnostics area of the previous statement, preventing you from reading the full details you need to inspect.

If a batch generates many warnings, the number of stored messages available for display may be capped by the max_error_count variable. Thus, the SHOW WARNINGS list may not contain every message when the volume is large. Check the setting:

```sql
SHOW VARIABLES LIKE 'max_error_count';
```

Do not treat the warning count as the number of skipped rows. One row can emit multiple warnings, and warnings can also come from rows that were inserted with adjusted values. Combine warnings with affected row counts and staging data to classify outcomes accurately.

## 6. Comparing INSERT IGNORE, ON DUPLICATE KEY UPDATE, and REPLACE

These three approaches serve different goals:

| Statement | On Duplicate Key | Modifies Existing Row? | Characteristics |
|---|---|---|---|
| INSERT IGNORE | Skips the conflicting row and emits a warning | No | Suitable when duplicates are acceptable and should be skipped |
| INSERT ... ON DUPLICATE KEY UPDATE | Runs the UPDATE branch | Yes | Suitable for upserts when existing rows must be updated |
| REPLACE | Deletes the conflicting row and inserts a new row per REPLACE semantics | Yes; may affect FKs/triggers and auto-increment | Not a simple form of UPDATE |

ON DUPLICATE KEY UPDATE example:

```sql
INSERT INTO members (email, display_name)
VALUES ('an@example.com', 'An Nguyen')
ON DUPLICATE KEY UPDATE
    display_name = VALUES(display_name);
```

The VALUES(column) syntax in the UPDATE clause has been deprecated in newer MySQL versions; in MySQL 8.0.19 and later, you can use a row alias according to the version's supported syntax. Verify the exact syntax for your deployment version.

REPLACE example:

```sql
REPLACE INTO members (member_id, email, display_name)
VALUES (1, 'an@example.com', 'An New');
```

REPLACE can delete the conflicting old row and then insert a new row. This can trigger side effects on foreign keys, triggers, audits, and auto-increment values. Do not use REPLACE merely to avoid duplicate errors.

## 7. INSERT IGNORE Is Not a Complete Update or Synchronization Mechanism

If a row already exists, INSERT IGNORE preserves the old data. Example:

```sql
INSERT IGNORE INTO members (email, display_name)
VALUES ('an@example.com', 'An Updated');
```

If the email already exists with display_name = 'An', the name will not change to An Updated. Applications must explicitly choose one of these policies:

- Insert only; duplicates represent already-processed records and are skipped.
- Update specific fields when the business key already exists.
- Reject if the same key has different content.
- Record the conflict for a human or business workflow to resolve.

Do not use INSERT IGNORE as a two-way data synchronization mechanism. It does not compare record versions, update timestamps, or authoritative data sources.

## 8. Errors You Should Not Expect IGNORE to Handle

IGNORE affects only certain errors during insertion. It is not a mechanism for catching all exceptions.

Cases such as syntax errors, missing tables, insufficient privileges, connection errors, deadlocks, or severe execution errors still require standard error handling. For foreign key, CHECK, and other constraint errors, do not infer behavior solely from the presence of IGNORE in the statement; consult version-specific documentation and test in a lab database.

In particular, IGNORE does not disable PRIMARY KEY, UNIQUE, NOT NULL, CHECK, or FOREIGN KEY constraints. Constraints remain part of data integrity; some violations may be downgraded to warnings or cause rows to be skipped per server rules, while other cases still raise errors.

Do not ignore SQLWarning at the application layer. A JDBC operation may return an affected row count without throwing SQLException even when data was adjusted or rows were discarded.

## 9. Using INSERT IGNORE in a Transaction

With InnoDB, rows successfully inserted in an INSERT IGNORE statement belong to the current transaction. Skipped rows create no records. Warnings do not automatically roll back the transaction.

Example:

```sql
START TRANSACTION;

INSERT IGNORE INTO members (email, display_name)
VALUES
    ('an@example.com', 'An'),
    ('binh@example.com', 'Binh'),
    ('an@example.com', 'Duplicate An');

SHOW WARNINGS;

-- The application or operator classifies warnings:
-- If only expected duplicates occurred, COMMIT.
-- If unexpected data warnings occurred, ROLLBACK.

COMMIT;
```

In this example, the decision to COMMIT or ROLLBACK is a conditional step in the application or operational procedure. SQL does not automatically roll back merely because warnings occurred.

If disallowed warnings are detected, you can roll back the entire write in the InnoDB transaction. Keep in mind that rolling back data does not reclaim allocated AUTO_INCREMENT values; ID gaps can still appear.

Do not rely on transactions to make non-transactional tables roll back. When atomicity is required, use InnoDB and verify the storage engine of the target table.

## 10. Safe Import Workflow with a Staging Table

A reliable batch import must separate valid data, acceptable duplicates, and rejected data. Do not feed raw data directly into business tables with INSERT IGNORE and treat statement success as completion.

Recommended workflow:

1. **Ingest data into staging.** Store source_row_id, source_key, and raw values; preserve traceability back to the source file or message.
2. **Validate structure.** Verify column count, data types, encoding, date formats, and required fields.
3. **Validate business rules.** Check numeric ranges, lengths, formats, referential relationships, and domain rules.
4. **Classify records.** Tag statuses such as VALID, DUPLICATE, INVALID, or NEEDS_REVIEW along with specific reasons.
5. **Transfer only valid data.** Use regular INSERT when duplicates are unexpected; use INSERT IGNORE if duplicates by source key are explicitly permitted.
6. **Read warnings.** Distinguish duplicate key warnings from conversion warnings; unexpected warnings must fail the batch or route to a remediation workflow.
7. **Reconcile counts.** Compare total source rows against inserted valid rows, accepted duplicates, rejected invalid rows, and rows needing review.
8. **Store audit records.** Log batch_id, source, timestamp, row counts, warnings, outcome, and rejection reasons.
9. **Controlled commit.** Commit only when quality checks and reconciliation pass.

Example staging table holding raw data:

```sql
CREATE TABLE member_import_stage (
    batch_id BIGINT NOT NULL,
    source_row_id BIGINT NOT NULL,
    source_key VARCHAR(80) NULL,
    email_raw TEXT NULL,
    age_raw VARCHAR(40) NULL,
    validation_status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    reject_reason VARCHAR(255) NULL,
    PRIMARY KEY (batch_id, source_row_id)
) ENGINE = InnoDB;
```

After validating via the application or appropriate queries, move VALID rows to the target table. Do not cast raw strings without prior validation; if conversion fails, data may be truncated or altered depending on SQL mode.

Example transferring rows marked as valid:

```sql
INSERT INTO members (email, display_name)
SELECT
    s.email_raw,
    s.source_key
FROM member_import_stage AS s
WHERE s.batch_id = 20261119
  AND s.validation_status = 'VALID';
```

If the workflow allows the same source_key to be resent, design a unique key on the source identifier and use INSERT IGNORE intentionally. Always inspect warnings after every batch.

## 11. Duplicate Reconciliation and Idempotency

Idempotent imports mean re-running the same batch does not create unintended business records. A more reliable approach is to use a stable source key and a unique constraint:

```sql
ALTER TABLE members
    ADD COLUMN source_system VARCHAR(40) NOT NULL,
    ADD COLUMN source_member_id VARCHAR(80) NOT NULL,
    ADD UNIQUE KEY uk_member_source (
        source_system,
        source_member_id
    );
```

A real-world design must address legacy data, nullability, and the possibility of source ID reuse before adding the constraint.

Once in place, INSERT IGNORE can skip records already imported from the same source. However, distinguish two cases:

- Same source_system and source_member_id with identical content: likely a valid replay.
- Same source key but different email or business data: likely an update conflict requiring version-based or sync-policy handling.

A unique key guarantees only key uniqueness. It does not prove the remaining columns match or that the data is newer. To sync updates, you need a version, reliable updated_at, or conflict-resolution rules.

Avoid relying solely on a pre-INSERT SELECT to detect duplicates:

```sql
SELECT 1
FROM members
WHERE email = 'an@example.com';
```

Between SELECT and INSERT, another transaction can insert the same email. That is a race condition. A UNIQUE constraint is the final database safeguard. You can use INSERT IGNORE to handle expected duplicates, but you must read warnings to know what occurred.

## 12. Monitoring Results in Java/JDBC

JDBC can return an affected row count without throwing SQLException when INSERT IGNORE encounters duplicates or errors downgraded to warnings. Therefore, calling executeUpdate() alone and ignoring warnings is insufficient.

Example:

```java
String sql = """
    INSERT IGNORE INTO members (email, display_name)
    VALUES (?, ?)
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setString(1, email);
    ps.setString(2, displayName);

    int affectedRows = ps.executeUpdate();

    SQLWarning warning = ps.getWarnings();
    while (warning != null) {
        System.err.printf(
            "MySQL warning: code=%d, state=%s, message=%s%n",
            warning.getErrorCode(),
            warning.getSQLState(),
            warning.getMessage()
        );
        warning = warning.getNextWarning();
    }

    ps.clearWarnings();

    System.out.println("Affected rows: " + affectedRows);
}
```

This snippet assumes the required JDBC types from java.sql are imported. With batch inserts, the driver may return update count arrays and warnings differently depending on Connector/J settings and version; test diagnostic retrieval on the exact driver deployed.

In production applications:

- Log warnings with batch ID, source row ID if available, and error code.
- Separate accepted warnings (such as source-key duplicates) from data warnings (truncation, out-of-range, conversion).
- Do not log personal or sensitive data beyond data-protection policies.
- If a warning is outside the allowlist, mark the batch as failed and roll back the transaction when possible.
- Reconcile inserted row counts against classified source row counts.

## 13. Counting Rows and Interpreting Results Properly

Do not conflate the following metrics:

| Metric | What It Indicates |
|---|---|
| Source row count | How many records were submitted to the batch |
| Affected rows | How many rows MySQL reports as affected per statement and driver semantics |
| Warning count | How many warning/note/error diagnostics were recorded for the statement |
| Actual rows in table | Data state after the operation |
| Duplicate row count | Must be classified by key and source, not simply inferred from warning count |

A single INSERT IGNORE statement can insert some rows, skip some duplicate rows, and insert other rows with adjusted values. Therefore, the formula "source count minus affected rows equals duplicates" is unreliable whenever a batch has conversion warnings or multiple error types.

If row-level accuracy is required, attach source_row_id in staging and track processing status per row. Aggregate statement warnings are not a complete audit table.

## 14. When to Use and When Not to Use INSERT IGNORE

| Situation | Recommendation |
|---|---|
| Re-receiving already-processed messages where a unique source key enforces idempotency | Can be used if duplicates are expected and warnings are monitored |
| Importing lists where duplicate emails may be skipped under a clear rule | Can be used, provided skipped counts are logged and reconciled |
| Data might contain overly long strings or out-of-range numbers | Do not use IGNORE to "auto-fix"; validate and reject upfront |
| Date/time data with uncertain formatting | Normalize and validate before writing |
| Sync requiring updates to existing rows | Use upsert with a version or timestamp update policy |
| Need to guarantee every row inserts successfully | Use regular INSERT in a transaction with explicit error handling |
| No unique key exists to identify duplicates | Design the business key first; IGNORE does not detect duplicates on its own |

## 15. Common Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Thinking IGNORE only skips duplicates | Bad values can be truncated or coerced and still inserted | Read all warnings and validate upfront |
| Thinking no thrown error means all rows are valid | Some rows may be skipped or altered | Reconcile source, affected rows, and staging |
| Using IGNORE to bypass strict mode | Invalid data can enter the table | Keep strict mode and validate before writing |
| Expecting automatic deduplication without a unique key | Identical rows still get inserted | Create a unique constraint on the business key |
| Using IGNORE to update existing data | Existing rows are not updated | Use ON DUPLICATE KEY UPDATE or a sync workflow |
| Reading only warning count | You do not know which warning types occurred | Read Level, Code, and Message |
| Running another statement before SHOW WARNINGS | Needed diagnostics are lost | Read warnings immediately after the statement |
| Assuming warning count equals skipped rows | One row may emit multiple warnings or still be inserted | Use staging for row-level reconciliation |
| Using REPLACE as an UPDATE | Existing rows may be deleted and re-inserted | Choose statements by semantics and check FKs/triggers |

## 16. Operational Checklist for INSERT IGNORE Batches

Before running:

- Identify which PRIMARY KEY or UNIQUE key defines duplicates.
- Define which duplicates are acceptable and which are business conflicts.
- Check SQL mode, column types, nullability, defaults, and constraints.
- Validate formats, lengths, numeric ranges, and dates/times before writing.
- Test on staging or a representative small batch.
- Prepare warning extraction in your SQL client or JDBC layer.

After running:

- Read SHOW WARNINGS immediately after the statement.
- Separate duplicate warnings from data warnings.
- Check affected rows and total batch row count.
- Reconcile skipped, rejected, and inserted rows.
- Roll back the transaction if any disallowed warning occurs.
- Save audit logs and batch metadata for safe investigation or replay.

## 17. Key Takeaways

- INSERT IGNORE downgrades certain insert errors to warnings and lets the statement continue.
- Duplicate PRIMARY KEY/UNIQUE keys normally skip the conflicting row; existing row data is not updated.
- Certain conversion errors can truncate or clamp values and still insert the row.
- IGNORE does not ignore all errors and does not disable data constraints.
- Strict SQL mode remains important; IGNORE can alter handling of errors that strict mode would otherwise reject.
- Read SHOW WARNINGS immediately after the statement; inspect Level, Code, and Message.
- Warning count does not equal skipped row count and does not fully identify which rows were altered.
- Use stable unique keys for idempotent imports; do not rely on SELECT before INSERT due to race conditions.
- Use staging tables to validate, classify, reject, and reconcile by source row.
- In Java/JDBC, inspect the SQLWarning chain after executeUpdate or batch execution.
- Allow only predefined warnings; unexpected data warnings must be treated as data-quality failures.

INSERT IGNORE is a useful tool when duplicate skipping is clearly defined. Pair it with strict mode, constraints, warning diagnostics, and row-level reconciliation so batch imports can retry safely without silently degrading data quality.
