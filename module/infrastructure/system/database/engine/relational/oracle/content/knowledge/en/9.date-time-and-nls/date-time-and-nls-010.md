# NLS_NUMERIC_CHARACTERS, NLS_SORT, and NLS_COMP When Processing Oracle Data

When an Oracle system serves users from multiple countries, **the same numeric value can be written as different strings**, and **the same list of names can be sorted or compared under different rules**. For example, the string `1.234,56` is commonly read as one thousand two hundred thirty-four point five six under one convention, while `1,234.56` expresses the same number under another. Similarly, `Lan`, `lan`, and `Lân` may be treated as distinct or equivalent in certain lookups depending on comparison rules.

Oracle Database provides **National Language Support (NLS)** to govern these differences. Among NLS settings, three important parameters are:

- **`NLS_NUMERIC_CHARACTERS`:** defines the decimal separator and the thousands group separator when *converting/formatting numbers to strings*.
- **`NLS_SORT`:** selects the sorting/linguistic rule (collation), such as binary code-point ordering vs. case-insensitive sorting.
- **`NLS_COMP`:** controls the role of linguistic comparison rules in SQL comparison predicates; particularly critical when paired with `NLS_SORT`.

These three parameters **do not turn a `NUMBER` column into `VARCHAR2`**, do not rewrite stored data whenever a session changes NLS, and are not synonymous with the database character set. They govern **string representation, parsing, and comparison** in specific contexts.

After this lesson, you will be able to:

1. Query a session's active NLS values and distinguish session settings from instance defaults.
2. Parse `VARCHAR2` into `NUMBER` with `TO_NUMBER` and format numbers as text with `TO_CHAR` using explicit decimal/group separators.
3. Explain why the SQL numeric literal `1234.56` differs from the string `'1.234,56'`.
4. Distinguish `NLS_SORT` ordering from `=`, `LIKE`, and predicates affected by `NLS_COMP`.
5. Choose case/accent-sensitive vs. insensitive comparisons and recognize their impact on search, sorting, uniqueness, and indexes.
6. Write queries and applications resilient to NLS changes from users, clients, or connection pools.

> Version note: From Oracle Database 12.2 onward, Oracle supports **data-bound collations** and the `COLLATE` clause in applicable contexts. Collation declared directly on columns or expressions can take precedence over session parameters. This lesson introduces the traditional session NLS model first, then highlights what to check on databases using declared collations. Never assume every object on every Oracle release is governed solely by session `NLS_SORT` and `NLS_COMP`.

## 1. The big picture of NLS in Oracle

NLS comprises several setting groups, such as:

| Group | Example parameters | Primary responsibility |
| --- | --- | --- |
| Number formatting | `NLS_NUMERIC_CHARACTERS` | Decimal and group separators in numeric representations |
| Date language/formatting | `NLS_DATE_LANGUAGE`, `NLS_DATE_FORMAT` | Month/day names and default formats when converting dates to strings |
| Territory | `NLS_TERRITORY` | Territory-based formatting defaults |
| Linguistic sorting | `NLS_SORT` | Collation rules in applicable sorting/comparison operations |
| Comparison mode | `NLS_COMP` | Binary vs. linguistic comparisons in applicable contexts |
| Message language | `NLS_LANGUAGE` | Several default language and message settings |

The three parameters in this lesson relate to one another yet **do not substitute for each other**:

```text
                  Oracle SQL session
                          │
             ┌────────────┴─────────────┐
             │                          │
       NUMERIC DATA                 TEXT DATA
             │                          │
             ▼                          ▼
 NLS_NUMERIC_CHARACTERS             NLS_SORT
  - Decimal separator           - Binary / linguistic
  - Group separator             - Case/accent sensitivity
             │                          │
             ▼                          ▼
  TO_NUMBER / TO_CHAR            ORDER BY / NLSSORT
  (and implicit conversion)             │
                                        ▼
                                     NLS_COMP
                               - Comparison predicates
                               - Binary / linguistic
```

### 1.1. NLS operates at multiple levels

An NLS setting may inherit a **default** from database/instance configuration, yet a client-created session can carry different values. Drivers, SQL clients, and connection pools can also configure or mutate session NLS state.

To inspect **the current session values**, run:

```sql
SELECT parameter, value
FROM nls_session_parameters
WHERE parameter IN (
    'NLS_NUMERIC_CHARACTERS',
    'NLS_SORT',
    'NLS_COMP'
)
ORDER BY parameter;
```

Example output:

```text
NLS_COMP                BINARY
NLS_NUMERIC_CHARACTERS  .,
NLS_SORT                BINARY
```

This is an **example**, not mandatory values. The actual output returned by the query reflects the state of your active session.

Related views:

- `NLS_SESSION_PARAMETERS`: values currently active in the session.
- `NLS_INSTANCE_PARAMETERS`: instance-level NLS values per corresponding view.
- `NLS_DATABASE_PARAMETERS`: database-level NLS parameter info.

Never use the database view output as proof that a **specific connection** holds the same values. When unexplained differences arise, inspect the exact session and how the connection was created.

### 1.2. Modifying the session for practice

