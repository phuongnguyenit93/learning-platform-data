# CSV: Delimiter, Enclosure, Escape, Newline, Charset, and NULL Representation

CSV is commonly used to exchange data between MySQL, Excel, accounting systems, web applications, and analytics tools. However, CSV does not have a single universal encoding across all systems. Two files with the `.csv` extension can still differ in column delimiters, string enclosures, quote escaping rules, line endings, charsets, and how `NULL` values are represented.

In MySQL, `LOAD DATA [LOCAL] INFILE` reads text files into a table at high speed. `SELECT ... INTO OUTFILE` writes query results to a file on the server. Both statements share `FIELDS` and `LINES` rules; for data to round-trip accurately, read and write configurations must match. This lesson uses MySQL 8.4 and illustrates a CSV format with commas, double quotes, backslash escaping, CRLF line endings, and UTF-8.

## Objectives

After this lesson, you will be able to:

- Distinguish delimiter, enclosure, escape character, and line terminator.
- Choose the right `FIELDS TERMINATED BY`, `ENCLOSED BY`, `ESCAPED BY`, and `LINES TERMINATED BY`.
- Load CSV files with headers, column orders differing from the table, and data requiring transformation.
- Distinguish `NULL`, empty strings, and the literal string `NULL`.
- Handle UTF-8/`utf8mb4` charsets, BOMs, and newlines across operating systems.
- Export CSV with `SELECT ... INTO OUTFILE`, check warnings, and handle import errors safely.

## 1. CSV Is an Exchange Format with Many Variants

CSV stands for *comma-separated values*, yet in practice the delimiter is not always a comma. Tools in many locales use semicolons or tabs; Windows files commonly use CRLF, whereas Linux files typically use LF. Some tools enclose strings in double quotes, while others omit quotes when unnecessary.

For example, these two lines mean the same thing but are formatted differently:

```text
101,Nguyen Van A,125000
102,Tran Thi B,98000
```

```text
101;"Nguyen Van A";125000\r\n
102;"Tran Thi B";98000\r\n
```

For MySQL to read the file accurately, identify its components before writing the statement:

| Component | MySQL Clause | Example | Meaning |
|---|---|---|---|
| Column delimiter | `FIELDS TERMINATED BY` | `','` or `';'` | Ends one field and begins the next. |
| Field enclosure | `FIELDS ENCLOSED BY` | `'"'` | Marks the start/end of a value, typically used for strings. |
| Escape character | `FIELDS ESCAPED BY` | `'\\'` in SQL | Allows representing quotes, delimiters, or special characters inside a value. |
| Line terminator | `LINES TERMINATED BY` | `'\r\n'` or `'\n'` | Marks the end of a record. |
| File charset | `CHARACTER SET` | `utf8mb4` | Tells MySQL how to decode bytes in the file. |
| Missing value | `NULL` rule | `\N` or `NULL` | Distinguishes SQL `NULL` from an empty string. |

MySQL requires non-empty enclosure and escape characters to be a single character; delimiters and line terminators may be multi-character. Format strings in `FIELDS`/`LINES` support only ASCII characters. Avoid configuring a delimiter that equals or prefixes the enclosure or line terminator, as the parser may fail to determine boundaries.

## 2. MySQL Default Rules

If `FIELDS` and `LINES` are omitted, MySQL defaults to the equivalent of:

```sql
FIELDS TERMINATED BY '\t'
       ENCLOSED BY ''
       ESCAPED BY '\\'
LINES TERMINATED BY '\n'
       STARTING BY ''
```

This means by default MySQL reads tab-delimited files, with no string enclosure, backslash as the escape character, and LF line endings. This is not the typical CSV format produced by Excel.

In SQL string literals, backslash is also MySQL's escape character. Therefore:

- `'\t'` represents a tab character.
- `'\n'` represents a line feed (LF).
- `'\r'` represents a carriage return (CR).
- `'\r\n'` represents a CRLF pair.
- `'\\'` represents a single literal backslash character.

When using `FIELDS ESCAPED BY '\\'`, files can use sequences such as `\t`, `\n`, `\r`, and `\\` to represent special characters. Specifically, `\N` is the convention representing SQL `NULL` under the default configuration.

## 3. Reading CSV with LOAD DATA

Suppose `orders.csv` was exported from a spreadsheet tool with a header, commas separating columns, double quotes enclosing strings, and CRLF line endings:

