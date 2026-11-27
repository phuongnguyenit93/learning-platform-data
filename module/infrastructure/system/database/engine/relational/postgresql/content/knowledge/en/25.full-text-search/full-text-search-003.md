# tsvector, tsquery, and the Full-Text Search Processing Pipeline

When users type "tối ưu truy vấn PostgreSQL" into a search box, they want to see lessons with **relevant content**, not just rows containing an exact character substring. They also need to filter documents by organization and access permissions, search phrases, rank results, display snippets, and return results quickly on large datasets.

PostgreSQL supports **Full-Text Search (FTS)** directly inside the relational database. The two core data types are:

- **`tsvector`**: represents text as **lexemes** (lexical units after analysis/normalization), optionally carrying positions and weights.
- **`tsquery`**: represents a search condition over lexemes using AND, OR, NOT, phrase, proximity, and prefix operators.

The **`@@`** operator checks whether a vector matches a query. However, a real-world search system also needs language analysis, GIN indexes, ranking, snippets, pagination, SQL injection prevention, access control, and a consistent mechanism to keep vectors up to date.

> **Environment:** This lesson uses modern PostgreSQL; certain features like JSONPath have version constraints but are not the focus here. Vietnamese examples use `pg_catalog.simple` for illustration; this configuration is **not a complete Vietnamese word segmenter or stemmer**. Tokenization, ranking, and plan outputs can vary by configuration, data, and version. Run table/index DDL in a practice database.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain the pipeline **source text → parser/dictionary → tsvector → GIN → tsquery → @@ → rank → snippet**.
2. Distinguish full-text search from `LIKE`, `ILIKE`, trigrams, and semantic search.
3. Use `to_tsvector`, `ts_debug`, `setweight`, `plainto_tsquery`, `phraseto_tsquery`, `websearch_to_tsquery`, and `to_tsquery`.
4. Write `@@` conditions combined with tenant, status, time, and access-control filters.
5. Create a **stored generated `tsvector` column** and a GIN index with the proper configuration.
6. Rank with `ts_rank`/`ts_rank_cd` and display results safely with `ts_headline`.
7. Understand phrase search, prefixes, stop words, synonyms, and limitations with Vietnamese.
8. Choose among generated columns, expression indexes, triggers, or search projection tables.
9. Read `EXPLAIN (ANALYZE, BUFFERS)`, benchmark, and diagnose missing-result or slow-query cases.
10. Integrate Java/JDBC/Spring without string-concatenating SQL or leaking unauthorized documents.

## 2. How Does Full-Text Search Differ from LIKE?

The query:

```sql
SELECT *
FROM articles
WHERE body ILIKE '%index%';
```

is a **substring** search, not a lexical-unit search. It is useful when character matching is needed, but it does not perform stemming, stop-word removal, title/body weighting, or document ranking.

With FTS:

```sql
SELECT *
FROM articles
WHERE search_vector @@
      plainto_tsquery('pg_catalog.simple', 'postgresql index');
```

`search_vector` is assumed to be a prebuilt `tsvector` column. Keywords are converted into a `tsquery`, then the engine evaluates lexemes and can leverage a GIN index.

### FTS is not fuzzy or semantic search

- **FTS**: matches lexical terms, dictionaries, phrases, weights.
- **`LIKE`/`ILIKE`**: matches strings by pattern.
- **`pg_trgm`**: can support character similarity, substrings, and character-level typos.
- **Semantic/vector search**: relies on semantic representations/embeddings if implemented by the system.

A solution may combine these layers. Do not expect `to_tsvector` to infer distant meanings, out-of-dictionary synonyms, or arbitrary spelling mistakes.

## 3. Search Pipeline Diagram

```text
                Source: title / summary / body
                              │
                              ▼
                   Text search configuration
                        parser + dictionary
                              │
                              ▼
                           tsvector
                     lexeme, position, weight
                              │
                              ▼
                           GIN index
                              │
User input ──► query constructor ──► tsquery
                              │
                              ▼
                      @@ find candidates
                              │
                 tenant / status / ACL filter
                              │
                              ▼
                    ts_rank / ts_rank_cd
                              │
                              ▼
                 sort + LIMIT + ts_headline
                              │
                              ▼
                       API search result
```

Most importantly, **document analysis and search query analysis must use consistent configurations**. If vectors are built with `english` while queries are parsed with `simple`, the two sides may produce different lexemes.

## 4. Parser, Tokens, Dictionaries, and Lexemes

| Concept | Role | Example |
|---|---|---|
| Document | Input text | "The runners are running" |
| Parser | Identifies token types | Word, number, email, URL |
| Token | Unit split by the parser | "running" |
| Dictionary | Normalizes/removes tokens | Stemming or stop word |
| Lexeme | Stored/queried unit | "run" in English config |
| Text search configuration | Maps token types to parser/dictionaries | `simple`, `english` |
| `tsvector` | Indexed lexemes of a document | `'run':...` |
| `tsquery` | Expression testing lexemes | `'run' & 'index'` |

Example:

```sql
SELECT
    to_tsvector(
        'pg_catalog.simple'::regconfig,
        'running runs'
    ) AS simple_vector,
    to_tsvector(
        'pg_catalog.english'::regconfig,
        'running runs'
    ) AS english_vector;
```

With `simple`, words generally retain a near-original form; with `english`, stemming can collapse them to a common lexeme. Never guess what form a word stems to without checking the server configuration.

## 5. Choosing a Text Search Configuration

Inspect:

```sql
SHOW default_text_search_config;

SELECT current_setting('default_text_search_config');
```

Two common choices:

- `pg_catalog.simple`: simple configuration, suitable for learning and corpora that do not need specialized stemming.
- `pg_catalog.english`: English analysis with stop words and stemming.

Always **specify the config explicitly**:

```sql
SELECT to_tsvector(
    'pg_catalog.simple'::regconfig,
    'Tìm kiếm toàn văn trong PostgreSQL'
);
```

Relying on `default_text_search_config` in index/generation expressions easily causes inconsistencies across sessions or environments. For expression indexes and stored generated columns, the `to_tsvector(regconfig, text)` form with an explicit configuration also satisfies the immutability/determinism requirements of the expression.

## 6. Inspecting a String with ts_debug

```sql
SELECT *
FROM ts_debug(
    'pg_catalog.english'::regconfig,
    'The runners are running through indexes'
);
```

`ts_debug` shows:

- The recognized token.
- The token type/alias.
- Which dictionary was tried.
- The resulting lexeme, or whether it was discarded.

This is the first diagnostic tool when a word appears in a document yet searches fail to find it.

### Stop words

Words such as `the`, `and`, and `of` may be discarded in the `english` configuration. In other configurations, they may be kept. Do not confuse **stop words** with terms blocked by access permissions; those are two independent layers of logic.

## 7. tsvector Stores Lexemes and Positions

```sql
SELECT to_tsvector(
    'pg_catalog.simple'::regconfig,
    'PostgreSQL database PostgreSQL indexing'
) AS document_vector;
```

The representation looks like:

```text
'database':2 'indexing':4 'postgresql':1,3
```

The numbers after the colon indicate where each lexeme appeared in the parsed string. A lexeme can appear at multiple positions.

### Do not use tsvector to reconstruct the original text

A vector does not preserve formatting, punctuation, all stop words, or original casing/spelling. Always keep the original `title`/`body` columns for display, auditing, and `ts_headline`.

### Why do positions matter?

Positions enable phrase queries and allow certain ranking functions to consider proximity between lexemes. `ts_rank_cd` in particular relies on positional information; stripping positions can strongly alter results.

## 8. Weights A, B, C, D Across Multiple Fields

A word in a **title** is usually more important than the same word buried deep in the **body**. PostgreSQL lets you assign weights:

- `A`: highest priority (e.g., title).
- `B`: next priority (summary).
- `C`: another intermediate group.
- `D`: default (body).

```sql
SELECT
    setweight(
        to_tsvector('pg_catalog.simple', 'GIN index PostgreSQL'),
        'A'
    )
    ||
    setweight(
        to_tsvector(
            'pg_catalog.simple',
            'Tìm kiếm toàn văn dùng chỉ mục GIN'
        ),
        'D'
    ) AS weighted_vector;
```

`||` concatenates two vectors, shifting positions appropriately. Assign weights **before** concatenating if you want to distinguish fields.

### Not an absolute relevance score

Weight A does not automatically guarantee every title match ranks above every body match. Results also depend on the ranking function, term frequency, positions, and normalization.

## 9. tsquery: Core Operators

