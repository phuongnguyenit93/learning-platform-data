# System Catalogs, OIDs, and Object Relationships in PostgreSQL

In PostgreSQL, a table is more than just the rows of data an application reads and writes. The database engine must also track the table's name, which schema owns it, its columns and data types, where the primary key lives, which indexes are used, which views depend on it, and which roles hold privileges on it. That information is **metadata**—data describing the structure and behavior of the database itself.

PostgreSQL stores most metadata in **system catalogs**, primarily inside the `pg_catalog` schema. To link records across multiple catalogs, PostgreSQL uses internal identifiers, notably **OIDs (Object Identifiers)**. Understanding system catalogs and OIDs helps you move from merely writing `CREATE TABLE` SQL to understanding **how PostgreSQL tracks relationships among database objects**.

This lesson centers on four questions:

1. **What are system catalogs?** How do they differ from business tables, `information_schema`, and statistics views?
2. **What do OIDs mean?** When do you use OIDs, `regclass`, and `regtype`, and why must you never store OIDs as business keys?
3. **How do catalogs link together?** From schemas to tables, columns, data types, indexes, constraints, views, functions, and dependencies.
4. **How can you inspect them with SQL?** Build a practice model and query the catalogs to observe PostgreSQL's structure firsthand.

> The queries in this lesson read metadata and are suitable for learning on modern PostgreSQL. Minor catalog details can vary across versions. **Never modify rows in `pg_catalog` directly**; always use PostgreSQL-supported DDL statements such as `CREATE`, `ALTER`, and `DROP`.

## 1. What Kinds of Information Does PostgreSQL Store?

PostgreSQL manages at least three categories of information:

| Category | Content | Examples |
|---|---|---|
| **Business data** | Rows created, read, and updated by applications | Customers, orders, products |
| **Structural metadata** | Definitions of tables, columns, keys, indexes, schemas, functions, types | `pg_class`, `pg_attribute`, `pg_constraint` |
| **Runtime state and statistics** | Connections, scan counts, estimated row counts, active queries | `pg_stat_activity`, `pg_stat_user_tables` |

Suppose an application runs:

~~~sql
CREATE TABLE demo_item (
    id BIGINT PRIMARY KEY,
    ten TEXT NOT NULL
);
~~~

This statement does more than allocate storage for rows. PostgreSQL also creates or updates metadata for:

- The `demo_item` relation and its owning schema.
- Columns `id` and `ten`, their ordinal positions, and their data types.
- The `PRIMARY KEY` and `NOT NULL` constraints.
- The unique index backing the primary key.
- The composite row type associated with the table.
- Dependencies preventing accidental drops or changes that would break dependent objects.

This metadata is distributed across multiple catalogs linked by internal identifiers and reference columns. When you run `\d demo_item` in `psql`, the client queries PostgreSQL's catalogs to render that output; `psql` does not memorize table schemas on its own.

## 2. What Is a System Catalog?

A **system catalog** is a collection of internal relations PostgreSQL uses to describe and manage database objects. Most live in the `pg_catalog` schema and can be queried via SQL with appropriate privileges.

Important catalogs include:

- `pg_namespace`: schemas.
- `pg_class`: tables, indexes, views, sequences, and other relation types.
- `pg_attribute`: columns/attributes of relations.
- `pg_type`: data types.
- `pg_constraint`: constraints, including primary keys, foreign keys, unique, and check constraints.
- `pg_index`: index-specific metadata.
- `pg_attrdef`: column default expressions and related info.
- `pg_proc`: functions and procedures.
- `pg_rewrite`: rewrite rules, including rules backing views.
- `pg_depend`: dependency edges among objects.
- `pg_description`: comments attached to objects.
- `pg_database`: databases within the cluster.
- `pg_roles`: view exposing role metadata safely for inspection.

You can query a catalog just like a regular table:

~~~sql
SELECT oid, nspname
FROM pg_catalog.pg_namespace
ORDER BY nspname;
~~~

However, **being readable via SQL does not mean it can be updated like an application table**. PostgreSQL relies on internal metadata invariants to maintain integrity. Manually editing catalog rows bypasses object-management steps and can corrupt the database or cause undefined behavior.

### 2.1. Why are catalogs stored as relations?

PostgreSQL stores metadata as relations so it can be queried, joined, and managed inside PostgreSQL's own transactional engine. Most DDL schema changes follow transactional rules.

Example:

~~~sql
BEGIN;

CREATE TABLE public.temp_catalog_demo (
    id INTEGER PRIMARY KEY
);

ROLLBACK;
~~~

After `ROLLBACK`, the table created inside that transaction no longer exists (assuming none existed beforehand). Correspondingly, its catalog metadata is not committed.

**Important distinction:** PostgreSQL's catalogs are transactional, yet not every administrative command is allowed inside a transaction block; for example, `CREATE DATABASE` cannot normally execute inside an explicit transaction block.

### 2.2. pg_catalog is not the same as information_schema

`pg_catalog` holds PostgreSQL-specific catalogs and functions, offering deep visibility into how PostgreSQL stores and manages objects.

`information_schema` provides SQL-standard metadata views at a more portable abstraction level, often convenient for tools aiming to minimize engine-specific coupling.

Example:

~~~sql
-- PostgreSQL-specific:
SELECT c.relname, c.relkind
FROM pg_catalog.pg_class AS c
WHERE c.relname = 'demo_item';

-- Information Schema:
SELECT table_schema, table_name, table_type
FROM information_schema.tables
WHERE table_name = 'demo_item';
~~~

These two sources serve different goals; results can also differ due to object classification and **the connected role's privileges**.

## 3. What Is an OID?

An **OID (Object Identifier)** is an internal identifier PostgreSQL assigns to many database objects and catalog rows. The `oid` type is an unsigned **4-byte** integer in PostgreSQL.

When you create a table, PostgreSQL assigns an OID to its entry in `pg_class`. When you create a schema, it gets an OID in `pg_namespace`. When you define a type, it gets an OID in `pg_type`.

Example of how catalogs link together:

~~~text
pg_namespace
  oid = 18420, nspname = 'catalog_lab'
             ^
             |
             | pg_class.relnamespace
             |
pg_class
  oid = 18451, relname = 'nhan_vien'
             ^
             |
             | pg_attribute.attrelid
             |
pg_attribute
  attrelid = 18451, attname = 'ho_ten'
~~~

**The numbers above are illustrative only.** Real OIDs are assigned dynamically per environment; never predict or hard-code `18451` in application code.

### 3.1. What to keep in mind about OIDs

- OIDs identify **objects within the current catalog/cluster context**.
- OIDs appear in `oid` columns and foreign-reference columns such as `relnamespace`, `attrelid`, and `atttypid`.
- OIDs allow fast, unambiguous metadata joins without relying solely on object names.
- An OID is an internal identifier, **never a business identifier** like a customer ID or order ID.
- Never assume an OID value is meaningful or unique across different PostgreSQL servers, databases, or catalogs.
- OIDs have finite 32-bit width; values can wrap or be reused according to internal rules.
- After `pg_dump`/restore or dropping and recreating an object, its OID **can change** even if name and structure match.
- A table's OID does not equal its disk file path or physical filename.

**Rule:** use OIDs when joining catalogs inside a live environment at a point in time; use **schema-qualified names, migrations, and business keys** to identify objects reliably across deployments.

### 3.2. Why is a bare OID insufficient to identify every object?

Many catalogs have an `oid` column: `pg_class`, `pg_type`, `pg_proc`, `pg_namespace`, and more. A raw integer without context cannot tell you whether it refers to a table, function, or data type.

When tracking dependencies, PostgreSQL therefore stores **the catalog containing the object**, **the object's OID**, and sometimes **a sub-object number**. We will see this trio in `pg_depend`.

## 4. regclass, regtype, and Mapping Names to OIDs

Instead of manually looking up raw OID integers, PostgreSQL provides object-identifier alias types such as:

| Alias type | Resolves | Example |
|---|---|---|
| `regclass` | Relation: table, view, index, sequence... | `'catalog_lab.nhan_vien'::regclass` |
| `regtype` | Data type | `'numeric'::regtype` |
| `regnamespace` | Schema | `'catalog_lab'::regnamespace` |
| `regproc` | Function by name (limited when overloaded) | `'lower'::regproc` |
| `regprocedure` | Specific function by name and argument types | `'lower(text)'::regprocedure` |
| `regrole` | Role | `'some_role'::regrole` |

These types let you write SQL using human-readable object names that PostgreSQL resolves to OIDs automatically.

The next query runs once `catalog_lab.nhan_vien` is created in the practice section:

