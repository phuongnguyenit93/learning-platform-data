# Boolean Mode, Search Operators, and Result Semantics

MySQL FULLTEXT supports searching the content of text columns. When an application needs to find documents matching a keyword string, FULLTEXT can parse tokens, look up the inverted index, and compute the relevance of each row. Boolean mode lets you describe search requirements using operators such as requiring words, excluding words, increasing or decreasing weights, searching phrases, and finding words in close proximity.

Boolean mode is suitable when users need finer control over search conditions. For example, someone might require an article to contain `mysql`, disallow `oracle`, prioritize articles mentioning `index`, and penalize articles containing `legacy`.

This lesson focuses on `IN BOOLEAN MODE` syntax, the meaning of each operator, combining expressions, reading relevance scores, and factors affecting results such as FULLTEXT indexes, parsers, stopwords, and token length. The examples use InnoDB and an articles table with a FULLTEXT index on `title` and `body`.

## 1. Boolean Mode in MySQL FULLTEXT

MySQL has two common FULLTEXT search modes:

- Natural language mode: interprets the search string as natural language and ranks documents based on relevance.
- Boolean mode: interprets the search string as an operator-based expression, allowing specific words and phrases to be required or excluded.

Boolean mode is not SQL's `AND`/`OR` operators. It is a dedicated syntax inside the string passed to `MATCH() AGAINST()`. Standard relational conditions are still written with `WHERE`, `JOIN`, and other SQL operators.

Syntax:

~~~sql
MATCH(column_list)
AGAINST('search_expression' IN BOOLEAN MODE)
~~~

Example:

~~~sql
SELECT
    article_id,
    title
FROM articles
WHERE MATCH(title, body)
      AGAINST('+mysql +index' IN BOOLEAN MODE);
~~~

The query above requires documents to contain both the words `mysql` and `index` according to the tokens recognized by the FULLTEXT parser.

### 1.1. What Scenarios Does Boolean Mode Solve?

Suppose a user searches technical documentation and enters:

~~~text
+mysql +index -oracle
~~~

Meaning:

- The document must contain `mysql`.
- The document must contain `index`.
- The document must not contain `oracle`.

A free-form query like `mysql index` does not explicitly express mandatory requirements. Boolean mode lets you express them directly.

### 1.2. Boolean Mode Does Not Replace SQL Filters

FULLTEXT only identifies rows matching the text expression. Conditions such as publication status, tenant, access permissions, or date ranges still need to be checked in SQL:

~~~sql
SELECT
    article_id,
    title
FROM articles
WHERE status = 'PUBLISHED'
  AND tenant_id = 42
  AND MATCH(title, body)
      AGAINST('+mysql +index' IN BOOLEAN MODE);
~~~

Do not put authorization conditions inside search content and treat them as an access control mechanism. Row-level read permissions must be enforced using relational conditions or an appropriate security mechanism.

## 2. Preparing the FULLTEXT Index

Boolean mode requires a FULLTEXT index on the searched columns. InnoDB supports FULLTEXT indexes on `CHAR`, `VARCHAR`, and `TEXT` columns.

Create the example table:

~~~sql
CREATE TABLE articles (
    article_id BIGINT UNSIGNED NOT NULL,
    tenant_id BIGINT UNSIGNED NOT NULL,
    title VARCHAR(250) NOT NULL,
    body MEDIUMTEXT NOT NULL,
    status VARCHAR(20) NOT NULL,
    published_at DATETIME NULL,
    PRIMARY KEY (article_id),
    KEY idx_articles_tenant_status_date
        (tenant_id, status, published_at),
    FULLTEXT KEY ft_articles_title_body (title, body)
) ENGINE = InnoDB;
~~~

The FULLTEXT index `ft_articles_title_body` indexes `title` and `body` together. Corresponding search queries must use the exact column list:

~~~sql
MATCH(title, body)
AGAINST('+mysql +index' IN BOOLEAN MODE)
~~~

With InnoDB, the column list in `MATCH()` must match the columns of a FULLTEXT index in the same order. If you want to search only in `title`, create a separate FULLTEXT index on `title` and use `MATCH(title)`. Do not assume an arbitrary composite FULLTEXT index can serve every column combination.

If you did not declare the FULLTEXT index in `CREATE TABLE`, you can add it after creating the table:

~~~sql
ALTER TABLE articles
ADD FULLTEXT INDEX ft_articles_title_body (title, body);
~~~

Choose one of the two ways to create the index: declare it in `CREATE TABLE` or add it via `ALTER TABLE`. Do not run both examples on the same table, as the index name will conflict.

### 2.1. Insert Sample Data

~~~sql
INSERT INTO articles
    (article_id, tenant_id, title, body, status, published_at)
