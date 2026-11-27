# Renaming, Dropping Columns, and Managing View or Function Dependencies in PostgreSQL

## 1. Why Must Renaming or Dropping Columns Be Managed Carefully?

In PostgreSQL, a column can be used by many components outside the table containing it: views, materialized views, functions, triggers, indexes, constraints, generated columns, policies, application queries, reports, and ETL jobs. A seemingly simple change like renaming or dropping a column can break these components if the rollout is not coordinated.

Two commonly used commands are:

~~~sql
ALTER TABLE app.customers
RENAME COLUMN full_name TO display_name;

ALTER TABLE app.customers
DROP COLUMN legacy_code;
~~~

Renaming a column changes the name clients use to reference it. Dropping a column removes access to that column from the table definition and can invalidate or remove dependent objects. PostgreSQL tracks dependencies in system catalogs, yet not every reference inside application source code, dynamic SQL, or string-bodied functions is fully tracked.

Therefore, a safe workflow must clarify:
- Where is the column currently used?
- Does PostgreSQL track that object's dependency?
- Will views keep working after the base column is renamed?
- Are function bodies parsed and recorded as dependencies at creation time?
- Does DROP COLUMN RESTRICT detect every consumer?
- Which additional objects will CASCADE drop?
- Can old and new applications coexist during deployment?
- Can we roll back before and after data migration occurs?

### 1.1. Learning Objectives

After this lesson, you will be able to:

1. Use ALTER TABLE ... RENAME COLUMN and DROP COLUMN.
2. Distinguish RESTRICT and CASCADE.
3. Understand how PostgreSQL tracks dependencies via pg_depend.
4. Inspect views, materialized views, rules, and objects depending on a column.
5. Distinguish SQL-standard function bodies from string-bodied functions and dynamic SQL.
6. Handle dependencies in PL/pgSQL, triggers, and application code.
7. Plan expand-and-contract rollouts for renaming or dropping columns.
8. Understand locks, transactions, table rewrites, and disk-space impacts.
9. Test migrations and control rollbacks.
10. Write runbooks to deploy schema changes safely.

### 1.2. Core Principles

- Renaming a column changes the schema contract; any consumer sending the old column name can fail.
- Views usually store dependencies by object/column identity, not simply as SQL text to find-and-replace.
- A view's output column name is a separate contract; renaming a base column does not automatically rename the view's output column.
- String-bodied functions and dynamic SQL can contain references not recorded by PostgreSQL as dependencies.
- DROP COLUMN defaults to RESTRICT; CASCADE can drop a chain of dependent objects.
- DROP COLUMN RESTRICT succeeding does not prove no references remain in application code.
- DDL requires locks; even fast metadata operations can wait on locks and build queues.
- Changes should roll out with a compatibility period when multiple application versions run concurrently.
- Always check pg_depend, source code, application telemetry, and tests before dropping a column.

---

## 2. Renaming Columns With ALTER TABLE

### 2.1. Basic Syntax

~~~sql
ALTER TABLE schema_name.table_name
RENAME COLUMN old_column_name TO new_column_name;
~~~

Example:

~~~sql
ALTER TABLE app.customers
RENAME COLUMN full_name TO display_name;
~~~

After this command, the table no longer has a column named full_name; the column is now named display_name. Existing data remains in the same column. PostgreSQL does not need to copy all rows just to rename it.

### 2.2. Renaming Is Not Adding a New Column

Renaming is a metadata change on an existing column:
- Values in rows are not moved to another column.
- Internal column identity (attribute number/attnum) is preserved.
- Indexes and constraints depending on the column normally remain attached to the same column.
- SQL referencing the old column name on the table after the rename will fail to resolve.
- Consumers querying through a view can keep working because view dependencies point to column identity.

That last point is crucial: PostgreSQL may keep a view working after a rename, while application queries hitting the table directly with the old name will break.

### 2.3. Renaming Tables vs. Renaming Columns

Table names and column names are two independent changes:

~~~sql
ALTER TABLE app.customer
RENAME TO customers;

ALTER TABLE app.customers
RENAME COLUMN name TO display_name;
~~~

Each command can affect different consumers. Renaming a table also does not automatically update SQL strings inside functions or application source code.

### 2.4. Renaming Columns in Other Schemas

Table names should be schema-qualified to avoid modifying the wrong object when search_path spans multiple schemas:

~~~sql
ALTER TABLE accounting.invoices
RENAME COLUMN invoice_date TO issued_at;
~~~

Before migrating, confirm the exact relation via catalogs or `\d+ accounting.invoices` in psql.

### 2.5. Renaming in Partitioned Tables

With partitioned tables, columns are part of the parent table's schema. Schema changes on the parent must be evaluated alongside the partition hierarchy and child partitions. PostgreSQL propagates many schema changes across partitions per command semantics and version; inspect all partitions and indexes post-migration, especially when foreign tables or independently managed partitions exist.

Do not run independent rename commands on individual child partitions when the partitioned parent is the relation used by applications. Verify DDL behavior on your running major version.

### 2.6. Renaming Does Not Change Default Values

Renaming a column does not alter its default expression or identity property. However, functions or application code referencing the column by name may need updates.

Check:

~~~sql
SELECT
    a.attname,
    pg_get_expr(d.adbin, d.adrelid) AS column_default,
    a.attidentity,
    a.attgenerated
FROM pg_attribute AS a
LEFT JOIN pg_attrdef AS d
    ON d.adrelid = a.attrelid
   AND d.adnum = a.attnum
WHERE a.attrelid = 'app.orders'::regclass
  AND a.attnum > 0
  AND NOT a.attisdropped
ORDER BY a.attnum;
~~~

### 2.7. Renaming a Column Referenced by a View

Example creating a table and view:

~~~sql
CREATE TABLE app.accounts (
    account_id bigint PRIMARY KEY,
    account_name text NOT NULL
);

CREATE VIEW app.account_directory AS
SELECT account_id, account_name
FROM app.accounts;
~~~

Then rename the base column:

~~~sql
ALTER TABLE app.accounts
RENAME COLUMN account_name TO display_name;
~~~

The view typically keeps working because PostgreSQL stores dependencies against column identity. The view's output column may keep the name account_name, because a view's column names form their own schema contract.

~~~sql
SELECT * FROM app.account_directory;
~~~

Applications reading app.account_directory.account_name can keep running while applications reading accounts.account_name directly will fail. If you also want to rename the view's output column, migrate the view separately:

~~~sql
ALTER VIEW app.account_directory
RENAME COLUMN account_name TO display_name;
~~~

This is a separate contract change and can affect consumers of the view.

### 2.8. Renaming and Application Code

PostgreSQL cannot automatically fix:
- SQL queries in source code.
- ORM model/property mappings.
- Prepared statements held in connection pools.
- BI/report definitions.
- ETL scripts.
- Stored function bodies lacking dependency tracking.
- Dynamic SQL strings.
- External services consuming the database schema.

Search all repositories and query/report catalogs before renaming.

---

## 3. Dropping Columns With ALTER TABLE DROP COLUMN

### 3.1. Syntax

~~~sql
ALTER TABLE schema_name.table_name
DROP COLUMN column_name;
~~~

Example:

~~~sql
ALTER TABLE app.customers
DROP COLUMN legacy_code;
~~~

By default, PostgreSQL uses RESTRICT behavior: it refuses to drop the column if recorded object dependencies exist that must be preserved.

You can specify it explicitly:

~~~sql
ALTER TABLE app.customers
DROP COLUMN legacy_code RESTRICT;
~~~

### 3.2. DROP COLUMN Is Not the Same as DELETE

DELETE FROM table removes rows matching a condition. DROP COLUMN removes an attribute from the schema:
- It does not delete whole rows.
- It does not delete other rows.
- The column is no longer accessible via SQL.
- Dependent objects are checked according to dependency rules.
- It does not necessarily shrink the table file immediately.

### 3.3. RESTRICT Is the Safe Default

If PostgreSQL knows a view, constraint, index, or other object depends on the column, DROP COLUMN may be rejected while naming the dependency. That is a signal to inspect and plan consumer updates.

Example:

~~~sql
ALTER TABLE app.accounts
DROP COLUMN account_name RESTRICT;
~~~

If a view references the column, the command may report the dependency and require CASCADE or dropping the dependency first. In production migrations, a RESTRICT error is valuable information; never react by blindly adding CASCADE.

### 3.4. CASCADE Can Drop Dependent Objects

~~~sql
ALTER TABLE app.accounts
DROP COLUMN account_name CASCADE;
~~~

CASCADE instructs PostgreSQL to drop objects depending on the column—such as views, rules, or related constraints—and can recursively drop objects depending on those objects.

A single command can remove:
- Views.
- Other views depending on the first view.
- Materialized views and rule dependencies.
- Related constraints or indexes.
- Other objects found in the catalog dependency graph.

Exact scope depends on the database's dependency graph. Never use CASCADE as a "quick fix"; inventory every object that would be dropped and plan recreations explicitly.

### 3.5. Does DROP COLUMN Reclaim Disk Immediately?

PostgreSQL usually marks the column dropped in the catalog; physical column data is not stripped from every existing tuple at DDL time. Space is not necessarily returned to the filesystem immediately.

A table rewrite such as VACUUM FULL, CLUSTER, or an appropriate rewrite tool can remove old storage, at its own disk, lock, and downtime cost. Never run a rewrite solely to "finish" DROP COLUMN without assessing impact.

### 3.6. Dropping Multiple Columns

~~~sql
ALTER TABLE app.customers
    DROP COLUMN old_code,
    DROP COLUMN obsolete_flag;
~~~

Grouping drops can reduce lock acquisitions, but only do so once dependencies and rollback plans are verified for every column. A dependency on one column will fail the entire statement.

### 3.7. Dropping Columns in Partitioned Tables

Dropping a column from a partitioned parent must be compatible with child partitions and dependent objects. Check constraints/indexes on parent and children, any foreign tables, and all consumers. Never assume externally managed partitions update automatically.

