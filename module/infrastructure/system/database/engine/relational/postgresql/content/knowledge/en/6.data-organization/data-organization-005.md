# Object dependencies, RESTRICT, and CASCADE in PostgreSQL

When designing a relational database, a table rarely exists in isolation. An orders table may contain a foreign key referencing a customers table; a view may read data from both tables; another reporting view may read from the first view; and indexes, constraints, and sequences also have relationships tied to tables or columns.

Therefore, a seemingly simple command such as:

~~~sql
DROP TABLE customers;
~~~

can be rejected by PostgreSQL with a message stating that other objects still depend on the table. The database engine must prevent a DDL operation from accidentally leaving retained objects in an invalid state.

PostgreSQL lets you control object deletion via two important modes:

- **`RESTRICT`:** refuses to drop if blocking dependencies remain; requires the administrator to proactively resolve related objects.
- **`CASCADE`:** consents to also dropping dependent objects according to PostgreSQL's rules, which may extend beyond what is immediately visible in the statement.

This lesson explains the **object dependency** model, distinguishes dependency types, demonstrates `DROP ... RESTRICT` and `DROP ... CASCADE` with tables, foreign keys, views, columns, and schemas, and shows how to inspect dependencies via system catalogs and deploy DDL changes safely.

## 1. What is an object dependency?

An object **A depends on B** when A's definition or integrity requires B to exist. If B is dropped or changed incompatibly, A may become invalid.

Example:

~~~text
      dep_lab.customers
           │
           ├──────────────────┐
           │                  │
           ▼                  ▼
  FK fk_orders_customer   dep_lab.v_order_summary
     (belongs to orders)      ▲
           ▲                  │
           │                  │
      dep_lab.orders ─────────┘
                                  │
                                  ▼
                         dep_lab.v_paid_orders
~~~

To read the diagram accurately:

1. Foreign key constraint `fk_orders_customer` belongs to the `orders` table and references the primary key on `customers`.
2. `v_order_summary` is a view using both `customers` and `orders`.
3. `v_paid_orders` is a view reading from `v_order_summary`, and thus indirectly depends on the underlying objects below it.
4. If a view lives in another schema yet reads `customers`, the dependency relationship still exists even though the two objects reside in different schemas.

PostgreSQL stores metadata for these relationships in system catalogs. The database engine uses them to decide whether to block an operation, which objects to drop alongside, or how to perform automatic cleanup.

### Dependencies go beyond foreign keys

| Object | Example dependency relationship |
| --- | --- |
| **Foreign key** | Constraint on `orders` requires the referenced key on `customers` |
| **View** | `v_order_summary` reads columns of `orders` and `customers` |
| **Nested view** | `v_paid_orders` reads data from `v_order_summary` |
| **Index** | Index belongs to a table and its indexed columns |
| **Constraint** | `CHECK`, `UNIQUE`, `PRIMARY KEY` attached to a table/column |
| **Identity/owned sequence** | Sequence tied to a column has an ownership/dependency link |
| **Materialized view** | Definition depends on source relations |
| **Schema** | Tables, views, sequences, functions, etc. belonging to the schema |
| **Function/type** | Certain function signatures, return types, or SQL expressions depend on other types, functions, or operators |

**Not every business-level link is automatically tracked by PostgreSQL.** For example, a Java application containing the SQL string `SELECT * FROM customers` does not become an object in the `pg_depend` catalog. Some references constructed via dynamic SQL or string-bodied functions may also not be tracked the way view definitions are. Therefore, checking dependencies inside the database is necessary, but **not sufficient** to guarantee the application will remain unaffected.

## 2. RESTRICT and CASCADE: two ways to handle dependencies

For many `DROP` statements, PostgreSQL supports:

~~~sql
DROP TABLE ten_bang RESTRICT;

DROP TABLE ten_bang CASCADE;
~~~

### RESTRICT

`RESTRICT` tells PostgreSQL to **reject the operation** if any dependent objects remain that the engine cannot automatically clean up as internal owned components of the dropped object.

For instance, if you try to drop the customers table while an orders table has a foreign key referencing it, or a view still uses that table, PostgreSQL reports a dependency error. The administrator must decide to drop or modify those related objects first.

### CASCADE

`CASCADE` permits PostgreSQL to **also drop the necessary dependent objects**. A single operation can trigger a chain:

~~~text
DROP TABLE customers CASCADE
               │
               ├── Drops orders foreign key referencing customers
               │
               ├── Drops view v_order_summary
               │          │
               │          └── Drops view v_paid_orders
               │
               └── Drops any other dependent objects if present
~~~

**`CASCADE` does not mean PostgreSQL will delete every table that ever had a relationship with the dropped table.** For example, `DROP TABLE customers CASCADE` may remove the **foreign key constraint** on `orders` while keeping the **`orders` table and its order rows** intact. However, views depending on `customers` will be dropped completely.

### RESTRICT is the default for DROP in many cases

~~~sql
DROP TABLE dep_lab.customers;
~~~

is equivalent in dependency policy to using `RESTRICT` on `DROP TABLE`. Writing `RESTRICT` explicitly signals cautious intent to readers.

