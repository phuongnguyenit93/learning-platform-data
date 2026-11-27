# Scoring, Relevance Sorting, and Result Pagination

This lesson belongs to the **Full-Text Search** chapter of the **DATABASE_MYSQL** module. The module aims to master MySQL from table design, data types, keys, and SQL queries to indexes, transactions, concurrency control, execution plan reading, query optimization, privilege management, backups, and relational database operational troubleshooting. Full-text search does more than answer whether a row contains a keyword; `MATCH()` also computes a relevance score to estimate how well content matches the query. Building a correct and stable search page requires understanding how scores are calculated, sorting explicitly by score, handling tied scores, choosing a pagination strategy, and recognizing the impact when the document collection changes.

After this lesson, you will be able to retrieve relevance scores using `MATCH() AGAINST()`, distinguish natural-language and Boolean ranking, explain factors affecting scores, write `ORDER BY` with a unique tie-breaker, understand conditions for automatic relevance sorting and InnoDB Top-N optimization, compare `OFFSET` vs. keyset pagination, recognize why score-based cursors can shift between requests, and store result snapshots when consistent pagination is needed.

## 1. What Is a Relevance Score?

With full-text search, multiple rows may match a query while differing in degree of match. For example, searching `mysql index`:

- Document A mentions both words multiple times and focuses on index design.
- Document B mentions `mysql` only once in the introduction.
- Document C mentions `index` several times without `mysql`.
- Document D contains neither word from the query.

`MATCH() AGAINST()` returns a numeric value representing how closely a row matches the search string. This value is typically aliased as `score`, `relevance`, or `rank`.

Syntax:

~~~sql
MATCH (title, body)
AGAINST ('mysql index' IN NATURAL LANGUAGE MODE)
~~~

`MATCH()` specifies the text columns to search. `AGAINST()` takes the query string and search modifier. If no modifier is specified, MySQL uses natural-language mode.

Example retrieving score:

~~~sql
SELECT
    article_id,
    MATCH (title, body)
        AGAINST ('mysql index' IN NATURAL LANGUAGE MODE) AS score
FROM articles;
~~~

The query above computes a score for every row, including rows with no matching words. A score of 0 means zero similarity as evaluated by full-text search.

### Score Is Not a Probability

Do not interpret score as a probability or percentage:

- A score of 0.8 does not mean the content is 80% accurate.
- A score of 2.4 does not mean 2.4 times more relevant on any universal scale.
- Scores from two different queries are not necessarily directly comparable.
- Scores can change when the set of documents in the collection changes.

Score is a ranking value valid within the scope of the active algorithm, parser, index, and collection.

### Collection and Document

In the full-text context:

- **Document** is the indexed text portion of a single row.
- **Collection** is the set of columns in the FULLTEXT index across the searched rows.

For instance, a FULLTEXT index on `(title, body)` forms a collection from the contents of those two columns. Document length, unique word count, and word frequency across the entire collection can affect relevance.

## 2. Retrieving Scores and Filtering Results with MATCH() AGAINST()

Example articles table:

~~~sql
CREATE TABLE articles (
    article_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    title VARCHAR(250) NOT NULL,
    body TEXT NOT NULL,
    status VARCHAR(20) NOT NULL,
    published_at DATETIME(6) NOT NULL,
    FULLTEXT KEY ft_articles_title_body (title, body),
    KEY idx_articles_status_published (status, published_at)
) ENGINE=InnoDB;
~~~

Find articles related to `mysql index`:

~~~sql
SELECT
    article_id,
    title,
    MATCH (title, body)
        AGAINST ('mysql index' IN NATURAL LANGUAGE MODE) AS score
FROM articles
WHERE MATCH (title, body)
    AGAINST ('mysql index' IN NATURAL LANGUAGE MODE);
~~~

Here `MATCH()` appears twice:

1. In `SELECT` to return the score to the client.
2. In `WHERE` to filter matching rows.

When both `MATCH()` expressions are identical, the MySQL optimizer recognizes this and does not invoke the full-text search engine an extra time merely because the expression is written in two places.

### MATCH() Must Match a FULLTEXT Index

With InnoDB, the column list in `MATCH()` must match the exact column list of a FULLTEXT index.

If the index was created as:

~~~sql
FULLTEXT KEY ft_articles_title_body (title, body)
~~~

then the matching expression is:

~~~sql
MATCH (title, body)
~~~

Do not assume an index on `(title, body)` also serves `MATCH(title)` or `MATCH(body)`. If you need to search `title` alone, create a separate FULLTEXT index on `title`.

As an exception, Boolean mode on MyISAM can search columns without a FULLTEXT index, though this is usually slow; do not apply that exception to InnoDB.

### AGAINST() Requires a Constant String During Query Evaluation

`AGAINST()` accepts a string value that does not vary per row during query evaluation. You cannot use another column of the table as a per-row search string.

In applications, pass the search text via prepared statement parameter binding:

~~~sql
SELECT
    article_id,
    MATCH (title, body) AGAINST (? IN NATURAL LANGUAGE MODE) AS score
FROM articles
WHERE MATCH (title, body) AGAINST (? IN NATURAL LANGUAGE MODE);
~~~

Both placeholders receive the same search text. Parameter binding avoids concatenating user input directly into SQL strings.

## 3. Factors Affecting the Relevance Score

In natural-language mode, the score is a non-negative floating-point value. A score of 0 indicates no similarity. MySQL computes relevance based on factors such as:

- Number of words in the document.
- Number of unique words in the document.
- Total number of words in the collection.
- Number of rows containing a specific word.

Intuitive meaning:

- A word occurring multiple times in a document can raise relevance.
- A word occurring in few documents generally has higher distinguishing power than a word appearing in most documents.
- Document length and word distribution across the collection also affect results.
- Words excluded by stopwords or token length limits do not contribute like normally indexed words.

