# Listen Addresses, Connection Ports, and Session Limits in PostgreSQL

After installing PostgreSQL, applications typically connect using a URL such as `jdbc:postgresql://db.internal:5432/shopdb`. However, having the right hostname and password is not enough to guarantee a successful connection. The server must **listen on the right network interface**, use the **right port**, accept connections according to **authentication rules**, and still have **available connection slots** for new clients.

For instance, PostgreSQL may be running normally yet listening only on `127.0.0.1`, preventing applications on other hosts from connecting. Or an application may work fine for a few minutes and then report `too many clients already` when multiple connection pools open sessions concurrently. Both incidents share the symptom "cannot connect," yet their root causes and fixes are completely different.

This lesson explains how to configure and diagnose three interrelated areas:

1. **Listen addresses:** `listen_addresses`, network interfaces, and Unix-domain sockets.
2. **Connection ports:** `port`, server port, client port, Docker/Kubernetes, and multiple instances on the same host.
3. **Session limits:** `max_connections`, reserved slots, per-role/per-database limits, `pg_stat_activity`, and connection pooling.

Examples focus on modern PostgreSQL, particularly PostgreSQL 14–18. Some parameters such as `reserved_connections` exist only in newer major versions; always cross-check documentation against the major version of the running server. Configuration edits and restarts should only be run in lab environments or under an approved runbook.

## 1. What Layers Does a PostgreSQL Connection Pass Through?

Imagine a Java application on another host sending a connection request to PostgreSQL:

```text
                  APPLICATION / JDBC CLIENT
                            |
                 host + port + database
                            |
                            v
                 DNS / route / firewall
                            |
                            v
                   PostgreSQL server
               listen_addresses + port
                            |
                            v
                  pg_hba.conf + TLS
                            |
                            v
                   User authentication
                            |
                            v
             connection slot / role / database
                            |
                            v
                  SQL session established
                            |
                     SELECT / INSERT ...
```

Different layers answer different questions:

| Layer | Question | Configuration Point or Tool |
| --- | --- | --- |
| Network | Can the client reach the server host? | DNS, routing, firewall, security group, NetworkPolicy. |
| Listener | Is PostgreSQL listening on that exact address/port? | `listen_addresses`, `port`, `ss`, `Get-NetTCPConnection`. |
| Authentication | Which authentication method is allowed for this host, database, and role? | `pg_hba.conf`, user/password, TLS. |
| Session slot | Does the server or role/database allow another session? | `max_connections`, reserved slots, connection limits. |
| SQL privileges | Can the authenticated session read/modify objects? | `GRANT`, `REVOKE`, schema/table privileges. |

**Being able to ping the host** does not mean the PostgreSQL port is open. **An open port** does not mean PostgreSQL accepts the user. **Successful login** does not mean the user can read tables. And **a role with valid privileges** still cannot open another session if connection slots are exhausted.

## 2. Confirm the Right Server Before Editing Configuration

In an active SQL connection, check first:

```sql
SELECT
    current_database() AS database_name,
    current_user AS database_role,
    inet_server_addr() AS server_address,
    inet_server_port() AS server_port,
    current_setting('server_version') AS server_version,
    pg_postmaster_start_time() AS server_started_at;
```

Continue with:

```sql
SHOW config_file;
SHOW data_directory;
SHOW hba_file;
```

This helps catch a common mistake: an administrator edits `postgresql.conf` on instance A while the real application connects to instance B. One machine can run multiple PostgreSQL clusters with distinct data directories and ports.

Notes:

- `inet_server_addr()` shows the local server address targeted by the current TCP connection. Over Unix-domain sockets, it may return `NULL`.
- `inet_server_port()` is the **server-side port** of the TCP connection, not the client's ephemeral source port.
- If connecting through a load balancer, proxy, or port forwarding, also check the endpoint used by the application; parts of the network path may not be visible through SQL functions.
- `SHOW config_file` and `SHOW data_directory` may require privileges to view those parameters. Never elevate an application account to superuser just for diagnostics.

A concise command set:

```sql
SHOW server_version;
SHOW listen_addresses;
SHOW port;
SHOW max_connections;
SHOW unix_socket_directories;
```

In `psql`, there is also:

```text
\conninfo
```

to inspect which host/socket, port, and database the client itself is connected to.

## 3. listen_addresses: Which Addresses Does PostgreSQL Listen On?

`listen_addresses` determines **which IP addresses/interfaces the PostgreSQL process attempts to bind TCP listening sockets on** at startup.

Example in `postgresql.conf`:

```conf
listen_addresses = 'localhost'
port = 5432
```

The typical default is `localhost`. With this setting, PostgreSQL generally accepts TCP connections only from the local host via loopback, such as `127.0.0.1` and `::1` depending on system name resolution and IPv6 support. A client on another host cannot connect directly over the server's public or private network IP merely by knowing a password.

### 3.1. Common Values

| Configuration Value | Meaning | When to Consider |
| --- | --- | --- |
| `'localhost'` | Listens on appropriate loopback addresses on the machine. | Development machine, same-host local connections. |
| `'127.0.0.1'` | Listens on IPv4 loopback. | When only local IPv4 TCP connections are desired. |
| `'::1'` | Listens on IPv6 loopback. | When only local IPv6 TCP connections are desired. |
| `'10.20.30.11'` | Listens on a specific IP that must exist and be usable on the server. | Service on an internal network with a known IP. |
| `'localhost,10.20.30.11'` | List of multiple listening addresses. | Serving both local connections and an internal network. |
| `'*'` | Attempts to listen on all available IP interfaces. | Only when network layers, firewalls, authentication, and TLS are strictly controlled. |
| `''` | Opens no TCP listening sockets. | Environments needing only Unix-domain sockets, if supported by the platform. |

Example configuration for a server on a private network:

```conf
# Example: the address must actually belong to the PostgreSQL server host.
listen_addresses = 'localhost,10.20.30.11'
port = 5432
```

**Do not put a CIDR range like `'10.20.30.0/24'` into `listen_addresses`.** This is a list of server-side addresses/hostnames or `*` to bind, not a list of allowed client networks. Client IP ranges belong in firewall rules or `pg_hba.conf`.

### 3.2. Wildcard Does Not Mean Access Is Granted

`listen_addresses = '*'` allows PostgreSQL to listen on more interfaces, yet it **does not automatically grant login permission**. Remote clients must still pass network routing, firewalls, `pg_hba.conf`, and PostgreSQL authentication.

However, using a wildcard expands reachability to the PostgreSQL port. On real systems:

- Open only the interfaces genuinely needed.
- Restrict source access via firewalls, security groups, or NetworkPolicies.
- Use `pg_hba.conf` and strong authentication per connection group.
- Use TLS whenever traffic requires network transport protection.
- Never expose PostgreSQL directly to the public Internet without an appropriate security architecture.

**An overly broad configuration does not become safe merely because passwords are currently strong.** Security relies on reducing the attack surface across multiple layers.

### 3.3. IPv4 and IPv6

`127.0.0.1` is IPv4 loopback; `::1` is IPv6 loopback. Connecting to `localhost` may attempt IPv6 first or IPv4 first depending on DNS/OS and client libraries.

Thus, the following can happen:

```text
psql -h 127.0.0.1 ...  -> succeeds
psql -h ::1 ...        -> fails
psql -h localhost ...  -> outcome depends on how the client resolves/connects
```

