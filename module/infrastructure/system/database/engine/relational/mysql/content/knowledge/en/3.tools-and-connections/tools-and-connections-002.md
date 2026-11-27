# Running SQL Statements, Scripts, and Recording Practice Results

When learning and operating MySQL, a statement running successfully in an SQL Editor is only part of the job. You also need to know which server you are connected to, which account and database you are using, which statements were actually sent, what results were returned, and how someone else can reproduce that exact workflow.

This lesson falls under the `DATABASE_MYSQL` scope: practicing queries, data manipulation, transactions, privilege management, and operating a relational database. The goal is to establish a repeatable workflow: **connect to the right environment → run statements or scripts → verify results → record evidence → enable reproducible runs**.

## 1. Ways to Work with MySQL

A client application sends SQL statements to MySQL Server over a connection. The server checks privileges, executes the statement, and returns data or status information. The client tool displays results, stores history, or writes logs according to its capabilities.

Commonly used tools:

| Tool | How It Is Used | Best Suited When |
|---|---|---|
| MySQL Command-Line Client (`mysql`) | Type SQL directly in a terminal or run SQL files | Learning syntax, automation, running scripts, quick checks |
| MySQL Workbench | Connect via a GUI, write SQL in the Editor tab, view results in a grid | Learning, development, administration, and schema visualization |
| MySQL Shell (`mysqlsh`) | Work in SQL, JavaScript, or Python modes | Advanced administration and automation; performing operations in multiple languages |
| DBeaver and other SQL IDEs | Manage multiple connections, write SQL, view data, and export results | Working across multiple database systems or needing a general-purpose GUI tool |
| Applications and connector libraries | Send statements via JDBC, Connector/Python, Node.js connectors, and other drivers | Integrating SQL into programs, services, and test pipelines |

Although their interfaces differ, all tools require connection details and are subject to MySQL Server's privilege checks. A read-only account cannot suddenly run an `UPDATE` statement simply because you use Workbench instead of a terminal.

It is important to distinguish three categories of commands:

- **SQL sent to the server:** `SELECT`, `INSERT`, `UPDATE`, `DELETE`, `CREATE TABLE`, `GRANT`, etc.
- **Client-specific commands:** `source`, `tee`, `status`, `delimiter`, `quit` in the MySQL Command-Line Client. The server does not interpret these as regular SQL statements.
- **Operating system commands:** launching the `mysql.exe` program, redirecting input/output, creating log directories, or invoking scripts from a terminal.

Understanding command categories helps avoid sending a client command in an SQL Editor or typing SQL statements into the operating system shell.

## 2. Preparing Connection Information

Before opening a client, you need the details provided by the administrator or development environment:

| Detail | Example | Meaning |
|---|---|---|
| Host | `127.0.0.1`, `db-dev.example.net` | Target MySQL server to connect to |
| Port | `3306` | TCP port of MySQL; may have been changed |
| User | `lab_user` | MySQL account used for authentication |
| Password | Entered at prompt | Authentication secret for the account |
| Database | `mysql_practice` | Default schema after connecting |
| TLS/CA | CA certificate and verification mode | Protects and verifies the connection to the server |

Do not guess the host, port, database, or account from a project name. Local, development, staging, and production environments may have different configurations. Before running statements that modify data, explicitly confirm the target environment.

### 2.1. Connecting with the MySQL Command-Line Client

Example connecting to MySQL running on the local machine:

~~~bash
mysql --host=127.0.0.1 --port=3306 --user=lab_user --password --database=mysql_practice --default-character-set=utf8mb4
~~~

Passing `--password` without a trailing value causes the client to prompt for the password interactively. Do not write passwords directly in commands like `--password=my-secret`: the password can appear in shell history, logs, or process lists.

If you do not specify a default database, omit `--database=mysql_practice`, then select the database in the session:

~~~sql
USE mysql_practice;
~~~

