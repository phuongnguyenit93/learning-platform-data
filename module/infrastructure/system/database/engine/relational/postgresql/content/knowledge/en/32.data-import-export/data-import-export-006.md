# Exporting Data from Tables or Queries in PostgreSQL

When you need to send PostgreSQL data to another system, analyze it in Excel, hand it off to a BI team, or produce an audit dataset, you need to **export data** into a suitable format and destination. PostgreSQL provides the `COPY ... TO` command to export directly from tables or query results. In the `psql` tool, the `\copy ... TO` command streams data over the connection and writes the file on the machine running the client.

The two commands look similar by name, yet differ in where files are accessed:

- **`COPY ... TO '/path/file.csv'`**: the PostgreSQL server writes the file directly on the database server's filesystem. File access uses the PostgreSQL server process's OS privileges.
- **`\copy ... TO 'file.csv'`**: `psql` writes the file on the client machine running `psql`. File access uses the client user's OS privileges; no superuser or server-file read/write privileges are needed just to write a client file.

Distinguishing these two locations is critical when databases run in the cloud, Docker, Kubernetes, or a remote Linux host: `/tmp/export.csv` in `COPY` is a path **on the server machine**, whereas in `\copy` it is a path **on the machine running psql**.

```text
                   APPLICATION / psql CLIENT
                            |
                     sends COPY request
                            |
                            v
                   POSTGRESQL SERVER
                            |
              +-------------+-------------+
              |                           |
          COPY TO file                COPY TO STDOUT
              |                           |
              v                           v
        SERVER Filesystem         protocol over connection
                                          |
                                          v
                                  psql / client application
                                          |
                                          v
                                   CLIENT Filesystem

        SQL:  COPY ... TO '/server/path.csv'
        psql: \copy ... TO 'client/path.csv'
```

This lesson belongs to the **Data Import and Export** chapter of the *Database Engine Relational PostgreSQL* module. It focuses on exporting from tables or queries, choosing CSV/text/binary, paths and permissions, `psql` usage, consistency across multi-file exports, protecting sensitive data, and common pitfalls.

After this lesson, you will be able to:

1. Write `COPY table TO ...` and `COPY (SELECT ...) TO ...`.
2. Choose server-side `COPY` or client-side `\copy` based on file location and actual permissions.
3. Export subsets of columns, filtered rows, JOINs, aggregates, views, or partitioned tables via queries.
4. Configure CSV headers, delimiters, quotes, escapes, NULLs, and encoding.
5. Distinguish CSV, text, and binary formats.
6. Use `psql \copy`, `\o`, `\g filename`, and `psql` CSV output for the right tasks.
7. Understand `SELECT` privileges, server-file privileges, and related predefined roles.
8. Export RLS-protected data under proper roles/policies without leaking rows beyond scope.
9. Coordinate snapshots and staging files when exporting multiple consistent datasets.
10. Spot risks of CSV formula injection, data leaks, partial files, and oversized exports.

> **Lab environment:** Examples use an isolated `export_lab` schema. Run them in a development/test database and substitute paths with an existing writable directory on the appropriate machine. Server-side file and `PROGRAM` examples are purely for learning syntax; never grant broad privileges or run them in production without review.

---

## 1. Why Export Data?

### 1.1. Common Scenarios

- Exporting orders within a date range for analysis.
- Generating CSVs for partners or accounting systems.
- Exporting aggregated summaries by customer, product, or month.
- Pulling query results from a database server to an analyst's laptop.
- Producing staging files to load into a data warehouse.
- Archiving a controlled extract for auditing.
- Exporting data from a refreshed materialized view.
- Extracting a subset of rows from a partitioned table without dumping the entire database.

### 1.2. Export vs. Backup

| Need | Suitable Tool |
|---|---|
| Export a table or query result as CSV/text | `COPY` or `\copy` |
| Export filtered data via WHERE/JOIN | `COPY (SELECT ...) TO` |
| Logical backup of a database/schema/object | `pg_dump` |
| Full cluster backup including roles and objects | `pg_dumpall` or appropriate backup solution |
| Export JSON/JSONL dataset | Query with `json_build_object`/`row_to_json` + `COPY` |
| Produce an Excel XLSX workbook | Export CSV, then convert via spreadsheet/ETL tool |

`COPY` is not a full backup tool. It exports column values from a result set—it does not save schemas, indexes, constraints, grants, triggers, or full table metadata.

### 1.3. An Export Is a Data Contract

A CSV file is more than "columns separated by commas". Consumers need to know:

- Column names and order.
- Data types and date/time formats.
- NULL and empty-string rules.
- Character encoding.
- Currency units, timezones, and precision.
- Row ordering if downstream depends on order.
- Data scope and snapshot timestamp.
- File schema/contract version.

For cross-system integrations, treat the export layout as a versioned **data contract**.

---

## 2. Setting Up the Lab Schema and Data

### 2.1. Create the Schema

```sql
CREATE SCHEMA export_lab;
```

If the schema already exists, use a fresh test database or verify ownership; never drop someone else's schema just to re-run exercises.

### 2.2. Create the customers Table

```sql
CREATE TABLE export_lab.customers (
    customer_id BIGINT PRIMARY KEY,
    customer_name TEXT NOT NULL,
    email TEXT,
    tenant_id INTEGER NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
);
```

### 2.3. Create the orders Table

```sql
CREATE TABLE export_lab.orders (
    order_id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL
        REFERENCES export_lab.customers(customer_id),
    tenant_id INTEGER NOT NULL,
    ordered_at TIMESTAMPTZ NOT NULL,
    status TEXT NOT NULL
        CHECK (status IN ('draft', 'paid', 'cancelled')),
    amount NUMERIC(14,2) NOT NULL
        CHECK (amount >= 0),
    note TEXT
);

CREATE INDEX orders_tenant_ordered_at_idx
ON export_lab.orders (tenant_id, ordered_at);
```

### 2.4. Load Sample Data

```sql
INSERT INTO export_lab.customers
    (customer_id, customer_name, email, tenant_id, created_at)
VALUES
    (1, 'Nguyen An', 'an@example.test', 10,
        TIMESTAMPTZ '2026-01-03 08:00:00+00'),
    (2, 'Tran Binh', NULL, 10,
        TIMESTAMPTZ '2026-01-05 09:30:00+00'),
    (3, 'Le Chi', 'chi@example.test', 20,
        TIMESTAMPTZ '2026-02-01 10:15:00+00');

INSERT INTO export_lab.orders
    (order_id, customer_id, tenant_id, ordered_at,
     status, amount, note)
VALUES
    (1001, 1, 10, TIMESTAMPTZ '2026-02-01 01:00:00+00',
     'paid', 120.50, 'First order'),
    (1002, 1, 10, TIMESTAMPTZ '2026-02-02 02:30:00+00',
     'draft', 80.00, 'Needs review, urgent'),
    (1003, 2, 10, TIMESTAMPTZ '2026-02-03 04:00:00+00',
     'paid', 250.00, 'Contains "special" item'),
    (2001, 3, 20, TIMESTAMPTZ '2026-02-04 06:00:00+00',
     'paid', 999.99, E'First line\nSecond line');
```

### 2.5. Inspect the Data

```sql
SELECT *
FROM export_lab.customers
ORDER BY customer_id;

SELECT *
FROM export_lab.orders
ORDER BY order_id;
```

The dataset includes a NULL email, notes with commas, double quotes, and newlines so you can observe how CSV quoting and escaping behave.

---

## 3. SQL COPY TO Command

### 3.1. Basic Syntax

```sql
COPY table_name
TO 'absolute_server_path'
WITH (FORMAT csv, HEADER true);
```

Or exporting a query result:

```sql
COPY (
    SELECT ...
) TO 'absolute_server_path'
WITH (FORMAT csv, HEADER true);
```

Key points:

- `COPY table TO` exports rows from a supported relation.
- `COPY (query) TO` exports the query's result set.
- The query must be wrapped in parentheses after `COPY`.
- `TO 'path'` writes the file directly on the server.
- `TO STDOUT` streams data over the connection to the client.
- `WITH (FORMAT csv, HEADER true)` selects CSV and writes a header row.

### 3.2. Exporting an Entire Table

```sql
COPY export_lab.orders
TO '/var/lib/postgresql/exports/orders.csv'
WITH (
    FORMAT csv,
    HEADER true,
    ENCODING 'UTF8'
);
```

This path is a **server-side example**. `/var/lib/postgresql/exports` must exist on the PostgreSQL host and be writable by the PostgreSQL process.

### 3.3. COPY TO Does Not Guarantee Row Order

When deterministic order is required, use a query:

```sql
COPY (
    SELECT
        order_id,
        customer_id,
        ordered_at,
        status,
        amount
    FROM export_lab.orders
    ORDER BY order_id
) TO '/var/lib/postgresql/exports/orders_sorted.csv'
WITH (FORMAT csv, HEADER true, ENCODING 'UTF8');
```

Never rely on physical heap order, primary keys, or indexes to assume output is sorted. **Only `ORDER BY` in a query defines output order.**

### 3.4. Exporting a Subset of Columns

```sql
COPY export_lab.orders (
    order_id,
    customer_id,
    ordered_at,
    amount
)
TO '/var/lib/postgresql/exports/order_amounts.csv'
WITH (FORMAT csv, HEADER true);
```

Only the listed columns are exported. `note` and `tenant_id` are omitted from this file.

### 3.5. Why Specify Columns Explicitly?

```sql
COPY export_lab.orders TO ...;
```

exports every eligible column of the table. If a migration later adds `internal_comment` or `payment_token_reference`, an unqualified table export may leak extra fields into the output file.

For long-lived or external exports, always specify an **explicit column list or `SELECT` list**.

---

## 4. Exporting Data from a SELECT Query

### 4.1. Filtering by Status