VALUES
(
    1, 42, 'MySQL index fundamentals',
    'Learn how a MySQL index helps the optimizer find rows efficiently.',
    'PUBLISHED', '2026-01-10 09:00:00'
),
(
    2, 42, 'MySQL query optimization',
    'Use EXPLAIN to inspect a query plan and improve database performance.',
    'PUBLISHED', '2026-01-12 10:00:00'
),
(
    3, 42, 'Oracle index concepts',
    'This article discusses index design in Oracle and relational databases.',
    'PUBLISHED', '2026-01-14 11:00:00'
),
(
    4, 42, 'Database engine internals',
    'The storage engine manages pages, transactions, indexes, and recovery.',
    'DRAFT', NULL
),
(
    5, 84, 'MySQL and full text search',
    'Boolean full text search supports required and excluded terms.',
    'PUBLISHED', '2026-01-18 13:00:00'
);
~~~

Sample data helps compare results when changing operators. In real environments, tokens may be skipped due to stopwords or token length rules; a later section explains why a word present in the search string may not necessarily be indexed.

## 3. Boolean Operators

Boolean mode supports the following primary operators:

| Operator | Meaning | Impact on Results |
|---|---|---|
| + | Word is required | Row must match this word |
| - | Word must not appear | Excludes rows containing this word |
| No operator | Optional word | Rows matching this word may be returned |
| > | Increases contribution to relevance | Prioritizes rows containing this word |
| < | Decreases contribution to relevance | Lowers relative score |
| ~ | Negative contribution to relevance | Lowers score without excluding the row |
| * | Token prefix search | Matches words starting with the prefix |
| () | Expression grouping | Combines conditions into a group |
| " | Phrase search | Searches for words as a phrase enclosed in quotes |
| @distance | Proximity search | Limits word distance within a phrase, InnoDB |

The operators `+`, `-`, `>`, `<`, `~` are placed before the corresponding word or expression. The `*` operator is placed after the token.

## 4. Required Words with the Plus Operator

The plus sign `+` requires the token to appear in returned rows.

### 4.1. Requiring One Word

~~~sql
SELECT article_id, title
FROM articles
WHERE MATCH(title, body)
      AGAINST('+mysql' IN BOOLEAN MODE);
~~~

Only articles containing the `mysql` token satisfy this expression.

### 4.2. Requiring Multiple Words

~~~sql
SELECT article_id, title
FROM articles
WHERE MATCH(title, body)
      AGAINST('+mysql +index' IN BOOLEAN MODE);
~~~

Both `mysql` and `index` are required. If a row has `mysql` without `index`, that row is not returned.

### 4.3. Distinguishing Two Plus Operators from Operator-Free Strings

| Expression | Meaning |
|---|---|
| +mysql | Must contain `mysql` |
| +mysql +index | Must contain both `mysql` and `index` |
| mysql index | Words are optional; matching either word can be enough to return a row |
| +mysql index | Must contain `mysql`; `index` is optional |

Words without operators are not required by default. This is an important point when translating user search inputs from the UI into Boolean expressions.

## 5. Excluding Words with the Minus Operator

The minus sign `-` excludes rows containing the marked token from the result set.

~~~sql
SELECT article_id, title
FROM articles
WHERE MATCH(title, body)
      AGAINST('+mysql -oracle' IN BOOLEAN MODE);
~~~

The query requires:

- Contains `mysql`.
- Does not contain `oracle`.

The minus operator is typically used alongside at least one positive condition. An expression containing only excluded words, such as `-oracle`, does not define a target document set and returns an empty set.

### 5.1. An Exclusion Condition Is Not a Full-Table SQL Negation

`-oracle` only excludes documents containing the `oracle` token in FULLTEXT-indexed content. It does not mean finding every row in the entire table that lacks `oracle` when there is no positive term as a base.

If you need to query all rows that do not contain a word, consider an appropriate SQL condition or query design. FULLTEXT Boolean mode is optimized for token-based content search, not as a replacement for every negation on a table.

### 5.2. Combining Required and Excluded Terms

~~~sql
SELECT
    article_id,
    title
FROM articles
WHERE MATCH(title, body)
      AGAINST('+mysql +index -oracle' IN BOOLEAN MODE)
  AND status = 'PUBLISHED';
~~~

Here FULLTEXT filters content; the `status` condition filters record status. The two layers of conditions have distinct responsibilities and can be combined in the same `WHERE` clause.

## 6. Optional Words

A token without an operator is optional. Rows containing that token may be returned, and the token can contribute to relevance.

~~~sql
SELECT
    article_id,
    title,
    MATCH(title, body)
        AGAINST('mysql index' IN BOOLEAN MODE) AS score
FROM articles
WHERE MATCH(title, body)
      AGAINST('mysql index' IN BOOLEAN MODE);
~~~

With `mysql index`, a document can match `mysql`, `index`, or both. If business logic requires both, you must write `+mysql +index`.

