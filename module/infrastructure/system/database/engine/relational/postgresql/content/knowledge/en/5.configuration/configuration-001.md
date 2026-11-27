# Roles of postgresql.conf, pg_hba.conf, and pg_ident.conf in PostgreSQL

When an application fails to connect to PostgreSQL, the root cause can vary widely: the server may not be listening on the required network address, authentication rules may not permit the connection source, the password may not match, or the operating system user may not be mapped to the PostgreSQL role requested by the application. Each case involves a different configuration layer.

Three essential files in configuring a PostgreSQL instance are:

- `postgresql.conf`: configures **how the server operates**, such as listening addresses, port, memory, logging, and many operational parameters.
- `pg_hba.conf`: determines **which connections are allowed to attempt authentication and which authentication method must be used**, based on connection type, database, role, and client address.
- `pg_ident.conf`: defines **how external identities** (such as operating system users) are mapped to a PostgreSQL role when the authentication method supports user mapping.

These three files **complement each other rather than replace one another**. Opening a port with `listen_addresses` does not automatically grant connection permission; having a matching `pg_hba.conf` entry does not automatically grant `SELECT` privileges; and declaring a `pg_ident.conf` entry does not create a PostgreSQL role.

This lesson explains the role of each file, their actual locations, precedence rules, reloading/restarting, common examples, and safe diagnostic methods in PostgreSQL.

## 1. Learning Objectives

After completing this lesson, you will be able to:

1. Accurately describe the connection flow from an application to PostgreSQL, identifying the role of each configuration file.
2. Find the effective paths of `postgresql.conf`, `pg_hba.conf`, and `pg_ident.conf` using SQL rather than guessing based on the OS distribution.
3. Distinguish between settings that require a **reload**, require a **restart**, or can be changed within a session.
4. Read `local`, `host`, `hostssl`, and `hostnossl` entries and understand the **first-match** rule in `pg_hba.conf`.
5. Set up a login account with SCRAM password authentication for TCP connections and understand TLS requirements.
6. Explain `peer` and `ident`, and construct a `pg_ident.conf` example mapping an OS user to a database role.
7. Inspect configuration using `SHOW`, `pg_settings`, `pg_file_settings`, `pg_hba_file_rules`, and `pg_ident_file_mappings`.
8. Identify distinct networking, authentication, and SQL authorization errors, and fix the right configuration layer.
9. Apply changes safely with an administrative fallback and rollback plan.

The examples use modern PostgreSQL on Linux/Unix to illustrate socket authentication. On Windows, containers, or managed PostgreSQL services, file locations and available authentication methods may differ.

---

## 2. The Big Picture: What Happens When a Client Connects?

Suppose an application wants to log in as PostgreSQL role `app_login` to database `appdb` on host `db.internal` over port 5432.

A simplified flow:

```text
Application / psql
    |
    | TCP to db.internal:5432 or Unix-domain socket
    v
[Is the PostgreSQL server listening?]
    |
    | Controlled by postgresql.conf:
    | listen_addresses, port, ssl, ...
    v
[Connection reaches the server]
    |
    | pg_hba.conf:
    | local/host/hostssl type
    | database, role, client IP
    | => selects an authentication rule
    v
[Execute authentication method]
    |
    | password / scram-sha-256 / peer /
    | cert / ident / other method
    |
    | pg_ident.conf (if user mapping is used)
    v
[PostgreSQL role identity authenticated]
    |
    | Role must exist, have LOGIN,
    | CONNECT privilege, and object privileges
    v
[Session established; application sends SQL]
    |
    | GRANT, REVOKE, RLS, schema/table privileges...
    v
[Read/write data according to effective privileges]
```

There are at least **four independent questions** here:

| Question | Primary Source of Control |
| --- | --- |
| Does the server accept connections on that address/port? | `postgresql.conf`, service status, network/firewall |
| How must this client authenticate? | `pg_hba.conf` |
| Can an external identity be used to log in as a differently named PostgreSQL role? | `pg_ident.conf` when the method supports mapping |
| After logging in, which databases/tables can be accessed? | Roles, `LOGIN`, `CONNECT`, `GRANT`, `REVOKE`, RLS, and other SQL policies |

**Do not use `pg_hba.conf` as a substitute for table access privileges.** It operates at the connection/authentication stage, before the application begins running business queries.

## 3. Do the Three Files Have the Same Function?

No. See the comparison table below:

| File | Purpose | Example Content | When Is It Read? |
| --- | --- | --- | --- |
| `postgresql.conf` | Operational parameters of the instance | `listen_addresses`, `port`, `shared_buffers`, `log_min_duration_statement` | At startup and/or on reload, depending on the parameter |
| `pg_hba.conf` | Client connection authentication rules | `hostssl appdb app_login 10.20.1.0/24 scram-sha-256` | Checked when a new connection arrives; configuration is loaded at startup/reload depending on the platform |
| `pg_ident.conf` | Mapping external usernames to PostgreSQL roles | `appmap appsvc app_login` | Used when user mapping is needed for an authentication method; configuration is loaded at startup/reload |

These files are managed per **PostgreSQL instance/cluster**; separate files are not automatically created for each application database.

You can alter the behavior of a single session with the SQL `SET` command for allowed parameters; that does not turn `pg_hba.conf` or `pg_ident.conf` into database SQL objects.

---

## 4. Finding the Exact Locations of the Active Files

Do not assume PostgreSQL always places its files in `/var/lib/postgresql/data/`. Installations via Linux packages, source builds, Docker, Kubernetes, or managed services can change the paths.

Connect using a role with appropriate privileges to view configuration details:

```sql
SHOW config_file;
SHOW hba_file;
SHOW ident_file;
SHOW data_directory;
```

Or:

```sql
SELECT
    current_setting('config_file') AS config_path,
    current_setting('hba_file') AS hba_path,
    current_setting('ident_file') AS ident_path;
```

Some sensitive settings or path details may be restricted for regular users; use an appropriately authorized administrative/monitoring account.

### 4.1. Distinguishing the Data Directory from the Config Directory

