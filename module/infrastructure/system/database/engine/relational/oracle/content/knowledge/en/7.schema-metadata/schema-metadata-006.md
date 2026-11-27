# Querying Tables, Columns, Constraints, Indexes, and Statistics

When taking over an unfamiliar Oracle Database, the first question is usually not "which query should I write?", but rather **what tables exist in the database, how are the columns defined, what rules constrain the data, which indexes exist, and what statistics does Oracle hold to optimize SQL?** This information is stored in the **data dictionary** and can be queried via **dictionary views**.

For example, before writing a SQL query joining `ORDERS` with `CUSTOMERS`, a developer needs to know:

1. Which **schema** and **PDB** do the two tables reside in?
2. How are primary keys, foreign keys, and join columns declared?
3. Is `CUSTOMER_ID` a `NUMBER` or `VARCHAR2`? Is `NULL` allowed?
4. Is there a suitable index for filtering and joining?
5. Do optimizer statistics reflect recent data, or are they stale?

This lesson walks through a SQL-based metadata lookup workflow, from read-only queries to a small hands-on lab where you can create a sample schema yourself. The examples use standard Oracle Database dictionary views, prioritizing scopes readable by an application account; administrative views requiring additional privileges are explicitly noted.

## 1. What is metadata in Oracle?

**Metadata** is data describing the structure and management state of data:

| Subject | Metadata examples | How does it differ from business data? |
| --- | --- | --- |
| Table | Table name, owner, tablespace, organization type | Not the order rows stored inside the table |
| Column | Name, position, data type, length, precision, nullability | Not the specific values of individual rows |
| Constraint | Primary key, foreign key, unique, check, validation status | Rules protecting data, not query results |
| Index | Name, type, columns or expression, order, status, uniqueness | A data access structure, not a copy of the table in SQL terms |
| Statistics | Estimated row count, block count, value distinctness, histograms, collection timestamp | Input for the optimizer, not a real-time row count |

Oracle maintains internal metadata in the data dictionary. Views such as `USER_TABLES`, `ALL_TAB_COLUMNS`, `USER_CONSTRAINTS`, and `USER_INDEXES` provide a stable SQL interface for querying according to privileges. Users normally do not query underlying system base tables such as `SYS.OBJ$` or `SYS.TAB$` directly to inspect application structure.

### Metadata exists across multiple layers

```text
Oracle Database / CDB
  |
  +-- PDB APP_PDB
       |
       +-- Schema SALES_APP
       |      +-- TABLE CUSTOMERS
       |      |      +-- columns
       |      |      +-- constraints
       |      |      +-- related indexes
       |      +-- TABLE ORDERS
       |             +-- columns
       |             +-- constraints
       |             +-- related indexes
       |             +-- optimizer statistics
       |
       +-- Schema REPORT_APP
              +-- VIEW ORDER_SUMMARY
```

**PDB**, **schema**, and **table** are distinct boundaries. The same name `ORDERS` can exist in two schemas or two PDBs; querying metadata without checking owner/container easily leads to wrong conclusions.

## 2. Choosing the right scope: USER_, ALL_, DBA_, and CDB_

Oracle generally provides view families with similar columns but different **visibility scopes**.

| Prefix | Typical scope | Has `OWNER` column? | When to use |
| --- | --- | --- | --- |
| **`USER_*`** | Objects belonging to the current user's schema | Typically omits `OWNER` since there is only one owner | Inspecting tables/columns/indexes in your own schema |
| **`ALL_*`** | Objects the current account has access to or can see under Oracle rules | Usually includes `OWNER` | Applications working with tables across multiple schemas |
| **`DBA_*`** | Metadata for objects in the database/container within administrative scope | Includes `OWNER` | DBA inventory, structure auditing, and full granted scope |
| **`CDB_*`** | Multi-container metadata across a CDB, subject to privileges and connected container | Includes `CON_ID` and relevant owner columns | Cross-container CDB/PDB administration |

Example when logged into schema `SALES_APP`:

```sql
-- Tables owned by the current user.
SELECT table_name
FROM user_tables
ORDER BY table_name;

-- Tables visible to the user through access privileges.
SELECT owner, table_name
FROM all_tables
WHERE table_name = 'ORDERS'
ORDER BY owner, table_name;

-- Intended for accounts with DBA-level dictionary read privileges.
SELECT owner, table_name
FROM dba_tables
WHERE table_name = 'ORDERS'
ORDER BY owner, table_name;
```

**`ALL_*` does not mean "every table on the entire server"**: it is the subset of metadata the account is permitted to see. Missing results may stem from a nonexistent object, wrong PDB/schema, casing differences, or missing privileges. Do not request `SELECT ANY DICTIONARY` just to run standard SQL exercises.

### 2.1. Verify the session context first

```sql
SELECT
    SYS_CONTEXT('USERENV', 'DB_NAME')        AS database_name,
    SYS_CONTEXT('USERENV', 'CON_NAME')       AS container_name,
    SYS_CONTEXT('USERENV', 'SESSION_USER')   AS session_user_name,
    SYS_CONTEXT('USERENV', 'CURRENT_SCHEMA') AS current_schema_name
FROM dual;
```

- **`SESSION_USER`** is the user identity of the login session.
- **`CURRENT_SCHEMA`** is the default schema used to resolve unprefixed object names; it can be changed via `ALTER SESSION SET CURRENT_SCHEMA = ...` without **changing identity or granting extra privileges**.
- **`CON_NAME`** confirms you are connected to the right PDB. Logging into CDB root instead of the application PDB yields a different metadata set.
- **`DB_NAME`** identifies the database, though by itself it does not fully distinguish PDBs within the same CDB.

`USER_*` views describe objects **owned by the user**; they do not automatically become views of another schema just by changing `CURRENT_SCHEMA`. If an application changes its default schema, use `ALL_*` views filtered by `OWNER` to inspect other granted schemas.

