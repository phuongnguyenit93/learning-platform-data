# Collation, Vietnamese, and Verifying Tokenization Quality

MySQL Full-Text Search (FTS) can index text and rank results by relevance. However, search results depend heavily on how text is split into tokens, collation character comparison rules, stopword lists, and token length limits. For Vietnamese, these factors are especially critical because a single word can consist of multiple syllables separated by spaces, while tone marks and diacritics can change word meaning.

Two responsibilities must be distinguished:

- **Collation** governs how strings are compared and sorted, including case sensitivity and accent sensitivity in collations that define those properties.
- **Tokenizer/parser** determines which tokens text is split into for insertion into the FULLTEXT index and query processing.

Collation is not a Vietnamese word segmenter. Choosing the right collation controls how diacritics and letter case are compared, yet it does not automatically know that "công nghệ thông tin" (information technology) is a phrase of two multi-syllable words. To achieve high-quality Vietnamese search, verify both MySQL configuration and the application-layer normalization and word-segmentation pipeline.

This lesson falls within the DATABASE_MYSQL scope: designing FULLTEXT indexes for Vietnamese text, choosing character sets/collations, understanding the default parser and ngram parser, managing stopwords/token sizes, building an evaluation dataset, and measuring precision/recall before rolling search out to production.

## 1. Components Determining Full-Text Search Results

A FULLTEXT query does not simply scan for substrings. MySQL processes content through multiple steps:

1. Read the indexed text.
2. The parser splits text into tokens according to its rules.
3. Tokens may be dropped if they are stopwords or fail length bounds.
4. Tokens are stored in the inverted index alongside information on the documents/rows containing them.
5. At query time, the search string is also processed by the parser under the corresponding configuration.
6. MySQL locates matching tokens and computes a relevance score per search mode.
7. The application can filter, sort, paginate, and apply additional business logic.

Components to control:

| Component | Question to Answer |
|---|---|
| Character set | Does it store full Vietnamese and Unicode characters? |
| Collation | Is it case-sensitive and accent-sensitive? |
| Parser | Does it split by words, n-grams, or a custom parser? |
| Token size | What are the shortest/longest tokens admitted into the index? |
| Stopwords | Which words are excluded from the index? |
| Query mode | Natural language, Boolean, or query expansion? |
| Input data | Are Unicode normalization and word segmentation applied consistently? |
| Evaluation | Do results match the benchmark query and labeled document set? |

Successfully creating a FULLTEXT index does not prove Vietnamese search works well. Inspect actual indexed tokens and evaluate results on a representative dataset.

## 2. Character Set and Collation for Vietnamese

### 2.1. Use utf8mb4

Vietnamese text requires storing Unicode characters with diacritics. In modern MySQL, use `utf8mb4` for schemas, tables, and text columns.

Example:

~~~sql
CREATE TABLE article (
    article_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    title VARCHAR(255) NOT NULL,
    body MEDIUMTEXT NOT NULL,
    PRIMARY KEY (article_id)
) ENGINE = InnoDB
  DEFAULT CHARACTER SET utf8mb4
  COLLATE utf8mb4_0900_as_cs;
~~~

`utf8mb4` supports full Unicode within your MySQL version's capabilities. Avoid legacy charsets or charsets covering only a subset of Unicode if content includes Vietnamese, emojis, or multilingual characters.

Check configuration:

~~~sql
SELECT
    @@character_set_server,
    @@collation_server,
    @@character_set_database,
    @@collation_database,
    @@character_set_connection,
    @@collation_connection;
~~~

Check columns:

~~~sql
SHOW FULL COLUMNS FROM article;
~~~

Verify the actual charset/collation of each column. Server defaults do not automatically change the collation of columns created earlier.

### 2.2. Collation Determines Comparison Rules

MySQL collation names typically indicate properties:

- `ai`: accent-insensitive, does not distinguish accents per collation rules.
- `as`: accent-sensitive, distinguishes accents.
- `ci`: case-insensitive, does not distinguish uppercase/lowercase.
- `cs`: case-sensitive, distinguishes uppercase/lowercase.
- `bin`: compares by binary/code-point value per binary collation rules.

Common UCA 9.0 collations in MySQL 8.0:

| Collation | Key Properties |
|---|---|
| utf8mb4_0900_ai_ci | Accent-insensitive and case-insensitive |
| utf8mb4_0900_as_ci | Accent-sensitive, case-insensitive |
| utf8mb4_0900_ai_cs | Accent-insensitive, case-sensitive |
| utf8mb4_0900_as_cs | Accent-sensitive and case-sensitive |

Collation names and availability can vary by version. Check the server directly rather than assuming every environment shares the exact same list:

~~~sql
SHOW COLLATION LIKE 'utf8mb4%';
~~~

To search for language-specific collations:

~~~sql
SHOW COLLATION LIKE 'utf8mb4%vi%';
~~~

Not every MySQL version or distribution ships the same set of locale collations. Select a collation only after verifying it exists on the target server.

### 2.3. Vietnamese Diacritics Can Change Meaning

Consider the strings:

- ma
- má
- mà
- mả
- mã
- mạ

In Vietnamese, tone marks are not mere formatting; they distinguish distinct words and meanings. Under an accent-insensitive collation, accented variants may be treated as equivalent in comparisons. That can boost recall when users omit diacritics, yet also introduces unrelated results.

For content that must distinguish Vietnamese words accurately, start testing with an accent-sensitive collation. If the product wants to support unaccented search, design a deliberate unaccented search strategy and measure false positives.

Never assume `ai_ci` is always better for search or `as_cs` is always better. It is a product decision based on how users enter queries and tolerance for approximate matches.

