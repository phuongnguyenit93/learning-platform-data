# Text Search Problems and Differences from LIKE

Text search appears in many application features: searching articles by content, searching products by name/description, looking up documents, filtering comments, or finding information in event descriptions. Although all of these can start with `LIKE`, not every search problem is a string pattern-matching problem.

`LIKE` checks whether a string matches a pattern. It is suitable for substring, prefix, or simple character pattern matching. Full-text search analyzes text into tokens/terms, indexes words, and supports searching by words, phrases, and search operators along with relevance scores. The two approaches have different semantics and access paths.

Choosing the right mechanism depends on the user's question: do you need to find an exact sequence of characters anywhere in the string, provide prefix suggestions, or find documents about a topic and rank the results? `LIKE '%term%'` is not a full-text engine; conversely, FULLTEXT does not replace every substring search.

## 1. Two Different Problems

Suppose the `articles` table contains article titles and bodies. The user enters `transaction`.

With `LIKE`, the database checks whether the string contains the exact character sequence `transaction` according to the collation. It does not understand that this is a word, does not analyze relevance, and does not automatically rank articles.

With full-text search, MySQL parses the content into tokens, stores a full-text index structure, and finds documents with matching tokens. Natural language mode can return a relevance score to rank results.

| Question | Usually Appropriate Mechanism |
| --- | --- |
| Does the code name contain the string `AB-12` in the middle? | `LIKE '%AB-12%'` or a specialized string search operation |
| Does the username start with `nguy`? | `LIKE 'nguy%'` with an appropriate index |
| Which articles talk about transaction and isolation? | FULLTEXT |
| Search for an exact phrase in the content? | FULLTEXT phrase search or `LIKE` if literal substring matching is needed |
| Find every occurrence of any character sequence, even mid-word? | `LIKE '%...%'` or a dedicated substring/ngram system |
| Rank documents by relevance to multiple keywords? | FULLTEXT or a dedicated search engine |

Before writing SQL, clearly define whether "match" means matching characters, prefixes, tokenized words, phrases, or topics.

## 2. LIKE: Character Pattern Matching

`LIKE` uses two primary wildcards:

- `%`: matches zero, one, or more characters.
- `_`: matches exactly one character.

Examples:

```sql
SELECT product_id, product_name
FROM products
WHERE product_name LIKE 'wireless%';
```

The query finds product names starting with `wireless`.

```sql
SELECT product_id, product_name
FROM products
WHERE product_name LIKE '%wireless%';
```

The query finds the string `wireless` anywhere in the product name.

```sql
SELECT product_id, product_name
FROM products
WHERE product_code LIKE 'AB_12';
```

This pattern matches `AB` + any single character + `12`; `_` does not represent a literal underscore.

`LIKE` does not automatically tokenize words, remove stopwords, compute relevance, or understand semantic relationships between words. It only applies pattern-matching rules according to the expression's charset/collation.

## 3. Escaping Wildcard Characters When Searching for Literals

If the user needs to search for the literal `%` or `_` character itself, they must be escaped. For example, searching for a code containing a literal underscore:

```sql
SELECT product_id, product_code
FROM products
WHERE product_code LIKE '%\\_%' ESCAPE '\\';
```

In this example, backslash is the escape character, so `\\_` in the SQL string represents a literal underscore; `%` on both ends remains a wildcard. You can choose another escape character to avoid differences caused by the `NO_BACKSLASH_ESCAPES` SQL mode.

When building queries from user input, never concatenate input into SQL. Use prepared statements and escape wildcards according to the search semantics the product wants to provide. Parameter binding prevents SQL injection, but by itself does not turn `%` and `_` into literal characters.

## 4. Collation Affects LIKE Results

String comparisons are affected by charset and collation. With a case-insensitive collation, `LIKE 'mysql%'` can match `MySQL Server`; with a case-sensitive collation, the result differs. Accent sensitivity also depends on the collation.

Check collation:

```sql
SHOW FULL COLUMNS FROM products;

SELECT
    COLLATION(product_name),
    CHARSET(product_name)
FROM products
LIMIT 1;
```

Do not assume all text columns share the same comparison rules. When case-sensitive or accent-sensitive search is required, specify the appropriate collation and verify with real data.

