# PRIMARY KEY, UNIQUE, and Their Relationship with Indexes in Oracle Database

When building a relational table in **Oracle Database**, defining what makes a record unique is foundational to data integrity. The two most commonly used constraints are **`PRIMARY KEY`** and **`UNIQUE`**. Oracle typically uses an **index** to enforce them, yet these three concepts are not synonymous: a *constraint* expresses a data rule that must hold, whereas an *index* is a data-access structure that can serve both constraint enforcement and query optimization.

Imagine a sales system:

- Every customer must have a defined `CUSTOMER_ID` that cannot be duplicated or left empty.
- Each customer's `USERNAME` may need to be unique because it is used for login.
- `EMAIL` may not be provided yet, but once provided, it must not duplicate another customer's email under application rules.
- Every order must have a unique order code and reference a valid customer.

`PRIMARY KEY`, `UNIQUE`, indexes, and foreign keys work together to satisfy these requirements. This lesson covers declaration syntax, `NULL` behavior, composite keys, indexes created or reused by Oracle, special cases such as **deferrable constraints**, reading metadata, and common operational pitfalls.

## 1. Distinguishing Primary Keys, Unique Constraints, and Indexes

| Component | Nature | Guarantee or Purpose | Automatically Forbids `NULL`? | How Many Per Table? |
|---|---|---|---|---|
| **`PRIMARY KEY` constraint** | Integrity rule | Every row has a unique and complete identifying key | **Yes**, every column in the primary key must be `NOT NULL` | At most **one** primary key; that key may consist of multiple columns |
| **`UNIQUE` constraint** | Integrity rule | Prevents duplicate key combinations according to Oracle's rules | **No**, unless the column also has `NOT NULL` | Can have **multiple** unique constraints |
| **Unique index** | Access structure and uniqueness check at index-key level | Disallows duplicate index keys under unique-index semantics | Does not automatically make source columns `NOT NULL` | Can have multiple indexes, subject to limits and design |
| **Nonunique index** | Access structure | Speeds up lookups/joins/sorts, or can be used by Oracle to enforce a suitable constraint | No | Can have multiple indexes |

Key takeaways:

1. **A primary key is a constraint**, not another name for a unique index.
2. **A unique constraint is a constraint** that can be backed by an index; that backing index does not necessarily have the `UNIQUE` attribute.
3. **A unique index can independently block certain duplicate values** even without a corresponding constraint, but it does not fully replace the semantics, metadata, and referenceability of a `PRIMARY KEY` or `UNIQUE` constraint.
4. **A foreign key references a primary key or unique constraint declared on the parent table**; merely creating a unique index on columns in the parent table does not automatically turn them into a key that a foreign key can reference.

```text
                        TABLE CUSTOMERS
                     +--------------------+
                     | CUSTOMER_ID        |---- PRIMARY KEY constraint
                     | USERNAME           |---- UNIQUE constraint
                     | EMAIL              |---- UNIQUE constraint
                     +--------------------+
                             |
                      Oracle chooses/creates
                      supporting index
                             v
                  INDEX (commonly B-tree)
                  - index key lookup
                  - supports duplicate checking
                  - usable by the optimizer

               Constraint != index object
```

## 2. PRIMARY KEY: Identifying Each Row with a Valid Key

The **`PRIMARY KEY`** constraint requires the key value to be **unique** and **non-`NULL`**. A table can have only one primary key constraint, though the key may be a **single-column key** or a **composite key** (multiple columns).

### 2.1. Declaring a Single-Column Primary Key

```sql
-- Run in an Oracle DEV/TEST practice schema with CREATE TABLE privileges.
CREATE TABLE lab_customers (
    customer_id NUMBER NOT NULL,
    username    VARCHAR2(50 CHAR) NOT NULL,
    email       VARCHAR2(200 CHAR),
    full_name   VARCHAR2(100 CHAR),
    CONSTRAINT pk_lab_customers PRIMARY KEY (customer_id),
    CONSTRAINT uq_lab_customers_username UNIQUE (username),
    CONSTRAINT uq_lab_customers_email UNIQUE (email)
);
```

Here:

- `PK_LAB_CUSTOMERS` requires `CUSTOMER_ID` to have a non-null, non-duplicate value.
- `UQ_LAB_CUSTOMERS_USERNAME` forbids duplicate usernames; `USERNAME` is also declared `NOT NULL` because the business does not allow accounts without a username.
- `UQ_LAB_CUSTOMERS_EMAIL` prevents duplicate provided emails while still allowing undeclared emails via `NULL`.

Writing `CUSTOMER_ID NUMBER NOT NULL` alongside `PRIMARY KEY` makes the intent explicit for readers; the primary key constraint itself already enforces non-nullability. When an `INSERT` omits `CUSTOMER_ID`, Oracle rejects it rather than auto-generating a value unless you design an **identity column, sequence/default, or key-generation mechanism**.

### 2.2. Column-Level vs. Table-Level Primary Key Declarations

For a single column, inline syntax can be used:

```sql
CREATE TABLE lab_products (
    product_id   NUMBER CONSTRAINT pk_lab_products PRIMARY KEY,
    product_name VARCHAR2(100 CHAR) NOT NULL
);
```

For a composite key, use a table-level constraint:

```sql
CREATE TABLE lab_order_items (
    order_id   NUMBER NOT NULL,
    line_no    NUMBER NOT NULL,
    product_id NUMBER NOT NULL,
    quantity   NUMBER DEFAULT 1 NOT NULL,
    CONSTRAINT pk_lab_order_items PRIMARY KEY (order_id, line_no),
    CONSTRAINT ck_lab_order_items_quantity CHECK (quantity > 0)
);
```

The key of `LAB_ORDER_ITEMS` is the pair `(ORDER_ID, LINE_NO)`. The value `ORDER_ID = 100` may appear on multiple rows, and `LINE_NO = 1` may appear across multiple orders; only the **value pair** must be unique. Every component of a composite key must be non-`NULL`.

| `ORDER_ID` | `LINE_NO` | Can Coexist? | Explanation |
|---:|---:|---|---|
| 100 | 1 | Yes | First line of order 100 |
| 100 | 2 | Yes | Different key pair from the previous row |
| 101 | 1 | Yes | Different key pair because `ORDER_ID` differs |
| 100 | 1 | **No**, if the first pair exists | Violates duplicate primary key pair |
| 100 | `NULL` | **No** | Columns participating in primary key cannot be `NULL` |

### 2.3. How Many Primary Keys Can a Table Have?

A table has **only one** `PRIMARY KEY` constraint, even though it may have multiple **candidate keys** or multiple `UNIQUE` constraints. If a system identifies orders by `ORDER_ID` and simultaneously needs a unique business code `ORDER_CODE`, the standard design is:

```sql
CREATE TABLE lab_orders (
    order_id      NUMBER NOT NULL,
    order_code    VARCHAR2(40 CHAR) NOT NULL,
    customer_id   NUMBER NOT NULL,
    created_at    TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
    CONSTRAINT pk_lab_orders PRIMARY KEY (order_id),
    CONSTRAINT uq_lab_orders_code UNIQUE (order_code),
    CONSTRAINT fk_lab_orders_customer FOREIGN KEY (customer_id)
        REFERENCES lab_customers (customer_id)
);
```

`ORDER_ID` is the technical primary key; `ORDER_CODE` is protected by a unique constraint as a business key. You cannot declare a second `PRIMARY KEY (ORDER_CODE)` on the same table; use `UNIQUE (ORDER_CODE)` instead.

### 2.4. Primary Keys and Value Generation

`PRIMARY KEY` **does not mean auto-increment**. Oracle allows IDs to be supplied by the application, a sequence, an identity column, or other designed strategies. For example, on Oracle versions supporting identity columns:

```sql
CREATE TABLE lab_identity_example (
    id NUMBER GENERATED ALWAYS AS IDENTITY,
    description VARCHAR2(100 CHAR),
    CONSTRAINT pk_lab_identity_example PRIMARY KEY (id)
);
```

The identity column lets Oracle generate ID values; the primary key constraint is what prevents duplicates and nulls. With sequence-based key generation, **never assume IDs are contiguous without gaps**: sequences can skip numbers due to rollbacks, caching, or concurrent operations; applications should not use IDs to infer record counts.

## 3. UNIQUE: Protecting Candidate Keys and Business Uniqueness Rules

A **`UNIQUE` constraint** ensures that key values—or combinations of values across declared columns—do not duplicate under Oracle semantics. It fits employee codes, usernames, product codes, tenant-scoped invoice numbers, partner order references, or email addresses when the business requires uniqueness.

### 3.1. Single-Column and Multi-Column UNIQUE Constraints

Single-column unique example:

```sql
ALTER TABLE lab_customers
ADD CONSTRAINT uq_lab_customers_phone UNIQUE (phone_number);
```

The illustrative statement above **only works if the `PHONE_NUMBER` column already exists** in the table. If the column does not exist yet, add it first via a valid migration. In real schemas, check existing data and duplicates before adding the constraint. Declaring it at table creation time is usually simpler and easier to manage.

Composite unique example on a separate table:

```sql
CREATE TABLE lab_external_orders (
    id             NUMBER NOT NULL,
    partner_code   VARCHAR2(30 CHAR) NOT NULL,
    external_code  VARCHAR2(60 CHAR) NOT NULL,
    CONSTRAINT pk_lab_external_orders PRIMARY KEY (id),
    CONSTRAINT uq_lab_external_orders_partner
        UNIQUE (partner_code, external_code)
);
```

The code `external_code = 'A100'` can be used simultaneously by `PARTNER_X` and `PARTNER_Y`, but **a single partner cannot have two orders with the same code**. This is a classic composite unique constraint: uniqueness applies to the **combination**, not each column individually.

### 3.2. UNIQUE with `NULL` in Oracle: How It Differs from PRIMARY KEY

For a **single-column unique constraint** in Oracle, **multiple `NULL` rows** are permitted. For example, multiple customers who have not provided an email have `EMAIL = NULL`; `UNIQUE (EMAIL)` does not forbid that. Conversely, if two rows hold the same concrete email, Oracle rejects the duplicate row.

```sql
INSERT INTO lab_customers (customer_id, username, email)
VALUES (1, 'an', NULL);

INSERT INTO lab_customers (customer_id, username, email)
VALUES (2, 'binh', NULL);

INSERT INTO lab_customers (customer_id, username, email)
VALUES (3, 'chi', 'chi@example.test');

COMMIT;
```

These three rows are valid under the constraint. However, the following statement **will fail** because the email already exists:

```sql
-- Deliberate violation example; DO NOT put in normal migrations.
INSERT INTO lab_customers (customer_id, username, email)
VALUES (4, 'dung', 'chi@example.test');

-- Typically raises ORA-00001 (unique constraint violated).
```

In Oracle SQL, `NULL` represents an unknown/absent value; the `=` operator does not treat `NULL = NULL` as `TRUE`. To check for null, use `IS NULL`. For `VARCHAR2` character columns, current Oracle versions also treat an empty string `''` as `NULL`; this can affect email and username handling depending on `NOT NULL` declarations and application parameter binding. Do not design uniqueness checks assuming `''` is a distinct non-null string in Oracle.

### 3.3. Composite UNIQUE and `NULL` Values: Do Not Reason Like a Single Column

For a **composite unique key** in Oracle, if **all columns in the key are `NULL`**, multiple such rows are allowed. However, if **some components are non-null and others are `NULL`**, combinations sharing the same non-null values are treated as duplicates; Oracle's composite-key uniqueness semantics differ from the naive assumption that "having any NULL always allows duplicates."

```sql
CREATE TABLE lab_pair_unique (
    id NUMBER PRIMARY KEY,
    region_code VARCHAR2(10 CHAR),
    partner_ref VARCHAR2(30 CHAR),
    CONSTRAINT uq_lab_pair UNIQUE (region_code, partner_ref)
);
```

| `(REGION_CODE, PARTNER_REF)` Value | If an Identical Row Exists, Can a Second Be Added? | Explanation |
|---|---|---|
| `('VN', 'X001')` | No | Same combination of non-null values |
| `('VN', NULL)` | **No** under Oracle semantics for composite keys with matching non-null parts | The defined key portion matches |
| `(NULL, 'X001')` | **No** under Oracle semantics for composite keys with matching non-null parts | The defined key portion matches |
| `(NULL, NULL)` | Allowed | All key components are null |
| `('VN', 'X001')` and `('US', 'X001')` | Allowed | Different combinations |

If the business strictly allows only one row when both attributes are missing, or has custom rules for blank values, design additional constraints, business checks, or an alternate key; **do not assume a nullable `UNIQUE` handles all "unknown" cases uniformly**.

### 3.4. `UNIQUE` Does Not Replace `NOT NULL`

For example, if a username is mandatory, use:

```sql
username VARCHAR2(50 CHAR) NOT NULL,
CONSTRAINT uq_lab_customers_username UNIQUE (username)
```

With only `UNIQUE (USERNAME)` and no `NOT NULL`, accounts without usernames could still exist. For mandatory business keys, combining `UNIQUE` + `NOT NULL` expresses the requirement accurately—or consider making it the primary key if it truly serves as the table's primary identifier.

## 4. What Is an Index and Why Does Oracle Use Indexes to Enforce Keys?

An **index** is a storage structure that supports fast key lookup and efficient ROWID/record retrieval. In a standard B-tree index, Oracle organizes keys in search order. An index can serve both **queries** (avoiding full table scans when beneficial) and **uniqueness checks** when data changes occur.

```text
                CUSTOMER Data

   CUSTOMER_ID | USERNAME | EMAIL
   ------------+----------+---------------------
       10      | lan      | lan@example.test
       11      | minh     | minh@example.test
       12      | nhu      | NULL

   PK index on CUSTOMER_ID:
       [10] --> Lan's row
       [11] --> Minh's row
       [12] --> Nhu's row

   Unique index on USERNAME:
       ['lan']  --> Lan's row
       ['minh'] --> Minh's row
       ['nhu']  --> Nhu's row
```

