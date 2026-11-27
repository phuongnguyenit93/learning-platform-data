# MERGE for Data Synchronization and Source/Target Matching Conditions

In Oracle Database, `MERGE` combines update and insert operations in a single DML statement. It is commonly used to synchronize a target table from a staging table, load batch data, update reference catalogs, or apply new records from an external source into an operational table.

The core idea is comparing source rows against target rows using an `ON` condition:

- If a source row **matches** a target row, the `WHEN MATCHED` branch can update the target row.
- If a source row **does not match** any target row, the `WHEN NOT MATCHED` branch can insert a new row.

The `ON` condition defines the boundary between "already exists" and "does not exist yet". Choosing the wrong match condition can cause an existing row to be treated as new, leading to duplicate key inserts or corrupted synchronization. In addition, the source must be normalized so multiple rows never attempt to update the same target row.

This lesson covers Oracle `MERGE` syntax, designing matching keys, the difference between `ON` and `UPDATE WHERE`/`INSERT WHERE`, handling duplicate sources, batch synchronization, key limitations, and verifying results.

## 1. What Does MERGE Do?

A `MERGE` statement has two datasets:

- **Target:** the table to be modified.
- **Source:** a table, view, or subquery supplying the rows to synchronize.

Each source row is matched against target rows using the `ON` condition. Depending on the outcome, Oracle executes the declared UPDATE or INSERT branch.

~~~text
                    SOURCE ROW
                         |
                         v
                  Evaluate ON condition
                    /           \
                 MATCH         NO MATCH
                   |              |
                   v              v
            WHEN MATCHED    WHEN NOT MATCHED
                   |              |
              UPDATE?          INSERT?
                   |              |
                   v              v
             TARGET ROW      NEW TARGET ROW
~~~

`MERGE` fits the **upsert** model (update if present, insert if absent). However, it does not automatically mean "make the two tables identical": rows existing only in the target and absent from the source are not automatically deleted.

## 2. Basic MERGE Syntax in Oracle

~~~sql
MERGE INTO target_table t
USING source_table s
   ON (t.business_key = s.business_key)
WHEN MATCHED THEN
    UPDATE SET
        t.column_a = s.column_a,
        t.column_b = s.column_b
WHEN NOT MATCHED THEN
    INSERT (business_key, column_a, column_b)
    VALUES (s.business_key, s.column_a, s.column_b);
~~~

| Component | Role |
| --- | --- |
| `MERGE INTO target_table t` | Selects the target table and alias `t` |
| `USING source_table s` | Selects the data source and alias `s` |
| `ON (...)` | Determines whether a source row matches a target row |
| `WHEN MATCHED THEN UPDATE` | Updates matched target rows |
| `WHEN NOT MATCHED THEN INSERT` | Inserts source rows with no matching target row |

In Oracle syntax, `WHEN MATCHED` is the update branch; `WHEN NOT MATCHED` is the insert branch. Both branches can have additional conditions. Oracle does not use `WHEN NOT MATCHED BY SOURCE` syntax found in some other database management systems.

## 3. Preparing Source and Target Lab Data

Let us use a customer catalog synchronization example. The target table holds data currently used by the application; the staging table holds data received from an external batch.

Run the statements in a practice schema you own, with table creation privileges and tablespace quota.

### 3.1. Create the Target Table

~~~sql
CREATE TABLE lab_customers (
    customer_id NUMBER PRIMARY KEY,
    full_name   VARCHAR2(100 CHAR) NOT NULL,
    email       VARCHAR2(200 CHAR),
    status      VARCHAR2(12 CHAR) DEFAULT 'ACTIVE' NOT NULL,
    updated_at  TIMESTAMP,
    CONSTRAINT ck_lab_customers_status
        CHECK (status IN ('ACTIVE', 'INACTIVE'))
);
~~~

`CUSTOMER_ID` is the primary key and will be the identifier used to match source and target.

### 3.2. Create the Staging Table

~~~sql
CREATE TABLE lab_customer_stage (
    batch_id          NUMBER NOT NULL,
    source_row_id     NUMBER PRIMARY KEY,
    customer_id       NUMBER NOT NULL,
    full_name         VARCHAR2(100 CHAR) NOT NULL,
    email             VARCHAR2(200 CHAR),
    source_status     VARCHAR2(12 CHAR),
    source_updated_at TIMESTAMP NOT NULL
);
~~~

