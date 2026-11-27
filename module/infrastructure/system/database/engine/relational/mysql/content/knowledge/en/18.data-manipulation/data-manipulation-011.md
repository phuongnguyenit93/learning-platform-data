# Safely Re-Executable Batch Data Loading and Modification

In the DATABASE_MYSQL module, data loading and modification workflows must coordinate table design, data types, keys, constraints, transactions, and concurrency control. A data ingestion pipeline must tolerate timeouts, dropped connections, and retries. Idempotency guarantees that re-running the same batch does not create duplicate records, apply deltas twice, or overwrite newer versions with older data.

## 1. What Is Idempotency in Data Operations?

An idempotent operation can be executed multiple times with the same request while leaving the final state identical to executing it once. For example, loading a customer with source code C-100 for the first time creates one row; re-running the same batch lets the database recognize that C-100 already exists and either update with the same data or take no action. The system neither creates a second customer row nor reapplies an additive change.

Idempotency matters when applications retry after timeouts, scheduled jobs re-run after deployments, operators restart an interrupted batch, or multiple workers receive the same message.

Not every SQL statement run twice is idempotent:

~~~sql
-- Not idempotent: every re-run adds another 10
UPDATE inventory
SET quantity = quantity + 10
WHERE product_id = 1001;

-- Can be idempotent if the input value is an absolute state
UPDATE inventory
SET quantity = 50
WHERE product_id = 1001;
~~~

The first statement expresses an incremental delta. If the same command is retried, quantity gets added multiple times. The second statement expresses a target state; re-running with the same value makes no further change to quantity.

## 2. Defining Business Keys Before Loading Data

An import workflow must know which record in the target table corresponds to a source record. Do not rely solely on a SELECT check before INSERT, because two workers can both see no existing row and both attempt to insert.

Use a stable business key, such as a customer ID from the source system:

~~~sql
CREATE TABLE customers (
    customer_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    external_id VARCHAR(64) NOT NULL,
    email VARCHAR(255) NULL,
    full_name VARCHAR(150) NOT NULL,
    source_version BIGINT UNSIGNED NOT NULL,
    created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (customer_id),
    UNIQUE KEY uq_customers_external_id (external_id)
) ENGINE=InnoDB;
~~~

The UNIQUE constraint on external_id serves as the final safeguard against duplicate records. Even if two requests arrive concurrently, the database will not allow two rows with the same source code.

An idempotency key should stay stable between the initial run and retries, represent the same business entity or request, avoid depending on line numbers if file ordering can change, and be enforced by a PRIMARY KEY or UNIQUE constraint in the database.

Do not use email as the business key if email addresses can change or be shared. When a customer has a dedicated source ID, use that ID. For composite keys, declare all components in a single unique index.

## 3. Distinguishing Record Keys from Batch Keys

A batch loading pipeline typically requires two types of identifiers:

| Identifier | Scope | Purpose |
|---|---|---|
| Business key | A single entity, e.g., external_id | Identifies a record for insert or update |
| Batch key / idempotency key | One logical data delivery, e.g., source + version or file checksum | Identifies a load run so retries do not reprocess it |

The batch ID must be generated and persisted before processing starts, then kept unchanged across every retry. If each retry generates a new UUID, the database treats it as a brand-new batch and cannot recognize the previous request.

## 4. Tracking Batch State with a Ledger Table

Create a table to track batch history:

~~~sql
CREATE TABLE import_batches (
    batch_id VARCHAR(100) NOT NULL,
    source_name VARCHAR(100) NOT NULL,
    source_version VARCHAR(100) NOT NULL,
    content_sha256 CHAR(64) NOT NULL,
    status ENUM('LOADING', 'READY', 'COMPLETED', 'FAILED') NOT NULL,
    expected_rows BIGINT UNSIGNED NULL,
    staged_rows BIGINT UNSIGNED NULL,
    processed_rows BIGINT UNSIGNED NULL,
    started_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    completed_at TIMESTAMP(6) NULL,
    PRIMARY KEY (batch_id),
    UNIQUE KEY uq_import_source_version (source_name, source_version)
) ENGINE=InnoDB;
~~~

Meaning of the fields:

- batch_id is the stable idempotency key.
- source_name and source_version identify the source along with its data version.
- content_sha256 detects cases where the same source version has modified file contents.
- status indicates whether the batch is loading, ready to merge, completed, or failed.
- expected_rows is the expected source row count; staged_rows is the count loaded and normalized; processed_rows is the count merged or marked processed.

