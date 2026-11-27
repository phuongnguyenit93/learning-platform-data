# Distinguishing Exact, Prefix, Pattern, and Full-Text Search in PostgreSQL

When a user enters a keyword into a search box, the first question is **not "which index should we use?"**, but rather **"what matching rule does the user want to search by?"**. PostgreSQL offers multiple ways to search text, each answering a different kind of question.

Suppose an article management application has titles:

- `PostgreSQL cơ bản`
- `PostgreSQL nâng cao`
- `Tối ưu hiệu năng PostgreSQL`
- `Giới thiệu SQL`
- `Cơ sở dữ liệu quan hệ`

If the user enters `PostgreSQL`, the possible interpretations can differ completely:

1. **Exact search:** the title must equal the exact string `PostgreSQL`.
2. **Prefix search:** the title must **start with** `PostgreSQL`.
3. **Pattern search:** the title contains `PostgreSQL` at any position, or satisfies an expression such as "starts with A and ends with B".
4. **Full-text search (*full-text search*)**: parses the title and body into keywords (*lexemes*), then finds documents containing related words according to linguistic rules, combining AND/OR, phrases, and relevance ranking.

Typical PostgreSQL queries:

```sql
-- 1. Match the entire value using the = comparison operator
WHERE title = 'PostgreSQL'

-- 2. Match a prefix of the entire string
WHERE title LIKE 'PostgreSQL%'

-- 3. Match a pattern/substring, case-insensitive
WHERE title ILIKE '%postgresql%'

-- 4. Full-text search on tsvector
WHERE search_vector @@ plainto_tsquery('simple', 'PostgreSQL')
```

These are **illustrative WHERE expressions**, not four complete statements. Even when the user types the same word, **semantics, result sets, index usability, and execution cost can vary dramatically**.

This lesson explains how to choose, implement, and measure performance for each search type in **PostgreSQL**, especially in Java/JDBC applications, search APIs, and Vietnamese data.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Accurately distinguish the meanings of **full-string match, prefix match, pattern match, word match, and full-text search**.
2. Use `=`, `LIKE`, `ILIKE`, `SIMILAR TO`, and the regex operators `~`, `~*` with the right semantics.
3. Understand the wildcards `%`, `_`, escape characters, and cases where users enter percent signs or underscores as literal data.
4. Explain why a B-tree index fits equality/prefix queries but usually does not directly help with `'%keyword%'` patterns.
5. Use `text_pattern_ops`, expression indexes on `lower(...)`, and consider `citext` when appropriate.
6. Use `pg_trgm` with GIN/GiST for substring search, `ILIKE`, regex, and similarity search.
7. Use PostgreSQL Full-Text Search (FTS): `to_tsvector`, `plainto_tsquery`, `phraseto_tsquery`, `websearch_to_tsquery`, `to_tsquery`, and the `@@` operator.
8. Build a generated `tsvector` column, a GIN index, and rank results with `ts_rank`/`ts_rank_cd`.
9. Recognize the limitations of the `simple` configuration with Vietnamese, diacritics, letter case, word segmentation, and normalization policies.
10. Use safe parameter binding without turning user search strings into uncontrolled SQL or regex.
11. Read `EXPLAIN (ANALYZE, BUFFERS)` to inspect indexes, filters, cardinality, and cost.
12. Design a search API with pagination, ranking, resource limits, and semantic testing.

## 2. Map of the Four Search Types

| Type | Intent | PostgreSQL Expression | Example matching input `PostgreSQL` |
| --- | --- | --- | --- |
| **Exact** | Entire value equals string | `title = 'PostgreSQL'` | Only equivalent values per comparison/collation rules |
| **Prefix** | String starts with keyword | `title LIKE 'PostgreSQL%'` | `PostgreSQL cơ bản` |
| **Pattern** | Character position/template | `title ILIKE '%postgresql%'` or regex | `Tối ưu PostgreSQL` |
| **Full-text** | Words and search expression meaning | `search_vector @@ plainto_tsquery(...)` | Documents containing lexeme `postgresql` in title/body |

### 2.1. There is no "best search" operator for every case

- **Item codes, order codes, identifier usernames:** usually use `=`.
- **Autocomplete by leading code/title:** usually use `LIKE 'abc%'` with an appropriate key/index.
- **Substring lookup inside a code or title:** usually requires `ILIKE '%abc%'`/`LIKE '%abc%'` and can use `pg_trgm`.
- **Searching articles by multi-word content, relevance, and ranking:** usually starts with FTS.

If a user enters an incomplete word in the middle of a string, FTS does not automatically solve every case; if you need to search meaningful words in an article, `LIKE '%...%'` does not automatically provide stemming, stop words, or proper ranking either.

### 2.2. "Exact" can mean three different things

Do not confuse:

1. **Exact entire string:** `title = 'SQL'`.
2. **Exact word in content:** FTS finds the lexeme `sql` (not synonymous with the entire title being SQL).
3. **Exact phrase:** FTS phrase query, which checks lexemes by position/order, **not guaranteed to match the exact original byte sequence**.

These three requirements do not share the same comparison operation.

## 3. Preparing the Documents Table for the Lab

The hands-on section uses a dedicated schema so it does not affect other data. DDL/DML statements should only be run on a **test PostgreSQL database**.

### 3.1. Create the schema and table

```sql
CREATE SCHEMA IF NOT EXISTS text_search_lab;

CREATE TABLE text_search_lab.documents (
    document_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    title TEXT NOT NULL,
    summary TEXT NOT NULL,
    body TEXT NOT NULL,
    category TEXT NOT NULL,
    published_at TIMESTAMPTZ NOT NULL,
    search_vector TSVECTOR GENERATED ALWAYS AS (
        setweight(
            to_tsvector('simple'::regconfig, COALESCE(title, '')),
            'A'
        ) ||
        setweight(
            to_tsvector('simple'::regconfig, COALESCE(body, '')),
            'B'
        )
    ) STORED
);
```

The `search_vector` column stores lexemes of **title** and **body**, assigning weight **A** to title and **B** to body. The `STORED` generated column syntax works in modern PostgreSQL versions that support generated columns. Explicitly providing the `'simple'::regconfig` configuration to `to_tsvector` keeps the expression deterministic for a generated column and avoids depending on the session's `default_text_search_config`.

**Note:** `summary` is not included in `search_vector`; that is a lab design choice. If searching `summary` is also required, it must be added to the expression and the weights/costs re-evaluated.

### 3.2. Load sample data

```sql
INSERT INTO text_search_lab.documents
    (title, summary, body, category, published_at)
VALUES
    (
        'PostgreSQL cơ bản',
        'Giới thiệu PostgreSQL cho người mới',
        'Học tạo bảng, SELECT và các phép JOIN trong PostgreSQL.',
        'database', '2026-01-03 08:00:00+00'
    ),
    (
        'PostgreSQL nâng cao',
        'Tìm hiểu cơ chế nội bộ',
        'Giải thích MVCC, transaction, WAL và cách tối ưu truy vấn.',
        'database', '2026-01-05 08:00:00+00'
    ),
    (
        'Tối ưu PostgreSQL',
        'Phân tích query plan và chỉ mục',
        'Dùng EXPLAIN ANALYZE để đo truy vấn PostgreSQL.',
        'database', '2026-01-10 08:00:00+00'
    ),
    (
        'Postgres và hệ sinh thái',
        'Các công cụ kết nối',
        'Giới thiệu công cụ quản trị PostgreSQL và JDBC.',
        'database', '2026-01-12 08:00:00+00'
    ),
    (
        'Giới thiệu SQL',
        'Câu lệnh SQL nhập môn',
        'SQL cho phép truy vấn dữ liệu từ các bảng quan hệ.',
        'sql', '2026-01-15 08:00:00+00'
    ),
    (
        'SQL nâng cao',
        'CTE và window functions',
        'Học SQL với subquery, CTE, ROW_NUMBER và JOIN.',
        'sql', '2026-01-18 08:00:00+00'
    ),
    (
        'Java JDBC với PostgreSQL',
        'Kết nối Java tới database',
        'PreparedStatement, ResultSet và truy vấn dữ liệu an toàn.',
        'java', '2026-02-01 08:00:00+00'
    ),
    (
        'Học Java căn bản',
        'Biến, kiểu và lớp',
        'Java có class, object và exception handling.',
        'java', '2026-02-03 08:00:00+00'
    ),
    (
        'MySQL và PostgreSQL',
        'So sánh hai hệ quản trị',
        'Cả MySQL và PostgreSQL đều hỗ trợ SQL.',
        'database', '2026-02-08 08:00:00+00'
    ),
    (
        'Tìm kiếm toàn văn',
        'Giới thiệu full text search',
        'PostgreSQL hỗ trợ tsvector, tsquery và chỉ mục GIN.',
        'search', '2026-02-11 08:00:00+00'
    ),
    (
        'Tìm kiếm tiền tố',
        'Gợi ý tìm kiếm qua LIKE',
        'LIKE với dấu phần trăm ở cuối có thể tìm theo tiền tố.',
        'search', '2026-02-14 08:00:00+00'
    ),
    (
        'Mẫu và biểu thức chính quy',
        'LIKE, ILIKE và regex',
        'Biểu thức chính quy giúp khớp cấu trúc của chuỗi.',
        'search', '2026-02-17 08:00:00+00'
    ),
    (
        '50% tối ưu SQL',
        'Dấu phần trăm là dữ liệu',
        'Một tiêu đề chứa ký tự phần trăm đúng nghĩa.',
        'sql', '2026-03-01 08:00:00+00'
    ),
    (
        'Mã A_B trong hệ thống',
        'Dấu gạch dưới là dữ liệu',
        'Tên mã chứa dấu gạch dưới cần escape khi dùng LIKE.',
        'search', '2026-03-03 08:00:00+00'
    ),
    (
        'postgresql không viết hoa',
        'So sánh phân biệt hoa thường',
        'Cách dùng ILIKE và lower để tìm tiêu đề.',
        'database', '2026-03-05 08:00:00+00'
    ),
    (
        'Hiệu năng truy vấn',
        'Đọc EXPLAIN và chỉ mục',
        'Index Scan có thể nhanh hơn Seq Scan với điều kiện phù hợp.',
        'database', '2026-03-07 08:00:00+00'
    ),
    (
        'Chỉ mục GIN',
        'Cấu trúc chỉ mục chuyên biệt',
        'GIN hỗ trợ full text search và nhiều kiểu dữ liệu khác.',
        'database', '2026-03-10 08:00:00+00'
    ),
    (
        'Tìm kiếm gần đúng',
        'Trigram và similarity',
        'pg_trgm có thể giúp tìm chuỗi con và chuỗi gần giống.',
        'search', '2026-03-12 08:00:00+00'
    ),
    (
        'Phân tích tiếng Việt',
        'Từ ghép và dấu thanh',
        'Tìm kiếm tiếng Việt cần chính sách chuẩn hóa và phân tích từ.',
        'search', '2026-03-15 08:00:00+00'
    ),
    (
        'PostgreSQL backup',
        'Sao lưu và phục hồi',
        'pg_dump và PITR là các cách phục hồi theo nhu cầu.',
        'database', '2026-03-20 08:00:00+00'
    ),
    (
        'SQL injection là gì?',
        'Tham số hóa câu SQL',
        'Dùng PreparedStatement, không nối input vào SQL.',
        'security', '2026-03-22 08:00:00+00'
    ),
    (
        'Khóa và transaction',
        'Cơ chế khóa trong database',
        'Transaction isolation và deadlock ảnh hưởng cạnh tranh.',
        'database', '2026-03-24 08:00:00+00'
    ),
    (
        'Tài liệu không có PostgreSQL trong tiêu đề',
        'Chỉ đề cập công nghệ trong summary',
        'Nội dung body nói về JSONB, MVCC và locking.',
        'database', '2026-03-26 08:00:00+00'
    ),
    (
        'Tài liệu về cấu trúc dữ liệu',
        'Không nhắc tới các hệ quản trị cụ thể',
        'Giải thích cây, danh sách liên kết và thuật toán.',
        'algorithm', '2026-03-30 08:00:00+00'
    );
```

