# pg_trgm, Similarity, and Fuzzy Search in PostgreSQL

A user searches for `"ban phim co"` in an e-commerce app. The catalog stores `"Bàn phím cơ không dây"`. Another user types `"bluetooh"` instead of `"bluetooth"`, or only remembers part of `"mechanical keyboard"`. Exact matching (`=`) fails to return the expected items, while `LIKE '%...%'` does not tolerate typos.

PostgreSQL provides the **`pg_trgm`** extension to compare strings by groups of **three consecutive characters** (*trigrams*), compute similarity scores, and find near-matching names. Combined with **GIN** or **GiST trigram indexes**, PostgreSQL can locate candidates far faster than scoring the entire table in suitable workloads.

~~~sql
-- Conceptual example after installing pg_trgm:
SELECT
    product_id,
    product_name,
    similarity(product_name, 'ban phim co') AS score
FROM catalog_products
WHERE product_name % 'ban phim co'
ORDER BY score DESC, product_id
LIMIT 10;
~~~

However, `pg_trgm` **does not understand Vietnamese semantics**, strip diacritics automatically, translate languages, or prove two names refer to the same entity. It also differs from full-text search (`tsvector`/`tsquery`): one focuses on **character-level similarity**, while the other focuses on **tokens/lexemes and lexical queries**.

The goal of this lesson is using the tool for its proper purpose: understanding scores and thresholds, writing index-friendly SQL, evaluating results on real data, and avoiding turning fuzzy search into unsafe identity or authorization checks.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Describe trigrams and why minor typos can still yield positive similarity.
2. Install, inspect, and use the `pg_trgm` extension in a permitted database.
3. Use `show_trgm`, `similarity`, `word_similarity`, and `strict_word_similarity`.
4. Distinguish whole-string matching, contiguous-extent matching, and word-boundary matching.
5. Use the operators `%`, `<%`, `%>`, `<<%`, `%>>`.
6. Compute distances `<->`, `<<->`, `<<<->` and understand `ORDER BY ... LIMIT`.
7. Adjust `pg_trgm.similarity_threshold`, `word_similarity_threshold`, and `strict_word_similarity_threshold` within a transaction.
8. Create `GIN ... gin_trgm_ops` and `GiST ... gist_trgm_ops`, comparing strengths and limits.
9. Explain why **GiST** efficiently supports **nearest-neighbor** ordering by distance, whereas GIN mainly filters candidates.
10. Search substrings with `LIKE`/`ILIKE` and understand limits of overly short or trigram-free patterns.
11. Read `EXPLAIN (ANALYZE, BUFFERS)` to identify index paths, rechecks, and sorts.
12. Avoid confusing character matching with synonyms, word segmentation, diacritic normalization, or full-text search.
13. Design a controlled Unicode/Vietnamese normalization strategy when needed.
14. Build a spell-suggestion and fuzzy product-search API with Java/JDBC prepared statements.
15. Evaluate precision/recall, false positives, thresholds, speed, and index maintenance costs.

## 2. Exact Search, Substring Search, and Fuzzy Search

Three common requirements that differ fundamentally:

| Requirement | Example | Starting Tool |
| --- | --- | --- |
| **Exact match** | SKU equals `'KB-001'` | B-tree + `=` |
| **Prefix/substring match** | Name contains `'phím'` | `LIKE`/`ILIKE`; trigram index if appropriate |
| **Fuzzy match** | `'bluetooh'` near `'bluetooth'` | `pg_trgm` similarity / word similarity |
| **Lexical text search** | Multi-word documents, stemming | Full-text search `tsvector`/`tsquery` |
| **Synonyms or semantics** | `'máy tính xách tay'` near `'laptop'` | Synonym dictionary, app logic, or suitable search engine |

**Never use `pg_trgm` to verify order codes, user permissions, security tokens, or foreign keys.** Fields requiring exactness must use exact matching and data constraints.

### 2.1. Why isn't LIKE enough?

~~~sql
WHERE product_name ILIKE '%bluetooth%'
~~~

can match names containing `bluetooth` case-insensitively per collation rules. Yet if a user omits `t` and types `bluetooh`, the original substring disappears. Trigram similarity can place both terms into a **nearby candidate group**.

### 2.2. Why isn't full-text search enough?

Full-text search excels at tokenization, lexeme ranking, and multi-word search, yet a typo that changes the lexeme drops results. Trigrams can **suggest spelling corrections**, or act as a fallback layer when standard FTS returns too few hits.

### 2.3. Fuzzy matches are candidates, not ground truth

Two people named `An` and `Anh` are close in characters but **not necessarily the same person**. Two products `"Cáp USB-C 1m"` and `"Cáp USB-C 2m"` look very similar, yet differ in length and possibly price. Fuzzy matches must be presented, filtered, and confirmed by business logic.

## 3. Installing the pg_trgm Extension

`pg_trgm` ships with PostgreSQL (as a contrib module), yet must **be created per database** before using its functions, operators, and index operator classes.

~~~sql
CREATE EXTENSION IF NOT EXISTS pg_trgm;
~~~

This command may require `CREATE` privilege on the database and environment approval. In modern PostgreSQL versions, `pg_trgm` is marked **trusted**, allowing appropriately privileged non-superusers to install it. On managed databases, availability depends on the provider's allowlist.

**Never run `CREATE EXTENSION` in production** without authorization and schema-change approval. The remaining examples assume `pg_trgm` is installed.

### 3.1. Verify the extension is installed

~~~sql
SELECT
    extname,
    extversion,
    extnamespace::regnamespace AS installed_schema
FROM pg_catalog.pg_extension
WHERE extname = 'pg_trgm';
~~~

If zero rows return, the extension is not installed in the current database. `CREATE EXTENSION IF NOT EXISTS` prevents errors if already installed, **without guaranteeing it lives in the schema your application expects**.

### 3.2. Database scope and search_path

PostgreSQL extensions are installed **per database**, not automatically across other databases in the same instance. The schema holding extension functions/operators and `search_path` affect unqualified calls. Examples in this lesson assume the extension is reachable via the normal `search_path`.

### 3.3. Quick function check

~~~sql
SELECT
    similarity('keyboard', 'keybord') AS overall_similarity,
    show_trgm('cat') AS cat_trigrams;
~~~

`similarity` returns `real` between 0 and 1. `show_trgm` returns `text[]`, typically used for **learning and debugging trigram extraction**, not for sending raw output to end users.

## 4. What Is a Trigram?

A **trigram** is a group of three consecutive characters representing small slices of a string. For each *word*, `pg_trgm` prepends **two leading spaces** and appends **one trailing space**, then extracts consecutive three-character slices. Non-word characters are ignored during trigram extraction.

Example with `cat`:

~~~text
Original string:  cat
Padded string:    "  cat "

Trigrams:
  "  c"
  " ca"
  "cat"
  "at "
~~~

For `cat` and `cut`, leading/trailing trigrams overlap even though the middle letter differs. For longer strings, a single typo changes only a small subset of trigrams rather than all of them.

### 4.1. Practicing show_trgm

~~~sql
SELECT
    show_trgm('cat') AS trigrams_cat,
    show_trgm('cut') AS trigrams_cut,
    show_trgm('bluetooth') AS trigrams_bluetooth,
    show_trgm('bluetooh') AS trigrams_typo;
~~~

Compare the elements of the trigram arrays. Exact counts and representations with multibyte characters can differ from naive byte-slicing, so **never implement your own trigram splitter by slicing bytes**.

### 4.2. Punctuation is not an independent search character

~~~sql
SELECT
    show_trgm('foo|bar') AS separated_words,
    show_trgm('foo bar') AS with_space;
~~~

Non-word separator characters do not act as ordinary letters during trigram construction. Consequently, `pg_trgm` **does not strongly distinguish hyphens `-`, pipes `|`, or punctuation** in identifier codes.

That is another reason **never to verify SKUs or transaction codes using similarity**: `AB-123` and `AB123` can score differently from business expectations.

### 4.3. Trigrams are not embeddings or synonyms

~~~text
"laptop" vs "máy tính xách tay"
~~~

Two phrases can share very few trigrams despite having the same meaning. Conversely, two products differing in capacity or variant while sharing most characters can score quite high.

**Trigram similarity is a character-level signal, not semantic proof.**

### 4.4. Short and long strings

Very short strings like `"a"` or `"an"` yield very few useful trigrams, making fuzzy results noisy. Conversely, on a very long passage, whole-string `similarity` can be low even when a user typed one word in the middle accurately. That is why **word similarity**, **strict word similarity**, and length-based fallbacks exist.

## 5. similarity(text, text): Whole-String Comparison

~~~sql
SELECT
    similarity('keyboard', 'keyboard') AS exact_score,
    similarity('keyboard', 'keybord') AS typo_score,
    similarity('keyboard', 'monitor') AS unrelated_score;
~~~

Scores:

- Range from **0 to 1**.
- Higher scores indicate more shared trigrams.
- `1` means identical trigram sets, **not a substitute for SQL `=` equality** across all systems.
- Never translate into "95% probability of being the same product".

### 5.1. similarity is symmetric

~~~sql
SELECT
    similarity('keyboard', 'keybord') AS a_to_b,
    similarity('keybord', 'keyboard') AS b_to_a;
~~~

`similarity` over two trigram sets is symmetric. That differs from **`word_similarity`**: it expects the "search term/phrase" as the first argument and the "candidate text containing the best match" as the second argument.

### 5.2. Scores need deterministic ordering

~~~sql
SELECT
    product_id,
    product_name,
    similarity(product_name, 'keyboard') AS score
FROM catalog_products
ORDER BY score DESC, product_id
LIMIT 10;
~~~

This conceptual query will be applied to the lab table shortly. `product_id` acts as a tie-breaker so rows with equal scores return in a deterministic order for APIs and pagination.

### 5.3. Why not always use whole-string similarity?

Comparing `"wireless"` against `"wireless mechanical keyboard"` can score fairly low because the full product name has many extra trigrams. Yet a user who only remembers one **word inside the name** does not want longer names penalized heavily. In that case, `word_similarity('wireless', full_name)` often fits better.

## 6. word_similarity(text, text): Matching a Contiguous Extent

`word_similarity(search_term, candidate_text)` finds the highest similarity between the first argument's trigram set and **any contiguous slice of the ordered trigram sequence** of the second argument.

~~~sql
SELECT
    similarity('word', 'two words') AS entire_string,
    word_similarity('word', 'two words') AS best_extent,
    word_similarity('words', 'two words') AS word_variant;
~~~

Per the official documentation example, `word_similarity('word', 'two words')` equals **0.8**; it compares against the best contiguous trigrams matching `word`, not the entire string.

### 6.1. Argument order matters

~~~sql
SELECT
    word_similarity(
        'bluetooth',
        'Tai nghe bluetooth khong day'
    ) AS query_inside_title,
    word_similarity(
        'Tai nghe bluetooth khong day',
        'bluetooth'
    ) AS whole_title_inside_query;
~~~

The two results are **not guaranteed to be equal**. Typical search puts the **user's term first** and the product name or passage second.

### 6.2. Word similarity does not enforce whole-word boundaries

`word_similarity` scans trigram extents without **requiring** the matched slice's boundaries to align with word boundaries. That helps when a user types part of a word, yet can also match mid-word substrings and produce false positives.

~~~sql
SELECT
    word_similarity('key', 'keyboard') AS substring_match,
    strict_word_similarity('key', 'keyboard') AS whole_word_match;
~~~

The two scores can differ markedly because the strict version respects word boundaries in the second string.

### 6.3. When to use it?

`word_similarity` fits when the query is a **short word/phrase** and the name/description contains multiple words. Do not assume it is ideal for comparing two long passages or matching distinct coded entities.

## 7. strict_word_similarity(text, text): Word Boundaries

`strict_word_similarity(search_term, candidate_text)` shares the goal of "finding the most similar slice in the second string", but restricts candidate slices to align with **word boundaries**.

~~~sql
SELECT
    strict_word_similarity('word', 'two words')
        AS strict_score,
    similarity('word', 'words')
        AS simple_score;
~~~

In the official documentation example, both values are roughly **0.571429**. This shows `strict_word_similarity` selects the **whole word** `words` rather than an interior slice.

### 7.1. Choosing among similarity, word_similarity, and strict_word_similarity

| Function | What It Compares | Best Fit |
| --- | --- | --- |
| `similarity(a, b)` | Two strings' full trigram sets | Comparing similar-length names, deduplicating candidates |
| `word_similarity(a, b)` | Best contiguous slice of `b`, possibly mid-word | Autocomplete / partial-word fuzzy matching |
| `strict_word_similarity(a, b)` | Best contiguous slice along **whole-word boundaries** of `b` | Matching a search term/phrase against complete words |

### 7.2. "Strict" does not mean exact

`strict_word_similarity` is still **approximate similarity**, not 100% exact keyword matching. A typo inside a word can still match if the score exceeds the threshold.