### 3.8. Never Use DROP COLUMN to Rename

Do not create a new column, drop the old column, and hope data moves automatically. To rename, use RENAME COLUMN. If you need to change types/semantics or migrate data, use expand-and-contract with backfilling and validation.

---

## 4. Dependency Tracking in PostgreSQL

### 4.1. What Is Object Dependency?

PostgreSQL records many dependency relationships between database objects in system catalogs. Dependencies let the server:
- Prevent dropping an object still referenced elsewhere.
- Drop dependent objects when CASCADE is used.
- Manage drop/recreate ordering.
- Track references across relations, columns, views, rules, constraints, types, functions, and other objects.

Dependency tracking forms a graph: an object can depend on many objects, and one object can be referenced by many others.

### 4.2. pg_depend

pg_depend is the primary catalog storing dependency records. Key columns include:
- classid: catalog containing the dependent object.
- objid: OID of the dependent object.
- objsubid: sub-object number, usually column number for relations.
- refclassid: catalog containing the referenced object.
- refobjid: OID of the referenced object.
- refobjsubid: sub-object number referenced, usually column attnum.
- deptype: dependency type.

Do not hard-code OIDs since OIDs differ across databases and restores. Use regclass and catalog joins when querying.

### 4.3. Dependencies by Column Identity

A column has an attnum in pg_attribute. View queries, index expressions, constraints, and several object definitions reference the column via this internal identity. That is why renaming a column differs from SQL string find-and-replace: dependencies continue pointing to the same column after the name changes.

Retrieve attnum:

~~~sql
SELECT
    attrelid::regclass AS table_name,
    attname,
    attnum,
    attisdropped
FROM pg_attribute
WHERE attrelid = 'app.accounts'::regclass
  AND attname = 'account_name'
  AND attnum > 0;
~~~

### 4.4. Querying Direct Dependencies of a Column

Example querying dependency records referencing a column:

~~~sql
SELECT
    d.deptype,
    d.classid::regclass AS dependent_catalog,
    d.objid,
    d.objsubid,
    pg_describe_object(
        d.classid,
        d.objid,
        d.objsubid
    ) AS dependent_object
FROM pg_depend AS d
WHERE d.refclassid = 'pg_class'::regclass
  AND d.refobjid = 'app.accounts'::regclass
  AND d.refobjsubid = (
      SELECT a.attnum
      FROM pg_attribute AS a
      WHERE a.attrelid = 'app.accounts'::regclass
        AND a.attname = 'account_name'
        AND a.attnum > 0
        AND NOT a.attisdropped
  )
ORDER BY dependent_catalog::text, dependent_object;
~~~

This is a catalog-based inventory, not an exhaustive list of all possible consumers in application source code. Verify results on your major version and check catalog permissions.

### 4.5. Dependency Types

deptype describes how PostgreSQL treats the dependency. Common types include:
- Normal dependency: referenced object cannot be dropped while the dependent object exists under RESTRICT.
- Auto dependency: dependent object can be dropped automatically when its parent object is dropped.
- Internal dependency: object is managed internally as part of another object.
- Extension dependency: object belongs to an extension's lifecycle.
- Pin dependency: specially protected system object.

Do not interpret every deptype identically. Use pg_describe_object and catalog documentation to understand each specific object.

### 4.6. pg_describe_object

pg_describe_object(classid, objid, objsubid) generates a human-readable description for an object in a dependency record. It is helpful when classid points to pg_rewrite, pg_constraint, pg_class, pg_proc, or another catalog.

### 4.7. The Dependency Graph Is Not a Static Code Analyzer

Catalogs only know dependencies recorded by PostgreSQL. They cannot automatically locate:
- SQL strings inside application repositories.
- Dynamic SQL built via concatenation.
- Query text in external BI tools.
- Stored function bodies lacking dependency metadata.
- Jobs running in separate services.
- Client queries using old column names.

Combine catalog inventories, source searches, telemetry, and tests.

---

## 5. Views, Materialized Views, and Rules

### 5.1. Views Store Parsed Queries

A view in PostgreSQL is not merely a raw SQL string re-parsed every execution. PostgreSQL stores a parsed query tree/rule and dependencies on referenced objects, including relations and columns.

For example:

~~~sql
CREATE VIEW app.customer_summary AS
SELECT customer_id, display_name
FROM app.customers;
~~~

The view holds dependencies on the base table's columns. When a base column is renamed, PostgreSQL can keep the view valid because the dependency tracks column identity.

### 5.2. Renaming a Base Column Does Not Rename the View's Output Column

For example:

~~~sql
CREATE TABLE app.people (
    person_id bigint PRIMARY KEY,
    full_name text NOT NULL
);

CREATE VIEW app.people_public AS
SELECT person_id, full_name
FROM app.people;

ALTER TABLE app.people
RENAME COLUMN full_name TO display_name;
~~~

The view continues returning an output column named full_name while the base table has display_name:

~~~sql
SELECT full_name
FROM app.people_public;
~~~

If you want to change the view's contract, rename its output column separately:

~~~sql
ALTER VIEW app.people_public
RENAME COLUMN full_name TO display_name;
~~~

View consumers will also need corresponding migrations.

### 5.3. Nested Views

One view can be queried by another view:

~~~sql
CREATE VIEW app.people_names AS
SELECT person_id, full_name
FROM app.people_public;

CREATE VIEW app.people_report AS
SELECT person_id, upper(full_name) AS normalized_name
FROM app.people_names;
~~~

The dependency chain looks like:

~~~text
app.people
   |
   v
app.people_public
   |
   v
app.people_names
   |
   v
app.people_report
~~~

When modifying a base column, the view tree can continue operating if query trees still reference the right column identity. With DROP COLUMN CASCADE, PostgreSQL can drop the entire chain of dependent views and rules. Inventory all levels before ever using CASCADE.

### 5.4. Finding Views Directly Depending on a Column

You can query pg_depend and pg_rewrite:

~~~sql
WITH target_column AS (
    SELECT attnum
    FROM pg_attribute
    WHERE attrelid = 'app.people'::regclass
      AND attname = 'display_name'
      AND attnum > 0
      AND NOT attisdropped
)
SELECT DISTINCT
    v.oid::regclass AS dependent_view,
    v.relkind,
    r.rulename,
    pg_describe_object(
        d.classid,
        d.objid,
        d.objsubid
    ) AS dependency
FROM pg_depend AS d
JOIN pg_rewrite AS r
    ON d.classid = 'pg_rewrite'::regclass
   AND d.objid = r.oid
JOIN pg_class AS v
    ON v.oid = r.ev_class
WHERE d.refclassid = 'pg_class'::regclass
  AND d.refobjid = 'app.people'::regclass
  AND d.refobjsubid = (SELECT attnum FROM target_column)
ORDER BY dependent_view::text;
~~~

relkind distinguishes ordinary views from materialized views across matching catalog versions. This query locates direct rule dependencies; nested view chains may require recursive queries or further inspection.

### 5.5. CREATE OR REPLACE VIEW Has Restrictions

CREATE OR REPLACE VIEW works when updating a query while preserving existing output columns in order, name, and data type. PostgreSQL permits appending new output columns at the end in supported cases; do not use it to silently rename, remove, or reorder existing output columns.

Example updating the query while preserving the contract:

~~~sql
CREATE OR REPLACE VIEW app.people_public AS
SELECT
    person_id,
    display_name AS full_name
FROM app.people;
~~~

The alias full_name preserves compatibility for legacy consumers during transition.

### 5.6. Materialized Views

A materialized view stores query results physically and holds dependencies on source objects. When a base column is renamed, the stored query definition typically continues referencing the right column identity. However:
- The materialized view's output schema remains a separate contract.
- Data does not refresh automatically just because base data changes.
- REFRESH MATERIALIZED VIEW must be scheduled after migration as needed.
- Dropping/recreating a materialized view may require rebuilding indexes and incur downtime/resource costs.
- CASCADE can drop a materialized view if dependencies are recorded.

Inspect via pg_matviews, pg_class, and dependency catalogs.

### 5.7. Rules and the Rewrite System

Ordinary views are implemented via rewrite rules, typically a `_RETURN` rule. Consequently, view dependencies appear in pg_depend with dependent objects belonging to pg_rewrite. Never manually drop a rule to "clear a dependency" without understanding view semantics.

### 5.8. View Column Compatibility Strategy

When renaming a base column:
1. Keep the view's old output name via an alias.
2. Deploy applications switching to the new view contract if needed.
3. Create a new versioned view if you want to change the output schema cleanly.
4. Migrate consumers.
5. Drop the old view once zero consumers remain.

For views shared across teams, a versioned view is usually much easier to coordinate than an abrupt output column rename.

---

## 6. Function Dependencies: SQL, PL/pgSQL, and Dynamic SQL

### 6.1. Why Must Functions Be Inspected Separately?

Functions can reference tables and columns inside their bodies. Yet PostgreSQL cannot track every kind of reference across every procedural language. How a function body is written determines whether dependencies inside it are parsed and recorded at creation time or only resolved at execution time.

Consequently:
- A view can block DROP COLUMN because its dependency is recorded.
- A string-bodied function might not block DROP COLUMN even while still containing the old column name.
- That function may fail only when invoked after the migration.

### 6.2. SQL Functions Using String Literal Bodies

For example:

~~~sql
CREATE FUNCTION app.get_person_name(p_id bigint)
RETURNS text
LANGUAGE sql
AS $$
    SELECT full_name
    FROM app.people
    WHERE person_id = p_id
$$;
~~~

With traditional string-literal bodies, the parser does not build full dependency records for body references the way SQL-standard bodies do. Therefore, never rely on DROP COLUMN RESTRICT to prove no functions use the column.

After renaming full_name, the function body still holds the old identifier. When re-parsed or executed later, the function can fail because the column no longer exists.

### 6.3. SQL-Standard Function Bodies

