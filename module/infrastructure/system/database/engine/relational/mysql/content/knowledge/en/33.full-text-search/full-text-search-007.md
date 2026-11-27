# Default Parser, ngram Parser, and Usage Conditions

MySQL Full-Text Search does not match text character by character like `LIKE '%text%'`. When creating a FULLTEXT index, MySQL uses a parser to split content into tokens, drops tokens that are not indexed according to configuration rules, and stores the remaining tokens to serve `MATCH() AGAINST()`. The parser therefore determines which units text is broken into and directly affects search results.

MySQL includes a default word-based parser and an ngram parser based on contiguous character sequences. The default parser suits text where words are clearly separated by spaces or delimiters. The ngram parser is generally better suited for Chinese, Japanese, Korean, and text without explicit word boundaries. Because the two parsers generate tokens differently, the same query can return different result sets.

In the **DATABASE_MYSQL** module, choosing a parser is an index design decision. This lesson covers how the default parser and ngram parser generate tokens, token length and stopword limits, creating FULLTEXT indexes, querying, and selection criteria based on language, data, and search requirements.

## 1. Full-Text Search and the Role of the Parser

Full-Text Search indexes text content for searching by words or tokens. Indexed columns must be of type `CHAR`, `VARCHAR`, or `TEXT`. Both InnoDB and MyISAM support FULLTEXT indexes, though certain token and stopword settings differ by storage engine.

Example articles table:

```sql
CREATE TABLE articles (
    article_id BIGINT UNSIGNED NOT NULL,
    title VARCHAR(255) NOT NULL,
    body TEXT NOT NULL,
    PRIMARY KEY (article_id)
) ENGINE = InnoDB;
```

Create a FULLTEXT index on `body`:

```sql
CREATE FULLTEXT INDEX ft_articles_body
ON articles (body);
```

Query:

```sql
SELECT
    article_id,
    title,
    MATCH(body) AGAINST (
        'database index'
        IN NATURAL LANGUAGE MODE
    ) AS relevance
FROM articles
WHERE MATCH(body) AGAINST (
    'database index'
    IN NATURAL LANGUAGE MODE
)
ORDER BY relevance DESC;
```

During index creation, the parser reads `body` content and generates tokens. When `MATCH() AGAINST()` runs, MySQL uses the parser bound to that FULLTEXT index to process the search string in the same manner.

The parser affects more than speed. It defines the search system's concept of a "word." If the parser does not generate tokens matching how users enter queries, the FULLTEXT index may fail to find expected content even though the string exists in the column.

## 2. Default Parser: Splitting Text into Words

MySQL's default parser identifies words based on word boundaries, typically separated by whitespace and punctuation. The resulting tokens are further subject to rules on minimum length, maximum length, and stopwords.

Example text:

```text
MySQL provides reliable database indexing.
A database index can improve query performance.
```

The default parser may produce tokens such as:

```text
mysql
provides
reliable
database
indexing
a
can
improve
query
performance
```

The list above only illustrates the idea. Which tokens are actually retained or discarded still depends on stopwords, min/max token size, charset, and server configuration.

### 2.1. Word Boundaries and Delimiters

The default parser is suitable when data has relatively clear word boundaries—for example, English and many languages written in the Latin alphabet that use spaces to separate words.

Text:

```text
relational database
database-engine
query, index, transaction
```

Delimiters can cause the parser to split text into separate tokens. Therefore, searching for phrases, hyphenated compound words, or word fragments should be tested against real data.

The default FULLTEXT parser is not a complete natural-language tokenizer. It does not understand semantics, automatically infer synonyms, or guarantee recognition of all morphological variants of a word. If search requirements call for stemming, synonyms, fuzzy matching, or specialized linguistic segmentation, add application-layer processing or use a dedicated search engine.

### 2.2. Token Length Limits

Tokens that are too short or too long may be skipped. Default values depend on the storage engine:

| Storage Engine | Default Minimum Length | Default Maximum Length | Configuration Variables |
|---|---:|---:|---|
| InnoDB, default parser | 3 characters | 84 characters | innodb_ft_min_token_size, innodb_ft_max_token_size |
| MyISAM, default parser | 4 characters | 84 characters | ft_min_word_len, ft_max_word_len |

For example, with default InnoDB settings, a token like `id` is shorter than the minimum threshold and will not be indexed. With MyISAM, the default threshold is one character higher.

