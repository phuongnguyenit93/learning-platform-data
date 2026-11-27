# FULLTEXT Indexes and Supported Engine/Column Requirements

MySQL provides **FULLTEXT indexes** to search for words or phrases within text content. Unlike B-tree indexes, which are typically used for equality comparisons, range scans, and sorting, a FULLTEXT index parses text into tokens and indexes them to support natural language or Boolean search.

This lesson belongs to the **DATABASE_MYSQL** module. The module aims to master MySQL from table design, data types, keys, and SQL queries to indexes, transactions, and concurrency control, while practicing execution plan analysis, query optimization, privilege management, backups, and relational database operational troubleshooting. In the **Full-Text Search** chapter, this lesson focuses on FULLTEXT indexes and requirements regarding storage engines, column types, and parsers. `SPECIAL_NOTE` is empty, so no extra specific constraints apply to this lesson.

## 1. What Problem Does a FULLTEXT Index Solve?

Suppose an articles table has a title and a long body. The application needs to find articles containing keywords such as `mysql`, `index`, or the phrase `query optimizer`.

If you only use:

```sql
SELECT *
FROM articles
WHERE body LIKE '%mysql%';
```

MySQL must inspect the content of matching rows. A standard B-tree index cannot help search efficiently with a leading wildcard (`%mysql%`). When text data is large, this type of search can consume significant I/O and CPU.

A FULLTEXT index indexes tokens in text to support search queries:

```sql
SELECT
    article_id,
    title
FROM articles
WHERE MATCH(title, body)
      AGAINST ('mysql index' IN NATURAL LANGUAGE MODE);
```

FULLTEXT is not a replacement for every string search. If you need to find an arbitrary substring, identifier, exact string, or custom pattern, `LIKE`, a B-tree on an appropriate column, or another search solution may be more suitable.

## 2. Which Storage Engines Support FULLTEXT?

In MySQL, FULLTEXT indexes are supported by two main storage engines:

| Storage Engine | FULLTEXT | Notable Characteristics |
|---|---|---|
| InnoDB | Yes | Transactional engine; usually the default choice for new applications. |
| MyISAM | Yes | Legacy engine; lacks transactions and uses table-level locking. |
| MEMORY | No | Does not support FULLTEXT indexes. |
| CSV | No | Does not support FULLTEXT indexes. |
| Other engines | Depends on engine | Not assumed supported by default; check the documentation for the engine in use. |

For most new applications, prefer InnoDB for transactions, crash recovery, and row-level locking. MyISAM can still be encountered in legacy systems or specific workloads, but you must account for the lack of transaction support and its different locking behavior compared to InnoDB.

Check the table's engine:

```sql
SHOW TABLE STATUS
LIKE 'articles';

SHOW CREATE TABLE articles;

SELECT
    TABLE_SCHEMA,
    TABLE_NAME,
    ENGINE
FROM INFORMATION_SCHEMA.TABLES
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'articles';
```

If the table uses an engine that does not support FULLTEXT, declaring a FULLTEXT index will fail. You can consider converting the table to InnoDB after evaluating compatibility, storage size, foreign keys, data types, and a migration plan:

```sql
ALTER TABLE articles ENGINE = InnoDB;
```

Changing engines is a structural modification that can consume time, I/O, temporary space, and lock the table during part of the operation. Test on a copy of the data and plan an appropriate deployment window.

## 3. Which Column Types Can Be FULLTEXT Indexed?

FULLTEXT indexes apply directly only to character columns of one of the following types:

- `CHAR`
- `VARCHAR`
- `TEXT` and variants in the TEXT family such as `TINYTEXT`, `MEDIUMTEXT`, `LONGTEXT`

Numeric types such as `INT`, `BIGINT`, `DECIMAL`, date/time types, `BLOB`, and JSON types are not column types directly supported by FULLTEXT indexes.

Valid example:

```sql
CREATE TABLE articles (
    article_id BIGINT NOT NULL AUTO_INCREMENT,
    title VARCHAR(250) NOT NULL,
    summary TEXT,
    body LONGTEXT,
    published_at DATETIME,
    PRIMARY KEY (article_id),
    FULLTEXT KEY ft_title_body (title, body)
) ENGINE = InnoDB;
```

The FULLTEXT index above includes two character columns from the same table. You cannot create a single FULLTEXT index combining columns from multiple different tables.

Invalid column type example:

```sql
CREATE TABLE invalid_fulltext_example (
    id BIGINT NOT NULL PRIMARY KEY,
    title VARCHAR(200),
    payload JSON,
    created_at DATETIME,
    FULLTEXT KEY ft_payload (payload)
) ENGINE = InnoDB;
```

`payload` has type JSON, so it cannot be placed directly in a FULLTEXT index under column type rules. If you need to search content inside JSON, design a separate text attribute or an appropriate extraction model, then verify the column type and indexing capability with your deployed MySQL version.

## 4. Table and Column List Requirements

When creating a FULLTEXT index, ensure:

1. The table uses a storage engine that supports FULLTEXT, usually InnoDB or MyISAM.
2. Each column in the index list has type CHAR, VARCHAR, or TEXT.
3. The columns belong to the same table.
4. The table/columns have a charset/collation appropriate for the content and desired search behavior.
5. The column list in `MATCH()` corresponds to the column list of an existing FULLTEXT index.

A FULLTEXT index can index one column or multiple columns. Example:

```sql
-- Example of adding a separate index for title.
ALTER TABLE articles
ADD FULLTEXT KEY ft_title (title);
```

The `articles` table in the Section 3 example already has a composite title/body index. Only add a separate index for `title` if the workload actually runs `MATCH(title)` queries; do not create an index that duplicates an existing one. A `MATCH(title, body)` query must use the exact corresponding indexed column set.

FULLTEXT indexes do not accept a prefix length declaration like B-tree indexes. Do not write `FULLTEXT KEY ft_body (body(100))`.

## 5. Creating a FULLTEXT Index

You can create a FULLTEXT index when creating the table:

```sql
CREATE TABLE product_documents (
    document_id BIGINT NOT NULL AUTO_INCREMENT,
    title VARCHAR(250) NOT NULL,
    description TEXT,
    PRIMARY KEY (document_id),
    FULLTEXT KEY ft_title_description (title, description)
) ENGINE = InnoDB;
```

Or add it after the table already exists:

```sql
ALTER TABLE articles
ADD FULLTEXT INDEX ft_articles_title_body (title, body);
```

Or use the syntax:

```sql
CREATE FULLTEXT INDEX ft_articles_title_body
ON articles (title, body);
```

All of the above create a FULLTEXT index on the specified column set. Creating an index on a large table may require reading and parsing substantial data, consuming CPU, I/O, and storage; evaluate duration and locking impact before running on production.

The statements in this section are alternative ways to create an index. Use only one approach, and only when the table does not already have a FULLTEXT index on the same column set; the example in Section 3 already created the title/body index inside CREATE TABLE.

## 6. Using MATCH ... AGAINST

`MATCH()` specifies the columns to search; `AGAINST()` provides the query string and search mode.

Example:

```sql
SELECT
    article_id,
    title,
    MATCH(title, body)
        AGAINST ('mysql index' IN NATURAL LANGUAGE MODE) AS relevance
FROM articles
WHERE MATCH(title, body)
      AGAINST ('mysql index' IN NATURAL LANGUAGE MODE)
ORDER BY relevance DESC;
```

In this example:

- `MATCH(title, body)` searches across the two columns indexed together.
- `AGAINST(...)` specifies the search keywords.
- `IN NATURAL LANGUAGE MODE` requests natural language mode.
- The `relevance` score indicates the relative match quality according to the FULLTEXT algorithm.

If the search mode is omitted, MySQL defaults to natural language mode. However, it is good practice to specify the mode explicitly so readers understand the intended behavior.

Do not interpret relevance as a probability or an absolute quality score. It is a MySQL ranking score based on content, tokens, and dataset statistics.

MyISAM's natural language mode also has a 50% threshold: a word appearing in more than half of the rows can be treated as lacking sufficient distinguishing power and ignored in results. InnoDB does not apply this 50% threshold. Therefore, the same data and query can produce different results when switching engines.

## 7. Basic Search Modes

MySQL has three common FULLTEXT search modes:

| Mode | Syntax | Purpose |
|---|---|---|
| Natural language | `IN NATURAL LANGUAGE MODE` | Search by keyword meaning and rank by relevance. |
| Boolean | `IN BOOLEAN MODE` | Use operators to require, exclude, or combine keywords. |
| Query expansion | `WITH QUERY EXPANSION` | Expand the query based on initial matching results. |

### 7.1. Natural Language Mode

`IN NATURAL LANGUAGE MODE` is the default mode. MySQL parses keywords, computes relevance, and returns matching rows:

```sql
SELECT
    article_id,
    title,
    MATCH(title, body)
        AGAINST ('mysql transaction' IN NATURAL LANGUAGE MODE) AS score
FROM articles
WHERE MATCH(title, body)
      AGAINST ('mysql transaction' IN NATURAL LANGUAGE MODE)
ORDER BY score DESC;
```

Words treated as stopwords or shorter than the token-length threshold may be ignored. Consequently, querying a very short or very common word may not return the results a newcomer expects.

### 7.2. Boolean Mode

Boolean mode allows using operators to express search conditions:

| Operator | Common Meaning |
|---|---|
| `+word` | The word must be present. |
| `-word` | Exclude results containing this word. |
| `word*` | Search for tokens with the prefix `word`. |
| `"a phrase"` | Search for a phrase in order. |
| `word` | The word is allowed to appear but is not strictly required. |

Example requiring `mysql` while excluding `oracle`:

```sql
SELECT
    article_id,
    title,
    MATCH(title, body)
        AGAINST ('+mysql -oracle' IN BOOLEAN MODE) AS score
FROM articles
WHERE MATCH(title, body)
      AGAINST ('+mysql -oracle' IN BOOLEAN MODE)
ORDER BY score DESC;
```

Prefix search example:

```sql
SELECT article_id, title
FROM articles
WHERE MATCH(title, body)
      AGAINST ('transact*' IN BOOLEAN MODE);
```

Boolean mode has its own syntax rules; do not combine operators arbitrarily. In particular, `+` and `-` must attach directly to the token they modify.

### 7.3. Query Expansion

`WITH QUERY EXPANSION` performs an initial search and then uses some of the matching documents to expand keywords for a second search pass:

```sql
SELECT article_id, title
FROM articles
WHERE MATCH(title, body)
      AGAINST ('mysql index' WITH QUERY EXPANSION);
```

This mode can uncover additional topically related documents, but it can also pull results away from the original intent. Enable it only after testing result quality against real data and queries.

## 8. Multi-Column FULLTEXT Indexes and MATCH()

If you create the index:

```sql
FULLTEXT KEY ft_title_body (title, body)
```

then the corresponding query is:

```sql
MATCH(title, body) AGAINST ('mysql' IN NATURAL LANGUAGE MODE)
```

The column list in MATCH must correspond to a FULLTEXT index. Do not create a composite index `(title, body)` and then query `MATCH(title)` expecting MySQL to automatically use that composite index.

If both searching `title` alone and searching `title`/`body` together are important, you can maintain two FULLTEXT indexes as created in the examples in Sections 3 and 4:

| FULLTEXT Index | Corresponding MATCH Clause |
|---|---|
| `ft_title_body (title, body)` | `MATCH(title, body)` |
| `ft_title (title)` | `MATCH(title)` |

Each index increases storage size and maintenance overhead during INSERT, UPDATE, or DELETE. Create only the combinations that serve real queries.

## 9. Tokens, Stopwords, and Minimum Word Length

FULLTEXT does not index every character sequence byte-by-byte. The parser breaks text into **tokens**. Some tokens may be skipped:

- Tokens shorter than the minimum length limit.
- Tokens longer than the maximum length limit.
- Stopwords present in the configured stopword list.
- Tokens not recognized by the active parser's word-splitting rules.

Common default values:

| Engine | Configuration Variable | Default |
|---|---|---:|
| InnoDB | `innodb_ft_min_token_size` | 3 |
| MyISAM | `ft_min_word_len` | 4 |

For example, with default settings, a very short word like `db` may not be indexed by the default parser. Stopwords such as certain common words may also be discarded and therefore cannot serve as useful search terms in natural language mode.

You can check the configuration:

```sql
SHOW VARIABLES LIKE 'innodb_ft_min_token_size';
SHOW VARIABLES LIKE 'innodb_ft_max_token_size';
SHOW VARIABLES LIKE 'innodb_ft_enable_stopword';
SHOW VARIABLES LIKE 'ft_min_word_len';
SHOW VARIABLES LIKE 'ft_max_word_len';
SHOW VARIABLES LIKE 'ft_stopword_file';
```

Token-size configuration variables are typically set at server startup. When changing thresholds or stopword configuration, follow the documentation for your MySQL version and **rebuild the FULLTEXT index** so stored tokens are regenerated under the new settings. Merely changing configuration variables does not automatically re-parse existing indexes.

With InnoDB, you can configure a server-level or user-level stopword table; MyISAM has its own stopword configuration mechanism. Do not assume the stopword list or behavior is identical between the two engines.

## 10. Charset and Collation Affect Search Results