PostgreSQL versions supporting SQL-standard body syntax allow bodies to be parsed when the function is created:

~~~sql
CREATE FUNCTION app.person_name(p_id bigint)
RETURNS text
LANGUAGE SQL
BEGIN ATOMIC
    SELECT display_name
    FROM app.people
    WHERE person_id = p_id;
END;
~~~

With a SQL-standard body parsed at definition time, PostgreSQL can record dependencies on referenced objects. This syntax was introduced in PostgreSQL 14; confirm your target version before using it.

This is one key advantage of SQL-standard bodies for dependency tracking. Still, test function behavior and do not treat the dependency catalog as a static analyzer for the entire application.

### 6.4. PL/pgSQL Functions

For example:

~~~sql
CREATE FUNCTION app.lookup_person(p_id bigint)
RETURNS text
LANGUAGE plpgsql
AS $$
DECLARE
    result_name text;
BEGIN
    SELECT full_name
    INTO result_name
    FROM app.people
    WHERE person_id = p_id;

    RETURN result_name;
END;
$$;
~~~

PL/pgSQL bodies are stored as source text, and SQL statements inside them are parsed and prepared when the function executes. Table/column references inside the body are generally not recorded as dependency records like views or SQL-standard function bodies.

After a rename or drop, the function may fail only when that specific code branch runs or when the statement recompiles. You must search and test every PL/pgSQL function referencing the column.

### 6.5. Dynamic SQL

For example:

~~~sql
EXECUTE
    'SELECT full_name FROM app.people WHERE person_id = '
    || p_id;
~~~

Dynamic SQL is constructed at runtime; catalog dependency tracking cannot reliably know the final relation or column names. Renames or drops will not catch this function. Use parameter binding with USING to prevent SQL injection and clarify code:

~~~sql
EXECUTE
    'SELECT display_name
     FROM app.people
     WHERE person_id = $1'
INTO result_name
USING p_id;
~~~

Parameter binding protects values, while dynamic identifiers must still be managed explicitly. Dynamic table/column names must be allowlisted and properly quoted via `format('%I', identifier)`.

### 6.6. Function Bodies Querying Through a View

A function may query a view rather than the base table:

~~~sql
CREATE FUNCTION app.get_public_name(p_id bigint)
RETURNS text
LANGUAGE sql
AS $$
    SELECT full_name
    FROM app.people_public
    WHERE person_id = p_id
$$;
~~~

If the view retains output column full_name, the function can keep working even if the base table column is renamed. This establishes a compatibility boundary, though string-bodied functions must still be tested and application contracts maintained.

### 6.7. Searching Function Bodies for a Column Name

You can search text in pg_proc.prosrc:

~~~sql
SELECT
    n.nspname AS schema_name,
    p.proname AS function_name,
    pg_get_function_identity_arguments(p.oid) AS arguments,
    l.lanname AS language,
    p.prosrc
FROM pg_proc AS p
JOIN pg_namespace AS n
    ON n.oid = p.pronamespace
JOIN pg_language AS l
    ON l.oid = p.prolang
WHERE n.nspname NOT IN ('pg_catalog', 'information_schema')
  AND p.prosrc ILIKE '%full_name%'
ORDER BY n.nspname, p.proname;
~~~

This is strictly a text search:
- It can produce false positives in comments or unrelated string literals.
- It can miss dynamically built names, quoted/case-sensitive identifiers, or SQL fragments stored in config tables.
- Function bodies may be written in other procedural languages.
- Overloaded functions must be distinguished by identity arguments.

Use pg_get_functiondef(oid) to inspect full definitions and review every candidate.

### 6.8. Finding Catalog-Recorded Function Dependencies

Direct column dependency queries may surface pg_proc objects or indirect dependencies through views. Query pg_depend with pg_describe_object to inspect actual records. However, zero results do not prove no functions use the column; string bodies and dynamic SQL remain major blind spots.

### 6.9. Trigger Functions

Triggers attach to tables and invoke trigger functions. The trigger definition holds dependencies on the function and relation, yet the trigger function's source body can still contain untracked column references. Inspect all of:
- Trigger definitions in pg_trigger.
- Function definitions in pg_proc.
- `UPDATE OF column` trigger declarations.
- `OLD.column` / `NEW.column` references in PL/pgSQL.
- Dynamic SQL inside trigger functions.
- Application side effects invoked by triggers.

### 6.10. Function Overloads and API Contracts

Functions with the same name can have multiple signatures. When changing parameters, return types, or function names:
- Use pg_get_function_identity_arguments.
- Check callers per signature.
- Create new overloads or versioned functions when compatibility is needed.
- Never DROP FUNCTION by name alone when overloads exist.
- Verify grants, ownership, and SECURITY DEFINER settings.
- Test all callers and permissions.

---

## 7. Other Objects That Can Depend on a Column

### 7.1. Indexes

Index expressions or index keys can depend on a column. When dropping a column, related indexes on the same table are usually handled automatically by PostgreSQL as part of ALTER TABLE. Before migrating, still inventory them to know which indexes will disappear and which queries rely on them.

~~~sql
SELECT
    schemaname,
    tablename,
    indexname,
    indexdef
FROM pg_indexes
WHERE schemaname = 'app'
  AND tablename = 'people'
ORDER BY indexname;
~~~

For expression indexes, inspect the expression in indexdef for column references.

### 7.2. Constraints

Constraints that can reference a column:
- PRIMARY KEY.
- UNIQUE.
- FOREIGN KEY.
- CHECK.
- NOT NULL (column metadata).
- Exclusion constraints.

Table-local indexes and constraints may be automatically dropped or impacted when dropping a column. Foreign keys on other tables referencing a unique/primary key column must be treated as related dependencies. Never assume inspecting only the source table's constraints is enough.

~~~sql
SELECT
    conrelid::regclass AS table_name,
    conname,
    contype,
    pg_get_constraintdef(oid) AS definition,
    convalidated
FROM pg_constraint
WHERE connamespace = 'app'::regnamespace
ORDER BY conrelid::regclass::text, conname;
~~~

### 7.3. Generated Columns and Default Expressions

A generated column or default expression can reference another column. PostgreSQL tracks many expression dependencies in catalogs and can block changes that invalidate those expressions.

Inspect generated/default expressions:

~~~sql
SELECT
    a.attname,
    a.attgenerated,
    pg_get_expr(d.adbin, d.adrelid) AS expression
FROM pg_attribute AS a
LEFT JOIN pg_attrdef AS d
    ON d.adrelid = a.attrelid
   AND d.adnum = a.attnum
WHERE a.attrelid = 'app.people'::regclass
  AND a.attnum > 0
  AND NOT a.attisdropped
ORDER BY a.attnum;
~~~

### 7.4. Triggers

Triggers can:
- Be declared to fire on `UPDATE OF` a column.
- Read `OLD.column` or `NEW.column`.
- Write column values into audit/history tables.
- Call functions containing SQL referencing the column.
- Emit events to external systems.

Inventory triggers:

~~~sql
SELECT
    t.tgname,
    t.tgenabled,
    pg_get_triggerdef(t.oid, true) AS trigger_definition,
    t.tgfoid::regprocedure AS trigger_function
FROM pg_trigger AS t
WHERE t.tgrelid = 'app.people'::regclass
  AND NOT t.tgisinternal
ORDER BY t.tgname;
~~~

Update trigger definitions and trigger functions in a coordinated deployment. Trigger events may stop firing or functions may error accessing OLD/NEW fields if a column is renamed or dropped.

### 7.5. Row-Level Security Policies

Policy expressions can reference columns to govern row visibility or write permissions. Inspect:

~~~sql
SELECT
    schemaname,
    tablename,
    policyname,
    permissive,
    roles,
    cmd,
    qual,
    with_check
FROM pg_policies
WHERE schemaname = 'app'
  AND tablename = 'people'
ORDER BY policyname;
~~~

A migration altering a policy can widen or narrow the rows an application role sees. Test using the actual application role with row-level security active.

### 7.6. Foreign Keys in Other Tables

If a column is referenced by a foreign key from another table, DROP COLUMN can be blocked by the dependent constraint. Identify both referencing and referenced relations:

~~~sql
SELECT
    conrelid::regclass AS referencing_table,
    conname,
    confrelid::regclass AS referenced_table,
    pg_get_constraintdef(oid) AS definition
FROM pg_constraint
WHERE contype = 'f'
  AND (
      conrelid = 'app.people'::regclass
      OR confrelid = 'app.people'::regclass
  )
ORDER BY referencing_table::text, conname;
~~~

When dropping a referenced key, handle child foreign keys according to business rules rather than blindly dropping constraints just to push DDL through.

### 7.7. Partition Keys and Indexes

If the column is a partition key, primary/unique key component, or critical index key, dropping it may be disallowed or require altering partition/index structures first. Check partition key definitions, constraints, indexes, and application routing logic before migrating.

### 7.8. Views, Functions, and External Consumers

Catalog queries are only part of the inventory. Include:
- Stored procedures and functions.
- Event triggers.
- Materialized views.
- BI and reporting tools.
- ETL/ELT jobs.
- Application repositories.
- ORM mappings.
- Prepared statements.
- Scheduled SQL.
- Data export contracts.
- External services and scripts.

### 7.9. Dependency Inventory Table

Build a migration tracking table:

| Consumer | Type | Dependency tracked? | Owner | Plan |
|---|---|---|---|---|
| customer_summary | View | Yes | Data team | Keep alias, migrate later |
| person_lookup | PL/pgSQL | Body refs usually untracked | Backend team | Update and test |
| people_audit | Trigger | Trigger tracked, body needs review | DBA | Update function |
| BI customer report | External | No | Analytics | Update report |
| ORM Customer.fullName | Application | No | App team | Deploy compatibility release |

Track status and owner for every consumer. Never drop the column while any consumer remains unaddressed.

---

## 8. Handling Views and Functions When Renaming Columns

### 8.1. Choose a Compatibility Boundary