### 2.2. Object names and case sensitivity

Oracle normally converts **unquoted** identifier names to uppercase in the dictionary:

```sql
CREATE TABLE orders (id NUMBER);
-- Dictionary normally records TABLE_NAME = 'ORDERS'.
```

If an identifier is created **with double quotes**:

```sql
CREATE TABLE "OrdersMixed" ("OrderId" NUMBER);
-- Dictionary preserves exact TABLE_NAME = 'OrdersMixed'.
```

Thus `WHERE TABLE_NAME = 'orders'` usually will not find a regular `ORDERS` table. For objects created with quoted identifiers, the name must match exactly. To avoid complexity across SQL and tooling, application schemas generally prefer unquoted names.

## 3. Sample tables for the queries in this lesson

To give the examples concrete object names, you can create two tables in a **dedicated practice schema** with `CREATE TABLE`, `CREATE INDEX`, and an appropriate tablespace quota. Never run DDL on a production schema or a schema managed by someone else.

```sql
CREATE TABLE lab_customers (
    customer_id   NUMBER GENERATED BY DEFAULT AS IDENTITY,
    customer_code VARCHAR2(20 CHAR)  NOT NULL,
    full_name     VARCHAR2(120 CHAR) NOT NULL,
    created_at    TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
    CONSTRAINT pk_lab_customers PRIMARY KEY (customer_id),
    CONSTRAINT uk_lab_customers_code UNIQUE (customer_code)
);

CREATE TABLE lab_orders (
    order_id    NUMBER GENERATED BY DEFAULT AS IDENTITY,
    customer_id NUMBER NOT NULL,
    amount      NUMBER(12, 2) DEFAULT 0 NOT NULL,
    status      VARCHAR2(12 CHAR) DEFAULT 'NEW' NOT NULL,
    created_at  TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
    CONSTRAINT pk_lab_orders PRIMARY KEY (order_id),
    CONSTRAINT fk_lab_orders_customer
        FOREIGN KEY (customer_id)
        REFERENCES lab_customers (customer_id),
    CONSTRAINT ck_lab_orders_amount CHECK (amount >= 0),
    CONSTRAINT ck_lab_orders_status
        CHECK (status IN ('NEW', 'PAID', 'CANCELLED'))
);

CREATE INDEX ix_lab_orders_customer_created
    ON lab_orders (customer_id, created_at);
```

Then insert a little sample data:

```sql
INSERT INTO lab_customers (customer_code, full_name)
VALUES ('C001', 'Nguyen An');

INSERT INTO lab_customers (customer_code, full_name)
VALUES ('C002', 'Tran Binh');

INSERT INTO lab_orders (customer_id, amount, status)
SELECT customer_id, 150000, 'NEW'
FROM lab_customers
WHERE customer_code = 'C001';

COMMIT;
```

The two tables have a **parent–child** relationship:

```text
LAB_CUSTOMERS                              LAB_ORDERS
  CUSTOMER_ID (PK)  <------------------+   ORDER_ID (PK)
  CUSTOMER_CODE (UNIQUE)               +-- CUSTOMER_ID (FK)
  FULL_NAME                                 AMOUNT (CHECK >= 0)
  CREATED_AT                                STATUS (CHECK value set)
                                            CREATED_AT

Dedicated index: IX_LAB_ORDERS_CUSTOMER_CREATED
                 (CUSTOMER_ID, CREATED_AT)
```

The lookup queries below assume you are logged into **the exact schema that created both tables**, or adjusted to `ALL_*` with an `OWNER` filter if logged in under another account.

## 4. Querying table lists and storage attributes

### 4.1. Listing tables in the schema

```sql
SELECT
    table_name,
    tablespace_name,
    temporary,
    partitioned,
    iot_type
FROM user_tables
WHERE table_name LIKE 'LAB_%'
ORDER BY table_name;
```

Explanation:

| Metadata column | How to read it |
| --- | --- |
| `TABLE_NAME` | Name of the table owned by the current user |
| `TABLESPACE_NAME` | Tablespace assigned to the table's storage, when applicable for that table type |
| `TEMPORARY` | Whether the table is a temporary table per metadata |
| `PARTITIONED` | Whether the table is partitioned |
| `IOT_TYPE` | Distinguishes index-organized table variants and related structures; regular heap tables typically show `NULL` |

A table can reside in a different tablespace from its indexes. `TABLESPACE_NAME` is not a datafile path; it is the name of a **logical** storage structure. For partitioned tables, IOTs, or specialized objects, storage details may require querying specialized views rather than inferring from a single row in `USER_TABLES`.

### 4.2. Finding tables in another schema

```sql
SELECT
    owner,
    table_name,
    tablespace_name,
    temporary
FROM all_tables
WHERE owner = 'SALES_APP'
  AND table_name LIKE 'ORD%'
ORDER BY table_name;
```

Replace `SALES_APP` with the **actual owner** visible to your account. Do not substitute a PDB name: `OWNER` indicates the schema, whereas PDB location is a connection context. When viewing all tables administratively, a DBA can use `DBA_TABLES`; for cross-container administration, use `CDB_TABLES` and check `CON_ID`.

### 4.3. Distinguishing tables from views

`USER_TABLES` queries tables, not every table-like object. Combine with:

```sql
SELECT object_name, object_type, status, created, last_ddl_time
FROM user_objects
WHERE object_name LIKE 'LAB_%'
ORDER BY object_type, object_name;

SELECT view_name
FROM user_views
WHERE view_name LIKE 'LAB_%'
ORDER BY view_name;
```

`USER_OBJECTS` can include `TABLE`, `VIEW`, `INDEX`, `SEQUENCE`, `TRIGGER`, and other objects. `LAST_DDL_TIME` reflects DDL/metadata changes to the object; it is **not** the timestamp of the last `INSERT` or `UPDATE` on row data.

