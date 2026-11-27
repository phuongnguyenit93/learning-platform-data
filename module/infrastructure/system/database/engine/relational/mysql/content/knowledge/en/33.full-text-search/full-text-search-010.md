# FULLTEXT Update Overhead and Choosing a Dedicated Search Engine

MySQL `FULLTEXT` helps search by words and rank documents, but every `INSERT`, `DELETE`, or `UPDATE` on indexed columns can incur work to maintain the inverted index. When data is large, write workloads are heavy, or multiple FULLTEXT indexes exist, CPU, I/O, storage, and write latency costs must be factored into the design. If a product needs fuzzy matching, autocomplete, synonyms, language-specific analyzers, or scaling search independently from OLTP, a dedicated search engine may be a better fit, though it adds a synchronization pipeline and operational overhead.

A search strategy should start from two sides: the result quality users need and the index maintenance cost under the data write rate. Classify requirements into exact/prefix/substring/term/phrase/fuzzy; determine language, tokenization, stopwords, token length, ranking, pagination, sync latency, and corpus scale. No single index type or single tool is optimal for every requirement.

Choosing a strategy starts from user behavior and data characteristics, and only then moves to engine, parser, mode, and index selection. Determine language, word segmentation, stopwords, token length, desired accuracy, ranking order, pagination requirements, update freshness, and data scale. A fast query that misses important words or ranks results poorly is still a poor search solution.

This lesson belongs to the `DATABASE_MYSQL` module, focusing on table design, data types, keys, SQL queries, indexes, transactions, concurrency control, execution plans, query optimization, and relational database operations. The goal is to choose accurately between FULLTEXT, other SQL search methods, and external search services; implement the right indexes; and then measure both quality and performance using representative data.

After this lesson, you will be able to:

- Distinguish word, phrase, prefix, substring, and approximate/semantic search.
- Decide when to use B-tree, `LIKE`, `FULLTEXT`, or a dedicated search engine.
- Choose InnoDB, parser, natural language mode, boolean mode, and query expansion.
- Design single-column or multi-column FULLTEXT indexes for titles/content.
- Understand the effects of stopwords, token size, collation, and language.
- Choose the ngram parser for non-space-delimited languages such as Chinese, Japanese, and Korean.
- Write `MATCH() AGAINST()` queries with stable ranking, filtering, and pagination.
- Evaluate FULLTEXT limitations, write costs, and impact on replication.
- Estimate the cost of `INSERT`/`UPDATE`/`DELETE` on FULLTEXT columns, bulk loads, and index rebuilds.
- Reduce write amplification by selecting the right number of indexes and structuring ingestion appropriately.
- Choose between MySQL FULLTEXT and a dedicated search engine based on features, read/write load, freshness, and operational cost.
- Test relevance, precision/recall, latency, and index freshness.

## 1. Start with the Type of Search Needed

Before creating an index, classify the queries the product needs to support.

| Need | Example | Typically Suitable Mechanism |
| --- | --- | --- |
| Exact match | Email, order code, SKU | `=` with UNIQUE/B-tree |
| Prefix search | Name starting with `dat` | `LIKE 'dat%'` with a suitable B-tree or range predicate |
| Arbitrary substring search | Code containing `-2026-`, name with mid-string chars | `LIKE '%...%'` on small sets; specialized n-gram/trigram index or search service at scale |
| Word search | Documents containing `database`, `index` | FULLTEXT |
| Phrase search | Phrase `query optimizer` | FULLTEXT phrase search or search engine |
| Required/excluded words | Has `mysql`, lacks `deprecated` | FULLTEXT boolean mode |
| Autocomplete | Suggestions while typing `mys...` | Prefix index, suggestion table, or search service |
| Typos/fuzzy | `myqsl` close to `mysql` | Search engine with fuzzy matching or application logic |
| Synonyms/linguistic | `car` and `automobile` | Synonym dictionary/analyzer in app or search engine; custom design if using MySQL |
| Multi-condition & faceted search | Text + category + price range + facet counts | FULLTEXT + SQL filters at suitable scale; search engine for large facet/search analytics |

Do not use FULLTEXT merely because data is `VARCHAR` or `TEXT`. FULLTEXT parses content into tokens according to parser and language rules; it is not a general-purpose index for arbitrary substrings.

## 2. Choosing Between B-tree, LIKE, FULLTEXT, and a Search Service

### 2.1. B-tree for Equality and Prefix

B-tree is the natural choice for exact key lookups:

```sql
CREATE INDEX idx_article_slug ON article (slug);

SELECT article_id, title
FROM article
WHERE slug = 'mysql-full-text-search';
```

For prefix search, a pattern without a leading wildcard can leverage a B-tree:

```sql
SELECT article_id, title
FROM article
WHERE title LIKE 'MySQL%';
```

Index usability depends on collation, expressions, and pattern shape. B-trees do not efficiently handle substring searches with a leading wildcard.

### 2.2. LIKE for Small Sets or Simple Substrings

```sql
SELECT product_id, product_name
FROM product
WHERE product_name LIKE '%adapter%';
```

