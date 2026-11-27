# GIN, GiST Indexes, and Query Plan Verification in PostgreSQL

When users search for a phrase across a few thousand documents, direct queries may be fast enough. However, when an application stores millions of articles, product descriptions, support notes, or business documents, evaluating text processing row by row on every search can consume huge amounts of CPU and I/O. PostgreSQL provides **Full Text Search (FTS)** with `tsvector`, `tsquery`, the `@@` matching operator, and specialized index types, notably **GIN** and **GiST**.

A typical query:

~~~sql
SELECT article_id, title
FROM articles
WHERE search_vector @@ plainto_tsquery('simple', 'postgresql gin');
~~~

If `search_vector` has an appropriate GIN or GiST index, PostgreSQL can probe the index to locate candidate rows rather than evaluating the search expression across the whole table. Yet **having an index does not mean the planner will always use it**: the plan still depends on row count, selectivity, exact expression written, query parameters, cost estimates, and statistics freshness.

This lesson belongs to the **Text Search** chapter of the *Database Engine Relational PostgreSQL* module. It moves from FTS concepts, creating `tsvector`/`tsquery`, comparing GIN and GiST, and the difference between an **index hit** and a **recheck**, through lab design, reading `EXPLAIN (ANALYZE, BUFFERS)`, index maintenance, and diagnosing queries that skip indexes.

## 1. Mental Map: From Text String to Search Results

An FTS system typically has four stages:

~~~text
               DATA
title/body: "PostgreSQL GIN Index and Query Planning"
                 |
                 | to_tsvector(config, document)
                 v
          SEARCHABLE VECTOR
lexemes + position/weight metadata
                 |
                 | GIN or GiST index
                 v
       CANDIDATE MATCHING ROWS
                 ^
                 | @@ operator
                 |
                 | plainto_tsquery / websearch_to_tsquery / ...
                 |
User input: "gin index"
                 |
                 v
             TSQUERY
                 |
                 v
          Planner + Executor
                 |
                 v
        Rows matched + ranking
~~~

Three layers must be kept separate:

1. **Semantics**: which words become lexemes, how queries are parsed, AND/OR/phrase logic.
2. **Access path**: which candidates a GIN/GiST index identifies.
3. **Execution**: which plan the planner chooses, whether heap rechecking is required, how many buffers are read, and how many rows are ranked.

Confusing these three layers leads to false conclusions like "creating GIN eliminates `to_tsvector`", "GiST returns wrong rows due to false positives", or "EXPLAIN showing Seq Scan means the index is broken".

## 2. FTS Differs from Ordinary Substring Search

Compare:

~~~sql
SELECT *
FROM articles
WHERE body ILIKE '%postgres%';
~~~

with:

~~~sql
SELECT *
FROM articles
WHERE search_vector @@ plainto_tsquery('simple', 'postgres');
~~~

The two queries have **different semantics**.

- `ILIKE '%postgres%'` searches for a case-insensitive substring per current matching and collation rules.
- FTS breaks documents into **lexemes** using a text search configuration, then matches against a `tsquery`.
- With a stemming configuration, words can be folded to roots or normalized.
- FTS is not inherently substring search; searching `post` does not automatically match every word containing `post`.
- An FTS query can use AND, OR, NOT, phrases, and lexeme prefix queries.

If the requirement is **substring** search, typo-tolerant fuzzy matching, or character-level autocomplete, consider `pg_trgm` or another suitable mechanism instead of misusing FTS GIN indexes.

## 3. Text Search Configurations Determine Lexemes

PostgreSQL provides text search configurations such as `simple` and `english`.

~~~sql
SELECT to_tsvector(
    'simple',
    'PostgreSQL provides GIN and GiST indexes'
);

SELECT to_tsvector(
    'english',
    'PostgreSQL provides indexes for searching documents'
);
~~~

### 3.1. Why do results differ?

A text search configuration specifies the parser, dictionaries, stop words, and normalization steps. The English configuration typically applies stemming and stop-word removal; `simple` behaves differently.

For instance, "searching" and "search" can collapse to the same lexeme under a stemming configuration. With `simple`, do not assume inflected variants fold to a common root.

### 3.2. Checking the default configuration

~~~sql
SHOW default_text_search_config;
~~~

For predictable queries, **specify the configuration explicitly** in both vector creation and query construction rather than inadvertently relying on the session default.

### 3.3. Index and query configurations must align

If vectors are built with `simple` while queries use `english`, differing lexeme normalization can prevent expected matches. There is no rule where "GIN automatically translates from one dictionary to another".

### 3.4. Limitations with Vietnamese

PostgreSQL does not ship out of the box with a linguistically rich Vietnamese word-segmentation pipeline like specialized search engines. `simple` works for suitably segmented text or simple token lookups, whereas multi-syllable compound words, Vietnamese diacritics, synonyms, and typos may require custom dictionaries, tokenizers, or extensions.

Never label a Vietnamese query "linguistically accurate" merely because it uses `tsvector` and GIN.

## 4. What Does tsvector Contain?

`tsvector` represents a document after text analysis: **lexemes**, optionally with positions and weights. Example:

~~~sql
SELECT to_tsvector(
    'simple',
    'gin gist gin planner'
);
~~~

Conceptually, the output looks like:

~~~text
'gin':1,3 'gist':2 'planner':4
~~~

PostgreSQL normalizes and sorts lexemes, grouping multiple positions of the same term under a single lexeme entry.

### 4.1. Positions enable phrase and proximity queries

Positional metadata lets you evaluate conditions like "`gin` immediately precedes `gist`". Knowing only that "both words co-occur" is insufficient for that matching semantics.

### 4.2. Weights A, B, C, D

You can construct vectors from titles and bodies with distinct priority levels:

~~~sql
SELECT
    setweight(to_tsvector('simple', 'GIN index'), 'A')
    ||
    setweight(to_tsvector('simple', 'Article about database searching'), 'B');
~~~

Typically `A` is used for titles, `B` for bodies, and `C`/`D` for other fields. This is an application convention—PostgreSQL does not force titles to be `A`.

### 4.3. tsvector is not the original document

Vectors do not preserve full original text, punctuation, casing, or whitespace for verbatim retrieval. Keep original `title`/`body` columns when the app needs to display or quote text.

### 4.4. Avoiding NULL vectors

If `title`/`body` can be `NULL`, wrap with `coalesce(title, '')` and `coalesce(body, '')` when building vectors so `NULL` does not wipe out the expression.

## 5. What Is tsquery?

`tsquery` represents a search condition over lexemes and boolean/positional operators.

~~~sql
SELECT to_tsquery('simple', 'gin & gist');
SELECT to_tsquery('simple', 'gin | gist');
SELECT to_tsquery('simple', 'gin & !deprecated');
SELECT to_tsquery('simple', 'gin <-> gist');
~~~

| Operator | Meaning |
|---|---|
| `&` | AND; all conditions must hold |
| `\|` | OR; at least one condition must hold |
| `!` | NOT |
| `<->` | Phrase / two lexemes adjacent per semantics |
| `<N>` | Positional distance N per `tsquery` syntax |
| `:*` | Lexeme prefix matching |
| `:A`, `:B` | Restrict lexeme by weight |

Prefix example:

~~~sql
SELECT to_tsquery('simple', 'post:*');
~~~

This prefix term targets **lexemes** starting with `post`; it is not equivalent to matching substrings anywhere inside raw text.

### 5.1. Be careful concatenating SQL strings

Never concatenate raw user input into `to_tsquery` or SQL text:

~~~text
"SELECT ... WHERE vector @@ to_tsquery('simple', '" + input + "')"
~~~

Use prepared statements and appropriate `tsquery` constructor functions to avoid syntax errors and SQL injection.

### 5.2. to_tsquery requires tsquery syntax

For free-form user input, stray punctuation or malformed operators can raise syntax errors in `to_tsquery`. `plainto_tsquery` or `websearch_to_tsquery` are usually far safer for search boxes.

## 6. Query Constructors for Different Input Types

### 6.1. plainto_tsquery

~~~sql
SELECT plainto_tsquery(
    'simple',
    'gin gist'
);
~~~

Converts plain text into a query, normally joining matching words with AND.

### 6.2. phraseto_tsquery

~~~sql
SELECT phraseto_tsquery(
    'simple',
    'gin gist'
);
~~~

Used when adjacent word order and positions matter. Stop-word handling depends on the configuration.

### 6.3. websearch_to_tsquery

~~~sql
SELECT websearch_to_tsquery(
    'english',
    '"full text search" OR index'
);
~~~

Used for search-box/web-style syntax, supporting readable forms like quoted phrases and `OR`. Do not treat it as a parser for every advanced `tsquery` expression.

### 6.4. to_tsquery