### 3.3. Statistics after loading

```sql
ANALYZE text_search_lab.documents;

SELECT
    COUNT(*) AS document_count,
    COUNT(*) FILTER (WHERE category = 'search')
        AS search_category_count
FROM text_search_lab.documents;
```

The dataset has **24 mock documents**, enough to observe semantics. On a table this small, the planner may prefer `Seq Scan` even when we create indexes. **Do not force performance conclusions from 24 rows**; the indexes are shown to understand design, while benchmarking requires a representative dataset.

## 4. Exact Search Using the Equals Operator

Query:

```sql
SELECT document_id, title
FROM text_search_lab.documents
WHERE title = 'PostgreSQL cơ bản';
```

The requirement here is that **the entire title value matches under the `=` comparison**, not merely that it contains a word.

### 4.1. How is it different from substring search?

```sql
-- Compare the entire string:
WHERE title = 'PostgreSQL'

-- Starts with the string:
WHERE title LIKE 'PostgreSQL%'

-- Contains the substring at any position:
WHERE title LIKE '%PostgreSQL%'
```

Example title `PostgreSQL cơ bản`:

| Condition | Matches? |
| --- | :---: |
| `title = 'PostgreSQL'` | No |
| `title = 'PostgreSQL cơ bản'` | Yes |
| `title LIKE 'PostgreSQL%'` | Yes |
| `title LIKE '%PostgreSQL%'` | Yes |
| `title = 'postgresql cơ bản'` under typical case-sensitive comparison | No |

Exact equality under `=` is affected by **data type and collation**. With common deterministic collations, differences in letter case or diacritics are usually not considered equal; however, PostgreSQL also supports special collation configurations. Do not design a "strict byte-for-byte comparison" requirement while ignoring collation, Unicode normalization, or the `CHAR(n)` type.

### 4.2. Using a B-tree index

```sql
CREATE INDEX idx_lab_documents_title_eq
ON text_search_lab.documents (title);
```

A B-tree index is usually the natural choice for equality:

```sql
EXPLAIN
SELECT document_id, title
FROM text_search_lab.documents
WHERE title = 'PostgreSQL cơ bản';
```

On a large table with high selectivity, you may see an `Index Scan` or `Bitmap Index Scan`. On a 24-row table, `Seq Scan` can still be a good choice.

### 4.3. Searching by normalized code

For identifiers, you usually need to define the rules:

- Is it case-sensitive?
- Should leading/trailing whitespace be trimmed?
- Are original Unicode characters preserved?
- Is there a unique constraint enforcing that exact rule?

If a code is normalized at write time, an equality query and a unique index can be better than using `ILIKE` on every read.

### 4.4. Do not confuse NULL with an empty string

```sql
-- Does not find NULL rows:
WHERE title = NULL

-- Proper way to check NULL:
WHERE title IS NULL

-- An empty string is a distinct value:
WHERE title = ''
```

In the lab schema, `title NOT NULL` is set, but in real systems clearly distinguish null, empty string, and whitespace.

## 5. Case-Insensitive Full-String Search

If the entire title must match while ignoring case differences, a simple option is:

```sql
SELECT document_id, title
FROM text_search_lab.documents
WHERE lower(title) = lower('POSTGRESQL CƠ BẢN');
```

Or use `ILIKE` **without wildcards**:

```sql
SELECT document_id, title
FROM text_search_lab.documents
WHERE title ILIKE 'POSTGRESQL CƠ BẢN';
```

Neither approach should be mistaken for **comprehensive Unicode/Vietnamese diacritic normalization**. They rely on PostgreSQL's case folding/locale rules, and may differ from complex normalization policies required by a product.

### 5.1. Expression index for lower(title)

```sql
CREATE INDEX idx_lab_documents_title_lower_eq
ON text_search_lab.documents (lower(title));
```

The query must use the matching expression:

```sql
SELECT document_id, title
FROM text_search_lab.documents
WHERE lower(title) = 'postgresql cơ bản';
```

If you use `WHERE title ILIKE '...'`, do not assume PostgreSQL always transforms it into a condition on the `lower(title)` expression index. Check the plan for the **actual expression**.

### 5.2. CITEXT is another option, not a mandatory requirement

The `citext` extension provides a character type with case-insensitive comparison behavior in appropriate cases. If an application needs case-insensitive usernames/emails under a specific policy, you can consider using that type and corresponding indexes/constraints.

However:

- It requires the extension and appropriate privileges.
- Comparison rules depend on locale/collation.
- Not every Unicode, accent-insensitive, or multilingual case-folding requirement is solved by `citext` alone.
- Migrating column types can affect unique constraints and existing values.

In this lab, we keep `TEXT` so each operation remains explicit.

## 6. Prefix Search Using LIKE 'abc%'

Example:

```sql
SELECT document_id, title
FROM text_search_lab.documents
WHERE title LIKE 'PostgreSQL%'
ORDER BY title;
```

`LIKE` uses wildcard characters:

- `%`: matches **zero or more characters**.
- `_`: matches **exactly one character**.

The pattern `'PostgreSQL%'` means:

```text
The string must start with: PostgreSQL
Followed by 0, 1, or more arbitrary characters
```

### 6.1. Why is prefix different from substring search?

```sql
-- Prefix: starts with PostgreSQL
WHERE title LIKE 'PostgreSQL%'

-- Suffix: ends with PostgreSQL
WHERE title LIKE '%PostgreSQL'

-- Substring: anywhere in the string
WHERE title LIKE '%PostgreSQL%'
```

For the title `Tối ưu PostgreSQL`:

- Does not match `'PostgreSQL%'`.
- Can match `'%PostgreSQL'`.
- Matches `'%PostgreSQL%'`.

### 6.2. Using LIKE for autocomplete

When the user types `Postg`:

```sql
SELECT document_id, title
FROM text_search_lab.documents
WHERE title LIKE 'Postg%'
ORDER BY title
LIMIT 10;
```

This suggests results by **title string prefix**, rather than automatically selecting results by linguistic relevance.

If you want case-insensitive matching:

```sql
SELECT document_id, title
FROM text_search_lab.documents
WHERE title ILIKE 'postg%'
ORDER BY title
LIMIT 10;
```

Do not assume both queries have the same access path: `ILIKE` and `LIKE` have different matching/index rules.

## 7. B-tree Index for Prefix Search and text_pattern_ops

A B-tree can efficiently support patterns with a **fixed prefix**, because it can seek a range of values starting from that prefix.

For `TEXT` data:

```sql
CREATE INDEX idx_lab_documents_title_pattern
ON text_search_lab.documents (title text_pattern_ops);
```

`text_pattern_ops` is a **B-tree operator class** for pattern comparisons, useful when using `LIKE 'prefix%'` under collations where a default B-tree index cannot optimize prefix matching by deriving an appropriate range.

### 7.1. When might a regular B-tree index be enough?

Under a **C** collation or an environment with suitable ordering semantics, a default B-tree index can support prefix LIKE. With linguistic collations, `text_pattern_ops` may be needed to leverage the index for pattern matching under appropriate binary-like rules.

Do not create both indexes on every table out of habit. Inspect the real queries and actual plans.

### 7.2. LIKE needs a fixed leading prefix

```sql
WHERE title LIKE 'PostgreSQL%'
```

has a fixed prefix `PostgreSQL`.

However:

```sql
WHERE title LIKE '%PostgreSQL'
```

starts with a wildcard, so a B-tree ordered by **the entire title from left to right** cannot jump directly to values with an arbitrary suffix.

### 7.3. Expression index for case-insensitive prefix

```sql
CREATE INDEX idx_lab_documents_lower_title_pattern
ON text_search_lab.documents
    (lower(title) text_pattern_ops);
```

Corresponding query:

```sql
SELECT document_id, title
FROM text_search_lab.documents
WHERE lower(title) LIKE 'postgresql%'
ORDER BY title
LIMIT 20;
```

This makes the lowercased value the **search key** of the index, instead of storing `title` as-is and hoping `ILIKE` automatically uses an expression index.

### 7.4. LIKE with a bound parameter

If the query uses:

```sql
WHERE title LIKE $1
```

the planner may need to know the concrete pattern to deduce a fixed prefix. With a **generic prepared plan**, the parameter value is not known in the same way as in a custom plan, so you cannot assume every `LIKE ?` leverages a prefix index the same way a literal does.

Check `EXPLAIN EXECUTE` on the **exact query form and plan mode your application actually uses**.

## 8. LIKE and Wildcard Characters: % Is Not an Ordinary Percent Sign

Suppose a user wants to find titles starting with the text:

```text
50%
```

If the application does:

```sql
WHERE title LIKE '50%%'
```

both `%` characters are wildcards; this pattern matches **any string starting with '50'**, even without an actual percent sign.

To treat the percent sign as literal data, you must escape it.

### 8.1. Escaping with an explicit character

Choose `!` as the escape character:

```sql
SELECT document_id, title
FROM text_search_lab.documents
WHERE title LIKE '50!%%' ESCAPE '!';
```

Explanation:

- `50`: two ordinary characters.
- `!%`: **one literal % sign**.
- Trailing `%`: wildcard for the rest of the string.

Therefore the pattern finds titles starting with `50%`.

### 8.2. Escaping the underscore

If you want to find the string `A_B`:

```sql
SELECT document_id, title
FROM text_search_lab.documents
WHERE title LIKE '%A!_B%' ESCAPE '!';
```

`!_` is a literal underscore; the leading and trailing `%` allow the substring at any position.

### 8.3. Escaping the escape character itself

When using `ESCAPE '!'`, a literal `!` must be written as `!!` in the pattern. Escaping rules must be handled by the **application code that builds the pattern**, rather than blindly taking raw input and wrapping it with `%`.

### 8.4. Note about backslashes

PostgreSQL allows choosing the escape character in LIKE. Representing backslashes inside SQL literals and Java string literals can easily be confusing; using `ESCAPE '!'` in the lab serves as a clear example and avoids unnecessary escaping layers.

## 9. Parameter Binding in JDBC: Safe for Both SQL and LIKE Patterns

Do not build SQL statements via string concatenation:

```java
// DO NOT: insert user input directly into SQL text.
String sql = "SELECT * FROM documents WHERE title LIKE '%"
    + userInput + "%'";
```

That creates a **SQL injection** risk when input becomes part of the SQL code.

Use `PreparedStatement`:

```java
String sql = """
    SELECT document_id, title
    FROM text_search_lab.documents
    WHERE title LIKE ? ESCAPE '!'
    ORDER BY title
    LIMIT 20
    """;

String escaped = userInput
    .replace("!", "!!")
    .replace("%", "!%")
    .replace("_", "!_");

String containsPattern = "%" + escaped + "%";

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setString(1, containsPattern);
    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            System.out.println(rs.getString("title"));
        }
    }
}
```

Key takeaways:

1. `?` is a **bind parameter**, not a place for SQL text concatenation.
2. `%` and `_` from user input are escaped so they are interpreted as **literal data**.
3. The two `%` signs intentionally added by the application define substring matching.
4. Replacement order matters: escape `!` first, then escape `%` and `_`.
5. `PreparedStatement` **prevents SQL injection in bind-parameter value context**, but **does not automatically turn LIKE wildcards into literals**.

### 9.1. Prefix search

If you want values starting with the input:

```java
String prefixPattern = escaped + "%";
```

If you want equality:

```sql
WHERE title = ?
```

then no wildcards or LIKE escaping are needed; bind the raw value directly.

### 9.2. Input validation

An API should enforce limits:

- Maximum keyword length, measured according to an appropriate Unicode policy.
- Allowed query modes: exact/prefix/contains/full_text.
- Page size, timeout, and data access permissions.
- Which fields can be searched: title/body/category or a whitelisted column set.

Do not allow clients to arbitrarily inject column names, SQL expressions, ORDER BY clauses, or operators into SQL via string concatenation.

## 10. ILIKE: Case-Insensitive but Does Not Strip Diacritics

`ILIKE` is a PostgreSQL extension operator for case-insensitive pattern matching according to locale/collation rules.

```sql
SELECT document_id, title
FROM text_search_lab.documents
WHERE title ILIKE 'postgresql%';
```

This query can find:

- `PostgreSQL cơ bản`.
- `PostgreSQL nâng cao`.
- `postgresql không viết hoa`.

However, it is **not automatically synonymous with "Vietnamese accent-insensitive"**:

```text
toi uu   ≠   tối ưu
```

in many common configurations.

### 10.1. Why are diacritics not stripped by default?

Case and accents are two distinct normalization dimensions. For example:

- `A` and `a`: differ in case.
- `a` and `á`: differ in diacritic.
- `Đ` and `D`: different characters/orthography, not simply case.

If a product requires accent-insensitive search to match accented text, you must design a **normalization pipeline** and verify Unicode/linguistic compatibility.

### 10.2. Collation can change comparison results

PostgreSQL supports deterministic and non-deterministic collations, whose comparison behavior can vary by version/provider. Certain pattern operations have different restrictions depending on collation type and version.

Do not take an `ILIKE` result on one server and assume it applies identically across all clusters/collations. If business requirements demand consistent behavior, explicitly define normalization/collation and test it.

## 11. Pattern Matching with LIKE: % and _

`LIKE` is a simple tool for **character patterns**, without the full power of regex.

Examples:

```sql
-- Starts with 'Post' and ends with 'SQL'
SELECT document_id, title
FROM text_search_lab.documents
WHERE title LIKE 'Post%SQL';
```

```sql
-- Any single character between 'A' and 'B'
SELECT document_id, title
FROM text_search_lab.documents
WHERE title LIKE '%A_B%';
```

The pattern `'A_B'` **does not require a literal underscore**. It can match `A-B`, `A0B`, or `A_B` in the appropriate context, because `_` is a single-character wildcard.

### 11.1. LIKE matches the entire string against the pattern

```sql
WHERE title LIKE 'SQL'
```

matches the value against the **entire pattern** `SQL`, and does not automatically find `SQL` in the middle of a string. For a substring:

```sql
WHERE title LIKE '%SQL%'
```

### 11.2. Scope of LIKE

LIKE fits:

- Prefixes/suffixes.
- A few fixed character positions.
- Literal substrings.
- Simple, easy-to-read pattern checks.

If you need character classes, repetition bounds, or complex alternations, regex usually expresses them more clearly.

## 12. SIMILAR TO: SQL's Regex-Like Pattern Matching

PostgreSQL supports `SIMILAR TO` with patterns containing some SQL regex operators, combined with LIKE-style `%` and `_` wildcards.

Example:

```sql
SELECT document_id, title
FROM text_search_lab.documents
WHERE title SIMILAR TO '(PostgreSQL|MySQL)%';
```

Here:

- `(PostgreSQL|MySQL)`: chooses one of the two starting strings.
- `%`: the remainder of the title.

### 12.1. SIMILAR TO differs from POSIX regex

`SIMILAR TO` checks the **entire string against the pattern**, in the spirit of LIKE. Meanwhile, the POSIX regex operators `~`/`~*` **can match part of a string** if there are no `^`/`$` anchors.

Example:

```sql
-- POSIX regex: substring at any position
WHERE title ~ 'SQL'

-- SQL SIMILAR TO: requires wildcards on both sides
WHERE title SIMILAR TO '%SQL%'
```

Do not reuse the same pattern text across both operator families and expect identical behavior.

### 12.2. When to choose SIMILAR TO?

Only when SQL-regex patterns clearly describe the requirement and the team knows the syntax. For complex regex, PostgreSQL POSIX regex operators are usually the clearer choice; for simple patterns, LIKE is easier to understand.

## 13. POSIX Regular Expressions: ~, ~*, !~, !~*

Common operators:

| Operator | Semantics |
| --- | --- |
| `~` | Regex match, case-sensitive per applicable rules |
| `~*` | Regex match, case-insensitive |
| `!~` | Does not match regex, case-sensitive |
| `!~*` | Does not match regex, case-insensitive |

Examples:

```sql
-- Titles starting with PostgreSQL
SELECT document_id, title
FROM text_search_lab.documents
WHERE title ~ '^PostgreSQL';

-- Titles ending with SQL, case-insensitive
SELECT document_id, title
FROM text_search_lab.documents
WHERE title ~* 'sql$';

-- Titles containing 'Java' or 'SQL'
SELECT document_id, title
FROM text_search_lab.documents
WHERE title ~ '(Java|SQL)';
```

### 13.1. Anchors

- `^`: start of string.
- `$`: end of string.

Without anchors:

```sql
WHERE title ~ 'SQL'
```

can match at any position in `title`.

With anchors:

```sql
WHERE title ~ '^SQL$'
```

requires the **entire title** to be `SQL` according to the active regex rules.

### 13.2. Character classes and repetition

Example checking a hypothetical ASCII code string, unrelated to the lab table:

```sql
SELECT
    'AB-1234' ~ '^[A-Z]{2}-[0-9]{4}$' AS valid_code,
    'AB-12'   ~ '^[A-Z]{2}-[0-9]{4}$' AS invalid_code;
```

In the pattern:

- `[A-Z]`: one character in the range A through Z.
- `{2}`: repeated exactly twice.
- `[0-9]{4}`: four digits.

Regex is very useful for format validation, though strict validation must also account for business logic, Unicode characters, byte length, encoding, and edge cases.

### 13.3. Do not trust arbitrary user-supplied regex

If an API lets users enter an uncontrolled regex, you may encounter:

- Overly complex patterns consuming CPU.
- Queries scanning many rows.
- Cases where the regex engine runs slowly on specific patterns/data.
- Unexpected results because regex characters are metacharacters.

Parameter binding prevents SQL injection, but **does not turn regex input into literals** and **does not stop an expensive regex from consuming resources**.

Systems should generally limit length/patterns, apply timeouts and rate limits, and only allow regex when it is an actual product feature.

## 14. LIKE '%keyword%' and Why B-tree Usually Does Not Help

Substring search query:

```sql
SELECT document_id, title
FROM text_search_lab.documents
WHERE title ILIKE '%postgresql%';
```

Here the leading `%` means **the prefix of the title is unknown**. A B-tree on `title` orders data from the left, so there is no simple contiguous range of keys representing all strings that **contain** `postgresql` in the middle.

On a large table, this kind of query may have to:

1. `Seq Scan` and check every title; or
2. Use a specialized pattern/substring index such as `pg_trgm` if available and chosen by the planner.

### 14.1. Prefix can use B-tree, substring usually needs another approach

```text
LIKE 'postgres%'
  -> Has a fixed prefix
  -> B-tree with suitable config/opclass can locate key range

LIKE '%postgres%'
  -> No fixed prefix for the entire title
  -> Ordinary B-tree cannot locate a simple key range
  -> Consider trigram index, FTS, or scan depending on semantics
```

### 14.2. Do not "fix" substring search by switching to FTS if the requirement differs

If a user searches for a hidden substring inside code `ABCD1234` using `'CD12'`, lexeme-based FTS **does not inherently match the middle of a code**.

Conversely, if a user searches for an article about "transaction mechanisms", substring LIKE may be too coarse and fail to rank relevance properly.

**Semantics must drive the search technology.**

## 15. pg_trgm for Substring, ILIKE, and Similarity Search

The `pg_trgm` extension supports text processing based on **trigrams** — three-character substrings formed according to its tokenization rules. It can provide index support for many pattern and similarity operations.

In an environment with the necessary privileges, you can run:

```sql
CREATE EXTENSION IF NOT EXISTS pg_trgm;
```

**This is an optional lab section.** The extension must be available and the user needs appropriate privileges. In production, it must be approved by the DBA/operations team; do not install extensions or alter system configurations just to run an exercise.

### 15.1. GIN trigram index

```sql
CREATE INDEX idx_lab_documents_title_trgm
ON text_search_lab.documents
USING GIN (title gin_trgm_ops);
```

Then a query:

```sql
SELECT document_id, title
FROM text_search_lab.documents
WHERE title ILIKE '%postgresql%';
```

can use the trigram index when PostgreSQL extracts sufficient information from the pattern and the table is large enough for the index to pay off.

### 15.2. GIN vs GiST for pg_trgm

`pg_trgm` also supports a GiST operator class:

```sql
-- Another option; no need to create both for every workload:
-- CREATE INDEX idx_lab_documents_title_trgm_gist
-- ON text_search_lab.documents
-- USING GIST (title gist_trgm_ops);
```

GIN is often useful for pattern/filter checks; GiST can be useful for other strategies such as nearest-neighbor distance queries when appropriate. **No single index method wins every workload**; you must measure read speed, write cost, storage size, and operator types.

### 15.3. Very short patterns may not yield selective trigrams

Example:

```sql
WHERE title ILIKE '%a%'
```

A single character usually does not provide enough trigrams to narrow the result set effectively. PostgreSQL may have to scan most of the index or table. Very short substring searches on large tables often require:

- Enforcing a minimum query length.
- Requiring additional category/tenant/date filters.
- Choosing prefix search if it fits the product.
- Designing a specialized lookup mechanism for single-character/code searches if truly needed.

Do not promise that creating `gin_trgm_ops` makes **every `LIKE '%...%'`** fast.

### 15.4. Similarity is not the same as contains

`pg_trgm` provides similarity functions/operators, for example when the extension is installed:

```sql
SELECT
    title,
    similarity(title, 'Postgres') AS score
FROM text_search_lab.documents
ORDER BY score DESC, document_id
LIMIT 10;
```

Results are ordered by string similarity rather than simply checking whether `title` contains an exact substring. Similarity threshold operators (such as `%` in the `pg_trgm` family) have their own conditions and threshold settings; do not confuse that with LIKE's `%` wildcard.

