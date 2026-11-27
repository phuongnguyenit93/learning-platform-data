# Executing Statements and Scripts with SQL*Plus, SQLcl, and SQL Developer

When working with **Oracle Database**, developers and administrators do more than just write SQL statements. They also need to know **how to route statements to the right database/schema, execute one or more statements in the proper order, inspect results, manage transactions, and save logs** so work can be reproduced in other environments.

Oracle provides three common tools for these tasks:

- **SQL*Plus**: Oracle's traditional command-line interface, widely used in administration scripts, deployments, and server environments.
- **SQLcl (SQL Developer Command Line)**: a more modern command-line tool, compatible with most common SQL*Plus scripting commands and equipped with additional formatting and data-export utilities.
- **Oracle SQL Developer**: a graphical application for creating connections, authoring SQL, viewing tabular results, and running scripts from the SQL Worksheet.

All three tools send SQL/PLSQL to Oracle Database for processing, but **how they submit commands, display output, and handle client-side commands are not identical**. This lesson walks through those operations directly using examples you can practice on a schema with table-creation privileges.

## 1. Distinguishing SQL, PL/SQL, and Tool Commands

Before opening any tool, distinguish these three layers of operations:

| Layer | Examples | Where It Executes |
|---|---|---|
| **SQL** | `SELECT`, `INSERT`, `UPDATE`, `DELETE`, `CREATE TABLE` | Received, parsed, optimized, and executed by Oracle Database |
| **PL/SQL** | `DECLARE ... BEGIN ... END;` blocks, procedures, functions | Oracle Database's PL/SQL engine |
| **Client/script commands** | `SET`, `SPOOL`, `PROMPT`, `DESCRIBE`, `@`, `CONNECT`, `VARIABLE` | Handled by SQL*Plus, SQLcl, or SQL Developer's script runner before/separately from SQL sent to the database |

Example:

```sql
-- SQL: executed by the database, returns one row.
SELECT 'Hello Oracle' AS message FROM dual;

-- Tool-side command: prints a message to the terminal/Script Output.
PROMPT Starting script execution
```

`PROMPT` is not a standard SQL statement sent to the SQL engine. If you send the string `PROMPT ...` over JDBC via `Statement.execute(...)`, the application will not support it the way SQL*Plus/SQLcl does when running that command. Conversely, a `SELECT` run in these tools is still executed by the same Oracle Database, so the returned data depends on the SQL, access privileges, and database state.

Processing flow diagram:

```text
User / .sql file
        |
        v
SQL*Plus / SQLcl / SQL Developer
        |  handles CONNECT, SET, PROMPT, SPOOL, @...
        |  sends SQL or PL/SQL
        v
Oracle Database (session, schema, transaction)
        |
        |  rows / ORA- errors / execution info
        v
Terminal / Results Grid / Script Output / log file
```

**Key takeaway:** a `.sql` file can contain SQL, PL/SQL, and tool scripting commands together. Not every line in the file can be executed directly over JDBC or by every other SQL client.

## 2. Preparing the Environment and Connection Details

To practice, you need:

1. A running Oracle Database accessible from the machine where the tool runs.
2. An Oracle account with a username/password; to run table-creation examples, the account needs table-creation privileges and quota on an appropriate tablespace.
3. At least one of the three tools installed and configured to be compatible with the database.
4. The **host**, **port**, and **service name** (or a preconfigured **TNS alias**).

Assumed example values used for the rest of the lesson:

| Property | Illustrative Value | Explanation |
|---|---|---|
| Host | `localhost` | Oracle running on the local machine; replace with the actual hostname/IP as needed |
| Port | `1521` | Common listener port, though a system may use a different port |
| Service name | `freepdb1` | Example PDB service name; not every Oracle system uses this name |
| Username | `lab_user` | Practice account provided by your environment |
| Password | Entered when prompted by the tool | Do not hardcode passwords into scripts or command lines saved in shell history |

For **Easy Connect**, the connection string typically has the form:

```text
//hostname:port/service_name
```

For example, `//localhost:1521/freepdb1`. The *service* name is advertised by the listener and database configuration; it cannot be guessed from the machine name. In a multitenant environment, connect to the proper **PDB** intended for the application rather than arbitrarily using the root container or administrative accounts.

A verification query after connecting:

```sql
SELECT USER AS connected_user,
       SYS_CONTEXT('USERENV', 'DB_NAME') AS database_name,
       SYS_CONTEXT('USERENV', 'CON_NAME') AS container_name
FROM dual;
```

