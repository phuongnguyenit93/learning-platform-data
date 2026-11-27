# PRIMARY KEY, UNIQUE, and Supporting Indexes in PostgreSQL

## 1. Learning Objectives

In a sales system, the database must guarantee that:

- No two customers share the same **customer ID**.
- A single tenant does not have two products with the same **SKU**, while two different tenants may share the same SKU.
- Two accounts cannot register with the same **email** if email is a system-wide identifier.
- A customer has **at most one default address**.
- Order records reference **real customers**.
- Multiple concurrent requests cannot create duplicate rows because the application checked too late.

These requirements relate to **uniqueness constraints** and **indexes**. In PostgreSQL, two central constructs are:

- **`PRIMARY KEY`**: defines a table's primary key, whose key values are **non-NULL** and **unique**.
- **`UNIQUE`**: enforces uniqueness of a column or combination of columns, with specific rules for **`NULL`**.

When these constraints are created, PostgreSQL normally creates a **B-tree unique index** automatically to enforce the check. However, a **constraint** is a rule of data correctness, whereas an **index** is an access and enforcement structure. They are closely related, but they are not completely interchangeable concepts.

After this lesson, you will be able to:

1. Design single-column and composite `PRIMARY KEY` and `UNIQUE` constraints suited to business rules.
2. Explain how `NULL` behaves in unique constraints and how `NULLS NOT DISTINCT` works starting in PostgreSQL 15.
3. Distinguish between a **unique constraint**, a **unique index**, a **partial unique index**, and an **expression unique index**.
4. Understand the role of supporting indexes, column ordering, and `INCLUDE` columns for query performance.
5. Identify requirements for target keys referenced by `FOREIGN KEY` and indexes on the referencing side.
6. Handle data conflicts with `INSERT ... ON CONFLICT` without check-then-write race conditions.
7. Understand `DEFERRABLE` constraints, validation timing, and their impact on upserts.
8. Inspect indexes/constraints in the system catalogs and plan safe migrations for large tables.
9. Practice in PostgreSQL with sample datasets and exercises with solutions.

> **Safety:** Commands that create tables, insert data, or alter indexes are strictly for an authorized **practice database**. In production, always plan migrations, backups, duplicate checks, lock impact, and workload effects before making changes.

---

## 2. Two Concepts: Logical Constraints vs. Physical Structures

Consider a `customers` table:

```sql
CREATE TABLE customers (
    customer_id BIGINT PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL
);
```

There are two data guarantees:

1. `customer_id` uniquely identifies a customer and has no `NULL` values.
2. `email` never duplicates across customers and has no `NULL` values.

PostgreSQL needs an efficient way to verify these guarantees when the table grows large. When `PRIMARY KEY` or `UNIQUE` is declared on a normal heap table, PostgreSQL automatically creates a corresponding unique B-tree index.

The relationship can be pictured as:

~~~text
Business rule
  "Customer IDs cannot duplicate"
            |
            v
PRIMARY KEY (customer_id)       -- Table constraint
            |
            v
Unique B-tree index             -- Supporting enforcement structure
            |
            v
Checked on INSERT / UPDATE,
and also accelerates certain SELECT lookups
~~~

An index is not only for making `SELECT` faster: **a unique index is also responsible for blocking invalid duplicate data on writes**.

However:

- A **unique constraint** is managed as a table constraint and appears in constraint metadata.
- A **unique index** created directly with `CREATE UNIQUE INDEX` can provide uniqueness enforcement, including on **expressions** or **rows matching a predicate**.
- A non-unique regular index only serves data access and **does not enforce uniqueness**.
- PostgreSQL allows **only one `PRIMARY KEY` per table**, while allowing multiple `UNIQUE` constraints.

Do not rely on application-level checks instead of database constraints:

```text
Request A: SELECT COUNT(*) WHERE email = 'x@example.com' -> 0
Request B: SELECT COUNT(*) WHERE email = 'x@example.com' -> 0
Request A: INSERT email x
Request B: INSERT email x
```

If you rely only on `SELECT` followed by `INSERT`, two concurrent requests can both believe the email is available. A proper unique constraint/index enforces the rule **at write time**, rather than trusting an earlier read.

## 3. PRIMARY KEY: Official Row Identifier

### 3.1. What Does a PRIMARY KEY Guarantee?

```sql
CREATE TABLE products (
    product_id BIGINT PRIMARY KEY,
    product_name TEXT NOT NULL
);
```

This constraint means:

- No two rows may have the same `product_id`.
- No row may have `product_id IS NULL`.
- Each key value identifies at most one row in the table.
- PostgreSQL maintains a supporting unique index for checking and PK lookups.

Both statements below are invalid if the corresponding data already exists or the key is NULL:

```sql
-- Example that fails if product_id = 1 already exists.
INSERT INTO products(product_id, product_name)
VALUES (1, 'Other name');

-- Example that fails because PRIMARY KEY does not accept NULL.
INSERT INTO products(product_id, product_name)
VALUES (NULL, 'No ID');
```

Common SQLSTATE codes:

| Violation | SQLSTATE | Meaning |
|---|---|---|
| Duplicate primary key / unique key | `23505` | `unique_violation` |
| NULL in a required column | `23502` | `not_null_violation` |
| Referenced foreign key does not exist | `23503` | `foreign_key_violation` |
| CHECK constraint violation | `23514` | `check_violation` |

In applications, SQLSTATE codes are far more reliable than matching error message strings that vary by version or locale.

### 3.2. At Most One PRIMARY KEY per Table

```sql
CREATE TABLE demo (
    id BIGINT PRIMARY KEY,
    code TEXT UNIQUE
);
```

Here we have one PK and one alternate key. You cannot add a second PK to the same table:

```sql
-- Invalid if the table already has a PRIMARY KEY:
ALTER TABLE demo ADD PRIMARY KEY (code);
```

However, a PK can **span multiple columns**:

```sql
CREATE TABLE enrollment (
    student_id BIGINT NOT NULL,
    course_id BIGINT NOT NULL,
    grade NUMERIC(4,2),
    PRIMARY KEY (student_id, course_id)
);
```

Here each `(student_id, course_id)` pair identifies one enrollment; neither `student_id` nor `course_id` needs to be unique on its own.

### 3.3. Primary Keys Do Not Have to Auto-Increment

PostgreSQL does not require a PK to be `SERIAL`, `BIGSERIAL`, `IDENTITY`, UUID, or gapless integers. Common choices:

| Key Type | Example | Pros and Considerations |
|---|---|---|
| Business code | `sku`, `student_code` | Human-readable; must remain stable and never be improperly reused |
| Application-assigned integer | `BIGINT` | Simple; application must coordinate non-colliding IDs |
| Identity | `BIGINT GENERATED ... AS IDENTITY` | PostgreSQL generates values via a sequence |
| UUID | `UUID PRIMARY KEY` | Fits distributed systems; consider generation method and index impact |
| Composite key | `(tenant_id, sku)` | Expresses uniqueness scoped across multiple columns |

Identity example:

```sql
CREATE TABLE customers_identity (
    customer_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    full_name TEXT NOT NULL
);

INSERT INTO customers_identity(full_name)
VALUES ('Nguyen An')
RETURNING customer_id;
```

`RETURNING` is the standard way to retrieve the database-generated ID. **Auto-generating identity/sequence values does not replace PRIMARY KEY/UNIQUE**: sequences can have gaps from rollbacks or caching, can be manually adjusted, and ultimate uniqueness is still enforced by the constraint.

### 3.4. Natural Keys vs. Surrogate Keys

An email address may look like a natural key, but customers change emails, emails may require normalization, and addresses are occasionally recycled. Therefore many systems use:

```sql
customer_id BIGINT PRIMARY KEY,
email TEXT NOT NULL UNIQUE
```

`customer_id` serves as a stable **surrogate key** for relationships; `email` is an **alternate business key** per policy.

Adding a surrogate key does not mean abandoning business uniqueness: if emails must be unique, you still need an appropriate unique constraint.

## 4. UNIQUE: Enforcing Uniqueness Beyond the PRIMARY KEY

### 4.1. Single-Column UNIQUE

```sql
CREATE TABLE employees (
    employee_id BIGINT PRIMARY KEY,
    employee_code TEXT NOT NULL UNIQUE,
    full_name TEXT NOT NULL
);
```

Each `employee_code` must be unique. A table can have multiple separate unique constraints:

```sql
CREATE TABLE organizations (
    organization_id BIGINT PRIMARY KEY,
    organization_code TEXT NOT NULL UNIQUE,
    tax_number TEXT UNIQUE,
    organization_name TEXT NOT NULL
);
```

Here `organization_code` cannot be NULL; `tax_number` is allowed to be missing, following PostgreSQL's default unique semantics for NULL explained next.

### 4.2. Composite UNIQUE

```sql
CREATE TABLE catalog_products (
    tenant_id BIGINT NOT NULL,
    sku TEXT NOT NULL,
    title TEXT NOT NULL,
    CONSTRAINT uq_catalog_tenant_sku UNIQUE (tenant_id, sku)
);
```