```sql
COPY (
    SELECT
        order_id,
        ordered_at,
        status,
        amount
    FROM export_lab.orders
    WHERE status = 'paid'
    ORDER BY ordered_at, order_id
) TO '/var/lib/postgresql/exports/paid_orders.csv'
WITH (FORMAT csv, HEADER true);
```

`COPY (SELECT ...) TO` shines when exports need `WHERE`, `ORDER BY`, `JOIN`, aggregates, expressions, or masking.

### 4.2. Filtering by Time Range

```sql
COPY (
    SELECT
        order_id,
        tenant_id,
        ordered_at,
        amount
    FROM export_lab.orders
    WHERE ordered_at >= TIMESTAMPTZ '2026-02-01 00:00:00+00'
      AND ordered_at <  TIMESTAMPTZ '2026-03-01 00:00:00+00'
    ORDER BY ordered_at, order_id
) TO '/var/lib/postgresql/exports/february_orders.csv'
WITH (FORMAT csv, HEADER true, ENCODING 'UTF8');
```

Half-open intervals `[start, end)` avoid calculating the "last second" of a day and work cleanly with high-precision timestamps.

### 4.3. Joining Multiple Tables

```sql
COPY (
    SELECT
        o.order_id,
        c.customer_name,
        c.email,
        o.ordered_at,
        o.status,
        o.amount
    FROM export_lab.orders AS o
    JOIN export_lab.customers AS c
      ON c.customer_id = o.customer_id
     AND c.tenant_id = o.tenant_id
    WHERE o.tenant_id = 10
    ORDER BY o.order_id
) TO '/var/lib/postgresql/exports/tenant_10_orders.csv'
WITH (FORMAT csv, HEADER true, ENCODING 'UTF8');
```

Query export headers take the `SELECT` column names or aliases. Use clear aliases so consumers get a clean schema.

### 4.4. Aggregating by Tenant

```sql
COPY (
    SELECT
        tenant_id,
        status,
        COUNT(*) AS order_count,
        SUM(amount) AS total_amount
    FROM export_lab.orders
    GROUP BY tenant_id, status
    ORDER BY tenant_id, status
) TO '/var/lib/postgresql/exports/order_summary.csv'
WITH (FORMAT csv, HEADER true);
```

### 4.5. Exporting Expressions and Aliases

```sql
COPY (
    SELECT
        order_id,
        amount,
        amount * 1.08 AS amount_with_tax,
        upper(status) AS status_code
    FROM export_lab.orders
    ORDER BY order_id
) TO '/var/lib/postgresql/exports/order_calculated.csv'
WITH (FORMAT csv, HEADER true);
```

These are computed output columns; neither `amount_with_tax` nor `status_code` exists physically in the base table.

### 4.6. Exporting Views

```sql
CREATE VIEW export_lab.paid_order_report AS
SELECT
    o.order_id,
    c.customer_name,
    o.ordered_at,
    o.amount
FROM export_lab.orders AS o
JOIN export_lab.customers AS c
  ON c.customer_id = o.customer_id
WHERE o.status = 'paid';

COPY (
    SELECT *
    FROM export_lab.paid_order_report
    ORDER BY order_id
) TO '/var/lib/postgresql/exports/paid_order_report.csv'
WITH (FORMAT csv, HEADER true);
```

Direct `COPY table TO` does not support every relation kind such as views or partitioned tables; use `COPY (SELECT ...) TO` for those cases.

### 4.7. Partitioned Tables

For a partitioned table, a query:

```sql
COPY (
    SELECT *
    FROM app.events
    WHERE event_time >= TIMESTAMPTZ '2026-01-01 00:00:00+00'
    ORDER BY event_time, event_id
) TO '/var/lib/postgresql/exports/events.csv'
WITH (FORMAT csv, HEADER true);
```

lets PostgreSQL scan the partitioned parent and prune irrelevant partitions. Direct `COPY app.events TO ...` is not equivalent to this general query pattern.

### 4.8. COPY Query from a Materialized View

`COPY table TO` can export a populated materialized view directly. When filtering or sorting is needed, the query form remains cleaner:

```sql
COPY (
    SELECT *
    FROM reporting.monthly_sales
    WHERE month_start >= DATE '2026-01-01'
    ORDER BY month_start, tenant_id
) TO '/var/lib/postgresql/exports/monthly_sales.csv'
WITH (FORMAT csv, HEADER true);
```

### 4.9. SELECT DISTINCT or UNION

```sql
COPY (
    SELECT DISTINCT customer_id
    FROM export_lab.orders
    ORDER BY customer_id
) TO '/var/lib/postgresql/exports/order_customers.csv'
WITH (FORMAT csv, HEADER true);
```

`COPY (query) TO` exports the query result set; PostgreSQL evaluates `DISTINCT`, `UNION`, `GROUP BY`, and `JOIN` normally.

---

## 5. Server-File COPY TO and Access Permissions

### 5.1. Server and Client Are Different Machines

Suppose:

```text
Analyst laptop:
    C:\Users\analyst\Downloads

Database server:
    /var/lib/postgresql/data
```

The command:

```sql
COPY export_lab.orders
TO '/tmp/orders.csv'
WITH (FORMAT csv, HEADER true);
```

writes `/tmp/orders.csv` on the **database server**, not on the analyst's laptop.

### 5.2. PostgreSQL's OS User

Server-side `COPY` opens files under the OS identity running the PostgreSQL server process (typically the `postgres` system user on Linux). A database login does not automatically have permission to write anywhere on the server.

Even when the SQL role holds `SELECT` on the table, writing a server file requires:

- The server directory exists and is accessible.
- OS permissions allow writes by the PostgreSQL process.
- Appropriate PostgreSQL privileges for server-side file operations.

### 5.3. Predefined Roles

Relevant PostgreSQL roles:

| Role | Primary Capability |
|---|---|
| `pg_write_server_files` | Write files anywhere the server process can access via file/COPY functions |
| `pg_read_server_files` | Read server files via file/COPY functions |
| `pg_execute_server_program` | Execute programs on the server via allowed features |

These roles carry broad power and should never be granted to application roles merely to download a CSV.

### 5.4. File Write Rights and Table Read Rights Are Two Separate Layers

Running:

```sql
COPY export_lab.orders
TO '/server/path/orders.csv'
WITH (FORMAT csv, HEADER true);
```

requires `SELECT` on the table/columns **and** server-file operation privileges when targeting a server file. `GRANT SELECT` never grants filesystem write access; conversely, `pg_write_server_files` never grants `SELECT` on tables.

### 5.5. Never Grant pg_write_server_files Casually

This role can write to any path writable by the PostgreSQL OS process. If OS permissions are loose, it risks overwriting configuration files, application data, or sensitive locations.

When analysts simply want files on their own machines, **`\copy` is almost always the right choice**.

### 5.6. Output Paths Must Be Absolute for COPY TO File

PostgreSQL requires an absolute path for `COPY TO` server filenames, avoiding ambiguity over the server process's working directory.

### 5.7. Windows Server Path Example

If the PostgreSQL server runs on Windows, an example like:

```sql
COPY export_lab.orders
TO E'C:\\postgres_exports\\orders.csv'
WITH (FORMAT csv, HEADER true);
```

is resolved on the Windows server's filesystem. Verify escaping and permissions for the PostgreSQL service account.

---

## 6. COPY TO STDOUT and psql \copy

### 6.1. COPY TO STDOUT

```sql
COPY (
    SELECT order_id, amount
    FROM export_lab.orders
    ORDER BY order_id
) TO STDOUT
WITH (FORMAT csv, HEADER true);
```

`STDOUT` means PostgreSQL streams data over the connection to the client. The server chooses no output file.

### 6.2. psql \copy

In `psql`:

```text
\copy export_lab.orders TO 'orders.csv' WITH (FORMAT csv, HEADER true, ENCODING 'UTF8')
```

`\copy` uses frontend copy: `psql` receives the stream from the server and writes the file on the **machine running psql**.

### 6.3. Exporting Query Results with \copy

```text
\copy (SELECT order_id, customer_id, ordered_at, status, amount FROM export_lab.orders WHERE status = 'paid' ORDER BY order_id) TO 'paid_orders.csv' WITH (FORMAT csv, HEADER true, ENCODING 'UTF8')
```

The query must be wrapped in parentheses. This is the standard way to export custom queries straight to an analyst's machine.

### 6.4. Relative Paths

With `\copy`, filenames resolve on the client side. Writing:

```text
\copy (SELECT order_id, amount FROM export_lab.orders) TO 'orders.csv' WITH (FORMAT csv, HEADER true)
```

writes into the current working directory of the `psql` process. Inspect or change it using meta-commands:

```text
\! pwd
\cd /path/to/export
```

`\ ! pwd` runs a shell command from `psql` and is OS-dependent. On Windows, use valid Windows client paths.

### 6.5. Windows Client Path Example

```text
\copy (SELECT order_id, amount FROM export_lab.orders ORDER BY order_id) TO 'C:/Users/analyst/Downloads/orders.csv' WITH (FORMAT csv, HEADER true, ENCODING 'UTF8')
```

The file sits on the machine running `psql`. If `psql` runs inside a container, the path resides inside the container and must be volume-mounted to reach the host.

### 6.6. No Superuser Needed to Write Client Files

`\copy` streams data over the connection. The user still needs `SELECT` privileges on the query and local OS write access at the destination path, yet needs zero `pg_write_server_files` privileges to create local files.

### 6.7. Special Parsing Rules for \copy

Unlike many `psql` meta-commands, everything on the line after `\copy` is parsed as its arguments. Therefore:

- Keep `\copy` cleanly on one line.
- Do not expect `psql` variable interpolation like `:myvar` inside arguments.
- Do not expect backquote expansion.
- Be careful with quotes inside queries and paths.

For complex dynamic SQL, generate controlled queries/functions or use a client API rather than assembling untrusted inputs into a `\copy` line.

### 6.8. COPY Count

SQL `COPY` normally returns a command tag:

```text
COPY 4
```

where 4 is the number of exported rows. For `COPY TO STDOUT` or `\copy ... TO stdout`, `psql` omits printing the command tag so status text does not contaminate the output stream.

---

## 7. Server-File COPY, Client-File \copy, and PROGRAM

| Syntax | Where file is read/written or command runs | Required Privileges |
|---|---|---|
| `COPY table TO '/path/file'` | Server filesystem | SQL `SELECT` + server-file privilege / OS access |
| `COPY (query) TO STDOUT` | Data streamed over connection | SQL `SELECT` |
| `\copy table TO 'file'` | `psql` client filesystem | SQL `SELECT` + local write access |
| `COPY (query) TO PROGRAM 'cmd'` | Command runs on server | SQL `SELECT` + `pg_execute_server_program` / appropriate rights |
| `\copy (query) TO PROGRAM 'cmd'` | Command runs on `psql` client | SQL `SELECT` + local command execution rights |

### 7.1. Server-Side COPY TO PROGRAM

```sql
-- Illustrative only; do not run casually:
-- COPY (
--     SELECT order_id, amount
--     FROM export_lab.orders
-- ) TO PROGRAM 'gzip > /var/lib/postgresql/exports/orders.csv.gz'
-- WITH (FORMAT csv, HEADER true);
```

PostgreSQL spawns the command via a shell on the server machine. Anyone who can influence the command string can cause severe damage. Never interpolate user input into `PROGRAM`.

### 7.2. Client-Side \copy PROGRAM

```text
-- Illustrative example for a Unix client with gzip:
\copy (SELECT order_id, amount FROM export_lab.orders) TO PROGRAM 'gzip > orders.csv.gz' WITH (FORMAT csv, HEADER true)
```

Here the command is spawned by the `psql` process on the client—not under the PostgreSQL server's OS account.

### 7.3. PROGRAM and Shell Injection

Never build commands like:

```text
PROGRAM 'gzip > ' || user_supplied_path
```

from untrusted input. Shells interpret `;`, `$()`, quotes, and pipes. For dynamic file paths, use client file APIs or safe argument-list process APIs paired with allowlists.

### 7.4. Prefer the Simpler Path

When you just need a local CSV:

```text
\copy (SELECT ...) TO 'file.csv' WITH (FORMAT csv, HEADER true)
```

is usually sufficient. Avoid server-side `PROGRAM` or broad OS privileges.

---

## 8. Choosing the Format: CSV, Text, or Binary

| Format | Characteristics | Best Fit |
|---|---|---|
| `text` | One row per line, tab delimiter by default, backslash escapes | PostgreSQL/text pipelines, simple files |
| `csv` | Standard quote/escape rules, spreadsheet/ETL support | Interchange across heterogeneous tools |
| `binary` | PostgreSQL type-specific binary framing | Controlled PostgreSQL-to-PostgreSQL pipelines needing fidelity/speed |

### 8.1. CSV Is the Most Common Choice

```sql
COPY (
    SELECT order_id, customer_id, amount
    FROM export_lab.orders
) TO STDOUT
WITH (FORMAT csv, HEADER true);
```

CSV is readable, supported by Excel/LibreOffice/ETL tools, and defines quoting rules for commas, newlines, and quotes.

### 8.2. Text Format

```sql
COPY (
    SELECT order_id, customer_id, amount
    FROM export_lab.orders
) TO STDOUT
WITH (FORMAT text, DELIMITER E'\t', NULL '\\N');
```

Text format defaults to tab delimiters and `\N` for NULL. Backslashes, tabs, newlines, and carriage returns inside values are escaped per COPY text rules.

### 8.3. Binary Format

```sql
COPY export_lab.orders
TO '/var/lib/postgresql/exports/orders.bin'
WITH (FORMAT binary);
```

Binary format preserves exact internal representations, yet:

- Cannot be opened in Excel like CSV.
- Has no CSV headers.
- Does not support text/CSV options like delimiters, NULL strings, or quotes/escapes.
- Depends on type send/receive functions and format version.
- Is poorly portable across differing systems, versions, and column types.

Never choose binary merely assuming the file will always be smaller. Benchmark and confirm consumer compatibility first.

### 8.4. CSV Is Not XLSX

PostgreSQL `COPY` does not natively emit Excel `.xlsx` workbooks. If XLSX is needed, export CSV or query via an application and build the workbook using a client library. CSV carries no multiple sheets, styles, formulas, or explicit spreadsheet cell types.

---

## 9. CSV Configuration: Delimiter, Quote, and Escape

### 9.1. Defaults

Default CSV:

- Delimiter: comma `,`.
- Quote: double quote `"`.
- Escape: same as quote, so literal quotes inside values are doubled.

### 9.2. Values Containing Commas

Data:

```text
note = Needs review, urgent
```

CSV output:

```csv
"Needs review, urgent"
```

### 9.3. Values Containing Double Quotes

Data:

```text
Contains "special" item
```

CSV output:

```csv
"Contains ""special"" item"
```

### 9.4. Values Containing Newlines

A text value containing a newline is quoted into one field spanning multiple physical lines:

```csv
"First line
Second line"
```

Therefore **never count physical text lines to count CSV records**. One record can contain embedded newlines inside quoted fields.

### 9.5. Customizing the Delimiter

```sql
COPY (
    SELECT order_id, customer_id, amount
    FROM export_lab.orders
) TO STDOUT
WITH (
    FORMAT csv,
    DELIMITER ';',
    HEADER true
);
```

The delimiter must be a single single-byte character. Semicolon-delimited CSV fits certain spreadsheet locales, provided consumers expect `;`.

### 9.6. Customizing Quote and Escape

```sql
COPY (
    SELECT order_id, note
    FROM export_lab.orders
) TO STDOUT
WITH (
    FORMAT csv,
    QUOTE '"',
    ESCAPE '"',
    HEADER true
);
```

Change quote/escape only when required by a data contract. Defaults are most widely compatible across CSV parsers.

### 9.7. FORCE_QUOTE

```sql
COPY (
    SELECT
        customer_id,
        customer_name,
        email
    FROM export_lab.customers
) TO STDOUT
WITH (
    FORMAT csv,
    HEADER true,
    FORCE_QUOTE (email)
);
```

`FORCE_QUOTE` applies only to CSV `COPY TO`. It forces quoting on **non-NULL** values in the specified columns. NULL outputs are never quoted.

Use `FORCE_QUOTE *` to quote all non-NULL values:

```sql
COPY (
    SELECT order_id, status, note
    FROM export_lab.orders
) TO STDOUT
WITH (FORMAT csv, HEADER true, FORCE_QUOTE *);
```

### 9.8. FORCE_NULL and FORCE_NOT_NULL Are Not Output Options

`FORCE_NULL` and `FORCE_NOT_NULL` belong to **`COPY FROM` CSV** (imports). On export, use `NULL` and `FORCE_QUOTE` when controlling NULL and string representation.

---

## 10. NULL and Empty Strings in CSV

### 10.1. CSV Must Distinguish NULL from Empty String

These two values:

```text
SQL NULL
empty string ''
```

are distinct. Default PostgreSQL CSV separates them as:

```csv

""
```

Here:

- An unquoted empty field represents NULL.
- `""` represents an empty string.

### 10.2. Export Example

```sql
COPY (
    SELECT
        customer_id,
        email
    FROM export_lab.customers
    ORDER BY customer_id
) TO STDOUT
WITH (FORMAT csv, HEADER true);
```

Customer 2 has a NULL email; the output encodes NULL per default CSV rules.

### 10.3. Setting a Custom NULL String

```sql
COPY (
    SELECT customer_id, email
    FROM export_lab.customers
) TO STDOUT
WITH (
    FORMAT csv,
    HEADER true,
    NULL 'NULL'
);
```

SQL NULL is written as unquoted `NULL`. A literal text value equal to `'NULL'` is quoted (`"NULL"`) to remain distinct.

### 10.4. Consumers Must Share the Data Contract

If a downstream pipeline re-imports the CSV, it must configure the matching NULL string. Never treat the literal word `NULL` as SQL NULL if the export used default empty-unquoted or another convention.

### 10.5. Never Coerce NULL to Empty String Accidentally

The query:

```sql
SELECT COALESCE(email, '') AS email
FROM export_lab.customers;
```

turns SQL NULL into an empty string **inside the query result**, altering file semantics. Only do so when explicitly required by the data contract.

---

## 11. Headers, Column Names, and Column Order

### 11.1. HEADER true

```sql
COPY (
    SELECT
        order_id AS id,
        ordered_at AS order_time,
        amount AS total_amount
    FROM export_lab.orders
    ORDER BY order_id
) TO STDOUT
WITH (FORMAT csv, HEADER true);
```

The first line emits the aliases:

```csv
id,order_time,total_amount
```

### 11.2. Without HEADER

```sql
COPY (
    SELECT order_id, amount
    FROM export_lab.orders
) TO STDOUT
WITH (FORMAT csv, HEADER false);
```

Use when consumers rely on positional schemas or forbid headers. Never omit headers merely because a file is small.

### 11.3. Column Names Are Part of the API

Renaming `total_amount` to `amount` can break downstream field mappings. Treat header names and column order as a versioned contract.

### 11.4. Headers Do Not Carry Data Types

CSV headers list only column names—no types, nullability, precision, timezones, or units. If machine-readable schemas are required, publish a sidecar schema/metadata file or use a schema-bearing format like Parquet via ETL tools.

---

## 12. Encoding and Date/Time Formatting

### 12.1. UTF-8

For Vietnamese and multilingual data, UTF-8 is standard:

```sql
COPY (
    SELECT customer_id, customer_name, email
    FROM export_lab.customers
) TO STDOUT
WITH (
    FORMAT csv,
    HEADER true,
    ENCODING 'UTF8'
);
```

### 12.2. Client Encoding

When `ENCODING` is omitted, `COPY` uses the active client encoding. In `psql`, inspect or set it via:

```text
\encoding
\encoding UTF8
```

`COPY`'s `ENCODING` specifies the file's data encoding; transcoding occurs between server/client configurations and the chosen encoding.

### 12.3. Do Not Confuse Server Encoding with File Encoding

`SHOW server_encoding;` reports the database's storage encoding. Exported files can use another supported encoding via transcoding. If a character cannot be represented in the target encoding, `COPY` raises an error.

### 12.4. DateStyle

Text/CSV `COPY` formats values via each type's output function. Date/time strings can be affected by GUCs like `DateStyle` and `TimeZone`.

For portable exports, set them locally:

```sql
BEGIN;

SET LOCAL DateStyle = 'ISO, YMD';
SET LOCAL TimeZone = 'UTC';

COPY (
    SELECT
        order_id,
        ordered_at,
        amount
    FROM export_lab.orders
    ORDER BY order_id
) TO STDOUT
WITH (FORMAT csv, HEADER true, ENCODING 'UTF8');

COMMIT;
```

This pattern uses server-side SQL `COPY TO STDOUT`; the client receives and saves the stream. With `\copy`, wrap `SET LOCAL` and `\copy` inside the same transaction.

### 12.5. TIMESTAMPTZ

`TIMESTAMPTZ` represents an absolute instant. Its text display depends on the active `TimeZone`. The exact same instant renders differently depending on session timezone:

```sql
BEGIN;
SET LOCAL TimeZone = 'UTC';
SELECT ordered_at FROM export_lab.orders;
SET LOCAL TimeZone = 'Asia/Ho_Chi_Minh';
SELECT ordered_at FROM export_lab.orders;
ROLLBACK;
```

When consumers expect consistent timestamps, specify the timezone in the data contract—commonly UTC.

### 12.6. INTERVAL

PostgreSQL recommends watching `IntervalStyle` when exporting portable data; certain interval formats can be parsed differently on servers with different settings. For cross-system exports, normalize to an explicit representation or document the style.

### 12.7. BOM for Spreadsheets

`COPY ENCODING 'UTF8'` writes UTF-8 without assuming every Excel user expects or accepts a BOM. Verify your target consumer. If an older spreadsheet flow requires a BOM, prepend it during client-side file assembly per contract—never inject BOM characters into individual data fields.

---

## 13. Exporting JSON and JSONL from Queries

`COPY` supports text, CSV, and binary formats. To produce JSON, project **one text/json expression column** and use text output.

### 13.1. One JSON Object per Line (JSONL)

```sql
COPY (
    SELECT row_to_json(q)
    FROM (
        SELECT
            order_id,
            customer_id,
            ordered_at,
            status,
            amount
        FROM export_lab.orders
        ORDER BY order_id
    ) AS q
) TO STDOUT;
```

Each row produces one JSON object on its own line (structurally JSON Lines/NDJSON); consumers must expect one object per line.

### 13.2. Single JSON Array

```sql
COPY (
    SELECT COALESCE(
        json_agg(
            json_build_object(
                'order_id', order_id,
                'customer_id', customer_id,
                'amount', amount
            )
            ORDER BY order_id
        ),
        '[]'::json
    )
    FROM export_lab.orders
) TO STDOUT;
```

This yields one row containing a single JSON array. For huge datasets, aggregating into one array demands substantial memory; streaming JSONL is usually better.

### 13.3. JSON Is Not CSV

When consumers need nested objects or arrays, JSON captures structure better than CSV. Still agree on:

- `json` vs. `jsonb` textual formatting.
- NULL handling.
- Number types and precision.
- Key names.
- One object per line vs. one array per file.
- Schema version.

### 13.4. JSON Exports Can Expose Unintended Columns

`row_to_json(t)` on a full table row serializes every column in the composite type. For sensitive tables, construct explicit `SELECT` projections rather than serializing entire rows.

---

## 14. Exporting Data with RLS and Permissions

### 14.1. SELECT Privileges Always Apply

To export data, the role needs read privileges on target tables/columns. Query exports also enforce `SELECT` rights, `EXECUTE` on called functions, and applicable security policies.

### 14.2. COPY table TO and Row-Level Security

When RLS is enabled on a table, PostgreSQL applies applicable `SELECT` policies to `COPY table TO`. Verify the active role and policies; never test an export as owner/superuser and assume runtime application roles see the same rows.

### 14.3. Query Exports Still Need Authorization

```sql
COPY (
    SELECT
        order_id,
        tenant_id,
        amount
    FROM export_lab.orders
    WHERE tenant_id = 10
) TO STDOUT
WITH (FORMAT csv, HEADER true);
```

`WHERE tenant_id = 10` is a query filter, not authorization. If callers can alter queries or pass tenant parameters, enforce authorization via database policies/grants and application checks.

### 14.4. Superuser and BYPASSRLS

Superusers and roles with `BYPASSRLS` bypass normal RLS policies. An export run under a privileged role may contain far more rows than one run by an application role.

### 14.5. Least-Privilege Principles

- Export using a role holding `SELECT` only on necessary data.
- Grant column-level `SELECT` where appropriate.
- Use explicit column lists in queries.
- Never run routine production exports as superuser for convenience.
- Audit who exported what, when, which query/report, and where files landed for sensitive datasets.
- Protect download links, file ACLs, encryption, retention, and deletion.

### 14.6. COPY FROM and RLS

Note the directional difference: PostgreSQL currently does not support `COPY FROM` on RLS-enabled tables and recommends using `INSERT` instead. That restriction applies to importing—it does not mean `COPY TO` fails under RLS.

---

## 15. psql Output: \copy, \o, \g, and --csv

### 15.1. \copy Is Frontend COPY

```text
\copy (SELECT order_id, amount FROM export_lab.orders ORDER BY order_id) TO 'orders.csv' WITH (FORMAT csv, HEADER true)
```

This is the primary choice when you need COPY-compliant CSV files written on the client machine.

### 15.2. \o Redirects psql Query Output

```text
\pset format csv
\o 'orders.csv'

SELECT order_id, amount
FROM export_lab.orders
ORDER BY order_id;

\o
```

`\o` redirects query output from `psql` into a file; `\o` without a filename closes redirection and restores default output.

Key difference: `\o` writes **`psql`-formatted output**, whereas `\copy` uses the COPY protocol to stream raw format-compliant data.

### 15.3. \g filename for a Single Query

```text
\pset format csv
SELECT order_id, amount
FROM export_lab.orders
ORDER BY order_id
\g 'orders.csv'
```

`\g filename` executes the current query buffer once and writes its output to the file—a convenient one-shot alternative to `\o`.

### 15.4. \pset format csv

```text
\pset format csv
```

tells `psql` to format query outputs as CSV. If headers are desired, check `tuples_only` and related `psql` formatting settings.

### 15.5. psql --csv

From a shell, `psql` supports:

```text
psql --csv -d appdb -c "SELECT order_id, amount FROM export_lab.orders ORDER BY order_id"
```

Query results print in CSV format. You can redirect stdout in the shell, keeping stdout data distinct from stderr messages. Add `-X` to ignore personal `.psqlrc` files and `-q` for quiet script output.

### 15.6. Why Never Concatenate Commas Manually?

Avoid:

```sql
SELECT order_id || ',' || customer_name || ',' || note
FROM ...;
```

because values may contain delimiters, quotes, newlines, NULLs, and encoding edge cases. `COPY` CSV already provides a proper serializer.

### 15.7. Why Never Use Aligned Output as CSV?

`psql`'s default aligned output includes padding spaces, separator lines, and row-count footers meant for humans, not data interchange. Use `\copy` or `\pset format csv`.

---

## 16. Exporting Query Results from Java/JDBC Applications

### 16.1. Standard ResultSet

A common approach queries via JDBC and serializes in Java:

```java
String sql =
    "SELECT order_id, amount " +
    "FROM export_lab.orders " +
    "WHERE tenant_id = ?";

try (Connection connection = dataSource.getConnection();
     PreparedStatement statement = connection.prepareStatement(sql)) {

    statement.setInt(1, 10);

    try (ResultSet resultSet = statement.executeQuery()) {
        while (resultSet.next()) {
            long orderId = resultSet.getLong("order_id");
            BigDecimal amount = resultSet.getBigDecimal("amount");
            // Serialize values using a CSV library.
        }
    }
}
```

When writing CSV manually, use a proper CSV library to handle delimiters, quotes, newlines, and NULLs—never join strings with commas.

### 16.2. Using PostgreSQL CopyManager

pgJDBC exposes the COPY API. Illustrative example:

```java
import org.postgresql.PGConnection;
import org.postgresql.copy.CopyManager;

import javax.sql.DataSource;
import java.io.OutputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.sql.Connection;

public long exportPaidOrders(DataSource dataSource, Path target)
        throws Exception {

    String copySql =
        "COPY (" +
        "  SELECT order_id, customer_id, ordered_at, amount " +
        "  FROM export_lab.orders " +
        "  WHERE status = 'paid' " +
        "  ORDER BY order_id" +
        ") TO STDOUT WITH (FORMAT csv, HEADER true, ENCODING 'UTF8')";

    try (Connection connection = dataSource.getConnection();
         OutputStream output = Files.newOutputStream(target)) {

        PGConnection pgConnection =
            connection.unwrap(PGConnection.class);

        CopyManager copyManager = pgConnection.getCopyAPI();

        return copyManager.copyOut(copySql, output);
    }
}
```

This uses the pgJDBC API; ensure your driver version includes `PGConnection` and `CopyManager`. The SQL here is static—if filters are dynamic, never concatenate untrusted input into the SQL string.

### 16.3. CopyManager vs. Standard JDBC

- `PreparedStatement` executes queries and iterates rows via `ResultSet`.
- `CopyManager.copyOut` uses the PostgreSQL COPY protocol to stream bytes straight into an `OutputStream`.
- `COPY` fits large exports well because the app avoids per-row/per-column `ResultSet` overhead.
- `ResultSet` serialization fits when complex Java-side formatting is required, provided memory, fetch size, and CSV escaping are managed.