Do not apply a single formula across all storage engines and search modes. Natural-language ranking and Boolean ranking differ algorithmically, especially between InnoDB and MyISAM.

### InnoDB Boolean Ranking and TF-IDF

For Boolean full-text search on InnoDB, MySQL describes a ranking algorithm based on BM25 and TF-IDF. One formulation for a single-word query uses:

- TF (term frequency): how many times the word appears in the document.
- IDF (inverse document frequency): how rare the word is in the collection.

The documentation describes:

\[
IDF = \log_{10}\left(\frac{N}{n}\right)
\]

Where:

- N is the total number of records in the collection.
- n is the number of records containing the word.

For a document containing the word multiple times, the contribution is described as:

\[
TF \times IDF
\]

and an example ranking formula for a single word in InnoDB Boolean mode is:

\[
rank = TF \times IDF^2
\]

This is a description of InnoDB Boolean ranking in the documentation, not a universal formula for all full-text search. MyISAM computes relevance differently; natural-language mode should also be understood according to its own documentation.

### Why Can Scores Change?

Suppose today the collection has 10,000 articles and the word `replication` appears in 100 articles. After importing many new articles, the document count and word frequency may shift. IDF and the corresponding scores can change.

Scores can also change when:

- Document content is updated.
- Documents are inserted or deleted.
- The FULLTEXT index is rebuilt after changing parser or stopwords.
- Query text or search mode changes.
- Storage engine or full-text search configuration changes.

Therefore, do not store a score cursor from days ago and assume it still represents the same position in an altered collection.

## 4. Natural-Language Mode and Boolean Mode Rank Differently

The two modes are typically used for two different search experiences.

| Criterion | Natural-Language Mode | Boolean Mode |
|---|---|---|
| Query expression style | Natural phrases/words | Includes control operators |
| Goal | Find and rank relevant content | Control required, excluded words, phrases |
| Relevance score | Yes | Can be retrieved via `MATCH() AGAINST()` |
| Auto-sorted descending by score | Yes under certain conditions | No |
| Operators `+`, `-`, `>`, `<`, `~` | Not used as Boolean operators | Yes |
| MyISAM 50% threshold | Can apply per MyISAM ranking | Not applied |
| InnoDB | Supported | Supported |

### Natural-Language Mode

~~~sql
SELECT
    article_id,
    title,
    MATCH (title, body)
        AGAINST ('mysql replication' IN NATURAL LANGUAGE MODE) AS score
FROM articles
WHERE MATCH (title, body)
    AGAINST ('mysql replication' IN NATURAL LANGUAGE MODE)
ORDER BY score DESC, article_id ASC
LIMIT 20;
~~~

This is the common pattern for a search page. MySQL finds relevant rows and sorts by descending score. `article_id` acts as a tie-breaker so ordering is deterministic when multiple rows share the same score.

### Boolean Mode

~~~sql
SELECT
    article_id,
    title,
    MATCH (title, body)
        AGAINST ('+mysql +replication -oracle' IN BOOLEAN MODE) AS score
FROM articles
WHERE MATCH (title, body)
    AGAINST ('+mysql +replication -oracle' IN BOOLEAN MODE)
ORDER BY score DESC, article_id ASC
LIMIT 20;
~~~

In this example:

- `+mysql`: row must contain `mysql`.
- `+replication`: row must contain `replication`.
- `-oracle`: exclude rows containing `oracle`.
- `ORDER BY score DESC`: place better-matching rows first.
- `article_id ASC`: handle tied scores.

Boolean mode does not automatically sort results by relevance. If ranking is needed, SELECT the score and write an explicit `ORDER BY`.

The `>` and `<` operators can increase or decrease a word's contribution to relevance in Boolean mode. `~` makes the contribution negative, whereas `-` excludes rows containing that word from matching results. Do not confuse these two behaviors.

## 5. Conditional Automatic Relevance Sorting

In natural-language search, when `MATCH()` is in `WHERE`, MySQL can automatically return rows in descending score order if all of the following conditions hold simultaneously:

1. No explicit `ORDER BY`.
2. The search uses a full-text index scan rather than a table scan.
3. If there is a JOIN, the table accessed via the full-text index scan must be the first non-constant table in the join order.

Example:

~~~sql
SELECT article_id, title
FROM articles
WHERE MATCH (title, body)
    AGAINST ('mysql replication' IN NATURAL LANGUAGE MODE);
~~~

Under suitable conditions, higher-relevance rows are returned first.

However, do not rely on this implicit behavior for APIs or paginated UIs. When a well-defined order is required, write:

~~~sql
SELECT
    article_id,
    title,
    MATCH (title, body)
        AGAINST ('mysql replication' IN NATURAL LANGUAGE MODE) AS score
FROM articles
WHERE MATCH (title, body)
    AGAINST ('mysql replication' IN NATURAL LANGUAGE MODE)
ORDER BY score DESC, article_id ASC;
~~~

Adding `ORDER BY` makes the application explicitly specify the ordering contract. It also makes the intended result order clear to SQL readers.

### A Tie-Breaker Is Mandatory for Stable Pagination

Scores can collide. For example, two articles may mention a word with similar frequency. If you only write:

~~~sql
ORDER BY score DESC
~~~

the ordering among tied rows is undefined. When execution plans, data, or indexes change, tied rows can swap positions.

Add a unique key:

~~~sql
ORDER BY score DESC, article_id ASC
~~~

The secondary key must be unique across the result set. The primary key is usually a good choice.

Do not use `ROUND(score, 2)` as a sort key unless deliberately bucketing scores. Rounding can turn distinct scores into ties and alter business ordering. You can round for display, while sorting by the raw score.