Register the batch before loading the file using the determined batch key:

~~~sql
INSERT INTO import_batches (
    batch_id,
    source_name,
    source_version,
    content_sha256,
    status,
    expected_rows
)
VALUES (
    'customers-2026-11-v1',
    'crm',
    'v1',
    '0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef',
    'LOADING',
    10000
);
~~~

If the INSERT hits a duplicate because the batch is already registered, read the existing ledger row and compare checksum, source version, and status. Do not change batch_id to dodge the conflict; the same source key with a different checksum must be treated as a data conflict.

The checksum string in the example is illustrative; the application must compute SHA-256 from the actual file contents and store that exact digest.

When a batch is already COMPLETED, a retry should read the ledger and return the completed result instead of merging again. If the same source/version has a different checksum, halt and investigate; never silently treat it as the same batch.

Do not track completion flags solely in the application. Update the COMPLETED status in the same transaction as the target table changes so ledger state and table data never drift apart.

## 5. Using Staging Tables to Separate Loading from Applying

For large files or multi-source data, do not load directly into business tables. Use a staging table to ingest, validate, normalize, and filter out bad records before merging:

~~~sql
CREATE TABLE customer_stage (
    batch_id VARCHAR(100) NOT NULL,
    external_id VARCHAR(64) NOT NULL,
    email VARCHAR(255) NULL,
    full_name VARCHAR(150) NOT NULL,
    source_version BIGINT UNSIGNED NOT NULL,
    PRIMARY KEY (batch_id, external_id)
) ENGINE=InnoDB;
~~~

The composite primary key ensures each batch holds at most one row per external_id. If a file contains two rows with the same external_id, the load step detects the conflict instead of arbitrarily picking one row. If a valid source permits multiple changes for the same customer in one file, define a deterministic winner rule before merging, such as the latest source version plus a stable tie-breaker.

Staging helps validate data types and required fields, detect duplicates, count valid vs. rejected rows, verify checksums, and re-run the merge step without re-reading the external source.

Do not use staging tables as long-term sources for business applications. Merge only after the batch passes validation.

## 6. Loading Files with LOAD DATA

MySQL supports LOAD DATA for loading delimited text files. It is typically far more efficient than many individual INSERT statements when importing large CSVs.

~~~sql
LOAD DATA LOCAL INFILE '/client/import/customers.csv'
INTO TABLE customer_stage
CHARACTER SET utf8mb4
FIELDS TERMINATED BY ','
ENCLOSED BY '"'
LINES TERMINATED BY '\n'
IGNORE 1 LINES
(external_id, email, full_name, source_version)
SET batch_id = 'customers-2026-11-v1';
~~~

The file path in LOAD DATA LOCAL INFILE is read from the connected client machine. With LOAD DATA INFILE without LOCAL, the file is read from the MySQL server host and is governed by `secure_file_priv` and the FILE privilege. LOCAL must be permitted on both client and server per deployment configuration.

Before running, verify the file comes from a trusted source and matches the intended batch; confirm encoding, delimiters, quote characters, and line endings match the actual file; handle NULLs, empty strings, and embedded newlines inside quoted fields; ensure staging has constraints to catch duplicate or missing data; and inspect LOAD DATA results and warnings before merging.

The example uses LF line endings. If the file was created on Windows with CRLF, declare `LINES TERMINATED BY '\r\n'`. Enable LOCAL INFILE only for trusted clients, servers, and sources per deployment security policy; do not enable it broadly if applications do not need it.

If re-loading the same batch into staging with primary key `(batch_id, external_id)`, existing keys will conflict. You can delete staging data for that specific batch and reload from the verified file, or design a raw staging table with a stable `source_row_id` to identify every line. Do not add IGNORE blindly, as it can mask unexpected data errors.

With a dedicated import staging table, you can clear only an unmerged batch before reloading:

~~~sql
DELETE FROM customer_stage
WHERE batch_id = 'customers-2026-11-v1';
~~~

Delete staging data only for a batch in LOADING or FAILED status after verifying the source file. Never delete staging for a batch currently being processed by another worker, and never delete target table data to prepare for a retry.

## 7. Validating and Normalizing Staging Before Merge

Count rows in the batch:

~~~sql
SELECT COUNT(*) AS staged_rows
FROM customer_stage
WHERE batch_id = 'customers-2026-11-v1';
~~~

Check for missing or invalid values:

~~~sql
SELECT external_id, full_name
FROM customer_stage
WHERE batch_id = 'customers-2026-11-v1'
  AND (
      external_id = ''
      OR full_name = ''
  );