~~~sql
SELECT
    'catalog_lab.nhan_vien'::regclass AS relation_name,
    'catalog_lab.nhan_vien'::regclass::oid AS relation_oid;
~~~

Casting `::regclass` resolves the relation by name. Casting further to `::oid` extracts its numeric OID.

If the object does not exist, casting directly to `regclass` raises an error. To check existence safely without failing:

~~~sql
SELECT to_regclass('catalog_lab.nhan_vien') AS existing_relation;
SELECT to_regclass('catalog_lab.khong_ton_tai') AS missing_relation;
~~~

`to_regclass` returns `NULL` if no matching relation is found under name-resolution rules, rather than aborting the query with an invalid-cast error.

### 4.1. search_path affects resolved names and display formatting

PostgreSQL uses `search_path` to resolve unqualified names:

~~~sql
SHOW search_path;
~~~

The query:

~~~sql
SELECT 'nhan_vien'::regclass;
~~~

succeeds only if `nhan_vien` is visible along the active schema search path. Even **displaying** a `regclass` value omits the schema prefix if the object is unambiguous in `search_path`.

To avoid ambiguity in administrative queries and documentation, prefer:

~~~sql
SELECT 'catalog_lab.nhan_vien'::regclass;
~~~

If schema or table names contain quoted uppercase letters or special characters, follow PostgreSQL's identifier-quoting rules. Never concatenate untrusted user input directly into administrative SQL.

## 5. Setting Up the Practice Environment

We will build a small model and inspect its objects across multiple catalogs.

Model:

~~~text
Schema: catalog_lab
  |
  +-- Table: phong_ban
  |       +-- PK: phong_ban_id
  |       +-- UNIQUE: ten_phong
  |
  +-- Table: nhan_vien
  |       +-- PK: nhan_vien_id
  |       +-- FK: phong_ban_id --> phong_ban
  |       +-- UNIQUE: email
  |       +-- CHECK: luong >= 0
  |       +-- Index: idx_nhan_vien_ho_ten
  |
  +-- View: v_nhan_vien
  |       +-- Depends on nhan_vien and phong_ban
  |
  +-- Sequence: so_phieu_seq
  |
  +-- Function: luong_tang_10pct(numeric)
~~~

**Use only a disposable test database.** The DDL below contains `DROP SCHEMA ... CASCADE`, which deletes every object in `catalog_lab` and any dependent objects. Never run it in production or a shared database without confirming safety.

### 5.1. Creating the schema, tables, view, sequence, and function

You can save this script as `catalog_lab.sql` and run `psql -v ON_ERROR_STOP=1 --single-transaction -f catalog_lab.sql` on a **lab database**:

~~~sql
-- For resetting in a practice database only.
DROP SCHEMA IF EXISTS catalog_lab CASCADE;
CREATE SCHEMA catalog_lab;

CREATE TABLE catalog_lab.phong_ban (
    phong_ban_id INTEGER PRIMARY KEY,
    ten_phong TEXT NOT NULL UNIQUE
);

CREATE TABLE catalog_lab.nhan_vien (
    nhan_vien_id INTEGER PRIMARY KEY,
    phong_ban_id INTEGER NOT NULL,
    ho_ten TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    luong NUMERIC(12, 2) NOT NULL DEFAULT 0,
    tao_luc TIMESTAMPTZ NOT NULL
        DEFAULT TIMESTAMPTZ '2026-01-01 00:00:00+00',

    CONSTRAINT fk_nhan_vien_phong_ban
        FOREIGN KEY (phong_ban_id)
        REFERENCES catalog_lab.phong_ban(phong_ban_id),

    CONSTRAINT chk_nhan_vien_luong
        CHECK (luong >= 0)
);

CREATE INDEX idx_nhan_vien_ho_ten
ON catalog_lab.nhan_vien (ho_ten);

CREATE VIEW catalog_lab.v_nhan_vien AS
SELECT
    nv.nhan_vien_id,
    nv.ho_ten,
    nv.email,
    pb.ten_phong
FROM catalog_lab.nhan_vien AS nv
JOIN catalog_lab.phong_ban AS pb
    ON pb.phong_ban_id = nv.phong_ban_id;

CREATE SEQUENCE catalog_lab.so_phieu_seq START WITH 1;

CREATE FUNCTION catalog_lab.luong_tang_10pct(p_luong NUMERIC)
RETURNS NUMERIC
LANGUAGE sql
IMMUTABLE
AS $function$
    SELECT p_luong * 1.10
$function$;

COMMENT ON TABLE catalog_lab.nhan_vien
    IS 'Employee table for system catalog lesson';

COMMENT ON COLUMN catalog_lab.nhan_vien.ho_ten
    IS 'Employee full name';

INSERT INTO catalog_lab.phong_ban
    (phong_ban_id, ten_phong)
VALUES
    (1, 'Engineering'),
    (2, 'Sales'),
    (3, 'Support');

INSERT INTO catalog_lab.nhan_vien
    (nhan_vien_id, phong_ban_id, ho_ten, email, luong)
VALUES
    (101, 1, 'Nguyễn An',  'an@example.test',   16000000.00),
    (102, 1, 'Trần Bình',  'binh@example.test', 19000000.00),
    (103, 2, 'Lê Chi',    'chi@example.test',  15000000.00),
    (104, 3, 'Phạm Dũng', 'dung@example.test', 13000000.00);
~~~

These emails use reserved example domains, not real accounts. Data and IDs are fixed for repeatable queries; **OIDs assigned to created objects are not fixed**.

### 5.2. Querying business data with ordinary SQL

~~~sql
SELECT
    nv.nhan_vien_id,
    nv.ho_ten,
    pb.ten_phong,
    nv.luong
FROM catalog_lab.nhan_vien AS nv
JOIN catalog_lab.phong_ban AS pb
    ON pb.phong_ban_id = nv.phong_ban_id
ORDER BY nv.nhan_vien_id;
~~~

This queries **business data**. Subsequent sections query the metadata PostgreSQL uses to understand both tables and their relationship.

## 6. Map of Relationships Across Catalogs

An abridged diagram:

~~~text
pg_namespace
    oid <---------------- pg_class.relnamespace
                                |
                                | pg_class.oid
                                |
                     +----------+-------------------+
                     |          |                   |
                     v          v                   v
        pg_attribute.attrelid  pg_index.indrelid   pg_constraint.conrelid
             |                   |
             | atttypid          | indexrelid
             v                   v
           pg_type          pg_class (index relation)

pg_constraint.confrelid -----> pg_class (table referenced by FK)
pg_constraint.conkey --------> pg_attribute.attnum (source column)
pg_constraint.confkey -------> pg_attribute.attnum (target column)

pg_rewrite.ev_class ---------> pg_class (view)
pg_depend.classid/objid -----> Dependent object
pg_depend.refclassid/refobjid -> Referenced object

pg_proc.pronamespace --------> pg_namespace
pg_description.classoid/objoid -> Commented object
~~~

Note: this diagram covers only **part** of PostgreSQL's catalog model, not every internal relationship. Additional catalogs come into play when studying partitions, roles, triggers, extensions, or replication in depth.

**Secret to reading catalogs:** always ask "Which catalog does this OID belong to?" and "Is this an object OID or a column position (`attnum`)?" Never join two columns blindly just because both have similar names or type `oid`.

## 7. pg_namespace: How Are Schemas Identified?

`pg_namespace` stores schema definitions, including:

- `oid`: OID of the schema.
- `nspname`: schema name.
- `nspowner`: OID of the owning role.
- `nspacl`: schema-level access privileges when configured.

Query:

~~~sql
SELECT
    n.oid AS schema_oid,
    n.nspname AS schema_name,
    n.nspowner AS owner_oid
FROM pg_catalog.pg_namespace AS n
WHERE n.nspname = 'catalog_lab';
~~~

Once the schema exists, this returns one row for `catalog_lab`. The `schema_oid` value depends on the database/cluster at creation time.

Common system schemas:

- `pg_catalog`: system catalogs and built-in functions/types.
- `information_schema`: SQL-standard metadata views.
- `pg_toast`: internal relations for PostgreSQL's out-of-line large-value storage.
- Temporary schemas such as `pg_temp_N` created per session as needed.
- `public`: default schema commonly present in new databases.
- User-created schemas such as `catalog_lab`.

The command:

~~~sql
CREATE SCHEMA catalog_lab;
~~~

instructs PostgreSQL to create the schema object and populate its catalog metadata; you never manually `INSERT` into `pg_namespace`.

## 8. pg_class: The Catalog of Relations