The `USER` value indicates the current schema/session user; the context values help avoid running scripts on the wrong database or PDB. `CURRENT_SCHEMA` can be changed separately via `ALTER SESSION SET CURRENT_SCHEMA = ...`, so the logged-in user and the schema used for object name resolution are not necessarily always the same.

## 3. SQL*Plus: Working Directly in the Terminal

**SQL*Plus** is the lightweight choice when working in a terminal, accessing a server over SSH, running automated scripts, or maintaining a system that uses traditional `.sql` files.

### 3.1 Launching the Program and Connecting

From a terminal where the `sqlplus` executable is available:

```text
sqlplus /nolog
```

The `/nolog` argument starts SQL*Plus **without logging into a database yet**. At the `SQL>` prompt:

```sql
CONNECT lab_user@//localhost:1521/freepdb1
```

The tool prompts for the password when needed. Once logged in successfully, try:

```sql
SHOW USER
SELECT 1 + 2 AS result FROM dual;
```

When finished:

```text
EXIT
```

SQL*Plus also supports aliases from `tnsnames.ora` or an appropriate Oracle Net configuration, such as `CONNECT lab_user@MYDB`; the name `MYDB` must actually exist in the client machine's configuration. To avoid exposing credentials, do not put passwords directly in `CONNECT user/password@...` in documentation, terminal history, CI logs, or version-controlled files.

### 3.2 Adjusting How Results Are Displayed

Some commonly used commands:

```sql
SET LINESIZE 160
SET PAGESIZE 100
SET FEEDBACK ON
SET TIMING ON
SET SERVEROUTPUT ON

SELECT SYSDATE AS current_date FROM dual;
```

| Command | Purpose |
|---|---|
| `SET LINESIZE n` | Sets the width of a text output line |
| `SET PAGESIZE n` | Controls the number of lines per page and header/page formatting output |
| `SET FEEDBACK ON` | Displays messages such as the number of rows selected or affected |
| `SET TIMING ON` | Displays execution time measured by the tool |
| `SET SERVEROUTPUT ON` | Displays output written by `DBMS_OUTPUT.PUT_LINE` in PL/SQL |
| `DESCRIBE object_name` or `DESC object_name` | Inspects the column/parameter structure of supported objects |
| `SHOW USER` | Displays the currently connected Oracle user |
| `SPOOL file_name` / `SPOOL OFF` | Starts/stops writing output to a file on the client machine |

`SET` settings are **client/tool-session settings** (and may trigger output-collection behavior); do not confuse them with SQL `ALTER SESSION` statements sent directly to the database.

## 4. SQLcl: SQL*Plus-Compatible CLI with Extra Utilities

**SQLcl** is the command-line tool in the Oracle SQL Developer suite. Depending on the installation, the executable is typically named `sql` (on Windows, `sql.exe`).

Launch SQLcl without connecting yet:

```text
sql /nolog
```

Then log in using the same workflow as SQL*Plus:

```sql
CONNECT lab_user@//localhost:1521/freepdb1
SHOW USER
SELECT 'SQLcl connected' AS message FROM dual;
```

Commands such as `@`, `@@`, `START`, `SPOOL`, `SET SERVEROUTPUT ON`, `VARIABLE`, and many familiar SQL*Plus script commands are also available in SQLcl. However, SQLcl and SQL*Plus are two different clients; some advanced commands or formatting modes exist only in SQLcl, and support levels may vary by version.

One visible convenience is exporting results as CSV:

```sql
SET SQLFORMAT CSV
SELECT 101 AS order_id, 'PAID' AS status FROM dual;
SET SQLFORMAT DEFAULT
```

`SET SQLFORMAT CSV` is a SQLcl feature. Do not copy this line into SQL*Plus expecting identical behavior. With real data, pay attention to escaping, delimiters, encoding, and NLS settings when exporting files for another system.

SQLcl is well suited when you want to keep a SQL*Plus-like scripting style while gaining a modern terminal experience, result-formatting utilities, and CLI workflows. You do not need to rewrite all existing scripts just because you switch clients; distinguish which commands are standard SQL and which belong to the tool's scripting command set.

## 5. Oracle SQL Developer: Executing via SQL Worksheet

**SQL Developer** provides a graphical interface to connect, write statements with syntax suggestions, browse table structures, and work with grid results.

### 5.1 Creating a Connection

