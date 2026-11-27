# Client-Side Import and Export with \copy in PostgreSQL

During PostgreSQL development and operations, data frequently needs to move between database tables and files on the user's machine: importing a product catalog from CSV, loading legacy data before transformation, exporting reconciliation reports, or handing data off to an analytics system. PostgreSQL provides SQL `COPY` for bulk data transfer. Specifically, the **`psql`** command-line client provides the **`\copy` meta-command**, which reads or writes files **on the machine where `psql` is running**.

This distinction determines where files must reside, which OS permissions are required, how remote server connections behave, and how scripts must be designed. If the database runs on a remote server while `psql` runs on your laptop, `\copy ... FROM 'products.csv'` looks for the file on **your laptop**, not inside the PostgreSQL server's data directory.

This lesson covers `\copy FROM/TO` syntax, client/server data flow, CSV import and export, formatting options, handling `NULL`, encoding, permissions, transactions, staging, and common errors.

## 1. Learning objectives

After completing this lesson, you will be able to:

- Clearly distinguish PostgreSQL SQL `COPY` from `psql`'s `\copy` meta-command.
- Import CSV from a local file into a table while specifying columns, header, and encoding.
- Export an entire table or `SELECT` query result to a local CSV file.
- Understand `FORMAT`, `HEADER`, `DELIMITER`, `QUOTE`, `ESCAPE`, and `NULL` options.
- Identify the exact file path and OS identity accessing the file.
- Distinguish database permission errors from client-side file read/write errors.
- Use transactions and staging tables when imported data requires validation.
- Avoid duplicate imports, column misalignment, data-type errors, and exposure of sensitive data.

Examples target modern PostgreSQL and `psql`. Run table creation or drop statements only on a **dedicated practice database**.

---

## 2. How does `\copy` differ from `COPY`?

### 2.1. SQL `COPY` runs on the server side

PostgreSQL provides the SQL statement:

```sql
COPY public.products
FROM '/var/lib/postgresql/import/products.csv'
WITH (FORMAT csv, HEADER true);
```

When a file path is passed to SQL `COPY`, it is interpreted on the filesystem of **the machine running the PostgreSQL server process**. The server must have read permissions on the file (or write permissions for `COPY TO`); the database account may also need appropriate server file read/write privileges.

A file on your laptop does not become a server file just because you connect to the database from your laptop. Nor is `/var/lib/postgresql/import/products.csv` a local directory path on the operator's machine, unless client and server actually run on the same host.

### 2.2. `\copy` runs on the client side

Inside `psql`, use:

```text
\copy public.products FROM '/home/student/products.csv' WITH (FORMAT csv, HEADER true)
```

`psql` reads `/home/student/products.csv` **on the machine running psql**, then streams the data over the PostgreSQL connection. On the server side, the underlying mechanism corresponds to `COPY ... FROM STDIN`.

Export works symmetrically: `\copy ... TO 'output.csv'` instructs the server to send data via `COPY ... TO STDOUT` so `psql` writes it to a local file.

```text
                  IMPORT: \copy ... FROM 'products.csv'

      Machine running psql                    PostgreSQL server
  +--------------------------+          +------------------------------+
  | products.csv             |          | Data table                   |
  |       |                  |          |      ^                       |
  |       v                  |          |      |                       |
  | psql reads local file ---+--------->| COPY ... FROM STDIN          |
  +--------------------------+ network  +------------------------------+


                   EXPORT: \copy ... TO 'export.csv'

      Machine running psql                    PostgreSQL server
  +--------------------------+          +------------------------------+
  | export.csv               |          | Table / SELECT query         |
  |       ^                  |          |      |                       |
  |       |                  |          |      v                       |
  | psql writes local file <-+----------+ COPY ... TO STDOUT           |
  +--------------------------+ network  +------------------------------+
```

| Aspect | SQL `COPY` with filename | `\copy` in `psql` |
| --- | --- | --- |
| Where file I/O executes | PostgreSQL server | `psql` client program |
| File path resolves on | Server machine | Client machine running `psql` |
| OS file permissions | OS account running PostgreSQL | OS account running `psql` |
| PostgreSQL table privileges | Still required | Still required |
| Arbitrary server file access | May require additional server privileges | Does not require server file privileges just to read/write client files |
| Streams CSV over client/server connection | Not in the same way when server opens the file directly | Yes |
| Runs in a plain SQL editor | Standard PostgreSQL SQL | No, unless the client supports meta-commands |

**Remember:** `\copy` is not a SQL statement sent verbatim to the server; it is a `psql` control command.

### 2.3. `\copy` on laptops, SSH, Docker, and CI

Where the file actually lives depends on **where the psql process is running**, not where your terminal window is displayed.

