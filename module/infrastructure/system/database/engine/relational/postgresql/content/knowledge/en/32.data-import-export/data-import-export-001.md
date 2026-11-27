# Server-Side COPY and Client-Side \copy in PostgreSQL

When you need to import hundreds of thousands of product records from CSV or export millions of report rows, running individual `INSERT` statements or `SELECT` queries and writing files manually is both slow and hard to control. PostgreSQL provides the **`COPY`** SQL command to transfer data in bulk between tables/queries and files or data streams. The **`psql`** command-line tool provides the **`\copy`** meta-command so that reading/writing files takes place on the **machine running psql**, not necessarily the machine running PostgreSQL.

The two approaches look similar in syntax, yet differ significantly in **where the file is opened, required permissions, security, and deployment**.

~~~text
                A. COPY FROM '/server/path/products.csv'

Machine running psql / Java               PostgreSQL Machine
┌─────────────────┐                      ┌──────────────────────┐
│ Client          │   SQL COPY --------> │ PostgreSQL backend   │
│                 │                      │    │                 │
└─────────────────┘                      │    v                 │
                                       │ /server/path/...     │
                                       │ (FILE ON SERVER)     │
                                       └──────────────────────┘


                B. \copy FROM '/client/path/products.csv'

Machine running psql                      PostgreSQL Machine
┌──────────────────────┐                  ┌─────────────────────┐
│ psql                 │                  │ PostgreSQL backend  │
│    │                 │    COPY FROM     │                     │
│    v                 │    STDIN         │                     │
│ /client/path/...     │ ===============> │ target table        │
│ (FILE ON CLIENT)     │  over connection │                     │
└──────────────────────┘                  └─────────────────────┘
~~~

Illustrative example:

~~~sql
-- This is SQL running on the PostgreSQL server.
COPY public.products (sku, name, price)
FROM '/var/lib/postgresql/import/products.csv'
WITH (FORMAT csv, HEADER true);
~~~

~~~text
-- This is a psql meta-command, not standard SQL.
\copy public.products (sku, name, price) FROM '/home/dev/import/products.csv' WITH (FORMAT csv, HEADER true)
~~~

**Core principle:** `COPY ... FROM '/path'` requires the **PostgreSQL server to open the file**, whereas `\copy ... FROM '/path'` requires the **psql client to open the file** and stream its contents to the server via `COPY FROM STDIN`. Choosing the wrong one can cause a "file not found" error even when the file exists, or force the application to require dangerous server-file privileges.

This lesson is a self-contained document in the **Data Import and Export** chapter of the *Database Engine Relational PostgreSQL* module, covering data locations, permissions, import/export syntax, CSV/TEXT/BINARY, `STDIN/STDOUT`, `NULL` handling, staging tables, transactions, JDBC applications, security, and exercises with solutions.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Accurately explain that **`COPY` is server-side SQL** and **`\copy` is a psql client-specific command**.
2. Predict which machine will read/write the file in each example, including when the client runs in a container or on a remote host.
3. Use `COPY FROM` and `COPY TO` properly with tables, column lists, and `SELECT` queries.
4. Use `COPY FROM STDIN`/`TO STDOUT` to stream over a single connection without requiring the server to access external paths.
5. Use `\copy ... FROM/TO 'file.csv' WITH (FORMAT csv, HEADER true)` for files on the client machine.
6. Distinguish table `SELECT/INSERT` privileges from permissions to read/write files or execute programs on the server.
7. Know when `pg_read_server_files`, `pg_write_server_files`, `pg_execute_server_program`, or superuser is required, and why they are sensitive.
8. Recognize the differences among `FORMAT text`, `FORMAT csv`, and `FORMAT binary`.
9. Control `DELIMITER`, `HEADER`, `QUOTE`, `ESCAPE`, `NULL`, and the column list.
10. Understand the difference between **SQL NULL**, empty strings, and literal `NULL` when working with CSV.
11. Design an import pipeline **file → staging → validation → target table** without silently dropping invalid rows.
12. Use transactions and rollbacks to avoid unintended partial import results.
13. Understand the impact of `COPY` on triggers, constraints, identity columns, indexes, WAL, autovacuum, and locking.
14. Know how to import/export via PGJDBC `CopyManager` instead of trying to run `\copy` as SQL.
15. Diagnose path, permission, encoding, malformed CSV, data type mismatch, and locking errors.
16. Monitor progress using `pg_stat_progress_copy` when supported by the PostgreSQL version.
17. Choose among `COPY`, `\copy`, JDBC batch, ETL, or `pg_dump/pg_restore` based on your goal.

## 2. COPY and \copy: Same Goal, Different Execution Location

### 2.1. COPY Is a PostgreSQL SQL Command

~~~sql
COPY schema.table_name
FROM '/absolute/path/on/database/server/file.csv'
WITH (FORMAT csv, HEADER true);
~~~

SQL is sent to PostgreSQL. When the source is a **filename**, the PostgreSQL process on the server looks for the file on the **filesystem visible to the backend** and opens it using the operating system privileges of the service account.

### 2.2. \copy Is a psql Meta-Command

~~~text
\copy schema.table_name FROM '/path/on/psql/client/file.csv' WITH (FORMAT csv, HEADER true)
~~~

The `\` prefix marks a `psql` meta-command. The PostgreSQL server does not understand `\copy` syntax if it is sent via JDBC or a tool that only executes SQL.

### 2.3. What Does psql Do Under the Hood?

For `\copy ... FROM '/path'`, psql opens the file on the client side and sends its contents to the server using the **`COPY ... FROM STDIN`** mechanism. For `\copy ... TO '/path'`, it reads the **`COPY ... TO STDOUT`** stream and writes it to the file on the client side.

### 2.4. Role of the Connection

With `\copy`, data travels over the client–server connection. If the connection uses TLS, the COPY stream is protected by TLS over that hop; however, the file on the client still requires its own security policies.

### 2.5. There Is No "\copy Inside PostgreSQL"

`\copy` only exists in clients that implement the corresponding meta-command, most commonly `psql`. Do not write `\copy` inside a SQL function, view, trigger, or JDBC `PreparedStatement`.

## 3. Quick Comparison Table

| Criterion | SQL `COPY` with file path | `psql \copy` with file path |
| --- | --- | --- |
| Who opens the file? | PostgreSQL backend on the server | psql process on the client |
| Where does the path reside? | Filesystem of the server/container running the DB | Filesystem of the host/container running psql |
| Operating system privileges | PostgreSQL service account | Account running psql |
| Special DB file permissions | Yes, when using server file/PROGRAM | Not needed solely for opening a client file |
| Table privileges still required? | Yes | Yes |
| Does data travel over client–server? | SQL command; file opened directly by DB | Yes, via STDIN/STDOUT |
| Can it run in JDBC as SQL? | Yes for server-file COPY if privileged; STDIN/STDOUT requires protocol API | No |
| Useful when file is on laptop | Usually no | Very suitable |
| Useful when file is on DB server | Suitable if permitted | Only if psql can also see that file |
| Cloud DB operability | Server file permissions are often restricted | Usually easier to use |
| File permission risk | Permissions on DB server are very sensitive | File/command risks reside on client side |
| Common import direction | `COPY FROM file` | `\copy FROM file` |
| Common export direction | `COPY TO file` | `\copy TO file` |

**Note:** SQL `COPY ... FROM STDIN`/**`TO STDOUT`** does not open a server file, so it does not require the corresponding server-file privileges just to use the stream. This is the core mechanism that enables client libraries like PGJDBC to stream data.

## 4. An Easily Confused File Location Example

Suppose:

~~~text
Personal laptop:
  /home/an/data/products.csv

PostgreSQL machine:
  /var/lib/postgresql/data/
  no /home/an/data/products.csv
~~~

You connect from your laptop:

~~~bash
psql "host=db.example.internal dbname=shop user=importer sslmode=verify-full"
~~~

and run:

~~~sql
COPY public.products
FROM '/home/an/data/products.csv'
WITH (FORMAT csv, HEADER true);
~~~

The server will attempt to open `/home/an/data/products.csv` **on the database machine**, not the laptop. A "could not open file" error does not prove the laptop file is missing; it simply means **the path is being resolved from a different machine**.

Fix it using:

~~~text
\copy public.products FROM '/home/an/data/products.csv' WITH (FORMAT csv, HEADER true)
~~~

provided the OS account running psql has read permission on the file and the database role has `INSERT` privilege on the table.

## 5. Learning Workflow with a CSV File

We will create a lab schema and import the file:

~~~csv
sku,product_name,unit_price_text,stock_text
KB-01,"Bàn phím, cơ",850000.00,8
MS-02,"Chuột ""siêu nhẹ""",299000.00,15
HM-03,Tai nghe,620000.50,3
~~~

Where:

- The `product_name` column in the first row contains a **comma**, so it must be enclosed in double quotes.
- The mouse name contains double-quote characters; in default CSV, a `"` character inside a value is represented as `""`.
- The data contains Vietnamese characters, so the encoding must be consistent.
- We initially import numeric columns into **text columns** so we can inspect data errors before casting.

### 5.1. Target After Processing

| SKU | Product Name | Price | Stock |
| --- | --- | ---: | ---: |
| KB-01 | Bàn phím, cơ | 850000.00 | 8 |
| MS-02 | Chuột "siêu nhẹ" | 299000.00 | 15 |
| HM-03 | Tai nghe | 620000.50 | 3 |

### 5.2. Using Staging Instead of Direct Insertion

~~~text
products.csv
     |
     v
\copy FROM local file
     |
     v
import_lab.product_stage (raw text)
     |
     +--- check missing/blank columns
     +--- check format and value ranges
     +--- detect duplicate SKUs
     +--- normalize
     |
     v
INSERT ... SELECT ... ON CONFLICT
     |
     v
import_lab.products (clean data)
~~~

For files of uncertain quality, staging lets you report **specific input errors** rather than just receiving an "invalid input syntax" exception on some row of a long import command.

## 6. Creating the Lab Schema and Tables

Execute on a test database:

~~~sql
CREATE SCHEMA import_lab;

CREATE TABLE import_lab.product_stage (
    stage_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sku text,
    product_name text,
    unit_price_text text,
    stock_text text,
    imported_at timestamptz NOT NULL DEFAULT clock_timestamp()
);

