# UPPER, LOWER, INITCAP, and Character Set Effects in Oracle Database

When processing text data in **Oracle Database**, applications frequently need to normalize user names, product codes, and email addresses, or format names into a readable form. The three core SQL functions commonly used are **`UPPER`**, **`LOWER`**, and **`INITCAP`**:

- `UPPER(char)`: converts letters in a string to uppercase.
- `LOWER(char)`: converts letters in a string to lowercase.
- `INITCAP(char)`: capitalizes the first letter of each word and converts the remaining letters in the word to lowercase.

These functions look simple, yet their output can depend on the **character set**, **linguistic case-mapping rules**, **collation/NLS settings**, and how data is stored in `CHAR`, `VARCHAR2`, `NCHAR`, or `NVARCHAR2`. In particular, `UPPER` is not synonymous with case-insensitive comparison, and `INITCAP` is not a tool that understands proper nouns or natural-language capitalization rules across every language.

This lesson explains each function's behavior, distinguishes character-mapping case conversion from linguistic case conversion, shows how to inspect NLS and character set settings, demonstrates how to build queries and indexes for case-insensitive searches, and highlights key considerations for Java/JDBC integration.

## 1. Distinguishing case conversion from string comparison

Before studying each function, separate three operations:

1. **Case conversion:** transforming a string into uppercase, lowercase, or title-case form. This is the role of `UPPER`, `LOWER`, `INITCAP`, and their NLS counterparts.
2. **String comparison:** determining whether two values are equal, unequal, or how they sort relative to each other. This depends on collation, data types, and comparison settings.
3. **Data normalization:** applying stable business rules before storing or searching, such as trimming whitespace, standardizing identifiers, handling Unicode normalization, and deciding accent/case comparison rules.

Example:

```sql
SELECT UPPER('Oracle Database') AS upper_text,
       LOWER('Oracle Database') AS lower_text,
       INITCAP('ORACLE DATABASE') AS title_text
FROM dual;
```

Illustrative result:

| `UPPER_TEXT` | `LOWER_TEXT` | `TITLE_TEXT` |
|---|---|---|
| ORACLE DATABASE | oracle database | Oracle Database |

`UPPER` returns an uppercased text expression. It **does not modify the original data in the table** when merely called in `SELECT`. To store normalized values, you need an `UPDATE` or a dedicated normalized column, taking data impact and indexes into account.

```text
Original value in table
        |
        +---- SELECT UPPER(column) ----> Display / transformed value
        |
        +---- UPDATE column = UPPER(column) ----> Modifies stored data
        |
        +---- Function-based index on UPPER(column)
                                      ----> Supports search / uniqueness
```

An application may use `UPPER(username) = UPPER(:username)` for case-insensitive lookup within a defined rule set, but should never assume all languages follow simple English casing rules.

## 2. The UPPER function: converting text to uppercase

`UPPER(char)` returns a string with letters converted to uppercase according to Oracle's character case mapping for that function. Characters without uppercase equivalents, digits, spaces, and punctuation generally remain unchanged.

```sql
SELECT UPPER('oracle database 23ai') AS result
FROM dual;
```

Result:

```text
ORACLE DATABASE 23AI
```

### 2.1. Using UPPER in SELECT

```sql
SELECT customer_id,
       customer_name,
       UPPER(customer_name) AS customer_name_upper
FROM customers;
```

The query returns both the original name and its uppercase version. It is suitable for reports, data exports, or temporary search labels. Here, `UPPER` does not update the `CUSTOMER_NAME` column.

### 2.2. Using UPPER in a WHERE clause

Suppose table `LAB_CASE_NAMES` stores usernames in mixed case. To find `lan` regardless of how the user types uppercase or lowercase:

```sql
SELECT user_id, username
FROM lab_case_names
WHERE UPPER(username) = UPPER('Lan');
```

If the data contains `lan`, `LAN`, and `Lan`, the comparison evaluates after converting both sides to uppercase under the active `UPPER` mapping. This is a common pattern for case-insensitive searches when case rules allow it.

With bind parameters in an application:

```sql
SELECT user_id, username
FROM lab_case_names
WHERE UPPER(username) = UPPER(:p_username);
```

`:p_username` should be bound with the proper character type from the driver. Never concatenate user input directly into SQL.

### 2.3. UPPER does not strip diacritics

`UPPER` is a case conversion function, not an accent-removal function. For example, a string containing `á` converts to `Á`, preserving the acute accent. If business logic requires **accent-insensitive** search, evaluate an appropriate collation or a dedicated normalization expression; do not treat `UPPER` like a `TRANSLATE` that strips accents.

### 2.4. UPPER and NULL

If the argument is `NULL`, `UPPER` also returns `NULL`:

```sql
SELECT UPPER(NULL) AS result
FROM dual;
```

The result is `NULL`. Therefore:

```sql
WHERE UPPER(customer_name) = 'LAN'
```

does not select rows where `CUSTOMER_NAME IS NULL`; the comparison evaluates to `UNKNOWN`. If missing values must be handled, add an explicit `IS NULL` condition.

