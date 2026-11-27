# Inspecting Catalogs, Dependencies, and Unused Objects in PostgreSQL

Long-term PostgreSQL administration requires knowing which objects exist in a database, how they depend on one another, and which ones may no longer be in use. As systems evolve, schemas accumulate tables, indexes, views, functions, sequences, roles, extensions, and objects left over from older application versions. Without an inventory and a safe cleanup process, databases grow harder to manage, migrations fail more easily, and dropping the wrong object can break applications.

PostgreSQL stores database metadata in **system catalogs**. Catalogs reveal object identities, owners, types, columns, constraints, indexes, privileges, extension membership, and dependencies. The **Information Schema** provides a standardized view layer, while **pg_catalog** exposes PostgreSQL's implementation-specific details. Statistics views add evidence of actual runtime activity, though they can never definitively prove that an object is no longer used.

This lesson belongs to the **Administration** chapter and focuses on:

- Exploring database structure using `information_schema` and `pg_catalog`.
- Inventorying schemas, tables, columns, indexes, constraints, views, routines, sequences, and extensions.
- Reading the dependency graph via `pg_depend` and `pg_shdepend`.
- Understanding object ownership, ACLs, extension membership, and system-generated objects.
- Distinguishing objects lacking statistics from objects genuinely no longer used.
- Finding unused index, table, function, and sequence candidates across multiple evidence sources.
- Checking invalid indexes, unvalidated constraints, and sequence-column relationships.
- Using `DROP RESTRICT`, dependency inspection, and deprecation workflows for safe cleanup.
- Tracking catalog changes, access privileges, and drift across environments.
- Building inventories, audit queries, cleanup runbooks, and practice exercises.

> **Key principle:** catalogs describe what PostgreSQL knows about the database; statistics describe activity recorded over a time window. No single query can prove an object is no longer used by applications, scheduled jobs, reports, migrations, or external systems. Treat "unused" results as candidates requiring verification before making changes.

## 1. Where Is PostgreSQL Metadata Stored?

PostgreSQL stores database object definitions in system catalogs. Catalogs are tables inside the `pg_catalog` system schema. Views like `information_schema.tables` or `pg_tables` make querying metadata more convenient.

### 1.1. Information Schema

`information_schema` is a collection of SQL-standard views, such as:

- `information_schema.schemata`: schemas visible under current privileges.
- `information_schema.tables`: tables and views.
- `information_schema.columns`: columns.
- `information_schema.table_constraints`: constraints.
- `information_schema.key_column_usage`: columns participating in key constraints.
- `information_schema.referential_constraints`: foreign-key relationships.
- `information_schema.views`: standardized view definitions.
- `information_schema.routines`: routines.
- `information_schema.sequences`: sequences.
- `information_schema.role_table_grants`: partial grant information.

Advantages:

- Familiar view and column names for SQL users.
- Easier to write portable queries across database engines.
- Less coupled to catalog internals.
- Generally exposes only objects the current role has permission to see.

Limitations:

- Does not contain all PostgreSQL-specific metadata.
- Several fields are missing or lack administrative detail.
- Results can be restricted by the current user's privileges.
- Cannot replace the dependency graph or internal flags.

### 1.2. pg_catalog

`pg_catalog` holds PostgreSQL-specific catalogs and system views. Key catalogs include:

| Catalog/view | Contents |
| --- | --- |
| pg_namespace | Schemas |
| pg_class | Relations: tables, indexes, sequences, views, materialized views, and certain relation-like objects |
| pg_attribute | Columns/attributes of relations |
| pg_type | Data types, domains, composite types, enums |
| pg_proc | Functions, procedures, aggregates, and window routines |
| pg_constraint | Constraints |
| pg_index | Index metadata |
| pg_inherits | Table/index inheritance and partition relationships |
| pg_depend | Dependencies between database objects |
| pg_shdepend | Dependencies on shared objects such as roles and tablespaces |
| pg_rewrite | Rewrite rules, including view rules |
| pg_trigger | Triggers |
| pg_extension | Extensions installed in the database |
| pg_description | Comments/descriptions |
| pg_roles | Roles and role attributes |
| pg_database | Databases in the cluster |
| pg_default_acl | Default privileges |

Catalog columns and semantics can change across major versions. Administrative queries running across multiple versions must check column availability rather than assuming identical schemas.

### 1.3. Convenience Views

Beyond catalogs, PostgreSQL provides more user-friendly views:

- `pg_tables` and `pg_views`.
- `pg_matviews`.
- `pg_indexes`.
- `pg_sequences`.
- `pg_stats`.
- `pg_stat_user_tables`.
- `pg_stat_user_indexes`.
- `pg_stat_user_functions`.
- `pg_stat_activity`.
- `pg_stat_database`.

Statistics views enforce their own visibility rules. Users lacking appropriate monitoring privileges may see only partial information or have query text from other sessions hidden.

### 1.4. Catalogs Are Metadata, Not a Business Registry

Catalogs can answer:

- Which schema holds a table?
- Who owns the table?
- Is an index valid?
- Which relations does a view depend on?
- Which column owns a sequence?
- Which extension owns an object?
- What privileges does a role hold?

Catalogs cannot necessarily answer:

- Which application still calls a table?
- Does a month-end report query this view?
- Does an external service invoke a function via dynamic SQL?
- Does a legacy dashboard still connect to the database?
- Is the object used in backup/restore or migration workflows?

You must combine catalogs, runtime statistics, query logs, application code, job inventories, and owner confirmation.

## 2. Naming Rules and Object Identification

Before querying dependencies or planning drops, identify the exact object unambiguously.

### 2.1. Schema and Object Name

Object names in PostgreSQL are scoped within a namespace. Two schemas can contain objects with the same name:

```sql
CREATE SCHEMA app;
CREATE SCHEMA reporting;

CREATE TABLE app.orders (
    id bigint PRIMARY KEY
);

CREATE VIEW reporting.orders AS
SELECT id FROM app.orders;
```

Always use fully schema-qualified names in inventories, dependency checks, and migrations. Avoid relying on `search_path` to identify objects in administrative scripts.

### 2.2. OID

Every database object has an Object Identifier (OID) in its corresponding catalog. For relations, the OID lives in `pg_class.oid`. For functions, the OID lives in `pg_proc.oid`.

OIDs are useful for joining catalogs and identifying objects within a single database. Never treat an OID as a business ID or a stable identifier across dump/restore, drop/recreate, or migrations.

```sql
SELECT
    c.oid,
    n.nspname AS schema_name,
    c.relname AS relation_name,
    c.relkind
FROM pg_class AS c
JOIN pg_namespace AS n
    ON n.oid = c.relnamespace
WHERE n.nspname = 'app'
ORDER BY c.relname;
```

### 2.3. to_regclass and regclass

`to_regclass` resolves a relation name to an OID if found, or returns `NULL` if it does not exist:

```sql
SELECT to_regclass('app.orders') AS relation_oid;
```

Casting to `regclass` can reference an object unambiguously inside queries:

```sql
SELECT 'app.orders'::regclass;
```

Schema-qualified names prevent ambiguity when multiple schemas hold identically named objects. Names containing uppercase letters or special characters must be double-quoted per identifier rules.

### 2.4. Do Not Persist OIDs Across Environments

A table's OID in development will not necessarily match its OID in staging or production. Use schema + object name + object type, or an administrative inventory key, when comparing environments.

## 3. Inventorying Schemas and Relations

The first step in an audit is listing objects within administrative scope.

### 3.1. Listing Schemas

```sql
SELECT
    n.oid,
    n.nspname AS schema_name,
    pg_get_userbyid(n.nspowner) AS owner
FROM pg_namespace AS n
WHERE n.nspname NOT LIKE 'pg\_%' ESCAPE '\'
  AND n.nspname <> 'information_schema'
ORDER BY n.nspname;
```

Do not drop a schema simply because it has no tables. A schema may contain functions, types, domains, operators, collations, policies, or objects referenced by applications via dynamic SQL.

### 3.2. Listing Relations by Schema

```sql
SELECT
    n.nspname AS schema_name,
    c.relname AS object_name,
    CASE c.relkind
        WHEN 'r' THEN 'table'
        WHEN 'p' THEN 'partitioned table'
        WHEN 'i' THEN 'index'
        WHEN 'I' THEN 'partitioned index'
        WHEN 'S' THEN 'sequence'
        WHEN 'v' THEN 'view'
        WHEN 'm' THEN 'materialized view'
        WHEN 'f' THEN 'foreign table'
        WHEN 't' THEN 'TOAST table'
        WHEN 'c' THEN 'composite type relation'
        ELSE c.relkind::text
    END AS object_type,
    CASE c.relpersistence
        WHEN 'p' THEN 'permanent'
        WHEN 'u' THEN 'unlogged'
        WHEN 't' THEN 'temporary'
    END AS persistence,
    pg_get_userbyid(c.relowner) AS owner
FROM pg_class AS c
JOIN pg_namespace AS n
    ON n.oid = c.relnamespace
WHERE n.nspname NOT LIKE 'pg\_%' ESCAPE '\'
  AND n.nspname <> 'information_schema'
ORDER BY n.nspname, c.relkind, c.relname;
```

`pg_class` holds many kinds of relation-like objects, not only ordinary tables. When building inventories, distinguish `relkind` rather than labeling everything a table.

### 3.3. Counting Objects by Schema and Type

