# Text, CSV, Binary Formats and Encoding Choices in PostgreSQL

Importing and exporting data is one of the tasks most prone to silent errors when operating PostgreSQL. A file that looks like "just rows and columns" can contain many hidden conventions: delimiters, embedded newlines, double quotes, NULL values, empty strings, character encodings, byte order marks (BOM), decimal formatting, timestamps, and data types.

For example, the following two values are **not the same**:

- SQL `NULL`: absence of a value.
- Empty string `''`: a text value with zero length.

If you export a table to CSV and re-import it without agreeing on how both cases are represented, the data can change meaning without throwing a single error.

PostgreSQL provides the **`COPY`** command with three primary data formats:

- **Text**: character-delimited fields, tab by default; special characters are escaped using PostgreSQL-specific rules.
- **CSV** (*Comma-Separated Values*): a character-based tabular format supporting quotes, delimiters, embedded newlines, and headers; convenient for exchanging data with Excel, BI tools, and other applications.
- **Binary**: uses PostgreSQL's proprietary COPY binary representation; suitable for certain bulk data transfers between compatible PostgreSQL systems, but not a universal interchange file format.

Alongside the format, you must choose an appropriate **character encoding**, usually UTF-8 for new systems. Format and encoding solve two distinct questions:

```text
                   PostgreSQL Data
                          |
                   COPY / \copy
                          |
          +---------------+----------------+
          |               |                |
       FORMAT text     FORMAT csv      FORMAT binary
          |               |                |
   field/line escape  quote/delimiter   type-specific bytes
          |               |                |
          +---------------+----------------+
                          |
                Byte stream / file
                          |
           When character data is present: encoding
           UTF-8, LATIN1, WIN1252, ...
```

This lesson belongs to the **Database Engine Relational PostgreSQL** module, chapter **Data Import and Export**, on the topic **"Text, CSV, Binary Formats and Encoding Choices"**. It focuses on format selection, `COPY` syntax and semantics, server-side vs. client-side distinctions, safe file design, Unicode handling, and round-trip data verification.

---

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish **data format** from **character encoding**.
2. Explain the roles of `COPY FROM`, `COPY TO`, `COPY FROM STDIN`, `COPY TO STDOUT`, and the `psql` `\copy` command.
3. Understand why the file path in `COPY ... FROM '/path'` resides on the **PostgreSQL server**, while in `\copy ... FROM 'path'` it is normally a file on the **machine running psql**.
4. Choose `FORMAT text`, `FORMAT csv`, or `FORMAT binary` based on your objective.
5. Understand delimiters, line endings, backslash escapes, and NULL markers in text format.
6. Understand CSV headers, delimiters, quotes, escapes, and fields containing commas or newlines.
7. Distinguish `NULL`, empty strings, and literal strings representing NULL.
8. Use `HEADER`, `HEADER MATCH`, `NULL`, `QUOTE`, `ESCAPE`, `FORCE_QUOTE`, `FORCE_NULL`, and `FORCE_NOT_NULL` where appropriate.
9. Understand that binary COPY is not a "fast CSV" format or a long-term backup format.
10. Understand `server_encoding`, `client_encoding`, and the COPY `ENCODING` option.
11. Recognize byte order marks (BOM), UTF-8/UTF-16/Windows code page files, and Vietnamese character encoding issues.
12. Know the limitations of "changing encoding" for data that already suffers from mojibake or lost characters.
13. Design CSV files that preserve Unicode, timestamps, decimals, quotes, and newlines.
14. Build a lab pipeline loading into a text staging table, validating/normalizing, and promoting to a typed table.
15. Handle records with type errors or constraint violations without swallowing errors.
16. Understand how COPY interacts with triggers, CHECK, FOREIGN KEY, RLS, transactions, and WAL.
17. Balance ingestion speed with safety, observability, and post-import recovery.
18. Understand CSV/Spreadsheet formula injection risks when others open exported files in spreadsheets.
19. Use `psql \copy` and streaming COPY in applications instead of granting unnecessary server file privileges.
20. Design *round-trip* tests for text, CSV, binary, and encoding.

**Scope:** Modern PostgreSQL. Some advanced `COPY` options (such as per-row import error handling or header matching) depend on the version. Always check `SELECT version();` and the documentation for your active version before deploying to production. Examples use an isolated schema in a lab database.

---

## 2. Why Import/Export Formatting Is Part of Data Correctness

Moving data from A to B involves at least four stages:

```text
Source value
   |
   v
Serialize: convert value to bytes
   |
   v
Transfer file / stdin / network
   |
   v
Parse & convert: bytes to target value
   |
   v
Validate data types and constraints
   |
   v
Target value
```

Any stage can introduce discrepancies.

### 2.1. Column Splitting Errors

The value `Hà Nội, Việt Nam` contains a comma. If the CSV file is not properly quoted, the parser may interpret it as two columns instead of one.

### 2.2. Newline Errors

A two-line note can be parsed as two separate records if a parser reads CSV by physical lines without recognizing quoted fields.

### 2.3. NULL and Empty String Errors

In PostgreSQL's default CSV format, NULL is exported as an **unquoted** empty field, whereas an empty string is exported as `""`. If another tool does not preserve this distinction, a round-trip can turn NULL into an empty string or vice versa.

### 2.4. Encoding Errors

The name `Đặng Thị Hạnh`, valid in Unicode, can turn into garbled characters when UTF-8 bytes are decoded under a different code page.

### 2.5. Data Type Errors

The string `1,25` may represent a locale-formatted decimal with a comma, while a PostgreSQL `NUMERIC` column generally expects standard engine numeric syntax such as `1.25`. Using a comma as the CSV delimiter makes this notation even more error-prone.

### 2.6. Timestamp Errors

`2026-11-14 09:00` has no explicit timezone; `2026-11-14T09:00:00+07:00` specifies an exact instant. When loaded into `TIMESTAMPTZ` under a different session timezone, a value without an offset can take on a different meaning.

**Conclusion:** "COPY ran without errors" is not enough to prove the data was imported accurately from a business perspective.

---

## 3. What Is COPY?

`COPY` is a PostgreSQL SQL statement used to transfer rows in bulk between a table or query and a data stream or file.

### 3.1. Importing Data

```sql
COPY schema_name.table_name (col1, col2, col3)
FROM '/server/path/data.csv'
WITH (FORMAT csv, HEADER true);
```

Here, the file path is resolved on the **PostgreSQL server** and is only permitted under the corresponding privilege rules.

### 3.2. Exporting Data

```sql
COPY schema_name.table_name (col1, col2)
TO '/server/path/export.csv'
WITH (FORMAT csv, HEADER true);
```

### 3.3. Exporting Query Results

```sql
COPY (
    SELECT order_id, customer_name, amount
    FROM app.orders
    WHERE status = 'PAID'
    ORDER BY order_id
)
TO STDOUT
WITH (FORMAT csv, HEADER true);
```

### 3.4. STDIN and STDOUT

`STDIN` and `STDOUT` use the data-transfer protocol over the **client–server connection**; they do not mean the server opens a file on the user's laptop.

```sql
COPY app.orders (order_id, customer_name)
FROM STDIN
WITH (FORMAT csv, HEADER true);
```

This statement requires a client supporting the COPY protocol to supply data over the corresponding STDIN stream.

### 3.5. COPY Is Not Row-by-Row INSERT

COPY typically reduces network round trips and per-statement overhead compared to numerous individual INSERTs, making it well-suited for bulk loading. However, COPY still adheres to PostgreSQL data types, constraints, triggers, and transaction semantics.

### 3.6. Format and Data Source Are Independent Axes

You can combine:

- CSV + server file.
- CSV + STDIN.
- Text + STDOUT.
- Binary + STDIN/STDOUT.

Do not equate "CSV" with "client file" or "binary" with "server file".

---

## 4. COPY vs. \copy: A Crucial Distinction

`\copy` is a **`psql` meta-command**, not PostgreSQL SQL that can be sent directly over JDBC.

| Aspect | SQL `COPY ... FROM '/path'` | `psql \copy ... FROM 'path'` |
| --- | --- | --- |
| Who opens the file? | PostgreSQL server process | Machine/process running psql |
| Where is the file path? | Filesystem on the database server | Filesystem on the psql client |
| Transfer channel | Server reads/writes file | Over COPY STDIN/STDOUT |
| OS file permissions | Server process OS account | psql process OS account |
| Special DB privileges | May require superuser or predefined file roles | Normally no server file read/write privileges needed |
| Usage in JDBC | SQL COPY protocol via driver | Cannot send `\copy` directly |
| Convenience for developers | Limited for remote databases | Often more convenient |

### 4.1. Example of \copy Importing a Local File

Inside a `psql` prompt:

```text
\copy app.orders (order_id, customer_name, amount) FROM './orders.csv' WITH (FORMAT csv, HEADER true)
```

`./orders.csv` is resolved relative to the `psql` working environment, not the PostgreSQL server's working directory.

### 4.2. Example of \copy Exporting to a Local File

```text
\copy (SELECT order_id, amount FROM app.orders ORDER BY order_id) TO './orders-export.csv' WITH (FORMAT csv, HEADER true)
```

### 4.3. If psql Runs Inside Docker, CI, or Another Host

"Client file" means the **machine/process running psql**, which could be a container, CI runner, or bastion host—not necessarily the developer's laptop. Always verify the active filesystem and volume mounts.

### 4.4. Server-File SQL COPY Carries Privilege Risks

Reading or writing files on the server involves special roles such as `pg_read_server_files`, `pg_write_server_files`, or superuser in the corresponding cases. These privileges cross normal SQL data boundaries; never grant them to an API role just to import a CSV.

### 4.5. COPY PROGRAM Has Highly Sensitive Privileges

`COPY ... PROGRAM` executes a server-side program under privileged conditions. It is not a convenient shortcut to read arbitrary files or invoke shell commands from an HTTP API. Never interpolate user input into a server-side command string.

**Preference:** Use `\copy` or the COPY protocol from a dedicated least-privilege import/export process whenever you only need client-side file access.

---

## 5. Comparing the Three Main Formats

| Criterion | Text | CSV | Binary |
| --- | --- | --- | --- |
| Human-readable | Yes, if you understand escapes | Yes | No |
| Field formatting | Delimiter + backslash escapes | Delimiter + quoting/escaping | Type-specific binary encoding |
| Default delimiter | Tab | Comma | No character delimiter like text |
| Default NULL | `\N` | Unquoted empty field | Binary NULL marker |
| Header | Not like CSV HEADER | Supports HEADER | No CSV-style header |
| Fields with newlines | Escaped per text rules | Allows newlines inside quoted fields | Binary payload per field |
| Spreadsheet exchange | Awkward | Very common, requires formula-injection defense | Unsuitable |
| Compatibility outside PostgreSQL | Needs a PostgreSQL-rule parser | High if adhering to CSV dialect | Low |
| Inspectable in text editor | Yes | Yes | No |
| Character encoding | Must agree on encoding | Must agree on encoding | Not a text file |
| Long-term interchangeability | Fair, if dialect is documented | Usually best with a schema contract | Not an archival choice |
| Speed | Depends on types and workload | Depends on quoting/parsing | Can be fast between identical systems, not guaranteed |
| Default recommendation | PostgreSQL-specific pipelines | Structured data exchange across systems | Controlled, compatible PostgreSQL COPY streams |

**No single format is "fastest" for every workload.** Always benchmark on the same tables, data, indexing, network, hardware, and transaction strategy.

---

## 6. Text Format: Basic Structure

PostgreSQL's text format is the traditional format: each row consists of fields separated by **tab** by default. Newlines terminate records, and special characters are escaped with backslashes.

Example:

```sql
COPY (
    SELECT 101 AS id, 'Nguyễn An'::TEXT AS name
    UNION ALL
    SELECT 102, 'Lê Bình'
)
TO STDOUT
WITH (FORMAT text);
```

Conceptually, the output looks like:

```text
101<TAB>Nguyễn An<NEWLINE>
102<TAB>Lê Bình<NEWLINE>
```