```text
order_id,customer_name,amount,created_at,note
101,"Nguyễn Văn An",125000.00,2026-11-19 09:30:00,"Deliver, call ahead"
102,"Trần Thị Bình",98000.00,2026-11-19 10:00:00,"Customer said ""wait until afternoon"""
103,"Lê Minh Châu",\N,2026-11-19 11:00:00,
```

Example loading into a staging table:

```sql
CREATE TABLE orders_stage (
    order_id        VARCHAR(30),
    customer_name   VARCHAR(255),
    amount_text     VARCHAR(50),
    created_at_text VARCHAR(50),
    note            TEXT
) ENGINE = InnoDB;

LOAD DATA LOCAL INFILE '/data/orders.csv'
INTO TABLE orders_stage
CHARACTER SET utf8mb4
FIELDS TERMINATED BY ','
       OPTIONALLY ENCLOSED BY '"'
       ESCAPED BY '\\'
LINES TERMINATED BY '\r\n'
IGNORE 1 LINES
(order_id, customer_name, amount_text, created_at_text, note);
```

Explanation:

- `LOCAL` instructs the client program to read the file on the client machine and stream its contents to the MySQL server.
- `CHARACTER SET utf8mb4` decodes file bytes as UTF-8 and converts data to target column charsets when needed.
- `FIELDS TERMINATED BY ','` selects comma as the delimiter.
- `OPTIONALLY ENCLOSED BY '"'` allows string fields to be enclosed by double quotes. On input, MySQL handles enclosures when present regardless of whether `OPTIONALLY` is specified; this keyword primarily governs output formatting.
- `ESCAPED BY '\\'` uses backslash to escape special characters and treats `\N` as `NULL`.
- `LINES TERMINATED BY '\r\n'` reads Windows files with CRLF pairs.
- `IGNORE 1 LINES` skips the header line.
- The column list specifies field order in the file; it does not need to match column order in the table.

If the file was created on Linux/macOS with LF, change to:

```sql
LINES TERMINATED BY '\n'
```

If the file uses a bare CR as line terminator, specify `LINES TERMINATED BY '\r'`. Do not guess line endings from the file extension; inspect the source file or confirm with the exporting system.

### 3.1. Delimiter and Enclosure

Delimiters separate fields. If a value contains the delimiter, a newline, or the enclosure character, that field must be properly enclosed and escaped according to the file's rules.

Example with a comma:

```text
101,"Nguyễn Văn An, Store 1",125000
```

Without an enclosure, the parser may interpret the customer name as two separate columns. When fields are not always quoted, use `OPTIONALLY ENCLOSED BY '"'` for export statements; when reading, MySQL still recognizes enclosures where present.

With `ENCLOSED BY '"'`, a double quote inside a value can be represented by doubling it:

```text
"Customer said ""wait until afternoon"""
```

The value read into the table is:

```text
Customer said "wait until afternoon"
```

Alternatively, the file may escape quotes using the `ESCAPED BY` character, such as `\"` when escaping with backslash. Confirm which approach the CSV exporter uses; never change `ESCAPED BY` arbitrarily between two systems.

### 3.2. ESCAPED BY and Special Characters

With backslash as the escape character, MySQL recognizes common sequences:

| In File | Value After Reading |
|---|---|
| `\\` | A single backslash character `\`. |
| `\t` | Tab. |
| `\n` | Line feed inside the value. |
| `\r` | Carriage return inside the value. |
| `\0` | NUL byte. |
| `\N` | SQL `NULL`. |

Avoid setting `ESCAPED BY ''` merely to suppress backslashes if the file may contain quotes, delimiters, newlines, or special characters. When escape is empty, MySQL does not interpret escape sequences; data can be split across fields or lines incorrectly. If the source system uses different rules, adjust the export format at the source or normalize the file before loading.

## 4. Distinguishing NULL, Empty Strings, and the Literal String NULL

This is one of the most common pitfalls in data migration. These three values are not equivalent:

| Representation | Meaning |
|---|---|
| `\N` | SQL `NULL` value when `ESCAPED BY` is backslash. |
| Empty field between two delimiters, e.g. `101,,125000` | Empty string for string columns; for numeric/datetime columns, conversion may produce a default value or warning depending on type and SQL mode. |
| `NULL` or `"NULL"` | When `ENCLOSED BY` is set, an unquoted `NULL` is read as SQL `NULL`; a quoted `"NULL"` is read as the literal string `NULL`. |

Under default settings, `NULL` is written to a file as `\N`, and on load `\N` is interpreted as SQL `NULL` if the escape character is backslash. When `FIELDS ENCLOSED BY` is non-empty, an unquoted field containing the word `NULL` is also read as `NULL`; `NULL` inside quotes becomes the string `'NULL'`.

Example of three distinct fields:

```text
101,\N,active
102,,active
103,"NULL",active
```

In this example, the second field is SQL `NULL`, an empty string, and the character string `'NULL'`, respectively.

When `FIELDS ESCAPED BY ''`, MySQL writes `NULL` as the word `NULL`, not `\N`. With fixed-row format (both `FIELDS TERMINATED BY` and `FIELDS ENCLOSED BY` are empty), `NULL` is written as an empty string; upon re-reading, `NULL` cannot be distinguished from an empty string. Do not use fixed-row format if you need to preserve this distinction.

**Principle:** agree on the `NULL` sentinel between exporter and importer. Do not automatically turn every empty field into `NULL` if business logic must distinguish "no value" from "present but empty."

## 5. Charset and Unicode

The file's charset is how bytes on disk are decoded; a column's charset is how strings are stored inside MySQL. These two concepts are independent. For Vietnamese data, use UTF-8 and `utf8mb4` columns to preserve full Unicode.

Check table and column charset/collation:

```sql
SHOW CREATE TABLE orders_stage\G

SHOW VARIABLES LIKE 'character_set_database';
SHOW VARIABLES LIKE 'character_set_server';
SHOW VARIABLES LIKE 'character_set_filesystem';
```

Specify the file charset when loading:

```sql
LOAD DATA LOCAL INFILE '/data/orders.csv'
INTO TABLE orders_stage
CHARACTER SET utf8mb4
FIELDS TERMINATED BY ','
       OPTIONALLY ENCLOSED BY '"'
       ESCAPED BY '\\'
LINES TERMINATED BY '\r\n'
IGNORE 1 LINES;
```

`SET NAMES` and `character_set_client` do not determine the input file's charset. `LOAD DATA` reads every field in the file using the single specified charset, rather than guessing separate charsets per column. MySQL does not support directly loading files encoded in `ucs2`, `utf16`, `utf16le`, or `utf32`; convert the file to a supported charset before importing.

When exporting a file, specify the matching charset:

```sql
SELECT order_id, customer_name, amount, created_at, note
INTO OUTFILE '/var/lib/mysql-files/orders.csv'
CHARACTER SET utf8mb4
FIELDS TERMINATED BY ','
       OPTIONALLY ENCLOSED BY '"'
       ESCAPED BY '\\'
LINES TERMINATED BY '\r\n'
FROM orders
ORDER BY order_id;
```

If `CHARACTER SET` is omitted in `SELECT ... INTO OUTFILE`, data is written using the `binary` charset, meaning no charset conversion occurs. When results contain columns with different charsets, the file may be difficult or impossible to reload cleanly. Always specify charset explicitly in both directions.

### 5.1. BOM and Corrupted Vietnamese Characters

Some editors save UTF-8 with a BOM (byte order mark) at the start of the file. The BOM can be read as part of the first column name or first value, introducing stray characters like `ï»¿` or breaking a match on the first value. If this occurs, inspect the leading bytes of the file and re-export as UTF-8 without BOM or strip the BOM before running `LOAD DATA`.

Common signs of a wrong charset:

- Vietnamese characters turn into `?` or mojibake character sequences.
- Import finishes without error, yet the first value in the file contains unexpected characters.
- An exported file looks right on one machine but garbled when opened in another tool.

Verify the source charset, specify the matching `CHARACTER SET`, and check target column charsets/collations before loading large volumes.

## 6. Newlines and Multi-Line Data

Operating systems and applications can use different line endings:

| Convention | Bytes | Configuration |
|---|---|---|
| LF (Linux, Unix) | `0A` | `LINES TERMINATED BY '\n'` |
| CRLF (Windows) | `0D 0A` | `LINES TERMINATED BY '\r\n'` |
| CR (some older macOS files) | `0D` | `LINES TERMINATED BY '\r'` |

Choosing the wrong line terminator can leave a trailing `\r` on the last field or merge multiple records into one row. For example, reading a Windows file with `LINES TERMINATED BY '\n'` can leave CR appended to the final field. Conversely, reading an LF file with CRLF may fail to split lines properly.

CSV allows a string field to contain newlines if the field is properly enclosed. Consequently, physical line count in a file can exceed the logical record count. Do not rely on simple text line-counting tools to verify CSV row counts when fields span multiple lines; use a CSV parser or inspect post-import results.

## 7. Column Mapping and Data Cleansing During Load

CSV files often have a different column order from the table, extra columns, or values needing normalization. Use a column list and user variables to control mapping.

Example where the file order is `customer_name, order_id, amount, created_at, note`, while the target table has a different order:

```sql
LOAD DATA LOCAL INFILE '/data/orders.csv'
INTO TABLE orders
CHARACTER SET utf8mb4
FIELDS TERMINATED BY ','
       OPTIONALLY ENCLOSED BY '"'
       ESCAPED BY '\\'