### 7.3. When users enter multi-word names

For `"chuot gaming khong day"`, whole-string similarity, word similarity, and strict word similarity may rank products differently. To choose, **evaluate search relevance on a real query suite** rather than assuming one function is universally best.

## 8. Hands-on Dataset

We use a dedicated schema `trgm_lab_327` and a products table containing Vietnamese names, English names, intentional typos, and near-identical names differing in specifications.

### 8.1. Create the schema and table

~~~sql
-- Must be installed in the database by a privileged account:
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE SCHEMA trgm_lab_327;

CREATE TABLE trgm_lab_327.products (
    product_id BIGINT PRIMARY KEY,
    sku TEXT NOT NULL UNIQUE,
    product_name TEXT NOT NULL,
    category TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL
        DEFAULT CURRENT_TIMESTAMP
);
~~~

### 8.2. Load sample data

~~~sql
INSERT INTO trgm_lab_327.products
    (product_id, sku, product_name, category, description, is_active)
VALUES
    (1, 'KB-001', 'Bàn phím cơ không dây', 'keyboard',
        'Bàn phím mechanical kết nối Bluetooth', TRUE),
    (2, 'KB-002', 'Bàn phím cơ có dây', 'keyboard',
        'Mechanical keyboard dùng cáp USB-C', TRUE),
    (3, 'KB-003', 'Bàn phím văn phòng', 'keyboard',
        'Bàn phím phổ thông gõ văn bản', TRUE),
    (4, 'KB-004', 'Wireless mechanical keyboard', 'keyboard',
        'Compact keyboard with Bluetooth', TRUE),
    (5, 'KB-005', 'Mechanical keyboard RGB', 'keyboard',
        'Gaming keyboard 87 keys', TRUE),
    (6, 'MS-001', 'Chuột không dây Bluetooth', 'mouse',
        'Chuột máy tính kết nối Bluetooth', TRUE),
    (7, 'MS-002', 'Chuột gaming không dây', 'mouse',
        'Wireless gaming mouse', TRUE),
    (8, 'MS-003', 'Chuột gaming có dây', 'mouse',
        'Wired gaming mouse', TRUE),
    (9, 'HD-001', 'Tai nghe Bluetooth không dây', 'headphone',
        'Tai nghe chụp tai có microphone', TRUE),
    (10, 'HD-002', 'Tai nghe Bluetooh thể thao', 'headphone',
        'Tên có typo có chủ ý để kiểm thử', TRUE),
    (11, 'CB-001', 'Cáp USB-C 1m', 'cable',
        'Cáp sạc dài một mét', TRUE),
    (12, 'CB-002', 'Cáp USB-C 2m', 'cable',
        'Cáp sạc dài hai mét', TRUE),
    (13, 'LB-001', 'Laptop văn phòng 14 inch', 'laptop',
        'Máy tính xách tay phục vụ công việc', TRUE),
    (14, 'LB-002', 'Máy tính xách tay đồ họa', 'laptop',
        'Laptop GPU rời', TRUE),
    (15, 'DP-001', 'Màn hình máy tính 24 inch', 'monitor',
        'Màn hình độ phân giải Full HD', TRUE),
    (16, 'DP-002', 'Màn hình máy tính 27 inch', 'monitor',
        'Màn hình độ phân giải QHD', TRUE),
    (17, 'KB-006', 'Ban phim co khong day', 'keyboard',
        'Tên không dấu có chủ ý', TRUE),
    (18, 'KB-007', 'Bàn phím cơ không dây mini', 'keyboard',
        'Bàn phím nhỏ gọn', TRUE),
    (19, 'MS-004', 'Chuột Bluetooth', 'mouse',
        'Phiên bản cũ ngừng bán', FALSE),
    (20, 'HD-003', 'Headphones wireless noise cancelling', 'headphone',
        'Over-ear headset', TRUE);

ANALYZE trgm_lab_327.products;
~~~

Every product has a unique `product_id` and `sku`. `sku` illustrates **exact search**—never verify codes with similarity. `is_active` lets exercises filter to active products only.

### 8.3. Search outputs depend on thresholds

The similarity queries below use `ORDER BY score DESC` or `distance ASC`. **Exact row counts and ordering must be observed in real PostgreSQL**—never assume a threshold of 0.3 returns a fixed count of ten across every language or collation.

### 8.4. Why include both accented and unaccented rows?

`'Bàn phím cơ không dây'` and `'Ban phim co khong day'` differ in characters. Trigrams compare characters and **do not automatically "know" they are equivalent without diacritics**. Storing a normalized unaccented field is a separate data-design decision covered later.

## 9. Simple Query: Displaying Fuzzy Scores

~~~sql
SELECT
    product_id,
    product_name,
    ROUND(
        similarity(product_name, 'bluetooh')::numeric,
        3
    ) AS score
FROM trgm_lab_327.products
WHERE is_active
ORDER BY
    similarity(product_name, 'bluetooh') DESC,
    product_id
LIMIT 10;
~~~

This query **ranks all active products** by score; without a filtering threshold, completely unrelated items can still appear in the top 10.

### 9.1. Adding a score threshold

~~~sql
SELECT
    product_id,
    product_name,
    similarity(product_name, 'bluetooh') AS score
FROM trgm_lab_327.products
WHERE is_active
  AND similarity(product_name, 'bluetooh') >= 0.3
ORDER BY score DESC, product_id
LIMIT 10;
~~~

This expresses a **fixed threshold in the expression**, which is easy to read. However, `similarity(...) >= ...` **is not a trigram operator designed to use a trigram index by threshold** like `%` is. On large tables, prefer index-supported operators or suitable top-N strategies.

### 9.2. A high score does not confirm the right product

`'Cáp USB-C 1m'` and `'Cáp USB-C 2m'` share most trigrams yet represent two distinct product specs. Never automatically swap cart items based on `similarity`; require explicit selection of `product_id`/`sku`.

## 10. The % Operator: Filtering by Similarity Threshold

The operator:

~~~sql
text_expression % text_expression
~~~

returns SQL `boolean`, testing whether the similarity of both arguments exceeds **`pg_trgm.similarity_threshold`**. In current PostgreSQL docs, the default is typically **0.3**.

~~~sql
SELECT
    product_id,
    product_name,
    similarity(product_name, 'bluetooh') AS score
FROM trgm_lab_327.products
WHERE is_active
  AND product_name % 'bluetooh'
ORDER BY score DESC, product_id
LIMIT 10;
~~~

Crucially, `%` **has index support** via `gin_trgm_ops` and `gist_trgm_ops` when an index and suitable plan exist. Writing `similarity(product_name, 'bluetooh') > 0.3` in `WHERE` does not ensure the planner produces the same indexed access path.

### 10.1. Similar goal, different index usability

~~~sql
-- Filter using an index-supported operator:
WHERE product_name % 'bluetooh'

-- Compute score manually against a constant:
WHERE similarity(product_name, 'bluetooh') >= 0.3
~~~

These two expressions are **not completely identical**: `%` uses the current threshold and checks `>=` per PostgreSQL's threshold semantics, whereas the second hardcodes `0.3` and lacks the same trigram index sargability.

### 10.2. Do not tune solely by inspecting %

If threshold `0.3` lets irrelevant products through, raising or lowering the threshold is a **suggestion-quality** decision. Measure **precision/recall** and user experience before finalizing.

### 10.3. Too low a threshold increases cost

When the threshold is low, more rows satisfy `%`. The index returns many candidates requiring heap rechecks, plus sorting and scoring overhead—so having GIN does not guarantee fast search.

## 11. Operators <% and %>: Word Similarity

Word similarity operators:

| Operator | Meaning |
| --- | --- |
| `query <% candidate` | Checks whether `word_similarity(query, candidate)` meets threshold |
| `candidate %> query` | **Commutator** of `query <% candidate` |

The threshold is controlled by `pg_trgm.word_similarity_threshold`, defaulting typically to **0.6**.

### 11.1. Finding a near-matching word inside a long name

~~~sql
SELECT
    product_id,
    product_name,
    word_similarity('bluetooh', product_name) AS score
FROM trgm_lab_327.products
WHERE is_active
  AND 'bluetooh' <% product_name
ORDER BY score DESC, product_id
LIMIT 10;
~~~

Here:

- `'bluetooh'` is the **user's term** (on the left);
- `product_name` is the **text searched for the closest segment** (on the right).

With a trigram index on `product_name`, the word-similarity operator can use the index to narrow candidates.

### 11.2. Swapping order with the commutator

~~~sql
SELECT
    product_id,
    product_name,
    word_similarity('bluetooh', product_name) AS score
FROM trgm_lab_327.products
WHERE is_active
  AND product_name %> 'bluetooh'
ORDER BY score DESC, product_id;
~~~

`%>` simply **swaps the two operands** of `<%`, not a different similarity family.

### 11.3. Swapping function arguments is not a commutator

~~~sql
word_similarity('bluetooh', product_name)
~~~

and:

~~~sql
word_similarity(product_name, 'bluetooh')
~~~

do not necessarily return the same value. When you want the column on the left in a filter, use the **commutator operator `%>`**, rather than silently flipping arguments while keeping `<%`.

### 11.4. Using word similarity on long descriptions

~~~sql
SELECT
    product_id,
    product_name,
    word_similarity('wireless', description) AS description_score
FROM trgm_lab_327.products
WHERE word_similarity('wireless', description) > 0.5
ORDER BY description_score DESC, product_id;
~~~

This example scores `description`; to filter with a trigram index, you need an index **on `description` itself** (or a matching expression) and an index-supported word-similarity operator aligned with the configured threshold.

## 12. Operators <<% and %>>: Strict Word Similarity

| Operator | Meaning |
| --- | --- |
| `query <<% candidate` | `strict_word_similarity(query, candidate)` meets threshold |
| `candidate %>> query` | Commutator of `<<%` |

Threshold is governed by `pg_trgm.strict_word_similarity_threshold`, defaulting typically to **0.5**.

~~~sql
SELECT
    product_id,
    product_name,
    strict_word_similarity('gaming', product_name) AS score
FROM trgm_lab_327.products
WHERE is_active
  AND 'gaming' <<% product_name
ORDER BY score DESC, product_id
LIMIT 10;
~~~

This operator helps avoid letting a **mid-word slice** count as the best match, while still performing fuzzy word matching rather than exact word matching.

### 12.1. Comparing against word similarity

~~~sql
SELECT
    product_name,
    word_similarity('key', product_name) AS loose_score,
    strict_word_similarity('key', product_name) AS strict_score
FROM trgm_lab_327.products
WHERE product_id IN (4, 5)
ORDER BY product_id;
~~~

The goal is observing the difference between `key` matching inside `keyboard` vs enforcing whole-word boundaries. **Do not assume the strict score must be 0**, because similarity between `key` and the full word `keyboard` is still positive.

### 12.2. Calibrating strict thresholds with real data

`0.5` is only a starting point. Product names with abbreviations, brands, model numbers, or multi-syllable words may need a different policy. Do not reuse one threshold across product names, long descriptions, emails, and people's names without measuring.

## 13. Threshold Parameters in pg_trgm

Three independent thresholds:

| GUC | Operator Using It | Reference Default |
| --- | --- | ---: |
| `pg_trgm.similarity_threshold` | `%` | 0.3 |
| `pg_trgm.word_similarity_threshold` | `<%` and `%>` | 0.6 |
| `pg_trgm.strict_word_similarity_threshold` | `<<%` and `%>>` | 0.5 |

### 13.1. View current thresholds

~~~sql
SHOW pg_trgm.similarity_threshold;
SHOW pg_trgm.word_similarity_threshold;
SHOW pg_trgm.strict_word_similarity_threshold;
~~~

### 13.2. Test changes scoped to a transaction

~~~sql
BEGIN;

SET LOCAL pg_trgm.similarity_threshold = 0.45;

SELECT
    product_id,
    product_name,
    similarity(product_name, 'bluetooh') AS score
FROM trgm_lab_327.products
WHERE is_active
  AND product_name % 'bluetooh'
ORDER BY score DESC, product_id;

ROLLBACK;
~~~

After `ROLLBACK`, `SET LOCAL` ceases to apply. This keeps experiments from altering thresholds for other requests or leaking onto pooled connections.

### 13.3. Testing word similarity

~~~sql
BEGIN;

SET LOCAL pg_trgm.word_similarity_threshold = 0.5;

SELECT
    product_id,
    product_name,
    word_similarity('bluetooh', product_name) AS score
FROM trgm_lab_327.products
WHERE 'bluetooh' <% product_name
ORDER BY score DESC, product_id;

ROLLBACK;
~~~

### 13.4. Testing strict word similarity

~~~sql
BEGIN;

SET LOCAL pg_trgm.strict_word_similarity_threshold = 0.65;

SELECT
    product_id,
    product_name,
    strict_word_similarity('gaming', product_name) AS score
