# Character Sets, Encoding, and Session Parameters When Connecting from Tools

When working with Oracle Database from SQL*Plus, SQLcl, SQL Developer, DBeaver, or a Java application, a statement may execute successfully yet display `Tiếng Việt` as question marks or garbled characters; dates may appear in an unexpected format; or the string `1,25` may be interpreted differently from `1.25`. These symptoms involve **character sets and character conversion**, **session NLS settings**, and **how the tool renders or sends values**.

This lesson shows how to separate those layers, inspect configurations directly from an Oracle client tool, test Unicode data, and set session parameters deliberately. Data-modification examples should only be run in a practice schema where you hold permissions.

## 1. Four Layers to Distinguish When a Character Travels from Tool to Oracle

~~~mermaid
flowchart LR
    A["User types 'Tiếng Việt'"] --> B["Editor / terminal / SQL file"]
    B --> C["Client: SQL*Plus, SQLcl, JDBC..."]
    C -->|"Oracle Net and character conversion when needed"| D["Oracle server / session"]
    D --> E["VARCHAR2/CLOB: database character set"]
    D --> F["NCHAR/NVARCHAR2/NCLOB: national character set"]
    D --> G["Session NLS: language, numbers, dates, sorting..."]
~~~

| Layer | What Does It Govern? | Typical Examples |
|---|---|---|
| **File/terminal encoding** | How bytes typed by the user or read/displayed by a tool are decoded into characters | `.sql` file saved as UTF-8; terminal using UTF-8; font supporting Vietnamese diacritics |
| **Client/driver character set** | How the client transmits or converts characters before Oracle receives them and after Oracle returns them | `NLS_LANG` in OCI/SQL*Plus clients; Java Unicode `String` in JDBC Thin |
| **Database character set** | How Oracle encodes characters inside the corresponding column data type | `AL32UTF8` for `VARCHAR2`/`CLOB`; `AL16UTF16` for `NVARCHAR2` |
| **Session NLS settings** | Language, date/number formats, comparison/sorting rules, and certain SQL execution defaults | `NLS_DATE_FORMAT`, `NLS_NUMERIC_CHARACTERS`, `NLS_DATE_LANGUAGE`, `NLS_SORT` |

A **character set** is a repertoire of characters paired with rules for representing them as bytes. **Encoding** is the method of mapping characters to bytes under those rules. Oracle names character sets such as `AL32UTF8` (standard UTF-8 for Unicode) or `AL16UTF16` (big-endian UTF-16 for national character data). **NLS** stands for *National Language Support*; many NLS parameters control **how values are formatted and interpreted**, without altering the stored bytes of existing records.

A common scenario: the database already uses `AL32UTF8`, yet a terminal or client reads the file with the wrong encoding. In that case, the database itself may be completely intact while displayed text looks broken; conversely, text may already have been corrupted **before** Oracle received it, causing the database to store the corrupted string itself.

## 2. Oracle Character Sets: Database Character Set vs. National Character Set

Oracle typically has two character-set declarations to inspect:

- **`NLS_CHARACTERSET`:** the primary database character set, applied to character data in `CHAR`, `VARCHAR2`, `CLOB`, and most standard character structures.
- **`NLS_NCHAR_CHARACTERSET`:** the national character set, applied to `NCHAR`, `NVARCHAR2`, and `NCLOB`. Common values include `AL16UTF16`; other values may appear depending on version and configuration.

From a SQL session connected to the **target database/PDB**, run:

~~~sql
SELECT parameter, value
FROM nls_database_parameters
WHERE parameter IN ('NLS_CHARACTERSET', 'NLS_NCHAR_CHARACTERSET')
ORDER BY parameter;
~~~

**Example** output (not representative of every Oracle instance):

~~~text
PARAMETER               VALUE
----------------------  --------
NLS_CHARACTERSET        AL32UTF8
NLS_NCHAR_CHARACTERSET  AL16UTF16
~~~

With Oracle multitenant, always verify the **exact container you are connected to**. Depending on version and configuration, the root and a PDB can have different character-set conditions or constraints; never treat a query in the root as automatically representing an application PDB. Check the current container with:

~~~sql
SELECT SYS_CONTEXT('USERENV', 'CON_NAME') AS current_container
FROM dual;
~~~