| How `psql` is launched | Where does `\copy FROM 'file.csv'` look? |
| --- | --- |
| Terminal on laptop | Laptop's filesystem |
| SSH into an application server, then run psql | Application server's filesystem |
| `docker exec ... psql` | Container's filesystem |
| `psql` inside a CI job | CI runner's filesystem |
| `psql` directly on the database host | That host's filesystem, since client and server share the machine |

For example, if `C:/data/products.csv` is on Windows while you run `psql` **inside a Linux container**, `\copy FROM 'C:/data/products.csv'` will not automatically find the Windows file. You must mount or copy the file into the filesystem visible to the running psql process.

---

## 3. Preparing the practice environment

### 3.1. Connecting to PostgreSQL with `psql`

Example from a terminal:

```bash
psql -h localhost -p 5432 -U postgres -d postgres
```

Account, host, and database must match your environment. Never place real passwords directly on the command line or in scripts that could enter shell history.

Once inside `psql`:

```sql
SELECT current_database(), current_user, version();
```

You can also run the meta-command:

```text
\conninfo
```

If the terminal accepts `\conninfo` and displays connection details, you are using a `psql` client suitable for the `\copy` examples.

### 3.2. Creating a sample table

> **Use only in a lab database.** The `DROP TABLE IF EXISTS` statements below delete any tables of the same names along with their data. Never run on production.

```sql
CREATE SCHEMA IF NOT EXISTS client_copy_lab;

DROP TABLE IF EXISTS client_copy_lab.products;
DROP TABLE IF EXISTS client_copy_lab.products_stage;

CREATE TABLE client_copy_lab.products (
    product_id INTEGER PRIMARY KEY,
    sku TEXT NOT NULL UNIQUE,
    product_name TEXT NOT NULL,
    unit_price NUMERIC(12,2) NOT NULL CHECK (unit_price >= 0),
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

Table characteristics:

- `product_id` is the primary key.
- `sku` must be non-null and unique.
- `unit_price` is an exact, non-negative decimal number.
- `active` takes boolean values.
- `created_at` has a server-side default, so it is **not required in the CSV file** if excluded from the column list.

### 3.3. Preparing a local CSV file

On the machine running `psql`, create `products.csv` using a UTF-8 editor:

```csv
product_id,sku,product_name,unit_price,active
1,BOOK-001,"SQL Book, basics",125000.00,true
2,PEN-002,"Blue ""ink"" pen",15000.00,true
3,NOTE-003,"Notebook",45000.00,false
```

This file contains three data rows and one header row.

Notable fields:

- The name `SQL Book, basics` contains a comma, so it must be enclosed in `"..."`.
- The name `Blue "ink" pen` contains double quotes, so inner quotes are doubled as `""`.
- `true` and `false` are valid input for PostgreSQL's `BOOLEAN` type.
- Prices use a decimal point rather than locale-specific decimal commas.
- The file must exist on the client side before running the import command.

You do not need to create `row47.md` or any other module files to practice. `products.csv` is simply an example created by the learner on their test machine.

---

## 4. Importing CSV with `\copy ... FROM`

### 4.1. Basic syntax

Inside `psql`, run on **a single line**:

```text
\copy client_copy_lab.products (product_id, sku, product_name, unit_price, active) FROM 'products.csv' WITH (FORMAT csv, HEADER true, ENCODING 'UTF8')
```

The command will:

1. Open `products.csv` on the client machine running `psql`.
2. Read the header row and skip it because `HEADER true` is set.
3. Split CSV fields according to delimiter and quoting rules.
4. Send values into the listed columns **in order**.
5. PostgreSQL casts types, checks constraints, and writes the rows.
6. Return the count of imported rows.

With the sample file and an empty table, the expected output is:

```text
COPY 3
```

Verify with SQL:

```sql
SELECT product_id, sku, product_name, unit_price, active, created_at
FROM client_copy_lab.products
ORDER BY product_id;