## 6. Top-N Full-Text Search Optimization

A Top-N query typically looks like:

~~~sql
SELECT
    article_id,
    title,
    MATCH (title, body)
        AGAINST ('mysql index' IN NATURAL LANGUAGE MODE) AS score
FROM articles
WHERE MATCH (title, body)
    AGAINST ('mysql index' IN NATURAL LANGUAGE MODE)
ORDER BY score DESC, article_id ASC
LIMIT 20;
~~~

MySQL includes a specific optimization for certain FULLTEXT queries on a single InnoDB table. Documentation notes the particularly efficient shapes:

- Returning only document IDs, or document IDs along with the search rank.
- Sorting matching rows by descending score and using `LIMIT` to fetch Top-N.
- No `WHERE` clause.
- Only a single `ORDER BY` in descending order.

These are narrow conditions for a specific Top-N optimization. Application queries adding `status` filters, `JOIN`s, or a tie-breaker may fall outside that exact optimized shape. Do not assume every `MATCH() AGAINST() ORDER BY score DESC LIMIT N` query uses the exact same plan.

### Fetch Fewer Columns First

If the first step only needs IDs and scores, avoid carrying long `body` text through the sorting stage:

~~~sql
SELECT
    article_id,
    MATCH (title, body)
        AGAINST ('mysql index' IN NATURAL LANGUAGE MODE) AS score
FROM articles
WHERE MATCH (title, body)
    AGAINST ('mysql index' IN NATURAL LANGUAGE MODE)
ORDER BY score DESC, article_id ASC
LIMIT 20;
~~~

Then, if needed, fetch details for the selected ID list. Splitting into two steps can reduce materialized or transferred data, though you should measure the actual plan and weigh the extra round trip.

### Standard Filters Can Alter the Plan

Example:

~~~sql
SELECT
    article_id,
    title,
    MATCH (title, body)
        AGAINST ('mysql index' IN NATURAL LANGUAGE MODE) AS score
FROM articles
WHERE status = 'PUBLISHED'
  AND MATCH (title, body)
      AGAINST ('mysql index' IN NATURAL LANGUAGE MODE)
ORDER BY score DESC, article_id ASC
LIMIT 20;
~~~

The `status` condition can alter the execution plan. The FULLTEXT index and a B-tree index on `status` serve different purposes; the optimizer must weigh how to combine them.

Do not assume the `status` index is always used before the full-text index or vice versa. Inspect `EXPLAIN`, actual row counts, and the selectivity of each condition.

## 7. OFFSET Pagination for Search Results

A familiar pagination pattern:

~~~sql
SELECT
    article_id,
    title,
    MATCH (title, body)
        AGAINST ('mysql index' IN NATURAL LANGUAGE MODE) AS score
FROM articles
WHERE MATCH (title, body)
    AGAINST ('mysql index' IN NATURAL LANGUAGE MODE)
ORDER BY score DESC, article_id ASC
LIMIT 20 OFFSET 40;
~~~

The query skips the first 40 rows and returns the next 20 rows.

Advantages:

- Simple SQL.
- Suits UIs with page numbers.
- Easy to jump to an arbitrary page.
- Easy to align with `page`/`pageSize` APIs.

Disadvantages:

- The larger the `OFFSET`, the more rows the server must traverse before the desired slice.
- Full-text search still must find and rank matching rows.
- Inserts or deletes between requests can shift row positions.
- Users can see duplicate or skipped articles when paging.

Examples:

~~~sql
LIMIT 20 OFFSET 0;
LIMIT 20 OFFSET 20;
LIMIT 20 OFFSET 40;
~~~

The deeper the page, the higher the cost of skipping rows. For very large search result sets, consider keyset pagination or snapshots.

### LIMIT Does Not Turn Score into a Seekable Index

Score is computed from `MATCH() AGAINST()`, not a stored B-tree column. MySQL cannot use a standard B-tree index to jump directly to score 0.75 the way it can when paginating over an indexed column.

Therefore, score-based keyset pagination can avoid counting and discarding `OFFSET` rows, but it does not mean MySQL avoids full-text matching and ranking work altogether. Benchmark on a real dataset.

## 8. Keyset Pagination by Score and Secondary Key

Keyset pagination uses the key values of the last row on the current page as a cursor.

Suppose the sort order is:

~~~sql
ORDER BY score DESC, article_id ASC
~~~

The last row on the previous page had:

- `score = 0.7421`
- `article_id = 500`

The next page needs rows where:

- `score` is less than `0.7421`, OR
- `score` equals `0.7421` and `article_id` is greater than `500`.

Condition:

~~~sql
score < 0.7421
OR (score = 0.7421 AND article_id > 500)
~~~

Example using a derived table so we can filter by the `score` alias:

~~~sql
SELECT
    article_id,
    title,
    score
FROM (
    SELECT
        article_id,
        title,
        MATCH (title, body)
            AGAINST ('mysql index' IN NATURAL LANGUAGE MODE) AS score
    FROM articles
    WHERE MATCH (title, body)
        AGAINST ('mysql index' IN NATURAL LANGUAGE MODE)
) AS ranked
WHERE score < 0.7421
   OR (score = 0.7421 AND article_id > 500)
ORDER BY score DESC, article_id ASC
LIMIT 20;
~~~

In the application, pass `last_score` and `last_article_id` via parameter binding:

~~~sql
WHERE score < ?
   OR (score = ? AND article_id > ?)
ORDER BY score DESC, article_id ASC
LIMIT ?;
~~~

Both `score` parameters must use the exact raw score value of the last row on the page. Do not round the score before saving the cursor.

### Conditions for a Score Cursor to Work Correctly