When two rows with the same `USERNAME` are inserted into a table with an active `UNIQUE` constraint, Oracle must detect the collision and reject the invalid change. An index lets Oracle perform this check far more efficiently than scanning the entire table for every new row.

### 4.1. Oracle Usually Creates a Supporting Index Automatically for PK/UNIQUE

When creating an enforced primary key or unique constraint, Oracle needs a mechanism to check uniqueness. If **no suitable index exists yet**, Oracle typically **creates an index** to back the constraint—in standard cases, a **unique B-tree index**. If a suitable index already exists, Oracle can **reuse** it instead of creating a redundant index.

This leads to several practical realities:

- You do not need to run `CREATE UNIQUE INDEX` followed by `PRIMARY KEY` as a mandatory ritual on every table.
- Do not create a duplicate index over the exact same key columns when Oracle already maintains a backing index for the constraint, unless there is a measured and approved specific need.
- **Constraint names and index names can differ.** Do not rely on naming conventions to assume they are the same object.
- An index backing a constraint has a lifecycle tied to enable/disable/drop operations on the constraint, though whether Oracle keeps or drops the index depends on whether it was auto-created or reused, command options, and constraint type.

### 4.2. Constraint Is the Rule; Index Is the Mechanism

| Situation | Constraint | Index | Key Takeaway |
|---|---|---|---|
| Declare `PRIMARY KEY(id)` | Guarantees `id` is unique and non-null | Oracle creates or reuses a backing index | A primary key may be enforced via an index with a different name |
| Declare `UNIQUE(code)` | Guarantees code uniqueness per nullable rules | Oracle creates or reuses a backing index | Does not replace `NOT NULL` |
| Only `CREATE UNIQUE INDEX(code)` | No PK/UK constraint is declared by this command | Unique index forbids duplicate index keys per Oracle rules | Relational metadata and foreign keys require a proper constraint |
| Only `CREATE INDEX(code)` | No uniqueness rule | Nonunique index only aids access | Duplicate data is still allowed unless another constraint prevents it |
| Deferrable `UNIQUE` | Rule checking can be deferred until end of transaction | Can be backed by a nonunique index | `INDEX.UNIQUENESS` does not always mirror `CONSTRAINT_TYPE` |

**Do not infer backward:** seeing `USER_INDEXES.UNIQUENESS = 'UNIQUE'` does not prove the table has a `UNIQUE` constraint; inspect `USER_CONSTRAINTS` and its associated index. Likewise, `USER_INDEXES.UNIQUENESS = 'NONUNIQUE'` does not mean the index cannot back a primary key or unique constraint.

### 4.3. Using an Existing Index to Back a Constraint

Example in a lab schema—create a **nonunique** index first, then specify it when adding the primary key:

```sql
CREATE TABLE lab_index_reuse (
    id NUMBER NOT NULL,
    note VARCHAR2(50 CHAR)
);

CREATE INDEX ix_lab_index_reuse_id
    ON lab_index_reuse (id);

ALTER TABLE lab_index_reuse
ADD CONSTRAINT pk_lab_index_reuse PRIMARY KEY (id)
USING INDEX ix_lab_index_reuse_id;
```

The constraint requires `ID` to be unique and non-null; Oracle can enforce it using the specified suitable **nonunique index**. That index does not turn into a separate constraint; the index type and constraint behavior are managed independently. This example shows why seeing `USER_INDEXES.UNIQUENESS = NONUNIQUE` is not enough to conclude that `ID` allows duplicates.

In real projects, deciding to reuse an index must account for column ordering, structure, partitioning, availability, privileges, and optimizer impact. Never blindly attach an index just because its name looks similar to the constraint.

### 4.4. What Is `USING INDEX` For?

When creating a PK/UNIQUE constraint, Oracle provides **`USING INDEX`** to specify or configure the backing index in supported cases. It can reuse an existing index or define valid storage attributes for the created index. Exact restrictions depend on constraint/index type and Oracle version.

Example on a new table reusing a pre-created index:

```sql
CREATE TABLE lab_code_reuse (
    id NUMBER NOT NULL,
    business_code VARCHAR2(30 CHAR) NOT NULL
);

CREATE INDEX ix_lab_code_reuse_code
    ON lab_code_reuse (business_code);

ALTER TABLE lab_code_reuse
ADD CONSTRAINT uq_lab_code_reuse UNIQUE (business_code)
USING INDEX ix_lab_code_reuse_code;
```

Oracle enforces the constraint even though the index was initially created as nonunique. If the table already contains duplicate values, creating or enabling the constraint fails. Investigate and resolve duplicates before activating the constraint.

## 5. Deferrable Constraints: Why UNIQUE/PK Can Use a Nonunique Index

By default, unique and primary key constraints are checked immediately (**non-deferrable**). Oracle also allows certain constraints to be declared **`DEFERRABLE`**, meaning checking can occur at statement end or be deferred until transaction `COMMIT`.

This is useful for multi-row update workflows, such as **swapping two unique seat codes** within a single transaction where intermediate states temporarily collide.

### 5.1. Declaring a Deferrable UNIQUE Constraint

```sql
CREATE TABLE lab_seat_assignment (
    employee_id NUMBER NOT NULL,
    seat_code   VARCHAR2(20 CHAR) NOT NULL,
    CONSTRAINT pk_lab_seat_assignment PRIMARY KEY (employee_id),
    CONSTRAINT uq_lab_seat_code UNIQUE (seat_code)
        DEFERRABLE INITIALLY IMMEDIATE
);
```

In this example, `UQ_LAB_SEAT_CODE` **is permitted to switch to deferred checking** inside a transaction, while defaulting to immediate mode. Oracle cannot use an **immediately-enforcing unique index** to permit the temporary duplicate states allowed by a deferred constraint; therefore, a deferrable unique constraint is typically enforced through a **nonunique index**.

This explains a very important observation: **a `UNIQUE` constraint is enabled/validated while its backing index displays `NONUNIQUE` in the data dictionary**. Do not drop the index or alter the constraint just because you see this attribute.

### 5.2. Deferring Checks Within a Transaction

```sql
INSERT INTO lab_seat_assignment (employee_id, seat_code)
VALUES (1, 'A01');

INSERT INTO lab_seat_assignment (employee_id, seat_code)
VALUES (2, 'B02');

COMMIT;

-- Start a transaction swapping seats in deferred mode.
SET CONSTRAINTS uq_lab_seat_code DEFERRED;

UPDATE lab_seat_assignment
SET seat_code = CASE employee_id
    WHEN 1 THEN 'B02'
    WHEN 2 THEN 'A01'
    ELSE seat_code
END
WHERE employee_id IN (1, 2);

COMMIT;
```

