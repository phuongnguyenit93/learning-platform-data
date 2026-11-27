# Inspecting structure with information_schema and pg_catalog in PostgreSQL

When taking over an unfamiliar PostgreSQL database, the first question is rarely "how many rows are in this table?" but rather **"what objects exist in the system, how are they defined, and how do they relate to one another?"**. Developers need to know whether a column allows `NULL`, which table a foreign key points to, whether an index is valid, which query defines a view, or why a table with the same name appears in another schema.

PostgreSQL provides two particularly useful metadata sources:

- **`information_schema`**: a set of SQL-standard views offering relatively portable structural inspection across relational database management systems.
- **`pg_catalog`**: PostgreSQL-specific system catalogs and views storing granular details that `information_schema` may omit, such as object OIDs, expression indexes, internal constraints, index validity states, partitions, and storage sizes.

This lesson guides you through inspecting schemas, tables, and columns down to primary keys, foreign keys, indexes, views, sequences, and privileges; explains joining system catalogs using **OIDs** and **column attribute numbers (`attnum`)**; and highlights caveats regarding metadata visibility permissions, PostgreSQL versions, and specialized objects. Examples apply to modern PostgreSQL (largely version 12 and above) and use a dedicated practice schema to avoid affecting real data.

## 1. What is metadata? How does it differ from business data?

Suppose the system has a table `sales.orders`:

~~~sql
SELECT order_id, order_code, status
FROM sales.orders;
~~~

The query above reads **business data** for orders. If instead you want to know which columns `orders` has, what type `status` is, or whether `order_code` is unique, you need to inspect **metadata**.

| Information | Example | Category |
| --- | --- | --- |
| A specific order | `SO-001` with status `PAID` | Business data |
| Column name | `order_code` | Metadata |
| Column type | `TEXT`, `TIMESTAMPTZ`, `NUMERIC(12,2)` | Metadata |
| Primary key | `orders_pkey` | Metadata |
| Relationship | `orders.customer_id` references `customers.customer_id` | Metadata |
| Index | Index on customer and order date | Metadata |
| Owner/privileges | Which role holds `SELECT` or `UPDATE` | Metadata/administration |
| Row estimate | `pg_class.reltuples` | Estimated statistic, not exact row count |

In PostgreSQL, metadata for most objects is stored in **system catalogs**. Views in `information_schema` or convenient views like `pg_catalog.pg_tables` generally pull information from these catalogs and present it in a readable format.

~~~mermaid
flowchart TD
    D["DDL: CREATE TABLE / INDEX / VIEW"] --> C["PostgreSQL system catalogs<br/>pg_class, pg_attribute, pg_constraint..."]
    C --> I["information_schema<br/>SQL-standard views"]
    C --> P["pg_catalog views and functions"]
    I --> A["Applications / basic schema inspection tools"]
    P --> B["Administration / PostgreSQL-specific introspection"]
~~~

Never directly modify data inside system catalog tables using `INSERT`, `UPDATE`, or `DELETE`. Structural changes must go through PostgreSQL-supported DDL so the server updates metadata, dependencies, locks, and internal caches properly.

## 2. Preparing an example schema for metadata queries

We create schema `meta_lab` with four tables: customers, products, orders, and order items, plus one index and one view. This DDL ensures the metadata queries in subsequent sections return meaningful results.

**Run only in a learning/empty database you are authorized to manage.** If a schema named `meta_lab` already exists from another exercise, pick a new name and update the queries accordingly; never drop objects of unknown origin.

### 2.1. Creating the schema, tables, and constraints

~~~sql
CREATE SCHEMA meta_lab;

CREATE TABLE meta_lab.customers (
    customer_id BIGINT GENERATED ALWAYS AS IDENTITY,
    customer_code TEXT NOT NULL,
    email TEXT NOT NULL,
    full_name TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT customers_pk PRIMARY KEY (customer_id),
    CONSTRAINT customers_code_uq UNIQUE (customer_code),
    CONSTRAINT customers_email_uq UNIQUE (email),
    CONSTRAINT customers_name_check
        CHECK (length(btrim(full_name)) > 0)
);

CREATE TABLE meta_lab.products (
    product_id BIGINT GENERATED ALWAYS AS IDENTITY,
    sku TEXT NOT NULL,
    product_name TEXT NOT NULL,
    list_price NUMERIC(12, 2) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,

    CONSTRAINT products_pk PRIMARY KEY (product_id),
    CONSTRAINT products_sku_uq UNIQUE (sku),
    CONSTRAINT products_price_check CHECK (list_price > 0)
);

CREATE TABLE meta_lab.orders (
    order_id BIGINT GENERATED ALWAYS AS IDENTITY,
    order_code TEXT NOT NULL,
    customer_id BIGINT NOT NULL,
    ordered_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    status TEXT NOT NULL DEFAULT 'NEW',

    CONSTRAINT orders_pk PRIMARY KEY (order_id),
    CONSTRAINT orders_code_uq UNIQUE (order_code),
    CONSTRAINT orders_customer_fk
        FOREIGN KEY (customer_id)
        REFERENCES meta_lab.customers (customer_id)
        ON DELETE RESTRICT,
    CONSTRAINT orders_status_check
        CHECK (status IN ('NEW', 'PAID', 'CANCELLED'))
);

CREATE TABLE meta_lab.order_items (
    order_id BIGINT NOT NULL,
    product_id BIGINT NOT NULL,
    quantity INTEGER NOT NULL,
    unit_price NUMERIC(12, 2) NOT NULL,

    CONSTRAINT order_items_pk
        PRIMARY KEY (order_id, product_id),
    CONSTRAINT items_order_fk
        FOREIGN KEY (order_id)
        REFERENCES meta_lab.orders (order_id),
    CONSTRAINT items_product_fk
        FOREIGN KEY (product_id)
        REFERENCES meta_lab.products (product_id),
    CONSTRAINT items_quantity_check CHECK (quantity > 0),
    CONSTRAINT items_price_check CHECK (unit_price > 0)
);

CREATE INDEX idx_orders_customer_time
    ON meta_lab.orders (customer_id, ordered_at DESC);
~~~

This design demonstrates:

- `customers` and `products` are parent tables in business relationships.
- `orders.customer_id` references the primary key of `customers`.
- `order_items` uses a **composite primary key** `(order_id, product_id)`.
- `UNIQUE`, `CHECK`, and `FOREIGN KEY` constraints are explicitly named.
- `orders.order_id` uses `IDENTITY`, so PostgreSQL maintains an associated sequence to issue IDs.
- Index `idx_orders_customer_time` lets us observe metadata for an index **not created solely to enforce a primary key or unique key**.

### 2.2. Creating a view and object comments

~~~sql
CREATE VIEW meta_lab.v_order_summary AS
SELECT
    o.order_id,
    o.order_code,
    c.customer_code,
    o.status,
    COALESCE(
        SUM(oi.quantity * oi.unit_price),
        0::numeric
    ) AS order_total
FROM meta_lab.orders AS o
JOIN meta_lab.customers AS c
    ON c.customer_id = o.customer_id
LEFT JOIN meta_lab.order_items AS oi
    ON oi.order_id = o.order_id
GROUP BY
    o.order_id, o.order_code, c.customer_code, o.status;

COMMENT ON TABLE meta_lab.orders IS
    'Practice orders table for demonstrating PostgreSQL metadata.';

COMMENT ON COLUMN meta_lab.orders.order_code IS
    'Unique business code of the order.';
~~~

The view demonstrates that metadata describes more than physical tables. `COMMENT` attaches descriptive text queryable via catalogs. This summary view should not be treated as an independent physical table storing data automatically; it represents a query.

### 2.3. Inserting a few rows to contrast data and structure

~~~sql
INSERT INTO meta_lab.customers (customer_code, email, full_name)
VALUES
    ('C001', 'an@example.test', 'Nguyễn An'),
    ('C002', 'binh@example.test', 'Trần Bình');

INSERT INTO meta_lab.products
    (sku, product_name, list_price)
VALUES
    ('BOOK-001', 'PostgreSQL Book', 150000.00),
    ('PEN-001', 'Blue Pen',        20000.00);

INSERT INTO meta_lab.orders
    (order_code, customer_id, status)
SELECT
    'SO-001', customer_id, 'PAID'
FROM meta_lab.customers
WHERE customer_code = 'C001';

INSERT INTO meta_lab.order_items
    (order_id, product_id, quantity, unit_price)
