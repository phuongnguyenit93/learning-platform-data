# CHAR, VARCHAR2, NCHAR, and NVARCHAR2 in Oracle Database

## 1. What Problem Do the Four Character Data Types Solve?

A Java application may need to store status codes, customer names, phone numbers, addresses, and multilingual content. In Oracle Database, the four common data types for bounded-length strings are **`CHAR`**, **`VARCHAR2`**, **`NCHAR`**, and **`NVARCHAR2`**. They differ along two axes:

1. **Fixed or variable length**: does it automatically pad with spaces up to the declared length, or store only the actual length of the value?
2. **Character set used**: is it stored using Oracle's *database character set* or *national character set*?

| Data Type | Length | Storage Character Set | Best Used When |
|---|---|---|---|
| `CHAR(n [BYTE\|CHAR])` | **Fixed**; space-padded when shorter than the declared length | Database character set | Codes that truly have fixed length; requires understanding padding effects |
| `VARCHAR2(n [BYTE\|CHAR])` | **Variable**; not padded up to the declared maximum | Database character set | Names, short descriptions, codes, emails, and most application string data |
| `NCHAR(n)` | **Fixed**, space-padded | National character set | Cases genuinely requiring fixed national strings under an existing design |
| `NVARCHAR2(n)` | **Variable** | National character set | Cases requiring storage in the database's separate national character set |

Conceptual example:

```text
Storing the string "AB":

CHAR(5 CHAR)       -> value like "AB   " (padded with 3 spaces)
VARCHAR2(5 CHAR)   -> value "AB"      (unpadded)
NCHAR(5)           -> value like "AB   " (in national character set)
NVARCHAR2(5)       -> value "AB"      (in national character set)
```

With `CHAR` and `NCHAR`, padding can affect `LENGTH`, comparisons, string concatenation, and how the application receives data. With `VARCHAR2` and `NVARCHAR2`, the declared length is a **limit**, not a guarantee that Oracle can always hold that many characters.

In an environment using **`AL32UTF8` as the database character set**, `VARCHAR2` already supports Vietnamese and appropriate Unicode characters. You do not need to default to `NVARCHAR2` merely because the application has Vietnamese data.

## 2. Two Axes to Remember: Fixed/Variable and Database/National Character Set

Conceptual diagram:

```text
                       ORACLE STRING DATA TYPES
                                  |
                  +---------------+----------------+
                  |                                |
         Database character set          National character set
                  |                                |
           +------+-------+                 +------+-------+
           |              |                 |              |
        Fixed          Variable           Fixed          Variable
           |              |                 |              |
         CHAR           VARCHAR2          NCHAR         NVARCHAR2
```

The **fixed/variable axis** determines padding rules and actual length storage. The **character set axis** determines how characters are encoded into bytes, data conversion behavior, and how byte limits apply.

A single table can contain all four types simultaneously; there is no need to create a separate database for `NCHAR` or `NVARCHAR2` columns.

## 3. `CHAR`: Fixed-Length Strings

### 3.1. Syntax

```sql
CHAR(size BYTE)
CHAR(size CHAR)
CHAR(size)
CHAR
```

`size` is the declared length; syntax omitting `BYTE`/`CHAR` takes the environment's default length semantics. If no size is specified, `CHAR` defaults to length **1** under the applicable character/byte semantics.

Example:

```sql
CREATE TABLE demo_fixed_code (
    country_code CHAR(2 CHAR) NOT NULL,
    state_code   CHAR(4 BYTE)
);
```

`CHAR(2 CHAR)` allows up to two character units under Oracle character semantics, provided the value does not exceed the data type's byte limit. `CHAR(4 BYTE)` restricts to four bytes in the database character set; if characters require multiple bytes, fewer than four characters may fit.

### 3.2. Space-Padding Mechanism

When assigning `'AB'` to a `CHAR(5 CHAR)` column, Oracle stores a fixed-length value with trailing spaces padded to the declared length:

```sql
CREATE TABLE demo_char_padding (
    fixed_text CHAR(5 CHAR)
);

INSERT INTO demo_char_padding (fixed_text) VALUES ('AB');
COMMIT;

SELECT fixed_text, LENGTH(fixed_text) AS length_chars
FROM demo_char_padding;
```

`LENGTH(fixed_text)` typically returns **5**, not 2, because the padding spaces belong to the representation of the `CHAR` value. When an application reads the column, it must account for trailing spaces.

The padding characters are **space** characters used by Oracle, not `0` bytes or `NULL`. Using `RTRIM` can strip trailing spaces, but it can also strip **meaningful spaces** that came from source data; do not blindly trim every column without checking business rules.

### 3.3. When to Use `CHAR`?

Some codes with a standardized fixed length, such as two-character country codes, can use `CHAR(2 CHAR)`. However, the choice also involves comparison, input handling, integration, and indexing needs. In many cases, using `VARCHAR2(2 CHAR)` with a length constraint is more convenient for the backend:

```sql
CREATE TABLE demo_country_code (
    code VARCHAR2(2 CHAR)
         CONSTRAINT ck_demo_country_code_len CHECK (LENGTH(code) = 2)
);
```

If you need to guarantee that a code is exactly two characters long and disallow invalid spaces, design the necessary validation rules. **`CHAR(2)` alone does not prove input data had two meaningful characters**, because Oracle pads shorter strings.

## 4. `VARCHAR2`: Variable-Length Strings

### 4.1. Syntax and Behavior

