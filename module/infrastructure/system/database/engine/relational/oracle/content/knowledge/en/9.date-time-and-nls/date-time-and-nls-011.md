# Collation, Vietnamese String Comparison, and Choosing Search Rules

An application running on Oracle Database may store customer names such as `Hòa`, `Hoà`, `HÒA`, `Hoa`, `Đức`, and `Duc`. When a user types `hoa`, should the system return `Hòa`? When displaying a list, where should `Đạt` appear relative to `Dung`? If two accounts use login codes `Minh` and `minh`, should the database allow both?

These questions cannot be answered simply by picking `VARCHAR2` or choosing the `AL32UTF8` character set. They belong to **collation**: the rules Oracle uses to **compare**, **order**, and—in collation-aware operations—**determine which strings match one another**.

This lesson focuses on three goals:

1. Distinguish **binary comparison** from **linguistic comparison**, as well as **case sensitivity** from **accent sensitivity**.
2. Apply appropriate rules for **Vietnamese** using `NLS_SORT`, `NLS_COMP`, `COLLATE`, and `NLSSORT` in Oracle SQL.
3. Choose an explicit search contract for your application—**exact identifiers**, **case-insensitive lookup**, **accent-insensitive search**, **display sorting**, or **full-text search**—and assess the impact on unique constraints and indexes.

> **Version scope:** Examples use syntax available in Oracle Database 12.2 and later, including 19c and newer releases. Sections on column/table-level **data-bound collation** carry specific configuration prerequisites; query examples using `COLLATE` or `NLSSORT` do not require changing database-wide settings. Exact features, collation names, and comparison outcomes should always be verified on your target release and character set.

## 1. What does collation actually decide?

**Collation** defines how ordering and equivalence are interpreted for **character string values**. It affects character-comparison operations such as `ORDER BY`, `=` / `<` / `>`, `LIKE`, certain string-search functions, grouping, and key/constraint enforcement.

Consider two strings:

```text
Value A: 'Anh'
Value B: 'anh'
```

- Under **case-sensitive** rules, the two strings are not equal.
- Under **case-insensitive** rules, the two strings can be treated as equivalent in comparisons.
- Under **case- and accent-insensitive** rules, `Ánh`, `Anh`, and `anh` can fall into the same matching group, depending on the collation.

When two values are **equal under a collation**, that **does not mean the bytes stored in the database were rewritten to match**. Oracle preserves each value's exact stored spelling; only a given comparison evaluates equivalence under the active rule.

### 1.1. Binary collation

**`BINARY`** compares the raw binary representation of strings in the active character set. It is simple, deterministic, and generally well suited for system identifiers, yet it is **not** the Vietnamese alphabetical order human readers expect.

For example, `A`, `a`, and `Á` have distinct encodings; `BINARY` does not treat them as similar merely because they share a base letter. Binary sorting can also place accented characters in unnatural positions relative to a Vietnamese dictionary.

### 1.2. Linguistic collation

**Linguistic collation** uses language rules to define sort order and equivalence levels. Oracle provides **monolingual** collations (for a single language), **multilingual** collations, and collations based on the **Unicode Collation Algorithm (UCA)**.

Oracle includes **`VIETNAMESE`** in its list of monolingual linguistic collations. When sorting a list of Vietnamese names or words by language rules, it is a primary candidate to evaluate. For multilingual datasets, evaluate UCA or multilingual collations supported by your release.

**Important:** "standard Vietnamese sorting" is a business requirement that must be clarified. Tone mark ordering, vowels `a/ă/â`, letters `d/đ`, spaces, hyphens, family/middle names, and whether to sort by **given name** or **full name** all affect what users expect. Database collation executes a chosen rule; it does not automatically define every dictionary or domain convention.

## 2. Two axes: case and accents

| Mode | Distinguishes `A` and `a`? | Distinguishes `a` and `á`? | When to consider |
| --- | --- | --- | --- |
| **Case-sensitive, accent-sensitive** | Yes | Yes | Exact matching, identifiers, business codes |
| **Case-insensitive (CI), accent-sensitive** | No | Yes | Name lookup without requiring exact capitalization, while preserving diacritics |
| **Case-insensitive, accent-insensitive (AI)** | No | No, for accent differences ignored by the collation | Convenient search box for users typing without diacritics |

In Oracle collation names:

- **`_CI`** typically means **case-insensitive**: ignores case differences while **remaining accent-sensitive**.
- **`_AI`** means **accent-insensitive *and* case-insensitive**. Never describe `_AI` as "accent-insensitive only while remaining case-sensitive."
- Names without a suffix such as `VIETNAMESE` typically represent the case- and accent-sensitive variant per that collation's rules.

Common names:

| Collation | Characteristics | Notes |
| --- | --- | --- |
| `BINARY` | Binary comparison, case- and accent-sensitive | Suitable when strict identifier boundaries are required |
| `BINARY_CI` | Case-insensitive variant of binary collation | Does not automatically become Vietnamese dictionary order |
| `BINARY_AI` | Case- and accent-insensitive variant of binary collation | Does not guarantee matching every product's "unaccented Vietnamese" rules |
| `VIETNAMESE` | Vietnamese linguistic collation | Evaluate for display sorting following Vietnamese rules |
| `VIETNAMESE_CI` | Case-insensitive Vietnamese collation | Remains accent-sensitive per collation rules |
| `VIETNAMESE_AI` | Case- and accent-insensitive Vietnamese collation | Strong candidate for unaccented search; test with real data |

`VIETNAMESE`, `VIETNAMESE_CI`, and `VIETNAMESE_AI` follow Oracle's linguistic collation naming and suffix conventions. If an older environment does not recognize a collation name, check the supported list for **that release** rather than guessing alternative names.

