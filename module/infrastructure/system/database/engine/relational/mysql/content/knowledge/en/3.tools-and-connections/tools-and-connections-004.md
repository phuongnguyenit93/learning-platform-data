# TCP/IP, Unix Socket, and Named Pipe Connections by Platform

In the **DATABASE_MYSQL** module, learners master MySQL from table design, data types, keys, and SQL queries to indexes, transactions, concurrency control, reading execution plans, query tuning, privilege management, backups, and operations. To practice these topics, you first need to understand the mechanisms by which a client program communicates with MySQL Server. MySQL supports TCP/IP across operating systems, Unix domain sockets on Unix/Linux, and named pipes on Windows. Choosing the right transport mechanism ensures reliable connections, easier diagnostics, and compliance with environment security requirements.

## 1. Three Connection Mechanisms

When a client opens a connection, it must specify the server, protocol, address or endpoint name, and authentication credentials. MySQL then accepts the connection, performs the protocol handshake, authenticates the account, and checks privileges. The transport protocol only determines the path data takes from client to server; it does not replace MySQL's account and privilege system.

| Mechanism | Platform | Connection Address | Typical Scope | Characteristics |
|---|---|---|---|---|
| TCP/IP | Windows, Linux, Unix, macOS | Host/IP and port, usually `3306` | Same host or over a network | Suitable for client/server applications and remote connections |
| Unix domain socket | Linux, Unix, macOS | Socket file path | Processes on the same host | Uses no IP or TCP port; access permissions depend on the OS |
| Named pipe | Windows | Pipe name, default usually `MySQL` | Primarily processes on the Windows host running MySQL | Requires named pipe enabled on the server and the client selecting the right protocol |

TCP/IP is the standard choice for backend applications, even when the application and MySQL reside on the same host. Unix sockets are often convenient for command-line tools on Linux. Named pipes are a Windows-specific IPC mechanism. You cannot use a Unix socket path on Windows or ask a Linux client to open a Windows named pipe as a local file.

## 2. Connecting via TCP/IP

### 2.1. Address and Port

TCP/IP uses a network address and port. For the classic MySQL protocol, the default port is typically `3306`; an instance can be configured to use a different port. The client must know the correct host and port:

```bash
mysql --protocol=TCP --host=127.0.0.1 --port=3306 --user=app_user --password
```

`--protocol=TCP` forces the client to use TCP. `--host` can be an IP address or DNS name. `127.0.0.1` is IPv4 loopback, pointing only to the machine running the client; when connecting from another machine, replace it with a routable server hostname or IP address. If the server listens on IPv6, the client can use an IPv6 address such as `::1` for loopback or the server's IPv6 address.

On Unix, `localhost` typically causes the client to choose a Unix socket instead of TCP. Therefore, when testing TCP on the same host, use `127.0.0.1` together with `--protocol=TCP`. When you need to eliminate guesswork about default protocols, specify `--protocol` explicitly.

Do not enter the password directly on the command line. Use `--password` or `-p` without a value so the client prompts interactively; this prevents the password from appearing in shell history or process lists.

### 2.2. Server Configuration

Key TCP options reside in the `[mysqld]` group of the configuration file:

```ini
[mysqld]
port=3306
bind-address=127.0.0.1
```

- `port` specifies the TCP port MySQL Server uses for the classic SQL protocol.
- `bind-address` specifies the network address the server listens on. `127.0.0.1` restricts IPv4 connections to the local machine; a specific IP address restricts listening to that interface; `0.0.0.0` listens on all IPv4 interfaces.
- `skip-networking`, when enabled, disables TCP/IP connections. TCP clients will not be able to connect even though the server may still accept connections over other local mechanisms.

If an application on another machine needs to access MySQL, the server must listen on an interface reachable from that application. At the same time, firewalls or security groups must allow traffic from the right sources to the right port. Do not open the MySQL port to the entire Internet just to resolve a connection error.

Changing `port`, `bind-address`, or `skip-networking` generally requires restarting the service to take effect. After applying changes, verify runtime values via SQL:

```sql
SHOW GLOBAL VARIABLES WHERE Variable_name IN
  ('port', 'bind_address', 'skip_networking');
```

### 2.3. Securing TCP Connections

When data crosses a network, consider TLS encryption and server identity verification. With modern MySQL clients, you can require certificate and hostname verification:

```bash
mysql --protocol=TCP \
  --host=db.example.internal \
  --port=3306 \
  --user=app_user \
  --password \
  --ssl-mode=VERIFY_IDENTITY \
  --ssl-ca=/path/to/ca.pem
```

The CA path is an example and must point to the environment's trusted CA certificate. `VERIFY_IDENTITY` requires TLS, verifies the certificate chain, and checks that the hostname matches the certificate. Enabling encryption without verifying server identity can still allow a client to connect to the wrong endpoint. On the server side, you can enforce secure connections with the `require_secure_transport` variable, depending on version and deployment policy.

TLS does not replace network restrictions, account authentication, and least-privilege grants. Use dedicated application accounts, restrict allowed client hosts, and grant privileges only on the schemas or objects the application needs.

### 2.4. TCP in Java Applications

Java applications using MySQL Connector/J typically connect with a JDBC URL over TCP/IP. For example:

```java
String url = "jdbc:mysql://db.example.internal:3306/sales";
Connection connection = DriverManager.getConnection(url, user, password);
```

In environments requiring TLS, configure `sslMode=VERIFY_IDENTITY` and trust material according to the documentation of your Connector/J version. Do not hard-code passwords in source code; read secrets from your deployment environment's configuration or secrets manager. Even if the Java application runs on the same Linux host as MySQL, TCP loopback remains a common direct connection approach and is supported by Connector/J through standard JDBC URLs.

## 3. Connecting via Unix Domain Socket

### 3.1. How It Works

A Unix domain socket is an inter-process communication mechanism in Unix-like operating systems. Instead of sending packets over an IP address and TCP port, the client opens a socket file endpoint on the same machine as MySQL Server. A common path is `/run/mysqld/mysqld.sock`, though the actual location depends on the distribution, package, and instance configuration.

Sockets are suitable for local clients such as the MySQL CLI, administrative scripts, or co-located services whose libraries support Unix sockets. They are not network endpoints that clients on other hosts can access directly. If you need to connect between two machines, use TCP/IP or an appropriate tunneling solution.

### 3.2. Configuration and Connection

The server and client must use the same socket path. Example on Linux:

```ini
[mysqld]
socket=/run/mysqld/mysqld.sock

[client]
socket=/run/mysqld/mysqld.sock
```

Connecting with the MySQL CLI:

```bash
mysql --protocol=SOCKET \
  --socket=/run/mysqld/mysqld.sock \
  --user=app_user \
  --password
```

To inspect the socket path the server is using:

```sql
SHOW GLOBAL VARIABLES LIKE 'socket';
```

Clients can also pick up default values from the `[client]` group in an option file. When troubleshooting, pass `--protocol=SOCKET` and `--socket` explicitly so you know for certain which endpoint the client is attempting to use.

### 3.3. Socket Permissions

Socket access is governed by permissions on the socket file and its parent directories. The OS account running the client must have execute/traverse permission on the directories and read/write permission on the endpoint; the MySQL service account needs permission to create the socket in the target directory. Some systems place the socket under `/run`, a runtime directory that is recreated after reboot.

OS permissions and MySQL privileges are two separate layers. Having permission to open the socket does not mean you are allowed to log in to the database; MySQL still authenticates the account and checks grants. Conversely, a MySQL account with the right password still cannot connect if the OS process cannot open the socket file.

Do not delete the socket file while the server is running. If you need to change the path, update both server and client configurations, verify the target directory and ownership, and restart the service following administrative procedures.

## 4. Connecting via Named Pipe on Windows

### 4.1. Named Pipe Mechanism

A named pipe is a Windows inter-process communication mechanism. MySQL Server accepts named pipe connections only when the feature is enabled. The default pipe name is usually `MySQL`; the actual value can be configured. Named pipes are often useful for clients running on the same Windows host as MySQL Server without needing to open a TCP port for that connection flow.

Named pipes still go through MySQL account authentication. Windows ACLs control which processes can open the pipe, while MySQL controls user, host, and database privileges. Both permission layers must be configured properly.

### 4.2. Enabling Named Pipes on the Server

In the MySQL configuration file on Windows, place options under `[mysqld]`:

```ini
[mysqld]
enable-named-pipe
socket=MySQL
```

`enable-named-pipe` enables the named pipe protocol. The `socket` option in a Windows context specifies the pipe name to use; the default name is usually `MySQL`. If you change the name, clients must also use that exact name. This configuration change requires restarting MySQL Server.

