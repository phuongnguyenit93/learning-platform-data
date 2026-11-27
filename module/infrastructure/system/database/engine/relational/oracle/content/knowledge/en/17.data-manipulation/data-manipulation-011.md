# Handling Duplicate Data with Constraints and Idempotent Operations in Oracle

An application may send the same request multiple times because a user double-clicks a button, a client times out and retries, a message broker redelivers a message, or a batch must re-run after a process stops. If every execution inserts a new row, the data can end up with multiple records representing the same customer, order, or event. Duplicate data can also enter through file imports, external system syncs, or manual operations.

To handle this properly, separate two tasks:

1. **Prevent new duplicates:** define the business key and use PRIMARY KEY, UNIQUE constraints, or unique indexes so the database enforces uniqueness.
2. **Make operations idempotent:** design statements and transactions so resending the same request produces no unintended extra effects.

When duplicates already exist, identify the canonical record, decide survivorship rules, reassign related references, and clean up redundant rows before enabling constraints. MERGE can help with upserts, yet it does not automatically solve every concurrency issue or turn an arbitrary workflow into an idempotent one.

After this lesson, you will be able to:

- Distinguish two rows identical in content from two rows duplicating business identity.
- Choose natural/business keys and design PRIMARY KEY/UNIQUE constraints.
- Use unique indexes, function-based unique indexes, and NOT NULL intentionally.
- Inspect existing data before adding constraints.
- Pick a canonical record with ROW_NUMBER and deterministic ordering, then clean up duplicates safely.
- Use MERGE for insert-or-update operations and understand its limits.
- Design idempotency keys for APIs, batches, and message consumers.
- Understand race conditions between pre-write checks and concurrent INSERTs.
- Handle ORA-00001, retries, transaction boundaries, and same-idempotency-key/different-payload conflicts.
- Control duplicate source data before MERGE and verify results after reruns.

> Examples use the `LAB_` prefix and should run in a practice schema with table/sequence creation privileges. Survivorship rules must follow business requirements and be confirmed before deleting data. DELETE statements in this lesson are controlled examples; always check with a matching SELECT and have a recovery plan before running on live data.

## 1. What Is Duplicate Data?

The word "duplicate" has multiple meanings. Two rows identical column-for-column are not necessarily duplicate business records; conversely, two rows with different names or emails can still represent the same customer.

### 1.1. Exact Duplicate (Physical Duplicate)

Two rows share the exact same values across all inspected columns:

| CUSTOMER_CODE | EMAIL | DISPLAY_NAME |
| --- | --- | --- |
| C100 | an@example.com | An Nguyen |
| C100 | an@example.com | An Nguyen |

This may be the same record imported twice. However, real tables often have surrogate keys or timestamps, so two rows are not bit-for-bit identical even when business content is duplicated.

### 1.2. Business Duplicate (Duplicate by Business Key)

Two rows represent the same entity per business rules, even though some attributes differ:

| SOURCE_SYSTEM | EXTERNAL_ID | EMAIL | DISPLAY_NAME |
| --- | --- | --- | --- |
| CRM_A | 9001 | an.old@example.com | An Nguyen |
| CRM_A | 9001 | an@example.com | Nguyen An |

If the rule states that (SOURCE_SYSTEM, EXTERNAL_ID) identifies a unique customer, these two rows duplicate identity. You must choose which data is authoritative, or merge attributes per business rules.

### 1.3. Duplicates After Normalization

Strings differing in letter case or whitespace may be treated as equivalent:

| Raw EMAIL | Simply normalized key |
| --- | --- |
| An@Example.com | AN@EXAMPLE.COM |
|  an@example.com  | AN@EXAMPLE.COM |

If the domain treats these two values as one, a plain `email = email` check will miss duplicates. Define explicit normalization rules (trimming, case folding, Unicode normalization, accents, dots, or email aliases if applicable) and apply them consistently on reads and writes.

Do not arbitrarily treat emails differing in dots, plus signs, or Unicode characters as belonging to the same person. That is a domain-specific rule, not a safe universal normalization.

### 1.4. Why Define Identity First?

Without a clear business key:

- A UNIQUE constraint may protect the wrong columns or miss duplicates.
- DISTINCT might collapse two legitimate transactions simply because their measure values match.
- ROW_NUMBER might preserve an outdated version by mistake.
- MERGE might create extra rows because the ON condition does not reflect true identity.
- Retries might multiply side effects because there is no request-identifying key.

Before writing SQL, answer: **which two writes must be treated as the same object or the same request?**

## 2. Choosing Keys: PRIMARY KEY, UNIQUE, and Business Keys

### 2.1. PRIMARY KEY

PRIMARY KEY uniquely identifies each row in a table. A table has at most one primary key constraint; the key can span one or more columns. Every primary key column is NOT NULL and key values cannot repeat.

Example using an internal ID:

```sql
CREATE TABLE lab_customers (
    customer_id NUMBER(12)
        CONSTRAINT pk_lab_customers PRIMARY KEY,
    source_system VARCHAR2(30) NOT NULL,
    external_customer_id VARCHAR2(80) NOT NULL,
    email VARCHAR2(320),
    display_name VARCHAR2(160),
    updated_at TIMESTAMP
);
```

CUSTOMER_ID is a surrogate key: a technical ID managed by the system. It provides stable foreign-key references across other tables, yet by itself **it does not stop the same external customer from being inserted multiple times**. Two imports can generate two different CUSTOMER_IDs for the same EXTERNAL_CUSTOMER_ID.

### 2.2. UNIQUE Constraint for Business Keys

If a customer is identified by source system and source ID, create a composite key:

```sql
ALTER TABLE lab_customers
ADD CONSTRAINT uq_lab_customers_source
UNIQUE (source_system, external_customer_id);
```

From then on, the database forbids two rows sharing the same `(SOURCE_SYSTEM, EXTERNAL_CUSTOMER_ID)` pair under Oracle uniqueness rules. PRIMARY KEY and UNIQUE constraints serve distinct roles:

| Constraint | Purpose |
| --- | --- |
| PRIMARY KEY | Row identity inside the table; unique and NOT NULL |
| UNIQUE | Protects an alternate key or business key from duplicates |
| FOREIGN KEY | Protects referential relationships between tables |
| NOT NULL | Requires a value in the column |
| CHECK | Enforces valid row-level value conditions |

A table can have multiple UNIQUE constraints, yet only one PRIMARY KEY.

### 2.3. UNIQUE Does Not Automatically Replace NOT NULL

Oracle allows NULLs in columns of a UNIQUE constraint. Therefore, if a business key is required to have a value, declare NOT NULL explicitly:

The MODIFY example below applies to legacy tables currently allowing NULL; the table just created in section 2.1 already declared both columns NOT NULL so you do not need to run it again.

```sql
ALTER TABLE lab_customers MODIFY (
    source_system NOT NULL,
    external_customer_id NOT NULL
);
```

For composite keys containing NULLs, Oracle uniqueness rules have important nuances: rows where all key components are NULL can coexist; if only part of the key is NULL, the non-NULL components must still satisfy uniqueness under composite key rules. Never use NULL to represent a required business key. Declare NOT NULL on every component when the business requires a complete identifier.

