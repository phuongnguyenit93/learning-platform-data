# IMPORT FOREIGN SCHEMA and Source Structure Management

`IMPORT FOREIGN SCHEMA` is a PostgreSQL SQL command used to create foreign tables in the current database based on the structure of tables and views in a schema on a remote server. It is commonly used with `postgres_fdw` to integrate data between PostgreSQL databases. After importing, applications can query remote objects using familiar SQL syntax just like querying local tables.

Importantly, the command only imports **metadata and foreign table definitions**. The data itself remains on the source server; PostgreSQL accesses remote data at query execution time. Imported definitions also do not update automatically when the source schema changes. Therefore, a change-management process is needed so foreign table definitions in the target database remain compatible with the actual source structure.

## 1. Role of IMPORT FOREIGN SCHEMA in Data Integration

When integrating two databases, you often need a layer of objects in the target database representing tables or views in the source database. With Foreign Data Wrappers (FDW), PostgreSQL provides this abstraction layer through foreign tables.

A typical `postgres_fdw` setup includes the following components:

- **Foreign data wrapper**: an extension or component that handles communication with a type of data source. `postgres_fdw` is the FDW for PostgreSQL.
- **Foreign server**: describes the remote server and database that PostgreSQL connects to.
- **User mapping**: maps a local database role to login credentials on the remote database.
- **Local schema**: a schema in the current database used to hold the foreign tables.
- **Foreign table**: a local definition describing a table or view on the remote source.

The access flow can be visualized as follows:

```text
Application / SQL query
          |
          v
Target database: schema ext_sales
          |
          | foreign table: ext_sales.orders
          v
postgres_fdw + foreign server + user mapping
          |
          | connects to source database
          v
Source database: schema public, table orders
          |
          v
Actual data remains stored in the source database
```

For example, the source database has table `public.orders`. After importing into schema `ext_sales` in the target database, queries can be written as:

```sql
SELECT order_id, customer_id, order_date, total_amount
FROM ext_sales.orders
WHERE order_date >= DATE '2026-01-01';
```

`ext_sales.orders` is a foreign table in the target database catalog. When the query runs, `postgres_fdw` connects to the source and reads the matching data. The import command does not copy data rows into the target database like `COPY`, `INSERT INTO ... SELECT`, or an ETL pipeline.

`IMPORT FOREIGN SCHEMA` is a feature of the FDW framework. An FDW must support schema import for the command to retrieve metadata and create foreign tables. Specific options depend on the FDW; the examples below featuring `import_collate`, `import_default`, `import_generated`, and `import_not_null` are `postgres_fdw` options.

## 2. Prerequisites Before Importing

Before running the command, prepare the connection to the source database and the target schema.

### 2.1. Installing postgres_fdw

Run in the target database:

```sql
CREATE EXTENSION IF NOT EXISTS postgres_fdw;
```

This creates the extension providing the `postgres_fdw` foreign data wrapper. The operator must have sufficient privileges to install extensions in the database.

### 2.2. Declaring the Foreign Server

Suppose the source database has host `db.example.net`, port `5432`, and database name `sales`:

```sql
CREATE SERVER sales_source
FOREIGN DATA WRAPPER postgres_fdw
OPTIONS (
    host 'db.example.net',
    port '5432',
    dbname 'sales'
);
```

The values in `OPTIONS` specify connection details. In real environments, configure TLS, authentication, and networking per system security policy. Never place real passwords in scripts committed to Git or shared documentation.

### 2.3. Creating a User Mapping

A user mapping defines the remote account that a local role uses. For example, creating a mapping for the role performing migrations:

```sql
CREATE USER MAPPING FOR CURRENT_USER
SERVER sales_source
OPTIONS (
    user 'sales_reader',
    password '<secret-managed-outside-source-control>'
);
```

The `sales_reader` role on the source database must have privileges to access the schema and the imported tables or views. If multiple local roles need access, create separate mappings per role or for a shared role according to your security design. A mapping must exist for the role executing the query; another role's mapping is not used automatically as a fallback.

### 2.4. Creating the Target Schema and Granting Privileges

```sql
CREATE SCHEMA IF NOT EXISTS ext_sales;

GRANT USAGE ON FOREIGN SERVER sales_source TO analytics_reader;
GRANT USAGE ON SCHEMA ext_sales TO analytics_reader;
```

The role executing `IMPORT FOREIGN SCHEMA` needs permission to use the foreign server and create objects in the target schema. End users querying afterward need `USAGE` on the schema, appropriate privileges on the foreign tables, and a valid user mapping.

For example, granting read privileges to an analytics role after foreign tables are created:

```sql
GRANT SELECT ON ALL TABLES IN SCHEMA ext_sales TO analytics_reader;
```

Beyond local privileges, the account declared in the user mapping must also be granted privileges on the source database. For read-only sources, use an account with least privilege—for instance, only `USAGE` on the schema and `SELECT` on permitted objects.

## 3. IMPORT FOREIGN SCHEMA Syntax

General syntax:

```sql
IMPORT FOREIGN SCHEMA remote_schema
    [ LIMIT TO ( table_name [, ...] )
    | EXCEPT ( table_name [, ...] ) ]
    FROM SERVER server_name
    INTO local_schema
    [ OPTIONS ( option 'value' [, ...] ) ];
```

Component meanings:

| Component | Meaning |
|---|---|
| `remote_schema` | Name of the schema on the source database to read metadata from. |
| `LIMIT TO` | Import only the listed tables or views. |
| `EXCEPT` | Import objects in the source schema excluding the listed names. |
| `FROM SERVER` | Selects a foreign server declared in the target database. |
| `INTO` | Selects the local schema that will hold the created foreign tables. This schema must already exist. |
| `OPTIONS` | Passes FDW-specific options. |

Object names in the list are SQL identifiers. If a name contains uppercase letters, spaces, or special characters, enclose it in double quotes per PostgreSQL identifier rules.

### 3.1. Importing an Entire Schema

Without `LIMIT TO` or `EXCEPT`, the command asks the FDW to import all supported objects in the source schema:

```sql
IMPORT FOREIGN SCHEMA public
FROM SERVER sales_source
INTO ext_sales;
```

With `postgres_fdw`, this creates foreign tables corresponding to supported tables and views in the `public` schema on the source database.

### 3.2. Importing Only Needed Objects with LIMIT TO

In production environments, explicitly define the set of objects to integrate. For example, importing only customers, orders, and order items:

```sql
IMPORT FOREIGN SCHEMA public
    LIMIT TO (customers, orders, order_items)
    FROM SERVER sales_source
    INTO ext_sales;
```

`LIMIT TO` ensures the target schema contains only the objects the application needs. This reduces coupling to the source, avoids accidentally broadening access, and makes change tracking easier.

### 3.3. Excluding Specific Objects with EXCEPT

When you need most of a schema but want to omit a few tables, use `EXCEPT`:

```sql
IMPORT FOREIGN SCHEMA public
    EXCEPT (audit_log, temporary_imports)
    FROM SERVER sales_source
    INTO ext_sales;
```

`EXCEPT` is convenient when the source schema has many shared tables. However, if only a few tables are approved for integration, an allowlist using `LIMIT TO` is usually easier to govern than an exclusion list.

### 3.4. Choosing postgres_fdw Import Options

`postgres_fdw` supports the following options during import:

| Option | Default | Effect |
|---|---:|---|
| `import_collate` | `true` | Whether column `COLLATE` information is included in foreign table definitions. |
| `import_default` | `false` | Whether column `DEFAULT` expressions are included in definitions. |
| `import_generated` | `true` | Whether `GENERATED` column expressions are included in definitions. |
| `import_not_null` | `true` | Whether column `NOT NULL` constraints are included in foreign table definitions. |

Example:

```sql
IMPORT FOREIGN SCHEMA public
    LIMIT TO (customers, orders)
    FROM SERVER sales_source
    INTO ext_sales
    OPTIONS (
        import_collate 'true',
        import_default 'false',
        import_generated 'true',
        import_not_null 'true'
    );
```

Key considerations when choosing options:

- `import_default` defaults to `false`. When enabled, default expressions are copied into the local definition. Those expressions may evaluate differently on the two servers; for instance, `nextval()` may reference a different sequence or state. Import can also fail if an expression uses a function or operator missing from the target database.
- `import_generated` defaults to `true`. Imported generated expressions must reference compatible types, functions, and operators in the target database.
- `import_collate` defaults to `true`. Collation names or default collations may differ between servers, especially across different operating systems. Disabling this option is not always a safe fix: incompatible collations can change comparison and sorting results.
- `import_not_null` defaults to `true`, so `NOT NULL` attributes are included in foreign table definitions.

`postgres_fdw` does not automatically import other constraints such as `CHECK`, primary keys, unique constraints, or foreign keys. If you need such constraints in the target database, design and add them manually after verifying that their expressions and semantics match the remote data. User-defined types on the source also require compatible types with the same name in the target database.

## 4. Complete Example

Suppose the `sales` database on the source server has a `public` schema with tables `customers`, `orders`, and `order_items`. The target database needs to query these three objects for reporting.