- Identical query text as the previous page.
- Identical search mode.
- Unchanged `MATCH` column list and FULLTEXT index.
- Identical filters and data access permissions.
- Exact score from the previous computation, unrounded.
- Document set and indexed content do not change in ways affecting ranking during the pagination session.

If the corpus changes, scores can shift. A new document changing IDF can shift previously viewed rows. An updated article can rise or fall in score. Keyset pagination does not freeze the order of the entire result set.

### Keyset by Score Is Not Equivalent to Keyset by B-tree

On a transactional table, a `(created_at, id)` cursor can leverage a composite B-tree index to seek directly to the next position. With full-text scores, score is a computed value from the search engine; it is not a key part in a B-tree index.

Score-based keyset pagination helps define clean pagination logic and avoid large `OFFSET`s, yet does not guarantee reducing the number of documents evaluated or sorted. Inspect the execution plan and measure empirically.

## 9. Search Result Snapshots When Stable Ordering Is Required

If product requirements state:

- A user opens page 1 today.
- A few minutes later they navigate to page 2.
- Source data may change in the meantime.
- Every page must belong to a single frozen search ordering.

then you should not recompute scores from a changing corpus on every request. You can store a result snapshot.

### Search Session Table

~~~sql
CREATE TABLE search_session (
    search_id BINARY(16) NOT NULL PRIMARY KEY,
    query_text VARCHAR(500) NOT NULL,
    search_mode VARCHAR(30) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    expires_at DATETIME(6) NOT NULL
) ENGINE=InnoDB;
~~~

### Ranked Results Table

~~~sql
CREATE TABLE search_result (
    search_id BINARY(16) NOT NULL,
    position_no BIGINT UNSIGNED NOT NULL,
    article_id BIGINT UNSIGNED NOT NULL,
    relevance_score DOUBLE NOT NULL,
    PRIMARY KEY (search_id, position_no),
    UNIQUE KEY uq_search_article (search_id, article_id),
    KEY idx_search_article (article_id),
    CONSTRAINT fk_search_result_session
        FOREIGN KEY (search_id)
        REFERENCES search_session(search_id)
) ENGINE=InnoDB;
~~~

When a user initiates a search:

1. Generate a unique `search_id`.
2. Store query text, mode, filters, and creation timestamp.
3. Compute relevance for the result set.
4. Assign `position_no` using `ROW_NUMBER()` ordered by `score DESC, article_id ASC`.
5. Insert IDs and scores into `search_result`.
6. Paginate by `position_no`.

Example creating a Top-500 snapshot:

~~~sql
INSERT INTO search_result (
    search_id,
    position_no,
    article_id,
    relevance_score
)
SELECT
    UUID_TO_BIN('11111111-1111-1111-1111-111111111111'),
    ROW_NUMBER() OVER (
        ORDER BY score DESC, article_id ASC
    ) AS position_no,
    article_id,
    score
FROM (
    SELECT
        article_id,
        MATCH (title, body)
            AGAINST ('mysql index' IN NATURAL LANGUAGE MODE) AS score
    FROM articles
    WHERE MATCH (title, body)
        AGAINST ('mysql index' IN NATURAL LANGUAGE MODE)
    ORDER BY score DESC, article_id ASC
    LIMIT 500
) AS ranked;
~~~

In production, `search_id` is generated in the application layer and passed via prepared statements. The UUID above is for illustration only.

### Fetching Pages from the Snapshot

First page:

~~~sql
SELECT
    sr.position_no,
    sr.article_id,
    sr.relevance_score,
    a.title
FROM search_result AS sr
JOIN articles AS a
    ON a.article_id = sr.article_id
WHERE sr.search_id = UUID_TO_BIN('11111111-1111-1111-1111-111111111111')
ORDER BY sr.position_no
LIMIT 20;
~~~

Next page:

~~~sql
SELECT
    sr.position_no,
    sr.article_id,
    sr.relevance_score,
    a.title
FROM search_result AS sr
JOIN articles AS a
    ON a.article_id = sr.article_id
WHERE sr.search_id = UUID_TO_BIN('11111111-1111-1111-1111-111111111111')
  AND sr.position_no > 20
ORDER BY sr.position_no
LIMIT 20;
~~~

At this point, ordering and scores are preserved as of snapshot creation time. Displayed article data may still be updated or deleted; if displayed content must also stay consistent, snapshot the display fields as well or apply document versioning.

### Cost of Snapshots

Snapshots increase:

- Storage footprint.
- Initial search result creation cost.
- Cleanup overhead for expired data.
- Number of rows written when starting a session.

There is no need to save thousands of results if the UI only allows viewing the first 10 pages. Cap Top-K per product rules and configure a TTL to purge old snapshots.

## 10. Paginating by Document Keys Instead of Score

Some systems choose a simpler ordering:

~~~sql
ORDER BY published_at DESC, article_id DESC
~~~

Here the cursor is `(published_at, article_id)` and can be supported by a composite B-tree index.

Example:

~~~sql
CREATE INDEX idx_articles_published
ON articles (status, published_at DESC, article_id DESC);
~~~

Query:

~~~sql
SELECT
    article_id,
    title
FROM articles
WHERE status = 'PUBLISHED'
  AND (
      published_at < '2026-11-18 10:00:00'
      OR (
          published_at = '2026-11-18 10:00:00'
          AND article_id < 500
      )
  )
ORDER BY published_at DESC, article_id DESC
LIMIT 20;
~~~

This is no longer pure relevance ranking. It is a product choice: prioritizing newest articles among those containing the keywords.

You can combine relevance and freshness into a custom score, provided you define the formula, normalize scales, and test result quality. Never add scores with different scales directly without understanding their distributions.

## 11. Combining Scores from title and body

