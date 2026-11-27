# Updating tsvector Using Expressions or Appropriate Triggers in PostgreSQL

A document-search application usually has a table containing `title`, `body`, `tags`, and other attributes. Users edit a title or content, and expect search results to reflect the change immediately. With PostgreSQL Full-Text Search (FTS), the question is not just **how to create a GIN index**, but also:

> **When source data changes, what updates the `tsvector` content that the system searches?**

Three common strategies:

1. **Expression index**: PostgreSQL computes `to_tsvector(...)` from source columns and stores the search entries inside the index; the application does not maintain a separate `tsvector` column.
2. **Stored generated column**: declare `search_vector tsvector GENERATED ALWAYS AS (...) STORED`; PostgreSQL computes and stores the vector on write, and you can build a GIN index directly on this column.
3. **Trigger**: create an ordinary `tsvector` column plus a `BEFORE INSERT OR UPDATE` trigger to assign the vector before saving the row. You can use the built-in `tsvector_update_trigger` or write a custom trigger for weights, per-row configurations, and specialized logic.

All three approaches can produce accurate search results when defined and updated consistently. They **differ** in storage, operational overhead, ranking ergonomics, migration complexity, and risk of going out of sync.

```text
                     title, body, tags
                            |
           +----------------+----------------+
           |                |                |
           v                v                v
    Expression GIN     Stored generated    BEFORE trigger
     index key         tsvector column     tsvector column
           |                |                |
           |                v                v
           |          GIN(search_vector) GIN(search_vector)
           |                |                |
           +----------------+----------------+
                            |
                            v
             search vector @@ tsquery
                            |
                            v
                     Search results
```

This lesson belongs to the **Text Search** chapter of the *Database Engine Relational PostgreSQL* module. The goal is to help you implement and pick the right **`tsvector` update strategy**, not just memorize trigger syntax.

After completing it, you will understand:

- `to_tsvector`, `tsquery`, `@@`, normalized lexemes, stop words, and word positions.
- Why the text search configuration must be specified explicitly when building expression indexes or generated columns.
- How to create a GIN expression index **without storing `tsvector` as a column**.
- How to build a **stored generated `tsvector`** with different weights for title and body.
- How to use **`tsvector_update_trigger`** and **custom PL/pgSQL triggers**.
- How to choose `INSERT`/`UPDATE` events, handle `NULL`, manage language configs, trigger ordering, and updated data.
- How to migrate/backfill existing tables, detect stale vectors, build indexes safely, and measure costs.
- When triggers are useful, versus when generated columns or expression indexes are simpler and less error-prone.

> **Lab note:** All SQL in this lesson uses the `fts_refresh_lab` schema in a test database. `EXPLAIN (ANALYZE)` examples apply only to pure `SELECT` queries on lab data. `EXPLAIN ANALYZE UPDATE/INSERT/DELETE` **actually executes the write statement**—it is not a harmless preview mode.

---

## 1. Foundation: What Are tsvector and tsquery Used For?

### 1.1. Not verbatim string matching like LIKE

An application might start with:

```sql
SELECT *
FROM articles
WHERE title ILIKE '%search%'
   OR body ILIKE '%search%';
```

This performs substring search, which works in some scenarios, but does not natively handle:

- Word tokenization.
- **Lexemes** and stemming.
- Stop words.
- Word positions.
- Multi-word queries with boolean operators.
- Frequency/weight-based ranking.

PostgreSQL FTS provides dedicated types and functions for these needs.

### 1.2. tsvector: the normalized document

```sql
SELECT to_tsvector(
    'pg_catalog.english'::regconfig,
    'PostgreSQL indexes help searching documents'
) AS document_vector;
```

The output contains lexemes processed under the `english` configuration, typically with **positions** in the text. Words are reduced to searchable forms—for instance, plurals and inflections can be stemmed.

Do not treat this example's output as an invariant string across all configurations and dictionary versions; run `SELECT` to observe what your real server produces.

### 1.3. tsquery: search condition expression

```sql
SELECT plainto_tsquery(
    'pg_catalog.english'::regconfig,
    'searching documents'
) AS query_terms;
```

`plainto_tsquery` converts plain user text into a standard search expression, normalizing words using the configuration's rules.

`websearch_to_tsquery` supports friendlier syntax such as quoted phrases, minus signs to exclude words, and `OR`:

```sql
SELECT websearch_to_tsquery(
    'pg_catalog.english'::regconfig,
    '"full text" OR indexing'
);
```

### 1.4. The @@ operator matches vector and query

```sql
SELECT
    to_tsvector(
        'pg_catalog.english'::regconfig,
        'Full text search uses inverted indexes'
    ) @@
    plainto_tsquery(
        'pg_catalog.english'::regconfig,
        'search indexes'
    ) AS matches;
```

The two operands have types `tsvector` and `tsquery`; `@@` evaluates to a boolean.

### 1.5. FTS is not substring matching

With FTS, querying one word does not necessarily match an arbitrary slice inside a longer word. If you need to match `'sql'` in every substring, FTS is not equivalent to `ILIKE '%sql%'`. For substring search, `pg_trgm` may be a better fit.

In addition:

- FTS handles **lexeme normalization** per configuration.
- FTS provides boolean operators and positional phrase/proximity matching.
- B-tree, GIN, and GiST play different roles.
- A row matching `@@` is not automatically ordered highest; ranking is an additional step.

---

## 2. Choosing a Text Search Configuration Before Building Vectors

`to_tsvector` does not inherently understand every language. It uses a **text search configuration** to select the parser and dictionaries processing tokens.

### 2.1. Checking the default configuration

```sql
SHOW default_text_search_config;
```

This value can differ across databases, roles, or sessions.

### 2.2. Avoid the single-argument form in expression indexes

```sql
SELECT to_tsvector('PostgreSQL search indexes');
```

The single-argument call depends on the session's default configuration. That causes two issues when maintaining vectors or indexes:

1. Two sessions with different configs can produce different lexemes for the same text.
2. Index and generated column expressions generally require **IMMUTABLE** functions, whereas the default-config variant violates that contract.

Therefore, when defining an expression index or generated column, always specify the configuration explicitly:

```sql
SELECT to_tsvector(
    'pg_catalog.english'::regconfig,
    'PostgreSQL search indexes'
);
```

### 2.3. Why does the (regconfig, text) signature matter?

`to_tsvector(regconfig, text)` takes an explicitly chosen configuration, allowing PostgreSQL to treat its result as determined solely by its arguments per its function contract. That is the form suitable for index expressions where supported.

```sql
-- Suitable form for an expression index key:
to_tsvector(
    'pg_catalog.english'::regconfig,
    coalesce(title, '')
)
```

Note: `regconfig` references an existing configuration object. **Changing the definition of a referenced dictionary/config** can leave old lexemes in stored vectors or indexes out of sync; that is a migration requiring deliberate rebuilds/recomputation, not a "free" change.

### 2.4. English and simple differ

```sql
SELECT
    to_tsvector('pg_catalog.english'::regconfig,
                'running searches') AS english_vector,
    to_tsvector('pg_catalog.simple'::regconfig,
                'running searches') AS simple_vector;
```

`english` has stemming dictionaries and stop words for English; `simple` normalizes tokens more minimally and lacks English stemming rules.

Do not pick `simple` just for its name and expect Vietnamese or multilingual search quality to automatically rival a specialized search engine.

### 2.5. Vietnamese content requires dedicated verification

PostgreSQL ships different configs and extensions depending on installation. Vietnamese words with diacritics, syllable spacing, compound words, and linguistic variants require dedicated validation. `pg_catalog.english` **is not a Vietnamese stemming dictionary**.

A Vietnamese product may need:

- Suitable dictionary configurations or an external word-segmentation pipeline.
- Agreed normalization rules for diacritics and casing.
- Dedicated tokenized/search columns per business rules.
- Measuring precision and recall on real Vietnamese queries.

Never label a trigger "standard Vietnamese FTS" merely because it calls `to_tsvector('simple', text)`.

### 2.6. Consistency rule between document and query

A vector built with `english` should normally be queried with a `tsquery` built with the **same configuration**:

```sql
to_tsvector('pg_catalog.english'::regconfig, body)
  @@
websearch_to_tsquery('pg_catalog.english'::regconfig, 'search phrase')
```

Mixing `english` and `simple` can produce unexpected misses because lexemes differ on the two sides.

---

## 3. Strategy Design: Expression Index, Generated Column, Trigger

### 3.1. Quick comparison table

| Criterion | Expression GIN index | Stored generated `tsvector` | Trigger-maintained `tsvector` |
|---|---|---|---|
| Separate `tsvector` column? | **Not required** | **Yes**, managed by PostgreSQL | **Yes**, an ordinary column |
| Auto-synced on source INSERT/UPDATE? | **Yes**, index keys are maintained | **Yes**, generated expression runs on write | **Yes, if trigger runs properly** |
| Need custom function/trigger? | No | No | Built-in or custom trigger |
| Uses `GIN`? | GIN on expression | GIN on generated column | GIN on trigger-maintained column |
| Supports A/B/C/D weights? | Possible, query must match expression | Very convenient with `setweight` | Very flexible |
| Concise query `search_vector @@ ...`? | No, unless designed differently | Yes | Yes |
| Extra column storage cost | No separate vector column | Yes | Yes |
| Risk of stale vectors from logic bugs | Low if index is valid | Low if expression/config is right | Higher if trigger missing/disabled/buggy |
| Large-table migration | Build index, can use `CONCURRENTLY` | Adding `STORED` column can be costly/rewrite | Add column, backfill, create trigger/index |
| Complex logic and custom rules | Constrained by immutable index expression | Constrained by immutable generated expression | Flexible via PL/pgSQL |

