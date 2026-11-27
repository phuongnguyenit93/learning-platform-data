# Batch Loading, Controlled Bad-Row Skipping, and Reading Warnings

Loading large volumes of data into MySQL requires balancing speed, data quality, and safe re-runnability. `LOAD DATA INFILE` is typically an efficient choice for loading structured text files such as CSV or TSV. However, a load command can encounter malformed data, values exceeding column limits, duplicate keys, or type conversion errors. Simply adding `IGNORE` to keep the command running can cause skipped records to go unnoticed until applications report incorrect numbers.

A reliable workflow preserves the original file, loads into a staging area, inspects warnings immediately after the load statement, classifies invalid rows, quarantines bad rows, and promotes valid data into business tables only after reconciliation. Each batch needs a unique identifier, expected row count, and processing status so it can be investigated or re-run without duplicating data.

## 1. Choosing a Batch Loading Method

MySQL offers several common loading methods:

| Method | Best Suited When | Considerations |
|---|---|---|
| `LOAD DATA INFILE` | Loading a file on the MySQL server or a filesystem readable by the server | Requires `FILE` privilege, `secure_file_priv` control, and a server-visible path |
| `LOAD DATA LOCAL INFILE` | File resides on the client machine or import application host | Client streams the file over the connection; requires `local_infile` on server and client, file source control, and TLS over networks |
| Multi-row `INSERT` | Small batches, data already validated or generated directly by the app | Easy to integrate with app logic; must bound statement size and round trips |
| ETL/CDC tools | Multiple data sources, complex mappings, checkpointing, or multi-step transformations | Requires operating pipelines, error tracking, and ordering management |

For large files, `LOAD DATA` is usually faster than sending individual `INSERT` statements because it reduces communication and statement-parsing overhead. Yet speed is not the sole criterion: source format, data quality, recoverability, key constraints, and impact on active workloads must all be evaluated.

## 2. Preparing the File and Target Structure

Before loading, agree on a file contract with the exporting system:

- Encoding, typically `utf8mb4`, and BOM handling.
- Column delimiter, string enclosure, escape character, and line terminator.
- Representation rules for `NULL`, empty strings, datetimes, decimals, and thousands separators.
- Presence of a header; stability of column order and names.
- Rules for quotes, embedded newlines inside text fields, and `LF` vs. `CRLF` line endings.
- Identifying keys for duplicate detection and a source line identifier for tracing bad records.

Do not guess formatting from the first few lines. Test edge cases as well: strings with commas, quotes, embedded newlines, Vietnamese diacritics, empty values, invalid dates, and high-precision decimals.

Example CSV file:

```csv
source_line_no,order_id,customer_id,amount,order_date
1,10001,501,125000.00,2026-11-18
2,10002,502,89000.50,2026-11-18
3,10003,503,invalid,2026-11-18
```

`source_line_no` is added by the exporting system to identify the original line when quarantining or requesting retransmission. If the source does not supply a line number, generate a stable identifier in a preprocessing step; do not rely on physical line counts because a CSV record can contain newlines inside quoted fields.

Define the target table with appropriate data types and constraints:

```sql
CREATE TABLE orders (
  order_id BIGINT UNSIGNED NOT NULL,
  customer_id BIGINT UNSIGNED NOT NULL,
  amount DECIMAL(14,2) NOT NULL,
  order_date DATE NOT NULL,
  PRIMARY KEY (order_id),
  KEY idx_orders_customer_date (customer_id, order_date)
) ENGINE=InnoDB;
```

`DECIMAL` suits monetary amounts requiring exact decimal precision. Use date/time types matching the data semantics, avoiding storing dates as strings merely to make imports easier. Primary key and unique index constraints serve as the last line of defense against duplicate data, even if application validation has bugs.

## 3. LOAD DATA INFILE and LOAD DATA LOCAL INFILE

### File Located on the MySQL Server

Example:

```sql
LOAD DATA INFILE '/var/lib/mysql-files/orders.csv'
INTO TABLE orders
CHARACTER SET utf8mb4
FIELDS TERMINATED BY ','
OPTIONALLY ENCLOSED BY '"'
ESCAPED BY '\\'
LINES TERMINATED BY '\n'
IGNORE 1 LINES
(@source_line_no, order_id, customer_id, amount, order_date);
```

In this example, the file must exist at a path readable by the MySQL process. The executing account needs the `FILE` privilege as required by the version, and the directory may be restricted by `secure_file_priv`. Check configuration:

```sql
SHOW VARIABLES LIKE 'secure_file_priv';
```

If `secure_file_priv` returns a path, server-side import/export operations are generally restricted to that directory. If the value is `NULL`, server-side file operations are disabled; an empty value means no directory restriction is imposed by this variable. Follow your environment's security policy and do not relax paths just to import a single file.

### File Located on the Client Machine

Example:

```sql
LOAD DATA LOCAL INFILE '/secure/import/orders.csv'
INTO TABLE orders
CHARACTER SET utf8mb4
FIELDS TERMINATED BY ','
OPTIONALLY ENCLOSED BY '"'
ESCAPED BY '\\'
LINES TERMINATED BY '\n'
IGNORE 1 LINES
(@source_line_no, order_id, customer_id, amount, order_date);
```

With `LOCAL`, the path is read by the client program and file contents are streamed to the server. Both server and client must permit this feature; inspect the `local_infile` variable and driver/client support flags. Enable it only for trusted applications and environments. Because a server can request local files from the client during a connection, use trusted clients/drivers, restrict permissions, and protect connections with TLS over networks.

`LOCAL` has a crucial difference in error handling: MySQL handles data interpretation and duplicate-key errors similarly to `IGNORE`, so bad rows may turn into warnings while the statement keeps running. Do not assume `LOCAL` and non-`LOCAL` behave identically when strict SQL mode is enabled. Test with the exact version, driver, `sql_mode`, and real data.

### Column Mapping and Transformation

The file does not need to match the table's column order. You can load into user variables and transform via `SET`:

```sql
LOAD DATA LOCAL INFILE '/secure/import/orders.csv'
INTO TABLE orders
CHARACTER SET utf8mb4
FIELDS TERMINATED BY ','
OPTIONALLY ENCLOSED BY '"'
ESCAPED BY '\\'
LINES TERMINATED BY '\n'
IGNORE 1 LINES
(@line_no, @order_id, @customer_id, @amount, @order_date)
SET
  order_id = NULLIF(@order_id, ''),
  customer_id = NULLIF(@customer_id, ''),
  amount = NULLIF(@amount, ''),
  order_date = STR_TO_DATE(@order_date, '%Y-%m-%d');
```

This example illustrates mapping and transformation; if the target table declares `NOT NULL`, empty values converted to `NULL` will be rejected or generate warnings depending on SQL mode and context. For workflows needing row-level error control, load raw values into string columns in staging first, then validate and cast types. That way, original data is never lost when conversion fails.

## 4. Loading into Staging Instead of Directly into Business Tables

Staging is a landing zone for raw data. Source columns are stored in sufficiently wide string fields alongside a batch ID and source line identifier. After loading, you can validate formatting, detect duplicates, classify errors, and promote only valid data into business tables.

Example:

```sql
CREATE TABLE import_stage_orders (
  batch_id BIGINT UNSIGNED NOT NULL,
  source_line_no VARCHAR(32) NOT NULL,
  order_id_raw VARCHAR(64),
  customer_id_raw VARCHAR(64),
  amount_raw VARCHAR(64),
  order_date_raw VARCHAR(64),
  loaded_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (batch_id, source_line_no)
) ENGINE=InnoDB;
```

Load raw data:

```sql
LOAD DATA LOCAL INFILE '/secure/import/orders.csv'
INTO TABLE import_stage_orders
CHARACTER SET utf8mb4
FIELDS TERMINATED BY ','
OPTIONALLY ENCLOSED BY '"'
ESCAPED BY '\\'
LINES TERMINATED BY '\n'
IGNORE 1 LINES
(@line_no, @order_id, @customer_id, @amount, @order_date)
SET
  batch_id = 2026111901,
  source_line_no = @line_no,
  order_id_raw = @order_id,
  customer_id_raw = @customer_id,
  amount_raw = @amount,
  order_date_raw = @order_date;
```

The batch ID is illustrative. In real systems, generate a unique ID for each received file and record metadata such as filename, checksum, receipt timestamp, sender, expected row count, and status. The key `(batch_id, source_line_no)` prevents loading the same line twice if the source provides stable line numbers.

Staging distinguishes three states:

- **Loaded:** the row has been received into staging, not yet validated.
- **Accepted:** the row passed validation and was promoted into the target table.
- **Rejected:** the row is invalid or violates business rules, retained with the rejection reason.

Do not delete source files or staging data right after `LOAD DATA` returns success. Transition the batch to completed only after reconciling row counts, reviewing warnings, and verifying target data.

## 5. Controlled Skipping of Bad Rows

MySQL can keep loading when `IGNORE` is used in supported situations, but `IGNORE` is not a quarantine system. It does not automatically retain the full content of skipped rows along with reasons for operations teams to resolve later.

Common error categories:

| Error Type | Example | Recommended Handling |
|---|---|---|
| Invalid data type | `amount=abc`, malformed date | Load raw into staging; validate syntax before `CAST`/`STR_TO_DATE` |
| Out of bounds | String longer than `VARCHAR`, number exceeding `DECIMAL` precision | Verify source contract limits; reject or fix mapping in a controlled way |
| Missing required value | `order_id` empty or `NULL` | Reject with clear reason; do not default to 0 |
| Duplicate key | `order_id` already exists | Choose skip, update, or reject rule per business policy |
| Out-of-domain value | Negative `amount`, status outside allowed list | Enforce business rules in staging |
| Invalid relationship | `customer_id` does not exist | Verify references before insert; store rejections for source remediation |

Create a quarantine table for rejected rows:

```sql
CREATE TABLE import_rejected_orders (
  batch_id BIGINT UNSIGNED NOT NULL,
  source_line_no VARCHAR(32) NOT NULL,
  order_id_raw VARCHAR(64),
  customer_id_raw VARCHAR(64),
  amount_raw VARCHAR(64),
  order_date_raw VARCHAR(64),
  reject_reason VARCHAR(255) NOT NULL,
  rejected_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (batch_id, source_line_no)
) ENGINE=InnoDB;
```

Example of classifying syntax errors:

```sql
INSERT INTO import_rejected_orders (
  batch_id, source_line_no, order_id_raw,
  customer_id_raw, amount_raw, order_date_raw, reject_reason
)
SELECT
  batch_id,
  source_line_no,
  order_id_raw,
  customer_id_raw,
  amount_raw,
  order_date_raw,
  CASE
    WHEN order_id_raw IS NULL OR order_id_raw NOT REGEXP '^[0-9]+$'
      THEN 'order_id is not a positive integer'
    WHEN customer_id_raw IS NULL OR customer_id_raw NOT REGEXP '^[0-9]+$'
      THEN 'customer_id is not a positive integer'
    WHEN amount_raw IS NULL OR amount_raw NOT REGEXP '^[0-9]+([.][0-9]{1,2})?$'
      THEN 'amount has invalid decimal format'
    WHEN order_date_raw IS NULL OR order_date_raw NOT REGEXP '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'
      THEN 'order_date does not match YYYY-MM-DD'
    ELSE 'Invalid'
  END
FROM import_stage_orders
WHERE batch_id = 2026111901
  AND (
    order_id_raw IS NULL OR order_id_raw NOT REGEXP '^[0-9]+$'
    OR customer_id_raw IS NULL OR customer_id_raw NOT REGEXP '^[0-9]+$'
    OR amount_raw IS NULL OR amount_raw NOT REGEXP '^[0-9]+([.][0-9]{1,2})?$'
    OR order_date_raw IS NULL OR order_date_raw NOT REGEXP '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'
  );
```