`data_directory` is the instance's data directory. It may be **different from the directory containing `postgresql.conf`**. For example, in some Linux distributions, configuration resides under `/etc/postgresql/...` while data resides under `/var/lib/postgresql/...`.

Therefore, the proper procedure is:

1. Identify the PostgreSQL instance you are connecting to.
2. Run `SHOW config_file`, `SHOW hba_file`, `SHOW ident_file`.
3. Use the actual paths returned by the instance.
4. Verify that you have permission to edit files on the right host/container.
5. Back up the current configuration before editing.

A single machine may run **multiple PostgreSQL clusters or containers**. Editing the files of the wrong cluster will not change the system you are diagnosing.

### 4.2. When Using a Managed PostgreSQL Service

With a managed PostgreSQL service, you might not be allowed to edit files directly on the filesystem. The provider may use parameter groups, instance configurations, or a dedicated interface to change parameters or network restrictions.

Although the SQL syntax and concepts are similar, **the ability to edit files, reload, restart, and enforce TLS policies depends on the provider**. Do not attempt to bypass restrictions or tamper with the service's filesystem where you have not been granted administrative access.

---

## 5. `postgresql.conf`: Server Operational Parameters

The `postgresql.conf` file contains parameters written in the form `parameter_name = value`. Lines beginning with `#` are usually comments.

An **illustrative** example, not a configuration to copy directly into production:

```conf
# PostgreSQL server settings (example only)

listen_addresses = 'localhost'
port = 5432

max_connections = 100
shared_buffers = '256MB'

password_encryption = 'scram-sha-256'
log_min_duration_statement = '500ms'
```

### 5.1. Connection Parameters

| Parameter | Meaning |
| --- | --- |
| `listen_addresses` | List of network addresses on the **server** machine on which PostgreSQL listens via TCP |
| `port` | TCP port PostgreSQL serves on, typically 5432 |
| `max_connections` | Configured limit on concurrent connections |
| `unix_socket_directories` | Location of Unix-domain sockets when supported by the platform |
| `ssl` | Controls TLS connection support depending on configuration and build/installation capabilities |

An important point: `listen_addresses` refers to **IP addresses bound to the server**, not the list of client IPs allowed to connect.

For example:

```conf
# Server listens only on loopback on the server machine:
listen_addresses = 'localhost'
```

In this case, a client on another machine may not be able to connect via TCP, even if `pg_hba.conf` contains `host all all 10.20.1.0/24 ...`.

If the server has an internal address `10.20.0.10`, an illustrative configuration to accept connections on that interface is:

```conf
listen_addresses = 'localhost,10.20.0.10'
```

The address must actually exist on the server machine; firewalls, routing, and `pg_hba.conf` must be configured accordingly. This is not a recommendation to expose PostgreSQL on all interfaces in production.

`listen_addresses = '*'` instructs PostgreSQL to listen on all available interfaces; it does **not** mean all clients will authenticate successfully, and it expands the connection surface so it must be evaluated carefully.

### 5.2. Memory and Resource Parameters

Example:

```conf
shared_buffers = '256MB'
work_mem = '4MB'
maintenance_work_mem = '64MB'
max_connections = 100
```

- `shared_buffers`: PostgreSQL's shared buffer pool for frequently accessed data pages; this is not the total amount of RAM PostgreSQL can consume.
- `work_mem`: base memory limit for operations such as sorting and hashing per operation context; a single query or multiple sessions can use **multiple** work memory allocations, not just one `work_mem` across the entire server.
- `maintenance_work_mem`: memory budget for certain maintenance operations.
- `max_connections`: configured maximum number of connections, which affects server resource consumption.

There is no universal "standard" parameter set for every system. Blindly increasing `work_mem` on a server with many connections can cause significant RAM pressure; increasing `max_connections` does not necessarily improve the system's capacity under load.

### 5.3. Logging and Observability Parameters

Example:

```conf
log_min_duration_statement = '500ms'
log_lock_waits = on
```

- `log_min_duration_statement` can log statements that exceed the configured duration threshold, which is useful when investigating slow queries.
- `log_lock_waits` helps log certain long lock-wait situations according to the associated logging mechanism.

Overly verbose logging incurs I/O and storage overhead and may record sensitive data inside SQL statements. Enable only the required level and design an appropriate log retention policy.

### 5.4. Where Does PostgreSQL Get Effective Values From?

A parameter's value **does not necessarily come solely from a single line in `postgresql.conf`**. Sources may include:

- PostgreSQL's built-in defaults.
- The main configuration file and included files.
- The `postgresql.auto.conf` file managed by `ALTER SYSTEM`.
- Server startup arguments, such as `-c` options passed by the launch process.
- Database/role-level settings such as `ALTER DATABASE ... SET` or `ALTER ROLE ... SET` when allowed for the parameter.
- Session-level settings via `SET` for parameters permitted to change within a session.

**Therefore, editing `postgresql.conf` without seeing the value change does not prove that reload is broken.** A higher-precedence source may be setting a different value.

---

## 6. Viewing Effective Parameters Using SQL

Before modifying files, inspect what values the server is actually using:

```sql
SHOW listen_addresses;
SHOW port;
SHOW max_connections;
SHOW shared_buffers;
SHOW work_mem;
SHOW password_encryption;
```

The `pg_settings` view provides more detail:

```sql
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
    'listen_addresses',
    'port',
    'max_connections',
    'shared_buffers',
    'work_mem',
    'password_encryption',
    'log_min_duration_statement'
)
ORDER BY name;
```

Key columns to pay attention to:

| Column | Meaning |
| --- | --- |
| `name` | Parameter name |
| `setting` | Effective value as represented by the view |
| `unit` | Internal or display unit to consider when reading the value |
| `context` | Scope/timing at which the parameter can be changed |
| `source` | Source of the effective value |
| `sourcefile`, `sourceline` | Configuration file path/line number if permitted to be displayed |
| `pending_restart` | Indicates whether a configuration change requires a restart to take effect |

The `sourcefile` and `sourceline` columns may be hidden if the account lacks privileges to view the corresponding configuration metadata.

### 6.1. Three Common Change Contexts

