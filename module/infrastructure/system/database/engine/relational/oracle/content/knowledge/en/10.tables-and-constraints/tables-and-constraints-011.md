# CREATE TABLE AS SELECT and Attributes to Verify After Copying in Oracle

When you need to create a table for testing, capture a data snapshot prior to migration, or build an aggregate table from a query result, Oracle Database provides **`CREATE TABLE AS SELECT` (CTAS)**. Example:

```sql
CREATE TABLE orders_snapshot AS
SELECT order_id, customer_id, total_amount
FROM orders
WHERE order_status = 'PAID';
```

One statement both **creates a new table** and **populates it with the rows returned by SELECT**. This is extremely convenient, yet it comes with a dangerous misconception: *"The new table is surely identical to the original table, just with a different name."* In reality, CTAS primarily copies **the column list/data types of the query output and the selected rows**; many schema attributes and operational behaviors of the source table **are not copied automatically**.

A CTAS table may look identical to the source table when running `SELECT *`, while missing **PRIMARY KEY**, **UNIQUE**, **FOREIGN KEY**, **CHECK**, **DEFAULT**, **IDENTITY**, **indexes**, **triggers**, **comments**, **grants**, or critical storage and security settings. Some **NOT NULL** constraints may be inherited by Oracle under certain conditions, yet you must never assume all constraints match.

This lesson explains CTAS within the context of **tables and constraints** in Oracle Database: syntax, runnable examples, what is preserved vs. omitted, how to inspect the data dictionary to verify, steps to restore missing attributes, and risks when using CTAS on critical data.

After this lesson, you will be able to:

- Use CTAS to create tables from all rows, a filtered subset, or **zero rows** of a SELECT query.
- Distinguish **copying data**, **copying column definitions**, and **cloning an entire table's structure and behavior**.
- Check constraints, indexes, defaults, identity columns, triggers, comments, privileges, LOB/partitioning, and storage.
- Use `USER_TABLES`, `USER_TAB_COLUMNS`, `USER_CONSTRAINTS`, `USER_INDEXES`, and other dictionary views to verify actual results.
- Avoid pitfalls involving implicit commits, snapshot consistency, permissions, and performance.
- Build a **technical checklist** before using a CTAS table in pipelines or real applications.

> Examples prefix table names with `LAB_CTAS_` for clarity. Run them only in a practice schema or authorized environment; `CREATE TABLE` is DDL and must not run inside a business transaction with uncommitted changes you want to roll back. Exact CTAS behavior can vary by Oracle version, enabled features, and source query shape. Always **re-read metadata on the new table**.

## 1. CTAS Does Two Things in One Statement

CTAS takes the form `CREATE TABLE ... AS SELECT ...`:

```text
        SOURCE TABLE / VIEW / JOINED TABLES
                        │
                        ▼
                  SELECT query
         • Select columns, expressions, aliases
         • WHERE / JOIN / GROUP BY
         • Evaluates results at runtime
                        │
                        ▼
                CREATE TABLE AS
                        │
         ┌──────────────┴──────────────┐
         ▼                             ▼
   Column definitions            Result rows
   inferred from SELECT          loaded into new table
         │                             │
         └──────────────┬──────────────┘
                        ▼
                 NEW TARGET TABLE

  NEVER ASSUME FULL CLONING OF:
  PK / FK / UNIQUE / CHECK / INDEX / TRIGGER /
  DEFAULT / IDENTITY / GRANTS / COMMENTS / ...
```

Key distinctions:

| Technique | Purpose | Must Target Table Already Exist? |
| --- | --- | --- |
| `CREATE TABLE ... AS SELECT ...` | Create a **new table** from SELECT results | **No**; CTAS creates the table |
| `INSERT INTO target SELECT ...` | Insert data into an **existing table** | **Yes** |
| `CREATE TABLE ...` with explicit columns & constraints | Create a schema with explicit design | No |
| `CREATE VIEW ... AS SELECT ...` | Save a logical query definition, not a materialized copy like CTAS | No; creates a view |
| Export/import, Data Pump, metadata DDL | Migrate/restore objects and data with full options | Depends on tool and goal |

CTAS excels when you **need a new data table derived from a query**. If your goal is an exact clone of a schema and all supporting objects to replace a production table, CTAS alone **is not** a complete one-command solution.

### 1.1. Required Privileges

For CTAS to succeed, the user needs:

- **`CREATE TABLE`** privilege in the target schema (or corresponding admin privileges if creating in another schema).
- Read access on source tables/views effective for the SELECT query.
- Adequate tablespace quota and storage capacity to load the rows.

Having `SELECT` privilege on a source table does not automatically grant permission to create tables in that schema. Conversely, a newly created table does not automatically inherit grants for users who had access to the source table.

## 2. Basic CTAS Syntax and Three Common Copy Patterns

### 2.1. Copying All Selected Columns and All Rows

```sql
CREATE TABLE lab_ctas_orders_all AS
SELECT *
FROM lab_ctas_orders;
```

Oracle creates `LAB_CTAS_ORDERS_ALL` and loads all queried rows. `SELECT *` is handy in a lab, yet carries risks:

- Column lists shift if the source table adds or drops columns.
- **Invisible/hidden columns** do not appear in normal `SELECT *`.
- CTAS captures **columns returned by SELECT**; it does not clone storage attributes, defaults, virtual expressions, or identity behavior.

In deployment scripts, **list columns explicitly** so the target schema is predictable:

```sql
CREATE TABLE lab_ctas_orders_all AS
SELECT order_id, customer_id, amount, status, created_at, note
FROM lab_ctas_orders;
```

Do **not run both statements above sequentially using the same table name**, because the second will fail with "name is already used by an existing object." Pick one approach and target name.

### 2.2. Copying Only Rows Matching WHERE

```sql
CREATE TABLE lab_ctas_orders_paid AS
SELECT order_id, customer_id, amount, status, created_at
FROM lab_ctas_orders
WHERE status = 'PAID';
```

The row count in the new table equals the number of rows returned by the query at the SELECT's read-consistent snapshot. The target table need not include every source column or every row.

### 2.3. Copying Only Column Structure, No Data

```sql
CREATE TABLE lab_ctas_orders_empty AS
SELECT order_id, customer_id, amount, status, created_at, note
FROM lab_ctas_orders
WHERE 1 = 0;
```

Since `1 = 0` is always false, the new table has **zero rows**, while keeping columns inferred from SELECT. This is a common shortcut for scaffolding column shapes quickly.

**Never call this "cloning the entire schema empty":** primary keys, foreign keys, defaults, indexes, triggers, and many attributes are not copied automatically just because the table is empty. Even `NOT NULL` constraints inherited under specific rules must be verified.

### 2.4. Copying from JOINs or Calculations, Not Just One Table

CTAS accepts any valid Oracle SELECT, including joins, expressions, and aggregations:

```sql
CREATE TABLE lab_ctas_customer_revenue AS
SELECT
    c.customer_id,
    c.customer_name,
    COUNT(o.order_id) AS order_count,
    SUM(o.amount) AS revenue
FROM lab_ctas_customers c
JOIN lab_ctas_orders o
  ON o.customer_id = c.customer_id
WHERE o.status = 'PAID'
GROUP BY c.customer_id, c.customer_name;
```