~~~sql
SELECT to_tsquery(
    'simple',
    'postgresql & (gin | gist)'
);
~~~

Useful when the application wants explicit control over operators. Construct queries safely; never feed raw user text straight into `to_tsquery`.

### 6.5. Do not choose by "fastest function"

Pick the constructor matching **expected user semantics**. A query returning fewer rows may be faster yet wrong for the user; accurate results come before raw speed.

## 7. The @@ Operator Connects Vector and Query

Direct example:

~~~sql
SELECT
    to_tsvector('simple', 'GIN GiST planner')
    @@
    plainto_tsquery('simple', 'gin planner')
    AS is_match;
~~~

The boolean result is true because the document contains both required lexemes.

### 7.1. Common query pattern

~~~sql
WHERE search_vector @@ plainto_tsquery('simple', :search_text)
~~~

Use driver/framework bind parameters rather than manual SQL string concatenation.

### 7.2. Distinguish filtering from ranking

`@@` decides whether a row matches. `ts_rank` or `ts_rank_cd` computes relevance scores. Indexes help find candidates rather than sorting results by relevance automatically.

### 7.3. Combining search with business filters

~~~sql
WHERE status = 'published'
  AND tenant_id = 42
  AND search_vector @@ plainto_tsquery('simple', 'gin index')
~~~

The planner can combine access paths and filters. Index choices must reflect the full workload, not just a single `@@` condition.

## 8. What Is GIN?

**GIN (Generalized Inverted Index)** is an inverted index: from any key inside a composite value, the index maps directly to the rows containing that key.

For full-text search on `tsvector`, keys are typically **lexemes**.

~~~text
Lexeme -> posting list / posting tree of matching rows

'gin'        -> row 3, row 7, row 19, ...
'gist'       -> row 7, row 25, ...
'planner'    -> row 3, row 7, row 26, ...

Query: gin & planner
  -> find candidates having both lexemes
  -> verify full semantics when needed
~~~

### 8.1. Creating a GIN index on tsvector

~~~sql
CREATE INDEX articles_search_gin_idx
ON articles
USING GIN (search_vector);
~~~

This is template syntax assuming an `articles` table exists. The lab section sets up the full schema and table.

### 8.2. Why is GIN usually the default choice for FTS?

GIN offers fast lookups when queries filter by lexemes, especially on large document collections with selective conditions. GIN is generally PostgreSQL's recommended starting point for general-purpose FTS.

### 8.3. GIN does not store all tsvector metadata

A GIN index on `tsvector` focuses on **lexemes** and does not store full positional and weight details for every query type. For weighted or phrase/proximity queries, the executor may need to **recheck the heap row/vector** to verify full conditions.

### 8.4. Read speed comes with write cost

An inverted index requires maintenance work when inserting or updating documents containing many lexemes. Storage size and write latency must be factored in.

## 9. What Is GiST in Full-Text Search?

**GiST (Generalized Search Tree)** is a general indexing framework supporting many operator classes. For `tsvector`, GiST typically uses a **bit signature** over a document's lexeme set to represent potential word presence.

~~~text
Document 1: gin, gist, planner
    |
    v
GiST signature: corresponding bits are set

Query: planner
    |
    v
Check signature:
  matching bits? -> row MIGHT match
  missing bits?  -> definitely excluded
~~~

### 9.1. Creating a GiST index

~~~sql
CREATE INDEX articles_search_gist_idx
ON articles
USING GIST (search_vector);
~~~

### 9.2. GiST tsvector is typically lossy

Multiple lexemes can hash onto overlapping bits. Consequently, the index can flag **a row as a candidate even though its actual `tsvector` does not match the query**.

This is a **false positive during candidate lookup**, not PostgreSQL returning wrong final rows. The executor performs a recheck when needed to filter out non-matching rows.

### 9.3. Tuning signature length

With a `tsvector_ops` operator class supporting options, you can try:

~~~sql
CREATE INDEX articles_search_gist_long_idx
ON articles
USING GIST (
    search_vector tsvector_ops(siglen=256)
);
~~~

Longer signatures can reduce bit collisions/false positives, while increasing index size and associated costs. Exact syntax and parameter limits depend on PostgreSQL version and operator class, so verify on the target server.

### 9.4. GiST is not "always slow"

GiST can be beneficial for specific workloads or operator-class properties. For mainstream FTS, GIN is usually the better place to start, though final decisions must come from measuring real queries and write costs.

## 10. Comparing GIN and GiST for tsvector

| Criterion | GIN | GiST |
|---|---|---|
| Core idea | Inverted mapping lexeme → rows | Approximate signature for lexeme set |
| Full-text search | Usually preferred | Supported |
| False positives from signature | Not via GiST-style signatures | Can occur |
| Phrase/weight recheck | May be needed | May be needed, often due to signature |
| INSERT/UPDATE cost | Can be high with many lexemes | Different trade-off profile |
| Size | Depends on lexemes/postings | Depends on signatures/structure |
| `siglen` tuning | Not a GiST-style signature parameter | May support `siglen` |
| Bitmap plans | Common | Common |
| Pre-sorted by relevance | No | No |
| Substring `ILIKE '%abc%'` by default | Not with `tsvector_ops` | Not with `tsvector_ops` |
| Depends on operator class | Yes | Yes |
| Workload selection | Measure both reads and writes | Measure false positives and writes |

**Do not compare GIN and GiST as "one fast, one slow" across all datasets.** Know which operator class GIN/GiST uses, which query operators are run, how data is distributed, and how frequently rows update.

## 11. Operator Classes: GIN/GiST Do Not Understand Every Operator Automatically

A PostgreSQL index has more than an access method like `GIN` or `GIST`. It also uses an **operator class** defining which operators the index supports.

Example:

~~~sql
CREATE INDEX articles_search_gin_idx
ON articles USING GIN(search_vector);
~~~

For `tsvector`, PostgreSQL picks the FTS operator class automatically.

By contrast, creating a GIN index with `gin_trgm_ops` on a `text` column to accelerate `ILIKE` uses a **different** search mechanism: keys are trigrams, not an FTS lexeme tree.

### 11.1. Do not mix up operators

- FTS: `tsvector @@ tsquery`.
- Trigram search: `LIKE`, `ILIKE`, or similarity operators per extension/operator class.
- Equality on ID keys: usually B-tree.

### 11.2. One GIN index does not solve every text predicate

`GIN(search_vector)` does not automatically accelerate `body ILIKE '%gin%'` when the query does not use expressions and operators supported by that index.

### 11.3. Full text is not fuzzy matching by default

FTS matches lexemes after dictionary analysis. Typos, diacritic variations, and mid-word substrings may require an additional processing layer.

## 12. Why Can a Query Need a Recheck?

An FTS query may execute as:

~~~text
Bitmap Index Scan (GIN/GiST)
        |
        v
Candidates from index
        |
        v
Bitmap Heap Scan
  - Recheck Cond
  - discard false positives if any
        |
        v
Exact @@ results
~~~

### 12.1. Recheck with GiST

GiST signatures can set overlapping bits for distinct lexemes. The executor must inspect the original `tsvector` to confirm a candidate actually satisfies the query.

### 12.2. Recheck with GIN

GIN lexeme postings suffice for basic conditions, yet phrase/position details and weights are not stored completely in the index, so rows may be fetched and rechecked for full semantics.

### 12.3. Bitmap lossiness is another cause

When a bitmap heap scan hits memory limits, it can store **lossy bitmap pages** instead of exact tuple IDs (TIDs). Rechecking is then needed due to **bitmap memory**, independent of GiST signature collisions.

### 12.4. Recheck does not mean wrong results

Candidate false positives are filtered out before the query returns, preserving exact semantics. Users will never see non-matching rows merely because a GiST index is lossy.

### 12.5. Reading EXPLAIN properly

Seeing `Recheck Cond` alone **does not prove how many false positives occurred**. Inspect `Rows Removed by Index Recheck`, `Heap Blocks: exact/lossy`, and surrounding node metrics in `EXPLAIN (ANALYZE, BUFFERS)`.

## 13. Lab: Preparing the Database and Verification Table

The commands below use a **test database** with an isolated schema. Never run DDL/DROP on production. If `search_lab` already holds data, pick a different schema name instead of deleting it.

### 13.1. Create the schema

~~~sql
CREATE SCHEMA search_lab;
~~~

### 13.2. Create the articles table

~~~sql
CREATE TABLE search_lab.articles (
    article_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    status TEXT NOT NULL
        CHECK (status IN ('draft', 'published')),
    published_at TIMESTAMPTZ NOT NULL,
    search_vector TSVECTOR GENERATED ALWAYS AS (
        setweight(
            to_tsvector('simple'::regconfig, coalesce(title, '')),
            'A'
        )
        ||
        setweight(
            to_tsvector('simple'::regconfig, coalesce(body, '')),
            'B'
        )
    ) STORED
);
~~~