### 2.1 Choosing `VARCHAR2` vs. `NVARCHAR2`

Example table creation in a practice schema:

~~~sql
CREATE TABLE nls_text_lab (
    id              NUMBER PRIMARY KEY,
    label_varchar   VARCHAR2(40 CHAR),
    label_nvarchar  NVARCHAR2(40)
);
~~~

`LABEL_VARCHAR` uses the database character set; `LABEL_NVARCHAR` uses the national character set. On an `AL32UTF8` database, `VARCHAR2` already supports Unicode, including Vietnamese characters, so **there is no default need to switch every Vietnamese column to `NVARCHAR2`**. Column type choice also depends on data architecture, compatibility, and conversion overhead during queries.

If a database's primary character set cannot represent a given character, conversion from the client can fail or lose data depending on the path and configuration. That is why checking `NLS_CHARACTERSET` is foundational when troubleshooting Unicode issues; changing display formatting alone will not add Unicode storage capability to a legacy character set.

### 2.2 `BYTE` vs. `CHAR` in Length Declarations

With a multibyte character set such as `AL32UTF8`, a string's **character count** and **byte count** can differ:

~~~sql
CREATE TABLE nls_length_lab (
    code_byte VARCHAR2(10 BYTE),
    code_char VARCHAR2(10 CHAR)
);
~~~

- `VARCHAR2(10 BYTE)` sets a limit of **10 bytes** in the database character set. A string of 10 Unicode characters may not fit.
- `VARCHAR2(10 CHAR)` sets a limit of **10 characters** (still subject to maximum byte limits of the data type and database settings).
- `NLS_LENGTH_SEMANTICS` controls the default interpretation when declaring `VARCHAR2(10)` without explicit `BYTE` or `CHAR`. It **does not alter definitions of already-existing columns**.

Inspect the session value:

~~~sql
SELECT parameter, value
FROM nls_session_parameters
WHERE parameter = 'NLS_LENGTH_SEMANTICS';
~~~

In a practice schema, if you want clarity, write `BYTE` or `CHAR` explicitly in DDL instead of relying on environment defaults. Never attempt to alter a database's character set via administrative commands just to fix a Vietnamese text-entry bug: that is a high-impact architectural change requiring a dedicated data-migration process.

## 3. Which NLS Parameters Affect a SQL Session?

Each application or tool connection establishes a **session**. Session NLS parameters can come from database defaults, client login settings, the tool itself, and `ALTER SESSION` statements. Two sessions on the same database **can display the exact same stored value differently**.

### 3.1 Inspecting Active Parameters in the Current Session

~~~sql
SELECT parameter, value
FROM nls_session_parameters
WHERE parameter IN (
    'NLS_LANGUAGE',
    'NLS_TERRITORY',
    'NLS_DATE_LANGUAGE',
    'NLS_DATE_FORMAT',
    'NLS_TIMESTAMP_FORMAT',
    'NLS_TIMESTAMP_TZ_FORMAT',
    'NLS_NUMERIC_CHARACTERS',
    'NLS_SORT',
    'NLS_COMP',
    'NLS_LENGTH_SEMANTICS'
)
ORDER BY parameter;
~~~

Key parameters:

| Parameter | Common Meaning |
|---|---|
| `NLS_LANGUAGE` | Default language for messages and language-specific conventions |
| `NLS_TERRITORY` | Territory conventions affecting several session defaults upon connect |
| `NLS_DATE_LANGUAGE` | Language for month/day names and how those names are parsed in date formats |
| `NLS_DATE_FORMAT` | Default display/parsing format for `DATE` during implicit string conversions |
| `NLS_TIMESTAMP_FORMAT` | Default format for `TIMESTAMP` without time zone |
| `NLS_TIMESTAMP_TZ_FORMAT` | Default format for `TIMESTAMP WITH TIME ZONE` |
| `NLS_NUMERIC_CHARACTERS` | Two characters: decimal separator first, thousands group separator second |
| `NLS_SORT` | Linguistic sorting rule when Oracle uses corresponding NLS sort/comparison |
| `NLS_COMP` | Controls linguistic comparison behavior for eligible SQL comparisons |
| `NLS_LENGTH_SEMANTICS` | Default `BYTE`/`CHAR` semantics for new character column declarations |

To compare against database-level stored parameters:

~~~sql
SELECT parameter, value
FROM nls_database_parameters
WHERE parameter IN (
    'NLS_LANGUAGE',
    'NLS_TERRITORY',
    'NLS_DATE_FORMAT',
    'NLS_NUMERIC_CHARACTERS'
)
ORDER BY parameter;
~~~

**Note:** `NLS_DATABASE_PARAMETERS` and `NLS_SESSION_PARAMETERS` are not the same data source. Values from database creation are not necessarily what the current session uses, and several session parameters are initialized or overridden at connect time. When reporting a bug seen in a specific tool, prioritize **that session's values**.

### 3.2 Changing Parameters Only for the Current Session

The following statements are suitable for practicing in an isolated connection:

~~~sql
ALTER SESSION SET NLS_DATE_FORMAT = 'YYYY-MM-DD HH24:MI:SS';
ALTER SESSION SET NLS_DATE_LANGUAGE = 'AMERICAN';
ALTER SESSION SET NLS_NUMERIC_CHARACTERS = '.,';

SELECT parameter, value
FROM nls_session_parameters
WHERE parameter IN (
    'NLS_DATE_FORMAT',
    'NLS_DATE_LANGUAGE',
    'NLS_NUMERIC_CHARACTERS'
)
ORDER BY parameter;
~~~

`ALTER SESSION` changes the behavior **of the current connection only**; it neither re-encodes stored values nor modifies system-wide settings. Once you disconnect and open a new session, values revert to defaults or whatever the tool/application configures.

If a tool or application uses a **connection pool**, physical connections are reused. A session setting changed by an earlier request can leak into a later request if the pool does not reset session state. In applications, initialize connections consistently at checkout/startup, use proper bind types, and avoid depending on uncontrolled session defaults.

## 4. Where Does `NLS_LANG` Fit in the Connection Path?

`NLS_LANG` is a **client-side environment variable** used by Oracle tools and libraries built on **Oracle Call Interface (OCI)**, including many SQL*Plus setups. It typically takes the form:

~~~text
LANGUAGE_TERRITORY.CHARACTER_SET
AMERICAN_AMERICA.AL32UTF8
~~~

Its three parts play different roles:

1. `LANGUAGE`: default language requested by the client, e.g., `AMERICAN`.
2. `TERRITORY`: territory conventions, e.g., `AMERICA`.
3. `CHARACTER_SET`: declares the character set the client uses when communicating over an applicable OCI path.

Important to remember: **`NLS_LANG` is not a command to change Oracle Database's character set.** Its final segment must accurately reflect how **the client actually represents characters**, rather than blindly copying the server's `NLS_CHARACTERSET`. Setting it incorrectly can cause Oracle to misconvert characters or corrupt text on input/output.

### 4.1 Example with a Unicode Shell on Linux/macOS

In a shell whose locale and terminal genuinely run in UTF-8, before starting SQL*Plus:

~~~sh
locale
export NLS_LANG=AMERICAN_AMERICA.AL32UTF8
sqlplus -L app_user@//db-host.example:1521/my_pdb_service
~~~

`db-host.example` and `my_pdb_service` are placeholders to replace; SQL*Plus will prompt for the password. A UTF-8 terminal, a UTF-8 SQL script file, and matching tool encoding must all align. If a file was already saved or read with the wrong encoding earlier, `export NLS_LANG` alone cannot recover lost characters.

Check the client variable in the shell:

~~~sh
printf '%s\n' "$NLS_LANG"
~~~

### 4.2 Example with Windows PowerShell

In PowerShell, set the environment variable **for the current shell process and its child processes** before running SQL*Plus:

~~~powershell
$env:NLS_LANG = 'AMERICAN_AMERICA.AL32UTF8'
sqlplus -L app_user@//db-host.example:1521/my_pdb_service
~~~

To inspect it:

~~~powershell
$env:NLS_LANG
~~~

On Windows, **console code page, actual application encoding, file encoding, and font** are separate factors. `chcp 65001` changes the console code page, yet does not guarantee every SQL*Plus version or every Unicode I/O path works cleanly. Test your actual environment rather than treating a single variable or code page as sole proof.

### 4.3 SQLcl, SQL Developer, DBeaver, and JDBC Thin

Never apply the `NLS_LANG` recipe blindly across every tool:

| Tool / Connection Path | How to Think About Characters |
|---|---|
| **SQL*Plus over OCI** | `NLS_LANG` and OS input/output encoding can affect character conversion |
| **SQLcl** | Java-based tool; check how Java/the tool reads files and encodes terminal I/O along with session NLS, rather than assuming OCI SQL*Plus byte rules |
| **SQL Developer** | Java/JDBC tool; watch editor/import/export encoding, UI settings, and connection NLS |
| **DBeaver via JDBC Thin** | Java `String`/driver handles Unicode characters; check driver, import/export encoding, and connection/session config |
| **Java JDBC Thin apps** | Java string parameters travel through the driver and convert to column types as supported by the server; OCI `NLS_LANG` is not the primary control for Java `String` transcoding |

With **JDBC Thin**, character conversion is handled by the driver and Oracle protocol from Java Unicode values; setting `NLS_LANG=...AL32UTF8` in the shell is not the root fix for a Java app using JDBC Thin. With **JDBC OCI** or OCI-based tools, client NLS rules differ. Always identify **the driver/connection type** before choosing which parameter to adjust.

Never conclude from:

~~~sql
SELECT SYS_CONTEXT('USERENV', 'LANGUAGE') AS current_language
FROM dual;
~~~

that your terminal or SQL file definitely uses that encoding. This string reflects the language/character-set context reported by Oracle (its character-set suffix relates to the **database character set**), **not a measurement of your terminal window's byte encoding**.

## 5. A Test That Distinguishes Input, Storage, and Display Errors

A reliable technique combines **visible text**, **character/byte length**, and **hexadecimal byte representation**. Merely seeing accented letters on screen is not enough to prove the underlying bytes were handled properly.

### 5.1 Testing in SQL Without Relying on Directly Typed Accents

Oracle's `UNISTR` function constructs Unicode strings from ASCII escape sequences. Example:

~~~sql
SELECT UNISTR('Ti\1EBFng Vi\1EC7t - H\00E0 N\1ED9i') AS vietnamese_text
FROM dual;
~~~

The expected result is **`Tiếng Việt - Hà Nội`**. Because the input uses only ASCII characters and `\hhhh` escapes, it separates **reading/typing an accented SQL file** from **returning results to the tool**. If the displayed output looks wrong, do not immediately conclude the database stored corrupt data: at this point we only evaluated an expression.

`UNISTR` returns a Unicode string in the national character data family. When inserted into a `VARCHAR2` column, Oracle converts it to the **database character set**; on `AL32UTF8`, the Vietnamese string in this example is represented faithfully. On other character sets, check what characters that character set can represent.

### 5.2 Testing Persistence in an Authorized Schema

If you have table-creation privileges in a **practice** schema, use the `NLS_TEXT_LAB` table from earlier and run:

~~~sql
INSERT INTO nls_text_lab (id, label_varchar, label_nvarchar)
VALUES (
    1,
    UNISTR('Ti\1EBFng Vi\1EC7t - H\00E0 N\1ED9i'),
    UNISTR('Ti\1EBFng Vi\1EC7t - H\00E0 N\1ED9i')
);

COMMIT;

SELECT id, label_varchar, label_nvarchar
FROM nls_text_lab
WHERE id = 1;
~~~

`INSERT` writes data, so run it only in a sample schema. To avoid confusion on re-runs, insert `ID = 1` only once; running it again with the same primary key raises a duplicate-key error. In read-only environments where table creation is not allowed, skip the write portion and use `UNISTR` expressions to inspect how the tool renders characters.

### 5.3 Inspecting Length and Stored Bytes of a String

~~~sql
SELECT id,
       label_varchar,
       LENGTH(label_varchar) AS characters_count,
       LENGTHB(label_varchar) AS bytes_count,
       DUMP(label_varchar, 1016) AS database_bytes_hex
FROM nls_text_lab
WHERE id = 1;
~~~

Meaning:

- `LENGTH` measures length in characters of the expression.
- `LENGTHB` measures length in bytes in Oracle's representation of that value; in a `VARCHAR2` column on `AL32UTF8`, many accented characters occupy more than one byte.
- `DUMP(value, 1016)` prints data type, length, and bytes in hexadecimal. Use it to verify the exact bytes stored in Oracle instead of trusting only what a tool draws on screen.