### 2.1. For Vietnamese, "unaccented" can mean multiple things

Vietnamese has **tone marks** (acute, grave, hook above, tilde, dot below), vowel modifiers (**ă, â, ê, ô, ơ, ư**), and the letter **đ**. In a UI, "search without typing accents" can mean several distinct levels:

1. Typing `anh` matches `Anh` and `Ánh`.
2. Typing `hoa` matches `Hòa` or `Hoà` regardless of tone-placement spelling.
3. Typing `duong` matches `Dương`.
4. Should typing `duc` match `Đức`?
5. Should typos in accents/positions, extra spaces, or one-letter typos match?

The first three generally fall within **case/accent-insensitive matching** testable via collations. Specifically for `d` vs. `đ`, you must **verify** behavior under your chosen collation: `đ` is a distinct letter in the Vietnamese alphabet, so never assume from `_AI` alone that every product expectation around mapping `đ` to `d` is satisfied. Case 5 belongs to **input normalization** or **fuzzy/full-text search**, beyond merely changing `NLS_SORT`.

**Do not write an "accent-stripping" function with a short `REPLACE` chain and treat it as equivalent to Oracle collation.** Such functions easily miss uppercase variants, Unicode compositions, `đ/Đ`, combining marks, and other languages.

## 3. Character set, NLS, and collation are separate layers

In the *Date/Time and NLS* chapter, understand how collation sits alongside other NLS parameters without conflating them.

| Concept/parameter | What question does it answer? | Does it solve unaccented search by itself? |
| --- | --- | --- |
| **`NLS_CHARACTERSET`** | Which character encoding does the database use, e.g., `AL32UTF8`? | **No** |
| **`NLS_NCHAR_CHARACTERSET`** | Which character set do national character types use? | **No** |
| **`NLS_LANGUAGE`** | Default language for messages, day/month names, and related settings | Not directly a search policy |
| **`NLS_TERRITORY`** | Regional conventions, number/date formats, and related defaults | No |
| **`NLS_DATE_LANGUAGE`** | Language for weekday/month names in datetime conversions | No |
| **`NLS_SORT`** | Session collation/sort sequence when operations reference it | **Yes**, if the operation actually uses session collation |
| **`NLS_COMP`** | Enables comparisons to use session linguistic collation in legacy/pseudo-collation mode | **Possibly**, paired with `NLS_SORT` |
| **`COLLATE`** | Binds a collation to an expression or column to govern comparisons | **Yes**, with an appropriate collation |

**Using UTF-8 to store Vietnamese diacritics** and **choosing a collation to compare Vietnamese properly** are two separate tasks. A `VARCHAR2` column in an `AL32UTF8` database still uses `BINARY` case/diacritic-sensitive comparisons by default. Likewise, `NCHAR`/`NVARCHAR2` do not automatically sort in Vietnamese dictionary order.

### 3.1. Inspecting session and database settings

In SQLcl, SQL Developer, or another SQL client:

```sql
SELECT parameter, value
FROM nls_session_parameters
WHERE parameter IN (
    'NLS_SORT',
    'NLS_COMP',
    'NLS_LANGUAGE',
    'NLS_TERRITORY',
    'NLS_DATE_LANGUAGE'
)
ORDER BY parameter;

SELECT parameter, value
FROM nls_database_parameters
WHERE parameter IN (
    'NLS_CHARACTERSET',
    'NLS_NCHAR_CHARACTERSET'
)
ORDER BY parameter;
```

Or read session attributes directly:

```sql
SELECT
    SYS_CONTEXT('USERENV', 'LANGUAGE') AS language_context,
    SYS_CONTEXT('USERENV', 'NLS_SORT') AS nls_sort
FROM dual;
```

`NLS_SESSION_PARAMETERS` shows the active parameters for **the session executing the SQL**. Connections from a Java app, SQL Developer, and a DBA session can carry different NLS values despite hitting the same PDB and table. That is why a "works on my machine, fails on yours" bug can stem from session settings or differences in columns' **declared collations**.

### 3.2. Relationship between `NLS_SORT` and `NLS_COMP`

In the classic **session collation** model, think of it as:

```text
              NLS_SORT = VIETNAMESE_AI
                         |
           +-------------+---------------+
           |                             |
   ORDER BY using            WHERE name = :keyword
   session collation         if column uses USING_NLS_COMP
           |                             |
   Sorts according to        NLS_COMP = BINARY
   VIETNAMESE_AI             -> usually binary comparison
                                         |
                            NLS_COMP = LINGUISTIC
                            -> linguistic comparison
```

In Oracle 12.2+, **data-bound collation** also participates in determining the effective rule. If a column is declared with a named collation such as `BINARY_CI`, do not assume tweaking `NLS_COMP` changes that column's behavior. `USING_NLS_COMP` is a **pseudo-collation** preserving session-dependent behavior for backward compatibility.

**Practical takeaway:** before predicting results, inspect **the column/expression collation** *and* the session parameters whenever an expression uses a pseudo-collation.

## 4. SQL lab with Vietnamese names

The statements below belong in a **dedicated practice schema** using lab-only tables. Never run `CREATE`/`DROP` in a business schema. Your client and connection path should support Unicode, ideally against an `AL32UTF8` database.

### 4.1. Create a table without explicit column collations