**Version note:** Stored generated columns are supported starting in PostgreSQL 12. This syntax uses functions/expressions permitted in generated expressions, with `simple` declared explicitly. On older PostgreSQL versions, use an alternative vector storage/update mechanism.

### 13.3. Why is a generated column helpful?

The application writes `title`/`body`; PostgreSQL computes `search_vector` from the declared expression on insert/update. Queries can then read the precomputed vector instead of running `to_tsvector` over `body` for every row on every search.

### 13.4. Title and body weights

`setweight(..., 'A')` on title and `'B'` on body let queries rank or filter by weight. **Weights do not make the index sort by relevance automatically**; the planner still evaluates scores when `ORDER BY` ranks results.

## 14. Loading 60,000 Test Records

To observe differences between `Seq Scan` and index paths, the lab populates more rows than a handful of manual examples.

~~~sql
INSERT INTO search_lab.articles(
    tenant_id, title, body, status, published_at
)
SELECT
    (n % 100) + 1,
    CASE
        WHEN n % 23 = 0
            THEN 'PostgreSQL full text search GIN GiST'
        WHEN n % 7 = 0
            THEN 'Hoc Java voi PostgreSQL'
        ELSE
            'Tai lieu nghiep vu so ' || n::text
    END,
    CASE
        WHEN n % 23 = 0
            THEN 'gin gist index planner explain tsquery tsvector'
        WHEN n % 7 = 0
            THEN 'jdbc java connection query'
        ELSE
            'ghi chu van hanh thong ke ban ghi'
    END,
    CASE
        WHEN n % 5 = 0 THEN 'draft'
        ELSE 'published'
    END,
    TIMESTAMPTZ '2026-01-01 00:00+00'
      + n * INTERVAL '1 minute'
FROM generate_series(1, 60000) AS gs(n);
~~~

### 14.1. Conditions present in the dataset

- Roughly 1/23 of rows contain lexemes related to `GIN`, `GiST`, and `planner`.
- Many other rows have `postgresql` in the title without containing `planner`.
- `status` has two values.
- `tenant_id` has 100 values.
- `published_at` is a timestamp allowing combined time-range filtering.

This is **synthetic** data with an artificial modulo distribution. Never extrapolate lab timings directly to production.

### 14.2. Update statistics

~~~sql
ANALYZE search_lab.articles;
~~~

The planner uses statistics to estimate matching row counts. Even before creating GIN/GiST, statistics guide access-path decisions.

### 14.3. Test a condition

~~~sql
SELECT COUNT(*)
FROM search_lab.articles
WHERE search_vector @@ plainto_tsquery('simple', 'gin planner');
~~~

Actual row counts reflect the generated data distribution and lexemes, not a universal constant outside the lab.

## 15. Measuring Baseline Without GIN/GiST

Run the query:

~~~sql
EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
SELECT article_id, title
FROM search_lab.articles
WHERE search_vector @@ plainto_tsquery('simple', 'planner');
~~~

Because no FTS index exists yet in the lab, the planner may pick `Seq Scan` or `Parallel Seq Scan` depending on settings and table size.

### 15.1. What should you record?

| Metric | Meaning |
|---|---|
| `Seq Scan` | Sequential scan of the relation |
| `Filter` | Condition applied after reading rows |
| `Rows Removed by Filter` | Rows discarded by the filter at this node |
| `rows=...` | Planner's estimated row count |
| `actual rows=...` | Actual rows returned by the node |
| `Buffers: shared hit/read` | Buffer blocks accessed from cache/read |
| `Planning Time` | Time spent planning |
| `Execution Time` | Time spent executing |

### 15.2. Measure across multiple runs

The first run may pay cold-cache costs; later runs find pages warm in shared buffers or OS cache. Never claim an index speedup factor from a single measurement.

### 15.3. Keep the query identical when comparing

If your baseline used `'planner'` and after indexing you measure `'postgresql'`, the two queries have different selectivity and are not a valid direct comparison.

## 16. Testing a GIN Index in the Lab

### 16.1. Create the index

~~~sql
CREATE INDEX articles_search_gin_idx
ON search_lab.articles
USING GIN(search_vector);
~~~

### 16.2. Refresh statistics when needed

~~~sql
ANALYZE search_lab.articles;
~~~

`CREATE INDEX` is distinct from `ANALYZE`; having an index does not guarantee column statistics accurately describe the data.

### 16.3. Re-run the exact same query

~~~sql
EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
SELECT article_id, title
FROM search_lab.articles
WHERE search_vector @@ plainto_tsquery('simple', 'planner');
~~~

A plan using GIN may conceptually look like:

~~~text
Bitmap Heap Scan on articles
  Recheck Cond: (search_vector @@ ...)
  Heap Blocks: exact=...
  -> Bitmap Index Scan on articles_search_gin_idx
       Index Cond: (search_vector @@ ...)
~~~

This is an **illustrative diagram**, not guaranteed fixed output. PostgreSQL can choose a different plan for small tables, common terms, or different settings.

### 16.4. Index Cond is a key indicator

If `Bitmap Index Scan on articles_search_gin_idx` shows `Index Cond` on `@@`, the planner is using GIN to collect candidates.

### 16.5. Compare against baseline

Compare:

- Execution time across multiple runs.
- Buffers read/hit.
- Estimated vs actual rows.
- Heap blocks accessed.
- Candidate counts and rechecks.
- Planning time.
- Memory/temp disk usage if any.

**Do not conclude GIN is effective merely because it was chosen; measure the actual work saved on real workloads.**

## 17. Testing a GiST Index for Comparison

To compare fairly without two indexes competing on the same predicate and making planner choices harder to isolate, proceed sequentially in the **lab database**.

### 17.1. Record the GIN results first

Save the output and metrics from the previous section.

### 17.2. Drop the GIN index created in the lab

~~~sql
DROP INDEX search_lab.articles_search_gin_idx;
~~~

Run this only on an index **you created in a test database**, never in production.

### 17.3. Create GiST

~~~sql
CREATE INDEX articles_search_gist_idx
ON search_lab.articles
USING GIST(search_vector);

ANALYZE search_lab.articles;
~~~

### 17.4. Re-run the identical query

~~~sql
EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
SELECT article_id, title
FROM search_lab.articles
WHERE search_vector @@ plainto_tsquery('simple', 'planner');
~~~

A plan may show `Bitmap Index Scan on articles_search_gist_idx` and a `Bitmap Heap Scan` with rechecks.

### 17.5. Watch for false positives

Because GiST `tsvector` uses lossy signatures, candidate counts can exceed true matches. Look for `Rows Removed by Index Recheck` in the plan if displayed.

### 17.6. Restore GIN to continue the lab

~~~sql
DROP INDEX search_lab.articles_search_gist_idx;

CREATE INDEX articles_search_gin_idx
ON search_lab.articles
USING GIN(search_vector);
~~~

Later sections assume GIN has been recreated. To explore longer GiST signatures, use another test database or swap in GiST at the comparison step.

## 18. Longer GiST Signatures Can Reduce False Positives

With an appropriate operator class and version, test a tuned GiST index:

~~~sql
CREATE INDEX articles_search_gist_sig256_idx
ON search_lab.articles
USING GIST (
    search_vector tsvector_ops(siglen=256)
);
~~~

### 18.1. Purpose of siglen

Longer signatures reduce bit collisions, lowering the number of non-matching rows rechecked. However, index size grows and write/maintenance costs shift.

### 18.2. Measure instead of guessing

Compare:

- Index size.
- `Rows Removed by Index Recheck`.
- Buffers/heap blocks.
- Execution time.
- DML overhead under update workloads.

### 18.3. Do not keep all three indexes by default

In production, keeping redundant indexes inflates `INSERT`/`UPDATE` overhead and storage. A lab can keep multiple indexes for learning; real designs pick based on measured workloads.

### 18.4. Watch version requirements

Some operator-class options, syntax, and parameter bounds vary across PostgreSQL versions. Verify support on the target server before putting them into migrations.

## 19. Reading EXPLAIN: Seq Scan, Index Scan, Bitmap Scan

### 19.1. Seq Scan

~~~text
Seq Scan on articles
  Filter: (search_vector @@ ...)
~~~

PostgreSQL reads the relation sequentially and evaluates the filter.

### 19.2. Bitmap Index Scan

~~~text
Bitmap Index Scan on articles_search_gin_idx
  Index Cond: (search_vector @@ ...)
~~~

This node scans the index to build a bitmap of candidate TIDs/pages.

### 19.3. Bitmap Heap Scan

~~~text
Bitmap Heap Scan on articles
  Recheck Cond: (search_vector @@ ...)
  Heap Blocks: exact=... lossy=...
~~~

