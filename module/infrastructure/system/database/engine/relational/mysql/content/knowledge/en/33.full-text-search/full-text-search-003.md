# MATCH AGAINST in Natural Language Mode

Full-text search in MySQL helps find words or phrases that a text parser has split into tokens across text columns. In natural language mode, the search query is interpreted as natural language: MySQL parses the words, finds documents containing matching words, and computes a relevance score to rank results. The central syntax is MATCH(...) AGAINST(...).

Within the DATABASE_MYSQL module, this lesson focuses on creating a FULLTEXT index, writing MATCH AGAINST in natural language mode, interpreting relevance scores, understanding tokenization and stopwords, and key differences between InnoDB and MyISAM. Natural language mode is suitable for keyword-based content search; it is not substring matching or exact ordered phrase matching.

## 1. How Does FULLTEXT Search Work?

A FULLTEXT index stores a lookup structure based on tokens extracted from text content. When running MATCH(...) AGAINST(...), MySQL parses the search string, looks up tokens in the FULLTEXT index, and computes the degree of relevance between documents and the query.

A general workflow:

1. Create a FULLTEXT index on one or more text columns.
2. MySQL parses column content into tokens and builds the index.
3. The application sends a search string to AGAINST.
4. MySQL parses the query string according to the parser and full-text configuration.
5. MATCH finds matching documents and returns relevance scores.
6. The application filters and sorts results by score or additional criteria.

A FULLTEXT index differs from a regular B-tree index. A B-tree is suited for value comparisons, ranges, and ordering; a FULLTEXT index serves token search in text.

## 2. Creating the Table and FULLTEXT Index

MySQL FULLTEXT indexes apply to CHAR, VARCHAR, or TEXT columns. Example articles table:

~~~sql
CREATE TABLE articles (
    article_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    title VARCHAR(255) NOT NULL,
    body TEXT NOT NULL,
    published_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    status VARCHAR(20) NOT NULL DEFAULT 'PUBLISHED',
    PRIMARY KEY (article_id),
    FULLTEXT KEY ft_articles_title_body (title, body),
    KEY idx_articles_status_published (status, published_at)
) ENGINE=InnoDB;
~~~

The index `ft_articles_title_body` is a composite FULLTEXT index on `title` and `body`. The `status`/`published_at` index is a standard B-tree index to support filtering and sorting by status/timestamp if the optimizer finds it beneficial.

You can add a FULLTEXT index after the table is created:

~~~sql
ALTER TABLE articles
    ADD FULLTEXT INDEX ft_articles_title_body (title, body);
~~~

Do not recreate the index if the table already has an index with the same name. When deploying migrations, inspect the current schema and use only one of the two ways to create the index.

## 3. Sample Data

Insert some articles:

~~~sql
INSERT INTO articles (title, body, status)
VALUES
(
    'MySQL transaction basics',
    'A transaction groups database changes. Commit saves changes and rollback cancels uncommitted work.',
    'PUBLISHED'
),
(
    'Understanding database indexes',
    'An index helps MySQL locate rows efficiently. A fulltext index supports searching words in text documents.',
    'PUBLISHED'
),
(
    'Transaction isolation in InnoDB',
    'InnoDB provides transaction isolation levels. Consistent reads and locking reads have different behavior.',
    'PUBLISHED'
),
(
    'Text search and relevance',
    'Fulltext search analyzes words and calculates relevance scores for matching documents.',
    'DRAFT'
);
~~~

Verify the data:

~~~sql
SELECT article_id, title, status
FROM articles
ORDER BY article_id;
~~~

Subsequent examples use this table. Actual results also depend on the parser, stopword list, minimum token size, collation, and MySQL version.

## 4. MATCH AGAINST Syntax in Natural Language Mode

Syntax:

~~~sql
MATCH (col_name [, col_name] ...)
AGAINST (expr [search_modifier])
~~~

With natural language mode:

~~~sql
MATCH (title, body)
AGAINST ('transaction isolation' IN NATURAL LANGUAGE MODE)
~~~

IN NATURAL LANGUAGE MODE can be written explicitly so readers understand the intent. If the search modifier is omitted, natural language mode is the default.

