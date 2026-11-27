# Local Connections via Unix-Domain Socket or TCP in PostgreSQL

After installing PostgreSQL, the first step is usually checking **whether the server is running** and **how applications or users can connect**. On Linux/macOS machines, two common local connection methods are:

- **Unix-domain socket:** the client process communicates with PostgreSQL on the same operating system through a socket file without using TCP/IP.
- **TCP loopback:** the client process connects to PostgreSQL via `127.0.0.1` (IPv4) or `::1` (IPv6), still on the same machine but using the TCP protocol.

Both paths can reach the **same PostgreSQL instance**, **same database**, and **same role**, yet address selection, `pg_hba.conf` authentication rules, and common errors differ. Understanding this distinction prevents the "server is running but `psql` cannot connect" confusion, especially right after installing PostgreSQL, configuring a Java service, or switching from an OS account to a dedicated application role.

This guide targets modern PostgreSQL, focusing on Unix-like environments (Linux/macOS) for Unix-domain sockets. On Windows and inside containers, socket and `localhost` details differ; those are covered at the end.

## 1. Distinguishing Server, Client, Database, and Role

In PostgreSQL, these objects are **not the same thing**:

| Component | Example | Role |
| --- | --- | --- |
| PostgreSQL server | The `postgres` process | Accepts connections, manages data, and executes SQL |
| Client | `psql`, Java/JDBC app, DBeaver | Sends connection requests and SQL statements |
| Database | `postgres`, `app_db` | Set of data objects targeted by a session |
| Role with LOGIN | `postgres`, `app_user` | Identity and privileges inside PostgreSQL |
| Operating system user | `postgres`, `alice` | Client process identity on the machine |
| Connection address | Socket directory, `127.0.0.1`, `::1` | How the client locates the server |
| Authentication method | `peer`, `scram-sha-256` | How the server verifies client identity |

For instance, `postgres` can simultaneously be the name of an administrative role and a default database, yet the two concepts are independent. The Linux OS user `postgres` is yet another identity that only maps to a PostgreSQL role per configuration.

`localhost` is merely a hostname, not an authentication method; it typically resolves to a loopback address and uses TCP. Conversely, a path like `/var/run/postgresql` in libpq's host parameter specifies a **Unix socket directory**.

## 2. Visualizing the Paths of Both Connection Types

~~~mermaid
flowchart LR
    C["Client: psql / libpq"] --> Q{"Select connection type"}
    Q -->|"No host on Unix, or host is a directory"| U["Unix-domain socket"]
    Q -->|"host=127.0.0.1 or host=localhost"| T["TCP loopback"]
    U --> H1["pg_hba.conf: local line"]
    T --> H2["pg_hba.conf: host/hostssl line"]
    H1 --> P[("PostgreSQL server")]
    H2 --> P
    P --> D[("Database app_db")]
~~~

In Unix-like environments, clients using **libpq** (such as `psql`) typically default to a Unix socket **when no host is specified**, whereas specifying `-h localhost` or `-h 127.0.0.1` causes the client to connect over TCP.

Note: this describes the default behavior of `psql`/libpq on Unix-like systems, **not a mandatory rule for all drivers**. For example, standard PostgreSQL JDBC URLs use TCP even when the application and database run on the same host.

## 3. Starting with psql: Key Parameters

General syntax:

~~~bash
psql -h HOST -p PORT -U ROLE -d DATABASE
~~~

Where:

- `-h` / `--host`: hostname/IP for TCP, or **socket directory path** for a Unix-domain socket.
- `-p` / `--port`: PostgreSQL port, commonly `5432` by default. For Unix sockets, the port number still determines the socket filename.
- `-U` / `--username`: PostgreSQL role to log in as.
- `-d` / `--dbname`: database to connect to.

If `-U` is omitted, libpq typically defaults to the current OS username. If `-d` is omitted, the default database name typically defaults to the role name. That is why running `psql` without arguments may report "role does not exist" or "database does not exist" even when the server is running normally.

Example accessing a specific database:

~~~bash
psql -U app_user -d app_db
~~~

On Linux/macOS, when no other host configuration overrides it, this usually looks for the default Unix-domain socket. However, if the `PGHOST` environment variable or a service configuration is set, the actual connection path may differ.

### Useful Checks Inside psql