This node visits candidate heap pages and verifies conditions when required.

### 19.4. Index Scan

Some access methods and query shapes produce `Index Scan` or other index plans. For GIN full-text search, `Bitmap Index Scan + Bitmap Heap Scan` is the standard shape; a plan does not need an `Index Scan` node to count as using an index.

### 19.5. Parallel Seq Scan

A query searching a very common lexeme may pick `Parallel Seq Scan` when the planner estimates scanning most of the table sequentially is cheaper than index lookups plus random heap reads.

**The plan node name alone is not enough to judge plan quality.**

## 20. Recheck Cond and Rows Removed by Index Recheck

In a plan:

~~~text
Bitmap Heap Scan on articles
  Recheck Cond: (search_vector @@ 'planner'::tsquery)
  Rows Removed by Index Recheck: 120
  Heap Blocks: exact=950
  -> Bitmap Index Scan ...
~~~

These numbers are an illustrative example, not measured lab output.

### 20.1. Recheck Cond

Shows the condition the heap scan may need to re-verify. It does not mean every candidate row is a false positive.

### 20.2. Rows Removed by Index Recheck

Reports how many rows were discarded by **re-evaluating the index condition on the heap**. For GiST signatures, this exposes false positives directly. Lossy bitmap pages can also produce recheck removals.

### 20.3. Heap Blocks exact vs lossy

- **exact**: the bitmap tracks exact TIDs for the heap block.
- **lossy**: the bitmap records that the page has candidates without tracking individual TIDs; the executor inspects all tuples on that page.

### 20.4. Two distinct causes of "lossy"

- GiST signature lossiness from hash bit collisions.
- Bitmap heap scan lossiness when bitmap memory is constrained.

Both trigger rechecks, yet you must distinguish the root cause when tuning.

### 20.5. Zero recheck removals does not prove an index is lossless

If a given query/dataset happens to avoid collisions and the bitmap stays exact, zero rows may be removed even with a lossy GiST signature. That is a measurement of one run, not a general property of the index.

## 21. AND, OR, and Negation Conditions in FTS

### 21.1. Words must appear together

~~~sql
SELECT article_id, title
FROM search_lab.articles
WHERE search_vector @@ to_tsquery('simple', 'gin & planner');
~~~

In the lab dataset, the set of articles having both lexemes is relatively small.

### 21.2. Either of two words

~~~sql
SELECT article_id, title
FROM search_lab.articles
WHERE search_vector @@ to_tsquery('simple', 'gin | postgresql');
~~~

`OR` can match far more rows than `AND`. When too many rows match, the planner may choose `Seq Scan` because the index saves few heap reads.

### 21.3. NOT does not replace a selective positive query

~~~sql
SELECT article_id
FROM search_lab.articles
WHERE search_vector @@ to_tsquery(
    'simple',
    'postgresql & !deprecated'
);
~~~

A standalone negation can match most of the table or struggle to use an index efficiently. Evaluate semantics and selectivity rather than expecting every `NOT` to turn into a fast index lookup.

### 21.4. Operators depend on syntax

`plainto_tsquery` parses plain text and does not share the semantics of `to_tsquery` with explicit AND/OR/NOT operators. Never swap the two functions without checking the resulting query.

## 22. Phrase Search and Lexeme Positions

Compare two documents:

~~~text
A: "gin gist planner"
B: "gin index is different from gist"
~~~

Both contain `gin` and `gist`, yet only A has the two words adjacent.

### 22.1. AND search

~~~sql
SELECT *
FROM search_lab.articles
WHERE search_vector @@ to_tsquery('simple', 'gin & gist');
~~~

### 22.2. Phrase search

~~~sql
SELECT *
FROM search_lab.articles
WHERE search_vector @@ phraseto_tsquery('simple', 'gin gist');
~~~

### 22.3. Why does GIN need heap recheck for phrases?

A `tsvector` GIN index does not hold full lexeme positional data to resolve every phrase relation inside the index. It finds candidate rows containing the words, and PostgreSQL verifies the phrase condition against each row's `tsvector`.

### 22.4. Queries with stop words

How `phraseto_tsquery` treats stop words and phrase gaps depends on the text search configuration. Never judge phrase matching purely by counting characters between words in raw text.

### 22.5. Semantics matter more than speed

If users want documents containing **both `gin` and `gist` anywhere**, using a phrase query will return fewer documents than expected. Choose operators for the desired search experience.

## 23. Weight Restrictions and Rechecks

The lab vector gives `title` weight `A` and `body` weight `B`.

### 23.1. Search lexeme in title only

~~~sql
SELECT article_id, title
FROM search_lab.articles
WHERE search_vector @@ to_tsquery(
    'simple',
    'postgresql:A'
);
~~~

### 23.2. Search lexeme in body only

~~~sql
SELECT article_id, title
FROM search_lab.articles
WHERE search_vector @@ to_tsquery(
    'simple',
    'planner:B'
);
~~~

### 23.3. Why must GIN still check rows?

A GIN FTS index does not store full weights, so it locates rows containing the lexeme and rechecks whether that lexeme carries the required weight.

### 23.4. Weights do not turn into a ranking index

Even with `title` A and `body` B, GIN does not return results sorted by "highest score". Ranking requires scoring matching rows.

## 24. Ranking: ts_rank and ts_rank_cd

A search UI usually wants the most relevant results first.

~~~sql
WITH q AS (
    SELECT websearch_to_tsquery(
        'simple',
        'postgresql gin'
    ) AS query
)
SELECT
    a.article_id,
    a.title,
    ts_rank(a.search_vector, q.query) AS score
FROM search_lab.articles AS a
CROSS JOIN q
WHERE a.search_vector @@ q.query
ORDER BY score DESC, a.article_id
LIMIT 20;
~~~

### 24.1. Index filters, rank sorts

GIN/GiST on `tsvector` helps find candidate documents. `ts_rank` scores vectors against the query; the executor may have to compute scores for matching rows and sort/Top-N them.

### 24.2. ts_rank_cd

`ts_rank_cd` evaluates lexeme proximity via cover density and behaves differently from `ts_rank`. Neither ranking function is universally superior; pick based on relevance needs.

### 24.3. Adding a tie-breaker column to ORDER BY

Using `ORDER BY score DESC, article_id` ensures deterministic ordering when scores tie, which helps pagination.

### 24.4. Ranking can be expensive

If a query matches a million rows with `LIMIT 20`, PostgreSQL may still have to score many matches to find the top 20. A GIN index does not mean "top 20 by score returned instantly".

### 24.5. Early filtering

Combining status/tenant/time predicates and suitable indexes can shrink the candidate set needing ranking. Do not try to solve overly broad result sets solely by tweaking FTS indexes.

## 25. Generated tsvector vs Expression Index

There are two common design paths.

### 25.1. Stored generated column

The lab uses:

~~~sql
search_vector TSVECTOR GENERATED ALWAYS AS (
    setweight(to_tsvector('simple'::regconfig, coalesce(title, '')), 'A')
    ||
    setweight(to_tsvector('simple'::regconfig, coalesce(body, '')), 'B')
) STORED
~~~

Then index it directly:

~~~sql
CREATE INDEX articles_search_gin_idx
ON search_lab.articles USING GIN(search_vector);
~~~

**Benefits:** concise queries, vector readily available for ranking/inspection, logic managed once in the schema.

**Cost:** extra column storage and recomputation overhead when source columns change.

### 25.2. Expression index

You can omit storing the vector as a separate column:

~~~sql
CREATE INDEX articles_expr_gin_idx
ON search_lab.articles
USING GIN(
    to_tsvector(
        'simple'::regconfig,
        coalesce(title, '') || ' ' || coalesce(body, '')
    )
);
~~~

This is an **extra illustrative index**. Never create a duplicate if production already has a generated-column GIN serving the same workload.

### 25.3. Queries must match the expression

~~~sql
SELECT article_id, title
FROM search_lab.articles
WHERE to_tsvector(
    'simple'::regconfig,
    coalesce(title, '') || ' ' || coalesce(body, '')
) @@ plainto_tsquery('simple', 'gin gist');
~~~

The planner can use the expression index when the expression, operator, and semantics align.

### 25.4. Mismatches prevent index usage

If the index is on `to_tsvector('simple', body)` while the query writes `to_tsvector('english', body)` or a different expression, never assume the planner can use that index.

### 25.5. Functions in expression indexes must be valid

PostgreSQL requires indexed expressions to satisfy immutability rules. Using `to_tsvector(regconfig, text)` with a **fixed configuration** expresses exact semantics; a form relying on session defaults lacks that contract.

### 25.6. Generated columns vs triggers

Older designs often used triggers to populate `tsvector` from `title`/`body`. Generated columns provide declarative synchronization, while version support, expression constraints, and custom logic can still make triggers appropriate in certain cases.