| Criterion | `RESTRICT` | `CASCADE` |
| --- | --- | --- |
| When normal dependencies exist | Blocks operation and reports an error | Permits dropping dependent objects along with the target |
| Manual control level | High | Requires thorough impact verification |
| Cascading deletion risk | Does not automatically execute chains of normal dependency drops | Can traverse multiple layers of views/constraints |
| Schema boundary | Checks dependencies outside the schema as well | Can also drop objects in other schemas |
| When to consider | Controlled changes, production migrations | Lab cleanup, or changes where every dependency has been audited |

`RESTRICT` and `CASCADE` are not "completely safe" vs. "completely dangerous"; they are **dependency-handling policy choices**. Choosing rightly depends on the change objective, level of control, and recovery plan.

## 3. Creating sample data to observe dependencies

The following experiments are meant for a **PostgreSQL lab** with permissions to create schemas, tables, and views. Do not execute them on a database holding real data.

We create two schemas to demonstrate that dependencies can cross schema boundaries:

~~~sql
CREATE SCHEMA dep_lab;
CREATE SCHEMA dep_reports;
~~~

### 3.1. Creating the customers and orders tables

~~~sql
CREATE TABLE dep_lab.customers (
    customer_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_name text NOT NULL UNIQUE
);

CREATE TABLE dep_lab.orders (
    order_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id bigint NOT NULL,
    status text NOT NULL,
    amount numeric(12, 2) NOT NULL CHECK (amount >= 0),
    CONSTRAINT fk_orders_customer
        FOREIGN KEY (customer_id)
        REFERENCES dep_lab.customers (customer_id)
);

CREATE INDEX idx_orders_customer
    ON dep_lab.orders (customer_id);
~~~

Points to note:

- `customers.customer_id` is the primary key.
- `orders.customer_id` holds a foreign key to `customers.customer_id`.
- `idx_orders_customer` is a supporting index for querying by customer; it is not a prerequisite for PostgreSQL allowing the foreign key to be created.
- Both `GENERATED ALWAYS AS IDENTITY` columns have column-bound sequences under PostgreSQL's mechanism.
- The `CHECK (amount >= 0)` and `PRIMARY KEY` constraints are also schema objects associated with the table.

Insert a few rows:

~~~sql
INSERT INTO dep_lab.customers (customer_name)
VALUES ('An'), ('Binh'), ('Chi');

INSERT INTO dep_lab.orders (customer_id, status, amount)
VALUES
    (1, 'paid',    120000.00),
    (1, 'pending',  80000.00),
    (2, 'paid',    150000.00);
~~~

The `INSERT` assumes identity IDs start sequentially from 1 in a fresh lab database. If the table already existed or sequences ran previously, retrieve the actual customer IDs rather than relying on sample order.

### 3.2. Creating views dependent on the tables

~~~sql
CREATE VIEW dep_lab.v_order_summary AS
SELECT
    o.order_id,
    c.customer_name,
    o.status,
    o.amount
FROM dep_lab.orders AS o
JOIN dep_lab.customers AS c
    ON c.customer_id = o.customer_id;
~~~

This view does not store a copy of rows like a regular table. It holds a **query definition**, referencing both `orders` and `customers`.

Create a view depending on the previous view:

~~~sql
CREATE VIEW dep_lab.v_paid_orders AS
SELECT
    order_id,
    customer_name,
    amount
FROM dep_lab.v_order_summary
WHERE status = 'paid';
~~~

The resulting dependency chain:

~~~text
orders + customers
         │
         ▼
v_order_summary
         │
         ▼
v_paid_orders
~~~

### 3.3. Creating a reporting view in another schema

~~~sql
CREATE VIEW dep_reports.v_customer_totals AS
SELECT
    c.customer_id,
    c.customer_name,
    COUNT(o.order_id) AS order_count,
    COALESCE(SUM(o.amount), 0) AS total_amount
FROM dep_lab.customers AS c
LEFT JOIN dep_lab.orders AS o
    ON o.customer_id = c.customer_id
GROUP BY c.customer_id, c.customer_name;
~~~

Even though the view belongs to the `dep_reports` schema, it still depends on objects in `dep_lab`.

Check the sample data:

~~~sql
SELECT * FROM dep_lab.v_order_summary ORDER BY order_id;
SELECT * FROM dep_lab.v_paid_orders ORDER BY order_id;
SELECT * FROM dep_reports.v_customer_totals ORDER BY customer_id;
~~~

In the following sections, we will use `BEGIN` and `ROLLBACK` to test drop operations **without persisting destructive changes** after the experiment ends.

## 4. Testing DROP TABLE ... RESTRICT

Suppose you want to drop `customers`:

~~~sql
BEGIN;

DROP TABLE dep_lab.customers RESTRICT;

-- DROP is expected to fail because dependencies remain.
ROLLBACK;
~~~

PostgreSQL reports a dependency error, typically conveying:

~~~text
ERROR: cannot drop table dep_lab.customers because other objects depend on it
DETAIL: constraint fk_orders_customer on table dep_lab.orders depends on table dep_lab.customers
DETAIL: view dep_lab.v_order_summary depends on table dep_lab.customers
...
HINT: Use DROP ... CASCADE to drop the dependent objects too.
~~~

The message above is **illustrative of meaning** and does not guarantee exact ordering or identical error lines across all versions.

**Important note when using psql:** inside a PostgreSQL transaction, an error statement normally puts the transaction into an *aborted* state. After an error, run `ROLLBACK` before trying other commands. If your tool is configured to halt scripts immediately on error, you may need to roll back manually on the open connection.