CREATE TABLE import_lab.products (
    product_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sku text NOT NULL UNIQUE,
    product_name text NOT NULL,
    unit_price numeric(14,2) NOT NULL
        CHECK (unit_price >= 0),
    stock integer NOT NULL
        CHECK (stock >= 0),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
~~~

### 6.1. Why Does Staging Use text?

If the file has `unit_price_text='not-a-number'` or `stock_text='five'`, importing into text columns is not immediately rejected by numeric/integer casting. We can run validation queries and report invalid rows.

### 6.2. Why Is stage_id Auto-Generated?

`stage_id` identifies staging rows for easier error investigation. We **omit** `stage_id` from the CSV and the COPY column list so the identity value is generated automatically.

### 6.3. Why Does the Target Table Have CHECK and UNIQUE?

`COPY` does not replace constraints. The final data must still be protected by the database even if another application writes directly to the table.

### 6.4. Keep the Lab Environment Isolated

Operations such as `TRUNCATE` or re-importing below are strictly for the test schema. Do not use a production `products` table or `DROP ... CASCADE` just to run examples.

## 7. Creating the CSV on the Machine Running psql

Save the following content to a file, for example `/home/dev/import/products.csv` on the Linux/macOS machine running `psql`:

~~~csv
sku,product_name,unit_price_text,stock_text
KB-01,"Bàn phím, cơ",850000.00,8
MS-02,"Chuột ""siêu nhẹ""",299000.00,15
HM-03,Tai nghe,620000.50,3
~~~

### 7.1. The File Must Be UTF-8

Save the file in UTF-8, matching `client_encoding` when connecting. Do not merely look at "Vietnamese diacritics appearing fine" in an editor and assume the byte encoding is correct.

### 7.2. Watch Out for File Location in Containers

If you run:

~~~bash
docker exec -it postgres psql -U postgres -d labdb
~~~

then `psql` **runs inside the container**. `\copy FROM '/home/dev/import/products.csv'` will then look for the file inside the container's filesystem, not on the host laptop.

### 7.3. If psql Runs Directly on the Laptop

~~~bash
psql "host=localhost port=5432 dbname=labdb user=lab_user"
~~~

then `\copy` sees the laptop's files, even if the PostgreSQL server is inside a container.

### 7.4. Windows

With psql running on Windows, use an appropriate client path, such as `C:/Data/products.csv`. Do not use a Unix path from a Linux example and expect Windows to find it. In PowerShell/cmd, **shell** quoting and **psql meta-command** parsing are two separate layers.

## 8. Importing CSV with Client-Side \copy

In a `psql` session connected to the right database:

~~~text
\copy import_lab.product_stage (sku, product_name, unit_price_text, stock_text) FROM '/home/dev/import/products.csv' WITH (FORMAT csv, HEADER true, ENCODING 'UTF8')
~~~

### 8.1. This Is a Single psql Command Line

`\copy` is a `psql` meta-command and has its own parsing rules. For basic commands, write the entire `\copy` command on **one line** in psql scripts to avoid multiline continuation errors that behave differently from regular SQL.

### 8.2. Conditions for Success

- The file exists **on the machine running psql**.
- The OS user running psql has permission to read the file.
- The PostgreSQL role has `INSERT` privilege on the target table/columns.
- The file is actually CSV and its columns match the column list.
- The encoding and data match the configured options.

### 8.3. Table Privilege Requirements Still Apply

`\copy` does not "bypass" SQL permissions. If the database role lacks `INSERT`, the import fails even if the local file is readable.

### 8.4. Why Specify the Column List?

The staging table has `stage_id` and `imported_at`, while the file only contains four columns. Specifying:

~~~sql
(sku, product_name, unit_price_text, stock_text)
~~~

ensures `COPY` does not attempt to push `sku` into `stage_id` due to table column positions differing from the file.

### 8.5. Inspecting Imported Rows

~~~sql
SELECT stage_id, sku, product_name,
       unit_price_text, stock_text
FROM import_lab.product_stage
ORDER BY stage_id;
~~~

You should expect three rows with properly decoded content and no CSV enclosing quotes remaining in the values.

## 9. Importing with Server-Side COPY

If the file has actually been placed **on the database server** at `/var/lib/postgresql/import/products.csv`:

~~~sql
COPY import_lab.product_stage (
    sku,
    product_name,
    unit_price_text,
    stock_text
)
FROM '/var/lib/postgresql/import/products.csv'
WITH (
    FORMAT csv,
    HEADER true,
    ENCODING 'UTF8'
);
~~~

### 9.1. The Server Must Be Able to See the File

The file can reside on a volume mount of a PostgreSQL container, a server host directory, or a network filesystem visible to the backend. A file located only on a client laptop cannot be read by this SQL statement.

### 9.2. OS User Differs from Database Role

The PostgreSQL backend opens the file using the OS service account running the database process. OS `chmod`/ACLs are distinct from `GRANT INSERT` in PostgreSQL.

### 9.3. Appropriate Server-File Privileges Are Required

SQL `COPY FROM '/server/file'` is only allowed for superusers or roles holding privileges such as `pg_read_server_files` depending on PostgreSQL version/rules. These privileges are highly sensitive and should not be granted to ordinary application accounts.

### 9.4. Absolute Paths

For server-file `COPY FROM`, PostgreSQL requires an absolute path for the filename. Do not use a relative path like `'products.csv'` expecting it to be found in your laptop's current working directory.

### 9.5. Practical Choice

In many managed PostgreSQL environments, arbitrary server filesystem read access is unavailable. `\copy` or an application using `COPY FROM STDIN` is usually the more appropriate solution.

## 10. COPY TO: Exporting Files on the Server Side

~~~sql
COPY import_lab.products (
    sku, product_name, unit_price, stock
)
TO '/var/lib/postgresql/export/products.csv'
WITH (
    FORMAT csv,
    HEADER true,
    ENCODING 'UTF8'
);
~~~

### 10.1. The Exported File Resides on the Server

The file is created by the PostgreSQL backend at the server path; it **does not automatically appear on the laptop** that sent the SQL.

### 10.2. Server File Write Privileges

Server-file `COPY TO` requires privileges such as `pg_write_server_files` or superuser according to PostgreSQL rules, and the target directory must be writable by the database process.

### 10.3. Do Not Write Arbitrarily into the Data Directory

Do not use the PostgreSQL data directory as an ad-hoc drop zone for exported CSV reports. Separate export paths with managed quotas, retention, and permissions to avoid impacting database storage.

### 10.4. Non-Overwriting Behavior of COPY TO File

When server-side `COPY TO 'filename'` creates a file, PostgreSQL generally refuses if the destination file already exists, preventing accidental overwrite of important data. Manage versioned filenames and controlled cleanup of old files; do not design scripts that rely on implicit overwriting.

### 10.5. Files on Another Machine Require a Retrieval Step

If users need to download exports to their laptops, a simpler option is to use `\copy ... TO local-file` directly from psql on the laptop.

## 11. \copy TO: Exporting Files Directly on the Client Machine

In psql:

~~~text
\copy import_lab.products (sku, product_name, unit_price, stock) TO '/home/dev/export/products.csv' WITH (FORMAT csv, HEADER true, ENCODING 'UTF8')
~~~

### 11.1. psql Opens the Output File

The path `/home/dev/export/products.csv` belongs to the **machine running psql**, not the PostgreSQL server. The OS user running psql needs write permission on `/home/dev/export`.

### 11.2. The Database Role Needs SELECT

The client can only export columns and rows allowed by SQL permissions and applicable data policies. `\copy` does not elevate table read privileges.

### 11.3. Data Travels Over the Network

PostgreSQL sends data over the COPY protocol to psql, and psql writes the file. For large exports, evaluate network bandwidth, duration, and client disk space.

### 11.4. Exported Files Need Protection

If the export contains emails, phone numbers, or sensitive information, the exported CSV on user disk is no longer automatically governed by PostgreSQL RLS/GRANT. File permissions, retention, encryption-at-rest, and storage location must be controlled.

## 12. Exporting Query Results Instead of an Entire Table

`COPY TO` supports a query enclosed in parentheses:

~~~sql
COPY (
    SELECT
        sku,
        product_name,
        unit_price,
        stock
    FROM import_lab.products
    WHERE stock > 0
    ORDER BY sku
)
TO STDOUT
WITH (FORMAT csv, HEADER true);
~~~

This is SQL `COPY (query) TO STDOUT`. Clients supporting the COPY protocol can receive the data stream directly over the connection.

### 12.1. With \copy in psql

~~~text
\copy (SELECT sku, product_name, unit_price, stock FROM import_lab.products WHERE stock > 0 ORDER BY sku) TO '/home/dev/export/in_stock.csv' WITH (FORMAT csv, HEADER true)
~~~

### 12.2. Why Use a Query?

It allows you to:

- Select a subset of columns.
- Filter with `WHERE`.
- Combine tables with `JOIN`.
- Compute expressions and set aliases.
- Sort output when deterministic order is needed.
- Mask or omit columns not permitted for export.

### 12.3. Do Not Rely on Physical Table Order

If you want a deterministic export order for file comparison or snapshot testing, use `ORDER BY` in the query. `COPY table TO` makes no guarantee about business-logical row ordering.

### 12.4. Column Names in the CSV Header

When using `HEADER true` with a query, the query column names or aliases are used to generate the header according to PostgreSQL behavior.

## 13. COPY FROM STDIN and TO STDOUT

PostgreSQL does not require data to reside in a server file. Two very important options are:

~~~sql
COPY import_lab.product_stage (
    sku, product_name, unit_price_text, stock_text
)
FROM STDIN
WITH (FORMAT csv, HEADER true);
~~~

~~~sql
COPY (
    SELECT sku, product_name, unit_price, stock
    FROM import_lab.products
)
TO STDOUT
WITH (FORMAT csv, HEADER true);
~~~

### 13.1. STDIN Is Not Necessarily the Database OS Stdin

In the PostgreSQL protocol, `COPY FROM STDIN` receives a data stream **from the client over the connection**. The PostgreSQL backend does not read directly from the server machine's keyboard.

### 13.2. STDOUT Is a Stream to the Client

`COPY TO STDOUT` sends data over the COPY protocol. The client decides whether to write it to a file, pipe it, or process it in memory as appropriate.

### 13.3. Why Does \copy Rely on STDIN/STDOUT?

Psql opens the local file and then uses the COPY protocol. As a result, it does not require granting server OS file read/write privileges to the application role.

### 13.4. JDBC Requires the COPY API

A standard `PreparedStatement.executeQuery("COPY ... TO STDOUT")` is not the appropriate streaming COPY interface. PGJDBC provides `CopyManager`/the COPY API for this purpose.

## 14. COPY FROM STDIN in Interactive psql

Psql can accept inline data immediately after the SQL command:

~~~text
COPY import_lab.product_stage (sku, product_name, unit_price_text, stock_text) FROM STDIN WITH (FORMAT csv, HEADER true);
sku,product_name,unit_price_text,stock_text
KB-01,"Bàn phím, cơ",850000.00,8
MS-02,"Chuột ""siêu nhẹ""",299000.00,15
\.
~~~

### 14.1. \. Is the End-of-Data Marker in psql

When psql is accepting data for `COPY FROM STDIN`, a line containing only `\.` marks the end of the data stream in psql/script mode.

### 14.2. Do Not Add SQL Semicolons to Data Rows

CSV lines are **data**, not SQL statements terminated by `;`. Psql distinguishes the COPY data phase from sending the next SQL statement.

### 14.3. Commands with HEADER true

The start of the data stream in the example includes a header; PostgreSQL skips the header row under this setting. If you omit the header while keeping `HEADER true`, the first data row will be treated as a header and skipped.

### 14.4. Not Suitable for Manual Large Imports

This illustrates the mechanism. For large files, use `\copy FROM 'filename'` or the PGJDBC COPY API instead of pasting millions of lines into a terminal.

## 15. \copy FROM STDIN and Piping

The `\copy` meta-command can also read from client stdin:

~~~text
\copy import_lab.product_stage (sku, product_name, unit_price_text, stock_text) FROM stdin WITH (FORMAT csv, HEADER true)
~~~

With `\copy ... FROM stdin` in an appropriate psql setup, data is read from psql's input source. When building shell pipelines, distinguish between:

- Standard input of the **shell/psql process**.
- The input psql uses to read SQL commands/meta-commands.
- The COPY data stream from stdin/pstdin supplied by psql.

### 15.1. Pipeline Structures Need Dedicated Testing

Shell quoting and psql parsing can cause a command with multiple `\` characters to behave differently across Bash, PowerShell, and cmd. When an automation script needs to import from a pipe, pick syntax compatible with your psql version and test it in practice, rather than assuming a command string in one shell transfers verbatim.

### 15.2. Avoid File Paths When Streaming Is Desired

For a Java service downloading files from object storage, you can stream an InputStream into PostgreSQL using `CopyManager` without writing files to the database server.

### 15.3. Validate the Input Stream

The STDIN stream must still have the right format, encoding, and column structure. The server will not automatically parse a JSON or Excel file as CSV simply because you specify `FORMAT csv`.

## 16. FORMAT text, csv, and binary

`COPY` supports multiple formats; do not confuse them with one another.

| Format | Data Form | Pros | Risks/Limitations |
| --- | --- | --- | --- |
| `text` | Delimited text with PostgreSQL-specific escaping | Simple, works well in many cases | Differs from CSV quoting |
| `csv` | CSV with delimiter, quote, escape, header | Compatible with many data tools | Must handle delimiters, NULL, quotes, and newlines |
| `binary` | PostgreSQL COPY binary format | Fast/avoids text conversion loss in suitable cases | Not a CSV file, less portable across schemas/versions/types |

### 16.1. FORMAT text

~~~sql
COPY import_lab.products TO STDOUT
WITH (FORMAT text);
~~~

The default text format typically uses TAB as the delimiter and `\N` for NULL, with specific escaping rules for tab, newline, and backslash characters.

### 16.2. FORMAT csv

~~~sql
COPY import_lab.products TO STDOUT
WITH (FORMAT csv, HEADER true);
~~~

Default CSV typically uses comma delimiters, double quotes as the quote character, and CSV quote-escaping rules.

### 16.3. FORMAT binary

~~~sql
COPY import_lab.products TO STDOUT
WITH (FORMAT binary);
~~~

Binary is unsuitable for opening in spreadsheets or text editors. Its contents depend on PostgreSQL type representations, and binary format is not a neutral interchange format across arbitrary database systems.

### 16.4. Do Not Mix Up Formats

A CSV file with headers cannot be arbitrarily imported with `FORMAT text` while expecting PostgreSQL to handle commas and quotes automatically.

## 17. HEADER: The Header Row

When importing:

~~~sql
COPY import_lab.product_stage (
    sku, product_name, unit_price_text, stock_text
)
FROM STDIN
WITH (FORMAT csv, HEADER true);
~~~

`HEADER true` tells PostgreSQL that the input has a header row to ignore during import. It **does not automatically map arbitrary header names to column names** in all modes/versions.

### 17.1. The Column List Determines Order

If the file has:

~~~csv
sku,product_name,unit_price_text,stock_text
~~~

then the column list must match the **actual order of data in the file**, unless you actively transform the file or use a specific supported feature.

### 17.2. Even an Incorrect Header May Be Ignored

With basic `HEADER true`, PostgreSQL does not necessarily verify that the header text matches the column names exactly. Versions supporting the `HEADER MATCH` option enforce stricter checking; confirm your server version's capabilities.

### 17.3. HEADER false

If the file has no header row, specify:

~~~sql
WITH (FORMAT csv, HEADER false)
~~~

or omit the HEADER option for that format. If accidentally set to true, the first data row will be discarded because it is interpreted as a header.

### 17.4. Exporting Files

`HEADER true` during `COPY TO` adds a column-name row, making the file self-describing. It is optional if the downstream consumer expects raw data without headers.

## 18. DELIMITER, QUOTE, ESCAPE

Common CSV uses:

~~~sql
WITH (
    FORMAT csv,
    DELIMITER ',',
    QUOTE '"',
    ESCAPE '"',
    HEADER true
)
~~~

### 18.1. DELIMITER

The field separator, usually a comma. Another character can be used, for example:

~~~sql
WITH (FORMAT csv, DELIMITER ';', HEADER true)
~~~

if the file is actually semicolon-delimited CSV.

### 18.2. QUOTE

The character enclosing fields that contain delimiters or control characters requiring quoting, typically `"`.

### 18.3. ESCAPE

The character used to escape quotes; by default in CSV it is the same as QUOTE. Two consecutive double quotes represent one literal double quote in the value.

### 18.4. Example with a Comma in the Name

~~~csv
KB-01,"Bàn phím, cơ",850000.00,8
~~~

The name value remains `Bàn phím, cơ` and is not split into two fields.

### 18.5. Example with Quotes in the Name

~~~csv
MS-02,"Chuột ""siêu nhẹ""",299000.00,15
~~~

The parsed value is `Chuột "siêu nhẹ"`.

### 18.6. Fields Containing Newlines

A CSV cell may contain newlines if properly quoted. Never use a custom `split("\n")` followed by `split(",")` to mimic a CSV parser for complex data.

## 19. SQL NULL vs. Empty String in CSV

This is one of the most common sources of silent data corruption during import.

### 19.1. Default CSV Behavior

With `FORMAT csv` and default settings, an **unquoted empty** field normally represents SQL `NULL`, whereas a **quoted empty** field (`""`) represents an empty text string.

For example:

~~~csv
sku,product_name,unit_price_text,stock_text
AA-01,,100.00,5
BB-02,"",100.00,5
~~~

When read into a text column, `AA-01` gets `product_name IS NULL`, while `BB-02` gets `product_name = ''` under default CSV rules.

### 19.2. NULL 'NULL'

You can specify an explicit token:

~~~sql
WITH (
    FORMAT csv,
    NULL 'NULL',
    HEADER true
)
~~~

Then the unquoted literal `NULL` is treated as the NULL marker. However, if valid data can contain the literal string `NULL`, you must understand how quoting distinguishes them.

### 19.3. Text Format Differs from CSV

In `FORMAT text`, the default NULL marker is `\N`. Do not assume `\N` is always the NULL marker for every CSV file; the format and `NULL` option determine this.

### 19.4. FORCE_NULL

In CSV imports where even **quoted** values matching the null string should become SQL NULL, the `FORCE_NULL` option on the relevant columns can help.

### 19.5. FORCE_NOT_NULL

`FORCE_NOT_NULL` prevents unquoted null strings from being interpreted as SQL NULL for specified CSV columns. This is useful when an upstream system exports empty fields that business logic requires to be empty strings.

### 19.6. Do Not Guess Data Semantics from the File

Before importing into production, define the data contract: does an empty field mean *no value*, *empty string*, *0*, or *default value*? Do not casually set `NULL ''` and lose the distinction.

## 20. Column Lists and DEFAULT

Given a table:

~~~sql
CREATE TABLE import_lab.products (
    product_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sku text NOT NULL UNIQUE,
    product_name text NOT NULL,
    unit_price numeric(14,2) NOT NULL,
    stock integer NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
~~~

When importing, specify:

~~~sql
COPY import_lab.products (
    sku, product_name, unit_price, stock
)
FROM STDIN
WITH (FORMAT csv, HEADER true);
~~~

Columns omitted from the list use their defaults or null/constraint rules per PostgreSQL behavior. Here, `product_id` generates an identity value and `updated_at` gets its default.

### 20.1. Do Not Assume Table Column Order Never Changes

Adding a column in a migration can break older files if you use `COPY table FROM ...` without a column list.

### 20.2. Explicit NULL Differs from Omitted Column

If the CSV includes `updated_at` and the value is parsed as SQL NULL, PostgreSQL does not automatically fall back to `DEFAULT clock_timestamp()` just because the cell is blank. **Omitting a column from the COPY list** and **including the column with a NULL value** are two distinct cases.

### 20.3. GENERATED/IDENTITY

For identity columns, understand `COPY` rules in your PostgreSQL version: if the file provides values for an identity column, PostgreSQL may use the supplied values instead of auto-generating them as it does when the column is omitted. When you want new IDs generated, **exclude the identity column** from the column list.

### 20.4. Generated Columns

Stored/generated columns have specific restrictions against direct value insertion. Do not export and re-import all columns without checking generated column metadata.

## 21. ENCODING and Vietnamese Text

A file containing:

~~~csv
sku,product_name,unit_price_text,stock_text
TV-01,Bộ gõ tiếng Việt,99000.00,12
~~~

### 21.1. Client Encoding

`COPY`/`\copy` processes text according to the specified encoding or `client_encoding` per version rules. If the file is UTF-8 but the client uses a different encoding, transcoding errors or character corruption can occur.

### 21.2. Specify ENCODING When Supported

~~~sql
WITH (FORMAT csv, HEADER true, ENCODING 'UTF8')
~~~

The encoding option for COPY is supported in modern PostgreSQL versions; when working with older servers, check syntax or set `client_encoding` appropriately.

### 21.3. UTF-8 BOM

Some applications save UTF-8 CSV files with a leading **byte-order mark (BOM)**. If the import tool does not strip the BOM as expected, the BOM character may attach to the first header column name or first value. Verify against real files and normalize during preprocessing if necessary.

### 21.4. Do Not Guess Encoding by Sight

Windows-1258, UTF-8, or UTF-16 files may look fine in an editor while having completely different byte representations. PostgreSQL will not automatically "fix" a UTF-16 file into UTF-8 merely because `FORMAT csv` is specified.

### 21.5. Normalize Inputs

Design your pipeline to validate byte encoding and file format at the boundary rather than waiting until row 50,000 fails with "invalid byte sequence".

## 22. Dates, Times, Decimals, and Locale

CSV is a text format; PostgreSQL must cast values to the target column types.

### 22.1. Monetary Values

~~~csv
sku,unit_price
AA-01,1234.50
~~~

`numeric` generally expects a decimal point in SQL syntax. If a file uses `1.234,50` due to locale formatting, normalize it according to a clear contract; do not simply replace all commas, since the CSV delimiter may also be a comma.

### 22.2. Dates and Times

Use ISO 8601 with explicit timezone/offset when needed:

~~~text
2026-11-14T09:30:00+07:00
~~~

### 22.3. DateStyle

How PostgreSQL interprets certain ambiguous date strings can depend on `DateStyle`. For cross-system imports, avoid ambiguous strings like `01/02/26` where month/day vs. day/month is unclear.

### 22.4. Time Zone

If a column is `timestamptz` and the file omits a timezone, interpretation can depend on the session time zone. Standardize on UTC or an explicit offset per contract.

### 22.5. Staging and Validation Before Casting

For external files, load dates and numbers into text staging columns first, then run validation queries or controlled conversions so you can record row-level error messages.

## 23. Validating Staging Data

After running `\copy`, before moving data into the target table, inspect invalid rows.

### 23.1. Finding Malformed SKUs

~~~sql
SELECT stage_id, sku
FROM import_lab.product_stage
WHERE sku IS NULL
   OR upper(btrim(sku)) !~ '^[A-Z0-9-]{3,24}$';
~~~

### 23.2. Finding Blank Names

~~~sql
SELECT stage_id, product_name
FROM import_lab.product_stage
WHERE product_name IS NULL
   OR btrim(product_name) = '';
~~~

### 23.3. Finding Invalid Prices

~~~sql
SELECT stage_id, unit_price_text
FROM import_lab.product_stage
WHERE unit_price_text IS NULL
   OR unit_price_text
      !~ '^[0-9]{1,12}([.][0-9]{1,2})?$';
~~~

This regex accepts only non-negative numbers with up to 12 integer digits and up to 2 decimal places; it is a **lab rule**, not a universal international currency parser.

### 23.4. Finding Invalid Stock Formats

~~~sql
SELECT stage_id, stock_text
FROM import_lab.product_stage
WHERE stock_text IS NULL
   OR stock_text !~ '^[0-9]{1,9}$';
~~~

The example permits up to 9 non-negative digits to ensure casting to PostgreSQL `integer` will not overflow solely due to an overly large number.

### 23.5. Detecting Duplicate SKUs Within the Same File

~~~sql
SELECT
    upper(btrim(sku)) AS normalized_sku,
    count(*) AS occurrences
FROM import_lab.product_stage
GROUP BY upper(btrim(sku))
HAVING count(*) > 1;
~~~

Two SKUs `kb-01` and `KB-01` may be considered duplicates after normalization, depending on business rules.

### 23.6. Never Silently Drop Invalid Rows

An `INSERT SELECT` that filters only valid rows without recording an error report can make an import appear to "succeed" while losing data. A pipeline must have a transparent fail-all, quarantine, or partial-acceptance policy.

## 24. Transactionally Promoting Staging → Target Table

Assuming a batch's file has been staged, we can use a transaction to ensure **no merge happens while staging still contains invalid rows**.

~~~sql
BEGIN;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM import_lab.product_stage
        WHERE sku IS NULL
           OR upper(btrim(sku)) !~ '^[A-Z0-9-]{3,24}$'
           OR product_name IS NULL
           OR btrim(product_name) = ''
           OR unit_price_text IS NULL
           OR unit_price_text
               !~ '^[0-9]{1,12}([.][0-9]{1,2})?$'
           OR stock_text IS NULL
           OR stock_text !~ '^[0-9]{1,9}$'
    ) THEN
        RAISE EXCEPTION 'Product stage contains invalid rows';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM import_lab.product_stage
        GROUP BY upper(btrim(sku))
        HAVING count(*) > 1
    ) THEN
        RAISE EXCEPTION 'Duplicate SKU inside import batch';
    END IF;
