# Using pgAdmin or SQL Tools to Explore Data in PostgreSQL

## 1. Data exploration is the first step before writing application code

When onboarding onto an unfamiliar PostgreSQL database, developers often need to answer several questions:

- Which **server**, **database**, and **schema** am I connected to?
- Which tables and views exist, and what are each table's columns and data types?
- Which column is the **primary key**, and which columns reference other tables via **foreign keys**?
- Does a column allow `NULL`, and does it have a `DEFAULT` or `IDENTITY`?
- What values, formats, date ranges, and missing cases appear in the actual data?
- Which relationships should joins between tables follow?
- Does a table have many rows, which indexes exist, and how does PostgreSQL plan to read the data?
- Can I explore the data **without accidentally modifying or slowing down the system**?

Graphical tools like **pgAdmin** let you browse structure and execute SQL through a UI. Command-line **psql** helps inspect, save scripts, and repeat steps in headless environments. Other SQL clients such as DBeaver or DataGrip serve similar needs.

This lesson presents a workflow to **explore from connection to structure, data, relationships, and query plans**, using PostgreSQL throughout. The goal is knowing **what to observe and which SQL verifies your conclusions**, rather than memorizing where a specific button sits in one UI version.

> **Practice rule:** on an unfamiliar or production database, prefer a **read-only** account and reasonably bounded `SELECT` queries. All table-creation, data-loading, or schema-changing commands in this lesson must run only on an authorized **practice database**.

## 2. Choosing a data exploration tool

| Tool | Interaction style | Strengths | When to use |
|---|---|---|---|
| **pgAdmin** | Graphical, Object Explorer, Query Tool | View server/database/schema/table trees, inspect metadata, run SQL, view results | Learning PostgreSQL, needing visual schema browsing |
| **psql** | Command line | Fast, easy to automate, offers meta-commands like `\dt` and `\d+` | Terminals, SSH, containers, scripts, or direct checks |
| **DBeaver** | Cross-DBMS graphical SQL IDE | Browse databases, edit scripts, view data, export results | Working across multiple DBMSs or multiple connections |
| **DataGrip** | IDE-integrated SQL workspace | Assists with SQL authoring, object navigation, and result inspection | Developers wanting database tools inside their IDE |
| **SQL apps via JDBC/Python** | Code | Repeatable queries, controlled data extraction | Automated analysis or integrated processing |

**pgAdmin is not PostgreSQL Server.** pgAdmin is a **client** connecting to a server; installing pgAdmin does not automatically mean PostgreSQL Server is running or a sample database exists.