The pattern `%adapter%` usually has no starting anchor for a B-tree range lookup, so it may scan many rows. On small tables, rarely changing data, or exact character-sequence requirements, this approach can still be simple and accurate. Measure with `EXPLAIN` and real data before replacing it.

FULLTEXT is not a drop-in replacement for `LIKE '%term%'`: FULLTEXT searches parser-extracted tokens, often drops overly short tokens or stopwords, and does not match arbitrary mid-token character sequences.

### 2.3. FULLTEXT for Word Search

FULLTEXT builds an inverted index: each token maps to the documents containing that token. Queries can search for words, phrases, or boolean expressions while computing a relevance score.

```sql
CREATE TABLE article (
    article_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    title VARCHAR(300) NOT NULL,
    body MEDIUMTEXT NOT NULL,
    published_at DATETIME NOT NULL,
    status VARCHAR(20) NOT NULL,
    PRIMARY KEY (article_id),
    FULLTEXT KEY ft_article_title_body (title, body),
    KEY idx_article_status_date (status, published_at)
) ENGINE = InnoDB;
```

Query:

```sql
SELECT
    article_id,
    title,
    MATCH(title, body) AGAINST ('mysql index' IN NATURAL LANGUAGE MODE) AS score
FROM article
WHERE MATCH(title, body) AGAINST ('mysql index' IN NATURAL LANGUAGE MODE)
  AND status = 'PUBLISHED'
ORDER BY score DESC, article_id DESC
LIMIT 20;
```

`MATCH()` takes the exact list of columns covered by a FULLTEXT index. When designing, use the exact same column list and order as the index definition to avoid errors or failing to match the intended index. A multi-column FULLTEXT index enables searching across that field combination; do not assume an index on `title` alone can serve `MATCH(title, body)`.

### 2.4. Dedicated Search Engine

Consider OpenSearch, Elasticsearch, or an equivalent service when the product needs one or more of the following capabilities:

- Fuzzy matching, typo tolerance, synonym graphs, and language-specific analyzers.
- Autocomplete, search-as-you-type, highlighting, or suggestions.
- Complex search facets/aggregations over large data volumes.
- Distributed indexing, sharding, independent scaling, and dedicated search workload tuning.
- Custom relevance models or ranking combining multiple signals.
- Multiple data sources and index synchronization pipelines.

A search engine is typically a read projection, not a second business source of truth. Keep MySQL as the source of truth; synchronize to the search service via outbox/CDC or a pipeline supporting retries, lag monitoring, and index rebuilds.

## 3. Choosing Storage Engine and Column Types

MySQL supports FULLTEXT indexes on `CHAR`, `VARCHAR`, and `TEXT` columns with InnoDB or MyISAM. For modern transactional applications, InnoDB is typically the default choice due to transactions, crash recovery, and row-level locking. MyISAM is a legacy engine lacking transactions and using a different locking model; choose it only for evaluated compatibility/specialized reasons.

Example InnoDB table:

```sql
CREATE TABLE knowledge_document (
    document_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    title VARCHAR(400) NOT NULL,
    summary TEXT NULL,
    content LONGTEXT NOT NULL,
    language_code VARCHAR(10) NOT NULL,
    visibility VARCHAR(20) NOT NULL DEFAULT 'PUBLIC',
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (document_id),
    FULLTEXT KEY ft_knowledge_title_content (title, content),
    KEY idx_knowledge_language_visibility (language_code, visibility)
) ENGINE = InnoDB
  DEFAULT CHARSET = utf8mb4
  COLLATE = utf8mb4_0900_ai_ci;
```

Here there is one composite FULLTEXT index for `title` and `content`, serving queries searching across both fields together. Additional separate FULLTEXT indexes on `content` or `title` are needed only if the workload has independent single-field search modes or requires separate field weights. Every extra index incurs storage and update overhead.

### 3.1. One Multi-Column Index or Multiple Separate Indexes?

If the search UI always treats title and body as one combined text corpus, a single `FULLTEXT(title, body)` index is the clean choice. If there are two distinct modes (title-only search and full-text search), you may need different indexes or a dedicated search column design. Never assume single-column FULLTEXT indexes automatically combine into a multi-column index.

Example separate indexes:

```sql
ALTER TABLE knowledge_document
ADD FULLTEXT KEY ft_knowledge_title (title),
ADD FULLTEXT KEY ft_knowledge_content (content);
```

Then you can query:

```sql
SELECT document_id, title
FROM knowledge_document
WHERE MATCH(title) AGAINST ('transaction' IN NATURAL LANGUAGE MODE);
```

These separate indexes are optional choices for workloads needing title-only/content-only search or separate field weighting. They increase storage and write costs; if you only search title+content as one corpus, keep the original composite index and skip the two separate indexes. If all three query patterns are required, you may keep all three after measuring costs.

### 3.2. Is the Searchable Data Truly Text?

Do not cram every attribute into a `TEXT` field just for search convenience. Identifiers, statuses, dates, tenants, categories, and monetary amounts should live in properly typed columns with relational indexes. FULLTEXT handles linguistic content; B-trees handle structured filtering/joining/sorting.

## 4. Natural Language Mode

Natural language mode is the default mode of `MATCH() AGAINST()`. MySQL parses the query into words and computes relevance based on word occurrences in the document and across the collection.