| Group | Common Examples | How It Takes Effect |
| --- | --- | --- |
| Parameters changeable only at server start (`context = postmaster`) | `listen_addresses`, `port`, `shared_buffers`, `max_connections` | **Restart PostgreSQL** |
| Server parameters reloadable at runtime (`context = sighup`) | Many logging parameters, configured operational limits | **Reload configuration** |
| Parameters changeable in a session (`user`/`superuser` or appropriate context) | `work_mem`, `statement_timeout` according to privileges | Use `SET` or appropriate session/role/database configuration |

This table is a general overview. When unsure, **check `pg_settings.context` directly on the running version** instead of inferring solely from the parameter name.

### 6.2. `ALTER SYSTEM` and `postgresql.auto.conf`

PostgreSQL supports:

```sql
-- Example in a test instance, executed by an administrator with sufficient privileges.
ALTER SYSTEM SET log_min_duration_statement = '500ms';
```

This command writes the configuration into `postgresql.auto.conf` rather than directly editing lines in `postgresql.conf`. The auto-config file has its own location and precedence mechanism, typically evaluated after the main configuration. Avoid manually editing `postgresql.auto.conf` without a clear change-control process.

After `ALTER SYSTEM`, the change still requires a **reload or restart** depending on the parameter. `ALTER SYSTEM` cannot run inside a regular transaction block. To revert a setting written to auto conf:

```sql
ALTER SYSTEM RESET log_min_duration_statement;
```

Then reload the configuration appropriately. These statements are **for syntax illustration only**; do not run them on a production instance without proper authorization and an approved change process.

---

## 7. Precedence When Multiple Files or Configuration Lines Exist

In `postgresql.conf`, include directives can be used:

```conf
include = 'memory.conf'
include_if_exists = 'local-overrides.conf'
include_dir = 'conf.d'
```

Depending on deployment layout, these files may group parameters by category. Ordering of configuration sources must be understood according to PostgreSQL's reading and precedence rules; **the final effective setting may come from a file other than the line you just edited**.

A simple example:

```conf
# postgresql.conf
work_mem = '4MB'
include = 'performance.conf'
```

The `performance.conf` file contains:

```conf
work_mem = '16MB'
```

With the appropriate application order and no higher-precedence source, the later value can override the earlier value. When `postgresql.auto.conf` or `-c` startup arguments are used, their respective precedence order must also be considered.

Do not rely on inspecting only a single file. When investigating, use `pg_settings` together with the `pg_file_settings` view:

```sql
SELECT
    sourcefile,
    sourceline,
    name,
    setting,
    applied,
    error
FROM pg_file_settings
WHERE name = 'work_mem'
ORDER BY sourcefile, sourceline;
```

This view shows lines parsed from configuration files and whether those values were applied. `applied = false` does not always indicate a syntax error: a line may simply have been overridden by a later effective entry. Check the `error` column and the effective value in `pg_settings`.

---

## 8. `pg_hba.conf`: Client Authentication Rules

The name HBA comes from **Host-Based Authentication**, though the file also governs connections over Unix-domain sockets. It answers:

> "For this connection type, database, PostgreSQL username, and source address, which authentication method must be used?"

A typical HBA line for TCP connections has the format:

```text
TYPE  DATABASE  USER  ADDRESS  METHOD  [OPTIONS]
```

Example:

```conf
# TYPE     DATABASE USER        ADDRESS         METHOD
host       appdb    app_login   10.20.1.0/24    scram-sha-256
```

Meaning:

- `host`: the rule applies to TCP/IP connections.
- `appdb`: the target database.
- `app_login`: the PostgreSQL role the client wants to log in as.
- `10.20.1.0/24`: clients within the corresponding IPv4 subnet.
- `scram-sha-256`: password authentication using SCRAM.
- Additional options may appear after the method, depending on the authentication type.

Once authentication succeeds, PostgreSQL still checks the role, connection privileges, and related conditions; an HBA rule **is not a SQL privilege grant**.

### 8.1. Common HBA Entry Types

| `TYPE` | Connections Covered | Notes |
| --- | --- | --- |
| `local` | Unix-domain sockets on the same host | Has no IP `ADDRESS` column; can use `peer` |
| `host` | TCP/IP, unrestricted by TLS state in the rule | Matches both TLS and non-TLS connections |
| `hostssl` | TCP/IP using TLS | Requires PostgreSQL to be configured with SSL/TLS support |
| `hostnossl` | TCP/IP without TLS | Generally should not be allowed for sensitive data |
| Other variants | Depends on version and authentication/SSL/GSS mechanisms | Use only when you thoroughly understand the feature |

**`local` does not mean the TCP address `127.0.0.1`.** These are two different connection types:

```bash
# On Unix/Linux: omitting -h typically selects a Unix-domain socket.
psql -U app_login -d appdb

# With -h 127.0.0.1: uses TCP/IP loopback.
psql -h 127.0.0.1 -U app_login -d appdb
```

A `local` line may use `peer`, whereas a `host` line for loopback may use `scram-sha-256`. Therefore, for the same database/role, one login method can succeed while the other fails.

### 8.2. The DATABASE, USER, and ADDRESS Fields

`DATABASE` can specify an exact database name or special keywords such as `all`, `sameuser`, and `samerole`. `USER` can be a role name or group according to HBA syntax; some cases allow role name patterns or included lists.

`ADDRESS` can be an IPv4/IPv6 address with a CIDR mask, for example:

```conf
host  appdb  app_login  127.0.0.1/32     scram-sha-256
host  appdb  app_login  10.20.1.0/24     scram-sha-256
host  appdb  app_login  ::1/128          scram-sha-256
```

Distinctions:

- `127.0.0.1/32`: a single IPv4 loopback address.
- `10.20.1.0/24`: an example IPv4 subnet.
- `::1/128`: IPv6 loopback.

Using an address range broader than actually needed expands the scope of clients permitted to **attempt authentication**. It does not grant them passwords or SQL privileges, but it increases the attack surface.

### 8.3. Authentication Methods