An optional word is not identical to a general SQL `OR` condition. It is interpreted within FULLTEXT's tokenization and relevance context.

## 7. Increasing and Decreasing Relevance with > and <

`>` and `<` adjust a token's contribution to the relevance score:

- `>` increases the relative weight of the token.
- `<` decreases the relative weight of the token.

These two operators do not turn a word into a required or excluded condition. To require a word, still use `+`; to exclude a word, still use `-`.

Example prioritizing articles with `mysql` and boosting priority for `index`:

~~~sql
SELECT
    article_id,
    title,
    MATCH(title, body)
        AGAINST('+mysql >index' IN BOOLEAN MODE) AS score
FROM articles
WHERE MATCH(title, body)
      AGAINST('+mysql >index' IN BOOLEAN MODE)
ORDER BY score DESC, article_id;
~~~

`+mysql` requires `mysql`. `>index` makes the `index` token contribute more strongly to relevance when present; `index` does not become mandatory just because of the greater-than sign.

You can decrease weight:

~~~sql
SELECT
    article_id,
    title,
    MATCH(title, body)
        AGAINST('+mysql <legacy' IN BOOLEAN MODE) AS score
FROM articles
WHERE MATCH(title, body)
      AGAINST('+mysql <legacy' IN BOOLEAN MODE)
ORDER BY score DESC, article_id;
~~~

In this example, `legacy` is an optional token with lower contribution. If you want to exclude documents containing `legacy` completely, replace `<legacy` with `-legacy`.

## 8. Penalizing Score Without Excluding Rows Using ~

The tilde `~` gives a token a negative relevance contribution. Unlike the minus sign, it does not exclude the row from results.

~~~sql
SELECT
    article_id,
    title,
    MATCH(title, body)
        AGAINST('+mysql ~legacy' IN BOOLEAN MODE) AS score
FROM articles
WHERE MATCH(title, body)
      AGAINST('+mysql ~legacy' IN BOOLEAN MODE)
ORDER BY score DESC, article_id;
~~~

Meaning:

- `mysql` is required.
- `legacy` is not an exclusion condition.
- If the document contains `legacy`, its relevance score is reduced.
- The document can still appear if it satisfies the positive condition.

Comparison:

| Expression | Behavior for Rows Containing the Token |
|---|---|
| +mysql -legacy | Excluded if `legacy` is present |
| +mysql ~legacy | Can still be returned, but score is reduced |
| +mysql <legacy | Can still be returned; `legacy` contributes less |

Choose the operator based on product semantics. If content must be prevented from appearing in results, use `-`; if you only want to demote priority, use `~` or `<`.

## 9. Prefix Search with *

The asterisk `*` is the truncation operator, appended to the end of a token to match tokens starting with that prefix.

~~~sql
SELECT
    article_id,
    title
FROM articles
WHERE MATCH(title, body)
      AGAINST('+optim*' IN BOOLEAN MODE);
~~~

The expression can match tokens such as `optimize`, `optimization`, or `optimizer` if they are indexed by the parser as tokens starting with `optim`.

### 9.1. The Asterisk Must Be at the End of the Token

Valid:

~~~text
optim*
+optim*
~~~

Do not place an asterisk at the start to request a suffix match:

~~~text
*ization
~~~

FULLTEXT Boolean mode is not an arbitrary substring matcher. The `*` operator performs token prefix matching and does not support double-sided wildcards like some other pattern-matching tools.

### 9.2. Combining Wildcards with Required Conditions

~~~sql
SELECT article_id, title
FROM articles
WHERE MATCH(title, body)
      AGAINST('+mysql +optim*' IN BOOLEAN MODE);
~~~

Documents must contain `mysql` and a token starting with `optim`.

Wildcards can broaden the set of matched tokens, so keep prefixes reasonably specific. Overly short prefixes can produce many results and make the query less selective.

## 10. Grouping Expressions with Parentheses

Parentheses `()` group tokens together to apply an operator to the whole group or organize complex search conditions.

Example requiring `mysql` and at least one of `index` or `optimizer`:

~~~sql
SELECT article_id, title
FROM articles
WHERE MATCH(title, body)
      AGAINST('+mysql +(index optimizer)' IN BOOLEAN MODE);
~~~

The second group is marked with `+`, so at least one token in the group must match. `mysql` is also an independent required condition.

### 10.1. Grouping with Weights

You can combine parentheses with weighting operators:

~~~sql
SELECT
    article_id,
    title,
    MATCH(title, body)
        AGAINST('+mysql +(>index <optimizer)' IN BOOLEAN MODE) AS score
FROM articles
WHERE MATCH(title, body)
      AGAINST('+mysql +(>index <optimizer)' IN BOOLEAN MODE)
ORDER BY score DESC, article_id;
~~~