```sql
SELECT
    n.nspname AS schema_name,
    CASE c.relkind
        WHEN 'r' THEN 'table'
        WHEN 'p' THEN 'partitioned table'
        WHEN 'i' THEN 'index'
        WHEN 'I' THEN 'partitioned index'
        WHEN 'S' THEN 'sequence'
        WHEN 'v' THEN 'view'
        WHEN 'm' THEN 'materialized view'
        WHEN 'f' THEN 'foreign table'
        ELSE 'other relation'
    END AS object_type,
    count(*) AS object_count
FROM pg_class AS c
JOIN pg_namespace AS n
    ON n.oid = c.relnamespace
WHERE n.nspname NOT LIKE 'pg\_%' ESCAPE '\'
  AND n.nspname <> 'information_schema'
GROUP BY n.nspname, c.relkind
ORDER BY n.nspname, object_type;
```

Use counts to monitor schema growth between releases or across environments. Counts do not capture full object complexity or data volume.

### 3.4. Table and Index Sizes

```sql
SELECT
    schemaname,
    relname AS table_name,
    pg_size_pretty(pg_relation_size(
        format('%I.%I', schemaname, relname)::regclass
    )) AS main_fork_size,
    pg_size_pretty(pg_table_size(
        format('%I.%I', schemaname, relname)::regclass
    )) AS table_size,
    pg_size_pretty(pg_total_relation_size(
        format('%I.%I', schemaname, relname)::regclass
    )) AS total_size
FROM pg_tables
WHERE schemaname NOT LIKE 'pg\_%'
  AND schemaname <> 'information_schema'
ORDER BY pg_total_relation_size(
    format('%I.%I', schemaname, relname)::regclass
) DESC;
```

- `pg_relation_size` measures the requested fork, defaulting to the main fork.
- `pg_table_size` includes table storage and related components such as TOAST, excluding all indexes.
- `pg_total_relation_size` includes the table, TOAST, and indexes.

Large size does not mean an object is unused. Conversely, a tiny table can still be a critical configuration table.

## 4. Inspecting Columns, Defaults, and Types

A useful inventory should reflect each table's schema contract.

### 4.1. Listing Columns

```sql
SELECT
    n.nspname AS schema_name,
    c.relname AS table_name,
    a.attnum AS ordinal_position,
    a.attname AS column_name,
    format_type(a.atttypid, a.atttypmod) AS data_type,
    a.attnotnull AS not_null,
    a.attidentity AS identity_kind,
    a.attgenerated AS generated_kind,
    pg_get_expr(ad.adbin, ad.adrelid) AS default_expression
FROM pg_class AS c
JOIN pg_namespace AS n
    ON n.oid = c.relnamespace
JOIN pg_attribute AS a
    ON a.attrelid = c.oid
LEFT JOIN pg_attrdef AS ad
    ON ad.adrelid = c.oid
   AND ad.adnum = a.attnum
WHERE c.relkind IN ('r', 'p', 'v', 'm', 'f')
  AND a.attnum > 0
  AND NOT a.attisdropped
  AND n.nspname = 'app'
ORDER BY c.relname, a.attnum;
```

`attisdropped` marks columns logically dropped while the catalog still retains an internal placeholder. Do not report those attributes as active columns.

### 4.2. Inspecting Custom Types and Domains

```sql
SELECT
    n.nspname AS schema_name,
    t.typname AS type_name,
    t.typtype,
    t.typcategory,
    pg_get_userbyid(t.typowner) AS owner
FROM pg_type AS t
JOIN pg_namespace AS n
    ON n.oid = t.typnamespace
WHERE n.nspname NOT LIKE 'pg\_%' ESCAPE '\'
  AND n.nspname <> 'information_schema'
ORDER BY n.nspname, t.typname;
```

A type can be used in table columns, function signatures, arrays, composite types, or application serialization. Do not drop a type merely because it does not appear directly on a table.

### 4.3. Enum Values

```sql
SELECT
    n.nspname AS schema_name,
    t.typname AS enum_type,
    e.enumsortorder,
    e.enumlabel
FROM pg_type AS t
JOIN pg_namespace AS n
    ON n.oid = t.typnamespace
JOIN pg_enum AS e
    ON e.enumtypid = t.oid
ORDER BY n.nspname, t.typname, e.enumsortorder;
```

Enum labels may be referenced in application code and API contracts. Catalog dependencies reveal only part of the relationship; inspect application code and serialized data before altering them.

## 5. Inventorying Constraints and Foreign Keys

Constraints encode data integrity rules and may be backed by indexes.

### 5.1. Listing Constraints

```sql
SELECT
    n.nspname AS schema_name,
    t.relname AS table_name,
    con.conname AS constraint_name,
    CASE con.contype
        WHEN 'p' THEN 'primary key'
        WHEN 'u' THEN 'unique'
        WHEN 'f' THEN 'foreign key'
        WHEN 'c' THEN 'check'
        WHEN 'x' THEN 'exclusion'
        WHEN 'n' THEN 'not null'
        ELSE con.contype::text
    END AS constraint_type,
    con.convalidated AS validated,
    pg_get_constraintdef(con.oid, true) AS definition,
    NULLIF(con.conindid, 0)::regclass AS supporting_index
FROM pg_constraint AS con
JOIN pg_class AS t
    ON t.oid = con.conrelid
JOIN pg_namespace AS n
    ON n.oid = t.relnamespace
WHERE n.nspname = 'app'
ORDER BY t.relname, con.conname;
```

Certain constraints are not attached to tables in the same way; the query above focuses on constraints tied to a relation via `conrelid`.

### 5.2. Foreign-Key Relationships

```sql
SELECT
    child_ns.nspname AS child_schema,
    child.relname AS child_table,
    fk.conname AS foreign_key_name,
    parent_ns.nspname AS parent_schema,
    parent.relname AS parent_table,
    pg_get_constraintdef(fk.oid, true) AS definition,
    fk.convalidated AS validated
FROM pg_constraint AS fk
JOIN pg_class AS child
    ON child.oid = fk.conrelid
JOIN pg_namespace AS child_ns
    ON child_ns.oid = child.relnamespace
JOIN pg_class AS parent
    ON parent.oid = fk.confrelid
JOIN pg_namespace AS parent_ns
    ON parent_ns.oid = parent.relnamespace
WHERE fk.contype = 'f'
ORDER BY child_ns.nspname, child.relname, fk.conname;
```

Foreign keys create dependencies on the referenced table and rely on a unique/primary key index on the referenced side. PostgreSQL does not automatically create an index on referencing columns; whether such an index is needed depends on delete/update workloads and query patterns.

### 5.3. Unvalidated Constraints

```sql
SELECT
    n.nspname AS schema_name,
    t.relname AS table_name,
    con.conname AS constraint_name,
    con.contype,
    pg_get_constraintdef(con.oid, true) AS definition
FROM pg_constraint AS con
JOIN pg_class AS t
    ON t.oid = con.conrelid
JOIN pg_namespace AS n
    ON n.oid = t.relnamespace
WHERE NOT con.convalidated
ORDER BY n.nspname, t.relname, con.conname;
```

Unvalidated constraints may come from migrations using `NOT VALID`. This is not automatically an error: PostgreSQL still enforces the constraint on new rows per its semantics, while existing rows have not yet been fully checked. Verify the reason and validation plan.

## 6. Inventorying Indexes and Validity State

Indexes consume storage and add write overhead. Index inventories surface invalid indexes, zero-scan indexes, and constraint-backing indexes.

### 6.1. Listing Indexes

```sql
SELECT
    ns.nspname AS schema_name,
    tbl.relname AS table_name,
    idx.relname AS index_name,
    i.indisprimary AS is_primary,
    i.indisunique AS is_unique,
    i.indisvalid AS is_valid,
    i.indisready AS is_ready,
    i.indisreplident AS is_replica_identity,
    pg_size_pretty(pg_relation_size(idx.oid)) AS index_size,
    pg_get_indexdef(idx.oid) AS index_definition
FROM pg_index AS i
JOIN pg_class AS idx
    ON idx.oid = i.indexrelid
JOIN pg_class AS tbl
    ON tbl.oid = i.indrelid
JOIN pg_namespace AS ns
    ON ns.oid = tbl.relnamespace
WHERE ns.nspname = 'app'
ORDER BY tbl.relname, idx.relname;
```

### 6.2. Invalid or Not-Ready Indexes

```sql
SELECT
    ns.nspname AS schema_name,
    tbl.relname AS table_name,
    idx.relname AS index_name,
    i.indisvalid,
    i.indisready,
    i.indislive,
    pg_get_indexdef(i.indexrelid) AS definition
FROM pg_index AS i
JOIN pg_class AS idx
    ON idx.oid = i.indexrelid
JOIN pg_class AS tbl
    ON tbl.oid = i.indrelid
JOIN pg_namespace AS ns
    ON ns.oid = tbl.relnamespace
WHERE NOT i.indisvalid
   OR NOT i.indisready
   OR NOT i.indislive
ORDER BY ns.nspname, tbl.relname, idx.relname;
```

Invalid indexes can appear after a failed concurrent index build or interrupted DDL operation. Do not drop or rebuild immediately before checking active operations, dependent constraints, and build logs.

### 6.3. Constraint-Backing Indexes

```sql
SELECT
    ns.nspname AS schema_name,
    tbl.relname AS table_name,
    idx.relname AS index_name,
    con.conname AS constraint_name,
    con.contype AS constraint_type,
    pg_get_constraintdef(con.oid, true) AS constraint_definition
FROM pg_constraint AS con
JOIN pg_class AS tbl
    ON tbl.oid = con.conrelid
JOIN pg_namespace AS ns
    ON ns.oid = tbl.relnamespace
JOIN pg_class AS idx
    ON idx.oid = con.conindid
WHERE con.conindid <> 0
ORDER BY ns.nspname, tbl.relname, con.conname;
```