Configuration commands on the target database:

```sql
-- 1. Install the FDW.
CREATE EXTENSION IF NOT EXISTS postgres_fdw;

-- 2. Declare the source database.
CREATE SERVER sales_source
FOREIGN DATA WRAPPER postgres_fdw
OPTIONS (
    host 'db.example.net',
    port '5432',
    dbname 'sales'
);

-- 3. Declare remote login credentials for the migration role.
CREATE USER MAPPING FOR CURRENT_USER
SERVER sales_source
OPTIONS (
    user 'sales_reader',
    password '<secret-managed-outside-source-control>'
);

-- 4. Prepare the local schema.
CREATE SCHEMA IF NOT EXISTS ext_sales;

-- 5. Import only the required objects.
IMPORT FOREIGN SCHEMA public
    LIMIT TO (customers, orders, order_items)
    FROM SERVER sales_source
    INTO ext_sales
    OPTIONS (
        import_default 'false',
        import_generated 'true',
        import_not_null 'true'
    );
```

After a successful import, you can query:

```sql
SELECT order_id, customer_id, order_date, total_amount
FROM ext_sales.orders
WHERE order_date >= DATE '2026-01-01'
ORDER BY order_date DESC
LIMIT 20;
```

You can combine foreign tables with local tables in the same query:

```sql
SELECT
    c.customer_id,
    c.customer_name,
    COUNT(o.order_id) AS order_count
FROM ext_sales.customers AS c
LEFT JOIN ext_sales.orders AS o
    ON o.customer_id = c.customer_id
GROUP BY c.customer_id, c.customer_name
ORDER BY order_count DESC;
```

Queries remain subject to permissions, connection state, network latency, and source database capacity. Foreign tables are not local data copies; each query reads data from the source according to the FDW execution plan.

## 5. Inspecting the Imported Structure

After importing, you need to verify which foreign tables were created and how columns were declared. You can use `psql` or system views.

### 5.1. Listing Foreign Tables

In `psql`, the following meta-command lists foreign tables:

```text
\det+ ext_sales.*
```

Or query `information_schema.foreign_tables`:

```sql
SELECT
    foreign_table_schema,
    foreign_table_name,
    foreign_server_name
FROM information_schema.foreign_tables
WHERE foreign_table_schema = 'ext_sales'
ORDER BY foreign_table_name;
```

### 5.2. Viewing Column Definitions

```sql
SELECT
    table_name,
    ordinal_position,
    column_name,
    data_type,
    udt_schema,
    udt_name,
    is_nullable
FROM information_schema.columns
WHERE table_schema = 'ext_sales'
ORDER BY table_name, ordinal_position;
```

The `information_schema.columns` view shows the column definitions currently stored in the target database. This is local foreign table metadata; it does not automatically query the source to compare against the latest schema. To check whether the source has changed, inspect metadata directly on the source database or import into a separate staging/inspection schema.

### 5.3. Verifying Data Accessibility

```sql
SELECT *
FROM ext_sales.orders
LIMIT 5;
```

A small query confirms that connectivity, the user mapping, remote privileges, and column mappings work. To inspect what part of the query is pushed down to the remote server, run:

```sql
EXPLAIN (VERBOSE, COSTS OFF)
SELECT order_id, total_amount
FROM ext_sales.orders
WHERE customer_id = 1001;
```

With `postgres_fdw`, the `Remote SQL` section in the verbose plan shows how the query is sent to the source database.

## 6. Managing Source Structure Changes

Schema import captures metadata at a point in time. Once foreign tables are created, the target database holds its own local column definitions. If an administrator adds, drops, renames, or alters a column's type on the source, foreign table definitions do not update automatically.

For example, suppose the source has:

```sql
CREATE TABLE public.orders (
    order_id bigint,
    customer_id bigint,
    order_date date,
    total_amount numeric(12, 2)
);
```

Later, the source adds a column:

```sql
ALTER TABLE public.orders
ADD COLUMN sales_channel text;
```

The existing foreign table `ext_sales.orders` does not automatically gain `sales_channel`. Querying the new column via the foreign table fails until the local definition is updated. Likewise, type changes, renames, or column drops on the source can break existing queries or return results that no longer match application expectations.

### 6.1. Classifying Changes