In the **Connections** pane, create a new connection and enter the illustrative fields:

| UI Field | Example Value |
|---|---|
| Connection Name | `Local Lab` (a label for the user to identify it) |
| Username | `lab_user` |
| Password | Enter according to your actual account |
| Connection Type | `Basic` or the type appropriate for your environment |
| Hostname | `localhost` |
| Port | `1521` |
| Service name | `freepdb1` |

Click **Test** to verify the connection, then **Connect**. Only choose to save the password if your environment and security policies permit it. If an enterprise service uses a wallet/TNS/SSL, follow the connection configuration provided by your system instead of forcing a Basic connection.

Open the **SQL Worksheet** for the newly created connection and enter:

```sql
SELECT USER AS connected_user FROM dual;
```

### 5.2 Two Easily Confused Run Modes: Run Statement and Run Script

In the SQL Worksheet, two common actions are:

| Feature | Common Default Shortcut | Purpose | Typical Output Window |
|---|---|---|---|
| **Run Statement** | `F9` | Runs the statement at the cursor or the selected text | Tabular **Query Result / Results** when running `SELECT` |
| **Run Script** | `F5` | Sequentially executes the worksheet/script contents in script mode | Text-based **Script Output**, including messages and supported script commands |

Shortcuts can be customized under Preferences/Key Bindings. Action names and toolbar icons are more reliable identifiers if your system has remapped shortcuts.

Example with two statements entered:

```sql
SELECT 'first' AS stage FROM dual;
SELECT 'second' AS stage FROM dual;
```

- Placing the cursor on the first statement and choosing **Run Statement**: typically runs the statement selected/identified at the cursor; results appear in a grid convenient for filtering, sorting, and viewing many columns.
- Choosing **Run Script**: runs the content as a script, sending both result sets and messages to **Script Output**.

**When learning or running files containing `PROMPT`, `SET`, `@`, PL/SQL, and multiple consecutive SQL statements, prefer `Run Script` (F5)**. `Run Statement` is optimized for quickly testing a single SQL/PLSQL statement and inspecting its results; it does not fully replace a script command interpreter.

### 5.3 Viewing `DBMS_OUTPUT` in SQL Developer

A PL/SQL block can write messages using:

```sql
BEGIN
    DBMS_OUTPUT.PUT_LINE('Hello from Oracle');
END;
/
```

With **Run Script (F5)**, add `SET SERVEROUTPUT ON` before the block to instruct the script runner to display `DBMS_OUTPUT`:

```sql
SET SERVEROUTPUT ON
BEGIN
    DBMS_OUTPUT.PUT_LINE('Executed PL/SQL');
END;
/
```

If using **Run Statement (F9)**, you can open the **DBMS Output** panel, enable output polling for the right connection, and then run the PL/SQL block. Simply calling `DBMS_OUTPUT.PUT_LINE` does not automatically print text into the **Query Result** grid. In Oracle, output is stored in a buffer and fetched/displayed by the client when configured appropriately; it is not a real-time log-streaming mechanism.

## 6. Semicolons `;`, Forward Slashes `/`, and the Statement Buffer

This is one of the most common sources of errors when running SQL from files.

### 6.1 Standard SQL Typically Ends with `;`

```sql
SELECT 10 * 3 AS total FROM dual;
```

In SQL*Plus and SQLcl, a trailing `;` on a SQL statement normally tells the client to terminate and submit the SQL statement for execution. This delimiter itself is not part of the SQL syntax forwarded verbatim as an operation inside the database.

### 6.2 PL/SQL Blocks: `;` Inside and `/` on Its Own Line

```sql
BEGIN
    DBMS_OUTPUT.PUT_LINE('Hello from PL/SQL');
END;
/
```

`END;` syntactically terminates the PL/SQL block, while `/` **alone on a new line** instructs the tool to execute the PL/SQL code accumulated in the buffer. This is especially important for scripts that create procedures, functions, packages, triggers, or anonymous PL/SQL blocks. Do not add `;` after `/`.

Example creating a procedure:

```sql
CREATE OR REPLACE PROCEDURE lab_say_hello AS
BEGIN
    DBMS_OUTPUT.PUT_LINE('Hello from stored procedure');
END;
/

SET SERVEROUTPUT ON
BEGIN
    lab_say_hello;
END;
/
```

Creating a procedure via DDL may succeed in creating the object while still reporting compilation errors; use `SHOW ERRORS` in a supporting client or inspect object status/errors in SQL Developer to diagnose them.