The `<TAB>` and `<NEWLINE>` tokens are **illustrative placeholders**; in the actual stream, they are the literal characters.

### 6.1. Changing the Delimiter

```sql
COPY app.simple_export
TO STDOUT
WITH (
    FORMAT text,
    DELIMITER '|'
);
```

A delimiter must follow the format's rules. Text COPY does not turn into CSV simply because you choose a comma or pipe.

### 6.2. What If Data Contains the Delimiter?

Text format escapes the delimiter according to text rules. A parser that naively calls `split('|')` without handling escapes will corrupt data.

### 6.3. Text Format Uses Backslash Escapes

Special characters are represented by escape sequences such as:

| Meaning | Text COPY Representation |
| --- | --- |
| Line feed (LF) inside a field | `\n` |
| Carriage return (CR) | `\r` |
| Tab | `\t` |
| Literal backslash character | `\\` |
| Default NULL | `\N` |

These are **character sequences in the text COPY file**, not Java source or SQL string literal escapes.

### 6.4. Do Not Write Custom Text Parsers with split

If a field contains escaped tabs or newlines, a hasty parser will split fields incorrectly. Use PostgreSQL's own COPY parser or a parser implementing the documented dialect.

---

## 7. Text Format: NULL and Empty Strings

Suppose:

```sql
SELECT
    NULL::TEXT AS a,
    ''::TEXT AS b,
    E'hello\\world'::TEXT AS c;
```

When exported in default text format:

- NULL is written as the `\N` marker.
- An empty string is a zero-length field.
- Backslashes inside values are escaped.

### 7.1. Customizing the NULL Marker

```sql
COPY app.some_table
TO STDOUT
WITH (
    FORMAT text,
    NULL 'NULL'
);
```

Be very careful: if real data contains the string `'NULL'`, the encoding/escaping must allow the parser to distinguish the string value from the marker during round-trips. Using the default marker or an unambiguous convention is generally safer.

### 7.2. The Text NULL Marker Is Not a SQL Keyword

In a file:

```text
\N
```

is a COPY text format marker. In SQL:

```sql
SELECT NULL;
```

is the SQL NULL value. Do not take a file marker and paste it directly into an `INSERT` statement without understanding the syntax.

### 7.3. Verifying with IS NULL

After import:

```sql
SELECT
    COUNT(*) FILTER (WHERE note IS NULL) AS null_notes,
    COUNT(*) FILTER (WHERE note = '') AS empty_notes
FROM app.some_table;
```

This verifies semantics far better than eyeballing the file.

### 7.4. Whitespace-Only Strings Are Not Empty Strings

`' '` and `''` are not the same. Never silently `TRIM` every column in an import/export pipeline without an explicit data policy.

---

## 8. Text Format: Watch Out for Backslashes and Ending COPY STDIN

In many `psql` contexts, when entering data inline for `COPY FROM STDIN`, a line containing only `\.` terminates the input stream. This is a **convention of the client/protocol**, not an ordinary data record that every text file parser handles automatically.

Example in `psql`:

```text
COPY app.simple_import (id, value) FROM STDIN WITH (FORMAT text);
1	hello
2	world
\.
```

The two data rows above are separated by real tabs.

### 8.1. Do Not Paste Arbitrary Data into a Terminal Without Escaping

If user-entered data contains backslashes, tabs, or newlines, manual pasting can alter its meaning. For real files, prefer `\copy FROM 'file'` or the COPY protocol from code.

### 8.2. Do Not Treat \. as a General CSV Delimiter

In an ordinary CSV file, a field value of `\.` can be valid data. The end-of-data marker's meaning applies to **STDIN/psql input context**, not universal CSV parsing.

### 8.3. One Physical Line Is Not Always One CSV Row

This difference becomes clear when switching to CSV with quoted multiline fields. Do not apply text COPY assumptions to CSV.

---

## 9. CSV Format: Basic Structure

PostgreSQL CSV is a dialect with delimiter, quote, escape, header, and NULL rules. Defaults typically use:

- `DELIMITER ','`.
- `QUOTE '"'`.
- `ESCAPE '"'`.
- NULL represented by an unquoted empty field.
- Empty strings quoted on export to distinguish them from NULL by default.

Example:

```sql
COPY (
    SELECT 1 AS id, 'Hà Nội, Việt Nam' AS location
    UNION ALL
    SELECT 2, 'TP. Hồ Chí Minh'
)
TO STDOUT
WITH (
    FORMAT csv,
    HEADER true
);
```

The CSV output looks like:

```csv
id,location
1,"Hà Nội, Việt Nam"
2,TP. Hồ Chí Minh
```

### 9.1. Why Are Quotes Needed?

The name `Hà Nội, Việt Nam` contains a comma. Without quotes, a parser would see more columns than expected.

### 9.2. QUOTE Differs from SQL String Quotes

In SQL source, single quotes `'...'` delimit string literals. In CSV files, the default quote character is the double quote `"`, protecting fields that contain delimiters, newlines, or quotes.

### 9.3. CSV Has No Built-In Data Types

All CSV fields are represented as characters. On import into PostgreSQL, the parser converts text into target types such as INTEGER, NUMERIC, TIMESTAMPTZ, or BOOLEAN.

### 9.4. CSV Is Not Self-Describing for Full Schemas

A header `amount,ordered_at` does not convey NUMERIC precision/scale, timezone policy, NULL semantics, or constraints. Serious data exchanges require an accompanying **schema contract**.

---

## 10. CSV: Delimiter, Quote, and Escape

Example field containing a comma:

```csv
external_id,buyer,note
E-001,"Nguyễn An","Giao tại Quận 1, TP.HCM"
```

Field containing double quotes:

```csv
external_id,buyer,note
E-002,"Lê Bình","Gói ""combo"" tháng 11"
```

Field containing a newline:

```csv
external_id,buyer,note
E-003,"Trần Cẩm","First line
Second line"
```

### 10.1. Two Consecutive Double Quotes

With `QUOTE '"'` and `ESCAPE '"'`, a literal quote inside a field is represented by doubling the quote:

```text
"Order ""combo"" today"
```

is parsed as:

```text
Order "combo" today
```

### 10.2. One Logical Row Can Span Multiple Physical Lines

If a CSV reader simply calls `readLine()` and `split(",")`, it will break the quoted newline example. Use a stateful CSV parser that understands quoted fields, or PostgreSQL's COPY parser.

### 10.3. Delimiters Can Be Changed

```sql
COPY app.orders
TO STDOUT
WITH (
    FORMAT csv,
    DELIMITER ';',
    HEADER true
);
```

Semicolons sometimes appear in files generated by locale-configured spreadsheet software. However, changing the delimiter does not make a decimal like `12,5` automatically valid for `NUMERIC` input.

### 10.4. The CSV Dialect Must Be Documented

When transferring files across organizations, specify delimiter, quote, escape, newline, encoding, NULL marker, header, timezone, numeric format, and spreadsheet formula handling.

---

## 11. CSV: NULL, Empty Strings, and Quoted Values

This is one of the most important rules.

Suppose a TEXT column holds three values:

1. `NULL`.
2. `''` (empty string).
3. `'NULL'` (a four-letter string).

With default CSV:

| SQL Value | Illustrative CSV Field Representation |
| --- | --- |
| `NULL` | Unquoted empty field |
| `''` | `""` |
| `'NULL'` | `NULL` |

### 11.1. Why Does This Differ from Text Format?

Text COPY defaults to `\N` for NULL. CSV defaults to an unquoted empty string as the NULL marker and quotes empty strings to preserve semantics.

### 11.2. Do Not Assume Every Blank Cell Is NULL

If a spreadsheet exports both empty cells and empty strings as bare empty fields, the original distinction is already lost. COPY cannot reconstruct information the file does not record.

### 11.3. Setting an Explicit NULL Marker

To make files easier to exchange in controlled pipelines:

```sql
COPY app.some_table
TO STDOUT
WITH (
    FORMAT csv,
    HEADER true,
    NULL '\N'
);
```

Then an unquoted `\N` field represents SQL NULL, and an empty string need not be conflated with the null marker.

### 11.4. Real Data Can Also Contain the Marker

If actual data can contain the string `\N`, the serializer and parser must quote appropriately to distinguish them. It is always best to round-trip test NULL, empty strings, and the literal marker together.

---

## 12. CSV: FORCE_NULL, FORCE_NOT_NULL, and FORCE_QUOTE

These options address common ambiguities.

### 12.1. FORCE_QUOTE When Exporting CSV

```sql
COPY app.some_table
TO STDOUT
WITH (
    FORMAT csv,
    HEADER true,
    FORCE_QUOTE *
);
```

This option forces quoting of **non-NULL** values according to COPY rules. It does not turn NULL into an empty string.

### 12.2. FORCE_NULL When Importing CSV

`FORCE_NULL (col)` enables matching against the NULL marker even when the field is quoted in applicable cases.

If the NULL marker is an empty string, `""` is normally an empty string; with `FORCE_NULL` on that column, it can be interpreted as NULL.

### 12.3. FORCE_NOT_NULL When Importing CSV

`FORCE_NOT_NULL (col)` prevents the parser from **treating values matching the NULL marker as NULL** in applicable cases. For instance, with the default empty NULL marker, an unquoted empty field can be kept as an empty string for the specified column.

### 12.4. Combining Both Options

In supported versions, both `FORCE_NULL` and `FORCE_NOT_NULL` can be applied to the same column to distinguish how **quoted** vs. **unquoted** NULL markers are interpreted.

### 12.5. Only Apply with an Explicit Contract

Do not blindly enable `FORCE_NULL`/`FORCE_NOT_NULL` across an entire file. First decide:

- What does an empty field mean?
- What does `""` mean?
- Can text data contain the literal marker?
- Are numeric/date columns allowed to be missing?

### 12.6. Use Text Staging to Preserve Raw Semantics

When sources are untrusted or frequently change dialect, loading into TEXT staging columns and normalizing explicitly is safer than forcing direct loads into production tables.

---

## 13. HEADER, HEADER MATCH, and Column Ordering

A CSV file typically has a header:

```csv
external_id,buyer,status,amount_text,order_time_text,note
E-1001,Nguyễn An,PAID,125000.50,2026-11-01T08:30:00+07:00,Place order
```

### 13.1. HEADER true

```sql
COPY app.stage_orders
FROM STDIN
WITH (
    FORMAT csv,
    HEADER true
);
```

Normally skips the first header row when importing CSV. `HEADER true` by itself does not map fields by header name regardless of order.

### 13.2. Specify the Column List

```sql
COPY app.stage_orders (
    external_id,
    buyer,
    status,
    amount_text,
    order_time_text,
    note
)
FROM STDIN
WITH (
    FORMAT csv,
    HEADER true
);
```

The column list defines **which column receives each position's data**. If a file swaps two columns without updating the importer, values will load into the wrong columns even if the header names look right.

### 13.3. HEADER MATCH

On PostgreSQL versions supporting this option, `HEADER MATCH` requires header names to match the target columns per COPY rules.

Example:

```sql
COPY app.stage_orders (
    external_id,
    buyer,
    status,
    amount_text,
    order_time_text,
    note
)
FROM STDIN
WITH (
    FORMAT csv,
    HEADER MATCH
);
```

**Do not mistake HEADER MATCH for automatic column reordering**; its goal is to verify that the header matches the copied columns in the expected order. Check support in your running version.

### 13.4. When Files Have Extra Columns

If an export adds columns, the importer needs an updated contract or an intermediate transform step. Do not silently ignore extra data if it could shift column mappings.

### 13.5. When the Header Has a BOM

If a BOM precedes the first column name, tools may see the first column name as starting with a special character instead of `external_id`. `HEADER MATCH` can fail with a mismatch. Normalize encoding and BOM during ingestion before checking headers.

---

## 14. CSV and CRLF/LF Line Endings

Different platforms commonly use:

- **LF** (`\n`) on Unix/Linux.
- **CRLF** (`\r\n`) on many Windows files.
- Standalone **CR** in legacy data.