The name `pg_class` can mislead because of the word "class," yet in PostgreSQL it represents **relations** broadly: tables, indexes, views, materialized views, sequences, and similar relation-like objects.

Key columns:

| Column | Meaning |
|---|---|
| `oid` | OID of the relation |
| `relname` | Relation name |
| `relnamespace` | OID of the owning schema, linking to `pg_namespace.oid` |
| `relkind` | Kind of relation |
| `relowner` | OID of the owning role |
| `relpersistence` | Permanent, unlogged, or temporary persistence mode |
| `reltype` | OID of the matching composite row type, if any |
| `reltuples` | Statistical estimate of row count |
| `relpages` | Statistical estimate of data page count |
| `relfilenode` | Physical storage file identifier, **not identical to OID** |

Common `relkind` values:

| relkind | Kind |
|---|---|
| `r` | Ordinary table |
| `p` | Partitioned table |
| `i` | Ordinary index |
| `I` | Partitioned index |
| `v` | View |
| `m` | Materialized view |
| `S` | Sequence |
| `f` | Foreign table |
| `c` | Composite type relation |
| `t` | TOAST table |

These codes are PostgreSQL-specific and may expand in newer versions.

### 8.1. Listing relations in the lab schema

~~~sql
SELECT
    n.nspname AS schema_name,
    c.relname AS relation_name,
    c.oid AS relation_oid,
    c.relkind,
    c.oid::regclass AS regclass_name
FROM pg_catalog.pg_class AS c
JOIN pg_catalog.pg_namespace AS n
    ON n.oid = c.relnamespace
WHERE n.nspname = 'catalog_lab'
ORDER BY c.relkind, c.relname;
~~~

Here:

- `c.relnamespace` is the schema OID.
- `n.oid` is the matching schema record's OID in `pg_namespace`.
- `c.oid::regclass` formats the OID back into a readable relation name per PostgreSQL resolution rules.

Output includes tables `phong_ban` and `nhan_vien`, view `v_nhan_vien`, sequence `so_phieu_seq`, and indexes (including indexes created automatically for `PRIMARY KEY`/`UNIQUE` constraints). **Never hard-code assumed auto-generated index names**; read actual names in your environment.

### 8.2. Why does pg_class contain more than tables?

Indexes are relations with their own metadata, so they appear in `pg_class`. Views are also cataloged as relations even though ordinary views do not store materialized row heaps. Sequences likewise have relation entries and metadata.

Consequently, running:

~~~sql
SELECT relname
FROM pg_catalog.pg_class;
~~~

returns far more than "a list of application tables." Always filter by `relkind` and schema for your goal.

### 8.3. reltuples is an estimate

~~~sql
SELECT
    c.relname,
    c.reltuples,
    c.relpages
FROM pg_catalog.pg_class AS c
WHERE c.oid = 'catalog_lab.nhan_vien'::regclass;
~~~

`reltuples` is updated by `VACUUM`/`ANALYZE` and similar tasks, not instantaneously like a live `COUNT(*)`. Never use it as an exact row count for financial reporting or data-loading verification.

## 9. pg_attribute: Which Relation Owns Each Column?

`pg_attribute` stores metadata about relation columns/attributes. Key columns:

- `attrelid`: OID of the owning relation, pointing to `pg_class.oid`.
- `attname`: column name.
- `attnum`: column position number within the relation.
- `atttypid`: OID of the data type, pointing to `pg_type.oid`.
- `atttypmod`: type-specific modifier (e.g., precision/scale or length).
- `attnotnull`: metadata flag indicating `NOT NULL`.
- `attisdropped`: marks logically dropped columns whose internal metadata remains temporarily.

Query:

~~~sql
SELECT
    a.attrelid::regclass AS relation_name,
    a.attnum AS column_position,
    a.attname AS column_name,
    a.atttypid AS type_oid,
    a.attnotnull
FROM pg_catalog.pg_attribute AS a
WHERE a.attrelid = 'catalog_lab.nhan_vien'::regclass
  AND a.attnum > 0
  AND NOT a.attisdropped
ORDER BY a.attnum;
~~~

Why include these filters:

- `attnum > 0`: selects user columns only, excluding system attributes (`ctid`, `xmin`, etc.) that carry negative `attnum`s.
- `NOT attisdropped`: excludes columns removed via `DROP COLUMN`.

**Never read all of `pg_attribute` assuming every row is a user-created column.** PostgreSQL stores system attributes and attributes for other relation types there too.

### 9.1. Joining pg_attribute with pg_type

To retrieve type names:

~~~sql
SELECT
    a.attnum,
    a.attname,
    t.typname,
    pg_catalog.format_type(
        a.atttypid,
        a.atttypmod
    ) AS display_type
FROM pg_catalog.pg_attribute AS a
JOIN pg_catalog.pg_type AS t
    ON t.oid = a.atttypid
WHERE a.attrelid = 'catalog_lab.nhan_vien'::regclass
  AND a.attnum > 0
  AND NOT a.attisdropped
ORDER BY a.attnum;
~~~

Notice the difference:

- `typname`: internal type name (e.g., `numeric`).
- `format_type`: DDL-friendly formatted type such as `numeric(12,2)` rather than just a raw type OID.

Using `format_type` is far safer and cleaner than trying to decode `atttypmod` manually for parameterized types.

### 9.2. A data type's OID is not the column's OID

Suppose `luong` has type `NUMERIC(12,2)`. `atttypid` identifies the **`numeric` data type**, while `atttypmod` encodes precision and scale. Columns do not have their own standalone OIDs in `pg_attribute`; catalogs identify a column by the pair **(relation OID, `attnum`)**.

This is a classic illustration of **why not every sub-object has its own single OID**.

## 10. pg_type: Data Type Metadata

`pg_type` catalogs PostgreSQL data types:

- Built-in types such as `integer`, `text`, `numeric`, and `timestamp`.
- Composite types (including row types linked to relations).
- Enum, domain, range, and extension types.
- Associated array types.

Notable columns:

| Column | Meaning |
|---|---|
| `oid` | Type OID |
| `typname` | Type name |
| `typnamespace` | Schema containing the type |
| `typtype` | Type category (`b` base, `c` composite, `d` domain, `e` enum, etc.) |
| `typrelid` | Associated relation OID for composite types |
| `typelem` | Element type OID for array types |
| `typbasetype` | Underlying base type for domains |

Example:

~~~sql
SELECT
    t.oid AS type_oid,
    t.typname,
    t.typtype,
    n.nspname AS schema_name
FROM pg_catalog.pg_type AS t
JOIN pg_catalog.pg_namespace AS n
    ON n.oid = t.typnamespace
WHERE t.oid IN (
    'integer'::regtype,
    'text'::regtype,
    'numeric'::regtype
)
ORDER BY t.typname;
~~~

### 10.1. Tables have an associated row type

In PostgreSQL, a table automatically has a corresponding composite row type. `pg_class.reltype` points to that type's OID in `pg_type`.

~~~sql
SELECT
    c.oid::regclass AS relation_name,
    c.reltype AS row_type_oid,
    t.typname AS row_type_name,
    t.typtype
FROM pg_catalog.pg_class AS c
JOIN pg_catalog.pg_type AS t
    ON t.oid = c.reltype
WHERE c.oid = 'catalog_lab.nhan_vien'::regclass;
~~~

This is a **relation → type** link distinct from **column → type**. It explains why PostgreSQL allows using a table's row type as a composite type in SQL expressions and functions.

## 11. pg_attrdef: Where Are Column Defaults Stored?

The declaration:

~~~sql
luong NUMERIC(12, 2) NOT NULL DEFAULT 0
~~~

is not stored merely as raw DDL text. Default expressions are stored structurally in `pg_attrdef`, which holds:

- `adrelid`: OID of the table/relation.
- `adnum`: column `attnum`.
- `adbin`: internal parsed node-tree representation of the default expression.

You can join `pg_attribute` with `pg_attrdef`:

~~~sql
SELECT
    a.attnum,
    a.attname,
    pg_catalog.format_type(
        a.atttypid,
        a.atttypmod
    ) AS data_type,
    pg_catalog.pg_get_expr(
        d.adbin,
        d.adrelid
    ) AS default_expression
FROM pg_catalog.pg_attribute AS a
LEFT JOIN pg_catalog.pg_attrdef AS d
    ON d.adrelid = a.attrelid
   AND d.adnum = a.attnum
WHERE a.attrelid = 'catalog_lab.nhan_vien'::regclass
  AND a.attnum > 0
  AND NOT a.attisdropped
ORDER BY a.attnum;
~~~