The resulting `LAB_CTAS_CUSTOMER_REVENUE` is **a new reporting table**, not a copy of `LAB_CTAS_CUSTOMERS` or `LAB_CTAS_ORDERS`. `REVENUE` derives from `SUM`, and `ORDER_COUNT` derives from `COUNT`. If UIs or APIs require fixed precision/scale, apply explicit `CAST`.

## 3. Preparing a Sample Dataset to Observe Differences

Run the steps in this section only inside a **practice schema**. If any object already exists, rename it rather than overwriting active tables.

Create the parent table:

```sql
CREATE TABLE lab_ctas_customers (
    customer_id   NUMBER(10)
        CONSTRAINT pk_lab_ctas_customers PRIMARY KEY,
    customer_name VARCHAR2(80) NOT NULL
);

INSERT INTO lab_ctas_customers (customer_id, customer_name)
VALUES (101, 'An');

INSERT INTO lab_ctas_customers (customer_id, customer_name)
VALUES (102, 'Binh');
```

Create the orders table with rich attributes to compare:

```sql
CREATE TABLE lab_ctas_orders (
    order_id    NUMBER(10),
    customer_id NUMBER(10) NOT NULL,
    amount      NUMBER(12, 2) DEFAULT 0 NOT NULL,
    status      VARCHAR2(20) DEFAULT 'NEW' NOT NULL,
    created_at  DATE DEFAULT SYSDATE NOT NULL,
    note        VARCHAR2(100),
    CONSTRAINT pk_lab_ctas_orders
        PRIMARY KEY (order_id),
    CONSTRAINT fk_lab_ctas_orders_customer
        FOREIGN KEY (customer_id)
        REFERENCES lab_ctas_customers (customer_id),
    CONSTRAINT ck_lab_ctas_orders_amount
        CHECK (amount >= 0),
    CONSTRAINT ck_lab_ctas_orders_status
        CHECK (status IN ('NEW', 'PAID', 'CANCELLED'))
);

CREATE INDEX idx_lab_ctas_orders_customer
    ON lab_ctas_orders (customer_id);
```

Insert sample rows to observe:

```sql
INSERT INTO lab_ctas_orders
    (order_id, customer_id, amount, status, note)
VALUES
    (1, 101, 120.50, 'PAID', 'Delivered successfully');

INSERT INTO lab_ctas_orders
    (order_id, customer_id, amount, status, note)
VALUES
    (2, 101, 85.00, 'NEW', NULL);

INSERT INTO lab_ctas_orders
    (order_id, customer_id, amount, status, note)
VALUES
    (3, 102, 30.00, 'CANCELLED', 'Cancelled');

COMMIT;
```

Notice: `CREATED_AT` receives default `SYSDATE` because the INSERT omits it. The primary key constraint creates a backing index for uniqueness; `IDX_LAB_CTAS_ORDERS_CUSTOMER` is an additional index supporting customer lookups.

Now run CTAS:

```sql
CREATE TABLE lab_ctas_orders_copy AS
SELECT order_id, customer_id, amount, status, created_at, note
FROM lab_ctas_orders;
```

The rows are copied, and now we must **actively compare the behavior** of the new table against the source.

## 4. Which Attributes Are Copied and Which Are Not?

The overview below summarizes typical Oracle CTAS behavior. Edge cases exist for `NOT NULL`, data types, and DDL options; reading metadata afterward is always mandatory.

| Component | Standard CTAS Behavior | What to Verify |
| --- | --- | --- |
| **Row count and column values** | Loads rows produced by SELECT | `WHERE`/`JOIN` filters, row counts, NULLs, totals, snapshot point-in-time |
| **Column names** | Uses SELECT column names/aliases or explicit target column list | Duplicate names, aliases, quoted identifiers, name lengths |
| **Data types** | Inferred from SELECT expression types | `NUMBER` precision/scale, `CHAR`/`VARCHAR2` length semantics, `DATE`/`TIMESTAMP`, LOBs |
| **`NULLABLE`/`NOT NULL`** | Some `NOT NULL`s may be inherited under Oracle conditions | `USER_TAB_COLUMNS.NULLABLE` and `USER_CONSTRAINTS`; never assume uniform inheritance |
| **`PRIMARY KEY`** | **Not copied automatically** | Add an appropriate PK after verifying data |
| **`UNIQUE`** | **Not copied automatically** | Does target data still guarantee uniqueness? |
| **`FOREIGN KEY`** | **Not copied automatically** | Parent tables, orphan rows, and `REFERENCES` privileges |
| **`CHECK`** | **Not copied automatically** | Must business validation still apply on target? |
| **`DEFAULT` / `DEFAULT ON NULL`** | **Source default definitions are not kept** | Check `DATA_DEFAULT` and re-add defaults as needed |
| **`IDENTITY` / sequence behavior** | Key generation mechanisms are not cloned | `USER_TAB_IDENTITY_COLS`, sequences/triggers |
| **Source table indexes** | **Not copied automatically** | `USER_INDEXES`, `USER_IND_COLUMNS`; create indexes for target workload |
| **Triggers** | **Not copied automatically** | `USER_TRIGGERS` and required side effects |
| **Comments** | Comment metadata is not kept | `USER_TAB_COMMENTS`, `USER_COL_COMMENTS` |
| **`GRANT` / privileges** | Source grants are not inherited | `USER_TAB_PRIVS_MADE` or relevant privilege views |
| **Virtual / hidden / invisible columns** | Depends on SELECT output; original properties are not preserved | `USER_TAB_COLS`, expressions/visibility |
| **Partitioning, compression, LOB storage, tablespace, logging** | Follows target DDL and defaults, not source settings | `USER_TABLES`, `USER_TAB_PARTITIONS`, `USER_LOBS`, live DDL |
| **Row-level security, audit, masking, encryption policies** | Never assume transfer to the new table | Inspect active security policies/controls |
| **Optimizer statistics** | Cannot be assumed identical to source stats | Inspect stats separately; CTAS may gather stats under certain conditions |

Conclusion: CTAS **copies SELECT results into a new table**, rather than "cloning every object and all supporting metadata."

## 5. Constraints: The Easiest Thing to Miss

### 5.1. PRIMARY KEY Does Not Appear Automatically

`LAB_CTAS_ORDERS` has:

```sql
CONSTRAINT pk_lab_ctas_orders PRIMARY KEY (order_id)
```

Yet `LAB_CTAS_ORDERS_COPY` created via CTAS does not receive that primary key. Current `ORDER_ID` values may happen to be distinct, **but currently distinct data does not mean a constraint protects future writes**.

To add a PK on the target table:

```sql
ALTER TABLE lab_ctas_orders_copy
    ADD CONSTRAINT pk_lab_ctas_orders_copy
    PRIMARY KEY (order_id);
```

Before adding it, verify:

```sql
SELECT order_id, COUNT(*) AS duplicate_count
FROM lab_ctas_orders_copy
GROUP BY order_id
HAVING COUNT(*) > 1;

SELECT COUNT(*) AS null_key_count
FROM lab_ctas_orders_copy
WHERE order_id IS NULL;
```

Because PK requires non-NULL and unique keys, if CTAS used a JOIN that multiplied an order row, `ALTER TABLE ... PRIMARY KEY` fails. Never assume PK validity merely because the source table had one.

### 5.2. UNIQUE, FOREIGN KEY, and CHECK Are Not Preserved Either

**UNIQUE:** if the target must guarantee a tuple never repeats, add the appropriate constraint:

```sql
ALTER TABLE lab_ctas_orders_copy
    ADD CONSTRAINT uq_lab_ctas_order_customer
    UNIQUE (order_id, customer_id);
```

This example makes sense only if the business requires uniqueness on the **pair** (`ORDER_ID`, `CUSTOMER_ID`); with a primary key already on `ORDER_ID`, it would be redundant. Never copy UNIQUE constraints mechanically without checking their purpose.

**FOREIGN KEY:** if the target operates as a transactional table linked to customers:

```sql
ALTER TABLE lab_ctas_orders_copy
    ADD CONSTRAINT fk_lab_ctas_copy_customer
    FOREIGN KEY (customer_id)
    REFERENCES lab_ctas_customers (customer_id);
```

Before adding an FK, check for rows pointing to nonexistent parents:

```sql
SELECT o.customer_id, COUNT(*) AS rows_without_parent
FROM lab_ctas_orders_copy o
LEFT JOIN lab_ctas_customers c
       ON c.customer_id = o.customer_id
WHERE o.customer_id IS NOT NULL
  AND c.customer_id IS NULL
GROUP BY o.customer_id;
```

If you took a snapshot of historical data and the parent table later changed, adding an FK may fail or be unwanted due to orphan rows. An analytical snapshot might intentionally omit FKs—make that a **deliberate design decision**, not an oversight.

**CHECK:**

```sql
ALTER TABLE lab_ctas_orders_copy
    ADD CONSTRAINT ck_lab_ctas_copy_amount
    CHECK (amount >= 0);

ALTER TABLE lab_ctas_orders_copy
    ADD CONSTRAINT ck_lab_ctas_copy_status
    CHECK (status IN ('NEW', 'PAID', 'CANCELLED'));
```

If CTAS transformed columns via expressions changing their semantics, do not blindly copy source CHECKs. For example, an aggregated summary table's `TOTAL_AMOUNT` may need different rules from a single order's amount.

### 5.3. NOT NULL Is the Nuanced Exception

Oracle **can inherit `NOT NULL`** from a source table in CTAS depending on the SELECT shape—such as selecting a `NOT NULL` source column directly under qualifying Oracle rules. Conversely, with expressions, JOINs, complex SELECT structures, or certain types/settings, inheritance is not guaranteed.

Therefore, **both extremes are wrong**:

1. "CTAS always drops every NOT NULL."
2. "CTAS always keeps every NOT NULL from the source table."

Check metadata directly:

```sql
SELECT table_name, column_name, nullable
FROM user_tab_columns
WHERE table_name IN ('LAB_CTAS_ORDERS', 'LAB_CTAS_ORDERS_COPY')
ORDER BY table_name, column_id;
```

And constraints:

```sql
SELECT table_name, constraint_name, constraint_type,
       status, validated, search_condition_vc
FROM user_constraints
WHERE table_name IN ('LAB_CTAS_ORDERS', 'LAB_CTAS_ORDERS_COPY')
ORDER BY table_name, constraint_type, constraint_name;
```

In releases supporting `SEARCH_CONDITION_VC`, it displays CHECK/NOT NULL conditions as VARCHAR2 (watch length limits and older versions). If your environment lacks that column, select the common columns `TABLE_NAME`, `CONSTRAINT_NAME`, `CONSTRAINT_TYPE`, `STATUS`, and `VALIDATED`.

A type `C` constraint in `USER_CONSTRAINTS` can be either **NOT NULL** or a **CHECK** constraint; inspect the column and condition rather than just counting type `C` rows.

If `STATUS` must be mandatory:

```sql
ALTER TABLE lab_ctas_orders_copy
    MODIFY (status NOT NULL);
```

If Oracle already inherited `NOT NULL` on that column, omit the duplicate `MODIFY`; check metadata first so you issue only needed DDL.

### 5.4. Constraint States Are Metadata Too

Beyond constraint type, the source table may carry attributes such as:

- `ENABLED` or `DISABLED`.
- `VALIDATED` or `NOT VALIDATED`.
- `DEFERRABLE` and `INITIALLY DEFERRED/IMMEDIATE`.
- Foreign key `ON DELETE` rules.
- Standardized constraint naming conventions.

When building a target table for production business use, adding a constraint of "the same type" does not guarantee **the same behavior**. Compare metadata carefully and decide which states to preserve.

## 6. DEFAULT, IDENTITY, Generated Columns, and Captured Data

### 6.1. Existing Values Are Copied, Defaults Are Not

In the source table:

```sql
status     VARCHAR2(20) DEFAULT 'NEW' NOT NULL,
created_at DATE DEFAULT SYSDATE NOT NULL
```

When CTAS selects `STATUS` and `CREATED_AT`, **existing row values are copied**. However, the target table does not automatically get `DEFAULT 'NEW'` or `DEFAULT SYSDATE` for future INSERTs.

Inspect:

```sql
SELECT table_name, column_name, nullable, data_default
FROM user_tab_columns
WHERE table_name IN ('LAB_CTAS_ORDERS', 'LAB_CTAS_ORDERS_COPY')
  AND column_name IN ('STATUS', 'CREATED_AT', 'AMOUNT')
ORDER BY table_name, column_name;
```

`DATA_DEFAULT` is typed as `LONG` in several dictionary views; inspect it in your SQL client instead of trying to `ORDER BY` it directly.

If the target needs defaults:

```sql
ALTER TABLE lab_ctas_orders_copy
    MODIFY (status DEFAULT 'NEW');

ALTER TABLE lab_ctas_orders_copy
    MODIFY (created_at DEFAULT SYSDATE);
```

Setting a default **does not retroactively modify existing stored values**. `DEFAULT ON NULL` or complex default expressions must be re-created with their exact semantics rather than assuming plain `DEFAULT` is equivalent.

### 6.2. IDENTITY Is More Than Numbers in a Column

Suppose the source table has:

```sql
id NUMBER GENERATED BY DEFAULT ON NULL AS IDENTITY
```

CTAS copies **existing ID values** when selecting `id`, yet **automatic generation for future INSERTs is not cloned**. For identity-based tables, query identity metadata such as `USER_TAB_IDENTITY_COLS` on supporting versions:

```sql
SELECT table_name, column_name, generation_type
FROM user_tab_identity_cols
WHERE table_name IN ('LAB_CTAS_ORDERS', 'LAB_CTAS_ORDERS_COPY')
ORDER BY table_name, column_name;
```

This query applies to versions supporting identity columns; do not expect this view on older releases.