```sql
CREATE TABLE vn_collation_lab (
    id        NUMBER PRIMARY KEY,
    full_name VARCHAR2(100 CHAR) NOT NULL,
    note      VARCHAR2(200 CHAR)
);

INSERT INTO vn_collation_lab VALUES (1,  'Anh',   'No accent, initial capital');
INSERT INTO vn_collation_lab VALUES (2,  'anh',   'Different case');
INSERT INTO vn_collation_lab VALUES (3,  'Ánh',   'Acute accent');
INSERT INTO vn_collation_lab VALUES (4,  'An',    'No accent');
INSERT INTO vn_collation_lab VALUES (5,  'Ân',    'Vowel Â');
INSERT INTO vn_collation_lab VALUES (6,  'Ăn',    'Vowel Ă');
INSERT INTO vn_collation_lab VALUES (7,  'Dung',  'Unaccented letter D');
INSERT INTO vn_collation_lab VALUES (8,  'Dũng',  'Tilde accent');
INSERT INTO vn_collation_lab VALUES (9,  'Đạt',   'Letter Đ');
INSERT INTO vn_collation_lab VALUES (10, 'Dat',   'Letter D');
INSERT INTO vn_collation_lab VALUES (11, 'Hoa',   'No accent');
INSERT INTO vn_collation_lab VALUES (12, 'Hòa',   'Grave accent');
INSERT INTO vn_collation_lab VALUES (13, 'Nam',   'No accent');
INSERT INTO vn_collation_lab VALUES (14, 'Năm',   'Vowel Ă');

COMMIT;
```

Explicit `COLLATE` clauses are omitted on columns in this lab table to clearly illustrate session behavior. However, **the schema or table default collation** may already be configured on a database with data-bound collations enabled; use the check in section 7 to verify your actual setup. To observe `NLS_COMP`/`NLS_SORT` most cleanly, run in a lab schema whose default is `USING_NLS_COMP`.

### 4.2. Compare binary vs. Vietnamese sort order

Instead of relying on current session NLS, apply **`COLLATE`** directly in `ORDER BY`:

```sql
-- Binary comparison.
SELECT id, full_name
FROM vn_collation_lab
ORDER BY full_name COLLATE BINARY, id;

-- Vietnamese linguistic collation comparison.
SELECT id, full_name
FROM vn_collation_lab
ORDER BY full_name COLLATE VIETNAMESE, id;
```

Record **the actual order of all 14 rows** in your environment; there is no need to memorize a raw Unicode code-point chart. Characters `a/ă/â`, `d/đ`, and tone marks make differences between binary order and linguistic order easy to observe. `VIETNAMESE` orders characters per Vietnamese linguistic rules, whereas `BINARY` is not designed for dictionary sorting.

**Why append `, id`?** If multiple strings tie under a collation, `ORDER BY full_name` alone does not guarantee deterministic ordering among tied rows. Appending a **unique** secondary key like `ID` makes pagination and repeated runs predictable.

### 4.3. Compare three matching levels

Search `anh` with exact matching:

```sql
SELECT id, full_name
FROM vn_collation_lab
WHERE full_name COLLATE BINARY = 'anh'
ORDER BY id;
```

This returns only binary-exact matches—row `anh`. Search case-insensitively while **preserving accents**:

```sql
SELECT id, full_name
FROM vn_collation_lab
WHERE full_name COLLATE VIETNAMESE_CI = 'anh'
ORDER BY id;
```

Both `Anh` and `anh` match; `Ánh` has a tone mark so it does not match under `_CI`. Search case-insensitively and **accent-insensitively per collation**:

```sql
SELECT id, full_name
FROM vn_collation_lab
WHERE full_name COLLATE VIETNAMESE_AI = 'anh'
ORDER BY id;
```

Under `VIETNAMESE_AI`, variants differing in accents or case such as `Ánh` also match `anh`. This fits a name search box allowing "unaccented typing." **Never use this query to replace identity verification or business keys**, because it intentionally collapses distinct strings into equality matches.

### 4.4. Verify `d` and `đ` behavior explicitly

Never guess solely from `_AI`. Run both independent checks:

```sql
SELECT
    CASE
        WHEN 'd' COLLATE VIETNAMESE_AI = 'đ'
        THEN 'EQUIVALENT'
        ELSE 'DISTINCT'
    END AS vietnamese_ai_result,
    CASE
        WHEN 'd' COLLATE BINARY_AI = 'đ'
        THEN 'EQUIVALENT'
        ELSE 'DISTINCT'
    END AS binary_ai_result
FROM dual;
```

Then compare against what product users expect when typing `Duc` to search for `Đức`. **Actual outputs from both collations** provide the evidence to decide; if business rules require a specific normalization/search rule beyond what the collation does, implement it transparently and test with real Vietnamese datasets.

## 5. Session NLS: changing comparison behavior without altering columns

To observe `NLS_COMP` and `NLS_SORT`, use a **dedicated lab session**; record the initial values from section 3.1 so you can restore them afterward.

### 5.1. `NLS_SORT` can affect `ORDER BY`

```sql
ALTER SESSION SET NLS_SORT = VIETNAMESE;

SELECT id, full_name
FROM vn_collation_lab
ORDER BY full_name, id;
```

On columns using the `USING_NLS_COMP` pseudo-collation, `ORDER BY` adopts linguistic order from `NLS_SORT`. However, if a column uses a **named collation** (such as `BINARY`), order follows the column's data-bound rule rather than session settings.

Thus, explicitly writing `COLLATE VIETNAMESE` is far more predictable when you do not want to rely on current session settings.

### 5.2. `NLS_COMP = BINARY` with equality

```sql
ALTER SESSION SET NLS_SORT = VIETNAMESE_AI;
ALTER SESSION SET NLS_COMP = BINARY;

SELECT id, full_name
FROM vn_collation_lab
WHERE full_name = 'anh'
ORDER BY id;
```