~~~

Check the source version range:

~~~sql
SELECT
    MIN(source_version) AS min_version,
    MAX(source_version) AS max_version
FROM customer_stage
WHERE batch_id = 'customers-2026-11-v1';
~~~

If the source can send duplicate business keys, establish a deduplication rule. For example, select the latest version and use `source_row_id` as the tie-breaker:

~~~sql
WITH ranked_source AS (
    SELECT
        s.*,
        ROW_NUMBER() OVER (
            PARTITION BY external_id
            ORDER BY source_version DESC, source_row_id DESC
        ) AS rn
    FROM customer_stage_raw AS s
    WHERE batch_id = 'customers-2026-11-v1'
)
SELECT external_id, email, full_name, source_version
FROM ranked_source
WHERE rn = 1;
~~~

This snippet uses a raw staging table with a unique, stable `source_row_id` column. Never pick an arbitrary row with ANY_VALUE or depend on physical file order; deduplication rules must deterministically identify the winning record.

Transition the batch to READY only after the entire file is loaded and validation completes:

~~~sql
UPDATE import_batches
SET
    status = 'READY',
    staged_rows = (
        SELECT COUNT(*)
        FROM customer_stage
        WHERE batch_id = 'customers-2026-11-v1'
    )
WHERE batch_id = 'customers-2026-11-v1'
  AND status = 'LOADING'
  AND (
      expected_rows IS NULL
      OR expected_rows = (
          SELECT COUNT(*)
          FROM customer_stage
          WHERE batch_id = 'customers-2026-11-v1'
      )
  );
~~~

The application must confirm that exactly one row transitioned to READY and that staged_rows matches expected_rows if the source declared a row count. If validation fails, keep the batch in LOADING or mark it FAILED per workflow rules; never merge unverified partial data.

## 8. Upsert with INSERT ... ON DUPLICATE KEY UPDATE

Upsert combines insert and update: if the primary key or unique key does not exist yet, MySQL inserts the row; on key conflict, MySQL executes the update branch.

~~~sql
CREATE TABLE inventory (
    product_id BIGINT UNSIGNED NOT NULL,
    quantity INT UNSIGNED NOT NULL,
    source_version BIGINT UNSIGNED NOT NULL,
    PRIMARY KEY (product_id)
) ENGINE=InnoDB;

INSERT INTO inventory (product_id, quantity, source_version)
VALUES
    (101, 20, 5),
    (102, 10, 7) AS incoming
ON DUPLICATE KEY UPDATE
    quantity = IF(
        incoming.source_version > inventory.source_version,
        incoming.quantity,
        inventory.quantity
    ),
    source_version = GREATEST(
        inventory.source_version,
        incoming.source_version
    );
~~~

In MySQL 8.0.19 and later, a row alias after the VALUES list lets you reference incoming values as `incoming`. This avoids the `VALUES(column)` function, which was deprecated starting in MySQL 8.0.20. On older versions, `VALUES(column)` may still be necessary; check the server version before choosing syntax.

With the version rule in the example:

- If product_id does not exist yet, a row is created with quantity and source_version from the source.
- If the row already exists and the new source_version is greater, the new state is applied.
- If an older batch is re-sent, source_version is not greater, so newer data is not overwritten.
- Re-running the same version and payload does not add quantity again.

Upserts are safe only when business keys and update rules are properly designed. If a row can conflict with multiple different unique indexes, examine it carefully because MySQL triggers the duplicate branch on whichever key conflicts; having multiple unique keys can cause an unintended row to be updated.

## 9. Avoiding Non-Idempotent Updates

Do not use cumulative addition if the same batch can be re-run:

~~~sql
-- Unsafe when retrying the same batch
INSERT INTO inventory (product_id, quantity, source_version)
VALUES (101, 20, 5) AS incoming
ON DUPLICATE KEY UPDATE
    quantity = inventory.quantity + incoming.quantity;
~~~

If executed twice, quantity increases by 40 instead of 20. When source data is a snapshot, assign absolute values guarded by version checks. When source data is a delta, persist applied transaction/event IDs so the same delta is never applied twice.

For event-based data, you can create an inbox/processed_events table:

~~~sql
CREATE TABLE processed_events (
    event_id VARCHAR(100) NOT NULL,
    processed_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (event_id)
) ENGINE=InnoDB;
~~~

Within a single transaction:

1. Insert event_id into processed_events.
2. If the insert succeeds, apply the delta to the business table.
3. If event_id already exists, skip the already-processed event.
4. Commit both the processed marker and the business change together.

If applying the delta fails, rolling back removes both the event marker and the incomplete business change. On retry, the event can be reprocessed safely.

## 10. Merging Staging into the Target Table in One Transaction

Suppose a batch has been loaded into customer_stage, validated, and import_batches is in READY status. You can update existing rows and insert missing rows within a single transaction:

~~~sql
START TRANSACTION;

-- Lock the batch so only one worker merges it at a time.
SELECT status
FROM import_batches
WHERE batch_id = 'customers-2026-11-v1'
FOR UPDATE;

-- Update existing customers, accepting only newer source versions.
UPDATE customers AS c
JOIN customer_stage AS s
  ON s.external_id = c.external_id
SET
    c.email = s.email,
    c.full_name = s.full_name,
    c.source_version = s.source_version,
    c.updated_at = CURRENT_TIMESTAMP(6)
WHERE s.batch_id = 'customers-2026-11-v1'
  AND s.source_version > c.source_version;

-- Insert customers that do not exist yet.
INSERT INTO customers (
    external_id,
    email,
    full_name,
    source_version
)
SELECT
    s.external_id,
    s.email,
    s.full_name,
    s.source_version
FROM customer_stage AS s
LEFT JOIN customers AS c
  ON c.external_id = s.external_id
WHERE s.batch_id = 'customers-2026-11-v1'
  AND c.customer_id IS NULL;

-- Mark completed in the same transaction as target table changes.
UPDATE import_batches
SET
    status = 'COMPLETED',
    processed_rows = (
        SELECT COUNT(*)
        FROM customer_stage
        WHERE batch_id = 'customers-2026-11-v1'
    ),
    completed_at = CURRENT_TIMESTAMP(6)
WHERE batch_id = 'customers-2026-11-v1'
  AND status = 'READY';

COMMIT;
~~~

The application must verify that the ledger row exists and its status is READY before running the merge statements. If status is COMPLETED, exit without merging; if it is LOADING or FAILED, halt and rerun the staging/validation phase. Locking the row with FOR UPDATE serializes batch ownership within the transaction when all workers follow this claiming rule.

The condition `source_version > target.source_version` prevents stale batches from overwriting newer state. This assumes `source_version` increases monotonically per `external_id` and that a given version's payload is immutable. If the same version arrives with a different payload, raise a conflict instead of choosing silently.

On a sequential retry after a successful commit, already-merged rows have `source_version` equal to the source version and are not updated again; already-inserted rows exist and are not re-inserted; and the ledger is already COMPLETED so workers inspect and skip the batch.

In multi-worker systems, ensure only one worker merges a given batch at a time or use a batch claim/lock mechanism. The unique key on `customers` remains the final safeguard. If two different batches concurrently insert the same `external_id`, one transaction may hit a duplicate-key error; roll back and retry under version rules rather than ignoring the error.

If the merge transaction fails before COMMIT, InnoDB rolls back changes to `customers` and the ledger status together. If the client loses its connection right after COMMIT before receiving the acknowledgment, a retry reading the ledger sees COMPLETED and avoids re-applying the batch.

In the example, `processed_rows` counts the staging rows processed in the batch, not newly inserted rows. If you need separate counts for inserted, updated, unchanged, or rejected rows, maintain distinct counters and clearly define when each is updated.

## 11. Recording Batches and Chunks for Controlled Retries

For very large batches, a single transaction can hold locks too long, generate excessive undo logs, and impact other workloads. You can split the work into smaller chunks, provided each chunk has a stable identifier and its own state.

~~~sql
CREATE TABLE import_chunks (
    batch_id VARCHAR(100) NOT NULL,
    chunk_no INT UNSIGNED NOT NULL,
    first_source_row BIGINT UNSIGNED NOT NULL,
    last_source_row BIGINT UNSIGNED NOT NULL,
    status ENUM('READY', 'COMPLETED') NOT NULL,
    processed_rows BIGINT UNSIGNED NULL,
    completed_at TIMESTAMP(6) NULL,
    PRIMARY KEY (batch_id, chunk_no)
) ENGINE=InnoDB;
~~~

Each chunk needs a deterministic source-row range or keyset boundary, must be merged in its own transaction, must update target data and chunk status COMPLETED in the same transaction, must be safely re-runnable if not yet COMPLETED, and must keep identical chunk boundaries on retry.