FROM trgm_lab_327.products
WHERE 'gaming' <<% product_name
ORDER BY score DESC, product_id;

ROLLBACK;
~~~

### 13.5. Avoid set_limit / show_limit in new code

`set_limit(real)` and `show_limit()` are legacy APIs for the `%` threshold and are marked **deprecated**. On versions supporting GUCs, prefer `SHOW` and `SET LOCAL pg_trgm.similarity_threshold` instead of scattering `set_limit` calls.

### 13.6. Connection pool hazards

A session-level `SET pg_trgm.similarity_threshold = 0.4` can persist on a connection returned to a pool. Subsequent requests will experience altered search results unless the pool resets session state.

**Rule:** experiment with transactions + `SET LOCAL`, or manage thresholds explicitly per query/session. Never alter server-wide thresholds just to test one query.

### 13.7. Do not turn thresholds into identity verification thresholds

A threshold of `0.8` or `0.95` does not mean "80%/95% confidence". Use thresholds strictly to **filter search candidates**; verifying a product or entity requires checking exact attributes.

## 14. Trigram Distance: <->, <<->, and <<<->

Besides `similarity` (higher = closer), `pg_trgm` offers **distance** operators (smaller = closer).

| Operator | Logical Formula | Direction |
| --- | --- | --- |
| `a <-> b` | `1 - similarity(a, b)` | Symmetric |
| `a <<-> b` | `1 - word_similarity(a, b)` | `a` is term, `b` is candidate |
| `a <->> b` | Commutator of `b <<-> a` | Swapped arguments |
| `a <<<-> b` | `1 - strict_word_similarity(a, b)` | `a` is term, `b` is candidate |
| `a <->>> b` | Commutator of `b <<<-> a` | Swapped arguments |

Distances range from **0 to 1**. Distance `0` means similarity `1` under that metric—**not a guarantee of identical characters**.

### 14.1. Checking score and distance consistency

~~~sql
SELECT
    similarity('keyboard', 'keybord') AS score,
    'keyboard' <-> 'keybord' AS distance,
    similarity('keyboard', 'keybord')
        + ('keyboard' <-> 'keybord') AS sum_to_one;
~~~

Conceptually `score + distance = 1`; due to `real` floating-point rounding, never check bit-for-bit equality as a business constraint.

### 14.2. Nearest-neighbor ordering

~~~sql
SELECT
    product_id,
    product_name,
    product_name <-> 'Ban phim co khong day'
        AS distance
FROM trgm_lab_327.products
WHERE is_active
ORDER BY
    product_name <-> 'Ban phim co khong day',
    product_id
LIMIT 10;
~~~

This query asks for the **10 closest active rows** without requiring a fixed threshold. Without an access path supporting distance ordering, PostgreSQL may score many rows and sort.

### 14.3. Word-distance with argument order

~~~sql
SELECT
    product_id,
    product_name,
    'bluetooh' <<-> product_name AS word_distance
FROM trgm_lab_327.products
WHERE is_active
ORDER BY 'bluetooh' <<-> product_name, product_id
LIMIT 10;
~~~

To find a segment inside `product_name` close to `bluetooh`, put the term on the left and the candidate on the right just like `word_similarity`. You can use the commutator `product_name <->> 'bluetooh'`, keeping the directional semantics consistent.

### 14.4. Strict word-distance

~~~sql
SELECT
    product_id,
    product_name,
    'gaming' <<<-> product_name AS strict_distance
FROM trgm_lab_327.products
WHERE is_active
ORDER BY 'gaming' <<<-> product_name, product_id
LIMIT 10;
~~~

GiST supports nearest-neighbor ordering for these distance operators; GIN trigram indexes lack GiST's **KNN index-order scan** capability.

## 15. Why Do % Filtering and ORDER BY similarity Often Pair Together?

A common pattern:

~~~sql
SELECT
    product_id,
    product_name,
    similarity(product_name, 'keybord') AS score
FROM trgm_lab_327.products
WHERE is_active
  AND product_name % 'keybord'
ORDER BY score DESC, product_id
LIMIT 10;
~~~

Two stages:

1. **Candidate filtering:** `product_name % 'keybord'` keeps rows above the threshold.
2. **Ranking:** `similarity` orders candidates from closest to farthest.

A GIN/GiST trigram index reduces rows inspected, yet `ORDER BY similarity(...) DESC` may still require a **`Sort`**. Index support for a filter operator does not guarantee rows emerge pre-sorted by score.

### 15.1. When only top-K nearest are needed

~~~sql
SELECT product_id, product_name
FROM trgm_lab_327.products
WHERE is_active
ORDER BY product_name <-> 'keybord'
LIMIT 10;
~~~

With a **GiST trigram index**, PostgreSQL can run a KNN index scan to fetch nearest neighbors without sorting the entire table by distance. That is a decisive difference when choosing GIN vs GiST.

### 15.2. Combining threshold and top-K

~~~sql
SELECT
    product_id,
    product_name,
    similarity(product_name, 'keybord') AS score
FROM trgm_lab_327.products
WHERE is_active
  AND product_name % 'keybord'
ORDER BY product_name <-> 'keybord', product_id
LIMIT 10;
~~~

Inspect the query plan to verify whether the index handles filtering and ordering as expected; non-trigram predicates like `is_active` also influence early termination and heap fetches.

### 15.3. Ties need a secondary key

Products can have equal distances. `ORDER BY distance, product_id` ensures deterministic SQL ordering. Adding a tie-breaker may require the planner to resolve ties in an additional step; **keep results deterministic first, then measure cost via `EXPLAIN`**.

## 16. Case-Insensitive Matching and Vietnamese

`pg_trgm` performs **case-insensitive** similarity comparisons by default in standard builds, though exact behavior depends on environment, collation, and build. Never infer **Vietnamese accent-insensitivity**.

~~~sql
SELECT
    similarity('Bluetooth', 'bluetooth') AS case_variant,
    similarity('ban phim', 'bàn phím') AS accent_variant,
    similarity('laptop', 'máy tính xách tay') AS synonym_variant;
~~~

The results illustrate three separate dimensions:

- **Case**: uppercase vs lowercase;
- **Accent**: Vietnamese diacritics;
- **Synonym/meaning**: different words referring to the same product category.

No single mechanism inside `pg_trgm` handles all three automatically.

### 16.1. Unicode normalization

Visually identical strings can have different Unicode byte sequences (e.g., precomposed characters vs base character + combining mark). For consistent matching:

- Standardize on one Unicode normalization form (typically NFC) at ingest and search time;
- Align Java, PostgreSQL, and index handling;
- Test accented Vietnamese strings in both forms;
- Never strip characters arbitrarily in domains where diacritics carry legal or identity meaning.

PostgreSQL supports `normalize(text, form)` in suitable encodings for Unicode normalization, though **that is not diacritic stripping**.

### 16.2. Accent-insensitive search is an explicit design choice

To make `"ban phim"` reliably find `"bàn phím"`, you can design a **`search_name`** field normalized for case and diacritics per product policy.

Example record:

~~~text
product_name: "Bàn phím cơ không dây"
search_name:  "ban phim co khong day"
~~~

Then build a trigram index on `search_name`, and normalize **the search query input** with the exact same algorithm and version.

### 16.3. Be careful with the unaccent extension

PostgreSQL's `unaccent` extension removes diacritics based on rules/dictionaries, yet **do not hastily create an expression index on `unaccent(product_name)`**. Standard `unaccent` definitions are not marked `IMMUTABLE` because they depend on mutable config/dictionaries; expression indexes require genuinely immutable functions.

A safer approach when rules can evolve is **storing a normalized column maintained by the application/ETL**, recomputing and rebuilding the index during migrations when rules change. **Never create a fake `IMMUTABLE` UDF wrapper just to bypass index checks.**

### 16.4. Over-normalization can erase distinctions

Stripping accents, hyphens, whitespace, or symbols can collapse previously distinct codes/names together. For SKU/model search, keep an **exact-matching channel** independent of the fuzzy normalized column.

### 16.5. Suggested Vietnamese search flow

A practical pipeline:

~~~text
User query
    |
    +-- Trim / length limit / Unicode normalization
    |
    +-- Exact SKU or identifier search (prioritized if syntax matches)
    |
    +-- Accented Vietnamese search, LIKE/FTS/trigrams
    |
    +-- Search on normalized unaccented column
    |
    +-- Merge, rerank, deduplicate, filter active/tenant
    |
    +-- Display candidates; never auto-pick silently for the user
~~~

Implement only the steps actually needed, backed by benchmarks and search-quality tests.

## 17. What Is a Trigram Index?

`pg_trgm` provides two **index operator classes**:

- `gin_trgm_ops` for **GIN** (*Generalized Inverted Index*);
- `gist_trgm_ops` for **GiST** (*Generalized Search Tree*).

They let the planner use indexes for similarity operators as well as pattern-matching operators like `LIKE`, `ILIKE`, `~`, `~*`, and `=`. Still, **index support never guarantees the planner uses the index**: row count, selectivity, table size, statistics, and cost estimates decide.

### 17.1. GIN: mapping trigrams to candidates

Think of GIN as mapping search trigrams directly to **rows containing candidate trigrams**. PostgreSQL then verifies the full condition per the operator.

~~~sql
CREATE INDEX idx_products_name_gin_327
ON trgm_lab_327.products
USING gin (product_name gin_trgm_ops);
~~~

Example:

~~~sql
SELECT
    product_id,
    product_name,
    similarity(product_name, 'keybord') AS score
FROM trgm_lab_327.products
WHERE product_name % 'keybord'
ORDER BY score DESC, product_id
LIMIT 10;
~~~

With a GIN index on `product_name`, `%` can use the index to find candidates. `ORDER BY score DESC` may still sort those candidates.

### 17.2. GiST: trigram signatures and nearest-neighbor ordering

~~~sql
CREATE INDEX idx_products_name_gist_327
ON trgm_lab_327.products
USING gist (product_name gist_trgm_ops);
~~~

The GiST trigram opclass represents trigrams using **approximate bitmap signatures**. False positives can occur during index lookup, so the executor **rechecks** the predicate against real row values.

GiST is especially valuable for:

~~~sql
SELECT
    product_id,
    product_name,
    product_name <-> 'keybord' AS distance
FROM trgm_lab_327.products
ORDER BY product_name <-> 'keybord'
LIMIT 10;
~~~

PostgreSQL can perform a **KNN GiST index scan** by distance, avoiding scoring and sorting the whole table on every top-K query under favorable conditions.

### 17.3. Do not think GiST returns pre-verified exact matches

Signatures are an **approximate index structure**, not permission for wrong SQL results: the index yields candidates and PostgreSQL verifies exact conditions during execution.

### 17.4. Neither GIN nor GiST replaces B-tree for common exact equality

~~~sql
SELECT product_id
FROM trgm_lab_327.products
WHERE sku = 'KB-001';
~~~

A `UNIQUE` B-tree index on `sku` is naturally optimized for exact equality and uniqueness enforcement. Although trigram indexes can support `=` on text, they are generally **less efficient than B-tree** for simple equality lookups.

## 18. Comparing GIN and GiST for pg_trgm

| Criterion | GIN `gin_trgm_ops` | GiST `gist_trgm_ops` |
| --- | --- | --- |
| Primary strength | Filtering candidates by trigrams/operators | Filtering candidates and nearest-neighbor ordering by distance |
| `WHERE name % query` | Index supported | Index supported |
| Suitable `LIKE`/`ILIKE`/regex | Index supported | Index supported |
| `ORDER BY name <-> query LIMIT K` | **No** GiST-style KNN index ordering | **Supports** GiST KNN |
| Structure | Inverted index | Signature tree |
| False positives / recheck | May need recheck per operator | Approximate signatures may need recheck |
| Size | Depends on data and config | Depends on data and `siglen` |
| Insert/update cost | Depends on pending list/maintenance and workload | Depends on GiST tree and workload |
| Best suited when | Filtering substrings/similarity in large sets | Fetching top-K nearest neighbors by distance |

There is no universal rule that "GIN is always faster than GiST" or vice versa. Measure real queries, write rates, index sizes, memory, returned row counts, and concurrency.

### 18.1. Do not create both in production "just in case"

Keeping two indexes on the same column adds:

- Disk storage;
- WAL and disk writes on every `INSERT`/`UPDATE`;
- `VACUUM`/maintenance work;
- Locks or operational overhead during builds;
- Shared-buffer cache pressure.

Create both in the lab to observe; in production, choose based on query families and benchmarks.

### 18.2. Customizing GiST siglen

~~~sql
CREATE INDEX idx_products_name_gist32_327
ON trgm_lab_327.products
USING gist (
    product_name gist_trgm_ops(siglen=32)
);
~~~

Per current PostgreSQL docs, the default signature length is **12 bytes**, and `siglen` can be increased within supported opclass limits (e.g., 32 bytes). Longer signatures generally **reduce false positives and heap accesses** at the cost of a **larger index**.

