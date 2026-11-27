# Configuration Files, Ports, Sockets, and the Data Directory

In the **DATABASE_MYSQL** module, learners master MySQL from table design, data types, keys, and SQL queries to indexes, transactions, concurrency control, reading execution plans, query optimization, access privileges, backups, and operations. Before practicing those topics, you need to understand where MySQL Server reads its configuration from, which port or socket it accepts connections on, and which directory it stores data in. These details determine whether an application connects to the right server, whether the server can start, and whether data is protected during operations.

## 1. The Big Picture

MySQL typically consists of a server process `mysqld` and one or more client programs such as `mysql`. The server reads its configuration at startup, opens connection endpoints, and accesses the data directory. Client programs can also read their own configuration file to determine how to connect.

| Component | Role | Example |
|---|---|---|
| Server configuration file | Configures how `mysqld` operates | `port`, `bind-address`, `socket`, `datadir` |
| TCP port | Accepts connections over an IP network | `3306` |
| Local socket | Accepts inter-process connections on the same Unix/Linux machine | `/run/mysqld/mysqld.sock` |
| Data directory | Stores the instance's data files and metadata | `/var/lib/mysql` |
| Client configuration file | Sets defaults for client programs | `[client]`, `[mysql]` |

The TCP port, socket, and data directory are three distinct settings. Changing the port does not automatically change the socket; changing the socket does not move data; changing `datadir` does not inform applications of a new connection address. When running multiple MySQL instances on the same machine, each instance must have its own configuration, and resources such as port, socket, PID file, and data directory must not conflict.

## 2. MySQL Configuration Files

### 2.1. Common Locations

The name and location of the configuration file depend on the operating system, installation method, and how MySQL was packaged. Common locations include:

| Environment | Common Location |
|---|---|
| Debian/Ubuntu | `/etc/mysql/my.cnf`; server configuration files are typically under `/etc/mysql/mysql.conf.d/` |
| RHEL/Oracle Linux and similar distributions | `/etc/my.cnf`; additional files may reside under `/etc/my.cnf.d/` |
| Windows installed via MySQL Installer | Typically `C:\ProgramData\MySQL\MySQL Server 8.0\my.ini`; version and installation path may vary |
| macOS or manual installations | Depends on the installer package and how MySQL was compiled |

Do not guess the configuration file from the operating system alone. Ask the MySQL program itself which option files and option groups it reads:

```bash
mysqld --verbose --help
mysql --verbose --help
```

Near the top of the output, look for the lines listing the option files read in order. The first command checks how the server searches for configuration; the second checks how the client searches for configuration. On Windows, run the commands from the directory containing the binaries or use the corresponding executable names, such as `mysqld.exe`.

To view the options read from option files:

```bash
mysqld --print-defaults
my_print_defaults mysqld
mysql --print-defaults
```

The output may contain sensitive information if someone placed secrets inside a configuration file; do not post the raw output publicly. These commands help inspect option files, but they do not replace verifying the runtime values of the running server.

### 2.2. Option Groups and Syntax

MySQL configuration files use groups enclosed in square brackets. The server reads server-targeted groups, while client programs read client-targeted groups:

- `[mysqld]`: options applied to MySQL Server.
- `[client]`: shared options for MySQL client programs.
- `[mysql]`: options specific to the `mysql` command-line client.

Minimal configuration example on Linux:

```ini
[mysqld]
port=3306
bind-address=127.0.0.1
socket=/run/mysqld/mysqld.sock
datadir=/var/lib/mysql

[client]
port=3306
socket=/run/mysqld/mysqld.sock
```

In this example, the server accepts TCP on port 3306 at the loopback address and creates a socket at the specified path. Clients can use the same port and socket as defaults. The paths are examples only: use the actual paths of the machine being configured, ensure parent directories exist, and verify the MySQL service account has appropriate permissions.

Option names can generally be written with hyphens or underscores, such as `bind-address` and `bind_address`. Lines starting with `#` or `;` can be used as comments. Options must be placed in the right group; putting `datadir` inside `[client]` does not configure the server's data directory.

