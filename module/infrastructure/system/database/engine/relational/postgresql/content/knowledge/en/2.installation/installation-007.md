# Creating Your First Role, Database, and Table in PostgreSQL

## 1. Objectives and Outcomes of This Lab

Once PostgreSQL is installed and running, the first steps for starting an application are typically **creating a login account**, **creating a dedicated database**, and **creating the first table to store data**. In PostgreSQL, these three tasks are related yet operate at distinct management levels:

- A **Role** defines the identity and privileges a person or application can use.
- A **Database** is the data container a PostgreSQL connection attaches to.
- A **Schema** is a namespace inside a database that organizes tables and other objects.
- A **Table** defines columns and constraints; data *rows* are stored inside the table.

By the end of this lesson, you will have a practice environment structured as follows:

```text
PostgreSQL server / database cluster
│
├── Role: pg38_app (LOGIN)
│   └── Logs in, owns database pg38_demo
│
├── Database: postgres
│   └── Used for initial administrative connection
│
└── Database: pg38_demo
    └── Schema: app
        └── Table: app.tasks
            ├── task_id
            ├── title
            ├── status
            ├── priority
            ├── due_date
            └── created_at
```

This lesson also walks through using `psql` to verify connectivity, insert rows, query data, update records, run basic transactions, and test a restricted runtime account.

**Prerequisites:** PostgreSQL is installed, an instance is running, the `psql` tool is available, and you have an administrative account **in a learning environment** with privileges to create roles and databases. Examples use modern PostgreSQL syntax compatible with supported releases such as PostgreSQL 16, 17, or 18; authentication details and default privileges may vary by version and installation method.

> **Safety scope:** the names `pg38_app` and `pg38_demo` are strictly for this lab. Do not arbitrarily create or drop roles or databases in production, never reuse example passwords as real credentials, and never use a superuser role as a routine application connection account.

## 2. Understanding Relationships Between Role, Database, Schema, and Table

PostgreSQL organizes objects across distinct scopes:

| Object | Scope | Example | Meaning |
|---|---|---|---|
| **PostgreSQL instance/cluster** | Running PostgreSQL instance managing a storage area | Server listening on port 5432 | Contains multiple databases and shared roles |
| **Role** | Database cluster level | `pg38_app` | Identity, role memberships, and privileges |
| **Database** | Inside a database cluster | `pg38_demo` | Container holding schemas, tables, and data |
| **Schema** | Inside a single database | `app` | Namespace for naming and organizing objects |
| **Table** | Belongs to one schema | `app.tasks` | Structure storing data rows |
| **Row** | Inside a table | A task with `task_id = 1` | Logical record consisting of column values |

A **role can access multiple databases** if granted appropriate privileges, because roles are not "created inside" an individual database. Conversely, a **table belongs to exactly one schema of one database** at a time. Two databases can both contain a table named `app.tasks`, yet they are completely independent tables.

Important: PostgreSQL does not have a MySQL-style `USE database_name` command. When you want to work in another database, you must **reconnect** or open a new connection.

### 2.1. How Does a Role Differ from a User?

In PostgreSQL, **role is the unified concept**. A role with the `LOGIN` attribute is an account usable for logging in; a role without `LOGIN` is typically used to group privileges or own objects.

These two statements are nearly equivalent when creating a login account:

```sql
CREATE ROLE example_login LOGIN;
CREATE USER another_login;
```

`CREATE USER` essentially creates a role with `LOGIN` enabled by default. By contrast, `CREATE ROLE example_group;` leaves `LOGIN` disabled by default.

Group-only roles can be granted to login roles. This separates **user or application identity** from **shared privilege sets**.

### 2.2. Ownership Does Not Equal Superuser

When a role owns a database or table, it holds management privileges over that object. However, a **database owner does not automatically become a PostgreSQL superuser**. It does not inherently gain rights to administer all roles, read every database, or modify every server setting.

In this lab, `pg38_app` owns the database so you can create schemas and tables easily. In production, a safer practice is **separating the schema owner role (migration owner) from the application runtime role**, since normal runtime operations rarely need DDL privileges.

## 3. Checking PostgreSQL and the `psql` Tool

Before creating any objects, verify PostgreSQL is running and reachable.

### 3.1. Checking the Client Tool

In a terminal or PowerShell:

```sh
psql --version
```

Illustrative output looks like:

```text
psql (PostgreSQL) 17.x
```

Exact numbers depend on your environment. The `psql` client version does not need to match the PostgreSQL server version identically; to check the server version, query it after connecting.

If the terminal reports `psql` is not found, the client package may not be installed or not in `PATH`. That is a local tooling issue and is insufficient to conclude the PostgreSQL server is down.

### 3.2. Connecting with a Lab Administrative Role

Example for a local instance listening on default port 5432:

```sh
psql -h 127.0.0.1 -p 5432 -U postgres -d postgres
```

Parameters:

| Parameter | Meaning |
|---|---|
| `-h 127.0.0.1` | Server address; connects via TCP to localhost |
| `-p 5432` | Listening port |
| `-U postgres` | Login role, typically the admin role created during setup |
| `-d postgres` | Initial database to connect to for administrative tasks |

The `postgres` role is usually created during cluster initialization, though authentication depends on the installation. On Linux, configurations often use **peer authentication** over a Unix socket for the `postgres` OS user; in that case, the TCP command above may prompt for a password or fail. In Docker, cloud, or managed PostgreSQL setups, the admin role may also have a different name and may not be a superuser.

**Do not recklessly alter authentication config just to run an exercise.** If you are not given a superuser/admin account in your lab, use the connection details and privileges prepared by your administrator.

### 3.3. Verifying the Target Server and Database

Inside `psql`:

```sql
SELECT
    version() AS server_version,
    current_database() AS connected_database,
    current_user AS current_role,
    session_user AS login_role,
    inet_server_port() AS tcp_port;
```

You can also use the `psql` command:

```text
\conninfo
```

This is a **`psql` meta-command**, not SQL sent to the PostgreSQL server. It displays the database, user, and endpoint the client is currently using.

To briefly view the server version:

```sql
SHOW server_version;
```

When running commands to create roles and databases, make sure this is a **lab instance**, not production.

## 4. Creating Your First Login Role