The constraint:

```text
UNIQUE (tenant_id, sku)
```

ensures **each tenant has at most one product per SKU**.

These rows are valid:

| tenant_id | sku |
|---:|---|
| 10 | `P-100` |
| 10 | `P-101` |
| 20 | `P-100` |

Adding another `(10, 'P-100')` would violate uniqueness.

Crucially:

```text
UNIQUE (tenant_id, sku)
```

is **not equivalent to**:

```text
UNIQUE (tenant_id)
UNIQUE (sku)
```

Two separate single-column constraints would forbid a tenant from having multiple SKUs and forbid two tenants from sharing a SKU—violating the business requirement.

### 4.3. Choosing PRIMARY KEY vs. UNIQUE for a Composite Key

If a table represents course enrollments and has no separate ID:

```sql
PRIMARY KEY (student_id, course_id)
```

is a sensible choice.

If the table has an `enrollment_id` used by APIs as the primary identifier:

```sql
enrollment_id BIGINT PRIMARY KEY,
UNIQUE (student_id, course_id)
```

can also be right **if business rules still restrict each pair to one enrollment**. The two constraints serve different roles and are not semantically redundant, even though both create indexes with storage/write overhead.

### 4.4. Naming Constraints Helps Error Handling

```sql
CREATE TABLE accounts (
    account_id BIGINT PRIMARY KEY,
    account_code TEXT NOT NULL,
    CONSTRAINT uq_accounts_account_code UNIQUE (account_code)
);
```

The name `uq_accounts_account_code` helps identify the exact violated rule in logs, migrations, and `ON CONFLICT ON CONSTRAINT`.

Meaningful names also simplify schema changes and locating constraints in `pg_constraint`.

## 5. NULL in UNIQUE: A Crucial Distinction

### 5.1. Default UNIQUE Treats NULL Values as Distinct

Under PostgreSQL's default behavior:

```sql
CREATE TABLE contact_methods (
    contact_id BIGINT PRIMARY KEY,
    external_reference TEXT UNIQUE
);
```

These rows are **valid**:

```sql
INSERT INTO contact_methods(contact_id, external_reference)
VALUES
    (1, NULL),
    (2, NULL),
    (3, 'EXT-100');
```

Because a default unique constraint does not treat `NULL` values as equal for uniqueness checking.

However:

```sql
-- Fails because 'EXT-100' already exists.
INSERT INTO contact_methods(contact_id, external_reference)
VALUES (4, 'EXT-100');
```

Do not confuse `NULL` with empty string `''`: two identical empty strings in a unique column are treated as duplicates, whereas multiple `NULL`s can coexist under default rules.

### 5.2. NULL in Composite UNIQUE

```sql
CREATE TABLE app_events (
    event_id BIGINT PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    external_ref TEXT,
    UNIQUE (tenant_id, external_ref)
);
```

These rows:

```text
(tenant_id=10, external_ref=NULL)
(tenant_id=10, external_ref=NULL)
```

are allowed under default unique semantics. Thus, **a nullable component** in a composite key can allow multiple rows with identical values in all other columns without being flagged as duplicates.

If a business key **must uniquely identify every row**, consider `NOT NULL` on key columns or `NULLS NOT DISTINCT`.

### 5.3. UNIQUE NULLS NOT DISTINCT (PostgreSQL 15+)

Starting in PostgreSQL 15, you can write:

```sql
CREATE TABLE external_links (
    link_id BIGINT PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    external_ref TEXT,
    CONSTRAINT uq_external_links
        UNIQUE NULLS NOT DISTINCT (tenant_id, external_ref)
);
```

This constraint treats `NULL` as **not distinct** for uniqueness. Therefore:

- `(10, 'ABC')` is allowed at most once.
- `(10, NULL)` is also allowed at most **once**.
- `(20, NULL)` can still exist because `tenant_id` differs.

Do not apply `NULLS NOT DISTINCT` mechanically: if the domain allows **multiple records without an external code**, the default unique behavior is more appropriate.

You can also use it directly on an index:

```sql
CREATE UNIQUE INDEX uq_external_links_tenant_ref
ON external_links (tenant_id, external_ref)
NULLS NOT DISTINCT;
```

This is an alternative when an equivalent constraint/index does not already exist; **there is no need to create both** on the same columns without a specific reason.

### 5.4. Deciding Based on Business Requirements

| Rule | Suggested Representation |
|---|---|
| Customer ID always exists and is unique | `PRIMARY KEY` or `NOT NULL UNIQUE` |
| Email may be absent; provided emails cannot duplicate | Default `UNIQUE(email)` with nullable email |
| Each group may have at most one record missing an external code | `UNIQUE NULLS NOT DISTINCT(group_id, external_code)` |
| Only active rows must be unique | **Partial unique index** |
| Case-insensitive email uniqueness | **Expression unique index** or appropriate type/collation design |

`NULL` is a matter of **data semantics**, not merely a SQL flag.

## 6. Composite PRIMARY KEY in Multi-Tenant Systems

Many systems logically partition data by tenant.

Example:

```sql
CREATE TABLE tenant_products (
    tenant_id BIGINT NOT NULL,
    sku TEXT NOT NULL,
    product_name TEXT NOT NULL,
    unit_price NUMERIC(12,2) NOT NULL,
    PRIMARY KEY (tenant_id, sku)
);
```

Why not `PRIMARY KEY (sku)`? Because tenant A and tenant B can both sell a product with SKU `P-100`, yet those are **two independent entities**.

When designing a composite key, ask:

1. Is `tenant_id` the scope of uniqueness?
2. Does the `(tenant_id, sku)` column order suit tenant-scoped queries?
3. Will referencing tables carry both columns to preserve tenant isolation?
4. Can an old SKU be reused after discontinuation?
5. Are the key columns stable, or frequently renamed?

### 6.1. Composite Keys and Composite Foreign Keys

```sql
CREATE TABLE product_notes (
    note_id BIGINT PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    sku TEXT NOT NULL,
    note_text TEXT NOT NULL,
    CONSTRAINT fk_product_notes_product
        FOREIGN KEY (tenant_id, sku)
        REFERENCES tenant_products(tenant_id, sku)
);
```

A composite FK requires both values together to reference a single key row in `tenant_products`. You cannot mix a `tenant_id` from one product with a SKU from another.

If FK columns are nullable, default `MATCH SIMPLE` rules have specific NULL behavior; to keep this model unambiguous, both columns are declared `NOT NULL`.

### 6.2. Supporting B-tree Index for a Composite Key

PostgreSQL creates a unique index for:

```sql
PRIMARY KEY (tenant_id, sku)
```

A B-tree with this key order is typically helpful for:

```sql
WHERE tenant_id = 10
```

and especially:

```sql
WHERE tenant_id = 10 AND sku = 'P-100'
```

However, a query filtering only by:

```sql
WHERE sku = 'P-100'
```

does not have the same leading-prefix advantage. PostgreSQL has optimizations depending on version and query plan, but **do not assume a `(tenant_id, sku)` index automatically optimizes every SKU-only query**. Check `EXPLAIN` and real workloads before adding extra indexes.

## 7. Indexes Created by PostgreSQL to Support Constraints

### 7.1. PRIMARY KEY and UNIQUE Create Indexes by Default

On standard heap tables, declaring:

```sql
PRIMARY KEY (product_id)
```

or:

```sql
UNIQUE (tenant_id, sku)
```

causes PostgreSQL to automatically create a **unique B-tree index** to enforce those constraints.

Therefore, do not blindly create an extra:

```sql
CREATE INDEX idx_duplicate ON products (product_id);
```

when `PRIMARY KEY(product_id)` already exists. A redundant index with identical keys only increases storage and write overhead without reliably improving `SELECT`.

### 7.2. Constraints and Indexes Are Not Completely Equivalent

| Criterion | `PRIMARY KEY` | `UNIQUE` constraint | `CREATE UNIQUE INDEX` |
|---|---|---|---|
| Prevents duplicate keys | Yes | Yes | Yes |
| Forbids NULL in all key columns | Yes | Not by default; add `NOT NULL` if needed | Not by default; depends on columns and `NULLS NOT DISTINCT` |
| Multiple allowed per table? | At most one PK | Yes | Yes |
| Constraint metadata in `pg_constraint` | Yes | Yes | Does not automatically create a constraint when created directly |
| Creates supporting B-tree unique index | Yes | Yes | Is itself an index |
| Expressions like `lower(email)` | Not directly in constraint column list | Not directly as a constraint expression | Yes |
| Predicate like `WHERE is_active` | No | No | Yes |
| `DEFERRABLE` as constraint | Possible | Possible | Direct `CREATE UNIQUE INDEX` has no such declaration |
| Clarity for logical modeling | Very clear | Very clear | Expresses specialized rule needing documentation |

An index created to back a constraint may share the constraint's name; dropping the constraint drops its backing index. Never manipulate a **constraint-owned index** directly as if it were an independent index.

### 7.3. Inspecting Indexes with pg_indexes

