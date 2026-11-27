# LOCAL INFILE, FILE Privilege, secure_file_priv, and the File Access Surface

In the **DATABASE_MYSQL** module, the **Security** section must treat file import and export operations as part of the database server's attack surface. A CSV loading statement can read a file from the application host or from the MySQL server; these two paths carry different privileges, paths, and risks. Confusing them can lead to granting server file-read privileges to an application account or inadvertently allowing an untrusted server to request local files from a client.

This lesson focuses on three mechanisms: **LOCAL INFILE**, the global **FILE** privilege, and the **secure_file_priv** configuration variable. They relate directly to privilege management, input data control, server protection, and secure MySQL operations.

Within the scope of the module, this topic complements mastering table design, data types, keys, SQL queries, indexes, transactions, and concurrency control; it also connects to reading execution plans, query optimization, privilege management, backups, and troubleshooting relational database operations.

## 1. Objectives and the File Access Model

After this lesson, you will be able to:

- Distinguish LOAD DATA INFILE from LOAD DATA LOCAL INFILE by where the file is read.
- Identify when the FILE privilege is required and when it is not.
- Explain the effects of secure_file_priv and local_infile.
- Configure controlled data imports, grant least privilege, and verify results.
- Investigate path, OS permission, and configuration errors related to file operations.

Always answer three questions before writing SQL:

1. Does the file reside on the client machine or on the MySQL server?
2. Which process actually opens the file: the client program or the mysqld process?
3. Which MySQL account and which OS account need permissions for the operation to succeed?

MySQL has two primary file import flows:

| Statement | Where the File Is Read | Who Accesses the Filesystem? | Typical MySQL Privileges |
|---|---|---|---|
| LOAD DATA INFILE | MySQL server | mysqld process | FILE and INSERT on the target table |
| LOAD DATA LOCAL INFILE | Client machine | Client program or driver library | INSERT on the target table; FILE not required |

The keyword LOCAL is the core distinction. With LOCAL, the client opens the file and streams its contents over the MySQL connection; the server does not open that path directly on the client's disk. If the application runs in a container or on an application server, the LOCAL path must exist and be readable in that application runtime environment, not necessarily on an end user's workstation.

## 2. LOAD DATA LOCAL INFILE

### 2.1. How It Works

For example, an application imports orders.csv from the application host into a staging table:

~~~sql
LOAD DATA LOCAL INFILE '/data/inbox/orders.csv'
INTO TABLE stg_orders
CHARACTER SET utf8mb4
FIELDS TERMINATED BY ','
OPTIONALLY ENCLOSED BY '"'
LINES TERMINATED BY '\n'
IGNORE 1 LINES
(order_id, customer_id, amount, created_at);
~~~

In this example:

- The path /data/inbox/orders.csv is resolved on the host running the MySQL client or the application process using the client library.
- The client reads the file and sends data to the server over the connection.
- The server requires the INSERT privilege on stg_orders.
- The FILE privilege is not required for the LOCAL operation.
- secure_file_priv governs server-side file operations, so it does not restrict local file paths opened by the client in a LOCAL flow.

The FIELDS and LINES settings must match the actual file format. The example above assumes a comma-separated CSV with double-quoted fields and LF line endings. If the file originates from Windows, lines may end with CRLF. If fields contain embedded quotes or escape characters, choose ESCAPED BY matching how the file was generated and test with representative sample data before bulk importing.

### 2.2. Conditions for Enabling LOCAL

LOCAL INFILE typically must be permitted on both the server side and the client side:

- On the server, the global variable local_infile must be enabled.
- On the client, the mysql program or driver library must allow LOCAL file loading.
- The MySQL account must have the required privileges on the target table, typically INSERT.

Check the server side:

~~~sql
SHOW GLOBAL VARIABLES LIKE 'local_infile';
~~~

With the MySQL command-line client, support can be enabled at connect time via an option:

~~~bash
mysql --local-infile=1 -u batch_loader -p shop
~~~

Driver library options depend on the driver and version. For instance, MySQL Connector/J has the allowLoadLocalInfile connection property. Check the documentation for the exact driver version deployed and enable the feature only on connections dedicated to data-import tasks.

If the system does not need client-side file imports, keep local_infile disabled on the server and disable the corresponding capability in clients. When enabling it temporarily, bound the duration, accounts, connection sources, and operational procedure; once finished, restore the hardened configuration.

### 2.3. Specific Risks of LOCAL

When LOCAL is enabled, the protocol allows the server to ask the client to send a local file. Therefore, a malicious or compromised MySQL server could attempt to ask the client program to send files readable by the client process. The risk depends on the OS permissions of the account running the application and how the driver constrains LOCAL requests.

Mitigations:

- Only open LOCAL connections to trusted servers; verify server identity and use TLS with proper certificate verification.
- Enable LOCAL only in clients and connections that genuinely need file imports.
- Run the application under an OS account with minimal read permissions; do not run data-import applications with administrative privileges.
- Place input files in a dedicated staging directory with restricted permissions and no secrets, config files, or unrelated sensitive data.
- Never allow users to supply arbitrary file paths. Applications should pick files from an allowed area, construct safe filenames, and validate data sources before importing.
- Use a dedicated MySQL account for import tasks and grant privileges only on the required schema or table.

TLS protects transport and authenticates the server per certificate settings, but it does not turn a malicious server into a trustworthy one. The decision to enable LOCAL must still rest on trust in the connection endpoint.

## 3. Server-Side LOAD DATA INFILE

When the LOCAL keyword is omitted, the mysqld process reads the file on the database server:

~~~sql
LOAD DATA INFILE '/var/lib/mysql-files/orders.csv'
INTO TABLE stg_orders
CHARACTER SET utf8mb4
FIELDS TERMINATED BY ','
OPTIONALLY ENCLOSED BY '"'
LINES TERMINATED BY '\n'
IGNORE 1 LINES
(order_id, customer_id, amount, created_at);
~~~

With this flow:

1. The path must exist on the MySQL server.
2. The OS account running mysqld must have permissions to read the file and traverse parent directories.
3. The MySQL account executing the statement must hold the global FILE privilege.
4. The MySQL account must hold INSERT on the target table.
5. The path must satisfy secure_file_priv restrictions if that variable is configured to limit the directory.

The FILE privilege does not override OS permissions. A MySQL account with FILE still cannot read a file that the mysqld process lacks permission to read. Conversely, OS read permissions are not enough if the MySQL account lacks FILE or the path is blocked by secure_file_priv.

Choose LOAD DATA INFILE when the file has already been securely transferred to the server and operations want the server to read from a controlled staging directory. If the file exists only on the application host, use LOCAL when security policy permits.

## 4. The Global FILE Privilege

### 4.1. What Does FILE Allow?

FILE is a global privilege that allows a MySQL account to perform certain server-side file read or write operations, notably:

- LOAD DATA INFILE: read a server-side file to load into a table.
- SELECT ... INTO OUTFILE: write query results to a file on the server.
- SELECT ... INTO DUMPFILE: write a single result row as raw data to a file.
- LOAD_FILE(): read the contents of a server-side file and return it as a value.

FILE is globally scoped; it cannot be restricted to one table by granting FILE on a schema. Consequently, granting it to ordinary application accounts significantly expands the filesystem access surface reachable through the MySQL process.

Example of exporting data:

~~~sql
SELECT order_id, customer_id, amount
INTO OUTFILE '/var/lib/mysql-files/orders-export.csv'
FIELDS TERMINATED BY ','
OPTIONALLY ENCLOSED BY '"'
LINES TERMINATED BY '\n'
FROM orders
WHERE created_at >= '2026-01-01';
~~~

This statement requires appropriate SELECT privileges on the data and the FILE privilege. The file is created on the server by the mysqld process. MySQL will not overwrite an existing file at the target path; use a fresh filename or a controlled file rotation workflow.

SELECT ... INTO DUMPFILE also writes a server-side file, but writes a single row without field or line delimiters. Exercise particular care when using it to export binary data.

Example of LOAD_FILE():

~~~sql
SELECT LOAD_FILE('/var/lib/mysql-files/notice.txt');
~~~

LOAD_FILE() reads a file only if the FILE privilege, OS read permissions, secure_file_priv restrictions, and relevant size limits are all satisfied. If unreadable, the function may return NULL. Never use it as an arbitrary file-reading mechanism from an application.

### 4.2. Granting and Revoking FILE

Grant FILE only to dedicated operational accounts when a reviewed process requires server-side file operations:

~~~sql
GRANT FILE ON *.* TO 'file_exporter'@'localhost';
~~~

If the export account needs to read the orders table, grant read privileges at the exact scope:

~~~sql
GRANT SELECT ON shop.orders TO 'file_exporter'@'localhost';
~~~

For server-side imports, the account also needs INSERT on the target table:

~~~sql
GRANT INSERT ON shop.stg_orders TO 'file_importer'@'localhost';
GRANT FILE ON *.* TO 'file_importer'@'localhost';
~~~

Revoke FILE when the task no longer requires it:

~~~sql
REVOKE FILE ON *.* FROM 'file_exporter'@'localhost';
~~~

Verify granted privileges:

~~~sql
SHOW GRANTS FOR 'file_exporter'@'localhost';
SHOW GRANTS FOR CURRENT_USER();
~~~

