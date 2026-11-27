# Checking PostgreSQL Version, Configuration Paths, and Startup Logs

After installing PostgreSQL, the first three questions to answer are: **which server is actually running**, **where does that server read its configuration from**, and **which logs show whether startup succeeded or failed**. Merely seeing that `psql` runs or that a service shows `active` is insufficient to conclude your application is connected to the intended PostgreSQL instance.

On a development machine, PostgreSQL 15 and 16 might coexist; the `psql` client might be version 17; configuration files may reside in a different directory from data files; and logs may go to a file, the systemd journal, Docker logs, or a centralized logging service. Using the wrong path or version while troubleshooting can sometimes be more dangerous than the original issue.

This lesson walks through an inspection workflow **from an active SQL connection** and **when the server fails to start**, with examples for Linux, Windows, and container environments. Illustrated commands target modern PostgreSQL, primarily PostgreSQL 14 and newer; service names, paths, and tool interfaces depend on your operating system, packaging, and deployment environment.

## 1. Distinguishing Three Groups of Information to Verify

| Check Group | Core Question | How to Verify |
| --- | --- | --- |
| **Version** | Which major/minor version is PostgreSQL Server actually running? Do the client and installed binaries differ? | `SHOW server_version`, `SELECT version()`, `SHOW server_version_num`; compare against `psql --version`. |
| **Configuration paths** | Where does the server currently read `postgresql.conf`, `pg_hba.conf`, and its data directory? Which config changes are active? | `SHOW config_file`, `SHOW hba_file`, `SHOW data_directory`, `pg_settings`. |
| **Startup logs** | Which port did the server bind to, is it ready to accept connections, or why did it stop? | `SHOW log_destination`, `pg_current_logfile()`, log files, `journalctl`, Docker/Kubernetes logs, Windows Event Viewer. |

A reliable diagnostic chain:

```text
Locate the right instance
       |
       v
Confirm Server version + address/port/database
       |
       v
Confirm config_file + data_directory + hba_file
       |
       v
Confirm active settings and any pending_restart
       |
       v
Locate the right log source for that instance
       |
       v
Read startup lines and address the root cause if errors exist
```

Notably, **information reported directly by the running server** is far more trustworthy than guessing from installation directories. Whenever the server is reachable, ask the server itself before opening filesystem files.

## 2. Checking the PostgreSQL Server Version

Open a SQL connection to the target server and run:

```sql
SHOW server_version;

SHOW server_version_num;

SELECT version();
```

Example output:

```text
server_version
--------------
16.4

server_version_num
------------------
160004

version()
----------------------------------------------------------
PostgreSQL 16.4 on ..., compiled by ..., 64-bit
```

Meaning:

- `server_version`: human-readable server version string; use this to pick the matching documentation set.
- `server_version_num`: integer representation convenient for comparisons in scripts.
- `version()`: fuller server banner, often including OS/architecture and compiler details.

In PostgreSQL starting from major version 10, `16.4` means **major 16, minor 4**. Prior to PostgreSQL 10, versions had three parts: e.g., `9.6.24` meant **major 9.6**, minor 24. `server_version_num` for `16.4` is `160004`; do not treat version strings as decimal floats when comparing.

A compact query to record these details:

```sql
SELECT
    current_setting('server_version') AS server_version,
    current_setting('server_version_num')::integer AS server_version_num,
    version() AS build_information;
```

### 2.1. Why Not Rely Solely on psql --version?

In a terminal:

```bash
psql --version
```

This prints the **version of the `psql` client program being invoked**, not the version of the server your application connects to. You might have:

```text
Laptop: psql (PostgreSQL) 17.2
Server: PostgreSQL 16.4
```

This is not necessarily an error. Clients and servers have independent deployment lifecycles. However, to determine whether a SQL feature is supported by the server, **server version** is what counts.

Similarly:

```bash
postgres --version
pg_config --version
pg_dump --version
```

These commands respectively reflect the server binary found first in `PATH`, the installation/build metadata matching `pg_config`, and the `pg_dump` tool version. They **do not prove** the running PostgreSQL process serving your application actually uses those exact binaries.

A machine with side-by-side versions may find `postgres` and `psql` in two different directories. With multiple instances, checking binaries in `PATH` without verifying live connections can lead to misdiagnosis.

### 2.2. Confirming You Are Querying the Intended Server

Once connected, record additional details:

```sql
SELECT
    current_database() AS database_name,
    current_user AS database_role,
    inet_server_addr() AS server_address,
    inet_server_port() AS server_port,
    current_setting('server_version') AS server_version,
    pg_postmaster_start_time() AS server_start_time;
```

`pg_postmaster_start_time()` returns when the current postmaster process started. This helps verify a restart just occurred and correlate timestamps in the logs.

`inet_server_addr()` or `inet_server_port()` may return `NULL` over a Unix-domain socket, or may not reflect the public address in front of a proxy/load balancer. Also record the endpoint from your application configuration.

Inside `psql`, you can run:

```text
\conninfo
```

to inspect connection details for the current session.

## 3. Connecting Deliberately to the Right Instance

If your host runs multiple PostgreSQL clusters or ports, do not rely blindly on `psql` defaults. Specify host, port, user, and database explicitly:

```bash
psql -X -h 127.0.0.1 -p 5432 -U postgres -d postgres
```

Where:

- `-X`: skips reading the user's `psqlrc` startup file, useful for clean diagnostics without custom overrides.
- `-h 127.0.0.1`: connects over TCP loopback instead of defaulting to a Unix socket on certain OSes.
- `-p 5432`: target PostgreSQL port; `5432` is common, though not mandatory for every instance.
- `-U postgres`: database login role; this role is distinct from an OS account of the same name.
- `-d postgres`: target database, which must exist and permit the account to connect.