If an application fails only with one host specification, check the actual addresses PostgreSQL is listening on, matching IPv4/IPv6 HBA rules, and DNS resolution. Never assume `localhost` is always identical to `127.0.0.1`.

## 4. TCP Connections and Unix-Domain Sockets

PostgreSQL can accept connections over:

1. **TCP/IP:** using host/IP and port; can traverse networks.
2. **Unix-domain socket:** a socket file in the filesystem on the same host, primarily on Unix/Linux systems.

In many Linux environments, when `-h` is omitted and no environment variable overrides it, `psql` defaults to connecting via a Unix-domain socket:

```bash
# Omitting -h: typically uses Unix-domain socket on Linux.
psql -U app_user -d appdb

# Specifying IPv4: uses TCP.
psql -h 127.0.0.1 -p 5432 -U app_user -d appdb
```

These two commands can match **different `pg_hba.conf` rules**: one matches a `local` entry for Unix sockets, while the other matches a `host`/`hostssl` entry for TCP.

### 4.1. unix_socket_directories

Inspect:

```sql
SHOW unix_socket_directories;
```

On Unix systems, this parameter lists the directories where PostgreSQL creates Unix-domain sockets. Socket filenames usually include the port number, e.g.:

```text
/var/run/postgresql/.s.PGSQL.5432
```

That path is an example only. Directory names depend on the distribution/package; some environments use `/tmp` or a PostgreSQL-specific directory.

If `listen_addresses = ''`, the server can still serve local connections via Unix-domain sockets when configured properly. Thus, **"not listening on TCP" does not mean "accepting zero connections."**

When client and server run in two separate containers, the server container's Unix socket does not automatically appear inside the client container. Using sockets across containers requires explicit path sharing; otherwise, TCP over the container network is usually simpler.

### 4.2. Does a Unix Socket Have a Port?

PostgreSQL socket files carry `.s.PGSQL.<port>` in their filename, yet that is not a TCP port open on the network. The `port` parameter still participates in naming the socket file, while local connections use the filesystem path.

This distinction is helpful when `pg_isready` reports the server ready over a socket while an application connecting to a TCP address gets `connection refused`.

## 5. port: The Port PostgreSQL Listens On

`port` is the TCP port PostgreSQL uses to accept connections. The standard value is `5432`.

```sql
SHOW port;
```

Example in `postgresql.conf`:

```conf
port = 5432
```

Notes:

- **Server port** is the port PostgreSQL listens on, e.g., `5432`.
- **Client source port** is normally an ephemeral port allocated by the client's OS; it does not need to match `5432`.
- **External proxy/container ports** may differ from PostgreSQL's internal port.
- The TCP port must be permitted through firewalls or security groups along the network path.

Example:

```text
App client: 10.20.30.50:49152
                      |
                      | TCP
                      v
DB server:  10.20.30.11:5432
```

Changing `port` does not automatically update JDBC URLs or client configs. After changing the server port, update application endpoints, health checks, firewalls, monitoring, and dependent tooling.

### 5.1. Multiple PostgreSQL Instances on One Host

A host can run PostgreSQL 15 and PostgreSQL 16 simultaneously, yet two processes cannot bind the exact same IP address and TCP port without separate configuration.

Example:

```text
Instance A:
  data_directory = /srv/pg15/data
  listen_addresses = '127.0.0.1'
  port = 5432

Instance B:
  data_directory = /srv/pg16/data
  listen_addresses = '127.0.0.1'
  port = 5433
```

Here each instance has its own data directory and port. Values are illustrative only. Ensure the **matching binary/major version for each data directory**, separate file permissions, and no port or socket path collisions at startup.

### 5.2. Port Already in Use Error

When the port is already occupied by another process, logs may contain:

```text
LOG:  could not bind IPv4 address "...": Address already in use
HINT: Is another postmaster already running on port 5432?
```

On Linux:

```bash
ss -lntp
```

On Windows PowerShell:

```powershell
Get-NetTCPConnection -LocalPort 5432 -State Listen
```

Identify the process and instance owning the port before deciding to change ports or stop services. Never kill a process just because it occupies `5432` without confirming whether it is a production PostgreSQL instance.

## 6. listen_addresses and port Require Restart, Not Just Reload

`listen_addresses` and `port` are bound when the PostgreSQL process starts. Changing them in configuration **does not take effect via reload alone**.

Example:

```conf
listen_addresses = 'localhost,10.20.30.11'
port = 5433
```

If you only run:

```sql
SELECT pg_reload_conf();
```

PostgreSQL recognizes that those changes require a **restart**, yet continues listening on the old values in the running process.

### 6.1. Checking pending_restart

```sql
SELECT
    name,
    setting,
    context,
    source,
    sourcefile,
    pending_restart
FROM pg_settings
WHERE name IN ('listen_addresses', 'port', 'max_connections')
ORDER BY name;
```

These parameters typically have `context = 'postmaster'`. If `pending_restart = true` after reloading configuration files, the server has detected changes requiring a restart.

**`pg_reload_conf() = true` only indicates the reload signal was sent successfully**; it does not prove the listener switched to the new port/IP.

On live servers, restarts must be performed via the appropriate management tool (systemd, Windows Service, container orchestrator, or managed database provider) within an approved maintenance window. Restarting drops active connections and interrupts open transactions.

### 6.2. Multiple Configuration Sources

Current values may come from `postgresql.conf`, `include` files, `postgresql.auto.conf` managed by `ALTER SYSTEM`, or startup command-line flags. Therefore, never inspect a single file and conclude that is what the server uses.

```sql
SHOW config_file;

SELECT
    name, setting, source, sourcefile,
    sourceline, pending_restart
FROM pg_settings
WHERE name IN ('listen_addresses', 'port', 'max_connections');
```

`sourcefile`/`sourceline` may be hidden from accounts lacking sufficient privileges. When administrative visibility is needed, use a policy-compliant monitoring role rather than granting superuser to applications.

## 7. Opening the Listener Does Not Grant Login: pg_hba.conf

A complete network setup coordinates multiple layers:

```text
listen_addresses = where to listen?
port             = which port to listen on?
firewall         = which hosts can reach the port?
pg_hba.conf      = which connections are accepted and how are they authenticated?
user/password    = how does the user prove identity?
GRANT CONNECT    = is the role allowed into the target database?
```

Suppose PostgreSQL listens on internal IP `10.20.30.11`, and the application lives in subnet `10.20.30.0/24`:

```conf
# postgresql.conf
listen_addresses = 'localhost,10.20.30.11'
port = 5432
```

A matching authentication rule might be:

```conf
# pg_hba.conf
# TYPE  DATABASE  USER      ADDRESS          METHOD
host    appdb     app_user  10.20.30.0/24    scram-sha-256
```

This line instructs PostgreSQL to accept matching TCP connections for the named database, user, and client network **when authentication succeeds**. Real network configuration and role/database setup are still required; examples do not replace proper TLS and firewall design.

### 7.1. The First Matching Rule Determines Authentication

`pg_hba.conf` is evaluated **in line order**; the first matching rule is selected. PostgreSQL does not continue trying later rules simply because authentication under the first matching rule failed.

Two-line example:

```conf
host  appdb  app_user  10.20.30.0/24  scram-sha-256
host  all    all       0.0.0.0/0      reject
```

