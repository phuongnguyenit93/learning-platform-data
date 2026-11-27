# ALTER TABLE: Adding, Modifying, Dropping Columns, and Converting Data in Oracle Database

Throughout an application's lifecycle, table structures continuously evolve: a screen needs an email field, a customer name column is too short, an old attribute must be renamed, or a price field stored as text must be converted to `NUMBER`. Oracle provides **`ALTER TABLE`** to change table definitions without necessarily recreating the entire table. However, **changing a column definition does not automatically transform existing data or application code**. A DDL statement that finishes in seconds on a tiny table can significantly impact locks, redo/undo, constraints, and dependent objects on a large table.

This lesson belongs to the **Tables and Constraints** group for Oracle Database and focuses on four operation categories: **adding columns**, **modifying/renaming columns**, **dropping columns**, and **converting existing data**. The conversion section emphasizes the *expand → backfill → validate → cutover → contract* workflow, which is valuable when upgrading schemas while applications remain in use.

After completing this lesson, you will be able to:

- Write `ALTER TABLE ... ADD`, `MODIFY`, `RENAME COLUMN`, `DROP COLUMN`, `SET UNUSED`, and `DROP UNUSED COLUMNS`.
- Distinguish **renaming a column**, **changing datatype/length**, and **converting actual data**.
- Understand the impact of `DEFAULT`, `NOT NULL`, `CHECK`, keys, indexes, views, triggers, and application code.
- Convert a `VARCHAR2` column holding numbers into a `NUMBER` column by adding a new column, validating data, and backfilling safely.
- Inspect structure before and after changes via `USER_TAB_COLUMNS`, `USER_CONSTRAINTS`, and related data dictionary views.
- Explain why Oracle DDL performs an **implicit commit**, why `ROLLBACK` cannot undo structural changes, and how to plan safe migrations.

> **Scope Warning:** The SQL in this lesson uses a lab table `ALTER_TABLE_LAB` that you create inside a **practice PDB/schema**. Never run `DROP COLUMN`, `SET UNUSED`, or datatype-conversion scripts on production tables just to test syntax. These operations can cause data loss or break applications; table ownership and rollout plans must be established first.

## 1. Map of `ALTER TABLE` Operations

Oracle supports many kinds of table modifications. Operations directly involving columns can be grouped as follows:

| Goal | Typical Syntax | Meaning |
| --- | --- | --- |
| Add a column | `ALTER TABLE t ADD (new_col VARCHAR2(100 CHAR));` | Adds a new attribute |
| Add a defaulted mandatory column | `ALTER TABLE t ADD (status VARCHAR2(20) DEFAULT 'NEW' NOT NULL);` | Default value and non-NULL constraint |
| Increase length | `ALTER TABLE t MODIFY (name VARCHAR2(200 CHAR));` | Alters an existing column's attributes |
| Change default value | `ALTER TABLE t MODIFY (status DEFAULT 'PENDING');` | Applies to future inserts per default rules |
| Enforce NOT NULL | `ALTER TABLE t MODIFY (name NOT NULL);` | Forbids NULL values if existing rows satisfy the condition |
| Rename a column | `ALTER TABLE t RENAME COLUMN old_name TO new_name;` | Renames the identifier without transforming data |
| Drop a column directly | `ALTER TABLE t DROP COLUMN old_name;` | Removes the column and its data |
| Mark a column unused | `ALTER TABLE t SET UNUSED (old_name);` | Removes the column logically before physical reclamation |
| Reclaim unused columns | `ALTER TABLE t DROP UNUSED COLUMNS;` | Physically cleans up columns marked `SET UNUSED` |

This is not the entire `ALTER TABLE` grammar: Oracle also supports partitions, storage, index-related operations, constraints, and many other changes. Here we focus strictly on **column evolution** and directly dependent data.

### 1.1. A Table Spans Multiple Layers

~~~text
                   APPLICATION / JDBC / REPORTS
                            |
                  SQL referencing column names
                            |
                            v
                     TABLE DEFINITION
          +-----------------+--------------------+
          | column names    | datatype/length    |
          | NULL/DEFAULT    | CHECK/PK/FK/UNIQUE |
          +-----------------+--------------------+
                            |
                   ACTUAL DATA IN ROWS
                            |
                indexes, views, triggers,
              procedures, grants, statistics
~~~

For example, renaming a column may not touch the bytes stored inside rows, yet **application SQL using the old name will break**. Conversely, converting text prices into numbers requires reading, parsing, validating, and writing data. Always separate **schema migration** from **data migration**.

### 1.2. `ALTER TABLE` Is DDL, Not DML

`ALTER TABLE` is **Data Definition Language (DDL)**. In Oracle, DDL typically executes an **implicit COMMIT before running and after completing successfully**. You cannot treat it like a normal `UPDATE` and run `ROLLBACK` to restore the previous structure.

~~~sql
-- Illustrative example; DO NOT run in a session holding uncommitted DML.
UPDATE some_lab_table
SET remark = 'changed'
WHERE id = 1;

ALTER TABLE some_lab_table ADD (new_flag NUMBER);

ROLLBACK;
~~~

Here, `ROLLBACK` after DDL does not undo `ADD COLUMN`. Worse, uncommitted DML **prior to the DDL** was already committed by the implicit commit preceding the DDL statement. Never mix DDL with uncommitted business transactions in the same session.

DDL also acquires metadata locks. If other sessions are using the table or holding long transactions, the DDL may wait, fail due to lock timeout, or impact operations. Lock duration and severity depend on the operation, Oracle version, data volume, and workload.

## 2. Preparing the Lab Table and Inspecting Metadata

### 2.1. Verify the Right Schema/PDB

Before creating or altering tables, run:

~~~sql
SELECT
    SYS_CONTEXT('USERENV', 'SESSION_USER') AS session_user,
    SYS_CONTEXT('USERENV', 'CURRENT_SCHEMA') AS current_schema,
    SYS_CONTEXT('USERENV', 'CON_NAME') AS container_name
FROM dual;
~~~

In a CDB/PDB setup, connect to the **practice PDB**, never `CDB$ROOT` or system schemas, to create business tables. Your lab account needs appropriate privileges like `CREATE TABLE` and tablespace quota. If working in another schema, `ALTER` privileges must be granted; the examples assume you are the **table owner**.

### 2.2. Create Sample Data

The snippet below creates a small table with three orders. Prices are stored as **strings** so we can practice converting them to `NUMBER`; the third row intentionally has an invalid value:

~~~sql
CREATE TABLE alter_table_lab (
    order_id      NUMBER
                  CONSTRAINT pk_alter_table_lab PRIMARY KEY,
    customer_name VARCHAR2(80 CHAR) NOT NULL,
    amount_text   VARCHAR2(30 CHAR),
    legacy_note   VARCHAR2(100 CHAR),
    created_at    TIMESTAMP WITH TIME ZONE
                  DEFAULT SYSTIMESTAMP NOT NULL
);

INSERT INTO alter_table_lab
    (order_id, customer_name, amount_text, legacy_note)
VALUES (1, 'Nguyen An', '1250.50', 'Legacy note A');

INSERT INTO alter_table_lab
    (order_id, customer_name, amount_text, legacy_note)
VALUES (2, 'Tran Binh', '90.00', NULL);

INSERT INTO alter_table_lab
    (order_id, customer_name, amount_text, legacy_note)
VALUES (3, 'Le Chi', 'unknown', 'Needs reconciliation');

COMMIT;

SELECT order_id, customer_name, amount_text, legacy_note
FROM alter_table_lab
ORDER BY order_id;
~~~

The reason for using `VARCHAR2(30 CHAR)` on `AMOUNT_TEXT` is to **illustrate unnormalized legacy data**, not to recommend storing money as text. Monetary data normally belongs in `NUMBER(p,s)` alongside explicit currency units and rounding rules.

If `ALTER_TABLE_LAB` already exists in your current schema, **do not re-run `CREATE TABLE` or wipe an existing table**. Use a fresh lab schema/table and substitute the name consistently.

### 2.3. Inspect Current Columns

~~~sql
SELECT
    column_id,
    column_name,
    data_type,
    data_length,
    char_length,
    char_used,
    nullable,
    data_default
FROM user_tab_columns
WHERE table_name = 'ALTER_TABLE_LAB'
ORDER BY column_id;
~~~

Notable metadata columns:

| Dictionary Column | Meaning |
| --- | --- |
| `COLUMN_NAME` | Column name stored by Oracle (unquoted names are uppercased) |
| `DATA_TYPE` | Oracle data type |
| `DATA_LENGTH` | Maximum length in bytes for certain types, not per-row bytes used |
| `CHAR_LENGTH` | Length in characters for character types |
| `CHAR_USED` | `B` for BYTE semantics, `C` for CHAR semantics |
| `NULLABLE` | Whether the column permits NULL per metadata |
| `DATA_DEFAULT` | Default expression stored in metadata |

`DATA_DEFAULT` uses a special type (`LONG`) in some dictionary views/releases, so avoid assuming string functions, grouping, or filtering on it work like `VARCHAR2`. This query is primarily for **inspecting metadata**.

To view table constraints:

~~~sql
SELECT constraint_name, constraint_type, status, validated
FROM user_constraints
WHERE table_name = 'ALTER_TABLE_LAB'
ORDER BY constraint_name;

SELECT constraint_name, column_name, position
FROM user_cons_columns
WHERE table_name = 'ALTER_TABLE_LAB'
ORDER BY constraint_name, position;
~~~

Constraint `PK_ALTER_TABLE_LAB` binds to `ORDER_ID`. Never drop columns participating in critical keys or constraints without checking them and any foreign keys referencing them from other tables.

## 3. Adding Columns with `ALTER TABLE ... ADD`

### 3.1. Adding a Nullable Column

Add email to the sample table:

~~~sql
ALTER TABLE alter_table_lab
ADD (email VARCHAR2(200 CHAR));
~~~

This is the most common form. Existing rows logically hold **`NULL`** in the new column since they had no email previously. You can update them later:

~~~sql
UPDATE alter_table_lab
SET email = 'an@example.com'
WHERE order_id = 1;

COMMIT;
~~~

Then:

~~~sql
SELECT order_id, customer_name, email
FROM alter_table_lab
ORDER BY order_id;
~~~

Adding multiple columns at once:

~~~sql
ALTER TABLE alter_table_lab
ADD (
    phone_number VARCHAR2(30 CHAR),
    note_text    VARCHAR2(300 CHAR)
);
~~~

Types, lengths, and semantics should match business meaning. Phone numbers belong in `VARCHAR2` rather than `NUMBER` because they may have leading zeros, plus signs, and country codes; reserve numeric types for fields needing arithmetic.

### 3.2. Adding a Column with `DEFAULT`

An order status might need a default value:

~~~sql
ALTER TABLE alter_table_lab
ADD (order_status VARCHAR2(12 CHAR) DEFAULT 'NEW');
~~~

When a new `INSERT` **omits** `ORDER_STATUS`, Oracle applies the default from the column definition. This standard default does not mean an explicit `NULL` insert automatically turns into `'NEW'`. In supporting releases, `DEFAULT ON NULL` is a separate feature with different semantics.

On populated tables, adding a column with a default may leverage metadata optimizations depending on Oracle version and conditions. Never assume every `ADD ... DEFAULT` rewrites the whole table, nor assume every case is "zero cost."

### 3.3. Adding a `DEFAULT ... NOT NULL` Column

If every order must always have a status:

~~~sql
-- Example on a lab table that does not yet have ORDER_STATUS.
ALTER TABLE alter_table_lab
ADD (
    order_status VARCHAR2(12 CHAR)
    DEFAULT 'NEW' NOT NULL
);
~~~

Note: this is an **alternative variant** to adding `ORDER_STATUS` in Section 3.2. If you already ran Section 3.2, do not run `ADD` with the same column name again; instead, backfill NULLs first and then apply `NOT NULL`:

~~~sql
UPDATE alter_table_lab
SET order_status = 'NEW'
WHERE order_status IS NULL;

COMMIT;

ALTER TABLE alter_table_lab
MODIFY (order_status NOT NULL);
~~~

Adding a `NOT NULL` column **without a default** to a non-empty table normally fails because existing rows lack a value for the new column. Oracle raises `ORA-01758` (*table must be empty to add mandatory column*). The safer sequence is:

1. Add the column as **nullable**.
2. Backfill values for existing rows per business rules.
3. Verify no NULLs remain where mandatory.
4. Apply `NOT NULL` and add `DEFAULT` if appropriate.

This sequence is especially useful when backfilling requires calculations or joins from other tables rather than a single constant default for every row.

### 3.4. Adding Constraints Inline with the Column

For instance, a discount percentage field can be bounded:

~~~sql
ALTER TABLE alter_table_lab
ADD (
    discount_pct NUMBER(5,2) DEFAULT 0 NOT NULL
        CONSTRAINT ck_alter_lab_discount
        CHECK (discount_pct BETWEEN 0 AND 100)
);
~~~

`NUMBER(5,2)` allows up to 5 significant digits with 2 decimal places; the constraint bounds valid values between 0 and 100. Do not confuse datatype with constraint: `NUMBER(5,2)` alone does not forbid negative values.