**Selection rule:** If `to_tsvector` is a pure expression over same-row columns and needs no manual orchestration, **an expression index or stored generated column is usually simpler than triggers**. Use triggers when you have a concrete reason such as custom update rules, complex multi-attribute logic, staged rollouts, or legacy compatibility.

### 3.2. Three data paths

```text
Expression index
title/body -> to_tsvector(...) -> GIN index entries
SQL query -> must use expression matching the index

Stored generated column
title/body -> PostgreSQL computes STORED search_vector
search_vector -> GIN index entries
SQL query -> search_vector @@ tsquery

Trigger
title/body -> BEFORE trigger assigns NEW.search_vector
search_vector -> GIN index entries
SQL query -> search_vector @@ tsquery
```

### 3.3. Do not add all three to one table "just to be safe"

If one table has a GIN expression index over title/body, a stored generated vector of the same text, and a trigger maintaining yet another equivalent vector, maintenance becomes complicated and write-heavy. Pick **one primary search representation** per requirement; multiple indexes are justified only when workloads genuinely differ.

---

## 4. Lab A: Expression Index Without Storing a tsvector Column

### 4.1. Inspect the environment

```sql
SHOW server_version;
SELECT current_database(), current_user;
```

Proceed only in a lab database where you have privileges to create schemas and tables. Modern PostgreSQL versions support the FTS features and expression indexes used here.

### 4.2. Create the schema and source table

```sql
CREATE SCHEMA fts_refresh_lab;

CREATE TABLE fts_refresh_lab.articles_expr (
    article_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    body TEXT,
    status TEXT NOT NULL DEFAULT 'draft'
        CHECK (status IN ('draft', 'published', 'archived')),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

This table **has no `tsvector` column**. We will build a GIN index on an expression computed directly from `title` and `body`.

### 4.3. Load sample documents

```sql
INSERT INTO fts_refresh_lab.articles_expr
    (tenant_id, title, body, status)
VALUES
    (1, 'PostgreSQL text search tutorial',
        'Learn full text search with inverted indexes.',
        'published'),
    (1, 'Trigger maintenance patterns',
        'Keep search vectors up to date after edits.',
        'published'),
    (2, 'Database indexing strategies',
        'B-tree and GIN indexes solve different access problems.',
        'published'),
    (1, 'Search quality and ranking',
        NULL,
        'draft'),
    (2, 'Vietnamese customer support',
        'An English-config demonstration, not a Vietnamese tokenizer.',
        'published');
```

### 4.4. Add rows to observe the optimizer

```sql
INSERT INTO fts_refresh_lab.articles_expr
    (tenant_id, title, body, status)
SELECT
    1 + (g % 8),
    CASE
        WHEN g % 200 = 0
            THEN 'PostgreSQL search indexing guide ' || g::text
        WHEN g % 10 = 0
            THEN 'Database operations note ' || g::text
        ELSE 'Daily operational record ' || g::text
    END,
    CASE
        WHEN g % 200 = 0
            THEN 'Full text search with GIN, dictionaries and lexemes.'
        WHEN g % 10 = 0
            THEN 'A routine database maintenance entry.'
        ELSE 'Routine service logs and application metrics.'
    END,
    'published'
FROM generate_series(1, 30000) AS gs(g);
```

After this single load, the table has **30,005** rows. Synthetic data is for observing plans, not representing real production workloads.

### 4.5. Create the expression GIN index

```sql
CREATE INDEX articles_expr_fts_gin_idx
ON fts_refresh_lab.articles_expr
USING GIN (
    to_tsvector(
        'pg_catalog.english'::regconfig,
        coalesce(title, '') || ' ' || coalesce(body, '')
    )
);

ANALYZE fts_refresh_lab.articles_expr;
```

In this expression:

- `coalesce(title, '')` and `coalesce(body, '')` guard against NULL columns.
- `|| ' ' ||` joins text with a space separator.
- `'pg_catalog.english'::regconfig` fixes the configuration for the index.
- `to_tsvector(...)` converts text to a `tsvector`.
- GIN indexes the lexeme entries.

### 4.6. Queries must use a matching expression

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT article_id, title
FROM fts_refresh_lab.articles_expr
WHERE to_tsvector(
          'pg_catalog.english'::regconfig,
          coalesce(title, '') || ' ' || coalesce(body, '')
      ) @@ websearch_to_tsquery(
          'pg_catalog.english'::regconfig,
          'PostgreSQL search'
      );
```

Here `@@` operates on the **exact indexed expression**. The planner can use `articles_expr_fts_gin_idx` when cost is favorable.

A plan might show:

```text
Bitmap Heap Scan on articles_expr
  Recheck Cond: (to_tsvector(...) @@ websearch_to_tsquery(...))
  -> Bitmap Index Scan on articles_expr_fts_gin_idx
       Index Cond: (to_tsvector(...) @@ websearch_to_tsquery(...))
```

This is an **illustration**, not a fixed plan. If a query matches too many rows, PostgreSQL may choose `Seq Scan`.

### 4.7. Expression indexes stay updated automatically on data edits

Suppose `article_id = 1` is edited:

```sql
UPDATE fts_refresh_lab.articles_expr
SET title = 'New search performance guide',
    body = 'Understanding full text search and GIN',
    updated_at = now()
WHERE article_id = 1;
```

After `UPDATE`, PostgreSQL updates the index keys for the modified row via standard index maintenance. **No separate trigger is needed** just to "refresh a GIN expression index".

Test it:

```sql
SELECT article_id, title
FROM fts_refresh_lab.articles_expr
WHERE to_tsvector(
          'pg_catalog.english'::regconfig,
          coalesce(title, '') || ' ' || coalesce(body, '')
      ) @@ plainto_tsquery(
          'pg_catalog.english'::regconfig,
          'performance'
      );
```

### 4.8. Conditions that do not match the index expression

If a query writes:

```sql
SELECT article_id
FROM fts_refresh_lab.articles_expr
WHERE to_tsvector(
    'pg_catalog.english'::regconfig,
    title
) @@ plainto_tsquery(
    'pg_catalog.english'::regconfig,
    'search'
);
```

the expression `to_tsvector(config, title)` **differs** from the index expression on `coalesce(title,'') || ' ' || coalesce(body,'')`. The earlier index cannot automatically serve title-only searches.

Similarly, using `simple` when the index was built with `english` does not match the expression.

### 4.9. One advantage and one limitation

**Advantage:** no extra stored `tsvector` column or trigger logic; synchronization is tied directly to PostgreSQL's index maintenance.

**Limitation:** to filter or rank with the same vector, queries typically have to repeat the full expression. This lengthens SQL and makes it easier for query, index, and app code definitions to drift apart.

That is a major reason to consider a stored generated column.

---

## 5. Why Is coalesce Needed When title/body Can Be NULL?

### 5.1. NULL in string concatenation

```sql
SELECT 'Title'::text || NULL::text AS combined_text;
```

The result is SQL `NULL`. If you write:

```sql
to_tsvector(
    'pg_catalog.english'::regconfig,
    title || ' ' || body
)
```

and `body IS NULL`, the entire concatenated string becomes `NULL`, wiping out all `title` words from that vector expression.

### 5.2. The right way

```sql
to_tsvector(
    'pg_catalog.english'::regconfig,
    coalesce(title, '') || ' ' || coalesce(body, '')
)
```

When `body` is NULL, `title` is still indexed.

### 5.3. Do not blindly use concat_ws in indexes

`concat_ws` conveniently skips NULLs:

```sql
SELECT concat_ws(' ', 'Title', NULL, 'Body');
```

However, **`concat_ws` is not marked IMMUTABLE by PostgreSQL for all argument types**, because it can handle types whose formatting depends on context/locale. Therefore, do not substitute `concat_ws` in an expression index or generated column assuming it will be accepted.

For explicit `TEXT` columns, `coalesce(title,'') || ' ' || coalesce(body,'')` is easier to control when immutability is required.

### 5.4. Dictionaries can still drop stop words

A document containing only `'the and or'` under `english` produces an empty vector due to stop words. That is **different** from `NULL` breaking concatenation. Data validation suites should distinguish:

- A `NULL` vector caused by unhandled NULLs.
- A valid empty vector caused by text having no non-stopword lexemes.

---

## 6. Lab B: Generated Column Storing tsvector

A stored generated column is a clean option when you want the search expression defined **once in the schema** and queried by column name.

### 6.1. Create a table with a generated search_vector

```sql
CREATE TABLE fts_refresh_lab.articles_generated (
    article_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    body TEXT,
    status TEXT NOT NULL DEFAULT 'published',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    search_vector TSVECTOR GENERATED ALWAYS AS (
        setweight(
            to_tsvector(
                'pg_catalog.english'::regconfig,
                coalesce(title, '')
            ),
            'A'
        )
        ||
        setweight(
            to_tsvector(
                'pg_catalog.english'::regconfig,
                coalesce(body, '')
            ),
            'D'
        )
    ) STORED
);
```

**Meaning:**

- PostgreSQL computes the vector when rows are written.
- It is **stored** in the table as a derived value.
- `title` receives weight `A`; `body` receives weight `D`.
- No trigger is needed to keep the vector in sync with `title`/`body`.

This is a **stored generated column**, not a virtual generated column. `STORED` is specified explicitly to match the persisted vector model covered in this lesson.

### 6.2. Why call setweight separately on each part?

If you write:

```sql
to_tsvector(config, coalesce(title,'') || ' ' || coalesce(body,''))
```

words from both title and body receive the default weight. To prioritize titles during ranking:

```sql
setweight(to_tsvector(config, coalesce(title,'')), 'A')
||
setweight(to_tsvector(config, coalesce(body,'')), 'D')
```