Short standalone comparison example:

~~~sql
SELECT LENGTH('A') AS ascii_chars,
       LENGTHB('A') AS ascii_bytes,
       LENGTH(UNISTR('\1ED9')) AS unicode_chars,
       DUMP(CAST(UNISTR('\1ED9') AS VARCHAR2(10 CHAR)), 1016)
           AS unicode_in_database_charset
FROM dual;
~~~

In `AL32UTF8`, the character `ộ` (U+1ED9) is encoded in **three UTF-8 bytes**. Do not assume every Unicode character takes two or three bytes; UTF-8 is variable-length, and supplementary characters outside the BMP take four bytes.

To compare a **directly typed string** against its `UNISTR` counterpart:

~~~sql
SELECT CASE
         WHEN 'Tiếng Việt' = UNISTR('Ti\1EBFng Vi\1EC7t')
         THEN 'MATCH'
         ELSE 'DIFFERENT'
       END AS typed_input_check
FROM dual;
~~~

If your script file or terminal transmits `'Tiếng Việt'` accurately, the result is `MATCH`. If it returns `DIFFERENT`, there may be an input encoding mismatch, or the two strings look identical yet use different Unicode code-point sequences.

**Unicode normalization:** the same accented letter can sometimes be represented as a precomposed character (composed) or a base letter plus combining diacritic (decomposed). They may render identically while differing in bytes and binary equality. Unicode normalization must be handled intentionally at data ingestion/processing; never assume Oracle automatically normalizes every string to the same form.

## 6. Checking How NLS Affects Numbers and Dates

Many problems loosely called "encoding bugs" are actually **data-type conversion errors caused by session NLS**.

### 6.1 Decimal Points and Group Separators

~~~sql
ALTER SESSION SET NLS_NUMERIC_CHARACTERS = '.,';

SELECT TO_CHAR(1234.5, 'FM9G999D0') AS formatted_number
FROM dual;
~~~

With `'.,'`, the decimal separator is **period** and the group separator is **comma**, so the format model produces `1,234.5`. Switch within the practice session:

~~~sql
ALTER SESSION SET NLS_NUMERIC_CHARACTERS = ',.';

SELECT TO_CHAR(1234.5, 'FM9G999D0') AS formatted_number
FROM dual;
~~~

Now the output becomes `1.234,5`. Format elements `D` and `G` follow `NLS_NUMERIC_CHARACTERS`. **The underlying `NUMBER` value is identical**; only the formatted string changes.

Avoid building SQL by concatenating formatted number strings from UI input:

~~~sql
-- Do not rely on Oracle implicitly parsing strings by session:
SELECT '12,50' AS text_input FROM dual;

-- Numbers in SQL are numeric literals (not user-entered text):
SELECT 12.50 AS numeric_value FROM dual;
~~~

`'12,50'` is a string; converting it to `NUMBER` without specifying rules can produce wrong numbers or `ORA-01722`. In Java, use `PreparedStatement.setBigDecimal(...)` or bind numerically with the matching type instead of splicing `"12,50"` into SQL.

### 6.2 Date Formats and Month Name Languages

~~~sql
ALTER SESSION SET NLS_DATE_FORMAT = 'DD/MM/YYYY HH24:MI:SS';

SELECT SYSDATE AS shown_date
FROM dual;
~~~

`SYSDATE` returns an Oracle `DATE` value; the tool implicitly formats it as a string using `NLS_DATE_FORMAT` when printing. An Oracle `DATE` always includes **both date and hours/minutes/seconds**, even if a format hides the time portion. If you switch to:

~~~sql
ALTER SESSION SET NLS_DATE_FORMAT = 'YYYY-MM-DD';

SELECT SYSDATE AS shown_date
FROM dual;
~~~

the time portion disappears from the display without being stripped from the underlying value.

For consistent output across sessions, use explicit formatting:

~~~sql
SELECT TO_CHAR(
           DATE '2026-11-14',
           'YYYY-MM-DD'
       ) AS stable_date
FROM dual;
~~~

`DATE '2026-11-14'` is an ANSI date literal independent of `NLS_DATE_FORMAT`. For user-supplied strings, use typed date/time binds or `TO_DATE(text, format_model)` / `TO_TIMESTAMP(text, format_model)` with an explicit format model. Errors like `ORA-01843` (*not a valid month*) or `ORA-01861` (*literal does not match format string*) typically signal mismatched date/string conversion.