When adding a constraint to a populated table, Oracle checks existing rows. If existing data violates it, the operation fails; never disable checking or set `NOVALIDATE` just to push a migration through without understanding the risk.

## 4. Modifying Column Definitions with `ALTER TABLE ... MODIFY`

### 4.1. Increasing Character Column Length

Initially `CUSTOMER_NAME` is `VARCHAR2(80 CHAR)`. If the business needs up to 160 characters:

~~~sql
ALTER TABLE alter_table_lab
MODIFY (customer_name VARCHAR2(160 CHAR));
~~~

Generally, **widening** a compatible character column succeeds without writing custom row-by-row conversion code. Still, it is DDL—it acquires locks and can affect dependencies. Re-check metadata:

~~~sql
SELECT column_name, data_type, char_length, char_used
FROM user_tab_columns
WHERE table_name = 'ALTER_TABLE_LAB'
  AND column_name = 'CUSTOMER_NAME';
~~~

`VARCHAR2(160 CHAR)` limits by character count, yet remains subject to `VARCHAR2`'s maximum byte ceiling per `MAX_STRING_SIZE` and character set. Switching a column from `BYTE` to `CHAR` does not repair previously corrupted encodings.

### 4.2. Shrinking Length: Inspect Existing Data First

Suppose you want to lower the name limit to 40 characters. First check:

~~~sql
SELECT
    MAX(LENGTH(customer_name)) AS max_chars,
    MAX(LENGTHB(customer_name)) AS max_bytes
FROM alter_table_lab;
~~~

Only if truly safe should you consider:

~~~sql
-- Run only after verifying no data truncation or dependency issues.
ALTER TABLE alter_table_lab
MODIFY (customer_name VARCHAR2(40 CHAR));
~~~

If any stored value exceeds the new size, Oracle raises `ORA-01441` (*cannot decrease column length because some value is too big*). Never blindly truncate customer names if the business forbids losing data. Also review constraint, index, and datatype-change limits.

### 4.3. Changing `DEFAULT`

If `ORDER_STATUS` exists and new orders should start at `PENDING`:

~~~sql
ALTER TABLE alter_table_lab
MODIFY (order_status DEFAULT 'PENDING');
~~~

This changes the **default for future inserts** per column semantics—**never treat it as a backfill for existing rows**. If the business wants existing rows updated, run explicit DML with tight predicates:

~~~sql
UPDATE alter_table_lab
SET order_status = 'PENDING'
WHERE order_status = 'NEW';

COMMIT;
~~~

Before running such an `UPDATE` in a live app, verify whether `NEW` rows have already entered other workflows; never equate changing a default with migrating business state.

### 4.4. Adding or Removing `NOT NULL`

If a column already contains data:

~~~sql
SELECT COUNT(*) AS null_email_count
FROM alter_table_lab
WHERE email IS NULL;
~~~

To make email mandatory, remediate rows lacking an email per data policy before running:

~~~sql
-- Run only after NULL_EMAIL_COUNT = 0 and rules are approved.
ALTER TABLE alter_table_lab
MODIFY (email NOT NULL);
~~~

If any NULLs remain, Oracle cannot validate the constraint and raises `ORA-02296` (*cannot enable ... null values found*).

To allow NULLs again (unless forbidden by another constraint such as primary key):

~~~sql
ALTER TABLE alter_table_lab
MODIFY (email NULL);
~~~

Toggling `NULL`/`NOT NULL` does not populate missing values. `NOT NULL` validates row completeness, whereas `DEFAULT` governs omitted values on insert (or `NULL` on insert if `DEFAULT ON NULL` is declared). The two mechanisms interact, yet are distinct.

### 4.5. Changing Precision/Scale or Datatype: Never Guess

Suppose you have `NUMBER(8,2)` and want `NUMBER(12,2)`, or want to reduce scale. Oracle's rules for `NUMBER` alterations depend on the direction of change and whether rows exist. Narrowing precision/scale on a populated column can trigger errors like `ORA-01440`. Never assume "all current values fit the new bounds, so every NUMBER alteration is allowed."

In particular, changing `VARCHAR2` directly to `NUMBER` or `DATE` on a **populated** column is generally disallowed; Oracle raises `ORA-01439` (*column to be modified must be empty to change datatype*). While certain compatible conversions exist, **do not rely on in-place datatype conversion as a business data-migration strategy**.

Risky example:

~~~sql
-- Do not use on populated AMOUNT_TEXT in the lab:
ALTER TABLE alter_table_lab
MODIFY (amount_text NUMBER(12,2));
~~~

The reliable pattern here is **adding a new numeric column, converting cleaned values via `TO_NUMBER`, reconciling, and then renaming/dropping the old column**. Details follow in Section 7.

## 5. Renaming Columns with `RENAME COLUMN`

Renaming updates the **column identifier**, without altering row contents:

~~~sql
ALTER TABLE alter_table_lab
RENAME COLUMN legacy_note TO legacy_comment;
~~~

Afterward, SQL must reference the new name:

~~~sql
SELECT order_id, legacy_comment
FROM alter_table_lab
ORDER BY order_id;
~~~

Running `SELECT legacy_note FROM alter_table_lab` fails, typically with `ORA-00904`.

### 5.1. Impact on Applications and Dependent Objects

Oracle updates the table's column metadata and maintains supported internal constraints/structures. However, **never assume every view, trigger, package, stored procedure, report, and application query updates automatically**:

- SQL in Java/JDBC or ORMs may still reference `LEGACY_NOTE`.
- Views, PL/SQL units, or dependent objects can become invalid and require recompilation or fixes.
- Column-level grants and logic must be reviewed per object type and Oracle version.
- CSV exporters, JSON mappings, and APIs may still expect the old column name.

Widely referenced names usually need a **backward-compatible transition** plan. Renaming directly while multiple application versions run concurrently will break older app instances immediately after DDL.

### 5.2. Quoted Names and Case Sensitivity

If you run:

~~~sql
-- Syntax example; no need to run in the main lab.
ALTER TABLE alter_table_lab
RENAME COLUMN legacy_comment TO "LegacyComment";
~~~

the new name is literally `LegacyComment`, not `LEGACYCOMMENT`. Every SQL query must then quote `"LegacyComment"` with exact casing. For new schemas, stick consistently to **unquoted uppercase-normalized identifiers** to avoid friction.

### 5.3. Renaming a Column Is Not Renaming a Table

Two distinct commands:

~~~sql
-- Rename one column:
ALTER TABLE alter_table_lab
RENAME COLUMN legacy_note TO legacy_comment;

-- Rename the entire table (not a column operation):
ALTER TABLE alter_table_lab
RENAME TO alter_table_lab_new;
~~~

