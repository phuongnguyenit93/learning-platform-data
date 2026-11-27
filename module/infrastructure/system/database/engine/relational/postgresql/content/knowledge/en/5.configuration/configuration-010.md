# Checking Configuration Errors and Safe Changes with Rollback Plans in PostgreSQL

## 1. Why Do Configuration Changes Need a Dedicated Workflow?

A PostgreSQL server may be serving multiple systems simultaneously: transactional APIs, background jobs, reporting, administrative connections, and replication. Changing a parameter like `work_mem` can alter memory consumption across many queries; changing `max_connections` changes resource budgets after a restart; editing `pg_hba.conf` can lock out applications or administrators from **logging in altogether**.

Many incidents stem from seemingly small actions:

- Editing a valid-looking file, yet **that file is not the config file the server actually uses**.
- Putting a new value in `postgresql.conf`, only to have `postgresql.auto.conf` or another source override it.
- Calling `pg_reload_conf()`, seeing `true`, and assuming every change took effect.
- Changing a **restart-required** parameter yet only reloading.
- Changing connection rules in `pg_hba.conf` and losing the administrative login path.
- Applying syntactically valid settings that trigger **high load, out-of-memory conditions, query timeouts, or application slowdowns**.
- Having a backup file without knowing **how to revert**, who decides to roll back, or how to verify the system returned to a safe state.

This lesson presents an end-to-end workflow:

1. **Identify the effective configuration and its origin.**
2. **Detect syntax errors, invalid values, and scope mismatches.**
3. **Assess impact and prepare before making changes.**
4. **Deploy the smallest possible change with verification.**
5. **Monitor for anomalies and revert if predefined thresholds are crossed.**
6. **Document outcomes and preserve recoverability for future changes.**

Examples target modern PostgreSQL and common Linux environments. Paths, services, permissions, and restart orchestration vary across direct installs, containers, Kubernetes, and managed PostgreSQL services. **Never run process-management commands verbatim** unless they match your real system.

> **Core principle:** configuration-change examples should only run in an **authorized lab or staging environment**. In production, require a runbook/approval, a maintenance window where needed, fallback access, and a rollback plan before hitting Reload or Restart.

## 2. Distinguishing "Value in a File" from "Effective Value"

PostgreSQL has multiple configuration layers. The same parameter name can appear in more than one place:

~~~text
PostgreSQL startup
  ├── Server command-line arguments
  ├── postgresql.conf
  │     ├── include '...'
  │     ├── include_if_exists '...'
  │     └── include_dir '...'
  └── postgresql.auto.conf (typically written by ALTER SYSTEM)
             |
             v
    Server-level applied configuration values
             |
             +--- ALTER DATABASE ... SET
             +--- ALTER ROLE ... SET
             +--- ALTER ROLE ... IN DATABASE ... SET
             +--- startup options / connection settings
             +--- SET / SET LOCAL in session (if parameter permits)
             |
             v
    Effective value in the observed session
~~~

This diagram classifies **sources**, not a rigid precedence table valid for every single parameter. Actual precedence depends on the **parameter's context**, override levels, and PostgreSQL rules.

### 2.1. Common Configuration Sources

| Source | Scope | When Is It Relevant? |
|---|---|---|
| `postgresql.conf` | Server config | Baseline settings for the PostgreSQL cluster |
| `include` / `include_dir` | Included configuration files | Organizing configuration by topic or environment |
| `postgresql.auto.conf` | Server-level overrides managed by `ALTER SYSTEM` | When settings were configured via SQL `ALTER SYSTEM` |
| Server command line | Parameter-dependent, can have high precedence | When service/container launches `postgres` with `-c` options |
| `ALTER DATABASE ... SET` | Default for new connections to a database | When each database needs distinct session defaults |
| `ALTER ROLE ... SET` | Default for new connections by a role | When an application/user has specific needs |
| `ALTER ROLE ... IN DATABASE ... SET` | Value for a role + database pair | When scoping must be exact |
| Startup options | New session | Client/driver passes options at login |
| `SET` / `SET LOCAL` | Session or transaction, for permitted GUCs | When a temporary, narrow-scoped change is needed |

Role/database-level changes generally apply when **new sessions start**; they do not automatically update previously opened connections. By contrast, some parameters reload via SIGHUP across existing backend processes.

### 2.2. Not Every Parameter Permits SET

PostgreSQL classifies parameters by `context`. For example, `max_connections` cannot be raised inside a session with `SET max_connections = 200`: it requires a server restart. A parameter such as `statement_timeout` can be adjusted in a session when the user holds appropriate privileges.

Therefore, verify **which levels allow changing a parameter**, rather than guessing from its name or reading only a file.

### 2.3. Confusing Override Scenario

Suppose `postgresql.conf` says:

~~~conf
work_mem = '8MB'
~~~

yet someone previously ran:

~~~sql
ALTER SYSTEM SET work_mem = '16MB';
~~~

After a reload, assuming no other overrides exist, the server default comes from `postgresql.auto.conf` and becomes **16MB**, not 8MB.

If an application session then runs:

~~~sql
SET work_mem = '32MB';
~~~

then `SHOW work_mem` inside that session returns 32MB. That is why investigations must record **the effective value, configuration source, and session scope**, rather than just grepping one file.

## 3. Quick Server and Config Path Checks

### 3.1. Verify Connection to the Right Host

Before taking action:

~~~sql
SELECT
    current_database() AS database_name,
    current_user AS effective_role,
    session_user AS login_role,
    inet_server_addr() AS server_ip,
    inet_server_port() AS server_port,
    version() AS postgres_version;
~~~

Unix-domain socket connections may cause `inet_server_addr()` or port to return `NULL`. That is not an error; verify the connection type and actual endpoint.

If applications connect through proxies, DNS, connection poolers, or failover endpoints, confirm the **actual target server** using operational metadata rather than relying on matching database names between staging and production.

### 3.2. Locate the Config Files the Server Actually Uses

With appropriate privileges:

~~~sql
SHOW config_file;
SHOW hba_file;
SHOW ident_file;
SHOW data_directory;
~~~

Meaning:

- `config_file`: main configuration file.
- `hba_file`: client authentication control file.
- `ident_file`: identity mapping file used by applicable authentication methods.
- `data_directory`: PostgreSQL data directory.

Paths may differ from defaults; containers and managed services often place files outside the data directory. Certain parameters and paths are restricted by privilege. If permission is denied, ask an authorized operator to provide the details—**never elevate an account to superuser just to view paths**.

### 3.3. Timestamp of Last Configuration Load

~~~sql
SELECT
    pg_postmaster_start_time() AS server_started_at,
    pg_conf_load_time() AS configuration_last_loaded_at;
~~~

`pg_postmaster_start_time()` tells you whether the server restarted. `pg_conf_load_time()` reflects when configuration was last loaded per PostgreSQL rules; results can reflect when the session's backend processed a reload.

**A recent load timestamp does not prove every new config line is valid or active.** Cross-check parameter states, parse errors, and logs.

## 4. Exploring pg_settings: Source of Truth for the Current Session

`pg_settings` is the most important system view when inspecting operational parameters.

### 4.1. Querying Parameter State

~~~sql
SELECT
    name,
    setting,
    unit,
    context,
    vartype,
    source,
    sourcefile,
    sourceline,
    pending_restart