### 2.4. UNIQUE Constraints and Unique Indexes

Oracle typically uses a unique index to enforce a PRIMARY KEY/UNIQUE constraint. You can create a unique index directly:

```sql
CREATE UNIQUE INDEX ux_lab_customers_source
ON lab_customers (source_system, external_customer_id);
```

This is an alternative to adding the UNIQUE constraint in section 2.2 if the goal is solely index-level uniqueness enforcement. Do not unnecessarily create two duplicate unique indexes on the exact same column set. If you want a UNIQUE constraint in metadata while an appropriate index already exists, attach the constraint to that index:

```sql
ALTER TABLE lab_customers
ADD CONSTRAINT uq_lab_customers_source
UNIQUE (source_system, external_customer_id)
USING INDEX ux_lab_customers_source;
```

A unique index enforces uniqueness at the index level. A UNIQUE constraint expresses a data integrity rule in metadata and is easily recognized by admin tools and constraint checks. In business schema design, prefer declaring constraints; Oracle uses an existing suitable index or creates one to enforce it.

If a suitable unique index already exists, create the constraint using that index via `USING INDEX` per your DDL workflow. There is no need to create a duplicate unique index if the constraint is already backed by an appropriate index.

### 2.5. Composite Keys and Column Order

A UNIQUE constraint can span multiple columns:

```sql
ALTER TABLE lab_order_lines
ADD CONSTRAINT uq_lab_order_line
UNIQUE (order_id, line_no);
```

This ensures each LINE_NO within an ORDER_ID appears at most once. It does not require LINE_NO to be unique across the whole table.

Pick the exact right set of columns. Adding UPDATED_AT to the key just to allow multiple versions changes the entity definition; omitting SOURCE_SYSTEM lets two source systems collide on IDs.

## 3. Normalizing Business Keys Before Applying Uniqueness

A UNIQUE constraint on EMAIL protects the exact stored value according to column/collation comparison rules. If the domain treats email as case-insensitive and ignores leading/trailing spaces, apply that rule consistently.

### 3.1. Finding Duplicates by Normalized Key

```sql
SELECT
    UPPER(TRIM(email)) AS normalized_email,
    COUNT(*) AS row_count
FROM lab_customers
WHERE email IS NOT NULL
GROUP BY UPPER(TRIM(email))
HAVING COUNT(*) > 1
ORDER BY normalized_email;
```

This checks duplicates under a simple rule: strip leading/trailing spaces and convert to uppercase. `UPPER(TRIM(...))` is not complete email normalization for every language/Unicode rule or collation; align the rule with the application and source data.

### 3.2. Function-Based Unique Indexes

To have the database enforce uniqueness on normalized values, create a unique function-based index:

```sql
CREATE UNIQUE INDEX ux_lab_customers_email_norm
ON lab_customers (UPPER(TRIM(email)));
```

From then on, `An@Example.com` and `an@example.com` (with leading/trailing spaces) cannot coexist if their normalized expressions match. When email is NULL, the index expression is NULL; Oracle B-tree indexes do not store entries when all key columns are NULL, so multiple NULL rows can coexist. If email is mandatory, add NOT NULL; if email is optional yet provided emails must be unique after normalization, this pattern fits well.

Another approach is creating a normalized virtual column and placing a UNIQUE constraint on it:

```sql
ALTER TABLE lab_customers ADD (
    email_normalized GENERATED ALWAYS AS (
        UPPER(TRIM(email))
    ) VIRTUAL
);

ALTER TABLE lab_customers
ADD CONSTRAINT uq_lab_customers_email_norm
UNIQUE (email_normalized);
```

A virtual column gives the normalization rule an explicit name in the schema and makes it directly queryable. Verify Oracle version, collation, and DDL privileges before using.

### 3.3. Choose Keys by Business Semantics, Not Convenience

Email is not always a good identifying key:

- Emails can change or be shared.
- One person can have multiple emails.
- Email may not be provided yet.
- Two source systems may normalize differently.

If the source system supplies stable IDs, `(SOURCE_SYSTEM, EXTERNAL_ID)` is usually better. Email can serve as an additional UNIQUE key if the business genuinely requires unique emails.

## 4. Checking for Duplicates Before Adding Constraints

If a table already contains duplicates, adding a UNIQUE constraint or unique index fails. Inspect the data first.

Queries in sections 4–5 describe handling a legacy table before uniqueness constraints are enabled. If you already added the UNIQUE constraint in section 2.2, the database blocks new duplicates; when practicing legacy cleanup, run these checks/cleanups on a legacy copy or prior to adding the constraint.

### 4.1. Finding Repeated Business Keys

```sql
SELECT
    source_system,
    external_customer_id,
    COUNT(*) AS duplicate_count
FROM lab_customers
GROUP BY source_system, external_customer_id
HAVING COUNT(*) > 1
ORDER BY source_system, external_customer_id;
```

The output identifies key groups appearing more than once. `COUNT(*)` here counts rows, not distinct column values.

### 4.2. Viewing All Rows in Duplicate Groups

```sql
SELECT c.*
FROM lab_customers c
JOIN (
    SELECT source_system, external_customer_id
    FROM lab_customers
    GROUP BY source_system, external_customer_id
    HAVING COUNT(*) > 1
) d
  ON d.source_system = c.source_system
 AND d.external_customer_id = c.external_customer_id
ORDER BY c.source_system,
         c.external_customer_id,
         c.updated_at DESC,
         c.customer_id DESC;
```

This inspection step shows how the rows differ. Never delete immediately upon seeing `COUNT(*) > 1`.

### 4.3. Checking NULLs and Missing Keys

```sql
SELECT COUNT(*) AS missing_business_key_rows
FROM lab_customers
WHERE source_system IS NULL
   OR external_customer_id IS NULL;
```

Rows missing keys cannot be safely matched by business key. Decide whether to repair the data, route it to a review queue, or keep it in an unidentified state. Never merge all NULL rows into a single customer entity.

### 4.4. Common Errors When Adding UNIQUE

If duplicates exist, DDL reports:

```text
ORA-02299: cannot validate (...) - duplicate keys found
```

If an INSERT/UPDATE violates an active unique constraint/index, Oracle reports:

```text
ORA-00001: unique constraint (...) violated
```

These two errors occur at different stages:

- ORA-02299 occurs when validating/enabling a constraint on data already containing duplicates.
- ORA-00001 occurs when a DML operation produces a key colliding with already-protected data.

### 4.5. Preparing Data Before Creating UNIQUE

A typical rollout process includes:

1. Define the business key and normalization rules.
2. Inventory duplicates, NULL keys, and conflicts that cannot auto-merge.
3. Determine the canonical row and map legacy IDs.
4. Reassign foreign keys in child tables to the canonical ID.
5. Delete/archive duplicate rows per retention policy.
6. Re-verify zero duplicates remain.
7. Create the unique index/constraint.
8. Update all write paths to supply complete business keys and handle duplicate key errors.

During cleanup, a concurrent write stream might insert new duplicates after your check. Control writers using a maintenance window, locks/write coordination, or an appropriate migration plan. Never assume a clean check SELECT guarantees data stays clean until DDL runs.