## 16. How Does Full-Text Search Differ from Substring Search?

PostgreSQL Full-Text Search operates on **linguistic/lexical components** rather than mere character positions.

Key concepts:

- **Parser:** splits text into tokens according to parser/configuration rules.
- **Dictionary:** normalizes tokens into lexemes or removes stop words depending on configuration.
- **`tsvector`:** a set of normalized lexemes, along with positions and optional weights.
- **`tsquery`:** a query expression over lexemes with AND/OR/NOT/phrase/prefix operators.
- **`@@`:** checks whether a `tsvector` satisfies a `tsquery`.

Example:

```sql
SELECT
    to_tsvector(
        'simple',
        'PostgreSQL hỗ trợ tìm kiếm toàn văn'
    ) AS vector;
```

The result is a representation of lexemes and positions, **not a verbatim copy of the string**.

### 16.1. FTS is not a smarter LIKE for everything

Example with `simple`:

```sql
SELECT
    to_tsvector('simple', 'PostgreSQL')
      @@ plainto_tsquery('simple', 'PostgreSQL')
      AS matches_word,
    to_tsvector('simple', 'PostgreSQL')
      @@ plainto_tsquery('simple', 'post')
      AS matches_partial_lexeme;
```

The word `post` **does not by default** match the lexeme `postgresql` the way `LIKE 'post%'` does. FTS and string prefix have different semantics.

FTS can support **lexeme prefix matching** with dedicated syntax, but does not natively support matching **arbitrary substrings in the middle of a lexeme**.

### 16.2. Word vs phrase vs exact string

```text
title = 'Java JDBC'
  -> Entire title value equals the string per comparison rules

title ILIKE '%java jdbc%'
  -> Two consecutive character segments appear in title,
     possibly differing in case

search_vector @@ phraseto_tsquery('simple', 'Java JDBC')
  -> Lexemes Java and JDBC appear in positional relationship
     of a phrase query after token processing
```

FTS phrase search does not guarantee that spaces, punctuation, or Unicode bytes in the source match the input verbatim.

## 17. to_tsvector and Text Analysis Configurations

The function:

```sql
SELECT to_tsvector(
    'simple',
    'PostgreSQL giúp tìm kiếm văn bản'
);
```

converts text into a `tsvector`.

### 17.1. Choosing an explicit configuration

```sql
SELECT
    to_tsvector('simple', 'Running runners run') AS simple_vector,
    to_tsvector('english', 'Running runners run') AS english_vector;
```

With `simple`, tokens are processed by the simple dictionary, mainly lowercasing according to its rules; it does not perform English stemming like the `english` configuration. The `english` configuration includes dictionaries/rules tailored to English, including stemming and stop words as configured.

Actual output depends on parser, dictionaries, version, and data, so avoid writing brittle tests hardcoding exact vector strings when the goal is understanding the mechanism.

### 17.2. Do not rely on the session default configuration

```sql
SELECT to_tsvector('PostgreSQL search example');
```

The single-argument version uses `default_text_search_config`; two environments can have different defaults.

In production systems, choose an explicit configuration and use it consistently when **writing vectors, indexing, and building queries**.

### 17.3. simple and Vietnamese data

PostgreSQL does not ship by default with a specialized Vietnamese morphological analyzer equivalent to trained application tokenizers. `simple` is useful as a baseline, but typically:

- Does not understand Vietnamese compound words linguistically.
- Does not strip diacritics automatically.
- Does not perform spell correction.
- Does not expand synonyms automatically.
- Does not guarantee a multi-syllable phrase is analyzed as a semantic compound word.

If a product searches Vietnamese content at scale, test with real data, define dictionaries/tokenizers, and consider evaluating specialized solutions beyond PostgreSQL defaults.

## 18. plainto_tsquery: Converting Plain Input into a Word Search Query

Do not blindly pass raw user input into `to_tsquery`. For ordinary user input, start with:

```sql
SELECT plainto_tsquery(
    'simple',
    'PostgreSQL tối ưu'
);
```

It builds a `tsquery` from the parsed words, typically combining lexemes with **AND**.

To search in the lab table:

```sql
SELECT document_id, title, category
FROM text_search_lab.documents
WHERE search_vector
    @@ plainto_tsquery('simple', 'PostgreSQL');
```

Important point: in the lab schema, `search_vector` contains **title + body**, so a document with `PostgreSQL` in `body` is also returned even if `title` does not contain it.

### 18.1. AND can make multi-word queries narrower

```sql
WHERE search_vector
    @@ plainto_tsquery('simple', 'PostgreSQL JDBC')
```

typically requires both the `postgresql` and `jdbc` lexemes to appear in the document vector, though **not necessarily adjacent to each other**.

### 18.2. When should you use plainto_tsquery?

- Simple plain-text search boxes.
- When users should not need to know `&`, `|`, `!` syntax.
- When you want user text parsed using the chosen dictionary.
- When web search engine syntax for quotes/exclusions is not needed.

If users need phrase search or intentional OR/NOT, see the functions below.

## 19. phraseto_tsquery: Matching by Word Position

Example:

```sql
SELECT phraseto_tsquery(
    'simple',
    'Java JDBC'
);
```

This function produces a search expression requiring **lexeme order and distance**, fitting phrase search better than `plainto_tsquery`.

Query:

```sql
SELECT document_id, title
FROM text_search_lab.documents
WHERE search_vector
    @@ phraseto_tsquery('simple', 'Java JDBC');
```

### 19.1. Phrase search is not the same as '='

The title:

```text
Java JDBC với PostgreSQL
```

can match the phrase `Java JDBC` even though the entire title does not equal `Java JDBC`.

If the content contains punctuation or stop words, lexeme positions and distances may differ from simply comparing consecutive character strings.

### 19.2. Difference from AND

```text
plainto_tsquery('simple', 'Java JDBC')
  -> Both lexemes must be present, not necessarily adjacent

phraseto_tsquery('simple', 'Java JDBC')
  -> Lexemes must follow phrase order/position
```

If the requirement is "two consecutive words in token terms", FTS phrase search fits better than LIKE, though you must check the language parser policy.

## 20. websearch_to_tsquery: Search-Engine-Like Syntax

PostgreSQL supports:

```sql
SELECT websearch_to_tsquery(
    'simple',
    '"Java JDBC" OR PostgreSQL -MySQL'
);
```

Idea:

- Double quotes create a phrase requirement.
- `OR` expresses alternatives.
- A minus sign before a word excludes it per supported syntax.
- Ordinary text is parsed into lexemes.

### 20.1. Using it for a search box

```sql
SELECT
    document_id,
    title
FROM text_search_lab.documents
WHERE search_vector
    @@ websearch_to_tsquery(
        'simple',
        '"Java JDBC" OR PostgreSQL'
    );
```

This function fits when you want users to type expressions close to web search syntax without requiring strict `tsquery` syntax.

### 20.2. It does not understand every search engine syntax

`websearch_to_tsquery` **is not a full Google parser**. Do not assume it supports `site:` operators, arbitrary wildcards, regex, or field-specific syntax.

If an API advertises a complex grammar, test it and build custom parsing/validation matching the contract.

## 21. to_tsquery: Controlled FTS Expression Syntax

When you need to construct a specialized query:

```sql
SELECT to_tsquery(
    'simple',
    'postgresql & (jdbc | sql)'
);
```

Common operators:

| tsquery operator | Meaning |
| --- | --- |
| `&` | AND |
| `|` | OR |
| `!` | NOT |
| `<->` | Two lexemes adjacent in phrase position |
| `<N>` | Two lexemes N positions apart per tsquery syntax |
| `:*` | Prefix match **of a lexeme** |

Example:

```sql
SELECT document_id, title
FROM text_search_lab.documents
WHERE search_vector
    @@ to_tsquery(
        'simple',
        'postgresql & (jdbc | sql)'
    );
```

### 21.1. Strict syntax can cause input errors

`to_tsquery` requires syntactically valid expressions. Do not send raw user input such as `java sql postgres` and expect it to always parse as plain text; such input may violate the grammar.

For standard search boxes, choose `plainto_tsquery` or `websearch_to_tsquery`; use `to_tsquery` when **the application builds valid expressions itself** or users are granted controlled advanced query syntax.

### 21.2. Lexeme prefix is not whole-title prefix

```sql
SELECT document_id, title
FROM text_search_lab.documents
WHERE search_vector
    @@ to_tsquery('simple', 'postgr:*');
```

`postgr:*` means finding lexemes that start with `postgr`. It does **not** require the **entire title to start** with `postgr`.

Thus it can match a document that has the lexeme `postgresql` in the body or in the middle of the title.

## 22. GIN Index for Full-Text Search

One way to create the index:

```sql
CREATE INDEX idx_lab_documents_fts
ON text_search_lab.documents
USING GIN (search_vector);
```

With the query:

```sql
SELECT document_id, title
FROM text_search_lab.documents
WHERE search_vector
    @@ plainto_tsquery('simple', 'PostgreSQL');
```

A GIN index allows finding documents containing matching lexemes without necessarily scanning the full text of every row.

### 22.1. GIN is not B-tree

Unlike a B-tree index on the whole title, GIN for `tsvector` organizes search entries (lexemes) and the documents containing them. It fits word-containment queries via `@@`.

Do not assume `USING GIN(search_vector)` automatically optimizes:

```sql
WHERE title LIKE 'PostgreSQL%'
```

or:

```sql
WHERE title = 'PostgreSQL cơ bản'
```

Those expressions have their own access paths/indexes. **Whether an index can be used depends on the operator and expression in the query.**

### 22.2. GIN index increases write cost

When updating `title`/`body`, the generated `tsvector` and related index entries must be maintained. Costs include:

- Storage space for the index and `tsvector`.
- CPU during tokenization/normalization.
- WAL and index maintenance.
- Vacuum/reindex when required by the workload.

On read-heavy tables, FTS GIN can be well worth it. On write-heavy tables or exact-ID lookup workloads, do not add FTS to every column by default.

### 22.3. Expression GIN index instead of a generated column

Another approach:

```sql
CREATE INDEX idx_lab_documents_fts_expression
ON text_search_lab.documents
USING GIN (
    to_tsvector(
        'simple'::regconfig,
        COALESCE(title, '') || ' ' || COALESCE(body, '')
    )
);
```

However, the query must use the **matching expression** for the planner to recognize the index:

```sql
SELECT document_id, title
FROM text_search_lab.documents
WHERE to_tsvector(
    'simple'::regconfig,
    COALESCE(title, '') || ' ' || COALESCE(body, '')
) @@ plainto_tsquery('simple', 'PostgreSQL');
```

This index does not store title A / body B weights like the original `search_vector` column. The lab already has a generated column; the expression index is only for architectural comparison—**do not keep two redundant FTS indexes in production**.

### 22.4. Why is a generated column useful?

- Simpler queries: `WHERE search_vector @@ ...`.
- The same vector can be used for both filtering and ranking.
- Easy to assign weights per field.
- No need to repeat a long expression in every query.

The downside is an extra stored column and write-time maintenance overhead.

## 23. Ranking FTS Results with ts_rank

`@@` only determines **whether a row matches**. Results also need to be ordered by relevance.

