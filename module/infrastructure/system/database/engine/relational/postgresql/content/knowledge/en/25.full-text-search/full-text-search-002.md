# LIKE, ILIKE, Regular Expressions, and Performance Limits in PostgreSQL

## 1. From Prefix Search to Queries Scanning Millions of Rows

Suppose an application has a documents table containing titles, bodies, and slugs:

```sql
SELECT document_id, title
FROM documents
WHERE title LIKE 'PostgreSQL%';
```

This is a **prefix** search: the title starts with `PostgreSQL`. With an appropriate B-tree index, PostgreSQL can bound the range of the index it must read. However, when changed to:

```sql
SELECT document_id, title
FROM documents
WHERE title ILIKE '%postgresql%';
```

the problem changes completely:

- `ILIKE` matches **case-insensitively** according to the relevant locale/collation rules.
- The leading `%` allows the target text to appear at **any position**.
- A standard B-tree index struggles to narrow the index range for a "string contained somewhere" predicate.
- On a large table, a `Seq Scan` may have to inspect a huge number of rows.

With regular expressions:

```sql
SELECT document_id, title
FROM documents
WHERE title ~* '^(PostgreSQL|Java).*index';
```

we must also account for pattern complexity, prefix/trigram extraction capability, statistics, CPU usage, and the risks of letting users supply arbitrary regexes.

**This lesson does not just teach syntax.** The goal is to choose the right matching operator, keep queries safe, and understand **when and how PostgreSQL can use an index**.

```text
User enters query
         |
         +--> Only know starting string? ----> LIKE 'prefix%'
         |
         +--> Match at any position? --------> LIKE '%term%'
         |
         +--> Case-insensitive? -------------> ILIKE / lower(...)
         |
         +--> Need character rules? ---------> POSIX regex ~ / ~*
         |
         +--> Need large text search? -------> pg_trgm / Full Text Search
         |
         +--> All require EXPLAIN, real data, and cost limits
```

> **Core principle:** matching expressive power and index usability are two related yet distinct decisions. A query that returns "correct results" can still be unsuitable to run over millions of rows on every request.

## 2. Learning Objectives

After this lesson, you will be able to:

1. Explain the `%` and `_` wildcards in `LIKE` / `ILIKE`.
2. Write prefix, suffix, contains, exact full-string, and ordered multi-segment patterns.
3. Escape `%`, `_`, and the escape character when **users want to search for them as literal text**.
4. Distinguish `LIKE`, `ILIKE`, `SIMILAR TO`, and POSIX regex operators `~`, `~*`, `!~`, `!~*`.
5. Write regexes with anchors, character classes, quantifiers, grouping, and alternation.
6. Use `regexp_match`, `regexp_matches`, `regexp_replace`, and `regexp_split_to_array` with the right semantics.
7. Understand NULLs, locale/collation, Unicode, and the difference between case-insensitivity and accent-insensitivity.
8. Explain why B-tree indexes usually fit `LIKE 'prefix%'` better than `LIKE '%term%'`.
9. Use `text_pattern_ops` and `lower(...)` expression indexes for suitable prefix searches.
10. Understand the `pg_trgm` extension along with GIN/GiST trigram indexes for substring, ILIKE, and regex queries.
11. Recognize overly short patterns, patterns without extractable trigrams, and recheck overhead.
12. Read `EXPLAIN (ANALYZE, BUFFERS)` for `Seq Scan`, `Index Scan`, and `Bitmap Heap Scan`.
13. Write safe Java/JDBC `PreparedStatement` code without confusing **SQL injection** with **pattern injection**.
14. Decide when to switch to PostgreSQL Full Text Search.
15. Design query limits, pagination, timeouts, and benchmarks on representative data.

## 3. Quick Comparison Table of Pattern-Matching Tools

| Mechanism | Common Target | Case-Sensitive | Example |
| --- | --- | --- | --- |
| `LIKE` | Simple wildcards | Usually yes, per collation | `title LIKE 'PostgreSQL%'` |
| `ILIKE` | Simple case-insensitive wildcards | No, per relevant locale | `title ILIKE '%postgresql%'` |
| `NOT LIKE` | Negated LIKE | Same as LIKE | `title NOT LIKE 'tmp%'` |
| `NOT ILIKE` | Negated ILIKE | Same as ILIKE | `title NOT ILIKE '%draft%'` |
| `SIMILAR TO` | SQL-style pattern combining LIKE and regex | Depends on semantics/collation | `title SIMILAR TO '(Java|SQL)%'` |
| `~` | POSIX regular expression | Case-sensitive | `title ~ '^PostgreSQL'` |
| `~*` | Case-insensitive POSIX regex | Case-insensitive | `title ~* 'postgresql'` |
| `!~` | Negated case-sensitive regex | Case-sensitive | `title !~ '[[:digit:]]'` |
| `!~*` | Negated case-insensitive regex | Case-insensitive | `title !~* 'draft'` |
| `pg_trgm` | Trigram-based indexing and similarity checks | Per operator | GIN/GiST index with `gin_trgm_ops` |
| Full Text Search | Word/lexeme search and search syntax | Per text-search configuration | `to_tsvector(...) @@ plainto_tsquery(...)` |

Some mechanisms have restrictions when using **nondeterministic collations**, and support details can vary across PostgreSQL versions. Do not equate `ILIKE` with accent-insensitive collation or natural-language search.

## 4. Creating a Lab Schema with Enough Data to Measure

The commands in this lesson should be run on a **test database**. Loading data and creating GIN indexes carry significant cost; never copy directly to production.

### 4.1. Create the schema and table

```sql
CREATE SCHEMA IF NOT EXISTS text_search_lab;

CREATE TABLE text_search_lab.documents (
    document_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    title text NOT NULL,
    slug text NOT NULL,
    body text NOT NULL,
    category text NOT NULL,
    created_at timestamptz NOT NULL,
    archived boolean NOT NULL DEFAULT false
);
```

`document_id` has a B-tree index from `PRIMARY KEY`, but that index **does not automatically help search strings inside `title`/`body`**.

### 4.2. Load 120,000 documents

```sql
INSERT INTO text_search_lab.documents
    (title, slug, body, category, created_at, archived)
SELECT
    CASE
        WHEN g % 100 = 0
            THEN 'PostgreSQL performance guide ' || g
        WHEN g % 17 = 0
            THEN 'Java indexing patterns ' || g
        WHEN g % 29 = 0
            THEN 'Café and Unicode notes ' || g
        ELSE
            'Database tutorial ' || g
    END AS title,
    'doc_' || lpad(g::text, 6, '0') AS slug,
    repeat('storage and query planning example. ', 3)
        || CASE
             WHEN g % 31 = 0
               THEN 'Search tuning with pg_trgm and index scans. '
             WHEN g % 37 = 0
               THEN 'Regular expression exercises and metadata. '
             ELSE 'General database foundations. '
           END
        || g::text AS body,
    CASE WHEN g % 10 = 0 THEN 'advanced'
         ELSE 'beginner'
    END AS category,
    timestamptz '2025-01-01 00:00:00+00'
       + g * interval '1 minute' AS created_at,
    (g % 19 = 0) AS archived
FROM generate_series(1, 120000) AS s(g);
```

Note: `CASE` picks the **first matching branch**; a row divisible by both 100 and 17 gets the PostgreSQL title, not Java.

### 4.3. Gather statistics and inspect the data

```sql
ANALYZE text_search_lab.documents;

SELECT
    COUNT(*) AS total,
    COUNT(*) FILTER (
        WHERE title LIKE 'PostgreSQL%'
    ) AS postgresql_prefix,
    COUNT(*) FILTER (
        WHERE title LIKE 'Java%'
    ) AS java_prefix,
    COUNT(*) FILTER (
        WHERE body LIKE '%pg_trgm%'
    ) AS trigram_mentions,
    COUNT(*) FILTER (
        WHERE archived
    ) AS archived_documents
FROM text_search_lab.documents;
```

The ratios in the dataset are relatively deterministic, while the chosen **plan** still depends on version, indexes, cache, planner settings, and hardware.

### 4.4. Run EXPLAIN before creating string-search indexes

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT document_id, title
FROM text_search_lab.documents
WHERE title LIKE 'PostgreSQL%';
```

Without an index on `title`, you will likely see a `Seq Scan`. Still, plans vary by environment. Record actual rows, buffers, and Execution Time as a baseline.

Do not use `COUNT(*)` as a complete substitute benchmark for a query returning `body` or multiple columns: changing the projection can change the access path.

## 5. LIKE: Syntax and Whole-String Matching Rules

Syntax:

```sql
expression LIKE pattern [ESCAPE escape_character]
```

Two important wildcards:

- `%` matches **zero, one, or more characters**.
- `_` matches **exactly one character** in the string per PostgreSQL's character semantics.

Unlike POSIX regex, `LIKE` matches the **entire string**. Even when a pattern has `%` at the start/end, "searching in the middle" comes from those wildcards rather than default regex-style substring matching.

### 5.1. Short examples

```sql
SELECT
    'PostgreSQL 18' LIKE 'PostgreSQL%' AS prefix_match,
    'PostgreSQL 18' LIKE '%SQL%' AS contains_sql,
    'AB7' LIKE 'AB_' AS one_character,
    'AB77' LIKE 'AB_' AS too_many_characters,
    'PostgreSQL' LIKE 'SQL' AS not_full_match;
