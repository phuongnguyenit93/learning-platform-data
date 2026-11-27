# Executing SQL Files, psql Variables, and Error Handling in PostgreSQL Scripts

## 1. Why execute SQL from files?

When first learning PostgreSQL, you typically open `psql` and enter one SQL statement at a time. However, in real projects, creating schemas, loading initial data, running reports, or altering table structures can involve dozens or hundreds of statements. Saving these commands in `.sql` files makes the workflow **reproducible, reviewable, and automatable**.

For example, a database deployment may need to:

1. Create a schema if it does not yet exist.
2. Create tables and constraints.
3. Load sample data.
4. Check certain conditions and output a report.
5. Stop the entire workflow if a SQL error occurs.
6. Return a nonzero exit code so CI/CD knows the deployment failed.

`psql` is the PostgreSQL command-line tool capable of performing all of these steps. Beyond SQL, `psql` provides **meta-commands** (starting with `\`), **psql variables**, and error-control options.

```text
Terminal / CI
    |
    | psql -X -v ON_ERROR_STOP=1 -f main.sql
    v
+------------------------------------+
| psql (client)                      |
| - Reads SQL file                   |
| - Handles \i / \ir / \set / \if    |
| - Substitutes :name variables      |
| - Sends SQL statements to PostgreSQL|
| - Prints errors, returns exit code |
+------------------+-----------------+
                   |
                   | PostgreSQL protocol
                   v
+------------------------------------+
| PostgreSQL Server                  |
| - Checks syntax and privileges     |
| - Executes SQL / transactions      |
| - Enforces keys and constraints    |
+------------------------------------+
```

**Core point:** `\set`, `\echo`, and `\ir` are commands **processed by psql on the client**, not SQL syntax that can be sent verbatim to the server over JDBC.

## 2. Preparing PostgreSQL and psql

Check the client version in the terminal:

```bash
psql --version
```

Connect to the test database:

```bash
psql --host=localhost --port=5432 \
     --username=lab_user --dbname=lab_db
```

The values `localhost`, `lab_user`, and `lab_db` are examples. Replace them only with endpoints and accounts you are authorized to use; do not use a superuser account for tasks that do not require administrative privileges.

At the `psql` prompt, you can type:

```text
\conninfo
\dt
\?
\q
```

| Meta-command | Effect |
| --- | --- |
| `\conninfo` | Displays connection details |
| `\dt` | Lists tables matching the search path |
| `\d table_name` | Describes table structure |
| `\?` | Help for psql commands |
| `\h CREATE TABLE` | Help for SQL syntax |
| `\q` | Exits the psql session |

Two environments are easily confused:

- **Terminal:** run `psql -f setup.sql` or `psql -c "SELECT 1"`.
- **Inside psql:** type `\i setup.sql` or `SELECT 1;`.

If you see a prompt like `lab_db=>`, you are inside psql; if you see a Bash/PowerShell prompt, you are in the operating system shell.

## 3. Running a SQL file with `-f` / `--file`

Create a UTF-8 file `setup.sql`:

```sql
CREATE SCHEMA IF NOT EXISTS demo_psql;

CREATE TABLE IF NOT EXISTS demo_psql.products (
    product_id bigint PRIMARY KEY,
    product_name text NOT NULL,
    price numeric(12,2) NOT NULL CHECK (price >= 0)
);

INSERT INTO demo_psql.products
    (product_id, product_name, price)
VALUES
    (1, 'Notebook', 35000.00)
ON CONFLICT (product_id) DO NOTHING;
```

Execute from the terminal:

```bash
psql -h localhost -U lab_user -d lab_db -f setup.sql
```

Or:

```bash
psql --host=localhost \
     --username=lab_user \
     --dbname=lab_db \
     --file=setup.sql
```

`psql` reads the file sequentially, sends SQL statements to PostgreSQL, and processes any meta-commands included in the file. After running:

```sql
SELECT product_id, product_name, price
FROM demo_psql.products
ORDER BY product_id;
```

Sample output:

| product_id | product_name | price |
| ---: | --- | ---: |
| 1 | Notebook | 35000.00 |

**Note:** `IF NOT EXISTS` prevents errors when an object already exists, but it does not verify that the existing structure matches what you expect. `ON CONFLICT DO NOTHING` skips duplicate-key rows in the example; this is not a strategy applicable to every kind of data.

### 3.1. When to use `-c`?

Run a short SQL statement:

```bash
psql -h localhost -U lab_user -d lab_db \
  -c "SELECT current_database(), current_user;"
```

You can pass multiple `-c` flags for multiple commands:

```bash
psql -h localhost -U lab_user -d lab_db \
  -c "SELECT now();" \
  -c "SELECT current_database();"
```

A `-c` argument can represent a SQL string sent directly to the server or a suitable psql meta-command. Do not mix SQL and meta-commands inside the same `-c` string; use `-f` when you need a multi-step script. In particular, psql variable substitution in `-c` SQL strings differs from running a file; use `-f` to leverage `:name` cleanly inside SQL.

### 3.2. Running via standard input

```bash
psql -h localhost -U lab_user -d lab_db < setup.sql
```

This can also execute SQL, but `-f` is usually more convenient because error messages can include **filename and line number**, which helps when debugging long scripts.

## 4. Running multiple files: `\i` and `\ir`

Inside psql, you can include files:

```text
\i setup.sql
\ir steps/01_schema.sql
```

The two commands have an important difference:

| Meta-command | Purpose | How relative paths are resolved |
| --- | --- | --- |
| `\i` | Read and execute another file | Relative to **psql's current working directory** |
| `\ir` | Include relative | Relative to **the directory containing the currently executing script** |

Suppose:

```text
project/
└── sql/
    ├── main.sql
    └── steps/
        ├── 01_schema.sql
        ├── 02_seed.sql
        └── 03_report.sql
```

File `sql/main.sql`:

```sql
\set ON_ERROR_STOP on

\echo Starting PostgreSQL setup

\ir steps/01_schema.sql
\ir steps/02_seed.sql
\ir steps/03_report.sql

\echo Setup completed
```

When invoked:

```bash
psql -X -v ON_ERROR_STOP=1 \
  -h localhost -U lab_user -d lab_db \
  -f project/sql/main.sql
```

`\ir` finds the files under `project/sql/steps/` because it resolves relative to the location of `main.sql`, regardless of which directory the user is currently in inside the terminal.

If you used `\i steps/01_schema.sql`, psql would resolve it relative to the working directory; the same script could work on one machine and fail with a path error on another.

**Best practice:** use `\ir` for sub-files within the same script suite; use full paths or guarantee the working directory when `\i` is needed.

## 5. psql variables: creating and using them

A psql variable is a value managed within the **psql session** that can be substituted into SQL or meta-commands using `:var` syntax. They allow the same file to run with different parameters.

### 5.1. Passing variables from the command line with `-v`

```bash
psql -h localhost -U lab_user -d lab_db \
  -v target_schema=demo_lab \
  -v min_amount=100000 \
  -f report.sql
```

`-v` is short for `--set`. The variables `target_schema` and `min_amount` are set in the psql session before the script runs.

### 5.2. Setting variables inside psql with `\set`

```text
\set target_schema demo_lab
\set min_amount 100000
\echo Schema: :target_schema
```

Removing a variable:

```text
\unset min_amount
```

Calling `\set` without arguments lists all currently defined variables. Be careful if sensitive information was stored in variables: do not print the variable list to public logs.

### 5.3. Distinguishing psql variables from SQL parameters

| Concept | Where is it processed? | Example |
| --- | --- | --- |
| psql variable | On the `psql` client | `:target_schema`, `\set` |
| Prepared statement parameter | In the SQL/driver mechanism | `$1`, bind values |
| Server session setting | PostgreSQL backend | `SET search_path TO ...` |

A psql variable **is not a bind parameter** of a JDBC driver. A file using `:name` must be executed in an environment that processes psql variables; sending it verbatim through another SQL API can cause a syntax error.

## 6. Quoting variables properly: `:var`, `:'var'`, `:"var"`

This is the most common source of bugs when writing parameterized scripts.

| Syntax | Meaning | Use when |
| --- | --- | --- |
| `:name` | Inserts the variable value almost verbatim into SQL syntax | Only for trusted SQL fragments/values |
| `:'name'` | Quotes the variable as a **SQL string literal** | Text values or literals that need casting to another type |
| `:"name"` | Quotes the variable as a **SQL identifier** | Schema, table, or column names |

Example variables:

```text
\set target_schema demo_lab
\set customer_name 'Nguyễn An'
\set min_amount 150000
```

Text value:

```sql
SELECT :'customer_name' AS selected_customer;
```

Object name:

```sql
CREATE SCHEMA IF NOT EXISTS :"target_schema";
```

Numeric value quoted as a literal and cast:

```sql
SELECT order_id, amount
FROM demo_lab.orders
WHERE amount >= :'min_amount'::numeric;
```

**Do not wrap variables in quotes manually**:

```sql
-- Wrong idea: the text inside quotes is treated as a fixed literal.
SELECT ':customer_name';

-- Correct: psql generates a safely quoted SQL literal.
SELECT :'customer_name';
```

Similarly, `:'target_schema'` produces a **string literal**, not an identifier; a schema name must use `:"target_schema"`.

### 6.1. Risks of raw `:name` interpolation

```sql
-- Do not use with values taken directly from untrusted input.
SELECT * FROM demo_lab.orders WHERE amount >= :min_amount;
```

`psql` substitutes the variable content directly into the SQL syntax. If the variable contains unexpected non-numeric text, the query can fail or be altered unexpectedly. A safer and more strongly typed approach is:

```sql
SELECT *
FROM demo_lab.orders
WHERE amount >= :'min_amount'::numeric;
```

Quoting as a literal does not validate business rules on its own. If a user passes a value that cannot be cast to `numeric`, the server will raise an error.

### 6.2. Checking whether a variable exists

`psql` supports an expression to test whether a variable is defined:

```text
\if :{?target_schema}
  \echo Target schema was supplied
\else
  \echo Target schema is missing
\endif
```

`:{?target_schema}` only checks whether the variable has been defined, not whether its value belongs to an allowed list of schemas. When running scripts automatically, validate required settings in the calling shell and enable `ON_ERROR_STOP`.

## 7. Practice: using variables to choose a schema

File `01_schema.sql`:

```sql
CREATE SCHEMA IF NOT EXISTS :"target_schema";

CREATE TABLE IF NOT EXISTS :"target_schema".orders (
    order_id bigint PRIMARY KEY,
    customer_name text NOT NULL,
    amount numeric(12,2) NOT NULL CHECK (amount >= 0),
    created_at timestamptz NOT NULL DEFAULT now()
);
```

Run command:

```bash
psql -X -v ON_ERROR_STOP=1 \
  -v target_schema=demo_batch \
  -h localhost -U lab_user -d lab_db \
  -f 01_schema.sql
```

When `target_schema=demo_batch`, the command creates `demo_batch.orders`. The same script can be run with `target_schema=demo_test` to create another test schema.

**Note:** do not use a schema variable to dynamically select production objects when a user can pass arbitrary values. `:"name"` quotes the identifier safely at the syntax level, but deciding *which schema is allowed to be modified* remains a matter of privileges and business validation.

## 8. Loading data and passing filter parameters

File `02_seed.sql`:

```sql
INSERT INTO :"target_schema".orders
    (order_id, customer_name, amount)
VALUES
    (1, 'Nguyễn An', 120000.00),
    (2, 'Trần Bình', 250000.00),
    (3, 'Lê Chi', 80000.00)
ON CONFLICT (order_id) DO UPDATE
SET customer_name = EXCLUDED.customer_name,
    amount = EXCLUDED.amount;
```

The example uses `ON CONFLICT` so the sample seed file can be re-run without duplicate-key errors. In real systems, **overwriting existing data on conflict is a business decision** and should not be applied blindly to every migration.

File `03_report.sql`:

```sql
SELECT
    order_id,
    customer_name,
    amount
FROM :"target_schema".orders
WHERE amount >= :'min_amount'::numeric
ORDER BY amount DESC, order_id ASC;
```

Run with:

```bash
psql -X -v ON_ERROR_STOP=1 \
  -v target_schema=demo_batch \
  -v min_amount=100000 \
  -h localhost -U lab_user -d lab_db \
  -f 03_report.sql
```

Result on sample data:

| order_id | customer_name | amount |
| ---: | --- | ---: |
| 2 | Trần Bình | 250000.00 |
| 1 | Nguyễn An | 120000.00 |

Here the variable is converted into a SQL literal via `:'min_amount'`, and PostgreSQL casts it to `numeric`.

## 9. `\gset`: capturing a SQL row into psql variables

Not every variable has to come from terminal arguments. `psql` provides the `\gset` meta-command to take values from **a single result row** of a `SELECT` query and store them as psql variables.

```sql
SELECT
    COUNT(*) AS order_count,
    COALESCE(SUM(amount), 0)::numeric AS total_amount
FROM :"target_schema".orders
\gset

\echo Total orders: :order_count
\echo Total amount: :total_amount
```

This `SELECT` returns a single aggregate row, making it suitable for `\gset`.

Rules to remember:

- The query must return **exactly one row**. If it returns 0 rows or more than 1 row, psql cannot assign variables this way.
- The result column names become variable names.
- If a column value is SQL `NULL`, the corresponding variable may be unset.
- You can specify a prefix, e.g., `\gset stats_` to set `stats_order_count`.
- Variables created by `\gset` live only on the psql client side.

`\gset` is not `INSERT` and does not write results back into the database.

## 10. `\if`, `\elif`, `\else` in scripts

psql supports conditionals to decide whether to execute a section of a script:

```text
\set run_report true

\if :run_report
  \echo Running report
\else
  \echo Report skipped
\endif
```

Condition values should be clear booleans such as `true/false`, `on/off`, `yes/no`, or `1/0`.

**Do not treat `\if` as a SQL expression evaluator.** For example:

```text
-- Not valid SQL comparison syntax for psql to evaluate directly:
\if :order_count > 0
```

If you need a condition based on database data, use `SELECT` to compute it first:

```sql
SELECT CASE
         WHEN COUNT(*) > 0 THEN 'true'
         ELSE 'false'
       END AS has_orders
FROM :"target_schema".orders
\gset

\if :has_orders
  \echo Orders were found
\else
  \echo No orders found
\endif
```

When a condition guards **an important write operation**, consider SQL/transaction atomicity rather than "reading via psql and updating later" in separate unprotected steps.

## 11. The problem: a SQL error occurs, yet the script keeps running

By default, if `ON_ERROR_STOP` is not enabled, psql may print an error and **continue running subsequent SQL statements**. This is especially dangerous for migrations.

Example `bad_setup.sql`:

```sql
CREATE TABLE demo_psql.example_one (
    id integer PRIMARY KEY
);

-- Intentional error: table does not exist.
INSERT INTO demo_psql.no_such_table(id)
VALUES (1);

CREATE TABLE demo_psql.example_two (
    id integer PRIMARY KEY
);
```

In normal autocommit mode, what can happen is:

```text
Statement 1: CREATE example_one   → succeeds, committed
Statement 2: INSERT no_such_table → raises error
Statement 3: CREATE example_two   → still runs, committed
Result: incomplete deployment state
```

A CI tool must never report success merely because the final line of a script finished running.

## 12. `ON_ERROR_STOP`: stopping on error

Pass it from the command line:

```bash
psql -X -v ON_ERROR_STOP=1 \
  -h localhost -U lab_user -d lab_db \
  -f bad_setup.sql
```

Or declare it inside the script:

```text
\set ON_ERROR_STOP on
```

`ON_ERROR_STOP` is a **special psql variable**. It tells psql to stop upon encountering an applicable error instead of continuing to subsequent statements.

**Important warning:** stopping on error **does not undo earlier statements**. If a `CREATE TABLE` already committed before the error, it remains unless an enclosing transaction rolls it back.

There are two separate goals:

- **Fail fast:** stop immediately when the script encounters an error.
- **Atomicity:** either all changes in the transaction commit together, or none of the changes in that transaction commit.

`ON_ERROR_STOP` serves the first goal; a transaction is needed to solve the second.

## 13. Exit codes: letting the shell/CI detect failure

`psql` returns an exit code when it terminates. Common codes are:

| Exit code | Meaning |
| ---: | --- |
| **0** | psql completed normally |
| **1** | Fatal client-side psql error (e.g., unreadable file) |
| **2** | Connection to the server broke in non-interactive mode |
| **3** | Error in the script while `ON_ERROR_STOP` is enabled |

Do not assume a script without `ON_ERROR_STOP` will always return nonzero simply because a SQL statement in the middle failed.

### 13.1. Bash: checking the exit code

```bash
#!/usr/bin/env bash

psql -X -v ON_ERROR_STOP=1 \
  -h localhost -U lab_user -d lab_db \
  -f setup.sql

status=$?

if [ "$status" -ne 0 ]; then
  echo "Database script failed (psql exit=$status)" >&2
  exit "$status"
fi

echo "Database script completed"
```

Capture `$?` **immediately after** the psql command, because the next command will overwrite the exit status.

### 13.2. Bash: running with error-stop flags

```bash
#!/usr/bin/env bash
set -euo pipefail

psql -X -v ON_ERROR_STOP=1 \
  -h localhost -U lab_user -d lab_db \
  -f setup.sql

echo "Completed"
```

`set -e` has shell-context exceptions (such as inside `if` conditions); `pipefail` prevents a pipeline from masking a preceding command's exit code. However, **`set -e` does not replace `ON_ERROR_STOP`**: the shell only knows psql failed if psql exits with an appropriate nonzero code.

### 13.3. Windows PowerShell 5.1

```powershell
& psql -X -v ON_ERROR_STOP=1 `
    -h localhost -U lab_user -d lab_db `
    -f .\setup.sql

$psqlExit = $LASTEXITCODE

if ($psqlExit -ne 0) {
    Write-Error "Database script failed: psql exit $psqlExit"
    exit $psqlExit
}

Write-Host "Database script completed"
```

In PowerShell, `$LASTEXITCODE` holds the exit code of the last native program executed. In Windows PowerShell 5.1, do not rely solely on `$ErrorActionPreference = 'Stop'` to catch nonzero exit codes from native executables. Check `$LASTEXITCODE` explicitly.

The line-continuation character in Bash is backslash `\`; PowerShell typically uses a **backtick**. Do not copy line-continuation syntax from Bash into PowerShell without adapting it.

## 14. `--single-transaction` / `-1`: making a set of files atomic

If all statements support running inside a transaction, you can use:

```bash
psql -X -v ON_ERROR_STOP=1 -1 \
  -h localhost -U lab_user -d lab_db \
  -f setup.sql
```

`-1` is short for `--single-transaction`. When used with compatible file/command options, psql wraps the statements in a single transaction. When `ON_ERROR_STOP` is enabled and an error occurs, the run can roll back instead of committing partial changes in that transaction.

```text
START TRANSACTION
      |
      +-- SQL A: succeeds
      |
      +-- SQL B: succeeds
      |
      +-- SQL C: fails
      |
      +-- ROLLBACK
      |
      +-- psql returns nonzero to shell
```

### 14.1. Why should `-1` and `ON_ERROR_STOP` be used together?

Because they solve two different problems:

| Option | Function |
| --- | --- |
| `-v ON_ERROR_STOP=1` | Stops the script and reports failure |
| `-1` | Groups compatible statements into one transaction |
| Combined | Stops on error and rolls back uncommitted changes in the transaction |

If you enable only `ON_ERROR_STOP`, earlier autocommitted statements **are not automatically rolled back**.

### 14.2. Statements that cannot run inside a transaction block

Not every PostgreSQL statement is compatible with `-1`:

```sql
-- Cannot run inside a transaction block:
CREATE DATABASE another_db;

-- Examples of operations with transaction restrictions:
VACUUM;
CREATE INDEX CONCURRENTLY idx_sample ON sample_table(id);
```

These statements only illustrate transaction-block incompatibility; `sample_table` is a hypothetical table. Separate such statements into their own deployment step with an appropriate control workflow.

### 14.3. Do not mix `-1` with ad-hoc transaction control inside files

If a file contains its own `BEGIN`, `COMMIT`, or `ROLLBACK`, they can break the "entire file in one transaction" intent set by `-1`. Choose one place to manage transactions:

- The script manages transactions explicitly, **or**
- The `psql -1` invocation manages the transaction for compatible files.

A `COMMIT` in the middle of a script can end the transaction early, leaving you without all-or-nothing rollback across the entire sequence.

### 14.4. Multiple files in one transaction

```bash
psql -X -v ON_ERROR_STOP=1 -1 \
  -h localhost -U lab_user -d lab_db \
  -f steps/01_schema.sql \
  -f steps/02_seed.sql \
  -f steps/03_report.sql
```

Or use a `main.sql` that includes sub-files with `\ir`. Both work well when you want a single psql session to execute steps in order.

## 15. Errors in transactions and `ON_ERROR_ROLLBACK`

PostgreSQL normally puts a transaction into an **aborted** state after a SQL error, causing subsequent statements in the transaction to be rejected until you roll back or properly use a savepoint.

```sql
BEGIN;

CREATE TABLE demo_psql.error_demo (
    id integer PRIMARY KEY
);

-- Intentional error: column does not exist.
INSERT INTO demo_psql.error_demo (missing_column)
VALUES (1);

-- Rejected because the transaction is already in error state.
INSERT INTO demo_psql.error_demo (id)
VALUES (2);

ROLLBACK;
```

Typical message:

```text
ERROR: current transaction is aborted,
commands ignored until end of transaction block
```

Always look for the **first root error**, not just the follow-on errors caused by the aborted transaction.

### 15.1. What is `ON_ERROR_ROLLBACK`?

`psql` has a special variable:

```text
\set ON_ERROR_ROLLBACK on
```

When enabled appropriately, psql uses savepoints to help roll back **only the failed statement** so the transaction can continue. This can be convenient during interactive practice, but should not be enabled to mask errors in migrations that require all-or-nothing semantics.

| Mechanism | Purpose |
| --- | --- |
| `ON_ERROR_STOP` | Stop script on error |
| `-1` | Wrap supported statements in a transaction |
| `ON_ERROR_ROLLBACK` | Use savepoints to continue after certain errors |
| `SAVEPOINT` / `ROLLBACK TO SAVEPOINT` | Control partial rollback within a transaction |

Explicit savepoint example:

```sql
BEGIN;

SAVEPOINT before_optional_step;

-- Perform optional step.
-- If that step fails: ROLLBACK TO SAVEPOINT before_optional_step;

COMMIT;
```

The comments above **describe a decision**, not automatic error handling. When you need error-driven branching, use application orchestration, SQL/PLpgSQL, or a workflow with explicit error handling.

## 16. Complete script suite: schema + seed + report

Recommended layout:

```text
sql/
├── main.sql
└── steps/
    ├── 01_schema.sql
    ├── 02_seed.sql
    └── 03_report.sql
```

### 16.1. `sql/main.sql`

```sql
\set ON_ERROR_STOP on

\echo ---------------------------------
\echo Starting PostgreSQL lab
\echo Schema: :target_schema
\echo ---------------------------------

\ir steps/01_schema.sql
\ir steps/02_seed.sql
\ir steps/03_report.sql

\echo Finished successfully
```

### 16.2. `sql/steps/01_schema.sql`

```sql
CREATE SCHEMA IF NOT EXISTS :"target_schema";

CREATE TABLE IF NOT EXISTS :"target_schema".orders (
    order_id bigint PRIMARY KEY,
    customer_name text NOT NULL,
    amount numeric(12,2) NOT NULL CHECK (amount >= 0),
    created_at timestamptz NOT NULL DEFAULT now()
);
```

### 16.3. `sql/steps/02_seed.sql`

```sql
INSERT INTO :"target_schema".orders
    (order_id, customer_name, amount)
VALUES
    (1, 'Nguyễn An', 120000.00),
    (2, 'Trần Bình', 250000.00),
    (3, 'Lê Chi', 80000.00)
ON CONFLICT (order_id) DO UPDATE
SET customer_name = EXCLUDED.customer_name,
    amount = EXCLUDED.amount;
```

### 16.4. `sql/steps/03_report.sql`

```sql
SELECT
    COUNT(*) AS order_count,
    COALESCE(SUM(amount), 0)::numeric AS total_amount
FROM :"target_schema".orders
\gset

\echo Orders: :order_count
\echo Total amount: :total_amount

SELECT order_id, customer_name, amount
FROM :"target_schema".orders
WHERE amount >= :'min_amount'::numeric
ORDER BY amount DESC, order_id;
```

### 16.5. Running the entire suite with one command

```bash
psql -X -v ON_ERROR_STOP=1 -1 \
  -v target_schema=lab_row45 \
  -v min_amount=100000 \
  -h localhost -U lab_user -d lab_db \
  -f sql/main.sql
```

Illustrative output:

```text
Schema: lab_row45
Orders: 3
Total amount: 450000.00
```

The report will contain the two orders with amounts of 100000 or greater.

From this example you can see:

1. `-v` passes parameters across all files in the same session.
2. `\ir` organizes sub-files independent of the working directory.
3. `:"target_schema"` quotes the schema name properly.
4. `:'min_amount'::numeric` turns the value into a cast literal.
5. `\gset` converts a SQL result into psql variables.
6. `ON_ERROR_STOP` stops on error; `-1` manages a shared transaction when all statements are compatible.

### 16.6. Testing an intentional error

In a **practice environment**, temporarily append the following statement to the end of `02_seed.sql`:

```sql
INSERT INTO :"target_schema".orders
    (order_id, customer_name, amount)
VALUES (999, 'Invalid', -10.00);
```

The `CHECK (amount >= 0)` constraint causes the statement to fail. When run with `-v ON_ERROR_STOP=1 -1`, psql stops, returns an error, and rolls back the changes made in that run's transaction.

Never test this on a schema holding real data, and never leave an intentional error statement in a production deployment script.

## 17. Printing output and diagnosing errors

### 17.1. `\echo` and `\timing`

Print messages:

```text
\echo Starting script
\echo Target schema: :target_schema
```

Time statements in psql:

```text
\timing on
```

`\timing` is handy for quick experiments, but does not replace controlled benchmarks that account for caches, load, and repeated runs.

### 17.2. Showing SQL on errors

Example:

```bash
psql -X -v ON_ERROR_STOP=1 --echo-errors \
  -h localhost -U lab_user -d lab_db \
  -f sql/main.sql
```

`--echo-errors` prints the statement associated with an error message. `-e` or `--echo-queries` prints all SQL statements sent to the server.

**Warning:** SQL text can contain sensitive literals; do not enable full SQL echoing in production logs if statements contain confidential data.

### 17.3. Disabling the pager in automation

```bash
psql -X -P pager=off -v ON_ERROR_STOP=1 \
  -h localhost -U lab_user -d lab_db \
  -f sql/main.sql
```

`-P pager=off` reduces the chance of output requiring interactive paging in scripted environments. It does not alter SQL or database data.

### 17.4. Redirecting output while preserving exit codes

```bash
psql -X -v ON_ERROR_STOP=1 \
  -h localhost -U lab_user -d lab_db \
  -f sql/main.sql \
  > sql-out.log 2> sql-err.log

status=$?
if [ "$status" -ne 0 ]; then
  echo "Failed: $status" >&2
  exit "$status"
fi
```

With pipelines like `psql ... | tee sql.log`, Bash normally returns the exit code of `tee` rather than `psql`. Use `set -o pipefail` or inspect `PIPESTATUS[0]` immediately after the pipeline. Never let a successful logging command mask a real psql failure.

## 18. Credentials, connections, and security in scripts

### 18.1. Do not embed real passwords in SQL files or commands

Never store database passwords in repositories, script files, URL logs, or command-line arguments. When automation requires authentication, use your platform's secret management mechanism or a properly controlled password file.

On Unix, libpq typically looks for the password file at:

```text
~/.pgpass
```

Each line has the structure:

```text
hostname:port:database:username:password
```

Format-illustration example only, **not a real credential**:

```text
db.example.internal:5432:lab_db:lab_user:REPLACE_WITH_SECRET
```

The file must have restricted permissions; on Unix this typically requires permissions equivalent to `0600`. On Windows, the default password file is usually at `%APPDATA%\postgresql\pgpass.conf`. You can use `PGPASSFILE` to point to a file provisioned by a secret manager.

### 18.2. Preventing prompts from blocking CI

Use `-w` / `--no-password`:

```bash
psql -X -w -v ON_ERROR_STOP=1 \
  -h db.example.internal -U lab_user -d lab_db \
  -f sql/main.sql
```

`-w` **does not bypass authentication**. It simply instructs psql not to prompt interactively for a password; if the server requires a password and the client cannot obtain one from a configured source, the connection fails immediately rather than hanging the pipeline.

### 18.3. TLS for remote connections

Example libpq connection string with certificate and hostname verification:

```bash
psql -X -w -v ON_ERROR_STOP=1 \
  "host=db.example.internal port=5432 dbname=lab_db user=lab_user sslmode=verify-full sslrootcert=/etc/postgresql/root.crt" \
  -f sql/main.sql
```

`sslmode=verify-full` requires TLS and verifies server identity against the trust chain and hostname. The CA file and endpoint must match the target environment. In proxied architectures, verify which hop terminates TLS.

### 18.4. `-X` to minimize differences between personal machines and CI

`psql` can load a personal `psqlrc` configuration file on startup. That is convenient during interactive use, but can make batch scripts behave differently across machines. `-X` / `--no-psqlrc` skips personal startup files, making results more reproducible.

## 19. Classifying errors to fix the root cause

| Error category | Example | Approach |
| --- | --- | --- |
| File/working directory | `main.sql` or a sub-file not found | Check paths for `-f`, `\i`, `\ir` |
| Connection | Wrong host, port, credentials, or TLS | Check libpq settings, network, and permissions |
| SQL syntax | Wrong column name, missing parenthesis | Check offending line, fix SQL |
| psql variable | Missing variable or literal used instead of identifier | Use `-v`, `:'var'`, `:"var"` |
| Privileges | Cannot create schema/table | Use right account and least-privilege grants |
| Constraints | Duplicate PK, invalid FK, violated CHECK | Fix input data or insert logic |
| Transactions | Transaction aborted, statement disallowed in transaction | Find root error, roll back, split files |
| Business logic | Script succeeded but targeted wrong schema | Verify target and deployment requirements |

### 19.1. File does not exist

Example message:

```text
psql: error: setup.sql: No such file or directory
```

Check:

- Whether the file actually exists.
- The working directory when invoking `-f`.
- Whether `\ir` should be used for paths relative to the script.
- Paths with spaces need proper shell quoting.

### 19.2. Improperly quoted variable

```sql
-- Unsuitable for schema names with special characters.
CREATE SCHEMA :target_schema;

-- Correct: quote variable as an identifier.
CREATE SCHEMA :"target_schema";
```

For string literals:

```sql
-- Wrong idea:
SELECT ':customer_name';

-- Correct:
SELECT :'customer_name';
```

### 19.3. Relation does not exist

```text
ERROR: relation "demo_batch.orders" does not exist
```

Verify the connected database and schema:

```sql
SELECT current_database(), current_user, current_schema();

SELECT table_schema, table_name
FROM information_schema.tables
WHERE table_name = 'orders'
ORDER BY table_schema;
```

Perhaps the schema creation script has not run yet, `target_schema` was passed incorrectly, or you connected to the wrong database.

### 19.4. Transaction aborted error

Message:

```text
ERROR: current transaction is aborted,
commands ignored until end of transaction block
```

This error normally appears **after** an earlier SQL statement already failed. Find the first error rather than focusing only on the subsequent rejected statement.

### 19.5. Distinguishing "script finished" from "business correctness"

A script can return exit 0 yet delete the wrong rows due to a missing `WHERE` clause, or create objects in the wrong schema. `ON_ERROR_STOP` cannot catch business-intent errors when the SQL itself is valid.

For critical operations, verify host, database, schema, expected row counts, and permissions, and have a suitable backup/rollback plan ready.

## 20. Bash automation template

```bash
#!/usr/bin/env bash
set -euo pipefail

: "${PGHOST:?PGHOST is required}"
: "${PGDATABASE:?PGDATABASE is required}"
: "${PGUSER:?PGUSER is required}"
: "${TARGET_SCHEMA:?TARGET_SCHEMA is required}"

psql \
  -X \
  -w \
  -v ON_ERROR_STOP=1 \
  -1 \
  -v target_schema="$TARGET_SCHEMA" \
  -v min_amount=100000 \
  -h "$PGHOST" \
  -U "$PGUSER" \
  -d "$PGDATABASE" \
  -f sql/main.sql

echo "SQL script completed successfully"
```

This is a shell runner template; it requires four non-empty configuration variables. Passwords must be supplied via an appropriate secret manager or password file and never printed to output.

For production automation:

- Keep SQL in version control, but never commit secrets.
- Never choose a schema/database name directly from unvalidated input.
- Verify the target environment before deploying.
- Use `ON_ERROR_STOP` and check the exit code.
- Use a single enclosing transaction **only when every statement is compatible**.
- Plan for re-runs or recovery after failure.
- Never weaken permissions or TLS configuration just to get past a connection error.

### Understanding idempotency properly

`CREATE TABLE IF NOT EXISTS` does not verify that an existing table has the right structure. `ON CONFLICT DO UPDATE` can overwrite valid data if misused. Therefore:

- "Re-running without errors" does not mean "the result is accurate."
- "Running inside a transaction" does not mean "cannot affect the wrong schema."
- For production migrations, use a system that tracks **migration versions**, applied state, and dedicated verification checks.

## 21. Advanced psql features requiring caution

### 21.1. `\gexec`

`\gexec` executes SQL statements **generated from the output of a query**. This is useful for controlled administrative tasks, but very dangerous if the generating query uses user data or concatenates object names without proper quoting.

Never use `\gexec` to run bulk `DROP` statements or privilege changes in production without an approval process and verification of the target object set.

### 21.2. `\copy` and `COPY`

`\copy` is a client-side psql meta-command commonly used to read/write CSV files on the client machine. `COPY` is a server-side PostgreSQL SQL command; variants that read/write server files have different privilege and path requirements.

Do not assume `\copy './file.csv'` and `COPY ... FROM '/path/file.csv'` access the same filesystem.

### 21.3. Plain SQL backup files vs. other formats

A **plain SQL** backup from `pg_dump` can be restored using `psql` under the appropriate workflow. However, custom, tar, or directory backup formats require tools like `pg_restore`. Never feed a binary backup file into `psql -f` as if it were a plain-text SQL script.

### 21.4. Script encoding

Save SQL files in **UTF-8**, especially when handling non-ASCII text. Check:

```sql
SHOW client_encoding;
```

In psql:

```text
\encoding UTF8
```

If a file uses a different encoding or was saved by a tool with an unexpected BOM, execution errors can occur. Standardize on UTF-8 across your repository and pipeline.

## 22. Self-check exercises

### Exercise 1: Run `setup.sql` and stop immediately on error

```bash
psql -X -v ON_ERROR_STOP=1 \
  -h localhost -U lab_user -d lab_db \
  -f setup.sql
```

**Explanation:** `ON_ERROR_STOP` ensures failure is reported when the script hits an error. If you also want atomicity and all statements support transactions, consider adding `-1`.

### Exercise 2: Distinguish `\i` and `\ir`

File `project/sql/main.sql` contains `\ir steps/01.sql`. When executed from a different terminal directory, which file gets included?

**Answer:** `project/sql/steps/01.sql`. `\ir` resolves relative to the currently running script's location, whereas `\i` resolves relative to psql's working directory.

### Exercise 3: Pass a table/schema name via a psql variable

```sql
CREATE TABLE :"target_schema".events (
    event_id bigint PRIMARY KEY,
    description text NOT NULL
);
```

**Explanation:** `:"target_schema"` quotes the variable as an identifier. The variable must be set with `-v target_schema=...` or `\set`.

### Exercise 4: Pass a text value in a WHERE clause

```sql
SELECT *
FROM demo_batch.orders
WHERE customer_name = :'customer_name';
```

**Explanation:** `:'customer_name'` produces a string literal. Do not write `WHERE customer_name = ':customer_name'`.

### Exercise 5: Script errors on the second statement, yet the third statement still runs

**Question:** What is the cause and how do you fix it?

**Answer:** `ON_ERROR_STOP` is not enabled, or the script is not being invoked as intended. Use `-v ON_ERROR_STOP=1` and check the exit code from `psql`; if all steps must succeed or roll back together, use an appropriate transaction.

### Exercise 6: Does `ON_ERROR_STOP` automatically roll back earlier statements?

**Answer:** No. It only instructs psql to stop. Statements that already autocommitted earlier remain persisted. An enclosing transaction such as `-1` is needed for supported groups of statements.

### Exercise 7: Can `-1` be used with `CREATE DATABASE`?

**Answer:** No, because `CREATE DATABASE` is not allowed inside a transaction block. It must run in a separate step outside a transaction.

### Exercise 8: How to check the exit code in PowerShell

**Answer:** Capture `$LASTEXITCODE` immediately after invoking `psql` and raise an error / `exit` if it is nonzero. Do not rely solely on PowerShell not printing red error text.

### Exercise 9: Capture a row count from SELECT into a psql variable

```sql
SELECT COUNT(*) AS order_count
FROM demo_batch.orders
\gset

\echo Orders: :order_count
```

**Explanation:** `\gset` assigns values from a single result row into the `order_count` variable.

### Exercise 10: Using `\if` with a SQL result

```sql
SELECT CASE WHEN COUNT(*) > 0 THEN 'true' ELSE 'false' END AS has_rows
FROM demo_batch.orders
\gset

\if :has_rows
  \echo Data exists
\else
  \echo No data
\endif
```

**Explanation:** SQL evaluates the expression, and psql uses the boolean variable to branch; `\if` does not parse arbitrary SQL comparison operators itself.

## 23. Takeaways

- **`psql -f file.sql`** is the standard way to execute SQL files from the terminal; **`\i`** and **`\ir`** include files from within psql. Use `\ir` for sub-files inside multi-directory script suites.
- **`-v name=value`** and **`\set`** define client-side psql variables, not server-side SQL bind parameters.
- **`:'name'`** quotes as a string literal, **`:"name"`** quotes as an identifier, and **`:name`** inserts raw text. Improper quoting can cause errors or unintended SQL.
- **`\gset`** turns a single SQL result row into variables; **`\if`** branches on booleans understood by psql.
- For automation, use **`-X -v ON_ERROR_STOP=1`**, check the **exit code**, and never let pipelines mask SQL errors.
- **`ON_ERROR_STOP` is not synonymous with a transaction.** Use **`-1`** when you need all-or-nothing execution and every statement is permitted inside a transaction block.
- **Not every SQL statement can run with `-1`**, such as `CREATE DATABASE` or `CREATE INDEX CONCURRENTLY`.
- Avoid storing passwords in scripts, command lines, or logs. Use a secret manager or password file, and disable password prompts with `-w` when required by automation.
- Before critical changes, verify the right host, database, schema, data, and privileges, and prepare a rollback plan.
- A reliable script must **do the right work, report errors clearly, stop at the right time, and leave no unintended state behind**.

When using `psql` with PostgreSQL, treat SQL file execution, variable substitution, and error management as **a process with an explicit contract with its caller**: success must return a success exit code; failure must emit a failure signal; and state changes must be paired with an appropriate transaction policy.