`SOURCE_ROW_ID` identifies a single row received from the source. `CUSTOMER_ID` is not unique in staging in this design: the same customer can appear multiple times in a batch due to duplicate source records or multiple update versions. Before running MERGE, we must decide how to select one authoritative record.

### 3.3. Existing Data in Target

~~~sql
INSERT INTO lab_customers
    (customer_id, full_name, email, status, updated_at)
VALUES
    (1, 'An Nguyen', 'an.old@example.test', 'ACTIVE',
     TIMESTAMP '2024-01-01 09:00:00');

INSERT INTO lab_customers
    (customer_id, full_name, email, status, updated_at)
VALUES
    (2, 'Binh Tran', 'binh@example.test', 'ACTIVE',
     TIMESTAMP '2024-01-02 09:00:00');

INSERT INTO lab_customers
    (customer_id, full_name, email, status, updated_at)
VALUES
    (4, 'Dung Le', 'dung@example.test', 'INACTIVE',
     TIMESTAMP '2024-01-04 09:00:00');

COMMIT;
~~~

### 3.4. Source Data for Batch 100

~~~sql
INSERT INTO lab_customer_stage VALUES
    (100, 1001, 1, 'An Nguyen', 'an.new@example.test', 'ACTIVE',
     TIMESTAMP '2024-02-01 10:00:00');

INSERT INTO lab_customer_stage VALUES
    (100, 1002, 2, 'Binh Tran', 'binh@example.test', 'ACTIVE',
     TIMESTAMP '2024-02-01 10:05:00');

INSERT INTO lab_customer_stage VALUES
    (100, 1003, 3, 'Chi Pham', 'chi@example.test', 'ACTIVE',
     TIMESTAMP '2024-02-01 10:10:00');

COMMIT;
~~~

State before MERGE:

| CUSTOMER_ID | TARGET | SOURCE BATCH 100 | Expected outcome |
| ---: | --- | --- | --- |
| 1 | Present, old email | Present, new email | UPDATE |
| 2 | Present, identical data | Present | No UPDATE needed |
| 3 | Not present | Present | INSERT |
| 4 | Present, INACTIVE | Not present | Leave unchanged |

This is batch synchronization: only customers appearing in the source batch are evaluated for update or insert. Target row 4 is not in the source, so it remains intact.

## 4. Basic MERGE: Match Updates, Non-Match Inserts

~~~sql
MERGE INTO lab_customers t
USING (
    SELECT
        customer_id,
        full_name,
        email,
        source_status,
        source_updated_at
    FROM lab_customer_stage
    WHERE batch_id = 100
) s
ON (t.customer_id = s.customer_id)
WHEN MATCHED THEN
    UPDATE SET
        t.full_name  = s.full_name,
        t.email      = s.email,
        t.status     = s.source_status,
        t.updated_at = s.source_updated_at
WHEN NOT MATCHED THEN
    INSERT (
        customer_id,
        full_name,
        email,
        status,
        updated_at
    )
    VALUES (
        s.customer_id,
        s.full_name,
        s.email,
        s.source_status,
        s.source_updated_at
    );
~~~

Expected result:

| CUSTOMER_ID | FULL_NAME | EMAIL | STATUS |
| ---: | --- | --- | --- |
| 1 | An Nguyen | an.new@example.test | ACTIVE |
| 2 | Binh Tran | binh@example.test | ACTIVE |
| 3 | Chi Pham | chi@example.test | ACTIVE |
| 4 | Dung Le | dung@example.test | INACTIVE |

Explanation:

- ID 1 matches on `CUSTOMER_ID`, and its email and timestamp are updated.
- ID 2 matches and is reassigned the same source values. Even though data did not change, the UPDATE branch still executes because there is no `UPDATE WHERE` condition.
- ID 3 is not found in target and is inserted.
- ID 4 does not appear in source, so MERGE does not touch it.

To re-run the lab from scratch, restore target/stage data or use a new batch and adjust data accordingly. Do not repeatedly run the initial INSERTs on the same table when primary keys already exist.

## 5. The ON Condition: Defining What Constitutes the Same Record

`ON` is the most critical part of MERGE. It determines whether a source row represents the same entity as a target row.

### 5.1. Use Stable Identifying Keys

Good example:

~~~sql
ON (t.customer_id = s.customer_id)
~~~

If `CUSTOMER_ID` is the primary key on the target and a stable identifier supplied by the source system, this is a clear match condition.

Do not match by display name if names can change or are not unique:

~~~sql
ON (t.full_name = s.full_name)
~~~

Two different customers can share a name; one customer can change names. Using descriptive attributes for identity can cause a source row to match the wrong target row or fail to find the row needing updates.