## 3. The LOWER function: converting text to lowercase

`LOWER(char)` converts letters in a string to lowercase. Digits, spaces, and punctuation that are not letters remain unchanged.

```sql
SELECT LOWER('ORACLE DATABASE 23AI') AS result
FROM dual;
```

Result:

```text
oracle database 23ai
```

### 3.1. Normalizing on read or write

You can use `LOWER` in a query:

```sql
SELECT email,
       LOWER(email) AS email_normalized
FROM customers;
```

Or in a data update:

```sql
-- Migration example only; evaluate data and impact before executing.
UPDATE lab_case_names
SET username = LOWER(username);
```

`UPDATE` modifies stored data. Before bulk normalization, check whether previously distinct values will collide after conversion. For example, `Lan` and `LAN` both become `lan`; if a unique constraint exists on the column, the update may be rejected or fail on colliding rows. Never run bulk normalization updates in production without duplicate detection, backup/rollback plans, and application testing.

### 3.2. LOWER does not strip diacritics either

For example, converting `ĐẶNG` to lowercase preserves the accented characters per the corresponding character mapping; the result is not `dang`. Accent-insensitive search requires a separate rule. Case conversion and accent removal are two independent transformations.

### 3.3. LOWER and NULL

`LOWER(NULL)` returns `NULL`. The predicate `LOWER(column) = 'abc'` will not match rows where `column IS NULL`. Do not blindly use `NVL(column, '')` to turn missing data into an empty string without defining business semantics, because Oracle treats empty strings in standard character types as `NULL` in many SQL contexts.

## 4. The INITCAP function: capitalizing each word

`INITCAP(char)` transforms a string using these rules:

- The first letter of each word is converted to uppercase.
- Remaining letters in the word are converted to lowercase.
- Word boundaries are generally determined by spaces or non-alphanumeric characters.

Example:

```sql
SELECT INITCAP('oracle database') AS result
FROM dual;
```

Result:

```text
Oracle Database
```

### 4.1. Examples with names and phrases

```sql
SELECT INITCAP('NGUYEN VAN AN') AS full_name,
       INITCAP('customer service center') AS department_name,
       INITCAP('oracle-sql tutorial') AS title_text
FROM dual;
```

Illustrative results based on word boundaries:

| Expression | Result |
|---|---|
| `INITCAP('NGUYEN VAN AN')` | `Nguyen Van An` |
| `INITCAP('customer service center')` | `Customer Service Center` |
| `INITCAP('oracle-sql tutorial')` | `Oracle-Sql Tutorial` |

With hyphens or punctuation, word-boundary detection can produce output that does not match your organization's editorial rules for proper names. Test against real data.

### 4.2. INITCAP does not understand acronyms or brand names

`INITCAP` applies a purely mechanical rule to each word; it does not know which words are proper nouns, abbreviations, or brands:

```sql
SELECT INITCAP('API AND SQL FOR ORACLE') AS result
FROM dual;
```

The output may be `Api And Sql For Oracle`, whereas technical documentation normally wants `API and SQL for Oracle`. Likewise, `iPhone`, `eBay`, personal names, place names, and custom acronyms should not be blindly formatted with `INITCAP` if exact casing must be preserved.

If business logic demands specific presentation rules, use an application formatting layer, a proper-noun dictionary, or explicitly defined rules rather than treating `INITCAP` as a natural-language capitalization engine.

### 4.3. INITCAP and NULL

`INITCAP(NULL)` returns `NULL`. Case-conversion functions do not automatically substitute another string for missing values. To display a fallback label, you can use `COALESCE`/`NVL` per business rules:

```sql
SELECT INITCAP(COALESCE(customer_name, 'unknown')) AS display_name
FROM customers;
```

Here, `UNKNOWN` is displayed as `Unknown`; this is a **presentation decision**, not a modification of stored data.

## 5. Quick comparison of UPPER, LOWER, and INITCAP

| Function | Intended Output | Sample Input | Sample Output | Typical Use Case |
|---|---|---|---|---|
| `UPPER` | Uppercase | `'Oracle Database'` | `ORACLE DATABASE` | Normalizing search keys or alphanumeric codes |
| `LOWER` | Lowercase | `'ORACLE Database'` | `oracle database` | Normalizing emails/usernames per policy |
| `INITCAP` | Capitalized word initials, rest lowercase | `'ORACLE DATABASE'` | `Oracle Database` | Formatting simple titles or names |

| Feature | `UPPER` | `LOWER` | `INITCAP` |
|---|---|---|---|
| Case transformation | All letters uppercase | All letters lowercase | First letter of each word uppercase, rest lowercase |
| Digits and punctuation | Generally preserved | Generally preserved | Preserved, though they can trigger word boundaries |
| Strips diacritics | No | No | No |
| Performs Unicode NFC/NFD normalization | No | No | No |
| Fixes proper nouns / acronyms | No | No | No |
| `NULL` argument | Returns `NULL` | Returns `NULL` | Returns `NULL` |

## 6. Impact of Oracle character sets