Regex checks only string shape. It does not prove a date exists on the calendar, a number fits the target type range, or a customer exists. For instance, `2026-02-31` matches the pattern yet is not a valid calendar date. Add type conversion, range, and referential checks before inserting into business tables.

One way to check amounts and dates before inserting:

```sql
SELECT
  source_line_no,
  amount_raw,
  order_date_raw,
  STR_TO_DATE(order_date_raw, '%Y-%m-%d') AS parsed_order_date
FROM import_stage_orders
WHERE batch_id = 2026111901;
```

Check for `NULL` in `parsed_order_date`, verify normalized formatting, and apply business bounds. For datetime values with timezones, normalize timezones per source contract before writing into `DATETIME` or `TIMESTAMP`.

After isolating syntax errors, promote valid rows to the target table:

```sql
INSERT INTO orders (order_id, customer_id, amount, order_date)
SELECT
  CAST(s.order_id_raw AS UNSIGNED),
  CAST(s.customer_id_raw AS UNSIGNED),
  CAST(s.amount_raw AS DECIMAL(14,2)),
  STR_TO_DATE(s.order_date_raw, '%Y-%m-%d')
FROM import_stage_orders AS s
WHERE s.batch_id = 2026111901
  AND s.order_id_raw REGEXP '^[0-9]+$'
  AND s.customer_id_raw REGEXP '^[0-9]+$'
  AND s.amount_raw REGEXP '^[0-9]+([.][0-9]{1,2})?$'
  AND s.order_date_raw REGEXP '^[0-9]{4}-[0-9]{2}-[0-9]{2}$';
```

This step is illustrative. In production, add actual calendar-date validation, target type bounds, customer existence, duplicate checks, and business rules. Ideally, build a fully validated `accepted` set before inserting so the exact same filter drives both row-count reporting and the insert itself.

## 6. Reading Warnings Immediately After the Load Statement

After `LOAD DATA`, MySQL returns summary counts such as records read, rows replaced, rows skipped, and warnings. Do not check only the exit code or `Query OK` message.

Immediately after the load command, run:

```sql
SHOW COUNT(*) WARNINGS;
SHOW WARNINGS LIMIT 100;
```

`SHOW WARNINGS` displays conditions from the most recent statement that produced diagnostics, including level (`Warning`, `Error`, `Note`), error code, and message. Collect the output right after the import statement to tie warnings to the exact batch. Do not run another import or statement that could overwrite the diagnostics area before collecting them.

`max_error_count` limits how many conditions are stored for display in the diagnostics area; it does not limit the actual total number of errors a statement may encounter. If warnings exceed that limit, `SHOW WARNINGS` displays only a subset. You can inspect and adjust it in the session before importing:

```sql
SHOW VARIABLES LIKE 'max_error_count';
SET SESSION max_error_count = 1000;
```

Choose a limit suited to batch size and available resources. Do not set it arbitrarily huge because storing many diagnostics consumes memory. For very large files, staging and batch validation avoid relying on a potentially truncated warning list.

Common warning examples:

| Code / Message Type | Common Cause | Resolution |
|---|---|---|
| Data truncated | Value cut off or incomplete conversion | Check column length, precision, charset, and source data |
| Incorrect date value | Date string cannot be parsed into target format | Normalize format, verify calendar validity and timezone |
| Duplicate entry | Primary key or unique index collision | Enforce business rule for duplicates; never ignore silently by default |
| Invalid integer/decimal | Invalid characters or out-of-range value | Inspect raw value and reject malformed row |
| Column count mismatch | File field count does not match mapping | Check delimiter, enclosure, escape, and header |

Warnings are evidence requiring investigation. A batch can load most rows yet still be wrong from a business standpoint. Record warning count, sample warnings, rows read, accepted rows, and rejected rows in batch metadata.

## 7. Distinguishing IGNORE, REPLACE, and Handling Duplicates

