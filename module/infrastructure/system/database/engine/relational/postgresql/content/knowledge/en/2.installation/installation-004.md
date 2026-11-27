# Starting, Stopping, Restarting, and Checking Status with pg_ctl

In PostgreSQL, the **`pg_ctl`** utility manages the lifecycle of a **database cluster**: starting the server, performing controlled shutdowns, restarting, reloading configuration, and checking status. These operations differ from normal SQL queries: `pg_ctl` runs on the server's operating system, requires access permissions to the data directory, and affects every database inside that PostgreSQL instance.

This lesson covers `start`, `stop`, `restart`, and `status` operations, distinguishing `smart`, `fast`, and `immediate` shutdown modes, using the `-D`, `-l`, `-w`, and `-t` flags, following up with `pg_isready` and `psql`, and troubleshooting common startup failures.

> **Safety:** Practice stopping and restarting only on a test PostgreSQL cluster you are authorized to manage. In production, verify the exact host, exact data directory, maintenance window, and service management system. Never use `pg_ctl` to fight for control against systemd, Kubernetes, or a high-availability cluster manager.

## 1. Structure to Understand Before Running pg_ctl

A PostgreSQL **cluster** is a collection of databases managed by a single PostgreSQL server sharing one **data directory**. One cluster can contain `postgres`, `appdb`, `reportdb`, and many other databases. `pg_ctl stop` shuts down **the entire server**, not just a single selected database.

| Component | Role |
|---|---|
| `postgres` | Server program handling connections, queries, and background processes. |
| `pg_ctl` | Control utility for the server process, targeting the specified data directory. |
| `PGDATA` | Environment variable pointing to the cluster's data directory. |
| `-D directory` | Option to pass the data directory directly to `pg_ctl`. |
| `postmaster.pid` | Server lock/status file in the data directory while PostgreSQL is running; must never be deleted arbitrarily. |
| `postgresql.conf` and related configs | Controls ports, memory, logging, and server parameters. |
| `pg_wal/` | Stores WAL segments related to durability and transaction recovery. |

Conceptual diagram:

```text
Lab machine
├── PostgreSQL binaries
│   ├── postgres
│   ├── pg_ctl
│   ├── pg_isready
│   └── psql
│
└── /srv/postgresql/labdata    <-- PGDATA
    ├── PG_VERSION
    ├── base/
    ├── global/
    ├── pg_wal/
    ├── postgresql.conf (may reside elsewhere depending on install method)
    └── postmaster.pid (when the server is running)
```

**`PGDATA` is not a SQL database name.** When running `pg_ctl -D /srv/postgresql/labdata status`, you are inspecting the server tied to that data directory, not querying a database named `labdata`.

### The Cluster Must Be Initialized First

`pg_ctl start` starts **an existing cluster**. It does not create initial data files; creating a new cluster belongs to `initdb` and the installation process. **Never re-run `initdb` on an existing data directory to fix a startup failure.** Doing so can accidentally initialize an empty cluster or disrupt data recovery procedures.

## 2. Preparing Permissions, Versions, and Paths

On Linux/macOS, check the tools:

```bash
command -v pg_ctl
pg_ctl --version
pg_config --bindir
```

`pg_config --bindir` helps locate the directory containing binaries if `pg_ctl` is not in `PATH`. Package installations may place binaries in versioned directories such as `/usr/lib/postgresql/16/bin/`. Actual paths depend on the installation method.

The PostgreSQL server usually runs under the `postgres` **OS user** or another dedicated account owning the data directory. **Never run the PostgreSQL server directly as root.** The SQL role `postgres` and the operating system user `postgres` are two distinct types of identities.

In this lab, assume a cluster has been initialized at:

```bash
export PGDATA=/srv/postgresql/labdata
export PGLOG=/srv/postgresql/logs/lab-postgres.log
```

These paths are **illustrative** and not mandatory on every machine. The parent directory of the log file must exist and be writable by the user running PostgreSQL. This lesson continues using these variables for readability.

### Know Which System Manages PostgreSQL

If PostgreSQL was installed through a service manager, the proper operational command may be:

```bash
# Example checking the service on a Linux system using systemd.
systemctl status postgresql
```