END;
$$;

INSERT INTO import_lab.products (
    sku,
    product_name,
    unit_price,
    stock
)
SELECT
    upper(btrim(sku)),
    btrim(product_name),
    unit_price_text::numeric(14,2),
    stock_text::integer
FROM import_lab.product_stage
ON CONFLICT (sku)
DO UPDATE SET
    product_name = EXCLUDED.product_name,
    unit_price = EXCLUDED.unit_price,
    stock = EXCLUDED.stock,
    updated_at = clock_timestamp()
WHERE (import_lab.products.product_name,
       import_lab.products.unit_price,
       import_lab.products.stock)
   IS DISTINCT FROM
      (EXCLUDED.product_name,
       EXCLUDED.unit_price,
       EXCLUDED.stock);

COMMIT;
~~~

### 24.1. If the DO Block Raises an Exception

The transaction enters an aborted state. In automated scripts, enable `psql -v ON_ERROR_STOP=1` or an equivalent mechanism to **halt immediately**, then roll back under the transaction owner rather than continuing subsequent steps and reporting success.

### 24.2. Why Check Duplicates Before ON CONFLICT?

If a single `INSERT ... ON CONFLICT DO UPDATE` receives multiple rows with the same target key in **one statement**, it can fail because it cannot affect the same target row multiple times as intended. Normalize and deduplicate within the batch before merging.