Client `app_user` from the permitted subnet matches the first line. Connections failing to match any earlier permissive line are rejected by the second line. However, broad rules such as `0.0.0.0/0` should be used carefully, and IPv6 traffic must be considered separately.

**Never use `trust` for broad networks** as a quick workaround for password issues. `trust` lets matching clients log in without password verification, creating severe risk if scoped improperly.

### 7.2. local, host, and hostssl

| HBA Type | Applies To |
| --- | --- |
| `local` | Connections over Unix-domain sockets. |
| `host` | TCP connections; can match with or without TLS depending on configuration. |
| `hostssl` | TCP connections using SSL/TLS. |
| `hostnossl` | TCP connections without SSL/TLS. |

Example:

```conf
# Unix socket for local administration; method must fit OS user model.
local    postgres    postgres                      peer

# TCP with TLS for application from a specific subnet.
hostssl  appdb       app_user   10.20.30.0/24      scram-sha-256
```

This illustrates a Unix setup; `peer` applies only under supported Unix-domain socket conditions. For `hostssl` to work, PostgreSQL must have TLS configured with valid certificates and keys.

### 7.3. Inspect HBA Before Concluding a Listener Error

```sql
SHOW hba_file;

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

`pg_hba_file_rules` helps catch parse errors in the HBA file and review rules in order. Viewing access may be restricted. Also inspect logs and test connections from the application's **actual source address**.

Changes to `pg_hba.conf` can usually be reloaded without restarting the entire server, noting that platform reload mechanisms can differ. By contrast, changing `listen_addresses`/`port` still requires a restart.

### 7.4. GRANT CONNECT on the Database

Even after authentication succeeds, `CONNECT` privilege on the target database remains part of access control.

```sql
-- Illustrative only for environments where privilege management is permitted.
GRANT CONNECT ON DATABASE appdb TO app_user;
```

PostgreSQL typically grants `CONNECT` to `PUBLIC` by default on new databases. Therefore, an individual `GRANT CONNECT` may not change effective access if the role already inherits it from `PUBLIC`.

To strictly lock down a database to specific roles, an administrator may consider revoking the default grant:

```sql
-- WARNING: affects many accounts; use only after auditing dependencies.
REVOKE CONNECT ON DATABASE appdb FROM PUBLIC;
GRANT CONNECT ON DATABASE appdb TO app_user;
```

Do not run this arbitrarily in production, as it can cut off monitoring, migration, backup tools, or other applications.

## 8. Actively Testing Connections from the Client

A `psql` command with explicit host and port:

```bash
psql -X -h 10.20.30.11 -p 5432 -U app_user -d appdb
```

Meaning of flags:

- `-X`: skips reading `psqlrc` startup files during diagnostics.
- `-h`: target address; in this example, the PostgreSQL server's IP.
- `-p`: server port.
- `-U`: database role.
- `-d`: target database.

After logging in:

```sql
SELECT
    current_database(),
    current_user,
    inet_server_addr(),
    inet_server_port(),
    pg_backend_pid();
```

If you prefer not to enter an interactive shell:

```bash
psql -X -h 10.20.30.11 -p 5432 -U app_user -d appdb \
  -c "SELECT current_database(), current_user, pg_backend_pid();"
```

The trailing `\` line continuation is Unix-shell syntax; PowerShell and CMD use different continuation characters. Never pass passwords directly on the command line or inside logged URLs; use an appropriate secrets manager.

### 8.1. pg_isready Only Confirms Endpoint Readiness

```bash
pg_isready -h 10.20.30.11 -p 5432
```

Example output:

```text
10.20.30.11:5432 - accepting connections
```

`pg_isready` distinguishes whether an endpoint is responding and accepting connections, temporarily rejecting connections, or unreachable. **It does not prove the application's username, password, or database is valid.** Follow up by testing with the actual account and database used by the application.

Common exit codes are `0` (accepting connections), `1` (server responded but rejected), `2` (no response), and `3` (invalid arguments/unable to attempt).

## 9. max_connections: Limiting Concurrent Client Sessions

In PostgreSQL's traditional process model, each client connection generally corresponds to a server-managed backend process. Each connection consumes resources: memory, transaction tracking structures, file descriptors, and scheduling overhead.

`max_connections` controls the **maximum number of concurrent connections configured for the server**, while a portion of slots is reserved for privileged accounts.

```sql
SHOW max_connections;
```

The default is commonly `100`, though actual values may be adjusted by administrators or service providers.

Example:

```conf
max_connections = 150
```

The number 150 does not mean the server will run fast with 150 heavy concurrent queries. It is a **cap on session creation**, not an optimal limit for CPU concurrency, queries per second, or transaction throughput.

### 9.1. Why Shouldn't You Set It Huge Just to Avoid Errors?

Every connection maintains its own state; high connection counts increase overhead for both PostgreSQL and applications. If hundreds of connections execute queries concurrently:

- CPUs spend time context-switching across many backends.
- Memory consumed by sorting/hashing across many queries can surge sharply.
- Lock contention and I/O queues can grow.
- Memory footprint, response latency, and stability can degrade.

Thus, when slots run out, the right fix may be **shrinking pool sizes, fixing connection leaks, or introducing a pooler**, rather than blindly setting `max_connections = 2000`.

### 9.2. max_connections Requires Restart

`max_connections` belongs to the `postmaster` group; updating config and running only `pg_reload_conf()` **is insufficient to raise the active slot limit**.

```sql
SELECT name, setting, context, pending_restart
FROM pg_settings
WHERE name = 'max_connections';
```

After editing and reloading, `pending_restart` may become `true`. Restart the instance following operational procedures for the setting to apply.

In topologies with standbys, changing `max_connections` can also interact with parameter compatibility requirements on standbys. Review docs for your major version and replication/HA runbooks before changing it.

## 10. Reserved Connection Slots for Administration and Operations

If applications occupy every connection slot, administrators could be locked out when trying to diagnose issues. PostgreSQL provides mechanisms to reserve slots for special connections.

### 10.1. superuser_reserved_connections

```sql
SHOW superuser_reserved_connections;
```

In many PostgreSQL releases, the default is `3`. When remaining free slots drop to the reserved threshold, regular connections are refused to preserve login capacity for superusers.

Illustrative example:

```text
max_connections = 100
superuser_reserved_connections = 3

97 slots: generally available to non-superuser connections
 3 slots: held back to support privileged superuser connections