`IGNORE` and `REPLACE` affect how MySQL handles certain errors and key conflicts during `LOAD DATA`:

- `IGNORE` can skip duplicate-key rows and continue processing other rows; data interpretation errors in supported cases may become warnings.
- `REPLACE` replaces conflicting rows with the new row. Behaviorally, it may delete the old row and insert the new one, affecting triggers, foreign keys, and columns omitted from the file.
- Do not use modifiers as substitutes for business rules. If incoming data should update only specific columns on existing records, explicitly define an upsert operation and the updatable columns.

Example load with `IGNORE`:

```sql
LOAD DATA LOCAL INFILE '/secure/import/orders.csv'
IGNORE INTO TABLE orders
CHARACTER SET utf8mb4
FIELDS TERMINATED BY ','
OPTIONALLY ENCLOSED BY '"'
LINES TERMINATED BY '\n'
IGNORE 1 LINES
(order_id, customer_id, amount, order_date);
```

In this example, `IGNORE` after `LOCAL INFILE` is the error/duplicate-handling modifier; `IGNORE 1 LINES` at the end skips the header row. These two uses of `IGNORE` serve completely different purposes.

If duplicates must be skipped, measure skipped row counts and reconcile against existing keys. If existing records must be updated, consider loading into staging and using `INSERT ... ON DUPLICATE KEY UPDATE` with an explicit column list. If duplicates represent source errors, route them into the reject table and request a corrected file. Do not use `REPLACE` without evaluating the impact of deleting and reinserting records.

## 8. Strict SQL Mode and Error Behavior

Strict SQL mode affects how MySQL handles invalid or missing values during write operations. Check the active mode:

```sql
SELECT @@SESSION.sql_mode;
SELECT @@GLOBAL.sql_mode;
```

Modes such as `STRICT_TRANS_TABLES` and `STRICT_ALL_TABLES` govern invalid, missing, or out-of-range conversions. Exact behavior depends on storage engine, statement, and whether `LOCAL`, `IGNORE`, or `REPLACE` is used. Never disable strict mode in production just to let an import pass. That can turn data errors into defaults or truncated values without appropriate business handling.

A safe workflow tests both valid and faulty sample files on the exact production MySQL version, driver, and `sql_mode`. Record outcomes for both: whether the command aborts or continues, whether transactions roll back, which warnings appear, and how many rows were written. To guarantee a batch publishes only when all checks succeed, perform the promotion from staging to target tables inside a controlled InnoDB transaction and update batch status in that same transaction.

Do not assume `LOAD DATA LOCAL INFILE` shares the exact error semantics of server-side `LOAD DATA INFILE`. `LOCAL` behaves similarly to `IGNORE` for certain input and duplicate-key errors. This is why raw staging and warning inspection are so valuable: data is captured first, and then you explicitly decide which rows are accepted.

## 9. Batch Splitting, Transactions, and Safe Re-Runs

A very large file can increase resource hold times, undo/redo volume, replication lag, and rollback duration. Split files into batches along complete record boundaries to:

- Bound staging storage and redo generated per run.
- Maintain checkpoints per batch and know exactly which batches succeeded.
- Retry a failed batch without reloading the entire dataset.
- Reduce reconciliation and bad-row isolation times.
- Pace load throughput according to production and replica load.

Each batch should carry metadata:

| Field | Purpose |
|---|---|
| `batch_id` | Unique identifier for the load run |
| `source_file` | Original filename or identifier |
| `source_checksum` | Detects file modification across retries |
| `expected_rows` | Expected data row count, excluding header |
| `loaded_rows` | Rows ingested into staging |
| `accepted_rows` | Rows promoted to target table |
| `rejected_rows` | Quarantined rows |
| `warning_count` | Total warnings captured from the load command |
| `status` | `RECEIVED`, `LOADED`, `VALIDATED`, `PUBLISHED`, `FAILED` |

