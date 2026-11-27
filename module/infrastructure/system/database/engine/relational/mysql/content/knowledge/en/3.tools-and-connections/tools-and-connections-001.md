# Using mysql client, MySQL Shell, and MySQL Workbench

When working with MySQL, you can send SQL statements from a terminal, run administration scripts using a programmable shell, or interact visually through a graphical interface. Three common tools are **mysql client**, **MySQL Shell**, and **MySQL Workbench**. They all connect to MySQL Server, but serve different workflows.

In a sales system, for example, a developer might use `mysql` to run migration files in a development environment, use MySQL Workbench to inspect table structures and query plans, and use MySQL Shell to automate checks or dump data. Knowing how to choose the right tool, establish a secure connection, and verify the target server helps reduce errors during both database development and operations.

## 1. Distinguishing the Three Tools

| Tool | How It Works | Best Suited For | Key Considerations |
|---|---|---|---|
| `mysql` client | Command-line interface for sending SQL over the classic MySQL protocol | Running SQL statements, `.sql` files, quick checks, and working in terminals or scripts | Lightweight, easy to combine with OS tools; not a dedicated programmable administration environment |
| MySQL Shell (`mysqlsh`) | Interactive shell with SQL, JavaScript, and Python modes; supports AdminAPI and import/export utilities | Automation, topology administration, dumping/loading data, and SQL operations | Can connect using the classic protocol or X Protocol; requires selecting the right mode and protocol |
| MySQL Workbench | Graphical application with an SQL Editor, modeling, and administration tools | Exploring schemas, writing SQL, viewing results, visualizing execution plans, and managing objects | Convenient for visual operations; requires verifying version compatibility with the server |

These three tools do not replace MySQL Server. They are client-side programs that require connection details and an account with appropriate privileges. Statements execute with the privileges of the connected account, so opening Workbench with an administrative account can cause changes just as dangerous as running the same statements in a terminal.

## 2. Preparing Connection Information

Before opening a tool, clearly identify the server and environment you need to access. A connection configuration typically includes:

- **Host:** the IP address or DNS name of the machine running MySQL Server, such as `127.0.0.1` or `db-dev.example.net`.
- **Port:** the TCP port. MySQL classic protocol typically uses `3306`; MySQL X Protocol typically uses `33060` by default.
- **Username and password:** the MySQL account provisioned for the specific task.
- **Database/schema:** the default schema to work in, such as `shop`.
- **TLS/SSL:** the encryption mode and CA certificate required when connecting over a network.
- **Network path:** whether a VPN, firewall, SSH tunnel, or internal network allows the client to reach the host and port.

Not every environment uses default ports. Administrators may change the port, disable X Protocol, or place MySQL behind a proxy. Obtain connection parameters from the environment configuration or the administrator rather than guessing.

### 2.1. Distinguishing localhost and Remote Connections

`localhost` can cause some clients to use a Unix socket or named pipe depending on the operating system and configuration. `127.0.0.1` typically forces a TCP loopback connection. On a development machine, these two approaches can result in different authentication methods or connection configurations.

MySQL accounts are also bound to the host part of the account identity. For example, `'app_user'@'localhost'` and `'app_user'@'10.20.%'` are two distinct accounts. Therefore, being able to log in locally on the server does not necessarily mean the application can log in from another machine.

### 2.2. Protecting Credentials

Do not write passwords directly after the `-p` option, do not put passwords into scripts committed to Git, and do not share configuration files containing secrets. With the mysql client, use `-p` so the client prompts for the password interactively. With MySQL Shell, you can let the shell prompt for the password when opening a connection.

When connecting over a network, prefer TLS and verify the server certificate. `VERIFY_IDENTITY` mode checks both the certificate chain and the server identity; you must provide a trusted CA and use a hostname matching the certificate. `REQUIRED` enforces encryption but does not verify server identity to the same extent. Do not disable TLS just to make a connection work.

Do not expose the MySQL port directly to the Internet without appropriate security controls. Prefer a private network, VPN, source-restricted firewall rules, or an SSH tunnel; grant access only from required hosts and use accounts with least privilege.