`setweight` attaches weight labels to word positions **before concatenating the two vectors**. Labels are `A`, `B`, `C`, `D`; `A` is conventionally highest under default ranking weights, though applications can supply custom weight arrays.

### 6.3. Load data

```sql
INSERT INTO fts_refresh_lab.articles_generated
    (tenant_id, title, body)
VALUES
    (1, 'PostgreSQL full text search',
        'Generated columns keep search vectors current.'),
    (1, 'Trigger implementation notes',
        'Triggers maintain values before writing rows.'),
    (2, 'Index architecture',
        'GIN indexes help search many documents.'),
    (2, 'Search-only title',
        NULL);
```

Omit `search_vector` from `INSERT` because it is a generated column.

### 6.4. Inspect stored vector values

```sql
SELECT
    article_id,
    title,
    search_vector
FROM fts_refresh_lab.articles_generated
ORDER BY article_id;
```

Output shows lexemes with positions and weights such as `1A` for title terms and other positions for body terms. Exact values depend on configuration and text.

### 6.5. Create a GIN index on the generated column

```sql
CREATE INDEX articles_generated_fts_gin_idx
ON fts_refresh_lab.articles_generated
USING GIN (search_vector);
```

Queries become much shorter:

```sql
SELECT article_id, title
FROM fts_refresh_lab.articles_generated
WHERE search_vector @@ websearch_to_tsquery(
    'pg_catalog.english'::regconfig,
    'PostgreSQL search'
);
```

### 6.6. Updating title/body refreshes the vector automatically

```sql
SELECT article_id, title, search_vector
FROM fts_refresh_lab.articles_generated
WHERE article_id = 1;

UPDATE fts_refresh_lab.articles_generated
SET title = 'Improved full text indexing',
    body = 'Indexing and ranking with generated tsvector',
    updated_at = now()
WHERE article_id = 1;

SELECT article_id, title, search_vector
FROM fts_refresh_lab.articles_generated
WHERE article_id = 1;
```

After `UPDATE`, PostgreSQL recomputes the vector from the generated expression and updates the GIN index accordingly.

### 6.7. Do not assign arbitrary values manually

```sql
-- Invalid to set an arbitrary value on a generated column:
-- UPDATE fts_refresh_lab.articles_generated
-- SET search_vector = 'manual lexeme'::tsvector
-- WHERE article_id = 1;
```

`search_vector` is controlled by the generated expression. To change how vectors are built, perform a controlled **schema definition** change rather than manually updating the generated column.

### 6.8. Generated columns and BEFORE triggers

With stored generated columns, the generated expression is evaluated **after BEFORE triggers** in PostgreSQL so it reflects final row values before storage. Do not write a `BEFORE` trigger expecting `NEW.search_vector` to already contain the computed generated value.

If a `BEFORE` trigger normalizes `title`, the generated expression computes from that normalized value. Still, verify trigger interactions across server versions, especially during migrations.

### 6.9. Cost of generated columns

Changing `title`/`body` causes PostgreSQL to recompute the vector on write. The table stores the vector alongside `title`/`body`, and the GIN index must be maintained. That increases storage and write overhead compared to a non-FTS table, while eliminating sync bugs from custom triggers.

---

## 7. Ranking Results with Weighted tsvector

### 7.1. @@ only checks matching, it does not sort by relevance

```sql
SELECT article_id, title
FROM fts_refresh_lab.articles_generated
WHERE search_vector @@ plainto_tsquery(
    'pg_catalog.english'::regconfig,
    'indexing'
);
```

Without `ORDER BY`, SQL **makes no guarantee** on result order. GIN does not return rows pre-sorted by relevance.

### 7.2. ts_rank

```sql
WITH search_input AS (
    SELECT websearch_to_tsquery(
        'pg_catalog.english'::regconfig,
        'indexing'
    ) AS q
)
SELECT
    a.article_id,
    a.title,
    ts_rank(a.search_vector, s.q) AS score
FROM fts_refresh_lab.articles_generated AS a
CROSS JOIN search_input AS s
WHERE a.search_vector @@ s.q
ORDER BY score DESC, a.article_id DESC
LIMIT 20;
```

`ts_rank` computes a score from lexemes, weights, and frequencies per PostgreSQL's formula. A rank score does not mean "95% probability of being right", and scores should not be compared blindly across algorithm versions or different corpora.

### 7.3. ts_rank_cd

```sql
WITH q AS (
    SELECT plainto_tsquery(
        'pg_catalog.english'::regconfig,
        'full text'
    ) AS needle
)
SELECT
    a.article_id,
    a.title,
    ts_rank_cd(a.search_vector, q.needle) AS cover_density
FROM fts_refresh_lab.articles_generated AS a
CROSS JOIN q
WHERE a.search_vector @@ q.needle
ORDER BY cover_density DESC, a.article_id DESC;
```

`ts_rank_cd` computes *cover-density* ranking, considering how close matching terms sit together. Vectors whose positions have been **stripped** limit this ranking method; review `strip()` and ranking needs before discarding positions.

### 7.4. GIN does not replace score sorting

A typical FTS query can run:

```text
Bitmap Index Scan on GIN(search_vector)
         |
         v
Bitmap Heap Scan / recheck
         |
         v
Compute ts_rank(...)
         |
         v
Sort by score DESC
         |
         v
LIMIT 20
```

GIN accelerates **candidate filtering**, without providing precomputed `ts_rank` order. If the hit count is huge, ranking and sorting can still consume significant CPU and memory.

### 7.5. Weight restrictions in tsquery

PostgreSQL provides `tsquery` weight-restriction syntax, such as suffix `:A` in `to_tsquery`:

```sql
SELECT to_tsquery(
    'pg_catalog.english'::regconfig,
    'postgresql:A'
);
```

When queries restrict by weight, note that **GIN indexes do not store full per-position weight labels like the heap `tsvector` does**, so a recheck step may be needed to verify the condition.

Do not assume GIN acts as a single index that both filters weights completely and ranks results just because the `tsvector` contains weights.

---

## 8. Lab C: Built-In Trigger tsvector_update_trigger

Before stored generated columns became widespread, a traditional pattern was storing a normal `tsvector` column and maintaining it with a built-in trigger.

### 8.1. Create a table with an ordinary search_vector column

```sql
CREATE TABLE fts_refresh_lab.articles_builtin_trigger (
    article_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    title TEXT NOT NULL,
    body TEXT,
    search_vector TSVECTOR
);
```

`search_vector` here is **not a generated column**. Without a trigger or manual update, it can be NULL or stale.

### 8.2. Create the built-in trigger

```sql
CREATE TRIGGER articles_builtin_search_refresh
BEFORE INSERT OR UPDATE
ON fts_refresh_lab.articles_builtin_trigger
FOR EACH ROW
EXECUTE FUNCTION pg_catalog.tsvector_update_trigger(
    search_vector,
    'pg_catalog.english',
    title,
    body
);
```

The arguments passed to the trigger function are:

1. **Target `tsvector` column**: `search_vector`.
2. **Text search configuration name**: `'pg_catalog.english'` (string, schema-qualified).
3. **Source text columns**: `title` and `body`.

`tsvector_update_trigger` is a built-in PostgreSQL trigger function. It lets you avoid writing a new PL/pgSQL function for simple cases.

### 8.3. Why schema-qualify the config?

`'pg_catalog.english'` fixes the configuration unambiguously instead of relying on the session's `search_path` to resolve an unqualified name. Keep vector and `tsquery` configs consistent.

### 8.4. Test INSERT

```sql
INSERT INTO fts_refresh_lab.articles_builtin_trigger
    (title, body)
VALUES
    ('PostgreSQL trigger tutorial',
     'A trigger maintains the search vector.'),
    ('Database indexing',
     'Using GIN for full text documents.');

SELECT article_id, title, search_vector
FROM fts_refresh_lab.articles_builtin_trigger
ORDER BY article_id;
```

Each inserted row fires the `BEFORE` trigger, which populates `search_vector` from `title`/`body` before writing.

### 8.5. Test UPDATE

```sql
UPDATE fts_refresh_lab.articles_builtin_trigger
SET title = 'Automatic text search refresh',
    body = 'The trigger runs after the application changes source text.'
WHERE article_id = 1;

SELECT article_id, search_vector
FROM fts_refresh_lab.articles_builtin_trigger
WHERE article_id = 1;
```

The vector is recomputed by the trigger. Because the trigger is declared as `BEFORE INSERT OR UPDATE` **without restricting `UPDATE` columns**, every matching row update fires it, even when only unrelated columns are edited.

### 8.6. Create GIN on the trigger-maintained column

```sql
CREATE INDEX articles_builtin_trigger_gin_idx
ON fts_refresh_lab.articles_builtin_trigger
USING GIN (search_vector);
```

Query:

```sql
SELECT article_id, title
FROM fts_refresh_lab.articles_builtin_trigger
WHERE search_vector @@ plainto_tsquery(
    'pg_catalog.english'::regconfig,
    'automatic search'
);
```

### 8.7. When is the built-in trigger insufficient?

`tsvector_update_trigger` works well for combining a few text columns under a fixed configuration. However, if you need:

- Weight **A for title**, **D for body**.
- Normalization rules based on multiple attributes.
- Per-row language configurations.
- Conditionally including/excluding content per business rules.

you will likely need a **stored generated expression** or a **custom trigger**.

### 8.8. Built-in triggers are still an operational dependency

If a trigger is disabled, invalidated by DDL, bypassed during bulk loads, or left behind after schema changes, `search_vector` can stop reflecting source data. That is a major difference from generated columns or expression indexes managed declaratively by the engine.

---

## 9. Custom PL/pgSQL Trigger with Weights and Per-Row Config