```sql
VARCHAR2(size BYTE)
VARCHAR2(size CHAR)
VARCHAR2(size)
```

`VARCHAR2` requires declaring a positive size within the limits supported by the Oracle version/configuration. It stores only the actual value, **without automatically adding spaces** up to the maximum size.

Example:

```sql
CREATE TABLE demo_customer_text (
    customer_code VARCHAR2(20 CHAR) NOT NULL,
    full_name     VARCHAR2(100 CHAR) NOT NULL,
    email         VARCHAR2(254 CHAR)
);
```

If `full_name` stores `'Lan'`, its logical length is three characters; Oracle does not append 97 spaces. If it stores `'Nguyễn Lan'`, the actual byte count depends on the database character set, whereas the `100 CHAR` limit describes size in character semantics rather than 100 bytes.

### 4.2. How Does `VARCHAR2` Differ from `VARCHAR`?

Oracle currently treats `VARCHAR` as synonymous with `VARCHAR2` in common contexts, yet Oracle documentation recommends **using `VARCHAR2`** because `VARCHAR` semantics may be reserved for future changes. When creating new schemas, prefer writing `VARCHAR2` explicitly to avoid unnecessary reliance on an alias.

### 4.3. Does `VARCHAR2` Automatically Solve Every Unicode Issue?

Not completely. Whether data stores characters properly also depends on:

- The database **`NLS_CHARACTERSET`**: for example, `AL32UTF8` supports Unicode.
- **How programs connect and send strings**: drivers/clients must transmit characters properly to avoid transcoding errors on input.
- **Declared length** and the type's byte limit: `100 CHAR` does not mean Oracle ignores byte limits.
- **Collation and comparison rules**: Unicode encoding alone does not dictate whether comparisons are case-sensitive or accent-sensitive.

With database character set `AL32UTF8`, `VARCHAR2(100 CHAR)` is a common choice for Vietnamese names with diacritics. With legacy database character sets unable to represent certain characters, choosing `VARCHAR2` alone may not suffice; evaluate the character set and data strategy of the entire system.

## 5. `NCHAR`: Fixed-Length Strings in the National Character Set

`NCHAR` follows the same **fixed-length and space-padding** principle as `CHAR`, except the data is stored in Oracle's **national character set**.

```sql
CREATE TABLE demo_national_fixed (
    n_code NCHAR(5)
);
```

When inserting a value shorter than five character units, Oracle pads it to the fixed length according to the type's rules. Unlike `CHAR`, the size of `NCHAR(n)` is declared in **character semantics**, without `BYTE`/`CHAR` unit modifiers like `CHAR` or `VARCHAR2`.

Related forms such as `NATIONAL CHAR` or `NATIONAL CHARACTER` belong to Oracle's national character data type declarations.

Data example:

```sql
INSERT INTO demo_national_fixed (n_code)
VALUES (N'AB');
```

`N'AB'` is a **national character literal**. To preserve Unicode characters when writing accented literals in scripts, pay attention to file encoding, driver/client settings, and transcoding rules. In applications using bind variables, let the driver pass strings with the right type rather than building literals via string concatenation.

**Note:** `NCHAR` is not a "free unlimited Unicode" type. The national character set may consume more bytes per character; the type is still subject to byte limits. And just like `CHAR`, trailing padding spaces can complicate string processing and comparison logic.

## 6. `NVARCHAR2`: Variable-Length Strings in the National Character Set

`NVARCHAR2` is the **variable-length** character type in the **national character set**:

```sql
CREATE TABLE demo_national_variable (
    display_name NVARCHAR2(80),
    note         NVARCHAR2(200)
);
```

`NVARCHAR2(80)` declares maximum length in **character semantics** for this data type. When storing `'Lan'`, Oracle does not pad trailing spaces like `NCHAR`.

Example using national literals:

```sql
INSERT INTO demo_national_variable (display_name, note)
VALUES (N'Lan', N'Display name');
```

This choice makes sense when you must work with national character set columns due to legacy requirements, cross-system compatibility, or a specific architectural policy. If the database already uses `AL32UTF8`, the more common choice for most new applications is **`VARCHAR2`**, unless there is a sound reason to separate into the national character set.

### Are `NCHAR` and `NVARCHAR2` Types Dedicated Specifically to Vietnamese?

No. The letter "N" refers to **national character set**, not "Vietnamese national language". Oracle maintains a dedicated national character set capable of representing characters from many languages. `VARCHAR2` on an `AL32UTF8` database can likewise store Vietnamese, Japanese, Korean, and many other languages.

## 7. Database Character Set and National Character Set

### 7.1. Database Character Set

The database character set is configured for the database and used by standard character types such as `CHAR`, `VARCHAR2`, and related character components.

Common example:

```text
NLS_CHARACTERSET = AL32UTF8
```

`AL32UTF8` is the UTF-8 Unicode encoding recommended by Oracle for many new databases. It supports multi-byte characters; therefore you cannot assume **one character always equals one byte**.

### 7.2. National Character Set

The national character set is the character set Oracle uses for `NCHAR`, `NVARCHAR2`, and `NCLOB`. Two common choices are **`AL16UTF16`** and **`UTF8`** by Oracle's naming. On many installations, the national character set is `AL16UTF16`. The name `UTF8` in the national character set context is an Oracle character set name with specific historical characteristics and should not be conflated with `AL32UTF8`.