Re-establishing an identity generator on a table that already contains IDs requires **careful generator design and starting-value alignment** to prevent collisions. Never start a new sequence at 1 if the copied table already holds keys 1, 2, 3, ...

### 6.3. VIRTUAL, INVISIBLE, and GENERATED Properties

Columns computed from expressions (**virtual columns**) or marked **invisible** behave specially; `SELECT *` generally omits invisible columns. When you explicitly SELECT a virtual column, its computed value is materialized as regular column data in the new table, **without preserving the virtual formula**.

Conceptual example:

```sql
CREATE TABLE lab_ctas_price_source (
    net_amount NUMBER(10, 2),
    tax_amount NUMBER(10, 2),
    gross_amount NUMBER(12, 2)
        GENERATED ALWAYS AS (net_amount + tax_amount) VIRTUAL
);

CREATE TABLE lab_ctas_price_copy AS
SELECT net_amount, tax_amount, gross_amount
FROM lab_ctas_price_source;
```

In the target, `GROSS_AMOUNT` holds the values evaluated at CTAS time; **do not assume virtual recalculation continues** if `NET_AMOUNT` is later updated. Check `USER_TAB_COLS` for virtual/hidden attributes where supported:

```sql
SELECT table_name, column_name, data_type,
       nullable, virtual_column, hidden_column
FROM user_tab_cols
WHERE table_name IN ('LAB_CTAS_PRICE_SOURCE', 'LAB_CTAS_PRICE_COPY')
ORDER BY table_name, column_id;
```

For expressions in `SELECT`, Oracle infers target names and types from the expression or alias. For a stable schema, specify explicit names and types deliberately.

## 7. Data Types and Column Names When SELECT Uses Expressions

CTAS does not only clone columns from one table. When SELECT transforms values, **target column types match the expression result type**, not necessarily the original column type.

Example:

```sql
CREATE TABLE lab_ctas_order_summary AS
SELECT
    CAST(customer_id AS NUMBER(10)) AS customer_id,
    CAST(COUNT(*) AS NUMBER(10)) AS order_count,
    CAST(SUM(amount) AS NUMBER(14, 2)) AS total_amount
FROM lab_ctas_orders
WHERE status = 'PAID'
GROUP BY customer_id;
```

Here:

- `ORDER_COUNT` is an aggregate result, not a source table column.
- `TOTAL_AMOUNT` sums across rows and needs sufficient precision/scale.
- `CAST` makes target types explicit instead of relying on complex expression type inference.
- Never blindly assign a primary key to `CUSTOMER_ID` if a query variant could produce multiple rows per customer.

### 7.1. Aliases and Duplicate Column Names

In CTAS with multi-expression SELECTs, every target column must have a valid, non-duplicate name. Joining two tables that both have `ID` with `SELECT a.id, b.id` fails in CTAS due to duplicate column names. Use aliases:

```sql
CREATE TABLE lab_ctas_pairs AS
SELECT a.customer_id AS customer_id,
       o.order_id    AS order_id
FROM lab_ctas_customers a
JOIN lab_ctas_orders o
  ON o.customer_id = a.customer_id;
```

For expressions like `SUM(amount)`, write `AS total_amount` instead of letting Oracle reject an unaliased expression. Avoid double-quoted aliases, which create case-sensitive column names that are awkward in later queries.

### 7.2. NULL Literals and CAST

If a new column should hold NULL in every row, declare its type explicitly:

```sql
CREATE TABLE lab_ctas_with_review_flag AS
SELECT order_id,
       CAST(NULL AS VARCHAR2(30)) AS review_note
FROM lab_ctas_orders;
```

Never write bare `NULL AS review_note` in CTAS expecting Oracle to guess your desired type and length; in many cases it raises an error or produces an unintended type.

### 7.3. DATE, TIMESTAMP, NUMBER, and VARCHAR2

Applying `TO_CHAR(created_at, ...)` turns the target column into **text**, no longer DATE/TIMESTAMP. Applying `TRUNC(created_at)` keeps a date-related type truncated per function rules. Arithmetic or `NVL` expressions infer types according to Oracle expression rules.

Never assume a CTAS table built from a reporting query matches a transactional table's schema. Inspect:

```sql
SELECT table_name,
       column_id,
       column_name,
       data_type,
       data_length,
       data_precision,
       data_scale,
       char_used,
       nullable
FROM user_tab_columns
WHERE table_name IN ('LAB_CTAS_ORDERS', 'LAB_CTAS_ORDERS_COPY',
                     'LAB_CTAS_ORDER_SUMMARY')
ORDER BY table_name, column_id;
```

`CHAR_USED` distinguishes byte vs. character length semantics on character columns; `DATA_LENGTH` does not always equal the UI's maximum character count.

## 8. Indexes, Triggers, Sequences, and Associated Objects

### 8.1. CTAS Does Not Copy Indexes

A source table may have several indexes for primary keys, foreign keys, searches, or function-based lookups. The new CTAS table **receives none of them**.

Inspect:

```sql
SELECT table_name, index_name, uniqueness, index_type, status
FROM user_indexes
WHERE table_name IN ('LAB_CTAS_ORDERS', 'LAB_CTAS_ORDERS_COPY')
ORDER BY table_name, index_name;
```

Index columns:

```sql
SELECT index_name, column_position, column_name, descend
FROM user_ind_columns
WHERE table_name IN ('LAB_CTAS_ORDERS', 'LAB_CTAS_ORDERS_COPY')
ORDER BY index_name, column_position;
```

For function-based indexes, also check `USER_IND_EXPRESSIONS`. If the new table serves only a one-off reconciliation, you may **not need** every source index. If it serves long-term application traffic, create indexes tailored to **actual queries**, constraints, and data.

Example adding an index for queries filtering by `CUSTOMER_ID`:

```sql
CREATE INDEX idx_lab_ctas_copy_customer
ON lab_ctas_orders_copy (customer_id);
```

Indexes consume storage and write time; never add them blindly just because the source had them.

### 8.2. Triggers Do Not Follow CTAS

A `BEFORE INSERT` trigger on the source might generate codes, write audit rows, check rules, or update auxiliary tables. CTAS creates a **separate table**; source triggers are never attached to it automatically.

Inspect:

```sql
SELECT table_name,
       trigger_name,
       trigger_type,
       triggering_event,
       status
FROM user_triggers
WHERE table_name IN ('LAB_CTAS_ORDERS', 'LAB_CTAS_ORDERS_COPY')
ORDER BY table_name, trigger_name;
```

Before recreating triggers on a target table, verify their **business intent**. A production audit trigger might be wrong for a test snapshot. Conversely, omitting a key-generation trigger on a replacement table will break new INSERTs.

### 8.3. Sequences, Synonyms, and External Objects

If an application uses `MY_SEQ.NEXTVAL` to populate source IDs, CTAS copies **only existing IDs** when you select that column. It does not create a new sequence, advance any sequence start value, or repoint synonyms to the new table.

In legacy systems, application DML may rely on coordinated sequences, triggers, synonyms, and grants. Audit every write path before switching to a new table, not just `SELECT COUNT(*)`.

