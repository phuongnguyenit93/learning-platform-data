# Headers, Delimiters, Escape Characters, and NULL Representation in PostgreSQL

Within the **Data Import and Export** chapter of the **Database Engine Relational PostgreSQL** module, this lesson focuses on the four factors that determine whether a CSV or TEXT file is read and exported with the right meaning: **headers**, **delimiters**, **quotes/escapes**, and **SQL NULL representation**.

Suppose you have a CSV file:

~~~csv
id,customer_name,note
1,"An, Nguyễn","Call before 9:00"
2,Bình,
3,Chi,""
4,Dũng,"Line one
Line two"
~~~

At first glance, these four data rows look simple. Yet if the importer fails to distinguish **a comma inside a cell from a column delimiter**, **an unquoted empty cell from a quoted empty string**, or **a newline inside a quoted field from the end of a record**, values can shift columns, turn into NULL, or fail to load altogether.

PostgreSQL supports `text`, `csv`, and `binary` formats via `COPY`. Among them, `text` and `csv` have different rules for all four factors above. **You cannot switch `FORMAT text` to `FORMAT csv` while keeping the same escape and NULL assumptions and expect the file to mean the same thing.**

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish PostgreSQL `COPY`, psql `\copy`, and data streaming over `STDIN`/`STDOUT`.
2. Choose `FORMAT csv` or `FORMAT text` appropriately for a data source.
3. Explain `HEADER true`, `HEADER false`, and `HEADER MATCH`, along with column-order verification limits.
4. Configure `DELIMITER` to match CSV files using commas, semicolons, or other characters.
5. Recognize that a delimiter must be a **single single-byte character**, not an arbitrary multi-character string.
6. Distinguish `QUOTE` (field enclosure) from `ESCAPE` (the character escaping quotes/escapes inside CSV values).
7. Understand default CSV rules: quote `"`, escape `"`, so a literal quote in data is written as `""`.
8. Parse values containing delimiters, quotes, newlines, or whitespace accurately.
9. Distinguish SQL `NULL` from empty string `''`, string `'NULL'`, and string `'\N'`.
10. Explain why default CSV maps **unquoted empty cells → NULL**, while `""` → empty string.
11. Use `NULL '...'` to select an explicit NULL representation.
12. Use `FORCE_NULL` and `FORCE_NOT_NULL` in `COPY FROM CSV` when you need to adjust NULL interpretation.
13. Use `FORCE_QUOTE` in `COPY TO CSV` without losing NULL distinction.
14. Understand escaping in `FORMAT text` via backslash sequences: `\t`, `\n`, `\r`, `\\`, `\N`.
15. Know that headers do not remap column names to different positions: `COPY` always loads by **position**.
16. Recognize `missing data for column`, `extra data after last expected column`, and data-type conversion errors.
17. Handle multiline CSVs, Vietnamese Unicode, BOMs, CRLF/LF line endings, and client encoding.
18. Design an import pipeline into a staging table with mapping, validation, and safe re-runnability.
19. Perform export→import round-trip tests to verify NULL is never conflated with empty strings.
20. Apply an intake checklist for partner files instead of guessing delimiter, encoding, and schema.

## 2. COPY and \copy: Where Does the Data Travel?

### 2.1. COPY Is a Server SQL Command

~~~sql
COPY schema_name.table_name
FROM '/absolute/server/path/data.csv'
WITH (FORMAT csv, HEADER true);
~~~

When specifying a file path directly in `COPY`, the **PostgreSQL server** reads or writes the file on the server host under the OS account and appropriately privileged DB role. It does **not** automatically read files sitting on your local machine running psql or your IDE.

### 2.2. \copy Is a psql Client Command

~~~text
\copy schema_name.table_name FROM 'data.csv' WITH (FORMAT csv, HEADER true)
~~~

`\copy` is a **psql meta-command**, not SQL to send verbatim from Java/JDBC. With `\copy`, psql opens the file **on the client machine**, then streams its contents over the database connection via `COPY ... FROM STDIN` or reads output from `COPY ... TO STDOUT`.

### 2.3. COPY ... FROM STDIN / TO STDOUT

~~~sql
COPY schema_name.table_name
FROM STDIN
WITH (FORMAT csv, HEADER true);
~~~

`STDIN` means the server reads bytes over the **COPY protocol stream** from the client; `STDOUT` sends bytes back to the client. `psql`, PostgreSQL drivers, or ETL applications manage this stream in their own way.

### 2.4. Do Not Use COPY PROGRAM Arbitrarily

`COPY ... PROGRAM 'shell command'` runs a program under the **server's** environment and privileges, posing high risk if commands are built from untrusted input. It is unnecessary for headers/CSV/NULL handling; prefer client-side `\copy` or least-privilege streaming APIs.

### 2.5. Execution Permissions

| Invocation | Where is the file? | Key permission requirement |
| --- | --- | --- |
| `COPY ... FROM 'file'` | Database server side | Server file read permission and table INSERT |
| `COPY ... TO 'file'` | Database server side | Server file write permission and data SELECT |
| `\copy ... FROM 'file'` | psql client side | Client file read access, DB role has INSERT |
| `\copy ... TO 'file'` | psql client side | Client file write access, DB role has SELECT |
| `COPY ... FROM STDIN` | Client sends stream | INSERT privilege, driver supports protocol |
| `COPY ... TO STDOUT` | Server sends stream | SELECT privilege, driver supports protocol |

Reading or writing server files may require superuser or specialized roles such as `pg_read_server_files` and `pg_write_server_files`. **Never grant these broad roles just to import a CSV from a laptop.**

## 3. The Three COPY Formats and This Lesson's Four Elements

### 3.1. Comparison Table

| Property | `FORMAT text` | `FORMAT csv` | `FORMAT binary` |
| --- | --- | --- | --- |
| Default for COPY | **Yes** | No | No |
| Default delimiter | Tab | Comma `,` | Binary byte structure |
| Default NULL | `\N` | **Unquoted** empty field | Binary marker |
| Quote/escape | Backslash escapes per COPY text | CSV QUOTE and ESCAPE | Not applicable |
| `HEADER` | Supported in modern PostgreSQL, syntax/version dependent | Yes | No |
| `DELIMITER` | Yes | Yes | No |
| `NULL '...'` | Yes | Yes | No |
| `QUOTE`/`ESCAPE` | No | Yes | No |
| View in text editor | Yes, requires knowing tab/backslash | Yes, requires CSV parser | Unsuitable |
| Cross-system compatibility | Follows PostgreSQL COPY text rules | Good when dialect is agreed | Depends on types/version/architecture |

`FORMAT text` is the **default** when `FORMAT` is omitted. A file casually called "CSV" imported via `COPY FROM ...` without `FORMAT csv` will be parsed as **TEXT**, easily causing delimiter and NULL errors.

### 3.2. General Syntax for CSV

~~~sql
COPY schema_name.table_name (col_a, col_b, col_c)
FROM STDIN
WITH (
    FORMAT csv,
    HEADER true,
    DELIMITER ',',
    QUOTE '"',
    ESCAPE '"',
    NULL ''
);
~~~

These options specify the **format contract**. Defaults need not be written out, yet in long-lived pipelines, declaring them explicitly makes it immediately clear how files are interpreted.

### 3.3. General Syntax for TEXT

~~~sql
COPY schema_name.table_name (col_a, col_b, col_c)
FROM STDIN
WITH (
    FORMAT text,
    DELIMITER E'\t',
    NULL E'\\N'
);
~~~

`E'\t'` is a **SQL escape string** containing a tab character. `E'\\N'` represents the two characters **backslash + N** in SQL. This is handled by the **SQL string literal parser of the COPY command**, distinct from `FORMAT text` later interpreting backslashes inside the **file data**.

### 3.4. Data Columns Do Not Have to Match Header Names

~~~sql
COPY my_table (customer_id, customer_name)
FROM STDIN
WITH (FORMAT csv, HEADER true);
~~~

`COPY FROM` maps **field 1 → customer_id** and **field 2 → customer_name**; it does not inspect header names to decide columns. `HEADER true` only skips the header row on input. To verify header names and order, use `HEADER MATCH` where supported.

## 4. Repeatable Lab Dataset in an Isolated Schema

Practice only on a database where creating schemas and test data is permitted. Never run `TRUNCATE`, `DROP SCHEMA CASCADE`, or test `COPY FROM` on production tables to experiment with delimiters.

### 4.1. Creating the Schema

~~~sql
CREATE SCHEMA copy411;
~~~

If schema `copy411` already exists from a prior session, use a fresh lab database or pick another name after verifying cleanup safety. The examples below assume a newly created schema.

### 4.2. Contacts Table

~~~sql
CREATE TABLE copy411.contacts (
    contact_id integer PRIMARY KEY,
    full_name text NOT NULL,
    nickname text,
    note text,
    active boolean NOT NULL DEFAULT true,
    created_at date
);
~~~

`nickname` and `note` allow NULL so we can distinguish **NULL** from **empty strings**. `full_name` is NOT NULL, and `contact_id` is the primary key to verify column order never shifts.

### 4.3. Inserting Diverse Test Data

~~~sql
INSERT INTO copy411.contacts (
    contact_id, full_name, nickname, note, active, created_at
)
VALUES
    (1, 'An, Nguyễn', NULL, 'Comma, inside value', true, DATE '2026-01-03'),
    (2, 'Bình "Bé"', '', 'Empty string differs from NULL', false, DATE '2026-02-14'),
    (3, 'Chi', 'C', E'Line 1\nLine 2', true, NULL),
    (4, 'Dũng', 'NULL', E'C:\\data\\report.csv', true, DATE '2026-03-20'),
    (5, 'Em', E'\\N', NULL, true, DATE '2026-04-01');
~~~

These rows use `E'...'` to represent backslashes and newlines unambiguously in **SQL**, not as CSV snippets. `E'Line 1\nLine 2'` contains a real newline; `E'C:\\data\\report.csv'` contains real backslashes; `E'\\N'` creates the literal string `\N`.

### 4.4. Verifying NULL and Empty Strings

~~~sql
SELECT
    contact_id,
    nickname,
    nickname IS NULL AS nickname_is_null,
    nickname = '' AS nickname_is_empty,
    length(nickname) AS nickname_length
FROM copy411.contacts
ORDER BY contact_id;
~~~

For `contact_id=1`, `nickname IS NULL` is true. For `contact_id=2`, `nickname = ''` is true. For `contact_id=4`, nickname is the four-character string `NULL`; for `contact_id=5`, nickname is **backslash plus N**, not SQL NULL.

### 4.5. Why Include "Tricky" Data?

A test set containing only `1,An,A` cannot verify quotes, escapes, NULL, newlines, or Unicode. **A proper round-trip test must include delimiters, quotes, backslashes, newlines, NULLs, empty strings, literal markers, and Vietnamese diacritics.**

## 5. HEADER: What Roles Do Column Headers Serve?

A CSV file with a header:

~~~csv
contact_id,full_name,nickname
1,An,
2,Bình,""
~~~

The first row `contact_id,full_name,nickname` contains field names, not data. If PostgreSQL is not told to skip the header, it will attempt to parse the string `contact_id` into the integer column `contact_id` and raise a type conversion error.

### 5.1. HEADER true

~~~sql
COPY copy411.contacts (
    contact_id, full_name, nickname
)
FROM STDIN
WITH (FORMAT csv, HEADER true);
~~~

With `HEADER true`, PostgreSQL **ignores** the first header line. Never interpret this as the server automatically remapping columns based on header text.

### 5.2. HEADER false

~~~sql
COPY copy411.contacts (
    contact_id, full_name, nickname
)
FROM STDIN
WITH (FORMAT csv, HEADER false);
~~~

If the file **has no header**, use `HEADER false` (the default). If you accidentally enable `HEADER true` on a headerless file, PostgreSQL will **discard the first data row** as if it were a header, silently losing a record.

### 5.3. HEADER MATCH

~~~sql
COPY copy411.contacts (
    contact_id, full_name, nickname
)
FROM STDIN
WITH (FORMAT csv, HEADER MATCH);
~~~

With `HEADER MATCH`, PostgreSQL requires the **number and names of header columns to match the target column list in the exact order**. If they do not match, COPY raises an error. This provides a safer format check than simply discarding the first line.

### 5.4. HEADER MATCH Does Not Reorder Columns

File:

~~~csv
full_name,contact_id,nickname
An,1,
~~~

while `COPY (contact_id, full_name, nickname)` expects `contact_id` first and `full_name` second:

- `HEADER true`: skips the header, then tries to insert `An` into integer `contact_id` → error; if column types happen to match, data can **silently swap columns**.
- `HEADER MATCH`: detects the mismatched header names/order and errors early.
- **There is no default mode that automatically maps header "full_name" to its column** regardless of position.

### 5.5. HEADER MATCH Is Only for Import

`HEADER MATCH` is an option for `COPY FROM`. When exporting with `COPY TO`, use `HEADER true` to emit a header line, not `MATCH`.

### 5.6. HEADER on TEXT and CSV

Current PostgreSQL allows `HEADER` on text-based formats (`text` and `csv`) per `COPY` documentation syntax. On systems running **older major versions**, check exact documentation/driver support before using values like `MATCH`. **`HEADER` is not supported for `FORMAT binary`**.

### 5.7. Headers in COPY (query) TO

~~~sql
COPY (
    SELECT
        contact_id AS id,
        full_name AS display_name
    FROM copy411.contacts
    ORDER BY contact_id
)
TO STDOUT
WITH (FORMAT csv, HEADER true);
~~~

The header uses the **query's output column names** (here `id,display_name`), not necessarily the underlying table's physical column names. If later imported into `COPY (contact_id, full_name) ... HEADER MATCH`, note that aliased header names will **not match**.

### 5.8. Headers Are Not Schema Migrations

When a partner adds, removes, or reorders columns in a file, do not just tweak `HEADER true`. Instead:

1. Compare the file schema against the contract;
2. Update the column list or staging mapping accordingly;
3. Use `HEADER MATCH` where appropriate;
4. Test sample data for types, NULLs, and encoding;
5. Version the contract so future loads do not shift meaning.

## 6. DELIMITER: Column Separator Character

PostgreSQL `COPY` supports:

~~~sql
DELIMITER ','
DELIMITER ';'
DELIMITER '|'
DELIMITER E'\t'
~~~

`FORMAT csv` defaults to **comma**. `FORMAT text` defaults to **tab**. `DELIMITER` must be a **single single-byte character in the active encoding**, not a string like `'||'` or a multi-byte UTF-8 character.

### 6.1. Comma-Delimited CSV

~~~csv
contact_id,full_name,nickname
1,An,
2,Bình,""
~~~

~~~sql
COPY copy411.contacts(contact_id, full_name, nickname)
FROM STDIN WITH (FORMAT csv, HEADER true, DELIMITER ',');
~~~

### 6.2. Semicolon-Delimited CSV

~~~csv
contact_id;full_name;nickname
1;An;
2;"Bình; Bé";""
~~~

~~~sql
COPY copy411.contacts(contact_id, full_name, nickname)
FROM STDIN WITH (FORMAT csv, HEADER true, DELIMITER ';');
~~~

Spreadsheet software may export CSV using `;` depending on locale. **CSV does not always use commas**, despite its name. Always inspect real files and the producer's contract.

### 6.3. Delimiter Inside a Value

With `DELIMITER ','`:

~~~csv
1,"An, Nguyễn"
~~~

is two fields: `1` and `An, Nguyễn`. The line:

~~~csv
1,An, Nguyễn
~~~

has **three fields**, not two. When the table expects two columns, `COPY FROM` raises `extra data after last expected column`.

### 6.4. Delimiter Must Not Collide with Quote or Escape

In CSV, delimiter, quote, and escape have distinct roles; the configuration must satisfy `COPY` restrictions. Never pick a delimiter equal to quote, escape, or newline characters. Typically, keep default quote/escape and set the delimiter to match the source file.

### 6.5. Pipes Do Not Eliminate the Need for Quoting

~~~csv
id|name|note
1|"An|Bình"|"Contains | in note"
~~~

With `DELIMITER '|'`, values containing `|` must still be properly quoted. Replacing commas with pipes **does not** let you skip quoting/escaping.

### 6.6. Tabs Are Literal Characters