Once inside an interactive session:

~~~sql
SELECT current_user, current_database(), version();
~~~

In the `psql` CLI, you can use meta-commands:

~~~text
\conninfo
\du
\l
\q
~~~

`\conninfo` shows the address type, user, and database of the current session. `\du` lists roles, `\l` lists databases, and `\q` exits. These are **`psql` commands**, not standard SQL to send directly over JDBC.

## 4. Connecting Locally via Unix-Domain Socket

### 4.1. What Is a Unix-Domain Socket?

On Unix-like systems, PostgreSQL typically creates a socket file named like:

~~~text
/var/run/postgresql/.s.PGSQL.5432
~~~

The trailing `5432` corresponds to the port the instance uses. The socket file is an **IPC (inter-process communication) endpoint** between processes on the same machine; it is not a text file containing the database and does not require a TCP connection to port 5432.

The directory holding the socket depends on the OS, installation method, and configuration. Examples:

- Many Debian/Ubuntu packages use `/var/run/postgresql` (typically linked to `/run/postgresql`).
- Other builds or installation methods use `/tmp`.
- Hosts running multiple instances can configure separate directories and ports.

**Do not hardcode a guessed socket path** from a different system. Check your PostgreSQL configuration or package documentation.

### 4.2. Using the Default Unix Socket

On a Unix-like host, try:

~~~bash
psql -U postgres -d postgres
~~~

If the PostgreSQL role `postgres` requires `peer` authentication, the command above may **fail** when run as an OS user other than `postgres`. This does not prove the socket is broken; you may simply not satisfy the authentication rule.

In Linux installations that provide a `postgres` OS account, a common administrative command is:

~~~bash
sudo -u postgres psql -d postgres
~~~

This uses the `postgres` OS account to connect to PostgreSQL. It succeeds when the service, socket, Unix permissions, and matching `pg_hba.conf` rules allow it. Do not use this administrative account as a routine application account.

### 4.3. Specifying the Socket Directory Explicitly

~~~bash
psql \
  -h /var/run/postgresql \
  -p 5432 \
  -U postgres \
  -d postgres
~~~

Note: `-h /var/run/postgresql` is the **directory path**, not the path to the `.s.PGSQL.5432` file itself. Libpq constructs the socket filename from the directory and port number.

If the server uses `/tmp`:

~~~bash
psql -h /tmp -p 5432 -U app_user -d app_db
~~~

There is no rule forcing `/var/run/postgresql` to exist on every system. If the command reports the socket cannot be found, verify the exact directory used by the server.

### 4.4. Confirming the Session Actually Uses a Unix Socket

Inside `psql`:

~~~text
\conninfo
~~~

On Unix systems, the message may indicate connecting `via socket in "/var/run/postgresql"`.

You can also use SQL:

~~~sql
SELECT
    current_user,
    current_database(),
    inet_client_addr() AS client_ip,
    inet_server_addr() AS server_ip;
~~~

For a **Unix-domain socket connection**, both `inet_client_addr()` and `inet_server_addr()` return SQL `NULL` because no IP address is used. Cross-check this output with `\conninfo`; not every `NULL` context in system views proves the exact same connection type.

## 5. Connecting Locally via TCP Loopback

### 5.1. Specifying IPv4 127.0.0.1

~~~bash
psql \
  -h 127.0.0.1 \
  -p 5432 \
  -U app_user \
  -d app_db
~~~

`127.0.0.1` is the IPv4 loopback address of the **network environment running the client**. The client initiates a TCP connection to PostgreSQL on port `5432` over loopback.

### 5.2. Specifying localhost or IPv6

~~~bash
psql -h localhost -p 5432 -U app_user -d app_db
~~~

The name `localhost` usually resolves to `::1` (IPv6), `127.0.0.1` (IPv4), or both depending on resolver configuration. Hence, connecting with `localhost` may hit a different address than specifying `127.0.0.1` directly.

To test IPv6 explicitly:

~~~bash
psql -h ::1 -p 5432 -U app_user -d app_db
~~~

To check the TCP addresses used in a successful session:

~~~sql
SELECT
    inet_client_addr() AS client_ip,
    inet_server_addr() AS server_ip,
    inet_server_port() AS server_port;
~~~