Run **only the example matching your goal**. If you run the second command renaming the table, subsequent statements referencing `ALTER_TABLE_LAB` will fail unless updated.

## 6. Dropping Columns: `DROP COLUMN` and `SET UNUSED`

### 6.1. Direct Drop with `DROP COLUMN`

If `PHONE_NUMBER` was added in the lab and confirmed unnecessary:

~~~sql
ALTER TABLE alter_table_lab
DROP COLUMN phone_number;
~~~

Dropping a column removes its values from the model and may require Oracle to physically process table blocks. There is **no DDL `ROLLBACK`** to restore the column and its data. Execution time, redo/undo, locking, and online capability depend on table size, features, and configuration.

Key limitations:

- You cannot casually drop columns belonging to primary keys, unique/check/foreign keys, virtual columns, or dependencies Oracle cannot automatically resolve.
- Dependent constraints and objects often must be dropped or adjusted first.
- You cannot drop the **last remaining column** to leave a zero-column table.
- If another table's foreign key references the column, using `CASCADE CONSTRAINTS` drops those foreign key constraints on other tables; never use it lightly.

Syntax example:

~~~sql
-- Inspect dependencies before CASCADE; never run on critical tables.
ALTER TABLE some_lab_table
DROP COLUMN some_column CASCADE CONSTRAINTS;
~~~

`CASCADE CONSTRAINTS` does not safely update application logic. Unchecked use can silently break data integrity across tables.

### 6.2. `SET UNUSED`: Removing the Column Logically First

When dropping a column from a large table, Oracle supports marking it **UNUSED**:

~~~sql
ALTER TABLE alter_table_lab
SET UNUSED (legacy_comment);
~~~

After this operation:

- The column is no longer accessible by its old name in standard SQL.
- It disappears from standard active columns in `USER_TAB_COLUMNS`.
- Physical storage remains until Oracle reclaims it later.
- This schema change is **not directly reversible** to restore the old column/data; do not treat it as a "safe temporary hide you can toggle back on."

`SET UNUSED` is useful to decouple **when the column disappears from the logical interface** from **when physical space is reclaimed**, though physical cleanup still needs scheduling.

### 6.3. Physically Dropping Unused Columns

~~~sql
ALTER TABLE alter_table_lab
DROP UNUSED COLUMNS;
~~~

This can be resource-intensive on very large tables. Schedule and monitor it per your Oracle release documentation; specialized admin options support resuming interrupted drops or checkpointing. **Never assume `SET UNUSED` is a backup or a zero-cost operation.**

Oracle also tracks unused column counts:

~~~sql
SELECT table_name, count
FROM user_unused_col_tabs
WHERE table_name = 'ALTER_TABLE_LAB';
~~~

`COUNT` here is the number of unused columns on the table, **not a row count**. If no columns are `SET UNUSED`, the view returns no row for that table.

### 6.4. Choosing Between `DROP` and `SET UNUSED`

| Criterion | `DROP COLUMN` | `SET UNUSED` then `DROP UNUSED COLUMNS` |
| --- | --- | --- |
| Removes column from SQL/active metadata | Yes | Yes, immediately after `SET UNUSED` |
| Column still usable by old name | No | No |
| Reclaims physical space | During drop | Deferred until `DROP UNUSED` |
| Data-loss risk | Yes | Yes, not reversible |
| Best suited for | Small tables or maintenance windows permitting direct drop | Decoupling logical removal from physical cleanup on large tables |

Before either option, eliminate all code dependencies, take necessary backups, and confirm reports/scripts no longer reference the column.

## 7. Converting Data: From `VARCHAR2` to `NUMBER`

This is the most critical section whenever **"data conversion"** is requested. Suppose `AMOUNT_TEXT` currently holds:

~~~text
ORDER_ID    AMOUNT_TEXT
--------    -----------
1           1250.50
2           90.00
3           unknown
~~~

You cannot safely run `MODIFY (amount_text NUMBER(12,2))` and expect Oracle to guess what `unknown` should become. Even for numeric-looking strings, conversion depends on decimal separators and NLS settings. Design **cleanup rules** first.

### 7.1. Controlled Migration Diagram

~~~text
PHASE 1 - EXPAND
  AMOUNT_TEXT VARCHAR2(30)      +      AMOUNT_NEW NUMBER(12,2)
                 |                             ^
                 |                             |
PHASE 2 - VALIDATE / BACKFILL  -----------------+
  Detect bad values, normalize formatting,
  TO_NUMBER into new column; keep old column for reconciliation.
                 |
PHASE 3 - VERIFY
  Verify row counts, values, nulls, precision,
  business rules, and dependent objects.
                 |
PHASE 4 - CUTOVER
  Stop asynchronous writes; switch SQL/apps to new column.
  Rename old/new columns if needed.
                 |
PHASE 5 - CONTRACT
  After verification period, SET UNUSED/DROP old column,
  archive backups, and update schema docs.
~~~

If the system continues receiving DML during backfill, design **dual-write, controlled sync triggers, batch/CDC, or a write-freeze window**. Running a single `UPDATE` will not stop new rows from being written to the old column afterward.

### 7.2. Step 1 — Add the Target Column

~~~sql
ALTER TABLE alter_table_lab
ADD (amount_new NUMBER(12,2));
~~~

`NUMBER(12,2)` stores up to 12 significant digits with 2 decimal places per the declared scale. For instance, `1250.50` fits cleanly. Oracle's rounding behavior when writing values with more than 2 decimal places must be reviewed against business rules; **never assume silent rounding is acceptable for money**.

Do not apply `NOT NULL` while data still needs cleaning, because the `unknown` row does not yet have a valid number.

### 7.3. Step 2 — Standardize Source Format Rules

In the lab, we choose an explicit source format rule:

- Positive number with **1 to 10 integer digits**.
- Must use a period `.` as the decimal separator.
- Fractional part has **exactly 2 digits**.
- No thousands separators, currency symbols, or extra text.
- `NULL` handled separately per business rules.

This rule is intentionally strict so `1,234` is never silently misread as `1.234` or `1234` depending on locale. On real datasets, rules must reflect source formats, negative signs, currencies, exponents, whitespace, and historical quirks.

Find non-conforming rows:

~~~sql
SELECT order_id, amount_text
FROM alter_table_lab
WHERE amount_text IS NOT NULL
  AND NOT REGEXP_LIKE(
      TRIM(amount_text),
      '^[0-9]{1,10}[.][0-9]{2}$'
  )
ORDER BY order_id;
~~~

In our lab data, `ORDER_ID=3` containing `unknown` appears. **Log the invalid value**, consult the business source, and decide how to fix it. Never blindly replace invalid strings with `0`, because `0` is a real monetary amount with an entirely different meaning from "unknown."