```sql
SELECT
    schemaname,
    tablename,
    indexname,
    indexdef
FROM pg_indexes
WHERE schemaname = 'constraint_lab'
ORDER BY tablename, indexname;
```

`pg_indexes.indexdef` shows the PostgreSQL index definition statement, including access method, key columns, `UNIQUE` attribute, and any predicate.

### 7.4. Inspecting Constraints with pg_constraint

```sql
SELECT
    con.conname AS constraint_name,
    con.contype AS constraint_type,
    con.conrelid::regclass AS table_name,
    con.conindid::regclass AS supporting_index,
    con.condeferrable AS is_deferrable,
    con.condeferred AS initially_deferred,
    pg_get_constraintdef(con.oid, true) AS definition
FROM pg_constraint AS con
JOIN pg_namespace AS n
  ON n.oid = con.connamespace
WHERE n.nspname = 'constraint_lab'
  AND con.contype IN ('p', 'u')
ORDER BY table_name, constraint_name;
```

In `pg_constraint.contype`:

- `p` is primary key.
- `u` is unique constraint.
- `f` is foreign key.
- `c` is check constraint.

A standalone `CREATE UNIQUE INDEX` appears in `pg_indexes` **without** a corresponding entry in `pg_constraint`.

### 7.5. Checking Index State via pg_index

```sql
SELECT
    i.indexrelid::regclass AS index_name,
    i.indrelid::regclass AS table_name,
    i.indisunique AS unique_index,
    i.indisprimary AS primary_index,
    i.indisvalid AS valid_for_planner,
    i.indisready AS ready_for_writes,
    i.indnkeyatts AS key_columns,
    i.indnatts AS all_index_columns,
    pg_get_indexdef(i.indexrelid) AS definition
FROM pg_index AS i
WHERE i.indrelid = 'constraint_lab.products'::regclass
ORDER BY index_name;
```

`indisvalid` and `indisready` are especially useful when a **`CREATE INDEX CONCURRENTLY`** fails or has not completed. Never treat an index's mere existence in the catalog as proof that it is valid and ready.

## 8. Standalone UNIQUE INDEX: When Standard Constraints Are Not Enough

### 8.1. Creating a Standard Unique Index

```sql
CREATE UNIQUE INDEX ux_users_username
ON users (username);
```

This syntax requires the `users` table to exist; it is an illustrative example, not a statement to run immediately against the lab schema.

It enforces uniqueness like a non-deferrable constraint, but exists as a **standalone index**. If no expression, predicate, or special workflow is needed, using a `UNIQUE` constraint in DDL usually expresses the data model more clearly.

### 8.2. Expression Unique Index

Sometimes business rules treat two emails differing only in case as the same identifier:

```text
Lan@Example.com
lan@example.com
```

If you only declare:

```sql
UNIQUE (email)
```

under typical case-sensitive types/collations, the two strings are not treated as duplicates.

You can use an expression index:

```sql
CREATE UNIQUE INDEX ux_users_email_normalized
ON users (lower(btrim(email)));
```

The index enforces uniqueness on **the evaluated expression** `lower(btrim(email))`, rather than the raw `email` text.

Keep in mind:

- Index expressions must meet PostgreSQL's requirements, including using functions allowed in index expressions.
- Case-insensitivity rules for email should be verified, especially regarding local-part rules, Unicode, collations, and normalization policy.
- **Existing data** containing two values with the same normalized form will cause unique index creation to fail.
- Queries wanting to leverage an expression index usually must match the expression/predicate for the planner to recognize it.
- Do not use an expression unique index as a standard FK target if you need to reference the raw column under standard FK rules.

Another option where supported is the `citext` extension or a custom collation design, though each approach has semantics and costs that must be evaluated rather than assumed identical.

### 8.3. Partial Unique Index: Constraining Only a Subset of Rows

Requirement:

> Each customer can have **at most one default shipping address**.

A table holding multiple addresses:

```sql
CREATE TABLE customer_addresses (
    address_id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    label TEXT NOT NULL,
    is_default BOOLEAN NOT NULL DEFAULT FALSE
);
```

Using:

```sql
UNIQUE (customer_id, is_default)
```

would be wrong because it allows **at most one** `is_default = FALSE` address per customer, whereas a customer must be allowed many non-default addresses.

The solution is a **partial unique index**:

```sql
CREATE UNIQUE INDEX ux_addresses_one_default
ON customer_addresses (customer_id)
WHERE is_default;
```

The index only contains rows where `is_default` is `TRUE`. Consequently:

- A customer can have **many non-default addresses**.
- A customer can have **at most one default address**.
- A customer can have **zero** default addresses.

Important final point: a partial unique index enforces **“at most one”**, **not “required to have one”**. If every customer must have a default address, additional workflow logic or constraints suited to creation and deletion paths are required.

### 8.4. Soft Deletes and Conditional Uniqueness

An application may retain soft-deleted rows:

```sql
CREATE TABLE project_members (
    membership_id BIGINT PRIMARY KEY,
    project_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL,
    deleted_at TIMESTAMPTZ
);
```

Rule:

> Each `(project_id, user_id)` pair may have only one membership that is **not soft-deleted**.

```sql
CREATE UNIQUE INDEX ux_project_members_active
ON project_members (project_id, user_id)
WHERE deleted_at IS NULL;
```

Once a membership has a non-NULL `deleted_at`, it leaves the index set and the pair can be inserted again for a new membership.

Therefore, plan carefully for “restoring” an old membership: if a new active membership already exists for the same pair, setting `deleted_at = NULL` on the old row will be blocked by the unique index. That is usually the desired behavior to avoid two active memberships.

### 8.5. A Partial Index Is Not a Standard UNIQUE Constraint

A `UNIQUE` constraint has no `WHERE` clause to apply only to a subset of rows. `CREATE UNIQUE INDEX ... WHERE ...` is the proper tool for conditional uniqueness.

A partial unique index **cannot be attached as a standard UNIQUE constraint** via `ALTER TABLE ... ADD CONSTRAINT ... USING INDEX`, and cannot serve as a general FK target key the way a full unique key can.

## 9. Column Order, Composite Indexes, and Query Optimization

### 9.1. Key Order Affects Access Paths

With:

```sql
UNIQUE (tenant_id, sku)
```

PostgreSQL builds a B-tree ordered by `(tenant_id, sku)`.

This query:

```sql
SELECT *
FROM constraint_lab.products
WHERE tenant_id = 10
  AND sku = 'P-100';
```

is an ideal match for both key columns.

This query:

```sql
SELECT *
FROM constraint_lab.products
WHERE tenant_id = 10;
```

can leverage the `tenant_id` leading prefix when the table is large enough and the planner finds it beneficial.

This query:

```sql
SELECT *
FROM constraint_lab.products
WHERE sku = 'P-100';
```

does not share the same leading-prefix advantage. If searching by SKU across **all tenants** is frequent and selective, you can evaluate another index such as:

```sql
CREATE INDEX ix_products_sku
ON constraint_lab.products (sku);
```

However, add it only after measuring the workload and checking `EXPLAIN`; never assume an extra index is always beneficial.

### 9.2. An Index Backing Uniqueness Can Serve SELECTs

With a primary key:

```sql
PRIMARY KEY (order_id)
```

this query:

```sql
SELECT *
FROM constraint_lab.orders
WHERE order_id = 1001;
```

can look up the row using the PK index. On a tiny table with just a few rows, however, PostgreSQL may choose `Seq Scan`; that **does not mean PK/UNIQUE is inactive**. The constraint is still enforced on writes regardless of the planner's read strategy.

### 9.3. Do Not Create Duplicate Indexes “Just in Case”

If a table already has:

```sql
PRIMARY KEY (tenant_id, sku)
```

then:

```sql
CREATE UNIQUE INDEX ux_products_same_columns
ON constraint_lab.products (tenant_id, sku);
```

typically adds no new business rule while increasing write costs. Before optimizing, inspect `pg_indexes` and establish a specific reason—such as sort direction, column order, predicate, or covering columns—for adding another index.

### 9.4. INCLUDE and Covering Indexes

PostgreSQL supports adding non-key columns that **do not participate in lookup/uniqueness keys** as **`INCLUDE`** columns, for example:

```sql
CREATE INDEX ix_products_tenant_sku_cover
ON constraint_lab.products (tenant_id, sku)
INCLUDE (product_name, price);
```

The index has two **key columns** and two **included columns**. Included columns:

- Can allow certain queries to satisfy projections directly from the index without reading heap rows when conditions permit.
- **Do not participate** in uniqueness checking in a unique index with `INCLUDE`.
- Make the index larger; data types and value sizes affect storage and indexability.
- Do not always eliminate heap fetches because PostgreSQL must still verify **MVCC visibility**.

For example, if a unique constraint/index has key `(tenant_id, sku)` and `INCLUDE(product_name)`, uniqueness is still evaluated solely on `(tenant_id, sku)`.

**Note:** the lab schema already has `PRIMARY KEY (tenant_id, sku)`. The covering index above is a **test candidate** that overlaps with the PK index, not a recommendation to keep both unconditionally. Always measure before adding wide indexes.