If you want to give `title` higher weight, you can create two separate FULLTEXT indexes:

~~~sql
CREATE TABLE articles_weighted (
    article_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    title VARCHAR(250) NOT NULL,
    body TEXT NOT NULL,
    FULLTEXT KEY ft_title (title),
    FULLTEXT KEY ft_body (body)
) ENGINE=InnoDB;
~~~

Then construct a custom score:

~~~sql
SELECT
    article_id,
    title,
    3.0 * MATCH (title)
        AGAINST ('mysql index' IN NATURAL LANGUAGE MODE)
    +
    1.0 * MATCH (body)
        AGAINST ('mysql index' IN NATURAL LANGUAGE MODE) AS score
FROM articles_weighted
WHERE MATCH (title)
        AGAINST ('mysql index' IN NATURAL LANGUAGE MODE)
   OR MATCH (body)
        AGAINST ('mysql index' IN NATURAL LANGUAGE MODE)
ORDER BY score DESC, article_id ASC
LIMIT 20;
~~~

This is a heuristic example. Weights `3.0` and `1.0` are not defaults or universal recommendations. Evaluate relevance against your product's query set and expected results.

Each `MATCH()` must have a corresponding FULLTEXT index matching its exact column list. If you prefer a single composite `(title, body)` FULLTEXT index, use `MATCH(title, body)` and accept how MySQL computes relevance over that combined collection.

Do not add scores from two separate collections without checking their scales and score distributions. Results can become heavily skewed toward one field.

## 12. Query Expansion Affects Result Sets and Ordering

MySQL supports query expansion:

~~~sql
SELECT
    article_id,
    title,
    MATCH (title, body)
        AGAINST (
            'database'
            WITH QUERY EXPANSION
        ) AS score
FROM articles
WHERE MATCH (title, body)
    AGAINST (
        'database'
        WITH QUERY EXPANSION
    )
ORDER BY score DESC, article_id ASC
LIMIT 20;
~~~

Query expansion executes the search twice:

1. Finds documents matching the original query.
2. Selects several high-relevance documents from the first pass.
3. Appends words from those documents to the query.
4. Executes a second search pass with the expanded query.

This can uncover additional topically related documents even if they lack the original keyword. However, it also alters both the result set and score ordering.

Do not enable query expansion by default for all queries. It can make results less direct, especially for short queries or ambiguous keywords. Test with real data and search requirements.

## 13. Parsers, Stopwords, and Tokens Affect Scores

Scores are computed strictly from tokens that the full-text parser places into the index.

Factors to check:

- The default parser splits words according to language rules.
- Stopwords may be excluded from the index and queries.
- Words that are too short or too long may be omitted per token size settings.
- Charset/collation affects case and character comparison.
- For languages without space-separated word boundaries such as Chinese or Japanese, the default parser is insufficient; MySQL provides the ngram parser and MeCab plugin for appropriate cases.

With InnoDB, `innodb_ft_min_token_size` and `innodb_ft_max_token_size` control token length bounds for the built-in parser. With MyISAM, the corresponding variables are `ft_min_word_len` and `ft_max_word_len`. The ngram parser uses `ngram_token_size`.

Changing token size settings usually requires restarting the server and rebuilding the FULLTEXT index to take effect. Never alter production settings just to make one short word appear in results without evaluating index cost and collection-wide impact.

### Columns in a Single FULLTEXT Index Must Share Charset/Collation

Columns combined in the same FULLTEXT index must share the same character set and collation. If case-insensitive or accent-sensitive matching is needed, choose the collation deliberately and test queries.

Do not use `%` as a `LIKE` wildcard inside full-text search. Full-text Boolean mode has its own `*` truncation operator with different semantics.

## 14. New Data and When FULLTEXT Indexes Update

With InnoDB, DML affecting FULLTEXT-indexed columns is processed at `COMMIT`. For instance, `INSERT`s are tokenized and added to full-text structures when the transaction commits.

Consequently, full-text search only returns committed data. A newly `INSERT`ed row whose transaction has not yet committed is not treated as an indexed full-text result.

Why this matters to applications:

- Do not expect to find uncommitted content within a transaction.
- After `COMMIT`, content enters the full-text index per InnoDB mechanics.
- When testing, commit data before running search queries from another session.
- Under heavy write workloads, measure the impact of FULLTEXT indexes on commit latency and index size.

## 15. EXPLAIN and Performance Notes

Use `EXPLAIN` to inspect the execution plan:

~~~sql
EXPLAIN
SELECT
    article_id,
    MATCH (title, body)
        AGAINST ('mysql index' IN NATURAL LANGUAGE MODE) AS score
FROM articles
WHERE MATCH (title, body)
    AGAINST ('mysql index' IN NATURAL LANGUAGE MODE)
ORDER BY score DESC, article_id ASC
LIMIT 20;
~~~

Fields to inspect:

| Field | What to Check |
|---|---|
| possible_keys | FULLTEXT indexes eligible for use |
| key | Index chosen by the optimizer |
| type/access type | How the table is accessed |
| rows | Estimated row count |
| filtered | Percentage of rows passing remaining conditions |
| Extra | Extra steps and optimizer notes |

`EXPLAIN` on a full-text query can be slower than on an ordinary query because MySQL evaluates the full-text expression during optimization to build the plan. In some cases, `Extra` may display `Select tables optimized away` because matching already occurred inside the optimizer and no table access is needed during subsequent execution.

Do not compare the execution time of `EXPLAIN` on a full-text query with a plain `SELECT` and conclude the query will have that same runtime latency.

### Measuring with Real Data

When evaluating search queries, record:

- Query text and search mode.
- Number of matching rows.
- Time to fetch Top-10, Top-20, and deep pages.
- Number of columns returned.
- Selectivity of status/category filters.
- Collection size.
- Frequency of `INSERT`/`UPDATE`/`DELETE`.
- Rate of empty-result or overly common queries.

If you need actual iterator timings, use `EXPLAIN ANALYZE` on appropriate `SELECT` queries. Note that `EXPLAIN ANALYZE` executes the query; use it only with safe queries and environments.

## 16. Full-Text Search Limitations Related to Ranking

Several limitations directly affect how queries and pagination are written:

- FULLTEXT is supported only by InnoDB and MyISAM.
- FULLTEXT search is not supported on partitioned tables.
- FULLTEXT indexes can only be created on `CHAR`, `VARCHAR`, or `TEXT`.
- In InnoDB, the `MATCH()` column list must match the exact column list of a FULLTEXT index.
- `AGAINST()` requires a constant string during query evaluation.
- Columns within a single FULLTEXT index must share the same character set and collation.
- `%` is not a full-text search wildcard.
- Boolean mode does not automatically sort by score.
- Natural-language score is floating-point; do not use a rounded score as a cursor.
- Score depends on the collection; data changes can shift rankings.

Account for these limits in schema and search API design, not merely in the frontend UI.

## 17. Practice Lab: Ranking and Paginating Articles

This lab creates a small dataset with overlapping keywords to observe scores, tie-breakers, and pagination. Do not hardcode expected score values because scores depend on the entire collection and full-text configuration.

### Step 1: Create Database and Table

~~~sql
CREATE DATABASE IF NOT EXISTS mysql_fulltext_ranking_lab;
USE mysql_fulltext_ranking_lab;

CREATE TABLE articles (
    article_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    title VARCHAR(250) NOT NULL,
    body TEXT NOT NULL,
    status VARCHAR(20) NOT NULL,
    published_at DATETIME(6) NOT NULL,
    FULLTEXT KEY ft_articles_title_body (title, body),
    KEY idx_articles_status_published (status, published_at)
) ENGINE=InnoDB;
~~~

### Step 2: Load Data

~~~sql
INSERT INTO articles (
    article_id,
    title,
    body,
    status,
    published_at
)
VALUES
    (1, 'MySQL index basics',
     'Learn how MySQL indexes help query execution and database performance.',
     'PUBLISHED', '2026-11-18 08:00:00'),
    (2, 'Full-text search in MySQL',
     'MySQL full-text search uses MATCH AGAINST and a FULLTEXT index.',
     'PUBLISHED', '2026-11-18 09:00:00'),
    (3, 'MySQL query optimization',
     'Query optimization uses indexes, statistics, and execution plans.',
     'PUBLISHED', '2026-11-18 10:00:00'),
    (4, 'Database indexing guide',
     'An index can reduce the amount of data read by a query.',
     'DRAFT', '2026-11-18 11:00:00'),
    (5, 'MySQL full-text ranking',
     'Relevance ranking sorts full-text search results by score.',
     'PUBLISHED', '2026-11-18 12:00:00'),
    (6, 'Search relevance and pagination',
     'Stable pagination needs deterministic ordering and a unique tie breaker.',
     'PUBLISHED', '2026-11-18 13:00:00'),
    (7, 'MySQL storage engines',
     'InnoDB supports FULLTEXT indexes and transactional data changes.',
     'PUBLISHED', '2026-11-18 14:00:00'),
    (8, 'Index maintenance',
     'Index maintenance and query plans help diagnose slow database workloads.',
     'PUBLISHED', '2026-11-18 15:00:00'),
    (9, 'MySQL search tutorial',
     'This article explains MySQL full-text search, relevance, and search ranking.',
     'PUBLISHED', '2026-11-18 16:00:00'),
    (10, 'Pagination patterns',
     'OFFSET and keyset pagination are useful for browsing search results.',
     'PUBLISHED', '2026-11-18 17:00:00');
~~~

### Step 3: Inspect Scores Without Filtering

~~~sql
SELECT
    article_id,
    title,
    MATCH (title, body)
        AGAINST ('mysql index' IN NATURAL LANGUAGE MODE) AS score
FROM articles
ORDER BY article_id;
~~~

Observations:

- Rows with no matching words can have a score of 0.
- Rows containing query words have positive scores.
- Scores can differ across rows.
- Do not assume scores lie between 0 and 1.

### Step 4: Search and Deterministic Sorting

~~~sql
SELECT
    article_id,
    title,
    MATCH (title, body)
        AGAINST ('mysql index' IN NATURAL LANGUAGE MODE) AS score
FROM articles
WHERE MATCH (title, body)
    AGAINST ('mysql index' IN NATURAL LANGUAGE MODE)
ORDER BY score DESC, article_id ASC
LIMIT 5;
~~~

Check that scores descend. When two rows tie on score, `article_id ASC` determines the order.

### Step 5: Compare Boolean Mode

~~~sql
SELECT
    article_id,
    title,
    MATCH (title, body)
        AGAINST ('+mysql +index -oracle' IN BOOLEAN MODE) AS score
FROM articles
WHERE MATCH (title, body)
    AGAINST ('+mysql +index -oracle' IN BOOLEAN MODE)
ORDER BY score DESC, article_id ASC;
~~~

Compare the row set with natural-language mode. Boolean mode does not auto-sort by relevance; `ORDER BY` in the example is explicit.

### Step 6: Filter by Status

~~~sql
SELECT
    article_id,
    title,
    MATCH (title, body)
        AGAINST ('mysql search' IN NATURAL LANGUAGE MODE) AS score
FROM articles
WHERE status = 'PUBLISHED'
  AND MATCH (title, body)
      AGAINST ('mysql search' IN NATURAL LANGUAGE MODE)