FROM pg_settings
WHERE name IN (
    'work_mem',
    'shared_buffers',
    'max_connections',
    'statement_timeout',
    'log_min_duration_statement',
    'listen_addresses'
)
ORDER BY name;
~~~

Fields to understand:

| Field | Meaning |
|---|---|
| `name` | Parameter name |
| `setting` | Effective value in internal/text form |
| `unit` | Metadata storage unit, e.g., `kB` or `8kB` |
| `context` | Context required for a change to take effect |
| `vartype` | Parameter type: bool, integer, real, string, enum |
| `source` | Source determining the effective value, such as default, configuration file, database/user, client, session |
| `sourcefile` / `sourceline` | Relevant file/line if sourced from a file and permitted to be displayed |
| `pending_restart` | Whether a restart-required change is waiting to take effect |

`sourcefile` and `sourceline` may return `NULL` either because the value did not come from a file **or** because your role lacks permissions to view paths. Never conclude "no config file exists" from a `NULL` cell alone.

### 4.2. Distinguishing setting and unit

Some GUCs store `setting` as `8192` while `unit` is `8kB` or `kB` depending on the parameter. To read human-friendly values, run:

~~~sql
SHOW work_mem;
SHOW shared_buffers;
SHOW statement_timeout;
~~~

Never assume `pg_settings.setting = 8192` always means 8192 **bytes**. Always inspect `unit` and the parameter's exact definition.

### 4.3. Viewing Descriptions and Bounds

~~~sql
SELECT
    name,
    short_desc,
    context,
    vartype,
    min_val,
    max_val,
    enumvals,
    boot_val,
    reset_val
FROM pg_settings
WHERE name IN (
    'work_mem',
    'max_connections',
    'wal_level'
)
ORDER BY name;
~~~

- `short_desc` states the basic purpose.
- `min_val` / `max_val` bound numeric values where applicable.
- `enumvals` lists allowed enum values.
- `boot_val` is the compiled-in default.
- `reset_val` is the value used when running `RESET` in the session, not a backup of the file before your edits.

**Never treat `reset_val` as guaranteed proof of "pre-change production value."** Proper rollback requires capturing a baseline before acting, including sources and files.

### 4.4. Comparing the Same Parameter Across Two Sessions

A DBA session and an application session may see different `SHOW statement_timeout` outputs due to `ALTER ROLE`, `ALTER DATABASE`, startup options, or `SET`. Never run SQL only in a superuser session and assume every application runs with the same value.

A reliable check must run **in the exact database, role, and connection mode** used by the application, or inspect configuration and live application session state directly.

## 5. Classifying Parameters by How Changes Apply

### 5.1. Context in pg_settings

| Common `context` | Operational Interpretation |
|---|---|
| `internal` | Internal value, cannot be changed via user configuration |
| `postmaster` | Requires **server restart** for changes to take effect |
| `sighup` | Configuration can be reloaded via SIGHUP/reload |
| `backend` | Setting affects backends when a **new session starts** |
| `superuser-backend` | Similar backend scope, with stricter privilege restrictions |
| `superuser` | Adjustable in session by appropriately privileged roles; file changes usually need reload |
| `user` | Adjustable in session by regular users within permitted scope |

A context name is not equivalent to **permission to edit any file**. A `context=user` parameter can still be constrained by setup, managed service policies, or organizational rules.

### 5.2. Typical Examples

| Parameter | Role | Application Notes |
|---|---|---|
| `max_connections` | Server-configured max connections | Usually `postmaster`: requires restart |
| `shared_buffers` | PostgreSQL shared memory buffer pool | `postmaster`: requires restart |
| `listen_addresses` | Network addresses the server listens on | `postmaster`: requires restart |
| `wal_level` | Level of WAL information | Usually requires restart and affects replication |
| `log_min_duration_statement` | Threshold for logging slow SQL | Reloadable at appropriate scope |
| `work_mem` | Memory budget for sort/hash operations per execution rules | Session-configurable where appropriate |
| `statement_timeout` | Statement execution time limit | Session-configurable where appropriate |
| `lock_timeout` | Max time waiting to acquire a lock | Session-configurable where appropriate |

Always **check `pg_settings.context` on your exact server version** instead of memorizing a fixed list; parameter names, privileges, and semantics can evolve across versions.

### 5.3. Reload Is Not Restart

- **Reload:** asks PostgreSQL to re-read applicable configuration files while the server keeps running. `postmaster` settings continue waiting for a restart.
- **Restart:** stops and starts the PostgreSQL process; interrupts connections, may trigger failover/recovery depending on topology, and requires application coordination.
- **New session:** role/database default changes or `backend`-context settings appear only when new connections are opened.
- **SET/SET LOCAL:** applies to one session or transaction; not proof that system-wide configuration changed.

Never treat restart as the default fix for every configuration issue: many changes apply safely via reload, whereas restarts cause major service disruption.

## 6. Detecting File Errors: pg_file_settings

PostgreSQL provides `pg_file_settings` to inspect parsed configuration entries from files within permitted privileges.

~~~sql
SELECT
    sourcefile,
    sourceline,
    seqno,
    name,
    setting,
    applied,
    error
FROM pg_file_settings
ORDER BY seqno;
~~~

This is useful when:

- Multiple `include` files interact in read order.
- A parameter appears repeatedly.
- A line has invalid syntax or an unacceptable value.
- You need to see which line was applied vs. overridden.

### 6.1. Finding Explicit Errors

~~~sql
SELECT
    sourcefile,
    sourceline,
    name,
    setting,
    error
FROM pg_file_settings
WHERE error IS NOT NULL
ORDER BY sourcefile, sourceline;
~~~

If errors appear, read the message, fix the right file, and **re-check**. Errors may involve syntax, unknown parameters, out-of-range values, unmet prerequisites, or invalid context.

**Never look at an empty error view and guarantee PostgreSQL will restart cleanly**: non-syntactic issues include hardware resources, filesystems, TLS certificates, file permissions, extensions, and topology constraints.

### 6.2. applied=false Is Not Always an Error

`pg_file_settings.applied = false` can appear when:

- An earlier entry was **overridden** by a higher-precedence or later entry.
- A change cannot apply right now (for example, it requires a restart).
- A specific entry or file error occurred.

Therefore, inspect **`error`**, the full sequence of entries for the same `name`, `pg_settings.source`, and `pending_restart` before jumping to conclusions.

~~~sql
SELECT
    sourcefile,
    sourceline,
    seqno,
    setting,
    applied,
    error
FROM pg_file_settings
WHERE name = 'work_mem'
ORDER BY seqno;
~~~

This example helps distinguish a setting in the main file that was overridden by another configuration file.

### 6.3. Access Privileges

Not every application role is allowed to inspect configuration file details via system views. If access is denied or columns are hidden, use **controlled config-reading roles** rather than granting superuser. Configs can contain internal paths and security-sensitive details.

## 7. Path Errors and Include Order

### 7.1. Configuration Directives

In `postgresql.conf`, you may encounter:

~~~conf
include = 'common.conf'
include_if_exists = 'site-override.conf'
include_dir = 'conf.d'
~~~

Important points:

- `include` requires the target file to exist and be valid per parser rules.
- `include_if_exists` skips missing files cleanly.
- `include_dir` loads eligible config files in the directory according to PostgreSQL's filename ordering; later values can override earlier ones.
- Relative paths resolve relative to the referencing configuration file—never guess relative to your terminal's working directory.
- `postgresql.auto.conf` is a separate source that normally takes precedence over entries in `postgresql.conf` under server config rules.