After connecting:

```sql
SHOW server_version;
SHOW port;
SHOW data_directory;
```

Certain parameters or administrative views may require elevated privileges. If you get a permission error, use an authorized administrative account per policy rather than granting `SUPERUSER` to an application account.

### 3.1. Reading Information in a Single Terminal Command

```bash
psql -X -h 127.0.0.1 -p 5432 -U postgres -d postgres \
  -c "SELECT current_database(), current_user, current_setting('server_version');"
```

This example uses `\` line continuation for Unix shells. In PowerShell or Command Prompt, write the command on a single line or use that shell's line continuation syntax.

### 3.2. Connection Failure Does Not Always Mean the Server Is Down

Messages like `connection refused` or `no response` indicate the **attempted connection path failed**, without pinpointing the cause:

- PostgreSQL may be stopped.
- PostgreSQL may be listening on a different port.
- The server may listen only on a Unix socket or a different IP address.
- A firewall, proxy, or network rule may be blocking traffic.
- You may be targeting the hostname of another machine.

Conversely, `password authentication failed` usually proves you reached a PostgreSQL server and failed at authentication. Distinguish startup failures, network connectivity failures, and authentication failures to look in the right logs.

## 4. Asking the Server Which Configuration Paths Are in Use

PostgreSQL uses several configuration files; filenames are usually identical across OSes, whereas their locations vary.

Run in an adequately privileged connection:

```sql
SHOW config_file;
SHOW hba_file;
SHOW ident_file;
SHOW data_directory;
```

You can retrieve all of them in a single query:

```sql
SELECT
    current_setting('config_file') AS config_file,
    current_setting('hba_file') AS hba_file,
    current_setting('ident_file') AS ident_file,
    current_setting('data_directory') AS data_directory;
```

Meaning:

| Parameter | Represents |
| --- | --- |
| `config_file` | Main configuration file actually loaded by the server, usually `postgresql.conf`. |
| `hba_file` | Host-based authentication rules file, usually `pg_hba.conf`. |
| `ident_file` | User-name mapping file for certain authentication methods, usually `pg_ident.conf`. |
| `data_directory` | Data directory of the running PostgreSQL cluster; holds storage files, metadata, WAL, and internal structures. |

Paths returned by the server are far more reliable than guessing conventions like `/etc/postgresql/...` or `/var/lib/postgresql/...`.

### 4.1. Why Can config_file Differ from data_directory?

Both layouts are valid:

**Single-directory layout** — common when initializing a data directory manually with `initdb`:

```text
/srv/postgres/main/
    PG_VERSION
    postgresql.conf
    pg_hba.conf
    pg_ident.conf
    base/
    global/
    pg_wal/
    ...
```

**Split config and data layout** — common in several Linux packaging systems:

```text
/etc/postgresql/16/main/postgresql.conf
/etc/postgresql/16/main/pg_hba.conf
/var/lib/postgresql/16/main/           <- data_directory
```

These paths are illustrative only; **never** treat them as universal defaults across all systems. In containers or managed servers, configuration may also come from environment variables, ConfigMaps, volumes, or configuration management tools.

### 4.2. Which File Does What?

**`postgresql.conf`** configures server behavior: port, listen addresses, memory, logging, replication, and operational settings. Example:

```conf
listen_addresses = 'localhost'
port = 5432
log_min_duration_statement = '500ms'
```

**`pg_hba.conf`** defines authentication methods and permitted client sources. Illustrative example:

```conf
# TYPE  DATABASE   USER        ADDRESS         METHOD
host    appdb      app_user    127.0.0.1/32    scram-sha-256
```

This is just one sample HBA line, **not a complete recommended config**. Line ordering in `pg_hba.conf` matters because PostgreSQL uses the first matching rule; misconfiguring it can lock out applications or even administrators.

**`pg_ident.conf`** maps OS usernames or certificate identities to database roles when an authentication method specifies a `map`.

### 4.3. Do Not Confuse PGDATA with config_file

The `PGDATA` environment variable or `-D` startup flag typically specifies the **data directory** or configuration directory depending on startup design. However, PostgreSQL can also be launched with `-c config_file=...` pointing separately to a `data_directory`.

Therefore:

```text
PGDATA set in shell               ≠  guaranteed active config_file
PostgreSQL install directory      ≠  guaranteed data_directory
Path in package documentation     ≠  guaranteed path used by running server
```

When the server is online, prefer `SHOW config_file` and `SHOW data_directory` to verify reality. When offline, inspect the startup command, service unit definition, and provisioned config files.

## 5. Which Configuration Is Actually Active?

Finding the right `postgresql.conf` is only the first step. An active value may come from:

- PostgreSQL built-in defaults.
- The main `postgresql.conf` file.
- Files included via `include`, `include_if_exists`, or `include_dir`.
- `postgresql.auto.conf` managed by `ALTER SYSTEM`, located in the data directory.
- Command-line flags passed to the server process.
- Session-, database-, or role-level overrides for parameters adjustable at those scopes.

Thus, seeing `log_min_duration_statement = 1000` in a file does not guarantee your session uses `1000`.

### 5.1. Reading Active Runtime Values

```sql
SHOW port;
SHOW listen_addresses;
SHOW max_connections;
SHOW shared_buffers;
SHOW log_destination;
SHOW logging_collector;
SHOW log_min_duration_statement;
```

Or using `current_setting`:

```sql
SELECT
    current_setting('port') AS port,
    current_setting('max_connections') AS max_connections,
    current_setting('logging_collector') AS logging_collector;