The column list in MATCH must correspond to the column list of a FULLTEXT index on the table as required by the engine. In the example, MATCH(title, body) uses `ft_articles_title_body`. If you want to search only on `title`, design a corresponding FULLTEXT index on `title` and use MATCH(title), rather than assuming a composite index will always serve every column subset.

Columns in MATCH must belong to the same table. A FULLTEXT index does not replace relational indexes for foreign keys, equality conditions, or standard sorting.

## 5. Basic Keyword Search

Query for articles related to transaction:

~~~sql
SELECT
    article_id,
    title,
    MATCH(title, body)
        AGAINST ('transaction' IN NATURAL LANGUAGE MODE) AS relevance
FROM articles
WHERE MATCH(title, body)
        AGAINST ('transaction' IN NATURAL LANGUAGE MODE)
ORDER BY relevance DESC, article_id;
~~~

MATCH AGAINST in SELECT returns the relevance score. The same expression in WHERE filters rows with matching search results. ORDER BY relevance DESC places higher-scoring documents first; `article_id` acts as a secondary tie-breaker for stable ordering when scores are equal.

Do not assume a specific relevance value will always stay identical across versions, engines, datasets, or configurations. Treat the score as a ranking signal, not as a probability or absolute quality score.

## 6. Natural Language Mode Searches Tokens, Not Substrings

Natural language mode parses the query string into words. Documents containing matching tokens can appear in results; the query does not require the words to be adjacent or in exact order like a phrase match.

Example:

~~~sql
SELECT article_id, title
FROM articles
WHERE MATCH(title, body)
    AGAINST ('database transaction' IN NATURAL LANGUAGE MODE);
~~~

This searches for the words `database` and `transaction` after parser processing. Do not interpret the query above as requiring the verbatim string `database transaction`.

If you need arbitrary substring search, LIKE has a different meaning:

~~~sql
SELECT article_id, title
FROM articles
WHERE body LIKE '%transaction%';
~~~

LIKE '%...%' can match a substring inside a word or a text span. FULLTEXT search matches tokens according to parser rules and can rank by relevance. The two approaches have different purposes and performance characteristics.

Natural language mode also does not automatically perform stemming or understand all grammatical variants. For example, different word forms may be treated as distinct tokens depending on the parser. If you need search for inflected languages, evaluate an appropriate parser or normalization strategy.

## 7. Relevance Score for Ranking

The relevance score represents the relative degree of match between a document and the search string according to the engine's algorithm. The score can be influenced by:

- Frequency of the token in the document.
- How common the token is across the document collection.
- Document length and token distribution.
- The columns included in MATCH.
- Engine, parser, and full-text configuration.

Example:

~~~sql
SELECT
    article_id,
    title,
    MATCH(title, body)
        AGAINST ('fulltext search' IN NATURAL LANGUAGE MODE) AS score
FROM articles
WHERE MATCH(title, body)
        AGAINST ('fulltext search' IN NATURAL LANGUAGE MODE) > 0
ORDER BY score DESC, published_at DESC;
~~~

Higher scores generally indicate more relevant results within the same query context. Do not compare scores directly across two tables with different content, engines, or indexes. If the UI needs a display threshold, evaluate the threshold using real data and monitor changes as data grows.

## 8. Searching Across Multiple Columns

A composite FULLTEXT index allows searching across multiple columns:

~~~sql
SELECT
    article_id,
    title,
    MATCH(title, body)
        AGAINST ('database index' IN NATURAL LANGUAGE MODE) AS relevance
FROM articles
WHERE MATCH(title, body)
        AGAINST ('database index' IN NATURAL LANGUAGE MODE) > 0
ORDER BY relevance DESC;
~~~

In a composite index, both `title` and `body` participate in the search. If `title` matters more than `body` in business ranking, consider:

- Using two separate FULLTEXT indexes and combining scores in the query if index structure/engine permits.
- Splitting `title` and `body` queries, then combining results in a controlled manner.
- Creating a normalized search content column with explicit rules.
- Applying business weights in the application layer after receiving relevance scores.

Do not arbitrarily add scores from different queries without verifying scales and datasets, because relevance values may not share the same comparison domain.

## 9. Combining FULLTEXT with Standard Filter Conditions

An application often searches only within published data:

~~~sql
SELECT
    article_id,
    title,
    MATCH(title, body)
        AGAINST ('transaction' IN NATURAL LANGUAGE MODE) AS relevance