### 6.3 Avoiding Running a SQL Statement Twice

In SQL*Plus and SQLcl, `/` on its own line can also **re-execute the SQL statement currently in the buffer**. Because of that, the following snippet can easily run `SELECT` twice:

```sql
SELECT 'once or twice?' AS message FROM dual;
/
```

For a standalone SQL statement, `;` alone is usually enough. For a PL/SQL block in a script, use `END;` and `/` as shown above. Do not habitually place `/` after every SQL statement, especially after `INSERT`, `UPDATE`, or `DELETE`: repeating DML can modify data multiple times or trigger unique-key errors.

## 7. Practicing SQL, DML, and Transactions

The examples below use a dedicated practice table. Run them with `Run Script` in SQL Developer or enter the corresponding commands in SQL*Plus/SQLcl.

### 7.1 Creating the Practice Table

```sql
CREATE TABLE lab_execution_log (
    log_id     NUMBER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    event_name VARCHAR2(100) NOT NULL,
    created_at TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL
);
```

This is a DDL statement. It modifies the schema structure, and **Oracle performs implicit commits around DDL**. Therefore, do not treat `ROLLBACK` as a way to undo a `CREATE TABLE` that has already succeeded. Create this table **only once**; running it again will produce a duplicate-object-name error if the table still exists.

If you lack `CREATE TABLE` privilege or adequate quota, use a pre-provisioned lab table rather than switching to `SYS` to bypass permission errors.

### 7.2 Inserting, Reading, and Committing Data

```sql
INSERT INTO lab_execution_log (event_name)
VALUES ('first run');

SELECT log_id,
       event_name,
       TO_CHAR(created_at, 'YYYY-MM-DD HH24:MI:SS') AS created_at_text
FROM lab_execution_log
ORDER BY log_id;

COMMIT;
```

`INSERT` modifies data within the current transaction. `COMMIT` confirms the uncommitted changes of that transaction. This example demonstrates interactive execution; in real applications, `COMMIT` boundaries must align with a complete business operation.

### 7.3 Testing `ROLLBACK` Safely

```sql
INSERT INTO lab_execution_log (event_name)
VALUES ('temporary row');

SELECT event_name FROM lab_execution_log
WHERE event_name = 'temporary row';

ROLLBACK;

SELECT event_name FROM lab_execution_log
WHERE event_name = 'temporary row';
```

Assuming no matching row existed beforehand, the query before `ROLLBACK` sees the row inserted by the same session; the query after no longer sees the rolled-back row. Note that `ROLLBACK` undoes **all uncommitted changes in the session's current transaction**, not just the immediately preceding `INSERT`. Do not run rollback exercises in a session containing real unsaved work.

### 7.4 Autocommit: Never Assume

In standard SQL*Plus/SQLcl workflows, you can set it explicitly:

```sql
SET AUTOCOMMIT OFF
```

SQL Developer has an autocommit option per connection/Preferences as well as **Commit** and **Rollback** buttons. Verify your current setting rather than guessing simply because an `INSERT` reported success. Data may appear immediately in the active session while remaining invisible to other sessions until `COMMIT`, depending on isolation level and transaction state. Certain application exit actions or client exit commands may have their own commit/rollback behavior, so scripts should establish explicit commit boundaries.

## 8. Running an Entire `.sql` File in SQL*Plus and SQLcl

Instead of typing manually, save SQL into a UTF-8 text file, for example `report.sql`:

```sql
-- report.sql
SET PAGESIZE 100
SET LINESIZE 160
PROMPT === REPORT: LAB EXECUTION LOG ===

SELECT log_id, event_name
FROM lab_execution_log
ORDER BY log_id DESC
FETCH FIRST 10 ROWS ONLY;

PROMPT === END REPORT ===
```

In a connected SQL*Plus or SQLcl session:

```sql
@report.sql
```

Or:

```sql
START report.sql
```

These commands tell the client to open the file, read its commands, and execute them sequentially. If the file is not in the current working directory or a location the client searches, provide the full path:

```sql
@C:\lab\sql\report.sql
```

The path is a path **on the machine running the client**, not a directory on the Oracle Database server (unless both machines happen to be the same). When working over SSH, the script resides on the machine where the SQL*Plus/SQLcl process runs. When running SQL Developer installed on a laptop, `@...` paths are resolved by the tool on the laptop.

Spaces, quotation marks, and relative paths may require different quoting rules depending on the client/version. For automation, use verified paths and a consistent working-directory convention.