With `DELIMITER E'\t'`, PostgreSQL expects an **actual tab character/byte**, not the two characters `\` and `t` in the file. Editors often display tabs as multiple spaces; never replace them with spaces casually.

### 6.7. Do Not Guess the Delimiter from a Single Line

If a quoted field contains commas, naive comma counting miscounts columns. Use a **real CSV parser** or inspect via `COPY`/staging rather than assuming the most frequent character in the file is the delimiter.

## 7. QUOTE and ESCAPE in FORMAT CSV

In `FORMAT csv`, defaults are:

~~~sql
QUOTE '"',
ESCAPE '"'
~~~

`QUOTE` is the character enclosing a field; `ESCAPE` is the character preceding quote/escape characters inside a value. When both `QUOTE` and `ESCAPE` are double quotes, literal quotes inside fields are written as **two consecutive double quotes**.

### 7.1. Comma Inside a Field

~~~csv
id,name
1,"An, Nguyễn"
~~~

The `name` value is `An, Nguyễn`, not split into two columns.

### 7.2. Double Quotes Inside a Field

Original value:

~~~text
Bình "Bé"
~~~

CSV representation:

~~~csv
2,"Bình ""Bé"""
~~~

The parser treats `""` inside quotes as **one literal quote**. The opening and closing quotes merely enclose the field and are not part of the string value.

### 7.3. Both Commas and Quotes

Value:

~~~text
Nguyễn "An, Bé"
~~~

CSV:

~~~csv
3,"Nguyễn ""An, Bé"""
~~~

The doubled quotes inside escape the literal quote characters; the comma inside the quoted span **does not split the column**.

### 7.4. QUOTE Different from ESCAPE

~~~sql
WITH (
    FORMAT csv,
    DELIMITER ',',
    QUOTE '"',
    ESCAPE '"'
)
~~~

This is the default pair. PostgreSQL supports a different escape character if agreed upon by the file producer, such as `ESCAPE E'\\'`, but **do not change it arbitrarily**: standard CSV doubles quotes; configuring a mismatch from the source file alters parsing.

### 7.5. QUOTE/ESCAPE Are Only for CSV

Never specify `QUOTE '"'` or `ESCAPE '"'` with `FORMAT text`. TEXT uses **backslash escaping** with its own rules. For binary, CSV options do not apply.

### 7.6. Fields with Actual Newlines

~~~csv
id,note
1,"Line one
Line two"
~~~

This is **one CSV record** with two fields, even though it spans **three physical lines** including the header. A CSV parser knows that newlines inside quotes belong to the field value rather than ending the record.

Never read CSV files using `split('\n')` followed by `split(',')` if the source allows quoted newlines.

### 7.7. Should You FORCE_QUOTE Everything?

`FORCE_QUOTE` in `COPY TO CSV` forces **non-NULL** values to be quoted, improving readability for some files and reducing ambiguity around special strings. However, **NULL remains unquoted** because PostgreSQL must keep NULL distinct from strings matching a marker.

~~~sql
COPY copy411.contacts
TO STDOUT
WITH (FORMAT csv, HEADER true, FORCE_QUOTE *);
~~~

### 7.8. CSV Quotes Are Not SQL Escapes

In:

~~~sql
QUOTE '"'
~~~

the SQL literal `'"'` holds the double-quote character. In CSV data:

~~~csv
"Bình ""Bé"""
~~~

the quotes are **CSV file syntax**. Never confuse SQL string escaping with CSV content escaping.

## 8. SQL NULL vs. Empty Strings: Different Data Meanings

PostgreSQL distinguishes:

| Database Value | Meaning |
| --- | --- |
| `NULL` | No SQL value, unknown/missing state |
| `''::text` | Zero-length string, **not NULL** |
| `'NULL'::text` | Four-character string N-U-L-L |
| `E'\\N'::text` | Two-character string backslash + N |
| `' '::text` | String containing one space |
| `'""'::text` | String containing two literal double quotes |

### 8.1. Direct Inspection

~~~sql
SELECT
    NULL::text IS NULL AS sql_null,
    ''::text IS NULL AS empty_is_null,
    length(''::text) AS empty_length,
    length('NULL'::text) AS marker_word_length,
    length(E'\\N'::text) AS backslash_n_length,
    length(' '::text) AS one_space_length;
~~~

Expected: `sql_null=true`, `empty_is_null=false`, `empty_length=0`, `marker_word_length=4`, `backslash_n_length=2`, `one_space_length=1`.

### 8.2. SQL NULL Is Not the Literal 'NULL'

~~~sql
SELECT
    NULL::text = ''::text AS null_equals_empty,
    NULL::text = 'NULL'::text AS null_equals_word,
    NULL::text IS DISTINCT FROM ''::text AS null_distinct_from_empty;
~~~

Both `=` comparisons with NULL yield SQL NULL (unknown), not true. `IS DISTINCT FROM` provides deterministic semantics even for NULLs; use it for round-trip checks or change detection on nullable columns.

### 8.3. Zero Length Is Not a Missing Field

CSV:

~~~csv
1,An,""
~~~

has **three fields**, where the third field is a **quoted empty string**, not a missing field. Input containing only:

~~~csv
1,An
~~~

is **missing the third field** for a `COPY` expecting three columns and raises a structural error.

### 8.4. Spaces Are Not Automatically Trimmed

~~~csv
1,"  An  "," "
~~~

Spaces inside values are significant; `'  An  '` differs from `'An'`. PostgreSQL CSV does not strip spaces just because a human sees "extra" whitespace. If business logic requires trimming, do it explicitly during staging/transformation.

## 9. Default NULL Representation in FORMAT CSV

**The single most important rule of PostgreSQL CSV:** under default `NULL ''`:

- **Unquoted empty field** → SQL `NULL`.
- **Quoted empty field** `""` → empty string `''`.

### 9.1. Example Table

Assuming the target column type is `text`:

| Field Content in CSV | PostgreSQL Reads As |
| --- | --- |
| *(empty, unquoted)* | SQL NULL |
| `""` | Empty string `''` |
| `" "` | Single-space string |
| `NULL` | String `'NULL'` |
| `"NULL"` | String `'NULL'` |
| `\N` | String `E'\\N'` |
| `"\N"` | String `E'\\N'` |
| `"An, Nguyễn"` | String `'An, Nguyễn'` |

This is **default CSV**; the table changes if you specify `NULL 'NULL'`, `FORCE_NULL`, or `FORCE_NOT_NULL`.

### 9.2. Minimal CSV from STDIN in psql

~~~sql
CREATE TABLE copy411.null_demo (
    id integer PRIMARY KEY,
    val text
);

COPY copy411.null_demo (id, val)
FROM STDIN
WITH (FORMAT csv, HEADER true);
id,val
1,
2,""
3,NULL
4,"NULL"
5," "
6,\N
\.
~~~

This is a **psql-specific script for inline data via COPY FROM STDIN**. Lines from `id,val` through `\.` are the **CSV payload**, not SQL statements; `\.` terminates the input stream in psql.

If running via a GUI or JDBC without inline COPY support, use psql `\copy` with a file or the driver's streaming API. Do not paste data blocks into an arbitrary SQL editor expecting them to behave like normal SQL.

### 9.3. Reading the Results

~~~sql
SELECT
    id,
    val,
    val IS NULL AS is_null,
    length(val) AS char_count
FROM copy411.null_demo
ORDER BY id;
~~~

| id | is_null | Semantic `val` |
| --- | --- | --- |
| 1 | true | SQL NULL |
| 2 | false | Empty string |
| 3 | false | String `NULL` |
| 4 | false | String `NULL` |
| 5 | false | One space |
| 6 | false | String `\N` |

In default CSV, `\N` is **not a NULL marker**. This is a major difference from default COPY TEXT.

### 9.4. On CSV Export, PostgreSQL Preserves the Distinction

When `val` is SQL NULL, `COPY TO CSV` writes an **unquoted empty field**. When `val` is an empty string, it writes `""` so an importer can tell them apart.

~~~sql
COPY (
    SELECT id, val
    FROM copy411.null_demo
    ORDER BY id
)
TO STDOUT
WITH (FORMAT csv, HEADER true);
~~~

When round-tripping with identical format/NULL options, PostgreSQL retains enough information to distinguish NULL from empty strings.

### 9.5. Why "Every Empty Cell Is NULL" Is Dangerous

In a UI form, a user might deliberately **clear a text field to an empty string**; in another context, SQL NULL means "unknown" or "not applicable". If an import silently turns `""` into NULL, queries like:

~~~sql
WHERE val IS NULL
WHERE val = ''
~~~

produce different results, impacting validation, unique constraints, reporting, business logic, and JSON output.

## 10. NULL '...': Choosing a Custom NULL Marker

PostgreSQL allows:

~~~sql
NULL 'NULL'
NULL '\N'
NULL 'N/A'
NULL ''
~~~

`NULL` inside `COPY` options **chooses the file string representing SQL NULL**—it is not SQL `IS NULL` syntax.

### 10.1. CSV with NULL 'NULL'

~~~sql
COPY copy411.null_demo(id, val)
FROM STDIN
WITH (
    FORMAT csv,
    HEADER true,
    NULL 'NULL'
);
id,val
11,NULL
12,"NULL"
13,
14,""
\.
~~~

Because the NULL marker is now `NULL`:

| id | Field in file | Result |
| --- | --- | --- |
| 11 | Unquoted `NULL` | SQL NULL |
| 12 | Quoted `"NULL"` | String `'NULL'` |
| 13 | Unquoted empty | Empty string (does not match marker `NULL`) |
| 14 | Quoted `""` | Empty string |

**Setting `NULL 'NULL'` alters the semantics of empty fields.** Never change the marker without updating the file contract.

### 10.2. CSV Containing a Literal NULL Marker

If an actual data value is the string `NULL`, PostgreSQL `COPY TO CSV WITH (NULL 'NULL')` **quotes it** as `"NULL"` so it is not confused with unquoted SQL NULL.

### 10.3. Avoid Markers That Appear Naturally in Data

Choosing `NULL 'N/A'` looks readable, yet real product text might also contain `N/A`. In CSV, proper quoting separates them; in TEXT, proper escaping does. With external systems that do not quote reliably, a "friendly" marker can corrupt meaning if it collides with real values.

### 10.4. Avoid Coercing NULL to Text Before Export

~~~sql
-- Risks re-importing the wrong meaning if N/A is real data:
SELECT COALESCE(nickname, 'N/A') FROM copy411.contacts;
~~~

This is a **data transformation**, not merely a serialization choice. To preserve SQL NULL, prefer `COPY ... NULL 'N/A'` with compatible parsers, or document the schema contract clearly.

### 10.5. Use Matching Options on Export and Import

~~~sql
COPY copy411.contacts
TO STDOUT
WITH (
    FORMAT csv,
    HEADER true,
    NULL 'NULL'
);
~~~

When re-importing, pass `NULL 'NULL'` along with identical `DELIMITER`/`QUOTE`/`ESCAPE` and column order. Using mismatched markers turns SQL NULLs into literal strings or vice versa.

## 11. FORCE_NOT_NULL: Preserving Empty Fields as Empty Strings

`FORCE_NOT_NULL` applies **only to `COPY FROM` with `FORMAT csv`**. It prevents PostgreSQL from matching values in the selected columns against the NULL marker.

### 11.1. With Default CSV

~~~sql
CREATE TABLE copy411.force_not_null_demo (
    id integer PRIMARY KEY,
    note text
);

COPY copy411.force_not_null_demo (id, note)
FROM STDIN
WITH (
    FORMAT csv,
    HEADER true,
    FORCE_NOT_NULL (note)
);
id,note
1,
2,""
3,NULL
\.
~~~

Because `note` is not checked against the default empty marker:

- id 1: empty string, **not NULL**;
- id 2: empty string, **not NULL**;
- id 3: literal text string `NULL`.

### 11.2. When Is This Useful?

When a CSV source defines empty fields to **always** mean an empty string rather than unknown, `FORCE_NOT_NULL (note)` accurately reflects that contract.

### 11.3. Do Not Apply Recklessly to Numeric or Date Columns

If an empty field enters an `integer` or `date` column under `FORCE_NOT_NULL`, PostgreSQL tries to parse an empty string as a number/date and throws `invalid input syntax`. `FORCE_NOT_NULL` **does not turn empty strings into 0 or a default date**.

### 11.4. Can Target Multiple Columns or *

~~~sql
FORCE_NOT_NULL (note, nickname)
FORCE_NOT_NULL *
~~~

Use `*` only when every column follows this rule. Avoid applying it to numeric, boolean, or date columns that reject empty strings.

### 11.5. FORCE_NOT_NULL Differs from the NOT NULL Constraint

`FORCE_NOT_NULL` is a **CSV decoding rule**, not a SQL constraint. It produces empty text strings, whereas a `NOT NULL` constraint forbids SQL NULL. To forbid empty strings too, add `CHECK` constraints or validation logic.

## 12. FORCE_NULL: Treating Quoted Markers as SQL NULL

`FORCE_NULL` is also restricted to `COPY FROM CSV`. It tells PostgreSQL to match **even quoted values** against the NULL marker and convert matches to SQL NULL.

### 12.1. Example with NULL 'NULL'

~~~sql
CREATE TABLE copy411.force_null_demo (
    id integer PRIMARY KEY,
    note text
);

COPY copy411.force_null_demo (id, note)
FROM STDIN
WITH (
    FORMAT csv,
    HEADER true,
    NULL 'NULL',
    FORCE_NULL (note)
);
id,note
1,NULL
2,"NULL"
3,
4,""
\.
~~~

Expected:

- id 1: unquoted `NULL` → SQL NULL;
- id 2: quoted `"NULL"` → SQL NULL **because of FORCE_NULL**;
- id 3: unquoted empty → empty string;
- id 4: `""` → empty string.

Do not enable `FORCE_NULL` on a column that may legitimately store **real text equal to the marker** if that text must be preserved.

### 12.2. With Default Empty String Marker

If `NULL ''`, `FORCE_NULL (note)` causes both:

~~~csv
,
,""
~~~

in the `note` column to decode as SQL NULL when the column and quote state match the option. At that point, **SQL NULL and empty string can no longer be distinguished** for those inputs.

### 12.3. Do Not Use FORCE_NULL as Trimming or Normalization

`FORCE_NULL` only compares against the **exact marker string** per CSV rules. It does not trim spaces, strip diacritics, fold `'null'` to `'NULL'`, or treat `'N/A'` as NULL unless the marker is `N/A`.

### 12.4. Specify Explicit Columns

If the requirement applies only to `note`, use `FORCE_NULL(note)` rather than altering semantics for the whole file with `FORCE_NULL *`.

## 13. Combining FORCE_NULL and FORCE_NOT_NULL

PostgreSQL allows both options **on the same column**; in that case:

- **Quoted** NULL marker → SQL NULL (via `FORCE_NULL`);
- **Unquoted** NULL marker → regular text value (via `FORCE_NOT_NULL`).

### 13.1. Lab Reversing the Quote Convention

~~~sql
CREATE TABLE copy411.force_both_demo (
    id integer PRIMARY KEY,
    note text
);

COPY copy411.force_both_demo (id, note)
FROM STDIN
WITH (
    FORMAT csv,
    HEADER true,
    NULL 'NULL',
    FORCE_NULL (note),
    FORCE_NOT_NULL (note)
);
id,note
1,NULL
2,"NULL"
3,
4,""
\.
~~~

Expected:

| id | Field | Value in DB |
| --- | --- | --- |
| 1 | Unquoted `NULL` | Text `'NULL'` |
| 2 | Quoted `"NULL"` | SQL NULL |
| 3 | Unquoted empty | Text `''` |
| 4 | Quoted `""` | Text `''` |

### 13.2. When Are Both Needed Together?

This is a specialized case when a source file uses a "**quoted sentinel means NULL**" convention opposite to PostgreSQL's default CSV rules. For standard pipelines, normalize sources to clearer rules and avoid confusing combinations unless required.

### 13.3. Round-Trip Consistency Note

If you import with both `FORCE_NULL` and `FORCE_NOT_NULL`, then export using standard COPY CSV rules, the exported file **may quote fields differently** than the original even though stored values match. Systems requiring byte-for-byte preservation need raw file archival or custom serialization.

## 14. FORCE_QUOTE: When Exporting CSV

`FORCE_QUOTE` applies only to **`COPY TO` with `FORMAT csv`**, affecting **non-NULL values** in the specified columns.

### 14.1. Example

~~~sql
COPY (
    SELECT contact_id, full_name, nickname
    FROM copy411.contacts
    ORDER BY contact_id
)
TO STDOUT
WITH (
    FORMAT csv,
    HEADER true,
    FORCE_QUOTE *
);
~~~

With `FORCE_QUOTE *`, non-NULL values are enclosed in `"..."` even when they contain no delimiters, quotes, or newlines. However, **SQL NULL is still emitted unquoted** per the NULL marker to preserve its meaning.

### 14.2. Selecting Specific Columns

~~~sql
COPY copy411.contacts (
    contact_id, full_name, nickname
)
TO STDOUT
WITH (
    FORMAT csv,
    HEADER true,
    FORCE_QUOTE (full_name, nickname)
);
~~~

### 14.3. FORCE_QUOTE Is Neither Encryption Nor Data Protection

Quoting helps parsers detect field boundaries. It does **not** encrypt sensitive data, stop spreadsheets from executing formulas, or prevent SQL injection.

### 14.4. Exporting CSV for Excel

Excel or spreadsheet software can auto-infer types, strip leading zeros from product codes, reformat dates by locale, or evaluate fields starting with `=` as formulas. `FORCE_QUOTE` does not ensure spreadsheets treat fields safely as plain text. Evaluate spreadsheet export policies, import-as-text guidance, and CSV formula injection defenses based on your threat model.

## 15. Summary Matrix of CSV NULL Decoding

Assume the column type is `text`:

| CSV field | Default `NULL ''` | `NULL 'NULL'` | `NULL 'NULL', FORCE_NULL` | `NULL 'NULL', FORCE_NOT_NULL` | Combined |
| --- | --- | --- | --- | --- | --- |
| Unquoted empty | SQL NULL | `''` | `''` | `''` | `''` |
| `""` | `''` | `''` | `''` | `''` | `''` |
| Unquoted `NULL` | `'NULL'` | SQL NULL | SQL NULL | `'NULL'` | `'NULL'` |
| Quoted `"NULL"` | `'NULL'` | `'NULL'` | SQL NULL | `'NULL'` | SQL NULL |

*Assumes `FORCE_NULL`/`FORCE_NOT_NULL` is applied to the column in question. Specifying other columns leaves this column's behavior unchanged.*

### 15.1. This Is a Design Step, Not an Ad-Hoc Fix After Errors

Choose the NULL marker and FORCE options before importing based on the **data contract**. Changing markers ad hoc after every error produces inconsistent semantics across batches.

### 15.2. Distinguishing NULL from DEFAULT

SQL NULL **differs** from a column's default. If a file provides a NULL marker for a column that has a default, PostgreSQL loads SQL NULL (and checks constraints)—it does **not** automatically substitute the default.

If a column is **omitted from the `COPY FROM` column list**, PostgreSQL applies the column's default to imported rows. Newer versions also support a `DEFAULT '...'` option to recognize an explicit marker for defaults on import, which is separate from NULL.

### 15.3. Do Not Use Empty-String Workarounds on Required Columns

A `NOT NULL` column encountering an unquoted empty CSV field under default `NULL ''` violates NOT NULL. That may be a legitimate source data error. Do not hastily add `FORCE_NOT_NULL` to "get past the error" if business rules actually forbid blank values.

## 16. FORMAT TEXT: Not "CSV Without Quotes"

`FORMAT text` is PostgreSQL COPY's default format. Each row normally occupies one physical line, with fields separated by **tab** by default. Control and special characters are written using **backslash sequences**.

### 16.1. Default

~~~sql
COPY copy411.contacts
TO STDOUT
WITH (FORMAT text);
~~~

A TEXT file has no CSV quoting semantics; PostgreSQL uses `\N` for SQL NULL, and special characters are escaped per text rules.

### 16.2. TEXT with a Custom DELIMITER

For readability in examples, let's use pipe `|` instead of tab:

~~~sql
COPY copy411.contacts(contact_id, full_name, nickname, note)
TO STDOUT
WITH (
    FORMAT text,
    DELIMITER '|',
    NULL E'\\N'
);
~~~

When a value contains `|`, COPY TEXT represents it as `\|` so it is not confused with the delimiter. **Never use CSV double quotes to protect pipes in TEXT**—that is a different mechanism.

### 16.3. COPY TEXT Escape Table

| Value to Represent | In TEXT File | Meaning on COPY FROM TEXT |
| --- | --- | --- |
| Literal newline | `\n` | Line feed character |
| Carriage return | `\r` | Carriage return character |
| Tab | `\t` | Tab character |
| Backslash | `\\` | Single backslash |
| Backspace | `\b` | Backspace character |
| Form feed | `\f` | Form feed character |
| Vertical tab | `\v` | Vertical tab character |
| Delimiter `\|` when DELIMITER is `\|` | `\|` | Literal `\|` inside field |
| Octal/hex escape | Per COPY TEXT syntax | Single valid character/byte in encoding |

Sequences like `\n`, `\t`, and `\\` in this table are **literal backslash characters in the file**, not instructions to press Enter or Tab inside a record.

### 16.4. Inline COPY TEXT Example with Pipe

~~~sql
CREATE TABLE copy411.text_demo (
    id integer PRIMARY KEY,
    name text,
    note text
);

COPY copy411.text_demo (id, name, note)
FROM STDIN
WITH (FORMAT text, DELIMITER '|', NULL E'\\N');
1|An|Hello\nWorld
2|Bình|\N
3|Chi|\\N
4|Dũng|a\|b
5|Em|C:\\temp\\report.txt
\.
~~~

Execute this block in **psql** using inline data mode. Do not treat lines like `1|An|...` as SQL statements.

### 16.5. Results

~~~sql
SELECT
    id,
    name,
    note,
    note IS NULL AS is_null,
    position(E'\n' IN note) > 0 AS contains_newline
FROM copy411.text_demo
ORDER BY id;
~~~

- id 1: `note` spans two lines, with the newline decoded from `\n`.
- id 2: `note` is SQL NULL per the `\N` marker.
- id 3: `note` is literal string `\N`, because the file contained `\\N`.
- id 4: `note` is `a|b`, not split into extra columns.
- id 5: `note` is `C:\temp\report.txt`, without turning `\t`/`\r` into tab/CR because the backslashes were escaped.

### 16.6. TEXT NULL Is Recognized Before Unescaping

This is a critical rule:

~~~text
Field \N  → matched against NULL marker first → SQL NULL
Field \\N → does not match \N marker → unescaped → text \N
~~~

Conversely, if a custom parser "unescapes first and checks the NULL marker second", both fields would look identical and **real data would be lost**.

### 16.7. Values Are Not CSV-Quoted

A TEXT field containing:

~~~text
"An, Nguyễn"
~~~

If the file literally contains double quotes, COPY TEXT **stores them as data characters** (subject to escape interactions), rather than stripping them like a CSV parser. Conversely, CSV treats enclosing quotes as file syntax.

### 16.8. Why SQL E-Strings and TEXT Escapes Are Easily Confused

When writing SQL:

~~~sql
NULL E'\\N'
~~~

PostgreSQL parses `E'\\N'` into the **string consisting of backslash + N** as the NULL option. Later, when COPY reads the TEXT file:

~~~text
\N
~~~

the parser recognizes that marker as SQL NULL. These are **two separate parsing layers**:

1. The SQL parser handles the `COPY WITH (...)` statement.
2. The COPY TEXT parser handles the file payload.

Do not conclude from SQL needing `E'\\N'` that the file must write `\\N` for NULL: **the file uses `\N` by default**.

### 16.9. NUL Bytes and Binary Data

PostgreSQL `text` cannot store NUL (`\0`) bytes in regular text values. If you must transport arbitrary bytes, evaluate `bytea` and source encoding; never treat COPY TEXT/CSV as an arbitrary transport for raw bytes including NUL.

## 17. How CSV Differs from TEXT on Backslashes

Suppose a file contains the field:

~~~text
C:\temp\new
~~~

### 17.1. In Default CSV

~~~csv
1,C:\temp\new
~~~

Backslashes carry no special escape meaning as in TEXT, so the parsed value is `C:\temp\new`.

### 17.2. In Default TEXT

~~~text
1|C:\temp\new
~~~

If text format uses `DELIMITER '|'`, `\t` in `\temp` becomes a tab and `\n` in `\new` becomes a newline. The value is **no longer the original path**.

### 17.3. Correct Representation for TEXT

~~~text
1|C:\\temp\\new
~~~

Each literal backslash is written `\\`. On `COPY FROM TEXT`, it decodes back to a single backslash in the stored string.

### 17.4. Never Infer FORMAT from File Extension

A filename `data.txt` does not guarantee PostgreSQL COPY TEXT format. A `data.csv` file might use `;` delimiters or custom quote/backslash dialects. Format **must come from a serialization contract**, not the filename extension.

## 18. The \. Marker and Ending COPY FROM STDIN

In psql, when entering inline data for:

~~~sql
COPY copy411.null_demo (id, val)
FROM STDIN
WITH (FORMAT csv);
~~~

psql must know where the data ends. The line:

~~~text
\.
~~~

acts as the **end-of-data marker** for inline `COPY FROM STDIN`.

### 18.1. CSV and Literal \. Values

If real data contains the literal string `\.` alone on a record, it could be mistaken for the end marker in inline psql. In CSV, quoting that text field writes it as:

~~~csv
"\."
~~~

Still, when feeding inline psql, you must account for how psql detects the marker line; prefer proper file streams or test this edge case explicitly.

### 18.2. Differences Across PostgreSQL Major Versions

Current PostgreSQL documentation notes a historical change: **prior to PostgreSQL 18**, an unquoted `\.` on its own line could be treated as an end marker even when reading CSV from a standalone file. **PostgreSQL 18** changed this behavior for CSV files, while inline `COPY FROM STDIN` in psql still relies on `\.`. When real data can contain `\.` on its own line, test on the **exact target major version**.

### 18.3. Do Not Insert \. into CSV Files Out of Habit

With `\copy ... FROM 'file.csv'`, end-of-file already defines end-of-input; do not manually append `\.` to CSV data files, as it can create extra records or behave differently across versions. Let producers and consumers follow standard format/protocol rules.

## 19. Multiline CSV, CRLF/LF, and "Line Counts"

### 19.1. One Record Can Span Multiple Physical Lines

~~~csv
id,note
1,"Line 1
Line 2"
2,"Line 3"
~~~

This file has **two data records**, even though a text editor shows **four physical lines** including the header. Never count newline bytes minus one to claim the number of CSV records.

### 19.2. When Does a Newline End a Record?

In CSV, a newline **outside a quoted field** terminates a record. A newline **inside a quoted field** is part of the field value. Parsers must track quote/escape state across lines.

### 19.3. COPY TEXT Normally Uses \n Escapes

COPY TEXT is designed around one row per line; embedded newlines should be written as `\n` rather than physical line breaks inside fields. PostgreSQL recommends serializing carriage returns and newlines as `\r` and `\n` for portability.

### 19.4. File Line Endings

Common formats:

- Unix LF: byte `0A`;
- Windows CRLF: bytes `0D 0A`;
- Legacy CR: byte `0D`.

PostgreSQL handles supported line endings, yet **mixing styles inconsistently** can cause errors—especially if fields contain unquoted/unescaped newlines.

### 19.5. Multiline Data Can Make Line Numbers Misleading

`COPY ... line N` error messages generally refer to line positions in the input stream, not necessarily "record N minus header" when records span multiple physical lines. Debugging multiline CSVs requires parser-aware record tracking.

### 19.6. Whitespace Outside Quotes

CSV:

~~~csv
1, "An"
~~~

has a space before `"`. Never assume a parser will strip that space and treat the field as `"An"`. PostgreSQL CSV treats characters literally; whitespace adjacent to quoted fields may behave differently than a producer expects. If a source pads spaces, apply deterministic preprocessing rather than ad-hoc manual edits.