### 7.4. Step 3 — Backfill Valid Rows

After validating formats:

~~~sql
UPDATE alter_table_lab
SET amount_new = TO_NUMBER(
    TRIM(amount_text),
    '9999999999D99',
    'NLS_NUMERIC_CHARACTERS=''.,'''
)
WHERE amount_text IS NOT NULL
  AND REGEXP_LIKE(
      TRIM(amount_text),
      '^[0-9]{1,10}[.][0-9]{2}$'
  );

COMMIT;
~~~

In `TO_NUMBER`:

- Format model `9999999999D99` parses the integer part and two fractional digits.
- `D` uses the decimal separator specified by NLS numeric characters.
- `'NLS_NUMERIC_CHARACTERS=''.,'''` explicitly fixes period as decimal separator and comma as group separator for this conversion instead of relying on session defaults.

Avoid writing bare `TO_NUMBER(amount_text)` when code may run across sessions or clients with differing NLS settings. Even so, the SQL above is an example for a **verified format**, not a universal multi-format parser.

In the lab, the two valid rows receive `1250.50` and `90.00` in `AMOUNT_NEW`. The `unknown` row remains `NULL` in the new column.

### 7.5. Step 4 — Identify Unconverted Rows

~~~sql
SELECT order_id, amount_text, amount_new
FROM alter_table_lab
WHERE amount_text IS NOT NULL
  AND amount_new IS NULL
ORDER BY order_id;
~~~

Do not rush to run `ALTER TABLE ... MODIFY (amount_new NOT NULL)` while unconverted rows remain. To continue the lab, suppose you checked the source record and confirmed the **true value** for order 3 is `35.00`:

~~~sql
-- Example assuming the value was verified against the business source.
UPDATE alter_table_lab
SET amount_text = '35.00'
WHERE order_id = 3;

UPDATE alter_table_lab
SET amount_new = TO_NUMBER(
    TRIM(amount_text),
    '9999999999D99',
    'NLS_NUMERIC_CHARACTERS=''.,'''
)
WHERE amount_text IS NOT NULL
  AND amount_new IS NULL
  AND REGEXP_LIKE(
      TRIM(amount_text),
      '^[0-9]{1,10}[.][0-9]{2}$'
  );

COMMIT;
~~~

In production, changing a monetary amount **must have business justification and an audit trail**; never invent `35.00` without a trusted source.

### 7.6. Step 5 — Reconcile Before Cutover

~~~sql
SELECT
    order_id,
    amount_text,
    amount_new
FROM alter_table_lab
ORDER BY order_id;

SELECT COUNT(*) AS unconverted_rows
FROM alter_table_lab
WHERE amount_text IS NOT NULL
  AND amount_new IS NULL;

SELECT COUNT(*) AS missing_numeric_rows
FROM alter_table_lab
WHERE amount_new IS NULL;
~~~

These two `COUNT` queries measure different things:

- `UNCONVERTED_ROWS`: rows with source text present that still lack a target number.
- `MISSING_NUMERIC_ROWS`: **all rows** lacking a target number, including rows where source was `NULL`.

If the target numeric column must be `NOT NULL`, enforce the constraint only after every `NULL` row is resolved per business rules. On tables with concurrent writes, a single-point check does not prove state remains unchanged by cutover time.

In the lab, a total-amount check might look like:

~~~sql
SELECT COUNT(*) AS row_count,
       SUM(amount_new) AS total_amount
FROM alter_table_lab;
~~~

Never rely on sum totals alone as your only verification, because two opposing errors can cancel out. For critical data, reconcile **by primary key**, format, values, and exception rows.

### 7.7. Step 6 — Column Name Cutover

Once applications are ready to switch from `AMOUNT_TEXT` to `AMOUNT`, on a **write-quiesced lab table**:

~~~sql
ALTER TABLE alter_table_lab
RENAME COLUMN amount_text TO amount_text_legacy;

ALTER TABLE alter_table_lab
RENAME COLUMN amount_new TO amount;

-- Apply only once all rows have valid non-null values:
ALTER TABLE alter_table_lab
MODIFY (amount NOT NULL);
~~~

Renaming does not automatically update Java/SQL code. Immediately after this command, DML referencing `AMOUNT_TEXT` breaks. When multiple application versions run concurrently, use a transitional design supporting both versions, a maintenance window, or an appropriate online redefinition strategy. Also update:

- SQL selects/inserts/updates, stored procedures, views, and triggers.
- ORM/JPA mappings, reports, ETL pipelines, and API contracts.
- Constraints, indexes, column-level grants, and metadata-driven schema discovery code.
- Data-processing jobs, replication/sync, and backup/recovery procedures.

### 7.8. Step 7 — Drop the Old Column Only After Confirmation

After confirming the application operates cleanly on `AMOUNT`, you can retire the old text column:

~~~sql
-- Run only when backups/recovery plans exist and no dependencies remain.
ALTER TABLE alter_table_lab
SET UNUSED (amount_text_legacy);

-- Reclaim physical space during an approved maintenance window.
ALTER TABLE alter_table_lab
DROP UNUSED COLUMNS;
~~~

If `LEGACY_COMMENT` was previously marked `SET UNUSED`, `DROP UNUSED COLUMNS` drops **all unused columns on that table**, not just the most recent one. Inspect table state and required data before running it.

**Rule of thumb:** adding a new column keeps rollback options open. Once you drop the old column or source data, reverting may require restoring from backup. Never equate "DDL succeeded" with "migration completed safely."

## 8. Converting Strings to Dates and Timestamps

Converting `VARCHAR2` to `DATE` should likewise never rely on implicit conversion, which depends on `NLS_DATE_FORMAT` and fails on invalid calendar dates.

Suppose another table has `ORDER_DATE_TEXT` storing canonical `YYYY-MM-DD` strings like `2026-11-14`. Conceptual workflow:

~~~sql
-- Example on a separate lab table containing ORDER_DATE_TEXT.
ALTER TABLE order_date_lab
ADD (order_date DATE);

-- Oracle 12.2+ supports VALIDATE_CONVERSION.
SELECT order_id, order_date_text
FROM order_date_lab
WHERE order_date_text IS NOT NULL
  AND VALIDATE_CONVERSION(
      order_date_text AS DATE, 'FXYYYY-MM-DD'
  ) = 0;

UPDATE order_date_lab
SET order_date = TO_DATE(order_date_text, 'FXYYYY-MM-DD')
WHERE order_date_text IS NOT NULL
  AND VALIDATE_CONVERSION(
      order_date_text AS DATE, 'FXYYYY-MM-DD'
  ) = 1;

