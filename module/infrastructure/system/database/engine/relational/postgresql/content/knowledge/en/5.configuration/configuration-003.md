# Precedence Between Server, Database, Role, and Session Configuration in PostgreSQL

A PostgreSQL system can serve multiple applications on the same instance: a sales application requires fast responses, a reporting tool runs long aggregation queries, and an administrative job needs lock-wait timeouts. If every workload shares one common parameter set, optimizing for one group can sometimes cause problems for another.

PostgreSQL solves this through its **configuration parameter** system (commonly known as **GUC – Grand Unified Configuration**). A parameter such as `work_mem` or `statement_timeout` can be declared at the **server level**, **database level**, **role level**, **role–database pair level**, or adjusted within a **session** and **transaction**.

When multiple places set the same parameter, the key question is not "which one was configured first," but **which source has higher precedence, and what value is actually in effect in the connected session?**

This lesson explains how to determine the precedence order, practice inspecting it with `SHOW` and `pg_settings`, understand exceptions caused by privileges or parameter types, and apply this knowledge to operating PostgreSQL applications.

## 1. PostgreSQL Configuration Has Multiple Scopes

Imagine a server serving two databases and multiple accounts:

~~~text
                     PostgreSQL instance
                             |
          postgresql.conf / ALTER SYSTEM / -c
                             |
                +------------+------------+
                |                         |
           Database shopdb          Database reportdb
                |                         |
          Role app_user              Role analyst
                |                         |
           Session A                  Session B
                |
         BEGIN ... SET LOCAL ...
                |
        Executing SQL statement
~~~

For example, an administrator wants:

- All connections by default to use `statement_timeout = '30s'`.
- The reporting database specifically to allow up to `'2min'`.
- A batch account to have `'5min'` regardless of which database it connects to.
- When the batch account runs in the reporting database, a specific `'90s'` limit for that account–database pair.
- One special transaction to have only a `'10s'` limit, and then automatically revert to the session's configuration.

PostgreSQL has mechanisms for every one of these cases without requiring server-wide reconfiguration whenever one query has different needs.

### A Few Common Parameters

| Parameter | Meaning | Common Configuration Scopes |
| --- | --- | --- |
| `work_mem` | Maximum memory for certain sort/hash operations before spilling or using another strategy; not total RAM for the whole query | Server, database, role, session/transaction |
| `statement_timeout` | Execution time limit for a statement according to PostgreSQL rules | Server, database, role, session/transaction |
| `lock_timeout` | Time limit for waiting to acquire a lock | Server, database, role, session/transaction |
| `search_path` | Schema search order when object names are not schema-qualified | Server, database, role, session/transaction |
| `TimeZone` | Time zone used to interpret/display certain temporal data | Server, database, role, session/transaction |
| `shared_buffers` | Size of the instance's shared data buffer pool | Server configuration; usually requires restart |
| `max_connections` | Connection limit for the instance | Server configuration; requires restart |

**Not every parameter can be adjusted at every scope.** `work_mem` can be set with `SET` in a session, whereas `shared_buffers` and `max_connections` cannot be changed per session. PostgreSQL classifies parameters by **context** and required privileges; a later section explains this clearly.

## 2. The Core Precedence Rule

For a **parameter permitted to be set at all relevant levels**, you can remember the order from **less specific defaults** to **more specific applied values**:

~~~text
        PostgreSQL built-in default
                    │
                    ▼
       Server / cluster configuration
          postgresql.conf, ...
                    │
                    ▼
          ALTER DATABASE ... SET
                    │
                    ▼
            ALTER ROLE ... SET
                    │
                    ▼
     ALTER ROLE ... IN DATABASE ... SET
                    │
                    ▼
       Options sent at connection startup
        (e.g., options / PGOPTIONS)
                    │
                    ▼
          SET ... in the session
                    │
                    ▼
      SET LOCAL ... in a transaction
       (only within applicable scope)
~~~

This ordering is a **practical model** for parameters that can be set at the levels above—not a claim that every parameter supports every source. Server configuration also has internal precedence among files, command-line options, and values written by `ALTER SYSTEM`.

### Configuration Source Comparison Table

| Source | Example Syntax | Where Does It Apply? | When Does It Take Effect? |
| --- | --- | --- | --- |
| Server | `work_mem = '4MB'` in config file | Instance-wide default, unless overridden | After configuration is loaded appropriately |
| Database | `ALTER DATABASE shopdb SET work_mem = '8MB';` | New sessions connecting to `shopdb` | On new connections |
| Role | `ALTER ROLE app_user SET work_mem = '16MB';` | New sessions logging in as role `app_user` | On new logins |
| Role in database | `ALTER ROLE app_user IN DATABASE shopdb SET work_mem = '24MB';` | New sessions logging in as `app_user` to `shopdb` | On new logins |
| Client startup options | `PGOPTIONS='-c work_mem=28MB'` | Connections passing those options | At connection creation |
| Session | `SET work_mem = '32MB';` | The session running the command | Once executed; subject to transaction rules |
| Transaction | `SET LOCAL work_mem = '48MB';` | Current transaction | For the remainder of the transaction, per scope rules |

