# LOAD DATA INFILE vs. LOAD DATA LOCAL INFILE

MySQL can bulk-load records from a file using the `LOAD DATA` statement. There are two ways to read the file: `LOAD DATA INFILE`, where the MySQL server process reads the file on the server host, and `LOAD DATA LOCAL INFILE`, where the client program reads the file on the client machine and streams its contents over the connection to the server. This difference in file location leads to differences in privileges, configuration, security, and deployment.

In a MySQL system, importing data is more than pushing CSV lines into a table. You must specify the file source, charset, delimiters, escape rules, target data types, account privileges, and how to handle malformed records. A safe pipeline typically loads into a staging table, validates the data, and then merges it into business tables.

This lesson uses MySQL 8.0 syntax. Some client options depend on the connector and version; consult the documentation for the exact driver you are using.

## Learning Objectives

After this lesson, you will be able to:

- Distinguish where `INFILE` and `LOCAL INFILE` read files from.
- Identify the required MySQL privileges, server configuration, and OS permissions.
- Choose the appropriate loading method based on file location, security policy, and deployment environment.
- Describe CSV/TSV format using `FIELDS`, `LINES`, `CHARACTER SET`, and `IGNORE`.
- Map columns, normalize values, and handle invalid data during import.
- Design an import workflow with staging, validation, logging, and safe re-runnability.

## 1. Two Ways to Read Files

### 1.1. `LOAD DATA INFILE`: Server Reads the File

Without the `LOCAL` keyword, MySQL Server opens and reads the file on the server host. The path in the statement is interpreted relative to the server's filesystem, under the OS user running the `mysqld` process.

Example:

```sql
LOAD DATA INFILE '/var/lib/mysql-files/orders.csv'
INTO TABLE staging_orders
CHARACTER SET utf8mb4
FIELDS TERMINATED BY ','
OPTIONALLY ENCLOSED BY '"'
ESCAPED BY '\\'
LINES TERMINATED BY '\r\n'
IGNORE 1 LINES;
```

In this example, the file must exist on the machine running MySQL, the MySQL OS account must have read permissions on the file, and the path must comply with `secure_file_priv` if that variable is set.

This option fits when files have already been placed on the server through a controlled deployment channel, such as an ETL job running close to the database or a dedicated import directory. The client does not have to stream the entire file content over the MySQL connection.

### 1.2. `LOAD DATA LOCAL INFILE`: Client Reads the File

With the `LOCAL` keyword, the client program reads the file on the machine running the client and sends the contents to MySQL Server over the connection. The path is interpreted on the client machine's filesystem, not the database server's.

```sql
LOAD DATA LOCAL INFILE '/client/import/orders.csv'
INTO TABLE staging_orders
CHARACTER SET utf8mb4
FIELDS TERMINATED BY ','
OPTIONALLY ENCLOSED BY '"'
ESCAPED BY '\\'
LINES TERMINATED BY '\r\n'
IGNORE 1 LINES;
```

The file `/client/import/orders.csv` must exist and be readable on the machine running the application or import tool. The server receives the data over the MySQL protocol and uses temporary storage while processing; therefore, adequate disk space and I/O are still required on the server side.

`LOCAL` is convenient when the file resides on an ETL host, admin workstation, or job container and you do not want to copy files onto the database host. In exchange, data traverses the network and both client and server must permit `LOCAL` capability.

### 1.3. Quick Comparison

| Criterion | `LOAD DATA INFILE` | `LOAD DATA LOCAL INFILE` |
|---|---|---|
| Where the file is opened | MySQL Server host | Machine running the client program |
| Where the path is resolved | Server filesystem | Client filesystem |
| Who reads the file | OS account running `mysqld` | OS account running the client |
| Characteristic MySQL privileges | Requires global `FILE` privilege and appropriate table write privileges | Does not require `FILE`; requires appropriate table write privileges |
| Relevant configuration | `secure_file_priv`, filesystem permissions, OS security policies | `local_infile` on server and LOCAL-enabling option on client/connector |
| Data flow | Server reads directly from server disk | Client streams content over the MySQL connection |
| Typical use case | File is already placed on the database host in a controlled import directory | File resides on an ETL host, admin machine, or client environment |