ORDER BY score DESC, article_id ASC
LIMIT 5;
~~~

Verify that `DRAFT` articles do not appear. Inspect `EXPLAIN` to see how the `status` filter affects the plan.

### Step 7: OFFSET Pagination

First page:

~~~sql
SELECT
    article_id,
    title,
    MATCH (title, body)
        AGAINST ('mysql search' IN NATURAL LANGUAGE MODE) AS score
FROM articles
WHERE MATCH (title, body)
    AGAINST ('mysql search' IN NATURAL LANGUAGE MODE)
ORDER BY score DESC, article_id ASC
LIMIT 3 OFFSET 0;
~~~

Second page:

~~~sql
SELECT
    article_id,
    title,
    MATCH (title, body)
        AGAINST ('mysql search' IN NATURAL LANGUAGE MODE) AS score
FROM articles
WHERE MATCH (title, body)
    AGAINST ('mysql search' IN NATURAL LANGUAGE MODE)
ORDER BY score DESC, article_id ASC
LIMIT 3 OFFSET 3;
~~~

Compare both ID sets and confirm no duplicates occur while the collection is unchanged.

### Step 8: Keyset Pagination by Score

Take the `score` and `article_id` of the last row on the first page. Replace the two placeholder values below with your actual results:

~~~sql
SELECT
    article_id,
    title,
    score
FROM (
    SELECT
        article_id,
        title,
        MATCH (title, body)
            AGAINST ('mysql search' IN NATURAL LANGUAGE MODE) AS score
    FROM articles
    WHERE MATCH (title, body)
        AGAINST ('mysql search' IN NATURAL LANGUAGE MODE)
) AS ranked
WHERE score < 0.5000
   OR (score = 0.5000 AND article_id > 3)
ORDER BY score DESC, article_id ASC
LIMIT 3;
~~~

Replace `0.5000` and `3` with the exact raw score and ID of the last row on the previous page. Do not use a rounded score from the UI.

Compare results against `OFFSET` while data is unchanged. Then insert a new article containing multiple keywords and re-run both queries. Observe that ordering can shift because the collection and relevance scores changed.

### Step 9: Inspect Execution Plan

~~~sql
EXPLAIN
SELECT
    article_id,
    MATCH (title, body)
        AGAINST ('mysql search' IN NATURAL LANGUAGE MODE) AS score
FROM articles
WHERE MATCH (title, body)
    AGAINST ('mysql search' IN NATURAL LANGUAGE MODE)
ORDER BY score DESC, article_id ASC
LIMIT 3;
~~~

Check access type, `key`, `rows`, `Extra`, and `EXPLAIN` timing. Small tables may not clearly show performance differences; the goal is to recognize `FULLTEXT` access and sorting.

### Step 10: Create a Top-N Snapshot

~~~sql
CREATE TABLE search_result_snapshot (
    search_id BINARY(16) NOT NULL,
    position_no BIGINT UNSIGNED NOT NULL,
    article_id BIGINT UNSIGNED NOT NULL,
    relevance_score DOUBLE NOT NULL,
    PRIMARY KEY (search_id, position_no),
    UNIQUE KEY uq_search_article (search_id, article_id)
) ENGINE=InnoDB;
~~~

Store ranked results:

~~~sql
INSERT INTO search_result_snapshot (
    search_id,
    position_no,
    article_id,
    relevance_score
)
SELECT
    UUID_TO_BIN('22222222-2222-2222-2222-222222222222'),
    ROW_NUMBER() OVER (
        ORDER BY score DESC, article_id ASC
    ),
    article_id,
    score
FROM (
    SELECT
        article_id,
        MATCH (title, body)
            AGAINST ('mysql search' IN NATURAL LANGUAGE MODE) AS score
    FROM articles
    WHERE MATCH (title, body)
        AGAINST ('mysql search' IN NATURAL LANGUAGE MODE)
) AS ranked;
~~~

Read the first page from the snapshot:

~~~sql
SELECT
    position_no,
    article_id,
    relevance_score
FROM search_result_snapshot
WHERE search_id = UUID_TO_BIN('22222222-2222-2222-2222-222222222222')
ORDER BY position_no
LIMIT 3;
~~~

Read the next page:

~~~sql
SELECT
    position_no,
    article_id,
    relevance_score
FROM search_result_snapshot
WHERE search_id = UUID_TO_BIN('22222222-2222-2222-2222-222222222222')
  AND position_no > 3
ORDER BY position_no
LIMIT 3;
~~~

After creating the snapshot, insert a new article and re-read the snapshot. Snapshot IDs and order remain unchanged because scores were persisted at snapshot creation time.

### Step 11: Clean Up

~~~sql
DROP DATABASE mysql_fulltext_ranking_lab;
~~~

Run `DROP DATABASE` only on the lab database you just created.

## 18. Common Errors and How to Handle Them

