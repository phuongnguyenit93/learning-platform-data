# Help Commands, Listing Objects, and Describing Structure in psql

When you first connect to a PostgreSQL server, you often do not yet know which schemas exist in the current database, where tables reside, how column names are declared, or which table a foreign key references. You may also forget the syntax of a SQL command such as `ALTER TABLE` or need to inspect a view, index, or function before modifying an application.

**`psql`** is the official command-line client, very useful for exploring PostgreSQL structure. In addition to sending SQL to the server, psql provides a system of **meta-commands** starting with a backslash `\`. Commands such as `\?`, `\h`, `\l`, `\dn`, `\dt`, `\d`, and `\d+` help you get syntax help, list objects, and read object definitions right in the terminal.

This lesson shows how to use them to **go from an unfamiliar connection to a map of objects in the database**, filter by schema, identify privileges, and avoid common pitfalls. The content focuses on PostgreSQL and **commands run inside psql**, without confusing them with SQL statements or other shell programs.

## 1. Distinguishing three types of commands when working with PostgreSQL

A learner can often run `SELECT` yet not understand why `\dt` fails in a JDBC client, or conversely type `psql -U ...` directly inside a SQL prompt.

Separate the three layers:

| Type | Where does it run? | Example | Role |
|---|---|---|---|
| **OS / shell command** | Operating system terminal | `psql -h localhost -U app_user -d appdb` | Launch the psql program and connect |
| **SQL** | Sent to the PostgreSQL server | `SELECT current_database();` | Query or modify data/objects |
| **psql meta-command** | Processed by psql on the client | `\dt`, `\d public.orders` | Help, client control, metadata queries |

Example in a terminal:

~~~bash
psql -h localhost -p 5432 -U app_user -d appdb
~~~

After connecting, you may see a prompt:

~~~text
appdb=>
~~~

Type SQL:

~~~sql
SELECT current_database();
~~~

Or a meta-command:

~~~text
\dt
~~~

Regular **SQL** ends with a semicolon `;`. A **meta-command** starts with `\` and normally ends at the end of the input line, **without needing a semicolon**. Writing `\dt;` is not the standard way to terminate a meta-command; the semicolon may be interpreted as part of an argument.

If you use DBeaver, pgAdmin, a cloud SQL editor, or JDBC, check whether the tool supports psql meta-commands. Many tools send SQL directly and **do not accept `\d` or `\?` as SQL**.

### 1.1. psql commands do not create a "new SQL language"

Commands like `\d`, `\dt`, or `\df` are **convenient client interfaces** in psql for reading the PostgreSQL catalog. They may execute metadata queries behind the scenes, but you cannot assume the server understands backslash syntax directly.

To automate via JDBC or build tools supporting multiple SQL clients, use `pg_catalog`, `information_schema`, or PostgreSQL JDBC `DatabaseMetaData`, rather than sending literal `\dt`.

## 2. Connecting to the right server and database

A common invocation from the shell:

~~~bash
psql -h localhost -p 5432 -U app_user -d appdb
~~~

Option breakdown:

| Option | Meaning |
|---|---|
| `-h` | Server hostname or address |
| `-p` | Connection port; 5432 is the common default |
| `-U` | Login role name |
| `-d` | Database to connect to |
| `-f` | Read commands from a script file |
| `-c` | Run a command string or suitable meta-command and exit |
| `-X` | Do not read the user's psql startup file; useful for reproducible script runs |
| `-v` | Set a psql variable, e.g., to control stopping on error |

Do not put real passwords directly in terminal commands or commit them to a repository. Authentication can use interactive prompts, a protected password file, environment variables per deployment policy, or a secret management service.

### 2.1. Confirming connection details with \conninfo

Right after entering psql, type:

~~~text
\conninfo
~~~

This displays current connection details such as database, user, host, port, and TLS when applicable. This is a simple step to avoid accidentally operating on production instead of a development environment.

Cross-check with SQL:

~~~sql
SELECT
    current_database() AS database_name,
    current_user AS active_role,
    session_user AS session_role,
    current_schema() AS current_schema,
    inet_server_addr() AS server_address,
    inet_server_port() AS server_port;
~~~

`inet_server_addr()` may return `NULL` when connected via a Unix-domain socket; this is not evidence of a broken connection.

### 2.2. Switching databases in psql

~~~text
\c appdb
~~~

Or specify database, user, and host if needed:

~~~text
\connect appdb app_user localhost 5432
~~~

`\c` is shorthand for `\connect`. When switching databases, psql opens a connection to the target database according to its connection rules.

In PostgreSQL, **schemas live inside a database**. Changing databases is different from merely switching schemas. A normal PostgreSQL session cannot use three-part names to directly JOIN tables across two different databases like some other RDBMSs.

### 2.3. Exiting psql

~~~text
\q
~~~

This is a meta-command to exit the client, not a `QUIT;` SQL statement sent to the server.

## 3. Two most important help tools: \? and \h

When you forget syntax, use the built-in help system rather than guessing.

### 3.1. \? — psql meta-command help

~~~text
\?
~~~

This command displays psql control commands with short descriptions. You can find command groups for:

- Connection and database access.
- Output formatting.
- Listing and describing objects.
- Input/output, scripts, variables, and helper tools.
- Managing the query buffer and interactive loop control.

This is **help for the psql program**. If you want to know which filter patterns `\dt` accepts or how to toggle expanded output, start with `\?`.

In newer psql versions, the help system may support additional topics like `\? commands` or `\? options`. That capability depends on the client version; **plain `\?` is the most compatible starting point**.

### 3.2. \h — SQL syntax help

~~~text
\h
~~~

`\h` (*help*) displays the list of SQL topics for which psql has syntax documentation.

To view a specific statement:

~~~text
\h SELECT
\h CREATE TABLE
\h ALTER TABLE
\h CREATE INDEX
\h INSERT
\h UPDATE
\h GRANT
\h VACUUM
~~~

For example, `\h CREATE TABLE` provides a broad syntax synopsis that helps identify column definitions, constraints, and table options.

`\h` does not list the structure of tables already created in the database; it is a **SQL syntax reference** for the running psql version.

### 3.3. When to use \? and when to use \h?

| You are asking... | Use command |
|---|---|
| How do I list tables in psql? | `\?` |
| PostgreSQL syntax for creating a table? | `\h CREATE TABLE` |
| Is there a meta-command to describe an index? | `\?`, then `\d index_name` |
| Syntax for `INSERT ... ON CONFLICT`? | `\h INSERT` |
| How do I format results vertically? | `\?`, check formatting group, then `\x` |
| Which tables exist in the current schema? | `\dt` (not `\h`) |

### 3.4. Do not confuse SQL help with runtime state

Syntax from `\h ALTER TABLE` does not tell you how long a DDL statement will take, whether it will wait on locks, or how much disk space it will use. Help ensures **valid syntax**; assessing runtime impact requires checking the actual table, data volume, operation type, and PostgreSQL version.

## 4. Understanding the PostgreSQL object hierarchy before listing

PostgreSQL organizes data across multiple levels:

~~~text
PostgreSQL server / cluster
|
+-- Database: appdb
|     |
|     +-- Schema: public
|     |     +-- Table: customers
|     |     +-- Table: orders
|     |     +-- View: recent_orders
|     |
|     +-- Schema: accounting
|           +-- Table: invoices
|           +-- Sequence: invoice_number_seq
|           +-- Function: calculate_tax(...)
|
+-- Database: analyticsdb
      |
      +-- Schema: mart
            +-- Materialized view: daily_revenue
~~~

Key points to remember:

- `\l` lists **databases** in the cluster that the account is allowed to see.
- `\dn` lists **schemas** in the current database.
- `\dt` lists **tables** according to pattern and visibility rules.
- `\dv` lists **views**.
- `\dm` lists **materialized views**.
- `\di` lists **indexes**.
- `\ds` lists **sequences**.
- `\df` lists **functions/procedures** according to options and version capabilities.

A single database can have multiple schemas containing tables of the same name, such as `public.orders` and `archive.orders`. Therefore, when describing precisely, **always write the full schema.table name**.

## 5. Preparing a practice setup in a dedicated schema

To see how listing commands work, let's create a few sample objects. This section only needs to be run **once** in a test PostgreSQL database where you have `CREATE` privilege on the database/schema.

The examples target modern PostgreSQL (PostgreSQL 12+). If a schema or objects with the same names already exist, use different names rather than dropping data arbitrarily.

### 5.1. Creating the schema and tables

~~~sql
CREATE SCHEMA IF NOT EXISTS psql_lab;

CREATE TABLE psql_lab.customers (
    customer_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE psql_lab.orders (
    order_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id BIGINT NOT NULL
        REFERENCES psql_lab.customers(customer_id),
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'paid', 'cancelled')),
    amount NUMERIC(12, 2) NOT NULL CHECK (amount >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_psql_lab_orders_customer_created
ON psql_lab.orders (customer_id, created_at DESC);
~~~

Components to note:

- Two tables: `customers` and `orders`.
- Auto-generated identity columns using `IDENTITY`.
- `PRIMARY KEY`, `UNIQUE`, `CHECK`, and `FOREIGN KEY` constraints.
- A composite index on `customer_id`, `created_at`.

In PostgreSQL, identity columns are backed by sequences. Thus, sequence inspection commands may show objects associated with identity columns.

### 5.2. Creating a view, materialized view, and function

~~~sql
CREATE VIEW psql_lab.v_active_customers AS
SELECT
    customer_id,
    customer_name,
    email
FROM psql_lab.customers
WHERE is_active = TRUE;

CREATE MATERIALIZED VIEW psql_lab.mv_order_totals AS
SELECT
    customer_id,
    COUNT(*) AS order_count,
    SUM(amount) AS total_amount
FROM psql_lab.orders
GROUP BY customer_id;

CREATE FUNCTION psql_lab.normalize_email(p_email TEXT)
RETURNS TEXT
LANGUAGE SQL
IMMUTABLE
STRICT
AS $$
    SELECT lower(btrim(p_email));
$$;
~~~

A **view** describes a named query; it does not store full results on its own like a physical table. A **materialized view** stores results as of creation/refresh time and requires `REFRESH MATERIALIZED VIEW` to update according to rules. A **function** is an object callable from SQL with a signature consisting of its name and argument types.

Even while the tables are empty, `\dv`, `\dm`, and `\df` still have objects to list.

### 5.3. Adding intentional comments

~~~sql
COMMENT ON TABLE psql_lab.customers
IS 'Customers of the psql practice schema';

COMMENT ON COLUMN psql_lab.orders.status
IS 'Business status of the order';
~~~

Comments help document the schema and can be displayed by psql in verbose description mode or via the appropriate comment-listing command.

**Practice scope:** these examples only create objects inside `psql_lab` in the currently connected database. Later chapters on DDL, transactions, indexes, or PL/pgSQL go deeper; in this lesson the goal is **reading object structure with psql**.

## 6. Listing databases: \l and \l+

In psql:

~~~text
\l
~~~

Or written in full:

~~~text
\list
~~~

This displays the list of databases and attributes that may include:

- Database name.
- Owner.
- Encoding.
- Locale/collation or corresponding environment details.
- Access privileges.

To view more details:

~~~text
\l+
~~~

Depending on the PostgreSQL/psql version, the verbose form may include size, tablespace, and additional metadata columns.

If multiple databases appear, that does not mean you are connected to all of them; `\conninfo` identifies **the currently connected database**.

### 6.1. Checking databases with SQL

~~~sql
SELECT current_database() AS current_database;

SELECT
    datname,
    datallowconn
FROM pg_catalog.pg_database
ORDER BY datname;
~~~

This SQL query reveals database metadata in the catalog. Depending on permissions, environment, and policies, seeing a database name differs from actually having the **CONNECT** privilege to that database.

### 6.2. Avoid confusing \l with \dn

`\l` operates only at the **database** level. If you want to know which schemas exist inside `appdb`, first connect to that database, then use `\dn`.

## 7. Listing schemas: \dn and \dn+

After connecting to the practice database:

~~~text
\dn
~~~

This lists schemas visible under psql's rules. To include owner and privilege details:

~~~text
\dn+
~~~

Filter by name:

~~~text
\dn psql_lab
\dn psql_*
~~~

You may see `public`, `psql_lab`, or other schemas created in the database.

### 7.1. A schema is not a database

If a database has two schemas `sales` and `hr`, each with an `employees` table, they are two distinct objects:

~~~sql
SELECT * FROM sales.employees;
SELECT * FROM hr.employees;
~~~

Conversely, you cannot use `\dn` directly to list schemas in an **unconnected database**. To explore another database, you must connect to it or use a dedicated administrative method.

### 7.2. Listing system schemas

Normally there are also PostgreSQL internal schemas such as `pg_catalog` and `information_schema`. psql has default rules to prevent lists from being flooded with system objects. The `S` modifier can be used with many listing/describe commands to include system objects when needed.

If your goal is simply reading application schemas, do not start by listing every system table.

## 8. \dt: listing tables

This is one of the most frequently used commands:

~~~text
\dt
~~~

It displays tables according to psql's visibility/search path rules, typically with columns like:

~~~text
Schema   | Name      | Type  | Owner
---------+-----------+-------+---------
psql_lab | customers | table | ...
psql_lab | orders    | table | ...
~~~

The output above is **illustrative**. If no tables appear, the database is not necessarily empty; the tables may be outside `search_path`, you may be connected to the wrong database, or you may lack visibility privileges.

### 8.1. Listing tables in a specific schema

~~~text
\dt psql_lab.*
~~~

The pattern `psql_lab.*` includes the schema name before the dot and a wildcard for table names. This is very useful when the schema is not in `search_path`.

List tables starting with `order` in that schema:

~~~text
\dt psql_lab.order*
~~~

List across multiple schemas with a broad pattern:

~~~text
\dt *.*
~~~

The last command can produce many rows in a large database depending on system-object display rules; use it only when that scope is genuinely needed.

### 8.2. Viewing detailed output

~~~text
\dt+ psql_lab.*
~~~

For some objects, `+` adds size and description. Data and sizes are presented according to the psql/server version and current privileges.

**`\dt+` is not an in-depth measurement of bloat, WAL, or total server disk usage.** It is just a convenient inventory tool; large-scale storage analysis requires dedicated statistics and queries.

### 8.3. \dt does not list every relation type

A **view**, **materialized view**, **sequence**, or **index** will not necessarily appear when you only run `\dt`. PostgreSQL has several relation/object kinds; `\dt` focuses on tables.

To explore thoroughly, use the type-specific commands in the next section.

## 9. Common object-listing commands

| Command | Object | Example |
|---|---|---|
| `\dt` | Table | `\dt psql_lab.*` |
| `\dv` | View | `\dv psql_lab.*` |
| `\dm` | Materialized view | `\dm psql_lab.*` |
| `\di` | Index | `\di psql_lab.*` |
| `\ds` | Sequence | `\ds psql_lab.*` |
| `\df` | Function/routine according to mode | `\df psql_lab.*` |
| `\dT` | User-defined data types and matching types | `\dT psql_lab.*` |
| `\dD` | Domain | `\dD psql_lab.*` |
| `\dx` | Extensions installed in the database | `\dx` |
| `\du` | Role | `\du` |
| `\dp` | Access privileges on objects | `\dp psql_lab.*` |
| `\ddp` | Altered default privileges | `\ddp` |
| `\db` | Tablespace | `\db` |

Many `\d...+` variants request more detailed output. Not all commands share the exact same metadata columns; returned output depends on object kind and version.

### 9.1. Views: \dv and \dv+

~~~text
\dv psql_lab.*
\dv+ psql_lab.*
~~~

These list views in the practice schema. To inspect the columns and defining query of a specific view, use `\d` or `\d+` with the view name:

~~~text
\d psql_lab.v_active_customers
\d+ psql_lab.v_active_customers
~~~

A regular view is a query defined in the catalog. It does not store a full copy of the source data.

### 9.2. Materialized views: \dm

~~~text
\dm psql_lab.*
\dm+ psql_lab.*
~~~

You can find `mv_order_totals`. This is a different object type from a regular view: it persists results and must be refreshed when needed.

Having a materialized view does not guarantee its data updates immediately when source tables change. `\dm` tells you the object exists, **not that its data is up to date**.

### 9.3. Indexes: \di

~~~text
\di psql_lab.*
\di+ psql_lab.*
~~~

The index list can include indexes created to back primary key/unique constraints as well as indexes created manually by administrators.

To find out **which table an index belongs to, which columns it covers, what access method it uses, and whether it is unique**, describe the specific index or query the catalog:

~~~text
\d psql_lab.idx_psql_lab_orders_customer_created
~~~

Do not rely on an index name alone to decide whether to drop an index: understand the queries, constraint dependencies, write overhead, and actual execution plans.

### 9.4. Sequences: \ds

~~~text
\ds psql_lab.*
~~~

`GENERATED ... AS IDENTITY` columns are typically backed by sequences created and managed by PostgreSQL. Standalone sequences created with `CREATE SEQUENCE` may also appear.

A sequence has its own permissions and state; do not call `setval()` or `nextval()` just to "inspect metadata" unless you intend to affect future generated values.

### 9.5. Functions and procedures: \df

~~~text
\df psql_lab.*
\df+ psql_lab.*
~~~

`\df` displays matching routines with details such as name, argument types, and return type according to the psql version. PostgreSQL supports **function overloading**, meaning multiple functions can share the same name with different argument types.

For example, the functions:

~~~text
calculate_total(integer)
calculate_total(numeric)
~~~

are distinct signatures. When inspecting details or writing scripts, you may need to specify the **signature**, not just the function name.

For a specific function:

~~~text
\df+ psql_lab.normalize_email
~~~

To view the function body when permitted, you can use the psql command:

~~~text
\sf psql_lab.normalize_email(text)
~~~

`\sf` displays the function definition rather than executing it. Viewing permissions and output formatting may vary by version and user privileges.

### 9.6. Extended commands

~~~text
\dT
\dD
\dx
\du
\db
~~~

These commands help discover user-defined types, domains, extensions, roles, and tablespaces. Not every system has custom objects of every kind; an empty list can be a valid result.

Role/tablespace listing commands are primarily for inventory and privilege review; they do not themselves grant privileges or alter structure.

## 10. \d: describing the structure of an object

For a known table, the most important command is:

~~~text
\d psql_lab.orders
~~~

It gives a summary table of columns, data types, nullability/defaults, along with details such as:

- Primary key.
- Table indexes.
- Check constraints.
- Outgoing foreign keys.
- Tables referencing the current table, when applicable.
- Triggers and related attributes, depending on the object.

Illustrative output (abbreviated, not attempting to reproduce one specific version's exact layout):

~~~text
Table "psql_lab.orders"
Column       | Type                     | Nullable | Default
-------------+--------------------------+----------+---------
order_id     | bigint                   | not null | identity
customer_id  | bigint                   | not null |
status       | text                     | not null | 'pending'
amount       | numeric(12,2)            | not null |
created_at   | timestamp with time zone | not null | CURRENT_TIMESTAMP

Indexes:
    orders_pkey PRIMARY KEY (order_id)
    idx_psql_lab_orders_customer_created (customer_id, created_at DESC)

Check constraints:
    status IN (...)
    amount >= 0

Foreign-key constraints:
    customer_id REFERENCES psql_lab.customers(customer_id)
~~~

Actual output may show more detailed index/constraint syntax, PostgreSQL-generated constraint names, and additional sections.

### 10.1. \d is not only for tables

Try:

~~~text
\d psql_lab.customers
\d psql_lab.v_active_customers
\d psql_lab.mv_order_totals
\d psql_lab.idx_psql_lab_orders_customer_created
~~~

psql chooses the description format based on the object type found. For a view, it can show columns and the view definition. For an index, it can show key/index expressions and the associated table.

### 10.2. When you do not yet know the object name

Enter:

~~~text
\d
~~~

Without a name, `\d` lists relations according to the current visibility context rather than describing a specific table. Once you find the name, use `\d schema.object` to view details.

In large environments, narrow down by schema and name pattern to avoid hundreds of unrelated rows.

## 11. How does \d+ differ from \d?

The plus sign `+` on many psql meta-commands requests more detailed information:

~~~text
\d+ psql_lab.orders
~~~

Extended information may include:

- Table/index access method (depending on version).
- Column storage mode, compression/column statistics when applicable.
- Relation/tablespace size.
- Comments on the table and columns.
- Object-type-specific attributes.

When inspecting tables with large columns like `TEXT`, `JSONB`, or custom storage settings, `\d+` is very helpful for getting a fuller picture than basic `\d`.

### 11.1. \d+ does not replace a full DDL export

PostgreSQL does not have a single standard SQL statement `SHOW CREATE TABLE` directly equivalent to every other DBMS.

`\d+` displays a **human-readable structural description**, not a guaranteed complete `CREATE TABLE` script ready for replay.

If you need to export actual DDL, use the `pg_dump` command-line tool with an appropriate schema-only scope. For example, from the terminal:

~~~bash
pg_dump --schema-only --table=psql_lab.orders --dbname=appdb
~~~

`pg_dump` is a **separate program**, not a `\d` meta-command or a SQL statement sent to the server. Exported DDL also needs review of dependency scope and target environment compatibility before deployment.

## 12. Using patterns to find the right objects

Most listing/describing meta-commands in psql accept a **pattern** for filtering.

Common patterns:

| Pattern | Example | Meaning |
|---|---|---|
| Exact name | `\d psql_lab.orders` | Describe a specific table |
| `*` wildcard | `\dt psql_lab.order*` | Names starting with `order` in the schema |
| `?` wildcard | `\dt psql_lab.ord?rs` | Single character at the question mark position |
| Schema and all names | `\dv psql_lab.*` | Views in the schema |
| Pattern without schema | `\dt *order*` | Search within the default visibility scope |
| Schema wildcard | `\dt *.*` | Broad pattern scan across multiple schemas |

**psql's pattern syntax is not identical to SQL `LIKE` syntax.** In meta-commands, `*` acts as a string wildcard, whereas in SQL:

~~~sql
SELECT *
FROM pg_catalog.pg_tables
WHERE tablename LIKE 'order%';
~~~

the `LIKE` pattern uses `%` and `_`, not `*` and `?`.

### 12.1. Uppercase names and quotes

PostgreSQL folds unquoted identifiers to lowercase according to SQL parser rules. If you created an object with a case-sensitive name, such as:

~~~sql
CREATE TABLE psql_lab."SalesOrder" (
    id BIGINT PRIMARY KEY
);
~~~

then pay attention to how you write the pattern/identifier in psql:

~~~text
\d psql_lab."SalesOrder"
~~~

Do not type `\d psql_lab.salesorder` and assume it refers to the same object. For names containing spaces or special characters, apply proper psql/PostgreSQL identifier quoting.

When designing new schemas, many teams adopt **lowercase snake_case** conventions to avoid constantly quoting identifiers.

### 12.2. Avoid unqualified names when duplicates exist

For example:

~~~text
\d orders
~~~

may describe a table in the current `search_path`, or fail to find the object you expected. Meanwhile:

~~~text
\d psql_lab.orders
~~~

explicitly targets the table in the practice schema.

When writing documentation or handling production incidents, fully qualified **schema.object** names are much more reliable.

## 13. search_path determines the default listing

In PostgreSQL, `search_path` is the list of schemas searched when you reference an object without a schema qualifier.

Check the configuration:

~~~sql
SHOW search_path;

SELECT current_schema();

SELECT current_schemas(TRUE);
~~~

For example, a session might have:

~~~text
"$user", public
~~~

If schema `psql_lab` is not in the search path, `\dt` may not display the two newly created tables. However:

~~~text
\dt psql_lab.*
~~~

still explicitly specifies the schema to search.

### 13.1. Changing search_path in a test session

~~~sql
SET search_path TO psql_lab, public;
~~~

Then:

~~~text
\dt
\d orders
~~~

can display tables in `psql_lab` via unqualified names.

You can restore the session setting per environment rules, for example:

~~~sql
RESET search_path;
~~~

**Do not treat `SET search_path` as having no security implications.** In high-privilege routines or systems where untrusted parties can create objects in a schema, search-path-based name resolution for functions or tables can introduce security risks. During application development, use explicit schema qualification and clear search_path policies.

### 13.2. Handling "Did not find any relations"

If you run:

~~~text
\dt
~~~

and psql reports no relations found, try:

~~~text
\conninfo
\dn
\dt psql_lab.*
~~~

If the explicitly schema-qualified command finds the tables, the cause is likely **`search_path`**, not that the tables vanished.

If still not found, verify the database, user permissions, object name, and casing before drawing conclusions.

## 14. Listing and inspecting privileges with \du, \dp, \ddp

When surveying an unfamiliar system, object structure is only part of the picture. You also need to know who can read and write.

### 14.1. \du — listing roles

~~~text
\du
\du+
~~~

Output may include role names, attributes such as `LOGIN`, `CREATEDB`, `CREATEROLE`, and role memberships depending on version.

PostgreSQL uses **roles** for both login accounts and permission groups. A role without `LOGIN` can still hold privileges granted to other roles.

`\du` is an **inspection command**; it does not show every effective object privilege across inheritance layers, ownership, and default privileges. To investigate thoroughly, inspect grants and the relevant privilege catalogs.

### 14.2. \dp — listing access privileges

~~~text
\dp psql_lab.*
~~~

`\dp` (also aliased as `\z` in psql) displays privilege information for matching relations such as tables/views/sequences, in PostgreSQL's ACL notation.

Privilege codes in psql output can be compact, for example:

~~~text
r  SELECT
a  INSERT
w  UPDATE
d  DELETE
D  TRUNCATE
x  REFERENCES
t  TRIGGER
~~~

These are examples of common codes; do not treat this short table as an exhaustive privilege reference for all object types. Functions, schemas, databases, and sequences have different privilege categories and symbols.

To test a specific privilege in SQL, use functions such as `has_table_privilege()` with the proper object name and context.

### 14.3. \ddp — default privileges

~~~text
\ddp
~~~

This displays **altered default privileges** compared to the standard defaults. Default privileges affect **future objects created** within the declared scope; they do not automatically alter existing tables.

Distinguish clearly:

- `\dp`: current privileges on existing objects.
- `\ddp`: configured default privileges for objects created later.

If a privilege column in the output is blank, do not assume "everyone has access" or "no one has access." Ownership, default rights, and role membership must be read according to PostgreSQL rules.

### 14.4. Checking the active role

~~~sql
SELECT
    current_user,
    session_user,
    current_database();
~~~

A session can switch roles if permitted. Thus, a metadata command run in a different session may return different results; always confirm the **active connection context**.

## 15. Object comments: \dd and extended descriptions

If a project uses `COMMENT ON TABLE` or `COMMENT ON COLUMN`, short documentation is stored alongside metadata.

Example already declared:

~~~sql
COMMENT ON TABLE psql_lab.customers
IS 'Customers of the psql practice schema';
~~~

You can view object descriptions with the appropriate meta-commands:

~~~text
\dd psql_lab.*
\d+ psql_lab.customers
\d+ psql_lab.orders
~~~

`\dd` lists visible comments/descriptions matching a pattern. `\d+` typically displays column details and extended attributes, including comments when present.

Writing `COMMENT` entries does not replace detailed business documentation or migration workflows, but it helps psql users understand a table or column's basic purpose right inside the tool.

## 16. Other useful structural inspection commands

### 16.1. Partitioned tables and indexes

In modern psql versions, commands like:

~~~text
\dP
~~~

can list partitioned objects by matching kind and supported options. When investigating a large partitioned table, describing the parent table and inspecting individual partitions are two distinct tasks.

Do not assume a partitioned table has the exact same storage layout as a regular table, or that inspecting one partition suffices to understand the entire partition tree.

### 16.2. Extensions

~~~text
\dx
\dx+
~~~

Extensions such as `pg_trgm`, `uuid-ossp`, or PostGIS (if installed) can add functions, types, operators, and index operator classes. Listing extensions explains why a database has capabilities beyond the core features of a PostgreSQL release.

An extension **not appearing** in `\dx` does not prove its package is uninstalled on the server; `CREATE EXTENSION` may simply not have been run in the current database, or visibility permissions may be restricted.

### 16.3. Enums, domains, and user-defined types

~~~text
\dT psql_lab.*
\dD psql_lab.*
~~~

These commands are useful when a table has custom data types and `\d table` shows an unfamiliar type name. A domain can carry its own constraints and defaults; an enum defines a fixed set of values.

### 16.4. Tablespaces

~~~text
\db
\db+
~~~

This lists visible tablespaces and can provide additional metadata in verbose mode. It is an advanced aid for tracking storage locations, not a way to modify data files directly from the terminal.

## 17. Formatting output so long lists stay readable

Quite often `\d+`, `\l+`, or catalog queries return many columns, causing horizontal wrapping in the terminal. psql has meta-commands to adjust display formatting.

### 17.1. \x — expanded output

~~~text
\x on
~~~

When enabled, each result row is displayed vertically, which is convenient for wide rows:

~~~text
-[ RECORD 1 ]------+------------------
table_name         | orders
column_name        | created_at
data_type          | timestamp with time zone
~~~

Turn off:

~~~text
\x off
~~~

Or let psql decide automatically when appropriate:

~~~text
\x auto
~~~

### 17.2. \pset — changing display options

~~~text
\pset pager off
\pset border 2
\pset null '(NULL)'
~~~

These options control the pager, table borders, and how SQL `NULL` values are rendered.

During interactive work, the pager can be handy for scrolling results. When running scripts that capture output, you may want to disable the pager to avoid interrupting output streaming.

### 17.3. \timing — measuring execution time

~~~text
\timing on
~~~

Afterward, executed commands display elapsed timing information. To turn off:

~~~text
\timing off
~~~

`\timing` is a convenient client-side timing indicator; it **does not replace** `EXPLAIN (ANALYZE, BUFFERS)`, server statistics, or application p95/p99 measurements. Results are affected by network latency, output rendering, caches, and machine load.

### 17.4. \watch — re-running a query periodically

For **read-only** observation queries, psql can re-execute them periodically:

~~~sql
SELECT count(*) AS active_sessions
FROM pg_stat_activity
WHERE state = 'active';
~~~

Then run `\watch 5` according to your psql version's last-command buffer behavior to refresh every 5 seconds.

Never use `\watch` with `UPDATE`, `DELETE`, or other side-effecting statements without an explicit, deliberate reason, as it repeats the write operation multiple times. Repeating a heavy catalog query can also create unnecessary load.

## 18. From psql to metadata SQL: when should you query pg_catalog?

Meta-commands are very fast for human operators, but sometimes you need results you can filter, join, or consume in an application. PostgreSQL provides catalogs and views such as:

- `pg_catalog.pg_namespace`: namespaces/schemas.
- `pg_catalog.pg_class`: relations such as tables, indexes, views, etc.
- `pg_catalog.pg_attribute`: system-level column/attribute definitions.
- `pg_catalog.pg_constraint`: constraints.
- `pg_catalog.pg_index`: index metadata.
- `information_schema.tables` and `information_schema.columns`: SQL-standard metadata views.
- `pg_catalog.pg_indexes`: convenient view for indexes.

### 18.1. Replacing \dt with SQL

~~~sql
SELECT
    schemaname,
    tablename,
    tableowner
FROM pg_catalog.pg_tables
WHERE schemaname = 'psql_lab'
ORDER BY tablename;
~~~

### 18.2. Reading the column list

~~~sql
SELECT
    table_schema,
    table_name,
    ordinal_position,
    column_name,
    data_type,
    is_nullable,
    column_default
FROM information_schema.columns
WHERE table_schema = 'psql_lab'
  AND table_name = 'orders'
ORDER BY ordinal_position;
~~~

This SQL query works in JDBC or inventory applications, though it does not necessarily expose **every PostgreSQL-specific attribute** shown by `\d+` or internal catalogs.

### 18.3. Listing indexes with SQL

~~~sql
SELECT
    schemaname,
    tablename,
    indexname,
    indexdef
FROM pg_catalog.pg_indexes
WHERE schemaname = 'psql_lab'
ORDER BY tablename, indexname;
~~~

`indexdef` is useful for seeing how PostgreSQL expresses the index definition in metadata.

### 18.4. Viewing view and function definitions

~~~sql
SELECT pg_get_viewdef(
    'psql_lab.v_active_customers'::regclass,
    TRUE
) AS view_sql;

SELECT pg_get_functiondef(
    'psql_lab.normalize_email(text)'::regprocedure
) AS function_sql;
~~~

These approaches are helpful when you need a SQL representation of an object's definition. However, metadata access and visibility depend on privileges, object naming, and matching types/signatures. `pg_get_viewdef` retrieves the view's query, not a complete script including all grants and comments.

### 18.5. Do not replace psql with a giant catalog query

Querying `pg_catalog` directly is flexible, but many system tables contain internal codes, OIDs, dependencies, and structures that are hard to read without deeper knowledge. For quick exploration, `\dt` and `\d+` are usually easier. Switch to metadata SQL only when you need automation, large-scale inventory, or custom reporting.

## 19. Practical scenario: inspecting structure before altering a table

Suppose you are tasked with adding a `shipping_address` column to the orders table. Before running `ALTER TABLE`, investigate first.

### Step 1 — Confirm the connection

~~~text
\conninfo
~~~

Be certain whether you are in development, staging, or production; never rely solely on the prompt name.

### Step 2 — Find the schema and table

~~~text
\dn
\dt psql_lab.*
~~~

If the table is missing, check the database and privileges before proceeding.

### Step 3 — Read the current structure

~~~text
\d psql_lab.orders
\d+ psql_lab.orders
~~~

Identify existing columns, defaults, nullability, primary keys, foreign keys, and indexes.

### Step 4 — Check relationships

For instance, `orders.customer_id` references `customers.customer_id`. Before changing a key column type or dropping a table, check both incoming and outgoing referential constraints, not just column types.

### Step 5 — Check size and impact

A 10-row table and a 100-million-row table have very different DDL costs. `\d+` gives orientation, but heavy changes require additional statistics and an operational rollout plan.

### Step 6 — Check syntax help

~~~text
\h ALTER TABLE
~~~

Verify the exact syntax for your PostgreSQL version; do not copy DDL verbatim from another DBMS.

### Step 7 — Write a separate migration and control deployment

Syntactic example:

~~~sql
ALTER TABLE psql_lab.orders
ADD COLUMN shipping_address TEXT;
~~~

Do not run this change simply because you finished reading metadata. Confirm data requirements, backward compatibility, deployment window, permissions, and rollback strategy before modifying production.

## 20. A 10-minute roadmap to explore an unfamiliar database

If you are granted access to a PostgreSQL database for the first time, follow this sequence:

| Step | Command | Question answered |
|---:|---|---|
| 1 | `\conninfo` | Which server/database am I connected to? |
| 2 | `\?` | Which meta-commands does psql provide? |
| 3 | `\h SELECT` | Where can I look up basic SQL syntax? |
| 4 | `\l` | Which databases exist in the cluster? |
| 5 | `\dn` | Which schemas exist in this database? |
| 6 | `SHOW search_path;` | Why does an unqualified table name resolve here? |
| 7 | `\dt schema_name.*` | Which tables exist in the target schema? |
| 8 | `\dv schema_name.*` | Which views exist? |
| 9 | `\d schema_name.table_name` | What are the columns and constraints of a table? |
| 10 | `\d+ schema_name.table_name` | What extended attributes, comments, or sizes exist? |

Then, depending on your task, continue with `\di`, `\ds`, `\df`, `\du`, or `\dp`.

This roadmap intentionally starts with **read-only** operations, minimizing the risk of modifying data while you are simply exploring.

## 21. Common errors and misconceptions

### 21.1. "\dt shows no tables, so the database must be empty"

Not necessarily. You might be connected to the wrong database, the schema might be outside `search_path`, your role might lack privileges, or the pattern might not match. Try `\conninfo`, `\dn`, and `\dt schema_name.*`.

### 21.2. "I ran \d in a SQL editor and got a syntax error"

`\d` is a **psql** meta-command, not server SQL. If your editor does not implement psql syntax, query `information_schema` or `pg_catalog` instead.

### 21.3. "\l lists schemas"

Incorrect. `\l` lists **databases**. `\dn` lists **schemas** in the current database.

### 21.4. "\dt displays views and materialized views too"

Do not assume that. Use the type-specific commands: `\dv` for views and `\dm` for materialized views.

### 21.5. "\d and \d+ are completely unrelated commands"

In fact, `+` typically requests **additional detail** for the same object kind. `\d+ schema.table` is the extended version of `\d schema.table`.

### 21.6. "Table names are always case-insensitive"

Unquoted identifiers in PostgreSQL are folded to lowercase. Names created with double quotes can be case-sensitive, so use matching patterns/identifiers when describing them.

### 21.7. "Meta-commands can take a semicolon just like SQL"

Usually not. Meta-commands in psql terminate at the end of the input line. Typing `\dt;` can be parsed differently from `\dt` and cause confusing issues.

### 21.8. "\d+ outputs a complete CREATE TABLE statement"

No. `\d+` produces a human-readable description. To export DDL, use `pg_dump --schema-only` with an appropriately defined scope.

### 21.9. "\di doesn't show an index, so the table has no unique constraint"

Check the schema/pattern and inspect the table description. PostgreSQL creates indexes to enforce primary key/unique constraints; an index not appearing under a default pattern does not prove none exists.

### 21.10. "\du shows me every permission of every account"

`\du` primarily shows roles and their attributes/memberships. Specific privileges on relations and default privileges must be examined using `\dp`, `\ddp`, privilege catalogs, and the effective role context.

### 21.11. "\timing is the ultimate query benchmark"

No. It is a client-side indicator from psql affected by network, client, and output formatting. Real query evaluation requires `EXPLAIN`, server metrics, and representative load testing.

### 21.12. "Just use the *.* wildcard on production to be thorough"

Broad wildcards can produce huge outputs and unnecessary overhead/clutter. Filtering patterns by the schema or object group you are investigating is much easier to control.

## 22. Practice exercises

### Exercise 1 — psql help or SQL help?

You forgot how to list indexes and also forgot the syntax to create an index. Choose the right help command for each question.

**Hint:** `\?` to find the `\di` meta-command; `\h CREATE INDEX` to view the SQL syntax.

### Exercise 2 — Database and schema

You are connected to database `appdb`, which contains schemas `public` and `psql_lab`. Which command lists databases, and which lists schemas?

**Suggested answer:**

~~~text
\l
\dn
~~~

### Exercise 3 — Table outside search_path

You created `psql_lab.orders`, yet `\dt` reports no relations found. How can you inspect it without changing session configuration?

**Hint:**

~~~text
\conninfo
\dn
\dt psql_lab.*
\d psql_lab.orders
~~~

### Exercise 4 — Finding objects by type

Write meta-commands to list the following objects in `psql_lab`: tables, views, materialized views, indexes, and sequences.

**Suggested answer:**

~~~text
\dt psql_lab.*
\dv psql_lab.*
\dm psql_lab.*
\di psql_lab.*
\ds psql_lab.*
~~~

### Exercise 5 — Describing order structure

You want to know which table `orders.customer_id` references, the data type of column `amount`, and what indexes the table has. Choose the appropriate command.

**Hint:**

~~~text
\d psql_lab.orders
\d+ psql_lab.orders
~~~

### Exercise 6 — Distinguishing quoted identifiers

A table `"SalesOrder"` was created in schema `psql_lab`. Why might `\d psql_lab.salesorder` fail to find it? Write the correct command to describe it.

**Hint:**

~~~text
\d psql_lab."SalesOrder"
~~~

### Exercise 7 — Inspecting a function

You see `psql_lab.normalize_email(text)` and want to inspect its signature and function body without executing it. Which commands do you choose?

**Hint:**

~~~text
\df+ psql_lab.normalize_email
\sf psql_lab.normalize_email(text)
~~~

### Exercise 8 — Checking privileges

An application can run `SELECT` on a view but cannot read the underlying table directly. You want to inspect roles and object privileges. Which psql commands do you use?

**Hint:**

~~~text
\du
\dp psql_lab.*
~~~

You should also check the active role context, ownership, grants, and view security settings before drawing conclusions.

### Exercise 9 — Distinguishing help from DDL

You want to check the `ALTER TABLE` syntax before modifying a large table. Is `\d+` enough?

**Hint:** No. `\d+` shows the current structure; `\h ALTER TABLE` shows the syntax. Assessing locks, duration, and disk space still requires separate operational steps.

### Exercise 10 — Translating psql commands into SQL

A Java program needs to list the columns of `psql_lab.orders`. Can it send `\d psql_lab.orders` verbatim over JDBC?

**Hint:** No. Use `information_schema.columns`, `pg_catalog`, or JDBC `DatabaseMetaData`.

### Exercise 11 — Identifying the risk of \watch

A user runs `UPDATE ...` and then invokes `\watch 1`. Why can this be dangerous?

**Hint:** If the statement is repeated, the write operation can execute multiple times. Only use periodic watch commands with **genuinely read-only** queries whose cost is well understood.

### Exercise 12 — Mapping a schema

From the test database, find: all tables, all indexes, views, sequences, and functions in schema `psql_lab`. Then describe the `orders` table and record the names of its foreign keys.

**Hint:** Combine `\dt`, `\di`, `\dv`, `\ds`, and `\df` with `\d+ psql_lab.orders`. The result is an inventory of the actual objects.

## 23. Quick reference table for psql

| What do you want to do? | Command |
|---|---|
| View psql help | `\?` |
| View SQL syntax help | `\h`, `\h CREATE TABLE` |
| View connection info | `\conninfo` |
| List databases | `\l`, `\l+` |
| Switch databases | `\c database_name` |
| List schemas | `\dn`, `\dn+` |
| List tables | `\dt`, `\dt schema.*` |
| List views | `\dv schema.*` |
| List materialized views | `\dm schema.*` |
| List indexes | `\di schema.*` |
| List sequences | `\ds schema.*` |
| List functions/routines | `\df schema.*` |
| View function source | `\sf schema.function(type)` |
| Describe a table | `\d schema.table` |
| Describe a table in detail | `\d+ schema.table` |
| List roles | `\du` |
| View object privileges | `\dp schema.*` |
| View default privileges | `\ddp` |
| View comments/descriptions | `\dd schema.*` |
| List extensions | `\dx` |
| List data types/domains | `\dT`, `\dD` |
| View search path | `SHOW search_path;` |
| Display results vertically | `\x on`, `\x auto` |
| Disable pager | `\pset pager off` |
| Enable execution timing | `\timing on` |
| Exit psql | `\q` |

---

## Conclusion

`psql` is much more than a place to type `SELECT` queries. Its meta-command system helps learners and operators **explore PostgreSQL methodically**: `\?` provides client command help, `\h` looks up SQL syntax, `\l` and `\dn` locate databases and schemas, commands like `\dt`, `\dv`, `\di`, `\ds`, and `\df` list objects, and `\d` and `\d+` reveal concrete structure.

When working in an unfamiliar database, always verify **the right connection, right schema, right object name, and right privileges**. Do not confuse meta-commands with SQL, do not assume a table was dropped just because `\dt` did not show it, and do not treat `\d+` output as a complete migration script. These habits help you inventory structure quickly, understand relationships between objects, and prepare safely before any schema change.