## 3. Using mysql client

`mysql` is the traditional command-line client for connecting to MySQL Server over the classic protocol. It is suitable for running quick SQL queries, executing script files, checking status, or integrating database operations into terminal workflows.

### 3.1. Connecting to MySQL Server

Example connecting to a development server over TCP, selecting the `shop` schema, and enabling TLS verification:

```bash
mysql \
  --host=db-dev.example.net \
  --port=3306 \
  --user=app_user \
  --password \
  --ssl-mode=VERIFY_IDENTITY \
  --ssl-ca=/etc/mysql/certs/ca.pem \
  --database=shop
```

The client will prompt for the password. On Windows, you can write the command on a single line or use the line-continuation character supported by your shell; the `\` character in the example is for Unix-style shells. The CA path must also exist on the machine running the client.

To connect locally over TCP:

```bash
mysql -h 127.0.0.1 -P 3306 -u root -p
```

Use the `root` account only in environments and operations that require administrative privileges. When working with applications, use a dedicated account such as `app_user` with privileges scoped to the appropriate schema.

### 3.2. Common Commands in an Interactive Session

Once connected, you can run SQL directly:

```sql
SELECT VERSION();
SELECT CURRENT_USER(), USER();
SHOW DATABASES;
USE shop;
SHOW TABLES;
SHOW CREATE TABLE orders;
```

Some commonly used mysql client control commands:

| Command | Effect |
|---|---|
| `status` or `\s` | View connection status, server info, default schema, and session details |
| `\c` | Clear the current input statement |
| `\q` or `exit` | Exit the client |
| `source path/to/file.sql` or `\. path/to/file.sql` | Read and execute an SQL file in the current session |
| `help` or `\h` | View client help |

Note that `SHOW DATABASES`, `SHOW TABLES`, and metadata queries only display objects that the account has privileges to see. If you do not see a schema or table, check privileges before concluding that the object does not exist.

### 3.3. Running SQL Files

You can execute a migration file in an interactive session:

```sql
USE shop;
source ./migrations/2026_11_add_order_index.sql;
```

Or launch the client and pass the file contents via standard input:

```bash
mysql -h 127.0.0.1 -P 3306 -u deploy_user -p shop < schema.sql
```

The second approach is well suited for automated scripts and deployment pipelines. Check the process exit code, error logs, and schema state after execution. Do not assume an entire file will automatically roll back if one statement fails; transaction behavior depends on statement types, the storage engine, and how the script is written.

For large files, run them in an environment with a stable connection, monitor execution time and log size, and prepare a recovery plan. Before running a migration in production, verify whether the file can be re-run safely and whether it acquires table locks or makes structural changes that impact the running application.

### 3.4. Running One-Off Queries and Saving Output

The `--execute` option sends a single SQL statement and exits:

```bash
mysql -h 127.0.0.1 -u report_user -p \
  --database=shop \
  --execute="SELECT status, COUNT(*) FROM orders GROUP BY status;"
```

To produce batch-formatted output convenient for scripts, you can use `--batch` and `--raw`:

```bash
mysql -h 127.0.0.1 -u report_user -p \
  --database=shop --batch --raw \
  --execute="SELECT id, status FROM orders LIMIT 10;" > orders.tsv
```

Output files must be handled as data that may contain sensitive information. Do not write customer query results or production data into public directories, CI logs, or source repositories.

## 4. Using MySQL Shell

MySQL Shell (`mysqlsh`) is a more modern interactive and automation environment. Beyond sending SQL, the shell can run JavaScript or Python, provides AdminAPI for administering certain MySQL topologies, and includes data dump/load utilities.

### 4.1. Connecting with Classic Protocol or X Protocol

To connect via the classic protocol on port `3306`, specify `--mysql` and enter SQL mode:

```bash
mysqlsh --mysql \
  --uri app_admin@db-dev.example.net:3306/shop \
  --sql
```

To use X Protocol, the server must have the X Plugin enabled and the corresponding port open, typically `33060`:

```bash
mysqlsh --mysqlx \
  --uri app_admin@db-dev.example.net:33060/shop \
  --sql