## 26. A Common Bug: Mismatched Text Search Configurations

Suppose:

~~~sql
CREATE INDEX articles_body_simple_gin
ON search_lab.articles
USING GIN (
    to_tsvector('simple'::regconfig, body)
);
~~~

Query:

~~~sql
SELECT article_id
FROM search_lab.articles
WHERE to_tsvector(
    'english'::regconfig,
    body
) @@ plainto_tsquery('english', 'search');
~~~

### 26.1. The problem

The index is defined on **`simple(body)`**, while the query runs **`english(body)`**. Those are different expressions and lexical rules; a `simple` index cannot serve an `english` query.

### 26.2. How to fix it

- Use one consistent configuration for a given search feature.
- Index the exact expression/config used at query time.
- For multiple languages, design separate vectors/indexes per document group.
- Read `EXPLAIN` to confirm which operator and index the planner uses.

### 26.3. Do not change config just to get an index plan

If English requires stemming and you switch everything to `simple` just to match an index, FTS results will violate requirements. Choose the **right semantics first**, then build the matching index.

## 27. Partial GIN Index: Indexing Only Searchable Rows

An app searching only published articles:

~~~sql
SELECT article_id, title
FROM search_lab.articles
WHERE status = 'published'
  AND search_vector @@ plainto_tsquery('simple', 'postgresql');
~~~

Consider a partial GIN index:

~~~sql
CREATE INDEX articles_published_gin_idx
ON search_lab.articles
USING GIN(search_vector)
WHERE status = 'published';
~~~

### 27.1. Potential benefits

- Smaller index if drafts make up a substantial fraction.
- Index maintenance applies only to rows matching the partial predicate.
- Published queries get a focused access path.

### 27.2. Condition for usage

The planner must prove the query's `WHERE` clause **implies** the partial index predicate, e.g., `status = 'published'` per applicable logic.

### 27.3. Prepared/generic plans

If the query is `WHERE status = $1`, a generic plan unaware of `$1`'s value cannot prove `status` is always `'published'`. Consequently, the partial index may be skipped even if the app usually passes `'published'`.

### 27.4. Do not accumulate overlapping indexes endlessly

Both a full-vector GIN and a partial published GIN might be considered by the planner. Measure write overhead and storage; keep both only if real workload evidence justifies it.

## 28. Combining FTS with Tenant, Status, and Time Filters

Real-world queries typically look like:

~~~sql
SELECT article_id, title, published_at
FROM search_lab.articles
WHERE tenant_id = 42
  AND status = 'published'
  AND published_at >= TIMESTAMPTZ '2026-01-15 00:00+00'
  AND search_vector @@ plainto_tsquery('simple', 'postgresql');
~~~

### 28.1. One FTS index does not handle every predicate

GIN on `search_vector` handles only the FTS predicate per its operator class. PostgreSQL may still have to filter tenant/status/time on the heap.

### 28.2. B-tree supports structured predicates

~~~sql
CREATE INDEX articles_tenant_time_idx
ON search_lab.articles (
    tenant_id,
    published_at
);
~~~

### 28.3. BitmapAnd or single-index scan

In some cases the planner combines bitmaps from multiple indexes (`BitmapAnd`), or uses one index and filters remaining predicates. There is no guarantee two indexes always trigger `BitmapAnd`; it depends on cost, selectivity, and statistics.

### 28.4. Start from the most selective predicate

If tenant 42 owns only a thousand documents, a tenant B-tree narrows rows dramatically before evaluating FTS. If the tenant has tens of millions of documents and the search term is rare, GIN may win.

### 28.5. Do not cram arbitrary columns into one index blindly

Multicolumn GIN indexes and specialized operator classes (like `btree_gin`) exist for specific scenarios, yet you cannot assume arbitrary data types and operators combine into one standard index without appropriate extensions/opclasses.

## 29. pg_trgm: GIN/GiST, Yet Different from Full-Text Search

When users need arbitrary substrings or fuzzy similarity, consider the `pg_trgm` extension.

### 29.1. Install the extension where permitted

~~~sql
CREATE EXTENSION IF NOT EXISTS pg_trgm;
~~~

This requires privileges and may be restricted by database/server policy.

### 29.2. Trigram GIN index

~~~sql
CREATE INDEX articles_title_trgm_idx
ON search_lab.articles
USING GIN (title gin_trgm_ops);
~~~

### 29.3. Trigram GiST index

Another option:

~~~sql
CREATE INDEX articles_title_trgm_gist_idx
ON search_lab.articles
USING GIST (title gist_trgm_ops);
~~~

Do not create both in production without comparing requirements and cost.

### 29.4. Matching query

~~~sql
SELECT article_id, title
FROM search_lab.articles
WHERE title ILIKE '%postgres%';
~~~

A trigram index can support matching `ILIKE` patterns per its operator class.

### 29.5. Semantic differences

| Need | Tool to Consider |
|---|---|
| Documents with lexemes, stemming, phrases | FTS `tsvector`/`tsquery` + GIN/GiST |
| Substring at any position | `pg_trgm` + GIN/GiST |
| Fuzzy matching, simple typos | `pg_trgm` similarity |
| Exact ID / keyword match | B-tree or suitable comparison |
| Geographic / spatial lookup | GiST with spatial operator class, not `tsvector` |

**Sharing an access method does not give two operator classes the same semantics.**

## 30. Why Might the Planner Skip GIN/GiST?

Common reasons:

1. Table is too small; `Seq Scan` is cheaper.
2. Lexeme is very common; the query matches most rows.
3. Stale statistics or inaccurate selectivity estimates.
4. Query does not use a matching `@@` predicate.
5. Index is on a different expression or config than the query.
6. Query uses `ILIKE` while the index is GIN `tsvector_ops`.
7. Partial index predicate is not implied by `WHERE`.
8. Generic prepared plan lacks concrete constants.
9. Joins or other filters make another access path cheaper.
10. Planner estimates random heap fetches cost more than a sequential scan.
11. Ranking/sorting dominates total cost, limiting index savings.
12. Index is not created yet, is `INVALID`, or lives on a different relation.
13. Partitioned table lacks an index on the target partition.
14. Query parses to empty or differs from expectations due to config/stop words.
15. Complex predicates/OR branches make part of the filter non-indexable.

### 30.1. Do not assume an index is broken just because Seq Scan runs

The planner picks the cheapest estimated plan. On a 100-row table, `Seq Scan` is completely reasonable.

### 30.2. Diagnostic steps

- `SHOW default_text_search_config`.
- Check index definitions in `pg_indexes`.
- Verify the actual query uses `@@`.
- Run `EXPLAIN (ANALYZE, BUFFERS)`.
- Compare estimated rows vs actual rows.
- Run `ANALYZE` if data changed significantly.
- Inspect query text, generated vectors, and lexemes.

## 31. Inspecting Index Definitions

### 31.1. pg_indexes

~~~sql
SELECT
    schemaname,
    tablename,
    indexname,
    indexdef
FROM pg_indexes
WHERE schemaname = 'search_lab'
  AND tablename = 'articles'
ORDER BY indexname;
~~~

### 31.2. Reading indexdef

Check:

- `USING gin` vs `USING gist`.
- Column `search_vector` vs expression `to_tsvector(...)`.
- Operator class if specified.
- Partial predicate `WHERE ...`.
- Number of indexes serving the same role.

### 31.3. Inspecting raw metadata when needed

`pg_class`, `pg_index`, `pg_am`, and `pg_opclass` hold internal index metadata. For everyday checks, `pg_indexes` is readable and sufficient to verify definitions.

## 32. Measuring Index Size and Usage Frequency

### 32.1. Index sizes

~~~sql
SELECT
    indexname,
    pg_size_pretty(
        pg_relation_size(
            (quote_ident(schemaname) || '.' ||
             quote_ident(indexname))::regclass
        )
    ) AS index_size
FROM pg_indexes
WHERE schemaname = 'search_lab'
  AND tablename = 'articles'
ORDER BY indexname;
~~~

### 32.2. pg_stat_user_indexes

~~~sql
SELECT
    s.relname AS table_name,
    s.indexrelname AS index_name,
    s.idx_scan,
    s.idx_tup_read,
    s.idx_tup_fetch
FROM pg_stat_user_indexes AS s
WHERE s.schemaname = 'search_lab'
  AND s.relname = 'articles'
ORDER BY s.indexrelname;
~~~

### 32.3. Interpreting the counters accurately

- `idx_scan`: number of index scans initiated per statistics semantics.
- `idx_tup_read`: index entries/tuples read at the index level.
- `idx_tup_fetch`: heap tuples fetched directly per view semantics—**not a counter of all rows returned by every Bitmap Heap Scan**.

Consult the documentation for your PostgreSQL version when interpreting these counters in detail, especially with bitmap scans.

