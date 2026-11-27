# System Functions, Session Information, and Privilege Checks in PostgreSQL

When writing applications with PostgreSQL, the problem does not always lie in the `SELECT` statement or table structure. Sometimes a query works in `psql` but fails over JDBC; a service connects to the right database yet cannot find a table; a user has `SELECT` privilege yet sees zero rows; or a connection reused from a pool still carries configuration from a previous request. Those situations involve **session identity**, **execution context**, **effective configuration**, and **access-control mechanisms**.

PostgreSQL provides many system functions and special expressions to answer these questions:

- "Which database am I connected to, and under which account?" — `current_database()`, `session_user`.
- "Under which role is the current command being checked for privileges?" — `current_user`, `current_role`.
- "Where will an unqualified table name be searched?" — `current_schema()`, `current_schemas()`, `current_setting('search_path')`.
- "Which backend is this; did the connection reach the server over TCP or a Unix socket?" — `pg_backend_pid()`, `inet_client_addr()`, `inet_server_addr()`.
- "What are the actual settings for `statement_timeout`, `TimeZone`, and `application_name`?" — `SHOW`, `current_setting()`, `pg_settings`.
- "Can this role read a table, column, schema, or sequence, or invoke a function?" — the `has_*_privilege()` functions and `pg_has_role()`.
- "Privileges are granted, yet rows are still filtered out?" — check **row-level security (RLS)**, column-level privileges, the effective role, and the query context as well.

This lesson progresses from concepts to practical queries, serving SQL learners, Java/JDBC developers, authorization designers, and operations troubleshooting engineers.

> **Scope:** The examples use modern PostgreSQL with a lab schema named `lesson_sys`. Statements that create roles, grant or revoke privileges, change `search_path`, and set roles may require specific privileges. Only perform privilege-changing operations in an authorized lab environment; in real systems, follow security procedures and the principle of least privilege. Results of some functions depend on role, connection method, and PostgreSQL version, so you cannot assume everyone will see identical values.

## 1. System Functions and Special Expressions

Several components are commonly grouped together as "system functions," yet **their SQL syntax is not completely uniform**:

| Category | Examples | Role |
|---|---|---|
| **Identity information** | `current_user`, `session_user`, `current_role` | Identify the effective role and session role. |
| **Database/schema information** | `current_database()`, `current_schema()`, `current_schemas(true)` | Identify the object lookup context. |
| **Backend/connection information** | `pg_backend_pid()`, `inet_client_addr()` | Identify the backend process and certain network attributes. |
| **Runtime configuration** | `current_setting()`, `set_config()`, `pg_settings` | Read/set configuration parameters. |
| **Session/transaction time** | `now()`, `statement_timestamp()`, `clock_timestamp()` | Distinguish transaction, statement, and wall-clock timestamps. |
| **Privilege checks** | `has_table_privilege()`, `has_schema_privilege()`, `pg_has_role()` | Check specific object-level and role-level privileges. |
| **System information** | `version()`, `pg_is_in_recovery()`, `pg_postmaster_start_time()` | Identify server version and server state. |

Minimal example:

```sql
SELECT
    current_user,
    session_user,
    current_role,
    current_database(),
    current_schema(),
    pg_backend_pid();
```

Note: `current_user`, `session_user`, and `current_role` are **special SQL expressions**, normally written **without parentheses**. Meanwhile, `current_database()` and `pg_backend_pid()` are function calls with parentheses.

Do not assume that everything looking like a `"current"` keyword shares the same syntax style.

## 2. Preparing the Lab Database

The examples below use a simple staff table, a tasks table, and a function for checking function-execution privileges.

```sql
CREATE SCHEMA IF NOT EXISTS lesson_sys;

CREATE TABLE lesson_sys.staff (
    staff_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    full_name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    salary NUMERIC(12, 2) NOT NULL CHECK (salary >= 0),
    department TEXT NOT NULL
);

CREATE TABLE lesson_sys.tasks (
    task_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    owner_id BIGINT NOT NULL REFERENCES lesson_sys.staff(staff_id),
    title TEXT NOT NULL,
    status TEXT NOT NULL
        CHECK (status IN ('TODO', 'DOING', 'DONE')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

INSERT INTO lesson_sys.staff(full_name, email, salary, department)
VALUES
    ('An', 'an@example.invalid', 20000000, 'Engineering'),
    ('Bình', 'binh@example.invalid', 17000000, 'Engineering'),
    ('Chi', 'chi@example.invalid', 15000000, 'Support');

INSERT INTO lesson_sys.tasks(owner_id, title, status)
VALUES
    (1, 'Design API', 'DOING'),
    (1, 'Test privileges', 'TODO'),
    (2, 'Write documentation', 'DONE');
```

This is sample data for a lab environment. The `staff_id` values are assumed to be 1, 2, and 3 when the table is completely fresh and the identity sequence starts at its default; if the database already contains data, obtain the actual IDs with `INSERT ... RETURNING` instead of relying on those literal numbers.

Create a function with a clear name:

```sql
CREATE FUNCTION lesson_sys.normalize_label(p_label TEXT)
RETURNS TEXT
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT lower(btrim(p_label))
$$;
```

Test it:

```sql
SELECT lesson_sys.normalize_label('  PostgreSQL  ') AS normalized;
-- postgresql
```

Once created, `lesson_sys.staff`, `lesson_sys.tasks`, and the function `lesson_sys.normalize_label(text)` serve as targets for privilege-check examples. **Do not grant privileges on these demo objects to production roles just to run the lesson**.

## 3. Distinguishing Between a Session and a Transaction

An application typically has the following structure:

```text
JDBC application
      │
      │ open or borrow a Connection
      ▼
PostgreSQL session / backend
      ├── Session identity (session_user)
      ├── Effective role (current_user)
      ├── Configuration (TimeZone, search_path, application_name, ...)
      │
      ├── Transaction A: BEGIN ... COMMIT
      ├── Transaction B: BEGIN ... ROLLBACK
      └── Transaction C: BEGIN ... COMMIT
```

A **Session** is the context of a backend connection. One session can execute many transactions sequentially. A **Transaction** is the atomic unit for SQL operations that share a commit/rollback boundary.

Within a session:

- The effective role can be changed by permitted operations such as `SET ROLE`.
- Some configuration parameters are session-scoped and persist across multiple transactions.
- `SET LOCAL` sets configuration only within the current transaction.
- `pg_backend_pid()` identifies the current backend for the lifetime of that connection.

When using a connection pool, a **Connection object returned to the pool** can be **borrowed again by another request**. Without explicit state management, subsequent requests may inherit unwanted session-level settings.

## 4. current_user, session_user, and current_role

This is the first group of expressions to remember:

```sql
SELECT
    session_user AS session_login_role,
    current_user AS effective_role,
    current_role AS current_role_name;
```

| Expression | Meaning | When can it change? |
|---|---|---|
| `session_user` | The **session authorization identifier** role, usually the role authenticated when the session was established. | Can change via `SET SESSION AUTHORIZATION` with sufficient privileges; does not change automatically just from `SET ROLE`. |
| `current_user` | The **effective role** used for most privilege checks in the current SQL execution. | Changes with `SET ROLE`, `RESET ROLE`, and temporarily inside a `SECURITY DEFINER` function. |
| `current_role` | In PostgreSQL, essentially equivalent to `current_user` for the effective role context. | Reflects the corresponding effective role. |

In a normal connection session, you typically observe:

```text
session_user = app_user
current_user = app_user
current_role = app_user
```

However, **you must not assume these three values are always identical**.

### Why does this matter?

When a `SELECT` fails with "permission denied," you need to know **which role is actually being used for the privilege check**. Looking only at the login account name may be misleading if the application executed `SET ROLE` or is running inside a `SECURITY DEFINER` function.

### current_user is not automatically the end user of an API

A Java backend might use a shared database account `app_service` to serve thousands of HTTP-authenticated users. In that case:

```text
HTTP users: user-101, user-102, ...
               │
               ▼
         Backend application
               │ DB connection as app_service
               ▼
current_user = app_service
```

`current_user` identifies the **PostgreSQL role**, and does not automatically identify the business user logged into the web/mobile app.

## 5. SET ROLE and the Scope of Identity Changes

`SET ROLE` switches the effective role when the session is permitted to assume that role.