```

These queries show the **effective value for the current session or server** according to each parameter's scope, not necessarily a specific line in a file.

### 5.2. Viewing Configuration Sources via pg_settings

`pg_catalog.pg_settings` exposes metadata for every parameter. Example:

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
    'port',
    'listen_addresses',
    'shared_buffers',
    'logging_collector',
    'log_destination',
    'log_directory',
    'log_filename',
    'log_min_duration_statement'
)
ORDER BY name;
```

Column meanings:

| Column | Interpretation |
| --- | --- |
| `name`, `setting`, `unit` | Parameter name, active value, and unit. |
| `context` | Context controlling how the parameter can change; indicates whether restart, reload, or session set applies. |
| `source` | Where the active value originated, e.g., default, configuration file, command line, or session. |
| `sourcefile`, `sourceline` | Config file path and line number, when server and permissions allow visibility. |
| `pending_restart` | `true` when a config file change has been detected that requires a server restart to apply. |

`sourcefile` and `sourceline` are often hidden from regular users; they may appear `NULL` if your account lacks privileges or the value did not come from a file. An admin role or `pg_read_all_settings` membership may be required depending on version and setup.

### 5.3. Checking for Errors in Configuration Files

For administrators with appropriate privileges:

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

`pg_file_settings` helps locate errors in lines parsed by PostgreSQL from config files. Having zero error rows **does not prove every setting makes operational sense**; it only verifies config parsing/loading status.

For parameters specified in multiple files or overridden, view all entries:

```sql
SELECT sourcefile, sourceline, name, setting, applied, error
FROM pg_file_settings
WHERE name IN ('port', 'shared_buffers', 'log_destination')
ORDER BY sourcefile, sourceline;
```

Never manually edit files inside `data_directory` just because they show up in metadata. Distinguish auto-generated files, package-managed files, and files controlled by configuration management tools.

## 6. How Does Reload Differ from Restart?

Some PostgreSQL parameters apply via **reload**, while others only take effect after a **restart**.

### 6.1. Reloading Configuration

When the server is running and your account has sufficient privileges:

```sql
SELECT pg_reload_conf();
```

This signals PostgreSQL to re-read its configuration files. Returning `true` essentially means the reload signal was sent successfully—**it does not guarantee every edited line applied without errors**.

After reloading, check:

```sql
SELECT name, setting, source, pending_restart
FROM pg_settings
WHERE name IN (
    'log_min_duration_statement',
    'shared_buffers',
    'logging_collector'
)
ORDER BY name;
```

and read the logs for config parsing errors or restart-required notices.

On systems with `pg_ctl` and appropriate OS permissions, you can run:

```bash
pg_ctl -D /path/to/data_directory reload
```

Replace the example path with the real data directory. If PostgreSQL is managed by systemd, Windows Services, Docker, or Kubernetes, use the corresponding operational mechanism and follow that environment's workflow.

### 6.2. Restarting the Server

Parameters such as `shared_buffers`, `port`, `listen_addresses`, and `logging_collector` generally take effect only after a server restart. In `pg_settings`, parameters with `context = 'postmaster'` belong to the restart-required group.

For example, if you edit:

```conf
shared_buffers = '1GB'
```

and only call `pg_reload_conf()`, the change stays pending a restart. `pending_restart = true` signals that a restart is needed.

**Restarting drops all active connections**, rolls back uncommitted transactions, and impacts SLAs. In replication/HA systems, coordinate restarts with primary/standby roles and the cluster orchestrator rather than restarting arbitrarily just to apply a parameter immediately.

### 6.3. ALTER SYSTEM and postgresql.auto.conf

Administrators can change many settings via SQL:

```sql
-- Illustrative only in a lab environment with admin privileges.
ALTER SYSTEM SET log_min_duration_statement = '500ms';

SELECT pg_reload_conf();

SHOW log_min_duration_statement;
```

`ALTER SYSTEM` writes settings to `postgresql.auto.conf` inside the data directory. These changes **persist across restarts**, unlike `SET` which typically affects only the session. Parameters requiring a restart still require a restart even when set via `ALTER SYSTEM`.

To clear a specific setting managed by `ALTER SYSTEM`:

```sql
-- Execute only when certain which change should be reverted.
ALTER SYSTEM RESET log_min_duration_statement;
SELECT pg_reload_conf();
```

Do not edit `postgresql.auto.conf` manually by hand without a proper procedure. If your infrastructure uses Ansible, Helm, managed-service parameter groups, or centralized configuration management, `ALTER SYSTEM` can conflict with your authoritative config source.

## 7. Where Are PostgreSQL Startup Logs Located?

There is no single mandatory log location for all PostgreSQL installations. The destination depends on **PostgreSQL's logging configuration** and **how the process is launched/packaged**.

Common sources:

| Environment | Where to Check |
| --- | --- |
| Standalone PostgreSQL via `pg_ctl` | File specified by `pg_ctl -l` or process stderr; collector log files if enabled. |
| systemd on Linux | `journalctl` for the exact service/unit; possibly package-specific log files as well. |
| Linux package with logging collector | Files inside `log_directory` named according to `log_filename`. |
| Docker | `docker logs` when PostgreSQL logs to stdout/stderr; or volume/log files if configured otherwise. |
| Kubernetes | `kubectl logs` on the PostgreSQL container; if file logging is enabled, inspect the volume or logging agent. |
| Windows | Log files configured via `logging_collector`, service wrapper stdout/stderr, or Windows Event Viewer if configured. |
| Managed PostgreSQL service | Provider console/logging service; host OS files are usually inaccessible. |