Over IPv4 loopback, you usually see `127.0.0.1`; over IPv6 loopback, you usually see `::1`. The port matches the server listening port.

### 5.3. TCP Loopback Is Not Remote TCP

If `listen_addresses = 'localhost'`, PostgreSQL listens only on appropriate loopback addresses. Another host on the network cannot connect via the server's LAN IP merely because TCP loopback is enabled.

Allowing connections from other machines requires adjusting network config, firewalls, `pg_hba.conf`, and security policies. This lesson focuses primarily on **local host connections**, not exposing PostgreSQL over the network or Internet.

## 6. Comparing Unix Socket vs. TCP Loopback

| Criterion | Unix-Domain Socket | TCP Loopback |
| --- | --- | --- |
| Transport mechanism | OS-level IPC | TCP/IP over loopback |
| `psql` example | `psql -h /var/run/postgresql ...` | `psql -h 127.0.0.1 ...` |
| Address | Socket directory and socket filename | IP/hostname + port |
| Typical scope | Processes on the same OS | Processes in the same network namespace/host using loopback |
| `pg_hba.conf` rule type | `local` | `host`, `hostssl`, `hostnossl` respectively |
| Common authentication | `peer` or password | `scram-sha-256`, TLS/password per config |
| Depends on `listen_addresses` | No; governed by `unix_socket_directories` | Yes |
| Can use `peer`? | Yes, when supported by OS/method | No (not via Unix-socket peer verification) |
| Verified via `inet_client_addr()` | SQL `NULL` | Usually `127.0.0.1` or `::1` |
| Best suited for | Local admin tools, co-located OS services | Standard applications, JDBC, port-based clients |

Neither option is universally faster or more secure in every deployment. Unix sockets bypass the TCP/IP stack and integrate neatly with OS-user authentication, whereas TCP is broadly supported across drivers and tools. On a single host, performance differences should be **measured on your actual workload** rather than used as the sole selection criterion.

## 7. Controlling Connection Modes via postgresql.conf

PostgreSQL separates TCP listening settings from Unix socket settings.

~~~conf
# Illustrative example in postgresql.conf
listen_addresses = 'localhost'
port = 5432
unix_socket_directories = '/var/run/postgresql'
~~~

Where:

- `listen_addresses`: IP addresses PostgreSQL listens on for **TCP connections**. `localhost` restricts to loopback; `'*'` opens listeners on all configured interfaces and should not be set carelessly.
- `port`: TCP port and part of the Unix socket filename.
- `unix_socket_directories`: directory or list of directories where Unix-domain sockets are created. An empty value disables Unix sockets in supported configs.

These parameters generally take effect at **PostgreSQL startup**, so changing them usually requires restarting the server. By contrast, edits to authentication rules in `pg_hba.conf` generally take effect upon reloading configuration, without restarting the entire instance in Unix-like environments.

To inspect active runtime values on the running server:

~~~sql
SHOW listen_addresses;
SHOW port;
SHOW unix_socket_directories;
SHOW config_file;
SHOW hba_file;
~~~

The paths `config_file` and `hba_file` indicate where the server reads configuration, which need not reside in the same folder as the PostgreSQL data directory. Display of certain paths may be restricted for unprivileged roles.

### Checking Whether PostgreSQL Created the Socket

On Linux, once you know the right directory:

~~~bash
ls -la /var/run/postgresql/
~~~

You should see files like `.s.PGSQL.5432` alongside an accompanying lock file. However, **a socket file existing does not guarantee your role can log in**, and a stale file does not prove PostgreSQL is ready. Use an actual connection check or `pg_isready` to verify status.

On Linux, inspect TCP listeners with:

~~~bash
ss -ltn
~~~

The listener list confirms whether the TCP port is open. It does not indicate whether a given PostgreSQL role will pass `pg_hba.conf`.

## 8. pg_hba.conf: Why Does the Same User Get Different Results on Two Connections?

`pg_hba.conf` (host-based authentication configuration) defines **which connection types may authenticate using which methods**. PostgreSQL scans entries top to bottom; the **first record matching** connection type, database, role, and address is selected.

If a record matches and authentication fails, the server **does not continue trying records below it** as fallbacks. That is why line ordering in this file is critical.

Illustrative example of a small rule set:

~~~conf
# TYPE   DATABASE   USER       ADDRESS          METHOD

# Unix socket: admin role uses OS authentication.
local    all        postgres                     peer

# Unix socket: application uses SCRAM password.
local    app_db     app_user                     scram-sha-256

# TCP loopback IPv4:
host     app_db     app_user   127.0.0.1/32      scram-sha-256

# TCP loopback IPv6:
host     app_db     app_user   ::1/128           scram-sha-256
~~~

The address field is omitted for `local` records. For `host` records, an allowed address/range is required. The example above contains no catch-all rule for arbitrary roles/databases; other connections are allowed only if another matching entry exists in the file.

### Distinguishing Record Types

| TYPE in pg_hba.conf | Applies To |
| --- | --- |
| `local` | Unix-domain socket connections only |
| `host` | TCP connections (encrypted or unencrypted per general rules) |
| `hostssl` | TCP connections using SSL/TLS (requires server SSL support/enabled) |
| `hostnossl` | TCP connections without SSL/TLS |

Because `local` and `host` are separate types, permitting a Unix socket connection **does not automatically** permit the same role over `127.0.0.1`.

Additionally, `-h localhost` may connect via IPv6 `::1`. If the file only includes `127.0.0.1/32` and lacks `::1/128`, IPv6 connections may fail to find a matching rule or behave unexpectedly. Verify the actual client address in errors/logs and active sessions.

## 9. Peer Authentication on Unix Sockets

**`peer`** is an authentication method PostgreSQL supports on Unix-domain sockets. It asks the operating system for the client process's OS user identity, then matches that identity against the login role or maps it via `pg_ident.conf`.

Suppose you have:

~~~conf
local   all   postgres   peer
~~~

If you run the command below as OS user `postgres`:

~~~bash
sudo -u postgres psql -U postgres -d postgres
~~~

PostgreSQL verifies the OS user is `postgres` and allows login as role `postgres`.

Conversely, if your OS user is `alice` and you run:

~~~bash
psql -U postgres -d postgres
~~~

you may receive:

~~~text
FATAL:  Peer authentication failed for user "postgres"
~~~

This is an **authentication failure**, not necessarily a wrong password or crashed server. When `peer` is configured, entering a password will not make the OS identity `alice` become `postgres`.

### When Is peer Appropriate?

- Administering PostgreSQL directly on the server using controlled OS accounts.
- Services running under dedicated OS users mapped to corresponding PostgreSQL roles.
- Environments relying on OS permissions and identity instead of distributing passwords to local processes.

To map differing OS usernames and database role names, use `pg_ident.conf` with the `map=...` option in `pg_hba.conf`. This is deliberate administrative configuration, not a way to bypass access controls.

`peer` does not apply to TCP `127.0.0.1` connections merely because both processes run on the same machine. For TCP, configure an authentication method appropriate for `host` entries.

## 10. Password Authentication with SCRAM-SHA-256

For application accounts, **`scram-sha-256`** is the standard choice. It is a challenge–response password authentication mechanism supported by PostgreSQL, replacing weaker legacy password methods.

Example for TCP loopback:

~~~conf
host   app_db   app_user   127.0.0.1/32   scram-sha-256
host   app_db   app_user   ::1/128        scram-sha-256
~~~

And for Unix sockets when using the same password mechanism:

~~~conf
local  app_db   app_user                  scram-sha-256
~~~

With SCRAM, the role must have a password secret stored in a compatible format. Logging in over TCP:

~~~bash
psql -h 127.0.0.1 -p 5432 -U app_user -d app_db -W
~~~

`-W` forces `psql` to prompt interactively for a password. Avoid placing real passwords directly in URLs, shell commands saved to history, or team docs.

### Creating a Role and Database for the Lab

In an authorized PostgreSQL admin session:

~~~sql
CREATE ROLE app_user LOGIN;
CREATE DATABASE app_db OWNER app_user;
~~~

`CREATE DATABASE` must execute in a valid context, outside any user-wrapped transaction block. If the role/database already exists, do not re-run without checking system state.

Inside `psql`, an administrator can set the password interactively:

~~~text
\password app_user
~~~

`\password` prompts securely and avoids putting a plaintext password into `ALTER ROLE ... PASSWORD '...'`, which could be captured in client history or logs. PostgreSQL stores a compatible SCRAM verifier per configuration. Administrators should inspect `password_encryption` and privilege policies before testing.

