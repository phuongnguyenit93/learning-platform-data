# Bulk Data Loading, Separating Error Rows, and Reconciling Results

Loading thousands or millions of records into Oracle Database is more than running a fast `INSERT` statement. A reliable bulk-load workflow must answer several questions: which file was received, which records were read, which rows were invalid, which data landed in the target table, which transactions committed, and how to prove the final result matches the source.

An operationally sound architecture typically divides the work into stages:

**Ingest Source → Landing/Staging → Normalize → Validate → Separate Error Rows → Load Target Table → Reconcile → Complete Batch.**

Separating raw data from validated data preserves input evidence, enables fixing errors without re-reading the original file, and allows controlled batch reruns. Oracle provides multiple mechanisms tailored to each workload: SQL*Loader, external tables, `INSERT ... SELECT`, direct-path insert, JDBC batching, PL/SQL `FORALL`, and DML error logging. No single tool fits every data source.

This lesson belongs to the **Integrated Practice** group of Database Engine Relational Oracle. It focuses on designing a bulk-loading pipeline, staging, classifying error rows, row-level error handling, transactions/chunks, safe restarts, and source-to-target reconciliation.

After this lesson, you will be able to:

- Choose the right loading mechanism for files, Java applications, or data already inside the database.
- Design batch IDs, source row numbers, and lineage for every record.
- Create staging tables to hold raw data prior to conversion.
- Distinguish SQL*Loader conventional path, direct path, and external tables.
- Use `INSERT ... SELECT`, `MERGE`, and JDBC batching for appropriate workloads.
- Create error logging tables with `DBMS_ERRLOG`.
- Isolate DML errors using `LOG ERRORS` and `REJECT LIMIT`.
- Use PL/SQL `FORALL SAVE EXCEPTIONS` to handle errors in bulk PL/SQL.
- Distinguish row-level data errors from system-level errors that fail the entire statement/job.
- Select batch sizes and transaction chunk sizes.
- Design idempotency, checkpointing, and retries.
- Reconcile row counts, business keys, monetary totals, checksums, and field-level details.
- Build reports for rejected rows, duplicate rows, and reconciliation variances.
- Create runbooks for operations, recovery, and batch completion.

> **Example Scope:** Examples use Oracle Database 19c, SQL*Loader, SQL, PL/SQL, and Java JDBC. Table names, services, file paths, and business keys are illustrative. Adjust data types, access privileges, resource limits, and transaction policies to match your environment.

## 1. Objectives of a Bulk-Load Pipeline

A well-built bulk load must achieve both throughput and outcome control.

### 1.1. Throughput

Throughput measures how much data is processed per unit of time, such as:

- Rows per second.
- MB per second.
- Files completed per hour.
- Batches completed within an ETL window.

Optimizing purely for speed without tracking errors and completeness can make a pipeline load bad data quickly.

### 1.2. Data Quality

Every record must be evaluated against data rules:

- Are all required fields present?
- Do dates and numbers parse cleanly?
- Do customer/product IDs exist?
- Are business keys duplicated?
- Are values within allowed ranges?
- Are fields mutually consistent?

### 1.3. Traceability

For every row of data, the system should be able to trace back to:

- Source file.
- Batch ID.
- Source row number or source record ID.
- Receipt and load timestamps.
- Mapping/rule version.
- Processing status.
- Rejection reason.

### 1.4. Recoverability

If a job stops partway through, you must know:

- Which chunks have committed.
- Which chunks have not run.
- Which rows have been processed.
- Whether it can be rerun without creating duplicates.
- From which checkpoint it can resume.

### 1.5. Reconciliation

Reconciliation must prove that source and target match according to agreed rules. Comparing total row counts alone is insufficient; two datasets can have identical counts yet differ in keys or values.

## 2. End-to-End Pipeline

~~~text
             SOURCE
        CSV / API / JDBC
               |
               v
        LANDING / FILE STORE
      checksum + immutable file
               |
               v
           STAGING
       raw values + lineage
               |
               v
      NORMALIZE / VALIDATE
        format + business rules
               |
        +------+------+
        |             |
        v             v
     VALID ROWS    REJECT ROWS
        |             |
        v             v
     APPLY DML     ERROR REVIEW
        |
        v
      TARGET
        |
        v
    RECONCILIATION
        |
        v
   BATCH COMPLETION
~~~

### 2.1. Landing

Landing is where raw files or payloads are stored as received. Files should remain immutable for the duration needed for reconciliation and auditing. Record checksum, size, source name, and receipt timestamp.

### 2.2. Staging

Staging is an intermediate area inside Oracle. It can store raw text and metadata before type casting or applying business rules.

### 2.3. Validation

Validation classifies records as valid, warning, or rejected. Rules need stable error codes for reporting and remediation.

### 2.4. Apply

Apply is the step that writes valid data into target tables using `INSERT`, `MERGE`, or PL/SQL/JDBC workflows.

### 2.5. Reconciliation

Reconciliation compares source, staging, accepted, rejected, and target datasets by batch. A batch completes only after passing all defined control checks.

## 3. Designing Batch ID and Lineage

A batch ID uniquely identifies a single data receipt or unit of processing.

### 3.1. Batch Control Table

~~~sql
CREATE TABLE load_batch (
    batch_id          VARCHAR2(40) PRIMARY KEY,
    source_system     VARCHAR2(50) NOT NULL,
    source_file       VARCHAR2(500),
    source_checksum   VARCHAR2(128),
    received_at       TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
    started_at        TIMESTAMP,
    completed_at      TIMESTAMP,
    batch_status      VARCHAR2(20) NOT NULL,
    expected_rows     NUMBER,
    staged_rows       NUMBER DEFAULT 0 NOT NULL,
    valid_rows        NUMBER DEFAULT 0 NOT NULL,
    rejected_rows     NUMBER DEFAULT 0 NOT NULL,
    inserted_rows     NUMBER DEFAULT 0 NOT NULL,
    updated_rows      NUMBER DEFAULT 0 NOT NULL,
    unchanged_rows    NUMBER DEFAULT 0 NOT NULL,
    error_message     VARCHAR2(2000)
);
~~~

Possible status values:

| Status | Meaning |
| --- | --- |
| RECEIVED | Metadata/file received |
| LOADING | Loading into staging |
| STAGED | Data loaded into staging |
| VALIDATING | Validating data |
| VALIDATED | Classified into valid/rejected |
| APPLYING | Writing to target |
| APPLIED | Apply step finished |
| RECONCILING | Running reconciliation |
| COMPLETED | Reconciliation passed |
| PARTIAL | Valid rows applied and rejects accepted per policy |
| FAILED | Batch failed |
| CANCELLED | Batch cancelled per procedure |

Statuses must be updated in alignment with checkpoints and transaction policies. Never mark `COMPLETED` solely because a SQL statement returned without error.

### 3.2. Generating Batch IDs

You can use a UUID or a sequence-generated code. What matters is that the batch ID is unique and propagated across every stage.

~~~sql
INSERT INTO load_batch (
    batch_id,
    source_system,
    source_file,
    source_checksum,
    batch_status,
    expected_rows
)
VALUES (
    'BATCH-20261114-0001',
    'ERP',
    'orders_20261114.csv',
    'sha256:example-checksum',
    'RECEIVED',
    250000
);
~~~

The checksum above is a placeholder. In production, compute the checksum over the actual file at the landing layer and store both algorithm and digest explicitly.

### 3.3. Source Row Number

Each record should have a row number or stable source record ID. If a file might be reordered on rerun, relying strictly on line position is fragile; prefer a stable source record ID or business key when supplied by the source.

### 3.4. Staging Table

Example staging table for orders:

~~~sql
CREATE TABLE stg_order (
    batch_id          VARCHAR2(40) NOT NULL,
    source_row_no     NUMBER NOT NULL,
    source_record_id  VARCHAR2(100),
    order_id_raw      VARCHAR2(100),
    customer_id_raw   VARCHAR2(100),
    order_date_raw    VARCHAR2(100),
    amount_raw        VARCHAR2(100),
    currency_raw      VARCHAR2(20),
    source_file       VARCHAR2(500),
    loaded_at         TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
    validation_status VARCHAR2(20) DEFAULT 'NEW' NOT NULL,
    CONSTRAINT pk_stg_order
        PRIMARY KEY (batch_id, source_row_no)
);
~~~

Raw columns are stored as text so parsing and validation occur under controlled logic. If the source is already strongly typed and pre-validated, staging can use typed columns upfront.

### 3.5. Reject Table

~~~sql
CREATE TABLE load_reject (
    reject_id         NUMBER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    batch_id          VARCHAR2(40) NOT NULL,
    source_row_no     NUMBER,
    source_record_id  VARCHAR2(100),
    source_file       VARCHAR2(500),
    reject_stage      VARCHAR2(30) NOT NULL,
    error_code        VARCHAR2(100) NOT NULL,
    error_message     VARCHAR2(2000),
    raw_payload       CLOB,
    rejected_at       TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
    resolution_status VARCHAR2(20) DEFAULT 'OPEN' NOT NULL
);
~~~

The reject table stores both technical and business errors. You can split into multiple tables by error category or keep a single table keyed by `reject_stage` and `error_code`.

### 3.6. Do Not Rely Only on Free-Form Messages

Use stable error codes such as:

| Error Code | Meaning |
| --- | --- |
| REQUIRED_ORDER_ID | Missing order ID |
| INVALID_ORDER_DATE | Date does not match expected format |
| INVALID_AMOUNT | Monetary amount is invalid |
| UNKNOWN_CUSTOMER | Customer not found |
| DUPLICATE_SOURCE_KEY | Duplicate source record |
| DUPLICATE_TARGET_KEY | Business key already exists |
| INVALID_CURRENCY | Invalid currency code |
| DML_CONSTRAINT_ERROR | DML rejected by database constraint |

Messages may change across versions or locales; stable error codes keep reporting and routing reliable.

## 4. Choosing a Data Loading Tool

