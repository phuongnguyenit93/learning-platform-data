# Initializing the Data Directory and Initial Administrative Accounts

The data directory is where MySQL stores the server's persistent data: the data dictionary, system tables, InnoDB data, redo logs, and status files required for startup. Properly initializing this directory lays the foundation for a new MySQL instance. Afterward, you need to set up an administrative account with explicit credentials and restrict where it can log in from.

This practical lesson belongs to the `DATABASE_MYSQL` module, in the Practice Environment chapter. Preparing the instance and administrative accounts establishes the foundation for practicing table design, data types, keys, SQL queries, indexes, transactions, and concurrency control; subsequent operational lessons will use this environment to read execution plans, optimize queries, manage privileges, and perform backups. The lesson uses MySQL 8.0/8.4 on Linux as the primary example. Service names, configuration paths, error log locations, and `root` authentication methods may vary depending on the Linux distribution or installation method. Always verify your actual configuration before running commands. Steps for a Windows machine are noted in a separate section.

## Objectives

After this lesson, you will be able to:

- Identify the data directory and the operating system account used by MySQL Server.
- Prepare a new data directory with appropriate access permissions.
- Initialize the data directory using `mysqld --initialize` and locate the temporary `root` password.
- Change the initial credentials, create a dedicated administrative account, and verify granted privileges.
- Recognize common errors during initialization or login.

## 1. Understanding the Data Directory Before Initialization

The data directory (typically configured via the `datadir` option) holds the internal data of a MySQL instance. Common components include:

| Component | Role |
|---|---|
| `mysql/` | System tables storing accounts, privileges, and administrative metadata |
| `performance_schema/` | Observability data on server activity and performance |
| `sys/` | Helper views for reading diagnostic data from the Performance Schema |
| InnoDB files | Tablespaces, redo logs, undo logs, and InnoDB stored data |
| `auto.cnf` | The instance's server UUID identifier |
| Error log file | Startup and error information; exact location depends on `log_error` |

Not all components reside inside the data directory in every configuration. For instance, the error log can be written to a separate path. The running `datadir` value is the authoritative source for determining the actual data directory.

When you invoke `mysqld --initialize`, MySQL creates the initial system structures and the local `root` account. With `--initialize`, the server generates a random temporary password for `root` and writes that password to the error log. The account typically requires changing its password upon first login. The `--initialize-insecure` option creates a `root` account with no password; only consider it in an isolated lab environment and set a password immediately.

**Important prerequisite:** the data directory used for initialization must be new and empty. Do not run `--initialize` on a directory that already contains an instance's data. If MySQL was installed from an OS package, the installer may have already initialized `/var/lib/mysql`; do not re-initialize that directory.

## 2. Checking Before You Begin

First, confirm the version and locations of the binaries:

```bash
mysqld --version
mysql --version
```

Check the server configuration. On Debian/Ubuntu, configuration is typically loaded from `/etc/mysql/my.cnf` along with included files under `/etc/mysql/`. On many RHEL-compatible systems, the main file is typically `/etc/my.cnf`. Do not assume every machine uses the same path.

If the server is running, log in using the existing administrative method and inspect:

```sql
SHOW VARIABLES LIKE 'datadir';
SHOW VARIABLES LIKE 'log_error';
SHOW VARIABLES LIKE 'socket';
SELECT VERSION();
```

If this machine was freshly installed via a package manager, check the service and error log to see whether the installation process already created the data directory. On Debian/Ubuntu, the service is typically named `mysql`; on RHEL-compatible systems, the service is typically named `mysqld`:

```bash
sudo systemctl status mysql
# Or:
sudo systemctl status mysqld
```

Only proceed with the manual initialization procedure once you have clearly verified that this is a new instance and the target data directory contains no data that needs to be preserved. If the directory already contains data, stop, identify the instance that owns it, and plan an appropriate backup/migration.

## 3. Preparing the Data Directory on Linux

The example below creates a dedicated directory `/srv/mysql/data`. You can use `/var/lib/mysql` if that is the path prescribed by the package and system configuration. Do not change `datadir` merely by creating a new directory; the server configuration and OS permissions must both point to the same location.

### 3.1. Stopping the Service if Configuration Needs Changes

If the instance is running and you are about to change `datadir`, stop the correct service first. Choose the service name matching your OS:

```bash
sudo systemctl stop mysql
# Or:
sudo systemctl stop mysqld
```

Do not stop a server that is serving users just to follow a lab example. In an environment with live data, changing the data directory requires a dedicated maintenance and backup plan.

### 3.2. Creating the Directory and Setting Permissions

On many Linux installations, the MySQL process runs under the OS account `mysql`. Verify that this account exists, then create the directory with permissions allowing access only to the required owner and group:

```bash
id mysql
sudo install -d -o root -g root -m 755 /srv/mysql
sudo install -d -o mysql -g mysql -m 750 /srv/mysql/data
```

`mysql:mysql` sets the owner and group for the data directory; permission `750` allows the service account to read, write, and traverse the directory while denying access to other users. Never set permission `777` to fix a permission error, as doing so exposes database files to every account on the machine.