The expression requires `mysql` and one of the tokens in the group. `index` has increased relative weight; `optimizer` has decreased relative weight. Grouping helps express compound conditions without splitting into multiple queries.

### 10.2. Do Not Use Parentheses in Place of the Required Operator

Parentheses only group expressions. If you want the entire group to be a required condition, place the `+` operator before the opening parenthesis. Without `+`, do not assume every token inside is required.

## 11. Phrase Search with Double Quotes

Enclose multiple words in double quotes to search for a phrase in the specified order:

~~~sql
SELECT article_id, title
FROM articles
WHERE MATCH(title, body)
      AGAINST('"query optimizer"' IN BOOLEAN MODE);
~~~

The expression searches for the phrase `query optimizer`. This is a different expression from searching for the two individual tokens anywhere in the document.

You can combine phrases with required operators:

~~~sql
SELECT article_id, title
FROM articles
WHERE MATCH(title, body)
      AGAINST('+"query optimizer" +mysql' IN BOOLEAN MODE);
~~~

Documents must contain the phrase `query optimizer` and the token `mysql`.

### 11.1. Phrases Still Depend on the Parser

Phrase search operates on the tokens produced by the FULLTEXT parser. Punctuation and word splitting can affect the token sequence; do not treat phrase matching as a byte-for-byte comparison with the original text snippet.

If a token in the phrase is skipped due to stopwords or token length rules, results may differ from expectations. Test phrases with the actual parser configuration and check the stopword list before exposing them in a search UI.

## 12. Proximity Search with @distance

InnoDB supports the proximity search operator `@distance` in Boolean mode. This operator follows a double-quoted phrase and limits the distance between words in the phrase, measured in number of words.

Example:

~~~sql
SELECT article_id, title
FROM articles
WHERE MATCH(title, body)
      AGAINST('"database optimizer" @5' IN BOOLEAN MODE);
~~~

The query finds documents where the words `database` and `optimizer` appear within the specified distance range. The distance value is a non-negative integer according to the operator's syntax; distance is measured in word positions, not character counts.

### 12.1. Proximity Search vs. Phrase Search

| Search Type | Goal |
|---|---|
| "database optimizer" | Search for a phrase by order and phrase structure |
| "database optimizer" @5 | Allow spacing between words within the proximity range |

Proximity is useful when users want to find two concepts appearing near each other without necessarily being adjacent.

### 12.2. Limitations of @distance

- `@distance` is a feature of InnoDB Boolean full-text search.
- The phrase must be enclosed in double quotes before the distance operator.
- Distance is measured in words recognized by the parser.
- Results still depend on stopwords, token size, and the parser.
- Do not treat proximity search as semantic search or synonym matching.

If the application uses MyISAM or a custom parser, verify the feature and syntax on the exact engine/parser before deploying.

## 13. Combining Operators into Practical Expressions

Boolean mode becomes especially useful when combining operators for specific search goals.

### 13.1. Document Must Have Two Words, Must Not Have a Third

~~~sql
SELECT article_id, title
FROM articles
WHERE MATCH(title, body)
      AGAINST('+mysql +transaction -oracle' IN BOOLEAN MODE);
~~~

Use when users want to narrow the topic clearly.

### 13.2. Match One of Two Complementary Concepts

~~~sql
SELECT article_id, title
FROM articles
WHERE MATCH(title, body)
      AGAINST('+mysql +(index optimizer)' IN BOOLEAN MODE);
~~~

Documents must contain `mysql` and at least one token in the `index`/`optimizer` group.

### 13.3. Prioritize One Word and Penalize Another

~~~sql
SELECT
    article_id,
    title,
    MATCH(title, body)
        AGAINST('+mysql >index ~legacy' IN BOOLEAN MODE) AS score
FROM articles
WHERE MATCH(title, body)
      AGAINST('+mysql >index ~legacy' IN BOOLEAN MODE)
ORDER BY score DESC, article_id;
~~~

`mysql` is required. `index` boosts relevance if present. `legacy` lowers relevance if present without excluding the row.

### 13.4. Search for a Phrase and Exclude Legacy Documents

~~~sql
SELECT article_id, title
FROM articles
WHERE MATCH(title, body)
      AGAINST('+"query optimizer" -legacy' IN BOOLEAN MODE);
~~~

Documents must contain the phrase `query optimizer` and must not contain the token `legacy`.

## 14. Meaning of the Relevance Score

`MATCH() AGAINST()` returns a relevance score for matching rows. In Boolean mode, this score can be used for ranking, but MySQL does not automatically sort results by relevance as it does in natural language mode.

Example:

~~~sql
SELECT
    article_id,
    title,
    MATCH(title, body)
        AGAINST('+mysql index' IN BOOLEAN MODE) AS relevance