### 4.1. Creating a Role with `CREATE ROLE ... LOGIN`

In an admin session connected to the `postgres` database, run:

```sql
CREATE ROLE pg38_app LOGIN;
```

Meaning:

- `CREATE ROLE`: creates a role at the PostgreSQL cluster level.
- `pg38_app`: name of the new role.
- `LOGIN`: allows the role to be used as a login identity.
- Without specifying `SUPERUSER`, a regular role has no superuser privileges.
- The statement above **does not yet set a password** for the role.

To inspect roles in `psql`:

```text
\du
```

Or using SQL:

```sql
SELECT rolname, rolcanlogin, rolsuper, rolcreatedb
FROM pg_roles
WHERE rolname = 'pg38_app';
```

Expected attribute values:

| rolname | rolcanlogin | rolsuper | rolcreatedb |
|---|---|---|---|
| pg38_app | true | false | false |

`rolcreatedb = false` is appropriate for the application role in this lesson. **It can still own a database created and assigned to it by an administrator**, even without permission to create additional databases itself.

### 4.2. Setting a Password Safely with `\password`

Instead of writing a password inside a SQL statement saved to command history, an administrator in **`psql`** can run:

```text
\password pg38_app
```

`psql` prompts to enter and confirm the password. Generate a random, strong lab password and **never reuse a production password**.

The advantage over running:

```sql
-- Syntax illustration only; putting real secrets in scripts/logs is discouraged.
ALTER ROLE pg38_app PASSWORD 'your_plaintext_secret';
```

is that `\password` avoids placing a plaintext password string in command history or SQL files. In automated environments, use an appropriate secret manager/distribution mechanism and securely configured authentication.

**Authentication note:** setting a password on a role does not automatically guarantee login succeeds. The server also enforces rules in `pg_hba.conf` or an equivalent authentication layer. Some connections require passwords, others require certificates/peer, and some configurations may reject your client endpoint.

### 4.3. Do Not Grant Unnecessary Administrative Privileges

Common role attributes:

| Attribute | Purpose | Should Runtime Applications Have It? |
|---|---|---|
| `LOGIN` | Allows logging in | Yes, if the role is a connection account |
| `SUPERUSER` | Bypasses most privilege checks | **No** |
| `CREATEDB` | Allows creating databases | Usually **No** |
| `CREATEROLE` | Manages roles within PostgreSQL rules | **No** |
| `REPLICATION` | Used for certain replication connections/tasks | No for standard apps |
| `BYPASSRLS` | Bypasses Row-Level Security where applicable | No for standard apps |

The pattern:

```sql
CREATE ROLE pg38_app LOGIN;
```

is a much better starting point than granting the application `SUPERUSER` just to "avoid permission denied errors."

## 5. Creating Your First Database and Assigning an Owner

### 5.1. Creating the Database from an Admin Session

The admin role runs:

```sql
CREATE DATABASE pg38_demo OWNER pg38_app;
```

PostgreSQL creates database `pg38_demo` inside the **connected cluster**, owned by `pg38_app`. This command does not start a new server, change ports, or automatically create extra accounts.

Use `psql` to list databases:

```text
\l
```

Or SQL:

```sql
SELECT
    datname AS database_name,
    pg_get_userbyid(datdba) AS owner_name
FROM pg_database
WHERE datname = 'pg38_demo';
```

Expected output shows a database named `pg38_demo` with owner `pg38_app`.

### 5.2. Why Does Ownership Matter?

A database owner holds database-level object management privileges according to PostgreSQL semantics. In this example, `pg38_app` can create new schemas inside the database it owns without needing cluster-wide `CREATEDB` privileges.

However:

- Owning a **database** does not automatically mean owning **every existing table** inside it.
- A database owner does not automatically have read/write access to tables owned by other roles.
- Access permissions also depend on per-object ownership, grants, and role memberships.

Hence, "creating a database" and "granting privileges on tables inside the database" are two distinct concepts.

### 5.3. `CREATE DATABASE` Cannot Run Inside a Transaction Block

Unlike many normal DDL statements, the following is **invalid**:

```sql
BEGIN;
CREATE DATABASE pg38_demo OWNER pg38_app;
COMMIT;
```

PostgreSQL does not allow `CREATE DATABASE` inside a transaction block. Run it as a standalone statement in an admin session. Many migration tools wrap scripts in transactions by default; if a script creates a database, configure its execution mode accordingly.

**Never run `DROP DATABASE` to "try again" on a system with real data.** If `pg38_demo` already exists, verify whether it is genuinely your lab object before renaming your exercise or cleaning up properly.

### 5.4. Do Not Confuse Database with Schema

```sql
CREATE DATABASE pg38_demo OWNER pg38_app;
```

creates a **database** inside the cluster, whereas:

```sql
CREATE SCHEMA app;
```

creates a **schema** inside the **current database**. If your session is connected to `postgres`, running `CREATE SCHEMA app` creates the schema inside `postgres`, **not** automatically inside `pg38_demo`.

Therefore, before creating tables, switch to a **connection targeting the right database**.

## 6. Reconnecting with the Newly Created Role

Exit the admin session if desired:

```text
\q
```

Open a new terminal or reuse the current one:

```sh
psql -h 127.0.0.1 -p 5432 -U pg38_app -d pg38_demo
```

After authenticating successfully, run:

```sql
SELECT
    current_database() AS db_name,
    current_user AS active_role,
    session_user AS login_role;
```

Expected result:

| db_name | active_role | login_role |
|---|---|---|
| pg38_demo | pg38_app | pg38_app |

Now the `CREATE SCHEMA` and `CREATE TABLE` statements below will execute inside **database `pg38_demo`**, not the administrative `postgres` database.

### 6.1. Switching Databases from Inside psql

If you are already inside a `psql` session and want to switch connections, use the meta-command:

```text
\connect pg38_demo pg38_app
```

or:

```text
\c pg38_demo pg38_app
```

Depending on your environment, `psql` will preserve or re-prompt for host/port/password parameters. This is a **client-side reconnect**. PostgreSQL does not support `USE pg38_demo;` as a SQL statement to switch databases inside an existing connection.

### 6.2. If Login Fails

Typical errors:

