# Building Full-Text and Fuzzy Search for a Catalog

A product, document, or content catalog typically needs to support two search modes. Full-text search locates words and phrases across multiple fields, understands search operators, and ranks results by relevance. Fuzzy search finds items with similar names when users make typos, omit diacritics, or recall names imprecisely.

PostgreSQL provides two toolsets suited for this problem: Full-Text Search with `tsvector`, `tsquery`, and GIN indexes; and the `pg_trgm` extension for trigram-based similarity matching. Combining both lets you build catalog search directly inside the database while maintaining consistent data filters and result ordering.

This lesson uses a hypothetical catalog table named `catalog_items` containing name, brand, category, and description. The examples can be adapted for article catalogs, documentation, customers, or other domain data.

## 1. Choosing the Right Search Type

The two techniques solve different needs:

| Need | Full-text search | Fuzzy search |
|---|---|---|
| Finding a word inside a long description | Well suited | Not the primary goal |
| Multi-word queries with AND/OR syntax | Supported via `tsquery` | Does not model word-level boolean logic |
| Phrase matching | Has phrase queries | Only compares string proximity |
| Relevance ranking by term importance | Has `ts_rank` / `ts_rank_cd` | Has similarity and distance |
| Handling spelling typos | Limited | Well suited |
| Substring matching in names | Not its primary purpose | Can use trigrams with `LIKE`/`ILIKE` or word similarity |
| Searching very short names | Depends on tokenization | Trigrams can be ineffective on very short strings |

For example, suppose a user searches for `tai nghe bluetooth`:

- Full-text search finds products containing all those terms across name, brand, category, or description.
- Fuzzy search can match `Tai nghe Bluetooh` even if the user transposes or mistypes a few characters in the name.
- Production systems often gather candidates from both techniques, then merge and rank them.

Do not use fuzzy search to replace full-text search over long descriptions. Trigrams measure character-sequence similarity and do not capture full word semantics or user query intent.

## 2. How PostgreSQL Full-Text Search Works

Full-Text Search converts text into a representation optimized for efficient searching.

- `tsvector` stores lexemes (normalized word forms) along with their positions.
- `tsquery` represents search criteria, including words, AND, OR, negation, and phrase matching.
- The `@@` operator checks whether a `tsvector` matches a `tsquery`.
- `to_tsvector` converts text into a vector.
- `plainto_tsquery`, `phraseto_tsquery`, and `websearch_to_tsquery` convert user input into structured queries.

A simple example:

~~~sql
SELECT
    to_tsvector('english', 'PostgreSQL supports full text search')
        AS document_vector,
    plainto_tsquery('english', 'text search')
        AS search_query;
~~~

You can test a match:

~~~sql
SELECT
    to_tsvector('english', 'PostgreSQL supports full text search')
    @@ plainto_tsquery('english', 'text search')
    AS matched;
~~~

The result is `true` because the document contains the target terms.

### 2.1. Text Search Configurations

The first argument to text search functions is the language configuration (`regconfig`). The configuration governs tokenization, normalization, stop-word removal, and stemming.

List available configurations:

~~~sql
SELECT
    cfgname,
    cfgnamespace::regnamespace AS schema_name
FROM pg_ts_config
ORDER BY cfgname;
~~~

Inspect how PostgreSQL analyzes a sentence:

~~~sql
SELECT *
FROM ts_debug('simple', 'Tai nghe khong day cho dien thoai');
~~~

`simple` is a minimal configuration suited when you want to keep tokens in basic lowercase form without language-specific stemming. Configurations like `english` include English dictionaries and stemming rules.

Never assume PostgreSQL ships with a built-in Vietnamese stemming configuration. For Vietnamese content, check what configurations actually exist in `pg_ts_config`; if no dedicated Vietnamese analyzer is installed, `simple` is a predictable starting point. It does not perform semantic Vietnamese word segmentation or reduce word variants to stems. If higher Vietnamese search quality is required, normalize/segment text in the application layer or integrate a dedicated analyzer, then store the pre-processed search field.

Always use the exact same configuration when building vectors and parsing queries. If vectors are built with `simple` while queries use `english`, matches may behave unexpectedly.

### 2.2. Converting User Input to `tsquery`