When analyzing a materialized view, external table, or partitioned table, identify its exact object type and inspect dedicated views rather than assuming it behaves like an ordinary heap table.

## 5. Querying column structure

### 5.1. Retrieving the column list in exact order

```sql
SELECT
    table_name,
    column_id,
    column_name,
    data_type,
    data_length,
    data_precision,
    data_scale,
    char_used,
    char_length,
    nullable
FROM user_tab_columns
WHERE table_name IN ('LAB_CUSTOMERS', 'LAB_ORDERS')
ORDER BY table_name, column_id;
```

| Metadata | Meaning |
| --- | --- |
| `COLUMN_ID` | Display/definition position of the column in standard order |
| `COLUMN_NAME` | Column name |
| `DATA_TYPE` | Oracle data type, e.g., `NUMBER`, `VARCHAR2`, `TIMESTAMP(6)` |
| `DATA_LENGTH` | Maximum length in **bytes** for the column type (not visible character count) |
| `DATA_PRECISION`, `DATA_SCALE` | Precision and scale for declared numeric types, e.g., `NUMBER(12,2)` |
| `CHAR_USED` | `B` for byte semantics, `C` for character semantics on applicable character types |
| `CHAR_LENGTH` | Declared length in characters, where applicable |
| `NULLABLE` | Whether the column permits NULL per metadata (`Y`/`N`) |

With `VARCHAR2(20 CHAR)`, Oracle permits up to 20 **characters** in the character set, though actual byte storage depends on the character set and type byte limits. Do not rely solely on `DATA_LENGTH` to claim "this column only holds 20 characters." For `NUMBER` without explicit precision/scale, those fields may be `NULL`; that does not make the column a string.

### 5.2. Viewing columns of a table in another schema

```sql
SELECT
    owner,
    table_name,
    column_id,
    column_name,
    data_type,
    nullable
FROM all_tab_columns
WHERE owner = 'SALES_APP'
  AND table_name = 'ORDERS'
ORDER BY column_id;
```

When joining `ALL_*` dictionary views, generally join on both **`OWNER` and `TABLE_NAME`**, because two schemas can contain tables with the same name. Joining only on `TABLE_NAME` risks mixing columns from another schema.

### 5.3. Hidden, invisible, virtual, identity, and default columns

`USER_TAB_COLUMNS` normally filters out system-generated and hidden columns under Oracle rules. When deeper inspection is needed, you can query `USER_TAB_COLS`:

```sql
SELECT
    table_name,
    column_name,
    column_id,
    hidden_column,
    virtual_column,
    identity_column
FROM user_tab_cols
WHERE table_name = 'LAB_ORDERS'
ORDER BY column_id NULLS LAST, column_name;
```

Release notes:

- **Hidden/system-generated columns** may be created by Oracle to support internal features; never treat them as business columns for applications to modify directly.
- **Invisible columns** involve visibility in SQL constructs such as `SELECT *`; check column properties and how your release's dictionary views represent them rather than inferring solely from `COLUMN_ID`.
- **Virtual columns** are computed from expressions rather than stored like ordinary base columns.
- **Identity columns** use an Oracle-managed value generation mechanism; you can also query `USER_TAB_IDENTITY_COLS` to inspect identity properties where supported.
- **Default expressions** can appear in `DATA_DEFAULT`, though in some dictionary views that column has type **LONG**. Do not assume string functions like `SUBSTR(DATA_DEFAULT,...)` are allowed in SQL. Some releases provide `DATA_DEFAULT_VC` with a length limit; for long expressions or exact DDL, use `DBMS_METADATA`.

Example checking identity metadata in the schema:

```sql
SELECT table_name, column_name, generation_type
FROM user_tab_identity_cols
WHERE table_name IN ('LAB_CUSTOMERS', 'LAB_ORDERS')
ORDER BY table_name, column_name;
```

View/column names and output may vary by release; this lab targets Oracle versions with standard identity column and multitenant support.

## 6. Querying constraints: Primary Key, Unique, Foreign Key, and Check

Two key views:

- **`USER_CONSTRAINTS`**: one row per constraint, including name, table, type, status, condition, or referenced constraint.
- **`USER_CONS_COLUMNS`**: columns participating in each constraint and their positions.

### 6.1. `CONSTRAINT_TYPE` codes

| Code | Constraint type | Role |
| --- | --- | --- |
| **`P`** | Primary key | Identifies rows; components cannot be NULL and must be unique |
| **`U`** | Unique | Enforces uniqueness under Oracle semantics, noting how NULLs are handled |
| **`R`** | Referential integrity / foreign key | Enforces relationship to a referenced key |
| **`C`** | Check constraint | Enforces a condition expression; `IS NOT NULL` rules also commonly appear as `C` |
| **`V` / `O`** | Specialized view-related constraints | Seen with `WITH CHECK OPTION` / `WITH READ ONLY` per release documentation |

Do not look only for `P` to judge a table's validity. A table can have multiple `U`, `R`, `C` constraints as well as system-named constraints like `SYS_C...`.

### 6.2. Viewing all constraints on a table

```sql
SELECT
    table_name,
    constraint_name,
    constraint_type,
    status,
    validated,
    deferrable,
    deferred,
    delete_rule
FROM user_constraints
WHERE table_name IN ('LAB_CUSTOMERS', 'LAB_ORDERS')
ORDER BY table_name, constraint_type, constraint_name;
```

Key columns explained:

| Field | Interpretation |
| --- | --- |
| `STATUS` | `ENABLED` or `DISABLED` per constraint state |
| `VALIDATED` | `VALIDATED` or `NOT VALIDATED`, indicating whether existing data has been verified against the constraint |
| `DEFERRABLE` | Whether checking can be deferred until transaction commit |
| `DEFERRED` | Initial checking mode: immediate or deferred per metadata |
| `DELETE_RULE` | Behavior when deleting a parent row of a foreign key, e.g., `NO ACTION`, `CASCADE`, `SET NULL` as configured |