If all four levels—**server, database, role, and role–database**—set `work_mem`, a session logging in as `app_user` to `shopdb` will use the role–database value `24MB`, unless overridden by a higher-precedence source or another specific constraint.

### Does Database or Role Take Higher Precedence?

This is a common point of confusion:

~~~sql
ALTER DATABASE shopdb SET work_mem = '8MB';
ALTER ROLE app_user SET work_mem = '16MB';
~~~

When `app_user` logs into `shopdb` via a **new connection**, the role setting `16MB` takes precedence over the database setting `8MB`.

If you also have:

~~~sql
ALTER ROLE app_user
IN DATABASE shopdb
SET work_mem = '24MB';
~~~

then **the setting for that exact role–database pair** takes precedence over both individual settings.

This rule lets administrators define a general default for a database, then specialize it for different types of accounts using that database.

## 3. Server Configuration: Files and Startup Options

Instance-wide PostgreSQL parameters typically live in `postgresql.conf` or included files. You can view current paths with:

~~~sql
SHOW config_file;
SHOW data_directory;
SHOW hba_file;
~~~

Example lines in `postgresql.conf`:

~~~conf
# Sample values, not mandatory settings:
work_mem = '4MB'
statement_timeout = '30s'
log_min_duration_statement = '1s'
~~~

Values in configuration files generally serve as **defaults** for sessions unless overridden by database, role, or session settings.

### 3.1. include and include_dir

PostgreSQL allows splitting configuration across multiple files:

~~~conf
include = 'common.conf'
include_if_exists = 'optional.conf'
include_dir = 'conf.d'
~~~

When the same parameter is set multiple times across files loaded in sequence, the effective value depends on **configuration processing order**. With `include_dir`, filename ordering matters. Do not just find the first matching line in `postgresql.conf` and assume it is the final value.

### 3.2. ALTER SYSTEM and postgresql.auto.conf

Administrators can use:

~~~sql
-- Illustrative command: changes instance-wide configuration.
ALTER SYSTEM SET work_mem = '6MB';
~~~

`ALTER SYSTEM` writes settings to `postgresql.auto.conf` inside the data directory. This file takes precedence over regular `postgresql.conf` settings and associated includes.

Key distinctions:

- `ALTER SYSTEM` **does not** mean changing `work_mem` only for the person running the command.
- For reloadable parameters, the change applies after the server reloads configuration appropriately.
- For restart-required parameters, a reload is not enough.
- `ALTER SYSTEM` is an administrative operation requiring appropriate privileges and cannot run inside a transaction block.

To refresh reloadable parameters, administrators can run:

~~~sql
SELECT pg_reload_conf();
~~~

A return value of `true` indicates the request to send the reload signal succeeded, **not a guarantee that every parameter was successfully applied**. Inspect logs, `pg_settings`, and pending-restart status to verify the outcome.

To remove an override from `ALTER SYSTEM`:

~~~sql
ALTER SYSTEM RESET work_mem;
SELECT pg_reload_conf();
~~~

Resetting at the server level does not automatically remove overrides at the database, role, or session level. This is a common reason why editing a config file leaves an application still using a different value.

### 3.3. Server Command-Line Options

A PostgreSQL server can be started with `-c` options:

~~~bash
# Illustrative startup syntax; do not run if a server is already running.
postgres -D /path/to/pgdata -c work_mem=8MB
~~~

Parameters passed on the server startup command line take high precedence within the **server configuration layer** compared to files. However, whether a parameter can be overridden by database/role/session still depends on the parameter's **context**; you cannot change `shared_buffers` with `SET LOCAL` just because you know a general precedence hierarchy.

On systems running under systemd or containers, startup options may come from unit files, entrypoints, or configuration management tools rather than appearing directly in `postgresql.conf`.

## 4. ALTER DATABASE SET: Defaults for a Database

Suppose a reporting database needs a longer `statement_timeout` than the global default:

~~~sql
ALTER DATABASE reportdb
SET statement_timeout = '2min';
~~~

This value is used for **new sessions** connecting to `reportdb`, unless overridden by role, role–database pair, or higher-precedence sources.

It **does not**:

- Change `statement_timeout` for any other database.
- Immediately alter already-open sessions.
- Grant table privileges or change login roles.
- Allow changing parameters that can only be configured at server startup.

To remove a database-level default:

~~~sql
ALTER DATABASE reportdb
RESET statement_timeout;
~~~

Afterward, new sessions no longer receive this database-level override, though they may still inherit values from role, role–database pair, server, or client startup options.

### Database Defaults Are Not a Database Transaction

`ALTER DATABASE ... SET` modifies **default configuration for future connections**, not a business transaction across all tables in the database. It does not scan rows to update data and does not alter all existing sessions.

One database can have multiple roles with different parameters. In that case, determining the actual value requires looking at the **specific role logging in**.

## 5. ALTER ROLE SET: Defaults for a Login Role