The query-builder functions behave differently:

| Function | Behavior |
|---|---|
| `plainto_tsquery(config, text)` | Treats input as plain text; words are joined with AND |
| `phraseto_tsquery(config, text)` | Builds an ordered phrase query |
| `websearch_to_tsquery(config, text)` | Supports web-search-like syntax such as quotes, `OR`, and minus signs |
| `to_tsquery(config, text)` | Expects explicit `tsquery` syntax including operators; input must be sanitized |

Examples:

~~~sql
SELECT plainto_tsquery('simple', 'tai nghe bluetooth');

SELECT phraseto_tsquery('simple', 'tai nghe bluetooth');

SELECT websearch_to_tsquery(
    'simple',
    '"tai nghe" bluetooth -co day'
);
~~~

For user-entered queries, `websearch_to_tsquery` is usually safer and friendlier than `to_tsquery` because users do not need to know internal PostgreSQL operator syntax. If you need advanced syntax, define an explicit grammar and validate input.

Never concatenate user search strings directly into SQL. Use driver bind parameters or prepared statements to prevent SQL injection. Likewise, avoid passing raw free-form user input directly to `to_tsquery`, as stray operator characters can trigger parse errors.

## 3. Designing the Catalog Table and Search Vector

Suppose the catalog has these fields:

- `name`: product name, carrying the highest weight.
- `brand`: brand name.
- `category`: product category.
- `description`: long description, carrying lower weight.

You can store a `tsvector` column automatically maintained by PostgreSQL as a generated column:

~~~sql
CREATE TABLE catalog_items (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name text NOT NULL,
    brand text,
    category text,
    description text,
    active boolean NOT NULL DEFAULT true,

    search_vector tsvector
        GENERATED ALWAYS AS (
            setweight(
                to_tsvector('simple', coalesce(name, '')),
                'A'
            )
            ||
            setweight(
                to_tsvector('simple', coalesce(brand, '')),
                'B'
            )
            ||
            setweight(
                to_tsvector('simple', coalesce(category, '')),
                'B'
            )
            ||
            setweight(
                to_tsvector('simple', coalesce(description, '')),
                'C'
            )
        ) STORED
);
~~~

`coalesce` turns `NULL` values into empty strings so the conversion function always receives text. The `||` operator concatenates vectors. `setweight` assigns importance labels to terms:

- `A`: highest importance, used for names.
- `B`: medium importance, used for brand and category.
- `C`: lower importance, used for description.
- `D`: lowest level, typically the default.

Weights do not alter the underlying text. They influence relevance scoring functions such as `ts_rank` or `ts_rank_cd`.

Insert sample rows:

~~~sql
INSERT INTO catalog_items (name, brand, category, description)
VALUES
(
    'Tai nghe Bluetooth X100',
    'Acme',
    'Tai nghe khong day',
    'Tai nghe chong on, pin lau, ket noi dien thoai'
),
(
    'Ban phim co K80',
    'KeyPro',
    'Phu kien may tinh',
    'Ban phim co ket noi USB va Bluetooth'
),
(
    'Chuot khong day M2',
    'Acme',
    'Phu kien may tinh',
    'Chuot quang khong day cho laptop'
),
(
    'Loa Bluetooth Mini',
    'SoundBox',
    'Loa',
    'Loa di dong pin sac, ket noi Bluetooth'
);
~~~

This example uses unaccented text to clearly demonstrate how the `simple` configuration behaves. When handling accented Vietnamese text, decide on an accent normalization policy as covered in the accent-insensitive search section below.

### 3.1. Creating a GIN Index

GIN is the standard index type for containment queries on `tsvector`:

~~~sql
CREATE INDEX catalog_items_search_vector_gin
ON catalog_items
USING GIN (search_vector);
~~~

GIN maps lexemes to the rows where they appear. When a query evaluates `search_vector @@ tsquery`, PostgreSQL can locate candidate rows via the index instead of scanning the entire table.

GIN does not store precomputed relevance rankings. PostgreSQL still computes `ts_rank` or `ts_rank_cd` across matching rows and sorts them. On small tables, the planner may pick a sequential scan because it is cheaper; that does not mean the index is broken.

## 4. Running Full-Text Search and Ranking

