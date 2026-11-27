# Distinguishing Server, Database Cluster, Database, Schema, Table, and Row in PostgreSQL

## 1. Why Is Distinguishing Each Level Important?

When starting with PostgreSQL, the terms **server**, **cluster**, **database**, **schema**, **table**, and **row** are often used interchangeably. For instance, a development team might say "create a database for the app" when they actually just added a **schema** in an existing database; or "connected to the server" without knowing which **database** the session is in.

Distinguishing them properly helps you:

- Connect to the right PostgreSQL instance, database, and schema.
- Understand why two tables with the exact same name can coexist.
- Avoid confusing creating a database with creating a schema.
- Design access privileges and application separation sensibly.
- Read SQL statements, object paths, and `"relation does not exist"` errors accurately.
- Know at which level a query searches for **data rows**.
- Understand querying limits across two different databases in PostgreSQL.
- Avoid confusing a **PostgreSQL database cluster** with an **HA/replication server cluster**.

The basic hierarchy:

```text
Computer / VM / container (host)
└── PostgreSQL server instance
    └── Database cluster (initialized by initdb)
        ├── Cluster-wide shared objects
        │   ├── Roles / users
        │   └── Tablespaces, parameters, and certain system catalogs
        ├── Database: postgres
        ├── Database: app_db
        │   ├── Schema: public
        │   │   └── Table: public.settings
        │   ├── Schema: sales
        │   │   ├── Table: sales.customers
        │   │   │   ├── Row: customer_id = 1
        │   │   │   └── Row: customer_id = 2
        │   │   └── Table: sales.orders
        │   └── Schema: audit
        │       └── Table: audit.events
        └── Database: analytics_db
            └── Schema: reporting
                └── Table: reporting.daily_metrics
```

The diagram shows a **PostgreSQL instance serving a database cluster** containing multiple databases, each database having multiple schemas, and each schema containing tables and related objects. Each table can contain many rows.

Technically, **server instance** and **database cluster** are tightly coupled and are sometimes used interchangeably in operations. However, *server* emphasizes **the service processes and connections**; *database cluster* emphasizes **the collection of databases initialized and managed together in a single data directory**. The following sections explain this distinction in detail.

## 2. Quick Comparison of the Six Concepts

| Level | English Term | What Is It? | What Does It Contain or Manage? | Example |
|---|---|---|---|---|
| 1 | Server / PostgreSQL instance | Running PostgreSQL process set accepting connections and processing SQL | One database cluster served by the instance | PostgreSQL listening on `db.example.internal:5432` |
| 2 | Database cluster | Collection of databases plus global objects initialized in a data directory | Multiple databases, roles, tablespaces, and shared metadata | Cluster containing `postgres` and `app_db` databases |
| 3 | Database | Relatively independent storage/object space inside a cluster | Schemas and database-scoped objects | `app_db` |
| 4 | Schema | Namespace inside a database | Tables, views, sequences, functions, types… | `sales` |
| 5 | Table | Relation storing data by columns and rows | Rows along with column definitions, constraints, and associated indexes | `sales.orders` |
| 6 | Row | One logical record in a table | Column values for an entity or event | `(order_id=1001, status='PAID')` |

Key relationships:

- One **database cluster** can contain multiple databases.
- Each **database** has multiple schemas, with `public` commonly created by default.
- One **schema** can contain multiple tables.
- One **table** contains rows; each row conforms to the column definitions and corresponding constraints.
- **Roles** are managed at the cluster level, **not** scoped inside a single schema.
- Ordinary SQL statements execute within **one specific database** per connection.

**Note:** the table above shows the **logical** hierarchy. Physical storage files may reside in different tablespaces, and a large relation can span multiple segment files. Do not infer that every table always corresponds to exactly one single file on disk.

## 3. PostgreSQL Server: Processes Serving Connections

### 3.1. A Server Is Not Synonymous with a Physical Machine

A PostgreSQL **server instance** is a running PostgreSQL service with its own configuration, listening port, and data area. It can run:

- Directly on a personal computer.
- Inside a virtual machine.
- Inside a Docker container.
- On a cloud-managed PostgreSQL service.
- On the same host alongside one or more other PostgreSQL instances.

Thus, the phrase "one server" can be ambiguous:

- **Host**: the machine/VM/container running the software.
- **PostgreSQL server instance**: the PostgreSQL service processes serving one data cluster.

One host can run two PostgreSQL instances using two different **data directories** and two different **ports**. Conversely, an application might connect to a single cloud endpoint backed by multiple machines operated by the provider.

Example model of two instances on the same host:

```text
Host: db-lab
  ├── PostgreSQL instance A
  │     port: 5432
  │     data directory: /data/pg_a
  │     databases: postgres, app_db
  └── PostgreSQL instance B
        port: 5433
        data directory: /data/pg_b
        databases: postgres, test_db
```

These are illustrative paths. **Never share a data directory between two running PostgreSQL instances**; each instance must own and manage its own data directory.

### 3.2. How Does the Server Accept Requests?

When an application connects to PostgreSQL via JDBC, psycopg, or `psql`, it specifies:

1. **Host** or socket.
2. **Port** of the PostgreSQL server (typically `5432` by default).
3. **Database name**.
4. **User/role** for authentication.
5. Security/connection parameters such as TLS, depending on the environment.

Example connection using `psql`:

```sh
psql -h 127.0.0.1 -p 5432 -U app_user -d app_db
```

In PostgreSQL, a connection is bound to one specific **database**. After connecting, you can select schemas via qualified names or `search_path`, but you cannot arbitrarily switch to another database with an SQL statement like `USE other_database`.

### 3.3. Inspecting the Connected Instance

In an active session:

```sql
SELECT
    current_database() AS database_name,
    current_user AS effective_role,
    session_user AS login_role,
    inet_server_addr() AS server_ip,
    inet_server_port() AS server_port,
    pg_postmaster_start_time() AS server_start_time;
```

Meanings:

- `current_database()`: database of the current connection.
- `current_user`: role currently used for privilege checks in the session.
- `session_user`: initial login role (may differ when `SET ROLE` is used).
- `inet_server_addr()` and `inet_server_port()`: server-side TCP address/port.
- `pg_postmaster_start_time()`: timestamp when the PostgreSQL instance was started.

If connected over a Unix-domain socket, the IP address/port functions may return `NULL`. That does **not** mean the connection failed.

In `psql`, the client command:

```text
\conninfo
```

reports connection details such as the current database, user, host, and port. This is a **psql meta-command**, not standard SQL sent directly over JDBC.

## 4. Database Cluster: A Collection of Jointly Managed Databases

### 4.1. Clusters Are Created by `initdb`

In PostgreSQL, **database cluster** is the technical term for the collection of databases managed by one PostgreSQL server instance. It is typically initialized with `initdb`, which prepares the **data directory**, initial system catalogs, and default databases.

Illustrative administrative syntax:

```sh
initdb -D /path/to/new/data-directory
```

**Never run this command against a data directory that already contains real data.** This tool is for initializing a new cluster, not a command to run each time you want to create an additional database.

A typical PostgreSQL cluster starts with these initial databases:

- `postgres`: commonly used as an administrative/maintenance database.
- `template1`: default template copied when creating new databases.
- `template0`: special baseline template, useful when creating a clean database with custom encoding/locale rules.

All of these databases belong to the same **cluster**; `postgres` is not a separate "server" or "cluster" just because it shares a name with the product.

### 4.2. Which Objects Are Shared Cluster-Wide?

Certain information is managed **cluster-wide**, typically:

- **Roles/users**: identities and login privileges.
- **Tablespaces**: physical storage locations usable by objects across databases.
- The list of **databases**.
- Certain shared catalogs and instance-level parameters.

In `pg_catalog`, `pg_database` stores the list of databases; `pg_roles` lets you inspect visible role information.

Example:

```sql
SELECT datname, datallowconn
FROM pg_database
ORDER BY datname;

SELECT rolname, rolcanlogin
FROM pg_roles
ORDER BY rolname;
```

**Not every catalog is shared cluster-wide.** Schema lists, tables, and most relational metadata are stored **per database**. Therefore, to inspect tables in another database, you usually must connect to that database rather than querying `pg_class` on the current connection and expecting to see the whole cluster.

### 4.3. "Database Cluster" vs. "HA/Replication Cluster"

This is one of the easiest points to confuse:

| Term | In PostgreSQL, Usually Refers To |
|---|---|
| **Database cluster** | Collection of databases created and managed by one instance/data directory |
| **HA cluster** | Multiple machines/instances coordinating to provide high availability |
| **Primary/standby topology** | Primary accepts writes; standby receives and replays WAL per configuration |
| **Cluster orchestrator** | Software coordinating failover/leader election, such as environment-specific HA tools |

A database cluster as defined by `initdb` **does not require multiple machines**. Conversely, an HA system may consist of multiple PostgreSQL instances, each with its own data directory; those instances replicate or switch roles without sharing a single data directory.

When documentation says "deploy a PostgreSQL cluster," read the context carefully: does it mean **initializing a data directory** or **deploying multi-node HA**?

## 5. Database: Connection Boundary and Object Space

### 5.1. Databases Live Inside a Cluster

A cluster can contain multiple databases:

```text
PostgreSQL database cluster
├── postgres
├── billing_db
├── crm_db
└── analytics_db
```

Each database has its own schemas, tables, views, functions, and data. Two different databases can both have a `public` schema and a `public.users` table, yet they are **two distinct objects**.

Example:

```text
billing_db.public.users     -- table in billing_db
crm_db.public.users         -- table in crm_db
```

The account `app_user` may be a **cluster-wide shared role**, while `CONNECT` privileges and object permissions inside each database are separate concerns. Being able to access `billing_db` does not automatically grant access to tables in `crm_db`.

### 5.2. Creating a Database: Privileges and Rules

In a connection with appropriate privileges, such as a role with the `CREATEDB` attribute:

```sql
CREATE DATABASE pg_intro_24;
```

`CREATE DATABASE` creates **a new database inside the existing cluster**. It does not start a new PostgreSQL instance, open a new port, or re-initialize the cluster.

One technical caveat: `CREATE DATABASE` **cannot run inside a transaction block** such as:

```sql
-- Invalid:
BEGIN;
CREATE DATABASE pg_intro_24;
COMMIT;
```

If you lack `CREATEDB` or equivalent privileges, use the lab database provisioned by your administrator. Do not request or use superuser privileges merely for table-creation exercises.

### 5.3. Selecting a Database for a Connection

Using `psql` to connect directly:

```sh
psql -h localhost -p 5432 -U lab_user -d pg_intro_24
```

Inside an open `psql` session, you can **disconnect and reconnect** to another database with the meta-command:

```text
\connect pg_intro_24
```

or the shorthand:

```text
\c pg_intro_24
```

This is a **psql client** command, not an SQL statement running inside the server. PostgreSQL **does not support** the MySQL-style statement:

```sql
-- Not valid PostgreSQL syntax:
USE pg_intro_24;
```

In Java/JDBC, the database is specified in the JDBC URL or connection parameters, for example:

```text
jdbc:postgresql://127.0.0.1:5432/pg_intro_24
```

To operate on a different database, an application normally needs to open a **separate connection** pointing to that database.

### 5.4. Can You Query Directly Across Two Databases?

Within a standard PostgreSQL connection, you can query multiple **schemas in the same database** using two-part `schema.table` names, but you cannot join two tables in different databases simply by writing:

```sql
-- Do not use this syntax to read another database:
SELECT *
FROM other_database.public.customers;
```

PostgreSQL does not support cross-database queries like this via ordinary SQL; if the database name points to a different database, you will encounter an error such as **cross-database references are not implemented**.

If cross-database communication is genuinely required:

- Connect separately to each database at the application layer.
- Use appropriate tools/extensions such as `postgres_fdw` or `dblink` if infrastructure allows.
- Synchronize data via ETL, messages/events, or well-designed integration pipelines.

Each option carries its own overhead, permissions, and transaction semantics. Do not split tables into separate databases just for grouping if business workflows require frequent joins and tight transactions across them.

## 6. Schema: Namespace Inside a Database

### 6.1. A Schema Is Not a Database

A **schema** is a **namespace** inside a database. It helps group and name objects:

```text
Database: pg_intro_24
├── Schema: public
│   ├── Table: settings
│   └── View: current_settings
├── Schema: sales
│   ├── Table: customers
│   ├── Table: orders
│   └── Sequence: order_seq
└── Schema: audit
    └── Table: events
```

Note: sequences, views, functions, and data types are also schema-scoped objects. A schema is not simply a "data folder" holding only tables.

Two schemas in the same database can contain tables with identical names:

```text
sales.events
audit.events
```

They are not the same table. The query:

```sql
SELECT * FROM sales.events;
```

refers specifically to the object in the `sales` schema of the current database.

### 6.2. Creating Schemas

After connecting to the lab database, you can run:

```sql
CREATE SCHEMA IF NOT EXISTS sales;
CREATE SCHEMA IF NOT EXISTS audit;
```

Creating a schema **does not** create a new database. This command requires `CREATE` privilege on the database or appropriate administrative/ownership privileges. If you only have access to an existing schema, use the schema provided by the administrator instead of escalating privileges.

List schemas via SQL:

```sql
SELECT schema_name
FROM information_schema.schemata
ORDER BY schema_name;
```

Or in `psql`:

```text
\dn
```

Results from `information_schema` may depend on the connected role's privileges. System schemas such as `pg_catalog`, `information_schema`, and `pg_toast` serve different purposes from application schemas; do not create business tables in them.

### 6.3. The `public` Schema

When a standard PostgreSQL database is created, the `public` schema typically exists already, so:

```sql
CREATE TABLE customers (
    customer_id bigint PRIMARY KEY
);
```

can create `public.customers` **if the current search path resolves to `public` as a valid schema for creating objects**.

However, do not assume every user has permission to create tables in `public`. In databases newly created by PostgreSQL 15 and later, the `CREATE` privilege on `public` is restricted by default compared to older PostgreSQL installations; upgraded or administrator-customized setups may differ.

When teaching or writing migrations, using an **explicit schema** is clearer:

```sql
CREATE TABLE sales.customers (
    customer_id bigint PRIMARY KEY
);
```

This avoids depending on whatever `search_path` happens to be configured.

## 7. Qualified Names and the `search_path` Mechanism

### 7.1. What Does `schema.table` Mean?

In PostgreSQL, schema-qualified object names are typically written as:

```text
schema_name.table_name
```

Example:

```sql
SELECT * FROM sales.customers;
SELECT * FROM audit.events;
```

A two-part name explicitly identifies the **schema** and **table** in the current database. PostgreSQL supports multi-part identifier syntax in certain contexts, yet that is **not** an arbitrary cross-database query mechanism as many beginners assume.

### 7.2. When Schema Is Omitted, Where Does PostgreSQL Look for the Table?

If you write:

```sql
SELECT * FROM customers;
```

PostgreSQL resolves the object using **`search_path`**. Inspect the setting:

```sql
SHOW search_path;

SELECT current_schema();

SELECT current_schemas(true);
```

A common default value is:

```text
"$user", public
```