Design idempotent operations: resubmitting the same batch must not create duplicate records or wrong updates. Use batch/source-line keys, business unique keys, checkpoint tables, and publishing transactions. Never mark a batch `PUBLISHED` before target data and reconciliation metrics are committed.

Example processing model:

```text
Receive file + checksum
        |
        v
Create batch_id / RECEIVED status
        |
        v
LOAD DATA into staging
        |
        v
Collect warnings + row counts
        |
        v
Validate and classify
      /   \
     v     v
 Reject  Accepted
   |       |
   |       v
   |   Publish to target table
   |       |
   +---+---+
       v
  Reconcile batch
       |
       v
  PUBLISHED / FAILED
```

If publishing spans multiple operations across InnoDB tables, consider wrapping them in a transaction so business data and batch status commit together. For very large batches, publish in smaller chunks, each with its own checkpoint and idempotency key. Ensure consumers never read partially published batch state.

## 10. Post-Import Reconciliation

Do not declare success simply because the command returned no error. Compare the numbers:

```text
expected_rows
  = loaded_rows + rows_rejected_before_staging (if any)

loaded_rows
  = accepted_rows + rejected_rows + rows_pending_review
```

These equations form the batch control model; clearly account for headers, blank lines, skipped duplicates, and unparseable file lines to avoid double counting.

Check row count in staging:

```sql
SELECT COUNT(*) AS loaded_rows
FROM import_stage_orders
WHERE batch_id = 2026111901;
```

Check rejected row count:

```sql
SELECT COUNT(*) AS rejected_rows
FROM import_rejected_orders
WHERE batch_id = 2026111901;
```

Check duplicate keys in staging:

```sql
SELECT order_id_raw, COUNT(*) AS occurrences
FROM import_stage_orders
WHERE batch_id = 2026111901
GROUP BY order_id_raw
HAVING COUNT(*) > 1;
```

Check records referencing missing parents:

```sql
SELECT s.source_line_no, s.customer_id_raw
FROM import_stage_orders AS s
LEFT JOIN customers AS c
  ON c.customer_id = CAST(s.customer_id_raw AS UNSIGNED)
WHERE s.batch_id = 2026111901
  AND s.customer_id_raw REGEXP '^[0-9]+$'
  AND c.customer_id IS NULL;
```

Reconciliation queries must run over type-checked rows to avoid casting invalid strings. Beyond row counts, reconcile total amounts, min/max dates, distinct key counts, and sample records. For critical datasets, compute chunked checksums or hashes and compare against the source.

## 11. Security During Import

Import files may contain personal data, payment details, or sensitive business records. Apply these controls:

- Restrict the import account to reading only necessary files; avoid granting `FILE` broadly.
- Restrict server-side directories via `secure_file_priv` and filesystem permissions.
- Enable `local_infile` only for trusted clients/applications; disable when no longer needed.
- Use TLS when sending files over the network and verify server identity on the client.
- Encrypt source files, staging tables, reject tables, and backups according to data classification.
- Avoid writing full sensitive row contents into warning logs, tickets, or application logs unnecessarily.
- Establish retention and secure deletion for source files, decrypted files, staging, and reject tables after expiry.
- Audit who triggered the import, file source, checksum, timestamp, row counts, and outcome.

Never allow arbitrary clients to enable `LOCAL` freely on a shared server. This feature enables a server to request files from the client during a session; restrict it by driver, account, and connection origin.

## 12. Common Troubleshooting