## 20. Vietnamese Encoding, BOMs, and Code Points

A CSV with valid delimiters and quotes can still corrupt Vietnamese text if encoding is mismatched.

### 20.1. UTF-8

For data like:

~~~csv
id,name
1,Nguyễn Văn An
2,Trần Thị Bình
~~~

standardize on producers emitting **UTF-8** and PostgreSQL/clients reading the same encoding.

### 20.2. ENCODING in COPY

Modern PostgreSQL supports:

~~~sql
COPY copy411.contacts (
    contact_id, full_name, nickname
)
FROM STDIN
WITH (
    FORMAT csv,
    HEADER true,
    ENCODING 'UTF8'
);
~~~

`ENCODING` specifies how file/stream bytes are decoded or written. When omitted, COPY uses the client encoding per PostgreSQL semantics. Check version-specific support and options when working with older servers.

### 20.3. Checking Database and Client Encoding

~~~sql
SHOW server_encoding;
SHOW client_encoding;
~~~

Database and client encodings can differ cleanly via conversion, provided the file's actual encoding is declared accurately. If source bytes are actually Windows-1258 or UTF-16 but labeled UTF-8, loading fails or yields mojibake.

### 20.4. BOM

Some tools write a UTF-8 **BOM** at the start of a file. If a pipeline does not handle it, the BOM appears as `U+FEFF` before the first header/field, turning the first header name into `\uFEFFid` instead of `id`.

Never assume every server or tool strips BOMs automatically. When `HEADER MATCH` fails even though headers look identical, inspect the leading bytes for a BOM and normalize inputs in a controlled pipeline step.

### 20.5. Unicode Normalization

Two visually identical Vietnamese strings can have different Unicode representations (precomposed vs. combining characters). COPY is **not a Unicode normalizer**. If business matching requires canonical Unicode normalization, enforce a versioned, verified normalization step rather than expecting CSV import to normalize names.

### 20.6. Never Choose a Multi-Byte Delimiter

PostgreSQL requires `DELIMITER` to be a **single-byte** character. Even when using UTF-8 with Vietnamese data, you cannot pick `'。'` or a multi-byte Vietnamese character as a COPY delimiter.

### 20.7. Checking DateStyle and Date Formats

~~~sql
SET DateStyle = ISO;
~~~

When exporting/importing dates and times, `DateStyle` and timezones affect formatting. For interchange files, prefer unambiguous ISO formats and timestamps with timezones; never rely on spreadsheet locale displays like `03/04/2026` to guess March 4 vs. April 3.

### 20.8. CSV Fields Are Strings; Types Are Parsed Later

A CSV field `"000123"` arrives as text payload when decoded by the CSV parser; if the target column is `integer`, PostgreSQL converts it to `123` and drops leading zeros per the **column type**. Use `text` or `varchar` for customer codes/SKUs when leading zeros matter.

## 21. Exporting CSV with \copy in psql

Suppose you run psql on a client machine, hold `SELECT` on the lab table, and want to produce a file for another system.

### 21.1. Export with Header and Explicit Rules

~~~text
\copy (SELECT contact_id, full_name, nickname, note, active, created_at FROM copy411.contacts ORDER BY contact_id) TO 'contacts_export.csv' WITH (FORMAT csv, HEADER true, DELIMITER ',', NULL '')
~~~

This is a **psql meta-command**, not terminated by a `;` like regular SQL. Depending on psql version, `\copy` syntax and path quoting follow specific rules; check psql help and OS conventions for real paths.

### 21.2. Why Add ORDER BY?

`COPY table TO` does not guarantee ID ordering unless you export a query with `ORDER BY`. When reproducible files are needed for diffing across exports, use `COPY (SELECT ... ORDER BY ...) TO` with deterministic tie-breakers.

### 21.3. Specify an Explicit Column List

If a migration adds a column to a table, `COPY table TO` without a column list changes the field count and layout. Listing columns explicitly in integration contracts reduces silent schema breakage.

### 21.4. Export Only Permitted Data

~~~text
\copy (SELECT contact_id, full_name FROM copy411.contacts WHERE active = true ORDER BY contact_id) TO 'contacts_active.csv' WITH (FORMAT csv, HEADER true)
~~~

The query controls which rows and columns are exported. Never assume an app role needs `SELECT` on every column; enforce grants, RLS, and data minimization on outbound files.

### 21.5. The File Resides on the Client Machine

With `\copy ... TO 'contacts_export.csv'`, relative paths resolve against the **psql client's** working directory. The server does not write this file in its data directory. If psql runs on another host, the file resides there—not magically on your laptop.

### 21.6. If Server-Side COPY Is Needed

~~~sql
COPY (
    SELECT contact_id, full_name
    FROM copy411.contacts
    ORDER BY contact_id
)
TO '/approved/server/export/contacts.csv'
WITH (FORMAT csv, HEADER true);
~~~

This writes a file on the **server** and requires server-file privileges. It is inappropriate for low-privilege application roles simply downloading CSVs; use `STDOUT`/`\copy` or streaming APIs for client downloads.

## 22. Importing CSV with \copy While Preserving Semantics

Assume `contacts_export.csv` was exported following the 6-column structure of `copy411.contacts`.