Meaning: PostgreSQL checks a schema matching the current role name if that schema exists and is accessible, followed by `public`. System schemas like `pg_catalog` have special lookup rules and may appear in the effective schema list even when not explicitly listed.

If the database contains:

```text
sales.customers
public.customers
```

then `SELECT * FROM customers` can resolve to **different tables** if `search_path` changes.

Example adjustment in a lab session:

```sql
SET search_path TO sales, public;

SELECT * FROM customers;        -- prefers sales.customers
SELECT * FROM public.customers; -- always explicitly targets public
```

These comments assume both tables exist and the role has appropriate privileges.

### 7.3. Risks of `search_path`

`search_path` affects not only table names, but also resolution of certain functions, types, and operators. Placing a schema where untrusted users can create objects at the front of the search path introduces the risk of resolving an unintended object.

Practical safeguards:

- In migrations or sensitive tasks, prefer explicit `schema.table` names.
- Configure `CREATE` privileges on schemas carefully; never let untrusted roles create objects in schemas prioritized by critical applications.
- Verify `SHOW search_path` in **the application's own connection**, not only in a DBA session.
- Avoid relying on unqualified table names to guarantee the application is reading the intended data.

### 7.4. Schemas Cannot Be Nested Inside Schemas

The hierarchy:

```text
database -> schema -> table
```

is not equivalent to a nested directory layout:

```text
database -> schema -> schema -> table
```

In PostgreSQL, schemas are a **single-level namespace inside a database**; there are no direct sub-schemas like subdirectories in a filesystem.

If multi-tier grouping is needed, use naming conventions, parallel schemas, application modules, or appropriate relational models rather than assuming `sales.eu.orders` denotes a schema `eu` inside `sales`.

## 8. Table: A Relation with Columns, Rows, and Constraints

### 8.1. What Is a Table?

A **table** holds rows conforming to a defined column structure. Example customers table:

| customer_id | full_name | email |
|---:|---|---|
| 1 | An Nguyễn | an@example.test |
| 2 | Bình Trần | binh@example.test |

Concepts:

- **Table name**: `customers`.
- **Containing schema**: e.g., `sales`.
- **Columns**: `customer_id`, `full_name`, `email`.
- **Data types**: `bigint`, `text`, …
- **Constraints**: `PRIMARY KEY`, `NOT NULL`, `UNIQUE`, `CHECK`, `FOREIGN KEY`.
- **Row**: a tuple of values for the columns, e.g., the customer with `customer_id = 1`.

In PostgreSQL system catalogs, many objects are collectively referred to as **relations**, including tables, views, materialized views, sequences, and several other relation kinds. **Not every relation is a table storing business rows like an ordinary table.**

### 8.2. Creating a Table with a Primary Key

In a lab database with the `sales` schema already created:

```sql
CREATE TABLE sales.customers (
    customer_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    full_name text NOT NULL,
    email text NOT NULL UNIQUE
);
```

Explanation:

- `GENERATED ALWAYS AS IDENTITY`: PostgreSQL manages generating identifier values on insert via the identity mechanism.
- `PRIMARY KEY`: each row must have a distinct, non-NULL primary key.
- `NOT NULL`: the column requires a non-NULL value.
- `UNIQUE`: emails cannot duplicate under the column's comparison/constraint rules and configuration.

`bigint` is a large integer type; `text` stores variable-length text. Do not treat `customer_id` as a "physical position on disk"; it is a **logical identifier** for the data.

### 8.3. Creating an Orders Table and Linking Two Tables

```sql
CREATE TABLE sales.orders (
    order_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id bigint NOT NULL,
    total_amount numeric(12, 2) NOT NULL CHECK (total_amount >= 0),
    status text NOT NULL DEFAULT 'NEW',
    placed_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT fk_orders_customer
        FOREIGN KEY (customer_id)
        REFERENCES sales.customers(customer_id)
);
```

Here:

- `orders` and `customers` are **two tables in the same schema**.
- The `customer_id` column in `orders` references the primary key of `customers`.
- `numeric(12,2)` suits two-decimal monetary examples.
- `timestamptz` represents a point in time with time zone semantics in PostgreSQL; display formatting depends on the session time zone.
- `CHECK (total_amount >= 0)` blocks negative values per the constraint rule; if the domain requires negative refunds, design a dedicated model for that operation.

A **database** can have dozens of schemas, a **schema** can have hundreds of tables, and a **table** can hold millions of rows. These counts alone do not dictate how to split schemas or databases; base the choice on permissions, deployment lifecycles, data coupling, and operational needs.

## 9. Row: A Logical Data Unit, Not a Tiny File

### 9.1. Inserting Rows into a Table

Assuming `sales.customers` has been created:

```sql
INSERT INTO sales.customers (full_name, email)
VALUES
    ('An Nguyễn', 'an@example.test'),
    ('Bình Trần', 'binh@example.test')
RETURNING customer_id, full_name, email;
```

Each tuple in `VALUES` creates one **logical row**. `RETURNING` returns data from the newly inserted rows, which is especially helpful when primary keys are generated by the database.

Next, create an order by looking up the customer key by email:

```sql
INSERT INTO sales.orders (customer_id, total_amount, status)
SELECT customer_id, 150000.00, 'PAID'
FROM sales.customers
WHERE email = 'an@example.test'
RETURNING order_id, customer_id, total_amount, status;
```