When connecting to a production server or over an untrusted network, configure TLS according to the provider's certificates and guidelines. Example with a provisioned CA certificate:

~~~bash
mysql --host=db.example.net --port=3306 --user=app_reader --password --ssl-mode=VERIFY_IDENTITY --ssl-ca=/path/to/ca.pem --default-character-set=utf8mb4
~~~

`VERIFY_IDENTITY` requires verifying both the certificate and the host identity. The hostname must match the certificate. Replace the CA path in the example with the actual path. Do not disable TLS verification just to make a connection error go away; inspect the CA, hostname, certificate expiration, and server configuration instead.

### 2.2. Storing Credentials More Conveniently

MySQL provides `mysql_config_editor` to create a login path for the Command-Line Client:

~~~bash
mysql_config_editor set --login-path=practice --host=127.0.0.1 --user=lab_user --port=3306 --password
~~~

The program prompts for the password and stores the credentials in a user-specific configuration file. You can then connect with:

~~~bash
mysql --login-path=practice --database=mysql_practice
~~~

A login path avoids typing the password on the command line every time. However, information in the login path file is obfuscated, not a strongly encrypted secrets vault. Protect the file with appropriate OS permissions and never share it with others.

In real-world applications, use a secret manager or the deployment environment's secrets mechanism. Never commit passwords, tokens, private keys, or config files containing secrets to Git.

### 2.3. Verifying the Target Server and Account

Immediately after connecting, run an environment-identification query:

~~~sql
SELECT
    VERSION() AS server_version,
    @@version_comment AS distribution,
    @@hostname AS server_host,
    @@port AS server_port,
    DATABASE() AS current_database,
    USER() AS client_identity,
    CURRENT_USER() AS privilege_identity,
    @@autocommit AS autocommit_mode,
    @@sql_mode AS sql_mode;
~~~

Each value has a distinct meaning:

- `VERSION()` shows the MySQL version that the connection is using.
- `@@version_comment` describes the distribution or engine build.
- `@@hostname` and `@@port` help identify the server as advertised by the server itself.
- `DATABASE()` returns the current default database; the result may be `NULL` if no database has been selected.
- `USER()` shows the identity the client sent to the server.
- `CURRENT_USER()` shows the account MySQL actually uses for privilege checks.
- `@@autocommit` and `@@sql_mode` show two settings that directly affect how statements behave.

Do not rely solely on tab titles or connection profile names. Verify with a query, especially before `DROP`, `TRUNCATE`, `DELETE`, `UPDATE`, migrations, or structural changes.

## 3. Running Interactive Statements

After connecting with `mysql`, you can enter SQL directly:

~~~sql
SELECT DATABASE();

SHOW TABLES;

SELECT VERSION();
~~~

In the MySQL Command-Line Client, SQL statements normally end with a semicolon (`;`). If you press Enter before the statement is terminated, the client waits for the rest of the statement. The semicolon is the statement terminator in standard mode; simply starting a new line does not execute the statement on the server.

Some useful client commands:

| Client Command | Effect |
|---|---|
| `status` or `\s` | Display connection status and session information |
| `source file.sql` or `\. file.sql` | Read and execute statements from a file |
| `tee file.log` | Write a copy of client output to a file |
| `notee` | Stop recording output with `tee` |
| `delimiter //` | Change the statement terminator recognized by the client |
| `warnings` | Display warnings after statements |
| `nowarning` | Disable automatic warning display |
| `clear` or `\c` | Clear the partially entered statement |
| `quit` or `\q` | Exit the client |

These are commands of the MySQL Command-Line Client. Some IDEs offer similar features, but menu names and interactions differ.

### 3.1. Running a Statement from the Terminal

The `--execute` option (short form `-e`) sends a statement and exits:

~~~bash
mysql --login-path=practice --database=mysql_practice --execute="SELECT CURRENT_TIMESTAMP AS checked_at, DATABASE() AS db_name;"
~~~