**Never stack multiple GiST indexes with different `siglen` values on the same production table** without clear goals and cost benchmarks. Use a separate lab/benchmark table to compare.

### 18.3. Broad filtering vs top-K

Design comparison:

~~~sql
-- Candidate filtering:
SELECT product_id
FROM trgm_lab_327.products
WHERE product_name % 'keybord';

-- Nearest neighbors:
SELECT product_id
FROM trgm_lab_327.products
ORDER BY product_name <-> 'keybord'
LIMIT 5;
~~~

The two queries have **different result semantics**:

- The first returns every row exceeding the current threshold;
- The second always tries to return up to 5 closest rows, even with poor scores if no good candidate exists.

For spell-suggestion autocomplete, decide whether to apply a minimum similarity threshold to avoid nonsensical suggestions.

## 19. GiST KNN: ORDER BY distance LIMIT

This is a flagship GiST use case:

~~~sql
EXPLAIN
SELECT
    product_id,
    product_name
FROM trgm_lab_327.products
ORDER BY product_name <-> 'bluetooh'
LIMIT 5;
~~~

When the planner chooses a GiST KNN index scan, an illustrative plan looks like:

~~~text
Limit
  -> Index Scan using idx_products_name_gist_327 on products
       Order By: (product_name <-> 'bluetooh'::text)
~~~

This is an **illustrative plan**, not guaranteed on a 20-row table. On tiny tables, `Seq Scan + Sort` is often cheaper.

### 19.1. Why does ORDER BY distance differ from ORDER BY score?

~~~sql
ORDER BY product_name <-> 'bluetooh'
~~~

uses the distance operator supported by the GiST opclass. By contrast:

~~~sql
ORDER BY similarity(product_name, 'bluetooh') DESC
~~~

shares the general ranking intent, yet is not a **KNN index-order operator**. For GiST top-K, write `ORDER BY indexed_column <-> query` using the supported operator direction.

### 19.2. Top-K by word similarity

~~~sql
SELECT
    product_id,
    product_name,
    'bluetooh' <<-> product_name AS distance
FROM trgm_lab_327.products
WHERE is_active
ORDER BY 'bluetooh' <<-> product_name
LIMIT 5;
~~~

This looks for a contiguous slice in `product_name` closest to `bluetooh`. Per `pg_trgm` docs, word and strict-word distance operators also have GiST KNN support. **Do not flip argument order arbitrarily.**

### 19.3. Tie-breakers and KNN

~~~sql
SELECT
    product_id,
    product_name,
    product_name <-> 'bluetooh' AS distance
FROM trgm_lab_327.products
ORDER BY product_name <-> 'bluetooh', product_id
LIMIT 5;
~~~

Adding `product_id` as a tie-breaker guarantees stable SQL ordering. The planner may add an extra step to order ties; **prioritize correct results first, then inspect `EXPLAIN` to check cost**.

### 19.4. KNN does not replace business filters

If only active products of the current tenant are visible, always keep:

~~~sql
WHERE is_active
  AND tenant_id = $1
~~~

per your real schema. **Never fetch global top-K across the whole database and filter tenants in the application**, which leaks data and leaves fewer than K valid results.

## 20. LIKE and ILIKE with Trigram Indexes

`pg_trgm` goes beyond fuzzy similarity: GIN/GiST trigram opclasses also accelerate **pattern matching**, even with leading wildcards.

### 20.1. Substring matching with ILIKE

~~~sql
SELECT product_id, product_name
FROM trgm_lab_327.products
WHERE product_name ILIKE '%keyboard%'
ORDER BY product_id;
~~~

A normal B-tree cannot effectively optimize `ILIKE '%...%'` with a leading wildcard; a trigram index extracts trigrams from fixed literal segments of the pattern to find candidates efficiently.

### 20.2. No leading prefix anchor needed like B-tree

~~~sql
-- Contains a word in the middle of the name:
SELECT product_id, product_name
FROM trgm_lab_327.products
WHERE product_name ILIKE '%gaming%'
ORDER BY product_id;
~~~

When the pattern yields enough useful trigrams, the planner can use a GIN/GiST index even with `%` on both sides.

### 20.3. LIKE does not tolerate typos

~~~sql
WHERE product_name ILIKE '%bluetooh%'
~~~

only matches names containing literal `bluetooh`, **never suggesting `bluetooth`**. To tolerate typos, use `%`, `<%`, `<<%`, or KNN distance.

### 20.4. ILIKE depends on data type and collation

For Vietnamese names, `ILIKE` and case-folding rules depend on collation/provider, and some collation types restrict pattern operators. Before deploying to production, verify column collation, PostgreSQL version, and Unicode edge cases.

### 20.5. Overly short patterns

~~~sql
SELECT product_id
FROM trgm_lab_327.products
WHERE product_name ILIKE '%a%';
~~~

For patterns yielding very few or **no useful trigrams**, trigram index lookups can degrade into a **full-index scan** or cause the planner to pick `Seq Scan`. Seeing an index exist does not guarantee a speedup.

A sensible policy:

- 0 characters: do not run catalog-wide fuzzy search;
- 1–2 characters: prefer bounded prefix search/autocomplete;
- Sufficiently long input: enable trigram filters/word similarity;
- Extremely long input: cap length and choose an appropriate search strategy.

Length thresholds are application policies, not a rigid rule that **queries under 3 characters can never use the index**: padding, pattern structure, and operators create variations. Still, patterns with no extractable trigrams will not benefit from the index.

### 20.6. LIKE metacharacters from users

Bind parameters **prevent SQL injection**, yet do not automatically treat `%` and `_` as literal characters inside a `LIKE` pattern.

For instance, if user input `"50%"` is wrapped into `ILIKE '%50%%'`, the user's `%` still acts as a wildcard. To match a **literal percent sign**, escape wildcard characters per `LIKE` rules, specify `ESCAPE`, and test backslashes/Unicode.

With the fuzzy `%` operator, input is **plain text for similarity calculation**, not a `LIKE` pattern—keep the two search flows' input handling separate.

## 21. Regex ~ and ~* Through Trigram Indexes

`pg_trgm` can also assist regex queries when PostgreSQL extracts fixed trigrams:

~~~sql
SELECT product_id, product_name
FROM trgm_lab_327.products
WHERE product_name ~* '(keyboard|bluetooth)'
ORDER BY product_id;
~~~

Operators:

| Operator | Meaning |
| --- | --- |
| `~` | Match regular expression, case-sensitive per applicable rules |
| `~*` | Match regular expression, case-insensitive |

### 21.1. Index support does not accelerate every regex

Overly broad regexes like `'.*'`, patterns of only a few characters, or patterns yielding no required trigrams can force PostgreSQL to scan most of the index or table.

### 21.2. Regex from untrusted input

Never let users supply arbitrary regexes to run unrestricted on large datasets:

- Complex patterns can burn heavy CPU;
- Users can trigger denial-of-service queries;
- Matches can probe strings users should not discover;
- Regex is overkill for simple substring/fuzzy search.

Enforce length limits, execution timeouts, data permissions, bound parameters, and strict pattern policies.

## 22. Partial Trigram Index on Active Data

If an application searches only active products, consider a **partial trigram index**:

~~~sql
CREATE INDEX idx_products_active_name_gin_327
ON trgm_lab_327.products
USING gin (product_name gin_trgm_ops)
WHERE is_active;
~~~

Matching query:

~~~sql
SELECT product_id, product_name
FROM trgm_lab_327.products
WHERE is_active
  AND product_name % 'keybord';
~~~

The planner can use the partial index when it proves the query predicate **implies `is_active`** and cost is favorable.

### 22.1. When does a partial index help?

If only 20% of the catalog is active, a partial index is substantially smaller than a full-table index. If 99% is active, size savings are minimal while maintenance still occurs whenever `is_active` or `product_name` changes.

### 22.2. Generic plans with parameterized active filters

If a query has `is_active = $1` in a generic plan, the planner does not know `$1` is `true` at plan time. The partial predicate `WHERE is_active` cannot be proven across arbitrary parameter values. **Test generic vs custom prepared plans** when combining partial indexes with bound parameters.

### 22.3. Never filter inactive rows in the application after LIMIT

~~~text
Wrong:
  top 10 nearest across entire catalog
  -> filter inactive products in Java
  -> may leave only 1-2 results and leak unauthorized data.

Right:
  SQL WHERE is_active / tenant_id / visibility
  -> search and rank within permitted rows
  -> LIMIT 10
~~~

Business visibility and authorization predicates must live inside the database query at the right level.

## 23. Indexing Normalized Expressions

Suppose the application stores:

~~~sql
ALTER TABLE trgm_lab_327.products
ADD COLUMN search_name TEXT;
~~~

Then application/ETL code populates an unaccented, normalized version per approved policy. **Illustrative SQL populating a few rows in the lab**:

~~~sql
UPDATE trgm_lab_327.products
SET search_name = CASE product_id
    WHEN 1 THEN 'ban phim co khong day'
    WHEN 2 THEN 'ban phim co co day'
    WHEN 3 THEN 'ban phim van phong'
    WHEN 17 THEN 'ban phim co khong day'
    WHEN 18 THEN 'ban phim co khong day mini'
    ELSE lower(product_name)
END;
~~~

This is **not a complete diacritic-stripping pipeline**: only a few rows were assigned manually for illustration. Production needs a consistent normalizer across **all** rows and inputs, with versioned rules.

### 23.1. Index on the normalized column

~~~sql
CREATE INDEX idx_products_search_name_gin_327
ON trgm_lab_327.products
USING gin (search_name gin_trgm_ops);
~~~

~~~sql
SELECT
    product_id,
    product_name,
    similarity(search_name, 'ban phim co') AS score
FROM trgm_lab_327.products
WHERE search_name % 'ban phim co'
ORDER BY score DESC, product_id
LIMIT 10;
~~~

The app displays the accented `product_name` while searching against `search_name`. Input `'ban phim co'` must go through the exact same normalization rules as the column.

### 23.2. Index on lower(product_name)

For stable lowercasing only:

~~~sql
CREATE INDEX idx_products_lower_name_gin_327
ON trgm_lab_327.products
USING gin (lower(product_name) gin_trgm_ops);
~~~

Matching query:

~~~sql
SELECT product_id, product_name
FROM trgm_lab_327.products
WHERE lower(product_name) % lower('Bluetooth')
ORDER BY product_id;
~~~

Do not assume an index on `lower(product_name)` will be used for `product_name % 'Bluetooth'`: **that is a different index expression**. Because trigram comparison is already case-insensitive in many builds, adding `lower` can be redundant; use it only when explicit uniform normalization is required.

### 23.3. Normalized columns must stay synchronized

If you rename a product without updating `search_name`, searches against the normalized column will hit stale data. Ensure:

- Application write paths always update both in the same transaction;
- Or use a trigger/generated column if immutability conditions hold;
- Audit jobs detect drift and backfill;
- Migrations reindex whenever normalization rules change;
- Tests cover Unicode, diacritics, and SKU patterns.

### 23.4. Do not confuse normalization with business semantics

Turning `"Cáp USB-C 1m"` into `"cap usb c 1m"` does not erase the real distinction between `1m` and `2m`. Keep structured product attributes such as length, capacity, and model codes intact for accurate filtering and reranking.

## 24. Online Index Creation and Maintenance

On large tables under continuous writes, a plain `CREATE INDEX` blocks concurrent writes during the build. PostgreSQL supports:

~~~sql
CREATE INDEX CONCURRENTLY idx_products_name_gin_online_327
ON trgm_lab_327.products
USING gin (product_name gin_trgm_ops);
~~~

**Deploy only when needed, authorized, and workload-tested.** `CREATE INDEX CONCURRENTLY` avoids long write locks at the cost of longer build time, I/O/CPU, and transaction wait phases.

### 24.1. Never run inside an explicit transaction block

~~~sql
-- Invalid:
-- BEGIN;
-- CREATE INDEX CONCURRENTLY ...
-- COMMIT;
~~~

### 24.2. Can leave an invalid index on failure

~~~sql
SELECT
    i.indexrelid::regclass AS index_name,
    i.indisvalid,
    i.indisready
FROM pg_catalog.pg_index AS i
JOIN pg_catalog.pg_class AS c
    ON c.oid = i.indrelid
WHERE c.oid = 'trgm_lab_327.products'::regclass
ORDER BY index_name;
~~~

If a concurrent build fails, never assume nothing was left behind. Check logs/errors, inspect for `INVALID` indexes, and drop/rebuild safely per version rules.

### 24.3. Impact of multiple indexes

Every `INSERT`/`UPDATE` on product names must update the B-tree and every GIN/GiST index on that column. For low-write, read-heavy catalogs this trade-off works well; for event streams ingesting hundreds of thousands of updates per second, multiple trigram indexes cause severe write amplification.

### 24.4. GIN pending list and VACUUM