### 2.4. Collation Does Not Normalize Stored Text

Collation governs comparison; it is not an input data normalization pipeline and does not rewrite stored strings into a single canonical Unicode form.

Unicode can represent an accented character either as a precomposed character or as a base character plus combining mark(s). For example, an accented letter can be represented by one code point or multiple combined code points.

Standardize Unicode normalization in the application layer, typically using NFC before storing and before processing queries. If legacy data already exists, audit and normalize it in a planned manner. Do not rely solely on collation and assume byte sequences already share the same form.

Test both visually equivalent Unicode forms to confirm comparison and FULLTEXT behavior on your active version/collation.

## 3. Distinguishing Collation from Tokenizer

These two concepts answer different questions.

| Example | Collation | Tokenizer |
|---|---|---|
| Are "SQL" and "sql" treated the same? | Affects outcome | Not its primary role |
| Are "ma" and "má" treated the same? | Affects outcome | Not its primary role |
| Which tokens is "công nghệ thông tin" split into? | Does not decide | Decides |
| Does punctuation create token boundaries? | Does not decide | Decides |
| Is "công_nghệ" a single token? | Does not decide | Depends on parser |
| Which words are dropped from the index? | Does not decide | Related to stopwords and FTS config |

Changing collation does not magically create a Vietnamese word segmenter. Changing the parser also does not enforce case or accent comparison rules required by the product.

When diagnosing a word that is not found, check in order:
1. Was the source data stored as valid normalized Unicode?
2. Does the indexed column have the right charset/collation?
3. Does the parser split tokens as expected?
4. Was the token dropped for being too short/long or a stopword?
5. Was the query string normalized and segmented the same way as the indexed content?
6. Does the search mode require the right token format?

## 4. MySQL's Default Parser

MySQL FULLTEXT uses the built-in parser by default unless another parser is specified. This parser splits text into words based on character boundaries and delimiters per MySQL rules.

Letters, digits, underscores, and certain word-internal apostrophes can be treated as part of a token. Punctuation and whitespace typically create token boundaries. Exact behavior should be verified against real data on the running server version.

Example text:

~~~text
Học MySQL để xây dựng hệ thống cơ sở dữ liệu quan hệ.
~~~

It may be split into tokens roughly like:

~~~text
Học | MySQL | để | xây | dựng | hệ | thống | cơ | sở | dữ | liệu | quan | hệ
~~~

This illustrates token boundaries, not the output of a Vietnamese linguistic analyzer. The default parser does not know that "cơ sở dữ liệu" (database) is a multi-syllable term, nor does it recognize "hệ thống quản trị cơ sở dữ liệu" (database management system) as a single concept.

### 4.1. Token Length Limits

InnoDB and MyISAM have separate token length configuration variables:

| Engine | Minimum Variable | Common Default | Maximum Variable |
|---|---|---:|---|
| InnoDB | innodb_ft_min_token_size | 3 | innodb_ft_max_token_size |
| MyISAM | ft_min_word_len | 4 | ft_max_word_len |

Defaults can vary by configuration. Check at runtime:

~~~sql
SHOW VARIABLES LIKE 'innodb_ft_min_token_size';
SHOW VARIABLES LIKE 'innodb_ft_max_token_size';
SHOW VARIABLES LIKE 'ft_min_word_len';
SHOW VARIABLES LIKE 'ft_max_word_len';
~~~

If a token is shorter than the minimum threshold, it may be excluded from the FULLTEXT index. This is particularly noticeable for Vietnamese and queries with short words like "AI", "IoT", or short acronyms.

Do not lower the token threshold solely because one specific query fails to return results. First confirm whether the token truly needs to be searched, whether stopwords affect it, and what the impact on index size is.

### 4.2. Too-Short Words and Abbreviations

For example, a user searches "AI" while InnoDB uses the default minimum token size of 3. The two-character token may be omitted from the index. As a result, the query fails to find the document even though the string `AI` is in `body`.

Options:
- Use a dedicated code/keyword column with a B-tree index if it is an identifier.
- Design a different parser or search strategy for abbreviations.
- Adjust token size if appropriate for the overall workload and index cost is acceptable.
- Use an alias/keyword table to map short terms.
- Test the ngram parser if the problem genuinely requires short character tokens, then evaluate quality.

## 5. Stopwords and Their Impact on Vietnamese Search

Stopwords are tokens excluded from the FULLTEXT index because they are considered too common or of low distinguishing value. MySQL provides a default stopword list and mechanisms for configuring custom lists.

Some very frequent function words in natural language add little value for distinguishing documents. However, for Vietnamese, do not adopt the default English stopword list and assume it fits a Vietnamese corpus.

Check InnoDB's default list:

~~~sql
SELECT value
FROM information_schema.innodb_ft_default_stopword
ORDER BY value;
~~~

Check configuration:

~~~sql
SHOW VARIABLES LIKE 'innodb_ft_enable_stopword';
SHOW VARIABLES LIKE 'innodb_ft_server_stopword_table';
SHOW VARIABLES LIKE 'innodb_ft_user_stopword_table';
~~~

### 5.1. Why Can Stopwords Skew Results?

If an important domain term ends up on the stopword list, FULLTEXT may fail to index that term. For instance, an abbreviation or specialized term common in internal docs can still be a vital keyword for users.

Conversely, failing to exclude overly common words can generate noisy results and degrade ranking quality.

Build a stopword list from your real corpus:
1. Measure token frequencies.
2. Assess each token's distinguishing power.
3. Consult domain experts.
4. Inspect queries users actually enter.
5. Measure precision/recall before and after changes.