SELECT
    o.order_id, p.product_id, 2, 150000.00
FROM meta_lab.orders AS o
CROSS JOIN meta_lab.products AS p
WHERE o.order_code = 'SO-001'
  AND p.sku = 'BOOK-001';
~~~

The **metadata** queries in the following sections do not require rows to be loaded. The seed rows simply help contrast `COUNT(*)` reading actual rows against estimated statistics in system catalogs. With the seed above, `meta_lab.v_order_summary` returns one row with an order total of `300000.00`.

## 3. Starting with the current environment and search_path

Before querying catalogs, confirm **which database you are connected to, under which role, and which search schemas are active**.

~~~sql
SELECT
    current_database() AS database_name,
    current_user AS current_role,
    current_schema() AS first_schema,
    current_setting('search_path') AS search_path_text,
    current_schemas(TRUE) AS resolved_schemas;
~~~

`search_path` determines how PostgreSQL resolves object names **without a schema prefix**. For instance, if multiple schemas have an `orders` table:

~~~sql
SELECT * FROM orders;
~~~

may resolve to different objects depending on the search path, whereas:

~~~sql
SELECT * FROM meta_lab.orders;
~~~

explicitly specifies the table in `meta_lab`. For metadata analysis tools, migrations, or code generators, always **filter by qualified schema name** rather than relying on an arbitrary `search_path`.

### 3.1. Checking if an object exists without throwing an error

~~~sql
SELECT
    to_regclass('meta_lab.orders') AS orders_object,
    to_regclass('meta_lab.unknown_table') AS missing_object;
~~~

`to_regclass(text)` looks up an object representable as `regclass` and returns `NULL` when not found, instead of throwing an error like directly casting `'...'::regclass` on a non-existent name.

Note: `regclass` does not represent only "data tables"—it can also point to other objects in `pg_class` such as views, sequences, or indexes. To confirm the object **kind**, inspect `pg_class.relkind` as well.

### 3.2. Common system schemas

| Schema | Purpose |
| --- | --- |
| `pg_catalog` | System catalogs, built-in functions, types, and internal objects |
| `information_schema` | SQL-standard metadata views |
| `public` | Common schema pre-created by databases; exact permissions vary by config/version |
| `pg_toast` | Internal storage mechanism for large values |
| `pg_temp_N` | Session temporary schema as needed |
| `meta_lab` | Application/practice schema we created |

Never place application tables into `pg_catalog` or modify system objects. When listing all schemas, you will see several technical schemas that are not business schemas.

## 4. What is information_schema and when should you use it?

`information_schema` includes views such as:

- `information_schema.schemata` — schemas.
- `information_schema.tables` — tables and views visible under privilege rules.
- `information_schema.columns` — columns and attributes.
- `information_schema.table_constraints` — constraints.
- `information_schema.key_column_usage` — columns participating in certain key constraints.
- `information_schema.constraint_column_usage` — columns referenced by constraints.
- `information_schema.referential_constraints` — foreign key properties.
- `information_schema.views` — view definitions when permitted.
- `information_schema.sequences` — standard-level sequence metadata.

Its advantage is relatively SQL-standard column naming without needing deep knowledge of OIDs and PostgreSQL storage internals. However:

1. They cover only **the portion of metadata fitting the SQL standard** and PostgreSQL's implementation of it.
2. These views generally **filter by access privileges**; not seeing an object does not always mean it does not exist.
3. Engine-specific details such as **expression indexes**, `indisvalid` state, partition table types, storage files, or materialized views often require `pg_catalog`.
4. "SQL standard" does not mean a specific query can be copied verbatim across PostgreSQL, MySQL, SQL Server, and Oracle with identical outputs.

## 5. Inspecting schemas and tables via information_schema

### 5.1. Listing observable user schemas

~~~sql
SELECT
    catalog_name,
    schema_name,
    schema_owner
FROM information_schema.schemata
WHERE schema_name = 'meta_lab';
~~~

`catalog_name` in PostgreSQL typically reflects **the current database**. Do not mistake this column for another database whose tables the connection can read directly.

### 5.2. Listing tables and views in a schema

~~~sql
SELECT
    table_catalog,
    table_schema,
    table_name,
    table_type
FROM information_schema.tables
WHERE table_schema = 'meta_lab'
ORDER BY table_type, table_name;
~~~

With the objects created earlier, we expect four base tables and one view:

| `table_name` | `table_type` |
| --- | --- |
| `customers` | `BASE TABLE` |
| `products` | `BASE TABLE` |
| `orders` | `BASE TABLE` |
| `order_items` | `BASE TABLE` |
| `v_order_summary` | `VIEW` |

Actual row ordering depends on `ORDER BY`; the table above groups by type for clarity. `table_type` in PostgreSQL can also reflect other types such as foreign tables where applicable.

If a role lacks appropriate privileges on tables/views, results from `information_schema.tables` may appear incomplete. Querying metadata **does not automatically grant table read access**.

### 5.3. Counting tables per schema

~~~sql
SELECT
    table_schema,
    COUNT(*) AS accessible_base_tables
FROM information_schema.tables
WHERE table_type = 'BASE TABLE'
  AND table_schema = 'meta_lab'
GROUP BY table_schema;
~~~

This counts **base tables visible in the metadata view under current privileges**, not necessarily an absolute inventory of every object in the instance. And `COUNT(*)` here counts **metadata rows**, not business data rows in tables.

## 6. Inspecting columns, ordinal position, data types, and defaults

One of the most frequently used queries when onboarding onto a system is:

~~~sql
SELECT
    table_name,
    ordinal_position,
    column_name,
    data_type,
    udt_name,
    character_maximum_length,
    numeric_precision,
    numeric_scale,
    is_nullable,
    column_default,
    is_identity,
    identity_generation
FROM information_schema.columns
WHERE table_schema = 'meta_lab'
  AND table_name = 'orders'
ORDER BY ordinal_position;
~~~

Column meanings:

| Field | Interpretation |
| --- | --- |
| `ordinal_position` | Column position in visible definition order |
| `column_name` | Column name |
| `data_type` | Type name as represented by `information_schema` |
| `udt_name` | Underlying PostgreSQL type name; useful for engine-specific types |
| `character_maximum_length` | Length limit if applicable to the type and declaration |
| `numeric_precision` / `numeric_scale` | Precision and scale where applicable |
| `is_nullable` | `YES` or `NO` reflecting column nullability |
| `column_default` | Default expression when visible, not necessarily identical to original source SQL |
| `is_identity` | `YES` if an identity column |
| `identity_generation` | e.g., `ALWAYS` for the identity defined in this lesson |

In `meta_lab.orders`, `order_id` is `BIGINT GENERATED ALWAYS AS IDENTITY`; inspect `is_identity` rather than inferring identity merely by searching for `nextval(...)` in `column_default`. Identity columns and `serial` declarations differ in sequence-management semantics.

### 6.1. data_type and udt_name are not always identical

In PostgreSQL, data types may be:

- Standard SQL types: `integer`, `numeric`, `character varying`.
- PostgreSQL-specific types: `uuid`, `jsonb`, `inet`, `timestamptz` (often shown in catalogs under internal names).
- User-defined types: enums, domains, composites.
- Arrays or other specialized types.

`information_schema.columns.data_type` may show standard names or labels like `USER-DEFINED` and `ARRAY`. In some cases, inspect `udt_schema`, `udt_name`, `domain_schema`, and `domain_name` to identify the exact base type or domain:

~~~sql
SELECT
    column_name,
    data_type,
    udt_schema,
    udt_name,
    domain_schema,
    domain_name
FROM information_schema.columns
WHERE table_schema = 'meta_lab'
  AND table_name = 'orders'
ORDER BY ordinal_position;
~~~

If a code generator needs to reconstruct **PostgreSQL types with typmod**, `pg_catalog.format_type` is generally more reliable than manually concatenating `data_type` and length fields.

### 6.2. NULL and CHECK are two separate validation layers

`is_nullable = 'NO'` indicates `NULL` is disallowed. A bare `CHECK (quantity > 0)` **does not forbid NULL**: in PostgreSQL, a `CHECK` constraint passes when the expression evaluates to `TRUE` or `UNKNOWN` (from `NULL`); an explicit `NOT NULL` constraint is required to forbid missing values.

Therefore, when reading metadata, inspect **both nullability and CHECK constraints**, rather than looking solely at `data_type`.

## 7. Inspecting standard constraints via information_schema