SELECT COUNT(*) AS row_count
FROM client_copy_lab.products;
```

Expected row count is **3**. `created_at` receives its default value because it was omitted from the import column list.

### 4.2. Why list columns explicitly?

Do not default to:

```text
\copy client_copy_lab.products FROM 'products.csv' WITH (FORMAT csv, HEADER true)
```

In our sample table, the CSV has 5 fields while the table also has `created_at`. Without an explicit column list, PostgreSQL expects values for all columns in table definition order and fails with missing data.

An explicit statement:

```text
\copy client_copy_lab.products (product_id, sku, product_name, unit_price, active) FROM 'products.csv' WITH (FORMAT csv, HEADER true)
```

defines a clear contract for field count and ordering. Columns omitted from the list receive their defaults if the schema allows.

### 4.3. Headers do not automatically map columns by name

Suppose the file changes to:

```csv
sku,product_id,product_name,unit_price,active
BOOK-001,1,"SQL Book, basics",125000.00,true
```

If `\copy` still specifies `(product_id, sku, ...)`, PostgreSQL tries to parse `BOOK-001` as an integer for `product_id`, resulting in an error.

With standard `HEADER true`, the header line is **skipped**, not matched by column name against table columns. If column order changes in the file, update the column list or normalize the file to match. Depending on version, other header-matching options may exist, but do not rely on them without verifying server support.

### 4.4. `\copy` inserts data; it does not UPSERT automatically

If you run the same file again after a successful import, `product_id` or `sku` will collide and PostgreSQL will raise `unique_violation`:

```text
ERROR: duplicate key value violates unique constraint ...
```

`\copy ... FROM` does not replace existing rows or silently skip duplicates by default. For repeatable imports, load into a staging table first and merge cleanly using `INSERT ... ON CONFLICT` or an equivalent ETL step.

---

## 5. Exporting CSV with `\copy ... TO`

### 5.1. Exporting selected columns from a table

In `psql`:

```text
\copy client_copy_lab.products (product_id, sku, product_name, unit_price, active) TO 'products_export.csv' WITH (FORMAT csv, HEADER true, ENCODING 'UTF8')
```

`products_export.csv` is created on **the machine running psql**. If given a relative path, its location depends on **the psql process's working directory**, not PostgreSQL's data directory.

`created_at` is excluded because the column list omitted it.

### 5.2. Exporting SELECT query results

If you only need rows where `active = true`:

```text
\copy (SELECT sku, product_name, unit_price FROM client_copy_lab.products WHERE active = true ORDER BY sku) TO 'active_products.csv' WITH (FORMAT csv, HEADER true, ENCODING 'UTF8')
```

The output file contains a header and two rows:

```csv
sku,product_name,unit_price
BOOK-001,"SQL Book, basics",125000.00
PEN-002,"Blue ""ink"" pen",15000.00
```

To export a summary report:

```text
\copy (SELECT active, COUNT(*) AS product_count, SUM(unit_price) AS total_unit_price FROM client_copy_lab.products GROUP BY active ORDER BY active DESC) TO 'products_summary.csv' WITH (FORMAT csv, HEADER true)
```

PostgreSQL executes the parenthesized query; psql receives the streamed COPY output and writes the local file.

### 5.3. Exporting to standard output

```text
\copy (SELECT sku, unit_price FROM client_copy_lab.products ORDER BY sku) TO STDOUT WITH (FORMAT csv, HEADER true)
```

This sends CSV to psql's standard output, useful for certain pipelines. For beginners, `TO 'report.csv'` is usually easier to manage. When redirecting shell stdout, account for client messages and exit codes so CSV data does not get mixed with other text.

### 5.4. Exporting does not automatically protect data

A CSV file generated from a `SELECT` may contain sensitive data. `\copy` does not encrypt, anonymize, or verify that the recipient is authorized to view those columns. Export only permitted columns and rows, secure the destination directory, and follow data-retention policies.

---

## 6. Key formatting options

Common CSV syntax:

```text
\copy some_table (col1, col2, col3) FROM 'file.csv' WITH (FORMAT csv, HEADER true, DELIMITER ',', QUOTE '"', ESCAPE '"', NULL '')
```

| Option | Meaning | How to use |
| --- | --- | --- |
| `FORMAT csv` | CSV-formatted data | Use for files with delimiters, quotes, and fields containing special characters |
| `FORMAT text` | PostgreSQL COPY's own text format | Not synonymous with CSV |
| `HEADER true` | Skip header on import; write column names on export | Does not automatically map columns by name |
| `DELIMITER ','` | Field separator character | CSV default is typically comma |
| `QUOTE '"'` | CSV quoting character | Allows delimiters and newlines inside fields |
| `ESCAPE '"'` | Quote-escaping character | Double quotes inside fields are typically written `""` |
| `NULL ''` | Representation of SQL NULL in CSV | Needed to distinguish NULL from empty strings |
| `ENCODING 'UTF8'` | COPY data encoding | Should match the file's encoding |
| `FORCE_NULL` | Controls interpreting input CSV values as null on chosen columns | Use when required by the data source |
| `FORCE_NOT_NULL` | Controls interpreting empty fields as non-null | Understand its effect on empty strings |

### 6.1. Semicolon-delimited files

If a file uses `;` instead of a comma:

```csv
product_id;sku;product_name;unit_price;active
10;PEN-010;"Blue pen";10000.00;true
```

You must specify:

```text
\copy client_copy_lab.products (product_id, sku, product_name, unit_price, active) FROM 'products_semicolon.csv' WITH (FORMAT csv, HEADER true, DELIMITER ';')
```

Conversely, if you leave `,` as the delimiter when the file actually uses `;`, PostgreSQL may treat the entire line as one field or report missing columns.

### 6.2. Values with commas or quotes

The following fields are all valid CSV:

```csv
id,description
1,"SQL Book, advanced"
2,"Name with ""double quotes"""
```

CSV must be parsed according to quoting/escaping rules; you cannot simply "split every line by commas" while ignoring quoted fields.

### 6.3. Newlines inside a CSV cell

Valid CSV can contain fields spanning multiple physical lines:

```csv
id,description
1,"First line
Second line"
```

This is still **one data record** when read by a proper parser. Therefore, counting newlines in a file does not always equal the number of CSV records; reconciliation tools must use an actual CSV parser.

### 6.4. Text format and `\N`

PostgreSQL COPY also has `text` format. In `text` format, tab is normally the default delimiter and `\N` is the default NULL representation; special characters follow COPY text escaping rules.

Example:

```text
\copy (SELECT product_id, sku, product_name FROM client_copy_lab.products ORDER BY product_id) TO 'products.txt' WITH (FORMAT text)
```

Do not treat `FORMAT text` and `FORMAT csv` as interchangeable aliases for the same file; their escaping and NULL rules differ.

---

## 7. Distinguishing NULL from empty strings

In PostgreSQL's standard CSV mode, by default:

- An **unquoted, empty** field is interpreted as SQL `NULL`.
- A **quoted empty** field `""` is interpreted as an empty string `''`.
- The literal text `NULL` in a file is just text data unless you configure `NULL 'NULL'` or handle it explicitly.

Example `notes.csv`:

```csv
id,note
1,
2,""
3,NULL
```

Create a practice table:

```sql
CREATE TABLE client_copy_lab.notes (
    id INTEGER PRIMARY KEY,
    note TEXT
);
```

Import in psql:

```text
\copy client_copy_lab.notes (id, note) FROM 'notes.csv' WITH (FORMAT csv, HEADER true)
```

Check:

```sql
SELECT
    id,
    note,
    note IS NULL AS is_null,
    note = '' AS is_empty_string