### 5.2. Changing Stopwords Requires Rebuilding the FULLTEXT Index

Changing the stopword list or stopword configuration does not automatically regenerate all previously indexed tokens. After updating configuration, rebuild FULLTEXT indexes following the procedure appropriate for your engine and version.

Do not simply change a configuration variable and assume old indexes already reflect the new list. Record the configuration, rebuild timestamp, and indexed row count for reproducibility.

## 6. Vietnamese-Specific Challenge: Words Can Span Multiple Syllables

Vietnamese places spaces between syllables. Many multi-syllable words are formed from two or more syllables:

- công nghệ (technology)
- thông tin (information)
- cơ sở dữ liệu (database)
- quản trị hệ thống (system administration)
- trí tuệ nhân tạo (artificial intelligence)
- học máy (machine learning)
- ngôn ngữ tự nhiên (natural language)

The built-in parser typically treats space-separated parts as separate tokens. For example, "cơ sở dữ liệu" may become four tokens: "cơ", "sở", "dữ", "liệu".

This causes several issues:
- Single-syllable queries can match many unrelated contexts.
- Multi-syllable compound words are not represented as a single semantic token.
- Short syllables may be dropped by min token size.
- Relevance scores may favor documents containing many common syllables rather than the exact term.
- Users entering accented vs. unaccented variants may receive different result sets.

### 6.1. Example of Noisy Results

Suppose two documents exist:

~~~text
A: Hướng dẫn cơ sở dữ liệu MySQL cho người mới học.
B: Cơ sở vật chất của trường học được nâng cấp.
~~~

A user searches "cơ sở dữ liệu" (database). The default parser may split it into individual tokens. Depending on search mode, stopwords, and relevance, document B might be considered because it contains "cơ sở" (facility/base) even though it has nothing to do with databases.

Boolean phrase search can help restrict to an adjacent token sequence, yet it does not replace linguistic understanding. Documents containing the same syllable sequence in another context can still be returned.

## 7. Application-Layer Preprocessing and Word Segmentation

A practical way to improve Vietnamese search quality is to run a word segmenter in the application layer and store the segmented text in a dedicated search column.

Keep the display content unchanged and create a `search_text` column:

~~~sql
CREATE TABLE article_search (
    article_id BIGINT UNSIGNED NOT NULL,
    title VARCHAR(255) NOT NULL,
    body MEDIUMTEXT NOT NULL,
    search_text MEDIUMTEXT NOT NULL,
    PRIMARY KEY (article_id),
    FULLTEXT KEY ft_article_search (search_text)
) ENGINE = InnoDB
  DEFAULT CHARACTER SET utf8mb4
  COLLATE utf8mb4_0900_as_cs;
~~~

Example original content:

~~~text
Học cơ sở dữ liệu và công nghệ thông tin với MySQL.
~~~

After Unicode normalization and segmentation with a Vietnamese-aware tool, the application can generate `search_text`:

~~~text
học cơ_sở_dữ_liệu và công_nghệ_thông_tin với MySQL
~~~

The underscore is used here as a convention to join syllables belonging to the same word. The built-in parser treats underscores as word-internal characters, though you must verify actual tokenization results on your server.

Queries must also pass through the same word segmenter:

~~~text
User query: cơ sở dữ liệu
Segmented string: cơ_sở_dữ_liệu
~~~

If you preprocess only documents without preprocessing queries, both sides will fail to produce matching tokens and search quality will drop.

### 7.1. Do Not Alter Original Text

Store separately:
- original `title`/`body` for display and editing.
- `search_text` to serve search.
- `tokenizer_version` to track which segmenter version generated the text, in case migrations are needed.

Never overwrite original content with underscore-joined syllables. `search_text` is a derived representation for querying.

### 7.2. Consistent Two-Sided Normalization

The pipeline should include these steps:
1. Validate that input is valid UTF-8.
2. Normalize Unicode to a uniform form, typically NFC.
3. Normalize whitespace and control characters per product rules.
4. Perform Vietnamese word segmentation.
5. Normalize casing according to the search strategy.
6. Generate `search_text`.
7. Save original content and `search_text` in the same transaction.
8. When users search, apply the same pipeline to the query.

Do not strip Vietnamese diacritics by default. If you want to support unaccented queries, design a separate search representation and measure noise.

### 7.3. Example with Parallel Accented and Unaccented Columns

You can maintain two search columns:

~~~sql
CREATE TABLE article_search_variant (
    article_id BIGINT UNSIGNED NOT NULL,
    original_text MEDIUMTEXT NOT NULL,
    search_text_accented MEDIUMTEXT NOT NULL,
    search_text_folded MEDIUMTEXT NOT NULL,
    PRIMARY KEY (article_id),
    FULLTEXT KEY ft_accented (search_text_accented),
    FULLTEXT KEY ft_folded (search_text_folded)
) ENGINE = InnoDB
  DEFAULT CHARACTER SET utf8mb4
  COLLATE utf8mb4_0900_as_cs;
~~~

- `search_text_accented` preserves diacritics and can use an accent-sensitive collation.
- `search_text_folded` is generated by a controlled accent-folding pipeline.
- `original_text` stores display content.

If both searches are executed, merge results properly, deduplicate `article_id`, reconcile relevance scores, and prioritize exact accented matches. Do not sum scores arbitrarily; define ranking rules and evaluate on a benchmark query set.

## 8. Creating a FULLTEXT Index with the Default Parser

Example document table:

~~~sql
CREATE TABLE knowledge_article (
    article_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    title VARCHAR(255) NOT NULL,
    body MEDIUMTEXT NOT NULL,
    search_text MEDIUMTEXT NOT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (article_id),
    FULLTEXT KEY ft_knowledge_search (search_text)
) ENGINE = InnoDB
  DEFAULT CHARACTER SET utf8mb4
  COLLATE utf8mb4_0900_as_cs;
~~~

Insert data:

~~~sql
INSERT INTO knowledge_article(title, body, search_text)
VALUES
(
    'Cơ sở dữ liệu MySQL',
    'Tài liệu giới thiệu hệ quản trị cơ sở dữ liệu quan hệ.',
    'tài_liệu giới_thiệu hệ_quản_trị cơ_sở_dữ_liệu quan_hệ'
),
(
    'Công nghệ thông tin',
    'Khái niệm công nghệ thông tin và hệ thống phần mềm.',
    'khái_niệm công_nghệ_thông_tin và hệ_thống phần_mềm'
);
~~~

Natural language search:

~~~sql
SELECT
    article_id,
    title,
    MATCH(search_text)
        AGAINST ('cơ_sở_dữ_liệu' IN NATURAL LANGUAGE MODE) AS relevance
FROM knowledge_article
WHERE MATCH(search_text)
    AGAINST ('cơ_sở_dữ_liệu' IN NATURAL LANGUAGE MODE)
ORDER BY relevance DESC;
~~~

In this example, `search_text` is preprocessed. If using raw `body`, tokenization results will differ and must be evaluated under the default parser.

### 8.1. MATCH Must Correspond to a FULLTEXT Index

The column list in `MATCH()` must match an available FULLTEXT index. If the index was created on `(title, body)`, queries typically use:

~~~sql
MATCH(title, body) AGAINST ('mysql database' IN NATURAL LANGUAGE MODE)
~~~

Do not assume a FULLTEXT index on `search_text` can serve `MATCH(body)` or `MATCH(title, body)`. Verify index definitions with:

~~~sql
SHOW INDEX FROM knowledge_article;
~~~

## 9. Natural Language Mode, Boolean Mode, and Phrase Search

### 9.1. Natural Language Mode

This is the default mode when no other mode is specified:

~~~sql
SELECT
    article_id,
    title,
    MATCH(search_text)
        AGAINST ('cơ_sở_dữ_liệu mysql' IN NATURAL LANGUAGE MODE) AS score
FROM knowledge_article
WHERE MATCH(search_text)
    AGAINST ('cơ_sở_dữ_liệu mysql' IN NATURAL LANGUAGE MODE)
ORDER BY score DESC;
~~~

Natural language mode computes relevance based on tokens and their distribution across the document set. It fits natural search, though it does not guarantee phrases appear intact in exact order.

In InnoDB, MyISAM's 50% threshold rule does not apply to natural language search. Behavior can differ between engines; verify the actual engine when migrating systems.

### 9.2. Boolean Mode

Boolean mode allows controlling required, excluded, or prefix tokens:

~~~sql
SELECT article_id, title
FROM knowledge_article
WHERE MATCH(search_text)
    AGAINST ('+cơ_sở_dữ_liệu +mysql -giải_trí' IN BOOLEAN MODE);
~~~

Common operators:
- `+term`: the term must appear.
- `-term`: the term must not appear.
- `term*`: matches tokens with the specified prefix.
- `"phrase"`: matches a token sequence in adjacent order per phrase search semantics.
- Other operators have specific rules for grouping, weighting, and negation.

MySQL Boolean mode syntax is not identical to other search engines' syntax. Test operators thoroughly before exposing them to users.

### 9.3. Phrase Search

Example searching for a segmented phrase:

~~~sql
SELECT article_id, title
FROM knowledge_article
WHERE MATCH(search_text)
    AGAINST ('"cơ_sở_dữ_liệu"' IN BOOLEAN MODE);
~~~

Phrase search checks an ordered sequence of tokens. If content and queries use different word-segmentation rules, phrase search may fail to match as expected.

Phrase search is not semantic search. It does not automatically understand synonyms, spelling variants, or user intent.

### 9.4. Query Expansion

Query expansion can broaden results based on top matches from the initial pass. It can retrieve additional documents with related tokens, yet also increases noisy results. Enable it only if the product needs query expansion and you have evaluated it on a benchmark dataset.

## 10. The ngram Parser and Limitations for Vietnamese

MySQL provides the ngram full-text parser plugin, useful for languages without space-separated words such as Chinese, Japanese, or Korean. The ngram parser splits strings into contiguous character sequences of length N.

Create the FULLTEXT index:

~~~sql
CREATE TABLE article_ngram (
    article_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    content TEXT NOT NULL,
    PRIMARY KEY (article_id),
    FULLTEXT KEY ft_article_ngram (content) WITH PARSER ngram
) ENGINE = InnoDB
  DEFAULT CHARACTER SET utf8mb4;
~~~

Configuration variable:

~~~sql
SHOW VARIABLES LIKE 'ngram_token_size';
~~~

`ngram_token_size` specifies the number of characters per n-gram; the default is typically 2. Check runtime configuration and version-specific documentation.

### 10.1. ngram Is Not a Vietnamese Word Segmenter

Vietnamese has spaces between syllables, yet multi-syllable words form lexical units. The ngram parser creates character sequences of length N and does not understand Vietnamese compound word structure or semantics.

For example, "công nghệ thông tin" can produce many character n-grams. Searching a short n-gram can return many documents containing the same character sequence inside completely different words. This helps for certain substring/prefix tasks or non-space-delimited languages, but does not solve Vietnamese word segmentation.