The inner `SELECT` must match the intended customer. Because `email` has a `UNIQUE` constraint, a lookup by a valid email returns at most one row in this example.

Reading the data:

```sql
SELECT customer_id, full_name, email
FROM sales.customers
ORDER BY customer_id;

SELECT order_id, customer_id, total_amount
FROM sales.orders
ORDER BY order_id;
```

### 9.2. A Row Has No "Natural Sequence Number"

When running:

```sql
SELECT * FROM sales.customers;
```

PostgreSQL **makes no guarantee** on return order without `ORDER BY`. Data may be retrieved via a sequential scan, index scan, or another plan; ordering can change after `UPDATE`, `VACUUM`, index changes, or optimizer plan changes.

If a UI requires customers ordered by ascending ID, state it explicitly:

```sql
SELECT customer_id, full_name
FROM sales.customers
ORDER BY customer_id;
```

A `PRIMARY KEY` guarantees uniqueness; it **does not** mean every `SELECT` automatically sorts by the primary key.

### 9.3. Which Rows Do UPDATE/DELETE Modify?

```sql
UPDATE sales.customers
SET full_name = 'An Nguyễn (new)'
WHERE email = 'an@example.test'
RETURNING customer_id, full_name;

DELETE FROM sales.orders
WHERE status = 'CANCELLED'
RETURNING order_id;
```

`WHERE` determines which logical rows are affected; `RETURNING` tells the application which rows were actually modified or deleted. In production systems, `DELETE` may be blocked by foreign key constraints, or business rules may call for status flags rather than physical deletion.

Never write `UPDATE sales.customers SET ...` or `DELETE FROM sales.orders` without `WHERE` when intending to affect only a few rows: doing so can modify **the entire table**.

### 9.4. Rows and Tuples in PostgreSQL/MVCC

At the SQL level, a **row** is a logical record. At the PostgreSQL implementation level, physical versions of a row are commonly called **tuples**. PostgreSQL uses **MVCC** (*Multi-Version Concurrency Control*) to allow multiple transactions to read and write concurrently according to isolation level and snapshot state.

Example:

1. Transaction A is reading a snapshot where the customer's name is `An Nguyễn`.
2. Transaction B updates the name and commits.
3. A may continue seeing the old version depending on isolation level and read snapshot.
4. A new transaction sees the updated version.

Physically, an `UPDATE` can create a **new tuple version** rather than overwriting old data in place. Obsolete versions are cleaned up by vacuum mechanisms under the relevant conditions.

Therefore:

- **One logical row** does not always correspond to one fixed physical location.
- The system column `ctid` locates a physical tuple version at query time, **not a stable business key**; `UPDATE` and maintenance operations can change its location.
- To reference rows across tables or from applications, use an appropriate **primary key/unique key**, never `ctid` as a durable identifier.

## 10. At Which Levels Are Privileges Applied?

Distinguishing these levels also helps avoid two mistakes: **granting overly broad privileges** or **assuming privileges are in place yet still hitting query errors**.

| Object Level | Typical Privileges / Attributes | Meaning |
|---|---|---|
| Server/cluster | Roles with `LOGIN`, `CREATEDB`, `CREATEROLE`… | Who can log in or manage high-level objects |
| Database | `CONNECT`, `CREATE`, `TEMPORARY` | Can connect and create schemas/appropriate objects |
| Schema | `USAGE`, `CREATE` | Can resolve/access objects in the schema or create objects |
| Table | `SELECT`, `INSERT`, `UPDATE`, `DELETE`… | Allowed to read/write table rows per policy |
| Column | Certain column-level privileges | Restricts operations to specific columns |
| Row | **Row-Level Security (RLS)** policies if designed and enabled | Restricts which rows a role can view/modify |

For example, a read-only reporting role might need:

```sql
-- Executed by an owner/administrator with appropriate privileges.
GRANT CONNECT ON DATABASE pg_intro_24 TO app_reader;
GRANT USAGE ON SCHEMA sales TO app_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA sales TO app_reader;
```

This assumes the `app_reader` role already exists. `CONNECT` only permits entering the database—it **does not automatically grant read access to all tables**; `USAGE` on a schema allows resolving objects inside it by name, yet **does not automatically grant SELECT on individual tables**.

Notes:

- Roles are **cluster-level** objects, whereas table privileges belong to a specific database.
- `GRANT SELECT ON ALL TABLES IN SCHEMA sales` applies to **tables existing in the schema at that moment**; tables created **later** may require `ALTER DEFAULT PRIVILEGES` configured for the role creating those tables.
- RLS provides finer-grained control at the **row level**; PostgreSQL does not automatically put each row in its own schema.
- Object privileges, ownership, role membership, and default privileges can all affect actual outcomes; always test using the application's own account.

### 10.1. Why Is Separating Schemas Useful?

Within one database, creating `sales`, `audit`, and `reporting` schemas helps:

- Separate object names and avoid collisions.
- Grant permissions by module.
- Partition migration and ownership responsibilities.
- Organize related tables while keeping **convenient joins and transactions** inside the same database.