An **`ENABLED NOVALIDATE`** constraint carries a different guarantee from **`ENABLED VALIDATE`** regarding existing data. Do not read `STATUS = ENABLED` alone and assume all historical data has been validated.

### 6.3. Viewing columns participating in constraints

```sql
SELECT
    c.table_name,
    c.constraint_name,
    c.constraint_type,
    cc.position,
    cc.column_name,
    c.status
FROM user_constraints c
LEFT JOIN user_cons_columns cc
    ON cc.constraint_name = c.constraint_name
   AND cc.table_name = c.table_name
WHERE c.table_name IN ('LAB_CUSTOMERS', 'LAB_ORDERS')
ORDER BY c.table_name, c.constraint_name, cc.position;
```

`POSITION` is especially important for multi-column primary, unique, or foreign keys. A composite key `(A, B)` is not equivalent in ordering to `(B, A)` in many lookups and index designs. For complex `CHECK` constraints, the listed columns identify involvement but do not replace reading the **check expression**.

### 6.4. Reading CHECK and NOT NULL conditions

```sql
SELECT
    constraint_name,
    table_name,
    status,
    search_condition_vc
FROM user_constraints
WHERE table_name = 'LAB_ORDERS'
  AND constraint_type = 'C'
ORDER BY constraint_name;
```

Expected conditions include `AMOUNT >= 0`, `STATUS IN (...)`, and the `IS NOT NULL` conditions recorded by Oracle for required columns. In Oracle, a `CHECK` condition passes when the expression evaluates to **UNKNOWN** due to NULL; to reject NULL, you need `NOT NULL` or an explicit check expression. For example, `CHECK (AMOUNT >= 0)` **alone** does not replace `AMOUNT NOT NULL`.

`SEARCH_CONDITION` is typically type `LONG`, while `SEARCH_CONDITION_VC` is a character representation with a **length limit** (which can truncate long expressions); therefore, when exact DDL reconstruction is needed, use `DBMS_METADATA.GET_DDL`. If your release lacks `SEARCH_CONDITION_VC`, consult the view documentation and metadata retrieval method for that release.

### 6.5. Tracing from a foreign key to the parent table and referenced column

A foreign key stores **`R_CONSTRAINT_NAME`**, which is the name of the **P/U constraint on the parent table** being referenced, not the parent table's name. Join to the parent constraint:

```sql
SELECT
    f.constraint_name   AS foreign_key_name,
    f.table_name        AS child_table,
    child_col.position  AS column_position,
    child_col.column_name AS child_column,
    parent.owner        AS parent_owner,
    parent.table_name   AS parent_table,
    parent_col.column_name AS parent_column
FROM user_constraints f
JOIN user_cons_columns child_col
  ON child_col.constraint_name = f.constraint_name
 AND child_col.table_name      = f.table_name
JOIN all_constraints parent
  ON parent.owner           = f.r_owner
 AND parent.constraint_name = f.r_constraint_name
JOIN all_cons_columns parent_col
  ON parent_col.owner           = parent.owner
 AND parent_col.constraint_name = parent.constraint_name
 AND parent_col.position        = child_col.position
WHERE f.constraint_type = 'R'
  AND f.table_name = 'LAB_ORDERS'
ORDER BY f.constraint_name, child_col.position;
```

In the lab, the logical result shows:

```text
FK_LAB_ORDERS_CUSTOMER:
  LAB_ORDERS.CUSTOMER_ID
     -> LAB_CUSTOMERS.CUSTOMER_ID
```

**Why must you join on both owner and constraint name?** Constraint names are not globally unique across all schemas. Furthermore, a foreign key can reference a table in **another schema** when appropriate privileges exist. For multi-column keys, you must join by `POSITION` so key components are not mismatched.

If the user lacks privilege to read the parent's metadata via `ALL_*`, rows may be missing; that is a visibility scope issue, not proof that the referential relationship does not exist.

## 7. Querying indexes: definitions, columns, expressions, and status

An **index** gives Oracle an additional access path to data; having an index does not guarantee the optimizer will use it in every query. Read **definition**, **status**, and **statistics** together before drawing performance conclusions.

Core views:

| View | What to inspect |
| --- | --- |
| `USER_INDEXES` | Name, table, index type, uniqueness, visibility, status |
| `USER_IND_COLUMNS` | List of indexed columns and their positional order |
| `USER_IND_EXPRESSIONS` | Expressions for function-based indexes |
| `USER_IND_STATISTICS` | Index statistics used by the optimizer |
| `USER_IND_PARTITIONS` / `USER_IND_SUBPARTITIONS` | Partitioned index metadata, if applicable |

### 7.1. Listing indexes on a table

```sql
SELECT
    table_name,
    index_name,
    index_type,
    uniqueness,
    visibility,
    status,
    tablespace_name
FROM user_indexes
WHERE table_name IN ('LAB_CUSTOMERS', 'LAB_ORDERS')
ORDER BY table_name, index_name;
```

For the lab, you will typically see indexes supporting primary keys `PK_LAB_CUSTOMERS` and `PK_LAB_ORDERS`, unique constraint `UK_LAB_CUSTOMERS_CODE`, and the explicitly created index `IX_LAB_ORDERS_CUSTOMER_CREATED`. Actual index names and how Oracle creates or reuses indexes for constraints depend on existing indexes and the exact DDL.

Reading the columns:

- **`INDEX_TYPE`:** e.g., `NORMAL` (standard B-tree), `BITMAP`, or other types depending on object and release.
- **`UNIQUENESS`:** `UNIQUE` or `NONUNIQUE` at the index level; **not** a complete list of all unique constraints on the table.
- **`VISIBILITY`:** whether the index is `VISIBLE` or `INVISIBLE` to the normal optimizer; invisible indexes may still require maintenance during DML depending on configuration.
- **`STATUS`:** index status; for partitioned indexes, also inspect partition/subpartition status, because the table-level index row alone may not reflect every partition.
- **`TABLESPACE_NAME`:** where the index storage is allocated, which does not have to match the table's tablespace.

### 7.2. Column order in an index

```sql
SELECT
    i.table_name,
    i.index_name,
    i.uniqueness,
    ic.column_position,
    ic.column_name,
    ic.descend
FROM user_indexes i
JOIN user_ind_columns ic
  ON ic.index_name = i.index_name
 AND ic.table_name = i.table_name
WHERE i.table_name = 'LAB_ORDERS'
ORDER BY i.index_name, ic.column_position;
```

For `IX_LAB_ORDERS_CUSTOMER_CREATED`, the declared order is:

```text
1. CUSTOMER_ID
2. CREATED_AT
```

This order matters when analyzing the leading prefix of a composite B-tree index, filtering with `WHERE CUSTOMER_ID = :id`, and sorting/filtering by `CREATED_AT`. However, whether the index is chosen also depends on selectivity, statistics, data size, cost model, and the specific SQL statement.

### 7.3. Function-based indexes

Suppose an expression-based index exists:

```sql
CREATE INDEX ix_lab_customers_upper_name
ON lab_customers (UPPER(full_name));
```

Some dictionary views may display a **system-generated hidden column name** instead of the original expression. In that case, query:

```sql
SELECT
    index_name,
    column_position,
    column_expression
FROM user_ind_expressions
WHERE table_name = 'LAB_CUSTOMERS'
ORDER BY index_name, column_position;
```

`COLUMN_EXPRESSION` may be of type `LONG` depending on release, so avoid assuming all string functions work directly on it. Function-based indexes also carry requirements around expression determinism, privileges, status, and execution environment; their existence alone does not prove every `UPPER(FULL_NAME)` query will use the index.

### 7.4. Are unique constraints and unique indexes the same?

**Not entirely.**

- A **unique/primary-key constraint** defines a data integrity rule and how Oracle validates it.
- A **unique index** is a storage/access structure enforcing uniqueness of the index key under its own semantics.
- Oracle commonly uses an **index** to enforce primary/unique constraints, and may **reuse an existing index** when suitable. A constraint can also be enforced by a **nonunique index** in supported cases, such as when a deferrable constraint is required.
- Conversely, creating an index with `UNIQUENESS = UNIQUE` does not automatically add a corresponding row in `USER_CONSTRAINTS`.

To link P/U constraints to their supporting indexes:

```sql
SELECT
    table_name,
    constraint_name,
    constraint_type,
    index_name,
    status,
    validated
FROM user_constraints
WHERE table_name IN ('LAB_CUSTOMERS', 'LAB_ORDERS')
  AND constraint_type IN ('P', 'U')
ORDER BY table_name, constraint_name;
```

A **foreign key** does not automatically get an Oracle-created index on the child column. The lab's `IX_LAB_ORDERS_CUSTOMER_CREATED` index was created manually; whether an FK needs an index depends on join frequency, parent row updates/deletes, concurrency, and query plans.

## 8. Optimizer statistics: read them accurately, never treat them as real-time data

Oracle's **cost-based optimizer (CBO)** uses statistics about tables, columns, indexes, and the system to estimate cardinality/cost and pick execution plans. Statistics are not an exact, continuously updated mirror of every table.

### 8.1. Table-level statistics

```sql
SELECT
    table_name,
    object_type,
    num_rows,
    blocks,
    avg_row_len,
    sample_size,
    last_analyzed,
    stale_stats
FROM user_tab_statistics
WHERE table_name IN ('LAB_CUSTOMERS', 'LAB_ORDERS')
  AND object_type = 'TABLE'
ORDER BY table_name;
```

| Field | Interpretation |
| --- | --- |
| `NUM_ROWS` | Row count per **optimizer statistics** at collection time; not a live `COUNT(*)` |
| `BLOCKS` | Number of blocks used by table data per Oracle statistics/calculation |
| `AVG_ROW_LEN` | Average row length per statistics, typically in bytes |
| `SAMPLE_SIZE` | Sample size used for estimation, when applicable |
| `LAST_ANALYZED` | Timestamp when statistics were gathered/updated |
| `STALE_STATS` | Flag indicating statistics may be stale under Oracle's tracking; not an absolute verification of plan quality |
| `OBJECT_TYPE` | TABLE/PARTITION/SUBPARTITION level depending on table structure |

If a table was just created or statistics have not been gathered yet, `NUM_ROWS`/`LAST_ANALYZED` may be `NULL`. For partitioned tables, inspect partition/subpartition statistics as well as global statistics, not only a single table-level row.

To see the difference between live data and metadata:

```sql
-- Actual row count at query time under Oracle read consistency.
SELECT COUNT(*) AS actual_rows
FROM lab_orders;

-- Most recent statistics values (if gathered).
SELECT num_rows, last_analyzed, stale_stats
FROM user_tab_statistics
WHERE table_name = 'LAB_ORDERS'
  AND object_type = 'TABLE';
```

These two numbers **can differ** even with zero data errors. `COUNT(*)` reads data according to an execution plan and snapshot; `NUM_ROWS` simply reads stored statistics. If the application inserts 1,000,000 rows after statistics were collected, `NUM_ROWS` may not reflect those rows yet.

### 8.2. Column-level statistics

```sql
SELECT
    table_name,
    column_name,
    num_distinct,
    num_nulls,
    density,
    histogram,
    num_buckets,
    avg_col_len,
    last_analyzed
FROM user_tab_col_statistics
WHERE table_name = 'LAB_ORDERS'
ORDER BY column_name;
```