FROM articles
WHERE MATCH(title, body)
      AGAINST('+mysql index' IN BOOLEAN MODE)
ORDER BY relevance DESC, article_id ASC;
~~~

`ORDER BY relevance DESC` places higher-scoring documents first. `article_id ASC` serves as a tie-breaker for deterministic ordering when multiple documents share the same score.

### 14.1. Relevance Score Is Not a Probability

A relevance score is neither the probability that a document is correct nor an accuracy percentage. The score depends on:

- The tokens in the search expression.
- Token frequency in the document.
- Token distribution across the indexed dataset.
- Weights and operators in the Boolean expression.
- Parser and stopword configuration.

Do not display the score as a percentage unless the product has a dedicated calibration step.

### 14.2. Scores Can Change as Data Changes

When documents are added, deleted, or updated, the word distribution in the index changes. Relevance scores can shift with the corpus. Therefore:

- Do not store scores as fixed attributes of an article.
- Do not compare scores from two different queries as if they were on the same absolute scale.
- Do not assume the same document will always have the exact same score after the corpus changes.
- Measure ranking quality using query test suites and user evaluation.

### 14.3. Boolean Mode Does Not Auto-Sort by Score

This is a key difference to remember:

| Mode | Sorting Behavior |
|---|---|
| Natural language mode | Results are typically sorted by relevance |
| Boolean mode | Does not automatically sort by relevance |

If the UI needs the best matches first, always write `ORDER BY score DESC` and add a secondary key for stable pagination.

## 15. Boolean Mode vs. Natural Language Mode

Both modes use the FULLTEXT index but interpret the search string differently.

| Aspect | Natural Language Mode | Boolean Mode |
|---|---|---|
| Purpose | Search by natural phrase/keywords | Search by operator-based expression |
| Requiring tokens | No `+` operator | Uses `+` |
| Excluding tokens | No `-` operator | Uses `-` |
| Weight adjustment | No equivalent Boolean syntax | Uses `>`, `<`, `~` |
| Grouping conditions | Does not use Boolean syntax | Uses parentheses |
| Sorting | Typically by relevance | Does not automatically sort by relevance |

Natural language example:

~~~sql
SELECT
    article_id,
    title,
    MATCH(title, body) AGAINST('mysql index') AS score
FROM articles
WHERE MATCH(title, body) AGAINST('mysql index');
~~~

Boolean example:

~~~sql
SELECT
    article_id,
    title,
    MATCH(title, body)
        AGAINST('+mysql +index -oracle' IN BOOLEAN MODE) AS score
FROM articles
WHERE MATCH(title, body)
      AGAINST('+mysql +index -oracle' IN BOOLEAN MODE)
ORDER BY score DESC;
~~~

Boolean mode allows expressing conditions more explicitly. In return, the application must understand how to build expressions and explain to users why a document was kept or excluded.

### 15.1. The 50% Threshold and Boolean Mode

MyISAM natural-language search has a 50% threshold rule: a word appearing in too many rows can be treated as uninformative and omitted from returning results in that mode. That rule does not apply to Boolean mode.

InnoDB natural-language search also does not apply MyISAM's 50% threshold. Therefore, do not explain every result difference between InnoDB and MyISAM with a single blanket threshold; examine engine, mode, parser, and index configuration.

## 16. Parsers, Stopwords, and Token Length

Boolean mode only finds tokens that the FULLTEXT parser places into the index. The query string is parsed according to the corresponding parser rules; a word present in the source text is not guaranteed to exist in the FULLTEXT index.

Common causes:

- The word is in the stopword list.
- The token is shorter than the minimum length.
- The token exceeds the maximum length.
- The parser splits words differently from the application's expectations.
- The language or writing style does not suit the default parser.

### 16.1. InnoDB and MyISAM Token Lengths

Some common default settings:

| Engine | Configuration | Common Default |
|---|---|---:|
| InnoDB | innodb_ft_min_token_size | 3 |
| InnoDB | innodb_ft_max_token_size | 84 |
| MyISAM | ft_min_word_len | 4 |
| MyISAM | ft_max_word_len | 84 |

Actual values may have been changed by an administrator. Check server configuration before concluding why a token cannot be found.

You can inspect several InnoDB variables:

~~~sql
SHOW VARIABLES LIKE 'innodb_ft_min_token_size';
SHOW VARIABLES LIKE 'innodb_ft_max_token_size';
SHOW VARIABLES LIKE 'innodb_ft_enable_stopword';
~~~

For MyISAM, check `ft_min_word_len` and `ft_max_word_len`:

~~~sql
SHOW VARIABLES LIKE 'ft_min_word_len';
SHOW VARIABLES LIKE 'ft_max_word_len';
SHOW VARIABLES LIKE 'ft_stopword_file';
~~~