An important distinction: very early startup messages (before file logging initializes) **may appear in the journal, console, or service wrapper logs**, even if subsequent runtime logs go to a dedicated file once the server is up.

## 8. Querying PostgreSQL for Current Logging Configuration

While the server is online, run:

```sql
SHOW log_destination;
SHOW logging_collector;
SHOW log_directory;
SHOW log_filename;
SHOW log_rotation_age;
SHOW log_rotation_size;
SHOW log_line_prefix;
SHOW log_min_messages;
```

Interpretation:

- `log_destination` controls where messages go: `stderr`, `csvlog`, `syslog`, or other version-supported destinations (`jsonlog` was added in PostgreSQL 15).
- `logging_collector` determines whether PostgreSQL's collector captures and writes logs to files when using destinations like `stderr`/`csvlog`/`jsonlog`.
- `log_directory` is the folder for collector log files. If relative, it is resolved relative to the **data directory**.
- `log_filename` is the filename pattern, often including timestamp placeholders.
- `log_rotation_age` and `log_rotation_size` control log file rotation thresholds.
- `log_line_prefix` prepends timestamps, PID, database, user, or other diagnostic fields to each log line.

### 8.1. Checking the Active Log File

When using the logging collector, you can call:

```sql
SELECT pg_current_logfile();
```

To request a specific supported format:

```sql
SELECT pg_current_logfile('stderr');
```

This returns the path to the current log file when PostgreSQL can identify it through the logging collector. It returns **NULL** if the collector is off, the requested format is not written to a file, or file info is unavailable.

Example configuration:

```text
data_directory       = /srv/postgres/main
logging_collector    = on
log_directory        = log
log_filename         = postgresql-%Y-%m-%d_%H%M%S.log
```

With these settings, collector log files reside under `/srv/postgres/main/log/`, **not** in a `log` folder relative to your shell's working directory. If `log_directory` is an absolute path, it is used directly.

### 8.2. When logging_collector = off

If `logging_collector = off` and `log_destination` includes `stderr`, PostgreSQL writes messages to stderr. Whatever launched the process captures them via:

- systemd journal;
- Docker/container runtime;
- the file targeted by `pg_ctl -l`;
- terminal/console or service wrapper.

In this case, `pg_current_logfile()` returns `NULL`; that does not mean PostgreSQL is not logging. Locate the **actual stderr destination** of the process.

If logs go via `syslog`, inspect your OS syslog/journald configuration. Never assume `logging_collector` is the only way logs exist.

## 9. Recognizing a Successful Startup in the Logs

Illustrative `LOG` messages during server startup:

```text
LOG:  starting PostgreSQL 16.4 on x86_64-...
LOG:  listening on IPv4 address "127.0.0.1", port 5432
LOG:  listening on Unix socket "/var/run/postgresql/.s.PGSQL.5432"
LOG:  database system was shut down at 2026-01-10 09:14:00 UTC
LOG:  database system is ready to accept connections
```

This is an **illustrative example**, not verbatim output guaranteed on every machine. Depending on config, PostgreSQL may listen on IPv6, multiple addresses, or different socket paths; after an unclean shutdown, recovery/WAL replay messages will also appear.

How to read it:

1. `starting PostgreSQL ...` confirms process startup and prints the running binary version.
2. `listening on ...` reveals the actual addresses, ports, and sockets bound.
3. Recovery, checkpoint, or system-state lines document recovery progress.
4. `database system is ready to accept connections` signals that startup has completed enough to accept connections in its current state.

However, **ready to accept connections does not guarantee every application can log in**. `pg_hba.conf`, TLS, users, passwords, databases, firewalls, and object privileges must still match.

### 9.1. Log Severity Levels to Watch

| Level/Label | Typical Meaning |
| --- | --- |
| `LOG` | Operational info: startup, shutdown, recovery, checkpoints, or configuration. |
| `WARNING` | Condition needing attention without necessarily stopping the server. |
| `ERROR` | A statement or operation failed. |
| `FATAL` | Connection or process encountered a fatal error ending the current session/startup; appears on client auth failures or startup errors. |
| `PANIC` | Critical condition forcing server termination or recovery; requires urgent investigation. |
| `DETAIL` / `HINT` | Extra context and suggestions immediately following an error message. |

Do not jump straight to a `FATAL` line and ignore preceding lines. The root cause often appears in the adjacent lines right above it—such as a config syntax error, port bind failure, or data directory permission error.

### 9.2. Timestamps, PIDs, and Sensitive Data

An informative `log_line_prefix` correlates events by time and process. Example:

```conf
log_line_prefix = '%m [%p] %u@%d '
```

Here `%m` prints the timestamp, `%p` the PID, `%u` the username, and `%d` the database when available. Early startup lines have no user/database yet, so those fields remain blank.

**Protecting log files:** higher logging levels can record SQL statements, hostnames, parameter values in errors, or application details. Avoid accidentally leaking passwords, tokens, and sensitive data into logs. Do not leave `log_statement = 'all'` enabled long-term in production just to troubleshoot a startup issue without assessing security and storage costs.

## 10. Finding Logs on Linux with systemd

Many Linux PostgreSQL packages are managed by `systemd`. First, identify the **actual unit name**.

On Debian/Ubuntu, you may encounter:

```bash
sudo systemctl status postgresql
sudo systemctl status postgresql@16-main
```

On Red Hat/Rocky/AlmaLinux packages, the unit name may be:

```bash
sudo systemctl status postgresql-16
```

These names are packaging examples. **Do not conclude the server is running solely because the umbrella `postgresql` unit shows `active (exited)`**: on some distributions, the top-level unit simply manages child instance units.