`pg_get_expr` deparses the stored internal expression into readable SQL. **Never parse `adbin` text manually as raw SQL**, because its internal format is not a stable application interface.

## 12. pg_constraint: Where Do Constraints Live?

PostgreSQL stores constraints in `pg_constraint`. Important columns:

| Column | Meaning |
|---|---|
| `oid` | Constraint OID |
| `conname` | Constraint name |
| `contype` | Constraint type |
| `conrelid` | Owning table OID, if a table constraint |
| `contypid` | Owning domain OID, if a domain constraint |
| `confrelid` | Referenced table OID for foreign keys |
| `conkey` | Array of source column `attnum`s |
| `confkey` | Array of referenced column `attnum`s |
| `condeferrable` | Whether checking can be deferred |
| `condeferred` | Whether deferred by default |
| `convalidated` | Whether the constraint has been validated in catalog state |

Common `contype` codes:

- `p`: primary key.
- `u`: unique constraint.
- `f`: foreign key.
- `c`: check constraint.
- `x`: exclusion constraint.

Check documentation for your server version for additional constraint types or newer version variations.

### 12.1. Listing constraints on a table

~~~sql
SELECT
    con.oid AS constraint_oid,
    con.conname,
    con.contype,
    con.conrelid::regclass AS source_relation,
    CASE
        WHEN con.confrelid = 0 THEN NULL
        ELSE con.confrelid::regclass
    END AS referenced_relation,
    pg_catalog.pg_get_constraintdef(
        con.oid,
        true
    ) AS definition
FROM pg_catalog.pg_constraint AS con
WHERE con.conrelid = 'catalog_lab.nhan_vien'::regclass
ORDER BY con.contype, con.conname;
~~~

Results show the primary key, unique constraint on email, foreign key `fk_nhan_vien_phong_ban`, and check constraint `chk_nhan_vien_luong`. How `NOT NULL` constraints appear can vary across PostgreSQL versions, so do not treat `pg_constraint` as the sole place to inspect nullability everywhere.

### 12.2. Foreign keys link two tables by OID

For the foreign key:

~~~sql
FOREIGN KEY (phong_ban_id)
REFERENCES catalog_lab.phong_ban(phong_ban_id)
~~~

the catalog records:

~~~text
pg_constraint
  contype  = 'f'
  conrelid = OID of catalog_lab.nhan_vien
  confrelid = OID of catalog_lab.phong_ban
  conkey   = {attnum of phong_ban_id in nhan_vien}
  confkey  = {attnum of phong_ban_id in phong_ban}
~~~

This metadata represents the **foreign-key relationship between two tables**. When an application inserts an employee with a nonexistent `phong_ban_id`, the engine enforces this constraint to reject the operation.

### 12.3. Mapping conkey/confkey to actual column names

A foreign key can span multiple columns. Never assume an FK always has a single column. PostgreSQL stores `attnum` arrays; you can use `unnest(...) WITH ORDINALITY` to align source and referenced columns positionally:

~~~sql
SELECT
    con.conname,
    con.conrelid::regclass AS source_table,
    src_att.attname AS source_column,
    con.confrelid::regclass AS referenced_table,
    ref_att.attname AS referenced_column,
    keys.ordinal_position
FROM pg_catalog.pg_constraint AS con
CROSS JOIN LATERAL unnest(
    con.conkey,
    con.confkey
) WITH ORDINALITY
    AS keys(source_attnum, referenced_attnum, ordinal_position)
JOIN pg_catalog.pg_attribute AS src_att
    ON src_att.attrelid = con.conrelid
   AND src_att.attnum = keys.source_attnum
JOIN pg_catalog.pg_attribute AS ref_att
    ON ref_att.attrelid = con.confrelid
   AND ref_att.attnum = keys.referenced_attnum
WHERE con.contype = 'f'
  AND con.conrelid = 'catalog_lab.nhan_vien'::regclass
ORDER BY con.conname, keys.ordinal_position;
~~~

Meaning:

- `conrelid` points to the table holding the FK.
- `confrelid` points to the referenced parent table.
- `conkey` and `confkey` are parallel `attnum` arrays in matching component order.
- `WITH ORDINALITY` preserves column pairing order for composite FKs.
- `pg_attribute` translates numeric `attnum`s into readable column names.

This is a textbook example of **joining multiple catalogs to reconstruct DDL structure**.

## 13. pg_index: Indexes Also Have Their Own OIDs and Relations

An index has a relation row in `pg_class` plus index-specific metadata in `pg_index`.

Key columns:

- `indexrelid`: OID of the index relation itself.
- `indrelid`: OID of the table/relation being indexed.
- `indisunique`: whether uniqueness is enforced.
- `indisprimary`: whether the index backs the primary key.
- `indisvalid`: whether the index is valid for query use.
- `indkey`: column `attnum`s indexed (0 indicates an expression, requiring further metadata).
- `indexprs`: internal representation of index expressions.
- `indpred`: predicate for partial indexes.

### 13.1. Viewing indexes on nhan_vien

~~~sql
SELECT
    i.indexrelid::regclass AS index_name,
    i.indrelid::regclass AS table_name,
    i.indisprimary,
    i.indisunique,
    i.indisvalid,
    pg_catalog.pg_get_indexdef(i.indexrelid) AS create_index_sql
FROM pg_catalog.pg_index AS i
WHERE i.indrelid = 'catalog_lab.nhan_vien'::regclass
ORDER BY i.indexrelid::regclass::text;
~~~

You will see at least:

- The index for `PRIMARY KEY (nhan_vien_id)`.
- The index for `UNIQUE (email)`.
- The explicit index `idx_nhan_vien_ho_ten`.

Auto-generated constraint index names follow PostgreSQL naming rules and avoid collisions with existing names; use `pg_get_indexdef` rather than guessing index names outside demos.

### 13.2. An index is not a foreign key

A common misconception is that adding a `FOREIGN KEY` automatically indexes the **referencing column on the child table**. PostgreSQL requires a matching primary/unique index on the referenced parent columns, but **does not automatically create indexes on child-side FK columns**.

For example, if an application frequently filters employees by department:

~~~sql
SELECT *
FROM catalog_lab.nhan_vien
WHERE phong_ban_id = 1;
~~~

you might add:

~~~sql
CREATE INDEX idx_nhan_vien_phong_ban
ON catalog_lab.nhan_vien (phong_ban_id);
~~~

This DDL adds a new index relation in `pg_class` and metadata in `pg_index`. Whether to create it depends on query patterns, table size, selectivity, and write overhead—not merely the existence of an FK.

### 13.3. Why avoid decoding indkey manually?

`indkey` involves `attnum` arrays and special cases like expression indexes. For general index DDL inspection, use:

~~~sql
SELECT pg_catalog.pg_get_indexdef(
    'catalog_lab.idx_nhan_vien_ho_ten'::regclass
);
~~~

Similarly, `pg_indexes` provides a convenient user-level view of indexes and their `indexdef`:

~~~sql
SELECT schemaname, tablename, indexname, indexdef
FROM pg_catalog.pg_indexes
WHERE schemaname = 'catalog_lab'
ORDER BY tablename, indexname;
~~~

There is no need to parse internal storage trees when PostgreSQL already provides built-in deparsing functions.

## 14. Views: Why Aren't Dependencies Just a Column in pg_class?

A view such as:

~~~sql
CREATE VIEW catalog_lab.v_nhan_vien AS
SELECT
    nv.nhan_vien_id,
    nv.ho_ten,
    pb.ten_phong
FROM catalog_lab.nhan_vien AS nv
JOIN catalog_lab.phong_ban AS pb
    ON pb.phong_ban_id = nv.phong_ban_id;
~~~

references two tables. PostgreSQL must track those references so dropping or altering an underlying table does not silently break the view.

**Yet a view's dependencies are not stored as a simple "`parent_table_oid`" column in `pg_class`.** PostgreSQL stores the view's rewrite rule in `pg_rewrite` and records dependency edges in `pg_depend`.

### 14.1. Viewing a view definition

~~~sql
SELECT pg_catalog.pg_get_viewdef(
    'catalog_lab.v_nhan_vien'::regclass,
    true
) AS view_definition;
~~~

`pg_get_viewdef` returns the readable SQL query defining the view—far easier than decoding internal rewrite trees.

### 14.2. pg_rewrite represents the view's rule

Notable columns:

- `pg_rewrite.oid`: OID of the rule.
- `pg_rewrite.ev_class`: OID of the relation owning the rule (the view here).
- `pg_rewrite.rulename`: rule name; views use an `_RETURN` rule for queries.
- Metadata for command/event and the internal query tree.

You can inspect it:

~~~sql
SELECT
    r.oid AS rule_oid,
    r.rulename,
    r.ev_class::regclass AS view_name
FROM pg_catalog.pg_rewrite AS r
WHERE r.ev_class = 'catalog_lab.v_nhan_vien'::regclass
ORDER BY r.rulename;
~~~

Crucial insight when analyzing dependencies: **references to underlying tables in a view are attached to the view's rewrite rule**, so inspecting only direct dependencies of the view's `pg_class` OID will miss the expected table edges.

## 15. pg_depend: How Does PostgreSQL Record Object Dependencies?

A **dependency** tracks **database object lifecycles**: if object A relies on object B, PostgreSQL must know whether B can be dropped/altered or whether A must be dropped alongside B.

`pg_depend` stores these key fields:

| Column | Meaning |
|---|---|
| `classid` | OID of the catalog containing the **dependent** object |
| `objid` | OID of the dependent object inside that catalog |
| `objsubid` | Sub-object number (typically column `attnum`); `0` if whole object |
| `refclassid` | OID of the catalog containing the **referenced** object |
| `refobjid` | OID of the referenced object |
| `refobjsubid` | Sub-object number of the referenced object |
| `deptype` | Dependency type governing drop/alter behavior |

Visualize a dependency edge:

~~~text
Dependent object
    classid, objid, objsubid
                   |
                   v
Referenced object
    refclassid, refobjid, refobjsubid
~~~

### 15.1. Why is classid necessary?

A numeric `objid` is meaningless unless you know which catalog it lives in. `classid` identifies the catalog, and `objid` identifies the specific row within that catalog.

For example, if `classid = 'pg_rewrite'::regclass`, `objid` is a rule OID in `pg_rewrite`. If `classid = 'pg_class'::regclass`, `objid` identifies a relation in `pg_class`.

This is the difference between **a bare OID integer** and **a complete metadata reference**.

### 15.2. Common deptype codes

- `n` — **normal dependency**: the dependent object requires the referenced object; `DROP` is normally blocked unless dependencies are handled.
- `a` — **auto dependency**: the dependent object is dropped automatically when the referenced object is dropped.
- `i` — **internal dependency**: the object is managed as an internal component of another object and cannot be manipulated independently.
- `e` — **extension dependency**: the object belongs to an extension and follows the extension's lifecycle.

Different PostgreSQL versions also use specialized dependency codes (e.g., for partitioning). Never write admin scripts assuming `deptype` only ever takes those four values.

### 15.3. Tracing which tables a view depends on

Because view dependencies attach to `pg_rewrite`, join `pg_rewrite` and `pg_depend` to discover referenced relations:

~~~sql
SELECT DISTINCT
    r.ev_class::regclass AS dependent_view,
    referred.oid::regclass AS referenced_relation,
    d.deptype
FROM pg_catalog.pg_rewrite AS r
JOIN pg_catalog.pg_depend AS d
    ON d.classid = 'pg_catalog.pg_rewrite'::regclass
   AND d.objid = r.oid
JOIN pg_catalog.pg_class AS referred
    ON d.refclassid = 'pg_catalog.pg_class'::regclass
   AND d.refobjid = referred.oid
WHERE r.ev_class = 'catalog_lab.v_nhan_vien'::regclass
  AND r.rulename = '_RETURN'
  AND referred.oid <> r.ev_class
ORDER BY referenced_relation::text, d.deptype;
~~~

For our demo view, dependencies point to `catalog_lab.nhan_vien` and `catalog_lab.phong_ban`. Column-level dependencies also exist via `refobjsubid`, so `DISTINCT` collapses multiple column edges onto the same table when you only want relation names.

**Exact dependency edges depend on how PostgreSQL stores metadata per object type.** This query illustrates views specifically; do not treat it as a universal algorithm for every object kind.

### 15.4. DROP RESTRICT and DROP CASCADE

Suppose a view depends on a table. Running:

~~~sql
-- Conceptual example only; do not run where data must be preserved:
DROP TABLE catalog_lab.nhan_vien;
~~~

normally fails because dependent objects like views still reference it. PostgreSQL suggests `CASCADE`, yet:

~~~sql
-- EXTREME CAUTION: may drop dependent objects.
DROP TABLE catalog_lab.nhan_vien CASCADE;
~~~

can drop dependent views, constraints, and other objects automatically per PostgreSQL dependency rules.

`CASCADE` on **`DROP` DDL** is completely different from `ON DELETE CASCADE` on a **foreign key**. One drops schema objects; the other deletes **data rows** when a referenced parent row is deleted.

Never run `CASCADE` in production just to "make the DROP go through." Inspect the full dependency graph and blast radius first.

## 16. Foreign Keys Are Not the Same as pg_depend

Two frequently confused concepts:

### 16.1. Foreign keys are data constraints

~~~sql
FOREIGN KEY (phong_ban_id)
REFERENCES catalog_lab.phong_ban(phong_ban_id)
~~~

Meaning: every `phong_ban_id` in `nhan_vien` must match a valid value in `phong_ban` subject to transaction state and constraint rules.

Primary metadata describing FKs lives in `pg_constraint`.

### 16.2. pg_depend tracks object dependencies

`pg_depend` governs DDL operations like `DROP TABLE`, `DROP VIEW`, `DROP TYPE`, and `DROP EXTENSION` across interrelated schema objects.

~~~text
FOREIGN KEY:
  Relationship between data/columns of two tables,
  enforcing INSERT/UPDATE/DELETE checks.

pg_depend:
  Lifecycle relationship between schema objects,
  controlling DROP/ALTER and metadata integrity.
~~~

An FK itself also creates internal dependency edges, yet **never replace a `pg_constraint` query with an ad-hoc `pg_depend` join** expecting it to describe all foreign-key constraints.

## 17. pg_proc: Functions and Procedures Are OID-Identified Objects

PostgreSQL stores function and procedure metadata in `pg_proc`. Notable fields:

- `oid`: OID of the routine.
- `proname`: routine name.
- `pronamespace`: schema OID.
- `proowner`: owning role.
- `prorettype`: return data type OID.
- `proargtypes`: input argument types in catalog representation.
- `prokind`: distinguishes functions, procedures, aggregates, and window functions.

Querying our created routines:

~~~sql
SELECT
    p.oid AS routine_oid,
    n.nspname AS schema_name,
    p.proname AS routine_name,
    p.prokind,
    pg_catalog.pg_get_function_identity_arguments(
        p.oid
    ) AS identity_arguments,
    pg_catalog.pg_get_function_result(
        p.oid
    ) AS result_type
FROM pg_catalog.pg_proc AS p
JOIN pg_catalog.pg_namespace AS n
    ON n.oid = p.pronamespace
WHERE n.nspname = 'catalog_lab'
ORDER BY p.proname;
~~~

Because PostgreSQL supports **overloading** (multiple functions sharing a name with different parameter types), a bare function name does not always uniquely identify a routine.

Example:

~~~sql
SELECT
    'catalog_lab.luong_tang_10pct(numeric)'::regprocedure
        AS function_identity;

SELECT catalog_lab.luong_tang_10pct(100.00) AS luong_moi;
~~~

The `regprocedure` type identifies a routine by **name plus parameter signature**, avoiding ambiguity when overloads exist.

**Never store function OIDs in application configs for long-term use.** Dropping/recreating or restoring a routine can change its OID. Rely on schema-qualified names/signatures and migrations.

## 18. pg_description: Where Are COMMENTs Stored?

PostgreSQL supports comments on tables, columns, functions, and many other objects:

~~~sql
COMMENT ON TABLE catalog_lab.nhan_vien
    IS 'Employee table for system catalog lesson';

COMMENT ON COLUMN catalog_lab.nhan_vien.ho_ten
    IS 'Employee full name';
~~~

Descriptions can be read using built-in helper functions:

~~~sql
SELECT pg_catalog.obj_description(
    'catalog_lab.nhan_vien'::regclass,
    'pg_class'
) AS table_comment;

SELECT pg_catalog.col_description(
    'catalog_lab.nhan_vien'::regclass,
    3
) AS column_comment;
~~~

In our demo schema, `ho_ten` is column 3 (`attnum = 3`). If column order changes after recreating a table, hard-coding `3` breaks; resolve `attnum` by column name instead:

~~~sql
SELECT
    a.attname,
    pg_catalog.col_description(
        a.attrelid,
        a.attnum
    ) AS column_comment
FROM pg_catalog.pg_attribute AS a
WHERE a.attrelid = 'catalog_lab.nhan_vien'::regclass
  AND a.attnum > 0
  AND NOT a.attisdropped