| Error | Possible Cause | How to Check |
|---|---|---|
| `connection refused` | Server not running, wrong host/port, or not listening on TCP | Check service, host, port, and `listen_addresses` |
| `password authentication failed` | Wrong password, role, or auth method | Verify account, password, and auth config |
| `no pg_hba.conf entry` | Connection matches no auth/source rule | Check `pg_hba.conf` rules and TLS requirements |
| `role "pg38_app" does not exist` | Role not created on connected instance or typo | Check server endpoint and `\du` as admin |
| `database "pg38_demo" does not exist` | Database not created on this instance or typo | Check `\l` as admin |
| `permission denied for database` | Role lacks `CONNECT` privilege | Check ownership and `GRANT CONNECT` |
| `Peer authentication failed` | Peer auth on local socket with mismatched OS/PG role | Use matching connection/auth rules; do not disable security carelessly |

**Never set `pg_hba.conf` to `trust` for all addresses just to bypass password errors.** That configuration permits unauthenticated logins within its scope, which is especially dangerous if the server listens on external networks.

## 7. Creating a Schema to Organize Application Tables

Inside your **`pg38_app@pg38_demo`** connection, run:

```sql
CREATE SCHEMA app AUTHORIZATION pg38_app;
```

Meaning:

- `app` is a namespace inside `pg38_demo`.
- `AUTHORIZATION pg38_app` sets `pg38_app` as the schema owner.
- This schema holds the application's tables and related objects.

Verify:

```text
\dn
```

Or via SQL:

```sql
SELECT schema_name, schema_owner
FROM information_schema.schemata
WHERE schema_name = 'app';
```

`CREATE SCHEMA` requires schema-creation privilege in the database. As owner of `pg38_demo`, this example succeeds unless custom security policies restrict object creation.

### 7.1. Why Not Put All Tables in `public`?

PostgreSQL creates a `public` schema by default in new databases. However, using a dedicated application schema has advantages:

- Clearly separates application tables from shared or scratch objects.
- Reduces naming collision risks.
- Organizes permissions and migrations per module.
- Makes object paths explicit in SQL statements, e.g., `app.tasks`.
- Avoids relying on default `CREATE` privileges on `public`, which vary across PostgreSQL versions and setups.

In modern PostgreSQL, especially starting with PostgreSQL 15, default object-creation privileges on `public` were tightened compared to older installations. Learning to use dedicated schemas and understand schema privileges from the start is good practice.

### 7.2. Schema-Qualified Names `schema.table`

When writing:

```sql
SELECT * FROM app.tasks;
```

`app` is the schema; `tasks` is the table. The database name is not part of this reference because the connection already targets `pg38_demo`.

Writing:

```sql
SELECT * FROM tasks;
```

only works if PostgreSQL can resolve `tasks` using **`search_path`** and role privileges. For clarity, this lesson uses fully qualified names like `app.tasks`.

## 8. Creating Your First Table with `CREATE TABLE`

This is the centerpiece of the lesson. In your `pg38_app@pg38_demo` connection, run:

```sql
CREATE TABLE app.tasks (
    task_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    title text NOT NULL,
    status text NOT NULL DEFAULT 'TODO',
    priority smallint NOT NULL DEFAULT 3,
    due_date date,
    created_at timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT tasks_status_check
      CHECK (status IN ('TODO', 'IN_PROGRESS', 'DONE')),

    CONSTRAINT tasks_priority_check
      CHECK (priority BETWEEN 1 AND 5)
);
```

The new table resides in schema `app` inside database `pg38_demo`. Because `pg38_app` executed the statement, that role owns the table under standard ownership rules.

### 8.1. Analyzing Each Column

| Column | Type | Constraint/Default | Meaning |
|---|---|---|---|
| `task_id` | `bigint` | `GENERATED ALWAYS AS IDENTITY PRIMARY KEY` | Unique identifier auto-generated by PostgreSQL |
| `title` | `text` | `NOT NULL` | Task description, required value |
| `status` | `text` | `NOT NULL DEFAULT 'TODO'`, `CHECK` | Task status |
| `priority` | `smallint` | `DEFAULT 3`, `CHECK 1..5` | Valid priority from 1 to 5 |
| `due_date` | `date` | Nullable | Due date, may be left unspecified |
| `created_at` | `timestamptz` | `DEFAULT now()` | Row creation timestamp |

Frequently asked questions:

**What is `PRIMARY KEY`?** It designates the table's primary key. Primary key values must be non-null and unique, and can be referenced by other tables via `FOREIGN KEY`.

**What is `IDENTITY`?** PostgreSQL manages an automatic ID generator backed by an associated sequence. With `GENERATED ALWAYS`, explicitly supplying an ID value is normally rejected unless using supported override syntax. Note that this does not guarantee gapless consecutive IDs.

**How does `text` differ from `varchar(200)`?** `text` holds variable-length strings without a column-declared length cap. If business rules require a length limit, use `varchar(n)` or `CHECK (char_length(title) <= n)` as appropriate. There is no need to use `varchar(255)` purely out of habit from other DBMSs.

**Does `DEFAULT` replace every `NULL`?** No. The default applies when the column is **omitted** in an `INSERT` or explicitly given `DEFAULT`. If an application explicitly inserts `NULL` into `status NOT NULL`, PostgreSQL raises a constraint violation instead of substituting `'TODO'`.

**Does `timestamptz` store the original timezone name?** No. PostgreSQL stores an absolute point in time and displays it according to the session's timezone. If business logic needs to remember the user's original timezone, store that timezone name or metadata separately.

**What does `CHECK` enforce?** It prevents invalid states at the database layer. A standard `CHECK` constraint does not treat an `UNKNOWN` result caused by `NULL` as a violation, so mandatory columns still need `NOT NULL`. Here, both `status` and `priority` include `NOT NULL`.

### 8.2. Inspecting the Newly Created Table

Inside `psql`:

```text
\dt app.*
\d app.tasks
```

`\d app.tasks` shows column definitions, data types, defaults, primary key, and constraints. This is a `psql`-specific command.

Use SQL if connecting through a driver:

```sql
SELECT
    table_schema,
    table_name,
    table_type
FROM information_schema.tables
WHERE table_schema = 'app'
ORDER BY table_name;

SELECT
    column_name,
    data_type,
    is_nullable,
    column_default
FROM information_schema.columns
WHERE table_schema = 'app'
  AND table_name = 'tasks'
ORDER BY ordinal_position;
```