When the expression relies on `USING_NLS_COMP`, `WHERE full_name = 'anh'` still executes binary equality under `NLS_COMP=BINARY`, even though `NLS_SORT` is `VIETNAMESE_AI`. That is why **changing `NLS_SORT` alone does not make `WHERE =` accent-insensitive**.

### 5.3. `NLS_COMP = LINGUISTIC` with equality

```sql
ALTER SESSION SET NLS_COMP = LINGUISTIC;

SELECT id, full_name
FROM vn_collation_lab
WHERE full_name = 'anh'
ORDER BY id;
```

When the comparison relies on `USING_NLS_COMP`, `NLS_COMP=LINGUISTIC` enables `WHERE` to use `NLS_SORT=VIETNAMESE_AI`; results can then include variants like `Anh` and `Ánh`.

**Limitation to remember:** this model applies to **pseudo-collations** and classic session behavior. Results differ if the column/expression carries a **named data-bound collation**. From Oracle 12.2 onward, expression collation is resolved via derivation/determination rules before applying session NLS parameters.

### 5.4. Wrap up the lab session

Restore the `NLS_SORT` and `NLS_COMP` values you **recorded** earlier. For example, if your session originally used `BINARY` and `BINARY`:

```sql
ALTER SESSION SET NLS_SORT = BINARY;
ALTER SESSION SET NLS_COMP = BINARY;
```

In applications using **connection pools**, session state can be reused. If one request executes `ALTER SESSION SET NLS_COMP=LINGUISTIC` and returns the connection without resetting, later requests inherit altered comparison behavior. Configure sessions cleanly in the connection pool or specify `COLLATE` directly per query to keep search contracts explicit.

## 6. `COLLATE` for individual queries

From Oracle 12.2 onward, the **`COLLATE` operator** lets you attach a collation to a character expression inside a single SQL operation:

```sql
-- Sort display list per Vietnamese rules.
SELECT id, full_name
FROM vn_collation_lab
ORDER BY full_name COLLATE VIETNAMESE, id;

-- Exact search, case- and accent-sensitive.
SELECT id, full_name
FROM vn_collation_lab
WHERE full_name COLLATE BINARY = :exact_name;

-- Case-insensitive search, accent-sensitive.
SELECT id, full_name
FROM vn_collation_lab
WHERE full_name COLLATE VIETNAMESE_CI = :name;

-- Case- and accent-insensitive search per Vietnamese rules.
SELECT id, full_name
FROM vn_collation_lab
WHERE full_name COLLATE VIETNAMESE_AI = :name;
```

`:exact_name` and `:name` are **bind variables**. SQL Developer may prompt for values; in JDBC, pass them via `PreparedStatement.setString` rather than concatenating user input into SQL text.

**Advantage:** each query declares its own comparison policy, allowing two screens to enforce different rules:

- A **login code** lookup screen uses `BINARY`.
- A directory listing screen uses `VIETNAMESE` for sorting.
- An "unaccented name search" box uses `VIETNAMESE_AI`.

This avoids altering `NLS_COMP` across the entire session when only **one** predicate needs different semantics.

### 6.1. `LIKE` and prefix search

Example searching for names starting with `hoa` (using accent-insensitive collation):

```sql
SELECT id, full_name
FROM vn_collation_lab
WHERE full_name COLLATE VIETNAMESE_AI LIKE 'hoa%'
ORDER BY full_name COLLATE VIETNAMESE, id;
```

`LIKE` uses `%` to match any sequence and `_` to match a single character. When searching user input, if the user wants literal **`%` or `_` characters**, escape them before constructing the pattern:

```sql
-- Search for literal %; \ is declared as the escape character.
SELECT id, full_name
FROM vn_collation_lab
WHERE full_name COLLATE VIETNAMESE_AI LIKE '%\%%' ESCAPE '\';
```

In applications, **bind the entire pattern** after escaping special wildcard characters. An input string like `100%` does not mean the user intended a SQL wildcard.

**Prefix search and substring search differ in performance.** `LIKE 'hoa%'` can often leverage an appropriate index, whereas `LIKE '%hoa%'` generally cannot use a standard B-tree index range scan because of the leading wildcard. For large text corpora needing mid-string word search, evaluate a full-text search engine.

### 6.2. Do not equate accent-insensitive with fuzzy search

`VIETNAMESE_AI` may equate `Anh` and `Ánh` across accents, yet it does not fix typos or swapped letters, split full names, understand nicknames, or expand `Nguyễn Văn An` from arbitrary abbreviations.

| Desired behavior | Appropriate starting tool |
| --- | --- |
| `Anh` = `anh` | Case-insensitive collation |
| `Anh` ≈ `Ánh` | Accent-insensitive collation per chosen rules |
| Prefix `hoa...` | `LIKE 'hoa%'` + collation/bind + thoughtful indexing |
| Match any word inside long documents | Oracle Text or dedicated full-text search |
| Single-character typos or transpositions | Dedicated fuzzy search/ranking |
| Search by given name rather than family/middle name | Data modeling and name-splitting rules |
| Normalize whitespace and composed Unicode characters | Explicit input normalization policy |

## 7. Data-bound collation on columns and tables

Besides `COLLATE` in a query, Oracle supports declaring **data-bound collations** on columns, tables, and schemas in qualifying configurations. This has broader impact because column operations, indexes, and constraints can all depend on the declared collation.

### 7.1. Important prerequisites before running DDL

Per the Oracle Globalization Support Guide, declaring **data-bound collations** on database objects in supported releases requires:

- `COMPATIBLE >= 12.2`.
- `MAX_STRING_SIZE = EXTENDED`.