`LOCAL` does not mean the server uses no disk. The server may still use temporary files to receive and process streamed contents. Conversely, `INFILE` does not mean the client needs access to the server's filesystem.

## 2. Privileges and Configuration for `LOAD DATA INFILE`

### 2.1. MySQL Privileges

For `LOAD DATA INFILE` without `LOCAL`, the account requires the global `FILE` privilege for the server to read the file, plus `INSERT` privilege on the target table. `FILE` is a sensitive privilege because it permits server-side file read/write operations within what MySQL and the OS allow; never grant it to ordinary application accounts.

Example of granting write privileges to a staging table:

```sql
GRANT INSERT
  ON import_db.staging_orders
  TO 'etl_loader'@'10.20.1.15';

GRANT FILE
  ON *.*
  TO 'etl_server_loader'@'localhost';

GRANT INSERT
  ON import_db.staging_orders
  TO 'etl_server_loader'@'localhost';
```

These statements illustrate two accounts with different roles: the account running `LOCAL` only needs table write privileges; the account using server-side `INFILE` needs both `FILE` and table write privileges. In production, grant privileges only to the account actually performing the import and restrict hosts appropriately. If using `REPLACE` or additional expressions/objects, check any extra privileges required by the statement and version.

### 2.2. `secure_file_priv`

`secure_file_priv` restricts server-side file import/export operations:

```sql
SHOW GLOBAL VARIABLES LIKE 'secure_file_priv';
```

Its value is typically interpreted as follows:

- A directory path: the server restricts related file operations to that directory.
- `NULL`: the server disables server-side file import/export operations governed by this variable.
- An empty string: no directory restriction is enforced by this variable; such a configuration must be evaluated very carefully.

In common installations, a dedicated directory for import/export is configured at MySQL startup, such as `/var/lib/mysql-files`. Verify the actual value rather than assuming the default path is identical across every OS or package.

Beyond `secure_file_priv`, the OS account running `mysqld` must have read permission on the file and traverse permission on parent directories. SELinux, AppArmor, or OS security policies can also block access even when Unix/Windows permissions appear sufficient.

### 2.3. Configuration and Privileges for `LOCAL`

The server must allow `LOCAL` capability via the `local_infile` variable; the client or connector must also enable sending local files. Check on the server side:

```sql
SHOW GLOBAL VARIABLES LIKE 'local_infile';
```

If policy permits and it needs to be enabled, an administrator can change the variable using the version-appropriate configuration mechanism, for example:

```sql
SET GLOBAL local_infile = ON;
```

A `GLOBAL` change affects new connections and may not persist across restarts unless startup configuration is updated. Changing the variable requires appropriate administrative privileges. Do not enable `LOCAL` on every server just to make one import job work; restrict the scope of clients and environments allowed to use it.

With the MySQL command-line client, `--local-infile=1` allows the client to use `LOCAL` if both the client build and server support it. For applications, configure the corresponding option on the connector in use. Option names and defaults vary across Connector/J, Connector/Python, Connector/C, and other drivers.

## 3. Security Risks When Enabling LOCAL

`LOAD DATA LOCAL INFILE` allows the server to request that the client send a file from the client machine. Consequently, a client with `LOCAL` enabled must trust the server it connects to. A malicious or compromised server could exploit this capability to ask the client to send files readable by the client process, depending on library behavior and protective settings.

Risk mitigation measures:

- Enable `LOCAL` only in jobs or connections that genuinely need client-side file imports.
- Use directory allowlists or path restriction mechanisms supported by the connector; never allow arbitrary file reads on application hosts.
- Connect only to servers with verified identity; use TLS to protect transit and authenticate endpoints per organizational policy.
- Never enable `LOCAL` in clients used to connect to untrusted servers.
- Use a dedicated import account granted privileges only on the required staging tables.
- Disable `LOCAL` or remove the client flag when the job finishes if the workflow does not need it continuously.
- Log the source file, operator, timestamp, target table, rows loaded, and warning count.