Applications can access tables directly or through views/functions. When a database is shared across services, a view/function API decouples physical schema from consumer contracts.

Example keeping the old output column in a view:

~~~sql
CREATE OR REPLACE VIEW app.people_api AS
SELECT
    person_id,
    display_name AS full_name
FROM app.people;
~~~

Old applications continue reading full_name from the view while the underlying table schema already uses display_name.

### 8.2. Migrating a View's Output Column

If consumers should move to the new name:
1. Create a new versioned view with the new output name.
2. Deploy consumers reading the new view.
3. Monitor usage of the old view.
4. Wait until all consumers have migrated.
5. Drop the old view once the dependency graph and telemetry allow.

For example:

~~~sql
CREATE VIEW app.people_api_v2 AS
SELECT
    person_id,
    display_name
FROM app.people;
~~~

Never alter a shared view contract without notifying consuming teams.

### 8.3. Updating SQL Function Bodies

For SQL-standard function bodies with dependency tracking, modifying a base column may block the migration or require recreating/updating the function per dependency rules. Use CREATE OR REPLACE FUNCTION when the signature and return contract allow.

For string bodies or PL/pgSQL:
- Search function definitions.
- Update column names.
- Check all branches and dynamic SQL.
- Deploy the updated function before applications invoke the new path.
- Run tests under the application role.
- Verify function ownership, grants, and SECURITY DEFINER behavior.

### 8.4. Function Wrappers for Compatibility

You can keep the function API stable while updating its implementation:

~~~sql
CREATE OR REPLACE FUNCTION app.person_display_name(p_id bigint)
RETURNS text
LANGUAGE sql
AS $$
    SELECT display_name
    FROM app.people
    WHERE person_id = p_id
$$;
~~~

Callers do not need to know the physical column name. However, changing the return type, volatility, security attributes, or function signature can still break the API.

### 8.5. PL/pgSQL OLD and NEW

Trigger functions use OLD/NEW records. After dropping or renaming a field, code like OLD.full_name or NEW.full_name can error when the trigger fires. The trigger definition may remain intact because its source body is not rewritten automatically.

Test all DML paths that actually fire the trigger:
- INSERT.
- Single-column UPDATEs.
- Multi-column UPDATEs.
- DELETE.
- Bulk loads/imports if triggers are enabled.
- ON CONFLICT DO UPDATE.

### 8.6. Dynamic SQL and Identifiers

When identifiers are built from text:
- Locate every place constructing SQL statements.
- Use allowlists for schema, table, and column names.
- Use `format('%I', identifier)` to quote identifiers.
- Use `USING` for parameter values.
- Never apply blind global find-and-replace without understanding quoting and case sensitivity.
- Test every dynamic query branch.

### 8.7. Materialized View Refresh/Rebuild

If a migration changes a materialized view's query or output schema, you may need to drop/recreate it or build a new version. Evaluate:
- Dependency chains.
- Refresh duration.
- Unique index required for REFRESH CONCURRENTLY.
- Disk space for materialized data and indexes.
- Locks and application read availability.
- Output column consumers.

---

## 9. Renaming and Dropping Columns With Expand-and-Contract

### 9.1. Why Are Multiple Phases Necessary?

During a rolling deployment, application instances do not update simultaneously. At the same time you may have:
- Old instances reading/writing the old column.
- New instances reading/writing the new column.
- Background workers not yet restarted.
- Scheduled BI/ETL jobs.
- Pooled connections holding old plans or session state.

If you rename or drop immediately, some consumer group can fail mid-rollout. Expand-and-contract keeps the schema compatible across the transition.

### 9.2. Adding a New Column Pattern

Suppose we want to rename full_name to display_name. A low-downtime approach adds a new column:

~~~sql
ALTER TABLE app.people
ADD COLUMN display_name text;
~~~

Then:
1. Deploy an application supporting both full_name and display_name.
2. Dual-write both columns or synchronize via trigger during transition.
3. Backfill historical data to the new column in batches.
4. Verify parity.
5. Switch readers to display_name.
6. Stop writes to full_name.
7. Confirm zero consumers still use full_name.
8. Drop full_name in a separate migration.

This is both a data and schema migration, not a direct rename command.

### 9.3. Dual-Write and Triggers

Application dual-write ensures both columns receive the same value, though you must avoid scenarios where an old client updates only the old column while a new client updates only the new column.

A sync trigger can serve as a compatibility layer during rollout, provided an authoritative source is defined and conflicting updates to both columns are handled. Avoid trigger loops or overwriting newer data with stale values.

### 9.4. Batched Backfills

Example bounded backfill:

~~~sql
UPDATE app.people
SET display_name = full_name
WHERE display_name IS NULL
  AND person_id > 0
  AND person_id <= 10000;
~~~

Repeat across key ranges or a primary-key cursor. After each batch:
- Commit.
- Record progress.
- Monitor WAL and replication lag.
- Check locks and latency.
- Retry safely.
- Avoid one giant transaction.

The WHERE clause must fit real data semantics; the example above is illustrative.

### 9.5. Verifying Parity

~~~sql
SELECT count(*) AS mismatched_rows
FROM app.people
WHERE display_name IS DISTINCT FROM full_name;
~~~

If normalization, casing, or trimming rules apply, compare using the business transformation rather than raw strings. Verify null semantics and any rows inserted/updated during backfilling.

### 9.6. Switch Readers Before Dropping

Deploy applications reading display_name while dual-write remains active. Wait until:
- All new instances are running.
- Background workers are updated.
- Old connection pools are drained.
- Scheduled jobs, reports, and ETL are updated.
- Telemetry shows zero queries touching full_name.
- The application rollback window has passed.

Only then stop dual-writing and drop the old column.

### 9.7. Using a View as a Compatibility Layer

If consumers access data through a view, you can update the view implementation to keep the old output contract. For instance, the view continues exposing full_name backed by the new display_name. This reduces how many clients must deploy simultaneously, though it does not protect clients querying the base table directly.

### 9.8. Contract Phase

Contraction removes the old column and temporary compatibility objects:
1. Confirm zero usage of old consumers over an adequate observation window.
2. Check dependency catalogs.
3. Check function bodies and source code.
4. Drop or replace dependent views/functions per plan.
5. Test DROP COLUMN RESTRICT in staging.
6. Set lock_timeout and run DDL in an appropriate maintenance window.
7. Verify schema after commit.
8. Monitor errors and query failures.

### 9.9. Rollback Before Contraction

Before dropping the old column, rolling back usually means switching readers back to the old column while keeping dual-write active. After dropping the old column, rollback requires restoring the column/data or running a forward migration; reverting application code alone cannot recover removed data.

### 9.10. Small Changes With Permitted Downtime

If all readers and writers can be stopped:
- Freeze application traffic.
- Drain transactions and connection pools.
- Update views, functions, and application SQL.
- Rename or drop the column.
- Validate.
- Deploy/start the application.
- Reopen traffic.

This can be a clean option for small databases or clear maintenance windows, provided lock acquisition and validation times are accounted for.

---

## 10. Locking, Transactions, and Operational Impact

### 10.1. Rename/Drop Requires a Table Lock

ALTER TABLE forms like RENAME COLUMN and DROP COLUMN require a strong lock on the relation, typically ACCESS EXCLUSIVE. This lock conflicts even with queries merely reading the table.

Even though DDL may only touch catalogs and finish fast once the lock is granted, it still must wait for transactions holding conflicting locks. Consequently, a "fast" command can stall in production.

### 10.2. Locks Are Held Until the End of the Transaction

When DDL runs inside a transaction block, the relation lock is typically held until COMMIT or ROLLBACK. Never place DDL inside a long transaction doing unrelated work.

For example:

~~~sql
BEGIN;
SET LOCAL lock_timeout = '3s';
SET LOCAL statement_timeout = '30s';

ALTER TABLE app.people
RENAME COLUMN full_name TO display_name;

COMMIT;
~~~

If the lock is not acquired within 3 seconds, the statement fails instead of waiting indefinitely. Choose timeouts matching maintenance policy and real workload.

### 10.3. lock_timeout and statement_timeout

- lock_timeout limits wait time per lock acquisition attempt.
- statement_timeout limits total statement runtime.
- idle_in_transaction_session_timeout limits sessions sitting idle in a transaction if configured.

Setting timeouts lets migrations fail fast and retry cleanly. Do not set them so low that DDL constantly fails under normal traffic, nor leave migrations waiting unboundedly for locks.

### 10.4. Checking Blockers Before DDL

~~~sql
SELECT
    a.pid,
    a.usename,
    a.application_name,
    a.state,
    a.wait_event_type,
    a.wait_event,
    clock_timestamp() - a.xact_start AS transaction_age,
    pg_blocking_pids(a.pid) AS blocking_pids,
    a.query
FROM pg_stat_activity AS a
WHERE a.datname = current_database()
ORDER BY a.xact_start NULLS LAST;
~~~

If DDL waits, locate sessions holding locks. Identify owner, query, and transaction age before canceling or terminating.

### 10.5. Inspecting Relation Locks

~~~sql
SELECT
    l.pid,
    l.mode,
    l.granted,
    a.application_name,
    a.state,
    a.query
FROM pg_locks AS l
LEFT JOIN pg_stat_activity AS a
    ON a.pid = l.pid
WHERE l.relation = 'app.people'::regclass
ORDER BY l.granted, l.pid;
~~~

This is a point-in-time snapshot. Combine with pg_stat_activity and pg_blocking_pids to trace the blocker chain.

### 10.6. DDL Queues Can Impact Traffic

An ALTER TABLE waiting for ACCESS EXCLUSIVE can build a lock queue. New queries needing conflicting locks may wait behind the DDL, spiking latency even before the DDL executes. If waiters pile up:
- Inspect the DDL PID and lock mode.
- Inspect active blockers.
- Cancel/retry the migration if queue impact crosses thresholds.
- Reschedule for an appropriate window.
- Never queue multiple similar DDLs concurrently.