```text
CHAR/VARCHAR2 types   -> NLS_CHARACTERSET
NCHAR/NVARCHAR2 types -> NLS_NCHAR_CHARACTERSET
```

Within a single database, these two character sets can differ. Oracle performs character conversion when exchanging data between types or expressions, depending on context.

### 7.3. Checking Configuration on the Connected Database

With appropriate dictionary access privileges:

```sql
SELECT parameter, value
FROM nls_database_parameters
WHERE parameter IN ('NLS_CHARACTERSET', 'NLS_NCHAR_CHARACTERSET')
ORDER BY parameter;
```

Sample output **for illustration only**:

```text
PARAMETER                  VALUE
-------------------------  --------
NLS_CHARACTERSET           AL32UTF8
NLS_NCHAR_CHARACTERSET     AL16UTF16
```

Actual environment values must be queried from the connected database. In a CDB/PDB architecture, pay attention to the right database/container and appropriate metadata access conditions.

### 7.4. Should Every Column Be Converted to `NVARCHAR2` to "Support Unicode"?

That should not be treated as a universal rule. In a database already using `AL32UTF8`, `VARCHAR2` is inherently Unicode-capable. Switching to `NVARCHAR2` can introduce extra character conversions, differences in byte limits, driver/ORM type-mapping quirks, and storage/index overhead depending on the data.

Changing a database character set or column types on a live system requires a migration plan and evaluation of data, indexes, constraints, and applications. Do not run character set modification commands on a whim just to fix a few misdisplayed characters.

## 8. `BYTE` vs. `CHAR`: Same Number 10, Potentially Different Limits

### 8.1. `VARCHAR2(10 BYTE)` vs. `VARCHAR2(10 CHAR)`

Example:

```sql
CREATE TABLE demo_length_semantics (
    text_by_bytes VARCHAR2(10 BYTE),
    text_by_chars VARCHAR2(10 CHAR)
);
```

Both columns specify `10`, yet:

- `text_by_bytes`: at most **10 bytes** after encoding in the database character set.
- `text_by_chars`: at most **10 characters** under Oracle character semantics, **still subject to the byte limit of the data type/column**.

With `AL32UTF8`, ASCII Latin letters usually take 1 byte, whereas accented Vietnamese characters often take multiple bytes. Hence a string that looks like "10 characters" may not fit into `VARCHAR2(10 BYTE)`.

Illustrative example of byte size:

```sql
SELECT LENGTH('ABC') AS char_count,
       LENGTHB('ABC') AS byte_count
FROM dual;
```

For an ASCII string on an `AL32UTF8` database, both values are typically 3. For a string with multi-byte characters, the two results can differ:

```sql
SELECT LENGTH('Tiếng Việt') AS char_count,
       LENGTHB('Tiếng Việt') AS byte_count
FROM dual;
```

For the example to be meaningful, both the script and client must pass Unicode characters properly; if data was already corrupted by encoding before reaching Oracle, all subsequent measurements reflect the corrupted string.

### 8.2. Why Does `10 CHAR` Still Have a Byte Limit?

`CHAR` limits express business requirements in character counts, but Oracle still has to encode them into bytes and enforce the maximum capacity permitted by the type/version. Some Unicode characters need more bytes than ASCII. Therefore, **declaring by characters does not make storage size infinite**.

For complex display glyphs such as emoji or letters with multiple combining marks, "one character the user sees" may also consist of multiple code points/code units. Do not assume every length function returns the exact count of *grapheme clusters* perceived by the user.

### 8.3. `NLS_LENGTH_SEMANTICS`

When `CHAR`/`VARCHAR2` omits `BYTE` or `CHAR`, the environment parameter **`NLS_LENGTH_SEMANTICS`** governs how unitless sizes are interpreted:

```sql
-- Can be viewed with SQL*Plus/SQLcl client command:
SHOW PARAMETER nls_length_semantics
```

Or depending on privileges/state:

```sql
SELECT parameter, value
FROM nls_session_parameters
WHERE parameter = 'NLS_LENGTH_SEMANTICS';
```

Example:

```sql
CREATE TABLE demo_implicit_length (
    code VARCHAR2(20)
);
```

Depending on the length semantics of the environment creating the table, `VARCHAR2(20)` may be interpreted in bytes or characters. For schemas serving multiple languages and deployed across environments, writing explicitly:

```sql
VARCHAR2(20 CHAR)
```

usually helps avoid dependence on the migration session's configuration. **`NCHAR` and `NVARCHAR2` are declared in character semantics**, without appending `BYTE` or `CHAR` after the length like the two standard types.

### 8.4. What Do Data Dictionary Columns Mean?

Oracle provides metadata to inspect how a specific column was declared. Example:

```sql
SELECT column_name,
       data_type,
       data_length,
       char_length,
       char_used
FROM user_tab_columns
WHERE table_name = 'DEMO_LENGTH_SEMANTICS'
ORDER BY column_id;
```

| Metadata Column | Meaning |
|---|---|
| `DATA_TYPE` | Column type: `CHAR`, `VARCHAR2`, `NCHAR`, `NVARCHAR2`... |
| `DATA_LENGTH` | Length in bytes recorded by Oracle for the column |
| `CHAR_LENGTH` | Length in character units recorded by Oracle |
| `CHAR_USED` | Indicates byte (`B`) or character (`C`) length semantics where applicable |

Reading actual metadata is more reliable than guessing from the original DDL script, especially when scripts ran across environments with different NLS settings.