Changing token size or stopword configuration does not automatically make previously skipped tokens appear in the old index. After changing configuration, rebuild the relevant FULLTEXT indexes following an appropriate operational procedure.

### 16.2. Stopwords

Stopwords are common words excluded from the FULLTEXT index to reduce noise. MySQL provides a default stopword list; InnoDB also supports configuring a custom stopword list at the server or table level per engine mechanics.

For example, if a word is on the stopword list, placing `+` before it cannot turn it into an indexed token. A required condition only applies to tokens that the index can actually look up.

When designing Vietnamese search or domain-specific terminology:

- Inspect the current stopword list.
- Identify which business terms must not be excluded.
- Consider a custom stopword list if appropriate.
- Check the impact on index size and result quality.
- Rebuild the index after changing stopword configuration.

Do not remove all stopwords mechanically. Overly common words can bloat index size and produce many low-value results.

### 16.3. Default Parser and Languages

The default parser splits content into tokens based on MySQL's word boundaries and character rules. For space-separated text like Vietnamese, the default parser generally operates along word boundaries it recognizes; however, punctuation, hyphens, proper noun formatting, and stopwords can still affect results.

For languages that do not use spaces to separate words, such as Chinese, Japanese, or Korean, the default parser may not meet requirements. MySQL provides the `ngram` parser for these languages:

~~~sql
CREATE TABLE multilingual_documents (
    document_id BIGINT UNSIGNED NOT NULL,
    content TEXT NOT NULL,
    PRIMARY KEY (document_id),
    FULLTEXT KEY ft_content (content) WITH PARSER ngram
) ENGINE = InnoDB;
~~~

The `ngram` parser splits text into n-gram sequences. Token size is controlled by the `ngram_token_size` variable; the default is usually 2. This setting directly affects how content is indexed and how queries are parsed.

Do not choose `ngram` merely because documents contain Unicode characters. Choose the parser based on language characteristics, how users enter queries, and real test results.

## 17. InnoDB and MyISAM in Boolean Search

Boolean mode is supported by both InnoDB and MyISAM, though there are implementation and configuration differences.

| Aspect | InnoDB | MyISAM |
|---|---|---|
| FULLTEXT index | Yes | Yes |
| Basic Boolean operators | Yes | Yes |
| Proximity operator @distance | Yes | Not supported like InnoDB |
| Token size setting | innodb_ft_min_token_size / innodb_ft_max_token_size | ft_min_word_len / ft_max_word_len |
| Stopword configuration | Dedicated InnoDB mechanism | Uses MyISAM stopword configuration |
| Transactional storage | Yes | No |

For new applications using InnoDB, note that `@distance` is tied to InnoDB Boolean full-text search. If switching engines or using another parser, re-verify advanced expressions.

## 18. Using Boolean Mode in Applications

Applications typically receive a query from a search box and send an expression to MySQL. Two separate problems must be solved:

1. Protecting the SQL query from SQL injection.
2. Defining which Boolean operators users are allowed to use.

### 18.1. Using Prepared Statements

Never concatenate search strings directly into SQL:

~~~sql
SELECT
    article_id,
    title,
    MATCH(title, body) AGAINST(? IN BOOLEAN MODE) AS score
FROM articles
WHERE tenant_id = ?
  AND status = 'PUBLISHED'
  AND MATCH(title, body) AGAINST(? IN BOOLEAN MODE)
ORDER BY score DESC, article_id ASC
LIMIT ?;
~~~

The application binds the search parameter, `tenant_id`, and `limit` using a prepared statement. If the same expression is used in both `SELECT` and `WHERE`, bind the corresponding value at both positions.

Prepared statements protect SQL structure. They do not automatically restrict Boolean operators inside the search string; `+`, `-`, `*`, or parentheses still carry meaning to the FULLTEXT parser.

### 18.2. Defining Allowed UI Syntax

If the product only wants to support simple keyword search, accept a list of keywords and construct the Boolean expression yourself from validated tokens. If you want to support advanced syntax, define a clear grammar and validate input before sending it to MySQL.

Example product rules:

- Allow `+` to require a word.
- Allow `-` to exclude a word.
- Limit token length and token count.
- Limit parenthesis nesting depth.
- Allow phrase search only if the UI documents how to use it.
- Allow `@distance` only when running InnoDB and properly tested.
- Never allow users to alter tenant or access control conditions through the FULLTEXT string.

Do not arbitrarily strip or escape every special character if the UI claims to support Boolean syntax; doing so can alter query semantics. Choose a clear input contract: normalized free-text search or a Boolean query with a controlled grammar.

### 18.3. Query Limits

A long expression with many branches, phrases, and wildcards can consume significant resources. You can limit:

- Number of tokens in a query.
- Number of groups and parenthesis depth.
- Maximum length of each token.
- Number of phrases.
- Maximum proximity distance.
- Returned row count and query timeout.