## 10. FOREIGN KEY: Target Keys and Referencing-Side Indexes

### 10.1. FKs Must Reference a PostgreSQL-Accepted Unique Key

Example:

```sql
CREATE TABLE authors (
    author_id BIGINT PRIMARY KEY,
    pen_name TEXT NOT NULL UNIQUE
);

CREATE TABLE books (
    book_id BIGINT PRIMARY KEY,
    author_id BIGINT NOT NULL
        REFERENCES authors(author_id)
);
```

`authors` has a PK on `author_id`. `books` uses an FK to guarantee the referenced ID is valid.

Under PostgreSQL's rules, FK target columns must form a **primary key**, a **non-deferrable unique constraint**, or match a suitable **non-partial unique index**. Do not assume a partial or expression unique index can act as a normal FK target.

### 10.2. PostgreSQL Does Not Auto-Create an Index on the Child FK Column

When you write:

```sql
CREATE TABLE books (
    book_id BIGINT PRIMARY KEY,
    author_id BIGINT NOT NULL REFERENCES authors(author_id)
);
```

PostgreSQL enforces the relationship using the PK/unique index on the **parent table**. It **does not automatically** create an index on `books(author_id)` just because an FK exists.

If you frequently query books by author or delete/update parent keys in `authors`, you can add:

```sql
CREATE INDEX ix_books_author_id
ON books(author_id);
```

An index on the child table can be critical when PostgreSQL checks referencing rows during parent `DELETE` or `UPDATE`. Without an appropriate index, such operations may scan many rows in the child table.

### 10.3. Composite Foreign Keys

Suppose:

```sql
PRIMARY KEY (tenant_id, sku)
```

is on products. A notes table must reference **both columns**:

```sql
FOREIGN KEY (tenant_id, sku)
REFERENCES products(tenant_id, sku)
```

You cannot define an FK on `sku` alone if SKU is not globally unique across tenants.

### 10.4. Partial Unique Indexes and Foreign Keys

If you only have:

```sql
CREATE UNIQUE INDEX ux_active_email
ON customers (email)
WHERE deleted_at IS NULL;
```

uniqueness applies only to **non-soft-deleted customers**. It cannot be used as a standard FK target across all rows of `customers`, because rows outside the predicate may share duplicate emails.

This is why relationships typically reference an **immutable PK** such as `customer_id`, while `email` remains a business attribute with its own uniqueness policy.

## 11. DEFERRABLE UNIQUE and PRIMARY KEY

### 11.1. Immediate or Deferred?

By default, constraints are checked under **non-deferred (immediate)** rules. Certain scenarios require a transaction to **temporarily** pass through a state that violates uniqueness before restoring validity **prior to commit**.

For example, swapping seat numbers 1 and 2 between two guests in the same session:

```text
Guest A: seat 1
Guest B: seat 2
```

If you update A to 2 before updating B to 1, the intermediate state would be blocked by a normal unique constraint.

PostgreSQL supports `DEFERRABLE` constraints:

```sql
CREATE TABLE seat_assignments (
    assignment_id BIGINT PRIMARY KEY,
    session_id BIGINT NOT NULL,
    seat_no INTEGER NOT NULL,
    CONSTRAINT uq_session_seat
        UNIQUE (session_id, seat_no)
        DEFERRABLE INITIALLY DEFERRED
);
```

Sample data:

```sql
INSERT INTO seat_assignments
    (assignment_id, session_id, seat_no)
VALUES
    (1, 10, 1),
    (2, 10, 2);
```

Seat-swap transaction:

```sql
BEGIN;

UPDATE seat_assignments
SET seat_no = CASE seat_no
    WHEN 1 THEN 2
    WHEN 2 THEN 1
END
WHERE session_id = 10
  AND seat_no IN (1, 2);

COMMIT;
```

The constraint is checked in deferred mode, allowing intermediate states while requiring **valid data at the final check point**. If two rows still share `(session_id, seat_no)` at commit time, the transaction fails.

### 11.2. Setting Check Timing

You can declare:

```sql
UNIQUE (session_id, seat_no)
DEFERRABLE INITIALLY IMMEDIATE
```

and inside a transaction with appropriate scope/privileges:

```sql
BEGIN;

SET CONSTRAINTS uq_session_seat DEFERRED;

-- Perform a sequence of changes.
-- Final state must satisfy uniqueness.

COMMIT;
```

`SET CONSTRAINTS` only controls constraints that are deferrable; it cannot make an ordinary index deferrable.

### 11.3. Trade-Offs of Using DEFERRABLE

- Violations may surface only at `COMMIT`, so applications must handle commit-time failures.
- Deferrable constraints can incur different overhead and contention compared to immediate uniqueness checks.
- PostgreSQL **does not allow deferrable unique constraints as conflict arbiters for `ON CONFLICT DO UPDATE`**.
- When serving as an FK target, note that PostgreSQL requires referenced uniqueness keys to be **non-deferrable**.

Therefore, only use `DEFERRABLE` when a business operation genuinely needs temporary reordering or swapping inside a transaction.

### 11.4. ON CONFLICT and DEFERRABLE

`INSERT ... ON CONFLICT` needs a suitable arbiter to detect conflicting rows. A deferrable unique constraint is **not a suitable choice** for that syntax. If the primary write pattern is upserting by a business key, a **non-deferrable** `UNIQUE` constraint is normally the right fit.

## 12. INSERT ... ON CONFLICT: Safe Writes Under Concurrency

### 12.1. When Is Upsert Needed?

Suppose an API receives a customer record with business key:

```text
(tenant_id = 10, email = 'an@example.com')
```

If absent, insert; if present, update the display name. Two concurrent requests should not perform a separate `SELECT` followed by an `INSERT` decision.

PostgreSQL provides `ON CONFLICT` to integrate with uniqueness enforcement.

### 12.2. DO NOTHING

```sql
INSERT INTO constraint_lab.customers
    (customer_id, tenant_id, email, display_name)
VALUES
    (99, 10, 'an@example.com', 'New An')
ON CONFLICT ON CONSTRAINT uq_customers_tenant_email
DO NOTHING;
```

If tenant 10 already has that email, no new row is inserted. However, **silently ignoring** conflicts must fit the business rule: if this is a registration flow where the user expects an “email already taken” error, `DO NOTHING` could hide a critical event.

### 12.3. DO UPDATE

```sql
INSERT INTO constraint_lab.customers
    (customer_id, tenant_id, email, display_name)
VALUES
    (99, 10, 'an@example.com', 'New Nguyen An')
ON CONFLICT ON CONSTRAINT uq_customers_tenant_email
DO UPDATE SET
    display_name = EXCLUDED.display_name
RETURNING customer_id, tenant_id, email, display_name;
```

`EXCLUDED.display_name` refers to the proposed row's value, while the existing row is updated per the `DO UPDATE` action.

**Note:** if `(tenant_id=10, email='an@example.com')` already exists, the proposed row's `customer_id=99` does not overwrite the existing PK unless you explicitly update the PK (which is usually discouraged). `RETURNING` outputs the final row resulting from the action.

### 12.4. Choosing the Right Conflict Target

You can specify columns:

```sql
ON CONFLICT (tenant_id, email)
DO UPDATE SET display_name = EXCLUDED.display_name
```

or a constraint name:

```sql
ON CONFLICT ON CONSTRAINT uq_customers_tenant_email
DO UPDATE SET display_name = EXCLUDED.display_name
```

**Choosing the right business key** is critical. Targeting only `customer_id` handles a PK collision while ignoring the tenant/email rule, or vice versa.

You must also handle other uniqueness errors: for instance, never assume every `23505` is a harmless conflict the application can ignore.

### 12.5. ON CONFLICT with a Partial Unique Index

When using a predicated unique index:

```sql
CREATE UNIQUE INDEX ux_active_membership
ON project_members(project_id, user_id)
WHERE deleted_at IS NULL;
```

you can specify the matching predicate in the conflict target so PostgreSQL infers the right arbiter:

```sql
INSERT INTO project_members
    (membership_id, project_id, user_id, deleted_at)
VALUES
    (101, 10, 20, NULL)
ON CONFLICT (project_id, user_id)
    WHERE deleted_at IS NULL
DO NOTHING;
```

This example assumes **the corresponding partial index already exists on the table**. Do not write `ON CONFLICT ON CONSTRAINT ux_active_membership` for a standalone unique index that is not backing a constraint: a standalone index name is **not a constraint name**.

Verify arbiter inference rules on your PostgreSQL version and check for any other matching indexes. If business logic distinguishes between an active membership and a soft-deleted one, test both cases with data.

## 13. Practice Lab: Creating the Schema and Data

This section uses a dedicated schema: `constraint_lab`.

### 13.1. Initialization

```sql
CREATE SCHEMA IF NOT EXISTS constraint_lab;
```

If the schema already exists from another run, do not drop it carelessly; use a clean lab database or choose another schema with the same structure.

### 13.2. tenants Table