```

Meaning:

| Pattern | Result |
| --- | --- |
| `'PostgreSQL 18' LIKE 'PostgreSQL%'` | true |
| `'PostgreSQL 18' LIKE '%SQL%'` | true |
| `'AB7' LIKE 'AB_'` | true |
| `'AB77' LIKE 'AB_'` | false |
| `'PostgreSQL' LIKE 'SQL'` | false |

### 5.2. Prefix search

```sql
SELECT document_id, title
FROM text_search_lab.documents
WHERE title LIKE 'PostgreSQL%';
```

Finds titles **starting** with `PostgreSQL`.

### 5.3. Suffix search

```sql
SELECT document_id, slug
FROM text_search_lab.documents
WHERE slug LIKE '%001';
```

Finds slugs **ending** with `001`. A standard B-tree struggles to narrow a range for a pattern starting with `%`.

### 5.4. Substring search

```sql
SELECT document_id, title
FROM text_search_lab.documents
WHERE title LIKE '%indexing%';
```

Finds `indexing` at any position in `title`.

### 5.5. Ordered segments

```sql
SELECT
    'PostgreSQL query optimizer' LIKE
    'PostgreSQL%optimizer' AS matched;
```

`%` represents the middle part, while the other text segments must still appear in the specified order.

### 5.6. Exact full-string matching

```sql
SELECT 'Java' LIKE 'Java' AS exact_text;
```

Without wildcards, `LIKE` matches the pattern verbatim. In ordinary equality queries, prefer:

```sql
WHERE title = $1
```

when the business logic truly wants equality matching, because its semantics are clearer and it can more straightforwardly use equality indexes.

## 6. The Underscore in LIKE Has Special Meaning

A very common mistake:

```sql
WHERE slug LIKE 'doc_0001%'
```

Here `_` is **not a literal underscore character**; it matches any single character.

That condition can also match `docX0001...` if the rest of the string matches.

### 6.1. Escaping underscore with a chosen character

```sql
SELECT
    'doc_000123' LIKE 'doc!_000%' ESCAPE '!' AS literal_underscore,
    'docX000123' LIKE 'doc!_000%' ESCAPE '!' AS reject_other_character;
```

The `!` character is designated as the **escape character**. Thus:

- `!_` means a literal underscore.
- `!%` means a literal percent sign.
- `!!` means a literal `!`.

### 6.2. Example escaping percent

```sql
SELECT
    '50% discount' LIKE '50!%%' ESCAPE '!' AS literal_percent,
    '500 discount' LIKE '50!%%' ESCAPE '!' AS not_same;
```

The pattern `50!%%` consists of `50`, a literal percent (`!%`), and a `%` wildcard.

### 6.3. Escaping the escape character itself

```sql
SELECT
    'hello!world' LIKE 'hello!!world' ESCAPE '!' AS matched;
```

Choosing an explicit escape character avoids confusion across multiple backslash-escaping layers in SQL literals, Java strings, and regexes.

### 6.4. Default backslash and standard_conforming_strings

In PostgreSQL, `\` is commonly used as the default LIKE escape character. At the same time, SQL string literals have backslash rules governed by `standard_conforming_strings` and `E'...'` syntax.

Because **two escaping layers** can exist, in this lesson and in applications we prefer:

```sql
LIKE $1 ESCAPE '!'
```

when escaping literal wildcards. Do not manually chain multiple `\` characters without verifying every SQL/regex/application layer.

## 7. LIKE, NULL, and Negation Operators

Like other SQL comparisons, if either operand is `NULL`, the match result is normally `NULL`, not false.

```sql
SELECT
    NULL::text LIKE 'a%' AS null_input,
    'abc' LIKE NULL::text AS null_pattern,
    NOT ('abc' LIKE NULL::text) AS null_negation;
```

All three expressions evaluate to NULL.

### 7.1. NOT LIKE does not automatically keep NULL rows

```sql
WHERE title NOT LIKE 'tmp%'
```

does not automatically include rows where `title IS NULL`. If business rules want to include NULLs:

```sql
WHERE title NOT LIKE 'tmp%'
   OR title IS NULL
```

In the lab `title NOT NULL` holds, but this rule is crucial in real-world tables.

### 7.2. `LIKE '%'` does not match NULL

```sql
SELECT
    'anything' LIKE '%' AS any_nonnull,
    NULL::text LIKE '%' AS null_is_not_true;
```

`LIKE '%'` evaluates to true for every **non-NULL** string, including empty strings, but yields NULL for NULL input.

### 7.3. Empty string differs from NULL

```sql
SELECT
    '' LIKE '%' AS empty_matches_percent,
    '' LIKE '_' AS empty_does_not_match_underscore,
    '' LIKE '' AS empty_matches_empty;
```

Do not use a LIKE check in place of application rules distinguishing missing, empty string, and null.

## 8. ILIKE: Case-Insensitive but Does Not Strip Diacritics

PostgreSQL provides `ILIKE` for LIKE-style wildcard matching without case sensitivity according to the relevant locale/collation rules.

```sql
SELECT
    'PostgreSQL' ILIKE 'postgresql' AS same_ignoring_case,
    'Java INDEX' ILIKE '%index%' AS contains_ignoring_case,
    'PostgreSQL' LIKE 'postgresql' AS like_can_differ;
```

### 8.1. On the documents table

```sql
SELECT document_id, title
FROM text_search_lab.documents
WHERE title ILIKE '%POSTGRESQL%';
```

This condition can match `PostgreSQL ...` titles even though the pattern is uppercase.

### 8.2. ILIKE is not accent-insensitive search

`ILIKE '%cafe%'` is **not guaranteed** to match `Café` when diacritics differ. Case sensitivity differs from diacritic sensitivity, Unicode normalization, and language-specific comparison rules.

If a product requires `cafe` to match `Café`, you must design an appropriate normalization/collation/search strategy and test multilingual data.

### 8.3. Unicode and visible characters

A single user-perceived character can consist of multiple code points (e.g., combining diacritics). Therefore, the `_` wildcard and regex character classes do not necessarily correspond to **one visible grapheme** as humans see it in the UI.

Do not build username-length validation using "a pattern of exactly N underscores" if business logic needs to count grapheme clusters.

### 8.4. ILIKE in a query without an index

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT document_id, title
FROM text_search_lab.documents
WHERE title ILIKE 'postgresql%';
```

With only a regular B-tree on `title`, PostgreSQL usually cannot leverage that B-tree for a case-insensitive prefix as straightforwardly as `LIKE 'PostgreSQL%'`.

Two solutions to know:

1. An expression index on `lower(title)` for **prefix patterns** using the matching expression.
2. A `pg_trgm` trigram index for flexible `ILIKE`/substring/pattern queries.

## 9. POSIX Regular Expressions: Fundamentally Different from LIKE

PostgreSQL provides regular expression operators:

| Operator | Meaning |
| --- | --- |
| `~` | Regex match, case-sensitive |
| `~*` | Regex match, case-insensitive |
| `!~` | Regex does not match, case-sensitive |
| `!~*` | Regex does not match, case-insensitive |

Key point: regex operators usually look for a **matching substring**, rather than implicitly requiring the entire string to match like LIKE.

```sql
SELECT
    'PostgreSQL indexing' ~ 'SQL' AS substring_regex,
    'PostgreSQL indexing' ~ '^SQL' AS not_at_start,
    'PostgreSQL indexing' ~ 'indexing$' AS at_end,
    'PostgreSQL indexing' ~* 'postgresql' AS ignore_case;
```

### 9.1. Start-of-string anchor: `^`

```sql
SELECT 'Java indexing' ~ '^Java' AS starts_java;
```

### 9.2. End-of-string anchor: `$`

```sql
SELECT 'guide.sql' ~ '\.sql$' AS ends_sql;
```

`\.` means a **literal dot**, because an unescaped `.` in regex normally matches any single character per regex semantics.

### 9.3. Enforcing the entire string: `^...$`

```sql
SELECT
    'AB-1234' ~ '^[A-Z]{2}-[0-9]{4}$' AS valid_code,
    'prefix AB-1234 suffix' ~ '^[A-Z]{2}-[0-9]{4}$' AS invalid_full;
```

Use anchors when validation requires the whole string rather than just a substring match.

### 9.4. Do not confuse regex `.*` with LIKE `%`

| Meaning | LIKE | Regex |
| --- | --- | --- |
| Any sequence of characters | `%` | `.*` |
| Any single character | `_` | `.` |
| Start of string | Implicitly full-string; prefix pattern needs no anchor | `^` |
| End of string | Implicitly full-string; suffix pattern needs no anchor | `$` |
| A digit | No character class | `[0-9]` or `[[:digit:]]` |
| "abc" at any position | `'%abc%'` | `'abc'` |

**Do not use regex syntax inside LIKE:** `LIKE 'A.*B'` looks for a literal dot and asterisk, not "A followed by anything followed by B".

## 10. Regex Character Classes and Quantifiers

### 10.1. Character classes

```sql
SELECT
    'user007' ~ '[[:digit:]]' AS contains_digit,
    'A7' ~ '^[A-Z][0-9]$' AS uppercase_and_digit,
    'B' ~ '^[A-Z]$' AS one_uppercase,
    'B' ~ '^[^0-9]+$' AS no_digits;
```

Common POSIX classes:

| Class | General Meaning |
| --- | --- |
| `[[:digit:]]` | Digit |
| `[[:alpha:]]` | Letter per locale/regex rules |
| `[[:alnum:]]` | Letter or digit |
| `[[:space:]]` | Whitespace character |
| `[[:lower:]]` | Lowercase letter |
| `[[:upper:]]` | Uppercase letter |

The Unicode and locale scope of character classes must be verified in your real environment if used for identity or language validation.

### 10.2. Quantifiers