`ALTER SESSION` alters settings for **the current session only**, requiring neither data updates nor database-wide configuration changes:

```sql
ALTER SESSION SET NLS_NUMERIC_CHARACTERS = ',.';
ALTER SESSION SET NLS_SORT = BINARY_CI;
ALTER SESSION SET NLS_COMP = LINGUISTIC;
```

Another session in the same database can retain different NLS values. With a **connection pool**, physical sessions are reused: if one request changes NLS and returns the connection to the pool without resetting, the next request suffers unintended side effects. Therefore, if an application depends on fixed session NLS, design explicit **connection initialization and reset** hooks.

## 2. NLS_NUMERIC_CHARACTERS: distinguishing decimal and group separators

`NLS_NUMERIC_CHARACTERS` consists of **two characters in order**:

1. First character: **decimal character** (fractional separator).
2. Second character: **group separator** (digit grouping, such as thousands).

Both characters must differ and obey Oracle's separator restrictions. In practice, common pairs are:

| Parameter value | Decimal separator | Group separator | Illustrative string |
| --- | --- | --- | --- |
| `'.,'` | `.` | `,` | `1,234.56` |
| `',.'` | `,` | `.` | `1.234,56` |

**Order matters.** `'.,'` does not mean the same thing as `',.'`. You cannot supply two identical characters because Oracle could not distinguish their roles.

### 2.1. Effect on TO_CHAR with format elements D and G

In Oracle numeric format models:

- `D` marks the **NLS decimal separator** position.
- `G` marks the **NLS group separator** position.
- `9` and `0` control digit positions per format model rules.
- `FM` is commonly used to suppress blank padding in formatted results.

Example formatting the same number under two conventions **without changing the session**:

```sql
SELECT
    TO_CHAR(
        1234.56,
        'FM9G999D00',
        'NLS_NUMERIC_CHARACTERS = ''.,'''
    ) AS format_dot_decimal,
    TO_CHAR(
        1234.56,
        'FM9G999D00',
        'NLS_NUMERIC_CHARACTERS = '',.'''
    ) AS format_comma_decimal
FROM dual;
```

Expected output:

```text
FORMAT_DOT_DECIMAL   FORMAT_COMMA_DECIMAL
------------------   --------------------
1,234.56             1.234,56
```

The third argument of `TO_CHAR` here is an **nlsparam string**. The SQL literal `'NLS_NUMERIC_CHARACTERS = '',.'''` escapes inner single quotes by doubling them (`''`). It specifies decimal comma, group dot. Because the rule lives directly inside the expression, output is far less dependent on session NLS.

### 2.2. TO_NUMBER parses strings using corresponding separators

Conversely, when the input is a **string**, use `TO_NUMBER` with an explicit format model:

```sql
SELECT
    TO_NUMBER(
        '1,234.56',
        '9G999D99',
        'NLS_NUMERIC_CHARACTERS = ''.,'''
    ) AS number_from_us_style,
    TO_NUMBER(
        '1.234,56',
        '9G999D99',
        'NLS_NUMERIC_CHARACTERS = '',.'''
    ) AS number_from_comma_style
FROM dual;
```

Both expressions return the `NUMBER` value **1234.56**. Once converted to `NUMBER`, a number no longer carries a "decimal comma" or "decimal dot" as a storage attribute. Which separator appears on future display depends on format/NLS when converting **NUMBER → text**.

### 2.3. What if you only change the session?

You can practice with:

```sql
ALTER SESSION SET NLS_NUMERIC_CHARACTERS = ',.';

SELECT
    TO_NUMBER('1.234,56', '9G999D99') AS amount,
    TO_CHAR(1234.56, 'FM9G999D00') AS amount_as_text
FROM dual;
```

In a session with decimal `,` and group `.`, the formatted text is `1.234,56`. However, if this statement runs in another session using `NLS_NUMERIC_CHARACTERS='.,'`, the input string may be misinterpreted or fail with a conversion error depending on format and input.

**Recommendation:** for data files, APIs, or cross-system integration, define **one canonical format** and convert explicitly at ingestion/export boundaries. Never expect the database to guess regional rules from a string like `1,234`, which can mean one thousand two hundred thirty-four or one point two three four depending on convention.

### 2.4. SQL numeric literals are not locale strings

In Oracle SQL syntax, a **numeric literal** uses a **period** as its decimal point:

```sql
SELECT 1234.56 AS amount
FROM dual;
```

Running:

```sql
ALTER SESSION SET NLS_NUMERIC_CHARACTERS = ',.';
```

**does not change SQL numeric literal syntax** to `1234,56`. Commas in SQL syntax separate expressions; for example, `SELECT 1, 5 FROM dual` selects two expressions, not a single numeric literal 1.5.

Distinguish them:

| Example | Nature |
| --- | --- |
| `1234.56` in SQL | Numeric literal, SQL syntax |
| `'1234.56'` | Character string, convertible to a number |
| `'1.234,56'` | Character string with locale-specific group/decimal separators |
| `:amount` bound as `NUMBER` | Typed numeric value; no text separator parsing required |