**These are not casual settings to toggle in a lab exercise.** Changing `MAX_STRING_SIZE` from `STANDARD` to `EXTENDED` is a database/PDB administrative upgrade procedure that cannot simply be reversed under Oracle rules; it requires a DBA and formal change control. **The expression-level `COLLATE` operator in SQL queries still works on supported releases even without enabling object-level data-bound collations.**

### 7.2. Column declaration example

Run this DDL only in a lab environment **already meeting data-bound collation prerequisites**:

```sql
CREATE TABLE vn_profile_collated (
    id           NUMBER PRIMARY KEY,
    login_code   VARCHAR2(60 CHAR) COLLATE BINARY NOT NULL,
    display_name VARCHAR2(100 CHAR) COLLATE VIETNAMESE_CI NOT NULL,
    search_name  VARCHAR2(100 CHAR) COLLATE VIETNAMESE_AI
);
```

Design intent:

- `LOGIN_CODE` has collation `BINARY`: exact character comparison, suitable when `ab` must differ from `AB`.
- `DISPLAY_NAME` has `VIETNAMESE_CI`: case-insensitive yet accent-sensitive in collation-sensitive operations.
- `SEARCH_NAME` has `VIETNAMESE_AI`: enables unaccented name lookup per Vietnamese rules.

This is a **mechanism illustration**, not a recommendation that every app store three columns or hardcode one collation across all person names. If a product serves multiple languages or screens needing diverse search modes, store clean source data and apply `COLLATE` per query.

### 7.3. Inspecting declared collations

```sql
SELECT table_name, column_name, data_type, collation
FROM user_tab_cols
WHERE table_name IN ('VN_COLLATION_LAB', 'VN_PROFILE_COLLATED')
  AND data_type IN ('CHAR', 'VARCHAR2', 'NCHAR', 'NVARCHAR2')
ORDER BY table_name, column_name;
```

Or within a query on a character column:

```sql
SELECT full_name, COLLATION(full_name) AS derived_collation
FROM vn_collation_lab
WHERE id = 1;
```

**`COLLATION(expression)`** reports the **derived data-bound collation** of the expression, not necessarily the **effective named collation used by the session** when the expression carries a pseudo-collation such as `USING_NLS_COMP` or `USING_NLS_SORT`. If it returns `USING_NLS_COMP`, you still need to check `NLS_COMP` and `NLS_SORT` to explain comparison behavior.

### 7.4. Constraints and indexes affected by collation

A column collation can govern how Oracle evaluates **unique constraints/unique indexes**, key equality, and key-dependent storage structures. Example in a lab supporting data-bound collations:

```sql
CREATE TABLE vn_account_ci (
    account_id NUMBER PRIMARY KEY,
    username   VARCHAR2(60 CHAR) COLLATE BINARY_CI
               NOT NULL UNIQUE
);
```

When a unique key uses a case-insensitive collation, `Minh` and `minh` collide as duplicates. That **fits** a system where usernames are case-insensitive, yet is **wrong** if business rules intentionally permit distinct accounts differing only in letter case.

Changing the collation of an existing column with data and constraints/indexes is a **data-semantics change**, not a UI tweak: values previously treated as distinct can suddenly conflict. For foreign keys, compatibility with the referenced key must also be checked. Never alter a production column's collation just to "fix search" without auditing duplicates and constraints.

## 8. `NLSSORT`: making comparison keys explicit

The **`NLSSORT`** function converts a character value into a `RAW` **collation key** whose binary order reflects the chosen collation rule.

```sql
SELECT
    id,
    full_name,
    RAWTOHEX(NLSSORT(full_name, 'NLS_SORT=VIETNAMESE')) AS sort_key_hex
FROM vn_collation_lab
ORDER BY NLSSORT(full_name, 'NLS_SORT=VIETNAMESE'), id;
```

`SORT_KEY_HEX` is for **technical inspection**, not a normalized text string to display to users. Never use `RAWTOHEX` output as an unaccented name or persist collation keys as permanent identifiers across database upgrades.

### 8.1. Comparing two strings under the same rule

```sql
SELECT
    CASE
        WHEN NLSSORT('Ánh', 'NLS_SORT=VIETNAMESE_AI')
           = NLSSORT('anh', 'NLS_SORT=VIETNAMESE_AI')
        THEN 'EQUIVALENT'
        ELSE 'DISTINCT'
    END AS vietnamese_ai_match
FROM dual;
```

You can substitute any candidate pairs, provided **both sides use the exact same collation**. Comparing a `BINARY` collation key against a `VIETNAMESE_AI` key is never a valid equivalence test.

### 8.2. `NLSSORT` for collation-exact equality predicates

```sql
SELECT id, full_name
FROM vn_collation_lab
WHERE NLSSORT(full_name, 'NLS_SORT=VIETNAMESE_AI')
    = NLSSORT(:search_name, 'NLS_SORT=VIETNAMESE_AI')
ORDER BY id;
```

This expresses a **function-based comparison**, useful when matching an `NLSSORT` expression index. On Oracle 12.2+, `WHERE full_name COLLATE VIETNAMESE_AI = :search_name` is usually clearer when you simply want to declare query semantics.

**Limitation:** `NLSSORT` produces a `RAW` collation key subject to length/size limits depending on release and `MAX_STRING_SIZE`. For very long strings, certain collations can truncate keys or raise errors like `ORA-12742` depending on configuration; never design critical identity checks around truncated keys. Consult Oracle documentation for your release's exact limits.

## 9. Indexes and collation search performance

Switching a predicate from binary to linguistic may force Oracle to compute collation keys or use a different index path. **There is no rule stating "having an index on the column makes every search mode fast."**

### 9.1. Standard indexes vs. comparison needs

```sql
CREATE INDEX ix_vn_name_binary
ON vn_collation_lab (full_name);
```