However, **a schema is not an isolated database in terms of resources**. Schemas in the same database still share the instance, database-level settings, WAL/transaction infrastructure, and operational resources. If you need separate upgrade cycles, connection policies, or stronger operational isolation, consider separate databases or separate instances.

## 11. End-to-End Practice: From Database Down to Rows

The following walkthrough uses a dedicated lab database and does not require superuser privileges for row/table operations if the role has sufficient permissions.

### Step 1: Connect to the Right Database

With `CREATEDB` privilege in a test environment, an administrator or authorized role can run:

```sql
CREATE DATABASE pg_intro_24;
```

Without that privilege, use your pre-provisioned test database and substitute `pg_intro_24` in the relevant commands. Do not run `CREATE DATABASE` inside `BEGIN ... COMMIT`.

Connect with `psql`:

```text
\connect pg_intro_24
```

Verify:

```sql
SELECT current_database(), current_user;
```

Expect `current_database()` to reflect the database you just connected to.

### Step 2: Create a Dedicated Schema

```sql
CREATE SCHEMA IF NOT EXISTS lab24;
```

This creates only a `lab24` namespace **inside the current database**, not a second database.

In `psql`:

```text
\dn
```

### Step 3: Create Two Tables in the Schema

```sql
CREATE TABLE lab24.customers (
    customer_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    full_name text NOT NULL,
    email text NOT NULL UNIQUE
);

CREATE TABLE lab24.orders (
    order_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id bigint NOT NULL
        REFERENCES lab24.customers(customer_id),
    amount numeric(12, 2) NOT NULL CHECK (amount >= 0),
    status text NOT NULL DEFAULT 'NEW'
);
```

Inspect the schema and tables:

```text
\dt lab24.*
\d lab24.customers
\d lab24.orders
```

`\dt` and `\d` are **psql meta-commands**. Query system catalogs or `information_schema` when connecting via drivers/applications that do not support them.

### Step 4: Insert Rows

```sql
INSERT INTO lab24.customers (full_name, email)
VALUES
    ('An', 'an@example.test'),
    ('Bình', 'binh@example.test')
RETURNING customer_id, full_name;

INSERT INTO lab24.orders (customer_id, amount, status)
SELECT customer_id, 150000.00, 'PAID'
FROM lab24.customers
WHERE email = 'an@example.test'
RETURNING order_id, customer_id, amount, status;
```

Result: two customer rows and one order row. Identity values generated by PostgreSQL may differ from earlier examples if prior runs occurred in this database; never assume IDs always start at 1 after earlier experiments.

### Step 5: Read Using Schema-Qualified Names

```sql
SELECT customer_id, full_name
FROM lab24.customers
ORDER BY customer_id;

SELECT
    o.order_id,
    c.full_name,
    o.amount,
    o.status
FROM lab24.orders AS o
JOIN lab24.customers AS c
  ON c.customer_id = o.customer_id
ORDER BY o.order_id;
```

Within the same database, both tables have explicit schemas; PostgreSQL performs the `JOIN` normally.

### Step 6: Observe the Effect of `search_path`

```sql
SHOW search_path;

SET search_path TO lab24, public;

SELECT * FROM customers ORDER BY customer_id;

SELECT * FROM lab24.customers ORDER BY customer_id;
```

If `lab24` exists and the role has permissions, both `SELECT` statements return the same rows because `lab24` is searched first. However, only the second statement is **independent of search path**.

Reset the session's search path setting:

```sql
RESET search_path;
```

`RESET` here only restores **the session `search_path` setting** to its default from the appropriate configuration source; it **does not** drop schemas or delete data.

### Step 7: Inspect Structure from System Catalogs

```sql
SELECT
    n.nspname AS schema_name,
    c.relname AS relation_name,
    c.relkind
FROM pg_class AS c
JOIN pg_namespace AS n
  ON n.oid = c.relnamespace
WHERE n.nspname = 'lab24'
  AND c.relkind IN ('r', 'p')
ORDER BY c.relname;
```

Here:

- `pg_namespace` stores schema metadata for the **current database**.
- `pg_class` stores metadata about many relation kinds in the **current database**.
- `relkind = 'r'` is an ordinary table; `'p'` is a partitioned table.
- Indexes, sequences, and views also have entries in `pg_class` with different `relkind` values; this query intentionally filters for only those two table kinds.

Alternatively, you can use the standard view:

```sql
SELECT table_schema, table_name, table_type
FROM information_schema.tables
WHERE table_schema = 'lab24'
ORDER BY table_name;
```

Results from `information_schema` are filtered by privilege semantics and object types; it suits many application metadata discovery tasks, while PostgreSQL system catalogs contain broader internal details.

## 12. Same Name, Different Level: Common Sources of Confusion

### Case A: Two Databases Both Have a `public` Schema

```text
Database A:
  public.users

Database B:
  public.users
```

These are two different tables. When a connection points to A, `SELECT * FROM public.users` reads the table in **A**. It does not look into B.

### Case B: One Database Has Two Schemas Containing Tables with the Same Name

```text
Database: app_db
  sales.events
  audit.events
```

You can query each unambiguously:

```sql
SELECT * FROM sales.events;
SELECT * FROM audit.events;
```