- **`NUM_DISTINCT`:** number of distinct values recorded/estimated by the optimizer.
- **`NUM_NULLS`:** count of NULLs per statistics, not a live query-time count.
- **`DENSITY`:** metric used in selectivity estimation; interpretation depends on histograms and release algorithms.
- **`HISTOGRAM`, `NUM_BUCKETS`:** value distribution details when Oracle collects a histogram, helpful for heavily skewed data.
- **`AVG_COL_LEN`:** average column value length per statistics.

For example, suppose `STATUS` has 99% `PAID` and 1% `CANCELLED`. Assuming uniform distribution to estimate rows for both filters would be inaccurate. Histograms **can** help the optimizer estimate more accurately, though creating histograms on every column is not a default best practice: it depends on workload, skew, bind variables, and release-specific Oracle behavior.

### 8.3. Index-level statistics

```sql
SELECT
    index_name,
    blevel,
    leaf_blocks,
    distinct_keys,
    clustering_factor,
    last_analyzed
FROM user_ind_statistics
WHERE index_name IN (
    'IX_LAB_ORDERS_CUSTOMER_CREATED',
    'IX_LAB_CUSTOMERS_UPPER_NAME'
)
ORDER BY index_name;
```

| Metadata | General meaning |
| --- | --- |
| `BLEVEL` | Number of branch levels between root and leaf in the B-tree per statistics |
| `LEAF_BLOCKS` | Number of leaf blocks per statistics |
| `DISTINCT_KEYS` | Number of distinct index key values per statistics |
| `CLUSTERING_FACTOR` | Correlation between index entry order and table row physical order; important when estimating table-access I/O via index |
| `LAST_ANALYZED` | Timestamp when index statistics were collected/updated |

**Clustering factor is not a fragmentation percentage.** It is an optimizer input estimating the cost of fetching table rows in index order. A high value does not prove "the index is corrupted"; physical row ordering and access patterns can naturally make table reads expensive.

### 8.4. Gathering statistics again in the lab

On the two tables **you created yourself**, you can use the `DBMS_STATS` package:

```sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname          => USER,
        tabname          => 'LAB_CUSTOMERS',
        estimate_percent => DBMS_STATS.AUTO_SAMPLE_SIZE,
        method_opt       => 'FOR ALL COLUMNS SIZE AUTO',
        cascade          => TRUE
    );

    DBMS_STATS.GATHER_TABLE_STATS(
        ownname          => USER,
        tabname          => 'LAB_ORDERS',
        estimate_percent => DBMS_STATS.AUTO_SAMPLE_SIZE,
        method_opt       => 'FOR ALL COLUMNS SIZE AUTO',
        cascade          => TRUE
    );
END;
/
```

`cascade => TRUE` instructs Oracle to gather statistics on associated indexes as supported by the package. Automated stats jobs, incremental statistics, histograms, statistics locking, and real-time statistics (when available) make real-world administration richer than this example.

**Never re-gather production statistics arbitrarily.** Updating statistics can cause the optimizer to pick different execution plans, changing performance. On live systems, schedule, method, privileges, and governance policies must be defined; this lesson only runs `DBMS_STATS` on lab tables you created yourself.

### 8.5. Metadata differs from an execution plan

Knowing a table has an index and fresh statistics does not prove a SQL statement will use that index. To inspect the estimated plan for a specific SQL query, you can run in a practice environment:

```sql
EXPLAIN PLAN FOR
SELECT order_id, amount
FROM lab_orders
WHERE customer_id = 1
ORDER BY created_at DESC;

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
```

`EXPLAIN PLAN` shows the **estimated plan**, which may differ from the actual runtime cursor plan with bind peeking and runtime conditions. For real performance analysis, a DBA may need `DBMS_XPLAN.DISPLAY_CURSOR` with runtime statistics and appropriate privileges. Do not declare an index "unused" based solely on one `EXPLAIN PLAN` against a tiny lab table with a handful of rows.

## 9. Consolidated workflow for quickly surveying an unknown table

When encountering an unfamiliar table, proceed in this order.

### Step 1 — Confirm table and owner

```sql
SELECT owner, table_name, tablespace_name, partitioned
FROM all_tables
WHERE table_name = 'ORDERS'
ORDER BY owner;
```

If multiple rows return, pick the right owner and PDB. For names created with double quotes, match the exact dictionary spelling.

### Step 2 — Retrieve columns

```sql
SELECT owner, column_id, column_name, data_type,
       data_length, data_precision, data_scale, nullable
FROM all_tab_columns
WHERE owner = 'SALES_APP'
  AND table_name = 'ORDERS'
ORDER BY column_id;
```

### Step 3 — Retrieve constraints and their columns

```sql
SELECT
    c.owner,
    c.constraint_name,
    c.constraint_type,
    cc.position,
    cc.column_name,
    c.status,
    c.validated
FROM all_constraints c
LEFT JOIN all_cons_columns cc
  ON cc.owner           = c.owner
 AND cc.constraint_name = c.constraint_name
 AND cc.table_name      = c.table_name
WHERE c.owner = 'SALES_APP'
  AND c.table_name = 'ORDERS'
ORDER BY c.constraint_name, cc.position;
```

### Step 4 — Retrieve indexes and column order

```sql
SELECT
    i.owner,
    i.index_name,
    i.uniqueness,
    i.status,
    ic.column_position,
    ic.column_name
FROM all_indexes i
LEFT JOIN all_ind_columns ic
  ON ic.index_owner = i.owner
 AND ic.index_name  = i.index_name
 AND ic.table_owner = i.table_owner
 AND ic.table_name  = i.table_name
WHERE i.table_owner = 'SALES_APP'
  AND i.table_name = 'ORDERS'
ORDER BY i.index_name, ic.column_position;
```