You can run multiple statements in the same string, separated by semicolons:

~~~bash
mysql --login-path=practice --database=mysql_practice --execute="SHOW TABLES; SELECT COUNT(*) AS total_tables FROM information_schema.tables WHERE table_schema = DATABASE();"
~~~

This approach works well for quick checks or small steps in an automated script. For multi-statement workflows, SQL files are usually easier to read, review, and version-control.

### 3.2. Running Selected Statements in an SQL Editor

In MySQL Workbench or DBeaver:

1. Open the connection profile and verify host, database, and user.
2. Open an SQL Editor bound to that connection.
3. Write one or more SQL statements.
4. Highlight the statements to run or place the cursor inside a statement as supported by the tool.
5. Use Execute to send the statement to the server.
6. Read the result pane, status/error messages, execution time, and affected row count.

Distinguish between the button to run the current statement, run the selected text, and run the entire editor contents. If the editor contains multiple statements, choosing the wrong execution mode can run more operations than intended.

Workbench typically displays query results in a grid along with status messages and statement history. DBeaver also provides result tabs and data export features. Menu names or keyboard shortcuts may vary by version; confirm the selected SQL range before executing.

## 4. Organizing Statements into SQL Files

An `.sql` file preserves a sequence of operations so it can be reviewed, re-run, committed to Git, or shared with teammates.

Example practice directory structure:

~~~text
mysql-practice/
├── sql/
│   ├── 00-check-connection.sql
│   ├── 01-create-schema.sql
│   ├── 02-seed-data.sql
│   └── 03-verify-result.sql
├── logs/
│   └── .gitkeep
└── README.md
~~~

Files can be split by purpose:

- Environment and privilege verification file.
- Schema, table, index, and constraint creation file.
- Seed/sample data file.
- Practice query file.
- Result verification file.
- Corresponding migration or rollback files when the project uses a migration workflow.

You do not need to split every single statement into its own file. Group statements by a purpose that can be reviewed and executed independently.

### 4.1. Example Connection-Check File

Contents of `00-check-connection.sql`:

~~~sql
-- Verify the connection before running data-modifying operations.
SELECT
    CURRENT_TIMESTAMP AS checked_at,
    VERSION() AS server_version,
    DATABASE() AS database_name,
    CURRENT_USER() AS privilege_identity;

SHOW ENGINES;
SHOW GRANTS;
~~~

Run the file inside a `mysql` session:

~~~text
source C:/lab/mysql-practice/sql/00-check-connection.sql
~~~

Using forward slashes in file paths is generally convenient with the MySQL client on Windows. Replace the path with the actual file location on your machine.

### 4.2. Example Re-Runnable Script

Create `01-practice.sql` with the following contents:

~~~sql
-- Save the file as UTF-8 to preserve Unicode characters.
CREATE DATABASE IF NOT EXISTS mysql_practice;
USE mysql_practice;

CREATE TABLE IF NOT EXISTS practice_item (
    item_id INT UNSIGNED NOT NULL,
    item_name VARCHAR(100) NOT NULL,
    quantity INT UNSIGNED NOT NULL,
    updated_at TIMESTAMP NOT NULL
        DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (item_id)
) ENGINE = InnoDB;

-- Reset data to its initial state so the exercise can be re-run.
INSERT INTO practice_item (item_id, item_name, quantity)
VALUES (1, 'Keyboard', 10)
ON DUPLICATE KEY UPDATE
    item_name = 'Keyboard',
    quantity = 10;

-- Test a change inside a transaction and then roll it back.
START TRANSACTION;

UPDATE practice_item
SET quantity = quantity - 1
WHERE item_id = 1 AND quantity > 0;

SELECT ROW_COUNT() AS affected_rows;

SELECT item_id, item_name, quantity
FROM practice_item
WHERE item_id = 1;

ROLLBACK;