Because `RESTRICT` blocks the operation, the `customers` table remains intact. The `orders` table, views, and data are also preserved.

### RESTRICT helps uncover dependents

This is an operational benefit of `RESTRICT`: PostgreSQL can reveal **some of the objects blocking deletion**. However, never rely on errors as the sole method to enumerate total impact, especially on production systems. Inspecting catalogs and schema definitions prior to deployment remains essential.

## 5. Testing DROP TABLE ... CASCADE

After mapping dependencies, retry the same operation while allowing cascading deletion:

~~~sql
BEGIN;

DROP TABLE dep_lab.customers CASCADE;

SELECT to_regclass('dep_lab.customers') AS customers_table;
SELECT to_regclass('dep_lab.orders') AS orders_table;
SELECT to_regclass('dep_lab.v_order_summary') AS summary_view;
SELECT to_regclass('dep_lab.v_paid_orders') AS paid_view;
SELECT to_regclass('dep_reports.v_customer_totals') AS report_view;

ROLLBACK;
~~~

While `DROP TABLE ... CASCADE` executes **inside the open transaction**, the `to_regclass(...)` queries verify which objects still exist at that moment:

| Object | Expected result before `ROLLBACK` | Explanation |
| --- | --- | --- |
| `dep_lab.customers` | `NULL` | Table requested to be dropped |
| `dep_lab.orders` | Still exists | Table holding FK is not automatically dropped with parent table |
| `fk_orders_customer` on `orders` | Gone | FK depending on `customers` key was dropped |
| `dep_lab.v_order_summary` | `NULL` | View referencing `customers` table |
| `dep_lab.v_paid_orders` | `NULL` | View depending on `v_order_summary` |
| `dep_reports.v_customer_totals` | `NULL` | View in another schema referencing `customers` |

Notice `to_regclass(text)` returns the object name if found, or `NULL` if the relation does not exist. It is convenient for experiments because it avoids throwing errors when a table/view name has been dropped.

In this experiment, **the `orders` table still keeps its columns and order rows**, yet **the constraint validating `customer_id` was removed**. This represents a severe data-integrity risk if committed on a live system: the application could keep writing orders with `customer_id` values whose referential integrity is no longer enforced.

Finally:

~~~sql
ROLLBACK;
~~~

at the end of the test block reverts the DDL operation and restores the pre-drop structure. PostgreSQL supports transactional DDL for operations like `DROP TABLE` in this example. Still, DDL can hold locks while the transaction is open and affect other sessions; never test on production simply because you think you can roll back.

### CASCADE does not make business decisions

PostgreSQL knows which views depend on a table and which constraints must be removed. However, it **does not know** which Java application calls that view, which reporting team relies on that data, or which constraint is critical for the sales workflow. Therefore, a syntactically valid `CASCADE` command can still trigger a severe business outage.

## 6. Indirect dependencies across multiple view layers

Suppose you only want to drop the `v_order_summary` view, without touching the data tables:

~~~sql
BEGIN;

DROP VIEW dep_lab.v_order_summary RESTRICT;

ROLLBACK;
~~~

The `RESTRICT` command is expected to fail because `v_paid_orders` still depends on `v_order_summary`.

If replaced with:

~~~sql
BEGIN;

DROP VIEW dep_lab.v_order_summary CASCADE;

SELECT to_regclass('dep_lab.v_order_summary') AS summary_view;
SELECT to_regclass('dep_lab.v_paid_orders') AS paid_view;
SELECT to_regclass('dep_lab.customers') AS customers_table;
SELECT to_regclass('dep_lab.orders') AS orders_table;

ROLLBACK;
~~~

then:

- `v_order_summary` is dropped as requested.
- `v_paid_orders` is also dropped because it depends on the first view.
- `customers` and `orders` remain intact: they are **data sources referenced by the view**, not objects depending on the view.
- `dep_reports.v_customer_totals` remains intact because it reads directly from the two tables, **not from `v_order_summary`**.

This illustrates **dependency direction**:

~~~text
Source tables ──► View A ──► View B

DROP View A CASCADE:
      drops View A, View B
      does not drop Source tables
~~~

When using `CASCADE`, PostgreSQL follows forward dependency links in the catalog, **never propagating backward to drop every object queried in the view definition**.

## 7. ALTER TABLE ... DROP COLUMN and its impact on views

You do not always want to drop an entire table. A migration might require removing the `status` column from `orders`.

However, `v_order_summary` reads `orders.status`, and `v_paid_orders` filters on the `status` column exposed by that view.

### 7.1. Refusing to drop a column while dependents exist

~~~sql
BEGIN;

ALTER TABLE dep_lab.orders
DROP COLUMN status RESTRICT;

ROLLBACK;
~~~

When PostgreSQL detects that a view depends on this column, the command is expected to be rejected.

### 7.2. Allowing column dependents to be dropped

~~~sql
BEGIN;

ALTER TABLE dep_lab.orders
DROP COLUMN status CASCADE;

SELECT to_regclass('dep_lab.orders') AS orders_table;
SELECT to_regclass('dep_lab.v_order_summary') AS summary_view;
SELECT to_regclass('dep_lab.v_paid_orders') AS paid_view;
SELECT to_regclass('dep_reports.v_customer_totals') AS totals_view;

ROLLBACK;
~~~

Expected outcome:

- The `orders` table remains without the `status` column inside the test transaction.
- View `v_order_summary`, which depends on the `status` column, is dropped.
- View `v_paid_orders`, which depends downstream on it, is also dropped.
- `dep_reports.v_customer_totals` does not reference `status` and therefore survives unless another dependency is affected.

**Lesson:** `DROP COLUMN ... CASCADE` can drop **entire views**, not merely "strip that column from the view definition". PostgreSQL does not automatically rewrite queries to keep views working after a source column is removed.

### Certain components are cleaned up automatically when a column is dropped

When dropping a column, tightly bound objects such as related indexes or column constraints may be removed automatically via internal or automatic dependency rules. This does not mean PostgreSQL always requires you to write `CASCADE` for every index attached to that column.

If the column participates in a primary key, unique constraint, or is referenced by another table's foreign key, inspect all constraints before making changes. Never assume keys and views will adjust themselves to match application expectations.

## 8. DROP SCHEMA and impact across schema boundaries

Dropping a schema is one of the most frequently misunderstood operations:

~~~sql
DROP SCHEMA dep_lab RESTRICT;
~~~

In the lab, `dep_lab` currently contains multiple tables and views, so the default/`RESTRICT` command is blocked. `RESTRICT` refuses to drop a schema that still holds objects requiring handling.

Try `CASCADE` inside a transaction:

~~~sql
BEGIN;

DROP SCHEMA dep_lab CASCADE;

SELECT EXISTS (
    SELECT 1
    FROM pg_namespace
    WHERE nspname = 'dep_lab'
) AS dep_lab_exists;

SELECT EXISTS (
    SELECT 1
    FROM pg_namespace
    WHERE nspname = 'dep_reports'
) AS dep_reports_exists;

SELECT to_regclass('dep_reports.v_customer_totals')
       AS totals_view;

ROLLBACK;
~~~

Explanation:

- Schema `dep_lab` and its objects are dropped inside the transaction.
- View `dep_reports.v_customer_totals`, despite living in **another schema**, is also dropped because it depends on tables in `dep_lab`.
- Schema `dep_reports` **still exists**, because the schema itself is not a dependent object that must be removed just because one view inside it was dropped.

For this reason, `DROP SCHEMA some_schema CASCADE` does not necessarily stay confined to `some_schema`. An external dependency can propagate the deletion chain to **objects belonging to other schemas**.

To clean up a lab once you have verified data is no longer needed, learners may drop the schemas they created. However, **never run a cleanup command with `CASCADE` without first checking all cross-schema dependencies**.

## 9. Foreign keys: DROP CASCADE is not ON DELETE CASCADE

Both syntaxes use the word `CASCADE`, yet they solve **completely different** problems.

### 9.1. ON DELETE CASCADE is row-level DML behavior

~~~sql
CREATE TABLE parent_demo (
    id integer PRIMARY KEY
);

CREATE TABLE child_demo (
    id integer PRIMARY KEY,
    parent_id integer REFERENCES parent_demo(id)
        ON DELETE CASCADE
);
~~~

In this example, when deleting a **row** in `parent_demo`, PostgreSQL automatically deletes rows in `child_demo` referencing that parent row per the foreign key rule.

~~~sql
DELETE FROM parent_demo WHERE id = 10;
~~~

This is a **DML operation on table data**, not dropping the definitions of `parent_demo` or `child_demo`.

### 9.2. DROP TABLE ... CASCADE is object-level DDL behavior

~~~sql
DROP TABLE parent_demo CASCADE;
~~~

This command requests dropping the **table object** and required dependent objects. If `child_demo` has a foreign key referencing `parent_demo`, PostgreSQL removes the **foreign key constraint** on `child_demo` while retaining `child_demo` and its existing rows.

| Syntax | Primary target affected | Meaning |
| --- | --- | --- |
| `DELETE FROM parent_demo ...` | Data rows | Deletes rows matching the condition |
| `ON DELETE CASCADE` | Child rows with foreign key | Automatically deletes child rows when parent row is deleted |
| `DROP TABLE parent_demo CASCADE` | Table definition and dependent objects | Drops parent table and dependent constraints/views per rules |

Similarly, **`ON DELETE RESTRICT`** in a foreign key definition governs **parent row deletion**, not the dependency policy of `DROP TABLE ... RESTRICT`.

Do not confuse these two layers when reading error messages or designing migrations.

## 10. Dependencies cleaned up automatically

PostgreSQL does not require `CASCADE` to drop **every internal child structure** belonging to a table.

Example:

~~~sql
CREATE TABLE dep_lab.logs (
    log_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    message text NOT NULL
);

CREATE INDEX idx_logs_message
    ON dep_lab.logs (message);
~~~

When dropping the table:

~~~sql
BEGIN;
DROP TABLE dep_lab.logs RESTRICT;
ROLLBACK;
~~~

PostgreSQL can still drop the table along with components **owned by or created to serve that table directly**, such as indexes on the table and sequences bound to identity columns, even with `RESTRICT`.

This is not a contradiction of the `RESTRICT` rule. Components like table indexes have **automatic or internal** dependency relationships, unlike an independent view querying table data or a foreign key from **another table**.

### Identity sequences and owned sequences

In the `GENERATED ALWAYS AS IDENTITY` example, PostgreSQL manages the associated sequence under the identity model. When the column or table is dropped, the column's sequence is handled according to its dependency relationship.