### 10.1. Viewing Logs for the Exact Unit

Example for a cluster named `16-main`:

```bash
sudo journalctl -u postgresql@16-main -b -n 200 --no-pager
```

Meaning:

- `-u`: selects the unit.
- `-b`: shows logs since the current OS boot.
- `-n 200`: shows the last 200 lines.
- `--no-pager`: prints directly to the terminal.

If your actual unit is `postgresql-16`, adjust `-u` accordingly. You can add `-f` to tail new logs while starting a test instance, while making sure not to miss the very first error lines.

### 10.2. Listing Clusters Managed by Debian/Ubuntu Packages

Debian/Ubuntu systems often provide:

```bash
pg_lsclusters
```

It displays version, cluster name, port, status, owner, and paths. This is a distribution packaging tool, **not a universal PostgreSQL utility** available on every installation.

In standard Debian packaging, logs often live at:

```text
/var/log/postgresql/postgresql-16-main.log
```

However, if the server configures `logging_collector`, runs in a container, or uses custom packaging, the real path may differ. Verify via `SHOW log_*`, service configuration, or OS tools before concluding no logs exist.

### 10.3. Finding the Startup Command Used by systemd

```bash
sudo systemctl cat postgresql@16-main
sudo systemctl show -p ExecStart postgresql@16-main
```

Unit definitions reveal the binary, port, data/config directories, or wrapper script invoked. If a wrapper script is used, inspect how that wrapper resolves instance paths rather than guessing every parameter from the unit name.

## 11. Standalone PostgreSQL Run via pg_ctl

For servers initialized manually with `initdb` or lab setups, administrators may use:

```bash
pg_ctl -D /srv/postgres/main status
```

This checks the status of the PostgreSQL instance tied to the specified data directory.

To capture stderr to a startup log file in a **test environment**:

```bash
pg_ctl -D /srv/postgres/main \
  -l /srv/postgres/startup.log start
```

`-l` specifies the file receiving startup process output under `pg_ctl`. If PostgreSQL enables `logging_collector`, later runtime logs may shift to files under `log_directory`/`log_filename`, while early startup errors remain in the `-l` file.

**Never run `start` against the data directory of an already running instance.** Always confirm service ownership, process status, and ports first; in production, perform start/stop actions through the instance's official service manager.

### When the Server Is Completely Stopped

`SHOW config_file` cannot run because no server is answering. Instead:

1. Inspect the configuration file referenced by the `postgres`/`pg_ctl` command or service definition.
2. Check the expected data directory and its `PG_VERSION` file.
3. Check the exact binary used by the service via `postgres --version` using the **full binary path**.
4. Read service logs, startup `-l` logs, or stderr output.

`PG_VERSION` inside the data directory records the **cluster's major version**, not the running binary's minor patch level. Never rely on `PG_VERSION` alone to verify whether a server was patched from `16.4` to `16.5`.

For offline cluster inspection at an administrative level, PostgreSQL also provides `pg_controldata`, though it must match the right tool version and path; it is **not** a substitute for reading startup logs, and you should never run repair utilities when only diagnosing.

## 12. Logs on Windows

PostgreSQL may be installed as a Windows Service. In PowerShell:

```powershell
Get-Service -Name '*postgres*'
```

To inspect exact service names and command lines in an authorized environment:

```powershell
Get-CimInstance Win32_Service |
    Where-Object { $_.Name -like '*postgres*' } |
    Select-Object Name, State, PathName
```

Service names usually embed the version or cluster name chosen by the installer; do not assume every host uses `postgresql-x64-16`.

If PostgreSQL logs to a file:

```powershell
Get-Content -Path 'C:\Path\To\PostgreSQL\data\log\postgresql.log' -Tail 100
```

Replace the placeholder path with your actual log file. If configured to log to Windows Event Log or via a service wrapper, open Event Viewer and filter by the corresponding application/source. When the server fails to start, checking service status and Event Viewer is often the best diagnostic path available.

On Windows, the service account's permissions on the data directory, log directory, TLS private keys, and config files may differ from the PowerShell user account you are running under.

## 13. PostgreSQL Logs in Docker and Kubernetes

### 13.1. Docker

In a container configured so PostgreSQL writes to stdout/stderr, run:

```bash
docker logs --tail 200 pg-demo
```

If the container is named `pg-demo` and running, you can query the server inside:

```bash
docker exec -it pg-demo \
  psql -U postgres -d postgres \
  -c "SHOW server_version;"
```

In practice, the database role and target database must match your configured image/secrets. Docker commands do not bypass PostgreSQL authentication and do not prove ports are published to the host.

**Remember:** PostgreSQL logs inside containers may be:

- Written to stdout/stderr and visible in `docker logs`.
- Written by `logging_collector` to files inside a volume.
- Forwarded by a logging agent to a centralized system.

If `docker logs` lacks details, do not assume PostgreSQL is silent; check logging settings, volumes, and the image's entrypoint script.

### 13.2. Kubernetes

For a PostgreSQL pod:

```bash
kubectl logs -n database pod/postgres-0 -c postgres --tail=200
```

If a container recently crashed/restarted, inspect the previous container instance:

```bash
kubectl logs -n database pod/postgres-0 -c postgres --previous
```

If the pod fails to start containers or hits mount/secret errors:

```bash
kubectl describe pod -n database postgres-0
```

Namespace, pod, and container names here are examples. When using a PostgreSQL operator, also inspect custom resources and operator logs to see why it modified config or restarted pods.

**Note:** a new container image tag might differ from the mounted PostgreSQL data directory. A newer major version image cannot automatically start an older major version's data directory. Cross-check binary versions against the data directory major version and your operator's upgrade workflow.