| Quantifier | Meaning |
| --- | --- |
| `*` | 0 or more times |
| `+` | 1 or more times |
| `?` | 0 or 1 time |
| `{n}` | Exactly n times |
| `{n,}` | At least n times |
| `{n,m}` | From n to m times |

Examples:

```sql
SELECT
    'abc' ~ '^a.*c$' AS any_between,
    'abbbc' ~ '^ab+c$' AS one_or_more_b,
    'ac' ~ '^ab?c$' AS optional_b,
    'AB-1234' ~ '^[A-Z]{2}-[0-9]{4}$' AS code_format;
```

### 10.3. Alternation and grouping

```sql
SELECT
    'PostgreSQL guide' ~ '^(PostgreSQL|Java)' AS starts_supported,
    'Python guide' ~ '^(PostgreSQL|Java)' AS not_supported;
```

The `|` inside a regex is **OR inside the pattern**, distinct from the boolean `OR` operator between two SQL predicates.

### 10.4. Word boundaries

PostgreSQL supports escapes defining word boundaries in regex (per appropriate engine/locale), such as `\m` at the start of a word and `\M` at the end of a word:

```sql
SELECT
    'learn PostgreSQL today' ~ '\mPostgreSQL\M'
        AS whole_word_found,
    'learn PostgreSQLish today' ~ '\mPostgreSQL\M'
        AS not_whole_word;
```

Do not assume these word boundaries understand all segmentation rules of Vietnamese or languages that do not rely purely on whitespace.

### 10.5. Practicing on the dataset

```sql
SELECT document_id, title
FROM text_search_lab.documents
WHERE title ~ '^(PostgreSQL|Java)'
ORDER BY document_id
LIMIT 20;
```

A regex with a clear literal prefix/alternation can help the planner and `pg_trgm` extract candidate conditions, though there is no guarantee every alternation will use an index efficiently.

## 11. Things Regex Does Not Do Like a Natural Language Tool

Regex is strong at **character pattern recognition**, not at understanding:

- Synonyms (database ↔ cơ sở dữ liệu).
- Word stems and morphological variants.
- Typos and relevance ranking.
- Linguistic Vietnamese word segmentation.
- Unicode normalization across multi-source data.
- Edit distance (*edit distance*) aligned with desired UX.

If a user types "hướng dẫn postgres index" and wants documents containing those related words in any position, PostgreSQL Full Text Search may fit better than a chain of `ILIKE '%...%'` conditions, though language support still needs evaluation.

## 12. Regex in SQL Strings: Two Layers of Escaping

There can be two layers:

1. **SQL string literal** parsing the string passed to the regex engine.
2. **Regex engine** interpreting characters like `.`, `*`, `+`, `\`, and anchors.

Example:

```sql
SELECT 'report.sql' ~ '\.sql$' AS match_extension;
```

With `standard_conforming_strings = on`, backslashes in standard SQL string literals are preserved verbatim so the regex engine receives `\.`.

If using escape string syntax `E'...'`, you must escape the backslash at the SQL layer:

```sql
SELECT 'report.sql' ~ E'\\.sql$' AS match_extension;
```

### 12.1. Checking the setting

```sql
SHOW standard_conforming_strings;
```

In applications, **bind regex patterns** via parameters when needed rather than manually concatenating SQL strings and backslashes.

### 12.2. Do not confuse with Java string escaping

In Java source code:

```java
String pattern = "\\.sql$";
```

the Java runtime string value is `\.sql$`, which is passed to PostgreSQL's regex engine via a bind parameter.

If you write the Java literal `"\.sql$"`, it is not valid Java string syntax because `\.` is not a valid Java escape sequence.

### 12.3. Literal text vs regex patterns

If a user enters a dot `.` intending to match a literal period, passing that raw value to a regex operator will match many other characters.

Parameterization protects SQL structure, but **does not automatically turn regex metacharacters into literals**. You need proper validation/quoting or LIKE with literal escaping.

## 13. Commonly Used Regex Functions

PostgreSQL includes a family of functions for extracting matches, replacing, and splitting strings. Newer functions vary by version; the examples below focus on widely available ones.

### 13.1. `regexp_match`: first match as an array

```sql
SELECT regexp_match(
    'Order AB-1234 received',
    '([A-Z]{2})-([0-9]{4})'
) AS captured_groups;
```

The `text[]` result contains captured groups, e.g., `{AB,1234}`. If the pattern does not match, the result is normally NULL.

If the regex has capture groups, the array holds those groups; if there are no capture groups, it can hold the entire match.

### 13.2. Extracting a specific group

```sql
SELECT
    (regexp_match(
        'Order AB-1234 received',
        '([A-Z]{2})-([0-9]{4})'
    ))[1] AS prefix,
    (regexp_match(
        'Order AB-1234 received',
        '([A-Z]{2})-([0-9]{4})'
    ))[2] AS number_part;
```

In real queries, avoid calling the same expensive regex multiple times if you can compute it once in a subquery/`LATERAL`.

### 13.3. `regexp_matches`: set-returning function

```sql
SELECT m.parts
FROM regexp_matches(
    'A-12 B-34 C-56',
    '([A-Z])-([0-9]+)',
    'g'
) AS m(parts);
```

The `g` flag means **global**: return multiple matches. Because this is a **set-returning function**, if there is no match it may emit zero rows—an important difference from `regexp_match`, which returns NULL.

### 13.4. Regex matches per row

```sql
SELECT
    d.document_id,
    m.parts[1] AS first_number
FROM text_search_lab.documents AS d
CROSS JOIN LATERAL regexp_matches(
    d.title,
    '([0-9]+)',
    'g'
) AS m(parts)
WHERE d.document_id <= 10
ORDER BY d.document_id;
```

`LATERAL` lets each row run the function on its own `title`. One document can produce multiple rows if the pattern matches multiple times.

### 13.5. `regexp_replace`

```sql
SELECT regexp_replace(
    'Invoice AB-1234 / CD-9999',
    '[0-9]+',
    '[NUMBER]',
    'g'
) AS redacted;
```

This replaces every sequence of digits with `[NUMBER]`. Do not mistake "demo redaction with regex" for a verified sensitive-data scrubbing pipeline; an expression can miss real-world formats.

### 13.6. `regexp_split_to_array`

```sql
SELECT regexp_split_to_array(
    'java,postgresql; index ;query',
    '[,;][[:space:]]*'
) AS keywords;
```

Splits on commas/semicolons and optional whitespace matching the pattern.

### 13.7. Version-dependent advanced functions

Some PostgreSQL versions add `regexp_count`, `regexp_instr`, `regexp_like`, `regexp_substr`, and extended signatures.

Before using them in production code, verify the exact version/syntax against documentation or the running database. In this lesson, `~` operators and `regexp_match(es)`, `regexp_replace`, `regexp_split_to_array` cover the fundamentals.

## 14. SIMILAR TO: Hybrid SQL Regex Syntax, Not POSIX Regex

`SIMILAR TO` combines LIKE-style `%` and `_` wildcards with certain regex constructs.

```sql
SELECT
    'PostgreSQL indexing' SIMILAR TO '(PostgreSQL|Java)%'
        AS one_of_two_prefixes,
    'Python indexing' SIMILAR TO '(PostgreSQL|Java)%'
        AS not_supported;
```

**Unlike `~`**, `SIMILAR TO` requires the pattern to match the **entire string**.

### 14.1. Key points to remember

- `%` and `_` still retain their SQL pattern meanings.
- `|` and `()` provide alternation/grouping.
- Do not casually substitute `%` with `.*` as in POSIX regex.
- Optimization capabilities and nondeterministic collation support differ from LIKE/regex depending on version.

### 14.2. Which tool should you use?

| Requirement | Prefer considering |
| --- | --- |
| Starts with a literal prefix | `LIKE 'prefix%'` |
| Contains a literal string | `LIKE '%term%'` or trigram |
| Case-insensitive wildcards | `ILIKE` / normalizing expression |
| Complex pattern with classes/quantifiers | `~` / `~*` |
| SQL-style pattern semantics with alternation | `SIMILAR TO` if genuinely needed |
| Text keyword search | Full Text Search |

Using `LIKE` or POSIX regex is usually easier to explain than forcing every case into `SIMILAR TO`.

## 15. Why Can LIKE Be Fast or Very Slow?

Consider three queries:

```sql
-- A. Match the entire value:
SELECT document_id
FROM text_search_lab.documents
WHERE title = 'Java indexing patterns 17';

-- B. Match a prefix:
SELECT document_id
FROM text_search_lab.documents
WHERE title LIKE 'Java indexing%';

-- C. Contains substring at any position:
SELECT document_id
FROM text_search_lab.documents
WHERE title LIKE '%indexing%';
```

Standard B-tree usability is not the same across them:

1. Equality usually has a clear index path.
2. A literal prefix can be turned into an **index range** when the operator class/collation supports it.
3. A leading `%` wildcard removes information about "where the value starts", so a B-tree cannot easily locate a contiguous key range to read.

### 15.1. Do not equate "has an index" with "query will use the index"

The PostgreSQL planner compares costs:

- Sequential scan of the full heap.
- Reading index + heap for matching rows.
- Bitmap scan via the index.
- Sorting, LIMIT, cache, and row width factors.

For very small tables or patterns matching 90% of rows, `Seq Scan` can be reasonable even when an index supports the predicate.

### 15.2. Selectivity matters

`LIKE 'PostgreSQL%'` may match 1% of rows in the lab.

`LIKE 'Database%'` matches most rows.

Both have a prefix, yet the optimal execution plan is not necessarily the same.

### 15.3. Rows returned and rows scanned are different

```sql
SELECT COUNT(*)
FROM text_search_lab.documents
WHERE body ILIKE '%database%';
```

The query returns only **one count** to the client, yet the executor still has to locate/inspect the rows needed to count them.

Do not conclude "the query returns one row so it must be fast".

## 16. B-tree Index for Prefix LIKE

Create a B-tree index:

```sql
CREATE INDEX documents_title_btree_idx
ON text_search_lab.documents (title);