Example:

~~~sql
SHOW password_encryption;
~~~

If the setting or stored password verifier is not compatible with `scram-sha-256`, update the verifier/password properly before connecting. Never replace all of `pg_hba.conf` with `trust` just to get past a password error quickly.

## 11. Side-by-Side Practice: Same Role, Two Connection Paths

Assume the server uses port `5432`, socket directory `/var/run/postgresql`, and `app_user`/`app_db` have been created with the SCRAM rules above.

### 11.1. Terminal A: Via Unix Socket

~~~bash
psql -h /var/run/postgresql \
     -p 5432 \
     -U app_user \
     -d app_db \
     -W
~~~

Inside `psql`:

~~~sql
SELECT
    current_user AS db_role,
    current_database() AS db_name,
    inet_client_addr() AS client_ip,
    inet_server_addr() AS server_ip,
    pg_backend_pid() AS backend_pid;
~~~

Expect `client_ip` and `server_ip` to be SQL `NULL`, and `db_role` to be `app_user`.

Inside `psql`:

~~~text
\conninfo
~~~

It will describe the connection via the socket directory.

### 11.2. Terminal B: Via TCP IPv4 Loopback

~~~bash
psql -h 127.0.0.1 \
     -p 5432 \
     -U app_user \
     -d app_db \
     -W
~~~

Run the same `SELECT` as in Terminal A. `client_ip` and `server_ip` should typically show `127.0.0.1`. `pg_backend_pid()` in A and B will differ because they are two separate backend sessions.

### 11.3. Comparing the Results

| Attribute | Terminal A | Terminal B |
| --- | --- | --- |
| Role | app_user | app_user |
| Database | app_db | app_db |
| Transport | Unix socket | TCP IPv4 loopback |
| Client IP | SQL `NULL` | `127.0.0.1` |
| pg_hba rule | `local` | `host ... 127.0.0.1/32` |
| Example auth method | scram-sha-256 | scram-sha-256 |

Both sessions can see the exact same tables in `app_db`, because **the transport does not govern data privileges**. Effective permissions come from roles, memberships, grants, object ownership, row-level security, and related security policies.

### 11.4. Closing Connections

In each terminal:

~~~text
\q
~~~

Closing the session releases the backend process and its associated resources per PostgreSQL's lifecycle.

## 12. Why Might Two Connections Require Different Passwords?

Suppose `pg_hba.conf` contains:

~~~conf
local   all     postgres                     peer
host    all     postgres    127.0.0.1/32     scram-sha-256
~~~

Then:

~~~bash
sudo -u postgres psql -U postgres -d postgres
~~~

can log in over the Unix socket **without entering a password** thanks to OS `peer` authentication.

However:

~~~bash
psql -h 127.0.0.1 -U postgres -d postgres -W
~~~

uses TCP and must satisfy `scram-sha-256`, requiring the role to have a matching password/verifier.

Therefore, saying "`sudo -u postgres` logs in, whereas `-h 127.0.0.1` fails" **is not a contradiction**. Two different `pg_hba.conf` records are being matched.

## 13. Inspecting and Applying pg_hba.conf

PostgreSQL does not automatically rewrite authentication rules based on client `psql` flags. If login fails because a rule is missing, an administrator must edit `pg_hba.conf` in accordance with security policy.

In an authorized admin session:

~~~sql
SHOW hba_file;
~~~

To view parsed rules and any syntax errors currently on disk:

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

The `pg_hba_file_rules` view helps spot syntax errors or rule ordering issues. However, it reflects the **file currently on disk**, which does not guarantee the running server has reloaded the latest edit in every situation. After editing, perform a proper reload.

Triggering a reload via SQL when permitted:

~~~sql
SELECT pg_reload_conf();
~~~

`pg_reload_conf()` sends a reload signal; its return value does not replace checking server logs or testing a new connection. Parameters requiring a restart, such as `listen_addresses`, do not take effect from a reload alone.

In environments managed by `systemd` or distribution-specific PostgreSQL tools, use the corresponding service reload command. Never guess service names from another OS, as instance names and versions vary.