Never concatenate user-typed numeric text into SQL to form a numeric literal. Use typed bind parameters or parse/validate at the input boundary and bind as `NUMBER`.

### 2.5. Implicit conversion creates subtle bugs

Seemingly harmless example:

```sql
SELECT *
FROM invoices
WHERE total_amount = '1,25';
```

Suppose `TOTAL_AMOUNT` is `NUMBER`. Because the right-hand side is a string, Oracle must apply implicit conversion rules. In one session `'1,25'` might parse with a decimal comma; in another session it may fail or parse differently.

Clearer form:

```sql
SELECT *
FROM invoices
WHERE total_amount = 1.25;
```

In Java/JDBC applications, bind `NUMBER` directly:

```java
String sql = "SELECT invoice_id FROM invoices WHERE total_amount = ?";

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setBigDecimal(1, new java.math.BigDecimal("1.25"));
    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            // Process invoice_id.
        }
    }
}
```

The Java code uses `"1.25"` **only to construct `BigDecimal` in Java**, then transmits a typed numeric value over JDBC—it does not send a locale string hoping Oracle parses it. If user input arrives with a decimal comma, the application must parse it under the confirmed locale before constructing `BigDecimal`, rather than blindly stripping dots or commas.

### 2.6. Number formatting for CSV and reports

A classic real-world bug is emitting comma-delimited CSV containing unquoted number strings like `1,234.56`. Without standard CSV quoting/escaping, downstream parsers split it across multiple columns.

When exporting files or JSON:

- Keep `NUMBER` values as native JSON numbers in APIs supporting typed numbers.
- If text output is mandatory, standardize both format and text encoding.
- For CSV, apply standard **quoting/escaping**, not just separator tweaks.
- On import, document column types, locale, format models, encoding, and invalid-data policies.
- Avoid depending on another job's `ALTER SESSION` altering implicit conversions.

## 3. NLS_SORT: string sorting rules

`NLS_SORT` defines **binary** or **linguistic** comparison/sorting order in operations where Oracle applies session-level collation.

Common values:

| Value | General purpose | Example effect |
| --- | --- | --- |
| `BINARY` | Based on binary/code-point ordering per Oracle mechanics | Case and diacritics may sort differently than linguistic expectations |
| `BINARY_CI` | **Case-insensitive** binary-style collation | `Lan` and `lan` can share sort order/match in collation-aware operations |
| `BINARY_AI` | **Accent-insensitive** binary-style collation (typically also case-insensitive) | `Lan`, `Lân`, and `lan` can be treated as equivalent in collation-aware comparisons |
| Language-specific linguistic sort | Sorting rules tailored to a specific language | Sorts words/names per expectations of that region/language |

**`BINARY_CI` is not the same as `BINARY_AI`.** `CI` is *case-insensitive*; `AI` is *accent-insensitive* (and usually case-insensitive too). Do not choose `AI` for systems where Vietnamese diacritics distinguish distinct words or business identities; stripping accents can merge unrelated records in queries.

Supported sort names and collation versions vary by Oracle version, edition, and character set. For Vietnamese text, evaluate **an appropriate linguistic collation** and test real accented strings rather than assuming `BINARY_AI` matches Vietnamese dictionary order.

### 3.1. Why does binary order differ from dictionary order?

Binary order generally compares raw encoded bytes/code points, whereas a language dictionary applies specialized rules for uppercase, lowercase, accented letters, and multi-character combinations. Consider sample values:

```text
Lan
lan
Lân
Anh
Ánh
Minh
```

Do not guess exact positions across collations by eye. Instead, specify the collation in your query and observe the real ordering on your target database release.

### 3.2. Sorting by session NLS_SORT

In the traditional session NLS model:

```sql
ALTER SESSION SET NLS_SORT = BINARY;

SELECT full_name
FROM lab_nls_people
ORDER BY full_name;
```

Then:

```sql
ALTER SESSION SET NLS_SORT = BINARY_CI;

SELECT full_name
FROM lab_nls_people
ORDER BY full_name;
```

Sorting rules apply to expressions according to the effective collation. In modern databases using **explicit collations** or column **data-bound collations**, setting `NLS_SORT` in the session may not govern every expression as it did in older models.

Never assume strings that tie under a collation preserve a stable relative order: if `Lan` and `lan` share the same sort key, the database can return them in different orders across runs. For paginated UIs, always add a deterministic **tie-breaker**:

```sql
SELECT id, full_name
FROM lab_nls_people
ORDER BY full_name, id;
```

### 3.3. NLSSORT: specifying the rule inline in the expression

`NLSSORT` computes a **linguistic sort key** (`RAW` type) under the specified collation:

```sql
SELECT id, full_name
FROM lab_nls_people
ORDER BY
    NLSSORT(full_name, 'NLS_SORT=BINARY_CI'),
    id;
```

Advantage: the expression states `BINARY_CI` explicitly instead of relying solely on the session's `NLS_SORT`. Adding `, id` stabilizes order when two names produce identical case-insensitive keys. When requirements call for accent sensitivity or a language-specific linguistic sort, choose the appropriate collation and document it.

