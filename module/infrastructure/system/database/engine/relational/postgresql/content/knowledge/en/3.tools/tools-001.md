# Connecting with psql and Connection String Structure in PostgreSQL

After installing PostgreSQL, the first task is usually connecting to **the right server, the right port, the right database, and the right login role**. PostgreSQL provides the command-line tool `psql` for this purpose. In addition to familiar options like `-h`, `-p`, `-U`, and `-d`, `psql` also accepts a **connection string** following the **libpq** library format: a `key=value` list or a `postgresql://...` URI.

Understanding connection strings helps you:

- Log in to a local PostgreSQL instance or a server on the network.
- Distinguish between Unix socket connections and TCP/IP connections.
- Transfer connection configurations across terminals, scripts, containers, and development environments.
- Configure timeouts, application names, and TLS requirements.
- Avoid exposing passwords in command history, configuration files, or logs.
- Diagnose errors caused by the wrong server, wrong database, insufficient privileges, or an inappropriate authentication method.

This lesson uses modern PostgreSQL, and the examples apply across Linux, Windows, and macOS. All illustrative addresses, roles, and databases must be replaced according to your environment. The examples do not require connecting to a public Internet server.

## 1. Distinguishing psql, libpq, PostgreSQL server, and database

`psql` is a **client** program. It does not run a storage engine or store data tables itself; it opens a connection to a running **PostgreSQL server** process. The **libpq** library handles connection parameters, opens the session, negotiates authentication, and communicates using the PostgreSQL protocol.

```mermaid
flowchart LR
    A["User / Terminal"] --> B["psql client"]
    B --> C["libpq: host, port, dbname, user, TLS..."]
    C --> D["PostgreSQL server"]
    D --> E["Database learning_pg"]
    E --> F["Schemas and tables"]
```

A connection typically includes the following information:

| Information | Example | Meaning |
| --- | --- | --- |
| Host | `127.0.0.1` or `db.internal.example` | Address of the **PostgreSQL server**, not the user's browser address |
| Port | `5432` | TCP port PostgreSQL listens on |
| Database | `learning_pg` | Database in which the session will open |
| User | `learning_app` | PostgreSQL role used for authentication |
| Password / auth | Password, peer, or appropriate method | Proves identity according to the authentication configuration |
| TLS mode | `verify-full` | Specifies transport security requirements |
| Application name | `psql_lab` | Identifies the client type in monitoring tools |
| Connect timeout | `5` seconds | Time limit for attempting to establish a connection |

**Server, database, and schema are not the same concept.** A single PostgreSQL instance can manage multiple databases; each database in turn contains multiple schemas and tables. When connecting, libpq needs to select an initial database. You cannot directly query a table in another database simply by writing `other_database.public.table` as you would when querying tables within the same database.

### 1.1. Conditions for a successful connection

A connection attempt must pass through several independent steps:

```mermaid
flowchart TD
    A["psql receives parameters"] --> B{"Can reach host and port/socket?"}
    B -->|No| C["Network, port, or server error"]
    B -->|Yes| D{"Does pg_hba.conf allow the connection type?"}
    D -->|No| E["Authentication rule error"]
    D -->|Yes| F{"Does user authentication succeed?"}
    F -->|No| G["Password/peer/certificate error"]
    F -->|Yes| H{"Does database exist and is CONNECT permitted?"}
    H -->|No| I["Database or privilege error"]
    H -->|Yes| J["Session ready to run SQL"]
```

A successful connection **does not mean** the user can `SELECT` or `INSERT` on every table. PostgreSQL also checks privileges at the database, schema, table, sequence, function, and related object levels when executing SQL.

## 2. Checking tools and the server before connecting

In a Linux/macOS terminal:

```bash
psql --version
```

On Windows PowerShell, if `psql.exe` is already in `PATH`:

```powershell
psql --version
```

If it is not in `PATH` and you installed PostgreSQL in a typical directory, you can invoke it using the full path (for example, version 18):

```powershell
& "C:\Program Files\PostgreSQL\18\bin\psql.exe" --version
```

The number `18` is an example of a **major version**; the actual path depends on your installation.

`psql --version` only tells you the **client version**. To find out which version the connected server is running, after logging in run:

```sql
SELECT version();
SHOW server_version;
```

The two versions can differ; you should not infer that the server has been upgraded solely from the `psql` binary version.

If `pg_isready` is available, you can probe the server at an endpoint:

```bash
pg_isready -h 127.0.0.1 -p 5432
```

`pg_isready` checks whether the server responds and appears ready to accept connections; it **does not prove** that a specific username/password pair will log in successfully or have SQL privileges.

## 3. Basic connection using psql options

Common syntax:

```text
psql -h <host> -p <port> -U <user> -d <database>
```

This is a template, not a literal command to run. The `<...>` placeholders indicate values you need to supply.

### 3.1. TCP connection to a local server

```bash
psql -h 127.0.0.1 -p 5432 -U learning_app -d learning_pg
```

| Option | Long equivalent | Function |
| --- | --- | --- |
| `-h 127.0.0.1` | `--host=127.0.0.1` | Selects target host or Unix socket directory path |
| `-p 5432` | `--port=5432` | Selects port |
| `-U learning_app` | `--username=learning_app` | Selects login role |
| `-d learning_pg` | `--dbname=learning_pg` | Selects database |
| `-W` | `--password` | Explicitly requests a password prompt |
| `-w` | `--no-password` | Never prompt interactively for a password; useful for automation using another secret mechanism |