| Mechanism | Best-Fit Source | Strengths | Watch-Outs |
| --- | --- | --- | --- |
| SQL*Loader | Text/CSV files | Dedicated bulk-load utility | Control file, bad/discard/log files, direct path |
| External tables | Files on database server | Query files directly with SQL | `DIRECTORY` object, OS permissions, reject limit |
| `INSERT ... SELECT` | Data already in Oracle | Set-based, minimal data movement | Undo/redo, locks, execution plan |
| Direct-path `INSERT` | Large loads into table/partition | Can increase throughput | Restrictions, locking, commit boundaries |
| JDBC batching | Data arriving from Java | Reduces round trips | Batch size, transactions, partial failures |
| PL/SQL `FORALL` | Collections in PL/SQL | Bulk bind reduces context switches | `SAVE EXCEPTIONS` and `SQL%BULK_EXCEPTIONS` |
| DML error logging | `INSERT`/`UPDATE`/`DELETE`/`MERGE` | Isolates many row-level DML errors | Cannot log every error type |

### 4.1. Tool Selection Questions

- Is the data currently in a file or inside the database?
- Is the file located on the application host or the database server?
- Does each record require Java-side transformations?
- Must individual rows have isolated error handling?
- Should valid rows proceed when some rows fail?
- Is volume high enough to benefit from direct-path or dedicated bulk loaders?
- Is an all-or-nothing atomic transaction required across the entire file?
- Does the system allow creating staging and reject tables?

### 4.2. Prefer Set-Based Operations When Data Is Already in Oracle

If the source data already resides in Oracle tables, prefer `INSERT ... SELECT` or `MERGE` instead of pulling millions of rows into Java only to push them back.

~~~sql
INSERT INTO order_archive (
    order_id,
    customer_id,
    order_date,
    amount
)
SELECT
    order_id,
    customer_id,
    order_date,
    amount
FROM orders
WHERE order_date < DATE '2025-01-01';
~~~

The database processes the set right where it lives, avoiding per-row round trips.

## 5. SQL*Loader: Loading Data from Files

SQL*Loader is an Oracle utility for loading data from external files into database tables.

### 5.1. Conventional Path vs. Direct Path

| Mode | Description |
| --- | --- |
| Conventional path | Uses the standard SQL `INSERT` interface; suitable when standard SQL processing is needed and load volume is moderate |
| Direct path | Formats and writes data blocks directly via the direct-load path; typically suited for large bulk loads |

Direct path can reduce overhead compared to conventional path, but imposes restrictions on tables, indexes, triggers, constraints, concurrent access, and transactions. Check the SQL*Loader documentation for your Oracle release before choosing it.

### 5.2. Output Files

| File | Purpose |
| --- | --- |
| Log file | Summary of the load, row counts, timing, and errors |
| Bad file | Records rejected due to data or conversion errors |
| Discard file | Records filtered out by `WHEN` clauses or discard conditions |
| Control file | Describes input layout and table mappings |

Bad files and discard files serve different purposes. A discarded record is not necessarily malformed; it simply did not satisfy a selection predicate in the control file.

### 5.3. CSV Example

File `orders.csv`:

~~~csv
1001,501,2026-11-01,125.50,VND
1002,502,2026-11-02,240.00,VND
1003,503,2026-11-03,89.90,VND
~~~

Assume the file has the column order above and one record per line.

### 5.4. Control File

~~~text
LOAD DATA
INFILE 'orders.csv'
BADFILE 'orders.bad'
DISCARDFILE 'orders.dsc'
APPEND
INTO TABLE stg_order
FIELDS TERMINATED BY ','
OPTIONALLY ENCLOSED BY '"'
TRAILING NULLCOLS
(
    order_id_raw     CHAR,
    customer_id_raw  CHAR,
    order_date_raw   CHAR,
    amount_raw       CHAR,
    currency_raw     CHAR
)
~~~

This control file is a minimal example. Our staging table also requires populating `batch_id`, `source_row_no`, and `source_file` using constant/bound fields or a dedicated metadata assignment step per your operational workflow.

If you need a stable source row number, use record numbering features in the control file or load into a staging structure carrying record numbers. Verify `RECNUM` syntax and mappings for your control file version.

### 5.5. Running SQL*Loader

~~~text
sqlldr userid=app_user@SALES_PROD control=orders.ctl log=orders.log bad=orders.bad discard=orders.dsc direct=false errors=1000
~~~

Never put real passwords on the command line or in shell history. Use environment-appropriate secure authentication and supply secrets via prompts or a secure credential store when supported.

### 5.6. Direct Path

You can run direct path:

~~~text
sqlldr userid=app_user@SALES_PROD control=orders.ctl log=orders.log bad=orders.bad direct=true
~~~

Evaluate:

- Throughput compared to conventional path.
- Index and constraint maintenance.
- Trigger behavior.
- Concurrent access.
- Recovery and logging requirements.
- Index build/rebuild duration, if applicable.
- Restartability after failure.

Never switch to direct path based solely on row count. Workload characteristics and table restrictions determine the right choice.

### 5.7. ERRORS and ROWS

SQL*Loader has parameters controlling allowable error thresholds and rows between save/commit points depending on load path. These parameters are not a comprehensive transaction policy that replaces batch design.

Inspect the log file for:

- Rows read.
- Rows loaded.
- Rows rejected.
- Rows discarded.
- Rows not loaded due to errors.
- Commit points.
- Error messages.

Never assume a job succeeded merely because the OS process exit code is 0 if the log reveals rejected rows disallowed by business rules.

### 5.8. Handling Real-World CSVs

CSV files can contain:

- Commas inside quoted fields.
- Escaped quotes.
- Blank lines.
- Unicode characters.
- Embedded newlines inside quoted fields.
- Varying decimal separators.
- Locale-specific date formats.

Agree explicitly on encoding, delimiter, quote character, escape rules, line endings, and null representation with the upstream producer. Test edge-case files before running large volumes.

### 5.9. Reloading a File

Never run `APPEND` repeatedly on the same file without idempotency controls. Reruns can introduce duplicates. Use batch IDs, source keys, controlled staging cleanup, or batch-scoped staging truncation before reloading.

## 6. External Tables: Querying Files with SQL

External tables allow Oracle to read data from files via SQL without loading them into physical tables first.

### 6.1. DIRECTORY Object

Oracle requires a `DIRECTORY` object pointing to a folder on the database server:

~~~sql
CREATE OR REPLACE DIRECTORY inbound_dir AS '/u01/data/inbound';
~~~

Grant read access:

~~~sql
GRANT READ ON DIRECTORY inbound_dir TO app_user;
~~~

If the external table is configured to write bad or log files, `WRITE` privilege may also be needed. The OS user running the Oracle database process must also hold matching filesystem permissions.

The path is a path on the database server, not a local path on your laptop or application server.

### 6.2. Creating an External Table

~~~sql
CREATE TABLE ext_order_file (
    order_id_text     VARCHAR2(100),
    customer_id_text  VARCHAR2(100),
    order_date_text   VARCHAR2(100),
    amount_text       VARCHAR2(100),
    currency_text     VARCHAR2(20)
)
ORGANIZATION EXTERNAL (
    TYPE ORACLE_LOADER
    DEFAULT DIRECTORY inbound_dir
    ACCESS PARAMETERS (
        RECORDS DELIMITED BY NEWLINE
        FIELDS TERMINATED BY ','
        OPTIONALLY ENCLOSED BY '"'
        MISSING FIELD VALUES ARE NULL
        (
            order_id_text     CHAR(100),
            customer_id_text  CHAR(100),
            order_date_text   CHAR(100),
            amount_text       CHAR(100),
            currency_text     CHAR(20)
        )
    )
    LOCATION ('orders.csv')
)
REJECT LIMIT UNLIMITED;
~~~

This example assumes a simple file structure. For complex CSVs, check `ORACLE_LOADER` access parameter options and record format limitations.

### 6.3. Querying an External Table

~~~sql
SELECT *
FROM ext_order_file;
~~~

An external table exposes a file as a queryable table in SQL. The data stays in the file; a `SELECT` does not copy data into staging automatically.

### 6.4. Loading into Staging

~~~sql
INSERT INTO stg_order (
    batch_id,
    source_row_no,
    order_id_raw,
    customer_id_raw,
    order_date_raw,
    amount_raw,
    currency_raw,
    source_file
)
SELECT
    'BATCH-20261114-0001',
    ROWNUM,
    order_id_text,
    customer_id_text,
    order_date_text,
    amount_text,
    currency_text,
    'orders.csv'
FROM ext_order_file;
~~~

`ROWNUM` here merely illustrates assigning an ordinal within a single read pass. If you need stable record identity across reruns, generate a source record ID upstream or use a controlled record numbering mechanism.

### 6.5. REJECT LIMIT

External tables use `REJECT LIMIT` to cap how many access/record errors Oracle tolerates before failing the query. `UNLIMITED` does not mean bad data is accepted or automatically routed to a reject table with full business reasons.

File parsing errors in an external table differ from business validation errors once data has been read. Design separate handling for:

- File/access rejects.
- Data conversion rejects.
- Business validation rejects.
- Target DML rejects.

### 6.6. When Are External Tables a Good Fit?

- Files already land on the database server or storage mounted by Oracle.
- You want to use SQL to filter or transform before loading.
- You want to avoid streaming data through the application tier.
- You can manage `DIRECTORY` and OS filesystem permissions securely.

If files reside only on an application pod/host, either transfer them to storage readable by the database server or load via JDBC/SQL*Loader from the appropriate tier.

## 7. Staging-First: Preserving Raw Data Before Transformation

Staging is the central control point of the pipeline.

### 7.1. Why Preserve Raw Values?

If dates or numbers are parsed while reading the file, a single malformed value can abort the entire load or destroy the original representation. Raw staging lets you:

- Preserve exact source values.
- Rerun validation when business rules evolve.
- Compare raw values against transformed values.
- Categorize conversion failures.
- Audit and trace lineage backward.