## 9. Maximum Limits: Why Distinguish Bytes from Characters?

Character type limits also depend on the **`MAX_STRING_SIZE`** parameter and the character set.

| Type | Byte Ceiling in Common Configurations | Notes |
|---|---|---|
| `CHAR` | Up to **2,000 bytes** | Fixed-length; still depends on bytes per character required |
| `VARCHAR2` | **4,000 bytes** when `MAX_STRING_SIZE=STANDARD`; up to **32,767 bytes** when `EXTENDED` | Actual max characters depends on the character set |
| `NCHAR` | Up to **2,000 bytes** | Size declared in characters; byte consumption follows national character set |
| `NVARCHAR2` | **4,000 bytes** when `STANDARD`; up to **32,767 bytes** when `EXTENDED` | Size declared in characters, still subject to byte ceiling |

The byte limit is the type's ceiling; **do not assume you can always declare a character count equal to the maximum byte count**. With national character set `AL16UTF16`, for instance, common characters take two bytes while supplementary Unicode characters can take more; character size and byte limit must be considered together.

`MAX_STRING_SIZE=EXTENDED` does not automatically expand `CHAR`/`NCHAR` to 32,767 bytes. It is a database configuration with a formal setup procedure and system-wide impact; do not change it just to make a test `CREATE TABLE` succeed.

If you need to store very long text (tens of thousands or millions of characters), evaluate `CLOB` or `NCLOB` rather than stretching `VARCHAR2`/`NVARCHAR2` beyond design needs. Using LOBs also brings differences in access, drivers, indexing, and performance that should be studied separately.

## 10. Trailing Spaces: Storage and Comparison Are Two Separate Issues

### 10.1. How Are Values Padded?

Example table with two columns:

```sql
CREATE TABLE demo_spaces (
    fixed_value    CHAR(5 CHAR),
    varying_value  VARCHAR2(5 CHAR)
);

INSERT INTO demo_spaces (fixed_value, varying_value)
VALUES ('A', 'A');

COMMIT;
```

Observing lengths:

```sql
SELECT '[' || fixed_value || ']' AS fixed_display,
       '[' || varying_value || ']' AS varying_display,
       LENGTH(fixed_value) AS len_fixed,
       LENGTH(varying_value) AS len_varying
FROM demo_spaces;
```

Conceptual output:

```text
fixed_display    -> [A    ]
varying_display  -> [A]
len_fixed        -> 5
len_varying      -> 1
```

When concatenating strings, padding spaces inside `CHAR` can show through. If the system builds composite codes like `'ORDER-' || code`, automatic space padding can produce unexpected outputs unless handling is standardized.

### 10.2. Blank-Padded and Nonpadded Comparison Semantics

Oracle has **blank-padded** and **nonpadded** string comparison rules depending on the types of the two operands:

- When both operands belong to `CHAR`, `NCHAR`, string literals, or expressions matching Oracle's rules, comparisons may **pad the shorter side with spaces** before comparing.
- When at least one operand belongs to `VARCHAR2` or `NVARCHAR2`, Oracle applies **nonpadded comparison semantics** in standard comparisons; trailing spaces can make values unequal.

Example illustrating two literals with `CHAR` semantics:

```sql
SELECT CASE
           WHEN 'A' = 'A ' THEN 'EQUAL'
           ELSE 'DIFFERENT'
       END AS comparison_result
FROM dual;
```

Under Oracle's blank-padding rules for character literals, the result can be `EQUAL`. Conversely, to observe variable-length comparison, cast explicitly:

```sql
SELECT CASE
           WHEN CAST('A' AS VARCHAR2(1)) =
                CAST('A ' AS VARCHAR2(2))
           THEN 'EQUAL'
           ELSE 'DIFFERENT'
       END AS comparison_result
FROM dual;
```

Under nonpadded comparison, these two strings differ. This is an important example because developers sometimes assume **every string comparison in Oracle automatically ignores trailing spaces**; that is false.

Actual comparison behavior can also be affected by **collation**, `NLS_COMP`, `NLS_SORT`, or column/expression collation settings in supported versions. Never extrapolate from a single ASCII example that all multilingual data compares byte-for-byte.

### 10.3. `TRIM`, `RTRIM`, and Meaningful Data

One normalization approach used in applications:

```sql
SELECT RTRIM(fixed_value) AS code_without_padding
FROM demo_spaces;
```

However, `RTRIM` strips **trailing spaces**, including spaces that are genuinely part of business data. In systems that must preserve verbatim text content, distinguish fixed-type padding from user-entered whitespace.

If codes have strict length rules, a steadier design is usually `VARCHAR2` plus a check constraint rather than relying on `CHAR` to pad short inputs.

## 11. How Does Oracle Handle `NULL` and Empty Strings?

In current Oracle Database releases, for character data types, a zero-length string `''` is treated as `NULL`. This differs from some other database systems or programming languages where `""` and `null` are two distinct values.

Example:

```sql
SELECT CASE
           WHEN '' IS NULL THEN 'NULL'
           ELSE 'NOT NULL'
       END AS empty_value_check
FROM dual;
```

In current Oracle releases, the illustrated result is `NULL`.

With a column:

```sql
CREATE TABLE demo_required_text (
    label VARCHAR2(30 CHAR) NOT NULL
);
```

`INSERT ... VALUES ('')` cannot be used to insert a valid empty string past `NOT NULL`; Oracle sees the value as `NULL` under current behavior.