For manually created sequences, ownership can be managed explicitly:

~~~sql
CREATE TABLE dep_lab.events (
    event_id bigint PRIMARY KEY,
    description text NOT NULL
);

CREATE SEQUENCE dep_lab.events_event_id_seq;

ALTER SEQUENCE dep_lab.events_event_id_seq
OWNED BY dep_lab.events.event_id;
~~~

The `OWNED BY` link instructs PostgreSQL to bind the sequence's lifecycle to the corresponding column. If the column or table is dropped appropriately, PostgreSQL automatically manages dropping that owned sequence.

An **unowned** sequence is not automatically dropped merely because the application used `nextval()` with it. This reinforces that **dependencies recorded by the database engine** govern DDL behavior, not informal usage habits in application code.

## 11. Dependency types in the PostgreSQL catalog

PostgreSQL tracks several dependency types in the `pg_depend` catalog. The `deptype` column indicates the relationship's semantics; common values include:

| `deptype` | Common name | Operational intuition |
| --- | --- | --- |
| `n` | Normal | Dependent object can be dropped independently; dropping the referenced object requires `CASCADE` if dependencies remain |
| `a` | Automatic | Dependent object can be dropped automatically when the referenced object is dropped |
| `i` | Internal | Internal component of another object; cannot be treated as an independent object to be dropped arbitrarily |
| `e` | Extension | Object is a member of an extension; lifecycle is governed by extension management rules |
| `P` / `S` | Partition dependencies | Dependencies tied to partition structures, governed by dedicated management rules |

Learners do not need to memorize every catalog detail to use `DROP`, yet knowing there are **multiple dependency types** explains why:

- A view blocks `DROP TABLE ... RESTRICT`.
- A table index is dropped alongside its table without needing a separate `CASCADE`.
- An object belonging to an extension may not be directly droppable and must be managed at the extension level.
- Partitioned structures can have stricter rules than ordinary tables.

**Never modify `pg_depend` directly.** This is a critical system catalog used by PostgreSQL to preserve schema consistency. Always operate through official DDL and let PostgreSQL maintain dependencies.

### An easily overlooked catalog detail for views

A view in PostgreSQL is backed by a **rewrite rule** storing its query definition. When inspecting `pg_depend`, references to source tables are typically represented via **the `_RETURN` rule in `pg_rewrite`**, rather than every dependency row pointing `objid` directly at the view's OID.

That is why a naive query checking only "view OID → source table OID" can miss dependencies, even though PostgreSQL knows about them and enforces them properly during `DROP`.

## 12. Inspecting foreign key dependencies with pg_constraint

For foreign keys, querying `pg_constraint` is usually much clearer than manually decoding every `pg_depend` row:

~~~sql
SELECT
    conname AS constraint_name,
    conrelid::regclass AS referencing_table,
    confrelid::regclass AS referenced_table,
    pg_get_constraintdef(oid) AS definition
FROM pg_constraint
WHERE contype = 'f'
  AND confrelid = 'dep_lab.customers'::regclass
ORDER BY conname;
~~~

Column meanings:

| Column | Meaning |
| --- | --- |
| `conname` | Constraint name |
| `conrelid` | Table **holding** the foreign key |
| `confrelid` | Table **being referenced** |
| `pg_get_constraintdef(oid)` | Human-readable constraint definition |

In our example, the expected result includes `fk_orders_customer`, `referencing_table = dep_lab.orders`, and `referenced_table = dep_lab.customers`.

To find all foreign keys defined on the `orders` table regardless of what they reference, change the condition to:

~~~sql
WHERE contype = 'f'
  AND conrelid = 'dep_lab.orders'::regclass
~~~

Treat this as a metadata lookup query, not a command modifying privileges or schemas.

## 13. Checking which views reference a table

In `psql`, an easy starting point is:

~~~text
\d+ dep_lab.customers
\d+ dep_lab.orders
\dv dep_lab.*
~~~

To view a view's definition:

~~~sql
SELECT pg_get_viewdef(
    'dep_lab.v_order_summary'::regclass,
    true
) AS view_definition;
~~~

In certain cases, `psql` also lists dependent objects beneath the table details; visibility depends on object type and version.

### Finding directly dependent views via pg_depend and pg_rewrite

The example below illustrates locating views whose rewrite rule references `dep_lab.orders`:

~~~sql
SELECT DISTINCT
    dep_ns.nspname AS dependent_schema,
    dep_rel.relname AS dependent_view,
    src_ns.nspname AS referenced_schema,
    src_rel.relname AS referenced_relation
FROM pg_depend AS d
JOIN pg_rewrite AS rw
    ON rw.oid = d.objid
JOIN pg_class AS dep_rel
    ON dep_rel.oid = rw.ev_class
JOIN pg_namespace AS dep_ns
    ON dep_ns.oid = dep_rel.relnamespace
JOIN pg_class AS src_rel
    ON src_rel.oid = d.refobjid
JOIN pg_namespace AS src_ns
    ON src_ns.oid = src_rel.relnamespace
WHERE d.classid = 'pg_rewrite'::regclass
  AND d.refclassid = 'pg_class'::regclass
  AND d.deptype = 'n'
  AND rw.rulename = '_RETURN'
  AND dep_rel.relkind IN ('v', 'm')
  AND src_rel.oid = 'dep_lab.orders'::regclass