Oracle DDL like CREATE INDEX or ALTER TABLE performs an implicit commit. Do not treat cleanup DML and constraint-creation DDL as a single transaction undoable with ROLLBACK. Separate migration phases, backup/restore plans, and execution timing.

## 5. Selecting the Canonical Record and Cleaning Up Duplicates

When one business key has multiple rows, you need a survivorship rule: which row to keep, which columns to merge, and which references to reassign. A common rule keeps the most recently updated row; if timestamps tie, a unique key acts as tie-breaker.

ROW_NUMBER/DELETE examples in this section assume a legacy table still containing duplicates and not yet protected by a UNIQUE constraint on the business key. Enable the constraint only after cleaning up data and re-verifying.

### 5.1. ROW_NUMBER Establishes Ordering Within Each Group

```sql
SELECT
    customer_id,
    source_system,
    external_customer_id,
    updated_at,
    ROW_NUMBER() OVER (
        PARTITION BY source_system, external_customer_id
        ORDER BY updated_at DESC NULLS LAST,
                 customer_id DESC
    ) AS rn
FROM lab_customers;
```

Meaning:

- PARTITION BY groups rows by business key.
- The row with `RN = 1` is selected to keep under the defined ordering.
- Rows with `RN > 1` are duplicate candidates to handle.
- `CUSTOMER_ID DESC` breaks ties deterministically when `UPDATED_AT` is equal.

Do not rely on ROW_NUMBER if ORDER BY is non-deterministic. If two rows share a timestamp without a tie-breaker, different runs can pick different canonical rows.

### 5.2. Previewing Rows to Be Removed

```sql
WITH ranked_customers AS (
    SELECT
        customer_id,
        source_system,
        external_customer_id,
        updated_at,
        ROW_NUMBER() OVER (
            PARTITION BY source_system, external_customer_id
            ORDER BY updated_at DESC NULLS LAST,
                     customer_id DESC
        ) AS rn
    FROM lab_customers
)
SELECT *
FROM ranked_customers
WHERE rn > 1
ORDER BY source_system, external_customer_id, rn;
```

Run this SELECT before DELETE. Review flagged rows against business rules, foreign keys, change history, and columns that cannot auto-merge.

### 5.3. Deleting Duplicates by ROWID After Confirmation

Once confirmed that only `RN = 1` rows should remain, delete the others:

```sql
DELETE FROM lab_customers c
WHERE c.ROWID IN (
    SELECT rid
    FROM (
        SELECT
            ROWID AS rid,
            ROW_NUMBER() OVER (
                PARTITION BY source_system, external_customer_id
                ORDER BY updated_at DESC NULLS LAST,
                         customer_id DESC
            ) AS rn
        FROM lab_customers
        WHERE source_system IS NOT NULL
          AND external_customer_id IS NOT NULL
    )
    WHERE rn > 1
);
```

ROWID identifies a row's physical location in the table per Oracle mechanics. Here it acts as a temporary locator for a one-off cleanup; **never use ROWID as a business key or store it as a permanent identifier**. For partitioned, clustered, or specialized tables, understand ROWID behavior and test on the exact object type.

The example intentionally excludes rows missing business keys so NULLs are not lumped into one duplicate group. After checking the deleted row count, verify again:

```sql
SELECT source_system, external_customer_id, COUNT(*) AS row_count
FROM lab_customers
WHERE source_system IS NOT NULL
  AND external_customer_id IS NOT NULL
GROUP BY source_system, external_customer_id
HAVING COUNT(*) > 1;
```

If zero rows are returned, data satisfies uniqueness for the checked key at query time.

### 5.4. Child Data Referencing Duplicate Rows

If ORDERS or CONTACTS reference CUSTOMER_ID, you cannot arbitrarily delete duplicate customers before reassigning foreign keys:

1. Select the canonical CUSTOMER_ID for each business key.
2. Build a mapping `duplicate_customer_id -> canonical_customer_id`.
3. Update child tables to point to the canonical ID.
4. Verify no references remain to IDs slated for deletion.
5. Delete duplicate rows.
6. Add/validate the UNIQUE constraint to prevent duplicates from returning.

Example temporary mapping:

```sql
WITH ranked AS (
    SELECT
        customer_id,
        source_system,
        external_customer_id,
        ROW_NUMBER() OVER (
            PARTITION BY source_system, external_customer_id
            ORDER BY updated_at DESC NULLS LAST, customer_id DESC
        ) AS rn,
        FIRST_VALUE(customer_id) OVER (
            PARTITION BY source_system, external_customer_id
            ORDER BY updated_at DESC NULLS LAST, customer_id DESC
        ) AS canonical_customer_id
    FROM lab_customers
    WHERE source_system IS NOT NULL
      AND external_customer_id IS NOT NULL
)
SELECT customer_id AS duplicate_customer_id,
       canonical_customer_id
FROM ranked
WHERE rn > 1;
```

Save the mapping in a staging/audit table if needed to update multiple child tables. Before running UPDATE, confirm each duplicate maps to exactly one canonical ID and inspect related constraints/triggers.

### 5.5. Merging Differing Attributes

Keeping only the newest row is not always right. An older row might hold the phone number while a newer row holds the email. In that case, define column-level merge rules:

- Take the latest value from a trusted source.
- Prefer non-NULL values.
- Prioritize one source system by trust rank.
- Record change history in an audit table.
- Route unresolvable conflicts to a manual review queue.

`MAX(email)` or `MAX(display_name)` are not meaningful survivorship rules just because they make SQL run. Picking authoritative data is a business decision; SQL merely executes it.

## 6. What Is an Idempotent Operation?

An operation is idempotent when executing it once or repeating it multiple times with the same request leads to the same final business state, without unintended extra side effects.

Examples:

| Operation | Can be idempotent? | Reason |
| --- | --- | --- |
| Set order status to PAID | Yes, under same conditions and no repeated side effects | Assigning the same value repeatedly leaves final state unchanged |
| Add 100 to balance | No | Each execution increases balance by another 100 |
| Record event with unique EVENT_ID | Yes, if DB protects EVENT_ID and handles duplicates properly | Same event does not create two rows |
| Send confirmation email on every API retry | No | Side effect repeats even if database data stays unchanged |
| Upsert profile by source key | Possibly | Requires unique key and deterministic UPDATE rules |

Idempotent does not mean "SQL succeeds without error every time". A retry may hit a duplicate key and return "already processed"; what matters is that state and business effects do not multiply.

### 6.1. Distinguishing Idempotency from Uniqueness

- A UNIQUE constraint ensures a key does not appear across multiple rows.
- Idempotency ensures repeating the same request does not repeat its effects.
- An idempotent operation usually needs a unique key to identify the request attempt, yet a unique constraint alone is insufficient to guard all side effects.

For instance, a unique CUSTOMER_ID does not prevent two submissions of the same create-customer request if the application generates a fresh CUSTOMER_ID each time. You need a business key or idempotency key stable across retries.

### 6.2. Do Not Use a Sequence as an Idempotency Key

A sequence generates a new value on every NEXTVAL call. If the application times out after INSERT without receiving a response, a retry generates a new ID and inserts a second row. Sequences work well as surrogate primary keys, not for identifying repeated requests.