An account using only LOAD DATA LOCAL INFILE usually only needs privileges on the target table; do not grant FILE to that account. Avoid combining data import, data export, and administrative privileges into a single long-lived account.

## 5. secure_file_priv

### 5.1. Meaning and States

secure_file_priv restricts or disables certain server-side file import and export operations. Check its current value with:

~~~sql
SHOW GLOBAL VARIABLES LIKE 'secure_file_priv';
~~~

Common states:

| Value | Meaning |
|---|---|
| A directory path, e.g., /var/lib/mysql-files | Restricts server-side file operations to the configured directory |
| Empty string | No directory restriction applied by this variable; wider file access surface |
| NULL | Disables server-side import and export operations governed by this variable |

Do not choose the empty string merely to make a failing statement work. Configuring a dedicated directory is usually easier to control and audit. Default values vary by platform and packaging, so read the actual server value rather than assuming.

secure_file_priv is read-only at runtime; changing it requires updating MySQL's startup configuration and restarting per operational procedures. Example in the server configuration file:

~~~ini
[mysqld]
secure_file_priv=/var/lib/mysql-files
local_infile=OFF
~~~

This example confines server-side file operations to a dedicated directory and disables server-side LOCAL. If a business workflow needs LOCAL, assess and configure local_infile separately according to approved policy; do not enable it as a quick workaround without reviewing the risks.

### 5.2. secure_file_priv Does Not Replace OS Permissions

Setting secure_file_priv to a directory does not automatically grant mysqld read or write permissions. OS administrators must:

- Create the directory before starting MySQL with that configuration.
- Grant appropriate ownership and access permissions to the account running mysqld.
- Restrict which other users and processes can write to the directory.
- Never place secret files, executables, or unrelated data inside the staging directory.
- Check additional protections such as AppArmor or SELinux if used by the OS.

Untrusted users should not have write permissions on a directory mysqld can read. If they can replace files in the staging directory, they can tamper with imported data or files consumed by export workflows.

### 5.3. Scope of the Variable

secure_file_priv controls server-side file operations such as LOAD DATA INFILE, SELECT ... INTO OUTFILE, SELECT ... INTO DUMPFILE, and LOAD_FILE(). It is not a mechanism that restricts paths opened by the client when using LOAD DATA LOCAL INFILE. Controlling LOCAL requires managing local_infile on the server, client or driver settings, server identity verification, and OS permissions of the client process.

Therefore, a strict secure_file_priv configuration still requires a separate policy for LOCAL. Likewise, disabling LOCAL does not automatically revoke FILE or disable SELECT ... INTO OUTFILE if server-side conditions still permit them.

## 6. Secure Data Import Workflow

A CSV import workflow can be broken into the following steps:

1. **Receive the file:** accept files over a controlled channel, restricting size, format, encoding, and sender.
2. **Stage the file:** use a dedicated directory. If importing with LOCAL, the directory is on the client machine; if using INFILE, the directory is on the MySQL server.
3. **Select the account:** the import account holds only the required INSERT privilege on the staging table. Grant FILE only if using the server-side INFILE flow.
4. **Verify configuration:** check local_infile, secure_file_priv, directory permissions, and readability by the relevant process.
5. **Load into the staging table:** specify CHARACTER SET, field delimiters, enclosure characters, line endings, header skipping, and the column list explicitly.
6. **Validate data:** check row counts, NULL values, data types, duplicate keys, numeric ranges, and conversion warnings.
7. **Promote to main tables:** use controlled statements, check constraints, and record business outcomes.
8. **Clean up:** delete staging files per retention policy, revoke temporary privileges, and disable any features enabled solely for the job.

Example immediate post-load checks:

~~~sql
SHOW WARNINGS;
SELECT ROW_COUNT() AS affected_rows;
~~~

Run SHOW WARNINGS right after LOAD DATA to read warnings from the import; then record ROW_COUNT() to track affected rows. For critical data, compare input row count, successfully loaded row count, and rejected or converted rows. Never treat a statement finishing without an error as sole proof that the data is valid.

A staging table separates data ingestion from core business tables. You can inspect malformed rows, normalize formats, detect duplicate keys, and reconcile totals before writing into main tables. Use InnoDB tables if you need InnoDB transactional guarantees in subsequent processing steps; do not assume every filesystem operation, table, and import step can be rolled back identically.

## 7. Security Selection and Configuration Matrix