GIN's **fastupdate** and pending list smooth certain write workloads, yet the pending list must still be merged and cleaned. When queries suddenly slow down or writes spike, inspect autovacuum, pending-list behavior, and GIN settings in current PostgreSQL docs before blindly tweaking server-wide parameters.

### 24.5. GiST siglen and false positives

If GiST signatures cause excessive rechecks, increasing `siglen` on a new index (with benchmarks) cuts false-positive candidates at the cost of larger index size. Never blame all `Rows Removed by Index Recheck` on bad data.

## 25. EXPLAIN: Verifying Whether the Index Is Actually Used

~~~sql
ANALYZE trgm_lab_327.products;

EXPLAIN (ANALYZE, BUFFERS)
SELECT
    product_id,
    product_name
FROM trgm_lab_327.products
WHERE product_name % 'keybord';
~~~

Illustrative plan when GIN is used:

~~~text
Bitmap Heap Scan on products
  Recheck Cond: (product_name % 'keybord'::text)
  -> Bitmap Index Scan on idx_products_name_gin_327
       Index Cond: (product_name % 'keybord'::text)
~~~

With GiST, you can also see `Bitmap Index Scan` or `Index Scan` with different properties. On 20 rows, PostgreSQL will likely pick `Seq Scan` because scanning the entire small table is cheapest.

### 25.1. Bitmap rechecks

GIN/GiST indexes locate candidate rows matching the operator, while the executor may **recheck** conditions on the heap. In `EXPLAIN ANALYZE`, read:

- `Recheck Cond`;
- `Rows Removed by Index Recheck` if present;
- `Heap Blocks: exact=... lossy=...`;
- `Buffers: shared hit/read`;
- `actual rows`, `loops`, and timings.

### 25.2. KNN GiST plan

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    product_id,
    product_name
FROM trgm_lab_327.products
ORDER BY product_name <-> 'keybord'
LIMIT 10;
~~~

If you see:

~~~text
Index Scan using idx_products_name_gist_327 on products
  Order By: (product_name <-> 'keybord'::text)
~~~

that shows the GiST index provides distance ordering. Seeing `Seq Scan -> Sort -> Limit` on a few dozen rows does not prove GiST lacks KNN support.

### 25.3. Cost is not milliseconds

~~~text
cost=100.00..500.00
actual time=1.234..12.345
~~~

`cost` is the planner's relative estimate; `actual time` is measured runtime in milliseconds for one `EXPLAIN ANALYZE` execution. Run multiple trials and document cache/concurrency state before drawing conclusions.

### 25.4. EXPLAIN ANALYZE executes the SQL

`EXPLAIN (ANALYZE)` **runs the statement** rather than merely printing the plan. On read-only lab `SELECT`s that is safe, whereas running it directly on `UPDATE`/`DELETE` in production mutates real data.

## 26. Creating a Larger Benchmark Dataset (Optional)

With 20 rows, the planner has little reason to pick an index. If your lab machine has sufficient RAM/disk and you want to observe index behavior, create a separate **100,000-row** benchmark table rather than bloating the demo table:

~~~sql
CREATE TABLE trgm_lab_327.large_products AS
SELECT
    g::bigint AS product_id,
    p.product_name || ' ref ' || g::text AS product_name,
    p.category,
    p.is_active
FROM generate_series(1, 100000) AS gs(g)
JOIN trgm_lab_327.products AS p
    ON p.product_id = ((g - 1) % 20 + 1);

ANALYZE trgm_lab_327.large_products;

CREATE INDEX idx_large_products_gin_327
ON trgm_lab_327.large_products
USING gin (product_name gin_trgm_ops);

CREATE INDEX idx_large_products_gist_327
ON trgm_lab_327.large_products
USING gist (product_name gist_trgm_ops);
~~~

**Skip this if resources are tight.** Generating rows and indexes consumes WAL, RAM, and disk. Synthetic data repeating product names + `ref` does not mirror every real-world distribution; it is solely for practicing planner index selection.

### 26.1. GIN filtering

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT product_id, product_name
FROM trgm_lab_327.large_products
WHERE product_name ILIKE '%mechanical%';
~~~

### 26.2. Filtering with %

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT product_id, product_name
FROM trgm_lab_327.large_products
WHERE product_name % 'bluetooh';
~~~

### 26.3. GiST top-K

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT product_id, product_name
FROM trgm_lab_327.large_products
ORDER BY product_name <-> 'bluetooh'
LIMIT 10;
~~~

### 26.4. Why do execution order and caches affect results?

If you benchmark GIN first and GiST second, heap/index blocks may already sit warm in shared buffers or OS cache. Run multiple iterations, alternate tests, inspect shared hits/reads, and monitor CPU/disk. Never crown GIN or GiST faster everywhere from one run differing by a few milliseconds.

### 26.5. Never force the planner just to "see the right index"

Planner `enable_*` switches work for diagnostics via `SET LOCAL`, yet **never disable `Seq Scan` server-wide** just to force a prettier plan. When a sequential scan is genuinely cheaper due to low selectivity, the planner is right to choose it.

## 27. Combining pg_trgm with Full-Text Search

PostgreSQL **Full-Text Search** and **trigram similarity** solve different problems:

| Aspect | Full-Text Search | Trigram Similarity |
| --- | --- | --- |
| Primary unit | Tokens/lexemes, dictionaries, stop words/stemming per config | Three-character slices |
| Best-fit queries | Multi-word search, long documents, lexical ranking | Typos, similar names, substrings/partial words |
| `laptop` vs `máy tính xách tay` | Also requires synonyms/language setup to match | Does not understand meaning |
| Typo `bluetooh` | Likely misses `bluetooth` lexeme | Can suggest spelling close to `bluetooth` |
| Index | Typically GIN on `tsvector` | GIN/GiST with `gin_trgm_ops`/`gist_trgm_ops` |

### 27.1. Basic full-text search query

~~~sql
SELECT
    product_id,
    product_name
FROM trgm_lab_327.products
WHERE to_tsvector(
    'simple',
    product_name || ' ' || description
) @@ plainto_tsquery('simple', 'mechanical keyboard')
ORDER BY product_id;
~~~

`simple` performs basic tokenization and does not translate `"bàn phím"` into `"keyboard"`. Depending on requirements, applications may add custom dictionaries or synonym layers.

### 27.2. Trigrams assisting spell correction before/after FTS

A practical workflow:

1. Run exact/prefix/FTS for the user's query;
2. If too few results return, query **fuzzy suggestions** from a vocabulary dictionary;
3. Display `"Did you mean bluetooth?"`;
4. Let the user confirm/click the suggestion or combine via controlled reranking;
5. Never silently rewrite keywords that could be people's names, model codes, or drug codes.

### 27.3. Building an auxiliary term dictionary

Per PostgreSQL documentation, a table of unique words can be extracted from text search documents. Lab example:

~~~sql
CREATE TABLE trgm_lab_327.search_words AS
SELECT word
FROM ts_stat(
    'SELECT to_tsvector(''simple'', description)
     FROM trgm_lab_327.products'
);

CREATE UNIQUE INDEX idx_search_words_exact_327
ON trgm_lab_327.search_words (word);

CREATE INDEX idx_search_words_trgm_327
ON trgm_lab_327.search_words
USING gin (word gin_trgm_ops);
~~~

`ts_stat` collects word statistics from `tsvector` queries; this auxiliary table does not automatically pick up new words as the catalog evolves. Build a **refresh/update process** for production. In the lab above, it snapshots `description` at creation time.

### 27.4. Spelling suggestions from the vocabulary table

~~~sql
SELECT
    word,
    similarity(word, 'bluetooh') AS score
FROM trgm_lab_327.search_words
WHERE word % 'bluetooh'
ORDER BY score DESC, word
LIMIT 5;
~~~

If `bluetooth` appears in descriptions, it surfaces as a candidate. Which source columns feed the dictionary affects suggestion quality; indexing only `description` may miss brand/model words appearing solely in `product_name`.

### 27.5. Watch Vietnamese tokenization

`simple` splits tokens using the default parser without ensuring semantic **multi-syllable Vietnamese word segmentation**. A phrase like `"máy tính xách tay"` consists of space-separated syllables; semantic search requires dedicated dictionaries or preprocessing.

### 27.6. Never concatenate input into SQL passed to ts_stat

`ts_stat` accepts a **SQL query string** to read `tsvector`s. Pass only controlled constant SQL from trusted sources; never concatenate user input into a SQL string passed to `ts_stat`. In applications, `ts_stat` is an offline dictionary/analysis tool, **not a direct per-request user API**.

## 28. Real-World Product Search Pipeline

A sound search pipeline prioritizes **business accuracy** before falling back to fuzzy matching:

~~~mermaid
flowchart TD
    Q["User enters query"] --> V["Validate length / Unicode / permissions"]
    V --> E{"Query matches SKU/code?"}
    E -->|Yes| X["Exact match via B-tree"]
    E -->|No| P["Prefix / substring / FTS"]
    X --> R["Authorized candidate set"]
    P --> F{"Enough relevant results?"}
    F -->|Yes| R
    F -->|No| T["Fuzzy pg_trgm / word similarity"]
    T --> R
    R --> C["Rerank / filter business attributes"]
    C --> L["LIMIT, stable ordering, UI suggestions"]
~~~

### 28.1. Exact SKU must get dedicated priority

~~~sql
SELECT
    product_id,
    sku,
    product_name
FROM trgm_lab_327.products
WHERE is_active
  AND sku = 'KB-001';
~~~

When a query matches an existing SKU, exact matches take top priority. Never use `sku % 'KB-001'` to determine which SKU a user is purchasing.

### 28.2. Fuzzy search scoped by category

~~~sql
SELECT
    product_id,
    sku,
    product_name,
    similarity(product_name, 'keybord') AS score
FROM trgm_lab_327.products
WHERE is_active
  AND category = 'keyboard'
  AND product_name % 'keybord'
ORDER BY score DESC, product_id
LIMIT 10;
~~~

The `category` filter reflects user selection/product navigation rather than pure ranking. When `category` comes from the user, bind it as a parameter.

### 28.3. Combining exact and fuzzy in one API

An application can run two clearly scoped queries:

- **Exact SKU** query: at most one high-precision result.
- **Fuzzy names** query: a shortlist with scores, thresholds, and `LIMIT`.

The app then merges by **`product_id`**, prioritizing exact hits and labeling fuzzy suggestions clearly. Never silently substitute a fuzzy match into an order line item.

### 28.4. Reranking by product attributes

Similar names differing in specifications need structured filtering/scoring:

- Size, capacity, color, model generation;
- Brand, stock status;
- Exact product code;
- Language and naming style;
- Category relevance.

For example, `"Cáp USB-C 1m"` and `"Cáp USB-C 2m"` share high trigram scores. If the user selected `length_m = 2`, filter or rerank by length as a **typed attribute**, never letting similarity obscure a numeric difference.

### 28.5. Multiple languages

When products have Vietnamese and English names, store aliases/synonyms in a normalized child table rather than gluing all names into one long string. Each alias carries language, type, version, and search text, linking back to `product_id`.

**Fuzzy search on aliases** catches alternate spellings; **exact constraints on `product_id`/SKU** still guard product identity.

## 29. Near-Duplicate Detection

Another use case is helping administrators spot near-identical product names or accidental duplicate entries:

~~~sql
SELECT
    a.product_id AS left_id,
    a.product_name AS left_name,
    b.product_id AS right_id,
    b.product_name AS right_name,
    similarity(a.product_name, b.product_name) AS score
FROM trgm_lab_327.products AS a
JOIN trgm_lab_327.products AS b
    ON a.product_id < b.product_id
   AND a.category = b.category
   AND a.product_name % b.product_name
ORDER BY score DESC, left_id, right_id
LIMIT 50;
~~~

### 29.1. Why `a.product_id < b.product_id`?

This condition avoids:

- Pairing a product with itself;
- Emitting both `(A, B)` and `(B, A)`.

Still, it **does not prove two records are duplicates**. An administrator must still compare model codes, brands, specs, and history.

### 29.2. Self-join cost

With `N` products, candidate pairs grow up to `N(N - 1) / 2` without effective filtering. On tables with millions of rows, never run an unpartitioned fuzzy self-join without a **blocking** strategy by category, brand, or key attributes.

A scalable workflow:

1. Partition by category/brand/blocking key;
2. Compare pairs only within potentially overlapping blocks;
3. Use indexes to retrieve candidates;
4. Enforce batch limits and statement timeouts;
5. Persist candidate pairs and review statuses;
6. Never auto-merge entities solely on high similarity scores.

### 29.3. When not to use pg_trgm for deduplication

When records carry exact identifiers, normalized addresses, emails, phone numbers, or legal entity IDs, use deterministic matching models and verification workflows. Character similarity does not replace ownership or identity verification.

## 30. Evaluating Results with Precision, Recall, and Ranking

Optimizing fuzzy search has **two independent dimensions**:

1. **Relevance** of returned candidates.
2. **Performance** of finding and ranking them.

A query running in 10 ms is not "good" if it returns irrelevant products.

### 30.1. Precision@K

Suppose out of the top 10 results, 7 are labeled relevant by experts:

\[
\mathrm{Precision@10} = \frac{7}{10}=0.7
\]

This is the fraction of relevant items in the top 10—**not a confidence score emitted by `similarity`**.

### 30.2. Recall@K

Suppose the labeled ground truth contains 14 relevant products, and the top 10 retrieve 7 of them:

\[
\mathrm{Recall@10}=\frac{7}{14}=0.5
\]

Raising the threshold can improve precision by cutting false positives while dropping low-scoring relevant items, reducing recall. That **trade-off** must be quantified.

### 30.3. Evaluation query suite

Maintain a representative benchmark suite:

| Query Type | Example | What to Measure |
| --- | --- | --- |
| Correctly spelled | `keyboard` | Exact/near matches rank well |
| Single typo | `keybord` | Is `keyboard` suggested? |
| Multiple typos | `bluetooh` | Are false positives excessive? |
| Accented Vietnamese | `bàn phím` | Proper product distinction |
| Unaccented Vietnamese | `ban phim` | Whether a normalized column is needed |
| Word inside long name | `mechanical` | Whether word similarity fits |
| Very short query | `ph` | Length guard / prefix fallback needed |
| Product code | `KB-001` | Exact SKU prioritized |
| Punctuated SKU | `USB-C` | Tokenizer doesn't lose the code |
| Similar names, different specs | `USB-C 2m` | Right length prioritized |
| Alias / synonym | `laptop` vs `máy tính xách tay` | Don't expect trigrams to translate |
| Special characters | `C++`, `50%` | Escaping / pattern semantics |

### 30.4. Additional ranking metrics

When results have graded relevance (exact, partial, irrelevant), use **MRR**, **MAP**, **nDCG@K**, or well-designed click/conversion metrics. You do not need every metric for a simple "did-you-mean" box, yet at minimum measure **top-K relevance and false-positive rate**.

### 30.5. Thresholds do not transfer uniformly across fields

A threshold of `0.4` on long English names behaves differently from `0.4` on short Vietnamese names. When a product spans multiple languages, columns, or query styles, **calibrate thresholds per field group, length, and context** rather than treating one number as universal.

### 30.6. Latency benchmarks

Measure:

- p50/p95/p99 latency;
- Candidate counts before and after filtering;
- Total buffer hits/reads and temp I/O;
- Index size and maintenance cost;
- Concurrency, CPU, and memory;
- Share of queries using GIN, GiST, or `Seq Scan`;
- Zero-result rate and excessive-result rate;
- Precision/recall@K.

Too low a threshold inflates CPU/sort cost and hurts precision; too high a threshold filters out typos users genuinely wanted to find.

## 31. Java/JDBC: Parameterized Fuzzy Search

In Java applications, pass search terms via **`PreparedStatement`**, never string concatenation into SQL.

### 31.1. Sample API using the % operator

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.List;

public class ProductFuzzySearch {
    public record Candidate(
            long productId,
            String sku,
            String productName,
            double similarity) {}

    public static List<Candidate> search(
            Connection connection,
            String query,
            int requestedLimit) throws SQLException {

        if (query == null || query.isBlank()) {
            return List.of();
        }

        String normalizedInput = query.strip();
        if (normalizedInput.length() < 3
                || normalizedInput.length() > 100) {
            return List.of(); // Lab policy: search 3..100 characters.
        }

        int limit = Math.max(1, Math.min(requestedLimit, 20));
        String sql = """
            SELECT
                product_id,
                sku,
                product_name,
                similarity(product_name, ?) AS score
            FROM trgm_lab_327.products
            WHERE is_active
              AND product_name % ?
            ORDER BY score DESC, product_id
            LIMIT ?
            """;

        List<Candidate> results = new ArrayList<>();
        try (PreparedStatement ps = connection.prepareStatement(sql)) {
            ps.setString(1, normalizedInput);
            ps.setString(2, normalizedInput);
            ps.setInt(3, limit);

            try (ResultSet rs = ps.executeQuery()) {
                while (rs.next()) {
                    results.add(new Candidate(
                            rs.getLong("product_id"),
                            rs.getString("sku"),
                            rs.getString("product_name"),
                            rs.getDouble("score")));
                }
            }
        }
        return results;
    }
}
~~~

This example uses Java **records** and text blocks (requiring Java 17+). On older Java versions, replace them with standard classes and strings.

### 31.2. Why bind the query twice?

The two placeholders correspond to:

~~~sql
similarity(product_name, ?)
product_name % ?
~~~

JDBC does not repeat one bound value across multiple `?` markers automatically; bind every placeholder by position.

### 31.3. Do not carelessly set session-wide thresholds

If an application needs a non-default threshold, run `SET LOCAL` inside the **same transaction** as the query.

~~~java
// Illustrative transaction workflow:
// connection.setAutoCommit(false);
// try (Statement st = connection.createStatement()) {
//     st.execute("SET LOCAL pg_trgm.similarity_threshold = 0.45");
// }
// ... run PreparedStatement ...
// connection.commit(); // Or rollback if testing only.
~~~

Always handle exceptions, rollbacks, and restoring auto-commit per connection-pool rules. Never execute session-level `SET` and return a dirty connection to the pool without resetting session state.

### 31.4. User-provided queries are text, not SQL

User inputs containing `'`, `%`, `_`, or Unicode cannot alter the SQL structure in this prepared statement. The trigram `%` operator treats input as plain text; however, when switching to `LIKE`/`ILIKE`, `%` and `_` act as wildcards and require explicit escaping.

### 31.5. Authorization comes before LIMIT

When real tables include `tenant_id`, `visibility`, or `is_active`, SQL must filter permitted rows **before ranking and `LIMIT`**. Never fetch top 20 across all tenants and keep only 5 in Java: you discard valid matches and risk leaking data in logs/telemetry.

### 31.6. Short queries and response timeouts

Enforce:

- Input length bounds;
- `LIMIT` caps;
- Query/statement timeouts per policy;
- Rate limits and query budgets;
- Caching where workloads repeat;
- Debouncing/limits before firing full searches on every keystroke.

This protects database resources when concurrent users type into autocomplete boxes.

## 32. SQL API Returning Ranked Candidates with Score Breakdown

An application may want to inspect why a result surfaced. Example:

~~~sql
SELECT
    product_id,
    sku,
    product_name,
    similarity(product_name, 'ban phim co') AS full_score,
    word_similarity('ban phim co', product_name) AS partial_score,
    strict_word_similarity('ban phim co', product_name)
        AS strict_score
FROM trgm_lab_327.products
WHERE is_active
  AND category = 'keyboard'
ORDER BY
    word_similarity('ban phim co', product_name) DESC,
    product_id
LIMIT 10;
~~~

This is an **exploratory ranking query for a small catalog**; on large tables, `ORDER BY word_similarity(...)` across every row causes full scans and sorts, so filter candidates first using an index-supported operator.

### 32.1. Filter candidates before computing multiple scores

~~~sql
SELECT
    product_id,
    sku,
    product_name,
    word_similarity('ban phim co', product_name) AS score
FROM trgm_lab_327.products
WHERE is_active
  AND category = 'keyboard'
  AND 'ban phim co' <% product_name
ORDER BY score DESC, product_id
LIMIT 10;
~~~

With an index on `product_name`, `<%` narrows candidates. The output remains a **fuzzy similarity score**, not a probability that the user wants to buy the item.

### 32.2. A composite score is not a statistical probability

An app might compute:

~~~text
rank = w1 * full_similarity
     + w2 * word_similarity
     + w3 * category_match
     + w4 * inventory_signal
~~~

Weights must be tuned and validated using labeled benchmarks and user feedback. Adding weighted terms does not turn a composite score into a calibrated "probability of relevance".

## 33. Technical Conditions Affecting Correctness

### 33.1. NULL strings

~~~sql
SELECT
    similarity(NULL::text, 'keyboard') AS null_similarity;
~~~

Returns SQL `NULL`. On nullable product columns, `product_name % 'keyboard'` yields `UNKNOWN` for `NULL` rows and fails `WHERE`; enforce `NOT NULL` when names are mandatory.

### 33.2. Empty strings

~~~sql
SELECT
    similarity('', 'keyboard') AS empty_score,
    show_trgm('') AS empty_trigrams;
~~~

Empty input lacks enough signal for meaningful fuzzy search. Return a defined default list or skip searching instead of scoring the entire catalog.

### 33.3. Punctuation and whitespace

Trigram extraction ignores non-word characters and pads each word. Changing `-`, `|`, spaces, or special symbols in product codes can alter scores in ways that do not match business intent. Keep an exact path for model codes.

### 33.4. Unicode normalization and collation upgrades

Upgrading ICU/libc collations or changing input/column normalization logic can change **index values and search semantics**. During text-rule migrations:

1. Identify dependent indexes;
2. Recompute normalized fields under the new version;
3. Rebuild affected indexes;
4. Test relevance and uniqueness/business constraints;
5. Prepare rollback steps and before/after audits.

### 33.5. Do not misuse fuzzy search on personal data

Fuzzy name search can match multiple distinct individuals. It does not prove identity, must never bypass access controls, and must comply with personal-data policies. In financial, healthcare, or customer records, confirm suggestions using exact verified attributes in authorized workflows.

### 33.6. Correctness across tenant/role permissions

In multi-tenant SaaS, `pg_trgm` is purely a query access method with **no built-in authorization**. SQL predicates and Row-Level Security must protect data so queries only rank and return rows the session is permitted to see.

## 34. Diagnostic Runbook When Fuzzy Search Is Slow

### Step 1 — Identify the query shape

Is it `LIKE '%abc%'`, `ILIKE`, `%`, `<%`, `<<%`, or `ORDER BY <-> LIMIT`?

**Do not optimize the wrong operator:** GIN helps filter `%`, while GiST accelerates KNN `<->` ordering.

### Step 2 — Check table size and selectivity

- Does the table have dozens, thousands, or millions of rows?
- Is the term long enough to yield useful trigrams?
- Is the threshold too low, generating huge candidate sets?
- Are `category`/`is_active`/`tenant` filters present?
- How many rows does it return, and what is `LIMIT`?

### Step 3 — Read EXPLAIN

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT product_id, product_name
FROM trgm_lab_327.products
WHERE is_active
  AND product_name % 'keybord'
ORDER BY similarity(product_name, 'keybord') DESC
LIMIT 10;
~~~

Inspect `Index Cond`, bitmap rechecks, `Filter`, `actual rows`, sort method, and buffer reads.

### Step 4 — Verify actual indexes

~~~sql
SELECT
    schemaname,
    tablename,
    indexname,
    indexdef
FROM pg_catalog.pg_indexes
WHERE schemaname = 'trgm_lab_327'
ORDER BY tablename, indexname;
~~~

Check that `gin_trgm_ops`/`gist_trgm_ops` sits on the right column/expression and inspect any partial predicate.

### Step 5 — Diagnose the root cause

| Symptom | Possible Cause | Remediation |
| --- | --- | --- |
| `Seq Scan` on 20 rows | Full scan is cheaper | No need to force index |
| `Seq Scan` on 10M rows | Missing index, overly low threshold, short term | Check plan, selectivity, index, pattern |
| `similarity(...) >= 0.3` slow | Not using index-supported operator | Switch to `%` with matching threshold |
| KNN query with GIN index | GIN lacks GiST-style index-order distance | Consider GiST |
| Very short `LIKE` pattern | Yields no useful trigrams | Prefix search, enforce minimum length |
| GIN bitmap returns too many rows | Low threshold, broad match | Raise threshold, refine query/filters |
| High GiST recheck count | Lossy signature / selectivity | Tune `siglen`, check cost/index choice |
| Normalized column returns wrong hits | Stale `search_name` / mismatched normalizer | Sync normalization and backfill |
| CPU spikes during autocomplete | High request rate, short queries, concurrency | Debounce, rate-limit, cache |
| Slow API despite fast SQL | Network, JSON serialization, ORM, pool | Profile application tier |

### Step 6 — Benchmark diverse terms

Do not measure `'keyboard'` alone; test typos, accented/unaccented Vietnamese, short queries, coded names, category-filtered queries, and discontinued products.

### Step 7 — Measure write and operational impact

GIN/GiST index size, `INSERT`/`UPDATE` latency, WAL volume, autovacuum, and concurrent `CREATE INDEX` overhead are all part of the optimization decision.

### Step 8 — Prepare rollback

Every change to extensions, indexes, normalized columns, or ranking queries needs a migration, rollback plan, and before/after relevance tests. Never raise `similarity_threshold` server-wide and treat resulting misses as random bugs.

## 35. Common Mistakes with pg_trgm