**Critical rule:** `pg_hba.conf` is evaluated top to bottom. When editing, check whether a broader rule earlier in the file (e.g., `host all all ...`) prevents a narrower rule below from ever being reached.

## 14. Checking Server Readiness with pg_isready

`pg_isready` checks whether PostgreSQL is accepting connections; it does not verify authentication or access to a specific database.

Check Unix socket:

~~~bash
pg_isready -h /var/run/postgresql -p 5432
~~~

Check TCP loopback:

~~~bash
pg_isready -h 127.0.0.1 -p 5432
~~~

Output indicates whether the server is `accepting connections`, `rejecting connections`, or unresponsive. For example, a server starting up or in recovery may not accept normal connections yet.

**Key point:** `pg_isready` reporting accepting connections **does not mean** `app_user`'s password is valid, the role has `LOGIN`, `app_db` exists, or the user has required privileges. Always follow readiness checks with an actual `psql` session using the **target host, port, role, and database**.

## 15. Common Unix Socket Errors

### 15.1. Socket Not Found

Common message:

~~~text
connection to server on socket
"/var/run/postgresql/.s.PGSQL.5432" failed:
No such file or directory
~~~

Possible causes:

- PostgreSQL is not running.
- The server creates its Unix socket in a different directory.
- The client specified the wrong port, looking for a non-existent socket filename.
- `unix_socket_directories` is configured differently or disabled.
- Client and server do not share the same filesystem/socket namespace, especially in containers.

Check:

~~~bash
pg_isready -h /var/run/postgresql -p 5432
~~~

If you have an active admin connection over TCP, inspect:

~~~sql
SHOW unix_socket_directories;
SHOW port;
~~~

Do not jump to concluding PostgreSQL is broken simply because the client's default path does not match where the server placed its socket.

### 15.2. Permission Denied Accessing the Socket

The client process may lack filesystem traversal permissions on the parent directory or access rights to the socket file. Inspect directory and socket permissions, service OS user, and application OS user.

PostgreSQL provides settings such as `unix_socket_permissions` and `unix_socket_group` on supported platforms. Never blindly run `chmod 777` across system directories as a "quick fix"; grant the minimal permissions matching your authentication model.

### 15.3. Peer Authentication Failed

Message:

~~~text
FATAL:  Peer authentication failed for user "postgres"
~~~

This means the connection reached PostgreSQL, but the OS identity failed the `peer` rule for that role. Check `whoami`/`id` on the client, the requested role, the matching `local` line, and any `pg_ident.conf` mapping.

Never switch `local all all` to `trust`, as `trust` allows matching clients to connect without password verification.

## 16. Common TCP Loopback Errors

### 16.1. Connection Refused

Typical message:

~~~text
connection to server at "127.0.0.1", port 5432 failed:
Connection refused
~~~

Possibilities:

- PostgreSQL is not running or not listening on TCP.
- `listen_addresses` does not include the target loopback address.
- The server is listening on a different port.
- You are inside a different network namespace (e.g., a container), so `127.0.0.1` points elsewhere.
- Network policy or firewall blocks the connection.

Check:

~~~bash
pg_isready -h 127.0.0.1 -p 5432
~~~

In an active admin session:

~~~sql
SHOW listen_addresses;
SHOW port;
~~~

On Linux, check listeners with `ss -ltn`. Modifying `listen_addresses` typically requires a PostgreSQL **restart** for the new listener to take effect.

### 16.2. No pg_hba.conf Entry

Typical message:

~~~text
FATAL: no pg_hba.conf entry for host "127.0.0.1",
user "app_user", database "app_db", ...
~~~

The server received the connection request but found no rule matching the connection type, role, database, client address, and encryption criteria. Check:

- Whether you are connecting via `127.0.0.1` or `::1`.
- Whether a `host`/`hostssl` rule exists for the exact address and database.
- Whether the server reloaded `pg_hba.conf` after editing.
- Whether SSL/TLS or non-SSL is specifically required.
- Whether an earlier `reject` or broader rule matched first.

Never substitute `host all all 0.0.0.0/0 trust` "just for a quick test"; that severely widens exposure.

### 16.3. Password Authentication Failed

~~~text
FATAL: password authentication failed for user "app_user"
~~~

Verify the role, entered password, verifier compatibility with `scram-sha-256`, authentication method on the matched `pg_hba.conf` line, and credential policies.