When requirements exceed the built-in trigger, you can write a custom trigger.

### 9.1. Create a table with per-row configuration

```sql
CREATE TABLE fts_refresh_lab.articles_weighted_trigger (
    article_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    body TEXT,
    search_config REGCONFIG NOT NULL
        DEFAULT 'pg_catalog.english'::regconfig,
    search_vector TSVECTOR NOT NULL
        DEFAULT ''::tsvector,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

`search_config` is a PostgreSQL column of type `regconfig`. It lets each row specify a text search configuration, though it **does not automatically guarantee multilingual search quality**. The application must enforce rules for choosing configurations and compatible queries.

### 9.2. Write the trigger function

```sql
CREATE OR REPLACE FUNCTION
    fts_refresh_lab.refresh_weighted_search_vector()
RETURNS trigger
LANGUAGE plpgsql
AS $function$
BEGIN
    NEW.search_vector :=
        setweight(
            to_tsvector(
                NEW.search_config,
                coalesce(NEW.title, '')
            ),
            'A'
        )
        ||
        setweight(
            to_tsvector(
                NEW.search_config,
                coalesce(NEW.body, '')
            ),
            'D'
        );

    RETURN NEW;
END;
$function$;
```

Key points:

- The function returns `trigger`, not `tsvector` directly.
- `NEW` is the row about to be written.
- The trigger assigns `NEW.search_vector`.
- `RETURN NEW` lets the `INSERT`/`UPDATE` proceed with the modified row.
- `NEW.search_config` determines tokenization and stemming per row.
- Never use dynamic SQL or interpolate function/column names from user input.

### 9.3. Attach the BEFORE trigger

```sql
CREATE TRIGGER articles_weighted_search_refresh
BEFORE INSERT OR UPDATE
ON fts_refresh_lab.articles_weighted_trigger
FOR EACH ROW
EXECUTE FUNCTION
    fts_refresh_lab.refresh_weighted_search_vector();
```

In this example, the trigger fires on **every `INSERT`/`UPDATE`** to preserve the invariant that `search_vector` always matches `title`, `body`, and `search_config`.

### 9.4. Create GIN

```sql
CREATE INDEX articles_weighted_trigger_gin_idx
ON fts_refresh_lab.articles_weighted_trigger
USING GIN (search_vector);
```

### 9.5. Insert data

```sql
INSERT INTO fts_refresh_lab.articles_weighted_trigger
    (tenant_id, title, body, search_config)
VALUES
    (
        1,
        'PostgreSQL search implementation',
        'Custom triggers provide weighted documents.',
        'pg_catalog.english'::regconfig
    ),
    (
        2,
        'Simple token demonstration',
        'Running runners run.',
        'pg_catalog.simple'::regconfig
    );
```

Inspect vectors:

```sql
SELECT
    article_id,
    search_config,
    title,
    search_vector
FROM fts_refresh_lab.articles_weighted_trigger
ORDER BY article_id;
```

The two rows store different lexemes because their text search configurations differ.

### 9.6. Querying the English group

```sql
SELECT article_id, title
FROM fts_refresh_lab.articles_weighted_trigger
WHERE search_config = 'pg_catalog.english'::regconfig
  AND search_vector @@ websearch_to_tsquery(
      'pg_catalog.english'::regconfig,
      'PostgreSQL implementation'
  );
```

When documents are indexed with `english`, `tsquery` also uses `english`. Never pick one query config and claim all languages will match uniformly.

### 9.7. Updating search_config must also refresh the vector

```sql
UPDATE fts_refresh_lab.articles_weighted_trigger
SET search_config = 'pg_catalog.english'::regconfig
WHERE article_id = 2;

SELECT article_id, search_config, search_vector
FROM fts_refresh_lab.articles_weighted_trigger
WHERE article_id = 2;
```

Because the trigger listens to all `UPDATE`s, changing `search_config` recomputes the vector. If a trigger only listened to `UPDATE OF title, body`, changing the configuration would leave the old vector **unupdated**.

---

## 10. Running Triggers Only When Relevant Columns Are Updated?

PostgreSQL lets you restrict triggers to a column list:

```sql
-- Alternative option; DO NOT add alongside the existing trigger:
--
-- CREATE TRIGGER articles_weighted_search_refresh
-- BEFORE INSERT OR UPDATE OF title, body, search_config
-- ON fts_refresh_lab.articles_weighted_trigger
-- FOR EACH ROW
-- EXECUTE FUNCTION
--     fts_refresh_lab.refresh_weighted_search_vector();
```

### 10.1. Benefit

If a system updates `updated_at` frequently while rarely modifying content, `UPDATE OF title, body, search_config` avoids firing the function when an `UPDATE` statement **does not list** those columns in `SET`.

### 10.2. Important pitfall: UPDATE OF checks the SET list

Do not interpret `UPDATE OF title` as "the trigger only runs when `title`'s actual value changes".

Example:

```sql
UPDATE fts_refresh_lab.articles_weighted_trigger
SET title = title
WHERE article_id = 1;
```

Because `title` appears in the `SET` clause, the column-specific trigger still fires **even though the new value equals the old value**.

Conversely, if another `BEFORE` trigger modifies `NEW.title` during a statement that only specifies `SET body = body` or another column, `UPDATE OF title` will not necessarily fire for that trigger-induced change.

### 10.3. Ordering of multiple BEFORE triggers

When multiple triggers of the **same type** exist on one table for the same event, PostgreSQL fires them in **alphabetical order by trigger name**. If a title-normalizing trigger runs **after** the FTS trigger, the vector will be built from the unnormalized title.

Therefore:

- Avoid scattering interdependent triggers without explicit ordering.
- If another trigger cleans up `title`/`body`, ensure FTS sees the final values.
- Consider combining logic or using a generated column when the task is a pure expression.
- Add tests after `INSERT`/`UPDATE` to catch vector drift.

### 10.4. Using IS DISTINCT FROM to skip redundant recomputation

Inside a custom trigger, you can optimize with:

```sql
-- Illustrative check to place at the top of the trigger body,
-- only when policy forbids the app from editing search_vector directly:
--
-- IF TG_OP = 'UPDATE'
--    AND NEW.title IS NOT DISTINCT FROM OLD.title
--    AND NEW.body IS NOT DISTINCT FROM OLD.body
--    AND NEW.search_config IS NOT DISTINCT FROM OLD.search_config
-- THEN
--     RETURN NEW;
-- END IF;
```

`IS NOT DISTINCT FROM` handles `NULL` cleanly, making it safer than `=` when `body` is nullable.

**However, this requires a strict invariant:** if applications can write `search_vector` directly, skipping recomputation can leave a bad vector intact. If `search_vector` can be `NULL` from a migration, skipping can leave rows unfixed. In this lab, the trigger **recomputes on every `UPDATE`** for simplicity and consistency safety.

### 10.5. Trigger WHEN and INSERT

`WHEN` can reduce `UPDATE` trigger invocations. However, `OLD` does not exist on `INSERT`, so you cannot write a single `WHEN` condition referencing `OLD` for both `INSERT` and `UPDATE` without respecting syntax/semantics. Separate `INSERT` and `UPDATE` triggers can be used when optimizing deeply.

Never chase a few microseconds at the cost of silently introducing stale vectors.

---

## 11. When to Use Built-In Trigger with a Config Column?

Besides `tsvector_update_trigger`, PostgreSQL supports `tsvector_update_trigger_column` to read the search configuration from **a column in the same row** rather than a fixed config name.

### 11.1. Idea

```text
article row
  title, body
  search_config = 'pg_catalog.english'::regconfig
           |
           v
  tsvector_update_trigger_column
           |
           v
  search_vector