FROM client_copy_lab.notes
ORDER BY id;
```

Expected interpretation:

| `id` | `note` | `is_null` | `is_empty_string` |
| --- | --- | --- | --- |
| 1 | SQL NULL | true | NULL |
| 2 | String `''` | false | true |
| 3 | String `'NULL'` | false | false |

Note that `NULL = ''` does not return `FALSE`; it evaluates to SQL `NULL` (unknown).

### 7.1. NULL vs. DEFAULT

In the `products` table, `created_at` was omitted from the import column list and received its default. If a column **is listed in the import** and the CSV provides a value interpreted as `NULL`, PostgreSQL does not substitute the column's default. If the column is `NOT NULL`, the import fails.

Therefore, when designing input files, distinguish carefully:

- Column **omitted from file/import** → default applies.
- Column **present in file with NULL** → NULL is stored unless explicitly transformed.
- Column **present with empty non-NULL string** → empty string is stored if the column type allows it.

---

## 8. Encoding, Unicode text, and numeric data

### 8.1. UTF-8

When text contains non-ASCII or multilingual characters, standardize on:

1. Saving files as UTF-8.
2. Specifying `ENCODING 'UTF8'` in COPY when explicitness is helpful.
3. Verifying the producer did not use a legacy encoding like Windows-1252.
4. Converting files with a BOM to UTF-8 without BOM if downstream steps fail on the leading character.

```text
\copy client_copy_lab.products (product_id, sku, product_name, unit_price, active) FROM 'products.csv' WITH (FORMAT csv, HEADER true, ENCODING 'UTF8')
```

If a file is not valid UTF-8, the server may raise `invalid byte sequence for encoding "UTF8"`. This is an encoding or source-data issue; granting extra database privileges will not fix it.

### 8.2. Decimal separators and locale

The `unit_price NUMERIC(12,2)` column in the example accepts numeric strings like `125000.00`. Another data source might export `125.000,00` based on locale. PostgreSQL does not automatically recognize every country's number format when loading into `NUMERIC`.

Good solutions:

- Standardize numeric formats in the CSV contract.
- Or import raw values as `TEXT` into a staging table and convert them using explicit rules.

Never blindly replace all commas with periods when the file uses commas as field delimiters.

### 8.3. Dates and timestamps

When importing `TIMESTAMPTZ` from a file, use timestamps with explicit time zone offsets, for example:

```text
2026-11-14T09:30:00+07:00
```

Date strings like `14/11/2026` can depend on `DateStyle` settings or require explicit parsing. This lab uses `created_at DEFAULT now()` to avoid timestamp parsing issues when not needed.

---

## 9. File paths and permissions

### 9.1. Relative paths

```text
\copy client_copy_lab.products TO 'export.csv' WITH (FORMAT csv, HEADER true)
```

The file is created relative to **the psql process's working directory**. To avoid confusion in scripts, use absolute paths.

### 9.2. Linux or macOS example

```text
\copy client_copy_lab.products TO '/home/student/exports/products.csv' WITH (FORMAT csv, HEADER true)
```

The `/home/student/exports` directory must exist and the OS user running psql must have write permission. PostgreSQL does not create missing client directories automatically.

### 9.3. Windows example

If `psql` runs directly on Windows:

```text
\copy client_copy_lab.products TO 'C:/data/exports/products.csv' WITH (FORMAT csv, HEADER true)
```

This Windows path is meaningless inside a Linux container if psql runs inside that container. Using `/` in examples helps avoid backslash-escaping confusion in certain contexts.

### 9.4. Distinguishing filesystem errors from SQL errors

| Message / symptom | Cause to check |
| --- | --- |
| `No such file or directory` | Wrong filename, wrong working directory, or file not on client filesystem |
| `Permission denied` when opening file | OS user running psql lacks read/write permission |
| `permission denied for table ...` | PostgreSQL role lacks `INSERT` or `SELECT` |
| `invalid input syntax for type ...` | CSV content does not match target data type |
| `duplicate key value violates unique constraint ...` | Input contains duplicate key values |
| Export file written to unexpected location | Misidentified where psql is running or used a relative path |
| Error near `\` in a SQL editor | Client does not support psql meta-commands |

When the file exists only on the client, granting PostgreSQL `SUPERUSER` will not make a missing client path appear.

---

## 10. Database privileges required for `\copy`

`\copy` uses the privileges of the connected PostgreSQL role:

| Operation | Relevant privileges |
| --- | --- |
| `\copy table FROM 'file.csv'` | `INSERT` on target table/columns, plus any others required by the operation |
| `\copy table TO 'file.csv'` | `SELECT` on read table/columns |
| `\copy (SELECT ...) TO ...` | Permission to execute the query, typically `SELECT` on referenced objects |
| Merging from staging into target table | Appropriate `INSERT` or `UPDATE` on the target table |
| SQL `COPY ... FROM '/server/file'` | In addition to table privileges, may require superuser or server file-read privilege |
| SQL `COPY ... TO '/server/file'` | In addition to table privileges, may require superuser or server file-write privilege |

A DBA in a lab environment can create an import account with only the necessary privileges:

```sql
CREATE ROLE client_copy_importer LOGIN PASSWORD 'REPLACE_WITH_STRONG_PASSWORD';
GRANT USAGE ON SCHEMA client_copy_lab TO client_copy_importer;
GRANT INSERT ON client_copy_lab.products TO client_copy_importer;
```

Read-only export account:

```sql
CREATE ROLE client_copy_exporter LOGIN PASSWORD 'REPLACE_WITH_ANOTHER_PASSWORD';
GRANT USAGE ON SCHEMA client_copy_lab TO client_copy_exporter;
GRANT SELECT ON client_copy_lab.products TO client_copy_exporter;
```

This is a lab privilege example. Production systems also require host controls, TLS, secret management, credential rotation, and access policies.

**Row-Level Security limitation:** PostgreSQL does not support `COPY FROM` on tables with RLS enabled in the same way as regular `INSERT` statements. When loading into RLS-protected systems, design an appropriate write path (such as inserting through application logic) rather than using `\copy` to bypass policy.

---

## 11. Transactions and import atomicity

Imported data must satisfy database constraints. If a file has a malformed number or duplicate key, `COPY FROM` fails.

### 11.1. Wrapping an import in a transaction

Inside a `psql` session:

```sql
BEGIN;
```

Then import on **a single line**:

```text
\copy client_copy_lab.products (product_id, sku, product_name, unit_price, active) FROM 'products.csv' WITH (FORMAT csv, HEADER true)
```

If the import succeeds and checks pass:

```sql
SELECT COUNT(*) FROM client_copy_lab.products;
COMMIT;
```

If the import fails or checks do not pass:

```sql
ROLLBACK;
```

These are **two mutually exclusive branches**, not `COMMIT` and `ROLLBACK` run back-to-back. After an error inside a transaction, PostgreSQL marks the transaction as aborted until rolled back.

### 11.2. `ON_ERROR_STOP` for scripts

Example script `import_products.sql` (a file **created by the learner on their client machine**, not a pre-existing project file):

```sql
\set ON_ERROR_STOP on
\copy client_copy_lab.products (product_id, sku, product_name, unit_price, active) FROM 'products.csv' WITH (FORMAT csv, HEADER true, ENCODING 'UTF8')
```

From the terminal:

```bash
psql -h localhost -U postgres -d postgres -v ON_ERROR_STOP=1 --single-transaction -f import_products.sql
```

- `ON_ERROR_STOP` tells psql to stop processing when an error occurs rather than continuing to subsequent commands.
- `--single-transaction` wraps the script in a transaction to commit or roll back all compatible work atomically.
- When using `--single-transaction`, the script **does not need its own `BEGIN` and `COMMIT`**.
- Relative filenames like `products.csv` resolve against **the psql process's working directory**, not necessarily the script's directory.
- Pipelines must check the **exit code** and error logs, not just whether a file exists or the final output line.

### 11.3. Failed COPY and physical storage

In PostgreSQL, if `COPY FROM` fails after processing some rows, rows from the failed COPY are never committed as visible data. However, physical row versions may remain for PostgreSQL to clean up later; for very large imports that fail late, monitoring disk usage or running `VACUUM` may be necessary.

Distinguish clearly between **transactional visibility** and **unreclaimed disk space**.

---

## 12. Staging tables: receiving data before writing to business tables

Loading external files straight into production tables carries high risk: bad formatting, duplicate keys, invalid rows, type mismatches, or unverified business rules.

A **staging table** lets you load raw data first and validate it before merging.

### 12.1. Creating a TEXT-based staging table

```sql
CREATE TABLE client_copy_lab.products_stage (
    product_id_text TEXT,
    sku TEXT,
    product_name TEXT,
    unit_price_text TEXT,
    active_text TEXT
);
```

Load from the file:

```text
\copy client_copy_lab.products_stage (product_id_text, sku, product_name, unit_price_text, active_text) FROM 'products.csv' WITH (FORMAT csv, HEADER true, ENCODING 'UTF8')
```

Raw data stays as text, preventing type-parsing errors during the initial load step.

### 12.2. Validating imported data

```sql
SELECT *
FROM client_copy_lab.products_stage
WHERE product_id_text IS NULL
   OR product_id_text !~ '^[0-9]+$'
   OR sku IS NULL
   OR btrim(sku) = ''
   OR product_name IS NULL
   OR btrim(product_name) = ''
   OR unit_price_text IS NULL
   OR unit_price_text !~ '^[0-9]+(\.[0-9]{1,2})?$'
   OR active_text IS NULL
   OR lower(active_text) NOT IN ('true', 'false');