## 5. LIKE and B-tree Index Usage

With a standard B-tree index on a string column, a pattern with a fixed prefix can allow a range lookup:

```sql
CREATE INDEX idx_products_name
ON products (product_name);

SELECT product_id, product_name
FROM products
WHERE product_name LIKE 'wireless%';
```

The optimizer can use the index because the beginning of the pattern is a fixed string. Whether the index is actually used also depends on data type, collation, expressions, and cost estimates; confirm with `EXPLAIN`.

Conversely:

```sql
SELECT product_id, product_name
FROM products
WHERE product_name LIKE '%wireless%';
```

A wildcard at the start of the pattern prevents the B-tree from identifying a contiguous range starting from a prefix. The query usually has to inspect many rows (typically a table scan or index scan). An index on the column might still be chosen in certain special cases, but it cannot be used as a prefix range lookup.

This does not mean `LIKE '%...%'` is always wrong. For small tables, low data volume, or infrequent queries, it can be simple enough. Problems arise when the table is large, queries are frequent, and the number of rows scanned is high.

## 6. LIKE Does Not Rank Relevance

Suppose three articles all contain the word `transaction`:

- Article A has this word in the title and 20 occurrences in the body.
- Article B mentions it only once near the end.
- Article C has the string `transaction` inside a long code snippet.

A `LIKE '%transaction%'` condition only determines which rows contain the matching string. Without adding custom logic, it does not know that Article A should be displayed before Article B.

You can build your own score using `CASE`, occurrence counts, or title weights, but that is ranking logic built by the application/SQL. FULLTEXT provides built-in token matching and relevance scoring better suited to keyword document search.

## 7. What Is Full-Text Search?

Full-text search parses text into search units (tokens/terms), indexes those tokens, and maps them back to the documents/rows containing them. When searching, MySQL looks up the full-text index instead of comparing a character pattern against every string value.

A full-text index differs from a B-tree index:

- A B-tree orders key values to support equality, range, and prefix lookups.
- FULLTEXT indexes words/tokens appearing in text.
- A single token can appear in many rows; the full-text index stores the relationship between tokens and documents.
- FULLTEXT queries can compute relevance to rank results.
- Tokenization, stopwords, and token length limits affect which words enter the index.

FULLTEXT is designed for natural language content search. It is not an index for arbitrary substrings and does not replace primary keys, unique indexes, or B-tree indexes used for JOINs.

## 8. FULLTEXT Indexes in MySQL

MySQL supports `FULLTEXT` indexes on `CHAR`, `VARCHAR`, and `TEXT` columns. InnoDB has supported full-text indexes since MySQL 5.6.4; MyISAM also supports FULLTEXT. For new applications, InnoDB is usually the default choice due to transactions and crash recovery, though you should verify the deployed version and engine.

Example of creating an articles table with a composite FULLTEXT index on title and body:

```sql
CREATE TABLE articles (
    article_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    title VARCHAR(250) NOT NULL,
    body MEDIUMTEXT NOT NULL,
    published_at DATETIME NOT NULL,
    PRIMARY KEY (article_id),
    FULLTEXT KEY ft_articles_title_body (title, body),
    KEY idx_articles_published (published_at)
) ENGINE=InnoDB
  DEFAULT CHARACTER SET utf8mb4;
```

If the table already exists:

```sql
ALTER TABLE articles
ADD FULLTEXT INDEX ft_articles_title_body (title, body);
```

A composite FULLTEXT index allows searching across the indexed column set. The column list in `MATCH()` must correspond to the column list of the FULLTEXT index being used. If you need to search `title` alone, consider creating a separate FULLTEXT index on `title` rather than assuming an index on `(title, body)` can substitute for every subset index.

## 9. MATCH() AGAINST(): Full-Text Queries

Basic syntax:

```sql
MATCH (col1, col2, ...) AGAINST (search_text [search_modifier])
```

Example searching for articles about transaction isolation:

```sql
SELECT
    article_id,
    title,
    MATCH(title, body)
        AGAINST ('transaction isolation') AS relevance
FROM articles
WHERE MATCH(title, body)
      AGAINST ('transaction isolation')
ORDER BY relevance DESC;
```