The unit name may be `postgresql@16-main`, `postgresql-16`, or something else. Debian/Ubuntu also provides `pg_ctlcluster` for package-managed clusters. Containers/Kubernetes and HA platforms have their own mechanisms.

**Never manually run `pg_ctl` on a data directory managed by a service manager.** The supervisor may automatically restart a process you just stopped, or report inconsistent state. The direct commands below are intended for **manually managed lab clusters**.

## 3. Syntax and Important Options

Basic operations:

```bash
pg_ctl -D "$PGDATA" status
pg_ctl -D "$PGDATA" -l "$PGLOG" -w -t 120 start
pg_ctl -D "$PGDATA" -m fast -w -t 120 stop
pg_ctl -D "$PGDATA" -m fast -w -t 120 restart
pg_ctl -D "$PGDATA" reload
```

| Option | Effect |
|---|---|
| `-D directory` | Specifies the data directory. If omitted, `pg_ctl` may use `PGDATA` from the environment. |
| `-l filename` | Redirects server startup output/log to the specified file as managed by `pg_ctl`. |
| `-w` | Waits for start/stop/restart completion. |
| `-W` | Does not wait for completion; the caller must verify status separately. |
| `-t seconds` | Maximum wait timeout in seconds, e.g., 120 seconds. |
| `-m smart/fast/immediate` | Shutdown mode for `stop`/`restart`. |
| `-o options` | Passes startup options directly to the `postgres` process. |
| `-s` | Suppresses informational output from the utility. |

In modern PostgreSQL versions, `pg_ctl` waits for completion by default, yet passing `-w` explicitly makes runbooks clear. A timeout on `-t` is **not sufficient to conclude** that the server has stopped or failed to start; inspect actual process state and logs.

### Why Specify -D Explicitly?

Suppose a machine hosts two clusters:

```text
/srv/postgresql/main   -> port 5432
/srv/postgresql/lab    -> port 55432
```

If `PGDATA` lingers from another shell session, `pg_ctl status` without `-D` may target the unintended cluster. In operational scripts, always pass `-D "/correct/data/path"` and confirm the data directory before stopping or restarting.

## 4. Checking Status with pg_ctl status

A read-only command that does not modify data:

```bash
pg_ctl -D "$PGDATA" status
```

When running, output looks like:

```text
pg_ctl: server is running (PID: 12345)
/path/to/postgres "-D" "/srv/postgresql/labdata" ...
```

When stopped:

```text
pg_ctl: no server running
```

PID and paths here are examples. The tool sets an **exit status** so calling scripts can inspect the outcome programmatically, not just human-readable text.

### How Much Does status Verify?

`pg_ctl status` verifies process status for the **exact PGDATA**. However, "server is running" does not guarantee:

1. The server is ready to accept new connections.
2. Application accounts can log in.
3. The target database exists with a complete schema.
4. Business queries can execute successfully.
5. You are targeting the right host/port when multiple PostgreSQL instances exist.

To confirm practical availability, follow the sequence **`pg_ctl status` → `pg_isready` → `psql`** in subsequent steps.

### Never Arbitrarily Delete postmaster.pid When Seeing Unexpected State

`postmaster.pid` helps the server track cluster status and prevents two server processes from using the same data directory simultaneously. If `start` reports a server is already running even though no port appears open, inspect PIDs, logs, service managers, and running OS processes.

**Never delete `postmaster.pid` to "force PostgreSQL to start" without verifying beyond doubt that no process is using the data directory.** Deleting a valid lock file and starting a second server on the same data directory can cause severe data corruption.

## 5. Starting with pg_ctl start

Once you confirm the server is stopped and the data directory is valid:

```bash
pg_ctl -D "$PGDATA" -l "$PGLOG" -w -t 120 start
```

Explanation:

- `-D "$PGDATA"`: selects the cluster to start.
- `-l "$PGLOG"`: records startup output/logs in a writable path.
- `-w`: waits until the server meets startup readiness criteria.
- `-t 120`: sets a 120-second timeout for the control command.

Flow:

```text
pg_ctl start
      |
      v
Locate data directory and configuration
      |
      v
Launch postgres process
      |
      v
Open data files, listener, and background workers
      |
      v
Perform recovery/WAL replay if needed
      |
      v
Server ready for connections
      |
      v
pg_ctl -w confirms or reports error/timeout
```