Limits should be enforced in the application layer and combined with database monitoring.

## 19. Performance and Operations

A FULLTEXT index makes token lookup much more efficient than scanning content with `LIKE` and a leading wildcard, though cost still depends on token counts, document length, result size, and expression complexity.

### 19.1. Combining FULLTEXT with Relational Indexes

In the `articles` example, the FULLTEXT index serves the content condition; the B-tree index on `tenant_id`, `status`, and `published_at` serves relational conditions. The two index types serve different purposes.

~~~sql
SELECT
    article_id,
    title,
    MATCH(title, body)
        AGAINST('+mysql +index' IN BOOLEAN MODE) AS score
FROM articles
WHERE tenant_id = 42
  AND status = 'PUBLISHED'
  AND published_at >= '2026-01-01'
  AND MATCH(title, body)
      AGAINST('+mysql +index' IN BOOLEAN MODE)
ORDER BY score DESC, article_id
LIMIT 20;
~~~

Check the execution plan and actual row counts on representative data. Do not assume relational indexes and the FULLTEXT index will always be combined in the exact desired order based solely on the order of conditions in `WHERE`.

### 19.2. Reading EXPLAIN

~~~sql
EXPLAIN
SELECT article_id, title
FROM articles
WHERE tenant_id = 42
  AND MATCH(title, body)
      AGAINST('+mysql +index' IN BOOLEAN MODE);
~~~

Check:

- Whether the FULLTEXT index is chosen for the `MATCH()` condition.
- Whether the estimated row count is reasonable.
- Whether `tenant`/`status` conditions are applied efficiently.
- Whether there is significant sorting or extra processing.
- Whether the Boolean expression returns too many intermediate rows.

If you need to inspect actual row counts and timings, you can use `EXPLAIN ANALYZE` on supported versions:

~~~sql
EXPLAIN ANALYZE
SELECT article_id, title
FROM articles
WHERE MATCH(title, body)
      AGAINST('+mysql +index' IN BOOLEAN MODE);
~~~

`EXPLAIN ANALYZE` executes the query to measure it. Use it only with appropriate read queries and representative data; do not confuse it with `EXPLAIN`, which only inspects the plan.

### 19.3. FULLTEXT Indexes Are Updated Along with Data

With InnoDB, `INSERT`, `UPDATE`, and `DELETE` operations that modify indexed content are reflected in the FULLTEXT index according to engine mechanics. The application does not need to maintain a separate auxiliary keyword table just for basic index updates.

Nevertheless, monitor:

- Write latency when documents are long or update volume is high.
- FULLTEXT index size.
- Latency and resource usage during bulk loads or rebuilds.
- Impact of changes to parser, stopwords, and token size.

If tokenization settings change, plan a rebuild and verify results after rebuilding before rolling out the new configuration to production.

### 19.4. When LIKE Is More Appropriate

FULLTEXT searches by tokens and parser rules. If the requirement is arbitrary substring matching—for example, a code snippet inside a long string—`LIKE` may express it more accurately:

~~~sql
SELECT article_id, title
FROM articles
WHERE title LIKE '%abc-123%';
~~~

`LIKE` with a leading wildcard typically cannot leverage a B-tree index the way a prefix search can. For large datasets, consider normalized columns, ngram, or a specialized search system depending on requirements.

## 20. Common Mistakes

### 20.1. Forgetting the Plus Operator

The query author wants both words but writes:

~~~text
mysql index
~~~

These are optional words. If both must appear, use:

~~~text
+mysql +index
~~~

### 20.2. Using Minus When Only Lowering Score Was Intended

~~~text
+mysql -legacy
~~~

excludes rows containing `legacy` from the result set that must contain `mysql`. If you only want to lower the score of rows containing `legacy`, use:

~~~text
+mysql ~legacy
~~~

Rows containing `mysql` can still be returned even if they contain `legacy`, but their relevance score is reduced.

Choose according to business requirements; do not conflate exclusion with down-weighting.

### 20.3. Having Only Excluded Words

The expression `-oracle` does not produce a result set of all documents without `oracle`. Include at least one positive condition, or use an appropriate SQL condition if the problem is a full-table negation.

### 20.4. Boolean Mode Does Not Auto-Sort by Relevance

If the UI needs the most relevant articles first, you must select the score and use `ORDER BY score DESC`. Do not rely on incidental row return order.

### 20.5. Searching for a Too-Short Word or Stopword

A token may be absent from the FULLTEXT index due to token size or stopword configuration. Check configuration and parser before concluding `MATCH()` is broken.

### 20.6. MATCH() Does Not Match a FULLTEXT Index

With InnoDB, the columns in `MATCH()` must match a FULLTEXT index in exact column list and order. If you need to search multiple column combinations, design corresponding indexes or adjust the query.