Example forcing a password prompt:

```bash
psql -h 127.0.0.1 -p 5432 -U learning_app -d learning_pg -W
```

**`-W` does not take a password as an argument.** When `-W` is present, `psql` prompts you to enter a password. Without `-W`, libpq may still prompt for a password when the server requires one and no other credential source is available.

Do not use `psql -W my_password` to pass a password: `my_password` is not a valid argument to `-W`. Avoid placing passwords on the command line or in URLs because shell history, process monitoring tools, and logs can expose secrets.

### 3.2. Connecting to a server on the network

```bash
psql -h db.internal.example -p 5432 -U report_reader -d reporting
```

This example assumes the organization has an internal hostname `db.internal.example`. For the connection to succeed, the server must listen on the appropriate network address, the firewall must allow the client source, `pg_hba.conf` must have a matching authentication rule, and the role must be granted the `CONNECT` privilege on the database.

**Do not expose a PostgreSQL port directly to the public Internet** just for testing. For remote servers, prefer a private network/VPN or protected access path, combined with TLS and least privilege.

### 3.3. Connecting without specifying all parameters

You can type concisely:

```bash
psql
```

However, this depends on libpq defaults, environment variables, and the operating system:

- The default user is usually **the operating system username running `psql`**, unless overridden by configuration.
- The default database usually has **the same name as the login user**.
- On Unix systems, when `host` is not specified, libpq typically tries a **Unix-domain socket** in the directory configured at build time.
- On Windows, the default connection behavior may differ; do not assume Windows supports the same socket path as Linux.
- The default port is usually **5432**, unless overridden by build/configuration or environment.

Therefore, `psql` without arguments may report `role "alice" does not exist` or `database "alice" does not exist` even when PostgreSQL is properly installed. In lessons and scripts, specify `-h`, `-p`, `-U`, and `-d` explicitly to avoid hidden environment dependencies.

## 4. Local connection via Unix socket vs. TCP

On Linux/macOS, PostgreSQL can allow local clients to connect via a **Unix-domain socket**. This connection does not use the same TCP stack as `127.0.0.1:5432`.

Examples on a Linux distribution with a socket in the appropriate directory:

```bash
# Use Unix socket with a specific socket directory:
psql -h /var/run/postgresql -U postgres -d postgres

# Force IPv4 TCP loopback:
psql -h 127.0.0.1 -p 5432 -U postgres -d postgres
```

The `/var/run/postgresql` directory is common on some Linux distributions but **is not fixed across all operating systems**. If `-h` is omitted, libpq uses the default socket path configured in the installation. On Ubuntu/Debian, you can log in as the administrative role via peer authentication using:

```bash
sudo -iu postgres psql -d postgres
```

Comparison:

| Connection | Transport | Authentication rules typically evaluated |
| --- | --- | --- |
| No `-h` on Unix | Unix socket per libpq default | `local` rules in `pg_hba.conf` |
| `-h /path/to/socket_dir` | Unix socket in the specified directory | `local` rules |
| `-h 127.0.0.1` | IPv4 TCP loopback | Matching `host`/`hostssl` rules |
| `-h ::1` | IPv6 TCP loopback | Host rules for IPv6 |
| `-h db.internal.example` | TCP to the server resolved by DNS | Host rules by source IP and TLS mode |

A role may be able to log in via socket using `peer` authentication while failing via TCP when no password has been set. **Do not conclude the server is "intermittent"** before distinguishing the protocol and corresponding `pg_hba.conf` rule.

## 5. What is a connection string?

Instead of splitting parameters across multiple CLI options, you can combine them into a single **connection string**. `psql` uses the connection string rules of **libpq**, which differ in several respects from the JDBC URL syntax used by Java applications.

Two common forms are:

1. **Keyword/value:** `host=... port=... dbname=... user=...`.
2. **URI:** `postgresql://user@host:port/database?parameter=value`.

Both describe the same connection endpoint, though they follow different escaping rules.

## 6. The libpq keyword/value format

A connection string can be written as `parameter_name=value` pairs separated by whitespace:

```bash
psql "host=127.0.0.1 port=5432 dbname=learning_pg user=learning_app"
```

Or specified explicitly via the `-d` option:

```bash
psql --dbname="host=127.0.0.1 port=5432 dbname=learning_pg user=learning_app connect_timeout=5 application_name=psql_lab"
```

Here:

- `host` selects the server.
- `port` selects the port.
- `dbname` selects the database.
- `user` selects the login role.
- `connect_timeout=5` limits the connection establishment time (in seconds).
- `application_name=psql_lab` helps identify the client in `pg_stat_activity`.

Libpq parameter names differ from some CLI option names: for example, `dbname` in a connection string corresponds to `-d` in `psql`.

### 6.1. When values contain spaces or special characters

In keyword/value format, values containing spaces can be enclosed in **single quotes** inside the string:

```bash
psql "host=127.0.0.1 port=5432 dbname='training space' user=learning_app"
```

This example only works if a database named `training space` actually exists; names with spaces are generally discouraged in learning environments. Libpq rules allow escaping single quotes and backslashes with a backslash when needed.

Distinguish between the two quoting layers:

- **Shell quoting**: the outer `"..."` ensures the terminal passes the connection string as a single argument.
- **Libpq quoting**: the inner `'...'` ensures a value containing spaces is parsed as a single parameter value.

If a parameter is overridden by combining a `-d` connection string with other CLI options, do not rely on ambiguous precedence; choose **one clear configuration source** for each parameter in scripts.

### 6.2. Common libpq parameters

| Parameter | Example | Purpose |
| --- | --- | --- |
| `host` | `db.internal.example` | Server hostname or Unix socket directory |
| `hostaddr` | `192.0.2.10` | Specific target IP address, which can avoid DNS lookup |
| `port` | `5432` | Connection port |
| `dbname` | `learning_pg` | Target database |
| `user` | `learning_app` | Login role |
| `connect_timeout` | `5` | Connection timeout in seconds |
| `application_name` | `psql_lab` | Application label |
| `sslmode` | `verify-full` | TLS policy |
| `sslrootcert` | `/path/to/ca.crt` | CA/trust material used to verify the server certificate |
| `passfile` | `/secure/path/pgpass` | Path to libpq password file |
| `service` | `training` | Selects configuration from a service file |
| `target_session_attrs` | `read-write` | Criteria for selecting a server when using multiple hosts |
| `options` | Valid session startup options | Sends server-supported session settings |

Not every parameter is needed for local connections. It is best to start with `host`, `port`, `dbname`, and `user`, and add only parameters that serve specific requirements.

## 7. URI format: postgresql://

Libpq supports URIs following this structure:

```text
postgresql://[user[:password]@][host][:port][/dbname][?param1=value1&param2=value2]
```

This is an illustrative structure; segments inside `[...]` are optional. In actual commands, **do not type these square brackets literally**.

Simple example:

```bash
psql "postgresql://learning_app@127.0.0.1:5432/learning_pg"
```

Equivalent in basic connection fields to:

```bash
psql "host=127.0.0.1 port=5432 dbname=learning_pg user=learning_app"
```

### 7.1. Adding parameters in the query string

```bash
psql 'postgresql://learning_app@db.internal.example:5432/learning_pg?sslmode=verify-full&connect_timeout=5&application_name=psql_lab'
```

Explanation:

| URI component | Value | Meaning |
| --- | --- | --- |
| Scheme | `postgresql://` | Uses the PostgreSQL connection string scheme |
| Userinfo | `learning_app@` | PostgreSQL login role |
| Host | `db.internal.example` | Target server |
| Port | `:5432` | TCP port |
| Path | `/learning_pg` | Database name |
| Query | `sslmode=verify-full` | Requires TLS and host identity verification |
| Query | `connect_timeout=5` | Connection establishment timeout |
| Query | `application_name=psql_lab` | Client label |

Libpq also accepts the `postgres://` scheme in common versions. When writing internal documentation, use `postgresql://` consistently for clarity.

**Note on `&`:** in many shells, `&` has command-control meaning. Wrap **the entire URI** in appropriate quotes as shown in the example, rather than pasting an unquoted URI with multiple query parameters.

### 7.2. Percent-encoding in URIs

Special characters in the user, password, database name, or URL parameters must be **percent-encoded** according to URI rules. Some examples:

| Original character | Encoded form |
| --- | --- |
| Space | `%20` |
| `@` | `%40` |
| `:` | `%3A` |
| `/` | `%2F` |
| `?` | `%3F` |
| `#` | `%23` |
| `%` | `%25` |

For example, if a real database is named `training space`, the URI path must be encoded:

```text
postgresql://learning_app@localhost:5432/training%20space
```

If a username contains `@`, it must also be encoded in the userinfo section. Do not write a URI with a literal `@` or `#` in a password and assume the client parses the host portion correctly.

In particular, **putting passwords directly in a URI is strongly discouraged**:

```text
# SYNTAX ILLUSTRATION ONLY; DO NOT USE THIS METHOD TO STORE REAL PASSWORDS:
postgresql://learning_app:EXAMPLE_PASSWORD@localhost:5432/learning_pg
```

URIs containing passwords can leak through shell history, configuration variables printed in logs, process inspection tools, copied URLs, or monitoring systems. Prefer prompts, a passfile, or a suitable secret manager.

### 7.3. URI differs from Java JDBC URL

Do not pass `jdbc:postgresql://...` literally to `psql`:

```text
# Libpq / psql:
postgresql://learning_app@localhost:5432/learning_pg

# PostgreSQL JDBC (Java application):
jdbc:postgresql://localhost:5432/learning_pg
```

Both describe a PostgreSQL connection, but they are parsed by **two different drivers**. Parameter names, values, and support for certain connection options may differ; consult the libpq documentation when using `psql` and the PostgreSQL JDBC documentation when using Java.

## 8. Setting up a practice environment to test connections

If you do not yet have a sample role/database, create them on the **PostgreSQL instance you are studying on**, via a `psql` session with a role that has `CREATEROLE` and `CREATEDB` or equivalent administrative privileges.

Example on Linux where distribution packages typically create the OS user `postgres`:

```bash
sudo -iu postgres psql -d postgres
```

On Windows, macOS, or custom setups, use an established administrative role; not every system supports the login method above. In the administrative psql session, run:

```sql
CREATE ROLE learning_app LOGIN;

CREATE DATABASE learning_pg OWNER learning_app;
```