`MATCH() AGAINST()` returns a relevance score; the condition in `WHERE` filters matching rows, and `ORDER BY relevance DESC` prioritizes rows with higher scores. This score is an internal metric of the full-text engine, not a probability of content correctness or user satisfaction.

`MATCH()` must use the exact columns declared in the corresponding FULLTEXT index. If no matching index exists, the query may raise an error instead of falling back to scanning strings like LIKE.

## 10. Natural Language Mode

If no modifier is specified, MySQL uses `IN NATURAL LANGUAGE MODE`:

```sql
SELECT
    article_id,
    title,
    MATCH(title, body)
        AGAINST ('transaction isolation' IN NATURAL LANGUAGE MODE) AS relevance
FROM articles
WHERE MATCH(title, body)
      AGAINST ('transaction isolation' IN NATURAL LANGUAGE MODE)
ORDER BY relevance DESC;
```

Natural language mode treats the input as a natural language query consisting of search words. MySQL finds documents containing matching tokens and computes relevance based on statistics of the document set/index.

This mode is suitable for general content search boxes. However, it should not be interpreted as a semantic understanding engine: MySQL does not automatically understand intent, synonyms, or conceptual relationships like a specialized search/AI system.

## 11. Boolean Mode

Boolean mode allows using operators to control how tokens are combined:

```sql
SELECT
    article_id,
    title,
    MATCH(title, body)
        AGAINST ('+transaction +isolation -oracle' IN BOOLEAN MODE) AS relevance
FROM articles
WHERE MATCH(title, body)
      AGAINST ('+transaction +isolation -oracle' IN BOOLEAN MODE)
ORDER BY relevance DESC;
```

Common operators:

| Operator | General Meaning |
| --- | --- |
| `+word` | Word must be present |
| `-word` | Exclude documents containing this word |
| `word` | Optional word; may contribute to relevance |
| `"phrase"` | Search for a phrase in token order |
| `word*` | Token prefix; the `*` is placed at the end of the word |
| `>word`, `<word` | Increase/decrease the word's contribution to relevance |
| `( ... )` | Group expressions to control combination |

Example phrase search:

```sql
SELECT article_id, title
FROM articles
WHERE MATCH(title, body)
      AGAINST ('"transaction isolation"' IN BOOLEAN MODE);
```

Boolean mode is suitable when the product needs required words, excluded words, or token prefixes. MySQL's boolean syntax has its own rules; do not assume every operator from Elasticsearch/Lucene has the same meaning.

## 12. LIKE vs. FULLTEXT: Direct Comparison

| Criterion | `LIKE` | `FULLTEXT` |
| --- | --- | --- |
| Matching unit | Character string by pattern | Tokens/terms extracted by the parser |
| Mid-word substring search | Possible via `%term%` | Not the goal of default FULLTEXT |
| Prefix search | `term%` can use B-tree | Boolean mode has token prefix `term*` |
| Stopwords | Does not automatically exclude stopwords | Can skip stopwords based on config/parser |
| Very short words | Still matches if pattern fits | May be excluded by min token size |
| Relevance score | Not built-in | Has relevance score |
| Phrase search | Literal string match via pattern | Token-based boolean phrase search |
| Index | B-tree can support equality/range/prefix | Requires FULLTEXT index |
| Result | Rows matching/not matching pattern | Rows with matching tokens, rankable |
| Use case | Codes, prefixes, substrings, simple patterns | Articles, descriptions, documents, multi-word content |

Neither mechanism is better in every case. Choose based on the search semantics the application needs to provide.

## 13. Tokenization: How Does MySQL Split Words?

The full-text parser analyzes text into tokens before indexing and searching. The default parser uses word-splitting rules based on delimiter characters. Punctuation and whitespace typically create token boundaries; certain word characters depend on the charset/parser.

Example content:

```text
MySQL transaction isolation protects concurrent updates.
```

The parser may index tokens such as `mysql`, `transaction`, `isolation`, `protects`, `concurrent`, `updates`, after applying length and stopword rules.