## 14. Managed PostgreSQL Cloud Services

On managed services such as Amazon RDS for PostgreSQL, Google Cloud SQL for PostgreSQL, or Azure Database for PostgreSQL, users typically **lack shell access to the underlying host OS**.

You can still run:

```sql
SHOW server_version;
SELECT version();
SHOW log_destination;
```

however, access to read `config_file`, `data_directory`, or raw log files may be restricted; managed platforms use parameter groups, consoles, APIs, or centralized log services instead.

In such environments:

- Identify the instance/cluster via the cloud provider console.
- Use the service's official log export/viewing features.
- Follow the platform's parameter update and restart mechanisms.
- Do not assume the managed database admin role equals a self-hosted PostgreSQL `SUPERUSER`.

On managed PostgreSQL, some parameters may be locked by the provider. If `SHOW` returns a value differing from expectations, check parameter groups or service-level policies rather than trying to edit host files you do not own.

## 15. An Early Readiness Check Tool: pg_isready

`pg_isready` checks endpoint readiness **without requiring a full SQL session**:

```bash
pg_isready -h 127.0.0.1 -p 5432
```

Common exit codes:

| Exit code | Meaning |
| ---: | --- |
| `0` | Server is accepting connections. |
| `1` | Server responded but is currently rejecting connections, e.g., still starting up. |
| `2` | No response from the target server. |
| `3` | Check could not run due to invalid arguments or similar usage error. |

Typical output messages:

```text
127.0.0.1:5432 - accepting connections
127.0.0.1:5432 - rejecting connections
127.0.0.1:5432 - no response
```

**Limitation:** "accepting connections" does not guarantee the application's user/password/database is valid or that business SQL can execute. After `pg_isready`, test an actual `psql` connection with real credentials and run `SHOW server_version`.

## 16. Common Startup Errors and How to Identify Them

Never start by editing multiple files at once. Find the **first meaningful error message** from the exact startup attempt and instance, then verify version, config, data directory, and OS permissions.

### 16.1. Port Already in Use

Illustrative log messages:

```text
LOG:  could not bind IPv4 address "127.0.0.1": Address already in use
HINT: Is another postmaster already running on port 5432?
FATAL: could not create any TCP/IP sockets
```

Possibilities:

- Another PostgreSQL instance is already using `5432`.
- An older service has not finished shutting down.
- Another process holds the port.

On Linux, when authorized, inspect:

```bash
ss -ltnp
```

On Windows:

```powershell
Get-NetTCPConnection -LocalPort 5432 -ErrorAction SilentlyContinue
```

Identify the actual owning process before deciding to change ports or stop services. **Never kill a process by PID merely because it listens on `5432` without confirming which instance it belongs to.**

### 16.2. Wrong Path or Permission Error on Data Directory

Messages may include:

```text
could not access directory ...
Permission denied
data directory ... has invalid permissions
```

Possible causes:

- The service runs under a different OS user than the owner of the data files.
- Parent directories or volumes deny read/write traversal.
- ACLs/ownership on the data directory broke after copying or restoring.
- Volume mounts under Docker/Kubernetes lack proper permissions.

Check the **OS user running PostgreSQL**, permissions on every parent directory and the data directory, log directory write access, and mount options. Never set permissions to "world readable/writable" as a quick fix: databases hold sensitive data and operational secrets that must stay protected.

### 16.3. Syntax or Value Error in postgresql.conf

Messages may look like:

```text
LOG:    syntax error in file ".../postgresql.conf" line ...
FATAL:  configuration file ".../postgresql.conf" contains errors
```

Or invalid parameter names, out-of-range values, invalid port numbers, or mismatched quotes.

Resolution:

1. Locate the exact `config_file` read by the service.
2. Inspect that line and any `include` files.
3. Compare against the last known working config.
4. Fix the exact error in a controlled manner.
5. Start using the proper service manager and re-check logs.

If the server is still running and the error appeared during reload, `pg_file_settings` and `pg_settings.pending_restart` help pinpoint it; if the server cannot start, inspect logs/stderr and config files directly.

### 16.4. Data Directory Belongs to a Different Major Version Than the Binary

A common message for this error:

```text
FATAL: database files are incompatible with server
DETAIL: The data directory was initialized by PostgreSQL version ...
```

For example: the data directory was initialized by major 16 while the process runs PostgreSQL 17 binaries.

**Never manually edit `PG_VERSION` to trick the server.** Data formats and WAL layouts can be incompatible across major versions. Use binaries matching the data directory's major version to start it, or follow a supported major upgrade workflow such as `pg_upgrade` or dump/restore.

### 16.5. Out of Disk Space

Messages may contain:

```text
No space left on device
could not write file ...
could not create file ...
```

Check the data volume, WAL volume, log directory, and temporary files filesystem. When disks fill up, PostgreSQL cannot create files, write WAL, or extend tables. Never arbitrarily delete files in `pg_wal` or the data directory to free space; doing so can destroy database integrity and recoverability.

Fixes must address the root cause: safely free space elsewhere, expand volumes, apply log/backup retention policies, or perform proper recovery.

### 16.6. postmaster.pid and an Already Running Instance

Illustrative error:

```text
FATAL: lock file "postmaster.pid" already exists
HINT: Is another postmaster (PID ...) running in data directory ...?
```

`postmaster.pid` helps verify which instance owns the data directory. **Never delete this file reflexively.** First verify:

- Is PostgreSQL actually running and using that exact data directory?
- Does the PID inside the file belong to a live process?
- Which service/cluster manager owns the instance?
- Is recovery or a restart still in progress?