Never assume an OS account password must match the PostgreSQL role password. They are separate authentication systems unless explicitly integrated.

### 16.4. Role or Database Does Not Exist

~~~text
FATAL: role "alice" does not exist
FATAL: database "alice" does not exist
~~~

This commonly happens when running `psql` without `-U` or `-d`, causing the client to default to the OS username.

Specify them explicitly:

~~~bash
psql -h 127.0.0.1 -U app_user -d app_db
~~~

If the role/database genuinely does not exist yet, an administrator must create them and grant privileges per policy. Switching transport from socket to TCP does not create roles or databases.

## 17. Unix Sockets, Docker, and Development Environments

### 17.1. localhost Inside a Container Is That Container's Loopback

Suppose the application runs in **container A** and PostgreSQL runs in **container B**. Running inside A:

~~~bash
psql -h 127.0.0.1 -p 5432 -U app_user -d app_db
~~~

looks for PostgreSQL inside **A's network namespace**, not B. On a Docker Compose network, applications typically connect by service name, such as:

~~~bash
psql -h db -p 5432 -U app_user -d app_db
~~~

Here `db` is the hypothetical service name provided by Compose/DNS. This is TCP **between two containers**, no longer local loopback within the client's own container.

### 17.2. What If You Want to Use a Unix Socket Between Containers?

Two containers can share a Unix-domain socket only if you configure a **shared accessible socket path**—for instance via a shared volume/mount—while resolving OS permissions, socket lifecycle, and PostgreSQL policies. This requires careful administration and is not the Docker Compose default.

Therefore, for containerized apps, TCP via service name is usually simpler and less filesystem-dependent.

### 17.3. Windows and WSL

On Windows, many PostgreSQL clients default to TCP `localhost` rather than Unix sockets as on Linux. If your app runs inside WSL while PostgreSQL runs on Windows (or vice versa), the two environments have distinct network and filesystem boundaries. Never assume `/var/run/postgresql` or `127.0.0.1` in one environment automatically reaches a server in the other.

Confirm where the **client** runs, where the **server** runs, and the actual network forwarding path before editing `pg_hba.conf`.

## 18. Java/JDBC Connections Typically Use TCP

In Java application development, a typical PostgreSQL JDBC URL looks like:

~~~text
jdbc:postgresql://127.0.0.1:5432/app_db
~~~

Connection example:

~~~java
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;

String url = "jdbc:postgresql://127.0.0.1:5432/app_db";
String username = "app_user";
String password = System.getenv("DB_PASSWORD");

try (Connection connection =
         DriverManager.getConnection(url, username, password);
     PreparedStatement ps =
         connection.prepareStatement(
             "SELECT current_user, current_database(), inet_client_addr()"
         );
     ResultSet rs = ps.executeQuery()) {

    if (rs.next()) {
        System.out.println(rs.getString(1));
        System.out.println(rs.getString(2));
        System.out.println(rs.getString(3));
    }
}
~~~

This snippet assumes the project includes the PostgreSQL JDBC driver dependency and sets `DB_PASSWORD`. In production apps, manage credentials via a secret manager, use a connection pool, and configure SSL/TLS appropriate for your deployment model.

**Difference from psql on Unix:** the URL above specifies `127.0.0.1`, so it uses **TCP** and matches `host` lines in `pg_hba.conf`. Do not assume that because `sudo -u postgres psql` (socket `peer`) works, a JDBC app using a username/password will automatically succeed.

Using Unix sockets with pgJDBC requires configuring custom socket factories; it is not the default behavior of a standard TCP URL.

## 19. Decision Guide

You can choose the right approach using a simple decision flow:

~~~mermaid
flowchart TD
    A["Where is the client?"] --> B{"Same OS environment as PostgreSQL?"}
    B -->|"No"| T["TCP to appropriate hostname/service"]
    B -->|"Yes"| C{"Need to rely on OS user identity?"}
    C -->|"Yes, with peer policy"| U["Unix-domain socket + pg_hba local/peer"]
    C -->|"No"| D{"Does driver/client explicitly support sockets?"}
    D -->|"Yes"| E["Unix socket or TCP loopback"]
    D -->|"No / Standard JDBC URL"| F["TCP loopback + pg_hba host"]
    T --> G["Check listen_addresses, network, pg_hba"]
    U --> H["Check unix_socket_directories, OS perms, pg_hba local"]
    E --> I["Verify actual connection path and auth"]
    F --> I