| Symptom | Possible Cause | Inspection and Resolution |
|---|---|---|
| `LOAD DATA INFILE` cannot open file | Server-invisible path, filesystem permissions, or `secure_file_priv` | Verify path on the MySQL host, read permissions, and `secure_file_priv` value |
| `LOCAL INFILE` rejected | Server or client disables `local_infile`, or driver blocks it | Check server variable, client/driver flags, and connection policy |
| Shifted column data | Wrong delimiter, enclosure, escape, or embedded newline | Inspect file format, declare `FIELDS`/`LINES` explicitly, and test on a sample |
| Corrupted Vietnamese characters | Source charset mismatch or BOM | Identify actual encoding, specify `CHARACTER SET`, and handle BOM cleanly |
| Dates or numbers parsed wrongly | Inconsistent format, locale, or decimal separator | Load raw into staging, normalize, then cast types |
| Many rows skipped despite command success | Duplicates, `IGNORE`, `LOCAL`, or conversion errors becoming warnings | Read `SHOW WARNINGS`, compare `Records/Skipped/Warnings`, and quarantine bad rows |
| `SHOW WARNINGS` missing rows | Exceeded `max_error_count` | Check total warnings, raise session limit appropriately, or split into smaller batches |
| Retry creates duplicates | Non-idempotent batch or missing unique key/checkpoint | Use batch ID, source row ID, checksum, and clear upsert rules |
| Import slows down replicas | Large batch, heavy indexes, rapid redo/binlog growth | Split batches, throttle rate, monitor applier and I/O load |

When an import fails, preserve the original file, batch metadata, summary output, and warnings. Do not immediately re-run with `IGNORE` or `REPLACE` without knowing how many rows were written. Inspect staging and target table state, determine whether the prior operation rolled back or partially committed, and only then decide whether to resume, truncate staging for the batch, or start a new batch.

## 13. Practical Scenario

An e-commerce platform receives a daily order file from a partner. The file has 500,000 rows, some of which may contain invalid dates, amounts, or customer IDs. The requirement is to load valid rows, retain invalid rows for the partner to fix, and prevent duplicate orders if the file is resent.

**Step 1 — Receive the file.** Store the file in a controlled landing zone, compute its checksum, count data rows, record the filename, and generate a `batch_id`. Preserve the original file for investigation.

**Step 2 — Load raw.** Use `LOAD DATA LOCAL INFILE` to ingest fields into staging as strings. Read warnings right after the statement and store metrics with batch metadata.

**Step 3 — Validate.** Validate ID format, amount, date, customer existence, in-file duplicates, and duplicates against the target table. Write invalid rows to `import_rejected_orders` with `reject_reason`.

**Step 4 — Publish.** Move valid rows into `orders` in a transaction or checkpointed chunks. A unique key on `order_id` guards against duplicates; duplicate policy is governed explicitly by the partner contract.

**Step 5 — Reconcile.** Confirm `loaded = accepted + rejected + pending_review`, compare total amount and daily order counts with the source file, and update the batch status to `PUBLISHED`.

**Step 6 — Error feedback.** Export rejected rows with source line numbers and clear reasons for the partner to fix. When receiving a corrected file, create a new batch linked to the prior batch and reload only the rows targeted for correction.

## 14. Pre-Production Import Checklist

- [ ] Verified file format, encoding, delimiter, enclosure, escape, and line ending.
- [ ] Tested edge cases: strings with commas, quotes, embedded newlines, `NULL`, and empty values.
- [ ] Selected `INFILE` or `LOCAL INFILE` according to file location and security policy.
- [ ] Verified `FILE` privilege, `secure_file_priv`, `local_infile`, and filesystem permissions.
- [ ] Tested staging load using the exact production MySQL version, driver, and `sql_mode`.
- [ ] Read `SHOW WARNINGS` immediately after import and noted the `max_error_count` limit.
- [ ] Configured batch ID, checksum, expected row count, and checkpoint for safe retries.
- [ ] Quarantined invalid rows with original content and rejection reasons.
- [ ] Defined explicit duplicate policy: reject, skip, or controlled update.
- [ ] Reconciled row counts, unique keys, total amounts, and business rules.
- [ ] Evaluated redo/binlog, index, locking, and replication lag impact for large batches.
- [ ] Secured source files, staging, reject tables, and intermediate SQL files with retention policies.

Safe batch loading does not end at pushing a file into MySQL. The system must prove which rows were received, which were valid, which were rejected, and why. Combining `LOAD DATA`, staging, diagnostics, reject tables, batch IDs, and reconciliation delivers a workflow that is both fast and auditable, re-runnable, and quality-controlled.