```

This regex is only a simple rule for the sample file: it allows non-negative integers and non-negative prices with up to two decimal places. It **does not block numbers exceeding `NUMERIC(12,2)` bounds**, and real data may require extra whitespace handling, locale rules, or edge cases.

Check for duplicate keys in staging:

```sql
SELECT product_id_text, COUNT(*) AS duplicate_count
FROM client_copy_lab.products_stage
GROUP BY product_id_text
HAVING COUNT(*) > 1;
```

Check for duplicate `sku` values:

```sql
SELECT sku, COUNT(*) AS duplicate_count
FROM client_copy_lab.products_stage
GROUP BY sku
HAVING COUNT(*) > 1;
```

If the file contains errors, fix the source or filter the batch per a defined policy; never silently discard invalid rows.

### 12.3. Controlled data merge

Once validation passes, you can perform an intentional UPSERT by `product_id`:

```sql
BEGIN;

INSERT INTO client_copy_lab.products (
    product_id, sku, product_name, unit_price, active
)
SELECT
    product_id_text::INTEGER,
    btrim(sku),
    product_name,
    unit_price_text::NUMERIC(12,2),
    active_text::BOOLEAN
FROM client_copy_lab.products_stage
ON CONFLICT (product_id) DO UPDATE
SET sku = EXCLUDED.sku,
    product_name = EXCLUDED.product_name,
    unit_price = EXCLUDED.unit_price,
    active = EXCLUDED.active;