Indexes backing primary key, unique, or exclusion constraints enforce data correctness. Never drop such indexes simply because statistics show `idx_scan` equals 0.

### 6.4. Zero-Scan Indexes Are Candidates, Not Conclusions

```sql
SELECT
    s.schemaname,
    s.relname AS table_name,
    s.indexrelname AS index_name,
    s.idx_scan,
    s.idx_tup_read,
    s.idx_tup_fetch,
    i.indisprimary,
    i.indisunique,
    i.indisreplident,
    EXISTS (
        SELECT 1
        FROM pg_constraint AS con
        WHERE con.conindid = i.indexrelid
    ) AS backs_constraint,
    pg_size_pretty(pg_relation_size(i.indexrelid)) AS index_size,
    pg_get_indexdef(i.indexrelid) AS definition
FROM pg_stat_user_indexes AS s
JOIN pg_index AS i
    ON i.indexrelid = s.indexrelid
WHERE s.idx_scan = 0
ORDER BY pg_relation_size(i.indexrelid) DESC;
```

The output is solely a review list. An index with `idx_scan = 0` may still:

- Serve month-end or seasonal workloads.
- Be used on another database or environment.
- Have had scans prior to a statistics reset.
- Enforce uniqueness or a primary key.
- Serve as `REPLICA IDENTITY`.
- Support a migration, maintenance task, or very rare query.
- Be unused due to current cache/plan choices yet still needed in the future.

Never automatically drop every index with `idx_scan = 0`.

### 6.5. Statistics Reset Timestamp

Before relying on index or table counters, check when statistics were last reset:

```sql
SELECT
    datname,
    stats_reset
FROM pg_stat_database
ORDER BY datname;
```

Stats can be reset by administrators or lifecycle events. If the statistics window covers only minutes after a restart, `idx_scan = 0` proves little. Compare across a complete business cycle and inspect logs and traces.

## 7. Evaluating Tables with Low or Zero Activity

PostgreSQL provides table statistics tracking scans and row modifications.

### 7.1. Table Statistics

```sql
SELECT
    schemaname,
    relname AS table_name,
    seq_scan,
    seq_tup_read,
    idx_scan,
    idx_tup_fetch,
    n_tup_ins,
    n_tup_upd,
    n_tup_del,
    n_live_tup,
    n_dead_tup,
    last_vacuum,
    last_autovacuum,
    last_analyze,
    last_autoanalyze
FROM pg_stat_user_tables
ORDER BY seq_scan + COALESCE(idx_scan, 0);
```

Some fields may differ across PostgreSQL major versions. If automation runs on older versions, verify the view definition first.

### 7.2. Tables Without Scans

```sql
SELECT
    schemaname,
    relname AS table_name,
    seq_scan,
    idx_scan,
    n_tup_ins,
    n_tup_upd,
    n_tup_del,
    n_live_tup,
    n_dead_tup
FROM pg_stat_user_tables
WHERE COALESCE(seq_scan, 0) = 0
  AND COALESCE(idx_scan, 0) = 0
ORDER BY n_live_tup DESC;
```

This is a candidate inventory. A table may be read via views, functions, or rare queries. A write-only table might still be an outbox, staging, audit, or queue table.

### 7.3. Writes Do Not Prove a Consumer Exists

`n_tup_ins`, `n_tup_upd`, and `n_tup_del` reflect write activity, not whether any application reads the table. Similarly, zero scans do not prove a table is useless.

Check all of the following:

- Foreign keys and dependencies.
- Triggers and rules.
- Views and materialized views.
- Functions and procedures.
- Application repositories and ORM mappings.
- Scheduled jobs, ETL, and BI queries.
- Audit, retention, backup, and compliance requirements.

### 7.4. Table Statistics Are Counters, Not Event History

Statistics views aggregate activity over a period. They do not record every query or caller. If you need to know who accessed an object, appropriate logging, auditing, or tracing must already be configured.

## 8. Inspecting Views and Materialized Views

Views can depend on many tables and other views. A view not queried directly might still act as an application API contract or be queried by another view.

### 8.1. Inventorying Views

```sql
SELECT
    schemaname,
    viewname,
    viewowner,
    definition
FROM pg_views
WHERE schemaname NOT LIKE 'pg\_%'
  AND schemaname <> 'information_schema'
ORDER BY schemaname, viewname;
```

### 8.2. Inventorying Materialized Views

```sql
SELECT
    schemaname,
    matviewname,
    matviewowner,
    ispopulated,
    definition
FROM pg_matviews
WHERE schemaname NOT LIKE 'pg\_%'
  AND schemaname <> 'information_schema'
ORDER BY schemaname, matviewname;
```

Materialized views persist query results on disk and can consume substantial storage. Check refresh schedules, consuming reports, owners, and freshness requirements before dropping.

### 8.3. View Definitions

Retrieve definitions with:

```sql
SELECT pg_get_viewdef('reporting.orders_summary'::regclass, true);
```

`pg_get_viewdef` returns the stored query definition. It helps inspect view structure but does not replace the dependency graph or runtime usage checks.

### 8.4. Views Lack Direct Usage Counters

PostgreSQL does not maintain a universal counter for how many times each view is queried. You can search query text in logs or `pg_stat_statements`, though dynamic SQL, prepared statements, normalized query text, and nested execution make mapping imperfect.

## 9. Inventorying Functions, Procedures, and Triggers

Routines can be invoked directly, or indirectly via triggers, views, application code, or dynamic SQL.

### 9.1. Listing Routines

```sql
SELECT
    n.nspname AS schema_name,
    p.proname AS routine_name,
    pg_get_function_identity_arguments(p.oid) AS identity_arguments,
    CASE p.prokind
        WHEN 'f' THEN 'function'
        WHEN 'p' THEN 'procedure'
        WHEN 'a' THEN 'aggregate'
        WHEN 'w' THEN 'window function'
        ELSE p.prokind::text
    END AS routine_type,
    pg_get_userbyid(p.proowner) AS owner,
    l.lanname AS language,
    p.prosecdef AS security_definer,
    p.provolatile AS volatility
FROM pg_proc AS p
JOIN pg_namespace AS n
    ON n.oid = p.pronamespace
JOIN pg_language AS l
    ON l.oid = p.prolang
WHERE n.nspname NOT LIKE 'pg\_%' ESCAPE '\'
  AND n.nspname <> 'information_schema'
ORDER BY n.nspname, p.proname, identity_arguments;
```

Function overloads can share the same name with different argument types. Function name alone is therefore insufficient to uniquely identify an object.

### 9.2. Function Definitions

```sql
SELECT
    n.nspname AS schema_name,
    p.proname AS function_name,
    pg_get_function_identity_arguments(p.oid) AS arguments,
    pg_get_functiondef(p.oid) AS definition
FROM pg_proc AS p
JOIN pg_namespace AS n
    ON n.oid = p.pronamespace
WHERE n.nspname = 'app'
  AND p.prokind IN ('f', 'p')
ORDER BY p.proname, arguments;
```

Do not export full definitions into broadly readable logs or tickets if function bodies contain literal secrets or sensitive logic.

### 9.3. Function Statistics

When `track_functions` is enabled appropriately, PostgreSQL provides statistics in `pg_stat_user_functions`:

```sql
SELECT
    schemaname,
    funcname,
    calls,
    total_time,
    self_time
FROM pg_stat_user_functions
ORDER BY total_time DESC;
```

If function tracking is disabled, calls will not be recorded as expected. Check `track_functions`, the stats window duration, and PostgreSQL version.

### 9.4. Trigger Inventory

```sql
SELECT
    n.nspname AS schema_name,
    t.relname AS table_name,
    trg.tgname AS trigger_name,
    trg.tgenabled AS enabled_state,
    pg_get_triggerdef(trg.oid, true) AS definition
FROM pg_trigger AS trg
JOIN pg_class AS t
    ON t.oid = trg.tgrelid
JOIN pg_namespace AS n
    ON n.oid = t.relnamespace
WHERE NOT trg.tgisinternal
  AND n.nspname = 'app'
ORDER BY t.relname, trg.tgname;
```

Internal triggers typically back foreign keys or system features. Never drop an internal trigger as a standalone object; manage the constraint or feature that owns it.

### 9.5. Dynamic SQL and Incomplete Dependencies

The dependency catalog cannot always track relation names constructed dynamically as strings at runtime. For example, a function building SQL via `format()` and `EXECUTE` can reference a table without the catalog recording a static dependency as an administrator might expect.

Therefore, dependency queries do not produce an exhaustive list of every object a function may touch. Read routine bodies, application code, job definitions, and runtime logs.

## 10. Sequences and Column Relationships

Sequences commonly supply values for `serial`/identity columns, yet can also be called directly by applications or functions.

### 10.1. Inventorying Sequences

```sql
SELECT
    schemaname,
    sequencename,
    sequenceowner,
    data_type,
    start_value,
    min_value,
    max_value,
    increment_by,
    cycle,
    cache_size,
    last_value
FROM pg_sequences
WHERE schemaname NOT LIKE 'pg\_%'
  AND schemaname <> 'information_schema'
ORDER BY schemaname, sequencename;
```

`last_value` can be `NULL` when the role lacks permission to read the sequence or the sequence has not been used per view semantics. Caching can also mean values issued to a session are not yet fully reflected on disk. Never rely on `last_value` alone to conclude a sequence is unused.

### 10.2. Sequence Ownership Dependencies

Serial and identity sequences typically carry a dependency to their table column. Inspect with:

```sql
SELECT
    seq_ns.nspname AS sequence_schema,
    seq.relname AS sequence_name,
    tbl_ns.nspname AS table_schema,
    tbl.relname AS table_name,
    col.attname AS column_name,
    dep.deptype AS dependency_type
FROM pg_class AS seq
JOIN pg_namespace AS seq_ns
    ON seq_ns.oid = seq.relnamespace
JOIN pg_depend AS dep
    ON dep.classid = 'pg_class'::regclass
   AND dep.objid = seq.oid
   AND dep.refclassid = 'pg_class'::regclass
   AND dep.refobjsubid > 0
JOIN pg_class AS tbl
    ON tbl.oid = dep.refobjid
JOIN pg_namespace AS tbl_ns
    ON tbl_ns.oid = tbl.relnamespace
JOIN pg_attribute AS col
    ON col.attrelid = tbl.oid
   AND col.attnum = dep.refobjsubid
WHERE seq.relkind = 'S'
ORDER BY seq_ns.nspname, seq.relname;
```

Dependency type generally indicates whether the sequence is auto-owned by a column or internally linked to an identity column. Verify version-specific semantics when writing automation.

### 10.3. Sequences Without Ownership Dependencies

A sequence lacking a column ownership dependency can still be called directly via `nextval()` in application code, functions, or dynamic SQL. It is solely a candidate for further lookup.

You can check defaults referencing sequences via dependencies of default expressions, though function bodies and dynamic SQL may still remain uncovered.

### 10.4. Do Not Reset or Drop Sequences Based on Name or last_value

Sequences can drive ID generation, ticket numbering, distributed coordination, or application logic. Before dropping or resetting:

- Identify the owner.
- Check defaults and identity relationships.
- Search code and functions for `nextval`, `currval`, and `setval`.
- Check jobs and integration services.
- Assess concurrency and data collision risks.
- Prepare a backup and rollback plan.

## 11. Dependency Graphs with pg_depend

`pg_depend` is the primary catalog for understanding dependencies between objects inside a database. Each dependency record states which object depends on which other object.

### 11.1. How to Read pg_depend

Key columns:

| Column | Meaning |
| --- | --- |
| classid | Catalog containing the dependent object |
| objid | OID of the dependent object |
| objsubid | Sub-object ID, typically attribute number for columns |
| refclassid | Catalog containing the referenced object |
| refobjid | OID of the referenced object |
| refobjsubid | Sub-object ID of the referenced object |
| deptype | Dependency type |

Dependency direction is crucial: the object on the `classid`/`objid` side depends on the object on the `refclassid`/`refobjid` side.

For example, a view depends on a table: the view is the dependent object, and the table is the referenced object. When checking "who depends on this table," filter by the referenced object.

### 11.2. Viewing Objects Depending on a Table

```sql
SELECT
    pg_describe_object(
        d.classid,
        d.objid,
        d.objsubid
    ) AS dependent_object,
    d.deptype AS dependency_type,
    pg_describe_object(
        d.refclassid,
        d.refobjid,
        d.refobjsubid
    ) AS referenced_object
FROM pg_depend AS d
WHERE d.refclassid = 'pg_class'::regclass
  AND d.refobjid = 'app.orders'::regclass
ORDER BY dependent_object;
```

Results can include views, rules, constraints, indexes, defaults, triggers, or other dependent objects depending on relationships. Read the dependency type to see how PostgreSQL behaves when the referenced object is dropped.

### 11.3. Viewing Objects a Table Depends On

```sql
SELECT
    pg_describe_object(
        d.refclassid,
        d.refobjid,
        d.refobjsubid
    ) AS referenced_object,
    d.deptype AS dependency_type
FROM pg_depend AS d
WHERE d.classid = 'pg_class'::regclass
  AND d.objid = 'app.orders'::regclass
ORDER BY referenced_object;
```

This shows whether the table object depends on custom types, tablespaces, or other objects. Column-level dependencies may be represented using sub-object IDs; do not ignore `objsubid`/`refobjsubid` during detailed analysis.

### 11.4. Dependency Types

Common dependency types in `pg_depend`:

- `n` — normal dependency: an object depends normally on the referenced object; `DROP RESTRICT` generally blocks dropping the referenced object while the dependent object exists.
- `a` — automatic dependency: the dependent object is automatically dropped when the referenced object is dropped.
- `i` — internal dependency: the object is treated as an internal part of another object and cannot usually be dropped independently.
- `e` — extension dependency: the object is a member of an extension.
- `P`/`S` — dependencies related to partition primary/secondary relationships in supporting PostgreSQL versions.
- `x` — auto-extension dependency in versions representing it.

Codes and semantics can evolve across versions. Pinned objects are protected by PostgreSQL through a separate mechanism and should not be treated like ordinary dependency types. Cross-check the catalog documentation for your exact major version; never write cleanup logic based on guessed code tables.

### 11.5. pg_describe_object

`pg_describe_object` turns a catalog OID / object OID / sub-object ID triple into a human-readable description:

```sql
SELECT pg_describe_object(
    'pg_class'::regclass,
    'app.orders'::regclass,
    0
);
```

Use this function in dependency reports instead of manually reconstructing names for every catalog class.

### 11.6. pg_identify_object

`pg_identify_object` returns the object type, schema, name, and identity suitable for object addressing:

```sql
SELECT *
FROM pg_identify_object(
    'pg_class'::regclass,
    'app.orders'::regclass,
    0
);
```

On supporting versions, `pg_identify_object_as_address` also returns object addresses as structured components usable in tooling. These helpers are great for building inventories and reports, while still requiring version compatibility checks.

### 11.7. Column-Level Dependencies

A dependency can point to an entire relation or to a specific column. When `refobjsubid` is greater than 0, it is typically the column's attribute number.

Looking up the column name:

```sql
SELECT
    pg_describe_object(
        d.classid,
        d.objid,
        d.objsubid
    ) AS dependent_object,
    d.refobjsubid AS referenced_attnum,
    a.attname AS referenced_column,
    d.deptype
FROM pg_depend AS d
LEFT JOIN pg_attribute AS a
    ON a.attrelid = d.refobjid
   AND a.attnum = d.refobjsubid
WHERE d.refclassid = 'pg_class'::regclass
  AND d.refobjid = 'app.orders'::regclass
ORDER BY dependent_object, d.refobjsubid;
```

Do not assume every `refobjsubid` across all catalog classes represents a column number; this join applies to referenced relation objects.

## 12. Shared Dependencies with pg_shdepend

Some objects are shared cluster-wide, such as roles and tablespaces. Dependencies on shared objects are recorded in `pg_shdepend`.

### 12.1. What Is pg_shdepend Used For?

It records relationships such as:

- Objects owned by a role.
- Objects with an ACL/grant referencing a role.
- Objects depending on a shared object.
- Other shared metadata relationships depending on version.

### 12.2. Viewing Objects Depending on a Role

Example role dependency inventory:

```sql
SELECT
    d.dbid,
    CASE
        WHEN d.dbid = 0 THEN 'shared object'
        ELSE db.datname
    END AS database_name,
    pg_describe_object(
        d.classid,
        d.objid,
        d.objsubid
    ) AS dependent_object,
    d.deptype AS dependency_type
FROM pg_shdepend AS d
LEFT JOIN pg_database AS db
    ON db.oid = d.dbid
WHERE d.refclassid = 'pg_authid'::regclass
  AND d.refobjid = (
      SELECT oid
      FROM pg_roles
      WHERE rolname = 'legacy_app'
  )
ORDER BY database_name, dependent_object;
```

The role must exist for the query to return meaningful rows. Reading shared dependency metadata may be restricted; execute using an appropriate administrative role.

### 12.3. Ownership and Grants Are Separate Concerns

A role may not own an object yet still hold `SELECT` or `EXECUTE` grants. Conversely, a role may own an object without appearing as a separate grantee in the ACL.

Before dropping a role:

- Check object ownership.
- Check grants and default privileges.
- Check role memberships and inheritance.
- Check database-level privileges.
- Check jobs, connection strings, and external secrets.
- Verify whether the role owns extensions or schemas.

### 12.4. REASSIGN OWNED and DROP OWNED

`REASSIGN OWNED` transfers ownership of objects in the current database and associated shared objects per command semantics. `DROP OWNED` drops objects owned by the role and revokes privileges granted to the role within the current database; its impact can be sweeping.

These commands have wide blast radii and must run under a role-decommission process with inventories, reviews, and backups. They do not replace verifying whether applications still use the role.

## 13. Extension Dependencies

An extension manages a bundle of objects such as functions, types, operators, casts, and views. PostgreSQL records membership dependencies showing which extension owns an object.

### 13.1. Listing Extensions

```sql
SELECT
    e.oid,
    e.extname,
    e.extversion,
    n.nspname AS extension_schema,
    pg_get_userbyid(e.extowner) AS owner,
    e.extrelocatable
FROM pg_extension AS e
JOIN pg_namespace AS n
    ON n.oid = e.extnamespace
ORDER BY e.extname;
```

### 13.2. Viewing Extension Member Objects

```sql
SELECT
    e.extname,
    pg_describe_object(
        d.classid,
        d.objid,
        d.objsubid
    ) AS extension_member
FROM pg_extension AS e
JOIN pg_depend AS d
    ON d.refclassid = 'pg_extension'::regclass
   AND d.refobjid = e.oid
   AND d.deptype = 'e'
ORDER BY e.extname, extension_member;
```

Never manually drop individual member objects while the extension still manages them. Use `DROP EXTENSION ... RESTRICT` or the official upgrade/drop procedure.

### 13.3. Extension Dependencies

One extension can depend on another extension. Inspect extension dependencies before dropping:

```sql
SELECT
    pg_describe_object(
        d.classid,
        d.objid,
        d.objsubid
    ) AS dependent_object,
    d.deptype,
    pg_describe_object(
        d.refclassid,
        d.refobjid,
        d.refobjsubid
    ) AS referenced_object
FROM pg_depend AS d
WHERE d.refclassid = 'pg_extension'::regclass
ORDER BY referenced_object, dependent_object;
```

An extension can be used across multiple schemas and objects. Evaluate applications, migrations, and other databases in the cluster before removing packages or server libraries.

## 14. Static Dependencies vs. Runtime References

Dependency catalogs are valuable, yet they cannot observe every way applications interact with a database.

### 14.1. Dependencies PostgreSQL Can Record

Examples:

- Views referencing tables or columns.
- Constraints referencing tables, types, or indexes.
- Default expressions referencing sequences.
- Function signatures referencing custom types.
- Objects belonging to an extension.
- Objects owned by schemas or roles under corresponding dependency types.

### 14.2. References That May Not Be Fully Recorded

Examples:

- Dynamic SQL constructing table names from input.
- Applications assembling SQL strings at runtime.
- ORMs generating queries behind feature flags.
- BI tools sending queries from external dashboards.
- Scheduled jobs managed in external orchestration systems.
- External services invoking functions by name.
- Code relying on `search_path` and unqualified object names.
- SQL stored in configuration repositories or secrets.

### 14.3. Catalogs Are Not Application Call Graphs

PostgreSQL cannot build a complete call graph across all application code and external systems. Combine source searches, application telemetry, database logs, audit records, and owner confirmation to complete the evidence.

### 14.4. Having a Dependency Does Not Mean an Object Is Actively Called

A dependency is a structural relationship. A view may depend on a table without being queried for months. Conversely, an object with zero catalog dependencies might still be queried directly by an external client.

Separate two questions:

1. What structural dependencies does the object have?
2. Is the object actually used in production workloads?

Those two questions require two different kinds of evidence.

## 15. Identifying Unused Objects

There is no universal `unused` flag in PostgreSQL catalogs. Determining whether an object is unused requires combining statistics, logs, code searches, and lifecycle knowledge.

### 15.1. Evidence by Confidence Level

| Evidence | What Can Be Concluded? | Limitations |
| --- | --- | --- |
| Dependency catalog | Static dependent objects exist | Incomplete for dynamic/runtime references |
| Index/table stats | Scans occurred during the stats window | Counters may reset; workloads can be seasonal |
| `pg_stat_statements` | Executed query fingerprints and frequencies | Not a complete object-level access audit |
| Slow/general logs | Query text within the logging window | Captures only configured statements |
| Application code search | References found in searched repositories | May miss dynamic SQL, configs, or external code |
| Scheduler/job inventory | Jobs that may access objects | Must cover every scheduler |
| Owner confirmation | Confirms business purpose and lifecycle | Requires the right owner and supporting evidence |
| Staging deprecation | No regressions during testing | Does not prove all production paths |

### 15.2. Choosing an Observation Window

The window must span real usage cycles:

- Daily jobs: at least one or multiple daily cycles.
- Weekly reports: multiple weekly cycles.
- Month-end close: must observe through month-end close.
- Quarterly/year-end processing: requires checking calendars and owners; cannot conclude from one week of stats.
- Disaster recovery/rare maintenance: inspect runbooks and operational dependencies.

No single default window fits every system. Base it on business calendars and RTO/RPO requirements.

### 15.3. Statistics Resets and Restarts

If counters recently reset, an object may not have had a chance to appear during the observation window. Record `stats_reset`, restart/deploy timelines, and collector uptime before classifying candidates.

### 15.4. Objects Written to Without Reads

A table may be:

- An audit log.
- An outbox queue.
- An event inbox.
- A staging or import table.
- A retention archive.
- Materialized state for downstream export.
- A buffer for a scheduled job.

Zero read scans do not prove a table can be deleted. Inspect write paths, cleanup policies, retention, and external consumers.

### 15.5. Indirectly Invoked Objects

Functions may call tables via dynamic SQL; views may be queried by downstream reports; triggers fire during DML. Check triggers, rules, routines, dependencies, and code paths.

## 16. Using pg_stat_statements as Workload Evidence

`pg_stat_statements` aggregates query execution by normalized query. It helps locate query references to tables and functions, though it does not replace audit logs.

### 16.1. Inspecting Query Fingerprints

If the extension is preloaded and created in the database:

```sql
SELECT
    queryid,
    calls,
    total_exec_time,
    mean_exec_time,
    rows,
    left(query, 1000) AS query_sample
FROM pg_stat_statements
ORDER BY calls DESC
LIMIT 100;
```

Query text may be normalized and omit literal values. For dynamic SQL, query text reflects the generated statement while still requiring correlation with callers.

### 16.2. Searching for References to an Object Name

Example searching query text mentioning a relation:

```sql
SELECT
    queryid,
    calls,
    total_exec_time,
    left(query, 1000) AS query_sample
FROM pg_stat_statements
WHERE query ILIKE '%app.orders%'
ORDER BY calls DESC;
```

This is a simple text search. It can miss unqualified names, quoted identifiers, aliases, prepared statements, or dynamically assembled queries. It can also falsely match comments or string literals.

### 16.3. pg_stat_statements Can Reset or Evict Entries

Entries can be reset or evicted under pressure against `pg_stat_statements.max`. Save periodic snapshots if long-term history is needed.

### 16.4. Do Not Use queryid as a Cross-Version Identifier

Query IDs can depend on PostgreSQL version, parse trees, and object identities. Store server version, database, schema context, and normalized query text for long-term comparisons.

## 17. Classifying Unused Candidates by Object Type

Each object type has distinct usage patterns and evidence requirements.

### 17.1. Indexes

Evidence:

- Low or zero `idx_scan` over a sufficiently long window.
- Not backing a constraint.
- Not a primary key or replica identity.
- Not used by rare reporting jobs.
- Not required by query plans under representative workloads.

Risks:

- A unique index may enforce a business invariant.
- An index may support foreign-key delete/update checks or rare queries.
- Partitioned table indexes relate to child indexes.
- Index usage can shift after data growth or plan changes.

### 17.2. Tables

Evidence:

- Zero scans across multiple business cycles.
- Zero writes or zero rows.
- No static dependencies.
- No application or job references.
- Owner confirms deprecation.

Risks:

- Audit or retention tables.
- Outbox/inbox queues.
- Staging tables.
- External reporting.
- Seasonal jobs.
- Restore/DR procedures.

### 17.3. Views

Evidence:

- No query references found in logs or traces.
- No other views depend on it.
- Not used by applications or BI tools.
- Owner confirms deprecation.

Risks:

- Catalogs offer no direct view usage counter.
- Views may serve as compatibility APIs.
- Dynamic SQL may query the view.
- `security_barrier` or `security_invoker` semantics may be important.

### 17.4. Materialized Views

Evidence:

- No consumers.
- Refresh jobs no longer run.
- No downstream exports.
- Data freshness is no longer required.

Risks:

- Dashboards opened only monthly or quarterly.
- Refresh schedules living in an external scheduler.
- Materialized views serving as key caches to offload primary workloads.

### 17.5. Functions and Procedures

Evidence:

- Function statistics show zero calls in the window while tracking is enabled.
- No static dependencies.
- No application or job references.
- Not called by triggers or rules.

Risks:

- Functions called from external SQL.
- Functions invoked via dynamic SQL or string-based RPC.
- Functions rarely called by migrations or maintenance.
- `track_functions` may be turned off.

### 17.6. Sequences

Evidence:

- No column ownership.
- No default expression dependency.
- No code references to `nextval`/`currval`/`setval`.
- No integration or job references.

Risks:

- Sequences invoked directly.
- Caching and `last_value` may not reflect every issued value.
- Sequences serving as business counters.

### 17.7. Schemas, Types, and Extensions

A schema with zero relations can still contain routines or types. A type can appear in function signatures or application contracts. An extension can provide functions and types relied upon by many objects.

Audit all object classes before classifying a schema or extension as unused.

## 18. Finding Standalone Sequence Candidates

The query below lists sequences lacking an ownership dependency on a table column. Results are candidates for investigation:

```sql
SELECT
    n.nspname AS schema_name,
    s.relname AS sequence_name,
    pg_get_userbyid(s.relowner) AS owner
FROM pg_class AS s
JOIN pg_namespace AS n
    ON n.oid = s.relnamespace
WHERE s.relkind = 'S'
  AND n.nspname NOT LIKE 'pg\_%' ESCAPE '\'
  AND n.nspname <> 'information_schema'
  AND NOT EXISTS (
      SELECT 1
      FROM pg_depend AS d
      WHERE d.classid = 'pg_class'::regclass
        AND d.objid = s.oid
        AND d.refclassid = 'pg_class'::regclass
        AND d.refobjsubid > 0
        AND d.deptype IN ('a', 'i')
  )
ORDER BY n.nspname, s.relname;
```

Standalone sequences can be entirely intentional. This query only detects missing ownership dependencies—it does not prove the sequence is never called.

## 19. Finding Apparently Empty Schemas

You can list schemas containing no relations:

```sql
SELECT
    n.nspname AS schema_name,
    pg_get_userbyid(n.nspowner) AS owner
FROM pg_namespace AS n
WHERE n.nspname NOT LIKE 'pg\_%' ESCAPE '\'
  AND n.nspname <> 'information_schema'
  AND NOT EXISTS (
      SELECT 1
      FROM pg_class AS c
      WHERE c.relnamespace = n.oid
  )
ORDER BY n.nspname;
```

This only means the schema has no entries in `pg_class`. It may still contain routines, types, operators, collations, or other objects. Before dropping a schema, inventory additional catalogs and inspect dependencies.

## 20. Checking Object Ownership and Stale Owners