```

This is a **conceptual allocation model**. Actual slot granting conditions depend on version, connection type, and server state; never treat a total of 100 as "100 slots all available to the application pool."

### 10.2. reserved_connections Starting in PostgreSQL 16

PostgreSQL 16 introduced `reserved_connections` alongside the `pg_use_reserved_connections` system role to reserve a pool of slots for authorized non-superuser roles, in addition to slots reserved for superusers.

On supporting servers:

```sql
SHOW reserved_connections;
SHOW superuser_reserved_connections;
SHOW max_connections;
```

On PostgreSQL 14 or 15, `SHOW reserved_connections` will fail because the parameter does not exist yet; do not copy commands from newer major-version manuals and assume an older server is misconfigured.

Hypothetical allocation example on a supporting PostgreSQL version:

```text
max_connections                = 100
reserved_connections           =   5
superuser_reserved_connections =   3
---------------------------------------
Max regular slots in model          92
Reserved slots for permitted roles   5
Final slots for superusers           3
```

When free slots drop low, roles permitted to use reserved slots can still log in per policy, while regular connections are rejected. When free slots drop even further, the remaining slots are reserved for superusers.

If you need to grant access to reserved slots on a supporting server:

```sql
-- Example only for an existing, approved operations role.
GRANT pg_use_reserved_connections TO ops_operator;
```

This is a **special privilege**, not something to grant to every application worker. Allowing application pools to consume reserved slots defeats their recovery purpose during overload.

### 10.3. Connection Slots and Availability Limits

Reserved slots only protect partial connectivity for administrative intervention. They do not solve:

- Queries blocked on locks for hours.
- Exhausted CPU and RAM.
- Full disks preventing WAL writes.
- Network or proxy failures.

When underlying resources are saturated, administrators may be able to log in yet still experience severe slowness. Reserved slots are one layer in an operational strategy, not a silver bullet for every outage.

## 11. Connection Limits per Role and per Database

`max_connections` is a server-wide setting. Sometimes you need to cap a single account or database so one service cannot exhaust all slots.

### 11.1. Limiting a Role

Assuming login role `app_service` already exists:

```sql
ALTER ROLE app_service CONNECTION LIMIT 20;
```

PostgreSQL then enforces the role's regular session limit per applicable rules; new connections exceeding the limit may be rejected. Not every connection type—especially privileged superuser connections—is constrained identically to regular connections.

To remove the custom limit:

```sql
ALTER ROLE app_service CONNECTION LIMIT -1;
```

`-1` means **no role-specific connection limit**; it does not disable server-wide `max_connections`.

### 11.2. Limiting a Database

```sql
ALTER DATABASE appdb CONNECTION LIMIT 60;
```

This limit constrains total connections to database `appdb` under PostgreSQL's rules, regardless of how many application roles connect to it.

To remove the custom limit:

```sql
ALTER DATABASE appdb CONNECTION LIMIT -1;
```

These are distinct limit layers:

| Limit Level | Example | How to Interpret |
| --- | --- | --- |
| Server | `max_connections = 100` | Total connection budget managed by the server. |
| Role | `app_service CONNECTION LIMIT 20` | Session quota for one login role per applicable rules. |
| Database | `appdb CONNECTION LIMIT 60` | Session quota for one database per applicable rules. |

For example, even when the server has free slots, if `app_service` hits its cap of 20, the application still receives connection errors. Increasing `max_connections` will not resolve a role limit when the role limit is the bottleneck.

### 11.3. Inspecting Current Limits

Administrators can query catalogs:

```sql
SELECT
    rolname,
    rolcanlogin,
    rolconnlimit
FROM pg_roles
WHERE rolname IN ('app_service', 'report_reader', 'ops_operator')
ORDER BY rolname;

SELECT
    datname,
    datconnlimit
FROM pg_database
WHERE datallowconn
ORDER BY datname;
```

`-1` indicates no dedicated limit. Role/database limits are checked during connection establishment and carry certain exceptions; do not treat them as a **millisecond-exact arbiter** under intense simultaneous login bursts.

Changing a limit does not automatically terminate existing sessions. If a database currently has more sessions than the new cap, manage existing sessions and observe the effect on subsequent connection attempts.

## 12. Viewing Existing Sessions with pg_stat_activity

`pg_stat_activity` is essential when investigating exhausted connection slots, excessive idle sessions, or active queries.

### 12.1. Counting Client Backends

```sql
SELECT count(*) AS client_sessions
FROM pg_stat_activity
WHERE backend_type = 'client backend';
```

Other rows in `pg_stat_activity` can represent background processes or parallel workers rather than user JDBC sessions. Counting all rows and comparing directly to `max_connections` can be misleading.

Group by database, user, and state:

```sql
SELECT
    datname,
    usename,
    state,
    count(*) AS session_count
FROM pg_stat_activity
WHERE backend_type = 'client backend'
GROUP BY datname, usename, state
ORDER BY session_count DESC, datname, usename, state;
```

Example result shape:

| datname | usename | state | session_count |
| --- | --- | --- | ---: |
| appdb | app_service | idle | 42 |
| appdb | app_service | active | 8 |
| appdb | report_reader | idle | 3 |
| postgres | ops_operator | active | 1 |

In this example, `app_service` holds 50 client sessions, yet only 8 are `active` at the sample instant. This typically reflects a connection pool keeping connections warm for reuse, not necessarily 50 queries running concurrently.

### 12.2. Distinguishing idle and idle in transaction

Common states:

| `state` | Meaning |
| --- | --- |
| `active` | Backend is executing a query. |
| `idle` | Session is connected and not executing a query at sample time. |
| `idle in transaction` | A transaction is open, yet the client is not currently running a query. |
| `idle in transaction (aborted)` | The transaction encountered an error and has not yet rolled back or ended. |

`idle` is not inherently an error: pools deliberately retain idle connections to avoid handshake overhead. By contrast, prolonged `idle in transaction` sessions can hold locks, pin old snapshots, block `VACUUM` from reclaiming dead tuples, or tie up resources longer than necessary.

Find sessions with open transactions:

```sql
SELECT
    pid,
    usename,
    datname,
    application_name,
    client_addr,
    state,
    xact_start,
    now() - xact_start AS transaction_age,
    wait_event_type,
    wait_event
FROM pg_stat_activity
WHERE backend_type = 'client backend'
  AND xact_start IS NOT NULL
ORDER BY xact_start;
```

The view hides certain details of other sessions if your role lacks monitoring privileges. For approved monitoring, PostgreSQL provides roles such as `pg_monitor` or `pg_read_all_stats` so you do not have to grant superuser indiscriminately.

### 12.3. Session Counts per Database

```sql
SELECT
    datname,
    numbackends
FROM pg_stat_database
WHERE datname IS NOT NULL
ORDER BY numbackends DESC;
```

`numbackends` shows the current number of backends connected to each database per the stats view. It is useful for quickly spotting which database holds the most connections, though you still need `pg_stat_activity` to see roles, applications, and states.

### 12.4. Inspecting Connection Sources

```sql
SELECT
    pid,
    datname,
    usename,
    application_name,
    client_addr,
    client_port,
    backend_start,
    state
FROM pg_stat_activity
WHERE backend_type = 'client backend'
ORDER BY backend_start DESC;
```

`client_addr` and `client_port` help trace TCP connection origins. Over Unix sockets, some fields may be `NULL`; behind a proxy or pooler, client addresses may reflect the **proxy/pooler** rather than the end application host.

Setting `application_name` is very helpful operationally: instead of every session showing a generic default, you can distinguish `checkout-api`, `inventory-worker`, `migration-job`, and `reporting`.

## 13. Estimating Connection Budgets Across Multiple Applications

A common cause of `too many clients` is summing connections across **all replicas** without matching the server's budget.

Suppose:

```text
PostgreSQL:
  max_connections = 100

Checkout API:
  3 replicas * maximumPoolSize 20 = 60 potential connections

Inventory Worker:
  2 replicas * maximumPoolSize 10 = 20 potential connections

Reporting / maintenance:
  may use another 5 connections