PostgreSQL uses constraints to enforce data integrity, and `information_schema.table_constraints` shows their types.

~~~sql
SELECT
    table_name,
    constraint_name,
    constraint_type,
    is_deferrable,
    initially_deferred
FROM information_schema.table_constraints
WHERE table_schema = 'meta_lab'
ORDER BY table_name, constraint_type, constraint_name;
~~~

Common types:

| `constraint_type` | Meaning |
| --- | --- |
| `PRIMARY KEY` | Primary key, non-duplicate and non-`NULL` |
| `UNIQUE` | Unique key value/combination per constraint semantics |
| `FOREIGN KEY` | Protects referential links from child table to parent table |
| `CHECK` | Restricts data values via boolean condition |

`NOT NULL` is clearly exposed in `information_schema.columns.is_nullable`; depending on the PostgreSQL version, internal representation of `NOT NULL` constraints may vary. Do not expect every not-null requirement to appear identically in `table_constraints`.

### 7.1. Inspecting columns belonging to PRIMARY KEY and UNIQUE

~~~sql
SELECT
    tc.table_name,
    tc.constraint_name,
    tc.constraint_type,
    kcu.ordinal_position,
    kcu.column_name
FROM information_schema.table_constraints AS tc
JOIN information_schema.key_column_usage AS kcu
    ON kcu.constraint_catalog = tc.constraint_catalog
   AND kcu.constraint_schema = tc.constraint_schema
   AND kcu.constraint_name = tc.constraint_name
   AND kcu.table_schema = tc.table_schema
   AND kcu.table_name = tc.table_name
WHERE tc.table_schema = 'meta_lab'
  AND tc.constraint_type IN ('PRIMARY KEY', 'UNIQUE')
ORDER BY
    tc.table_name,
    tc.constraint_name,
    kcu.ordinal_position;
~~~

For `order_items`, constraint `order_items_pk` has two columns in order:

~~~text
ordinal_position = 1 -> order_id
ordinal_position = 2 -> product_id
~~~

**Column order matters.** It governs how composite keys are declared and how backing indexes are organized. Never aggregate columns into a string without `ORDER BY ordinal_position` assuming natural row order is stable.

### 7.2. Aggregating constraint columns into one row

~~~sql
SELECT
    tc.table_name,
    tc.constraint_name,
    tc.constraint_type,
    string_agg(
        quote_ident(kcu.column_name),
        ', ' ORDER BY kcu.ordinal_position
    ) AS constraint_columns
FROM information_schema.table_constraints AS tc
JOIN information_schema.key_column_usage AS kcu
    ON kcu.constraint_catalog = tc.constraint_catalog
   AND kcu.constraint_schema = tc.constraint_schema
   AND kcu.constraint_name = tc.constraint_name
   AND kcu.table_schema = tc.table_schema
   AND kcu.table_name = tc.table_name
WHERE tc.table_schema = 'meta_lab'
  AND tc.constraint_type IN ('PRIMARY KEY', 'UNIQUE')
GROUP BY
    tc.table_name,
    tc.constraint_name,
    tc.constraint_type
ORDER BY tc.table_name, tc.constraint_name;
~~~

`quote_ident` safely quotes column names for display per PostgreSQL identifier syntax. In code generators, clearly distinguish **identifiers** from **data values**, and never splice user-provided names into SQL via unchecked string concatenation.

### 7.3. Inspecting FOREIGN KEY properties

~~~sql
SELECT
    tc.table_name AS child_table,
    tc.constraint_name,
    rc.match_option,
    rc.update_rule,
    rc.delete_rule
FROM information_schema.table_constraints AS tc
JOIN information_schema.referential_constraints AS rc
    ON rc.constraint_catalog = tc.constraint_catalog
   AND rc.constraint_schema = tc.constraint_schema
   AND rc.constraint_name = tc.constraint_name
WHERE tc.table_schema = 'meta_lab'
  AND tc.constraint_type = 'FOREIGN KEY'
ORDER BY child_table, tc.constraint_name;
~~~

`update_rule` and `delete_rule` return actions such as `NO ACTION`, `RESTRICT`, `CASCADE`, `SET NULL`, or `SET DEFAULT` as defined. This answers "What happens when the parent key is updated or the parent row is deleted?".

In systems with multiple schemas and duplicate constraint names, joining on **catalog, schema, and constraint name** is essential. For complex FK mappings—especially multi-column foreign keys—using OIDs in `pg_catalog` is generally clearer and less ambiguous.

## 8. When should you switch to pg_catalog?

`pg_catalog` is the schema containing PostgreSQL's system catalogs along with system views and functions. Key catalogs for structural inspection:

| Catalog/view/function | Main contents |
| --- | --- |
| `pg_namespace` | Schemas / namespaces |
| `pg_class` | Tables, views, materialized views, indexes, sequences, and other relation objects |
| `pg_attribute` | Attributes/columns of relations, ordered by `attnum` |
| `pg_type` | Built-in and user-defined data type definitions |
| `pg_attrdef` | Column defaults or generated expressions |
| `pg_constraint` | Primary key, unique, foreign key, check, exclusion constraints, and metadata |
| `pg_index` | Index structure and validity state |
| `pg_inherits` / `pg_partitioned_table` | Inheritance relationships and partitioned tables |
| `pg_description` | Comments on objects and columns |
| `pg_depend` | Dependencies among objects |
| `pg_proc` | Functions and procedures |
| `pg_trigger` | Triggers |
| `pg_sequence` / `pg_sequences` | Sequence attributes and friendly view |
| `pg_tables`, `pg_views`, `pg_matviews`, `pg_indexes` | Simpler lookup views over base catalogs |
| `pg_get_constraintdef`, `pg_get_indexdef`, `pg_get_viewdef` | Functions reconstructing human-readable definitions |

These catalogs are **PostgreSQL implementation details**, not a cross-DBMS SQL-standard metadata contract. Schemas, column names, or semantics can change between major versions. Test introspection tools against every PostgreSQL version your application supports.

## 9. Understanding OID, attnum, and relkind before JOINing catalogs

Three core PostgreSQL concepts:

- **OID** (*Object Identifier*): internal identifier for many catalog objects, typically used to join catalogs within **the current database**.
- **`attnum`**: ordinal attribute number inside a relation; combined with `attrelid` to identify a column.
- **`relkind`**: relation kind code in `pg_class`.

~~~mermaid
flowchart LR
    N["pg_namespace<br/>oid, nspname"] -->|"oid = relnamespace"| C["pg_class<br/>oid, relname, relkind"]
    C -->|"oid = attrelid"| A["pg_attribute<br/>attnum, attname, atttypid"]
    A -->|"atttypid = oid"| T["pg_type<br/>typname"]
    C -->|"oid = conrelid"| K["pg_constraint<br/>contype, conkey, confrelid"]
    C -->|"oid = indrelid"| I["pg_index<br/>indexrelid, indisvalid"]
~~~

**OIDs are internal identifiers**, not stable application business keys. Across dump/restore or object recreation, OIDs can change. Never store table OIDs inside business data as long-lived keys without an explicit lifecycle design.

### 9.1. Common relkind values

| `pg_class.relkind` | Type |
| --- | --- |
| `r` | Ordinary table |
| `p` | Partitioned table |
| `v` | View |
| `m` | Materialized view |
| `f` | Foreign table |
| `S` | Sequence |
| `i` | Index |
| `I` | Partitioned index |

`pg_class` also holds internal relations such as TOAST tables and composite types. To list "user tables", filter `relkind` and target schemas appropriately rather than blindly counting every row in `pg_class`.

### 9.2. Listing objects in a schema using pg_class

~~~sql
SELECT
    n.nspname AS schema_name,
    c.relname AS object_name,
    c.relkind,
    pg_get_userbyid(c.relowner) AS owner_name,
    c.relpersistence
FROM pg_catalog.pg_class AS c
JOIN pg_catalog.pg_namespace AS n
    ON n.oid = c.relnamespace
WHERE n.nspname = 'meta_lab'
  AND c.relkind IN ('r', 'p', 'v', 'm', 'f', 'S', 'i', 'I')
ORDER BY c.relkind, c.relname;
~~~

`relpersistence` indicates whether a relation is persistent, unlogged, or temporary (`p`, `u`, `t`). It **differs from `relkind`**: one describes object kind, while the other describes storage persistence.

Seeing indexes and sequences in the output does not mean "extra tables were created accidentally"—they are objects tracked in `pg_class` metadata.