LINES TERMINATED BY '\r\n'
IGNORE 1 LINES
(@customer_name, @order_id, @amount, @created_at, @note)
SET customer_name = TRIM(@customer_name),
    order_id = CAST(@order_id AS UNSIGNED),
    amount = NULLIF(@amount, ''),
    created_at = STR_TO_DATE(@created_at, '%Y-%m-%d %H:%i:%s'),
    note = @note;
```

In this example:

- `@customer_name` and the remaining variables receive values in file field order.
- `TRIM()` strips leading/trailing whitespace from customer names.
- `CAST()` converts the order ID to an unsigned integer.
- `NULLIF(@amount, '')` converts empty numeric fields into SQL `NULL`.
- `STR_TO_DATE()` parses datetime strings in the known format into `DATETIME` values.
- `@note` is preserved as-is; if the field in the file is `\N` and escaping is backslash, MySQL treats it as `NULL`.

Do not load untrusted data directly into heavily constrained business tables. For important imports, use a staging table with `VARCHAR` columns to hold raw data, check format errors, and then `INSERT ... SELECT` into production tables with explicit conversions.

### 7.1. Example Staging Pipeline

```sql
-- 1. Load file into a staging table with text columns.
LOAD DATA LOCAL INFILE '/data/orders.csv'
INTO TABLE orders_stage
CHARACTER SET utf8mb4
FIELDS TERMINATED BY ','
       OPTIONALLY ENCLOSED BY '"'
       ESCAPED BY '\\'
LINES TERMINATED BY '\r\n'
IGNORE 1 LINES
(order_id, customer_name, amount_text, created_at_text, note);

-- 2. Check rows missing required fields.
SELECT *
FROM orders_stage
WHERE order_id IS NULL
   OR customer_name IS NULL
   OR amount_text = ''
   OR created_at_text = '';

-- 3. Check datetime strings that fail to parse.
SELECT created_at_text
FROM orders_stage
WHERE created_at_text IS NOT NULL
  AND STR_TO_DATE(created_at_text, '%Y-%m-%d %H:%i:%s') IS NULL;

-- 4. Insert only valid rows into the business table.
INSERT INTO orders (order_id, customer_name, amount, created_at, note)
SELECT CAST(order_id AS UNSIGNED),
       TRIM(customer_name),
       CAST(NULLIF(amount_text, '') AS DECIMAL(12,2)),
       STR_TO_DATE(created_at_text, '%Y-%m-%d %H:%i:%s'),
       note
FROM orders_stage
WHERE order_id REGEXP '^[0-9]+$'
  AND customer_name IS NOT NULL
  AND STR_TO_DATE(created_at_text, '%Y-%m-%d %H:%i:%s') IS NOT NULL;
```

The validation checks in this example are illustrative. In production systems, define business rules for negative amounts, currency precision, timezones, invalid dates, duplicate keys, and mandatory fields. Save rejected rows into an error table so they can be corrected and reloaded.

## 8. Exporting CSV with SELECT ... INTO OUTFILE

`SELECT ... INTO OUTFILE` writes query results to a file on the MySQL server host, not the client machine. Example:

MySQL escapes an enclosure character inside a value by preceding it with the `ESCAPED BY` character. With backslash, an embedded double quote is exported as `\"`. Many RFC 4180 CSV libraries double quotes (`""`) instead of using backslash. MySQL can read doubled quotes when a field starts with the enclosure, but MySQL's export format does not necessarily match every application's dialect. When exchanging files with a specific system, test an actual file against that system's parser.