### 32.4. Low counters do not always mean a useless index

An index may serve a rare yet business-critical query that must finish fast. Never `DROP` an index solely because `idx_scan` is low over a short window without checking stats resets, deployments, and workload patterns.

## 33. GIN Maintenance Cost: fastupdate and the Pending List

GIN can use a **pending list** to reduce the immediate cost of many small `INSERT`/`UPDATE` operations via `fastupdate`.

### 33.1. fastupdate

~~~sql
ALTER INDEX search_lab.articles_search_gin_idx
SET (fastupdate = on);
~~~

This illustrates altering an index in the lab; in production, evaluate writes, reads, and maintenance impact.

### 33.2. What is the pending list?

When `fastupdate` is enabled, new entries accumulate in a pending list before being merged into the main GIN tree. This lowers average write latency, while forcing queries to scan pending entries too and causing occasional pending-list cleanup bursts.

### 33.3. Cleanup

Autovacuum/`VACUUM` and cleanup mechanisms process the pending list. Some versions provide:

~~~sql
SELECT gin_clean_pending_list(
    'search_lab.articles_search_gin_idx'::regclass
);
~~~

Run this only with a clear operational reason; cleanup can consume heavy I/O and affect latency.

### 33.4. gin_pending_list_limit

`gin_pending_list_limit` can be tuned at config or index level where supported. This limit controls when/how much pending-list data triggers cleanup, not a direct limit on row counts or lexeme counts per document.

### 33.5. Is fastupdate = off always faster?

No. When disabled, every write updates the main structure immediately, which can hurt write-heavy workloads differently. Do not toggle it solely because a pending list exists.

### 33.6. Monitor tail latency

If cleanup batches cause latency spikes, measure write p95/p99, autovacuum cadence, GIN size, read latency, and pending-list behavior before changing settings.

## 34. GiST Also Has Write Trade-offs

GiST uses a search tree and signature representation for `tsvector`. Write cost depends on data, tree structure, and signature size.

### 34.1. Do not assume GiST is always better for writes

A smaller index in one test is not guaranteed to yield faster writes across all workloads.

### 34.2. Longer signatures improve candidate precision at a price

Increasing `siglen` reduces false positives while increasing index size and I/O. Evaluate based on data distribution and query workload.

### 34.3. VACUUM and maintenance

Both index types are affected by row churn, dead tuples, autovacuum, and bloat. Index maintenance is part of FTS design; never measure `SELECT` in isolation.

### 34.4. Choosing GIN vs GiST is a total-cost decision

Analyze together:

- `SELECT` vs `INSERT`/`UPDATE`/`DELETE` ratio.
- Average lexemes per document.
- Body update frequency.
- Query selectivity.
- p95/p99 latency.
- Index size.
- Memory, I/O, and autovacuum behavior.

## 35. Bulk Loading and Building Indexes

When loading a large batch of new documents, operation order affects total duration:

### 35.1. Create GIN first, then INSERT

The index must be updated during every `INSERT`, consuming substantial resources.

### 35.2. Load table data first, create index afterward

In controlled migrations or bulk loads, `COPY`/`INSERT` followed by `CREATE INDEX` can be much faster. However, this is unsuitable if live search must remain available without temporarily lacking the index.

### 35.3. CREATE INDEX CONCURRENTLY

On systems serving live writes, consider `CREATE INDEX CONCURRENTLY` where permitted, noting its transaction-block constraints, runtime, and resource usage. Never assume it runs faster than standard `CREATE INDEX`; its main benefit is avoiding blocking concurrent writes during the build.

### 35.4. ANALYZE after loading

~~~sql
ANALYZE search_lab.articles;
~~~

Fresh statistics help the planner estimate match counts accurately after data distribution shifts.

### 35.5. Test on a representative dataset

60,000 rows in the lab cannot represent hundreds of millions of documents, though it teaches syntax and plan shapes. Verify sizing on production-like data before choosing a bulk-load strategy.

## 36. Updating Documents and search_vector

With a generated column:

~~~sql
UPDATE search_lab.articles
SET title = 'PostgreSQL GIN and query planning'
WHERE article_id = 23;
~~~

PostgreSQL recomputes the generated `search_vector` from its declared expression when the row changes, and updates the FTS index to reflect the new vector.

### 36.1. Cost grows with document size

Updating a long body can alter many lexemes, increasing index maintenance and WAL. Chat/log systems with constant edits behave very differently from article archives edited rarely.

### 36.2. Is updating an unrelated column always cheap?

It depends on storage, HOT update eligibility, indexes, and generated expressions. Never assume an `UPDATE` touching only a column outside `search_vector` has zero effect on FTS indexes.

### 36.3. If maintaining a tsvector column manually

When applications or triggers update vectors, ensure `title`/`body` edits update the vector in the same transaction. Otherwise FTS returns stale results or misses documents even though the index accurately mirrors the **stale stored vector**.

### 36.4. Never treat GIN as the source of truth

Indexes accelerate data access. `search_vector`/document values and update rules are the logical data; an index can be rebuilt, but it will never fix a vector computed wrongly by application code.

## 37. Multilingual and Vietnamese FTS

A system storing both Vietnamese and English must define **which configuration/dictionary builds lexemes for each document**.

### 37.1. Per-language configuration

You can store a language code and build vectors with known configurations. Still, generated expressions and index matching must respect immutability, configuration matching, and query predicates; never change a session default and expect stored vectors to update automatically.

### 37.2. Vietnamese diacritics

Accented and unaccented strings will not match under `simple` without an appropriate normalization step. The `unaccent` extension can be part of a pipeline in some designs, provided volatility, collation, and safe index expressions are handled properly. Never mark a wrapper function `IMMUTABLE` if it actually depends on mutable dictionaries/configs.

### 37.3. Compound word segmentation

Vietnamese frequently uses multi-syllable words separated by spaces. The default parser treats each syllable as a separate token, affecting precision and relevance. Dedicated tokenizers/dictionaries or language-aware search engines may be needed.

### 37.4. User experience

Define explicitly:

- Should accent-insensitive matching be supported?
- Are singular/plural inflections needed?
- Is typo tolerance required?
- Are synonyms needed?
- Are ordered phrases required?
- Is prefix/autocomplete needed?
- Should title matches get boosted?
- Is tenant/status authorization required?

No single default GIN index solves all of these requirements out of the box.

## 38. Security Filtering and Tenants Alongside FTS

A SaaS app searching articles must never leak another tenant's documents:

~~~sql
SELECT article_id, title
FROM search_lab.articles
WHERE tenant_id = 42
  AND status = 'published'
  AND search_vector @@ websearch_to_tsquery(
      'simple',
      'gin gist'
  );
~~~

### 38.1. Indexes do not replace authorization

GIN/GiST reduces scanned rows, **not access permissions**. Users must be authenticated and authorized via application checks and/or RLS and grants.

### 38.2. RLS queries can affect plans

Row-Level Security injects predicates/barriers that preserve security semantics. Benchmarking as a superuser can yield different plans from the actual application role.

### 38.3. Metadata leaks

Features like `ts_headline` extract passages from `body`. Only run them after verifying row access permissions, and sanitize/escape output safely when rendering to the web.

### 38.4. Do not let users pick arbitrary text search configurations without control

Allowing clients to pass arbitrary dictionary/config names or raw SQL syntax can trigger unpredictable behavior or leak environment details. Restrict configurations and query modes via an API whitelist.

## 39. ts_headline: Displaying Matching Excerpts

PostgreSQL provides:

~~~sql
SELECT
    article_id,
    title,
    ts_headline(
        'simple',
        body,
        plainto_tsquery('simple', 'gin gist')
    ) AS excerpt
FROM search_lab.articles
WHERE search_vector @@ plainto_tsquery('simple', 'gin gist')
LIMIT 10;
~~~

### 39.1. Generate excerpts only for selected rows

Whenever possible, pick the top N documents first and compute `ts_headline` only for those N rows, rather than calling `ts_headline` on millions of candidates.

### 39.2. Handle HTML safely

`ts_headline` inserts highlight markup into text, yet it is **not an HTML sanitizer** against XSS. Escape/render safely in the application; never insert raw user-controlled HTML into the DOM unescaped.

### 39.3. Highlighting is not ranking

`ts_headline` formats excerpts; `ts_rank` computes scores; `@@` filters matches; GIN/GiST speeds up access paths. These are four distinct responsibilities.

## 40. Prefix Search and Autocomplete

FTS supports lexeme prefixes:

~~~sql
SELECT article_id, title
FROM search_lab.articles
WHERE search_vector @@ to_tsquery(
    'simple',
    'post:*'
);
~~~

### 40.1. Prefix applies only to lexemes

Not every substring inside a word will match. The prefix query `post:*` is not equivalent to `ILIKE '%ost%'`.