-- Confirm data after ROLLBACK remains in its initial state.
SELECT item_id, item_name, quantity, updated_at
FROM practice_item
ORDER BY item_id;
~~~

This script illustrates several points:

- `CREATE DATABASE IF NOT EXISTS` and `CREATE TABLE IF NOT EXISTS` avoid creation errors when objects already exist.
- `INSERT ... ON DUPLICATE KEY UPDATE` resets the sample row to deterministic values, ensuring consistent results when re-running the exercise.
- `START TRANSACTION` opens a transaction for data manipulation.
- `ROW_COUNT()` returns the number of rows affected by the immediately preceding statement.
- `ROLLBACK` undoes the data changes inside the transaction.
- The final query shows that quantity is still 10.

Note: creating a database or creating a table are DDL operations. In MySQL, many DDL statements cause an implicit commit, so do not assume that wrapping an entire file in `START TRANSACTION` makes all structural operations rollbackable. The example above creates the database/table first and only then starts a transaction for data changes.

The script requires privileges to create databases and tables. If your practice account lacks those privileges, an administrator can pre-create the schema/table and grant the necessary privileges; in that case, remove the object-creation statements from the file.

### 4.3. Running a File with the source Command

Connect to the database:

~~~bash
mysql --login-path=practice --database=mysql_practice
~~~

Then run inside the MySQL client:

~~~text
source C:/lab/mysql-practice/sql/01-practice.sql
~~~

The client reads the file contents and executes statements sequentially. If an error occurs, inspect the error message and line number to locate the failing statement. After fixing the file, re-run it and verify the data state.

### 4.4. Running a File via Input Redirection

In Windows Command Prompt, Git Bash, or a Unix-style shell, you can pipe file contents into the client's stdin:

~~~bash
mysql --login-path=practice --database=mysql_practice --table --verbose --show-warnings < C:/lab/mysql-practice/sql/01-practice.sql
~~~

Meaning of options:

- `--table` formats results in tabular form.
- `--verbose` prints the statements executed by the client, useful when logging.
- `--show-warnings` displays warnings after statements when present.
- `<` redirects file contents as input to the client.

If you want to capture both stdout and stderr into a log in CMD or a compatible shell:

~~~bash
mysql --login-path=practice --database=mysql_practice --table --verbose --show-warnings < C:/lab/mysql-practice/sql/01-practice.sql > C:/lab/mysql-practice/logs/run-01.log 2>&1
~~~

PowerShell has its own redirection and native process handling rules. If using PowerShell, you can open the MySQL client and run `source`, or invoke redirection syntax inside `cmd.exe`/Git Bash. Avoid using an untested redirection command for production workflows.

## 5. Running Scripts with Procedures, Functions, or Triggers

Routines often contain multiple semicolons inside their body. If the client treats the first semicolon as the end of the statement, the remainder will be sent prematurely or fail with a syntax error.

The MySQL Command-Line Client provides the `DELIMITER` command to change the terminator recognized by the client. Example:

~~~sql
DELIMITER //

CREATE PROCEDURE show_practice_time()
BEGIN
    SELECT CURRENT_TIMESTAMP AS practice_time;
    SELECT DATABASE() AS database_name;
END//

DELIMITER ;
~~~

In this example:

- `DELIMITER //` instructs the client to wait until `//` before sending the complete procedure definition.
- Semicolons inside `BEGIN ... END` are preserved as SQL statement terminators inside the routine.
- `DELIMITER ;` restores the client's default terminator.

`DELIMITER` is a client directive, not an SQL statement sent to MySQL Server. Therefore, when executing scripts via a JDBC library or application driver, you cannot assume you can send `DELIMITER` directives verbatim to the server. The program must send the routine definition as a single statement supported by its API/driver.

Workbench also supports delimiters in SQL scripts. For other tools, verify how they parse routines and multi-line statements before running them.

## 6. Choosing Output Formats and Logging