| Source Change | Potential Impact on Target Database | Handling Approach |
|---|---|---|
| Add column | Existing foreign table lacks the new column. | Update the foreign table or re-import into a staging schema before switching. |
| Drop column | Queries referencing the removed source column will fail. | Find and update consumers before dropping; then update local definitions. |
| Rename column | Old local column name no longer maps properly to the source. | Update column mapping or foreign table definition and fix affected queries. |
| Change data type | Local type may no longer be compatible with the source type. | Verify conversion compatibility, update local type, and test queries. |
| Add or drop table | Local foreign table list does not sync automatically. | Import new objects or remove obsolete ones after checking dependencies. |
| Rename table or schema | Foreign table continues pointing to the old source name. | Update FDW name mapping options or recreate the foreign table. |

Additive changes like adding columns are typically less disruptive than breaking changes like dropping or altering column types. However, even additive changes require updating metadata if applications want to read the new column.

### 6.2. Importing into a Staging Schema Before Switching

For major changes, create a temporary schema to import the new structure:

```sql
CREATE SCHEMA ext_sales_stage;

IMPORT FOREIGN SCHEMA public
    LIMIT TO (customers, orders, order_items)
    FROM SERVER sales_source
    INTO ext_sales_stage;
```

Then inspect the table and column list in `ext_sales_stage`, run test queries, diff against the active schema, and identify queries or views needing adjustment. This lets you prepare new metadata without immediately altering foreign tables actively used by applications.

Once the new structure is verified, update the application's stable access layer according to your rollout plan. For instance, create a local view with an explicit column list:

```sql
CREATE SCHEMA IF NOT EXISTS reporting;

CREATE OR REPLACE VIEW reporting.orders AS
SELECT
    order_id,
    customer_id,
    order_date,
    total_amount
FROM ext_sales_stage.orders;
```

Views decouple the names and data shapes used by applications from foreign table names. Always list columns explicitly rather than using `SELECT *`, so adding a column at the source does not unintentionally alter the view's output contract. If a change removes or alters a column that applications depend on, plan an appropriate migration or versioned view.

Drop old schemas or foreign tables only after confirming that no views, functions, reports, or applications depend on them. `DROP ... CASCADE` can delete dependent objects, so verify its scope before using it.

### 6.3. Updating Foreign Tables Manually

If a change is small and the exact metadata update is clear, use `ALTER FOREIGN TABLE`. For example, adding a column matching a newly added source column:

```sql
ALTER FOREIGN TABLE ext_sales.orders
ADD COLUMN sales_channel text;
```

If the source renames a column but you want to keep the local column name to avoid rewriting many queries, `postgres_fdw` supports the column-level `column_name` option. For example, mapping local `customer_id` to remote `buyer_id`:

```sql
ALTER FOREIGN TABLE ext_sales.orders
ALTER COLUMN customer_id
OPTIONS (ADD column_name 'buyer_id');
```

Similarly, the table-level `table_name` option maps a stable local name to a renamed source table:

```sql
ALTER FOREIGN TABLE ext_sales.orders
OPTIONS (ADD table_name 'sales_orders');
```

Use `ADD` only when the option does not already exist; if it already exists, use `SET`. Verify actual column names, table names, and data types on the source before altering mappings. Modifying local metadata does not alter structures on the source database.

When multiple columns change or breaking changes occur, importing into a new schema is usually easier to control than editing columns in place. If you must drop and recreate a foreign table, check dependent objects first; `DROP FOREIGN TABLE` may be rejected if dependencies exist, while `CASCADE` drops those dependent objects as well.

### 6.4. Establishing a Schema Management Process

A source change-management workflow can include these steps:

1. **Record changes from the source owner**: identify affected tables, columns, data types, nullability, and rollout timing.
2. **Read updated metadata**: inspect the source schema directly rather than assuming existing foreign tables reflect the latest state.
3. **Assess impact**: find queries, views, reports, and jobs referencing the affected tables or columns.
4. **Prepare updated definitions**: use `ALTER FOREIGN TABLE` for minor edits or import into a staging schema for larger changes.
5. **Verify privileges and data**: confirm user mappings, remote privileges, data types, and representative queries.
6. **Deploy in compatible order**: whenever possible, add new structures first, migrate consumers, and remove old structures afterward.
7. **Record version and rollout timestamp**: keep migration scripts, corresponding source schemas, and deployment results for traceability.

Treat schema changes as part of an integration contract between the source database team and data consumers. Advance notice of breaking changes gives the target team time to update and test.

## 7. Limitations to Understand When Importing

`IMPORT FOREIGN SCHEMA` speeds up creating initial foreign table definitions, but it does not replace full schema design in the target database.