### 40.2. Indexability depends on operator class

FTS GIN/GiST indexes support `tsquery` operators in appropriate cases. The planner still weighs cost and selectivity; if a prefix is overly broad, `Seq Scan` may be reasonable.

### 40.3. Autocomplete for proper names

If you need fuzzy suggestions as a user types partial strings, consider `pg_trgm`, B-tree prefix indexes where suitable, or a dedicated search service.

### 40.4. Very short query inputs

One- or two-character inputs can match huge numbers of rows, spiking CPU, memory, and I/O. Enforce rate limiting, minimum query lengths per UX, and strict result limits.

## 41. Query Returns No Rows: Distinguishing Data vs Index

If a query fails to return expected documents:

1. Verify source `title`/`body` actually contains the expected words.
2. Inspect the generated vector:

~~~sql
SELECT
    article_id,
    title,
    search_vector
FROM search_lab.articles
WHERE article_id = 23;
~~~

3. Inspect `to_tsvector(config, text)` directly.
4. Check which lexemes `plainto_tsquery(config, input)` emits.
5. Compare vector and query configs.
6. Check stop words, stemming, language, and diacritics.
7. Check boolean AND/OR/phrase/weight operators.
8. Check tenant/status/RLS predicates.
9. Check for stale vectors if updated via triggers or app code.
10. Verify the record is committed and visible under transaction isolation.

**Having or lacking an index normally does not change the logical result of a valid FTS query**; it changes only the access path. Never diagnose "empty results because GIN is broken" when the vector and query actually fail to match.

## 42. Common Misconceptions

### 42.1. "GIN is mandatory for every text search"

Wrong. Exact lookups suit B-tree; substrings/fuzzy suit `pg_trgm`; FTS typically uses GIN/GiST on `tsvector`.

### 42.2. "GiST always returns wrong results because it is lossy"

Wrong. Signatures may yield false-positive candidates, which the executor rechecks per operator semantics.

### 42.3. "GIN never needs a recheck"

Wrong. Phrase/weight conditions or bitmap lossiness can require heap rechecking.

### 42.4. "Recheck Cond means every row at the node is wrong"

Wrong. It indicates a condition that may need verification; check rows removed.

### 42.5. "Longer GiST signatures always make every query faster"

Wrong. Longer signatures reduce potential collisions while increasing storage and other costs.

### 42.6. "With GIN, PostgreSQL will never choose Seq Scan"

Wrong. Small tables, common lexemes, and cost estimates can make `Seq Scan` cheaper.

### 42.7. "GIN automatically sorts results by ts_rank"

Wrong. Ranking must be computed and sorted explicitly.

### 42.8. "ILIKE and @@ have identical semantics"

Wrong. Substring matching differs from lexical FTS matching.

### 42.9. "A GIN tsvector index speeds up ILIKE '%abc%'"

Not by default. That is a different predicate type; consider `pg_trgm`.

### 42.10. "All GIN indexes share the same operator class"

Wrong. GIN `tsvector` and GIN trigram differ in keys and operator semantics.

### 42.11. "Picking simple vs english arbitrarily doesn't affect results"

Wrong. Text search configurations change lexemes, stemming, and stop words.

### 42.12. "Generated columns cost zero storage or write overhead"

Wrong. Vectors are stored and recomputed whenever referenced columns change.

### 42.13. "An expression index and a generated-column index are always identical"

Not necessarily. They differ in storage and query-matching semantics; inspect actual expressions and plans.

### 42.14. "If a query skips the index, just set enable_seqscan = off"

Never a production fix. It is only a controlled diagnostic toggle to inspect an alternative plan—it does not fix selectivity, expression mismatches, or SQL logic.

### 42.15. "One big GIN index is always better than smaller indexes"

No universal rule. Weigh workload, partial predicates, write overhead, and storage.

### 42.16. "A partial GIN for published always applies when querying with a status parameter"

Not guaranteed under generic plans if the planner cannot prove `status` is always `'published'`.

### 42.17. "Vietnamese FTS automatically understands all compound words and diacritics"

Wrong. Choose appropriate tokenizers, dictionaries, and normalization.

### 42.18. "Searching more lexemes is always faster"

No. `OR` widens results, while `AND` narrows them yet phrases/weights may trigger rechecks; plans and costs vary.

### 42.19. "Rows Removed by Index Recheck indicates a database logic bug"

No. It is execution telemetry counting candidates eliminated during recheck.

### 42.20. "Heap Blocks: lossy is always caused by GiST"

Wrong. Lossy bitmaps stem from bitmap heap scan memory constraints; GiST signatures are a separate lossy mechanism.

### 42.21. "idx_tup_fetch counts every heap tuple read by Bitmap Heap Scan"

Wrong. Counters in `pg_stat_user_indexes` have specific semantics; combine `EXPLAIN` with the appropriate stats views.

### 42.22. "After creating an index, ANALYZE is unnecessary"

Wrong as an operational habit. Whenever data or distributions shift, update statistics so the planner makes sound choices.

### 42.23. "With an FTS index, editing body updates app-managed vectors automatically"

Wrong. If vectors are maintained manually, enforce consistency in your write path.

### 42.24. "ts_headline prevents XSS"

Wrong. The application must handle text and markup safely.

### 42.25. "One SELECT benchmark is enough to pick GIN over GiST"

Wrong. Measure multiple queries, multiple runs, identical data, plus write and storage costs.

## 43. Investigation Workflow for a Slow FTS Query

Follow this practical sequence:

1. Capture the exact SQL and bind parameters.
2. Confirm whether the user needs lexical search or substring/fuzzy search.
3. Identify the text search configuration used.
4. Check `to_tsvector` output on sample documents.
5. Check the `tsquery` constructor output.
6. Confirm the index matches the exact column, expression, and operator class.
7. Check any partial index predicate.
8. Verify vectors stay current when source data changes.
9. Run `EXPLAIN (ANALYZE, BUFFERS, VERBOSE)` on a read-only query.
10. Compare estimated rows vs actual rows.
11. Inspect `Seq Scan`, `Bitmap Index Scan`, and `Bitmap Heap Scan`.
12. Check whether `Index Cond` actually uses `@@`.
13. Inspect `Recheck Cond` and `Rows Removed by Index Recheck`.
14. Inspect `Heap Blocks: exact/lossy`.
15. Check shared hit/read and temp I/O if any.
16. Check ranking, sorting, and `LIMIT` cost.
17. Check tenant/status/date filters and supporting indexes.
18. Run `ANALYZE` if statistics are stale.
19. Benchmark GIN vs GiST on representative data.
20. Track write and maintenance costs of each option.
21. Deploy only with verified improvement on the target workload.

### 43.1. Do not turn diagnostics into permanent system changes

You can test `SET LOCAL enable_seqscan = off` inside a lab transaction to inspect index eligibility; treat it strictly as **exploration**, never as a production setting since it can force far worse plans.

### 43.2. Read timings in context

A query taking 3ms vs 4ms on 60,000 rows may simply be cache/load jitter. Run multiple iterations, use realistic scale, and inspect buffers before drawing conclusions.

### 43.3. EXPLAIN ANALYZE does more than show a plan

It **actually runs** the SQL. For DML, use a test environment or transactions with `ROLLBACK`; never run `UPDATE`/`DELETE` in production just to "view the plan".

## 44. Hands-on Exercises

### Exercise 1 — Role of tsvector

Does `tsvector` store the verbatim text of `title`/`body`?

**Hint:** No; it stores lexemes along with related position and weight metadata.

### Exercise 2 — Role of tsquery

What does `tsquery` represent?

**Answer:** Search conditions over lexemes and operators.

### Exercise 3 — Matching operator

Which PostgreSQL operator normally tests `tsvector` against `tsquery`?

**Answer:** `@@`.

### Exercise 4 — Simple vs english

Why must vector creation and query parsing use consistent configurations?

**Hint:** Dictionaries, stemming/stop words, and normalization change lexemes.

### Exercise 5 — Create GIN

Write a GIN index on `search_vector` in the lab table.

~~~sql
CREATE INDEX articles_test_gin_idx
ON search_lab.articles USING GIN(search_vector);
~~~

The lab already creates a GIN index after the comparison step, so omit adding another unless testing separately.

### Exercise 6 — Create GiST

~~~sql
CREATE INDEX articles_test_gist_idx
ON search_lab.articles USING GIST(search_vector);
~~~

### Exercise 7 — GIN structure

What does an FTS GIN index fundamentally map?

**Answer:** Lexemes to matching row/TID posting lists.

### Exercise 8 — GiST signature

Why can GiST return false-positive candidates?

**Hint:** Signature bit collisions.

### Exercise 9 — Recheck

Do GiST false positives appear in the final query output?