Example:

~~~text
postgresql.conf
   work_mem = '8MB'
   include_dir = 'conf.d'

conf.d/10-base.conf
   work_mem = '12MB'

conf.d/90-app.conf
   work_mem = '16MB'

postgresql.auto.conf
   work_mem = '24MB'
~~~

After loading, the server default may come from a later/higher override, **while individual sessions can still set another value**. Trace the origin with `pg_file_settings` and `pg_settings`, not by grepping only the first line.

### 7.2. Avoid Editing Files Generated by Management Tools

In managed services or automated deployments, files may be regenerated by Helm charts, operators, Ansible, Terraform, or control planes. Manual edits can be silently overwritten on the next rollout.

Identify the configuration's **source of truth**: Git repository, ConfigMap, managed service parameter group, cloud API, or local host files. Rollbacks must also flow **through that same management channel** to prevent config drift.

## 8. pg_hba.conf: Checking Authentication and Avoiding Lockout

`pg_hba.conf` defines allowed connections and authentication methods for PostgreSQL. HBA stands for **Host-Based Authentication**, though the file also governs local Unix socket rules.

An illustrative line:

~~~conf
# TYPE     DATABASE  USER           ADDRESS           METHOD
hostssl    shopdb    report_reader  192.0.2.0/24      scram-sha-256
~~~

Here:

- `hostssl` matches only SSL/TLS TCP connections if the server has SSL configured.
- `shopdb` restricts the database.
- `report_reader` restricts the role.
- `192.0.2.0/24` is a documentation-reserved example IP range, not a real production subnet.
- `scram-sha-256` specifies SCRAM password authentication.

`pg_hba.conf` **does not enable network listening on its own**: `listen_addresses`, firewalls, DNS, proxies, and server TLS must also be properly configured.

### 8.1. Rules Are Evaluated in Order

PostgreSQL applies the **first matching rule** in `pg_hba.conf` order for an incoming connection. There is no fallback mechanism that says "if the password fails on this rule, try a looser rule below."

Example:

~~~conf
# Tight rule for a specific source
hostssl shopdb report_reader 192.0.2.10/32 scram-sha-256

# Broader rule for the whole subnet
hostssl shopdb report_reader 192.0.2.0/24 scram-sha-256
~~~

The first line matches first when a connection arrives from `192.0.2.10`. Placing a `reject` rule or blocking policy ahead of required rules can cut off intended access.

**Never add an open-network rule** such as `0.0.0.0/0` with a weak authentication method to troubleshoot connection errors. That widens the attack surface and usually masks the real issue.

### 8.2. Inspecting HBA Files with pg_hba_file_rules

With appropriate privileges:

~~~sql
SELECT
    line_number,
    type,
    database,
    user_name,
    address,
    auth_method,
    error
FROM pg_hba_file_rules
ORDER BY line_number;
~~~

Rows where `error IS NOT NULL` show parser or syntax issues detected by PostgreSQL:

~~~sql
SELECT line_number, error
FROM pg_hba_file_rules
WHERE error IS NOT NULL
ORDER BY line_number;
~~~

**Limitations of this check:**

- The view reflects rules from **current file contents on disk**, not necessarily an immutable snapshot of active in-memory rules serving connections.
- Having no `error` **does not guarantee** users can log in. Host, database, role, password/certificate, SSL state, and rule order must all align.
- Rule edits govern **new connections**; already-open sessions are not automatically re-authenticated when HBA changes.
- Platforms and deployment setups differ on when file edits take effect; follow your environment's reload procedure.

### 8.3. Safe HBA Change Plan

Before changing:

1. Confirm an **independent fallback admin path** unaffected by the planned rule edit (e.g., verified local/tunnel/bastion access).
2. Back up the exact current `pg_hba.conf`, recording checksum/version.
3. Document all connections that must remain working: applications, batch jobs, replicas, monitoring, DBAs.
4. Keep an **active administrative session open** while testing; still never rely on it as your only recovery path.
5. Edit one clear, well-scoped rule group at a time.
6. Check `pg_hba_file_rules`, reload per runbook, and **test login with new connections** from real sources.
7. If it fails, **restore the old HBA file**, reload, re-test, and inspect logs.

When connecting from an application host through a proxy, the source IP seen by PostgreSQL may be the proxy/NAT address rather than the client host's IP. Verify empirically rather than guessing CIDRs from internal network diagrams.

## 9. pg_ident.conf and Identity Mapping Errors

`pg_ident.conf` maps OS or external authentication identities to PostgreSQL roles for methods such as `ident`/`peer` when configured with a `map`.

If HBA references a map while `pg_ident.conf` is missing or misconfigured, logins fail even when the target role exists.

Inspect when supported by version and privileges:

~~~sql
SELECT *
FROM pg_ident_file_mappings
WHERE error IS NOT NULL;
~~~

Or list current mapping rules:

~~~sql
SELECT
    line_number,
    map_name,
    sys_name,
    pg_username,
    error
FROM pg_ident_file_mappings
ORDER BY line_number;
~~~

When errors occur, check:

- Which mapping name the HBA rule references.
- Which external identity the authentication system supplies.
- Whether the mapping permits authenticating as the intended PostgreSQL role.
- Whether file syntax is valid.

Never switch authentication to `trust` just to bypass mapping errors. `trust` allows matching connections without password verification, which is dangerous wherever network access is not strictly isolated.

## 10. Finding Configuration Errors in Logs

System views inspect metadata; logs show what PostgreSQL **actually did during parsing, reload, and startup**.

### 10.1. Common Log Message Categories

Typical messages may include:

- `unrecognized configuration parameter`: parameter does not exist or is unsupported in that version.
- `invalid value for parameter`: value cannot be parsed, is out of bounds, or is an invalid enum value.
- `parameter ... cannot be changed without restarting the server`: requires restart.
- `could not open configuration file`: missing file, wrong path, or permission error.
- `could not load ... certificate/key`: TLS resource error when TLS is configured.
- `no pg_hba.conf entry for host ...`: no matching authentication rule for the connection.
- `password authentication failed for user ...`: authentication failed; distinguish from missing HBA rules.
- `FATAL: ...` at startup: configuration or environment prevents the server from starting.

Exact wording varies by version and scenario; always read **full log entries, timestamps, PIDs, hosts, and severity levels**.

### 10.2. Where Are Logs Located?

Depends on configuration and deployment:

- PostgreSQL logging collector.
- journald/systemd or process manager logs.
- Container stdout/stderr and log aggregators.
- Managed database provider log UIs or APIs.

Never assume `/var/log/postgresql/postgresql.log` always exists. Before hunting for logs, check how the instance is deployed and inspect logging parameters such as `logging_collector`, `log_destination`, and `log_directory` where authorized.

### 10.3. Avoid Exposing Secrets When Sharing Logs

Logs can contain SQL statements, usernames, IP addresses, database names, or data from error messages. When filing incident reports, share only what is needed and scrub passwords, tokens, and personal data per security policy.

## 11. Preparing a Safe Change Record

A well-run configuration change should have at least a minimal **change record**:

| Component | Example Content |
|---|---|
| Goal | Reduce report runtime or increase visibility into slow queries |
| Scope | Which instance, primary or replica, which database/role |
| Current value | Effective value, source, file/line, `pending_restart` |
| Proposed value | `log_min_duration_statement = '750ms'` |
| Reason | Log queries over 750 ms for time-boxed diagnostics |
| Impact | Increased log volume; potential sensitive SQL literals in logs |
| Apply method | Reload / new session / restart |
| Verification | `SHOW`, `pg_settings`, logs, test query, metrics |
| Rollback trigger | Log spike, CPU/I/O or latency exceeding threshold |
| Rollback steps | Restore prior source, reload/restart, verify |
| Owners | Implementer and approver |
| Observation window | Agreed monitoring period in change plan |

If you do not yet know **the old value and effective source**, you are not ready to claim a change is "reversible."

### 11.1. Save a Baseline of Relevant Parameters

~~~sql
SELECT
    name,
    setting,
    unit,
    context,
    source,
    sourcefile,
    sourceline,
    pending_restart
FROM pg_settings
WHERE name IN (
    'log_min_duration_statement',
    'statement_timeout',
    'work_mem',
    'max_connections'
)
ORDER BY name;
~~~

Save the output appropriately along with the capture timestamp. If `sourcefile` is restricted, note the privilege limit and export configuration proof from your authoritative management system.

### 11.2. Back Up Modified Files

If self-managing the host:

- Back up the original file, permissions/ownership, and checksum before editing.
- Never copy secret-bearing files into public/shared directories.
- Use version control or reviewed configuration management tooling.
- Avoid two people editing the same file through different channels simultaneously.
- For `postgresql.auto.conf`, manage it via `ALTER SYSTEM` while the server is running; avoid ad-hoc manual edits.

On managed services, export a **snapshot of the parameter group or equivalent config resource**, since users rarely have OS file access.

### 11.3. Test First in a Comparable Environment

When staging is available:

1. Use a matching PostgreSQL version and extensions.
2. Reproduce representative data/workload if benchmarking is needed.
3. Use the exact same change mechanism: SQL, file, operator, or API.
4. Also perform a **dry-run rollback**.
5. Measure reload/restart duration and impact on connections and replication.
6. Compare metrics against baseline—not just whether the parameter value changed.

A syntactically valid configuration can still fail **on performance** under higher load; preflight testing must include an impact-measurement plan.

## 12. Testing Inside a Transaction: SET LOCAL

When testing the effect of `work_mem` on **a single analytical query**, `SET LOCAL` carries far lower risk than changing the entire server.

~~~sql
BEGIN;

SET LOCAL work_mem = '16MB';

SHOW work_mem;

EXPLAIN (ANALYZE, BUFFERS)
SELECT
    customer_id,
    COUNT(*) AS order_count
FROM lab_orders
GROUP BY customer_id
ORDER BY order_count DESC;

ROLLBACK;
~~~

This example assumes a `lab_orders` table exists in your lab database. You can substitute any valid `SELECT` query; never run `EXPLAIN ANALYZE` on heavy queries in production without approval.

`SET LOCAL` is transaction-scoped. After `COMMIT` or `ROLLBACK`, the local override does not remain on the session.

### 12.1. SET vs. SET LOCAL

~~~sql
-- Changes for the current session, if parameter and privileges permit.
SET statement_timeout = '5s';

SHOW statement_timeout;

-- Restores session value from defaults / session reset.
RESET statement_timeout;
~~~

`SET` typically persists until reset or session end (following transaction rules if `SET` ran inside a transaction). `SET LOCAL` lasts only for the open transaction. Never use `RESET` expecting to roll back a server-level change written to `postgresql.conf` or `postgresql.auto.conf`.

### 12.2. Why Are Session-Scoped Tests Safer?

- Small blast radius.
- No restart required.
- Ending the transaction removes the override.
- Validates hypotheses before promoting changes to server policy.

Still, if a test query consumes heavy resources, **`SET LOCAL` does not make a heavy query harmless**. Choose SQL and test environments responsibly.

## 13. Changing Defaults per Database or Role

When one application needs a custom timeout, you do not have to change defaults for every user in the instance.

### 13.1. At the Database Level

~~~sql
-- Run only on a lab database when authorized.
ALTER DATABASE shopdb
SET statement_timeout = '5s';
~~~

**Newly opened** sessions to `shopdb` receive this default unless overridden by higher-precedence settings. Existing open pooled connections do not automatically update immediately.

Rollback:

~~~sql
ALTER DATABASE shopdb
RESET statement_timeout;
~~~

`RESET` here **removes the database-level override**. It does not necessarily update already-open connections, nor does it force a fixed "PostgreSQL default" if another layer sets an override.

### 13.2. At the Role Level

~~~sql
ALTER ROLE report_reader
SET statement_timeout = '30s';
~~~

Rollback:

~~~sql
ALTER ROLE report_reader
RESET statement_timeout;
~~~

### 13.3. For a Specific Role + Database Combination

~~~sql
ALTER ROLE report_reader IN DATABASE shopdb
SET work_mem = '32MB';
~~~

Rollback:

~~~sql
ALTER ROLE report_reader IN DATABASE shopdb
RESET work_mem;
~~~

Requires privileges on the target role and database. These are **illustrative** statements—never run them if `shopdb` or `report_reader` are production objects outside your responsibility.

### 13.4. Connection Pools and Impact on New Sessions

Many applications use HikariCP, PgBouncer, or other poolers. Running `ALTER ROLE` / `ALTER DATABASE` does not guarantee **existing** physical connections update their defaults. Plan to:

- Open a **new** connection to verify.
- Recycle/rotate the connection pool gradually via application mechanisms if needed.
- Avoid killing all connections simultaneously under heavy load.
- Under transaction pooling, understand how the pooler manages session state and reset queries.
- Test using the **exact role and database** used by the application.

Never use `SHOW statement_timeout` from a DBA session as proof that the application picked up the new policy.

## 14. Changing Server Configuration with ALTER SYSTEM

`ALTER SYSTEM` is SQL for setting **server-level** configuration. PostgreSQL writes these settings to `postgresql.auto.conf`.

### 14.1. Lab Example: Enabling Slow Query Logging

Suppose you want to measure queries taking over 750 ms:

~~~sql
ALTER SYSTEM SET log_min_duration_statement = '750ms';

SELECT pg_reload_conf();
~~~

`ALTER SYSTEM` requires appropriate privileges, **cannot run inside a transaction block**, and has instance-wide scope. `SELECT pg_reload_conf()` asks the server to process a reload; returning `true` confirms the SIGHUP request was sent, **not that every configuration entry loaded without error**.

Verify:

~~~sql
SELECT
    name,
    setting,
    unit,
    source,
    sourcefile,
    sourceline,
    pending_restart
FROM pg_settings
WHERE name = 'log_min_duration_statement';

SHOW log_min_duration_statement;

SELECT
    sourcefile,
    sourceline,
    name,
    setting,
    applied,
    error
FROM pg_file_settings
WHERE name = 'log_min_duration_statement'
ORDER BY seqno;
~~~

A session-level override in the DBA session could make `SHOW` differ from the default new sessions receive. Test with a fresh connection having no personal `SET` when verifying.

### 14.2. Two Distinct Ways to Revert

**Case A — there was no prior ALTER SYSTEM override:** remove the new override to fall back to underlying sources:

~~~sql
ALTER SYSTEM RESET log_min_duration_statement;
SELECT pg_reload_conf();
~~~