Two tables in the same database but in different namespaces. If you write `SELECT * FROM events`, the target depends on `search_path`.

### Case C: A Role Is Cluster-Wide, Not Schema-Scoped

Role `app_user` can log into multiple databases **if granted CONNECT**, yet tables in each database do not become shared data owned by that role. A role is an identity and permission principal, not a container for rows.

### Case D: Two PostgreSQL Instances on the Same Host

Instance A listens on port 5432, instance B on port 5433. Both can have a database named `app_db` and a schema named `public`, yet they are objects inside **two completely independent database clusters**.

### Case E: One Table Has Many Rows but Only One Column Definition

The table `sales.customers` has one definition `(customer_id, full_name, email)`, and each `INSERT` adds a new row. You do not "create a new schema" or "create a new table" for each customer.

## 13. Distinguishing Logical Levels from Physical Storage

The hierarchy **database → schema → table → row** is a logical view for organizing data and SQL. PostgreSQL also has physical structures:

- **Data directory**: the storage area of the database cluster.
- **Tablespace**: configurable physical storage location.
- **Relation files/segments**: how PostgreSQL stores tables/indexes on disk per internal rules.
- **Pages**: storage page units, typically 8 KiB by default.
- **Tuples**: storage-level record versions.
- **WAL** (*Write-Ahead Log*): log records supporting durability, crash recovery, and certain replication mechanisms.

Do not assume a **schema** is an OS directory of the same name, or that each **row** is a separate file. A table can exceed a single segment file, reside in a specified tablespace, and have multiple indexes creating additional storage structures.

If a learner runs:

```sql
SELECT pg_relation_size('lab24.customers'::regclass);
```

the function returns the storage size of the specified relation per PostgreSQL semantics; that is not the same as counting rows. To count rows in the current snapshot, run:

```sql
SELECT COUNT(*) AS customer_count
FROM lab24.customers;
```

Row count and byte size are two different measurements.

## 14. When to Choose Multiple Databases vs. Multiple Schemas?

There is no single rule that "one application must use one database" in every system. Guiding questions:

| Criterion | Multiple Schemas in One Database | Multiple Databases in One Cluster |
|---|---|---|
| `JOIN` queries across modules | Convenient with `schema.table` | Cannot join directly via three-part names; requires separate integration |
| Multi-table transactions | Can belong to one transaction on one connection | Standard SQL transactions do not span two DBs on one connection |
| Namespace and object privilege isolation | Good for modules of the same system | Stronger separation at the connection/database boundary |
| Schema migration lifecycle | Can deploy per module while sharing one DB | Cleaner separation of DB objects; requires separate connections/migration targets |
| Roles, server config, instance resources | Shared across the cluster | Also shared across the cluster |
| Independent server upgrades needed | Not solved | Not solved if DBs remain on the same instance/cluster |
| Stronger operational infrastructure isolation | Limited | Consider **separate instances/clusters**, not just separate databases |

A practical approach:

- Use **multiple schemas** when table groups are closely related, need direct joins/transactions, yet benefit from module-level naming and privilege separation.
- Use **multiple databases** when applications or datasets have distinct connection boundaries and operational privileges with little need for direct joins.
- Use **separate PostgreSQL instances** when you need distinct resource limits, upgrade schedules, governance, security boundaries, or operational lifecycles.

Creating two databases on the same instance **does not** isolate CPU, RAM, WAL, hardware configuration, or instance failures like two independent servers.

## 15. Common Errors and How to Pinpoint the Right Level

### 15.1. `relation "customers" does not exist`

Possible causes:

- The table has not been created yet.
- Connected to the **wrong database**.
- The table lives in a **different schema**.
- `search_path` does not include the target schema.
- The object name is case-sensitive because it was created with double quotes.

How to diagnose:

```sql
SELECT current_database(), current_schema();
SHOW search_path;

SELECT table_schema, table_name
FROM information_schema.tables
WHERE table_name ILIKE 'customers';
```

If the table is found in `sales`, use `sales.customers` or set an appropriate search path.

### 15.2. `permission denied for schema sales`

The account may already have `CONNECT` on the database and `SELECT` on the table, yet lack `USAGE` on the schema. Check privileges **at every level**, rather than running `GRANT SELECT ON TABLE` while forgetting the schema.

### 15.3. `database "x" does not exist`

The connection requested a database that does not exist in the cluster **served by that server endpoint**, or the name is misspelled. A database with the same name on a different server/port does not exist in the current instance.

### 15.4. Cannot Use `USE db_name`

`USE` is familiar syntax in some other DBMSs, but is not PostgreSQL's command for switching databases. Use `\connect` in `psql` or open a new connection pointing to the target database.

### 15.5. Case Sensitivity in Object Names

PostgreSQL folds **unquoted identifiers** to lowercase. For example:

```sql
CREATE TABLE sales.CustomerProfiles (
    id bigint PRIMARY KEY
);
```

If the schema exists, the actual name created is normally `sales.customerprofiles`.

In contrast:

```sql
CREATE TABLE sales."CustomerProfiles" (
    id bigint PRIMARY KEY
);
```