When using month names such as `MON` or `MONTH`, `NLS_DATE_LANGUAGE` also changes how Oracle parses and prints them. If you must parse month names from strings, pin the language explicitly instead of expecting every session to behave the same.

### 6.3 Time Zones Are Distinct from Character Encoding

~~~sql
SELECT SESSIONTIMEZONE,
       DBTIMEZONE,
       CURRENT_TIMESTAMP,
       SYSTIMESTAMP
FROM dual;
~~~

- `SESSIONTIMEZONE`: time zone of **the current session**.
- `DBTIMEZONE`: database-configured time zone; not necessarily the time zone of every session.
- `CURRENT_TIMESTAMP`: current instant with the session's time zone.
- `SYSTIMESTAMP`: current instant from the database server host, with its corresponding time zone/offset.

You can set the session time zone in a practice connection:

~~~sql
ALTER SESSION SET TIME_ZONE = '+07:00';

SELECT SESSIONTIMEZONE, CURRENT_TIMESTAMP
FROM dual;
~~~

This does not change any character set or automatically shift `DATE` values to the new time zone. `DATE` and `TIMESTAMP` store no time zone, whereas `TIMESTAMP WITH TIME ZONE` and `TIMESTAMP WITH LOCAL TIME ZONE` have distinct storage and display rules. When debugging hour offsets, inspect the column type, session time zone, and how the driver transmits values; do not diagnose it as a UTF-8 bug.

## 7. Sorting and String Comparison Are Not the Same as UTF-8 Storage

Suppose two strings differ by uppercase/lowercase or diacritics:

~~~sql
SELECT label_varchar
FROM nls_text_lab
ORDER BY label_varchar;
~~~

Sort order depends on the comparison/collation rules applied to the expression and database/session settings. **Unicode or `AL32UTF8` only defines character representation; it does not guarantee Vietnamese linguistic sorting order.**

In environments supporting NLS sorting parameters, inspect:

~~~sql
SELECT parameter, value
FROM nls_session_parameters
WHERE parameter IN ('NLS_SORT', 'NLS_COMP')
ORDER BY parameter;
~~~

`NLS_SORT` governs linguistic sorting; `NLS_COMP` governs linguistic comparison in eligible SQL expressions. Starting in Oracle 12.2, **data-bound collation** on columns and expressions can also participate in comparison semantics. Never assume changing a single parameter makes every `ORDER BY`, `WHERE`, and index behave identically across all releases.

Changing collation rules can affect search matches, case sensitivity, and index usage. Verify column definitions and business requirements before choosing comparison semantics, especially when strings serve as search keys or unique identifiers.

## 8. Connection Tools: What to Configure and What Not to Configure

### 8.1 Running SQL Scripts in SQL*Plus

One way to organize the exercise:

~~~sh
sqlplus -L app_user@//db-host.example:1521/my_pdb_service
~~~

Once connected, run the script:

~~~sql
-- At SQL*Plus's SQL> prompt:
@my_script.sql
~~~

Layers to check in order: **whether `my_script.sql` was saved in the right encoding**, which bytes the SQL*Plus client reads, whether `NLS_LANG`/OCI environment matches, which column type the server converts into, and whether the terminal can render Unicode. If a script run via `@` mangles accents while `UNISTR` displays cleanly, inspect **the script file's encoding or client file-reading path** first.

SQL*Plus `SPOOL` writes output to a file. The output file's encoding depends on the client/environment character output path and config; it **does not automatically become `AL32UTF8` merely because the database uses `AL32UTF8`**. When exchanging CSV or text files between tools, verify the actual encoding on both export and import sides.

### 8.2 SQL Developer and DBeaver

In graphical tools, keep these settings distinct:

- Encoding used when **opening/saving SQL scripts** in the editor.
- Encoding used when **importing/exporting CSV or text files**; UTF-8 is usually right for Vietnamese if both ends agree.
- Driver type (JDBC Thin vs. other mechanisms) and driver version.
- Connection/session initialization statements (if supported by the tool), e.g., `ALTER SESSION SET NLS_DATE_FORMAT = ...`.
- Result-grid font and rendering. Boxes or missing glyphs may be a font issue rather than bad data in Oracle.