### 16.4. Writing to a Staging File

In Java, write to a temporary file on the same filesystem and rename only after `COPY` finishes:

```java
Path temporary = target.resolveSibling(
    target.getFileName().toString() + ".part"
);

// After copy finishes and the stream closes cleanly:
Files.move(
    temporary,
    target,
    java.nio.file.StandardCopyOption.REPLACE_EXISTING,
    java.nio.file.StandardCopyOption.ATOMIC_MOVE
);
```

`ATOMIC_MOVE` depends on filesystem/provider support; handle fallback deliberately if unsupported. Never publish a `.part` file as a finished export.

### 16.5. Never Log Sensitive File Contents

Log row counts, durations, query/report identifiers, and correlation IDs where useful. Keep full CSV payloads, tokens, emails, and PII out of logs.

---

## 17. Snapshots and Consistency During Export

### 17.1. A Single COPY Query Is One Statement

```sql
COPY (
    SELECT ...
) TO STDOUT WITH (FORMAT csv, HEADER true);
```

executes as one statement under a single snapshot per the active isolation level and transaction. Commits arriving after the snapshot starts do not leak inconsistently into the output.

### 17.2. Multiple Files Can See Different Snapshots

If an app exports:

```text
orders.csv
customers.csv
payments.csv
```

using three separate statements under `READ COMMITTED`, each statement takes a fresh snapshot. Concurrent commits between exports can make the three files inconsistent with each other.

### 17.3. Use REPEATABLE READ for Multi-File Snapshot Consistency

To ensure multiple exports see the exact same snapshot:

```sql
BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;

-- psql can execute \copy commands inside this transaction:
-- \copy (SELECT ... FROM export_lab.orders) TO 'orders.csv' WITH (FORMAT csv, HEADER true)
-- \copy (SELECT ... FROM export_lab.customers) TO 'customers.csv' WITH (FORMAT csv, HEADER true)

COMMIT;
```

Under `REPEATABLE READ`, all `SELECT`s inside the transaction share a consistent snapshot. If data spans external systems or side effects outside the transaction, broader coordination is required.

### 17.4. Read-Only Transactions

`READ ONLY` marks the transaction non-mutating, preventing accidental writes in export scripts. It does not replace `SELECT` privileges or RLS enforcement.

### 17.5. Long Snapshots Have a Cost

A long-running export holds back the transaction horizon, forcing PostgreSQL to retain dead tuple versions that `VACUUM` cannot reclaim yet.

This increases bloat and storage pressure. For large exports:

- Schedule off-peak when possible.
- Measure duration and bloat impact.
- Never keep transactions open while an app slowly post-processes files outside the database.
- Consider export staging, standby replicas (mindful of standby conflict/replay settings), logical replication, or a data warehouse for heavy recurring extracts.

### 17.6. Files Are Outside Database Transactions

Even when the export query runs inside a transaction:

- Files already written to disk do not roll back if the SQL transaction rolls back.
- If the second export fails, the first file still exists on disk.
- Network or client crashes leave truncated files behind.

This is a key boundary between atomic database commits and filesystem I/O.

### 17.7. File Staging and Publishing

A reliable workflow:

```text
1. Write orders.csv.part
2. Write customers.csv.part
3. Verify COPY completion, row counts, and metadata
4. Commit/close the transaction cleanly
5. Rename staging files to published names
6. Write manifest / checksum / version
```

Publish files only after every export succeeds. Atomic rename protects individual files on supported filesystems; when publishing multiple files together, use a manifest, versioned directory, or completion marker.

---

## 18. Large Exports: Streaming, Batching, and Progress

### 18.1. COPY Streams Data

`COPY` does not buffer the entire result set in client memory before writing to disk. Clients stream chunks to disk incrementally.

### 18.2. Avoid Huge OFFSET Pagination by Default

This pattern:

```sql
SELECT *
FROM export_lab.orders
ORDER BY order_id
LIMIT 10000 OFFSET 1000000;
```

scales poorly because the database scans and discards all `OFFSET` rows on every page. If chunking is necessary, use indexed keyset/range pagination:

```sql
SELECT *
FROM export_lab.orders
WHERE order_id > 1000000
ORDER BY order_id
LIMIT 10000;
```

Note that separate batches under `READ COMMITTED` see different snapshots; if snapshot consistency across chunks is required, coordinate transactions or streaming appropriately.

### 18.3. Splitting Files by Partition or Range

Monthly export example:

```sql
COPY (
    SELECT event_id, event_time, payload
    FROM app.events
    WHERE event_time >= TIMESTAMPTZ '2026-01-01 00:00+00'
      AND event_time <  TIMESTAMPTZ '2026-02-01 00:00+00'
    ORDER BY event_time, event_id
) TO STDOUT WITH (FORMAT csv, HEADER true);
```

Choose non-overlapping, gap-free boundaries. Include time range, tenant/scope, and schema version in filenames where helpful.

### 18.4. pg_stat_progress_copy

PostgreSQL exposes `pg_stat_progress_copy` to track running `COPY` operations:

```sql
SELECT
    pid,
    command,
    type,
    bytes_processed,
    bytes_total,
    tuples_processed,
    tuples_excluded
FROM pg_stat_progress_copy;
```

Some columns may be NULL or unused depending on `COPY` direction, source/target type, and execution phase. Viewing other sessions requires appropriate monitoring privileges.

### 18.5. COPY TO STDOUT and Client Backpressure

If a client writes slowly to disk, socket I/O throttles to match network and filesystem speed. Ensure clients consume the stream incrementally rather than buffering gigabytes in RAM.

### 18.6. Compression

You can compress on the client side or via `PROGRAM` when appropriate. Compression saves storage and network bandwidth at the cost of CPU and harder mid-file resumption—benchmark bottlenecks before adding it.

---

## 19. CSV Formula Injection When Opened in Spreadsheets

### 19.1. CSV Escaping Is Not Spreadsheet Safety

The CSV serializer protects commas, quotes, and newlines per CSV grammar. Yet spreadsheet tools may evaluate cell text starting with characters like:

```text
=
+
-
@
```

as formulas or expressions depending on the application and how the file is opened.

User-entered text such as:

```text
=HYPERLINK("https://example.invalid","Open")
```

can be interpreted as a live formula by spreadsheets. Valid CSV quoting **does not neutralize formula injection**.

### 19.2. Distinguish Negative Numbers from Formulas

You cannot blindly prefix every `-` value without checking column types; `-100` may be a legitimate negative number. Enforce policies per column type and consumer.

### 19.3. Consumer-Specific Mitigation

When files are opened directly in spreadsheets:

- Identify columns holding untrusted text.
- Check for formula-triggering prefixes after accounting for leading whitespace/control characters per threat model.
- Provide a neutralized **presentation export** for spreadsheets (e.g., apostrophe prefixing tested against Excel/LibreOffice).
- Keep a separate raw machine-to-machine export when exact source text must be preserved.
- Document that neutralization alters string representation.

Never slap a single generic SQL expression onto all systems and declare CSV completely safe.

### 19.4. Illustrative Presentation Field Example

```sql
SELECT
    order_id,
    CASE
        WHEN customer_supplied_text ~ '^[[:space:]]*[=+@-]'
        THEN '''' || customer_supplied_text
        ELSE customer_supplied_text
    END AS spreadsheet_safe_text
FROM some_table;
```

This merely illustrates the concept and is not a complete sanitizer for every spreadsheet or locale. Never apply it blindly to numeric columns without considering types and consumers. Test tabs, CR, LF, leading spaces, and target spreadsheet behavior.

### 19.5. Never Overwrite Raw Data with Presentation Formatting

If the consumer is an API or ETL pipeline, do not prepend apostrophes and treat that as raw data. Separate:

- Raw exports preserving exact values.
- Spreadsheet exports applying consumer-safe neutralization per contract.

---

## 20. Securing Exported Data and Files

### 20.1. Exports Cross the Database Security Boundary

Once a file is written:

- RLS no longer restricts who opens the file.
- `GRANT SELECT` no longer protects the exported copy.
- Database auditing no longer tracks copies shared via email or cloud drives.
- Backup retention does not automatically purge ad-hoc exports.

Exports therefore require their own data-governance controls.

### 20.2. Data Minimization

Export only:

- Columns downstream genuinely needs.
- Rows within the approved business scope.
- Approved time windows.
- Identifiers cleared for sharing.

Avoid `SELECT *` in external exports.

### 20.3. File Controls

- Write files into directories with strict ACLs.
- Keep exports out of public web roots and open shared folders.
- Encrypt sensitive exports at rest and in transit.
- Enforce retention and expiration policies.
- Audit who ran the export, purpose, timestamp, and scope.
- Never export credentials or secrets into CSVs.
- Clean up failed staging files promptly.

### 20.4. Server-File Exports

When `COPY` writes server files, the PostgreSQL OS user controls where writes can land. Restrict exports to a dedicated directory and block writes into configuration or key directories.

### 20.5. Client-File Exports

With `\copy`, files land on the machine running `psql`. If `psql` runs inside a container, CI runner, or jump host, files reside on that environment's filesystem rather than the remote user's laptop.

### 20.6. Never Use COPY PROGRAM as an Arbitrary File Mover

Server-side `PROGRAM` executes OS commands under the PostgreSQL service account. Never grant `pg_execute_server_program` to analysts or apps just to zip or transfer files; compress on the client side or use a scoped export service.

---

## 21. Exporting with RLS: Test Under the Real Role

### 21.1. Creating an Illustrative RLS Table

Optional lab experiment:

```sql
CREATE TABLE export_lab.tenant_notes (
    note_id BIGINT PRIMARY KEY,
    tenant_id INTEGER NOT NULL,
    note_text TEXT NOT NULL
);

INSERT INTO export_lab.tenant_notes
VALUES
    (1, 10, 'Tenant 10 note'),
    (2, 20, 'Tenant 20 note');

ALTER TABLE export_lab.tenant_notes ENABLE ROW LEVEL SECURITY;
```

### 21.2. Illustrative Policy

Production policies must bind to trusted identities/contexts. Simple role- or GUC-based examples must be adapted safely; never trust caller-controlled GUCs in policies without secure context enforcement.

```sql
-- Syntax template for environments with trusted roles and context:
-- CREATE POLICY tenant_export_policy
-- ON export_lab.tenant_notes
-- FOR SELECT
-- USING (tenant_id = current_setting('app.tenant_id')::integer);
```

### 21.3. COPY TO Enforces SELECT Policies

When `COPY table TO` runs on an RLS-enabled table, applicable `SELECT` policies filter rows for the executing role. Query exports likewise enforce all query privileges and policies.

### 21.4. Test Under the Runtime Role

Never test as superuser and assume application users see identical export results. Always test under the real runtime role and policy configuration.

### 21.5. Never Export Using BYPASSRLS Unnecessarily

Roles with `BYPASSRLS` or superuser can export rows across all tenants. For tenant-scoped exports, use least-privilege roles and audit scope carefully.

---

## 22. psql Scripts and Automation

### 22.1. Using Script Files

An `export.sql` script can contain:

```sql
BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;

SET LOCAL DateStyle = 'ISO, YMD';
SET LOCAL TimeZone = 'UTC';

-- psql meta-command: file is written on the client.
-- \copy (SELECT order_id, amount FROM export_lab.orders ORDER BY order_id) TO 'orders.csv' WITH (FORMAT csv, HEADER true, ENCODING 'UTF8')

COMMIT;
```

Run it with:

```bash
psql -X -v ON_ERROR_STOP=1 -d appdb -f export.sql
```

`-X` ignores personal `.psqlrc`; `ON_ERROR_STOP=1` halts `psql` on SQL errors. In automation, check both exit code and output file completeness.

### 22.2. Set Client Directory First

Inside a `psql` script, `\cd` changes the client's working directory:

```text
\cd /var/tmp/exports
\copy (SELECT order_id, amount FROM export_lab.orders) TO 'orders.csv' WITH (FORMAT csv, HEADER true)
```

On Windows, supply a valid path for the `psql` machine.

### 22.3. Avoid Confusing Shell and Server Paths

```bash
psql -d appdb -c "COPY export_lab.orders TO '/tmp/orders.csv' WITH (FORMAT csv, HEADER true)"
```

writes on the server host.

Whereas:

```bash
psql -d appdb -c "\copy export_lab.orders TO 'orders.csv' WITH (FORMAT csv, HEADER true)"
```

writes on the machine running `psql`.

### 22.4. stdout vs. stderr

In automation:

- Route CSV output to its own file or stdout.
- Keep error messages on stderr/logs.
- Avoid mixing banners, timing stats, SQL echo, or row counts into CSV streams.
- Use `-q` and `-X` appropriately.
- Enable `ON_ERROR_STOP` so failing scripts do not exit 0 silently.

### 22.5. Shell Quoting

Queries containing single quotes, parentheses, dollar quoting, and spaces easily break under shell parsing if passed inline. For complex queries, put them in `.sql` script files and run `psql -f` rather than assembling complex shell strings from user input.

---

## 23. Exporting Query Results with \g and \o

### 23.1. \g filename

```text
SELECT order_id, amount
FROM export_lab.orders
ORDER BY order_id
\g 'orders.csv'
```

`psql` writes the current query's output to the file, formatted according to `\pset` settings.

### 23.2. \o filename

```text
\pset format csv
\o 'orders.csv'

SELECT order_id, amount
FROM export_lab.orders
ORDER BY order_id;

SELECT COUNT(*) AS order_count
FROM export_lab.orders;

\o
```

Both queries redirect into the same file, producing two back-to-back result sets in one CSV. When a file needs a single consistent schema, redirect only the target query or use separate `\copy` commands.

### 23.3. \copy vs. \g

| Feature | `\copy ... TO` | `\g filename` |
|---|---|---|
| Underlying mechanism | PostgreSQL COPY protocol | `psql` query output formatting |
| CSV serializer | COPY CSV | `psql` CSV formatter when format CSV is set |
| Exports tables/queries | Yes | Query results |
| Writes on client | Yes | Yes |
| COPY options (`NULL`/`QUOTE`/`FORCE_QUOTE`) | Yes | Does not accept full COPY option set |
| Suited for bulk exports | Highly suited | Suited for ad-hoc query output |

---

## 24. COPY TO on Partitioned Tables, Views, and Inheritance

### 24.1. Direct COPY Relation Restrictions

Direct `COPY table TO` works on plain tables and populated materialized views. It does not directly support partitioned tables, inheritance hierarchies as a whole, or views.

### 24.2. Use a COPY Query

```sql
COPY (
    SELECT *
    FROM app.partitioned_events
) TO STDOUT
WITH (FORMAT csv, HEADER true);
```

Query mode uses full `SELECT` semantics, covering views and partitioned parents seamlessly.

### 24.3. Inheritance and ONLY

With table inheritance, `SELECT * FROM parent` includes rows from child tables per inheritance rules, whereas `SELECT * FROM ONLY parent` selects only parent rows. Choose explicitly whether you want:

```sql
COPY (
    SELECT *
    FROM ONLY app.parent_table
    ORDER BY id
) TO STDOUT
WITH (FORMAT csv, HEADER true);
```

or the entire hierarchy.

### 24.4. Materialized Views Must Be Populated

An unpopulated materialized view (`WITH NO DATA`) has no rows to export until refreshed via `REFRESH MATERIALIZED VIEW`.

---

## 25. Special Formats and Data Types

### 25.1. Numeric and Money

`NUMERIC` exports as text via its output function. For monetary data, specify:

- Currency unit.
- Scale and rounding rules.
- Decimal separator.
- Independence from spreadsheet locale assumptions.
- Explicit currency code column when multi-currency.

Never export an `amount` column without documenting whether it is VND, USD, or another currency.

### 25.2. Boolean

Booleans export using PostgreSQL's textual representation (`t`/`f` in text format and corresponding CSV output). If consumers expect `true`/`false`, format explicitly:

```sql
SELECT
    CASE WHEN is_active THEN 'true' ELSE 'false' END AS is_active
FROM app.users;
```

### 25.3. Arrays

PostgreSQL arrays use PostgreSQL array literal syntax; generic CSV consumers will not automatically parse them into multi-value fields. For portable structure, convert to JSON:

```sql
SELECT to_json(tags) AS tags_json
FROM app.products;
```

### 25.4. JSON/JSONB

`json`/`jsonb` exports via textual output. When consumers parse embedded JSON, verify CSV escaping and encoding rather than splitting on commas.

### 25.5. Bytea

`bytea` exports in text encoding (such as hex format per settings) or binary COPY. CSV is not a native binary format; large `bytea` values expand significantly in text CSV.

### 25.6. Large Objects

PostgreSQL Large Objects are referenced by OID and managed via large-object APIs; exporting an OID column does not export the underlying blob bytes. Use Large Object functions/APIs or dedicated client logic to extract blob payloads.

### 25.7. Generated Columns

When `COPY table TO` omits a column list, generated columns follow specific rules and differ from ordinary stored columns. To include generated column values reliably per contract, use an explicit `SELECT` query.

---

## 26. Ensuring Order, Schema Stability, and Reproducibility

### 26.1. Always Include a Tie-Breaker in ORDER BY

```sql
ORDER BY ordered_at
```

leaves ties in indeterminate order. For reproducible exports, add a unique tie-breaker:

```sql
ORDER BY ordered_at, order_id
```

### 26.2. Never Use SELECT *

Schema migrations add columns, reorder columns, or introduce sensitive fields. Write:

```sql
SELECT order_id, ordered_at, status, amount
```

instead of `SELECT *` in external data contracts.

### 26.3. Version Your Exports

Include contract versions in:

- Filenames: `orders_v2_2026-02.csv`.
- A JSON manifest storing schema version, timestamp, row count, and checksum.
- Catalog/pipeline metadata.

Never prepend arbitrary metadata banner lines inside a CSV when consumers expect the header on line 1; use a sidecar manifest.

### 26.4. Checksums

After writing a file, compute a SHA-256 checksum on the client to detect corruption or tampering in transit. Checksums verify file integrity, not business correctness.

### 26.5. Row Counts

The `COPY` command tag returns the row count. You can compare with:

```sql
SELECT COUNT(*)
FROM export_lab.orders
WHERE status = 'paid';
```

However, a separate `COUNT(*)` query may read a different snapshot if data is changing concurrently. For strict reconciliation, count inside the same `REPEATABLE READ` transaction or track counts directly from the export stream.

---

## 27. Common Errors When Exporting Data

### 27.1. could not open file: Permission denied

When running SQL `COPY TO '/server/path'`:

- Verify the path exists on the server.
- Check the PostgreSQL OS user.
- Check directory and file permissions.
- Check that the database role holds server-file privileges.

If you want the file on your laptop, switch to `\copy`.

### 27.2. must be superuser or a member of pg_write_server_files

This is a server-side file privilege error. Never solve it by making an app role superuser. For local exports, use `\copy`; if server files are genuinely required, have a DBA grant minimal scoped permissions.

### 27.3. relation does not exist

Common causes:

- Table name is not schema-qualified.
- `search_path` excludes the schema.
- Connected to the wrong database.
- Table resides in another schema.
- Direct `COPY` attempted on an unsupported relation type.

Always schema-qualify:

```sql
COPY app.orders TO STDOUT;
```

or use the query form.

### 27.4. permission denied for table

The role can connect, yet lacks `SELECT` on the table or columns. Check:

```sql
SELECT has_table_privilege(
    current_user,
    'export_lab.orders',
    'SELECT'
);
```

With column-level grants, inspect each referenced column.

### 27.5. invalid byte sequence / character conversion

The target file encoding cannot represent a source character. Check `server_encoding`, `client_encoding`, and `ENCODING`. UTF-8 is usually safest for multilingual exports.

### 27.6. Misaligned CSV Columns or Extra Lines

Check whether the consumer handles:

- Quoted newlines.
- Custom delimiters.
- Escaped quotes.
- NULL markers.
- File encoding.

Never parse CSV by reading lines and splitting on commas manually.

### 27.7. Empty File

A header-only file is a valid output when a query matches zero rows. Check `COPY 0` and query filters rather than assuming a small file failed.

### 27.8. Truncated / Partial File

If `COPY` fails mid-stream or the client disconnects, the output file may be incomplete. Write to a staging filename and rename/publish only after successful completion.

### 27.9. Cannot Find File After \copy

Check the **psql process's** working directory, not the database server's. If `psql` ran inside Docker or CI, the file sits inside that container or runner filesystem.

### 27.10. \copy Does Not Substitute psql Variables

Because of its special parser, `\copy ... TO :'filename'` will not interpolate variables like standard SQL. Use explicit paths or controlled client scripts/APIs.

---

## 28. Monitoring Export Progress and Activity

### 28.1. COPY Command Tag

On success, PostgreSQL returns:

```text
COPY n
```

where `n` is the count of copied rows.

### 28.2. pg_stat_progress_copy

```sql
SELECT
    pid,
    relid::regclass AS relation,
    command,
    type,
    bytes_processed,
    bytes_total,
    tuples_processed,
    tuples_excluded
FROM pg_stat_progress_copy;
```

Not every column applies to every source/destination mode. For `COPY (query) TO STDOUT`, `relation` may not reflect all underlying tables in the query.

### 28.3. pg_stat_activity

```sql
SELECT
    pid,
    usename,
    application_name,
    state,
    query_start,
    wait_event_type,
    wait_event,
    query
FROM pg_stat_activity
WHERE query ILIKE 'COPY %'
ORDER BY query_start;
```

Viewing queries from other sessions requires appropriate monitoring privileges. Never log or export full query strings if they contain sensitive literals.

### 28.4. Client-Side Tracking

Alongside database metrics, log:

- Start and completion timestamps.
- Exported row count.
- File size in bytes.
- SHA-256 checksum.
- Error/retry rates.
- Target path or object storage key.
- Data contract version.

---

## 29. Common Misconceptions

**1. "COPY TO '/path' writes the file on my laptop."** False. It writes on the PostgreSQL server's filesystem.

**2. "\copy and COPY are the same SQL command."** No. `\copy` is a `psql` meta-command executing frontend copy.

**3. "\copy requires pg_write_server_files."** Not for writing client files; it needs `SELECT` privileges and client filesystem write access.

**4. "Server-side COPY only needs SELECT."** Server-side file/`PROGRAM` targets also require server-file/program roles and OS permissions.

**5. "Holding pg_write_server_files grants SELECT on every table."** No. Server filesystem privileges are independent of table grants.

**6. "Grant pg_execute_server_program to the app so it can zip files."** Highly risky; it permits OS command execution as the database server user.

**7. "COPY table TO always supports views and partitioned tables."** No. Use `COPY (SELECT ...) TO`.

**8. "COPY table TO sorts by primary key automatically."** No. Use `ORDER BY` in a query.

**9. "COPY table TO exports columns in whatever order I expect."** No. Always specify an explicit column list or `SELECT` list.

**10. "SELECT * is safe for long-lived exports."** Adding columns in migrations breaks contracts and can leak sensitive fields.

**11. "CSV is just joining values with commas."** False. You need proper quoting, escaping, newline, and NULL handling.

**12. "One CSV line is always one physical line."** False. Quoted fields can span newlines.

**13. "NULL and empty string are identical in CSV."** No. PostgreSQL distinguishes them via quoting under the configured NULL string.

**14. "FORCE_NOT_NULL is a COPY TO option."** No. It is a `COPY FROM` CSV option.

**15. "FORCE_QUOTE quotes NULLs too."** No. NULL outputs are never quoted by `FORCE_QUOTE`.

**16. "HEADER MATCH is an export option."** No. `HEADER MATCH` applies only to `COPY FROM`.

**17. "ENCODING UTF8 guarantees every consumer renders Vietnamese properly."** Not if the consumer opens the file with the wrong encoding or mishandles BOMs/metadata.

**18. "UTF-8 always adds a BOM automatically."** No. `COPY` UTF-8 encoding does not emit a BOM.

**19. "TIMESTAMPTZ always exports in UTC regardless of session."** No. Text output reflects the session `TimeZone`.

**20. "DateStyle does not affect exported files."** It affects date formatting; set ISO explicitly for portable exports.

**21. "Binary COPY is a portable interchange format."** No. Binary format is tied to PostgreSQL types and versions and cannot be opened in spreadsheets.

**22. "Direct file COPY TO needs no stable client connection."** It still requires the controlling connection; `STDOUT` also streams over it.

**23. "Query exports automatically filter tenants from app parameters."** Only when queries, policies, and grants are designed properly.

**24. "RLS does not apply to COPY TO."** False; applicable `SELECT` policies apply to `COPY table TO`.

**25. "Superuser exports match runtime role exports."** No. Superuser and `BYPASSRLS` bypass tenant policies.

**26. "Exported files remain protected by RLS."** No. Files sit outside the database security boundary.

**27. "Wrapping multiple COPYs in one transaction makes file writes atomic."** No. Filesystem writes never roll back with database transactions.

**28. "READ COMMITTED multi-file exports share one snapshot."** Not guaranteed; each statement sees a new snapshot.

**29. "REPEATABLE READ is free."** Long snapshots pin dead tuples and impede vacuum.

**30. "Just write directly to the final filename."** Mid-stream crashes leave truncated files; stage first and publish after completion.

**31. "CSV quoting prevents spreadsheet formula injection."** No. CSV parsers and spreadsheet formula engines operate at different layers.

**32. "Every text field starting with minus is a formula."** No. Check column types and consumers so valid negative numbers stay intact.

**33. "\o and \copy are identical."** No. One redirects `psql`-formatted output, while the other uses the COPY protocol.

**34. "psql aligned output is CSV."** No.

**35. "psql variables expand inside \copy arguments."** Not under `\copy`'s special meta-command parser.

**36. "COPY PROGRAM runs on the client."** No. SQL `COPY PROGRAM` runs on the server; `\copy PROGRAM` runs on the `psql` client.

**37. "A matching row count proves an export is correct."** No. Also verify schema, scope, snapshot, checksums, and downstream ingestion.

**38. "No COPY count printed means export failed."** No. For `STDOUT`, `psql` suppresses the tag so it won't corrupt output data.

**39. "A Large Object OID is the blob payload."** No. Large Object contents require separate Large Object APIs.

**40. "Generating a CSV gives you an Excel workbook."** No. CSV is not XLSX.

---

## 30. Practice Exercises and Solutions

### Exercise 1 — Export an Entire Table to CSV

**Task:** Export `orders` with a header.

```sql
COPY export_lab.orders
TO STDOUT
WITH (FORMAT csv, HEADER true);
```

### Exercise 2 — Query Export

**Task:** Export only `paid` orders.

```sql
COPY (
    SELECT order_id, ordered_at, amount
    FROM export_lab.orders
    WHERE status = 'paid'
    ORDER BY order_id
) TO STDOUT
WITH (FORMAT csv, HEADER true);
```

### Exercise 3 — Export a Subset of Columns

**Task:** Export only `order_id` and `amount`.

```sql
COPY export_lab.orders (order_id, amount)
TO STDOUT
WITH (FORMAT csv, HEADER true);
```

### Exercise 4 — ORDER BY

**Question:** Does `COPY table TO` guarantee ascending `order_id`?

**Answer:** No. Use the query form with `ORDER BY order_id`.

### Exercise 5 — Export Tenant Data

```sql
COPY (
    SELECT order_id, amount
    FROM export_lab.orders
    WHERE tenant_id = 10
    ORDER BY order_id
) TO STDOUT
WITH (FORMAT csv, HEADER true);
```

### Exercise 6 — JOIN Customers

```sql
COPY (
    SELECT o.order_id, c.customer_name, o.amount
    FROM export_lab.orders o
    JOIN export_lab.customers c
      ON c.customer_id = o.customer_id
    ORDER BY o.order_id
) TO STDOUT
WITH (FORMAT csv, HEADER true);
```

### Exercise 7 — Aggregation

```sql
COPY (
    SELECT tenant_id, COUNT(*) AS order_count, SUM(amount) AS total
    FROM export_lab.orders
    GROUP BY tenant_id
    ORDER BY tenant_id
) TO STDOUT
WITH (FORMAT csv, HEADER true);
```

### Exercise 8 — Exporting a View

**Question:** Can you run direct `COPY view_name TO ...`?

**Answer:** Direct `COPY TO` does not support views like plain tables. Use `COPY (SELECT ... FROM view_name) TO ...`.

### Exercise 9 — Partitioned Tables

**Question:** How do you export a partitioned parent table?

**Answer:** Use `COPY (SELECT ... FROM partitioned_parent) TO ...`.

### Exercise 10 — Server Path vs. Client Path

**Question:** Where does `COPY ... TO '/tmp/a.csv'` write?

**Answer:** On the database server's filesystem.

### Exercise 11 — psql \copy

**Task:** Write CSV on the `psql` machine.

```text
\copy (SELECT order_id, amount FROM export_lab.orders ORDER BY order_id) TO 'orders.csv' WITH (FORMAT csv, HEADER true)
```

### Exercise 12 — Server File Permissions

**Question:** Can a role with `SELECT` but without `pg_write_server_files` write a server file via `COPY TO filename`?