The following query accepts keywords via parameter `$1`, finds matching rows, and ranks them by relevance:

~~~sql
WITH query_input AS (
    SELECT websearch_to_tsquery('simple', $1) AS query
)
SELECT
    item.id,
    item.name,
    item.brand,
    item.category,
    ts_rank_cd(item.search_vector, query_input.query) AS relevance
FROM catalog_items AS item
CROSS JOIN query_input
WHERE item.active
  AND numnode(query_input.query) > 0
  AND item.search_vector @@ query_input.query
ORDER BY relevance DESC, item.id
LIMIT 20;
~~~

`numnode` counts the nodes in a `tsquery`. This guard skips empty queries—for instance, when a user submits an empty string or only stop words stripped by the dictionary.

`ts_rank_cd` scores matches using term frequency and cover density (proximity of lexemes). You can use `ts_rank` if positional proximity is unnecessary. Scores are not probabilities; treat them as relative values for sorting results within a single search strategy.

### 4.1. Phrase Search

Use `phraseto_tsquery` when word order matters:

~~~sql
SELECT
    id,
    name
FROM catalog_items
WHERE search_vector @@
      phraseto_tsquery('simple', $1);
~~~

For example, when a user searches for the phrase `tai nghe`, matching documents must contain both words in order at the expected adjacency. Exact matching behavior depends on tokenization and dictionary rules.

### 4.2. Searching with `OR` and Exclusions

`websearch_to_tsquery` supports familiar syntax:

~~~sql
SELECT
    id,
    name,
    ts_rank_cd(
        search_vector,
        websearch_to_tsquery('simple', $1)
    ) AS relevance
FROM catalog_items
WHERE search_vector @@
      websearch_to_tsquery('simple', $1)
ORDER BY relevance DESC, id;
~~~

Example inputs:

- `bluetooth tai nghe`: matches all terms using default AND logic.
- `bluetooth OR loa`: matches either branch.
- `"tai nghe"`: matches the phrase.
- `bluetooth -co day`: excludes documents containing negated terms.

Test queries with multiple negations or overly broad terms. Never return the entire catalog just because a search input is empty or contains only exclusion operators.

### 4.3. Custom Weights and Highlighted Excerpts

`A`/`B`/`C`/`D` weights let product names influence ranking more strongly than descriptions. You can customize weight multipliers in `ts_rank_cd`:

~~~sql
SELECT
    id,
    name,
    ts_rank_cd(
        ARRAY[0.1, 0.2, 0.4, 1.0],
        search_vector,
        websearch_to_tsquery('simple', $1)
    ) AS relevance
FROM catalog_items
WHERE search_vector @@
      websearch_to_tsquery('simple', $1)
ORDER BY relevance DESC, id;
~~~

The weight array is ordered `{D, C, B, A}`. Larger numbers give lexemes with that weight a bigger contribution to the rank. Measure search quality against a curated evaluation query set rather than guessing weights by intuition.

You can generate highlighted snippets using `ts_headline`:

~~~sql
SELECT
    id,
    ts_headline(
        'simple',
        coalesce(description, ''),
        websearch_to_tsquery('simple', $1),
        'StartSel=<mark>, StopSel=</mark>, MaxWords=25, MinWords=8'
    ) AS excerpt
FROM catalog_items
WHERE search_vector @@
      websearch_to_tsquery('simple', $1);
~~~

`ts_headline` renders output from the raw text. When embedding excerpts into HTML, escape or sanitize properly; never treat an excerpt as trusted HTML simply because the highlight tags were set in SQL.

## 5. Fuzzy Search with `pg_trgm`

The `pg_trgm` extension splits strings into trigrams—groups of three consecutive characters padded with boundary spaces per the extension's algorithm. PostgreSQL compares shared trigrams between two strings to compute similarity.

Install the extension in the target database:

~~~sql
CREATE EXTENSION IF NOT EXISTS pg_trgm;
~~~

Common functions and operators:

| Element | Meaning |
|---|---|
| `similarity(a, b)` | Returns similarity score between two strings, from 0 to 1 |
| `a % b` | Tests whether similarity exceeds the current threshold |
| `word_similarity(a, b)` | Compares the first string against a contiguous substring of the second |
| `a <% b` | Tests word similarity against its threshold |
| `strict_word_similarity(a, b)` | Compares word similarity respecting word boundaries |
| `a <<% b` | Tests strict word similarity against its threshold |
| `a <-> b` | Trigram distance, equal to `1 - similarity` |