### 5.2. Composite Keys

If identity is unique only across multiple columns, include all components in ON:

~~~sql
ON (
    t.tenant_id = s.tenant_id
    AND t.external_customer_id = s.external_customer_id
)
~~~

Using only `EXTERNAL_CUSTOMER_ID` can cross-match two customers from different tenants. The ON condition must reflect the true business unique key, and the target should also have a matching unique constraint to protect data.

### 5.3. Normalizing Text Keys

If business rules are case-insensitive or ignore leading/trailing spaces, values may need normalization:

~~~sql
ON (
    UPPER(TRIM(t.external_code)) =
    UPPER(TRIM(s.external_code))
)
~~~

Only use normalization expressions when that is an agreed identity rule. Notes:

- `TRIM` does not handle all Unicode whitespace types or every normalization rule.
- `UPPER` depends on collation/NLS semantics and character sets in the environment.
- Expressions can prevent normal indexes from being used; if needed, consider a function-based index or storing a normalized key column.
- The target must be unique under that exact normalization rule; if two distinct stored values normalize to the same key, MERGE can match multiple rows.

### 5.4. NULL in Matching Keys

With:

~~~sql
ON (t.external_code = s.external_code)
~~~

if both `EXTERNAL_CODE` values are NULL, the comparison evaluates to UNKNOWN rather than TRUE. Thus two rows with NULL keys are not considered matched.

If keys are NOT NULL in the data model, this is desirable. If source keys can be NULL, decide how to handle them:

- Reject or quarantine source rows missing keys.
- Use an alternative identifying key.
- Only when business rules explicitly dictate, write an intentional NULL-safe condition.

Do not use a sentinel like `NVL(key, -1)` or `NVL(code, 'UNKNOWN')` if that value could be a real key or cause collisions.

### 5.5. Do Not Use Update Filters as Identity Conditions

Suppose the target has customer ID 4 with status INACTIVE. If you write:

~~~sql
ON (
    t.customer_id = s.customer_id
    AND t.status = 'ACTIVE'
)
~~~

then source row ID 4 will fail to match the target because the target status is INACTIVE. Oracle treats the source row as NOT MATCHED and sends it to the INSERT branch. If `CUSTOMER_ID` is the primary key, INSERT fails with `ORA-00001` because the key already exists.

Normally, `ON` should identify **the same entity** by identifying key. If you only want to update ACTIVE targets, put that filter in the UPDATE branch:

~~~sql
MERGE INTO lab_customers t
USING (
    SELECT customer_id, full_name, email, source_status, source_updated_at
    FROM lab_customer_stage
    WHERE batch_id = 100
) s
ON (t.customer_id = s.customer_id)
WHEN MATCHED THEN
    UPDATE SET
        t.full_name = s.full_name,
        t.email = s.email,
        t.status = s.source_status,
        t.updated_at = s.source_updated_at
    WHERE t.status = 'ACTIVE'
WHEN NOT MATCHED THEN
    INSERT (customer_id, full_name, email, status, updated_at)
    VALUES (s.customer_id, s.full_name, s.email,
            s.source_status, s.source_updated_at);
~~~

For target ID 4, ON still matches the entity; UPDATE WHERE skips the update because the status is inactive. That row **does not fall through to the INSERT branch**. For new ID 3, the INSERT branch still runs.

## 6. WHERE Conditions in MERGE Branches

Oracle allows additional predicates inside the UPDATE and INSERT branches. Their roles differ from the ON condition.

### 6.1. UPDATE WHERE: Update Only When Needed

An unconditional MERGE updates matched rows even when no columns changed. You can avoid unnecessary DML:

~~~sql
MERGE INTO lab_customers t
USING (
    SELECT customer_id, full_name, email, source_status, source_updated_at
    FROM lab_customer_stage
    WHERE batch_id = 100
) s
ON (t.customer_id = s.customer_id)
WHEN MATCHED THEN
    UPDATE SET
        t.full_name = s.full_name,
        t.email = s.email,
        t.status = s.source_status,
        t.updated_at = s.source_updated_at
    WHERE
        t.full_name <> s.full_name
        OR t.email <> s.email
        OR t.status <> s.source_status;
~~~

This is a basic example, but it has an issue: `<>` does not detect changes from NULL to a value or from a value to NULL. For instance, if `t.email` is NULL and `s.email` is a string, `t.email <> s.email` evaluates to UNKNOWN rather than TRUE.

### 6.2. NULL-Safe Comparison in UPDATE WHERE