```sql
CREATE TABLE constraint_lab.tenants (
    tenant_id BIGINT PRIMARY KEY,
    tenant_name TEXT NOT NULL UNIQUE
);
```

In this example `tenant_name` is marked unique to illustrate an alternate key. In real businesses, display names can collide, so a unique `tenant_code` is often used while allowing duplicate `tenant_name` values.

### 13.3. customers Table

```sql
CREATE TABLE constraint_lab.customers (
    customer_id BIGINT PRIMARY KEY,
    tenant_id BIGINT NOT NULL
        REFERENCES constraint_lab.tenants(tenant_id),
    email TEXT NOT NULL,
    display_name TEXT NOT NULL,
    CONSTRAINT uq_customers_tenant_email
        UNIQUE (tenant_id, email)
);
```

Rules:

- `customer_id` is a global customer ID in the lab dataset.
- `tenant_id` references an existing tenant.
- One tenant cannot have two customers with the same `email`.
- Two different tenants **can** use the same email.

This is **tenant-scoped** uniqueness, not system-wide uniqueness.

### 13.4. products Table with a Composite PRIMARY KEY

```sql
CREATE TABLE constraint_lab.products (
    tenant_id BIGINT NOT NULL
        REFERENCES constraint_lab.tenants(tenant_id),
    sku TEXT NOT NULL,
    product_name TEXT NOT NULL,
    price NUMERIC(12,2) NOT NULL CHECK (price >= 0),
    CONSTRAINT pk_products
        PRIMARY KEY (tenant_id, sku)
);
```

There is no global `product_id` column in this example. The `(tenant_id, sku)` key suffices to identify a product within the assumed business scope.

### 13.5. orders Table with a Nullable Alternate Key

```sql
CREATE TABLE constraint_lab.orders (
    order_id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL
        REFERENCES constraint_lab.customers(customer_id),
    external_ref TEXT,
    status TEXT NOT NULL
        CHECK (status IN ('NEW', 'PAID', 'CANCELLED')),
    amount NUMERIC(12,2) NOT NULL CHECK (amount >= 0),
    ordered_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_orders_customer_external
        UNIQUE (customer_id, external_ref)
);
```

`external_ref` may be NULL when an external source has not assigned one. Default uniqueness permits multiple orders for the same customer with `external_ref NULL`; **non-NULL** codes must be unique per customer.

### 13.6. addresses Table and Partial Unique Index

```sql
CREATE TABLE constraint_lab.customer_addresses (
    address_id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL
        REFERENCES constraint_lab.customers(customer_id),
    address_label TEXT NOT NULL,
    is_default BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE UNIQUE INDEX ux_customer_one_default_address
ON constraint_lab.customer_addresses (customer_id)
WHERE is_default;
```

Each customer can have many secondary addresses and at most one default address.

### 13.7. Loading Sample Data

```sql
INSERT INTO constraint_lab.tenants
    (tenant_id, tenant_name)
VALUES
    (10, 'Shop A'),
    (20, 'Shop B');

INSERT INTO constraint_lab.customers
    (customer_id, tenant_id, email, display_name)
VALUES
    (1, 10, 'an@example.com', 'Nguyen An'),
    (2, 10, 'binh@example.com', 'Tran Binh'),
    (3, 20, 'an@example.com', 'Nguyen An at Shop B');

INSERT INTO constraint_lab.products
    (tenant_id, sku, product_name, price)
VALUES
    (10, 'P-100', 'Keyboard', 350000),
    (10, 'P-101', 'Mouse', 150000),
    (20, 'P-100', 'Shop B Keyboard', 380000);

INSERT INTO constraint_lab.orders
    (order_id, customer_id, external_ref, status, amount)
VALUES
    (1001, 1, 'REQ-001', 'PAID', 350000),
    (1002, 1, NULL, 'NEW', 150000),
    (1003, 1, NULL, 'NEW', 250000),
    (1004, 2, 'REQ-001', 'PAID', 500000);

INSERT INTO constraint_lab.customer_addresses
    (address_id, customer_id, address_label, is_default)
VALUES
    (11, 1, 'Home', TRUE),
    (12, 1, 'Office', FALSE),
    (21, 2, 'Home', TRUE),
    (31, 3, 'Work', FALSE);
```

The sample data demonstrates:

- Two tenants can share SKU `P-100`.
- Two tenants can share email `an@example.com`.
- Two different customers can share `external_ref = 'REQ-001'`.
- One customer can have **multiple orders with `external_ref NULL`**.
- One customer can have multiple secondary addresses but only one default address.

IDs are explicitly specified for this exercise. In production systems, consider identity or UUIDs when an ID generation mechanism is needed instead of manual numbers.

## 14. Testing Valid and Violating Cases

### 14.1. Duplicate PRIMARY KEY

The statement below **will fail with `23505`** because tenant 10 already has a product with SKU `P-100`:

```sql
-- RUN SEPARATELY ONLY TO OBSERVE THE ERROR:
INSERT INTO constraint_lab.products
    (tenant_id, sku, product_name, price)
VALUES
    (10, 'P-100', 'New name', 400000);
```

However, tenant 20's SKU `P-100` exists independently without conflicting with tenant 10.

### 14.2. Tenant-Scoped UNIQUE

The statement below **will fail** because tenant 10 already has that email:

```sql
-- RUN SEPARATELY ONLY TO OBSERVE THE ERROR:
INSERT INTO constraint_lab.customers
    (customer_id, tenant_id, email, display_name)
VALUES
    (99, 10, 'an@example.com', 'Another customer');
```

The same email in tenant 20 does not conflict with `(10, 'an@example.com')`.

### 14.3. UNIQUE with Multiple NULLs

```sql
SELECT order_id, customer_id, external_ref
FROM constraint_lab.orders
WHERE customer_id = 1
ORDER BY order_id;
```

In the sample data, customer 1 has two orders with `external_ref IS NULL`; both are valid.

### 14.4. Violating a Partial Unique Index

```sql
-- RUN SEPARATELY ONLY TO OBSERVE THE ERROR:
INSERT INTO constraint_lab.customer_addresses
    (address_id, customer_id, address_label, is_default)
VALUES
    (13, 1, 'Second default address', TRUE);
```

The unique index on `customer_id WHERE is_default` blocks it because customer 1 already has address 11 as default.

Adding a secondary address:

```sql
BEGIN;

INSERT INTO constraint_lab.customer_addresses
    (address_id, customer_id, address_label, is_default)
VALUES
    (13, 1, 'Another secondary address', FALSE);

ROLLBACK;
```

is valid because `FALSE` falls outside the unique index predicate. `ROLLBACK` keeps the sample dataset clean for later sections.

### 14.5. Observing Errors Inside a Transaction

If you want to test a statement expected to fail while continuing a transaction, use `SAVEPOINT`:

```sql
BEGIN;

SAVEPOINT before_duplicate;

-- Run an INSERT expected to violate UNIQUE here.
-- After observing error 23505, execute:

ROLLBACK TO SAVEPOINT before_duplicate;

ROLLBACK;
```

Without `ROLLBACK TO SAVEPOINT` after a statement fails in a transaction, PostgreSQL places the current transaction into an **aborted** state and rejects subsequent statements until rollback. Do not paste a batch of error-testing commands into one script assuming the client will automatically continue every step.

## 15. Querying Metadata to Verify Existing Constraints

### 15.1. Listing PK/UNIQUE Constraints in the Schema

```sql
SELECT
    con.conrelid::regclass AS table_name,
    con.conname AS constraint_name,
    CASE con.contype
        WHEN 'p' THEN 'PRIMARY KEY'
        WHEN 'u' THEN 'UNIQUE'
        ELSE con.contype::text
    END AS constraint_type,
    con.conindid::regclass AS supporting_index,
    pg_get_constraintdef(con.oid, true) AS definition
FROM pg_constraint AS con
JOIN pg_namespace AS n
  ON n.oid = con.connamespace
WHERE n.nspname = 'constraint_lab'
  AND con.contype IN ('p', 'u')
ORDER BY table_name, constraint_name;
```

`supporting_index` shows which index backs the constraint. Standalone indexes—such as the partial index for default addresses—must be viewed separately via `pg_indexes`.

### 15.2. Listing All Indexes

```sql
SELECT
    tablename,
    indexname,
    indexdef
FROM pg_indexes
WHERE schemaname = 'constraint_lab'
ORDER BY tablename, indexname;
```

A useful verification exercise:

1. Find the index for `pk_products`.
2. Find the index for `uq_customers_tenant_email`.
3. Find `ux_customer_one_default_address` and its `WHERE is_default` predicate.
4. Compare which indexes were **created by constraints** and which were **created directly**.

### 15.3. information_schema

```sql
SELECT
    table_schema,
    table_name,
    constraint_name,
    constraint_type
FROM information_schema.table_constraints
WHERE table_schema = 'constraint_lab'
  AND constraint_type IN ('PRIMARY KEY', 'UNIQUE')
ORDER BY table_name, constraint_name;
```

`information_schema` provides a SQL-standard metadata interface; `pg_catalog` and `pg_indexes` expose richer PostgreSQL-specific details, especially expression and partial indexes.