### 24.3. Why Use WHERE ... IS DISTINCT FROM?

It avoids issuing an UPDATE for rows with no actual changes, reducing WAL, index churn, and trigger side effects. This is especially important when running repeated imports on overlapping data.

### 24.4. Do Not Copy Everything Blindly to Production

If a file contains entities requiring relational validation, currency codes, categories, tenants, or other business invariants, add corresponding validations before promotion.

### 24.5. The Lab Does Not Distinguish Multiple Staging Batches

In production, staging needs a batch ID/import job ID, unique constraints, status, source checksum, and retention; do not promote an entire shared staging table across multiple files without scoping.

## 25. Importing and Promoting in the Same Transaction

When you want staging and target table changes to roll back together on failure, psql can run:

~~~text
BEGIN;
TRUNCATE import_lab.product_stage;
\copy import_lab.product_stage (sku, product_name, unit_price_text, stock_text) FROM '/home/dev/import/products.csv' WITH (FORMAT csv, HEADER true)
-- Run the validation and INSERT ... SELECT statements above, without nested BEGIN.
COMMIT;
~~~

This is a **workflow outline**, not a ready-to-run script with a comment standing in for validation. For automation, place the full validation/merge statements in the script, enable `ON_ERROR_STOP`, and ensure each transaction has a single owner.

### 25.1. \copy Participates in the Current Transaction

Psql uses the same connection to send `COPY FROM STDIN`, so if a `BEGIN` is active, data loaded by `\copy` belongs to that transaction.

### 25.2. Mid-Stream Failures

A CSV parse error or constraint violation during COPY causes the statement to fail. In a normal transaction, PostgreSQL will reject further SQL commands until you roll back (or roll back to an appropriate savepoint).

### 25.3. All-or-Nothing vs. Batch Commits

If a file of hundreds of gigabytes is split into 100 batches, committing each batch avoids a massive transaction but sacrifices the ability to roll back the **entire file** with a single ROLLBACK. You will need checkpoints, import IDs, and a resume plan.

### 25.4. Do Not Hold Transactions Open While Waiting on Network Downloads

Fetch and verify the file on the client before starting the transaction; holding a transaction open while waiting on external I/O can prolong locks/snapshots and tie up connections.

## 26. COPY and Constraints, Triggers, and Rules

PostgreSQL executes `COPY FROM` as a table write operation with specific rules—it does not bypass the entire schema.

### 26.1. CHECK and NOT NULL

Data violating constraints is rejected. For example, `stock = -1` cannot enter `import_lab.products` when `CHECK (stock >= 0)` is enforced.

### 26.2. UNIQUE and PRIMARY KEY

Indexes and constraints are still updated and checked. If a file has duplicate SKUs, a direct COPY into the target table can raise a duplicate-key error.

### 26.3. FOREIGN KEY

COPY FROM enforces foreign-key checks where applicable. Do not treat it as a way to bypass relational integrity.

### 26.4. Triggers

COPY FROM on a target table fires applicable triggers and enforces CHECK constraints. If a row trigger writes audit records or executes heavy logic, loading millions of rows can take considerably longer.

### 26.5. Rules

By PostgreSQL design, `COPY FROM` **does not fire rewrite rules** the way standard `INSERT` statements can. If an application relies on rules to route or transform data, do not assume COPY follows the same path.

### 26.6. RLS

`COPY FROM` does not directly support importing into tables with row-level security enabled under certain PostgreSQL rules; when loading under RLS, use an appropriate `INSERT` path or staging with well-designed roles, permissions, and policies. Do not disable RLS just for faster imports without reviewing access control.

## 27. COPY and Partitioned Tables

A partitioned table can accept COPY under supported mechanisms/versions; PostgreSQL routes rows to partitions based on the partition key.

### 27.1. Out-of-Range Partition Data

If no matching partition exists (and there is no default partition), COPY FROM can fail because there is no partition to hold the row.

### 27.2. Triggers on Partitions

Row triggers on partitioned tables/partitions may execute according to row-routing semantics; statement-level triggers follow the targeted relation and specific version semantics. Test with realistic workloads when auditing is enabled.

### 27.3. Do Not Implicitly Assume the File Is Sorted

If a file spans many days or months, PostgreSQL still must route each row by key. Consider partitioning, index maintenance, and import ordering if measurements show an impact.

### 27.4. COPY TO Parent

When exporting from a partitioned table, verify `COPY` support/scope for your version. A clear and flexible pattern is `COPY (SELECT ... FROM parent ... ORDER BY ...) TO STDOUT` to precisely control data retrieved across partitions.

## 28. SQL Table Privileges vs. Server File Privileges

A role granted:

~~~sql
GRANT INSERT ON import_lab.product_stage TO import_role;
GRANT SELECT ON import_lab.products TO export_role;
~~~

still cannot automatically execute:

~~~sql
COPY import_lab.product_stage
FROM '/etc/sensitive-file'
WITH (FORMAT text);
~~~

### 28.1. Two Permission Layers

- **Table/column privileges:** `INSERT` for COPY FROM, `SELECT` for COPY TO or queries.
- **Server file/program privileges:** control whether the backend may open files or execute commands on the server host.

### 28.2. pg_read_server_files

This is a predefined role granting privileges to read files accessible to the server according to PostgreSQL rules. It is a **very broad and sensitive** capability.

### 28.3. pg_write_server_files

Grants the ability to write server files subject to OS and PostgreSQL conditions. This poses risks when writing to locations writable by the PostgreSQL service account.

### 28.4. pg_execute_server_program

Allows running server-side programs via features like `COPY PROGRAM`. This can amount to code execution under the PostgreSQL service account's OS privileges and must be tightly guarded.

### 28.5. Do Not Grant These Roles to Ordinary Applications

In most workflows, applications and importers only need `INSERT/SELECT` on relevant tables and use `\copy` or COPY STDIN/STDOUT. Do not grant `pg_read_server_files` just to "import faster".

## 29. OS Permissions and PostgreSQL Roles

Accessing a file on the server simultaneously requires:

1. The file actually exists in the filesystem visible to the backend.
2. The PostgreSQL OS process has the corresponding read/write permissions.
3. The database role is permitted to use server-file COPY.
4. The database role has privileges on the table/columns.

### 29.1. Missing OS Permissions

Even a PostgreSQL superuser cannot read a file if the PostgreSQL OS process is denied access by OS permissions/ACLs, unless granted access through another actual mechanism.

### 29.2. Missing Database Role

OS read permission on the file is insufficient if PostgreSQL blocks the database role from using server-file COPY.