```sql
WITH q AS (
    SELECT websearch_to_tsquery(
        'simple',
        'PostgreSQL tối ưu'
    ) AS query
)
SELECT
    d.document_id,
    d.title,
    d.published_at,
    ts_rank(d.search_vector, q.query) AS relevance
FROM text_search_lab.documents AS d
CROSS JOIN q
WHERE d.search_vector @@ q.query
ORDER BY relevance DESC, d.published_at DESC, d.document_id DESC
LIMIT 20;
```

### 23.1. Why have weights A/B?

In the lab schema:

```sql
setweight(to_tsvector(...title...), 'A') ||
setweight(to_tsvector(...body...), 'B')
```

Terms appearing in `title` can be scored differently from terms in `body`, depending on the ranking function and vector weights.

An example business expectation:

```text
A document with the keyword in the title:
  may deserve a higher rank than one mentioning it briefly in the body
```

However, PostgreSQL ranking does not understand full semantics like a semantic search model. Measure relevance on real query sets rather than looking only at raw scores.

### 23.2. GIN does not automatically sort by ts_rank

GIN helps find **matching documents**, but PostgreSQL still generally needs to **compute ranks for candidates and sort them** to produce the top results.

If a keyword is very common and the candidate set is large, `ORDER BY ts_rank(...) LIMIT 20` can still consume significant CPU/Sort even with a GIN index.

### 23.3. ts_rank_cd

`ts_rank_cd` is an option based on cover density, which can emphasize proximity/closeness of matching terms in appropriate cases.

```sql
SELECT
    document_id,
    title,
    ts_rank_cd(
        search_vector,
        plainto_tsquery('simple', 'PostgreSQL')
    ) AS cover_density_rank
FROM text_search_lab.documents
WHERE search_vector
    @@ plainto_tsquery('simple', 'PostgreSQL')
ORDER BY cover_density_rank DESC, document_id
LIMIT 10;
```

Do not expect `ts_rank` and `ts_rank_cd` to produce the same ordering on every query; their ranking algorithms differ.

### 23.4. Tie-breaker

Two documents can have the exact same score. Adding `document_id` to `ORDER BY` makes ordering deterministic within a snapshot, making pagination and tests less flaky.

## 24. Highlighting Matching Words with ts_headline

FTS can generate snippets highlighting matched terms:

```sql
WITH q AS (
    SELECT plainto_tsquery(
        'simple',
        'PostgreSQL'
    ) AS query
)
SELECT
    d.document_id,
    d.title,
    ts_headline(
        'simple',
        d.body,
        q.query
    ) AS snippet
FROM text_search_lab.documents AS d
CROSS JOIN q
WHERE d.search_vector @@ q.query
ORDER BY d.document_id
LIMIT 10;
```

### 24.1. ts_headline does not replace a sanitizer/XSS protection

If the application uses `ts_headline` output to render HTML with highlight tags, you must safely handle document content and markup.

User-generated `body` text may contain HTML or special characters. Do not pass raw strings from the database into `innerHTML` without proper escaping/sanitization.

### 24.2. Highlighting and ranking happen after candidate selection

It is better to limit candidates/top results per policy before generating snippets for a very large set. Running `ts_headline` over hundreds of thousands of wide `body` values can be expensive.

## 25. Full-Text Search with Vietnamese

The hardest part is usually not the `@@` syntax, but **linguistic semantics**.

For example, a user types:

```text
toi uu co so du lieu
```

while the article contains:

```text
Tối ưu cơ sở dữ liệu
```

With the `simple` configuration, PostgreSQL does not automatically guarantee that unaccented input will match accented text.

### 25.1. Need a clear search policy

Product decisions should answer:

- Is search accent-sensitive or accent-insensitive?
- Is it case-sensitive?
- Should spelling variants be merged?
- Are synonyms and abbreviations supported, e.g. `CSDL` ↔ `cơ sở dữ liệu`?
- Should multi-syllable phrases be matched as a unit?
- Are typo correction and fuzzy matching needed?
- Is there mixed English and Vietnamese data?

You cannot solve all of this with a single `ILIKE` or a single `to_tsvector('simple', ...)`.

### 25.2. unaccent is an optional tool

PostgreSQL provides the `unaccent` extension to remove diacritics via dictionaries/rules:

```sql
-- Only run if the environment permits extensions:
-- CREATE EXTENSION IF NOT EXISTS unaccent;
--
-- SELECT unaccent('Tối ưu dữ liệu');
```

If using `unaccent`, keep in mind:

- The extension/rules must be installed and managed.
- Normalization for display vs search must be consistent.
- The `unaccent` function should not be assumed **IMMUTABLE** for every use case because its dictionary/rules can change.
- Do not blindly declare an `IMMUTABLE` wrapper to create an expression index without strong guarantees of immutability and a rebuild procedure when rules change.
- Spelling and word-segmentation differences still remain after stripping diacritics.

One strategy is storing a **search-normalized field** generated and consistently updated by an application pipeline, then indexing that field with an appropriate pattern. You must plan updates/synchronization whenever the normalization algorithm changes.

### 25.3. Synonym search

For example, if a user wants `db` to find documents containing `database` or `cơ sở dữ liệu`, you may need dictionary/thesaurus configuration, query-expansion logic, or a dedicated search service.

Do not treat `pg_trgm` as a synonym engine: trigrams are character-based and do not understand that "db" semantically equals "database".

## 26. Comparing Exact, Prefix, Contains, and FTS on the Same Data

With input `PostgreSQL`:

### 26.1. Exact title

```sql
SELECT document_id, title
FROM text_search_lab.documents
WHERE title = 'PostgreSQL';
```

In the lab dataset, no title **equals solely** `PostgreSQL`, so this returns **0 rows**.

### 26.2. Prefix title

```sql
SELECT document_id, title
FROM text_search_lab.documents
WHERE title LIKE 'PostgreSQL%'
ORDER BY title;
```

This can return:

- `PostgreSQL cơ bản`.
- `PostgreSQL nâng cao`.
- `PostgreSQL backup`.

It does not return `Tối ưu PostgreSQL` because the keyword is not at the start of the title.

### 26.3. Case-insensitive contains on title

```sql
SELECT document_id, title
FROM text_search_lab.documents
WHERE title ILIKE '%postgresql%'
ORDER BY title;
```

This query can also return:

- `Tối ưu PostgreSQL`.
- `Java JDBC với PostgreSQL`.
- `MySQL và PostgreSQL`.
- `postgresql không viết hoa`.

### 26.4. FTS on title + body

```sql
SELECT document_id, title
FROM text_search_lab.documents
WHERE search_vector
    @@ plainto_tsquery('simple', 'PostgreSQL')
ORDER BY document_id;
```

This query returns documents containing the lexeme `postgresql` in `title` **or `body`**, not only in `title`. Because `summary` is not in the vector, a document mentioning PostgreSQL only in `summary` will **not match via summary**.

### 26.5. Different result sets are expected, not a bug

A good test encodes **search intent**, rather than treating LIKE's result set as the ground truth and forcing FTS to return the exact same rows.

## 27. Exact Word Match Is Not Substring Search

Examples:

```text
PostgreSQL
Postgres
postgresql
PostgreSQLbackup
```

With the `simple` configuration, FTS operates on lexemes. `ILIKE '%sql%'` can match the `SQL` character sequence inside `PostgreSQL`, whereas FTS looking for the standalone lexeme `sql` does not necessarily match the lexeme `postgresql`.

### 27.1. A visual test

```sql
SELECT
    to_tsvector('simple', 'PostgreSQL')
      @@ plainto_tsquery('simple', 'sql')
        AS fts_sql_in_postgresql,
    'PostgreSQL' ILIKE '%sql%'
        AS substring_sql_in_postgresql;
```

Key point: **FTS is not substring search**. It matches tokenized/normalized keywords.

### 27.2. Lexeme prefix search

```sql
SELECT
    to_tsvector('simple', 'PostgreSQL')
      @@ to_tsquery('simple', 'postgr:*')
        AS fts_prefix_lexeme;
```

FTS prefix allows finding lexemes with a matching prefix, but it does not mean the title must start with the prefix, nor does it support matching arbitrary substrings in the middle of a lexeme.

## 28. Searching Fixed Values: IN and ANY Instead of Patterns

If the user selects a set of **exact categories**:

```sql
SELECT document_id, title, category
FROM text_search_lab.documents
WHERE category IN ('database', 'java')
ORDER BY document_id;
```

Do not write:

```sql
WHERE category ILIKE '%database%'
   OR category ILIKE '%java%'
```

because `category` is a **fixed classification code**, which does not need fuzzy/pattern semantics.

### 28.1. Standard index for category

```sql
CREATE INDEX idx_lab_documents_category
ON text_search_lab.documents(category);
```

On a large table with selective conditions, B-tree can support equality/`IN`.

### 28.2. ANY with an array parameter

```sql
SELECT document_id, title
FROM text_search_lab.documents
WHERE category = ANY(ARRAY['database', 'java']::text[]);
```

In JDBC, you can bind an array via the driver. Do not concatenate an unvalidated category list into the SQL string.

## 29. Adding Other Predicates to Narrow Scope Before Searching

A multi-tenant system typically searches within data belonging to the logged-in tenant.

```sql
-- Hypothetical illustration assuming a table has tenant_id;
-- do not execute on the lab schema because documents does not have this column.
SELECT document_id, title
FROM tenant_documents
WHERE tenant_id = $1
  AND published_at >= $2
  AND search_vector @@ websearch_to_tsquery('simple', $3)
ORDER BY published_at DESC
LIMIT 20;
```

### 29.1. A search index does not replace authorization

Even if a GIN FTS or trigram index is very fast, you must still enforce:

- Which tenants the user can view.
- Whether the document is hidden/soft-deleted.
- Category/record permissions.
- Row-Level Security when appropriate.

Do not query system-wide search and then filter tenants in Java. That both overfetches and leaks unauthorized data out of the database.

### 29.2. Partial indexes when stable predicates exist

If most queries only search published or active documents:

```sql
-- Illustrative DDL for a hypothetical table with a published column.
CREATE INDEX idx_published_docs_fts
ON published_documents
USING GIN (search_vector)
WHERE published = TRUE;
```

This is a **partial index pattern**, not a command runnable as-is in the lab (no `published_documents` table exists yet). The planner only uses a partial index when query conditions are sufficient to prove the predicate in the planning context.

## 30. Choosing an Index by Question Type

| Query | Index usually worth trying | Things to remember |
| --- | --- | --- |
| `title = ?` | B-tree `(title)` | Compares full value, collation |
| `lower(title) = ?` | B-tree expression `(lower(title))` | Query must use matching expression |
| `title LIKE 'abc%'` | B-tree C collation or `text_pattern_ops` | Requires fixed prefix |
| `lower(title) LIKE 'abc%'` | B-tree expression + `text_pattern_ops` | Case fold and prefix |
| `title LIKE '%abc%'` | `pg_trgm` GIN/GiST when suitable | Prefix B-tree cannot solve this |
| `title ILIKE '%abc%'` | `pg_trgm` GIN/GiST when suitable | Trigrams do not guarantee speed for very short keywords |
| `title ~ 'regex'` | Can consider trigram for suitable patterns | Not every regex can extract effective trigrams |
| `search_vector @@ query` | GIN `(search_vector)` | Lexeme semantics, not substring |
| `category = ANY(...)` | B-tree `(category)` | Fixed code values should use equality |