**Answer:** No; the executor rechecks the condition.

### Exercise 10 — GIN weighted query

Why might searching `planner:B` still trigger a recheck even with GIN?

**Hint:** GIN does not store full weight metadata.

### Exercise 11 — Phrase

Write a query searching for the phrase "gin gist".

~~~sql
SELECT article_id
FROM search_lab.articles
WHERE search_vector @@ phraseto_tsquery(
    'simple',
    'gin gist'
);
~~~

### Exercise 12 — AND

How does `to_tsquery('simple','gin & planner')` differ from OR?

**Hint:** AND requires both lexemes; OR requires only one.

### Exercise 13 — User queries

Why shouldn't user input be concatenated straight into SQL text?

**Answer:** SQL injection and unsafe syntax; use bind parameters and proper parsing functions.

### Exercise 14 — Plain input

A search box receives `gin gist` with no advanced syntax. Which function fits?

**Hint:** `plainto_tsquery`.

### Exercise 15 — Phrase UI

A user puts text in double quotes wanting a phrase. What can you consider?

**Hint:** `phraseto_tsquery` or appropriate websearch syntax.

### Exercise 16 — Baseline

Which command displays the actual execution plan and buffers?

**Answer:** `EXPLAIN (ANALYZE, BUFFERS)`.

### Exercise 17 — Index Cond

In `EXPLAIN`, which node shows the FTS index was used?

**Hint:** `Bitmap Index Scan` on the index name, with `Index Cond` on `@@`.

### Exercise 18 — Recheck Cond

Does the appearance of `Recheck Cond` prove 100% of rows were wrong?

**Answer:** No.

### Exercise 19 — Rows Removed

Which field counts rows discarded during index recheck?

**Answer:** `Rows Removed by Index Recheck`.

### Exercise 20 — Bitmap lossiness

How does `Heap Blocks: lossy` differ from GiST signature lossiness?

**Hint:** One relates to bitmap memory/granularity, the other to signature collisions.

### Exercise 21 — Seq Scan

A 100-row table with GIN still picks `Seq Scan`. Does that prove the index is broken?

**Answer:** No.

### Exercise 22 — Common terms

Why might a word appearing across the entire table gain little from GIN?

**Hint:** Index returns huge candidate sets, still requiring most of the heap to be read.

### Exercise 23 — Ranking

Does GIN automatically return results sorted by `ts_rank`?

**Answer:** No.

### Exercise 24 — Top N

A query matches 1 million rows with `LIMIT 20` by rank. Why is it still CPU-intensive?

**Hint:** It must score and sort many matches.

### Exercise 25 — Expression mismatch

Can an index on `to_tsvector('simple', body)` automatically serve a query on `to_tsvector('english', body)`?

**Answer:** Not by default.

### Exercise 26 — Generated vector

How does a generated `search_vector` help?

**Hint:** The vector stays automatically maintained from its expression on row changes.

### Exercise 27 — Partial index

If a GIN index only covers `published`, can a query for `draft` rows use it?

**Answer:** No; the index contains no draft rows.

### Exercise 28 — Parameterized partial plan

Why might a generic plan with `status = $1` skip a partial index `WHERE status = 'published'`?

**Hint:** The planner cannot prove `$1` is always `'published'`.

### Exercise 29 — pg_trgm

To run `ILIKE '%postgre%'`, is a `tsvector` GIN index the most direct choice?

**Hint:** No; consider `pg_trgm`.

### Exercise 30 — Trigrams

Name one difference between trigrams and FTS lexemes.

**Hint:** Three-character slices vs parsed words/lexemes.

### Exercise 31 — fastupdate

What is the GIN pending list for?

**Hint:** Reduces immediate cost of small updates by deferring merges into the main GIN tree.

### Exercise 32 — Cleanup

What role does autovacuum/`VACUUM` play for GIN?

**Hint:** Helps clean up pending-list entries and dead items.

### Exercise 33 — GiST siglen

Increasing signature length aims to reduce what?

**Hint:** Bit collisions/false positives, at the cost of extra storage.

### Exercise 34 — Index size

Which functions display index size?

**Answer:** `pg_relation_size`, `pg_size_pretty`.

### Exercise 35 — Index statistics

Which view exposes `idx_scan` and `idx_tup_read`?

**Answer:** `pg_stat_user_indexes`.

### Exercise 36 — Vietnamese

Why can `simple` fall short for accurate Vietnamese search?

**Hint:** Compound word segmentation, diacritics, and dictionaries.

### Exercise 37 — Tenant security

Does a GIN index on `search_vector` automatically prevent leaking another tenant's articles?

**Answer:** No; authorization/RLS is still required.

### Exercise 38 — ts_headline

Should raw `ts_headline` markup be rendered as safe unescaped HTML?

**Answer:** No; it is not an XSS sanitizer.

### Exercise 39 — Stale data

If `body` is updated while an app-managed vector stays unchanged, does the index fix search results?

**Answer:** No; the vector itself must be updated properly.

### Exercise 40 — Practical design

A system has 50 million documents, 95% English lexeme queries, 5% substring queries, and continuous updates. What must you measure to choose the architecture?

**Hint:** GIN/GiST `tsvector`, separate `pg_trgm` for substrings, selectivity, read/write latency, index sizes, autovacuum/pending lists, partial indexes, ranking, and FTS configs.

## 45. Quick Reference Table

| Topic | Key Takeaway |
|---|---|
| Convert text to lexemes | `to_tsvector(config,text)` |
| Query from plain text | `plainto_tsquery` |
| Phrase query | `phraseto_tsquery` |
| Web-style search query | `websearch_to_tsquery` |
| Explicit-syntax query | `to_tsquery` |
| Matching | `tsvector @@ tsquery` |
| AND/OR/NOT | `&`, `\|`, `!` |
| Phrase | `<->` |
| Lexeme prefix | `:*` |
| Title weight A | `setweight(vector,'A')` |
| Full-text GIN | `CREATE INDEX ... USING GIN(vector)` |
| Full-text GiST | `CREATE INDEX ... USING GIST(vector)` |
| GIN structure | Lexeme → postings |
| GiST structure | Lossy signature |
| False positives | Heap recheck |
| GIN phrase/weights | May require recheck |
| Bitmap lossiness | Exact/lossy bitmap blocks |
| Index used | `Bitmap Index Scan` and `Index Cond` |
| Candidate heap | `Bitmap Heap Scan` |
| Recheck removals | `Rows Removed by Index Recheck` |
| Planner picks `Seq Scan` | Can be right for common terms / small tables |
| Ranking | `ts_rank`, `ts_rank_cd` |
| Highlighting | `ts_headline`, still needs safe escaping |
| Generated vector | `GENERATED ALWAYS AS (...) STORED` |
| Expression index | Index on `to_tsvector(...)` expression |
| Partial GIN | `WHERE status='published'` |
| Substring/fuzzy | `pg_trgm` with `gin_trgm_ops`/`gist_trgm_ops` |
| Index definitions | `pg_indexes` |
| Index usage | `pg_stat_user_indexes` |
| Index size | `pg_relation_size` |
| GIN write buffering | `fastupdate`, pending list |
| Cleanup | `VACUUM`/autovacuum, `gin_clean_pending_list` |
| Refresh stats | `ANALYZE` |
| Inspect real plan | `EXPLAIN (ANALYZE, BUFFERS, VERBOSE)` |
| Authorization | RLS/GRANT/app authorization, not indexes |

---

## Conclusion

**Both GIN and GiST can serve PostgreSQL Full Text Search, but they locate candidates differently.** For `tsvector`, GIN builds an inverted structure from lexemes to matching rows and is typically the first choice for FTS queries. GiST uses compact approximate signatures, which can yield false-positive candidates requiring recheck. GIN also has recheck cases, notably for positional/phrase details and weights not stored completely in the index.

More important than the index name is **the integrity of the entire pipeline**: building lexemes with a consistent configuration, parsing `tsquery` with the user's intended semantics, matching `@@` with the right operator class, and verifying plans via `EXPLAIN (ANALYZE, BUFFERS)`. Read `Index Cond`, `Recheck Cond`, `Rows Removed by Index Recheck`, `Heap Blocks: exact/lossy`, actual rows, buffers, and timings. Never treat `Seq Scan` as a bug on small tables or ultra-common terms; never treat `Recheck Cond` as proof of wrong results.

In production, designs must also account for **selectivity, `UPDATE`/`INSERT` overhead, GIN pending lists, autovacuum, expression alignment, partial indexes, ranking, tenant filters, and language rules**. When the requirement is substring or fuzzy search rather than lexical FTS, evaluate `pg_trgm` instead of misusing an FTS index.

Final practical rule: **choose the right search semantics first; build the matching index second; use execution plans and real read/write workload measurements to decide between GIN, GiST, or another structure**.