You can spell out the cases explicitly:

~~~sql
WHERE
       t.full_name <> s.full_name
    OR (t.full_name IS NULL AND s.full_name IS NOT NULL)
    OR (t.full_name IS NOT NULL AND s.full_name IS NULL)
    OR t.email <> s.email
    OR (t.email IS NULL AND s.email IS NOT NULL)
    OR (t.email IS NOT NULL AND s.email IS NULL)
    OR t.status <> s.source_status
    OR (t.status IS NULL AND s.source_status IS NOT NULL)
    OR (t.status IS NOT NULL AND s.source_status IS NULL)
~~~

Since `FULL_NAME` and `STATUS` are declared NOT NULL in the lab, their NULL-safe branches are redundant, though they illustrate the general pattern. You can also use Oracle's `DECODE` to compare two values while handling NULL:

~~~sql
WHERE
       DECODE(t.full_name, s.full_name, 0, 1) = 1
    OR DECODE(t.email, s.email, 0, 1) = 1
    OR DECODE(t.status, s.source_status, 0, 1) = 1
~~~

`DECODE` treats two NULLs as equal under its function semantics. If used, align data types and understand DECODE's implicit conversion rules. Explicit conditions are easier to read when logic is complex; DECODE is concise when comparing values of the same type.

### 6.3. INSERT WHERE: Restrict Rows Inserted

Example inserting only customers with valid source statuses:

~~~sql
WHEN NOT MATCHED THEN
    INSERT (
        customer_id, full_name, email, status, updated_at
    )
    VALUES (
        s.customer_id, s.full_name, s.email,
        s.source_status, s.source_updated_at
    )
    WHERE s.source_status IN ('ACTIVE', 'INACTIVE')
~~~

The predicate in INSERT WHERE only decides whether a NOT MATCHED row gets inserted. It does not turn a MATCHED row into NOT MATCHED and does not alter ON matching results.

## 7. Synchronizing a Source with Multiple Rows for the Same Key

A classic MERGE error occurs when the source returns multiple rows matching a single target row. Oracle requires MERGE to be deterministic: a target row cannot be updated multiple times in one MERGE statement.

### 7.1. Duplicate Key Source Example

Suppose staging has two versions for the same customer:

~~~sql
INSERT INTO lab_customer_stage VALUES
    (200, 2001, 10, 'Mai Nguyen', 'mai.old@example.test', 'ACTIVE',
     TIMESTAMP '2024-03-01 09:00:00');

INSERT INTO lab_customer_stage VALUES
    (200, 2002, 10, 'Mai Nguyen', 'mai.new@example.test', 'ACTIVE',
     TIMESTAMP '2024-03-02 09:00:00');

COMMIT;
~~~

Both rows share `CUSTOMER_ID = 10` but have different email/timestamps. If you MERGE batch 200 directly:

~~~sql
MERGE INTO lab_customers t
USING (
    SELECT customer_id, full_name, email, source_status, source_updated_at
    FROM lab_customer_stage
    WHERE batch_id = 200
) s
ON (t.customer_id = s.customer_id)
WHEN MATCHED THEN
    UPDATE SET
        t.email = s.email,
        t.updated_at = s.source_updated_at
WHEN NOT MATCHED THEN
    INSERT (customer_id, full_name, email, status, updated_at)
    VALUES (s.customer_id, s.full_name, s.email,
            s.source_status, s.source_updated_at);
~~~

If ID 10 already exists in the target, two source rows target the same row. Oracle raises `ORA-30926: unable to get a stable set of rows in the source tables` because the same target row would be affected multiple times. If ID 10 does not exist yet, both rows enter the INSERT branch and hit a unique constraint violation. Therefore, always normalize the source before MERGE regardless of whether the key currently exists in the target.

### 7.2. Selecting the Latest Record with ROW_NUMBER

If the rule is "keep only the latest source version per customer", use an analytic function to pick exactly one row:

~~~sql
MERGE INTO lab_customers t
USING (
    SELECT
        customer_id,
        full_name,
        email,
        source_status,
        source_updated_at
    FROM (
        SELECT
            stg.customer_id,
            stg.full_name,
            stg.email,
            stg.source_status,
            stg.source_updated_at,
            ROW_NUMBER() OVER (
                PARTITION BY stg.customer_id
                ORDER BY
                    stg.source_updated_at DESC,
                    stg.source_row_id DESC
            ) AS rn
        FROM lab_customer_stage stg
        WHERE stg.batch_id = 200
    )
    WHERE rn = 1
) s
ON (t.customer_id = s.customer_id)
WHEN MATCHED THEN
    UPDATE SET
        t.full_name = s.full_name,
        t.email = s.email,
        t.status = s.source_status,
        t.updated_at = s.source_updated_at