### 10.7. Transactions and Prepared Statements

Application connection pools may keep sessions and prepared statements alive across a migration. PostgreSQL invalidates and replans cached plans when schemas change, yet application-level SQL text using the old column name will still fail upon re-parsing.

After renaming:
- Drain or recycle connections if required by the framework.
- Check prepared statements.
- Inspect application logs.
- Exercise live query paths.
- Never rely on an old session's cached plan as proof of migration compatibility.

### 10.8. Table Rewrites and Disk Reclamation

DROP COLUMN is usually a fast metadata operation, marking the column dropped. Existing row versions may still contain the old bytes; subsequent inserts/updates store NULL for the dropped attribute. Space is reclaimed gradually as rows are updated, or more completely via a table rewrite.

Normal VACUUM makes space reusable within the table, but does not necessarily return space to the filesystem. VACUUM FULL, CLUSTER, or rewrite tools can reclaim storage at the cost of extra disk space, locks, and maintenance windows.

### 10.9. Do Not Mix Schema Changes With Heavy Rewrites

Renaming/dropping a column and rewriting a table are two different operations. If you both drop a column and run VACUUM FULL/CLUSTER in the same maintenance window, evaluate:
- Lock duration.
- Disk space required for the rewrite copy.
- WAL and replication impact.
- Backup windows.
- Application downtime.
- Rollback procedures.

### 10.10. Post-DDL Verification

After COMMIT:
- Query information_schema.columns / pg_attribute to verify the schema.
- Check views, materialized views, functions, and triggers.
- Check indexes and constraints.
- Run smoke tests under the application role.
- Monitor errors, locks, and query latency.
- Confirm the migration tool recorded the version cleanly.

---

## 11. Inventorying Dependencies Before Renaming or Dropping

### 11.1. Confirm Table and Column

~~~sql
SELECT
    n.nspname AS schema_name,
    c.relname AS table_name,
    a.attname AS column_name,
    a.attnum,
    format_type(a.atttypid, a.atttypmod) AS data_type,
    a.attnotnull,
    a.attisdropped
FROM pg_attribute AS a
JOIN pg_class AS c
    ON c.oid = a.attrelid
JOIN pg_namespace AS n
    ON n.oid = c.relnamespace
WHERE c.oid = 'app.people'::regclass
  AND a.attnum > 0
ORDER BY a.attnum;
~~~

Verify column existence, type, and nullability before grabbing attnum to look up dependencies.

### 11.2. Inventory Views and Materialized Views

Use the pg_depend/pg_rewrite query from earlier to find direct dependencies. Then:
- Read definitions with pg_get_viewdef.
- Inspect output columns via information_schema.columns.
- Find views depending on those views.
- Check materialized view refresh policies.
- Identify external database consumers.

### 11.3. Inventory Functions and Procedures

~~~sql
SELECT
    n.nspname,
    p.proname,
    pg_get_function_identity_arguments(p.oid) AS identity_arguments,
    l.lanname,
    pg_get_functiondef(p.oid) AS definition
FROM pg_proc AS p
JOIN pg_namespace AS n
    ON n.oid = p.pronamespace
JOIN pg_language AS l
    ON l.oid = p.prolang
WHERE n.nspname = 'app'
ORDER BY p.proname, identity_arguments;
~~~

Review source code for old column names. You can export definitions to search them, while protecting the output if functions contain literals or secrets.

### 11.4. Inventory Triggers and Policies

Use pg_trigger/pg_get_triggerdef and pg_policies. Do not overlook trigger function bodies, policy roles, and command scopes. Test SELECT, INSERT, UPDATE, and DELETE using an RLS-enabled application role.

### 11.5. Inventory Constraints and Indexes

Use pg_constraint, pg_indexes, and indexdef. Check other tables referencing the column via foreign keys. Inspect expression indexes, partial-index predicates, and INCLUDE columns.

### 11.6. Search Application Repositories

Search for the exact column identifier in:
- SQL migrations.
- ORM entities and models.
- Query builders.
- Raw SQL.
- Reports and dashboards.
- ETL pipelines.
- Stored function definitions.
- Test fixtures.
- Configuration-driven SQL.
- Deployment scripts.

Search for both quoted identifiers and aliases. Common column names produce false positives; review context rather than running blind bulk replacements.

### 11.7. Query Telemetry

If pg_stat_statements or query logging is available:
- Find queryid/query text referencing the old name.
- Check application_name.
- Review hourly/daily execution frequency.
- Watch for weekly, monthly, or quarterly jobs.
- Review query logs over a sufficiently long window.
- Confirm prepared statements and connection pools have rotated.

pg_stat_statements only stores aggregated query text per configuration/normalization; it is not a complete history of every SQL statement ever executed.

### 11.8. Owners and Sign-Off

Each consumer needs:
- An owner or team.
- Environment where it runs.
- Deployment timing.
- Test evidence.
- Rollback approach.
- End date of compatibility window.

Never execute contraction/drop without owners signed off for critical consumers.

---

## 12. Runbook: Renaming a Column

### 12.1. When Downtime Is Permitted

1. Inventory dependencies and consumers.
2. Deploy code, views, and function definitions using the new name or preserving compatibility aliases.
3. Stop writers and readers per maintenance plan.
4. Drain long-running transactions and connection pools if needed.
5. Run ALTER TABLE ... RENAME COLUMN with lock_timeout.
6. Update view output names if intended.
7. Update functions, triggers, and policies whose bodies reference the old name.
8. Run smoke and business tests.
9. Reopen traffic and monitor.
10. Record migration version and owner.

### 12.2. When Using Rolling Deployment

1. Add a new column or create a compatibility view/function.
2. Deploy code able to read/write both old and new schemas.
3. Dual-write or synchronize via trigger during transition.
4. Backfill old data in batches.
5. Validate parity and null semantics.
6. Switch all readers to the new name.
7. Stop old writes and wait out the consumer observation window.
8. Rename/drop the old column in the contract phase.
9. Remove compatibility layers once zero consumers remain.
10. Monitor query errors and data correctness.

### 12.3. Before Running DDL

~~~sql
BEGIN;
SET LOCAL lock_timeout = '3s';
SET LOCAL statement_timeout = '30s';

ALTER TABLE app.people
RENAME COLUMN full_name TO display_name;

COMMIT;
~~~

Run only after application, view, and function plans are ready. If lock timeout or DDL failure occurs, roll back the transaction and retry per procedure.

### 12.4. Post-Rename Verification

~~~sql
SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_schema = 'app'
  AND table_name = 'people'
ORDER BY ordinal_position;
~~~

Then test:
- Direct table reads and writes.
- Compatibility views.
- SQL functions.
- PL/pgSQL functions.
- Triggers.
- RLS policies.
- Application code and scheduled jobs.

---

## 13. Runbook: Dropping a Column

### 13.1. Deprecation Phase

1. Mark the column deprecated in the schema contract.
2. Notify consumer owners.
3. Deploy code that no longer reads or writes the column.
4. Stop ETL jobs, reports, or scheduled jobs using the column.
5. Retain the column for the compatibility window.
6. Monitor query telemetry and application errors.
7. Archive data if retention or business rules require.

### 13.2. Dependency Phase

1. Query pg_depend by table and attnum.
2. Inventory views, materialized views, and rules.
3. Search function and procedure bodies.
4. Inspect trigger definitions and trigger functions.
5. Inspect indexes, constraints, and foreign keys.
6. Inspect generated/default expressions and policies.
7. Search application repositories and external consumers.
8. Obtain owner sign-off for each dependency.

### 13.3. Dropping With RESTRICT

~~~sql
BEGIN;
SET LOCAL lock_timeout = '3s';
SET LOCAL statement_timeout = '30s';

ALTER TABLE app.people
DROP COLUMN legacy_code RESTRICT;

COMMIT;
~~~

RESTRICT is the proper choice so the migration fails if the catalog holds a dependency that must be preserved. If it fails, read the object named in the error and handle the dependency deliberately.

### 13.4. CASCADE Only After Inventorying

If the design requires dropping dependent views or rules, review the dependency graph and export definitions first. You can drop and recreate dependent objects via explicit migration scripts. Use CASCADE only when every object to be dropped has been approved.

Never add CASCADE to migrations by default just to silence dependency errors.

### 13.5. After DROP COLUMN

- Verify the column no longer appears in information_schema.columns.
- Verify dependent views, functions, and triggers.
- Verify index and constraint definitions.
- Run application smoke and regression tests.
- Monitor SQL errors and query latency.
- Track table size over time; do not expect immediate disk reduction.
- Evaluate a separate table rewrite if storage reclamation is required.

---

## 14. Migration Pattern: Rename With a Compatibility Window

### 14.1. Scenario

The table app.people has full_name. The application needs to switch to display_name, but multiple application instances and reports cannot deploy at once.

Goals:
- Do not break older application versions during rollout.
- Keep data consistent between both columns.
- Switch readers service by service.
- Drop the old column only after confirming zero consumers remain.

### 14.2. Expand: Add the New Column

~~~sql
ALTER TABLE app.people
ADD COLUMN display_name text;
~~~

The new column starts nullable to avoid backfilling the entire table inside one DDL transaction. Confirm default and nullability semantics with the application.

### 14.3. Application Dual-Write

During transition, the application writes the same value to both columns. Designate an authoritative source and ensure all writers obey the rule.

If services run mixed versions, a trigger can synchronize writes from un-upgraded clients. Test the trigger thoroughly for inserts, updates, nulls, and conflicts.

### 14.4. Example Trigger Synchronizing Two Columns

This is an illustrative pattern for a lab table; adapt to your business rules:

~~~sql
CREATE OR REPLACE FUNCTION app.sync_people_name_columns()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        IF NEW.display_name IS NULL THEN
            NEW.display_name := NEW.full_name;
        ELSIF NEW.full_name IS NULL THEN
            NEW.full_name := NEW.display_name;
        ELSIF NEW.display_name IS DISTINCT FROM NEW.full_name THEN
            RAISE EXCEPTION 'full_name and display_name differ';
        END IF;
        RETURN NEW;
    END IF;

    IF NEW.display_name IS DISTINCT FROM OLD.display_name
       AND NEW.full_name IS NOT DISTINCT FROM OLD.full_name THEN
        NEW.full_name := NEW.display_name;
    ELSIF NEW.full_name IS DISTINCT FROM OLD.full_name
       AND NEW.display_name IS NOT DISTINCT FROM OLD.display_name THEN
        NEW.display_name := NEW.full_name;
    ELSIF NEW.display_name IS DISTINCT FROM NEW.full_name THEN
        RAISE EXCEPTION 'conflicting name updates';
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER people_sync_name_columns
BEFORE INSERT OR UPDATE OF full_name, display_name
ON app.people
FOR EACH ROW
EXECUTE FUNCTION app.sync_people_name_columns();
~~~

This trigger is only an example. If both columns change simultaneously to different values, it rejects the write to avoid picking the wrong value. If business rules prioritize one source, implement that conflict resolution explicitly.

### 14.5. Batched Backfill

~~~sql
UPDATE app.people
SET display_name = full_name
WHERE display_name IS NULL
  AND person_id >= 1
  AND person_id < 10001;
~~~

Repeat across key ranges. Commit each batch separately, record progress, and monitor WAL and replication lag. Install the trigger or application dual-write before backfilling so newly written rows are not missed.

### 14.6. Validate

~~~sql
SELECT
    count(*) FILTER (
        WHERE display_name IS DISTINCT FROM full_name
    ) AS mismatch_count,
    count(*) FILTER (
        WHERE display_name IS NULL
    ) AS missing_new_value
FROM app.people;
~~~

If mismatches appear, determine the source of truth and reconcile; never automatically overwrite all data from one side.

### 14.7. Switch Readers

Deploy readers using display_name. Roll out per service, tenant, or canary. Monitor:
- Query errors.
- Null values.
- API response differences.
- Reports and exports.
- Trigger exceptions.
- Background jobs.
- Prepared statements and connection pools.

### 14.8. Stop Old Writes

Once all writers use display_name:
1. Remove old dual-write code.
2. Confirm the trigger is no longer needed.
3. Drop the compatibility trigger and function.
4. Observe zero usage of full_name across sufficient job cycles.
5. Obtain owner sign-offs.

### 14.9. Contract: Drop the Old Column

~~~sql
ALTER TABLE app.people
DROP COLUMN full_name RESTRICT;
~~~

After dropping:
- Verify schema.
- Verify functions, views, and triggers.
- Run application tests.
- Retain rollback data/backups per policy.
- Do not run a table rewrite without a storage reclamation requirement and separate plan.

### 14.10. Alternative: Keep Physical Column, Change View Contract

If applications access data through a view, you can rename the underlying table column while keeping the old alias in the view. This is often simpler than dual-writing, though it applies only when consumers do not query the base table directly and the view remains updatable or satisfies write semantics.

---

## 15. Testing Strategy for Schema Changes

### 15.1. Catalog Tests

In staging, run:
- Column and attnum inventory.
- Direct dependencies in pg_depend.
- Views and materialized views.
- Functions and procedures.
- Triggers and policies.
- Constraints and indexes.
- Foreign keys from other tables.

Compare expected objects before and after migration.

### 15.2. Function Tests

Invoke every function path using the column:
- SQL functions.
- PL/pgSQL functions.
- Trigger functions.
- Dynamic SQL branches.
- Functions invoked by scheduled jobs.
- Functions invoked by different application roles.

An unexercised function in a smoke test can still fail in a rare branch.

### 15.3. View Tests

Test:
- Direct views.
- Nested views.
- Materialized view queries and refreshes.
- Output column names and types.
- Permissions and security_barrier / security_invoker behavior if applicable.
- Application queries referencing the view.

### 15.4. DML Tests

For triggers, constraints, and policies, test:
- INSERT.
- UPDATE on old column.
- UPDATE on new column.
- UPDATE on both columns.
- DELETE.
- ON CONFLICT.
- Bulk imports / COPY.
- RLS across each role.

### 15.5. Compatibility Tests

Run both old and new application versions in staging against the same transitional schema window. Confirm the old version reads and writes during expansion, and the new version needs nothing from the old column after switching.

### 15.6. Lock Tests

Run the migration while transactions read and write the table to measure lock wait. Verify lock_timeout, queue behavior, and DDL duration. Use production-like workloads without impacting live systems.

### 15.7. Rollback Tests

Test rollback at every phase:
- Before backfilling.
- Mid-backfill.
- After full backfill but before switching readers.
- After switching readers but before dropping the old column.
- After dropping the old column.

Post-contract rollback requires restoring the column/data or a forward migration, not merely reverting code.

### 15.8. Migration Idempotency

Migration runners can guarantee each migration runs once. For retryable operational scripts, add explicit guards and state checks. Never use IF EXISTS / IF NOT EXISTS to mask an unexpected schema state without validation.

### 15.9. Observability

During rollout, monitor:
- Application error rate.
- Query errors containing undefined_column.
- Function execution failures.
- View and report failures.
- Lock waits.
- Trigger exceptions.
- Backfill progress and mismatch counts.
- Database CPU, WAL, and replication lag.
- Consumer usage of the old column.

### 15.10. Readiness Gate

Proceed to contraction only when:
- All critical consumers have migrated.
- Old column usage has been zero over a sufficiently long observation window.
- Data parity is verified.
- Views, functions, triggers, and policies have been tested.
- Rollback paths and owners are clear.
- The DDL lock window is approved.

---

## 16. Rollback and Recovery

### 16.1. Rolling Back a Rename

If you renamed directly and no incompatible writes or schema changes occurred yet, you can rename back:

~~~sql
ALTER TABLE app.people
RENAME COLUMN display_name TO full_name;
~~~

Code and database rollbacks must be coordinated. If the new app already wrote data under new semantics or view contracts changed, renaming back may not suffice.

### 16.2. Rolling Back the Expand Phase

If the new column was added without switching readers:
- Stop dual-writes or triggers per plan.
- Keep the new column for investigation or drop it only once confirmed free of dependencies.
- The old source column remains authoritative.
- Do not delete new data without checking whether any consumer already used it.

### 16.3. Rolling Back After Backfill

Backfilling may have populated new data or normalized values. While the source remains intact, you can pause the migration and keep both columns. Never automatically copy back if divergent writes happened on both sides.

### 16.4. Rolling Back After Reader Switch

Switch readers back to the old column if dual-write remained active and parity still holds. If dual-write was already disabled, identify the source of truth and synchronize before reverting the application.

### 16.5. Rolling Back After DROP COLUMN

Once the old column is dropped, PostgreSQL cannot simply rename it back because the column definition and data are no longer accessible via SQL. To roll back:
- Restore from backup/PITR into an appropriate environment and extract the data.
- Re-add the column and backfill from the new column if semantics match.
- Reconstruct from audit or event history.
- Forward-fix on the new schema.

If old column data had distinct semantics or was discarded, re-adding the column will not restore previous values automatically.

### 16.6. CASCADE Rollback

CASCADE can drop multiple views, rules, and constraints. Rolling back requires definitions, ownership, grants, indexes, and materialized data/refresh plans. Save definitions before migrating and prefer explicit migration scripts capable of recreating objects.

### 16.7. Pre-Contract Backup

Before a critical DROP COLUMN:
- Verify the latest backup can be restored.
- Record table and column metadata.
- Save view, function, and trigger definitions.
- Save grants and ownership.
- Confirm retention and legal requirements.
- Identify the PITR window if needed.

A backup is only valuable if its restore path has been tested; never use an unverified backup as an excuse to skip validation.

---

## 17. Common Mistakes

### 17.1. Assuming Rename Fixes Application SQL

PostgreSQL only manages dependencies recorded in the database. Source code, ORMs, BI tools, and dynamic SQL must be updated separately.

### 17.2. Assuming View Output Names Update With Base Columns

View output columns are a separate schema contract. Renaming a base column may leave the view running while keeping its old output name.

### 17.3. Using CASCADE to Bypass RESTRICT Errors

CASCADE can wipe out many dependent objects. Inventory dependencies and identify consumer owners first.

### 17.4. Relying on DROP RESTRICT to Catch Every Function

String-bodied functions, PL/pgSQL source, and dynamic SQL often lack body dependencies in the catalog. Search and test them separately.

### 17.5. Dropping a Column While Old App Instances Still Run

An old instance or scheduled job can query the column after it is dropped and hit undefined_column. Wait out the compatibility window and verify telemetry.

### 17.6. Assuming DROP COLUMN Frees Disk Immediately

The column is marked dropped; existing tuples can retain the old bytes. Space is reclaimed gradually as rows are updated or via a table rewrite.

### 17.7. Thinking Fast DDL Needs No Maintenance Window

Renames and drops require strong locks. Long transactions can force DDL to wait and build queues blocking other queries.

### 17.8. Changing Views and Functions in the Wrong Order

Dependent views or functions can fail to compile if base objects change before compatibility layers exist. Establish dependency ordering and deploy wrappers/views before migrating consumers.

### 17.9. Running Backfills in One Massive Transaction

A full-table UPDATE generates heavy WAL, bloat, replication lag, and lock/latency impact. Split into batches, commit frequently, and track progress.

### 17.10. Skipping RLS and Trigger Testing

Queries run as superuser may succeed while the application role is blocked by policies or triggers. Test with the real application role and all DML paths.

---

## 18. Lab: Column Rename and View Dependencies

Run in a lab database. Never alter production schemas just to observe dependencies.

### 18.1. Create Table and Views

~~~sql
CREATE SCHEMA IF NOT EXISTS schema_change_lab;

CREATE TABLE schema_change_lab.people (
    person_id bigint PRIMARY KEY,
    full_name text NOT NULL
);