In `ALL_IND_*` views, the **index owner** can differ from the **table owner** in specialized configurations; use the matching owner join keys and never assume `INDEX_NAME` alone suffices.

### Step 5 — Check statistics timestamp and values

```sql
SELECT
    owner,
    table_name,
    num_rows,
    blocks,
    avg_row_len,
    last_analyzed,
    stale_stats
FROM all_tab_statistics
WHERE owner = 'SALES_APP'
  AND table_name = 'ORDERS'
  AND object_type = 'TABLE';
```

If you lack privileges to view certain details, stop at what is legitimately visible or ask a DBA to run a **read-only** administrative query. Do not use an over-privileged account capable of modifying schemas just to inspect metadata.

## 10. Extracting DDL to read the full structure

Dictionary views are well-suited for **filtering, joining, and analyzing**; when you need the relatively complete DDL of an object, you can use the `DBMS_METADATA` package:

```sql
-- Inside the schema owning the lab table.
SELECT DBMS_METADATA.GET_DDL('TABLE', 'LAB_ORDERS', USER)
FROM dual;

SELECT DBMS_METADATA.GET_DDL('INDEX',
                            'IX_LAB_ORDERS_CUSTOMER_CREATED',
                            USER)
FROM dual;
```

Some SQL clients truncate CLOB output by default; enable full CLOB display or export the result properly. When extracting DDL for an object in another schema, privileges and metadata policies may restrict output.

Generated DDL can contain **storage clauses**, identity definitions, constraints, tablespaces, optional parameters, and release-specific features. Never copy raw generated DDL into another database expecting it to run unchanged: review tablespaces, privileges, edition features, and actual dependencies. `DBMS_METADATA` offers transform handles to customize DDL output formatting within a session when exporting structure.

### When to query views vs. when to extract DDL?

| Goal | Appropriate approach |
| --- | --- |
| Find all tables matching a prefix and owner | `ALL_TABLES` / `USER_TABLES` |
| Find columns of a specific data type or length | `ALL_TAB_COLUMNS` |
| Map PK/FK relationships across tables | `ALL_CONSTRAINTS` + `ALL_CONS_COLUMNS` |
| Check which index leads with `CUSTOMER_ID` | `ALL_INDEXES` + `ALL_IND_COLUMNS` |
| Check row estimates and collection timestamps | `ALL_TAB_STATISTICS` |
| Read full object definition for review/migration | `DBMS_METADATA.GET_DDL` |
| Know whether an actual query runs fast | Execution plan + runtime measurements, never inferred from metadata alone |

## 11. Common pitfalls when querying metadata

| Symptom or wrong conclusion | Possible cause | How to handle |
| --- | --- | --- |
| `USER_TABLES` lacks `SALES_APP.ORDERS` | You are logged in as a different user | Use `ALL_TABLES` with `OWNER` or connect to the owning schema |
| `ALL_TABLES` returns multiple `ORDERS` tables | Multiple schemas have same-named tables | Filter by `OWNER` and verify the PDB |
| Table not found even though the app queries it | Uses a synonym, wrong PDB, missing privileges, or quoted identifier | Check `ALL_SYNONYMS`, `SYS_CONTEXT`, and exact spelling |
| `DATA_LENGTH = 80` assumed to always hold 80 characters | Confused byte vs. char semantics | Inspect `CHAR_USED`, `CHAR_LENGTH`, and data type |
| `USER_CONSTRAINTS` shows an unexpected `C` constraint | Oracle generates check constraints for `NOT NULL` | Read `SEARCH_CONDITION_VC` or DDL |
| Trying to find FK parent table by reading `R_CONSTRAINT_NAME` as a table name | It is the **referenced constraint name** | Join to `ALL_CONSTRAINTS` and `ALL_CONS_COLUMNS` |
| Foreign key exists without a matching index | Oracle does not automatically create FK indexes in all cases | Evaluate index need based on workload |
| Seeing `UNIQUE` in `USER_INDEXES` and assuming a unique constraint exists | Indexes and constraints are distinct object/metadata types | Also inspect `USER_CONSTRAINTS` |
| `NUM_ROWS` differs from `COUNT(*)` | Optimizer stats are point-in-time estimates | Check `LAST_ANALYZED`, `STALE_STATS`, and `DBMS_STATS` policies |
| `INDEX_STATUS = VALID` assumed to guarantee the query uses the index | Valid status does not force the optimizer to choose it | Inspect execution plan, statistics, and SQL predicates |
| Metadata is visible yet `SELECT` on table fails with insufficient privileges | Metadata visibility and operation privileges have separate scopes | Check grants, view scope, and exact target object |
| Querying `DBA_*` fails with insufficient privileges | Administrative views require privileges | Use `USER_*`/`ALL_*` when sufficient, or ask a DBA to run approved queries |
| Confusing hidden columns appear in metadata | Oracle features can generate hidden/virtual columns | Check `USER_TAB_COLS` and DDL; never edit system metadata |

### Synonyms do not create a copy of the table

Suppose the application schema has a synonym `ORDERS` pointing to `SALES_APP.ORDERS`. Query:

```sql
SELECT owner, synonym_name, table_owner, table_name, db_link
FROM all_synonyms
WHERE synonym_name = 'ORDERS'
ORDER BY owner;
```

A synonym is solely a **reference alias**, not a new table. To read columns, constraints, and indexes, follow through to the **actual owner/table**. If a synonym traverses a database link, metadata and privileges on the remote database are governed by remote link constraints; never assume local `ALL_TABLES` includes the remote object.

### Should you trust constraint names completely?

Names such as `PK_ORDERS`, `FK_ORDERS_CUSTOMER`, or `IX_ORDERS_CREATED` improve readability, yet they are **naming conventions** and do not guarantee constraint type or behavior. A constraint named `SYS_C005432` can still be a primary key or a critical `NOT NULL` rule. Always rely on `CONSTRAINT_TYPE`, joined column metadata, and actual conditions rather than guessing from prefixes.