WHEN NOT MATCHED THEN
    INSERT (customer_id, full_name, email, status, updated_at)
    VALUES (s.customer_id, s.full_name, s.email,
            s.source_status, s.source_updated_at);
~~~

`ROW_NUMBER` assigns a sequence number within each customer. `SOURCE_UPDATED_AT DESC` picks the latest version; `SOURCE_ROW_ID DESC` breaks ties deterministically when timestamps match. The subquery yields at most one row per `CUSTOMER_ID`.

Do not pick the latest row using only `MAX(source_updated_at)` joined back if multiple rows can share the same timestamp; that can still produce multiple source rows. Always include a unique tie-breaker or an explicit aggregation rule.

### 7.3. When the Source Is Transactional Data, Aggregation May Be Needed

Multiple source rows are not always duplicate versions. If the source contains multiple transactions to accumulate, aggregate by the target key:

~~~sql
USING (
    SELECT
        account_id,
        SUM(transaction_amount) AS batch_amount
    FROM staging_transactions
    WHERE batch_id = :batch_id
    GROUP BY account_id
) s
~~~

The subquery produces one row per account. Use `ROW_NUMBER` when selecting one version; use `GROUP BY` when multiple rows must contribute to an aggregated value. The two rules are not interchangeable.

## 8. The Source Must Match the Exact Batch

In a staging table, batch ID defines the scope of source data. If you omit the batch filter, MERGE can re-process data from prior loads:

~~~sql
USING (
    SELECT customer_id, full_name, email, source_status, source_updated_at
    FROM lab_customer_stage
) s
~~~

This is often a dangerous bug because older source rows can overwrite newer data. Filter the batch right inside the source subquery:

~~~sql
USING (
    SELECT customer_id, full_name, email, source_status, source_updated_at
    FROM lab_customer_stage
    WHERE batch_id = :batch_id
) s
~~~

If the source holds multiple systems or tenants, batch/source-system/tenant can also be part of source scoping or the composite key. Do not put the batch filter into ON as a substitute for filtering the source; doing so can alter MATCHED/NOT MATCHED semantics.

## 9. Update Only When Source Data Is Newer

A common synchronization rule is overwriting the target only when the source version is newer:

~~~sql
MERGE INTO lab_customers t
USING (
    SELECT customer_id, full_name, email, source_status, source_updated_at
    FROM lab_customer_stage
    WHERE batch_id = :batch_id
) s
ON (t.customer_id = s.customer_id)
WHEN MATCHED THEN
    UPDATE SET
        t.full_name = s.full_name,
        t.email = s.email,
        t.status = s.source_status,
        t.updated_at = s.source_updated_at
    WHERE s.source_updated_at > t.updated_at
WHEN NOT MATCHED THEN
    INSERT (customer_id, full_name, email, status, updated_at)
    VALUES (s.customer_id, s.full_name, s.email,
            s.source_status, s.source_updated_at);
~~~

This condition prevents an older source record from overwriting a newer one. However, you must clearly define what happens when `T.UPDATED_AT` is NULL:

- If NULL means the target was never synchronized, use `t.updated_at IS NULL OR s.source_updated_at > t.updated_at`.
- If the source timestamp can be NULL, reject it or define explicit ordering.
- If clocks across source systems are not synchronized, timestamps are not always reliable version markers; a sequence/version number from the source system may be needed.

Example handling NULL target timestamp:

~~~sql
WHERE t.updated_at IS NULL
   OR s.source_updated_at > t.updated_at
~~~

## 10. Can MERGE Delete Rows?

Oracle supports `DELETE WHERE` inside the UPDATE branch:

~~~sql
MERGE INTO lab_customers t
USING (
    SELECT customer_id, full_name, email, source_status, source_updated_at
    FROM lab_customer_stage
    WHERE batch_id = :batch_id
) s
ON (t.customer_id = s.customer_id)
WHEN MATCHED THEN
    UPDATE SET
        t.full_name = s.full_name,
        t.email = s.email,
        t.status = s.source_status,
        t.updated_at = s.source_updated_at
    DELETE WHERE t.status = 'INACTIVE'
WHEN NOT MATCHED THEN
    INSERT (customer_id, full_name, email, status, updated_at)
    VALUES (s.customer_id, s.full_name, s.email,
            s.source_status, s.source_updated_at);