Oracle stores character data using a **character set**. For case operations, the character set and character encoding determine which characters can be stored and which default binary mappings apply.

Two concepts to distinguish:

- **Database character set**: the character set used for `CHAR`, `VARCHAR2`, `CLOB`, and most standard character data.
- **National character set**: the character set used for `NCHAR`, `NVARCHAR2`, and `NCLOB`.

In many modern Oracle deployments, the database character set is **`AL32UTF8`** for Unicode support, and the national character set is **`AL16UTF16`**. These are common configurations, not guaranteed defaults for all legacy databases.

### 6.1. Checking the database character set

```sql
SELECT parameter, value
FROM nls_database_parameters
WHERE parameter IN (
    'NLS_CHARACTERSET',
    'NLS_NCHAR_CHARACTERSET'
)
ORDER BY parameter;
```

Results may show:

| Parameter | Sample Value | Scope |
|---|---|---|
| `NLS_CHARACTERSET` | `AL32UTF8` | `CHAR`, `VARCHAR2`, `CLOB` columns |
| `NLS_NCHAR_CHARACTERSET` | `AL16UTF16` | `NCHAR`, `NVARCHAR2`, `NCLOB` columns |

If your account lacks privileges to query this view, ask a DBA for the configuration values; never grant broad administrative privileges just to read two parameters.

### 6.2. CHAR/VARCHAR2 vs. NCHAR/NVARCHAR2

```sql
CREATE TABLE lab_character_types (
    id             NUMBER PRIMARY KEY,
    normal_text    VARCHAR2(100 CHAR),
    national_text  NVARCHAR2(100)
);
```

- `NORMAL_TEXT` uses the database character set.
- `NATIONAL_TEXT` uses the national character set.
- `VARCHAR2(100 CHAR)` specifies length in **character semantics** instead of byte semantics.
- `NVARCHAR2(100)` enforces limits per the national character set semantics; do not equate 100 to a fixed byte count without checking configuration.

Calling `UPPER`, `LOWER`, or `INITCAP` on a character column does not convert `VARCHAR2` to `NVARCHAR2`, nor is it a character-set conversion designed to repair corrupted encoding. Case functions operate on the character values Oracle receives and return results according to the type and character-set rules of the argument.

### 6.3. BYTE semantics vs. CHAR semantics

A single Unicode character can occupy multiple bytes in `AL32UTF8`. Therefore:

- `VARCHAR2(30 BYTE)` limits storage by byte count.
- `VARCHAR2(30 CHAR)` limits storage by character count under Oracle semantics.
- A 30-character string does not necessarily fit in 30 bytes.

Checking lengths:

```sql
SELECT customer_name,
       LENGTH(customer_name)  AS char_length,
       LENGTHB(customer_name) AS byte_length
FROM customers;
```

`LENGTH` counts characters per data type semantics, whereas `LENGTHB` counts bytes. For Unicode data, the two values can differ. Case conversion can also affect character representation under certain mappings; therefore, never assume the output always has the exact same byte count as the input. When evaluating column limits or index key sizes, measure actual data with the appropriate length functions.

### 6.4. Character sets cannot repair already-corrupted encoding

If a client sends data using an incompatible encoding or a string was mangled before reaching the database, calling `UPPER` cannot recover the original text. For instance, if a Vietnamese name was turned into garbled characters due to misconfigured client settings, `UPPER` simply uppercases whatever garbled string Oracle received.

When investigating Vietnamese or Unicode text issues, inspect:

1. The database's `NLS_CHARACTERSET` and `NLS_NCHAR_CHARACTERSET`.
2. The encoding of the ingestion source (CSV files, APIs, message queues, ETL jobs).
3. Whether the driver/client sends Unicode strings properly.
4. Whether data underwent double-conversion or character loss before insertion.
5. Whether the SQL client display uses a compatible font and encoding.

Never change the database character set just to fix one column with corrupted encoding. Changing a database character set is a major administrative operation requiring full assessment of all data, applications, and migration steps.

## 7. UPPER/LOWER and linguistic rules: NLS_UPPER, NLS_LOWER

`UPPER` and `LOWER` use Oracle's standard character-set case mapping. By contrast, **`NLS_UPPER`** and **`NLS_LOWER`** support linguistic case conversion and allow specifying an NLS parameter.

General syntax:

```sql
NLS_UPPER(char [, 'nlsparam'])
NLS_LOWER(char [, 'nlsparam'])
```

Here, `nlsparam` can specify the appropriate sort/linguistic rule, for example:

```text
NLS_SORT = XTurkish
```

If `nlsparam` is omitted, the function uses the session's default NLS sort setting per Oracle rules. For consistent results across sessions and applications, consider passing the parameter explicitly whenever business logic requires a specific linguistic rule.

### 7.1. NLS_UPPER and NLS_LOWER examples

```sql
SELECT UPPER('istanbul') AS binary_upper,
       NLS_UPPER('istanbul', 'NLS_SORT = XTurkish') AS turkish_upper
FROM dual;
```