Set a password for the role using the `psql` meta-command:

```text
\password learning_app
```

`\password` prompts for the new password and confirmation within `psql`'s flow, avoiding placing a real password in an `ALTER ROLE ... PASSWORD '...'` command stored in SQL history. In real environments, use a strong, unique password and store it via a secret management mechanism.

**`CREATE DATABASE` must run outside a transaction block.** In psql's default mode, this command runs standalone; do not wrap it in `BEGIN; ... COMMIT;`.

Then exit the administrative session:

```text
\q
```

Log in as the new role over TCP:

```bash
psql -h 127.0.0.1 -p 5432 -U learning_app -d learning_pg -W
```

If the server only permits local authentication via another method or uses a port other than 5432, adjust the configuration appropriately. Do not change `pg_hba.conf` to `trust` just to bypass password errors.

### 8.1. Verifying the active session after login

In `psql`:

```sql
SELECT
    current_user AS effective_role,
    session_user AS login_role,
    current_database() AS database_name,
    current_schema() AS schema_name;

SHOW server_version;
SHOW port;
```

Then:

```text
\conninfo
```

`\conninfo` displays current connection details such as database, user, host/socket, and port; on TLS-protected connections, the tool may also report SSL details depending on the client version.

**Note:** `current_user` can change via `SET ROLE` or execution contexts using elevated privileges; `session_user` remains tied to the login session's user under PostgreSQL semantics. When diagnosing permissions, inspect both if the application uses role switching.

## 9. Essential psql meta-commands

Once a `psql` session is connected, commands starting with `\` are **client meta-commands**, not SQL statements parsed directly by the server.

| Meta-command | Effect |
| --- | --- |
| `\conninfo` | Displays connection information |
| `\l` | Lists databases the user is permitted to view |
| `\du` | Lists roles and attributes |
| `\dn` | Lists schemas |
| `\dt` | Lists visible tables according to search path/pattern |
| `\d products` | Inspects the definition of table `products` |
| `\c learning_pg` | Switches connection to database `learning_pg` |
| `\c learning_pg learning_app 127.0.0.1 5432` | Reconnects with specified database/user/host/port |
| `\timing on` | Displays command execution time |
| `\x auto` | Automatically selects expanded output display when appropriate |
| `\pset pager off` | Disables the pager for long results |
| `\?` | Help for meta-commands |
| `\h SELECT` | SQL syntax help for `SELECT` |
| `\q` | Exits psql |

Example:

```text
learning_pg=> \conninfo
learning_pg=> \dt
learning_pg=> \timing on
learning_pg=> \x auto
learning_pg=> \q
```

`learning_pg=>` is an illustrative prompt, **not part of what you type**.

### 9.1. Changing databases with \connect

```text
\connect postgres
```

This switches to database `postgres` using the provided connection details or reusing existing ones per psql rules. After reconnecting, check `\conninfo`, especially if you also changed host, user, or port.

An active transaction cannot be "carried over" intact to another database via a reconnect. Finish or roll back any transaction before using `\connect`.

### 9.2. Trying a simple query

```sql
SELECT
    current_database() AS db_name,
    current_user AS role_name,
    now() AS server_transaction_time;
```

SQL statements end with `;`. In psql, an unterminated input line stays in the query buffer until you submit a complete statement. If you mistype something, the `\r` meta-command clears the current command buffer; `\q` exits the program.

## 10. libpq connection environment variables

To avoid repeatedly typing parameters, libpq provides **environment variables**. They are useful in development environments, scripts, and containers, though they must be used with care.

| Variable | Corresponds to | Example |
| --- | --- | --- |
| `PGHOST` | `host` | `127.0.0.1` |
| `PGPORT` | `port` | `5432` |
| `PGUSER` | `user` | `learning_app` |
| `PGDATABASE` | `dbname` | `learning_pg` |
| `PGCONNECT_TIMEOUT` | `connect_timeout` | `5` |
| `PGAPPNAME` | `application_name` | `psql_lab` |
| `PGSSLMODE` | `sslmode` | `verify-full` |
| `PGSSLROOTCERT` | `sslrootcert` | Path to CA certificate |
| `PGSERVICE` | `service` | `learning_local` |
| `PGPASSFILE` | `passfile` | Path to password file |
| `PGPASSWORD` | `password` | Supported, but should not be used as the default way to store secrets |

On Linux/macOS, set them for the current terminal session:

```bash
export PGHOST=127.0.0.1
export PGPORT=5432
export PGUSER=learning_app
export PGDATABASE=learning_pg
export PGCONNECT_TIMEOUT=5

psql -W
```

On Windows PowerShell:

```powershell
$env:PGHOST = "127.0.0.1"
$env:PGPORT = "5432"
$env:PGUSER = "learning_app"
$env:PGDATABASE = "learning_pg"
$env:PGCONNECT_TIMEOUT = "5"