Example — **run this only if the role already exists and the session is permitted to switch to it**:

```sql
SELECT session_user, current_user;

SET ROLE lab_reader;

SELECT session_user, current_user, current_role;

RESET ROLE;

SELECT session_user, current_user;
```

When `SET ROLE lab_reader` succeeds:

- `session_user` usually **remains unchanged**.
- `current_user` becomes `lab_reader`.
- Subsequent SQL operations undergo privilege checks under the effective role and relevant membership/inheritance rules.

If the role does not exist or the session is not permitted to run `SET ROLE`, the command fails. `SET ROLE` is not a way to grant yourself privileges.

### Difference from SET SESSION AUTHORIZATION

`SET SESSION AUTHORIZATION` has the semantics of changing the **session authorization identifier**, which differs from `SET ROLE`. The ability to switch to another role is restricted by the caller's privileges; this command should not be used in normal application flows just to "test privileges."

A quick rule of thumb:

```text
session_user ── authorization origin of the session
current_user ── effective role for the current SQL operation
```

For real-context privilege checks, **query both expressions on the exact connection in question** before guessing.

## 6. SECURITY DEFINER and Temporary Changes to current_user

A PostgreSQL function can be declared as:

- `SECURITY INVOKER`: generally executes with the privileges of the role calling the function.
- `SECURITY DEFINER`: executes in the privilege context of the **function owner**.

Look at a lab function:

```sql
CREATE FUNCTION lesson_sys.who_is_executing()
RETURNS TABLE (
    effective_role NAME,
    session_role NAME
)
LANGUAGE sql
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $$
    SELECT current_user::name, session_user::name
$$;
```

When called:

```sql
SELECT *
FROM lesson_sys.who_is_executing();
```

`effective_role` **inside the function** reflects the function owner under `SECURITY DEFINER` rules; `session_role` reflects the session authorization. If the function was created by a different role than the connected role, the two values can differ.

### Why not automatically use current_user as the audit actor?

When a trigger function runs as `SECURITY DEFINER`, `current_user` **inside the function** may be the function owner rather than the original caller. If auditing requires knowing "which business user requested the operation," you must design a mechanism to pass an authenticated identity or record the event at a trusted layer.

### Security warning

`SECURITY DEFINER` is not a casual privilege-escalation shortcut. When it is genuinely needed:

1. The function must be owned by a trusted role.
2. Lock down `search_path` safely; prefer explicit `schema.object` qualification.
3. Control `EXECUTE` privileges, including the default grant to `PUBLIC`.
4. Do not construct dynamic SQL by concatenating untrusted input.
5. Audit `CREATE` privileges on schemas listed in `search_path`.

The lab function only uses system expressions, yet these principles still apply before deploying functions with privileges to read or modify sensitive data.

## 7. current_database(): Knowing Exactly Which Database You Are Connected To

`current_database()` returns the name of the database that the current connection is attached to:

```sql
SELECT current_database() AS database_name;
```

In PostgreSQL, **a connection is bound to one specific database**. There is no universal SQL command equivalent to `USE other_database` found in some other systems to switch databases inside the current session.

To access another database in the same cluster, you normally need to **open a connection to that database** or use a dedicated mechanism such as a configured FDW/dblink.

### Why check current_database()?

An application can easily confuse:

- A development database vs. a staging database.
- Databases with identical schema names but different data.
- A connection string configured to point at another default database.
- A connection pool pointing at a datasource from the wrong environment.

Checking:

```sql
SELECT
    current_database(),
    session_user,
    current_user,
    pg_backend_pid();
```

helps pinpoint the **database, role, and backend of the exact connection** before investigating further.

## 8. current_schema() and current_schemas()

A PostgreSQL database can contain multiple schemas such as `public`, `lesson_sys`, or various domain schemas.

Two key functions:

```sql
SELECT
    current_schema() AS current_schema_name,
    current_schemas(false) AS explicit_search_schemas,
    current_schemas(true) AS effective_search_schemas;
```

Meaning:

- `current_schema()` returns the current schema according to the effective search path rules; it also corresponds to the default schema for object-creation statements without a schema prefix.
- `current_schemas(false)` returns the list of **valid** schemas from the configured search path.
- `current_schemas(true)` may also include schemas searched **implicitly**, such as `pg_catalog` and the current temporary schema when applicable.

Results depend on session configuration, existing schemas/permissions, and the presence of temporary objects; do not copy a specific output as a universal baseline across all servers.

### search_path configures object resolution, not privileges

```sql
SHOW search_path;

SELECT current_setting('search_path') AS configured_path;
```

`search_path` determines which schemas PostgreSQL searches when an **unqualified object name** is used.

Lab example:

```sql
SET search_path TO lesson_sys, public;

SELECT staff_id, full_name
FROM staff
ORDER BY staff_id;

RESET search_path;
```

With that `search_path`, the short name `staff` can resolve to `lesson_sys.staff` if the role has appropriate access privileges.

However:

**`SET search_path TO lesson_sys` neither grants `USAGE` on the schema nor grants `SELECT` on the table.** Name resolution and access privileges are two separate mechanisms.

### Distinguishing schema names from table aliases

```sql
SELECT s.full_name
FROM lesson_sys.staff AS s;
```

- `lesson_sys`: schema qualifying the actual object.
- `staff`: actual table name inside the schema.
- `s`: source alias within the query block.
- `s.full_name`: `full_name` column of source `s`.

Do not confuse `s` with a new schema, and do not reference the original table name instead of the alias within the same query block once an alias has been assigned.

## 9. pg_catalog, pg_temp, and Risks from search_path

Two special schemas to know:

- **`pg_catalog`** holds system objects, built-in functions, and system catalogs.
- **`pg_temp`** refers to the session's temporary-object schema when one exists.

PostgreSQL applies special lookup rules for these schemas; you cannot just look at the `SHOW search_path` string and assume it represents the complete effective resolution order for every kind of object.

Example:

```sql
SELECT
    current_schemas(true) AS effective_schemas,
    current_schemas(false) AS configured_valid_schemas;
```

### Why is search_path security-relevant?

If a `SECURITY DEFINER` function calls objects by unqualified names and an untrusted schema can supply an object of the same name, name resolution can be hijacked. That is a form of **search-path hijacking**.

For privileged code:

```sql
CREATE FUNCTION lesson_sys.safe_example(p_text TEXT)
RETURNS TEXT
LANGUAGE sql
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $$
    SELECT pg_catalog.lower(p_text)
$$;
```

This example pins the search path and schema-qualifies the built-in function. When referencing business tables inside a function, also write `lesson_sys.staff` explicitly instead of relying on a session-modifiable schema path.

**Do not assume every privileged function is safe merely because it runs inside PostgreSQL.** Security also depends on owner, `EXECUTE` grants, `search_path`, referenced objects, and internal SQL logic.

## 10. Checking Object Existence with to_regclass()

During debugging, you sometimes need to know whether a table name resolves to an existing relation.

```sql
SELECT
    to_regclass('lesson_sys.staff') AS known_table,
    to_regclass('lesson_sys.nonexistent_table') AS missing_table;
```

Expected results:

- `known_table`: a `regclass` value representing the matching relation.
- `missing_table`: SQL `NULL` if no object exists under that name.

Helpful property: `to_regclass(text)` can return `NULL` rather than raising an error for a nonexistent relation name.

### Difference from casting directly to regclass

```sql
SELECT 'lesson_sys.staff'::regclass AS table_object;
```

If the relation exists, the cast succeeds; if not, `::regclass` raises an error. Choose `to_regclass()` when you want a controlled existence check.

**Warning:** The existence of a relation **does not mean the role has permission to read its data**. `to_regclass` does not replace `has_table_privilege`, `has_schema_privilege`, or RLS evaluation.

### Name parameters must still be controlled

If relation names are generated dynamically from input, distinguish object-name text from SQL identifiers and apply proper quoting/validation. Never concatenate arbitrary table names from HTTP requests into executed SQL.

## 11. pg_backend_pid(): Identifying the Current Backend

`pg_backend_pid()` returns the **process ID of the PostgreSQL backend** serving the current session:

```sql
SELECT pg_backend_pid() AS backend_pid;
```

Useful when:

- Correlating server logs with an application session.
- Finding the matching row in `pg_stat_activity`.
- Checking whether a connection pool reuses the same backend across two consecutive borrows.
- Diagnosing a transaction, lock wait, or timeout on the exact connection.

### A backend PID is neither a user ID nor a request ID

One backend can serve many sequential requests when connections are reused. Operating systems can also reuse PIDs after a process terminates. Therefore, **a PID is not a globally unique historical identifier for a request**.

In logs and traces, combine backend PID with application name, timestamp, request/correlation ID, and any other fields required by your logging policy.

## 12. Connection Address Information: inet_client_* and inet_server_*

Several system functions let you inspect the network endpoints of a session:

```sql
SELECT
    inet_client_addr() AS client_ip,
    inet_client_port() AS client_port,
    inet_server_addr() AS server_ip,
    inet_server_port() AS server_port;
```

| Function | Meaning |
|---|---|
| `inet_client_addr()` | Client-side IP address as seen by the backend connection. |
| `inet_client_port()` | Client-side port when applicable. |
| `inet_server_addr()` | Server-side IP address used by the connection. |
| `inet_server_port()` | Server-side port when applicable. |

**Do not assume these values always contain an IP address.** Connections over Unix-domain sockets may return SQL `NULL` for the IP address and represent the port specially as documented by PostgreSQL. In container, proxy, or PgBouncer environments, the client address observed by PostgreSQL may be the **proxy**, not the end HTTP user's IP.

### Do not treat an IP address as an authenticated identity

IPs can change, sit behind NAT, or pass through load balancers. `inet_client_addr()` is useful for network diagnostics, but **does not prove which business user performed an action**.

## 13. pg_stat_activity: Observing the Right Backend

The system view `pg_stat_activity` shows active backends and sessions.

Find the current connection itself:

```sql
SELECT
    pid,
    usename,
    datname,
    application_name,
    client_addr,
    backend_start,
    xact_start,
    state,
    wait_event_type,
    wait_event
FROM pg_catalog.pg_stat_activity
WHERE pid = pg_backend_pid();
```

Key fields:

- `pid`: backend PID.
- `usename`: session role according to backend metadata.
- `datname`: connected database.
- `application_name`: configured application label.
- `backend_start`: timestamp when the backend started.
- `xact_start`: start time of the current transaction, if any.
- `state`: backend state reported by the statistics subsystem.
- `wait_event_type`/`wait_event`: reported wait category and wait event, if any.

### Visibility into other sessions may be restricted

Ordinary roles cannot necessarily inspect every sensitive field of other sessions. Certain monitoring details require an appropriate role or monitoring privilege such as `pg_monitor`/`pg_read_all_stats`, depending on requirements.

**Do not grant superuser merely to view pg_stat_activity.** Choose the least-privileged monitoring role fit for purpose.

### Be careful with query text

`pg_stat_activity` includes a `query` field containing statement text subject to context and privileges. SQL text may contain sensitive literals if applications embed literals directly. Mask or redact contents appropriately when exporting debug reports or logs.

## 14. version(), server_version, and server_version_num

To determine the PostgreSQL version:

```sql
SELECT version() AS build_description;

SHOW server_version;

SELECT current_setting('server_version') AS server_version;

SELECT
    current_setting('server_version_num')::integer
        AS server_version_number;
```

Differences:

- `version()` typically contains the version description along with build/platform details.
- `server_version` is the server version string.
- `server_version_num` is the numeric version value, which is easier to use in logic conditions than parsing a string manually.

In real systems, do not treat `version()` as a complete "health check": it shows that the server answers a query, **not that the database is ready for all writes, that replication is healthy, or that the application holds all required privileges**.

### Check the version before relying on newer features

A feature or function variant may not exist on an older PostgreSQL release. Instead of guessing based on your local workstation version, query the **exact server the application connects to**.

Example during migration checks:

```sql
SELECT
    current_database(),
    current_setting('server_version_num')::integer AS version_num;
```

Do not hardcode a single version number across deployment docs if dev, staging, and production environments may run different versions.

## 15. current_setting(): Reading Runtime Configuration Parameters

`current_setting(name)` reads the current value of a PostgreSQL configuration parameter.

```sql
SELECT
    current_setting('TimeZone') AS session_timezone,
    current_setting('search_path') AS schema_search_path,
    current_setting('application_name') AS application_name,
    current_setting('statement_timeout') AS statement_timeout;
```

The results have **type text**. If you need numeric values, cast only when you know the exact format and unit of the parameter being read.

### SHOW as the familiar interactive inspection command

```sql
SHOW TimeZone;
SHOW search_path;
SHOW application_name;
SHOW statement_timeout;
```

`SHOW` is convenient when checking a single setting. `current_setting()` is convenient when you want to **return multiple settings in one SELECT**, combine them with role/database info, or use the value inside an expression.

### Nonexistent parameters

For an unrecognized parameter name, a normal call:

```sql
SELECT current_setting('unknown.demo_parameter');
```

raises an error because PostgreSQL does not recognize the setting.

Optional form:

```sql
SELECT current_setting(
    'unknown.demo_parameter',
    true
) AS optional_value;
```

The second argument `missing_ok = true` returns SQL `NULL` when the setting does not exist according to the function's rules.

**Do not treat missing_ok as a configuration-name validation mechanism**. Custom configuration parameters can still have empty strings or previously set session values; handle both `NULL` and empty strings according to your application contract.

## 16. set_config(), SET, and Scope of Effect

`set_config(name, value, is_local)` updates an eligible runtime parameter within the permitted scope.

Example:

```sql
SELECT set_config(
    'application_name',
    'demo-report-worker',
    false
) AS effective_application_name;

SELECT current_setting('application_name');
```

The argument `is_local = false` sets the parameter with **session-level** duration under PostgreSQL's transaction rules; do not mistake this for persisting a change into `postgresql.conf`.

The corresponding `SET` syntax:

```sql
SET application_name = 'demo-report-worker';

SHOW application_name;

RESET application_name;
```

`RESET` returns the setting to the default applicable for the session according to the active configuration hierarchy—it does not mean "set to an empty string" for every setting.

### SET LOCAL applies only within the transaction

```sql
BEGIN;

SET LOCAL statement_timeout = '2s';

SELECT current_setting('statement_timeout') AS inside_transaction;

COMMIT;

SELECT current_setting('statement_timeout') AS after_commit;
```

After `COMMIT`, the `SET LOCAL` change no longer applies; the setting reverts to the level effective outside the transaction (such as a previously set session value).

Similarly:

```sql
BEGIN;

SELECT set_config(
    'application_name',
    'one-request-only',
    true
);

SELECT current_setting('application_name');

ROLLBACK;
```

Passing `true` scopes the setting to **the current transaction**. After rollback, the transaction-local value does not linger as a long-lived session setting.

### Do not rely on SET LOCAL outside an explicit transaction

To achieve predictable transaction-local behavior, place `SET LOCAL` **explicitly inside `BEGIN ... COMMIT/ROLLBACK`**. When using connection pools or JDBC auto-commit, verify that all related statements truly execute on the same connection and inside the same transaction.

## 17. pg_settings: Values, Sources, and Configuration Contexts

`pg_catalog.pg_settings` is a system view more informative than `SHOW` when you need to understand **where a configuration value comes from and at what scope it can be changed**.

```sql
SELECT
    name,
    setting,
    unit,
    context,
    source,
    pending_restart
FROM pg_catalog.pg_settings
WHERE lower(name) IN (
    'timezone',
    'search_path',
    'application_name',
    'statement_timeout',
    'max_connections'
)
ORDER BY name;
```

Selected columns:

| Column | Meaning |
|---|---|
| `name` | Setting name. |
| `setting` | Current value as text. |
| `unit` | Unit or unit representation, if applicable. |
| `context` | Context level required to change the setting. |
| `source` | Source determining the active value, such as default, config file, user/session, etc. |
| `pending_restart` | Whether a pending configuration change requires a server restart to take effect. |

### Not every setting can be changed with SET

For example, `max_connections` typically requires a server restart to apply a new value and is not something you can arbitrarily change with:

```sql
-- Not a valid way to change max_connections at runtime:
-- SET max_connections = 200;
```

By contrast, `application_name` and `statement_timeout` support session/transaction-level changes when the role has permission.

### Configuration sources and viewing permissions

