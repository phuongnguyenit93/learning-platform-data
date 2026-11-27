# SELECT INTO OUTFILE, FILE Privilege, and secure_file_priv

MySQL can export query results directly into a file on the database server using the `SELECT INTO OUTFILE` statement. This mechanism is useful when you need a clearly formatted logical export to transfer data to another system. However, the file is written on the MySQL server's filesystem, not the machine running the SQL client. Consequently, the `FILE` privilege, `secure_file_priv` configuration, and write permissions of the OS account running MySQL must all be verified.

This lesson belongs to the **DATABASE_MYSQL** module, focusing on data import/export and migration: generating CSV or TSV files, controlling the exported data scope, configuring secure directories, enforcing least privilege, and handling file-writing errors. Examples use MySQL 8.0.

## 1. How Does SELECT INTO OUTFILE Work?

`SELECT INTO OUTFILE` executes a query on MySQL Server and writes the resulting rows into a file on a filesystem accessible to the `mysqld` process.

Execution flow:

1. The client sends the `SELECT INTO OUTFILE` statement to MySQL Server.
2. The server verifies `SELECT` privilege on the queried objects and `FILE` privilege on the account.
3. The server checks the `secure_file_priv` policy.
4. The OS checks whether the MySQL service account has permission to create the file in the target directory.
5. MySQL writes the query rows according to the configured field delimiter, enclosure, escape, and line-ending rules.

Key point: the path in `INTO OUTFILE` is resolved on the database server. If a client connects from a personal workstation to a remote server, the file is still created on the server. To obtain the file on the client machine, transfer the file over a secured channel or use an export tool that writes files on the client side.

### General Syntax

~~~sql
SELECT select_list
INTO OUTFILE 'file_name'
  [CHARACTER SET charset_name]
  [FIELDS
    [TERMINATED BY 'string']
    [[OPTIONALLY] ENCLOSED BY 'char']
    [ESCAPED BY 'char']
  ]
  [LINES
    [STARTING BY 'string']
    [TERMINATED BY 'string']
  ]
FROM table_name
WHERE condition;
~~~

Formatting options:

- **CHARACTER SET** selects the character set used to write data to the file.
- **FIELDS TERMINATED BY** sets the delimiter between columns.
- **ENCLOSED BY** wraps field values with a character, such as a double quote.
- **OPTIONALLY ENCLOSED BY** wraps only string-type fields rather than all values.
- **ESCAPED BY** specifies the character used to escape special characters and `NULL` values.
- **LINES TERMINATED BY** sets the terminating sequence for each row.
- **LINES STARTING BY** prepends a string at the start of each row, typically unnecessary for CSV.

If options are omitted, MySQL uses the default format with tabs separating fields, newlines separating rows, and backslashes for escaping. For system integrations, declare formatting explicitly to avoid relying on defaults.

## 2. FILE Privilege and SELECT Privilege

To export with `SELECT INTO OUTFILE`, the account needs:

- `SELECT` privilege on the queried table or view.
- Global `FILE` privilege so MySQL permits server-side file reading/writing via supported mechanisms.
- OS permissions for the account running `mysqld` to create files in the target directory.
- A path within `secure_file_priv` if that variable restricts the directory.

Check current privileges:

~~~sql
SHOW GRANTS FOR CURRENT_USER();
~~~

`FILE` is a global privilege and cannot be scoped to a single schema or table. Example of granting it:

~~~sql
GRANT FILE ON *.* TO 'data_exporter'@'10.20.%';
~~~

When no longer needed:

~~~sql
REVOKE FILE ON *.* FROM 'data_exporter'@'10.20.%';
~~~

Do not grant `FILE` to ordinary application accounts or shared accounts. This privilege is broad: depending on configuration and filesystem permissions, the account may read or write files accessible to the MySQL process. Therefore, create a dedicated export account, restrict the host, grant `SELECT` on the narrowest scope, and revoke `FILE` once the task completes if only needed temporarily.

The `FILE` privilege does not automatically grant `SELECT`. Conversely, having `SELECT` on a table is insufficient to run `INTO OUTFILE` without `FILE`.

## 3. How Does secure_file_priv Control Directories?