ORDER BY dependent_schema, dependent_view;
~~~

On the sample data, views **directly** depending on `dep_lab.orders` normally include:

- `dep_lab.v_order_summary`.
- `dep_reports.v_customer_totals`.

`dep_lab.v_paid_orders` reads **view `v_order_summary`** rather than reading `orders` directly, so a query looking only for direct dependencies on `orders` may omit it. To assess the full **indirect dependency chain**, traverse multiple levels or use tooling capable of constructing a dependency graph.

**Important limitation:** the query above targets **views/materialized views via the `_RETURN` rule**. It is not an exhaustive enumeration of all dependency kinds such as FKs, functions, sequences, triggers, extensions, or dependencies arising from other constructs.

### Listing objects inside schemas

~~~sql
SELECT
    n.nspname AS schema_name,
    c.relname AS relation_name,
    c.relkind
FROM pg_class AS c
JOIN pg_namespace AS n
    ON n.oid = c.relnamespace
WHERE n.nspname IN ('dep_lab', 'dep_reports')
ORDER BY n.nspname, c.relkind, c.relname;
~~~

Common `relkind` values: `r` for ordinary table, `v` for view, `m` for materialized view, `i` for index, `S` for sequence, `p` for partitioned table. This query helps inventory relations in schemas, **but cannot replace a dependency graph**.

## 14. RESTRICT/CASCADE with DROP FUNCTION, TYPE, and EXTENSION

These two options do not apply only to tables and views.

### 14.1. Functions used by views

Example creating a simple SQL function and a view calling it:

~~~sql
CREATE FUNCTION dep_lab.double_amount(x numeric)
RETURNS numeric
LANGUAGE sql
IMMUTABLE
RETURN x * 2;

CREATE VIEW dep_lab.v_amount_preview AS
SELECT
    order_id,
    dep_lab.double_amount(amount) AS doubled_amount
FROM dep_lab.orders;
~~~

`RETURN x * 2` uses the SQL-standard function body syntax supported in modern PostgreSQL releases. For the view definition, PostgreSQL records a dependency on the function used.

Test:

~~~sql
BEGIN;
DROP FUNCTION dep_lab.double_amount(numeric) RESTRICT;
ROLLBACK;
~~~

The command is expected to be rejected because a view uses the function. With `CASCADE`:

~~~sql
BEGIN;
DROP FUNCTION dep_lab.double_amount(numeric) CASCADE;
SELECT to_regclass('dep_lab.v_amount_preview') AS preview_view;
ROLLBACK;
~~~

the dependent view is dropped in the chain.

**Important:** when dropping overloaded functions, always specify the **parameter type signature**, such as `double_amount(numeric)`. PostgreSQL allows multiple functions with the same name and different parameter types, so looking solely at the function name is insufficient.

Not every reference to a function or table inside a dynamic SQL string is tracked this way. Dependency catalogs protect references PostgreSQL can analyze in object definitions, yet cannot replace auditing application code and dynamic SQL.

### 14.2. Types and domains

A column may use a custom type or domain. If you attempt to drop a type currently used by a column or function, `RESTRICT` blocks it; `CASCADE` drops dependent objects per PostgreSQL rules.

Syntax example:

~~~sql
DROP TYPE some_schema.some_type RESTRICT;
DROP TYPE some_schema.some_type CASCADE;
~~~

This is **illustrative**; do not run without creating the type and inventorying objects using it. Dropping a type can sweep away objects far more critical than the type itself.

### 14.3. Extensions

An extension such as `hstore` or `pg_trgm` can install functions, operators, types, index operator classes, and helper objects. Objects that are extension members follow the extension's lifecycle management rules.

~~~sql
-- Syntax illustration only; do not run in live environments
-- without evaluating all dependencies:
DROP EXTENSION pg_trgm RESTRICT;
DROP EXTENSION pg_trgm CASCADE;
~~~

`CASCADE` can remove objects outside the extension that depend on objects provided by the extension, following PostgreSQL rules. This requires extra caution when upgrading or removing application extensions.

## 15. Dropping dependencies manually in order instead of CASCADE

If you want operations that can be controlled and reviewed step by step, you can **drop dependent objects from the outside in** before dropping the source object.

For `customers` in the lab, the following example shows an intentional deletion order:

~~~sql
BEGIN;

-- 1. Drop views at the highest dependency layer.
DROP VIEW dep_lab.v_paid_orders;

-- 2. Drop views reading directly from the tables.
DROP VIEW dep_lab.v_order_summary;
DROP VIEW dep_reports.v_customer_totals;

-- 3. Drop FK on the table being retained.
ALTER TABLE dep_lab.orders
DROP CONSTRAINT fk_orders_customer;

-- 4. Now drop the customers table.
DROP TABLE dep_lab.customers RESTRICT;

-- 5. Testing only; do not keep destructive changes.
ROLLBACK;
~~~

Advantages:

- Every command explicitly names the **object intended for removal**.
- Easy to include step-by-step in database migration code reviews.
- Separates the decision to keep `orders` and drop the FK into an explicit business choice.
- Makes it straightforward to plan recreating views whose definitions need updating.

Disadvantage: every dependent object must be inventoried. If a new view or constraint was created elsewhere while preparing the migration, `RESTRICT` will still raise an error—which is generally a healthy signal to review impact rather than blindly adding `CASCADE`.