**Case B — an older ALTER SYSTEM value existed beforehand:** if you changed `'1000ms'` to `'750ms'`, the exact rollback sets back the **previous value**:

~~~sql
ALTER SYSTEM SET log_min_duration_statement = '1000ms';
SELECT pg_reload_conf();
~~~

Using `RESET` in Case B removes the override completely, dropping configuration to a lower-precedence source **which may differ from 1000 ms**. That is why you cannot safely roll back without recording the initial baseline.

### 14.3. Avoiding Conflicts with Configuration Management

If automation generates `postgresql.conf` while a DBA overrides values via `ALTER SYSTEM`, subsequent deployments may display one value in the main file while runtime uses a different value from `postgresql.auto.conf`. Standardize on **one authoritative configuration channel**, or document override rules and drift-resolution procedures.

Never delete the entire `postgresql.auto.conf` file just because one parameter caused an error: the file may hold other intentional overrides.

## 15. Restart-Required Changes: Very Different Planning Than Reload

Parameters such as `max_connections`, `shared_buffers`, and `listen_addresses` require a restart.

Example **solely to illustrate restart requirements**—never run blindly on production:

~~~sql
-- Staging example with a planned restart:
ALTER SYSTEM SET max_connections = '250';

-- Reloading does not activate max_connections=250 immediately.
SELECT pg_reload_conf();

SELECT
    name,
    setting,
    pending_restart
FROM pg_settings
WHERE name = 'max_connections';
~~~

If the new value is valid yet requires a restart, `pending_restart = true` appears in the applicable context. `SHOW max_connections` continues reporting the value the running postmaster started with.

### 15.1. Why Are Restarts Riskier?

- Drops active application sessions.
- Aborts in-flight queries/transactions; applications must handle connection errors cleanly.
- Can trigger a thundering-herd reconnect surge across pools.
- Can trigger failover or replication lag in HA setups.
- Risks the server **failing to start** if settings are invalid or resources are insufficient.
- Changing `max_connections` or `shared_buffers` alters RAM and OS resource budgets.

Therefore, restarts require:

1. Confirming the exact instance and topology.
2. Checking capacity/resources, OS limits, replicas, and expected connection counts.
3. Scheduling a maintenance window or rolling/failover procedure.
4. Backing up configuration and verifying recovery access.
5. Testing the restart in staging with a comparable version and configuration.
6. Having operators watch logs, health checks, and connection state.
7. Defining a **cutoff deadline or abort criteria** triggering rollback.
8. Re-verifying applications and replication afterward.

### 15.2. Never Recommend One Universal Restart Command

Across environments, restarts happen via:

- `systemctl` and package-managed service units.
- `pg_ctl` with the exact data directory and OS user.
- Kubernetes operators or StatefulSets per HA policy.
- Managed PostgreSQL service APIs.
- Orchestration tooling for primary/standby clusters.

A command like `systemctl restart postgresql` **does not always target the intended cluster**; hosts running multiple versions/instances may use different unit names or affect multiple clusters. Only run the exact command specified in your environment's runbook.

### 15.3. Rolling Back a Restart-Required Parameter

If raising `max_connections` from 150 to 250 causes an incident after restart:

1. Confirm the original value and **original source** (e.g., auto.conf previously held 150).
2. Restore 150 through the exact same management channel.
3. Schedule **another restart** for it to take effect.
4. Verify `pg_settings`, actual connection counts, health checks, and metrics post-restart.

Reloading alone **is insufficient** to revert a `postmaster` change already applied via restart.

## 16. Pre-Reload Checks and Post-Reload Verification

A sample checklist for `sighup` parameter or `pg_hba.conf` changes:

### 16.1. Before Applying

- [ ] Verified target server, instance, environment, and authorized privileges.
- [ ] Saved baseline effective values, sources, and file/config backups.
- [ ] Classified parameter context via `pg_settings.context`.
- [ ] Checked `pg_file_settings` for any pre-existing errors.
- [ ] If editing HBA/ident, inspected `pg_hba_file_rules` / `pg_ident_file_mappings`.
- [ ] Verified fallback administrative access and reliable file backup.
- [ ] Defined success criteria and rollback thresholds.
- [ ] Notified application teams if timeout/logging/role behavior will change.

### 16.2. Reload Operation

With appropriate privileges:

~~~sql
SELECT pg_reload_conf();
~~~

Or invoke reload via the service manager/operator per runbook. Issuing a reload does not guarantee every backend instantly sees identical values if session-context or override layers exist.

### 16.3. After Applying

~~~sql
SELECT
    name,
    setting,
    unit,
    context,
    source,
    pending_restart
FROM pg_settings
WHERE name IN (
    'log_min_duration_statement',
    'statement_timeout',
    'max_connections'
);

SELECT
    sourcefile,
    sourceline,
    name,
    setting,
    applied,
    error
FROM pg_file_settings
WHERE error IS NOT NULL
ORDER BY sourcefile, sourceline;

SELECT pg_conf_load_time();
~~~

Next:

- Inspect logs for parse or reload errors.
- If HBA changed, open **new connections** from application/DBA paths and verify success.
- If role/database defaults changed, test with a **new session** using that exact user/database.
- If query parameters changed, run a representative query in staging and check latency/logs.
- If `pending_restart` is true, do not declare the change fully applied.
- Compare system metrics against baseline.

## 17. Monitoring Impact: Config Valid Yet Workload Suffers

### 17.1. Useful Metrics

| Category | Metric / Observation | Why Relevant? |
|---|---|---|
| Connections | Session counts, failed logins, pool acquisition timeouts | Auth changes, connection limits, timeouts |
| Performance | Query latency p50/p95/p99, throughput | Memory, planner, or limit changes |
| CPU / I/O | CPU usage, IOPS, disk read/write, temp files | Sorts/hashes, table scans, logging |
| Memory | RAM, swap, OOM killer, container memory | `work_mem` and total concurrency |
| Locks | Lock waits, deadlocks, long transactions | Timeout or load changes |
| WAL / Replication | WAL volume, replica lag, standby state | `wal_level` and HA-related logging/settings |
| Application | HTTP error rate, retries, connection resets | Client-side impact of DB changes |
| Logs | FATAL/ERROR counts, log volume | Increased logging or config errors |
| Security | Authentication failures, unexpected grants | HBA/role/SSL changes |

Never treat a single metric as complete proof. For instance, increasing `work_mem` may cut temp I/O for one query while pushing total memory over budget under concurrent load.

### 17.2. pg_stat_activity to Inspect Session State

~~~sql
SELECT
    pid,
    usename,
    datname,
    state,
    wait_event_type,
    wait_event,
    query_start,
    xact_start
FROM pg_stat_activity
WHERE datname = current_database()
ORDER BY xact_start NULLS LAST
LIMIT 30;
~~~

Permissions to view other users' session details may be restricted. Watch closely for long-lived `idle in transaction` sessions when adjusting timeouts or pool settings.

### 17.3. Checking Connection Counts

~~~sql
SELECT
    state,
    COUNT(*) AS sessions
FROM pg_stat_activity
GROUP BY state
ORDER BY sessions DESC;
~~~

This counts backend sessions visible under your permissions; it is **not equivalent** to running HTTP requests or threads waiting on a connection pool. Correlate with application/pool metrics.

### 17.4. Don't Turn Slow-Query Logs into Sensitive Data Leaks