ANALYZE text_search_lab.documents;
```

In some collations, the planner can use a regular B-tree for:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT document_id, title
FROM text_search_lab.documents
WHERE title LIKE 'PostgreSQL%';
```

However, in non-C locales, the default operator class may **not support prefix LIKE optimization the way you expect**.

### 16.1. `text_pattern_ops`

For a `text` column:

```sql
CREATE INDEX documents_title_prefix_idx
ON text_search_lab.documents (title text_pattern_ops);
```

`text_pattern_ops` is a B-tree operator class supporting pattern comparisons suitable for prefix searches in collations where the default index is unsuitable.

Corresponding operator classes also exist for `varchar`/`char` where appropriate.

### 16.2. How to use it

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT document_id, title
FROM text_search_lab.documents
WHERE title LIKE 'PostgreSQL%';
```

An illustrative plan might look like:

```text
Index Scan using documents_title_prefix_idx on documents
  Index Cond: (
    (title ~>=~ 'PostgreSQL'::text)
    AND (title ~<~ 'PostgreSQM'::text)
  )
  Filter: (title ~~ 'PostgreSQL%'::text)
```

The internal operators and upper bound in the example only **illustrate the prefix range mechanism**; the exact operator names/bound values are generated by the planner and may differ. Read actual plans on your machine rather than copying this text structure as SQL.

### 16.3. Not every regex/pattern uses text_pattern_ops

For example:

```sql
WHERE title LIKE '%PostgreSQL'
```

has a leading wildcard, so a B-tree index cannot derive a useful prefix range from the trailing `PostgreSQL`.

Similarly, an expression with multiple wildcards may only exploit the **first literal prefix segment**, then filter the rest.

### 16.4. Index type must match the column

If `title` is `varchar`, consider the matching operator class. Do not arbitrarily cast data to `text` and create redundant indexes.

### 16.5. Pattern indexes do not replace collation-based comparison indexes

`text_pattern_ops` is designed for pattern comparisons; it does not necessarily serve locale-ordered ranges/`ORDER BY` like the default B-tree operator class.

If the workload has both locale-based `ORDER BY title` and `LIKE 'prefix%'`, evaluate different index definitions and total write cost.

## 17. Expression Index on lower(title) for Case-Insensitive Prefixes

One way to replace `ILIKE 'postgresql%'` with an expression predicate is:

```sql
WHERE lower(title) LIKE 'postgresql%'
```

Create the expression index:

```sql
CREATE INDEX documents_lower_title_prefix_idx
ON text_search_lab.documents
    ((lower(title)) text_pattern_ops);
```

Test it:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT document_id, title
FROM text_search_lab.documents
WHERE lower(title) LIKE 'postgresql%';
```

The planner can use the index on the **exact expression** `lower(title)`.

### 17.1. Why isn't an index on title enough?

An index on:

```sql
(title text_pattern_ops)
```

is not equivalent to an index on:

```sql
(lower(title) text_pattern_ops)
```

because `lower(title)` is a different expression from the raw column.

### 17.2. When the user supplies a prefix

Keep parameter binding:

```sql
PREPARE title_prefix(text) AS
SELECT document_id, title
FROM text_search_lab.documents
WHERE lower(title) LIKE $1;
```

In the application, bind a normalized value such as `postgresql%`. If you need to ensure a custom plan leverages the parameter's prefix, compare `EXPLAIN` for custom vs generic plans using `plan_cache_mode` and real indexes.

### 17.3. Why can a generic plan affect index selection?

A generic prepared plan for:

```sql
WHERE lower(title) LIKE $1
```

is not optimized using a per-execution literal prefix the way a custom plan is. If the planner cannot deduce a fixed prefix to bound the index range at plan time, it may choose a different access path.

Do not conclude that "creating an expression index guarantees generic plans will use it for every pattern".

### 17.4. Case normalization is not accent normalization

`lower('Café')` changes letter case per applicable rules, but does not automatically convert `é` into `e` in every configuration.

If accent-insensitive search is required, you must define a compatible normalization/collation and index strategy. The `unaccent` extension can help in some systems, though using it directly in an expression index requires understanding volatility/`IMMUTABLE` assumptions and dictionary configuration; never copy an arbitrary `IMMUTABLE` wrapper into production.

### 17.5. Do not create multiple indexes serving the same purpose

In the lab we create several indexes for comparison. In production, evaluate effectiveness and write cost before keeping them all.

## 18. Leading Wildcards: Why B-tree Is Not Enough

These two patterns:

```sql
WHERE title LIKE 'PostgreSQL%'
WHERE title LIKE '%PostgreSQL%'
```

differ in the input information available to a B-tree.

### 18.1. A prefix forms a range

Strings starting with `PostgreSQL` sit next to each other in a suitable lexicographical order. A B-tree can bound the candidate range.

### 18.2. Contains has no single simple key range

Strings containing `PostgreSQL` could start with:

```text
A PostgreSQL guide
Best PostgreSQL book
Learn PostgreSQL
PostgreSQL guide
Why PostgreSQL?
```

The keys do not reside in a single prefix range. A normal B-tree may have to inspect nearly every key/row.

### 18.3. Suffixes are similar

```sql
WHERE title LIKE '%guide'
```

knows only the ending, not the beginning.

If a suffix query is critical, a specialized strategy can use an **expression index on the reversed string** and query a prefix on the reversed string; however, you must align expressions, collation, Unicode semantics, and workload. Do not assume it is universally better than trigrams.

### 18.4. Testing substring LIKE

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT document_id, title
FROM text_search_lab.documents
WHERE title ILIKE '%indexing%';
```

Before creating a trigram index, `Seq Scan` can be a reasonable access path because a prefix B-tree index does not directly serve a leading wildcard.

## 19. `pg_trgm`: Index for Substring, ILIKE, and Regex

PostgreSQL includes the `pg_trgm` extension, providing similarity operations and operator classes for **trigram indexing**.

A **trigram** is a group of three consecutive characters produced by the extension's normalization/tokenization mechanism. The index stores information about trigrams in text, helping find **candidate rows** likely to match a pattern.

### 19.1. Enable the extension in the lab database

```sql
CREATE EXTENSION IF NOT EXISTS pg_trgm;
```

This requires the extension to be available on the server and sufficient privileges. On managed PostgreSQL, allowed extensions and installation privileges may be restricted.

### 19.2. Create a GIN trigram index on title

```sql
CREATE INDEX documents_title_trgm_idx
ON text_search_lab.documents
USING gin (title gin_trgm_ops);
```

When the extension/operator class is installed in a schema reachable via `search_path`, this definition works directly. If the extension lives in another schema, qualify the operator class appropriately.

### 19.3. Substring LIKE can use the trigram index

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT document_id, title
FROM text_search_lab.documents
WHERE title LIKE '%indexing%';
```

An illustrative plan:

```text
Bitmap Heap Scan on documents
  Recheck Cond: (title ~~ '%indexing%'::text)
  Heap Blocks: exact=...
  -> Bitmap Index Scan on documents_title_trgm_idx
       Index Cond: (title ~~ '%indexing%'::text)
```

Notes:

- This is an **illustrative plan**, not a guarantee the planner always picks it.
- `pg_trgm` identifies candidate rows from trigrams and must then verify the actual LIKE condition.
- `Recheck Cond` is an important detail when reading bitmap scans.

### 19.4. ILIKE can also be supported

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT document_id, title
FROM text_search_lab.documents
WHERE title ILIKE '%POSTGRESQL%';
```

A trigram index can be useful for case-insensitive contains searches.

### 19.5. Regex on title

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT document_id, title
FROM text_search_lab.documents
WHERE title ~* 'postgreSQL.*guide';
```

For regexes from which useful literal trigrams can be extracted, `pg_trgm` can also help locate candidates. Not every regex is index-friendly.

### 19.6. The extension is not a "regex engine" replacing the executor

The index filters candidates; PostgreSQL still has to apply full LIKE/ILIKE/regex semantics, especially for complex wildcards/alternations.

Do not conclude that a candidate returned by the index is **already verified as a match** without rechecking.

## 20. GIN and GiST Trigram Indexes: How They Differ

`pg_trgm` supports both GIN and GiST operator classes.

### 20.1. GIN

```sql
CREATE INDEX documents_title_trgm_idx
ON text_search_lab.documents
USING gin (title gin_trgm_ops);
```

GIN is often considered for trigram text filtering queries, such as LIKE/ILIKE with sufficiently long literal segments.

### 20.2. GiST

```sql
CREATE INDEX documents_title_trgm_gist_idx
ON text_search_lab.documents
USING gist (title gist_trgm_ops);
```

GiST has characteristics suited to similarity/distance ordering in addition to pattern matching in supported cases.

### 20.3. Practical choice

| Aspect | GIN trigram | GiST trigram |
| --- | --- | --- |
| Contains/ILIKE/regex filtering | Can be strong | Can be strong |
| How trigrams are stored | GIN-style inverted index | Signature/representation per GiST opclass |
| Recheck/false positives | Depends on pattern/index path | Can incur more rechecks depending on signature |
| Similarity nearest-neighbor order | Lacks GiST's KNN index-ordering capability | Useful for KNN with suitable distance operator |
| Storage/write cost | Depends on data, pending list, and workload | Depends on signature length and workload |
| Is one "always fastest"? | No | No |