**Avoid assuming manual deletion order guarantees valid business data.** If you drop a foreign key while keeping `orders.customer_id`, the application needs a strategy to maintain referential integrity as the relational design changes.

## 16. Should schema changes run in transactions?

PostgreSQL supports **transactional DDL** for many operations such as creating/dropping tables, views, and constraints. This allows testing in an isolated environment and rolling back if an expected step fails.

~~~sql
BEGIN;

DROP VIEW dep_lab.v_paid_orders;
DROP VIEW dep_lab.v_order_summary;

-- If you do not actually want to keep the changes, abort the transaction:
ROLLBACK;
~~~

After `ROLLBACK`, both views are restored to their pre-transaction state, provided they were only modified inside that transaction.

However, not **every** PostgreSQL administrative command is allowed inside a transaction block; for example, `DROP DATABASE` has its own restrictions. Furthermore, while DDL runs inside a transaction, PostgreSQL may still hold **locks** on objects until the transaction ends.

### Testing RESTRICT errors inside a transaction

In PostgreSQL, if a command errors after `BEGIN`, the transaction normally enters an aborted state. Only commands like `ROLLBACK` or rolling back to an appropriate savepoint can exit that state.

A pattern for interactive testing:

~~~sql
BEGIN;
SAVEPOINT before_drop;

-- Expected to fail due to dependencies:
DROP TABLE dep_lab.customers RESTRICT;

-- Run after error if the client continues accepting commands:
ROLLBACK TO SAVEPOINT before_drop;

-- Can continue checks inside the transaction:
SELECT COUNT(*) FROM dep_lab.customers;

ROLLBACK;
~~~

When running in pipelines using `psql -v ON_ERROR_STOP=1` or tools that halt on error, statements after the failure may **not execute**; ensure the transaction is rolled back before reusing the connection.

**Even with transactions, always test on a recoverable clone/staging database.** An accidentally committed `DROP ... CASCADE` can wipe out both structure and data. Transactions are not a backup mechanism and do not fix operational mistakes once committed.

## 17. Safe migration workflow when dependencies exist

Before running `DROP TABLE`, `DROP VIEW`, or `ALTER TABLE DROP COLUMN` in production, follow a structured process:

1. **Identify the source object**: qualified name including schema, table, view, column, function signature; avoid ambiguity from `search_path`.
2. **Inventory dependencies inside PostgreSQL**: foreign keys, views, materialized views, sequences, indexes, constraints, extensions, and related objects.
3. **Inspect dependencies outside the database**: SQL in Java, ORM mappings, stored application queries, reports, BI dashboards, jobs, ETL, and data contracts.
4. **Forecast RESTRICT/CASCADE impact**: which objects are blocked, which are dropped, and which tables survive without constraints.
5. **Design reviewable migrations**: prefer naming each object explicitly; if using `CASCADE`, attach an expected list of objects to be removed.
6. **Prepare recovery**: take appropriate backups/snapshots, verify restores, and prepare scripts to rebuild objects if needed.
7. **Test on staging**: run the migration and business queries; check DDL ordering and lock durations.
8. **Deploy with control**: consider maintenance windows, lock timeouts, active query sessions, and how the application rolls out the new schema version.
9. **Verify post-change**: inspect catalogs, constraints, views, application queries, business outputs, and error logs.

### Example of an "expand first, contract later" change

If you need to remove the `status` column while views depend on it, a safer strategy than immediate deletion is typically:

~~~text
Phase 1: Create replacement structure, e.g., new column/status
Phase 2: Update application and views to use the new structure
Phase 3: Verify no legacy consumers remain
Phase 4: Drop old views/column via a verified migration
~~~

This strategy, commonly called **expand–migrate–contract**, avoids breaking older application versions during multi-service rollouts.

### Never treat IF EXISTS as data-loss protection

~~~sql
DROP TABLE IF EXISTS dep_lab.customers CASCADE;
~~~

`IF EXISTS` merely stops PostgreSQL from throwing an error if the table **does not exist** (typically emitting a notice). When the table **does exist**, the command still executes `CASCADE` and can cascade-delete dependent objects. It is not a "dry run" mode and prompts for no confirmation.

## 18. Hands-on exercises

Use the `dep_lab` and `dep_reports` objects created in Section 3. If you only want to analyze, you do not need to run the `DROP` statements.

### Exercise 1. Predicting RESTRICT behavior

The `orders` table has a foreign key referencing `customers`, and view `v_order_summary` reads `customers`. What happens when running:

~~~sql
DROP TABLE dep_lab.customers RESTRICT;
~~~

Why doesn't PostgreSQL just remove the constraint and proceed?

### Exercise 2. Predicting CASCADE behavior

Assume no objects exist outside the lab objects:

~~~sql
DROP TABLE dep_lab.customers CASCADE;
~~~

State the fate of:

1. Table `dep_lab.orders`.
2. Constraint `fk_orders_customer`.
3. View `dep_lab.v_order_summary`.
4. View `dep_lab.v_paid_orders`.
5. View `dep_reports.v_customer_totals`.

### Exercise 3. Multi-level view dependencies

Given `v_paid_orders` reads `v_order_summary`, and `v_order_summary` reads two source tables. Does the command:

~~~sql
DROP VIEW dep_lab.v_order_summary CASCADE;
~~~

drop the `orders` table? Why or why not?

### Exercise 4. DROP COLUMN CASCADE