If a server is already running against the same PGDATA, **do not call start again**. PostgreSQL must never run two server processes sharing the same data directory.

### Notes on the Log File

`-l` redirects server output to the specified file at startup. However, a PostgreSQL setup may route logs via **logging collector, systemd journal, or container logs**, so this file does not necessarily hold all subsequent runtime logs.

If `start` fails:

```bash
pg_ctl -D "$PGDATA" status
tail -n 100 "$PGLOG"
```

Also inspect wherever PostgreSQL is actually configured to write logs. Never publish logs containing personal data or sensitive SQL statements to public locations.

### When the Start Command Times Out

If `-t 120` expires, the server may still be **replaying WAL after an unclean shutdown**. Inspect `status`, `pg_isready`, logs, and system resources rather than blindly re-running `start` or deleting lock files.

A `pg_ctl` timeout is a wait limit on the **control command**, not proof that the PostgreSQL process has terminated.

## 6. Checking Readiness with pg_isready

Once `pg_ctl` has started the server, check the endpoint:

```bash
pg_isready -h 127.0.0.1 -p 5432
```

Example:

```text
127.0.0.1:5432 - accepting connections
```

Common exit codes:

| Exit code | Meaning | Next Step |
|---:|---|---|
| `0` | Server is accepting connections. | Try logging in with `psql`. |
| `1` | Server responded but is rejecting connections. | Check startup/recovery/logs. |
| `2` | No response. | Check host, port, listener, firewall, server. |
| `3` | Invalid parameters or tool usage error. | Fix the check command. |

**`pg_isready` does not fully verify application access.** It only checks whether the server accepts connection attempts, even if the role/database you intend to use is invalid.

Therefore, the next verification step is **actual login and SQL execution**:

```bash
psql \
  -h 127.0.0.1 \
  -p 5432 \
  -U app_user \
  -d appdb \
  -v ON_ERROR_STOP=1 \
  -c "SELECT current_database(), current_user, pg_postmaster_start_time();"
```

`app_user` and `appdb` are illustrative names. Use real test credentials and databases. Never pass passwords on the command line or in logs; use prompts or an appropriate secret mechanism.

`pg_postmaster_start_time()` returns when the server started, which helps verify a restart actually occurred. On systems with multiple clusters, target the exact host, port, and account for the cluster under inspection.

## 7. Stopping PostgreSQL: smart, fast, and immediate

`pg_ctl stop` supports three **shutdown modes**. Your choice affects active clients and transactions.

### 7.1. smart — Wait for Clients to Disconnect

```bash
pg_ctl -D "$PGDATA" -m smart -w -t 120 stop
```

The server stops accepting new connections during shutdown and **waits for existing clients to disconnect on their own**. Long-lived sessions, including connection pools or idle sessions, can prevent the stop command from completing within the expected window.

Suitable when **draining traffic** and allowing clients to finish normally. If it times out, identify remaining connected sessions before deciding to switch modes.

### 7.2. fast — Abort In-Flight Work and Shut Down Cleanly

```bash
pg_ctl -D "$PGDATA" -m fast -w -t 120 stop
```

The server does not wait for clients to disconnect; active connections are terminated and uncommitted transactions are **rolled back**. PostgreSQL performs a **clean shutdown**.

On modern PostgreSQL versions, `fast` is the default mode for `pg_ctl stop` when `-m` is omitted. Specifying it explicitly alerts operators that active requests may be interrupted.

### 7.3. immediate — Emergency Use Only

```bash
# Illustrative only. Do not run without justification and approval.
pg_ctl -D "$PGDATA" -m immediate stop
```

The server aborts **immediately** without performing the normal clean shutdown sequence. The next startup requires **crash recovery** via WAL. This is not a standard shutdown method to save a few seconds during maintenance.

While WAL protects consistency and durability per PostgreSQL's configuration, an `immediate` stop can make the next startup take much longer to recover; it does not replace backups and is not a safe cure-all for every incident.

### Comparison Table

| Mode | Existing Connections | Active Transactions | Next Startup |
|---|---|---|---|
| `smart` | Waits for clients to leave. | Given a chance to finish over the connection before stopping. | After clean shutdown. |
| `fast` | Disconnects clients; does not wait. | Aborts active work and rolls back uncommitted parts. | After clean shutdown. |
| `immediate` | Terminates processes immediately. | Bypasses normal rollback/clean shutdown path. | Requires WAL crash recovery. |