TLS protects data in transit over the network, but it does not stop a server trusted by the client from requesting local files. Restricting filesystem permissions of the ETL process remains critical.

## 4. Defining Input Data Format

`LOAD DATA` does not automatically guess every CSV dialect accurately. Operators must specify how the file separates fields, encloses values, and terminates lines.

| Option | Meaning | Example |
|---|---|---|
| `CHARACTER SET` | Charset used to interpret file contents | `CHARACTER SET utf8mb4` |
| `FIELDS TERMINATED BY` | Column delimiter character | `FIELDS TERMINATED BY ','` |
| `OPTIONALLY ENCLOSED BY` | Field quoting character, commonly used for text | `OPTIONALLY ENCLOSED BY '"'` |
| `ESCAPED BY` | Escape character inside the file | `ESCAPED BY '\\'` |
| `LINES TERMINATED BY` | Line-ending sequence | `LINES TERMINATED BY '\r\n'` |
| `IGNORE n LINES` | Skip initial lines, typically a header | `IGNORE 1 LINES` |

Example with a UTF-8 CSV file on Windows, with a header and CRLF line endings:

```sql
LOAD DATA LOCAL INFILE '/client/import/customers.csv'
INTO TABLE staging_customers
CHARACTER SET utf8mb4
FIELDS TERMINATED BY ','
OPTIONALLY ENCLOSED BY '"'
ESCAPED BY '\\'
LINES TERMINATED BY '\r\n'
IGNORE 1 LINES
(customer_id, full_name, email, created_at);
```

This example assumes the file uses backslash as the escape character. If the generating system produces CSV using a different quoting convention, such as doubling double-quotes to represent a quote inside a field, configure `ENCLOSED BY`/`ESCAPED BY` accordingly and test with rows containing commas, quotes, and embedded newlines. Never assume every `.csv` file shares the same dialect.

### 4.1. Charset and Newlines

`CHARACTER SET` describes the charset of the data inside the file. It does not set the charset for the entire connection. If a file was exported in UTF-8 but loaded as another charset, accented characters can become corrupted or turn into unintended characters.

Inspect file characteristics before importing:

- Actual encoding: UTF-8, UTF-8 with BOM, Windows-1252, or another charset.
- Delimiter: comma, tab, semicolon, or another character.
- Quoting and escaping rules.
- Whether newlines are `\n` or `\r\n`.
- Whether there is a header, blank lines, NUL characters, or trailing delimiters.

If the file has a BOM or a dialect not handled by MySQL as expected, normalize the file in an ETL step before loading. Do not blindly strip or replace leading bytes without verifying the impact on the first field.

### 4.2. Headers, Ignored Columns, and User Variables

`IGNORE 1 LINES` skips the first line, typically a header. MySQL does not automatically match header names to table columns; field order must still be declared explicitly.

You can read a field into a user variable and transform it with `SET`:

```sql
LOAD DATA LOCAL INFILE '/client/import/orders.csv'
INTO TABLE staging_orders
CHARACTER SET utf8mb4
FIELDS TERMINATED BY ','
OPTIONALLY ENCLOSED BY '"'
ESCAPED BY '\\'
LINES TERMINATED BY '\r\n'
IGNORE 1 LINES
(order_id, customer_id, @raw_amount, @raw_created_at)
SET amount = NULLIF(TRIM(@raw_amount), ''),
    created_at = STR_TO_DATE(@raw_created_at, '%Y-%m-%d %H:%i:%s');
```

In this example, data goes into `@raw_amount` and `@raw_created_at` first, then is converted into values suited to the columns. Columns omitted from the list can receive defaults or values assigned by `SET`. Ensure the field list matches the actual data order in the file.

If the file contains unused columns, map those fields into user variables and omit them in `SET`. This preserves file column alignment without modifying the source file.

## 5. Handling Duplicate Records and Bad Data

### 5.1. `IGNORE` and `REPLACE`

`LOAD DATA` supports options for handling unique-key conflicts:

- `IGNORE`: skip conflicting records and continue processing subsequent rows. This can result in fewer loaded rows than lines in the file.
- `REPLACE`: replace existing records when a unique-key conflict occurs. Evaluate deletion/replacement impact, foreign keys, triggers, and other unique keys before using this.

Example:

```sql
LOAD DATA LOCAL INFILE '/client/import/products.csv'
IGNORE INTO TABLE staging_products
FIELDS TERMINATED BY ','
LINES TERMINATED BY '\n';
```

Do not use `IGNORE` to mask data errors. It can suppress conflicts and certain invalid data conditions, making an import appear successful while dropping records. Inspect warnings and row counts after every load.

### 5.2. Checking Warnings Immediately After Import

After `LOAD DATA`, read the result summary returned by the client and check warnings in the same session:

```sql
SHOW COUNT(*) WARNINGS;
SHOW WARNINGS LIMIT 50;
```

Reconcile lines in the file, rows read, rows skipped, rows replaced, and warning count. Warnings can indicate truncated values due to column length, invalid number/date conversions, wrong charset, or duplicate keys.

SQL mode, MySQL version, storage engine, and whether `LOCAL`, `IGNORE`, or `REPLACE` is used affect how certain errors are reported and handled. Test on a small sample containing edge-case data before importing the full file.

### 5.3. Data Types and NULL Values

Do not load external source data directly into overly strict column types if the file may contain empty strings, malformed numbers, or non-standard dates. A staging table can use text columns to retain source values intact, then validate and transform them via SQL.

Rules to define clearly:

- Does an empty string `''` mean an empty value or must it become `NULL`?
- Is `\N` used in the file to represent SQL `NULL`?
- Do decimals use a period or a comma?
- Are dates formatted as `YYYY-MM-DD`, `DD/MM/YYYY`, or something else?
- Is leading/trailing whitespace significant or should `TRIM()` be applied?

MySQL's default format uses `\N` to represent `NULL` in many cases. When using custom `ESCAPED BY` or `ENCLOSED BY`, re-verify how the parser interprets `NULL`, empty strings, and escape characters.

## 6. Safe Import Workflow Using Staging Tables

For business data, do not let external files write directly into core tables without validation. A staging table holds input data, exposes errors, and lets you control when target tables are updated.

### 6.1. Creating the Staging Table

Example:

```sql
CREATE TABLE staging_orders (
  order_id_text VARCHAR(40),
  customer_id_text VARCHAR(40),
  amount_text VARCHAR(80),
  created_at_text VARCHAR(80),
  imported_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE = InnoDB;
```

Text columns preserve source values for conversion checks. For large files, add a batch identifier or source-file column if the workflow needs to trace multiple imports; fixed values can be supplied via user variables/`SET`.

### 6.2. Loading the File and Validating

```sql
LOAD DATA LOCAL INFILE '/client/import/orders.csv'
INTO TABLE staging_orders
CHARACTER SET utf8mb4
FIELDS TERMINATED BY ','
OPTIONALLY ENCLOSED BY '"'
ESCAPED BY '\\'
LINES TERMINATED BY '\r\n'
IGNORE 1 LINES
(order_id_text, customer_id_text, amount_text, created_at_text);

SELECT COUNT(*) AS staged_rows
FROM staging_orders;

SELECT *
FROM staging_orders
WHERE order_id_text = ''
   OR customer_id_text = ''
   OR amount_text NOT REGEXP '^[0-9]+([.][0-9]{1,2})?$'
LIMIT 50;
```

The regular expression is only an example for positive numbers with up to two decimal places. If business rules allow negative numbers, thousands separators, or different rounding rules, adjust validation accordingly.

### 6.3. Moving Valid Data into Business Tables

After verifying row counts, duplicates, foreign keys, and formatting, move valid rows with a controlled SQL statement:

```sql
START TRANSACTION;

INSERT INTO orders (order_id, customer_id, amount, created_at)
SELECT
  CAST(order_id_text AS UNSIGNED),
  CAST(customer_id_text AS UNSIGNED),
  CAST(amount_text AS DECIMAL(12, 2)),
  STR_TO_DATE(created_at_text, '%Y-%m-%d %H:%i:%s')
FROM staging_orders
WHERE order_id_text REGEXP '^[0-9]+$'
  AND customer_id_text REGEXP '^[0-9]+$'
  AND amount_text REGEXP '^[0-9]+([.][0-9]{1,2})?$'
  AND STR_TO_DATE(created_at_text, '%Y-%m-%d %H:%i:%s') IS NOT NULL;

COMMIT;
```

This is a skeleton example; add deduplication conditions, customer existence checks, and business-specific update rules. If the statement fails, handle rollback per application procedure. Do not purge staging before recording import metrics and completing reconciliation.

### 6.4. Safe Re-Runs

A job may be retried due to timeouts or worker restarts. Without an import-run identifier, data can be duplicated or overwritten incorrectly. Use an `import_batch_id`, filename with checksum, import audit table, or unique key derived from the source identifier.

Before retrying, determine how far the previous import got, whether the statement committed, and whether staging data still exists. Design the merge step to be idempotent per business rules; avoid broad `REPLACE` if you do not want related records deleted and re-inserted.

## 7. Performance and Operations

`LOAD DATA` is generally more efficient than sending individual `INSERT` statements because MySQL processes data via a bulk-loading path. However, actual speed still depends on file size, indexes, constraints, triggers, storage, binlogs, network, and concurrent load.

### 7.1. Choosing Server-Side vs. LOCAL Based on File Location

- File is already on the database host and can be placed in a controlled directory: consider `INFILE` so the server reads directly.
- File is on an ETL host or container: `LOCAL` is usually simpler, but restrict file read permissions and secure the connection.
- Very large file or slow client-server network: consider transferring the file to a staging area near the database via a controlled channel and using `INFILE`, if infrastructure policy permits.

Do not pick `INFILE` solely to avoid network transfer if granting `FILE` and placing files on the database host creates greater operational risk.

### 7.2. Importing Large Files

For large files:

- Measure file read speed, network throughput, disk I/O, and execution time on representative data.
- Ensure the server has sufficient space for temporary files, binary logs, redo/undo, and target data.
- Check the impact of indexes, unique constraints, foreign keys, and triggers.
- Split the file into batches if separate batch commits are acceptable and resumability is needed.
- Monitor lock waits, replication lag, and backup duration during import.
- Record rows loaded, skipped, replaced, warnings, and processing duration.

Do not arbitrarily disable constraint checks or triggers to gain speed. If optimization is needed, evaluate it on an environment clone, ensure data is validated before re-enabling constraints, and verify the complete result.

### 7.3. Transactions and Integrity

For InnoDB tables, data writes are transactional per the storage engine's capabilities; imports and merge steps can be structured in appropriate transactions. For non-transactional tables, a mid-flight error can leave partial writes behind. Steps like creating tables or altering structure also have their own commit rules, so never assume an entire workflow of creating staging, loading a file, validating, and merging forms a single atomic transaction.

For critical data, prefer InnoDB, import into staging, validate before merging, and maintain appropriate backups/restore points. Test rollback, duplicates, and conversion errors in a test environment before deploying.

## 8. Troubleshooting Workflow

When `LOAD DATA` fails or data looks wrong, check in order:

1. **Verify file location:** for `INFILE`, check the database host; for `LOCAL`, check the machine or container running the client.
2. **Check filesystem permissions:** does the user running `mysqld` or the client have read access to the file? Do parent directories have traverse permissions?
3. **Check MySQL privileges:** server-side needs `FILE` and table privileges; `LOCAL` needs table write privileges and `LOCAL` enabled.
4. **Check configuration:** inspect `secure_file_priv` for server-side and `local_infile` for `LOCAL`; verify connector options.
5. **Check dialect:** do charset, BOM, delimiter, quotes, escapes, newlines, and header match the file?
6. **Check warnings:** run `SHOW WARNINGS` immediately after import and compare file line count with loaded row count.
7. **Check target table:** duplicate keys, constraints, triggers, data types, column lengths, and `NULL` values.
8. **Check resources:** disk space, temporary directory, network, I/O, binary logs, and replication lag.