~~~

Key points to remember:

- `DELETE WHERE` applies only to rows updated by the MATCHED branch.
- The DELETE condition is evaluated on the **post-UPDATE values**.
- NOT MATCHED rows inserted by INSERT do not pass through DELETE WHERE.
- Target rows with no matching source row are also not deleted.

For example, if the source updates a customer's status from ACTIVE to INACTIVE, the target row is updated first and then deleted because its post-update status is INACTIVE. This is a high-impact operation; use it only when business rules truly require it.

If you want to delete target rows when **they no longer appear in a snapshot source**, `DELETE WHERE` inside MERGE does not solve that requirement. You need a separate DELETE with `NOT EXISTS` or a clearly scoped snapshot sync mechanism:

~~~sql
DELETE FROM lab_customers t
WHERE NOT EXISTS (
    SELECT 1
    FROM lab_customer_stage s
    WHERE s.batch_id = :complete_snapshot_batch
      AND s.customer_id = t.customer_id
);
~~~

Only run this type of DELETE when the batch is a **full snapshot** of the synchronized scope. If the batch only contains incremental changes (delta), an absent row simply did not change; deleting it would cause data loss. MERGE and DELETE should be designed within the appropriate workflow/transaction, with controlled batch keys and snapshot rules.

## 11. MERGE and Primary Key / Unique Constraints

The ON condition only describes how to match; it does not enforce data uniqueness on its own. The target should have a primary key or unique constraint matching the join key.

Example:

~~~sql
ALTER TABLE lab_customers
ADD CONSTRAINT uq_lab_customers_email
UNIQUE (email);
~~~

Only add this constraint if business rules guarantee unique emails and current data has no violations. In the lab, email is nullable; Oracle unique constraints allow multiple rows with NULL per Oracle rules. Do not use email as the MERGE key just because it has a unique constraint if email can change or is not a stable identifier.

Layers of protection should include:

- Target primary key/unique constraint on the entity identifier.
- Unique constraint or source validation guaranteeing one source row per target key.
- NOT NULL on mandatory key components.
- Foreign key/check constraints for related data rules.
- Workflow for handling invalid or keyless source rows before MERGE.

## 12. MERGE Is Deterministic: Avoid Updating the Same Target Row Multiple Times

Oracle defines `MERGE` as deterministic: a single MERGE statement cannot update the same target row more than once. If multiple source rows match one target row, the statement fails with:

~~~text
ORA-30926: unable to get a stable set of rows in the source tables
~~~

If multiple unmatched source rows share the same target key, they can all enter the INSERT branch and violate a unique constraint. Both errors stem from the source lacking a single clear row per target identifier.

Before running MERGE, check:

~~~sql
SELECT customer_id, COUNT(*) AS source_rows
FROM lab_customer_stage
WHERE batch_id = :batch_id
GROUP BY customer_id
HAVING COUNT(*) > 1;
~~~

If the query returns rows, decide the deduplication/aggregation rule before running MERGE. Do not blindly apply `DISTINCT` across all columns: two versions with the same ID and different emails will not be collapsed by DISTINCT, and deduplicating display columns still leaves ambiguity about which version is authoritative.

## 13. The ON Condition and Restrictions on Updating Key Columns

Oracle forbids updating a target column referenced in the ON condition of the same MERGE. For example:

~~~sql
MERGE INTO lab_customers t
USING source_customers s
ON (t.customer_id = s.customer_id)
WHEN MATCHED THEN
    UPDATE SET t.customer_id = s.new_customer_id;
~~~

This design is invalid because `CUSTOMER_ID` is used in ON. If an identifier must change, design a separate operation accounting for foreign keys, uniqueness, related tables, and identity migration rules. Do not try to use MERGE to both identify a row by a key and modify that same key inside the UPDATE branch.

## 14. Source/Target Conditions Across Multiple States

| Scenario | ON | UPDATE WHERE | INSERT WHERE |
| --- | --- | --- | --- |
| Same customer, data changed | Matches by ID | TRUE | Not applicable |
| Same customer, data unchanged | Matches by ID | FALSE if comparing changes | Not applicable |
| Same customer, target locked/inactive | Still matches by ID | FALSE if not updatable | Not applicable; no INSERT |
| New customer, valid source | No match | Not applicable | TRUE |
| New customer, invalid source | No match | Not applicable | FALSE or filtered from source |
| Target customer absent from source | No source row to match | Does not run | Does not run |