### 14.1. CSV Parsers Must Distinguish Record Newlines from Field Newlines

Example:

```csv
id,note
1,"First order
Deliver after 5 PM"
2,"No notes"
```

Physically there are multiple lines, yet there are only **two data records** after the header.

### 14.2. Do Not Blindly Run Global Newline Replacement

Replacing all `\r\n` with `\n` can help when encoding and format are certain, but if the tool breaks quoting or BOM structure, data can still be corrupted. For CSV, use a dialect-aware parser.

### 14.3. Define a Newline Policy on Export

If a consumer requires CRLF, you can use client-side newline tools or COPY options supported by your PostgreSQL version for that purpose. Avoid assuming all PostgreSQL versions share identical newline options.

### 14.4. One Record Does Not Always Equal One readLine Call

In Java programming, use a streaming CSV parser that tracks quote state rather than `BufferedReader.readLine() + String.split()`.

---

## 15. Binary COPY: A PostgreSQL Format, Not Encoded CSV

`FORMAT binary` serializes data using PostgreSQL's binary COPY format.

Example:

```sql
COPY app.orders
TO STDOUT
WITH (FORMAT binary);
```

Or via `psql`:

```text
\copy app.orders TO './orders.copybin' WITH (FORMAT binary)
```

### 15.1. Cannot Be Opened in a Text Editor for Direct Reading

The file contains raw bytes, headers/flags, and field payloads following binary COPY rules. Vietnamese characters are not "plainly visible" as in CSV.

### 15.2. Primary Purposes

- Efficient data transfer between clients supporting the binary COPY protocol and PostgreSQL.
- Certain bulk transfers between compatible PostgreSQL systems.
- Avoiding part of the overhead of converting types to text and parsing them back.

### 15.3. Not a Universal Interchange Format

Spreadsheets, BI tools, and other database engines generally do not understand PostgreSQL binary COPY files.

### 15.4. Not a Long-Term Backup Choice

The binary COPY format has compatibility constraints across versions, architectures, type representations, and schemas. For PostgreSQL backup and restore, use official tools like `pg_dump/pg_restore` or proper physical backups—never use binary COPY as a complete recoverable database backup.

### 15.5. Not Guaranteed to Be Fastest

Performance depends on CPU conversion, type mix, network, buffering, constraints, WAL, and hardware. Binary may offer little gain if the main bottleneck is index maintenance or disk I/O.

---

## 16. Binary COPY: Conceptual Structure

At a high level, a binary COPY stream consists of:

```text
File signature / header
      |
      v
Format flags / extension area
      |
      v
Record 1:
    field count
    field 1 length + bytes
    field 2 length + bytes
    ...
      |
      v
Record 2 ...
      |
      v
End marker
```

NULL values have a dedicated representation rather than relying on `\N` strings or empty CSV fields.

### 16.1. Format Depends on Type Binary Send/Receive Routines

Two columns with the same byte length when printed as text do not necessarily share the same binary representation. Binary COPY transfers data using each PostgreSQL type's send/receive routines.

### 16.2. Column Count and Order Must Match

Do not add a column to the target table and reload an old binary file by implicit position expecting PostgreSQL to guess the schema.

### 16.3. Data Types Must Match

The displayed value `100` has different binary representations for INTEGER, BIGINT, and NUMERIC. Loading binary bytes of one type into a column of another type can fail or be misinterpreted.

### 16.4. Never Hand-Edit Bytes in a Binary COPY File

Opening the file in an editor and tweaking bytes is risky; it requires understanding the binary format and type encodings. To edit data, use schema-bound CSV/text or modify data inside PostgreSQL.

### 16.5. Cross-Version Compatibility

Do not rely on binary COPY for long-term exchange across different PostgreSQL major versions or architectures without testing. For durable migrations, use logical dumps, CSV with a schema contract, or a clearly versioned serialization format.

---

## 17. Choosing a Format by Use Case

| Scenario | Recommendation | Reason |
| --- | --- | --- |
| Sending order lists to partners | UTF-8 CSV + schema contract | Easy interchange |
| Ingesting supplier CSVs | CSV into TEXT staging | Allows validation and normalization |
| Exporting for Excel | UTF-8 CSV, check BOM/locale/formula injection | Common, but carries interpretation risks |
| Simple internal PostgreSQL pipeline | Text or CSV | Easy to debug |
| COPY via PostgreSQL driver with fixed schema | Benchmark text/CSV/binary | Workload-dependent |
| Full database backup | `pg_dump`/`pg_restore` or physical backup | Preserves schema and metadata |
| HA replication | Streaming/WAL replication | Not CSV import |
| CDC to Kafka/warehouse | Logical decoding/dedicated connector | Dedicated data/event contracts |
| Hundreds of millions of rows needing checks | Streaming CSV + staging/chunking | Balances throughput and observability |
| Heavily nested JSON or binary blobs | Consider JSON/Parquet/Avro at interchange layer | COPY CSV is not optimal for all structures |

**Choose based on consumer and contract first; benchmark throughput second.**

---

## 18. What Is Encoding?

A **character encoding** maps characters to bytes.

The same Vietnamese name can be represented by different byte sequences depending on encoding. If a decoder uses the wrong encoding, data can:

- Fail with an invalid byte sequence error.
- Have characters replaced with question marks or replacement characters.
- Turn into "mojibake": valid text characters that look like gibberish.
- Suffer irreversible information loss once stored incorrectly.

### 18.1. Unicode and UTF-8

Unicode defines characters and code points. UTF-8 is a way to encode Unicode into bytes, standard on the web, modern systems, and PostgreSQL databases.

### 18.2. UTF-16 Is Not UTF-8

A file can contain Unicode while being encoded in UTF-16 little-endian or big-endian. Passing such a file straight into COPY with encoding UTF8 causes the parser to hit unexpected NUL bytes or invalid byte sequences.

### 18.3. Legacy Encodings

Older sources may use LATIN1, WIN1252, or another encoding. Always verify the exact source encoding rather than guessing just because the file was created on Windows.

### 18.4. UTF-8 Is the Default Recommendation for New Systems

For Vietnamese content, Unicode UTF-8 preserves diacritics and reduces dependency on machine-specific code pages.

### 18.5. Encoding Does Not Determine the Delimiter

A UTF-8 CSV can still use commas, semicolons, or tabs as delimiters. Encoding defines how bytes represent characters; format defines how characters are structured into fields and rows.

---

## 19. server_encoding and client_encoding

PostgreSQL has two core concepts:

- **`server_encoding`**: the character encoding used by the database to store data.
- **`client_encoding`**: the encoding used for communication between the client and PostgreSQL in text protocol contexts.

Inspect them:

```sql
SHOW server_encoding;
SHOW client_encoding;
```

Or:

```sql
SELECT
    current_setting('server_encoding') AS server_encoding,
    current_setting('client_encoding') AS client_encoding;
```

### 19.1. The Two Values Can Differ

For example, a UTF8 database can communicate with a client using WIN1252 or LATIN1 for combinations supported by PostgreSQL when characters are convertible.

### 19.2. PostgreSQL Can Transcode Characters

On paths supporting encoding conversion, PostgreSQL converts between client encoding and server encoding. However, not every Unicode character can be represented in every legacy encoding.

### 19.3. If a Character Does Not Exist in the Target Encoding

When exporting Unicode to a restricted encoding, PostgreSQL raises an error if a character has no equivalent representation. This is preferable to silently substituting wrong characters.

### 19.4. server_encoding Should Not Be Changed Arbitrarily

Database encoding is fixed when the database is created per PostgreSQL rules. You cannot run a simple `SET` command to "switch a table's server_encoding" while it holds data.

### 19.5. client_encoding Affects How Bytes Are Interpreted

If a file is UTF-8 but COPY reads it under a different client encoding without an explicit setting, some bytes may be decoded incorrectly. Always verify both file bytes and connection configuration.

---

## 20. The COPY ENCODING Option

COPY provides an option to declare the encoding of text/CSV data:

```sql
COPY app.some_table
FROM '/server/path/data.csv'
WITH (
    FORMAT csv,
    HEADER true,
    ENCODING 'UTF8'
);
```

This option clarifies the source data encoding in contexts supported by PostgreSQL.

### 20.1. When ENCODING Is Omitted

COPY uses default encoding rules tied to `client_encoding` in the respective copy paths, even when the file is read directly by the PostgreSQL server.

### 20.2. ENCODING Does Not Change Format

`ENCODING 'UTF8'` will not magically convert a UTF-16 file into UTF-8, nor will it fix broken CSV quoting. It specifies how bytes are decoded or encoded on the stream.

### 20.3. Explicit Choice Aids Reproducibility

In production batches, explicitly specifying:

```sql
WITH (
    FORMAT csv,
    HEADER true,
    ENCODING 'UTF8'
)
```

helps avoid unintended setting dependencies when supported by your PostgreSQL version. However, with `psql \copy`, you must also consider how psql reads bytes, client/session encoding, and the transport stream.

### 20.4. Binary Format Is Not "CSV with a Different Encoding"

In binary COPY, payloads are PostgreSQL binary type representations, not character streams in UTF-8 or LATIN1 like text/CSV. Do not rely on `ENCODING` to transcode binary typed data.

---

## 21. psql \encoding and SET client_encoding

In `psql`, you can view or change client encoding via:

```text
\encoding
\encoding UTF8
```

In a SQL session:

```sql
SET client_encoding TO 'UTF8';
SHOW client_encoding;
```

### 21.1. Practice with UTF-8 CSV Sources

When a file is verified as UTF-8 and the client/driver uses the same encoding, the COPY stream becomes predictable.

### 21.2. Never SET by Guessing

A CP1252 file does not become UTF-8 simply because you run `SET client_encoding='UTF8'`. You are instructing the decoder to read those bytes as UTF-8, which causes errors or corrupted data.

### 21.3. Filenames Do Not Determine Encoding

A filename like `orders-utf8.csv` is just a label. Confirm encoding from the producing system, trusted metadata, or proper inspection; the `.csv` extension says nothing about encoding.

### 21.4. Terminal Fonts Are Not Database Encoding

If characters render poorly in a terminal while the bytes, file, and database are correct, the issue may be font or terminal locale rather than PostgreSQL data corruption. Always distinguish display issues from stored-data corruption.

### 21.5. Never Enable client_encoding SQL_ASCII as a Workaround

`SQL_ASCII` has special byte-validation and conversion semantics. Using it to "let through" unknown encodings hides mismatches and complicates Unicode processing later. Always prefer UTF8 for new systems.

---

## 22. BOM: Byte Order Mark and UTF-8 CSV

A **BOM** is a special byte sequence sometimes written at the beginning of a file.

Some encodings and file standards use a BOM to indicate endianness or encoding; for UTF-8, a BOM is unnecessary, yet some tools still prepend one.

### 22.1. Why Does a BOM Cause Problems?

Suppose the expected file header is:

```text
external_id,buyer,status
```

If the file starts with a BOM, a parser or raw text reader may see an extra special character prepended to `external_id`.

### 22.2. With HEADER true

If the importer simply discards the header line, a BOM on that discarded line may have less impact; however, never rely on this coincidence—especially for headerless files or when `HEADER MATCH` is used.

### 22.3. With HEADER MATCH

An unhandled BOM can make the first column name differ from the expected string, causing an error.

### 22.4. UTF-8 With or Without BOM?

- For machine-to-machine pipelines: typically choose **UTF-8 without BOM**.
- For specific spreadsheet consumers: a BOM or specific import workflow may be needed for the software to detect UTF-8 properly.

There is no single answer when consumers have differing requirements.

### 22.5. Never Blindly Strip the First Three Bytes

Only remove a BOM after confirming those bytes actually are the expected BOM. Deleting the first three bytes of a non-BOM file corrupts the start of the data.

---

## 23. Vietnamese Unicode: Diacritics, Normalization, and Mojibake

Vietnamese data uses diacritics and many non-ASCII characters.

Examples:

```text
Nguyễn
Đặng
Thảo
Hòa
Thành phố Hồ Chí Minh
```

### 23.1. UTF-8 Stores Vietnamese Cleanly

A UTF8 database stores these strings cleanly when the client sends valid bytes and conversions are aligned.

### 23.2. Unicode Normalization

A visible character can be represented as a precomposed code point or as a base character plus combining marks. Two visually identical strings do not necessarily share the same byte sequence.

### 23.3. PostgreSQL Does Not Automatically Normalize All Input

If a pipeline requires canonical Unicode normalization for name matching or search, enforce an explicit policy and tooling rather than assuming CSV COPY handles it automatically.

### 23.4. Mojibake

When a UTF-8 string is decoded under a different encoding, it produces gibberish. Once that mangled text is stored in the database as valid UTF-8, changing `client_encoding` afterward **cannot recover** the original text.

### 23.5. Remediation Approach

- Locate the original source bytes.
- Identify the true source encoding.
- Back up the data before repairing.
- Perform a verified conversion.
- Compare round-trip results on Vietnamese fields and special characters.
- Avoid repeatedly re-encoding/decoding without knowing the current state.

---

## 24. File Charset and TEXT/VARCHAR Types

A common misconception is that a `VARCHAR(255)` column requires a different file encoding than a `TEXT` column. In PostgreSQL, both TEXT and VARCHAR store values in the database encoding; there is no per-column text encoding property.

### 24.1. VARCHAR(n) Limits Logical Length

The `VARCHAR(n)` limit counts characters per PostgreSQL rules, not simply UTF-8 byte length.

### 24.2. One Character Can Span Multiple Bytes

In UTF-8, many Vietnamese characters take more than one byte. Thus, file byte size cannot be estimated as character count times one across all languages.

### 24.3. CHAR(n) Adds Padding Semantics

When importing from CSV, `CHAR(n)` applies blank-padding and comparison semantics. Never choose `CHAR(n)` merely to "match column width in a file".

### 24.4. Do Not Use BYTEA for Text Just to Avoid Encoding

`BYTEA` is meant for raw binary data (images, binary files, raw bytes); if the content is names or addresses that require text search and sorting, fix the encoding rather than storing everything as BYTEA.

---

## 25. Lab: Creating a Practice Schema

Let's build a pipeline that ingests supplier order files.

**Concept:**

```text
supplier-orders.csv (UTF-8)
            |
            | psql \copy / COPY FROM STDIN
            v
copyfmt_lab.stage_orders (all TEXT columns)
            |
            | validation / cast / business mapping
            v
copyfmt_lab.orders (strong types and constraints)
            |
            | COPY SELECT TO STDOUT
            v
orders-export.csv / text / binary
```

> **Warning:** `DROP SCHEMA ... CASCADE` deletes all objects in the lab schema. Run this only on a test database cleared for resets. Never use this schema name if it holds real data.

```sql
DROP SCHEMA IF EXISTS copyfmt_lab CASCADE;
CREATE SCHEMA copyfmt_lab;
```

### 25.1. Creating the Staging Table

```sql
CREATE TABLE copyfmt_lab.stage_orders (
    external_id TEXT,
    buyer TEXT,
    status TEXT,
    amount_text TEXT,
    order_time_text TEXT,
    note TEXT
);
```

We intentionally choose TEXT for every column to preserve raw input and capture formatting errors cleanly.

### 25.2. Creating the Typed Target Table

```sql
CREATE TABLE copyfmt_lab.orders (
    order_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    external_id TEXT NOT NULL UNIQUE,
    buyer TEXT NOT NULL CHECK (BTRIM(buyer) <> ''),
    status TEXT NOT NULL
        CHECK (status IN ('PENDING','PAID','CANCELED')),
    amount NUMERIC(12,2) NOT NULL CHECK (amount >= 0),
    ordered_at TIMESTAMPTZ NOT NULL,
    note TEXT,
    imported_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);
```

### 25.3. What Constraints Does the Target Have?

- UNIQUE `external_id`: prevents duplicate external orders per contract.
- `buyer` non-empty after trimming.
- `status` within an allowed set.
- `amount >= 0` stored as `NUMERIC(12,2)`.
- `ordered_at` as `TIMESTAMPTZ`.
- `note` permits NULL or empty string.

### 25.4. Staging Is Not Trusted by Default

A row residing in staging is not guaranteed to be business-valid. Never let APIs query staging directly as the authoritative orders table.

---

## 26. Lab: CSV File with Vietnamese Diacritics, Quotes, and Newlines

Create a UTF-8 file named `supplier-orders.csv` with the contents:

```csv
external_id,buyer,status,amount_text,order_time_text,note
E-1001,"Nguyễn An",PAID,125000.50,2026-11-01T08:30:00+07:00,"Mua bộ ""combo"", giao nhanh"
E-1002,"Lê Bình",PENDING,0,2026-11-01T09:05:00+07:00,"Địa chỉ: Quận 1, TP.HCM"
E-1003,"Trần Cẩm",PAID,89000,2026-11-02T12:00:00+07:00,"First line
Second line"
E-1004,"Phạm Duy",CANCELED,50000,2026-11-03T10:00:00+07:00,""
E-1005,"Hà My",PAID,30000,2026-11-04T16:30:00+07:00,\N
```

**Conventions of this file:**

- `FORMAT csv`.
- Comma delimiter.
- Double-quote quote/escape.
- Header on the first line.
- UTF-8 encoding.
- NULL marker is **unquoted** `\N`.
- `""` is an empty string.
- Timestamps carry timezone offsets.
- NUMERIC uses a decimal point.

### 26.1. Why Are There Five Records Across More Than Six Physical Lines?

Record E-1003 has a `note` field containing a newline inside quotes. A proper CSV parser reads the entire field before ending the record.

### 26.2. Why Do E-1004 and E-1005 Differ?

- E-1004 `note` = empty string.
- E-1005 `note` = NULL.

### 26.3. Why Is amount_text TEXT?

So every initial row is preserved exactly as in the file and can be validated before casting to NUMERIC. For volatile input files, this decouples ingestion from validation.

### 26.4. Warning When Copying Examples into an Editor

Markdown displays `\N` as a backslash followed by N. Make sure your editor does not silently alter escapes, quotes, or encoding when creating the real file.

---

## 27. Lab: Loading CSV with psql \copy

After creating the local file on the machine running `psql`, run:

```text
\encoding UTF8
\copy copyfmt_lab.stage_orders (external_id, buyer, status, amount_text, order_time_text, note) FROM './supplier-orders.csv' WITH (FORMAT csv, HEADER true, NULL '\N')
```

### 27.1. Where Does This Command Run?

This is a `psql` meta-command. If you use a GUI database tool that does not support `\copy`, use the GUI's import feature or the COPY protocol directly.

### 27.2. Checking the Results

```sql
SELECT
    external_id,
    buyer,
    status,
    amount_text,
    order_time_text,
    note,
    note IS NULL AS note_is_null,
    LENGTH(note) AS note_length
FROM copyfmt_lab.stage_orders
ORDER BY external_id;
```

Expected results:

- 5 logical rows.
- E-1003 contains a newline in `note`.
- E-1004 has `note_length = 0`.
- E-1005 has `note_is_null = true`.

### 27.3. Failing to Load the File?

Distinguish:

- "No such file": psql cannot find the local file at that path.
- "Permission denied": OS/DB permissions.
- "invalid byte sequence": file encoding mismatch.
- "extra data after last expected column": wrong CSV delimiter, quote, or header.
- "missing data for column": record is missing fields.

### 27.4. Do Not Fix Data by Blindly Changing Encoding

If you hit a UTF-8 error, verify the file's actual encoding before changing settings or transcoding. A quoting error cannot be fixed with `ENCODING`.

---

## 28. Lab: Entering CSV Manually via COPY FROM STDIN

Without creating a file, an interactive `psql` session can supply data manually:

```text
COPY copyfmt_lab.stage_orders (external_id, buyer, status, amount_text, order_time_text, note)
FROM STDIN WITH (FORMAT csv, HEADER true, NULL '\N');
external_id,buyer,status,amount_text,order_time_text,note
E-2001,"Ngô Thu",PAID,75000,2026-11-05T09:00:00+07:00,"Test STDIN"
\.
```

Here `\.` terminates STDIN data in psql context.

### 28.1. Different from a Plain SQL Statement

Sending `COPY ... FROM STDIN` through a normal JDBC `PreparedStatement` without supplying the COPY data stream via the driver API will not automatically provide data for PostgreSQL to read.

### 28.2. For Large Files

Use `\copy FROM 'file'` or COPY protocol streaming; never paste millions of rows into a console.

### 28.3. Resetting the Lab

If you ran both the file example and STDIN, staging will also contain E-2001. When checking sample counts, keep the original five rows distinct from the extra test row.

---

## 29. Lab: Validating Raw Data Before Casting

You can check:

```sql
SELECT
    COUNT(*) AS rows_in_staging,
    COUNT(*) FILTER (WHERE external_id IS NULL) AS missing_id,
    COUNT(*) FILTER (WHERE buyer IS NULL OR BTRIM(buyer) = '')
        AS invalid_buyer,
    COUNT(*) FILTER (
        WHERE status NOT IN ('PENDING','PAID','CANCELED')
           OR status IS NULL
    ) AS invalid_status,
    COUNT(*) FILTER (WHERE note IS NULL) AS null_notes,
    COUNT(*) FILTER (WHERE note = '') AS empty_notes
FROM copyfmt_lab.stage_orders;
```

### 29.1. Why Check Row Counts First?

Counting logical rows helps detect missing or extra records. Compare against a reliable manifest or source report rather than relying solely on visual inspection.

### 29.2. Do Not Use DISTINCT to Hide Duplicates

If `external_id` duplicates exist, `SELECT DISTINCT` can silently discard rows with differing contents. Enforce an explicit deduplication/idempotency policy.

### 29.3. Validate Required Fields

If `external_id` or `buyer` is missing, depending on the business contract you may reject the row, enrich from another source, or reject the entire batch—never invent placeholder values.

### 29.4. Checking Number Locale

For files standardized on a decimal point, `amount_text` can be pre-checked with a regular expression:

```sql
SELECT external_id, amount_text
FROM copyfmt_lab.stage_orders
WHERE amount_text IS NULL
   OR amount_text !~ '^[0-9]+([.][0-9]{1,2})?$';
```

This regex is only **a syntactic check for this example's contract**; it does not replace type casting, precision/scale checks, or fit every currency format.

### 29.5. Timestamps and Unicode Need Separate Checks

A parseable timestamp is not necessarily in the expected business timezone. A readable Vietnamese string is not necessarily Unicode-normalized per contract.

---

## 30. Lab: Promoting Staging to the Typed Table

After verifying raw data against the contract, promote to the target table:

```sql
BEGIN;

INSERT INTO copyfmt_lab.orders (
    external_id,
    buyer,
    status,
    amount,
    ordered_at,
    note
)
SELECT
    external_id,
    buyer,
    status,
    amount_text::NUMERIC(12,2),
    order_time_text::TIMESTAMPTZ,
    note
FROM copyfmt_lab.stage_orders
WHERE external_id LIKE 'E-100%'
ON CONFLICT (external_id) DO NOTHING;

SELECT
    external_id,
    buyer,
    amount,
    ordered_at,
    note,
    note IS NULL AS note_is_null
FROM copyfmt_lab.orders
ORDER BY external_id;

ROLLBACK;
```

### 30.1. Why BEGIN/ROLLBACK?

The example lets you inspect the result inside a transaction without persisting test data. For real production batch imports, `COMMIT` under controlled procedures and log audit metadata.

### 30.2. Casting Can Fail

If `amount_text` contains `12,50` or `order_time_text` has an invalid date string, the `INSERT` statement fails. That is why staging and validation are separated.

### 30.3. What Does ON CONFLICT DO NOTHING Mean?

With unique `external_id`, this skips already-existing rows. However, if the source supplies duplicate IDs with differing amounts, silently skipping can hide discrepancies that require reconciliation.