```sql
SELECT
    document_id,
    title,
    MATCH(title, content)
        AGAINST ('transaction isolation mysql' IN NATURAL LANGUAGE MODE) AS relevance
FROM knowledge_document
WHERE MATCH(title, content)
        AGAINST ('transaction isolation mysql' IN NATURAL LANGUAGE MODE)
ORDER BY relevance DESC, document_id DESC
LIMIT 20;
```

Characteristics:

- Fits free-text search boxes where users enter a few keywords.
- Results are ranked by relevance; the score is not a correctness probability.
- Words too short, too long, or on the stopword list may be ignored.
- Word order in the query does not equate to an exact phrase requirement.
- Relevance depends on the dataset and algorithm; never compare scores directly across two different tables or corpora.

Natural language mode fits when users want to find documents relevant to a topic without expressing mandatory/exclusion logic.

## 5. Boolean Mode

Boolean mode allows controlling which words are required, which are excluded, word grouping, and certain relevance adjustments.

```sql
SELECT
    document_id,
    title,
    MATCH(title, content)
        AGAINST ('+mysql +index -deprecated' IN BOOLEAN MODE) AS score
FROM knowledge_document
WHERE MATCH(title, content)
        AGAINST ('+mysql +index -deprecated' IN BOOLEAN MODE)
ORDER BY score DESC, document_id DESC
LIMIT 20;
```

Common operators:

| Symbol | Common Meaning |
| --- | --- |
| `+word` | Word must appear |
| `-word` | Exclude documents containing that word |
| `word` | Optional word; without required operators, follows boolean query rules |
| `"a phrase"` | Search for a phrase in token order |
| `word*` | Token prefix/truncation |
| `>` and `<` | Increase/decrease the word's relevance contribution |
| `~word` | Lower score when the word appears |
| `( ... )` | Group expressions |

Example requiring `mysql`, along with either `replication` or `binary log`, while excluding `deprecated`:

```sql
SELECT document_id, title
FROM knowledge_document
WHERE MATCH(title, content) AGAINST (
    '+mysql +(replication "binary log") -deprecated'
    IN BOOLEAN MODE
);
```

Boolean mode suits advanced search UIs or rule-based keyword filters. The syntax is its own query language: binding parameters protects SQL from injection, but does not automatically restrict which boolean operators users can submit. If the product permits only a subset of operators, parse/validate the query grammar in the application.

Do not assume boolean mode results are sorted by score like natural language mode. If ranking is needed, select `MATCH() AGAINST()` and specify `ORDER BY` explicitly; test relevance on a real query set.

## 6. Phrase Search and Query Expansion

### 6.1. Phrase Search

Phrase search uses double quotes inside the query string:

```sql
SELECT document_id, title
FROM knowledge_document
WHERE MATCH(title, content) AGAINST (
    '"query optimizer"' IN BOOLEAN MODE
);
```

Phrase search relies on tokens generated by the parser. It is not the same as matching consecutive bytes via `LIKE '%query optimizer%'`. Punctuation, stopwords, and tokenization affect how phrases are interpreted. Test with real data and languages.

### 6.2. Query Expansion

`WITH QUERY EXPANSION` performs an expanded search: MySQL retrieves documents matching the initial query and uses related words from those documents to expand a follow-up search pass.

```sql
SELECT document_id, title
FROM knowledge_document
WHERE MATCH(title, content) AGAINST (
    'mysql replication' WITH QUERY EXPANSION
)
LIMIT 20;
```

This mode can find documents that lack all original keywords yet share related terms through the initial matches. It can also amplify noise if first-pass results are weak or the corpus contains many generic terms. Enable it only when the product truly needs expansion and relevance testing demonstrates a benefit.

## 7. Tokenization, Stopwords, and Word Length

FULLTEXT does not index text literally character-by-character. The parser splits content into tokens; MySQL then applies stopword and token length rules. Consequently, two identically spelled queries can yield different results if parser/configuration differs.

### 7.1. Minimum/Maximum Token Length

Common variables:

| Engine/Parser | Variable | Common Default |
| --- | --- | --- |
| InnoDB built-in parser | `innodb_ft_min_token_size` | 3 |
| InnoDB built-in parser | `innodb_ft_max_token_size` | 84 |
| MyISAM built-in parser | `ft_min_word_len` | 4 |
| MyISAM built-in parser | `ft_max_word_len` | 84 |

Verify values on the server:

```sql
SHOW VARIABLES LIKE 'innodb_ft_min_token_size';
SHOW VARIABLES LIKE 'innodb_ft_max_token_size';
SHOW VARIABLES LIKE 'ft_min_word_len';
SHOW VARIABLES LIKE 'ft_max_word_len';
```

Changing token size configuration variables typically requires configuring the server and rebuilding FULLTEXT indexes so content is re-tokenized. Changing a variable without rebuilding indexes can leave queries and indexes following mismatched rules. Schedule maintenance and test rebuild duration on near-production data sizes.

### 7.2. Stopwords

Stopwords are common words excluded from the FULLTEXT index or queries per configuration. This shrinks index size and reduces noise, yet can drop meaningful domain terms. For instance, a system searching technical codes or short terminology may need customized stopword/token rules.