COMMIT;
~~~

This is an **illustrative example** and will not run in the main lab unless you create `ORDER_DATE_LAB`. `FX` enforces stricter format matching (preventing the parser from accepting unintended variants), while `VALIDATE_CONVERSION` flags invalid dates before `TO_DATE` fails inside an `UPDATE`.

For instance, `2026-02-30` matches a digit-and-hyphen regex yet **is not a real calendar date**, so regex alone cannot replace date conversion validation.

For datetimes with timezones, consider `TIMESTAMP`/`TIMESTAMP WITH TIME ZONE` and `TO_TIMESTAMP`/`TO_TIMESTAMP_TZ` instead of `DATE` if fractional seconds or offsets matter. Never convert local time strings to UTC without knowing the **source timezone**; `2026-11-14 09:00:00` by itself does not identify a single unambiguous instant.

### 8.1. Converting Character Semantics BYTE/CHAR

Beyond converting text to numbers/dates, you may need to change length semantics:

~~~sql
-- Example changing length semantics of a lab column:
ALTER TABLE alter_table_lab
MODIFY (customer_name VARCHAR2(160 CHAR));
~~~

In an `AL32UTF8` database, accented Vietnamese characters take multiple bytes each. `VARCHAR2(100 BYTE)` is not equivalent to `VARCHAR2(100 CHAR)`; meanwhile, `CHAR` semantics remain bounded by `VARCHAR2`'s maximum byte ceiling. Before shrinking sizes or changing semantics, measure `LENGTH`, `LENGTHB`, and check `CHAR_USED` in the data dictionary.

### 8.2. Fields That Should Not Be Converted to Numbers

Never convert **phone numbers, postal codes, customer codes, or document numbers** to `NUMBER` merely because current values look all-numeric. Those are **identifiers**: they may have leading zeros, `+` signs, or delimiters, and do not undergo arithmetic.

Datatype selection follows **business semantics and operations**, not merely what current sample values look like.

## 9. Schema Dependencies: Constraints, Indexes, Views, and PL/SQL

### 9.1. Inspect Constraints Before Modifying or Dropping Columns

~~~sql
SELECT
    c.constraint_name,
    c.constraint_type,
    c.status,
    cc.column_name,
    cc.position
FROM user_constraints c
JOIN user_cons_columns cc
    ON cc.constraint_name = c.constraint_name
   AND cc.table_name = c.table_name
WHERE c.table_name = 'ALTER_TABLE_LAB'
ORDER BY c.constraint_name, cc.position;
~~~

Common constraint types:

| `CONSTRAINT_TYPE` | Constraint Group | Impact When Modifying/Dropping Columns |
| --- | --- | --- |
| `P` | Primary key | Do not drop key columns without redesigning identity/references |
| `U` | Unique | Uniqueness index/constraint may be affected |
| `R` | Foreign key | Check both child tables and referenced parent tables |
| `C` | Check, often including NOT NULL in the dictionary | Existing data must satisfy conditions before enabling/changing |

Oracle has additional constraint types depending on features. Always check **constraints on the current table and foreign keys from other tables** before dropping any column.

### 9.2. Do Indexes Use the Column Being Modified?

~~~sql
SELECT index_name, column_name, column_position
FROM user_ind_columns
WHERE table_name = 'ALTER_TABLE_LAB'
ORDER BY index_name, column_position;
~~~

For function-based indexes, also check index expressions and how renaming or datatype changes affect them. When a column participates in an index key, changing length or type can hit index key size limits, trigger rebuild costs, or encounter DDL restrictions. Never assume indexes "automatically adapt unconditionally."

### 9.3. Views, Triggers, and PL/SQL May Reference Old Names

~~~sql
SELECT name, type, referenced_name, referenced_type
FROM user_dependencies
WHERE referenced_name = 'ALTER_TABLE_LAB'
ORDER BY type, name;
~~~

This detects **database dependencies tracked by Oracle**; it cannot find SQL inside Java code, batch jobs, external reports, dynamic SQL, or external ETL tools. Some references also depend on current schema and privileges. Search application code and external repositories per deployment procedure.

After structural changes, check for invalid objects:

~~~sql
SELECT object_name, object_type, status
FROM user_objects
WHERE status <> 'VALID'
ORDER BY object_type, object_name;
~~~

Investigate any `INVALID` objects; do not assume every invalid object was caused solely by your table change. Real rollouts may require recompiling affected units and running application tests.

### 9.4. Column Defaults and CHECK Do Not Repair Existing Bad Data

Suppose you want amounts to always be non-negative:

~~~sql
ALTER TABLE alter_table_lab
ADD CONSTRAINT ck_alter_lab_amount
CHECK (amount >= 0);
~~~

This makes sense **only after `AMOUNT` exists** at cutover. `CHECK` ensures future writes and existing rows comply when validated; it **does not fix negative numbers**. Likewise, `DEFAULT 0` is not a cleanup tool for old `unknown` strings.

For critical data, define every edge case clearly: is NULL allowed? Do negatives represent refunds? Are currency and scale consistent? Constraints must model the true business rules.

## 10. Running DDL When Tables Are Large or Under Active Traffic

A script that finishes instantly on a handful of rows tells you nothing about running on millions of rows. Distinguish the operation classes:

| Task | Typical Impact | Deployment Notes |
| --- | --- | --- |
| Add nullable column | Primarily metadata in many cases | Still needs DDL lock and code review |
| Add column with default | May use metadata optimization depending on version/conditions | Never assume every variant has zero I/O |
| Increase `VARCHAR2` length | Usually simpler than changing datatype | Check indexes, dependencies, locks, and version |
| Rename column | Metadata change, yet breaks old name references | Ensure compatible application releases |
| Backfill millions of rows | Heavy DML, redo/undo, locks, archive logs, I/O | Chunk into controlled batches, track progress, reconcile |
| `DROP COLUMN` | Can consume heavy resources processing physical data | Schedule window, verify backups and recovery |
| `SET UNUSED` | Separates logical removal from physical cleanup | Old name stops working immediately; `DROP UNUSED` later still takes work |

### 10.1. The Expand/Contract Deployment Pattern

For applications that cannot tolerate long downtime, the standard pattern is:

1. **Expand:** add the target column while keeping the source column active.
2. **Sync:** deploy controlled dual-write or sync triggers so old and new columns do not drift during transition.
3. **Backfill:** migrate historical rows in batches, handling errors and watching resource usage.
4. **Verify:** reconcile by primary key, row counts, NULLs, and business invariants.
5. **Cutover:** switch reads/writes to the new column at a safe point and test all application paths.
6. **Contract:** remove old data/columns only after recovery plans are verified and compatibility needs end.