### 7.2. Attaching Batch Metadata

Every row must carry a batch ID. If the source provides a source ID, keep that too.

~~~sql
SELECT
    batch_id,
    source_row_no,
    source_record_id,
    order_id_raw,
    customer_id_raw,
    order_date_raw,
    amount_raw,
    currency_raw
FROM stg_order
WHERE batch_id = :batch_id;
~~~

### 7.3. Never Mix Batches

Validation, apply, and reconciliation queries must always filter by `batch_id`. Otherwise, rows from earlier batches could be counted or reprocessed.

### 7.4. Staging Indexes

Commonly useful indexes:

- `(batch_id, source_row_no)`.
- `(batch_id, validation_status)`.
- `(batch_id, source_record_id)`.

Avoid over-indexing staging when insert throughput is critical. Measure both load and query costs.

### 7.5. Partitioning Staging

For high volumes and batch/date retention policies, partitioning staging by date or batch window simplifies data management and purging. Partition keys should align with actual query predicates, especially `batch_id` and load time.

## 8. Data Normalization and Conversion

Validation should separate safe type conversion from business rules.

### 8.1. Dates

Do not rely on default `NLS_DATE_FORMAT`.

~~~sql
TO_DATE(order_date_raw, 'YYYY-MM-DD')
~~~

Formats must match the source contract. If the source includes timestamps, use `TO_TIMESTAMP` with the matching format mask.

### 8.2. Decimals

Do not rely on default `NLS_NUMERIC_CHARACTERS` when a file uses explicit decimal separators.

~~~sql
TO_NUMBER(
    amount_raw,
    '999999999999D99',
    'NLS_NUMERIC_CHARACTERS=''.,'''
)
~~~

Here `.` is the decimal separator and `,` is the group separator per the specified NLS parameter.

### 8.3. Validating Conversions Before Casting

Oracle 19c provides `VALIDATE_CONVERSION`:

~~~sql
SELECT
    source_row_no,
    amount_raw,
    VALIDATE_CONVERSION(
        amount_raw AS NUMBER,
        '999999999999D99',
        'NLS_NUMERIC_CHARACTERS=''.,'''
    ) AS amount_is_valid
FROM stg_order
WHERE batch_id = :batch_id;
~~~

`VALIDATE_CONVERSION` tests whether an expression can convert to the target type. It does not replace business validation, such as verifying that `amount > 0`.

### 8.4. Nulls and Empty Strings

Oracle treats zero-length character strings as `NULL` in SQL for `VARCHAR2`. The source contract must clarify:

- Does an empty field mean `NULL` or missing data?
- Should whitespace-only strings be trimmed?
- What do sentinel strings like `N/A` or `UNKNOWN` mean?

Never blindly convert all empty values to `0` or a dummy date.

### 8.5. Text Normalization

May include:

- Trimming leading/trailing whitespace.
- Unicode normalization.
- Standardizing country/currency codes.
- Case normalization on business keys.
- Stripping invalid control characters.

Do not trim or alter casing on fields where whitespace or letter case is meaningful data.

## 9. Multi-Layer Validation

A record is promoted to accepted only after passing all required validation layers.

### 9.1. Structural Validation

- Expected column count.
- Valid delimiter and encoding.
- No truncated records.
- Field lengths within bounds.
- Valid header version.

### 9.2. Type Validation

- Dates parse cleanly.
- Numbers parse cleanly.
- Timestamps are valid.
- Unicode encoding is valid.

### 9.3. Required-Field Validation

- Order ID is non-null.
- Customer ID is non-null.
- Amount is non-null when required by business rules.

### 9.4. Domain Validation

- Currency belongs to allowed list.
- Status belongs to valid enum.
- Amount within bounds.
- Date within valid business range.

### 9.5. Referential Validation

- Customer exists.
- Product exists.
- Account is active.
- Related foreign keys are valid.

### 9.6. Duplicate Validation

- Duplicates within the same file.
- Duplicates across batches.
- Duplicates against target table.
- Duplicate source ID with differing content.

### 9.7. Cross-Field Validation

- End date is not before start date.
- Currency matches the account currency.
- Quantity and unit price produce a valid total.
- Status is consistent with timestamp fields.

### 9.8. Assigning Stable Error Codes

Example view for typed conversion:

~~~sql
CREATE OR REPLACE VIEW v_stg_order_converted AS
SELECT
    batch_id,
    source_row_no,
    source_record_id,
    order_id_raw,
    customer_id_raw,
    order_date_raw,
    amount_raw,
    currency_raw,
    CASE
        WHEN VALIDATE_CONVERSION(order_id_raw AS NUMBER) = 1
        THEN TO_NUMBER(order_id_raw)
    END AS order_id,
    CASE
        WHEN VALIDATE_CONVERSION(customer_id_raw AS NUMBER) = 1
        THEN TO_NUMBER(customer_id_raw)
    END AS customer_id,
    CASE
        WHEN VALIDATE_CONVERSION(order_date_raw AS DATE, 'YYYY-MM-DD') = 1
        THEN TO_DATE(order_date_raw, 'YYYY-MM-DD')
    END AS order_date,
    CASE
        WHEN VALIDATE_CONVERSION(
            amount_raw AS NUMBER,
            '999999999999D99',
            'NLS_NUMERIC_CHARACTERS=''.,'''
        ) = 1
        THEN TO_NUMBER(
            amount_raw,
            '999999999999D99',
            'NLS_NUMERIC_CHARACTERS=''.,'''
        )
    END AS amount
FROM stg_order;
~~~

This view demonstrates guarded conversion. In large systems, consider a typed staging table or materialized transform table to avoid repeating conversions multiple times.

### 9.9. Recording Validation Rejects

~~~sql
INSERT INTO load_reject (
    batch_id,
    source_row_no,
    source_record_id,
    source_file,
    reject_stage,
    error_code,
    error_message
)
SELECT
    s.batch_id,
    s.source_row_no,
    s.source_record_id,
    s.source_file,
    'VALIDATION',
    CASE
        WHEN s.order_id_raw IS NULL THEN 'REQUIRED_ORDER_ID'
        WHEN VALIDATE_CONVERSION(s.order_id_raw AS NUMBER) = 0
            THEN 'INVALID_ORDER_ID'
        WHEN s.amount_raw IS NULL THEN 'REQUIRED_AMOUNT'
        WHEN VALIDATE_CONVERSION(s.amount_raw AS NUMBER) = 0
            THEN 'INVALID_AMOUNT'
        ELSE 'OTHER_VALIDATION_ERROR'
    END,
    'Record failed validation'
FROM stg_order s
WHERE s.batch_id = :batch_id
  AND (
      s.order_id_raw IS NULL
      OR VALIDATE_CONVERSION(s.order_id_raw AS NUMBER) = 0
      OR s.amount_raw IS NULL
      OR VALIDATE_CONVERSION(s.amount_raw AS NUMBER) = 0
  );
~~~

If a single row has multiple errors, you can write one reject record per error or one record listing all errors. Choose a consistent model so reports do not mistake error count for rejected-row count.

## 10. Separating Accepted Rows and Rejected Rows

Do not delete raw staging immediately after generating rejects.

### 10.1. Accepted/Typed Staging Table

~~~sql
CREATE TABLE stg_order_valid (
    batch_id          VARCHAR2(40) NOT NULL,
    source_row_no     NUMBER NOT NULL,
    source_record_id  VARCHAR2(100),
    order_id          NUMBER NOT NULL,
    customer_id       NUMBER NOT NULL,
    order_date        DATE NOT NULL,
    amount            NUMBER(15,2) NOT NULL,
    currency_code     VARCHAR2(3) NOT NULL,
    CONSTRAINT pk_stg_order_valid
        PRIMARY KEY (batch_id, source_row_no)
);
~~~

### 10.2. Loading Accepted Rows

~~~sql
INSERT INTO stg_order_valid (
    batch_id,
    source_row_no,
    source_record_id,
    order_id,
    customer_id,
    order_date,
    amount,
    currency_code
)
SELECT
    batch_id,
    source_row_no,
    source_record_id,
    order_id,
    customer_id,
    order_date,
    amount,
    currency_raw
FROM v_stg_order_converted
WHERE batch_id = :batch_id
  AND order_id IS NOT NULL
  AND customer_id IS NOT NULL
  AND order_date IS NOT NULL
  AND amount IS NOT NULL
  AND currency_raw IN ('VND', 'USD', 'EUR');
~~~

This illustrates only type and domain checks. Add customer existence, duplicate checks, and remaining business rules before applying.

### 10.3. Updating Staging Status

~~~sql
UPDATE stg_order s
SET validation_status =
    CASE
        WHEN EXISTS (
            SELECT 1
            FROM stg_order_valid v
            WHERE v.batch_id = s.batch_id
              AND v.source_row_no = s.source_row_no
        )
        THEN 'VALID'
        ELSE 'REJECTED'
    END
WHERE s.batch_id = :batch_id;
~~~

Ensure every raw record finishes validation with exactly one terminal status. Even if a record has multiple reject reasons, its status remains `REJECTED` while the reject table stores each reason detail.

## 11. Duplicate Detection

Duplicates can occur within the same file or against previously loaded target data.

### 11.1. Duplicates Within the Batch

~~~sql
SELECT
    order_id,
    COUNT(*) AS duplicate_count
FROM stg_order_valid
WHERE batch_id = :batch_id
GROUP BY order_id
HAVING COUNT(*) > 1;
~~~

### 11.2. Selecting Which Row to Keep

If the source contract allows picking one record by timestamp or priority, use `ROW_NUMBER` with deterministic ordering:

~~~sql
SELECT *
FROM (
    SELECT
        v.*,
        ROW_NUMBER() OVER (
            PARTITION BY v.order_id
            ORDER BY v.source_row_no DESC
        ) AS rn
    FROM stg_order_valid v
    WHERE v.batch_id = :batch_id
)
WHERE rn = 1;
~~~