This affects identifiers, abbreviations, and technical terms. Tokens such as `C`, `Go`, `UI`, `SQL`, or `NoSQL` may not be handled as desired depending on actual length and spelling. Never assume every word visible in a column is searchable with FULLTEXT.

### 2.3. Stopwords

Stopwords are words excluded from the FULLTEXT index because they occur too frequently and add little value in distinguishing results. In English, this typically includes words like `the`, `a`, `is`, `of`.

MySQL provides a default stopword list; InnoDB and MyISAM have separate stopword configuration mechanisms. With InnoDB you can control enabling/disabling stopwords and use custom stopword tables. MyISAM has a configuration variable pointing to a stopword file.

Example text:

```text
the database is reliable
database indexing improves performance
```

If `the` or `is` is on the stopword list, they do not become searchable tokens. Searching for these words alone generally does not yield results like searching an ordinary term.

Stopwords are helpful for reducing noise and index size, but can surprise teams if an important business term collides with a stopword. Applications searching product codes, acronyms, or short phrases should review the stopword list before deployment.

### 2.4. Impact of Charset and Collation

The parser operates on column text, so charset and collation are part of search design. Collation affects how text is compared—for instance, case-sensitive vs. case-insensitive and accent-sensitive vs. accent-insensitive.

For Vietnamese data, test accented and unaccented cases, uppercase and lowercase, as well as the active collation. Do not assume the default parser automatically normalizes all Vietnamese variants into the same token.

## 3. ngram Parser: Splitting Text into Contiguous Character Sequences

The ngram parser splits text into fixed-length character groups of length n, called n-grams. Instead of relying on spaces to identify word boundaries, the parser creates tokens from contiguous character sequences.

For example, with `ngram_token_size = 2`, the string:

```text
database
```

is split into illustrative bigrams:

```text
da
at
ta
ab
ba
as
se
```

Each token consists of two adjacent characters. With `ngram_token_size = 3`, the string is split into trigrams:

```text
dat
ata
tab
aba
bas
ase
```

The ngram parser is especially useful for languages where words are not separated by spaces or word boundaries cannot be trivially inferred from spaces, such as Chinese, Japanese, and Korean.

### 3.1. ngram_token_size

The `ngram_token_size` variable specifies the number of characters in each token:

| Setting | Result for string "abcdef" |
|---|---|
| 1 | a, b, c, d, e, f |
| 2 | ab, bc, cd, de, ef |
| 3 | abc, bcd, cde, def |
| 4 | abcd, bcde, cdef |

In MySQL, `ngram_token_size` defaults to 2 and accepts values from 1 to 10. It is a server-level configuration variable set only at startup; it cannot be changed per index or modified dynamically within a session. Choose a value suited to the language and common query lengths.

- Smaller n creates more tokens, which can increase index size and match counts.
- Larger n creates fewer tokens, typically making short queries harder to match and reducing the ability to find short strings.
- Too small an n easily produces overly common tokens, increasing noise.
- Too large an n can miss queries shorter than the token length.

If a search term is shorter than `ngram_token_size`, the query may fail to generate any matching token and return no expected results. Check the shortest keywords users will actually enter.

### 3.2. Example with Chinese Text

Suppose the content contains the Chinese string:

```text
数据库索引
```

With `ngram_token_size = 2`, illustrative bigrams are:

```text
数据
据库
库索
索引
```

When a user searches for a substring of sufficient length, the parser can generate corresponding bigrams to match in the FULLTEXT index. This mechanism enables searching without needing to know exact word boundaries.

Other examples in Japanese or Korean similarly generate n-gram sequences under the same rules. However, character-based tokenization does not mean MySQL understands word or phrase meaning. Results depend on `ngram_token_size`, stopwords, and how queries are converted into tokens.

### 3.3. Whitespace and Punctuation

The ngram parser processes strings into n-grams and strips whitespace from tokens. This differs from the default parser, which relies on word boundaries. Punctuation and special characters can alter the actual token sequence, so test with data containing hyphens, periods, identifiers, URLs, and multi-byte characters.

In particular, never calculate token counts by counting UTF-8 bytes. `ngram_token_size` refers to characters as defined by the parser, not byte length. A single Unicode character can occupy multiple bytes when stored in UTF-8.