Under Turkish rules, lowercase `i` maps to dotted uppercase `İ`, while dotless `ı` maps to `I`. Consequently, linguistic mapping can produce results different from standard binary uppercase mapping. Valid sort names and exact output should be verified on your target Oracle version and configuration.

Lowercase example:

```sql
SELECT NLS_LOWER('ISTANBUL', 'NLS_SORT = XTurkish') AS turkish_lower
FROM dual;
```

This illustrates why case conversion that works for English may fall short for other languages. With multilingual data, choose rules based on business requirements and test edge cases.

### 7.2. INITCAP and NLS_INITCAP

Oracle also provides **`NLS_INITCAP`** to capitalize word initials using a specified linguistic rule:

```sql
NLS_INITCAP(char [, 'nlsparam'])
```

Example:

```sql
SELECT INITCAP('istanbul') AS default_title,
       NLS_INITCAP('istanbul', 'NLS_SORT = XTurkish') AS turkish_title
FROM dual;
```

Do not use `INITCAP` or `NLS_INITCAP` as a complete personal-name formatter. Proper names can include internal capitals, prefixes, suffixes, abbreviations, or culture-specific conventions.

### 7.3. Which function should you choose?

| Requirement | Good Starting Function | Notes |
|---|---|---|
| Normalize simple ASCII codes to uppercase | `UPPER` | Does not strip diacritics |
| Normalize strings to lowercase | `LOWER` | Verify rules for special languages |
| Display simple titles | `INITCAP` | Does not recognize acronyms or proper nouns |
| Convert case using linguistic rules | `NLS_UPPER`, `NLS_LOWER` | Pick an appropriate, consistent `nlsparam` |
| Capitalize word initials linguistically | `NLS_INITCAP` | Still does not replace editorial name rules |
| Case-insensitive comparison | Matching collation or normalizing both sides | Case conversion and comparison are separate operations |
| Accent-insensitive comparison | Accent-insensitive collation or separate normalized key | Do not rely solely on `UPPER`/`LOWER` |

## 8. How NLS settings affect results

Oracle uses various NLS parameters to govern language, territory, sort order, and character comparison. Common parameters include:

| Parameter | General Meaning |
|---|---|
| `NLS_LANGUAGE` | Language for messages and certain default linguistic rules |
| `NLS_TERRITORY` | Territory conventions, such as date/number formats and regional defaults |
| `NLS_SORT` | Linguistic sorting/comparison rules in applicable contexts |
| `NLS_COMP` | Controls whether Oracle applies linguistic or binary comparisons for certain SQL operations |
| `NLS_CHARACTERSET` | Database character set for standard character types |
| `NLS_NCHAR_CHARACTERSET` | National character set for `NCHAR`/`NVARCHAR2`/`NCLOB` |

### 8.1. Viewing database NLS settings

```sql
SELECT parameter, value
FROM nls_database_parameters
WHERE parameter IN (
    'NLS_CHARACTERSET',
    'NLS_NCHAR_CHARACTERSET',
    'NLS_LANGUAGE',
    'NLS_TERRITORY'
)
ORDER BY parameter;
```

Character set parameters reflect database-level configuration; `NLS_LANGUAGE` and `NLS_TERRITORY` here reflect database defaults.

### 8.2. Viewing session NLS settings

```sql
SELECT parameter, value
FROM nls_session_parameters
WHERE parameter IN (
    'NLS_LANGUAGE',
    'NLS_TERRITORY',
    'NLS_SORT',
    'NLS_COMP'
)
ORDER BY parameter;
```

A session can have settings different from database defaults due to client configuration, application settings, or `ALTER SESSION`. Therefore, two users running the same SQL in different sessions may receive different sorting or comparison results if the query relies on session NLS settings.

### 8.3. ALTER SESSION affects only the current session

Example modifying session settings to demonstrate linguistic comparison:

```sql
-- Test example in an isolated session.
ALTER SESSION SET NLS_COMP = LINGUISTIC;
ALTER SESSION SET NLS_SORT = BINARY_CI;

SELECT customer_name
FROM customers
WHERE customer_name = 'lan';
```

`BINARY_CI` is a case-insensitive binary sort. Settings such as `BINARY_AI` can be used for accent- and case-insensitive comparisons in supported contexts. When `NLS_COMP = LINGUISTIC`, Oracle applies the `NLS_SORT` rule to relevant SQL comparisons per the version documentation.

**Warning:** `ALTER SESSION` mutates session state. In applications using connection pools, a session can be reused for subsequent requests; if settings are not reset, unrelated requests may inherit unexpected comparison behavior. Never alter NLS settings globally or per request just to make one search screen work without evaluating impacts on sorting, indexes, execution plans, and business logic.

### 8.4. NLS functions and explicit parameters

If you only need linguistic case conversion, you can call `NLS_UPPER`/`NLS_LOWER` with an explicit `nlsparam` without mutating the entire session. This keeps the expression self-contained and reduces dependence on shifting session parameters.

However, when an expression is stored in a **function-based index**, rule consistency is critical. Do not build an index on an implicit NLS rule that varies by session and expect every client to generate matching keys. Use expressions with fixed rules, verify against your Oracle version, and manage index rebuilds if policies change.

