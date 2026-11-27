# GIN, Multi-Value Data, and Text Search in PostgreSQL

A B-tree index works well for questions like “which row has `id = 42`?”, “which orders have `created_at >= ...`?”, or “fetch rows in descending score order.” Yet many modern applications do not store only single scalar values per column: a row may hold an **array of tags**, a **JSONB document**, **keywords of an article**, or **long text**.

For example, consider a document with:

```text
doc_id = 101
tags = ['postgresql', 'gin', 'database']
attributes = {
  "type": "guide",
  "skills": ["sql", "indexing"],
  "features": {"fts": true, "jsonb": true}
}
title = "PostgreSQL GIN index"
description = "GIN indexes support arrays JSONB and full text search"
```

The application needs to query:

- “Which documents have **both** the `postgresql` and `gin` tags?”
- “Which documents have **at least one** of the tags `fts` or `array`?”
- “Does the JSONB contain the structure `{"features":{"fts":true}}`?”
- “Which articles contain the phrase **full text**?”
- “If a user types `postgre`, how do we fuzzy-match names containing PostgreSQL?”

For these queries, PostgreSQL provides **GIN — Generalized Inverted Index**: an inverted index family mapping from *searchable components* (an array element, a JSONB key/value, a text lexeme, a trigram, etc.) to the rows containing that component.

GIN is a powerful tool, yet **not the best default index for every column**. Whether GIN works depends on **data type, query operator, operator class**, selectivity, update frequency, and maintenance cost. This lesson progresses from inverted index mechanics to practical queries, full-text search, `pg_trgm`, execution plans, the pending list, and safe deployment choices.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain the difference between a **B-tree** and a **GIN inverted index**.
2. Understand why GIN fits multi-component row values: `TEXT[]`, `JSONB`, and `TSVECTOR`.
3. Write `CREATE INDEX ... USING GIN` and choose the right operator class.
4. Use array operators `@>`, `<@`, `&&` and distinguish them from `= ANY(...)`.
5. Query JSONB using `@>`, `?`, `?|`, `?&` and understand **top-level** key existence semantics.
6. Compare `jsonb_ops` against `jsonb_path_ops`, their supported operators, and size/selectivity trade-offs.
7. Use `to_tsvector`, `plainto_tsquery`, `phraseto_tsquery`, `websearch_to_tsquery`, `to_tsquery`, and `@@`.
8. Combine `setweight`, `ts_rank`, `ts_rank_cd`, and `ts_headline` to build ranked search results.
9. Understand the limits of built-in PostgreSQL FTS for **Vietnamese** and the role of word segmentation, diacritics, and dictionary configuration.
10. Distinguish **full-text search** from `LIKE`/`ILIKE` substring matching and fuzzy matching via the `pg_trgm` extension.
11. Read `EXPLAIN (ANALYZE, BUFFERS)` output with `Bitmap Index Scan`, `Bitmap Heap Scan`, `Recheck Cond`, and `Rows Removed by Index Recheck`.
12. Analyze the impact of `fastupdate`, the **GIN pending list**, `VACUUM`, inserts/updates, and competing indexes.
13. Choose among GIN, GiST, B-tree, and expression indexes based on actual queries rather than column type names alone.
14. Run a reproducible SQL lab testing duplicate array tags, nested JSONB, and multi-condition queries.

**Scope:** Modern PostgreSQL. Certain operator classes, JSONPath indexing support, monitoring views, and extension features vary across versions; always check your target server version before deploying. Any `DROP TABLE`, `CREATE INDEX`, `UPDATE`, and extension-creation statements here are strictly for authorized test environments.

---

## 2. From B-tree to Inverted Index

Suppose a documents table has a `tags TEXT[]` column:

```text
doc_id | tags
-------+-----------------------------------
101    | {postgresql,gin,database}
102    | {postgresql,jsonb,database}
103    | {postgresql,fts,search}
104    | {postgresql,trigram,search}
105    | {postgresql,array,database}
106    | {postgresql,fts,viet}
107    | {database,search,design}
```

A traditional B-tree sorts **whole row key values**, such as:

```text
id=101 -> row 101
id=102 -> row 102
id=103 -> row 103
...
```

An inverted index conceptually reverses that mapping:

```text
"postgresql" -> {101,102,103,104,105,106}
"gin"        -> {101}
"jsonb"      -> {102}
"fts"        -> {103,106}
"search"     -> {103,104,107}
"database"   -> {101,102,105,107}
```

When searching `tags @> ARRAY['postgresql','fts']`, the engine can intersect the candidate sets for `"postgresql"` and `"fts"`, then confirm matching rows.

### 2.1. One GIN Entry Is Not One Row

Core ideas:

- A **GIN key** is a component extracted from the column value by the operator class.
- Each key points to a list or tree of **posting references** to matching rows.
- For very common keys, the posting set can grow large and use a dedicated posting tree structure.
- When searching multiple keys, the index combines candidate sets and verifies actual predicates according to the PostgreSQL execution plan.

Do not read this diagram as a byte-level storage specification. GIN also uses posting lists, posting trees, a pending list, and internal metadata.

### 2.2. Multi-Component Rows Do Not Produce Just One Entry

A single value `tags = ARRAY['postgresql','gin','database']` contributes entries to multiple keys. Similarly:

- A `JSONB` object contributes multiple paths/keys/values.
- A `tsvector` contains multiple **lexemes**.
- A text string indexed with `gin_trgm_ops` generates multiple **trigrams**.

That is also why `INSERT` and `UPDATE` on multi-component types can make GIN do significantly more work than a small B-tree index.

### 2.3. When Does GIN Make Sense?

GIN is especially useful when:

- Each row holds **multiple elements or tokens**.
- Queries frequently ask whether one or more components **are present**.
- Conditions use operators supported by a GIN operator class.
- The candidate set is selective enough for an index scan to beat a full table scan.

GIN is rarely the first choice when you only need:

```sql
WHERE id = 101
ORDER BY id
LIMIT 10;
```

Here a B-tree on the primary key or sort column is the obvious candidate.

---

## 3. Operator Classes Determine Which Questions an Index Can Answer

General syntax:

```sql
CREATE INDEX index_name
ON table_name
USING GIN (indexed_expression operator_class);
```

You can omit `operator_class` when the data type has an appropriate default GIN operator class.

| Data Type | Common GIN Operator Class | Typical Queries |
| --- | --- | --- |
| `TEXT[]`, supported arrays | `array_ops` (default for arrays) | `@>`, `<@`, `&&`, `=` |
| `JSONB` | `jsonb_ops` (default) | `@>`, `?`, `?|`, `?&`, `@?`, `@@` |
| `JSONB` | `jsonb_path_ops` | `@>`, `@?`, `@@` |
| `TSVECTOR` | `tsvector_ops` (default) | Full-text query match operator `@@` |
| `TEXT` with `pg_trgm` | `gin_trgm_ops` | Fuzzy/trigram search, `LIKE`/`ILIKE`, compatible operators |

**Crucial point:** having a GIN index on a column **does not mean every operator on that column can use the index**. The planner can only leverage operators and expressions compatible with the index's operator class.

### 3.1. Same JSONB, Two Different Operator Classes

```sql
CREATE INDEX idx_attributes_ops
ON documents USING GIN (attributes jsonb_ops);
```

and:

```sql
CREATE INDEX idx_attributes_path
ON documents USING GIN (attributes jsonb_path_ops);
```

have different designs and supported operator sets. Do not treat `jsonb_path_ops` as an “always faster” version of `jsonb_ops`.

### 3.2. Expression Indexes Differ from Full-Column Indexes

Suppose a query writes:

```sql
WHERE attributes -> 'features' ? 'fts'
```

The `?` operator is applied to the result of `attributes -> 'features'`, not directly to `attributes`. To index that exact expression, you can define:

```sql
CREATE INDEX idx_features
ON documents USING GIN ((attributes -> 'features'));
```

or rewrite the condition as containment on the full JSONB if the semantics match:

```sql
WHERE attributes @> '{"features":{"fts":true}}'::jsonb
```

These two queries are not identical: checking whether key `fts` exists is different from checking whether `fts` equals `true`.

---

## 4. Unified Lab Dataset

To make every example reproducible, let us create a documents table containing:

- `tags TEXT[]`: array of tags.
- `attributes JSONB`: structured properties.
- `title` and `description`: text content.
- `search_vector TSVECTOR`: full-text search representation.
- `locale`: declared language to illustrate multilingual handling.

> **Warning:** `DROP TABLE IF EXISTS` deletes any existing lab table with the same name. Run only in a **test database** where resetting data is permitted.

### 4.1. Creating the Schema and Table

```sql
CREATE SCHEMA IF NOT EXISTS gin_lab;

DROP TABLE IF EXISTS gin_lab.documents;

CREATE TABLE gin_lab.documents (
    doc_id BIGINT PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    tags TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    attributes JSONB NOT NULL DEFAULT '{}'::JSONB,
    locale TEXT NOT NULL DEFAULT 'en',
    search_vector TSVECTOR
        GENERATED ALWAYS AS (
            setweight(
                to_tsvector('simple'::REGCONFIG, coalesce(title, '')),
                'A'
            )
            ||
            setweight(
                to_tsvector(
                    'simple'::REGCONFIG, coalesce(description, '')
                ),
                'B'
            )
        ) STORED
);
```