| Operator | Meaning | Example |
|---|---|---|
| `&` | AND | `postgresql & index` |
| `\|` | OR | `postgresql \| mysql` |
| `!` | NOT | `postgresql & !mysql` |
| `<->` | Adjacent lexemes | `postgresql <-> index` |
| `<N>` | Specific positional distance | `postgresql <2> index` |
| `:*` | Lexeme prefix | `postgres:*` |

Examples:

```sql
SELECT to_tsquery(
    'pg_catalog.simple',
    'postgresql & index'
);

SELECT to_tsquery(
    'pg_catalog.simple',
    'postgresql | mysql'
);

SELECT to_tsquery(
    'pg_catalog.simple',
    'postgresql & !mysql'
);
```

`to_tsquery` expects an expression following its specific syntax, not an arbitrary natural sentence. Unpaired operator characters or syntax errors can raise an exception.

## 10. Four Ways to Construct a tsquery

| Function | How It Interprets Input | When to Use |
|---|---|---|
| `plainto_tsquery` | Plain text, lexemes typically joined with AND | Simple search boxes |
| `phraseto_tsquery` | Positional/phrase relationship, accounting for stopword gaps | Searching a phrase |
| `websearch_to_tsquery` | Web-style syntax: quotes, OR, minus sign | Public search boxes |
| `to_tsquery` | Query expression with AND/OR/NOT/prefix/weights | Controlled advanced search |

```sql
SELECT
    plainto_tsquery(
        'pg_catalog.simple',
        'PostgreSQL index'
    ) AS plain_q,
    phraseto_tsquery(
        'pg_catalog.simple',
        'PostgreSQL index'
    ) AS phrase_q,
    websearch_to_tsquery(
        'pg_catalog.simple',
        '"PostgreSQL index" OR tuning'
    ) AS web_q;
```

### Usage rule

For free-form user input, usually prefer `plainto_tsquery` or `websearch_to_tsquery`. `to_tsquery` is better suited when **the system builds components programmatically** and validates syntax.

## 11. Phrase Search and Positions

```sql
SELECT
    to_tsvector(
        'pg_catalog.simple',
        'Hướng dẫn tối ưu truy vấn PostgreSQL'
    )
    @@
    phraseto_tsquery(
        'pg_catalog.simple',
        'tối ưu truy vấn'
    ) AS phrase_match;
```

If the lexemes appear consecutively in the exact order, the query matches. `phraseto_tsquery` understands positional gaps when stop words are removed, unlike manually joining with `<->` based on whitespace.

**Phrase matching is not exact substring matching:** tokenization, punctuation, stemming, and stop words can make two different strings yield the same lexeme sequence, or vice versa.

If the product requires exact verbatim character sequences, consider `LIKE`/`ILIKE` or `pg_trgm` alongside FTS.

## 12. Prefix Search Does Not Fix Typos

```sql
SELECT to_tsquery(
    'pg_catalog.simple',
    'postgres:*'
);
```

`:*` is **prefix search** on a lexeme, not:

- Substring search in the middle of a word.
- Edit distance or fuzzy matching.
- A spell-check suggester.
- A synonym engine.

Very short prefix queries can produce huge result sets; enforce input/prefix length limits for practical UX.

## 13. Negated Queries and Overly Broad Queries

```sql
SELECT to_tsquery(
    'pg_catalog.simple',
    'postgresql & !mysql'
);
```

requires `postgresql` to appear while `mysql` does not.

Conversely, using only:

```sql
SELECT to_tsquery('pg_catalog.simple', '!mysql');
```

has no positive lexeme for a selective index lookup, which can cause heavy work.

`querytree` lets you inspect the index-usable portion:

```sql
SELECT querytree(
    to_tsquery(
        'pg_catalog.simple',
        'postgresql & !mysql'
    )
);
```

Do not treat `querytree` as a guarantee that the planner will pick an index or as the full cost evaluation.

## 14. Handling Empty or Stop-Word-Only Input

```sql
SELECT numnode(
    plainto_tsquery(
        'pg_catalog.english',
        'the and of'
    )
) AS number_of_nodes;
```

An English query containing only stop words may leave zero useful lexemes. The application needs a policy:

- Prompt the user to enter meaningful keywords.
- Return an empty list with a clear message.
- Allow a controlled alternative search mode.

**Do not automatically turn an empty query into a query returning all rows** unless business logic explicitly intends that.

## 15. SQL Lab: Setting Up the Schema

```sql
CREATE SCHEMA IF NOT EXISTS lesson_fts;
```

A multi-tenant articles table:

```sql
CREATE TABLE lesson_fts.articles (
    article_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    slug TEXT NOT NULL,
    title TEXT NOT NULL,
    summary TEXT,
    body TEXT NOT NULL,
    language_code TEXT NOT NULL DEFAULT 'vi'
        CHECK (language_code IN ('vi','en')),
    status TEXT NOT NULL DEFAULT 'PUBLISHED'
        CHECK (status IN ('DRAFT','PUBLISHED')),
    published_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    search_vector TSVECTOR GENERATED ALWAYS AS (
        setweight(
            to_tsvector(
                'pg_catalog.simple'::regconfig,
                title
            ),
            'A'
        )
        ||
        setweight(
            to_tsvector(
                'pg_catalog.simple'::regconfig,
                COALESCE(summary, '')
            ),
            'B'
        )
        ||
        setweight(
            to_tsvector(
                'pg_catalog.simple'::regconfig,
                body
            ),
            'D'
        )
    ) STORED,
    CONSTRAINT uq_articles_tenant_slug
        UNIQUE (tenant_id, slug)
);
```

### Why use STORED GENERATED?

On INSERT/UPDATE of `title`, `summary`, or `body`, PostgreSQL automatically recomputes the vector from the expression. The application does not need to manually maintain a separate text search vector column.

The `simple` config is fixed for **both `vi` and `en` in the lab** to stay focused on the mechanism. The `language_code` column is just metadata in this example and does not yet select a per-row analyzer.

## 16. Sample Data

```sql
INSERT INTO lesson_fts.articles (
    tenant_id, slug, title, summary, body,
    language_code, status, published_at
)
VALUES
    (
      10, 'postgres-index',
      'Chỉ mục PostgreSQL',
      'Hướng dẫn tạo và chọn chỉ mục',
      'PostgreSQL hỗ trợ B-tree và GIN index. Chỉ mục giúp truy vấn lọc dữ liệu hiệu quả.',
      'vi', 'PUBLISHED',
      TIMESTAMPTZ '2026-10-01 09:00:00+07'
    ),
    (
      10, 'query-tuning',
      'Tối ưu truy vấn PostgreSQL',
      'Đọc EXPLAIN ANALYZE và đánh giá index',
      'Tối ưu truy vấn cần xem thống kê, chỉ mục, bộ nhớ và thời gian thực thi.',
      'vi', 'PUBLISHED',
      TIMESTAMPTZ '2026-10-02 09:00:00+07'
    ),
    (
      10, 'row-locks',
      'Giao dịch và khóa hàng',
      'Phân tích blocking và deadlock',
      'PostgreSQL sử dụng MVCC và các loại khóa để điều phối giao dịch đồng thời.',
      'vi', 'PUBLISHED',
      TIMESTAMPTZ '2026-10-03 09:00:00+07'
    ),
    (
      10, 'gin-fts',
      'GIN index cho tìm kiếm toàn văn',
      'Sử dụng tsvector, tsquery và toán tử đối sánh',
      'Tìm kiếm toàn văn dùng text search configuration và chỉ mục GIN trên tsvector.',
      'vi', 'PUBLISHED',
      TIMESTAMPTZ '2026-10-04 09:00:00+07'
    ),
    (
      10, 'english-search',
      'PostgreSQL full text search',
      'Ranking and phrase search',
      'English searching uses lexemes, stemming, dictionaries and ranking.',
      'en', 'PUBLISHED',
      TIMESTAMPTZ '2026-10-05 09:00:00+07'
    ),
    (
      10, 'vietnamese-search',
      'Tìm kiếm toàn văn tiếng Việt',
      'Tách từ và cấu hình từ điển tiếng Việt',
      'Tìm kiếm tiếng Việt cần quan tâm đến dấu, từ ghép và cấu hình phân tích văn bản.',
      'vi', 'PUBLISHED',
      TIMESTAMPTZ '2026-10-06 09:00:00+07'
    ),
    (
      20, 'postgres-index',
      'PostgreSQL index của tenant 20',
      'Một tài liệu thuộc tổ chức khác',
      'Bài này có cùng từ khóa nhưng không thuộc tenant 10.',
      'vi', 'PUBLISHED',
      TIMESTAMPTZ '2026-10-07 09:00:00+07'
    ),
    (
      10, 'draft-fts',
      'Tối ưu chỉ mục chưa xuất bản',
      'Bản nháp dành cho biên tập viên',
      'Bản nháp nói về PostgreSQL và tối ưu truy vấn.',
      'vi', 'DRAFT',
      TIMESTAMPTZ '2026-10-08 09:00:00+07'
    );
```