## 9. Character sets, Unicode, and special letter cases

In basic English, mapping `a` to `A` is intuitive. With Unicode and other languages, a character can have more complex casing rules.

### 9.1. The letter i in Turkish

Turkish distinguishes:

| Lowercase | Corresponding Uppercase |
|---|---|
| `i` | `İ` (dotted I) |
| `ı` | `I` (dotless I) |

Thus, a multilingual application must not assume every case can be normalized with English-style `UPPER`. `NLS_UPPER` with the proper rule can express linguistic mapping, provided you verify available NLS sort names and test on an actual database.

### 9.2. Vietnamese diacritics

Sample data:

```sql
SELECT UPPER('đặng thị lan') AS upper_name,
       LOWER('ĐẶNG THỊ LAN') AS lower_name,
       INITCAP('ĐẶNG THỊ LAN') AS initcap_name
FROM dual;
```

On a database that fully supports Vietnamese characters, case functions apply mappings to the characters Oracle receives. The expected visual result is uppercase, lowercase, or capitalized word initials **without stripping accents**. Test on your target character set, collation, and Oracle version; do not extrapolate from an ASCII example that every Unicode character behaves identically.

### 9.3. Characters with multiple Unicode representations

Visually identical characters can be encoded as a single precomposed code point or as a base letter plus combining marks. Case conversion **is not Unicode NFC/NFD normalization**. Consequently, two strings that look identical on screen can still have different internal representations and fail to compare equal under binary comparison.

When data arrives from multiple systems, establish a Unicode normalization policy in the application layer or a designated mechanism, and apply it consistently across inserts, updates, searches, and uniqueness checks. Do not rely on `UPPER` as a silver bullet for all Unicode issues.

### 9.4. Length is not always just bytes

To inspect character data, you can query:

```sql
SELECT text_value,
       LENGTH(text_value)  AS length_chars,
       LENGTHB(text_value) AS length_bytes,
       LENGTHC(text_value) AS length_complete_chars
FROM lab_unicode_text;
```

`LENGTHC` counts Unicode complete characters per Oracle's definition; `LENGTHB` counts bytes. `LENGTH2` and `LENGTH4` count UCS2/UCS4 code points. These functions have data-type and version constraints documented in Oracle manuals. Table `LAB_UNICODE_TEXT` is a conceptual example, not one of the lab tables created earlier.

When a column approaches a `VARCHAR2(n BYTE)` limit or when building an index on a transformed expression, check the byte length of the converted result, not just the visible character count.

## 10. Case-insensitive comparison: multiple approaches

Case-insensitive search is a common requirement, with several implementation paths. Pick the one matching your Oracle version, linguistic rules, indexing strategy, and uniqueness needs.

### 10.1. Converting both sides with UPPER

```sql
SELECT user_id, username
FROM app_users
WHERE UPPER(username) = UPPER(:p_username);
```

Advantages:

- Easy to understand and works across Oracle versions.
- Does not require altering the original values in the table.
- Can be paired with a function-based index on the same expression.

Limitations:

- Case mapping follows `UPPER` rules, which may not fit all languages.
- Without a matching index, Oracle may have to evaluate the function over many rows.
- `NULL` column values still yield `NULL`; define a missing-data policy.

### 10.2. Function-based index on UPPER

If searches by `UPPER(username)` run frequently, you can create an index on the expression:

```sql
CREATE INDEX ix_app_users_upper_username
ON app_users (UPPER(username));
```

Queries must use the matching expression:

```sql
SELECT user_id, username
FROM app_users
WHERE UPPER(username) = UPPER(:p_username);
```

Oracle can use the function-based index when the expression and predicate match the index, statistics, and cost plan. Creating an index **does not force the optimizer to use it**; inspect the actual execution plan and workload.

### 10.3. Unique function-based index to enforce case-insensitive uniqueness

Suppose usernames must be case-insensitively unique per application rules. You can create:

```sql
CREATE TABLE lab_case_users (
    user_id  NUMBER PRIMARY KEY,
    username VARCHAR2(80 CHAR) NOT NULL
);

CREATE UNIQUE INDEX ux_lab_case_users_upper
ON lab_case_users (UPPER(username));
```

Then `Lan` and `LAN` produce the same index key `LAN`, preventing both from coexisting under the unique index. Note that this is a **unique index on an expression**, not a standard `UNIQUE` constraint declared directly on the `USERNAME` column. While it enforces expression uniqueness, do not assume it shares the exact metadata or foreign-key reference capabilities of a standard column unique constraint.

Because `USERNAME` is declared `NOT NULL`, the example disallows multiple missing usernames. If an indexed expression can evaluate to `NULL`, B-tree indexes follow specific rules for null keys; add `NOT NULL` or additional constraints per business rules.

### 10.4. Using NLS_UPPER with a fixed rule

For multilingual data, a specific NLS expression may be required:

```sql
-- Illustrative example; choose an NLS_SORT matching your requirements and Oracle version.
SELECT user_id, username
FROM lab_case_users
WHERE NLS_UPPER(username, 'NLS_SORT = XTurkish') =
      NLS_UPPER(:p_username, 'NLS_SORT = XTurkish');
```

To index this expression, the index expression and query expression must match:

```sql
-- Design example requiring testing on the target version.
CREATE INDEX ix_lab_case_users_turkish
ON lab_case_users (
    NLS_UPPER(username, 'NLS_SORT = XTurkish')
);
```

Using an explicit `nlsparam` decouples case mapping from implicit session NLS settings. Still, creating function-based indexes on linguistic expressions must be thoroughly tested for stability, collation interaction, and index usability on your target Oracle version.

### 10.5. Case-insensitive or accent-insensitive collations

Oracle offers collations such as `BINARY_CI` (case-insensitive) and `BINARY_AI` (accent-insensitive and case-insensitive) in supported contexts and releases. Collation governs **how strings are compared and sorted**, unlike mutating stored values via `UPPER`/`LOWER`.

In releases supporting **data-bound collation**, you can declare collation at the column or expression level per that release's syntax and prerequisites. Conceptual example:

```sql
-- Check COLLATE syntax against the target Oracle version/configuration.
-- Illustrative example for environments supporting data-bound collation:
CREATE TABLE lab_collation_users (
    user_id NUMBER PRIMARY KEY,
    username VARCHAR2(80 CHAR) COLLATE BINARY_CI
);
```

Do not copy `COLLATE` DDL to an older release that does not support it or lacks required prerequisites. Also, do not assume `BINARY_AI` fits every Vietnamese search requirement; ignoring accents can collapse distinct names into equivalents, causing uniqueness collisions or unexpected search hits.

### 10.6. Choosing an approach by requirement

| Requirement | Approach to Consider | Notes |
|---|---|---|
| Case-insensitive lookup on ASCII codes | `UPPER(col) = UPPER(:value)` | Simple; verify index usage |
| Frequent searches on large tables | Function-based index on the same expression | Measure execution plans and DML overhead |
| Case-insensitive unique usernames | Unique function-based index or dedicated normalized column | Check for existing duplicates before creating |
| Languages with special casing rules | `NLS_UPPER`/`NLS_LOWER` with explicit `nlsparam` | Verify NLS sort and test with real data |
| Accent- and case-insensitive comparisons | Suitable collation if supported by the release | Watch for collisions and linguistic rules |
| Preserve original casing | Keep original column; add separate normalized expression/index | Do not update the raw column just for search |

## 11. Character set and collation are two separate layers

A common misconception is thinking `AL32UTF8` automatically makes all comparisons case-insensitive or accent-insensitive. The **character set** defines the repertoire of characters and how they are encoded; **collation** defines comparison and sorting rules.

| Layer | Question Answered | Examples |
|---|---|---|
| Character set | Which characters can be represented and how are they encoded? | `AL32UTF8`, `AL16UTF16` |
| Case mapping | What uppercase/lowercase character does a letter map to? | `UPPER`, `LOWER`, `NLS_UPPER` |
| Collation | How are two strings compared and ordered? | `BINARY`, `BINARY_CI`, `BINARY_AI`, linguistic sort |
| Unicode normalization | How are canonically equivalent Unicode sequences standardized? | NFC/NFD in a supporting layer |

For example, an `AL32UTF8` database can store a wide range of Unicode characters, yet a binary comparison still treats two different code-point sequences as unequal. To search case-insensitively, choose an appropriate collation or normalize per requirements. To treat differently composed Unicode forms as equivalent, address normalization separately.

## 12. Java/JDBC integration: Unicode data and case conversion

Java stores `String` as Unicode; the JDBC driver transmits strings to Oracle and handles conversions based on column and database types. When an application handles Vietnamese or multilingual text, verify **both data before sending and data after reading**.

### 12.1. Bind Strings instead of concatenating SQL

```java
String sql = """
    SELECT user_id, username
    FROM lab_case_users
    WHERE UPPER(username) = UPPER(?)
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setString(1, inputUsername);

    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            long userId = rs.getLong("user_id");
            String username = rs.getString("username");
            // Process result according to the application contract.
        }
    }
}
```

Bind parameters avoid splicing data into SQL syntax and keep data in its proper role. Never write `UPPER('` + input + `')`, which introduces SQL injection risks as well as quoting and encoding bugs.

### 12.2. Verifying Vietnamese data end to end

A useful test set might include:

```text
Nguyễn An
NGUYỄN AN
nguyễn an
Đặng Thị Lan
đặng thị lan
İstanbul
Istanbul
istanbul
```

Do not assume all of these become equal after `UPPER`/`LOWER`; define explicit requirements for case, accents, and language rules. Verify:

1. Java receives strings from HTTP/JSON/CSV with valid Unicode.
2. JDBC binds and inserts properly into `VARCHAR2`/`NVARCHAR2` columns.
3. Oracle stores and returns the exact characters.
4. `UPPER`/`LOWER`/`NLS_UPPER` return expected output on the target database.
5. Collation and indexes deliver search and uniqueness behavior matching the contract.