### 15.4. psql and pgAdmin

In `psql`:

```text
\d+ constraint_lab.products
\d+ constraint_lab.customers
\di constraint_lab.*
```

These are **`psql` meta-commands**, not SQL statements to send verbatim over JDBC or pgAdmin Query Tool. In pgAdmin, inspect the **Constraints**, **Indexes**, and table SQL/DDL tabs.

## 16. EXPLAIN: Are Supporting Constraint Indexes Used for Reads?

### 16.1. Inspecting a PK Lookup Query

```sql
EXPLAIN
SELECT tenant_id, sku, product_name, price
FROM constraint_lab.products
WHERE tenant_id = 10
  AND sku = 'P-100';
```

The planner **may** choose the index on `(tenant_id, sku)` or a `Seq Scan` depending on table size, data distribution, and cost estimates. On a table with just a few rows, a sequential scan is usually cheapest.

Never conclude from seeing `Seq Scan` that a PK is inactive: **write-time uniqueness enforcement** and **read execution plans** are two separate functions.

### 16.2. EXPLAIN ANALYZE and BUFFERS

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT tenant_id, sku, product_name, price
FROM constraint_lab.products
WHERE tenant_id = 10
  AND sku = 'P-100';
```

`EXPLAIN ANALYZE` **actually executes the SELECT query** to measure runtime metrics. Inspect:

- `actual time` and `actual rows`.
- `loops` per node.
- Buffer hits and reads.
- Discrepancies between estimated and actual `rows`.
- Presence or absence of `Index Scan` / `Index Only Scan`.

On a tiny sample table, millisecond timings **do not predict** behavior at millions of rows. To evaluate index performance, benchmark on representative data volumes and realistic filter predicates.

### 16.3. A Unique Index Does Not Guarantee Index Only Scan

Even when a query selects only columns present in the index, PostgreSQL must still respect **MVCC visibility**. An `Index Only Scan` may fall back to heap fetches if the Visibility Map has not marked pages all-visible; check `Heap Fetches` in the plan.

Therefore, never assume an index covering all selected columns always avoids table page reads.

### 16.4. Inspecting Index Usage Statistics

```sql
SELECT
    schemaname,
    relname,
    indexrelname,
    idx_scan,
    idx_tup_read,
    idx_tup_fetch
FROM pg_stat_user_indexes
WHERE schemaname = 'constraint_lab'
ORDER BY relname, indexrelname;
```

These counters are **cumulative statistics since server start or stats reset**, not metrics from a single query, and have interpretation caveats. A unique index with low `idx_scan` can still be essential for **enforcing uniqueness on writes**.

**Never drop a unique index merely because `idx_scan` is low.**

## 17. Adding PRIMARY KEY or UNIQUE to a Table with Existing Data

A large table may initially lack constraints. Adding constraints in production takes more steps than a single `ALTER TABLE` command.

### 17.1. Check for Duplicates First

Suppose a table `legacy_customers(tenant_id, email, ...)` already exists:

```sql
SELECT
    tenant_id,
    email,
    COUNT(*) AS duplicate_count
FROM legacy_customers
GROUP BY tenant_id, email
HAVING COUNT(*) > 1
ORDER BY duplicate_count DESC, tenant_id, email;
```

This is an illustrative query—run it only when the real table exists. On large datasets, `GROUP BY` itself can be resource-intensive.

If key columns must also be non-NULL:

```sql
SELECT COUNT(*) AS null_keys
FROM legacy_customers
WHERE tenant_id IS NULL
   OR email IS NULL;
```

With `UNIQUE NULLS NOT DISTINCT`, duplicate checks must also handle NULL groups per target semantics. For `PRIMARY KEY`, every key column must be **non-NULL**.

You cannot “fix” duplicates using `MAX(id)`, `DISTINCT`, or blindly deleting rows without knowing which record is the source of truth. You need a business-approved merge/deduplication policy.

### 17.2. Adding the Constraint Directly

Example:

```sql
ALTER TABLE legacy_customers
ADD CONSTRAINT uq_legacy_tenant_email
UNIQUE (tenant_id, email);
```

PostgreSQL must verify uniqueness and build the supporting index. On large tables, this can incur heavy scan time, locking, and I/O load. Never assume this DDL is “online and non-blocking”.

### 17.3. Creating an Index Concurrently and Attaching the Constraint

For large tables, a commonly considered strategy is:

```sql
CREATE UNIQUE INDEX CONCURRENTLY
    ux_legacy_tenant_email
ON legacy_customers (tenant_id, email);
```

Once created **successfully and validly**, an eligible index can be attached as a constraint:

```sql
ALTER TABLE legacy_customers
ADD CONSTRAINT uq_legacy_tenant_email
UNIQUE USING INDEX ux_legacy_tenant_email;
```

Requirements when using `USING INDEX`:

- The index must be a valid **unique** B-tree index meeting structural requirements.
- It must **not** be a partial index or expression index.
- Sort order and access method properties must satisfy PostgreSQL's constraint requirements.
- `ALTER TABLE` can still acquire locks and have a brief but noticeable impact during peak load.
- Once attached, the constraint takes ownership of the index under PostgreSQL's catalog rules.

`CREATE INDEX CONCURRENTLY` cannot run inside an ordinary transaction block. Adding a **`PRIMARY KEY`** via `USING INDEX` also requires key columns to be `NOT NULL`; if they are not yet `NOT NULL`, PostgreSQL may need additional verification or alteration steps with lock and scan impact.

### 17.4. When CREATE UNIQUE INDEX CONCURRENTLY Fails

Common causes:

- Existing data already contains duplicates.
- A concurrent transaction inserts duplicates during the build.
- Resource errors, deadlocks, or canceled jobs.
- Conflicting schema changes occurring during the build.

A failed concurrent index build **can leave behind an `INVALID` index**. Notably, depending on the phase where it failed, an invalid unique index may still participate in uniqueness enforcement on writes in certain cases—never assume it is harmless.

Inspect:

```sql
SELECT
    indexrelid::regclass AS index_name,
    indisvalid,
    indisready,
    indisunique