The closer the similarity score is to 1, the more alike the two strings are. The default threshold for `%` is typically `0.3`; it can be adjusted via `pg_trgm.similarity_threshold` per session or transaction.

### 5.1. Finding Similar Names

Create a GIN index on the lowercased name:

~~~sql
CREATE INDEX catalog_items_name_trgm_gin
ON catalog_items
USING GIN (lower(name) gin_trgm_ops);
~~~

Query:

~~~sql
SELECT
    id,
    name,
    similarity(lower(name), lower($1)) AS similarity_score
FROM catalog_items
WHERE active
  AND lower(name) % lower($1)
ORDER BY similarity_score DESC, id
LIMIT 10;
~~~

If a user mistypes a few characters, names sharing many trigrams still surface in results. The GIN index filters candidates via the `%` operator; PostgreSQL then computes exact scores and sorts them.

You can adjust the threshold inside a transaction:

~~~sql
BEGIN;

SET LOCAL pg_trgm.similarity_threshold = 0.25;

SELECT
    id,
    name,
    similarity(lower(name), lower($1)) AS score
FROM catalog_items
WHERE lower(name) % lower($1)
ORDER BY score DESC
LIMIT 10;

COMMIT;
~~~

Lower thresholds return more candidates but increase irrelevant matches. Higher thresholds reduce noise but risk missing real typos. Tune thresholds based on real query logs, typical name lengths, and UX expectations.

### 5.2. Matching Words Inside Longer Names

`word_similarity` works well when the user's input resembles a portion of a longer name or description:

~~~sql
SELECT
    id,
    name,
    word_similarity(lower($1), lower(name)) AS score
FROM catalog_items
WHERE lower($1) <% lower(name)
ORDER BY score DESC, id
LIMIT 10;
~~~

`<%` is directional: the left-hand string is compared against an extent inside the right-hand string. Swapping the operands changes the semantics.

`strict_word_similarity` enforces tighter word-boundary matching:

~~~sql
SELECT
    id,
    name,
    strict_word_similarity(lower($1), lower(name)) AS score
FROM catalog_items
WHERE lower($1) <<% lower(name)
ORDER BY score DESC, id
LIMIT 10;
~~~

Each operator has its own threshold parameter. Configure and test thresholds consistently with your ranking logic.

### 5.3. Top-K Nearest Matches with GiST

GIN excels at filtering rows above a threshold. When the goal is fetching the closest strings by distance, GiST supports K-nearest-neighbor ordering:

~~~sql
CREATE INDEX catalog_items_name_trgm_gist
ON catalog_items
USING GIST (lower(name) gist_trgm_ops);
~~~

Top nearest matches query:

~~~sql
SELECT
    id,
    name,
    lower(name) <-> lower($1) AS distance
FROM catalog_items
ORDER BY lower(name) <-> lower($1)
LIMIT 10;
~~~

Smaller distance means closer match. GiST supports KNN ordering on `<->`; inspect plans with `EXPLAIN` to verify the planner actually uses the index.

You do not need both GIN and GiST on every table. Choose based on workload: threshold-filtered similarity queries, top-K nearest queries, write rate, and index footprint.

## 6. Case-Insensitive and Accent-Insensitive Search

`lower()` normalizes letter case for fuzzy search. However, it does not strip Vietnamese diacritics. For example, `ca phe` and `cà phê` yield different trigrams.

The `unaccent` extension provides an accent-stripping function:

~~~sql
CREATE EXTENSION IF NOT EXISTS unaccent;
~~~

Test it:

~~~sql
SELECT
    unaccent('Cà phê rang xay') AS normalized_text;
~~~

An important indexing detail: `unaccent` depends on a dictionary and is not marked `IMMUTABLE` by default. PostgreSQL requires expressions used in indexes to be `IMMUTABLE`. Consequently, you cannot blindly create an index directly on `unaccent(name)`.

There are two common solutions:

1. **Store a pre-normalized search column:** the application or a trigger writes `name_search` lowercased and unaccented on `INSERT`/`UPDATE`, and a trigram index is created on that stored column.
2. **Create a controlled `IMMUTABLE` wrapper:** use only if you guarantee the `unaccent` dictionary will not change over the index's lifetime. If the dictionary ever changes, you must update rows and rebuild the index. Never mark a function `IMMUTABLE` merely to bypass the index error without managing the consequences.

Example of maintaining a normalized column via trigger:

~~~sql
ALTER TABLE catalog_items
ADD COLUMN name_search text NOT NULL DEFAULT '';

CREATE OR REPLACE FUNCTION catalog_items_set_name_search()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.name_search :=
        lower(unaccent('public.unaccent'::regdictionary, coalesce(NEW.name, '')));
    RETURN NEW;
END;
$$;

CREATE TRIGGER catalog_items_name_search_trg
BEFORE INSERT OR UPDATE OF name
ON catalog_items
FOR EACH ROW
EXECUTE FUNCTION catalog_items_set_name_search();
~~~

This example assumes `unaccent` is installed in the `public` schema; if installed elsewhere, adjust the dictionary reference accordingly. After adding the trigger, backfill existing rows:

~~~sql
UPDATE catalog_items
SET name = name;
~~~

This fires the trigger for existing rows because `name` is updated. On large tables, batch the backfill and throttle load instead of updating the entire table during peak traffic.

Create an index on the normalized column:

~~~sql
CREATE INDEX catalog_items_name_search_trgm_gin
ON catalog_items
USING GIN (name_search gin_trgm_ops);
~~~

Search:

~~~sql
SELECT
    id,
    name,
    similarity(name_search, lower(unaccent($1))) AS score
FROM catalog_items
WHERE name_search % lower(unaccent($1))
ORDER BY score DESC, id
LIMIT 10;
~~~

Here, the parameter's normalization runs at query time while the column is already normalized and indexed. Calling `unaccent` on the query parameter still allows the index on `name_search` to be used.

If full-text search must also be accent-insensitive, maintain normalized text columns and build `tsvector` from them. A generated column should not call a non-immutable `unaccent` function directly. Either maintain the vector via trigger or store normalized search text and derive a generated vector from that text. Ensure normalized text and vectors update inside the same transaction as the source columns.

## 7. Combining Full-Text and Fuzzy Search

Catalogs often need strong results for both exact-word queries and typos. One implementation builds two candidate sets:

- Full-text candidates: rows matching `search_vector`.
- Fuzzy candidates: rows whose names resemble the query string.

They are then merged by ID and scored together. The following example combines normalized full-text scores with trigram similarity:

~~~sql
WITH query_input AS (
    SELECT
        websearch_to_tsquery('simple', $1) AS query,
        lower($1) AS needle
),
full_text_matches AS (
    SELECT
        item.id,
        ts_rank_cd(item.search_vector, q.query) AS text_rank
    FROM catalog_items AS item
    CROSS JOIN query_input AS q
    WHERE item.active
      AND numnode(q.query) > 0
      AND item.search_vector @@ q.query
),
fuzzy_matches AS (
    SELECT
        item.id,
        similarity(lower(item.name), q.needle) AS trigram_score
    FROM catalog_items AS item
    CROSS JOIN query_input AS q
    WHERE item.active
      AND lower(item.name) % q.needle
),
candidate_scores AS (
    SELECT
        id,
        0.7 * (text_rank / (1.0 + text_rank)) AS score
    FROM full_text_matches

    UNION ALL

    SELECT
        id,
        0.3 * trigram_score AS score
    FROM fuzzy_matches
),
combined AS (
    SELECT
        id,
        sum(score) AS relevance
    FROM candidate_scores
    GROUP BY id
)
SELECT
    item.id,
    item.name,
    item.brand,
    item.category,
    combined.relevance
FROM combined
JOIN catalog_items AS item
  ON item.id = combined.id
WHERE item.active
ORDER BY combined.relevance DESC, item.id
LIMIT 20;
~~~

The weights `0.7` and `0.3` are illustrative only. Full-text ranks and trigram similarity sit on different scales; normalization makes combining them easier, yet weights must still be tuned against real evaluation data. When a row matches both methods, its scores sum to reflect reinforcement from both signals.