An object owner holds administrative control over the object, yet that role may belong to someone who left the organization or is no longer used.

### 20.1. Relation Owners

```sql
SELECT
    n.nspname AS schema_name,
    c.relname AS relation_name,
    c.relkind,
    pg_get_userbyid(c.relowner) AS owner
FROM pg_class AS c
JOIN pg_namespace AS n
    ON n.oid = c.relnamespace
WHERE n.nspname NOT LIKE 'pg\_%' ESCAPE '\'
  AND n.nspname <> 'information_schema'
ORDER BY owner, n.nspname, c.relname;
```

### 20.2. Schema Owners

```sql
SELECT
    n.nspname AS schema_name,
    pg_get_userbyid(n.nspowner) AS owner
FROM pg_namespace AS n
WHERE n.nspname NOT LIKE 'pg\_%' ESCAPE '\'
  AND n.nspname <> 'information_schema'
ORDER BY owner, schema_name;
```

### 20.3. Role Inventory

```sql
SELECT
    rolname,
    rolcanlogin,
    rolsuper,
    rolcreatedb,
    rolcreaterole,
    rolreplication,
    rolconnlimit,
    rolvaliduntil
FROM pg_roles
ORDER BY rolname;
```

Roles with `LOGIN` set to false may still be group roles used for grants. Never drop a role simply because it cannot log in directly.

### 20.4. Default Privileges

```sql
SELECT
    defaclrole::regrole AS creator_role,
    defaclnamespace::regnamespace AS schema_name,
    defaclobjtype AS object_type,
    defaclacl
FROM pg_default_acl
ORDER BY creator_role, schema_name, object_type;
```

When decommissioning a role, check default ACLs so stale grants do not keep applying or leaving that role referenced as a creator role for new objects.

## 21. Inspecting Privileges and ACLs

Objects may be used by roles other than their owner. Dependency and ownership inventories must pair with grant reviews.

### 21.1. Table Privileges

```sql
SELECT
    table_schema,
    table_name,
    grantee,
    privilege_type,
    is_grantable
FROM information_schema.role_table_grants
WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
ORDER BY table_schema, table_name, grantee, privilege_type;
```

This view reflects grants filtered by Information Schema visibility rules. For thorough audits, inspect catalog ACLs and default privileges too.

### 21.2. Function Privileges

```sql
SELECT
    routine_schema,
    routine_name,
    grantee,
    privilege_type,
    is_grantable
FROM information_schema.routine_privileges
WHERE routine_schema NOT IN ('pg_catalog', 'information_schema')
ORDER BY routine_schema, routine_name, grantee;
```

Overloaded functions can share the same name. Use identity arguments to distinguish signatures.

### 21.3. PUBLIC Privileges

Privileges granted to `PUBLIC` apply broadly to all roles. Audit default privileges and object ACLs when databases have strict security requirements.

### 21.4. Do Not Edit ACLs Directly in Catalogs

Use `GRANT`/`REVOKE`, `ALTER DEFAULT PRIVILEGES`, and object ownership commands. Never `UPDATE` system catalog rows directly with SQL to alter ACLs or owners.

## 22. DROP RESTRICT and DROP CASCADE

PostgreSQL supports dependency-aware DDL. Understanding the difference is mandatory before cleanup.

### 22.1. RESTRICT

`RESTRICT` refuses the drop if dependent objects exist that would be affected. This is the default behavior for many `DROP` commands.

Example:

```sql
DROP TABLE app.orders RESTRICT;
```

If a view or another object depends on the table, PostgreSQL errors and lists dependencies. Use `RESTRICT` in cleanup workflows to prevent unintended cascading deletions.

### 22.2. CASCADE

`CASCADE` drops the object along with dependent objects per dependency rules:

```sql
DROP TABLE app.orders CASCADE;
```

This can drop views, rules, constraints, or other objects according to the dependency graph. A single `CASCADE` can reach far further than expected. Never use `CASCADE` as a shortcut to "clean things out" without reading the full list of dependent objects first.

### 22.3. CASCADE Does Not Detect Runtime References

If an application queries a table via dynamic SQL, external BI tools, or a job scheduler, PostgreSQL may have no catalog record of that dependency. `CASCADE` cannot warn about callers outside the catalog graph.

### 22.4. Transaction Dry Runs in Test Environments

For transactional DDL, you can test operations inside a transaction and roll back in lab/staging:

```sql
BEGIN;
SET LOCAL lock_timeout = '2s';

DROP VIEW reporting.orders_summary RESTRICT;

ROLLBACK;
```

Understand lock behavior and event-trigger side effects. Transaction rollback does not neutralize external side effects from extensions or event triggers. Never test destructive DDL in production merely because you plan to roll back.

### 22.5. DROP IF EXISTS Is Not a Safety Check

`DROP ... IF EXISTS` only suppresses errors when the object does not exist. It does not validate that the object is safe to remove or prevent data loss.

## 23. Deprecation Workflow Before Dropping

Even obsolete objects require a controlled deprecation period.

### 23.1. Inventory

Record:

- Object type, schema, name, and owner.
- OID/identity at audit time.
- Size and dependencies.
- Related constraints and indexes.
- Extension membership.
- Grants and known callers.
- Statistics reset timestamp and observation window.

### 23.2. Identify Owners

Each candidate object needs a technical owner and a business owner. Owners must confirm purpose, consumers, retention, and deprecation timelines.

### 23.3. Search for References Outside Catalogs

Search application repositories, migration files, ORM mappings, SQL templates, dashboard/report definitions, scheduled jobs, and integration configs.

### 23.4. Announce Deprecation

Create a migration/change request documenting:

- The object to deprecate.
- Consumers/owners required to confirm.
- Decommission timeline.
- Rollback method.
- Metrics and logs to monitor.
- Approvers.

### 23.5. Stop Callers First

Deploy code that stops calling the object, disable jobs, or migrate consumers to replacements. Monitor errors and logs across an appropriate observation window.

### 23.6. Drop with RESTRICT

Once dependencies and runtime references are cleared, drop the object using `RESTRICT`. If the command reports dependencies, return to the inventory to trace what remains linked.

### 23.7. Post-Change Verification

After dropping:

- Confirm migration completion.
- Check application errors and scheduled jobs.
- Verify dependent views and functions still operate properly.
- Monitor database logs and metrics.
- Update the inventory and ownership registry.
- Retain rollback/restore paths per policy.

## 24. Inspecting Partitioning and Inheritance Dependencies

Partitioned tables create numerous relationships between parent and child relations. Cleaning up a partition requires understanding its data and associated indexes.

### 24.1. Listing Inheritance/Partition Relationships

```sql
SELECT
    parent_ns.nspname AS parent_schema,
    parent.relname AS parent_table,
    child_ns.nspname AS child_schema,
    child.relname AS child_table,
    inh.inhseqno,
    inh.inhdetachpending
FROM pg_inherits AS inh
JOIN pg_class AS parent
    ON parent.oid = inh.inhparent
JOIN pg_namespace AS parent_ns
    ON parent_ns.oid = parent.relnamespace
JOIN pg_class AS child
    ON child.oid = inh.inhrelid
JOIN pg_namespace AS child_ns
    ON child_ns.oid = child.relnamespace
ORDER BY parent_ns.nspname, parent.relname, inh.inhseqno;
```

Columns like `inhdetachpending` may be absent on older versions. If queries run across multiple versions, check catalog schemas first.

### 24.2. Partitions Without Traffic

An older partition may no longer receive inserts yet still store historical data for reporting, compliance, or range scans. Never classify a partition as unused based on write activity alone.

### 24.3. Detaching and Dropping

`DETACH PARTITION` and `DROP TABLE` have different semantics and locking across versions and options. Check foreign keys, partitioned indexes, constraints, retention rules, and concurrent operations before detaching or dropping.

### 24.4. Partitioned Indexes

A parent partitioned index has child indexes. Verify states and definitions across the entire hierarchy before dropping an index or partition.

## 25. Checking Object Descriptions and Comments

Comments help document owners and purposes inside catalogs.

### 25.1. Relation Comments

```sql
SELECT
    n.nspname AS schema_name,
    c.relname AS object_name,
    col_description(c.oid, 0) AS relation_comment
FROM pg_class AS c
JOIN pg_namespace AS n
    ON n.oid = c.relnamespace
WHERE n.nspname = 'app'
ORDER BY c.relname;
```

### 25.2. Column Comments

```sql
SELECT
    n.nspname AS schema_name,
    c.relname AS table_name,
    a.attname AS column_name,
    col_description(c.oid, a.attnum) AS column_comment
FROM pg_class AS c
JOIN pg_namespace AS n
    ON n.oid = c.relnamespace
JOIN pg_attribute AS a
    ON a.attrelid = c.oid
WHERE n.nspname = 'app'
  AND a.attnum > 0
  AND NOT a.attisdropped
ORDER BY c.relname, a.attnum;
```

### 25.3. Comments as Administrative Metadata

You can standardize comment formats to record owner team, purpose, data classification, retention, and ticket references. Never place secrets or personal data inside comments; catalogs can be read by many roles.

## 26. Schema Drift Across Environments

Development, staging, and production can diverge after migrations or hotfixes.

### 26.1. Comparing by Object Identity

Do not compare OIDs across environments. Compare:

- Schema name.
- Object name and type.
- Column order, name, type, nullability, and defaults.
- Constraint definitions.
- Index definitions and validity.
- View and function definitions.
- Ownership and privileges.
- Extension names and versions.
- Partition hierarchies.
- Comments and metadata.

### 26.2. Using Migration History

Catalog snapshots capture current state; migration history captures the intended steps that created that state. Check both to catch hotfixes missing from migration repositories or missed migrations.