Lowering `log_min_duration_statement` can produce substantial SQL logs, sometimes including sensitive literals. Agree on an active duration window, log access controls, and data security policies. **Rolling back due to log overload** may need to happen much faster than long-term query optimization.

## 18. Scenario A: Parameter "Doesn't Change" After Reload

**Symptom:** A DBA edits `postgresql.conf`:

~~~conf
work_mem = '16MB'
~~~

calls `pg_reload_conf()`, yet a new session still sees `32MB`.

### 18.1. Hypotheses

1. An override exists in `postgresql.auto.conf`.
2. An `include_dir` file sets another value.
3. Role/database/session defaults set a custom value.
4. The DBA edited **the wrong file instead of the active config file**.
5. The config line had an error and was not applied.
6. The check ran on **a different server or session**.
7. Server command-line/startup flags override it.

### 18.2. Verification Steps

~~~sql
SHOW config_file;

SELECT
    name, setting, unit, context,
    source, sourcefile, sourceline, pending_restart
FROM pg_settings
WHERE name = 'work_mem';

SELECT
    seqno, sourcefile, sourceline,
    setting, applied, error
FROM pg_file_settings
WHERE name = 'work_mem'
ORDER BY seqno;
~~~

Then connect with the intended role and database to compare, and inspect reload logs and actual files.

### 18.3. Reverting Cleanly

If the issue came from a new `ALTER SYSTEM` override, revert **that override**; if it came from a GitOps-managed file commit, revert that commit and let automation apply it. Never patch the same parameter across multiple layers trying to "force" a number, as that makes future changes hard to manage.

## 19. Scenario B: Editing pg_hba.conf Breaks Application Connections

**Symptom:** After updating HBA, existing connections continue working, while new connections fail with:

~~~text
FATAL: no pg_hba.conf entry for host ...
~~~

### 19.1. Explanation

HBA governs **new** connections. Existing open connections do not prove the new rules work. Causes may include:

- Source IP differs from expected (NAT/proxy).
- Wrong database or role in the rule.
- Missing rule for the actual TLS/non-TLS mode.
- An earlier `reject` or matching rule precedes it.
- The edited file was not reloaded or has a parse error.

### 19.2. Step-by-Step Recovery

1. Keep existing DBA access open and verify console/out-of-band access.
2. Check connection logs and `pg_hba_file_rules`.
3. Diff the edited file against the backup to inspect changed lines.
4. If error rates breach thresholds, **restore the pre-change HBA file** and reload appropriately.
5. Test **new connections** from apps, jobs, monitoring, and DBAs.
6. Once stable, diagnose the root cause and validate the fixed rule in staging before redeploying.

Never propose `trust` or wide-open CIDRs as a default fix. Access rules must preserve both reachability **and** security policy.

## 20. Scenario C: Restart Fails Due to Invalid Parameter

**Symptom:** After modifying `shared_buffers` or `max_connections`, PostgreSQL fails to start.

### 20.1. Actions to Take

1. Preserve startup logs intact and identify the **very first error**.
2. Verify the right service/cluster was actually targeted.
3. Compare the new config file or parameter group against the **baseline**.
4. If resource-related (RAM, shared memory, file descriptors, disk), do not treat it merely as syntax.
5. Restore the **last known good configuration** via the proper channel, while PostgreSQL is stopped if necessary.
6. Start the server per runbook, then verify health checks and applications.
7. Check HA/replica components, not just a single `psql` login.

### 20.2. When SQL Is Unavailable

If the server fails to start, you **cannot rely on `ALTER SYSTEM RESET` via SQL** because no PostgreSQL backend is accepting connections. Recovery must use host file/config management, container/operator tooling, or the managed service control plane.

`postgresql.auto.conf` may be involved if `ALTER SYSTEM` made the pre-restart change; never delete that file blindly. Back up and restore only the relevant setting per runbook, preserving file permissions/ownership and other intentional overrides.

### 20.3. Why Shouldn't You "Just Retry Restarting Several Times"?

Unplanned repeated restarts can:

- Extend outage duration.
- Trigger repeated failovers or fight orchestration controllers.
- Cause thundering-herd reconnection storms from applications.
- Clutter logs or mask system state during triage.

It is far better to stop, identify the first root error, and restore a **known-good configuration**.

## 21. Scenario D: Changing work_mem Causes RAM Spike and Temp I/O Issues

`work_mem` is often misunderstood as "total memory per connection." In reality, it is a per-operation budget for executor nodes such as sorts and hashes under specific rules; **one query can allocate multiple nodes**, many queries can run concurrently, and hash operations have their own multipliers.

Suppose 50 queries run concurrently, each using several sort/hash nodes. Raising `work_mem` from 4MB to 128MB globally can sharply escalate out-of-memory risk even if one isolated report speeds up.

### 21.1. A Safer Way to Test

1. Pick one slow query showing sort/hash spill evidence.
2. Use `SET LOCAL work_mem` in a lab/staging session.
3. Compare `EXPLAIN (ANALYZE, BUFFERS)` and temporary I/O.
4. Test under realistic concurrency.
5. If beneficial for a reporting group, consider a **role/database override** rather than raising it cluster-wide.
6. Define rollback thresholds on RAM/swap/OOM—not just query latency.

Lab example:

~~~sql
BEGIN;
SET LOCAL work_mem = '16MB';

EXPLAIN (ANALYZE, BUFFERS)
SELECT customer_id, COUNT(*)
FROM lab_orders
GROUP BY customer_id
ORDER BY COUNT(*) DESC;

ROLLBACK;
~~~

`lab_orders` is an illustrative table created by the learner in a lab environment. `EXPLAIN ANALYZE` **actually executes the `SELECT`**; on very large real datasets, it can still impose heavy load.

## 22. Scenario E: Timeout Change Causes Widespread Application Errors

Suppose `statement_timeout = '2s'` is set for all sessions. Afterward, reports taking 3–5 seconds start failing even though they previously succeeded.

### 22.1. Target the Right Layer

Distinct timeouts:

| Timeout | Typical Effect |
|---|---|
| `statement_timeout` | Limits statement execution duration on the server |
| `lock_timeout` | Limits time **waiting to acquire a lock** |
| `idle_in_transaction_session_timeout` | Limits idle time inside an open transaction |
| `idle_session_timeout` | Limits idle time outside transactions per policy |
| Connection pool timeout | How long callers wait to borrow a connection from the pool |
| HTTP / request timeout | How long client/gateway waits for a response |

Not every 2-second request error is a PostgreSQL `statement_timeout`. It could be pool acquisition, an HTTP deadline, a lock wait, or network latency.

### 22.2. Controlled Configuration Alternative

Instead of setting a short timeout instance-wide:

~~~sql
ALTER ROLE report_reader IN DATABASE shopdb
SET statement_timeout = '30s';
~~~

Then only **new sessions** matching that role and database inherit this default per precedence rules. This works much better when reporting uses a separate role from OLTP applications.

Revert:

~~~sql
ALTER ROLE report_reader IN DATABASE shopdb
RESET statement_timeout;
~~~

Then open an appropriate new session to verify the reset value—do not rely on a single `SHOW` in a previously opened connection.

## 23. Configuration in Clusters with Replication or HA

On a single PostgreSQL node, rollbacks already require care. In an HA cluster, complexity increases due to **primary, standbys, failover, synchronous/asynchronous replication**, and orchestration layers.