**Answer:** No, unless it has appropriate server-file privileges; use `COPY TO STDOUT` or `\copy` to a client file instead.

### Exercise 13 — Client Permissions

**Question:** Since `\copy` does not need `pg_write_server_files`, can it write into any folder on a laptop?

**Answer:** No. The `psql` process still needs local filesystem write permissions.

### Exercise 14 — NULL

**Question:** How does default CSV represent NULL vs. empty string?

**Answer:** NULL is an unquoted empty field; empty string is `""`.

### Exercise 15 — Headers

**Task:** Emit headers using aliases.

```sql
COPY (
    SELECT order_id AS id, amount AS total
    FROM export_lab.orders
) TO STDOUT
WITH (FORMAT csv, HEADER true);
```

### Exercise 16 — Quote All

```sql
COPY (
    SELECT order_id, status
    FROM export_lab.orders
) TO STDOUT
WITH (FORMAT csv, HEADER true, FORCE_QUOTE *);
```

**Answer:** Quotes all non-NULL values; NULL stays unquoted.

### Exercise 17 — Encoding

**Task:** Export as UTF-8.

```sql
COPY (
    SELECT customer_name
    FROM export_lab.customers
) TO STDOUT
WITH (FORMAT csv, HEADER true, ENCODING 'UTF8');
```

### Exercise 18 — TimeZone

**Question:** Why can the same `TIMESTAMPTZ` export as different clock strings?

**Answer:** Text formatting reflects the session `TimeZone`; set timezone explicitly per contract, such as UTC.

### Exercise 19 — CSV Newlines

**Question:** Does a field containing a newline create two CSV records?

**Answer:** No, when properly quoted; the newline stays inside the same record's field.

### Exercise 20 — CSV Formula Injection

**Question:** Does valid CSV quoting stop Excel from evaluating `=...` as a formula?

**Answer:** No. Neutralize text fields according to consumer and threat model.

### Exercise 21 — RLS

**Question:** Does `COPY table TO` enforce `SELECT` policies when RLS is enabled?

**Answer:** Yes, applicable `SELECT` policies are enforced. Test under the actual runtime role.

### Exercise 22 — COPY FROM RLS

**Question:** Is `COPY FROM` supported on RLS-enabled tables?

**Answer:** Not currently; use equivalent `INSERT` statements per PostgreSQL documentation.

### Exercise 23 — Binary

**Question:** Is binary COPY suitable for opening directly in Excel?

**Answer:** No. Use CSV for spreadsheets.

### Exercise 24 — JSONL

**Task:** Export one JSON object per order.

```sql
COPY (
    SELECT row_to_json(q)
    FROM (
        SELECT order_id, status, amount
        FROM export_lab.orders
        ORDER BY order_id
    ) q
) TO STDOUT;
```

### Exercise 25 — psql \o

**Question:** How do `\o` and `\copy` differ?

**Answer:** `\o` redirects `psql`-formatted query output; `\copy` uses the COPY protocol with COPY options.

### Exercise 26 — \copy Variables

**Question:** Do `\copy` arguments support `psql` variable interpolation like normal queries?

**Answer:** No; `\copy`'s parser treats the rest of the line as raw arguments without variable interpolation or backquote expansion.

### Exercise 27 — PROGRAM

**Question:** Where does SQL `COPY TO PROGRAM` run?

**Answer:** On the server. `\copy TO PROGRAM` runs on the client machine running `psql`.

### Exercise 28 — Snapshots

**Question:** Are three files exported via three `READ COMMITTED` statements guaranteed to share one snapshot?

**Answer:** No. Wrap them inside a `REPEATABLE READ READ ONLY` transaction if all queries must share one snapshot.

### Exercise 29 — File Atomicity

**Question:** Does rolling back a transaction delete a CSV file already written by the client?

**Answer:** No. Filesystems do not participate in database transactions; write to staging files and publish only on success.

### Exercise 30 — pg_stat_progress_copy

**Task:** Monitor `COPY` progress.

```sql
SELECT pid, command, type, bytes_processed, tuples_processed
FROM pg_stat_progress_copy;
```

### Exercise 31 — Ordering COPY table TO

**Question:** How do you guarantee deterministic output order?

**Answer:** `COPY (SELECT ... ORDER BY ...) TO ...`.

### Exercise 32 — Export Only Public Columns

**Question:** Should you use `SELECT *` when sending data to partners?

**Answer:** No. List columns explicitly to avoid exposing new or sensitive columns later.

### Exercise 33 — XLSX

**Question:** Can `COPY` generate multi-sheet `.xlsx` workbooks?

**Answer:** No. `COPY` emits text/CSV/binary; use client libraries to build XLSX if needed.

### Exercise 34 — Large Objects

**Question:** Does exporting a Large Object OID export the blob payload?

**Answer:** No. Use dedicated Large Object APIs/functions to export blob contents.

### Exercise 35 — Server Export Paths

**Question:** Why shouldn't every analyst hold `pg_write_server_files`?

**Answer:** It allows writing to server paths accessible by the PostgreSQL process, far exceeding typical local export needs.

### Exercise 36 — Automation

**Task:** Halt a `psql` script if export fails.

**Suggested solution:**

```bash
psql -X -v ON_ERROR_STOP=1 -d appdb -f export.sql
```

Check the exit code and output file before publishing.

---

## 31. Pre-Publish Export File Checklist

### Content and Schema

1. Source table or query clearly defined?
2. Schema-qualified table names used where needed?
3. Columns listed explicitly, avoiding `SELECT *`?
4. Headers, aliases, and column order locked down?
5. Proper `WHERE` and tenant scoping applied?
6. `ORDER BY` with tie-breaker included when order matters?
7. Data types, timezones, currency units, and precision documented in a contract?

### Destination and Privileges

8. File resides on server or client?
9. Path targets the exact right host or container?
10. Role holds `SELECT` on the required tables and columns?
11. Server-file `COPY` has required roles and OS permissions?
12. Broad `pg_write_server_files`/`pg_execute_server_program` grants avoided?
13. Local client has file write permission?
14. `PROGRAM` never receives untrusted input in commands?

### Format

15. CSV/text/binary matches the consumer?
16. `HEADER true/false` matches the contract?
17. Delimiter, quote, and escape rules agreed upon?
18. NULL vs. empty string behaves as expected?
19. UTF-8 or agreed target encoding set?
20. `DateStyle`/`TimeZone`/`IntervalStyle` portable?
21. Consumer handles embedded newlines and quoted fields?
22. CSV formula injection evaluated if opened in spreadsheets?

### Security and Operations

23. Export runs under a least-privilege role?
24. RLS tested under the actual runtime role?
25. No out-of-scope PII or secrets included?
26. Output files protected with ACLs, encryption, and retention?
27. Consistent snapshot enforced across multi-file exports?
28. Large exports evaluated for vacuum, locks, and storage impact?
29. Files written to staging paths and published only on success?
30. Row counts, file size, and checksums recorded?
31. Logs free of sensitive payloads?
32. Runbook ready for retries and cleanup on mid-stream failure?

---

## 32. Summary

PostgreSQL provides `COPY ... TO` to export rows from tables or query results. It is a powerful data-export tool, provided you understand **file destinations, permissions, formats, and snapshots**.

Key takeaways:

- **`COPY ... TO '/server/path'`** writes on the PostgreSQL server's filesystem and requires server-file privileges plus OS access.
- **`COPY ... TO STDOUT`** streams data over the connection. **`psql \copy ... TO 'client/path'`** receives the stream and writes on the `psql` client host without server-file privileges.
- Use **`COPY (SELECT ...) TO`** for filtering, JOINs, aggregates, views, partitioned tables, computed expressions, and deterministic ordering.
- Direct `COPY table TO` does not support every relation kind; the query form is the general solution.
- CSV defines quoting/escaping for delimiters, quotes, and newlines; NULL and empty strings stay distinct via quoting.
- Standardize UTF-8, `DateStyle`, `TimeZone`, and `IntervalStyle` for portable files.
- RLS `SELECT` policies apply to `COPY TO`; always test under the real runtime role.
- Server-side `COPY PROGRAM` is highly privileged; never concatenate untrusted input into shell commands.
- Multi-file exports may require a shared snapshot; use appropriate transaction isolation while mindful of long-snapshot costs.
- Database transactions never roll back client files; stage, verify, and publish only after completion.
- CSV escaping does not protect against spreadsheet formula injection; handle untrusted text per consumer.

**Self-check question:** When running `COPY (SELECT ...) TO '/tmp/report.csv'` from a laptop connected to a cloud database, where is the file written and who needs write permissions? If you want the file on your laptop instead, which command fits? And if the exported query contains tenant data, which privileges and policies enforce row scope? Answering these three questions covers the most important decisions before exporting data from PostgreSQL.

### Official PostgreSQL Documentation

- [COPY — copy data between a file and a table](https://www.postgresql.org/docs/current/sql-copy.html).
- [psql — \copy, frontend copy](https://www.postgresql.org/docs/current/app-psql.html).
- [psql — output formatting, \o, \g, --csv](https://www.postgresql.org/docs/current/app-psql.html).
- [Predefined Roles — pg_read_server_files, pg_write_server_files, pg_execute_server_program](https://www.postgresql.org/docs/current/predefined-roles.html).
- [Row Security Policies](https://www.postgresql.org/docs/current/ddl-rowsecurity.html).
- [COPY Progress Reporting](https://www.postgresql.org/docs/current/progress-reporting.html).
- [Transaction Isolation](https://www.postgresql.org/docs/current/transaction-iso.html).
- [Date/Time Types and TimeZone](https://www.postgresql.org/docs/current/datatype-datetime.html).
- [Client Connection Defaults — client_encoding](https://www.postgresql.org/docs/current/runtime-config-client.html).
- [pgJDBC — Copy API](https://jdbc.postgresql.org/documentation/publicapi/org/postgresql/copy/CopyManager.html).