~~~

A standard configuration workflow follows this order:

1. Identify **where the client actually runs** and which PostgreSQL server it targets.
2. Choose the **transport**: Unix socket, TCP loopback, or network TCP.
3. Confirm **role, database, port**, and login credentials.
4. Verify the server is listening on the expected socket/address.
5. Check the first matching `pg_hba.conf` entry and its authentication method.
6. Use `pg_isready` to verify connection readiness.
7. Test authentication with `psql` or the actual app, then confirm transport via `\conninfo`/`inet_client_addr()`.
8. Apply the **principle of least privilege**; never widen listeners or enable `trust` merely to bypass config errors.

## 20. Practice Exercises

### Exercise 1: Identifying the Transport

Run two commands on a Linux machine with PostgreSQL:

~~~bash
psql -U app_user -d app_db
psql -h 127.0.0.1 -U app_user -d app_db
~~~

Identify which command uses a Unix socket by default and which uses TCP. Note that the first command can be altered by the `PGHOST` environment variable; for unambiguous behavior, pass `-h /path/to/socket` explicitly.

### Exercise 2: Why Do peer and SCRAM Behave Differently?

Suppose `pg_hba.conf` contains:

~~~conf
local   all   postgres                  peer
host    all   postgres   127.0.0.1/32   scram-sha-256
~~~

OS user `alice` tries `psql -U postgres -d postgres` and gets a peer error. When adding `-h 127.0.0.1`, the client prompts for a password. Explain: **changing the transport changes which `pg_hba.conf` rule type is matched**, not the PostgreSQL role itself.

### Exercise 3: Which Address Does localhost Choose?

Test:

~~~bash
psql -h localhost -U app_user -d app_db
psql -h 127.0.0.1 -U app_user -d app_db
psql -h ::1 -U app_user -d app_db
~~~

Once connected, run:

~~~sql
SELECT inet_client_addr(), inet_server_addr();
~~~

Match the addresses against the `127.0.0.1/32` and `::1/128` rules. Do not assume every environment has IPv6 enabled.

### Exercise 4: Distinguishing Server Errors from Authentication Errors

If `pg_isready -h 127.0.0.1 -p 5432` reports `accepting connections`, yet `psql -h 127.0.0.1 -U app_user -d app_db` reports "password authentication failed", what should you check?

**Answer:** the server accepted the connection at the protocol level; check `app_user`'s credentials, `scram-sha-256` method, the exact matched rule, role password, and related settings. Do not restart the server as a first step when the real issue is password authentication.

### Exercise 5: Fixing Socket Path Errors

Running `psql -h /tmp -p 5432 ...` reports "No such file or directory", whereas a TCP connection `-h 127.0.0.1` succeeds. Run `SHOW unix_socket_directories;` from the TCP session to find the real socket path. If the socket resides in `/var/run/postgresql`, retry with `-h /var/run/postgresql`.

### Exercise 6: Diagnosing Container Connection Issues

The app is in container `web` and PostgreSQL is in container `db`. Why does `-h 127.0.0.1` inside container `web` fail to reach `db`?

**Answer:** `127.0.0.1` is container `web`'s own loopback; you must use the address/service name provided by the system's network, such as `-h db` when the Docker Compose network is configured properly.

## 21. Summary

Both **Unix-domain sockets** and **TCP loopback** let a client access PostgreSQL on the same host, yet they are **two distinct transport paths**:

- Unix sockets use a directory path and `local` rules in `pg_hba.conf`, and can use OS-user-based `peer` authentication.
- TCP loopback uses `127.0.0.1` or `::1`, depends on `listen_addresses` and `host` rules in `pg_hba.conf`, and commonly uses SCRAM passwords for application accounts.
- The exact same PostgreSQL role can succeed via one path and fail via the other because **transport, authentication rules, and client identity** differ.

When troubleshooting connection failures, check in order: **correct server → correct transport → correct address/socket and port → correct pg_hba rule → correct role/database/password**. This systematic approach resolves issues cleanly without arbitrarily weakening PostgreSQL security.