ORDER BY a.attnum;
~~~

`pg_description` uses `classoid`, `objoid`, and `objsubid` to attach descriptions to objects or sub-objects (columns)—another example of **OIDs paired with catalog identity and attribute numbers**.

## 19. pg_database and Shared Catalogs

A PostgreSQL cluster can contain multiple databases, each with its own schemas and objects. Catalogs like `pg_database` describe cluster-wide objects.

~~~sql
SELECT
    oid AS database_oid,
    datname AS database_name,
    datallowconn AS allows_connection
FROM pg_catalog.pg_database
ORDER BY datname;
~~~

Unlike per-database catalogs such as `pg_class` and `pg_attribute`, `pg_database` is a **shared** catalog across the whole cluster. Keep scope in mind when interpreting OIDs.

Role and membership metadata are similarly cluster-wide rather than scoped to a single database.

### 19.1. Roles and privileges

Avoid querying sensitive authentication catalogs like `pg_authid` directly without proper privileges and justification. The `pg_roles` view exposes role metadata safely for observation:

~~~sql
SELECT
    oid,
    rolname,
    rolcanlogin,
    rolsuper
FROM pg_catalog.pg_roles
ORDER BY rolname;
~~~

To check table privileges:

~~~sql
SELECT
    current_user AS active_role,
    pg_catalog.has_table_privilege(
        current_user,
        'catalog_lab.nhan_vien',
        'SELECT'
    ) AS can_select;
~~~

**Knowing a table's OID never bypasses authorization**. Reading metadata and reading table data are separate privileges, both enforced by PostgreSQL.

## 20. Partitions and Inheritance: pg_inherits

PostgreSQL supports structures beyond flat tables, including declarative partitioning and table inheritance. `pg_inherits` records parent–child relation links.

Key columns:

- `inhrelid`: child relation OID.
- `inhparent`: parent relation OID.
- `inhseqno`: sequence number within inheritance hierarchy.

General inspection query:

~~~sql
SELECT
    child.oid::regclass AS child_relation,
    parent.oid::regclass AS parent_relation,
    inh.inhseqno
FROM pg_catalog.pg_inherits AS inh
JOIN pg_catalog.pg_class AS child
    ON child.oid = inh.inhrelid
JOIN pg_catalog.pg_class AS parent
    ON parent.oid = inh.inhparent
ORDER BY parent.oid::regclass::text,
         child.oid::regclass::text;
~~~

If your lab schema only contains ordinary tables with no partitions or inheritance, returning zero rows for `catalog_lab` is completely expected.

A partitioned table has `pg_class.relkind = 'p'`; each leaf partition is its own relation with its own metadata. Never assume all partitioned rows reside inside one physical parent table just because a parent table name exists.

## 21. Extensions and Dependencies

PostgreSQL packages types, functions, and objects via extensions, tracked in `pg_extension`.

~~~sql
SELECT
    e.oid AS extension_oid,
    e.extname AS extension_name,
    e.extversion,
    n.nspname AS schema_name
FROM pg_catalog.pg_extension AS e
JOIN pg_catalog.pg_namespace AS n
    ON n.oid = e.extnamespace
ORDER BY e.extname;
~~~

An extension owns objects whose lifecycles tie to the extension. In `pg_depend`, `deptype = 'e'` records those extension dependencies.

When inspecting installed extensions:

~~~sql
-- Illustrates how to inspect extensions;
-- do not install extensions without permission or need.
SELECT extname, extversion
FROM pg_catalog.pg_extension
ORDER BY extname;
~~~

On managed PostgreSQL services, allowed extensions and installation privileges may be restricted by the provider. Being able to query `pg_extension` does not imply permission to run `CREATE EXTENSION`.

## 22. pg_trigger: Triggers Also Have Catalog Entries

Table triggers are cataloged in `pg_trigger`. Key columns:

- `oid`: trigger OID.
- `tgname`: trigger name.
- `tgrelid`: OID of the table owning the trigger.
- `tgfoid`: OID of the trigger function invoked.
- `tgisinternal`: whether the trigger is an internal PostgreSQL constraint trigger.

Listing **non-internal** triggers on a table:

~~~sql
SELECT
    t.tgname,
    t.tgrelid::regclass AS on_table,
    t.tgfoid::regprocedure AS trigger_function,
    pg_catalog.pg_get_triggerdef(t.oid) AS definition
FROM pg_catalog.pg_trigger AS t
WHERE t.tgrelid = 'catalog_lab.nhan_vien'::regclass
  AND NOT t.tgisinternal
ORDER BY t.tgname;
~~~

Because our demo defines no user triggers, this returns **0 rows**. That does not mean PostgreSQL uses zero internal triggers: PostgreSQL implements constraint mechanisms such as foreign keys using internal triggers under the hood.

That is why `NOT t.tgisinternal` is essential when auditing user-defined triggers.

## 23. Inspecting Metadata with psql Without Writing Catalog Joins

Many common questions can be answered directly via `psql` meta-commands:

~~~text
\dn                   -- List schemas
\dt catalog_lab.*     -- List tables in lab schema
\dv catalog_lab.*     -- List views
\ds catalog_lab.*     -- List sequences
\di catalog_lab.*     -- List indexes
\d catalog_lab.nhan_vien
\df catalog_lab.*
~~~