In production systems, you can incorporate additional signals:

- Exact name match.
- Name prefix match.
- Brand or category match.
- Active and in-stock status.
- Popularity or recency.
- User permissions and tenant scope.

Security and data-isolation filters must be applied before returning results. Never let a fuzzy candidate from another tenant leak through just because its similarity score is high.

## 8. Query Performance and Execution Plan Tuning

Search must be evaluated at data sizes and query mixes close to production.

### 8.1. Using `EXPLAIN`

Inspect the plan:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT id, name
FROM catalog_items
WHERE search_vector @@
      websearch_to_tsquery('simple', 'bluetooth tai nghe');
~~~

For fuzzy search:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT id, name
FROM catalog_items
WHERE lower(name) % lower('bluetooh');
~~~

Review these details:

- `Seq Scan`: sequential table scan; may be reasonable on small tables or low-selectivity predicates.
- `Bitmap Index Scan`: retrieves matching row locations from an index, typical for GIN.
- `Bitmap Heap Scan`: fetches heap blocks identified by the bitmap.
- `Index Scan`: reads rows directly via an index.
- `Rows Removed by Filter`: rows discarded by secondary filters.
- `Buffers`: pages read from disk or found in shared cache.
- `Execution Time`: observed execution time for that run.

Never draw conclusions from a single run. Cold vs. warm caches, table statistics, predicate selectivity, and table size strongly influence plan selection.

### 8.2. Keeping Statistics Up to Date

After bulk imports or major distribution shifts, run `ANALYZE` or ensure autovacuum/analyze is configured appropriately:

~~~sql
ANALYZE catalog_items;
~~~

Statistics let the planner estimate matching row counts and pick appropriate plans. If a table grows rapidly while statistics lag behind, the planner may choose suboptimal sequential or index scans.

### 8.3. Cost of GIN and GiST

GIN typically excels for multi-token search and trigram threshold filtering. It can occupy significant disk space and increase write overhead because updating a single row may modify many index entries. `fastupdate` and pending lists affect how GIN handles writes; monitor vacuum activity, tail latency, and index size.

GiST shines for `pg_trgm` KNN distance ordering, though actual performance depends on data distribution and index settings. Measure on representative workloads before deciding.

Do not index every column simply because it might be searched. Every index increases disk usage and `INSERT`/`UPDATE`/`DELETE` cost. Identify which fields users actually search, query patterns, and usage frequency.

### 8.4. Limiting Results and Pagination

Always enforce sensible result limits. For large catalogs, avoid returning thousands of rows for a short query. Use `ORDER BY relevance DESC, id` for deterministic tie-breaking when multiple rows share the same score.

For deep pagination, large `OFFSET` values become expensive because the database still skips all preceding sorted rows. You can use keyset pagination on `(relevance, id)`, provided scores remain consistent across pages. If underlying data mutates frequently, consider a transaction snapshot or cursor when UX demands stable pagination.

### 8.5. Handling Very Short or Overly Broad Queries

Trigrams are rarely useful on one- or two-character strings because too few trigrams exist. Full-text search on overly common terms can match most of the catalog. Establish clear guardrails:

- Skip fuzzy search for overly short inputs.
- Cap word count or query string length.
- Do not run searches on empty queries.
- Cap candidate counts from each search branch.
- Set appropriate statement timeouts on search endpoints.
- Monitor queries exhibiting abnormal execution times or scanned row counts.

Do not silently truncate queries in ways that alter meaning without user feedback or explicit rules.

## 9. Designing a Catalog Search API

A search API payload might look like:

~~~json
{
  "query": "tai nghe bluetooh",
  "category": "audio",
  "activeOnly": true,
  "limit": 20,
  "cursor": null
}
~~~

The backend should:

1. Validate query length and format.
2. Determine tenant and permission scope from authenticated identity.
3. Normalize the query per accent and casing policy.
4. Select full-text, fuzzy, or hybrid mode depending on length and query type.
5. Apply category, active, tenant, and permission filters.
6. Score, stably sort, and limit results.
7. Return results with pagination metadata.

Never trust `tenant_id` or sensitive data-access filters sent directly by the client. The backend must derive access scope from the authenticated principal.