`information_schema` is a SQL-standard metadata interface; certain PostgreSQL-specific details like identities, constraints, and sequences may require querying PostgreSQL catalogs or dedicated tools.

### 8.3. Distinguishing Table Creation from Inserting Rows

`CREATE TABLE` defines **structure only**. Immediately after creation, the table has zero rows:

```sql
SELECT COUNT(*) AS task_count
FROM app.tasks;
```

Expected result is `0`, unless someone inserted rows while you were practicing.

## 9. Inserting Your First Rows with `INSERT`

Insert two tasks:

```sql
INSERT INTO app.tasks (title, priority, due_date)
VALUES
    ('Learn how to create PostgreSQL roles', 2, DATE '2026-11-20'),
    ('Create first database and table', 1, DATE '2026-11-21')
RETURNING
    task_id, title, status, priority, due_date, created_at;
```

PostgreSQL auto-generates `task_id`; `status` and `created_at` receive their default values. Notice the `INSERT` statement **omits `task_id`** because it is declared `GENERATED ALWAYS AS IDENTITY`.

Illustrative output (omitting exact creation timestamps):

| task_id | title | status | priority | due_date |
|---:|---|---|---:|---|
| 1 | Learn how to create PostgreSQL roles | TODO | 2 | 2026-11-20 |
| 2 | Create first database and table | TODO | 1 | 2026-11-21 |

If you have run this exercise multiple times, `task_id` values may no longer be 1 and 2. Identity sequences do not guarantee continuous numbering across rollbacks, failed inserts, or other operations.

### 9.1. Retrieving Stored Data

```sql
SELECT
    task_id,
    title,
    status,
    priority,
    due_date,
    created_at
FROM app.tasks
ORDER BY task_id;
```

Use `ORDER BY` whenever a deterministic sort order is desired. PostgreSQL makes no guarantee about output ordering for `SELECT` without `ORDER BY`, even when a primary key exists.

### 9.2. Filtering Incomplete Tasks

```sql
SELECT task_id, title, priority
FROM app.tasks
WHERE status = 'TODO'
ORDER BY priority ASC, task_id ASC;
```

This query simply reads matching rows. It does not create roles, schemas, or new tables.

### 9.3. Updating a Task's Status

```sql
UPDATE app.tasks
SET status = 'IN_PROGRESS'
WHERE title = 'Learn how to create PostgreSQL roles'
RETURNING task_id, title, status;
```

In this sample dataset, the title appears only once. In real applications, always update by **primary key** or an appropriate unique key rather than a potentially duplicate title.

Example when the ID is known:

```sql
UPDATE app.tasks
SET status = 'DONE'
WHERE task_id = 1
RETURNING task_id, status;
```

If your generated ID differs from 1, substitute the actual ID returned by `RETURNING`.

### 9.4. Testing Constraint Violations

This statement intentionally supplies an invalid priority:

```sql
INSERT INTO app.tasks (title, priority)
VALUES ('Task with invalid priority', 9);
```

PostgreSQL rejects it because `tasks_priority_check` allows priorities only between 1 and 5. The next statement is also invalid:

```sql
INSERT INTO app.tasks (title, status)
VALUES ('Task with invalid status', 'UNKNOWN');
```

Both examples show database-layer constraints protecting data integrity rather than relying solely on application checks. If you run these **inside an open transaction**, you will need `ROLLBACK` before continuing because PostgreSQL marks the transaction as aborted.

## 10. Your First Transaction with `BEGIN`, `COMMIT`, and `ROLLBACK`

PostgreSQL supports transactions to group multiple SQL statements into an atomic unit of work. In `psql`'s default autocommit mode, each standalone SQL statement commits upon succeeding. To coordinate multiple steps explicitly, open an explicit transaction.

### 10.1. Testing a Change and Rolling Back

```sql
BEGIN;

UPDATE app.tasks
SET priority = 5
WHERE task_id = 1;

SELECT task_id, priority
FROM app.tasks
WHERE task_id = 1;

ROLLBACK;
```

Inside the same transaction, you see the updated value. After `ROLLBACK`, uncommitted changes are undone.

Check again:

```sql
SELECT task_id, priority
FROM app.tasks
WHERE task_id = 1;
```

The value reverts to its pre-test state, assuming no other transaction modified it and ID 1 was the target row.

### 10.2. When to Use `COMMIT`?

```sql
BEGIN;

UPDATE app.tasks
SET status = 'DONE'
WHERE task_id = 1;

COMMIT;
```

After `COMMIT`, the change is persisted under PostgreSQL's transactional guarantees and becomes visible to other sessions according to isolation/snapshot rules.

**Important note:** PostgreSQL supports transactional DDL for many commands like `CREATE TABLE`, yet `CREATE DATABASE` is an exception that cannot run inside a transaction block. Never blindly wrap all administrative statements in a single transaction without checking each command.

### 10.3. When a Statement Inside a Transaction Fails

Example:

```sql
BEGIN;

INSERT INTO app.tasks (title, priority)
VALUES ('Constraint violation', 99);

-- The INSERT statement fails.
-- The transaction remains in an aborted state until ended.

ROLLBACK;
```

After a SQL error inside a PostgreSQL transaction, subsequent statements fail with `current transaction is aborted, commands ignored until end of transaction block`. In practice exercises, run `ROLLBACK`, fix the statement, and start a fresh transaction. In applications, handle errors and rollbacks at the transaction manager/JDBC layer.

## 11. Setting `search_path` to Use Short Table Names

PostgreSQL resolves unqualified table names using **`search_path`**. Check it:

```sql
SHOW search_path;
SELECT current_schema();
```

A common default is:

```text
"$user", public
```

This does not include schema `app`. Therefore:

```sql
SELECT * FROM tasks;
```

may report `relation "tasks" does not exist` even though `app.tasks` exists.

You can set it for the **current session**:

```sql
SET search_path TO app, public;

SELECT task_id, title
FROM tasks
ORDER BY task_id;

SELECT task_id, title
FROM app.tasks
ORDER BY task_id;
```

Both statements access the same table when `search_path` and privileges align.

To reset the session setting:

```sql
RESET search_path;
```