COMMIT;
```

The rules above represent **an illustrative update policy**:

- New product ID → insert product.
- Existing product ID → update selected columns.
- `created_at` on existing products stays unchanged because it is omitted from the UPDATE list.

Watch out for:

- Two staging rows with the same `product_id` in a single UPSERT statement will fail because PostgreSQL cannot update the same target row twice in one command.
- Two different `product_id` values sharing the same `sku` will still violate `UNIQUE(sku)`.
- Casting prices or IDs can fail if values are invalid or out of range.
- Never use UPSERT to overwrite business records if requirements only permit new inserts or require approval.

For systems running concurrent import batches, staging tables should include a `batch_id` or per-job isolation so batches do not mix.

---

## 13. Interactive input via STDIN

You can stream data directly through psql without creating a file:

```text
\copy client_copy_lab.products (product_id, sku, product_name, unit_price, active) FROM STDIN WITH (FORMAT csv)
```

Then enter the data rows:

```text
10,ERASER-010,White eraser,5000.00,true
11,RULER-011,Ruler,12000.00,true
\.
```

A line containing only `\.` marks the end of input in psql. The sample data **has no header** because the `\copy` command did not specify `HEADER true`.

This is convenient for learning how `FROM STDIN` works, but for large datasets use `FROM 'file.csv'` to avoid manual mistakes. When embedding inline data in a script, place the rows and `\.` terminator carefully; if forgotten, subsequent SQL statements will be consumed as CSV data.

---

## 14. Special syntax rules of the psql meta-command

A regular SQL statement can span multiple lines:

```sql
SELECT
    product_id,
    sku