```

On a table with a `search_config REGCONFIG` column, you can consider:

```sql
-- Alternative to the custom trigger in Section 9;
-- DO NOT attach two triggers maintaining the same column.
--
-- CREATE TRIGGER articles_search_from_config_column
-- BEFORE INSERT OR UPDATE
-- ON fts_refresh_lab.articles_weighted_trigger
-- FOR EACH ROW
-- EXECUTE FUNCTION pg_catalog.tsvector_update_trigger_column(
--     search_vector,
--     search_config,
--     title,
--     body
-- );
```

### 11.2. When does it fit?

When you only need to **combine text columns into one vector** while letting each row use a different text search configuration. If you also need **weights title A / body D**, this built-in function does not accept per-column weights in a simple call; a generated expression or custom trigger expresses that much more cleanly.

### 11.3. Per-row configuration has a cost

When a search query arrives from a user, you must decide:

- Which config does the query use?
- Does a single request search across multiple configs at once?
- Should you group by language/tenant before constructing `tsquery`?
- How do you prevent dictionaries/configs from changing unexpectedly?

`WHERE search_vector @@ websearch_to_tsquery(search_config, $1)` has a **right-hand side that depends on each row**, which makes it harder for PostgreSQL to use a GIN index cleanly compared to a single fixed `tsquery` for the whole query. For multilingual corpora, you often run separate queries per fixed config and merge results per application rules.

---

## 12. Index Expressions and Generated Columns Also Have Immutability Limits

### 12.1. Valid expression with explicit config

```sql
to_tsvector(
    'pg_catalog.english'::regconfig,
    coalesce(title, '') || ' ' || coalesce(body, '')
)
```

This makes all row inputs and the fixed config explicit.

### 12.2. Missing config is usually invalid

```sql
-- Do not use as an expression index key:
-- CREATE INDEX bad_fts_idx
-- ON fts_refresh_lab.articles_expr
-- USING GIN (to_tsvector(title || ' ' || body));
```

`to_tsvector(text)` depends on `default_text_search_config` and fails the immutability requirement for index expressions.

### 12.3. Never fake IMMUTABLE

Never create a wrapper function reading session settings or external state and label it `IMMUTABLE` just to bypass index or generated column creation errors. When PostgreSQL trusts an `IMMUTABLE` promise that is false, index or generated values **stop matching real content**.

### 12.4. Generated columns are not for querying other tables

Generated expressions must obey PostgreSQL restrictions—no arbitrary subqueries, volatile functions, or cross-table lookups. If you need text from multiple related tables:

- Consider structured `JOIN` + FTS queries.
- Design a denormalized search projection table with a sync workflow.
- Use controlled triggers/events/outbox patterns when denormalizing.
- Handle updates across **all source tables**, not just the primary row.

Do not expect a trigger on `articles` to fire when a row in a `comments` table changes.

---

## 13. Data Quality: How Can tsvector Become Stale?

### 13.1. What is a stale vector?

Suppose a row has:

```text
title = 'PostgreSQL indexing'
body  = 'Learn GIN indexes'
search_vector = vector from old text 'Trigger tutorial'
```

If queries search `search_vector`, the new content **will not be found** even though `title`/`body` changed.

### 13.2. Common causes with triggers

- The trigger was created after old data had already been imported.
- The trigger fired only on `INSERT`, forgetting `UPDATE`.
- The trigger used `UPDATE OF title` while text changed via another column or another trigger.
- A `summary` column was added to search requirements without updating the trigger function.
- Configuration switched from `english` to `simple` without rebuilding old vectors.
- A bulk load or replication process bypassed or disabled triggers.
- Application code wrote directly to `search_vector` without preserving invariants.
- The trigger function was replaced with new logic while old rows were never backfilled.
- A record with `body IS NULL` caused string concatenation to return `NULL` because `coalesce` was missing.

### 13.3. Stored generated columns eliminate one class of bugs

When `search_vector` is defined as a generated expression over `title`/`body`, the application cannot accidentally edit the vector independently of source columns. Automatic recomputation on write minimizes sync drift.

However, generated columns **do not automatically re-evaluate all rows when external dictionaries/text search configurations change**, and migrations modifying the vector expression can still require recomputing or rewriting rows.

### 13.4. Expression indexes also do not auto-update when dictionaries change

When an expression index uses `to_tsvector(config, title/body)`, index entries reflect the rules at the time they were computed. Changing mappings or dictionaries in that config may require **`REINDEX` or controlled index rebuilds** so keys match the new rules.

Distinguish clearly:

- **Expression index**: rebuild **index entries** under the new config.
- **Stored generated / trigger-maintained `tsvector`**: **recompute the stored vector values on rows** (and GIN stays synced), not merely `REINDEX` on stale stored vectors.

### 13.5. Verifying consistency with a query

On `articles_weighted_trigger` with the function defined above, you can detect out-of-sync rows:

```sql
SELECT article_id, title, search_config
FROM fts_refresh_lab.articles_weighted_trigger AS a
WHERE a.search_vector IS DISTINCT FROM (
    setweight(
        to_tsvector(
            a.search_config,
            coalesce(a.title, '')
        ),
        'A'
    )
    ||
    setweight(
        to_tsvector(
            a.search_config,
            coalesce(a.body, '')
        ),
        'D'
    )
);
```

The verification expression must use the **exact same vector construction logic as the real function**. On large tables, this query burns CPU computing `tsvector`s across many rows; run in batches or sample as needed.

### 13.6. Do not use length equality as proof of correctness

Two vectors can have the exact same `length(search_vector)` while holding completely different lexemes. Proper verification compares **actual vector contents** or runs a representative search test suite.

---

## 14. Backfilling Existing Tables: From NULL Vectors to Complete Search

An existing table with many rows cannot simply attach a trigger and assume old data now has vectors.

### 14.1. Scenario

```text
existing articles:
  id=1 title='...' body='...' search_vector=NULL
  id=2 title='...' body='...' search_vector=NULL

CREATE TRIGGER ...
  -> maintains new INSERT/UPDATEs
  -> DOES NOT automatically backfill existing rows
```

### 14.2. General migration workflow

1. Add a nullable `search_vector TSVECTOR` column.
2. Create the function/trigger to **protect new writes**.
3. Backfill old rows in batches using the exact same vector logic.
4. Audit counts of `NULL`/mismatched rows.
5. Build the GIN index (using `CONCURRENTLY` if online traffic requires it).
6. Switch read queries to use the vector and monitor results.
7. Add `NOT NULL` constraint if truly needed with a safe DDL plan.

This ordering narrows the window where new writes lack vectors, while deployment must still handle concurrency between backfill jobs and live writers.

### 14.3. Illustrative DDL adding a column to an existing table

Suppose an application table already exists:

```sql
-- Illustrative template; do not run on a table that already has the column.
-- ALTER TABLE existing_articles
-- ADD COLUMN search_vector TSVECTOR;
```

Do not run `ADD COLUMN ... GENERATED ... STORED` without evaluating large-table impact: adding a stored generated column may compute vectors for every existing row and incur heavy DDL/lock costs depending on PostgreSQL version.

### 14.4. Batch backfill

For a trigger-maintained table with an ordinary `search_vector` column and matching formula:

```sql
-- Example for articles_weighted_trigger;
-- suppose a legacy migration left rows with search_vector IS NULL.
--
-- UPDATE fts_refresh_lab.articles_weighted_trigger AS a
-- SET search_vector =
--       setweight(
--           to_tsvector(
--               a.search_config,
--               coalesce(a.title,'')
--           ),
--           'A'
--       )
--       ||
--       setweight(
--           to_tsvector(
--               a.search_config,
--               coalesce(a.body,'')
--           ),
--           'D'
--       )
-- WHERE a.article_id BETWEEN 1 AND 1000
--   AND a.search_vector IS NULL;
```

In this lab, the column is `NOT NULL DEFAULT ''::tsvector`, so new rows never have `NULL`. The backfill example illustrates a **nullable legacy column** before applying constraints; `IS NULL` will not work if legacy rows used an empty vector to mean "not yet backfilled".

**Choose an unambiguous backfill marker** (`NULL`, a boolean migration flag, or a checkpoint table), rather than assuming every empty vector is invalid; an article containing only stop words legitimately yields an empty vector.

### 14.5. Iterating over primary-key ranges

A real backfill job might run:

```text
batch 1: id 1..1000
batch 2: id 1001..2000
batch 3: id 2001..3000
...
```

For each batch:

- Open a short transaction.
- Compute vectors for that range.
- Commit.
- Record a checkpoint.
- Monitor WAL/I/O and replication lag.
- Support pausing if production load spikes.

Never wrap an `UPDATE` of tens of millions of rows into a multi-hour single transaction without assessing locks, WAL, bloat, and rollback impact.

### 14.6. Concurrent writers

Once the trigger is active before backfill starts, new `INSERT`/`UPDATE` statements stay updated. Still guard against:

- Old jobs writing `search_vector` directly without following the rules.
- Triggers being disabled in import sessions.
- Two processes computing vectors with different function versions.
- Backfills overwriting newer edits using stale snapshots computed outside the DB.

To minimize races, compute vectors inside the `UPDATE` statement from **current row values** under appropriate transaction/row locks, rather than exporting rows to a client, processing for hours, and writing back blindly without version checks.

### 14.7. Post-backfill verification

For a legacy table:

```sql
-- Substitute the real migration table name:
-- SELECT COUNT(*)
-- FROM existing_articles
-- WHERE search_vector IS NULL;
```

Combine with checks for:

- Unbackfilled row count.
- Comparing vectors against the source formula on samples or batches.
- Verifying FTS queries find both old and new rows.
- Confirming trigger enabled/disabled state.
- Verifying index validity.

---

## 15. Building GIN on Large Tables: CONCURRENTLY and Index State

### 15.1. Standard CREATE INDEX

```sql
CREATE INDEX articles_generated_new_gin_idx
ON fts_refresh_lab.articles_generated
USING GIN (search_vector);
```

**Note:** `articles_generated` in Section 6 already has a similar index `articles_generated_fts_gin_idx`. This statement merely illustrates DDL on the lab schema; **do not keep two GIN indexes on the same key**.

### 15.2. CREATE INDEX CONCURRENTLY

```sql
-- Run only when actually creating a new index.
-- Never wrap inside an explicit BEGIN ... COMMIT block.
--
-- CREATE INDEX CONCURRENTLY articles_generated_online_gin_idx
-- ON fts_refresh_lab.articles_generated
-- USING GIN (search_vector);
```

`CONCURRENTLY` reduces blocking of concurrent writes during build, with specific constraints:

- Cannot run inside an **explicit transaction block**.
- May wait for concurrent transactions/snapshots.
- Still consumes significant CPU, I/O, disk, and WAL.
- If interrupted or failed, can leave an **`INVALID`** index that needs cleanup.
- Having a new index does not force the planner to use it for every query immediately.

### 15.3. Checking index status

```sql
SELECT
    idx.relname AS index_name,
    i.indisvalid,
    i.indisready,
    pg_size_pretty(pg_relation_size(idx.oid)) AS size
FROM pg_index AS i
JOIN pg_class AS idx
    ON idx.oid = i.indexrelid
JOIN pg_namespace AS ns
    ON ns.oid = idx.relnamespace