The **secure_file_priv** system variable restricts server-side file import/export operations, including `SELECT INTO OUTFILE`, `LOAD DATA INFILE`, and `LOAD_FILE()`.

Check:

~~~sql
SHOW VARIABLES LIKE 'secure_file_priv';
~~~

Its three states have distinct meanings:

| Value | Behavior |
|---|---|
| Directory path, e.g. `/var/lib/mysql-files/` | File operations are restricted to the specified directory |
| Empty string | No directory restriction applied by `secure_file_priv`; scope still depends on filesystem permissions |
| `NULL` | Disables file import/export operations governed by this variable |

On many packages, MySQL is configured with a dedicated import/export directory. The actual value depends on OS, package, and server configuration; always query the instance rather than guessing the path.

### Configuring a Secure Directory

Example in the MySQL configuration file:

~~~ini
[mysqld]
secure_file_priv=/var/lib/mysql-files
~~~

The directory must exist and the OS account running MySQL must have appropriate write permissions. Do not grant broad write permissions to all users. On Linux systems, administrators can set directory ownership and permissions for the MySQL service account, for example:

~~~bash
sudo install -d -o mysql -g mysql -m 750 /var/lib/mysql-files
~~~

The service account name may vary by distribution. Verify the actual account before changing filesystem permissions.

**secure_file_priv** is read-only while the server is running and is set at MySQL startup. After editing the configuration file, restart MySQL per your maintenance procedure and verify the value again. You cannot use `SET GLOBAL` to change this variable in a running session.

Do not set `secure_file_priv` to an empty string in production without an evaluated operational justification. Limiting access to a dedicated directory narrows the set of files SQL statements can touch.

## 4. Exporting TSV Data

TSV uses tabs to separate fields. It is a simple format suitable when the target system can consume tab-delimited text.

~~~sql
SELECT
  order_id,
  customer_id,
  created_at,
  total_amount
INTO OUTFILE '/var/lib/mysql-files/orders.tsv'
CHARACTER SET utf8mb4
FIELDS TERMINATED BY '\t'
LINES TERMINATED BY '\n'
FROM sales.orders
WHERE created_at >= '2026-01-01';
~~~

In this example:

- Only the four needed columns are exported, avoiding `SELECT *`.
- Data is written in UTF-8/`utf8mb4`.
- Tabs separate columns.
- MySQL's default escape character is used for tabs, newlines, backslashes, and special values.
- Each row ends with LF.

If the receiving system requires CRLF, set **LINES TERMINATED BY '\r\n'**. Align line-ending rules with the consuming system.

## 5. Exporting CSV

CSV typically uses commas to separate columns and double quotes to enclose text values. Example:

~~~sql
SELECT
  order_id,
  customer_name,
  created_at,
  total_amount
INTO OUTFILE '/var/lib/mysql-files/orders.csv'
CHARACTER SET utf8mb4
FIELDS TERMINATED BY ','
OPTIONALLY ENCLOSED BY '"'
LINES TERMINATED BY '\n'
FROM sales.orders
WHERE created_at >= '2026-01-01';
~~~

**OPTIONALLY ENCLOSED BY** wraps string fields in double quotes. The default escape character is backslash. Data containing commas, quotes, backslashes, or newlines must be escaped per MySQL's export rules.

CSV does not have a single uniform way to represent `NULL` across all tools. With a non-empty escape character, MySQL writes `NULL` as backslash-N (`\N`). The receiving application must distinguish `NULL` from an empty string. If the target system mandates specific CSV rules, test with sample data containing `NULL`, empty strings, commas, quotes, and newlines before running a full export.

`SELECT INTO OUTFILE` does not automatically add a column header row. If the recipient requires headers, add the header row in a client-side step or craft an export query with a separate initial row, then verify data types and column order before use.

Sample test values should include:

| Source Value | What to Verify |
|---|---|
| `NULL` | `NULL` recognition under escape rules |
| Empty string | Not misinterpreted as `NULL` |
| `Nguyen, An` | Comma inside a string field |
| `He said "hello"` | Double quotes inside content |
| Line 1 and line 2 | Newline character inside a single field |
| Vietnamese text with diacritics | Character set decoded accurately |