Here:

- `to_tsvector('simple'::REGCONFIG, ...)` specifies a fixed text-search configuration, because the two-argument form with an explicit `REGCONFIG` is eligible for use in a generated column expression.
- `setweight(...,'A')` assigns weight `'A'` to `title` and `'B'` to `description`. Weights A/B/C/D can be used during ranking.
- `||` concatenates two tsvectors, automatically shifting lexeme positions in the second vector relative to the first.
- This is a **STORED generated column**, automatically recomputed by PostgreSQL when dependent columns change without requiring manual client updates.
- We deliberately use `'simple'` to study general mechanics and observe Vietnamese text, **not assuming `'simple'` performs high-quality Vietnamese word segmentation**.

### 4.2. Loading Eight Sample Documents

```sql
INSERT INTO gin_lab.documents (
    doc_id, title, description,
    tags, attributes, locale
)
VALUES
(
    101,
    'PostgreSQL GIN index',
    'GIN indexes support arrays JSONB and full text search',
    ARRAY['postgresql','gin','database']::TEXT[],
    '{"type":"guide","level":"advanced",
       "skills":["sql","indexing"],
       "features":{"fts":true,"jsonb":true}}'::JSONB,
    'en'
),
(
    102,
    'JSONB catalog',
    'JSONB containment and top level key operators',
    ARRAY['postgresql','jsonb','database']::TEXT[],
    '{"type":"tutorial","level":"intermediate",
       "skills":["jsonb","sql"],
       "features":{"fts":false,"jsonb":true}}'::JSONB,
    'en'
),
(
    103,
    'Full text search',
    'PostgreSQL tsvector and tsquery rank text documents',
    ARRAY['postgresql','fts','search']::TEXT[],
    '{"type":"guide","level":"advanced",
       "skills":["fts","ranking"],
       "features":{"fts":true,"jsonb":false}}'::JSONB,
    'en'
),
(
    104,
    'Search with trigrams',
    'Trigram similarity supports fuzzy matching',
    ARRAY['postgresql','trigram','search']::TEXT[],
    '{"type":"tutorial","level":"beginner",
       "skills":["trigram"],
       "features":{"fts":false}}'::JSONB,
    'en'
),
(
    105,
    'Indexing arrays',
    'Array overlaps and containment with GIN',
    ARRAY['postgresql','array','database']::TEXT[],
    '{"type":"reference","level":"beginner",
       "skills":["array","sql"],
       "features":{"jsonb":false}}'::JSONB,
    'en'
),
(
    106,
    'Tìm kiếm văn bản',
    'Chỉ mục GIN cho tiếng Việt cần cân nhắc tách từ',
    ARRAY['postgresql','fts','viet']::TEXT[],
    '{"type":"guide","level":"intermediate",
       "skills":["fts","vietnamese"],
       "features":{"fts":true}}'::JSONB,
    'vi'
),
(
    107,
    'Search architecture',
    'GIN and B-tree serve different access patterns',
    ARRAY['database','search','design']::TEXT[],
    '{"type":"article","level":"advanced",
       "skills":["architecture"],
       "features":{}}'::JSONB,
    'en'
),
(
    108,
    'Empty metadata',
    'Minimal jsonb object and empty array examples',
    ARRAY[]::TEXT[],
    '{"type":"note","skills":[],"features":{}}'::JSONB,
    'en'
);

ANALYZE gin_lab.documents;
```

### 4.3. Inspecting the Data

```sql
SELECT doc_id, title, tags, attributes, search_vector
FROM gin_lab.documents
ORDER BY doc_id;
```

The `search_vector` column does not store a plain copy of raw text; it stores **lexemes** produced by the parser and dictionary, along with positions and weights.

### 4.4. Creating Basic GIN Indexes

```sql
CREATE INDEX idx_documents_tags_gin
    ON gin_lab.documents USING GIN (tags);

CREATE INDEX idx_documents_attributes_ops_gin
    ON gin_lab.documents USING GIN (attributes jsonb_ops);

CREATE INDEX idx_documents_search_gin
    ON gin_lab.documents USING GIN (search_vector);

ANALYZE gin_lab.documents;
```

These are three separate indexes for three distinct query patterns. In production, never create every possible index just because you can; check read workloads, `UPDATE` frequency, and storage footprint.

---

## 5. GIN with Arrays: @>, <@, and &&

PostgreSQL arrays hold multiple elements within a single value:

```sql
SELECT ARRAY['postgresql','gin','database']::TEXT[];
```

GIN extracts individual array elements as search keys to serve compatible array operators.

### 5.1. @> — Array Contains Required Elements

Find documents having **both** tags `postgresql` and `fts`:

```sql
SELECT doc_id, title, tags
FROM gin_lab.documents
WHERE tags @> ARRAY['postgresql','fts']::TEXT[]
ORDER BY doc_id;
```

With the lab data, the two matching rows are:

| doc_id | title |
| ---: | --- |
| 103 | Full text search |
| 106 | Tìm kiếm văn bản |

`@>` is the **contains** operator: the left array contains all elements specified in the right array.

### 5.2. && — Overlaps (Shares at Least One Element)

```sql
SELECT doc_id, title, tags
FROM gin_lab.documents
WHERE tags && ARRAY['fts','array']::TEXT[]
ORDER BY doc_id;
```

This query selects documents tagged `fts` **or** `array` (in the lab: 103, 105, 106).

### 5.3. <@ — Array Is Contained By Another Array

```sql
SELECT doc_id, title, tags
FROM gin_lab.documents
WHERE tags <@ ARRAY[
    'postgresql','gin','database','fts','search','viet'
]::TEXT[]
ORDER BY doc_id;
```

With `<@`, every element of the left array must belong to the set of elements in the right array per operator semantics. It is not asking “just one tag matches.”

### 5.4. Empty Arrays and Duplicate Elements

Edge cases:

```sql
SELECT
    ARRAY['a','a']::TEXT[] @> ARRAY['a']::TEXT[]
        AS duplicate_contains_a,
    ARRAY['a']::TEXT[] @> ARRAY['a','a']::TEXT[]
        AS a_contains_duplicate_request,
    ARRAY[]::TEXT[] && ARRAY['a']::TEXT[]
        AS empty_overlap_a;
```

Under array containment semantics, duplicate elements are **not counted by multiplicity**. If business logic needs “element `'a'` appears at least twice,” write explicit counting logic; never use `@>` to check multiplicity.

An empty array does not overlap with an array containing `'a'`.

### 5.5. Why Isn't = ANY(tags) Equivalent for Indexing?

Two predicates may look logically equivalent for a single element:

```sql
WHERE 'fts' = ANY(tags)
```

and:

```sql
WHERE tags @> ARRAY['fts']::TEXT[]
```

yet GIN `array_ops` is built around **array operators** like `@>`. Do not assume the planner can use a GIN array index for the scalar-array form `= ANY(tags)`.

If you want to leverage GIN for element membership, prefer expressing the predicate with an operator inside the operator class and confirm with `EXPLAIN`.

### 5.6. NULLs and Inconsistent Values

Arrays can contain `NULL`s, and `NULL` matching follows specific semantics. For searchable tags, you should usually:

- Normalize tags before storing (lowercase, trim whitespace, deduplicate unless duplicates are meaningful).
- Avoid `NULL` elements unless meaningful.
- Enforce consistency with constraints or application validation.
- Never mix accented/unaccented tags expecting equality to treat them as identical automatically.

GIN accelerates finding stored values; **it does not normalize messy data for you**.

---

## 6. JSONB: Containment Operator @>

`JSONB` stores key/value structures, nested objects, and arrays. GIN indexes components inside documents to accelerate filtering.

Example attributes from doc 101:

```json
{
  "type": "guide",
  "level": "advanced",
  "skills": ["sql", "indexing"],
  "features": {
    "fts": true,
    "jsonb": true
  }
}
```

### 6.1. Matching Nested JSONB Substructures

```sql
SELECT doc_id, title
FROM gin_lab.documents
WHERE attributes @> '{"features":{"fts":true}}'::JSONB
ORDER BY doc_id;
```

In the lab, rows with `features.fts = true` are 101, 103, and 106.

`@>` checks **structural and value containment**. Unlike raw JSON text comparison, object key ordering does not affect JSONB semantics.

### 6.2. Matching an Array Element Inside JSONB

```sql
SELECT doc_id, title
FROM gin_lab.documents
WHERE attributes @> '{"skills":["sql"]}'::JSONB
ORDER BY doc_id;
```

Results include 101 and 102.

Under JSONB containment, arrays can contain additional elements beyond those requested, and element order does not restrict containment matching. Still, do not assume every JSONB array behavior matches SQL array operators identically.

### 6.3. Matching Multiple Keys and Values Together

```sql
SELECT doc_id, title
FROM gin_lab.documents
WHERE attributes @> '{"type":"guide","level":"advanced"}'::JSONB
ORDER BY doc_id;
```

In the lab: 101 and 103.

This is a clean, direct way to specify exact substructure values.

### 6.4. Containment Is Not Substring Matching