| `METHOD` | Role | When to Consider |
| --- | --- | --- |
| `scram-sha-256` | Password authentication using SCRAM | Suitable for most modern PostgreSQL clients |
| `peer` | Authenticates using the OS user of a Unix socket connection | Managed local services on Linux/Unix |
| `ident` | Obtains client identity via an ident service, typically for TCP in specialized contexts | Uncommon; requires understanding infrastructure trust |
| `cert` | Authenticates using a TLS client certificate | Environments with PKI and proper certificate management |
| `trust` | Accepts matching connections without requiring password verification | Only in tightly controlled special situations; avoid in production |
| `reject` | Rejects matching connections | Used when a specific range needs to be blocked |
| `md5` | Legacy password method / compatibility setting | Avoid new designs relying on MD5; prefer SCRAM |
| PAM/LDAP/GSS/SSPI... | External infrastructure-integrated authentication | Requires environment-specific configuration |

Do not use `trust` for open network ranges merely for "ease of connection." In production configurations, prefer modern authentication methods, restricted networks, and TLS with remote identity verification where needed.

---

## 9. The Most Important Rule in pg_hba.conf: First Match

PostgreSQL evaluates HBA lines **in order** and selects the **first line that matches** the connection type, database, user, and source address. If authentication fails under that line's method, the server **does not continue trying subsequent lines as a fallback**.

Example:

```conf
# Line 1 matches all IPv4 TCP connections from 10.20.1.0/24 to appdb:
host  appdb  app_login  10.20.1.0/24    reject

# Line 2 intends to allow the same connection, but will never be tried:
host  appdb  app_login  10.20.1.15/32   scram-sha-256
```

A connection from `10.20.1.15` to `appdb` as `app_login` is rejected at **Line 1**. Line 2 is more specific, but because it appears afterward, it is never used.

To allow `10.20.1.15` while blocking the rest of the subnet, the order must be:

```conf
host  appdb  app_login  10.20.1.15/32   scram-sha-256
host  appdb  app_login  10.20.1.0/24    reject
```

**PostgreSQL does not pick the "most specific" line via an IP specificity ranking algorithm.** It picks the first matching line in the order of the effective configuration.

### 9.1. Pitfall with Broad Rules Placed First

Example:

```conf
local  all    all                 peer
local  appdb  app_login           peer map=local_app_map
```

The `local all all peer` line already matches every Unix socket connection. The mapping line below it is never evaluated. Therefore, to use a specific mapping, place the specific rule **before** the broader rule:

```conf
local  appdb  app_login           peer map=local_app_map
local  all    all                 peer
```

This is a common reason why logging in with a mapped user still fails even after `pg_ident.conf` has been configured correctly.

### 9.2. What If No Line Matches?

If no HBA line matches the request, the connection is rejected. The message may look like:

```text
FATAL: no pg_hba.conf entry for host "...",
user "...", database "...", ...
```

Do not solve this by immediately adding:

```conf
# DANGEROUS CONFIGURATION if deployed on a real network:
host  all  all  0.0.0.0/0  trust
```

This rule allows IPv4 connections matching it from anywhere **without requiring a password**, which is very risky. The proper fix is to identify the required host, database, role, connection type, and security method, then add the **narrowest possible rule**.

---

## 10. HBA Example for an Application Connecting via TCP over TLS

Suppose:

- The PostgreSQL server has internal IP address `10.20.0.10`.
- The application connects from `10.20.1.15`.
- The target database is `appdb`.
- The login PostgreSQL role is `app_login`.
- The organization requires TLS and SCRAM.

In `postgresql.conf` (an example only, after TLS infrastructure is prepared):

```conf
listen_addresses = 'localhost,10.20.0.10'
port = 5432

# Enable TLS only when cert/key/server configuration is properly prepared.
ssl = on
```

In `pg_hba.conf`:

```conf
# TYPE    DATABASE USER       ADDRESS         METHOD
hostssl   appdb    app_login  10.20.1.15/32   scram-sha-256
```

In PostgreSQL (using an account with role-management privileges):

```sql
-- Learning example only; use a strong secret and never store real passwords in Git.
CREATE ROLE app_login LOGIN
PASSWORD 'REPLACE_WITH_LONG_RANDOM_SECRET';

-- Assuming database appdb already exists.
GRANT CONNECT ON DATABASE appdb TO app_login;
```

Notes:

1. `pg_hba.conf` only permits the application to **attempt** SCRAM authentication on TLS connections from the specified IP.
2. Role `app_login` must exist and have the `LOGIN` attribute.
3. The server must have a password verifier compatible with SCRAM. `password_encryption = 'scram-sha-256'` governs how **newly set** passwords are encrypted; changing this setting does not automatically convert previously stored passwords.
4. The client must be configured to verify the TLS server (e.g., `sslmode=verify-full`, with the proper CA and hostname), rather than enabling encryption without identity verification.
5. `GRANT CONNECT` does not grant `SELECT` or `INSERT` privileges inside the database. Appropriate schema/table/sequence privileges must be granted separately.
6. The network/firewall must allow traffic from the application to the server; HBA does not replace network rules.
7. `listen_addresses` is a parameter that **requires a restart** to take effect; HBA changes typically require a reload.

Example client command (illustrative only; requires accurate CA and DNS in a real environment):

```bash
psql "host=db.internal port=5432 dbname=appdb user=app_login sslmode=verify-full sslrootcert=/path/to/ca.pem"
```

If the server certificate does not match the hostname or the CA is untrusted, `verify-full` will reject the connection. This is an essential safeguard, not a reason to disable verification immediately.

---

## 11. `pg_ident.conf`: Mapping External Usernames

Normally, the `peer` method on a Unix socket checks the OS username of the client process. If you run `psql` as OS user `appsvc` and want to log in as PostgreSQL role `app_login`, the two names differ, so default `peer` authentication does not treat them as equivalent.

`pg_ident.conf` solves **identity mapping** for authentication methods that support it.

Common line format:

```text
MAPNAME  SYSTEM-USERNAME  PG-USERNAME
```

Example in `pg_ident.conf`:

```conf
# MAPNAME      SYSTEM-USERNAME  PG-USERNAME
local_app_map  appsvc           app_login
```