Use a stable key generated before sending the request (such as a request UUID) or a source-supplied business key, and place UNIQUE/PRIMARY KEY on that key. Sequences can still assign internal IDs once a request is confirmed new.

## 7. Safe INSERT: Do Not Just SELECT Before INSERT

An easy-to-write pattern that is unsafe under concurrency:

```sql
SELECT COUNT(*)
INTO l_count
FROM lab_customers
WHERE source_system = :source_system
  AND external_customer_id = :external_id;

IF l_count = 0 THEN
    INSERT INTO lab_customers (
        customer_id,
        source_system,
        external_customer_id
    )
    VALUES (
        lab_customer_seq.NEXTVAL,
        :source_system,
        :external_id
    );
END IF;
```

Suppose two sessions run concurrently:

```text
Session A                         Session B
---------                         ---------
MERGE checks: not found            MERGE checks: not found
Enters NOT MATCHED                 Enters NOT MATCHED
INSERTs row                        INSERTs same business key
COMMIT                             Waits for lock/uniqueness check
                                   Receives ORA-00001
```

Without a UNIQUE constraint, both rows can be inserted. With a UNIQUE constraint, one session wins and the other hits a duplicate key error. Therefore, a pre-SELECT cannot replace a constraint; between SELECT and INSERT there is always a window where state can change.

### 7.1. Use a UNIQUE Constraint as the Final Barrier

Make the business key unique:

If you already added this constraint in section 2.2 or attached it to the unique index in section 2.4, do not re-run the DDL below.

```sql
ALTER TABLE lab_customers
ADD CONSTRAINT uq_lab_customers_source
UNIQUE (source_system, external_customer_id);
```

Then the application can attempt INSERT. If it receives a duplicate key from the expected constraint, re-read the existing row and treat the request as already handled or transition to an UPDATE per rules. Never catch and ignore all database errors; connection errors, NOT NULL errors, or other constraint failures must still be raised.

### 7.2. Handling Duplicate Keys in PL/SQL

A simple pattern:

```sql
DECLARE
    l_customer_id lab_customers.customer_id%TYPE;
BEGIN
    INSERT INTO lab_customers (
        customer_id,
        source_system,
        external_customer_id,
        display_name,
        updated_at
    )
    VALUES (
        lab_customer_seq.NEXTVAL,
        :source_system,
        :external_customer_id,
        :display_name,
        SYSTIMESTAMP
    )
    RETURNING customer_id INTO l_customer_id;

    DBMS_OUTPUT.PUT_LINE('CREATED=' || l_customer_id);
EXCEPTION
    WHEN DUP_VAL_ON_INDEX THEN
        SELECT customer_id
        INTO l_customer_id
        FROM lab_customers
        WHERE source_system = :source_system
          AND external_customer_id = :external_customer_id;

        DBMS_OUTPUT.PUT_LINE('ALREADY_EXISTS=' || l_customer_id);
END;
/
```

This example handles duplicates on that exact business key in a lab environment. In real systems, `DUP_VAL_ON_INDEX` can be triggered by any unique constraint/index on the table. Only treat the error as "already exists" after confirming it was the expected constraint and successfully finding the row by business key; if not found, re-raise the error so other bugs are not masked.

In JDBC applications, the equivalent approach catches the unique violation, identifies the constraint/SQL state per driver API, and re-reads by business key. Avoid parsing localized error message strings when structured error metadata is available.

## 8. MERGE: Insert-or-Update by Key

MERGE combines a matching condition with UPDATE or INSERT actions. It is widely used for source data synchronization and upserts.

### 8.1. Basic Syntax

```sql
MERGE INTO target_table t
USING source_table s
ON (t.business_key = s.business_key)
WHEN MATCHED THEN
    UPDATE SET
        t.value_col = s.value_col
WHEN NOT MATCHED THEN
    INSERT (business_key, value_col)
    VALUES (s.business_key, s.value_col);
```

ON determines whether two rows share the same business identity:

- MATCHED: target row exists; execute UPDATE if an UPDATE branch is present.
- NOT MATCHED: no target row yet; execute INSERT if an INSERT branch is present.

### 8.2. Upserting Customers by Source ID

```sql
MERGE INTO lab_customers t
USING (
    SELECT
        :source_system AS source_system,
        :external_customer_id AS external_customer_id,
        :email AS email,
        :display_name AS display_name
    FROM dual
) s
ON (
    t.source_system = s.source_system
    AND t.external_customer_id = s.external_customer_id
)
WHEN MATCHED THEN
    UPDATE SET
        t.email = s.email,
        t.display_name = s.display_name,
        t.updated_at = SYSTIMESTAMP
WHEN NOT MATCHED THEN
    INSERT (
        customer_id,
        source_system,
        external_customer_id,
        email,
        display_name,
        updated_at
    )
    VALUES (
        lab_customer_seq.NEXTVAL,
        s.source_system,
        s.external_customer_id,
        s.email,
        s.display_name,
        SYSTIMESTAMP
    );
```

With the same business key, the first call creates the row; subsequent calls update that row instead of creating a new one. A UNIQUE constraint on `(SOURCE_SYSTEM, EXTERNAL_CUSTOMER_ID)` is still needed to protect data from other writers and non-MERGE write paths.

### 8.3. MERGE Is Only Idempotent When UPDATE Rules Are Stable

A MERGE may fail to be idempotent in effect if each execution:

- Adds to an existing column (`t.qty = t.qty + s.qty`).
- Writes a fresh timestamp that changes state even when payload is unchanged.
- Fires an audit event or notification trigger on every match.
- Overwrites newer data with an older payload arriving on a late retry.

If you want "snapshot state synchronization", UPDATE should deterministically assign target values rather than accumulating repeatedly. If you want delta event processing, require a unique EVENT_ID so the same event is never applied twice.

Example updating only when the new payload actually differs:

```sql
MERGE INTO lab_customers t
USING (
    SELECT
        :source_system AS source_system,
        :external_customer_id AS external_customer_id,
        :email AS email,
        :display_name AS display_name
    FROM dual
) s
ON (
    t.source_system = s.source_system
    AND t.external_customer_id = s.external_customer_id
)
WHEN MATCHED THEN
    UPDATE SET
        t.email = s.email,
        t.display_name = s.display_name,
        t.updated_at = SYSTIMESTAMP
    WHERE DECODE(t.email, s.email, 0, 1) = 1
       OR DECODE(t.display_name, s.display_name, 0, 1) = 1
WHEN NOT MATCHED THEN
    INSERT (
        customer_id, source_system, external_customer_id,
        email, display_name, updated_at
    )
    VALUES (
        lab_customer_seq.NEXTVAL, s.source_system,
        s.external_customer_id, s.email,
        s.display_name, SYSTIMESTAMP
    );
```

Here DECODE compares NULLs as equal per DECODE rules, skipping UPDATE when both columns are unchanged. Still review other columns, triggers, and actual timestamp rules; never assume that leaving two display columns unchanged guarantees all side effects are idempotent.

## 9. Concurrency During MERGE and Handling Duplicate Races

MERGE expresses matched/not-matched logic in one statement, yet it is not an exclusive lock on a business key across all sessions. Two sessions can evaluate a nonexistent key concurrently and both enter the NOT MATCHED branch. When both attempt to INSERT, the UNIQUE constraint blocks the second row and one session receives ORA-00001.