`attributes @> '{"type":"gui"}'` **will not match** `"guide"`. JSONB containment compares JSON values for equality, not substring or fuzzy matching.

If you need substring matching inside a specific key's value, extract the text and use text operators/indexes:

```sql
SELECT doc_id
FROM gin_lab.documents
WHERE attributes ->> 'type' ILIKE '%gui%';
```

That is a **text pattern** query rather than JSONB containment; default `jsonb_ops` GIN will not accelerate `ILIKE` on `->>` results.

---

## 7. JSONB: ?, ?|, ?&, and Which Level Keys Exist At

With `jsonb_ops`, key-existence operators can be backed by GIN.

### 7.1. ? — Top-Level Key Exists

```sql
SELECT doc_id, title
FROM gin_lab.documents
WHERE attributes ? 'skills'
ORDER BY doc_id;
```

Every lab row has `skills` at the top level.

However:

```sql
SELECT doc_id, title
FROM gin_lab.documents
WHERE attributes ? 'fts';
```

will not find the key `fts` nested **inside the `features` object** when `?` is applied at the top level of `attributes`.

### 7.2. ?| — At Least One Top-Level Key Exists

```sql
SELECT doc_id, title
FROM gin_lab.documents
WHERE attributes ?| ARRAY['type','unknown_key']::TEXT[]
ORDER BY doc_id;
```

This acts as a logical OR across top-level keys.

### 7.3. ?& — All Listed Top-Level Keys Exist

```sql
SELECT doc_id, title
FROM gin_lab.documents
WHERE attributes ?& ARRAY['type','skills']::TEXT[]
ORDER BY doc_id;
```

This acts as a logical AND across top-level keys.

### 7.4. Checking Keys Inside a Nested Object

```sql
SELECT doc_id, title
FROM gin_lab.documents
WHERE (attributes -> 'features') ? 'fts'
ORDER BY doc_id;
```

Here `?` operates on the **nested JSONB sub-object**, not the top-level `attributes`.

Or if you specifically want a boolean value check:

```sql
SELECT doc_id, title
FROM gin_lab.documents
WHERE attributes @> '{"features":{"fts":true}}'::JSONB
ORDER BY doc_id;
```

These two predicates differ in meaning:

- `features ? 'fts'`: key exists, even if its value is `false`.
- `@> {"features":{"fts":true}}`: key must exist and have JSON boolean `true`.

### 7.5. Top-Level Arrays Also Work with Existence

On a JSONB value that is an **array of strings**, `?` tests whether that string element appears at the top level of the array. It is not a recursive search across arbitrary nested objects/arrays.

To inspect deep structures, use containment, JSONPath, or an expression index targeting the exact sub-object.

---

## 8. jsonb_ops vs. jsonb_path_ops: How to Choose

PostgreSQL provides two prominent GIN operator classes for JSONB:

### 8.1. jsonb_ops (Default)

```sql
CREATE INDEX idx_documents_attributes_ops_gin
ON gin_lab.documents
USING GIN (attributes jsonb_ops);
```

Characteristics:

- Compatible with a wide range of JSONB operators, including `@>`, `?`, `?|`, `?&`, `@?`, `@@`.
- Useful when workloads check **key existence** or mix diverse JSONB predicates.
- Can generate many index entries for complex JSONB documents.

### 8.2. jsonb_path_ops

You can add a **second index in the lab to experiment**, though in production you should rarely keep both by default:

```sql
CREATE INDEX idx_documents_attributes_path_gin
ON gin_lab.documents
USING GIN (attributes jsonb_path_ops);
```

Key characteristics:

- Supports `@>`, `@?`, and `@@` in modern PostgreSQL versions with matching support.
- **Does not directly support** key-existence operators `?`, `?|`, `?&` the way `jsonb_ops` does.
- Typically builds a smaller index and can be more selective for containment on nested paths/values.
- Has a notable limitation on JSON structures without indexable scalar values—for example, searching for an empty object `{"a":{}}` can be inefficient because no leaf value entry exists.

### 8.3. Quick Comparison

| Query Pattern | jsonb_ops | jsonb_path_ops |
| --- | --- | --- |
| `attributes @> '{"type":"guide"}'` | Yes | Yes |
| `attributes ? 'type'` | Yes | No |
| `attributes ?| ARRAY['type','level']` | Yes | No |
| `attributes ?& ARRAY['type','level']` | Yes | No |
| Indexable JSONPath `@?`/`@@` expressions | Yes | Yes |
| Highly selective containment queries | Can work well | Often worth benchmarking |
| General key-existence queries | Suitable | Not a direct option |
| Containment with empty objects/arrays | Needs measurement | Can be especially inefficient |

**There is no rule that “`jsonb_path_ops` is always better.”** Measure real queries while weighing supported operators, index size, write speed, and data shape.

### 8.4. Two Indexes on the Same Column Don't Mean the Planner Uses Both

When both `jsonb_ops` and `jsonb_path_ops` exist, the planner evaluates costs and operators to pick a plan. It may choose one index, combine bitmaps with another index, or perform a sequential scan when row counts are low.

On our eight-row lab table, `Seq Scan` is completely reasonable even with indexes present.

---

## 9. JSONPath: @? and @@

PostgreSQL provides JSONPath operators useful for complex predicates on `JSONB`.

### 9.1. @? — Does the Path Match Any Element?

Example finding documents containing skill `"sql"`:

```sql
SELECT doc_id, title
FROM gin_lab.documents
WHERE attributes @? '$.skills[*] ? (@ == "sql")'
ORDER BY doc_id;
```

### 9.2. @@ — Evaluates a JSONPath Predicate

Example checking a boolean value at a path:

```sql
SELECT doc_id, title
FROM gin_lab.documents
WHERE attributes @@ '$.features.fts == true'
ORDER BY doc_id;
```

### 9.3. Not All JSONPath Expressions Are Accelerated Equally

GIN can extract indexable bounds from certain JSONPath expressions, especially paths leading to equality comparisons against constants. Complex expressions, non-indexable predicates, or special path combinations may still examine many rows.

Therefore:

- Using `@?` alone never guarantees an index scan.
- `jsonb_ops` and `jsonb_path_ops` differ in which JSONPath accessors they accelerate.
- Always check execution plans against realistic data.
- A straightforward `@>` predicate is often clearer and easier to optimize than JSONPath when it expresses the exact requirement.

---

## 10. Expression Indexes for Nested JSONB

If the application frequently checks:

```sql
WHERE (attributes -> 'features') ? 'fts'
```

you can index that exact expression:

```sql
CREATE INDEX idx_documents_features_gin
ON gin_lab.documents
USING GIN ((attributes -> 'features'));
```

The planner can then apply the JSONB GIN operator class to the result of `attributes -> 'features'`.

### 10.1. Query Expressions Must Match the Index Expression

An index:

```sql
USING GIN ((attributes -> 'features'))
```

is not equivalent to indexing all of `attributes`. It assists queries applying indexable operators to that matching sub-expression.

If the application needs key existence across multiple nesting levels plus general containment, choose between a full-column JSONB index and targeted expression indexes based on the workload.

### 10.2. Rewrites Can Have Different Semantics

For example:

```sql
attributes -> 'features' ? 'fts'
```

and:

```sql
attributes @> '{"features":{"fts":true}}'::JSONB
```

differ when `fts` is `false`. Index tuning must never silently convert a “key exists” check into a “value is true” check unless business logic permits it.

### 10.3. When Should JSONB Fields Be Normalized into Dedicated Columns?

If a JSONB field:

- Is filtered or joined on very frequently.
- Requires `NOT NULL`, `UNIQUE`, or foreign key constraints.
- Needs frequent range queries or `ORDER BY`.
- Serves as a core business identifier.

it often belongs in its **own SQL column** with a B-tree or suitable index, rather than extracting it from JSONB on every query. GIN makes semi-structured data searchable, yet it does not replace relational schema design when strict invariants apply.

---

## 11. Full-Text Search: From Text to tsvector

Full-text search (FTS) is not simply `LIKE '%word%'`. PostgreSQL parses text into **lexemes** using a parser and dictionaries, optionally normalizing stems, dropping stop words, and recording positions.

Example:

```sql
SELECT to_tsvector(
    'english',
    'PostgreSQL indexes support searching documents'
);
```

With `'english'`, words are stemmed to base forms and stored with positions. Exactly what is kept or stemmed depends on dictionary configuration and input text.

Compare with:

```sql
SELECT to_tsvector(
    'simple',
    'PostgreSQL indexes support searching documents'
);
```

The `'simple'` configuration does not perform English stemming the way `'english'` does.

### 11.1. What Is a tsvector?

A `TSVECTOR` is a sorted structure of normalized lexemes prepared for search:

```text
Raw text:
"PostgreSQL full text search"

Conceptual tsvector:
'full':2 'postgresql':1 'search':4 'text':3
```

This is illustrative; exact lexemes and positions depend on the configuration and tokenizer output.

### 11.2. What Is a tsquery?

A `TSQUERY` represents a search condition:

```text
postgresql & gin
full <-> text
jsonb | array
```

Matched using `@@`:

```sql
search_vector @@ some_tsquery
```

GIN indexes the lexemes inside `search_vector` to locate matching candidate rows.