`v_order_summary` references column `orders.status`. If you run:

~~~sql
ALTER TABLE dep_lab.orders
DROP COLUMN status CASCADE;
~~~

does PostgreSQL automatically strip the `status` column from the view definition and keep the view working? Which objects can be dropped via dependencies?

### Exercise 5. Cross-schema dependencies

View `dep_reports.v_customer_totals` reads tables from schema `dep_lab`. If you run `DROP SCHEMA dep_lab CASCADE`, is schema `dep_reports` dropped? What about the view inside it?

### Exercise 6. Two kinds of CASCADE

Explain the difference between:

~~~sql
DELETE FROM parent_demo WHERE id = 10;
-- Foreign key on child_demo has ON DELETE CASCADE.

DROP TABLE parent_demo CASCADE;
~~~

Which command deals with deleting **data rows**, and which deals with dropping **object definitions**?

### Exercise 7. Finding foreign keys referencing customers

Write a catalog query displaying the foreign key name, referencing table, and referenced table for FKs pointing to `dep_lab.customers`.

### Exercise 8. Manual deletion order

Arrange the operations into a sequence that can use `RESTRICT` instead of `CASCADE` when dropping `customers`:

- Drop constraint `fk_orders_customer`.
- Drop `v_paid_orders`.
- Drop `v_order_summary`.
- Drop `dep_reports.v_customer_totals`.
- Drop `customers`.

Explain why upper-layer views must be handled before lower-layer views.

### Exercise 9. Dependencies unseen by the catalog

A Java application contains SQL `SELECT status FROM dep_lab.orders`, yet no PostgreSQL view or function contains that SQL. Is querying `pg_depend` enough to confirm dropping the `status` column will not break the application?

### Exercise 10. RESTRICT and transactions

Inside a transaction, `DROP TABLE ... RESTRICT` fails due to a dependency. Why might the subsequent `SELECT` fail? Which command must be used to continue?

### Answer hints

| Exercise | Key answer |
| --- | --- |
| 1 | Rejected because normal dependent FK and views remain; `RESTRICT` does not consent to removing them |
| 2 | `orders` remains; FK is dropped; `v_order_summary`, `v_paid_orders`, and `v_customer_totals` are cascade-dropped |
| 3 | No. Table `orders` is a data source read by the view, not a dependent object of the view being dropped |
| 4 | PostgreSQL does not rewrite views to drop columns; affected views are dropped by `CASCADE` |
| 5 | Schema `dep_reports` remains; view `v_customer_totals` depends on tables in `dep_lab` and is therefore dropped |
| 6 | `ON DELETE CASCADE` applies to data rows; `DROP ... CASCADE` applies to schema objects |
| 7 | Use `pg_constraint` with `contype = 'f'` and `confrelid = 'dep_lab.customers'::regclass` |
| 8 | Drop `v_paid_orders`, `v_order_summary`, `v_customer_totals`, drop FK, then drop `customers`; independent steps can be reordered |
| 9 | No. SQL dependencies inside application code do not automatically appear in catalogs |
| 10 | Transaction enters aborted state; use `ROLLBACK` or `ROLLBACK TO SAVEPOINT` as appropriate |

Sample solution for Exercise 7:

~~~sql
SELECT
    conname,
    conrelid::regclass AS referencing_table,
    confrelid::regclass AS referenced_table
FROM pg_constraint
WHERE contype = 'f'
  AND confrelid = 'dep_lab.customers'::regclass
ORDER BY conname;
~~~

## 19. Quick reference table

| Task | Illustrative statement | Key takeaway |
| --- | --- | --- |
| Drop table but block if normal dependencies exist | `DROP TABLE dep_lab.customers RESTRICT;` | Suitable for preventing unintended cascading drops |
| Drop table and dependent objects | `DROP TABLE dep_lab.customers CASCADE;` | Can remove FKs on other tables and drop views |
| Drop view while blocking child views | `DROP VIEW dep_lab.v_order_summary RESTRICT;` | Downstream referencing views will block it |
| Drop view and child views | `DROP VIEW dep_lab.v_order_summary CASCADE;` | Does not propagate backward to drop source tables |
| Drop column and dependent objects | `ALTER TABLE dep_lab.orders DROP COLUMN status CASCADE;` | Can drop entire views |
| Drop schema and dependents | `DROP SCHEMA dep_lab CASCADE;` | Impact can cross schema boundaries |
| Drop FK while keeping table | `ALTER TABLE dep_lab.orders DROP CONSTRAINT fk_orders_customer;` | Data remains, but referential enforcement is lost |
| Inspect FKs referencing a table | `pg_constraint`, `confrelid` | Constraint inventory |
| Inspect views referencing a table | `pg_depend` + `pg_rewrite` | Only a partial view of the dependency graph |
| Test rollback-capable DDL | `BEGIN; ... ROLLBACK;` | Still acquires locks; does not replace backups |

**Key takeaway:** PostgreSQL manages dependencies to safeguard schema consistency. `RESTRICT` forces administrators to address normal dependent objects prior to deletion, whereas `CASCADE` approves a deletion chain that can traverse multiple layers of views, constraints, columns, and even other schemas. Whenever deciding to drop an object, verify **dependency direction, scope of affected objects, application references**, and recovery plans. A syntactically successful DDL command is never enough by itself to conclude a system remains business-safe.