### 3.4. Stopwords in the ngram Parser

The ngram parser can still apply stopword filtering. Stopwords can cause certain n-grams to be excluded from the index, so not every generated bigram/trigram is guaranteed to be stored.

When searching CJK text or short character sequences, check the interaction between `ngram_token_size` and the stopword list. A stopword configuration designed for English word search may not fit n-grams, because short strings can appear inside many different words.

Do not disable stopwords by default. Evaluate the ratio of common tokens, index size, and result accuracy on a representative corpus before making changes.

## 4. Creating a FULLTEXT Index with the Default Parser

If no parser is specified, MySQL uses the default parser. Example:

```sql
CREATE TABLE documents (
    document_id BIGINT UNSIGNED NOT NULL,
    title VARCHAR(255) NOT NULL,
    content MEDIUMTEXT NOT NULL,
    PRIMARY KEY (document_id),
    FULLTEXT KEY ft_documents_title_content (title, content)
) ENGINE = InnoDB;
```

The index on `title` and `content` is a composite FULLTEXT index. `MATCH` queries must specify the exact same column set:

```sql
SELECT
    document_id,
    MATCH(title, content) AGAINST (
        'mysql full text'
        IN NATURAL LANGUAGE MODE
    ) AS score
FROM documents
WHERE MATCH(title, content) AGAINST (
    'mysql full text'
    IN NATURAL LANGUAGE MODE
)
ORDER BY score DESC;
```

If you want to search `title` or `content` separately with independent access paths, consider creating separate FULLTEXT indexes per column. Design indexes to match the exact `MATCH` patterns used by the application.

### 4.1. Creating an Index After the Table Exists

```sql
ALTER TABLE documents
ADD FULLTEXT INDEX ft_documents_content (content);
```

When adding a FULLTEXT index, MySQL parses existing data and builds tokens according to the parser/configuration active at index creation time. On large tables, this operation can consume significant CPU, I/O, temporary space, and migration time. Plan time and system load before deploying.

### 4.2. MATCH() AGAINST() and Search Modes

Natural language mode is the default when no mode is specified:

```sql
SELECT document_id
FROM documents
WHERE MATCH(content)
AGAINST ('transaction isolation');
```

Boolean mode allows expressing required, excluded, or prefix conditions:

```sql
SELECT document_id
FROM documents
WHERE MATCH(content)
AGAINST ('+transaction -replication' IN BOOLEAN MODE);
```

Query expansion can broaden searches based on initially matching documents:

```sql
SELECT document_id
FROM documents
WHERE MATCH(content)
AGAINST ('database' WITH QUERY EXPANSION);
```

These modes share the same FULLTEXT index while interpreting the query string differently. The parser still determines how the search string is tokenized. Query expansion can raise recall, yet also broadens results and adds noise; enable it only when suited to the search experience.

## 5. Creating a FULLTEXT Index with the ngram Parser

To use the ngram parser, specify `WITH PARSER ngram` when creating the FULLTEXT index:

```sql
CREATE TABLE cjk_articles (
    article_id BIGINT UNSIGNED NOT NULL,
    title VARCHAR(255) NOT NULL,
    content MEDIUMTEXT NOT NULL,
    PRIMARY KEY (article_id),
    FULLTEXT KEY ft_cjk_content (content) WITH PARSER ngram
) ENGINE = InnoDB;
```

Or add the index to an existing table:

```sql
ALTER TABLE cjk_articles
ADD FULLTEXT INDEX ft_cjk_title (title) WITH PARSER ngram;
```

The ngram parser is built into MySQL. You do not need to write a custom tokenizer to use `WITH PARSER ngram`, though you should verify parser support on your deployed server version.

Queries use `MATCH() AGAINST()` just like any standard FULLTEXT index:

```sql
SELECT
    article_id,
    MATCH(content) AGAINST (
        '数据库'
        IN NATURAL LANGUAGE MODE
    ) AS relevance
FROM cjk_articles
WHERE MATCH(content) AGAINST (
    '数据库'
    IN NATURAL LANGUAGE MODE
)
ORDER BY relevance DESC;
```

MySQL uses the ngram parser attached to the index to parse the search string. You do not need to write manual bigram-splitting functions inside `MATCH`.

### 5.1. Checking ngram_token_size

Check current configuration:

```sql
SHOW VARIABLES LIKE 'ngram_token_size';
```

With the default value of 2, the ngram parser produces bigrams. With real data and queries, test a mix of short keywords, long keywords, whitespace, and punctuation to verify tokenization meets requirements.

`ngram_token_size` is configured at the server level at startup. When changing it, restart the instance with the new value, roll out consistent settings across related nodes, and rebuild FULLTEXT indexes so stored tokens match the new rule. Never change the parameter on one server and keep using old indexes without verification.

### 5.2. Comparison Example: Default Parser vs. ngram

Suppose the same content is stored:

```text
数据库索引优化
```

The default parser relies on word boundaries and may fail to create useful tokens without delimiters. The ngram parser with `ngram_token_size = 2` can generate:

```text
数据
据库
库索
索引
引优
优化
```

If a user searches for the substring `索引`, the ngram parser can generate the matching bigram. This is why ngram fits this type of text much better.

Ngram is not always better than the default parser. On clearly space-delimited English text, bigrams create many overlapping tokens like `da`, `at`, `ta`, enlarging the index and potentially increasing irrelevant matches. Choose the parser based on language and query patterns, not on which parser produces more tokens.

## 6. How the Parser Affects Search Results

On the same text column, the two parsers can build different indexes:

| Characteristic | Default Parser | ngram Parser |
|---|---|---|
| Token unit | Word | Contiguous n-character sequence |
| Primary boundary | Whitespace, delimiters | n-character sliding window |
| Length setting | Engine min/max token size | ngram_token_size |
| Suitable languages | Text with clear word boundaries | CJK and text without clear word boundaries |
| Short keywords | May be dropped by min token size | May be shorter than n characters |
| Index size | Depends on word count and stopwords | Can grow due to many overlapping n-grams |
| Substring search | Not the primary goal | Can support at the n-gram level |

### 6.1. Tokenization and Phrase Search

In natural language mode, MySQL searches by tokens and computes relevance. In boolean mode, operators can require or exclude tokens. For phrase search, enclose the phrase in double quotes in boolean mode:

```sql
SELECT document_id
FROM documents
WHERE MATCH(content)
AGAINST ('"database index"' IN BOOLEAN MODE);
```

With the ngram parser, the search phrase is also converted into n-grams per parser configuration. Thus, changing `ngram_token_size` can alter how phrases are split and how the index matches phrases.

Do not interpret phrase search as an exact byte-string check in the column. FULLTEXT still applies the token semantics of the parser and search mode.

### 6.2. Too-Short Keywords

With the default parser, tokens shorter than the minimum threshold may not exist in the index. With the ngram parser, search strings shorter than `ngram_token_size` do not generate enough tokens to match.

For example, if `ngram_token_size = 2`, a single-character query may return no results. If the product needs to search short codes, single characters, or prefixes, consider a B-tree index, prefix `LIKE`, a dedicated code column, or another search mechanism.

### 6.3. Token Search Is Not Arbitrary Substring Search

FULLTEXT is designed to search tokens, not to replace every form of substring search. The ngram parser can make substring matching more effective at the n-gram level, yet it still depends on `n`, stopwords, and `MATCH` semantics.

If the requirement is to find any arbitrary string inside a column, including very short fragments, `LIKE '%abc%'` has different semantics. `LIKE` queries with leading wildcards typically cannot use standard B-tree indexes. Depending on scale, you may need specialized indexes, generated search keys, or a dedicated search system.

## 7. Choosing a Parser by Language and Data

### 7.1. When to Use the Default Parser

Choose the default parser when:

- Text has clear word boundaries using spaces or delimiters.
- Users search by words, phrases, and relevance.
- Min/max token size aligns with term lengths.
- The stopword list is acceptable or customizable.
- You want word-level indexing instead of every contiguous character sequence.

Examples: English technical articles, English product descriptions, space-delimited documentation.

### 7.2. When to Use the ngram Parser

Consider the ngram parser when:

- Text uses writing systems without spaces separating words, such as Chinese, Japanese, or Korean.
- Users frequently search for substrings within text.
- You need to search content that the default parser does not split into useful tokens.
- You can control and test `ngram_token_size`.
- You accept the index overhead and broader result sets caused by overlapping tokens.

The ngram parser does not perform linguistic analysis, identify compound words automatically, or know the meaning of character sequences. It simply generates n-grams at the configured size.