Results should be stored according to their intended use. Logs for human readers should be readable; data for automated processing needs a stable structure.

### 6.1. Readable Results in the Terminal

By default, the MySQL client typically displays query results in tabular format. You can explicitly request table formatting with `--table`:

~~~bash
mysql --login-path=practice --database=mysql_practice --table --execute="SELECT item_id, item_name, quantity FROM practice_item ORDER BY item_id;"
~~~

This format is suitable for direct inspection or attaching logs to practice reports.

### 6.2. Batch Format for Automated Processing

The `--batch` option outputs tab-separated results suitable for some processing scripts:

~~~bash
mysql --login-path=practice --database=mysql_practice --batch --skip-column-names --execute="SELECT item_id, item_name, quantity FROM practice_item ORDER BY item_id;"
~~~

`--skip-column-names` omits the header row. The `--raw` option disables certain escaping mechanisms in batch output. Use these only when the consuming program knows how to handle tabs, newlines, and special characters; do not assume this output is valid CSV.

If you need CSV or XLSX for analysis, use the export feature in Workbench/DBeaver or an export tool with clear quoting and encoding rules. Do not rename a TSV file to CSV and assume columns are properly CSV-escaped.

### 6.3. Recording a Session with tee

In the MySQL Command-Line Client:

~~~text
tee C:/lab/mysql-practice/logs/practice-session.log
source C:/lab/mysql-practice/sql/01-practice.sql
notee
~~~

The `tee` command writes a copy of client output to a file. Use `notee` to stop recording. You can enable `tee` before running a script to preserve output and messages from the practice session.

Logs may contain query result data, table names, environment metadata, or sensitive values. Do not include passwords in commands, avoid putting personal data or secrets into logs unnecessarily, and review logs before sharing or committing.

### 6.4. Exporting Results from Workbench or DBeaver

When a query returns a result grid:

1. Check that the query includes `ORDER BY` if row order matters.
2. Verify that the row count and columns match expectations.
3. Use the tool's Export feature to choose CSV, JSON, SQL, or another supported format.
4. Select the appropriate encoding, typically UTF-8.
5. Save the file to the practice results directory or agreed artifact location.
6. Re-open the exported file to verify Unicode characters, delimiters, column headers, and row counts.

Do not rely solely on screenshots when you need to compare multi-row datasets. Screenshots are helpful for illustrating UI state or messages, whereas structured export files are far better suited for verification and analysis.

## 7. Verifying Results and Handling Errors

A statement that finishes without an error does not necessarily satisfy business requirements. After execution, verify the actual data and state.

### 7.1. Checking Affected Row Counts

After an `INSERT`, `UPDATE`, or `DELETE` statement, you can inspect the affected row count with:

~~~sql
SELECT ROW_COUNT() AS affected_rows;
~~~

Run this immediately after the statement being checked, because subsequent statements can overwrite the previous status value. Affected rows are not always equal to matched rows; for example, an `UPDATE` setting a column to its existing value may report zero affected rows.

For `INSERT` statements using an auto-increment column, you can read the generated value on the same connection:

~~~sql
SELECT LAST_INSERT_ID() AS generated_id;
~~~

Do not use `LAST_INSERT_ID()` from a different connection to infer the ID generated by the current operation.

### 7.2. Checking Warnings

In the MySQL client, run immediately after the statement under investigation:

~~~sql
SHOW WARNINGS;
~~~

You can use `SHOW ERRORS` to view the most recent errors recorded by the server. These commands help detect cases where a statement executed but produced warnings—such as data being converted or truncated under the current SQL mode.

Do not ignore warnings merely because rows were written. Investigate the root cause and determine whether the warning is acceptable in the exercise or in a real application.

### 7.3. Common Errors