INSERT INTO schema_change_lab.people
VALUES
    (1, 'An Nguyen'),
    (2, 'Binh Tran');

CREATE VIEW schema_change_lab.people_v1 AS
SELECT person_id, full_name
FROM schema_change_lab.people;

CREATE VIEW schema_change_lab.people_v1_report AS
SELECT person_id, upper(full_name) AS normalized_name
FROM schema_change_lab.people_v1;
~~~

### 18.2. Inspect Definitions

~~~sql
SELECT
    schemaname,
    viewname,
    definition
FROM pg_views
WHERE schemaname = 'schema_change_lab'
ORDER BY viewname;
~~~

### 18.3. Rename the Base Column

~~~sql
ALTER TABLE schema_change_lab.people
RENAME COLUMN full_name TO display_name;
~~~

### 18.4. Test View Output

~~~sql
SELECT * FROM schema_change_lab.people_v1;
SELECT * FROM schema_change_lab.people_v1_report;
~~~

Observe that the views still return the old output names per their definitions. Verify that querying people.full_name directly no longer resolves.

### 18.5. Rename View Output

~~~sql
ALTER VIEW schema_change_lab.people_v1
RENAME COLUMN full_name TO display_name;
~~~

Inspect the dependent view people_v1_report and adjust if needed. Query both views after the migration.

### 18.6. Inspect Dependencies

Run the pg_depend/pg_rewrite query from Section 5.4 using the lab's schema, table, and column. Cross-check direct dependent views.

---

## 19. Lab: Function Dependencies and DROP COLUMN

### 19.1. Create a String-Body Function

~~~sql
CREATE FUNCTION schema_change_lab.person_name(p_id bigint)
RETURNS text
LANGUAGE sql
AS $$
    SELECT display_name
    FROM schema_change_lab.people
    WHERE person_id = p_id
$$;
~~~

### 19.2. Create a PL/pgSQL Function

~~~sql
CREATE FUNCTION schema_change_lab.person_name_plpgsql(p_id bigint)
RETURNS text
LANGUAGE plpgsql
AS $$
DECLARE
    v_name text;
BEGIN
    SELECT display_name
    INTO v_name
    FROM schema_change_lab.people
    WHERE person_id = p_id;

    RETURN v_name;
END;
$$;
~~~

### 19.3. Test Functions

~~~sql
SELECT schema_change_lab.person_name(1);
SELECT schema_change_lab.person_name_plpgsql(1);
~~~

### 19.4. Search Function Sources

~~~sql
SELECT
    p.oid::regprocedure AS function_signature,
    l.lanname,
    p.prosrc
FROM pg_proc AS p
JOIN pg_namespace AS n
    ON n.oid = p.pronamespace
JOIN pg_language AS l
    ON l.oid = p.prolang
WHERE n.nspname = 'schema_change_lab'
  AND p.prosrc ILIKE '%display_name%';
~~~

### 19.5. Test DROP RESTRICT in a Separate Lab

Create a view depending on display_name and attempt DROP COLUMN RESTRICT. Observe PostgreSQL reporting the dependency. Then drop/recreate the view per plan and retry.

Do not use CASCADE before recording all dependent definitions. String-bodied functions may not block DROP despite still containing the column name; invoke the function after dropping to observe the runtime error if references remain.

### 19.6. Clean Up the Lab

After saving results, drop the lab schema in the test environment. Do not run cleanup commands if the schema holds objects you want to keep.

---

## 20. Lab: Expand-and-Contract

### 20.1. Create Lab Table

~~~sql
CREATE TABLE schema_change_lab.contacts (
    contact_id bigint PRIMARY KEY,
    old_label text
);

INSERT INTO schema_change_lab.contacts
SELECT g, 'Contact ' || g
FROM generate_series(1, 10000) AS g;
~~~

### 20.2. Expand

~~~sql
ALTER TABLE schema_change_lab.contacts
ADD COLUMN new_label text;
~~~

### 20.3. Batched Backfill

~~~sql
UPDATE schema_change_lab.contacts
SET new_label = old_label
WHERE new_label IS NULL
  AND contact_id BETWEEN 1 AND 1000;
~~~

Repeat across remaining ranges. In production, install dual-write or a trigger before backfilling so concurrent writes are not missed.

### 20.4. Validate Parity

~~~sql
SELECT
    count(*) FILTER (
        WHERE new_label IS DISTINCT FROM old_label
    ) AS mismatch_count,
    count(*) FILTER (
        WHERE new_label IS NULL
    ) AS null_count
FROM schema_change_lab.contacts;
~~~

### 20.5. Switch Readers and Contract

In the lab, switch queries to new_label. After confirming zero consumers still use old_label:

~~~sql
ALTER TABLE schema_change_lab.contacts
DROP COLUMN old_label RESTRICT;
~~~

### 20.6. Observe Physical Storage

Compare pg_total_relation_size before and after DROP COLUMN. Do not expect immediate shrinkage; test a table rewrite only in a dedicated lab and observe lock/disk impact.

---

## 21. Practice Exercises

Use a PostgreSQL lab for these exercises. Never run DROP COLUMN CASCADE in production merely to inspect dependencies.

### Exercise 1 — Rename

Write the command to rename column full_name to display_name in app.people.

### Exercise 2 — Drop

Write the command to drop legacy_code with RESTRICT explicitly specified.

### Exercise 3 — CASCADE

How does CASCADE differ from RESTRICT? Name two types of dependent objects that can be dropped.

### Exercise 4 — Column Identity

Why can a view continue working after a base table column is renamed?

### Exercise 5 — View Output

After renaming a base column, does a view's output column name change automatically? How do you change the output name?

### Exercise 6 — pg_depend

Explain the meaning of classid, objid, refobjid, and refobjsubid.

### Exercise 7 — attnum

What is attnum? Why does an attnum-based dependency remain valid after a rename?

### Exercise 8 — String-Bodied Functions

Why might an SQL function using a string literal body fail to block DROP COLUMN RESTRICT?

### Exercise 9 — SQL-Standard Bodies

How does an SQL-standard function body differ from a string body regarding dependency tracking?

### Exercise 10 — PL/pgSQL

At what point after a rename might a PL/pgSQL function referencing old_column fail?

### Exercise 11 — Dynamic SQL

Why is dynamic SQL hard for catalog dependency tracking to detect?

### Exercise 12 — Triggers

List what needs checking when a trigger function uses OLD.old_column or NEW.old_column.

### Exercise 13 — Materialized Views

How does renaming a base column affect a materialized view? When is a refresh needed?

### Exercise 14 — Indexes

Why must expression indexes be inventoried before dropping a column?

### Exercise 15 — Foreign Keys

Why must referencing tables also be checked when dropping a referenced key column?

### Exercise 16 — RLS

How can a policy depend on a column? Which role should be used for testing?

### Exercise 17 — DROP Storage

Does DROP COLUMN immediately return disk space to the filesystem?

### Exercise 18 — Locks

Why can a fast ALTER TABLE rename/drop still cause downtime?

### Exercise 19 — lock_timeout

How does lock_timeout differ from statement_timeout?

### Exercise 20 — Expand-Contract

Outline the stages of adding a new column, dual-writing, backfilling, switching readers, and dropping the old column.

### Exercise 21 — Backfill

Why should backfills be split into batches?

### Exercise 22 — Parity

Write a query counting rows where new_value differs from old_value, properly accounting for NULL semantics.

### Exercise 23 — View Compatibility

When should you use a view alias to preserve an old column name for consumers?

### Exercise 24 — Rollback

Why is rollback easier before dropping the old column? What options exist after dropping it?

### Exercise 25 — CASCADE Review

What information must be gathered and reviewed before using CASCADE?

### Exercise 26 — Query Telemetry

How can pg_stat_statements help detect old column usage? What are its limitations?

### Exercise 27 — Prepared Statements

How can renames/drops affect prepared statements and application connection pools?

### Exercise 28 — Multi-Team Ownership

A column is used by 3 services, 2 reports, and 1 trigger. How should the migration be managed?

### Exercise 29 — DDL Rollout

Describe a column-rename migration sequence for a rolling deployment without extended downtime.

### Exercise 30 — Capstone Incident

DROP COLUMN RESTRICT succeeded, yet a PL/pgSQL function errored with undefined_column during a nightly job. Explain why the catalog did not block it and how to prevent recurrence.

---

## 22. Solutions — Exercises 1 to 15

### Exercise 1 — Rename

~~~sql
ALTER TABLE app.people
RENAME COLUMN full_name TO display_name;
~~~

### Exercise 2 — Drop

~~~sql
ALTER TABLE app.people
DROP COLUMN legacy_code RESTRICT;
~~~

### Exercise 3 — CASCADE

RESTRICT rejects the drop if any catalog-recorded dependency must be preserved. CASCADE drops the specified object along with dependent objects across the dependency graph. For example, dependent views and rules can be dropped, and views depending on those views can also be removed.

### Exercise 4 — Column Identity

A view's query tree stores references to relation/column identity, typically via attnum. Renaming only changes the display name of the column without creating a new column identity, so the view continues referencing the same column.

### Exercise 5 — View Output

No. A view's output column is a separate contract and can keep the old name. Use ALTER VIEW ... RENAME COLUMN to rename the output column, then migrate consumers of the view.

### Exercise 6 — pg_depend

classid identifies the catalog holding the dependent object; objid is that object's OID; refobjid is the OID of the referenced object; refobjsubid identifies the referenced sub-object or column.

### Exercise 7 — attnum

attnum is the column's attribute number within the relation. Renaming does not change attnum, so column-identity dependencies remain valid even though attname changes.

### Exercise 8 — String-Bodied Functions

String-bodied functions are stored as source text and are not parsed into full dependency records like SQL-standard bodies. PostgreSQL may not know which column identifiers appear inside the body; the function only fails when executed after DROP/RENAME.

### Exercise 9 — SQL-Standard Bodies