### 8.1 `@` vs. `@@` When Calling Subscripts

Example file layout:

```text
C:\lab\sql\
  main.sql
  01_setup.sql
  02_insert.sql
  03_report.sql
```

In `main.sql`:

```sql
PROMPT Running lab script suite
@@01_setup.sql
@@02_insert.sql
@@03_report.sql
PROMPT Completed
```

In SQL*Plus/SQLcl, `@@` is used when a running script calls another script **relative to the calling script's location**, which is especially useful for subscripts stored in the same directory. `@` or `START` calls a script using the client's current path/search rules. Choosing `@@` for interdependent files makes a script bundle easier to move across directories, though you should still verify paths when switching platforms or clients.

SQL Developer supports executing many compatible script commands via **Run Script (F5)**; when using `@`/`@@`, verify behavior for your SQL Developer version and local paths if results differ from the terminal. **Run Statement (F9)** is not the right place to invoke a chain of `@` commands like a script runner.

## 9. Using Variables in Scripts: `&`, `ACCEPT`, and Bind Variables

Variables let you reuse one file with different parameters without editing SQL by hand. However, **substitution variables** and **bind variables** differ in mechanism and safety.

### 9.1 Substitution Variables: Text Replacement Before Sending SQL

Example `report_from_id.sql`:

```sql
SET VERIFY OFF
PROMPT Report from log_id = &1

SELECT log_id, event_name
FROM lab_execution_log
WHERE log_id >= &1
ORDER BY log_id;
```

In SQL*Plus/SQLcl, invoke:

```sql
@report_from_id.sql 10
```

The argument `10` is substituted for positional `&1`. If `&variable_name` is used without an assigned value, the client may prompt the user for input. `SET VERIFY OFF` only suppresses printing the before/after substitution text; it does not turn substitution into binding.

You can declare a simple value:

```sql
DEFINE min_log_id = 10

SELECT log_id, event_name
FROM lab_execution_log
WHERE log_id >= &min_log_id;

UNDEFINE min_log_id
```

**Important to remember:** `&min_log_id` performs **client-side text substitution** before sending the SQL. Taking untrusted user input and splicing it directly into SQL can introduce syntax errors or SQL injection risks. In addition, strings containing single quotes, `&` characters, or date formats can break substitution. Use substitution for trusted script parameters with controlled formatting; for user-supplied data in applications, prefer bind variables.

### 9.2 `ACCEPT`: Prompting for a Typed Parameter

SQL*Plus and SQLcl support interactive prompting:

```sql
ACCEPT p_min_id NUMBER PROMPT 'Enter minimum log_id: '

SELECT log_id, event_name
FROM lab_execution_log
WHERE log_id >= &p_min_id;

UNDEFINE p_min_id
```

Declaring `NUMBER` provides basic input-format validation in interactive scripts. However, `ACCEPT` still injects the value via substitution rather than **binding**; do not use it as a substitute for parameterized Java/JDBC APIs when handling untrusted data.

### 9.3 Bind Variables: Passing Values via `:name`

Example for SQL*Plus/SQLcl and SQL Developer's script runner supporting `VARIABLE` syntax:

```sql
VARIABLE p_event VARCHAR2(100)

BEGIN
    :p_event := 'script executed';
END;
/

INSERT INTO lab_execution_log (event_name)
VALUES (:p_event);

PRINT p_event
ROLLBACK;
```

`VARIABLE` creates a client-side variable, while `:p_event` is a bind reference inside SQL/PLSQL. Binding lets the database receive values separately from the SQL statement structure, supporting statement reuse and avoiding building SQL through direct data concatenation. `PRINT` is a client command for displaying the variable, not SQL.

When writing Java programs connecting to Oracle, this principle corresponds to `PreparedStatement` and `?` placeholders, even though JDBC's parameter-binding API differs from `VARIABLE` syntax in SQL*Plus/SQLcl.

**Note:** prompting behavior for bind/substitution variables can differ between **Run Statement** and **Run Script** in SQL Developer. A script using `VARIABLE`, `PRINT`, `@`, and `PROMPT` should be tested in **F5** mode when you want command-line-compatible script behavior.

## 10. Writing Output to a File with `SPOOL`

When you need to log operations or save a report:

```sql
SET ECHO ON
SET FEEDBACK ON
SET TIMING ON
SET LINESIZE 160
SET PAGESIZE 100
SPOOL C:\lab\sql\run-output.log

PROMPT === START ===
SELECT USER AS connected_user FROM dual;
SELECT COUNT(*) AS total_rows FROM lab_execution_log;
PROMPT === FINISH ===

SPOOL OFF
```

`SPOOL` writes the tool-generated output to a file on the client machine. `SET ECHO ON` is useful when running script files because it logs each command read from the script; `SET TIMING ON` adds client-measured timing info. If you only want structured data exported for another machine to process, SQLcl can use CSV formatting or a dedicated export tool instead of treating a text spool log as clean CSV.

Differences among output channels:

| Channel | Purpose | Key Notes |
|---|---|---|
| Terminal output | Interactive monitoring in SQL*Plus/SQLcl | May include headers, feedback, timings, and messages |
| SQL Developer **Query Result** | Inspecting a single tabular result set | Convenient for viewing, sorting, and exporting data via GUI |
| SQL Developer **Script Output** | Viewing sequential multi-statement output and script messages | Suited for `PROMPT`, `SET`, and PL/SQL in F5 mode |
| `DBMS_OUTPUT` | Messages from PL/SQL | Requires client output collection enabled; not a centralized logger |
| `SPOOL` | Writing client output to a file | File paths and permissions apply on the machine running the tool |

Sensitive details such as passwords, tokens, or customer data can accidentally appear in logs if scripts echo commands or values. Store and share logs only with appropriate permissions; avoid turning on full echo in workflows handling sensitive data unless necessary.

## 11. Organizing a Repeatable Script Suite

To see the full workflow, suppose we create three adjacent files in `C:\lab\sql\` and run them only in a **practice schema**.

**File `01_setup.sql` — create the table, run once:**

```sql
PROMPT Creating lab table...

CREATE TABLE lab_script_run (
    run_id     NUMBER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    note       VARCHAR2(100) NOT NULL,
    created_at TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL
);
```

**File `02_execute.sql` — insert a row and inspect the results:**

```sql
PROMPT Inserting a row...

VARIABLE v_note VARCHAR2(100)
BEGIN
    :v_note := 'executed by script';
    DBMS_OUTPUT.PUT_LINE('Preparing insert');
END;
/

INSERT INTO lab_script_run(note) VALUES (:v_note);
COMMIT;

SELECT run_id,
       note,
       TO_CHAR(created_at, 'YYYY-MM-DD HH24:MI:SS') AS run_at
FROM lab_script_run
ORDER BY run_id DESC
FETCH FIRST 5 ROWS ONLY;
```

**File `main.sql` — orchestrator:**

```sql
SET SERVEROUTPUT ON
SET FEEDBACK ON
SET TIMING ON
SET ECHO ON

PROMPT ===== START LAB =====
@@01_setup.sql
@@02_execute.sql
PROMPT ===== END LAB =====
```

To run from the CLI, navigate to the directory containing the scripts, connect to the right service with SQL*Plus or SQLcl, and run:

```sql
@main.sql
```

In SQL Developer, open `main.sql` in an appropriate SQL Worksheet and choose **Run Script (F5)**; check how `@@` resolution behaves on your client/version.

On the first run, `01_setup.sql` creates the table and `02_execute.sql` inserts a row. **Subsequent runs will fail on table creation because the table already exists**. This highlights two distinct properties:

- *Schema setup* scripts typically require version tracking, applied-state checks, and a migration strategy rather than blindly re-running `CREATE`.
- *Data manipulation* scripts must decide whether repeated execution is allowed to insert new rows. When a business process requires idempotency, use appropriate business keys and conditional logic.

Do not automatically drop tables or use `DROP TABLE ... PURGE` just to make a script "re-runnable" when data needs to be preserved. In real environments, use controlled migrations and schema version management rather than embedding destructive logic in shared scripts.

## 12. Error Handling and Exit Codes for Automated Scripts

Interactive runs let you read errors on screen; CI/CD pipelines, batch jobs, or operational tasks need **exit codes** so subsequent steps know whether execution succeeded or failed.

SQL*Plus supports directives such as:

```sql
WHENEVER SQLERROR EXIT SQL.SQLCODE ROLLBACK
WHENEVER OSERROR EXIT FAILURE ROLLBACK
```

`WHENEVER SQLERROR` tells SQL*Plus to exit when a **SQL/PLSQL** error occurs (e.g., missing table, constraint violation, failing procedure); `WHENEVER OSERROR` handles supported OS/client errors. SQLcl also supports this style of script flow control within its compatibility scope. Exact syntax and the exit code returned to the calling environment should be verified against your specific version.

Example `batch_job.sql`, for **non-interactive execution** against existing objects:

```sql
SET ECHO ON
SET FEEDBACK ON
WHENEVER OSERROR EXIT FAILURE ROLLBACK
WHENEVER SQLERROR EXIT SQL.SQLCODE ROLLBACK