Certain fields in `pg_settings`, such as source file locations, may be restricted based on privileges. Do not grant overly broad privileges solely to inspect a setting; use the columns you need and an appropriate monitoring role.

Do not rely on `SHOW search_path` alone to conclude what value **persists after a restart**. The effective value may originate from login role defaults, database settings, session commands, or transaction commands; inspecting `source` and configuration management reveals the true cause.

## 18. Custom Configuration Parameters for Request Context

Applications can use custom setting names, for example:

```sql
BEGIN;

SELECT set_config('app.request_id', 'req-123', true);
SELECT set_config('app.actor_id', 'user-456', true);

SELECT
    NULLIF(
        current_setting('app.request_id', true),
        ''
    ) AS request_id,
    NULLIF(
        current_setting('app.actor_id', true),
        ''
    ) AS actor_id;

COMMIT;
```

This is helpful when triggers or functions need to read **request context** within the same transaction.

However, there are limits:

- `app.actor_id` is an **application-supplied string**; PostgreSQL does not independently authenticate the web user behind that ID.
- Any client permitted to run SQL on the connection can often set custom settings itself.
- For RLS or auditing, do not treat client-controlled custom settings as standalone security proof.
- When connections are reused, prefer transaction scope and always complete transactions cleanly so state cannot leak into subsequent requests.

### Connection pool lesson

```text
Request A
    └── Borrows connection X
          SET app.actor_id = 'user-A'  [session]
          returns connection to pool

Request B
    └── Borrows connection X again
          risks reading app.actor_id = 'user-A'
          if the pool/app does not reset state
```

Using `SET LOCAL`/`set_config(..., true)` inside a transaction helps reduce **context leakage** between requests when the application manages transaction boundaries properly.

## 19. System Time Functions: Transaction, Statement, and Clock

PostgreSQL offers several "current time" expressions, and they do not share the same semantics:

| Expression | Observed point in time |
|---|---|
| `CURRENT_TIMESTAMP` | Start time of the current transaction. |
| `now()` | Equivalent to the start time of the current transaction. |
| `transaction_timestamp()` | Start time of the current transaction. |
| `statement_timestamp()` | Start time of the current statement. |
| `clock_timestamp()` | Wall-clock time when the function is called; can advance within the same statement. |
| `CURRENT_DATE` | Current date under the session's time/time-zone context. |

Example:

```sql
BEGIN;

SELECT
    now() AS transaction_time,
    statement_timestamp() AS statement_time,
    clock_timestamp() AS wall_clock_time;

SELECT pg_sleep(1);

SELECT
    now() AS transaction_time,
    statement_timestamp() AS statement_time,
    clock_timestamp() AS wall_clock_time;

ROLLBACK;
```

Inside a transaction:

- `now()` stays fixed at the transaction start time.
- `statement_timestamp()` in the second `SELECT` advances compared with the first statement.
- `clock_timestamp()` reads the wall clock at call time.

### Do not use timestamps as proof of commit order

Two transactions can start in order A then B, yet commit in order B then A. Neither `now()` nor `statement_timestamp()` **guarantees commit order**.

If business logic needs monotonically increasing entity version numbers, use proper locking, version columns, or transaction-safe mechanisms rather than timestamps as concurrency keys.

## 20. Operations-Related Server Status Functions

Certain system functions help inspect server context:

```sql
SELECT
    pg_is_in_recovery() AS in_recovery,
    pg_postmaster_start_time() AS postmaster_started_at;
```

Meaning:

- `pg_is_in_recovery()` indicates whether the server is currently in recovery under PostgreSQL semantics; on a physical standby it returns true.
- `pg_postmaster_start_time()` returns when the postmaster/server process started according to server state.

### In recovery is not a full topology check

`pg_is_in_recovery() = false` does not by itself prove that the application can write to every table or that replication is healthy. Write privileges, transaction modes, proxy routing, replication lag, and other conditions may still restrict operations.

Likewise, `pg_postmaster_start_time()` helps correlate restarts, but does not replace system monitoring, readiness checks, and replication monitoring.

## 21. Privileges in PostgreSQL: Object Privileges and Role Membership

PostgreSQL uses **roles** for both identity and authorization. Common privileges include:

| Object | Common privileges | Example purpose |
|---|---|---|
| Database | `CONNECT`, `CREATE`, `TEMPORARY` | Connecting, creating schemas, creating temporary objects. |
| Schema | `USAGE`, `CREATE` | Resolving/using objects in the schema, creating new objects. |
| Table/view | `SELECT`, `INSERT`, `UPDATE`, `DELETE`, `TRUNCATE`, `REFERENCES`, `TRIGGER`, `MAINTAIN` (version-dependent) | Reading/writing and performing operations appropriate to the object type. |
| Column | `SELECT`, `INSERT`, `UPDATE`, `REFERENCES` | Selective column-level access grants. |
| Sequence | `USAGE`, `SELECT`, `UPDATE` | Accessing and controlling sequences per privilege semantics. |
| Function/procedure | `EXECUTE` | Permitting invocation of the callable object. |
| Role membership | `MEMBER`, `USAGE` via `pg_has_role` | Checking role relationships and privilege inheritance under role rules. |

**Not every object supports every privilege in the table.** Privileges such as `MAINTAIN` depend on PostgreSQL version. Always verify version and object type before specifying a particular privilege name.

### Two privilege layers often required together

To run:

```sql
SELECT *
FROM lesson_sys.staff;
```

a role typically needs:

1. `USAGE` on schema `lesson_sys`.
2. `SELECT` on table `lesson_sys.staff`, or privileges covering all columns being read.

**Holding SELECT on a table without USAGE on its schema can still block access in normal queries.** Conversely, holding `USAGE` on a schema does not grant `SELECT` on its tables.

### Privileges and object ownership

Object owners have special management and grant capabilities under specific rules, and superusers bypass most privilege checks. The `has_*_privilege` functions must be interpreted alongside ownership, role membership, and special privileges rather than by inspecting a single isolated `GRANT` line.

## 22. has_database_privilege(): Checking Database Privileges

Example checking the effective role's privileges on the current database:

```sql
SELECT
    current_database() AS db_name,
    has_database_privilege(
        current_user,
        current_database(),
        'CONNECT'
    ) AS can_connect,
    has_database_privilege(
        current_user,
        current_database(),
        'CREATE'
    ) AS can_create_in_database,
    has_database_privilege(
        current_user,
        current_database(),
        'TEMPORARY'
    ) AS can_create_temp_objects;
```

Privilege-check functions return boolean values when given valid objects and arguments. They answer **"Does the grant path for this role currently allow this privilege on that object?"**

### CONNECT = true does not mean schemas/tables are accessible

`has_database_privilege(..., 'CONNECT')` only checks database connection privilege; it does not check whether:

- The role has `USAGE` on business schemas.
- The role has `SELECT` on tables.
- RLS filters out rows.
- A function has `EXECUTE`.

Furthermore, network connections remain subject to **authentication and access rules** such as `pg_hba.conf` and proxies. `CONNECT` privilege is just one layer of the picture and does not simulate the full client login handshake.

## 23. has_schema_privilege(): USAGE and CREATE Privileges

Example:

```sql
SELECT
    has_schema_privilege(
        current_user,
        'lesson_sys',
        'USAGE'
    ) AS can_use_schema,
    has_schema_privilege(
        current_user,
        'lesson_sys',
        'CREATE'
    ) AS can_create_in_schema;
```

Meaning:

- **`USAGE`**: privilege to use/look up objects inside the schema under authorization rules.
- **`CREATE`**: privilege to create new objects in the schema, though it does not automatically grant special privileges on all existing objects.

### A common pitfall

Suppose role `report_reader` is granted:

```sql
GRANT SELECT ON lesson_sys.staff TO report_reader;
```

but **has not been granted `USAGE` on `lesson_sys`**. Queries reading the table can still fail due to missing schema privilege.

Usually you also need:

```sql
GRANT USAGE ON SCHEMA lesson_sys TO report_reader;
```

These `GRANT` statements are illustrative administration examples assuming the role exists and the executor has grant rights; they are not run automatically as read-only checks.

### USAGE does not grant schema-modification privileges

A role holding only `USAGE` cannot run `CREATE TABLE lesson_sys.some_table`. `CREATE` is a separate privilege.