FULLTEXT analyzes text according to the column's character set and collation. These attributes affect case comparison, accents, and multi-byte characters.

Example:

```sql
CREATE TABLE multilingual_articles (
    article_id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    title VARCHAR(250)
        CHARACTER SET utf8mb4
        COLLATE utf8mb4_unicode_ci,
    body TEXT
        CHARACTER SET utf8mb4
        COLLATE utf8mb4_unicode_ci,
    FULLTEXT KEY ft_title_body (title, body)
) ENGINE = InnoDB;
```

The `utf8mb4_unicode_ci` collation uses Unicode comparison rules that are case-insensitive and accent-insensitive. Other collations can produce different matching behavior. When building multilingual search, test with accented characters, upper/lower case, punctuation, and actual non-ASCII characters from your application.

Do not treat a collation change as a purely visual change. It can affect comparisons, uniqueness, sort order, and how FULLTEXT parses/matches content. Inspect existing data and rebuild indexes when needed according to your schema change procedure.

## 11. Default Parser and the ngram Parser

The default parser generally splits tokens on word boundaries and delimiters that the parser recognizes. This works well for many languages that use spaces to separate words. However, some languages lack clear space-delimited word boundaries or have complex word-segmentation rules.

MySQL provides the ngram full-text parser to split text into contiguous character sequences of fixed length (n-grams). This parser is useful for CJK search such as Chinese, Japanese, and Korean.

Creating an index using ngram:

```sql
CREATE TABLE cjk_documents (
    document_id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    content TEXT NOT NULL,
    FULLTEXT KEY ft_content_ngram (content) WITH PARSER ngram
) ENGINE = InnoDB;
```

The n-gram length is controlled by the `ngram_token_size` variable; the default is 2. This setting affects how text is tokenized, index size, and keyword matching. If you change its value, you must rebuild FULLTEXT indexes that use the ngram parser.

You can check the variable:

```sql
SHOW VARIABLES LIKE 'ngram_token_size';
```

Ngram is not a complete linguistic analyzer. For Vietnamese, the default parser may treat space-separated syllables as individual tokens; ngram does not automatically understand all Vietnamese compound word rules or semantics. Test search quality on a real text corpus before choosing a parser.

## 12. Limitations to Know Before Designing

Several limitations directly affect table design:

- FULLTEXT supports only CHAR, VARCHAR, and TEXT types; it does not apply directly to numeric, date/time, BLOB, or JSON columns.
- The table's engine must support FULLTEXT, typically InnoDB or MyISAM.
- Columns in a single FULLTEXT index must belong to the same table.
- FULLTEXT indexes do not support prefix lengths like B-tree indexes.
- FULLTEXT indexes are not supported on partitioned tables.
- The column list in MATCH must match a corresponding FULLTEXT index.
- Stopwords and token-size limits can prevent a word from entering the index.
- Parser and collation affect how content is parsed and matched.

If the application needs to search JSON content, explicitly identify which text fields need to be searchable. You can extract that content into a text column maintained under a data contract, then create a FULLTEXT index on that appropriate column. You cannot simply declare FULLTEXT on a JSON column.

## 13. Verifying That a FULLTEXT Index Was Created

View table indexes:

```sql
SHOW INDEX FROM articles;
```

Or query metadata:

```sql
SELECT
    TABLE_SCHEMA,
    TABLE_NAME,
    INDEX_NAME,
    INDEX_TYPE,
    COLUMN_NAME,
    SEQ_IN_INDEX
FROM INFORMATION_SCHEMA.STATISTICS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'articles'
ORDER BY INDEX_NAME, SEQ_IN_INDEX;
```

For a FULLTEXT index, INDEX_TYPE shows FULLTEXT. Columns in a composite index share the same INDEX_NAME, and column order is represented by SEQ_IN_INDEX.

Check column types and charset/collation:

```sql
SELECT
    COLUMN_NAME,
    DATA_TYPE,
    COLUMN_TYPE,
    CHARACTER_SET_NAME,
    COLLATION_NAME
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'articles'
ORDER BY ORDINAL_POSITION;
```

Inspect both the table definition and metadata before concluding that an index has the expected column set, engine, and data types.

## 14. Checking the Execution Plan

After creating the index, use EXPLAIN to see whether the optimizer chooses FULLTEXT access:

```sql
EXPLAIN
SELECT article_id, title
FROM articles
WHERE MATCH(title, body)
      AGAINST ('mysql index' IN NATURAL LANGUAGE MODE);
```

