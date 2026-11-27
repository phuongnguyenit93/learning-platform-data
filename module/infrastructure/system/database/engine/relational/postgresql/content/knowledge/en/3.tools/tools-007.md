# Managing Connection Information with Service Files and .pgpass in PostgreSQL

When working with PostgreSQL, users often repeat many connection parameters across `psql`, `pg_dump`, `pg_restore`, or programs built on `libpq`:

```bash
psql -h db.internal.example -p 5432 -U report_reader -d shopdb
pg_dump -h db.internal.example -p 5432 -U report_reader -d shopdb -Fc -f shopdb.dump
```

Copying these details across scripts makes it easy to mistype a hostname, confuse staging with production, forget TLS settings, or repeatedly type passwords. PostgreSQL provides two client-side mechanisms to solve these problems:

- **Connection service file**: assigns a name to a group of connection parameters, e.g., `[shop_staging_ro]`, so clients only need `service=shop_staging_ro`.
- **Password file**: contains lines matching host/port/database/user to a password, allowing tools to authenticate automatically without exposing passwords on the command line.

On Linux/macOS, the personal files are normally named **`~/.pg_service.conf`** and **`~/.pgpass`**. On Windows, the default paths are typically **`%APPDATA%\postgresql\.pg_service.conf`** and **`%APPDATA%\postgresql\pgpass.conf`**.

These two files perform **different yet complementary** jobs. The service file selects the right connection target; the password file supplies credentials for that connection. They do **not** create databases, grant SQL privileges, open firewalls, or replace server-side authentication and TLS.

After this lesson, you will be able to create service files, use `.pgpass` with the proper format and permissions, understand parameter precedence, invoke `psql`/`pg_dump` from scripts, and troubleshoot common issues.

> **Scope:** These mechanisms are features of **libpq**, the PostgreSQL client library. Standard tools like `psql` and `pg_dump` use libpq; however, do not assume every PostgreSQL driver in every language—especially pure Java JDBC—reads service files and password files the way libpq does.

## 1. A practical scenario

Suppose a development team manages three environments:

| Label in this lesson | Server | Port | Database | Role |
|---|---|---:|---|---|
| Dev | `127.0.0.1` | 5432 | `shopdb_dev` | `dev_user` |
| Staging | `stg-db.internal.example` | 5432 | `shopdb` | `report_reader` |
| Production | `prod-db.internal.example` | 5432 | `shopdb` | `report_reader` |

With a service file defined, you can run:

```bash
psql "service=shop_dev"
psql "service=shop_staging_ro"
pg_dump -d "service=shop_staging_ro" -Fc -f staging.dump
```

Instead of repeating each parameter, you only need a service name. When the staging hostname changes, you update the corresponding definition without rewriting every script. If the server requires a password, libpq looks up `.pgpass` matching the effective parameters.

To practice, you need PostgreSQL client tools installed, real target connection details, and a role with `LOGIN` and required privileges. The server must be running, and `listen_addresses`, port, firewall, and server-side `pg_hba.conf` must allow the connection.

## 2. What is a service file and where does it live?

A **service file** is an INI-formatted file containing multiple sections. Each section name is a service name; the section body contains `key=value` connection parameters.

Example:

```ini
# ~/.pg_service.conf

[shop_dev]
host=127.0.0.1
port=5432
dbname=shopdb_dev
user=dev_user
connect_timeout=5
application_name=shop_dev_cli

[shop_staging_ro]
host=stg-db.internal.example
port=5432
dbname=shopdb
user=report_reader
connect_timeout=10
application_name=shop_report_cli
sslmode=verify-full
sslrootcert=/home/linh/.postgresql/root.crt
```

Each section is a **named configuration**. For example, `shop_staging_ro` specifies host, database, user, and TLS certificate verification. The `_ro` suffix is merely a naming convention and **does not restrict the account to read-only access**; real permissions must be configured on the PostgreSQL role.

### 2.1. Personal file locations

| OS | Default path |
|---|---|
| Linux | `~/.pg_service.conf` |
| macOS | `~/.pg_service.conf` |
| Windows | `%APPDATA%\postgresql\.pg_service.conf` |

Windows example when the user profile is at `C:\Users\Linh`:

```text
C:\Users\Linh\AppData\Roaming\postgresql\.pg_service.conf
```

This is a **client-side** file, not a PostgreSQL server configuration file inside `PGDATA`. Whichever OS user runs the command is the user whose configuration libpq searches, unless overridden by an environment variable. A job running under a `backup` account does not automatically use the administrator's `~/.pg_service.conf`.

### 2.2. System-wide file and precedence between the two

In addition to the personal file, libpq can read a shared service file named **`pg_service.conf`** located in the PostgreSQL installation's configuration directory. When the corresponding tool is available:

```bash
pg_config --sysconfdir
```

identifies the system configuration directory for that `pg_config` binary. If multiple PostgreSQL versions are installed on the machine, check which version is resolved in `PATH`.

When both the personal file and the system-wide file define a service with **the same name**, the definition in **the personal file takes precedence**. Do not assume two identically named sections are merged; use distinct names and verify which file the client actually reads.

### 2.3. Selecting a different service file

The `PGSERVICEFILE` environment variable points to a **specific file**, replacing the default personal file location:

```bash
export PGSERVICEFILE="$HOME/config/services_pg.conf"
psql "service=shop_staging_ro"
unset PGSERVICEFILE
```

On Windows PowerShell:

```powershell
$env:PGSERVICEFILE = 'C:\Config\PostgreSQL\services_pg.conf'
psql "service=shop_staging_ro"
Remove-Item Env:PGSERVICEFILE
```

`PGSYSCONFDIR` sets the **directory** searched for the system-wide `pg_service.conf` file, not the path to a personal file:

```bash
export PGSYSCONFDIR=/etc/postgresql-client
psql "service=shop_staging_ro"
```

Distinguish clearly: `PGSERVICE` selects the **service name**; `PGSERVICEFILE` selects the **personal file**; `PGSYSCONFDIR` selects the **system configuration directory**.

## 3. Parameters to place in a service file

| libpq parameter | Role | Notes |
|---|---|---|
| `host` | Hostname or server address | For TLS `verify-full`, the hostname must match the certificate |
| `hostaddr` | TCP IP address used to connect | Understand interactions with `host`, TLS, and password file |
| `port` | PostgreSQL port | Defaults commonly to 5432, but may differ |
| `dbname` | Database name | Do not confuse with the service name |
| `user` | Role used to log in | Not the OS user running the process |
| `connect_timeout` | Connection wait limit (seconds) | Useful for non-interactive jobs |
| `application_name` | Client label for observability | Visible in `pg_stat_activity` |
| `sslmode` | TLS policy | `verify-full` requires certificate and hostname verification |
| `sslrootcert` | Trusted root CA path | File must exist and come from the proper trust anchor |
| `passfile` | Alternate password file | Must protect permissions on the file containing secrets |
| `target_session_attrs` | Server suitability requirement for multi-host strings | Use only when you clearly understand the topology |

You do not need to set every parameter. Omitted parameters fall back to environment variables or defaults. Do not place `password` directly in a service file even though libpq accepts it: service files are often shared across teams and easily copied; use a password file or a controlled secret management system instead.

### 3.1. A service for a local environment

```ini
[inventory_local]
host=127.0.0.1
port=5432
dbname=inventory
user=inventory_dev
connect_timeout=5
```

### 3.2. A service over a private network with TLS

```ini
[inventory_staging]
host=stg-db.internal.example
port=5432
dbname=inventory
user=inventory_reader
connect_timeout=8
sslmode=verify-full
sslrootcert=/home/linh/.postgresql/root.crt
application_name=staging_inventory_check
```

The hostname and CA path are **illustrative**; they cannot be used verbatim without matching DNS and certificates in your environment. With `verify-full`, do not change to `sslmode=disable` just to bypass verification errors; verify the hostname, CA, and server certificate properly.

## 4. Connecting by service name

Direct usage:

```bash
psql "service=inventory_local"
```

Libpq locates the `[inventory_local]` section, reads host/port/dbname/user, and opens the connection as permitted by the server.

### 4.1. Verifying the actual target after connecting

In `psql`, run:

```sql
SELECT
    current_database() AS ten_database,
    current_user AS role_hien_tai,
    inet_server_addr() AS server_ip,
    inet_server_port() AS server_port,
    current_setting('application_name') AS ten_ung_dung;
```