MySQL provides a default stopword list and supports custom engine-specific lists. Before making changes, determine:

- Which words must be searchable despite being common.
- Whether the list applies server-wide or to a single table.
- How configuration is synchronized between primary and replicas.
- The procedure to rebuild FULLTEXT indexes after changes.
- Impact on relevance and index size.

For InnoDB, stopword variables and tables include `innodb_ft_enable_stopword`, `innodb_ft_server_stopword_table`, and `innodb_ft_user_stopword_table`. MyISAM has separate settings such as `ft_stopword_file`. Never apply one engine's configuration to the other engine.

## 8. Charset, Collation, and Language

Choose charset/collation from the beginning. For new applications, `utf8mb4` is the standard choice for full Unicode support. Collation affects text comparisons and can influence case sensitivity and accent sensitivity depending on the chosen collation. Do not assume all FULLTEXT searches fold accents or process languages identically.

Inspect column and table configuration:

```sql
SHOW FULL COLUMNS FROM knowledge_document;
SHOW CREATE TABLE knowledge_document;
```

For Vietnamese:

- Accented Vietnamese words can be stored in Unicode; standardize Unicode normalization between ingestion sources and queries.
- Accented vs. unaccented forms, compound words, homographs, and word segmentation are distinct relevance decisions.
- MySQL's built-in parser primarily splits tokens by parser rules rather than acting as a complete Vietnamese linguistic analyzer.
- The ngram parser can be useful for character-sequence/ngram search, but does not inherently understand Vietnamese word boundaries or semantics.
- If accent folding, synonyms, stemming, or high-quality word segmentation are needed, normalize at the ingestion/query layer or use a search engine with an appropriate analyzer; test with a real Vietnamese query set.

## 9. The ngram Parser for Non-Space-Delimited Languages

The default built-in parser typically relies on spaces and punctuation to recognize words. For Chinese, Japanese, and Korean, this segmentation does not work as well as for space-delimited languages. MySQL provides the ngram full-text parser to split text into contiguous fixed-length character sequences.

Example creating a table using the ngram parser:

```sql
CREATE TABLE product_description_cjk (
    product_id BIGINT UNSIGNED NOT NULL,
    description TEXT NOT NULL,
    PRIMARY KEY (product_id),
    FULLTEXT KEY ft_product_description (description) WITH PARSER ngram
) ENGINE = InnoDB
  DEFAULT CHARSET = utf8mb4;
```

Ngram size is controlled by `ngram_token_size` (typically defaulting to 2). This is a server configuration variable; changing it requires rebuilding FULLTEXT indexes so new tokens are generated at the new size. The ngram parser also has distinct stopword rules: stopwords apply at the ngram level rather than whole-word level.

Ngram fits when character-sequence search is required and the language lacks clear word boundaries. However:

- Small token sizes enlarge indexes and can increase false positives.
- Large token sizes shrink indexes yet can miss short queries.
- Phrase matching and relevance must be tested per language.
- It does not replace a specialized analyzer when word-level understanding, grammar, synonyms, or typo handling are needed.

Do not apply ngram to every table simply because data contains Unicode. For Vietnamese or English, the built-in parser may be more suitable; decide using test sets and query logs.

## 10. Building FULLTEXT Indexes and Inspecting Metadata

If an existing table does not yet have this composite FULLTEXT index, you can add it with `ALTER TABLE`. The sample table created in Section 3 already has `ft_knowledge_title_content`, so do not re-run this statement on that exact fixture:

```sql
ALTER TABLE knowledge_document
ADD FULLTEXT KEY ft_knowledge_title_content (title, content);
```

Inspect definition:

```sql
SHOW CREATE TABLE knowledge_document;
SHOW INDEX FROM knowledge_document;
```

Creating an index can consume CPU, I/O, and temporary space while impacting read/write workloads. On large tables, plan capacity and duration; check online DDL capabilities for your exact version, engine, and operation. Never assume adding a FULLTEXT index is always lock-free or without replication lag impact.

FULLTEXT indexes are updated whenever data changes. Every `INSERT`/`UPDATE`/`DELETE` touching indexed columns carries inverted index maintenance cost. Having redundant FULLTEXT indexes significantly increases write amplification and index size.

### 10.1. Work Generated When Writing Data

A FULLTEXT index stores tokens and the mappings between tokens and documents containing them. Therefore:

- **INSERT:** MySQL must parse text in FULLTEXT columns and add tokens to the index.
- **UPDATE on indexed columns:** old tokens may need to be removed and new tokens added. Modifying a long text block usually costs much more work than updating a short field.
- **DELETE:** index entries tied to deleted documents must be handled; bulk deletes can increase I/O and cleanup overhead.
- **UPDATE on non-FULLTEXT-indexed columns:** does not need to re-tokenize unchanged text columns, although the row itself and other B-tree indexes can still incur cost.

Cost depends on text length, token count, number of FULLTEXT indexes, parser, change frequency, and resource contention. A table with three FULLTEXT indexes over the same content incurs greater write amplification than a table keeping only the composite index the workload actually uses. InnoDB manages internal full-text caches and structures; hence the duration of a single DML statement does not always reflect all deferred index work.