### 11.3. Why Not Index Raw Text Directly with FTS GIN?

Standard FTS GIN works on `TSVECTOR`, rather than running full text parsing dynamically over an arbitrary `TEXT` column on every lookup. You can:

- Store a `TSVECTOR` column maintained automatically via a generated column.
- Create a GIN **expression index** on `to_tsvector(config, text)`.
- Use triggers or application pipelines when custom preprocessing is needed.

The essential rule is that **queries must use the same tokenization and dictionary configuration** as the indexed data.

---

## 12. GIN on tsvector

In our lab we created:

```sql
CREATE INDEX idx_documents_search_gin
ON gin_lab.documents
USING GIN (search_vector);
```

A typical FTS query:

```sql
SELECT doc_id, title
FROM gin_lab.documents
WHERE search_vector @@ plainto_tsquery(
    'simple', 'full text'
)
ORDER BY doc_id;
```

In the lab, docs 101 and 103 contain lexemes `'full'` and `'text'` in their indexed fields; results depend on document text and the `'simple'` configuration.

### 12.1. plainto_tsquery — Friendly for Plain User Input

```sql
SELECT plainto_tsquery('simple', 'postgresql gin');
```

For this input, the resulting `tsquery` conceptually resembles:

```text
'postgresql' & 'gin'
```

It converts plain words into an AND query without expecting users to type `&`, `|`, or `!` syntax.

### 12.2. to_tsquery — For Structured Query Syntax

```sql
SELECT to_tsquery(
    'simple',
    'postgresql & (gin | jsonb)'
);
```

Important operators:

| Operator in tsquery | Meaning |
| --- | --- |
| `&` | AND |
| `|` | OR |
| `!` | NOT |
| `<->` | Adjacent words/phrases in order |
| `<N>` | Positional distance of N tokens between lexemes |
| `:*` | Lexeme prefix match in supported syntax |

`to_tsquery` requires valid syntax and throws errors on malformed input. **Never concatenate untrusted user input directly into `to_tsquery`** assuming syntax safety; use bind parameters and appropriate parsing functions.

### 12.3. phraseto_tsquery — Matching Exact Phrases

```sql
SELECT doc_id, title
FROM gin_lab.documents
WHERE search_vector @@ phraseto_tsquery(
    'simple', 'full text'
)
ORDER BY doc_id;
```

This builds a phrase query checking word order and adjacency; ideal when `"full text"` must appear consecutively under FTS rules.

### 12.4. websearch_to_tsquery — Web-Style Search Syntax

```sql
SELECT websearch_to_tsquery(
    'simple',
    '"full text" OR jsonb -trigram'
);
```

It supports user-friendly syntax like quoted phrases, `OR`, and `-` for negation, making it far safer and friendlier than `to_tsquery` for search bars.

Still, “user-friendly” does not mean the engine infers deep semantics, fixes typos, segments Vietnamese compound words, or enforces arbitrary filters.

### 12.5. Inspect Generated tsqueries Before Guessing Results

```sql
SELECT
    plainto_tsquery('simple', 'full text') AS plain_query,
    phraseto_tsquery('simple', 'full text') AS phrase_query,
    websearch_to_tsquery(
        'simple', '"full text" OR jsonb'
    ) AS web_query;
```

Printing the generated `tsquery` shows exactly how PostgreSQL interpreted the input.

---

## 13. AND, OR, NOT, and Selectivity in FTS

A query:

```sql
SELECT doc_id, title
FROM gin_lab.documents
WHERE search_vector @@ to_tsquery(
    'simple', 'postgresql & gin'
);
```

selects documents containing both lexemes. In the lab, doc 101 is the clear match.

With OR:

```sql
SELECT doc_id, title
FROM gin_lab.documents
WHERE search_vector @@ to_tsquery(
    'simple', 'gin | jsonb'
)
ORDER BY doc_id;
```

the result set can grow larger since only one of the terms is required.

### 13.1. Prefix Search Differs from Substring Search

Example:

```sql
SELECT doc_id, title
FROM gin_lab.documents
WHERE search_vector @@ to_tsquery(
    'simple', 'postgre:*'
);
```

A prefix in `tsquery` matches **lexemes starting with that prefix** under the chosen configuration. It does not match an arbitrary substring anywhere inside a word.

For instance, `'tgre'` inside `"PostgreSQL"` can match `ILIKE '%tgre%'`, yet will never match the lexeme prefix `postgre:*`.

### 13.2. Pure Negation Queries Can Be Unselective

A `tsquery` meaning “does not contain word X” may match nearly the whole table. Queries lacking selective positive terms are poorly suited for inverted indexes, and the planner may scan many rows rather than gaining much from GIN.

When designing search APIs, never promise that arbitrary Boolean FTS expressions will always run as fast as looking up a rare keyword.

---

## 14. Weighted Full-Text Search: title vs. description

Our lab table builds:

```sql
setweight(to_tsvector('simple', title), 'A')
||
setweight(to_tsvector('simple', description), 'B')
```

This lets ranking distinguish matches in the **title** from matches in the **description**.

### 14.1. Searching and Computing Rank

```sql
WITH q AS (
    SELECT plainto_tsquery('simple', 'full text') AS query
)
SELECT
    d.doc_id,
    d.title,
    ts_rank(d.search_vector, q.query) AS rank
FROM gin_lab.documents AS d
CROSS JOIN q
WHERE d.search_vector @@ q.query
ORDER BY rank DESC, d.doc_id ASC;
```

The `rank` column represents relevance under the chosen algorithm; it is not a normalized “90% accuracy” probability, nor is it comparable across different queries.

### 14.2. Weights A/B/C/D

PostgreSQL lets you label lexeme positions with weights. Assigning `'A'` to `title` and `'B'` to `description` allows title matches to contribute differently from description matches.

Keep in mind:

- `setweight` attaches weights to lexeme positions.
- `ts_rank` and `ts_rank_cd` compute scores using different formulas.
- Custom weight arrays can be passed to rank functions for tuning.
- Scores also depend on term frequency and document structure.
- Production search often also incorporates freshness, access permissions, popularity, and business ranking signals.

### 14.3. A GIN Index Does Not Return Rows Pre-Sorted by Rank

A query:

```sql
WHERE search_vector @@ q
ORDER BY ts_rank(search_vector, q) DESC
LIMIT 20
```

normally has to:

1. Find matching rows (potentially via GIN).
2. Compute rank for every matched row.
3. Sort by rank.
4. Return the top N.

A GIN index on `tsvector` **is not pre-sorted by `ts_rank` for arbitrary queries**. Because rank varies per `tsquery`, having GIN never makes `ORDER BY rank` free.

### 14.4. ts_rank_cd and Lexeme Positions

`ts_rank_cd` uses cover density scoring, which relies on token proximity. If positions are stripped from a `tsvector`, proximity-based ranking degrades substantially.

For systems needing phrase matching or proximity ranking, preserve lexeme positions when building `tsvector`.

---

## 15. ts_headline: Highlighting Matched Terms

PostgreSQL provides `ts_headline` to generate text snippets with matched terms marked.

```sql
WITH q AS (
    SELECT plainto_tsquery('simple', 'full text') AS query
)
SELECT
    d.doc_id,
    d.title,
    ts_headline(
        'simple',
        d.description,
        q.query,
        'StartSel=<b>, StopSel=</b>, MaxWords=20, MinWords=5'
    ) AS snippet
FROM gin_lab.documents AS d
CROSS JOIN q
WHERE d.search_vector @@ q.query
ORDER BY d.doc_id;
```

This helps produce search result snippets for UIs.

### 15.1. XSS Warning When Rendering HTML

If you use `StartSel=<b>` and `StopSel=</b>`, **never assume `ts_headline` output is safe to inject directly as raw HTML** when the source text comes from users.

Escape/sanitize text and apply safe frontend markers properly. `ts_headline` is a snippet-highlighting function, **not an HTML sanitizer**.

### 15.2. ts_headline Is Not a Reason to Add Extra GIN Indexes

GIN locates rows matching `tsquery`. `ts_headline` still processes the raw text of selected rows to generate snippets. Avoid computing highlights across the entire table before filtering/limiting rows.

---

## 16. FTS Configurations and Languages

An FTS query must use an appropriate text-search configuration:

```sql
SELECT to_tsvector('english', 'Indexes are indexing documents');
SELECT to_tsvector('simple',  'Indexes are indexing documents');
```

Differences arise from stemming, stop words, and dictionary rules.

### 16.1. Text Indexed in One Language, Queried in Another

If the index is built with:

```sql
to_tsvector('english', body)
```

yet queries run:

```sql
plainto_tsquery('simple', user_input)
```

query lexemes may fail to match stored lexemes—for example, inflected English words stemmed on one side and unstemmed on the other.

Rule: **tokenization and dictionary configurations of the index and query must match**.

### 16.2. Why Relying on Session Defaults Is Risky

The single-argument form:

```sql
to_tsvector(body)
```

uses `default_text_search_config` from the session/database. If that setting changes, identical expressions yield different lexemes.

In expression indexes and generated columns, always specify `REGCONFIG` explicitly:

```sql
to_tsvector('english'::REGCONFIG, body)
```

so indexing and querying remain deterministic. Choosing a configuration is a domain decision, not just a technical tweak.