psql -W
```

These environment variables apply only to the corresponding **process environment**; changing them does not modify server or role configuration. Parameters passed explicitly in a connection string/option can override environment defaults per libpq rules.

### 10.1. Do not use PGPASSWORD for long-term password storage

`PGPASSWORD` is recognized by libpq but has drawbacks: environment variables can appear in process inspection tools, crash reports, debugging systems, or configuration logs depending on platform and permissions. Whenever possible, prefer:

1. The `-W` prompt during manual operations.
2. A libpq-supported password file with strict file permissions.
3. Your deployment system's secret manager/credential store.
4. Other authentication mechanisms approved and managed by your organization.

Do not store real passwords in shell profile files or commit secret configurations to Git.

## 11. Using .pgpass/pgpass.conf to avoid repeated password entry

Libpq supports a **password file** for storing authentication credentials for matching connections. This is convenient for scripts, but the file must be carefully protected.

Default locations are typically:

| Platform | Password file location |
| --- | --- |
| Linux/macOS | `~/.pgpass` |
| Windows | `%APPDATA%\postgresql\pgpass.conf` |

Each line has the structure:

```text
hostname:port:database:username:password
```

Illustrative example (do not use sample passwords in practice):

```text
127.0.0.1:5432:learning_pg:learning_app:REPLACE_WITH_REAL_SECRET
db.internal.example:5432:reporting:report_reader:REPLACE_WITH_ANOTHER_SECRET
```

Libpq selects the **first matching** line. `*` can act as a wildcard for multiple values, though it broadens the match scope; use it only when genuinely needed. In a password file, colons and backslashes within a value must be escaped with a backslash according to the file syntax.

On Unix, the file must have sufficiently restrictive permissions, typically:

```bash
chmod 600 ~/.pgpass
```

Libpq may **ignore** the password file on Unix if its permissions are too permissive. On Windows, file access control relies on Windows ACLs; you must restrict access to the file containing secrets.

Once a valid file is in place, the command:

```bash
psql -h 127.0.0.1 -p 5432 -U learning_app -d learning_pg
```

can use the matched password without prompting. If the file does not match, is invalid, or has improper permissions, the connection may still prompt for a password or fail, depending on interactive options.

### 11.1. Using a custom passfile path

You can select a different password file via `PGPASSFILE` or the `passfile` parameter in a libpq connection string:

```bash
psql "host=db.internal.example port=5432 dbname=reporting user=report_reader passfile=/secure/path/to/pgpass"
```

Replace the path in the example with an actual file; on Windows use an appropriate Windows path. Having a passfile **does not encrypt the file at rest**. You must protect the file itself, its backups, and any OS accounts that can read it.

## 12. Using a service file to reuse multiple configurations

When frequently connecting to multiple environments such as development, staging, and reporting, you can define connections in a **libpq service file**.

Common locations include:

- Linux/macOS: `~/.pg_service.conf`.
- Windows: the service file in the PostgreSQL configuration directory under `%APPDATA%`, typically `%APPDATA%\postgresql\.pg_service.conf`.
- You can specify a path explicitly via the `PGSERVICEFILE` environment variable.

Example service file contents:

```ini
[learning_local]
host=127.0.0.1
port=5432
dbname=learning_pg
user=learning_app
connect_timeout=5
application_name=learning_psql

[reporting_internal]
host=db.internal.example
port=5432
dbname=reporting
user=report_reader
connect_timeout=5
sslmode=verify-full
sslrootcert=/secure/path/company-ca.crt
```

Replace the CA certificate path with the actual path on the OS using the service file. Do not place real passwords directly in this file without proper protection; combine it with a passfile or secret manager.

Connect using the service name:

```bash
psql "service=learning_local"
```

Or:

```bash
psql "service=reporting_internal"
```

Service files make scripts less dependent on specific hostnames/ports and keep configurations clearer. However, when changing a service file or `PGSERVICEFILE`, verify that scripts are reading the intended configuration; do not rely solely on identical service names across machines.

## 13. Secure connections with TLS

PostgreSQL TCP connections can be protected using **TLS**. For servers on networks that are not fully trusted, you must both encrypt data in transit and verify the server's identity.

Libpq offers common `sslmode` settings:

| `sslmode` | General meaning | Notes |
| --- | --- | --- |
| `disable` | Do not require TLS | Consider only in clearly controlled environments |
| `allow` | Try without TLS first, then with TLS if needed | Unsuitable when policy requires TLS |
| `prefer` | Prefer TLS, but accept non-TLS fallback | Often the libpq default; does not guarantee mandatory TLS |
| `require` | Require the connection to be encrypted with TLS | Not sufficient to confirm the server hostname was verified |
| `verify-ca` | TLS and certificate verification against a trusted CA | Does not check the hostname like `verify-full` |
| `verify-full` | TLS, CA verification, and server hostname check | Recommended when connecting to remote servers with proper certificates |

Example URI requiring server identity verification:

```bash
psql 'postgresql://report_reader@db.internal.example:5432/reporting?sslmode=verify-full&connect_timeout=5'
```

This example only succeeds when the server supports TLS, the certificate is valid for hostname `db.internal.example`, and the client has suitable trust material, such as a CA certificate configured via `sslrootcert` or `PGSSLROOTCERT` per policy.

**Do not assume `sslmode=require` equals full server identity verification.** In some configurations/compatibility modes, the presence of a root CA file can influence verification behavior; to express your requirement unambiguously, use `verify-full` and configure the appropriate CA.

### 13.1. Checking whether a connection uses SSL

While in `psql`, run:

```text
\conninfo
```

You can also query the system view if you have permissions:

```sql
SELECT
    s.ssl,
    s.version,
    s.cipher