To separate UI rendering issues from stored data, run **the exact same `DUMP` query** in both tools. If Oracle's bytes match while the rendered glyphs differ, the cause points to client/rendering. If stored bytes are already wrong, trace input encoding at the source and transmission through the driver.

### 8.3 Java JDBC Applications

Example connection using service name:

~~~properties
spring.datasource.url=jdbc:oracle:thin:@//db-host.example:1521/my_pdb_service
spring.datasource.username=app_user
~~~

Hostnames and accounts in examples are placeholders. Passwords should come from your environment's secrets manager, never written into documentation or logs.

When writing character data, use bind variables:

~~~java
String sql = "INSERT INTO nls_text_lab (id, label_varchar) VALUES (?, ?)";
try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setLong(1, 2L);
    statement.setString(2, "Tiếng Việt");
    statement.executeUpdate();
}
~~~

This snippet sits inside a flow that already has an active `Connection connection`, JDBC imports, and transaction management. Java `String` represents Unicode; the driver transmits values per protocol and column type. `PreparedStatement` separates **values** from **SQL text**, avoiding string concatenation and reducing reliance on client literal parsing. If data was already corrupted in JSON or a file before `setString`, JDBC cannot guess how to repair it.

For numbers and dates, prefer typed binds (`setBigDecimal`, `setDate`, `setTimestamp`, or driver-supported time APIs) so you do not depend on NLS string formatting. Format output intentionally at the UI/API layer when presenting text to users.

## 9. Common Symptoms and How to Isolate Them

| Symptom | Likely Layer | First Check to Run |
|---|---|---|
| Vietnamese accents turn into `?` immediately on input | Conversion step cannot represent the character, or file/client already lost data | Compare direct input against `UNISTR`; query `DUMP` of the stored value |
| Text turns into garbled sequences like `Ã©` | A byte sequence was decoded under the wrong encoding at some step | Check file/terminal/client encoding; inspect raw bytes before and after each step |
| SQL*Plus mangles accents while SQL Developer displays them fine | The two clients use different decoding/display paths | Check SQL*Plus `NLS_LANG`, console/locale, and script encoding |
| `ORA-12899` when inserting accented strings | Byte length exceeded column limit | Check `VARCHAR2(... BYTE/CHAR)`, `LENGTHB`, and column definition |
| `ORA-12704` (*character set mismatch*) | Expression mixes incompatible character-set families in that context | Check column types, literals, and `CAST`/`CONVERT` usage |
| `ORA-12705` regarding NLS data files/environment | Invalid or inaccessible NLS config/data at client or server | Check `NLS_LANG`, Oracle Home, and tool runtime environment |
| `ORA-01722` on numeric strings | Number parsing failed due to separator/format mismatch or non-numeric text | Compare `NLS_NUMERIC_CHARACTERS` and bind/`TO_NUMBER` usage |
| `ORA-01843` or `ORA-01861` | Date string does not match format model or language | Check `NLS_DATE_FORMAT`/`NLS_DATE_LANGUAGE`; parse with explicit format |
| Same date displays differently on two machines | Session NLS or UI formatting | Query `NLS_SESSION_PARAMETERS`; use `TO_CHAR` with explicit format |
| Characters show as boxes even though bytes are valid | Font/rendering lacks glyphs | Switch to a Unicode-capable font; compare `DUMP` output |
| Case matching or Vietnamese sort order differs from expectations | Collation / NLS sort / comparison | Check `NLS_SORT`, `NLS_COMP`, and column/expression collation |

### 9.1 Distinguishing Three Failure Stages

~~~mermaid
flowchart TD
    A["Accented characters look wrong"] --> B["Use UNISTR to build same value from ASCII"]
    B --> C{"Does UNISTR display properly?"}
    C -->|Yes| D["Check source file/terminal encoding during input"]
    C -->|No| E["Check client character I/O and display font"]
    D --> F["Store in practice table and check DUMP/LENGTHB"]
    E --> F
    F --> G{"Do Oracle bytes match expected value?"}
    G -->|Yes| H["Isolate to client display/export layer"]
    G -->|No| I["Isolate to input conversion, column type, and character set"]
~~~