Two tenants can share the same slug because `UNIQUE(tenant_id, slug)` only enforces uniqueness per pair. You must apply the proper tenant filter when searching.

## 17. GIN Index and B-tree Index

```sql
CREATE INDEX ix_articles_fts_gin
ON lesson_fts.articles
USING GIN (search_vector);

CREATE INDEX ix_articles_tenant_status_time
ON lesson_fts.articles (
    tenant_id,
    status,
    published_at DESC,
    article_id DESC
);

ANALYZE lesson_fts.articles;
```

**GIN(`search_vector`)** looks up documents by lexemes. **B-tree** filters tenant/status and can support chronological ordering. The planner may choose an index, bitmap combination, or `Seq Scan` depending on statistics and cost.

With an eight-row table, seeing `Seq Scan` is normal; do not force indexes just to make `EXPLAIN` show a node named `Index Scan`.

## 18. Basic Query with @@

```sql
SELECT
    article_id, slug, title
FROM lesson_fts.articles
WHERE tenant_id = 10
  AND status = 'PUBLISHED'
  AND search_vector @@ plainto_tsquery(
      'pg_catalog.simple',
      'postgresql'
  )
ORDER BY article_id;
```

`@@` is the FTS match operator. It does not enforce tenant or publish-status rules by itself; those relational predicates must remain explicit.

### Combining multiple words

```sql
SELECT article_id, title
FROM lesson_fts.articles
WHERE tenant_id = 10
  AND status = 'PUBLISHED'
  AND search_vector @@ plainto_tsquery(
      'pg_catalog.simple',
      'postgresql index'
  );
```

With `plainto_tsquery`, lexemes are typically combined with AND: both must appear in the vector, not necessarily next to each other.

## 19. Reusing the Query Constructor via a CTE

```sql
WITH input_query AS (
    SELECT websearch_to_tsquery(
        'pg_catalog.simple',
        'postgresql index'
    ) AS q
)
SELECT
    a.article_id,
    a.title
FROM lesson_fts.articles AS a
CROSS JOIN input_query AS i
WHERE a.tenant_id = 10
  AND a.status = 'PUBLISHED'
  AND a.search_vector @@ i.q
ORDER BY a.article_id;
```

A CTE cleanly defines a single query used for filtering, ranking, and snippets. It is not guaranteed to be materialized; the planner may inline it depending on conditions and version.

## 20. Ranking with ts_rank

```sql
WITH q AS (
    SELECT plainto_tsquery(
        'pg_catalog.simple',
        'postgresql index'
    ) AS search
)
SELECT
    a.article_id,
    a.title,
    ts_rank(a.search_vector, q.search) AS rank_score
FROM lesson_fts.articles AS a
CROSS JOIN q
WHERE a.tenant_id = 10
  AND a.status = 'PUBLISHED'
  AND a.search_vector @@ q.search
ORDER BY
    rank_score DESC,
    a.published_at DESC,
    a.article_id DESC;
```

A rank score is a **formula-based relevance score**, not a 90% probability that the document is right. It is affected by title/summary/body weights, term frequency and positions, and normalization.

### Why is SORT still needed?

GIN finds matching candidates rather than automatically returning results ordered by `ts_rank(search_vector, q)` for arbitrary dynamic queries. Thus `ORDER BY rank_score DESC` can require processing and sorting the candidates.

## 21. ts_rank_cd and Cover Density

```sql
WITH q AS (
    SELECT plainto_tsquery(
        'pg_catalog.simple',
        'postgresql index'
    ) AS search
)
SELECT
    title,
    ts_rank(search_vector, q.search) AS score_basic,
    ts_rank_cd(search_vector, q.search) AS score_cover_density
FROM lesson_fts.articles
CROSS JOIN q
WHERE tenant_id = 10
  AND status = 'PUBLISHED'
  AND search_vector @@ q.search
ORDER BY score_cover_density DESC, title;
```

`ts_rank_cd` evaluates matching spans/positions differently from `ts_rank`. If a vector lacks useful positions, results may not reflect proximity as expected.

There is no single default ranking function that is best for every domain. Evaluate with a test query suite and product relevance labels.

## 22. Normalization and Weight Ordering

`ts_rank`/`ts_rank_cd` provide overloads accepting weights and normalization flags. Example:

```sql
WITH q AS (
    SELECT plainto_tsquery(
        'pg_catalog.simple',
        'postgresql'
    ) AS search
)
SELECT
    title,
    ts_rank(search_vector, q.search, 32) AS normalized_score
FROM lesson_fts.articles
CROSS JOIN q
WHERE search_vector @@ q.search
  AND tenant_id = 10
  AND status = 'PUBLISHED'
ORDER BY normalized_score DESC, article_id;
```

Normalization `32` is a PostgreSQL-defined flag; it does not turn rank into a calibrated "quality" probability.

When passing a weight array to ranking functions, the order is **`{D,C,B,A}`**, not A,B,C,D. This is easy to get backwards when tuning title vs body priority.

## 23. Snippets with ts_headline

```sql
WITH q AS (
    SELECT websearch_to_tsquery(
        'pg_catalog.simple',
        'postgresql index'
    ) AS search
)
SELECT
    a.title,
    ts_headline(
        'pg_catalog.simple',
        a.body,
        q.search,
        'StartSel=**, StopSel=**, MaxWords=20, MinWords=5'
    ) AS snippet
FROM lesson_fts.articles AS a
CROSS JOIN q
WHERE a.tenant_id = 10
  AND a.status = 'PUBLISHED'
  AND a.search_vector @@ q.search;
```

`ts_headline` selects and marks a passage containing matched terms. To avoid wasting CPU, usually invoke it only for the **final displayed results**.

### HTML/XSS warning

`ts_headline` **is not an HTML sanitizer**. If `body` is user-supplied, escape content and construct highlight markup safely in the UI; never treat output with `StartSel=<b>` as proof that the HTML is clean.

## 24. A Filter, Rank, Limit, and Snippet Pipeline

```sql
WITH input_query AS (
    SELECT websearch_to_tsquery(
        'pg_catalog.simple',
        'postgresql index'
    ) AS q
),
ranked AS (
    SELECT
        a.article_id,
        a.slug,
        a.title,
        a.body,
        a.published_at,
        ts_rank(a.search_vector, i.q) AS score
    FROM lesson_fts.articles AS a
    CROSS JOIN input_query AS i
    WHERE a.tenant_id = 10
      AND a.status = 'PUBLISHED'
      AND a.search_vector @@ i.q
    ORDER BY
        score DESC,
        a.published_at DESC,
        a.article_id DESC
    LIMIT 10
)
SELECT
    r.article_id,
    r.slug,
    r.title,
    r.score,
    ts_headline(
        'pg_catalog.simple',
        r.body,
        (SELECT q FROM input_query),
        'StartSel=**, StopSel=**, MaxWords=18'
    ) AS snippet
FROM ranked AS r
ORDER BY r.score DESC, r.published_at DESC, r.article_id DESC;
```

### Notes

- Never drop tenant/visibility filters when building the query.
- Include a tie-breaker so ordering is deterministic when ranks tie.
- `LIMIT` applies to the matched/ranked set; it does not implicitly cap how many documents GIN must evaluate.
- In real systems, combine per-user/ACL authorization, not just tenant and status.

## 25. When Text Is Updated, How Is the Vector Synchronized?

```sql
INSERT INTO lesson_fts.articles (
    tenant_id, slug, title, summary, body, status
)
VALUES (
    10,
    'window-functions',
    'Window functions trong PostgreSQL',
    'ROW_NUMBER và PARTITION BY',
    'Hướng dẫn sử dụng hàm cửa sổ khi truy vấn dữ liệu.',
    'PUBLISHED'
);

UPDATE lesson_fts.articles
SET title = 'Window functions và tối ưu truy vấn'
WHERE tenant_id = 10
  AND slug = 'window-functions';
```

Because `search_vector` is a stored generated column, PostgreSQL recomputes it from `title`/`summary`/`body` per the expression when the row changes and maintains the associated index.

### Cost

Generating vectors and updating a GIN index consumes CPU, WAL, and storage. For occasionally edited documents, this consistency is worth it. For continuously mutating content, evaluate write amplification.

## 26. Another Approach: Expression GIN Index

Not every case needs a stored `tsvector` column:

```sql
CREATE INDEX ix_articles_title_fts_expr
ON lesson_fts.articles
USING GIN (
    to_tsvector(
        'pg_catalog.simple'::regconfig,
        title
    )
);
```

Matching query:

```sql
SELECT article_id, title
FROM lesson_fts.articles
WHERE to_tsvector(
          'pg_catalog.simple'::regconfig,
          title
      ) @@ plainto_tsquery(
          'pg_catalog.simple',
          'postgresql'
      );
```

### Comparison

| Design | Benefits | Trade-offs |
|---|---|---|
| Stored generated `search_vector` + GIN | Vector available for ranking and multi-field queries | Stores vector, recomputed on write |
| Expression GIN on `to_tsvector(...)` | No separate vector column needed | Query must match expression; recomputes vector for ranking if needed |
| Trigger-maintained `tsvector` column | Custom update logic | Creates backfill and sync obligations |
| Separate search projection | Aggregates across multiple tables/document types | Must manage lag, deletes, auth, and rebuilds |

The lab already has a GIN index on the full vector; a title-only index serves a different purpose. Do not keep redundant indexes just because examples show multiple options.

## 27. Why Must the Config Be Specified in an Index Expression?

`to_tsvector(text)` uses the session's `default_text_search_config`; that is not immutable across environments.

With the index:

```sql
CREATE INDEX ix_articles_body_fts_expr
ON lesson_fts.articles
USING GIN (
    to_tsvector(
        'pg_catalog.simple'::regconfig,
        body
    )
);
```

the configuration is fixed in the index definition. If a query uses a different config, the planner cannot assume the indexed vector carries the same lexemes or equivalent expression.

**Do not change the default config in the connection pool and expect already-indexed documents to re-analyze automatically.**

## 28. GIN and GiST

Two index methods commonly mentioned for PostgreSQL FTS:

- **GIN**: inverted index for lexemes, usually the primary choice for FTS.
- **GiST**: different trade-offs in structure/signatures/rechecks, useful in certain workloads.

Alternative GiST example:

```sql
CREATE INDEX ix_articles_fts_gist
ON lesson_fts.articles
USING GiST (search_vector);
```

The lab already uses GIN; do not keep both without a specific benchmark or requirement.

### What GIN does not do by itself

GIN does not sort by rank, generate snippets, fix typos or understand synonyms, enforce tenant/ACL policies, or force every query to use an index.

## 29. Partial GIN Index

If most queries only search published articles:

```sql
CREATE INDEX ix_articles_published_fts
ON lesson_fts.articles
USING GIN (search_vector)
WHERE status = 'PUBLISHED';
```

The predicate limits which documents enter the index. However, the planner must prove the query implies the predicate; a prepared statement with `status = $1` and a generic plan will not always use a partial index.

Do not use current-time predicates like `published_at < now()` to build a "self-updating over time" index; index predicates require immutability and do not update as the clock advances.

## 30. Full-Text Search Combined with Structured Filters

A lesson search API might need:

```sql
SELECT article_id, title
FROM lesson_fts.articles
WHERE tenant_id = 10
  AND status = 'PUBLISHED'
  AND published_at >=
      TIMESTAMPTZ '2026-10-01 00:00:00+07'
  AND search_vector @@ websearch_to_tsquery(
      'pg_catalog.simple',
      'postgresql index'
  );
```

FTS handles lexemes. B-tree/typed columns handle tenant, status, timestamps, prices, codes, and foreign keys. Do not turn exact structured filters into a text string and search them via FTS.

### Security boundary

A `tenant_id` received from a request **does not prove the user is authorized to view that tenant**. The backend must enforce authorization/RLS from a trusted authority even when the FTS query matches accurately.

## 31. Reading an FTS Execution Plan

```sql
EXPLAIN (
    ANALYZE,
    BUFFERS,
    SETTINGS
)
SELECT
    article_id,
    title
FROM lesson_fts.articles
WHERE tenant_id = 10
  AND status = 'PUBLISHED'
  AND search_vector @@ websearch_to_tsquery(
      'pg_catalog.simple',
      'postgresql index'
  );
```

On a large corpus with a selective query, you might see a structure like:

```text
Bitmap Heap Scan on articles
  Recheck Cond: (search_vector @@ ...)
  Filter: (...)
  Buffers: shared hit=... read=...
  -> Bitmap Index Scan on ix_articles_fts_gin
       Index Cond: (search_vector @@ ...)
```

This is illustrative output, not measured output from the eight-row table.

### Fields to analyze

- **Index Cond**: Is FTS using the index lookup?
- **Recheck Cond**: Are candidate rows re-verified?
- **Actual Rows / Plan Rows**: How many matches did the planner estimate vs actual?
- **Rows Removed by Filter**: How many rows were discarded by conditions not pushed into the index?
- **Buffers**: Were many data/index pages read?
- **Execution Time**: Runtime for the execution.
- **Sort**: Is sorting by rank needed, and did it spill to temporary files?

Do not conclude "the index is ineffective" just because `Seq Scan` appears on a tiny dataset or an overly common keyword.

## 32. Evaluating Selectivity and Common Keywords

The word `postgresql` may appear in nearly every article in a PostgreSQL documentation corpus. By contrast, `deadlock` might appear in only a few articles.

A query:

```sql
search_vector @@ plainto_tsquery('simple', 'postgresql')
```

will likely generate far more candidates than:

```sql
search_vector @@ plainto_tsquery('simple', 'deadlock')
```

Thus performance depends not just on the number of query lexemes, but also on **document frequency** and relational filters.

### Choosing benchmark inputs

Include at least these categories:

1. A very common word.
2. A rare word.
3. Two words joined by AND.
4. A rare phrase.
5. Multiple terms with OR.
6. Long prefix and short prefix.
7. Stop-word-only query.
8. Accented and unaccented Vietnamese input.
9. Queries on a tenant with many documents and a tenant with few documents.

Do not benchmark a single keyword and extrapolate conclusions to the entire system.

## 33. Do Not Use FTS to Replace Structured Data Filters

Suppose an e-commerce site searches for "laptop workstation" with constraints:

- Price under 40 million.
- In stock.
- Belongs to the logged-in tenant.
- Status ACTIVE.

The search part can be:

```sql
search_vector @@ websearch_to_tsquery(
    'simple',
    'laptop workstation'
)
```

However, **price** must use `NUMERIC` range comparisons, **inventory** must use quantity/warehouse constraints, **status** must use a typed column, and **tenant** must use authorization. Never cram all filters into a text string and treat lexeme matching as proof of valid structured criteria.

FTS solves **textual relevance**; relational columns and constraints solve **integrity + exact filtering**.

## 34. Search Indexing When a Document Spans Multiple Related Tables

An article has an author, category, and tags:

```text
articles(article_id, title, body, author_id)
authors(author_id, author_name)
article_tags(article_id, tag_id)
tags(tag_id, tag_name)
```

A stored generated column on `articles` cannot directly run arbitrary JOIN subqueries to other tables to pull in author names or tags. If you want to search across all those fields, decide among:

- **Option A:** Vector contains only title/body; tag/category are filtered via SQL JOIN.
- **Option B:** Maintain a denormalized keywords column, updated properly when tags change.
- **Option C:** A search projection table aggregating data from multiple tables.
- **Option D:** A dedicated external search service synchronized from PostgreSQL.

### Why must changes in related tables be accounted for?

If an author changes their name, the article's vector may still hold the old name. If a tag is removed, search results can become stale. A multi-table search design must define a **dependency graph and invalidation/re-indexing mechanism**, not just INSERT logic on `articles`.

## 35. Creating a Separate Search Projection Table

```sql
CREATE TABLE lesson_fts.search_documents (
    document_id BIGINT PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    document_type TEXT NOT NULL,
    source_id BIGINT NOT NULL,
    source_version BIGINT NOT NULL CHECK (source_version >= 0),
    title TEXT NOT NULL,
    search_vector TSVECTOR NOT NULL,
    indexed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, document_type, source_id)
);

CREATE INDEX ix_search_documents_vector
ON lesson_fts.search_documents
USING GIN (search_vector);
```

### Advantages

- Search across multiple entity types through one interface.
- Decouples search-focused storage from a highly normalized OLTP schema.
- Can combine title/body/tags/author with weights.
- Easy to rebuild the projection when changing analyzers.

### Accompanying responsibilities

- Ensure idempotent UPSERT by source key.
- Prevent stale events from overwriting newer `source_version`s.
- Sync deletions, status transitions, and ACL changes.
- Monitor lag between source and index.
- Never rely on an eventually consistent projection as the sole authorization authority.

If the projection is **eventually consistent**, users may temporarily not find newly published articles. That is a trade-off to accept per product requirements, not a random bug.