This table shows that the three conditions have three separate responsibilities:

- `ON`: identify the same entity.
- `UPDATE WHERE`: decide whether to update a matched row.
- `INSERT WHERE`: decide whether to insert an unmatched row.

Mixing all three into a single ON expression can produce wrong branching behavior.

## 15. Transactions, Errors, and Concurrency

`MERGE` is a single DML statement. UPDATE/INSERT actions belong to the same statement and follow statement-level atomicity: if the statement fails, the statement's changes are rolled back per Oracle mechanisms. However, the transaction may still hold earlier uncommitted DML.

Design considerations:

1. **Do not commit mid-way inside a MERGE.** Commit/rollback belongs to the application or batch workflow transaction.
2. **Keep unique constraints on the target.** The ON condition does not replace constraints.
3. **Handle contention between concurrent sessions.** Two sessions merging a nonexistent key at the same time can both enter the INSERT branch; a unique constraint protects the data, while one session may receive a unique violation depending on commit/lock timing.
4. **Design controlled retries.** If an error is caused by contention, the application may retry per transaction policy after reading fresh state; do not blindly retry every error.
5. **Attach batch IDs and store processing status.** This enables controlled reruns, error investigation, and prevents mixing multiple load runs.
6. **Control timestamps/versions from the source.** Prevent stale data from overwriting newer data when batches arrive out of order.

A single MERGE does not solve every distributed sync challenge on its own. You must define whether the source is a snapshot or delta, batch ordering, identifying keys, idempotency, and writer conflict resolution.

## 16. Verifying Data Before and After MERGE

### 16.1. Count Source Rows by Batch

~~~sql
SELECT
    COUNT(*) AS source_rows,
    COUNT(DISTINCT customer_id) AS distinct_customers
FROM lab_customer_stage
WHERE batch_id = :batch_id;
~~~

If the two numbers differ, the source has repeated customer IDs. This is not necessarily an error if the pipeline has version selection or aggregation rules, but it must be handled before MERGE.

### 16.2. Find Source Keys Not Yet in Target

~~~sql
SELECT s.customer_id
FROM lab_customer_stage s
WHERE s.batch_id = :batch_id
  AND NOT EXISTS (
      SELECT 1
      FROM lab_customers t
      WHERE t.customer_id = s.customer_id
  );
~~~

This is the set of keys expected to enter the INSERT branch unless filtered out by another condition.

### 16.3. Find Source Keys Already in Target

~~~sql
SELECT s.customer_id
FROM lab_customer_stage s
JOIN lab_customers t
  ON t.customer_id = s.customer_id
WHERE s.batch_id = :batch_id;
~~~

This is the set of keys expected to enter the MATCHED branch. The UPDATE WHERE condition may leave some rows in this set untouched.

### 16.4. Compare State After Synchronization

~~~sql
SELECT
    t.customer_id,
    t.full_name,
    t.email,
    t.status,
    t.updated_at
FROM lab_customers t
ORDER BY t.customer_id;
~~~

Reconcile results against batch rules, not just total row counts. One batch may update some rows, insert some rows, skip some rows, and leave target-only rows intact.

## 17. Common Errors

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Row exists, yet MERGE tries to INSERT | ON includes non-key status/attribute filter | Match by identifying key in ON; move update filters to UPDATE WHERE |
| ORA-00001 in INSERT branch | Target row exists but ON failed to match, or concurrent race | Check ON, unique keys, and concurrency |
| ORA-30926 | Multiple source rows affect one target row | Deduplicate with ROW_NUMBER or aggregate per rule |
| MERGE inserts multiple duplicate-key rows | Source has multiple rows with same key absent from target | Normalize source and maintain unique constraint |
| Target data overwritten by older version | Missing batch filter or version comparison | Filter batch and enforce timestamp/version rules |
| NULL changes not detected | Plain `<>` used in UPDATE WHERE | Use NULL-safe comparison explicitly or DECODE |
| Two NULL keys fail to match | `NULL = NULL` evaluates to UNKNOWN | Enforce NOT NULL keys or design intentional NULL-safe logic |
| UPDATE WHERE is false, yet row still does not INSERT | Row already MATCHED by ON; UPDATE WHERE only skips update | Expected behavior; there is no fallback to INSERT |
| Target rows absent from source remain | MERGE does not automatically delete target-only rows | Run separate DELETE NOT EXISTS per snapshot rules |
| DELETE WHERE does not delete target-only rows | DELETE WHERE applies only to matched updated rows | Run separate DELETE NOT EXISTS per snapshot rules |
| Updating ON column fails | Oracle forbids updating target columns referenced in ON | Design identity changes as a separate operation |
| Re-running batch produces different results | Source changed or non-deterministic tie-breaking | Lock down snapshot/batch, tie-breakers, and idempotency |