---

## 17. Vietnamese: Limitations of simple and english

PostgreSQL includes parsers and text-search configurations, yet you must not assume PostgreSQL ships with **complete Vietnamese morphological analysis and word segmentation out of the box**.

Vietnamese has many **multi-syllable compound words separated by spaces**, for example:

```text
"cơ sở dữ liệu"
"tìm kiếm toàn văn"
"chỉ mục ngược"
```

A generic configuration like `'simple'` tokenizes space-separated syllables, yet does not automatically recognize `"cơ sở dữ liệu"` as a single domain term. Meanwhile `'english'` applies English stemming and stop words, making it unsuitable for Vietnamese text.

### 17.1. Inspect Output Directly

```sql
SELECT
    to_tsvector('simple', 'Tìm kiếm văn bản tiếng Việt')
        AS vietnamese_vector,
    plainto_tsquery('simple', 'tìm kiếm')
        AS vietnamese_query,
    phraseto_tsquery('simple', 'tìm kiếm')
        AS vietnamese_phrase;
```

Inspect how the parser and dictionary actually tokenize lexemes. Never treat syllable tokenization here as full word segmentation for proper names, slang, domain terms, or compound words.

### 17.2. Accented vs. Unaccented Text

```text
"tim kiem"
"tìm kiếm"
```

should not be assumed to match automatically. Define a clear policy:

- Should searches be accent-sensitive or accent-insensitive?
- Should stored vectors keep diacritics or normalize them?
- Is Unicode normalization (NFC/NFD) applied on ingestion?
- Should fuzzy typo matching and unaccented queries be supported?
- Does stripping diacritics blur distinct words or proper names?

### 17.3. unaccent Is a Tool, Not Complete Vietnamese Support

The `unaccent` extension (when authorized and installed) strips diacritics according to rule files for normalization. However:

- Stripping diacritics does not solve **word segmentation**.
- `unaccent` is not automatic spell correction.
- Normalized forms can conflate words with different meanings.
- When used in indexes or generated columns, check function **volatility/immutability** and dictionary setup; never falsely mark a wrapper `IMMUTABLE` if its output depends on mutable dictionary configs.

For demanding Vietnamese search requirements, consider custom text-search configurations with dictionaries, external preprocessing pipelines, or a dedicated search engine.

### 17.4. Multilingual Content

Our lab table has a `locale` column, yet `search_vector` uses `'simple'` for all rows. That is a pedagogical simplification, **not an optimal design for mixed Vietnamese and English search**.

In production systems, you can:

1. Partition or group documents by language.
2. Build vectors with per-language configurations.
3. Store the chosen configuration and reuse it at query time.
4. Align expression indexes or generated columns accordingly.
5. Combine proper-name lookup and fuzzy matching where needed.

Do not assume `locale = 'vi'` makes PostgreSQL switch dictionaries automatically if the index expression hardcodes `'simple'`.

---

## 18. Full-Text Search vs. LIKE and ILIKE

Three queries may look similar on the surface while behaving completely differently:

| Requirement | Usually Suitable Tool |
| --- | --- |
| Records containing meaningful **words/lexemes** per dictionary | FTS: `tsvector @@ tsquery` |
| Strings containing an **exact substring** anywhere | `LIKE`/`ILIKE`, optionally backed by trigrams |
| Strings **roughly similar** to input (typos) | `pg_trgm` and similarity |
| Lookup by exact scalar ID or value | B-tree |
| Semantic similarity via vector embeddings | Dedicated vector-search solution, not standard FTS GIN |

### 18.1. FTS Is Not Substring Matching

If a user types `postgre`:

- `ILIKE '%postgre%'` matches `"PostgreSQL"`.
- `to_tsquery('simple','postgre:*')` matches lexemes starting with that prefix.
- `plainto_tsquery('simple','postgre')` does not automatically match the start of `"postgresql"`.

If a user types a middle substring like `tgre`, FTS prefix matching cannot replace substring search.

### 18.2. Does a B-tree on TEXT Help ILIKE '%word%'?

A standard B-tree cannot accelerate leading-wildcard patterns such as `ILIKE '%word%'`. Prefix `LIKE` queries can use B-tree under compatible collations/operator classes, whereas **arbitrary substring matching** calls for another mechanism such as `pg_trgm`.

---

## 19. pg_trgm: GIN for Trigrams and Fuzzy Matching

The `pg_trgm` extension provides operators and operator classes for trigrams—three-character sequences extracted according to the extension's rules.

### 19.1. Installing the Extension Where Permitted

In a lab database where you have privileges:

```sql
CREATE EXTENSION IF NOT EXISTS pg_trgm;
```

If your account lacks permission to create extensions, ask an administrator or use a preconfigured environment; never alter extensions casually in production.

### 19.2. Creating a GIN Trigram Index

```sql
CREATE INDEX idx_documents_title_trgm
ON gin_lab.documents
USING GIN (title gin_trgm_ops);
```

This index serves a **different purpose** from `idx_documents_search_gin` on `tsvector`.

### 19.3. Substring Search with ILIKE

```sql
SELECT doc_id, title
FROM gin_lab.documents
WHERE title ILIKE '%postgre%'
ORDER BY doc_id;
```

Trigram GIN can accelerate compatible pattern queries. In the lab, doc 101's title contains `"PostgreSQL"`.

### 19.4. Similarity and the % Operator

```sql
SELECT
    doc_id,
    title,
    similarity(title, 'PostgreSQL GIN indez') AS sim
FROM gin_lab.documents
WHERE title % 'PostgreSQL GIN indez'
ORDER BY sim DESC, doc_id;
```

The `%` operator compares against `pg_trgm`'s configured similarity threshold; it **does not perform FTS word matching**.

Trigram similarity is a character-level string metric, not semantic similarity. Words can look close in spelling while having unrelated meanings.

### 19.5. No Guarantee Indexes Are Fast on Very Short Strings

If a search pattern yields too few trigrams, the index lacks selective keys and the query may inspect many rows or fall back to `Seq Scan`.

For instance, a single-character substring search:

```sql
WHERE title ILIKE '%a%'
```

will not magically become fast just because a GIN trigram index exists. Test against realistic data.

### 19.6. GIN vs. GiST for pg_trgm

`pg_trgm` supports both `gin_trgm_ops` and `gist_trgm_ops`, with distinct structures and trade-offs:

- GIN is often strong for matching/filtering candidates.
- GiST can support distance-ordered / k-NN similarity sorting using compatible `pg_trgm` operators.
- Top-K nearest-string requirements, update rates, and actual data determine the better fit.

Never generalize that “GIN is always faster than GiST,” especially when queries `ORDER BY` similarity distance.

---

## 20. Expression Indexes for Full-Text Search

You do not strictly need a stored `search_vector` column if you only want an expression index.

Hypothetical table example:

```sql
CREATE INDEX idx_articles_fts
ON articles
USING GIN (
    to_tsvector(
        'english'::REGCONFIG,
        coalesce(title, '') || ' ' || coalesce(body, '')
    )
);
```

Queries must match the indexed expression and configuration:

```sql
SELECT article_id, title
FROM articles
WHERE to_tsvector(
    'english'::REGCONFIG,
    coalesce(title, '') || ' ' || coalesce(body, '')
) @@ plainto_tsquery('english', 'search index');
```

The `articles` table is not created in our lab; this illustrates the structural pattern.

### 20.1. When Is a Generated tsvector Column Helpful?

- Queries can reference the concise `search_vector` column name.
- Easy to reuse the same vector for both `@@` filtering and ranking.
- Field weights can be assigned cleanly.
- PostgreSQL maintains the `STORED` column automatically on row modifications.

Trade-offs:

- Extra disk space to store the vector.
- `INSERT`/`UPDATE` on title/body recomputes the vector and updates GIN.
- Changing dictionaries or normalization logic may require migration/rebuilding.
- Generated column expressions must comply with PostgreSQL immutability rules.

### 20.2. Be Careful Maintaining tsvector Manually in Application Code

If an application writes a `tsvector` manually, every code path updating `title` or `body` must keep the vector synchronized. Missing one path causes FTS results to diverge from live text.

Generated columns or triggers reduce that risk when designed carefully with explicit configurations and write paths.

---

## 21. Combining GIN Across Arrays, JSONB, and FTS

A real-world query often combines multiple predicates:

> Find documents tagged PostgreSQL, having FTS enabled in attributes, and matching “search”.

```sql
SELECT
    doc_id,
    title
FROM gin_lab.documents
WHERE tags @> ARRAY['postgresql']::TEXT[]
  AND attributes @> '{"features":{"fts":true}}'::JSONB
  AND search_vector @@ plainto_tsquery('simple','search')
ORDER BY doc_id;
```

The planner may:

- Use one GIN index and filter remaining conditions on the heap.
- Combine bitmaps across multiple indexes via `BitmapAnd`.
- Choose `Seq Scan` if the table is small or selectivity is low.

There is no guarantee that combining predicates with `AND` forces the planner to use all indexes.

### 21.1. Why Does Bitmap Index Scan Usually Appear?

GIN results naturally produce sets of **candidate row locations**, which PostgreSQL accesses in the heap using a bitmap scan.