## 36. Using Triggers to Maintain a tsvector Column

When not using a generated column, PostgreSQL provides built-in trigger support for updating vectors:

```sql
CREATE TABLE lesson_fts.legacy_articles (
    article_id BIGINT PRIMARY KEY,
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    search_vector TSVECTOR
);

CREATE TRIGGER legacy_articles_tsvector_update
BEFORE INSERT OR UPDATE OF title, body
ON lesson_fts.legacy_articles
FOR EACH ROW
EXECUTE FUNCTION tsvector_update_trigger(
    search_vector,
    'pg_catalog.simple',
    title,
    body
);
```

### Comparison with generated columns

A stored generated column fits well when the vector is derived **from same-row columns** using a valid expression. Triggers suit legacy schemas or custom logic, while adding obligations:

- Backfilling rows that existed before the trigger was created.
- Ensuring every write path populates the vector properly.
- Recomputing when config/dictionaries change.
- Accounting for write paths, trigger overhead, and migrations.

Do not attempt to assign directly to a generated column via a trigger like an ordinary column; the two mechanisms have different rules.

## 37. Backfilling and Migrating Existing Tables

When adding FTS to a table with millions of articles:

1. Finalize the language-specific config and dictionary choices.
2. Finalize participating fields and weights.
3. Choose **stored generated column**, **expression index**, or **projection table**.
4. Measure vector generation cost on a staging dataset.
5. Backfill if using a regular/trigger-maintained column or projection.
6. Create the GIN index with an appropriate rollout strategy.
7. Update API queries and authorization filters.
8. Audit unindexed rows, config errors, and result quality.
9. Keep a rollback plan in case latency or quality degrades sharply.

### Creating an index concurrently

```sql
CREATE INDEX CONCURRENTLY ix_search_documents_vector_online
ON lesson_fts.search_documents
USING GIN (search_vector);
```

This illustrates online migration syntax; the table already has another GIN index in the lab, so do not keep both if they serve the same purpose. `CREATE INDEX CONCURRENTLY` **cannot run inside an explicit transaction block**, still consumes I/O, and can leave an `INVALID` index if it fails.

Adding a stored generated column to a large table can also require table scans/rewrites and locks depending on PostgreSQL version and approach. Never assume every `ALTER TABLE` is "online" just because the SQL is short.

## 38. Vectors Must Be Rebuilt When Dictionaries/Config Change

Suppose all documents previously used `simple`, and now English documents switch to `english`.

`simple` may keep forms like `running`/`runs` separate, while `english` may stem them to a shared lexeme. Stored vectors **do not update automatically** when you change session config.

You must:

1. Define the new configuration/dictionary version.
2. Recompute vectors for the affected corpus.
3. Ensure the GIN index reflects the new vectors.
4. Build queries using the matching config.
5. Test recall/ranking before and after.
6. Keep a rollback plan if quality drops.

Even when the config name stays the same, if dictionaries or extensions are updated, previously built vectors/indexes may need rebuilding to preserve lexeme consistency.

## 39. Vietnamese with simple: Benefits and Limitations

```sql
SELECT to_tsvector(
    'pg_catalog.simple',
    'Tối ưu tìm kiếm toàn văn tiếng Việt'
);
```

The `simple` configuration is a useful starting point for accented documents and technical codes, but it does not natively provide:

- Semantic Vietnamese word segmentation.
- Proper handling of compound words such as "cơ sở dữ liệu", "tìm kiếm", "học máy".
- Synonyms: "CSDL" and "cơ sở dữ liệu".
- Unaccented typing: "tim kiem" matching "tìm kiếm".
- Typo tolerance.
- Semantic search.

### Why is "tìm kiếm" special?

In Vietnamese, many lexical units consist of multiple space-separated syllables. Whitespace-based parsers split them into independent lexemes; phrase search helps enforce adjacency, but does not turn it into a full word-segmentation or semantic engine.

If a system has a large Vietnamese corpus where search quality is critical, a **verified specialized dictionary/segmenter or dedicated search pipeline** is needed.

## 40. Unaccented Queries and unaccent

A user types:

```text
tim kiem
```

while the document contains:

```text
tìm kiếm
```

`simple` does not guarantee these two forms are treated as equivalent by default.

PostgreSQL includes the `unaccent` extension in many environments, yet using it effectively with FTS requires building a **consistent text search configuration / dictionary chain**, rather than merely installing the extension and assuming stored vectors changed.

### Checklist

- Is the extension permitted on the server?
- Do ingest and query paths use the same analyzer?
- Do you need to index both accented and unaccented forms?
- Does stripping diacritics introduce ambiguity and lower precision?
- Were vectors/indexes rebuilt after dictionary changes?
- Are Unicode composed/decomposed forms normalized consistently?

Do not replace proper query-set evaluation with a blanket promise that "unaccenting is always better".

## 41. Synonyms and Abbreviations

A user searches for:

```text
CSDL
```

while the article only contains "cơ sở dữ liệu". FTS does not automatically know the two expressions are equivalent.

Approaches:

- Add canonical keywords to the search document.
- Expand queries using a versioned synonym list.
- Use a thesaurus dictionary if operationally suitable.
- Combine lexical and semantic retrieval if needed.

### Beware of false positives

One abbreviation can have multiple meanings. Expanding every abbreviation into dozens of phrases can hurt precision. Validate quality against your domain.

## 42. Multilingual Search

A corpus has Vietnamese and English. There are three strategies:

**A. Use `simple` for everything:** simple to implement, but misses English-specific stemming.

**B. One vector/config per language:** maintain `language_code` and index/query accordingly.

**C. Multiple vectors or projections:** store multiple analyzed representations for fallback search at the cost of extra index/write overhead.

### Design considerations

- Where does the language come from (editorial input, detection, or metadata)?
- Are vectors generated with the matching config?
- Should a Vietnamese query match English documents?
- Are rank scores across two language configurations directly comparable?
- Must proper names/identifiers match across languages?
- Is there a reindex plan when configs change?

The lab uses `simple` uniformly to avoid introducing too many variables; **that does not mean a production multilingual system should do the exact same thing**.

## 43. JSONB and Full-Text Search

A document:

```json
{
  "title": "PostgreSQL",
  "body": "Tìm kiếm toàn văn",
  "keywords": ["GIN", "index"],
  "price": 120
}
```

PostgreSQL provides `to_tsvector` overloads for JSON/JSONB depending on version:

```sql
SELECT to_tsvector(
    'pg_catalog.simple'::regconfig,
    '{"title":"PostgreSQL","body":"Tìm kiếm toàn văn"}'::jsonb
);
```

### Be careful

- JSONB does not preserve object key order.
- Lexeme positions across field values follow specific rules.
- Phrase queries spanning fields may not match the order the application assumes.
- Numbers, booleans, and nested objects behave differently from plain text; know what the function extracts.

If `title` needs weight A and `body` weight D, it is usually clearer to extract **those specific fields** and apply `setweight`, rather than indexing an entire JSONB object without a field policy.

### FTS does not replace containment

`attributes @> '{"price":120}'::jsonb` is a structural query; do not use lexical FTS to replace exact numeric price checks.

## 44. FTS with SQL Arrays or Tags

An article has tags that are managed entities, can be renamed, or act as facets. When tags have foreign keys or dedicated metadata, a **junction table** usually fits best:

```text
articles
article_tags(article_id, tag_id)
tags(tag_id, tag_code, display_name)
```

When users filter by an exact tag:

```text
tag_id = 42
```

use relational joins and B-tree/equality, rather than turning tags into lexemes and hoping the parser preserves every character.

Tag display names can still be added to the search vector for keyword search, provided there is an update mechanism when a tag is renamed.

## 45. Long Documents and Chunking

A multi-megabyte document can produce a huge vector, making `ts_headline`, ranking, and index maintenance expensive. Another pattern splits documents into chunks:

```sql
CREATE TABLE lesson_fts.article_chunks (
    article_id BIGINT NOT NULL
        REFERENCES lesson_fts.articles(article_id)
        ON DELETE CASCADE,
    chunk_no INTEGER NOT NULL CHECK (chunk_no > 0),
    chunk_text TEXT NOT NULL,
    chunk_vector TSVECTOR GENERATED ALWAYS AS (
        to_tsvector(
            'pg_catalog.simple'::regconfig,
            chunk_text
        )
    ) STORED,
    PRIMARY KEY (article_id, chunk_no)
);

CREATE INDEX ix_article_chunks_fts
ON lesson_fts.article_chunks
USING GIN (chunk_vector);
```

### Trade-offs