MySQL provides the `named_pipe_full_access_group` option to specify a Windows group granted full access to the named pipe. When deploying in a multi-user environment, evaluate the assigned group and ACL policy under the principle of least privilege. Do not add this option with a sample group name without verifying the actual group name on the machine.

### 4.3. Connecting from a Windows Client

The client must select protocol `PIPE` and specify the pipe name if not using the default:

```powershell
mysql --protocol=PIPE --socket=MySQL --user=app_user --password
```

If the server and client use different pipe names, the client will fail to open the endpoint even while the MySQL service is running. If named pipes are not enabled on the server, `PIPE` connection attempts will also fail. Check the server configuration file, service status, pipe name, and Windows permissions before modifying MySQL accounts.

Windows also supports a shared-memory mechanism in certain MySQL configurations. That is a different local protocol from named pipes; the server must enable the shared-memory option and the client must select protocol `MEMORY`. When a task calls for named pipes, do not confuse `--protocol=PIPE` with `--protocol=MEMORY`.

## 5. Choosing the Right Protocol

| Scenario | Typically Appropriate Choice | Reason |
|---|---|---|
| Java application or backend service connecting to MySQL over a network | TCP/IP | Standard JDBC URLs support host and port; easy to deploy across hosts |
| MySQL CLI running on the same Linux host | Unix socket or TCP loopback | Socket is convenient for local administration; TCP is useful when testing the exact network path |
| Application running on another host | TCP/IP with TLS | A socket file is not a network-accessible endpoint; TCP supports remote connections |
| Windows tool requiring local connection via named pipe | Named pipe | Windows IPC; avoids using a TCP port for that connection |
| Need standardized diagnostics across all operating systems | Explicitly specified TCP/IP | Uniform host/port model and easy to verify with network tools |

Before choosing, answer three questions: which operating system does the client run on, is the client on the same host or a different host, and does the connector library support that protocol? For Java applications using standard Connector/J, prefer JDBC over TCP/IP; do not assume a JDBC URL can natively use a Unix socket or Windows named pipe.

## 6. Determining Which Protocol the Client Actually Uses

Do not rely solely on the hostname in configuration. Defaults can cause the client to choose a different protocol than expected. On Unix, `localhost` normally uses a socket; `127.0.0.1` with `--protocol=TCP` forces a TCP connection. On Windows, specify `--protocol=TCP` or `--protocol=PIPE` explicitly when testing.

Corresponding command examples:

```bash
# TCP/IP
mysql --protocol=TCP --host=127.0.0.1 --port=3306 -u app_user -p

# Unix domain socket (Linux/Unix)
mysql --protocol=SOCKET --socket=/run/mysqld/mysqld.sock -u app_user -p
```

```powershell
# TCP/IP on Windows
mysql --protocol=TCP --host=127.0.0.1 --port=3306 -u app_user -p

# Named pipe on Windows
mysql --protocol=PIPE --socket=MySQL -u app_user -p
```

After logging in, the `status` command in the MySQL CLI displays session details, including the connection type the client is using. You can run:

```sql
SHOW SESSION STATUS LIKE 'Ssl_cipher';
SHOW GLOBAL VARIABLES WHERE Variable_name IN ('port', 'socket', 'bind_address');
```

`status` confirms the client-side transport; the system variables show server configuration. `Ssl_cipher` has a non-empty value when the session is using TLS. Never assume a TCP connection is encrypted; verify the actual TLS configuration and status.

## 7. Layer-by-Layer Connection Troubleshooting

| Symptom | Possible Cause | How to Check |
|---|---|---|
| TCP reports `Connection refused` | No process listening on address/port, service stopped, or wrong port | Check MySQL status, `@@port`, `@@bind_address`, and listening port list |
| TCP timeout | Firewall, security group, routing, or incorrect DNS | Check name resolution, network path, firewall rules, and test from the actual client host |
| TCP connects but `Access denied` | Wrong password, account host mismatch, or missing privileges | Check user, allowed host, authentication method, and grants |
| Socket reports `No such file or directory` | Client uses wrong path or server did not create the socket | Read `@@socket`, inspect socket file and error log |
| Socket reports `Permission denied` | Inadequate permissions on socket file or parent directories | Check user/group, directory permissions, and OS security policies |
| Named pipe does not exist or cannot be opened | Server has not enabled named pipe, wrong pipe name, or service not ready | Check `enable-named-pipe`, `socket` name, server status, and client config |
| Named pipe access denied | Windows ACL or group does not grant permission to open pipe | Check ACLs, `named_pipe_full_access_group`, and client process identity |