| Need | Approach | Key Privileges/Settings | Required Controls |
|---|---|---|---|
| File is on the application host | LOAD DATA LOCAL INFILE | local_infile on server and client; INSERT on table | Connect only to trusted servers, restrict directories and client process permissions |
| File is on the DB server | LOAD DATA INFILE | Global FILE and INSERT on table | secure_file_priv, mysqld read permissions, dedicated staging directory |
| Export query to server file | SELECT ... INTO OUTFILE | Global FILE and SELECT on data | secure_file_priv, mysqld write permissions, control file destination |
| Read server file content in SQL | LOAD_FILE() | Global FILE | Restrict usage, control directory and OS permissions |
| Application has no need for LOCAL | Disable LOCAL | local_infile=OFF and client disallows LOCAL | Review drivers and connection configs |

A baseline configuration generally suited to application systems that do not need to read client files:

- Keep local_infile set to OFF.
- Point secure_file_priv to a dedicated directory if server-side processes must import or export files.
- Do not grant FILE to normal application accounts.
- Use dedicated, short-lived accounts for tasks requiring FILE.
- Restrict OS permissions on directories used by MySQL.
- Log the operator, timestamp, file source, row counts, and import results.

If an organization requires LOCAL, document the business justification, trusted target servers, permitted clients/drivers, allowed directories, and enable/disable schedule. Test the configuration in an equivalent environment before deploying.

## 8. Troubleshooting Common Issues

| Symptom | Possible Cause | Where to Check |
|---|---|---|
| LOCAL rejected or client reports unsupported | local_infile disabled on server or client; driver disallows LOCAL | Check server variable and exact client/driver option |
| LOAD DATA INFILE reports access denied | Missing FILE, missing INSERT, or missing OS permissions | Check SHOW GRANTS and permissions of the account running mysqld |
| Path not found | Path resolved on the wrong machine; wrong path or working directory | Determine whether flow uses LOCAL and check on the matching host |
| secure_file_priv blocks operation | File is outside the permitted directory or variable is NULL | Read variable value and check path; update config per startup workflow |
| Server cannot read/write despite MySQL grants | Directory permissions, file permissions, AppArmor, or SELinux blocking | Inspect OS permissions and security logs |
| Loads data, yet wrong columns or garbled characters | Wrong delimiter, encoding, enclosure character, or line ending | Inspect sample lines and FIELDS, LINES, CHARACTER SET settings |
| Some rows skipped or converted | Type mismatch, duplicate keys, IGNORE option, or SQL mode | Read SHOW WARNINGS, compare source data against table rules |

When investigating, collect at minimum: the executed statement (with secrets redacted), MySQL and driver versions, local_infile and secure_file_priv values, SHOW GRANTS output, the path used, which machine owns that path, and OS permissions of the relevant process. Do not remediate by granting FILE to a broader account or setting secure_file_priv to an empty string before identifying the root cause.

If an unnecessary account is found to hold FILE, audit its usage scope, revoke the privilege, inspect relevant logs, and verify which directories MySQL can access. If LOCAL is no longer needed, disable the feature on both server and clients per deployment configuration.

## 9. Self-Check

**Scenario 1:** An application running on an application server needs to import a CSV file from the application's own directory into a remote MySQL server. The import account only needs to insert into a staging table. What is the right approach?

**Hint:** Consider LOAD DATA LOCAL INFILE. The path must be readable by the application process; LOCAL must be enabled on both server and client, and the account needs INSERT on the table. Do not grant FILE simply because LOCAL is used.

**Scenario 2:** An administrator wants MySQL to read a file from /var/lib/mysql-files on the DB server itself. Which control layers must all be satisfied?

**Hint:** LOAD DATA INFILE requires FILE and INSERT; secure_file_priv must permit the directory; the mysqld process must have permissions to read the file and parent directories.

**Scenario 3:** The server has secure_file_priv pointing to a dedicated directory, yet the application still uses LOCAL to read files from the application host. Does this variable restrict LOCAL paths?

**Hint:** No. secure_file_priv controls server-side file operations. LOCAL must be governed via local_infile, client/driver configuration, server identity verification, and client process permissions.

**Scenario 4:** An application account holds FILE even though it only runs SELECT, INSERT, and UPDATE on a business schema. How should this be handled?

**Hint:** Verify whether the application truly needs server-side file operations. If not, revoke FILE. FILE is a global privilege and should not be treated as a convenience privilege for application accounts.

## 10. Key Takeaways

- LOCAL reads files from the client host; INFILE without LOCAL reads files from the MySQL server.
- LOAD DATA LOCAL INFILE does not require the FILE privilege, but requires LOCAL enabled on both client and server plus write privileges on the target table.
- FILE is a global privilege opening server-side file read or write capabilities through supported statements.
- secure_file_priv restricts or disables server-side file operations; it does not replace OS permissions and does not restrict LOCAL paths.
- Disable LOCAL when unused, avoid granting FILE to application accounts, and use a dedicated staging directory with minimal permissions.
- Always check warnings, row counts, file formatting, and business outcomes after importing.