### 23.1. Questions Before Changing

- Must this parameter be configured **consistently across primary and standbys**?
- Does the change affect WAL, replication slots, timelines, or standby catch-up?
- Does restarting standbys first align with your rolling-change procedure?
- If the primary fails over right after the change, will the standby have the same configuration?
- Do clients use a static endpoint or dynamic discovery that switches primaries?
- Who orchestrates restarts/failovers? Could an operator overwrite manual config?

Replication parameters such as `wal_level`, `max_wal_senders`, and `max_replication_slots` directly govern cluster architecture; never tweak them casually following generic query-tuning guides.

### 23.2. Avoid Uncoordinated Manual Per-Node Edits

If the primary receives a config change that standbys lack because automation hasn't synced them, a failover exposes the discrepancy. Clarify the **source of truth**, rollout policy, and authorized failover testing. Never run `pg_ctl restart` directly on an operator-managed node when the operator controls lifecycle.

### 23.3. Checking Pre/Post Status

Helpful SQL queries depending on node role:

~~~sql
SELECT pg_is_in_recovery() AS is_standby;

SELECT
    application_name,
    state,
    sync_state,
    replay_lag
FROM pg_stat_replication;
~~~

On a primary, `pg_stat_replication` shows active replication connections within viewing permissions. On a standby, that view may have no primary-to-standby rows; use standby-appropriate views/functions instead. `replay_lag` can be `NULL` in certain states—never naively assume `NULL = 0 ms`.

A successful rollback in HA must verify **matching configuration across all relevant nodes** and healthy replication, not just `SHOW` in one session.

## 24. Decision Table: Reload, Reconnect, or Restart

| Change | Mechanism Typically Needed | How to Verify | How to Revert |
|---|---|---|---|
| `SET LOCAL work_mem` | Within transaction | `SHOW` in same transaction, measure query | `ROLLBACK` or end transaction |
| `SET statement_timeout` | Within session | `SHOW` in same session | `RESET` or end session |
| `ALTER ROLE ... SET` | New session | Reconnect as that exact role | `ALTER ROLE ... RESET` then new session |
| `ALTER DATABASE ... SET` | New session | Reconnect to that exact database | `ALTER DATABASE ... RESET` then new session |
| Edit `postgresql.conf` for `sighup` GUC | Reload | `pg_settings`, `pg_file_settings`, logs | Restore old file then reload |
| `ALTER SYSTEM SET` for reloadable GUC | Reload | `pg_settings` sourcefile/pending_restart, logs | Restore old override or `RESET` then reload |
| Edit `pg_hba.conf` | Reload per platform; test new login | `pg_hba_file_rules` and new login | Restore old HBA, reload, test login |
| `postmaster` GUC like `max_connections` | Restart | `pending_restart`, `SHOW` post-restart, health checks | Restore old value/source and restart again |
| Cloud/operator-managed parameters | Via control plane workflow | Provider config + SQL + health | Revert via the same control plane |

This table describes principles. **The instance's configuration source, parameter context, and management tooling** determine the exact procedure. There is no single universal "rollback" button for every change layer.

## 25. Workflow Diagram for Handling a Configuration Change

~~~mermaid
flowchart TD
    A["Configuration change requested"] --> B["Verify target instance, role, and scope"]
    B --> C["Record baseline values + sources + logs/metrics"]
    C --> D["Inspect context and check file errors"]
    D --> E{"Apply method confirmed?"}
    E -- "No" --> F["Research parameter, privilege needs, staging"]
    F --> D
    E -- "Yes" --> G["Back up old config and prepare rollback"]
    G --> H["Test in staging / canary where feasible"]
    H --> I["Apply change at smallest effective scope"]
    I --> J["Reload / reconnect / restart per context"]
    J --> K["Verify values + logs + connections + workload"]
    K --> L{"Success criteria met?"}
    L -- "Yes" --> M["Continue monitoring and record change log"]
    L -- "No" --> N["Roll back via matching source and mechanism"]
    N --> O["Re-verify operations and baseline"]
~~~

**Rollback must have its own verification.** An `ALTER SYSTEM RESET` completing without error does not prove the service returned to its old state: other sources, existing sessions, pending restarts, and downstream workload effects may remain.

## 26. Detailed Runbook Template for a Reloadable Change

Suppose staging is authorized to test **slow query logging**, and an operator wants to lower the logging threshold from an existing value to `750ms`.

### 26.1. Collect Baseline

~~~sql
SELECT
    current_database(),
    current_user,
    pg_postmaster_start_time(),
    pg_conf_load_time();

SELECT
    name, setting, unit, context,
    source, sourcefile, sourceline, pending_restart
FROM pg_settings
WHERE name = 'log_min_duration_statement';

SELECT
    seqno, sourcefile, sourceline,
    setting, applied, error
FROM pg_file_settings
WHERE name = 'log_min_duration_statement'
ORDER BY seqno;
~~~

Record results in the change record; specifically check whether an **existing override sits in auto.conf**. Back up the authoritative configuration record per infrastructure practice.

### 26.2. Define Change Criteria

Example acceptance criteria:

- The `750ms` setting loads with zero parser errors.
- Logs begin recording queries exceeding the threshold under representative traffic.
- No spike in system errors or log volume exceeding budget.
- Latency and CPU/I/O do not degrade past operations-defined thresholds.
- Administrative login path remains functional.

Specific thresholds must be defined by workload owners; this lesson does not assume **750ms** is optimal for every system.

### 26.3. Apply in Lab

~~~sql
ALTER SYSTEM SET log_min_duration_statement = '750ms';

SELECT pg_reload_conf();
~~~

Then:

~~~sql
SELECT
    name, setting, unit, source, pending_restart
FROM pg_settings
WHERE name = 'log_min_duration_statement';

SELECT sourcefile, sourceline, applied, error
FROM pg_file_settings
WHERE name = 'log_min_duration_statement'
ORDER BY seqno;
~~~

Record reload timestamp, inspect logs, and test a new session if needed. Never inject secrets or personal data into SQL queries just to trigger a logging threshold test.

### 26.4. Conditional Rollback

If **baseline had no override in auto.conf**:

~~~sql
ALTER SYSTEM RESET log_min_duration_statement;
SELECT pg_reload_conf();
~~~

If **baseline already had an override** (e.g., `'1500ms'`):

~~~sql
ALTER SYSTEM SET log_min_duration_statement = '1500ms';
SELECT pg_reload_conf();
~~~

These two branches are **alternatives based on baseline**, not commands to run sequentially. After rolling back, verify `SHOW`, `source`, logs, and live impact; session-level overrides may alter observations.

## 27. Practice Exercises

The exercises below build reasoning and diagnostic skills. Configuration-changing commands should run only on an authorized **PostgreSQL lab** or be answered in writing; never run unapproved changes on production.

### Exercise 1 — Distinguish Configuration Sources

`postgresql.conf` sets `work_mem = '8MB'`, yet `postgresql.auto.conf` sets `work_mem = '16MB'`. A new session as role `report_reader` sees `32MB`.

List at least three places to inspect and write an SQL query to find the effective `source`.

### Exercise 2 — Reload or Restart?

Given the parameter list:

~~~text
max_connections
shared_buffers
log_min_duration_statement
statement_timeout
listen_addresses
~~~

Classify which typically require a restart versus which can reload or apply per session, and write an SQL query to inspect their actual `context`.