FROM pg_index
WHERE indrelid = 'legacy_customers'::regclass;
```

If an invalid index exists, follow a runbook: identify the cause, check whether the index is active on writes, decide on **dropping/rebuilding concurrently**, and verify afterward. Never drop a production index without verifying whether it backs a constraint or serves another workload.

### 17.5. NOT VALID Does Not Apply Arbitrarily to UNIQUE

PostgreSQL supports `NOT VALID` / `VALIDATE CONSTRAINT` workflows for **certain constraint types** such as foreign keys and check constraints. Do not assume you can add an arbitrary `UNIQUE NOT VALID` constraint and validate it later the way FKs work: PostgreSQL does not support that workflow as a general option for unique constraints.

For uniqueness on large tables, use `CREATE UNIQUE INDEX CONCURRENTLY` when appropriate.

## 18. Concurrency, Locks, and Write Correctness

### 18.1. Why Does UNIQUE Prevent Race Conditions?

Suppose two transactions concurrently insert the same email:

```text
T1: INSERT (tenant=10, email='new@example.com')
T2: INSERT (tenant=10, email='new@example.com')
```

PostgreSQL guarantees that two rows **violating uniqueness** cannot both commit under constraint semantics. One transaction may block waiting for the other and then fail with a uniqueness error, or route to `ON CONFLICT` depending on the statement.

Crucially, correctness is enforced at the **database boundary**, regardless of what either request read beforehand.

### 18.2. Do Not Treat Unique Constraints as a Universal Business Lock

`UNIQUE` protects against **duplicate key values**. It does not automatically enforce:

- Non-negative total inventory across multiple rows.
- Remaining seat capacity under a seat-allocation algorithm.
- At most N orders per customer per day.
- Non-overlapping booking intervals when the scope is a **time range**.

Such rules may require conditional updates, transactions, isolation levels, exclusion constraints, or other concurrency mechanisms.

For instance, “no two overlapping room bookings” fits an **exclusion constraint** on a range type rather than `UNIQUE` on a simple timestamp pair.

### 18.3. Locks and Migrations

Changing constraints or indexes on large tables can interact with long-running write transactions. Monitor:

- DDL execution duration.
- Lock waits and blocked sessions.
- CPU, I/O, WAL generation, and replication lag.
- Application connection pools and error rates.
- Other concurrent index builds or maintenance jobs.

`CREATE INDEX CONCURRENTLY` reduces certain write-blocking locks compared to regular index creation, but it is **neither free nor wait-free**. It still interacts with active transactions and performs full table scans.

## 19. UNIQUE and Partitioned Tables

PostgreSQL supports declarative partitioning, but uniqueness across partitions has important limitations.

### 19.1. Tenant-Partitioned Table Example

```sql
CREATE TABLE partitioned_products (
    tenant_id BIGINT NOT NULL,
    sku TEXT NOT NULL,
    product_name TEXT NOT NULL,
    PRIMARY KEY (tenant_id, sku)
) PARTITION BY LIST (tenant_id);
```

The PK includes `tenant_id`, which is the **partition key**, satisfying the general requirement for declaring PK/UNIQUE on a partitioned table.

### 19.2. Why Must the Key Contain the Partition Key?

PostgreSQL uses per-partition indexes in many cases rather than a single global unique index spanning all partitions the way applications might assume.

To enforce uniqueness across partitions, `PRIMARY KEY` / `UNIQUE` constraints declared on a partitioned parent must contain **all partition key columns** per PostgreSQL's rules; partitioning with expressions/functions further restricts constraint keys.

If a table is partitioned by `tenant_id`, `UNIQUE (sku)` on the **parent** cannot enforce global SKU uniqueness across all tenants/partitions through that key mechanism. If global SKU uniqueness is truly required, reconsider the **partitioning strategy, key design, or uniqueness enforcement approach**.

### 19.3. Date Partitioning and Order Keys

A system partitioning `orders` by `created_at` may want `order_id` to be globally unique. However, declaring `PRIMARY KEY (order_id)` alone on a parent partitioned by `created_at` does not behave like a simple global PK on an unpartitioned heap table.

You may need a key including the partition key, a global ID generator combined with external checks, or a different partition key axis. **A sequence generating new IDs is not by itself absolute proof of uniqueness across all partitions.**

Separate **business rules** from **storage/partition layout capabilities** before choosing a partition key.

## 20. Distinguishing UNIQUE from Easily Confused Concepts

| Concept | What It Protects | What It Does Not Automatically Protect |
|---|---|---|
| `PRIMARY KEY` | Non-NULL, non-duplicate primary key | Other business keys unless separately constrained |
| `UNIQUE` | Uniqueness of key columns per NULL semantics | Whether a referenced value exists in another table |
| `UNIQUE NULLS NOT DISTINCT` | Uniqueness treating NULLs as non-distinct | Requiring all columns to be non-NULL |
| `UNIQUE INDEX ... WHERE` | Uniqueness restricted to rows matching predicate | Rows outside the predicate; “must have at least one” |
| `UNIQUE INDEX(lower(email))` | Uniqueness of the normalized expression | Business validity of email formats |
| `FOREIGN KEY` | Referenced key exists in parent | Uniqueness in child table if a 1:1 relation is desired |
| `CHECK` | Per-row expression per SQL semantics | Multi-row global rules |
| Non-unique `INDEX` | Data access path | Uniqueness |
| `ON CONFLICT` | Handling INSERT collisions on matching arbiter | Other business errors or conflicts on other constraints |

### 20.1. “At Most One” vs. “Exactly One”

`UNIQUE (customer_id)` on a secondary profile table guarantees at most **one profile** per customer. It does not force **every customer** to have a profile.

Similarly, partial unique index `WHERE is_default` ensures at most one default address, not that a default address always exists.

If the rule is “every customer **must have** one default address”, you need an additional mechanism maintaining existence and referential consistency, typically with coordinated constraints and transactions.

### 20.2. Uniqueness Does Not Mean Format Validity

```sql
UNIQUE (email)
```

does not verify that `email` contains `@`, that the domain exists, or that the user owns the address. Those belong to separate rules.

### 20.3. Case Sensitivity and Collations

Depending on data type and collation, string comparisons can behave differently. Do not assume `UNIQUE(TEXT)` always treats `An@X` and `an@x` as identical, nor assume every environment shares identical collation semantics.

If business rules require case-insensitivity, choose an explicit **normalization/comparison policy** and test it on your exact database version and collation.

### 20.4. A PK Does Not Guarantee SELECT Ordering

A B-tree index maintains key order, yet:

```sql
SELECT * FROM constraint_lab.products;
```

without `ORDER BY` has **no SQL-guaranteed result order**.

If the UI requires ordering:

```sql
SELECT *
FROM constraint_lab.products
ORDER BY tenant_id, sku;
```

Always write `ORDER BY` explicitly; never rely on the table having a PK.

## 21. Practical Constraint Design Workflow

~~~mermaid
flowchart TD
    A["Identify entities and business keys"] --> B["Choose a stable, non-NULL PK"]
    B --> C["List alternate unique rules"]
    C --> D["Determine tenant scope and NULL semantics"]
    D --> E{"Does uniqueness apply to all rows?"}
    E -- "Yes" --> F["UNIQUE constraint / PK"]
    E -- "No" --> G["Partial unique index"]
    F --> H{"Normalized expression needed?"}
    G --> H
    H -- "Yes" --> I["Expression unique index, verify data"]
    H -- "No" --> J["Add matching constraints and indexes"]
    I --> J
    J --> K["Design FKs and referencing-side indexes"]
    K --> L["Test duplicates/NULLs and concurrency"]
    L --> M["Staging migration + EXPLAIN + rollback"]
~~~

Before adding a unique rule, ask:

1. What is each row's **primary identifier**?
2. Does the rule apply **globally, per tenant, or per time period**?
3. Can the key be **NULL or unassigned**?
4. If nullable, should multiple rows with NULL be allowed?
5. Does uniqueness apply only to `active`, `deleted_at IS NULL`, or specific statuses?
6. Do we need uniqueness on a **normalized expression** like `lower(email)`?
7. Must this key act as an **FK target**?
8. Does any transaction need to violate uniqueness temporarily and restore it before commit?
9. Does existing data contain duplicates or edge cases?
10. Will the resulting index help common queries or duplicate another index?

## 22. Common Design Mistakes

### 22.1. Using UNIQUE on an Unstable Business Key

Applying `UNIQUE(full_name)` to customers blocks different people who share the same name. Choose proper keys and enforce real invariants.

### 22.2. Forgetting tenant_id in a Unique Key

If email only needs to be unique **within a tenant**, a table-wide `UNIQUE(email)` blocks the same email in another tenant. Use `UNIQUE(tenant_id, email)`.

### 22.3. Confusing Composite UNIQUE with Two Separate UNIQUEs

`UNIQUE(a, b)` does not mean `a` or `b` is individually unique. Declare two separate single-column unique constraints if each column truly must be unique on its own.

### 22.4. Overlooking NULLs in UNIQUE

`UNIQUE(external_ref)` permits multiple NULLs by default. Choose `NOT NULL` or `NULLS NOT DISTINCT` deliberately per policy rather than by accident.

### 22.5. Creating a Regular Index Thinking It Prevents Duplicates

`CREATE INDEX` is **not** `CREATE UNIQUE INDEX`. A lookup index creates no uniqueness invariant.

### 22.6. Using a Partial Unique Index as an FK Target

A partial index does not enforce uniqueness over the entire table, so it cannot serve as a standard FK target. Use a proper PK or full unique key as the identifier.

### 22.7. Missing Indexes on Child FK Columns

PostgreSQL does not automatically index child FK columns. Deleting or updating parent keys can trigger expensive child scans; evaluate child-side indexes based on workload.

### 22.8. Using ON CONFLICT DO NOTHING to Mask Business Errors

If a customer needs to know an email is already taken, silently ignoring the conflict causes broken UX and lost input.

### 22.9. Keeping Redundant Indexes on Identical Keys

Constraints already create supporting indexes. Add another index only with concrete evidence regarding predicates, covering columns, key order, workload, or specific query needs.

### 22.10. Adding Unique Constraints to Dirty Tables Without Checking Duplicates

The command will fail after potentially consuming heavy I/O and locks. Audit, clean up, and test on representative data first.

### 22.11. Treating CONCURRENTLY as Zero-Impact

`CREATE UNIQUE INDEX CONCURRENTLY` still reads the table, writes WAL, consumes CPU/I/O, and may wait on active transactions. If it fails, it can leave an invalid index requiring cleanup.

### 22.12. Mixing Up DEFERRABLE with Upserts

Deferrable unique constraints help with row swapping, but cannot serve as arbiters for `ON CONFLICT DO UPDATE`. Choose constraint semantics based on actual write patterns.

### 22.13. Forgetting the Partition Key in UNIQUE on Partitioned Tables

A PK or unique constraint on a partitioned parent must satisfy partition-key inclusion rules. Never assume a single global unique index exists as on a standalone heap table.

### 22.14. Dropping a Unique Index Because idx_scan Is Low

The index may exist primarily to enforce **uniqueness on writes**. Low scan counts alone do not make it unused.

## 23. Practice Exercises

Use the `constraint_lab` schema from Section 13. Exercises expected to raise errors should be run separately in the lab, using transactions/savepoints if you want to preserve sample data.

### Exercise 1 — PRIMARY KEY or UNIQUE?

Table `employees(employee_id, employee_code, full_name)` requires both ID and employee code to be unique and non-NULL; `employee_id` is the API identifier. Write the DDL and explain the choice of PK vs. alternate key.

### Exercise 2 — Tenant-Scoped Key

A SKU may be reused across different tenants but cannot duplicate within the same tenant. Write the constraint and identify which pairs are valid:

```text
(tenant=1,sku=A)
(tenant=2,sku=A)
(tenant=1,sku=B)
(tenant=1,sku=A)
```

### Exercise 3 — NULL in UNIQUE

`orders(customer_id, external_ref)` has `UNIQUE(customer_id, external_ref)` with nullable `external_ref`. Can `(1, NULL)` appear twice? How does behavior change with `NULLS NOT DISTINCT`?

### Exercise 4 — Partial Unique Index

Design an addresses table allowing a customer to have multiple addresses but at most one with `is_default = TRUE`. Why is `UNIQUE(customer_id, is_default)` wrong? Write the replacement index.

### Exercise 5 — Case-Insensitive Email

Table `users(user_id, email)` has non-NULL emails. Write a unique expression index on `lower(btrim(email))`. How do you check for duplicates before creating it?

### Exercise 6 — Foreign Keys and Child Indexes

`authors(author_id PRIMARY KEY)` and `books(book_id PRIMARY KEY, author_id REFERENCES authors)`. Which indexes does PostgreSQL create automatically? For frequent `WHERE author_id = ?` queries, what index should you consider?

### Exercise 7 — Reading the Catalog

Write SQL to list PK/UNIQUE constraint names and their supporting index names in `constraint_lab`. Why is `ux_customer_one_default_address` not listed among `pg_constraint` PK/UNIQUE entries?

### Exercise 8 — ON CONFLICT

Write an upsert for `customers` on `(tenant_id, email)` that updates `display_name` on conflict and returns `customer_id`. What happens to the proposed ID if a conflict matches an existing customer?

### Exercise 9 — DEFERRABLE

Two guests sit in seats 1 and 2 in the same session. You need to swap their seats with an `UPDATE` without failing on temporary duplicate values. What constraint design fits? Why is it unsuitable for `ON CONFLICT`?

### Exercise 10 — Duplicates Before Migration

Table `legacy_customers` has 10 million rows and no unique key yet. Write SQL to find duplicate `(tenant_id, email)` pairs and outline a plan to add the unique constraint with controlled write impact.

### Exercise 11 — INCLUDE and Uniqueness

A unique index has key `(tenant_id, sku)` and `INCLUDE(product_name)`. Can two rows have the same `(tenant_id, sku)` with different `product_name` values? Why or why not?

### Exercise 12 — PARTITION BY RANGE

Table `orders` is partitioned by `created_at`, and the application wants `PRIMARY KEY(order_id)` globally unique across all partitions. Explain the limitation and design options to consider.

### Exercise 13 — Read Plans vs. Write Protection

A 20-row table shows `Seq Scan` for a PK lookup query. Can you conclude the PK index is missing or inactive? Explain how to verify via catalogs and an intentionally violating write test.

### Exercise 14 — Writing a Design Decision

A table has `membership_id`, `project_id`, `user_id`, `deleted_at`. Requirement: each `(project_id, user_id)` pair can have at most one non-deleted membership, while retaining many historical soft-deleted memberships. Choose the PK and uniqueness rule, and explain the consequence when restoring an old record.

## 24. Suggested Solutions

### Exercise 1

```sql
CREATE TABLE employees (
    employee_id BIGINT PRIMARY KEY,
    employee_code TEXT NOT NULL UNIQUE,
    full_name TEXT NOT NULL
);
```

`employee_id` is the PK as the API identifier; `employee_code` is the alternate key per business rules. Both keys are non-NULL and unique.

### Exercise 2

```sql
UNIQUE (tenant_id, sku)
```

The first three pairs are valid; the fourth duplicates `(1, 'A')` and violates the constraint. You can use `PRIMARY KEY (tenant_id, sku)` if it is the primary identifier and both columns are non-NULL.

### Exercise 3

Under default uniqueness, two `(1, NULL)` rows can coexist. With:

```sql
UNIQUE NULLS NOT DISTINCT (customer_id, external_ref)
```

only one `(1, NULL)` row is allowed, while `(2, NULL)` is a distinct key.

### Exercise 4

`UNIQUE(customer_id, is_default)` also blocks two `FALSE` secondary addresses for the same customer. You need:

```sql
CREATE UNIQUE INDEX ux_one_default
ON customer_addresses(customer_id)
WHERE is_default;
```

This enforces **at most one**, not **required to have one**.

### Exercise 5

```sql
CREATE UNIQUE INDEX ux_users_email_normalized
ON users (lower(btrim(email)));
```

Pre-check:

```sql
SELECT
    lower(btrim(email)) AS normalized_email,
    COUNT(*) AS duplicates