```

The shell will prompt for a password when needed. Choose the protocol that matches the server's port and configuration; you cannot switch to X Protocol simply by changing the client if the server does not have the X Plugin enabled. Workbench and the traditional mysql client typically use the classic protocol.

### 4.2. Switching Between SQL, JavaScript, and Python Modes

MySQL Shell has three main modes:

- **SQL mode:** sends SQL statements to the server.
- **JavaScript mode:** writes JavaScript scripts, accesses the session, and calls administration APIs.
- **Python mode:** writes Python scripts to automate tasks.

Within a shell session, use the following commands to switch modes:

```text
\sql
\js
\py
\status
```

Example in SQL mode:

```sql
SELECT VERSION();
SHOW DATABASES;
```

Example in JavaScript mode, using the active session to run a query:

```javascript
var result = session.runSql("SELECT COUNT(*) AS total FROM shop.orders");
result.fetchAll();
```

In Python mode, the corresponding API follows Python naming conventions:

```python
result = session.run_sql("SELECT COUNT(*) AS total FROM shop.orders")
result.fetch_all()
```

Do not mix pure SQL syntax with JavaScript or Python syntax when the shell is in a different mode. If a command appears unrecognized, check the current mode with `\status`.

### 4.3. AdminAPI for Topology Administration

MySQL Shell provides AdminAPI to inspect and manage configurations such as InnoDB Cluster and ReplicaSet. In JavaScript mode, a connected session can retrieve the status of an existing cluster:

```javascript
var cluster = dba.getCluster();
cluster.status();
```

AdminAPI also provides operations to check instance configuration, create a cluster, add instances, and modify topology. These are administrative operations that can alter server state. Before running them, verify MySQL Shell/server versions, configuration prerequisites, account privileges, backups, replication status, and the failover/switchover plan. Do not run cluster creation or topology-changing commands in production just to experiment.

### 4.4. Dumping and Loading Data

MySQL Shell provides dump/load utilities that support splitting data into chunks and running in parallel. Example in JavaScript mode:

```javascript
util.dumpSchemas(["shop"], "/backup/shop-dump", {threads: 4});
```

Loading the dump into a target server:

```javascript
util.loadDump("/backup/shop-dump", {threads: 4});
```

The path in the example is a directory on the machine running MySQL Shell. Ensure the target directory has read/write permissions, sufficient disk space, and will not overwrite unexpected data. Dump/load operations may require specific MySQL privileges and options compatible with the server version. Read command output, inspect warnings, and verify the data after loading.

A MySQL Shell dump is a form of logical backup. It does not by itself replace all physical backup requirements, binary log retention for point-in-time recovery, backup encryption, off-site/independent storage, and recovery drills. A backup is only reliable once the restore procedure has been tested.

## 5. Using MySQL Workbench

MySQL Workbench is a graphical application that integrates query execution, schema design, and server administration tools. It is useful when you need to inspect data structures or work across many tables where remembering names and relationships from a terminal becomes inconvenient.

### 5.1. Creating a Connection

Basic workflow:

1. Open MySQL Workbench and choose to create a new connection in the MySQL Connections area.
2. Give it a clearly recognizable name, such as `Local Dev` or `Staging Read Only`.
3. Choose the connection method: TCP/IP, TCP/IP over SSH, or another method supported by the environment.
4. Enter the hostname, port, username, and TLS configuration if required.
5. Click **Test Connection** to verify, then save and open the connection.

Do not name a connection simply `MySQL` if you regularly work across multiple environments. Names like `DEV`, `STAGING`, and `PRODUCTION READ ONLY` help reduce the risk of running statements in the wrong environment, though you should still verify the hostname and schema in every session.

Workbench can store passwords using the operating system's credential store. Store credentials only on protected personal devices; do not share connection profiles containing sensitive information with others.

### 5.2. SQL Editor and Schema Management

After opening a connection, the SQL Editor allows you to:

- Write and execute SQL statements, execute a selected portion of statements, or run an entire script.
- View results in a grid, sort, and filter returned data.
- Browse schemas, tables, views, stored procedures, and triggers in the Navigator.
- Inspect table definitions, primary keys, foreign keys, indexes, and data types.
- Create or modify objects through visual editors.

When modifying structures through the GUI, review the SQL that Workbench intends to execute before applying it. Changing a data type or key may require a table rebuild, hold metadata locks, or disrupt active applications.

### 5.3. Viewing Execution Plans

In the SQL Editor, Workbench can display a visual execution plan for a query. You can start with:

```sql
EXPLAIN
SELECT id, status, total_amount
FROM shop.orders
WHERE customer_id = 120
ORDER BY created_at DESC
LIMIT 20;
```

The plan shows how MySQL intends to access tables, which indexes may be selected, join order, and estimated row counts. On MySQL versions that support `EXPLAIN ANALYZE` (MySQL 8.0.18 and later), the statement executes the query and reports actual row counts and timings per iterator:

```sql
EXPLAIN ANALYZE
SELECT id, status, total_amount
FROM shop.orders
WHERE customer_id = 120
ORDER BY created_at DESC
LIMIT 20;
```

`EXPLAIN ANALYZE` actually runs the query. Limit the scope and assess the impact before using it on heavy queries in production. The visual interface does not replace reading the estimates, actual row counts, timings, and filter conditions in the plan.

### 5.4. Administration Tools and Import/Export

Workbench includes administration sections to inspect server status, users and privileges, configuration variables, active sessions, and various performance metrics. The exact names and capabilities of each screen depend on the Workbench and MySQL Server versions.

The Data Export and Data Import/Restore features support exporting schemas/data to SQL files and reloading them from dump files. Before importing, confirm the correct connection, target schema, disk space, and compatibility. Importing into a schema actively used by an application can overwrite or alter existing data.

Workbench also includes an EER modeling tool to diagram tables, relationships, and generate SQL. Visual models are useful during design, but the actual schema should still be verified using `SHOW CREATE TABLE` and managed migrations in the development workflow.

## 6. Choosing a Tool by Task

| Task | Tool to Start With | Reason |
|---|---|---|
| Running a quick `SELECT` or `SHOW` | `mysql` client or SQL Editor | Fast startup, immediate results |
| Running migration files in CI/CD | `mysql` client | Easy to pipe files via standard input and check exit codes |
| Writing check scripts across multiple servers | MySQL Shell | Provides JavaScript/Python and a session API |
| Checking an InnoDB Cluster or ReplicaSet | MySQL Shell | Provides dedicated AdminAPI |
| Dumping/loading large schemas in parallel | MySQL Shell | Built-in parallel dump/load utilities |
| Exploring relationships across tables | MySQL Workbench | Navigator and EER Diagram aid visual inspection |
| Viewing query results and graphical plans | MySQL Workbench | SQL Editor integrates results and EXPLAIN |
| Running commands from a headless server | `mysql` client or MySQL Shell | Operates via terminal and can be automated |

No single tool is best for every task. A development workflow might use Workbench to explore schemas, store migrations as SQL files in Git, run migrations with the mysql client in CI/CD, and use MySQL Shell for scheduled checks or backups.

## 7. Sample Workflow

Suppose you need to inspect an orders table, diagnose a slow query, and deploy an index in a development environment.

### Step 1: Confirm the Target Server

Connect with your preferred tool and verify the server identity:

```sql
SELECT
    @@hostname AS server_host,
    @@port AS server_port,
    DATABASE() AS current_schema,
    CURRENT_USER() AS authenticated_account,
    VERSION() AS mysql_version;