After `COMMIT` succeeds, the two seats are swapped and uniqueness remains intact. During execution, rows may temporarily violate the deferrable constraint as allowed; **the final transaction state must still be valid**. If data still duplicates at final validation time, `COMMIT` fails; the application must handle the error, investigate, and roll back or fix the transaction per policy.

Only constraints **declared `DEFERRABLE` from the start** can switch checking modes this way. A constraint created with the default `NOT DEFERRABLE` does not become deferrable when calling `SET CONSTRAINTS`; changing that property typically requires a controlled drop/recreate of the constraint.

### 5.3. Deferrable Is Not Always Better

- Deferring uniqueness helps with batch swaps/updates, but increases error-handling complexity at `COMMIT` time.
- A nonunique index backing a deferred constraint has different characteristics from a standard unique index; measure against real workloads.
- `DEFERRABLE INITIALLY DEFERRED` can delay data errors until the end of the transaction, making debugging harder if the application assumes every individual statement is valid upon execution.
- Long-lived transactions increase contention and resource usage; do not use deferred constraints to mask frequent duplicate-data issues.

When there is no clear business need, **non-deferrable keys** remain the simpler default for most application tables.

## 6. How Do PRIMARY KEY/UNIQUE and FOREIGN KEY Relate?

A **foreign key (FK)** represents a referential relationship between a child table and a declared key on a parent table. In Oracle, the target key must be backed by a valid **primary key or unique constraint**, not merely a standalone unique index without a constraint.

```sql
CREATE TABLE lab_order_headers (
    order_id      NUMBER NOT NULL,
    order_code    VARCHAR2(40 CHAR) NOT NULL,
    CONSTRAINT pk_lab_order_headers PRIMARY KEY (order_id),
    CONSTRAINT uq_lab_order_headers_code UNIQUE (order_code)
);

CREATE TABLE lab_order_payments (
    payment_id NUMBER NOT NULL,
    order_code VARCHAR2(40 CHAR) NOT NULL,
    amount     NUMBER(12, 2) NOT NULL,
    CONSTRAINT pk_lab_order_payments PRIMARY KEY (payment_id),
    CONSTRAINT fk_lab_payment_order_code FOREIGN KEY (order_code)
        REFERENCES lab_order_headers (order_code)
);
```

This example demonstrates that an FK **does not have to reference a primary key**. `LAB_ORDER_PAYMENTS.ORDER_CODE` can reference `LAB_ORDER_HEADERS.ORDER_CODE` because the parent table has a **unique constraint** on that column.

### 6.1. What Does a Foreign Key Guarantee?

- When `ORDER_CODE` in the child table has a non-null value, Oracle verifies that the value matches a row in the parent table.
- If the referenced key does not exist, child inserts/updates fail with **`ORA-02291`**.
- Deleting or updating a parent key while dependent child rows exist without a configured cascade/set-null rule triggers **`ORA-02292`**.
- An FK can allow `NULL` in the child column if the child column lacks `NOT NULL`; this models an optional relationship and should be deliberate.

### 6.2. Does Oracle Automatically Create Indexes on Foreign Key Columns?

**No.** Oracle typically creates or reuses an index to enforce the parent table's **PK/UNIQUE**, but **does not automatically create a separate index on child-table foreign key columns** just because an FK is declared.

In systems with frequent joins or frequent parent-row updates/deletes, indexing FK columns can help query performance and reduce certain locking/contention risks during referential checks. For example:

```sql
CREATE INDEX ix_lab_payments_order_code
ON lab_order_payments (order_code);
```

However, **not every FK needs an index**: indexes add write and storage overhead; if the child table is tiny, joins are rare, or an existing composite index already covers the leading column, an extra index may be redundant. Check execution plans, query frequency, parent DML patterns, and data characteristics before adding one.

### 6.3. Is a Standalone Unique Index Enough for a Parent Key?

Suppose a parent table has:

```sql
CREATE UNIQUE INDEX ux_some_business_code
ON some_parent_table (business_code);
```

This statement creates a **unique index** on a hypothetical table. To create a foreign key referencing `BUSINESS_CODE`, the parent table must have a valid **PK/UNIQUE constraint**; a standalone unique index does not satisfy foreign key target requirements. On a real table, you can add a unique constraint on the column when conditions are met, allowing Oracle to reuse the suitable index.

## 7. Index Enforcement Does Not Mean the Optimizer Always Uses the Index

An index used to enforce key integrity and an index chosen by an **execution plan** are two different concerns. When Oracle receives a query, the optimizer chooses among full table scan, index unique scan, index range scan, index fast full scan, or other access paths based on cost, statistics, and SQL structure.

### 7.1. Querying by Primary Key

```sql
SELECT customer_id, username, email
FROM lab_customers
WHERE customer_id = :customer_id;
```

With an equality predicate on a single-column primary key, the key's index is usually an efficient way to locate a row. Still, **never claim Oracle is forced to use the index every time**: tiny tables, statistics, optimizer settings, and other factors can make a full table scan cheaper.

### 7.2. Querying by Composite Key

```sql
SELECT product_id, quantity
FROM lab_order_items
WHERE order_id = :order_id
  AND line_no = :line_no;
```

The composite key `(ORDER_ID, LINE_NO)` matches queries filtering on both equality predicates well. If queries frequently filter only by `LINE_NO`, an index ordered `(ORDER_ID, LINE_NO)` does not behave like an index leading with `LINE_NO`. Designing indexes for queries requires looking at column order, selectivity, and access patterns—**not just constraint names**.

### 7.3. B-Tree Indexes and NULL Values

In a **standard Oracle B-tree index**, an index key in which **all indexed columns are `NULL`** is generally not stored as an index entry. This helps explain why a single-column unique constraint allows multiple `NULL` values and how composite keys with null components behave. However, do not conclude from this that **no `IS NULL` query can ever use an index**: composite indexes containing another non-null column, function-based indexes, bitmap indexes, and other designs can create valid index access paths.

**Index uniqueness is a property of the index key**, which does not mean Oracle treats two rows with identical business attributes as duplicates if the index only covers part of them. Data rules must be declared accurately via PK/UNIQUE constraints and complementary constraints.

## 8. Querying Metadata: Which Constraint Uses Which Index?

When auditing an Oracle schema, do not just list `USER_INDEXES`. Inspect **`USER_CONSTRAINTS`**, **`USER_CONS_COLUMNS`**, **`USER_INDEXES`**, and **`USER_IND_COLUMNS`** together.

### 8.1. Listing PRIMARY KEY and UNIQUE Constraints

```sql
SELECT constraint_name,
       table_name,
       constraint_type,
       status,
       validated,
       deferrable,
       deferred,
       index_name
FROM user_constraints
WHERE constraint_type IN ('P', 'U')
ORDER BY table_name, constraint_type, constraint_name;
```