Do not create **both indexes** on the same column in production without measuring, as both increase storage and write amplification.

### 20.4. GIN pending list and write workload

GIN indexes have a configurable pending-entries mechanism that can affect INSERT speed and cleanup timing. On continuously updated tables, monitor write latency, autovacuum, and index size.

Choose GIN/GiST based on read/write ratio, pattern shapes, ranking requirements, and benchmarks.

## 21. Trigrams Are Not Effective for Every Pattern

A key limitation is that **useful trigrams must be extractable** from the pattern.

### 21.1. Patterns that are too short

```sql
SELECT document_id, title
FROM text_search_lab.documents
WHERE title ILIKE '%ab%';
```

The literal `ab` has only two characters. This may not provide a sufficiently selective trigram set for the index.

### 21.2. Overly broad regexes

```sql
WHERE title ~ '.*'
```

matches almost all non-NULL values under regex semantics and yields no useful candidate filter. A trigram index cannot make a non-selective pattern fast.

### 21.3. Special characters breaking up literal runs

Example:

```sql
WHERE title LIKE '%a%b%c%'
```

has multiple wildcards and very short literal runs. The index may have to scan large numbers of candidate entries or lack useful trigrams.

### 21.4. Trigram rechecks and false positives

A trigram index finds candidate rows that might satisfy a pattern; merely containing the trigrams does not prove full order, position, case, or regex constraints.

The executor still needs to evaluate the actual condition using the operator.

### 21.5. When no trigrams can be extracted

When a pattern yields no extractable trigrams, using a trigram index can degenerate into **scanning many or all index entries**, resulting in worse performance than expected.

Never promise "a GIN trigram index speeds up every `ILIKE '%...%'`".

### 21.6. Check selectivity

Even with a long literal, if it appears in 95% of rows, reading most of the table sequentially can still be cheaper than index-driven heap lookups.

Index usefulness depends on both **literal length** and **actual frequency**.

## 22. Trigram Indexes on Body: Cost and Limits

`body` is usually much longer than `title`. A GIN trigram index on `body` can become very large.

### 22.1. Test separately in the lab

```sql
CREATE INDEX documents_body_trgm_idx
ON text_search_lab.documents
USING gin (body gin_trgm_ops);

ANALYZE text_search_lab.documents;
```

### 22.2. Querying a technical term

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT document_id, title
FROM text_search_lab.documents
WHERE body ILIKE '%pg_trgm%';
```

**Note:** `_` in LIKE is a wildcard. To match the literal string `pg_trgm`:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT document_id, title
FROM text_search_lab.documents
WHERE body ILIKE '%pg!_trgm%' ESCAPE '!';
```

### 22.3. Why is indexing body expensive?

- Each row can contain very many trigrams.
- The GIN index holds many entries/postings.
- INSERT/UPDATE on `body` must maintain the index.
- Building/reindexing can consume heavy I/O, CPU, WAL, and disk.
- Queries matching common terms remain non-selective.

### 22.4. Do not index every text column

Examine which queries users actually execute:

- Search title only?
- Search slug/identifier?
- Search body?
- Multi-word/phrase search?
- Full-text search with ranking?

Design indexes for the workload. An FTS index on `body` plus a trigram index on `title` is often better balanced than GIN trigrams on every column.

## 23. Comparison with PostgreSQL Full Text Search

Full Text Search (FTS) is designed for **word/lexeme search**, unlike substring matching.

### 23.1. Example on body

```sql
SELECT document_id, title
FROM text_search_lab.documents
WHERE to_tsvector('simple', body)
      @@ plainto_tsquery('simple', 'query planning')
LIMIT 20;
```

`'simple'` is a basic text-search configuration; it does not mean PostgreSQL provides complete stemming/word segmentation for every language.

### 23.2. FTS index

```sql
CREATE INDEX documents_body_fts_idx
ON text_search_lab.documents
USING gin (to_tsvector('simple', body));
```

### 23.3. FTS vs trigram

| Need | LIKE/ILIKE + trigram | FTS |
| --- | --- | --- |
| Substring at any position | Usually suitable | Not the direct target |
| Single keyword by lexeme | Possible | Suitable |
| Multiple words with logic operators | Regex/LIKE gets messy | Dedicated `tsquery` syntax |
| Relevance ranking | Trigram similarity | `ts_rank`/`ts_rank_cd` per config |
| Word prefix | LIKE prefix | Lexeme prefix queries where supported |
| Typo/fuzzy matching | `pg_trgm` similarity helps | Standard FTS is not fuzzy edit-distance |
| Vietnamese and complex segmentation | Needs normalization handling | Needs suitable tokenizer/config; not built-in |

### 23.4. Do not expect FTS to find every substring

For example, a user searching `gres` inside `PostgreSQL`: lexeme-based FTS will not necessarily find this substring; trigrams fit better if the product wants contains/fuzzy matching.

### 23.5. Avoid uncontrolled chains of multi-word ILIKE conditions

```sql
WHERE body ILIKE '%postgresql%'
  AND body ILIKE '%index%'
  AND body ILIKE '%plan%'
```

This may match literal substrings, but lacks word-tokenization and ranking semantics like a search engine. For multi-word search, consider FTS so the query is modeled cleanly.

## 24. Case, Accents, Unicode, and Collation

### 24.1. Collation affects string comparison

Case-insensitive matching outcomes and B-tree pattern optimization depend on locale/collation and version.

PostgreSQL supports different collation types, including **nondeterministic collations** that ignore certain distinctions. However, **support for pattern operators under nondeterministic collations is not uniform across LIKE, ILIKE, and regex** and can vary by version.

Therefore, for multilingual applications, test the exact:

- PostgreSQL version.
- Database/column/expression collation.
- Accented strings, case, combining marks.
- Query plans and index matching.

### 24.2. Do not equate ILIKE with "accent-insensitive"

`Café` can differ from `Cafe` even under case-insensitive matching. If UX requires accent-insensitive search, intentional normalization is needed.

### 24.3. Unicode normalization

Two visually identical strings can have different Unicode representations (precomposed vs combining code points). LIKE/regex is not an automatic Unicode normalization step tailored to application rules.

Standardize storage normalization and test data from multiple sources.

### 24.4. Regex character classes and locale

`[[:alpha:]]` and word-boundary detection follow engine/locale rules, not a complete multilingual linguistic parser.

If validating technical codes that must be ASCII, write an explicit pattern:

```sql
SELECT 'AB-1234' ~ '^[A-Z]{2}-[0-9]{4}$';
```

If validating names, addresses, or multilingual text, never carelessly restrict to `[A-Za-z]+` and assume it is valid for all users.

### 24.5. Testing a Vietnamese example

```sql
SELECT
    'Cơ sở dữ liệu' ILIKE '%dữ liệu%' AS case_insensitive,
    'Cơ sở dữ liệu' ILIKE '%du lieu%' AS no_automatic_unaccent;
```

Results depend on collation/version in certain setups, so do not treat this example as an immutable guarantee across every deployment. The key point is that **accent-insensitive** search requirements must be explicitly defined and tested.

## 25. EXPLAIN for LIKE/ILIKE/Regex

The most important tool:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT document_id, title
FROM text_search_lab.documents
WHERE title ILIKE '%indexing%';
```

### 25.1. Seq Scan

When no suitable index exists or the pattern matches too many rows:

```text
Seq Scan on documents
  Filter: (title ~~* '%indexing%'::text)
  Rows Removed by Filter: ...
  Buffers: shared hit=... read=...
```

`~~*` is how PostgreSQL may display the `ILIKE` operator in plan text.

### 25.2. B-tree prefix Index Scan

With a suitable prefix index:

```text
Index Scan using documents_title_prefix_idx on documents
  Index Cond: (...)
  Filter: (title ~~ 'PostgreSQL%'::text)
```

The index finds a range of candidate keys, and a full LIKE Filter may still be needed.

### 25.3. Bitmap Heap Scan from a trigram index

```text
Bitmap Heap Scan on documents
  Recheck Cond: (title ~~* '%indexing%'::text)
  Heap Blocks: exact=...
  -> Bitmap Index Scan on documents_title_trgm_idx
       Index Cond: (title ~~* '%indexing%'::text)
```

`Bitmap Index Scan` locates candidate positions; `Bitmap Heap Scan` reads the heap and verifies the predicate.

### 25.4. Does Recheck mean a bad index?

No. Recheck is a normal part of bitmap/index access path semantics. However, if `Rows Removed by Index Recheck` is very high or heap blocks are lossy, investigate selectivity, `work_mem`, and index type.

### 25.5. Key metrics

| EXPLAIN Field | Question |
| --- | --- |
| `cost` | How did the planner estimate cost? |
| `rows` | Estimated row count? |
| `actual rows` | Actual row count? |
| `Rows Removed by Filter` | How many rows were filtered out after scanning? |
| `Index Cond` | Which condition actually drove the index lookup? |
| `Recheck Cond` | Which predicate needed re-verification? |
| `Heap Blocks: exact/lossy` | Did the bitmap lose exactness? |
| `Buffers: shared hit/read` | Which blocks came from shared buffers vs needed reading? |
| `Planning Time` | Time spent planning? |
| `Execution Time` | Time spent executing? |
| `loops` | How many times did the node execute? |

### 25.6. Cost is not milliseconds

`cost=0.00..3000.00` is an estimated cost unit, not "3 seconds".

### 25.7. Buffers do not equal physical disk reads

`shared hit` means blocks already in shared buffers. `shared read` means blocks read into shared buffers, which may still be served from the OS filesystem cache. Measure multiple runs under documented cache/load conditions.

### 25.8. EXPLAIN ANALYZE actually executes the query

For SELECT, it executes without having to transmit all result rows to the application like a normal SELECT. For DML:

```sql
EXPLAIN (ANALYZE, BUFFERS)
UPDATE ...
```

will actually UPDATE data. Never run DML `EXPLAIN ANALYZE` carelessly on production; in the lab, use transactions/`ROLLBACK` and understand any remaining side effects.

## 26. Selectivity, Statistics, and Pattern Parameters

PostgreSQL uses statistics to estimate how many rows may match a predicate.

```sql
SELECT
    attname,
    null_frac,
    n_distinct,
    most_common_vals,
    most_common_freqs,
    histogram_bounds,
    correlation