FROM articles
WHERE status = 'PUBLISHED'
  AND MATCH(title, body)
        AGAINST ('transaction' IN NATURAL LANGUAGE MODE) > 0
ORDER BY relevance DESC, published_at DESC
LIMIT 20;
~~~

The FULLTEXT index handles the token search part; a B-tree index can support the `status` or `published_at` condition. The optimizer decides the plan based on statistics and cost. There is no guarantee every combined query will use both indexes in the exact way hoped for.

Use EXPLAIN to inspect the plan:

~~~sql
EXPLAIN
SELECT article_id, title
FROM articles
WHERE status = 'PUBLISHED'
  AND MATCH(title, body)
        AGAINST ('transaction' IN NATURAL LANGUAGE MODE);
~~~

Inspect key, access type, rows estimate, and Extra. Small datasets can cause the optimizer to choose a different plan than in production; benchmark on a dataset with near-production size and distribution.

## 10. Stopwords: Words Ignored During Indexing or Searching

Stopwords are common words that the full-text parser ignores to reduce noise and index size. In English, for example, this may include very frequent function words like `the`, `a`, or `is`, depending on the stopword list in use.

If a query contains only stopwords, results can be empty because those tokens are not included in the search. For example, searching for an overly common word is usually unhelpful.

InnoDB and MyISAM have separate stopword mechanisms and configurations. InnoDB uses a default stopword list or a configured list; MyISAM has its corresponding stopword configuration. When changing the stopword list, you must rebuild the FULLTEXT index so content is re-parsed under the new list.

Do not delete all stopwords just to make one specific query return results. Changing them affects index size, relevance, and every query on that index. Test with representative data before applying.

## 11. Minimum Token Size and Too-Short Words

Tokens shorter than the configured limit may not be indexed. Common defaults:

| Engine | Configuration | Common Default |
|---|---|---:|
| InnoDB | innodb_ft_min_token_size | 3 characters |
| MyISAM | ft_min_word_len | 4 characters |

For example, codes like `SQL`, `C`, `R`, or short product names may be skipped if the token is shorter than the limit. Check the actual server configuration rather than relying on defaults.

When changing minimum token size, you must rebuild the FULLTEXT index so tokens are indexed under the new limit. Changing the configuration variable without rebuilding the index does not re-tokenize existing data.

For languages that do not separate words with spaces such as Chinese, Japanese, or Korean, the default parser may be unsuitable. MySQL provides the ngram parser for searching fixed-length n-character sequences; the `ngram_token_size` setting affects segmentation and should be reviewed when creating/rebuilding indexes.

## 12. Differences Between InnoDB and MyISAM in Natural Language Mode

The two engines have notable differences:

| Characteristic | InnoDB | MyISAM |
|---|---|---|
| FULLTEXT support | Available since MySQL 5.6.4 | Available in earlier MySQL versions |
| Transactions | Yes, per InnoDB properties | Non-transactional |
| Common default minimum token | 3 | 4 |
| Stopwords | InnoDB mechanism and configuration | MyISAM mechanism and configuration |
| 50% common-word threshold in natural language | Not applied like MyISAM | Can exclude words appearing in over 50% of rows |
| Rollback recovery | InnoDB transactional changes roll back | No equivalent transactional guarantee |

The 50% threshold is a distinctive feature of MyISAM natural language search: a word appearing in more than half of the rows can be deemed too common and excluded from search. Do not apply this rule to InnoDB.

This explains why the same data and query can yield different results when switching engines. Do not switch engines merely to alter search results without evaluating transactions, locking, crash recovery, and write workload.

## 13. Collation and Case Sensitivity

Full-text matching behavior is affected by the character set and collation of the indexed columns. With a case-insensitive collation, search is typically case-insensitive. Binary collations or case-sensitive collations can produce different behavior.

Check column definitions:

~~~sql
SHOW FULL COLUMNS FROM articles;
~~~

If the application requires consistent search rules, choose the character set/collation during schema design and test uppercase, lowercase, Vietnamese diacritics, and Unicode characters. Do not assume the parser handles every language just like English.

## 14. Vietnamese Search and Parsers