**Rule of thumb:** For routine time-bounded maintenance, `fast` is generally preferred over `immediate`. If you need to wait for connections to finish naturally, `smart` works, though it may wait indefinitely.

## 8. Restarting with pg_ctl restart

`restart` combines stopping and starting the cluster:

```bash
pg_ctl -D "$PGDATA" -m fast -w -t 120 restart
```

Impact:

1. Open connections to the server are dropped during shutdown.
2. Transactions uncommitted at the time of a `fast` stop do not continue after restart.
3. PostgreSQL re-reads startup configurations; parameters requiring a restart take their new values.
4. Applications must reconnect, re-establish physical connections in pools, and handle failed requests per policy.

**`pg_ctl restart` is not a zero-downtime operation.** Maintaining availability in production requires replicas, failover, or proper traffic orchestration; calling `restart` on a standalone node causes a service interruption.

### Verifying the Server Actually Restarted

Before and after restarting in the lab:

```sql
SELECT pg_postmaster_start_time() AS server_started_at;
```

An updated timestamp confirms the PostgreSQL server restarted. Next, verify the changed parameters and application connectivity.

### Example Parameters Requiring Restart

Settings such as `shared_buffers` and `max_connections` have `postmaster` context and require a restart after configuration changes:

```conf
# Example only in postgresql.conf for the lab cluster.
shared_buffers = '256MB'
max_connections = 150
```

After editing the right configuration file, restart via your environment's **official lifecycle manager** and verify:

```sql
SHOW shared_buffers;
SHOW max_connections;
```

Never assume a setting took effect simply because the restart command exited cleanly without checking runtime values.

## 9. When Is pg_ctl reload Enough?

`reload` instructs PostgreSQL to reload its configuration files:

```bash
pg_ctl -D "$PGDATA" reload
```

This command **does not stop the entire server** and normally does not disconnect clients. However, only parameters whose context permits reloading take effect on reload.

You can also trigger a reload via SQL if your account has permission:

```sql
SELECT pg_reload_conf();
```

This function returns `true` when the reload signal is sent successfully; **it does not guarantee every change is valid and applied**. Always check logs, `pg_settings`, and—when authorized—`pg_file_settings`.

### Checking Whether a Parameter Requires Restart

```sql
SELECT
    name,
    setting,
    context,
    pending_restart
FROM pg_settings
WHERE name IN (
    'shared_buffers',
    'max_connections',
    'log_min_duration_statement',
    'work_mem'
)
ORDER BY name;
```

`context` indicates the parameter's configuration context, while `pending_restart` shows whether a change has been recorded that requires a restart to take effect. Parameters modifiable per session or by a superuser behave differently from startup-only parameters.

| Operation | Disrupts Existing Connections? | Applies Parameters Requiring Restart? |
|---|---|---|
| `pg_ctl reload` | Usually no. | No. |
| `SELECT pg_reload_conf()` | Usually no. | No. |
| `pg_ctl restart` | Yes. | Yes, if configuration is valid and server starts cleanly. |

Do not restart solely because you edited a file: first determine which parameters can be reloaded and which genuinely require a restart.

## 10. Reading Logs and Explaining Common Start Errors

When startup fails, read messages and logs before modifying any data files.

| Symptom | Possible Cause | Approach |
|---|---|---|
| "permission denied" on data directory. | Wrong OS user, owner, or permissions. | Check account/permissions; never run as root or grant world-writable access to the data directory. |
| `PG_VERSION` not found. | Wrong `-D`, empty path, or `initdb` not run. | Verify the original cluster; do not run `initdb` over data. |
| Port already in use. | Another instance is listening on the port. | Identify the port/process; never stop another server without authorization. |
| Reports server already running. | Cluster is currently active or stale lock state needs investigation. | Check `status`, PID, supervisor; never delete `postmaster.pid` arbitrarily. |
| Data directory incompatible with server version. | Using binaries from a different PostgreSQL major version. | Check `pg_ctl --version` and `PG_VERSION`; follow a proper upgrade plan. |
| Server is in recovery and not yet accepting connections. | Replaying WAL, starting after an unclean shutdown. | Monitor logs/status; do not run duplicate starts on timeout. |
| "unrecognized configuration parameter" or invalid value. | Invalid configuration edit. | Revert/fix the setting; check logs and active config sources. |
| Logs not found in the `-l` file. | Logging collector or service manager routes logs elsewhere. | Check actual log destination (journal/container/log directory). |