Or enter the meta-command:

```text
\conninfo
```

If the client connects via a Unix-domain socket, `inet_server_addr()` and `inet_server_port()` may return `NULL`. That alone does not mean the connection failed.

**Always verify database, role, and host before performing risky modifying operations**, especially when a machine hosts multiple instances or multiple services with similar names.

### 4.2. Selecting a service via an environment variable

Bash:

```bash
export PGSERVICE=inventory_local
psql
unset PGSERVICE
```

PowerShell:

```powershell
$env:PGSERVICE = 'inventory_local'
psql
Remove-Item Env:PGSERVICE
```

Environment variables help select a service for a group of commands in the same process/shell. If a script already passes `service=...` directly or has higher-precedence settings, verify the effective source rather than assuming `PGSERVICE` won.

### 4.3. Using services in pg_dump, pg_restore, and pg_isready

```bash
# Check whether the server accepts connections.
pg_isready -d "service=inventory_staging"

# Export a custom-format logical dump.
pg_dump -d "service=inventory_staging" \
    -Fc -f inventory_staging.dump

# Illustrative restore syntax; run ONLY in an authorized test environment.
pg_restore -d "service=inventory_local" \
    inventory_staging.dump
```

`pg_isready` does not prove a role can authenticate or has privileges on every table. `pg_dump` needs read privileges on the objects to back up. `pg_restore` modifies data/schema and requires its own plan; never run it merely to test connectivity.

## 5. Connection parameter precedence

When the same parameter is specified in multiple places, libpq resolves them **per parameter** in roughly this order:

```text
Higher priority
    1. Explicitly supplied connection parameters
       (e.g., in the connection string)
    2. Values read from the selected service file
    3. Corresponding environment variables (PGHOST, PGPORT, ...)
    4. libpq built-in defaults
Lower priority
```

Example service:

```ini
[shop_report]
host=stg-db.internal.example
port=5432
dbname=shopdb
user=report_reader
```

Suppose the shell has `PGPORT=5444`, and you run:

```bash
psql "service=shop_report port=5433"
```

The connection uses **port 5433**, because the explicit parameter takes precedence. If you omit `port=5433`, it uses **5432** from the service, not `PGPORT=5444`. Host, dbname, and user still come from the service unless overridden.

### 5.1. Common environment variables

| Variable | Corresponding parameter |
|---|---|
| `PGHOST` | `host` |
| `PGPORT` | `port` |
| `PGDATABASE` | `dbname` |
| `PGUSER` | `user` |
| `PGCONNECT_TIMEOUT` | `connect_timeout` |
| `PGSSLMODE` | `sslmode` |
| `PGSSLROOTCERT` | `sslrootcert` |
| `PGAPPNAME` | `application_name` |
| `PGSERVICE` | `service` |
| `PGPASSFILE` | `passfile` |

`PGPASSWORD` can supply a password, but is discouraged because environment variables risk exposure via process inspection tools, debuggers, and logs. A secret set in `PGPASSWORD` can also cause libpq **not to consult** the password file as you expected.

### 5.2. Avoiding confusion between service precedence and the password file

A service file does not perform authentication itself. Once final host/port/dbname/user values are resolved, libpq connects and, when a password is needed and not provided elsewhere, looks up the password file.

If a user overrides `user` or `host` in the connection string, the password file must contain a line matching **the final effective values**, not the original service values. This is a common cause of "the service is right, yet it still asks for a password."

## 6. Where does the .pgpass password file live?

A **password file** is a client-side file storing credentials for connection combinations.

| Platform | Default location |
|---|---|
| Linux/macOS/Unix-like | `~/.pgpass` |
| Windows | `%APPDATA%\postgresql\pgpass.conf` |

A common point of confusion on Windows:

```text
Service file:  %APPDATA%\postgresql\.pg_service.conf
Password file: %APPDATA%\postgresql\pgpass.conf
```

The password file name does **not** have a leading dot like `.pgpass` on Unix. An alternate password file can be specified with:

```bash
export PGPASSFILE="$HOME/secrets/pg_passwords"
psql "service=inventory_local"
```

Or by using the `passfile` connection parameter when the client supports libpq parameters.