A configuration file can include another file using `!include` or include a directory using `!includedir`. Therefore, a change in the main file can be overridden by a file read later. Check the actual read order and included files before concluding which value takes effect.

Options passed directly on the command line can override values in configuration files. MySQL 8.0 also supports variables persisted with `SET PERSIST`; these values are stored in `mysqld-auto.cnf` in the data directory and loaded on startup. When the actual runtime value differs from the file you just edited, check both startup arguments and persisted variables. You can view persisted variables with:

```sql
SELECT VARIABLE_NAME, VARIABLE_VALUE
FROM performance_schema.persisted_variables;
```

If you need to force a program to read a specific file, use `--defaults-file`; this option must appear immediately after the program name, before any other options:

```bash
mysql --defaults-file=/path/to/client.cnf --protocol=TCP
```

## 3. TCP Port and Bind Address

### 3.1. What Is the Port Used For?

MySQL Server typically uses TCP port **3306** for standard SQL connections. This is a common default, not a guarantee that every instance uses this port. MySQL X Protocol typically uses port **33060** when the X Protocol plugin is enabled; this port serves a separate protocol and does not replace the classic SQL port 3306.

Clients must connect to the right IP address or hostname, the right port, and the right protocol. Example of connecting via TCP to a server on the same machine:

```bash
mysql --protocol=TCP --host=127.0.0.1 --port=3306 --user=app_user --password
```

The `--password` option in this form tells the client to prompt interactively for the password; do not place the password directly in the command because shell history and process listings can expose secrets. When connecting to a remote server, replace `127.0.0.1` with the server's address or DNS name.

### 3.2. Bind Address Determines Which Hosts Can Connect

The `bind-address` option specifies the network address the server listens on:

- `127.0.0.1`: accepts IPv4 connections only from the same machine.
- A specific private IP address: listens only on the corresponding network interface.
- `0.0.0.0`: listens on all IPv4 interfaces; must be restricted via firewall and network policy.

If the server only serves applications running on the same machine, binding to loopback is usually a good way to limit scope. If connections from other machines are needed, choose the appropriate interface, open the firewall for the exact source and port, and configure MySQL accounts with least privilege. Do not expose the MySQL port to the Internet merely for connection convenience.

If the `skip-networking` option is enabled, the server does not accept TCP connections; in that case, TCP clients cannot connect even though the local socket may still work. Also distinguish between a firewall blocking connections and a server not listening: these two causes have different fixes.

## 4. Local Sockets

On Linux and Unix, a Unix domain socket allows processes on the same machine to communicate through a socket file. This connection does not go over TCP/IP and does not require opening a network port. The socket path is typically configured using the `socket` variable in the `[mysqld]` group.

Clients also need to know the corresponding socket path. For example:

```ini
[mysqld]
socket=/run/mysqld/mysqld.sock

[client]
socket=/run/mysqld/mysqld.sock
```

If the server creates the socket at one path while the client looks at another path, the client may report that it cannot connect even though the service is running. Check the server-side value:

```sql
SHOW GLOBAL VARIABLES LIKE 'socket';
```

And test connecting with an explicit path:

```bash
mysql --protocol=SOCKET --socket=/run/mysqld/mysqld.sock --user=app_user --password
```

On Unix, connecting to `localhost` typically selects the Unix socket, whereas `127.0.0.1` selects TCP. When accurate diagnosis is required, specify `--protocol=SOCKET` or `--protocol=TCP` rather than relying on defaults. On Windows, local mechanisms may be a named pipe or shared memory if enabled; Unix domain sockets and Linux-style paths do not apply directly.

Socket access depends on permissions on the socket file and its parent directory. If a client lacks access permission, inspect user/group ownership and service configuration. Do not delete the socket file arbitrarily without verifying the server process state; the file may be actively in use or managed by the service.

## 5. Data Directory (datadir)