- Can return snippets pointing to the exact matching passage.
- Supports finding relevant sections inside long documents.
- Increases row counts and index entries, and requires grouping results back by article.
- Phrase search **across chunk boundaries** is not automatically handled as a single whole-article vector.

Chunking is only worth it if document size or UX demands it; never split short articles into multiple rows needlessly.

## 46. Should Markdown/HTML Be Preprocessed Before Indexing?

An article contains:

```text
# Hướng dẫn PostgreSQL

Sử dụng **EXPLAIN ANALYZE** để xem kế hoạch.

Một code block chứa SELECT * FROM products.
```

Passing raw markup directly into `to_tsvector` can let symbols, code identifiers, or HTML tags generate unwanted tokens.

A sound pipeline:

1. Store source Markdown/HTML for editing and rendering.
2. Use a proper parser to extract **searchable plain text**.
3. Prioritize title, headings, and summary using weights.
4. Decide whether to index code blocks if users genuinely search code.
5. Version the extraction logic and reindex when it changes.

Never claim a short regex safely sanitizes HTML. Text extraction and XSS protection at render time are two separate concerns.

## 47. Vector Updates and Concurrency

With a generated column, PostgreSQL recomputes the vector in the same transaction that updates `title`/`body`:

```sql
BEGIN;

UPDATE lesson_fts.articles
SET body = body || ' Bổ sung về hiệu năng tìm kiếm.'
WHERE tenant_id = 10
  AND slug = 'query-tuning';

COMMIT;
```

### What happens?

- `UPDATE` creates a new row version under MVCC.
- The generated `search_vector` is recomputed from the source columns.
- The GIN index is maintained accordingly.
- Once committed, the new state becomes visible per MVCC visibility rules.

This gives strong consistency when indexing directly on the table. With asynchronously updated projections, freshness can lag and must be monitored.

### Another risk: concurrent edits from two apps

If two editors use read-modify-write on `body`, there is still an **application-level lost update** risk when overwriting an old snapshot. A generated vector does not resolve editorial conflicts; use optimistic locking/versions or proper merge workflows.

## 48. WAL and Write Amplification

To observe write cost in the lab:

```sql
BEGIN;

EXPLAIN (
    ANALYZE,
    BUFFERS,
    WAL
)
UPDATE lesson_fts.articles
SET body = body || ' Thêm hướng dẫn về GIN index.'
WHERE tenant_id = 10
  AND slug = 'gin-fts';

ROLLBACK;
```

**`EXPLAIN ANALYZE` executes the real `UPDATE`.** `ROLLBACK` reverts transactional data changes, yet the generated WAL, locks, and buffer activity do not "vanish" just because of rollback.

Writing large text can generate:

- New heap tuple versions.
- New vectors and GIN index maintenance work.
- WAL traffic and cache pressure.
- Dead tuples requiring `VACUUM`.

If articles are edited occasionally, this cost is typically acceptable. If there are thousands of writes per second on long bodies, analyze throughput and indexing strategy carefully.

## 49. Publish Status and Data Safety

A `PUBLISHED` document transitions to `DRAFT`/`PRIVATE`:

```sql
UPDATE lesson_fts.articles
SET status = 'DRAFT'
WHERE tenant_id = 10
  AND slug = 'query-tuning';
```

The FTS index may still hold lexemes from the article, so public queries **must filter status** or enforce the corresponding policy. Never treat a search index as access control.

With an asynchronous projection, permission updates can outpace document index updates; check permissions against the source of truth before returning results. **Never let indexing lag create authorization lag.**

## 50. Pagination When Sorting by Rank

```sql
WITH q AS (
    SELECT websearch_to_tsquery(
        'pg_catalog.simple',
        'postgresql'
    ) AS search
)
SELECT
    article_id,
    title,
    ts_rank(search_vector, q.search) AS score
FROM lesson_fts.articles
CROSS JOIN q
WHERE tenant_id = 10
  AND status = 'PUBLISHED'
  AND search_vector @@ q.search
ORDER BY score DESC, published_at DESC, article_id DESC
LIMIT 10 OFFSET 0;
```

### Downsides of large OFFSET

`OFFSET 10000` can force PostgreSQL to find, rank, and sort many matches only to discard them. For a large corpus, deep pagination should be bounded.

### Keyset pagination

If sorting by `score DESC, published_at DESC, article_id DESC`, the cursor must include **all corresponding sort keys**. Using only `article_id > cursor` fails to preserve rank order. Moreover, scores and documents can change between requests, so define appropriate consistency/tie-breaking strategies.

Do not try to build a static B-tree index on `ts_rank(vector, query)` when `query` varies per user and expect PostgreSQL to return results pre-sorted by rank.

## 51. An Efficient Snippet Strategy

`ts_headline` must parse text to locate matching passages, so avoid running it on every candidate when only the final 10 results are needed.

A clean workflow:

1. Filter by FTS + ACL to find candidates.
2. Compute rank for the candidate set.
3. Select the result page via `LIMIT`/`OFFSET` or a valid cursor.
4. Call `ts_headline` only for the displayed IDs.
5. Escape/sanitize in the UI according to HTML policy.

Never treat `ts_headline` as automatic safe HTML highlighting for untrusted input.

## 52. Inputs That Produce Overly Broad Queries

Users can send:

```text
a OR b OR c OR d OR e ...
```

or single-character prefixes, causing the candidate set to explode.

Safeguards:

- Input length limit.
- Limit on number of lexemes/operators.
- Minimum length rules for prefixes/phrases.
- Per-tenant/per-user rate limits.
- Appropriate statement timeouts or deadlines.
- Page size limits.
- Monitoring top heavy queries.

`numnode(tsquery)` is only one signal and cannot describe full cost; a single very common word can be heavier than many rare words combined.

## 53. SQL Injection and Search Query Syntax

Distinguish clearly:

**SQL injection:** concatenating input into SQL and altering statement structure.

**Search syntax:** `websearch_to_tsquery`/`to_tsquery` interpreting quotes, `OR`, minus signs, etc. as search operators.

Use **`PreparedStatement`**:

```sql
SELECT article_id, title
FROM lesson_fts.articles
WHERE tenant_id = ?
  AND status = 'PUBLISHED'
  AND search_vector @@ websearch_to_tsquery(
      'pg_catalog.simple'::regconfig,
      ?
  );
```

Here `?` is a **JDBC placeholder**, not native SQL syntax typed directly in `psql`. The server receives the parameter bound by the driver.

Do not concatenate:

```java
String sql = "SELECT ... to_tsquery('" + userInput + "')";
```

besides being unsafe, it is brittle with escaping.

## 54. Java/JDBC Example

Assuming the PostgreSQL JDBC driver and a `DataSource` are available:

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import javax.sql.DataSource;

public final class ArticleSearchRepository {
    private final DataSource dataSource;