## 24. has_table_privilege(): Checking SELECT, INSERT, UPDATE, and DELETE

Example using the lab table:

```sql
SELECT
    has_table_privilege(
        current_user,
        'lesson_sys.staff',
        'SELECT'
    ) AS can_select_staff,
    has_table_privilege(
        current_user,
        'lesson_sys.staff',
        'INSERT'
    ) AS can_insert_staff,
    has_table_privilege(
        current_user,
        'lesson_sys.staff',
        'UPDATE'
    ) AS can_update_staff,
    has_table_privilege(
        current_user,
        'lesson_sys.staff',
        'DELETE'
    ) AS can_delete_staff;
```

The function has overloads taking user, table, and privilege, or omitting user to check the current effective role according to function rules.

Short form:

```sql
SELECT
    has_table_privilege(
        'lesson_sys.staff',
        'SELECT'
    ) AS current_role_can_select;
```

### The table name must exist

For privilege functions accepting a table name as text, an invalid or missing object name can raise a relation-resolution error. Do not conflate "does not exist" with "exists without privilege."

Safer existence check before checking privileges:

```sql
SELECT
    to_regclass('lesson_sys.staff') IS NOT NULL
        AS staff_relation_exists;
```

After confirming the object exists, call `has_table_privilege` to check access. In dynamic debugging queries, remember concurrent schema changes and schema permissions can still interfere; two separate checks do not form a race-free transactional lock.

### Privileges can come from multiple paths

`has_table_privilege` evaluates PostgreSQL's full privilege rules, not solely direct grants on that role. Privileges may arrive via membership/inheritance, `PUBLIC`, ownership, or superuser status.

## 25. has_column_privilege(): Column-Level Authorization

A table can hold both public fields and sensitive fields:

```text
lesson_sys.staff
├── staff_id
├── full_name
├── email
├── salary        <-- sensitive data
└── department
```

PostgreSQL supports `GRANT SELECT(column_name)` to grant read access on specific columns only.

Check example:

```sql
SELECT
    has_column_privilege(
        current_user,
        'lesson_sys.staff',
        'full_name',
        'SELECT'
    ) AS can_read_full_name,
    has_column_privilege(
        current_user,
        'lesson_sys.staff',
        'salary',
        'SELECT'
    ) AS can_read_salary;
```

**has_column_privilege returns true when the role holds either table-level privilege or column-specific privilege.** Do not inspect only column-level grant tables and conclude a role lacks access if it also received `SELECT ON TABLE` through another path.

### Column-restricted grant example

**Only for administrators with appropriate privileges in the lab database:**

```sql
CREATE ROLE lab_reader NOLOGIN;

GRANT USAGE ON SCHEMA lesson_sys TO lab_reader;

GRANT SELECT (staff_id, full_name, department)
ON lesson_sys.staff TO lab_reader;
```

Then, assuming the role holds no other grants:

```sql
SELECT
    has_table_privilege(
        'lab_reader',
        'lesson_sys.staff',
        'SELECT'
    ) AS full_table_select,
    has_column_privilege(
        'lab_reader',
        'lesson_sys.staff',
        'full_name',
        'SELECT'
    ) AS name_select,
    has_column_privilege(
        'lab_reader',
        'lesson_sys.staff',
        'salary',
        'SELECT'
    ) AS salary_select;
```

Expected semantics:

- `full_table_select`: **false** if there is no table-wide `SELECT` grant through any other path.
- `name_select`: **true**.
- `salary_select`: **false**.

### Practical application

Avoid `SELECT *` for roles granted access to only a subset of columns. Choose:

```sql
SELECT staff_id, full_name, department
FROM lesson_sys.staff;
```

This both respects column-level grants and prevents APIs from accidentally leaking sensitive columns.

**Note:** Referencing columns in `WHERE`, `ORDER BY`, or other expressions is also governed by column `SELECT` privilege rules; it is not only output columns that matter.

## 26. has_sequence_privilege(): Privileges on Sequences

Sequences are separate objects in PostgreSQL. Tables using `serial` or manually declared sequences may require appropriate sequence privileges when applications invoke `nextval()`/`currval()`/`setval()` depending on each function's semantics.

Example retrieving the sequence attached to an identity column in the lab table:

```sql
SELECT
    pg_get_serial_sequence(
        'lesson_sys.staff',
        'staff_id'
    ) AS associated_sequence;
```

`pg_get_serial_sequence` locates the sequence linked to a column under PostgreSQL rules, including `serial` and identity columns.

Check privileges:

```sql
SELECT
    has_sequence_privilege(
        current_user,
        pg_get_serial_sequence(
            'lesson_sys.staff',
            'staff_id'
        ),
        'USAGE'
    ) AS can_use_associated_sequence;
```

### Distinguishing SERIAL and IDENTITY

`GENERATED ... AS IDENTITY` and `serial` both allocate values via sequences, yet **their privilege rules on INSERT differ**. Do not assume every `INSERT` into an identity-column table requires the caller role to hold `USAGE` on the sequence the same way `serial` / direct `nextval()` defaults do.

When diagnosing sequence-related insert failures:

1. Check whether the column is `IDENTITY` or `serial`/default `nextval(...)`.
2. Check `INSERT` privileges on the table/columns.
3. Check the actual function/sequence called in the default expression.
4. Check `has_sequence_privilege` for the referenced sequence.
5. Reproduce using the actual application role rather than relying on owner/superuser privileges.

## 27. has_function_privilege(): EXECUTE Privileges

For the function created in the lab:

```sql
SELECT
    has_function_privilege(
        current_user,
        'lesson_sys.normalize_label(text)',
        'EXECUTE'
    ) AS can_call_normalize_label;
```

Notice the function name includes its **argument type signature**:

```text
lesson_sys.normalize_label(text)
```

PostgreSQL supports **overloading**: two functions with the same name but different argument types are distinct objects. To check the right function, specify the exact signature.

### Zero-argument functions

For a function without parameters:

```sql
SELECT
    has_function_privilege(
        current_user,
        'lesson_sys.who_is_executing()',
        'EXECUTE'
    ) AS can_call_context_function;
```

### PUBLIC may hold EXECUTE by default

In PostgreSQL, newly created functions often grant `EXECUTE` to `PUBLIC` by default unless default privileges or explicit revokes change that behavior. Therefore, merely running:

```sql
GRANT EXECUTE
ON FUNCTION lesson_sys.normalize_label(text)
TO lab_reader;
```

does not imply other roles were previously blocked from calling the function.

When a function is privileged or reads sensitive data, review `PUBLIC` privileges and revoke them if needed:

```sql
-- Apply only in a lab or an approved migration:
REVOKE EXECUTE
ON FUNCTION lesson_sys.normalize_label(text)
FROM PUBLIC;

GRANT EXECUTE
ON FUNCTION lesson_sys.normalize_label(text)
TO lab_reader;
```

**EXECUTE does not mean the caller holds direct privileges on all tables the function reads.** Under `SECURITY INVOKER`, object access inside the function is checked under caller semantics; under `SECURITY DEFINER`, the function executes with the owner's privileges within its scope.

## 28. pg_has_role(): Role Membership and Privilege Inheritance

PostgreSQL roles can be **granted to other roles**, forming a membership graph.

```text
report_viewer
    ▲
    │ GRANT report_viewer TO app_analyst
    │
app_analyst
```

Example checks:

```sql
SELECT
    pg_has_role(
        current_user,
        'pg_monitor',
        'MEMBER'
    ) AS member_of_pg_monitor,
    pg_has_role(
        current_user,
        'pg_monitor',
        'USAGE'
    ) AS inherits_pg_monitor_privileges;
```

Here `pg_monitor` is a built-in monitoring role available in modern PostgreSQL releases. The two checks illustrate the distinction:

- **`MEMBER`**: checks membership status according to PostgreSQL role semantics.
- **`USAGE`**: checks whether the role's privileges are currently usable by the caller via privilege inheritance (not merely bare membership).

Results depend on grants, membership options, role attributes, and PostgreSQL version. **Being a member of a role does not automatically mean the caller can exercise all its privileges directly**, especially when inheritance or `SET ROLE` options come into play.

### Nonexistent roles

`pg_has_role(..., 'some_role', ...)` raises an error if the role name does not exist; do not treat arbitrary user-supplied role names as safe boolean inputs.