## 12. Hands-on exercises

### Exercise 1 — Survey the lab tables

After creating the two tables in Section 3, write SQL to answer:

1. What is the current session's schema? Which PDB is connected?
2. How many tables starting with `LAB_` exist in `USER_TABLES`?
3. Which columns does each table have, ordered by `COLUMN_ID`?
4. What precision/scale does `AMOUNT` have, and does it allow NULL?
5. Is `CUSTOMER_CODE`'s length declared in **bytes** or **characters**?

**Explain your answers using metadata**, rather than merely taking screenshots of a SQL client's table grid.

### Exercise 2 — Map relationships from the dictionary

Use `USER_CONSTRAINTS` and `USER_CONS_COLUMNS` to find:

- Each table's primary key.
- The unique constraint on `CUSTOMER_CODE`.
- The foreign key from `LAB_ORDERS` to `LAB_CUSTOMERS` and the exact linked column names.
- The check constraints restricting `AMOUNT` and `STATUS`.
- The `C` constraints generated from `NOT NULL` requirements.

Then draw the relationship diagram relying solely on the **dictionary**, without looking back at the original `CREATE TABLE` script. This simulates inheriting a schema without DDL scripts.

### Exercise 3 — Distinguish constraints from indexes

1. Query `USER_INDEXES` for `LAB_ORDERS`.
2. Use `USER_IND_COLUMNS` to record column order in each index.
3. Inspect `USER_CONSTRAINTS.INDEX_NAME` for primary and unique keys.
4. Identify which `CREATE INDEX` statement produced `IX_LAB_ORDERS_CUSTOMER_CREATED`.
5. Discuss why having a foreign key on `CUSTOMER_ID` does not mean Oracle automatically creates an index named `FK_LAB_ORDERS_CUSTOMER`.

### Exercise 4 — Compare statistics with actual row counts

On your own lab table:

```sql
SELECT COUNT(*) AS actual_rows FROM lab_orders;

SELECT num_rows, last_analyzed, stale_stats
FROM user_tab_statistics
WHERE table_name = 'LAB_ORDERS'
  AND object_type = 'TABLE';
```

Record both values, gather statistics using `DBMS_STATS` from Section 8.4, and re-query. If numbers still differ or statistics do not update as expected, explain why in terms of sampling, version, and collection state rather than assuming a database bug.

### Exercise 5 — Simulate a schema handover scenario

You are tasked with accessing `SALES_APP`, yet your login account is `REPORT_APP`. Build a read-only query checklist to verify:

1. Are database, PDB, `SESSION_USER`, and `CURRENT_SCHEMA` as expected?
2. Does schema `SALES_APP` have an `ORDERS` table visible to your current account?
3. What columns and constraints does the table have?
4. Which index supports filtering on `CUSTOMER_ID` and sorting on `CREATED_AT`?
5. Were table statistics gathered recently?

If `ALL_*` does not return the needed object, document the **missing privilege scope** and the appropriate privileges to request from the DBA; never use `SYS` to bypass authorization.

### Clean up lab data

Only drop tables **you created yourself for this lesson**, inside the designated practice schema:

```sql
DROP TABLE lab_orders PURGE;
DROP TABLE lab_customers PURGE;
```

`PURGE` bypasses the recycle bin for the dropped tables; never use it on data you might need to recover. Indexes and constraints belonging to the dropped tables are handled under Oracle DDL rules. If you created additional indexes or function-based indexes in the lab, they are attached to the table and removed when the table is dropped per Oracle behavior.

## 13. A daily workflow for reading schemas

When opening an unfamiliar database, a practical sequence is:

```text
1. Verify CDB/PDB, SESSION_USER, CURRENT_SCHEMA
                         |
                         v
2. Find TABLE and OWNER in USER_/ALL_TABLES
                         |
                         v
3. Read COLUMN_NAME, DATA_TYPE, NULLABLE in *_TAB_COLUMNS
                         |
                         v
4. Read PK, UQ, FK, CHECK in *_CONSTRAINTS
   + *_CONS_COLUMNS
                         |
                         v
5. Read INDEX_TYPE, COLUMNS, STATUS in
   *_INDEXES + *_IND_COLUMNS / *_IND_EXPRESSIONS
                         |
                         v
6. Read NUM_ROWS, NUM_DISTINCT, HISTOGRAM,
   LAST_ANALYZED in *_TAB/IND_STATISTICS
                         |
                         v
7. Use DBMS_METADATA to inspect full DDL if needed
                         |
                         v
8. Only when analyzing specific SQL:
   measure execution plans and runtime I/O/cardinality
```

This workflow keeps three questions separate: **how structure is declared**, **what the optimizer knows about the data**, and **how queries actually run**. All three answers are related, yet none replaces the others.

## Recommended Oracle Documentation

- [Oracle Database Reference – Data Dictionary](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/) — explains and lists dictionary views per release.
- [Oracle Database Concepts](https://docs.oracle.com/en/database/oracle/oracle-database/19/cncpt/) — schemas, tables, indexes, data dictionary, and statistics in Oracle architecture.
- [Oracle Database SQL Language Reference](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/) — syntax for `CREATE TABLE`, `CREATE INDEX`, constraints, identifiers, and data types.
- [Oracle Database PL/SQL Packages and Types Reference – DBMS_STATS](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_STATS.html) — gathering, inspecting, and managing optimizer statistics.
- [Oracle Database PL/SQL Packages and Types Reference – DBMS_METADATA](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_METADATA.html) — extracting object DDL and metadata.

Column names and visibility for some views can vary by release, edition, object type, and access privileges. When surveying a concrete system, always cross-check documentation matching the installed Oracle version.