INSERT INTO lab_execution_log (event_name)
VALUES ('batch job');

COMMIT;
EXIT SUCCESS
```

If the `INSERT` fails, the script exits and rolls back uncommitted changes. If it succeeds, the script commits and returns a success status. The job invoking SQL*Plus/SQLcl should check both the exit code **and** the execution log.

Important note: `WHENEVER SQLERROR` **does not guarantee catching every client-command syntax error**, such as a nonexistent `SET` option or certain `SP2-...` errors; it is not a universal exception handler for the entire scripting language. Likewise, do not place `EXIT SUCCESS` inside an interactive session containing unsaved work. Any DDL statement that succeeded before a subsequent SQL error will have already performed an implicit commit, so rolling back on exit cannot restore the schema to its pre-DDL state.

With the SQL Developer GUI, errors appear in Results/Script Output and do not provide the same exit-code model for shell jobs. When automation requires exit-code monitoring, prefer a suitable CLI tool.

## 13. Common Errors When Using the Three Tools

| Symptom/Error | Common Cause | How to Check/Resolve |
|---|---|---|
| `ORA-01017: invalid username/password` | Incorrect credentials or authentication method | Check username, password, service, and auth configuration; do not print passwords to logs |
| `ORA-12154` | Connect identifier/TNS alias could not be resolved | Verify Easy Connect string, `tnsnames.ora`, environment variables/Oracle Net config |
| `ORA-12514` | Listener does not know the requested service | Confirm host/port/service name and service status with the administrator |
| `ORA-00942` | Table/view does not exist in the resolved schema or missing access privilege | Check `USER`, schema, object name, and granted privileges |
| `ORA-01031` | Insufficient privileges for the operation | Use an account/privilege appropriate for the task; do not escalate to `SYSDBA` |
| `ORA-00001` | Unique constraint/index violation | Check the unique key and why a duplicate is being inserted; do not drop constraints to hide errors |
| `ORA-06550` with `PLS-...` | PL/SQL compilation or execution error | Read line/column info, check syntax, data types, and variable names |
| `SP2-0310: unable to open file` (SQL*Plus) | Script is not at a path readable by the client | Check working directory, path, file permissions; distinguish `@` vs. `@@` |
| Script runs but `DBMS_OUTPUT` is missing | Output collection/display is not enabled | Add `SET SERVEROUTPUT ON` in scripts; enable the DBMS Output panel for the right connection in GUI statement mode |
| PL/SQL does not run or seems incomplete | Missing `/` on its own line | End with `END;` and add `/` on the next line in scripts |
| An `INSERT` appears to execute twice | `;` followed by a misplaced `/` | Inspect the command buffer and remove extra `/` after standalone SQL statements |
| SQL Developer only runs one statement out of many | Using **Run Statement** instead of **Run Script** | Use F5 for a sequence of `.sql` commands |
| Data visible in one session but not another | Uncommitted DML or different transaction context | Check autocommit, `COMMIT`, isolation level, and active connection/schema |
| Date/time results differ from expectations | Implicit conversion depending on NLS | Use explicit conversion expressions such as `TO_DATE(..., 'YYYY-MM-DD')`, `TO_CHAR(..., 'YYYY-MM-DD HH24:MI:SS')` |

Exact error codes and messages may vary slightly across versions. Save the **complete error message**, including the offending SQL line and connection state, because an error code alone rarely explains the full cause.

## 14. Best Practices for Writing Oracle Scripts

1. **Specify the target environment.** Before running data-modification scripts, verify user, service/PDB, and schema. Avoid hitting identically named tables in the wrong environment.
2. **Use least-privilege accounts.** Do not run practice scripts as `SYS`/`SYSTEM` and do not grant broad privileges merely to bypass an access error.
3. **Separate read scripts, DML, and high-impact DDL.** Clearly mark what alters data and requires `COMMIT`; manage schemas via migrations across multiple environments.
4. **Set intentional transaction boundaries.** `COMMIT`/`ROLLBACK` should reflect business decisions; remember DDL performs implicit commits and clients have their own exit behaviors.
5. **Use bind variables for data values.** Never build application SQL by concatenating user strings or inserting unchecked substitution text.
6. **Use proper statement terminators.** `;` for regular SQL; PL/SQL blocks in scripts end with `END;` followed by `/` on its own line; avoid overusing `/` after DML.
7. **Format dates, numbers, and outputs explicitly.** Especially when moving data across environments with different NLS/locale settings; do not rely on Oracle implicitly parsing date strings.
8. **Keep scripts under version control with explicit ordering.** Name files such as `001_create_tables.sql`, `002_seed_data.sql`, `003_report.sql`, and document prerequisites before running.
9. **Inspect errors in context.** Batch jobs need exit codes, logs, and grouped error handling; do not assume a multi-line output screen proves every step succeeded.
10. **Protect sensitive information.** Never put passwords into `.sql` files, shell history, or outputs; configure log file permissions and review `SPOOL` output before sharing.

## 15. Practice Exercises

### Exercise 1: Same Query Across All Three Tools

Connect to the proper schema and run:

```sql
SELECT USER AS current_user,
       SYSTIMESTAMP AS database_timestamp