Because of tokenization, FULLTEXT searches for extracted words rather than arbitrary character substrings. Searching for `trans` may not find the token `transaction` in natural language mode. Boolean prefix `trans*` is a different mechanism that searches for tokens starting with that prefix when syntax and index allow.

## 14. Stopwords and Minimum Token Length

Stopwords are words excluded from the full-text index or ignored during search, usually because they appear too frequently and provide little help in distinguishing documents. Additionally, the parser enforces minimum/maximum token length limits.

Common configuration variables:

| Engine | Minimum Token Limit | Maximum Token Limit |
| --- | --- | --- |
| InnoDB | `innodb_ft_min_token_size` (typically defaults to 3) | `innodb_ft_max_token_size` (typically defaults to 84) |
| MyISAM | `ft_min_word_len` (typically defaults to 4) | `ft_max_word_len` (typically defaults to 84) |

Actual values should be checked on the server:

```sql
SHOW VARIABLES LIKE 'innodb_ft_min_token_size';
SHOW VARIABLES LIKE 'innodb_ft_max_token_size';
SHOW VARIABLES LIKE 'ft_min_word_len';
SHOW VARIABLES LIKE 'ft_max_word_len';
```

If users need to search for short words like `SQL`, `C`, `R`, or short codes, check token size and stopwords. Changing full-text configuration typically requires restarting the server and rebuilding the FULLTEXT index so content is indexed under the new rules.

Do not reduce min token size arbitrarily: the index can grow significantly larger and contain many low-value tokens. Test the search workload and plan operational index rebuilds before changing it.

## 15. How Do Stopwords Affect Results?

If a word is on the stopword list, the user can enter it, but full-text search does not process it as an ordinary token. Therefore, searching for a very common word or a word configured for exclusion may not return expected results.

InnoDB has its own stopword configuration, including a default list and the ability to use a custom stopword table. MyISAM has its own stopword configuration mechanism. Do not assume both engines share the same configuration or results.

When a domain has common yet important terminology—such as `order`, `status`, `select`, or short product names—check the stopword list and consider custom configuration. Changing stopwords also requires rebuilding the index so previously excluded tokens are added to the index.

## 16. Vietnamese Search and Default Parser Limitations

Vietnamese search needs to be tested with real data. Vietnamese has many compound words consisting of syllables separated by spaces; the default parser may process each part along token boundaries rather than recognizing a compound word according to a linguistic dictionary.

For example, the phrase `cơ sở dữ liệu` (database) may be parsed into separate tokens. This may work for syllable-level matching, but it is not equivalent to a Vietnamese word segmenter that understands vocabulary, diacritics, variants, or synonyms.

Points to check:

- Should accented and unaccented data be treated as equivalent?
- Do users search for the whole phrase or individual words/syllables?
- Are short words excluded by min token size or stopwords?
- Does the collation handle case and accents as required?
- Are stemming, synonyms, typo tolerance, or domain-specific ranking needed?

MySQL includes an ngram parser, commonly used for languages without space-separated word boundaries such as Chinese, Japanese, and Korean. Ngram splits text into character sequences of configurable length; it does not automatically become a Vietnamese semantic analyzer. If the product needs Vietnamese word segmentation, spell correction, synonyms, or complex ranking, consider a dedicated analysis pipeline or specialized search engine.

## 17. One Example: Same Data, Two Semantics

Suppose `articles.body` contains:

```text
The database transaction protects the account balance.
```

Compare:

```sql
-- Find the exact character string "trans" at any position.
SELECT article_id, title
FROM articles
WHERE body LIKE '%trans%';

-- Find the token "transaction" in the full-text index.
SELECT article_id, title
FROM articles
WHERE MATCH(title, body)
      AGAINST ('transaction' IN NATURAL LANGUAGE MODE);

-- Find tokens with the prefix "trans" in boolean mode.
SELECT article_id, title
FROM articles
WHERE MATCH(title, body)
      AGAINST ('trans*' IN BOOLEAN MODE);
```

The three queries can return different results:

- `LIKE '%trans%'` matches `transaction` because it contains the character sequence `trans`.
- Natural language search for `transaction` searches for the token `transaction`, and does not by default match every word with prefix `trans`.
- Boolean `trans*` searches for tokens starting with `trans` if those tokens are indexed and not excluded by configuration.