### 9.1. Illustrating the Race Condition

Suppose `(CRM_A, 9001)` does not exist yet:

```text
Session A                         Session B
---------                         ---------
MERGE checks: not found            MERGE checks: not found
Enters NOT MATCHED                 Enters NOT MATCHED
INSERTs row                        INSERTs same business key
COMMIT                             Waits for lock/uniqueness check
                                   Receives ORA-00001
```

The UNIQUE constraint guarantees final data never holds two rows with the same key. It does not guarantee both MERGE statements return success. Applications must handle this race explicitly: re-read the canonical row, attempt a conditional UPDATE if appropriate, or perform bounded retries.

### 9.2. Duplicate Race Handling Pattern

A common strategy:

1. Attempt MERGE by business key.
2. If it succeeds, complete the transaction.
3. If ORA-00001 is raised on the exact business-key unique constraint, re-read the row by key.
4. Compare version/timestamp/payload per synchronization rules.
5. If needed, run a conditional UPDATE; otherwise, treat the request as already processed.
6. If the error did not come from the expected constraint or the row is not found, raise and log the error.

Never retry infinitely. Use bounded retry counts with jittered backoff at the application tier and log final failures to avoid retry storms under overload.

### 9.3. Preventing Older Retries from Overwriting Newer Data

Suppose event version 12 already updated the profile. An older message with version 11 is redelivered afterward. If MERGE updates unconditionally, newer data gets overwritten.

Add a version condition:

```sql
MERGE INTO lab_customers t
USING (
    SELECT
        :source_system AS source_system,
        :external_customer_id AS external_customer_id,
        :source_version AS source_version,
        :email AS email
    FROM dual
) s
ON (
    t.source_system = s.source_system
    AND t.external_customer_id = s.external_customer_id
)
WHEN MATCHED THEN
    UPDATE SET
        t.email = s.email,
        t.source_version = s.source_version,
        t.updated_at = SYSTIMESTAMP
    WHERE s.source_version > t.source_version
WHEN NOT MATCHED THEN
    INSERT (
        customer_id, source_system, external_customer_id,
        source_version, email, updated_at
    )
    VALUES (
        lab_customer_seq.NEXTVAL, s.source_system,
        s.external_customer_id, s.source_version,
        s.email, SYSTIMESTAMP
    );
```

This example requires adding `SOURCE_VERSION` to the lab table before running. Version comparison is only valid if the source system supplies reliably ordered versions; otherwise use governed timestamps, source sequences, or an appropriate conflict-resolution mechanism.

## 10. Idempotency Keys for APIs, Batches, and Message Consumers

A business key identifies an entity (such as a customer). An idempotency key identifies a **specific request or event**. One customer can have hundreds of distinct update requests, so never substitute a business key for a request key.

### 10.1. Designing a Ledger Table for Processed Requests

A ledger table can store the request key, client scope, payload hash, and outcome:

```sql
CREATE TABLE lab_request_ledger (
    client_id       VARCHAR2(80) NOT NULL,
    idempotency_key VARCHAR2(120) NOT NULL,
    request_hash    VARCHAR2(64) NOT NULL,
    result_code     NUMBER(3),
    result_body     CLOB,
    completed_at    TIMESTAMP,
    CONSTRAINT pk_lab_request_ledger
        PRIMARY KEY (client_id, idempotency_key)
);
```

A composite key avoids collisions between two independent clients generating the same key string. Depending on the API, key scoping can be tenant + operation + key or an equivalent scope.

`REQUEST_HASH` is the hash of a canonicalized payload (such as JSON with normalized field order and value representation). The same idempotency key with a different payload must be treated as a conflict, not served the cached response as if the requests matched.

### 10.2. Request Processing Transaction

Flow pattern within a single database transaction:

```text
BEGIN TRANSACTION
    1. INSERT (client_id, idempotency_key, request_hash)
       into LAB_REQUEST_LEDGER.
    2. Apply business change in the same transaction.
    3. Save result_code, result_body, and completed_at.
COMMIT

If any step fails:
    ROLLBACK entire ledger row and business change.
```

The crucial point is committing the ledger row and business change together. If the process crashes before COMMIT, both roll back and retries can run safely. If COMMIT succeeds yet the response drops on the wire, a retry hits the existing idempotency key and returns the saved outcome.

Do not commit the ledger row in a separate transaction before performing the business update unless you have a lease/recovery mechanism. If a `PROCESSING` row commits and the worker dies, the system needs a way to detect stuck requests and take over safely.

### 10.3. Rules When the Key Already Exists

When inserting into the ledger hits a duplicate key:

- Read the ledger row by `(CLIENT_ID, IDEMPOTENCY_KEY)`.
- If `REQUEST_HASH` matches and the request is complete, return the stored result.
- If `REQUEST_HASH` differs, return a conflict error (such as HTTP 409) because the same key was reused for a different payload.
- If the status is still processing in an architecture with separate state commits, apply wait/lease-check rules; never execute the business logic a second time.

In a single-transaction design, a concurrent transaction using the same key waits for the first transaction to commit or roll back. Once the first commits, the second INSERT gets a duplicate key error and reads the committed result. If the first rolls back, the second succeeds and becomes the active processor.

### 10.4. Idempotency for Balance-Modifying Events

An example of an additive update that is not idempotent if re-run:

```sql
UPDATE lab_accounts
SET balance = balance + :amount
WHERE account_id = :account_id;
```

If the message is redelivered, the balance gets credited again. Create a processed-events table with a unique `EVENT_ID`:

```sql
CREATE TABLE lab_processed_events (
    event_id       VARCHAR2(120)
        CONSTRAINT pk_lab_processed_events PRIMARY KEY,
    account_id     NUMBER(12) NOT NULL,
    amount         NUMBER(14, 2) NOT NULL,
    processed_at   TIMESTAMP NOT NULL
);
```

Within the same transaction:

```sql
INSERT INTO lab_processed_events (
    event_id, account_id, amount, processed_at
)
VALUES (
    :event_id, :account_id, :amount, SYSTIMESTAMP
);

UPDATE lab_accounts
SET balance = balance + :amount
WHERE account_id = :account_id;

COMMIT;
```

If inserting the event succeeds, update the balance and commit. If `event_id` already exists, the duplicate key stops the UPDATE when the application handles the exception/rollback properly. Both operations must share the same transaction so an event is never marked processed without updating the balance, nor the balance updated with the event ledger rolled back.

The SQL snippet above illustrates the transaction body; application/PLSQL code must catch the duplicate key at the right boundary and never proceed to UPDATE if the event INSERT failed.

### 10.5. Side Effects Outside the Database and Transactional Outbox

An Oracle transaction cannot roll back a sent email, an HTTP call to a payment gateway, or a message already published to a broker. If a request both updates the database and calls an external service, this can occur:

1. Database commits successfully.
2. External service receives the request.
3. Client times out before receiving the response.
4. Retry fires again and the external service executes the side effect a second time.

A common pattern is the transactional outbox:

- Inside the business transaction, update the main table and INSERT an outbox event with a unique event key.
- Commit both together.
- A worker reads the outbox, dispatches the message, and marks it sent.
- If the worker retries, the consumer or downstream service also deduplicates by event key.

An outbox ensures the event is recorded atomically with the database change; delivery is typically at-least-once, so consumers still require idempotency. Do not confuse an outbox with end-to-end exactly-once guarantees.

## 11. Cleaning the Source Before MERGE

MERGE requires an unambiguous source set. If the source has multiple rows for the same business key:

- If the target already has a matching row, multiple source rows try to update the same target row; Oracle raises ORA-30926 because it cannot obtain a stable set of rows.
- If the target lacks that row, multiple source rows with the same key enter the INSERT branch and violate the UNIQUE constraint.
- If the source rows carry differing payloads, there is no automatic rule telling which row is newer or authoritative.

### 11.1. Detecting Source Duplicates

Suppose a batch lands in a staging table:

```sql
CREATE TABLE lab_customer_stage (
    stage_row_id NUMBER(12) PRIMARY KEY,
    batch_id     VARCHAR2(80) NOT NULL,
    source_system VARCHAR2(30),
    external_customer_id VARCHAR2(80),
    email        VARCHAR2(320),
    display_name VARCHAR2(160),
    source_version NUMBER(12),
    loaded_at    TIMESTAMP
);
```

Check duplicates within a batch:

```sql
SELECT
    source_system,
    external_customer_id,
    COUNT(*) AS source_rows
FROM lab_customer_stage
WHERE batch_id = :batch_id
GROUP BY source_system, external_customer_id
HAVING COUNT(*) > 1;
```

If staging contains multiple rows for the same business key, decide how to resolve them before MERGE: pick the latest version, merge attributes, or route conflicts to an error table.

### 11.2. Selecting the Single Source Row with the Highest Version

```sql
WITH ranked_source AS (
    SELECT
        s.*,
        ROW_NUMBER() OVER (
            PARTITION BY source_system, external_customer_id
            ORDER BY source_version DESC NULLS LAST,
                     loaded_at DESC NULLS LAST,
                     stage_row_id DESC
        ) AS rn
    FROM lab_customer_stage s
    WHERE batch_id = :batch_id
      AND source_system IS NOT NULL
      AND external_customer_id IS NOT NULL
)
SELECT *
FROM ranked_source
WHERE rn = 1;
```

This is a sample rule: higher version wins; if versions tie, later load time wins; finally `stage_row_id` provides deterministic ordering. Only use this rule when `source_version` has business meaning. If two rows share the same version yet have conflicting payloads, flagging an error is often safer than silently picking the later load timestamp.

### 11.3. MERGE from a Deduplicated Source

```sql
MERGE INTO lab_customers t
USING (
    SELECT
        source_system,
        external_customer_id,
        email,
        display_name
    FROM (
        SELECT
            s.*,
            ROW_NUMBER() OVER (
                PARTITION BY source_system, external_customer_id
                ORDER BY source_version DESC NULLS LAST,
                         loaded_at DESC NULLS LAST,
                         stage_row_id DESC
            ) AS rn
        FROM lab_customer_stage s
        WHERE batch_id = :batch_id
          AND source_system IS NOT NULL
          AND external_customer_id IS NOT NULL
    )
    WHERE rn = 1
) s
ON (
    t.source_system = s.source_system
    AND t.external_customer_id = s.external_customer_id
)
WHEN MATCHED THEN
    UPDATE SET
        t.email = s.email,
        t.display_name = s.display_name,
        t.updated_at = SYSTIMESTAMP
WHEN NOT MATCHED THEN
    INSERT (
        customer_id, source_system, external_customer_id,
        email, display_name, updated_at
    )
    VALUES (
        lab_customer_seq.NEXTVAL, s.source_system,
        s.external_customer_id, s.email,
        s.display_name, SYSTIMESTAMP
    );
```

The MERGE source now has at most one row per business key in the batch. The target still needs a unique constraint; source deduplication does not guard against concurrent writers.

### 11.4. Do Not Use DISTINCT to Arbitrarily Pick One Row

`SELECT DISTINCT source_system, external_customer_id, email ...` only eliminates rows identical across all selected columns. If the same business key has two different emails, both rows survive and MERGE still hits multiple source rows for one key.

DISTINCT cannot replace survivorship rules. Use ROW_NUMBER with a meaningful ORDER BY, GROUP BY with clear aggregation rules, or route conflicts to manual resolution.

## 12. Insert-If-Absent Alternatives and Their Limits

### 12.1. INSERT ... WHERE NOT EXISTS

You can write:

```sql
INSERT INTO lab_customers (
    customer_id, source_system, external_customer_id, display_name
)
SELECT
    lab_customer_seq.NEXTVAL,
    :source_system,
    :external_customer_id,
    :display_name
FROM dual
WHERE NOT EXISTS (
    SELECT 1
    FROM lab_customers c
    WHERE c.source_system = :source_system
      AND c.external_customer_id = :external_customer_id
);
```

This avoids INSERT if the row already exists as of the statement's read snapshot. However, two concurrent sessions can both evaluate NOT EXISTS as true and both attempt INSERT. Thus you still need a UNIQUE constraint and ORA-00001 handling. NOT EXISTS here is a logical filter, not an exclusive lock.

### 12.2. MERGE vs. Insert-If-Absent

| Need | Approach |
| --- | --- |
| Create only if absent, never update existing rows | Insert-if-absent or INSERT catching duplicate key |
| Create new or synchronize current values | MERGE |
| Process an event exactly once | INSERT event ledger with unique EVENT_ID, then apply effect in same transaction |
| Sync a batch with multiple source rows | Deduplicate/validate staging first, then MERGE |
| Increment/decrement by event delta | Unique event key + transaction; not plain cumulative MERGE |

Choose syntax according to business semantics. Regardless of approach, database uniqueness constraints remain the final line of defense.

## 13. Managing Transactions and Batch Reruns

Idempotency depends on transaction boundaries. Define clearly which pieces must commit together.

### 13.1. Commit Business Row and Processed Marker Together

For a database-only event:

```text
BEGIN
    INSERT processed_event(event_id)   -- unique key
    UPDATE business_table              -- apply event
    INSERT audit_row (if needed)
COMMIT
```

If UPDATE fails, roll back `processed_event` too. If commit succeeds, retries see `processed_event` and skip reapplying the event. Do not split these two operations into separate independent transactions without corresponding recovery mechanics.

### 13.2. Savepoints When Processing Multiple Records

A batch may process many records in one transaction or commit in chunks. For each record, you can use SAVEPOINT to isolate recoverable business errors:

```sql
SAVEPOINT before_one_record;

-- Try applying one record here.

-- If record is invalid and may be skipped:
ROLLBACK TO before_one_record;
```

SAVEPOINT only rolls back changes after the savepoint within the current transaction. It does not replace idempotency keys and cannot undo external side effects. If a record already committed in an earlier chunk, reruns must recognize it via its business/event key.

### 13.3. Re-Runnable Batches

An idempotent batch should have:

- A `BATCH_ID` or deterministic source repeatable across runs.
- Unique business keys/event keys per source record.
- Staging deduplicated and validated before merging.
- Per-record status or audit tables tracking succeeded/failed records.
- Clear transaction boundaries (per record, per chunk, or per batch).
- A way to resume from unfinished records without reapplying committed effects.