    public ArticleSearchRepository(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public void search(long authorizedTenantId, String input)
            throws SQLException {
        String sql = """
            WITH q AS (
                SELECT websearch_to_tsquery(
                    'pg_catalog.simple'::regconfig, ?
                ) AS search
            )
            SELECT
                a.article_id,
                a.title,
                ts_rank(a.search_vector, q.search) AS score
            FROM lesson_fts.articles AS a
            CROSS JOIN q
            WHERE a.tenant_id = ?
              AND a.status = 'PUBLISHED'
              AND a.search_vector @@ q.search
            ORDER BY score DESC,
                     a.published_at DESC,
                     a.article_id DESC
            LIMIT 20
            """;

        try (Connection conn = dataSource.getConnection();
             PreparedStatement ps = conn.prepareStatement(sql)) {
            ps.setString(1, input);
            ps.setLong(2, authorizedTenantId);

            try (ResultSet rs = ps.executeQuery()) {
                while (rs.next()) {
                    long id = rs.getLong("article_id");
                    String title = rs.getString("title");
                    float score = rs.getFloat("score");
                    // Map to a DTO according to the application's API contract.
                }
            }
        }
    }
}
```

### Key takeaways

- `authorizedTenantId` must come from a trusted authorization context, never blind client input.
- Validate query length and syntax policy before sending SQL.
- Apply timeouts and rate limits for heavy queries.
- Avoid returning raw `body` or sensitive fields unnecessarily.
- Rank score does not mean "accuracy percentage".

## 55. Spring/JdbcTemplate

A simple example with parameter binding:

```java
String sql = """
    SELECT article_id, title
    FROM lesson_fts.articles
    WHERE tenant_id = ?
      AND status = 'PUBLISHED'
      AND search_vector @@ websearch_to_tsquery(
          'pg_catalog.simple'::regconfig, ?
      )
    ORDER BY published_at DESC, article_id DESC
    LIMIT 20
    """;

var results = jdbcTemplate.query(
    sql,
    (rs, rowNum) -> new ArticleResult(
        rs.getLong("article_id"),
        rs.getString("title")
    ),
    authorizedTenantId,
    inputText
);
```

This snippet is a skeleton requiring an `ArticleResult` class/record and `jdbcTemplate` instance. In a real project, verify transaction management, validation, and exception mapping.

ORM annotations do not automatically create text search dictionaries, GIN indexes, ranking, or ACLs. Schema migrations and actual queries must still be managed explicitly.

## 56. Prepared Statements and Plan Differences

Keywords vary widely in frequency. A prepared query:

```sql
WHERE tenant_id = $1
  AND search_vector @@ websearch_to_tsquery('simple', $2)
```

may receive generic or custom plans depending on conditions, configuration, and driver behavior. A plan that works well for `deadlock` may perform poorly for `postgresql` if the latter appears throughout the corpus.

When benchmarking:

- Test both common and rare inputs.
- Compare corpus and tenant sizes.
- Inspect `EXPLAIN` matching how the application executes prepared statements.
- Check statistics, configuration, and parameter selectivity.

Do not attribute every performance difference to `work_mem` or the driver merely because two requests share the same SQL template.

## 57. Metrics to Collect

| Metric | Purpose |
|---|---|
| p50/p95/p99 search latency | Track speed and tail latency |
| Query count and timeout/error rate | Load and stability |
| Zero-result rate | Spot quality/lexeme/config issues |
| Candidate/result count | Evaluate query breadth |
| CTR or search success (when valid) | Ranking quality |
| GIN index size and write cost | Storage and update overhead |
| Indexing lag | Freshness of search projection |
| Buffer reads/temp writes | Executor bottlenecks |
| Breakdown by tenant/language/query type | Pinpoint problematic data segments |

### Privacy

Search input can contain PII or secrets. Do not log every raw query verbatim by default; use fingerprints, metadata, and policy-based redaction, restricting log access and retention.

## 58. pg_stat_statements in FTS Investigation

If the extension is installed and configured:

```sql
SELECT
    calls,
    total_exec_time,
    mean_exec_time,
    rows,
    LEFT(query, 180) AS query_sample
FROM pg_stat_statements
ORDER BY total_exec_time DESC
LIMIT 20;
```

It reports **cumulative statistics per query fingerprint**, not the full plan tree of each individual input. Use `EXPLAIN (ANALYZE, BUFFERS)` on safely reproducible cases to locate bottleneck operators or indexes.

Do not query this view and conclude "FTS is broken" if the extension is not installed.

## 59. Runbook When Documents Are Not Found

1. Verify the document exists, belongs to the right tenant, and is authorized.
2. Check `PUBLISHED`/`DRAFT` status.
3. Read the original `title`, `summary`, and `body`.
4. Inspect the actual `search_vector`.
5. Print the `tsquery` produced by the constructor.
6. Compare the document config and query config.
7. Run `ts_debug` to inspect tokens, dictionaries, stemming, and stop words.
8. Check `numnode` to rule out empty queries.
9. Distinguish expected AND, phrase, prefix, and substring semantics.
10. Verify vectors/indexes updated after the latest content edit.

### Avoid fixing the wrong problem

If a document is excluded by a valid tenant filter, **never remove the tenant condition** to "fix search". If the user needs access, that is a separate authorization matter.

## 60. Runbook When FTS Is Slow

1. Capture the query shape, language/config, tenant scope, and redacted real input.
2. Run `EXPLAIN (ANALYZE, BUFFERS, SETTINGS)` in a suitable environment.
3. Check whether it uses a GIN index scan/bitmap recheck or a `Seq Scan`.
4. Compare estimated vs actual rows and candidate counts.
5. Check whether the query uses overly common terms, long ORs, short prefixes, or NOT-only terms.
6. Look for rank `Sort` nodes and `temp read/written`.
7. Check whether `ts_headline` runs before `LIMIT` on too many rows.
8. Inspect B-tree filters for status/tenant/ACL.
9. Check GIN index size, write patterns, statistics, and `VACUUM`.
10. Measure across multiple runs with representative cache and concurrency.

Do not just raise `work_mem` when the root cause is an overly broad query or running `ts_headline` on millions of documents.

## 61. When Is PostgreSQL FTS Good Enough?

Usually suitable when:

- Data already lives in PostgreSQL.
- You need lexical search, phrases, and basic ranking.
- Relational/permission filters are tightly coupled to the data.
- You do not want to operate a separate search cluster.
- The corpus and workload meet SLAs in benchmarks.

You may need to extend or replace the solution when:

- High typo tolerance or semantic retrieval is required.
- Advanced multilingual word segmentation is needed.
- Complex faceting, autocomplete, or personalized ranking is required.
- Search traffic competes heavily with OLTP workloads.
- Search and transactional data require independent scaling and availability.

Do not choose an external search engine based solely on row count; decide based on **SLAs, search quality, and total operational cost**.

## 62. Common Misconceptions

**"tsvector is a verbatim copy of the text."** No. It stores lexemes, positions, and weights, and discards parts of the original text.

**"tsquery is an arbitrary search string."** No. It has specific syntax and lexeme units.

**"LIKE '%term%' is equivalent to FTS."** No. One is substring matching; the other is lexical retrieval.

**"plainto_tsquery uses OR by default."** No; lexemes are normally joined with AND.

**"to_tsquery accepts any user input without errors."** No. Use an appropriate query constructor and bind parameters.

**"Prefix search finds all typos."** No; `:*` is a lexeme prefix.

**"Phrase query compares exact bytes in the body."** No; phrases match lexeme positions after parsing.

**"A GIN index automatically sorts results by ts_rank."** No. Ranking and sorting are separate steps.

**"If GIN exists, the planner always uses GIN."** No. Small tables or broad queries may use `Seq Scan`.

**"Weight A guarantees title matches always rank first."** No; ranking and matching details still apply.

**"ts_rank is the probability a document is right."** No; it is a formula-based relevance score.

**"ts_headline safely escapes HTML."** No; protect against XSS when rendering.

**"Changing config automatically updates stored vectors."** No; stored data/indexes must be rebuilt for the new semantics.

**"simple fully understands Vietnamese compound words."** No; quality must be evaluated per language and corpus.

**"unaccent works automatically once the extension is installed."** No; you need a consistent analysis pipeline.

**"FTS automatically knows CSDL and cơ sở dữ liệu are synonyms."** Not by default.

**"With JSONB holding title/body, phrase positions need no special thought."** No; key ordering and lexeme extraction rules can affect them.

**"Search vectors have zero write cost."** No; INSERT/UPDATE recomputes vectors and maintains GIN.

**"A generated column can join authors/tags inside its expression."** Do not assume so; use a projection, trigger, or job.

**"An eventually consistent search projection is still safe when document permissions change."** No; check permissions against the source of truth at query time.

**"Client-supplied tenant_id proves access rights."** No.

**"With a small numnode, the query is definitely cheap."** No; a single very common word can match vast numbers of rows.

**"Search does not need rate limiting."** No; ORs, prefixes, and NOT-only queries can consume heavy resources.

**"One EXPLAIN on an eight-row table is enough."** No; benchmarks must use representative corpora and queries.

## 63. Quick Hands-on Command Set

**A — Vectors and positions:**

```sql
SELECT
    article_id, title, search_vector
FROM lesson_fts.articles
WHERE tenant_id = 10
ORDER BY article_id;
```

**B — Comparing analyzers:**

```sql
SELECT
    to_tsvector('simple', 'running runs') AS simple_v,
    to_tsvector('english', 'running runs') AS english_v;
```

**C — Tenant-safe query:**

```sql
SELECT article_id, title
FROM lesson_fts.articles
WHERE tenant_id = 10
  AND status = 'PUBLISHED'
  AND search_vector @@ plainto_tsquery(
      'pg_catalog.simple',
      'postgresql'
  );
```

**D — Phrase:**

```sql
SELECT article_id, title
FROM lesson_fts.articles
WHERE tenant_id = 10
  AND status = 'PUBLISHED'
  AND search_vector @@ phraseto_tsquery(
      'pg_catalog.simple',
      'tối ưu truy vấn'
  );
```

**E — Ranking:**

```sql
WITH q AS (
    SELECT websearch_to_tsquery(
        'pg_catalog.simple',
        'postgresql index'
    ) AS search
)
SELECT
    title,
    ts_rank(search_vector, q.search) AS score
FROM lesson_fts.articles
CROSS JOIN q
WHERE tenant_id = 10
  AND status = 'PUBLISHED'
  AND search_vector @@ q.search
ORDER BY score DESC, title;
```

**F — Inspecting the parser:**

```sql
SELECT *
FROM ts_debug(
    'pg_catalog.simple',
    'Tối ưu truy vấn PostgreSQL'
);
```

**G — Execution plan:**

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT article_id
FROM lesson_fts.articles
WHERE search_vector @@ websearch_to_tsquery(
    'pg_catalog.simple',
    'postgresql index'
);
```

## 64. Hands-on Exercises

### Exercise 1 — Tokens and lexemes

Run `to_tsvector('simple','PostgreSQL database PostgreSQL indexing')`. Identify the lexemes/positions; why can't you reconstruct the original text from the vector?

### Exercise 2 — Simple and English

Test `running runs runner` with `simple` and `english`, using `ts_debug` to observe stemming.

### Exercise 3 — Stop words

Run `ts_debug('english','The runners are running')`. Which tokens are discarded by the dictionary and why?

### Exercise 4 — Explicit config

Why should you use `to_tsvector('pg_catalog.simple'::regconfig,title)` in an expression index or generated column?

### Exercise 5 — Weights

Create a vector with title weight `A` and body weight `D`, then concatenate with `||`. Explain positions and weights.

### Exercise 6 — Three constructors

For `postgresql index`, compare `plainto_tsquery`, `phraseto_tsquery`, and `websearch_to_tsquery`. What UX does each serve?

### Exercise 7 — AND and OR

Write `to_tsquery` with AND/OR for `PostgreSQL` and `index`. Predict which query can return more rows.

### Exercise 8 — NOT

Write a query finding `PostgreSQL` without `MySQL`. Why can `!mysql` alone be difficult to optimize with an index?

### Exercise 9 — Phrase search

Search for the phrase "tối ưu truy vấn", comparing with a plain AND query of the same words. Explain the difference.

### Exercise 10 — Prefix search

Test `postgres:*`. Why is this query not equivalent to `ILIKE '%postgres%'` or typo correction?

### Exercise 11 — Empty tsquery

Test input `the and of` with the `english` config and `numnode`. Propose API behavior when a query has no remaining lexemes.

### Exercise 12 — Generated vector

Insert a new article and read `search_vector`; update `title`/`body` and read it again. Why does it stay synchronized automatically?

### Exercise 13 — GIN index

Create a GIN index on `search_vector` and run `EXPLAIN`. Why might PostgreSQL pick `Seq Scan` with eight articles?

### Exercise 14 — Ranking

Compute `ts_rank` for the query `PostgreSQL index` and sort by rank, `published_at`, `article_id`. Why is a tie-breaker needed?

### Exercise 15 — Cover density

Compare `ts_rank` and `ts_rank_cd` when two lexemes are adjacent vs far apart.

### Exercise 16 — Normalization

Try a normalization flag; explain why the score is not a probability.

### Exercise 17 — Headline

Generate a snippet with `ts_headline`. If `body` contains untrusted HTML, how do you prevent XSS?

### Exercise 18 — Complete pipeline

Write a CTE building the query once, filtering tenant/status, ranking, applying `LIMIT 10`, and generating snippets outside the limited set.

### Exercise 19 — Tenant isolation

A tenant 20 article has the same keywords. Write SQL ensuring a tenant 10 account never receives it.

### Exercise 20 — Draft visibility

A `DRAFT` article has a very high rank. Why must public search not return it? Where should ACLs be enforced?

### Exercise 21 — Expression index

Create an expression GIN index for `to_tsvector('simple',title)` and compare with a stored generated vector.

### Exercise 22 — Partial GIN

Create a GIN index only for `PUBLISHED`. Why might a generic prepared plan with `status=$1` fail to use that index?

### Exercise 23 — Trigger

Use `tsvector_update_trigger` on the legacy table. Test INSERT/UPDATE and compare with generated columns.

### Exercise 24 — Projection

Design `search_documents` combining title, author name, and tags. When an author changes name or a tag is deleted, what reindexing mechanism is needed?

### Exercise 25 — Config migration

Switch an English corpus from `simple` to `english` stemming. Write a plan to rebuild vectors/indexes and switch the query config.

### Exercise 26 — Vietnamese

Take "cơ sở dữ liệu", "tìm kiếm", and "học máy". Using `simple`, describe the word segmentation and phrase limitations.

### Exercise 27 — Unaccented search

A user enters `tim kiem` while the source has `tìm kiếm`. Propose consistent normalization/dictionaries and a policy when stripping diacritics creates ambiguity.

### Exercise 28 — Multilingual

A `vi`/`en` corpus must be searched per language; design configs/indexes/queries so `english` stemming is not applied to Vietnamese documents.

### Exercise 29 — Substring and trigrams

A user needs to search the exact string `foo.bar`. When is FTS insufficient and when should `LIKE`/`pg_trgm` be considered?

### Exercise 30 — JSONB

A product stores `title`/`description`/`keywords` in JSONB. Design a vector with `title` weight `A` and description weight `D`; explain the risk of phrases crossing JSON fields.

### Exercise 31 — Chunking

A 3 MB document. Design `article_chunks`, GIN, and grouping results by `article_id`; how do you handle phrases crossing chunks?

### Exercise 32 — HTML/Markdown

Outline a strategy to extract plain text from markup and exclude code blocks from indexing when code is irrelevant to search.

### Exercise 33 — Overly broad query

A user enters a single-character prefix with multiple OR branches. Design input limits, rate limits, `statement_timeout`, and monitoring.

### Exercise 34 — JDBC

Write a repository using `PreparedStatement` binding input and an authenticated tenant, with `LIMIT 20`; no SQL concatenation.

### Exercise 35 — ACL and indexing lag

A document switches to `PRIVATE`, while the projection has not updated yet. How do you prevent public search from returning it?

### Exercise 36 — EXPLAIN

Inspect Bitmap Index Scan/Heap Scan if present, `Recheck Cond`, estimated/actual rows, shared reads, and execution time.

### Exercise 37 — Pagination

Sort by `score DESC, published_at DESC, article_id DESC`. Why does a cursor holding only `article_id` produce wrong ordering?

### Exercise 38 — Quality metrics

Prepare 20 queries with relevance labels. Choose metrics to test zero-result rate, precision/recall, ranking, and latency.

### Exercise 39 — Write amplification

Inside a lab transaction, `UPDATE` `body` with `EXPLAIN (ANALYZE, BUFFERS, WAL)` and roll back. Why doesn't rollback erase the generated WAL?

### Exercise 40 — Comprehensive system design

A multi-tenant platform stores one million Vietnamese/English articles, needing title/body/tags search, phrases, ranking, snippets, search suggestions, RLS, and content updates:

1. Design source tables, vectors, weights, and language configurations.
2. Choose generated columns or projections, plus GIN/B-tree indexes.
3. Define query constructors for plain input, phrases, and advanced syntax.
4. Enforce tenant/status/ACL across every search path.
5. Design ranking, stable pagination, and safe highlighting.
6. Propose approaches for unaccented search, synonyms, typo tolerance, and semantic fallback when needed.
7. Describe migrations/rebuilds and monitoring indexing lag.
8. Set performance/relevance metrics to confirm the system meets SLAs.

## Conclusion

**`tsvector` represents documents as lexemes with positions/weights; `tsquery` represents search expressions; `@@` is the core match operator of PostgreSQL Full-Text Search.** Use `to_tsvector` with an explicit configuration to analyze source text, `plainto_tsquery`/`phraseto_tsquery`/`websearch_to_tsquery` for matching user input scenarios, and `to_tsquery` for controlled query expressions.

A **GIN index** is usually the main choice for finding candidates, though it does not sort by rank, build snippets, or protect document permissions by itself. **`setweight`**, **`ts_rank`/`ts_rank_cd`**, and **`ts_headline`** handle prioritization and presentation; the application must still enforce tenant/status/ACL filters and escape displayed content.

For **Vietnamese**, `simple` is a helpful starting point but does not solve compound words, unaccented matching, synonyms, or typos on its own. For multilingual corpora, keep **analysis configurations consistent between documents and queries**, and plan rebuilds whenever dictionaries or normalization change. Stored generated vectors work well when data comes from the same row; triggers or search projections fit better when aggregating multiple tables, in exchange for update cost and freshness trade-offs.

A solid FTS system does more than return rows containing keywords. It requires a **controllable pipeline from ingest to query**, reliable source data, the right indexes, safe queries, verified ranking, tenant/ACL enforcement, sensible pagination, and performance measurement on representative workloads. When all of these pieces are designed together, PostgreSQL can deliver powerful full-text search directly inside the relational database.