### 6.1. Five-field format

Each line:

```text
hostname:port:database:username:password
```

All passwords below are **placeholders**, not real secrets:

```text
127.0.0.1:5432:inventory:inventory_dev:EXAMPLE_LOCAL_PASSWORD
stg-db.internal.example:5432:inventory:inventory_reader:EXAMPLE_STAGING_PASSWORD
```

Do not wrap fields in quotes. `:` separates fields; if an actual value contains special characters, escape them properly.

### 6.2. Line matching rules

Libpq scans top to bottom and uses **the first line** matching all connection fields.

Example:

```text
stg-db.internal.example:5432:inventory:inventory_reader:SECRET_A
127.0.0.1:5432:inventory:inventory_dev:SECRET_B
```

The `inventory_staging` service above declares host `stg-db.internal.example`, port `5432`, dbname `inventory`, and user `inventory_reader`, so the first line matches to provide the password.

If you run `psql "service=inventory_staging user=other_user"`, that line no longer matches because the effective username changed.

### 6.3. Wildcards and placing specific entries before general ones

The first four fields may use `*` to match any value:

```text
stg-db.internal.example:5432:inventory:inventory_reader:SPECIFIC_PASSWORD
stg-db.internal.example:5432:*:inventory_reader:STAGING_PASSWORD
*:5432:*:inventory_dev:GENERIC_DEV_PASSWORD
```

Because **the first matching line wins**, always put specific lines ahead of wildcard lines. If you write:

```text
*:*:*:*:GENERIC_PASSWORD
stg-db.internal.example:5432:inventory:inventory_reader:SPECIFIC_PASSWORD
```

then the broad first line intercepts every match before the specific line is reached. Avoid `*:*:*:*` in multi-server environments: it can send the wrong password to an unexpected host and complicate troubleshooting.

### 6.4. Escaping colons and backslashes

Because `:` delimits fields, literal `:` and `\` inside a value must be escaped with a backslash:

```text
# Illustrative password: pass:word\example
db.internal.example:5432:shopdb:app_user:pass\:word\\example
```

`\:` represents a literal colon; `\\` represents a literal backslash. Do not add arbitrary escapes to other characters unnecessarily.

### 6.5. Hostnames vs. IP addresses and Unix socket connections

Password matching depends on `host`; if `host` is unset and `hostaddr` is set, libpq considers `hostaddr`; if neither is set, it matches against `localhost`. Special rules apply for Unix-domain sockets in the default socket directory.

Therefore:

- `host=localhost` and `host=127.0.0.1` are **two different strings**.
- A password file with only `localhost:5432:...` will not match a service specifying `host=127.0.0.1`.
- With custom socket directories, verify how libpq derives the hostname field for matching.
- Whenever `host`, `port`, `dbname`, or `user` changes, review the corresponding `.pgpass` entries.

## 7. .pgpass permissions on Unix: mandatory security requirement

Password files store **plaintext** passwords. On Linux/macOS/Unix, libpq **ignores the file** if permissions allow group or other access. Typical setup:

```bash
# Create the file with restrictive umask if it does not exist yet.
umask 077
touch "$HOME/.pgpass"

# Owner read/write only.
chmod 600 "$HOME/.pgpass"

# Verify owner and mode.
ls -l "$HOME/.pgpass"
```

Example permissions:

```text
-rw------- 1 linh linh ... /home/linh/.pgpass
```

`0600` means:

- Owner: read and write.
- Group: no permissions.
- Other: no permissions.

A file with `-rw-r--r--` (`0644`) will be **ignored** by libpq on Unix for password lookup. Non-interactive scripts will then fail due to a missing password.

Never work around this by changing `pg_hba.conf` to `trust` or making the password file world-readable. Set the proper permissions, owner, file path, and client execution account.

### 7.1. Are service file permissions checked the same way as .pgpass?

You should still protect `~/.pg_service.conf`, for example:

```bash
chmod 600 "$HOME/.pg_service.conf"
```

However, distinguish carefully: PostgreSQL explicitly enforces **ignoring files with overly broad group/other permissions** on **password files**. Service files should not hold secrets, and a system-wide service file may be shared in a controlled manner. Do not conflate the two file types.

### 7.2. Windows: using NTFS ACLs

On Windows, libpq does not enforce a Unix `0600` mode check; it assumes the user profile is already protected. Still, passwords remain plaintext, so you must enforce **NTFS ACLs**.

PowerShell commands to locate the file and inspect its ACL:

```powershell
$file = Join-Path $env:APPDATA 'postgresql\pgpass.conf'
Write-Output $file