### 30.4. Production Strategy

- Load into staging tagged by `batch_id`/`source_file`.
- Validate and record rejected rows with error codes.
- Deduplicate by explicit business keys.
- Transform inside a transaction.
- Verify accepted/rejected counts.
- `COMMIT` only when quality thresholds are met.
- Store manifest, checksum, and source timestamps.
- Report import success only after `COMMIT`.

### 30.5. Do Not Confuse Raw Staging with the Source of Truth

Staging should have retention and PII protection policies, rather than becoming a widely exposed table just because "it's only an import file".

---

## 31. Lab: Exporting CSV Matching the Schema Contract

Once the target table holds committed data, you can export:

```text
\copy (SELECT external_id, buyer, status, amount, ordered_at, note FROM copyfmt_lab.orders ORDER BY external_id) TO './orders-export.csv' WITH (FORMAT csv, HEADER true, NULL '\N')
```

### 31.1. Intentional Column Ordering

Do not use `SELECT *` in long-lived exchange contracts. Adding a new column to the table changes output if you rely on `SELECT *`.

### 31.2. Is ORDER BY Needed?

COPY queries do not guarantee deterministic output order unless `SELECT` includes `ORDER BY`. For reconciliation snapshots needing stable order, `ORDER BY` on an explicit key makes diffs straightforward.

### 31.3. Encoding

Verify UTF-8 via `\encoding UTF8`/session settings and file-generation procedures. If using SQL COPY and your version supports it, specify `ENCODING 'UTF8'`.

### 31.4. NULL Marker

Use `NULL '\N'` consistently with the example importer instead of relying on default CSV empty markers.

### 31.5. Sensitive Data

Do not export unit costs, PII, or internal fields merely because the source table contains those columns. Select only required columns and use an appropriate read role.

---

## 32. Lab: Exporting Text and Binary for Comparison

### 32.1. Exporting Text

```text
\copy (SELECT external_id, buyer, amount FROM copyfmt_lab.orders ORDER BY external_id) TO './orders-export.txt' WITH (FORMAT text)
```

### 32.2. Exporting Binary

```text
\copy (SELECT external_id, buyer, amount FROM copyfmt_lab.orders ORDER BY external_id) TO './orders-export.copybin' WITH (FORMAT binary)
```

### 32.3. Comparing the Files

- Text files are editor-readable, provided you understand tab and backslash escapes.
- Binary files should not be read as text.
- CSV files include headers and quoting, convenient for external consumers.
- Check byte sizes, but do not assume a smaller file automatically loads or queries faster.

### 32.4. Conditional Binary Re-Import

A binary COPY file can only be reloaded into an object with matching column list and types per supported binary format rules:

```text
\copy copyfmt_lab.binary_target (external_id, buyer, amount) FROM './orders-export.copybin' WITH (FORMAT binary)
```

The `binary_target` table here is a **placeholder**: you must create a table with compatible types and column order before running it. Do not mistakenly load into `stage_orders` (all TEXT columns) if the binary source contains NUMERIC.

### 32.5. Do Not Benchmark on Empty Files

To measure `FORMAT text/csv/binary`, ensure the target has real data and run tests under consistent conditions. If you did not `COMMIT` the previous lab, `orders` may be empty.

---

## 33. A Round-Trip Verification Test

Suppose initial data includes these cases:

```text
NULL
empty string
text with comma
text with "double quote"
text with tab
text with newline
text with backslash
Vietnamese characters
emoji
UTC timestamp
NUMERIC decimal
```

A proper test must:

1. Create known source data in PostgreSQL or a verified source file.
2. Export using the specified format and encoding.
3. Import into a fresh table with matching schema.
4. Compare in SQL using exact semantics.
5. Ensure NULL stays NULL and empty stays empty.
6. Verify string lengths, characters, and diacritics.
7. Verify timestamps represent the same instant, not just the same display string.
8. Verify numeric values lose no precision.
9. Verify record counts.
10. Verify file checksums if the goal is byte-identical transfer.

### 33.1. NULL/Empty Verification

```sql
SELECT
    COUNT(*) FILTER (WHERE note IS NULL) AS null_count,
    COUNT(*) FILTER (WHERE note = '') AS empty_count
FROM copyfmt_lab.orders;
```

### 33.2. Checksums Do Not Replace Semantic Equality

Two files with different checksums can represent identical data with different newlines, quoting, or ordering. Conversely, matching checksums only prove identical bytes, not correct mapping into table types.

### 33.3. Table Comparison

Given identical schemas and unique keys, use a `FULL OUTER JOIN` on the business key to catch missing or mismatched rows. Be careful when comparing NULLs:

```sql
a.note IS DISTINCT FROM b.note
```

provides clear NULL-safe comparison semantics.

---

## 34. COPY and Access Control

### 34.1. COPY FROM Table

The role needs appropriate `INSERT` privileges on the target table/columns along with schema access per PostgreSQL rules.

### 34.2. COPY TO Table/Query

The role needs corresponding `SELECT` privileges, just like any standard read query.

### 34.3. Server-Side File COPY

Reading/writing server files requires specialized database privileges and OS permissions; this is a sensitive trust boundary. Never grant file-level roles simply because a worker needs to import data.

### 34.4. Client-Side \copy

`psql \copy` avoids needing server filesystem read/write privileges, though the SQL role still needs appropriate `SELECT`/`INSERT` on tables.

### 34.5. COPY TO Can Exfiltrate Large Amounts of Data

A role with `SELECT` on a sensitive table can export the entire table via `COPY TO STDOUT`. COPY itself is not a vulnerability—it reflects overly broad `SELECT` grants. Enforce least privilege and data egress controls.

### 34.6. Client Filesystem Permissions

Even when the server only streams results, the exported file sits on the psql or application machine. Who is allowed to read that file? Does it need encryption, retention limits, auditing, or deletion after processing? Database grants do not control external copies.

---

## 35. COPY and Row-Level Security (RLS)

RLS has special interactions with bulk operations.

### 35.1. COPY FROM on Tables with RLS

PostgreSQL documents that `COPY FROM` **does not support loading directly into tables with RLS enabled** in the applicable contexts; to insert data while enforcing policies, use `INSERT` statements or a controlled staging/privileged import architecture.

Do not assume a `COPY FROM` executed by an RLS-restricted role will automatically check policies the way standard `INSERT` does.

### 35.2. COPY TO and RLS

When `COPY TO` reads data through supported SQL mechanisms, RLS policies can restrict exported rows based on role and object privileges. However, table owners, superusers, and roles with `BYPASSRLS` follow special rules.

### 35.3. Why Staging Helps

An import service can load into staging inside a dedicated schema, validate, and move data into tenant tables via controlled DML. Clearly define which role transfers data and at which step constraints and policies are enforced.

### 35.4. Never Use an Owner Account to Bypass RLS Without Scoping

If an importer runs as an owner bypassing RLS, it could insert data across tenant boundaries. While sometimes needed in specialized ETL, this must follow strict operational controls rather than being an API default.

### 35.5. Test with Real Roles

Never test COPY solely as superuser and assume application roles share the same permissions.

---

## 36. COPY and Constraints, Triggers, and Indexes

### 36.1. Constraints Still Apply

When `COPY FROM` loads a typed table, PostgreSQL checks constraints such as NOT NULL, CHECK, UNIQUE/PK, and FK according to standard rules.

### 36.2. Triggers

`COPY FROM` can fire triggers on the target table per PostgreSQL rules. This may cause side effects or slow bulk loads. Never rely on the myth that "COPY skips all triggers".

### 36.3. Index Maintenance

COPY into indexed tables must maintain all indexes. Many large indexes reduce ingest throughput. In controlled rebuild/reload workflows, operators may load data first and build indexes afterward, weighing downtime, constraints, availability, and integrity.

### 36.4. GENERATED and Identity Columns

PostgreSQL enforces specific rules for generated and identity columns during `COPY FROM`. For instance, `COPY FROM` can accept explicit identity values from input rather than always auto-generating defaults when supported. Define column lists and contracts explicitly rather than loading identity values haphazardly in production.

### 36.5. Triggers/Constraints Do Not Replace Source Validation

A date string that parses validly yet has the wrong business date, or an amount valid as NUMERIC yet in the wrong currency, passes basic database constraints. Business validation belongs in staging.

---

## 37. Transaction Semantics When COPY FROM Fails

A `COPY FROM` is a SQL statement inside a transaction. If COPY fails due to bad data or constraint violations, the statement cannot commit successfully.

### 37.1. Failure Example

```csv
external_id,buyer,status,amount,ordered_at
E-01,An,PAID,100,2026-11-01T08:00:00+07:00
E-02,Bình,PAID,not-a-number,2026-11-01T08:10:00+07:00
```

When loaded directly into a NUMERIC column, record E-02 triggers a type conversion error.

### 37.2. No "Half-Committed" State for an Aborted Statement

Changes from an aborted COPY statement are never partially committed. However, tuples physically written before the error leave dead space that requires `VACUUM`/maintenance to reclaim; they are not visible valid rows.

### 37.3. Huge Transactions Impact WAL and Storage

A massive import can generate heavy WAL, bloat, and locks, pressuring I/O, replication lag, and disk capacity. Design batch/transaction scopes and monitor them.

### 37.4. Multiple COPY Statements in One Transaction

If a batch splits into several COPY statements within one transaction, the whole transaction still depends on the final `COMMIT`. If each chunk commits independently, earlier committed chunks will not automatically roll back when a later chunk fails.

### 37.5. Choosing All-or-Nothing vs. Partial Acceptance

- **All-or-nothing:** appropriate when batches must be strictly atomic.
- **Partial acceptance:** requires rejected-rows/accepted-rows tracking tables and a clear business contract—never silently discard errors.

---

## 38. Handling Load Errors: Staging and Rejection Policies

Some newer PostgreSQL versions provide COPY options to ignore certain per-row conversion errors in supported formats. However, exact support and ignored error classes depend on the version and options. Never treat this as a blanket "ignore all constraint errors" switch.

### 38.1. Stable Pattern

1. Load raw bytes/text into a well-defined staging schema.
2. Verify row counts and file manifest.
3. Validate columns and business keys.
4. Promote accepted sets into typed tables.
5. Record rejected rows and reasons.
6. Decide commit/rollback per SLA.
7. Emit accepted/rejected metrics.
8. Manage retries and idempotency.

### 38.2. When Using ON_ERROR on Supported Versions

Options like `ON_ERROR ignore` exist in newer PostgreSQL releases for supported formats. Always verify version documentation before relying on them to know which errors are ignored and which still abort the statement.

### 38.3. Do Not Lose Failed Records

If business operations require full traceability, skipped records must leave an audit trail. Never settle for "COPY finished" while ignoring how many rows actually loaded.

### 38.4. Structured Error Logging

Record `source_file`, `batch_id`, `row_number`/logical record identifier, column, `error_code`, and a redacted sample. Never log raw tokens, PII, or secrets unnecessarily.

### 38.5. Do Not Build Contracts on Unstable Error Message Text

When catching driver errors, rely on SQLSTATE and structured error fields for classification rather than brittle message substrings that vary by version and locale.

---

## 39. Performance: Is Text, CSV, or Binary Faster?

There is no universal ranking across all workloads.

### 39.1. Text Overhead

- Formatting/parsing values as characters.
- Escaping delimiters and backslashes.
- Character encoding conversion where needed.

### 39.2. CSV Overhead

- Quoting and escaping fields.
- Scanning delimiters and handling multiline fields.
- Type conversion after parsing.

### 39.3. Binary Overhead

- Serializing/deserializing via binary type routines.
- No quote/delimiter character overhead in the file format.
- Narrower tool compatibility and stricter schema requirements.

### 39.4. Bottlenecks Beyond Format

- Network latency and bandwidth.
- WAL generation.
- Index maintenance.
- Foreign key and trigger checks.
- Disk throughput.
- Autovacuum and dirty buffers.
- Replication lag.
- Transaction duration.
- CPU type conversion.
- Client buffering and streaming.