### 12.3. Do not confuse NLS_LANG with all JDBC drivers

Older client tools or OCI connections use specific environment encoding variables; you cannot copy SQL*Plus/OCI settings mechanically to JDBC Thin. When character corruption occurs, inspect the exact **driver, client, runtime environment, and transport path**. Setting an arbitrary NLS environment variable will not automatically fix broken encoding in a Java application.

## 13. Testing case functions and rules with boundary data

Do not test only `abc` and `ABC`. A multilingual test suite should cover:

| Data Category | Examples | Questions to Confirm |
|---|---|---|
| Basic ASCII | `oracle`, `ORACLE`, `Oracle` | Are UPPER/LOWER and equality results accurate? |
| Vietnamese diacritics | `Đặng`, `đặng`, `Nguyễn` | Are accented characters converted accurately? |
| Locale-specific letters | `i`, `I`, `ı`, `İ` | Which Turkish/locale rules apply? |
| Acronyms | `API`, `SQL`, `eBay` | Does INITCAP break required casing? |
| Punctuation / whitespace | `an-nguyen`, `an  nguyen`, `O'Connor` | Do INITCAP word boundaries match expectations? |
| NULL / empty string | `NULL`, `''` | Do API and SQL distinguish missing state properly? |
| Composed Unicode | precomposed characters vs. base + combining mark | Is normalization needed? |
| Long strings | strings near column limits | Does conversion affect byte/index limits? |

### 13.1. Create a small test table

```sql
CREATE TABLE lab_case_conversion (
    id NUMBER PRIMARY KEY,
    raw_text VARCHAR2(200 CHAR)
);

INSERT INTO lab_case_conversion VALUES (1, 'oracle database');
INSERT INTO lab_case_conversion VALUES (2, 'ORACLE DATABASE');
INSERT INTO lab_case_conversion VALUES (3, 'Đặng Thị Lan');
INSERT INTO lab_case_conversion VALUES (4, 'API and SQL');
INSERT INTO lab_case_conversion VALUES (5, NULL);
COMMIT;
```

### 13.2. Run all three functions and observe

```sql
SELECT id,
       raw_text,
       UPPER(raw_text) AS upper_text,
       LOWER(raw_text) AS lower_text,
       INITCAP(raw_text) AS initcap_text,
       LENGTH(raw_text) AS char_length,
       LENGTHB(raw_text) AS byte_length
FROM lab_case_conversion
ORDER BY id;
```

Compare row 4 to see how `INITCAP` turns `API` into `Api` and `SQL` into `Sql`. Row 5 shows all three functions returning `NULL`. For the Vietnamese row, verify the result against your environment's character set and Oracle version.

### 13.3. Test case-insensitive search

```sql
SELECT id, raw_text
FROM lab_case_conversion
WHERE UPPER(raw_text) = UPPER('ORACLE DATABASE')
ORDER BY id;
```

Expected results include rows 1 and 2. Row 5 is excluded because `UPPER(NULL)` is `NULL`, and comparing it to a string evaluates to `UNKNOWN`.

After practicing, clean up only if you confirm this is a lab table you created in DEV/TEST:

```sql
DROP TABLE lab_case_conversion PURGE;
```

`DROP TABLE ... PURGE` permanently drops the object and data without sending it to the recycle bin; it is DDL with an implicit commit. Never run it on real tables or shared schemas without authorization.

## 14. Performance and common design mistakes

### 14.1. Functions on columns can alter access paths

If there is a standard B-tree index on `USERNAME`, the query:

```sql
WHERE UPPER(username) = 'LAN'
```

is no longer a direct comparison on the raw `USERNAME` values. The optimizer may not use the standard index as hoped. A function-based index on `UPPER(USERNAME)` is an appropriate option when the workload warrants it.

### 14.2. Do not create function-based indexes on every text column

Indexes consume storage and increase the cost of `INSERT`, `UPDATE`, and `DELETE`, because Oracle must maintain the index expression whenever data changes. Create them only for frequent queries with measurable benefit. If you only need uppercase display in a small report, `UPPER` in `SELECT` is usually enough.

### 14.3. Unique normalized indexes can expose existing duplicates

Before creating:

```sql
CREATE UNIQUE INDEX ux_users_upper_name
ON users (UPPER(username));
```

check for values sharing the same normalized expression:

```sql
SELECT UPPER(username) AS normalized_name,
       COUNT(*) AS row_count
FROM users
WHERE username IS NOT NULL
GROUP BY UPPER(username)
HAVING COUNT(*) > 1;
```

If this query returns any rows, the unique index creation will fail. You must determine which record is valid, how to merge or rename duplicates, and any foreign-key impacts before modifying data. Never delete an account arbitrarily just to make index creation succeed.

### 14.4. Use the same rule across all write and search paths

If inserts use `LOWER(username)`, search screens use `UPPER(username)`, batch imports leave values untouched, and an index uses a different `NLS_UPPER` expression, the system will behave inconsistently. Normalization rules must be defined **once at the business level**, then implemented uniformly across the database and applications.