if (Test-Path -LiteralPath $file) {
    Get-Acl -LiteralPath $file | Format-List
}
```

Only the account that needs it and authorized administrators should have read access. Never place the file in public folders, broad network shares, repositories, emails, or tickets.

**Note:** Windows Task Scheduler jobs may run under a different account than your interactive PowerShell session. That account has a different `APPDATA` path and ACLs; always verify the actual execution context.

## 8. End-to-end example combining both files

Assume a development PostgreSQL instance is running on `127.0.0.1:5432`, and database `inventory` with role `inventory_dev` already exists.

### Step 1 — Create the service file

Contents of `~/.pg_service.conf`:

```ini
[inventory_local]
host=127.0.0.1
port=5432
dbname=inventory
user=inventory_dev
connect_timeout=5
application_name=inventory_tutorial
```

### Step 2 — Create the password file

Contents of `~/.pgpass`:

```text
127.0.0.1:5432:inventory:inventory_dev:EXAMPLE_PASSWORD_REPLACE_ME
```

Replace the placeholder with a valid password via an approved secret management workflow. Never copy real passwords into lessons or Git.

### Step 3 — Set permissions

```bash
chmod 600 "$HOME/.pgpass"
chmod 600 "$HOME/.pg_service.conf"
```

### Step 4 — Test non-interactive connection

```bash
psql -w "service=inventory_local" \
    -c "SELECT current_database(), current_user;"
```

The `-w`/`--no-password` option tells `psql` **not to prompt interactively for a password**. If the credential file is wrong or missing, the command errors immediately rather than hanging at a prompt. It does not bypass server authentication checks.

### Step 5 — Verify the active service

```bash
psql "service=inventory_local" -c "SELECT current_database();"

psql "service=inventory_local application_name=one_off_check" \
    -c "SELECT current_setting('application_name');"
```

The second command overrides `application_name` for that invocation to demonstrate explicit-parameter precedence. Avoid passing `-h`, `-p`, and `-U` casually while trying to verify the exact values loaded from a service.

## 9. Using in cron, CI, and backup jobs

A job that works in an interactive terminal yet fails in automation usually fails because the runtime environment differs, not because PostgreSQL "forgot" the service.

### 9.1. Sample Bash script

```bash
#!/usr/bin/env bash
set -euo pipefail

export PGSERVICEFILE=/etc/myapp/pg_services.conf
export PGPASSFILE=/etc/myapp/pg_passwords.secret

mkdir -p /var/backups/myapp

pg_dump -w -d "service=inventory_staging" \
    -Fc -f /var/backups/myapp/inventory_staging.dump
```

In real systems, the account running the job must have read access to both files and write access to the backup directory. On Unix, the password file still requires permissions denying group/other access. Paths under `/etc` are illustrative; use secret stores, volumes/permissions, and organizational policies appropriate to your platform.

`pg_dump` produces a logical dump. It does not automatically capture cluster-wide objects like global roles/tablespaces and does not replace physical/WAL backups when point-in-time recovery is required. Verify backups using actual restore tests.

### 9.2. Why can't cron find the service?

Typical causes:

- The job runs under a different account, so `HOME` and personal files differ.
- `PGSERVICEFILE` or `PGPASSFILE` is not set inside the job.
- Relative paths resolve from a different working directory.
- The password file lacks read permissions for the running account.
- On Unix, the password file has overly permissive mode bits and is ignored by libpq.
- Inherited `PG*` variables unexpectedly override some parameters.
- `psql`/`pg_dump` in cron's `PATH` comes from a different PostgreSQL installation.

Use absolute paths, verify the execution account, inspect the environment safely, and never dump all environment variables to logs where `PGPASSWORD` or other secrets could leak.

### 9.3. Windows Task Scheduler

PowerShell example for the task execution account:

```powershell
$env:PGSERVICEFILE = 'C:\Config\PostgreSQL\services.conf'
$env:PGPASSFILE = 'C:\Secrets\PostgreSQL\pgpass.conf'