Similarly, `psql` is a client tool. You need a running PostgreSQL Server and valid connection details. The exploratory SQL queries below work in **pgAdmin Query Tool**, `psql`, or most other SQL clients; commands starting with `\` such as `\dt` are **psql-specific meta-commands**, not sent verbatim via JDBC or Query Tool.

### 2.1. Connection-level concepts

~~~text
PostgreSQL server / instance
├── database: postgres
├── database: learning_db
│   ├── schema: public
│   └── schema: explore_lab
│       ├── table: customers
│       ├── table: products
│       ├── table: orders
│       └── view: v_paid_orders
└── database: another_db
~~~

- **Server/instance** is the PostgreSQL process accepting connections and managing databases.
- **Database** is the object scope accessible directly by a single PostgreSQL connection.
- **Schema** is a namespace inside a database containing tables, views, functions, and other objects.
- **Table** stores data rows; a **view** is a named query (regular views do not materialize result rows on their own).
- **Role/user** governs authentication and permissions. A login role name does not necessarily match any schema name.

Do not confuse **database** with **schema**. For example, `explore_lab.orders` is the `orders` table in the `explore_lab` schema of **the currently connected database**, not a path to another database.

## 3. Information needed before opening a connection

Obtain these from an administrator or authorized environment configuration:

| Information | Illustrative example | Purpose |
|---|---|---|
| Host | `db-lab.example.internal` | Machine or endpoint accepting connections |
| Port | `5432` | PostgreSQL port; may differ from default |
| Database | `learning_db` | Database containing the data to explore |
| Username | `report_reader` | Login role granted permissions |
| Password/credential | Provided by secret manager | Authentication |
| TLS/SSL mode | `verify-full` if infrastructure supports valid CA/hostname | Connection encryption/verification |
| Target schema | `explore_lab` | Exploration scope |
| Policy | Read-only, query limits, staging environment | Avoid impacting live systems |

Never store real passwords in documentation, Git repositories, or publicly shared commands. If using a secret manager, retrieve credentials through your organization's approved mechanism. When connecting via VPN, SSH tunnel, or proxy, the address entered in the SQL client may differ from the server's internal address.

### 3.1. Verifying the right target after connecting

This SQL query runs in any SQL client:

~~~sql
SELECT
    current_database() AS database_name,
    current_user AS current_role,
    session_user AS login_role,
    current_schema() AS default_schema,
    current_setting('search_path') AS search_path,
    current_setting('TimeZone') AS session_timezone,
    version() AS server_version;
~~~

Explanation:

- `current_database()` returns the active database.
- `current_user` is the effective role checked for permissions; it may differ from `session_user` after role switching.
- `current_schema()` reflects the first active schema on `search_path`, not all schemas in the database.
- `search_path` determines how PostgreSQL resolves unqualified object names.
- `TimeZone` affects display and certain calculations on time values.

If an application has both staging and production, verify the endpoint using infrastructure details beyond just the database name. Two different servers can easily both have a database named `learning_db`.

## 4. Connecting and browsing data in pgAdmin

### 4.1. Registering a PostgreSQL Server

pgAdmin versions vary in button placement, but the common flow is:

1. Open pgAdmin and locate **Register > Server** or the option to register a new server under **Servers**.
2. Under **General**, enter a recognizable display name such as `PostgreSQL Lab - Read Only`. This is a label inside pgAdmin, **not** the real database or PostgreSQL server name.
3. Under **Connection**, enter host, port, maintenance database, username, and authentication method.
4. If the environment requires TLS, configure SSL/TLS with the CA, server name, and organizational policy.
5. Save the configuration and open the connection.
6. Run the SQL from Section 3.1 to confirm you are connected to the intended database/role.

The **Maintenance database** on the registration screen is typically the database used for the initial administrative connection, such as `postgres` or a permitted database. It does not mean you have opened the right business database. Select the **actual target database** in Object Explorer before opening Query Tool.

Enabling password saving in a GUI must comply with device and security policies; do not assume every workstation is safe for storing auto-login credentials.

### 4.2. Browsing the Object Explorer tree

A typical hierarchy in pgAdmin:

~~~text
Servers
└── PostgreSQL Lab
    └── Databases
        └── learning_db
            └── Schemas
                └── explore_lab
                    ├── Tables
                    │   ├── customers
                    │   │   ├── Columns
                    │   │   ├── Constraints
                    │   │   └── Indexes
                    │   ├── products
                    │   └── orders
                    ├── Views
                    │   └── v_paid_orders
                    ├── Functions
                    └── Procedures
~~~

For each table, you can inspect:

- **Columns:** column names, data types, nullability, default/identity.
- **Constraints:** primary key, unique, foreign key, check.
- **Indexes:** regular indexes, composite indexes, unique indexes, access methods.
- **Properties:** attributes supported by the UI.
- **SQL/DDL:** statements to recreate the object when displayed by pgAdmin.

If an expected schema or table is missing, check that you selected the right **database**, verify role privileges, check Object Explorer filters, and **Refresh** the object tree after schema changes. Never assume a table was dropped just because it is absent from a filtered list.

### 4.3. Viewing data via View/Edit Data

pgAdmin typically includes **View/Edit Data**, with options such as viewing the first N rows or all rows depending on version and UI.

This feature is handy for a quick look at real values, but keep in mind:

- On a large table, requesting **all rows** can be very expensive.
- Without an explicit `ORDER BY`, "first 100 rows" does not mean the 100 newest rows.
- The grid may allow inline edits if the role has write privileges; **never edit data just while exploring**.
- `JSONB`, array, `bytea`, timestamp, or long text values may be formatted by the GUI.
- A paginated/limited grid **does not show the total row count of the table**.

To control the exact result set, switch to **Query Tool** and write `SELECT ... ORDER BY ... LIMIT`.

### 4.4. Opening Query Tool

Select the target database and open **Tools > Query Tool** or the equivalent UI action. In Query Tool:

1. Enter a `SELECT` query.
2. Run it using the Execute/Run button or the tool's shortcut.
3. Inspect the result grid under **Data Output**.
4. Review messages, runtime, and errors in the messages/history pane if provided.
5. Use query plan visualization when needed, carefully distinguishing **Explain** from **Explain Analyze**.
6. Save useful SQL queries as `.sql` files so they can be reused.

A good first query:

~~~sql
SELECT *
FROM information_schema.tables
WHERE table_schema = 'explore_lab'
ORDER BY table_name
LIMIT 50;
~~~

**A script with multiple statements** can execute everything if you run the whole buffer. When your goal is read-only inspection, highlight the exact statement before running and scrutinize any `DELETE`, `UPDATE`, `DROP`, `TRUNCATE`, or `ALTER`.

### 4.5. Saving results or exporting CSV

You can use the GUI's result-set download/export feature depending on version. When exporting:

- Select only needed columns; avoid `SELECT *` on tables containing personal data.
- Confirm encoding (typically UTF-8), delimiter, column names, and `NULL` representation.
- Watch out for Query Tool row limits; an export from the result grid **may contain only the loaded subset of rows**.
- Protect exported files because data in CSV is no longer guarded by PostgreSQL access controls once it leaves the server.

If you need reproducible exports with controlled sizing, `psql \copy` is an alternative covered later.

## 5. Exploring with psql

`psql` is PostgreSQL's official command-line client, usually included with PostgreSQL tool installations.

### 5.1. Connecting

~~~bash
psql -h db-lab.example.internal -p 5432 -U report_reader -d learning_db
~~~

Depending on authentication configuration, the client may prompt for a password or use another auth method. You can also use a connection string:

~~~bash
psql "host=db-lab.example.internal port=5432 dbname=learning_db user=report_reader sslmode=verify-full"
~~~

`verify-full` requires TLS and verifies the server hostname and certificate. Without a valid CA and matching hostname, adding this parameter alone is not enough for security; certificates must be configured per infrastructure requirements.

Do not place real passwords in arguments or URLs that get logged. For internal test connections and varying security requirements, the SSL mode parameter should follow your environment's policy.

### 5.2. Common meta-commands

At the `psql` prompt:

| Command | Purpose |
|---|---|
| `\conninfo` | View current connection details |
| `\l` | List databases (per permissions and visibility) |
| `\c learning_db` | Switch connection to another database |
| `\dn` | List schemas |
| `\dt explore_lab.*` | List tables in schema `explore_lab` |
| `\dv explore_lab.*` | List views in the schema |
| `\di explore_lab.*` | List indexes |
| `\d explore_lab.orders` | Describe table, columns, indexes, and constraints |
| `\d+ explore_lab.orders` | Add extended details depending on version |
| `\df explore_lab.*` | Find functions in the schema |
| `\du` | View visible roles |
| `\timing on` | Display statement execution time |
| `\x auto` | Automatically switch to vertical display when appropriate |
| `\h SELECT` | View SQL syntax help for `SELECT` |
| `\?` | View psql meta-command help |
| `\q` | Exit psql |

Meta-commands **do not end with a semicolon** like SQL statements. Example:

~~~text
learning_db=> \dn
learning_db=> \dt explore_lab.*
learning_db=> \d+ explore_lab.orders
learning_db=> \timing on
learning_db=> SELECT current_database(), current_user;
learning_db=> \q
~~~

Never run `\d`, `\dt`, or `\copy` via JDBC `Statement.execute(...)`: those are `psql` client syntax, not server SQL.

### 5.3. Running a SQL script

~~~bash
psql -h db-lab.example.internal -U report_reader -d learning_db \
  -v ON_ERROR_STOP=1 -f inspect_schema.sql
~~~

`-f` tells psql to read the file on **the machine running psql**. `ON_ERROR_STOP=1` makes psql stop on SQL errors in the script, which is helpful for catching failures instead of continuing past erroneous output. For scripts that write data, manage transactions and permissions explicitly; do not assume `ON_ERROR_STOP` rolls back previously committed statements automatically.

`-X` can be added to skip reading a personal `psqlrc` startup file when consistent client behavior is needed:

~~~bash
psql -X -v ON_ERROR_STOP=1 -d learning_db -f inspect_schema.sql
~~~

In inspection scripts, use schema-qualified names and explicit `SELECT` queries to reduce dependence on session settings.

## 6. Preparing a sample dataset for practice

From here on, **CREATE/INSERT** commands must run only on a practice database where you are authorized to create schemas. If you only have read-only access to production, **skip this section** and run the metadata-exploration queries in later sections against an authorized schema.

### 6.1. Creating the schema and tables

~~~sql
CREATE SCHEMA IF NOT EXISTS explore_lab;

CREATE TABLE explore_lab.customers (
    customer_id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    full_name TEXT NOT NULL,
    joined_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    tier TEXT NOT NULL CHECK (tier IN ('VIP', 'STANDARD'))
);

CREATE TABLE explore_lab.products (
    product_id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    sku TEXT NOT NULL UNIQUE,
    product_name TEXT NOT NULL,
    current_price NUMERIC(12, 2) NOT NULL CHECK (current_price >= 0),
    tags TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[]
);

CREATE TABLE explore_lab.orders (
    order_id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    customer_id BIGINT NOT NULL
        REFERENCES explore_lab.customers(customer_id),
    ordered_at TIMESTAMPTZ NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('NEW', 'PAID', 'CANCELLED')),
    total_amount NUMERIC(12, 2) NOT NULL CHECK (total_amount >= 0),
    metadata JSONB NOT NULL DEFAULT '{}'::JSONB
);

CREATE INDEX idx_orders_customer_time
ON explore_lab.orders (customer_id, ordered_at DESC);
~~~

Here:

- `BIGINT GENERATED BY DEFAULT AS IDENTITY` lets PostgreSQL auto-generate IDs when omitted. The example **pins explicit IDs** when loading data so results are easy to follow.
- `TIMESTAMPTZ` represents a point in time; its formatted display can vary with the session time zone.
- `NUMERIC(12,2)` suits monetary amounts with two decimal places.
- `TEXT[]` is PostgreSQL's array type.
- `JSONB` stores binary JSON supporting specialized operators.
- `CHECK` enforces allowed values on `status` and `tier`.
- The foreign key from `orders.customer_id` to `customers.customer_id` ensures every order references an existing customer.

### 6.2. Loading sample data

~~~sql
INSERT INTO explore_lab.customers
    (customer_id, email, full_name, joined_at, tier)
VALUES
    (1, 'an@example.com', 'Nguyen An',
        TIMESTAMPTZ '2026-01-01 08:00:00+07', 'VIP'),
    (2, 'binh@example.com', 'Tran Binh',
        TIMESTAMPTZ '2026-01-02 08:00:00+07', 'STANDARD'),
    (3, 'chi@example.com', 'Le Chi',
        TIMESTAMPTZ '2026-01-03 08:00:00+07', 'VIP');

INSERT INTO explore_lab.products
    (product_id, sku, product_name, current_price, tags)
VALUES
    (11, 'KB-01', 'Keyboard', 350000.00, ARRAY['accessory', 'office']),
    (12, 'MS-01', 'Mouse', 150000.00, ARRAY['accessory']),
    (13, 'MN-01', 'Monitor', 2200000.00, ARRAY['display', 'office']);

INSERT INTO explore_lab.orders
    (order_id, customer_id, ordered_at, status, total_amount, metadata)
VALUES
    (1001, 1, TIMESTAMPTZ '2026-01-05 10:00:00+07',
        'PAID', 500000.00, '{"channel":"web","coupon":null}'::jsonb),
    (1002, 2, TIMESTAMPTZ '2026-01-05 15:00:00+07',
        'PAID', 2200000.00, '{"channel":"mobile"}'::jsonb),
    (1003, 1, TIMESTAMPTZ '2026-01-08 16:00:00+07',
        'NEW', 350000.00, '{"channel":"web"}'::jsonb),
    (1004, 3, TIMESTAMPTZ '2026-01-10 09:00:00+07',
        'PAID', 150000.00, '{"channel":"store"}'::jsonb),
    (1005, 2, TIMESTAMPTZ '2026-02-01 11:00:00+07',
        'CANCELLED', 900000.00, '{}'::jsonb);
~~~

Because the sample inserts provide explicit IDs for identity columns, the underlying sequences remain at their initial values. If you want to insert new rows **without specifying IDs** later, synchronize the sequences in a controlled way or create a fresh lab schema. The exploration steps in this lesson **do not require inserting more rows** after loading the sample dataset.

From this data we have:

| Dataset | Row count |
|---|---:|
| `explore_lab.customers` | 3 |
| `explore_lab.products` | 3 |
| `explore_lab.orders` | 5 |

In `orders`: three `PAID` orders totaling `2,850,000`, one `NEW` order, and one `CANCELLED` order. Subsequent results rely on this dataset.

### 6.3. Creating a view to explore

~~~sql
CREATE VIEW explore_lab.v_paid_orders AS
SELECT
    o.order_id,
    o.ordered_at,
    c.full_name,
    o.total_amount
FROM explore_lab.orders AS o
JOIN explore_lab.customers AS c
  ON c.customer_id = o.customer_id
WHERE o.status = 'PAID';
~~~

A view stores only its defining query. When reading a regular view, PostgreSQL executes that query logic against source tables as of the appropriate snapshot. **A regular view differs from a materialized view**, which stores computed results and requires refreshing.

## 7. Exploring schemas and objects

### 7.1. Listing schemas

~~~sql
SELECT
    schema_name,
    schema_owner
FROM information_schema.schemata
WHERE schema_name NOT IN ('pg_catalog', 'information_schema')
ORDER BY schema_name;
~~~

Depending on role and privileges, some schemas may not appear. So "not seeing a schema" does not necessarily mean it does not exist; the user might lack access or you might be connected to the wrong database.

In psql:

~~~text
\dn
~~~

In pgAdmin: select the database and expand **Schemas**.

### 7.2. Listing tables and views in a schema

~~~sql
SELECT
    table_schema,
    table_name,
    table_type
FROM information_schema.tables
WHERE table_schema = 'explore_lab'
ORDER BY table_type, table_name;
~~~

Expect three `BASE TABLE` entries and one `VIEW`.

To use PostgreSQL's catalog:

~~~sql
SELECT
    schemaname,
    tablename,
    tableowner
FROM pg_catalog.pg_tables
WHERE schemaname = 'explore_lab'
ORDER BY tablename;
~~~

`information_schema` is a SQL-standard metadata interface convenient for general details. `pg_catalog` exposes PostgreSQL-specific details, including indexes, constraints, statistics, and object kinds not fully represented in information schema.

### 7.3. Schema-qualified names and search_path

These two queries can behave differently:

~~~sql
SELECT * FROM orders LIMIT 5;

SELECT * FROM explore_lab.orders LIMIT 5;
~~~

The first only searches for `orders` in schemas listed in `search_path`. If `explore_lab` is missing from the path or another schema earlier in the path also has an `orders` table, it can fail or read **the wrong table**.

Check:

~~~sql
SHOW search_path;

SELECT current_schema();
~~~

You can set a preferred schema in a **practice session**:

~~~sql
SET search_path TO explore_lab, public;

SELECT order_id, status
FROM orders
ORDER BY order_id
LIMIT 5;
~~~

When switching sessions or opening a new Query Tool tab, `search_path` may revert to its default. When writing SQL for documentation, admin scripts, or multi-schema exploration, **fully schema-qualified names** like `explore_lab.orders` prevent ambiguity.

## 8. Exploring columns, data types, and defaults

### 8.1. Using information_schema.columns

~~~sql
SELECT
    ordinal_position,
    column_name,
    data_type,
    udt_name,
    is_nullable,
    column_default,
    identity_generation
FROM information_schema.columns
WHERE table_schema = 'explore_lab'
  AND table_name = 'orders'
ORDER BY ordinal_position;
~~~

Fields to inspect:

| Field | Meaning |
|---|---|
| `ordinal_position` | Column position in the table definition |
| `column_name` | Column name |
| `data_type` | Type name as presented by information schema |
| `udt_name` | Underlying PostgreSQL type name; useful for custom types or arrays |
| `is_nullable` | Whether SQL `NULL` is allowed |
| `column_default` | Default expression if present |
| `identity_generation` | `ALWAYS` / `BY DEFAULT` for identity columns, if applicable |

For domains, enums, arrays, or user-defined types, `information_schema.columns.data_type` may not tell the full story. When you need the exact PostgreSQL type, use `psql \d+` or `pg_catalog`.

### 8.2. Using pg_attribute and format_type

~~~sql
SELECT
    a.attnum AS column_position,
    a.attname AS column_name,
    pg_catalog.format_type(a.atttypid, a.atttypmod) AS pg_type,
    a.attnotnull AS not_null,
    pg_catalog.pg_get_expr(d.adbin, d.adrelid) AS default_expr
FROM pg_catalog.pg_attribute AS a
JOIN pg_catalog.pg_class AS c
  ON c.oid = a.attrelid
JOIN pg_catalog.pg_namespace AS n
  ON n.oid = c.relnamespace
LEFT JOIN pg_catalog.pg_attrdef AS d
  ON d.adrelid = a.attrelid
 AND d.adnum = a.attnum
WHERE n.nspname = 'explore_lab'
  AND c.relname = 'orders'
  AND a.attnum > 0
  AND NOT a.attisdropped
ORDER BY a.attnum;
~~~

This query uses PostgreSQL's catalog to retrieve **the fully formatted type**, useful when you want to see `numeric(12,2)` or distinguish types with length/precision modifiers. For identity/generated details, check the corresponding metadata rather than assuming `default_expr` alone captures everything.

In psql:

~~~text
\d+ explore_lab.orders
~~~

In pgAdmin: expand `orders` and inspect **Columns** and their properties.

### 8.3. Distinguishing SQL NULL, JSON null, and empty string

The `orders` table has `metadata JSONB`; an object may contain `"coupon": null`. Distinguish clearly:

- **SQL `NULL`:** the column itself has no SQL value.
- **JSON `null`:** a JSON value inside the JSON document.
- **Empty string `''`:** a text value of length 0.
- **Missing JSON key:** the key does not exist in the object at all.

Example:

~~~sql
SELECT
    order_id,
    metadata,
    metadata ? 'coupon' AS has_coupon_key,
    metadata -> 'coupon' AS coupon_json_value,
    metadata ->> 'coupon' AS coupon_text_value
FROM explore_lab.orders
ORDER BY order_id;
~~~

For `order_id = 1001`, the `coupon` key exists and holds JSON null. For orders without that key, the `?` operator returns false. The `->>` operator returns text and produces SQL NULL for both JSON null and a missing key, so check key existence when you need to distinguish the two.

## 9. Exploring keys, constraints, and relationships

### 9.1. Using pg_constraint

~~~sql
SELECT
    c.conname AS constraint_name,
    c.contype AS constraint_type_code,
    c.conrelid::regclass AS table_name,
    pg_catalog.pg_get_constraintdef(c.oid, true) AS definition
FROM pg_catalog.pg_constraint AS c
JOIN pg_catalog.pg_class AS t
  ON t.oid = c.conrelid
JOIN pg_catalog.pg_namespace AS n
  ON n.oid = t.relnamespace
WHERE n.nspname = 'explore_lab'
ORDER BY t.relname, c.contype, c.conname;
~~~

In `pg_constraint.contype`, common codes are:

| Code | Constraint kind |
|---|---|
| `p` | Primary key |
| `u` | Unique constraint |
| `f` | Foreign key |
| `c` | Check constraint |
| `x` | Exclusion constraint |

Some `NOT NULL` attributes are stored in column metadata or catalog structures depending on version, so do not rely on a `pg_constraint` query alone to conclude **every** nullability constraint.

### 9.2. Listing foreign keys with information_schema

~~~sql
SELECT
    tc.table_schema,
    tc.table_name,
    tc.constraint_name,
    kcu.column_name,
    ccu.table_schema AS referenced_schema,
    ccu.table_name AS referenced_table,
    ccu.column_name AS referenced_column
FROM information_schema.table_constraints AS tc
JOIN information_schema.key_column_usage AS kcu
  ON kcu.constraint_catalog = tc.constraint_catalog
 AND kcu.constraint_schema = tc.constraint_schema
 AND kcu.constraint_name = tc.constraint_name
JOIN information_schema.constraint_column_usage AS ccu
  ON ccu.constraint_catalog = tc.constraint_catalog
 AND ccu.constraint_schema = tc.constraint_schema
 AND ccu.constraint_name = tc.constraint_name
WHERE tc.table_schema = 'explore_lab'
  AND tc.constraint_type = 'FOREIGN KEY'
ORDER BY tc.table_name, tc.constraint_name, kcu.ordinal_position;
~~~

For **composite (multi-column)** foreign keys, if you need to pair each source column with its exact referenced target column by ordinal position, use `pg_constraint.conkey` / `confkey` or join information schema views on ordinal position. The simpler query above is best for **viewing relationships**, not as a DDL generator for all composite keys.

### 9.3. Table relationships in the sample dataset

~~~mermaid
erDiagram
    CUSTOMERS ||--o{ ORDERS : places
    CUSTOMERS {
        bigint customer_id PK
        text email
        text full_name
    }
    ORDERS {
        bigint order_id PK
        bigint customer_id FK
        timestamptz ordered_at
        text status
    }
    PRODUCTS {
        bigint product_id PK
        text sku
        numeric current_price
    }
~~~

`customers` relates to `orders` via `customer_id`; `products` has no relationship to `orders` in this minimal dataset. **Never assume two columns with matching names automatically have a foreign key.** To confirm a database-enforced relationship, check actual foreign keys in the catalog.

### 9.4. Using JOIN to verify your understanding

~~~sql
SELECT
    o.order_id,
    o.status,
    o.total_amount,
    c.customer_id,
    c.full_name
FROM explore_lab.orders AS o
JOIN explore_lab.customers AS c
  ON c.customer_id = o.customer_id
ORDER BY o.order_id;
~~~

Expect five order rows accompanied by the matching customer names.

To see **all customers**, including those with no orders yet, use `LEFT JOIN`:

~~~sql
SELECT
    c.customer_id,
    c.full_name,
    COUNT(o.order_id) AS order_count
FROM explore_lab.customers AS c
LEFT JOIN explore_lab.orders AS o
  ON o.customer_id = c.customer_id
GROUP BY c.customer_id, c.full_name
ORDER BY c.customer_id;
~~~

In the sample data: An has 2 orders, Binh has 2 orders, and Chi has 1 order. `COUNT(o.order_id)` is more accurate than `COUNT(*)` for counting orders in a `LEFT JOIN`, because a customer with zero orders still produces one NULL-extended row in the JOIN result.

## 10. Exploring data without reading the entire table

### 10.1. Viewing a few rows in deterministic order

~~~sql
SELECT
    order_id,
    customer_id,
    ordered_at,
    status,
    total_amount
FROM explore_lab.orders
ORDER BY order_id
LIMIT 10;
~~~

`LIMIT 10` caps returned rows, but **does not guarantee** the query is cheap in all cases. For example, if `ORDER BY` requires sorting millions of rows without a supporting index, PostgreSQL may still process many rows to find the top 10.

If you only want to inspect the result set's structure, run a `SELECT` of the columns of interest with `LIMIT 0`:

~~~sql
SELECT
    order_id,
    status,
    total_amount
FROM explore_lab.orders
LIMIT 0;
~~~

Zero rows are returned, yet SQL clients still display the result set's column names and data types.

### 10.2. Avoiding SELECT * on real tables

`SELECT *` is convenient when **starting out** on small tables, but on systems with sensitive data or large `JSONB`/`BYTEA` columns, it can:

- Transmit many unnecessary bytes over the network.
- Expose personal data in result grids or logs.
- Consume excessive memory in the SQL client.
- Make it harder for readers to spot the important columns.

Select specific columns and apply filters relevant to your exploration goal.

### 10.3. Finding distinct values

~~~sql
SELECT DISTINCT status
FROM explore_lab.orders
ORDER BY status;
~~~

Expect `CANCELLED`, `NEW`, `PAID`.

To inspect distribution:

~~~sql
SELECT
    status,
    COUNT(*) AS order_count,
    SUM(total_amount) AS total_value
FROM explore_lab.orders
GROUP BY status
ORDER BY order_count DESC, status;
~~~

This is a practical exploration step before building reports or UI filters: identifying valid values, frequencies, and unexpected cases.

## 11. Exploring data quality

### 11.1. NULLs, duplicates, and value ranges

~~~sql
SELECT
    COUNT(*) AS total_rows,
    COUNT(*) FILTER (WHERE email IS NULL) AS email_missing,
    COUNT(DISTINCT email) AS distinct_emails,
    MIN(joined_at) AS first_joined_at,
    MAX(joined_at) AS last_joined_at
FROM explore_lab.customers;
~~~

In the sample table, `email NOT NULL UNIQUE` makes missing emails 0 and distinct emails 3. In real tables, **constraints may differ**, and externally imported data may contain anomalies or empty strings.

To check for duplicate emails in a table **without a UNIQUE constraint**:

~~~sql
SELECT
    lower(trim(email)) AS normalized_email,
    COUNT(*) AS duplicate_count
FROM explore_lab.customers
WHERE email IS NOT NULL
GROUP BY lower(trim(email))
HAVING COUNT(*) > 1
ORDER BY duplicate_count DESC, normalized_email;
~~~

In the sample schema this returns zero rows. The query also highlights a subtle distinction: the database enforces uniqueness on **raw email strings and their collation/comparison rules**, whereas business rules may define uniqueness on **normalized email**. Confirm the rule before using the output to clean data or add an expression unique index.

### 11.2. Time-series data

~~~sql
SELECT
    MIN(ordered_at) AS first_order_at,
    MAX(ordered_at) AS last_order_at,
    COUNT(*) AS number_of_orders
FROM explore_lab.orders;
~~~

To group by local calendar day:

~~~sql
SELECT
    (ordered_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::date AS order_day,
    COUNT(*) AS orders_count
FROM explore_lab.orders
GROUP BY 1
ORDER BY 1;
~~~

`TIMESTAMPTZ` stores a point in time; how `ordered_at` displays depends on the session's `TimeZone`. For reports like "orders on Jan 05 Vietnam time," specifying the time zone explicitly produces consistent results.

### 11.3. Inspecting JSONB

~~~sql
SELECT
    order_id,
    metadata ->> 'channel' AS channel,
    jsonb_typeof(metadata) AS metadata_type
FROM explore_lab.orders
ORDER BY order_id;
~~~

Count by channel:

~~~sql
SELECT
    COALESCE(metadata ->> 'channel', '(missing)') AS channel,
    COUNT(*) AS order_count
FROM explore_lab.orders
GROUP BY 1
ORDER BY order_count DESC, channel;
~~~

Expect `web` = 2, `mobile` = 1, `store` = 1, and `(missing)` = 1.

A JSONB containment filter:

~~~sql
SELECT order_id, status
FROM explore_lab.orders
WHERE metadata @> '{"channel":"web"}'::jsonb
ORDER BY order_id;
~~~

The `@>` operator tests whether JSONB contains the given structure. Understanding how JSON is stored and which operators queries use gives you the basis to evaluate a **GIN index** on JSONB if a large workload genuinely requires one.

### 11.4. Exploring arrays

~~~sql
SELECT
    product_id,
    product_name,
    tags
FROM explore_lab.products
WHERE 'office' = ANY(tags)
ORDER BY product_id;
~~~

Expect `Keyboard` and `Monitor`. PostgreSQL supports arrays and array operators; do not assume array data uses the same query syntax as JSONB.

## 12. Counting rows and estimating table size

### 12.1. Exact COUNT(*)

~~~sql
SELECT COUNT(*) AS exact_rows
FROM explore_lab.orders;
~~~

In the lab, the result is 5. However, with PostgreSQL and MVCC, an exact `COUNT(*)` on a very large table typically must inspect many tuples or index entries visible to the snapshot. It **is not automatically an O(1) lookup of a stored total**.

### 12.2. Estimating via statistics

~~~sql
SELECT
    schemaname,
    relname,
    n_live_tup,
    n_dead_tup,
    last_analyze,
    last_autoanalyze
FROM pg_stat_user_tables
WHERE schemaname = 'explore_lab'
ORDER BY relname;
~~~

- `n_live_tup` is a statistical **estimate** of live rows.
- `n_dead_tup` is a statistical **estimate** of dead tuples.
- `last_analyze` and `last_autoanalyze` indicate when statistics were updated (if ever).

These numbers may be 0 or stale on newly created tables. Never treat them as exact row counts, and visibility of statistics may be restricted by permissions.

Another approach:

~~~sql
SELECT
    c.oid::regclass AS relation_name,
    c.reltuples::bigint AS estimated_rows
FROM pg_class AS c
JOIN pg_namespace AS n
  ON n.oid = c.relnamespace
WHERE n.nspname = 'explore_lab'
  AND c.relkind = 'r'
ORDER BY c.relname;
~~~

`reltuples` is also an **estimate** and may not reflect recent changes.

### 12.3. Table and index sizes

~~~sql
SELECT
    pg_size_pretty(pg_relation_size('explore_lab.orders'::regclass))
        AS table_heap_size,
    pg_size_pretty(pg_indexes_size('explore_lab.orders'::regclass))
        AS indexes_size,
    pg_size_pretty(pg_total_relation_size('explore_lab.orders'::regclass))
        AS total_relation_size;
~~~

Where:

- `pg_relation_size` (without a fork argument) measures the main fork of the relation.
- `pg_indexes_size` measures the total size of associated indexes.
- `pg_total_relation_size` includes table heap, indexes, TOAST, and related components per function definition.

Actual sizes depend on data, version, storage layout, and bloat; do not compare them directly against byte sizes of CSV files or SQL dumps.

To find the largest tables in a schema:

~~~sql
SELECT
    c.oid::regclass AS table_name,
    pg_size_pretty(pg_total_relation_size(c.oid)) AS total_size
FROM pg_class AS c
JOIN pg_namespace AS n
  ON n.oid = c.relnamespace
WHERE n.nspname = 'explore_lab'
  AND c.relkind IN ('r', 'p')
ORDER BY pg_total_relation_size(c.oid) DESC;
~~~

For partitioned tables (`relkind = 'p'`), understand parent versus partition sizes separately; do not assume the parent relation size equals the sum of all partitions unless aggregated intentionally.

## 13. Exploring indexes and access methods

### 13.1. Listing index definitions

~~~sql
SELECT
    schemaname,
    tablename,
    indexname,
    indexdef
FROM pg_indexes
WHERE schemaname = 'explore_lab'
ORDER BY tablename, indexname;
~~~

Expect to see primary-key/unique-key indexes and the explicitly created `idx_orders_customer_time`.

In psql:

~~~text
\di explore_lab.*
\d+ explore_lab.orders
~~~

In pgAdmin: expand **Indexes** under the table and view each index's DDL/Properties.

### 13.2. Why an existing index might not be used

~~~sql
EXPLAIN
SELECT
    order_id,
    customer_id,
    ordered_at
FROM explore_lab.orders
WHERE customer_id = 1
ORDER BY ordered_at DESC
LIMIT 10;
~~~

On a five-row table, `Seq Scan` is cheaper than traversing an index. PostgreSQL chooses plans based on statistics and estimated cost, not on whether a developer hopes to see `Index Scan`.

On a large table with many orders across many customers, an index starting with `customer_id` can help this query. To draw conclusions, check **the execution plan on representative data**, not a tiny few-row test.

### 13.3. Do not create indexes arbitrarily

Indexes speed up certain queries but increase the cost of `INSERT`, `UPDATE`, `DELETE`, and storage. An index suited for `WHERE customer_id = ...` will not necessarily help a full-table `GROUP BY status` report.

When your task is strictly **exploration**, focus on **observing** existing indexes. Adding or dropping indexes belongs to a reviewed design and schema-change phase, not an immediate reflex upon seeing a slow query.

## 14. Interpreting query plans with EXPLAIN

### 14.1. EXPLAIN estimates only

~~~sql
EXPLAIN
SELECT
    o.order_id,
    o.total_amount,
    c.full_name
FROM explore_lab.orders AS o
JOIN explore_lab.customers AS c
  ON c.customer_id = o.customer_id
WHERE o.status = 'PAID'
ORDER BY o.order_id;
~~~

You may see nodes such as:

| Node | Role |
|---|---|
| `Seq Scan` | Sequential scan of the table |
| `Index Scan` | Uses an index to locate positions and reads matching rows |
| `Index Only Scan` | Reads directly from the index when visibility conditions permit |
| `Bitmap Index Scan` / `Bitmap Heap Scan` | Collects candidate locations from an index and reads heap pages via bitmap |
| `Nested Loop` | Joins tables using nested iteration |
| `Hash Join` | Builds/probes a hash table to join |
| `Merge Join` | Joins two appropriately sorted inputs |
| `HashAggregate` | Computes groups using a hash structure |
| `GroupAggregate` | Computes groups over pre-sorted input |
| `Sort` | Sorts intermediate results |
| `Limit` | Caps returned rows |

`cost=...` and `rows=...` in `EXPLAIN` are **optimizer estimates**, not milliseconds or actual rows read.

### 14.2. EXPLAIN ANALYZE executes the query

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    status,
    COUNT(*) AS order_count,
    SUM(total_amount) AS total_value
FROM explore_lab.orders
GROUP BY status
ORDER BY status;
~~~

`ANALYZE` causes PostgreSQL to **actually run the query** and report actual timings and row counts; `BUFFERS` reports buffer activity. If applied to `UPDATE` or `DELETE`, the DML actually executes. Therefore, during safe exploration, start with `EXPLAIN ANALYZE` only on bounded, non-heavy `SELECT` queries.

`EXPLAIN (ANALYZE, BUFFERS)` on a large read query still consumes CPU and I/O and can affect active workloads; never run it carelessly on production during peak hours.

### 14.3. Questions to ask when reading a plan

1. Which table is accessed first, and why?
2. Are `WHERE` filters applied early or only after scanning many rows?
3. How many `rows` did PostgreSQL estimate at each node? Does `actual rows` differ drastically?
4. Are there large sorts, hashes, or temporary disk files?
5. How many input rows had to be processed to return just five output rows?
6. After measuring, can a filter be rewritten or an appropriate index considered?

Do not optimize just to eliminate a `Sort` node on a handful of rows. The goal is **correctness and overall cost** under real workloads.

## 15. Exploring sessions and system activity

### 15.1. Current session/transaction details

~~~sql
SELECT
    current_database(),
    current_user,
    current_setting('transaction_isolation') AS isolation_level,
    current_setting('statement_timeout') AS statement_timeout,
    current_setting('TimeZone') AS session_timezone;
~~~

In particular, `statement_timeout` may be configured at the role, database, or session level to stop runaway SQL. Do not change global settings just because an exploratory query needs more time.

### 15.2. pg_stat_activity

~~~sql
SELECT
    pid,
    usename,
    datname,
    state,
    wait_event_type,
    wait_event,
    query_start
FROM pg_stat_activity
WHERE datname = current_database()
ORDER BY query_start NULLS LAST
LIMIT 30;
~~~

Visibility depends on privileges. A normal role may see full details only for its own sessions and restricted details for other users' sessions. Never assume you have permission to read every user's SQL text.

Common states:

- `active`: the session is currently executing a statement.
- `idle`: the connection is idle, possibly waiting in a connection pool.
- `idle in transaction`: the session has an open transaction but is not currently running a statement; staying in this state too long warrants investigation.

Never run `pg_terminate_backend` or `pg_cancel_backend` merely while exploring without proper authorization and operational responsibility; they can interrupt someone else's work.

### 15.3. Visibility depends on permissions

A read-only data account does not necessarily have permission to inspect all system statistics, other roles, or specialized object definitions. If you encounter `permission denied`, request the exact privileges needed; **do not use superuser for everyday exploration** just to avoid a metadata error.

## 16. Exploring safely in production

A `SELECT` query can still impose heavy load or expose sensitive information. Distinguish **not modifying data** from **having zero impact**.

### 16.1. Use a read-only role

Example permission model set up by an administrator on an authorized database:

~~~sql
-- Administrator example; DO NOT run on production
-- without authorization/approval:
CREATE ROLE explore_reader LOGIN;

GRANT CONNECT ON DATABASE learning_db TO explore_reader;
GRANT USAGE ON SCHEMA explore_lab TO explore_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA explore_lab TO explore_reader;
~~~

This is a **privilege pattern**, not a complete account-provisioning workflow: you must also handle authentication, password/secret management, default privileges for future tables, row-level security, sequence/function permissions, and network access policies. Newly created objects will not automatically inherit privileges without proper default privileges configured.

### 16.2. Read-only transactions when needed

~~~sql
BEGIN READ ONLY;
SET LOCAL statement_timeout = '5s';

SELECT order_id, status, total_amount
FROM explore_lab.orders
ORDER BY order_id
LIMIT 20;

COMMIT;
~~~

- `BEGIN READ ONLY` starts a transaction flagged read-only, preventing most SQL write operations inside the transaction.
- `SET LOCAL` scopes the setting to the current transaction.
- `statement_timeout` caps SQL execution duration, though it does not guarantee every I/O or operation is harmless.
- `COMMIT`/`ROLLBACK` closes the transaction so the session does not sit `idle in transaction`.

**Do not treat a read-only transaction as your sole security layer.** Role privileges and RLS policies govern which objects and rows a user can read. A `SELECT` can also invoke a function with side effects if permissions allow; always review SQL before executing it.

### 16.3. Avoiding unnecessarily expensive queries

- Prefer filtering by indexed keys or selective time ranges.
- Never run `COUNT(*)` on a billion-row table just to see "how big it is"; start with statistical estimates.
- Never run `SELECT *` across all columns and rows on tables holding sensitive data.
- Never run `EXPLAIN ANALYZE` on unassessed SQL during peak production load.
- Never leave an open transaction sitting idle in a SQL client for hours.
- Never export personal data to CSV or the clipboard without a clear purpose and authorization.
- Specify server/schema explicitly in scripts to avoid operating on the wrong environment.

### 16.4. Do not treat LIMIT as complete protection

`LIMIT 100` reduces the number of **returned** rows, but a complex `ORDER BY`, aggregate, or join may still process massive amounts of data first. Execution timeouts, permissions, and selective filter conditions remain essential.

## 17. Exporting data with psql and saving exploration findings

### 17.1. Client-side CSV export with \copy

In psql, the command:

~~~text
\copy (SELECT order_id, status, total_amount FROM explore_lab.orders ORDER BY order_id) TO 'orders_sample.csv' WITH (FORMAT csv, HEADER true)
~~~

writes the file on **the machine running psql**, under the client process's permissions. The `\copy` meta-command differs from SQL `COPY ... TO '/path/file'`, which writes on the PostgreSQL Server side and requires special server privileges.

From the terminal, you can run:

~~~bash
psql -h db-lab.example.internal -U report_reader -d learning_db \
  -c "\copy (SELECT order_id, status, total_amount FROM explore_lab.orders ORDER BY order_id LIMIT 100) TO 'orders_sample.csv' WITH (FORMAT csv, HEADER true)"
~~~

Exported files may contain sensitive data. Export minimal data to authorized directories and follow retention/deletion policies.

### 17.2. Saving an exploration script

An `inspect_explore_lab.sql` file can hold queries such as:

~~~sql
-- 1) Identify session.
SELECT current_database(), current_user;

-- 2) List tables.
SELECT table_name, table_type
FROM information_schema.tables
WHERE table_schema = 'explore_lab'
ORDER BY table_name;

-- 3) View a few recent orders by ID.
SELECT order_id, status, total_amount
FROM explore_lab.orders
ORDER BY order_id DESC
LIMIT 10;

-- 4) Status distribution.
SELECT status, COUNT(*) AS orders_count
FROM explore_lab.orders
GROUP BY status
ORDER BY status;
~~~

You can run the same file via pgAdmin Query Tool or `psql -f`. This script requires no write privileges and establishes a **repeatable inspection routine**.

When recording exploration findings, include:

- Database/server (never secrets).
- Schema, table names, and timestamp of inspection.
- PostgreSQL version if relevant.
- Exact SQL queries executed.
- Denominator, filter, and time-zone definitions for any metrics.
- Data precision: **exact COUNT** versus **statistical estimate**.

## 18. Common errors and how to diagnose them

| Symptom | Common cause | Check step |
|---|---|---|
| `connection refused` | Wrong host/port, server down, firewall, tunnel | Verify endpoint and network path |
| `password authentication failed` | Wrong credentials or auth method | Check user, password, and `pg_hba.conf` with admin help |
| `database does not exist` | Wrong database selected or not yet created | Verify the database exists on the intended server |
| `permission denied for schema` | Missing `USAGE` on schema | Check role grants |
| `permission denied for table` | Missing `SELECT` or blocked by RLS/role | Check object grants and policies |
| `relation "orders" does not exist` | Wrong schema, wrong `search_path`, or quoted uppercase name | Use `explore_lab.orders`, check `\dt` |
| Table visible in pgAdmin but query fails | Query Tool connected to a different database or schema | Run `current_database()`, `SHOW search_path` |
| Timestamps shifted by several hours | Display time zone differs from expected | Check `TimeZone`, `AT TIME ZONE` |
| `LIMIT` returns different rows | Missing deterministic `ORDER BY` | Add `ORDER BY` including a unique key |
| `COUNT(*)` is very slow | Table is huge, scanning many tuples | Check `pg_stat_user_tables` if an estimate suffices |
| Index exists yet `Seq Scan` is chosen | Small table, low selectivity, or stale stats | Inspect `EXPLAIN`; don't force indexes blindly |
| Function definition not visible | Insufficient privileges or client filter settings | Check permissions and `pg_catalog` |
| Query Tool shows fewer rows than expected | Client row limit/pagination or SQL limit | Compare the SQL query against tool grid settings |
| Query times out | `statement_timeout`, network, locks, or client timeout | Read error message and identify where timeout is enforced |

### 18.1. Uppercase or special-character names

PostgreSQL folds **unquoted** identifiers to lowercase:

~~~sql
SELECT * FROM explore_lab.orders;

-- If a table was created with exact quoted identifier "SalesOrders":
SELECT * FROM explore_lab."SalesOrders";
~~~

`"SalesOrders"` and `salesorders` are not the same identifier in PostgreSQL. Avoid unnecessary quoted camel-case identifiers when designing new schemas; for existing schemas, match the exact identifier casing.

### 18.2. Confusing VIEW with MATERIALIZED VIEW

A regular view is defined by a query and reads source tables per the active snapshot. A materialized view persists materialized results and can be **stale** until `REFRESH MATERIALIZED VIEW` runs. When inspecting a reporting object, verify its type before assuming it reflects every recent commit.

### 18.3. Confusing NULL with client display strings

Some tools render SQL `NULL` as an empty cell, `[null]`, or special highlighting. A blank cell in a GUI does not prove the value is an empty string. Verify with SQL:

~~~sql
SELECT
    COUNT(*) FILTER (WHERE metadata ->> 'channel' IS NULL) AS no_channel,
    COUNT(*) FILTER (WHERE metadata ->> 'channel' = '') AS empty_channel
FROM explore_lab.orders;
~~~

These two conditions answer two different questions.

## 19. Workflow for exploring an unfamiliar schema

Use the following checklist as a repeatable method:

~~~mermaid
flowchart TD
    A["Verify right server / database / role"] --> B["List schemas and objects"]
    B --> C["Inspect columns, types, PK/FK, CHECK, indexes"]
    C --> D["Read a few rows with ORDER BY and LIMIT"]
    D --> E["Inspect NULLs, distincts, min/max, and distributions"]
    E --> F["Verify business relationships with JOIN"]
    F --> G["Estimate size and inspect EXPLAIN plan"]
    G --> H["Document SQL, findings, and confidence level"]
~~~

Detailed breakdown:

1. **Verify connection:** `current_database()`, `current_user`, server, and time zone.
2. **List objects:** schemas, tables, views, and relevant objects.
3. **Understand structure:** column types, nullability, defaults, identity, check constraints, PK, unique, FK, and indexes.
4. **Inspect sample data:** a few intentionally ordered rows; avoid excessive extraction.
5. **Examine distributions:** distinct values, `NULL`s, date ranges, and grouped totals.
6. **Verify relationships:** confirm real foreign keys and write meaningful JOINs.
7. **Assess scale:** `COUNT(*)` only when reasonable, statistical estimates, and relation sizes.
8. **Review performance:** `EXPLAIN` first; `EXPLAIN ANALYZE` only when permitted and appropriate.
9. **Record findings:** scripts, observations, open questions, evidence sources, and access scope.

Crucially, **never turn data exploration into data modification** unless explicitly tasked with design or migration work.

## 20. Practice exercises

The exercises below use `explore_lab` populated in Section 6. No additional writes are needed.

### Exercise 1 — Identify the environment

Write a SQL query displaying the session's database, current user, default schema, and time zone. Explain why you should run this before working in Query Tool on a server hosting both staging and production.

### Exercise 2 — Find tables, columns, and types

Write SQL using `information_schema` to list all tables/views in `explore_lab`; then list all columns of `orders` in definition order. Identify the data types of `ordered_at` and `metadata`.

### Exercise 3 — Identify relationships

Write SQL or a meta-command to find the foreign key on `orders`. State the source table/column and referenced table/column. Then write a JOIN retrieving customer names for the orders.

### Exercise 4 — Examine status distribution

Count orders by `status` and sum `total_amount` per status. From the sample data, how many `PAID` orders exist and what is their total?

### Exercise 5 — Explore JSONB

List purchase channels (`metadata.channel`) and order counts per channel. How are orders missing the `channel` key distinguished from an empty string?

### Exercise 6 — Inspect indexes and explain a plan

List all indexes on `explore_lab.orders`. Write an `EXPLAIN` for querying customer 1's orders in descending chronological order. Why might PostgreSQL choose `Seq Scan` on the sample dataset despite having an index?

### Exercise 7 — Exact count vs. statistical estimate

Use `COUNT(*)` to count orders exactly. Then retrieve `n_live_tup` from `pg_stat_user_tables`. If the two numbers differ, does it mean data was lost?

### Exercise 8 — Safe exploration

You receive a read-only production connection where a table has 100 million orders. A manager asks, "Roughly how many rows does the table have and what are its columns?" Choose a sequence of steps that avoids immediately running `SELECT * FROM orders` or a full-table `COUNT(*)`.

### Exercise 9 — Distinguish client tools

Can `\d+ explore_lab.orders` be pasted verbatim and executed inside pgAdmin Query Tool? If not, what do you use in pgAdmin, and which SQL queries replace part of its functionality?

## 21. Suggested solutions

### Exercise 1

~~~sql
SELECT
    current_database(),
    current_user,
    current_schema(),
    current_setting('TimeZone');
~~~

This prevents making assumptions from a connection's display label, especially when multiple environments share identical table names.

### Exercise 2

~~~sql
SELECT table_name, table_type
FROM information_schema.tables
WHERE table_schema = 'explore_lab'
ORDER BY table_name;

SELECT ordinal_position, column_name, data_type, udt_name
FROM information_schema.columns
WHERE table_schema = 'explore_lab'
  AND table_name = 'orders'
ORDER BY ordinal_position;
~~~

`ordered_at` is `timestamp with time zone` (`timestamptz`); `metadata` is PostgreSQL type `jsonb`. The underlying type name appears in `udt_name`.

### Exercise 3

~~~sql
SELECT
    conname,
    pg_get_constraintdef(oid, true) AS definition
FROM pg_constraint
WHERE conrelid = 'explore_lab.orders'::regclass
  AND contype = 'f';

SELECT o.order_id, c.full_name
FROM explore_lab.orders AS o
JOIN explore_lab.customers AS c
  ON c.customer_id = o.customer_id
ORDER BY o.order_id;
~~~

The FK is `orders.customer_id → customers.customer_id`.

### Exercise 4

~~~sql
SELECT status,
       COUNT(*) AS order_count,
       SUM(total_amount) AS total_value
FROM explore_lab.orders
GROUP BY status
ORDER BY status;
~~~

There are **3 PAID orders**, totaling **2,850,000.00**. `NEW` and `CANCELLED` orders are excluded from paid revenue when business rules define revenue that way.

### Exercise 5

~~~sql
SELECT
    COALESCE(metadata ->> 'channel', '(missing)') AS channel,
    COUNT(*) AS cnt
FROM explore_lab.orders
GROUP BY 1
ORDER BY channel;
~~~

The sample data has `web = 2`, `mobile = 1`, `store = 1`, `(missing) = 1`. To distinguish a missing key from JSON null, use `metadata ? 'channel'`; an empty string is tested with `= ''`, which is distinct from `IS NULL`.

### Exercise 6

~~~sql
SELECT indexname, indexdef
FROM pg_indexes
WHERE schemaname = 'explore_lab'
  AND tablename = 'orders';

EXPLAIN
SELECT order_id, customer_id, ordered_at
FROM explore_lab.orders
WHERE customer_id = 1
ORDER BY ordered_at DESC
LIMIT 10;
~~~

PostgreSQL can choose `Seq Scan` because the table has only five rows and reading the whole heap is cheaper. Never force an index just to make a plan look "prettier."

### Exercise 7

~~~sql
SELECT COUNT(*) AS exact_rows
FROM explore_lab.orders;

SELECT n_live_tup, last_analyze, last_autoanalyze
FROM pg_stat_user_tables
WHERE schemaname = 'explore_lab'
  AND relname = 'orders';
~~~

`COUNT(*)` returns the exact count at the query's snapshot; `n_live_tup` is a **statistical estimate** and may be out of date. A discrepancy alone does not indicate data loss.

### Exercise 8

First verify server/role/schema, use `\d+` or `information_schema.columns` to inspect metadata; obtain estimated row counts from `pg_stat_user_tables.n_live_tup` or `pg_class.reltuples`, paired with `pg_total_relation_size` to gauge scale. If sample rows are needed, select non-sensitive columns with selective filters, `LIMIT`, and `ORDER BY`. Run an exact `COUNT(*)` only when cost, permissions, and purpose are approved.

### Exercise 9

No. `\d+` is a **psql** meta-command, not SQL. In pgAdmin, inspect **Columns**, **Constraints**, **Indexes**, and **Properties** in Object Explorer; or query `information_schema.columns`, `pg_constraint`, and `pg_indexes` via SQL for metadata.

## 22. Conclusion

Effective PostgreSQL exploration starts by **verifying the right connection**, then moving methodically from **schema → tables/views → columns/types → constraints/indexes → sample data → distributions/relationships → sizes/query plans**. pgAdmin helps visualize objects and run SQL in Query Tool; psql excels in terminals, scripts, and meta-commands like `\dt` and `\d+`. Other SQL clients support equivalent workflows.

Do not rely solely on how data appears in a result grid. **Verify with SQL and catalogs**: `information_schema` for portable metadata; `pg_catalog` for PostgreSQL specifics; `pg_stat_*` for statistical estimates; `EXPLAIN` for estimated plans; and `EXPLAIN ANALYZE` for actual execution metrics.

Above all, data exploration must be **safe and purposeful**: use least privilege, limit returned columns and rows, remember that large `SELECT` queries still consume resources, and keep repeatable scripts along with verifiable findings. Following these steps gives you a solid foundation to write accurate queries, understand the data model, and propose PostgreSQL optimizations without guessing from table names or UI labels.