| Misconception / Mistake | Why It Is Dangerous or Wrong | Right Approach |
| --- | --- | --- |
| `pg_trgm` understands synonyms | Compares trigrams, not word meaning | FTS + synonym/alias layer or semantic layer |
| `ban phim` automatically matches `bàn phím` cleanly | Does not strip diacritics automatically | Controlled Unicode/accent normalization |
| Similarity score 0.9 means 90% same product | Not a probability | Treat strictly as a ranking signal |
| `similarity` always fits short terms in long names | Penalized by extra words | Try `word_similarity` / `strict_word_similarity` |
| `word_similarity(a, b) = word_similarity(b, a)` | Arguments play asymmetric roles | Query term on left, candidate on right |
| `strict_word_similarity` enforces exact word match | Still fuzzy, only aligned to word boundaries | Use `=` or token checks when exact is needed |
| `%` is always modulo | On `text` with `pg_trgm`, it is the similarity operator | Check operand types and extension |
| `%` always uses threshold `0.3` | Threshold can be changed per session/transaction | Check `SHOW pg_trgm.similarity_threshold` |
| `<%` shares the same threshold as `%` | Word similarity has its own GUC | Check `word_similarity_threshold` |
| `<<%` shares the same threshold as `<%` | Strict word has its own GUC | Check `strict_word_similarity_threshold` |
| Flipping `word_similarity` args keeps meaning | Output can change | Use commutators `%>` / `%>>` |
| Larger distance means closer | `distance = 1 - similarity` | `ORDER BY distance ASC` |
| `ORDER BY similarity DESC` triggers GiST KNN | KNN requires distance operators | Use `ORDER BY column <-> query LIMIT` |
| GIN supports KNN top-K like GiST | GIN lacks index-order distance scans | Pick GiST for nearest neighbors |
| GiST is always faster than GIN | Depends on filter vs KNN workload | Benchmark real queries |
| GIN is always faster than GiST | Differs across KNN and `siglen` workloads | Benchmark |
| B-tree on name handles `ILIKE '%abc%'` | Leading wildcard defeats B-tree prefix range | Consider trigrams |
| Trigram index speeds up every short pattern | Few or zero trigrams extracted | Prefix search / length bounds |
| `ILIKE` fixes typos | Pattern match only, not fuzzy | Use `%`, `<%`, or KNN |
| Any regex uses the trigram index | Some patterns yield no trigrams | Bound regex, inspect `EXPLAIN` |
| `LIKE '%50%%'` matches literal `%` | `%` remains a wildcard | Escape metacharacters |
| `similarity(...) >= 0.3` uses GIN like `%` | Function call may score many rows | Filter candidates with operators |
| `SHOW pg_trgm.similarity_threshold` is cluster-fixed | GUC can vary per session/transaction | Check config source; use `SET LOCAL` |
| `set_limit` is the modern API | Deprecated legacy API | Use GUC `SET`/`SHOW` |
| `SET` on a pooled connection resets automatically | Session state can leak | Use `SET LOCAL` in transaction and pool reset |
| GiST signatures never false-positive | Recheck may be needed | Inspect `Rows Removed by Index Recheck` |
| Raising `siglen` always speeds up queries | Increases index size and other costs | Benchmark |
| `CREATE INDEX CONCURRENTLY` has zero risks | Can leave `INVALID` indexes | Monitor logs / `pg_index` |
| `CREATE INDEX CONCURRENTLY` runs inside `BEGIN` | Unsupported by PostgreSQL | Run outside explicit transactions |
| Extra trigram indexes don't affect writes | Increases maintenance and WAL | Measure `INSERT`/`UPDATE` |
| Existing indexes are always used by planner | Cost/selectivity may favor `Seq Scan` | Check `EXPLAIN`, especially on small tables |
| `pg_trgm` only works when `LIKE` has no leading `%` | Trigrams support leading wildcards | Ensure patterns have useful trigrams |
| Partial active GIN applies to all queries | Query must prove active predicate | Write explicit filter / test generic plan |
| Filtering tenants in Java after `LIMIT` is equivalent | Breaks top-K and risks data leaks | Filter inside SQL |
| Fuzzy SKU search replaces unique constraints | No authenticity/uniqueness guarantee | B-tree exact `=` and `UNIQUE` constraint |
| `unaccent` can be marked `IMMUTABLE` freely for indexes | Rules/dictionaries can change | Store normalized text and migrate |
| Stripping diacritics has no downsides | Can merge distinct words/codes | Keep original data and test |
| `pg_trgm` handles all Vietnamese names cleanly | Trigrams don't segment or parse Vietnamese | Evaluate on Vietnamese test suites |
| Top 10 always contains 10 relevant items | KNN returns closest even if all are poor | Minimum threshold + empty state |
| `ORDER BY score` is stable on equal scores | Ties lack deterministic order | Add `product_id` tie-breaker |
| Testing one `keyboard` query suffices | Misses typos, languages, lengths | Labeled benchmark suite |
| Measuring latency alone without precision | Fast search with wrong results | Measure both relevance and latency |
| `pg_stat_user_indexes.idx_scan = 0` means useless | Stats may have reset, or unique/rare index | Long-term observation and constraints |
| Fast PostgreSQL query guarantees fast API | Pool, network, or mapping may lag | Trace end-to-end |
| Bound SQL parameters enforce search permissions | Injection safety differs from authorization | Filter tenant/RLS/visibility |

## 36. Hands-on Exercises

Exercises use `trgm_lab_327.products` and the indexes shown above. For several exercises, the answer is **reasoning and tool selection** rather than a hardcoded similarity number: inspect actual values in PostgreSQL rather than guessing. Run GUC changes inside lab transactions with `SET LOCAL` and `ROLLBACK`.

### Exercise 1 — Check the extension

Write SQL confirming `pg_trgm` is installed in the current database, showing its version and schema.

**Hint:** `pg_extension`.

### Exercise 2 — Inspect trigrams of a word

~~~sql
SELECT show_trgm('cat');
~~~

**Question:** Why does `cat` have trigrams starting and ending with spaces? How many spaces are padded at the start and end?

**Answer:** Two at the start, one at the end **per word**.

### Exercise 3 — Single-character typo

Compare:

~~~sql
SELECT
    similarity('keyboard', 'keybord') AS typo_score,
    similarity('keyboard', 'monitor') AS unrelated_score;
~~~

**Exercise:** Explain based on trigram overlap without guessing exact numbers before running.

### Exercise 4 — Whole-string vs word match

Compute:

~~~sql
SELECT
    similarity('wireless', 'wireless mechanical keyboard'),
    word_similarity('wireless', 'wireless mechanical keyboard'),
    strict_word_similarity('wireless', 'wireless mechanical keyboard');
~~~

**Question:** Why does a long string usually cause whole-string similarity to differ from word/strict similarity?

### Exercise 5 — Flipping arguments

Compare `word_similarity('bluetooth', product_name)` with `word_similarity(product_name, 'bluetooth')` on a long name.

**Conclusion:** `word_similarity` is not symmetric. Which argument is the query, and which is the candidate?

### Exercise 6 — Strict word boundaries

Compare `word_similarity('key', 'keyboard')` and `strict_word_similarity('key', 'keyboard')`.

**Question:** By what rule does `strict` pick an extent, and is it synonymous with exact matching?

### Exercise 7 — Inspect three thresholds

Run:

~~~sql
SHOW pg_trgm.similarity_threshold;
SHOW pg_trgm.word_similarity_threshold;
SHOW pg_trgm.strict_word_similarity_threshold;
~~~

**Hint:** Reference defaults are 0.3, 0.6, and 0.5 respectively; actual values may have been altered.

### Exercise 8 — The % operator

Write a query filtering the catalog with `product_name % 'bluetooh'`, sorted by `similarity(...) DESC`.

**Question:** Why is `%` better for trigram index usage than `similarity(...) >= threshold`?

### Exercise 9 — Tuning threshold in a transaction

~~~sql
BEGIN;
SET LOCAL pg_trgm.similarity_threshold = 0.6;
SELECT product_id
FROM trgm_lab_327.products
WHERE product_name % 'bluetooh';
ROLLBACK;
~~~

**Question:** Does the `0.6` threshold remain after `ROLLBACK`?

**Answer:** No; `SET LOCAL` applies only within the transaction.

### Exercise 10 — Word similarity operator

Write a query using `'bluetooh' <% product_name` and display `word_similarity('bluetooh', product_name)`.

**Question:** Which commutator operator puts `product_name` on the left?

**Answer:** `product_name %> 'bluetooh'`.

### Exercise 11 — Strict word operator

Write a query using `'gaming' <<% product_name` sorted by `strict_word_similarity`.

**Question:** Which GUC controls its threshold?

### Exercise 12 — Comparing % vs <% and <<%

On `'mechanical'` and long English names, run all three queries using `%`, `<%`, and `<<%`.

**Question:** How do candidate differences relate to score type and word boundaries?

### Exercise 13 — Distance

Compute:

~~~sql
SELECT
    similarity('keyboard','keybord') AS sim,
    'keyboard' <-> 'keybord' AS dist;
~~~

**Guided answer:** Mathematically `dist = 1 - sim`, subject to floating-point rounding.

### Exercise 14 — Top-K by distance

Write a query fetching the five closest products to `'keybord'` using `ORDER BY product_name <-> 'keybord' LIMIT 5`.

**Question:** How does this differ from `WHERE product_name % 'keybord'`?

### Exercise 15 — Word distance

Write `ORDER BY 'bluetooh' <<-> product_name`.

**Question:** Why should the term be on the left? What is the commutator syntax?

### Exercise 16 — Strict word distance

Write `ORDER BY 'gaming' <<<-> product_name` for top 5. State the difference between this metric and full-string `<->`.

### Exercise 17 — GIN index

Create:

~~~sql
CREATE INDEX idx_practice_name_gin_327
ON trgm_lab_327.products
USING gin (product_name gin_trgm_ops);
~~~

**Question:** When can GIN help filter candidates? Does creating the index guarantee the Query Planner uses it?

### Exercise 18 — GiST index

Create:

~~~sql
CREATE INDEX idx_practice_name_gist_327
ON trgm_lab_327.products
USING gist (product_name gist_trgm_ops);
~~~

**Question:** Why can GiST fit nearest-neighbor queries?

### Exercise 19 — GIN and ORDER BY distance

With only a GIN index, can `ORDER BY product_name <-> 'keybord' LIMIT 10` use GiST-style KNN index ordering?

**Answer:** Not via GiST KNN; the planner may have to score and sort rows.

### Exercise 20 — GiST siglen

Explain `gist_trgm_ops(siglen=32)` and the trade-off between index size and signature accuracy / heap rechecks.

### Exercise 21 — LIKE with leading wildcard

~~~sql
SELECT product_id, product_name
FROM trgm_lab_327.products
WHERE product_name ILIKE '%keyboard%';
~~~

**Question:** What can a trigram index accelerate here that a standard B-tree struggles with when patterns have a leading `%`?

### Exercise 22 — ILIKE is not fuzzy

Search `'%bluetooh%'` with `ILIKE` vs `product_name % 'bluetooh'`.

**Question:** Why doesn't the first match `bluetooth`, whereas the second finds near matches?

### Exercise 23 — Overly short patterns

For `ILIKE '%a%'`, explain why a GIN trigram index cannot be assumed effective. Propose an autocomplete policy for 1–2 character queries.

### Exercise 24 — Regex

Write a query using `~* '(keyboard|bluetooth)'`.

**Question:** Can a regex `'.*'` yield enough trigrams for selective index search?

### Exercise 25 — Exact SKU

~~~sql
SELECT product_id
FROM trgm_lab_327.products
WHERE sku = 'KB-001';
~~~

**Question:** Why use a unique/B-tree exact lookup instead of `sku % 'KB-001'`?

### Exercise 26 — Near-duplicate product names

Compare `'Cáp USB-C 1m'` with `'Cáp USB-C 2m'`.

**Question:** Is a high score enough to swap a cart item? Name business attributes that must be checked.

### Exercise 27 — Inactive products

Write a fuzzy search with `WHERE is_active`.

**Question:** Why does filtering in Java after `LIMIT` break both top-K and data-access security?

### Exercise 28 — Partial GIN index

Create a partial GIN index `WHERE is_active` and explain when the planner matches a query to it. Under a generic plan with `is_active = $1`, why might the partial index be skipped?

### Exercise 29 — Unicode NFC and diacritics

Explain why `'bàn phím'` and `'ban phim'` are not automatically treated as identical by `pg_trgm`. Distinguish **Unicode normalization** from **diacritic stripping**.

### Exercise 30 — unaccent and IMMUTABLE

A developer wraps `unaccent` in a UDF marked `IMMUTABLE` to build an index.

**Exercise:** Explain why mutable dictionaries/rules violate true immutability; propose maintaining a `search_name` column with migrations.

### Exercise 31 — search_name can go stale