WHERE ns.nspname = 'fts_refresh_lab'
ORDER BY idx.relname;
```

If `indisvalid = false`, investigate and recover per procedure (`DROP INDEX CONCURRENTLY` or rebuild as appropriate). Never assume a new index is "ready" solely because its name appears in the catalog.

### 15.4. Migration ordering matters on large tables

For a trigger-maintained column with existing data, **backfill first, build GIN second** is often preferred when avoiding GIN maintenance on millions of backfill `UPDATE`s. However, protect concurrent writes and measure workload; systems requiring continuous online search may need a multi-phase rollout.

No single ordering is optimal for every environment; weigh downtime, I/O, concurrency, and when new search traffic is enabled.

---

## 16. Reading EXPLAIN and Understanding GIN Is Not a Ranking Index

### 16.1. Querying a generated vector

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT article_id, title
FROM fts_refresh_lab.articles_generated
WHERE search_vector @@ plainto_tsquery(
    'pg_catalog.english'::regconfig,
    'indexing'
);
```

### 16.2. Plans may use Bitmap Index Scan

An illustrative plan:

```text
Bitmap Heap Scan on articles_generated
  Recheck Cond: (search_vector @@ ...)
  -> Bitmap Index Scan on articles_generated_fts_gin_idx
       Index Cond: (search_vector @@ ...)
```

GIN typically identifies candidate row locations; `Bitmap Heap Scan` fetches heap pages and rechecks as needed.

### 16.3. A tiny demo table usually skips GIN

In `articles_generated` with only four rows, PostgreSQL will likely choose `Seq Scan` even though GIN exists. That is rational because scanning four rows is cheaper than traversing index and heap pages.

To evaluate real performance, use representative data and parameters; never force `enable_seqscan = off` as a production setting.

### 16.4. Index expressions are not materialized columns

In `articles_expr`, queries can use the GIN expression index, yet there is no `search_vector` column to `SELECT` directly. If ranking is needed, SQL may have to recompute the expression vector on matching rows:

```sql
WITH q AS (
    SELECT plainto_tsquery(
        'pg_catalog.english'::regconfig,
        'PostgreSQL search'
    ) AS needle
)
SELECT
    a.article_id,
    a.title,
    ts_rank(
        to_tsvector(
            'pg_catalog.english'::regconfig,
            coalesce(a.title,'') || ' ' || coalesce(a.body,'')
        ),
        q.needle
    ) AS score
FROM fts_refresh_lab.articles_expr AS a
CROSS JOIN q
WHERE to_tsvector(
          'pg_catalog.english'::regconfig,
          coalesce(a.title,'') || ' ' || coalesce(a.body,'')
      ) @@ q.needle
ORDER BY score DESC, a.article_id DESC
LIMIT 20;
```

This is a trade-off of expression-index-only vs stored generated vectors: SQL is longer and ranking must evaluate the expression for candidate rows. Real performance depends on planner, caches, and workload.

### 16.5. GIN does not provide ts_rank order automatically

Even with GIN on `search_vector`, `ORDER BY ts_rank(...) DESC` still generally requires scoring and sorting matches. Do not confuse candidate retrieval via GIN with pre-sorted relevance tables.

### 16.6. BUFFERS and rows matter more than node names

Inspect:

- Estimated `rows` and actual `rows`.
- `Rows Removed by Filter` if present.
- `Recheck Cond` and exact/lossy bitmap pages.
- `Buffers: shared hit/read`.
- Sort method if ranking is used.
- Total `Execution Time` and variance across multiple runs.

A GIN plan that ends up reading 90% of the table may not beat a `Seq Scan`.

---

## 17. Monitoring Write Amplification and FTS Costs

### 17.1. GIN maintains many lexemes

A single long document row can generate hundreds or thousands of lexemes. When content changes, maintaining GIN can require far more work than maintaining a B-tree on an integer key.

### 17.2. Pending list and fastupdate

GIN uses a `fastupdate` mechanism with a pending list to amortize the average cost of writes. Pending entries are merged and cleaned up later per GIN rules, which can cause occasional spikes in write latency.

```text
INSERT/UPDATE
     |
     v
  GIN pending list
     |
     | cleanup / merge
     v
  GIN main index
```

Tuning `gin_pending_list_limit` or `fastupdate` must be driven by measurements and system load, never applied blindly across databases.

### 17.3. Stored vectors make the table larger

When using stored generated or trigger-maintained `tsvector`s:

- `title` and `body` still occupy space.
- `search_vector` occupies additional table/TOAST space.
- The GIN index on the vector adds more storage.

Compared to an expression-index-only approach, this trades **extra vector storage for simpler queries and avoiding repeated vector computation in some workloads**.

### 17.4. Updates that do not change text still have costs

With an unrestricted `BEFORE INSERT OR UPDATE` custom trigger, updating `updated_at` still invokes the vector computation function. You can optimize by column or actual value changes when justified by workload, provided invariants against stale vectors remain intact.

### 17.5. Monitoring index usage and size

```sql
SELECT
    schemaname,
    relname,
    indexrelname,
    idx_scan,
    idx_tup_read,
    idx_tup_fetch
FROM pg_stat_user_indexes
WHERE schemaname = 'fts_refresh_lab'
ORDER BY relname, indexrelname;
```

`idx_scan` is a cumulative counter, not automatic proof that an index is "never used". Consider the observation window and real workload cycles.

### 17.6. Checking table/index sizes

```sql
SELECT
    c.oid::regclass AS object_name,
    pg_size_pretty(pg_relation_size(c.oid)) AS bytes_pretty
FROM pg_class AS c
JOIN pg_namespace AS n
    ON n.oid = c.relnamespace
WHERE n.nspname = 'fts_refresh_lab'
ORDER BY pg_relation_size(c.oid) DESC;
```

When switching between an expression index and a stored column, compare **total table + index footprint**, not just a single index's size.

---

## 18. When Changing a Text Search Dictionary or Config

### 18.1. The same text can yield different lexemes

If you alter a text search configuration's mappings, stop words, stemming rules, or dictionaries can change. The same `title`/`body` can yield different `to_tsvector(config, text)` outputs after migration.

### 18.2. Expression indexes require rebuilding

With:

```sql
CREATE INDEX ... USING GIN (
    to_tsvector('pg_catalog.english'::regconfig, ...)
);
```

the index stores keys computed under the rules at creation/update time. If you modify the underlying config/dictionary, plan a controlled **`REINDEX` or index rebuild** per best practices rather than assuming index entries rewrite themselves.

### 18.3. Stored generated columns require recomputing vectors

Suppose:

```sql
search_vector GENERATED ALWAYS AS (
  to_tsvector('your_config'::regconfig, ...)
) STORED
```

Modifying `your_config` in the catalog does not `UPDATE` every row in the table, so stored values remain un-recomputed. You need a planned **data-recomputation migration**; running `REINDEX` alone on stale stored vectors will not generate new lexemes.

### 18.4. Trigger-maintained columns behave similarly

If a trigger function changes logic or configuration, PostgreSQL does not re-run the trigger across existing rows. Only rows touched by future matching `INSERT`/`UPDATE` statements are updated. Run a batched backfill before treating the search index as updated to the new semantics.

### 18.5. Never change language configs silently

When migrating a system from `english` to a custom configuration:

1. Finalize business rules, dictionaries, and test cases.
2. Evaluate how query terms are parsed.
3. Choose the update/rebuild strategy.
4. Monitor progress, WAL, and disk usage.
5. Compare old vs new search results.
6. Switch traffic only after confirming new vectors and indexes are ready.

Changing an FTS configuration is a **search-semantics change**, not merely SQL tuning.

---

## 19. Application Search Queries: Avoiding Wrong Configs and SQL Injection

### 19.1. Choose the right tsquery function

Common functions:

| Function | Meaning |
|---|---|
| `plainto_tsquery(config, text)` | Plain text, words combined with basic search logic |
| `phraseto_tsquery(config, text)` | Builds an ordered, distance-aware phrase query |
| `websearch_to_tsquery(config, text)` | Web-like syntax: quotes, `OR`, exclusions |
| `to_tsquery(config, text)` | Explicit `tsquery` operators; powerful but requires valid syntax |

### 19.2. Never concatenate strings into SQL

Do not do this:

```java
// UNSAFE:
// String sql = "SELECT * FROM articles WHERE search_vector @@ "
//            + "to_tsquery('english', '" + userInput + "')";
```

Use parameters instead:

```sql
SELECT article_id, title
FROM fts_refresh_lab.articles_generated
WHERE search_vector @@ websearch_to_tsquery(
    'pg_catalog.english'::regconfig,
    $1
);
```

`$1` is a PostgreSQL prepared-statement placeholder; JDBC uses `?`.

### 19.3. Java JDBC

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;