With important data, **never keep overwriting or bulk-fixing rows** based solely on a broken-looking screen. Pinpoint the exact stage where corruption occurs using queries and small test samples before deciding on a remediation.

## 10. Step-by-Step Guided Exercise

### Step 1 — Verify the Right Database and Container

Log in with an authorized tool, then run:

~~~sql
SELECT SYS_CONTEXT('USERENV', 'CON_NAME') AS con_name,
       USER AS session_user
FROM dual;

SELECT parameter, value
FROM nls_database_parameters
WHERE parameter IN ('NLS_CHARACTERSET', 'NLS_NCHAR_CHARACTERSET')
ORDER BY parameter;
~~~

Record the PDB/container name, schema, and both character sets. Do not mistake `NLS_NCHAR_CHARACTERSET` for a variable modifiable with `ALTER SESSION`.

### Step 2 — Record Session Parameters

~~~sql
SELECT parameter, value
FROM nls_session_parameters
WHERE parameter IN (
    'NLS_LANGUAGE',
    'NLS_TERRITORY',
    'NLS_DATE_FORMAT',
    'NLS_DATE_LANGUAGE',
    'NLS_NUMERIC_CHARACTERS',
    'NLS_SORT',
    'NLS_COMP',
    'NLS_LENGTH_SEMANTICS'
)
ORDER BY parameter;
~~~

### Step 3 — Compare Accented String vs. Unicode Escape String

~~~sql
SELECT 'Tiếng Việt' AS typed_text,
       UNISTR('Ti\1EBFng Vi\1EC7t') AS escaped_text,
       CASE
           WHEN 'Tiếng Việt' = UNISTR('Ti\1EBFng Vi\1EC7t')
           THEN 'MATCH'
           ELSE 'DIFFERENT'
       END AS comparison_result
FROM dual;
~~~

If `DIFFERENT`, check the SQL file or input encoding. If both match yet boxes appear in the results grid, check rendering/font support. If you need to verify stored values, run `DUMP(...,1016)` on the specific column.

### Step 4 — Test Changing Formats **Within the Session**

~~~sql
ALTER SESSION SET NLS_DATE_FORMAT = 'YYYY-MM-DD HH24:MI:SS';
ALTER SESSION SET NLS_NUMERIC_CHARACTERS = '.,';

SELECT SYSDATE AS display_date,
       TO_CHAR(1234.5, 'FM9G999D0') AS display_number
FROM dual;
~~~

Switch `NLS_NUMERIC_CHARACTERS` to `',.'` in the same session and re-run `TO_CHAR` to observe the difference. Open a second connection and check `NLS_SESSION_PARAMETERS` in the new session; never assume the two sessions stay synchronized.

### Step 5 — Compare Across Two Tools

Run the same `UNISTR`, `NLS_SESSION_PARAMETERS`, and (if you have the sample table) `DUMP` queries in both SQL*Plus and SQL Developer/SQLcl. Document: client type, connection method, file/script encoding, **each session's** NLS settings, and the bytes in Oracle. The goal is to isolate the exact variable rather than merely noting "machine A fails, machine B works."

## 11. Takeaways to Remember

1. **`NLS_CHARACTERSET` and `NLS_NCHAR_CHARACTERSET`** define the character sets storing data in Oracle. `ALTER SESSION` does not convert those character sets.
2. **`NLS_LANG`** belongs to applicable OCI/SQL*Plus client paths, holding language/territory and client character-set declaration. `NLS_LANG` does not measure every terminal and is not the main mechanism controlling Java `String` encoding in JDBC Thin.
3. **`NLS_SESSION_PARAMETERS`** reflects the NLS settings currently active in the running session; one database can serve many sessions with different settings simultaneously.
4. **Number formatting, date formatting, time zones, and collation** are distinct from string character encoding. A date printing in a different format does not mean UTF-8 bytes are broken.
5. **`UNISTR`, `LENGTH`, `LENGTHB`, and `DUMP`** help determine whether a bug begins at input, storage, or display. Test on small samples and the right PDB before altering configuration.

When facing "Oracle displays Vietnamese incorrectly," the logical sequence is **verify source encoding → identify client/driver → inspect database character set and column type → check session NLS → cross-check data via Unicode escapes and byte dumps → verify display/export handling**. Clarifying each layer lets you fix the true root cause without damaging data that was already stored cleanly.