In critical SQL or migrations, explicitly writing `app.tasks` is clearer and safer because it does not depend on connection `search_path` settings.

**Security note:** never place a schema where untrusted users can create objects ahead of trusted schemas in a critical application's `search_path`. Unqualified function/operator/object resolution can cause bugs or security vulnerabilities if namespaces are uncontrolled.

## 12. Granting Privileges to a Runtime Application Account: Separating Owner and DML

Earlier, `pg38_app` served as both the login user and the owner of the database/schema/table. While convenient for labs, production applications rarely need permission to run `ALTER TABLE` or `DROP TABLE` arbitrarily.

A better model:

```text
Migration/owner role:
    CREATE, ALTER, DROP objects per deployment workflow

Runtime application role:
    CONNECT to database
    USAGE on schema
    SELECT, INSERT, UPDATE, DELETE on required tables only

Reporting role:
    CONNECT, USAGE, SELECT within reporting scope
```

You can practice creating a restricted runtime role **against the table you already created**.

### 12.1. Creating the Runtime Role as the Lab Admin

Open a separate admin `psql` session connected to the `postgres` database of the **same instance**:

```sql
CREATE ROLE pg38_runtime LOGIN;
```

Inside admin `psql`:

```text
\password pg38_runtime
```

Next, connect to `pg38_demo` using a role permitted to grant privileges (such as the admin or object owner):

```text
\connect pg38_demo
```

Grant privileges:

```sql
GRANT CONNECT ON DATABASE pg38_demo TO pg38_runtime;
GRANT USAGE ON SCHEMA app TO pg38_runtime;

GRANT SELECT, INSERT, UPDATE, DELETE
ON TABLE app.tasks
TO pg38_runtime;
```

Meaning:

- `CONNECT` allows connecting to the database.
- `USAGE` allows resolving permitted objects inside the schema.
- Table DML privileges allow corresponding data operations.
- **No `CREATE` on schema or database** is granted in these commands.
- This role **is not the owner** of the table.

On new databases, `CONNECT` may already be granted to `PUBLIC` by default, so `GRANT CONNECT` may not visibly alter behavior right away. Even so, it explicitly models required privileges; in hardened environments that revoke default privileges, manage both `PUBLIC` and specific accounts intentionally.

**Regarding sequences:** for `GENERATED ... AS IDENTITY` columns, PostgreSQL manages identity handling internally with the table. For legacy `serial` columns using `nextval()` on standalone sequences, a runtime account may also need `USAGE` on those sequences when inserting rows. Avoid blindly granting `USAGE ON ALL SEQUENCES` if only specific sequences are needed.

### 12.2. Verifying Using the Runtime Account Itself

Open a new terminal:

```sh
psql -h 127.0.0.1 -p 5432 -U pg38_runtime -d pg38_demo
```

Test querying:

```sql
SELECT current_user, current_database();

SELECT task_id, title, status
FROM app.tasks
ORDER BY task_id;
```

Read queries succeed if the grants above were applied and no additional restrictive policies interfere.

Test an **unauthorized** operation:

```sql
CREATE TABLE app.unauthorized_test (
    id integer PRIMARY KEY
);
```

PostgreSQL should raise a permission error denying object creation in schema `app`. If the statement succeeds instead, inspect `current_user`, ownership, role memberships, and privileges granted to `PUBLIC` or inherited via another role; never assume least privilege without verifying.

### 12.3. Inspecting Privileges via SQL

Under a role permitted to read privilege info:

```sql
SELECT
    has_database_privilege('pg38_runtime', 'pg38_demo', 'CONNECT')
        AS can_connect,
    has_schema_privilege('pg38_runtime', 'app', 'USAGE')
        AS can_use_app_schema,
    has_schema_privilege('pg38_runtime', 'app', 'CREATE')
        AS can_create_in_app,
    has_table_privilege('pg38_runtime', 'app.tasks', 'SELECT')
        AS can_select_tasks;
```

Target results:

- `can_connect = true`
- `can_use_app_schema = true`
- `can_create_in_app = false`
- `can_select_tasks = true`

If the role inherited extra rights through another role or policy, results may differ. The goal is checking **effective privileges**, not just reading a `GRANT` line in a script.

In `psql`, you can inspect table privileges with:

```text
\dp app.tasks
```

Or from an admin session, run `\du pg38_runtime` to inspect role attributes, without confusing role attributes for per-table permissions.

### 12.4. Why Not Use the Owner Account in Real Applications?

If the application runtime connects as the table owner, an application bug or SQL injection vulnerability can execute unintended DDL if the role holds those rights. A DML-only account limits the blast radius.

Still, **DML can also destroy data**—for instance, `DELETE FROM app.tasks;` when the runtime account holds `DELETE`. If an application never needs to delete rows, omit `DELETE`, use separate purpose-built accounts, or enforce operations via controlled APIs/stored routines.

## 13. Creating a Second Table and Understanding Default Privileges

Suppose an application module adds `app.task_notes`:

```sql
-- Run as the owner/migration role permitted to create tables in schema app.
CREATE TABLE app.task_notes (
    note_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    task_id bigint NOT NULL REFERENCES app.tasks(task_id),
    note_text text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
```

This new table has a foreign key referencing `app.tasks`. Even though `pg38_runtime` already holds privileges on `app.tasks`, **it does not automatically get SELECT/INSERT on the new table**.

Grant privileges on the new table if required by business logic:

```sql
GRANT SELECT, INSERT
ON TABLE app.task_notes
TO pg38_runtime;
```

### 13.1. Default Privileges for Future Tables

To configure privileges for future tables automatically, the **role that actually creates the tables** can set default privileges for objects it creates in the schema:

```sql
-- Run as the table-creating role, e.g., pg38_app.
ALTER DEFAULT PRIVILEGES IN SCHEMA app
GRANT SELECT, INSERT, UPDATE, DELETE
ON TABLES TO pg38_runtime;
```

Meaning:

- Applies to **future tables** created by that specific role under default privilege rules.
- Does not retroactively alter privileges on already existing tables.
- Does not automatically apply to tables created by a different owner unless configured for that creating role.
- Requires careful selection of privileges; not every service needs `DELETE` or `UPDATE` on every new table.

In multi-service systems, design ownership, migration roles, and default privileges consistently. Schema-level defaults do not replace reviewing table-level access controls.