### 7.1. Tools for Checking TCP

On Linux, you can list listening TCP ports:

```bash
ss -ltnp
```

To filter for the default port:

```bash
ss -ltnp 'sport = :3306'
```

On Windows PowerShell:

```powershell
Get-NetTCPConnection -LocalPort 3306 -State Listen
Test-NetConnection -ComputerName db.example.internal -Port 3306
```

`Get-NetTCPConnection` checks TCP sockets on the local machine; `Test-NetConnection` checks reachability of a host/port from the client machine. These tools do not verify MySQL passwords or privileges.

### 7.2. Tools for Checking Unix Sockets

On Linux, use:

```bash
ss -lxnp
ls -l /run/mysqld/mysqld.sock
```

The name and path must match `@@socket`. If the socket does not exist, inspect the service status and error log to find out why the server did not create the endpoint. If the socket exists but access is denied, inspect permissions along the entire path, not only the final file.

### 7.3. Checking Logs and Runtime State

When a client cannot connect, read the MySQL error log and service logs to check for errors during startup or endpoint creation. You can retrieve the error log path via:

```sql
SHOW GLOBAL VARIABLES LIKE 'log_error';
```

Once you have an SQL session, cross-check runtime configuration:

```sql
SELECT @@hostname AS server_host,
       @@port AS tcp_port,
       @@bind_address AS bind_address,
       @@socket AS local_endpoint,
       @@skip_networking AS tcp_disabled;
```

Note that `@@socket` on Unix is typically the Unix socket path; on Windows, when named pipes are enabled, this value may indicate the pipe name. Interpret the value in the proper operating system context.

## 8. Hands-On Lab: Comparing Connection Protocols

Perform this lab on a development instance or lab environment you are authorized to access. Use your assigned account and do not modify shared server configurations without a plan.

**Step 1 — Record server configuration.** Connect using a working method and run a query to fetch `port`, `bind_address`, `socket`, `skip_networking`, and `hostname`. Record the OS, MySQL version, and error log path.

**Step 2 — Test TCP explicitly.** On the host running MySQL, connect to `127.0.0.1` using `--protocol=TCP` and the runtime port. If testing from another machine, use the server's hostname/IP and verify the firewall permits the client source.

**Step 3 — Test OS-appropriate IPC.** On Linux/Unix, connect using `--protocol=SOCKET` and the exact `@@socket`. On Windows, test named pipes only if the server has `enable-named-pipe` enabled; use `--protocol=PIPE` and the exact pipe name. Do not attempt to run Unix socket commands on Windows.

**Step 4 — Verify the transport.** After each login, run `status` in the MySQL CLI and record the connection type. Compare it against the protocol specified in the command.

**Step 5 — Classify errors.** If a method fails, determine whether the failure is at the endpoint layer, network/OS permission layer, or MySQL authentication/privilege layer. Use OS tools and the error log to gather evidence before changing configuration.

**Expected outcome:** able to explain why TCP/IP uses host/port, Unix sockets use a file path, and named pipes use a pipe name on Windows; able to select protocols explicitly, verify actual transport, and isolate faults by layer.

## 9. Key Principles to Remember

- TCP/IP is cross-platform and suited for remote connections; control `bind-address`, firewalls, TLS, and MySQL accounts.
- Unix sockets are local IPC on Unix-like systems; server and client must agree on the path and maintain proper OS permissions.
- Named pipes are Windows IPC; the server must enable `enable-named-pipe`, the client must choose `PIPE`, and both sides must use the same pipe name.
- The transport protocol does not grant database privileges. After opening a connection, MySQL still authenticates the account and enforces grants.
- When diagnosing issues, specify `--protocol` explicitly and inspect `status` to avoid defaulting to an unintended protocol.
- For Java applications using standard MySQL Connector/J, use TCP/IP via a JDBC URL and configure TLS when connecting over a network.

Understanding how MySQL connects across platforms helps you select the right endpoint for clients, enforce proper access controls, and quickly isolate whether an issue lies in the network, OS IPC, or the MySQL authentication layer.