FROM pg_stats
WHERE schemaname = 'text_search_lab'
  AND tablename = 'documents'
  AND attname IN ('title', 'category', 'slug')
ORDER BY attname;
```

### 26.1. Prefix estimates differ from substring estimates

A prefix `'PostgreSQL%'` allows the planner to estimate using string distribution and index range under suitable conditions.

Patterns like `'%sql%'` or complex regexes are harder to estimate because they depend on internal character positions and combinations.

### 26.2. Prepared statements and generic plans

```sql
PREPARE search_title(text) AS
SELECT document_id, title
FROM text_search_lab.documents
WHERE title LIKE $1;
```

You can run:

```sql
BEGIN;
SET LOCAL plan_cache_mode = force_custom_plan;

EXPLAIN (ANALYZE, BUFFERS)
EXECUTE search_title('PostgreSQL%');

EXPLAIN (ANALYZE, BUFFERS)
EXECUTE search_title('%sql%');

ROLLBACK;
```

With a custom plan, the planner sees the concrete pattern to estimate prefix vs contains.

### 26.3. Comparing with generic

```sql
BEGIN;
SET LOCAL plan_cache_mode = force_generic_plan;

EXPLAIN (ANALYZE, BUFFERS)
EXECUTE search_title('PostgreSQL%');

EXPLAIN (ANALYZE, BUFFERS)
EXECUTE search_title('%sql%');

ROLLBACK;
```

A generic plan must work for any value of `$1`, and cannot assume every pattern has a long prefix. Consequently, its plan shape can differ from a custom plan.

```sql
DEALLOCATE search_title;
```

### 26.4. Do not drop parameter binding to force custom plans

Bind parameters must still be used to keep SQL structure safe. If generic plans actually cause regressions, evaluate narrowly scoped `plan_cache_mode`, pre-declared query variants, or suitable indexes instead of concatenating user patterns into SQL text.

### 26.5. ANALYZE is not a silver bullet

```sql
ANALYZE text_search_lab.documents;
```

updates statistics, but does not build trigrams, change operators, or turn `LIKE '%abc%'` into a B-tree prefix query.

## 27. SQL Injection and Pattern Injection Are Two Different Issues

Suppose a user enters the string:

```text
50%_off
```

The application wants to search for the **literal** `50%_off` in `title`.

### 27.1. Bind parameters only protect SQL syntax

Good example:

```sql
SELECT document_id, title
FROM text_search_lab.documents
WHERE title LIKE $1 ESCAPE '!';
```

If the client binds `%50%_off%` **without escaping wildcards**, the user has accidentally or intentionally crafted a broader pattern than the literal text.

That is not SQL injection, but it can be **pattern injection** or broken search semantics.

### 27.2. Escaping in the right order

When choosing `!` as the escape character:

1. Replace `!` with `!!`.
2. Replace `%` with `!%`.
3. Replace `_` with `!_`.
4. Only then add the `%` wildcards intentionally used by the app for contains search.

### 27.3. Java example

```java
static String escapeLikeLiteral(String input) {
    return input
        .replace("!", "!!")
        .replace("%", "!%")
        .replace("_", "!_");
}
```

Usage:

```java
String literal = escapeLikeLiteral(userText);
String pattern = "%" + literal + "%";

try (var ps = connection.prepareStatement(
        "SELECT document_id, title " +
        "FROM text_search_lab.documents " +
        "WHERE title LIKE ? ESCAPE '!' " +
        "ORDER BY document_id LIMIT 100")) {
    ps.setString(1, pattern);
    try (var rs = ps.executeQuery()) {
        while (rs.next()) {
            System.out.println(rs.getLong("document_id")
                + ": " + rs.getString("title"));
        }
    }
}
```

This approach:

- Keeps SQL syntax separate from user input.
- Handles wildcard escaping for literal substring semantics.
- Uses `LIMIT` to cap returned rows.
- Is not an absolute CPU cap if the pattern is too broad or no index helps.

### 27.4. Prefix search in Java

If the product wants "starts with literal input":

```java
String pattern = escapeLikeLiteral(userText) + "%";
```

Do not add a leading `%`. This small change can determine whether a B-tree prefix index can be used.

### 27.5. What if you want to support user-entered wildcards?

When designing a search syntax where users intentionally enter `%`/`_`, make it explicit in the UI and enforce controls:

- Pattern length limits.
- Wildcard count limits.
- Rejecting overly broad patterns.
- Timeouts/quotas.
- Index planning.
- Rate limiting and pagination.

Do not blur "searching literal text" with "letting users write query patterns" without defining a clear contract.

## 28. User-Supplied Regex: SQL Safety Is Not Enough for Performance Safety

An application might let users enter a regex:

```sql
SELECT document_id, title
FROM text_search_lab.documents
WHERE title ~* $1;
```

Bind parameters protect against SQL injection, yet a regex can still:

- Be overly long.
- Be overly broad, matching every row.
- Contain complex combinations consuming CPU/memory.
- Lack literal trigrams for indexing.
- Cause high latency when evaluated over large `body` texts.
- Be abused if the API lacks quotas.

### 28.1. Do not accept free-form regex if UX only needs contains

If users just want keyword search, use LIKE with escaped literals + a trigram index or FTS rather than handing them the entire regex language.

### 28.2. Statement timeout

Inside a test transaction:

```sql
BEGIN;

SET LOCAL statement_timeout = '5s';

SELECT COUNT(*)
FROM text_search_lab.documents
WHERE title ~* '^(PostgreSQL|Java).*';

ROLLBACK;
```

`statement_timeout` bounds statement execution time on the server. It is an **operational guardrail**, not a substitute for query/index/authorization design.

### 28.3. Input limits and controls

An API supporting free-form regex should have:

- Authentication/authorization.
- Pattern length limits.
- Policies on allowed constructs.
- Limits on searchable data/domain.
- Query timeouts.
- Rate limits/concurrency limits.
- Maximum result caps and pagination.
- Logging/observability with sensitive data redacted.

A regex engine can consume significant time and memory. Never trust an index alone to block every dangerous pattern.

### 28.4. Do not validate regex by executing it against real data

If you want to report syntax errors on a user's regex, validate in a controlled way; never let validation accidentally scan the entire table due to an unbounded query.

### 28.5. Regex syntax errors

An invalid pattern can cause PostgreSQL to raise a regex error. The application must catch it and return an appropriate error message without exposing raw errors or stack traces.

## 29. Filtering by Category and Date Before Text Search

A search endpoint may include additional filters:

```sql
SELECT document_id, title
FROM text_search_lab.documents
WHERE category = 'advanced'
  AND archived = false
  AND created_at >= timestamptz '2025-02-01 00:00:00+00'
  AND title ILIKE '%PostgreSQL%'
ORDER BY created_at DESC
LIMIT 50;
```

### 29.1. Narrowing candidate rows

Category, archived, and date predicates can shrink the number of rows needing pattern inspection, provided the planner finds a good plan.

### 29.2. Do not assume SQL WHERE runs in written order

SQL is declarative; the optimizer may reorder evaluations and choose access paths within semantic rules. Writing `category` before `ILIKE` **does not guarantee** the database filters `category` first and runs the pattern second.

### 29.3. Composite index or two separate indexes?

Considerations include:

- B-tree on `(category, created_at)`.
- Partial index for `archived = false` when archived rows make up the majority.
- GIN trigram on `title`.
- Combining bitmap indexes when supported by the planner.
- Query variants with selective prefixes.

There is no magical single B-tree+trigram index that accelerates every predicate and every `ORDER BY`. Measure each option against real patterns.

### 29.4. LIMIT and ORDER BY

`LIMIT 50` caps output rows, yet if the planner has to inspect many rows or sort candidates to find the 50 newest matches, the query can still be costly.

An access path matching `ORDER BY` can avoid a `Sort`, but may still inspect many titles before collecting 50 matches.

### 29.5. Keyset pagination

For deep pages, `OFFSET 100000` may process huge numbers of rows before returning the next page. Consider keyset pagination on `(created_at, document_id)` when the sort key is stable and indexes/pagination are designed accordingly.

## 30. Using Partial Indexes When the Workload Is Clear

If most queries only inspect non-archived documents:

```sql
CREATE INDEX documents_active_title_trgm_idx
ON text_search_lab.documents
USING gin (title gin_trgm_ops)
WHERE archived = false;
```

A partial trigram index can be smaller than a full index if archived records make up most of the table.

### 30.1. In the lab dataset, archived is only about 5%

In the sample dataset, `archived = true` occurs in roughly 1/19 of rows. A partial index for active rows is nearly the same size as the full index, so it **may not provide meaningful savings**.

Do not create a partial index just because the syntax looks neat.

### 30.2. Generic prepared plans and partial predicates

If the query is:

```sql
WHERE archived = $1
  AND title ILIKE $2