## 9. Comments, Privileges, and Security Policies Are Not Cloned

### 9.1. Comments

Table and column comments help tools and engineers understand data:

```sql
COMMENT ON TABLE lab_ctas_orders
IS 'CTAS practice orders table';

COMMENT ON COLUMN lab_ctas_orders.amount
IS 'Order amount';
```

After CTAS, **never assume comments carried over to the copy**. Check:

```sql
SELECT table_name, comments
FROM user_tab_comments
WHERE table_name IN ('LAB_CTAS_ORDERS', 'LAB_CTAS_ORDERS_COPY')
ORDER BY table_name;

SELECT table_name, column_name, comments
FROM user_col_comments
WHERE table_name IN ('LAB_CTAS_ORDERS', 'LAB_CTAS_ORDERS_COPY')
ORDER BY table_name, column_name;
```

When appropriate, copy comments or write new ones documenting **the source and snapshot timestamp**:

```sql
COMMENT ON TABLE lab_ctas_orders_copy
IS 'CTAS copy for practice; not auto-synced';
```

### 9.2. Source Table GRANTs Are Not Inherited

Suppose user `APP_READER` holds `SELECT` on `LAB_CTAS_ORDERS`. That does not grant read access on `LAB_CTAS_ORDERS_COPY`.

Inspect granted privileges where applicable and permitted:

```sql
SELECT table_name, grantee, privilege, grantable
FROM user_tab_privs_made
WHERE table_name IN ('LAB_CTAS_ORDERS', 'LAB_CTAS_ORDERS_COPY')
ORDER BY table_name, grantee, privilege;
```

If the new table must be shared, the owner should grant least-privilege access explicitly:

```sql
-- Example only when APP_READER exists and is approved:
-- GRANT SELECT ON lab_ctas_orders_copy TO app_reader;
```

Never blindly clone all source grants. A snapshot table might hold sensitive data or belong to a test environment; access rights must be reviewed deliberately.

### 9.3. Row-Level Security, Masking, and Encryption

A source table may be governed by:

- **VPD / row-level security** restricting which rows a user sees.
- **Data Redaction** or masking/presentation policies.
- **Auditing** and specialized access rules.
- **Column/tablespace encryption** and sensitive storage policies.

**Never assume CTAS transfers these policies to the new table.** The source `SELECT` sees only rows visible under your session context, yet the new table must have its own security controls verified independently. Understand how policies transform queried values before copying them.

Never run CTAS from a sensitive table into a less-secure schema or tablespace just for a "quick backup." CTAS is no substitute for proper backups, data masking, and data governance.

## 10. Tablespace, Partitioning, Compression, LOBs, and Logging

### 10.1. Storage Location Is Not Automatically Preserved

Unless specified, a CTAS table follows **the user's default tablespace and DDL defaults**; a source in `APP_DATA` does not guarantee the target lands in `APP_DATA`.

Explicit example:

```sql
CREATE TABLE lab_ctas_orders_in_data
TABLESPACE app_data
AS
SELECT order_id, customer_id, amount, status
FROM lab_ctas_orders;
```

This succeeds only if `APP_DATA` exists and your user has quota/privileges on it. In a lab schema without `APP_DATA`, omit `TABLESPACE` or substitute your configured tablespace.

Inspect in the dictionary:

```sql
SELECT table_name,
       tablespace_name,
       partitioned,
       temporary,
       logging,
       compression,
       compress_for
FROM user_tables
WHERE table_name IN ('LAB_CTAS_ORDERS', 'LAB_CTAS_ORDERS_COPY')
ORDER BY table_name;
```

Some compression columns depend on version/edition; for partitioned tables, table-level `TABLESPACE_NAME` alone does not show where all partitions/subpartitions reside.

### 10.2. Partitioning Does Not Carry Over Automatically

Even if the source is range- or hash-partitioned, standard CTAS creates a non-partitioned table unless you explicitly **define partitioning in `CREATE TABLE`** (on supporting versions/features) and verify afterward:

```sql
SELECT table_name, partitioning_type, subpartitioning_type
FROM user_part_tables
WHERE table_name = 'LAB_CTAS_ORDERS_COPY';
```

For partitioned tables, also inspect `USER_TAB_PARTITIONS`/`USER_TAB_SUBPARTITIONS` and related indexes. Never put a CTAS table into production traffic only to discover later that all rows sit in a single unpartitioned segment.

### 10.3. LOB Storage and Column Properties

For `CLOB`, `BLOB`, or other LOB types, CTAS creates LOB columns from SELECT output, yet **SecureFiles/BasicFiles, LOB storage, retention/compression/deduplication, and encryption** settings do not automatically match the source. Check metadata:

```sql
SELECT table_name, column_name, segment_name,
       tablespace_name, securefile
FROM user_lobs
WHERE table_name IN ('LAB_CTAS_ORDERS', 'LAB_CTAS_ORDERS_COPY')
ORDER BY table_name, column_name;
```

Some `USER_LOBS` columns and SecureFiles capabilities vary by release/edition; this query applies when tables contain LOBs. On lab tables without LOBs, zero rows is expected.

### 10.4. LOGGING, NOLOGGING, and Recovery

CTAS can be tuned for bulk loads using `PARALLEL` or `NOLOGGING` depending on environment. That is an **operational decision**, not just a speed tweak.

Specialized syntax example:

```sql
CREATE TABLE lab_ctas_bulk_copy
NOLOGGING
AS
SELECT order_id, customer_id, amount, status
FROM lab_ctas_orders;
```

**Never use `NOLOGGING` by default for critical data.** Nologging loads can reduce redo generation for bulk data in supported Oracle modes, yet still emit metadata redo; `FORCE LOGGING` or database policies may override it. Unlogged changes introduce **media recovery and standby risks** if backups and synchronization are not handled properly.

When using CTAS for large loads:

1. Verify recovery/RPO and Data Guard requirements.
2. Check organization-approved logging settings.
3. Size tablespace, TEMP, UNDO, redo, and storage capacity.
4. Plan post-load statistics, indexes, and constraints.
5. Schedule backups and verify recovery whenever nologging is used.

CTAS **is not a physical backup replacing RMAN**. A copy inside the same database/tablespace cannot protect against storage failure, database-level corruption, or severe operational mistakes.

## 11. DDL, COMMIT, and Data Consistency

### 11.1. CTAS Is DDL, with Implicit Commit

In Oracle, `CREATE TABLE` is **DDL**, even with `AS SELECT`. DDL triggers implicit commits on the current transaction per Oracle semantics; executing DDL after uncommitted DML **commits those prior changes** even if you thought you were inside an application transaction.

Pattern to avoid in applications:

```sql
UPDATE orders
SET order_status = 'PAID'
WHERE order_id = 1001;

-- Creating a table below is DDL, not an INSERT step
-- that can ROLLBACK with the business transaction.
CREATE TABLE orders_checkpoint AS
SELECT * FROM orders;

ROLLBACK;
```

`ROLLBACK` after CTAS **will not drop the newly created table or undo table creation**. Manage staging tables via approved create/drop workflows, never transaction rollbacks.