### 7.3. Special Notes for Vietnamese

Vietnamese uses spaces between syllables, yet a single word can consist of multiple syllables. The default parser may index each syllable as a separate token. This can sometimes make phrase or compound-word queries behave differently from business expectations.

The ngram parser can be useful if the product needs character substring matching, but it is not a Vietnamese word segmenter. For instance, n-grams can produce many tokens across adjacent characters without knowing compound word boundaries or phrase meaning. Therefore, do not switch all Vietnamese search to ngram solely because Vietnamese has multi-syllable words.

For Vietnamese search, clarify requirements upfront:

- Search individual syllables or multi-syllable phrases?
- Need unaccented queries to match accented data?
- Need compound word matching, variants, or synonyms?
- Do users typically type full words or character fragments?
- Need relevance ranking across title and body?

You can use the default parser combined with phrase search and an appropriate collation; if word segmentation is needed, normalize/tokenize in the application layer before writing to a dedicated search column. If unaccented search, synonyms, or complex ranking are required, design additional search fields or use a dedicated search engine. Always test with a real Vietnamese query suite.

### 7.4. Decision Matrix

| Data and Requirement | Initial Choice | Must Verify |
|---|---|---|
| English, word-based search | Default parser | Stopwords, min/max token |
| Chinese, Japanese, Korean | ngram parser | ngram_token_size, stopwords |
| Short codes and symbols | Do not default to FULLTEXT | Token length, B-tree, or separate column |
| Vietnamese, syllable-level search | Default parser may fit | Phrases, accents, collation |
| Vietnamese, substring search | Test ngram or alternative | Noisy results, length n |
| Synonyms, stemming, fuzzy search | Default/ngram insufficient | Application processing or search engine |

## 8. Token Size and Stopword Configuration

Token size settings directly affect FULLTEXT index contents. Common variables:

| Variable | Scope | Common Default |
|---|---|---:|
| innodb_ft_min_token_size | InnoDB, default parser | 3 |
| innodb_ft_max_token_size | InnoDB, default parser | 84 |
| ft_min_word_len | MyISAM, default parser | 4 |
| ft_max_word_len | MyISAM, default parser | 84 |
| ngram_token_size | ngram parser | 2 |

These values can depend on server version and configuration. Inspect directly on the instance:

```sql
SHOW VARIABLES LIKE 'innodb_ft_min_token_size';
SHOW VARIABLES LIKE 'innodb_ft_max_token_size';
SHOW VARIABLES LIKE 'ft_min_word_len';
SHOW VARIABLES LIKE 'ft_max_word_len';
SHOW VARIABLES LIKE 'ngram_token_size';
```

### 8.1. Changing Token Size

When changing min/max token size or `ngram_token_size`, ensure FULLTEXT indexes are rebuilt under the new configuration. Tokens dropped when the old index was built do not automatically appear simply because a configuration variable changed.

General deployment workflow:

1. Collect common user search keywords and their lengths.
2. Identify the storage engine and parser of each FULLTEXT index.
3. Choose token sizes aligned with language and corpus.
4. Set server configuration per version requirements; restart if variables are startup-only.
5. Drop/recreate or rebuild affected FULLTEXT indexes.
6. Re-run the test query suite and compare results.
7. Measure index size, write duration, and search latency.

Do not change variables in production without estimating rebuild duration and server load impact. In replicated environments, plan consistent configuration across nodes.

### 8.2. Customizing Stopwords

The default stopword list may not match your business domain. For example, a common natural-language word may be an important code or term in your system.

Before customizing:

- List words frequently excluded that business users need to search.
- Identify the storage engine in use.
- Select the stopword mechanism for that engine.
- Check stopword enable/disable variables and custom table/file settings per version.
- Rebuild FULLTEXT indexes after changing the list.
- Measure impact on index size and result noise.

InnoDB provides variables such as `innodb_ft_enable_stopword` and server/user stopword table mechanisms. MyISAM uses `ft_stopword_file`. Do not mistakenly apply one engine's configuration to the other.

## 9. Combining Multiple Columns and Multiple Parsers

A single FULLTEXT index can cover multiple text columns:

```sql
CREATE FULLTEXT INDEX ft_articles_title_body
ON articles (title, body);
```