## 14. Querying Tables from a Java/JDBC Application

PostgreSQL is commonly used with Java via the **PostgreSQL JDBC Driver (pgJDBC)**. The JDBC URL specifies address, port, and database:

```text
jdbc:postgresql://127.0.0.1:5432/pg38_demo
```

In application code, use an appropriate runtime role rather than a superuser or migration owner:

```java
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;

public class FirstPostgresQuery {
    public static void main(String[] args) throws Exception {
        String url = "jdbc:postgresql://127.0.0.1:5432/pg38_demo";
        String user = System.getenv("PG_APP_USER");
        String password = System.getenv("PG_APP_PASSWORD");

        if (user == null || password == null) {
            throw new IllegalStateException("Missing DB credentials");
        }

        String sql = """
            SELECT task_id, title, status
            FROM app.tasks
            WHERE status = ?
            ORDER BY task_id
            """;

        try (Connection connection =
                    DriverManager.getConnection(url, user, password);
             PreparedStatement statement = connection.prepareStatement(sql)) {

            statement.setString(1, "TODO");

            try (ResultSet rows = statement.executeQuery()) {
                while (rows.next()) {
                    long taskId = rows.getLong("task_id");
                    String title = rows.getString("title");
                    String status = rows.getString("status");

                    System.out.printf("%d: %s (%s)%n", taskId, title, status);
                }
            }
        }
    }
}
```

This example uses **Java 15+ text blocks**; the project requires the pgJDBC dependency and actual connection configuration. The two environment variables:

```text
PG_APP_USER=pg38_runtime
PG_APP_PASSWORD=<password retrieved from secret store>
```

illustrate configuration inputs, not a file with sample passwords to commit to a repository.

In production:

- Retrieve secrets from a proper secret management system; environment variables are only one option and require strict access control.
- Enable and verify TLS according to your network architecture.
- Use a properly sized connection pool with appropriate connection limits and timeouts.
- Always use `PreparedStatement` with parameters; never concatenate user input directly into SQL strings.
- Separate migrations from application runtime; never recreate databases/schemas on every service startup.
- Handle connection loss, deadlocks, timeouts, and transactions cleanly in the application layer.

This Java snippet illustrates **reading an existing table**; it does not run `CREATE TABLE` at runtime. Creating and altering tables belongs in a dedicated migration workflow for serious applications.

## 15. Common Errors When Creating Roles, Databases, and Tables

### 15.1. `ERROR: permission denied to create role`

The connected role lacks privilege to create roles. Check:

```sql
SELECT current_user;

SELECT rolname, rolcreaterole, rolsuper
FROM pg_roles
WHERE rolname = current_user;
```

Use an administrative account in the lab or ask an administrator to provision the required role. Never grant `CREATEROLE` to an application runtime account just to complete an exercise.

### 15.2. `ERROR: permission denied to create database`

The role executing `CREATE DATABASE` lacks `CREATEDB` or sufficient rights. If an application role lacks this privilege, that is usually the **intended** secure setup—not a bug to "fix" with `SUPERUSER`. Have an administrator create the database and assign ownership as required.

### 15.3. `ERROR: CREATE DATABASE cannot run inside a transaction block`

You are running database creation inside `BEGIN ... COMMIT` or a tool that automatically opens a transaction. Execute `CREATE DATABASE` as a standalone statement per PostgreSQL rules.

### 15.4. `ERROR: database "pg38_demo" does not exist`

The database may have been created on another instance, misspelled, targeted via the wrong host/port, or not created yet. Connect with an admin account to the **same endpoint** and check:

```sql
SELECT datname
FROM pg_database
WHERE datname = 'pg38_demo';
```

### 15.5. `ERROR: role "pg38_app" does not exist`

The role has not been created in the connected cluster or the name is misspelled. Check:

```sql
SELECT rolname
FROM pg_roles
WHERE rolname = 'pg38_app';
```

A role created in cluster A does not automatically exist in cluster B, even if both clusters host identically named databases.

### 15.6. `ERROR: permission denied for schema app`

The account can connect to the database but lacks `USAGE` on the schema, or lacks `CREATE` when creating a table in the schema. Distinguish:

- `CONNECT`: enter the database.
- `USAGE`: access permitted objects inside the schema.
- `CREATE` on schema: create objects inside the schema.
- `SELECT/INSERT/UPDATE/DELETE`: manipulate data in tables.

One privilege does not automatically imply the others.

### 15.7. `ERROR: relation "tasks" does not exist`

The table may exist as `app.tasks`, while `search_path` omits `app`, or you are connected to a different database. Check:

```sql
SELECT current_database();
SHOW search_path;

SELECT to_regclass('app.tasks') AS fully_qualified,
       to_regclass('tasks') AS resolved_by_search_path;
```

If `fully_qualified` is non-null while `resolved_by_search_path` is `NULL`, qualify the table as `app.tasks` or adjust `search_path` appropriately.

### 15.8. `ERROR: relation "app.tasks" already exists`

You may have already run `CREATE TABLE` earlier. **Do not rush to run `DROP TABLE` to retry**: the table might contain data. Inspect `\d app.tasks`, check its definition, and decide whether to reuse the existing table or start a clean lab.

`CREATE TABLE IF NOT EXISTS` suppresses the error when the table exists, yet it does not verify that the existing table structure **matches** your new definition; thus it does not replace controlled migrations.

### 15.9. `INSERT` Fails to Generate an Identity

First inspect the column definition:

```text
\d app.tasks
```

If the column is not properly declared as an identity or your code passes an explicit value to `GENERATED ALWAYS AS IDENTITY`, the insert fails. For this pattern, omit `task_id` from the `INSERT` column list and use `RETURNING task_id` to retrieve the generated ID.

### 15.10. Command Fails with "current transaction is aborted"

A previous SQL statement inside `BEGIN ... COMMIT` failed. Close the failed transaction with `ROLLBACK`, then retry valid statements in a new transaction. This is not a host/port or schema error.

### 15.11. Mixing Up Letter Case in Object Names

PostgreSQL folds **unquoted identifiers** to lowercase. For example:

```sql
CREATE TABLE app.FirstTasks (
    id bigint PRIMARY KEY
);
```