FROM pg_stat_ssl AS s
WHERE s.pid = pg_backend_pid();
```

The output shows whether the **current session** uses SSL/TLS and, if so, the reported version and cipher. On Unix socket connections, TCP TLS does not apply in the same way as on network connections.

### 13.2. Hostname and hostaddr

The `host` parameter usually holds the hostname to connect to; `hostaddr` can specify the target IP address directly. When using certificate name verification under `sslmode=verify-full`, keep a **hostname matching the certificate** in `host`, rather than supplying only an IP and skipping name verification.

For example, in environments with special DNS or IP routing, a configuration might need both `host` and `hostaddr`, but you must verify they both represent the right server; never bypass hostname verification just to get a connection to succeed.

## 14. Timeouts, application names, and multiple server hosts

### 14.1. Limiting connection wait time

An application or script should not hang indefinitely when a hostname fails to resolve or a server stops responding.

```bash
psql "host=db.internal.example port=5432 dbname=learning_pg user=learning_app connect_timeout=5 application_name=maintenance_check"
```

`connect_timeout=5` applies to connection establishment time under libpq rules, **not** as an execution time limit for all SQL statements after login. To limit query execution time, PostgreSQL provides separate session settings such as `statement_timeout`, which should be applied according to business requirements.

### 14.2. application_name for connection observability

Set an application name in the connection string:

```bash
psql "host=127.0.0.1 port=5432 dbname=learning_pg user=learning_app application_name=lesson43_psql"
```

Inside the session:

```sql
SHOW application_name;
```

With an administrative/monitoring role holding appropriate privileges, you can observe sessions via:

```sql
SELECT pid, usename, datname, application_name, state
FROM pg_stat_activity
WHERE application_name = 'lesson43_psql';
```

`application_name` is a monitoring label, **not** a trusted security identity: any client can set it arbitrarily. Never use this label as a basis for granting permissions.

### 14.3. Multiple hosts and read-write selection

Libpq supports specifying multiple hosts/ports in a single connection string to attempt connections according to a policy. For example, on PostgreSQL infrastructure with multiple endpoints:

```bash
psql "host=pg1.internal.example,pg2.internal.example port=5432,5432 dbname=learning_pg user=learning_app target_session_attrs=read-write connect_timeout=5"
```

`target_session_attrs=read-write` instructs libpq to select a connection with attributes suitable for a writable session, rather than connecting to just any standby. This is a connection target selection mechanism; **it does not create high availability, elect a primary, or solve full application-level routing**.

In failover environments, combine it with cluster management, DNS/load balancers, or properly operated orchestration mechanisms. Do not list multiple independent servers and assume they share the same data.

## 15. Running SQL from the command line without an interactive session

`psql` is not only for opening an interactive SQL prompt; it can also execute a single command or a script file.

### 15.1. Executing a single SQL command with -c

```bash
psql -h 127.0.0.1 -p 5432 -U learning_app -d learning_pg \
  -c "SELECT current_database(), current_user, now();"
```

This snippet uses `\` for line continuation in Linux/macOS shells. In PowerShell, you can write the command on a single line:

```powershell
psql -h 127.0.0.1 -p 5432 -U learning_app -d learning_pg -c "SELECT current_database(), current_user, now();"
```

For automation, handle exit codes and output carefully. Do not rely solely on seeing SQL results printed on screen once to conclude that a full script succeeded.

### 15.2. Running a .sql file

Suppose you have a file `init_lab.sql` in the working directory:

```sql
CREATE TABLE IF NOT EXISTS demo_notes (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    message TEXT NOT NULL
);

INSERT INTO demo_notes (message)
VALUES ('Hello PostgreSQL');

SELECT id, message
FROM demo_notes
ORDER BY id;
```

Run it using:

```bash
psql -h 127.0.0.1 -p 5432 -U learning_app -d learning_pg \
  -X -v ON_ERROR_STOP=1 -f init_lab.sql
```

Explanation:

- `-f init_lab.sql`: reads and executes the commands in the file.
- `-X`: ignores the user's `psqlrc` startup file, reducing the impact of custom settings when running scripts.
- `-v ON_ERROR_STOP=1`: tells `psql` to stop on error instead of continuing through subsequent steps.
- The file executes under the logged-in role's privileges; `CREATE` privilege on the schema is required if the script creates tables.

In PowerShell you can write it on one line:

```powershell
psql -h 127.0.0.1 -p 5432 -U learning_app -d learning_pg -X -v ON_ERROR_STOP=1 -f init_lab.sql
```

**Note on transactions:** multiple SQL statements in a file do not automatically form a single transaction. If all statements must succeed together or roll back together, use `BEGIN ... COMMIT` inside the file where appropriate, or `psql`'s `--single-transaction` option when the commands allow it. Some commands like `CREATE DATABASE` cannot run inside a transaction block, so do not apply this option blindly to every script.

### 15.3. Extracting output for shell scripts

When you need a simple value without table headers:

```bash
psql -h 127.0.0.1 -U learning_app -d learning_pg \
  -X -A -t -c "SELECT current_database();"
```

`-A` selects unaligned output; `-t` hides table headers and footers. This output format is useful for shell scripts, but only when you know the exact structure of the returned data; with multi-line data, newlines/tabs and special values must be handled carefully.

## 16. Configuration precedence and how to avoid connecting to the wrong target

An environment can supply connection information from several sources:

```text
Parameters passed directly to psql / connection string
          |
          v