Queries must `MATCH` the exact column list indexed:

```sql
SELECT article_id
FROM articles
WHERE MATCH(title, body)
AGAINST ('mysql index' IN NATURAL LANGUAGE MODE);
```

If you want to index `title` with the default parser and `content` with ngram, create separate FULLTEXT indexes with their respective parsers:

```sql
CREATE FULLTEXT INDEX ft_articles_title
ON articles (title);

CREATE FULLTEXT INDEX ft_articles_content_ngram
ON articles (content) WITH PARSER ngram;
```

Each `MATCH` expression must use the exact column set corresponding to a FULLTEXT index that the optimizer can use. Having multiple indexes increases storage and update overhead; create them only when real query patterns require them.

## 10. Inspecting Parsers and FULLTEXT Indexes

View table definition:

```sql
SHOW CREATE TABLE articles;
```

View indexes:

```sql
SHOW INDEX FROM articles;
```

View parser settings:

```sql
SHOW VARIABLES LIKE 'ngram_token_size';
SHOW VARIABLES LIKE 'innodb_ft%';
SHOW VARIABLES LIKE 'ft_%';
```

You can also view loaded plugins:

```sql
SHOW PLUGINS;
```

To verify the parser and index work properly, do not rely solely on checking DDL. Build a representative dataset containing short words, long words, punctuation, spaces, stopwords, CJK strings, and queries of varying lengths. Run `MATCH AGAINST()` on that suite and inspect both results and relevance.

### 10.1. Testing FULLTEXT Indexes with Sample Queries

Example testing the default index:

```sql
SELECT article_id
FROM articles
WHERE MATCH(body)
AGAINST ('database' IN NATURAL LANGUAGE MODE);
```

Example testing boolean mode:

```sql
SELECT article_id
FROM articles
WHERE MATCH(body)
AGAINST ('+database -legacy' IN BOOLEAN MODE);
```

Example testing an ngram index:

```sql
SELECT article_id
FROM cjk_articles
WHERE MATCH(content)
AGAINST ('数据库' IN NATURAL LANGUAGE MODE);
```

If results are unexpectedly empty, check token size, stopwords, the parser attached to the index, charset/collation, and the actual indexed content.

## 11. Performance and Operational Cost

The ngram parser often generates many overlapping tokens. For long text, token counts can be substantially higher than with a word-based parser. This increases:

- FULLTEXT index size.
- CPU and I/O when building or updating the index.
- Write overhead during `INSERT`, `UPDATE`, or `DELETE` on text.
- Candidate counts evaluated when tokens are common.
- Rebuild time when changing configuration.

The default parser also has stopword and token-size costs, but typically produces token counts closer to the number of recognized words.

To choose a parser, measure at least:

| Metric | Question to Answer |
|---|---|
| Index size | How much does the index grow when switching to ngram? |
| Build time | Is index creation/rebuild duration acceptable? |
| Write latency | How much extra cost does `INSERT`/`UPDATE` on text add? |
| Query latency | Are common queries faster or slower? |
| Recall | Are expected user documents retrieved? |
| Precision | Are there too many irrelevant results? |
| Relevance | Is result ranking reasonable? |

Do not evaluate a parser using only a handful of queries. Use a realistic query suite covering typos, short words, phrases, special characters, and multi-language queries if supported.

## 12. Common Mistakes

| Mistake | Consequence | How to Handle |
|---|---|---|
| Using default parser for text without word boundaries | Tokens do not reflect searchable content | Test the ngram parser |
| Using ngram for every type of text | Large index, noisy results | Choose parser per language and query pattern |
| Not checking min/max token size | Short or long words are not indexed | Check engine-specific variables |
| Forgetting stopwords | Search terms are dropped | Check and customize stopwords |
| Changing token size without rebuilding index | Index still holds tokens from old config | Rebuild FULLTEXT index |
| Setting ngram_token_size too large | Short queries fail to generate tokens | Pick smaller n and evaluate noise |
| Setting ngram_token_size too small | Too many common tokens | Measure index size and precision |
| Thinking ngram understands word semantics | Results rely purely on character sequences | Use a linguistic tokenizer/search engine when needed |
| Confusing UTF-8 bytes with characters | Wrong n-gram predictions | Test with real Unicode characters |
| MATCH() uses column list not matching FULLTEXT index | Cannot use right index or query errors | Match the exact column set of the index |
| Using FULLTEXT for single-character substrings | No matching tokens exist | Use code columns, B-tree, or another search strategy |
| Not measuring write cost | Search is fast while data updates slow down | Benchmark both read and write workloads |