If the API exposes exact and fuzzy modes, distinguish them clearly so the frontend can render helpful suggestions. Returning a `matchType` such as `full_text`, `fuzzy`, or `exact` is useful, provided it never leaks metadata about records the user is unauthorized to view.

## 10. Testing Search Quality

Search has an information-retrieval quality dimension—not just verifying SQL runs without errors. Curate a representative query suite paired with expected results.

A test matrix might include:

| Case | Sample Input | Expected Verification |
|---|---|---|
| Exact name match | `Tai nghe Bluetooth X100` | Exact item ranks first |
| Multiple terms in description | `pin lau bluetooth` | Items containing those description terms appear |
| Phrase | `tai nghe` | Results satisfy phrase query |
| OR | `bluetooth OR loa` | Results match either branch |
| Exclusion | `bluetooth -co day` | Items with excluded terms are omitted |
| Typo | `bluetooh` | Similar product names are suggested |
| Partial name error | `tai nghe X10` | Approximate matches rank sensibly |
| Accent variance | `ca phe` and `cà phê` | Follows accent-normalization policy |
| Short strings | `a`, `xy` | Does not flood results with noise |
| Empty query | empty string | Returns empty list or prompts for keywords |
| No results | non-existent term | Returns empty list without errors |
| Permissions / tenant | Query matching another tenant's data | Zero cross-tenant data leakage |

Evaluate using metrics like `Precision@K` (fraction of relevant items in the top K) and `Recall@K` (fraction of relevant items retrieved in the top K) when labeled relevance judgments exist. Add MRR or NDCG when ranking position matters strongly.

Whenever you adjust weights, trigram thresholds, or text search configurations, rerun the entire evaluation suite to compare. Never tune for a single anecdote.

## 11. Common Mistakes

- Passing free-form text to `to_tsquery`: special characters or invalid syntax trigger errors; use `websearch_to_tsquery` or validate grammar.
- Using different configurations for vector creation and query parsing: tokens normalize differently and fail to match.
- Missing GIN index: `@@` queries degrade to full table scans as data grows.
- Assuming GIN pre-sorts by rank: GIN only filters candidates; ranking still requires computing scores and sorting.
- Running trigram matching on tiny strings: sparse trigrams yield noisy or overly broad matches.
- Setting fuzzy thresholds too low: floods results with unrelated items.
- Using only `lower()` and expecting accents to disappear: lowercasing does not strip diacritics.
- Placing `unaccent` inside an expression index without considering volatility: PostgreSQL requires index expressions to be `IMMUTABLE`.
- Forgetting to refresh vectors or normalized columns: newly inserted/updated rows become unsearchable if triggers or application writes drift out of sync.
- Skipping `ANALYZE` after bulk loads: stale statistics mislead the planner.
- Returning too many rows: increases latency, database load, and payload transfer cost.
- Omitting security filters: fuzzy search can leak names or snippets from restricted rows.

## 12. Step-by-Step Implementation Workflow

A safe rollout path for catalog search:

1. Define searchable fields, languages, accent policies, and autocomplete/fuzzy requirements.
2. Choose a text search configuration and inspect tokenization with `ts_debug`.
3. Design weighted `tsvector` across name, brand, category, and description.
4. Create a GIN index and benchmark full-text queries.
5. Install `pg_trgm`, and create a GIN or GiST index matching your fuzzy query style.
6. If accent-insensitivity is required, design normalized columns and consistent update triggers/pipelines.
7. Write the hybrid query, cap candidate sets, and compute combined rankings.
8. Enforce tenant, permission, category, and status filters before returning rows.
9. Test exact queries, typos, empty inputs, short strings, and zero-match cases.
10. Profile `EXPLAIN (ANALYZE, BUFFERS)` on production-like data volumes.
11. Monitor latency, returned row counts, cache behavior, index size, and write amplification.
12. Tune weights and thresholds using your evaluation suite and deploy safely with rollback capability.

Full-text search and trigrams provide a powerful foundation for catalog search inside PostgreSQL. Full-text search understands words and query operators, while trigrams catch near-matches when users mistype names. Designing vectors, accent normalization, indexes, ranking, and authorization filters together delivers relevant results while preserving performance and data boundaries.