Only after confirming beyond doubt that no process uses the data directory should you follow documented stale-PID cleanup procedures. Deleting it while another server uses the directory can cause severe data corruption.

### 16.7. pg_hba.conf or Authentication Errors

Examples:

```text
FATAL: no pg_hba.conf entry for host ..., user ..., database ...
FATAL: password authentication failed for user ...
```

These messages indicate the server **is already accepting connection attempts**, yet the account, source host, SSL mode, or authentication method failed checks.

Check:

```sql
SHOW hba_file;
```

With admin privileges on a running server, inspect:

```sql
SELECT line_number, type, database, user_name,
       address, auth_method, error
FROM pg_hba_file_rules
ORDER BY line_number;
```

`pg_hba_file_rules` displays parsed HBA rules from disk. Inspect errors, rule ordering, and host ranges. After editing HBA, reload according to your environment's workflow; HBA reload behavior has platform-specific nuances in some cases. Never open all sources or enable broad `trust` just to avoid password errors.

### 16.8. Resource Limits or Recovery Failures

Logs may report inability to allocate shared memory, exhausted OS limits, unreadable WAL segments, failed recovery, or invalid checkpoint settings.

These errors require reading the **full message, `DETAIL`/`HINT`, storage health, and configuration**. On production data, never run low-level repair utilities or delete WAL segments based on random Internet tips without verified backups and approved recovery procedures.

## 17. Distinguishing Server Startup Errors from Application Errors

Not every PostgreSQL connection error originates at startup. Examples:

| Symptom | Initial Classification | Verification Step |
| --- | --- | --- |
| `pg_isready`: no response | Server or network path unreachable | Check service, port, network, and startup logs. |
| `FATAL: database files are incompatible with server` | Binary/cluster major version mismatch | Compare binary version and data directory version. |
| `database system is ready to accept connections`, yet client fails | Likely auth, network, or database issue | Check endpoint, HBA, user, password, and firewall. |
| `password authentication failed` | Authentication rejected | Check role, secret, HBA, SSL, and source IP. |
| `database "appdb" does not exist` | Target DB missing or misspelled | Connect to the right DB; list DBs with an authorized account. |
| `relation "orders" does not exist` | Schema/`search_path`/query issue | Check database, schema, migrations, and `search_path`. |
| Server restarted and app sees connection reset | Stale connections dropped | Check connection pool, retry logic, and restart logs. |

A startup log showing the server is ready does not guarantee migrations ran, app roles have privileges, or a proxy in front of the DB is healthy. Diagnose at the **failing layer**.

## 18. A Read-Only Inspection Workflow That Modifies No Data

Most checks in this lesson are **read-only**. A safe inspection sequence on a running instance:

### Step 1: Identify the Endpoint

```sql
SELECT
    current_database() AS db,
    current_user AS db_user,
    inet_server_addr() AS server_ip,
    inet_server_port() AS server_port,
    pg_postmaster_start_time() AS started_at;
```

Record the environment name and the endpoint used by your application. If behind a proxy or load balancer, verify the actual backend member too.

### Step 2: Confirm Version

```sql
SHOW server_version;
SHOW server_version_num;
SELECT version();
```

Never substitute package metadata or image tags for the live running server version.

### Step 3: Identify Configuration Files and Data Directory

```sql
SHOW config_file;
SHOW hba_file;
SHOW ident_file;
SHOW data_directory;
```

If lacking permissions, ask an administrator to verify rather than elevating an application account.

### Step 4: Read Active Values and Pending-Restart Status

```sql
SELECT
    name, setting, unit, context, source, pending_restart
FROM pg_settings
WHERE name IN (
    'port', 'listen_addresses', 'max_connections',
    'shared_buffers', 'logging_collector',
    'log_destination', 'log_directory', 'log_filename'
)
ORDER BY name;
```

If you edited a config file and the active value has not updated, inspect `source`, `pending_restart`, and reload/restart logs.

### Step 5: Locate the Log Destination

```sql
SHOW logging_collector;
SHOW log_destination;
SHOW log_directory;
SHOW log_filename;

SELECT pg_current_logfile();
```

If `pg_current_logfile()` returns `NULL`, check stderr/journal/container logging or the corresponding configured destination.

### Step 6: Correlate Logs with Startup Time

Look for lines around `pg_postmaster_start_time()`:

```text
starting PostgreSQL ...
listening on ...
database system is ready to accept connections
```

If no "ready" line appears, inspect preceding errors and service state. If the server has been running for a long time, startup logs may have been rotated or archived, so search by timestamp and retention policy.

### Step 7: Test Connectivity Like an Application

```bash
pg_isready -h 127.0.0.1 -p 5432
```

Then connect with the application's actual account and database to run a simple read query, if permitted. Confirming an open port is not enough; verify authentication and target database privileges as well.

## 19. Hands-On Practice on a PostgreSQL Lab

These exercises require a test PostgreSQL instance. Read-only queries make no changes; startup and config edits should only be done in an authorized learning environment.

### Exercise 1. Distinguishing Server and Client Versions

In a terminal:

```bash
psql --version
```

Inside a connected `psql` session:

```sql
SHOW server_version;
SHOW server_version_num;
```

**Task:** record all three values. If `psql --version` differs from `server_version`, explain why that is not necessarily an error.

**Hint:** the client has its own version; the server is what parses and executes SQL statements.

### Exercise 2. Distinguishing Config and Data Directories

```sql
SELECT
    current_setting('config_file') AS config_file,
    current_setting('data_directory') AS data_directory;
```

**Task:** check whether both paths reside in the same directory. If they differ, identify how your installation manages config files.