creates a case-sensitive identifier; subsequent queries must use double quotes and exact casing. To prevent mistakes, use lowercase names separated by underscores, such as `customer_profiles`.

### 15.6. Assuming `PRIMARY KEY` Means Rows Are Ordered

A primary key enforces uniqueness and non-NULL and usually creates a supporting index. PostgreSQL **does not guarantee output order** without `ORDER BY`.

### 15.7. Confusing Logical Rows with Physical Tuples

A row with `id = 42` remains the same business entity after an `UPDATE`, even though PostgreSQL may create a different physical tuple version. Never use `ctid` as a long-term data identifier.

### 15.8. Confusing a PostgreSQL Database Cluster with an HA Cluster

A directory initialized with `initdb` is already called a database cluster even with **one single instance**. High availability requires additional standby, replication, failover, backup, and operational orchestration.

## 16. Self-Practice Exercises

### Exercise 1. Identify Object Levels

Given the logical path:

```text
PostgreSQL server: db.internal:5432
Database: shop_db
Schema: inventory
Table: products
Row: product_id = 501
```

**Question:** What is `inventory`? What is `products`? Which level does `501` identify?

**Solution:** `inventory` is a schema inside the `shop_db` database; `products` is a table; `product_id = 501` is a column value identifying one logical row (assuming `product_id` is a primary or unique key). They are not three separate databases.

### Exercise 2. Can Two Tables Share the Same Name?

Inside `shop_db`, you want both `sales.events` and `audit.events`.

**Solution:** Yes, because schemas are namespaces. The two objects have distinct qualified names. Run:

```sql
SELECT * FROM sales.events;
SELECT * FROM audit.events;
```

As long as the role has privileges on the schemas/tables and the objects exist, both queries succeed.

### Exercise 3. Why Does a Connection Need a Database Name?

An application connects to `db.internal:5432` as user `app_user` but forgets to specify a database.

**Solution:** A PostgreSQL connection must bind to **one database**. A driver/client may default the database name based on the username or config, but you should not rely on that. Specify the database explicitly in the URL/connection parameters and verify with `current_database()`.

### Exercise 4. Can `search_path` Change Which Table Is Queried?

A database contains:

```text
public.settings
tenant_a.settings
```

If `search_path = tenant_a, public`, which table does `SELECT * FROM settings` prefer?

**Solution:** It prefers `tenant_a.settings`, provided the schema and object are valid for the session's privileges and state. Use `public.settings` when you want to target the `public` table regardless of search path.

### Exercise 5. Why Don't Two Databases Join Automatically?

`billing_db.public.invoices` and `crm_db.public.customers` exist in the same cluster. A developer tries to join them using `billing_db.public.invoices JOIN crm_db.public.customers` on a single connection.

**Solution:** Standard PostgreSQL connections operate inside **one database**. Using schema-qualified names does not turn it into a cross-database query. Design application-level integration/connections or use tools like `postgres_fdw`/`dblink` if truly required.

### Exercise 6. What Is the Role of a Primary Key?

The `customers` table has two rows with the same name. The primary key is `customer_id`.

**Solution:** Two people can share the same name as long as they have different `customer_id` values. A primary key identifies rows logically and supports foreign key references; it does not determine the output order of `SELECT` statements.

### Exercise 7. How Many Machines Does a Database Cluster Have?

An administrator runs `initdb` on a single VM, starts one PostgreSQL instance, and creates three databases.

**Solution:** That is already **one PostgreSQL database cluster** in PostgreSQL terminology, even on a single machine with no HA/standby configured. Three databases do not mean three clusters.

### Exercise 8. Why Can't an Account Read a Table?

An admin grants `CONNECT` on the database and `SELECT` on `sales.orders`, but forgets to grant `USAGE` on the `sales` schema.

**Solution:** Privileges are checked at multiple levels. The account needs permission to use the schema namespace as well as appropriate table privileges. Granting `CONNECT` only clears the database boundary; it does not replace `USAGE` on the schema or `SELECT` on the table.

## 17. Key Takeaways

| Question | Short Answer |
|---|---|
| Where does the software accept connections? | **PostgreSQL server instance**, via host/port or socket |
| What is the collection of databases managed by that instance? | **Database cluster** |
| What is the current connection's database name? | `SELECT current_database();` |
| What is the namespace inside a database called? | **Schema** |
| Can two tables with the same name exist in one database? | Yes, if they are in **different schemas** |
| How is an explicit table name commonly written? | `schema.table` |
| What is `search_path` used for? | Resolving objects written **without a schema** |
| What does a table contain? | **Rows** with data conforming to column definitions and constraints |
| How do you stably identify a row? | With a **primary key/unique key**, not `ctid` |
| At which level do roles live? | **Cluster-wide**, while object privileges apply at their respective levels |
| Can you use `USE other_db`? | No; reconnect to the other database |
| Does a database cluster require multiple machines? | No; that is different from an **HA cluster** |

**Foundational PostgreSQL mental model:** one **server instance** serves one **database cluster**; the cluster contains multiple **databases**; each database has multiple **schemas**; each schema contains multiple **tables**; each table contains **rows**. Distinguishing these levels is the first step toward writing accurate SQL, designing data models, managing privileges, and operating PostgreSQL safely.