| Error Code | Situation | What to Check |
|---|---|---|
| 1045 | Access denied | Check user, password, allowed source host, and authentication mechanism |
| 1049 | Unknown database | Check database name and visibility privileges |
| 1064 | SQL syntax error | Check keywords, commas, quotes, delimiter, and version syntax |
| 1146 | Table doesn't exist | Check current database, table name, and script execution order |
| 2003 | Cannot connect to server | Check host, port, MySQL service, firewall, and network |
| 1205 | Lock wait timeout | Investigate lock-holding transactions, wait timeout, and access order |
| 1213 | Deadlock | Check contending transactions; applications need an appropriate retry strategy |

When encountering an error:

1. Save the exact error message and error code.
2. Identify the statement and line number in the file that caused the error.
3. Verify the connection, current database, and account.
4. Check schema, privileges, data types, constraints, and transaction state.
5. Fix the root cause and re-run only the necessary parts.
6. Verify the data after fixing; if the script may have run partially, do not blindly re-run it from the top.

In batch script runs, by default the client should stop on error so the operator knows the run did not complete. The `--force` option causes the client to continue despite SQL errors; use it only when there is a clear reason and a per-statement verification process after errors. For migrations or data-modifying scripts, continuing after an error can leave a half-applied state that is hard to recover from.

## 8. A Reproducible Practice Workflow

A solid practice run should document which environment it ran against, which script was used, and what the expected outcome was.

Recommended workflow:

1. **Prepare:** save the SQL file in the project directory, verify UTF-8 encoding, and read through the contents before running.
2. **Connect:** use the profile for the right environment; verify server version, host, database, and user.
3. **Check privileges:** run `SHOW GRANTS` and confirm the account has the required privileges.
4. **Dry run / test:** start with read-only queries or operations in a dedicated practice schema.
5. **Execute:** run the statement or SQL file; do not run the entire editor if only a subset is needed.
6. **Verify:** check affected row counts, post-operation data, warnings, transaction status, and expected outcomes.
7. **Log:** save output, error messages, and run metadata; strip secrets and sensitive data.
8. **Evaluate:** explicitly record PASS/FAIL, root cause, remediation, and next steps.
9. **Clean up:** delete practice data or schemas only when certain you are in the right environment and no longer need evidence.

### 8.1. Run Log Template

You can use the following Markdown template in a README or practice notebook:

~~~markdown
## Run: SQL Practice 01

- Timestamp:
- Operator:
- Environment: local / development / staging
- MySQL server version:
- Host and port (no secrets):
- Database:
- Account/role:
- Client and version:
- Script:
- Git commit or script version:
- Objective:
- Expected result:
- Actual result:
- Affected rows:
- Warnings/errors:
- Log or output file:
- Status: PASS / FAIL
- Notes and next steps:
~~~

Do not record passwords, access tokens, private keys, or secrets in the template. If logs need to be shared, mask sensitive data and confirm recipients are authorized to view it.

### 8.2. Why Use ORDER BY When Saving Results?

SQL does not guarantee row order if a query does not specify `ORDER BY`. Two runs of the same query may return rows in different orders due to changes in execution plans, indexes, or data.

For example, when saving a list of items sorted by ID:

~~~sql
SELECT item_id, item_name, quantity
FROM practice_item
ORDER BY item_id;
~~~

If results are used to compare across runs, fix the sort order and filter criteria. When comparing data that may change over time, record the timestamp, filters, and appropriate snapshot or transaction context.

## 9. Storing Scripts and Results in Git

SQL is source code for data operations, so it can be reviewed and version-controlled just like other code files.

Should be committed to Git:

- Reviewed SQL files with a clear purpose.
- A README explaining execution order, privilege requirements, and expected outcomes.
- Synthetic sample data containing no real customer data.
- Sample logs or outputs stripped of sensitive information if needed for documentation.

Should NOT be committed to Git:

- Passwords, tokens, private keys, and configuration files containing secrets.
- Production data dumps not authorized for sharing.
- Logs containing personal data, account details, or sensitive contents.
- Large export files or auto-generated data unnecessary for the lesson.