```sql
SELECT order_id, customer_name, amount, created_at, note
INTO OUTFILE '/var/lib/mysql-files/orders-export.csv'
CHARACTER SET utf8mb4
FIELDS TERMINATED BY ','
       OPTIONALLY ENCLOSED BY '"'
       ESCAPED BY '\\'
LINES TERMINATED BY '\r\n'
FROM orders
ORDER BY order_id;
```

Key requirements to remember:

- The account needs the `FILE` privilege.
- The path is on the server running `mysqld`.
- If `secure_file_priv` is set to a directory, the file must reside inside that directory.
- The target file must not already exist; MySQL will not overwrite an existing file.
- The file is created under the OS account running `mysqld`; filesystem permissions must be managed separately.

Check configuration:

```sql
SHOW VARIABLES LIKE 'secure_file_priv';
```

If `secure_file_priv` returns `NULL`, server-side file import/export is disabled. If it returns a path, use only that directory. Do not broaden file permissions or point the variable to a shared directory just to make an export command run.

If you want to create the file on the client machine, run the query from the client and redirect stdout to a local file, such as `mysql -e "SELECT ..." > result.txt`. However, that approach requires handling headers, escaping, and output formatting separately; it is not automatically equivalent to `SELECT ... INTO OUTFILE`.

## 9. LOCAL and File Access Permissions

The two forms of `LOAD DATA` have different file locations and security requirements:

| Statement | Where Is the File? | Privileges / Notes |
|---|---|---|
| `LOAD DATA INFILE` | MySQL Server host | Requires `FILE` privilege; subject to `secure_file_priv`; file must be readable by the MySQL OS account. |
| `LOAD DATA LOCAL INFILE` | Connecting client machine | Client reads the file and sends it to the server; does not require `FILE`, but both client and server must permit `LOCAL`. |
| `SELECT ... INTO OUTFILE` | MySQL Server host | Requires `FILE` privilege; subject to `secure_file_priv`; target file must not already exist. |

Check server-side variables:

```sql
SHOW VARIABLES LIKE 'local_infile';
SHOW VARIABLES LIKE 'secure_file_priv';
```

`LOAD DATA LOCAL INFILE` works only when both server and client allow it. If `local_infile` is off, `LOCAL` statements fail with an error. Because the client streams the file over the connection, `LOCAL` can be slower than direct server reads, and the server still needs enough temporary directory space to buffer the incoming file during processing.

Enable `LOCAL` only when needed, connect to trusted servers, and enforce TLS per system policy. An untrusted server can request local files from a `LOCAL`-enabled client; therefore, do not enable `LOCAL` broadly for environments making arbitrary connections.

An easily overlooked detail: `LOAD DATA LOCAL` without `REPLACE` behaves like `IGNORE`. Duplicate-key rows may be skipped and data conversion errors can turn into warnings rather than aborting the statement. When strict control is required, load into staging, read warnings, and verify row counts before moving data into business tables.

## 10. Checking Warnings and Import Results

Immediately after `LOAD DATA`, inspect the returned summary and warnings:

```sql
SHOW COUNT(*) WARNINGS;
SHOW WARNINGS LIMIT 50;
```

Warnings can indicate:

- Invalid or truncated numeric values.
- Unparseable date/time strings.
- `NULL` loaded into a `NOT NULL` column.
- Data exceeding column length.
- Duplicate-key rows skipped when using `IGNORE` or `LOCAL`.

Do not check only whether the statement completed without fatal error. Reconcile rows read, rows loaded, warning count, and skipped rows. For critical data, archive the original file, import timestamp, statement used, and verification results for auditing or replay.

## 11. Common Issues

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Every line becomes a single field | Wrong delimiter selected, often tab instead of comma | Declare the correct `FIELDS TERMINATED BY`. |
| End-of-line values contain `\r` | Reading CRLF with `LINES TERMINATED BY '\n'` | Use `LINES TERMINATED BY '\r\n'`. |
| Vietnamese characters become garbled | File charset and import charset mismatch | Verify source, use UTF-8/`utf8mb4`, and specify `CHARACTER SET`. |
| First column starts with `ï»¿` | File has a UTF-8 BOM | Export UTF-8 without BOM or strip BOM before loading. |
| Columns are shifted | Header not skipped, wrong column order, or wrong delimiter/enclosure | Use `IGNORE 1 LINES`, specify column list, and check dialect. |
| Comma inside a name splits columns | Field is not properly enclosed | Use appropriate enclosure and verify quote escaping. |
| Literal string `NULL` becomes SQL NULL unexpectedly | Enclosure is set but literal NULL field is unquoted | Quote literal strings with enclosure; standardize NULL sentinel. |
| Empty string becomes NULL | Indistinguishable sentinel or `NULLIF` conversion | Keep empty strings and `\N` distinct; avoid over-normalizing. |
| Cannot read file | Wrong file location, OS permissions, or `secure_file_priv` | Confirm whether file is on client or server and check exact permissions. |
| `LOCAL` rejected | Client or server disallows `LOCAL` | Check `local_infile` and client configuration; enable only if security permits. |
| Import reports duplicate key | File has keys colliding with existing data | Choose error, `IGNORE`, or `REPLACE` policy explicitly; do not rely on accidental defaults. |
| Import finishes but rows are missing | `LOCAL`/`IGNORE` skipped bad or duplicate rows | Read warnings, reconcile row counts, and reload from staging after fixing. |