### 20.7. Expecting Wildcard * to Match Substrings

`optim*` matches tokens starting with `optim`. It does not match a substring appearing in the middle of a token. Use `LIKE` or another search tool if substring search is required.

### 20.8. Using @distance on an Unsupported Engine

`@distance` is an InnoDB Boolean search proximity feature. Verify storage engine and parser before using it.

### 20.9. Assuming Prepared Statements Disable Boolean Operators

Prepared statements prevent data from altering SQL structure, but the bound string is still interpreted by the FULLTEXT parser. If the application does not want users entering operators, restrict the grammar in the application layer.

### 20.10. Forgetting Access Control Filters

The FULLTEXT index does not know which documents the current user is allowed to view. Always combine tenant, status, ACL, or data-scope conditions according to the security design.

## 21. Practice Exercises

The exercises use the `articles` table and `ft_articles_title_body` FULLTEXT index from the beginning of the lesson.

### 21.1. Require Two Words

Write a query that only returns articles containing both `mysql` and `index`. Return `article_id`, `title`, and the relevance score; sort by score descending.

### 21.2. Exclude a Topic

Extend the previous query to exclude documents containing `oracle`. Explain why this condition is not equivalent to querying all rows that do not contain `oracle`.

### 21.3. Optional Words and Required Words

Compare the results of three expressions:

~~~text
mysql index
+mysql index
+mysql +index
~~~

State clearly which tokens are required and which are optional in each expression.

### 21.4. Adjust Relevance

Write a query requiring `mysql`, boosting `index`, and lowering the contribution of `legacy`. Then replace the down-weighting operator with the exclusion operator and compare the row sets.

### 21.5. Prefix Search

Find documents containing a token starting with `optim`. Try a shorter prefix and observe both result count and query time.

### 21.6. Group Conditions

Write an expression requiring `mysql` and at least one of the two tokens `index` or `optimizer`. Try removing the `+` before the group and explain the change.

### 21.7. Phrase and Proximity Search

Search for the phrase `query optimizer`. Then test proximity search on InnoDB with distance 5. Compare results and explain why proximity is not semantic search.

### 21.8. Combine Access Control

Write a Boolean query that searches only matching content within the current user's `tenant_id` and returns only `PUBLISHED` articles. Explain why `tenant` and `status` must be in SQL conditions.

### 21.9. Investigate Missing Tokens

Pick a short word or a stopword. Check token size and stopword configuration. Explain why adding `+` cannot force MySQL to find a token that is not in the index.

### 21.10. Design an Input Grammar

Propose a grammar for a search box supporting:

- Required words.
- Excluded words.
- Phrases.
- Condition groups.

Specify limits on token count, query length, and group depth. Distinguish SQL injection protection from Boolean operator control.

## 22. Pre-Release Checklist for Boolean Search

- [ ] Table engine supports FULLTEXT and satisfies the required syntax.
- [ ] A FULLTEXT index exists on the exact columns passed to `MATCH()`.
- [ ] With InnoDB, column order in `MATCH()` matches the index.
- [ ] Users/developers understand the difference between required, optional, and excluded words.
- [ ] Expressions with only excluded words are handled per product intent.
- [ ] Use `>` and `<` to tune relevance, not confused with required conditions.
- [ ] Use `~` to penalize score, not confused with the `-` exclusion operator.
- [ ] Use `*` at the end of a token for prefix search.
- [ ] Use parentheses to group conditions and test nested expressions.
- [ ] Phrase search and `@distance` are tested on the actual parser/engine.
- [ ] Checked stopword list and token size.
- [ ] Tested parser with real language and data.
- [ ] Rebuilt FULLTEXT indexes after applying tokenization changes.
- [ ] Included `ORDER BY relevance DESC` if the product requires ranking.
- [ ] Included a deterministic tie-breaker key for pagination.
- [ ] Used prepared statements for search values and SQL parameters.
- [ ] Boolean grammar is constrained to match UI capabilities.
- [ ] Tenant, ACL, status, and business filters are enforced in SQL.
- [ ] Ran `EXPLAIN` or `EXPLAIN ANALYZE` on representative data.
- [ ] Measured result counts, query time, and FULLTEXT index update cost.

## Conclusion

Boolean mode enables controlling FULLTEXT search with operators. `+` requires a token to appear; `-` excludes a token; tokens without operators are optional; `>` and `<` adjust relevance contribution; `~` reduces score without excluding the row; `*` matches prefixes; parentheses group expressions; double quotes match phrases; and `@distance` supports proximity search in InnoDB.

Final results always depend on the tokens indexed by the parser. Stopwords, token size, engine, and parser can prevent a word in the query string from participating in search as expected. In applications, use prepared statements, control Boolean grammar, enforce authorization conditions in SQL, and sort by relevance explicitly when ranking is needed.