### 14.5. INITCAP is not a raw-data cleanup tool

Do not run bulk `UPDATE people SET full_name = INITCAP(full_name)` statements merely because stored names are all uppercase. Personal names can have compound surnames, prefixes, initials, or custom capitalization. Display formatting should follow rules approved by data owners; keep the original input when traceability is needed.

## 15. Common errors and misconceptions

| Misconception | Why It Is Wrong | Recommended Practice |
|---|---|---|
| `UPPER` removes diacritics | It only converts to uppercase; accents remain | Use accent-insensitive collation or normalization as required |
| `LOWER` produces identical results in all locales | Some letters have language-specific mappings | Consider `NLS_LOWER` with explicit rules |
| `INITCAP` understands personal names and acronyms | It applies mechanical word-boundary rules | Format via application rules or dictionaries |
| `UPPER` modifies underlying table data | Calling it in SELECT only returns a transformed expression | Use controlled UPDATE if persistence is genuinely needed |
| `UPPER` automatically makes all comparisons case-insensitive | It only transforms an expression; collation and locale still apply | Use consistent expressions or explicit collation |
| `AL32UTF8` means case-insensitive comparison | Character set is not collation | Choose comparison/collation rules separately |
| `VARCHAR2(100)` always holds 100 Unicode characters | Length may be declared in BYTE semantics | Use `CHAR` semantics when appropriate and check `LENGTHB` |
| Visually identical strings always compare equal | Unicode allows multiple code-point representations | Define normalization and collation policies |
| `UPPER` and `NLS_UPPER` are always equivalent | NLS functions can apply linguistic mappings | Choose based on language needs and test |
| `ALTER SESSION` alone ensures uniform search across apps | Pooled sessions can carry differing settings | Manage NLS/collation cleanly at app/database level |
| Function-based indexes are always chosen by the optimizer | The optimizer decides based on cost and expressions | Inspect execution plans, statistics, and workload |
| Creating a unique index on `UPPER(col)` always succeeds | Data may collide after normalization | Check for duplicates beforehand |
| `UPPER(NULL)` returns an empty string | The result remains NULL | Use `IS NULL`/`COALESCE` per business logic |

## 16. Self-check questions

**Question 1.** What does `UPPER('Oracle Database')` return?

**Answer:** `ORACLE DATABASE`.

**Question 2.** Does `LOWER` automatically strip Vietnamese diacritics?

**Answer:** No. `LOWER` converts to lowercase; accents are preserved according to the input characters and active mappings.

**Question 3.** Is `INITCAP('API AND SQL')` guaranteed to return `API and SQL`?

**Answer:** No. It returns `Api And Sql`; it does not understand acronyms or editorial casing rules.

**Question 4.** Does a database using `AL32UTF8` automatically mean `WHERE name = 'lan'` matches `LAN`?

**Answer:** No. Character set and collation are separate concepts; case-insensitive comparison requires explicit rules or collation.

**Question 5.** How can you write a simple case-insensitive username lookup expression?

**Answer:** `WHERE UPPER(username) = UPPER(:p_username)`, provided standard case mapping satisfies business requirements.

**Question 6.** If queries frequently filter by `UPPER(username)`, what index can be considered?

**Answer:** A function-based index on `UPPER(username)`, after checking duplicates, DML overhead, and execution plans.

**Question 7.** Why can `NLS_UPPER` differ from `UPPER`?

**Answer:** `NLS_UPPER` supports linguistic case-mapping rules and accepts `nlsparam`; `UPPER` uses the function's default character mapping.

**Question 8.** Why can two Unicode strings that look identical on screen compare unequal?

**Answer:** They may use different code-point representations (such as precomposed characters versus combining marks); case conversion does not normalize Unicode.

**Question 9.** Should you run `ALTER SESSION SET NLS_SORT = BINARY_CI` on every request in a pooled application?

**Answer:** Not indiscriminately. Pooled sessions are reused; you must manage/reset state and evaluate `NLS_COMP`, collation, indexes, and execution plans.

**Question 10.** You create a unique index on `UPPER(username)`, but the table already contains `Lan` and `LAN`. What happens?

**Answer:** Both rows generate the same normalized key `LAN`, so creating the unique index fails until the duplicate data is resolved per business policy.

## Conclusion

**`UPPER`**, **`LOWER`**, and **`INITCAP`** are string case-transformation functions; they do not strip accents, normalize Unicode, or govern all comparison semantics. **`NLS_UPPER`**, **`NLS_LOWER`**, and **`NLS_INITCAP`** support linguistic case mapping and accept explicit NLS parameters. Their results must always be interpreted in the context of the database/national character sets, collation, and session NLS settings.

When implementing case-insensitive search or uniqueness, choose a consistent normalization rule, check for existing duplicates after conversion, evaluate function-based indexes or appropriate collations, and test with real Unicode data. In Java/JDBC applications, ensure strings are bound and stored with the proper encoding; never use case-conversion functions to mask encoding bugs or substitute for business rules. This approach ensures consistent behavior across DEV, TEST, production, and multilingual clients.