### Checking Port for a Test Cluster

If the lab cluster needs port `55432` and the server is currently stopped:

```bash
pg_ctl -D "$PGDATA" \
  -l "$PGLOG" \
  -o "-p 55432" \
  -w -t 120 start

pg_isready -h 127.0.0.1 -p 55432
```

`-o` passes startup flags to `postgres`. For settings meant to persist across restarts, manage the port in the authoritative configuration file rather than relying on manually typed CLI flags.

### Verifying the Data Path Once Connected

An authorized PostgreSQL user can run:

```sql
SHOW data_directory;
SELECT version(), pg_postmaster_start_time();
```

Access to `data_directory` may be restricted since it reveals internal host layout; application accounts do not necessarily have permission to read it. This check helps operators verify the **target cluster**, not a privilege to grant broadly.

## 11. Verification Sequence After Restart

Even when a `restart` command reports success, verify across multiple layers:

```text
pg_ctl status
    |
    v
Is the right PostgreSQL process/cluster running?
    |
    v
pg_isready -h ... -p ...
    |
    v
Is the endpoint accepting connections?
    |
    v
psql -U ... -d ... -c "SELECT 1"
    |
    v
Can the application account log in and run SQL?
    |
    v
Check schema, lab test transactions, API
    |
    v
Does the service meet business criteria?
```

Having a running PID does not prove the target database is intact, roles have permissions, extensions load, or the application is healthy.

### PostgreSQL and Java Connection Pools

In Spring Boot, HikariCP and similar pools reuse **physical connections**. When the PostgreSQL server restarts, previously open connections can no longer be used seamlessly. The pool must establish new connections; requests executing during the restart window may receive a `SQLException`.

Read operations can often be retried per policy, but writes require care: **a network error while awaiting a response does not prove the transaction failed to commit**. If business logic cannot tolerate duplicate effects, implement idempotency or transaction verification before retrying.

## 12. Distinguishing pg_ctl from Other Management Tools

| Tool | Scope | When to Use |
|---|---|---|
| `pg_ctl` | PostgreSQL process and data directory. | Manual clusters or approved runbook steps. |
| `systemctl` | Service lifecycle in systemd. | PostgreSQL managed by a Linux service manager. |
| `pg_ctlcluster` | PostgreSQL clusters managed by Debian/Ubuntu packages, if present. | Hosts using those distribution tools. |
| `pg_isready` | Checks the PostgreSQL endpoint. | Confirming the server is accepting connections. |
| `psql` | Connects and executes SQL. | Validating roles/databases and running real queries. |

In containers/Kubernetes, an orchestrator may automatically restart a workload if the process exits. In HA setups, a cluster manager controls leader, replica, and failover states. **Never mix conflicting control planes arbitrarily.**

On Windows, `pg_ctl.exe` offers equivalent operations. Example (illustrative paths):

```powershell
& "C:\Program Files\PostgreSQL\16\bin\pg_ctl.exe" -D "C:\PostgreSQL\labdata" status
& "C:\Program Files\PostgreSQL\16\bin\pg_ctl.exe" -D "C:\PostgreSQL\labdata" -l "C:\PostgreSQL\logs\startup.log" -w -t 120 start
& "C:\Program Files\PostgreSQL\16\bin\pg_ctl.exe" -D "C:\PostgreSQL\labdata" -m fast -w -t 120 stop
```

If a cluster is registered and managed as a Windows Service, use the appropriate service control tools per administrative policy rather than launching another process manually against the same data directory.

## 13. Minimal Runbook for a Test Cluster

### Before Operating

1. Confirm host, PostgreSQL version, `PGDATA`, port, and OS user.
2. Check what manages the server lifecycle: manual or supervisor.
3. Inspect `pg_ctl status`, `pg_isready`, and log destinations.
4. For stop/restart operations, ensure authorization and announce the interruption.
5. Define policy for in-flight transactions and Java application connections.

### Starting