| Column | Meaning to Check |
|---|---|
| `CONSTRAINT_TYPE = 'P'` | Primary key constraint |
| `CONSTRAINT_TYPE = 'U'` | Unique constraint |
| `STATUS` | Whether the constraint is enabled or disabled |
| `VALIDATED` | Whether Oracle has verified that all existing data satisfies the constraint |
| `DEFERRABLE` | Whether the constraint allows deferred checking |
| `DEFERRED` | Declared initial checking mode |
| `INDEX_NAME` | Index associated with enforcing PK/UNIQUE, when applicable |

Note that a constraint's state can be **`ENABLED NOVALIDATE`** when Oracle enforces new changes without having verified all historical rows under that state. Never assume `ENABLED` guarantees historical data has zero violations; check `VALIDATED` and migration history too.

### 8.2. Listing Columns Belonging to Each Constraint

```sql
SELECT c.table_name,
       c.constraint_name,
       c.constraint_type,
       cc.column_name,
       cc.position
FROM user_constraints c
JOIN user_cons_columns cc
  ON cc.constraint_name = c.constraint_name
WHERE c.constraint_type IN ('P', 'U')
ORDER BY c.table_name, c.constraint_name, cc.position;
```

`POSITION` indicates column order within the constraint. For composite keys, this clarifies the definition and helps compare against index column order—though you should not assume the backing index chosen by Oracle always shares the exact name or declaration order in every index-reuse scenario.

### 8.3. Inspecting Backing Indexes and Index Types

```sql
SELECT c.table_name,
       c.constraint_name,
       c.constraint_type,
       c.deferrable,
       c.index_name,
       i.uniqueness,
       i.index_type,
       i.status
FROM user_constraints c
LEFT JOIN user_indexes i
  ON i.index_name = c.index_name
WHERE c.constraint_type IN ('P', 'U')
ORDER BY c.table_name, c.constraint_name;
```

Seeing `CONSTRAINT_TYPE = 'U'` alongside `UNIQUENESS = 'NONUNIQUE'` can be completely valid—especially for deferrable constraints or reused nonunique indexes backing a constraint. Do not "fix" it just because the two terms look different.

### 8.4. Inspecting Actual Index Column Order

```sql
SELECT index_name,
       table_name,
       column_name,
       column_position,
       descend
FROM user_ind_columns
WHERE table_name IN ('LAB_CUSTOMERS', 'LAB_ORDER_ITEMS')
ORDER BY index_name, column_position;
```

For expression-based indexes, also check `USER_IND_EXPRESSIONS`; looking only at generated column names can be misleading. For objects in another schema, use the corresponding `ALL_*` or `DBA_*` views with proper privileges and filter by `OWNER`/`INDEX_OWNER`. In a CDB/PDB architecture, verify you are in the **right PDB** before comparing metadata for identically named objects.

### 8.5. Metadata Investigation Map

```text
USER_CONSTRAINTS
  - TABLE_NAME
  - CONSTRAINT_NAME
  - CONSTRAINT_TYPE = P / U
  - INDEX_NAME (when applicable)
            |
            +---- USER_CONS_COLUMNS
            |        key columns
            |
            +---- USER_INDEXES
                     - UNIQUENESS
                     - INDEX_TYPE
                     - STATUS
                       |
                       +---- USER_IND_COLUMNS
                                index columns
```

The relationship between a constraint and its index should be **observed directly in metadata**, never inferred by comparing object names or assuming one index must exist per individual column.

## 9. PK/UNIQUE Schema Changes in Migrations

On a table that already contains data, adding a primary key or unique constraint will fail if existing rows violate the condition. Detect this **before** deploying the migration to production.

### 9.1. Finding Duplicates Before Adding UNIQUE

Suppose `CUSTOMERS_LEGACY` has an `EXTERNAL_CODE` column that the system wants to make unique:

```sql
SELECT external_code, COUNT(*) AS duplicate_count
FROM customers_legacy
WHERE external_code IS NOT NULL
GROUP BY external_code
HAVING COUNT(*) > 1
ORDER BY duplicate_count DESC;
```

The query above applies to a **single nullable column**, finding values appearing more than once. For a composite unique key, **group by all key columns** and interpret `NULL` combinations according to Oracle semantics rather than blindly filtering out every row containing a null.

For a primary key, check both **duplicate keys** and **`NULL` values**:

```sql
SELECT COUNT(*) AS rows_with_missing_id
FROM customers_legacy
WHERE customer_id IS NULL;

SELECT customer_id, COUNT(*) AS duplicate_count
FROM customers_legacy
WHERE customer_id IS NOT NULL
GROUP BY customer_id
HAVING COUNT(*) > 1;
```

These illustrative queries inspect legacy data; run them only where the table exists and you have access. On large tables, DBAs and developers must account for scan cost, statistics, and maintenance windows.

### 9.2. Creating Constraints on an Existing Table

```sql
-- Run only after confirming CUSTOMERS_LEGACY has the columns and valid data.
ALTER TABLE customers_legacy
ADD CONSTRAINT pk_customers_legacy PRIMARY KEY (customer_id);

ALTER TABLE customers_legacy
ADD CONSTRAINT uq_customers_legacy_code UNIQUE (external_code);
```

If duplicates or missing IDs exist, Oracle rejects creating/validating the constraint. Do not leave `DISABLE` or `NOVALIDATE` in place indefinitely just to push a deployment through without understanding existing data. **Schema changes in Oracle are DDL and typically perform an implicit commit**; an entire migration cannot simply be undone via `ROLLBACK` like a pure DML transaction.

### 9.3. ENABLE, DISABLE, and VALIDATE Are Not Harmless Performance Switches

When a constraint is **disabled**, Oracle no longer enforces the rule during DML the way you might expect. Depending on index type and state, disabling or dropping a constraint can alter or drop its backing index; re-enabling it may require scanning the table, revalidating data, or rebuilding supporting structures.

In bulk-load pipelines, states such as `ENABLE VALIDATE`, `ENABLE NOVALIDATE`, `DISABLE`, and `DEFERRABLE` have very different effects. DBAs and migration engineers must clarify:

- Has existing data already been verified, and who is responsible for resolving violations?
- Is new DML protected by the constraint in the intended state?
- Will the backing index be kept, reused, or recreated?
- Are dependent child foreign keys affected when disabling/dropping a parent PK/UNIQUE?
- Does constraint validation time fit the table size and deployment window?

Never disable primary keys or unique constraints in production simply to "load faster" without assessing post-import validation and referential integrity risks.

### 9.4. Dropping a Constraint vs. Dropping an Index

`DROP CONSTRAINT` changes an integrity rule. `DROP INDEX` removes an access structure and can affect any constraint relying on that index. Oracle enforces rules when an index backs a PK/UNIQUE constraint; such an index generally cannot be dropped directly while the active constraint depends on it.

Therefore, never run `DROP INDEX` just because "another similar-looking index exists." Before changing anything, inspect `USER_CONSTRAINTS.INDEX_NAME`, column order, deferrability, index status, query plans, and dependencies. If a backing index truly needs replacement, perform it through a DBA-reviewed and tested migration.

## 10. Business Uniqueness: Case Sensitivity, Whitespace, and Normalization

A unique constraint on `USERNAME` does not automatically answer questions such as:

- Should `Lan` and `lan` count as the same username?
- Should `abc@example.test` and `ABC@example.test` count as the same email under the application contract?
- Are leading/trailing spaces, Unicode characters, accents, or Unicode normalization forms handled before comparison?
- Is uniqueness global across the system or scoped to a tenant?

In common binary comparison settings, strings differing in case are treated as distinct. However, Oracle also supports linguistic collations and comparison settings depending on version and configuration, so **never claim every Oracle database always compares every string in binary mode**. Uniqueness rules must align across API validation, SQL queries, constraints/indexes, and data normalization.

### 10.1. Function-Based Unique Index for Case-Insensitive Uniqueness

If an application wants case-insensitive usernames and has validated the `LOWER` rule, a **function-based unique index** can be used:

```sql
-- Illustrative example on a table permitted in DEV/TEST.
CREATE TABLE lab_usernames (
    id NUMBER PRIMARY KEY,
    username VARCHAR2(80 CHAR) NOT NULL
);

CREATE UNIQUE INDEX ux_lab_usernames_lower
ON lab_usernames (LOWER(username));
```

This index enforces uniqueness on the **evaluated expression `LOWER(USERNAME)`**. It causes `Lan` and `lan` to conflict. However, **this is a unique index on an expression**, not a standalone `UNIQUE (USERNAME)` constraint, and you cannot arbitrarily target `LOWER(USERNAME)` as a standard foreign key parent key.

`LOWER` also does not cover all Unicode normalization or complex email/username policies. In multilingual systems, check collation, normalization rules, whitespace handling, and Oracle version. Another option is storing a **normalized key** in a dedicated column or suitable virtual column, then declaring a clear constraint on that column per data policy.

### 10.2. Tenant-Scoped UNIQUE

If an object code only needs to be unique **within each tenant**, do not place a table-wide `UNIQUE (BUSINESS_CODE)` when the business allows multiple tenants to share codes. You can declare:

```sql
CREATE TABLE lab_tenant_products (
    tenant_id NUMBER NOT NULL,
    product_code VARCHAR2(40 CHAR) NOT NULL,
    product_name VARCHAR2(100 CHAR) NOT NULL,
    CONSTRAINT pk_lab_tenant_products PRIMARY KEY (tenant_id, product_code)
);
```

Here, the composite primary key enforces per-tenant uniqueness and requires both components to be non-null. If the table also has a surrogate `PRODUCT_ID` primary key, protect `(TENANT_ID, PRODUCT_CODE)` with a separate **unique constraint**, rather than a second primary key.

## 11. Partitioning and Uniqueness: Index Scope Constraints

On partitioned tables, indexes backing PK/UNIQUE constraints can be **local** or **global** depending on design and Oracle rules. A **local unique index** on a partitioned table generally requires **the index key columns to contain the table's partition key columns** so uniqueness can be enforced across all partitions. If the unique key excludes the partition key, the design may require a **global unique index** or revisiting the partitioning strategy.

Business example:

```text
Table ORDERS is partitioned by ORDER_DATE

Requirement A: UNIQUE (ORDER_DATE, ORDER_CODE)
  -> Includes partition key; a local unique index can be considered

Requirement B: UNIQUE (ORDER_CODE) across all history
  -> Excludes ORDER_DATE; typically requires global uniqueness/index
     or changing the partition/key strategy
```

Do not blindly choose a local unique index just because "independent partitions are faster"; **guaranteeing no duplicates across the entire table** is a logical requirement, not merely per-partition. Exact rules depend on partitioning type and Oracle version, so verify against actual DDL and design before deployment.

## 12. Concurrency: Why SELECT Before INSERT Does Not Replace UNIQUE

A classic application bug is checking whether a code exists via `SELECT`, and then inserting:

```text
Session A: SELECT COUNT(*) WHERE username = 'lan' -> 0
Session B: SELECT COUNT(*) WHERE username = 'lan' -> 0
Session A: INSERT username='lan' -> succeeds
Session B: INSERT username='lan' -> ?
```

Without a proper unique constraint/index, both sessions can insert duplicate data under race conditions. With an **enforced unique constraint**, Oracle applies the integrity rule during DML/transaction execution; the second session may wait on the concurrent transaction and ultimately receive `ORA-00001` when the conflict cannot be allowed.

This establishes two principles:

1. **Database constraints are the final line of defense for correctness** when uniqueness is required, even if the application performs pre-checks for friendly UI feedback.
2. **The application must still handle conflict errors cleanly**: return `409 Conflict` or an appropriate business error, retry only when safe/idempotent, and avoid leaking sensitive data.

Never treat a `SELECT NOT EXISTS` result as proof an insert will succeed under concurrent users. With deferrable constraints, the error may be raised at `COMMIT` time, so transaction handling logic must account for that.

## 13. Common Oracle Error Codes

| Error Code | Typical Context | Investigation Steps |
|---|---|---|
| `ORA-00001` | Unique constraint or unique index violation | Identify the constraint/index, involved columns, conflicting data, and concurrent write flows |
| `ORA-01400` | Attempt to insert `NULL` into a `NOT NULL` column | Check input payload, defaults/identity generation, primary key, and mandatory columns |
| `ORA-02260` | Attempt to add a second primary key to a table that already has one | Inspect `USER_CONSTRAINTS` and model additional candidate keys with `UNIQUE` |
| `ORA-02291` | Foreign key references a nonexistent parent key | Check referenced key, insert ordering, and transaction boundaries |
| `ORA-02292` | Deleting/updating a parent key while dependent child rows exist | Check FKs, child rows, and business deletion rules |
| `ORA-02299` | Cannot validate constraint because duplicate keys exist | Inspect existing data and resolve duplicates before enabling/validating |
| `ORA-01452` | Cannot create unique index because duplicate keys exist | Inspect duplicate rows or index expression values |
| `ORA-02449` | Attempt to drop a primary/unique key still referenced by an FK | Inspect dependencies and relationship-change plan |

The `ORA-00001` message usually reports the constraint or index name involved; newer versions may also include column details. **Do not rely solely on error message wording**—verify against Oracle metadata, because the reported name could be an index or a constraint, and index names do not have to match constraint names.

### 13.1. Investigating `ORA-00001` in an Account-Creation API

Safe diagnostic workflow:

1. Record the application version, environment/PDB, timestamp, and ORA code; never log passwords or unmasked personal data.
2. Identify the reported constraint/index and the table/columns it protects.
3. Trace the write path: how values are normalized, whether requests may be retried/duplicated, and whether concurrent transactions or race conditions occur.
4. Distinguish a **username** collision from a **primary key** collision caused by ID generation; both raise `ORA-00001`, yet their fixes differ.
5. Return a controlled business error; retry only if the operation is idempotent or guarded against creating invalid data.

Never drop a constraint just to "make inserts succeed," as that breaks data integrity across the entire system.

## 14. Oracle Hands-On Lab: Creating Constraints, Triggering Conflicts, and Inspecting Indexes