| Symptom | Cause | How to Handle |
|---|---|---|
| Missing `score` column | `MATCH()` is only in `WHERE` | Add `MATCH() AGAINST()` to the `SELECT` list |
| Score is 0 | No indexed token matched, or token dropped by stopword/too short | Check parser, stopwords, token size, and data |
| Results auto-sort but unstably | Relying on implicit relevance order or tied scores | Write `ORDER BY score DESC, primary_key` |
| Boolean mode not sorted by score | Boolean mode does not auto-sort by relevance | `SELECT` score and write explicit `ORDER BY` |
| `MATCH()` reports no matching FULLTEXT index | `MATCH` column list does not match index | Create index on exact columns or fix `MATCH` list |
| Cannot pass another table column to `AGAINST` | `AGAINST` requires a constant string during evaluation | Use parameter binding with the search text |
| Deep pages are slow | Large `OFFSET` and full-text result set processing | Use keyset where appropriate or store a snapshot |
| Keyset duplicates/skips when scores tie | Cursor contains only `score` | Add a unique key to `ORDER BY` and cursor |
| Keyset results shift between requests | Corpus changed, altering scores and positions | Store a result snapshot for the search session |
| Keyset is not much faster | Score is a dynamic expression with no B-tree index to seek | Inspect `EXPLAIN`/latency; do not expect keyset to skip full-text matching |
| Scores change after adding articles | IDF and collection statistics changed | Accept dynamic ranking or snapshot results |
| `title`/`body` score is skewed | Summing two scores from different collections with arbitrary weights | Evaluate relevance and tune weights using a query set |
| Full-text `EXPLAIN` is slow | Optimizer evaluates the full-text expression during planning | Understand this behavior and benchmark the actual query |
| Newly `INSERT`ed data not found | InnoDB updates FULLTEXT indexes on `COMMIT` | Commit the transaction before searching from another session |
| Very short words not found | Token size or stopwords exclude word from index | Check config, parser, and rebuild index after changes |
| Query with `%` does not behave like `LIKE` | `%` is not a full-text wildcard | Use Boolean truncation `*` if appropriate |
| Full-text search does not work on partitioned table | MySQL does not support FULLTEXT search on partitioned tables | Re-evaluate schema or search architecture |

## 19. Search API and Pagination Design Checklist

- [ ] Selected natural-language or Boolean mode per requirements.
- [ ] Identified the exact `MATCH()` column list and corresponding FULLTEXT index.
- [ ] `AGAINST()` receives search text via parameter binding.
- [ ] Retrieved `score` in `SELECT` if the API displays or paginates by score.
- [ ] Do not treat score as a probability or percentage.
- [ ] Do not compare scores across different queries on a common scale.
- [ ] Wrote explicit `ORDER BY score DESC`.
- [ ] Added primary key/unique key as a tie-breaker.
- [ ] Do not `ROUND` score before sorting or building a cursor.
- [ ] Verified conditions for natural-language automatic relevance sorting.
- [ ] Understood that Boolean mode does not auto-sort by relevance.
- [ ] Checked specific conditions for Top-N FULLTEXT optimization.
- [ ] Measured `OFFSET` on deep pages.
- [ ] If using score-based keyset pagination, cursor holds raw score and secondary key.
- [ ] Understood that scores can shift when the collection changes.
- [ ] Considered result snapshots when stable ordering across requests is required.
- [ ] Configured TTL and cleanup job for snapshots.
- [ ] Evaluated parser, stopwords, token size, charset, and collation.
- [ ] Measured FULLTEXT index impact on `INSERT`/`UPDATE`/`DELETE` and `COMMIT`.
- [ ] Checked `EXPLAIN` on near-production data.
- [ ] Tested empty queries, overly common words, tied scores, and zero-result cases.

## 20. Principles to Remember

1. `MATCH() AGAINST()` returns a relevance score for documents in the indexed collection.
2. Natural-language scores are non-negative floating-point numbers; a score of 0 means no similarity.
3. Score is not a probability and has no fixed scale across queries.
4. Natural-language ranking depends on document content and collection statistics.
5. InnoDB Boolean ranking is based on BM25/TF-IDF; do not apply that formula universally across all engines/modes.
6. Natural-language mode only auto-sorts by score under specific conditions.
7. Boolean mode does not auto-sort by relevance; write an explicit `ORDER BY`.
8. Always append a unique key at the end of `ORDER BY` to break ties.
9. Do not `ROUND` scores before sorting or constructing cursors.
10. FULLTEXT Top-N optimization applies only to narrow query shapes.
11. `OFFSET` is simple, but deep pages can be costly and shift as data changes.
12. Score-based keyset defines a clean cursor, yet does not provide a B-tree seek on dynamic scores.
13. Scores can change when documents or the collection change.
14. Result snapshots fit when stable pagination across multiple requests is required.
15. Query expansion can broaden the result set and alter ranking.
16. Parser, stopwords, token size, charset, and collation govern which words enter the index.
17. InnoDB updates FULLTEXT indexes at `COMMIT`; full-text search only returns committed data.

## Official References

Syntax and behavior in this lesson are aligned with the **MySQL 9.7 Reference Manual**:

1. [Natural Language Full-Text Searches](https://dev.mysql.com/doc/refman/9.7/en/fulltext-natural-language.html): `MATCH() AGAINST()`, relevance scores, auto-sorting conditions, and factors affecting scores.
2. [Boolean Full-Text Searches](https://dev.mysql.com/doc/refman/9.7/en/fulltext-boolean.html): Boolean operators, sorting behavior, InnoDB TF-IDF/BM25, and relevance ranking.
3. [Full-Text Search Functions](https://dev.mysql.com/doc/refman/9.7/en/fulltext-search.html): `MATCH`/`AGAINST` syntax and search modifiers.
4. [Full-Text Restrictions](https://dev.mysql.com/doc/refman/9.7/en/fulltext-restrictions.html): engine limits, partitioning, charset/collation, `MATCH` column lists, and `COMMIT`-time index updates.
5. [Column Indexes — FULLTEXT Indexes](https://dev.mysql.com/doc/refman/9.7/en/column-indexes.html): conditions for FULLTEXT Top-N optimization, `LIMIT`, and `EXPLAIN`.
6. [Full-Text Searches with Query Expansion](https://dev.mysql.com/doc/refman/9.7/en/fulltext-query-expansion.html): query expansion mechanism and effect on result sets.
7. [Fine-Tuning MySQL Full-Text Search](https://dev.mysql.com/doc/refman/9.7/en/fulltext-fine-tuning.html): token size, stopwords, and rebuilding FULLTEXT indexes.