Commands starting with `\` are **`psql` meta-commands**, not standard PostgreSQL SQL statements to send over JDBC.

For instance, `\d catalog_lab.nhan_vien` displays:

- Columns, types, and defaults.
- Primary key, unique constraints, and indexes.
- Foreign keys and referencing constraints.
- Comments when verbose options (`\d+`) are used.

Under the hood, `psql` issues metadata queries and formats the results client-side. Understanding catalogs helps you **interpret `psql` output**, without forcing you to hand-write complex catalog joins for every daily task.

## 24. information_schema When Portability Matters

To list basic table and column metadata portably, start with `information_schema`:

~~~sql
SELECT
    table_schema,
    table_name,
    column_name,
    ordinal_position,
    data_type,
    is_nullable,
    column_default
FROM information_schema.columns
WHERE table_schema = 'catalog_lab'
ORDER BY table_name, ordinal_position;
~~~

Advantages:

- View and column names align with SQL-standard metadata conventions.
- Convenient for documentation generators or cross-database tooling minimizing PostgreSQL-specific coupling.
- Automatically filters objects based on the current user's privileges.

However, `information_schema` does not expose PostgreSQL-specific internals at the same depth as `pg_catalog`—such as MVCC, persistence modes, internal dependencies, and storage details.

### 24.1. Which source should you choose?

| Question | Suitable source |
|---|---|
| Which columns does a table have? | `information_schema.columns` or `pg_attribute` |
| How is a specific index defined? | `pg_indexes`, `pg_index`, `pg_get_indexdef` |
| Which columns form a constraint? | `pg_constraint` joined with `pg_attribute` |
| Which schema owns a table/view? | `pg_class` joined with `pg_namespace` |
| Which tables does a view depend on? | `pg_rewrite` and `pg_depend` for deep inspection |
| What is a column's formatted type? | `format_type`, `pg_type` |
| How many exact rows are in a table? | `COUNT(*)` on the business table |
| How many connections are on the server? | `pg_stat_activity` / statistics views |
| Does a role have `SELECT` privilege? | `has_table_privilege` |
| Cross-DBMS metadata extraction | Can start with `information_schema` |

**No single source fits every question.** Choose based on required detail, portability, and privilege scope.

## 25. Common Catalog Queries Used in Practice

### 25.1. Listing user tables in a schema

~~~sql
SELECT
    n.nspname AS schema_name,
    c.relname AS table_name,
    c.oid AS table_oid
FROM pg_catalog.pg_class AS c
JOIN pg_catalog.pg_namespace AS n
    ON n.oid = c.relnamespace
WHERE n.nspname = 'catalog_lab'
  AND c.relkind IN ('r', 'p')
ORDER BY c.relname;
~~~

`'r'` denotes ordinary tables and `'p'` denotes partitioned tables. Views, indexes, and sequences are excluded.

### 25.2. Inspecting columns and data types

~~~sql
SELECT
    a.attnum,
    a.attname,
    pg_catalog.format_type(
        a.atttypid,
        a.atttypmod
    ) AS type_name,
    a.attnotnull
FROM pg_catalog.pg_attribute AS a
WHERE a.attrelid = 'catalog_lab.nhan_vien'::regclass
  AND a.attnum > 0
  AND NOT a.attisdropped
ORDER BY a.attnum;
~~~

### 25.3. Inspecting foreign keys across all tables in a lab schema

~~~sql
SELECT
    con.conname,
    con.conrelid::regclass AS source_table,
    con.confrelid::regclass AS target_table,
    pg_catalog.pg_get_constraintdef(
        con.oid,
        true
    ) AS fk_definition
FROM pg_catalog.pg_constraint AS con
JOIN pg_catalog.pg_class AS c
    ON c.oid = con.conrelid
JOIN pg_catalog.pg_namespace AS n
    ON n.oid = c.relnamespace
WHERE n.nspname = 'catalog_lab'
  AND con.contype = 'f'
ORDER BY source_table::text, con.conname;
~~~

### 25.4. Inspecting indexes and index expressions

~~~sql
SELECT
    i.indexrelid::regclass AS index_name,
    i.indrelid::regclass AS on_table,
    i.indisunique,
    i.indisprimary,
    pg_catalog.pg_get_indexdef(
        i.indexrelid
    ) AS definition
FROM pg_catalog.pg_index AS i
JOIN pg_catalog.pg_class AS c
    ON c.oid = i.indrelid
JOIN pg_catalog.pg_namespace AS n
    ON n.oid = c.relnamespace
WHERE n.nspname = 'catalog_lab'
ORDER BY on_table::text, index_name::text;
~~~

### 25.5. Reading view definitions

~~~sql
SELECT
    c.oid::regclass AS view_name,
    pg_catalog.pg_get_viewdef(c.oid, true) AS definition
FROM pg_catalog.pg_class AS c
JOIN pg_catalog.pg_namespace AS n
    ON n.oid = c.relnamespace
WHERE n.nspname = 'catalog_lab'
  AND c.relkind = 'v'
ORDER BY c.relname;
~~~

### 25.6. Resolving OIDs by name and checking existence

~~~sql
SELECT
    to_regclass('catalog_lab.phong_ban') AS department_table,
    to_regclass('catalog_lab.nhan_vien') AS employee_table,
    to_regclass('catalog_lab.unknown') AS missing_table;
~~~

### 25.7. Displaying table and column comments

~~~sql
SELECT
    c.oid::regclass AS relation_name,
    pg_catalog.obj_description(
        c.oid,
        'pg_class'
    ) AS relation_comment
FROM pg_catalog.pg_class AS c
WHERE c.oid = 'catalog_lab.nhan_vien'::regclass;
~~~

These examples only read metadata. You do not need catalog-modification privileges to inspect database structure.

## 26. OIDs vs. Object Names vs. Physical File Paths

Three concepts easily confused:

**Object name:**

~~~text
catalog_lab.nhan_vien
~~~

**Catalog OID:**

~~~text
Example: 18451
~~~

**Relation storage location:**

~~~text
Managed by PostgreSQL using physical storage structures
and corresponding mapping metadata.
~~~

An object can be renamed via:

~~~sql
-- Theoretical example in a lab environment:
-- ALTER TABLE catalog_lab.nhan_vien RENAME TO nhan_vien_moi;
~~~

which changes its name without dropping or recreating the object. Conversely, `DROP TABLE` followed by `CREATE TABLE` with the same name can assign a new OID.

Table-rewriting or index-rebuilding operations can change physical storage files while keeping the same catalog OID identity. `pg_class.relfilenode` is not an OID to replace a table name and should never be saved as a business reference key.

**Conclusion:** if migration tools need to know "what is the logical table named," use schema-qualified names and migration history. If a catalog query joins table metadata within one snapshot, use OIDs/`regclass`.

## 27. OIDs, Metadata Caching, and Concurrency

PostgreSQL reads catalogs when parsing and executing SQL. To avoid hitting disk for metadata on every query, backends maintain **internal metadata caches**. DDL executes transactionally, and PostgreSQL maintains cache consistency across backends.

Example:

1. Session A begins reading from `catalog_lab.nhan_vien`.
2. Session B attempts DDL altering the table's structure.
3. PostgreSQL uses locks, MVCC, and catalog management to prevent structural changes from making in-flight queries unsafe.
4. Once DDL commits, other sessions observe the new structure per transaction rules and internal cache invalidation.

Never build an application-level OID cache lasting across deployments assuming mappings never change. Migrations, dump/restore, drop/recreate, or restarts can invalidate cached OIDs.

### 27.1. Catalog queries obey transaction rules too

Running sequential metadata queries across separate transactions while another session creates or drops tables can return changing results. Never export catalog `SELECT` results as permanent external keys.

To run migrations safely under concurrent DDL, use proper migration tooling, permissions, and locking rather than non-transactional "check if exists, then alter" scripts.

## 28. Security When Querying System Catalogs

Metadata helps DBAs tremendously, yet can also expose structural details of a system.

Key points:

- Certain catalogs and views restrict access or redact sensitive fields.
- `pg_roles` is designed for role inspection instead of exposing sensitive auth hashes directly.
- `information_schema` typically filters rows based on the connected user's privileges.
- A role may be able to see a table's name in catalogs while **lacking `SELECT` permission on the table's data**.
- Metadata inspection functions and queries must adhere to assigned role privileges.
- On managed PostgreSQL, full superuser access may be restricted.

Example:

~~~sql
SELECT
    current_user,
    pg_catalog.has_schema_privilege(
        current_user,
        'catalog_lab',
        'USAGE'
    ) AS can_use_schema,
    pg_catalog.has_table_privilege(
        current_user,
        'catalog_lab.nhan_vien',
        'SELECT'
    ) AS can_read_table;
~~~

**An OID is never a shortcut around permissions**. If an application lacks read privileges on a table, knowing its OID grants zero access.

Additionally, never splice schema or table names from untrusted user input into unescaped SQL strings. When writing dynamic SQL in admin routines, quote identifiers properly using `format('%I', identifier)` in safe PL/pgSQL and parameterize data values whenever possible.

## 29. Avoid Editing Catalogs Directly

Proper operations:

~~~sql
ALTER TABLE catalog_lab.nhan_vien
ADD COLUMN ghi_chu TEXT;

COMMENT ON COLUMN catalog_lab.nhan_vien.ghi_chu
IS 'Internal note';
~~~

PostgreSQL updates all affected catalogs cleanly through official mechanisms.

Operations you **must never perform**:

~~~sql
-- DO NOT EXECUTE: dangerous example shown only for recognition.
-- UPDATE pg_catalog.pg_attribute
-- SET attname = 'ten_moi'
-- WHERE attrelid = 'catalog_lab.nhan_vien'::regclass
--   AND attname = 'ho_ten';

-- DO NOT EXECUTE:
-- DELETE FROM pg_catalog.pg_class
-- WHERE relname = 'nhan_vien';
~~~

Editing catalogs directly skips dependency updates, index adjustments, cache invalidation, and integrity checks. It is never a valid way to rename columns or drop objects.

To rename a column, use `ALTER TABLE ... RENAME COLUMN`. To remove a table, use `DROP TABLE` after reviewing dependencies and confirming backups/recovery plans.

## 30. Common Conceptual Mistakes

### Mistake 1: "`pg_class` only holds tables"

No. `pg_class` holds many relations including tables, indexes, views, and sequences.

**Right approach:** filter by `relkind`, schema, and relation name per your goal.

### Mistake 2: "An OID is a permanent global primary key"

No. OIDs are internal identifiers with bounded scope and lifecycle; they are not guaranteed stable across dump/restore, drop/recreate, or different environments.

**Right approach:** use OIDs to join catalogs in the current database; use schema-qualified names and migrations for durable identification.

### Mistake 3: "Any two columns of type `oid` can be joined together"

No. You must verify which source and target catalogs each OID references.

**Right approach:** check the semantics of `relnamespace`, `attrelid`, `atttypid`, or `classid`/`objid` pairs.

### Mistake 4: "Foreign keys live only in `pg_depend`"

No. FK definitions are primarily stored in `pg_constraint` via `conrelid`, `confrelid`, `conkey`, and `confkey`.

**Right approach:** query `pg_constraint` for row-data constraints, and `pg_depend` for object lifecycle dependencies.

### Mistake 5: "To find a view's table dependencies, just check the view's `pg_class` row"

Not always sufficient. Views rely on rewrite rules and dependencies recorded against `pg_rewrite`/`pg_depend`.

**Right approach:** use `pg_get_viewdef` or join through `pg_rewrite` and `pg_depend`.

### Mistake 6: "Every `attnum` represents a current user column"

No. System attributes and dropped columns also have rows in `pg_attribute`.

**Right approach:** filter `attnum > 0 AND NOT attisdropped` when listing active user columns.

### Mistake 7: "`pg_class.reltuples` equals `COUNT(*)`"

No. `reltuples` is an **estimated** row count.

**Right approach:** use statistics for planning estimates; run `COUNT(*)` when you need an exact count.

### Mistake 8: "OID equals `relfilenode`"

No. Logical catalog identity and physical storage file identifiers are distinct concepts.

**Right approach:** never use internal filenames or paths as business identifiers.

### Mistake 9: "Updating catalogs directly with `UPDATE` is faster than `ALTER`"

Wrong and dangerous. It risks corrupting metadata and bypassing internal checks.

**Right approach:** use supported DDL and migration tools.

### Mistake 10: "Knowing an OID bypasses SQL permissions"

No. Role privileges are still enforced by PostgreSQL.

**Right approach:** verify `has_table_privilege` and role grants.

### Mistake 11: "`information_schema` and `pg_catalog` always return identical results"

No. They differ in purpose, detail level, and privilege filtering rules.

**Right approach:** choose the source suited to your metadata query.

### Mistake 12: "`DROP CASCADE` drops only one table"

No. `CASCADE` can drop dependent objects across schemas.

**Right approach:** inspect the dependency graph and blast radius before using it, especially in production.

## 31. Workflow for Analyzing an Object in PostgreSQL

When investigating how a table or view is wired together, follow this sequence:

**Step 1 — Verify active database and role.**

~~~sql
SELECT current_database(), current_user;
~~~

**Step 2 — Resolve the relation's OID from its schema-qualified name.**

~~~sql
SELECT to_regclass('catalog_lab.nhan_vien');
~~~

**Step 3 — Inspect relation kind and schema.**

~~~sql
SELECT
    c.oid,
    c.relname,
    c.relkind,
    n.nspname
FROM pg_catalog.pg_class AS c
JOIN pg_catalog.pg_namespace AS n
    ON n.oid = c.relnamespace
WHERE c.oid = 'catalog_lab.nhan_vien'::regclass;
~~~

**Step 4 — Inspect columns and data types.** Use `pg_attribute` with `format_type`/`pg_type`.

**Step 5 — Inspect keys and indexes.** Use `pg_constraint`, `pg_index`, `pg_get_constraintdef`, and `pg_get_indexdef`.

**Step 6 — Inspect dependent objects.** For views, inspect `pg_rewrite`/`pg_depend`; for FKs, `pg_constraint`; for partitions, `pg_inherits`.

**Step 7 — Inspect privileges and comments.** Use `has_table_privilege`, `obj_description`, and `col_description` as needed.

**Step 8 — Run DDL only after understanding its impact.** Never modify `pg_catalog` directly or use `CASCADE` out of habit.

## 32. Practice Exercises

### Exercise 1 — Classifying three kinds of data

Assign each item to the right category: `catalog_lab.nhan_vien`, `pg_class`, `pg_stat_activity`, `pg_constraint`, `pg_stat_user_tables`.

**Hint:** the employee table holds business data; `pg_class` and `pg_constraint` hold metadata; `pg_stat_activity` and `pg_stat_user_tables` provide runtime state/statistics.

### Exercise 2 — Table OID

Write SQL to fetch the OID and relation name of `catalog_lab.nhan_vien`.

**Hint:**

~~~sql
SELECT
    c.oid,
    c.oid::regclass AS relation_name
FROM pg_catalog.pg_class AS c
WHERE c.oid = 'catalog_lab.nhan_vien'::regclass;
~~~

### Exercise 3 — Schema containing a table

Write SQL joining `pg_class` and `pg_namespace` to find the schema of `nhan_vien`.

**Hint:** `pg_class.relnamespace = pg_namespace.oid`.

### Exercise 4 — Column list

Use `pg_attribute` to list `attnum`, `attname`, and data type for `catalog_lab.nhan_vien`, excluding system attributes and dropped columns.

**Hint:** `attrelid = 'catalog_lab.nhan_vien'::regclass`, `attnum > 0`, `NOT attisdropped`, `format_type`.

### Exercise 5 — Foreign key

Use `pg_constraint` to identify the source and target tables of `fk_nhan_vien_phong_ban`. Why does `conrelid` differ from `confrelid`?

**Hint:** `conrelid` points to `nhan_vien`; `confrelid` points to `phong_ban`.

### Exercise 6 — Column ordinal numbers

Why can you not interpret `conkey = {2}` as "the column with OID 2"?

**Hint:** elements of `conkey` are `attnum` column numbers within the relation identified by `conrelid`, not standalone column OIDs.

### Exercise 7 — Index metadata

Use `pg_index` and `pg_class` to list every index on the employee table. Distinguish `indexrelid` from `indrelid`.

**Hint:** one is the index relation; the other is the indexed table.

### Exercise 8 — View dependencies

Which two tables does `catalog_lab.v_nhan_vien` use? Why must you include `pg_rewrite` when querying `pg_depend`?

**Hint:** the view uses `nhan_vien` and `phong_ban`; view dependencies normally attach to the `_RETURN` rewrite rule.

### Exercise 9 — Renames and OIDs

`ALTER TABLE ... RENAME TO` changes the name; dropping and recreating with the same name can change the OID. Should cross-environment migrations track names or OIDs?

**Hint:** track logical schema-qualified names and migration versions; never hard-code OIDs.

### Exercise 10 — Formatting NUMERIC types

Why is `pg_attribute.atttypid` alone insufficient to print `NUMERIC(12,2)`?

**Hint:** you also need `atttypmod` and formatting rules; use `format_type(atttypid, atttypmod)`.

### Exercise 11 — DROP CASCADE

A table is referenced by a view. If you run `DROP TABLE ... CASCADE`, what else risks being dropped? Contrast with `ON DELETE CASCADE`.

**Hint:** dependent views or objects can be dropped at the schema level; `ON DELETE CASCADE` deletes child rows per a foreign key.

### Exercise 12 — Checking privileges

Write SQL using `has_table_privilege` to check whether the current role has `SELECT` privilege on the employee table.

**Hint:** `has_table_privilege(current_user, 'catalog_lab.nhan_vien', 'SELECT')`.

### Exercise 13 — Routine overloading

Why is `regprocedure` usually better than a bare function name when multiple functions share the same name?

**Hint:** the parameter type list is needed to uniquely identify the overload signature.

### Exercise 14 — Role of information_schema

When building a cross-DBMS column listing tool, should you start with `information_schema.columns` or join PostgreSQL-specific catalogs first?

**Hint:** `information_schema` offers an SQL-standard interface; `pg_catalog` is needed for PostgreSQL-specific details.

### Exercise 15 — Column comment

Write a query reading the comment on `ho_ten` without hard-coding column number 3.

**Hint:** join `pg_attribute` or filter `attname = 'ho_ten'`, then call `col_description(attrelid, attnum)`.

## 33. Key Takeaways

- **System catalogs** store PostgreSQL metadata for schemas, relations, columns, types, indexes, constraints, views, functions, and dependencies.
- **`pg_catalog`** is PostgreSQL's native metadata source; **`information_schema`** provides SQL-standard metadata views with privilege-based filtering.
- **OIDs** are 4-byte internal identifiers useful for catalog joins, never durable business keys or globally invariant IDs across servers.
- **`regclass`, `regtype`, and `regprocedure`** resolve names/signatures to OIDs and format objects readably.
- **`pg_namespace` ↔ `pg_class`** connects schemas to relations.
- **`pg_class` ↔ `pg_attribute` ↔ `pg_type`** describes relations, columns, and data types.
- **`pg_constraint`** defines constraints, using `conrelid`, `confrelid`, `conkey`, and `confkey` for foreign keys.
- **`pg_index`** links index relations to tables and holds index metadata.
- **`pg_rewrite` + `pg_depend`** reveal view dependencies; object dependencies are distinct from foreign-key row constraints.
- **`pg_description`** attaches comments to objects or columns; **`pg_proc`** describes routines; **`pg_inherits`** links inheritance and partitioned relations.
- **OIDs, column ordinal positions (`attnum`), and physical filenames (`relfilenode`) are distinct concepts**; never conflate them.
- **Never edit system catalogs directly**, and never run `DROP ... CASCADE` without understanding every affected object.
- When exploring a database, prefer schema-qualified names, helper functions such as `pg_get_constraintdef`, `pg_get_indexdef`, and `pg_get_viewdef`, and read-only catalog queries.

Understanding system catalogs and OIDs is a crucial step toward viewing PostgreSQL as **a structured system of interrelated objects and dependency rules**, rather than just a bucket of rows. Once you know what each catalog describes and how OIDs connect them, you can explain why a foreign key exists, why a dependent view blocks a table drop, which table an index serves, and what a schema change can impact.