& 'C:\Program Files\PostgreSQL\bin\psql.exe' -w "service=inventory_local" -c "SELECT 1;"
```

The binary path is illustrative; replace it with the actual `psql.exe` installation path. With Task Scheduler, grant NTFS ACL access on the secret file to the exact service account; do not assume the administrator's profile will be used.

## 10. Interaction with TLS and server permissions

A service can specify connection security requirements:

```ini
[prod_readonly]
host=prod-db.internal.example
port=5432
dbname=shopdb
user=report_reader
sslmode=verify-full
sslrootcert=/home/linh/.postgresql/root.crt
connect_timeout=8
```

`sslmode=verify-full` checks the CA/server certificate and hostname. If the certificate is only valid for `prod-db.internal.example` and the service is changed to an uncertified IP, verification will fail. Never disable TLS verification just to get past an error when policy requires protection against misdirected or spoofed servers.

**A service name never guarantees read-only permissions.** If `report_reader` has `INSERT`/`DELETE` due to mistaken `GRANT` statements, naming the service `prod_readonly` will not stop writes. Create least-privilege roles and restrict access properly via `pg_hba.conf`, firewalls, and authentication.

### 10.1. Files not to confuse

| File | Side | Purpose |
|---|---|---|
| `.pg_service.conf` | libpq client | Groups connection parameters under a service name |
| `.pgpass` / `pgpass.conf` | libpq client | Looks up passwords by host/port/database/user |
| `postgresql.conf` | PostgreSQL server | Configures listeners, memory, and server parameters |
| `pg_hba.conf` | PostgreSQL server | Connection authentication policy |
| `pg_ident.conf` | PostgreSQL server | Identity mapping for certain authentication methods |

Editing client files **does not change** server listeners or server permissions. Changing the server port from 5432 to 5433 requires updating service files, `.pgpass`, firewalls, and related clients/monitoring.

## 11. Which clients actually support these files?

| Client | Can use service/.pgpass like libpq? | Notes |
|---|---|---|
| `psql` | Yes | PostgreSQL tool built on libpq |
| `pg_dump` | Yes | Uses connection settings, still needs backup privileges |
| `pg_restore` | Yes when connecting directly to DB | Be careful as restore modifies data/schema |
| `pg_isready` | Uses libpq parameters | Checks only server readiness, not role permissions |
| C apps using libpq | Yes | When parameters, files, and environment are passed properly |
| libpq-based Python drivers | Usually yes | Depends on driver/version and DSN format |
| Pure Java PostgreSQL JDBC | Not by default | Has its own config mechanism; do not assume libpq behavior |
| Other GUIs/ORMs/drivers | Product-dependent | May use OS credential stores or custom formats |

Therefore, a file read successfully by `psql` is not proof that a Java application reads the same file. Always verify the documentation and configuration of your actual connection library.

## 12. Diagnosing when service or .pgpass does not work

### 12.1. Service not found

Error like:

```text
definition of service "inventory_local" not found
```

Check the section name, OS account, personal file path, `PGSERVICEFILE`, `PGSYSCONFDIR`, and duplicate service names. On Windows, verify the personal filename is **`.pg_service.conf`**, not confused with `pgpass.conf`.

### 12.2. .pgpass exists yet psql still prompts for a password

Check in order:

1. Is the file in the home/profile of the OS user running the client?
2. On Unix, does the file have `0600` or sufficiently strict permissions?
3. Does the entry match the exact host/port/dbname/user **after overrides**?
4. Do specific lines appear before wildcard lines?
5. Are `:` and `\` escaped properly?
6. Is `PGPASSWORD` or another `password` parameter taking precedence?
7. Is the server actually requesting password auth rather than another method?

Test with:

```bash
psql -w "service=inventory_local" -c "SELECT 1;"
```

`-w` lets the task fail cleanly without hanging on a prompt. Never print `.pgpass` contents to logs while debugging.

### 12.3. Parameters are right, yet the server rejects the connection

| Symptom | Where to check |
|---|---|
| `Connection refused` | PostgreSQL not running, wrong port, or `listen_addresses` |
| TCP timeout | Routing, DNS, firewall, cloud security group |
| `no pg_hba.conf entry` | Server rule missing for client host/user/database/SSL |
| `password authentication failed` | Wrong password, role, or authentication method |
| `database does not exist` | Wrong `dbname` or connected to wrong cluster |
| `role does not exist` | Wrong `user` or role not yet created |
| Certificate verification error | CA, hostname, server cert, or TLS policy |
| `permission denied for schema/table` | Missing SQL privileges after login |

Never change `pg_hba.conf` to `trust` or open wide firewall rules just to fix a service file issue. These errors belong to distinct connection layers.

### 12.4. A service points to the wrong environment

In systems with production, the most dangerous failure is **connecting successfully to the wrong database**. Causes include identically named services across personal and system files, `PGSERVICEFILE` pointing elsewhere, explicit parameter overrides on `host`, or DNS changes.

Before `DROP`, migrations, restores, or data modifications, always verify:

```sql
SELECT current_database(), current_user, inet_server_addr(), inet_server_port();
```

Also separate credentials and permissions between production and test environments so a misdirected connection does not immediately hold destructive privileges.

## 13. Password security and long-term operations

`.pgpass` is convenient, but **stores secrets in plaintext**. Therefore you must:

- Maintain strict file permissions/ACLs.
- Keep secrets out of command lines, Git, emails, docs, and tickets.
- Use dedicated roles with only required privileges.
- Combine with TLS whenever traversing networks that require security.
- Rotate passwords and update files across all dependent jobs.
- Distinguish **trace/request IDs** in logs from secrets; never log passwords while debugging.
- Restrict backup permissions and storage locations, as dumps also contain sensitive data.

### 13.1. Password rotation

When rotating `report_reader`'s password on the server, any client using an outdated `.pgpass` entry will fail authentication. A proper rotation workflow includes:

1. Inventory all accounts and jobs using the credential.
2. Prepare the new secret through a secure distribution channel.
3. Update the secret in every task's profile/file/secret store.
4. Verify connectivity using `psql -w` or the actual client tool.
5. Revoke the old credential per policy; avoid leaving old secrets in unprotected backups.

Do not confuse rotating a role password on the server with editing `.pgpass`: the client file cannot alter a role's password on the server.

### 13.2. When should you avoid .pgpass?

In some infrastructures, organizations mandate secret managers, short-lived credentials, workload identities, or client certificates instead of static password files. Follow your organization's supported authentication mechanisms rather than forcing every setup into `.pgpass` just for simplicity.

If CI requires a password file, provision it temporarily via a secret store with tight permissions and delete it once the job finishes. Never embed secrets directly in repository workflow YAML files.

## 14. Checklist before sharing configurations

### 14.1. Service file

- [ ] Service names clearly distinguish dev/staging/production.
- [ ] You know whether personal or system-wide service files are being read.
- [ ] `host`, `port`, `dbname`, and `user` are verified.
- [ ] Appropriate `sslmode`/CA settings are configured when TLS is required.
- [ ] No real passwords are stored in shared files or Git.
- [ ] You understand explicit parameters override service files and environment variables.

### 14.2. Password file

- [ ] Placed at the path belonging to the OS account running the client.
- [ ] Every line has all five fields in the correct order.
- [ ] Specific entries precede wildcard entries.
- [ ] Colons `:` and backslashes `\` are properly escaped.
- [ ] On Unix, permissions deny group/other access; typically `0600`.
- [ ] On Windows, NTFS ACLs block unauthorized accounts.
- [ ] Passwords never appear in logs, Git, tickets, or config dumps.

### 14.3. Connection verification

- [ ] Tested `psql -w "service=..." -c "SELECT 1;"`.
- [ ] Verified database/role/host/port or `\conninfo`.
- [ ] Tested the actual target tool, such as `pg_dump`, under the real job account.
- [ ] Have an update plan when host, port, role, or password changes.

## 15. Practice exercises with solutions

### Exercise 1 — Create two distinct services

**Task:** create `inventory_dev` pointing to `127.0.0.1:5432`, database `inventory`, user `dev_user`; and `inventory_staging` pointing to `stg-db.internal.example:5432`, database `inventory`, user `read_user`, with full TLS verification.

**Sample solution:**

```ini
[inventory_dev]
host=127.0.0.1
port=5432
dbname=inventory
user=dev_user