## 10. Inspecting column definitions via pg_attribute

Using catalogs, join `pg_class`, `pg_namespace`, `pg_attribute`, and `pg_attrdef`:

~~~sql
SELECT
    n.nspname AS schema_name,
    c.relname AS table_name,
    a.attnum AS column_position,
    a.attname AS column_name,
    pg_catalog.format_type(a.atttypid, a.atttypmod)
        AS formatted_type,
    a.attnotnull AS is_not_null,
    a.attidentity AS identity_kind,
    a.attgenerated AS generated_kind,
    pg_catalog.pg_get_expr(d.adbin, d.adrelid)
        AS default_or_generation_expr
FROM pg_catalog.pg_class AS c
JOIN pg_catalog.pg_namespace AS n
    ON n.oid = c.relnamespace
JOIN pg_catalog.pg_attribute AS a
    ON a.attrelid = c.oid
LEFT JOIN pg_catalog.pg_attrdef AS d
    ON d.adrelid = a.attrelid
   AND d.adnum = a.attnum
WHERE n.nspname = 'meta_lab'
  AND c.relname = 'orders'
  AND c.relkind IN ('r', 'p')
  AND a.attnum > 0
  AND NOT a.attisdropped
ORDER BY a.attnum;
~~~

Why is `a.attnum > 0 AND NOT a.attisdropped` essential?

- PostgreSQL has **system columns** such as `ctid` and `xmin` represented by special attribute numbers; these are not application-defined SQL columns.
- After `DROP COLUMN`, positional slots can remain internally. Failing to filter `attisdropped` can expose dropped columns to schema generators.
- `attnum` is the **internal attribute position within the relation**, not a freeform display number you can renumber without affecting metadata. Gaps can exist due to dropped columns.

`format_type(atttypid, atttypmod)` builds display types such as `numeric(12,2)` and is usually far cleaner than manually combining `pg_type.typname` with precision/length attributes.

### 10.1. Identity and generated column metadata

In `pg_attribute`:

- `attidentity` represents identity columns (`ALWAYS` or `BY DEFAULT`), and is empty for ordinary columns.
- `attgenerated` indicates generated columns per PostgreSQL version support; normally empty if not generated.
- `pg_attrdef` and `pg_get_expr` describe default expressions or generated column expressions.

Do not assume every sequence-backed column has `column_default LIKE 'nextval%'`: identity columns are managed differently from traditional `serial` declarations. Use specialized functions/catalogs to detect column-bound sequences rather than matching default strings alone.

## 11. Retrieving constraint definitions directly from pg_constraint

`pg_constraint` provides richer details than standard metadata views, especially for multi-column foreign keys, deferrable constraints, and checking whether constraints have been validated.

~~~sql
SELECT
    c.relname AS table_name,
    con.conname AS constraint_name,
    con.contype AS constraint_kind,
    con.condeferrable AS is_deferrable,
    con.condeferred AS initially_deferred,
    con.convalidated AS is_validated,
    pg_catalog.pg_get_constraintdef(con.oid, TRUE)
        AS definition
FROM pg_catalog.pg_constraint AS con
JOIN pg_catalog.pg_class AS c
    ON c.oid = con.conrelid
JOIN pg_catalog.pg_namespace AS n
    ON n.oid = c.relnamespace
WHERE n.nspname = 'meta_lab'
ORDER BY c.relname, con.conname;
~~~

Common `contype` codes:

| `contype` | Meaning |
| --- | --- |
| `p` | Primary key |
| `u` | Unique constraint |
| `f` | Foreign key |
| `c` | Check constraint |
| `x` | Exclusion constraint |

`pg_get_constraintdef(con.oid, TRUE)` reconstructs the corresponding SQL clause, e.g.:

~~~text
PRIMARY KEY (order_id, product_id)
FOREIGN KEY (customer_id) REFERENCES meta_lab.customers(customer_id) ON DELETE RESTRICT
CHECK ((quantity > 0))
~~~

This is an **illustrative display form**; PostgreSQL may add extra parentheses, identifier quotes, or options. When storing DDL, use proper dump/schema-migration tooling rather than assuming deparsed text matches the original migration file verbatim.

### 11.1. Validation and deferrability fields

`convalidated` indicates whether a constraint has been validated when the constraint kind and syntax support `NOT VALID`. `condeferrable`/`condeferred` describe deferrability and initial state.

Not all constraint kinds support `NOT VALID` or `DEFERRABLE`. Nullability checks and unique indexes have distinct rules. Introspection tools must inspect **constraint kind** rather than over-generalizing from a single boolean.

### 11.2. Mapping multi-column FOREIGN KEYs via OID and attnum

A multi-column foreign key looks like:

~~~sql
FOREIGN KEY (col_a, col_b)
REFERENCES parent_table (parent_a, parent_b)
~~~

To know that `col_a` maps to `parent_a`, never join solely on constraint name and guess positions. `pg_constraint` stores:

- `conrelid`: OID of the child table.
- `confrelid`: OID of the parent table (for foreign keys).
- `conkey`: array of `attnum` values for the child table columns.
- `confkey`: corresponding array of `attnum` values for the parent table columns.

The query below reads **each column pair by array index**:

~~~sql
SELECT
    child_ns.nspname AS child_schema,
    child.relname AS child_table,
    con.conname AS foreign_key_name,
    k.pos AS column_pair_position,
    child_col.attname AS child_column,
    parent_ns.nspname AS parent_schema,
    parent.relname AS parent_table,
    parent_col.attname AS parent_column
FROM pg_catalog.pg_constraint AS con
JOIN pg_catalog.pg_class AS child
    ON child.oid = con.conrelid
JOIN pg_catalog.pg_namespace AS child_ns
    ON child_ns.oid = child.relnamespace
JOIN pg_catalog.pg_class AS parent
    ON parent.oid = con.confrelid
JOIN pg_catalog.pg_namespace AS parent_ns
    ON parent_ns.oid = parent.relnamespace
CROSS JOIN LATERAL
    generate_subscripts(con.conkey, 1) AS k(pos)
JOIN pg_catalog.pg_attribute AS child_col
    ON child_col.attrelid = con.conrelid
   AND child_col.attnum = con.conkey[k.pos]
JOIN pg_catalog.pg_attribute AS parent_col
    ON parent_col.attrelid = con.confrelid
   AND parent_col.attnum = con.confkey[k.pos]
WHERE con.contype = 'f'
  AND child_ns.nspname = 'meta_lab'
ORDER BY
    child.relname,
    con.conname,
    k.pos;
~~~

On the practice dataset, we see:

~~~text
orders.customer_id          -> customers.customer_id
order_items.order_id        -> orders.order_id
order_items.product_id      -> products.product_id
~~~

This query remains directly useful when two- or three-column foreign keys appear later. The constraint's OID is a reliable internal key for joining inside the same catalog, whereas bare constraint names are not guaranteed unique across an entire instance.

## 12. Inspecting indexes: pg_indexes or pg_index?

`information_schema` provides no standard view equivalent to `pg_index` for inspecting PostgreSQL-specific index attributes. The simplest starting point:

~~~sql
SELECT
    schemaname,
    tablename,
    indexname,
    indexdef
FROM pg_catalog.pg_indexes
WHERE schemaname = 'meta_lab'
ORDER BY tablename, indexname;
~~~

Results include both **indexes created automatically for PRIMARY KEY/UNIQUE constraints** and indexes created via `CREATE INDEX`. Consequently, the total number of indexes is usually **greater than the count of explicit CREATE INDEX statements** in DDL.

### 12.1. Checking whether an index is unique/primary/valid

~~~sql
SELECT
    t.relname AS table_name,
    i.relname AS index_name,
    x.indisunique AS is_unique,
    x.indisprimary AS supports_primary_key,
    x.indisvalid AS is_valid,
    x.indisready AS is_ready_for_insert,
    pg_catalog.pg_get_indexdef(i.oid) AS index_ddl
FROM pg_catalog.pg_index AS x
JOIN pg_catalog.pg_class AS t
    ON t.oid = x.indrelid
JOIN pg_catalog.pg_namespace AS n
    ON n.oid = t.relnamespace
JOIN pg_catalog.pg_class AS i
    ON i.oid = x.indexrelid
WHERE n.nspname = 'meta_lab'
  AND t.relname = 'orders'
ORDER BY i.relname;
~~~

Key fields:

- `indisunique`: whether the index enforces uniqueness per its definition.
- `indisprimary`: whether the index backs a primary key.
- `indisvalid`: whether the planner can treat the index as valid for queries under matching conditions.
- `indisready`: whether the index is ready to receive updates from writes.

In operations, `CREATE INDEX CONCURRENTLY` can fail and leave behind an **invalid index**. Merely seeing an index name in `pg_indexes` is not enough to conclude the planner uses it normally. `pg_index.indisvalid` is a critical check; when encountering an invalid index, diagnose the root cause and plan remediation before dropping anything in production.

### 12.2. Expression indexes, partial indexes, and INCLUDE

Suppose these indexes exist:

~~~sql
-- DDL example; run on lab tables only if you want to practice.
CREATE INDEX idx_customers_lower_email
    ON meta_lab.customers (lower(email));

CREATE INDEX idx_products_active
    ON meta_lab.products (list_price)
    WHERE is_active = TRUE;
~~~

An index on `lower(email)` is an **expression index**; an index on `list_price` covering only rows where `is_active = TRUE` is a **partial index**. Plain column lists cannot represent their full semantics. Use:

~~~sql
SELECT
    i.relname AS index_name,
    pg_catalog.pg_get_indexdef(i.oid) AS definition
FROM pg_catalog.pg_index AS x
JOIN pg_catalog.pg_class AS i
    ON i.oid = x.indexrelid
JOIN pg_catalog.pg_class AS t
    ON t.oid = x.indrelid
JOIN pg_catalog.pg_namespace AS n
    ON n.oid = t.relnamespace
WHERE n.nspname = 'meta_lab'
  AND t.relname IN ('customers', 'products')
ORDER BY index_name;
~~~

When building index inventory tools, you may also need `pg_index.indpred` (partial index predicate), `indexprs` (expressions), `indkey`, and `INCLUDE` columns. For **displaying** readable definitions, `pg_get_indexdef` is usually better than assembling metadata manually.

Do not add the indexes above just to see them in the catalog. In real systems, analyze queries, selectivity, write overhead, and execution plans.

## 13. Inspecting views and materialized views

### 13.1. Views via information_schema

~~~sql
SELECT
    table_schema,
    table_name,
    view_definition,
    check_option,
    is_updatable
FROM information_schema.views
WHERE table_schema = 'meta_lab'
ORDER BY table_name;
~~~

`v_order_summary` was defined via `CREATE VIEW`. The `view_definition` column can be restricted by ownership/privileges; never infer a view is "empty" merely because a role cannot see its definition.

### 13.2. Views via pg_views and pg_get_viewdef

~~~sql
SELECT
    schemaname,
    viewname,
    viewowner,
    definition
FROM pg_catalog.pg_views
WHERE schemaname = 'meta_lab';

SELECT pg_catalog.pg_get_viewdef(
    'meta_lab.v_order_summary'::regclass,
    TRUE
) AS reconstructed_select;
~~~

`pg_get_viewdef` reconstructs the underlying `SELECT` query in PostgreSQL's canonicalized format. Its formatting, aliases, or parentheses may differ from the original `CREATE VIEW` text even when semantically equivalent. Never rely solely on verbatim string comparison to verify whether a migration changed a view.

### 13.3. Materialized views require a separate query

**Materialized views** store physical results as of creation/refresh time per PostgreSQL's mechanism, unlike regular views. To inspect them:

~~~sql
SELECT
    schemaname,
    matviewname,
    matviewowner,
    ispopulated,
    definition
FROM pg_catalog.pg_matviews
WHERE schemaname = 'meta_lab'
ORDER BY matviewname;
~~~

With the current lab DDL, this returns **0 rows** because no materialized view was created.

In `pg_class`, materialized views have `relkind = 'm'`. Do not expect them to appear like ordinary views in all `information_schema.views` queries. When tooling must inventory all data sources, inspect `pg_matviews` and other relation kinds too.

## 14. Inspecting sequences and IDENTITY columns

`IDENTITY` uses a PostgreSQL-managed sequence to generate values. For `meta_lab.customers`:

~~~sql
SELECT
    column_name,
    is_identity,
    identity_generation,
    identity_start,
    identity_increment
FROM information_schema.columns
WHERE table_schema = 'meta_lab'
  AND table_name = 'customers'
  AND column_name = 'customer_id';
~~~

To locate the sequence bound to an identity or serial column:

~~~sql
SELECT pg_catalog.pg_get_serial_sequence(
    'meta_lab.customers',
    'customer_id'
) AS sequence_name;
~~~

Actual sequence names are generated by PostgreSQL under naming and collision-avoidance rules, so never assume the name will always be `customers_customer_id_seq` if DDL or restores altered the object.

List sequences in the schema:

~~~sql
SELECT
    schemaname,
    sequencename,
    sequenceowner,
    data_type,
    start_value,
    min_value,
    max_value,
    increment_by,
    cycle
FROM pg_catalog.pg_sequences
WHERE schemaname = 'meta_lab'
ORDER BY sequencename;
~~~

### 14.1. Sequence values do not equal table COUNT(*)

Sequence values can advance even when inserting transactions later **`ROLLBACK`**. Row deletions and unique conflicts also leave ID gaps. Therefore:

~~~text
Maximum ID value:      10
Current row count:      7
~~~

does not prove "three rows of data were lost" or that the sequence is broken. Never use `max(id) + 1` to generate IDs in multi-connection applications; use PostgreSQL-managed identity/sequences.

### 14.2. Never mutate sequences while merely reading metadata

`setval(...)`, `ALTER SEQUENCE`, and `RESTART` are operations that **affect future generated IDs**. They are not read-only metadata queries. Especially in production, misadjusting a sequence can cause primary key collisions on subsequent `INSERT` statements.

For investigation, start with `information_schema.columns`, `pg_get_serial_sequence`, and `pg_sequences`. Remember that certain fields showing current sequence state may be privilege-restricted and cannot be interpreted as an absolute "next ID" under concurrent traffic.

## 15. Inspecting object comments

Earlier when creating the schema, we ran `COMMENT ON TABLE` and `COMMENT ON COLUMN`. PostgreSQL provides description functions to feed schema documentation:

~~~sql
SELECT
    obj_description(
        'meta_lab.orders'::regclass,
        'pg_class'
    ) AS table_comment;
~~~

Read each column's comment:

~~~sql
SELECT
    a.attnum,
    a.attname AS column_name,
    pg_catalog.col_description(c.oid, a.attnum)
        AS column_comment
FROM pg_catalog.pg_class AS c
JOIN pg_catalog.pg_namespace AS n
    ON n.oid = c.relnamespace
JOIN pg_catalog.pg_attribute AS a
    ON a.attrelid = c.oid
WHERE n.nspname = 'meta_lab'
  AND c.relname = 'orders'
  AND a.attnum > 0
  AND NOT a.attisdropped
ORDER BY a.attnum;
~~~

If an object or column has no comment, the function returns `NULL`. **Lacking a comment does not mean the structure is broken**; yet on large systems, comments communicate business semantics that column names alone cannot capture.

`COMMENT` is not a substitute for constraints or permissions. A comment saying "email unique" will not prevent duplicate emails unless an actual unique constraint exists in DDL.

## 16. Inspecting table sizes and statistics via pg_catalog

Tables with identical column counts can vary drastically in size and workload. PostgreSQL provides size functions accepting `regclass`:

~~~sql
SELECT
    pg_size_pretty(
        pg_relation_size('meta_lab.orders'::regclass)
    ) AS main_relation_size,
    pg_size_pretty(
        pg_table_size('meta_lab.orders'::regclass)
    ) AS table_storage_size,
    pg_size_pretty(
        pg_indexes_size('meta_lab.orders'::regclass)
    ) AS indexes_size,
    pg_size_pretty(
        pg_total_relation_size('meta_lab.orders'::regclass)
    ) AS total_relation_size;
~~~

Practical interpretation:

| Function | Primary meaning |
| --- | --- |
| `pg_relation_size` | Size of the selected relation fork, defaulting to the main fork |
| `pg_table_size` | Table-related storage size including appropriate table/TOAST components, **excluding table indexes** |
| `pg_indexes_size` | Total size of indexes attached to the table |
| `pg_total_relation_size` | Total size of the table together with its indexes and associated components |
| `pg_size_pretty` | Converts byte counts into human-readable units |

Values change with data volume, indexes, VACUUM state, and storage layout. This **measures storage size**, not row counts.

### 16.1. Listing sizes of ordinary tables in a schema

