# search_path, name resolution, and fully qualified object names

In PostgreSQL, a single database can contain multiple **schemas**, and each schema can hold tables, views, sequences, data types, functions, or other objects. Consequently, the statement `SELECT * FROM orders` does not unambiguously specify which table will be read if the database contains both `sales.orders` and `archive.orders`.

PostgreSQL uses the **`search_path`** parameter to determine the search order of schemas when an object name **is written without a schema prefix**. This mechanism keeps SQL shorter and more convenient, yet also causes subtle bugs: querying the wrong table, creating objects in an unintended schema, failing to find a table even though it exists, or an application invoking the wrong function when an untrusted schema is in the search path.

This lesson explains **schemas**, **name resolution**, `search_path`, the special schemas `pg_catalog` and `pg_temp`, how to write **schema-qualified names**, `USAGE`/`CREATE` privileges, configuring the search path at session/role/database levels, along with practical scenarios in Java/JDBC and PostgreSQL administration.

> Commands that create schemas/tables, alter `search_path`, and modify permissions in this lesson are intended only for **test databases** you are authorized to manage. Do not apply them directly in production before understanding the scope of changes and application dependencies.

## 1. What is a schema in PostgreSQL?

A **schema** is a namespace inside a PostgreSQL database. Objects with the same name can coexist if they belong to different schemas.

For example:

```text
PostgreSQL instance
└── database shopdb
    ├── schema sales
    │   ├── table orders
    │   ├── table customers
    │   └── function calculate_total(...)
    │
    ├── schema archive
    │   └── table orders
    │
    ├── schema public
    │   └── table products
    │
    └── schema pg_catalog
        ├── system views/tables
        ├── built-in functions
        └── built-in types
```

Thus, `sales.orders` and `archive.orders` are **two independent relations**, even though both end with the name `orders`. Users can distinguish them using qualified names:

```sql
SELECT * FROM sales.orders;
SELECT * FROM archive.orders;
```

A schema is **not a different database**. Schemas in the same database share one instance and can be queried/joined directly when privileges permit:

```sql
SELECT s.id, a.id
FROM sales.orders AS s
JOIN archive.orders AS a ON a.id = s.id;
```

This JOIN example illustrates syntax only, assuming both tables and the `id` column exist. Conversely, PostgreSQL **does not natively support directly joining a table located in another database** by typing `other_database.schema.table` as though all databases in an instance shared a namespace. That need requires a dedicated mechanism, such as a foreign data wrapper like `postgres_fdw` or application-level connections.

### What are schemas commonly used for?

- Grouping tables by business domain: `billing`, `sales`, `inventory`.
- Separating objects belonging to modules or extensions.
- Managing access permissions per group of objects.
- Allowing tables with the same name in different namespaces.
- Supporting certain multi-tenant models or schema versioning strategies, if the application has a clear design.

**A schema is not a complete security isolation mechanism by default.** To restrict access, you must configure proper privileges on the schema and each object, rather than merely naming them differently or changing `search_path`.

## 2. Two ways to write object names: unqualified and qualified

An object referenced in SQL can be written as:

| Form | Example | Meaning |
|---|---|---|
| **Unqualified name** | `orders` | PostgreSQL must look up the schema via `search_path` and SQL statement context. |
| **Schema-qualified name** | `sales.orders` | Explicitly specifies schema `sales` and object `orders`. |
| **Schema-qualified function name** | `sales.calculate_total(123)` | Calls the function in the specified schema, with additional parameter-signature resolution. |
| **Schema-qualified sequence name** | `sales.order_id_seq` | Explicitly identifies which schema the sequence belongs to. |
| **Schema-qualified data type name** | `sales.order_status` | Explicitly identifies the user-defined type in that schema. |

Example:

```sql
-- Depends on search_path:
SELECT * FROM orders;

-- Does not depend on search_path to identify the schema:
SELECT * FROM sales.orders;
```

Even when using a qualified name, PostgreSQL still checks **whether the schema and object exist and whether the role has sufficient privileges**. A qualified name does not bypass authentication or authorization.

### Qualified names are not required for every column

In the query:

```sql
SELECT o.id, o.created_at
FROM sales.orders AS o
WHERE o.status = 'PAID';
```

`sales.orders` is a schema-qualified relation name. `o.id` and `o.status` are columns resolved through **table alias `o` inside the query**, not via `search_path`.

Therefore, distinguish between:

- **Resolving tables/functions/types by schema**: affected by `search_path` when the schema is omitted.
- **Resolving columns by alias, FROM scope, and expressions**: governed by name scoping in the query; `search_path` is not a list of tables for looking up columns.

An ambiguous column error (`column reference ... is ambiguous`) in a JOIN generally needs to be fixed with aliases like `a.id` or `b.id`, not by changing `search_path`.

## 3. What is search_path?

`search_path` is a PostgreSQL configuration parameter whose value is **an ordered list of schemas to search** when an object name lacks a schema prefix.

Read the current value:

```sql
SHOW search_path;

SELECT current_setting('search_path') AS configured_path;
```

A common default value on a newly initialized PostgreSQL cluster is:

```text
"$user", public
```

Meaning:

1. `"$user"` is a special symbol referencing **a schema with the same name as the current role**, if that schema exists and can be used. It does **not** create the schema automatically.
2. `public` is the standard schema pre-created in many PostgreSQL databases.
3. PostgreSQL also has implicit lookup rules for **`pg_catalog`** and the temporary schema **`pg_temp`**, so `SHOW search_path` does not necessarily print the entire effective search order.

For example, role `report_user` might have a schema named `report_user`. If the schema exists and the role has appropriate permissions, `"$user"` can resolve to that schema. If not, PostgreSQL skips the unusable entry and continues evaluating subsequent valid schemas.

### search_path is not a list of every schema in the database

You may create `sales`, `billing`, and `analytics` while `SHOW search_path` remains `"$user", public`. In that situation:

```sql
SELECT * FROM sales.orders;
```

can still work with proper privileges, whereas:

```sql
SELECT * FROM orders;
```

may report that the table was not found, because `sales` is not used when resolving unqualified names.