### 22.1. Creating a Separate Target Table

~~~sql
CREATE TABLE copy411.contacts_roundtrip (
    LIKE copy411.contacts INCLUDING ALL
);
~~~

In the lab, the source table's constraints and defaults clone cleanly via `LIKE ... INCLUDING ALL`. In production, cloning constraints/indexes/defaults does not replace proper schema migrations or compatibility reviews.

### 22.2. Importing with Matching Options

~~~text
\copy copy411.contacts_roundtrip (contact_id, full_name, nickname, note, active, created_at) FROM 'contacts_export.csv' WITH (FORMAT csv, HEADER MATCH, DELIMITER ',', NULL '')
~~~

When your PostgreSQL/psql version supports `HEADER MATCH` and the header matches the column order, COPY verifies the header before loading rows. If the file lacks headers or uses aliased column names, align the contract rather than blindly disabling validation.

### 22.3. Checking Row Counts

~~~sql
SELECT
    (SELECT COUNT(*) FROM copy411.contacts) AS source_rows,
    (SELECT COUNT(*) FROM copy411.contacts_roundtrip) AS target_rows;
~~~

Matching counts are a **necessary condition**, not proof of data equivalence. Two text columns like `nickname` and `note` could be swapped if `HEADER true` skipped an undetected header mismatch.

### 22.4. Comparing Values Including NULLs

~~~sql
SELECT
    s.contact_id,
    s.full_name AS original_name,
    t.full_name AS reimported_name,
    s.nickname IS NOT DISTINCT FROM t.nickname
        AS nickname_equal_including_null,
    s.note IS NOT DISTINCT FROM t.note
        AS note_equal_including_null,
    s.active IS NOT DISTINCT FROM t.active
        AS active_equal_including_null,
    s.created_at IS NOT DISTINCT FROM t.created_at
        AS date_equal_including_null
FROM copy411.contacts AS s
FULL OUTER JOIN copy411.contacts_roundtrip AS t
    ON s.contact_id = t.contact_id
ORDER BY COALESCE(s.contact_id, t.contact_id);
~~~

For thorough verification, compare every column, detect missing/extra rows, and use **NULL-safe** comparisons.

### 22.5. Using EXCEPT to Compare Datasets

~~~sql
(
    SELECT *
    FROM copy411.contacts
    EXCEPT
    SELECT *
    FROM copy411.contacts_roundtrip
)
UNION ALL
(
    SELECT *
    FROM copy411.contacts_roundtrip
    EXCEPT
    SELECT *
    FROM copy411.contacts
);
~~~

When schemas and data match under `EXCEPT` semantics, the result is empty. On tables without unique keys or with duplicate rows, `EXCEPT` removes duplicates by default; use `EXCEPT ALL` or grouped count comparisons when multiplicity matters.

### 22.6. File Hashes Do Not Replace Logical Verification

File checksums detect byte corruption in transit, yet two CSV files with different bytes can hold **identical data** (differing line endings or quoting), while identical bytes imported with **different NULL/DELIMITER options** produce different table data. You need both artifact checksums and logical schema/value verification.

## 23. COPY FROM STDIN with Inline CSV and Practical Limits

When running psql directly, you can create a table and load inline data:

~~~sql
CREATE TABLE copy411.inline_contacts (
    id integer PRIMARY KEY,
    name text,
    note text
);

COPY copy411.inline_contacts(id, name, note)
FROM STDIN
WITH (FORMAT csv, HEADER true, DELIMITER ',');
id,name,note
1,"An, Nguyễn","Comma inside cell"
2,"Bình ""Bé""","Contains quotes"
3,Chi,
4,Dũng,""
\.
~~~

### 23.1. Expected Results

| id | name | note |
| --- | --- | --- |
| 1 | `An, Nguyễn` | `Comma inside cell` |
| 2 | `Bình "Bé"` | `Contains quotes` |
| 3 | `Chi` | SQL NULL |
| 4 | `Dũng` | Empty string |

### 23.2. Why Is \. Needed?

In inline psql, `\.` tells the client to finish sending CSV lines for `COPY FROM STDIN`. In Java/JDBC, the driver supplies data via the **COPY protocol API**; `\.` is not universally treated as a standalone SQL command across APIs.

### 23.3. SQL INSERT vs. COPY Input

For tiny datasets, `INSERT INTO ... VALUES (...)` is simpler to control. For hundreds of thousands of rows from files, `COPY` cuts overhead and raises throughput, provided delimiter/NULL/schema contracts and permission/transaction controls are in place.

### 23.4. Never Submit a CSV File as a Plain SQL Statement

`COPY ... FROM STDIN` only initiates data transfer mode. The driver must switch to the COPY protocol rather than running a SQL string followed by ad-hoc `INSERT`s or raw text payloads. In Java PostgreSQL JDBC, use `CopyManager`/`PGConnection` APIs and manage streams, encoding, and errors per driver docs.

## 24. Using Staging Tables to Separate Parsing from Business Validation

For external files, avoid loading directly into business tables until schema, delimiters, NULLs, and data quality are verified.

### 24.1. Recommended Pipeline

~~~text
CSV/TSV Source
  |
  +-- Verify metadata: checksum, encoding, version, schema
  |
  +-- Parse CSV/TEXT per fixed contract
  |
  +-- COPY into staging with text columns
  |
  +-- Validate names, types, dates, NULL/empty
  |
  +-- Store rejected rows and reasons
  |
  +-- INSERT ... SELECT with type casts into target table
  |
  +-- Reconcile accepted/rejected counts and confirm batch
~~~

### 24.2. Staging Table