Never commit target data first and record chunk status in a separate transaction. If the process crashes between the two steps, the system cannot tell whether the chunk was applied. Data and completion markers must commit together.

Chunking alone does not make cumulative additions idempotent. Each row still requires a business key/event ID or source version to recognize already-applied effects.

## 12. Why REPLACE and INSERT IGNORE Are Not Default Solutions

### REPLACE INTO

REPLACE looks like an upsert, yet its semantics replace conflicting rows by deleting the old row and inserting a new row. This can:

- Trigger DELETE/INSERT behavior instead of UPDATE.
- Affect foreign keys and ON DELETE actions.
- Fire corresponding triggers.
- Overwrite omitted columns with defaults.
- Generate new AUTO_INCREMENT values or leave ID gaps.

Do not use REPLACE merely to update existing rows. When controlled updates are required, use UPDATE or INSERT ... ON DUPLICATE KEY UPDATE.

### INSERT IGNORE

INSERT IGNORE can skip duplicate keys, but it can also downgrade numerous data errors to warnings and coerce invalid values depending on the case. A row can be skipped due to duplicates, truncation, or conversion errors without the pipeline noticing unless warnings are inspected.

If the requirement is "on key conflict, update by version; on invalid data, reject," use constraints, validation, and explicit upserts. Never use IGNORE as a blanket mask for errors.

## 13. Avoiding Unnecessary Timestamp Updates or Side Effects on Retry

A batch might leave business values unchanged while an UPDATE still runs. Always setting `updated_at = CURRENT_TIMESTAMP(6)` will change the timestamp on every retry, making records appear newly modified even when the actual data stayed identical.

You can update the timestamp only when values actually differ:

~~~sql
-- Step 1: update timestamp only when content actually differs.
UPDATE customers AS c
JOIN customer_stage AS s
  ON s.external_id = c.external_id
SET c.updated_at = CURRENT_TIMESTAMP(6)
WHERE s.batch_id = 'customers-2026-11-v1'
  AND s.source_version > c.source_version
  AND (
      NOT (c.email <=> s.email)
      OR NOT (c.full_name <=> s.full_name)
  );

-- Step 2: apply content and record the new source version.
UPDATE customers AS c
JOIN customer_stage AS s
  ON s.external_id = c.external_id
SET
    c.email = s.email,
    c.full_name = s.full_name,
    c.source_version = s.source_version
WHERE s.batch_id = 'customers-2026-11-v1'
  AND s.source_version > c.source_version;
~~~

The `<=>` operator is MySQL's null-safe equality comparison: it treats two NULLs as equal and returns TRUE/FALSE rather than UNKNOWN. Both UPDATE statements execute in the same transaction: the first changes `updated_at` only when business content differs, while the second still advances `source_version` when receiving a newer version. Consequently, a newer version with identical content still blocks late-arriving older batches without producing misleading timestamp changes.

External side effects outside the database—such as sending emails, calling APIs, or publishing messages—must not be triggered directly in ways that can repeat unintentionally. Use a transactional outbox: write the outbound event to an outbox table within the business transaction, then have a worker deliver and mark it using an idempotent event ID.

## 14. Error Handling and Retries

Do not retry every error the same way. Classify errors:

| Error Type | Action |
|---|---|
| Connection drop / timeout, commit state unknown | Read batch ledger by batch_id; if COMPLETED, finish; if READY, retry |
| Deadlock | Roll back transaction and retry the entire transaction with the same batch/chunk key |
| Lock wait timeout | Consider rolling back transaction; retry with bounded attempts and backoff |
| Unexpected duplicate key | Roll back, inspect business keys and worker contention; do not skip automatically |
| Wrong data type / missing field | Route to reject log, fix source or mapping; do not retry unchanged endlessly |
| Checksum differs from registered batch | Halt processing and investigate data source |
| Permission or configuration error | Fix config/permissions; retry after root cause is resolved |

Retries should use bounded max attempts, exponential backoff with jitter, and log `batch_id`/`chunk_no`. Never hold a transaction open while waiting during backoff; roll back first, wait, and then open a new transaction.

## 15. Verifying Results After Merge

Do not rely solely on a SQL statement returning without error. Reconcile the data:

~~~sql
SELECT
    COUNT(*) AS staged_count,
    COUNT(DISTINCT external_id) AS distinct_external_ids
FROM customer_stage
WHERE batch_id = 'customers-2026-11-v1';

SELECT
    COUNT(*) AS target_rows_for_batch
FROM customers AS c
JOIN customer_stage AS s
  ON s.external_id = c.external_id