### 10.2. When to Test ngram?

You might test it if:
- The application needs substring or character-sequence search.
- Very short keywords occur frequently.
- Multilingual data includes CJK content.
- An external word segmenter cannot meet operational requirements.
- The team accepts a larger index and evaluates false positives.

Do not pick ngram solely because Vietnamese search involves diacritics. For Vietnamese word/phrase search, an application-layer word segmenter usually represents compound word semantics much more clearly.

### 10.3. Cost and Limitations

Ngram creates more tokens than a word-based parser, especially when token size is small. This can:
- Make the FULLTEXT index larger.
- Increase `INSERT`/`UPDATE` overhead.
- Increase candidate counts during queries.
- Increase noisy results.
- Make ranking harder to control.

Changing `ngram_token_size` requires planning a FULLTEXT index rebuild so the index reflects the new setting. Never change production settings without benchmarking index size and latency.

## 11. Controlling Stopwords and Token Size for a Vietnamese Corpus

Before tuning settings, build a test table covering these word groups:

| Group | Example | Question |
|---|---|---|
| Short single words | AI, C, Go | Dropped due to min token size? |
| Long single words | database, transaction | Indexed as expected by parser? |
| Multi-syllable words | công nghệ, học máy | Need application-layer word segmentation? |
| Domain phrases | cơ sở dữ liệu, kiểm soát đồng thời | Need phrase search or joined tokens? |
| Very common words | và, là, của | Dropped by stopwords? |
| Technical codes | SQL, C++, utf8mb4 | How are punctuation and special chars handled? |
| Accented words | máy, mây, may | Does collation distinguish them as required? |

### 11.1. InnoDB Configuration

Check:

~~~sql
SHOW VARIABLES LIKE 'innodb_ft_%';
~~~

Key variables:
- `innodb_ft_min_token_size`.
- `innodb_ft_max_token_size`.
- `innodb_ft_enable_stopword`.
- `innodb_ft_server_stopword_table`.
- `innodb_ft_user_stopword_table`.

Not all variables share the same scope or dynamic mutability. Confirm version documentation before changing. Some settings must be specified at server startup or only take effect when creating/rebuilding indexes.

### 11.2. MyISAM Configuration

If the system uses MyISAM, check:
- `ft_min_word_len`.
- `ft_max_word_len`.
- `ft_stopword_file`.

These variables differ from InnoDB variables. Do not use InnoDB variable names to infer MyISAM behavior.

### 11.3. Configuration Changes Require Rebuilds

After changing min token size, max token size, stopwords, or parser configuration:
1. Identify which FULLTEXT indexes are affected.
2. Save the previous configuration.
3. Plan the rebuild.
4. Test in staging with a representative data copy.
5. Compare token counts/index sizes and search results.
6. Deploy within an appropriate maintenance window.
7. Re-verify queries and relevance.
8. Keep a rollback plan for configuration and index.

If you change variables without rebuilding, old indexes may still contain tokens created under the previous rules.

## 12. Collation and Testing Accented/Unaccented Queries

Do not test only with ordinary `SELECT`s. Directly test FULLTEXT with accented, unaccented, upper/lower case, and different Unicode forms.

Example data insertion:

~~~sql
INSERT INTO knowledge_article(title, body, search_text)
VALUES
('Máy học', 'Giới thiệu máy học và dữ liệu.', 'máy_học giới_thiệu máy_học dữ_liệu'),
('Mây dữ liệu', 'Lưu trữ dữ liệu trên nền tảng đám mây.', 'mây dữ_liệu lưu_trữ dữ_liệu nền_tảng đám_mây'),
('May mặc', 'Quy trình sản xuất hàng may mặc.', 'may_mặc quy_trình sản_xuất hàng may_mặc');
~~~

Query each variant:

~~~sql
SELECT article_id, title,
       MATCH(search_text) AGAINST ('máy_học' IN NATURAL LANGUAGE MODE) AS score
FROM knowledge_article
WHERE MATCH(search_text) AGAINST ('máy_học' IN NATURAL LANGUAGE MODE)
ORDER BY score DESC;
~~~

~~~sql
SELECT article_id, title,
       MATCH(search_text) AGAINST ('may_hoc' IN NATURAL LANGUAGE MODE) AS score
FROM knowledge_article
WHERE MATCH(search_text) AGAINST ('may_hoc' IN NATURAL LANGUAGE MODE)
ORDER BY score DESC;
~~~

Results depend on how `search_text` is generated, collation, parser, stopwords, and token size. Do not conclude from a single example that every unaccented word will automatically match its accented counterpart.

### 12.1. Minimum Query Test Matrix

| Query | What to Verify |
|---|---|
| máy học | Accented phrase matching |
| may hoc | Unaccented search behavior |
| MÁY HỌC | Case sensitivity |
| Máy_học | Token-joining convention |
| máy | Short tokens and noisy results |
| học máy | Reversed token order |
| "máy học" | Phrase search |
| máy học -quảng cáo | Boolean exclusion |
| SQL | Technical abbreviations |
| C++ | Punctuation inside technical tokens |

Each query should have a list of expected relevant documents and non-relevant documents to evaluate false positives and false negatives.

## 13. Verifying Unicode Normalization

The same visually displayed word can originate from multiple sources:
- Web forms.
- CSV/Excel files.
- Third-party APIs.
- Text copied from editors.
- Legacy imported data.

If the normalization pipeline is inconsistent, queries may fail to match even when they look identical in the UI.