Parameters loaded from service file (if service is used)
          |
          v
Environment variables PGHOST / PGPORT / PGUSER / PGDATABASE ...
          |
          v
libpq / operating system defaults
```

This is a high-level diagram to **explain configuration sources**, not an exhaustive override table for every parameter collision case. Rules combining `-d`, service files, and explicit parameters have specific nuances; to reduce ambiguity, configure each parameter in one deliberate place.

For example, if the terminal already has:

```bash
export PGDATABASE=reporting
export PGHOST=db.internal.example
```

And you then simply type:

```bash
psql -U learning_app
```

you could end up connecting to **reporting on the remote server**, rather than local `learning_pg` as intended. For important operations, you should:

1. Specify the endpoint and database explicitly in the command or controlled service.
2. Use a role with least privilege.
3. Run `\conninfo` and `SELECT current_database(), current_user;` to verify the session.
4. For production environments, apply additional safeguards before running data-modifying statements.

## 17. Diagnosing common connection errors

### 17.1. psql command not found

Messages such as `psql: command not found` or `psql is not recognized` mean the shell cannot find the binary in `PATH`, or the client is not installed.

Solution: locate where the binary is installed, use the full path or add the correct `bin` directory to `PATH`, then retry `psql --version`. If multiple PostgreSQL versions are installed on the machine, check which binary is being resolved.

### 17.2. Connection refused or timeout

Example:

```text
connection to server at "127.0.0.1", port 5432 failed:
Connection refused
```

Common causes:

- The PostgreSQL server is not running.
- Wrong hostname or port.
- The server is not listening on the specified address.
- A firewall, route, or proxy is blocking the connection.
- The server is starting up, overloaded, or the port is occupied by another service.

Try:

```bash
pg_isready -h 127.0.0.1 -p 5432
```

If the server does not respond, inspect the service manager and logs on **the right server machine**. `Connection refused` differs from a wrong-password error: it is typically a failure before the user authentication step.

### 17.3. FATAL: password authentication failed

The server accepted the connection, but the role's credentials were rejected under the applicable rule.

Check:

- Did you select the right `host`/`port`/`dbname`/`user`?
- Is a password file or secret manager supplying an outdated password?
- Which authentication method does `pg_hba.conf` specify?
- Does the client/driver support mechanisms such as SCRAM?
- Are there multiple instances with the same database name using different accounts?

Do not fix this by enabling `trust` on a public network. Have an administrator reset the credential for **the right role on the right instance** if needed.

### 17.4. FATAL: role does not exist

Example:

```text
FATAL: role "learning_app" does not exist
```

Check the username sent via `-U`, the `PGUSER` variable, and the existing roles. On a system where you have access, use `\du` or query the appropriate metadata.

If the role was just created yet still reports missing, you are very likely connecting to **a different instance** (wrong host, port, container, or service).

### 17.5. FATAL: database does not exist

If `-d` is omitted, the default database may match the role name. Specify `-d learning_pg` explicitly to avoid guessing wrong. If the database does not exist on the current instance, an administrator can create it when legitimately required; do not blindly create a database of the same name on a production server.

### 17.6. Peer authentication failed

On Linux/Unix, local `peer` authentication can compare the OS user against the PostgreSQL role. Therefore:

```bash
psql -U postgres
```

may fail if you are running as a different OS user, even though:

```bash
sudo -iu postgres psql
```

succeeds. A TCP path with `-h 127.0.0.1` may use a different authentication rule; check the configuration before changing passwords or lines in `pg_hba.conf`.

### 17.7. No pg_hba.conf entry

The connection reached the server, but no authentication rule matched the connection type, **client** address, role, database, and SSL state.

Example message:

```text
FATAL: no pg_hba.conf entry for host "...", user "...",
database "...", ...
```

To fix properly:

1. Identify the client address seen by PostgreSQL.
2. Check the `pg_hba.conf` path via `SHOW hba_file;` if you have privileges.
3. Determine the appropriate `host`/`hostssl` entry, CIDR, role, and database.
4. Add a **scoped rule** with a secure authentication method.
5. Reload the configuration following your approved procedure.

Never add `host all all 0.0.0.0/0 trust` just to make a connection command work.

### 17.8. Certificate or hostname errors when using verify-full

If `sslmode=verify-full` reports an invalid certificate, possible causes include:

- The client lacks or uses the wrong CA certificate.
- The server certificate has expired or was not signed by the expected CA.
- The hostname in the URI does not match the name verified by the certificate.
- You connected by IP while the certificate was issued for a different hostname.
- You are connecting to the wrong endpoint/server.

Do not immediately switch to `sslmode=disable` to bypass the error. Identify the certificate for the right server, and configure the trust material and canonical hostname according to security procedures.

## 18. Diagnosing directly inside a connected psql session

Once logged in, run:

```sql
SELECT
    current_database() AS db,
    current_user AS effective_user,
    session_user AS login_user,
    inet_server_addr() AS server_ip,
    inet_server_port() AS server_port,
    inet_client_addr() AS client_ip;