public final class ArticleSearchRepository {
    public void search(Connection connection, String keywords)
            throws SQLException {
        String sql = """
            SELECT article_id, title
            FROM fts_refresh_lab.articles_generated
            WHERE search_vector @@ websearch_to_tsquery(
                'pg_catalog.english'::regconfig,
                ?
            )
            ORDER BY article_id DESC
            LIMIT 20
            """;

        try (PreparedStatement ps =
                 connection.prepareStatement(sql)) {
            ps.setString(1, keywords);

            try (ResultSet rs = ps.executeQuery()) {
                while (rs.next()) {
                    long id = rs.getLong("article_id");
                    String title = rs.getString("title");
                    // Pass results to the appropriate application layer.
                }
            }
        }
    }
}
```

Example uses Java text blocks (Java 15+). In a real application layer, add tenant/permission boundaries, timeouts, empty/overlong query checks, pagination, and contract-compliant result mapping.

### 19.4. Search ranking can create heavy load

A query with `ts_rank(...) ORDER BY score DESC LIMIT 20` may still score tens of thousands of candidates for very common words. Use:

- Tenant/status/time filters where applicable.
- Query input limits.
- Narrow column projections.
- Fresh statistics and appropriate GIN indexes.
- Selectivity and end-to-end latency measurements.

Never add `LIMIT` and assume the database only inspects 20 rows.

### 19.5. Highlighting requires proper escaping

`ts_headline` can generate excerpts highlighting matched terms. When returning HTML or rendering markup, account for escaping/XSS and untrusted user content. A string processed by `ts_headline` **is not automatically safe HTML** when rendered.

---

## 20. Common Mistakes When Maintaining tsvector

**1. "After creating a GIN index, I still need a trigger to update the index."** Not for an expression index: PostgreSQL automatically maintains index keys when source data changes.

**2. "An expression index creates a tsvector column I can SELECT by name."** No. An index expression is distinct from a stored generated column.

**3. "A stored generated column needs an accompanying trigger to refresh it."** No. PostgreSQL evaluates generated expressions automatically on writes.

**4. "The built-in trigger automatically assigns weight A to title and D to body."** No. Differentiated weights require a generated expression or custom logic.

**5. "`to_tsvector(text)` is always safely immutable for indexes."** No. It depends on the default config.

**6. "I don't need to specify the text search config in queries."** This risks lexeme mismatches between documents and queries across sessions with different defaults.

**7. "`body = NULL` doesn't affect `title || body`."** Wrong. Concatenating with SQL `NULL` yields `NULL`.

**8. "An empty vector always proves the trigger failed."** No. Stop words or empty documents legitimately produce empty vectors.

**9. "`concat_ws` is always immutable in every expression index."** No. Never assume so.

**10. "With GIN on the vector, searches return sorted by rank."** Wrong. GIN filters candidates; ranking and sorting are separate steps.

**11. "`@@` automatically sorts by relevance."** No. You need `ts_rank`/`ts_rank_cd` and `ORDER BY`.

**12. "`ts_rank` is an exact probability."** No. It is a relative ranking measure.

**13. "Weights in tsvector are fully stored in GIN so no recheck is needed."** No. Weight restrictions can require heap rechecking on the vector.

**14. "Updating title on a generated column does not update the vector."** Wrong. The vector is recomputed on row write.

**15. "Creating an UPDATE trigger automatically backfills rows created earlier."** Wrong. Migrations and backfills are required.

**16. "An `UPDATE OF title` trigger only runs when title's value actually changes."** Wrong. It depends on the statement's `SET` column list.

**17. "`UPDATE OF title` always fires if another trigger modifies `NEW.title`."** Not guaranteed; column-specific firing inspects the statement's target list.

**18. "Multiple BEFORE triggers run in random order."** PostgreSQL orders triggers of the same type alphabetically by name; design dependencies explicitly.

**19. "Changing `search_config` doesn't require updating vectors."** Wrong whenever the config produces different lexemes.

**20. "You can edit a generated `tsvector` with `UPDATE` like an ordinary column."** No. It is governed by the generated expression.

**21. "`RETURN NULL` in a `BEFORE ROW` trigger is always harmless."** No. Per trigger semantics, it silently skips the current row operation; sample functions use `RETURN NEW`.

**22. "Changing a dictionary/config automatically updates all stored vectors."** No. Plan recomputation or reindexing accordingly.

**23. "Running `REINDEX` on an old stored `tsvector` updates lexemes inside the column."** Wrong. `REINDEX` does not recompute stored column values.

**24. "If an expression index uses `english`, queries using `simple` behave identically."** Wrong. Dictionaries, stop words, and stemming differ.

**25. "English FTS handles all of Vietnamese natively."** No. Dedicated word segmentation, normalization, and quality testing are required.

**26. "Adding a generated column to a 100-million-row table never takes locks or rewrites."** Never assume so. Check PostgreSQL version, migration plan, and resources.

**27. "`CREATE INDEX CONCURRENTLY` works inside `BEGIN`."** No.

**28. "`CONCURRENTLY` doesn't need monitoring for I/O, WAL, or invalid indexes."** Wrong. It still carries overhead and failure modes.

**29. "If a trigger is enabled, every data ingestion path definitely ran it."** Never assume so when replication, bulk imports, trigger-bypassing tools, or legacy jobs exist.

**30. "Comparing `length(tsvector)` is enough to verify vectors are right."** No. Vectors can have the same length with different lexemes.

**31. "GIN indexes make JSON/text `UPDATE`s free."** No. Maintaining lexemes, positions, and GIN entries carries write overhead.

**32. "Title weight A guarantees a document matches even if the query has no matching lexeme."** No. Weights influence ranking and restrictions, never inventing missing words.

**33. "To avoid triggers, drop all constraints and put every field in JSONB."** No. Data integrity/typed columns and FTS are separate concerns.

**34. "Updating `last_seen` must re-run the FTS trigger to stay fresh."** Not necessarily. If searchable fields didn't change, you can optimize while guarding invariants.

**35. "A SQL query finding a few rows proves FTS works well."** No. Measure quality, consistency, latency, NULLs, multilingual behavior, and edge cases.

**36. "A trigger automatically fires when a related table changes content."** No. A table trigger responds only to events on that table; multi-table denormalization needs its own sync workflow.

---

## 21. Hands-on Exercises and Solutions

### Exercise 1 — Distinguishing text search and LIKE

**Question:** Do `body ILIKE '%search%'` and `to_tsvector(body) @@ plainto_tsquery('search')` always return the same result set?

**Answer:** No. `LIKE` matches substrings per string comparison rules; FTS normalizes tokens/lexemes using a configuration and evaluates a `tsquery`.

### Exercise 2 — Explicit-config tsvector syntax

**Task:** Create an English vector from `'Running searches'`.

```sql
SELECT to_tsvector(
    'pg_catalog.english'::regconfig,
    'Running searches'
);
```

### Exercise 3 — Why avoid to_tsvector(text) in expression indexes?

**Answer:** The single-argument variant depends on `default_text_search_config`, violating the immutability requirement for index expressions.

### Exercise 4 — NULL-safe expression

**Task:** Concatenate nullable `title`/`body` for FTS without losing `title` when `body` is `NULL`.

```sql
to_tsvector(
    'pg_catalog.english'::regconfig,
    coalesce(title,'') || ' ' || coalesce(body,'')
)
```

### Exercise 5 — Create an expression index

**Answer:**

```sql
-- Equivalent to the lab index already created.
CREATE INDEX exercise_articles_expr_gin
ON fts_refresh_lab.articles_expr
USING GIN (
    to_tsvector(
        'pg_catalog.english'::regconfig,
        coalesce(title,'') || ' ' || coalesce(body,'')
    )
);
```

Never keep two indexes on identical expressions in production; this DDL is for syntax practice only.

### Exercise 6 — Does an expression index need a trigger?

**Answer:** No. PostgreSQL maintains the index expression automatically on row `INSERT`/`UPDATE` via index maintenance.

### Exercise 7 — Query matching the index expression

**Answer:**

```sql
SELECT article_id
FROM fts_refresh_lab.articles_expr
WHERE to_tsvector(
    'pg_catalog.english'::regconfig,
    coalesce(title,'') || ' ' || coalesce(body,'')
) @@ plainto_tsquery(
    'pg_catalog.english'::regconfig,
    'database indexing'
);
```

### Exercise 8 — Why isn't indexing title alone equivalent to title + body?

**Answer:** They have different expression keys and lexeme sets. A query calling only `to_tsvector(config, title)` cannot automatically use an index expression built from both `title` and `body`.

### Exercise 9 — STORED generated column

**Task:** State the main advantage over expression-index-only.

**Answer:** The schema stores an automatically maintained `search_vector`; SQL can use `WHERE search_vector @@ query` and `ts_rank(search_vector, query)` without repeating the entire source expression.

### Exercise 10 — Weighting title and body

```sql
setweight(
  to_tsvector('pg_catalog.english'::regconfig,
              coalesce(title,'')), 'A'
)
||
setweight(
  to_tsvector('pg_catalog.english'::regconfig,
              coalesce(body,'')), 'D'
)
```

**Answer:** `title` receives weight `A` and `body` receives `D`, supporting title-prioritized ranking with suitable rank functions.

### Exercise 11 — Updating generated vectors

**Question:** After `UPDATE articles_generated SET body='new content'`, must you separately `UPDATE` `search_vector`?

**Answer:** No. PostgreSQL automatically recomputes the stored generated column from the new row data.

### Exercise 12 — Writing a built-in trigger

**Answer:**

```sql
CREATE TRIGGER exercise_tsvector_refresh
BEFORE INSERT OR UPDATE
ON fts_refresh_lab.articles_builtin_trigger
FOR EACH ROW
EXECUTE FUNCTION pg_catalog.tsvector_update_trigger(
    search_vector,
    'pg_catalog.english',
    title,
    body
);
```

The lab already has an equivalent trigger; do not create two triggers maintaining the same vector. This template is for syntax practice only.

### Exercise 13 — Built-in trigger and weights

**Question:** Does the built-in `tsvector_update_trigger` syntax above automatically assign weight `A` to `title`?

**Answer:** Not in that simple call. For differentiated weights, use a generated expression or a custom trigger.

### Exercise 14 — What must the trigger RETURN?

**Answer:** For a `BEFORE ROW INSERT/UPDATE` trigger updating a vector, the function returns `NEW` so the row with the assigned vector continues to be written. Returning `NULL` skips the row operation.

### Exercise 15 — Per-row config changes

**Question:** Why can a trigger with only `UPDATE OF title, body` fail if a `search_config` column is added?

**Answer:** When `search_config` changes without `title` or `body` appearing in `SET`, the trigger will not fire, leaving the vector with lexemes from the old config. Include `search_config` in the column list or fire on all `UPDATE`s.

### Exercise 16 — UPDATE OF vs actual value change

```sql
UPDATE fts_refresh_lab.articles_weighted_trigger
SET title = title
WHERE article_id = 1;
```

**Answer:** An `UPDATE OF title` trigger still fires because `title` appears in the `SET` list, even though its value did not change.

### Exercise 17 — Two BEFORE triggers

A title-normalizing trigger runs **after** the FTS trigger.

**Answer:** Risk that `search_vector` reflects the unnormalized title; fix trigger ordering or use a generated expression evaluated after `BEFORE` triggers, depending on requirements.

### Exercise 18 — Trigger on primary table and changes in child table

**Question:** When a comment is edited in `comments`, does an FTS trigger on `articles` fire automatically?

**Answer:** No. Triggers on `articles` only respond to events on `articles`; you need a dedicated sync workflow from `comments` if the search vector includes comments.

### Exercise 19 — Does a new trigger automatically backfill old rows?

**Answer:** No. You must recompute old rows in batches, then audit vectors, indexes, and rollout state.

### Exercise 20 — Why not treat empty vectors as unbackfilled?

**Answer:** Empty documents or stop-word-only documents legitimately produce empty vectors. Use an explicit migration marker/`NULL` by design instead of guessing from vector length.

### Exercise 21 — Checking for stale vectors

**Answer:** Compare `search_vector IS DISTINCT FROM <equivalent vector expression>` over selected data; differences indicate synchronization bugs or config/logic changes.

### Exercise 22 — Changing dictionaries

**Question:** Does running `REINDEX` on an old stored `tsvector` GIN index automatically update lexemes inside the column?

**Answer:** No. You must recompute the vector data, which updates the index accordingly. For an expression index over `title`/`body`, rebuilding the index under the new config is what recomputes keys.

### Exercise 23 — Ranking

**Answer:**

```sql
WITH q AS (
    SELECT plainto_tsquery(
        'pg_catalog.english'::regconfig,
        'search ranking'
    ) AS terms
)
SELECT
    a.article_id,
    ts_rank(a.search_vector, q.terms) AS score