Theoretical client peak above = 60 + 20 + 5 = 85
```

85 does not yet include other tools connecting to the same server, rolling deployments where **two pod versions overlap briefly**, burst pool expansion, administrators, monitoring, or failover headroom. If all replicas raise pool size from 20 to 30, Checkout API alone could open `3 * 30 = 90` connections.

Therefore:

\[
\text{Expected Peak Connections} =
\sum_i (\text{replicas}_i \times \text{max pool}_i)
+ \text{other direct sessions}
\]

For a safe configuration, expected peak connections must **remain below the truly available client budget**, after accounting for reserved slots and operational spikes.

### 13.1. Pool Size Does Not Equal Concurrent Requests

For example, 200 concurrent HTTP requests do not require 200 PostgreSQL connections:

- A request may be authenticating, waiting on network, reading cache, or running Java logic.
- Each request holds a connection only during the portion of time spent querying the database.
- The pool caps DB connections and queues remaining requests briefly until a connection frees up.

A pool that is too small makes the application wait longer; a pool that is too large can overload the database. Measure **connection hold time**, SQL latency, concurrent queries, lock waits, and server resources rather than sizing pools equal to HTTP thread counts.

### 13.2. Example HikariCP Configuration in a Java Application

```properties
# Spring Boot / HikariCP example, not optimal values for every workload.
spring.datasource.url=jdbc:postgresql://db.internal.example.test:5432/appdb
spring.datasource.username=app_service
spring.datasource.hikari.maximum-pool-size=15
spring.datasource.hikari.minimum-idle=3
spring.datasource.hikari.connection-timeout=30000
```

`maximum-pool-size` limits connections held by **one pool instance**; if the service runs six pods, the budget is not 15, but up to `6 * 15 = 90` for that service alone.

HikariCP's `connection-timeout` is how long a client waits to borrow a connection from the pool before throwing an error (milliseconds in this example); it is **not** PostgreSQL's `statement_timeout` or the TCP connect timeout to the host.

Credentials should come from a secret manager or vault—never store real passwords in configuration files committed to a repository.

## 14. Connection Pooling and PgBouncer

In PostgreSQL's traditional architecture, opening too many direct connections incurs high overhead. **Connection pooling** allows reusing connections instead of opening and closing one per HTTP request.

Two common layers:

1. **In-application pools:** Java's HikariCP keeps a bounded pool of connections to the database.
2. **External poolers:** PgBouncer accepts many client connections and multiplexes them onto a controlled number of server connections.

```text
                  4 Application replicas
                    /      |      \
                   v       v       v
                 JDBC / Hikari pools
                         |
                         v
                      PgBouncer
                  (pool server connections)
                         |
                         v
                 PostgreSQL primary
              bounded max_connections
```

### 14.1. Session Pooling vs. Transaction Pooling

| Mode | Concept | Caveats |
| --- | --- | --- |
| Session pooling | One server connection stays assigned to a client for the entire session. | Reduces connection creation overhead, but achieves lower sharing when many clients are idle. |
| Transaction pooling | Assigns a server connection to a client only for the duration of one transaction, then returns it to the pool. | Optimizes backend count for suitable workloads, though features relying on session state may require design changes. |

With transaction pooling, applications must pay attention to session state such as temporary tables, session-level `SET` parameters, session-level advisory locks, `LISTEN/NOTIFY`, cursors, or prepared statements; exact support depends on the feature and PgBouncer version. Never assume switching from direct connections to transaction pooling preserves all session behaviors unchanged.

### 14.2. Poolers Do Not Create Extra CPU or I/O Capacity

PgBouncer helps control server connection counts and reduce overhead, yet it cannot make a single PostgreSQL server execute unlimited SQL concurrently. When too many heavy transactions arrive, the pooler **queues** requests waiting for a backend. Monitor queue wait latency, timeouts, CPU, locks, and I/O.

If the goal is higher throughput, combine SQL/index tuning, shorter transaction times, read replicas, or architectural adjustments. Pooling is only one piece of capacity planning.

## 15. Timeouts and Session Lifecycle

Not every open connection is doing useful work. PostgreSQL provides timeouts to bound risky situations.

| Parameter | General Meaning |
| --- | --- |
| `idle_in_transaction_session_timeout` | Terminates sessions left idle too long while a transaction remains open. |
| `idle_session_timeout` | Terminates sessions idle outside a transaction; use carefully with connection pools. |
| `statement_timeout` | Limits execution duration of a statement within its applied scope. |
| `lock_timeout` | Limits time spent waiting to acquire a lock. |
| `authentication_timeout` | Limits time allowed to complete connection authentication. |
| `tcp_keepalives_idle` and related keepalive settings | Affects detection of dead TCP connections per OS and configuration. |

Check:

```sql
SHOW idle_in_transaction_session_timeout;
SHOW idle_session_timeout;
SHOW statement_timeout;
SHOW lock_timeout;
```

Do not blindly set all timeouts to the same number without understanding their roles:

- `statement_timeout` does not directly resolve a pool holding too many `idle` connections.
- `idle_in_transaction_session_timeout` reduces risk from hanging transactions, though it can cause errors if an application legitimately holds a transaction open too long.
- `idle_session_timeout` can close idle connections that a pool expects to reuse; if the pool fails to detect and discard dead connections, the application may experience intermittent failures.

When enabling timeouts, coordinate settings with JDBC/pooler configuration and test application retry behavior.

## 16. Diagnosing Common Connection Errors

The following errors look similar at the application layer yet originate from different layers.

| Symptom | Primary Possibility | What to Check |
| --- | --- | --- |
| `Connection refused` | No listener on target address/port, or system actively rejected it. | Server running, `listen_addresses`, `port`, firewall, and port mapping. |
| TCP connect timeout | Network path blocked, unroutable, or endpoint unresponsive. | DNS, routing, firewall, security group, proxy/load balancer. |
| `no pg_hba.conf entry` | No matching HBA rule for host/user/database/TLS. | `hba_file`, IPv4/IPv6 rules, rule ordering, SSL mode. |
| `password authentication failed` | Authentication failed. | Password/secret, user, HBA method, account provisioning. |
| `remaining connection slots are reserved` | Regular slots exhausted; only privileged slots remain. | `max_connections`, reserved slots, pool sizes, `pg_stat_activity`. |
| `too many clients already` | Connection limit reached. | Session count, pool leak, server config, and concurrency demand. |
| `too many connections for role` | Role `CONNECTION LIMIT` reached. | `pg_roles.rolconnlimit`, sessions for that role. |
| `too many connections for database` | Database connection limit reached. | `pg_database.datconnlimit`, `pg_stat_database.numbackends`. |
| JDBC pool timeout | Unable to borrow connection from pool before timeout. | Hikari active/idle/pending metrics, slow SQL, connection leak, server saturation. |

Exact messages vary across PostgreSQL, JDBC, PgBouncer, and error-wrapping libraries. Always preserve the **SQLSTATE, original message, and timestamp** to isolate the root cause.

### 16.1. "Connection refused" Is Not Necessarily a pg_hba.conf Error

`pg_hba.conf` is evaluated only after a client reaches PostgreSQL at the connection stage. If no process is listening on that address and port, adding an HBA entry will not create a listener.

Sequence:

1. Verify the PostgreSQL process is running.
2. Verify active `listen_addresses` and `port`.
3. Inspect listening sockets in the OS or container.
4. Check routing and firewalls.
5. Once TCP succeeds, investigate HBA and authentication if connections are still rejected.

### 16.2. Reserved Slots Error

If the server reports that remaining slots are reserved for superusers or privileged roles, **regular connections have hit capacity**. Do not configure applications to log in as superuser to bypass the limit.

Instead, administrators should:

- Inspect `pg_stat_activity` to see which role/database/service holds excessive sessions.
- Check connection growth following rollouts or autoscaling.
- Check whether connection pools are leaking or holding sessions too long.
- Reduce peak connection openings or throttle requests per runbook.
- Consider raising `max_connections` only after evaluating resources and scheduling a restart.

### 16.3. When the Timeout Is a Client Pool Error

A message like "Connection is not available, request timed out" from HikariCP usually means a thread could not borrow a connection from the pool in time. It **does not prove PostgreSQL rejected the connection**: all server connections in the pool may simply be busy executing slow queries or holding long transactions.

Correlate pool `active`, `idle`, `pending`, and borrow-time metrics with server state. Raising max pool size may temporarily hide the error while shifting even heavier load onto PostgreSQL.

## 17. Using pg_stat_ssl to Observe TLS Connections

When PostgreSQL serves over a network, TLS protects data in transit and can participate in authentication policies.

Check server configuration:

```sql
SHOW ssl;
```

With appropriate viewing privileges, inspect session TLS status:

```sql
SELECT
    a.pid,
    a.usename,
    a.client_addr,
    a.application_name,
    s.ssl,
    s.version,
    s.cipher