~~~sql
SELECT
    n.nspname AS schema_name,
    c.relname AS table_name,
    pg_size_pretty(
        pg_total_relation_size(c.oid)
    ) AS total_size,
    pg_total_relation_size(c.oid) AS total_bytes
FROM pg_catalog.pg_class AS c
JOIN pg_catalog.pg_namespace AS n
    ON n.oid = c.relnamespace
WHERE n.nspname = 'meta_lab'
  AND c.relkind = 'r'
ORDER BY total_bytes DESC, table_name;
~~~

For partitioned tables, consider parent tables (`relkind = 'p'`) and child partitions carefully. Size functions called on a partitioned parent should not automatically be assumed to sum all child partitions; traverse the partition tree and aggregate member partitions properly.

### 16.2. reltuples and relpages are estimated statistics

~~~sql
SELECT
    c.relname AS table_name,
    c.reltuples AS estimated_rows,
    c.relpages AS estimated_pages
FROM pg_catalog.pg_class AS c
JOIN pg_catalog.pg_namespace AS n
    ON n.oid = c.relnamespace
WHERE n.nspname = 'meta_lab'
  AND c.relkind IN ('r', 'p')
ORDER BY c.relname;
~~~

`reltuples` is an **estimated row count** referenced by the planner in cost calculations, typically updated by VACUUM/ANALYZE and statistics collection. It can differ substantially from:

~~~sql
SELECT COUNT(*) FROM meta_lab.orders;
~~~

`COUNT(*)` scans the table to count visible rows in the query's snapshot, whereas `reltuples` is estimated metadata. Never use `reltuples` for business logic requiring exact figures such as paid order counts.

### 16.3. pg_stat_user_tables adds operational insights

~~~sql
SELECT
    schemaname,
    relname,
    n_live_tup,
    n_dead_tup,
    last_vacuum,
    last_autovacuum,
    last_analyze,
    last_autoanalyze
FROM pg_catalog.pg_stat_user_tables
WHERE schemaname = 'meta_lab'
ORDER BY relname;
~~~

`pg_stat_user_tables` is an **operational statistics view**, not a purely structural catalog. `n_live_tup` and `n_dead_tup` are also estimates. A newly created table having `last_analyze = NULL` does not indicate an error; it simply may not have been analyzed yet.

## 17. Partitioned tables and inheritance in pg_catalog

On large schemas, PostgreSQL may use **partitioning**. A partitioned parent table normally has `pg_class.relkind = 'p'`, while child partitions can be ordinary tables with inheritance metadata.

Inspect parent–child relationships:

~~~sql
SELECT
    parent_ns.nspname AS parent_schema,
    parent.relname AS parent_table,
    child_ns.nspname AS child_schema,
    child.relname AS child_table,
    pg_get_expr(
        child.relpartbound,
        child.oid
    ) AS partition_bound
FROM pg_catalog.pg_inherits AS inh
JOIN pg_catalog.pg_class AS parent
    ON parent.oid = inh.inhparent
JOIN pg_catalog.pg_namespace AS parent_ns
    ON parent_ns.oid = parent.relnamespace
JOIN pg_catalog.pg_class AS child
    ON child.oid = inh.inhrelid
JOIN pg_catalog.pg_namespace AS child_ns
    ON child_ns.oid = child.relnamespace
WHERE parent_ns.nspname = 'meta_lab'
  AND parent.relkind = 'p'
ORDER BY parent.relname, child.relname;
~~~

Our practice DDL creates no partitions, so this query returns **0 rows**. `pg_inherits` is also used for traditional **table inheritance**; therefore, never assume every row in `pg_inherits` represents declarative partitioning without checking the parent's `relkind` and related metadata.

To view the partition key:

~~~sql
SELECT
    c.relname AS partitioned_table,
    pg_catalog.pg_get_partkeydef(c.oid) AS partition_key
FROM pg_catalog.pg_class AS c
JOIN pg_catalog.pg_namespace AS n
    ON n.oid = c.relnamespace
WHERE n.nspname = 'meta_lab'
  AND c.relkind = 'p'
ORDER BY c.relname;
~~~

When building scripts to inventory sizes, row counts, or indexes for partitioned tables, decide explicitly whether to include **child partitions**. Blindly summing every relation in `pg_class` easily double-counts or misses partitions.

## 18. Inspecting functions, triggers, and other objects

A PostgreSQL schema contains more than tables, indexes, and views. It can also hold functions, procedures, triggers, enums, domains, and extensions.

### 18.1. Functions and procedures

A basic query using `pg_proc`:

~~~sql
SELECT
    n.nspname AS schema_name,
    p.proname AS routine_name,
    p.prokind AS routine_kind,
    pg_catalog.pg_get_function_identity_arguments(p.oid)
        AS identity_arguments,
    pg_catalog.pg_get_function_result(p.oid)
        AS return_type
FROM pg_catalog.pg_proc AS p
JOIN pg_catalog.pg_namespace AS n
    ON n.oid = p.pronamespace
WHERE n.nspname = 'meta_lab'
ORDER BY p.proname, identity_arguments;
~~~

`pg_proc` describes functions and other routine kinds; `prokind` distinguishes them. **Routine names are not always unique** because PostgreSQL supports function overloading (same name, different parameter types). To pinpoint a specific function, use its signature or OID instead of `proname` alone.

To view a definition (when the role holds appropriate privileges):

~~~sql
-- Works only when a function with this exact signature exists.
-- Syntax illustration:
-- SELECT pg_get_functiondef('meta_lab.some_fn(integer)'::regprocedure);
~~~

### 18.2. Triggers

~~~sql
SELECT
    c.relname AS table_name,
    t.tgname AS trigger_name,
    t.tgenabled AS enabled_state,
    pg_catalog.pg_get_triggerdef(t.oid, TRUE)
        AS definition
FROM pg_catalog.pg_trigger AS t
JOIN pg_catalog.pg_class AS c
    ON c.oid = t.tgrelid
JOIN pg_catalog.pg_namespace AS n
    ON n.oid = c.relnamespace
WHERE n.nspname = 'meta_lab'
  AND NOT t.tgisinternal
ORDER BY c.relname, t.tgname;
~~~

In the current example, no user triggers were created, so this returns **0 rows**. `NOT t.tgisinternal` excludes internal system triggers—including triggers implementing foreign keys—from the user trigger list.

**Never conclude "zero triggers exist" from this query if you intend to audit internal system triggers.** It lists only non-internal triggers in the filtered schema.

### 18.3. User-defined types

~~~sql
SELECT
    n.nspname AS schema_name,
    t.typname AS type_name,
    t.typtype AS type_kind,
    t.typcategory
FROM pg_catalog.pg_type AS t
JOIN pg_catalog.pg_namespace AS n
    ON n.oid = t.typnamespace
WHERE n.nspname = 'meta_lab'
ORDER BY t.typname;
~~~

`pg_type` includes many type kinds, among them **composite types automatically created for tables**. Seeing more rows than `CREATE TYPE` statements is therefore normal. To list enums or domains specifically, filter `typtype` appropriately; this is a PostgreSQL-specific detail.

## 19. Access privileges and metadata visibility

An important principle: **metadata visibility differs from data access**.

- `information_schema` normally displays only objects/columns for which the role holds appropriate privileges.
- `pg_catalog` may allow reading broader metadata, yet doing so grants no `SELECT` privilege on business tables.
- Certain sensitive details (object definitions, privilege details, or authentication info) are restricted via dedicated permissions, schemas, or views.
- Row-level security (RLS) governs reading **table rows**, and should not be mistaken for a mechanism that hides all table/column names in catalogs.

### 19.1. Checking current role and table privileges

~~~sql
SELECT
    current_user AS role_name,
    has_schema_privilege(
        current_user,
        'meta_lab',
        'USAGE'
    ) AS can_use_schema,
    has_table_privilege(
        current_user,
        'meta_lab.orders',
        'SELECT'
    ) AS can_select_orders,
    has_table_privilege(
        current_user,
        'meta_lab.orders',
        'INSERT'
    ) AS can_insert_orders;
~~~

`has_schema_privilege` and `has_table_privilege` evaluate role privileges per PostgreSQL rules, including inherited privileges where applicable. For non-existent objects, some call forms raise errors; verify object existence with `to_regclass` or resolve OIDs first if introspection tools must tolerate missing objects.

### 19.2. Inspecting grants via information_schema