Meaning: when an authentication rule uses the map named `local_app_map`, the external user `appsvc` is allowed to authenticate as PostgreSQL role `app_login` according to that mapping.

**This is not an account rename inside PostgreSQL.** Role `app_login` must still be created via SQL, and that role still needs appropriate privileges on the database.

### 11.1. Combining pg_ident.conf with pg_hba.conf

In `pg_hba.conf`:

```conf
# Specific rule MUST come before broader local rules.
local  appdb  app_login  peer map=local_app_map
local  all    all        peer
```

In `pg_ident.conf`:

```conf
local_app_map  appsvc  app_login
```

In SQL, the role must exist:

```sql
CREATE ROLE app_login LOGIN;
GRANT CONNECT ON DATABASE appdb TO app_login;
```

On a Unix/Linux host with a properly managed OS user `appsvc`, when running `psql` as that user and connecting over a Unix socket:

```bash
psql -U app_login -d appdb
```

Conceptual processing in PostgreSQL:

```text
Client connects via Unix-domain socket
         |
         v
HBA: local appdb app_login peer map=local_app_map
         |
         v
Obtain actual OS user identity: appsvc
         |
         v
pg_ident map local_app_map:
    appsvc -> app_login
         |
         v
Authenticate for PostgreSQL role app_login
         |
         v
Check CONNECT and subsequent SQL privileges
```

Creating the mapping **does not create the OS user `appsvc`** and does not change who is allowed to run processes under that OS account. OS/container administration and file/socket permissions must still be configured properly.

### 11.2. How `peer` Differs from `ident`

| Method | Where Does Identity Information Come From? | Context |
| --- | --- | --- |
| `peer` | The **server-side** operating system retrieves the identity of the process connecting via Unix-domain socket | `local` connections on supported systems |
| `ident` | The server queries an Ident service on the client side to get the username for a TCP connection via the ident protocol | host/TCP connections when the infrastructure is controlled |
| `cert` | Identity from a TLS client certificate under certificate authentication policy | TLS connections and PKI systems |

`peer` is usually the more natural choice when a local service runs under a dedicated OS user and you do not want to store a PostgreSQL password for socket connections.

`ident` depends on the response from a client-side ident service, so the trustworthiness of the client host/infrastructure must be evaluated. It is not a default replacement for password/TLS authentication for applications connecting over untrusted networks.

`pg_ident.conf` can also participate in other mapping mechanisms such as client certificates when properly configured. It **is not a password file**.

### 11.3. One Mapping Can Map Multiple Identities

Example:

```conf
# Two different OS users mapped to the same database role.
local_app_map  appsvc   app_login
local_app_map  jobsync  app_login
```

This allows two OS identities to be mapped to the same PostgreSQL role if HBA permits. However, sharing a database role reduces the ability to distinguish access on the PostgreSQL side. In many systems, it is better to assign **separate roles per service** for clearer logging and auditing.

A map can also use name-matching expressions as supported by PostgreSQL, though this lesson prefers explicit mappings for easier control. Do not write overly broad regex patterns without understanding their impact on login permissions.

### 11.4. Mapping Does Not Change Table Privileges

Once `appsvc` is mapped to `app_login`, all SQL executed after login runs with the effective privileges of `app_login` and its associated roles/settings. It **does not gain OS root privileges**, does not automatically receive PostgreSQL superuser privileges, and does not automatically gain access to all tables.

Distinguish the two stages:

```text
OS user appsvc  --pg_ident mapping-->  PostgreSQL role app_login
                                               |
                                               v
                                        Check GRANT/REVOKE,
                                        schema/table/RLS...
```

---

## 12. A Safe Configuration Change Workflow

Editing PostgreSQL configuration on a live server can disconnect applications or prevent the server from starting. The workflow should distinguish between **parameter changes** and **authentication changes**.

### Step 1 — Identify the Right Instance and Current Values

```sql
SELECT current_database(), current_user;
SHOW config_file;
SHOW hba_file;
SHOW ident_file;

SELECT name, setting, context, source, pending_restart
FROM pg_settings
WHERE name IN ('listen_addresses', 'port', 'work_mem', 'shared_buffers')
ORDER BY name;
```

Note the administrative login path that currently works. If you misconfigure HBA and no new connections can be made, you may need console access or an already open administrative session to recover.

### Step 2 — Back Up Configuration and Prepare a Rollback Plan

Before modifying real files:

- Save a copy of the current configuration files using authorized OS administration tools.
- Document which lines are changed and who approved the change.
- Maintain a trusted administrative access path, but **never** leave a broad `trust` rule as a "backdoor" in production.
- Plan for a reload or restart depending on the parameters.
- Test in a staging/test environment before applying to production.

### Step 3 — Make the Smallest Scoped Change

For instance, if you need to add an application IP to HBA, add a `hostssl` line for the specific database, role, and IP, placed appropriately according to the first-match rule.

If you need to change `listen_addresses`, confirm the address actually exists on the server host and remember that the change usually requires a restart.

If you need to map an OS user, edit `pg_ident.conf` and ensure `pg_hba.conf` has a matching `peer map=...` rule.

### Step 4 — Check File Configuration Errors Before Applying

PostgreSQL provides views to inspect parsed lines:

```sql
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
```

For HBA:

```sql
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
```

For mappings:

```sql
SELECT
    line_number,
    map_name,
    sys_name,
    pg_username,
    error
FROM pg_ident_file_mappings
ORDER BY line_number;
```

These views are available on supported PostgreSQL versions and may require specific administrative/monitoring privileges. Exact column structures may vary by version; if a query fails, inspect `\d+ pg_hba_file_rules` or the documentation for the running instance.

**Important:** a view reading/parsing the current file contents **does not prove that those rules are currently active in memory**. After editing files, reload the configuration as appropriate, check logs, and test a new connection.

### Step 5 — Perform the Right Type of Reload or Restart

To ask PostgreSQL to re-read configuration parts that support reloading:

```sql
SELECT pg_reload_conf();
```

A return value of `true` indicates PostgreSQL successfully sent the reload signal via the function's mechanism. **It is not a confirmation that every line in the files is valid and has been applied.** Check the server logs, `pg_file_settings`/HBA views, and effective values.