FROM pg_stat_activity AS a
JOIN pg_stat_ssl AS s
  ON s.pid = a.pid
WHERE a.backend_type = 'client backend'
ORDER BY a.pid;
```

`s.ssl = true` shows that the corresponding PostgreSQL session uses SSL/TLS. If a proxy terminates TLS in front of PostgreSQL, security across each hop must be evaluated separately: TLS from client to proxy **does not automatically prove** the hop from proxy to PostgreSQL also uses TLS.

### verify-full in Applications

With PostgreSQL clients/libpq, `sslmode=verify-full` requires verifying both the certificate chain and hostname per supported TLS rules. Applications need the proper CA certificate and matching hostname to connect successfully.

Example URL:

```text
jdbc:postgresql://db.internal.example.test:5432/appdb?sslmode=verify-full
```

This URL illustrates the option only; configure trust material and server certificates matching your PostgreSQL JDBC Driver. Never switch to `sslmode=disable` just to silence certificate errors in environments requiring transport encryption.

## 18. Containers, Docker, and Kubernetes: Internal vs. External Ports

### 18.1. Docker Port Mapping

Suppose PostgreSQL inside a container listens on `0.0.0.0:5432`, and you want only the host machine to access it via loopback:

```text
Docker host 127.0.0.1:15432
              |
       port forwarding
              |
              v
Container 0.0.0.0:5432
```

Illustrative Docker syntax:

```bash
docker run --name pg-lab \
  -e POSTGRES_PASSWORD=REPLACE_WITH_LAB_SECRET \
  -p 127.0.0.1:15432:5432 \
  postgres:16
```

This command is for lab experimentation only: the environment variable uses a placeholder and can be exposed in shell history or container metadata. Never pass real production secrets this way. Follow your platform's secrets management and persistent volume practices.

Inside the container, PostgreSQL still listens on port `5432`; from the host, clients connect via `127.0.0.1:15432`. Changing port mapping **does not require changing `port` inside PostgreSQL**.

`listen_addresses = 'localhost'` inside a container listens only on loopback **inside the container**, so port forwarding from the host via the container's network interface may fail to reach it. Configure both the listener address and network policies properly rather than just adding `-p`.

### 18.2. Kubernetes Services

A PostgreSQL Pod may listen on `5432`, while a Kubernetes Service provides DNS and a port for clients:

```text
App Pod
   |
   v
postgres.database.svc.cluster.local:5432
   |
   v
Kubernetes Service -> PostgreSQL Pod:5432
```

Here:

- The Service `port` may differ from the Pod's `targetPort`.
- A NetworkPolicy may restrict allowed source pods.
- PostgreSQL still needs an appropriate listener and HBA rules matching the addresses it actually observes—which could be Pod IPs or NAT/proxy addresses.
- When using a PostgreSQL Operator, `listen_addresses` and `max_connections` are typically managed via custom resources rather than editing files directly inside a Pod.

**Do not look at `SHOW port` and assume external clients must use that exact port.** Clients must connect to the port exposed by their target endpoint after passing through configured forwarding layers.

## 19. Managed PostgreSQL and Administrative Account Limits

On managed PostgreSQL services, the provider may control `listen_addresses`, port exposure, certificates, connection limits, or parameter modification privileges.

You can still run:

```sql
SHOW listen_addresses;
SHOW port;
SHOW max_connections;
```

but displayed values and editability depend on parameter groups, service-level server config, or granted admin privileges.

For example, when connections from another VM are refused:

1. Verify the endpoint and port published by the provider.
2. Check network access rules, security groups, and private networking.
3. Verify TLS settings and credentials.
4. Check service-specific connection limits.
5. Use the provider's console/API to adjust supported parameters.

Do not assume you can run `ALTER SYSTEM` or edit physical `postgresql.conf` files on a managed database the same way as a self-managed PostgreSQL server.

## 20. Parameters and Queries Commonly Checked Together

A **read-only** script can support baseline diagnostics:

```sql
SELECT
    name,
    setting,
    unit,
    context,
    source,
    pending_restart
FROM pg_settings
WHERE name IN (
    'listen_addresses',
    'port',
    'unix_socket_directories',
    'max_connections',
    'superuser_reserved_connections',
    'reserved_connections',
    'ssl',
    'authentication_timeout',
    'idle_in_transaction_session_timeout',
    'idle_session_timeout'
)
ORDER BY name;
```

An advantage of querying `pg_settings` over a series of `SHOW` statements is that **if an older major version lacks `reserved_connections`, the query still returns all existing parameters** instead of failing on an unsupported `SHOW`.

Inspect current connections:

```sql
SELECT
    datname,
    usename,
    state,
    count(*) AS sessions