FROM client_copy_lab.products
ORDER BY product_id;
```

By contrast, `\copy` has special parsing rules: psql treats the remainder of the line as arguments to the meta-command. To keep it reliable:

- Write **the entire `\copy` command on a single line**.
- Do not add a trailing `;` out of SQL habit.
- Do not split `\copy (SELECT ...) TO ...` across lines as if it were SQL.
- Do not assume `:variable` interpolation or backtick expansion from other meta-commands works identically inside `\copy`.
- Do not place another meta-command after `\copy` on the same line.

Example:

```text
\copy (SELECT sku FROM client_copy_lab.products ORDER BY sku) TO 'sku.csv' WITH (FORMAT csv, HEADER true)
```

If an export query is long, consider creating an authorized view or generating the single-line command carefully via script. Using SQL `COPY (query) TO STDOUT` with a supporting driver/API is also an option for applications not running psql.

---

## 15. Monitoring progress and performance

### 15.1. Why is `\copy` usually faster than row-by-row INSERTs?

COPY streams data continuously and avoids round-trips for individual `INSERT` statements. For large row counts, this significantly improves throughput.

Total duration still depends on:

- Client ↔ server network bandwidth.
- Local file read/write speed.
- CSV parsing and type conversion speed.
- Indexes, foreign keys, triggers, and table constraints.
- WAL, disk I/O, checkpoints, and lock contention.
- File size, transaction boundaries, and validation overhead.

Do not arbitrarily disable constraints or triggers for speed when data integrity matters. For very large datasets, use staging, batching, or bulk-load strategies benchmarked in an equivalent environment.

### 15.2. `pg_stat_progress_copy`

PostgreSQL provides a progress-monitoring view on supported versions:

```sql
SELECT
    pid,
    datname,
    relid::regclass AS relation_name,
    command,
    type,
    bytes_processed,
    bytes_total,
    tuples_processed,
    tuples_excluded
FROM pg_stat_progress_copy;
```

This view shows running COPY operations, depending on privileges and version. When streaming via STDIN/STDOUT, `bytes_total` may not be known on the server side. `tuples_processed` does not mean those rows **have committed** if the operation is still running or later rolls back.

For a sample table with only a few rows, COPY finishes too fast to observe from another connection.

### 15.3. Batch reconciliation

To verify an import succeeded accurately:

1. Count CSV records using a parser that understands quoting and embedded newlines.
2. Compare against the row count reported by COPY.
3. Compare row counts in the table **for the specific batch**, rather than total table count if prior data existed.
4. Validate keys, NULL ratios, out-of-range values, and required control totals.
5. Record batch metadata, checksums, timestamps, and errors for traceability.

When `\copy` writes an export file and a later job step fails, still reconcile before assuming the output is valid for use.

---

## 16. Securing CSV files and import/export accounts

Important safeguards:

- **Least privilege:** import accounts get only required `INSERT`; export accounts get only `SELECT` on permitted objects.
- **Encrypted connections:** when running psql remotely, configure TLS appropriately on client and server.
- **Separate secrets:** never hard-code passwords in scripts, Git, or exposed command lines.
- **Target directory permissions:** restrict file read/write access, especially when exporting personal data.
- **Scoped SELECTs:** select only the columns and rows needed for the task.
- **Retention and cleanup:** do not leave exported files indefinitely on laptops, CI runners, or shared folders.
- **Care when opening in spreadsheets:** `\copy` does not prevent CSV formula injection. User-entered strings starting with `=`, `+`, `-`, or `@` may be evaluated as formulas by spreadsheet software. If Excel or similar tools are the target, handle output safely while preserving data accuracy.

Just because a file sits on the client side does not make it safe: it can still hold sensitive data, get auto-synced to cloud drives, or be read by other processes on the machine.

---

## 17. Common errors

| Error / symptom | Common cause | How to handle |
| --- | --- | --- |
| `syntax error at or near "\"` | Sent `\copy` as ordinary SQL | Run inside `psql` |
| `No such file or directory` | File missing on psql machine or wrong working directory | Check client filesystem and use absolute paths |
| `Permission denied` opening file | psql's OS user lacks permissions | Use a directory/file with appropriate permissions |
| `permission denied for table` | PostgreSQL role lacks `SELECT`/`INSERT` | Grant minimal required privileges |
| `missing data for column` | File has fewer fields than column list | Check file structure and column list |
| `extra data after last expected column` | Unquoted comma in field or extra columns in file | Fix CSV quoting or column list |
| `invalid input syntax for type numeric` | Price does not match numeric format | Normalize data or use staging |
| `duplicate key value violates unique constraint` | Re-importing existing keys | Use staging and an explicit merge policy |
| Garbled Unicode text | Wrong encoding or BOM | Verify source encoding and use UTF-8 properly |
| Header treated as data | Forgot `HEADER true` | Add the header option |
| Columns mapped wrongly despite header | Header does not auto-map column names | Align the column list order |
| Export file stuck inside container | psql actually ran inside a container | Mount/transfer the file via workflow |
| Script keeps running after import error | Missing error handling | Use `ON_ERROR_STOP`, transactions, and exit codes |
| CSV exists but row count looks wrong | Embedded newlines in quotes or partial query | Use a proper CSV parser and check query filters |