For strict RFC 4180 exchange or specific platform requirements, confirm the receiving parser is compatible with MySQL's escaping. Format conversion via a client-side tool after export may be necessary.

## 6. Controlling Data Before Export

`SELECT INTO OUTFILE` can create a copy of sensitive data on the database server's filesystem. Before running it, define the exact purpose and scope of data to provide.

### Selecting Columns and Filtering Rows

Do not export all columns out of habit. Write an explicit column list, filter by date or status, and retrieve only records in scope.

~~~sql
SELECT
  customer_id,
  email,
  created_at
INTO OUTFILE '/var/lib/mysql-files/customer-contact.csv'
CHARACTER SET utf8mb4
FIELDS TERMINATED BY ','
OPTIONALLY ENCLOSED BY '"'
LINES TERMINATED BY '\n'
FROM crm.customers
WHERE marketing_consent = 1
  AND status = 'active';
~~~

If real emails are unnecessary, export customer IDs or masked/encrypted data per policy. Never export passwords, tokens, payment credentials, or personal data beyond the processing purpose.

### Using Views or Explicitly Scoped Queries

You can create a view exposing only permitted fields and grant `SELECT` on that view to the export account. This separates data access scope from querying the entire source table. However, `FILE` remains a global privilege and must be controlled separately.

### Protecting Files After Export

- Restrict directory and file read permissions to required service accounts or operational groups.
- Do not retain files longer than business requirements dictate.
- Encrypt at rest and in transit over the network.
- Log the requester, query/scope, timestamp, and file location.
- Delete temporary copies via a controlled process once the recipient confirms complete receipt.
- Avoid writing paths containing sensitive details into public application logs.

## 7. Target File Must Not Already Exist

MySQL will not overwrite an existing file with `SELECT INTO OUTFILE`. If the target file already exists, the command typically fails with:

~~~text
ERROR 1086 (HY000): File ... already exists
~~~

Use a new filename for each export, such as appending a timestamp or run ID. Do not automatically delete an old file before confirming no other process is still using it.

Date-based filenames can be generated by the application or orchestrator and passed as a safe literal in the SQL statement. Never concatenate paths directly from unvalidated user input; prevent callers from choosing arbitrary server paths.

`SELECT INTO OUTFILE` does not create parent directories. The directory must already exist, reside within `secure_file_priv`, and have appropriate write permissions.

## 8. Comparing OUTFILE, DUMPFILE, and Client-Side Export

| Export Method | Where File Is Created | Format | When to Use |
|---|---|---|---|
| `SELECT INTO OUTFILE` | MySQL Server host | Text rows with delimiters/escapes | Exporting structured TSV/CSV datasets from the server |
| `SELECT INTO DUMPFILE` | MySQL Server host | Raw binary data of a single row | Exporting a single binary value or single row without added delimiters |
| Client-side export | Machine running app or SQL client | Tool-dependent | Writing files directly on the client machine or avoiding granting `FILE` |

**SELECT INTO DUMPFILE** writes only a single row and adds no field/row formatting delimiters. It is not a substitute for multi-row CSV.

If you need files on the client machine, use an application, database library, or client-side export utility. For example, MySQL Shell has a table export utility suited to certain export flows. Check that tool's output path since files are generally written on the machine running Shell, unlike `OUTFILE`.

Client-side export avoids granting `FILE` to the database user, though the application still needs `SELECT` and must protect output files similarly.

## 9. Combining OUTFILE with LOAD DATA INFILE

A text-based data movement workflow often has two steps:

1. Export data from the source with `SELECT INTO OUTFILE`.
2. Transfer the file to the target server over a secure channel and load it with `LOAD DATA INFILE` or a compatible tool.

Example loading TSV:

~~~sql
LOAD DATA INFILE '/var/lib/mysql-files/orders.tsv'
INTO TABLE sales.orders_import
CHARACTER SET utf8mb4
FIELDS TERMINATED BY '\t'
LINES TERMINATED BY '\n'
(order_id, customer_id, created_at, total_amount);
~~~

The `LOAD DATA` format must match how `SELECT INTO OUTFILE` wrote the file. Even when using the same directory on the same server, ensure the file is placed in the right location and is readable.

Distinction:

- **LOAD DATA INFILE** reads the file on the MySQL server host.
- **LOAD DATA LOCAL INFILE** reads the file from the client machine and sends it to the server; `LOCAL` capability must be enabled and permitted on both client and server per configuration.

Do not enable `LOCAL INFILE` broadly just for convenience when importing one file. Control the file source, allowed connecting clients, and permissions of the loading account.

When loading data into a target table, use a staging table, verify data types and row counts, validate constraints, and only then merge into business tables. Never load directly into production tables without a plan for bad rows, duplicate keys, and rollback.

## 10. Common Errors and Resolutions

### Server Rejects Due to secure_file_priv

Errors occur when the path lies outside the permitted directory or `secure_file_priv` is `NULL`. Check:

~~~sql
SHOW VARIABLES LIKE 'secure_file_priv';
~~~

Choose a path inside the configured directory. If policy needs to change, update server configuration and restart per procedure. Do not try to bypass the restriction via alternate paths or unapproved OS permission changes.

### Missing FILE Privilege

Check:

~~~sql
SHOW GRANTS FOR CURRENT_USER();
~~~

If the account is authorized to export data, grant `FILE` temporarily per approval workflow and revoke it upon completion. Also confirm the account has `SELECT` on the tables to export.

### Insufficient File Write Permissions

MySQL may fail to create the file even when the SQL account has `FILE`. Check whether the directory exists, whether the OS account running `mysqld` has write permission, whether disk space is sufficient, and whether access controls like SELinux or AppArmor are blocking it.

### File Already Exists

Pick a new filename or archive/rotate the old file per retention policy. MySQL does not overwrite existing files with `INTO OUTFILE`.

### File Created but Wrong Format

Check character set, delimiter, enclosure, escape, `NULL` rules, and line endings. Export a small dataset covering all edge cases, then open it with the receiving system's parser to verify.

### File Too Large or Slow Query

Narrow scope with filters, split by key ranges or time windows, inspect execution plans, and pick suitable indexes. Monitor I/O, disk space, and server load. For recurring high-volume exports, consider batch jobs or export tools with resume and throttling support.

## 11. Safe Data Export Workflow

Before running:

1. Confirm requester, purpose, and required tables/columns.
2. Check sensitive data and masking requirements.
3. Verify `FILE`, `SELECT`, and `secure_file_priv`.
4. Confirm target directory exists, filesystem permissions are set, and disk space is available.
5. Test the query with a row limit and inspect output formatting.
6. Specify a fresh filename and designated recipient.

During execution:

- Monitor query runtime, row count, I/O load, and file size.
- Avoid running multiple large exports concurrently on heavily loaded servers.
- Record run details and any errors.

After completion:

- Confirm the file exists, has reasonable size, and is readable.
- Count records in the file using an appropriate parser—not simple line counting if fields can contain newlines.
- Compare record counts with the source query over the same scope.
- Check encoding, `NULL`, delimiters, and edge-case fields.
- Transfer the file over a secured channel and confirm complete receipt.
- Revoke temporary `FILE` privileges and clean up copies per retention policy.

## 12. Checklist

- [ ] Determined whether the file is created on the server or client.
- [ ] Checked `secure_file_priv` and selected the proper directory.
- [ ] Confirmed account has `SELECT` on data and `FILE` only as needed.
- [ ] Confirmed the OS user running `mysqld` has write access to the directory.
- [ ] Confirmed the target file does not exist and parent directory already exists.
- [ ] Selected explicit columns, filtered rows, and excluded unnecessary data.
- [ ] Specified character set, delimiter, enclosure, escape, and line ending.
- [ ] Tested `NULL`, empty strings, commas, quotes, and newlines.
- [ ] Verified disk capacity, performance, and server load.
- [ ] Secured the file at rest and in transit; revoked temporary privileges.

## Conclusion

`SELECT INTO OUTFILE` exports data directly from MySQL Server into a file with controlled formatting. Safe usage requires coordinating `SELECT` privilege, the global `FILE` privilege, `secure_file_priv` directory restrictions, and filesystem permissions for the `mysqld` process. Export only necessary columns and rows, test formatting against edge-case data, protect generated files, and verify output before handing off to another system.