### 29.3. Container Mounts

~~~text
Host: /home/dev/products.csv
Container: /input/products.csv
~~~

If you mount a file into a container at `/input/products.csv`, server-side COPY inside the container uses the **container path**, not the host path.

### 29.4. Managed Databases

On managed PostgreSQL services, arbitrary paths to the server filesystem are often unavailable to customers. Use client COPY streams or the provider's official import/export mechanisms as required.

## 30. COPY PROGRAM: Running OS Commands on the Server Side

PostgreSQL supports the syntax:

~~~sql
-- Functional illustration only; do not run with a regular app role.
COPY import_lab.products
TO PROGRAM 'gzip > /var/lib/postgresql/export/products.csv.gz'
WITH (FORMAT csv, HEADER true);
~~~

Here, the PostgreSQL server launches **a program on the server side**, piping COPY output to the program's stdin (or reading stdout for `FROM PROGRAM`, depending on direction).

### 30.1. It Does Not Run on Your Laptop

`PROGRAM 'gzip ...'` in **SQL COPY** executes on the server. If the server is a Linux container, `gzip` must exist inside that container environment, not on the Windows laptop typing the SQL.

### 30.2. Extremely Sensitive Privilege

Typically requires `pg_execute_server_program` or superuser. Never grant this role to an account that only needs to import CSV files.

### 30.3. Shell Injection

`PROGRAM` may be executed via a shell; constructing the command string from untrusted input risks command injection. Never concatenate user-supplied filenames directly into `PROGRAM`.

### 30.4. A Safer Workflow

If you need gzip/compression, stream the COPY output to a trusted client and compress on the client side, keeping OS program execution privileges isolated from the database server.

## 31. \copy PROGRAM: Client-Side Programs

Psql supports the `PROGRAM` option in `\copy` in supported versions. For example:

~~~text
\copy (SELECT sku, product_name, unit_price FROM import_lab.products ORDER BY sku) TO PROGRAM 'gzip > /home/dev/export/products.csv.gz' WITH (FORMAT csv, HEADER true)
~~~

### 31.1. The Program Runs on the psql Machine

Unlike SQL `COPY TO PROGRAM`, `\copy ... TO PROGRAM` causes psql to launch the command **in the client environment**.

### 31.2. Client OS Permissions

The account running psql needs `gzip` and write access to the client path. `pg_execute_server_program` is not needed just because psql compresses a local file.

### 31.3. Shell Syntax May Differ

The example uses a Unix shell. On Windows, available programs, quoting, and redirection differ; choose commands supported by the operating system.

### 31.4. Never Accept Command Strings from Users

Running commands on the client still carries risks of code execution, data exposure through pipes, and unsafe paths. Do not construct `PROGRAM` commands from unvalidated input.

### 31.5. If PROGRAM Is Unnecessary, Use a File

`\copy ... TO 'products.csv'` is simpler, easier to audit, and has a smaller attack surface.

## 32. COPY in Transactions: Success or Failure

PostgreSQL applies transaction semantics to `COPY` just like other data-modification operations.

~~~sql
BEGIN;

COPY import_lab.product_stage (
    sku, product_name, unit_price_text, stock_text
)
FROM STDIN
WITH (FORMAT csv, HEADER true);

-- COPY data stream is provided by the client here.

COMMIT;
~~~

### 32.1. Statement Atomicity

If a parse or constraint error occurs during COPY FROM, the transaction cannot commit rows from the failed statement as partially valid. The error puts the transaction into an aborted state requiring rollback.

### 32.2. Physical Storage Cost Still Occurs

In a large COPY FROM that fails after many rows, PostgreSQL may have already written tuples that become invisible upon failure; consumed storage space may need **VACUUM** to reclaim or reuse. Never assume a failed COPY uses zero disk resources.

### 32.3. Do Not Hold Huge Transactions Open Unnecessarily

A massive import transaction can hold locks, generate heavy WAL, and cause significant checkpoint/replication lag. Evaluate batch sizes, scheduling, and acceptable partial-commit semantics.

### 32.4. Rollback Does Not Undo Already-Generated WAL

Transaction rollback protects data correctness, but the I/O and WAL already generated do not disappear. That is why files should be validated and normalized before streaming huge payloads.

### 32.5. If the Client Disconnects

An in-progress COPY fails if the connection drops. Import pipelines should track job IDs, checksums, and a way to verify committed state before retrying.

## 33. Large COPY Jobs and Batching Strategies

Suppose a file has 15 million rows.

### 33.1. One Giant Transaction

Pros:

- All-or-nothing: entire load succeeds or rolls back.
- Consistent data snapshot within a single transaction.

Trade-offs:

- Long-running transaction.
- WAL/disk/replication lag.
- Late failures require redoing a lot of work.

### 33.2. Splitting into Multiple Batches

Pros:

- Easier checkpointing.
- Bounded transaction duration and lock hold times.
- Ability to retry only failed chunks.

Trade-offs:

- Lacks whole-file atomicity once earlier batches commit.
- Requires idempotency/unique keys and upsert rules.
- Must report "partially imported" states accurately.

### 33.3. Raw Staging and Promotion

A balanced design loads the file into **batch-scoped staging**, validates thoroughly, and then promotes only approved batches in shorter transactions.

### 33.4. Deduplication and Source Versioning

If the same SKU is imported multiple times across files, define whether newer data overwrites older data by source/timestamp or rejects conflicts. `ON CONFLICT DO UPDATE` needs explicit business rules, not just available syntax.

## 34. COPY and Performance

`COPY` is usually far more efficient than individual `INSERT` statements because it reduces parser, statement, and network round-trip overhead.

### 34.1. What Still Has to Happen?

PostgreSQL still must:

- Parse and cast data types.
- Write heap pages and WAL as configured.
- Enforce constraints.
- Maintain indexes.
- Fire applicable triggers.
- Handle locks and transactions.

### 34.2. COPY Is Not Always the Fastest End-to-End Path

If data requires heavy transformation and complex validation, a staging + set-based INSERT pipeline can outperform forcing COPY directly into the main table.

### 34.3. Indexes on the Target Table

More indexes slow down imports because every row must update each index. However, never drop essential production constraints or indexes recklessly just for speed.

### 34.4. Heavy Triggers

A `FOR EACH ROW` trigger executes N times for an N-row file; if each invocation queries a large table, it creates an N+1 workload. Consider moving batch logic to statement-level triggers with transition tables where appropriate.

### 34.5. After Large Data Imports

The planner needs accurate statistics. Run:

~~~sql
ANALYZE import_lab.products;
~~~

when a large data distribution shift occurs and autovacuum has not yet updated statistics.

### 34.6. Measure Outside Production First

Benchmark throughput, WAL, disk, locks, and import duration in a realistic staging environment; never assume all files load at the same speed.

## 35. VACUUM, WAL, and Replication

### 35.1. COPY Writes Data into PostgreSQL Storage

Even when data arrives via `\copy`, it is still written on the server through PostgreSQL's storage/WAL subsystem per server rules. `\copy` does not skip WAL merely because the file is read on the client.

### 35.2. WAL and Logical/Physical Replicas

Large imports can generate heavy WAL and cause replica lag. If reporting queries run on replicas, monitor lag during bulk loads.

### 35.3. VACUUM After Failed COPY

A COPY that fails after writing many invisible tuples may need cleanup to make space reusable. Consider running `VACUUM` on the affected table per operational practices.

### 35.4. COPY FREEZE

PostgreSQL offers a `FREEZE` option with fairly strict preconditions (for instance, a table newly created or truncated within the current transaction/subtransaction per rules, and subject to restrictions on partitioned/foreign tables). It can speed up bulk loading in appropriate cases, but affects MVCC visibility semantics and must not be used carelessly on production tables with concurrent transactions.

### 35.5. UNLOGGED and TEMP Tables

Staging can use `UNLOGGED` or `TEMP` tables when durability and replication requirements permit. However, they trade off crash recovery, replication, and session scope; do not default to unlogged staging for import data that must survive crashes.

## 36. Monitoring Progress with pg_stat_progress_copy

Modern PostgreSQL provides a COPY progress view:

~~~sql
SELECT
    pid,
    datname,
    relid::regclass AS relation_name,
    command,
    type,
    bytes_processed,
    bytes_total,
    tuples_processed
FROM pg_stat_progress_copy;
~~~

### 36.1. command

Indicates the operation type, such as `COPY FROM` or `COPY TO`, depending on view output and version.

### 36.2. type

Distinguishes how COPY transfers data, such as file, program, or pipe/callback. Exact value names depend on PostgreSQL capabilities; inspect the running view to observe them.

### 36.3. bytes_processed

Bytes processed so far—useful for checking whether the import is actively progressing.

### 36.4. bytes_total May Be 0

When the source size is unknown over a stream, PostgreSQL may not know total bytes. Do not see `bytes_total=0` and conclude the import is empty or stuck.

### 36.5. tuples_processed

Tracks how many rows have been processed. An increasing count does not guarantee the **transaction has committed**; it can still roll back at the end.

### 36.6. View Access Privileges

Monitoring views may restrict details by role. Monitoring accounts need appropriate permissions, though not necessarily superuser.

## 37. pg_stat_activity and COPY

While a COPY is running:

~~~sql
SELECT
    pid,
    usename,
    application_name,
    state,
    wait_event_type,
    wait_event,
    left(query, 160) AS query_prefix
FROM pg_stat_activity
WHERE datname = current_database()
ORDER BY query_start DESC;
~~~

### 37.1. Reading the Query Alongside Wait Events

If COPY is waiting on I/O or a lock, the cause may be disk, network, constraint/index contention, or another blocking transaction.

### 37.2. Do Not Guess Locks from "Running COPY"

`COPY FROM` acquires appropriate locks to modify the table and can interact with DDL, VACUUM FULL, or other transactions. Inspect `pg_locks` when identifying actual blockers.

### 37.3. Clients Using \copy Still Show COPY FROM STDIN

From the server's perspective, `\copy FROM local file` arrives over the COPY protocol. Server monitoring does not directly show the **local filename** on the psql laptop.

### 37.4. ApplicationName

Set an appropriate `application_name`/PGJDBC `ApplicationName` to distinguish import workers, ETL jobs, interactive psql, and API applications.

## 38. PGJDBC CopyManager: Loading Client Files into PostgreSQL

In Java, you cannot execute the `\copy` meta-command as SQL through a `PreparedStatement`. PGJDBC provides `CopyManager` via its driver API.

### 38.1. Example Importing via Reader

~~~java
import java.io.Reader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.sql.Connection;
import java.sql.SQLException;
import javax.sql.DataSource;
import org.postgresql.PGConnection;
import org.postgresql.copy.CopyManager;

public final class ProductCsvImporter {
    private final DataSource dataSource;