~~~sql
SELECT
    table_schema,
    table_name,
    grantor,
    grantee,
    privilege_type,
    is_grantable
FROM information_schema.role_table_grants
WHERE table_schema = 'meta_lab'
ORDER BY table_name, grantee, privilege_type;
~~~

Results depend on the querying role and how privileges were granted. `role_table_grants` is not the whole answer for effective permissions, due to role memberships, ownership, inherited roles, and `PUBLIC` grants. To answer "can this role actually SELECT?", `has_table_privilege` is usually more reliable than inferring from a single GRANT row.

### 19.3. Never inspect passwords via system catalogs

`pg_roles` exposes appropriate role metadata for observation, yet **is not meant to expose password hashes**. Sensitive catalogs like `pg_authid` restrict access. Never attempt to extract credentials or secrets under the guise of "just querying metadata"; administrative work must obey privilege and security policies.

## 20. Using psql meta-commands for quick lookups

`psql` offers commands starting with `\`:

~~~text
\dn
\dt meta_lab.*
\dv meta_lab.*
\di meta_lab.*
\ds meta_lab.*
\d meta_lab.orders
\d+ meta_lab.orders
\d+ meta_lab.v_order_summary
~~~

They help:

- `\dn`: list schemas.
- `\dt`: tables.
- `\dv`: views.
- `\di`: indexes.
- `\ds`: sequences.
- `\d`: describe object structure, columns, and constraints.
- `\d+`: adds extra details such as storage, comments, and size depending on object kind and version.

These are **client-side `psql` meta-commands**, not SQL syntax sent over JDBC. If you run:

~~~sql
-- Invalid SQL when sent via PreparedStatement:
-- \d meta_lab.orders
~~~

the application will not get `psql`-style results. For Java services generating metadata automatically, query `information_schema` or `pg_catalog` instead.

### 20.1. Viewing the SQL that psql uses to query metadata

`psql` has a flag to echo internal queries, which is great for learning how catalogs join. In a lab environment:

~~~text
psql -E -d your_database
\d meta_lab.orders
~~~

This reveals the SQL `psql` executes to build its output. Keep in mind, however, that these are implementation details of your **`psql` version**, not a stable API that applications should copy verbatim and rely on long-term.

## 21. Writing a reusable schema inventory report

When onboarding onto a new system, compile metadata reports using read-only queries, avoiding dynamic SQL generation at the start.

### 21.1. List of relations and owners

~~~sql
SELECT
    n.nspname AS schema_name,
    c.relname AS object_name,
    CASE c.relkind
        WHEN 'r' THEN 'table'
        WHEN 'p' THEN 'partitioned table'
        WHEN 'v' THEN 'view'
        WHEN 'm' THEN 'materialized view'
        WHEN 'f' THEN 'foreign table'
        WHEN 'S' THEN 'sequence'
        WHEN 'i' THEN 'index'
        WHEN 'I' THEN 'partitioned index'
        ELSE 'other'
    END AS object_type,
    pg_get_userbyid(c.relowner) AS owner_name
FROM pg_catalog.pg_class AS c
JOIN pg_catalog.pg_namespace AS n
    ON n.oid = c.relnamespace
WHERE n.nspname = 'meta_lab'
  AND c.relkind IN ('r','p','v','m','f','S','i','I')
ORDER BY object_type, object_name;
~~~

### 21.2. User column count per table

~~~sql
SELECT
    n.nspname AS schema_name,
    c.relname AS table_name,
    COUNT(a.attnum) AS user_column_count
FROM pg_catalog.pg_class AS c
JOIN pg_catalog.pg_namespace AS n
    ON n.oid = c.relnamespace
LEFT JOIN pg_catalog.pg_attribute AS a
    ON a.attrelid = c.oid
   AND a.attnum > 0
   AND NOT a.attisdropped
WHERE n.nspname = 'meta_lab'
  AND c.relkind IN ('r', 'p')
GROUP BY n.nspname, c.relname
ORDER BY c.relname;
~~~

Putting column filters **inside the JOIN** preserves selected tables even if no matching columns appear in scope; in practice, defined ordinary tables have user columns.

### 21.3. FK relationships for building an ERD

~~~sql
SELECT
    child.relname AS from_table,
    con.conname AS fk_name,
    parent.relname AS to_table,
    pg_get_constraintdef(con.oid, TRUE) AS fk_definition
FROM pg_catalog.pg_constraint AS con
JOIN pg_catalog.pg_class AS child
    ON child.oid = con.conrelid
JOIN pg_catalog.pg_class AS parent
    ON parent.oid = con.confrelid
JOIN pg_catalog.pg_namespace AS ns
    ON ns.oid = child.relnamespace
WHERE ns.nspname = 'meta_lab'
  AND con.contype = 'f'
ORDER BY from_table, fk_name;
~~~

When drawing ERDs requiring **exact column names on both ends**, use the positional `conkey`/`confkey` join from Section 11.2 rather than parsing text definitions.

### 21.4. Invalid indexes in the schema

~~~sql
SELECT
    t.relname AS table_name,
    i.relname AS index_name,
    x.indisvalid,
    x.indisready
FROM pg_catalog.pg_index AS x
JOIN pg_catalog.pg_class AS i
    ON i.oid = x.indexrelid
JOIN pg_catalog.pg_class AS t
    ON t.oid = x.indrelid
JOIN pg_catalog.pg_namespace AS n
    ON n.oid = t.relnamespace
WHERE n.nspname = 'meta_lab'
  AND NOT x.indisvalid
ORDER BY t.relname, i.relname;
~~~

On a cleanly created lab schema, this query returns **0 rows**. On a live system, an invalid index can result from a failed `CREATE INDEX CONCURRENTLY` or an incomplete operation; investigate status and active jobs before intervening.

## 22. Limitations and caveats when using metadata

### 22.1. Metadata is not an immutable system-wide snapshot

PostgreSQL supports concurrent DDL. If a tool runs sequential metadata queries across separate transactions, a migration between queries might rename a table, add a column, or drop an index.

For schema exports requiring strict consistency, rely on a **controlled snapshot/backup/migration process**. Never expect discrete queries against a live system undergoing DDL changes to reconstruct a single point-in-time definition reliably.

### 22.2. Never compare OIDs across two environments

A table's OID in dev can differ from its counterpart's OID in staging or production. To compare schemas across environments, compare **schema name, object name, type, definition, and migration version**; use OIDs strictly as metadata JOIN keys within a single database context.

### 22.3. Handling uppercase or special-character names accurately

PostgreSQL folds unquoted identifiers to lowercase:

~~~sql
CREATE TABLE meta_lab.sample_table (id INTEGER);
-- Actual stored name: sample_table.
~~~

However:

~~~sql
CREATE TABLE meta_lab."SampleTable" (id INTEGER);
-- Actual stored name must be referenced as "SampleTable".
~~~

Consequently, filters like `WHERE table_name = 'sampletable'` will not find `"SampleTable"`. For DDL generators, standardize naming conventions or use `quote_ident` / `format('%I.%I', schema_name, table_name)` when emitting identifiers.

**Do not run those two CREATE statements if you only want to query metadata**; they merely illustrate PostgreSQL identifier handling.

### 22.4. Metadata visibility does not equal schema modification privilege

A role may read table names from `pg_catalog.pg_class` while lacking `SELECT` on table rows and `ALTER TABLE` privileges. Never assume an introspection tool capable of listing objects holds administrative privileges. For application roles, keep read/write/migration permissions separated and protect sensitive data.

### 22.5. Catalogs can change across versions

Columns for generated columns, partitioning, index options, and privilege details can differ across PostgreSQL major versions. In particular, avoid writing `SELECT *` and serializing entire catalog rows into a rigid contract.

For long-lived tooling:

1. Define supported PostgreSQL major versions.
2. Select only the metadata columns actually needed.
3. Test against specialized features such as identity, domains, arrays, materialized views, partitions, and expression indexes.
4. Never edit system catalogs to "fix metadata errors".
5. Use migrations/schema dumps as structural verification sources where appropriate.

## 23. information_schema vs. pg_catalog: quick selection guide

| Question | Preferred source | Why? |
| --- | --- | --- |
| Which schemas exist and are accessible? | `information_schema.schemata` | Easy-to-use SQL-standard view |
| Which tables/views am I allowed to see? | `information_schema.tables` | Applies privilege filtering |
| Columns, SQL types, defaults, nullability? | `information_schema.columns` | Sufficient for many CRUD/schema-browser cases |
| Basic primary keys, unique keys, FKs? | `table_constraints`, `key_column_usage` | Accessible via standard views |
| How do multi-column FK columns map? | `pg_constraint`, `pg_attribute` | `conkey`/`confkey` and OIDs give exact mapping |
| Index DDL, expressions, partial predicates, valid state? | `pg_indexes`, `pg_index` | PostgreSQL-specific metadata |
| Distinguish ordinary tables, partitions, matviews, sequences? | `pg_class.relkind` | Covers more relation kinds than standard views |
| View DDL? | `pg_views` / `pg_get_viewdef` | Reconstructs query definitions |
| Column comments? | `col_description` | Links comments by OID + attnum |
| Sequence backing an identity column? | `pg_get_serial_sequence` / `pg_sequences` | Supports identity/serial mechanisms |
| Table/index storage sizes? | `pg_total_relation_size`, `pg_indexes_size` | Storage-specific functions |
| Exact row count? | `SELECT COUNT(*)` | Catalogs provide estimates only |
| Effective privileges of a role? | `has_table_privilege` | Better than inferring from a single GRANT row |
| Quick terminal inspection? | `psql \d` / `\dt` / `\di` | Practical for manual exploration |

A solid rule of thumb is to **start with `information_schema` when standard SQL metadata suffices**, and switch to `pg_catalog` when PostgreSQL-specific attributes or exact OID-based structural reconstruction are needed.

## 24. Practice exercises

### Exercise 1 — Listing columns and checking NOT NULL

Write a query on `information_schema.columns` returning all columns of `meta_lab.products` with `ordinal_position`, `data_type`, `is_nullable`, and `column_default`.

**Hint:**

~~~sql
SELECT
    ordinal_position,
    column_name,
    data_type,
    is_nullable,
    column_default
FROM information_schema.columns
WHERE table_schema = 'meta_lab'
  AND table_name = 'products'
ORDER BY ordinal_position;
~~~

Explain why column `is_active` has default `TRUE` yet still needs `NOT NULL` to forbid `NULL`.

### Exercise 2 — Identifying a composite primary key

Use `table_constraints` and `key_column_usage` to find the columns of `order_items_pk`. You can reuse the query in Section 7.1 with `tc.constraint_name = 'order_items_pk'`.

**Expected:** `order_id` is position 1, `product_id` is position 2. Explain why each column is not marked unique individually.

### Exercise 3 — Drawing a relationship diagram from catalogs

From the `pg_constraint` join query in Section 11.2, draw the arrows:

~~~text
orders.customer_id       --> customers.customer_id
order_items.order_id     --> orders.order_id
order_items.product_id   --> products.product_id
~~~

Then explain why a standalone constraint name is not always sufficient as a join key across all metadata.

### Exercise 4 — Finding indexes beyond primary key indexes

Query `pg_indexes` on `meta_lab.orders`. Identify which indexes enforce primary keys/unique constraints and which index was created by `CREATE INDEX idx_orders_customer_time`. Then check `indisvalid` via `pg_index`.

**Hint:** never count `CREATE INDEX` statements in source SQL to deduce total indexes, since `PRIMARY KEY` and `UNIQUE` automatically create supporting indexes.

### Exercise 5 — Comparing views and materialized views

Query `information_schema.views`, `pg_views`, and `pg_matviews` in the schema. Which type is `v_order_summary`? Why does `pg_matviews` return 0 rows for this DDL?

**Hint:** regular views are defined by a query; materialized views store physical results that can be refreshed.

### Exercise 6 — Comparing row metadata against COUNT(*)

Run:

~~~sql
SELECT relname, reltuples
FROM pg_catalog.pg_class
WHERE oid = 'meta_lab.orders'::regclass;

SELECT COUNT(*) AS exact_visible_rows
FROM meta_lab.orders;
~~~

**Question:** why can `reltuples` differ from 1 even though the seed inserted one order? Explain the difference between planner statistics and snapshot-based counting.

### Exercise 7 — Inspecting comments and sequences

Use `obj_description`, `col_description`, and `pg_get_serial_sequence` to answer:

- What is the comment on `orders`?
- What is the comment on `orders.order_code`?
- Which sequence is linked to `customers.customer_id`?

**Hint:** never guess sequence names from table names alone.

### Exercise 8 — Identifying privilege boundaries

Suppose a reporting role has only `USAGE` on the schema and `SELECT` on `meta_lab.v_order_summary`, without direct `SELECT` on `orders`. Explain:

1. Why `information_schema.tables` can show different rows when run as owner vs. reporting role?
2. Why seeing an object in `pg_catalog` does not grant `SELECT` privilege?
3. Should a reporting role be given superuser solely to inventory metadata?

**Hint:** metadata visibility, table data access, and schema modification privileges are separate concepts.

### Exercise 9 — Handling uppercase object names

Suppose a team creates a table using the quoted identifier `"CustomerOrders"`. Why does `table_name = 'customerorders'` fail to find it? Show how to call `to_regclass` with properly quoted naming and how to filter `pg_class.relname` appropriately.

### Exercise 10 — Designing a schema documentation exporter

Design a report covering:

- Schema, object name, and relation kind.
- Column names, display types, nullability, identity/default.
- Primary keys, unique, check, and foreign key constraints.
- Expression/partial indexes along with validity status.
- View definitions and comments.
- Storage size metadata where permitted.

Specify which sections should prefer `information_schema` and which require or suit `pg_catalog`. When implementing, use OIDs to join **within the same database**, never as durable object keys across environments.

## 25. Recommendations for using metadata in real projects

When building tools working with PostgreSQL, metadata sources can power:

**Automated data documentation:** extract column names, types, FKs, comments, and view definitions to build ERDs or data dictionaries.

**Migration verification:** compare expected objects in migrations against live structure. Avoid comparing only column names while ignoring nullability, indexes, constraints, or defaults.

**Schema browsers/IDEs:** let users explore tables, views, and relationships even without full data read access.

**Operational inventories:** detect invalid indexes, partitions, custom types, sequences, table owners, or storage sizes to support controlled changes.

**SQL generation tools:** metadata identifies columns and types, yet you must still safely quote identifiers, bind data parameters, and enforce execution permissions. Finding a column name in the catalog does not make dynamically concatenated SQL safe.

In multi-role, multi-schema systems, always log the **database, schema, querying role, and PostgreSQL version** alongside reports. Metadata output lacking that context is easily mistaken for a complete cluster-wide view.

## 26. Official references

When building long-term introspection tools, consult documentation matching your exact version:

- [PostgreSQL — Information Schema](https://www.postgresql.org/docs/current/information-schema.html): SQL-standard metadata views.
- [PostgreSQL — System Catalogs](https://www.postgresql.org/docs/current/catalogs.html): `pg_class`, `pg_attribute`, `pg_constraint`, `pg_index`, and other catalogs.
- [PostgreSQL — System Information Functions](https://www.postgresql.org/docs/current/functions-info.html): functions for OIDs, privileges, definitions, and metadata.
- [PostgreSQL — Database Object Size Functions](https://www.postgresql.org/docs/current/functions-admin.html): object size functions.
- [PostgreSQL — psql](https://www.postgresql.org/docs/current/app-psql.html): `\d`, `\dt`, `\di` meta-commands and internal query echo mode.

The `/docs/current/` path refers to the latest stable release. If your database runs PostgreSQL 14, 15, 16, or another specific release, replace `current` with **the corresponding major version number** when checking exact behavior.

## 27. Summary

**`information_schema` is a convenient starting point** for inventorying schemas, tables, columns, keys, and views in a relatively standardized metadata model. It fits many admin UIs, schema docs, and basic structural checks, though results can be filtered by user privileges and do not cover every PostgreSQL-specific capability.

**`pg_catalog` provides a deeper view into PostgreSQL's object architecture.** By joining `pg_namespace`, `pg_class`, `pg_attribute`, `pg_constraint`, and `pg_index` via OID and `attnum`, you can precisely inspect relation kinds, columns, multi-column foreign keys, index validity, partitions, views, sequences, comments, and storage stats. The `pg_get_*def` functions reconstruct readable definitions.

When inspecting metadata, remember three boundaries: **never confuse bare object names with schema/`search_path`**, **never treat catalog estimates as exact business counts**, and **never confuse metadata visibility with data access privileges**. Knowing how to pick the right source and interpret its semantics enables exploring unfamiliar databases, verifying migrations, and administering PostgreSQL based on evidence rather than guesswork.