This exercise is designed for **Oracle DEV/TEST** in a lab schema with `CREATE TABLE` / `CREATE INDEX` privileges and sufficient quota. Never run DDL in production or schemas holding real data. `LAB_*` names are illustrative; ensure they do not already exist in your schema.

### Step 1 – Verify Connection Target

```sql
SELECT
    SYS_CONTEXT('USERENV', 'CON_NAME') AS container_name,
    SYS_CONTEXT('USERENV', 'SERVICE_NAME') AS service_name,
    SYS_CONTEXT('USERENV', 'SESSION_USER') AS session_user
FROM dual;
```

Match the PDB/service and user against your assigned lab environment. If anything does not match, **stop before running DDL**.

### Step 2 – Create a Table with PRIMARY KEY and UNIQUE

```sql
CREATE TABLE lab_pk_uk_demo (
    id NUMBER NOT NULL,
    username VARCHAR2(40 CHAR) NOT NULL,
    email VARCHAR2(100 CHAR),
    tenant_id NUMBER NOT NULL,
    external_code VARCHAR2(30 CHAR) NOT NULL,
    CONSTRAINT pk_lab_pk_uk_demo PRIMARY KEY (id),
    CONSTRAINT uq_lab_pk_uk_username UNIQUE (username),
    CONSTRAINT uq_lab_pk_uk_email UNIQUE (email),
    CONSTRAINT uq_lab_pk_uk_ext UNIQUE (tenant_id, external_code)
);
```

### Step 3 – Insert Valid Data

```sql
INSERT INTO lab_pk_uk_demo
    (id, username, email, tenant_id, external_code)
VALUES (1, 'lan', 'lan@example.test', 10, 'A01');

INSERT INTO lab_pk_uk_demo
    (id, username, email, tenant_id, external_code)
VALUES (2, 'minh', NULL, 10, 'A02');

INSERT INTO lab_pk_uk_demo
    (id, username, email, tenant_id, external_code)
VALUES (3, 'nhu', NULL, 20, 'A01');

COMMIT;
```

Three valid rows: distinct `ID`s, distinct `USERNAME`s, two allowed `NULL` `EMAIL`s, and non-duplicate `(TENANT_ID, EXTERNAL_CODE)` pairs. `EXTERNAL_CODE = 'A01'` appears in both tenant 10 and tenant 20, yet the composite pairs remain distinct.

### Step 4 – Inspect PK/UNIQUE Metadata

```sql
SELECT constraint_name, constraint_type,
       status, validated, deferrable, index_name
FROM user_constraints
WHERE table_name = 'LAB_PK_UK_DEMO'
  AND constraint_type IN ('P', 'U')
ORDER BY constraint_type, constraint_name;

SELECT index_name, uniqueness, index_type, status
FROM user_indexes
WHERE table_name = 'LAB_PK_UK_DEMO'
ORDER BY index_name;

SELECT index_name, column_name, column_position
FROM user_ind_columns
WHERE table_name = 'LAB_PK_UK_DEMO'
ORDER BY index_name, column_position;
```

Note that the table has **one** primary key and **three** unique constraints, along with the names, types, and column orders of their backing indexes. Do not draw conclusions purely from index count if extra manual indexes exist in the lab schema or if Oracle reused an existing index.

### Step 5 – Test Individual Violation Scenarios

The following statements are **intentionally designed to fail**. Run **each statement separately**, note the error code, and do not include this block in automated migrations:

```sql
-- A: Duplicate primary key ID = 1.
INSERT INTO lab_pk_uk_demo
    (id, username, email, tenant_id, external_code)
VALUES (1, 'new_user', 'new@example.test', 30, 'B01');

-- B: New ID, but duplicate username 'lan'.
INSERT INTO lab_pk_uk_demo
    (id, username, email, tenant_id, external_code)
VALUES (4, 'lan', 'other@example.test', 30, 'B02');

-- C: Duplicate UNIQUE pair (tenant_id, external_code) = (10, 'A01').
INSERT INTO lab_pk_uk_demo
    (id, username, email, tenant_id, external_code)
VALUES (5, 'another', 'another@example.test', 10, 'A01');

-- D: Primary key ID is NULL.
INSERT INTO lab_pk_uk_demo
    (id, username, email, tenant_id, external_code)
VALUES (NULL, 'null_id', NULL, 50, 'C01');
```

Statements A, B, and C typically raise `ORA-00001` while **violating different constraints**; statement D raises `ORA-01400` because `ID` cannot be null. This illustrates how constraint names help pinpoint debugging targets.

### Step 6 – Observe Nullable UNIQUE Behavior

```sql
SELECT id, username, email
FROM lab_pk_uk_demo
WHERE email IS NULL
ORDER BY id;
```

Both `MINH` and `NHU` can have `EMAIL = NULL`. This does not violate the unique constraint on `EMAIL`. If email must be required, add `NOT NULL` when the business dictates it; do not try to use `UNIQUE` alone to forbid nulls.

### Step 7 – Inspect Index Relationship and Clean Up Lab Data

Check `USER_CONSTRAINTS.INDEX_NAME` against `USER_INDEXES.UNIQUENESS`. If possible, create a separate table with `DEFERRABLE UNIQUE` as in Section 5 to observe a **`NONUNIQUE`** index backing constraint uniqueness.

After finishing and confirming only your own lab data is present, clean up:

```sql
DROP TABLE lab_pk_uk_demo PURGE;
```

`DROP TABLE ... PURGE` deletes the object permanently without sending it to the recycle bin; it is destructive DDL. **Never run it on production tables or real data**, even if names resemble `LAB_*`.

## 15. Common Design Questions

### 15.1. Natural Key or Surrogate Key as PRIMARY KEY?

| Key Choice | Advantages | Risks / Trade-offs |
|---|---|---|
| **Surrogate key** (numeric `CUSTOMER_ID`, identity/sequence, or UUID) | Stable across username/email changes; compact if numeric; consistent references | Must still add `UNIQUE` on business keys like username or partner code to block duplicates |
| **Natural key** (meaningful business code) | Leverages existing identifier; readable in SQL and reports | Format, length, or issuing rules can change; ripples across many FKs if modified |
| **Composite key** (`TENANT_ID`, `PRODUCT_CODE`) | Expresses natural contextual uniqueness | Can enlarge FKs/indexes, complicate joins, and require updates if key attributes change |

There is no single always-right answer. What matters is that the primary key is **stable, unique, and non-null**; other business keys that must be unique should also be protected by appropriate unique constraints.

### 15.2. Do We Still Need a Unique Constraint If the Backend Already Checks?

**Yes, if uniqueness is a mandatory data invariant.** Backend pre-checks improve UX, but cannot prevent concurrent transactions, import scripts, batch jobs, or other services writing directly to the database. Database constraints enforce the rule across every write path.

### 15.3. Should We Put UNIQUE on Every Frequently Filtered Column?