```

If the output does not match the expected environment, stop and reconnect. Do not rely solely on tab colors or profile names to identify production.

### Step 2: Explore Table Structure

```sql
SHOW CREATE TABLE shop.orders;
SHOW INDEX FROM shop.orders;
```

Review data types, keys, constraints, and existing indexes before proposing changes. Do not create duplicate or near-duplicate indexes without understanding the purpose of the existing ones.

### Step 3: Measure and Inspect the Query Plan

Run the query with realistic conditions, inspect the slow query log or Performance Schema statistics if you have privileges, and then use `EXPLAIN`. Use `EXPLAIN ANALYZE` only when the version supports it and running the query is acceptable.

### Step 4: Test the Change in Development

Write the migration into an SQL file, review the statement, estimate its impact on the data, and test it against a representative dataset. If running via terminal:

```bash
mysql -h 127.0.0.1 -u deploy_user -p shop < migrations/add_orders_customer_created_index.sql
```

### Step 5: Verify After the Change

Check `SHOW INDEX`, re-run the query, and compare the execution plan, response time, and write overhead. An index can speed up read queries while increasing `INSERT`, `UPDATE`, and storage costs. Evaluate both sides before deploying.

## 8. Troubleshooting Common Connection Errors

| Message or Symptom | Possible Cause | How to Check |
|---|---|---|
| `ERROR 2002` or cannot connect to socket | Server is not running, wrong socket path, or client is using a different connection method than expected | Check the MySQL service, socket path, and try TCP loopback if appropriate |
| `ERROR 2003` / connection refused or timeout | Wrong host/port, blocked by firewall, server not listening on TCP, or unreachable network path | Check hostname, port, server status, firewall, VPN, and bind address |
| `ERROR 1045: Access denied` | Wrong password, wrong host part of account, or missing compatible authentication method | Verify username, source host, credentials, and account privileges with the administrator |
| `ERROR 1049: Unknown database` | Schema does not exist or name was mistyped | Check the schema name and visibility privileges |
| TLS certificate error | Untrusted CA, hostname mismatch with certificate, or expired certificate | Check the CA, SAN/hostname, certificate expiration, and server TLS configuration |
| Connection dropped mid-session | Unstable network, timeout, server restart, or long-running query | Check server logs, network, timeouts, and query state |
| MySQL Shell cannot connect via X Protocol | X Plugin is not enabled or wrong port is used | Use the classic protocol if appropriate or ask the administrator to verify X Plugin and port |

When troubleshooting errors, isolate the problem layer by layer: can the client run, does the hostname resolve, does TCP reach the port, does the server accept the connection, does TLS validate, and does the account have privileges? This sequential check prevents modifying server privileges or settings when the fault is actually in the network.

## 9. Safe Habits When Using MySQL Tools

- **Verify the environment before writing:** confirm host, port, schema, and account before `UPDATE`, `DELETE`, `ALTER`, or migrations.
- **Use role-appropriate accounts:** reporting accounts only need read privileges; application accounts only need privileges on the business schema; administrative accounts should only be used when truly necessary.
- **Do not expose secrets:** keep passwords out of command history, scripts, screenshots, logs, and shared config files.
- **Use TLS over networks:** verify server identity with a valid CA and hostname.
- **Review SQL before applying:** especially for structural changes, data deletions, import/export, and AdminAPI.
- **Keep migrations in version control:** document purpose, execution order, idempotency/re-run conditions, and rollback/recovery steps.
- **Back up and test restores:** a successful export does not prove the system can be recovered to the required point in time and state.
- **Do not test destructive operations on production:** use a development environment or an appropriate data copy.

## 10. Pre-Operation Checklist

- Am I connected to the right host, port, and schema?
- Am I using the classic protocol or X Protocol, and does the server support it?
- Are the client, MySQL Shell, Workbench, and server versions compatible?
- Is TLS enabled and is the certificate verified?
- Does the account have least-privilege permissions appropriate for the task?
- Is the command I am about to run read-only, or can it modify data/structure?
- If running a migration, import, or dump, have I verified the files, directories, disk space, and recovery plan?
- Have I verified the outcome afterward and saved necessary logs?

## Conclusion

The `mysql` client is well suited for SQL and command-line scripts; MySQL Shell adds programmability, AdminAPI, and dump/load utilities; MySQL Workbench helps explore schemas, write queries, and administer servers visually. Whichever tool you use, confirm the target server, choose the appropriate protocol, protect credentials, apply least privilege, and check impact before modifying data. These habits keep MySQL design, querying, tuning, and operations safe, repeatable, and auditable.