Setting a parameter by role:

~~~sql
ALTER ROLE report_reader
SET statement_timeout = '45s';
~~~

For a **new session logging in** as `report_reader`, the `45s` setting takes precedence over a database-specific setting if both specify that parameter.

To remove the setting:

~~~sql
ALTER ROLE report_reader
RESET statement_timeout;
~~~

This **resets a default parameter attached to the role**; it does not drop the role and does not reset all server configuration values.

### Role Membership Differs from Logging In as That Role

An account `service_user` may be a member of role `report_reader`, but **`ALTER ROLE report_reader SET ...` settings are not automatically inherited merely through role membership**.

Similarly, running:

~~~sql
SET ROLE report_reader;
~~~

in a session already logged in as another role changes the privilege context per `SET ROLE` rules; it **does not reload** `report_reader`'s GUC defaults as if the session had just logged in as that role.

Therefore:

> When relying on `ALTER ROLE ... SET` to configure operational parameters, identify the **login role used when opening the connection**, not just the effective role after `SET ROLE`.

This is especially important in applications using connection pools and group-role permission models.

## 6. ALTER ROLE IN DATABASE: The Most Specific Role–Database Configuration

An account may need different settings when accessing two different databases:

~~~sql
ALTER ROLE report_reader
IN DATABASE reportdb
SET statement_timeout = '90s';
~~~

This setting applies when **both** conditions are met:

1. A new session logs in as `report_reader`.
2. That session connects to `reportdb`.

If `report_reader` connects to `shopdb`, the `report_reader/reportdb` pair setting **does not apply**. PostgreSQL then evaluates values from the role, the other target database, and the server.

Order in this specific example:

~~~text
Server:                  statement_timeout = 30s
Database reportdb:       statement_timeout = 2min
Role report_reader:      statement_timeout = 45s
Role + database:         statement_timeout = 90s

Connection report_reader → reportdb: 90s
Connection report_reader → shopdb:   45s
Connection other role    → reportdb: 2min
Connection other role    → shopdb:   30s (assuming no other overrides)
~~~

These outcomes assume no `PGOPTIONS`, `SET`, or higher-precedence parameter sources exist.

To remove the pair-specific setting:

~~~sql
ALTER ROLE report_reader
IN DATABASE reportdb
RESET statement_timeout;
~~~

After resetting, new connections by `report_reader` to `reportdb` fall back to the next applicable value in the precedence chain—in the example above, `45s` from the role setting.

## 7. Session Configuration with SET and RESET

After connecting successfully, users can adjust permitted parameters at the session level:

~~~sql
SHOW work_mem;

SET work_mem = '32MB';

SHOW work_mem;
~~~

`SET work_mem` changes the value for the **currently running session**; it does not modify `postgresql.conf`, affect other sessions, or create a new default for future logins.

### 7.1. What Value Does RESET Return To?

~~~sql
RESET work_mem;
SHOW work_mem;
~~~

`RESET work_mem` restores the **session's effective default value** according to the configuration sources loaded at connection time and related rules; it does not necessarily revert to PostgreSQL's compiled-in boot default.

Example:

~~~text
Server = 4MB
Database = 8MB
Role = 16MB
Role+database = 24MB

Initial new connection: 24MB
SET work_mem = '32MB': 32MB
RESET work_mem: 24MB
~~~

This is why `RESET` does not mean "erase all database and role settings."

### 7.2. RESET ALL

~~~sql
RESET ALL;
~~~

This command restores all resettable parameters in the session to their session default values per PostgreSQL rules. It does not remove settings in configuration files, `ALTER DATABASE SET`, or `ALTER ROLE SET`.

### 7.3. SET Inside a Transaction and ROLLBACK

An important detail: `SET` executed **inside a transaction** follows commit/rollback semantics.

~~~sql
SHOW work_mem;         -- Suppose 24MB.

BEGIN;
SET work_mem = '32MB';
SHOW work_mem;         -- 32MB inside the transaction.
ROLLBACK;

SHOW work_mem;         -- Reverts to 24MB.
~~~

If the transaction runs `COMMIT` instead of `ROLLBACK`, a regular `SET` change can persist in the session until reset, overwritten, or the session ends.

Thus, saying "`SET` always lasts until the end of the connection" is **not completely accurate**: when executed inside a failed or rolled-back transaction, its effect can be undone.

## 8. SET LOCAL: Transaction-Scoped Precedence

When only a single transaction needs a different setting, use `SET LOCAL`:

~~~sql
SHOW work_mem;  -- For example, 24MB.

BEGIN;

SET LOCAL work_mem = '48MB';
SHOW work_mem;  -- 48MB for the remainder of the transaction.

-- Query that needs this setting.
SELECT current_setting('work_mem');

COMMIT;

SHOW work_mem;  -- Reverts to the effective value prior to SET LOCAL.
~~~

Key points:

- `SET LOCAL` takes effect only within the currently open transaction and within its valid scope under PostgreSQL rules.
- When the transaction ends with `COMMIT` or `ROLLBACK`, the `SET LOCAL` effect disappears.
- Running `SET LOCAL` outside a transaction block does not mean "set for the next SQL statement"; PostgreSQL issues a warning and does not create an extended transaction scope to retain that value.
- If using a savepoint and rolling back to a savepoint prior to the setting command, the effect of `SET`/`SET LOCAL` in the rolled-back portion can also be reverted.

### Distinguishing SET and SET LOCAL

| Criterion | `SET work_mem = '32MB'` | `SET LOCAL work_mem = '48MB'` |
| --- | --- | --- |
| Primary scope | Session | Current transaction |
| Usable outside `BEGIN`? | Yes | Not useful outside a transaction block |
| After `COMMIT` | Can remain active in the session | Expires |
| After `ROLLBACK` if set in transaction | Change made in the transaction is rolled back | Expires |
| Changes database/role defaults? | No | No |
| Automatically affects other connections? | No | No |

### Application Example: Limiting a Reporting Transaction

~~~sql
BEGIN;

SET LOCAL statement_timeout = '10s';
SET LOCAL lock_timeout = '2s';

SELECT
    customer_id,
    SUM(total_amount)
FROM sales_orders
GROUP BY customer_id;

COMMIT;
~~~

`sales_orders` is a **hypothetical** table. The example shows how to constrain timeouts for the **current transaction** without altering timeouts for subsequent queries after the transaction ends.

**Note:** If a statement times out and puts the transaction into an aborted state, the application must `ROLLBACK` or handle savepoints appropriately. `SET LOCAL` does not automatically turn a failed transaction into a successful one.

## 9. Client Configuration at Connection Creation

Beyond server, database, role, and `SET` settings, clients can pass configuration options when establishing a connection. With `libpq`/`psql`, a Unix shell environment can use `PGOPTIONS`:

~~~bash
PGOPTIONS='-c work_mem=28MB -c statement_timeout=15s' \
  psql -h 127.0.0.1 -U app_user -d shopdb
~~~

This illustrative command assumes the account and database exist. In the new connection:

~~~sql
SHOW work_mem;
SHOW statement_timeout;
~~~

Client options can override database and role defaults for parameters **permitted** to be set this way. A valid `SET` run after connecting can still change the session's value.

Avoid these misconceptions:

- The `PGOPTIONS` environment variable is how **libpq sends startup options**; it does not modify server configuration.
- Not every application uses libpq; Java JDBC has its own driver option mechanisms.
- A parameter requiring a server restart cannot be validly changed solely via client startup options.
- When inspecting `source` in `pg_settings`, the value may be reported as coming from client/startup packet rather than `ALTER ROLE`.

In systems with connection pools, only **newly created physical connections** go through this startup step. An HTTP request borrowing an existing pooled connection may inherit session values modified by a previous request if the pool does not properly manage or reset session state.

## 10. Reproducible Practice: Observing Every Precedence Level

This section uses `work_mem` because it supports session-level configuration. Run examples on a **test database** using an administrative account permitted to create roles/databases and modify their defaults.

Note: the MB values here serve to **observe precedence levels**, not as recommendations for tuning `work_mem` in production. `work_mem` can be consumed by **multiple operations per query, multiple sessions, and parallel workers**; setting it too high broadly can increase out-of-memory risk.

### Step 1. Create the Practice Role and Database

In an administrative session:

~~~sql
CREATE ROLE cfg_student
LOGIN PASSWORD 'REPLACE_WITH_STRONG_LAB_SECRET';

CREATE DATABASE cfg_demo OWNER cfg_student;
~~~

`REPLACE_WITH_STRONG_LAB_SECRET` is only a placeholder; replace it with a strong environment-appropriate password. `CREATE DATABASE` must run outside a transaction block and may be rejected if the account lacks `CREATEDB` or equivalent administrative privileges.

If the role or database already exists, do not overwrite without verifying its state. This walkthrough assumes `cfg_student` and `cfg_demo` are not yet in use.

### Step 2. Set a Value at the Database Level

~~~sql
ALTER DATABASE cfg_demo
SET work_mem = '8MB';
~~~

Open a **new connection** as `cfg_student` to `cfg_demo`:

~~~bash
psql -h 127.0.0.1 -p 5432 -U cfg_student -d cfg_demo
~~~

In the newly opened session:

~~~sql
SHOW work_mem;
-- Expected 8MB if no other overrides exist.
~~~

Close this connection before the next step:

~~~text
\q
~~~

### Step 3. Set a Value at the Role Level

In the administrative session:

~~~sql
ALTER ROLE cfg_student
SET work_mem = '16MB';
~~~

Open `psql` again as `cfg_student` to `cfg_demo`:

~~~sql
SHOW work_mem;
-- Expected 16MB: role overrides database.
~~~

Because the role level sets `16MB`, the database's `8MB` setting is not deleted, yet it no longer determines the outcome for sessions logged in as this role.

Close the test session before the next step.

### Step 4. Set a Value Specifically for the Role–Database Pair