To list existing roles:

```sql
SELECT
    rolname,
    rolcanlogin,
    rolinherit
FROM pg_catalog.pg_roles
WHERE rolname IN ('pg_monitor', 'lab_reader')
ORDER BY rolname;
```

`pg_roles` displays role metadata within system visibility rules; seeing a row there **does not mean you have permission to SET ROLE or grant that role**.

## 29. Creating Roles and GRANT/REVOKE in the Lab

If you hold role-management privileges in the lab database, you can demonstrate the principle of least privilege as follows.

### 29.1. Create a role purely for the example

```sql
-- Run only if lab_reader does not already exist:
CREATE ROLE lab_reader NOLOGIN;
```

`NOLOGIN` means this role is not used for direct login in this configuration; it can still serve as a privilege-group role.

### 29.2. Grant schema USAGE and column SELECT

```sql
GRANT USAGE ON SCHEMA lesson_sys TO lab_reader;

GRANT SELECT (staff_id, full_name, department)
ON lesson_sys.staff TO lab_reader;
```

### 29.3. Grant EXECUTE on a function

```sql
REVOKE EXECUTE
ON FUNCTION lesson_sys.normalize_label(text)
FROM PUBLIC;

GRANT EXECUTE
ON FUNCTION lesson_sys.normalize_label(text)
TO lab_reader;
```

### 29.4. Check privileges by role name

```sql
SELECT
    has_schema_privilege(
        'lab_reader',
        'lesson_sys',
        'USAGE'
    ) AS schema_usage,
    has_column_privilege(
        'lab_reader',
        'lesson_sys.staff',
        'full_name',
        'SELECT'
    ) AS read_name,
    has_column_privilege(
        'lab_reader',
        'lesson_sys.staff',
        'salary',
        'SELECT'
    ) AS read_salary,
    has_function_privilege(
        'lab_reader',
        'lesson_sys.normalize_label(text)',
        'EXECUTE'
    ) AS execute_normalize_label;
```

### 29.5. Revoke when no longer needed

```sql
REVOKE SELECT (staff_id, full_name, department)
ON lesson_sys.staff FROM lab_reader;

REVOKE EXECUTE
ON FUNCTION lesson_sys.normalize_label(text)
FROM lab_reader;
```

**Important:** `REVOKE` on one grant path **does not guarantee the effective privilege disappears**, if the role still derives privilege via membership, `PUBLIC`, table-level grants, or another path. Re-check with `has_*_privilege` after making changes.

### Do not assume SET ROLE works without membership

`CREATE ROLE lab_reader NOLOGIN` does not automatically allow everyone to run `SET ROLE lab_reader`. To test via `SET ROLE`, you need an account permitted to switch into that role under active grant policy. An authorized administrator can grant membership in the lab, though you should never do so on production roles solely to try out a lesson.

## 30. Distinguishing Privilege Checks for Another Role vs. the Current Session

These two queries answer two different questions:

```sql
SELECT has_table_privilege(
    current_user,
    'lesson_sys.staff',
    'SELECT'
) AS my_effective_select;

SELECT has_table_privilege(
    'lab_reader',
    'lesson_sys.staff',
    'SELECT'
) AS lab_reader_select;
```

- The first asks about **the effective role of the current connection**.
- The second asks about **the role named `lab_reader`**, without implying the current connection has become that role.

Just because a privilege check for role X returns true does not mean **the current caller is permitted to impersonate role X** or access data as X.

### Should has_*_privilege serve as the sole authorization gate in an app?

No. Privilege-check functions are helpful for **status display and diagnostics**, whereas actual SQL execution must always rely on PostgreSQL's own authorization enforcement at execution time.

Between an earlier check and a subsequent statement, privileges, objects, or roles may change, and additional layers such as RLS still apply. Relying on a pre-check as a permanent guarantee creates a **time-of-check/time-of-use** gap.

## 31. Table Privileges vs. Row-Level Security

PostgreSQL supports **row-level security (RLS)** to restrict which rows can be read or modified according to policies.

Conceptual flow:

```text
Role has SELECT on table staff
               │
               ▼
        Object privilege check
               │
               ▼
           RLS policy
               │
               ▼
       Only permitted rows
```

When `has_table_privilege(..., 'SELECT')` returns true, it **does not guarantee every row will be returned**. An RLS policy can cause a query to return 0 rows or only a subset.

### Checking whether RLS applies

PostgreSQL provides `row_security_active()` to check whether RLS applies to a table in the current context:

```sql
SELECT row_security_active(
    'lesson_sys.staff'::regclass
) AS rls_active_for_current_context;
```

If RLS is not enabled on the table, the result is normally false. When RLS is enabled, whether policies apply to the current connection also depends on table ownership, bypass privileges, configuration, and PostgreSQL rules.

**Do not infer from `row_security_active` alone whether a role has SELECT privilege.** It checks an orthogonal layer and does not replace object privileges.

### Why might a role have SELECT yet see zero rows?

Reasons to check:

1. Is RLS enabled with a policy filtering rows?
2. Which role is the session running under (`current_user`)?
3. Do tenant-context settings hold the expected values?
4. Is there a filter in `WHERE`, a view, or the application itself?
5. Are you connected to the right database and schema?

In multi-tenant systems, do not rely on a client-editable `app.tenant_id` setting as your sole security boundary.

## 32. Schema, Column, and Role Privileges Interact

Suppose role `lab_reader` holds:

```text
USAGE ON SCHEMA lesson_sys
SELECT (staff_id, full_name) ON TABLE lesson_sys.staff
EXECUTE ON FUNCTION lesson_sys.normalize_label(text)
```

A valid query might look like:

```sql
SELECT staff_id, full_name
FROM lesson_sys.staff
ORDER BY staff_id;
```

However, this query:

```sql
SELECT *
FROM lesson_sys.staff;
```

must read **all columns**, including `salary` and `email`. Unless the role holds read privilege on those columns via another path, `SELECT *` will fail.

### Why can an error still occur even when has_column_privilege for full_name is true?

Because the actual query may still involve:

- Another column without granted access.
- A schema or function invoked inside an expression.
- A view or function with its own security mode.
- RLS policies or session configuration.

**Authorization is the conjunction of multiple checks**, not just one boolean returned by a single function.

## 33. Catalog Views for Inspecting Privileges

In addition to `has_*_privilege`, you can inspect system catalogs and `information_schema`.

### pg_roles

```sql
SELECT
    rolname,
    rolcanlogin,
    rolcreatedb,
    rolcreaterole,
    rolinherit,
    rolbypassrls
FROM pg_catalog.pg_roles
ORDER BY rolname;
```

This shows role metadata, not an exhaustive list of every privilege on every object.

### information_schema.table_privileges

```sql
SELECT
    grantor,
    grantee,
    table_schema,
    table_name,
    privilege_type
FROM information_schema.table_privileges
WHERE table_schema = 'lesson_sys'
ORDER BY table_name, grantee, privilege_type;
```

`information_schema` exposes **declared GRANTs** visible under role and view visibility rules; which rows appear depends on caller privileges and view semantics.

**Do not treat grant-listing views as an automatic reconstruction of all effective privileges.** Inherited privileges, ownership, `PUBLIC`, role membership, and RLS must all be accounted for separately.

### information_schema.column_privileges

```sql
SELECT
    grantee,
    table_schema,
    table_name,
    column_name,
    privilege_type
FROM information_schema.column_privileges
WHERE table_schema = 'lesson_sys'
  AND table_name = 'staff'
ORDER BY grantee, column_name;
```

Useful when auditing an application restricted to specific columns, though once again **effective privileges** should be verified with the appropriate functions and real queries.

## 34. Privileges Inside Views and Functions

When querying through a **view**, privileges on the view, underlying tables, and view security options all affect evaluation. In PostgreSQL versions supporting `security_invoker` on views, underlying table privilege checks behave differently from views operating under owner semantics.

Similarly, for functions:

- `SECURITY INVOKER` generally requires the caller to hold privileges on objects accessed inside the function.
- `SECURITY DEFINER` runs the function body with the owner's privileges, though callers still require `EXECUTE` and any prerequisite access.

Hence, running:

```sql
SELECT has_table_privilege(
    current_user,
    'lesson_sys.staff',
    'SELECT'
);
```