This is why the search contract must be clearly defined before choosing the SQL approach.

## 18. Combining Relational Conditions with FULLTEXT

Applications often need to filter results by tenant, status, or time alongside keywords:

```sql
SELECT
    article_id,
    title,
    MATCH(title, body)
        AGAINST ('mysql indexing' IN NATURAL LANGUAGE MODE) AS relevance
FROM articles
WHERE MATCH(title, body)
      AGAINST ('mysql indexing' IN NATURAL LANGUAGE MODE)
  AND published_at >= '2026-01-01'
ORDER BY relevance DESC, published_at DESC
LIMIT 20;
```

FULLTEXT searches content by tokens; relational conditions filter the result scope by date/status/tenant. Designing B-tree indexes for relational filters still matters, though the optimizer chooses a combined plan based on cost. Do not assume a single index can solve the entire query.

For multi-tenant data, the `tenant_id` condition must be enforced as an explicit security/authorization constraint, not left to keyword filtering alone. Full-text search does not replace authorization.

## 19. Inspecting Execution Plans and Cost

Use `EXPLAIN` to see how MySQL intends to execute the query:

```sql
EXPLAIN
SELECT article_id, title
FROM articles
WHERE MATCH(title, body)
      AGAINST ('transaction isolation' IN NATURAL LANGUAGE MODE);
```

Compare with a `LIKE` query:

```sql
EXPLAIN
SELECT article_id, title
FROM articles
WHERE body LIKE '%transaction%';
```

Observe access type, key, estimated rows, and Extra. FULLTEXT requires an appropriate index; `LIKE` with a leading wildcard usually has to examine many rows. Actual results also depend on document count, token distribution, keyword frequency, and additional filter conditions.

When supported by the MySQL version, use `EXPLAIN ANALYZE` for SELECT queries to inspect actual rows and iterator timing. Run benchmarks with representative data and parameters; a common keyword can match far more documents than a rare keyword.

## 20. When Is LIKE Still the Right Choice?

`LIKE` remains appropriate when:

- The table is small and queries are infrequent.
- Searching identifiers, product codes, or fixed-structure strings.
- Searching prefixes for autocomplete (`prefix%`) with a B-tree index.
- Needing literal substring matching in the middle of a string (`%substring%`).
- Needing simple character pattern matching rather than natural language words.
- Results only need true/false matching without relevance ranking.

Example searching for emails ending with a domain:

```sql
SELECT user_id, email
FROM users
WHERE email LIKE '%@example.com';
```

This pattern is character-based string matching; FULLTEXT is not the right tool for checking email suffixes. If high performance is needed for suffixes or substrings, consider a normalized column, reverse index, or specialized search structure after measuring the workload.

## 21. When Is FULLTEXT Appropriate?

FULLTEXT is usually appropriate when:

- Searching keywords in long content such as articles, descriptions, documents, or comments.
- Results need to be ordered by relevance.
- Searching multiple tokens or phrases.
- Data is text-structured and the parser can tokenize it appropriately.
- Wanting integrated search directly inside MySQL without deploying a separate search system.

FULLTEXT may fall short when you need:

- Arbitrary mid-token substring matching.
- Fuzzy matching, spell correction, or advanced typo tolerance.
- Synonyms, stemming, or domain-specific semantic search.
- Complex language analysis unsupported by the default parser.
- Custom ranking combining multiple signals such as freshness, popularity, access permissions, and personalization.

In those cases, MySQL can remain the source of truth for transactional data while a dedicated search engine handles indexing/ranking; synchronization, eventual consistency, and document deletion/update handling must be designed accordingly.

## 22. Common Misconceptions