WHERE s.batch_id = 'customers-2026-11-v1';

SELECT batch_id, status, expected_rows, staged_rows, processed_rows, completed_at
FROM import_batches
WHERE batch_id = 'customers-2026-11-v1';
~~~

With staging keyed by `(batch_id, external_id)`, the distinct external_id count in the batch must equal the staged row count. After merge, every valid external_id in staging must match a target row. If a subset of rows was rejected, reconcile accepted and rejected counts separately rather than forcing the two numbers to match.

Detailed data comparisons can use anti/bidirectional joins or partitioned checksums. At large scale, partition reconciliation by key ranges to avoid repeatedly scanning the entire table.

## 16. Designing a Re-Runnable Import Pipeline

A practical workflow can be split into stages:

~~~mermaid
flowchart TD
    A[Receive file or message] --> B[Generate stable batch key and checksum]
    B --> C{Batch already COMPLETED?}
    C -->|Yes| D[Return completed result]
    C -->|No| E[Load into staging]
    E --> F[Validate, deduplicate, and reconcile]
    F --> G{Data valid?}
    G -->|No| H[Write reject log and mark FAILED]
    G -->|Yes| I[Claim batch / assign worker]
    I --> J[Transaction: merge data and update ledger]
    J --> K{Commit succeeded?}
    K -->|Yes| L[COMPLETED]
    K -->|Unknown due to timeout| M[Re-read ledger by batch key]
    M --> C
~~~

Each stage can be re-run without corrupting state:

- File ingestion: batch key and checksum identify identical payloads.
- Staging: an individual batch can be cleared and reloaded after verifying the source.
- Validation: re-runnable because it only reads data and produces check outputs.
- Merge: protected by business keys, versions, and transactions.
- Completion: the ledger commits atomically alongside target data changes.

Idempotency ensures safe handling when messages or batches are delivered at least once and may repeat. It does not automatically guarantee exactly-once external side effects; outbound messages, emails, or API calls still require event IDs and deduplication on the receiving side.

## 17. Pre-Deployment Checklist

1. A stable batch key is preserved across all retries.
2. Checksums or source versions detect the same batch arriving with altered content.
3. Target tables enforce PRIMARY KEY / UNIQUE constraints on business keys.
4. Staging enforces uniqueness and defines source deduplication rules.
5. Validation, reject logging, and row-count reconciliation steps are in place.
6. Upserts apply absolute state or event IDs; cumulative deltas are never blindly repeated.
7. Older source data cannot overwrite newer versions.
8. Data merge and ledger update happen inside the same transaction.
9. Chunks have fixed ranges and identifiers; chunk state commits with target data.
10. Deadlocks, timeouts, duplicate keys, and data errors are handled distinctly.
11. Retries use bounded attempts, backoff, and log batch/chunk IDs.
12. REPLACE/IGNORE are not used to mask errors or replace business rules.
13. External side effects have event IDs and dedicated outbox/idempotency mechanisms.
14. Crash scenarios before commit, after commit, and lost acknowledgment after commit have been tested.

## 18. Practice Exercises

1. Create a `customers` table with a UNIQUE `external_id` and an `import_batches` table with a stable `batch_id`.
2. Load the same set of customers twice; verify the target row count does not grow and no duplicate data is created.
3. Use `INSERT ... ON DUPLICATE KEY UPDATE` with `source_version`; test replaying an older version after a newer version and confirm data does not regress.
4. Create `customer_stage`, load a CSV via `LOAD DATA LOCAL INFILE`, and check row counts and duplicates.
5. Try placing two rows with the same `external_id` in one batch; observe the constraint catching the conflict and define a deduplication rule.
6. Merge staging using `UPDATE JOIN` and insert missing rows inside a transaction; re-run the same batch and compare final states.
7. Simulate an error before COMMIT and run ROLLBACK; verify neither target nor ledger was finalized.
8. Simulate a lost response after COMMIT; read the ledger by `batch_id` and verify retries do not reapply the batch.
9. Have two workers merge the same business key concurrently; handle duplicate-key/deadlock errors with rollback and retry.
10. Compare `REPLACE`, `INSERT IGNORE`, and `ON DUPLICATE KEY UPDATE` on a test table with triggers or foreign keys.

You have mastered this lesson when you can design batch keys and business keys, load data through staging, merge inside transactions, handle retries after timeouts without duplicating effects, and prove final state using the ledger and reconciliation checks. The goal is to turn re-execution into a routine, controllable, and verifiable operational step.