Conceptual plan:

```text
Bitmap Heap Scan on documents
  Recheck Cond: (...)
  -> Bitmap Index Scan on idx_documents_tags_gin
       Index Cond: (tags @> ...)
```

This is purely illustrative; actual plans depend on PostgreSQL version, statistics, selectivity, and configuration.

### 21.2. Recheck Does Not Mean the Index Is Broken

Some GIN conditions or memory-constrained lossy bitmaps require rechecking rows on the heap to guarantee exact results. `Recheck Cond` is PostgreSQL verifying candidates—not an index bug.

When a bitmap degrades to page-level granularity due to `work_mem` limits, you may see `Rows Removed by Index Recheck`. That differs from ordinary post-scan `Rows Removed by Filter`.

### 21.3. Do Not Confuse ORDER BY with GIN

When you need:

```sql
ORDER BY created_at DESC
LIMIT 20
```

GIN on tags or JSONB does not return rows ordered by `created_at`. You may need a B-tree on the timestamp or another plan strategy.

If queries always filter tags and sort newest-first, index design must consider **the full workload and `EXPLAIN` output**, rather than blindly adding GIN alone.

---

## 22. Reading EXPLAIN for GIN

On an eight-row lab table, PostgreSQL normally picks **`Seq Scan`**, even when indexes exist. That is rational because reading a single heap page beats traversing an index and bitmap.

### 22.1. Inspecting the Actual Plan

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT doc_id, title
FROM gin_lab.documents
WHERE tags @> ARRAY['postgresql','fts']::TEXT[];
```

Check:

- Is it `Seq Scan` or `Bitmap Heap Scan`?
- Is there a `Bitmap Index Scan` on GIN?
- What are `actual rows` and `Rows Removed by Filter`?
- Are `Recheck Cond` and `Rows Removed by Index Recheck` shown?
- What do `Buffers: shared hit/read` show?
- What are Planning Time and Execution Time?

### 22.2. Encouraging the Planner to Use the Index in the Lab to Study Plans

Only inside a lab transaction:

```sql
BEGIN;

SET LOCAL enable_seqscan = off;

EXPLAIN (ANALYZE, BUFFERS)
SELECT doc_id, title
FROM gin_lab.documents
WHERE tags @> ARRAY['postgresql','fts']::TEXT[];

ROLLBACK;
```

`SET LOCAL` applies only within the current transaction and resets afterward. Suppressing `Seq Scan` here lets you **inspect an index plan structure**, not prove it is faster.

Never apply `enable_seqscan = off` as production tuning. The planner may still choose `Seq Scan` when no viable index plan exists.

### 22.3. BitmapAnd When Combining Multiple GIN Indexes

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT doc_id
FROM gin_lab.documents
WHERE tags @> ARRAY['postgresql']::TEXT[]
  AND attributes @> '{"type":"guide"}'::JSONB;
```

The planner may combine bitmaps or use one selective predicate as the primary index path. On small tables, `Seq Scan` remains optimal. Evaluate matched row counts and selectivity instead of chasing a particular node name.

### 22.4. Planner Cost Is Not Milliseconds

The `cost=...` numbers in `EXPLAIN` are **relative planner cost units**, not milliseconds. Only `EXPLAIN ANALYZE` reports measured execution times in that environment.

---

## 23. GIN and Write Cost: One Row, Many Keys

In a B-tree on `doc_id`, each row generally corresponds to one entry. In a GIN index on `tags`, one row can generate many keys. GIN on `JSONB` or `TSVECTOR` can involve even more entries.

This creates a clear trade-off:

| Read Benefit | Write / Maintenance Cost |
| --- | --- |
| Fast multi-tag filtering | `INSERT` must update all relevant GIN keys |
| Flexible JSONB containment | `UPDATE` on JSONB structures can trigger heavy index work |
| Lexeme-based full-text search | Editing title/body recomputes vectors and updates GIN |
| Trigram substring/fuzzy search | Strings can emit many trigrams |
| Combining multiple predicates | Multiple indexes consume disk, WAL, and `VACUUM` work |

### 23.1. What About Updating a Column Unrelated to GIN?

Under PostgreSQL MVCC, `UPDATE` creates a new tuple version. If the `UPDATE` qualifies for HOT and no indexed columns (or expressions) changed, PostgreSQL can avoid writing new index entries.

However, modifying `tags`, `attributes`, `title`, or `description` (and thus generated `search_vector`) affects the relevant indexes. A non-HOT `UPDATE` also forces other indexes on the table to add pointers for the new tuple location.

Never estimate write cost solely from newly added array elements while ignoring the rest of the table's indexes.

### 23.2. Does Updating JSONB Modify Just One Key In Place?

A statement:

```sql
UPDATE gin_lab.documents
SET attributes = jsonb_set(
    attributes,
    '{features,fts}',
    'true'::JSONB
)
WHERE doc_id = 102;
```

constructs a new JSONB value at the SQL level; PostgreSQL MVCC writes a new tuple version for the `UPDATE`. Never assume JSONB or GIN performs zero-cost in-place updates on a single nested key.

This statement also updates GIN entries and generates WAL. Run it only in the lab when intentionally modifying data.

---

## 24. fastupdate and the GIN Pending List

GIN commonly uses `fastupdate` to boost write throughput by buffering new index entries into a **pending list** first, then merging them into the main index structure during cleanup.

Conceptual flow:

```text
INSERT / UPDATE
     |
     v
GIN fastupdate enabled
     |
     v
Pending list (not yet merged into main tree)
     |
     +--> Queries must also scan relevant pending entries
     |
     v
Cleanup / VACUUM / eligible triggers
     |
     v
GIN main index structure
```

### 24.1. Why Is the Pending List Helpful?

If every `INSERT` immediately updated dozens of scattered keys in the main GIN tree, writes would incur heavy random I/O. The pending list batches part of that work, improving write throughput in many workloads.

Yet this **defers work** rather than eliminating it.

### 24.2. Consequences of a Large Pending List

- Read queries must scan the pending list, adding read latency.
- When cleanup triggers, a noticeable spike in CPU and I/O can occur.
- If autovacuum and cleanup lag behind `INSERT`/`UPDATE` rates, latency becomes erratic.
- WAL and maintenance costs still apply.

This explains why GIN write latencies can look spiky: many fast writes punctuated by pending-list flush pauses.

### 24.3. gin_pending_list_limit and fastupdate

Key settings:

- Index storage parameter `fastupdate`.
- Pending list size cap `gin_pending_list_limit` (configured globally or via reloption).
- `VACUUM`/autovacuum frequency and cleanup thresholds.
- Write rate and index size.

Lab-only adjustment example:

```sql
ALTER INDEX gin_lab.idx_documents_tags_gin
SET (fastupdate = off);
```

Disabling `fastupdate` changes the write path; it **does not automatically flush existing pending entries** immediately. Do not toggle this blindly in production.

### 24.4. Inspecting the Pending List

If an administrator has installed and granted access to the `pgstattuple` extension, PostgreSQL provides GIN inspection functions such as:

```sql
-- Only when pgstattuple is installed and authorized:
SELECT *
FROM pgstatginindex(
    'gin_lab.idx_documents_tags_gin'::REGCLASS
);
```

Output includes pending pages and pending tuples depending on version. This extension is not required to learn the core concepts; never install extensions unapproved in production.

### 24.5. Role of VACUUM

`VACUUM` keeps tables and indexes healthy as `UPDATE`/`DELETE` create dead tuples, and also cleans up the GIN pending list.

Never disable autovacuum to save CPU while expecting GIN to remain stable. Maintenance tuning balances write throughput, size, query latency, and `VACUUM` progress.

---

## 25. GIN with VACUUM, REINDEX, and Index Bloat

Heavy `UPDATE`/`DELETE` churn can leave indexes holding dead entries or fragmented free space awaiting reuse.

### 25.1. Regular VACUUM

```sql
VACUUM (ANALYZE) gin_lab.documents;
```

Run this outside an explicit `BEGIN ... COMMIT` block in the lab database. `VACUUM` is not a command to “shrink every index to its minimum byte size,” but rather cleans obsolete entries and enables space reuse under PostgreSQL's rules.

### 25.2. REINDEX

When bloat or structural issues genuinely call for rebuilding, `REINDEX` can be used following proper operational procedures:

```sql
-- Illustrative only; do not run casually in production:
REINDEX INDEX gin_lab.idx_documents_tags_gin;
```

`REINDEX` consumes disk, CPU, I/O, and WAL, and acquires locks depending on execution mode. Concurrent modes have specific version, transaction, and scheduling constraints.

### 25.3. Don't Drop a GIN Index Just Because It Is Large

A large GIN index can still be worth every byte if containment or FTS queries are critical. Weigh:

- Query latency and usage frequency.
- Index size and growth rate over time.
- `INSERT`/`UPDATE` write overhead.
- `VACUUM`/autovacuum behavior.
- Keyword selectivity.
- Whether a narrower expression or partial index could replace it.
- Semantic or performance impacts if dropped or switched to another operator class.

---

## 26. Partial GIN Indexes

If a large documents table has a `published` flag and only public documents are searched, a partial GIN index can help:

```sql
-- Pattern on a hypothetical table with published BOOLEAN.
CREATE INDEX idx_articles_public_search_gin
ON articles
USING GIN (search_vector)
WHERE published = true;
```

Queries targeting that index must include the matching predicate:

```sql
SELECT article_id, title
FROM articles
WHERE published = true
  AND search_vector @@ plainto_tsquery('english', 'database');
```

Benefits:

- Index covers only rows matching the predicate.
- Smaller footprint and zero maintenance for writes outside the subset (other than predicate checks).
- Especially worthwhile when public rows are a small fraction of the table.

Trade-offs:

- `UPDATE` changing `published` adds or removes index membership.
- Queries omitting the predicate cannot use the partial index.
- PostgreSQL must prove the query implies the predicate; parameterized prepared statements may fail this proof in generic plans.

Do not add a partial index simply because a boolean column exists; measure the workload first.

---

## 27. GIN, GiST, and B-tree: A Selection Flow

```text
What kind of search is needed?
       |
       +--> ID / scalar equality / range / ORDER BY
       |         |
       |         v
       |       B-tree
       |
       +--> Array tags contains / overlaps
       |         |
       |         v
       |       GIN array_ops
       |
       +--> JSONB containment / key existence
       |         |
       |         v
       |       GIN jsonb_ops / jsonb_path_ops
       |
       +--> Full-text keyword search
       |         |
       |         v
       |       tsvector + GIN (or benchmark vs. GiST)
       |
       +--> Substring / character fuzzy matching
       |         |
       |         v
       |       pg_trgm + GIN/GiST
       |
       +--> Ranges / geometry / other k-NN nearest neighbor
                 |
                 v
          Consider GiST / SP-GiST / specialized AM
```

### 27.1. GIN vs. GiST for Full-Text Search

Both GIN and GiST offer text-search operator classes in PostgreSQL. GIN is typically preferred for read-heavy FTS with many lexemes; GiST uses lossy signature trees with different write/read trade-offs and more rechecks.

Never generalize without benchmarking. Under update-heavy workloads, varying document sizes, and specific latency goals, either method can have distinct advantages.

### 27.2. B-trees Don't Disappear When Using GIN

A single table often needs:

- B-tree for `PRIMARY KEY`.
- B-tree on `created_at` for time-ordered pagination.
- GIN on `tags`.
- GIN on `search_vector`.

Each index serves a distinct role, which is why you must weigh **combined write and maintenance cost**.

### 27.3. Should You Put Multiple Columns in One GIN Index?

PostgreSQL supports multi-column GIN indexes when each column has a compatible GIN operator class (extensions like `btree_gin` provide GIN opclasses for scalar types).

However, do not view multi-column GIN as a left-to-right ordered composite B-tree. Design around specific operators and query patterns, and compare against separate single-column indexes combined via `BitmapAnd`.

---

## 28. Combining Ranking, Filtering, and Pagination

A document search API often needs to:

1. Enforce tenant/access permissions.
2. Filter tags/JSONB attributes.
3. Match FTS lexemes.
4. Compute rank scores.
5. Sort deterministically and paginate.

Lab example:

```sql
WITH search_input AS (
    SELECT plainto_tsquery(
        'simple', 'postgresql search'
    ) AS q
)
SELECT
    d.doc_id,
    d.title,
    ts_rank(d.search_vector, s.q) AS relevance
FROM gin_lab.documents AS d
CROSS JOIN search_input AS s
WHERE d.tags @> ARRAY['postgresql']::TEXT[]
  AND d.search_vector @@ s.q
ORDER BY relevance DESC, d.doc_id ASC
LIMIT 10;
```

### 28.1. Why Include a Tie-Breaker?

Two documents can receive identical relevance scores. Adding `doc_id ASC` (`ORDER BY relevance DESC, doc_id ASC`) ensures deterministic ordering across ties.

For large-scale pagination with complex filters, consider keyset/seek pagination where feasible rather than assuming large `OFFSET` values are cheap.

### 28.2. Search Ranking Is Not Authorization

In multi-tenant applications, every search query must enforce tenant/permission filters or Row-Level Security policies.

Never let GIN fetch documents and filter permissions in the frontend; enforce authorization server-side in the database/query layer.

### 28.3. Update Latency and Caches

Generated `tsvector` columns and GIN indexes update transactionally on write, so subsequent queries on the primary with a fresh snapshot see updates right after `COMMIT`. However, reads from asynchronous replicas or external caches/search services can lag due to replication or invalidation delays.

Do not confuse **PostgreSQL primary consistency** with end-to-end freshness across a distributed search stack.

---

## 29. Common Mistakes and Misconceptions

| Misconception | Reality |
| --- | --- |
| “GIN is just a faster B-tree.” | GIN is an inverted index for multi-component keys; mechanics and queries differ |
| “Adding GIN on TEXT enables full-text search.” | FTS requires `tsvector`/`tsquery` or matching expressions |
| “A GIN index accelerates every operator.” | Requires matching operator class and query expression |
| “Array `= ANY` always uses GIN.” | GIN `array_ops` mainly serves array operators like `@>` and `&&` |
| “`tags @> ARRAY[a,a]` requires two copies of `a`.” | Array containment ignores element multiplicity |
| “JSONB `@>` performs substring matching.” | It checks structural and value containment |
| “`attributes ? 'fts'` finds nested keys.” | `?` on JSONB inspects top-level keys only |
| “`jsonb_path_ops` supports `?`/`?|`/`?&`.” | No; use `jsonb_ops` if those operators are needed |
| “`jsonb_path_ops` always beats `jsonb_ops`.” | It trades off key-existence support and empty structures |
| “Using `@?` guarantees an index scan.” | Indexability depends on JSONPath expression and opclass |
| “An index on `attributes` automatically covers `(attributes->'x') ? 'y'`.” | May need an expression index or query rewrite |
| “`LIKE '%abc%'` is FTS.” | FTS matches lexemes; substrings use `LIKE`/trigrams |
| “`plainto_tsquery` parses user `AND`/`OR` syntax.” | It treats input as plain words; use `to_tsquery` or `websearch_to_tsquery` |
| “`to_tsquery` accepts arbitrary raw user strings.” | Requires valid syntax and errors on invalid input |
| “Built-in FTS segments Vietnamese well.” | Requires dedicated segmentation/diacritic handling as needed |
| “English stemming works for Vietnamese.” | English dictionaries do not handle Vietnamese linguistics |
| “`unaccent` solves all Vietnamese search needs.” | It only strips diacritics; it does not segment words |
| “GIN returns rows sorted by `ts_rank`.” | GIN finds candidates; ranking and sorting are separate work |
| “`ts_rank` is an exact probability.” | It is an algorithmic relevance score |
| “`ts_headline` output is safe HTML.” | Must escape/sanitize to prevent XSS |
| “`pg_trgm` searches by meaning.” | It measures character-level trigram similarity |
| “Single-character `ILIKE` is super fast with trigram.” | Too few trigrams yields low selectivity |
| “If an index exists, PostgreSQL must use it.” | The planner chooses `Seq Scan` when cheaper |
| “`Recheck Cond` means the index is wrong.” | Recheck is normal for lossy bitmaps or index verification |
| “`EXPLAIN` cost is in milliseconds.” | Cost is in relative planner units |
| “The more GIN indexes, the better.” | `INSERT`/`UPDATE`, WAL, `VACUUM`, and storage costs grow |
| “`fastupdate` eliminates write costs.” | It defers work to the pending list |
| “The pending list doesn't affect reads.” | Read queries must also scan the pending list |
| “`VACUUM` always shrinks index files back to the OS.” | It primarily cleans dead entries and enables reuse |
| “`REINDEX` has no lock, disk, or WAL cost.” | It is a heavyweight maintenance operation needing planning |
| “Indexing a JSONB column makes every query fast.” | Selectivity, operators, and data shape decide |
| “GIN handles authorization automatically.” | Always enforce `WHERE`/RLS/authorization independently |

---

## 30. Practice Exercises

### Exercise 1 — Explain the Inverted Index

Using the tags from docs 101, 102, and 103, sketch the posting lists for `postgresql`, `gin`, and `fts`. Which `doc_id`s are in the intersection of `postgresql` and `fts`?

### Exercise 2 — Array Containment of Multiple Tags

Write a query selecting documents with both `postgresql` and `fts` tags using `@>`. Expect docs 103 and 106.

### Exercise 3 — Array Overlap

Find documents with at least one of `array` or `trigram` using `&&`. How does that differ from containment?

### Exercise 4 — Contained-By Set Check

Write `tags <@ ARRAY[...]` with an allowed tag set. Explain why every element of the left array must belong to the right array.

### Exercise 5 — Duplicate Array Elements

Run `ARRAY['a'] @> ARRAY['a','a']`. Why doesn't the result mean the left array holds two distinct copies of `'a'`?

### Exercise 6 — Nested JSONB Containment

Find documents where `features.fts = true` using `@>`. Predict the matching `doc_id`s in the lab.

### Exercise 7 — JSONB Array Containment

Find documents whose `skills` contain `sql` using `@>`. Why do JSONB arrays containing extra elements still match?

### Exercise 8 — JSONB Top-Level Existence

Compare `attributes ? 'fts'` against `(attributes -> 'features') ? 'fts'`. Why do their results differ?