`NLSSORT` returns a sort key, **not a modified copy of the text**. Data stored in `FULL_NAME` retains its original uppercase, lowercase, and diacritics.

## 4. NLS_COMP: when do SQL comparisons use linguistic rules?

This is the most common source of confusion. **`NLS_SORT` and `NLS_COMP` must be considered together** when evaluating `=`, `<`, `>`, `LIKE`, and collation-sensitive predicates in the traditional session NLS model.

### 4.1. NLS_COMP = BINARY

When `NLS_COMP=BINARY`, standard character comparisons under the classic session model use binary semantics, even if the session's `NLS_SORT` is set to `BINARY_CI`:

```sql
ALTER SESSION SET NLS_SORT = BINARY_CI;
ALTER SESSION SET NLS_COMP = BINARY;

SELECT id, full_name
FROM lab_nls_people
WHERE full_name = 'Lan';
```

For columns using traditional session collation and this sample data, `= 'Lan'` remains case-sensitive. That is why **changing `NLS_SORT` alone does not automatically make `WHERE` clauses case-insensitive**.

### 4.2. NLS_COMP = LINGUISTIC

When `NLS_COMP=LINGUISTIC`, Oracle uses `NLS_SORT` to perform linguistic comparisons in supported SQL predicates:

```sql
ALTER SESSION SET NLS_SORT = BINARY_CI;
ALTER SESSION SET NLS_COMP = LINGUISTIC;

SELECT id, full_name
FROM lab_nls_people
WHERE full_name = 'Lan'
ORDER BY id;
```

With `Lan` and `lan` in the sample table, both match under `BINARY_CI`; `Lân` remains distinct because the collation is accent-sensitive.

Switching to `BINARY_AI`:

```sql
ALTER SESSION SET NLS_SORT = BINARY_AI;
ALTER SESSION SET NLS_COMP = LINGUISTIC;

SELECT id, full_name
FROM lab_nls_people
WHERE full_name = 'Lan'
ORDER BY id;
```

Under `BINARY_AI`, names differing only in case or accents (`Lan`, `lan`, `Lân`) can match as equal. This is a **business choice**, not an unconditional "improvement": in Vietnamese, diacritics distinguish completely different words and identities.

### 4.3. Combined NLS_SORT and NLS_COMP matrix

| NLS_SORT | NLS_COMP | Expected behavior in session-style comparison |
| --- | --- | --- |
| `BINARY` | `BINARY` | Basic binary sorting and comparison |
| `BINARY_CI` | `BINARY` | Case-insensitive sorting when expression uses NLS sort; `WHERE col='x'` can remain binary |
| `BINARY_CI` | `LINGUISTIC` | Session-collated comparisons can become case-insensitive |
| `BINARY_AI` | `LINGUISTIC` | Comparisons can become case- and accent-insensitive |
| Other linguistic sort | `LINGUISTIC` | Comparisons follow the chosen linguistic rules when applicable |

Read this table with one proviso: **the column/expression must not have a higher-precedence collation**. In Oracle 12.2+, explicit collations, declared collations, and collation derivation rules can override session behavior.

### 4.4. NLS_COMP is not simply a case-sensitivity toggle

`NLS_COMP` governs whether eligible comparisons follow collation rules; `NLS_SORT` supplies the rule itself. For instance:

- `BINARY` with `NLS_COMP=LINGUISTIC` does not automatically become case-insensitive.
- `BINARY_CI` with `NLS_COMP=BINARY` does not automatically make `WHERE name='lan'` case-insensitive.
- `BINARY_AI` can collapse accented variants onto the same comparison key, changing search behavior and business outcomes.

More complex operations—`LIKE`, `BETWEEN`, `IN`, pattern matching, and grouping/sorting—must be tested against your actual Oracle release and **the expression's effective collation**, rather than looking at two parameters and generalizing across all SQL.

## 5. Hands-on example: comparing names with uppercase and accents

Practice in an isolated schema such as `LAB_USER`, avoiding collisions with active objects. Pick a different table name if needed.

### 5.1. Create sample data

```sql
CREATE TABLE lab_nls_people (
    id        NUMBER PRIMARY KEY,
    full_name VARCHAR2(100) NOT NULL
);

INSERT INTO lab_nls_people VALUES (1, 'Lan');
INSERT INTO lab_nls_people VALUES (2, 'lan');
INSERT INTO lab_nls_people VALUES (3, 'Lân');
INSERT INTO lab_nls_people VALUES (4, 'Anh');
INSERT INTO lab_nls_people VALUES (5, 'Ánh');
INSERT INTO lab_nls_people VALUES (6, 'Minh');

COMMIT;
```

This merely illustrates case and accents. Results depend on **the collation of `FULL_NAME`**, the database, and the session. If your database declares a column-level collation overriding session rules, verify the `WHERE` results below under the effective collation.

### 5.2. Record initial session state

```sql
SELECT parameter, value
FROM nls_session_parameters
WHERE parameter IN ('NLS_SORT', 'NLS_COMP')
ORDER BY parameter;
```

Note both values so you can restore them after testing.

### 5.3. Test binary search