SHOW search_path;
SHOW application_name;
```

And:

```text
\conninfo
```

Understand that:

- `inet_server_addr()` and `inet_server_port()` may return `NULL` on Unix socket connections.
- `search_path` affects how schema-unqualified table names resolve to objects.
- `application_name` is a client-supplied label, not a credential.
- `current_user` reflects the current effective role, while `session_user` typically reflects the session's login role.

If querying an unqualified table returns `relation does not exist` even though the table actually exists, you may be in a **different database** or `search_path` does not include the table's schema. That is an object-name scope issue, not necessarily a transport or authentication failure.

## 19. Common mistakes

| Mistake | Consequence | How to handle |
| --- | --- | --- |
| Typing only `psql` and assuming it always enters `postgres` | Libpq may choose a database matching the OS user or environment | Specify `-h`, `-U`, `-d` explicitly and check `\conninfo` |
| Confusing `psql --version` with the server version | Misdiagnosing the major version | Connect and run `SHOW server_version;` |
| Assuming `-h localhost` always means a Unix socket | Authentication and transport paths differ | Verify host, socket directory, and explicit TCP |
| Putting passwords on the command line or in URIs | Easily leaked via history/logs/processes | Use a prompt, passfile, or secret manager |
| Typing `-W password` | `-W` does not accept a password as its value | Use `-W` and type at the prompt |
| Using a URI with `&` unquoted | The shell may split the command | Quote the entire URI |
| Failing to percent-encode special characters in URIs | Mis-parses user, host, database, or query | Encode per URI semantics |
| Using `jdbc:postgresql://...` with psql | Driver URI syntax differs from libpq | Use `postgresql://...` or `key=value` |
| Using `sslmode=prefer` and assuming TLS is mandatory | Client can fall back to non-TLS | Configure `verify-full` when server verification is needed |
| Using `sslmode=require` and assuming hostname check occurred | Full identity verification may be skipped | Configure `verify-full` and the proper CA |
| Reading secrets from `.pgpass` with overly broad permissions on Unix | Libpq may ignore the file | Restrict permissions, typically `chmod 600` |
| Running scripts without `ON_ERROR_STOP` | May continue executing after a failed SQL statement | Use `-X -v ON_ERROR_STOP=1` when appropriate |
| Trusting a service name without checking the actual endpoint | May accidentally connect to staging/production | Verify endpoint, role, database, and privileges |
| Enabling `trust` or public ports to bypass auth errors | Weakens system security | Fix `pg_hba.conf`, TLS, and firewall properly |

## 20. Practice exercises

Use a practice PostgreSQL instance, never a production database:

1. Run `psql --version`, then connect and run `SHOW server_version;`. Explain why the two values can differ.
2. Connect to `learning_pg` using the four options `-h`, `-p`, `-U`, `-d`. Run `\conninfo` and record the database, role, host, and port.
3. Rewrite the connection from exercise 2 as a **libpq keyword/value connection string**. Add `connect_timeout=5` and `application_name=lesson43_psql`.
4. Rewrite the same connection as a `postgresql://...` URI. Add two query parameters and explain why the entire URI needs quoting when `&` is present.
5. If a database name contains a space, explain how to quote the value in `key=value` form and how to percent-encode the space in a URI.
6. On Linux/macOS, compare connecting without `-h` versus `-h 127.0.0.1`. Use `\conninfo` to identify the protocol/host and state the difference between `local` and `host` rules in `pg_hba.conf`.
7. Set `PGHOST`, `PGPORT`, `PGUSER`, and `PGDATABASE` in the terminal and connect with `psql -W`. Explain which parameters are supplied by the environment.
8. Create a password file in a test environment only, secure its file permissions appropriately, connect without typing a password, and explain why this file should never be committed to Git.
9. Create a service file with two profiles: local training and internal reporting. Use `psql "service=..."` and verify you do not connect to the wrong instance.
10. Set up a connection requiring `sslmode=verify-full` in an environment with properly issued certificates; use `\conninfo` or `pg_stat_ssl` to confirm TLS. Explain the difference between `require` and `verify-full`.
11. Run a query with `psql -c`, then create a SQL file and run it via `psql -X -v ON_ERROR_STOP=1 -f ...`. Describe how to detect execution errors from a script.
12. Diagnose five scenarios: client not in `PATH`, `Connection refused`, `Peer authentication failed`, `Role does not exist`, and `No pg_hba.conf entry`. For each error, specify whether to check client, server, authentication, or privilege configuration.
13. A terminal already has `PGHOST=db.internal.example` and `PGDATABASE=reporting`. If you run `psql -U learning_app`, where is it likely to connect? Design a way to prevent operating on the wrong environment.
14. Compare a libpq connection string `postgresql://...` with a JDBC URL `jdbc:postgresql://...`; identify what is similar and why they cannot be used interchangeably verbatim.

## 21. Summary

To connect to PostgreSQL successfully with `psql`, you must clearly specify the **endpoint, port, database, role, and authentication method**. You can supply these details via individual CLI options, a `key=value` connection string, or a `postgresql://...` URI. Libpq also supports environment variables, password files, and service files for reusing configurations.

In real deployments, prioritize **verifying which server you are connected to**, **keeping passwords out of command lines and source code**, **using TLS with identity verification for remote connections**, and **setting appropriate timeouts**. Once a session is open, `\conninfo`, `current_database()`, `current_user`, and diagnostic queries help distinguish connection failures from permission or wrong-database errors. Mastering these tools is the foundation for using PostgreSQL safely across terminals, scripts, and applications.