There is no single online recipe for every database. Oracle provides tools like **online table redefinition (`DBMS_REDEFINITION`)** for suitable scenarios, requiring careful assessment of prerequisites, locks, dependent objects, privileges, duration, and Oracle version. That is a dedicated administrative workflow, not a one-line `MODIFY`.

### 10.2. Batch Backfilling and Avoiding Concurrent Data Loss

On a large table, a single statement:

~~~sql
UPDATE huge_table
SET new_col = expensive_conversion(old_col);
~~~

can generate massive undo/redo, hold row locks for a long time, and stall the system. DBAs and developers typically chunk by primary key, cap batch size, commit per batch, and checkpoint progress. Even so, **batch commits do not eliminate race conditions** if the application keeps updating the source column concurrently. Design synchronization and idempotent retries explicitly.

In a small lab, a conditional `UPDATE` followed by `COMMIT` suffices to learn the concept. In production, batch execution must align with schedules, load thresholds, and testing.

### 10.3. DDL Locks and Wait Timeouts

If `ALTER TABLE` blocks behind a long transaction or fails with `ORA-00054: resource busy and acquire with NOWAIT specified or timeout expired`, never blindly kill user sessions. DBAs inspect blockers, active transactions, maintenance windows, and whether `DDL_LOCK_TIMEOUT` is appropriate within policy.

In the lab, you can view the parameter:

~~~sql
SHOW PARAMETER ddl_lock_timeout;
~~~

This parameter governs how long DDL waits for locks in applicable cases; raising the timeout does not eliminate locking impact or make an operation online. Production changes still need proper downtime or compatibility planning.

### 10.4. Backups, Strategic Rollback, and Recoverability

Because Oracle DDL performs implicit commits, a plan saying "if anything fails, `ROLLBACK` everything" **is wrong**. Instead:

- Prepare forward scripts and safe **compensating migrations** where possible.
- Back up relevant data/metadata and verify restore/recover procedures matching RPO/RTO.
- Retain the source column long enough during transition to reconcile and recover data if needed.
- Never drop the old column until confirming applications and downstream consumers have moved off it.
- Rehearse changes in staging with representative schema, data, constraints, indexes, triggers, and load.

Once a column is dropped with `DROP` or `SET UNUSED`, do not assume instant rollback preserves old values. Recovery may require backups, flashback, or DBA-managed restoration depending on active features and state.

## 11. Common Oracle Error Codes

| Error | Typical Scenario | Diagnostic Steps |
| --- | --- | --- |
| `ORA-01430` | Attempt to `ADD` a column that already exists | Inspect `USER_TAB_COLUMNS`, column name/casing, and prior migrations |
| `ORA-00904` | SQL references a renamed, dropped, or misspelled column | Check metadata names, quoted identifiers, and stale app SQL |
| `ORA-01758` | Adding a mandatory column without default to a non-empty table | Add nullable → backfill → `NOT NULL`, or supply an appropriate default |
| `ORA-02296` | Enabling `NOT NULL` while NULL values exist | Query NULL rows and remediate per business rules |
| `ORA-01441` | Decreasing column length below existing value size | Measure actual lengths first; never truncate arbitrarily |
| `ORA-01440` | Narrowing numeric precision/scale when data/column state disallows it | Review numeric types, data, and constraints; use a new column if needed |
| `ORA-01439` | Changing datatype when column preconditions fail (usually non-empty) | Use the new-column + conversion + cutover strategy |
| `ORA-01722` | Converting a string that is not a valid number | Inspect format, NLS settings, and bad rows; use explicit `TO_NUMBER` and validation |
| `ORA-01861` | Date literal does not match format string | Use `TO_DATE`/`TO_TIMESTAMP` with explicit format masks |
| `ORA-01843` | Invalid month or date format | Inspect actual data and NLS date language |
| `ORA-12899` | Value exceeds target column byte/character length | Measure `LENGTH`/`LENGTHB`, check `CHAR_USED` and column definition |
| `ORA-02449` | Dropping a referenced key object without handling foreign keys | Inspect PK/UK/FK relationships before DDL; never cascade blindly |
| `ORA-00054` | Failed to acquire DDL lock within timeout | Inspect blocking sessions, execution plan, and maintenance window |

Exact error wording can vary by release and statement. **An error code never replaces data analysis**, especially during complex migrations.

### 11.1. Quick Diagnostic Queries When an Alteration Fails

~~~sql
-- Column structure:
SELECT column_name, data_type, data_length,
       char_length, char_used, nullable
FROM user_tab_columns
WHERE table_name = 'ALTER_TABLE_LAB'
ORDER BY column_id;

-- Constraints:
SELECT constraint_name, constraint_type, status, validated
FROM user_constraints
WHERE table_name = 'ALTER_TABLE_LAB';

-- Indexes:
SELECT index_name, column_name, column_position
FROM user_ind_columns
WHERE table_name = 'ALTER_TABLE_LAB'
ORDER BY index_name, column_position;

-- UNUSED columns:
SELECT table_name, count
FROM user_unused_col_tabs
WHERE table_name = 'ALTER_TABLE_LAB';
~~~

If the table belongs to another schema, query the appropriate `ALL_*` or `DBA_*` views with owner filters; `USER_*` reflects only the current owner's objects.

## 12. Continuous End-to-End Practice Sequence

To avoid accidentally running mutually exclusive **alternative variants** from earlier examples, follow this clean sequence on the `ALTER_TABLE_LAB` table created in Section 2:

### Phase A — Adding Attributes

~~~sql
ALTER TABLE alter_table_lab
ADD (email VARCHAR2(200 CHAR));

ALTER TABLE alter_table_lab
ADD (order_status VARCHAR2(12 CHAR) DEFAULT 'NEW' NOT NULL);

ALTER TABLE alter_table_lab
MODIFY (customer_name VARCHAR2(160 CHAR));
~~~

Afterward, inspect `USER_TAB_COLUMNS` and `SELECT` rows. Existing rows logically exhibit `NEW` per the default declared when adding the column.

### Phase B — Renaming Legacy Column

~~~sql
ALTER TABLE alter_table_lab
RENAME COLUMN legacy_note TO legacy_comment;

SELECT order_id, legacy_comment
FROM alter_table_lab
ORDER BY order_id;
~~~

In this step, do not run `ALTER TABLE ... RENAME TO`, as renaming the whole table breaks subsequent references to `ALTER_TABLE_LAB`.

### Phase C — Converting Prices Containing Invalid Data

~~~sql
ALTER TABLE alter_table_lab
ADD (amount_new NUMBER(12,2));