FROM pg_stat_activity
WHERE backend_type = 'client backend'
GROUP BY datname, usename, state
ORDER BY sessions DESC;
```

Inspect per-role limits:

```sql
SELECT rolname, rolconnlimit
FROM pg_roles
WHERE rolcanlogin
ORDER BY rolname;
```

Inspect per-database limits:

```sql
SELECT datname, datconnlimit
FROM pg_database
WHERE datallowconn
ORDER BY datname;
```

A thorough connection report records the **measurement timestamp**, **instance and port**, **configured maximum**, **actual session count**, **breakdown by application/role**, and **slots reserved for operations**.

## 21. Controlled Configuration Changes

When opening access from a new application host or increasing session limits, avoid changing multiple parameters simultaneously without a clear goal.

### 21.1. Listener Change Workflow

Suppose a new application resides in `10.20.30.0/24` and PostgreSQL currently listens only on localhost.

1. Confirm the server is running and check `SHOW config_file`/`SHOW listen_addresses`.
2. Confirm IP `10.20.30.11` actually belongs to a server network interface.
3. Choose the narrowest sufficient `listen_addresses`, e.g., `'localhost,10.20.30.11'`.
4. Create firewall/security group rules permitting only required application sources to the PostgreSQL port.
5. Add appropriate HBA/TLS authentication rules for the target database and role.
6. Schedule a restart since `listen_addresses` belongs to `postmaster`.
7. After restarting, verify `SHOW listen_addresses`, OS listeners, and connectivity from the actual application host.
8. Monitor application behavior and logs, keeping a rollback plan ready if connectivity breaks.

Example configuration:

```conf
listen_addresses = 'localhost,10.20.30.11'
port = 5432
```

Matching HBA remains a separate step:

```conf
hostssl  appdb  app_user  10.20.30.0/24  scram-sha-256
```

Not every environment allows editing `postgresql.conf` directly; managed services and operators require using their native configuration mechanisms.

### 21.2. max_connections Change Workflow

1. Measure client sessions and peak demand over time, not just a single instant.
2. Audit each pool/replica and connection creation spikes during rollouts.
3. Determine whether slot exhaustion stems from oversized pools, connection leaks, or genuine load growth.
4. Consider tuning pools or adding PgBouncer before raising the hard limit.
5. If an increase is still required, calculate RAM and related resource usage, and account for standby/HA members.
6. Update the parameter and schedule a restart.
7. After restarting, confirm the value and monitor memory, latency, and session states.

Illustrative example only:

```conf
max_connections = 150
superuser_reserved_connections = 3
```

On PostgreSQL 16+, consider adding `reserved_connections` for operational roles where appropriate. Reserved-slot parameters typically also follow the corresponding configuration/restart workflow.

Never raise `max_connections` to an arbitrary huge number merely to silence pool timeout errors; doing so can degrade memory usage and concurrency efficiency.

## 22. Operational Scenarios and Reasoning

### Scenario A: Local Connects, Remote Fails

**Situation:** On the database server, `psql -h 127.0.0.1` succeeds; from the application host, `psql -h 10.20.30.11` returns `connection refused`.

**Analysis:** PostgreSQL may be listening only on loopback, the expected IP/port is unbound, or the network layer rejects it. Check `SHOW listen_addresses`, `SHOW port`, and OS listeners; next, check firewalls and HBA. Adding an HBA line without binding the listener to the right IP will not fix this.

### Scenario B: Logs Report FATAL: no pg_hba.conf entry

**Situation:** PostgreSQL is listening, yet clients from a new subnet are rejected.

**Analysis:** The client reached PostgreSQL's connection handler. Inspect database, role, client source IP, SSL mode, and HBA rules in order. Raising `max_connections` will not fix a missing HBA rule.

### Scenario C: After Autoscaling, Application Reports too many clients

**Situation:** Previously there were two application replicas, each with pool size 20; after autoscaling to six replicas with unchanged pool settings, errors appear.

**Analysis:** Peak potential connections jumped from `2 * 20 = 40` to `6 * 20 = 120`, before counting monitoring/jobs and reserved slots. With `max_connections = 100`, the system runs out of slots. Reduce per-replica pool size or cap replicas, evaluate PgBouncer, or perform controlled capacity adjustments.

### Scenario D: max_connections Has Headroom, Yet One Service Cannot Log In

**Situation:** Server has `max_connections = 150` and only ~70 client sessions, yet one account reports exceeding its session limit.

**Analysis:** Check `rolconnlimit` or `datconnlimit`. If that role is capped at 10 sessions or the database at 60, that is the bottleneck. The server-wide limit is not the only limit.

### Scenario E: Edited port and Reloaded, Yet Application Still Must Use Old Port

**Situation:** Changed `port = 5433` and ran `SELECT pg_reload_conf()`, yet the server still listens on `5432`.

**Analysis:** `port` requires a restart. Inspect `pg_settings.context` and `pending_restart`, schedule a restart, and verify afterward. Reloading HBA and restarting the listener operate on different scopes.

### Scenario F: Pool Holds Many idle Sessions

**Situation:** `pg_stat_activity` shows dozens of `idle` sessions for one user while DB load is light.

**Analysis:** Many idle sessions can be normal connection pool behavior, though oversized pools still consume slots. Compare active/idle/pending metrics, replica counts, and connection idle lifetimes before declaring every idle session a leak.

### Scenario G: idle in transaction Sessions Increasing

**Situation:** Several sessions show `state='idle in transaction'` with old `xact_start` timestamps.

**Analysis:** The application is likely opening transactions and running slow work or forgetting to commit/roll back. Such sessions can hold locks/snapshots, delay `VACUUM`, and block queries. Fix transaction boundaries in application code; `idle_in_transaction_session_timeout` is a protective guardrail, not a substitute for fixing the root cause.

### Scenario H: TCP Check Passes, Yet Application Fails TLS

**Situation:** `pg_isready` reports accepting connections, while JDBC with `sslmode=verify-full` reports a certificate error.

**Analysis:** The port and PostgreSQL endpoint are reachable, yet the certificate mismatches the hostname, the CA is untrusted, or TLS termination is misconfigured. Inspect certificates and the TLS path; never disable certificate verification to make the error vanish without assessing risk.

## 23. Practice Exercises

The exercises below primarily use read-only queries. For `ALTER ROLE`, `ALTER DATABASE`, or `postgresql.conf` edits, run them only in a lab where you have admin privileges and can restore configuration.

### Exercise 1. Inspect the Server's Listener

```sql
SHOW listen_addresses;
SHOW port;
SHOW unix_socket_directories;
```

**Question:** If `listen_addresses = 'localhost'` and `port = 5432`, can an application on another machine connect directly to the database server's internal IP?

**Answer:** Not with that configuration alone. PostgreSQL typically listens only on loopback. Configure the listener on the appropriate IP, verify firewall, HBA, and authentication, and restart after changing `listen_addresses`.

### Exercise 2. Distinguish TCP and Unix Sockets

Run sequentially on a Linux host with a PostgreSQL lab:

```bash
psql -U app_user -d appdb
psql -h 127.0.0.1 -p 5432 -U app_user -d appdb
```

**Task:** Observe the authentication behavior and `\conninfo`. If they differ, explain why.

**Hint:** Connecting without `-h` typically uses a Unix socket and `local` HBA rules; connecting to `127.0.0.1` uses TCP and `host`/`hostssl` rules.

### Exercise 3. Calculate Connection Budget

A server has `max_connections = 100`, `superuser_reserved_connections = 3`, and on a supporting PostgreSQL version `reserved_connections = 5`. An application runs three replicas with max pool 30 each, plus a batch job with max pool 10.

**Question:** Does this pool setup risk exhausting connection slots?

**Analysis:** `3 * 30 + 10 = 100` potential connections. Meanwhile, regular slots must leave room for reserved slots and other clients. This design is prone to rejections during peak overlap; reduce pool budgets, account for monitoring/migrations, and consider a pooler.

### Exercise 4. Identify Connection States

```sql
SELECT
    state,
    count(*) AS sessions