---

## 18. Practice exercises

### Exercise 1 — Distinguishing client and server sides

PostgreSQL runs on `db.internal`, while `psql` runs on your laptop. If you run:

```text
\copy client_copy_lab.products TO '/tmp/products.csv' WITH (FORMAT csv, HEADER true)
```

Where is the file created? If `psql` runs inside a Docker container, how does the answer change? Why doesn't the PostgreSQL server need read/write access to your laptop's directories?

### Exercise 2 — Importing and verifying three products

Create `products.csv` per Section 3.3, run the import command with the 5-column list and `HEADER true`. Read the table back with `SELECT`. Verify the comma in the book title, the double quotes in `PEN-002`, and the `created_at` values.

### Exercise 3 — Exporting only active products

Run:

```text
\copy (SELECT sku, product_name, unit_price FROM client_copy_lab.products WHERE active = true ORDER BY sku) TO 'active_products.csv' WITH (FORMAT csv, HEADER true)
```

Verify row count and product ordering. Why should `ORDER BY` be specified explicitly when deterministic file ordering is required?

### Exercise 4 — NULL and empty string

Create `notes.csv` from Section 7, import it into `notes`, and run `note IS NULL` alongside `note = ''`. Explain why `COUNT(note)` skips row id 1 but includes row id 2.

### Exercise 5 — Delimiters and quoting

An incoming file contains the line:

```csv
21,BOOK-021,Book, advanced,129000.00,true
```

If 5 columns are expected but the line has an extra comma inside the name, how many fields will the parser see? Rewrite the name field as `"Book, advanced"` to make it valid.

### Exercise 6 — Second import

After importing the sample file, run the same `\copy` command again into `products`. Explain the unique violation error and propose using staging + `ON CONFLICT` instead of wiping all existing table data.

### Exercise 7 — Failed transaction

Create a CSV with one valid row and one row whose `unit_price` is `abc`. Try importing inside a transaction. Observe the error, roll back, and check the row count in the table. Why can't you look at intermediate processed rows and assume they committed?

### Exercise 8 — Access privileges

Design two roles: one that can only load into `products_stage`, and one that can only export from `products`. Write the minimal `GRANT` statements and explain why `SUPERUSER` is not needed just to use `\copy` with client files.

### Exercise 9 — Automated script

Design a daily job exporting `sku` and `unit_price` to CSV, with exit code checks, encryption/storage handling, retention policy, and batch metadata. If the job runs inside a CI runner, where must the output file be collected from?

---

## 19. Reliable import/export workflow

```text
IMPORT
File from validated source
        |
        v
Verify encoding + header + delimiter + column count
        |
        v
\copy FROM into staging (when validation is needed)
        |
        v
Validate data, duplicate keys, NULLs, type casts
        |
        v
BEGIN -> merge into target table -> COMMIT
        |
        v
Reconcile row counts + record batch metadata + manage files

EXPORT
Confirm purpose and read permissions
        |
        v
SELECT exact permitted columns and rows
        |
        v
\copy (SELECT ...) TO local CSV
        |
        v
Verify contents + protect file + transfer securely
```

Responsibilities of each layer:

| Component | Responsible for |
| --- | --- |
| PostgreSQL server | Executing SQL/COPY, validating data types, constraints, table privileges, and transactions |
| `psql` client | Opening local files, streaming data over the connection, writing local files, and reporting errors |
| Operational script/application | Selecting the right file, validation, protecting secrets, reconciliation, retry/idempotency, and retention |

## Conclusion

`\copy` is a **`psql` meta-command** for importing and exporting data between PostgreSQL and **files on the client side**. On `FROM`, psql reads a local file and sends data to the server using the COPY protocol; on `TO`, psql receives data from the server and writes a local file.

Remember four principles: **(1) file paths belong to the machine running psql; (2) CSV files must match column order, encoding, and formatting; (3) PostgreSQL privileges and constraints still apply; (4) production imports/exports require transactions, error checking, reconciliation, and file protection.** Once you understand the client/server boundary and data contract, you can use `\copy` to build simple, fast, and safe import/export workflows without granting arbitrary access to the database server's filesystem.