### Exercise 3 — Detect File Errors

A DBA edits an included file and `pg_reload_conf()` returns `true`, yet the setting does not change. Use `pg_file_settings` and `pg_settings` to distinguish parse errors, overridden entries, and `pending_restart`.

### Exercise 4 — Roll Back ALTER SYSTEM to the Right Source

Originally `postgresql.auto.conf` had `log_min_duration_statement = '2000ms'`. After testing `500ms`, you want to restore the exact baseline. Is `ALTER SYSTEM RESET` always the right answer? Why or why not?

### Exercise 5 — HBA Error After Reload

Applications with existing connections continue working, yet new workers fail to log in. Outline steps to check `pg_hba.conf`, source IP, role, TLS, rule order, and new-connection testing; describe the rollback.

### Exercise 6 — Change Role Defaults

You want `statement_timeout = '10s'` for `report_reader` on `shopdb`, without affecting other roles. Write the SQL to set and reset it. Are connections opened prior to the change guaranteed to pick up the new value?

### Exercise 7 — work_mem and RAM

A report sorts large datasets; someone proposes raising `work_mem` server-wide from 4MB to 256MB. State three risks and a narrower-scoped testing plan.

### Exercise 8 — Failed Restart

After changing `max_connections`, PostgreSQL fails to start and `psql` cannot connect. How do you roll back without relying on `ALTER SYSTEM` over SQL?

### Exercise 9 — Reading pg_settings

Explain the meaning of:

~~~text
name = max_connections
setting = 100
context = postmaster
pending_restart = true
~~~

Can you conclude the server currently allows 250 connections because the file was updated to 250?

### Exercise 10 — Draft a Change Record

Draft a minimal change record for adjusting `log_min_duration_statement`, including goal, baseline, scope, apply method, verification, rollback thresholds, and owners.

### Exercise 11 — Check HBA Errors

Write SQL to list HBA rules with errors. Why can an application still fail to log in even when that query returns zero rows?

### Exercise 12 — Measure Real Impact

A new `statement_timeout` appears properly when the DBA runs `SHOW`. Yet the API still times out at 3 seconds. List the timeout layers and evidence needed to distinguish PostgreSQL, connection pool, and HTTP gateway.

## 28. Solution Hints

### Exercise 1

Inspect main/included files, `postgresql.auto.conf`, role/database defaults, startup options, and session `SET`. SQL:

~~~sql
SELECT
    name, setting, unit, source,
    sourcefile, sourceline, context
FROM pg_settings
WHERE name = 'work_mem';
~~~

Must run inside the reporting job's **actual session/role** to see the real effective source.

### Exercise 2

`max_connections`, `shared_buffers`, and `listen_addresses` typically require a restart. `log_min_duration_statement` can apply via reload or session depending on privileges/context. `statement_timeout` is session-configurable and supports multiple default sources.

~~~sql
SELECT name, context, setting, unit, pending_restart
FROM pg_settings
WHERE name IN (
  'max_connections',
  'shared_buffers',
  'log_min_duration_statement',
  'statement_timeout',
  'listen_addresses'
)
ORDER BY name;
~~~

Always trust live server output rather than a static cheat sheet alone.

### Exercise 3

~~~sql
SELECT sourcefile, sourceline, name, setting, applied, error
FROM pg_file_settings
WHERE error IS NOT NULL OR name = 'work_mem'
ORDER BY seqno;

SELECT name, setting, source, pending_restart
FROM pg_settings
WHERE name = 'work_mem';
~~~

Read `error` for parse/validation issues; `applied=false` can indicate an override; `pending_restart` indicates a restart-required change. Check logs to confirm whether reload hit other problems.

### Exercise 4

Not always. `RESET` removes the `ALTER SYSTEM` override entirely, potentially falling back to another value from the main file. Since baseline already had `2000ms` in auto.conf, you likely need:

~~~sql
ALTER SYSTEM SET log_min_duration_statement = '2000ms';
SELECT pg_reload_conf();
~~~

Then verify the effective value and source.

### Exercise 5

Check `SHOW hba_file`, backup/current file contents, `pg_hba_file_rules`, logs, real client address across NAT/proxy, database/user, and TLS. Keep fallback access open, restore the old file, reload, and test **new connections** from both applications and DBAs. Never open `trust` or `0.0.0.0/0` as a quick fix.

### Exercise 6

~~~sql
ALTER ROLE report_reader IN DATABASE shopdb
SET statement_timeout = '10s';

-- Rollback:
ALTER ROLE report_reader IN DATABASE shopdb
RESET statement_timeout;
~~~

Role/database defaults apply to **new sessions**. Pools must recycle connections appropriately, and verification must use that exact role/database.

### Exercise 7

Risks: concurrent sort/hash nodes spike RAM usage, risking swap/OOM; increased pressure on OS page cache; other queries and the whole instance suffer even though only one report needs extra memory. First test `SET LOCAL work_mem` on a `SELECT` in staging, measure `EXPLAIN ANALYZE`, temp I/O, and concurrent load; consider a role-level override if only reporting needs it.

### Exercise 8

SQL is unavailable when the server is down. Restore the value/file/parameter group **via the real operational channel** (host files, operator, or cloud provider) from a known-good config; avoid deleting `postgresql.auto.conf` blindly. Read logs for the root cause, restart per runbook, and verify health and applications.

### Exercise 9

`context=postmaster` requires a restart. `pending_restart=true` indicates an unapplied restart-required change. `setting=100` reflects the effective value the running session/instance currently uses per the view; you cannot conclude 250 is active just because the file contains the new value.

### Exercise 10

The change record should include requester, reason, instance/role, baseline and source, new value, before/after measurements, reload type, timestamp, expected log volume, rollback triggers, steps to restore override or main file, owners, and post-change verification.

### Exercise 11

~~~sql
SELECT line_number, type, database, user_name, address, auth_method, error
FROM pg_hba_file_rules
WHERE error IS NOT NULL
ORDER BY line_number;
~~~

Zero parser errors do not prove a rule matches new connections; source IP, rule order, database, user, TLS, password/certificate, listener, firewall, and reload status all matter.

### Exercise 12

Check `statement_timeout`, `lock_timeout`, driver socket/read timeout, connection pool borrow timeout, HTTP gateway, and request deadlines. Collect exact SQLSTATE/error logs, pool acquire/execute durations, server query execution times, HTTP statuses, and end-to-end tracing.

## 29. Conclusion

PostgreSQL configuration spans multiple layers and scopes. **Seeing a value in a file is not enough to prove it is active**, and **a reload returning true at signal delivery does not prove the configuration is valid**. Core investigative tools include `pg_settings` (effective values and sources), `pg_file_settings` (file entries and errors), `pg_hba_file_rules`/`pg_ident_file_mappings` (authentication rules), alongside logs and real connection tests.

Classify every parameter by its `context`: use `SET LOCAL` for short experiments, `ALTER ROLE`/`ALTER DATABASE` for new-session defaults, reload for reloadable changes, and **controlled restarts** for `postmaster` parameters. The broader the scope of a change, the more critical staging tests, monitoring, and explicit abort criteria become.

A true rollback plan must capture **the prior value, the source that wrote it, how to restore that source, and how to verify the result in the exact session/instance**. Preparing rollback alongside every change allows tuning PostgreSQL systematically with evidence—minimizing connection drops, outages, and production workload regressions.