After renaming `product_name` without updating `search_name`, which queries return stale results? How do you manage write paths, backfills, and rule versions?

### Exercise 32 — Full-text search and typos

Compare searching `'bluetooth'` with `to_tsvector ... @@ ...` vs `'bluetooh'` via trigram correction.

**Question:** Why can trigrams complement full-text search without replacing it?

### Exercise 33 — Suggestion dictionary

Build a vocabulary table from `ts_stat`, add a GIN trigram index on `word`, and query `word % 'bluetooh'`.

**Question:** When `descriptions` update, does the vocabulary table update automatically?

**Answer:** Not in the simple materialized table setup in the lab; a refresh/sync job is needed.

### Exercise 34 — Product suggestions and synonyms

A user types `'laptop'`, while the product is named `'máy tính xách tay'`. Why is trigram similarity insufficient? Propose an alias/synonym/semantic dictionary approach.

### Exercise 35 — Candidate scores and relevance

A query returns 10 results, 7 labeled relevant. Compute Precision@10.

**Answer:** `0.7`. Can the highest similarity score be interpreted as precision?

**Answer:** No; they are two different quantities.

### Exercise 36 — Recall@10

If 14 products are relevant and top 10 find 7, compute Recall@10.

**Answer:** `0.5`. Why does lowering the threshold raise recall while also increasing false positives?

### Exercise 37 — Top-K with overly low scores

A KNN query returns 5 closest products even though none are truly similar. How would you add a confidence/empty-state policy **without** equating scores to probabilities?

### Exercise 38 — Multilingual aliases

Design a `product_aliases` table with `product_id`, `locale`, `alias_name`, `search_name`. State its advantages over concatenating all aliases into one search string.

### Exercise 39 — Near-duplicate self-join

Write `products a JOIN products b` on `a.product_id < b.product_id`, matching category and `a.product_name % b.product_name`.

**Question:** Why does a one-million-product catalog need blocking, batch limits, and manual review?

### Exercise 40 — EXPLAIN with GIN

On the benchmark table (if created), run `EXPLAIN (ANALYZE, BUFFERS)` for `product_name ILIKE '%mechanical%'`.

**Question:** Distinguish `Bitmap Index Scan`, `Bitmap Heap Scan`, `Recheck Cond`, and `Sort`.

### Exercise 41 — EXPLAIN with GiST KNN

On the benchmark table, run `EXPLAIN` for `ORDER BY product_name <-> 'keybord' LIMIT 5`.

**Question:** What does seeing `Index Scan ... Order By` mean? Does seeing `Seq Scan + Sort` on a tiny table prove GiST failed?

### Exercise 42 — Write costs

A table has 10 million products and hundreds of thousands of hourly updates; a team wants GIN plus two GiST trigram indexes on the same column.

**Exercise:** List the measurements needed before rollout: index size, WAL, `INSERT`/`UPDATE` latency, `VACUUM`, read p95, query counts, and rollback plan.

### Exercise 43 — CREATE INDEX CONCURRENTLY

Explain the pros and cons of `CREATE INDEX CONCURRENTLY` in production and why it cannot run inside an explicit transaction.

**Question:** If the command fails, what must you inspect in `pg_index.indisvalid`/`indisready` and do before retrying?

### Exercise 44 — SET LOCAL in connection pools

An application executes `SET pg_trgm.similarity_threshold = 0.1` and returns the connection to the pool.

**Question:** What risk does the next request face? Write a transaction flow using `SET LOCAL` to isolate the threshold.

### Exercise 45 — Safe PreparedStatement

Write a Java method taking `term` and `limit`, using two placeholders for `similarity(name, ?)` and `name % ?`, plus one placeholder for `LIMIT ?`.

**Requirements:** validate length, bind parameters, close `PreparedStatement`/`ResultSet`, and cap result count.

### Exercise 46 — LIKE wildcards from user input

A user searches for literal `'50%'`. Why is building `ILIKE '%50%%'` wrong? Distinguish **SQL injection** from **LIKE wildcard escaping**.

### Exercise 47 — Multi-tenant security

A fuzzy query searches customers across all tenants and filters tenants in Java after `LIMIT 10`.

**Exercise:** Explain why this is wrong, and move `tenant_id`/permission filters into SQL before ranking.

### Exercise 48 — People's names are not identity

Two customers have similar names with trigram similarity `0.97`.

**Question:** Should records be auto-merged? Why are business verification workflows and exact identifiers required?

### Exercise 49 — Unfair benchmark

Team A measures GIN on the first run (cold cache); Team B measures GiST on the second run (warm cache) and concludes GiST is 3× faster.

**Exercise:** Redesign the A/B benchmark: identical SQL/terms/rows, interleaved runs, `EXPLAIN BUFFERS`, index sizes, write throughput, and multiple iterations.

### Exercise 50 — Capstone: fuzzy product search

Design a product search API satisfying:

- Exact SKU matches prioritize **exact B-tree lookup**.
- Accented/unaccented queries normalize consistently while displaying original product names.
- Single-word queries inside long names consider `word_similarity`/`strict_word_similarity`.
- Near-matching names use `similarity` or KNN `<->`.
- Typos trigger trigram fallback or spelling suggestions.
- Very short queries never run unbounded catalog-wide fuzzy scans.
- Search only `is_active` products the user is authorized to view.
- Return at most 10 results with `product_id` tie-breaking and an empty state when relevance is insufficient.
- Pick GIN vs GiST for filtering/substrings vs nearest-neighbor ordering.
- Use prepared statements; never concatenate input into SQL/LIKE/regex.
- Measure Precision@10, Recall@10, p95 latency, buffer reads, index size, and write cost.
- Plan migrations for normalized fields, collation/Unicode, and extension/index upgrades.

**Expected deliverables:** pipeline diagram, two or three core SQL queries, index strategy, labeled test query matrix, threshold policy, and rollback plan if search relevance drops.

## 37. pg_trgm Implementation Checklist

1. [ ] `pg_trgm` extension installed in the target database and reachable schema.
2. [ ] Clarified whether search is exact, substring, prefix, fuzzy, or semantic.
3. [ ] Fuzzy search not used for SKUs, transaction keys, or security tokens.
4. [ ] Understood trigram padding and non-word character behavior.
5. [ ] Selected `similarity`, `word_similarity`, or `strict_word_similarity` per use case.
6. [ ] Used correct operand order for `<%`/`<<%` and their commutators.
7. [ ] Documented all three separate GUC thresholds and test environments.
8. [ ] Experimented with `SET LOCAL`, without leaking session state.
9. [ ] Established Unicode normalization and/or diacritic-stripping policies if needed.
10. [ ] Never falsely marked an `unaccent`-based UDF as `IMMUTABLE`.
11. [ ] Planned maintenance and rule versioning for normalized `search_name`.
12. [ ] Kept exact lookup/alias paths for business identifiers.
13. [ ] Selected GIN for filtering/substrings vs GiST for nearest neighbors appropriately.
14. [ ] Did not expect GIN to provide GiST-style KNN index ordering.
15. [ ] Understood GiST `siglen` trades signature precision against index size.
16. [ ] Tested very short patterns and regexes lacking extractable trigrams.
17. [ ] Escaped `LIKE` wildcards whenever literal matching is intended.
18. [ ] Applied `is_active`/`tenant_id`/authorization filters before `LIMIT`.
19. [ ] Checked whether the planner proves partial index predicates.
20. [ ] Inspected `EXPLAIN`, buffer counts, rechecks, sorts, and actual rows.
21. [ ] Benchmarked on large, realistic data distributions.
22. [ ] Accounted for GIN pending-list and GiST signature maintenance.
23. [ ] Measured `INSERT`/`UPDATE` overhead, WAL, `VACUUM`, and index size.
24. [ ] Tested relevance across typos, Unicode, short/long queries, and lookalike SKUs.
25. [ ] Measured Precision/Recall@K and p95 latency.
26. [ ] Used bind parameters and enforced input-length/`LIMIT` caps.
27. [ ] Configured rate limits, timeouts, and query budgets for autocomplete.
28. [ ] Logged metrics without leaking sensitive search inputs.
29. [ ] Planned updates for dictionaries, aliases, and synonyms.
30. [ ] Prepared migration/rollback plans for extensions, indexes, and normalization updates.

## 38. Official PostgreSQL Documentation

Examples apply to modern PostgreSQL; verify against your server's **exact major version**, as function/operator/index features and planner choices can vary.

- [`pg_trgm` — similarity, operators, thresholds, GiST/GIN](https://www.postgresql.org/docs/current/pgtrgm.html): primary extension documentation covering `show_trgm`, `similarity`, `word_similarity`, `strict_word_similarity`, distance operators, `siglen`, and KNN index scans.
- [CREATE EXTENSION](https://www.postgresql.org/docs/current/sql-createextension.html): installing extensions, schemas, and privileges.
- [CREATE INDEX](https://www.postgresql.org/docs/current/sql-createindex.html): `USING gin/gist`, operator classes, partial indexes, `CONCURRENTLY`.
- [Index Types](https://www.postgresql.org/docs/current/indexes-types.html): B-tree, GiST, GIN, and supported access conditions.
- [Indexes on Expressions](https://www.postgresql.org/docs/current/indexes-expressional.html): indexing `lower(name)` and normalized fields.
- [Partial Indexes](https://www.postgresql.org/docs/current/indexes-partial.html): predicate implication and usage constraints.
- [GIN Indexes](https://www.postgresql.org/docs/current/gin.html): GIN internals, maintenance, and behavior.
- [GIN Tips and Tricks](https://www.postgresql.org/docs/current/gin-tips.html): pending list and read/write performance.
- [GiST Indexes](https://www.postgresql.org/docs/current/gist.html): GiST architecture and operator classes.
- [Pattern Matching](https://www.postgresql.org/docs/current/functions-matching.html): `LIKE`, `ILIKE`, and regular expressions.
- [Text Search](https://www.postgresql.org/docs/current/textsearch.html): `tsvector`, `tsquery`, configurations, and ranking.
- [Text Search Functions and Operators](https://www.postgresql.org/docs/current/functions-textsearch.html): `to_tsvector`, `plainto_tsquery`, `ts_stat`.
- [Data Type Character Sets / Collations](https://www.postgresql.org/docs/current/collation.html): collation behavior and upgrades.
- [String Functions](https://www.postgresql.org/docs/current/functions-string.html): string normalization/transformation and limitations.
- [unaccent](https://www.postgresql.org/docs/current/unaccent.html): text search dictionary and unaccent function; volatility considerations for expression indexes.
- [EXPLAIN](https://www.postgresql.org/docs/current/sql-explain.html): `ANALYZE`, `BUFFERS`, `SETTINGS`, and plan measurement.
- [Using EXPLAIN](https://www.postgresql.org/docs/current/using-explain.html): estimated cost, actual rows, Seq/Index/Bitmap scans.
- [PREPARE](https://www.postgresql.org/docs/current/sql-prepare.html): prepared statements and generic/custom plans when parameters affect planning.

`/docs/current/` URLs point to the current PostgreSQL release. On PostgreSQL 14, 15, 16, 17, 18, or other versions, open the documentation for your **exact version number** before applying GUCs or syntax that may differ.

## 39. Summary

**`pg_trgm`** provides **character-level fuzzy matching** using trigrams. Its three core functions are `similarity(a, b)` for full strings, `word_similarity(a, b)` for the closest contiguous slice in `b`, and `strict_word_similarity(a, b)` for slices aligned with **word boundaries**. They return scores from 0 to 1; high scores mean trigram similarity, **not probability of matching the same entity**.

In SQL, `%`, `<%`/`%>`, and `<<%`/`%>>` filter candidates against **three separate configurable thresholds**. Distance operators `<->`, `<<->`, and `<<<->` measure `1 - similarity` respectively, so **smaller distances mean closer matches**. For top-K nearest results, `ORDER BY indexed_column <-> query LIMIT K` can leverage **GiST KNN**. For filtering many candidates or substring searches with `LIKE`/`ILIKE`, **GIN trigrams** often fit best. Never assume GIN provides GiST-style KNN ordering or accelerates every short pattern.

For Vietnamese, `pg_trgm` does not strip diacritics, segment compound words semantically, or translate synonyms automatically. To support **accent-insensitive** search, build a consistent normalizer and manage `search_name`/migrations rather than falsely declaring an `unaccent`-based UDF as `IMMUTABLE`. For SKUs, model codes, capacity-differentiated product names, or customer identities, always preserve **exact-match paths and business validation**.

A strong fuzzy search solution needs both **relevance and performance**: labeled typo and Unicode test suites, Precision/Recall@K, calibrated thresholds, `EXPLAIN`/buffers, input/`LIMIT` caps, authorization checks, write-cost monitoring, and rollback plans. `pg_trgm` works best as a **controlled candidate finder and spelling suggester**, paired with exact matching, full-text search, and business filters rather than treated as a language-understanding or identity-verification engine.