If the installation uses a different service account, replace `mysql` with the actual account. Parent directories must also grant the MySQL process traversal permission (`execute` on the directory), even though the process does not need write permission on every parent directory.

### 3.3. Configuring `datadir`

Add or update the corresponding options in the `[mysqld]` section of the configuration file that the service actually loads. For example:

```ini
[mysqld]
user=mysql
datadir=/srv/mysql/data
```

Keep existing settings for `socket`, `pid-file`, `log_error`, `basedir`, and other options if they are still valid. Do not replace the entire configuration file with this short snippet. If the configuration specifies the socket or error log in another directory, ensure that directory exists and the service has appropriate permissions.

On systems with SELinux or AppArmor, standard Unix permissions alone may not be enough. Security policies can block `mysqld` from accessing a custom path. Configure SELinux labels or AppArmor profiles according to your distribution's policy, then check audit logs if the server continues reporting `Permission denied`.

## 4. Initializing a New Instance

Before running the command, re-verify three points: the service is not running against the target data directory, the target directory is empty, and `mysqld` is reading the exact configuration file containing the `datadir` you just set.

On Linux, for example with the main configuration `/etc/mysql/my.cnf`:

```bash
sudo mysqld --defaults-file=/etc/mysql/my.cnf --user=mysql --initialize
```

If the machine uses `/etc/my.cnf`, substitute the corresponding path. `--defaults-file` must appear immediately after the program name so MySQL loads the specified configuration. The `--user=mysql` option instructs the process to use the `mysql` service account when working with the files.

When finished, look for the line announcing the temporary `root` password in the error log. The log path is determined by `log_error`; if not explicitly configured, the default location may be inside the data directory. With a systemd service, service startup logs can also be viewed via:

```bash
sudo journalctl -u mysql -n 100 --no-pager
# Or:
sudo journalctl -u mysqld -n 100 --no-pager
```

The `journalctl` command is useful for service logs; if you ran `mysqld --initialize` directly, check the exact error log specified in the configuration. Store the temporary password in a secure secrets manager. Never put real passwords into documentation, source code, shell history, or screenshots.

After initialization succeeds, start the service:

```bash
sudo systemctl start mysql
# Or:
sudo systemctl start mysqld
```

Check the service status before logging in. If the service fails to start, read the error log and resolve the cause first; do not blindly repeat `--initialize` on a partially initialized directory.

### 4.1. Package Manager Installations

Some MySQL packages distributed by the operating system automatically create the data directory and administrative account during installation. On Ubuntu, for example, the `root` account may be configured to authenticate via a Unix socket. In that case, the initial login method may be:

```bash
sudo mysql
```

If this works, check `datadir` and the current authentication method before modifying accounts. Do not re-run `mysqld --initialize` on a data directory created by the package. Use the administrative workflow provided by the distribution or configure accounts according to system policy.

## 5. Setting Up the Initial `root` Account

For an instance created with `--initialize`, log in using the temporary password:

```bash
mysql -u root -p
```

Enter the password retrieved from the error log when prompted. Then change the password immediately in the MySQL client:

```sql
ALTER USER 'root'@'localhost'
  IDENTIFIED BY 'ReplaceWithStrongUniquePassword';
```

Replace the placeholder string with a strong password generated and stored in a password manager. Do not copy the example password verbatim into a real environment. If the server's authentication policy has specific requirements, follow that policy. On package installations using Unix socket authentication, do not arbitrarily switch the authentication plugin just to make this password example work.

Verify the account and login session:

```sql
SELECT CURRENT_USER();
SELECT user, host, plugin, account_locked, password_expired
FROM mysql.user
WHERE user = 'root';
```

`CURRENT_USER()` reports the MySQL account actually used for privilege checks. The `host` column confirms that the `root` account is restricted to `localhost`; `plugin` shows the active authentication method. Avoid creating or widening a `root` account for host `%`.

## 6. Creating Dedicated Administrative Accounts

In operations, you should use a named administrative account for day-to-day work. The `root` account can be reserved as a bootstrap or recovery account when needed. Separating accounts makes auditing activity and revoking privileges easier.

### 6.1. Creating a DBA Restricted to Localhost Login

The following example creates `dba_admin` matching only local connections:

```sql
CREATE USER 'dba_admin'@'localhost'
  IDENTIFIED BY 'ReplaceWithDedicatedDbaPassword';

GRANT ALL PRIVILEGES ON *.*
  TO 'dba_admin'@'localhost'
  WITH GRANT OPTION;
```

Privileges on `*.*` are server-wide; `WITH GRANT OPTION` allows the account to delegate privileges it holds. This is a very powerful account—create it only for trusted DBAs in environments requiring full instance administration. If a user only administers a single schema, grant privileges on `schema_name.*` instead of the entire server.

Example of an account restricted to operating on a lab schema:

```sql
CREATE USER 'lab_operator'@'localhost'
  IDENTIFIED BY 'ReplaceWithDedicatedLabPassword';

GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, ALTER, INDEX, DROP
  ON lab_db.*
  TO 'lab_operator'@'localhost';
```