FROM users
GROUP BY lower(btrim(email))
HAVING COUNT(*) > 1;
```

Verify normalization rules, collation, and any NULL values.

### Exercise 6

PostgreSQL creates indexes for `authors(author_id PRIMARY KEY)` and `books(book_id PRIMARY KEY)`, but **does not automatically** index `books.author_id` just for the FK. Consider:

```sql
CREATE INDEX ix_books_author
ON books(author_id);
```

if queries by author or parent-table updates/deletes show it is needed.

### Exercise 7

```sql
SELECT
    con.conrelid::regclass AS table_name,
    con.conname,
    con.conindid::regclass AS index_name,
    pg_get_constraintdef(con.oid) AS definition
FROM pg_constraint AS con
JOIN pg_namespace AS n
  ON n.oid = con.connamespace
WHERE n.nspname = 'constraint_lab'
  AND con.contype IN ('p','u');
```

The partial unique index was created directly as an index, so it does not automatically have a corresponding `UNIQUE` constraint entry in `pg_constraint`.

### Exercise 8

```sql
INSERT INTO constraint_lab.customers
    (customer_id,tenant_id,email,display_name)
VALUES
    (99,10,'an@example.com','New name')
ON CONFLICT ON CONSTRAINT uq_customers_tenant_email
DO UPDATE SET display_name = EXCLUDED.display_name
RETURNING customer_id;
```

On conflict with an existing customer, `RETURNING customer_id` returns the ID of the existing row that was updated. The proposed ID 99 does not overwrite the existing key.

### Exercise 9

```sql
UNIQUE (session_id, seat_no) DEFERRABLE INITIALLY DEFERRED
```

allows swapping seats within a transaction provided the final state is valid. Deferrable unique constraints cannot serve as arbiters for `ON CONFLICT DO UPDATE`.

### Exercise 10

```sql
SELECT tenant_id, email, COUNT(*) AS duplicate_count
FROM legacy_customers
GROUP BY tenant_id, email
HAVING COUNT(*) > 1;
```

After resolving duplicates and NULLs per business rules, you can run `CREATE UNIQUE INDEX CONCURRENTLY` in controlled staging/production, verify the index is valid, and run `ALTER TABLE ... ADD CONSTRAINT ... USING INDEX` if eligible. Monitor locks, WAL, I/O, failures, and rollback steps.

### Exercise 11

No. Uniqueness is determined solely by the **key columns** `(tenant_id, sku)`; `INCLUDE` columns carry extra payload inside the index and do not participate in uniqueness checks.

### Exercise 12

PostgreSQL requires PK/UNIQUE constraints on a partitioned parent to include the partition key. When partitioned by `created_at`, a PK on `order_id` alone is not supported as a global unique key. Options include adding the partition key to the key, changing the partitioning axis, or using a global ID mechanism with corresponding constraint trade-offs.

### Exercise 13

No. `Seq Scan` is the planner's choice for small datasets. Use `pg_constraint`, `pg_indexes`, and `pg_index` to verify the PK and index; an intentional duplicate `INSERT` test in the lab will raise `23505` even if `SELECT` plans use `Seq Scan`.

### Exercise 14

```sql
membership_id BIGINT PRIMARY KEY
```

and:

```sql
CREATE UNIQUE INDEX ux_membership_active
ON project_members(project_id,user_id)
WHERE deleted_at IS NULL;
```

Soft-deleted rows fall outside the index; restoring an old row will conflict if a new active membership already exists for the same pair.

## 25. Conclusion

`PRIMARY KEY` and `UNIQUE` define core PostgreSQL data invariants. A PK is a **non-NULL, non-duplicate** primary identifier; `UNIQUE` protects business or alternate keys according to column scope and NULL rules. PostgreSQL normally creates a **unique B-tree index** to enforce these constraints and assist certain read queries, yet **correctness enforcement** and **read plan selection** must be evaluated separately.

As business rules grow more nuanced, pick the right mechanism:

- **`UNIQUE (tenant_id, sku)`** for tenant-scoped uniqueness.
- **`UNIQUE NULLS NOT DISTINCT`** when NULLs should also count as duplicates.
- **Expression unique index** for normalized keys such as `lower(email)`.
- **Partial unique index** for active rows or single default addresses.
- **DEFERRABLE constraints** when a transaction must temporarily pass through conflicting states before commit.
- **`ON CONFLICT`** to handle concurrent writes safely using the right arbiter.
- **FKs and child-side indexes** to protect references and support lookups/checks.

A durable workflow is: **define business rule → choose keys and NULL semantics → enforce with proper constraint/index → audit existing data → deploy safely → measure workload and monitor after rollout**. An index is truly valuable only when it serves real query needs while keeping data consistent at an acceptable operational cost.