When a FULLTEXT index is used, the plan may show an access type of `fulltext`. Read the key, possible_keys, rows, and Extra columns as well; do not draw conclusions solely from the fact that the query runs without error.

If the FULLTEXT index is not chosen, check in order:

1. Is the table engine InnoDB or MyISAM?
2. Are the indexed columns CHAR, VARCHAR, or TEXT?
3. Was the index created on the right table and right column set?
4. Does the column list in MATCH match the index?
5. Was the keyword excluded by token-size limits or stopwords?
6. Is a different parser, charset, or collation being used than expected?
7. Does the query use valid syntax and search mode?

EXPLAIN describes the optimizer's estimated plan. For real workloads, measure execution time, returned row counts, CPU/I/O load, and behavior as data grows.

## 15. Lab: Creating and Querying FULLTEXT on InnoDB

This lab uses a dedicated table to practice engine/column requirements, index creation, and querying. Run it in a test schema; if the table already exists, inspect it before recreating.

### 15.1. Create the Table

```sql
CREATE TABLE fts_lab_articles (
    article_id BIGINT NOT NULL AUTO_INCREMENT,
    title VARCHAR(200) NOT NULL,
    body TEXT NOT NULL,
    PRIMARY KEY (article_id),
    FULLTEXT KEY ft_lab_title_body (title, body)
) ENGINE = InnoDB
  DEFAULT CHARSET = utf8mb4
  COLLATE = utf8mb4_unicode_ci;
```

### 15.2. Insert Data

```sql
INSERT INTO fts_lab_articles (title, body)
VALUES
    (
        'MySQL full text search',
        'MySQL supports FULLTEXT indexes for searching words in text columns.'
    ),
    (
        'InnoDB transaction basics',
        'InnoDB provides transactions, row locks, and crash recovery.'
    ),
    (
        'Database indexing',
        'B-tree indexes help equality and range queries; FULLTEXT helps text search.'
    );
```

### 15.3. Natural Language Search

```sql
SELECT
    article_id,
    title,
    MATCH(title, body)
        AGAINST ('mysql fulltext' IN NATURAL LANGUAGE MODE) AS score
FROM fts_lab_articles
WHERE MATCH(title, body)
      AGAINST ('mysql fulltext' IN NATURAL LANGUAGE MODE)
ORDER BY score DESC;
```

### 15.4. Boolean Search

```sql
SELECT article_id, title
FROM fts_lab_articles
WHERE MATCH(title, body)
      AGAINST ('+mysql -transaction' IN BOOLEAN MODE);
```

### 15.5. Inspect Index and Plan

```sql
SHOW INDEX FROM fts_lab_articles;

EXPLAIN
SELECT article_id, title
FROM fts_lab_articles
WHERE MATCH(title, body)
      AGAINST ('mysql fulltext' IN NATURAL LANGUAGE MODE);
```

Compare the `ft_lab_title_body` index, column types, engine, and access type in EXPLAIN. Exact results also depend on server version, token configuration, and data content.

## 16. Maintenance Cost and Managing FULLTEXT Indexes

FULLTEXT indexes speed up search queries, but they require storage space and maintenance overhead:

- INSERT must parse content and add tokens to the index.
- UPDATE on indexed columns can modify many tokens.
- DELETE must remove the associated index entries.
- Creating or rebuilding an index on a large table consumes CPU, I/O, and temporary storage.
- Multiple FULLTEXT indexes with different column combinations increase write overhead.

Only index columns actually used in queries. If an index is no longer needed, you can drop it:

```sql
ALTER TABLE articles
DROP INDEX ft_articles_title_body;
```

Before dropping, verify whether any application queries depend on the index. Index changes on large tables should be scheduled and monitored like any schema migration.

## 17. Common Errors

| Symptom | Possible Cause | How to Handle |
|---|---|---|
| Cannot create FULLTEXT index | Engine does not support it | Use InnoDB or MyISAM after evaluating migration. |
| Invalid column type error | Column is numeric, date/time, BLOB, or JSON | Use an appropriate CHAR, VARCHAR, or TEXT column. |
| MATCH cannot use the index | Column list does not match a FULLTEXT index | Create an index on the exact column set or fix MATCH. |
| Searching a very short word returns no results | Token is shorter than min token size | Check engine configuration and consider an appropriate threshold. |
| Searching a common word returns no results | Stopwords or MyISAM's 50% threshold | Check stopwords and engine differences. |
| Poor CJK search results | Default parser does not segment appropriately | Evaluate the ngram parser and ngram_token_size. |
| Accented words give unexpected results | Charset/collation differs from expectations | Check charset/collation and real data. |
| Index creation takes a long time | Large table, long text, or limited I/O | Measure load, storage, and pick a deployment window. |
| LIKE speed differs from expectations | FULLTEXT and LIKE have different semantics and plans | Choose the right tool for the search type and measure on real data. |
| Index exists but results are missing | Tokenization, stopwords, parser, or mode | Check configuration and query step by step. |