SQL-standard bodies are parsed at function definition time, allowing PostgreSQL to record dependencies on referenced objects. Traditional string bodies do not receive the same tracking for references inside the body.

### Exercise 10 — PL/pgSQL

The function can fail when the branch containing SQL using old_column executes, or when the statement is compiled/replanned after the schema change. Because body references are typically not recorded like view dependencies, DROP can succeed before runtime errors appear.

### Exercise 11 — Dynamic SQL

Relation and column names are concatenated as text at runtime. Catalogs cannot determine the final identifier from source strings; source searches, allowlists, and runtime tests are required.

### Exercise 12 — Triggers

Check trigger event definitions, UPDATE OF column lists, OLD/NEW field references, trigger function source, dynamic SQL, application side effects, and all DML paths that fire the trigger.

### Exercise 13 — Materialized Views

A materialized view holds dependencies on its source query objects and can continue referencing column identity after a rename. Materialized data does not refresh automatically when base rows change; run REFRESH per policy. Changing the output schema may require versioning or recreating it.

### Exercise 14 — Indexes

Expression and partial indexes can use a column in their keys or predicates. Dropping the column can remove related indexes; you must know which workloads depend on them and prepare replacement indexes if needed.

### Exercise 15 — Foreign Keys

A referenced column may be referenced by multiple child tables. You must inventory foreign keys on both referenced and referencing sides, determine business integrity rules, and plan migration order.

---

## 23. Solutions — Exercises 16 to 30

### Exercise 16 — RLS

Policy USING/WITH CHECK expressions can reference columns to control row visibility and write permissions. Test with actual application roles under active row-level security, not solely as superuser.

### Exercise 17 — DROP Storage

No. The column is marked dropped; existing tuples can retain the old bytes. Space is reclaimed gradually as rows are updated or via a table rewrite. Normal VACUUM does not necessarily return space to the filesystem immediately.

### Exercise 18 — Locks

RENAME/DROP requires a strong table lock. If another transaction holds a conflicting lock, DDL waits; the lock queue can force new queries to wait behind it. Even fast metadata DDL can cause latency or downtime.

### Exercise 19 — lock_timeout

lock_timeout limits how long a statement waits to acquire a lock. statement_timeout limits total statement duration, including both lock wait time and execution.

### Exercise 20 — Expand-Contract

Add the new column; deploy dual-write/triggers; backfill in batches; validate parity; switch readers; stop old writes; wait for zero remaining old consumers; drop the old column with RESTRICT; remove compatibility layers.

### Exercise 21 — Backfill

Batches reduce transaction size, WAL bursts, lock duration, replication lag, and bloat risk. Each range can be committed/retried independently while tracking progress.

### Exercise 22 — Parity

~~~sql
SELECT count(*)
FROM app.people
WHERE new_value IS DISTINCT FROM old_value;
~~~

IS DISTINCT FROM handles NULL semantics properly, treating NULL/NULL as equal and NULL/value as distinct.

### Exercise 23 — View Compatibility

Use when multiple consumers need a stable schema contract and can access data through a view instead of the base table. A view alias can keep the old output column name while the table uses the new name. It does not protect direct table access.

### Exercise 24 — Rollback

Before dropping, the old column still holds data so readers/writers can revert to the old schema or keep dual-writing. After dropping, rollback requires re-adding/backfilling, restoring from backup/PITR, reconstructing from audit/event history, or deploying a forward migration.

### Exercise 25 — CASCADE Review

Gather the dependency graph, object definitions, owners, grants, materialized data/refresh requirements, indexes/constraints, application/report consumers, rollback scripts, and sign-offs. Identify every object that will be dropped recursively.

### Exercise 26 — Query Telemetry

pg_stat_statements can locate query text/queryids using the old name along with execution frequency/call counts within the retention/reset window. It does not store complete statement history, misses unexecuted queries, and cannot uncover all dynamic SQL or external sources.

### Exercise 27 — Prepared Statements

Schema changes trigger invalidation/replanning of cached plans. Once a statement re-parses, SQL text using the old column name will fail. Recycle/drain pools if needed and run live tests post-migration.

### Exercise 28 — Multi-Team Ownership

Build a consumer inventory with owners for the 3 services, 2 reports, and trigger. Announce deprecation, establish a compatibility window, update each consumer, dual-write/backfill if needed, monitor usage, obtain sign-off, and only then contract/drop. Update and test the trigger function separately.

### Exercise 29 — DDL Rollout

Add a new column or view alias; deploy code compatible with both old and new; dual-write; backfill; validate; switch readers service by service; stop old writes; observe zero usage long enough; drop the old column with RESTRICT in a short window using lock_timeout; verify and monitor.

### Exercise 30 — Capstone Incident

DROP COLUMN RESTRICT succeeded because body references inside PL/pgSQL source are typically not recorded as column dependencies. When the function ran, SQL parsed/replanned and failed to find the dropped identifier. Fix the function body, test all branches and trigger callers, add source searches and function tests to the migration pipeline, monitor query/function errors, and require owner sign-off before contraction.

---

## 24. Deployment Checklist

### Before Rename/Drop
- [ ] Confirm exact schema, table, and column.
- [ ] Confirm business meaning and data retention rules.
- [ ] Inventory pg_depend and direct dependent objects.
- [ ] Check views, materialized views, and rules.
- [ ] Search SQL-standard, string-bodied, and PL/pgSQL functions.
- [ ] Check dynamic SQL and trigger OLD/NEW references.
- [ ] Inventory indexes, constraints, foreign keys, generated columns, and RLS policies.
- [ ] Search application, ORM, BI, ETL, and reporting consumers.
- [ ] Identify owners, deployment order, and rollback paths.
- [ ] Run staging rehearsal with lock_timeout.

### Before Contract/Drop
- [ ] Old column usage is zero over an adequate observation window.
- [ ] All application instances and background jobs have migrated.
- [ ] Dual-write/backfill parity achieved.
- [ ] Views, functions, triggers, and policies updated and tested.
- [ ] Dependency graph reviewed.
- [ ] Use RESTRICT first; never use CASCADE without sign-off.
- [ ] Backup/PITR/restore path verified.
- [ ] Maintenance window, lock_timeout, and decision owner confirmed.

### After Migration
- [ ] Schema and column metadata are correct.
- [ ] View output names and types are correct.
- [ ] Functions, procedures, and triggers execute cleanly.
- [ ] Indexes, constraints, and foreign keys are valid.
- [ ] Application smoke and regression tests pass.
- [ ] Query errors / undefined_column counts do not rise.
- [ ] Data parity and business invariants hold.
- [ ] Compatibility objects are removed on schedule.
- [ ] Migration records and runbooks are updated.

---

## 25. PostgreSQL Reference Documentation

Prefer documentation matching your running major version:

- [PostgreSQL — ALTER TABLE](https://www.postgresql.org/docs/current/sql-altertable.html): RENAME COLUMN, DROP COLUMN, RESTRICT/CASCADE, and lock behavior.
- [PostgreSQL — Dependency Tracking](https://www.postgresql.org/docs/current/ddl-depend.html): dependency rules and DROP behavior.
- [PostgreSQL — System Catalogs: pg_depend](https://www.postgresql.org/docs/current/catalog-pg-depend.html): dependency records.
- [PostgreSQL — System Catalogs: pg_attribute](https://www.postgresql.org/docs/current/catalog-pg-attribute.html): relation columns and attnum.
- [PostgreSQL — CREATE VIEW](https://www.postgresql.org/docs/current/sql-createview.html): view definitions and replacement constraints.
- [PostgreSQL — CREATE FUNCTION](https://www.postgresql.org/docs/current/sql-createfunction.html): function body syntax and SQL-standard bodies.
- [PostgreSQL — ALTER VIEW](https://www.postgresql.org/docs/current/sql-alterview.html): renaming view output columns.
- [PostgreSQL — Explicit Locking](https://www.postgresql.org/docs/current/explicit-locking.html): table locks and conflicts.

`/current/` pages may reflect newer major releases. Check syntax, catalog columns, and function body behavior on your operating version.

---

## 26. Summary

Renaming and dropping columns are schema changes that can affect many consumers. PostgreSQL dependency tracking protects object references stored in catalogs, yet does not replace checking function sources, dynamic SQL, application code, reports, and external jobs.

Key principles to remember:

1. RENAME COLUMN renames an existing column without copying data into a new column.
2. Views can keep running after a base column rename because dependencies track column identity.
3. A view's output column name is a separate contract and does not change automatically with the base column.
4. DROP COLUMN defaults to RESTRICT; CASCADE can drop an entire dependency chain.
5. Table-local indexes and constraints may be handled automatically on drop, yet must still be inventoried for workload impact.
6. pg_depend and pg_attribute let you inspect direct dependencies by relation OID and attnum.
7. SQL-standard function bodies provide stronger dependency tracking than traditional string bodies.
8. PL/pgSQL and dynamic SQL can hold references missed by catalogs; runtime errors can appear after DROP.
9. Trigger definitions, OLD/NEW references, policies, generated expressions, and foreign keys must all be reviewed.
10. DROP COLUMN does not necessarily free disk immediately; existing tuples may keep old bytes.
11. RENAME/DROP requires strong locks; use lock_timeout and short transactions.
12. Expand-and-contract lets rolling deployments and multiple consumers coexist.
13. Dual-write and backfills require a clear authoritative source and conflict rules.
14. Drop only after zero old usage over a sufficient period and owner sign-off.
15. Prefer DROP RESTRICT; use CASCADE only after reviewing the dependency graph.
16. Rollback after DROP requires restoring/rebuilding data or forward migration; you cannot simply rename back.
17. Test under the application role across all function and view paths, not just superuser smoke tests.

General workflow: **inventory consumers → inspect catalog dependencies → design compatibility window → update views/functions/triggers → dual-write/backfill if needed → validate parity → switch readers/writers → observe zero old usage → DROP COLUMN RESTRICT → verify and monitor**.