**Hint:** many Linux packages separate config and data directories; do not assume one universal default location.

### Exercise 3. Tracing Configuration Sources

```sql
SELECT name, setting, context, source, pending_restart
FROM pg_settings
WHERE name IN ('shared_buffers', 'port', 'log_min_duration_statement')
ORDER BY name;
```

**Task:** identify which parameters require a restart and which can apply via reload/session based on `context`.

**Hint:** `shared_buffers` and `port` typically require a restart due to `postmaster` context. `log_min_duration_statement` can be applied via supported reload/session mechanisms without restarting the server.

### Exercise 4. Identifying Log Sources

```sql
SHOW logging_collector;
SHOW log_destination;
SHOW log_directory;
SELECT pg_current_logfile();
```

**Task:** determine whether logs reside in PostgreSQL files or in stderr/journal/container logs.

**Hint:** if the collector is off and `pg_current_logfile()` returns `NULL`, check how your service/container captures stderr instead of hunting for an imaginary default file.

### Exercise 5. Checking Connection Paths

```bash
pg_isready -h 127.0.0.1 -p 5432
```

If this outputs "no response", list at least three hypotheses before editing any configuration.

**Hint:** server stopped, wrong port, not listening on TCP at that address, firewall, or wrong target address.

### Exercise 6. Issue After Changing Port

An administrator edits `postgresql.conf`:

```conf
port = 5433
```

then runs only `SELECT pg_reload_conf();` and sees the server still listening on `5432`.

**Explanation:** `port` requires a restart and does not take effect on reload alone. Check `pg_settings.pending_restart`, plan a restart, and verify `SHOW port` and `listening on ...` in the logs.

### Exercise 7. Suspecting "Server Is Running the Wrong Binary"

Terminal reports:

```text
postgres --version    -> PostgreSQL 17.x
SHOW server_version   -> PostgreSQL 16.x
```

**Explanation:** `postgres --version` may simply find a different binary in `PATH` than the running instance. Before touching the data directory, inspect the service startup command and the binary attached to the running process. Never swap a running server's binaries just to make two commands print matching versions.

### Exercise 8. Classifying Errors from Logs

Scenarios:

1. `Address already in use`.
2. `database files are incompatible with server`.
3. `no pg_hba.conf entry`.
4. `No space left on device`.
5. `database system is ready to accept connections`.

**Answers:**

1. Inspect port/process conflicts or listen addresses.
2. Check major versions of the binary and data directory.
3. Primarily an authentication/connection-layer issue, not a startup failure.
4. Check filesystem/volume/WAL/log usage and follow safe cleanup procedures.
5. Indicates the server reached ready state for accepting connections, without guaranteeing all clients/apps can authenticate or query.

## 20. Common Misconceptions to Avoid

**Misconception 1: "`psql --version` is the version of the running database."** False. That is the client version; check the server via `SHOW server_version`.

**Misconception 2: "`postgresql.conf` is always inside the data directory."** False. Many packages separate config and data directories, and the server can be passed an explicit `config_file`.

**Misconception 3: "I edited the right file, so the setting is definitely active."** Not necessarily. It may be overridden, shadowed by an include, or awaiting a restart. Use `pg_settings` and logs.

**Misconception 4: "`pg_reload_conf() = true` means all changes succeeded."** False. It only confirms the reload signal was sent; you must still check active settings, `pending_restart`, and log errors.

**Misconception 5: "`logging_collector = off` means PostgreSQL produces no logs."** False. Logs may be written via stderr, systemd journal, or container runtime.

**Misconception 6: "`pg_current_logfile() = NULL` means startup had no errors."** False. The function returns NULL when another logging mechanism is used, even if errors exist in the journal.

**Misconception 7: "systemctl showing active guarantees the application works."** False. Verify the exact instance/unit, port, readiness, and application authentication.

**Misconception 8: "`PG_VERSION` tells you the server's minor patch version."** False. It identifies the cluster data format at the major level only, not `SHOW server_version` or the binary patch version.

**Misconception 9: "Deleting `postmaster.pid` fixes any lock file error."** Very dangerous. Always verify beyond doubt that no process uses the data directory before handling a stale PID file.

**Misconception 10: "Deleting WAL files is a safe way to free disk space."** False. WAL is tied to crash recovery and data integrity; deleting WAL arbitrarily can corrupt the database.

**Misconception 11: "Startup logs are always in a PostgreSQL log file."** They may live in the journal, Windows Event Viewer, container logs, or a managed service's log console.

**Misconception 12: "If the server is ready, all SQL will work."** Ready only confirms connection acceptance at a basic level; authentication, migrations, privileges, schemas, and app logic still require verification.

## 21. Conclusion

To inspect a PostgreSQL installation, always distinguish the **installed binaries**, the **running client**, and the **actual server connected to by your application**. Once the server is running, `SHOW server_version`, `SHOW config_file`, `SHOW data_directory`, `SHOW hba_file`, and `pg_settings` are reliable starting points. To locate logs, check `log_destination`, `logging_collector`, `log_directory`, `pg_current_logfile()`, and your OS/container logging mechanism.

When PostgreSQL fails to start, SQL is unavailable; shift to inspecting the **service definition, exact binary, exact data directory, and failed startup logs**. Read the very first root-cause message before altering configs, and avoid deleting `postmaster.pid` or data/WAL files by guesswork. Finally, test from the application's perspective using the exact host, port, user, and database to confirm the instance is truly ready.

Good PostgreSQL diagnostics never start with "tweaking a few parameters at random"—they start by **confirming the exact server, exact version, exact config files, and exact log lines**.