FROM fts_refresh_lab.articles_generated AS a
CROSS JOIN q
WHERE a.search_vector @@ q.terms
ORDER BY score DESC, a.article_id DESC;
```

### Exercise 24 — Does GIN maintain rank order?

**Answer:** No. GIN locates candidate rows. `ts_rank` and `ORDER BY` remain separate work.

### Exercise 25 — Why does ts_rank_cd care about positions?

**Answer:** Cover-density ranking uses lexeme distances/positions to score term proximity; stripping positions with `strip()` limits its utility.

### Exercise 26 — Migrating a 10-million-row table

**Suggested answer:** Finalize expression/config, attach trigger for new writes if using a regular column, backfill in batches, audit `NULL`/inconsistencies, build GIN `CONCURRENTLY` outside transactions, verify index validity, and shift read traffic in phases. For generated columns, assess backfill/rewrite cost upfront.

### Exercise 27 — CREATE INDEX CONCURRENTLY inside BEGIN

**Question:** Is it valid?

**Answer:** No. `CREATE INDEX CONCURRENTLY` must run outside explicit transaction blocks; migration runners must be configured accordingly.

### Exercise 28 — When to choose an expression index?

**Answer:** When the expression is simple and immutable with an explicit config, no separate `tsvector` column is needed for frequent ranking/inspection, and you want PostgreSQL to maintain the index without triggers.

### Exercise 29 — When to choose a generated column?

**Answer:** When you want a named vector column, concise queries/ranking, weights defined in the schema, and accept the vector storage and stored-generated-column migration cost.

### Exercise 30 — When to choose a custom trigger?

**Answer:** When update logic is complex, requires per-row configs, custom write rules, or legacy compatibility; you assume responsibility for monitoring stale vectors, dependencies, trigger ordering, and backfills.

### Exercise 31 — English vs simple

**Question:** Can you build vectors with `english` and queries with `simple` and expect equivalent results?

**Answer:** No. Lexemes differ due to stemming and stop words; choose a configuration per search contract and apply it consistently on both sides.

### Exercise 32 — Side effects of EXPLAIN ANALYZE

**Question:** Is it safe to run `EXPLAIN ANALYZE UPDATE articles...` just to "inspect the index"?

**Answer:** No. The `UPDATE` **actually runs**, and triggers execute as well. Use `EXPLAIN UPDATE` without `ANALYZE`, or test in a disposable lab database.

---

## 22. Checklist for Choosing and Operating a tsvector Refresh Mechanism

### Semantics design

1. **What are the searchable sources?** Title/body/tags/comments or other tables?
2. **Language/configuration?** `english`, `simple`, or custom dictionaries?
3. **Consistent normalization?** Do document and `tsquery` configs match?
4. **NULLs?** Does `coalesce` prevent losing `title` when `body` is `NULL`?
5. **Weights?** Title A, body D, or another scheme?
6. **Need positions?** Required by phrase search or cover-density ranking?
7. **Multiple languages?** Which config will queries use per row group?

### Choosing where to maintain vectors

8. **Expression GIN** if you only need search lookup over an immutable expression.
9. **Stored generated** if you want a named vector column, automatic computation, and clean ranking.
10. **Built-in trigger** if maintaining a regular vector column from text fields with a simple config.
11. **Custom trigger** if flexible weights or conditional rules are needed.
12. **Do not duplicate** multiple mechanisms computing the same vector without reason.
13. **Never falsely mark `IMMUTABLE`** to bypass rules.

### Correct updates

14. Does the trigger cover both **`INSERT` and `UPDATE`**?
15. If using `UPDATE OF`, are **config and dependent columns** included?
16. Do other triggers edit `title`/`body`? In what order do they fire?
17. Does the trigger function `RETURN NEW` and handle `NULL` properly?
18. Can apps or bulk loads bypass triggers or write `search_vector` directly?
19. When changing dictionaries/configs, is there a recompute/reindex plan?
20. Were existing rows backfilled in batches and verified?

### Indexes and performance

21. Is GIN built on the **exact expression/column** queries use?
22. Did you run `EXPLAIN`/`EXPLAIN ANALYZE` on safe `SELECT`s with representative data?
23. Do broad FTS queries match too many rows, making ranking/sorting expensive?
24. Have GIN storage, write amplification, WAL, and pending list behavior been measured?
25. Is `CREATE INDEX CONCURRENTLY` run outside transactions for online builds?
26. Were `indisvalid`/`indisready` checked after index creation?
27. Are stale vectors and query quality monitored post-rollout?
28. Were API latency, permissions/RLS, tenant filters, and SQL injection protections reviewed?

---

## 23. Summary

The goal of `tsvector` is to convert text into lexeme structures that PostgreSQL can search with `tsquery` and `@@`. In systems with continuously changing data, **ensuring vectors reflect current content is just as important as building the index**.

Remember the three choices:

- **Expression index**: `GIN (to_tsvector(config, title/body))` is maintained automatically by PostgreSQL with no `tsvector` column and no triggers. Queries must repeat the matching expression. Usually a strong starting point for simple expressions.
- **Stored generated column**: `search_vector TSVECTOR GENERATED ALWAYS AS (...) STORED` persists the vector and recomputes it on `INSERT`/`UPDATE`. Makes `search_vector @@ query` and `ts_rank(search_vector, query)` concise, and supports `setweight` for title/body priority. Trades off extra storage and large-table migration cost.
- **Trigger**: `tsvector_update_trigger` or a custom `BEFORE INSERT OR UPDATE` assigns `NEW.search_vector`. Most flexible for custom logic, but prone to stale vectors if events are missed, configs change, triggers are disabled, or legacy rows are not backfilled.

Principles for preserving accuracy:

1. **Specify the text search configuration explicitly** for both vectors and `tsquery`.
2. Use **`coalesce`** whenever source text columns can be `NULL`.
3. For weights, call **`setweight` on each source separately, then concatenate vectors**.
4. Never assume a newly added trigger backfills historical rows.
5. When dictionaries, configs, or vector logic change, plan **recomputation/reindexing** appropriate to your chosen mechanism.
6. GIN speeds up lookup; **it does not sort by relevance automatically**.
7. Benchmark under representative conditions, and remember `EXPLAIN ANALYZE` **executes the statement**.

**Final pre-deployment question:** "If a user edits a title at 10:00, where will the system read the new lexemes from at 10:01? Does PostgreSQL update an expression index, recompute a generated column, or rely on a dependable trigger—and have legacy rows and config-change scenarios been accounted for?"

### Official PostgreSQL Documentation

- [Text Search — Introduction](https://www.postgresql.org/docs/current/textsearch-intro.html).
- [Text Search — Tables and Indexes](https://www.postgresql.org/docs/current/textsearch-tables.html).
- [Text Search — Controlling Text Search](https://www.postgresql.org/docs/current/textsearch-controls.html).
- [Text Search — Ranking Search Results](https://www.postgresql.org/docs/current/textsearch-controls.html#TEXTSEARCH-RANKING).
- [Text Search — Indexes](https://www.postgresql.org/docs/current/textsearch-indexes.html).
- [Text Search — Updating tsvector, Stored Generated Columns and Triggers](https://www.postgresql.org/docs/current/textsearch-features.html).
- [Text Search Functions and Operators](https://www.postgresql.org/docs/current/functions-textsearch.html).
- [Indexes on Expressions](https://www.postgresql.org/docs/current/indexes-expressional.html).
- [Generated Columns](https://www.postgresql.org/docs/current/ddl-generated-columns.html).
- [CREATE TRIGGER](https://www.postgresql.org/docs/current/sql-createtrigger.html).
- [CREATE INDEX](https://www.postgresql.org/docs/current/sql-createindex.html).
- [GIN Indexes](https://www.postgresql.org/docs/current/gin.html).
- [Using EXPLAIN](https://www.postgresql.org/docs/current/using-explain.html).