[inventory_staging]
host=stg-db.internal.example
port=5432
dbname=inventory
user=read_user
sslmode=verify-full
sslrootcert=/home/linh/.postgresql/root.crt
```

Do not place passwords in the service file. The CA path is illustrative and must point to the real file.

### Exercise 2 — Create a matching password file

**Sample solution:**

```text
127.0.0.1:5432:inventory:dev_user:DEV_EXAMPLE_SECRET
stg-db.internal.example:5432:inventory:read_user:STAGING_EXAMPLE_SECRET
```

On Unix, store at `~/.pgpass` with `chmod 600`; on Windows, store at `%APPDATA%\postgresql\pgpass.conf` with proper ACLs.

### Exercise 3 — Which port wins?

The service file has `port=5432`, the environment has `PGPORT=5444`, and you run:

```bash
psql "service=inventory_dev port=5433"
```

**Answer:** Port **5433** wins because explicit parameters have highest precedence. If `port=5433` is omitted, **5432** from the service is used, not `PGPORT=5444`.

### Exercise 4 — Wildcard listed first

```text
*:*:*:*:GENERIC
stg-db.internal.example:5432:inventory:read_user:SPECIFIC
```

**Answer:** The first line matches every connection, so `SPECIFIC` is never reached. Place specific lines first and limit broad wildcards.

### Exercise 5 — Password exists yet psql still prompts

`~/.pgpass` on Linux has mode `0644`.

**Answer:** The file allows group/other read access, so libpq ignores it. Run:

```bash
chmod 600 "$HOME/.pgpass"
psql -w "service=inventory_dev" -c "SELECT 1;"
```

If it still fails, check the file owner, final resolved host/port/database/user, and other `password` sources.

### Exercise 6 — Hostname localhost vs. 127.0.0.1

The service uses `host=127.0.0.1`; the password file only has:

```text
localhost:5432:inventory:dev_user:EXAMPLE
```

**Answer:** It will not necessarily match. `localhost` and `127.0.0.1` are different strings in standard host matching. Add a line with `127.0.0.1` or align the matching rule consistently.

### Exercise 7 — Cron cannot find the service

Running `psql "service=inventory_dev"` works in your terminal, but cron running as user `backup` reports the service is not found.

**Answer:** Your personal file does not automatically exist in user `backup`'s home directory. Configure `PGSERVICEFILE`/`PGPASSFILE` using absolute paths, set proper permissions, and inspect cron's runtime environment.

### Exercise 8 — Does editing .pgpass require restarting PostgreSQL?

**Answer:** No. `.pgpass` is a client-side file read when opening new connections. Changing a role's password on the server is a separate action; new connections require matching credentials. Modifying server config like `pg_hba.conf` is a separate reload/restart process.

## 16. Summary and reference documentation

Remember the core principles:

1. **`.pg_service.conf`** maps a service name to host, port, database, role, and other connection parameters.
2. **`.pgpass`** (Windows: `pgpass.conf`) stores passwords as `hostname:port:database:username:password`, using **the first matching line**.
3. **Explicit parameters → service file → environment variables → defaults** is the basic precedence order when using services.
4. **On Unix, password files with overly permissive modes are ignored**; on Windows, proper NTFS ACLs are required.
5. **A service name does not replace SQL permissions, TLS, or firewalls**; password files do not create users or passwords on the server.
6. **Not every driver uses libpq**; rely on these mechanisms only when your client actually supports them.

Official PostgreSQL documentation:

- [Connection Service File](https://www.postgresql.org/docs/current/libpq-pgservice.html).
- [The Password File](https://www.postgresql.org/docs/current/libpq-pgpass.html).
- [Environment Variables](https://www.postgresql.org/docs/current/libpq-envars.html).
- [libpq Connection Strings](https://www.postgresql.org/docs/current/libpq-connect.html).

**Conclusion:** Service files let you invoke **the right connection configuration by a stable name**, while `.pgpass` supplies **matching credentials in an automatable way**. Combining them with strict file permissions, least-privilege roles, and proper TLS simplifies operating `psql`, `pg_dump`, and libpq-based tools while keeping secret exposure under control.