## 18. Practice Exercises

Use `LAB_CUSTOMERS` and `LAB_CUSTOMER_STAGE` from section 3. Predict each MERGE branch before executing.

### Exercise 1 — Basic Upsert

Write a MERGE for batch 100: update existing customers by CUSTOMER_ID and insert missing customers. Verify results for IDs 1, 2, 3, and 4.

### Exercise 2 — Update Only on Change

Add UPDATE WHERE to avoid rewriting rows with identical data. Start with `<>`, then fix it to detect changes from NULL to value and value to NULL.

### Exercise 3 — Wrong ON Condition

Add `AND t.status = 'ACTIVE'` to ON. Observe target ID 4, which is INACTIVE. Explain why this row is treated as NOT MATCHED and why INSERT can violate the primary key. Fix it using UPDATE WHERE.

### Exercise 4 — Duplicate Key Source

Insert two rows for CUSTOMER_ID 10 into batch 200. Run the duplicate source check. Write a MERGE using ROW_NUMBER to select only the latest version, using SOURCE_ROW_ID as the tie-breaker.

### Exercise 5 — Composite Key

Suppose the target table has `TENANT_ID` and `EXTERNAL_CUSTOMER_ID`. Write an ON clause using both columns. Explain the risk of using only EXTERNAL_CUSTOMER_ID.

### Exercise 6 — NULL in Keys

Create source and target rows with NULL EXTERNAL_CODE. Run matching with `=` and explain why they do not match. Propose a data-model-driven handling strategy instead of using arbitrary sentinels.

### Exercise 7 — Version Synchronization

Update only when `SOURCE_UPDATED_AT` is newer than `TARGET.UPDATED_AT`. Handle NULL target timestamps explicitly and explain why source timestamps are unreliable if system clocks drift.

### Exercise 8 — Snapshot Deletion

Distinguish between a delta batch and a full snapshot. Write DELETE NOT EXISTS exclusively for the full snapshot case; explain why it must not be used on a delta batch.

## 19. Clean Up Lab Data

Run only in the lab schema you created, after finishing the exercises:

~~~sql
DROP TABLE lab_customer_stage PURGE;
DROP TABLE lab_customers PURGE;
~~~

Drop staging before target if foreign keys or dependent relationships are added later. `PURGE` bypasses the recycle bin; never run on business tables or data that might need recovery.

## Summary

`MERGE` identifies rows using the `ON` condition, then chooses UPDATE for MATCHED rows or INSERT for NOT MATCHED rows. Design `ON` around stable, complete identifying keys; conditions deciding **whether to update** belong in `UPDATE WHERE`. Conditions restricting inserted rows belong in `INSERT WHERE`. These three clauses have distinct responsibilities and should not be mixed.

The source must provide at most one authoritative row per target key. If staging holds multiple versions, pick one row with `ROW_NUMBER` and a deterministic tie-breaker; if the source contains transactions to accumulate, aggregate by key first. Maintain primary key/unique constraints on the target, handle NULLs in keys, filter the exact batch, and enforce version checks to avoid overwriting newer data with stale records. MERGE does not automatically delete target rows missing from the source; run a separate DELETE only when the source is a full snapshot and business rules permit.

## Oracle Reference Documentation

- [Oracle Database SQL Language Reference — MERGE (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/MERGE.html) — MERGE syntax, ON, UPDATE WHERE, INSERT WHERE, and DELETE WHERE.
- [Oracle Database SQL Language Reference — MERGE (26ai)](https://docs.oracle.com/en/database/oracle/oracle-database/26/sqlrf/MERGE.html) — syntax comparison on newer releases.
- [Oracle Database Error Messages — ORA-30926](https://docs.oracle.com/error-help/db/ora-30926/) — unable to get a stable set of rows in the source tables.
- [Oracle Database SQL Language Reference — Analytic Functions (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/Analytic-Functions.html) — ROW_NUMBER for ordered source version selection.
- [Oracle Database SQL Language Reference — Constraints (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/constraint.html) — primary key, unique, foreign key, and check constraints.

When deploying on an Oracle release other than 19c, check the SQL Language Reference for that exact version, particularly regarding conditional clauses, restrictions on updating ON columns, and behavior when the source has multiple rows per key.