does not by itself answer "will every view or function reading `staff` succeed?" You must examine the **actual execution path**.

### Why not treat views or functions as a casual bypass around every policy?

Views and functions are valid tools for exposing constrained database APIs, provided they are **designed, reviewed, and authorized** as part of your security surface. A `SECURITY DEFINER` function returning all salaries can leak sensitive data if `EXECUTE` is granted too broadly.

## 35. Session Information in Java/JDBC Applications

A Java service usually borrows connections from a datasource/pool. You can inspect its context with:

```java
String sql = """
    SELECT
        current_database() AS database_name,
        session_user AS login_role,
        current_user AS effective_role,
        current_schema() AS schema_name,
        pg_backend_pid() AS backend_pid,
        current_setting('application_name') AS app_name
    """;

try (PreparedStatement ps = connection.prepareStatement(sql);
     ResultSet rs = ps.executeQuery()) {
    if (rs.next()) {
        String database = rs.getString("database_name");
        String loginRole = rs.getString("login_role");
        String effectiveRole = rs.getString("effective_role");
        String schema = rs.getString("schema_name");
        int backendPid = rs.getInt("backend_pid");
        String appName = rs.getString("app_name");

        // Log diagnostic details only as needed, avoiding exposure of sensitive data.
    }
}
```

This snippet uses a Java text block and assumes an already-created `connection`, appropriate imports, and `SQLException` handling.

### Why check on the exact connection?

If you run `SELECT current_user` in `psql` under an admin account while the application connects as `app_service`, your terminal result **does not represent** the application's actual privileges.

With connection pools:

```text
psql admin connection ──> current_user = db_admin
Spring app connection  ──> current_user = app_service
Background worker      ──> current_user = report_worker
```

When diagnosing errors, collect context from the **failing connection itself**, not from another client connected to the same database.

### Do not log everything indiscriminately in production

Depending on policy, role names, database names, and application names can aid observability. Never dump raw SQL query text containing sensitive values, tokens, passwords, personal data, or unrestricted network details into public logs.

## 36. Setting Transaction Context in JDBC

Suppose a request needs to pass `request_id` to a trigger and cap `statement_timeout` for that transaction.

```java
boolean oldAutoCommit = connection.getAutoCommit();

try {
    connection.setAutoCommit(false);

    try (PreparedStatement ps = connection.prepareStatement(
            "SELECT set_config('app.request_id', ?, true)")) {
        ps.setString(1, "req-123");
        ps.execute();
    }

    try (Statement st = connection.createStatement()) {
        st.execute("SET LOCAL statement_timeout = '3s'");
    }

    // Related INSERT/UPDATE statements execute on this same connection.
    // ...

    connection.commit();
} catch (SQLException e) {
    connection.rollback();
    throw e;
} finally {
    connection.setAutoCommit(oldAutoCommit);
}
```

This example highlights the principle: **same connection, same transaction**. In real applications, error cleanup in `finally` and rollback/connection-closing logic must align with your transaction manager and pool. Do not manually toggle auto-commit inside a managed framework transaction such as Spring `@Transactional` if doing so conflicts with the framework's connection management.

### SET LOCAL is not a shared global variable

Changes made inside connection A's transaction do not alter session B. This isolation makes it safe when a server handles many concurrent requests.

### Do not assume every pool automatically runs RESET ROLE

Connection pools vary in how they reset state. If an application runs `SET ROLE` or modifies `search_path` at session scope, verify **which exact pool or driver guarantees which resets**; never assume `close()` on a JDBC wrapper clears every piece of backend state.

## 37. Systematic Workflow for Diagnosing "permission denied"

Suppose an API encounters:

```text
ERROR: permission denied for table staff
SQLSTATE: 42501
```

A systematic diagnostic checklist:

### Step 1 — Identify the connection context

```sql
SELECT
    current_database(),
    session_user,
    current_user,
    current_role,
    pg_backend_pid();
```

### Step 2 — Identify the schema and relation

```sql
SHOW search_path;

SELECT current_schemas(true);

SELECT to_regclass('lesson_sys.staff') AS resolved_table;
```

### Step 3 — Check schema privileges

```sql
SELECT has_schema_privilege(
    current_user,
    'lesson_sys',
    'USAGE'
) AS schema_usage;
```

### Step 4 — Check table and column privileges

```sql
SELECT
    has_table_privilege(
        current_user,
        'lesson_sys.staff',
        'SELECT'
    ) AS select_table,
    has_column_privilege(
        current_user,
        'lesson_sys.staff',
        'full_name',
        'SELECT'
    ) AS select_name,
    has_column_privilege(
        current_user,
        'lesson_sys.staff',
        'salary',
        'SELECT'
    ) AS select_salary;
```

### Step 5 — Check whether RLS applies

```sql
SELECT row_security_active(
    'lesson_sys.staff'::regclass
) AS rls_applies;
```

### Step 6 — Inspect GRANT paths and test under the actual role

If an administrator decides to grant access, grant **only the minimum required privilege** and re-test. Do not reflexively run `GRANT SELECT ON ALL TABLES ...` just to fix a missing read grant on a single column.

### Step 7 — Verify the application environment

Check whether the connection pool uses a different role or session settings than your terminal, whether `SET ROLE` or `SET search_path` is executed, and which exact SQL statement fails. A query inside a function or view may require **different privileges** than querying the base table directly.

## 38. When to Use Privilege Functions vs. Executing Real Queries

| Situation | Helpful function | Still check additionally |
|---|---|---|
| Displaying a database-access dashboard | `has_database_privilege` | Authentication/network/proxy rules when opening real connections. |
| Checking if a role can access a schema | `has_schema_privilege` | Privileges on tables/functions inside the schema. |
| Checking table-level `SELECT` access | `has_table_privilege` | Column privileges, RLS, views/functions. |
| Checking access to a single column | `has_column_privilege` | Any other columns referenced in the query. |
| Checking function invocation | `has_function_privilege` | Internal object privileges and function security mode. |
| Checking sequence access | `has_sequence_privilege` | `IDENTITY`/`serial`/default expressions and specific operations. |
| Checking role membership | `pg_has_role` | Inheritance, `SET ROLE` ability, and effective grant paths. |

These functions are especially helpful for **preflight diagnostics** and administration tools, but permanent security decisions must never rest solely on a precomputed boolean. The database must enforce every real operation directly.

### A combined diagnostic SQL query for incident triage

```sql
SELECT
    current_database() AS db_name,
    session_user AS login_role,
    current_user AS effective_role,
    current_schema() AS schema_name,
    current_setting('search_path') AS path,
    pg_backend_pid() AS pid,
    has_schema_privilege(
        current_user, 'lesson_sys', 'USAGE'
    ) AS schema_usage,
    has_table_privilege(
        current_user, 'lesson_sys.staff', 'SELECT'
    ) AS table_select,
    has_column_privilege(
        current_user, 'lesson_sys.staff', 'full_name', 'SELECT'
    ) AS name_select;
```

Its output is a **point-in-time context snapshot**, not a permanent certificate of privileges.

## 39. Common Mistakes and Misconceptions

### 39.1. Confusing session_user with the web application user

`session_user` is normally a PostgreSQL role, not the HTTP API's logged-in user ID. Keep database identity distinct from business principal identity.

### 39.2. Assuming current_user and session_user are always equal

`SET ROLE` or `SECURITY DEFINER` can make them differ. Check both when debugging.

### 39.3. Using current_role as the original login role

In PostgreSQL, `current_role` tracks the effective role (matching `current_user`); do not substitute it for `session_user` to assert who authenticated at session start.

### 39.4. Assuming SET search_path grants schema access

No. `search_path` governs name resolution; `USAGE` and object privileges are separate.

### 39.5. Assuming schema USAGE allows reading every table in it

No. Each table, view, function, and sequence requires its own privileges.

### 39.6. Assuming has_table_privilege SELECT = false means no columns can be read

Not necessarily. PostgreSQL supports column-level `SELECT` grants. Also check `has_column_privilege`.

### 39.7. Assuming has_table_privilege SELECT = true means every row is visible

No. Row-level security policies or query filters may restrict visible rows.

### 39.8. Assuming role membership guarantees use of all target role privileges