Common issues:

| Symptom | Possible Cause | Resolution |
|---|---|---|
| `Access denied` when using `INFILE` | Missing `FILE`, wrong host/path, or blocked by `secure_file_priv` | Check grants, server path, and protective variable |
| File not found | File is on client while using `INFILE`, or on server while using `LOCAL` | Confirm where the client runs versus where `mysqld` runs |
| `LOCAL` rejected | `local_infile` disabled on server or connector | Check policy, server variable, and driver option |
| Vietnamese characters are corrupted | Declared charset mismatch or file has a BOM | Identify actual encoding and load with matching charset; normalize file if needed |
| Strange characters in last column | Wrong newline, e.g., CRLF read as LF | Adjust `LINES TERMINATED BY` and inspect sample rows |
| Fewer rows loaded than in file | Header, bad rows, duplicates, or `IGNORE` | Read summary and warnings; inspect each group of records |
| Slow import | Indexes/constraints/triggers, I/O, binlog, or network bottleneck | Measure each layer and optimize using representative benchmarks |

## 9. Practice Exercise

An ETL team runs jobs in a separate container, generating a `customers.csv` file with 2 million rows. MySQL runs on a different server. The file contains Vietnamese names, a datetime column, an optionally empty email field, and a header on the first line. The ETL account currently has only `INSERT` privilege on `import_db.staging_customers`.

Design two import approaches and explain the trade-offs:

1. If using `LOAD DATA LOCAL INFILE`, which capabilities must be enabled on the server and connector? Where is the file read and over which path is it sent?
2. If using `LOAD DATA INFILE`, where must the file be transferred, and which MySQL and OS permissions are required?
3. Why should the ETL account not be granted `FILE` just to import from a container?
4. Write a `LOAD DATA` statement with `CHARACTER SET utf8mb4`, delimiters, quotes, escapes, newlines, and skipping the header.
5. How do you convert empty emails to `NULL`, parse datetimes, and detect invalid records?
6. What should be checked after loading to confirm all 2 million rows were processed accurately?
7. Design a batch identifier mechanism and safe re-run strategy if the container crashes mid-run.
8. List measures to mitigate risks when enabling `LOCAL`, especially if the client connects to multiple servers.

A solid plan must specify file location, component permissions, `LOCAL` configuration, data formatting, and result reconciliation. Test first with a small file containing Vietnamese diacritics, commas inside text fields, empty strings, invalid dates, and duplicate keys.

## 10. Common Misconceptions

- **Assuming `INFILE` reads files on the machine executing the SQL:** without `LOCAL`, the server reads the file on the database host.
- **Assuming `LOCAL` needs no server configuration:** both server and client/connector must permit `LOCAL`.
- **Granting `FILE` to every ETL account:** this privilege is global and affects server-side file operations; grant it only when genuinely using server-side import.
- **Assuming `secure_file_priv` restricts directories on the client:** this variable governs server-side file operations, and does not replace path allowlists in client applications.
- **Assuming all CSVs use the same quote/escape rules:** always inspect the actual dialect of the exported file.
- **Ignoring warnings because the statement finished:** the statement may have loaded fewer rows than expected or converted data unexpectedly.
- **Importing straight into core tables:** staging helps catch bad data, duplicates, and format mismatches before updating business data.
- **Using `IGNORE` to hide errors:** skipping rows can cause missing data without addressing the root cause.

## Conclusion

`LOAD DATA INFILE` has MySQL Server read a file on the server host, typically requiring the `FILE` privilege, appropriate filesystem permissions, and compliance with `secure_file_priv`. `LOAD DATA LOCAL INFILE` has the client read a file on the client machine and stream its contents to the server; it requires permission on both server and connector and must be controlled because it enables a server to request local files from the client. Whichever approach you choose, specify the exact charset and dialect, inspect warnings, stage business data before merging, and record import metrics for reconciliation and safe re-runs.