FROM dual;
```

Observe: SQL*Plus displays terminal text; SQLcl can switch output formats; SQL Developer **Run Statement** displays a grid, while **Run Script** prints to script output. Compare the logical results against the presentation format while confirming you are connected to the intended environment.

### Exercise 2: Running SQL and PL/SQL in One Script

Create a file `hello_oracle.sql`:

```sql
SET SERVEROUTPUT ON
PROMPT Start example

SELECT 2 * 5 AS arithmetic_result FROM dual;

BEGIN
    DBMS_OUTPUT.PUT_LINE('PL/SQL block completed');
END;
/

PROMPT End example
```

Run `@hello_oracle.sql` in SQL*Plus/SQLcl, then run the same content using F5 in SQL Developer. Identify which lines are returned by the database and which are generated by the client.

### Exercise 3: Verifying Transactions

In the practice schema where `lab_execution_log` was created, run:

```sql
INSERT INTO lab_execution_log(event_name)
VALUES ('rollback exercise');

SELECT COUNT(*) AS row_count
FROM lab_execution_log
WHERE event_name = 'rollback exercise';

ROLLBACK;

SELECT COUNT(*) AS row_count
FROM lab_execution_log
WHERE event_name = 'rollback exercise';
```

Compare both counts; if a row with the same name already existed, the count after `ROLLBACK` will not necessarily be 0. Retry with a uniquely distinguishable value, observe the current session vs. another session before committing, and record your conclusions on transaction visibility.

### Exercise 4: Parameters and Logging

Create a file `find_log.sql`:

```sql
SET FEEDBACK ON
PROMPT Looking up logs since id &1

SELECT log_id, event_name
FROM lab_execution_log
WHERE log_id >= &1
ORDER BY log_id;
```

Run `@find_log.sql 1` and then `@find_log.sql 100` in SQL*Plus/SQLcl. Afterward, use `SPOOL` to write the output to a file in a directory you manage. Explain why `&1` is a substitution variable and when you should switch to a bind variable.

## 16. Choosing the Right Tool for the Job

| Need | Suitable Tool | Main Reason |
|---|---|---|
| Typing Oracle commands in a terminal, over SSH, minimal environments | **SQL*Plus** | Lightweight, familiar, fits many existing operational scripts |
| Running scripts from terminal with formatting/export conveniences | **SQLcl** | Supports many SQL*Plus commands plus extended CLI utilities |
| Exploring schemas, testing queries, viewing interactive result sets | **SQL Developer – Run Statement** | Results grid and visual tools |
| Running sequences of SQL/PLSQL, `PROMPT`, `SET`, and scripts in GUI | **SQL Developer – Run Script** | Processes content as a script flow and displays Script Output |
| Automated deployments/batch jobs needing exit codes and logs | **SQL*Plus or SQLcl** | Easy CLI integration and conditional error handling |

The two most important principles to remember in practice are: **know which statements run in Oracle Database versus which commands are handled by the client; and know when you are running a single statement versus an entire script.** Once you master `F9`/`F5`, `;`/`/`, `@`/`@@`, bind/substitution variables, `COMMIT`/`ROLLBACK`, and `SPOOL`, you can move from ad-hoc SQL testing to writing repeatable, observable, and controllable Oracle workflows.