Do not rely on "row 500 in the file" as a stable identifier if file ordering can change. Use source record IDs or deterministic keys derived from business data.

### 13.4. Sequences Can Have Gaps

Oracle sequences are non-transactional with respect to rolling back NEXTVAL values. A failed INSERT or rolled-back transaction still consumes sequence numbers. This is normal behavior; IDs do not need to be contiguous to be unique.

Do not search for duplicates by assuming IDs must be consecutive, never reuse issued IDs, and never infer committed record counts from sequence values. Idempotency must rest on stable request/event/business keys.

## 14. Inspecting Constraints in Oracle

After creating constraints, inspect metadata in the data dictionary.

### 14.1. Viewing Table Constraints

```sql
SELECT
    constraint_name,
    constraint_type,
    status,
    validated,
    deferrable,
    deferred
FROM user_constraints
WHERE table_name = 'LAB_CUSTOMERS'
ORDER BY constraint_name;
```

Constraint types include:

| CONSTRAINT_TYPE | Meaning |
| --- | --- |
| P | PRIMARY KEY |
| U | UNIQUE |
| R | FOREIGN KEY |
| C | CHECK (including NOT NULL represented as check metadata) |

STATUS shows whether the constraint is ENABLED or DISABLED; VALIDATED shows whether existing data has been verified against the constraint. Check both—never see a constraint name in the schema and assume data is fully protected.

### 14.2. Viewing Columns of a Composite Key

```sql
SELECT
    constraint_name,
    column_name,
    position
FROM user_cons_columns
WHERE table_name = 'LAB_CUSTOMERS'
ORDER BY constraint_name, position;
```

For composite keys, POSITION shows column order inside the constraint. Cross-check the column list against the agreed business key.

### 14.3. Viewing Related Indexes

```sql
SELECT
    index_name,
    uniqueness,
    status
FROM user_indexes
WHERE table_name = 'LAB_CUSTOMERS'
ORDER BY index_name;
```

Inspect index columns:

```sql
SELECT
    index_name,
    column_name,
    column_position,
    descend
FROM user_ind_columns
WHERE table_name = 'LAB_CUSTOMERS'
ORDER BY index_name, column_position;
```

Function-based indexes store their expressions in corresponding dictionary views (such as `USER_IND_EXPRESSIONS`). When using normalization expressions, check the actual enforced expression rather than just the index name.

### 14.4. DEFERRABLE and Uniqueness Check Timing

By default, PRIMARY KEY/UNIQUE constraints are checked immediately per statement. A constraint can be declared DEFERRABLE to defer checking until transaction end (or configured deferred state):

```sql
ALTER TABLE lab_example
ADD CONSTRAINT uq_lab_example_code
UNIQUE (code)
DEFERRABLE INITIALLY DEFERRED;
```

This helps when a transaction modifies multiple rows through an intermediate state that temporarily violates uniqueness, while the final state is valid. It does not allow committing duplicates. Use only when the business logic requires it; deferring checks pushes errors to COMMIT time, making error handling harder.

## 15. Hands-On Scenario from Staging to Target Data

### Step 1 — Create Target Table and Sequence

```sql
CREATE TABLE lab_customers (
    customer_id NUMBER(12)
        CONSTRAINT pk_lab_customers PRIMARY KEY,
    source_system VARCHAR2(30) NOT NULL,
    external_customer_id VARCHAR2(80) NOT NULL,
    email VARCHAR2(320),
    display_name VARCHAR2(160),
    source_version NUMBER(12),
    updated_at TIMESTAMP
);

CREATE SEQUENCE lab_customer_seq START WITH 1 INCREMENT BY 1;

ALTER TABLE lab_customers
ADD CONSTRAINT uq_lab_customers_source
UNIQUE (source_system, external_customer_id);
```

In a standalone run, create the table/constraint only once. Similar DDL snippets earlier illustrated alternatives; do not re-run DDL adding the same constraint if it already exists.

### Step 2 — Create Staging and Load a Batch

If you have not created `LAB_CUSTOMER_STAGE` from section 11 yet, run its DDL. Then load:

```sql
INSERT INTO lab_customer_stage (
    stage_row_id, batch_id, source_system,
    external_customer_id, email, display_name,
    source_version, loaded_at
)
VALUES (
    1, 'BATCH-001', 'CRM_A', '9001',
    'an@example.com', 'An Nguyen', 1, SYSTIMESTAMP
);

INSERT INTO lab_customer_stage (
    stage_row_id, batch_id, source_system,
    external_customer_id, email, display_name,
    source_version, loaded_at
)
VALUES (
    2, 'BATCH-001', 'CRM_A', '9001',
    'an.new@example.com', 'An Nguyen', 2, SYSTIMESTAMP
);

INSERT INTO lab_customer_stage (
    stage_row_id, batch_id, source_system,
    external_customer_id, email, display_name,
    source_version, loaded_at
)
VALUES (
    3, 'BATCH-001', 'CRM_B', '7002',
    'binh@example.com', 'Binh Tran', 1, SYSTIMESTAMP
);

COMMIT;
```

The two `CRM_A` rows share the same business key with different versions. The sample rule picks version 2.

### Step 3 — Check Duplicates in the Batch

```sql
SELECT source_system, external_customer_id, COUNT(*) AS row_count
FROM lab_customer_stage
WHERE batch_id = 'BATCH-001'
GROUP BY source_system, external_customer_id
HAVING COUNT(*) > 1;
```

The output should show `CRM_A / 9001` has two rows. Do not treat them as two separate customers.

### Step 4 — MERGE from One Source Row per Business Key

Run the MERGE query from section 11.3 with `batch_id = 'BATCH-001'`. The target will contain two customers: `CRM_A / 9001` with version 2 and `CRM_B / 7002` with version 1.

### Step 5 — Re-Run the Same Batch

Re-run the exact same MERGE with the same `batch_id`. No additional rows should be created because the target already holds those business keys. Columns are reassigned from the source payload. If timestamp is assigned `SYSTIMESTAMP`, timestamps change; decide whether that side effect is acceptable. To keep a batch completely no-op when payload is identical, add an UPDATE filter comparing values or use a version predicate.

### Step 6 — Verify Uniqueness and Results

```sql
SELECT source_system, external_customer_id, COUNT(*) AS row_count
FROM lab_customers
GROUP BY source_system, external_customer_id
HAVING COUNT(*) > 1;

SELECT *
FROM lab_customers
ORDER BY source_system, external_customer_id;
```

The duplicate query must return zero rows. Verify versions and payloads of the canonical records match the rules.

## 16. Testing Idempotency and Concurrency

An operation should only be called idempotent after testing multiple execution paths, not just a single successful run.

### 16.1. Running the Same Input Twice

Record initial state, run the batch/request the first time, and save row counts and outputs. Re-run the exact same input with the same business key/idempotency key, then compare:

- Did business row counts grow unexpectedly?
- Were totals/balances added twice?
- Did audit/outbox events multiply?
- Did timestamps/versions change according to intended policy?
- Was the returned response consistent?