## 13. Process for Selecting a Parser in Production Systems

1. Identify the language and text type in the column.
2. Collect real queries and determine whether users search by word, phrase, or substring.
3. Choose the default parser as baseline for text with clear word boundaries.
4. Test the ngram parser on a representative corpus if text lacks word boundaries or requires substring matching.
5. Check min/max token size, `ngram_token_size`, and stopwords.
6. Create test indexes and run the benchmark query suite.
7. Measure precision, recall, relevance, index size, and write latency.
8. Pick the configuration meeting product requirements and operational capacity.
9. Plan index rebuilds and consistent deployment across nodes.
10. Monitor search quality after release.

## 14. Pre-Deployment Checklist

**Data and Language:**

- Confirmed charset/collation of text columns.
- Identified whether word boundaries are clear.
- Tested uppercase, lowercase, accents, and Unicode characters.
- Tested short words, long words, identifiers, and punctuation.
- For Vietnamese, tested multi-syllable phrases and unaccented queries.

**Parser and Index:**

- Confirmed InnoDB or MyISAM storage engine.
- Chosen default or ngram parser for each FULLTEXT index.
- Checked min/max token size or `ngram_token_size`.
- Checked stopword list.
- Ensured `MATCH` column lists match FULLTEXT indexes.
- Evaluated number of FULLTEXT indexes and storage footprint.

**Operations:**

- Planned startup configuration and restarts if needed.
- Rebuilt indexes after parser/tokenization/stopword changes.
- Measured index build duration and write load.
- Verified replication and search nodes.
- Prepared regression queries to verify results after migration.
- Monitored index size, query latency, and irrelevant result rate.

## 15. Key Takeaways

- The FULLTEXT parser determines how MySQL splits text into tokens during indexing and when parsing search strings.
- The default parser splits by words and is affected by min/max token size and stopwords.
- InnoDB defaults to `innodb_ft_min_token_size = 3` and `innodb_ft_max_token_size = 84`; MyISAM commonly defaults to `ft_min_word_len = 4` and `ft_max_word_len = 84`.
- The ngram parser splits strings into contiguous n-character groups.
- `ngram_token_size` defaults to 2 and ranges from 1 to 10.
- The ngram parser suits CJK and text without clear word boundaries; it does not understand semantics or perform linguistic word segmentation.
- For Vietnamese, evaluate multi-syllable phrases, diacritics, and search requirements; ngram does not replace a word segmenter.
- Stopwords can cause desired search tokens to be excluded from the index.
- InnoDB and MyISAM have different token size and stopword variables.
- Changing parser or tokenization rules requires rebuilding FULLTEXT indexes.
- `MATCH() AGAINST()` must use the exact column set supported by a FULLTEXT index.
- ngram can increase index size and write cost due to overlapping tokens.
- Use a real query suite to evaluate precision, recall, relevance, latency, and storage.
- If stemming, synonyms, fuzzy search, or deep linguistic analysis are required, consider application-layer processing or a dedicated search engine.

Choose the parser based on the language and search behavior the product needs to support. The default parser fits word search with clear boundaries; ngram fits character-sequence search in languages such as CJK. Once chosen, lock down tokenization rules, rebuild indexes properly, and validate quality with real queries.

## References

- MySQL 8.0 Reference Manual — Full-Text Search Functions: https://dev.mysql.com/doc/refman/8.0/en/fulltext-search.html
- MySQL 8.0 Reference Manual — Full-Text Stopwords: https://dev.mysql.com/doc/refman/8.0/en/fulltext-stopwords.html
- MySQL 8.0 Reference Manual — ngram Full-Text Parser: https://dev.mysql.com/doc/refman/8.0/en/fulltext-search-ngram.html
- MySQL 8.0 Reference Manual — Fine-Tuning MySQL Full-Text Search: https://dev.mysql.com/doc/refman/8.0/en/fulltext-fine-tuning.html
- MySQL 8.0 Reference Manual — InnoDB FULLTEXT Indexes: https://dev.mysql.com/doc/refman/8.0/en/innodb-fulltext-index.html