The `datadir` variable indicates the root directory that a MySQL instance uses to store data. This directory may contain database subdirectories, system metadata, tablespace files, redo logs, undo logs, and other files depending on the version and storage engine configuration. Binary logs and certain other logs can be placed on separate paths, so do not assume all logs live inside `datadir`.

Inspect the path currently used by the server:

```sql
SHOW GLOBAL VARIABLES LIKE 'datadir';
-- Or query alongside other environment settings:
SELECT @@global.port,
       @@global.bind_address,
       @@global.socket,
       @@global.datadir;
```

The data directory belongs to the server process. The OS account running `mysqld` needs read, write, and traversal permissions on the required parent directories. On Linux, you may also need to adjust SELinux or AppArmor policies when moving data to a new location. Never resolve permission errors by granting broad write permissions to all users.

### 5.1. Changing datadir Safely

Changing `datadir` is an operation that directly affects data and startup. General procedure:

1. Identify the exact instance, MySQL version, current data path, and the OS account running the service.
2. Create a restorable backup; verify the backup before making the switch.
3. Stop MySQL cleanly and confirm the process has stopped completely.
4. Prepare the destination directory, copy or restore the data using an appropriate method, preserving ownership, permissions, and required metadata.
5. Update `datadir` in the exact configuration for the instance; also check related paths such as logs, socket, and PID file if they depend on the old location.
6. Start the service, read the error log, and verify system variables along with application data.
7. Only remove the old data after verifying the new setup works and your backup remains restorable.

Never copy data files actively used by `mysqld` with a plain file copy. Never run initialization on a directory that already contains data you need to keep. When version or storage format differences exist, backing up and restoring with MySQL tools is usually safer and more controllable than moving raw files.

When creating a brand-new instance, the data directory must be initialized according to the documentation for the version and package in use. `mysqld --initialize` creates the initial system data and generates a temporary password for the root account; this password is written to the error log. `--initialize-insecure` creates a root account without an initial password and is only suitable for isolated lab environments that are secured immediately afterward. Never run initialization commands on an existing data directory.

## 6. Applying and Verifying Configuration

A configuration change is only considered complete after confirming the server starts with the desired values and clients connect via the intended path.

1. **Identify the exact instance.** Determine the binary, configuration file, service name, and data directory. If multiple instances exist, do not rely on default service names.
2. **Back up the configuration file.** Save the original before editing so you can roll back if the new configuration prevents the service from starting.
3. **Edit the correct group.** Put server options in `[mysqld]` and shared client options in `[client]`. Check included files and service command-line options.
4. **Check before applying.** Use `mysqld --print-defaults` or `my_print_defaults mysqld` to review option files; use configuration validation syntax supported by the installed version if available.
5. **Restart the right service when needed.** On Linux, the service name is usually `mysql` or `mysqld`; verify the actual name before restarting. For example, when the service is named `mysql`:

   ```bash
   sudo systemctl restart mysql
   sudo systemctl status mysql
   sudo journalctl -u mysql -n 100 --no-pager
   ```

   On Windows, you can locate the service with `Get-Service *mysql*`, then verify the exact service name before restarting.

6. **Verify from inside MySQL.** Once connected, run:

   ```sql
   SELECT @@global.port AS tcp_port,
          @@global.bind_address AS bind_address,
          @@global.socket AS socket_path,
          @@global.datadir AS data_directory,
          @@global.skip_networking AS skip_networking;
   ```

7. **Verify at the OS level.** On Linux, use `ss -ltnp` to view listening TCP ports and `ss -lxnp` to view Unix sockets. On Windows, use `Get-NetTCPConnection -LocalPort 3306 -State Listen` with the exact configured port. OS-level output helps distinguish a server that is not listening from a client or firewall error.

The error log path can be retrieved with `SHOW GLOBAL VARIABLES LIKE 'log_error';`. If the service fails to start, read this log or the service log before making further edits; error messages usually point to an invalid option, malformed configuration syntax, an occupied port, or an inaccessible data directory.

## 7. Practice Exercise: Identifying Connection Paths and Data Location