A standard index on the column accelerates lookups and `ORDER BY` matching the key's collation. If a query applies a **different linguistic collation**, the optimizer may have to evaluate `NLSSORT` and **cannot use the binary index as an equivalent range scan**.

On releases supporting named data-bound collations, Oracle can organize indexes on collated columns similarly to **function-based indexes on collation keys**. Always verify in the data dictionary and execution plan rather than assuming one rigid rule across all cases.

### 9.2. Function-based index for unaccented name search

On the lab table, you can create an expression index:

```sql
CREATE INDEX ix_vn_name_ai
ON vn_collation_lab (
    NLSSORT(full_name, 'NLS_SORT=VIETNAMESE_AI')
);
```

Matching query expression:

```sql
SELECT id, full_name
FROM vn_collation_lab
WHERE NLSSORT(full_name, 'NLS_SORT=VIETNAMESE_AI')
    = NLSSORT(:search_name, 'NLS_SORT=VIETNAMESE_AI')
ORDER BY id;
```

The optimizer **may** choose the function-based index depending on row count, selectivity, statistics, configuration, and cost estimates. On a 14-row lab table, a full table scan is completely reasonable. Never judge index effectiveness from timings on a handful of rows.

Real-world indexing considerations:

- Collation-key indexes consume extra storage and add `INSERT`/`UPDATE` maintenance cost.
- A collation key can be longer than the raw string; for wide columns, verify **maximum index key length** and `NLSSORT` length limits.
- The query expression and index expression must align for the optimizer to exploit the index.
- If session settings affect the expression, stabilize environment settings so plans stay predictable.
- With data-bound collations and system-generated key indexes, inspect the dictionary to avoid creating redundant duplicate indexes.

### 9.3. Inspect the execution plan—never guess

```sql
EXPLAIN PLAN FOR
SELECT id, full_name
FROM vn_collation_lab
WHERE NLSSORT(full_name, 'NLS_SORT=VIETNAMESE_AI')
    = NLSSORT('anh', 'NLS_SORT=VIETNAMESE_AI');

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
```

`EXPLAIN PLAN` shows an **estimated plan**; it does not prove what happened at runtime. For deep analysis, DBAs inspect **actual cursor plans**, row counts, and I/O with appropriate privileges. On tiny tables, Oracle skipping an index does not mean the index is "broken."

### 9.4. B-tree indexes do not replace full-text search

Prefix matching and **mid-text word matching** are completely different queries:

```sql
-- Prefix search: an appropriate index can be considered.
WHERE full_name COLLATE VIETNAMESE_AI LIKE 'hoa%'

-- Substring search: generally cannot use a simple B-tree range scan.
WHERE full_name COLLATE VIETNAMESE_AI LIKE '%hoa%'
```

For long documents, Vietnamese word segmentation, fuzzy matching, and relevance ranking, evaluate **Oracle Text** or a dedicated search service. Word tokenization, Vietnamese support, diacritics, and relevance scoring are features **of the lexer, index, and search configuration**, not something automatically gained by setting `NLS_SORT=VIETNAMESE_AI`.

## 10. Choosing comparison policies by data type and use case

| Data / scenario | Required search behavior | Recommended policy |
| --- | --- | --- |
| UUIDs, system codes, tokens, text checksums | Exact comparison, never merge variants | `BINARY`; consider binary storage where appropriate |
| Case-insensitive username | `Minh` = `minh` while diacritics remain significant if chosen | `BINARY_CI` or chosen CI collation; enforce via unique constraint |
| Full names in Vietnamese UI lists | Sort per linguistic rules | `ORDER BY full_name COLLATE VIETNAMESE` with tie-breaker |
| Search names forgiving capitalization errors | Do not merge differently accented names | `VIETNAMESE_CI` |
| Search box with "ignore accents" option | Ignore accents/case per agreed definition | Test `VIETNAMESE_AI` or `BINARY_AI` with a Vietnamese test suite |
| Place names like `Hòa Bình`, `Đà Nẵng` | Users may omit accents or vary spacing | AI collation **combined** with input normalization and custom rules where needed |
| Multilingual documents | Multilingual ordering and equivalence | Evaluate UCA/multilingual collations in your release |
| Word search across thousands of documents | Full-text, ranking, word segmentation | Oracle Text or dedicated search engine |
| Typo-tolerant name lookup | Spelling errors, missing letters, nicknames | Dedicated fuzzy search, not collation alone |
| Identity verification / foreign key joins | Never accidentally merge two legally distinct values | Technical keys and deliberate equality/unique rules |

### 10.1. Login codes and display names should not share one rule

Suppose a record has:

```text
account_id = 42
login_code = "minh.nd"
full_name  = "Nguyễn Đức Minh"
```

`LOGIN_CODE` is a **login identifier**; `FULL_NAME` is **display and search information**. You may want to:

- Enforce `LOGIN_CODE` with a strict, consistent uniqueness policy.
- Display `FULL_NAME` verbatim as entered by the user.
- Search `FULL_NAME` case- and accent-insensitively when requested.
- Sort `FULL_NAME` with Vietnamese collation.

Declaring `FULL_NAME COLLATE VIETNAMESE_AI UNIQUE` as a person identifier would wrongly reject distinct people whose names differ only by accents. **Forgiving search** and **uniqueness constraints** must be decided independently.

### 10.2. Put the choice in the right layer

```text
User types "hoa"
          |
          v
Application receives input + validates + normalizes UI whitespace/Unicode
          |
          v
SQL with bind parameter and explicit search collation
          |
          v
Oracle compares via collation, optionally using an index
          |
          v
Returns rows + sorts display list per policy
          |
          v
Application displays original stored names without overwriting them with "hoa"
```