**No.** `UNIQUE` is an integrity rule, not a "fast index option." For example, `STATUS = 'ACTIVE'` appears across many customers; `STATUS` is not unique. If queries filter by status, evaluate a **nonunique index** and selectivity—never add `UNIQUE` just to get an index.

### 15.4. Should Every Column of a Composite Primary Key Be Indexed Individually?

Not automatically. The index backing `(TENANT_ID, PRODUCT_CODE)` has its own column order and characteristics; if queries frequently filter only by `PRODUCT_CODE`, check execution plans and workload before adding another index. Every extra index adds write, redo, storage, and maintenance costs.

### 15.5. When Is a Standalone Unique Index Appropriate?

A unique **function-based index** works well for enforcing uniqueness on a normalized expression such as `LOWER(USERNAME)`. Certain conditional uniqueness rules can also be modeled using unique function-based indexes with expressions returning `NULL` outside the protected subset. However, this is an **index enforcing index-key uniqueness**, not a column-level `UNIQUE` constraint that can serve as a standard FK parent key; applications and migrations must account for metadata and dependency implications.

## 16. Common Misconceptions to Avoid

| Misconception | Accurate Understanding |
|---|---|
| "A PRIMARY KEY is a unique index." | A primary key is a logical `UNIQUE + NOT NULL` constraint; Oracle uses an index to help enforce it, but the two objects are distinct. |
| "A table can have multiple PRIMARY KEYs." | Each table has at most one PK, which may span multiple columns; additional candidate keys use `UNIQUE`. |
| "UNIQUE automatically forbids NULL." | Single-column unique allows multiple NULLs; PK forbids null. Composite UNIQUE with NULL has specific Oracle semantics. |
| "If a row has any NULL, composite UNIQUE always allows duplicates." | In Oracle composite unique keys, keys with identical non-null portions can still be rejected as duplicates. |
| "A UNIQUE index alone is enough for an FK reference." | A foreign key requires a valid PK/UNIQUE constraint on the parent table. |
| "Because a table has a PK, I never need to inspect indexes." | You still need to understand backing indexes, column order, deferrability, and query access needs. |
| "A UNIQUE constraint always uses a UNIQUE index." | Deferrable constraints or reused indexes can use a NONUNIQUE index. |
| "After creating a UNIQUE constraint, I must create an identical UNIQUE index." | Oracle normally creates or reuses a suitable index; creating a duplicate is redundant. |
| "Oracle automatically indexes child FK columns." | Oracle does not create child-side FK indexes by default. |
| "`SELECT NOT EXISTS` before `INSERT` eliminates all duplicates." | Race conditions still happen; database constraints enforce correctness under concurrency. |
| "The PK index is always used by the optimizer." | The optimizer chooses plans based on cost, statistics, and query shape. |
| "Dropping an index does not affect constraints." | An index may be backing a PK/UNIQUE constraint; always check metadata and dependencies. |
| "DDL constraint changes can always be rolled back like DML." | Many Oracle DDL statements commit implicitly; prepare proper migrations and recovery plans. |
| "`ORA-00001` always means a duplicate ID." | It can come from any UNIQUE constraint or unique index, including business keys and function-based indexes. |

## 17. Self-Study Questions

**Question 1.** Table `CUSTOMERS` has `CUSTOMER_ID` as primary key and `USERNAME` as unique. Can two rows share the same `CUSTOMER_ID` with different usernames?

**Answer:** No. The primary key forbids duplicate `CUSTOMER_ID` values regardless of username.

**Question 2.** Table `USERS` has `EMAIL VARCHAR2(200)` and `UNIQUE(EMAIL)` without `NOT NULL`. Can two users both have `EMAIL = NULL`?

**Answer:** Yes, with a single-column unique constraint in Oracle. If email is mandatory, add `NOT NULL`.

**Question 3.** A composite primary key is `(ORDER_ID, LINE_NO)`. Can `LINE_NO = 1` appear in another order?

**Answer:** Yes, as long as the pair `(ORDER_ID, LINE_NO)` is unique and all components are non-null.

**Question 4.** The data dictionary shows constraint `UQ_CODE` has `CONSTRAINT_TYPE = U`, while its backing index has `UNIQUENESS = NONUNIQUE`. Is the configuration necessarily broken?

**Answer:** No. The constraint could be `DEFERRABLE` or backed by a reused nonunique index. Check `USER_CONSTRAINTS.DEFERRABLE`, status, and the linked index.

**Question 5.** If a standalone unique index exists on `PARENT(CODE)` without a declared constraint, can a foreign key reference it?

**Answer:** No. An FK requires a valid primary key or unique constraint declared on the parent table.

**Question 6.** Column `ORDERS.CUSTOMER_ID` has an FK to `CUSTOMERS.CUSTOMER_ID`. Does Oracle automatically create an index on `ORDERS.CUSTOMER_ID`?

**Answer:** Not by default. Evaluate adding a separate FK index based on query workload and DML patterns.

**Question 7.** Two requests both check that `USERNAME = 'lan'` does not exist, then both insert. Why is the backend pre-check insufficient?

**Answer:** Because two sessions can concurrently observe the absent state and both attempt to write. A database unique constraint protects correctness while the application handles conflict errors.

**Question 8.** A table is partitioned by `ORDER_DATE`, yet the business requires `ORDER_CODE` to be unique across all dates. Can you arbitrarily create a local unique index on `ORDER_CODE` alone?

**Answer:** Generally no. A local unique index must satisfy partition-key inclusion rules; a global unique index or an alternative design may be required. Validate against the actual partitioning strategy.

**Question 9.** Does `UNIQUE(USERNAME)` automatically treat `'Lan'` and `'lan'` as duplicates?

**Answer:** It depends on the system's collation/comparison rules. If the business requires case-insensitivity, design and test an explicit normalization/uniqueness mechanism rather than relying on an assumed default across all Oracle configurations.

**Question 10.** Should you create two indexes with the exact same columns and order when one is already used by the PK constraint?

**Answer:** Normally no, unless there is a measured and verified technical reason. Redundant indexes increase write, storage, and maintenance costs.

## Conclusion

In Oracle, **`PRIMARY KEY`** designates each table's identifying key and enforces it to be **unique and non-`NULL`**; **`UNIQUE`** protects candidate keys or business uniqueness rules across one or more columns with distinct `NULL` behavior. An **index** is the structure that accelerates access and enforces uniqueness, but **is not the constraint itself**. Oracle typically creates or reuses a suitable index; in particular, a **`DEFERRABLE`** primary key or unique constraint can be enforced through a **nonunique index**.

When designing schemas, declare constraints accurately, pick stable keys, pair `NOT NULL` where needed, distinguish composite keys from multi-column index access, understand foreign key interactions, and prevent race conditions with database-level constraints. During operations and migrations, inspect `USER_CONSTRAINTS`, `USER_CONS_COLUMNS`, `USER_INDEXES`, and `USER_IND_COLUMNS` to verify the exact objects involved, avoiding duplicate indexes or dropping indexes that back active keys. A strong design both **preserves data correctness under concurrency** and maintains query performance and safe schema evolution.