Picking the last row only makes sense if source row ordering is genuinely meaningful. Otherwise, order by a business timestamp or source sequence. Never silently drop duplicates without logging a reject or audit record.

### 11.3. Duplicates Against Target

~~~sql
SELECT
    s.order_id,
    s.source_row_no
FROM stg_order_valid s
JOIN app_order t
  ON t.order_id = s.order_id
WHERE s.batch_id = :batch_id;
~~~

These are duplicates if business rules require insert-only semantics. If updates are allowed, switch to `MERGE`.

### 11.4. Unique Constraints Remain the Final Guard

Duplicate pre-checks do not eliminate race conditions between concurrent batches. Unique constraints on target tables remain essential to guarantee integrity.

## 12. Loading into Target via INSERT ... SELECT

Once accepted rows sit in staging, set-based `INSERT` is usually much faster than row-by-row loops.

### 12.1. Insert-Only

~~~sql
INSERT INTO app_order (
    order_id,
    customer_id,
    order_date,
    amount,
    currency_code,
    source_system,
    source_record_id,
    load_batch_id
)
SELECT
    order_id,
    customer_id,
    order_date,
    amount,
    currency_code,
    'ERP',
    source_record_id,
    batch_id
FROM stg_order_valid
WHERE batch_id = :batch_id;
~~~

### 12.2. Recording Inserted Row Counts

In PL/SQL, read `SQL%ROWCOUNT` immediately after the DML statement being measured:

~~~sql
DECLARE
    l_inserted NUMBER;
BEGIN
    INSERT INTO app_order (
        order_id, customer_id, order_date, amount,
        currency_code, source_system, source_record_id, load_batch_id
    )
    SELECT
        order_id, customer_id, order_date, amount,
        currency_code, 'ERP', source_record_id, batch_id
    FROM stg_order_valid
    WHERE batch_id = :batch_id;

    l_inserted := SQL%ROWCOUNT;

    UPDATE load_batch
    SET inserted_rows = l_inserted,
        batch_status = 'APPLIED'
    WHERE batch_id = :batch_id;
END;
/
~~~

`SQL%ROWCOUNT` must be captured immediately after the target statement. If you update metadata first and read `SQL%ROWCOUNT` afterward, it reflects the metadata `UPDATE`, not the `INSERT`.

### 12.3. Insert Conflicts

If a row violates a unique constraint, a standard `INSERT` fails. Options include:

- Checking duplicates beforehand.
- Using `MERGE` when business rules specify upsert.
- Using DML error logging to capture loggable row errors.
- Chunking inserts to bound retry scope.

Never catch all errors and ignore them. System errors can leave an entire statement incomplete.

## 13. MERGE for Upserts

`MERGE` inserts new rows or updates existing rows matched by business key.

### 13.1. Example

~~~sql
MERGE INTO app_customer t
USING (
    SELECT
        customer_id,
        customer_name,
        email
    FROM stg_customer_valid
    WHERE batch_id = :batch_id
) s
ON (t.customer_id = s.customer_id)
WHEN MATCHED THEN
    UPDATE SET
        t.customer_name = s.customer_name,
        t.email = s.email
WHEN NOT MATCHED THEN
    INSERT (customer_id, customer_name, email)
    VALUES (s.customer_id, s.customer_name, s.email);
~~~

### 13.2. MERGE Source Must Be Deterministic

If multiple source rows match the same target row, `MERGE` fails because it cannot update the same row multiple times in one statement. Deduplicate the source per business rules prior to `MERGE`.

### 13.3. Distinguishing Inserted vs. Updated Rows

`SQL%ROWCOUNT` on `MERGE` returns total affected rows without separating inserts from updates. If separate metrics are needed, measure them explicitly:

- Compare source against target prior to `MERGE` within a consistent snapshot/transaction.
- Stamp action markers in staging.
- Use output/auditing mechanisms supported by your Oracle release.
- Reconcile target rows after `MERGE` by batch ID and source key.

Never report `inserted_rows = total MERGE rows`.

### 13.4. Idempotent MERGE

`MERGE` supports safe reruns when:

- Match keys are stable.
- Update semantics are deterministic.
- Source batch data does not mutate unexpectedly.
- Side effects outside the target table are not duplicated.
- Unique constraints protect business keys.

`MERGE` alone does not make every pipeline idempotent. Triggers, audit events, sequence generation, and external side effects must all be evaluated.

## 14. Direct-Path INSERT

Direct-path `INSERT` writes directly into data segments and is commonly used for very large loads.

### 14.1. APPEND Hint

~~~sql
INSERT /*+ APPEND */ INTO app_order_archive (
    order_id,
    customer_id,
    order_date,
    amount
)
SELECT
    order_id,
    customer_id,
    order_date,
    amount
FROM stg_order_valid
WHERE batch_id = :batch_id;
~~~

The `APPEND` hint requests a direct-path insert whenever Oracle permits it. The optimizer may ignore the hint if conditions are not met; verify actual execution behavior via SQL trace or execution plan.

### 14.2. Benefits

- Can reduce some conventional-insert overhead.
- Can leverage parallel direct-path loading when workload and configuration permit.
- Well suited for append-oriented bulk loads.

### 14.3. Limitations

- Subject to restrictions on object types, constraints, triggers, partitioning, and transaction state.
- Direct-path inserts can impact concurrent access and table locking.
- Index maintenance and storage growth still apply.
- Subsequent reads/writes on the same object within the same transaction may be restricted.
- With direct-path or parallel DML, accessing the modified object again before commit can raise `ORA-12838` under applicable restrictions.

### 14.4. Transaction Boundaries

~~~sql
INSERT /*+ APPEND */ INTO app_order_archive
SELECT ...
FROM stg_order_valid
WHERE batch_id = :batch_id;

COMMIT;
~~~

Never assume you can immediately read or modify the same table in the same transaction after direct-path or parallel DML. Check exact restrictions and place commit boundaries accordingly.

### 14.5. NOLOGGING

Some bulk loads can use `NOLOGGING` where permitted to reduce redo generation, but this affects recoverability and backup strategy. Never enable `NOLOGGING` purely for speed. The DBA must evaluate force logging, Data Guard, backup/recovery SLAs, and post-load backups.

### 14.6. Partition Exchange

In data warehouses, you can load a structurally identical staging table/partition and use `EXCHANGE PARTITION` to swap data into the target partition. This metadata-only operation is very fast for suitable workloads, provided you manage:

- Matching column structures.
- Proper constraints and validation.
- Local and global index maintenance.
- Valid partition keys and data boundaries.
- Pre-exchange data verification.
- Transaction/DDL operational plans.

DDL carries implicit commit semantics; never place `EXCHANGE PARTITION` inside a transaction expecting DML-style rollback.

## 15. DML Error Logging with DBMS_ERRLOG

DML error logging allows Oracle to record eligible per-row errors into an error logging table while continuing to process remaining rows per statement semantics.

### 15.1. Creating the Error Logging Table

~~~sql
BEGIN
    DBMS_ERRLOG.CREATE_ERROR_LOG(
        dml_table_name      => 'APP_ORDER',
        err_log_table_name  => 'ERR$_APP_ORDER',
        skip_unsupported    => TRUE
    );
END;
/
~~~

Create the error table once for the target table. If the target has data types unsupported in error tables, `skip_unsupported => TRUE` omits those columns. Therefore, never assume the error table captures every target column.

### 15.2. System Columns

Error logging tables include metadata columns such as:

| Column | Meaning |
| --- | --- |
| `ORA_ERR_NUMBER$` | Oracle error number |
| `ORA_ERR_MESG$` | Error message |
| `ORA_ERR_ROWID$` | Related rowid, if applicable |
| `ORA_ERR_OPTYP$` | DML operation type |
| `ORA_ERR_TAG$` | Application-supplied tag |

Additionally, the table contains columns matching supported target table columns.

### 15.3. INSERT with LOG ERRORS

~~~sql
INSERT INTO app_order (
    order_id,
    customer_id,
    order_date,
    amount,
    currency_code
)
SELECT
    order_id,
    customer_id,
    order_date,
    amount,
    currency_code
FROM stg_order_valid
WHERE batch_id = :batch_id
LOG ERRORS INTO err$_app_order ('BATCH-20261114-0001')
REJECT LIMIT UNLIMITED;
~~~

The tag identifies the batch inside the error logging table.

### 15.4. Querying Logged Errors

~~~sql
SELECT
    ora_err_number$,
    ora_err_mesg$,
    ora_err_optyp$,
    ora_err_tag$,
    order_id,
    customer_id,
    amount
FROM err$_app_order
WHERE ora_err_tag$ = 'BATCH-20261114-0001'
ORDER BY order_id;
~~~

### 15.5. REJECT LIMIT

`REJECT LIMIT` specifies the maximum number of row errors tolerated before the statement aborts. You can provide a numeric limit or `UNLIMITED`.

~~~sql
LOG ERRORS INTO err$_app_order ('BATCH-20261114-0001')
REJECT LIMIT 100;
~~~

Choose `REJECT LIMIT` according to business policy. `UNLIMITED` does not guarantee the statement will always succeed: errors unsupported by error logging, parse errors, privilege errors, system errors, or statement-level failures will still abort the statement.

### 15.6. MERGE with LOG ERRORS

~~~sql
MERGE INTO app_customer t
USING stg_customer_valid s
ON (t.customer_id = s.customer_id)
WHEN MATCHED THEN
    UPDATE SET t.customer_name = s.customer_name
WHEN NOT MATCHED THEN
    INSERT (customer_id, customer_name)
    VALUES (s.customer_id, s.customer_name)
LOG ERRORS INTO err$_app_customer ('CUSTOMER-BATCH-01')
REJECT LIMIT UNLIMITED;
~~~

Verify syntax for your Oracle release and DML pattern. Error logging does not replace pre-`MERGE` validation.

### 15.7. Errors That Should Not Be Assumed Loggable

DML error logging does not capture every kind of error:

- Syntax or statement parse errors.
- Insufficient privileges.
- Connection or database instance failures.
- Resource exhaustion such as tablespace/space errors.
- Certain constraint/deferred constraint errors and direct-path/parallel DML restrictions.
- Unsupported data types in error tables.

Consult the Oracle documentation for the exact list of restrictions. Test error behavior for each DML pattern on your target release, access path, and table definition.

### 15.8. Error Logging Does Not Automatically Build a Business Reject Workflow

The error table logs DML errors. It does not automatically know:

- Which source file contained the record.
- The original source line number.
- Whether the record should be retried.
- Which errors require data remediation.
- Whether partial batch success is allowed.

To preserve lineage, carry `source_record_id`/source row number into the target or a mapping table, or join back to staging by business key.

### 15.9. Transaction Semantics

Error logging operates within the transaction context of the DML statement. Applications must define commit/rollback policies and test scenarios where `REJECT LIMIT` is exceeded or the statement fails. Do not treat the error logging table as an autonomous audit system that auto-commits independently of the transaction.

## 16. PL/SQL FORALL and SAVE EXCEPTIONS

`FORALL` is PL/SQL's bulk-binding mechanism. It sends collection values to a DML statement without incurring one SQL/PLSQL context switch per element like a regular DML loop.

### 16.1. Basic FORALL

~~~sql
DECLARE
    TYPE t_order_ids IS TABLE OF app_order.order_id%TYPE;
    l_order_ids t_order_ids := t_order_ids(1001, 1002, 1003);
BEGIN
    FORALL i IN 1 .. l_order_ids.COUNT
        UPDATE app_order
        SET status = 'READY'
        WHERE order_id = l_order_ids(i);
END;
/
~~~

### 16.2. SAVE EXCEPTIONS

By default, an error on any iteration aborts the `FORALL` statement. `SAVE EXCEPTIONS` instructs Oracle to record iteration errors and continue executing remaining iterations; upon completion, PL/SQL raises `ORA-24381`.

### 16.3. Complete Example

~~~sql
DECLARE
    TYPE t_order_ids IS TABLE OF app_order.order_id%TYPE;
    l_order_ids t_order_ids := t_order_ids(1001, 1002, 1003, 1004);

    e_bulk_errors EXCEPTION;
    PRAGMA EXCEPTION_INIT(e_bulk_errors, -24381);
BEGIN
    FORALL i IN 1 .. l_order_ids.COUNT SAVE EXCEPTIONS
        UPDATE app_order
        SET status = 'READY'
        WHERE order_id = l_order_ids(i);

    DBMS_OUTPUT.PUT_LINE('Bulk DML completed without row errors');

EXCEPTION
    WHEN e_bulk_errors THEN
        DBMS_OUTPUT.PUT_LINE(
            'Bulk errors: ' || SQL%BULK_EXCEPTIONS.COUNT
        );

        FOR i IN 1 .. SQL%BULK_EXCEPTIONS.COUNT LOOP
            DBMS_OUTPUT.PUT_LINE(
                'Iteration=' ||
                SQL%BULK_EXCEPTIONS(i).ERROR_INDEX ||
                ', Oracle error=' ||
                SQL%BULK_EXCEPTIONS(i).ERROR_CODE
            );
        END LOOP;
END;
/
~~~

### 16.4. ERROR_INDEX

`ERROR_INDEX` identifies which `FORALL` iteration failed. For dense collections over `1 .. COUNT`, it maps directly to the collection index. With `INDICES OF`, `VALUES OF`, or sparse collections, map the iteration index back to the source record carefully.

### 16.5. SQL%BULK_ROWCOUNT

`SQL%BULK_ROWCOUNT(i)` reports how many rows iteration `i` affected. This is useful when each key is expected to update exactly one row:

- 0 rows: record not found.
- 1 row: exact match.
- Multiple rows: DML predicate was insufficiently selective or business rules allow multi-row updates.

### 16.6. FORALL Is Not SQL*Loader

`FORALL` fits when data is already in PL/SQL collections. When the source is a large file, SQL*Loader or external tables are usually better suited. Never load millions of rows into PL/SQL collections if staging and set-based SQL can process them using far less memory.

## 17. JDBC Batching for Java Data Sources

When data arrives from APIs, file streams, or message queues inside a Java application, JDBC batching reduces network round trips.

### 17.1. PreparedStatement