**Distinguish empty strings from space strings**:

```text
''        -> treated by Oracle as NULL (current behavior)
' '       -> one space character, not NULL
'   '     -> three space characters, not NULL
```

With `CHAR`, `' '` may be padded with additional spaces to reach the declared length, yet it still does not become `NULL`.

In Java, `String.isEmpty()` and `String.isBlank()` also differ. If business logic treats whitespace-only strings as "empty content", normalize and validate at the appropriate layer and define database constraints as needed. Do not rely solely on `NOT NULL` to reject all whitespace-only values.

Oracle notes the possibility of empty-string handling changing in the future; when designing, express `NULL` intent explicitly rather than building logic dependent on that equivalence.

## 12. Literals, Type Conversions, and Unicode in SQL

### 12.1. Regular Literals and National Literals

In Oracle SQL:

```sql
SELECT 'Hello'  AS database_charset_text,
       N'Hello' AS national_charset_text
FROM dual;
```

- `'Hello'` is a standard character literal.
- `N'Hello'` is a **national character literal**.

To preserve accented characters, `.sql` files and clients must handle encoding properly. If data was already misdecoded as `?` or mojibake before Oracle received the statement, using `N'...'` does not magically restore the original content.

### 12.2. `UNISTR` and Escaped Unicode Characters

Oracle provides `UNISTR` to represent Unicode characters using escape syntax, useful when avoiding direct entry of certain characters in scripts:

```sql
SELECT UNISTR('\0048\00E0\0020\004E\1ED9\0069') AS city_name
FROM dual;
```

The escape string illustrates **"Hà Nội"**. `UNISTR` returns a national character result; supplementary Unicode characters require appropriate escape forms under Oracle's mechanism.

Do not turn every user input into a `UNISTR` literal via string concatenation in code. For application data, **bind parameters** remain the right way to pass values.

### 12.3. `TO_CHAR`, `TO_NCHAR`, and Character Conversion

Oracle provides mechanisms to convert data between character forms. `TO_NCHAR` can convert a suitable expression to national character representation; `TO_CHAR` converts back to standard character representation in supported contexts.

Example:

```sql
SELECT TO_NCHAR('Sample') AS national_text
FROM dual;
```

Conversion does not guarantee every target character set can represent every source character. If the database character set does not support a character being converted, replacement characters or errors can occur depending on configuration. When working with multilingual data, the durable solution is usually selecting the right character set and driver from design time.

### 12.4. `LENGTH`, `LENGTHB`, `LENGTHC`, `LENGTH2`, `LENGTH4`

Functions to inspect length in multiple ways:

| Function | Meaning |
|---|---|
| `LENGTH(expr)` | Length in characters as Oracle evaluates the expression |
| `LENGTHB(expr)` | Length in bytes |
| `LENGTHC(expr)` | Length in Unicode complete characters per Oracle rules |
| `LENGTH2(expr)` | Length measured in UCS2 code units |
| `LENGTH4(expr)` | Length measured in UCS4 code units |

Example:

```sql
SELECT LENGTH('A')  AS chars,
       LENGTHB('A') AS bytes
FROM dual;
```

For ASCII characters and an `AL32UTF8` database, both columns typically yield `1`. For data containing supplementary Unicode characters, counts by bytes, code units, and code points can differ. Notably, **Oracle length does not automatically equal the number of visible characters on a UI** when a grapheme consists of multiple components.

### 12.5. Using `DUMP` to Inspect Representation

```sql
SELECT DUMP('ABC') AS dump_text
FROM dual;
```

`DUMP` can show the internal type and byte values, useful when investigating encoding differences or invisible whitespace. Do not build business rules on internal type codes from `DUMP`; use supported functions and metadata to validate data.

## 13. Lab: Comparing All Four Data Types Side by Side

These examples are intended for a **practice schema** with `CREATE TABLE` privilege, adequate quota, and a running Oracle Database. DDL/DML statements modify schema data, so **do not run them on production business tables**.

### Step 1. Check Character Sets

```sql
SELECT parameter, value
FROM nls_database_parameters
WHERE parameter IN ('NLS_CHARACTERSET', 'NLS_NCHAR_CHARACTERSET')
ORDER BY parameter;
```

Note the database and national character sets. If the database uses `AL32UTF8` and `AL16UTF16`, keep in mind that regular and national types can encode the same characters in different numbers of bytes.

### Step 2. Create a Test Table

```sql
CREATE TABLE demo_four_text_types (
    id             NUMBER PRIMARY KEY,
    code_fixed     CHAR(5 CHAR),
    code_varying   VARCHAR2(5 CHAR),
    code_nfixed    NCHAR(5),
    code_nvarying  NVARCHAR2(5),
    full_name      VARCHAR2(100 CHAR)
);
```

`DEMO_FOUR_TEXT_TYPES` is written unquoted, so Oracle normally stores its metadata in uppercase. The purpose of the table is to compare character storage behavior; the primary key here only distinguishes sample rows.

### Step 3. Insert the Same Short Value

```sql
INSERT INTO demo_four_text_types (
    id, code_fixed, code_varying,
    code_nfixed, code_nvarying, full_name
) VALUES (
    1, 'AB', 'AB',
    N'AB', N'AB', 'Lan'
);

COMMIT;
```

We use ASCII-only data here to avoid client encoding interference while observing padding.

### Step 4. Observe Character and Byte Lengths