### 10.2. Structuring Bulk Loads, Batches, and Rebuilds

For a new table loaded in large batches, consider loading data first and building the FULLTEXT index afterward. This avoids maintaining the inverted index row-by-row throughout the import phase. For a live production table, do not drop indexes casually; use a staging table or maintenance window if index reconstruction is needed, then swap or migrate data via a tested procedure.

```sql
-- Example for a new staging table: create the table and load data first.
CREATE TABLE knowledge_document_stage (
    document_id BIGINT UNSIGNED NOT NULL,
    title VARCHAR(400) NOT NULL,
    content LONGTEXT NOT NULL,
    PRIMARY KEY (document_id)
) ENGINE = InnoDB
  DEFAULT CHARSET = utf8mb4;

-- After importing and verifying staging data:
ALTER TABLE knowledge_document_stage
ADD FULLTEXT KEY ft_stage_title_content (title, content);
```

This illustrates operation ordering, not a complete production table swap script. When building indexes on large tables, budget CPU, I/O, temporary space, DDL duration, and replication lag; check online DDL support for your specific MySQL version and operation.

For continuous write streams:

- Create only FULLTEXT indexes serving actual queries; avoid redundant composite and single-column indexes without matching workloads.
- Coalesce text changes to the same document into a single `UPDATE` rather than many rapid small updates when business logic permits.
- Split bulk writes into moderate batches to bound transaction size, undo logs, and lock hold times.
- When changing only `visibility`, `status`, or other metadata, avoid rewriting the entire `content` column unnecessarily.
- When changing parser, stopwords, or token-size settings, plan a rebuild because old index entries were created under previous rules.

### 10.3. Measure Write Cost Instead of Only SELECT Speed

Benchmarks should exercise both read and write workloads. Compare at least three states on similarly sized data: no FULLTEXT index, one appropriate index, and additional separate indexes if required by the product. Record:

- `INSERT`/`UPDATE`/`DELETE` throughput and p95/p99 latency.
- CPU, I/O, FULLTEXT index size, and total table size.
- Import duration, index creation/rebuild duration, and temporary space needed.
- Replication lag during import, rebuild, and sustained writes.
- Query latency, relevance, and result counts to ensure reducing write cost does not break search requirements.

Do not take a faster `SELECT` query as proof that the entire strategy is better. If write workloads dominate and search needs are simple, one fewer index or a B-tree approach may be a better fit.

### 10.4. When to Choose a Dedicated Search Engine?

| Criterion | MySQL FULLTEXT | Dedicated Search Engine |
| --- | --- | --- |
| Data source | Data and search reside in the same database | Usually a read model synced from MySQL or multiple sources |
| Freshness | Searches reflect MySQL commit state | Typically eventual consistency depending on pipeline |
| Language analysis | Built-in parser and ngram | Richer analyzers, synonyms, stemming, and tokenizers depending on product |
| Advanced search | Natural language, boolean, phrase, query expansion | Fuzzy, autocomplete, typo tolerance, highlighting, facets, custom ranking |
| Write cost | Maintains FULLTEXT index inside transaction/DB workload | MySQL writes plus sync, indexing, and search cluster operations |
| Operations | Fewer moving parts if MySQL is already the main platform | Must manage cluster, mappings, pipelines, retries, lag, rebuilds, monitoring |

Prefer MySQL FULLTEXT when corpus and search load fit the database, near-transactional freshness is needed, queries are mainly word/phrase-based, and keeping architecture simple is valued. Choose a separate search engine when analyzer/ranking requirements exceed built-in parsers, typo/fuzzy/autocomplete/faceting is needed, data comes from multiple sources, or search must scale independently of OLTP.

When splitting out a search service, treat the external index as a rebuildable projection. Use outbox or CDC to synchronize, handle retries/idempotency, monitor lag, and maintain a full rebuild procedure from MySQL. Never send HTTP requests directly from triggers, because a MySQL transaction cannot roll back side effects already committed in an external service.

## 11. MATCH() AGAINST() and Result Ranking

### 11.1. Basic Query Pattern

```sql
SELECT
    document_id,
    title,
    MATCH(title, content)
        AGAINST (? IN NATURAL LANGUAGE MODE) AS relevance
FROM knowledge_document
WHERE MATCH(title, content)
        AGAINST (? IN NATURAL LANGUAGE MODE)
  AND visibility = 'PUBLIC'
ORDER BY relevance DESC, document_id DESC
LIMIT ?;
```

`?` illustrates a prepared statement parameter. In the application, bind the same search text to both positions and bind `limit` as an integer. Never concatenate user strings directly into SQL.

### 11.2. Boosting Title Weight

If `title` needs higher weight than `content`, you can construct a scoring query from two FULLTEXT indexes:

This is an optional ranking approach—run it only when the two separate indexes `ft_knowledge_title` and `ft_knowledge_content` from Section 3.1 have been created. If the workload uses only the composite `(title, content)` index, skip this query and use the unified relevance score from Section 11.1.