If the product lets users toggle **"Accent-sensitive / Accent-insensitive"**, switch between **two pre-authored SQL statements** or expressions using the same safe bind variable. Never accept an arbitrary collation name from user input and concatenate it into SQL: `COLLATE` takes a SQL identifier keyword, **not a bindable data value**. Control choices strictly via an allowlist.

## 11. Unicode normalization and whitespace: collation does not solve everything

An accented character can exist as a **precomposed Unicode character** or as a **base character + combining mark (decomposed)**. For example, `ò` can be stored as a single code point or as `o` followed by a combining grave accent.

In some linguistic/UCA collations, canonically equivalent Unicode sequences match properly, yet **never assume every binary comparison or every collation behaves identically**. When building Vietnamese name search:

1. Standardize on a normalization form (commonly **NFC**) consistently at data ingestion and indexing boundaries if required.
2. Preserve original user-entered text for display or auditing when required; never strip diacritics from source columns.
3. Define rules for repeated spaces, trailing spaces, punctuation, hyphens, and multi-word names.
4. Test with real Unicode fixtures including `ă/â/ê/ô/ơ/ư/đ`, uppercase variants, tone-mark placements, and **combining mark** sequences.
5. If maintaining an application-normalized search column/key, manage updates and index rebuilds whenever normalization logic changes.

Oracle also treats trailing spaces differently between `CHAR` and `VARCHAR2`, and Oracle SQL treats empty strings `''` as `NULL`. Therefore, "two strings look identical in the UI" does not guarantee every type or comparison treats them as equal.

### Example creating combining marks to inspect

Oracle can construct decomposed Unicode sequences using `UNISTR`. Example:

```sql
SELECT
    DUMP('ò', 1016)                         AS precomposed_dump,
    DUMP('o' || UNISTR('\0300'), 1016)      AS decomposed_dump
FROM dual;
```

Both render identically on screen yet have different code-point sequences. Compare them under `BINARY`, `VIETNAMESE`, and a UCA collation supported by your release, and record the results. That shows the **practical limits** of a chosen rule.

## 12. Common implementation mistakes

| Claim / symptom | Why it can be wrong | Resolution |
| --- | --- | --- |
| "The database uses `AL32UTF8`, so unaccented search already works." | Character set governs encoding, not matching rules | Choose an appropriate collation or search method |
| "Setting `NLS_SORT=VIETNAMESE_AI` makes every `WHERE =` accent-insensitive." | Under `USING_NLS_COMP`, `NLS_COMP=BINARY` still performs binary equality | Check `NLS_COMP`/declared collation or use explicit `COLLATE` |
| "`_CI` also strips accents." | `CI` ignores only case | Use `AI` when accent-insensitivity is required |
| "`_AI` strips accents while remaining case-sensitive." | Oracle `_AI` is also case-insensitive | Design custom rules if you truly need that combination |
| "`BINARY_AI` definitely sorts names in Vietnamese alphabetical order." | Binary AI and Vietnamese linguistic sorting have different goals | Evaluate `VIETNAMESE`/`VIETNAMESE_AI` for your use case |
| "`Đ` definitely equals `D` in every AI collation." | Individual letter rules cannot be inferred solely from the suffix | Test `d/đ` against product fixtures |
| "Changing `NLS_LANGUAGE` to Vietnamese is enough." | `NLS_LANGUAGE` is not a full equality/sorting contract per expression | Use explicit `COLLATE` or controlled NLS settings |
| "Changing session NLS in one request won't affect others." | Connection pools reuse sessions | Reset sessions or use explicit `COLLATE` per query |
| "An index on `FULL_NAME` will definitely be used for `VIETNAMESE_AI`." | Linguistic comparisons may require collation-key/expression indexes | Inspect the execution plan and index alignment |
| "`LIKE '%hoa%'` will be fast with a B-tree index." | Leading wildcards normally prevent standard range scans | Consider full-text or specialized search indexes |
| "`LOWER(name)` handles all Vietnamese casing and accents." | Case folding does not perform accent normalization or linguistic collation | Choose appropriate collations and language APIs |
| "Changing collation does not affect unique keys." | Previously distinct values can collide as equivalent | Audit duplicate data, constraints, and indexes before migrating |
| "`COLLATION(column)` always shows the active `NLS_SORT`." | It shows derived collation; pseudo-collations still depend on session settings | Query both `USER_TAB_COLS.COLLATION` and session NLS |
| "Accent-insensitive search will fix typos or match synonyms." | Collation compares characters, not semantic or fuzzy similarity | Build a dedicated search layer if required |

## 13. Practice exercises with guided answers

### Exercise 1 — Compare sort orders

After creating `VN_COLLATION_LAB`:

1. Run `ORDER BY FULL_NAME COLLATE BINARY, ID`.
2. Run `ORDER BY FULL_NAME COLLATE VIETNAMESE, ID`.
3. Run `ORDER BY FULL_NAME COLLATE VIETNAMESE_AI, ID`.
4. Record the positions of `An`, `Ân`, `Ăn`, `Dung`, `Dũng`, `Dat`, and `Đạt`.
5. Explain why an AI collation can form **equivalence groups** and why `ID` is a helpful tie-breaker.

**Guided answer:** all three queries read the same underlying data and differ only in sort rules. When names tie under AI, you cannot rely on stable ordering without a unique tie-breaker column.

### Exercise 2 — Compare equality across three levels

Write three queries finding `anh` using `BINARY`, `VIETNAMESE_CI`, and `VIETNAMESE_AI`. Then answer:

- Why do `Anh` and `anh` match under CI but not under BINARY?
- Why does `Ánh` match under AI but not under CI?
- If a system has one person named `Anh` and another named `Ánh`, should an AI collation decide they are the same person?

**Guided answer:** CI folds case differences, while AI folds accent differences per policy as well; matching for search **is never proof that two records represent the same person**.

### Exercise 3 — Verify `d/đ` behavior

Run the query from section 4.4 and record `VIETNAMESE_AI_RESULT` and `BINARY_AI_RESULT` in your environment. Add tests with `Duc` vs. `Đức` and `Da Nang` vs. `Đà Nẵng`.

**Guided answer:** before promising "unaccented search" UX, build a test suite covering `đ`, tone marks, and modified vowels. If collation behavior does not match product policy, add a tested secondary mechanism rather than mutating source data.

### Exercise 4 — Session NLS vs. named collation

1. Query `NLS_SESSION_PARAMETERS`.
2. Set `NLS_SORT=VIETNAMESE_AI` and `NLS_COMP=BINARY` in your lab session.
3. Run `WHERE FULL_NAME='anh'`.
4. Change `NLS_COMP=LINGUISTIC` and run again.
5. Run a query using `FULL_NAME COLLATE BINARY = 'anh'`.
6. Restore original NLS settings.

**Guided answer:** on `USING_NLS_COMP` columns, `NLS_COMP` controls whether equality uses session `NLS_SORT`. Explicit `COLLATE BINARY` fixes predicate semantics independently of session linguistic settings.

### Exercise 5 — Choosing policies by business rules

A CRM has three fields:

```text
CUSTOMER_ID  NUMBER         -- surrogate technical key
LOGIN_CODE   VARCHAR2(60)   -- user login identifier
FULL_NAME    VARCHAR2(150)  -- display name
```

Design:

1. Equality and uniqueness policy for `LOGIN_CODE`.
2. How to display sorted `FULL_NAME` lists in Vietnamese.
3. A name search box offering "Accent-sensitive" and "Accent-insensitive" modes.
4. Indexing strategy for frequent queries given 5 million customers.
5. Test dataset covering `Anh`, `Ánh`, `Đức`, `Duc`, `Hòa`, `Hoa`, and decomposed Unicode characters.

**Guided answer:** use the technical key for identity, define explicit login uniqueness, use linguistic collation for display sorting, selective CI/AI for search, and validate indexes against realistic workloads. Never place an accent-insensitive unique constraint across full names.

### Exercise 6 — Distinguish prefix vs. full-text search

Write one SQL query matching names starting with `hoa` and another matching `hoa` in the middle of a name. Explain the difference in B-tree index range scan eligibility. When searching many pages of Vietnamese text, propose an Oracle Text approach and what lexer/index behaviors must be tested.

### Clean up the lab

Run only in your practice schema after completing all exercises:

```sql
DROP TABLE vn_collation_lab PURGE;

-- Drop only if you created them in an environment
-- with data-bound collations enabled.
DROP TABLE vn_profile_collated PURGE;
DROP TABLE vn_account_ci PURGE;
```

If you did not create the two optional tables because data-bound collations were not enabled, **do not run those two DROP statements**. `PURGE` bypasses the recycle bin; never use it on tables that might need recovery.

## 14. Summary of practical application

When handling Vietnamese text in Oracle, separate four decisions:

1. **Preserve original data:** Unicode character set and proper encoding from client to database.
2. **Sort for human readers:** evaluate `VIETNAMESE` linguistic collation and include a tie-breaker in `ORDER BY`.
3. **Search as expected:** use case-insensitive (`_CI`) or case-and-accent-insensitive (`_AI`) selectively, testing Vietnamese cases like `ă/â/ơ/ư/đ` and Unicode normalization.
4. **Protect data integrity:** design PKs, unique constraints, FKs, and indexes intentionally; never use permissive search rules to determine identity or legal uniqueness.

Technically, `NLS_SORT`/`NLS_COMP` govern operations using session collation; `COLLATE` gives individual SQL expressions explicit policies; `NLSSORT` exposes collation keys and supports expression indexes; and data-bound collations push rules onto columns/tables subject to configuration prerequisites and constraint/index impact. These are tools for enforcing **predefined business decisions**.

## Oracle reference documentation

- [Oracle Database Globalization Support Guide — Linguistic Sorting and Matching (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/nlspg/linguistic-sorting-and-matching.html) — binary, monolingual, UCA, case/accent sensitivity, data-bound collation, linguistic indexes.
- [Oracle Database Globalization Support Guide — Locale Data (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/nlspg/appendix-A-locale-data.html) — list of linguistic collations, including `VIETNAMESE`.
- [Oracle Database Globalization Support Guide — SQL and PL/SQL Programming in a Global Environment (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/nlspg/sql-and-plsql-programming-in-global-environment.html) — effects of `NLS_COMP`/`NLS_SORT`, `ORDER BY`, and comparison predicates.
- [Oracle Database SQL Language Reference — COLLATION (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/COLLATION.html) — derived collation of expressions.
- [Oracle Database SQL Language Reference — NLSSORT (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/NLSSORT.html) — collation keys, `NLS_SORT` parameter, and limits.
- [Oracle Database SQL Language Reference — CREATE TABLE (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/CREATE-TABLE.html) — column `COLLATE`, default collation, and `MAX_STRING_SIZE=EXTENDED` prerequisite.
- [Oracle Database Reference — ALL_TAB_COLS (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/ALL_TAB_COLS.html) — inspecting column `COLLATION` metadata.

All equivalence examples—especially involving **`đ/Đ`, Vietnamese diacritics, and Unicode variants**—must be verified on your exact Oracle release, character set, and product policy before applying them to production search or unique constraints.