- **Does not copy data**: data is fetched from the source at query time. If you need an independent local copy for analytics or archival, design ETL, logical replication, or an appropriate replication mechanism.
- **Does not sync schemas continuously**: adding or altering source columns does not update existing foreign tables.
- **Does not import all constraints**: with `postgres_fdw`, only `NOT NULL` is supported via the import option; other constraints require manual handling.
- **Does not replace access control**: privileges on the foreign server, schema, and foreign tables in the target database must still be configured, and the remote account must hold source permissions.
- **Does not guarantee all custom types are compatible**: user-defined types require matching types in the target database.
- **Does not eliminate network cost**: queries depend on network latency and source database availability. Project only needed columns, filter appropriately, and check execution plans.
- **Does not resolve semantic differences automatically**: collations, default expressions, generated expressions, and type handling can differ between two servers.

Additionally, `postgres_fdw` assumes foreign tables are updatable by default, though `INSERT`, `UPDATE`, `DELETE`, or `TRUNCATE` only succeed when the remote object and account permit them. For read-only integrations, grant read-only privileges at the source and consider setting `updatable 'false'` or `truncatable 'false'` at the appropriate level to prevent unintended writes.

## 8. Common Errors and Troubleshooting

| Symptom | Common Cause | How to Check or Fix |
|---|---|---|
| `permission denied for foreign server` | The role running the query or import lacks `USAGE` privilege on the foreign server. | Run `GRANT USAGE ON FOREIGN SERVER ...` for the appropriate role. |
| `user mapping not found` | No user mapping exists for the role executing the query. | Create a mapping for that role or design a shared mapping per security policy. |
| Remote connection refused | Wrong host, port, database, password, TLS config, or remote `pg_hba.conf` rule. | Verify server details, authentication, and connection permissions on the source host. |
| `permission denied` on source table | The account in the user mapping lacks privileges on the source schema or table. | Grant `USAGE` on the schema and required privileges on the source table or view. |
| `schema does not exist` or object not found | Wrong source schema name, wrong database, or remote role cannot see the object. | Verify the database in the foreign server, schema name, and metadata privileges on the source. |
| Missing data type or function error during import | Source uses a custom type or default/generated expression lacking a compatible counterpart at the target. | Create compatible types/functions or adjust import options after impact review. |
| Collation error | Source collation is missing or incompatible on the target server. | Compare collations across both servers; change `import_collate` only after verifying comparison semantics. |
| Object already exists error | Target schema already contains a foreign table with the same name. | Import into a staging schema or plan updates/drops of old objects after handling dependencies. |
| Query misses new columns | Foreign table was imported before the source added the column. | Update the definition with `ALTER FOREIGN TABLE` or re-import into a new schema. |
| Query fails after source renames/drops a column | Local metadata still maps to the old source name. | Update column mappings or foreign table definitions and update affected consumers. |

When troubleshooting, distinguish errors across three layers: connectivity and authentication, access privileges, and metadata compatibility. Checking layer by layer pinpoints the root cause without making unnecessary schema changes.

## 9. Operational Best Practices

- Import only the tables and views actually needed; prefer `LIMIT TO` when the integration list is known.
- Use a least-privilege remote role. Separate migration roles from application runtime roles if operations require it.
- Manage SQL for servers, user mappings, schemas, and imports in versioned migrations. Never store real passwords in repositories.
- Use a staging schema to stage major changes, diff metadata, and run representative queries before switching applications.
- Build local views as a stable interface layer when multiple applications consume the source data. List columns explicitly and evolve interfaces via controlled migrations.
- Track source schema changes alongside the source owner. Never treat a previously successful import as proof that current metadata remains compatible.
- Inspect query plans and network latency for large queries. `postgres_fdw` can push down many filters and joins to the source, but not every expression is shippable.
- Clean up obsolete foreign tables or schemas only after confirming zero dependencies and completed consumer cutovers.

## 10. Summary

`IMPORT FOREIGN SCHEMA` makes it fast to generate foreign tables from tables and views in a remote schema. With `postgres_fdw`, you can scope objects using `LIMIT TO` or `EXCEPT`, customize imported metadata with options, and query the source with standard SQL. Data stays on the source server, while foreign table definitions reside in the target database.

Because local definitions do not sync automatically when the source schema changes, structure management requires metadata checks, versioned migrations, staging schemas for major updates, and stable view layers for applications. This approach maintains a clear data contract between the source database and the integrated database.

## References

- [PostgreSQL — IMPORT FOREIGN SCHEMA](https://www.postgresql.org/docs/current/sql-importforeignschema.html)
- [PostgreSQL — postgres_fdw](https://www.postgresql.org/docs/current/postgres-fdw.html)
- [PostgreSQL — Foreign Data](https://www.postgresql.org/docs/current/ddl-foreign-data.html)