### Exercise 9 — JSONB ?| and ?&

Write queries finding objects having at least one of `type`, `unknown`, and objects having both `type` and `skills`, using the appropriate operators.

### Exercise 10 — jsonb_ops vs. jsonb_path_ops

Explain which operators each opclass supports. If an app mainly uses `?` existence checks, which should you try? If it mainly runs selective containment, which is worth benchmarking?

### Exercise 11 — Empty JSONB Structures

Test containment `attributes @> '{"features":{}}'`. Why might `jsonb_path_ops` lack useful index entries for this query?

### Exercise 12 — JSONPath

Write `@?` to match skill `sql` and `@@` to check `features.fts == true`. Explain why not all JSONPath queries leverage the index equally.

### Exercise 13 — Expression Index

Create a GIN index on `(attributes -> 'features')`. Write a query matching that expression and compare it with top-level JSONB containment.

### Exercise 14 — TSVECTOR

Run `to_tsvector('simple', ...)` and `to_tsvector('english', ...)` on the same English sentence. Observe lexemes, positions, and stemming.

### Exercise 15 — plainto_tsquery

Build an FTS query for `full text` with `plainto_tsquery`, and filter `search_vector` with `@@`. Why can results differ from an adjacent phrase match?

### Exercise 16 — phraseto_tsquery

Write a query matching the ordered phrase `full text`. Compare the `tsquery` produced by `phraseto_tsquery` against `plainto_tsquery`.

### Exercise 17 — websearch_to_tsquery

Test `"full text" OR jsonb -trigram` and print the generated `TSQUERY`. Why is this safer than `to_tsquery` for user-entered web search syntax?

### Exercise 18 — Ranking

Find documents matching `full text`, compute `ts_rank`, and `ORDER BY rank DESC, doc_id ASC`. Why doesn't GIN automatically supply rank order?

### Exercise 19 — Safe ts_headline

Use `ts_headline` to generate snippets for FTS matches. If user-supplied raw text contains malicious HTML, what must the frontend do before rendering?

### Exercise 20 — Vietnamese Text

Test `to_tsvector('simple', 'Tìm kiếm văn bản tiếng Việt')`. Why shouldn't syllable tokenization be mistaken for complete word segmentation?

### Exercise 21 — Removing Diacritics

Explain the difference between `tìm kiếm` and `tim kiem`. Why can `unaccent` help without replacing a Vietnamese word segmenter?

### Exercise 22 — pg_trgm

In an authorized lab database, create `pg_trgm`, build a `gin_trgm_ops` GIN index on `title`, and test `ILIKE '%postgre%'`. What search pattern does this solve that plain FTS lexemes do not directly solve?

### Exercise 23 — Similarity

Test `%` and `similarity(title, 'PostgreSQL GIN indez')`. Why is string similarity neither semantic similarity nor a certainty percentage?

### Exercise 24 — GIN Query Plans

Run `EXPLAIN (ANALYZE, BUFFERS)` for a `tags @>` query. Why might PostgreSQL pick `Seq Scan` on an eight-row table? What does `SET LOCAL enable_seqscan = off` teach you, and what does it fail to prove?

### Exercise 25 — BitmapAnd

Combine `tags @> ...`, `attributes @> ...`, and `search_vector @@ ...`. Must the planner use all three GIN indexes? When might it use one index and filter the rest?

### Exercise 26 — GIN Pending List

Explain `fastupdate`, the pending list, and cleanup. Why can `INSERT`s be fast initially yet encounter periodic I/O spikes during cleanup?

### Exercise 27 — UPDATE and Write Amplification

Update a document's `tags` from 3 tags to 10 tags; analyze heap/MVCC, GIN index updates, WAL, and `VACUUM`. Why can't total write cost be measured just by counting the new tags?

### Exercise 28 — Partial GIN

Suppose `articles` has `published BOOLEAN`. Write a partial GIN index on `search_vector` for published rows only. When can a query use it? What happens when `published` changes from `false` to `true`?

### Exercise 29 — GIN or B-tree?

Choose suitable indexes for four queries: ID equality, tags contains, JSONB key existence, and `ORDER BY created_at DESC`. Explain why one index type cannot cover everything.

### Exercise 30 — Designing Product Search

An API requires filtering tags, JSONB properties, phrase search, ranking, returning 20 results, typo tolerance, and unaccented Vietnamese search. Design the FTS/`pg_trgm`/normalization pipeline, authorization rules, indexes to benchmark, and a test suite measuring accuracy and latency.

---

## 31. Production GIN Deployment Checklist

| Question | What to Verify |
| --- | --- |
| Is data an array, JSONB, or text? | Actual stored column type |
| Which operations do users run? | Contains, overlap, existence, lexeme, substring |
| Does a GIN opclass support the operator? | Verify `array_ops`/`jsonb_ops`/`path_ops`/`tsvector_ops`/`trgm` |
| Is the index on the column or an expression? | Must match `WHERE` predicates |
| Does JSONB need `?`/`?|`/`?&`? | If yes, prefer `jsonb_ops` |
| Does JSONB mostly use `@>`? | Benchmark `jsonb_ops` vs. `jsonb_path_ops` |
| Do queries search empty JSON structures? | Account for `jsonb_path_ops` limitations |
| Are many array/JSON keys very common? | Check selectivity and posting list size |
| Do many rows share the same key? | Measure candidate count and rechecks |
| Which FTS dictionary config is used? | Keep index and query configs aligned |
| Are phrase/proximity queries needed? | Use `phraseto_tsquery` and keep positions |
| Is ranking required? | `ts_rank`/`ts_rank_cd` and explicit sorting |
| Is highlighting required? | `ts_headline` + HTML escaping/sanitizing |
| Is Vietnamese text involved? | Word segmentation, Unicode, diacritics, normalization |
| Are both English and Vietnamese used? | Per-language config and tokenization tests |
| Are substring or typo searches needed? | `pg_trgm`/`LIKE`/similarity thresholds |
| Are search terms very short? | Trigrams may lose selectivity |
| Is time-based ordering required? | Pair with B-tree or supporting indexes |
| Is tenant/authorization scoping required? | Server-side `WHERE`/RLS |
| Is the table update-heavy? | Evaluate GIN, WAL, and HOT impact |
| Could the pending list grow large? | Tune `fastupdate`, cleanup, autovacuum |
| Is `VACUUM` keeping pace? | Monitor stats, logs, and bloat |
| Would a partial index help? | Check query predicates and membership churn |
| Did you inspect real `EXPLAIN` output? | `Seq Scan`, `Bitmap Index/Heap`, `Recheck` |
| Did you measure multiple runs? | Warm vs. cold cache, data size, concurrency |
| Is there index bloat? | Monitor relation sizes, maintenance, rebuild if needed |
| Should `tsvector` be a generated column? | Weigh schema storage vs. index maintenance |
| Is a dictionary/tokenizer migration planned? | Rebuild vectors/indexes and test search regression |
| Does text contain personal data? | Auth, logging, snippet XSS/privacy |
| Are replicas or search caches used? | Verify result freshness and lag |
| Did you benchmark reads **and writes**? | Avoid one-sided optimization |
| Do you have language and typo test cases? | Ground truth for relevance quality |

## Conclusion

**GIN — Generalized Inverted Index** is PostgreSQL's powerhouse when a single row stores **multiple components that must be searched individually**. Instead of indexing one scalar key per row, GIN maps from individual elements, lexemes, or trigrams to the rows containing them.

Essential principles:

- For **arrays**, GIN `array_ops` accelerates containment, contained-by, and overlap via operators like `@>`, `<@`, and `&&`. Never assume `= ANY(tags)` gets the same index treatment automatically.
- For **JSONB**, `jsonb_ops` flexibly supports containment and key existence, whereas `jsonb_path_ops` often shines for selective containment/JSONPath yet lacks direct support for `?`, `?|`, and `?&`.
- For **full-text search**, PostgreSQL relies on `tsvector`, `tsquery`, and `@@`. GIN finds matching lexemes; `ts_rank` and `ts_headline` handle ranking and snippets—they neither make rank pre-sorted in the index nor sanitize HTML.
- For **Vietnamese**, plan explicitly for word segmentation, diacritics, and dictionary rules. Default `'simple'` or `'english'` configs do not solve Vietnamese linguistics; `unaccent` handles only part of normalization.
- For **substring/fuzzy matching**, `pg_trgm` adds capabilities distinct from FTS, usable with either GIN or GiST depending on query patterns.
- When reading **EXPLAIN**, GIN typically executes via bitmap scans and may perform rechecks. On very small tables, `Seq Scan` is often optimal.
- **Write and maintenance costs** are part of every decision: abundant lexemes, JSON keys, or trigrams enlarge indexes, pending-list cleanups can create latency spikes, and `UPDATE`s still incur MVCC and WAL work.
- Never pick an index from a column name alone: base your design on **operators, `WHERE` expressions, selectivity, write costs, sorting requirements, and authorization**.

Understanding both inverted-index mechanics and linguistic and operational trade-offs lets you build PostgreSQL queries over arrays, JSONB, and text that are both semantically accurate and backed by effective execution plans—rather than adding GIN out of habit and hoping every search is fast.