```sql
ALTER SESSION SET NLS_SORT = BINARY;
ALTER SESSION SET NLS_COMP = BINARY;

SELECT id, full_name
FROM lab_nls_people
WHERE full_name = 'Lan'
ORDER BY id;
```

With this stored data and a default column using traditional session binary comparison, only the exact match `Lan` is returned.

### 5.4. Test linguistic, case-insensitive

```sql
ALTER SESSION SET NLS_SORT = BINARY_CI;
ALTER SESSION SET NLS_COMP = LINGUISTIC;

SELECT id, full_name
FROM lab_nls_people
WHERE full_name = 'Lan'
ORDER BY id;
```

When collation honors session NLS, both `Lan` and `lan` match, while `Lân` is excluded due to its accent.

### 5.5. Test linguistic, accent-insensitive

```sql
ALTER SESSION SET NLS_SORT = BINARY_AI;
ALTER SESSION SET NLS_COMP = LINGUISTIC;

SELECT id, full_name
FROM lab_nls_people
WHERE full_name = 'Lan'
ORDER BY id;
```

You will see accented matches appear in the output. For sensitive data like personal names, identifiers, or Vietnamese vocabulary, evaluate carefully whether **accent-insensitive** matching is desirable.

### 5.6. Pin sorting inside individual queries

```sql
SELECT id, full_name
FROM lab_nls_people
ORDER BY
    NLSSORT(full_name, 'NLS_SORT=BINARY_CI'),
    id;
```

Then test:

```sql
SELECT id, full_name
FROM lab_nls_people
ORDER BY
    NLSSORT(full_name, 'NLS_SORT=BINARY_AI'),
    id;
```

Compare name positions. Output order changes because accented letters share the same bucket under `BINARY_AI`; `ID` breaks ties whenever names share a sort key.

### 5.7. Restore the session

In a practice environment, if you want to return to baseline values so other exercises are unaffected:

```sql
ALTER SESSION SET NLS_SORT = BINARY;
ALTER SESSION SET NLS_COMP = BINARY;
ALTER SESSION SET NLS_NUMERIC_CHARACTERS = '.,';
```

Those three are **example baseline values**, **not guaranteed to restore your exact original state** if your session started with different conventions. To truly restore, apply the values recorded in step 5.2 along with your original `NLS_NUMERIC_CHARACTERS`, or open a fresh session per application initialization policy.

## 6. Sorting, searching, and uniqueness are three different problems

Three business requirements are frequently conflated:

1. **Sorting names for display:** may prefer dictionary order, case-insensitive.
2. **Matching names typed in a search box:** may allow accent- and case-insensitive matching to improve recall.
3. **Determining whether two identifiers collide:** must enforce strict identity/uniqueness rules.

For example, `Lan` and `Lân` may both appear in a **fuzzy search**, yet should never automatically be treated as the same person or username. A collation suited for search does not replace a stable identity key.

### 6.1. Does session NLS automatically alter UNIQUE constraints?

**Never assume changing `NLS_COMP`/`NLS_SORT` in a session causes every unique constraint in the database to treat `Lan` and `lan` as duplicates.** Unique constraints and their backing indexes follow object/collation definitions and Oracle release rules.

In modern Oracle with **data-bound collations**, a column declared case-insensitive carries different semantics from a binary column. Uniqueness must be designed in the **schema, indexes, and constraints** and verified with controlled tests—never left to user-level NLS session settings.

### 6.2. When case-insensitive search is required

Several approaches exist depending on Oracle version and requirements:

- Declare an appropriate collation on the column/expression where supported and schema changes are governed.
- Use `NLSSORT` or `COLLATE` in expressions per version support.
- Use a normalized expression such as `UPPER(column)` backed by a function-based index for simple cases.
- Use dedicated search/indexing capabilities for complex search requirements.

For example, `UPPER(name) = UPPER(:search_name)` supports basic case-insensitive matching, yet is **not strictly equivalent** to every linguistic collation: casing rules and special characters vary by language. Nor does `BINARY_AI` substitute for consistent identifier normalization.

## 7. Impact on indexes and performance

Oracle may need to compute **linguistic sort keys** to sort or compare under non-binary collations. If a query previously used a B-tree index in binary order, switching to linguistic comparison can cause the optimizer to choose another plan, add a sort step, or require a matching expression index.

### 7.1. Function-based index for a specific sort rule

Example on the lab table:

```sql
CREATE INDEX idx_lab_nls_people_ci
ON lab_nls_people (
    NLSSORT(full_name, 'NLS_SORT=BINARY_CI')
);
```

This index stores keys derived from `NLSSORT(...BINARY_CI)`. It can assist matching queries if the optimizer deems it beneficial and expression/metadata/stats prerequisites are met. **Creating an index never guarantees Oracle will use it**; inspect execution plans and real row volumes.

In production, function-based indexes add write and storage overhead, require up-to-date statistics, and are subject to sort-key length limits. Never create `BINARY_CI` and `BINARY_AI` indexes indiscriminately without understanding the workload.

### 7.2. SQL queries and session state affect execution plans

Suppose SQL:

```sql
SELECT id
FROM lab_nls_people
WHERE full_name = :full_name;
```

If the effective collation changes, the set of matching values changes—affecting **cardinality** and index eligibility. Never cache application results as if `'Lan'` always had one fixed equality rule when different requests or connections may use different NLS settings.

Cursors reused in the shared pool carry session environment context; changing session settings can affect cursor sharing and plan reuse per Oracle rules. With connection pools, enforce **one consistent NLS policy**, guard request-scoped overrides, and capture execution plans when troubleshooting.

### 7.3. ORDER BY results can produce tied sort keys

Under `NLS_SORT=BINARY_CI`, `ALPHA` and `alpha` share the same sort key. `ORDER BY name` leaves their relative order undefined. Paginated queries using `OFFSET/FETCH` become unstable if the sort key is non-unique.

Always append the primary key or a deterministic secondary key:

```sql
SELECT id, full_name
FROM lab_nls_people
ORDER BY
    NLSSORT(full_name, 'NLS_SORT=BINARY_CI'),
    id
OFFSET 0 ROWS FETCH NEXT 20 ROWS ONLY;
```

This yields stable pagination because `ID` is unique, while keeping collation-equivalent strings grouped consistently.

## 8. Data-bound collations and COLLATE in modern Oracle

Starting with Oracle Database 12.2, Oracle supports collations bound directly to SQL objects and expressions. Consequently, actual comparison behavior can be governed by:

- **Explicit collation:** stated inline in a SQL expression with `COLLATE` on supported versions/types.
- **Declared/data-bound collation:** collation attribute on a column or schema/object.
- **Collation derivation rules** for expressions.
- **Session NLS parameters:** particularly for expressions using session-derived collations, depending on context.

**Syntax illustration** on versions supporting `COLLATE`:

```sql
SELECT id, full_name
FROM lab_nls_people
WHERE full_name COLLATE BINARY_CI = 'lan'
ORDER BY id;
```

This expresses case-insensitive comparison **directly inside the expression** without altering the entire session's NLS. Validate syntax, collation derivation, and index usage on your actual release and configuration.

To inspect declared column collations on versions with the corresponding metadata, administrators can query dictionary views such as `USER_TAB_COLUMNS` (column `COLLATION` where supported) or schema metadata. If your view lacks a `COLLATION` column, do not assume the database is broken: it reflects version or feature differences.

**Key rule:** when diagnosing "I ran `ALTER SESSION SET NLS_COMP=LINGUISTIC` yet `WHERE` behavior didn't change," stop guessing NLS combinations and inspect **the actual collation of the column/expression** and your Oracle release mechanics.

## 9. Common pitfalls in data import/export

### 9.1. A NUMBER column fed by text input

Suppose a partner file contains:

```text
invoice_id;amount_text
1001;1.234,56
1002;99,50
```

Using `;` as delimiter, parsing `AMOUNT_TEXT` must specify the exact decimal and group separators. Invalid strings should raise errors for inspection—**never blindly strip all `.` or `,` characters and guess the number**.

Intentional conversion example:

```sql
SELECT
    TO_NUMBER(
        '1.234,56',
        '9G999D99',
        'NLS_NUMERIC_CHARACTERS='',.'''
    ) AS parsed_amount
FROM dual;
```

The `NUMBER` result is `1234.56`. By contrast, if `'1.234'` arrives without a format contract, you cannot tell whether it means one thousand two hundred thirty-four or one point two three four.

### 9.2. Data read from REST APIs / JSON

A JSON number such as:

```json
{"amount":1234.56}
```

differs from a JSON string:

```json
{"amount":"1.234,56"}
```

When APIs use typed JSON numbers, no locale-specific text conversion is needed to transmit the value. When APIs intentionally send formatted display strings, enforce an explicit locale/format contract and validate/parse at the right layer.

**Never infer backend storage format from frontend display locale.** An application serving both Vietnamese and English users stores the exact same `NUMBER`; only UI text rendering should adapt.

### 9.3. Comparing person names, product names, and identifiers

Each task has distinct requirements:

| Need | Approach |
| --- | --- |
| Sort names for UI display | Language-appropriate collation with tie-breaker |
| Case-insensitive name search | `BINARY_CI` or verified equivalent collation |
| Fuzzy accent-insensitive search | Use accent-insensitive only when business accepts approximate matches |
| Enforce unique usernames | Uniqueness/normalization rules per schema and app policy |
| Compare exact business codes | Binary/explicit semantics; never casually reuse search collations |

For accented languages especially, stripping accents merges distinct words and people. Never treat accent-insensitivity as harmless data normalization.

## 10. Comprehensive hands-on exercise on DUAL and sample data

The first steps create no tables and work in SQL Developer, SQLcl, or SQL*Plus. Name-lookup steps reuse `LAB_NLS_PEOPLE` from section 5 or can be adapted with a CTE.

### Step A — Record and inspect session NLS

```sql
SELECT parameter, value
FROM nls_session_parameters
WHERE parameter IN (
    'NLS_NUMERIC_CHARACTERS',
    'NLS_SORT',
    'NLS_COMP'
)
ORDER BY parameter;
```