In the administrative session:

~~~sql
ALTER ROLE cfg_student
IN DATABASE cfg_demo
SET work_mem = '24MB';
~~~

Open a **new** connection to `cfg_demo` as `cfg_student`:

~~~sql
SHOW work_mem;
-- Expected 24MB: role-database pair has highest precedence
-- among the database/role/role-database levels.
~~~

If the same role logs into a different database without a pair-specific override, the `24MB` setting **does not automatically apply** to that other database; the role value `16MB` is used instead.

### Step 5. Temporarily Override Within the Session

Inside the newly opened `cfg_student` connection:

~~~sql
SET work_mem = '32MB';
SHOW work_mem;
-- 32MB

RESET work_mem;
SHOW work_mem;
-- Reverts to 24MB from the role-database pair in this example.
~~~

`RESET` does not erase settings configured by the administrator. It simply returns the session value to its corresponding current default.

### Step 6. Override Within a Transaction

~~~sql
SHOW work_mem;
-- 24MB

BEGIN;
SET LOCAL work_mem = '48MB';
SHOW work_mem;
-- 48MB

COMMIT;

SHOW work_mem;
-- 24MB
~~~

Or test rollback:

~~~sql
BEGIN;
SET work_mem = '32MB';
SHOW work_mem;
-- 32MB

ROLLBACK;
SHOW work_mem;
-- 24MB because SET occurred inside a rolled-back transaction.
~~~

This sequence clearly illustrates the boundary between **login defaults**, **session overrides**, and **transaction-only overrides**.

### Step 7. Remove Each Layer and Watch Where the Value Falls Back

Close the current `cfg_student` session. In the administrative session:

~~~sql
-- Remove the most specific configuration:
ALTER ROLE cfg_student
IN DATABASE cfg_demo
RESET work_mem;
~~~

A new connection as `cfg_student` to `cfg_demo` will now see `16MB` from the role.

Continue:

~~~sql
ALTER ROLE cfg_student
RESET work_mem;
~~~

A new connection will now see `8MB` from the database.

Finally:

~~~sql
ALTER DATABASE cfg_demo
RESET work_mem;
~~~

A new connection no longer has any of these three overrides and takes the appropriate value from server configuration or other connection sources. **Do not assume it will definitely be `4MB`** if the actual server has custom settings or the client passes `PGOPTIONS`.

**Important for the entire experiment:** after every `ALTER DATABASE` or `ALTER ROLE` command, you must open a **new connection** to evaluate the result. Do not rely on `SHOW work_mem` in a connection opened prior to the change to conclude that the administrative command had no effect.

### Step 8. Clean Up the Practice Environment When Finished

Ensure all connections to `cfg_demo` are closed. In the administrative session:

~~~sql
DROP DATABASE cfg_demo;
DROP ROLE cfg_student;
~~~

`DROP DATABASE` cannot run inside a transaction block and will fail if connections to the target database remain open under applicable rules. **Do not use `WITH (FORCE)` or arbitrarily terminate connections** just to finish a lab exercise, as this can impact other users working with the database.

Only drop these two objects if you are certain they were created **exclusively for the lab** and contain no data worth keeping.

## 11. Tracing Effective Values with SHOW, current_setting, and pg_settings

When an application reports using a value different from expected, first inspect **inside the application's own session** or in a connection sharing the exact same user, database, and startup options.

### 11.1. SHOW and current_setting

~~~sql
SHOW work_mem;
SHOW statement_timeout;
SHOW search_path;

SELECT
    current_setting('work_mem') AS work_mem,
    current_setting('statement_timeout') AS statement_timeout;
~~~

`SHOW` and `current_setting` tell you the **effective value in the session**. By themselves, they do not tell you whether the parameter came from the server, database, role, or `SET`.

### 11.2. pg_settings Reveals Source and Context

~~~sql
SELECT
    name,
    setting,
    unit,
    source,
    context,
    sourcefile,
    sourceline,
    pending_restart
FROM pg_settings
WHERE name IN (
    'work_mem',
    'statement_timeout',
    'shared_buffers',
    'max_connections'
)
ORDER BY name;
~~~

Key columns:

| Column | How to Interpret |
| --- | --- |
| `name` | Parameter name |
| `setting` | Value as represented by PostgreSQL in the view |
| `unit` | Unit associated with the value, if any |
| `source` | Source from which the current value was selected |
| `context` | Scope/authority level needed to change the parameter |
| `sourcefile`, `sourceline` | Relevant file and line when the source is a configuration file and viewing privileges allow |
| `pending_restart` | Indicates whether a new setting is waiting for a restart to take effect |

`pg_settings` reflects values **in the querying session**, not a single summary table for all users. If you are connected as an admin account in database `postgres`, `work_mem` may differ completely from `cfg_student`'s session in `cfg_demo`.

Sources may be reported as configuration file, database, user/role, database–user combination, client, or session setting. Exact labels depend on the version and source used. Never look only at a single `source` value while ignoring `context`, restart status, and the actual connection.