~~~java
String sql = """
    INSERT INTO stg_order (
        batch_id, source_row_no, order_id_raw,
        customer_id_raw, order_date_raw, amount_raw, currency_raw
    )
    VALUES (?, ?, ?, ?, ?, ?, ?)
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    int pending = 0;

    for (SourceOrder row : sourceRows) {
        ps.setString(1, batchId);
        ps.setLong(2, row.sourceRowNo());
        ps.setString(3, row.orderId());
        ps.setString(4, row.customerId());
        ps.setString(5, row.orderDate());
        ps.setString(6, row.amount());
        ps.setString(7, row.currency());
        ps.addBatch();
        pending++;

        if (pending == 100) {
            ps.executeBatch();
            ps.clearBatch();
            pending = 0;
        }
    }

    if (pending > 0) {
        ps.executeBatch();
        ps.clearBatch();
    }
}
~~~

A batch size of 100 is a starting point for benchmarking, not a universal optimum for every workload.

### 17.2. Transaction Chunks

~~~java
connection.setAutoCommit(false);

try {
    // addBatch/executeBatch for a chunk
    connection.commit();
} catch (SQLException e) {
    connection.rollback();
    throw e;
}
~~~

If you commit every 1,000 rows, each chunk is an independent transaction. Executing `executeBatch` every 100 rows while committing after 1,000 rows sends 10 JDBC batches within one transaction.

### 17.3. BatchUpdateException

When `executeBatch` throws, inspect:

- `getUpdateCounts()`.
- `getLargeUpdateCounts()` when using the large-update API.
- `getSQLState()`.
- `getErrorCode()`.
- `getNextException()`.

JDBC drivers may stop or continue on errors according to documented driver behavior. Oracle JDBC standard batching stops at the failing operation and returns update counts for preceding successful operations. Do not assume all drivers behave identically.

### 17.4. Retries

Never blindly retry an entire batch. If earlier chunks already committed, retrying the whole file can create duplicates. Rely on batch IDs, source keys, unique constraints, and checkpoints.

### 17.5. JDBC Batching Does Not Replace Validation

Batching only optimizes DML transport. It does not automatically route bad records into reject rows. Validate beforehand or use Oracle staging and error logging.

## 18. Distinguishing Row Errors from Job-Wide Errors

This is a critical pipeline design decision.

### 18.1. Row-Level Data Errors

Examples:

- Invalid date.
- Unparseable amount.
- Missing customer ID.
- Nonexistent foreign key.
- Duplicate business key.
- Value out of allowed range.

These errors can generally be attributed to a specific source record and routed to the reject table.

### 18.2. Statement/Job-Level Errors

Examples:

- Invalid SQL syntax.
- Insufficient privileges.
- Tablespace full.
- Database unavailable.
- Network connection lost.
- Deadlock or resource failure.
- Unreadable data file.
- Service or instance shutdown.

These errors normally require stopping or retrying the statement, chunk, or job under a recovery policy. Never log them as if only a single data row were invalid.

### 18.3. Handling Matrix

| Error Type | Action |
| --- | --- |
| Validation error | Log reject tied to source row |
| Loggable DML constraint error | Use `LOG ERRORS` or handle exception |
| JDBC batch row error | Inspect `BatchUpdateException` and update counts |
| PL/SQL `FORALL` row error | `SAVE EXCEPTIONS` and `SQL%BULK_EXCEPTIONS` |
| File parse error | SQL*Loader bad file or external table diagnostics |
| Network/system error | Stop chunk, roll back if possible, retry per policy |
| Tablespace/privilege/config error | Stop job, fix root cause, do not spin-retry |

## 19. Transaction and Chunk Design

Batch size and transaction chunk size are two distinct concepts.

### 19.1. Batch Size

Number of rows bundled into a single round trip or execution call, such as:

- JDBC `addBatch`/`executeBatch`.
- One bulk operation in the application.

### 19.2. Transaction Chunk Size

Number of rows processed within one transaction before committing.

Example:

~~~text
File: 1,000,000 rows

Transaction 1: 10 batches x 100 rows = 1,000 rows -> COMMIT
Transaction 2: 10 batches x 100 rows = 1,000 rows -> COMMIT
...
Transaction 1000: 1,000 rows -> COMMIT
~~~

### 19.3. Transactions Too Small

- Increases commit frequency.
- Increases log sync and commit overhead.
- Can reduce throughput.
- Makes whole-file atomicity harder to enforce.

### 19.4. Transactions Too Large

- Increases undo and redo pressure.
- Holds locks longer.
- Increases rollback duration.
- Increases risk of losing substantial progress on failure.
- Increases recovery time.

### 19.5. Sizing Chunks via Benchmarks

Measure:

- Elapsed time.
- Rows per second.
- Commit latency.
- Undo/redo generation.
- Memory consumption.
- Lock waits.
- Error rate.
- Rollback duration.

Do not force one universal chunk size across all tables; row width, indexes, LOBs, constraints, and concurrency all shift the optimum.

### 19.6. Atomic File vs. Partial Acceptance?

Two common policies:

**Atomic file**

- Any bad record prevents the batch from completing.
- All target changes can be rolled back.
- Fix the file and rerun the entire batch.
- Fits files that must be wholly consistent per business rules.

**Partial acceptance**

- Valid rows are applied and committed.
- Bad rows are isolated in the reject table.
- Batch can enter `PARTIAL` status.
- Failed rows are remediated and reprocessed via a separate workflow.
- Fits workloads where records can be processed independently.

Decide the policy before implementation. Never let default SQL*Loader or JDBC driver behavior dictate business atomicity.

## 20. Idempotency and Safe Restarts

Idempotency allows rerunning the same input without causing unintended side effects.

### 20.1. Business Keys

Example unique constraint:

~~~sql
ALTER TABLE app_order
ADD CONSTRAINT uq_app_order_source
UNIQUE (source_system, source_record_id);
~~~

If the same source record is replayed, the database blocks duplicate keys. Decide whether duplicates should be rejected, ignored, or updated.

### 20.2. Batch ID and File Checksum

Record:

- Source system.
- Source file name.
- File checksum.
- File size.
- Source row count.
- Batch ID.
- Mapping/rule version.

If a file has the same name but a different checksum, it is a different input. Never rely solely on file name to determine whether a file was already loaded.

### 20.3. Per-Chunk Checkpoints

~~~sql
CREATE TABLE load_checkpoint (
    batch_id       VARCHAR2(40) NOT NULL,
    chunk_no       NUMBER NOT NULL,
    first_row_no   NUMBER,
    last_row_no    NUMBER,
    chunk_status   VARCHAR2(20) NOT NULL,
    committed_at   TIMESTAMP,
    processed_rows NUMBER DEFAULT 0 NOT NULL,
    CONSTRAINT pk_load_checkpoint PRIMARY KEY (batch_id, chunk_no)
);
~~~

Mark a checkpoint `COMMITTED` only after the chunk's data has committed successfully. When design allows, persist the checkpoint and target data in the same transaction.

### 20.4. Crash Recovery

When a job restarts:

1. Read batch status.
2. Verify whether the file checksum matches the prior input.
3. Read the last committed checkpoint.
4. Identify incomplete chunks.
5. Reconcile target rows by batch/source key.
6. Resume uncommitted chunks.
7. Re-run reconciliation before marking complete.

### 20.5. Do Not Trust Application State Alone

A process can crash after Oracle commits but before the application updates batch status. Always verify database checkpoints and target records before retrying.

### 20.6. Unknown Commit Outcomes

If the connection drops right after the client sends `COMMIT`, the client may not know whether the commit succeeded. Never assume a rollback occurred. Inspect batch ID, source keys, and checkpoints in the database before resending.

## 21. Count Reconciliation

Count reconciliation is foundational, but every query must use the exact same data scope and batch ID.

### 21.1. Source/Staging Count

~~~sql
SELECT COUNT(*) AS staged_rows
FROM stg_order
WHERE batch_id = :batch_id;
~~~

### 21.2. Accepted Count

~~~sql
SELECT COUNT(*) AS valid_rows
FROM stg_order_valid
WHERE batch_id = :batch_id;
~~~

### 21.3. Rejected Row Count

If a single row can have multiple reject reasons, count distinct source rows:

~~~sql
SELECT COUNT(DISTINCT source_row_no) AS rejected_rows
FROM load_reject
WHERE batch_id = :batch_id;
~~~

If you need total error count, use `COUNT(*)` and label it clearly as reject reasons or error records.

### 21.4. Target Count by Batch

~~~sql
SELECT COUNT(*) AS target_rows
FROM app_order
WHERE load_batch_id = :batch_id;
~~~

This requires storing `load_batch_id` on the target or maintaining a batch mapping table.

### 21.5. Control Equations

When every staged record receives a single terminal status:

~~~text
STAGED_ROWS = VALID_ROWS + REJECTED_ROWS
~~~

When separate duplicate/ignored/deferred statuses exist:

~~~text
STAGED_ROWS =
    INSERTED_ROWS
  + UPDATED_ROWS
  + UNCHANGED_ROWS
  + REJECTED_ROWS
  + DUPLICATE_IGNORED_ROWS
  + DEFERRED_ROWS
~~~

Categories must be mutually exclusive so no row is double-counted.

## 22. Amount and Aggregate Reconciliation

When data contains amounts, quantities, or balances, compare aggregates across source, accepted staging, and target.

### 22.1. Total Amount in Accepted Staging

~~~sql
SELECT
    COUNT(*) AS row_count,
    SUM(amount) AS total_amount,
    MIN(order_date) AS min_order_date,
    MAX(order_date) AS max_order_date
FROM stg_order_valid
WHERE batch_id = :batch_id;
~~~

### 22.2. Total Amount in Target

~~~sql
SELECT
    COUNT(*) AS row_count,
    SUM(amount) AS total_amount,
    MIN(order_date) AS min_order_date,
    MAX(order_date) AS max_order_date
FROM app_order
WHERE load_batch_id = :batch_id;
~~~

### 22.3. Grouping by Currency

Never sum different currencies directly:

~~~sql
SELECT
    currency_code,
    COUNT(*) AS row_count,
    SUM(amount) AS total_amount
FROM app_order
WHERE load_batch_id = :batch_id
GROUP BY currency_code
ORDER BY currency_code;
~~~

Reconcile per currency to avoid meaningless totals mixing VND, USD, and EUR.

### 22.4. Aggregates Do Not Prove Every Row Matches

Two datasets can share identical counts and sums while containing different records. Aggregates are a fast check; follow up with key-level reconciliation.

## 23. Business-Key Reconciliation

### 23.1. Present in Source, Missing in Target

~~~sql
SELECT
    s.order_id,
    s.source_row_no
FROM stg_order_valid s
LEFT JOIN app_order t
  ON t.order_id = s.order_id
 AND t.load_batch_id = s.batch_id
WHERE s.batch_id = :batch_id
  AND t.order_id IS NULL;
~~~

These are source rows not yet found in the target under the mapping join above.

### 23.2. Present in Target, Missing in Source

~~~sql
SELECT
    t.order_id
FROM app_order t
LEFT JOIN stg_order_valid s
  ON s.order_id = t.order_id
 AND s.batch_id = t.load_batch_id
WHERE t.load_batch_id = :batch_id
  AND s.order_id IS NULL;
~~~

### 23.3. Same Key, Differing Values

~~~sql
SELECT
    s.order_id,
    s.amount AS source_amount,
    t.amount AS target_amount,
    s.currency_code AS source_currency,
    t.currency_code AS target_currency
FROM stg_order_valid s
JOIN app_order t
  ON t.order_id = s.order_id
 AND t.load_batch_id = s.batch_id
WHERE s.batch_id = :batch_id
  AND (
      NVL(s.amount, -1) <> NVL(t.amount, -1)
      OR NVL(s.currency_code, '???') <> NVL(t.currency_code, '???')
  );
~~~

Choose `NVL` sentinels that cannot collide with valid data. For complex types or strict null semantics, write explicit null-safe comparisons.

### 23.4. Using FULL OUTER JOIN

A `FULL OUTER JOIN` can classify rows into:

- `SOURCE_ONLY`.
- `TARGET_ONLY`.
- `MATCHED_EQUAL`.
- `MATCHED_DIFFERENT`.

This is useful when generating detailed reconciliation audit outputs.

## 24. Hashes, Checksums, and Fingerprints

Checksums serve multiple layers:

- File checksums to verify input files.
- Row fingerprints to compare individual records.
- Partition/batch aggregate fingerprints for rapid discrepancy detection.

### 24.1. File Checksum

Compute SHA-256 at the landing layer and persist it in `load_batch`. If a file is altered, its checksum changes.

### 24.2. Row Fingerprint

Compute a hash over canonicalized fields:

~~~sql
SELECT
    order_id,
    STANDARD_HASH(
        NVL(TO_CHAR(customer_id), '#NULL#') || '|' ||
        NVL(TO_CHAR(order_date, 'YYYY-MM-DD'), '#NULL#') || '|' ||
        NVL(TO_CHAR(amount, 'FM9999999999990D00',
                    'NLS_NUMERIC_CHARACTERS=''.,'''), '#NULL#') || '|' ||
        NVL(currency_code, '#NULL#'),
        'SHA256'
    ) AS row_hash
FROM stg_order_valid
WHERE batch_id = :batch_id;
~~~

Canonicalization must standardize:

- Field order.
- Character encoding.
- Date/time zones and formats.
- Decimal separators and scale.
- Null representation.
- Whitespace and case normalization.

Without identical canonicalization, equivalent business values can yield different hashes.

### 24.3. Hashes Do Not Replace Field-Level Comparison

Hashes accelerate detection but do not identify which column differs. When a mismatch appears, run key-level comparison and export differing columns for investigation.

### 24.4. Aggregate Hashes

You can compute fingerprints per partition or batch, though never combine hashes arbitrarily and treat them as absolute mathematical proof. Choose a well-defined algorithm and canonicalization scheme and record its version.

## 25. Reconciliation Report

A reconciliation report should include both summary and detail sections.

### 25.1. Summary

| Metric | Meaning |
| --- | --- |
| Expected rows | Row count per manifest/source |
| Staged rows | Rows loaded into staging |
| Valid rows | Rows passing validation |
| Rejected rows | Rows rejected |
| Inserted rows | New rows inserted |
| Updated rows | Existing rows updated |
| Unchanged rows | Rows unchanged per policy |
| Target rows | Target rows tagged with batch |
| Missing rows | Present in source, missing in target |
| Extra rows | Present in target, absent from source |
| Mismatched rows | Same key, differing values |
| Amount variance | Difference in total amount |

### 25.2. Detail

Every mismatch should include:

- Batch ID.
- Source record ID / row number.
- Business key.
- Field name.
- Source value.
- Target value.
- Difference / reason.
- Severity.
- Resolution status.

### 25.3. Example Report SQL

~~~sql
SELECT
    b.batch_id,
    b.expected_rows,
    (SELECT COUNT(*)
       FROM stg_order s
      WHERE s.batch_id = b.batch_id) AS staged_rows,
    (SELECT COUNT(*)
       FROM stg_order_valid v
      WHERE v.batch_id = b.batch_id) AS valid_rows,
    (SELECT COUNT(DISTINCT r.source_row_no)
       FROM load_reject r
      WHERE r.batch_id = b.batch_id) AS rejected_rows,
    (SELECT COUNT(*)
       FROM app_order t
      WHERE t.load_batch_id = b.batch_id) AS target_rows,
    b.batch_status
FROM load_batch b
WHERE b.batch_id = :batch_id;
~~~

When multiple reject categories exist, ensure multiple error reasons on one row do not inflate rejected-row counts in the summary.

## 26. Tiered Error Handling and Retries

### 26.1. File-Level Rejects

Examples:

- Missing mandatory header.
- Invalid character encoding.
- Wrong column count structure.
- Checksum mismatch against manifest.
- Truncated file or missing trailer.

A file-level reject can fail the entire batch before creating staging rows.

### 26.2. Record-Level Rejects

Examples:

- Unparseable amount on a record.
- Customer ID does not exist.
- Duplicate business key.

Can be written to the reject table while continuing with remaining rows if policy permits.

### 26.3. Chunk-Level Failures

Examples:

- Deadlock.
- Tablespace full.
- Network interruption.
- Statement timeout.

Roll back the active chunk if the transaction is still open. Determine the commit outcome before retrying.

### 26.4. Job-Level Failures

Examples:

- Database outage.
- Insufficient privileges.
- Broken schema mapping.
- Missing dependent service.
- File store unavailable.

Halt the job and preserve staging, logs, and checkpoints for investigation. Do not mark remaining rows as bad data.

### 26.5. Retry Policy

| Error | Retry? | Handling |
| --- | --- | --- |
| Temporary network error | Conditional | Exponential backoff, verify commit outcome |
| Deadlock | Conditional | Roll back transaction, retry business unit |
| Invalid date | Do not auto-retry | Fix source data or mapping |
| Missing customer | Per business policy | Wait for master data or reject |
| Duplicate source ID | Never blindly | Reconcile idempotency key |
| Tablespace full | Not immediately | DBA resolves capacity before resuming |
| Invalid SQL/privilege | No | Fix code, config, or permissions |

### 26.6. Bounded Retries

Track:

- Attempt number.
- Last error.
- Next retry timestamp.
- Backoff duration.
- Maximum attempts.
- Final status.

Never retry infinitely in a tight loop.

## 27. Performance and Operations

### 27.1. Reducing Round Trips

In Java, use `PreparedStatement` batching. For data already in Oracle, use set-based SQL. For large files, benchmark SQL*Loader and external tables.

### 27.2. Choosing Appropriate Indexes

Indexes accelerate validation and reconciliation but add overhead to inserts and updates. Evaluate:

- Indexes required for uniqueness and integrity.
- Indexes supporting staging queries.
- Indexes that can be built post-load in suitable environments.
- Global vs. local indexes with partitioning.

Never drop unique or business constraints purely for speed without an equivalent enforcement mechanism.

### 27.3. Statistics

After a bulk load, optimizer statistics may need refreshing so cardinality estimates remain accurate.

~~~sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname => USER,
        tabname => 'APP_ORDER',
        cascade => TRUE
    );
END;
/
~~~

In production, specify the proper owner, appropriate estimate/sample settings, partition-level strategies, and maintenance windows. Do not gather full stats on massive tables after every small chunk.

### 27.4. Undo and Redo

DML generates undo and redo according to database configuration. Oversized chunks increase undo pressure and rollback time. Direct path and `NOLOGGING` carry specific recovery semantics that the DBA must evaluate.

### 27.5. Parallel Execution

Parallel loads can boost throughput while increasing:

- CPU and I/O consumption.
- `TEMP` space usage.
- Contention across concurrent workloads.
- Contention on target tables and indexes.
- Transaction and recovery complexity.

Enable parallelism only after benchmarking workload and resource limits. Verify the actual degree of parallelism (DOP) rather than assuming hints are always honored.

### 27.6. Monitoring

Track at minimum:

- Batch ID.
- File name and checksum.
- Start and end timestamps.
- Rows read, staged, valid, rejected, and applied.
- Throughput.
- Chunk and commit counts.
- Error counts by error code.
- Retry counts.
- Reconciliation status.

## 28. Integrated Hands-On Lab

This lab simulates loading orders into Oracle using staging-first, validation, reject rows, apply, and reconciliation.

### Step 1 — Create Target Table

~~~sql
CREATE TABLE app_order_lab (
    order_id          NUMBER PRIMARY KEY,
    customer_id       NUMBER NOT NULL,
    order_date        DATE NOT NULL,
    amount            NUMBER(15,2) NOT NULL,
    currency_code     VARCHAR2(3) NOT NULL,
    source_record_id  VARCHAR2(100) NOT NULL,
    load_batch_id     VARCHAR2(40) NOT NULL,
    CONSTRAINT uq_order_lab_source
        UNIQUE (source_record_id)
);
~~~

### Step 2 — Create Batch, Staging, and Reject Tables

~~~sql
CREATE TABLE load_batch_lab (
    batch_id       VARCHAR2(40) PRIMARY KEY,
    expected_rows  NUMBER,
    batch_status   VARCHAR2(20),
    created_at     TIMESTAMP DEFAULT SYSTIMESTAMP
);

CREATE TABLE stg_order_lab (
    batch_id          VARCHAR2(40) NOT NULL,
    source_row_no     NUMBER NOT NULL,
    source_record_id  VARCHAR2(100),
    order_id_raw      VARCHAR2(100),
    customer_id_raw   VARCHAR2(100),
    order_date_raw    VARCHAR2(100),
    amount_raw        VARCHAR2(100),
    currency_raw      VARCHAR2(20),
    CONSTRAINT pk_stg_order_lab
        PRIMARY KEY (batch_id, source_row_no)
);

CREATE TABLE reject_order_lab (
    batch_id       VARCHAR2(40),
    source_row_no  NUMBER,
    error_code     VARCHAR2(100),
    error_message  VARCHAR2(1000),
    raw_order_id   VARCHAR2(100),
    raw_amount     VARCHAR2(100),
    rejected_at    TIMESTAMP DEFAULT SYSTIMESTAMP
);
~~~

### Step 3 — Create Batch Record

~~~sql
INSERT INTO load_batch_lab(batch_id, expected_rows, batch_status)
VALUES ('LAB-001', 5, 'RECEIVED');

COMMIT;
~~~

### Step 4 — Load Raw Rows

~~~sql
INSERT INTO stg_order_lab (
    batch_id, source_row_no, source_record_id,
    order_id_raw, customer_id_raw, order_date_raw,
    amount_raw, currency_raw
)
VALUES ('LAB-001', 1, 'SRC-001', '1001', '501', '2026-11-01', '125.50', 'VND');

INSERT INTO stg_order_lab VALUES (
    'LAB-001', 2, 'SRC-002', '1002', '502', '2026-11-02', '240.00', 'VND'
);

INSERT INTO stg_order_lab VALUES (
    'LAB-001', 3, 'SRC-003', '1003', '503', '2026-11-03', 'INVALID', 'VND'
);

INSERT INTO stg_order_lab VALUES (
    'LAB-001', 4, 'SRC-004', '1004', '504', '2026-11-04', '-10.00', 'VND'
);

INSERT INTO stg_order_lab VALUES (
    'LAB-001', 5, 'SRC-005', '1005', '505', 'BAD-DATE', '99.00', 'VND'
);

COMMIT;
~~~

### Step 5 — Validate

~~~sql
INSERT INTO reject_order_lab (
    batch_id, source_row_no, error_code,
    error_message, raw_order_id, raw_amount
)
SELECT
    batch_id,
    source_row_no,
    CASE
        WHEN VALIDATE_CONVERSION(order_id_raw AS NUMBER) = 0
            THEN 'INVALID_ORDER_ID'
        WHEN VALIDATE_CONVERSION(order_date_raw AS DATE, 'YYYY-MM-DD') = 0
            THEN 'INVALID_ORDER_DATE'
        WHEN VALIDATE_CONVERSION(amount_raw AS NUMBER) = 0
            THEN 'INVALID_AMOUNT'
        WHEN TO_NUMBER(amount_raw DEFAULT NULL ON CONVERSION ERROR) < 0
            THEN 'NEGATIVE_AMOUNT'
        ELSE 'OTHER'
    END,
    'Validation failed',
    order_id_raw,
    amount_raw
FROM stg_order_lab
WHERE batch_id = 'LAB-001'
  AND (
      VALIDATE_CONVERSION(order_id_raw AS NUMBER) = 0
      OR VALIDATE_CONVERSION(order_date_raw AS DATE, 'YYYY-MM-DD') = 0
      OR VALIDATE_CONVERSION(amount_raw AS NUMBER) = 0
      OR (
          VALIDATE_CONVERSION(amount_raw AS NUMBER) = 1
          AND TO_NUMBER(amount_raw) < 0
      )
  );
~~~

The lab snippet uses `DEFAULT NULL ON CONVERSION ERROR`, available in supporting Oracle releases. You can remove that branch and rely solely on `VALIDATE_CONVERSION` if targeting older releases.

### Step 6 — Load Accepted Rows

~~~sql
INSERT INTO app_order_lab (
    order_id,
    customer_id,
    order_date,
    amount,
    currency_code,
    source_record_id,
    load_batch_id
)
SELECT
    TO_NUMBER(order_id_raw),
    TO_NUMBER(customer_id_raw),
    TO_DATE(order_date_raw, 'YYYY-MM-DD'),
    TO_NUMBER(amount_raw),
    currency_raw,
    source_record_id,
    batch_id
FROM stg_order_lab s
WHERE batch_id = 'LAB-001'
  AND NOT EXISTS (
      SELECT 1
      FROM reject_order_lab r
      WHERE r.batch_id = s.batch_id
        AND r.source_row_no = s.source_row_no
  );

COMMIT;
~~~

### Step 7 — Reconcile Counts

~~~sql
SELECT COUNT(*) AS staged_rows
FROM stg_order_lab
WHERE batch_id = 'LAB-001';

SELECT COUNT(DISTINCT source_row_no) AS rejected_rows
FROM reject_order_lab
WHERE batch_id = 'LAB-001';

SELECT COUNT(*) AS target_rows
FROM app_order_lab
WHERE load_batch_id = 'LAB-001';
~~~

### Step 8 — Reconcile Amounts

~~~sql
SELECT
    currency_code,
    COUNT(*) AS row_count,
    SUM(amount) AS total_amount
FROM app_order_lab
WHERE load_batch_id = 'LAB-001'
GROUP BY currency_code;
~~~

### Step 9 — Check Source Rows Missing from Target

~~~sql
SELECT s.source_row_no, s.source_record_id, s.order_id_raw
FROM stg_order_lab s
LEFT JOIN app_order_lab t
  ON t.source_record_id = s.source_record_id
WHERE s.batch_id = 'LAB-001'
  AND t.source_record_id IS NULL;
~~~

### Step 10 — Rerun the Batch

Try rerunning the accepted `INSERT`. The unique constraint on `source_record_id` prevents duplicates. Afterward, design `MERGE` or skip logic per your idempotency policy rather than catching and ignoring errors.

## 29. Common Bulk-Load Errors

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| SQL*Loader rows rejected | Format, conversion, or constraint error | Inspect log and bad file by source record |
| SQL*Loader rows discarded | Failed `WHEN`/discard predicate | Check control file and discard file |
| External table query error | `DIRECTORY`/file permission/format issue | Check DB server path, grants, access parameters |
| `ORA-01722` | Invalid number | Validate conversion and NLS settings |
| `ORA-01861`/`01843` | Invalid date format or month | Use explicit format masks |
| `ORA-00001` | Duplicate key | Check source keys and unique constraints |
| `ORA-02291` | Parent key not found | Verify load order and reference data |
| `ORA-12838` | Accessing modified object after direct/parallel DML before commit | Place commit boundaries per applicable restrictions |
| `ORA-01555` | Insufficient undo for long consistent read | Tune queries, transactions, and undo retention |
| `ORA-01653` | Unable to extend table segment | DBA checks tablespace/datafiles |
| `ORA-01654` | Unable to extend index segment | Check index tablespace |
| `ORA-00060` | Deadlock | Standardize lock ordering and transaction scope |
| `BatchUpdateException` | One or more JDBC batch operations failed | Inspect update counts and driver behavior |
| `ORA-24381` | `FORALL SAVE EXCEPTIONS` encountered iteration errors | Inspect `SQL%BULK_EXCEPTIONS` |
| DML error log missing rows | Unloggable error type or statement-level failure | Review Oracle restrictions and statement error |
| Source/target counts mismatch | Wrong batch scope, duplicates, rejects, or uncommitted data | Reconcile by batch and source key |
| Retry creates duplicates | Missing idempotency/checkpoints | Enforce unique business keys and verify commit outcomes |

## 30. Batch Operations Checklist

**Source and Lineage**

- Unique batch ID assigned?
- File checksum and source row count recorded?
- Source record ID / row number captured?
- Original file preserved immutably?
- Mapping/rule version recorded?

**Staging and Validation**

- Raw values preserved?
- Batch ID filtered in every query?
- Conversions use explicit format masks and NLS settings?
- Validation uses stable error codes?
- Can one row have multiple reject reasons?
- Are duplicates handled per business rules?

**Apply**

- Right choice among SQL*Loader, external table, set-based SQL, JDBC, or `FORALL`?
- Direct-path restrictions checked?
- Unique constraints protecting business keys?
- Does DML error logging cover the expected error types?
- Batch, chunk, and transaction sizes benchmarked?

**Recovery**

- Per-chunk checkpoints present?
- Idempotency enforced?
- Unknown commit outcomes handled?
- Retries bounded with backoff?
- Row-level errors separated from system-level errors?

**Reconciliation**

- Source/staging/valid/rejected counts match?
- Inserted/updated/unchanged counts separated clearly?
- Aggregates compared by currency/date/partition?
- Key-level anti-join executed?
- Field-level mismatch checks run?
- Batch marked `COMPLETED` only after reconciliation passes?

## 31. Self-Check Questions

1. Why does bulk loading need staging?
2. What is a batch ID used for?
3. What role does the source row number play?
4. How does SQL*Loader conventional path differ from direct path?
5. How does a bad file differ from a discard file?
6. Where does an external table store file data?
7. Which machine's filesystem does a `DIRECTORY` object point to?
8. Why should raw staging store values as text?
9. What problem does `VALIDATE_CONVERSION` solve?
10. Why should you not rely on default `NLS_DATE_FORMAT`?
11. How does structural validation differ from business validation?
12. Why does a duplicate pre-check not replace a unique constraint?
13. When should you use `INSERT ... SELECT`?
14. When should you use `MERGE`?
15. Why must a `MERGE` source be deduplicated?
16. How does the `APPEND` hint relate to direct-path insert?
17. When can `ORA-12838` occur?
18. Why does `NOLOGGING` require DBA recovery review?
19. What does `DBMS_ERRLOG.CREATE_ERROR_LOG` create?
20. What are `ORA_ERR_NUMBER$` and `ORA_ERR_TAG$` used for?
21. How do `LOG ERRORS` and `REJECT LIMIT` work together?
22. Does DML error logging capture every error?
23. Why does an error logging table not replace a business reject table?
24. What overhead does `FORALL` reduce?
25. How does `SAVE EXCEPTIONS` handle iteration errors?
26. What is `SQL%BULK_EXCEPTIONS.ERROR_INDEX`?
27. How does batch size differ from transaction chunk size?
28. How does atomic file processing differ from partial acceptance?
29. Why can retrying an entire file create duplicates?
30. What should an idempotency key be based on?
31. What is an unknown commit outcome?
32. Why must counts be reconciled by batch ID?
33. Why do identical counts and `SUM`s not prove two row sets are identical?
34. What must a row fingerprint canonicalize?
35. When is a batch allowed to transition to `COMPLETED`?

**Suggested Answers:**

1. Keeps raw input, lineage, validation, and recovery isolated from the target table.
2. Identifies a single data receipt/processing run.
3. Traces records and maps errors back to the exact source position.
4. Conventional uses the SQL `INSERT` interface; direct path writes directly to data blocks with specific restrictions.
5. Bad records fail to load due to errors; discarded records are filtered out by control-file conditions.
6. Data remains in the file; the external table provides a SQL interface to read it.
7. The database server's filesystem.
8. Preserves exact source representations and allows controlled conversion afterward.
9. Checks whether an expression can convert to the target data type.
10. Because results depend on session/environment settings and can cause mis-parsing.
11. Structural checks verify format/shape; business validation checks domain and business rules.
12. Because race conditions can occur between the pre-check and the insert.
13. When the source data is already in the database and can be processed set-based.
14. When you need to update existing rows and insert new rows by key.
15. A target row must not be matched by multiple source rows in the same `MERGE`.
16. `APPEND` requests direct-path insert when conditions allow.
17. When accessing an object modified by direct/parallel DML before commit under applicable restrictions.
18. Because redo, recovery, and backup behavior can change.
19. Creates an error logging table for a target DML table.
20. The Oracle error number and the batch/application tag.
21. Logs supported row errors into the error table and caps tolerated errors before aborting the statement.
22. No.
23. It does not automatically track full business lineage, reasons, or retry workflows.
24. Per-row SQL/PLSQL context switches.
25. Continues remaining iterations, then raises `ORA-24381` to report saved errors.
26. The index of the failing iteration in `FORALL`.
27. Batch size is statements per execution round trip; transaction chunk size is rows committed per transaction.
28. Atomic rolls back the entire unit; partial acceptance commits valid rows and isolates rejects.
29. Because earlier chunks or records may have already committed.
30. Source system + source record ID or a stable business key.
31. The client does not know whether `COMMIT` succeeded after losing the connection.
32. To avoid mixing data across different runs.
33. Two datasets can share identical aggregates while containing different rows.
34. Field order, nulls, encoding, date/time, decimals, and whitespace/casing.
35. When apply, transactions/checkpoints, and reconciliation all satisfy policy.

## Oracle Reference Documentation

- [Oracle Database 19c Utilities — SQL*Loader](https://docs.oracle.com/en/database/oracle/oracle-database/19/sutil/oracle-sql-loader.html): conventional/direct path, control files, log/bad/discard files, and load options.
- [Oracle Database 19c Utilities — External Tables](https://docs.oracle.com/en/database/oracle/oracle-database/19/sutil/oracle-external-tables.html): `ORACLE_LOADER`, `DIRECTORY`, access parameters, and reject limits.
- [Oracle Database 19c PL/SQL Packages and Types Reference — DBMS_ERRLOG](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_ERRLOG.html): creating error logging tables.
- [Oracle Database 19c SQL Language Reference — INSERT](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/INSERT.html): `INSERT`, direct-path insert, and error logging clause.
- [Oracle Database 19c SQL Language Reference — MERGE](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/MERGE.html): upsert semantics and error logging.
- [Oracle Database 19c PL/SQL Language Reference — Bulk SQL and Bulk Binding](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/bulk-sql-and-bulk-binding.html): `FORALL`, `SAVE EXCEPTIONS`, `SQL%BULK_EXCEPTIONS`, and `SQL%BULK_ROWCOUNT`.
- [Oracle Database 19c SQL Language Reference — VALIDATE_CONVERSION](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/VALIDATE_CONVERSION.html): checking data conversion validity.
- [Oracle Database 19c SQL Language Reference — STANDARD_HASH](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/STANDARD_HASH.html): computing hashes/fingerprints from expressions.
- [Oracle Database 19c Administrator's Guide — Managing Tables](https://docs.oracle.com/en/database/oracle/oracle-database/19/admin/managing-tables.html): managing tables, partitions, and bulk data operations.

**Key Principle to Remember:** Bulk data loading should begin with staging carrying a batch ID and source lineage. Validate before applying, separate row-level rejects from system errors, and pick the right mechanism: SQL*Loader/external tables for files, set-based SQL for data inside Oracle, JDBC batching for Java sources, and `FORALL` for PL/SQL collections. DML error logging preserves many row-level errors but does not handle every error type. Define transaction chunks, checkpoints, and idempotency before running in production. Only mark a batch complete once counts, aggregates, and key-level reconciliation all pass.