## 12. Standard Workflow When Receiving a New CSV File

1. Identify delimiter, enclosure, escape, line terminator, and charset from the exporting system.
2. Check whether the file has a header, BOM, or fields containing delimiters, quotes, or embedded newlines.
3. Establish the `NULL` convention: `\N`, literal `NULL`, empty string, or a custom sentinel.
4. Create a staging table or explicitly specify column mapping and data conversions.
5. Choose `LOAD DATA INFILE` if the file is on the server with proper permissions; choose `LOCAL` if the file is on the client and policy permits.
6. Test with a small sample, inspecting results and warnings.
7. Reconcile row counts, duplicate keys, required values, and data types.
8. Load valid data into business tables and archive the original file alongside the import log.

For exports, specify charset and `FIELDS`/`LINES` explicitly; ensure the recipient uses the matching dialect to read it. If strict compatibility with a specific CSV standard or multiple external apps is required, test with the target app's CSV parser rather than assuming every tool interprets CSV identically to MySQL.

## 13. Self-Check Exercises

1. A file created on Windows uses CRLF. If `LINES TERMINATED BY '\n'` is used, what artifact can appear at the end of the last field on a line?
2. Why does `LOAD DATA LOCAL INFILE` not require the `FILE` privilege, yet requires both client and server to allow `LOCAL`?
3. With `FIELDS ESCAPED BY '\\'`, which sequence represents SQL `NULL`? Which represents an empty string?
4. When `FIELDS ENCLOSED BY '"'` is set, what is the difference between `NULL` and `"NULL"`?
5. Why is `CHARACTER SET utf8mb4` inside `LOAD DATA` more important than `SET NAMES utf8mb4` for decoding file bytes?
6. Why might `LOAD DATA LOCAL` skip certain bad rows instead of failing immediately?
7. When a file's column order differs from the table, which part of the `LOAD DATA` statement is needed?
8. Why does `SELECT ... INTO OUTFILE` not write the file directly onto the client machine?

**Answer Hints:** (1) A CR character may remain at the end of the final field. (2) The client reads the file and streams its contents over the connection; `LOCAL` must be enabled on both ends. (3) `\N` is SQL `NULL`; an empty field is an empty string for string columns. (4) Unquoted `NULL` is SQL `NULL`, while `"NULL"` is the literal string. (5) `LOAD DATA` decodes file bytes using `CHARACTER SET`; `SET NAMES` does not affect file charset. (6) `LOCAL` acts like `IGNORE` when `REPLACE` is not specified, so conversion errors become warnings and processing continues. (7) The column list and user variables matching the file's field order. (8) `OUTFILE` always creates files on the server's filesystem; writing on the client requires a client command or another export tool.

## References

- [MySQL 8.4 Reference Manual: LOAD DATA Statement](https://dev.mysql.com/doc/refman/8.4/en/load-data.html)
- [MySQL 8.4 Reference Manual: SELECT ... INTO Statement](https://dev.mysql.com/doc/refman/8.4/en/select-into.html)
- [MySQL 8.4 Reference Manual: Security Considerations for LOAD DATA LOCAL](https://dev.mysql.com/doc/refman/8.4/en/load-data-local-security.html)
- [MySQL 8.4 Reference Manual: Character Sets and Collations](https://dev.mysql.com/doc/refman/8.4/en/charset.html)
- [MySQL 8.4 Reference Manual: Server System Variables (secure_file_priv, local_infile)](https://dev.mysql.com/doc/refman/8.4/en/server-system-variables.html)