**File viewing privileges:** `sourcefile` and `sourceline` can be `NULL` if no file source applies or the account lacks privileges to view configuration details. Do not infer "the file does not exist" merely from `NULL`.

### 11.3. Parameter Settings Can Use Specific Units

`SHOW work_mem` may display `'24MB'`, while `pg_settings.setting` and `pg_settings.unit` represent the data differently, such as a numeric value in `kB`.

If you need to convert to MB or compare numbers programmatically, read **both `setting` and `unit`**, rather than assuming all parameters share the same unit or are already in bytes.

## 12. Viewing Default Values Assigned to Roles and Databases

Current values in a single session do not show the full picture of defaults saved for **other roles and databases**. For administrators, PostgreSQL stores this metadata in the `pg_db_role_setting` catalog.

Example:

~~~sql
SELECT
    s.setdatabase,
    d.datname,
    s.setrole,
    r.rolname,
    s.setconfig
FROM pg_db_role_setting AS s
LEFT JOIN pg_database AS d
    ON d.oid = s.setdatabase
LEFT JOIN pg_roles AS r
    ON r.oid = s.setrole
ORDER BY d.datname NULLS FIRST, r.rolname NULLS FIRST;
~~~

Common interpretations:

- `setdatabase = 0`: setting is not restricted to a specific database.
- `setrole = 0`: setting is not restricted to a specific role.
- Both hold specific OIDs: setting tailored specifically for that **role–database pair**.
- `setconfig` contains the list of parameter/value pairs saved for that scope.

Depending on metadata access privileges and version, non-administrative accounts may not be able to view all required details. Moreover, this catalog contains **stored overrides**, not the final effective value of an open connection after `PGOPTIONS` or `SET`.

Therefore, when investigating, combine:

1. `pg_db_role_setting` to see saved database/role settings.
2. `pg_settings` in the target session to see the actual value and source.
3. Server configuration, logs, and startup options to determine the rest.

## 13. Not Every Parameter Can Be Changed at the Same Level

Precedence rules only matter when a parameter is **permitted to be adjusted at that source**.

PostgreSQL distinguishes GUC `context` values. Common groups:

| `context` | Practical Meaning |
| --- | --- |
| `internal` | Determined internally by PostgreSQL; users cannot modify freely |
| `postmaster` | Must be set at server startup; changes typically require a restart |
| `sighup` | Can take effect after the server reloads configuration |
| `backend` | Determined when the backend/session starts within allowed scopes |
| `superuser-backend` | Similar to `backend`, with stricter privilege limits |
| `superuser` | Requires elevated privileges or explicit `SET` privilege granted appropriately, depending on version |
| `user` | Regular users can adjust in a session or permitted source |

For example:

~~~sql
SELECT
    name,
    context,
    setting,
    source,
    pending_restart
FROM pg_settings
WHERE name IN (
    'work_mem',
    'statement_timeout',
    'shared_buffers',
    'max_connections',
    'log_min_duration_statement'
)
ORDER BY name;
~~~

Examples:

- `work_mem` typically has `context = 'user'`: can be set via `SET` if valid.
- `shared_buffers` typically has `context = 'postmaster'`: changing it requires restarting PostgreSQL.
- `max_connections` is also a startup parameter and cannot be changed for one session via `SET`.
- Some parameters for logging or security can only be changed by highly privileged users.

Do not reason that "session has the highest precedence, so `SET shared_buffers = ...` will beat the server configuration." PostgreSQL will reject the invalid operation.

### Reload vs. Restart

~~~text
Edit reloadable parameter
          |
          v
postgresql.conf / ALTER SYSTEM
          |
          v
pg_reload_conf() or reload signal
          |
          v
Takes effect at the appropriate point

Edit postmaster parameter
          |
          v
postgresql.conf / ALTER SYSTEM
          |
          v
Not yet in effect; pending_restart
          |
          v
Restart instance per operational procedures
~~~

Reloading or restarting must be done in a controlled manner, especially on production servers. An invalid value can prevent PostgreSQL from starting or impact application workloads.

## 14. Common Conflict Scenarios

### Scenario A: "Edited postgresql.conf, Yet SHOW Still Returns the Old Value"

Possible causes:

1. Not reloaded yet, or the parameter requires a restart.
2. `postgresql.auto.conf` or server command-line options override the file.
3. A database, role, or role–database pair has an override.
4. The session ran `SET` or the client sent startup options.
5. You are connected to a **different instance** or a pooler reusing a backend.

How to diagnose:

~~~sql
SHOW config_file;
SELECT name, setting, source, context, pending_restart
FROM pg_settings
WHERE name = 'work_mem';
~~~

Then test a new connection with the exact role/database and inspect database/role-level metadata.

### Scenario B: "Ran ALTER ROLE SET, Yet the Application Hasn't Changed"

`ALTER ROLE ... SET` normally loads only on **new logins**. Applications using a connection pool may continue reusing previously established physical connections.

The fix is not to immediately alter `max_connections` or restart the entire server. First:

- Verify the actual login role (`session_user`).
- Open a separate new connection to confirm the value.
- If the application uses a pool, plan a safe connection refresh within pool capabilities and SLA.
- Check whether the application runs `SET` or passes overriding startup options.

### Scenario C: "Account Belongs to an Admin Role, Yet Doesn't Receive That Role's work_mem"

`ALTER ROLE role_x SET ...` does not apply automatically via role membership. It applies when a session **logs in as `role_x`** per PostgreSQL rules. Running `SET ROLE role_x` inside an existing session does not re-apply login configuration settings of that role.

If you want defaults for a group of accounts, you may need to configure each login role directly or adjust administrative design—do not assume membership inherits all session variables.

### Scenario D: "Ran SET LOCAL, Yet Queries After COMMIT Lost the Value"

This is expected behavior: `SET LOCAL` exists only within the transaction scope. If you need it for the entire session, use `SET`; if you need it for every login by a role/database, use `ALTER ROLE` / `ALTER DATABASE`.

### Scenario E: "Ran RESET work_mem, Yet It Didn't Revert to 4MB"

`RESET` restores the session's effective default, which may be `24MB` from a role–database pair. To remove the value at that layer, an administrator must run `ALTER ROLE ... IN DATABASE ... RESET`, not just `RESET` in one connection.

### Scenario F: "Set statement_timeout for Reporting, Yet Other Applications Were Affected"

If `statement_timeout` is set at the server level, multiple workloads are affected unless overridden. If only reporting needs a different timeout, set it per database/role or specific transaction, while ensuring applications do not share broad roles and session state does not leak between pooled requests.

## 15. Applying in Production: Connection Pools and Session Management

In a Java application using JDBC/HikariCP, each physical connection to PostgreSQL has a **session** with its own configuration state.

Example workflow:

~~~text
Application borrows connection from pool
        |
        v
Connection already logged into PostgreSQL
        |
        +-- Server/database/role defaults loaded at connection creation
        |
        +-- Request A: SET search_path = tenant_a
        |              SELECT ...
        |              Returns connection to pool
        |
        +-- Request B borrows the same connection
                       May still have search_path from A
                       if pool/app fails to reset properly
~~~

This creates a risk of **session state leakage** across requests (not a bypass of PostgreSQL access controls, yet still dangerous). Even so, it can cause queries to hit the wrong schema, use unintended timeouts, or produce incorrect business behavior.

### Suitable Option for Short-Lived Changes

If only one transaction needs a setting:

~~~sql
BEGIN;
SET LOCAL statement_timeout = '5s';

-- Business SQL query.
SELECT 1;

COMMIT;
~~~

Because `SET LOCAL` automatically expires when the transaction ends, it is often easier to control than a session-wide `SET`. Still, the application must **commit or roll back** properly, and the pool must ensure connections are not returned while a transaction remains open.

### Note on PgBouncer Transaction Pooling

With PgBouncer in **transaction pooling** mode, a client connection does not necessarily use the same PostgreSQL backend across multiple transactions. Therefore:

- Do not assume a session-level `SET` in one transaction remains active in the next transaction.
- Specialized parameters should come from role/database design at backend connection initialization, or use `SET LOCAL` within a transaction under specific conditions.
- Understand how the pooler handles startup parameters, reset queries, and backend sessions before relying on session-level settings.

Do not compare `SHOW` results through a pooler with a direct connection without confirming pooling mode and using the same role/database.

## 16. Administrative Privileges When Changing Configuration

Not every application account has permission to modify every level:

| Operation | Privileges to Consider |
| --- | --- |
| `SET work_mem` | Can be executed for parameters users are permitted to change |
| `SET log_min_duration_statement` | May require elevated privileges or specifically granted `SET` privilege |
| `ALTER DATABASE ... SET` | Requires administrative/ownership privileges and permission to alter the parameter |
| `ALTER ROLE ... SET` | Requires role administration privileges per PostgreSQL rules and permission for the parameter |
| `ALTER SYSTEM SET` | Instance-wide configuration action requiring appropriate high administrative privileges |
| Editing `postgresql.conf`, restarting server | Requires operational access on host/container/managed service |

Exact privileges vary by version and parameter; for instance, PostgreSQL supports granting `SET` privilege on specific parameters. **Do not grant superuser to an application just so it can change `statement_timeout`.** Use an appropriate configuration scope or have an administrator set role/database defaults.

### Security-Sensitive Settings Must Also Be Controlled

`search_path` affects how PostgreSQL resolves unqualified object names and can therefore impact the safety of applications or `SECURITY DEFINER` functions if designed carelessly. For security-critical SQL, use explicit schema names or configure a safe `search_path` by design.

Similarly, overly generous timeouts or excessively high per-role `work_mem` can create resource risks. Users permitted to adjust parameters must still follow proper configuration governance.

## 17. Practice Exercises

These exercises assume `work_mem` is permitted to be changed at all stated levels, the roles/databases already exist, and there are no startup options or session overrides other than those described in each question.