### 11.2. CTAS Is a Point-in-Time Logical Snapshot

CTAS materializes whatever the `SELECT` sees under Oracle **read consistency**. It establishes no ongoing sync link with the source table.

```text
T0:  CTAS begins reading ORDERS
      ↓
      Reads a consistent dataset as of its query snapshot
      ↓
T1:  Creates ORDERS_SNAPSHOT with selected results
      ↓
T2:  Source continues receiving INSERT / UPDATE / DELETE
      ↓
      Snapshot table does NOT automatically update with source
```

If the source receives concurrent writes, snapshot contents may differ from the source when you re-check afterward. That is normal snapshot behavior—not necessarily missing rows.

For migrations requiring consistency across **multiple tables**, use consistent flashback/SCN snapshots, cutover windows, or dedicated tools rather than running separate CTAS statements at different moments and assuming they share one snapshot.

### 11.3. CTAS Does Not Guarantee Physical or Query Ordering Later

Even if a CTAS SELECT includes an ordering clause where permitted, **a relational table is an unordered set with no guaranteed row order on subsequent reads**.

When reading the copy, always specify explicit ordering:

```sql
SELECT order_id, amount
FROM lab_ctas_orders_copy
ORDER BY order_id;
```

Never build pagination assuming "CTAS loaded rows in date order" without `ORDER BY`. Include a unique tie-breaker column whenever sort values can tie.

## 12. Verifying the Target Table via the Data Dictionary

A solid CTAS reconciliation checks more than `SELECT COUNT(*)`. Inspect layer by layer:

```text
                 SOURCE TABLE
                      │
                  CREATE TABLE
                   AS SELECT
                      │
                      ▼
                 TARGET TABLE
                      │
       ┌──────────────┼────────────────────────┐
       ▼              ▼                        ▼
     Data        Column Definitions     Other Attributes
   COUNT/SUM       USER_TAB_COLUMNS      USER_CONSTRAINTS
   NULL/DUPLICATE  USER_TAB_COLS         USER_INDEXES
   MIN/MAX         USER_TAB_IDENTITY...  USER_TRIGGERS
                                         USER_TAB_COMMENTS
                                         USER_TAB_PRIVS...
                                         USER_TABLES/USER_LOBS
                      │
                      ▼
           Recreate needed attributes
                      │
                      ▼
          Re-verify and hand off
```

### 12.1. Does the Target Exist as the Right Object Type?

```sql
SELECT object_name, object_type, status
FROM user_objects
WHERE object_name IN (
    'LAB_CTAS_ORDERS',
    'LAB_CTAS_ORDERS_COPY'
)
ORDER BY object_name;
```

For objects in another schema, query `ALL_OBJECTS` filtered by `OWNER` where permitted. In CDB/PDB, confirm the right service/container first to avoid comparing identically named tables in different containers.

### 12.2. Comparing Row Counts and Business Totals

When CTAS copied the full orders table:

```sql
SELECT 'SOURCE' AS source_name,
       COUNT(*) AS row_count,
       SUM(amount) AS amount_sum
FROM lab_ctas_orders
UNION ALL
SELECT 'COPY' AS source_name,
       COUNT(*) AS row_count,
       SUM(amount) AS amount_sum
FROM lab_ctas_orders_copy;
```

Sample output when no writes occurred after CTAS:

| SOURCE_NAME | ROW_COUNT | AMOUNT_SUM |
| --- | ---: | ---: |
| SOURCE | 3 | 235.50 |
| COPY | 3 | 235.50 |

**Never conclude two tables are identical merely because COUNT and SUM match.** Different rows can add up to the same sum. If the source keeps receiving writes, current source totals will diverge from the target snapshot. Reconcile against the same snapshot or use row-level verification matching requirements.

Checking NULLs and uniqueness:

```sql
SELECT COUNT(*) AS row_count,
       COUNT(order_id) AS nonnull_order_ids,
       COUNT(DISTINCT order_id) AS distinct_order_ids,
       SUM(CASE WHEN status IS NULL THEN 1 ELSE 0 END) AS null_status_rows
FROM lab_ctas_orders_copy;
```

These checks catch anomalies before adding constraints.

### 12.3. Comparing Column Names, Types, and Precision/Scale

```sql
SELECT table_name,
       column_id,
       column_name,
       data_type,
       data_length,
       data_precision,
       data_scale,
       nullable
FROM user_tab_columns
WHERE table_name IN (
    'LAB_CTAS_ORDERS',
    'LAB_CTAS_ORDERS_COPY'
)
ORDER BY table_name, column_id;
```

In practice, also compare `DATA_DEFAULT`, `CHAR_USED`, collation, identity settings, and hidden/virtual properties when used. Those details are easily overlooked if you inspect only names and `VARCHAR2`.

### 12.4. Comparing Constraints and Participating Columns

```sql
SELECT c.table_name,
       c.constraint_name,
       c.constraint_type,
       cc.column_name,
       cc.position,
       c.status,
       c.validated
FROM user_constraints c
LEFT JOIN user_cons_columns cc
       ON cc.constraint_name = c.constraint_name
WHERE c.table_name IN (
    'LAB_CTAS_ORDERS',
    'LAB_CTAS_ORDERS_COPY'
)
ORDER BY c.table_name, c.constraint_name, cc.position;
```

In `USER_CONSTRAINTS`:

- `P` = primary key.
- `U` = unique.
- `R` = referential / foreign key.
- `C` = check, including `NOT NULL` representations where applicable.

System-generated names and display order may differ. To check exact conditions and referenced parent tables/constraints, read the corresponding metadata columns rather than only constraint type.

### 12.5. Comparing Indexes and Triggers

```sql
SELECT table_name, index_name, uniqueness
FROM user_indexes
WHERE table_name IN ('LAB_CTAS_ORDERS', 'LAB_CTAS_ORDERS_COPY')
ORDER BY table_name, index_name;

SELECT table_name, trigger_name, status
FROM user_triggers
WHERE table_name IN ('LAB_CTAS_ORDERS', 'LAB_CTAS_ORDERS_COPY')
ORDER BY table_name, trigger_name;
```

If the source had a PK backing index, the target gets a corresponding index **only after you add the constraint/index on the target**.

### 12.6. Comparing Full Definitions with DBMS_METADATA

Oracle provides `DBMS_METADATA.GET_DDL` to extract object DDL when privileged:

```sql
SELECT DBMS_METADATA.GET_DDL(
           'TABLE',
           'LAB_CTAS_ORDERS',
           USER
       ) AS source_ddl
FROM dual;

SELECT DBMS_METADATA.GET_DDL(
           'TABLE',
           'LAB_CTAS_ORDERS_COPY',
           USER
       ) AS target_ddl
FROM dual;
```

In SQL*Plus, increase CLOB display length (e.g., `SET LONG 20000`) to see the full DDL. `DBMS_METADATA` output varies with transform parameters, privileges, edition, and Oracle version. Secondary objects like non-constraint indexes, grants, and triggers often require extracting by **their own object types** or separate scripts rather than assuming `GET_DDL('TABLE', ...)` includes everything.