Perform this on a development instance or lab environment you are authorized to access.

**Step 1 — Locate the configuration.** Run `mysqld --verbose --help` and record the list of files the server reads. Open the relevant file, identify the `[mysqld]` group, any included files, and the values related to `port`, `bind-address`, `socket`, and `datadir`.

**Step 2 — Read the effective configuration.** Run `my_print_defaults mysqld` and compare it with the file you just read. If there are differences, check file order, included files, and startup flags.

**Step 3 — Read runtime values.** Connect with your assigned account and run:

```sql
SELECT @@hostname AS server_name,
       @@port AS tcp_port,
       @@bind_address AS bind_address,
       @@socket AS socket_path,
       @@datadir AS data_directory;
```

Record the output. These are the values the server is actually using, which are more reliable than looking at a single configuration file that may not even be loaded.

**Step 4 — Test a TCP connection.** Use the loopback address and the port you identified:

```bash
mysql --protocol=TCP --host=127.0.0.1 --port=3306 --user=app_user --password
```

Replace the port with the actual value if the instance does not use 3306. To test a socket on Linux, use:

```bash
mysql --protocol=SOCKET --socket=/run/mysqld/mysqld.sock --user=app_user --password
```

Replace the path with the `@@socket` value you read earlier. Compare the two connections and identify which one uses TCP and which uses the socket.

**Step 5 — Cross-check with the OS.** Verify the port and socket using the appropriate OS tools. Confirm the `datadir` path exists and the service account has access permissions. Do not move or edit data files in this exercise.

**Expected outcome:** you can explain whether the client is connecting over TCP or a socket, which address/port the server is listening on, which configuration file supplies the options, and where the instance's data resides.

## 8. Common Errors and Fault Isolation

| Symptom | Possible Cause | Investigation Direction |
|---|---|---|
| Client reports it cannot connect to `127.0.0.1:3306` | Service stopped, different port, wrong bind address, `skip-networking`, or firewall | Check the service, `@@port`, `@@bind_address`, `@@skip_networking`, and TCP listening state |
| Client reports socket not found or cannot connect | Client uses wrong path, socket not yet created, or directory/file permissions mismatch | Check `@@socket`, inspect `ss -lxnp`, permissions, and the error log |
| `Address already in use` on startup | Another process already holds the port or socket | Identify the listening process; assign dedicated resources to the instance or properly stop the conflicting service |
| `Access denied` | The connection reached MySQL, but authentication or account privileges do not match | Check user, allowed host, authentication method, and grants; do not change the port to fix a privilege error |
| MySQL fails to start after editing config | Misspelled option, wrong group, nonexistent path, wrong permissions, or conflicting settings | Read the error log, verify loaded files, and restore the previous config if needed |
| MySQL cannot read data in the new datadir | Wrong owner/permissions, OS security policy, or data was not transferred properly | Check the service account, directory permissions, SELinux/AppArmor, and the backup/restore process |

Classify errors by layer: routing or firewall errors occur before reaching the server; port/socket errors are connection-path issues; `Access denied` is an authentication or authorization issue after reaching MySQL; datadir errors typically surface at startup or when accessing data files.

## 9. Safe Operational Principles

- Restrict `bind-address` to required interfaces; open the firewall only to trusted sources and ports actually in use.
- Use dedicated MySQL accounts for applications with least privilege; do not use administrative accounts for routine connections.
- Never write plaintext passwords in configuration files or command lines. Protect configuration files and backups as they may contain sensitive information.
- Ensure only the MySQL service account and administrators are allowed to access the data directory.
- For multiple instances, allocate separate `datadir`, TCP port, socket, and PID file per instance.
- Before changing data paths or application connection settings, prepare a rollback plan and re-verify application connectivity after applying changes.

Understanding configuration files, ports, sockets, and `datadir` helps you determine precisely where a MySQL instance is running, which path applications use to connect, and where data is stored. This is the foundation for practicing queries, indexes, transactions, access control, backups, and troubleshooting in a controlled MySQL environment.