```sql
SELECT id,
       LENGTH(code_fixed)    AS len_char,
       LENGTH(code_varying)  AS len_varchar2,
       LENGTH(code_nfixed)   AS len_nchar,
       LENGTH(code_nvarying) AS len_nvarchar2
FROM demo_four_text_types;
```

Expected character lengths:

```text
ID  LEN_CHAR  LEN_VARCHAR2  LEN_NCHAR  LEN_NVARCHAR2
--  --------  ------------  ---------  -------------
 1         5             2          5              2
```

Byte comparison:

```sql
SELECT LENGTHB(code_fixed)    AS bytes_char,
       LENGTHB(code_varying)  AS bytes_varchar2,
       LENGTHB(code_nfixed)   AS bytes_nchar,
       LENGTHB(code_nvarying) AS bytes_nvarchar2
FROM demo_four_text_types;
```

Byte counts for national types depend on `NLS_NCHAR_CHARACTERSET`; do not hardcode one fixed number for every database. With `AL16UTF16` and basic Latin characters, national characters typically consume more bytes than the corresponding ASCII characters in `AL32UTF8`.

### Step 5. Visualize Padding Spaces

```sql
SELECT '[' || code_fixed || ']'   AS fixed_display,
       '[' || code_varying || ']' AS varying_display,
       '[' || code_nfixed || ']'  AS nfixed_display,
       '[' || code_nvarying || ']' AS nvarying_display
FROM demo_four_text_types;
```

When displayed properly by the client, you will see `CHAR`/`NCHAR` containing trailing spaces after `AB`, whereas the two variable-length types do not pad to maximum length.

### Step 6. View Metadata for Each Column

```sql
SELECT column_name,
       data_type,
       data_length,
       char_length,
       char_used
FROM user_tab_columns
WHERE table_name = 'DEMO_FOUR_TEXT_TYPES'
ORDER BY column_id;
```

Observe the difference between `CHAR_LENGTH` and `DATA_LENGTH`. This is how to verify actual column definitions rather than inferring from how string values look.

### Step 7. Test Unicode Strings on a Supported Environment

If the database uses `AL32UTF8` and both the client and script file transmit Unicode correctly, try:

```sql
INSERT INTO demo_four_text_types (
    id, full_name, code_nvarying
) VALUES (
    2, 'Hà Nội', N'Hà'
);

COMMIT;

SELECT full_name,
       LENGTH(full_name) AS char_count,
       LENGTHB(full_name) AS byte_count,
       code_nvarying
FROM demo_four_text_types
WHERE id = 2;
```

If using a machine/terminal that does not handle Unicode properly, before blaming the column type, check script file encoding, display fonts, and client settings. National literals cannot repair text already corrupted at the source.

### Step 8. Clean Up the Test Object

Once certain this is the table you created in your practice schema and you no longer need the data:

```sql
DROP TABLE demo_four_text_types PURGE;
```

`DROP TABLE ... PURGE` is a destructive operation with an implicit commit and bypasses the recycle bin for eligible tables. Do not run it on shared objects or data needing recovery.

## 14. Java/JDBC: Choosing the Right Type and Passing Strings Safely

For Java applications, business interfaces usually use `String` for both `VARCHAR2` and `NVARCHAR2`. However, how values are **bound** and how the driver converts characters must match column types and driver capabilities.

### 14.1. `VARCHAR2` via `PreparedStatement`

Sample table:

```sql
CREATE TABLE app_people (
    person_id NUMBER PRIMARY KEY,
    full_name VARCHAR2(100 CHAR) NOT NULL
);
```

In Java:

```java
String sql = "INSERT INTO app_people (person_id, full_name) VALUES (?, ?)";

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setLong(1, 101L);
    ps.setString(2, "Nguyễn Lan");
    ps.executeUpdate();
}
```

`setString` passes the value via JDBC's bind mechanism without concatenating strings into SQL. Whether Vietnamese characters are stored properly depends on the database character set and driver/client transcoding.

### 14.2. `NVARCHAR2` and the `setNString`/`getNString` APIs

Example national column:

```sql
CREATE TABLE app_people_national (
    person_id NUMBER PRIMARY KEY,
    full_name NVARCHAR2(100) NOT NULL
);
```

With a JDBC driver supporting national character APIs:

```java
String sql = "INSERT INTO app_people_national (person_id, full_name)"
           + " VALUES (?, ?)";

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setLong(1, 102L);
    ps.setNString(2, "Nguyễn Lan");
    ps.executeUpdate();
}
```

Reading back:

```java
String sql = "SELECT full_name FROM app_people_national WHERE person_id = ?";

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setLong(1, 102L);
    try (ResultSet rs = ps.executeQuery()) {
        if (rs.next()) {
            String name = rs.getNString("full_name");
            System.out.println(name);
        }
    }
}
```

These snippets assume an existing `Connection`, JDBC imports, application-managed transactions/commits, and driver support for those calls. Some frameworks/ORMs have their own mechanisms for mapping nationalized types; check the actual mapping instead of changing an annotation and assuming the Oracle column converts as desired.

**Rule of thumb:** if the database uses `AL32UTF8`, storing Vietnamese data in `VARCHAR2` via `setString` is a normal design. `setNString` is for national character set columns/streams when needed, not a mandatory call for every `String` containing Unicode.

### 14.3. Practical Pitfalls with `CHAR`

An application reading `CHAR(5)` can receive a `String` containing trailing padding spaces. Therefore:

- Do not assume the returned length always equals the exact number of characters the user typed.
- Do not call `trim()` indiscriminately on names, notes, or data where whitespace must be preserved.
- If a code requires standardization, establish a consistent policy: choose `VARCHAR2`, validate length, and normalize per business rules where appropriate.

If an ORM generates schema from configuration, inspect the actual DDL and Oracle metadata to verify whether it uses `VARCHAR2` or `NVARCHAR2`, and `BYTE` or `CHAR` semantics. Never infer solely from Java's `String` type.

### 14.4. `PreparedStatement` Is Not Replaced by `N'...'` Literals

Here is an example of **what not to do**:

```java
// Wrong: directly concatenating user input into a SQL statement.
String sql = "SELECT * FROM app_people WHERE full_name = '" + userInput + "'";
```

The risks here are SQL injection and failures when input contains quotes; replacing `'` with `N'` does not make the query safe either. The right way is:

```java
String sql = "SELECT person_id FROM app_people WHERE full_name = ?";

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setString(1, userInput);
    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            // Process results.
        }
    }
}
```

## 15. Performance, Indexes, Comparisons, and Design Decisions

### 15.1. Is `CHAR` Always Faster Than `VARCHAR2`?

No. "Fixed-length" does not automatically mean faster SQL operations in all situations. `CHAR` can consume extra space due to padding; row length affects how many rows fit in a data block, I/O, and cache efficiency. `VARCHAR2` is usually better suited for variable-length strings.

Performance must be evaluated using workloads, data sizes, indexes, execution plans, and real environments. Do not switch all columns to `CHAR` simply assuming fixed memory is faster to access.

### 15.2. Does Choosing `NCHAR`/`NVARCHAR2` Affect Storage?

Possibly. National character sets like `AL16UTF16` encode many common characters in a different number of bytes than `AL32UTF8`. Index keys, byte limits, and conversions in SQL/JDBC can be affected. However, you cannot accurately claim `NVARCHAR2` always uses double the storage, because characters, data distributions, and encodings vary.

When selecting a type for an indexed key, examine **index key byte-length limits** and comparison behavior rather than merely reading `NVARCHAR2(100)`.

### 15.3. Encoding Differs from Collation

- **Encoding/character set**: how characters are represented as bytes.
- **Collation**: the rules by which strings are compared and sorted (case sensitivity, accents, language rules, etc.).

For example, being able to store the letter **"Đ"** does not mean Oracle automatically knows you want `"đ"` treated as equivalent to `"Đ"` during searches. Depending on version and configuration, `NLS_SORT`, `NLS_COMP`, or column/expression collations adjust comparison and sorting behavior.

For user data with Vietnamese accents, in addition to column type, define search requirements: accent-sensitive or not, case-sensitive or not, Unicode normalization needed or not. These requirements are independent of choosing `VARCHAR2` vs. `NVARCHAR2`.

### 15.4. Display Character Limits Differ from SQL Length

An emoji may be a single Unicode code point, yet many emoji and complex accented letters are built from multiple code points. Thus a UI rule limiting input to "50 visible user characters" can **differ** from `LENGTH(value) <= 50`.

For input fields with strict UI requirements, clearly define the character-counting unit and align rules across frontend, Java, and database. Even with `VARCHAR2(50 CHAR)`, Oracle's byte limit still applies.

## 16. Guide to Choosing Data Types for Real-World Scenarios

| Business Data | Commonly Considered Type | Why | Additional Controls Needed |
|---|---|---|---|
| Full names, addresses, product names | `VARCHAR2(n CHAR)` if database uses `AL32UTF8` | Variable length; Unicode in database character set | Byte limits, client encoding, input normalization |
| Email, username | `VARCHAR2(n CHAR)` or `VARCHAR2(n BYTE)` per clear engineering policy | Variable length | Case/collation, uniqueness, validation |
| Strictly two-character country code | `CHAR(2 CHAR)` or `VARCHAR2(2 CHAR)` with constraint | Can be a fixed code | `CHAR` padding; actual length and valid characters |
| Order statuses like `NEW`, `PAID` | `VARCHAR2(n CHAR)` | Codes have varying lengths | `CHECK` or reference table for allowed values |
| National strings in legacy schemas | `NCHAR(n)`/`NVARCHAR2(n)` per existing specification | Compatibility with designed structure and transcoding flow | JDBC/ORM mapping, byte limits, and conversions |
| Very long text | `CLOB` or `NCLOB` when truly warranted | Exceeds short-string needs/limits | LOB APIs, storage, indexing, migration |

### Practical Principles

1. **Prefer `VARCHAR2` for variable-length strings** in a database with an appropriate Unicode character set.
2. **Explicitly specify `BYTE` or `CHAR`** on `CHAR`/`VARCHAR2` when character count or byte count is a design constraint that must remain stable across environments.
3. **Use `CHAR` only when you understand padding effects**; fixed-length codes can also be stored in `VARCHAR2` with a length check.
4. **Choose `NCHAR`/`NVARCHAR2` when tied to national character set requirements**, not simply because you see Unicode or Vietnamese text.
5. **Check `NLS_CHARACTERSET`, `NLS_NCHAR_CHARACTERSET`, `MAX_STRING_SIZE`, and column metadata** before drawing conclusions about actual capacity.
6. **Separate character length from byte length and visible display characters**; complex Unicode may require dedicated counting logic in the application.
7. **Use bind parameters in Java** to maintain safety and type correctness instead of concatenating SQL or national literals.
8. **Define handling for spaces, empty strings, and `NULL`** across both the API and database layers.