In the application layer:
- Normalize text before storing, typically to NFC.
- Normalize queries using the same rule.
- Keep original content untouched if preserving raw bytes/source is required.
- Store a hash or pipeline version to track migrations if needed.
- Test strings containing combining marks.

SQL can help inspect character and byte lengths:

~~~sql
SELECT
    title,
    CHAR_LENGTH(title) AS character_count,
    LENGTH(title) AS byte_count,
    HEX(title) AS utf8_bytes
FROM knowledge_article
WHERE article_id = 1;
~~~

`CHAR_LENGTH` counts characters in the string; `LENGTH` counts bytes. `HEX` helps inspect byte representations when investigating Unicode data. These functions do not replace Unicode normalization in the application.

## 14. Evaluating Search Quality with a Benchmark Query Set

Do not evaluate search quality merely by typing a few queries and eyeballing results. Build a test suite of queries with human-labeled relevant documents.

Example structure:

| query_id | query_text | relevant_article_ids | intent |
|---|---|---|---|
| Q001 | cơ sở dữ liệu | 10, 12, 19 | Database concept |
| Q002 | công nghệ thông tin | 21, 22 | Multi-syllable term |
| Q003 | máy học | 30, 31 | Accented term |
| Q004 | may hoc | 30, 31 | Unaccented query |
| Q005 | SQL | 42, 45 | Short abbreviation |
| Q006 | kiểm soát đồng thời | 51, 53 | Domain phrase |

The evaluation set should cover:
- Short and long queries.
- Accented and unaccented forms.
- Uppercase/lowercase variations.
- Single-syllable and multi-syllable words.
- Domain phrases.
- Abbreviations.
- Common typos.
- Punctuation and technical codes.
- Multi-intent queries.
- Queries with no matching results.

### 14.1. Precision@K

Precision@K measures the proportion of relevant results within the top K results:

[
Precision@K = \frac{\text{number of relevant results in top K}}{K}
]

For example, if the top 5 contains 4 relevant documents:

[
Precision@5 = \frac{4}{5} = 0.8
]

High precision means fewer noisy results in the top positions.

### 14.2. Recall@K

Recall@K measures the proportion of all relevant documents found within the top K results:

[
Recall@K = \frac{\text{number of relevant documents in top K}}{\text{total number of labeled relevant documents}}
]

If there are 10 relevant documents and the top 10 finds 6:

[
Recall@10 = \frac{6}{10} = 0.6
]

Low recall may result from the tokenizer dropping tokens, stopwords, min token size, or inconsistent query normalization.

### 14.3. MRR

Mean Reciprocal Rank evaluates the position of the first relevant result:

[
RR(q) = \frac{1}{\text{rank of the first relevant result}}
]

MRR is the average of RR across all queries. If the first relevant document ranks 1st, RR=1; if 4th, RR=0.25.

MRR is useful when users typically inspect only the first few results.

### 14.4. nDCG

Normalized Discounted Cumulative Gain evaluates ranking with multi-level relevance grades. A highly relevant document can be scored 3, partially relevant 1, and irrelevant 0. nDCG penalizes relevant results appearing too far down the list.

Use nDCG when reviewers need to distinguish deeply relevant documents from documents that merely share overlapping keywords.

### 14.5. Evaluating by Error Slice

Do not compute only a single overall average. Break down by category:
- Accented.
- Unaccented.
- Case variation.
- Unicode normalization.
- Multi-syllable words.
- Abbreviations.
- Stopwords.
- Short tokens.
- Phrases.
- Typos.

A configuration with high overall precision but very low recall on unaccented queries may still fail product requirements.

## 15. Comparing Tokenization Strategies

Compare at least three baselines:

| Strategy | Approach | Strengths | Risks |
|---|---|---|---|
| Built-in parser | Index original text with default parser | Simple, fewer moving parts | Does not understand Vietnamese compound words |
| Application word segmentation | Segment Vietnamese words and store `search_text` | Preserves lexical units better | Must keep tokenizer synchronized for index and query |
| ngram parser | Split strings into character n-grams | Can support character/substring and CJK search | Large index, noisy, lacks Vietnamese word semantics |

Compare using the same corpus, same query set, same relevance criteria, and same hardware. Never compare the latency of one configuration on a warm cache against another on a cold cache.

Record:
- Precision@5 and Precision@10.
- Recall@10.
- MRR or nDCG.
- p50/p95 latency.
- FULLTEXT index size.
- Load/rebuild duration.
- `INSERT`/`UPDATE` overhead.
- Zero-result query rate.

## 16. Inspecting FULLTEXT Indexes and Runtime Configuration

Diagnostic commands:

~~~sql
SHOW CREATE TABLE knowledge_article;
SHOW INDEX FROM knowledge_article;
SHOW FULL COLUMNS FROM knowledge_article;
~~~

Check engine, charset, and collation:

~~~sql
SELECT
    TABLE_NAME,
    ENGINE,
    TABLE_COLLATION
FROM information_schema.tables
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'knowledge_article';
~~~

~~~sql
SELECT
    COLUMN_NAME,
    DATA_TYPE,
    CHARACTER_SET_NAME,
    COLLATION_NAME
FROM information_schema.columns
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'knowledge_article';
~~~

Check FULLTEXT token size and stopwords:

~~~sql
SHOW VARIABLES LIKE 'innodb_ft_min_token_size';
SHOW VARIABLES LIKE 'innodb_ft_max_token_size';
SHOW VARIABLES LIKE 'innodb_ft_enable_stopword';
SHOW VARIABLES LIKE 'ngram_token_size';
~~~

InnoDB provides INFORMATION_SCHEMA views to inspect indexed tokens in certain diagnostic scenarios:

~~~sql
SET GLOBAL innodb_ft_aux_table = 'app_db/knowledge_article';

SELECT
    WORD,
    DOC_COUNT,
    DOC_ID
FROM information_schema.innodb_ft_index_table
ORDER BY WORD;
~~~

`innodb_ft_aux_table` is a diagnostic variable for InnoDB FULLTEXT; reading auxiliary tables requires appropriate privileges and state. Do not enable or alter global diagnostic settings casually in production. Consult version-specific documentation before using it.

If expected tokens do not appear, check stopwords, token size, parser, and index state before modifying data.

## 17. Changing Collation, Parser, and Rebuilding Indexes

Changing a column's collation can alter comparison semantics and how FULLTEXT processes words. Changing the parser or token-size/stopword configuration also changes the indexed token set.

A controlled migration:
1. Save `SHOW CREATE TABLE` and current FTS configuration.
2. Create a data copy or staging environment for testing.
3. Apply charset/collation/parser/configuration changes in staging.
4. Rebuild the FULLTEXT index.
5. Run the benchmark query suite.
6. Compare precision/recall, relevance, and latency.
7. Estimate index size and build duration.
8. Schedule a deployment window and rollback plan.
9. Execute the production migration.
10. Verify index, collation, and search results post-deployment.

Example dropping and recreating a FULLTEXT index:

~~~sql
ALTER TABLE knowledge_article
    DROP INDEX ft_knowledge_search;

ALTER TABLE knowledge_article
    ADD FULLTEXT INDEX ft_knowledge_search (search_text);
~~~

If using ngram:

~~~sql
ALTER TABLE article_ngram
    ADD FULLTEXT INDEX ft_article_ngram_v2 (content) WITH PARSER ngram;
~~~

Exact DDL behavior and locking/online characteristics depend on version, engine, table size, and change type. Do not assume rebuilding a FULLTEXT index is non-disruptive.

## 18. Common Misconceptions

| Misconception | Reality | How to Handle |
|---|---|---|
| Collation segments Vietnamese words automatically | Collation only governs comparison/sorting | Use an appropriate tokenizer |
| `utf8mb4` guarantees good Vietnamese search | Charset only ensures character storage capability | Test parser, collation, and tokens |
| `ai_ci` is always best | Ignoring accents can increase false positives | Evaluate accent-sensitive vs. insensitive |
| `as_cs` is always mandatory | Products may need unaccented queries | Design controlled search variants |
| MySQL understands "cơ sở dữ liệu" as one word | Built-in parser splits mainly by character boundaries | Use word segmentation or token-joining convention |
| ngram is a Vietnamese word segmenter | ngram splits character strings by N | Use when n-grams fit the problem, without expecting semantic understanding |
| Every word in body is indexed | Tokens may be dropped by length or stopwords | Check FTS configuration |
| Changing stopwords updates old indexes automatically | Old indexes must be rebuilt under the new config | Plan index rebuilds |
| Changing collation only affects display | Collation affects comparison semantics and indexes | Test and rebuild appropriately |
| Unaccented search always matches accented text | Depends on collation, parser, and pipeline | Test accented/unaccented queries |
| Phrase search understands semantics | Phrase search checks an ordered token sequence | Add relevance/semantic layer if needed |
| Creating a FULLTEXT index means the optimizer always uses it | Plan depends on query and cost | Check `EXPLAIN` |
| A high relevance score means the result is correct | Relevance is only an internal ranking | Evaluate with labeled query sets |
| MyISAM and InnoDB share identical FTS rules | Token size, stopwords, and some semantics differ | Check specific engine behavior |
| Changing min token size needs no rebuild | Old index may still reflect prior settings | Rebuild and re-test |

## 19. Process for Verifying Vietnamese Tokenization Quality

1. Collect a corpus representative of real content.
2. Create a query list with accented, unaccented, compound words, abbreviations, and domain terms.
3. Label relevant documents with relevance grades.
4. Normalize Unicode for documents and queries via the same pipeline.
5. Run a baseline with the built-in parser.
6. Check whether token size and stopwords drop important words.
7. Test accent-sensitive and accent-insensitive collations.
8. Test application word segmentation and create a dedicated `search_text` column.
9. If needed, test the ngram parser as an additional baseline.
10. Run the same query set across each configuration.
11. Compute Precision@K, Recall@K, MRR, and nDCG.
12. Analyze false positives/false negatives by query slice.
13. Measure p50/p95 latency and index size.
14. Measure write and rebuild costs.
15. Choose the configuration balancing quality, speed, and operational maintainability.
16. Record tokenizer version, collation, stopwords, and token-size config alongside evaluation results.
17. Run regression tests after every pipeline or MySQL version change.

## 20. Practice Exercises

### Exercise 1: Compare Collations

Create two tables or two columns using `utf8mb4_0900_ai_ci` and `utf8mb4_0900_as_cs`. Insert variants "ma", "má", "mà", "mã", "mạ". Compare regular equality checks and FULLTEXT search. Record the differences.

### Exercise 2: Case Sensitivity Check

Search for the same document using "MySQL", "mysql", and "MYSQL" across different collations. Determine which collation matches product requirements.

### Exercise 3: Built-in Parser

Create a FULLTEXT index on raw `body`. Search for "cơ sở dữ liệu", "cơ_sở_dữ_liệu", "cơ sở", and "dữ liệu". Observe results and explain why the default parser does not understand compound words.

### Exercise 4: Token Size

Check `innodb_ft_min_token_size`. Test queries "AI", "IoT", and "SQL". Identify which tokens are dropped, then design a handling approach without altering production configuration.