For quick targeted checks, dictionary views remain faster and simpler.

## 13. Deliberately Re-Adding Attributes After CTAS

A standard workflow when preparing a **long-lived target table**:

1. **Clarify purpose:** read-only snapshot, staging, reporting, or replacing a transactional table?
2. **Define column list:** direct columns or expressions? Use `CAST` and explicit aliases where needed.
3. **Run CTAS in an authorized environment** and confirm load completion.
4. **Verify data:** row counts, NULLs, duplicates, business totals, FK validity.
5. **Verify metadata:** types, precision, nullability, defaults, identity, generated columns.
6. **Add required constraints** after ensuring target rows satisfy them.
7. **Create workload-driven indexes** and evaluate storage costs.
8. **Review triggers, sequences, privileges, comments, and security policies** for the intended use.
9. **Review tablespace, partitioning, LOBs, logging, stats, and backup/recovery** before going live.
10. **Run application tests:** do inserts/updates/deletes, APIs, and state transitions behave properly?

For example, on `LAB_CTAS_ORDERS_COPY` after verifying no duplicate keys exist, we can add:

```sql
ALTER TABLE lab_ctas_orders_copy
    ADD CONSTRAINT pk_lab_ctas_orders_copy PRIMARY KEY (order_id);

ALTER TABLE lab_ctas_orders_copy
    MODIFY (customer_id NOT NULL);

ALTER TABLE lab_ctas_orders_copy
    MODIFY (amount DEFAULT 0);

ALTER TABLE lab_ctas_orders_copy
    MODIFY (status DEFAULT 'NEW');

ALTER TABLE lab_ctas_orders_copy
    ADD CONSTRAINT ck_lab_ctas_copy_amount CHECK (amount >= 0);

CREATE INDEX idx_lab_ctas_copy_customer
    ON lab_ctas_orders_copy(customer_id);
```

These are **illustrative snippets for the lab object**, not a universal source-cloning script. If PK, NOT NULL, or indexes were already added in earlier steps, do not re-run duplicates. For an immutable snapshot, many constraints and indexes may be unnecessary, while comments/metadata documenting snapshot time are essential.

### 13.1. Optimizer Statistics After CTAS

When CTAS loads substantial data, Oracle may gather optimizer statistics automatically during creation depending on release and conditions. Still, **never assume the new table inherits source statistics** or that stats are always optimal for new queries.

Check:

```sql
SELECT table_name,
       num_rows,
       blocks,
       last_analyzed,
       stale_stats
FROM user_tab_statistics
WHERE table_name IN ('LAB_CTAS_ORDERS', 'LAB_CTAS_ORDERS_COPY');
```

In large production environments, `DBMS_STATS` gathering must follow policy and data volume guidelines; never trigger a schema-wide stats job in production simply because you ran CTAS.

### 13.2. Creation Time and Ownership

`USER_OBJECTS.CREATED` on the target reflects when the new object was created, not the source table's creation time. Target owner/schema follows the `CREATE TABLE` context, not necessarily `source_owner` in `FROM source_owner.source_table`.

In multi-schema architectures, record **source owner, target owner, PDB, timestamp**, and data version clearly. Two identically named tables in separate PDBs can have completely different metadata.

## 14. Common Errors When Using CTAS

| Error / Symptom | Typical Cause | Resolution |
| --- | --- | --- |
| `ORA-00955: name is already used by an existing object` | Target table or object name already exists | Pick a new name or manage lifecycle properly; never drop hastily |
| `ORA-00942: table or view does not exist` | Wrong owner/PDB, wrong name, or missing privileges | Check current schema, grants, and qualified source name |
| `ORA-01031: insufficient privileges` | Missing `CREATE TABLE` or DDL capability | Verify required grants and quota |
| `ORA-01950: no privileges on tablespace` | Missing quota on target tablespace | Request valid quota or target another tablespace |
| `ORA-01653: unable to extend table` | Target tablespace/storage cannot allocate extent | Check tablespace, datafiles/autoextend, ASM/filesystem space |
| `ORA-00918: column ambiguously defined` | Ambiguous or duplicate column names in source query | Use unique column aliases |
| `ORA-01723: zero-length columns are not allowed` | Expression fails to infer valid length/type | Use explicit `CAST` with type and length, especially for `NULL` literals |
| New INSERT into copy lacks default | CTAS did not carry over defaults | Check `DATA_DEFAULT` and add defaults as needed |
| Duplicates appear after CTAS | Missing PK/UNIQUE; JOIN multiplied rows | Audit data and add appropriate constraints |
| Application keys no longer auto-generate | Identity/sequence/trigger not cloned | Re-establish key generation avoiding ID collisions |
| Queries on copy run slower than source | Missing indexes, different stats, different layout | Check execution plans, workload, indexes, and stats |
| Another user cannot read copy | Source grants not inherited | Grant least-privilege access on the new table |
| Sensitive data exposed in snapshot | Target lacks security policies/masking/grants | Stop distribution, verify security controls and copy process |
| Source and target COUNT mismatch | `WHERE`, `JOIN`, ongoing source writes, or query logic bug | Compare at the same snapshot/scope with matching predicates |
| `ROLLBACK` fails to drop copy | CTAS is DDL with implicit commit | Manage object lifecycle with explicit DDL, not rollback |

Never fix all these issues by blindly re-running CTAS with `SELECT *`. Identify whether the root cause lies in **the source SELECT, privileges/DDL, loaded rows, or target metadata** before acting.

## 15. Business Scenarios Requiring the Right Approach

### Scenario A — Quick Backup Before Migration

A team wants to run:

```sql
CREATE TABLE orders_backup AS
SELECT * FROM orders;
```

**Pros:** creates a queryable data snapshot inside the same database. **Limits:** not a system-level recovery backup, omits constraints/indexes/grants/triggers, and shares the same storage infrastructure. Before major migrations, use proper backup/recovery tools (like RMAN/Data Pump), verified snapshots, and environment controls.

### Scenario B — Building a Reporting Table from a JOIN

Multi-table CTAS works well for period-end reporting tables, yet you should avoid copying every source foreign key and trigger onto a read-only report. Focus instead on clean column names, data types, aggregate accuracy, refresh strategy, reporting indexes, `SELECT` grants, and report cutoff timestamps.

### Scenario C — Creating a Staging Table Before Import

`WHERE 1 = 0` scaffolds an empty table quickly, yet missing constraints/defaults can admit dirty data. A staging table may **intentionally relax constraints** to capture bad rows, provided validation runs before loading into core business tables. If staging itself must enforce types and uniqueness on load, declare explicit constraints instead of relying on CTAS.

### Scenario D — Replacing a Transactional Table via CTAS

This is high-risk: applications may depend on key-generation triggers, identity columns, grants, indexes, partitions, security policies, and incoming foreign keys from other tables. A CTAS copy with identical row data can still be **incompatible with the application**. You need full migration scripts, cutover plans, dependency checks, backups, and deployment-level rollback plans. Never rename or drop a production table based solely on a CTAS copy.

### Scenario E — Splitting Data by Year