## 17. Common Misconceptions

| Claim | Assessment | Explanation |
|---|---|---|
| "`CHAR(10)` always contains exactly ten meaningful characters." | False | Shorter values are padded with spaces to the fixed length |
| "`VARCHAR2(10)` pads up to ten characters." | False | It is a variable-length type |
| "`NCHAR` and `NVARCHAR2` are mandatory for storing Vietnamese." | False | `VARCHAR2` with an `AL32UTF8` database supports Unicode |
| "`VARCHAR2(10 CHAR)` can hold an unlimited number of bytes." | False | Type/column byte ceilings still apply |
| "`NVARCHAR2(100)` always uses exactly 100 bytes." | False | Maximum is in characters; actual bytes depend on data and the national character set |
| "`NLS_LENGTH_SEMANTICS` controls the unit for `NCHAR(n)`." | False | `NCHAR`/`NVARCHAR2` use character semantics |
| "`CHAR` and `VARCHAR2` always compare trailing spaces identically." | False | Oracle has blank-padded and nonpadded comparison semantics |
| "`''` in Oracle behaves like an independent empty string in Java." | False under current Oracle behavior | Oracle treats a zero-length string as `NULL` |
| "`LENGTH` always equals `LENGTHB`." | False | Unicode can use multiple bytes per character |
| "Using `N'...'` fixes characters already corrupted by encoding errors." | False | Literals cannot recover source data already transcoded incorrectly |
| "Changing `VARCHAR2` to `NVARCHAR2` is guaranteed to be faster." | False | Can introduce conversions and different storage sizes; must benchmark |
| "If a user enters one emoji, every Oracle length function returns `1`." | Not guaranteed | There are code points, code units, and grapheme clusters; counts differ |

## 18. Self-Check Questions

**Question 1.** When storing `'AB'` in `CHAR(5 CHAR)` and `VARCHAR2(5 CHAR)`, how does the length returned by `LENGTH` differ?

**Answer:** With `CHAR`, Oracle pads to five characters, so `LENGTH = 5` typically. With `VARCHAR2`, there is no padding, so `LENGTH = 2`.

**Question 2.** A database uses `AL32UTF8`. To store Vietnamese full names, is `NVARCHAR2` mandatory?

**Answer:** No. `VARCHAR2(n CHAR)` is usually suitable, provided data is sent properly as Unicode and the column size fits the actual bytes.

**Question 3.** What is the difference between `VARCHAR2(20 BYTE)` and `VARCHAR2(20 CHAR)`?

**Answer:** The first has a 20-byte limit; the second has a 20-character limit under Oracle semantics while still subject to the maximum byte limit.

**Question 4.** Is `NCHAR(10 BYTE)` valid syntax to limit national text to 10 bytes?

**Answer:** No. `NCHAR` declares length in characters via `NCHAR(n)`; it does not use `BYTE`/`CHAR` as `CHAR` does.

**Question 5.** Does setting `MAX_STRING_SIZE=EXTENDED` allow `CHAR` to hold 32,767 bytes?

**Answer:** No. Extended mode mainly raises the byte ceiling of `VARCHAR2`/`NVARCHAR2` and supported related types, while `CHAR`/`NCHAR` have their own limits.

**Question 6.** Why do `'A'` and `'A '` sometimes compare equal, whereas two corresponding `VARCHAR2` values may differ?

**Answer:** Oracle uses blank-padding rules for certain `CHAR`/literal operands; when a comparison applies nonpadded semantics for `VARCHAR2`/`NVARCHAR2`, trailing spaces are significant.

**Question 7.** Is storing `''` into a `VARCHAR2 NOT NULL` column valid?

**Answer:** Under current Oracle behavior, `''` is treated as `NULL`, so it violates `NOT NULL`.

**Question 8.** To check whether a column actually uses byte or character semantics, what should you inspect?

**Answer:** Check `USER_TAB_COLUMNS` or `ALL_TAB_COLUMNS` for `DATA_TYPE`, `DATA_LENGTH`, `CHAR_LENGTH`, and `CHAR_USED`, along with relevant NLS settings.

**Question 9.** How do JDBC `setString` and `setNString` differ in purpose?

**Answer:** `setString` is for binding standard strings, while `setNString` is for binding national character parameters when supported by the driver. Neither alters the database's character set configuration.

**Question 10.** Is `CHAR(2 CHAR)` enough to guarantee users truly submitted a two-character code?

**Answer:** Not by itself. Shorter values can be space-padded. If strict format is required, add validation/constraints and standardize whitespace handling.

## 19. Conclusion

`CHAR`, `VARCHAR2`, `NCHAR`, and `NVARCHAR2` are Oracle's four character data types distinguished by **fixed vs. variable length** and **database character set vs. national character set**. `CHAR` and `NCHAR` follow space-padding rules; `VARCHAR2` and `NVARCHAR2` store variable-length values. Standard columns use the database character set, while the two types starting with `N` use the national character set.

When designing Oracle schemas for Java applications, prioritize **the type matching the nature of the data**: variable-length strings generally fit `VARCHAR2` on an `AL32UTF8` database; national types require a specific data or compatibility justification. Verify `BYTE`/`CHAR` semantics, byte limits, Unicode handling, whitespace comparisons, `NULL` behavior, and JDBC binding to avoid bugs that surface only when data or environments change.