```sql
SELECT
    document_id,
    title,
    2.0 * MATCH(title) AGAINST (? IN NATURAL LANGUAGE MODE)
      + MATCH(content) AGAINST (? IN NATURAL LANGUAGE MODE) AS relevance
FROM knowledge_document
WHERE MATCH(title) AGAINST (? IN NATURAL LANGUAGE MODE)
   OR MATCH(content) AGAINST (? IN NATURAL LANGUAGE MODE)
ORDER BY relevance DESC, document_id DESC
LIMIT 20;
```

This query requires two separate FULLTEXT indexes for `title` and `content` (added in Section 3.1). The `2.0` weight is only an example; choose weights via relevance evaluation and user feedback rather than treating it as a universal constant.

With a single composite `(title, content)` FULLTEXT index, scores do not automatically provide separate field weighting for `title`. Choose the index structure and scoring approach aligned with ranking requirements.

### 11.3. Structured Filters

FULLTEXT handles the text portion, while filters such as tenant, status, category, and date range should use properly typed columns and indexes:

```sql
SELECT
    document_id,
    title,
    MATCH(title, content) AGAINST (? IN NATURAL LANGUAGE MODE) AS relevance
FROM knowledge_document
WHERE MATCH(title, content) AGAINST (? IN NATURAL LANGUAGE MODE)
  AND language_code = 'vi'
  AND visibility = 'PUBLIC'
  AND created_at >= '2026-01-01'
ORDER BY relevance DESC, document_id DESC
LIMIT 50;
```

FULLTEXT and B-tree indexes are not always combined by the optimizer in an intuitive way. Use `EXPLAIN`/`EXPLAIN ANALYZE`, inspect actual row counts, and benchmark against realistic tenant/status distributions. For multi-tenant systems, always enforce tenant/authorization predicates in SQL; never rely on search indexes or UI filters to protect data.

## 12. Pagination and Stability

`LIMIT offset, count` is easy to use for early pages, but cost can grow at large offsets because the server must locate/read and discard many results. With relevance ranking, order can also shift when the corpus is updated.

Options:

- Cap page depth and support only small offsets.
- Use keyset pagination with a stable key if ordering is primarily by key/date.
- For relevance, store snapshots/result IDs or use a search service supporting point-in-time/`search_after` when stable deep paging is required.
- Add a unique tie-breaker such as `document_id` so results with identical scores have deterministic order.

Simple offset example:

```sql
SELECT document_id, title
FROM knowledge_document
WHERE MATCH(title, content) AGAINST ('mysql index' IN NATURAL LANGUAGE MODE)
ORDER BY MATCH(title, content)
             AGAINST ('mysql index' IN NATURAL LANGUAGE MODE) DESC,
         document_id DESC
LIMIT 20 OFFSET 40;
```

Never promise that page 3 will always contain the exact same rows as an earlier search if documents are inserted/deleted or scores change between requests. API contracts should document pagination semantics and data freshness.

## 13. FULLTEXT and Transactions

With InnoDB, table writes and FULLTEXT index updates follow the table's transaction semantics. Uncommitted transactions should not be treated as visible in search results of other sessions. When the application needs to read newly written data immediately, commit before querying from another transaction/session and test visibility under the active isolation level.

A transaction writing many documents and then committing can batch FULLTEXT index updates at commit time. Long-running transactions hold uncommitted changes longer, increasing undo/lock overhead and delaying visibility for other sessions.

Never use FULLTEXT relevance as a locking mechanism or uniqueness check. If a keyword/code must be unique, enforce a `UNIQUE` constraint on the appropriate column.

## 14. Limitations and Cases Where FULLTEXT Does Not Fit

- Arbitrary mid-token substring matching is not the goal of the built-in FULLTEXT parser.
- Overly short tokens, stopwords, or unsuitable tokenization can cause words to be skipped.
- Typo tolerance, stemming, synonyms, and linguistic semantics are not general capabilities of the built-in parser.
- FULLTEXT indexes carry storage and maintenance costs as data changes.
- Relevance scores depend on the corpus and algorithm; they are not probabilities or scores comparable across arbitrary datasets.
- Combining B-tree filters with FULLTEXT requires checking the execution plan; do not assume all indexes are optimally intersected.
- Search-as-you-type and autocomplete usually require dedicated prefix/suggestion models.
- Arbitrary JSON search is not solved by creating a FULLTEXT index directly on a JSON column; extract searchable content into a clearly managed text column or use a search pipeline.
- When searching across multiple data sources, complex facets, or scaling reads independently, a search service is usually more suitable.

## 15. Inspecting Execution Plans and Operations

Inspect the query:

```sql
EXPLAIN
SELECT document_id, title
FROM knowledge_document
WHERE MATCH(title, content)
      AGAINST ('mysql transaction' IN NATURAL LANGUAGE MODE);
```

On MySQL versions supporting `EXPLAIN ANALYZE`, you can inspect actual timings and row counts; this command executes the query, so run it only with `SELECT` queries in an appropriate environment:

```sql
EXPLAIN ANALYZE
SELECT document_id, title
FROM knowledge_document
WHERE MATCH(title, content)
      AGAINST ('mysql transaction' IN NATURAL LANGUAGE MODE)
LIMIT 20;
```

Monitor:

- Query latency p50/p95/p99 and search request volume.
- Average result count, zero-result queries, and queries with dropped tokens.
- FULLTEXT index size and total table storage footprint.
- CPU, I/O, buffer pool pressure, and write latency during bulk loads.
- Replication lag after imports/rebuilds or large update batches.
- Index rebuild duration and required free disk space.
- Relevance metrics from benchmark query suites and user feedback.

When changing stopwords, token size, parser, or collation, plan FULLTEXT index rebuilds and re-test relevance. Keep configuration consistent across primary, replicas, and deployment environments.

## 16. Sync Architecture with an External Search Engine

If MySQL is the source of truth and the search service is a read model, handle asynchronous updates properly:

1. Business transaction updates the document in MySQL.
2. Within the same transaction, write an outbox event containing document ID and version.
3. Worker/CDC reads the outbox or binlog and fetches the document version to index.
4. Worker upserts/deletes the document in the search engine by ID and version.
5. Track checkpoints, retry transient failures, and route persistent failures to a dead-letter queue.
6. Maintain a mechanism to rebuild the full index from MySQL and reconcile counts/versions.

Never issue HTTP calls directly from database triggers. A database transaction cannot roll back an operation already sent to the search service. An outbox captures sync intent atomically with the transaction and allows workers to retry independently.

The design must accept eventual consistency: a newly committed document may not appear immediately in search results. If business rules require read-your-writes, return newly created data directly from the transaction, wait for index acknowledgment, or supplement with direct ID lookups.

## 17. Security and Query Safety

- Use prepared statements to bind search text, filters, and limits.
- With boolean mode, parse/validate operators against a product-allowed grammar; parameter binding does not prevent users from sending valid yet unwanted boolean operators.
- Always enforce tenant ID, visibility, and authorization filters in server-side SQL.
- Never return sensitive content simply because FULLTEXT matched; apply read permissions alongside search.
- Cap query length, token count, page size, and execution timeout.
- Do not log raw queries verbatim if they may contain sensitive data; mask or hash logs per policy.
- Use an application database account with only `SELECT` privileges on searchable tables; `DDL`/index rebuild privileges belong to DBAs/deployment automation.

## 18. Quick Decision Matrix

| Context | Choice | Rationale and Notes |
| --- | --- | --- |
| Exact order code, email, slug | B-tree/UNIQUE | Deterministic equality, supports constraints |
| Prefix name suggestions | B-tree prefix | Fast, predictable, requires pattern without leading wildcard |
| Mid-string match in a small table | LIKE | Simple; measure full scan and bound data growth |
| Word search in title/body, moderate corpus | InnoDB FULLTEXT | Built-in inverted index and relevance |
| User-supplied required/excluded words | FULLTEXT boolean mode | Rich query syntax; validate grammar |
| Phrase search | FULLTEXT phrase search | Tokenization/stopwords affect semantics |
| Chinese/Japanese/Korean | ngram or dedicated search analyzer | Select token size via test set |
| Vietnamese needing segmentation, accent folding, synonyms | App analyzer/search engine | Built-in FULLTEXT is not a Vietnamese NLP engine |
| Typos, fuzzy, autocomplete, large facets | Dedicated search engine | Needs analyzers/ranking and independent scaling |
| Multi-source, cluster-wide distributed search | Search engine + outbox/CDC | Decouple read model from OLTP, accept eventual consistency |

## 19. Process for Deploying a Search Strategy

1. Collect sample user queries and classify into exact/prefix/substring/term/phrase/fuzzy.
2. Determine language, charset, collation, normalization, stopwords, and token size.
3. Choose storage engine; prefer InnoDB for transactional data.
4. Design text columns and FULLTEXT indexes matching exact searchable column sets.
5. Write sample queries for natural language/boolean/phrase modes and structured filters.
6. Build a benchmark query set with human-labeled relevant results.
7. Measure precision, recall, top-k relevance, and latency on a representative corpus.
8. Use `EXPLAIN`/`EXPLAIN ANALYZE` to check access paths and actual rows.
9. Measure write cost, index size, rebuild time, and replication lag.
10. Test under near-production traffic/corpus; roll out in phases and monitor.
11. If using a search service, implement outbox/CDC, retries, idempotency, rebuilds, and reconciliation.
12. Document search limitations so the product does not promise behaviors unsupported by the engine.

## 20. Measuring Search Quality

Speed alone is not enough to evaluate search. Build a representative query set with labeled relevant documents, then measure:

- **Precision@k:** within the top k results, the fraction that are genuinely relevant.
- **Recall@k:** among known relevant documents, the fraction appearing in the top k results.
- **NDCG@k:** ranking quality when relevance has multiple graded levels.
- **Zero-result rate:** percentage of queries returning no results.
- **Latency:** p50/p95/p99 under expected concurrency.
- **Freshness:** delay from MySQL commit until the document appears in search.

Slice the query set by language, length, accented/unaccented, rare/common words, phrases, typos, and filters. Whenever changing parser, stopwords, or token size, re-run the entire test suite to catch regressions.

## 21. Common Errors