FROM pg_stat_activity
WHERE backend_type = 'client backend'
GROUP BY state
ORDER BY sessions DESC;
```

**Task:** Distinguish `active`, `idle`, and `idle in transaction`. Why can't you assume every `idle` connection is dangerous?

**Hint:** Pools intentionally keep idle connections warm for reuse; focus on total pool sizing, hold durations, and detecting long-running open transactions.

### Exercise 5. Role Limit vs. Server Limit

In a lab environment with an existing role:

```sql
ALTER ROLE app_service CONNECTION LIMIT 5;
```

**Question:** If PostgreSQL still has dozens of free slots, why can a sixth connection for this role still be rejected?

**Answer:** Because the role's own `CONNECTION LIMIT 5` can be reached even while `max_connections` has headroom. These are separate limit layers; inspect `pg_roles.rolconnlimit` and the role's active sessions.

After practicing, only if permitted and needed to remove the cap:

```sql
ALTER ROLE app_service CONNECTION LIMIT -1;
```

### Exercise 6. Config Changed but Not Yet Active

```sql
SELECT name, setting, context, pending_restart
FROM pg_settings
WHERE name IN ('listen_addresses', 'port', 'max_connections');
```

**Question:** What do `context = 'postmaster'` and `pending_restart = true` indicate?

**Answer:** The changes require a server restart to take effect. A reload alone cannot rebind listening sockets or resize connection slots allocated at startup.

### Exercise 7. Analyzing a Container Environment Error

PostgreSQL inside a container listens on `5432`. The host publishes `15432:5432`, and a client running on the host uses `-p 5432` and receives `connection refused`.

**Hint:** Connect to the **host-published port**, `15432` in this example, while verifying Docker port mapping and bind addresses. `SHOW port` inside the container will still report `5432`.

### Exercise 8. Connection Design for a Java API

An application runs 4 replicas, each with Hikari `maximum-pool-size = 25`; PostgreSQL has `max_connections = 120`. Besides the application, there are batch jobs and admin connections.

**Question:** Why is there still a risk of exhausting connection slots even though `4 * 25 = 100 < 120`?

**Answer:** The remaining 20 slots are not purely safe headroom for the app: reserved slots, jobs, monitoring, overlapping replica rollouts, and other clients all draw from them. Budget for **system-wide peak**, while also evaluating RAM/CPU cost and excessive query concurrency.

### Exercise 9. Inspecting TLS Connections

```sql
SELECT
    a.usename,
    a.client_addr,
    s.ssl,
    s.version
FROM pg_stat_activity AS a
JOIN pg_stat_ssl AS s USING (pid)
WHERE a.backend_type = 'client backend';
```

**Task:** If a TCP session shows `ssl = false` while policy requires TLS, what should you investigate?

**Hint:** Connection path, HBA `hostssl`, server and client TLS configuration, and possible TLS termination at a proxy. Never assume every hop is encrypted from a single TLS flag.

## 24. Common Misconceptions

**1. "`listen_addresses='*'` means anyone can log in."** False. It only expands where the server listens; HBA, authentication, database privileges, and firewalls still control access.

**2. "To allow subnet `10.20.30.0/24`, put the CIDR in `listen_addresses`."** False. `listen_addresses` specifies **server** IPs/interfaces or hostnames; client ranges belong in HBA/firewalls.

**3. "`localhost` and `127.0.0.1` are always identical."** Not completely. `localhost` can resolve to IPv4 or IPv6; omitting host on Linux can also select a Unix socket.

**4. "Changing `port` only requires `pg_reload_conf()`."** False. `port` requires a server restart.

**5. "`pg_isready` reports accepting, so the application account can definitely log in."** False. It does not verify username, password, database, TLS, or privileges.

**6. "`max_connections=100` means all 100 connections belong to the app pool."** False. You must account for reserved admin slots, other clients, and version-specific settings.

**7. "Connection limit caps how many queries run simultaneously."** False. An `idle` session still occupies a connection slot even when running no query at that instant.

**8. "Raising `max_connections` always makes the application faster."** False. Too many active backends can cause CPU/RAM/I/O contention and reduce throughput.

**9. "Raising `max_connections` fixes a role hitting `CONNECTION LIMIT`."** False. Role/database limits are enforced independently.

**10. "Every PostgreSQL version supports `reserved_connections`."** False. That parameter was added in PostgreSQL 16; check the server's major version first.

**11. "`idle in transaction` sessions are just as harmless as `idle` sessions."** False. Long open transactions hold locks and impede MVCC cleanup.

**12. "Connecting via Docker/Kubernetes must always use `SHOW port`."** Not necessarily. Client-facing ports may be determined by host port publishing or Service mappings.

**13. "With PgBouncer, you don't need to care about transactions or session state."** False. Transaction pooling imposes compatibility requirements on how applications use session state.

**14. "One timeout can fix every connection error."** False. Pool connection timeouts, `statement_timeout`, `lock_timeout`, and idle session timeouts solve distinct problems.

**15. "Once the listener is open, TLS is unnecessary."** False. When traffic crosses networks requiring protection, TLS and proper verification are essential design components.

## 25. Quick Diagnostic Workflow

When an application fails to connect or connects intermittently, follow this order:

```text
1. Identify the exact endpoint the application actually uses:
   hostname/IP, port, database, user, TLS/proxy
                         |
                         v
2. Run pg_isready or test TCP from the actual client host
                         |
              +----------+-----------+
              |                      |
        Unreachable             Reaches server
              |                      |
              v                      v
3A. Process/listener/port/     3B. HBA/TLS/authentication
    DNS/firewall/route              /CONNECT privilege
              |                      |
              +----------+-----------+
                         |
                         v
4. If connection-limit error:
   max_connections / reserved slots
   rolconnlimit / datconnlimit
                         |
                         v
5. Inspect pg_stat_activity:
   role, database, active, idle, idle in transaction
                         |
                         v
6. Cross-check pool sizes, replicas, rollouts, and real load
                         |
                         v
7. Fix the failing layer; re-verify from the application
```

A quick read-only SQL diagnostic set on a running server:

```sql
SHOW server_version;
SHOW listen_addresses;
SHOW port;
SHOW max_connections;

SELECT count(*) AS client_sessions
FROM pg_stat_activity
WHERE backend_type = 'client backend';

SELECT datname, usename, state, count(*) AS sessions
FROM pg_stat_activity
WHERE backend_type = 'client backend'
GROUP BY datname, usename, state
ORDER BY sessions DESC;
```

For connection incidents, test results from the **actual client host** and server logs around the error timestamp remain crucial. A successful test directly on the database host does not represent the network path used by your Java application.

## 26. Summary

PostgreSQL connection configuration rests on three pillars:

- **`listen_addresses`** determines which network addresses PostgreSQL listens on; **`port`** sets the server's TCP port. Both require a restart when changed.
- **`pg_hba.conf`, TLS, firewalls, and `CONNECT` privileges** decide whether a client reaching the server can authenticate and access a database. Opening the listener **does not** grant access to all clients.
- **`max_connections` and role/database limits** cap concurrent sessions, while reserved slots protect partial administrative access when slots near exhaustion. Raising connection limits does not automatically increase query throughput.

When operating multiple Java applications or container replicas, budget capacity as **replica count multiplied by max pool size**, plus other clients and safety headroom. Use `pg_stat_activity` to distinguish `active`, `idle`, and `idle in transaction` sessions; use connection pooling or PgBouncer where appropriate instead of opening unbounded backends.

Finally, never tweak configuration by guesswork. **Confirm the exact instance, listener, network path, and limit layer**, make controlled edits, and re-verify from the exact connection path the application actually uses. That is the foundation for keeping PostgreSQL accessible, secure, and stable under load.