### 30.1. One table does not need every index in this lesson

In the lab, we create multiple indexes to compare mechanisms. In production, every index:

- Consumes storage.
- Increases INSERT/UPDATE/DELETE cost.
- Can prevent HOT updates if indexed columns change.
- Requires VACUUM/maintenance.
- Increases planning/search-space and migration complexity.

Only keep indexes justified by **workload, cardinality, and real benchmarks**.

## 31. EXPLAIN: Observing Which Scan PostgreSQL Chooses

First:

```sql
EXPLAIN
SELECT document_id, title
FROM text_search_lab.documents
WHERE title = 'PostgreSQL cơ bản';
```

Next:

```sql
EXPLAIN
SELECT document_id, title
FROM text_search_lab.documents
WHERE title LIKE 'PostgreSQL%';
```

And:

```sql
EXPLAIN
SELECT document_id, title
FROM text_search_lab.documents
WHERE title ILIKE '%postgresql%';
```

Finally:

```sql
EXPLAIN
SELECT document_id, title
FROM text_search_lab.documents
WHERE search_vector
    @@ plainto_tsquery('simple', 'PostgreSQL');
```

### 31.1. The key point is not "if an index exists, it must be used"

On 24 documents, a `Seq Scan` is very cheap. The planner may choose not to use any index even when all of them exist. That **does not mean the index is broken**.

With a large dataset and selective conditions, you may see:

- `Index Scan` with B-tree equality/prefix.
- `Bitmap Index Scan + Bitmap Heap Scan` with GIN/trigram.
- `Seq Scan` when most rows match.
- `Sort` after computing ranks.

### 31.2. EXPLAIN ANALYZE BUFFERS

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT document_id, title
FROM text_search_lab.documents
WHERE search_vector
    @@ plainto_tsquery('simple', 'PostgreSQL');
```

`EXPLAIN ANALYZE` executes the SELECT to measure:

- `actual rows`.
- `loops`.
- `actual time`.
- `Buffers shared hit/read`.
- `Rows Removed by Filter` or `Recheck Cond` if present.

### 31.3. GIN may require a recheck

In a Bitmap Heap Scan, `Recheck Cond` may appear. Do not assume that is an error; the access method and lossy/exact bitmaps may require re-verifying rows when reading the heap. When `Heap Blocks: exact/lossy` appears, inspect those lines as well.

### 31.4. Do not sum cost/time across every node

A parent node's cost already includes its subtree per the planner model; measured parent time may include child work. Do not add up every `EXPLAIN` line as independent intervals.

## 32. Benchmarking on Larger Data

Generate more mock rows in the lab if you want to observe the planner favoring indexes on a larger table:

```sql
INSERT INTO text_search_lab.documents
    (title, summary, body, category, published_at)
SELECT
    CASE
        WHEN g.n % 100 = 0 THEN 'PostgreSQL tài liệu ' || g.n
        WHEN g.n % 100 = 1 THEN 'Giới thiệu PostgreSQL ' || g.n
        ELSE 'Tài liệu số ' || g.n
    END,
    'Summary for document ' || g.n,
    CASE
        WHEN g.n % 100 = 0
          THEN 'PostgreSQL GIN index và full text search.'
        WHEN g.n % 100 = 1
          THEN 'Java JDBC kết nối PostgreSQL.'
        ELSE 'Nội dung dữ liệu thử nghiệm và cấu trúc bảng.'
    END,
    CASE WHEN g.n % 2 = 0 THEN 'database'
         ELSE 'algorithm'
    END,
    TIMESTAMPTZ '2026-04-01 00:00:00+00'
        + (g.n % 10000) * INTERVAL '1 minute'
FROM generate_series(1, 100000) AS g(n);

ANALYZE text_search_lab.documents;
```

This is an **optional extra load step** and should only be run once on a study database. It generates 100,000 rows, using CPU/disk/WAL; never run it automatically in production.

### 32.1. Comparing query costs

Measure:

1. Equality `title = ...`.
2. Prefix `title LIKE 'PostgreSQL%'`.
3. Contains `title ILIKE '%postgresql%'`.
4. FTS `search_vector @@ ...`.

For substring search, test with and without a `pg_trgm` index in a controlled lab environment. For FTS, test GIN on the vector.

### 32.2. Compare the actual workload

Record:

| Metric | Meaning |
| --- | --- |
| Rows/estimated rows | Is the planner estimating accurately? |
| Execution Time | Measured SQL duration |
| Shared hit/read | Page accesses in shared buffers |
| Index size | Storage footprint to maintain |
| Rows Removed by Filter | Whether many rows are scanned/filtered out |
| Sort Method, memory | Ranking/ordering cost |
| INSERT/UPDATE latency | Write overhead from indexes |
| P95 API latency | Real application user experience |

An index that speeds up SELECTs but slows INSERTs too severely may not be worth keeping.

## 33. Prefix on TEXT vs Prefix on FTS Lexemes

These two queries:

```sql
SELECT document_id, title
FROM text_search_lab.documents
WHERE lower(title) LIKE 'postgr%';
```

and:

```sql
SELECT document_id, title
FROM text_search_lab.documents
WHERE search_vector
    @@ to_tsquery('simple', 'postgr:*');
```

are not equivalent:

- First query: **the entire title** after `lower` starts with `postgr`.
- Second query: **any indexed lexeme** starts with `postgr`.

For example, the title `Tối ưu PostgreSQL`:

- Does not match title-prefix.
- Can match FTS lexeme-prefix.

### 33.1. Word-based vs title-based autocomplete

If the UI suggests titles starting with the typed string, use **title prefix**.

If the UI suggests documents containing a word starting with the prefix anywhere in the body, use **FTS lexeme prefix**, depending on indexing and ranking.

If the UI wants an arbitrary substring match even in the middle of a word, use **substring/trigram** when appropriate.

Do not change the implementation without aligning product behavior/tests.

## 34. Choosing Search Methods for Emails, Item Codes, People Names, and Documents

### 34.1. Email or username

Usually requires **exact match after normalization** and corresponding uniqueness:

```sql
WHERE normalized_email = ?
```

Do not use `ILIKE '%@example.com%'` to verify user identity.

### 34.2. SKU or product code

If users remember the leading characters of a code:

```sql
WHERE sku LIKE 'ABC%'
```

If you need to search a segment in the middle of a code, consider `pg_trgm` or another strategy depending on code length/format.

### 34.3. Display names

May require:

- Prefix search for suggestions.
- Case/accent normalization per policy.
- Trigrams for minor typos.
- Tie-breakers and result ordering.

Do not treat people-name search as pure FTS keyword matching; proper names have distinct linguistic structures and privacy protection requirements.

### 34.4. Articles/documentation

FTS usually fits better when multiple words, phrases, and relevance are needed. It can combine category/date/tenant filters and ranking.

### 34.5. Error logs

Logs often contain exact error codes or snippets:

```text
SQLSTATE 23505
connection refused
timeout after 30000 ms
```

FTS may not preserve punctuation/codes verbatim like raw strings. For substring/regex log search, pattern/trigram approaches or a dedicated log search system may fit better.

## 35. Queries Combining Exact Filters + Full-Text Search

One endpoint can use multiple search styles in the same SQL query:

```sql
WITH q AS (
    SELECT websearch_to_tsquery('simple', 'PostgreSQL') AS query
)
SELECT
    d.document_id,
    d.title,
    d.category,
    ts_rank(d.search_vector, q.query) AS relevance
FROM text_search_lab.documents AS d
CROSS JOIN q
WHERE d.category = 'database'
  AND d.search_vector @@ q.query
ORDER BY relevance DESC, d.document_id DESC
LIMIT 20;
```

Here:

- `category = 'database'` is an **exact filter**.
- `search_vector @@ q.query` is **FTS**.
- `ORDER BY relevance` is **ranking**.

A B-tree index on `category` and a GIN FTS index may combine via bitmap operations if the cost is favorable; the planner will not always use both.

### 35.1. Do not move category into FTS

If `category` is an enum/code value, use `=` or `IN`. Putting every field into FTS can make matching ambiguous and reduce business precision.

## 36. Paginating Search Results

Example top 20 by rank:

```sql
WITH q AS (
    SELECT plainto_tsquery('simple', 'PostgreSQL') AS query
)
SELECT
    document_id,
    title,
    ts_rank(search_vector, q.query) AS rank_score
FROM text_search_lab.documents
CROSS JOIN q
WHERE search_vector @@ q.query
ORDER BY rank_score DESC, document_id DESC
LIMIT 20 OFFSET 0;
```

### 36.1. Deep OFFSET is expensive

`OFFSET 10000 LIMIT 20` may still need to identify and sort/traverse many candidates before returning 20 rows. GIN can filter quickly, but sorting by rank is generally not ordered by the index.

### 36.2. Keyset pagination for ranking

You can design a cursor over:

```text
(rank_score, document_id)
```

and fetch rows whose key pair comes after the cursor in `rank_score DESC, document_id DESC` order, while accounting for:

- Rank scores can change if documents are edited.
- The **same query/config/weighting** must be used across all pages.
- A snapshot or search session may be needed if the business requires consistent results.
- Floating-point scores can cause issues if cursor serialization loses precision.
- Generic pagination queries must handle NULL/score and tie-breakers carefully.

Do not blindly copy a timestamp-based keyset query to relevance scores without defining ranking stability.

### 36.3. Cap maximum returned results

The API should enforce a max page size, allow filtering by category/date/tenant, and consider minimum query length for very short patterns. A single-character keyword across hundreds of millions of documents can generate too many candidates.

## 37. Factors Affecting Text Search Performance

| Factor | Example | Impact |
| --- | --- | --- |
| Selectivity | `SQL` appears in 80% of titles | Index may offer little benefit |
| Wildcard position | `'abc%'` vs `'%abc%'` | Prefix B-tree vs substring |
| Term length | `'a'` vs `'postgresql'` | Trigrams carry little signal for very short terms |
| FTS configuration | `simple` vs `english` | Lexemes, stop words, stemming |
| Collation | Locale/case rules | Matching and index eligibility |
| Projection | `SELECT title` vs `SELECT *` | Row width, TOAST, I/O |
| Ranking | `ORDER BY ts_rank` | CPU + Sort over candidates |
| Table size/shape | 24 vs 100 million rows | Seq Scan vs index decision |
| UPDATE volume | Body changes constantly | GIN/trigram maintenance, WAL |
| Statistics | Fresh vs stale ANALYZE | Cardinality estimation |
| Limit/offset | `LIMIT 20` vs deep `OFFSET` | Top-K cost |
| Concurrency | 1 vs 1000 requests | Contention, CPU, I/O |

### 37.1. Full-text search can return very many candidates

An overly common term may match most documents. A GIN index helps look up lexemes, but does not eliminate the work of fetching, ranking, and sorting millions of matches. You can add valid filters, pagination, and search UX rules to bound the work.

### 37.2. Patterns on very wide body columns

`body ILIKE '%abc%'` can read far more data and put more pressure on CPU/I/O than `title ILIKE '%abc%'` because `body` is long. Consider FTS or specialized indexes when semantics allow.

### 37.3. SQL cost is not milliseconds

In `EXPLAIN`, `cost=...` is the **planner's relative estimate**, whereas `actual time=...` in `EXPLAIN ANALYZE` is the measured runtime for that execution.

Do not decide whether to keep an index by comparing `cost` between two environments with different configurations or data.

## 38. Searching Multiple Words with LIKE: Weaknesses Compared to FTS

If you want to find text containing both `PostgreSQL` and `JDBC`, you might write:

```sql
WHERE body ILIKE '%PostgreSQL%'
  AND body ILIKE '%JDBC%'