~~~sql
CREATE TABLE copy411.contact_stage (
    import_row_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    contact_id_text text,
    full_name_text text,
    nickname_text text,
    note_text text,
    active_text text,
    created_at_text text,
    imported_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
~~~

With all data fields staged as text, values like `'not-a-date'` load cleanly for inspection instead of immediately aborting COPY on date parsing; **however**, structural CSV errors, bad encoding, or broken quoting still cause COPY to fail.

### 24.3. Explicit Column List for Staging

~~~text
\copy copy411.contact_stage (contact_id_text, full_name_text, nickname_text, note_text, active_text, created_at_text) FROM 'contacts_export.csv' WITH (FORMAT csv, HEADER true, DELIMITER ',', NULL '')
~~~

Here the exported file header is `contact_id,full_name,...`, while staging columns end in `_text`. Hence **`HEADER true`** skips the header, whereas `HEADER MATCH` would **fail** on name mismatch. This is a deliberate trade-off when staging; to use `MATCH`, match staging column names to the contract or verify headers in a separate step.

### 24.4. Inspecting Staged Input

~~~sql
SELECT
    import_row_id,
    contact_id_text,
    full_name_text,
    created_at_text,
    nickname_text IS NULL AS nickname_missing,
    nickname_text = '' AS nickname_empty
FROM copy411.contact_stage
ORDER BY import_row_id
LIMIT 20;
~~~

### 24.5. Date Errors Must Not Be Silently Coerced

If date inputs might be `DD/MM/YYYY` or `MM/DD/YYYY`, do not blindly run `created_at_text::date` hoping `DateStyle` matches. Define explicit format parsing rules, validate numbers/dates, log rejected rows, and keep raw inputs for investigation.

### 24.6. Keep Raw Values Separate from Normalized Values

Staging should preserve enough raw information for debugging: for example, `nickname_text IS NULL` vs. `nickname_text = ''` must stay intact. Calling `COALESCE(nickname_text, '')` immediately upon ingestion destroys original NULL information.

### 24.7. Reconciling Counts

~~~sql
SELECT COUNT(*) AS staged_rows
FROM copy411.contact_stage;
~~~

Combine with:

~~~text
total source data records
  = parsed/staged records + rejected parse records

staged records
  = accepted transform rows + rejected validation rows
~~~

Remember that for CSVs with quoted newlines, "source data records" does **not** necessarily equal "physical lines minus one header".

### 24.8. Controlling Duplicates

If the same file is re-imported, prevent `INSERT` from creating duplicates or unintentionally overwriting existing records. Use batch IDs/file checksums, partitioned staging, unique keys, transactions, reviewed `ON CONFLICT` logic, and accepted/rejected reconciliation before publishing results.

## 25. Common Errors When HEADER or DELIMITER Is Wrong

### 25.1. invalid input syntax for type integer

~~~text
ERROR: invalid input syntax for type integer: "contact_id"
~~~

Common cause: the file has a header, but `HEADER true` was not enabled. PostgreSQL tries to parse the column name into an integer.

**Fix:** confirm the file has a header and enable `HEADER true` or `HEADER MATCH`.

### 25.2. extra data after last expected column

~~~text
ERROR: extra data after last expected column
~~~

Possible causes: unquoted delimiter inside a field, wrong `DELIMITER`, wrong format selected, or unexpected extra columns in the file.

**Fix:** verify field counts per record, use a proper CSV parser, check the schema contract, and inspect quoted delimiters/newlines.

### 25.3. missing data for column

~~~text
ERROR: missing data for column "note"
~~~

A record has fewer fields than expected, such as a missing trailing delimiter. Never confuse an **empty field** with a **missing field**:

~~~csv
1,An,
~~~

has three fields; whereas:

~~~csv
1,An
~~~

has only two fields.

### 25.4. unterminated CSV quoted field

~~~csv
1,"An
~~~

The file ended before a quote closed (or quotes/escapes are malformed), so PostgreSQL cannot determine where the field or record ends.

### 25.5. Wrong Header Order Without an Error

If two columns are both `text` and the file swaps their order while importing with `HEADER true`, PostgreSQL succeeds while **loading values into the wrong columns**. This silent data quality bug is far worse than a syntax error.

### 25.6. Semicolon CSV Imported as Comma-Delimited

~~~csv
id;name;note
1;An;Hello
~~~

If the parser expects commas, each line looks like **a single field**, leading to missing-column or conversion errors.

### 25.7. NULL Turning into Empty String

If imported with `FORCE_NOT_NULL` against the contract, unquoted empty fields become `''` instead of SQL NULL. Queries using `IS NULL` suddenly return fewer rows.

### 25.8. Empty String Turning into NULL

If `FORCE_NULL` is used with an empty marker on a text column that legitimately uses empty strings, quoted `""` also turns into NULL, losing the distinction.

### 25.9. \N Misinterpreted

If a file is actually COPY TEXT but imported as CSV, `\N` does not mean SQL NULL under default CSV rules. Conversely, if a CSV containing path backslashes is imported as TEXT, sequences like `\t` or `\n` get turned into tabs or newlines.

### 25.10. Vietnamese Encoding Errors

If UTF-8 bytes are decoded using another encoding or a BOM alters a header name, `HEADER MATCH` fails or names become corrupted. Inspect encoding and raw bytes—never tweak SQL delimiters to fix an encoding bug.

## 26. Can COPY FROM Skip Invalid Rows?

**By default**, when `COPY FROM` encounters an error, the statement aborts. Modern PostgreSQL provides options to handle type conversion errors:

~~~sql
ON_ERROR stop
ON_ERROR ignore
~~~

PostgreSQL versions predating this feature reject the syntax. **Verify your major version** before using `ON_ERROR`, `REJECT_LIMIT`, and `LOG_VERBOSITY`.

### 26.1. ON_ERROR ignore Has a Narrow Scope

Per current PostgreSQL documentation, `ON_ERROR ignore` is supported for `COPY FROM` in `text`/`csv` formats to **skip rows that fail column input type conversion**.

Never assume it skips **all errors**:

- Broken CSV quotes/delimiters can prevent record boundary detection.
- Constraint violations follow separate semantics and are not mere type conversion errors.
- Permission errors, file errors, encoding errors, or server errors do not turn into simple row rejections.
- Triggers can raise business exceptions outside conversion handling.

### 26.2. REJECT_LIMIT

~~~sql
COPY copy411.contacts (
    contact_id,
    full_name,
    nickname,
    note,
    active,
    created_at
)
FROM STDIN
WITH (
    FORMAT csv,
    HEADER true,
    ON_ERROR ignore,
    REJECT_LIMIT 5
);
~~~

`REJECT_LIMIT` caps the number of tolerated conversion errors when using `ON_ERROR ignore`. If errors exceed the limit, COPY fails. On PostgreSQL versions lacking this option, implement staging, validation, or driver-level rejection flows instead.

### 26.3. LOG_VERBOSITY

Modern documentation lets you configure logging for ignored rows, such as `default`, `verbose`, or `silent`. `verbose` logs the line and column encountering conversion errors; `silent` suppresses notices. This is an **observability setting**, not an input validation tool.

### 26.4. Why Never Enable Unlimited Ignore?

If a source has 100,000 records and only 40,000 load due to malformed dates, a COPY completing without reconciliation leaves a **silently incomplete table**. Always:

1. Define a reject budget;
2. Save rejected/raw rows or emit an error report;
3. Compare source record counts with accepted + rejected counts;
4. Block batch publication if the error rate exceeds thresholds;
5. Fix the source or transformation properly rather than ignoring errors silently.

### 26.5. When COPY Fails Mid-Stream

If `COPY FROM` aborts on error, rows already processed by the statement are rolled back transactionally; however, they can leave dead tuples requiring VACUUM to reclaim disk space. Never assume a rolled-back table consumed zero **disk space** just because queries see no rows.

### 26.6. Distinguish Error Classes

| Error Class | Example | Typical Resolution |
| --- | --- | --- |
| CSV parse | Unclosed quote | Fix or reject invalid file |
| Field count | Missing/extra columns | Check HEADER/DELIMITER/column list |
| Encoding | Undecodable bytes | Verify encoding / transcode properly |
| Type cast | `'abc'` into integer | Text staging & validation; or `ON_ERROR` per version |
| Constraint | Duplicate key, NOT NULL | Fix data/model, controlled dedup/merge |
| Trigger | `RAISE EXCEPTION` in trigger | Review business rules |
| Privilege | permission denied | Grant proper INSERT/SELECT or use `\copy` |
| System | Disk full / timeout | Ops runbook, transaction/retry |

## 27. COPY FROM and Triggers, Constraints, and RLS

### 27.1. INSERT Triggers Can Fire

`COPY FROM` fires applicable triggers and evaluates check constraints on the target table per PostgreSQL semantics. A row-level `BEFORE INSERT` trigger can normalize values and an `AFTER` trigger can write audit logs—this also adds overhead on large loads.

### 27.2. COPY FROM Does Not Execute Rules as Many Expect

Per PostgreSQL documentation, `COPY FROM` fires triggers and check constraints, yet does not invoke query rewrite rules like a normal `INSERT`. If a legacy system relies on rewrite rules during inserts, test thoroughly before replacing `INSERT` with `COPY`.

### 27.3. RLS

`COPY TO` respects `SELECT` policies for read access. For `COPY FROM` into tables with Row-Level Security enabled, current PostgreSQL documents a restriction: **`COPY FROM` is not supported on tables with RLS enabled**, so use `INSERT` statements when policies must be enforced. Never disable RLS in production just for faster loads.

### 27.4. NOT NULL / CHECK / UNIQUE Still Matter

NULL serialization/parsing rules do not replace business constraints:

~~~sql
CREATE TABLE copy411.required_demo (
    code text PRIMARY KEY,
    note text NOT NULL
);
~~~

If default CSV contains an unquoted empty `note`, PostgreSQL parses it as SQL NULL and the `NOT NULL` constraint rejects it. Enabling `FORCE_NOT_NULL` lets empty string `''` through, so add `CHECK` constraints if blank text is also disallowed.

### 27.5. COPY and Identity Columns

When an identity column appears in the `COPY FROM` column list, PostgreSQL semantics load the supplied values instead of auto-generating new ones per `COPY` documentation. When importing external IDs, establish policies for key collisions, sequence synchronization, and permissions beforehand.

### 27.6. Never Drop Constraints to Reduce Import Errors

Files with bad data belong in staging and source remediation. Disabling triggers/checks or loosening schema constraints so COPY "succeeds" lets production data violate invariants, causing much harder problems later.

## 28. CSV File Security and Exported Data

### 28.1. CSV Does Not Encrypt Data

`FORMAT csv` files are plain text readable in any editor; if they hold emails, phone numbers, addresses, or customer data, control storage, transit, and access permissions. Neither `QUOTE` nor `FORCE_QUOTE` provides encryption.

### 28.2. CSV Formula Injection

User-generated text fields can start with characters that some spreadsheet applications evaluate as formulas, such as `=`, `+`, `-`, `@`, or variants with leading whitespace/control characters.

Example database value:

~~~text
=1+1
~~~

When exported to CSV and opened in a spreadsheet, the software may **evaluate it as a formula** instead of plain text, depending on the application and settings.

`FORCE_QUOTE` **does not prevent formula injection**: spreadsheets can still evaluate values after stripping CSV quotes. For spreadsheet-bound exports, apply security-approved neutralization and test in the actual target software, or export in formats with explicit text cell types rather than raw CSV.

### 28.3. Never Use CSV Escaping to Prevent SQL Injection

SQL queries and connection APIs must use placeholders/prepared statements. CSV quoting only helps CSV parsers find field boundaries; a properly CSV-quoted field can still be dangerous if application code concatenates it into SQL.

### 28.4. Do Not Grant Broad Server-File Read Privileges to Apps

If an app only needs to download data, use `COPY ... TO STDOUT` or a protected export API—never grant `pg_read_server_files`/superuser or expose arbitrary server paths.

### 28.5. PII in Test Files

In labs, use synthetic names. When debugging real production issues, never share raw CSVs containing personal data over unauthorized support channels or logs; build a sanitized reproducer that reproduces quote/NULL issues without PII.

### 28.6. Path Permissions with \copy

`\copy` reads/writes files as the **OS user running psql**. Having `INSERT`/`SELECT` on the database role does not imply OS file read/write permission for the client path; verify both permission layers.

## 29. Key Differences Between PostgreSQL and Spreadsheet Software

| Issue | PostgreSQL COPY CSV | Possible Spreadsheet Behavior |
| --- | --- | --- |
| NULL vs. empty | Distinguishes unquoted empty from `""` by default | May merge both upon opening/saving |
| Data types | Parses per table column types | May auto-infer types by locale |
| Leading zeros | Preserved in text columns | May strip if treated as numbers |
| Dates | Per PostgreSQL input functions / DateStyle | May swap day/month silently |
| Quotes | Strict CSV grammar | May export with custom dialect |
| Line endings | Supports quoted multiline CSV | May alter line breaks on re-save |
| Delimiter | Explicit single-byte character | May follow locale `,` vs. `;` |
| Formula-like text | COPY strictly serializes data | May execute as formulas |
| Encoding | `ENCODING` / client encoding | May add BOM or save different encoding |

**Never treat opening and re-saving a CSV in a spreadsheet as a harmless step.** After re-saving, re-verify against the data contract—especially NULLs, leading zeros, dates, embedded newlines, and encoding.

## 30. Choosing the Right Import/Export Format

### 30.1. CSV Is Appropriate When

- Exchanging with Excel, BI, ETL, or tools with standard CSV parsers;
- Headers are needed for downstream column recognition;
- Delimiters, quotes/escapes, and NULL markers are agreed upon;
- Text-based inspection and metadata logging are desired;
- Producers and consumers handle quoted multiline records.

### 30.2. TEXT Is Appropriate When

- Running internal PostgreSQL pipelines or systems built for COPY TEXT rules;
- Backslashes/newlines/tabs follow COPY escaping rules;
- Default `\N` works as the NULL marker;
- CSV quoting semantics are unwanted;
- Files must maintain one physical line per row via escaped newlines.

### 30.3. Binary Is Appropriate When

- Producer and consumer are both PostgreSQL-compatible and tested for types/versions;
- Transfer throughput matters more than portability and human readability;
- Text-format options like HEADER/DELIMITER/NULL/QUOTE/ESCAPE are unneeded.

### 30.4. Hierarchical Data or Evolving Schemas

For nested JSON objects, heterogeneous record types, optional fields, or complex schema evolution, consider JSON Lines, Parquet, or schema-aware protocols. `COPY CSV` can carry JSON inside a properly quoted text field, yet does not manage schema versioning or validation automatically.

### 30.5. Prioritize Contracts Over Format Names

A file contract should specify:

~~~yaml
format: csv
header: true
header_validation: match
delimiter: ","
quote: '"'
escape: '"'
null_marker: ""
encoding: UTF8
column_order:
  - contact_id
  - full_name
  - nickname
  - note
  - active
  - created_at
date_format: ISO_8601
newline_policy: LF_or_CRLF
version: "1"
~~~

This is an **illustrative contract document**, not YAML automatically read by PostgreSQL COPY. Also explicitly define how **NULL** and **empty string** are distinguished, embedded newline policies, required columns, and error/rejection reporting.

## 31. File Import Decision Flowchart

~~~mermaid
flowchart TD
    A["Receive external file"] --> B{"Format contract known?"}
    B -->|No| C["Verify with producer: CSV vs TEXT, delimiter, encoding, NULL"]
    C --> B
    B -->|Yes| D{"Text-based file?"}
    D -->|No| E["Evaluate binary/schema/version separately"]
    D -->|Yes| F{"CSV or COPY TEXT?"}
    F -->|CSV| G["Set HEADER / DELIMITER / QUOTE / ESCAPE / NULL"]
    F -->|TEXT| H["Set DELIMITER and backslash/NULL rules"]
    G --> I["Check header, row count, encoding"]
    H --> I
    I --> J["COPY into staging and validate"]
    J --> K{"Accepted/rejected meet policy?"}
    K -->|No| L["Halt publication, fix source/mapping"]
    K -->|Yes| M["Load target table with transaction/idempotency"]
    M --> N["Reconcile NULL/empty, row counts, and sample data"]
~~~

### 31.1. Role of HEADER MATCH

`HEADER MATCH` catches certain schema and column-order bugs, yet it **does not** verify that `amount` is positive, emails are valid, dates aren't in the future, or business keys are unique. Those checks belong in validation and constraints.

### 31.2. Role of FORCE Options

`FORCE_NULL` and `FORCE_NOT_NULL` alter **field parsing**. They are not automatic data-quality fixers or replacements for `NOT NULL`/`CHECK`.

### 31.3. Role of Round-Trip Testing

Round-trip tests validate serialization for tricky inputs containing delimiters, quotes, newlines, and NULLs. They do not replace authorization checks, high-volume load tests, concurrency testing, or business reconciliation.

## 32. Basic Exercises: HEADER and DELIMITER

The exercises below use the `copy411` schema and lab tables created earlier. Some include inline `COPY FROM STDIN` payloads ending with `\.`: run those directly in **psql** or an equivalent supporting tool. If using a GUI or JDBC, create a matching file or use the streaming COPY API. Never run these on production business tables. Reasoning questions can be worked out on paper before testing in SQL.

### Exercise 1 — What Is the Default COPY Format?

~~~sql
COPY copy411.contacts TO STDOUT;
~~~

**Question:** Does PostgreSQL use `FORMAT csv` or `FORMAT text` when `FORMAT` is omitted? What are the default delimiter and NULL marker?

**Answer:** TEXT, tab, `\N`.

### Exercise 2 — Default CSV

~~~sql
COPY copy411.contacts
TO STDOUT WITH (FORMAT csv);
~~~

**Question:** What are the default delimiter, quote, escape, and NULL marker for CSV?

**Answer:** comma; both quote and escape are double quote; NULL is an unquoted empty field.

### Exercise 3 — Header Present or Not?

A file:

~~~csv
id,name
1,An
2,Bình
~~~

**Question:** If `COPY FROM` omits `HEADER true`, what happens when column `id` is integer?

### Exercise 4 — Accidentally Skipping the First Data Row

A headerless file:

~~~csv
1,An
2,Bình
~~~

is imported with `HEADER true`. **Question:** How does the server handle `1,An`? Will it necessarily raise an error?

**Answer:** skipped as a header, risking silent row loss without error.

### Exercise 5 — HEADER MATCH

File header:

~~~csv
name,id
An,1
~~~

COPY specifies `(id,name)` and `HEADER MATCH`. **Question:** Does PostgreSQL reorder fields automatically by header name?

**Answer:** no; it raises a header name/order mismatch error.

### Exercise 6 — HEADER true with Swapped Columns

Two text columns: `first_name`, `last_name`. The file changes the header order to `last_name,first_name` while the importer uses `HEADER true`.

**Exercise:** Describe the silent bug that occurs and why `HEADER MATCH` or a contract check matters.

### Exercise 7 — Header of COPY (query)

~~~sql
COPY (
    SELECT contact_id AS id, full_name AS display_name
    FROM copy411.contacts
) TO STDOUT
WITH (FORMAT csv, HEADER true);
~~~

**Question:** Will the header names be `contact_id,full_name` or `id,display_name`?

### Exercise 8 — Is HEADER Supported on Binary?

Someone proposes:

~~~sql
COPY copy411.contacts TO STDOUT
WITH (FORMAT binary, HEADER true);
~~~

**Question:** Does `HEADER` apply to binary format?

**Answer:** not supported.

### Exercise 9 — Semicolon Delimiter

File:

~~~csv
id;name;note
1;An;Hello
2;"Bình; Bé";"Contains ; in cell"
~~~

**Exercise:** Write the correct `COPY FROM` command with `DELIMITER ';'` and `HEADER true`.

### Exercise 10 — Pipes Do Not Replace Quoting

File:

~~~text
1|An|A|B
~~~

Target has three columns and delimiter `|`. **Question:** How many fields are present? How must the third field containing `A|B` be written in CSV?

**Answer:** the line currently has four fields; fix it to `1|An|"A|B"`.

### Exercise 11 — Multi-Character Delimiter

A producer exports `id||name||note` and wants to use `DELIMITER '||'`.

**Question:** Does PostgreSQL COPY accept this delimiter? Suggest a solution.

**Answer:** no; preprocess or ask the producer to switch to a single-byte delimiter, or convert formats with a custom parser.

### Exercise 12 — Tab vs. Spaces

Someone views a TSV in an editor and replaces tabs with four spaces to "align columns nicely".

**Exercise:** Explain why `DELIMITER E'\t'` no longer parses correctly.

### Exercise 13 — Comma Inside a String

File:

~~~csv
1,"An, Nguyễn",active
~~~

**Question:** How many fields are there? If quotes around the name are removed, how many fields would there be?

### Exercise 14 — Field Count Mismatch

Distinguish:

~~~csv
1,An,
1,An
~~~

for column list `(id,name,note)`.

**Question:** Which one has an empty field, and which one is missing a field?

### Exercise 15 — Should You Guess Delimiters by Counting Commas?

A file contains quoted `"An, Nguyễn"`. If you use `split(',')`, how is the record mis-split? Write high-level pseudocode for a parser that tracks quote state.

## 33. Intermediate Exercises: QUOTE, ESCAPE, and Multiline

### Exercise 16 — Escaping Double Quotes

Actual value:

~~~text
Bình "Bé"
~~~

**Exercise:** Write the valid CSV field using default quote/escape settings.

**Answer:** `"Bình ""Bé"""`.

### Exercise 17 — Quotes and Delimiters Together

Actual value:

~~~text
Nguyễn "An, Bé"
~~~

**Exercise:** Write the valid CSV field and explain which quotes are outer delimiters vs. escaped quotes.

### Exercise 18 — Multiline CSV

~~~csv
id,note
1,"Line 1
Line 2"
2,OK
~~~

**Question:** How many data records are there? Why doesn't physical line count equal record count?

### Exercise 19 — CSV Backslashes

A field in default CSV contains:

~~~text
C:\temp\new
~~~

**Question:** Do backslashes turn into tabs/newlines like in TEXT?

**Answer:** no; default CSV does not use COPY TEXT backslash escaping.

### Exercise 20 — COPY TEXT Backslashes

To store the literal path `C:\temp\new` using `FORMAT text` and delimiter `|`:

**Exercise:** Write the escaped TEXT field.

**Answer:** `C:\\temp\\new`.

### Exercise 21 — TEXT Delimiter Inside a Value

With `DELIMITER '|'`, a field has literal text `A|B`. **Exercise:** Write the field in COPY TEXT.

**Answer:** `A\|B`.

### Exercise 22 — TEXT Newline

Write a field containing two lines `Hello` and `World` using COPY TEXT.

**Question:** Use a physical newline in the field or the `\n` escape?

**Answer:** `Hello\nWorld` in the TEXT file.

### Exercise 23 — TEXT Literal \N

Distinguish the two TEXT fields:

~~~text
\N
\\N
~~~

**Question:** Which becomes SQL NULL, and which becomes the two-character string `\N` by default?

### Exercise 24 — CSV Literal \N

A default CSV contains an unquoted field `\N`.

**Question:** Does it become SQL NULL?

**Answer:** no; it is the literal text `\N`.

### Exercise 25 — Differing QUOTE and ESCAPE

A producer quotes with `"` but escapes literal quotes with a backslash. The consumer configures `ESCAPE '"'`.

**Exercise:** Explain why parsing fails or misreads values, and what agreement is required between both sides.

### Exercise 26 — FORCE_QUOTE

`COPY TO CSV WITH (FORCE_QUOTE *)` on values `NULL`, `''`, `'abc'`.

**Question:** Is NULL quoted? Why must PostgreSQL keep the distinction?

**Answer:** NULL is unquoted; non-NULL values are quoted.

### Exercise 27 — Spaces

Compare:

~~~csv
"  An  "
  An
~~~

**Question:** Does PostgreSQL automatically trim to `An`? What risk arises if a producer adds spaces outside quotes?

### Exercise 28 — File Line Endings

A CSV mixes CRLF and LF and contains an unquoted newline inside a field.

**Exercise:** Explain why the parser fails and how to standardize line endings and quoted multiline fields per contract.

### Exercise 29 — \. in Inline psql

When using inline `COPY FROM STDIN` in psql, which line ends the stream? How should a CSV field containing literal `\.` on its own line be handled?

### Exercise 30 — Version Differences

A CSV containing a standalone `\.` field is exported from PostgreSQL 18 and imported into PostgreSQL 16.

**Exercise:** Identify the end-marker compatibility risk, how to verify versions, and how to round-trip test.

## 34. Advanced Exercises: NULL, Empty, and FORCE Options

### Exercise 31 — NULL and Empty String

Default CSV:

~~~csv
id,note
1,
2,""
~~~

**Question:** What are the `note` values in both rows inside PostgreSQL?

**Answer:** row 1 SQL NULL; row 2 empty string.

### Exercise 32 — Literal Text 'NULL'

Default CSV has an unquoted field `NULL`.

**Question:** Does it become SQL NULL?

**Answer:** no; it is just the string `'NULL'`.

### Exercise 33 — NULL 'NULL'

With `NULL 'NULL'`, distinguish:

~~~csv
1,NULL
2,"NULL"
~~~

**Answer:** row 1 SQL NULL, row 2 text `'NULL'` when `FORCE_NULL` is not used.

### Exercise 34 — NULL Marker Colliding with Real Data

A producer picks `NULL 'N/A'`, yet the business has a product description literally equal to `N/A`.

**Exercise:** Which field must the producer quote, and what options must the consumer keep to avoid losing meaning?

### Exercise 35 — FORCE_NOT_NULL

Unquoted empty field in column `note text` with `FORCE_NOT_NULL(note)`.

**Question:** Is the DB value SQL NULL or `''`?

**Answer:** `''`.

### Exercise 36 — FORCE_NOT_NULL with Integer

Unquoted empty field into an integer column using `FORCE_NOT_NULL`.

**Question:** Does it automatically become 0?

**Answer:** no; an empty string is not a valid integer and raises a conversion error.

### Exercise 37 — FORCE_NULL with Quoted Empty

`NULL ''` and `FORCE_NULL(note)` are active; the field is `""`.

**Question:** What value does PostgreSQL import?

**Answer:** SQL NULL.

### Exercise 38 — FORCE_NULL with Quoted 'NULL'

`NULL 'NULL'` and `FORCE_NULL(note)`; the field is `"NULL"`.

**Answer:** SQL NULL.

### Exercise 39 — FORCE_NOT_NULL and FORCE_NULL on the Same Column

`NULL 'NULL'`, `FORCE_NULL(note)`, and `FORCE_NOT_NULL(note)`:

~~~csv
1,NULL
2,"NULL"
~~~

**Question:** Which row becomes text, and which becomes SQL NULL?

**Answer:** row 1 text `'NULL'`, row 2 SQL NULL.

### Exercise 40 — NULL vs. DEFAULT

A column `status text DEFAULT 'pending' NOT NULL`.

**Question:** If an unquoted empty field loads into `status` under default CSV, does it automatically become `'pending'`? What if `status` is omitted from the COPY column list?

**Answer:** the NULL marker loads SQL NULL (violating NOT NULL); if the column is omitted from the column list, the default can apply.

## 35. Capstone Exercises: Pipelines and Operations

### Exercise 41 — Round-Tripping Diverse Data

Export `copy411.contacts` with `\copy ... FORMAT csv, HEADER true`, then import into `contacts_roundtrip`. Compare columns containing:

- NULL;
- Empty string;
- Comma;
- Quotes;
- Newline;
- Backslash;
- Vietnamese Unicode;
- Date.

**Requirement:** Verify using `IS NOT DISTINCT FROM` or `EXCEPT ALL` as appropriate. Explain why checking row counts alone is insufficient.

### Exercise 42 — Header Alias vs. MATCH

An export query aliases `contact_id AS id` and `full_name AS name`, but the import specifies column list `(contact_id, full_name)` with `HEADER MATCH`.

**Question:** Why does it fail? Possible fixes: align export headers to the target contract, rename staging columns, or verify headers independently before mapping.

### Exercise 43 — Staging with _text Column Names

The file header is `contact_id,full_name,...` while staging columns are `contact_id_text,full_name_text,...`.

**Exercise:** Choose `HEADER true` or `HEADER MATCH` for copying into staging? How can you still validate the header contract outside COPY?

### Exercise 44 — Date Type Errors

A CSV contains `created_at=32/13/2026` for a `date` target column.

**Exercise:** Explain why you should not tweak `DateStyle` arbitrarily or enable unlimited `ON_ERROR ignore`; propose text staging and a rejection report.

### Exercise 45 — Multiline Records

A file contains 1,000 CSV records, yet counting newlines yields 1,100 due to multiline notes.

**Question:** How do you determine the true CSV record count without splitting on newlines?

### Exercise 46 — CSV Formula Injection

A field starting with `=1+1` will be opened in a spreadsheet.

**Question:** Is `FORCE_QUOTE *` enough to prevent the target software from treating it as a formula? What controls should be evaluated?

**Answer:** insufficient; apply neutralization/import-as-text or explicitly typed formats per the target application's security policy.

### Exercise 47 — Server COPY File vs. Client \copy File

A developer runs:

~~~sql
COPY copy411.contacts FROM 'C:\Users\Me\contacts.csv'
WITH (FORMAT csv, HEADER true);
~~~

while the PostgreSQL server actually runs on remote Linux.

**Exercise:** Explain why the server cannot see the laptop file; choose client `\copy` or driver-based `COPY FROM STDIN`.

### Exercise 48 — Missing Server-File COPY Permission

An app role has `INSERT` on the table but not `pg_read_server_files`.

**Question:** Should broad server-file roles be granted just to import CSVs from the app? What are the alternatives?

**Answer:** no; use `STDIN`/`\copy` or a properly scoped import API.

### Exercise 49 — ON_ERROR ignore

A file has 100 rows; 20 rows have invalid dates. One team wants to enable `ON_ERROR ignore` and treat zero fatal errors as a successful import.

**Exercise:** Design an accepted/rejected tracking table, reject limit, source count reconciliation, error reporting, and publication threshold. Distinguish conversion errors from constraint and CSV parser errors.

### Exercise 50 — Capstone: Partner Data Integration

A partner sends a daily file:

~~~csv
customer_code;full_name;nickname;note;joined_at
000123;"Nguyễn, An";;"Note ""VIP""";2026-01-31
000124;Bình;"";"Line 1
Line 2";2026-02-01
000125;Chi;NULL;C:\sales\new;2026-02-02
~~~

Confirmed partner contract:

- `FORMAT csv`, `DELIMITER ';'`, `QUOTE '"'`, `ESCAPE '"'`;
- UTF-8 file with header;
- Partner specifies **unquoted empty nickname = SQL NULL**;
- `""` = empty string;
- Unquoted `NULL` is **literal text 'NULL'**;
- `customer_code` is text and must retain leading zeros;
- `note` may contain quotes, delimiters, newlines, and backslashes;
- `joined_at` uses ISO dates;
- No data loss or duplicate batch loads on retry.

**Deliverables:**

1. Define the staging table and target table.
2. Write `\copy`/`COPY FROM STDIN` with the right delimiter, header, and encoding.
3. State the exact NULL marker per contract and whether FORCE options are needed.
4. Explain the three `nickname` cases across rows.
5. Explain why CSV backslashes in `C:\sales\new` do not need COPY TEXT escaping.
6. Account for quoted newlines to avoid miscounting records.
7. Ensure `customer_code` is never coerced to integer.
8. Verify schema/header, noting when `HEADER MATCH` applies if column names align with the contract.
9. Validate dates, required strings, duplicates, and anomalies.
10. Include import batch ID/checksum, accepted/rejected reports, transactions, and idempotency.
11. Round-trip test CSV → staging → target table → CSV export.
12. Propose PII controls and formula-injection protection if files are opened in spreadsheets.

**Key goal:** not just making COPY run "without errors", but proving both **structure and value semantics** are preserved end-to-end.

## 36. Pre-Ingestion Checklist

### 36.1. File Structure

- [ ] Confirmed `FORMAT csv` vs. `FORMAT text`; not guessed from filename extension.
- [ ] Determined whether a header is present.
- [ ] If present, chose `HEADER true` or `HEADER MATCH`.
- [ ] If using `MATCH`, header names and order match the COPY column list.
- [ ] Verified field counts across all records, not just the header.
- [ ] Locked target column list, order, and data types.
- [ ] Confirmed delimiter is a single single-byte character.
- [ ] Confirmed `,`, `;`, `|`, or tab delimiter.
- [ ] Not parsing quoted CSV with `split(',')` / `split('\n')`.
- [ ] Checked whether embedded newlines or delimiters appear in text fields.

### 36.2. Quoting and Escaping

- [ ] For CSV, confirmed `QUOTE` and `ESCAPE`.
- [ ] Under defaults, embedded `"` is written as `""`.
- [ ] Tested fields containing both quotes and delimiters.
- [ ] Tested multiline CSV with balanced opening/closing quotes.
- [ ] For TEXT, used backslash escapes properly without mixing in CSV quote rules.
- [ ] Tested paths containing backslashes in TEXT.
- [ ] Tested literal `\N` vs. marker `\N` in TEXT.
- [ ] Checked end-of-data `\.` behavior if using inline psql or older PostgreSQL versions.

### 36.3. NULL and Empty Strings

- [ ] Documented that SQL NULL differs from `''`, `'NULL'`, and literal `'\N'`.
- [ ] Understand CSV default: unquoted empty = NULL, quoted `""` = empty string.
- [ ] Understand TEXT default: `\N` = SQL NULL, `\\N` = literal `\N`.
- [ ] Selected `NULL '...'` per contract without arbitrary overrides.
- [ ] Checked whether real data can collide with the null marker.
- [ ] Applied `FORCE_NULL` or `FORCE_NOT_NULL` only to specific needed columns.
- [ ] Not using `FORCE_NOT_NULL` to mask business `NOT NULL` failures.
- [ ] Aware `FORCE_QUOTE` never quotes SQL NULL.
- [ ] Tested NULL-safe round-trip or canonical output.
- [ ] Not coalescing NULL to text before export when meaning must be preserved.

### 36.4. Encoding, Types, and Security

- [ ] Source encoding matches `ENCODING` / `client_encoding`.
- [ ] Checked for BOM if `HEADER MATCH` fails unexpectedly.
- [ ] Checked LF/CRLF and quoted multiline CSV behavior.
- [ ] Standardized date/time/decimal formats and locale rules.
- [ ] Codes with leading zeros stored as text where required.
- [ ] Neutralization/controls in place for CSV formula injection if opened in spreadsheets.
- [ ] PII governed by proper access permissions and retention policies.
- [ ] No broad server-file privileges granted merely to import client CSVs.
- [ ] Distinguished server-side `COPY` from client-side `\copy`.

### 36.5. Import Operations

- [ ] Stage first when sources are not fully trusted.
- [ ] Track schema version, checksum, and import batch ID.
- [ ] Negative tests for wrong delimiter, bad header, broken quotes, and NULL/empty.
- [ ] Accepted/rejected reporting and total record reconciliation.
- [ ] If using `ON_ERROR ignore`, verified PostgreSQL version and conversion-error scope.
- [ ] Never ignore constraint/trigger errors without investigation.
- [ ] Transaction, rollback, and idempotency controls for batch loads.
- [ ] Retry policy prevents duplicate ingestion.
- [ ] Verified triggers, check constraints, and RLS on target tables.
- [ ] Plan to monitor performance, disk, and WAL during large COPY loads.
- [ ] Tested export→import→real-data comparison with NULL-safe checks.

## 37. Frequently Asked Questions

### 37.1. Must COPY CSV Always Use Commas?

No. CSV defaults to comma, yet you can specify `DELIMITER ';'` or another single-byte character. Producer and consumer must agree on the delimiter.

### 37.2. Does HEADER true Map Columns by Name?

No. It only skips the header during import. `HEADER MATCH` checks names and order, yet does not reorder fields automatically.

### 37.3. Why Do Empty Fields Become NULL in PostgreSQL?

That is the default CSV rule under `NULL ''` for **unquoted empty fields**. For an empty string, producers write `""`, or consumers enable `FORCE_NOT_NULL` per an explicit contract.

### 37.4. Does `""` in CSV Mean the Text '""'?

Not by default: it is a **quoted empty string**, decoded as `''`. To represent two literal quote characters, escape/quote per CSV rules—for example `""""""` represents a CSV field containing two literal quotes.

### 37.5. Why Doesn't Default CSV Treat \N as NULL?

Because default CSV uses an **unquoted empty field** as its NULL marker. `\N` is the default NULL marker for **COPY TEXT**, not CSV.

### 37.6. If I Change the NULL Marker to 'NULL', What Do Empty Fields Become?

In CSV on a text column without FORCE options, an unquoted empty field no longer matches the `NULL` marker, so it loads as an empty string rather than SQL NULL.

### 37.7. What If I Want "NULL" to Also Become NULL?

Use `NULL 'NULL'` and `FORCE_NULL(column)` where appropriate. Confirm no real text `'NULL'` needs preservation, as quoted markers will also become SQL NULL.

### 37.8. How Do I Ensure Empty Fields Never Become NULL?

In CSV, `FORCE_NOT_NULL(column)` can be used on text columns whose contract defines blank as empty string. Never apply it blindly to numeric or date columns without handling logic.

### 37.9. Does FORCE_QUOTE Improve Import Accuracy?

It only affects **CSV export**, forcing non-NULL values to be quoted; it does not alter input mapping or constraints. SQL NULL remains unquoted.

### 37.10. Why Doesn't COPY TEXT Use QUOTE?

Because TEXT format uses **backslash escaping** rather than CSV quoted fields. For CSV quoting, use `FORMAT csv`.

### 37.11. Can a CSV Cell Contain a Newline?

Yes, when the field is properly quoted. That is why physical line counts cannot determine record counts.

### 37.12. In psql, Should I Use COPY or \copy?

When the file lives on the psql client machine and the role lacks server-file permissions, `\copy` is usually more practical. `COPY ... FROM '/server/file'` reads from the PostgreSQL server machine.

### 37.13. Why Does Importing a Laptop File to a Remote Server Say File Not Found?

Because `COPY FROM 'path'` is server-side. Use psql `\copy` or `COPY FROM STDIN` via a driver to stream bytes from the client.

### 37.14. Does HEADER MATCH Exist in Every PostgreSQL Version?

Never assume so; check documentation for your exact major version. `HEADER MATCH` validates names/order and applies only to `COPY FROM` on supported formats.

### 37.15. Can ON_ERROR ignore Prevent All Import Errors?

No. It primarily covers **column data-type conversion errors** in supported versions; CSV syntax errors, permission failures, constraints, and system errors can still fail COPY.

### 37.16. Does COPY Fire Triggers?

`COPY FROM` fires applicable triggers and check constraints on the target table. This can slow large loads or reject rows per business rules. Never disable triggers arbitrarily to "bypass" data errors.

### 37.17. Why Do Leading Zeros Disappear After Opening and Saving CSV in Excel?

Spreadsheets often infer numeric types on numeric-looking codes, converting text `000123` to `123`. Store codes with leading zeros as text and document import-as-text steps.

### 37.18. Why Do Identical File Hashes Produce Different Import Results?

Identical bytes loaded with different `FORMAT`, `DELIMITER`, `NULL`, `ENCODING`, column lists, or target column types produce different results. Checksums protect bytes, not parser semantics.

## 38. Official PostgreSQL Documentation

PostgreSQL documentation varies across major versions; especially for `HEADER MATCH`, `DEFAULT`, `ON_ERROR`, `REJECT_LIMIT`, `\.` handling in CSV, and the `ENCODING` option, consult the **exact version you operate**.

- [COPY](https://www.postgresql.org/docs/current/sql-copy.html): authoritative reference for `FORMAT`, `DELIMITER`, `NULL`, `HEADER`, `QUOTE`, `ESCAPE`, FORCE options, TEXT/CSV/BINARY parsing, errors, and privileges.
- [psql](https://www.postgresql.org/docs/current/app-psql.html): usage of `\copy`, client-side file paths, meta-commands, and scripting.
- [PostgreSQL Protocol: COPY Operations](https://www.postgresql.org/docs/current/protocol-flow.html#PROTOCOL-COPY): `COPY IN`/`COPY OUT` streams for clients and drivers.
- [Character Set Support](https://www.postgresql.org/docs/current/multibyte.html): server/client encodings, conversions, and Unicode.
- [Data Types](https://www.postgresql.org/docs/current/datatype.html): how PostgreSQL parses integer, date, text, boolean, timestamp types, and conversions.
- [Date/Time Input](https://www.postgresql.org/docs/current/datatype-datetime.html): date/time strings, DateStyle, timezones.
- [String Functions](https://www.postgresql.org/docs/current/functions-string.html): `length`, `btrim`, and string helpers during validation.
- [Comparisons](https://www.postgresql.org/docs/current/functions-comparison.html): `IS NULL`, `IS DISTINCT FROM`, and NULL semantics.
- [CREATE TABLE](https://www.postgresql.org/docs/current/sql-createtable.html): column defaults, NOT NULL/CHECK/UNIQUE, and data types.
- [INSERT](https://www.postgresql.org/docs/current/sql-insert.html): alternative to COPY when transforms, upserts, or RLS are required.
- [Row Security Policies](https://www.postgresql.org/docs/current/ddl-rowsecurity.html): securing data via RLS and `COPY FROM` restrictions.
- [Monitoring Progress](https://www.postgresql.org/docs/current/progress-reporting.html#COPY-PROGRESS-REPORTING): `pg_stat_progress_copy` for monitoring large COPY operations.
- [VACUUM](https://www.postgresql.org/docs/current/sql-vacuum.html): reclaiming dead tuples after failed imports and managing storage.
- [Roles and Privileges](https://www.postgresql.org/docs/current/user-manag.html): SELECT/INSERT rights, server file permissions, and least-privilege principles.

## 39. Summary

A file with clean headers can still load incorrectly if **column order**, **delimiters**, **quoting/escaping rules**, or **NULL markers** are misaligned between producer and consumer.

| Factor | Quick Rule of Thumb |
| --- | --- |
| **HEADER true** | Skips header row on import; emits column names on export |
| **HEADER MATCH** | Verifies header names and order on `COPY FROM`, **never reorders** |
| **DELIMITER** | One single-byte character; TEXT defaults to tab, CSV defaults to comma |
| **CSV QUOTE** | Defaults to double quote enclosing fields with delimiters/quotes/newlines |
| **CSV ESCAPE** | Defaults to double quote; literal `"` inside data becomes `""` |
| **TEXT escape** | Backslash sequences `\n`, `\t`, `\r`, `\\`... |
| **TEXT NULL** | Defaults to `\N` |
| **CSV NULL** | Defaults to **unquoted empty field** |
| **CSV empty string** | Defaults to `""` |
| **FORCE_NULL** | Allows quoted markers to become SQL NULL |
| **FORCE_NOT_NULL** | Prevents marker on selected columns from becoming NULL |
| **FORCE_QUOTE** | CSV export only; never quotes SQL NULL |
| **\copy** | psql reads/writes files on the client side |
| **COPY 'path'** | PostgreSQL server reads/writes files on the server side |

**When importing CSV/TEXT, the key question is not merely "did COPY run without error?"—it is "was every value decoded with its true meaning?"** To answer yes, lock down the format contract, verify headers and schemas, use proper parsers, preserve NULL vs. empty string distinctions, stage untrusted sources first, and round-trip test with quotes, delimiters, newlines, backslashes, Vietnamese Unicode, and blank values. That is the foundation of an **accurate, secure, and verifiable** PostgreSQL import–export pipeline.