### 39.5. File Size Does Not Equal Load Time

Binary may be smaller or larger than CSV depending on types and values. A smaller file will not necessarily load faster if indexes dominate or the network is not the bottleneck.

### 39.6. Benchmarking Properly

- Identical data and schema.
- Identical indexes and constraints.
- Identical transaction strategy.
- Identical server, client, and network.
- Multiple runs.
- Include warm-up and separate warm vs. cold cache results.
- Measure rows/s, MB/s, CPU, WAL bytes, latency, and replication lag.
- Verify round-trip correctness before comparing speed.

---

## 40. Optimizing Large Imports Safely

### 40.1. Use COPY Instead of Millions of Small INSERTs

In most bulk ingest scenarios, COPY drastically cuts overhead compared to sending each row as a separate network INSERT.

### 40.2. Load Only Required Columns

```sql
COPY app.orders (external_id, buyer, amount)
FROM STDIN
WITH (FORMAT csv);
```

Columns omitted from the COPY list receive defaults or NULL per schema and constraints.

### 40.3. Stage to Separate Raw and Typed Layers

When source data frequently contains errors, staging avoids loading directly into critical business tables and enables pre-validation.

### 40.4. Chunk Based on Operational Targets

Too many rows in a single transaction increase lock/resource hold times and make late rollbacks costly. Chunking improves observability and retryability, at the cost of handling partial commits and idempotency.

### 40.5. Manage Indexes Deliberately

Indexes speed up queries but add write amplification. For massive initial loads on fresh tables, consider building non-unique indexes after bulk loading. On live production tables, never drop indexes or constraints arbitrarily just for speed.

### 40.6. ANALYZE After Bulk Loads

After loading large volumes:

```sql
ANALYZE copyfmt_lab.orders;
```

gives the planner updated statistics. Autovacuum/autoanalyze handles this in many systems, though major batch jobs often coordinate timing with query workloads.

---

## 41. WAL, Replication, and Imports

`COPY FROM` is a PostgreSQL write operation, so it generates WAL according to table/cluster durability settings and affects replication.

### 41.1. Do Not Think COPY "Bypasses WAL"

Loading into regular logged tables goes through PostgreSQL's WAL mechanism. Special optimizations depend on specific modes or table types with strict preconditions—they do not skip WAL by default.

### 41.2. Replication Lag

Bulk loads can lag standbys and logical consumers when write volume spikes or replay slows down. Monitor WAL and replication metrics before, during, and after batches.

### 41.3. UNLOGGED Tables

An `UNLOGGED` staging table can reduce WAL in certain cases, but comes with crash-recovery and physical replication limitations. Never make durable business data `UNLOGGED` just for faster imports.

### 41.4. COPY FREEZE

PostgreSQL offers a `FREEZE` option under strict conditions, such as tables created or truncated in the current transaction alongside snapshot rules, with several limitations. It is a specialized optimization—**never** enable it indiscriminately in production or treat it as a way to "skip VACUUM forever".

### 41.5. Durability Is a Business Decision

Never set `synchronous_commit = off`, switch to UNLOGGED, or alter fsync solely for a benchmark without understanding crash data-loss risks and recovery SLAs.

---

## 42. CSV Injection When Files Open in Spreadsheets

This is a major information security risk when exporting CSVs.

A user-controlled text field may begin with:

```text
=SUM(1,2)
+1+2
-1+2
@some_expression
```

Some spreadsheet applications interpret such strings as formulas rather than plain text, depending on version, configuration, and opening method.

### 42.1. COPY Only Serializes Data

PostgreSQL CSV COPY guarantees quoting per the CSV dialect—it **does not guarantee spreadsheets will treat every cell as harmless text**.

### 42.2. CSV Quoting Alone Does Not Prevent Formula Execution

Wrapping a field in CSV double quotes does not stop spreadsheet software from evaluating its contents as a formula.

### 42.3. Safe Export Policies

If end users open files in spreadsheets, design a safe output format or sanitization layer:

- Choose formats that explicitly type cells as text where possible.
- Neutralize untrusted leading characters per consumer security requirements.
- Test against real spreadsheet software with adversarial inputs.
- Document how escaping or prefixing alters values.
- Never silently alter values if the file is intended for machine-to-machine round-trips.

### 42.4. Separate the Two Export Contracts

A CSV intended for **machine ingestion** must preserve exact bytes and values. A file intended for **human spreadsheet viewing** may require a dedicated transformation layer to disarm formulas.

---

## 43. Formatting Numbers, Money, and Timestamps in Exports

### 43.1. Decimals

For monetary values:

```text
125000.50
```

is clean text input for PostgreSQL `NUMERIC`. Do not insert locale-specific thousands separators unless the importer contract expects them.

### 43.2. Never Use FLOAT for Money Just to Shrink Files

If a system uses `NUMERIC(12,2)` for exact currency precision per policy, exports and imports should never route values through uncontrolled floating point.

### 43.3. Timestamps with Timezones

For example:

```text
2026-11-01T08:30:00+07:00
```

specifies an unambiguous instant compared to an offset-less string. For `TIMESTAMPTZ`, PostgreSQL stores the instant per type semantics, while export formatting still reflects session timezone settings.

### 43.4. DateStyle

When using non-ISO date strings, `DateStyle` affects parsing and display. For portable exports, always choose explicit ISO formats.

### 43.5. Boolean Values

PostgreSQL accepts several boolean input spellings, yet export contracts should standardize on `true`/`false` rather than leaving consumers to guess `Y/N` or `1/0` without agreement.

### 43.6. Spreadsheet Locale Issues

If a spreadsheet opens a comma-delimited CSV while configured for a locale that uses commas as decimal points, number parsing can behave unexpectedly. Always provide consumer import instructions and never treat CSV as self-describing.

---

## 44. Encoding and Conversion When Legacy Sources Use Old Charsets

Suppose a supplier sends a file encoded in WIN1252.

### 44.1. Verify the Source

Obtain metadata or confirmation from the supplier. Never guess WIN1252 just because the file has a `.csv` extension.

### 44.2. Transcode Before Loading

Use an appropriate conversion tool to convert the file to UTF-8, then verify with non-ASCII sample values. In Java applications, configure an explicit source charset decoder and UTF-8 encoder in a controlled streaming pipeline.

### 44.3. Never Change Bytes While Keeping the Old Label

A file converted to UTF-8 while still labeled WIN1252 by the producer will break downstream consumers. Metadata must match the actual bytes.

### 44.4. Transcoding Does Not Fix Data Logic

Turning `1,25` into `1.25` is **data normalization**, not encoding conversion. Likewise, converting local timestamps to UTC is not encoding conversion.

### 44.5. Handling Legacy Vietnamese Encodings

Some older systems used legacy code pages or custom Vietnamese encodings without trivial 1-to-1 standard charset mappings. Require source documentation and verified mapping tables rather than ad-hoc conversions.

### 44.6. Test with Canary Strings

A test file should include:

```text
Đặng Thị Hạnh
Nguyễn Ánh
Trần Quốc Bảo
Tôi đến Thành phố Hồ Chí Minh.
```

to compare before and after conversion instead of testing only ASCII strings that look identical across many encodings.

---

## 45. Java/JDBC: Streaming COPY Instead of Sending \copy

In Java, `\copy` is not valid SQL for a `PreparedStatement`. The PostgreSQL JDBC driver provides a dedicated API for the COPY protocol.

Illustrative example using PostgreSQL JDBC driver classes (add the appropriate `pgjdbc` dependency):

```java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.sql.Connection;
import org.postgresql.PGConnection;
import org.postgresql.copy.CopyManager;

public class CopyImportExample {
    public static long importCsv(
            Connection connection,
            Path file
    ) throws Exception {
        CopyManager manager = connection
                .unwrap(PGConnection.class)
                .getCopyAPI();

        String sql = """
            COPY copyfmt_lab.stage_orders
                (external_id, buyer, status,
                 amount_text, order_time_text, note)
            FROM STDIN
            WITH (
                FORMAT csv,
                HEADER true,
                NULL '\\N'
            )
            """;

        try (InputStream in = Files.newInputStream(file)) {
            return manager.copyIn(sql, in);
        }
    }
}
```

### 45.1. Why Use InputStream?

The driver streams bytes over the COPY protocol instead of turning the file into millions of INSERT statements. It also avoids needing server-side file read privileges simply because the app has a local file.

### 45.2. Control Encoding Explicitly

When streaming raw bytes, ensure the file's encoding matches COPY and session expectations. Never call an `InputStream` "Unicode" without knowing its actual byte encoding.

### 45.3. When Transforming Rows in Java

Use a streaming CSV parser with an explicit charset decoder, validate rows, and emit a clean COPY data stream. Handle delimiters, quotes, newlines, and NULLs properly rather than concatenating strings blindly.

### 45.4. Never Interpolate Arbitrary Table Names

The `COPY` statement above is an application-controlled SQL template. If schema or table names are dynamic, enforce an allowlist and proper identifier quoting to prevent SQL injection.

### 45.5. Transaction Management

`copyIn` does not commit the business operation automatically. With `autoCommit=false`, the caller must commit or roll back per contract; if the file is malformed, inspect SQLSTATE, roll back, and report errors cleanly.

---

## 46. Java CSV Export via the COPY Protocol

An application can stream `COPY TO STDOUT`, for example using pgjdbc `CopyManager`:

```java
import java.io.OutputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.sql.Connection;
import org.postgresql.PGConnection;
import org.postgresql.copy.CopyManager;

public class CopyExportExample {
    public static void exportCsv(
            Connection connection,
            Path target
    ) throws Exception {
        CopyManager manager = connection
                .unwrap(PGConnection.class)
                .getCopyAPI();

        String sql = """
            COPY (
                SELECT external_id, buyer, status,
                       amount, ordered_at, note
                FROM copyfmt_lab.orders
                ORDER BY external_id
            )
            TO STDOUT
            WITH (
                FORMAT csv,
                HEADER true,
                NULL '\\N'
            )
            """;

        try (OutputStream out = Files.newOutputStream(target)) {
            manager.copyOut(sql, out);
        }
    }
}
```

### 46.1. Strengths

- Streams directly without iterating `ResultSet.getString()` per row and manually joining commas.
- PostgreSQL handles CSV dialect quoting.
- Integrates cleanly with local files or object-storage upload pipelines.

### 46.2. Securing the Output File

Local files may contain PII. Enforce appropriate filesystem permissions, storage paths, encryption, and retention. Never export into a web server's public directory just for easy downloads.

### 46.3. Query Privileges

The application still needs appropriate `SELECT` privileges. If the table uses RLS, test with the actual runtime role and permission context.

### 46.4. Mid-Stream Failures

If the connection drops mid-export, the file will be **incomplete**. Never publish a file as complete until the COPY protocol finishes, the stream flushes/closes, and any required manifest/checksum passes. When needed, write to a temporary path and atomically rename where the filesystem supports it.

---

## 47. COPY via pgAdmin, GUIs, and ETL Tools

Not every tool behaves like `psql \copy`.

### 47.1. GUI Importers May Parse CSV Themselves

A GUI tool might read the client file, parse CSV in its own layer, and send INSERTs or COPY protocol streams. This affects option compatibility, error paths, streaming, and encoding.

### 47.2. Never Rely on Unchecked GUI Defaults for Recurring Batches

If an operator picks the wrong delimiter, header setting, or encoding, data loads incorrectly. Production pipelines should use versioned configuration and reproducible automation.

### 47.3. ETL Tools May Coerce Types Before PostgreSQL

For example, an ETL parser may read leading zeros of a postal code as an integer and output it without leading zeros. This is not a COPY bug—the upstream parser changed the data.

### 47.4. Verify Results in SQL After Loading

Verify counts, business keys, NULL/empty states, amounts, and timezones. A GUI "Success" dialog is not sufficient proof.

### 47.5. Log Import Configuration

Record format, delimiter, encoding, NULL marker, source URI, file checksum, `batch_id`, versions, and row counts to debug future discrepancies.