**Exercise 1.** The server default is `work_mem = 4MB`. Database `shopdb` sets `8MB`, and role `app_user` sets `16MB`. When `app_user` opens a new connection to `shopdb`, what value applies?

**Exercise 2.** Keeping Exercise 1's settings, add `ALTER ROLE app_user IN DATABASE shopdb SET work_mem='24MB'`. In a new connection with that role and database, which value wins? If `app_user` connects to `otherdb` which has no specific override, what value is expected?

**Exercise 3.** After connecting and receiving `24MB` from the role–database pair, run `SET work_mem='32MB'` followed by `RESET work_mem`. What will the value be after `RESET`? Why does it not return to `4MB`?

**Exercise 4.** In a session currently having `work_mem = 24MB`, run:

~~~sql
BEGIN;
SET LOCAL work_mem = '48MB';
SHOW work_mem;
COMMIT;
SHOW work_mem;
~~~

What values do the two `SHOW` statements return?

**Exercise 5.** In a session currently having `work_mem = 24MB`, run:

~~~sql
BEGIN;
SET work_mem = '32MB';
ROLLBACK;
SHOW work_mem;
~~~

What is the value after `ROLLBACK`?

**Exercise 6.** An administrator ran `ALTER ROLE analyst SET statement_timeout='90s'`, yet a connection opened yesterday still shows `30s`. Name two things to check before concluding the `ALTER ROLE` command failed.

**Exercise 7.** A user is a member of role `report_reader`. The administrator sets `ALTER ROLE report_reader SET work_mem='64MB'`. Does the user automatically receive `64MB` when logging in with their own account?

**Exercise 8.** Write a query to retrieve `name`, `setting`, `source`, `context`, and `pending_restart` for `shared_buffers` and `work_mem`. Between the two, which typically requires a restart to change?

**Exercise 9.** An application uses a connection pool, runs `SET search_path = tenant_a`, and returns the connection to the pool. Another request receives that same connection and expects `tenant_b`. What problem can occur? How should this be designed?

**Exercise 10.** Distinguish these three operations:

~~~sql
RESET statement_timeout;

ALTER ROLE report_reader RESET statement_timeout;

ALTER ROLE report_reader
IN DATABASE reportdb
RESET statement_timeout;
~~~

Which scope does each command affect?

### Answer Hints

| Exercise | Core Answer |
| --- | --- |
| 1 | `16MB`, because role settings take precedence over database settings |
| 2 | `24MB` for `app_user@shopdb`; `16MB` when connecting to `otherdb` if no other overrides exist |
| 3 | `24MB`, because `RESET` restores the session default inherited from the role–database pair |
| 4 | `48MB` inside the transaction, `24MB` after `COMMIT` |
| 5 | `24MB`, because `SET` inside the transaction was rolled back |
| 6 | Open a new connection with the exact login role; inspect `pg_settings.source`, role–database pair overrides, `PGOPTIONS`, or `SET` |
| 7 | No; GUC defaults from `ALTER ROLE` are not inherited via role membership or `SET ROLE` |
| 8 | `shared_buffers` typically requires a restart; `work_mem` can be changed in a session |
| 9 | The session may retain `search_path` from request A; reset state when returning to the pool, set the value per request, or use transaction scope appropriately |
| 10 | Respectively: resets in the current session; removes the role's default; removes the role–database pair's default |

Example solution for **Exercise 8**:

~~~sql
SELECT
    name,
    setting,
    source,
    context,
    pending_restart
FROM pg_settings
WHERE name IN ('shared_buffers', 'work_mem')
ORDER BY name;
~~~

## 18. Quick Reference Table

| Goal | Which Approach? | Key Reminder |
| --- | --- | --- |
| Server-wide default | `postgresql.conf` or `ALTER SYSTEM` | May require reload or restart |
| Default when connecting to a DB | `ALTER DATABASE db SET param = value` | Applies to new connections |
| Default when logging in as a role | `ALTER ROLE role SET param = value` | Takes precedence over database alone |
| Default for a role–DB pair | `ALTER ROLE role IN DATABASE db SET ...` | More specific than role or database individually |
| Override at connection open | Startup/client options, e.g., `PGOPTIONS` | Only for permitted parameters |
| Change in running session | `SET param = value` | Persists until reset/session end, subject to transaction rules |
| Change only in transaction | `SET LOCAL param = value` | Automatically expires after transaction |
| View effective value | `SHOW param` or `current_setting()` | Read inside the target session |
| View source and context | `pg_settings` | Check `source`, `context`, `pending_restart` |
| View saved role/DB overrides | `pg_db_role_setting` | Does not replace checking actual session state |

**Takeaway:** For parameters configurable at each respective level, **server → database → role → role–database pair → connection options → session → transaction-local** is the practical precedence order. However, "higher precedence" never bypasses **parameter modification privileges**, **`context` requiring reload/restart**, or **session lifecycle**. When a value looks unexpected, inspect it using `SHOW` and `pg_settings` inside the very connection under investigation, then trace the configuration source from most specific back to general defaults.