### Exercise 5: Stopwords

Inspect the default stopword table. Create a corpus with a frequently occurring domain term. Evaluate how queries change if that term is excluded from the index.

### Exercise 6: Application Word Segmentation

Use a Vietnamese word segmenter to create `search_text` with an underscore-joining convention. Create a FULLTEXT index and compare queries against the built-in parser baseline.

### Exercise 7: Unicode Normalization

Create two visually identical strings, one using precomposed characters and the other using combining marks. Check `CHAR_LENGTH`, `LENGTH`, `HEX`, and search behavior before/after NFC normalization in the application.

### Exercise 8: Accent Folding

Create `search_text_accented` and `search_text_folded` columns. Compare accented and unaccented queries. Record false positives from accent folding and propose ranking rules favoring exact matches.

### Exercise 9: ngram Parser

Create a FULLTEXT index `WITH PARSER ngram`. Check `ngram_token_size`, search short character sequences, and compare index size with the default parser.

### Exercise 10: Boolean and Phrase Search

Test `+term`, `-term`, prefix wildcards, and phrase search on segmented data. Verify syntax and results on accented queries.

### Exercise 11: Quality Evaluation Suite

Create at least 30 queries, each with labeled relevant documents. Compute Precision@5, Recall@10, and MRR for two tokenizer configurations.

### Exercise 12: Regression Testing

Save collation, parser, token size, stopword, and tokenizer version settings. Change one setting in staging, rebuild the index, and re-run the entire query set. Report before/after quality and latency.

## 21. Pre-Deployment Checklist for Vietnamese Full-Text Search

- [ ] Text columns use the `utf8mb4` charset.
- [ ] Actual collation of each FULLTEXT column is verified.
- [ ] Understood how `ai`/`as` and `ci`/`cs` affect search requirements.
- [ ] Checked available collations on the target server.
- [ ] Distinguished collation from tokenizer.
- [ ] Tested the default parser on a Vietnamese corpus.
- [ ] Evaluated multi-syllable words and domain phrases.
- [ ] Checked `innodb_ft_min_token_size` or `ft_min_word_len` per engine.
- [ ] Checked stopwords and excluded domain terms.
- [ ] Standardized Unicode normalization for documents and queries.
- [ ] Evaluated application-layer word segmentation.
- [ ] Kept original content separate from `search_text`.
- [ ] Used the same tokenizer for content and queries.
- [ ] Evaluated accented and unaccented search.
- [ ] Used ngram only where suited and measured false positives.
- [ ] Confirmed `MATCH()` matches a FULLTEXT index.
- [ ] Tested Natural Language, Boolean, and phrase search.
- [ ] Built a query set with relevance labels.
- [ ] Measured Precision@K, Recall@K, MRR, or nDCG.
- [ ] Measured latency, index size, and write cost.
- [ ] Planned rebuilds after collation/parser/stopword/token-size changes.
- [ ] Ran regression tests on the exact production MySQL version.

## 22. Conclusion

Vietnamese Full-Text Search quality depends simultaneously on charset, collation, parser, token size, stopwords, and text normalization. `utf8mb4` enables full Unicode storage; collation defines case and accent comparison rules; the parser defines how tokens are split. These mechanisms do not replace one another.

The built-in parser is simple, but typically splits Vietnamese by syllable without recognizing multi-syllable compound words. The ngram parser creates N-character sequences and fits certain CJK/substring tasks better; it is not a Vietnamese-aware word segmenter. For Vietnamese term search, a practical approach is normalizing Unicode and segmenting words in the application layer, storing a separate `search_text`, and applying the same pipeline to queries.

Never choose a collation or tokenizer on intuition alone. Build a labeled corpus and query set, test accented/unaccented variants, short words, stopwords, compound words, and technical codes. Measure precision, recall, ranking, latency, index size, and write cost. After any parser, stopword, token-size, or collation change, rebuild indexes as planned and run regression tests before releasing.

## Official References

- [MySQL 8.4 Reference Manual – Full-Text Search Functions](https://dev.mysql.com/doc/refman/8.4/en/fulltext-search.html)
- [MySQL 8.4 Reference Manual – Full-Text Stopwords](https://dev.mysql.com/doc/refman/8.4/en/fulltext-stopwords.html)
- [MySQL 8.4 Reference Manual – Fine-Tuning MySQL Full-Text Search](https://dev.mysql.com/doc/refman/8.4/en/fulltext-fine-tuning.html)
- [MySQL 8.4 Reference Manual – ngram Full-Text Parser](https://dev.mysql.com/doc/refman/8.4/en/fulltext-search-ngram.html)
- [MySQL 8.4 Reference Manual – Full-Text Parser Plugins](https://dev.mysql.com/doc/refman/8.4/en/plugin-types.html)
- [MySQL 8.4 Reference Manual – Character Sets and Collations](https://dev.mysql.com/doc/refman/8.4/en/charset.html)
- [MySQL 8.4 Reference Manual – Unicode Character Sets](https://dev.mysql.com/doc/refman/8.4/en/charset-unicode.html)
- [MySQL 8.4 Reference Manual – SHOW COLLATION](https://dev.mysql.com/doc/refman/8.4/en/show-collation.html)
- [MySQL 8.4 Reference Manual – InnoDB INFORMATION_SCHEMA FULLTEXT Tables](https://dev.mysql.com/doc/refman/8.4/en/innodb-information-schema-fulltext-tables.html)
- [MySQL 8.4 Reference Manual – EXPLAIN](https://dev.mysql.com/doc/refman/8.4/en/explain.html)