## 18. Design and Verification Process

When adding FULLTEXT to a live table, proceed in order:

1. Identify the exact search queries and text columns to be searched.
2. Check the table engine; prefer InnoDB for applications needing transactions.
3. Verify column types are CHAR, VARCHAR, or TEXT.
4. Decide whether a single-column or multi-column composite index is needed.
5. Check charset/collation and the parser suited to the data's language.
6. Check min/max token size and stopword configuration.
7. Create the FULLTEXT index in a test environment.
8. Test natural language, boolean, and query expansion if needed.
9. Verify metadata using SHOW INDEX and INFORMATION_SCHEMA.STATISTICS.
10. Use EXPLAIN to confirm the query plan.
11. Measure result quality, query latency, and write overhead during INSERT/UPDATE/DELETE.
12. Plan creating, rebuilding, or dropping the index in production.

## 19. Practice Exercises

### Exercise 1: Check Engine

Create a text table on InnoDB and try creating a FULLTEXT index. Check the engine using SHOW TABLE STATUS and INFORMATION_SCHEMA.TABLES.

**Task:** explain why the engine is a prerequisite before creating FULLTEXT.

### Exercise 2: Check Column Types

Create a table with title VARCHAR, body TEXT, amount DECIMAL, and payload JSON.

**Task:** identify which columns can be placed directly into a FULLTEXT index and explain why the remaining columns are unsuitable.

### Exercise 3: Single-Column and Multi-Column Indexes

Create a separate FULLTEXT index for title and a composite title/body index.

**Task:** write two corresponding MATCH queries; explain why the column list must match the index.

### Exercise 4: Natural Language and Boolean

Search for documents containing the word mysql, then require mysql and exclude oracle using Boolean mode.

**Task:** compare the results and relevance.

### Exercise 5: Token-Size and Stopwords

Check the min token size configuration and try searching for a short word and a common word.

**Task:** explain why results may be omitted; do not modify production configuration during the exercise.

### Exercise 6: ngram Parser

Create a FULLTEXT index using the ngram parser on a test text column.

**Task:** check ngram_token_size and compare search behavior with the default parser on CJK data.

### Exercise 7: EXPLAIN

Run EXPLAIN on a MATCH ... AGAINST query.

**Task:** identify the access type and key, and explain whether the FULLTEXT index is being used.

## 20. FULLTEXT Review Checklist

- [ ] Confirmed storage engine supports FULLTEXT.
- [ ] Confirmed indexed columns are CHAR, VARCHAR, or TEXT.
- [ ] Columns in the index belong to the same table.
- [ ] No prefix length is used on the FULLTEXT index.
- [ ] MATCH column list matches a FULLTEXT index.
- [ ] Chose single-column or multi-column based on actual queries.
- [ ] Checked charset/collation.
- [ ] Checked parser, stopwords, and min/max token size.
- [ ] Considered ngram for CJK data.
- [ ] Understood MyISAM natural language mode's 50% threshold difference.
- [ ] Verified index via SHOW INDEX or INFORMATION_SCHEMA.STATISTICS.
- [ ] Verified query plan with EXPLAIN.
- [ ] Evaluated INSERT/UPDATE/DELETE overhead and index size.
- [ ] Tested search quality on representative data.

## 21. Key Takeaways

A FULLTEXT index is used for searching tokens in text content and is supported by InnoDB and MyISAM. Indexed columns must be of type CHAR, VARCHAR, or TEXT; a multi-column index only combines columns from the same table. The column list in MATCH must correspond to a FULLTEXT index. FULLTEXT does not use prefix lengths and is not supported on partitioned tables.

Queries use MATCH ... AGAINST with natural language, boolean, or query expansion mode. Results depend on the parser, charset/collation, stopwords, and token-size limits. InnoDB and MyISAM have configuration differences, notably MyISAM natural language mode's 50% threshold, which InnoDB does not apply. Use SHOW INDEX, INFORMATION_SCHEMA, and EXPLAIN to verify structure and execution plans; measure both search cost and index maintenance overhead before deploying.