```sql
CREATE TABLE lab_ctas_orders_2025 AS
SELECT order_id, customer_id, amount, status, created_at
FROM lab_ctas_orders
WHERE created_at >= DATE '2025-01-01'
  AND created_at < DATE '2026-01-01';
```

Half-open date intervals select date/time ranges cleanly without implicit text conversions. The resulting table suits analysis, yet you must decide whether it acts as an **archive, snapshot, or live operational table**. If an archive has retention and security mandates, CTAS is merely the data-copy step.

## 16. Hands-On Lab: Comparing Source and CTAS Tables

**Prerequisites:** `CREATE TABLE` privilege in a lab schema, sufficient quota, and `LAB_CTAS_CUSTOMERS`/`LAB_CTAS_ORDERS` created from Section 3. Create and inspect only lab objects; never modify production tables.

### Part A — Create the Copy and Verify Rows

If not already created:

```sql
CREATE TABLE lab_ctas_orders_copy AS
SELECT order_id, customer_id, amount, status, created_at, note
FROM lab_ctas_orders;
```

Run:

```sql
SELECT COUNT(*) AS copied_rows,
       SUM(amount) AS total_amount
FROM lab_ctas_orders_copy;
```

With unmodified sample data, expected values are **3** rows and **235.50** total amount. If they differ, verify your INSERTs, CTAS query, and source state rather than assuming everything ran cleanly.

### Part B — Inspect Data Types and DEFAULTs

```sql
SELECT table_name, column_name, data_type,
       data_precision, data_scale, nullable, data_default
FROM user_tab_columns
WHERE table_name IN ('LAB_CTAS_ORDERS', 'LAB_CTAS_ORDERS_COPY')
  AND column_name IN ('ORDER_ID', 'AMOUNT', 'STATUS', 'CREATED_AT')
ORDER BY table_name, column_name;
```

Write down a comparison table: what are the types and nullability of `ORDER_ID`, `AMOUNT`, `STATUS`, and `CREATED_AT`? Are `DEFAULT 0`, `DEFAULT 'NEW'`, and `DEFAULT SYSDATE` still present on the copy?

### Part C — Inspect Constraints

```sql
SELECT table_name, constraint_name, constraint_type,
       status, validated
FROM user_constraints
WHERE table_name IN ('LAB_CTAS_ORDERS', 'LAB_CTAS_ORDERS_COPY')
ORDER BY table_name, constraint_type, constraint_name;
```

Determine:

1. Which PK, FK, and CHECK constraints exist on the source?
2. Did the target automatically inherit PK/FK/CHECK?
3. Which `NOT NULL` constraints exist on the target, and under what CTAS rules were they inherited?
4. If the target will accept new INSERTs, which constraints would you add and **how would you check existing data first**?

### Part D — Inspect Indexes and Triggers

```sql
SELECT table_name, index_name, uniqueness
FROM user_indexes
WHERE table_name IN ('LAB_CTAS_ORDERS', 'LAB_CTAS_ORDERS_COPY')
ORDER BY table_name, index_name;
```

Locate the PK index and `IDX_LAB_CTAS_ORDERS_CUSTOMER` on the source. Which indexes exist on the target right after CTAS? If you later add a PK on the target, how does the index list change?

If no triggers were created on the source in this lab, seeing zero rows in `USER_TRIGGERS` is expected—which still reinforces the rule that triggers never transfer automatically via CTAS.

### Part E — Filtered CTAS and Empty CTAS

```sql
CREATE TABLE lab_ctas_paid_only AS
SELECT order_id, customer_id, amount
FROM lab_ctas_orders
WHERE status = 'PAID';

CREATE TABLE lab_ctas_empty_shape AS
SELECT order_id, customer_id, amount
FROM lab_ctas_orders
WHERE 1 = 0;
```

Compare:

```sql
SELECT 'PAID_ONLY' AS copy_type, COUNT(*) AS row_count
FROM lab_ctas_paid_only
UNION ALL
SELECT 'EMPTY_SHAPE', COUNT(*)
FROM lab_ctas_empty_shape;
```

With the sample dataset, `PAID_ONLY` has 1 row and `EMPTY_SHAPE` has 0 rows. Both still inherit column shapes inferred from SELECT without cloning all table constraints.

### Part F — Write a Handoff Checklist

Suppose `LAB_CTAS_ORDERS_COPY` will replace the source in a Java application:

- Does the API rely on `IDENTITY`/sequences/triggers for key generation?
- Which queries need matching indexes and execution plans?
- Which columns require `DEFAULT` or `NOT NULL`?
- Do external tables have foreign keys referencing the source?
- Which `GRANT`s, comments, masking, auditing, and backups are required?
- How do jobs, PL/SQL packages, synonyms, and views reference the old table name?
- Is there a tested rollback/cutover plan before modifying production?

Conclude whether **a single CTAS statement alone** suffices to replace a transactional table, and explain why.

## 17. End-of-Lesson Summary Table

| Goal | Is CTAS Appropriate? | Conditions |
| --- | --- | --- |
| Create an immediately queryable snapshot table | **Yes** | Understand snapshots do not auto-sync and are not standalone backups |
| Create an empty table matching a SELECT's columns | **Yes**, with `WHERE 1=0` | Do not assume constraints, defaults, or indexes carry over |
| Create a summary table from JOIN / GROUP BY | **Yes** | Define explicit aliases/types and verify aggregate correctness |
| Accurately clone PK/FK/UNIQUE/CHECK/DEFAULT/IDENTITY | **Not with CTAS alone** | Requires additional DDL/metadata and post-creation verification |
| Clone indexes, triggers, grants, security policies | **Not with CTAS alone** | Design and deploy separately |
| Create a new table with exact partitioning/compression/LOB storage | **Possible** with explicit DDL | Must be configured and verified explicitly, not inferred from source |
| Create a recoverable backup against database/storage loss | **No** | Use supported backup/recovery solutions |
| Replace a production table without disruption | **Insufficient** | Needs full migration/cutover, dependency, permission, and test plans |

```text
CREATE TABLE target AS SELECT ... FROM source
                     │
                     ▼
   COLUMNS + INFERRED TYPES + SELECTED ROWS
                     │
                     ▼
     ADDITIONAL VERIFICATION BEFORE USE
          ├── PK / UNIQUE / FK / CHECK / NOT NULL
          ├── DEFAULT / IDENTITY / VIRTUAL / INVISIBLE
          ├── INDEX / TRIGGER / SEQUENCE / SYNONYM
          ├── COMMENTS / PRIVILEGES / SECURITY
          ├── TABLESPACE / PARTITION / LOB / LOGGING
          ├── STATS / BACKUP / RECOVERY
          └── ROW COUNTS / VALUES / SNAPSHOT TIME
                     │
                     ▼
    TARGET TABLE VERIFIED FIT FOR PURPOSE
```

**Core takeaway:** CTAS is a powerful tool to **materialize a SELECT result into a new table**, not a command that clones every attribute of a source table. Once you clearly separate *data*, *column definitions*, and *supporting objects/constraints*, you can use CTAS rapidly in Oracle while keeping data integrity, security, and operability firmly under control.