| Misconception / Error | Reality | How to Handle |
| --- | --- | --- |
| `LIKE '%word%'` is full-text search | It is character pattern matching | Use FULLTEXT when token matching and relevance are needed |
| FULLTEXT finds every substring | FULLTEXT searches tokens extracted by the parser | Use LIKE/ngram/search engine for arbitrary substrings |
| `LIKE 'prefix%'` and `LIKE '%prefix%'` behave the same for indexes | Prefix can use B-tree range; leading wildcard usually cannot | Check EXPLAIN |
| FULLTEXT understands sentence meaning | The parser mainly analyzes tokens and statistical relevance | Use a search engine/semantic layer if semantic understanding is needed |
| Every word is indexed | Stopwords and token-size limits can exclude words | Check configuration and indexed data |
| FULLTEXT works on any column | Only supports CHAR, VARCHAR, TEXT and requires a FULLTEXT index | Design columns/indexes with the right types |
| FULLTEXT index replaces B-tree | The two indexes serve different access patterns | Maintain B-tree indexes for JOIN/filter/range as appropriate |
| Boolean mode uses Lucene syntax | MySQL has its own boolean syntax | Follow MySQL operators strictly |
| Default Vietnamese search always handles compound words accurately | The parser does not necessarily segment Vietnamese dictionary compounds | Test tokenization or use an appropriate parser/search service |
| MATCH() can arbitrarily use a subset of a composite index's columns | MATCH columns must correspond to a FULLTEXT index | Create appropriate indexes for each column set to be searched |

## 23. Process for Selecting and Implementing a Search Mechanism

1. Define semantics: substring, prefix, token, phrase, or relevance.
2. Collect real sample queries and expected user results.
3. Check charset/collation and data language.
4. If using LIKE, determine whether patterns have leading wildcards and whether B-tree can help.
5. If using FULLTEXT, choose `CHAR`/`VARCHAR`/`TEXT` columns and create a FULLTEXT index.
6. Check parser, stopwords, min/max token size, and important short words.
7. Choose natural language or boolean mode based on the search experience.
8. Combine tenant/status/time filters and enforce authorization.
9. Use `EXPLAIN`/`EXPLAIN ANALYZE` and benchmark with both common and rare keywords.
10. Measure latency, result counts, relevance, and index update overhead.
11. Test inserts/updates/deletes, index rebuilds, and configuration deployment procedures.
12. If language/ranking requirements exceed FULLTEXT capabilities, consider a dedicated search engine.

## 24. Practice Exercises

1. Create an `articles` table with `title`, `body`, and a composite FULLTEXT index.
2. Insert at least 20 articles containing common keywords, rare keywords, short words, and phrases.
3. Compare `LIKE '%transaction%'` with FULLTEXT natural language mode.
4. Compare `LIKE 'trans%'` with boolean prefix `trans*`.
5. Search for a phrase using `LIKE` and boolean phrase search; note cases where results differ.
6. Run `EXPLAIN` on `LIKE 'prefix%'` and `LIKE '%prefix%'`; compare access paths.
7. Run `EXPLAIN` on `MATCH() AGAINST()` and confirm the FULLTEXT index is used.
8. Test boolean operators `+`, `-`, `>`, `<`, `*`, and parentheses grouping.
9. Inspect min token size and stopwords; try searching for `SQL`, `C`, or very common words.
10. Test accented/unaccented Vietnamese queries and multi-syllable phrases; note parser limitations.
11. Combine FULLTEXT with `tenant_id` and `published_at` filters and relevance sorting.
12. Write a recommendation choosing LIKE, FULLTEXT, or a search engine for three features: autocomplete, product code search, and article search.

## 25. Key Takeaways

`LIKE` matches strings by pattern: `%` matches zero or more characters, and `_` matches a single character. A B-tree can support patterns with a fixed prefix such as `abc%`, whereas patterns starting with `%` like `%abc%` usually cannot use a range lookup. LIKE does not tokenize words and does not rank relevance; results also depend on collation.

FULLTEXT indexes tokens in `CHAR`, `VARCHAR`, or `TEXT` columns and is queried via `MATCH(...) AGAINST(...)`. Natural language mode is suitable for keyword content search and relevance; boolean mode supports required/excluded words, phrases, and token prefixes. Parser, stopwords, min/max token size, and language affect results; short or very common words may be excluded. FULLTEXT does not match arbitrary substrings and is not semantic search. Choose based on semantics: LIKE for character/prefix/substring patterns; FULLTEXT for token search in text; and a dedicated search engine when advanced language analysis, typo handling, synonyms, or complex ranking is required.