```

However, this query:

- Matches substrings, possibly inside longer words.
- Uses no stemming/dictionaries.
- Has no linguistic ranking without extra code.
- Can incur expensive scans/pattern checks on wide `body` columns.
- Allows the substrings to be arbitrarily far apart.

FTS:

```sql
WHERE search_vector
    @@ plainto_tsquery('simple', 'PostgreSQL JDBC')
```

expresses a **lexeme requirement**. This is different semantics, not merely "speeding up the old SQL".

### 38.1. OR and NOT

If you need "PostgreSQL or MySQL but not containing JDBC", you can build a `tsquery` with appropriate syntax:

```sql
SELECT document_id, title
FROM text_search_lab.documents
WHERE search_vector
    @@ to_tsquery(
        'simple',
        '(postgresql | mysql) & !jdbc'
    );
```

Or `websearch_to_tsquery` for suitable user input.

### 38.2. NOT alone can be inefficient

A query that only excludes a single word across all documents, with no selective positive keyword, may have to inspect a huge number of rows. Do not promise that GIN turns every `NOT` into an efficient index search.

## 39. Short Queries, Stop Words, and Empty Vectors

Depending on the dictionary, common words may be stripped from the vector/query. When the parsed `tsquery` contains no useful lexemes, `@@` may not match as users expect.

Example with the English configuration:

```sql
SELECT
    plainto_tsquery('english', 'the and or') AS query_terms;
```

The result can be an empty `tsquery` because all words are stop words in that dictionary.

### 39.1. Do not reflexively treat empty results as "no documents"

The API should distinguish:

- Empty input keyword.
- Keyword containing only stop words.
- Keyword shorter than policy allows.
- Valid keyword with zero matches.

Depending on UX, return a helpful message guiding the user to refine the query or show results using another filter, **rather than arbitrarily falling back to scanning all documents**.

### 39.2. Checking for useful lexemes

PostgreSQL provides query inspection functions, for example:

```sql
SELECT
    numnode(plainto_tsquery('english', 'the and or'))
        AS number_of_query_nodes;
```

This provides a signal to inspect query structure after parsing; integrate it into product policy when handling queries with no remaining terms.

## 40. Consistency Between Written Data and Search Configuration

If you index the vector with:

```sql
to_tsvector('simple', title || ' ' || body)
```

but query with:

```sql
plainto_tsquery('english', user_input)
```

then normalization can become **inconsistent**, especially regarding stemming/stop words.

### 40.1. Configuration convention

A system should specify:

```text
search_configuration = simple
searchable_fields = title, body
title_weight = A
body_weight = B
accent_policy = keep accents (lab)
case_policy = parser's configured normalization
query_parser = websearch_to_tsquery
ranking = ts_rank + published_at + document_id
```

If you change the configuration, plan to rebuild/recompute vectors and indexes accordingly. Never silently change the query parser without evaluating its effect on results.

### 40.2. Generated column updates when rows change

When `title` or `body` is updated, the `search_vector GENERATED ALWAYS AS (...) STORED` column is recomputed from the expression, and the associated GIN index is maintained as well. That ensures synchronization, at the cost of write overhead.

### 40.3. Existing data still needs attention during migrations

Adding `search_vector` to a table with millions of rows can consume significant CPU/disk and acquire locks depending on syntax/rollout approach. Evaluate workload and migration windows instead of treating a production `ALTER TABLE` like a risk-free lab command.

## 41. Searching Multiple Languages in One Table

A documentation site may contain Vietnamese, English, and technology names. A single dictionary will not necessarily fit all of them.

Design directions:

- One unified configuration like `simple` while accepting its limitations.
- Store document language/config and build vectors with the matching configuration when architecture permits.
- Separate search vectors by language group.
- Combine FTS with dedicated normalization/search services for compound words and synonyms.

### 41.1. Queries need to know which vector they are matching against

If English documents are stemmed with `english` while Vietnamese input uses `simple`, matching and ranking should not be assumed uniform. The system must define query routing and explain the UX.

### 41.2. Searching proper names and technical terms

For `PostgreSQL`, `Java`, `JDBC`, and product names, you may want to keep tokens more intact than automatic stemming allows. Multilingual datasets must be tested with realistic queries, not just an English benchmark.

## 42. Combining Exact, Prefix, and FTS in an API

A search API can expose modes:

```text
GET /documents?mode=exact&q=PostgreSQL
GET /documents?mode=prefix&q=Postg
GET /documents?mode=contains&q=gres
GET /documents?mode=full_text&q=PostgreSQL%20JDBC
```

These are **illustrative API** URLs, not existing endpoints.

### 42.1. Explicit mode ↔ SQL mapping

| mode | Primary SQL | Behavior |
| --- | --- | --- |
| `exact` | `title = ?` | Exact whole title |
| `prefix` | `lower(title) LIKE ? ESCAPE '!'` | Prefix after lowercasing |
| `contains` | `title ILIKE ? ESCAPE '!'` | Case-insensitive substring |
| `full_text` | `search_vector @@ websearch_to_tsquery('simple', ?)` | Lexeme search |

These queries **cannot guarantee the same ranking**:

- Exact may prioritize an exact match and then fall back.
- Prefix may sort by title or frequency/popularity.
- Contains may prioritize matches at the start of the title over matches at the end.
- FTS uses relevance scores computed from vectors and `tsquery`.

Defining clear UX/ranking helps users understand why the same keyword returns different results.

### 42.2. Do not let clients send arbitrary SQL operators

The service layer should map an enum:

```java
enum SearchMode {
    EXACT, PREFIX, CONTAINS, FULL_TEXT
}
```

to **predefined, controlled SQL statements**. Never turn a user-supplied string into a column name, operator, or SQL condition via string concatenation.

### 42.3. Enforce limits and return friendly errors

Examples:

- Empty keyword: return a validation error or top documents per another defined mode.
- Single-character prefix: possibly allow only for autocomplete with a very small limit.
- Contains shorter than three characters: prompt for more characters if data/indexes cannot search efficiently.
- Regex: do not enable for all users by default.
- Stop-word-only FTS: inform the user that no searchable tokens were found.

Limits should reflect product data characteristics, not arbitrary fixed PostgreSQL rules.

## 43. Security and Resource Safety of Search Boxes

Do not treat every search endpoint as a "harmless" SELECT.

### 43.1. SQL injection

Use `PreparedStatement`/bind parameters. Whether in LIKE, ILIKE, regex, or tsquery, never concatenate raw input into SQL text.

### 43.2. Wildcard injection

Bind parameters do not stop `%`/`_` inputs from altering LIKE semantics. If the product intends literal matching, escape wildcards as shown in Sections 8–9.

### 43.3. Query complexity

Users can submit:

- Highly complex regexes.
- FTS queries with many OR branches.
- NOT-only queries.
- Single-character substring searches on massive tables.
- Very large LIMIT/OFFSET values.

You need budgets/timeouts, rate limits, authentication, and complexity bounds.

### 43.4. statement_timeout

Example inside a test transaction:

```sql
BEGIN;
SET LOCAL statement_timeout = '3s';

SELECT document_id, title
FROM text_search_lab.documents
WHERE title ILIKE '%postgresql%'
LIMIT 20;