### 26.3. Drift Reports

A useful report categorizes:

- Missing objects.
- Unexpected objects.
- Definition mismatches.
- Owner/ACL mismatches.
- Extension version mismatches.
- Invalid or unvalidated object states.
- Dependency mismatches.

### 26.4. Never Sync by Copying Catalog Rows

Catalogs are internal implementation details. Use DDL, migration scripts, or schema management tools. Never copy or update system catalog rows directly between databases.

## 27. Consolidated Audit Queries

You can save the following queries as a read-only audit script and run it periodically with an appropriately privileged role.

### 27.1. Basic Object Inventory

```sql
SELECT
    current_database() AS database_name,
    n.nspname AS schema_name,
    c.relname AS object_name,
    c.relkind AS relation_kind,
    pg_get_userbyid(c.relowner) AS owner,
    pg_total_relation_size(c.oid) AS total_bytes
FROM pg_class AS c
JOIN pg_namespace AS n
    ON n.oid = c.relnamespace
WHERE n.nspname NOT LIKE 'pg\_%' ESCAPE '\'
  AND n.nspname <> 'information_schema'
  AND c.relkind IN ('r', 'p', 'v', 'm', 'S', 'f')
ORDER BY n.nspname, c.relname;
```

### 27.2. Dependencies of a Relation

```sql
SELECT
    pg_describe_object(
        d.classid,
        d.objid,
        d.objsubid
    ) AS dependent_object,
    d.deptype,
    pg_describe_object(
        d.refclassid,
        d.refobjid,
        d.refobjsubid
    ) AS referenced_object
FROM pg_depend AS d
WHERE d.refclassid = 'pg_class'::regclass
  AND d.refobjid = to_regclass('app.orders')
ORDER BY dependent_object;
```

If `to_regclass` returns `NULL`, the query did not find the referenced object. Verify spelling and schema before interpreting an empty result.

### 27.3. Unused Index Candidates

```sql
SELECT
    s.schemaname,
    s.relname AS table_name,
    s.indexrelname AS index_name,
    s.idx_scan,
    i.indisprimary,
    i.indisunique,
    i.indisreplident,
    EXISTS (
        SELECT 1
        FROM pg_constraint AS con
        WHERE con.conindid = i.indexrelid
    ) AS backs_constraint,
    pg_size_pretty(pg_relation_size(i.indexrelid)) AS index_size
FROM pg_stat_user_indexes AS s
JOIN pg_index AS i
    ON i.indexrelid = s.indexrelid
WHERE s.idx_scan = 0
ORDER BY pg_relation_size(i.indexrelid) DESC;
```

### 27.4. Tables Without Scans in the Stats Window

```sql
SELECT
    schemaname,
    relname,
    seq_scan,
    idx_scan,
    n_tup_ins,
    n_tup_upd,
    n_tup_del,
    n_live_tup
FROM pg_stat_user_tables
WHERE COALESCE(seq_scan, 0) = 0
  AND COALESCE(idx_scan, 0) = 0
ORDER BY n_live_tup DESC;
```

### 27.5. Invalid Indexes and Unvalidated Constraints

```sql
SELECT
    ns.nspname AS schema_name,
    tbl.relname AS table_name,
    idx.relname AS index_name,
    i.indisvalid,
    i.indisready
FROM pg_index AS i
JOIN pg_class AS idx ON idx.oid = i.indexrelid
JOIN pg_class AS tbl ON tbl.oid = i.indrelid
JOIN pg_namespace AS ns ON ns.oid = tbl.relnamespace
WHERE NOT i.indisvalid OR NOT i.indisready
ORDER BY ns.nspname, tbl.relname, idx.relname;
```

```sql
SELECT
    ns.nspname,
    tbl.relname,
    con.conname,
    pg_get_constraintdef(con.oid, true) AS definition
FROM pg_constraint AS con
JOIN pg_class AS tbl ON tbl.oid = con.conrelid
JOIN pg_namespace AS ns ON ns.oid = tbl.relnamespace
WHERE NOT con.convalidated
ORDER BY ns.nspname, tbl.relname, con.conname;
```

## 28. Automation for Catalog Audits

Periodic audits detect schema drift and candidate objects earlier than massive sporadic cleanups.

### 28.1. Run Read-Only

The audit role needs only read access to required metadata and statistics. Never grant `DROP` or `ALTER` privileges to inventory jobs.

### 28.2. Point-in-Time Snapshots

Save inventory outputs alongside:

- Database identity and environment.
- PostgreSQL version.
- Timestamp.
- Migration version.
- Statistics reset timestamp.
- Query/script version.
- Role executing the audit.

Do not store OIDs as cross-environment identities; you may keep OIDs as diagnostic fields within a snapshot paired with database identity.

### 28.3. Diffing Snapshots

Compare the current snapshot against the prior snapshot to detect:

- New objects.
- Dropped objects.
- Owner changes.
- Definition or ACL changes.
- Extension upgrades.
- Index validity changes.
- Dependency graph changes.
- Table/index size growth.

### 28.4. Never Auto-Drop Based on Reports

Automation can label candidates, open tickets, or email owners. Destructive DDL requires lifecycle review and approval. A job must never drop an index or table merely because a counter is zero.

### 28.5. Catalog Query Cost

Catalog queries are lighter than full table scans, yet cluster- or database-wide inventories on huge schemas can still consume CPU, memory, and time. Avoid scanning large definitions or calling `pg_total_relation_size` on every object in high-frequency scrapes every few seconds. Separate periodic inventories from high-frequency runtime metrics.

## 29. Security During Catalog Audits

Catalogs can reveal schemas, role names, function definitions, ownership, and security configurations.

### 29.1. Least Privilege

Use a dedicated audit role with read access strictly limited to needed metadata. Views exposing other sessions' activity require appropriate monitoring privileges per version.

### 29.2. Security Definer Routines

When inventorying routines, flag `prosecdef` to spot `SECURITY DEFINER` functions. Inspect owners, `search_path`, and `EXECUTE` grants. A security-definer function runs with elevated owner rights; never drop or alter it without evaluating its security contract.

### 29.3. Search Path

Routines and application sessions may depend on `search_path`. Unqualified object names can resolve to different objects if `search_path` changes. Check routine definitions, role/database defaults, and `proconfig` when auditing behavior.

### 29.4. Do Not Broadcast Sensitive Metadata Broadly

Function bodies, grants, role names, and schema layouts can be sensitive internal details. Restrict read access to audit reports and enforce retention/access controls.

## 30. Common Pitfalls When Reading Catalogs

| Symptom / Assumption | Why It Is Wrong | How to Handle |
| --- | --- | --- |
| Table missing from `information_schema` | Role lacks visibility or different object type | Check privileges and `pg_catalog` |
| No dependency shown | Runtime/dynamic SQL is not recorded | Search code, logs, jobs, and external callers |
| `idx_scan = 0` means unused | Short/reset stats window or rare workload | Observe across business cycles and check constraints |
| Table with zero scans can be dropped | May be audit/outbox/staging or external consumer | Check writes, owner, retention, and jobs |
| Sequence `last_value` NULL means unused | Missing privileges or unflushed cache state | Check ownership, defaults, code, and permissions |
| Views have no usage stats | PostgreSQL lacks direct counters per view | Use logs, query stats, and dependencies |
| Function `calls = 0` means dead code | `track_functions` may be off; external callers | Check setting, code, and runtime logs |
| `DROP CASCADE` deletes only one object | Can wipe out an entire dependency tree | Inventory dependents, use `RESTRICT` |
| Schema with no tables is empty | May contain routines, types, or operators | Inventory all object classes |
| Non-`LOGIN` role is unused | May be a group role or owner | Check memberships, ownership, and ACLs |
| OIDs match across environments | OIDs are not stable cross-environment IDs | Compare schema-qualified identities and definitions |
| Catalog columns match across all versions | Catalogs change across major versions | Check `server_version` and catalog schemas |
| Extension objects can be dropped individually | Objects belong to extension lifecycle | Manage via extension commands |
| Statistics are audit logs | Statistics are merely aggregate counters | Use auditing/logging if caller history is needed |

## 31. End-to-End Audit and Cleanup Process

**Step 1 — Define scope.** Select databases, schemas, object types, and audit goals: inventory, drift, security, or unused candidates.

**Step 2 — Record baseline.** Save PostgreSQL version, database identity, migration version, and statistics reset timestamps.

**Step 3 — Build inventory.** Collect schemas, relations, columns, constraints, indexes, routines, sequences, extensions, owners, and ACLs.

**Step 4 — Build dependency graph.** Use `pg_depend`/`pg_shdepend` and helper functions to list dependent objects, extension membership, and role dependencies.

**Step 5 — Analyze runtime evidence.** Inspect table/index/function stats, `pg_stat_statements`, logs, traces, and scheduler inventories.

**Step 6 — Verify with owners.** Confirm business purpose, seasonal usage, retention, external integrations, and deprecation timelines.

**Step 7 — Classify risk.** Label keep, investigate, deprecate, or approved-for-removal. Document evidence and confidence.

**Step 8 — Deprecate callers.** Deploy application/job changes and observe over a suitable observation window.

**Step 9 — Re-check dependencies.** Run an inventory immediately prior to DDL to catch newly created or referenced objects.

**Step 10 — Drop with RESTRICT.** Use explicit schema-qualified names and a sensible lock timeout. If dependencies surface, stop and review.

**Step 11 — Post-cleanup verification.** Check application errors, jobs, reports, catalog state, and database metrics.

**Step 12 — Update registry.** Record DDL/migrations, owners, audit outcomes, and rollback/restore information.