**Changing `search_path` does not create or drop schemas, move tables to another schema, or grant access privileges.** It primarily alters how PostgreSQL **interprets names that do not specify a schema**.

## 4. Name resolution rules by search_path order

Suppose a session has:

```sql
SET search_path TO sales, archive, public;
```

With an unqualified table name:

```sql
SELECT * FROM orders;
```

PostgreSQL searches in logical order:

```text
Name to resolve: orders
             │
             ▼
pg_catalog? (if implicit search applies for the object type)
             │
             ▼
Does sales.orders exist and is it usable?
             ├── Yes ──► select sales.orders
             │
             └── No
                    │
                    ▼
Does archive.orders exist and is it usable?
             ├── Yes ──► select archive.orders
             │
             └── No
                    │
                    ▼
Does public.orders exist and is it usable?
             ├── Yes ──► select public.orders
             └── No  ──► relation not found error
```

This diagram omits certain special rules: the temporary schema `pg_temp` can be searched before regular schemas for **relations and data types**, while `pg_catalog` has its own implicit or explicit placement. Both exceptions are explained in later sections.

### "First schema wins" is only a simplification

For tables sharing the same name, picking the table in the **first matching schema** is quite intuitive. However, for **functions** or **operators**, PostgreSQL also considers **argument count, parameter types, overloading, and type coercion rules** to select the right candidate.

For instance, if functions share a name but have different signatures across multiple schemas, resolution is not simply "pick whatever function is in the first schema". Parameter compatibility and PostgreSQL's function resolution rules are evaluated as well.

This matters for **security**: placing a schema where untrusted users can create objects into `search_path` can influence function/operator resolution and alter SQL semantics.

## 5. Hands-on example: two schemas with same-named tables

Create two schemas in a **lab database**:

```sql
CREATE SCHEMA IF NOT EXISTS training_sales;
CREATE SCHEMA IF NOT EXISTS training_archive;
```

Create a table named `invoices` in each schema:

```sql
CREATE TABLE training_sales.invoices (
    id INTEGER PRIMARY KEY,
    customer_name TEXT NOT NULL,
    amount NUMERIC(12, 2) NOT NULL
);

CREATE TABLE training_archive.invoices (
    id INTEGER PRIMARY KEY,
    customer_name TEXT NOT NULL,
    amount NUMERIC(12, 2) NOT NULL
);

INSERT INTO training_sales.invoices(id, customer_name, amount)
VALUES
    (101, 'An', 125000),
    (102, 'Binh', 80000);

INSERT INTO training_archive.invoices(id, customer_name, amount)
VALUES
    (1, 'Cu', 50000);
```

**This example is intended for an empty lab database.** If the tables already exist, the `CREATE TABLE` statements will report errors; never casually run `DROP ... CASCADE` just to rerun on a database holding data you need to preserve.

### Step 1 — Put the sales schema first

```sql
SET search_path TO training_sales, training_archive, public;

SHOW search_path;

SELECT id, customer_name, amount
FROM invoices
ORDER BY id;
```

The `SELECT` uses the unqualified name `invoices`. It resolves to **`training_sales.invoices`** first; the expected result includes rows `101` and `102`.

### Step 2 — Swap the order

```sql
SET search_path TO training_archive, training_sales, public;

SELECT id, customer_name, amount
FROM invoices
ORDER BY id;
```

Without changing the text of the `SELECT` statement, it now returns row `id = 1` from **`training_archive.invoices`**.

**Lesson:** Two identical SQL strings can read **two completely different datasets** when connections have different `search_path` values. For financial, reporting, or multi-tenant applications, this silent divergence can be far worse than a "relation does not exist" error.

### Step 3 — Use qualified names to eliminate the dependency

```sql
SELECT * FROM training_sales.invoices ORDER BY id;
SELECT * FROM training_archive.invoices ORDER BY id;
```

Regardless of which schema `search_path` prioritizes, both statements unambiguously specify the relation to read.

### Step 4 — Clean up the session configuration after the experiment

```sql
RESET search_path;
```

`RESET` restores the session's configuration to the default **effective in that connection context**, which may include role/database/server settings rather than always returning `"$user", public`. This command does not delete tables or schemas.

## 6. How do current_schema() and current_schemas() differ from SHOW search_path?

`SHOW search_path` prints the **configured value**, which may include non-existent schemas, schemas lacking `USAGE` privilege, or an unresolved `"$user"` token.

PostgreSQL provides functions to observe the actual effective search path:

```sql
SELECT
    current_schema() AS default_schema,
    current_schemas(false) AS explicit_usable_path,
    current_schemas(true) AS path_including_implicit;
```

| Expression | Meaning |
|---|---|
| `SHOW search_path` | Session setting string, including special/non-existent entries. |
| `current_setting('search_path')` | Retrieves the value of the `search_path` GUC as text for use in SQL. |
| `current_schema()` | Current schema chosen as the default location for new unqualified objects. |
| `current_schemas(false)` | List of valid and usable schemas in the search path, excluding implicit schemas. |
| `current_schemas(true)` | Includes implicitly searched schemas such as `pg_catalog` and an active temporary schema when applicable. |

Example:

```sql
SET search_path TO schema_chua_ton_tai, training_sales, public;

SHOW search_path;

SELECT current_schema(), current_schemas(true);
```

`SHOW` can still print `schema_chua_ton_tai`, yet PostgreSQL skips non-existent schemas when actually resolving objects. Consequently, `current_schema()` can be `training_sales` if that schema exists and is usable.

**Do not confuse these two outputs.** If an application logs only the string from `SHOW search_path`, that log may not accurately reflect which schemas are actually searched.

## 7. Creating new objects: which schema does CREATE use?

`search_path` does not affect only `SELECT`. When creating certain objects **without specifying a schema**, PostgreSQL uses the **current schema** determined from the search path.

Suppose:

```sql
SET search_path TO training_sales, training_archive, public;

SELECT current_schema();
-- Expected: training_sales.

CREATE TABLE import_jobs (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

Because `CREATE TABLE` omits the schema, the new table is typically created inside **`training_sales`**, provided the role has `CREATE` privilege there:

```sql
SELECT to_regclass('training_sales.import_jobs') AS created_table;
```

To guarantee the target schema for the new table, write the qualified name:

```sql
CREATE TABLE training_archive.import_jobs (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

This is a different table from `training_sales.import_jobs`.

### The search path does not grant CREATE privilege

If a role has `USAGE` on `training_sales` but **lacks `CREATE`**, `CREATE TABLE import_jobs` can fail with a permission error even though `current_schema()` points to `training_sales`. PostgreSQL does not automatically "skip a schema lacking CREATE and search for the next writable schema" when creating objects.

Conversely, when no valid schema exists for creation:

```sql
SET search_path TO schema_chua_ton_tai;

-- Can cause error: no schema has been selected to create in.
CREATE TABLE should_not_be_created(id INTEGER);
```

Therefore, when encountering a table creation error, inspect **`current_schema()` and CREATE privileges**, not merely whether the table already exists.

### DDL migrations should specify the schema explicitly

A migration script using:

```sql
CREATE TABLE orders (...);
```

might accidentally create the table under the connecting role's schema instead of the application schema. For reliable migration pipelines, prefer:

```sql
CREATE TABLE app.orders (...);
```

Establish a clear naming convention and verify the target schema before deployment; the `...` in the example above is a placeholder for column definitions, not complete SQL.

## 8. pg_catalog: the system schema always worth watching

`pg_catalog` holds PostgreSQL's system tables/views, built-in functions, and built-in data types. PostgreSQL automatically includes `pg_catalog` in the lookup path when needed.

Key rules:

- If **`pg_catalog` is not listed** in `search_path`, it is normally **searched before** explicitly listed schemas for eligible object types.
- If **`pg_catalog` is explicitly listed**, it is searched **at the exact position** where you place it in the search path.

Example:

```sql
SET search_path TO training_sales, public;

SELECT current_schemas(true);
```

You can see `pg_catalog` appear even though `SHOW search_path` does not print it.

If you want an explicit, tightly controlled order:

```sql
SET search_path TO pg_catalog, training_sales, public;
```

**Never place a schema where untrusted users can create functions before `pg_catalog` in configurations running privileged code.** Certain cases of same-named functions or operators can lead to unexpected behavior, especially with overloading and implicit parameter casts.

### An example using a system object

```sql
SELECT oid, relname
FROM pg_catalog.pg_class
WHERE relname = 'invoices';
```

This uses the **qualified name `pg_catalog.pg_class`** to explicitly target the catalog relation without relying on `search_path` for the system table name. Columns `oid` and `relname` belong to the selected table.

## 9. pg_temp: why can a temporary table "shadow" a regular table?

When a session creates a **temporary table**, PostgreSQL uses a session-bound temporary schema, which can be referenced via the special alias **`pg_temp`**.

Important details:

- If the temporary schema exists and **`pg_temp` is not explicitly placed** in the search path, PostgreSQL can search the temporary schema **before** regular schemas when resolving **relations and data type names**.
- The temporary schema is **not implicitly searched for function and operator names**.
- Temporary tables are normally session-scoped; other sessions do not automatically see your temporary table through `pg_temp` on their connections.

Example in a lab session:

```sql
SET search_path TO training_sales, public;

CREATE TEMP TABLE invoices (
    source_note TEXT NOT NULL
);

INSERT INTO invoices(source_note)
VALUES ('Session temporary data');

-- Because the temp schema takes precedence for relations,
-- the unqualified name invoices can resolve to the temp table.
SELECT * FROM invoices;

-- Still explicitly reference the regular table when needed:
SELECT * FROM training_sales.invoices;

-- Explicitly reference the temporary table:
SELECT * FROM pg_temp.invoices;
```

After `CREATE TEMP TABLE`, `SELECT * FROM invoices` can return the `source_note` column instead of `id`, `customer_name`, `amount` from the regular table. If an application assumes `invoices` is always the regular table, the result will be surprising.

### When should pg_temp be placed last?

In security-sensitive contexts, especially **`SECURITY DEFINER` functions**, you can place `pg_temp` at the **end of the search path** to prevent temporary objects from taking undue precedence:

```sql
SET search_path TO pg_catalog, training_sales, pg_temp;
```

This is one component of secure search-path design, not the sole solution. **Fully qualifying table/function names and restricting CREATE privileges in trusted schemas** remain essential.

After finishing with the temporary table example:

```sql
DROP TABLE IF EXISTS pg_temp.invoices;
RESET search_path;
```

Run `DROP` only in the lab session that created that temporary table; never copy cleanup commands into an application connection running other work.

## 10. USAGE and CREATE privileges on schemas

`search_path` decides **where PostgreSQL looks for names**, while privileges decide **whether a role is allowed to access and manipulate objects**.

Two critical schema privileges:

| Schema privilege | Meaning |
|---|---|
| **USAGE** | Allows looking up/accessing objects inside the schema per applicable privilege rules. |
| **CREATE** | Allows creating certain objects inside the schema, subject to PostgreSQL semantics and constraints. |

**USAGE on a schema does not automatically grant SELECT on all tables.** Reading `training_sales.invoices` still requires `SELECT` privilege on the table or an appropriate grant mechanism.

Illustrative example on a lab database, executed by a role with administrative privileges:

```sql
-- Grant ability to use names inside the schema.
GRANT USAGE ON SCHEMA training_sales TO reporting_role;

-- Grant read privilege on a specific table.
GRANT SELECT ON TABLE training_sales.invoices TO reporting_role;
```

These statements assume `reporting_role` already exists. Never grant `CREATE` on business schemas to read-only accounts just to make `relation does not exist` errors go away.

### Checking existing permissions

```sql
SELECT
    current_user AS current_role,
    has_schema_privilege(current_user, 'training_sales', 'USAGE')
        AS can_use_schema,
    has_schema_privilege(current_user, 'training_sales', 'CREATE')
        AS can_create_in_schema;
```

When a schema exists but a role lacks `USAGE`, PostgreSQL can **skip that schema** during name resolution via `search_path`. Meanwhile, a qualified name like `training_sales.invoices` can report **permission denied for schema training_sales**. This is why two `SELECT` queries targeting the same business table can produce different error messages.

### Never assume public always grants CREATE to everyone

Default privileges on the `public` schema have changed across PostgreSQL versions: starting in PostgreSQL 15, in new databases, `CREATE` on `public` is no longer granted broadly to all roles by default as in many older versions. Upgraded databases or databases with customized privileges may still retain different settings.

When assessing security, **inspect the actual ACL**, rather than inferring from the name `public` or the version number:

```sql
SELECT
    has_schema_privilege('public', 'USAGE')  AS public_usage,
    has_schema_privilege('public', 'CREATE') AS public_create;
```

This example checks privileges for the **current role**. `GRANT`/`REVOKE` decisions should consider object owners, other roles, extensions, and the project's deployment policies.

## 11. search_path at SESSION, ROLE, and DATABASE scopes

A PostgreSQL session can receive its `search_path` value from multiple configuration layers. Understanding the scope of changes helps avoid surprises when one client has a different path from another.

### 11.1. SET search_path within a connection

```sql
SET search_path TO training_sales, public;

SELECT current_schema(), current_schemas(true);
```

This command changes **the current session**, without automatically altering sessions of other applications. Closing and reopening a connection may pick up settings from the role, database, or server instead of the value just `SET`.

End the test:

```sql
RESET search_path;
```

### 11.2. ALTER ROLE ... SET

An administrator with appropriate privileges can set a default value for **new sessions of a role**:

```sql
ALTER ROLE app_user
SET search_path TO training_sales, public;
```

This statement affects the default setting for eligible logins **afterward**; it does not immediately apply to connections already open in a pool.

### 11.3. ALTER DATABASE ... SET

Set the default configuration for new sessions connecting to a database:

```sql
ALTER DATABASE appdb
SET search_path TO training_sales, public;
```

Different roles connecting to `appdb` may be affected unless overridden by a higher-precedence setting. Consider the impact on multiple applications sharing a database.

### 11.4. ALTER ROLE ... IN DATABASE ... SET

When you want to target **one role inside one database**:

```sql
ALTER ROLE app_user IN DATABASE appdb
SET search_path TO training_sales, public;
```

This is often the more appropriate scope when the same role logs into multiple databases, or when a database serves multiple applications using different roles.

### Scope comparison table

| Configuration method | Scope | Do open connections update automatically? |
|---|---|---|
| `SET search_path` | Current session. | Only the session issuing the command changes. |
| `ALTER ROLE ... SET` | Default for new sessions of the role. | No. |
| `ALTER DATABASE ... SET` | Default for new sessions into the database. | No. |
| `ALTER ROLE ... IN DATABASE ... SET` | Default for the role-and-database combination. | No. |
| Server/startup configuration | Global default unless overridden by other layers. | Does not auto-update already-initialized sessions. |

Among role/database default sources, the **role-in-database** setting takes precedence over general role or database settings. An explicit `SET` in a session can override that session's defaults.

**Note:** `ALTER ROLE ... SET` is loaded into the session when the role logs in through supported mechanisms; simply calling `SET ROLE` mid-session does not automatically reapply all startup settings of the new role.

## 12. SET LOCAL search_path for a single transaction

Sometimes a task needs a specific schema without permanently altering a reused connection. PostgreSQL supports **`SET LOCAL`** inside a transaction:

```sql
BEGIN;

SET LOCAL search_path TO training_sales, public;

SELECT * FROM invoices ORDER BY id;

COMMIT;
```

A value set via `SET LOCAL` normally remains in effect only until the end of that transaction; after `COMMIT` or `ROLLBACK`, the session reverts to the value in effect prior to `SET LOCAL`.

| Command | Lifecycle |
|---|---|
| `SET search_path TO ...` | Session-level change; can persist across multiple transactions. |
| `SET LOCAL search_path TO ...` | Scoped to the currently executing transaction. |
| `RESET search_path` | Returns the parameter to the session's effective default configuration. |

Do not treat `SET LOCAL` outside a transaction block as a way to configure a request temporarily. This command is designed to apply within a transaction; outside an appropriate block, PostgreSQL may issue a warning and not produce the effect you expect.

### Why is SET LOCAL useful for applications?

In a connection pool, one physical connection can serve many requests:

```text
Connection #7
  ├── Request A: SET search_path = tenant_a
  ├── Return connection to pool
  └── Request B: SELECT * FROM orders
                    ▲
                    └── risk of accidentally reading tenant_a
```

When switching paths per transaction is required, `SET LOCAL` bounds the duration of the change. However, it **does not replace cross-tenant permission checks**, identifier protection, transaction boundaries, or pool connection-reset mechanisms.

## 13. JDBC, Spring, and connection pools

### 13.1. Each connection has its own session state

Java applications typically use HikariCP or a similar pool. A pool maintains multiple **physical connections**, each holding its own `search_path`.

Suppose:

```text
Connection A: search_path = training_sales, public
Connection B: search_path = training_archive, public

Identical SQL:
    SELECT * FROM invoices;

Connection A → training_sales.invoices
Connection B → training_archive.invoices
```

This is why many "query works sometimes and fails other times" bugs occur when paths are modified sporadically across requests.

### 13.2. Setting a default schema on connect

pgJDBC supports the **`currentSchema`** connection parameter to set a connection's search path. Example **lab connection string**:

```properties
spring.datasource.url=jdbc:postgresql://127.0.0.1:5432/appdb?currentSchema=training_sales,public
```

Meaning: the driver can establish the appropriate search path when creating connections. Never put sensitive credentials into URLs or commit secrets to a repository.

Another option is configuring pool connection initialization SQL, as supported by HikariCP/Spring versions:

```yaml
spring:
  datasource:
    hikari:
      connection-init-sql: "SET search_path TO training_sales, public"
```

Initialization config applies only when **new physical connections are created**, meaning existing connections are not automatically adjusted after editing a config file. Establish **one primary configuration source** so the driver, pool, and business SQL do not overwrite each other.

### 13.3. JDBC setSchema

JDBC provides the API:

```java
connection.setSchema("training_sales");
```

In pgJDBC, behavior regarding schema/search path must be understood for the specific driver and version. This API is useful when an application **manages an individual connection**, though you should not assume every pool automatically reverts all schema changes if code executes raw `SET search_path` SQL directly.

### 13.4. Leaking search_path state in a pool

Dangerous example:

```java
try (Connection connection = dataSource.getConnection();
     Statement statement = connection.createStatement()) {

    statement.execute("SET search_path TO training_archive, public");

    // Run a few queries...
}
```

Closing the logical connection in the code above usually means **returning the physical connection to the pool**, not necessarily destroying the PostgreSQL connection. If the pool is unaware of or does not reset session GUCs altered by SQL, subsequent requests may inherit this path.

Risk-reduction strategies:

1. Whenever possible, **write qualified schema names** in critical business SQL.
2. For an application with a fixed schema, configure it consistently at connection creation time.
3. When per-transaction changes are needed, use `SET LOCAL` with explicit transaction management.
4. Use a well-designed multi-tenant mechanism; never concatenate tenant names directly from requests into SQL.
5. Inspect the path **on the actual application connection** when troubleshooting, not solely from a DBA's `psql` window.

## 14. Double-quoted names and case-sensitivity rules

PostgreSQL folds **unquoted identifiers** to lowercase when parsing SQL:

```sql
-- Both forms refer to the same lowercase names.
SELECT * FROM Training_Sales.Invoices;
SELECT * FROM training_sales.invoices;
```

However, double-quoted identifiers preserve exact casing:

```sql
CREATE SCHEMA "SalesArea";

CREATE TABLE "SalesArea"."Orders" (
    "OrderID" BIGINT PRIMARY KEY,
    amount NUMERIC(12, 2)
);

SELECT "OrderID", amount
FROM "SalesArea"."Orders";
```

With the schema and table above, the statement:

```sql
SELECT * FROM salesarea.orders;
```

does **not** resolve to `"SalesArea"."Orders"` because the names were double-quoted and are case-sensitive.

### Double quotes differ from single quotes

| Syntax | Meaning |
|---|---|
| `"SalesArea"` | Identifier for schema name with uppercase letters preserved. |
| `'SalesArea'` | String literal, not schema identifier syntax in `FROM`. |
| `training_sales.invoices` | Two unquoted identifiers, normalized to lowercase. |
| `"odd.schema"."table.name"` | Dots are **inside the identifier** when quoted; not name-part separators. |

Naming schemas and tables in lowercase with underscores generally makes SQL, migrations, and drivers easier to manage. If mixed-case identifiers are already in use, be consistent with double quotes.

### search_path with schema names requiring quotes

```sql
SET search_path TO "SalesArea", public;

SHOW search_path;
```

This sets the search path to the schema strictly named `SalesArea`. If you accidentally write `salesarea` unquoted, PostgreSQL will look for a different lowercase schema.

## 15. Metadata: determining which table a name actually resolves to

Sometimes `SELECT * FROM invoices` succeeds, yet you suspect it is reading the wrong schema. PostgreSQL provides ways to inspect the **OID and visibility** of relations.

### 15.1. to_regclass()

`to_regclass(text)` resolves a relation name to a `regclass` OID if found; if not found, it normally returns `NULL` rather than throwing a not-found error.

```sql
SET search_path TO training_archive, training_sales, public;

SELECT
    to_regclass('invoices') AS resolved_unqualified,
    to_regclass('training_sales.invoices') AS sales_relation,
    to_regclass('training_archive.invoices') AS archive_relation;
```

A `regclass` value may **display as a short name or a qualified name** depending on the relation's visibility in the search path. When you need a more stable identifier, retrieve the OID and join the catalogs.

### 15.2. Joining pg_class with pg_namespace

```sql
SELECT
    c.oid,
    n.nspname AS schema_name,
    c.relname AS relation_name,
    c.relkind
FROM pg_catalog.pg_class AS c
JOIN pg_catalog.pg_namespace AS n
  ON n.oid = c.relnamespace
WHERE c.oid = to_regclass('invoices');
```

The result shows **the actual schema of the relation resolved in the current session**. In the catalog, multiple distinct OIDs with the same `relname='invoices'` can exist across different `relnamespace` values.

### 15.3. pg_table_is_visible()

```sql
SELECT
    pg_catalog.pg_table_is_visible(
        'training_sales.invoices'::regclass
    ) AS sales_is_visible,
    pg_catalog.pg_table_is_visible(
        'training_archive.invoices'::regclass
    ) AS archive_is_visible;
```

A relation is considered visible if it can be referenced solely by its unqualified name in the current context under resolution rules. When two tables share a name, the earlier schema can shadow the later schema.

### 15.4. Finding all relations with the same name

```sql
SELECT
    n.nspname AS schema_name,
    c.relname,
    c.relkind
FROM pg_catalog.pg_class AS c
JOIN pg_catalog.pg_namespace AS n
  ON n.oid = c.relnamespace
WHERE c.relname = 'invoices'
ORDER BY n.nspname;
```

This query can show relations across multiple schemas, including schemas outside the current `search_path`, depending on metadata read permissions. To distinguish tables, views, materialized views, and other relation kinds, check `relkind` and PostgreSQL catalog documentation.

## 16. psql tools for inspecting schemas and relations

`psql` supports helpful **meta-commands**:

```text
\dn
\dt
\dt *.*
\d training_sales.invoices
\d training_archive.invoices
```

Typical meanings:

- `\dn`: list schemas.
- `\dt`: list tables per `psql` pattern/visibility rules.
- `\dt *.*`: expand scope to list tables across multiple schemas.
- `\d training_sales.invoices`: inspect structure of the specified table using its qualified name.

These are **commands specific to `psql`**, not SQL sent over JDBC. Never pass `\dn` or `\dt` verbatim into a `PreparedStatement`.

### Reading the current schema via SQL

```sql
SELECT current_database() AS database_name,
       current_user AS role_name,
       current_schema() AS current_schema_name;

SHOW search_path;
```

The three pieces of information **database, role, and search path** are crucial when investigating why two applications running the same query against PostgreSQL get different results.

## 17. Function, type, and operator names also relate to search_path

Focusing solely on tables is not enough. PostgreSQL uses namespaces for many other object kinds, though their resolution rules **are not completely identical**.

### Functions in schemas

Example:

```sql
CREATE FUNCTION training_sales.apply_tax(p_amount NUMERIC)
RETURNS NUMERIC
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT p_amount * 1.1
$$;

-- Qualified name:
SELECT training_sales.apply_tax(100);
```

If called as:

```sql
SELECT apply_tax(100);
```

PostgreSQL must select the schema and function signature matching the argument types via `search_path` and function resolution rules.

### Overloading can make outcomes non-obvious

PostgreSQL supports **multiple functions with the same name but different parameter type lists**. When passing untyped literals or relying on implicit casts, the resolver weighs candidates; schema order is part of the process, not the whole story.

Therefore, when stable behavior is required:

- Call functions with **`schema.function_name(...)`** when collision risk exists.
- Use explicit parameter types when overloading matters.
- Never add untrusted schemas to the search path of high-privilege programs.

### User-defined data types

```sql
CREATE TYPE training_sales.invoice_state AS ENUM (
    'DRAFT',
    'ISSUED',
    'PAID'
);

CREATE TABLE training_sales.invoice_state_log (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    state training_sales.invoice_state NOT NULL
);
```

Qualified type names avoid search-path dependencies when a same-named type exists in another schema.

### Schema-qualified operators

PostgreSQL also allows schema-qualifying operators via the special syntax `OPERATOR(schema.operator)` when needed. Syntax example:

```sql
SELECT 1 OPERATOR(pg_catalog.+) 2;
```

You cannot assume `schema.+` works like a table name: **operators have their own resolution syntax**.

## 18. search_path and security: why schemas in the search path must be trusted

When PostgreSQL searches for unqualified names, it evaluates objects residing in the schemas of `search_path`. If a schema allows an **untrusted role** to create objects, that role could create objects with the same name or signature to interfere with another user's SQL queries.

The risk escalates sharply when a **`SECURITY DEFINER`** function runs with the owner's privileges while using unqualified object names. In that case, a search path controlled by the caller or environment can cause the function to resolve the wrong object.

### Illustrating a dangerous scenario

Suppose a high-privilege function executes:

```sql
-- Example illustrating an insecure design, not code
-- that should be deployed in practice.
SELECT COUNT(*) FROM accounts;
```

If `accounts` lacks an explicit schema and the search path prioritizes a schema where another party can create objects, the name can resolve to an unintended object. For functions, types, or operators, inserting same-named objects can even alter logic under candidate-selection rules.

### A more cautious way to write SECURITY DEFINER

Inside a schema with a trusted owner:

```sql
-- Assumes schema security_admin and table accounts are
-- managed by a trusted owner and permissions have been audited.
CREATE FUNCTION security_admin.account_count()
RETURNS BIGINT
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, security_admin, pg_temp
AS $$
DECLARE
    v_count BIGINT;
BEGIN
    SELECT COUNT(*) INTO v_count
    FROM security_admin.accounts;

    RETURN v_count;
END;
$$;
```

This is a **conditional design pattern**: schema `security_admin` and table `accounts` must exist, and ownership plus `EXECUTE` privileges must be controlled. The approach demonstrates several principles:

1. The function's search path is **explicitly pinned**.
2. `pg_catalog` is prioritized for built-in objects.
3. Only **trusted** schemas appear in the search path.
4. `pg_temp` is placed last rather than searched ahead of tables in trusted schemas.
5. Critical tables use explicit **`security_admin.accounts`** names.
6. Schema object creation privileges and function execution privileges must be controlled.

**Never think simply adding `SET search_path` makes a function automatically safe.** If a listed schema allows an attacker to create functions/types/operators, or if the function executes dynamic SQL without proper quoting, risks remain.

### Checking actual public privileges

In older databases or those with modified ACLs, `public` may allow many roles to create objects. When a security-sensitive function includes `public` in its search path, name-shadowing risks must be evaluated.

On PostgreSQL 15+ with new databases, default `CREATE` privileges on `public` are more restricted than in many older versions; **never guess from version alone and skip ACL inspection**. Running `REVOKE CREATE` in production can affect existing applications and extensions, so proper migration planning and replacement grants are needed.

## 19. Schema-based multi-tenancy: benefits and risks

A multi-tenant model may use:

```text
database appdb
├── tenant_alpha
│   ├── orders
│   └── customers
├── tenant_beta
│   ├── orders
│   └── customers
└── shared
    └── product_catalog
```

An application can switch `search_path` per tenant to reuse the same SQL:

```sql
SET search_path TO tenant_alpha, shared, pg_catalog;

SELECT * FROM orders;
```

However, this model requires **tight engineering**:

- Tenants must be **authenticated and mapped** to authorized schemas, never taken directly from raw request strings.
- Search paths must be scoped properly per **transaction or connection** and must never leak to other requests.
- Accessing roles need appropriate permissions; if every tenant is granted access to every schema, `search_path` is **not a security barrier**.
- Migrations must be applied across the corresponding schemas and version-managed.
- Critical queries must avoid unintended cross-tenant object references.
- `SECURITY DEFINER` functions and dynamic SQL must be audited separately.

### Never concatenate schema names from untrusted input

Dangerous pattern:

```java
// Unsafe: do not concatenate arbitrary schema names from requests.
String sql = "SET search_path TO " + tenantFromRequest;
statement.execute(sql);
```

A schema name is a **SQL identifier**, and value placeholders like `SELECT ... WHERE id = ?` cannot directly substitute arbitrary identifier positions in SQL. Look up the tenant in an **allowlisted schema mapping** and use valid identifier quoting.

In PL/pgSQL, if you truly must construct dynamic SQL from a **validated** schema name, you can use `format('%I', identifier)` to quote identifiers instead of arbitrary string concatenation:

```sql
-- Illustrates PostgreSQL identifier quoting.
SELECT format('%I.%I', 'tenant_alpha', 'orders')
       AS qualified_relation_name;
```

`format('%I', ...)` protects identifier syntax; **it does not verify whether a role has access or whether a tenant is valid**. Permission validation and tenant mapping remain the application's responsibility.

### Alternative designs: qualified names or role separation

In many applications, passing explicit `schema.table` (from an allowlisted schema) or using dedicated roles/connections can reduce session leakage risks. In exchange, SQL and permissions must be carefully managed. There is no single approach suited to every tenancy model.

## 20. search_path and objects resolved at an earlier time

When PostgreSQL processes SQL, name resolution occurs during stages such as parse analysis, planning, or execution depending on the object type and mechanism.

### Views and object dependencies

A view created via:

```sql
SET search_path TO training_sales, public;

CREATE VIEW training_sales.invoice_ids AS
SELECT id FROM invoices;
```

When defining the view, PostgreSQL resolves the **actual source object** and records the corresponding dependency. Afterward, changing the `search_path` of a user querying the view **does not automatically switch** the view's source from `training_sales.invoices` to `training_archive.invoices`.

Thus, when changing `search_path` after migrations, distinguish between:

- Newly submitted SQL with unqualified names: may resolve according to the new path.
- Stored views/constraints/objects dependent on an object's OID: do not automatically rebind to same-named objects in another schema.
- Functions containing SQL (especially PL/pgSQL or dynamic SQL): resolution context and statement preparation timing must be evaluated individually, rather than applying a single rule to all functions.

### Prepared statements and caches

Applications may use prepared statements or server-side plan caches. Relation names can be resolved during parse/prepare; PostgreSQL also has re-parse/re-plan mechanisms for situations such as `search_path` changes between executions. **Do not rely on plan caches to retain or switch schemas as desired**.

If an application varies `search_path` per request, testing must cover **prepared statements, connection pools, transactions, and same-named schemas**. A simpler solution is usually to avoid arbitrary dynamic paths for SQL statements requiring high determinism.

### Sequences and regclass

PostgreSQL has the special `regclass` type representing the OID of a relation/sequence. For example:

```sql
SELECT to_regclass('training_sales.invoices');
```

In expressions such as `nextval('schema.sequence_name'::regclass)`, the name can be resolved to an OID early under `regclass` semantics, so you cannot assume changing `search_path` will redirect stored sequence references to a same-named sequence in another schema.

When designing migrations, understand the difference between **runtime name resolution** and **OID-bound stored dependencies**.

## 21. Common errors and how to diagnose them

### 21.1. relation does not exist — SQLSTATE 42P01

Example:

```sql
SELECT * FROM invoices;
```

If the real table lives at `training_sales.invoices` but that schema is missing from the path, PostgreSQL reports that the relation does not exist for the **unqualified name**.

How to check:

```sql
SHOW search_path;
SELECT current_schema(), current_schemas(true);
SELECT to_regclass('training_sales.invoices');
SELECT to_regclass('invoices');
```

If the qualified name resolves while the unqualified name does not, this points to `search_path`/privileges rather than lost data.

### 21.2. permission denied for schema or table

A qualified name may report missing `USAGE` privilege on the schema; or the table is found but lacks `SELECT`, `INSERT`, or `UPDATE` privileges on the table.

Check further:

```sql
SELECT
    has_schema_privilege('training_sales', 'USAGE')
        AS schema_usage,
    has_schema_privilege('training_sales', 'CREATE')
        AS schema_create;
```

To check table privileges:

```sql
SELECT has_table_privilege(
    'training_sales.invoices',
    'SELECT'
) AS may_select_invoices;
```

Grant only the **minimum required privileges**; never fix every error by turning the application account into a superuser.

### 21.3. Table not visible after CREATE TABLE

The DDL may have created the table in a different schema because the migration connection's `search_path` differed from expectations.

Inspect:

```sql
SELECT current_schema(), current_schemas(true);

SELECT n.nspname, c.relname
FROM pg_catalog.pg_class AS c
JOIN pg_catalog.pg_namespace AS n
  ON n.oid = c.relnamespace
WHERE c.relname = 'import_jobs';
```

Never recreate a duplicate table before verifying which schema holds the original object and what data it contains.

### 21.4. Same SQL returns different row counts across two connections

Check:

```sql
SELECT
    current_database(),
    session_user,
    current_user,
    current_schema(),
    current_schemas(true);
```

Different roles, search paths, or databases can cause unqualified SQL to target different data. If the application uses a pool, capture this information **from the exact connection executing the query**, along with appropriate connection/request IDs.

### 21.5. Wrong function called or ambiguous function

Same-named functions across multiple schemas, overloading, and ambiguous argument types can cause PostgreSQL to choose a different candidate or report an ambiguous function error.

The usual fix is to **schema-qualify the function** and **explicitly cast arguments** where appropriate, while auditing untrusted schemas present in the search path.

### 21.6. Temporary table shadowing a regular table

If the session ran `CREATE TEMP TABLE invoices`, the name `invoices` can resolve to the temp schema. Check `current_schemas(true)` and `to_regclass('invoices')`, and use `training_sales.invoices` when you want the regular table.

### 21.7. Updated ALTER ROLE but application behavior hasn't changed

`ALTER ROLE ... SET search_path` affects **newly opened** sessions. A pool holding old physical connections can keep using the original value or a value set by the application.

To align everything, plan connection recycling or baseline session initialization rather than merely updating role metadata.

### 21.8. Migration succeeds locally for developer but fails in CI

Differences in database role, schema, privileges, `search_path` settings, or startup SQL can lead to "table not found" / "permission denied" errors.

Log at minimum `current_database()`, `current_user`, `current_schemas(true)`, and the migration revision; prefer schema-qualified DDL and explicit privilege grants.

## 22. Safe search_path design and operations workflow

For multi-schema projects, proceed in order:

1. **Define ownership per schema**: who has `CREATE`, who has `USAGE`, which objects are exposed to the application.
2. **Choose naming conventions**: lowercase schemas/tables, consistent names, avoiding unnecessary object name collisions.
3. **Establish when to use qualified names**: migrations, grants, core business tables, privileged functions, and SQL at risk of name conflicts.
4. **Standardize the source of search_path**: server, database, role, driver, or connection pool configuration; avoid uncoordinated overrides across layers.
5. **Design transaction boundaries**: if changing paths per task, use `SET LOCAL` with clear commit/rollback boundaries.
6. **Audit security**: which schemas in the path let others create objects? Do `SECURITY DEFINER` functions have trusted paths?
7. **Track changes**: the same SQL statement can resolve differently if schemas or `search_path` ordering changes.
8. **Verify with application connections**: never treat a single DBA session as sufficient proof.
9. **Test with duplicate-named schemas** in staging if production uses multiple schemas or multi-tenancy.
10. **Store configuration alongside migrations/IaC** where appropriate to prevent environment drift.

A practical guideline:

| Context | Preferred approach |
|---|---|
| Single application with a fixed schema | Set a stable search path at connection creation, or qualify critical relations. |
| Schema migrations | Explicitly write `schema.object`, verify database/role before DDL. |
| Multiple modules sharing a database | Use separate schemas for namespaces, qualified names across module boundaries. |
| SECURITY DEFINER functions | Fixed search path, trusted schemas, `pg_temp` last, critical objects fully qualified. |
| Schema-based multi-tenancy | Verified tenant mapping, strict connection/transaction management, separate access grants; never treat `search_path` as security control. |
| Troubleshooting object-not-found errors | Compare qualified names, `current_schemas(true)`, schema/table privileges, and catalog metadata. |

## 23. Hands-on exercises

### Exercise 1 — Resolving two tables with the same name

Given the example tables `training_sales.invoices` and `training_archive.invoices`:

```sql
SET search_path TO training_archive, training_sales, public;
SELECT * FROM invoices;
```

Identify which table is read and why. Switch to `SET search_path TO training_sales, training_archive, public` and predict the result without altering the `SELECT` statement.

### Exercise 2 — Inspecting the effective search path

Suppose:

```sql
SET search_path TO schema_missing, training_sales, public;
```

Explain the differences between `SHOW search_path`, `current_schema()`, and `current_schemas(true)`. Why can a non-existent schema appear in the config string yet not participate in name resolution?

### Exercise 3 — Where does CREATE TABLE create the table?

With `search_path = training_archive, training_sales, public`, the role has `USAGE` and `CREATE` on both schemas. State where `CREATE TABLE new_events(id INT)` creates the table. Write a SQL statement to create the same table **guaranteed** to reside in `training_sales`.

Then analyze what happens if the role has `USAGE` but lacks `CREATE` on the first schema.

### Exercise 4 — Temporary tables and pg_temp

In a lab session containing `training_sales.invoices`, run:

```sql
SET search_path TO training_sales, public;
CREATE TEMP TABLE invoices(note TEXT);
SELECT * FROM invoices;
```

Which table does the `SELECT` target? Write a query to read the regular table despite the temporary table, and explain why you should not assume the temp schema is searched for function/operator names.

### Exercise 5 — Privileges and qualified names

Role `reporting_role` has `SELECT` privilege on `training_sales.invoices` but lacks `USAGE` on schema `training_sales`.

Explain what issues can occur when executing:

```sql
SELECT * FROM invoices;
SELECT * FROM training_sales.invoices;
```

Write the appropriate grant statement following least privilege.

### Exercise 6 — SET LOCAL and connection pools

A web application uses 20 physical connections. Request A runs `SET search_path TO tenant_alpha`, runs queries, and returns the connection to the pool. Request B later borrows that exact connection.

Identify the risk, the role of `SET LOCAL` inside a transaction, and what **SET LOCAL does not automatically solve**, especially regarding tenant authentication and schema privileges.

### Exercise 7 — Distinguishing role/database settings

A database has a general config, a role has its own `search_path` setting, and an `ALTER ROLE ... IN DATABASE ... SET` setting exists for that role.

Describe the scope of each configuration and explain why existing connections do not auto-update after `ALTER ROLE`.

### Exercise 8 — Diagnosing table not found

An application reports `SQLSTATE 42P01: relation "orders" does not exist`. The DBA knows `sales.orders` exists. Build a diagnostic checklist covering database, role, `search_path`, `current_schemas(true)`, `USAGE`/`SELECT` privileges, and querying `to_regclass('sales.orders')`.

### Exercise 9 — SECURITY DEFINER

Why is a `SECURITY DEFINER` function using unqualified table and function names in a search path containing a schema where other users have `CREATE` dangerous? Propose a safe `SET search_path` pattern and explain why `pg_temp` is placed last.

### Exercise 10 — Double-quoted names

A schema was created named `"SalesArea"`, containing table `"Orders"`. Write a SQL query to read the table with the proper qualified name. Explain why `salesarea.orders` is not equivalent.

## Conclusion

**`search_path` determines the order in which PostgreSQL looks up object names that omit a schema prefix.** When a database contains multiple schemas, identical SQL statements can read or modify different objects if sessions have different `search_path` values. When creating objects without specifying a schema, **`current_schema()`** reveals where PostgreSQL intends to place the object; `USAGE` and `CREATE` privileges are still checked independently.

To troubleshoot accurately, combine **`SHOW search_path`, `current_schemas(true)`, `to_regclass()`, `pg_catalog`, and access privileges**. Write **`schema.object`** names whenever determinism matters, especially in migrations, critical business SQL, and high-privilege functions. Keep in mind that **`pg_catalog`** has its own implicit lookup behavior and **`pg_temp`** can shadow regular tables.

In Java applications and multi-tenant systems, pay close attention to **connection pool session state**, bound changes to transactions where appropriate, and avoid putting schema names from requests directly into SQL. **`search_path` is a name-resolution mechanism, not an authorization boundary.** Understanding that distinction is foundational for organizing PostgreSQL data across schemas, deploying safely, and reliably diagnosing object-naming issues.