creates a table logically named `app.firsttasks`. If you intentionally quote it:

```sql
CREATE TABLE app."FirstTasks" (
    id bigint PRIMARY KEY
);
```

you must always quote `"FirstTasks"` in every subsequent query. To minimize errors, stick to `lowercase_with_underscores` naming.

### 15.12. Wrong Role Inside a Connection Pool

An application switches config from `pg38_app` to `pg38_runtime`, yet old pooled connections remain open under the previous role. Check `current_user` on the application's actual connections and follow a proper pool rotation/recycle procedure when changing accounts or privileges.

## 16. Inspecting Structure via System Catalogs

PostgreSQL stores metadata in system catalogs. After creating roles, databases, schemas, and tables, use these queries to see how they relate.

### 16.1. Listing Roles in the Cluster

```sql
SELECT rolname, rolcanlogin, rolcreatedb, rolsuper
FROM pg_roles
WHERE rolname IN ('pg38_app', 'pg38_runtime')
ORDER BY rolname;
```

`pg_roles` provides cluster role metadata; do not look for roles inside a specific schema.

### 16.2. Listing Databases in the Cluster

```sql
SELECT datname, pg_get_userbyid(datdba) AS owner_name
FROM pg_database
WHERE datname = 'pg38_demo';
```

`pg_database` manages cluster-level database metadata.

### 16.3. Schemas in the Database

Connect to `pg38_demo` and run:

```sql
SELECT nspname AS schema_name,
       pg_get_userbyid(nspowner) AS owner_name
FROM pg_namespace
WHERE nspname = 'app';
```

`pg_namespace` describes schemas inside the **current database**.

### 16.4. Tables in a Schema

```sql
SELECT
    n.nspname AS schema_name,
    c.relname AS table_name,
    c.relkind
FROM pg_class AS c
JOIN pg_namespace AS n
  ON n.oid = c.relnamespace
WHERE n.nspname = 'app'
  AND c.relkind IN ('r', 'p')
ORDER BY c.relname;
```

Here `relkind = 'r'` represents an ordinary table and `'p'` represents a partitioned table. `pg_class` also stores metadata for other relation types such as indexes, views, and sequences, which is why the query filters explicitly.

### 16.5. Rows in a Table

```sql
SELECT task_id, title, status, priority
FROM app.tasks
ORDER BY task_id;
```

This is **business data**, not metadata. A newly created table can be empty even though the catalogs record its existence.

## 17. How Should Roles Be Separated in Team Environments?

Once you understand the simple lab workflow, consider a model closer to production systems:

```text
PostgreSQL cluster
├── Role: app_owner       (NOLOGIN)
│    └── Owns schemas/tables per design
├── Role: app_migrator    (LOGIN, appropriate migration rights)
│    └── Runs Flyway/Liquibase or DDL scripts
├── Role: app_runtime     (LOGIN, required DML)
│    └── Used by the Java application to serve APIs
└── Role: report_reader   (LOGIN, SELECT)
     └── Reporting tools
```

For example:

```sql
-- Illustrating role attributes, run by admin in a dedicated lab.
CREATE ROLE app_owner NOLOGIN;
CREATE ROLE app_runtime LOGIN;
```

**Do not run colliding commands on an existing environment without verifying ownership.** For a migration role to manage objects owned by `app_owner`, configure role membership/`SET ROLE` or version-appropriate grants. Never assume any role with `CREATE` can `ALTER/DROP` objects owned by another role.

Benefits of role separation:

- Runtime cannot alter table structures.
- Migrations carry a distinct audit trail and deployment window.
- Reporting queries have no write access.
- Credentials can be rotated independently per component.
- If a secret leaks, blast radius is far smaller than a superuser compromise.

A single database with multiple schemas can also isolate modules using distinct roles. When services require strong isolation, consider separating databases/instances and network policies, not just `GRANT` statements.

## 18. Cleaning Up the Lab Without Deleting Valuable Data

This lesson created these primary objects:

```text
Role:      pg38_app
Role:      pg38_runtime            (if completing the advanced privilege section)
Database:  pg38_demo
Schema:    app
Tables:    app.tasks
           app.task_notes          (if completing the extension section)
```

If you want to **keep the data for upcoming lessons**, do not delete anything. That is usually the most convenient choice.

If you truly want to clean up the entire lab:

1. Confirm the database and roles are **test objects you created yourself**.
2. Ensure no application or session still uses that database.
3. Take a backup first if the data has value.
4. Connect to a **different** database (e.g., `postgres`), because you cannot drop the database your current session is using.
5. Drop objects in dependency order; never use wildcards or run cleanup commands in production.

Example **for reference only, never run on real databases**:

```sql
-- Run after switching to database postgres as lab admin,
-- and confirming no active sessions remain on pg38_demo.
DROP DATABASE pg38_demo;

-- Execute only after confirming no remaining objects/dependencies exist.
DROP ROLE pg38_runtime;
DROP ROLE pg38_app;
```

If tables or grants still reference a role, `DROP ROLE` is rejected due to lingering privileges or cross-database dependencies. PostgreSQL enforces this to protect objects; avoid running sweeping drop-privilege commands without understanding their scope.

**Never put `DROP DATABASE` at the top of a learning script "to reset cleanly."** Using a fresh lab database/schema or a controlled migration tool is safer whenever data might matter.

## 19. Self-Practice Exercises with Solutions

### Exercise 1. Which Role Can Log In?

Given:

```sql
CREATE ROLE role_a;
CREATE ROLE role_b LOGIN;
```

**Question:** which role can be used as a login account?

**Solution:** `role_b` has `LOGIN`. `role_a` defaults to a non-login role; it can serve as a privilege group or object owner as needed. Beyond `LOGIN`, actual login also depends on authentication rules and passwords/certificates.

### Exercise 2. Who Owns the Database?

An administrator runs:

```sql
CREATE DATABASE demo_training OWNER developer_role;
```

**Question:** which role owns the database? Does the command automatically create `developer_role`?

**Solution:** `developer_role` is assigned as owner; that role **must already exist**, and `CREATE DATABASE` does not create roles automatically. The executing user must also hold appropriate privileges to create databases and assign that owner.

### Exercise 3. Which Database Holds the Table?

You connect to database `postgres` and run:

```sql
CREATE SCHEMA training;
CREATE TABLE training.tasks (
    id bigint PRIMARY KEY
);
```

**Question:** is the table in `postgres` or in another new database?

**Solution:** the table is in schema `training` inside the **connected `postgres` database**. Creating a schema does not create a new database; reconnect to the target database whenever creating objects there.

### Exercise 4. Why Does Omitting the Schema Cause an Error?

Table `app.tasks` exists, yet:

```sql
SELECT * FROM tasks;
```

reports `relation does not exist`.

**Solution:** `search_path` may not contain `app`. Run `SELECT * FROM app.tasks;` or inspect and adjust `search_path` if appropriate. Also confirm you are in the right database and hold `USAGE`/`SELECT` privileges.

### Exercise 5. Why Is `CONNECT` Not Enough to Read a Table?

A role is granted:

```sql
GRANT CONNECT ON DATABASE pg38_demo TO report_user;
```

yet cannot read `app.tasks`.

**Solution:** `CONNECT` only permits entering the database. The role also needs `USAGE` on the schema and `SELECT` on the table, per effective privileges and ownership. Permission layers do not substitute for one another.

### Exercise 6. Default Values and `NULL`

Table `app.tasks` has `status text NOT NULL DEFAULT 'TODO'`. How do these two statements differ?

```sql
INSERT INTO app.tasks(title)
VALUES ('Omitted status');

INSERT INTO app.tasks(title, status)
VALUES ('Passed NULL', NULL);
```

**Solution:** the first uses the default `'TODO'`; the second violates `NOT NULL` instead of automatically substituting the default.

### Exercise 7. Creating a Read-Only Runtime Role

**Requirement:** role `report_reader` can log in and only read table `app.tasks`.

**Hint:**

```sql
-- Admin creates the role and sets a password securely via psql \password.
CREATE ROLE report_reader LOGIN;

-- After connecting to pg38_demo with privilege-granting rights:
GRANT CONNECT ON DATABASE pg38_demo TO report_reader;
GRANT USAGE ON SCHEMA app TO report_reader;
GRANT SELECT ON TABLE app.tasks TO report_reader;
```

Verify the role using a new connection. Never grant `SUPERUSER`, `CREATEDB`, or `CREATE` just to read a table.

### Exercise 8. Distinguishing Database and Schema

You need two modules, `sales` and `audit`, and frequently join data between them.

**Hint:** using two schemas inside the same database is convenient, e.g., `sales.orders` and `audit.events`. Placing them in two separate databases prevents standard single-query three-part cross-database joins in PostgreSQL, requiring separate integration mechanisms.

### Exercise 9. Why Doesn't a Primary Key Guarantee SELECT Order?

Table `app.tasks` has primary key `task_id`. You run:

```sql
SELECT task_id, title FROM app.tasks;
```

**Solution:** PostgreSQL makes no guarantee of row order without `ORDER BY`. Always add `ORDER BY task_id` when ascending ID order is desired.

### Exercise 10. Transaction Aborted by a Constraint Error

You run:

```sql
BEGIN;
INSERT INTO app.tasks(title, priority)
VALUES ('Invalid data', 99);
```

The `INSERT` fails. What should you do next?

**Solution:** run `ROLLBACK;` to end the aborted transaction, then start a new transaction if you want to retry with valid data. Do not run `COMMIT` expecting PostgreSQL to skip only the failed statement while keeping subsequent ones.

## 20. Operational Checklist and Key Takeaways

| Task | Command/Tool | What to Confirm |
|---|---|---|
| Check PostgreSQL client | `psql --version` | Working CLI binary available |
| Log in to lab server | `psql -h ... -p ... -U ... -d ...` | Correct host, port, role, database |
| Check connection | `\conninfo` / `current_database()` | Not operating on the wrong database |
| Create login role | `CREATE ROLE name LOGIN` | No unnecessary superuser privileges |
| Set password | `\password name` in psql | No secrets in history/code |
| Create database | `CREATE DATABASE name OWNER role` | Correct owner, executed outside transaction |
| Connect to new database | `psql -d name` / `\connect` | Session targets the intended database |
| Create schema | `CREATE SCHEMA app ...` | Appropriate namespace and owner |
| Create table | `CREATE TABLE app.tasks (...)` | Correct columns, types, and constraints |
| Inspect structure | `\dt app.*`, `\d app.tasks` | Table exists in the intended schema |
| Insert rows | `INSERT ... RETURNING` | Valid IDs and default values |
| Read and update rows | `SELECT`, `UPDATE ... RETURNING` | `WHERE` clause present, expected row count |
| Test transactions | `BEGIN` / `COMMIT` / `ROLLBACK` | Session not left in aborted state |
| Separate runtime account | `GRANT CONNECT/USAGE/DML` | App has neither DDL nor superuser |
| Check effective privileges | `SHOW GRANTS` is not PostgreSQL syntax; use `\dp` and `has_*_privilege` functions | Avoid mixing in MySQL syntax |

### Three Core Steps Summary

**Step 1 — Create the login role using lab admin:**

```sql
CREATE ROLE pg38_app LOGIN;
-- In psql, run: \password pg38_app
```

**Step 2 — Create the database and assign the owner:**

```sql
CREATE DATABASE pg38_demo OWNER pg38_app;
```

**Step 3 — Connect as `pg38_app` to `pg38_demo`, then create the schema and table:**

```sql
CREATE SCHEMA app AUTHORIZATION pg38_app;

CREATE TABLE app.tasks (
    task_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    title text NOT NULL,
    status text NOT NULL DEFAULT 'TODO',
    created_at timestamptz NOT NULL DEFAULT now()
);
```

Step 3 in this summary shows a **minimal version** of the main practice table without `priority`, `due_date`, and extra constraints. If you already created the full table in Section 8, **do not re-run this minimal `CREATE TABLE`** because the table already exists; treat it simply as a syntax reminder for a fresh lab.

**Core principle:** Roles answer "**who may connect and what can they do?**"; databases answer "**which data container am I working in?**"; schemas answer "**which namespace does an object belong to?**"; tables answer "**how are data rows structured?**". By creating each level cleanly, verifying the right connection, and testing privileges from the application account itself, you establish a solid foundation for subsequent PostgreSQL queries and features.