Once scripts are used to modify shared environments, establish clear migration, review, and rollback procedures. Do not arbitrarily edit a migration file that has already been applied in another environment; create a new migration to record subsequent changes. Before running a migration in production, assess impact, backup/restore readiness, table-lock duration, and the recovery plan.

## 10. Pre- and Post-Execution SQL Checklist

**Before running**

- [ ] Verified host, port, server version, and database.
- [ ] Verified user/role and required privileges.
- [ ] Checked that the correct editor tab or script file is selected.
- [ ] Read statements that can modify or delete data.
- [ ] Identified transactions, implicit commits, and rollback behavior.
- [ ] Protected passwords and authentication credentials.
- [ ] Determined where logs and results will be saved.

**After running**

- [ ] Checked error messages and warnings.
- [ ] Verified affected row counts.
- [ ] Re-queried the data to verify results.
- [ ] Confirmed transactions were COMMITted or ROLLED BACK as expected.
- [ ] Saved scripts, logs, and necessary environment details.
- [ ] Removed secrets and sensitive data from shared artifacts.
- [ ] Recorded PASS/FAIL and root cause if failed.

## 11. Practice Exercises

### Exercise 1: Verify Connection

Connect to the practice database and run the identification query in Section 2.3. Record the server version, current database, privilege-checking account, and autocommit mode.

**Expected deliverable:** a record confirming the target server, database, and account.

### Exercise 2: Run an SQL File Twice

Save the script in Section 4.2 as `01-practice.sql`. Run the file twice and observe:

- Does the second run cause a duplicate database or table error?
- Is the sample row reset to `quantity = 10`?
- After the transaction and ROLLBACK, is `quantity` still `10`?
- How many updated rows does `ROW_COUNT()` report?

**Expected deliverable:** the SQL file, logs from both runs, and an explanation of the script's repeatability.

### Exercise 3: Trigger a Controlled Error Intentionally

In the practice schema, try querying a nonexistent table or misspelling a column name. Record the error code, error location, how you identified the cause, and the corrected statement.

Do not intentionally cause errors on a production database or a schema containing real data.

**Expected deliverable:** before/after fix logs and a successful verification query.

### Exercise 4: Export Ordered Results

Run a query listing items with `ORDER BY item_id`, export the results to CSV or TSV, and then open the file in a text editor or spreadsheet application.

**Expected deliverable:** a UTF-8 exported file with the right row count and no misaligned columns caused by delimiters.

## 12. Summary

Working effectively with MySQL requires more than typing SQL and seeing a result table. You must manage connection details, distinguish SQL from client commands, organize statements into reviewable and re-runnable scripts, know how to log output, inspect errors, and verify data state.

A reliable run must answer: **where it ran, under which account, which file or statement ran, what the actual outcome was, and how it can be reproduced**. When these details are recorded, practice results become auditable evidence and SQL workflows can be shared, reviewed, and automated.

## Official References

- [MySQL 8.4 Reference Manual – mysql, the MySQL Command-Line Client](https://dev.mysql.com/doc/refman/8.4/en/mysql.html)
- [MySQL 8.4 Reference Manual – mysql client commands](https://dev.mysql.com/doc/refman/8.4/en/mysql-commands.html)
- [MySQL 8.4 Reference Manual – Executing SQL Statements from a Text File](https://dev.mysql.com/doc/refman/8.4/en/batch-mode.html)
- [MySQL 8.4 Reference Manual – mysql_config_editor](https://dev.mysql.com/doc/refman/8.4/en/mysql-config-editor.html)
- [MySQL 8.4 Reference Manual – mysql client options](https://dev.mysql.com/doc/refman/8.4/en/mysql-command-options.html)
- [MySQL Workbench Manual](https://dev.mysql.com/doc/workbench/en/)
- [MySQL Shell User Guide](https://dev.mysql.com/doc/mysql-shell/8.4/en/)