Vietnamese text has diacritics and spaces between syllables. The default parser analyzes tokens according to its own rules and does not necessarily understand Vietnamese word boundaries like a dedicated word segmenter. Search results may differ from expectations when users enter phrases, compound words, or accented/unaccented forms.

Directions to test:

- Store content in the utf8mb4 character set with an appropriate collation.
- Test the same keywords in both accented and unaccented forms.
- Evaluate the default parser on a real Vietnamese corpus.
- Consider the ngram parser if it fits character-sequence search requirements.
- If linguistic word segmentation is required, consider preprocessing content in the application layer or a dedicated search solution.

Example creating an index using the ngram parser:

~~~sql
ALTER TABLE articles
    ADD FULLTEXT INDEX ft_articles_ngram (title, body)
    WITH PARSER ngram;
~~~

This is an additional index for testing purposes; do not create duplicates in production without evaluating storage size and query patterns. Ngram splits text into n-character segments, so it can match substrings differently from a standard word parser, though the index can be larger and relevance needs tuning.

## 15. Natural Language Mode Is Not Boolean Mode

Natural language mode interprets the search string as ordinary keywords. Control symbols such as plus signs, minus signs, asterisks, or parentheses do not carry Boolean operator meaning the way they do in Boolean mode.

Natural language example:

~~~sql
SELECT article_id, title
FROM articles
WHERE MATCH(title, body)
    AGAINST ('transaction isolation' IN NATURAL LANGUAGE MODE);
~~~

If you need required/excluded word syntax, trailing wildcards, or exact phrases, study Boolean mode separately. The following example only illustrates the syntax difference, not natural language mode:

~~~sql
SELECT article_id, title
FROM articles
WHERE MATCH(title, body)
    AGAINST ('+"transaction isolation" -rollback' IN BOOLEAN MODE);
~~~

Do not mix the two rule sets in the same query. Choose the mode based on desired product behavior: natural search with ranking, or queries with explicit control operators.

## 16. Natural Language Mode and Phrase Search

The query:

~~~sql
MATCH(title, body) AGAINST ('database transaction' IN NATURAL LANGUAGE MODE)
~~~

does not require the two words `database` and `transaction` to appear adjacent to each other in exact order. It searches by tokens and relevance.

If the business requirement is an exact phrase, use Boolean mode with the phrase enclosed in double quotes:

~~~sql
MATCH(title, body)
    AGAINST ('"database transaction"' IN BOOLEAN MODE)
~~~

Phrase search is still subject to tokenization, stopwords, and parser rules. It is not equivalent to matching any verbatim byte sequence with LIKE.

## 17. Result Pagination and Stable Ranking

Example fetching the top 20 results:

~~~sql
SELECT
    article_id,
    title,
    MATCH(title, body)
        AGAINST ('database index' IN NATURAL LANGUAGE MODE) AS relevance
FROM articles
WHERE status = 'PUBLISHED'
  AND MATCH(title, body)
        AGAINST ('database index' IN NATURAL LANGUAGE MODE) > 0
ORDER BY relevance DESC, published_at DESC, article_id DESC
LIMIT 20;
~~~

ORDER BY includes secondary criteria so ordering remains deterministic when multiple documents share the same relevance. For deep pages, large LIMIT offsets can be costly. Benchmark the query and consider a business-appropriate pagination strategy; do not assume relevance is a unique pagination key because scores can shift as data or indexes change.

## 18. Content Updates and FULLTEXT Index Maintenance

When rows are INSERTed, UPDATEd, or DELETEd, MySQL maintains the FULLTEXT index according to the engine's mechanism. With InnoDB, data and index changes participate in transactions; rebuilding an index can require substantial resources.

Operational aspects to manage:

- Creating an index on a large table can consume significant CPU, I/O, and time.
- Changing parser, stopwords, or minimum token size usually requires rebuilding the index.
- Changing character set/collation can affect tokenization and matching.
- After migrations, verify search queries and relevance using a standard keyword test suite.
- Monitor index size, write throughput, and query latency.

Do not drop and recreate FULLTEXT indexes arbitrarily during peak hours. Plan deployments, check locking/DDL impact, and prepare a rollback plan appropriate for your MySQL version.

## 19. Inspecting FULLTEXT Indexes and Execution Plans

List indexes:

~~~sql
SHOW INDEX FROM articles;
~~~

View table definition:

~~~sql
SHOW CREATE TABLE articles;
~~~

Inspect execution plan:

~~~sql
EXPLAIN
SELECT article_id, title
FROM articles
WHERE MATCH(title, body)
    AGAINST ('transaction' IN NATURAL LANGUAGE MODE);
~~~

Observe `key` and access `type` to confirm the appropriate FULLTEXT index is used. If the plan is not as expected, check:

- Whether the column list in MATCH matches a FULLTEXT index.
- Whether the table has the right engine and the index exists.
- Whether any tokens in the search string were excluded by stopwords or minimum token size.
- Whether parser and collation settings are appropriate.
- Whether the query has expressions or conditions altering the plan.

EXPLAIN shows the estimated plan, not actual latency. Benchmark with a dataset, text lengths, and keyword distribution close to production.

## 20. Common Errors

| Symptom | Possible Cause | How to Check / Handle |
|---|---|---|
| MATCH AGAINST reports missing FULLTEXT index error | Index not created or column list does not match | Run SHOW INDEX and compare with MATCH columns |
| Very short words not found | Excluded by minimum token size | Check innodb_ft_min_token_size or ft_min_word_len |
| Common words return no results on MyISAM | 50% threshold rule | Check engine; InnoDB does not use this threshold |
| Query with only stopwords returns empty | Tokens ignored by stopword list | Check stopword list and pick meaningful keywords |
| LIKE finds it but FULLTEXT does not | LIKE searches substrings, FULLTEXT searches tokens | Clarify the desired search type |
| Non-adjacent words still match as a phrase | Natural language is not exact phrase matching | Use Boolean phrase search if exact phrase is required |
| Vietnamese search does not behave as expected | Default parser does not segment words per domain language | Test utf8mb4, collation, ngram, or preprocessing |
| Ranking order changes | Corpus, tokens, index, or engine changed | Evaluate relevance on the current dataset |
| Index creation slows down the system | DDL/index build consumes resources | Plan ahead and monitor resources |

## 21. Process for Deploying Natural Language Search

1. Identify text columns to search and the table's storage engine.
2. Choose the FULLTEXT column list matching the queries.
3. Create the FULLTEXT index and verify with SHOW CREATE TABLE.
4. Confirm character set, collation, and parser.
5. Check minimum token size and stopword list.
6. Write MATCH(...) AGAINST(... IN NATURAL LANGUAGE MODE).
7. Return the relevance score and sort descending.
8. Combine status/date filters as needed by the application.
9. Use EXPLAIN and benchmark on representative data.
10. Test short words, stopwords, common words, Unicode, and zero-result queries.
11. Define how to handle phrase search or Boolean operators if needed by the product.
12. Re-measure after changing parser, stopwords, engine, or indexed content.

## 22. Practice Exercises

1. Create an `articles` table with `title`, `body`, and a composite FULLTEXT index.
2. Insert at least 10 articles with varied content and keywords.
3. Search for the word `transaction` using natural language mode and display relevance.
4. Search for two words `database index`; check documents matching one or more tokens.
5. Sort by `relevance DESC` and add `article_id` as a secondary sort key.
6. Combine MATCH AGAINST with the condition `status = 'PUBLISHED'`.
7. Try a short word like `SQL` and observe the effect of minimum token size on your engine.
8. Try a stopword and a rare word; compare result counts.
9. Compare FULLTEXT results with `LIKE '%transaction%'`.
10. Compare natural language with Boolean phrase search to see semantic differences.
11. Use EXPLAIN and SHOW INDEX to confirm the FULLTEXT index is used.
12. Test accented/unaccented Vietnamese text and evaluate the default parser vs. ngram on test data.
13. If the environment allows, compare InnoDB and MyISAM behavior, especially MyISAM's 50% rule.
14. Write a deployment checklist for changing stopwords or minimum token size and explain why the index must be rebuilt.

You have completed this lesson when you can create an appropriate FULLTEXT index, write MATCH AGAINST in natural language mode, explain relevance scores, predict the impact of stopwords/minimum token size, and distinguish token search from substring or exact phrase matching. Treat natural language mode as a text search and ranking mechanism with well-defined parser rules, not a general-purpose string matcher.