    public ProductCsvImporter(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public long importCsv(Path localCsv) throws Exception {
        String copySql =
            "COPY import_lab.product_stage " +
            "(sku, product_name, unit_price_text, stock_text) " +
            "FROM STDIN WITH (FORMAT csv, HEADER true, ENCODING 'UTF8')";

        try (Connection connection = dataSource.getConnection();
             Reader input = Files.newBufferedReader(
                 localCsv, StandardCharsets.UTF_8
             )) {

            connection.setAutoCommit(false);
            try {
                PGConnection pgConnection =
                    connection.unwrap(PGConnection.class);
                CopyManager copyManager =
                    pgConnection.getCopyAPI();

                long copiedRows =
                    copyManager.copyIn(copySql, input);

                // Run SQL validation/merge on the same
                // connection before committing if needed.

                connection.commit();
                return copiedRows;
            } catch (SQLException | RuntimeException ex) {
                try {
                    connection.rollback();
                } catch (SQLException rollbackError) {
                    ex.addSuppressed(rollbackError);
                }
                throw ex;
            }
        }
    }
}
~~~

This example uses a PGJDBC version supporting `PGConnection.getCopyAPI()`/`CopyManager.copyIn(String,Reader)`. It demonstrates **local file/stream → STDIN** without granting server-file privileges. When using a specific DataSource/pool implementation, verify that `unwrap(PGConnection.class)` works and that the connection stays scoped to the job.

### 38.2. Privileges

The application role only needs `INSERT` on the staging table, not `pg_read_server_files`, because the source is a client-side InputStream/Reader.

### 38.3. Explicit Transactions

`setAutoCommit(false)`, `commit()`, and `rollback()` control the same transaction as regular SQL statements. You can run validation/merge `PreparedStatement`s on the **same connection** before committing.

### 38.4. Error Handling

CopyManager can throw I/O or SQL exceptions; the example catches SQL/runtime exceptions to roll back, while checked I/O exceptions from the Reader may require additional catch/rollback handling. In production code, **any error before commit** (including `IOException`) must trigger an explicit rollback before closing the connection.

### 38.5. Do Not Read the Entire File into a String

For large files, using a Reader/InputStream streams data instead of holding hundreds of megabytes on the heap.

## 39. PGJDBC CopyManager: Exporting Data

An export path uses `CopyManager.copyOut` into a `Writer` or `OutputStream`, depending on the driver API.

~~~java
import java.io.Writer;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.sql.Connection;
import javax.sql.DataSource;
import org.postgresql.PGConnection;
import org.postgresql.copy.CopyManager;

public final class ProductCsvExporter {
    public void exportCsv(
            DataSource dataSource,
            Path localCsv
    ) throws Exception {
        String copySql =
            "COPY (" +
            "SELECT sku, product_name, unit_price, stock " +
            "FROM import_lab.products ORDER BY sku" +
            ") TO STDOUT WITH (FORMAT csv, HEADER true)";

        try (Connection connection = dataSource.getConnection();
             Writer out = Files.newBufferedWriter(
                 localCsv, StandardCharsets.UTF_8
             )) {
            CopyManager copyManager =
                connection.unwrap(PGConnection.class)
                          .getCopyAPI();
            copyManager.copyOut(copySql, out);
        }
    }
}
~~~

Depending on the PGJDBC version, `copyOut` overloads support `Writer` or `OutputStream` with differing encoding behavior. If your project uses a version with only `OutputStream`, use the official API accordingly and manage encoding explicitly.

### 39.1. The File Is a Client File

`localCsv` resides on the filesystem where the **Java process is running**, not the DB server. If the Java process runs in a Kubernetes pod, the path belongs to that pod/container.

### 39.2. Mid-Export Failures

The file may already be partially written before a network or SQL error occurs. Production workflows should write to a **temporary file** and rename/publish only after `copyOut` completes and required checks succeed.

### 39.3. SELECT Privileges

The Java role needs read permissions for the query used. It does not need `pg_write_server_files` because the file is written on the client side.

### 39.4. Do Not Mindlessly Paginate Huge Exports with OFFSET

`COPY (SELECT ... ORDER BY ...) TO STDOUT` streams the result; if you need mid-file resumption on failure, design keyset chunking and a separate manifest.

## 40. JDBC Batch or CopyManager?

| Criterion | JDBC batch INSERT | PGJDBC CopyManager |
| --- | --- | --- |
| Source data | Java objects/rows | CSV/text/binary stream |
| SQL pattern | Repeated `INSERT ... VALUES (?,...)` | `COPY ... FROM STDIN` |
| Java validation | Convenient per object | Often staged after COPY |
| Bulk throughput for large data | Good with proper batching | Usually very efficient |
| Per-row RETURNING | More flexible via SQL API | COPY FROM returns no row-by-row ResultSet |
| Conflict handling | Can use `ON CONFLICT` in INSERT | Direct COPY does not support `ON CONFLICT` |
| Server file privileges | No | No when FROM STDIN |
| JDBC transactions | Yes | Yes |
| Retryability | Depends on business logic | Needs batching/checksums/idempotency |

### 40.1. When to Use Batch

Your application already holds typed objects, needs per-row upserts with `ON CONFLICT`, or must report errors per individual record.

### 40.2. When to Use COPY

Your source is a large file or standard stream, you need high throughput, and you can load into staging before merging.

### 40.3. Do Not Evaluate Only by Rows/sec

Account for parsing, validation, dead-letter files, commits, indexes, retries, auditing, operations, and overall system complexity.

## 41. COPY vs. pg_dump/pg_restore

`COPY` and `pg_dump` serve different purposes.

### 41.1. COPY

Suited for moving **table data or query results** in formats like CSV/TEXT/BINARY within a specified scope.

### 41.2. pg_dump

Produces logical database exports capable of including schemas, data, privileges, and object definitions depending on dump mode. Many dump formats use COPY internally to represent table data.

### 41.3. pg_restore

Used to restore compatible archive dump formats. Do not feed a plain CSV file directly to `pg_restore` expecting it to recreate schemas.

### 41.4. When to Choose Backup/Restore

If the goal is backing up an entire database and restoring schemas, indexes, and dependencies, use an appropriate backup strategy (`pg_dump`/`pg_restore` or physical backups). A COPY CSV is not a complete database backup.

## 42. Exporting CSV Safely for Spreadsheet Users

CSV files are often opened in Excel, LibreOffice, or BI tools. This introduces risks distinct from SQL injection.

### 42.1. CSV Formula Injection

If an untrusted text field starts with a character that spreadsheet software treats as a formula—such as `=`, `+`, `-`, or `@` depending on context—the consuming application may evaluate it as a formula.

### 42.2. PostgreSQL COPY Does Not Automatically Prevent Malicious Formulas

`FORMAT csv` escapes commas and quotes per CSV syntax, which does not mean the content is **safe when interpreted by a spreadsheet**.

### 42.3. Know the Consumer

If the export is for machine-to-machine CSV integration, automatically prefixing every string starting with `=` may corrupt real data. If the export is for spreadsheets, apply consumer-appropriate escaping/sanitization policies and test how files open.

### 42.4. Protecting Sensitive Data

CSVs typically lack encryption-at-rest and row-level database access controls. Exporting PII requires reviewing allowed columns, masking, file permissions, destinations, and retention limits.

## 43. Automating psql \copy in Scripts

Psql can execute a script file containing SQL and meta-commands:

~~~text
\set ON_ERROR_STOP on
BEGIN;
TRUNCATE import_lab.product_stage;
\copy import_lab.product_stage (sku, product_name, unit_price_text, stock_text) FROM '/home/dev/import/products.csv' WITH (FORMAT csv, HEADER true)
-- Actual validation and merge queries go here.
COMMIT;
~~~

### 43.1. ON_ERROR_STOP

Psql can stop executing a script upon encountering handled SQL/psql errors, preventing automation from continuing and reporting false success.

### 43.2. Exit Codes

When invoking psql from CI or a job runner, check the process exit code—do not just check whether the log ends with the word `COMMIT`.

### 43.3. \copy Has a Special Parser

The `\copy` meta-command does not undergo the full variable interpolation available in many other psql meta-commands; therefore, do not assume `:file_path` or SQL-like string concatenation will work. For dynamic paths, use tested stdin/input piping, controlled script generation, or a client API.

### 43.4. Never Concatenate Raw Shell Input into Commands

User-supplied file paths must be properly validated and quoted at both the shell and psql layers. Never construct `\copy ... PROGRAM ...` from unvalidated strings.

### 43.5. Do Not Store Secrets in Plaintext Scripts

Use secret injection, `.pgpass` with proper permissions, or organizational secret stores—avoid committing passwords into import scripts.

## 44. Common Error: File Does Not Exist

### 44.1. SQL COPY Server File

Message such as:

~~~text
could not open file "...": No such file or directory
~~~

Check the **database machine**, container mounts, and the path actually visible to the backend.

### 44.2. Psql \copy Client File

Psql reports it cannot open the file because the path does not exist on the **machine running psql**, not necessarily the server.

### 44.3. Do Not Copy Files to the Server as a "Quick Fix"

If the application requirement is simply uploading a CSV from a laptop, switching to `\copy` is usually cleaner and safer than creating an ad-hoc upload channel onto the database host.

### 44.4. Paths Containing Spaces

Quote paths using supported syntax and verify the filesystem path. Pay attention to quoting differences across the shell, SQL, and psql meta-commands.

## 45. Permission Denied Errors

### 45.1. SQL COPY FROM '/server/file'

Missing the database role to read server files, or the OS `postgres` user lacks read permission on the file.

### 45.2. SQL COPY TO '/server/file'

Missing the database role to write server files, the target directory is not writable, or the file already exists.

### 45.3. \copy FROM '/client/file'

The OS user running psql cannot read the local file, or the database role lacks `INSERT`.

### 45.4. \copy TO '/client/file'

The OS user running psql cannot write to the local directory, or the database role lacks `SELECT`.

### 45.5. Never Grant Superuser to Fix Permissions

Identify the exact **permission layer** that is missing. Often you only need proper local file permissions or `GRANT INSERT/SELECT`, not server-file privileges.

## 46. Malformed CSV or Column Count Mismatch Errors

### 46.1. Missing Data for Column

A row has fewer fields than the target column list, or improper quoting caused the parser to miss a delimiter.

### 46.2. Extra Data After Last Expected Column

A row has more fields than expected, commonly due to an unquoted comma inside a text value.

### 46.3. Unterminated CSV Quoted Field

A value opened a quote without closing it properly, or the file was truncated.

### 46.4. Quotes Inside Values

Valid default CSV:

~~~csv
MS-02,"Chuột ""siêu nhẹ""",299000.00,15
~~~

Invalid if written as:

~~~csv
MS-02,"Chuột "siêu nhẹ"",299000.00,15
~~~

### 46.5. Line Numbers Can Be Hard to Read with Multiline Fields

If a CSV field contains newlines, the "physical line" and the "CSV record" differ. Use a standards-compliant CSV parser and report errors with context.

## 47. Data Type Mismatch Errors

### 47.1. Invalid Input Syntax

~~~text
invalid input syntax for type numeric: "one hundred"
~~~

comes from casting CSV text into a numeric column; text staging preserves raw values for inspection.

### 47.2. Out of Range

`integer` or `numeric(14,2)` has bounds. A file with huge numbers can overflow even when the string contains only digits.

### 47.3. Date/Time Parsing

Wrong date formats or missing timezones cause errors or unintended interpretations. Standardize on ISO 8601 and specify time zones.

### 47.4. Encoding

An "invalid byte sequence" message indicates a file encoding mismatch or bytes invalid for the selected text encoding.

### 47.5. NULL vs. NOT NULL

Unquoted empty CSV fields are interpreted as SQL NULL and can trigger NOT NULL violations even when the file producer meant an empty string.

## 48. Design Mistakes to Avoid

### Mistake 1. Thinking SQL COPY Reads Files on Your Laptop

`COPY FROM '/path'` opens files on the database server.

### Mistake 2. Thinking \copy Is PostgreSQL SQL

`\copy` is strictly a psql meta-command; JDBC does not understand it directly.

### Mistake 3. Running psql in a Container While Passing Laptop Paths

The psql client is running **inside the container**, so `\copy` opens container paths.

### Mistake 4. Granting pg_read_server_files to an Import App

This privilege grants very broad server-file read access. Use client-side COPY STDIN instead when appropriate.

### Mistake 5. Granting pg_execute_server_program to Regular Jobs

This can lead to OS command execution under the `postgres` service account. Do not grant it to an application user that just imports CSVs.

### Mistake 6. Omitting the Column List

Adding a column in a schema migration shifts column alignment and can corrupt imported data.

### Mistake 7. Believing HEADER true Matches Columns by Name

Basic mode only skips the header line; column order is determined by the COPY column list.

### Mistake 8. Confusing SQL NULL with Empty Strings

Quoted and unquoted empty CSV fields have different meanings under default NULL settings.

### Mistake 9. Importing a UTF-16 File as UTF-8 CSV

Encoding mismatches cause character errors or data corruption.

### Mistake 10. Parsing CSV with split(",")

Commas inside quoted fields are not field delimiters; quote escaping and multiline fields also break naive splitting.

### Mistake 11. Running COPY Directly on Untrusted Data into Main Tables

You lose validation/quarantine capabilities and row-level error reporting. Staging is usually worthwhile.

### Mistake 12. Silently Dropping Invalid Rows

Importing only rows that "match a regex" without reporting dropped rows produces silent data loss.

### Mistake 13. Not Checking Duplicates After Normalization

`kb-01` and `KB-01` can collide on a UNIQUE constraint during merge.

### Mistake 14. Using ON CONFLICT DO UPDATE with Duplicate Targets in the Same Batch

This can raise an error because a single INSERT cannot modify the same target row multiple times under UPSERT semantics.

### Mistake 15. Splitting into Batches While Claiming Whole-File Atomicity

Committing per batch leaves partial file data in the database if a later batch fails.

### Mistake 16. Assuming Failed COPY Has Zero Storage Cost

Tuples written before failure may need VACUUM to reclaim space; WAL and I/O do not vanish.

### Mistake 17. Ignoring Index, Trigger, and Constraint Costs

COPY does not bypass table safeguards and can be slowed significantly by row-level triggers.

### Mistake 18. Treating bytes_total=0 as an Empty File

Progress tracking on streamed sources may not know the total size.

### Mistake 19. Skipping ANALYZE After a Large Import

The planner may rely on stale statistics and choose suboptimal query plans.

### Mistake 20. Running Server COPY TO and Looking for the File Locally

You will not find the CSV on your laptop because the file was written on the database host or container.

### Mistake 21. Expecting Deterministic Export Order Without ORDER BY

There is no business-order guarantee unless explicitly requested in the query.

### Mistake 22. Exporting PII and Leaving Files Unprotected

CSV files outside the DB are no longer governed by PostgreSQL RLS or GRANTs.

### Mistake 23. Relying on FORMAT csv to Prevent Formula Injection

CSV escaping does not stop spreadsheets from evaluating cell strings as formulas.

### Mistake 24. Using COPY CSV Instead of Full Database Backups

CSVs lack schemas, indexes, roles, and full object dependencies required for proper backups.

### Mistake 25. Calling JDBC executeQuery on \copy

JDBC understands SQL and the COPY protocol via its API, not psql meta-commands.

### Mistake 26. Loading an Entire CSV into a String Before CopyManager

This wastes heap memory; stream from a Reader or InputStream.

### Mistake 27. Exporting Directly to the Final Path While Users Can Read It Early

If `copyOut` fails mid-stream, the file is truncated. Write to a temporary file, verify, then publish/rename.

### Mistake 28. Forgetting to Roll Back After a Failed COPY in a Transaction

The connection remains in an aborted state, causing subsequent SQL statements to fail until rolled back.

### Mistake 29. Passing User-Supplied Server Paths Directly into PROGRAM

This can expose data or enable command injection; only use controlled file/command workflows.

### Mistake 30. Running Concurrent Imports into an Unscoped Staging Table

Two jobs can interleave rows, misdetect duplicates, or promote each other's files.

## 49. Practice Exercises

These exercises are based on the `import_lab` schema and `products.csv` file from this lesson. Never run server-file write commands or `PROGRAM` in production without official authorization and procedures.

### Exercise 1. File Location

When running `COPY ... FROM '/home/an/a.csv'` via psql from a laptop, which machine looks for the file?

### Exercise 2. \copy

When running `\copy ... FROM '/home/an/a.csv'` in psql on a laptop, which machine opens the file?

### Exercise 3. Containers

If you run `docker exec ... psql`, does `\copy` see files on the host or inside the container?

### Exercise 4. JDBC

Why is `PreparedStatement.execute("\\copy ...")` not the right way to import a file?

### Exercise 5. Table Role Privileges

What database role privilege is needed to import into staging using `\copy FROM`?

### Exercise 6. Server File Privileges

If you must use SQL `COPY FROM` with a server file path, which special PostgreSQL privileges are required?

### Exercise 7. COPY TO Server

Who writes the file `'/var/lib/postgresql/export/products.csv'` in SQL `COPY TO`?

### Exercise 8. \copy TO Client

Write a psql meta-command to export columns `sku,product_name,unit_price,stock` to a client file `'/home/dev/export/out.csv'` with a CSV header.

### Exercise 9. Selecting Columns

Why must you specify a column list when the file lacks `product_id` and `imported_at`?

### Exercise 10. TEXT vs. CSV

What are the basic differences in delimiter, NULL handling, and escaping between `FORMAT text` and `FORMAT csv`?

### Exercise 11. CSV Comma

Write the name value `Bàn phím, cơ` as a valid CSV field.

### Exercise 12. CSV Quotes

Write a CSV field containing the exact string `Chuột "siêu nhẹ"`.

### Exercise 13. HEADER true

If a file has no header row but COPY specifies `HEADER true`, how is the first row handled?

### Exercise 14. NULL

In default CSV, are unquoted empty and quoted empty (`""`) equivalent?

### Exercise 15. ENCODING

Why can't a UTF-16 file containing Vietnamese text simply be imported correctly with `ENCODING 'UTF8'`?

### Exercise 16. Query Export

Write a `COPY (SELECT ...) TO STDOUT` command to export products with stock greater than 0, ordered by SKU, including a header.

### Exercise 17. STDIN

Does `COPY FROM STDIN` read data from a PostgreSQL OS file or from the client stream?

### Exercise 18. \.

In interactive psql when importing via `COPY ... FROM STDIN`, what does `\.` mean?

### Exercise 19. CSV Parser

Why shouldn't you use `String.split(",")` to parse arbitrary CSV files?

### Exercise 20. Staging

Name three benefits of loading into a text staging table before casting types.

### Exercise 21. SKU Validation

Write a SQL query to find SKUs that do not match `^[A-Z0-9-]{3,24}$` after `upper` and `btrim`.

### Exercise 22. Duplicates

Write a SQL query to find duplicate SKUs after `upper(btrim(sku))` in staging.

### Exercise 23. Promotion

Why must you validate data before running `INSERT ... ON CONFLICT DO UPDATE`?

### Exercise 24. Transactions

If COPY FROM fails inside an uncommitted transaction, what must the application do?

### Exercise 25. Mid-File COPY Failure

Why can a late-failing COPY still consume table storage and WAL?

### Exercise 26. Constraints

Does COPY FROM bypass `CHECK`, `UNIQUE`, and table triggers?

### Exercise 27. Rules

Does COPY FROM behave the same as INSERT with respect to rewrite rules?

### Exercise 28. RLS

Why should you be cautious with COPY FROM on tables using RLS?

### Exercise 29. COPY PROGRAM

Where does `COPY TO PROGRAM 'gzip ...'` execute, and why does it require strong privileges?

### Exercise 30. \copy PROGRAM

Where does `\copy TO PROGRAM 'gzip ...'` execute?

### Exercise 31. Security

Why should `pg_execute_server_program` not be granted to an app that only needs to import CSVs?

### Exercise 32. pg_stat_progress_copy

Write a query displaying `pid,command,type,bytes_processed,bytes_total,tuples_processed`.

### Exercise 33. bytes_total

If `bytes_total=0` in COPY FROM STDIN, can you conclude the file is empty?

### Exercise 34. JDBC CopyManager

Describe how PGJDBC imports a local file into PostgreSQL without using psql.

### Exercise 35. CopyManager Transaction

To keep import, validation, and merge atomic together, how many Connections are needed and when should commit happen?

### Exercise 36. Export Failure

To prevent users from receiving an incomplete CSV file, what should you do before publishing the file?

### Exercise 37. Statistics

After a large bulk import that alters data distribution, which PostgreSQL command updates planner statistics?

### Exercise 38. Backup

When backing up both schema and data, does COPY CSV fully replace `pg_dump/pg_restore`?

### Exercise 39. CSV Injection

Why must CSV exports for Excel evaluate values starting with `=`, `+`, `-`, or `@`?

### Exercise 40. Choosing an Approach

Choose among `COPY server file`, `psql \copy`, `PGJDBC CopyManager`, and `pg_dump` for four scenarios: file on DB server; file on laptop; Java service receiving a stream; logical database backup.

## 50. Reference Solutions

### Exercises 1–3. Where Files Are Opened

`COPY FROM 'file'`: the PostgreSQL backend opens the file on the server. `\copy FROM 'file'`: psql opens the file on the client. If psql runs via `docker exec`, the client is the psql process **inside the container**, not the host outside the container.

### Exercise 4. JDBC

`\copy` is not PostgreSQL SQL. Java should use SQL `COPY ... FROM STDIN` with PGJDBC `CopyManager`, or build a JDBC batch pipeline.

### Exercises 5–7. Permissions

`\copy FROM` requires appropriate `INSERT` on the table and OS read permission for psql. SQL `COPY FROM server-file` requires special privileges like `pg_read_server_files` or superuser plus OS read permission. `COPY TO server-file` is written by the PostgreSQL backend and requires privileges like `pg_write_server_files`/superuser plus OS write permission.

### Exercise 8. \copy TO

~~~text
\copy import_lab.products (sku, product_name, unit_price, stock) TO '/home/dev/export/out.csv' WITH (FORMAT csv, HEADER true)
~~~

### Exercise 9. Column List

The file only has four columns; specifying the column list avoids schema-order mismatches and allows identity/default columns like `product_id`/`imported_at` to use the table's defaults.

### Exercise 10. Format

`FORMAT text` typically uses TAB, PostgreSQL-style escapes, and `\N` for NULL. `FORMAT csv` typically uses commas and double quotes; unquoted empty defaults to SQL NULL while quoted empty represents an empty string.

### Exercises 11–12. Quoting

~~~csv
"Bàn phím, cơ"
"Chuột ""siêu nhẹ"""
~~~

### Exercise 13. Header

With `HEADER true`, the first data row is treated as a header and skipped, resulting in a missing record.

### Exercise 14. SQL NULL

No. In default CSV, unquoted empty is SQL NULL whereas quoted empty is an empty text string, unless overridden by NULL/`FORCE_*` options.

### Exercise 15. Encoding

UTF-16 and UTF-8 are different byte encodings; PostgreSQL will not automatically transcode a UTF-16 file just because `ENCODING 'UTF8'` is set. You must transcode the file or read it appropriately.

### Exercise 16. Query Export

~~~sql
COPY (
    SELECT sku, product_name, unit_price, stock
    FROM import_lab.products
    WHERE stock > 0
    ORDER BY sku
)
TO STDOUT
WITH (FORMAT csv, HEADER true);
~~~

### Exercises 17–18. STDIN

`STDIN` is COPY data sent from the client over the PostgreSQL connection; in interactive/script psql, `\.` marks the end of the COPY data section.

### Exercise 19. CSV Parser

CSV allows delimiters, quotes, and newlines inside quoted fields; `split(",")` cannot distinguish data commas from separator commas.

### Exercise 20. Staging

It helps (1) preserve raw values when numeric/date columns are invalid; (2) validate and report errors per row; (3) deduplicate/normalize; (4) manage batches/retries; and (5) promote only approved data.

### Exercise 21. SKU Validation

~~~sql
SELECT stage_id, sku
FROM import_lab.product_stage
WHERE sku IS NULL
   OR upper(btrim(sku)) !~ '^[A-Z0-9-]{3,24}$';
~~~

### Exercise 22. Deduplication

~~~sql
SELECT upper(btrim(sku)) AS sku, count(*)
FROM import_lab.product_stage
GROUP BY upper(btrim(sku))
HAVING count(*) > 1;
~~~

### Exercise 23. Promotion

You must catch duplicate normalized SKUs, malformed prices/stock, NULL/blank values, and business invariants. Otherwise, the merge may fail the entire batch or perform incorrect updates.

### Exercises 24–25. Failed COPY

After a SQL error in a transaction, roll back or roll back to an appropriate savepoint. A late-failing COPY can leave dead tuples requiring VACUUM and still consumes I/O and WAL.

### Exercises 26–28. Constraints/Rules/RLS

`COPY FROM` enforces applicable constraints and triggers—it does not bypass them. It does not invoke rewrite rules like `INSERT`. For RLS, check `COPY FROM` restrictions and use an appropriate import path; never disable RLS just to bypass permissions.

### Exercises 29–31. PROGRAM

SQL `COPY ... PROGRAM` executes commands on the server under the `postgres` OS service privileges and requires strong authorization. `\copy ... PROGRAM` runs on the psql client machine. Do not grant `pg_execute_server_program` to an import app because it enables OS command execution on the database server.

### Exercise 32. Progress

~~~sql
SELECT
    pid,
    command,
    type,
    bytes_processed,
    bytes_total,
    tuples_processed
FROM pg_stat_progress_copy;
~~~

### Exercise 33. Unknown Total

No. For streamed sources, PostgreSQL may not know the total byte count, leaving `bytes_total=0` even while actively processing large amounts of data.

### Exercise 34. Java COPY

Open the local file with a Reader/InputStream, obtain `PGConnection.getCopyAPI()` from the JDBC connection, call `copyIn("COPY ... FROM STDIN ...", reader)`, and manage SQL/rollback/commit on that connection.

### Exercise 35. Single Connection

Use a single `Connection` with `setAutoCommit(false)`, import via CopyManager, validate/merge on the same session, and commit only when all required steps succeed; roll back on any failure.

### Exercise 36. Export Temp File

Write to a temporary file on the client, wait for `copyOut` to finish and pass necessary checks, then rename/publish following safe filesystem practices. On error, never publish an incomplete file.

### Exercise 37. ANALYZE

~~~sql
ANALYZE import_lab.products;
~~~

### Exercise 38. Backup

No. CSV only contains selected data; `pg_dump/pg_restore` and proper backup strategies manage schemas, objects, data, and metadata for recovery goals.

### Exercise 39. Formula Injection

Spreadsheets can evaluate strings starting with formula characters as expressions even when CSV quoting is valid. Consumer-appropriate export policies are needed, not just comma escaping.

### Exercise 40. Choosing the Transfer Method

| Scenario | Choice |
| --- | --- |
| File actually resides on DB server with approved role | SQL `COPY FROM server-file` |
| File resides on laptop running psql | `\copy FROM client-file` |
| Java service has a Reader/InputStream | PGJDBC `CopyManager` + `COPY FROM STDIN` |
| Logical backup of both schema and data | `pg_dump`, restored with the matching tool |

## 51. Quick Reference Table

| Task | Syntax / Approach |
| --- | --- |
| Server reads file | `COPY table FROM '/server/path'` |
| Server writes file | `COPY table TO '/server/path'` |
| Client psql reads file | `\copy table FROM '/client/path'` |
| Client psql writes file | `\copy table TO '/client/path'` |
| Client streams to server | `COPY table FROM STDIN` |
| Server streams to client | `COPY table TO STDOUT` |
| Export SELECT results | `COPY (SELECT ...) TO STDOUT` |
| CSV with header | `WITH (FORMAT csv, HEADER true)` |
| Semicolon CSV | `DELIMITER ';'` |
| CSV quoted fields | `QUOTE '"'` |
| Escape quote characters | `ESCAPE '"'` |
| Control NULL marker | `NULL '...'` |
| Keep unquoted empty as text | `FORCE_NOT_NULL (column)` when appropriate |
| Force quoted null marker to NULL | `FORCE_NULL (column)` when appropriate |
| UTF-8 encoding | `ENCODING 'UTF8'` per version |
| Auto-generated identity column | Omit column from COPY column list |
| Server file read privilege | `pg_read_server_files`/superuser + OS permissions |
| Server file write privilege | `pg_write_server_files`/superuser + OS permissions |
| Server executes PROGRAM | `pg_execute_server_program`/superuser |
| Client executes PROGRAM | `\copy ... PROGRAM` on psql machine |
| Validate before main table load | Text staging + validation |
| Merge duplicate SKUs in target | `INSERT ... ON CONFLICT` after batch dedupe |
| Roll back import | `BEGIN`/`ROLLBACK` or JDBC transaction |
| Monitor COPY progress | `pg_stat_progress_copy` |
| Monitor sessions and waits | `pg_stat_activity`/`pg_locks` |
| Update statistics | `ANALYZE table` |
| Java import stream | PGJDBC `CopyManager.copyIn` |
| Java export stream | PGJDBC `CopyManager.copyOut` |
| Logical database backup | `pg_dump`/`pg_restore` |

## 52. Production Import/Export Implementation Checklist

1. **Identify where the file resides**: laptop, app pod, ETL worker, database server, or object storage?
2. Can the PostgreSQL server actually see the path if using server-side COPY?
3. Have you avoided granting server-file privileges to application roles unnecessarily?
4. Does the role have `INSERT`/`SELECT` on the right tables/columns and schema `USAGE`?
5. Is the file CSV, text, or binary? Is the format contract finalized?
6. Is there a header, does column order match, and is the column list explicit?
7. Do delimiter/quote/escape match the source format?
8. Have SQL NULL, quoted/unquoted empty, and missing values been agreed upon?
9. Does the file have the right encoding and is BOM handling addressed?
10. Are dates/times in ISO format with explicit time zones, and are decimals clearly defined?
11. Is staging separated from the main table when the file is untrusted?
12. Are raw values and errors stored by `stage_id`/`batch_id`?
13. Are duplicate keys checked after normalization?
14. Is there a clear reject-all, quarantine, or partial-success policy?
15. Is idempotency defined if the same file/job is re-run?
16. Are transaction boundaries and rollbacks enforced if any required step fails?
17. Are psql `ON_ERROR_STOP` and process exit codes checked?
18. Is batch size aligned with WAL/locks/replication and atomicity needs?
19. Are triggers/constraints/RLS preserved rather than disabled arbitrarily?
20. Are index overhead and post-import `ANALYZE` considered for large loads?
21. Are `pg_stat_progress_copy` and connection states monitored?
22. Is shell injection prevented when using `COPY PROGRAM` or `\copy PROGRAM`?
23. Is an appropriate TLS/SSL policy applied to the client–server hop?
24. Do exports restrict sensitive columns/rows, PII, and tenant permissions?
25. Are CSVs intended for spreadsheets evaluated for formula injection?
26. Do file exports use a temp/publish workflow to avoid exposing truncated files?
27. Are retention, disk quotas, and checksums in place for files and batch records?
28. Do connections and app workers have proper timeouts and retry policies?
29. Are empty files, header-only files, multiline CSVs, quotes, and UTF-8 tested?
30. Is there a runbook for missing files, permission errors, invalid input, and disk full?

## 53. Summary

The most important distinction in PostgreSQL import/export is **who opens the file**:

- **SQL `COPY ... FROM/TO 'path'`:** the PostgreSQL backend opens the file on the **server** using the database service's OS privileges. It requires highly sensitive server-file privileges in addition to table privileges.
- **`psql \copy ... FROM/TO 'path'`:** the **psql process on the client** opens the file and transfers data via `COPY FROM STDIN` or `COPY TO STDOUT`. The database role still needs table privileges, but does not need arbitrary file read/write privileges on the server machine.
- **`COPY FROM STDIN`/`TO STDOUT`:** is the SQL/PostgreSQL data-transfer protocol for clients; PGJDBC `CopyManager` uses this mechanism to stream Java files or Readers without running the `\copy` meta-command.

In practice, always specify an explicit **column list**, choose the right `FORMAT`/`HEADER`/`NULL`/`ENCODING`, handle quoted CSV with a proper parser, and favor **staging + validation + transactions** when data sources are untrusted. For large datasets, evaluate WAL, locks, triggers, indexes, disk, replication lag, and resumability; `COPY` is fast, yet does not exempt data from PostgreSQL's integrity rules.

A very useful decision question is: **"Where does the file live, who is permitted to open it, and what checks must the data pass before committing?"** Answering these three parts correctly helps you choose `COPY`, `\copy`, or `CopyManager` safely, quickly, and reliably in operations.
