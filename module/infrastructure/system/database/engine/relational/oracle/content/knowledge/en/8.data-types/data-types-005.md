# BYTE/CHAR Length Semantics and Storing Vietnamese in Oracle Database

A customer management application might successfully store the name `Ha Noi` yet fail with an error when storing `Hà Nội`, even though both have six visible characters. The cause may be that the column is defined as `VARCHAR2(6 BYTE)`: Oracle limits it to **six bytes**, whereas accented Vietnamese letters often require more than one byte when the database uses Unicode `AL32UTF8`. There are also cases where the column is changed to `VARCHAR2(6 CHAR)` yet still cannot store an overly long string because Oracle also enforces a maximum **byte** limit for the data type.

This lesson belongs to the **Data Types** module in Oracle Database and explains how to choose and verify `BYTE`/**`CHAR`** length semantics when storing Vietnamese. Beyond `CREATE TABLE` syntax, you will understand the relationship between Unicode, character sets, bytes, code points, the data dictionary, session settings, and JDBC/application limits.

After this lesson, you will be able to:

- Distinguish `VARCHAR2(20 BYTE)`, `VARCHAR2(20 CHAR)`, and `VARCHAR2(20)`.
- Explain why Vietnamese string length in **characters** can differ from length in **bytes** under `AL32UTF8`.
- Use `LENGTH`, `LENGTHB`, `DUMP`, and `USER_TAB_COLUMNS` metadata to inspect data and column structure.
- Recognize the effect and limits of `NLS_LENGTH_SEMANTICS`, `MAX_STRING_SIZE`, `CHAR`, `VARCHAR2`, `NVARCHAR2`, and `CLOB`.
- Design columns cleanly for person names, addresses, identifiers, and Vietnamese content; troubleshoot `ORA-12899` or corrupted characters without guessing.

> **Example assumptions:** The practice database or PDB uses the `AL32UTF8` character set, and SQL*Plus/SQL Developer can send and display Unicode properly. This is the right setup for modern Vietnamese, though not every Oracle Database uses it. Always **check the actual character set** first; exact byte counts in the examples depend on it and on how strings are encoded.

## 1. Three Units to Distinguish: Byte, Character, and Display Character

A string can be measured in several ways:

| Unit | Meaning | Why It Matters |
| --- | --- | --- |
| **Byte** | 8-bit storage unit; one Unicode code point may require multiple bytes in UTF-8 | `VARCHAR2(n BYTE)` and SQL maximum capacity limits |
| **Character/code point** | A code point in the character set; Oracle uses character units to interpret `VARCHAR2(n CHAR)` | Checking the logical character count of a column |
| **Grapheme cluster / user-perceived character** | A display unit such as a base letter plus combining marks or a composite emoji | Input forms, UI display limits, safe string truncation |

In the common case, an accented Vietnamese letter such as `à` is **one code point** yet can require **two bytes** in UTF-8 encoding. The letter `ộ` is typically **one code point** and requires **three bytes**. ASCII characters such as `A`, spaces, and digits 0–9 need only one byte in `AL32UTF8`.

However, Unicode allows the same visually identical letter to be represented as **one precomposed code point** or **multiple code points consisting of a base letter and combining marks**. Hence "6 user-visible characters" does not always mean "6 code points". When determining real limits, pay attention to both **encoding** and **Unicode normalization**.

### 1.1. Some Vietnamese Characters in AL32UTF8

| String / Code Point | Code Points in Precomposed Form (NFC) | Bytes in AL32UTF8 | Explanation |
| --- | ---: | ---: | --- |
| `A` | 1 | 1 | ASCII |
| `à` (U+00E0) | 1 | 2 | Accented Latin character |
| `đ` (U+0111) | 1 | 2 | Vietnamese letter đ |
| `ộ` (U+1ED9) | 1 | 3 | Latin letter with multiple diacritics |
| `Ha Noi` | 6 | 6 | ASCII only |
| `Hà Nội` | 6 | 9 | H = 1, à = 2, space = 1, N = 1, ộ = 3, i = 1 |

The illustrative numbers assume strings represented in precomposed **NFC** form. A string that looks like `Hà Nội` but uses decomposed combining marks can have different code point and byte counts. Oracle should not be relied on to automatically normalize every incoming string to NFC.

### 1.2. Journey of a Vietnamese String

~~~text
User types "Hà Nội"
         |
         v
UI / Java String / JDBC parameter
         |
         |  Conversion via driver, encoding, and character set
         v
Oracle column VARCHAR2(...)
         |
         +--> Character limit if declared as CHAR
         |
         +--> Column / datatype byte limit must still be respected
         |
         v
Value stored in the database character set
~~~

If corruption occurs at the terminal/driver/encoding stage, increasing column length **cannot restore Vietnamese accents already replaced with question marks**. Conversely, if the error occurs because the column is too short, arbitrarily changing client encoding will not fix the root cause either.

## 2. `VARCHAR2(n BYTE)` and `VARCHAR2(n CHAR)`

### 2.1. `BYTE` Limits Total Bytes

~~~sql
CREATE TABLE vn_byte_example (
    display_name VARCHAR2(6 BYTE)
);
~~~

`VARCHAR2(6 BYTE)` allows each value to be at most **6 bytes** in the database character set. With `AL32UTF8`:

- `'Ha Noi'` requires 6 bytes ⇒ fits the limit.
- `'Hà Nội'` (NFC) requires 9 bytes ⇒ exceeds the limit.
- `'ààà'` requires 6 bytes ⇒ fits the limit even though it is only 3 characters.
- `'ộộộ'` requires 9 bytes ⇒ exceeds the limit even though it is also only 3 characters.

You cannot infer that a `VARCHAR2(6 BYTE)` column will hold "six Vietnamese letters". Six bytes is a byte limit; how many characters fit depends on the content.

### 2.2. `CHAR` Limits Characters / Code Points

~~~sql
CREATE TABLE vn_char_example (
    display_name VARCHAR2(6 CHAR)
);
~~~

`VARCHAR2(6 CHAR)` allows up to **6 characters** under Oracle semantics for the database character set. With NFC data:

- `'Ha Noi'`: 6 characters ⇒ valid.
- `'Hà Nội'`: 6 characters ⇒ valid even though it needs 9 bytes.
- `'ộộộộộộ'`: 6 characters ⇒ valid provided it does not hit the data type's absolute byte limit.
- `'Hà Nội!'`: 7 characters ⇒ exceeds the limit.

Declaring `CHAR` here specifies **length semantics**; it does not turn the column into a fixed-length `CHAR` type. The column type remains **`VARCHAR2`**: values are variable-length, and Oracle does not pad spaces up to six characters.

### 2.3. Side-by-Side Comparison on the Same Table

| Declaration | Limit Stated in DDL | `Ha Noi` (6 bytes, 6 chars) | `Hà Nội` (9 bytes, 6 chars) |
| --- | --- | --- | --- |
| `VARCHAR2(6 BYTE)` | Up to 6 bytes | Fits | Does not fit |
| `VARCHAR2(6 CHAR)` | Up to 6 characters, still subject to datatype byte cap | Fits | Fits |
| `VARCHAR2(6)` | Follows `NLS_LENGTH_SEMANTICS` of the session creating the column | Session-dependent | Session-dependent |

The key point is that **`BYTE` and `CHAR` describe the length unit**, not the encoding name. A `VARCHAR2(30 CHAR)` column in an `AL32UTF8` database still stores characters in `AL32UTF8`; saying `CHAR` does not switch storage to UTF-16.

## 3. Setting and Verifying the Actual Character Set

### 3.1. Two Character Sets in Oracle

Oracle distinguishes:

| Character Set | Primarily Applies To | Common Example Values |
| --- | --- | --- |
| **Database character set** | `CHAR`, `VARCHAR2`, `CLOB`, and most string data in the database | `AL32UTF8` |
| **National character set** | `NCHAR`, `NVARCHAR2`, `NCLOB` | `AL16UTF16`, or an Oracle-supported national charset configuration |

With the `AL32UTF8` database character set, `VARCHAR2(... CHAR)` columns can store Vietnamese without issue. **You do not have to switch to `NVARCHAR2` just because data has Vietnamese accents.** Choosing NCHAR types should be based on concrete requirements, drivers, and existing data policies.

Check via SQL in the connected database/PDB:

~~~sql
SELECT parameter, value
FROM nls_database_parameters
WHERE parameter IN (
    'NLS_CHARACTERSET',
    'NLS_NCHAR_CHARACTERSET'
)
ORDER BY parameter;
~~~

Example output:

~~~text
PARAMETER               VALUE
----------------------  --------
NLS_CHARACTERSET        AL32UTF8
NLS_NCHAR_CHARACTERSET  AL16UTF16
~~~

If `NLS_CHARACTERSET` is another encoding, the byte counts estimated earlier **will not necessarily hold**. If a Vietnamese character cannot be represented in the database character set, character conversion can fail or lose data depending on the pipeline/configuration. The long-term fix is usually choosing a full Unicode character set, but **changing a database character set is a migration project**, not something solved by tweaking `NLS_LENGTH_SEMANTICS`.

### 3.2. Why Prefer AL32UTF8?

`AL32UTF8` is Oracle's modern UTF-8 implementation for the database character set, supporting Unicode characters across many languages. It fits systems storing Vietnamese alongside foreign names, symbols, and non-BMP characters (where a single code point can occupy four bytes).

Do not confuse Oracle's legacy `UTF8` character set name with `AL32UTF8`: Oracle distinguishes between the two, especially in how certain supplementary non-BMP Unicode characters are encoded. For new systems, using `AL32UTF8` per Oracle guidance is the standard choice.

Choosing a character set and choosing `BYTE/CHAR` serve **two different purposes**:

~~~text
AL32UTF8:  Which characters can be represented, and how many bytes does each character need?

BYTE/CHAR: Is each column value bounded by bytes or by code points?
~~~

Even when a database supports Unicode, poorly declared column lengths in the schema can still raise length-exceeded errors.

## 4. `LENGTH`, `LENGTHB`, `LENGTHC`, and Related Functions

### 4.1. Measuring Strings in Characters and Bytes

Oracle provides several length functions:

| Function | Unit of Measurement | Use Case |
| --- | --- | --- |
| `LENGTH(text)` | Characters in the expression's character set | Checking standard character counts |
| `LENGTHB(text)` | Bytes | Checking short string representation size in the corresponding character set |
| `LENGTHC(text)` | Unicode complete characters as defined by Oracle | Checking Unicode cases needing different counting than `LENGTH` |
| `LENGTH2(text)` | UCS-2 code units | Analyzing special Unicode cases |
| `LENGTH4(text)` | UCS-4 code points | Analyzing Unicode code point counts where appropriate |

With a Vietnamese literal sent to an `AL32UTF8` database using **proper encoding** in NFC form:

~~~sql
SELECT
    LENGTH('Hà Nội')  AS character_count,
    LENGTHB('Hà Nội') AS byte_count
FROM dual;
~~~

Expected result:

~~~text
CHARACTER_COUNT  BYTE_COUNT
---------------  ----------
6                9
~~~

Additional check:

~~~sql
SELECT
    LENGTH('Ha Noi')  AS ascii_chars,
    LENGTHB('Ha Noi') AS ascii_bytes,
    LENGTH('ộ')       AS viet_chars,
    LENGTHB('ộ')      AS viet_bytes
FROM dual;
~~~

In `AL32UTF8` with a properly Unicode-configured client, `Ha Noi` gives 6/6 and `ộ` gives 1/3. If results differ or output prints as `H? N?i`, inspect the **input and transcoding pipeline**, not just the schema.

### 4.2. Using `DUMP` to Inspect Byte Representation

The `DUMP` function shows the datatype and byte representation of an expression:

~~~sql
SELECT
    DUMP('Hà Nội', 1016) AS hex_dump,
    LENGTH('Hà Nội')     AS chars,
    LENGTHB('Hà Nội')    AS bytes
FROM dual;
~~~

The parameter `1016` requests hexadecimal output along with the corresponding character set name. In an `AL32UTF8` environment, the byte sequence of an NFC string reflects the UTF-8 encoding of each code point.

If you want to construct a Unicode character **without depending on how a terminal types accents**, Oracle provides `UNISTR` with Unicode escapes:

~~~sql
-- U+00E0 is the letter a with grave accent.
SELECT
    CAST(UNISTR('\00E0') AS VARCHAR2(10 CHAR)) AS unicode_character
FROM dual;
~~~

`UNISTR` returns a string in the national character set; `CAST ... AS VARCHAR2` converts it to the database character set in the example. This helps separate terminal input issues from database encoding issues.

### 4.3. Unicode Normalization: Identical-Looking Characters May Have Different Lengths

The two strings below can look identical when rendered:

~~~text
NFC:  "é"   = U+00E9                (1 code point)
NFD:  "é"  = U+0065 + U+0301       (2 code points)
~~~

In `AL32UTF8`, their lengths are:

| Form | Code Points | UTF-8 Bytes |
| --- | ---: | ---: |
| Precomposed `é` | 1 | 2 |
| Letter `e` + combining accent | 2 | 3 |

In an `AL32UTF8` database, you can test using expressions built from Unicode escapes:

~~~sql
SELECT
    LENGTH(CAST(UNISTR('\00E9') AS VARCHAR2(20 CHAR)))    AS precomposed_len,
    LENGTHB(CAST(UNISTR('\00E9') AS VARCHAR2(20 CHAR)))   AS precomposed_bytes,
    LENGTH(CAST(UNISTR('e\0301') AS VARCHAR2(20 CHAR)))   AS decomposed_len,
    LENGTHB(CAST(UNISTR('e\0301') AS VARCHAR2(20 CHAR)))  AS decomposed_bytes
FROM dual;
~~~

The expected values are **1/2** and **2/3** respectively. This is why a UI limit counted in "user-visible characters" sometimes disagrees with the code point count enforced by the database or driver.

**Recommendation:** If the application needs Vietnamese strings stored consistently, establish a Unicode normalization policy (typically NFC) in the ingestion/application layer and test round-trips. Do not assume `VARCHAR2(n CHAR)` or `LENGTHC` replaces a full grapheme cluster library across all languages and composite emoji.

### 4.4. `SUBSTR` and `SUBSTRB`

The BYTE/CHAR distinction also appears in substring functions:

~~~sql
-- First two characters of a string using character semantics:
SELECT SUBSTR('Hà Nội', 1, 2) AS first_two_chars
FROM dual;

-- String sliced by bytes; may be unsuitable for Unicode text:
SELECT SUBSTRB('Hà Nội', 1, 2) AS first_two_bytes
FROM dual;
~~~

For Vietnamese text, when business logic says "take the first two characters", `SUBSTR` is usually more appropriate than `SUBSTRB`. Slicing in the middle of a multi-byte code point can produce unexpected results depending on system conversion and handling. Never use `SUBSTRB` to enforce UI character limits.

Byte-based functions are useful for protocol codes, file formats, byte-bounded payloads, or diagnostics—not as the default for person names or addresses.

## 5. Lab: A Table with Both BYTE and CHAR Semantics

Run these steps in a lab schema granted `CREATE TABLE` inside a `READ WRITE` PDB. Before starting, verify the character set as shown in Section 3. The fixed results below apply only when the database uses `AL32UTF8` and the client sends valid Unicode.

### Step 1 — Create the practice table

~~~sql
CREATE TABLE vn_length_lab (
    id          NUMBER PRIMARY KEY,
    byte_label  VARCHAR2(6 BYTE),
    char_label  VARCHAR2(6 CHAR),
    code        VARCHAR2(6 BYTE)
);
~~~

Both `BYTE_LABEL` and `CHAR_LABEL` hold text, but with different length constraints. The `CODE` column intentionally uses `BYTE` because the example code is specified to contain only ASCII characters with an explicit byte length.

### Step 2 — Store ASCII strings

~~~sql
INSERT INTO vn_length_lab (id, byte_label, char_label, code)
VALUES (1, 'Ha Noi', 'Ha Noi', 'HN0001');

COMMIT;
~~~

Both `'Ha Noi'` values are **6 characters and 6 bytes**, fitting both column definitions.

### Step 3 — Store accented Vietnamese names

~~~sql
INSERT INTO vn_length_lab (id, byte_label, char_label, code)
VALUES (2, NULL, 'Hà Nội', 'HN0002');

COMMIT;
~~~

`'Hà Nội'` has 6 code points and 9 bytes in AL32UTF8/NFC; hence only `CHAR_LABEL` accepts it under the declared limits. `BYTE_LABEL` is left `NULL`.

### Step 4 — Intentionally trigger an error on the BYTE column

~~~sql
-- Expected ORA-12899 error with AL32UTF8/NFC:
INSERT INTO vn_length_lab (id, byte_label, char_label, code)
VALUES (3, 'Hà Nội', 'Hà Nội', 'HN0003');
~~~

In the sample environment, Oracle may report `ORA-12899: value too large for column` for `BYTE_LABEL`, because 9 actual bytes exceed the 6-byte limit. A failed `INSERT` **does not create half a row**: the entire statement is rejected. Do not enlarge the column just to make the demo error go away; the point of the exercise is understanding limit design.

### Step 5 — Query values and measure lengths

~~~sql
SELECT
    id,
    byte_label,
    char_label,
    LENGTH(char_label)  AS char_count,
    LENGTHB(char_label) AS byte_count
FROM vn_length_lab
ORDER BY id;
~~~

Expected output:

| ID | BYTE_LABEL | CHAR_LABEL | CHAR_COUNT | BYTE_COUNT |
| --- | --- | --- | ---: | ---: |
| 1 | `Ha Noi` | `Ha Noi` | 6 | 6 |
| 2 | `NULL` | `Hà Nội` | 6 | 9 |

`NULL` is written out as text for readability; in SQL output, NULL usually displays blank. Row ID=3 does not appear because the error test failed.

### Step 6 — Inspect metadata for both columns

~~~sql
SELECT
    column_name,
    data_type,
    data_length,
    char_length,
    char_used
FROM user_tab_columns
WHERE table_name = 'VN_LENGTH_LAB'
ORDER BY column_id;
~~~

In the Oracle data dictionary:

- `DATA_LENGTH` reflects the **maximum length in bytes** recorded in metadata for the column definition.
- `CHAR_LENGTH` reflects character-unit length metadata for character types, though it **should not be used alone** to assume multi-byte strings will fit in a `BYTE`-semantics column.
- `CHAR_USED = 'B'` means the column was declared in **BYTE**.
- `CHAR_USED = 'C'` means the column was declared in **CHAR**.

With `AL32UTF8`, `CHAR_LABEL VARCHAR2(6 CHAR)` can show `DATA_LENGTH=24` reflecting up to four bytes per code point, whereas `BYTE_LABEL VARCHAR2(6 BYTE)` shows `DATA_LENGTH=6`. **`DATA_LENGTH` is not how many bytes a row actually uses.** `VARCHAR2` stores only the actual length of each value under Oracle's storage format; it does not reserve 24 bytes for every row.

### Step 7 — Drop the demo table when no longer needed

~~~sql
-- Only run on the lab table you created and confirmed no longer needs data.
DROP TABLE vn_length_lab;
~~~

Oracle DDL commits according to database mechanics; do not treat `DROP TABLE` as a test you can undo with `ROLLBACK`. Keep the table if you want to inspect its metadata in later sections.

## 6. `NLS_LENGTH_SEMANTICS`: Default When BYTE/CHAR Is Omitted

### 6.1. Why Can `VARCHAR2(30)` Cause Surprises?

When declaring:

~~~sql
CREATE TABLE customer_example (
    full_name VARCHAR2(30)
);
~~~

The DDL does not state `BYTE` or `CHAR`. Oracle takes the default length semantics from **`NLS_LENGTH_SEMANTICS` of the session creating the object** (with certain exceptions such as objects created by `SYS`).

Inspect it:

~~~sql
SHOW PARAMETER nls_length_semantics;

SELECT value
FROM nls_session_parameters
WHERE parameter = 'NLS_LENGTH_SEMANTICS';
~~~

Supported values are `BYTE` or `CHAR`; the default is typically `BYTE`. Two deployment sessions running the exact same `CREATE TABLE ... VARCHAR2(30)` with different session settings can create two columns with different length semantics.

### 6.2. Changing the Session Default

In your own lab schema:

~~~sql
-- Change default for DDL created after this command in the session.
ALTER SESSION SET NLS_LENGTH_SEMANTICS = CHAR;

CREATE TABLE implicit_char_lab (
    viet_name VARCHAR2(30),
    byte_code VARCHAR2(10 BYTE)
);

SELECT column_name, data_length, char_length, char_used
FROM user_tab_columns
WHERE table_name = 'IMPLICIT_CHAR_LAB'
ORDER BY column_id;

-- Restore the lab's target value.
ALTER SESSION SET NLS_LENGTH_SEMANTICS = BYTE;
~~~

In this example:

- `VIET_NAME VARCHAR2(30)` is created with `CHAR` semantics due to the session default when the DDL ran.
- `BYTE_CODE VARCHAR2(10 BYTE)` still uses `BYTE` because an **explicit declaration takes precedence**.
- Switching the session back to `BYTE` **does not retroactively change already-created columns** to `VARCHAR2(30 BYTE)`.

To restore the exact original session configuration, record its value beforehand and reset to that value; do not assume every session starts at `BYTE`.

### 6.3. Why Should You Not Change the Instance-Wide Parameter Just to Support Vietnamese?

Oracle recommends **specifying `BYTE`/`CHAR` explicitly in DDL** when the goal is documenting column intent and avoiding environment dependence. Changing `NLS_LENGTH_SEMANTICS` to `CHAR` instance-wide can cause legacy scripts to unexpectedly create larger columns, introduce metadata drift, or break code/migrations that assumed byte semantics.

Key points:

- The **session** parameter controls the default for non-explicit declarations created in that session; it is not a live data validation limit on existing columns.
- The `SYS` account has special default rules and must not be used to create application tables.
- Clients, migration tools, and drivers may initialize sessions differently. Query the actual session running DDL rather than looking only at instance configuration.
- `NLS_LENGTH_SEMANTICS` **does not change the database character set**, does not convert data to UTF-8, and does not raise the maximum byte limit of SQL datatypes.

In projects using schema versioning, explicit DDL is easier to test and reproduce:

~~~sql
CREATE TABLE customer_profile (
    customer_id   NUMBER PRIMARY KEY,
    full_name     VARCHAR2(120 CHAR) NOT NULL,
    contact_code  VARCHAR2(32 BYTE)
);
~~~

Each column states its intent clearly; regardless of whether the session's `NLS_LENGTH_SEMANTICS` is `BYTE` or `CHAR`, these two definitions keep the semantics written here.

## 7. Maximum Byte Limit of `VARCHAR2` and the Real Meaning of CHAR

A common misconception is: "`VARCHAR2(4000 CHAR)` is guaranteed to store any 4,000 Unicode characters." This is false when values must obey the maximum byte limit of `VARCHAR2` in SQL.

### 7.1. `MAX_STRING_SIZE`

For **`VARCHAR2` SQL columns**, the absolute byte limit depends on `MAX_STRING_SIZE`:

| `MAX_STRING_SIZE` | Max Byte Limit of a `VARCHAR2` Value in SQL |
| --- | ---: |
| `STANDARD` | 4,000 bytes |
| `EXTENDED` | 32,767 bytes |

Check in an environment where you have privileges:

~~~sql
SHOW PARAMETER max_string_size;
~~~

Even when a column is declared with `CHAR`, an actual value cannot exceed the applicable byte ceiling. For example, with `AL32UTF8` and `MAX_STRING_SIZE=STANDARD`, 2,000 three-byte characters require around 6,000 bytes; that value **will not fit** in a SQL `VARCHAR2(2000 CHAR)` column even though the character count equals the declared limit.

Meanwhile, `VARCHAR2(100 CHAR)` with at most 4 bytes per code point requires at most about 400 bytes, well below the 4,000-byte ceiling of `STANDARD`. Sizing columns appropriately to business needs makes the data model far more predictable.

**Do not extrapolate SQL ceilings from PL/SQL:** `VARCHAR2` variables in PL/SQL have different size rules/limits than `VARCHAR2` columns in SQL tables. A string processed inside PL/SQL may not fit into a SQL table column.

### 7.2. CHAR Is a Character Constraint, Not a Guarantee That Every Unicode String Fits

In Oracle `VARCHAR2(n CHAR)`:

1. There is a limit of **n characters/code points** under the datatype and database character set semantics.
2. There is still a maximum byte limit enforced by **`MAX_STRING_SIZE`** and the column definition.
3. Actual bytes depend on data, Unicode normalization, and character set.

Therefore, "change everything to CHAR" is not enough to size columns properly. Classify by business use: person names, addresses, long notes, ASCII codes, or JSON payloads all have different needs.

### 7.3. When Should You Use `CLOB`?

If a value is **long text content** such as document descriptions, articles, multi-page notes, or text that can exceed `VARCHAR2` limits, consider `CLOB`:

~~~sql
CREATE TABLE vietnamese_documents (
    document_id NUMBER PRIMARY KEY,
    title       VARCHAR2(200 CHAR) NOT NULL,
    body_text   CLOB
);
~~~

`CLOB` uses the database character set and is designed for large character data; `NCLOB` uses the national character set. They have different storage, access patterns, and API limits than `VARCHAR2`. For CLOB, `DBMS_LOB.GETLENGTH(clob_column)` returns length in **characters**; `LENGTHB` is not directly supported on multibyte CLOBs the way it is for `VARCHAR2`. Do not replace every `VARCHAR2` with `CLOB`, because searching, indexing, constraints, and performance must be designed intentionally.

## 8. Fixed `CHAR`, Variable `VARCHAR2`, and `NCHAR/NVARCHAR2`

### 8.1. How Does `CHAR(10 CHAR)` Differ from `VARCHAR2(10 CHAR)`?

In both types, `(10 CHAR)` refers to **character-based length units**, but:

| Column Type | Storage of Values Shorter Than Declared Length | Better Suited For |
| --- | --- | --- |
| `CHAR(10 CHAR)` | Oracle **pads with spaces** to a fixed 10-character length | Truly fixed-length codes, some legacy structures |
| `VARCHAR2(10 CHAR)` | Does not pad spaces up to declared length | Names, labels, addresses, variable-length short text |

Example:

~~~sql
CREATE TABLE fixed_vs_variable (
    fixed_code CHAR(5 CHAR),
    person_name VARCHAR2(5 CHAR)
);

INSERT INTO fixed_vs_variable VALUES ('AB', 'AB');

SELECT
    LENGTH(fixed_code)  AS fixed_chars,
    LENGTH(person_name) AS variable_chars
FROM fixed_vs_variable;
~~~

With `'AB'`, `FIXED_CODE` is typically 5 characters long because of 3 padding spaces, whereas `PERSON_NAME` is 2 characters long. `LENGTH` on `CHAR` includes trailing spaces. Account for **blank-padding and comparison semantics** when choosing `CHAR`; never pick it thinking "`CHAR` supports Unicode better than `VARCHAR2`".

### 8.2. `NVARCHAR2(n)` and the National Character Set

`NVARCHAR2(n)` uses the **national character set** and has **character** semantics, without adding `BYTE`/`CHAR` in the declaration like `VARCHAR2`:

~~~sql
CREATE TABLE national_text_lab (
    id          NUMBER PRIMARY KEY,
    regular_vn  VARCHAR2(50 CHAR),
    national_vn NVARCHAR2(50)
);
~~~

Both can store Vietnamese **when the database character set supports Unicode**, such as `AL32UTF8`. `NVARCHAR2` helps in specific compatibility scenarios or when the existing database character set lacks full Unicode support, but it brings national character set transcoding, byte limits, and dedicated driver/application considerations. **Do not use `NVARCHAR2` as a default bandage for `ORA-12899` errors.**

`NLS_LENGTH_SEMANTICS` only sets the default for applicable character-type declarations; it does not switch `NCHAR/NVARCHAR2` to byte semantics. For national character types, length units are already characters.

## 9. Designing Vietnamese Storage by Field Type

| Data Field | Suggested Type | Why |
| --- | --- | --- |
| Customer full name | `VARCHAR2(120 CHAR)` | Business limits are usually in characters; may contain Vietnamese accents |
| District name, shipping address | `VARCHAR2(255 CHAR)` or business-appropriate limit | Multilingual data and variable length |
| ASCII-only customer code | `VARCHAR2(32 BYTE)` plus validation | Explicit byte bound, though **BYTE does not forbid Unicode characters by itself** |
| Email | `VARCHAR2(n CHAR)` or designed per relevant protocol/system limits | Distinguish Unicode characters from protocol byte limits |
| Short description | `VARCHAR2(500 CHAR)` if within SQL byte cap | Input capped by code points |
| Long content / articles | `CLOB` | Not constrained by small `VARCHAR2` caps |
| International strings using national charset by specific requirement | `NVARCHAR2(n)` | Meaningful when the system genuinely requires the national character set |

These are **data modeling suggestions**, not mandatory standard sizes. Real decisions also depend on data lengths, whether emoji may appear, collations, indexes, upstream/downstream systems, UX validation, integration protocols, and historical data retention.

### 9.1. BYTE Does Not Mean ASCII-Only

A `VARCHAR2(20 BYTE)` column can store several multi-byte Unicode characters as long as total bytes do not exceed 20. If business rules state an identifier contains only `A-Z`, `0-9`, `_`, or `-`, you must **enforce content rules separately** with validation or an appropriate constraint:

~~~sql
CREATE TABLE product_code_lab (
    code VARCHAR2(20 BYTE)
        CONSTRAINT ck_product_code_ascii
        CHECK (REGEXP_LIKE(code, '^[A-Z0-9_-]+$'))
);
~~~

This example constraint restricts characters via a regular expression; it does not arise automatically from `BYTE` semantics. If the column needs a primary key or `NOT NULL`, declare those as well per business rules.

### 9.2. Sizing from Real Data

Before altering a production schema, collect:

1. Character and byte lengths of **existing data**.
2. Sample data that must be supported: NFC Vietnamese names, decomposed diacritics, international names, emoji, or non-BMP characters.
3. Limits imposed by protocols/APIs, UI, ingestion pipelines, and storage policies.
4. Indexes, constraints, unique keys, or external interfaces depending on the column definition.
5. Actual current DDL and `CHAR_USED`/`DATA_LENGTH` rather than guessing from an admin UI.

Example profiling query:

~~~sql
-- Replace CUSTOMERS/FULL_NAME with the actual table/column.
SELECT
    MAX(LENGTH(full_name))  AS max_char_count,
    MAX(LENGTHB(full_name)) AS max_byte_count,
    COUNT(*)                AS row_count
FROM customers;
~~~

If `NULL` values exist, `LENGTH` and `LENGTHB` of NULL are also NULL; `MAX` ignores NULL. Also inspect percentile distributions near the limit, not just the maximum value, when deciding on a column-widening policy.

## 10. Java, JDBC, and Unicode Normalization Connections

### 10.1. Java `String.length()` Does Not Always Equal Code Point Count

Java stores strings as **UTF-16 code units**, so:

~~~java
String text = "Hà Nội";

int utf16Units = text.length();
int codePoints = text.codePointCount(0, text.length());
int utf8Bytes = text.getBytes(java.nio.charset.StandardCharsets.UTF_8).length;

System.out.println("UTF-16 units: " + utf16Units);
System.out.println("Code points: " + codePoints);
System.out.println("UTF-8 bytes: " + utf8Bytes);
~~~

For the NFC string `Hà Nội`, both `utf16Units` and `codePoints` are 6, while `utf8Bytes` is 9. For non-BMP emoji, `String.length()` can be 2 for a single code point because UTF-16 uses a surrogate pair. In applications validating character limits for Oracle `VARCHAR2(n CHAR)`, `codePointCount` can be a better match than `String.length()` in this case.

However, the UI's **grapheme cluster** count can still differ from Unicode code points, especially with combining diacritics or multi-part emoji. If a limit is specified as "user-visible characters", choose an appropriate Unicode/grapheme segmentation library.

### 10.2. Normalizing Unicode Before Storing When Needed

Java provides `java.text.Normalizer`:

~~~java
import java.text.Normalizer;

String raw = requestName;
String normalized = Normalizer.normalize(raw, Normalizer.Form.NFC);

int codePoints = normalized.codePointCount(0, normalized.length());
byte[] encodedUtf8 = normalized.getBytes(
        java.nio.charset.StandardCharsets.UTF_8);

if (codePoints > 120) {
    throw new IllegalArgumentException("Name exceeds 120 code points");
}

// After validation, bind the value via PreparedStatement/JPA.
~~~

Normalization should be an **explicit design decision**, applied consistently across ingestion, search, comparison, and import. Historical data may contain decomposed strings; changing normalization can affect unique constraints, searches, and integrated feeds.

### 10.3. Bind Parameters Instead of SQL String Concatenation

JDBC:

~~~java
String sql = """
    INSERT INTO customer_profile(customer_id, full_name)
    VALUES (?, ?)
    """;

try (java.sql.PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setLong(1, customerId);
    ps.setString(2, normalized);
    ps.executeUpdate();
}
~~~

`PreparedStatement` separates data from SQL syntax, prevents SQL injection, and lets the driver handle proper type/charset conversion. It **does not bypass BYTE/CHAR limits**: the database can still raise `ORA-12899` if the value exceeds the column definition.

Oracle JDBC Thin handles transcoding inside the driver and typically does not depend on `NLS_LANG` the way OCI/native clients do; verify your driver version and application settings. When SQL*Plus displays accents wrong while JDBC displays them right, inspect each client's character pipeline **separately**.

## 11. Common Errors and How to Diagnose Them

| Symptom | Possible Cause | Check / Resolution |
| --- | --- | --- |
| `ORA-12899: value too large for column` | Value exceeds column BYTE or CHAR limit, or datatype byte cap | `USER_TAB_COLUMNS.CHAR_USED`, `DATA_LENGTH`; `LENGTH`/`LENGTHB` of data; redesign limit if needed |
| Vietnamese text replaced by `?` or garbled characters | Wrong encoding during input/conversion, client charset, or import/export | Check `NLS_CHARACTERSET`, terminal/file/driver pipeline, source data, and round-trip |
| `Ha Noi` saves fine, `Hà Nội` fails | Column too tight in bytes for a multi-byte charset | Compare `LENGTHB` vs. column limit; consider explicit `CHAR` |
| `VARCHAR2(2000 CHAR)` still rejects 2,000 multi-byte Unicode chars | Hit total byte ceiling of `VARCHAR2` (e.g., 4,000 in STANDARD) | Check `MAX_STRING_SIZE` and actual byte count; consider `CLOB` |
| Column declared `VARCHAR2(30)` differs between env A and env B | Different session `NLS_LENGTH_SEMANTICS` when DDL ran | Compare `NLS_SESSION_PARAMETERS` and `USER_TAB_COLUMNS`; write explicit `BYTE`/`CHAR` |
| Strings look identical yet have different lengths | NFC/NFD or combining characters | Inspect code points/bytes with `LENGTH`/`LENGTHB`/`DUMP`; standardize normalization |
| Byte-based truncation corrupts letters | Using byte counts or byte slicing on Unicode text | Use character/code-point or grapheme-aware APIs for UI |
| Measuring `LENGTHB` on CLOB fails | `LENGTHB` has restrictions on multibyte CLOBs | Use `DBMS_LOB`/appropriate APIs for the measurement goal |
| Expanding column triggers index/key size error | Index key, expression, or dependent object limits | Evaluate indexes/constraints and migration plan; do not change blindly globally |
| SQL*Plus and Java display different results | Different client encode/decode paths | Test sample Unicode data, check DB charset, verify file/console and JDBC |

### 11.1. Triage Workflow for `ORA-12899`

Suppose inserting `Hà Nội` into `CUSTOMERS.FULL_NAME` fails.

**Step 1 — Inspect actual column metadata:**

~~~sql
SELECT
    column_name, data_type, data_length, char_length, char_used
FROM user_tab_columns
WHERE table_name = 'CUSTOMERS'
  AND column_name = 'FULL_NAME';
~~~

**Step 2 — Check database character set and session settings:**

~~~sql
SELECT parameter, value
FROM nls_database_parameters
WHERE parameter = 'NLS_CHARACTERSET';

SELECT parameter, value
FROM nls_session_parameters
WHERE parameter = 'NLS_LENGTH_SEMANTICS';
~~~

**Step 3 — Measure input along the exact ingestion path:**

~~~sql
SELECT LENGTH('Hà Nội') AS n_chars,
       LENGTHB('Hà Nội') AS n_bytes
FROM dual;
~~~

If the application passes the value via a bind parameter, capture controlled diagnostic logs or test an equivalent input; never log sensitive personal data to public logs. Ensure the string reaches the database in the right encoding before comparing sizes.

**Step 4 — Apply the fix in the right place:**

- If the business limit is in characters and data exceeds current byte capacity, consider increasing size or switching to explicit `CHAR` after impact analysis.
- If the input genuinely exceeds business limits, keep the constraint and return a proper validation error.
- If accents were corrupted by transcoding, fix the encoding pipeline first; widening a column cannot repair corrupted characters.
- If it exceeds the `VARCHAR2` ceiling, evaluate `CLOB` or another storage design.

Modifying existing columns may require `ALTER TABLE ... MODIFY` and impose requirements on data, indexes, views, APIs, locking duration, or downtime. Never run such changes on production based on a single error example alone.

### 11.2. When Vietnamese Data Displays as Garbled Characters

A string turning into `HÃ  Ná»™i` or question marks may stem from UTF-8 being decoded with the wrong encoding or characters unrepresentable along a transcoding path. Depending on where the fault lies:

1. If the string was **already stored corrupted**, changing client NLS settings afterward will not automatically repair old data.
2. If the data is **stored correctly and only displays wrong**, prioritize checking fonts, terminal encoding, code page, native client `NLS_LANG`, export format, and rendering pipeline.
3. If CSV import/export files break accents, check the encoding of **both source and target files**, tool settings, and charset mapping—not just the column type.
4. If JDBC and SQL*Plus disagree, inspect each client individually instead of assuming both share the same environment.

When diagnosing, a test string containing `à`, `ộ`, `đ`, and non-ASCII characters helps pinpoint the bug; compare `LENGTHB`, `DUMP`, and the raw bytes of the file/input.

## 12. Design Rules to Remember

**Rule 1 — Specify units explicitly:** `VARCHAR2(100 BYTE)` is at most 100 bytes; `VARCHAR2(100 CHAR)` is at most 100 code points per Oracle semantics, still subject to the absolute byte limit.

**Rule 2 — Prefer explicit declarations:** DDL should specify `BYTE`/`CHAR` on every column where semantics matter. This avoids depending on the migration session's `NLS_LENGTH_SEMANTICS`.

**Rule 3 — Vietnamese requires consistent Unicode:** `AL32UTF8` handles multilingual text well; clients/imports/exports must also preserve Unicode. `CHAR` semantics alone do not protect against broken encoding.

**Rule 4 — Use functions for their intended purpose:** `LENGTH` measures characters, `LENGTHB` measures bytes; UI grapheme counting may require dedicated Unicode algorithms.

**Rule 5 — Check metadata:** `USER_TAB_COLUMNS.CHAR_USED` reveals whether a column actually uses `B` or `C`. Do not infer from type names or UI display.

**Rule 6 — Do not use CHAR in place of CLOB:** Very long text needs a CLOB strategy; changing `VARCHAR2(4000 BYTE)` to `VARCHAR2(4000 CHAR)` does not remove SQL's byte ceiling.

**Rule 7 — Test with real accented data:** Testing only ASCII names misses byte-semantics bugs. Include at least a string like `Hà Nội`, a three-byte character, and a combining Unicode sequence in test datasets.

## 13. Review Questions

1. In an `AL32UTF8` database, why can `'Ha Noi'` be stored in `VARCHAR2(6 BYTE)` while `'Hà Nội'` cannot?
2. Does `VARCHAR2(50 CHAR)` always guarantee storing any string of exactly 50 code points if `MAX_STRING_SIZE=STANDARD`? When does the byte limit still matter?
3. Does `VARCHAR2(20)` default to BYTE or CHAR? Where can you check which semantics an existing column actually uses?
4. Does changing `NLS_LENGTH_SEMANTICS` automatically convert existing columns to the new semantics?
5. If `'ộ'` is a single Unicode code point, why can `LENGTH('ộ')` and `LENGTHB('ộ')` return 1 and 3?
6. Why is a user-visible character not always equal to one code point? Give an example of Unicode normalization.
7. When using `VARCHAR2` in an `AL32UTF8` database, do you need to switch to `NVARCHAR2` solely to store Vietnamese?
8. How do `CHAR(10 CHAR)` and `VARCHAR2(10 CHAR)` differ when storing `'AB'`?
9. Why can calling `LENGTHB` directly on a multibyte CLOB be unsuitable? What approach should you take?
10. Why does a "BYTE column for ASCII codes" still need validation to truly forbid non-ASCII characters?
11. Is Java `String.length()` always equal to the code point count Oracle counts for `AL32UTF8`?
12. If Vietnamese turns into `?` characters in an import file, will changing `VARCHAR2(20 BYTE)` to `VARCHAR2(100 CHAR)` guarantee a fix?

**Answer key:** (1) 6 bytes vs. 9 bytes for NFC data; (2) no, the byte cap still applies; (3) the session's `NLS_LENGTH_SEMANTICS` at creation time, verified via `CHAR_USED` metadata; (4) no; (5) UTF-8 encodes `ộ` in 3 bytes; (6) precomposed `é` vs. `e` plus combining mark; (7) no if the database charset supports Unicode; (8) `CHAR` pads spaces, `VARCHAR2` does not; (9) use `DBMS_LOB.GETLENGTH`/APIs for character length and appropriate tools when bytes are needed; (10) BYTE only restricts storage capacity, not the allowed character set; (11) no, Java counts UTF-16 code units; (12) no, you must fix the transcoding pipeline and check the source data.

## Oracle References

- [Oracle SQL Language Reference — Data Types](https://docs.oracle.com/en/database/oracle/oracle-database/26/sqlrf/Data-Types.html): `VARCHAR2(size BYTE|CHAR)` syntax, byte limits, `CHAR`, and `NVARCHAR2`.
- [Oracle Database Globalization Support Guide — Choosing a Character Set](https://docs.oracle.com/en/database/oracle/oracle-database/26/nlspg/choosing-character-set.html): `AL32UTF8` encoding, character semantics, and Unicode selection.
- [Oracle SQL Language Reference — LENGTH](https://docs.oracle.com/en/database/oracle/oracle-database/26/sqlrf/LENGTH.html): `LENGTH`, `LENGTHB`, `LENGTHC`, `LENGTH2`, and `LENGTH4`.
- [Oracle Database Reference — NLS_LENGTH_SEMANTICS](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/NLS_LENGTH_SEMANTICS.html): session defaults and effect on new column definitions.
- [Oracle Database Reference](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/): `USER_TAB_COLUMNS` and related configuration parameters.