```

a generic plan cannot safely assume `$1 = false` across all executions to use a partial index with predicate `archived = false`.

If a business endpoint **always searches only active documents**, write a dedicated query variant:

```sql
WHERE archived = false
  AND title ILIKE $1
```

still binding the text input, while keeping the `archived` predicate as an explicit constant so the planner can consider the partial index.

### 30.3. Partial indexes do not replace authorization

If a document requires owner/tenant access control, an `archived` index is not a security boundary. The query must still enforce access policies.

## 31. Measuring Time, Buffers, and Index Cost

### 31.1. Measure the baseline before creating indexes

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT document_id, title
FROM text_search_lab.documents
WHERE title ILIKE '%PostgreSQL%';
```

### 31.2. Create the trigram index and re-measure

```sql
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE INDEX documents_title_trgm_idx
ON text_search_lab.documents
USING gin (title gin_trgm_ops);
```

If you already created this index earlier, **do not run `CREATE INDEX` again with the same name**. In this lab, each DDL example should only be executed once.

```sql
ANALYZE text_search_lab.documents;

EXPLAIN (ANALYZE, BUFFERS)
SELECT document_id, title
FROM text_search_lab.documents
WHERE title ILIKE '%PostgreSQL%';
```

### 31.3. Do not draw conclusions from a single run

Subsequent runs may be faster due to warm caches rather than solely the index. Run multiple iterations under comparable load and record:

- PostgreSQL version/config.
- Table/index sizes.
- Query/pattern.
- Estimated and actual rows.
- Shared buffers hit/read.
- Planning Time/Execution Time.
- Cache state, concurrency, hardware.
- INSERT/UPDATE cost after adding the index.

### 31.4. Comparing index storage

```sql
SELECT
    indexname,
    pg_size_pretty(
        pg_relation_size(
            (quote_ident(schemaname) || '.'
             || quote_ident(indexname))::regclass
        )
    ) AS index_size
FROM pg_indexes
WHERE schemaname = 'text_search_lab'
  AND tablename = 'documents'
ORDER BY indexname;
```

The indexes created in the lab are for comparison; production should not keep all of them.

### 31.5. Balancing reads and writes

A GIN trigram index on `body` can speed up contains queries while making write workloads heavier. Measure:

- INSERT throughput.
- UPDATE on `body`/`title`.
- WAL generation.
- VACUUM/index maintenance.
- Disk usage.
- Read latency at p95/p99.

Optimizing one query must not automatically be assumed to optimize the entire system.

## 32. Subtle Performance Pitfalls

### 32.1. Query wraps column in a function without a matching index

```sql
WHERE lower(title) LIKE 'postgresql%'
```

does not automatically leverage an index on `title` the way a matching expression index on `lower(title)` does.

### 32.2. Pattern starts with percent

```sql
WHERE title ILIKE '%postgresql%'
```

is not a B-tree prefix search. Consider a trigram index or changing UX to starts-with if business rules allow.

### 32.3. Very short patterns

```sql
WHERE title ILIKE '%a%'
```

can get little help from a trigram index and match a huge number of rows.

### 32.4. Unbounded result queries

```sql
SELECT *
FROM text_search_lab.documents
WHERE body ILIKE '%database%';
```

can send tens of thousands of rows with long `body` fields over the network.

### 32.5. Regex with many non-selective alternatives

```sql
WHERE title ~* '(a|b|c)'
```

can match very many rows and lacks useful literal trigrams.

### 32.6. Dynamic optional OR

```sql
WHERE ($1 IS NULL OR title ILIKE $1)
```

forces a generic plan to handle both NULL (no filter) and potentially selective patterns. Splitting into distinct query variants can be better.

### 32.7. Client fires queries on every keystroke

Autocomplete sending a request per keypress without debouncing/rate limiting can trigger many concurrent expensive `ILIKE`/regex scans.

### 32.8. Unnormalized accented data

Users type `cafe` while data stores `Café`; adding indexes does not fix semantic mismatches.

### 32.9. Relying on a single EXPLAIN with an easy pattern

Testing a long, rare `'%PostgreSQL%'` does not represent `'%a%'`, `'%%'`, or empty input.

### 32.10. Treating `cost` as real time

Planner cost is not milliseconds; always cross-check with `EXPLAIN ANALYZE` and application telemetry.

## 33. Hands-on Exercises and Solutions

Exercises use the `text_search_lab.documents` table created above. DDL/index statements should only be run once in the lab; plan outputs are empirical observations, not fixed node answers.

### Exercise 1. Which wildcards does LIKE use?

**Answer:** `%` matches 0 or more characters; `_` matches exactly one character.

### Exercise 2. Find titles starting with PostgreSQL

```sql
SELECT document_id, title
FROM text_search_lab.documents
WHERE title LIKE 'PostgreSQL%';
```

**Answer:** prefix pattern; can leverage a suitable B-tree when cost/selectivity are favorable.

### Exercise 3. Find titles ending with guide

```sql
SELECT document_id, title
FROM text_search_lab.documents
WHERE title LIKE '%guide';
```

**Answer:** suffix pattern; a leading wildcard prevents a B-tree prefix range.

### Exercise 4. Find the word "indexing" in the middle

```sql
SELECT document_id, title
FROM text_search_lab.documents
WHERE title LIKE '%indexing%';
```

**Answer:** contains pattern; `pg_trgm` is usually the index option to consider.

### Exercise 5. How does ILIKE differ from LIKE?

**Answer:** `ILIKE` is case-insensitive per locale/collation, whereas `LIKE` is typically case-sensitive under common deterministic collations.

### Exercise 6. Does ILIKE automatically match without diacritics?

**Answer:** Not guaranteed. Case folding and accent normalization are two separate concerns.

### Exercise 7. Why doesn't LIKE `'a_c'` only match an underscore?

**Answer:** `_` is a wildcard representing any single character.

### Exercise 8. Escape a literal underscore

```sql
SELECT 'doc_000001' LIKE 'doc!_000%' ESCAPE '!';
```

**Answer:** true; `!_` means a literal underscore.

### Exercise 9. Escape a literal % sign

```sql
SELECT '50% off' LIKE '50!%%' ESCAPE '!';
```

**Answer:** true; `!%` is a literal percent, while the trailing `%` remains a wildcard.

### Exercise 10. Escape the ! character itself

```sql
SELECT 'hello!world' LIKE 'hello!!world' ESCAPE '!';
```

**Answer:** true.

### Exercise 11. Does NULL LIKE '%' evaluate to true or false?

**Answer:** NULL. In `WHERE`, `UNKNOWN` is not retained as `TRUE`.

### Exercise 12. Does `NOT LIKE` include NULL titles?

**Answer:** Not automatically; add `OR title IS NULL` if business logic requires it.

### Exercise 13. How does regex operator `~` differ from LIKE?

**Answer:** `~` uses POSIX regex and can match substrings; `LIKE` uses SQL wildcards and matches the full string.

### Exercise 14. Which operator is case-insensitive regex?

**Answer:** `~*`.

### Exercise 15. Case-insensitive negated regex?

**Answer:** `!~*`.

### Exercise 16. Regex for code AB-1234

```sql
SELECT 'AB-1234' ~ '^[A-Z]{2}-[0-9]{4}$';
```

**Answer:** true, if the string has exactly two A–Z letters, a hyphen, and four digits.

### Exercise 17. Why are `^` and `$` important?

**Answer:** They anchor the start/end of the pattern; without anchors, a regex can match just a small slice of the string.

### Exercise 18. What is the regex equivalent of LIKE `'%SQL%'`?

**Suggested answer:** `~ 'SQL'` for substring matching (note case sensitivity); `~* 'sql'` if case-insensitive is desired.

### Exercise 19. What does a dot mean in regex?

**Answer:** `.` matches any single character per regex semantics; use `\.` for a literal dot.

### Exercise 20. How is alternation written?

```sql
SELECT 'Java indexing' ~ '^(Java|PostgreSQL)';
```

**Answer:** true. `|` is OR inside regex.

### Exercise 21. Does `SIMILAR TO` match substrings like `~`?

**Answer:** No. `SIMILAR TO` requires full-string matching under SQL-style pattern semantics.

### Exercise 22. What does `regexp_match` return when there is no match?

**Answer:** Normally NULL; on a match it returns a text array of captured groups or the whole match.

### Exercise 23. How does `regexp_matches` with `g` differ?

**Answer:** It returns a set of rows for multiple matches; no match may emit zero rows, unlike a scalar NULL.

### Exercise 24. Replace every group of digits

```sql
SELECT regexp_replace(
    'A12 B345',
    '[0-9]+',
    '#',
    'g'
);
```

**Answer:** `A# B#`.

### Exercise 25. Split by comma or semicolon

```sql
SELECT regexp_split_to_array(
    'a,b;c',
    '[,;]'
);
```

**Answer:** a text array containing `a`, `b`, `c`.

### Exercise 26. Why can `LIKE 'prefix%'` use a B-tree?

**Answer:** The prefix defines a key range in a suitable B-tree ordering, narrowing candidate keys.

### Exercise 27. Why isn't `LIKE '%term%'` well supported by B-tree?

**Answer:** The starting characters are unknown, so there is no favorable contiguous prefix key range.

### Exercise 28. When is `text_pattern_ops` useful?

**Answer:** When prefix `LIKE` needs a B-tree in collations where the default operator class does not provide the desired access path.

### Exercise 29. Does `text_pattern_ops` make ILIKE substring fast?

**Answer:** Not by itself; look at `lower(...)` expression indexes for prefixes or trigrams for substring/`ILIKE`.

### Exercise 30. Create a case-insensitive prefix expression index