SELECT order_id, amount_text
FROM alter_table_lab
WHERE amount_text IS NOT NULL
  AND NOT REGEXP_LIKE(
      TRIM(amount_text),
      '^[0-9]{1,10}[.][0-9]{2}$'
  );

UPDATE alter_table_lab
SET amount_new = TO_NUMBER(
    TRIM(amount_text),
    '9999999999D99',
    'NLS_NUMERIC_CHARACTERS=''.,'''
)
WHERE amount_text IS NOT NULL
  AND REGEXP_LIKE(
      TRIM(amount_text),
      '^[0-9]{1,10}[.][0-9]{2}$'
  );

COMMIT;
~~~

Result: row 3 remains unconverted because of `unknown`. Once verified in the lab, follow Section 7.5 to fix it, backfill, and reconcile.

### Phase D — Cutover

After all values are verified:

~~~sql
ALTER TABLE alter_table_lab
RENAME COLUMN amount_text TO amount_text_legacy;

ALTER TABLE alter_table_lab
RENAME COLUMN amount_new TO amount;

ALTER TABLE alter_table_lab
MODIFY (amount NOT NULL);

SELECT order_id, customer_name, amount, order_status
FROM alter_table_lab
ORDER BY order_id;
~~~

Do not run Phase D if `AMOUNT_NEW` still contains NULLs on a column that must become mandatory. That is a business precondition, not an error to bypass.

### Phase E — Cleaning Up Unused Columns

Only once you confirm the lab is complete and legacy values are no longer needed:

~~~sql
ALTER TABLE alter_table_lab
SET UNUSED (legacy_comment, amount_text_legacy);

SELECT table_name, count
FROM user_unused_col_tabs
WHERE table_name = 'ALTER_TABLE_LAB';

ALTER TABLE alter_table_lab
DROP UNUSED COLUMNS;
~~~

If you want to practice `DROP COLUMN` instead of `SET UNUSED`, drop a non-critical column such as `EMAIL` on your **lab table** after confirming its data is expendable:

~~~sql
ALTER TABLE alter_table_lab
DROP COLUMN email;
~~~

### Phase F — Cleaning Up the Lab Table (Optional)

~~~sql
-- Run only if this is your own lab table and the data is no longer needed.
DROP TABLE alter_table_lab PURGE;
~~~

`PURGE` bypasses the recycle bin when dropping the table, so Flashback Drop cannot recover a purged table. Skip this step if you want to keep your practice results or if any non-lab data exists.

## 13. Self-Check Questions

1. On a table with 100,000 existing rows, what logical value do old rows hold in a new nullable column added via `ALTER TABLE ... ADD (new_col VARCHAR2(100))` without a default?
2. Why does adding a `NOT NULL` column without a default to a populated table fail?
3. Do `DEFAULT 'NEW'` and `NOT NULL` play the same role?
4. Does running `MODIFY (order_status DEFAULT 'PENDING')` automatically change existing `'NEW'` rows to `'PENDING'`?
5. Does renaming `LEGACY_NOTE` to `LEGACY_COMMENT` automatically fix application SQL?
6. Why cannot you rely on `ROLLBACK` after `ALTER TABLE ... DROP COLUMN` to recover the dropped data?
7. Contrast `DROP COLUMN` and `SET UNUSED` regarding when the column disappears from SQL and when physical storage is reclaimed.
8. Why is `ALTER TABLE t MODIFY (amount_text NUMBER(12,2))` unsafe when `AMOUNT_TEXT` already holds `unknown`?
9. During a migration from `VARCHAR2` to `NUMBER`, why must decimal separators and NLS settings be standardized before calling `TO_NUMBER`?
10. When the source column has `NULL` rows, why is checking `amount_text IS NOT NULL AND amount_new IS NULL` alone insufficient before applying `NOT NULL` to the target column?
11. Why can converting a phone number from `VARCHAR2` to `NUMBER` destroy data meaning?
12. When an `ALTER TABLE` script runs slowly on a large table, what two categories of impact (locking vs. I/O) should be investigated?
13. Why can an application continuing to insert into the source column during backfill leave the new column incomplete?
14. Besides `USER_TAB_COLUMNS`, which data dictionary views help uncover constraints, indexes, and database dependencies?
15. Before running `DROP UNUSED COLUMNS` in production, why are backups and recovery plans required even though the column is already invisible to SQL?

**Suggested Answers:**

1. `NULL`.
2. Existing rows lack values to satisfy `NOT NULL`; a default or backfill is needed first.
3. No. A default supplies values on insert per column semantics; `NOT NULL` forbids NULL.
4. No; modifying existing rows requires explicit DML.
5. No; old names may persist in Java code, views, PL/SQL, batch jobs, and reports.
6. DDL performs an implicit commit; dropping is a structural change that can permanently remove data.
7. Both remove SQL access to the column, but `SET UNUSED` defers physical reclamation until `DROP UNUSED COLUMNS`.
8. Oracle restricts in-place datatype changes on populated columns, and invalid strings cannot convert cleanly to numbers.
9. The same text like `1,234` means different values across locales; the source format must be explicitly defined.
10. It ignores rows where the source was NULL; if the target is mandatory, check **all** NULLs in the target.
11. Leading zeros and identifier characters like `+` are stripped or invalid in numeric arithmetic types.
12. DDL locks/blocking and physical I/O across redo, undo, and datafiles.
13. Race conditions between backfill and live DML; synchronization or a controlled cutover window is required.
14. `USER_CONSTRAINTS`, `USER_CONS_COLUMNS`, `USER_IND_COLUMNS`, `USER_DEPENDENCIES`, `USER_OBJECTS`.
15. Marking a column unused is not a backup; physical cleanup cannot be rolled back and can consume substantial resources.

## Oracle Reference Documentation

- [Oracle Database SQL Language Reference — ALTER TABLE](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/ALTER-TABLE.html): syntax for adding, modifying, renaming, and dropping columns, unused columns, and constraints.
- [Oracle Database SQL Language Reference — Data Types](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/Data-Types.html): `VARCHAR2`, `NUMBER`, `DATE`, BYTE/CHAR lengths, and datatype limits.
- [Oracle Database SQL Language Reference — TO_NUMBER](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/TO_NUMBER.html): converting strings to numbers using format models and NLS numeric settings.
- [Oracle Database SQL Language Reference — VALIDATE_CONVERSION](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/VALIDATE_CONVERSION.html): evaluating data convertibility before migration.
- [Oracle Database Administrator's Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/admin/): table administration, storage, schema changes, and operational considerations.
- [Oracle Database Reference](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/): `USER_TAB_COLUMNS`, `USER_CONSTRAINTS`, `USER_IND_COLUMNS`, `USER_UNUSED_COL_TABS`, and dependency views.