| Error / Symptom | Cause | How to Handle |
| --- | --- | --- |
| FULLTEXT misses short words | Token shorter than min token size | Check token size variables and consider index rebuild |
| Common words do not appear | Stopword list | Check stopword list and relevance requirements |
| `MATCH` reports no matching FULLTEXT index | `MATCH` column list does not match index | Create index on exact column set and match it in `MATCH` |
| `%word%` speed is erratic | FULLTEXT does not search arbitrary substrings | Use `LIKE` for small sets or ngram/search service |
| Poor CJK search | Built-in parser does not segment words properly | Test ngram parser and pick token size using real data |
| Vietnamese results miss expectations | Tokenization, diacritics, normalization, compound words | Normalize/analyze in app or search service |
| Boolean query returns too many/few rows | Operators or stopwords/tokenization | Validate grammar and test each query pattern |
| Relevance shifts after data import | Corpus and token statistics changed | Re-evaluate ranking on benchmark query set |
| `UPDATE`/`INSERT` slows after adding FULLTEXT | Inverted index maintenance overhead | Drop redundant indexes, batch writes, measure write workload |
| External search engine missing new data | Sync pipeline lag/errors | Outbox/CDC checkpoints, retries, dead-letter queue, rebuilds |
| Users see another tenant's documents | Missing authorization filter | Enforce tenant/visibility filters in server-side SQL |

## 22. Practice Exercises

1. Create an InnoDB `knowledge_document` table with title, summary, content, language, and visibility.
2. Create a FULLTEXT index on `(title, content)` and test natural language mode.
3. Test boolean query `+mysql -deprecated` and phrase query `"transaction isolation"`.
4. Compare FULLTEXT against `LIKE '%mysql%'` using `EXPLAIN` and latency on a growing corpus.
5. Create a separate `title` index; compare relevance of `MATCH(title)` vs. `MATCH(title, content)`.
6. Inspect `innodb_ft_min_token_size` and stopwords; pick a short word to verify behavior.
7. In a separate lab, change stopwords/token size, rebuild the index, and compare before/after results.
8. Create a table using `WITH PARSER ngram`; test CJK queries across multiple `ngram_token_size` values in a test environment.
9. Build a 20-query Vietnamese test set covering accented, unaccented, compound words, phrases, and short terms; label relevant results.
10. Add `language_code`, `visibility`, and tenant filters; verify zero cross-tenant data leakage.
11. Run `EXPLAIN ANALYZE` and record actual rows/timings for common queries.
12. Measure write latency and index size before/after adding a second FULLTEXT index.
13. Design an outbox/CDC flow syncing a document to a search engine and simulate worker retries.
14. Write an architecture decision record choosing FULLTEXT, B-tree, `LIKE`, or a search engine for a specific feature.

## 23. Pre-Release Checklist

- [ ] Properly classified requirements as exact, prefix, substring, term, phrase, fuzzy, or autocomplete.
- [ ] FULLTEXT is used only for text content needing token search.
- [ ] Storage engine and charset/collation were chosen deliberately.
- [ ] Column lists in `MATCH` match FULLTEXT indexes.
- [ ] Tested natural language/boolean/phrase modes with real queries.
- [ ] Evaluated stopwords, token size, and parser per language.
- [ ] Considered ngram for languages without space-delimited words.
- [ ] Tenant, visibility, and authorization filters always execute server-side.
- [ ] Clear ranking, tie-breaker, and pagination limits are in place.
- [ ] Checked `EXPLAIN`/`EXPLAIN ANALYZE` and p95/p99 latency.
- [ ] Measured index size, write overhead, rebuild time, and replication lag.
- [ ] Maintained a relevance test set and appropriate precision/recall or NDCG metrics.
- [ ] Established sync/rebuild procedures if using an external search service.
- [ ] Queries bind parameters and boolean grammar is validated.
- [ ] Monitoring, query limits, and runbooks for index errors/lag are ready.

## 24. Completion Criteria

You complete this lesson when you can take a real search requirement, classify the matching type, pick the appropriate mechanism and engine, design FULLTEXT indexes on the right columns, write natural language/boolean/phrase queries, explain the impact of tokenization/stopwords/language, safely combine structured filters, and verify quality with relevance tests and benchmarks. You must also know when MySQL FULLTEXT falls short and how to synchronize MySQL to a dedicated search engine.

## References

- [MySQL 8.4 Reference Manual — Full-Text Search Functions](https://dev.mysql.com/doc/refman/8.4/en/fulltext-search.html)
- [MySQL 8.4 Reference Manual — Natural Language Full-Text Searches](https://dev.mysql.com/doc/refman/8.4/en/fulltext-natural-language.html)
- [MySQL 8.4 Reference Manual — Boolean Full-Text Searches](https://dev.mysql.com/doc/refman/8.4/en/fulltext-boolean.html)
- [MySQL 8.4 Reference Manual — Full-Text Stopwords](https://dev.mysql.com/doc/refman/8.4/en/fulltext-stopwords.html)
- [MySQL 8.4 Reference Manual — ngram Full-Text Parser](https://dev.mysql.com/doc/refman/8.4/en/fulltext-search-ngram.html)
- [MySQL 8.4 Reference Manual — Fine-Tuning MySQL Full-Text Search](https://dev.mysql.com/doc/refman/8.4/en/fulltext-fine-tuning.html)