COMMIT;
```

Three seconds is just an example. `statement_timeout` bounds a single statement in PostgreSQL; the application also needs an overall request deadline and cancellation handling so connections are not held needlessly.

### 43.5. Permissions and sensitive data

Search must never bypass authorization. Especially for internal documents, apply permission filters before/alongside search and never highlight or rank documents the user is not allowed to see.

## 44. Search Method Selection Checklist

Before writing SQL, ask:

1. Does the user need the **entire string to match** or only part of it?
2. Do we need a **prefix of the entire title**, or a prefix of a word inside the document?
3. Do we need to match an **arbitrary substring inside a word**?
4. Do we need complex regex patterns?
5. Do we need multiple words and **AND/OR/phrase/NOT**?
6. Do we need **ranking** and highlighting?
7. Is search sensitive to case, Vietnamese diacritics, or Unicode normalization?
8. How long is the text, and how many documents exist?
9. Are we searching title, body, tags, or all fields?
10. Are there tenant/category/date filters that must be applied properly?
11. Which B-tree, `text_pattern_ops`, trigram, or GIN FTS index fits?
12. Does a parameterized query cause the planner to pick a generic plan different from a literal?
13. How are single-character keywords and empty queries handled?
14. Are page size/timeout/rate limits enforced?
15. Have actual rows, buffers, latency, and write overhead been measured?
16. Are semantics tested, including `%`, `_`, Unicode, and case?

## 45. Table of Common Misconceptions

| Misconception | Correct Understanding |
| --- | --- |
| `=` and `LIKE '%...%'` mean the same thing | `=` compares the full value; `LIKE` uses wildcards |
| `LIKE 'SQL'` finds `SQL` at any position | No; the pattern has no `%` on either side |
| `LIKE 'SQL%'` and `LIKE '%SQL%'` both use B-tree the same way | A leading wildcard usually prevents an effective B-tree prefix scan |
| `_` in LIKE is always a literal underscore | It is a wildcard matching any single character |
| Parameter binding makes `%` literal | No; wildcards must be escaped when literal matching is needed |
| `ILIKE` automatically strips Vietnamese diacritics | Not by default |
| Lowercasing is full Unicode normalization | No |
| `LIKE`, `SIMILAR TO`, and regex share the same grammar | No |
| `~ 'abc'` requires the entire title to equal `abc` | Regex `~` can match substrings unless anchored |
| Having `GIN(search_vector)` makes `ILIKE '%...%'` use that index | No; different operator/expression |
| Trigrams understand word meanings | No; they are character-based |
| `pg_trgm` is always fast for single-character search | Very short keywords lack selective trigrams |
| FTS is substring search | FTS works on lexemes |
| `postgr:*` is a prefix of the whole title | It is a prefix of a lexeme |
| `plainto_tsquery` handles `OR` syntax in input | Not like strict/web search grammar |
| `to_tsquery` always accepts plain text input | It has its own syntax and can throw errors |
| `phraseto_tsquery` checks exact bytes of a phrase | It matches lexeme positions after analysis |
| GIN automatically returns documents in ranked order | Ranks usually must be computed and sorted |
| English FTS always works for Vietnamese | No |
| Having GIN means no need for VACUUM/ANALYZE | Maintenance/statistics are still required |
| `SELECT *` is fine because "there is an index" | Wide projections increase heap/TOAST/transfer overhead |
| `Seq Scan` on 24 lab rows proves the index is useless | The planner may pick Seq Scan because the table is tiny |
| `ts_headline` guarantees HTML safety | Escaping/sanitization is still needed at the render layer |
| Fast search can skip authorization | No; tenant/document access must still be enforced |
| A user FTS query is always cheap | Common words, broad ORs, and ranking can be very expensive |

## 46. PostgreSQL Hands-on Exercises

Exercises use the `text_search_lab` schema unless explicitly noted as design examples. Exercises involving `pg_trgm`/`unaccent` should only be run if permitted by your learning environment.

1. **Classification:** A user types `PostgreSQL` into an article title search box; describe the differences between exact, prefix, contains, and FTS.
2. **Exact:** Write SQL to find titles strictly equal to `PostgreSQL cơ bản`.
3. **Not exact:** Explain why `title = 'PostgreSQL'` does not find `PostgreSQL cơ bản`.
4. **B-tree equality:** Create an index on `title` and use `EXPLAIN` to inspect the chosen scan.
5. **Case sensitive:** Compare `title = 'PostgreSQL cơ bản'` and `title = 'postgresql cơ bản'` under the lab collation.
6. **Lower equality:** Write `lower(title) = lower(?)` and create a suitable expression index.
7. **Prefix:** Write a `LIKE 'PostgreSQL%'` query and check which titles match.
8. **No middle match:** Why doesn't `Tối ưu PostgreSQL` match the prefix?
9. **ILIKE prefix:** Find titles starting with `postg` ignoring case.
10. **Pattern opclass:** Create a B-tree index `(title text_pattern_ops)` and explain when it is useful.
11. **Lower pattern index:** Create `(lower(title) text_pattern_ops)`; how must the query be written to use that index?
12. **Contains:** Find titles containing `postgresql` anywhere, case-insensitive.
13. **B-tree limitation:** Why doesn't `'%postgresql%'` leverage a prefix B-tree like `'postgresql%'`?
14. **Wildcards:** Explain `%` and `_` in PostgreSQL `LIKE`.
15. **Percent sign:** Find titles starting with literal `50%` using `ESCAPE '!'`.
16. **Underscore:** Find literal `A_B`, comparing `'%A_B%'` with `'%A!_B%' ESCAPE '!'`.
17. **Escape character:** Describe how to search for a literal `!` when `!` is the escape character.
18. **PreparedStatement:** Write Java code building `"%" + escapedInput + "%"` and binding the parameter safely.
19. **SQL injection:** Distinguish SQL injection from wildcard injection in `LIKE`.
20. **SIMILAR TO:** Find titles starting with `PostgreSQL` or `MySQL`.
21. **Regex:** Find titles starting with `PostgreSQL` using `~ '^PostgreSQL'`.
22. **Case-insensitive regex:** Convert the example above to `~*`.
23. **Anchors:** Explain the difference between `~ 'SQL'` and `~ '^SQL$'`.
24. **Validation regex:** Validate sample code `AB-1234` using `^[A-Z]{2}-[0-9]{4}$`.
25. **Regex safety:** List three risks of allowing arbitrary regex input from clients.
26. **pg_trgm:** Create the extension on a permitted test database and a GIN `gin_trgm_ops` index on `title`.
27. **Short trigrams:** Why is `ILIKE '%a%'` difficult to speed up with a trigram index?
28. **GIN vs GiST trigram:** State situations to consider each method based on operator/workload.
29. **Similarity:** Use `similarity` with input `Postgres` and explain how it differs from contains.
30. **FTS lexemes:** Run `to_tsvector('simple', ...)` and observe lexemes/positions.
31. **Language config:** Compare `simple` vs `english` for `Running runners run`; why shouldn't `english` be used by default for Vietnamese content?
32. **plainto_tsquery:** Use input `PostgreSQL JDBC` and explain the `AND` semantics.
33. **FTS search:** Query `search_vector @@ plainto_tsquery('simple','PostgreSQL')`.
34. **Title vs body:** Find a document that matches FTS via `body` even though `title` does not contain the term.
35. **Distinguishing summary:** Why might a document mentioning the keyword only in `summary` not match the vector in the lab?
36. **Phrase:** Use `phraseto_tsquery('simple', 'Java JDBC')` and compare with `plainto_tsquery`.
37. **Web search syntax:** Test `'"Java JDBC" OR PostgreSQL -MySQL'` with `websearch_to_tsquery`.
38. **Strict tsquery:** Write `postgresql & (jdbc | sql)` using `to_tsquery`.
39. **Prefix lexeme:** Use `postgr:*` and explain why it is not a title-prefix.
40. **FTS vs substring:** Run `to_tsvector('simple','PostgreSQL') @@ plainto_tsquery('simple','sql')` and `'PostgreSQL' ILIKE '%sql%'`.
41. **GIN FTS:** Create an index on generated `search_vector` and measure with `EXPLAIN`.
42. **Ranking:** Sort by `ts_rank(search_vector,q) DESC` and add a `document_id` tie-breaker.
43. **Weights:** Explain title weight `A` and body weight `B` in the lab schema.
44. **ts_rank_cd:** Compare rank results with `ts_rank` and explain the meaning of cover density.
45. **Highlight:** Use `ts_headline` on `body` and explain how to prevent HTML injection/XSS.
46. **Generated vector:** `UPDATE` a `body` in the lab and verify `search_vector` changes; explain write overhead.
47. **Large load:** Insert 100,000 more documents in the lab, `ANALYZE`, and measure B-tree/trigram/FTS.
48. **Index choice:** Build a table selecting indexes for exact, prefix, contains, and FTS.
49. **EXPLAIN:** Read `Index Cond`, `Filter`, `Bitmap Heap Scan`, rows, and buffers if present.
50. **Statistics:** Why might a 24-row table use `Seq Scan` even when an index exists?
51. **Short keywords:** Design UX for a single-character `contains` query.
52. **Accented data:** Explain why `toi uu` does not match `tối ưu` by default.
53. **unaccent:** State the benefits and why you should not hastily mark an `unaccent` wrapper `IMMUTABLE` in an expression index.
54. **Synonyms:** Design a way to make `CSDL` match `cơ sở dữ liệu`.
55. **Vietnamese:** Explain the limitation with compound words under the `simple` configuration.
56. **Mixed languages:** Propose how to manage FTS configurations if documents mix Vietnamese and English.
57. **Empty query:** Use `numnode` to detect a query consisting solely of stop words in the `english` config.
58. **Category filter:** Combine `category='database'` with FTS instead of putting category into query text.
59. **Partial index:** State when a partial FTS index for published documents can be useful.
60. **Search API:** Sketch `EXACT`/`PREFIX`/`CONTAINS`/`FULL_TEXT` modes and their SQL mappings.
61. **Pagination:** Why does `ORDER BY rank` need a tie-breaker and why is deep `OFFSET` still expensive?
62. **Keyset ranking:** State the risks when a cursor includes a floating-point rank while data is changing.
63. **Auth:** Design a tenant-scoped search query without leaking documents from other tenants.
64. **Performance:** Measure SELECT latency, GIN size, UPDATE overhead, and request P95.
65. **Equivalence:** Given one input, demonstrate that exact/prefix/contains/FTS can return four different result sets.
66. **Comprehensive design:** An app has SKU search, title autocomplete, and article body search; choose the three query patterns, indexes, normalization, timeouts, and tests.

## 47. Search Design Review Checklist

A proposal:

```sql
SELECT *
FROM documents
WHERE title ILIKE '%' || :q || '%';
```

should be reviewed with the following questions:

1. **What is the search requirement?** True substring matching or whole-word matching?
2. **Is `SELECT *` needed?** Are there very long TEXT/JSONB columns?
3. **Can clients enter `%`/`_`?** Are wildcards escaped when literal matching is intended?
4. **Are parameters bound properly?** No concatenating raw user input into SQL text?
5. **What is the minimum search term length?** Will a single character produce too many matches?
6. **Have collation/case/accent semantics been confirmed?**
7. **Is ranking needed?** If so, `ILIKE` does not naturally produce good relevance scores.
8. **Can a B-tree prefix be used?** If the UI only searches the beginning of the title, why add a leading `%`?
9. **If substring is needed, is `pg_trgm` suitable?** Has it been measured and is the extension permitted?
10. **If multi-word content is needed, is FTS the right semantics?**
11. **For Vietnamese data, do tokenization/accent-insensitive handling meet requirements?**
12. **Does the planner use the index on real queries?** Generic vs custom plans?
13. **Do common keywords cause scanning/ranking too many candidates?**
14. **Are tenant/permission filters, limits, and timeouts in place?**
15. **Are there tests for case, diacritics, wildcards, phrases, and empty keywords?**
16. **Have write overhead, storage, and index maintainability been measured?**

An implementation that merely "has a working SELECT" is not enough to prove the search feature is accurate and operationally sustainable.

## 48. Summary

Core differences:

```text
EXACT SEARCH
  title = 'PostgreSQL'
  -> Compares the entire value
  -> B-tree is usually suitable

PREFIX SEARCH
  title LIKE 'PostgreSQL%'
  -> Starts with a fixed string
  -> B-tree / text_pattern_ops / lower expression

PATTERN / SUBSTRING SEARCH
  title ILIKE '%postgresql%'
  title ~* '^postgresql'
  -> Character-level matching via wildcards/regex
  -> Prefix B-tree does not solve all patterns
  -> pg_trgm is useful for many substring/pattern workloads

FULL-TEXT SEARCH
  search_vector @@ plainto_tsquery('simple', 'PostgreSQL')
  -> Token/lexeme search over indexed fields
  -> GIN tsvector, tsquery, ranking/phrase/lexeme prefix
  -> Not synonymous with arbitrary character substring matching
```

Most important principles:

- **Choose semantics first, indexes second.** A LIKE substring is not automatically equivalent to searching words in content.
- **`=` compares the full value; `LIKE 'abc%'` is prefix; `LIKE '%abc%'` is contains.** The position of `%` strongly dictates meaning and B-tree usability.
- **`%` and `_` are LIKE wildcards.** If users enter them as literal data, escape them even when binding SQL parameters.
- **`ILIKE` handles case-insensitive patterns per applicable rules, not Vietnamese accent-insensitivity automatically.**
- **B-tree/`text_pattern_ops` fit equality/prefix; `pg_trgm` fits many substring/pattern searches; GIN `tsvector` is for FTS `@@`.** Do not assume these indexes are interchangeable.
- **FTS searches lexemes, not arbitrary character slices.** Use `plainto_tsquery` for plain text, `phraseto_tsquery` for phrases, `websearch_to_tsquery` for web-search syntax, and `to_tsquery` for controlled expressions.
- **Generated `tsvector` and GIN enable full-text queries at scale**, but add CPU/storage/maintenance overhead on writes. GIN also does not sort by relevance on its own.
- **Vietnamese requires explicit policies for diacritics, word segmentation, abbreviations, and synonyms.** The `simple` configuration is helpful in the lab but does not guarantee production linguistic quality.
- **Use `EXPLAIN (ANALYZE, BUFFERS)` on real queries** to decide on indexes and track write cost, payload width, candidate counts, and latency.
- **Keep search endpoints safe:** bind parameters, validate pattern/query complexity, filter access permissions, cap page sizes, set timeouts, and sanitize highlighted output.

When you clearly distinguish **exact match, starts-with, character pattern match, and lexeme search**, you will choose the right SQL, indexes, and search experience for PostgreSQL—not merely "finding a few rows", but returning **the right set of documents, with the right relevance, at the right operational cost**.