```sql
CREATE INDEX documents_lower_title_prefix_idx
ON text_search_lab.documents
    ((lower(title)) text_pattern_ops);
```

**Answer:** The index supports the `lower(title)` expression in matching conditions; if already created in the lab, do not recreate it.

### Exercise 31. Why is an index on title not equivalent to an index on lower(title)?

**Answer:** One stores the raw column and the other stores expression values; the planner needs an access path matching the query expression.

### Exercise 32. Which extension provides trigram indexing?

**Answer:** `pg_trgm`.

### Exercise 33. How is a GIN trigram index created?

```sql
CREATE INDEX documents_title_trgm_idx
ON text_search_lab.documents
USING gin (title gin_trgm_ops);
```

**Answer:** Use `gin_trgm_ops` once the extension is available; avoid duplicates if already created.

### Exercise 34. Does GIN trigram speed up every short pattern?

**Answer:** No. Patterns lacking literal trigrams or matching very common strings may not benefit.

### Exercise 35. Why does a trigram index still need Recheck Cond?

**Answer:** The index identifies candidates from trigrams; the executor must verify they satisfy the full LIKE/ILIKE/regex predicate.

### Exercise 36. Are GIN and GiST trigrams completely identical?

**Answer:** No. Their structure, recheck behavior, write cost, and similarity/distance-ordering traits differ; measure against your workload.

### Exercise 37. When should you use Full Text Search instead of LIKE?

**Answer:** When you need word/lexeme search, multiple words, search logic, and ranking; not when you need arbitrary substrings in the middle of words.

### Exercise 38. Why isn't `ILIKE '%pg_trgm%'` guaranteed to match only a literal underscore?

**Answer:** `_` is a LIKE wildcard; use `ILIKE '%pg!_trgm%' ESCAPE '!'` to match a literal underscore.

### Exercise 39. Does parameter binding automatically escape % and _?

**Answer:** No. Binding prevents SQL injection while LIKE wildcard semantics remain active; the application must escape literal search text when needed.

### Exercise 40. How do you escape LIKE literals in Java?

**Answer:** Sequentially replace `! -> !!`, `% -> !%`, `_ -> !_`, then add application-intended wildcards and bind.

### Exercise 41. What risk arises if a user enters regex `.*`?

**Answer:** Overly broad pattern that can match huge numbers of rows and burn CPU/I/O; enforce input bounds, timeouts, quotas, and query scope.

### Exercise 42. Does `statement_timeout` make queries always fast?

**Answer:** No. It can cancel queries exceeding the limit, but does not improve the access path.

### Exercise 43. Why might LIMIT 20 not make substring search cheap?

**Answer:** The executor may have to inspect many rows or sort before finding 20 properly ordered matches.

### Exercise 44. Does `cost=1000` mean 1000 ms?

**Answer:** No. It is a planner cost unit.

### Exercise 45. Is seeing a Seq Scan on a small table a bug?

**Answer:** No. Reading a small table sequentially can be cheaper than index lookups even when an index exists.

### Exercise 46. Should you add indexes endlessly?

**Answer:** No. Every index increases storage, WAL, and write/maintenance cost. Only create them when justified by workload evidence.

### Exercise 47. Can case-insensitive `ILIKE` replace every regex?

**Answer:** No. `ILIKE` only has `%`/`_` wildcards; it lacks full regex character classes, alternations, and quantifiers.

### Exercise 48. Outline a search benchmark process

**Suggested answer:** Measure baseline; create the right index; `ANALYZE`; re-measure `EXPLAIN (ANALYZE, BUFFERS)` across short/long prefix/contains/ILIKE/regex queries; run multiple iterations and concurrency tests; compare planning/execution time, buffers, rows, write impact, storage, and p95/p99.

## 34. Practical Search Decision Matrix

| Requirement | First Option | At Large Data Scale |
| --- | --- | --- |
| Exact title | `title = ?` | Suitable B-tree index |
| Starts with, case-sensitive | `title LIKE 'abc%'` | B-tree `text_pattern_ops` under appropriate collation |
| Starts with, case-insensitive | `lower(title) LIKE 'abc%'` | Expression B-tree `lower(title) text_pattern_ops` |
| Contains literal | `title LIKE '%abc%'` | `pg_trgm` GIN/GiST if pattern is selective enough |
| Contains case-insensitive | `title ILIKE '%abc%'` | Trigram index and measure selectivity |
| Suffix | `title LIKE '%abc'` | Trigram or reversed-string expression index if justified |
| Complex character pattern | `title ~ regex` | Trigram if literal trigrams can be extracted |
| Fuzzy/typo | Trigram similarity | GIN/GiST per operator, ranking UX |
| Multi-word lexeme search | Full Text Search | GIN `tsvector` + language-appropriate config |
| Accent-insensitive search | Normalization/search design | Index matching normalized expression and collation |
| Arbitrary user input | Bind + escaping + policy | Timeouts, rate limits, quotas, indexes |
| Autocomplete | Prefix and LIMIT | Prefix index, debounce, keyset |
| Rare query, small table | Simple LIKE/ILIKE | Seq Scan may suffice |

There is no single best choice for every problem. Start from **product semantics**, then design indexes and verify with real data.

## 35. Pre-Production Search Checklist

| Question | What to Verify |
| --- | --- |
| Does the user want exact, prefix, or contains? | Choose the right operator/wildcards |
| Are input `%`/`_` literals or wildcards? | Escape LIKE accordingly |
| Is case-insensitivity needed? | ILIKE/normalization |
| Is accent-insensitivity needed? | Test Unicode/collation/normalization |
| Is regex needed or only substring? | Do not expose free regex unnecessarily |
| Could user regexes be overly complex? | Limit length/constructs/time |
| What about empty or 1–2 char inputs? | Avoid unselective scans |
| Is there an index for prefix? | B-tree `pattern_ops` / expression index |
| Is there an index for contains? | `pg_trgm` if beneficial |
| Does the pattern yield enough literal trigrams? | Check `EXPLAIN` with realistic patterns |
| Is the body index too large? | Measure size/write cost |
| Would FTS fit better? | Lexemes, ranking, language config |
| PostgreSQL version/collation? | Verify semantics and index capability |
| Does the query use prepared params? | Compare custom/generic when patterns vary |
| Are `ORDER BY` / `LIMIT` present? | Read the entire plan, not just Filter |
| Are status/category predicates present? | Index strategy and partial indexes |
| Is tenant authorization enforced? | Never let search bypass permission boundaries |
| Is pagination enforced? | Bound rows/network traffic |
| Are debouncing/rate limiting in place? | Prevent every keystroke triggering a full scan |
| Are timeouts configured? | Appropriate `statement_timeout` |
| Did you run `EXPLAIN ANALYZE BUFFERS`? | Measure actual scans/indexes/rechecks |
| Did you benchmark short and long patterns? | Avoid cherry-picking one easy case |
| Did you measure p95/p99 and concurrency? | Protect production |
| Are sensitive patterns logged? | Redact/aggregate metadata |
| Did you measure write cost after indexing? | WAL/INSERT/UPDATE/VACUUM |
| Is `ANALYZE` scheduled/planned? | Fresh stats for the planner |
| Is there an index rollback plan? | Coordinate migrations |
| Are slow-query alerts set up? | Observability |
| Are spelling/Unicode tests included? | Ensure accurate user semantics |

## 36. Summary

### LIKE

- `%` matches zero or more characters.
- `_` matches exactly one character.
- `LIKE` matches the **entire string** against the pattern.
- `LIKE 'prefix%'` often has a chance to use a suitable B-tree index.
- `LIKE '%term%'` usually lacks a favorable B-tree prefix range.

### ILIKE

- Same wildcards as `LIKE`, but case-insensitive per the relevant locale/collation.
- Does not automatically provide accent-insensitive search or full Unicode normalization.
- `lower(title)` + expression B-tree can support case-insensitive prefixes.
- A trigram index can support case-insensitive contains.

### POSIX regex

- `~` is case-sensitive; `~*` is case-insensitive.
- Regex operators can match a **substring**, so use `^...$` when full-string matching is required.
- Supports character classes, quantifiers, grouping, and alternation.
- User-supplied regexes must be bounded to prevent overly broad/complex patterns.

### Performance

- B-tree works well for **equality/prefix** when collation/operator class fits.
- `text_pattern_ops` and `lower(...)` expression indexes solve many prefix workloads.
- `pg_trgm` with GIN/GiST supports many **contains/ILIKE/regex** patterns, but needs selective literal trigrams and incurs index/recheck costs.
- Full Text Search fits when **lexeme/keyword** semantics are needed, not arbitrary substrings.
- `EXPLAIN (ANALYZE, BUFFERS)` distinguishes Seq Scan, Index Scan, and Bitmap Scan while measuring rows/buffers/timing.
- Query shape, pattern length, case/locale, data distribution, and `ORDER BY`/`LIMIT` all influence plans.

### Safety

- Use `PreparedStatement` and bind parameters to prevent SQL injection.
- When searching **literal text**, escape `%`, `_`, and the escape character before adding wildcards.
- Bind parameters **do not** automatically prevent pattern injection or expensive regexes.
- Enforce input limits, timeouts, pagination, and quotas on search endpoints.
- Do not create every possible index; measure read benefit, write cost, and disk usage.

**Final rule:** before optimizing a `LIKE`, `ILIKE`, or regex condition, answer four questions: **(1) what exact thing must this pattern match, (2) how selective is the literal string, (3) which index can genuinely bound candidates, and (4) how many rows/blocks does EXPLAIN show PostgreSQL actually read?** Only when you can answer all four do you have the basis to choose B-tree, trigrams, Full Text Search, or redesign the search feature.