### 16.2. Testing Same Key with Different Payload

Send the same idempotency key with a different payload. The system must detect a conflict, never silently returning the old result or applying the second payload under the same request ID.

### 16.3. Testing Two Concurrent Sessions

Open two Oracle sessions and send the same business key nearly simultaneously:

1. Clear test data or pick a fresh key.
2. Execute the same MERGE/INSERT in both sessions.
3. Commit the first session.
4. Observe whether the second session waits and then receives ORA-00001.
5. Confirm the target table still has only one row for that business key.
6. Verify the application handles the duplicate race cleanly without repeating side effects.

Never test concurrency in production by generating arbitrary load. Use a test schema and data that can be wiped/restored.

### 16.4. Testing Timeouts Around COMMIT

Simulate these scenarios:

- Client disconnects before the database commits.
- Database commits successfully, yet response never reaches client.
- Worker crashes after reading a message but before committing.
- Worker commits successfully, yet crashes before acknowledging the message.

The design must distinguish "not committed" from "committed, caller missed response". An idempotency ledger/event key lets retries look up the committed outcome.

## 17. Common Errors and Pitfalls

| Symptom | Cause | Resolution |
| --- | --- | --- |
| ORA-02299 when adding UNIQUE | Existing data contains duplicates | Group, pick canonical row, clean data, then create constraint |
| ORA-00001 on INSERT | Business key already exists or concurrent writer | Identify offending constraint, re-read by key, handle per policy |
| ORA-00001 on MERGE | Two sessions concurrently insert new key or conflicting source keys | Keep unique constraint; handle races and deduplicate source |
| ORA-30926 on MERGE | Multiple source rows hit same target row or unstable source | Pick one source row/key or aggregate source first |
| Data still duplicates despite PK | PK only enforces technical ID, not business key | Add UNIQUE constraint on business key |
| Unique email still allows case/space variants | Constraint checks raw stored value, unnormalized | Function-based unique index or virtual normalized column |
| Multiple NULL rows in unique key | UNIQUE allows NULL per Oracle rules | Add NOT NULL if business key is mandatory |
| Retries create extra rows | Each retry generates a new ID or lacks idempotency key | Use stable request/event key and unique constraint |
| Balance credited twice | Delta UPDATE re-ran without event ledger | Record unique EVENT_ID and update in same transaction |
| MERGE overwrites newer data | Stale retry lacks version check | Use version/timestamp predicate and conflict rules |
| Batch MERGE fails even when target lacks key | Staging has multiple rows for the same key | Deduplicate or resolve source conflicts before MERGE |
| Deleting duplicates breaks references | Child tables still point to deleted ID | Reassign FKs to canonical ID before deleting |
| Batch rerun duplicates audit/outbox | External side effect not idempotent | Use event keys, outbox, and consumer dedup |
| ROLLBACK does not restore sequence | NEXTVAL is non-transactional | Accept gaps; do not use sequences for dedup |

## 18. Best Practices

1. **Define business keys before writing SQL.** Do not confuse surrogate primary keys with business identity.
2. **Use UNIQUE constraints so the database enforces uniqueness.** Pre-checking with SELECT cannot stop race conditions.
3. **Use NOT NULL on mandatory key components.** Never use NULL to represent an unknown identifier while expecting full uniqueness.
4. **Normalize consistently.** If trimming/case-folding is the rule, apply it in both write paths and database constraints.
5. **Clean up data using deterministic survivorship rules.** ROW_NUMBER needs an ORDER BY with a tie-breaker.
6. **Preserve referential integrity.** Reassign foreign keys to the canonical ID before deleting duplicate parents.
7. **Deduplicate the source before MERGE.** One source row per business key within a batch.
8. **Never assume MERGE handles concurrency on its own.** Keep UNIQUE constraints and handle ORA-00001 by root cause.
9. **Design retries with stable keys.** Never use sequence NEXTVAL as an idempotency key.
10. **Commit markers and business effects in the same transaction.** If one commits without the other, retries corrupt state.
11. **Verify payload when the key already exists.** Same key, different payload is a conflict requiring explicit handling.
12. **Decouple external side effects.** Use an outbox and require consumers/external services to support deduplication.
13. **Test reruns and two concurrent sessions.** A single solo run does not prove idempotency.
14. **Monitor constraint status and audits.** Verify constraints are genuinely ENABLED/VALIDATED as intended.

## 19. Self-Check Questions

1. Are two rows identical across all display columns guaranteed to represent the same business entity?
2. Why is a surrogate primary key insufficient to prevent importing the same customer twice?
3. How does a UNIQUE constraint differ from a PRIMARY KEY?
4. When is NOT NULL needed alongside UNIQUE?
5. What does a function-based unique index with `UPPER(TRIM(email))` protect?
6. Why must email normalization rules be aligned with the business before creating an index?
7. How does ORA-02299 differ from ORA-00001?
8. Why does ROW_NUMBER need a unique tie-breaker when picking a canonical row?
9. Why must foreign keys be reassigned to the canonical customer before deleting duplicates?
10. How does idempotency differ from uniqueness?
11. Why does `SELECT NOT EXISTS` followed by `INSERT` still suffer from race conditions?
12. How does MERGE handle MATCHED and NOT MATCHED?
13. Why can MERGE still receive ORA-00001 when two sessions concurrently insert a new business key?
14. How can ORA-30926 occur when staging has multiple source rows for a single target key?
15. Why is `UPDATE balance = balance + amount` not idempotent when an event is redelivered?
16. Which attributes should scope an idempotency key?
17. Why must the same idempotency key with a different request hash be treated as a conflict?
18. Why should the ledger row and business update commit in the same transaction?
19. What problem does a transactional outbox solve, and why do consumers still need deduplication?
20. Why can sequences have gaps after rollbacks?

## 20. Mental Model

```text
DEFINE IDENTITY
    │
    ├── Surrogate PK: identifies row in database
    ├── Business UNIQUE: identifies business entity
    └── Idempotency key: identifies retried request/event
    │
    ▼
PREVENT DUPLICATES
    │
    ├── NOT NULL for mandatory keys
    ├── UNIQUE constraint / unique index
    └── Consistent key normalization
    │
    ▼
CLEAN UP LEGACY DATA
    │
    ├── GROUP BY / HAVING to detect
    ├── ROW_NUMBER to pick canonical row
    ├── Reassign FKs and merge attributes
    └── Delete/archive extra rows then validate constraint
    │
    ▼
RETRY-SAFE WRITES
    │
    ├── MERGE / INSERT by business key
    ├── Deduplicate source before MERGE
    ├── Handle ORA-00001 and concurrency races
    ├── Ledger + business update in same transaction
    └── Outbox for external side effects
    │
    ▼
VERIFY
    ├── Run same input multiple times
    ├── Same key, different payload
    ├── Two concurrent sessions
    └── Timeout before/after COMMIT
```

**Key takeaway:** UNIQUE constraints protect data identity; idempotency keys protect effects when the same request is resent. MERGE is useful for upserts, yet it does not replace constraints, does not automatically fix source duplicates, and does not guarantee side effects happen only once. Define accurate business keys, clean up duplicates by deterministic rules, keep markers and business changes in the same transaction, and test both retries and concurrency.