At the OS level, administrators can also use service tools or `pg_ctl reload` depending on how the instance is managed.

For parameters that require a restart (such as `listen_addresses`, `shared_buffers`), a reload **is not enough**. When a restart is required:

- Plan for connection impact.
- Ensure a configuration rollback plan is ready if the server fails to start.
- Check `pg_settings.pending_restart` and logs.
- Do not casually restart production just to test an exercise.

### Step 6 — Test a New Connection

Test the exact type of connection targeted by the new configuration:

- Unix socket (for `local`/`peer`).
- TCP with or without TLS per policy.
- Correct database, username, and source host.
- Created role with `CONNECT` privilege.

After logging in:

```sql
SELECT
    current_user,
    session_user,
    current_database(),
    inet_client_addr() AS client_ip;
```

For Unix socket connections, `inet_client_addr()` is typically `NULL`. For TCP, it shows the client address as seen by the server.

Then test **an authorized `SELECT` query**—do not run `DROP TABLE` tests in a live environment.

---

## 13. How Reload Differs from Restart

| Action | When to Use | Basic Impact |
| --- | --- | --- |
| `SELECT pg_reload_conf();` | Changing reloadable parameters, HBA/ident in supported environments | Requests a configuration reload; does not stop the entire instance |
| `pg_ctl reload` / sending SIGHUP | OS-level administrative way to reload | Similar effect to requesting a reload |
| Restart PostgreSQL service | Changing parameters requiring postmaster restart or planned maintenance | Active connections may be dropped; server stops and starts again |
| `SET work_mem = '...'` | Changing only a single permitted session | Does not edit instance-wide configuration files |
| `ALTER ROLE ... SET ...` / `ALTER DATABASE ... SET ...` | Setting defaults per user/database if supported by the parameter | Typically affects new sessions according to application rules |
| `ALTER SYSTEM SET ...` | Writing server parameter changes to auto conf | Still requires reload/restart depending on context |

Typically, changing `pg_hba.conf` and `pg_ident.conf` on Unix/Linux requires a **reload** to take effect for new connections. On Windows, PostgreSQL may apply HBA changes to new connections per platform behavior without a Unix-style SIGHUP signal; even so, verify your specific version and operational procedures.

An **already active connection** is not re-authenticated immediately just because HBA changes. When evaluating changes, open a **new connection**. To revoke SQL access for existing sessions, you may also need to address roles, privileges, and active sessions; do not treat an HBA edit alone as terminating all already logged-in connections.

---

## 14. Inspecting HBA with pg_hba_file_rules

The `pg_hba_file_rules` view helps inspect how PostgreSQL parses HBA entries.

```sql
SELECT
    line_number,
    type,
    database,
    user_name,
    address,
    auth_method,
    error
FROM pg_hba_file_rules;
```

To filter for errors:

```sql
SELECT line_number, error
FROM pg_hba_file_rules
WHERE error IS NOT NULL;
```

An empty result from the error query shows that the view recorded no parse errors on those lines; it **does not prove the policy is functionally or security-wise correct**. An overly broad `trust` rule can be completely valid syntactically while still being dangerous.

Logical verification steps:

1. Determine whether the connection uses `local` or `host/hostssl`.
2. Identify the requested database, PostgreSQL role, and actual source IP.
3. Read lines in **effective order** to see which line matches first.
4. Check the authentication method and options such as `map=...`.
5. Verify client-side identity/secret/certificate.
6. If files were edited, confirm the reload succeeded and test a new connection.

An HBA file can use includes on supported PostgreSQL versions. When it does, effective rules can come from multiple files; do not inspect only one file and overlook included rules.

---

## 15. Inspecting Mappings with pg_ident_file_mappings

A misconfigured mapping can cause `peer` or other methods to reject connections even when both the OS user and PostgreSQL role exist.

Example mapping `appsvc → app_login` via map `local_app_map`:

```conf
# pg_ident.conf
local_app_map  appsvc  app_login
```

Check:

```sql
SELECT
    line_number,
    map_name,
    sys_name,
    pg_username,
    error
FROM pg_ident_file_mappings;
```

If you see:

- `map_name` differs from `map=...` in HBA → wrong mapping is referenced.
- `sys_name` differs from the actual OS username → mapping does not match.
- `pg_username` differs from the role requested by the client → does not match.
- `error` is not `NULL` → parse issue needs fixing.

After fixing, reload according to the environment and open a **new connection** to test.

Do not extend one mapping to too many PostgreSQL roles without clear requirements and governance. Mapping is only an identity-authentication bridge; authorization policies must still be restricted at the role level.

---

## 16. HBA Authentication Succeeds, but Queries Are Still Denied

Suppose an application has logged into `appdb` as `app_login`, runs:

```sql
SELECT * FROM public.orders;
```

and receives:

```text
ERROR: permission denied for table orders
```

This is **no longer an authentication method selection error in pg_hba.conf**. The connection has been established; PostgreSQL is checking object access privileges.

Items to inspect:

- Does the role have `LOGIN` (if troubleshooting the login stage)?
- Does the database grant `CONNECT` as required?
- Does the schema have `USAGE` privilege?
- Does the table have `SELECT`/`INSERT`/`UPDATE` privileges as needed?
- Does a sequence have required privileges if the operation uses a sequence?
- Is Row-Level Security or another policy restricting data access?

Example (grant only the privileges required by business needs):

```sql
-- Executed by an administrator/owner with grant privileges.
GRANT CONNECT ON DATABASE appdb TO app_login;
GRANT USAGE ON SCHEMA public TO app_login;
GRANT SELECT ON TABLE public.orders TO app_login;
```

These statements are illustrative only; `public.orders` must exist and belong to database `appdb` when executed. Do not escalate to `GRANT ALL PRIVILEGES ON ALL TABLES` just to resolve a `SELECT` query.

---

## 17. Troubleshooting by Error Message

The following symptoms represent **different problem layers**:

| Symptom | Layer to Check First | Diagnostic Question |
| --- | --- | --- |
| `connection refused` | Network/service/`postgresql.conf` | Is PostgreSQL running, and on which IP/port is it listening? |
| TCP connection timeout | Network, firewall, route, load balancer, security group | Are packets reaching the server, and is the port open per policy? |
| `no pg_hba.conf entry for host ...` | `pg_hba.conf` | Is there a matching line for connection type, database, user, IP, and TLS? |
| `password authentication failed for user ...` | HBA method, role, and credentials | What is the first matching line, and is the password/verifier correct? |
| `Peer authentication failed for user ...` | `peer` and `pg_ident.conf` | Does the OS username match the PostgreSQL role or mapping? |
| `role "..." does not exist` | Roles in the database cluster | Has the account been created? |
| `role "..." is not permitted to log in` | Role attributes | Does the role have `LOGIN`? |
| `permission denied for database ...` | SQL privileges | Has the appropriate `CONNECT` privilege been granted? |
| `permission denied for schema/table ...` | SQL privileges | What are the `USAGE`, `SELECT`/DML, and RLS privileges? |
| TLS handshake/certificate error | TLS/cert/client settings | Are the CA, hostname, certificate, and `sslmode` correct? |
| Parameter edited but `SHOW` unchanged | Reload/restart/config precedence | What are the parameter's `context`, `pending_restart`, and `source`? |
| PostgreSQL fails to start after file edit | Config syntax/values, file/certificate paths | What does the startup log report, and is a backup available to restore? |

### 17.1. Analyzing "no pg_hba.conf entry"

Suppose the log reports:

```text
FATAL: no pg_hba.conf entry for host "10.20.1.15",
user "app_login", database "appdb", no encryption
```

The phrase "no encryption" indicates that the connection attempt in this case **did not use TLS**. If HBA only has:

```conf
hostssl  appdb  app_login  10.20.1.15/32  scram-sha-256
```

then a non-TLS connection **does not match** the `hostssl` line. The proper fix may be configuring the client to use TLS correctly, rather than immediately relaxing HBA to `host` or `trust`.

Similarly, if the client actually arrives from a proxy/NAT IP different from what you expected, HBA must be designed for the source address seen by the server.

### 17.2. Analyzing "peer authentication failed"

A user runs:

```bash
psql -U app_login -d appdb
```

on Linux under OS user `developer`, while HBA uses:

```conf
local  all  all  peer
```

The `peer` method normally expects the OS user identity to match the PostgreSQL role unless a suitable mapping exists. Because `developer` differs from `app_login`, the connection can fail.

Context-appropriate options:

1. Log in as the PostgreSQL role matching the OS user if created and authorized.
2. Configure `pg_ident.conf` and a **narrow** `peer map=...` HBA rule if formal mapping is intended.
3. Use a TCP connection with SCRAM/TLS and managed secrets if the application does not need OS-user authentication.
4. Check whether the client actually uses a Unix socket or TCP; `-h 127.0.0.1` changes which HBA type is evaluated.

Do not replace the entire `local all all peer` line with `trust` as a "quick fix" on a shared machine.

---

## 18. Security Recommendations When Editing the Three Files

### 18.1. Do Not Expose the Network Wider Than Necessary

A risky configuration when paired with overly broad authentication rules:

```conf
# postgresql.conf
listen_addresses = '*'
```

and:

```conf
# pg_hba.conf: NOT RECOMMENDED for production
host  all  all  0.0.0.0/0  trust
```

If the port is reachable from untrusted sources, clients matching the `trust` rule can log in without a password. Instead, use:

- Intentional server listening addresses.
- Restricted client IP ranges that are genuinely permitted.
- `hostssl` for connections requiring TLS.
- Strong authentication methods such as SCRAM or certificates.
- Firewalls/security groups/private networks.
- SQL roles with least privilege.

### 18.2. Protect Configuration Files at the OS Level

Configuration files govern server operation and may contain paths, network policies, or sensitive parameters. Read/write permissions must align with the OS account running PostgreSQL and administrative procedures.

Do not edit files via publicly shared directories, do not grant world-writable permissions, and do not store TLS private keys or passwords directly in sample documentation.

### 18.3. Separate Login and Administrative Accounts

Application roles should only hold privileges needed for business operations. Administrative accounts that modify `postgresql.conf`/HBA or issue `GRANT` statements must be protected separately.

After a successful login, HBA does not enforce privilege boundaries between two roles. An application session does not gain permission to alter tables or read sensitive data simply because its IP address is permitted to connect.

### 18.4. Do Not Confuse Transport Security with Role Authentication

`hostssl` requires a TLS connection for that HBA line to match, but it does not guarantee the client is verifying the right server. The client should validate the CA and hostname where required, such as `sslmode=verify-full`, alongside proper certificate and renewal lifecycle management.

Conversely, `scram-sha-256` authenticates passwords more strongly than legacy methods, but does not replace transport encryption when required by security policy.

---

## 19. Hands-On Exercise: Reading Without Modifying Production Configuration

If you have a test PostgreSQL instance and appropriate viewing privileges, you can complete this section using only `SELECT` and `SHOW` statements.

### Step 1 — Locate the Three Files

```sql
SHOW config_file;
SHOW hba_file;
SHOW ident_file;
```

Record the paths and answer: do they necessarily reside in the same directory as `data_directory`?

### Step 2 — Inspect Connection Settings and Context

```sql
SELECT
    name,
    setting,
    context,
    source,
    pending_restart
FROM pg_settings
WHERE name IN (
    'listen_addresses',
    'port',
    'max_connections',
    'work_mem',
    'shared_buffers'
)
ORDER BY name;
```

Identify which parameters have context `postmaster` and which can be changed within a session.

### Step 3 — Inspect HBA as Parsed by the Server

```sql
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
```

Identify which line matches a TCP `localhost` connection in your lab environment (knowing the database, role, and TLS state).

### Step 4 — Inspect Mappings If Any

```sql
SELECT
    line_number,
    map_name,
    sys_name,
    pg_username,
    error
FROM pg_ident_file_mappings
ORDER BY line_number;
```

If the table has no mappings, explain why that does not mean all `peer` connections fail: `peer` can authenticate when the OS username matches the database role without needing a separate mapping.