```bash
pg_ctl -D "$PGDATA" status
# Only after confirming the cluster is stopped:
pg_ctl -D "$PGDATA" -l "$PGLOG" -w -t 120 start
pg_ctl -D "$PGDATA" status
pg_isready -h 127.0.0.1 -p 5432
```

Next, log in with `psql` and run the corresponding smoke test.

### Stopping

```bash
# Be prepared for client disconnections and rollback of uncommitted transactions.
pg_ctl -D "$PGDATA" -m fast -w -t 120 stop
pg_ctl -D "$PGDATA" status
```

After stopping, `status` reporting no server running is the expected result. If `stop` times out, inspect running processes and logs before taking further action.

### Restarting

```bash
# Only use if the server is running and downtime is planned.
pg_ctl -D "$PGDATA" -m fast -w -t 120 restart
pg_ctl -D "$PGDATA" status
pg_isready -h 127.0.0.1 -p 5432
```

If the server is already stopped, use `start`; do not treat `restart` as a catch-all command for every cluster state. Afterward, query server start time and verify modified settings.

### Recording Operational Evidence

A concise report should capture: cluster name, data directory path, version, control tool, operator, start/end timestamps, shutdown mode, command results, any error logs, `pg_isready` confirmation, and application smoke test results. In production, include approvals, customer impact, and rollback plans.

## 14. Practice Exercises

### Exercise 1 — Write Accurate Commands and Identify Clusters

A host has two clusters: `/srv/postgresql/a` on port `5432` and `/srv/postgresql/b` on port `55432`. Write two separate `pg_ctl status` commands and two `pg_isready` commands targeting the right ports. Explain why `pg_isready -p 5432` does not verify cluster B's status.

### Exercise 2 — Choosing a Stop Mode

Choose among `smart`, `fast`, and `immediate` for each scenario:

1. Waiting for existing sessions to close naturally after draining traffic.
2. Stopping within a maintenance window where rolling back uncommitted transactions is acceptable.
3. An emergency incident where immediate termination is approved.

Explain the differences in connection handling and recovery on the next startup.

### Exercise 3 — Analyzing Status Results

`pg_ctl status` reports the server is running, yet `pg_isready` reports `rejecting connections`. List at least two possible reasons and the inspection sequence. Why should you avoid immediately running a second `start` or deleting `postmaster.pid`?

### Exercise 4 — Starting with a Timeout

Write a start command for `/srv/postgresql/labdata` logging to `/srv/postgresql/logs/startup.log` and waiting up to 90 seconds. If 90 seconds elapse and logs show WAL replay is underway, describe the safe next step.

### Exercise 5 — Reload vs. Restart

You edit two parameters: `max_connections` and `log_min_duration_statement`. Show how to inspect `pg_settings.context` and `pending_restart`, explain which parameter requires a restart, and describe how to verify the change actually took effect.

### Exercise 6 — Verifying the Application After Restart

A Java application with HikariCP connects to PostgreSQL. Outline the verification chain from `status` to `pg_isready`, `psql`, and the API, and describe how stale dropped connections are handled and the risk of retrying non-idempotent writes.

### Exercise 7 — When PostgreSQL Has a Service Manager

An administrator runs `pg_ctl stop` on a PostgreSQL instance managed by systemd, and the server restarts itself automatically. Explain what mechanism causes this behavior and why you should not control the same cluster with both manual `pg_ctl` and a supervisor.

## Conclusion

**`pg_ctl` manages PostgreSQL's lifecycle by targeting the exact data directory.** `start` launches the server, `stop` shuts it down using the selected mode, `restart` stops and starts it again, and `status` reports the process status tied to the cluster. `-D`/`PGDATA` targets the exact instance; `-l` captures startup logs; `-w`/`-t` control waiting; and `-m` determines client impact during shutdown.

Remember that **`smart` waits for clients, `fast` disconnects clients and rolls back incomplete work for a clean shutdown, and `immediate` requires crash recovery on the next start**. When changing settings that do not require a restart, `reload` avoids unnecessary disruption.

Seeing "server is running" is only the first check: always follow up with **`pg_isready`, `psql` login, and business smoke checks** before declaring the service ready. On infrastructure managed by systemd, Kubernetes, or HA controllers, always use the **official control tool** and follow system operational procedures.