It is not that simple. Membership, inheritance, and `SET ROLE` permissions can differ; inspect `pg_has_role` with the right privilege flag and verify role policies.

### 39.9. Assuming granting EXECUTE to one role makes a function private

Not necessarily. Functions often default to having `EXECUTE` granted to `PUBLIC`. Inspect and revoke `PUBLIC` grants explicitly when needed.

### 39.10. Assuming SECURITY DEFINER is always a safe workaround for permission errors

No. Functions running with owner privileges require hardened `search_path`, input validation, trusted ownership, and tight `EXECUTE` controls to avoid data exposure or privilege escalation.

### 39.11. Assuming is_local = false persists across server restarts

No. `set_config(..., false)` sets session-level runtime state; session changes do not edit persistent configuration files.

### 39.12. Assuming SET LOCAL acts like a session-wide SET

No. `SET LOCAL` lasts only for the current transaction; use explicit transaction boundaries.

### 39.13. Treating pg_backend_pid as a request ID

No. Connection pools reuse backends across many requests, and the OS can reuse PIDs after processes exit.

### 39.14. Assuming inet_client_addr is always the end user's IP

No. PostgreSQL may observe a proxy address or a Unix-socket `NULL`, and an IP is never an authenticated user identity.

### 39.15. Assuming pg_stat_activity always exposes everyone's full SQL text

No. Visibility is governed by role privileges and logging/monitoring configuration.

### 39.16. Assuming now() advances with every statement inside a transaction

No. `now()` stays pinned to transaction start time; use `statement_timestamp()` or `clock_timestamp()` when you need advancing timestamps.

### 39.17. Relying on version() alone to confirm the right environment

No. Also verify database name, role, schema, host/datasource, and expected data.

### 39.18. Assuming revoking one grant removes effective access

Not if access remains via `PUBLIC`, role membership, table-wide grants, or another path.

### 39.19. Assuming SELECT privilege allows SELECT * on every view

No. View definitions, column grants, security modes, and RLS can change what is allowed or returned.

### 39.20. Treating custom app.user_id settings as tamper-proof identity

No. They are session state set by SQL clients; protect identity origin and SQL execution paths accordingly.

## 40. Practice Exercises

### Exercise 1 — Identify session roles

Write a query returning `session_user`, `current_user`, and `current_role`. Explain when the three values can differ and why `current_user` is not automatically the HTTP user.

### Exercise 2 — Distinguish database and schema

Write a query retrieving `current_database()`, `current_schema()`, `current_schemas(true)`, and `current_setting('search_path')`. Explain how `lesson_sys.staff` differs from unqualified `staff` in a `FROM` clause.

### Exercise 3 — SET ROLE

In a lab with an appropriately granted role, run `SET ROLE lab_reader`, inspect `current_user`/`session_user`, and then run `RESET ROLE`. Document the prerequisites required for `SET ROLE` to succeed.

### Exercise 4 — Diagnose missing schema USAGE

Suppose a role holds `SELECT ON lesson_sys.staff` but lacks `USAGE ON SCHEMA lesson_sys`. Write two `has_*_privilege` queries demonstrating both privilege layers and explain why reading the table still fails.

### Exercise 5 — Column-level privileges

Suppose role `lab_reader` is granted only `SELECT(staff_id, full_name)`. Use `has_table_privilege` and `has_column_privilege` to compare table-wide `SELECT`, column `full_name`, and column `salary`. Why is `SELECT *` unsuitable here?

### Exercise 6 — Database privileges

Use `has_database_privilege` to check `CONNECT`, `CREATE`, and `TEMPORARY` on `current_database()`. Do these privileges substitute for `SELECT` on a table?

### Exercise 7 — Function EXECUTE

Check `has_function_privilege('lesson_sys.normalize_label(text)', 'EXECUTE')`. Explain why `(text)` must be specified explicitly and how `PUBLIC` can affect the outcome.

### Exercise 8 — Sequences and IDENTITY

Call `pg_get_serial_sequence('lesson_sys.staff', 'staff_id')` and then check sequence privileges. Explain why `nextval` privilege rules for `serial` columns cannot be applied blindly to `IDENTITY` columns.

### Exercise 9 — Role membership

Check both `pg_has_role(current_user, 'pg_monitor', 'MEMBER')` and its `'USAGE'` variant. Research the difference between membership and inherited usability.

### Exercise 10 — Session config vs. transaction config

Inside a transaction, run `SET LOCAL statement_timeout = '2s'`, read it via `current_setting`, commit, and read it again. Why should you not assume the 2-second value stays active after commit?

### Exercise 11 — Custom GUCs

Set `app.request_id` with `set_config(..., true)` inside a transaction. Read it using `current_setting(..., true)` and `NULLIF`. Explain the risk of passing `is_local = false` when using a connection pool.

### Exercise 12 — Distinguish timestamps

Run `SELECT now(), statement_timestamp(), clock_timestamp()` twice inside the same transaction with `pg_sleep(1)` in between. Which timestamps stay constant and which advance?

### Exercise 13 — Backend and network

Write a query returning `pg_backend_pid()`, `inet_client_addr()`, and `inet_server_addr()`. Why might `client_ip` be SQL `NULL` or a proxy's IP?

### Exercise 14 — pg_stat_activity

Query `pg_stat_activity` with `WHERE pid = pg_backend_pid()`. Inspect `backend_start`, `state`, and `application_name`. State the difference between a backend PID and a request ID.

### Exercise 15 — pg_settings

Look up the rows in `pg_settings` for `statement_timeout` and `max_connections`. Compare `context`, `source`, and `pending_restart`. Why can't every parameter be changed with `SET` at runtime?

### Exercise 16 — Object exists but is inaccessible

Combine `to_regclass('lesson_sys.staff')` and `has_table_privilege(...)`. Explain why knowing a relation exists does not prove a role has `SELECT` access.

### Exercise 17 — SECURITY DEFINER

Create `lesson_sys.who_is_executing()` in the lab and invoke it from a role granted `EXECUTE`. Predict how `current_user` inside the function differs from `session_user`. Why must `current_user` inside that function not be assumed to be the audit actor?

### Exercise 18 — RLS

On an RLS-enabled table in an isolated lab, compare `has_table_privilege(..., 'SELECT')` and `row_security_active(...)`. Explain why a query can still return no rows despite holding `SELECT` privilege.

### Exercise 19 — JDBC diagnostics

Write a `PreparedStatement` reading `current_database()`, `session_user`, `current_user`, `current_schema()`, and `pg_backend_pid()`. Explain why results from the JDBC connection matter more than an admin `psql` session when diagnosing an API issue.

### Exercise 20 — Least-privilege design analysis

An API only needs to read `staff_id` and `full_name` to list staff members. Propose:

1. Minimal database, schema, table, and column privileges.
2. Verification queries using `has_schema_privilege` and `has_column_privilege`.
3. Ways to avoid `SELECT *` or returning full-row JSON.
4. A verification workflow executed as the actual application role rather than superuser.

## Conclusion

PostgreSQL's system functions and special expressions let you **observe the exact execution context**, with each group answering a specific question. **`session_user`** reflects session authorization; **`current_user`/`current_role`** show the effective role; **`current_database()`**, **`current_schema()`**, and **`current_schemas()`** determine where SQL runs and how object names resolve. **`pg_backend_pid()`** and the `inet_*` functions aid connection diagnostics, while **`current_setting()`/`set_config()`/`pg_settings`** reveal active configuration values and their scope of effect.

For privilege checks, always distinguish **database privileges**, **schema privileges**, **table privileges**, **column privileges**, **sequence privileges**, **function EXECUTE privileges**, and **role membership**. Functions like `has_table_privilege` and `pg_has_role` verify effective privileges, yet **do not replace** executing real SQL under the target role, do not guarantee RLS exposes all rows, and do not guarantee privileges cannot change after the check.

In Java/JDBC applications—especially with connection pools—remember the distinction between **session-level state** and **transaction-local state**, use `SET LOCAL` or `set_config(..., true)` for per-transaction request context, and never rely on unverified custom settings as your sole security foundation. Good debugging always starts by confirming **the right database, the right connection, the right effective role, the right schema, the right object, and the right privileges**, before moving on to RLS, views/functions, configuration, and application logic. Mastering these tools enables you to diagnose and resolve PostgreSQL issues accurately, deliberately, and securely.