### Step 5 — Check Sources and Precedence

```sql
SELECT
    name,
    setting,
    source,
    sourcefile,
    sourceline
FROM pg_settings
WHERE name IN ('work_mem', 'log_min_duration_statement');
```

If an administrator places settings across multiple files, describe how to cross-check `pg_file_settings` against the effective value.

### Step 6 — Observe Your Own Connection

```sql
SELECT
    current_user,
    session_user,
    current_database(),
    inet_client_addr(),
    inet_server_addr(),
    inet_server_port();
```

If a TCP address field is `NULL`, consider that the session may be using a Unix socket. Do not infer whether a connection uses TLS solely from the presence of an IP address; inspect TLS configuration or TLS connection state appropriately.

---

## 20. Scenario Exercises

### Exercise 1 — Two Files and a Network Error

A server has:

```conf
# postgresql.conf
listen_addresses = 'localhost'
```

and:

```conf
# pg_hba.conf
host  appdb  app_login  10.20.1.15/32  scram-sha-256
```

The application on `10.20.1.15` tries to connect to the server's internal IP and receives `connection refused`. Why is adding the HBA line not enough? What other network settings must be checked?

### Exercise 2 — First-Match Rule

Given the HBA:

```conf
host  appdb  app_login  10.20.1.0/24    reject
host  appdb  app_login  10.20.1.15/32   scram-sha-256
```

Will a connection from `10.20.1.15` be allowed to attempt SCRAM? Rewrite the order so that address is allowed to authenticate with SCRAM while other addresses in the subnet are rejected.

### Exercise 3 — Local Socket vs. TCP

Explain why these two commands can produce different results:

```bash
psql -U app_login -d appdb
psql -h 127.0.0.1 -U app_login -d appdb
```

List the corresponding `local` and `host` entries in HBA.

### Exercise 4 — Writing a Safe Mapping

A service on Linux runs under OS user `batchsvc`, while the required PostgreSQL role is `batch_login`. It needs to connect via Unix socket to database `appdb`.

Write a `pg_ident.conf` line and a `pg_hba.conf` line using `peer map=...` to perform an explicit mapping. Explain why specific lines must appear before a broader `local all all ...` rule.

### Exercise 5 — Reload or Restart?

Classify the following changes:

1. Adding a `hostssl` line to `pg_hba.conf`.
2. Adding a mapping to `pg_ident.conf`.
3. Changing `listen_addresses`.
4. Changing `shared_buffers`.
5. Running `SET work_mem = '16MB'` in a permitted session.

State when a reload is sufficient, when a restart is required, and why a **new connection** must be tested after modifying HBA.

### Exercise 6 — Can Log In, Cannot SELECT

An application logs in successfully but receives `permission denied for relation orders`. Why should you not continue modifying HBA? Name the privileges that may need to be checked at the database, schema, and table levels.

### Exercise 7 — HBA and TLS

Only this rule exists:

```conf
hostssl  appdb  app_login  10.20.1.15/32  scram-sha-256
```

Will a connection from the right IP without TLS match? If the client uses TLS but the server certificate is not trusted by the client, which layer must be checked? Why should you not rush to change it to `host all all ... trust`?

### Exercise 8 — Reading What Is Actually Applied

Someone edits `work_mem` in the main file, reloads successfully, yet `SHOW work_mem` still returns the old value. State three possibilities: the line was overridden by an included file or auto conf, the session has its own override, or the new value failed to load due to an error. Write the SQL queries needed to verify `source`, `sourcefile`, `pg_file_settings`, and `pending_restart`.

---

## 21. Quick Reference Table

| What Do You Want to Do? | Where to Check? | Notes |
| --- | --- | --- |
| Have the server listen on another IP/port | `postgresql.conf`: `listen_addresses`, `port` | Usually requires restart |
| Increase `shared_buffers` memory | `postgresql.conf` or effective config source | Check `context`, usually requires restart |
| Change slow query logging threshold | PostgreSQL logging parameters | Check context and reload appropriately |
| Allow an app from a specific IP to authenticate | `pg_hba.conf` | Specific line, strong method, check first-match |
| Force a group of connections to use TLS | `hostssl` + server/client TLS config | Does not replace certificate verification |
| OS user differs from PostgreSQL role name | `pg_ident.conf` + `pg_hba.conf map=...` | Applies to methods supporting mapping |
| Do not know where config files are located | `SHOW config_file/hba_file/ident_file` | Read from the connected instance |
| Unsure which value is effective | `pg_settings` | Check `setting`, `source`, `context` |
| Check for configuration file line errors | `pg_file_settings` | Check `applied` and `error` |
| Check if HBA can be parsed | `pg_hba_file_rules` | Syntactic validity does not prove policy correctness |
| Check ident mappings | `pg_ident_file_mappings` | Check map name and usernames |
| Ask PostgreSQL to re-read config | `SELECT pg_reload_conf();` | Re-verify logs and effective values |
| App connects then SELECT is denied | `GRANT`, `REVOKE`, schema/table/RLS | Not an HBA error |
| App receives connection refused | Service, listen address, firewall, route | HBA does not replace server listening |

## Conclusion

The three PostgreSQL configuration files have distinct responsibilities:

- **`postgresql.conf`** defines the operational parameters of the PostgreSQL server, including listening addresses, port, memory, and logging. Changes may require a reload or restart depending on `pg_settings.context`.
- **`pg_hba.conf`** defines authentication rules for each connection type. PostgreSQL evaluates rules **in order and selects the first matching line**; authentication failure on that line does not cause the server to try subsequent lines.
- **`pg_ident.conf`** supports mapping external identities to PostgreSQL roles when using methods such as `peer` or other user-mapping-capable methods. It does not create roles, store passwords, or automatically grant data privileges.

A successful connection requires coordinating **server listening → network reaching the server → HBA choosing the right method → valid identity authentication → role having appropriate SQL privileges**. When a step fails, fix the right layer instead of arbitrarily widening permissions or disabling authentication. Reading effective values, documenting changes, reloading/restarting properly, and testing a new connection are essential habits for operating PostgreSQL safely.