Record the actual outputs before continuing.

### Step B — Two ways of displaying the same NUMBER

```sql
SELECT
    TO_CHAR(
        9876.5,
        'FM99G999D00',
        'NLS_NUMERIC_CHARACTERS=''.,'''
    ) AS dot_decimal,
    TO_CHAR(
        9876.5,
        'FM99G999D00',
        'NLS_NUMERIC_CHARACTERS='',.'''
    ) AS comma_decimal
FROM dual;
```

Expected: `9,876.50` and `9.876,50`. Verify that the input `NUMBER` did not change; it remains `9876.5`.

### Step C — Two differently formatted numeric strings

```sql
SELECT
    TO_NUMBER(
        '9,876.50',
        '99G999D99',
        'NLS_NUMERIC_CHARACTERS=''.,'''
    ) AS n1,
    TO_NUMBER(
        '9.876,50',
        '99G999D99',
        'NLS_NUMERIC_CHARACTERS='',.'''
    ) AS n2
FROM dual;
```

Both `NUMBER` results should be equal per the explicit rules. Explain why you should never pass raw `'9.876,50'` into arithmetic while relying on an uncontrolled app server session.

### Step D — Compare behavior after changing NLS_SORT and NLS_COMP

Assuming the lab table holds `Lan`, `lan`, and `Lân`:

```sql
ALTER SESSION SET NLS_SORT = BINARY;
ALTER SESSION SET NLS_COMP = BINARY;

SELECT id, full_name
FROM lab_nls_people
WHERE full_name = 'Lan'
ORDER BY id;
```

Continue:

```sql
ALTER SESSION SET NLS_SORT = BINARY_CI;
ALTER SESSION SET NLS_COMP = LINGUISTIC;

SELECT id, full_name
FROM lab_nls_people
WHERE full_name = 'Lan'
ORDER BY id;
```

Finally:

```sql
ALTER SESSION SET NLS_SORT = BINARY_AI;

SELECT id, full_name
FROM lab_nls_people
WHERE full_name = 'Lan'
ORDER BY id;
```

Answer: which combination matches `lan`? Which combination matches `Lân`? If output differs from expectations, inspect **column collation** and Oracle release before assuming session settings failed.

### Step E — Pin ORDER BY per SQL query

```sql
SELECT id, full_name
FROM lab_nls_people
ORDER BY
    NLSSORT(full_name, 'NLS_SORT=BINARY_CI'),
    id;
```

Compare with:

```sql
SELECT id, full_name
FROM lab_nls_people
ORDER BY
    NLSSORT(full_name, 'NLS_SORT=BINARY_AI'),
    id;
```

Observe names sharing a sort key and the role of `id` in pagination.

### Step F — Restore environment

Restore session parameters to the values captured in Step A, or close the lab connection and open a fresh connection under your client/application's standard settings. If the lab table is no longer needed, only the lab owner should drop it in the right schema; never touch objects outside the lesson scope.

## 11. Real-world troubleshooting

| Symptom | Causes to check | Diagnostic step |
| --- | --- | --- |
| `ORA-01722: invalid number` when filtering a `NUMBER` column with a string | Implicit conversion, non-numeric text, or incompatible separators | Check column/bind types, `NLS_NUMERIC_CHARACTERS`, and `TO_NUMBER` format |
| Same amount displays `1,234.56` on machine A and `1.234,56` on machine B | Different formats or session NLS | Inspect `NLS_SESSION_PARAMETERS`, `TO_CHAR` masks, and client settings |
| Numbers corrupted during export/import | Unspecified locale or separator | Verify data contract; parse explicitly and compare `NUMBER` values |
| `ORDER BY name` order changes after NLS change | Different collation/sort key | Check `NLS_SORT`, column collation, and `NLSSORT` |
| `WHERE name='Lan'` remains case-sensitive despite `NLS_SORT=BINARY_CI` | `NLS_COMP=BINARY` or higher-precedence expression collation | Inspect `NLS_COMP` and data-bound/explicit collations |
| Accented names collide in search results | Accent-insensitive collation | Review `BINARY_AI` against business requirements |
| Query slows down after NLS change | Optimizer stopped using prior index/plan; sort cost increased | Inspect execution plan, stats, and expression/index alignment |
| Pagination duplicates or skips rows when sorting names | Distinct names share the same linguistic sort key | Add unique tie-breaker `ORDER BY ... , id` |
| Next request in connection pool sees different behavior | Session NLS state altered without reset | Inspect connection init/reset code and trace per-session values |
| Set `NLS_COMP=LINGUISTIC` yet predicate behavior stayed unchanged | Column/expression has a declared collation | Inspect collation metadata and release rules |

### 11.1. Concise investigation workflow

```text
Wrong numeric value or wrong sort/search behavior?
                 │
        ┌────────┴──────────┐
        ▼                   ▼
   NUMERIC DATA          TEXT DATA
        │                   │
 NUMBER or text type?    ORDER BY or WHERE?
        │                   │
 NLS_NUMERIC_CHARACTERS  NLS_SORT / NLS_COMP
        │                   │
 TO_NUMBER / TO_CHAR     Column/expression collation
        │                   │
 Bind typed NUMBER       NLSSORT / COLLATE
        │                   │
        └────────┬──────────┘
                 ▼
      Inspect the exact session
                 │
                 ▼
  Compare results and execution plan
```