---

## 48. CSV Exports for Excel and BI: Specific Decisions

### 48.1. Encoding

UTF-8 is a strong default, though spreadsheet users may need to select UTF-8 explicitly during import. Some versions/open flows rely on BOM, locale, or OS settings.

### 48.2. Headers

Headers help human readers, but avoid duplicate or unpredictably shifting column names.

### 48.3. Leading Zeros

Codes like `001234` can be auto-parsed by spreadsheets into `1234`, stripping leading zeros. Use explicit text formatting or import schema guidance.

### 48.4. Dates

`01/02/2026` can be parsed as February 1 or January 2 depending on locale. Use unambiguous ISO 8601 and/or explicit import type mapping.

### 48.5. Text Starting with Formula Characters

Apply consumer-aware neutralization when untrusted input is present. CSV quoting alone does not block formula execution.

### 48.6. Multiline Values

Spreadsheets can display multiline cells, whereas naive CSV consumers may split them into extra rows. Test with the real downstream consumer.

---

## 49. End-to-End Secure Ingestion Workflow

A production workflow can be structured as:

```text
Supplier
   |
   | upload file
   v
Object storage / inbound area
   |
   +-- authenticate source
   +-- checksum + file size + scan
   +-- encoding/dialect detection using trusted contract
   v
Staging loader (dedicated DB role)
   |
   | COPY CSV UTF-8 -> raw staging
   v
Validation
   |
   +-- schema/header check
   +-- raw row count
   +-- parse/constraint/business rules
   +-- dedup/idempotency
   +-- rejected data tracking
   v
Typed application tables
   |
   +-- transaction commit
   +-- audit result
   v
Downstream consumers
```

### 49.1. Who Has Load Privileges?

The loader runs under a dedicated role with `INSERT` on staging and only the privileges required to promote typed data. Never use superuser or a role with broad database read access.

### 49.2. Pre-COPY File Checks

Enforce limits on file size, column count, header, delimiter, encoding, file origin, maximum row count, and fields hazardous to downstream systems.

### 49.3. Retain Raw Data Safely with Retention Policies

If needed for audits or retries, keep source files or raw staging under clear retention windows and access controls. Never retain PII indefinitely just for convenience.

### 49.4. Rejected Rows Need a Contract

When partial imports are allowed, each rejected row must have an identifier and rejection reason. Ensure a retry does not create business duplicates from a previously partial-committed batch.

### 49.5. Record Provenance

Log:

- Source system.
- File name/path identifier (avoiding sensitive host paths where unnecessary).
- Checksum.
- Encoding/dialect version.
- Schema contract version.
- Import batch ID.
- Started/completed timestamps.
- Accepted/rejected counts.
- Status/transaction outcome.

---

## 50. Diagnosing Errors from PostgreSQL Messages

Common error groups:

| Symptom | Possible Cause | Where to Check |
| --- | --- | --- |
| `invalid byte sequence for encoding "UTF8"` | File is not UTF-8 or bytes are corrupted | Verify file bytes/encoding |
| `extra data after last expected column` | Wrong delimiter/quote, extra fields | Check CSV dialect and header |
| `missing data for column` | Missing fields in record | Check quoting/newlines/column count |
| `invalid input syntax for type numeric` | Malformed number syntax | Stage as TEXT and normalize |
| `invalid input syntax for type timestamp...` | Bad date format | ISO/timezone/DateStyle |
| `null value ... violates not-null constraint` | NULL marker or blank value | NULL vs. empty policies |
| `duplicate key value violates unique constraint` | Key already exists | Business key/dedup strategy |
| `permission denied for table` | Missing table GRANT | Role privileges |
| `permission denied for schema` | Missing USAGE | Schema privileges |
| `could not open file ...` | Server/client path or OS permissions | Distinguish COPY vs. \copy |
| Garbled Vietnamese diacritics after import | Upstream decoding error | Raw file/encoding/terminal |
| Missing rows in export | Query filter, RLS, or snapshot | Permissions and WHERE clause |
| Binary COPY fails to load | Incompatible schema/types | Check column order/types/version |

### 50.1. SQLSTATE Is Better Than Parsing Message Text

When handling errors in drivers, classify failures using SQLSTATE and structured error metadata rather than fragile message substrings.

### 50.2. One Symptom Can Have Multiple Root Causes

A broken quote can surface as an "extra columns" error. Never widen the table schema to silence the error—fix the file formatting root cause.

### 50.3. Successful Parsing Does Not Guarantee Data Quality

A CSV can pass parsing yet mix up tenant IDs, currency units, or timezones. Separate business validation is always required.

---

## 51. Scenario A: Third-Party Sends a Windows CSV

**Context:** A supplier sends `products.csv` exported from an older Excel version; it uses semicolons, Vietnamese characters, and comma decimals.

### 51.1. Do Not Import Immediately with Default CSV

The default COPY delimiter is a comma, which will misalign columns completely.

### 51.2. Verify Encoding

The file may be WIN1252 or another encoding, but never guess from the OS name alone. Confirm with the supplier or inspect sample bytes.

### 51.3. Normalize the Data

Pipeline:

- Decode using the verified source encoding.
- Parse with `;` delimiter and exact quote rules.
- Convert locale-formatted numbers to canonical numeric strings.
- Convert timestamps/timezones per policy.
- Emit standard UTF-8 CSV matching the pipeline's delimiter and NULL marker.
- Load into staging and validate.

### 51.4. Retain the Original File

If a monetary value is converted wrongly, you can reconcile against the original source bytes; never keep only the normalized file without provenance.

---

## 52. Scenario B: Notes Containing Multiple Lines and Quotes

**Context:** An order note contains:

```text
Deliver to "Ms. Ha"
Call 15 minutes ahead, ext 123.
```

A hand-rolled export concatenating:

```text
order_id + "," + note + "\n"
```

corrupts the file because the note contains commas, quotes, and newlines.

### 52.1. Use COPY CSV

`COPY (SELECT ...) TO STDOUT WITH (FORMAT csv)` handles quoting per PostgreSQL's CSV dialect.

### 52.2. Never Use String.split(",") in Consumers

Consumers must parse CSV with full quoted-field semantics.

### 52.3. Round-Trip Check

After import, compare:

```sql
source.note IS NOT DISTINCT FROM imported.note
```

to validate NULL and text values with exact semantics.

### 52.4. Spreadsheets Can Render Multiline Cells

That does not mean the file has two records; always distinguish physical lines from logical CSV records.

---

## 53. Scenario C: Binary COPY Between Two PostgreSQL Versions

**Context:** A team exports binary COPY on one cluster and plans to load it into another cluster with version, extension, or type differences.

### 53.1. Risks

- Different column order.
- Differing INTEGER/BIGINT/NUMERIC types.
- User-defined types with custom binary protocols.
- Format or type representation changes across versions.
- File lacks schema/metadata needed for self-recovery.

### 53.2. Recommended Approach

For durable migrations, prefer `pg_dump/pg_restore` or CSV/text with an explicit contract. If still using binary COPY, do so only after thorough compatibility testing on the exact target pair with a rollback plan.

### 53.3. Never Treat Binary COPY as a Backup

A binary export of a `SELECT` only captures selected rows and columns—it omits indexes, constraints, grants, functions, and metadata required to restore a database.

---

## 54. Scenario D: Unicode Looks Fine in Source, Broken After Import

**Context:** Opening the CSV in an editor shows Vietnamese names properly, yet PostgreSQL stores gibberish.

### 54.1. Investigate Layer by Layer

1. Confirm the file's actual byte encoding.
2. Confirm which charset the reader tool uses.
3. Check `client_encoding` in the session.
4. Check `server_encoding`.
5. Check the COPY `ENCODING` option if specified.
6. Check any pre-COPY conversion steps.
7. Check SQL client display, font, and terminal locale.
8. Inspect raw values and exports with a known UTF-8 tool.

### 54.2. If Bytes Were Already Corrupted Before Reaching PostgreSQL

A simple `ALTER DATABASE` or `SET client_encoding` cannot fix it. Restore from the original file or run a verified conversion.

### 54.3. Test with Unicode Samples

Include names with heavy diacritics, hook marks, `Đ/đ`, emojis, and combining marks to catch bugs rather than testing only ASCII.

---

## 55. Common Misconceptions

| Misconception | Reality |
| --- | --- |
| "CSV always means comma-delimited." | The delimiter can vary; check the contract |
| "CSV = UTF-8." | CSV is a format; encoding is an independent axis |
| "If an editor opens it fine, it's UTF-8." | Editors may auto-detect or silently re-encode |
| "UTF-16 is UTF-8 because both are Unicode." | They are different byte serializations |
| "Changing client_encoding fixes garbled text." | Not if mojibake/data loss already occurred |
| "A BOM is always required." | UTF-8 needs no BOM; consumers may request it |
| "A BOM doesn't affect headers." | It can break `HEADER MATCH` |
| "COPY is a psql command." | `COPY` is PostgreSQL SQL |
| "\copy is SQL usable in JDBC." | `\copy` is a psql meta-command |
| "COPY FROM '/path' reads my laptop file." | It uses a server-side path |
| "\copy reads files on the PostgreSQL server." | It uses the client-side process path |
| "COPY FROM STDIN reads any file automatically." | The client must stream data |
| "Server-file COPY only needs table INSERT." | It needs file-level privileges and OS access |
| "COPY PROGRAM is a handy way to open files." | Sensitive privileges, command execution risk |
| "Text COPY defaults to commas." | It defaults to tab |
| "Text COPY doesn't escape backslashes." | It has its own escape rules |
| "\N is SQL NULL syntax." | It is a file marker in text/CSV contracts |
| "CSV NULL and empty string are always identical." | Quoting/markers can distinguish them |
| "FORCE_QUOTE turns NULL into empty string." | It does not |
| "HEADER true maps columns by name." | It mainly handles the header line; column order must match |
| "HEADER MATCH reorders columns automatically." | It validates names/order against the contract |
| "Each physical line in CSV is one record." | Quoted fields can span newlines |
| "split(',') is enough to parse CSV." | Breaks on quoted commas and newlines |
| "Changing delimiter fixes 1,25 decimals." | Numeric normalization is separate |
| "CSV DATE/TIMESTAMP never depends on timezone." | Can depend on input, DateStyle, and session |
| "Binary COPY is a compressed CSV." | It is a proprietary binary format |
| "Binary is always faster than CSV." | Depends on workload |
| "Binary COPY is a PostgreSQL backup." | Lacks schemas, ACLs, and metadata |
| "Binary copy is portable across all versions/types." | Not guaranteed |
| "COPY skips constraints and triggers." | It enforces them by default |
| "COPY generates no WAL." | Generates WAL on logged tables |
| "A failed COPY can half-commit a statement." | Failed statements do not half-commit |
| "A failed COPY uses zero disk." | Dead tuples consume space until VACUUM |
| "ON_ERROR ignore skips every error." | Only supported error types per version |
| "COPY FROM enforces RLS like INSERT." | `COPY FROM` has restrictions with RLS |
| "COPY TO as owner guarantees tenant filtering." | Owners can bypass RLS |
| "Table INSERT implies sequence rights everywhere." | Sequence/default privileges need review |
| "Import succeeded means business-correct." | Still validate counts, rules, and timezones |
| "TEXT staging means all data is clean." | TEXT only defers type parse failures |
| "ON CONFLICT DO NOTHING is always safe dedup." | Can mask conflicting data updates |
| "Excel treats =... safely if CSV-quoted." | Formula injection risk still applies |
| "Export file is complete once COPY starts." | Connection can drop mid-stream |
| "Higher rows/s means a safer batch." | Also consider consistency, WAL, replication, recovery |
| "SQL_ASCII fixes encoding errors." | Masks validation and corrupts Unicode |
| "Admin accounts should run file imports." | Prefer least-privilege import roles |
| "Fastest COPY means dropping constraints." | Risks correctness and downtime |

---

## 56. Practice Exercises

### Exercise 1 — Format or Encoding?