## 32. Practice Exercises

Perform these in a dedicated PostgreSQL lab. Never drop objects, revoke roles, or run `CASCADE` in production merely for testing.

### Exercise 1 — Information Schema

List schemas, tables, and columns using `information_schema`. Compare visibility using two roles with differing privileges.

### Exercise 2 — pg_class Inventory

Use `pg_class`/`pg_namespace` to list tables, indexes, sequences, views, and materialized views. Distinguish `relkind`.

### Exercise 3 — OID and regclass

Retrieve an object's OID using `pg_class` and `to_regclass`. Explain why OIDs are not stable identifiers across environments.

### Exercise 4 — Column Metadata

Use `pg_attribute`/`pg_attrdef` to list types, nullability, identity, generated columns, and defaults.

### Exercise 5 — Constraints Inventory

List primary, unique, foreign-key, check, and exclusion constraints using `pg_constraint`.

### Exercise 6 — Foreign-Key Graph

Create two tables with a foreign key. Use `pg_constraint` to display child/parent relationships and constraint definitions.

### Exercise 7 — Unvalidated Constraints

Create a `NOT VALID` constraint in the lab. Inspect `convalidated` and determine when `VALIDATE CONSTRAINT` should run.

### Exercise 8 — Index Inventory

Use `pg_index` and `pg_class` to retrieve definitions, sizes, and unique/primary/replica-identity flags.

### Exercise 9 — Invalid Indexes

Simulate a failed concurrent index build in the lab if possible. Locate the invalid/not-ready index and outline safe remediation.

### Exercise 10 — Constraint-Backed Indexes

Join `pg_constraint.conindid` with `pg_index`. Demonstrate why an index backing a PK or unique constraint must not be marked unused from `idx_scan` alone.

### Exercise 11 — Index Scan Statistics

Run a workload using an index and a workload bypassing it. Compare `idx_scan` before/after and record the stats reset timestamp.

### Exercise 12 — Zero-Scan Index Candidate

Create a rarely used index in the lab. Generate an `idx_scan = 0` report and write a verification checklist before proposing a drop.

### Exercise 13 — Table Scan Statistics

Create a table receiving `SELECT`/`INSERT`/`UPDATE`/`DELETE`. Observe `pg_stat_user_tables` counters.

### Exercise 14 — Stats Reset

Reset statistics in the lab if permitted. Observe counters and explain why zero scans after a reset does not prove non-use.

### Exercise 15 — View Dependencies

Create a view on a table. Use `pg_depend` and `pg_describe_object` to find views depending on the table.

### Exercise 16 — Nested Views

Create a view depending on another view. Build a dependency report and determine the deprecation order.

### Exercise 17 — Materialized Views

Create a materialized view, refresh it, and inspect `pg_matviews`. Build an inventory covering owner, populated state, and refresh consumers.

### Exercise 18 — Function Inventory

Create overloaded functions sharing a name with different arguments. Use `pg_get_function_identity_arguments` to distinguish them.

### Exercise 19 — Function Statistics

Enable `track_functions` in the lab (restarting if needed), invoke functions, and observe `pg_stat_user_functions`. Disable tracking and note limitations.

### Exercise 20 — Dynamic SQL

Create a function using `EXECUTE` to query a table by dynamic name. Compare catalog dependencies against references inside the function body.

### Exercise 21 — Trigger Inventory

Create a trigger and trigger function. List via `pg_trigger`, distinguishing user triggers from internal triggers.

### Exercise 22 — Sequence Ownership

Create a serial/identity column and a standalone sequence. Use `pg_depend` to find sequence-column ownership relationships.

### Exercise 23 — Sequence Usage

Call `nextval` in the lab, inspect `pg_sequences.last_value`, and explain limitations due to permissions and caching.

### Exercise 24 — Extension Membership

Install an available extension in the lab. Use `pg_extension` and `pg_depend` to list members. Test `DROP EXTENSION RESTRICT` in a test database.

### Exercise 25 — Role Ownership

Create an owner role and several objects. Use `pg_shdepend` to inventory dependencies on that role.

### Exercise 26 — ACL Inventory

Run `GRANT`/`REVOKE` on tables and functions. Compare `information_schema` grants with catalog ACLs and default privileges.

### Exercise 27 — Schemas Without Relations

Create a schema containing only a function or type. Run a query finding schemas without `pg_class` relations and explain why it cannot be dropped immediately.

### Exercise 28 — Partition Dependencies

Create a partitioned table, partitions, and indexes. Use `pg_inherits`/`pg_depend` to inventory the hierarchy.

### Exercise 29 — Object Descriptions

Use `pg_describe_object`, `pg_identify_object`, and `regclass` to produce a readable report for a dependency graph.

### Exercise 30 — RESTRICT and CASCADE

In the lab, create a table/view dependency. Test `DROP TABLE RESTRICT` and `CASCADE` in a rollback-safe database; record affected objects.

### Exercise 31 — Unused Candidate Assessment

Create tables, indexes, and functions with varied usage. Combine stats, dependencies, and code searches to classify keep/investigate/deprecate.

### Exercise 32 — Seasonal Workloads

Design an observation window for a monthly/quarterly report. Explain why one week of `idx_scan = 0` is insufficient to drop an index.

### Exercise 33 — Schema Drift

Create two lab databases with differing schema definitions. Compare names, columns, constraints, indexes, owners, and extension versions without comparing OIDs.

### Exercise 34 — Catalog Audit Snapshot

Write a read-only script exporting object inventories and dependencies with server version, timestamp, and stats reset time. Save snapshots and compute a diff on the next run.

### Exercise 35 — Cleanup Runbook

Select a lab object as an unused candidate. Write a deprecation record, verify callers and dependencies, drop with `RESTRICT`, verify post-drop state, and document the rollback path.

## 33. Summary

Key takeaways when **inspecting catalogs, dependencies, and unused objects**:

1. Information Schema provides standardized metadata; `pg_catalog` provides PostgreSQL-specific details.
2. `pg_class`, `pg_namespace`, `pg_attribute`, `pg_type`, `pg_proc`, `pg_constraint`, and `pg_index` form the inventory foundation.
3. OIDs are useful for joining catalogs within a database, not stable across environments or object recreation.
4. `pg_depend` describes intra-database dependencies; `pg_shdepend` describes dependencies on shared objects like roles.
5. `pg_describe_object` and `pg_identify_object` produce readable dependency reports.
6. Dependency graphs show structural links, not complete application call graphs.
7. Index scan counters and table statistics are meaningful only over known observation windows.
8. Constraint-backing indexes, replica identities, seasonal indexes, and audit/outbox tables must be protected from naive unused classifications.
9. Function, view, and sequence usage may lack complete counters; dynamic SQL and external callers require separate checks.
10. Extension objects must be managed through the extension lifecycle.
11. Ownership, ACLs, default privileges, and role memberships must all be reviewed before decommissioning roles.
12. `DROP RESTRICT` surfaces catalog dependencies; `DROP CASCADE` can wipe out entire dependency trees.
13. Deprecation requires owner confirmation, code/job searches, observation windows, and rollback plans.
14. Catalog audits should be snapshotted and diffed periodically without auto-dropping objects.
15. Safe cleanup relies on corroborating evidence and controlled changes.

Catalogs tell you what objects PostgreSQL manages and how they link structurally. Statistics and logs show part of observed runtime activity. Combining these sources with application code, job inventories, and owner confirmation lets administrators identify candidate objects rigorously, reduce schema drift, and clean up databases while safeguarding critical dependencies.

## 34. Official PostgreSQL Documentation

- [System Catalogs](https://www.postgresql.org/docs/current/catalogs.html)
- [The Information Schema](https://www.postgresql.org/docs/current/information-schema.html)
- [pg_class](https://www.postgresql.org/docs/current/catalog-pg-class.html)
- [pg_namespace](https://www.postgresql.org/docs/current/catalog-pg-namespace.html)
- [pg_attribute](https://www.postgresql.org/docs/current/catalog-pg-attribute.html)
- [pg_depend](https://www.postgresql.org/docs/current/catalog-pg-depend.html)
- [pg_shdepend](https://www.postgresql.org/docs/current/catalog-pg-shdepend.html)
- [pg_constraint](https://www.postgresql.org/docs/current/catalog-pg-constraint.html)
- [pg_index](https://www.postgresql.org/docs/current/catalog-pg-index.html)
- [pg_proc](https://www.postgresql.org/docs/current/catalog-pg-proc.html)
- [pg_extension](https://www.postgresql.org/docs/current/catalog-pg-extension.html)
- [Monitoring Database Activity](https://www.postgresql.org/docs/current/monitoring-stats.html)
- [Statistics Views](https://www.postgresql.org/docs/current/monitoring-stats.html#MONITORING-STATS-VIEWS)
- [Object Information Functions](https://www.postgresql.org/docs/current/functions-info.html)
- [Dependency Tracking](https://www.postgresql.org/docs/current/ddl-depend.html)
- [DROP TABLE](https://www.postgresql.org/docs/current/sql-droptable.html)
- [DROP OWNED](https://www.postgresql.org/docs/current/sql-drop-owned.html)
- [REASSIGN OWNED](https://www.postgresql.org/docs/current/sql-reassign-owned.html)
- [Privileges](https://www.postgresql.org/docs/current/ddl-priv.html)
- [Extensions](https://www.postgresql.org/docs/current/extend-extensions.html)

Links using `current` point to the latest PostgreSQL documentation. Catalog columns, dependency codes, statistics fields, partition metadata, and predefined roles can change across major versions. Before running automated audits, verify `SHOW server_version`, catalog definitions, and audit role privileges in your exact environment.