In both paths, verify **actual column types**, **session values**, **column/expression collation**, and **SQL/app formatting** before changing system settings. Altering a global NLS setting to fix one report can silently break queries in other applications.

## 12. Best practices for multilingual system design

### 12.1. Numeric data: store typed numbers, format at boundaries

- Store money, quantities, and rates using appropriate numeric types with explicit precision/scale.
- Bind numeric parameters as `NUMBER`/`BigDecimal`; avoid SQL string concatenation.
- Use `TO_NUMBER(text, mask, nlsparam)` when parsing text from a verified source.
- Use `TO_CHAR(number, mask, nlsparam)` for text output or fixed-convention reports.
- Never expect `NLS_NUMERIC_CHARACTERS` to change SQL numeric literal syntax.
- For JSON/CSV, document data types and separators explicitly; state the locale whenever numbers travel as strings.

### 12.2. Text data: choose collations aligned with business semantics

- Separate **UI sorting**, **case/accent-insensitive search**, and **identity/uniqueness checks** into three distinct requirements.
- Avoid accent-insensitive collations for identifiers where diacritics or exact characters matter.
- Add a unique tie-breaker whenever `ORDER BY` can produce identical sort keys.
- On Oracle releases with declared collations, inspect effective collation rather than only session NLS.
- Check execution plans and indexes when applying linguistic predicates to large tables.
- Test with realistic Vietnamese diacritics, casing, Unicode data, and colliding sort keys.

### 12.3. Sessions and connection pools: consistency is key

- Initialize essential NLS settings upon connection creation if the application relies on them.
- Reset session state before returning connections to the pool; prevent cross-request leakage.
- Prefer **explicit formatting in SQL or the application layer** for data interchange protocols.
- Never let one request set `NLS_COMP` for search and leave the session altered for subsequent business queries expecting different comparison rules.
- Test against production's actual Oracle version and collations, not just a local developer install.

## 13. Self-check questions

1. With `NLS_NUMERIC_CHARACTERS=',.'`, which character is the decimal separator and which is the group separator? How is `'1.234,56'` parsed with a matching format model?
2. Why does `SELECT 1234.56 FROM dual` remain a valid numeric literal after switching the session to a decimal comma?
3. Using `TO_CHAR` and `'FM9G999D00'`, how do you generate both `1,234.56` and `1.234,56` from **the same `NUMBER` value** without altering the session?
4. Why should you avoid `WHERE total_amount = '1,25'` when `TOTAL_AMOUNT` is `NUMBER` in a multi-region application?
5. If `NLS_SORT=BINARY_CI` while `NLS_COMP=BINARY`, can you conclude `WHERE name='Lan'` will be case-insensitive? Why or why not?
6. Under the session-style collation model, what condition is needed for `BINARY_AI` to apply to `WHERE` comparisons?
7. Why might `BINARY_AI` be unsuitable for deciding whether two usernames or two person names are identical?
8. What does `NLSSORT` return? Does it modify data stored in the column?
9. When two names share the same linguistic sort key, why must you add `id` to `ORDER BY` for pagination?
10. On Oracle 12.2+, why might a column with a declared collation ignore `ALTER SESSION SET NLS_COMP=LINGUISTIC` in searches?
11. What must you investigate when one request changes `NLS_SORT` and subsequent requests on a connection pool return altered results?
12. When should you consider indexing for linguistic collation searches, and why inspect the execution plan?

## 14. Summary

```text
NLS_NUMERIC_CHARACTERS = '.,'
  ├── decimal = '.'
  └── group   = ','
             ↓
TO_NUMBER / TO_CHAR with D, G
  → controls parsing/rendering numbers as text
  → does not alter NUMBER type or SQL numeric literal syntax

NLS_SORT = BINARY / BINARY_CI / BINARY_AI / linguistic
             ↓
  Collation / sorting rules
             │
             ▼
NLS_COMP = BINARY or LINGUISTIC
  → controls binary vs. linguistic comparisons in applicable scopes
  → does not override explicit/data-bound collations in newer releases
```

Three core principles:

1. **`NLS_NUMERIC_CHARACTERS` governs string-number conversion/formatting, not stored numeric values.** Pass numbers as typed numeric values across systems and convert explicitly at boundaries.
2. **`NLS_SORT` defines the collation rule; `NLS_COMP` determines whether linguistic comparison applies in eligible SQL predicates.** Never assume changing `NLS_SORT` alone changes `WHERE` behavior.
3. **Behavior depends on session context and column/expression collation.** In multilingual systems, keep display, search, and uniqueness separate; manage session NLS cleanly, test accented characters, and verify performance whenever collations change.

Mastering these three parameters explains regional number conversion errors, unexpected sort orders, and the critical boundary between "case-insensitive search" and "exact data equality" in Oracle Database.