Explain the difference between CSV and UTF-8. Can a file be CSV encoded in UTF-16?

### Exercise 2 — COPY vs. \copy

State where files are opened when running `COPY FROM '/tmp/data.csv'` vs. `\copy FROM './data.csv'`. Why might those paths refer to two different machines?

### Exercise 3 — STDIN/STDOUT

Write a COPY command exporting a table to STDOUT as CSV and one importing from STDIN. What must the client do in each case?

### Exercise 4 — Text Defaults

What default delimiter and NULL marker does text COPY use? When should you choose text over CSV?

### Exercise 5 — Text Escapes

Represent a field containing a tab, newline, and backslash in text format. Why is splitting on tabs insufficient?

### Exercise 6 — CSV Quoted Comma

Write a CSV record where `buyer` is `Hà Nội, Việt Nam` while remaining a single `buyer` field.

### Exercise 7 — CSV Quotes

Represent the note `Order "combo"` using default QUOTE/ESCAPE settings.

### Exercise 8 — Multiline Field

Create a CSV with a two-line note, import it, and verify the logical row count and note value.

### Exercise 9 — NULL vs. Empty

Write the three cases—NULL, `''`, and `'NULL'`—in default CSV, then check them in SQL with `IS NULL` and `LENGTH`.

### Exercise 10 — Custom NULL Marker

Use `NULL '\N'` to export data, re-import it, and prove empty strings are not converted to NULL.

### Exercise 11 — FORCE_QUOTE

Export a table to CSV with `FORCE_QUOTE *`. Do NULL values turn into empty strings?

### Exercise 12 — FORCE_NULL / FORCE_NOT_NULL

Explain how these two options affect parsing quoted vs. unquoted NULL markers.

### Exercise 13 — HEADER true

Import a CSV with a header and explicit column list. If the header reorders columns without updating the importer, what risk arises?

### Exercise 14 — HEADER MATCH

If your PostgreSQL version supports it, test `HEADER MATCH` with a valid header and then an incorrect column name. Does the option reorder columns automatically?

### Exercise 15 — Semicolon Delimiter

Write a CSV COPY command using `DELIMITER ';'`. When do spreadsheets export semicolon-delimited CSVs?

### Exercise 16 — CRLF/LF

Explain why physical line counts can differ from CSV record counts. Write a test for a quoted multiline field.

### Exercise 17 — Binary Format

Compare human readability and portability of text, CSV, and binary. Why is binary COPY not a backup?

### Exercise 18 — Binary Types

Can a binary file exported from an INTEGER column be loaded straight into a NUMERIC column without checks? Why or why not?

### Exercise 19 — Measuring File Size

Export the same dataset in text, CSV, and binary; compare byte sizes. Does fewer bytes guarantee a faster import?

### Exercise 20 — server/client Encoding

Run `SHOW server_encoding` and `SHOW client_encoding`. What two distinct concepts do they express?

### Exercise 21 — UTF-8

Create a UTF-8 CSV containing `Đặng Thị Hạnh` and `Nguyễn Ánh`, then import it. How do you verify Vietnamese diacritics are intact?

### Exercise 22 — UTF-16

What errors can occur if a UTF-16 file is passed to COPY with `ENCODING UTF8`? How do you transcode safely without data loss?

### Exercise 23 — BOM

A UTF-8 CSV with a BOM causes `HEADER MATCH` to fail on the first column name. Propose a safe way to handle this.

### Exercise 24 — Mojibake

If the database already stored misdecoded Unicode text, why isn't `SET client_encoding` an automatic fix?

### Exercise 25 — SQL_ASCII

Why shouldn't `SQL_ASCII` be used to bypass invalid UTF-8 errors when importing multilingual data?

### Exercise 26 — Staging File

Create `copyfmt_lab.stage_orders` with TEXT columns. Why avoid loading directly into the typed table when source files frequently contain errors?

### Exercise 27 — CSV Lab

Create `supplier-orders.csv` per the example, run `\copy` into staging, and count logical rows.

### Exercise 28 — NULL/Empty Lab

For E-1004 and E-1005, inspect `note IS NULL` and `LENGTH(note)`. State the expected values.

### Exercise 29 — Casting NUMERIC

Insert a staging row with `amount_text='12,50'`. Why might casting to NUMERIC in SELECT fail? Design locale normalization.

### Exercise 30 — Timestamps

Compare `2026-11-01T08:30:00+07:00` with an offset-less string. How do you preserve the exact instant across exports/imports between sessions in different timezones?

### Exercise 31 — ON CONFLICT

If two rows share `external_id` with different amounts, is `ON CONFLICT DO NOTHING` enough for correctness? Propose a conflict check.

### Exercise 32 — Round-Trip

Build a test covering NULL, empty, comma, quote, newline, tab, backslash, Unicode, and timestamp; export, re-import, and compare using `IS DISTINCT FROM`.

### Exercise 33 — Permissions

Why might a role with `INSERT` on a table still lack permission for server-side `COPY FROM`? When is `\copy` more practical?

### Exercise 34 — RLS

Explain `COPY FROM` restrictions on tables with RLS. How should a multi-tenant application design its import pipeline?

### Exercise 35 — Constraint Failure

Load a file whose last row violates a `CHECK` constraint. What happens to the COPY statement and the disk space of tuples written before the error?

### Exercise 36 — Triggers/Indexes

A table has 10 indexes and multiple triggers. Why can COPY still be slow even with fast CSV parsing?

### Exercise 37 — WAL/Replication

How can bulk loading increase replication lag? Which metrics should you monitor?

### Exercise 38 — UNLOGGED Staging

When is `UNLOGGED` staging useful, and what are its crash-recovery and replication limitations?

### Exercise 39 — COPY FREEZE

Consult version documentation and state the prerequisites for `COPY FREEZE`. Why should it not be enabled indiscriminately?

### Exercise 40 — CSV Injection

A note starting with `=` or `+` is exported and opened in a spreadsheet. Why doesn't CSV quoting guarantee safety? State an appropriate protection policy.

### Exercise 41 — Leading Zeros

Code `001234` turns into `1234` in Excel. Is this an encoding issue, a PostgreSQL COPY issue, or spreadsheet type inference?

### Exercise 42 — JDBC CopyManager

Write Java code using `CopyManager.copyIn(sql, InputStream)` to stream CSV from a file. Why not pass `\copy` to `PreparedStatement`?

### Exercise 43 — Java Export

Use `CopyManager.copyOut(sql, OutputStream)` to generate a CSV. If the connection drops mid-export, how should file publishing be handled?

### Exercise 44 — Import Audit

Design a batch log table containing `source_file`, `checksum`, `encoding`, `format options`, `row_count`, `accepted_count`, `rejected_count`, and `status`.

### Exercise 45 — Error Handling

A CSV raises "extra data after last expected column". List possible causes and how to investigate without widening the schema recklessly.

### Exercise 46 — Production Architecture

A PostgreSQL system ingests 20 GB of CSV/day from multiple suppliers with legacy Unicode/Excel files, multi-tenancy, HA standbys, and dashboards. Design a safe pipeline covering file ingestion, encoding normalization, staging, constraints, batching, idempotency, auditing, security, WAL/replication monitoring, schema contracts, and rollback.

---

## 57. Pre-Production Data Import/Export Checklist

| Question | What to Verify |
| --- | --- |
| Which format does the file use? | Text, CSV, or binary |
| Which encoding? | UTF-8 or verified source encoding |
| Is there a BOM? | Check and normalize properly |
| Which delimiter? | Tab, comma, semicolon, or other |
| Quotes and escapes? | Documented dialect |
| Newlines? | LF/CRLF, quoted multiline |
| Is there a header? | `true`/`false`/`MATCH` per version |
| Is column order right? | Fixed explicit column list |
| Is there a schema contract? | Names, types, nulls, timezones |
| What is the NULL marker? | `\N`/empty/custom |
| Are empty strings preserved? | Test alongside NULL |
| Are literal NULL markers handled? | Quoting/escaping |
| Is there Vietnamese Unicode? | Test with canary strings |
| Is there a Unicode normalization policy? | When matching/searching |
| Do timestamps carry offsets? | ISO 8601/timezone |
| Do numbers use decimal points? | No unexpected locale dependence |
| Are there leading zeros? | Keep as TEXT |
| Is there CSV formula injection risk? | Spreadsheet export policy |
| Which machine holds the file path? | Server `COPY` vs. client `\copy` |
| Are OS permissions aligned? | Server/client filesystem |
| Are unnecessary file-privilege roles avoided? | Avoid granting them |
| Is the COPY protocol supported? | psql/JDBC/GUI |
| Is there a file size limit? | Quota/validation |
| Is there a checksum? | Source integrity |
| Is there staging? | Raw data and validation |
| Are target columns properly typed? | NUMERIC, TIMESTAMPTZ |
| Are CHECK/UNIQUE/FK enforced? | Data invariants |
| Are there triggers? | Side effects/performance |
| Is RLS enabled? | `COPY FROM` limits, real role tests |
| Are SELECT/INSERT privileges right? | Least privilege |
| Is sensitive data in exports controlled? | Column/scope review |
| Is deterministic ordering needed? | `ORDER BY` when required |
| Is idempotency handled? | Prevent duplicates |
| Is there a duplicate policy? | No silent data loss |
| Is there a partial acceptance policy? | Rejected rows and counts |
| Is there SQLSTATE/error logging? | Structured diagnostics |
| Are transaction boundaries clear? | Explicit `COMMIT`/`ROLLBACK` |
| Was end-of-file failure tested? | Statement atomicity |
| Is WAL monitored? | Disk/replication lag |
| Is there an autovacuum/ANALYZE plan? | Statistics/bloat |
| Are duration and load bounded? | Availability |
| Are there round-trip tests? | Null/empty/Unicode/quotes |
| Tested with real consumers? | Excel/BI/Java |
| Is format metadata versioned? | Reproducibility |
| Is completeness verified before publishing? | Temp path/checksum |
| Are retention and encryption enforced? | Files and staging |
| Is there a backup/restore strategy? | Never use binary COPY as full backup |

---

## 58. Conclusion

**Text, CSV, binary formats, and encoding choices** span both PostgreSQL syntax and end-to-end data correctness across systems.

Key principles to remember:

1. **Format and encoding are separate concepts.** CSV/text defines field and row structure; UTF-8 or a code page defines how bytes represent characters.
2. **COPY and \copy differ in where files open.** Server-side SQL `COPY` accesses the database server filesystem; `psql \copy` streams client-side files over the COPY protocol.
3. **Text format is a PostgreSQL-specific dialect.** Tab-delimited by default, with backslash escapes and `\N` as the NULL marker.
4. **CSV is convenient for exchange but has strict rules.** Delimiter, quote, escape, header, NULL marker, and multiline fields must align.
5. **NULL is not an empty string.** Default CSV distinguishes them via quoted vs. unquoted fields; always test round-trips.
6. **Binary COPY is useful for specialized PostgreSQL streams, not as a universal archive or backup format.**
7. **UTF-8 is usually the safest choice for new systems.** Still verify sources, handle BOMs, and never guess encoding from file extensions.
8. **Correct encoding does not normalize data.** Numeric locales, timezones, leading zeros, and Unicode normalization belong to separate contracts.
9. **COPY still obeys transactions, constraints, triggers, and WAL.** A fast bulk load is unsafe without validating data, permissions, and replication impact.
10. **Staging decouples ingestion from validation.** Especially with messy supplier files, load TEXT first and promote to typed tables with explicit rejection policies.
11. **Exporting CSV for spreadsheets risks formula injection.** CSV quoting alone does not make spreadsheets treat every cell as safe text.
12. **Test with real data and real consumers.** Verify round-trip correctness before optimizing throughput; report success or publish files only after the entire pipeline completes cleanly.

A reliable PostgreSQL import/export pipeline does not just move rows quickly—it **preserves the exact meaning of every value, accounts for byte provenance, distinguishes NULL from empty strings, protects Unicode, prevents data leaks, and recovers cleanly when files or connections fail**.