Application accounts should likewise be granted only the exact privileges the application needs on its schema. Do not use `root` or a server-wide DBA account as an application's routine connection account.

### 6.2. Verifying Privileges

Inspect the granted privileges:

```sql
SHOW GRANTS FOR 'dba_admin'@'localhost';
SHOW GRANTS FOR 'lab_operator'@'localhost';
```

Try logging in with the new account in another terminal:

```bash
mysql -u dba_admin -p
```

In the new session, verify identity and access:

```sql
SELECT CURRENT_USER();
SHOW DATABASES;
```

If you only need to verify an application account, test an allowed query on the application's schema and confirm that out-of-scope operations are denied. `CREATE USER`, `ALTER USER`, and `GRANT` take effect immediately; you do not need to run `FLUSH PRIVILEGES` after these administrative statements.

### 6.3. If Remote Administration Is Needed

Only enable remote administration when there is a clear operational requirement. Create an account bound to the specific IP address or hostname of the admin machine, enable TLS, restrict the firewall, and configure `bind-address` appropriately. Example account declaration:

```sql
CREATE USER 'dba_remote'@'10.20.30.15'
  IDENTIFIED BY 'DedicatedPasswordForAdminHost'
  REQUIRE SSL;
```

Then grant the exact required set of privileges to this account. The address `10.20.30.15` is only an example; replace it with the actual permitted address. Do not use host `%` to bypass identifying the connection source, and never expose the MySQL port to the Internet without appropriate access controls.

## 7. Notes for Windows

For a MySQL Server installation on Windows, use Command Prompt or PowerShell with appropriate privileges. Identify the exact `my.ini`, installation directory, and `datadir` before initializing. Example command for a new, empty data directory:

```powershell
& 'C:\Program Files\MySQL\MySQL Server 8.4\bin\mysqld.exe' `
  --defaults-file='C:\ProgramData\MySQL\MySQL Server 8.4\my.ini' `
  --initialize --console
```

`--console` displays initialization messages and the temporary password in the console window. The paths above are only examples; use the exact paths from your machine's MySQL Installer/Configurator. Run the command under an account with write permission to the data directory. Afterward, start the Windows service configured for the instance and log in with the MySQL client to change the `root` password, create the DBA account, and verify privileges as shown above.

## 8. Troubleshooting Common Issues

| Symptom | Possible Cause | How to Check and Resolve |
|---|---|---|
| `--initialize` reports the data directory is not empty | The directory already has data or a previous run created partial files | Verify the exact instance and directory contents. Do not delete data reflexively; only use a new directory after confirming there is no data to keep. |
| `Permission denied` during initialization or startup | Wrong owner/group, missing traversal permission on parent directories, or blocked by SELinux/AppArmor | Check `id mysql`, permissions on each directory, the error log, and audit logs; fix permissions/policies for the exact path. |
| Temporary password not found | Looking at the wrong error log or `log_error` points elsewhere | Check `SHOW VARIABLES LIKE 'log_error'` if the server is already running; otherwise check the configuration used during initialization and the log from that run. |
| Service fails to start after changing `datadir` | The service loads a different config file, wrong path, insufficient permissions, or security policy blocks access | Check the service unit, loaded config file, and error log; confirm `datadir` in the config matches the initialized directory. |
| `Access denied for user 'root'@'localhost'` | Temporary password mistyped, account uses a different plugin, or connecting to a different instance | Check socket/port and exact instance; check the authentication plugin via a still-accessible admin session. Do not create another `root` account to bypass the error. |
| `Can't connect to local MySQL server through socket` | Service is not running or client uses a different socket path than the server | Check service status, `socket` in the config, and the error log; specify the correct socket if needed. |

## 9. Practice Exercise and Completion Criteria

Perform on a lab machine or an instance dedicated to this lesson:

1. Record the current MySQL version, service name, configuration file, `datadir`, and `log_error`.
2. Create a new, empty data directory; grant permissions to the proper service account and update `datadir` in the configuration.
3. Initialize using `mysqld --initialize`. Locate the temporary password in the error log and log in with the `root` account.
4. Change the `root` password, create `dba_admin` restricted to logging in from `localhost`, and inspect `SHOW GRANTS`.
5. Also create `lab_operator` with limited privileges on a test schema. Test both permitted operations and denied operations.
6. Cross-check `CURRENT_USER()`, `@@datadir`, `@@socket`, and `VERSION()` to confirm you are working against the exact intended instance.

You have completed this lesson when the service starts reliably, MySQL uses the chosen data directory, administrative accounts can log in, granted privileges match the intended scope, and there is no need to use the `root` account for application connections.

## 10. Principles to Remember

- Initializing the data directory is a one-time operation for a new instance; never re-run it on a directory containing existing data.
- `--initialize` generates a temporary `root` password; change the password immediately and protect the error log since it may contain initial credentials.
- Directory ownership and permissions must match the account running MySQL; SELinux/AppArmor must also allow access.
- Keep administrative accounts restricted by host, use separate accounts for separate purposes, and grant privileges according to the principle of least privilege.
- Back up before any change that could affect the data directory. Never move, delete, or edit data files directly while MySQL is running.
