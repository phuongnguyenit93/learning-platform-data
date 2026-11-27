# Stopwords, Token Length, and Index Build Configuration

MySQL Full-Text Search does not index every character sequence appearing in text. Before writing a word into a FULLTEXT index, the parser splits text into tokens, removes stopwords, and drops tokens outside the configured length limits. Consequently, a phrase present in a TEXT column may still not be found if it is a stopword, too short, too long, or not recognized by the parser in the way the application expects.

Three configuration groups directly affect results:

- **Stopwords**: common words excluded from the index to reduce noise.
- **Token length**: length bounds for tokens allowed into the index.
- **Parser and index build**: how tokens are split, settings applied to InnoDB/MyISAM/ngram, and when a FULLTEXT index must be rebuilt.

Configuration values for InnoDB and MyISAM are not shared. The ngram parser has its own token rules and ignores standard min/max word length variables. Changing configuration after an index has been created also does not automatically fix old tokens; the FULLTEXT index must be rebuilt so index data reflects the new policy.

This lesson focuses on understanding the index-building pipeline, choosing stopwords and token sizes appropriate to your data, configuring per storage engine, rebuilding indexes safely, and verifying the actual tokens stored by MySQL.

## Learning Objectives

After this lesson, you will be able to:

- Explain the parser, tokens, stopwords, and inverted index in MySQL Full-Text Search.
- Identify why a word present in text cannot be found.
- Distinguish between InnoDB and MyISAM default stopword lists.
- View InnoDB's default stopword list.
- Create a custom stopword table server-wide or for a specific InnoDB FULLTEXT index.
- Configure MyISAM's stopword file and understand how to disable stopword filtering.
- Distinguish InnoDB min/max token size from MyISAM min/max word length.
- Understand the impact of token size on index size and searchability.
- Use the ngram parser for Chinese, Japanese, Korean, and non-space-delimited data.
- Explain how ngram handles stopwords and whitespace.
- Create FULLTEXT indexes on single or multiple columns.
- Identify which configuration changes require a restart and which require an index rebuild.
- Rebuild InnoDB and MyISAM FULLTEXT indexes properly.
- Inspect tokens in INFORMATION_SCHEMA and diagnose search results.
- Plan controlled index configuration rollouts in production.

## 1. How Does a FULLTEXT Index Create Tokens?

A FULLTEXT index is an inverted index: instead of storing each row and searching text by scanning full strings, MySQL stores the mapping between tokens and the documents/rows containing them.

High-level pipeline:

    Text in column
          |
          v
      FULLTEXT parser
          |
          v
      Split into tokens
          |
          v
      Stopword check
          |
          v
      Token length check
          |
          v
      Write token to FULLTEXT index
          |
          v
      MATCH(...) AGAINST(...)

Example text:

    MySQL is a relational database.

The standard parser identifies words based on word boundaries. Stopwords such as `a` may be dropped. Tokens shorter than the minimum or longer than the maximum limit may not be written to the index. Remaining tokens are indexed to serve MATCH ... AGAINST.

Therefore, seeing a word in `SELECT body` does not prove that the word exists in the FULLTEXT index.

### 1.1. Three Concepts to Keep Separate

| Concept | Meaning | Example |
|---|---|---|
| Token | Text unit produced by the parser | `database` |
| Stopword | Token excluded per stopword list | `the`, `and` |
| Token length | Length limits for indexed tokens | InnoDB defaults to min 3 characters |

Stopwords and token length are two independent filters. A token can be long enough yet still be excluded because it is on the stopword list. Conversely, a non-stopword can still be excluded because it is too short or too long.

### 1.2. Why Exclude Certain Tokens?

Words that occur too frequently usually provide little help in distinguishing documents. If every article contains `the`, `is`, or `and`, indexing them can bloat the index and degrade ranking quality.

Length limits also help control index growth. Very short words often carry little information in some languages; overly long strings may be codes, random strings, or data that are not typical search terms.

However, default policies do not fit every data domain. In technical documentation, short terms like `SQL`, `C++`, or product codes can be crucial. In Vietnamese, Chinese, Japanese, or Korean, word segmentation also requires special consideration.

## 2. Storage Engine Determines the Token Configuration Set

MySQL maintains separate variables for InnoDB and MyISAM FULLTEXT indexes:

| Setting | InnoDB | MyISAM |
|---|---|---|
| Shortest token | `innodb_ft_min_token_size` | `ft_min_word_len` |
| Longest token | `innodb_ft_max_token_size` | `ft_max_word_len` |
| Default stopwords | Built-in InnoDB list | Built-in MyISAM list |
| Custom list | InnoDB stopword table | File specified by `ft_stopword_file` |
| Disable stopwords | `innodb_ft_enable_stopword=OFF` | `ft_stopword_file=''` |
| ngram parser | Yes | Yes |

Do not change `ft_min_word_len` and expect an InnoDB FULLTEXT index to change. Conversely, `innodb_ft_min_token_size` does not control MyISAM indexes.

### 2.1. Common Default Values

| Engine | Minimum | Maximum |
|---|---:|---:|
| InnoDB | 3 | 84 |
| MyISAM | 4 | 84 |

These are MySQL 8.4 defaults. Check the actual configuration on your server because an administrator may have changed them.

With default configuration:

- InnoDB can index the word `SQL` (3 characters), but skips `DB` (2 characters).
- MyISAM skips both `SQL` and `DB` by default because its minimum is 4.
- Words longer than the maximum are not added to the FULLTEXT index.

Limits are applied when building the index. Merely changing configuration variables without rebuilding the index leaves the old index reflecting the old policy.

### 2.2. Checking Running Configuration

    SHOW GLOBAL VARIABLES LIKE 'innodb_ft_min_token_size';
    SHOW GLOBAL VARIABLES LIKE 'innodb_ft_max_token_size';
    SHOW GLOBAL VARIABLES LIKE 'innodb_ft_enable_stopword';
    SHOW GLOBAL VARIABLES LIKE 'innodb_ft_server_stopword_table';
    SHOW GLOBAL VARIABLES LIKE 'innodb_ft_user_stopword_table';

    SHOW GLOBAL VARIABLES LIKE 'ft_min_word_len';
    SHOW GLOBAL VARIABLES LIKE 'ft_max_word_len';
    SHOW GLOBAL VARIABLES LIKE 'ft_stopword_file';
    SHOW GLOBAL VARIABLES LIKE 'ngram_token_size';

You can query multiple variables at once:

    SELECT
        @@GLOBAL.innodb_ft_min_token_size,
        @@GLOBAL.innodb_ft_max_token_size,
        @@GLOBAL.innodb_ft_enable_stopword,
        @@GLOBAL.ft_min_word_len,
        @@GLOBAL.ft_max_word_len,
        @@GLOBAL.ngram_token_size;

If your account lacks permission to read certain variables or metadata, ask a DBA to check with appropriate privileges. Do not infer server configuration from a single `my.cnf` file alone, since the server may read multiple option files or receive startup flags.

## 3. What Are Stopwords and How Do They Affect Search Results?

Stopwords are words excluded from the FULLTEXT index based on a configured list. When querying, a word excluded from the index generally cannot be found via standard token search, even though the word remains in the text column.

Example:

    CREATE TABLE articles (
        id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
        title VARCHAR(255),
        body TEXT,
        FULLTEXT KEY ft_articles (title, body)
    ) ENGINE=InnoDB;

If `body` contains:

    The database is available for SQL queries.

Words in InnoDB's stopword list are not written to the FULLTEXT index. Searching for `database` can return results; searching for a stopword like `the` alone may return no matching rows.

### 3.1. Stopwords Do Not Delete Original Text

Stopword filtering only affects the FULLTEXT index. Content inside `title`/`body` columns remains intact:

    SELECT id, body
    FROM articles
    WHERE id = 1;

Stopwords are not deleted from the table, modified in strings, or hidden from standard `LIKE` comparisons. They are simply omitted from the FULLTEXT index.

### 3.2. InnoDB and MyISAM Lists Differ

InnoDB has a relatively short default list. This list is designed to retain many short words that can be meaningful in technical documents, literature, or phrases.

MyISAM has a longer default list managed through a built-in stopword list mechanism.

Do not assume the same query will produce identical results on both engines if they use different default stopwords.

### 3.3. Viewing InnoDB Default Stopwords

    SELECT value
    FROM INFORMATION_SCHEMA.INNODB_FT_DEFAULT_STOPWORD
    ORDER BY value;

This INFORMATION_SCHEMA table displays InnoDB's default stopword list. Accounts require appropriate privileges; MySQL documentation requires the `PROCESS` privilege to query this table.

Some words in the default list:

    a
    about
    an
    are
    as
    at
    be
    by
    for
    from
    in
    is
    it
    of
    on
    or
    the
    this
    to
    with

These are illustrative examples only. Query INFORMATION_SCHEMA on your server to obtain the exact list for your running version.

### 3.4. Collation Affects Stopword Comparison

The stopword list is loaded and matched using the server character set/collation, specifically `character_set_server` and `collation_server`.

Case sensitivity depends on collation:

- A case-insensitive collation treats `The` and `the` as equivalent.
- A case-sensitive or binary collation may treat them as distinct.

If a stopword file or stopword table uses a different character set/collation from the server or indexed columns, false hits or false misses can occur. When designing custom stopwords, verify character set, collation, and case normalization.

## 4. Custom Stopword Configuration for InnoDB

InnoDB supports three ways to define a stopword list:

1. Use the built-in default list.
2. Use a server-wide stopword table via `innodb_ft_server_stopword_table`.
3. Use a per-table/index stopword table via `innodb_ft_user_stopword_table`.

`innodb_ft_enable_stopword` enables or disables associating a stopword list with a FULLTEXT index when the index is created.

If both user stopword table and server stopword table are configured, InnoDB prefers the user stopword table. If no user table is set but a server table is, it uses the server table. If neither is set, it uses the default list.

### 4.1. Creating a Properly Structured Stopword Table

A stopword table must:

- Use the InnoDB storage engine.
- Have a single VARCHAR column named `value`.
- Be created before setting the variable pointing to the table.

The examples below assume schema `app` already exists. Select that schema before running or replace `app` with your actual schema.

Example:

    USE app;

    CREATE TABLE app_search_stopwords (
        value VARCHAR(100) NOT NULL
    ) ENGINE=InnoDB
      DEFAULT CHARSET=utf8mb4;

    INSERT INTO app_search_stopwords(value)
    VALUES
        ('internal'),
        ('draft'),
        ('placeholder');

The sample list above fits a hypothetical application. Do not copy stopwords from another domain without evaluating business meaning.

### 4.2. Using a Server-Wide Stopword Table

Set global variables before creating the FULLTEXT index:

    SET GLOBAL innodb_ft_enable_stopword = ON;

    SET GLOBAL innodb_ft_server_stopword_table =
        'app/app_search_stopwords';

Then create the index:

    CREATE FULLTEXT INDEX ft_articles
    ON articles(title, body);

The stopword table must exist before setting the variable. The server stopword table variable applies to InnoDB FULLTEXT indexes created under that configuration.

Changing the variable does not automatically update tokens already written to old indexes. If you want an existing index to use the new list, rebuild the index.

### 4.3. Using a Stopword Table for a Specific Table

You can use `innodb_ft_user_stopword_table` to specify a list for a specific index/table. This variable supports both SESSION and GLOBAL scope; the common way to limit scope is to set SESSION in the connection creating the index:

    CREATE TABLE article_search_stopwords (
        value VARCHAR(100) NOT NULL
    ) ENGINE=InnoDB
      DEFAULT CHARSET=utf8mb4;

    INSERT INTO article_search_stopwords(value)
    VALUES ('internal'), ('draft');

    CREATE TABLE articles_custom (
        id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
        title VARCHAR(255),
        body TEXT
    ) ENGINE=InnoDB
      DEFAULT CHARSET=utf8mb4;

    SET SESSION innodb_ft_enable_stopword = ON;

    SET SESSION innodb_ft_user_stopword_table =
        'app/article_search_stopwords';

    CREATE FULLTEXT INDEX ft_article_search
    ON articles_custom(title, body);

The user stopword table is bound to the specific InnoDB table when the FULLTEXT index is created. Ensure `CREATE FULLTEXT INDEX` runs in the same session where `innodb_ft_user_stopword_table` was set. Document the configuration used to create the index in migrations or operational runbooks.

### 4.4. Disabling Stopword Filtering in InnoDB

If business requirements demand searching even common words, you can disable stopword filtering:

    SET GLOBAL innodb_ft_enable_stopword = OFF;

Or set it in the configuration file before creating the index:

    [mysqld]
    innodb_ft_enable_stopword=OFF

This variable is dynamic, but existing FULLTEXT indexes still need to be rebuilt for the new policy to take effect on indexed data.

Disabling stopwords can make indexes larger and increase the number of common tokens matched. Measure storage size, build time, and result quality before applying system-wide.

## 5. Stopword Configuration for MyISAM

MyISAM uses the `ft_stopword_file` variable to select a stopword file.

- If a relative filename is used, the server searches for the file in the data directory.
- An absolute path can be used to specify another location.
- The file contains the stopword list; words are separated by non-alphanumeric characters such as newlines, spaces, or commas.
- Underscores and single quotes have special rules: they are treated as word characters.
- The file uses the server's default character set.

Example file path:

    /etc/mysql/myisam-stopwords.txt

Contents:

    internal
    draft
    placeholder

In the option file:

    [mysqld]
    ft_stopword_file=/etc/mysql/myisam-stopwords.txt

The server must be able to read the file under the OS user running MySQL.

### 5.1. Disabling Stopword Filtering for MyISAM

Set the variable to an empty string:

    [mysqld]
    ft_stopword_file=''

This disables stopword filtering for MyISAM FULLTEXT indexes. Do not apply this approach to configure InnoDB.

### 5.2. Changing the Stopword File

When changing the file path or contents:

1. Prepare the new file and verify MySQL read permissions.
2. Update the option file or startup parameters.
3. Restart MySQL to load the new configuration/file.
4. Rebuild affected MyISAM FULLTEXT indexes.
5. Test queries with previously excluded words and newly excluded words.

Simply editing the file on disk without restarting and rebuilding will not change existing indexes.

## 6. InnoDB Token Length

InnoDB uses two variables:

- `innodb_ft_min_token_size`: minimum length.
- `innodb_ft_max_token_size`: maximum length.

Defaults:

| Variable | Default Value | MySQL 8.4 Range |
|---|---:|---:|
| innodb_ft_min_token_size | 3 | 0 to 16 |
| innodb_ft_max_token_size | 84 | 10 to 84 |

These are GLOBAL, non-dynamic variables; they must be configured at server startup. `innodb_ft_min_token_size` is the minimum number of characters for a word stored in an InnoDB FULLTEXT index. `innodb_ft_max_token_size` is the maximum character length.

### 6.1. Example: Changing Minimum Token Size

Suppose technical docs need to search short codes `DB` and `UI`. The default minimum of 3 skips 2-character tokens.

In the option file:

    [mysqld]
    innodb_ft_min_token_size=2
    innodb_ft_max_token_size=84

After saving the configuration:

1. Restart MySQL.
2. Verify actual values via SHOW VARIABLES.
3. Rebuild FULLTEXT indexes on affected InnoDB tables.
4. Run tests with 2-character tokens.

Do not just restart and assume you are done. Existing indexes were built with the old threshold and must be rebuilt.

### 6.2. Increasing Minimum to Reduce Index Size

If the system only searches words longer than 4 characters, raising the minimum can reduce stored tokens and index size. However, meaningful short words such as error codes, product names, or technical terms may be dropped.

Before increasing the minimum, analyze real queries to identify important short tokens. Do not decide based on index size alone.

### 6.3. Maximum Token Size

Tokens longer than `innodb_ft_max_token_size` are omitted from the index. Lowering the maximum can reduce index size but sacrifices the ability to search long identifier strings.

Do not pick a small maximum just because most natural-language words are short. Check product codes, URLs, package names, identifiers, and domain terms.

## 7. MyISAM Word Length

MyISAM uses:

- `ft_min_word_len`: minimum word length.
- `ft_max_word_len`: maximum word length.

Defaults:

| Variable | Default Value | MySQL 8.4 Range |
|---|---:|---:|
| ft_min_word_len | 4 | 1 to 82 |
| ft_max_word_len | 84 | 10 to 84 |

Both variables are GLOBAL and non-dynamic. They are read at server startup.

Example configuration:

    [mysqld]
    ft_min_word_len=2
    ft_max_word_len=84

After restarting, MyISAM FULLTEXT indexes must be rebuilt.

### 7.1. Rebuilding MyISAM After Changing Token Size

You can use:

    REPAIR TABLE articles QUICK;

Or use ALTER TABLE to drop and recreate the FULLTEXT index. MySQL documentation notes that a QUICK repair is sufficient to rebuild MyISAM FULLTEXT indexes after such changes.

If using `myisamchk` to repair indexes outside the server, pass `ft_min_word_len`, `ft_max_word_len`, and `ft_stopword_file` matching the server configuration. Otherwise, `myisamchk` may rebuild the index using default values and cause search results to diverge.

### 7.2. Do Not Confuse MyISAM and InnoDB Settings

For example:

- `ft_min_word_len=2` only affects MyISAM.
- `innodb_ft_min_token_size=2` only affects InnoDB.

If an application uses both engines, configure and rebuild each group of indexes according to its own engine.

## 8. The ngram Parser and Token Size

The standard parser relies on word boundaries. For Chinese, Japanese, Korean, and content without clear whitespace word delimiters, the standard parser may not produce the desired tokens.

MySQL provides a built-in ngram parser. Ngram splits strings into fixed-length character groups, commonly called n-grams.

With `ngram_token_size=2`, the string:

    database

is split into:

    da
    at
    ta
    ab
    ba
    as
    se

For the string `abc def`, the ngram parser generates tokens `ab`, `bc`, `de`, `ef`; whitespace is stripped during parsing.

### 8.1. Configuring ngram_token_size

Defaults:

| Variable | Value |
|---|---:|
| ngram_token_size | 2 |
| Minimum | 1 |
| Maximum | 10 |

`ngram_token_size` is a read-only variable configurable only at server startup via option file or command-line arguments.

Example:

    [mysqld]
    ngram_token_size=2

Changing `ngram_token_size` requires restarting the server and rebuilding FULLTEXT indexes that use the ngram parser.

### 8.2. Minimum/Maximum Word Length Does Not Apply to ngram

For FULLTEXT indexes using the ngram parser, the following variables are ignored:

- `innodb_ft_min_token_size`
- `innodb_ft_max_token_size`
- `ft_min_word_len`
- `ft_max_word_len`

Token length for ngram is controlled solely by `ngram_token_size`. Do not lower `innodb_ft_min_token_size` to troubleshoot Chinese search when the index uses ngram; check `ngram_token_size` and rebuild the index.

### 8.3. Creating a FULLTEXT Index with ngram

    CREATE TABLE articles_cjk (
        id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
        title VARCHAR(200),
        body TEXT,
        FULLTEXT KEY ft_articles_cjk (title, body)
            WITH PARSER ngram
    ) ENGINE=InnoDB
      DEFAULT CHARSET=utf8mb4;

Or add it to an existing table:

    ALTER TABLE articles_cjk
    ADD FULLTEXT INDEX ft_articles_cjk (title, body)
        WITH PARSER ngram;

The ngram parser is built into MySQL; no separate plugin installation is required.

### 8.4. Choosing ngram_token_size

Small token size:

- Generates more overlapping tokens.
- Can support shorter queries.
- Usually produces a larger index and higher processing cost.

Large token size:

- Generates fewer tokens.
- Can reduce index size.
- Unsuitable if the application needs to search very short phrases.

Choose based on actual search phrase lengths, language, and workload. No single value is optimal for every dataset.

### 8.5. Special Notes for Vietnamese Search

The standard parser splits text along word boundaries recognized by MySQL, typically spaces and delimiters. In Vietnamese, a word can consist of multiple space-separated syllables. For example, the phrase `cơ sở dữ liệu` (database) may be split into tokens `cơ`, `sở`, `dữ`, and `liệu` rather than a single token representing the entire concept.

With InnoDB's default minimum of 3, many two-character syllables such as `cơ`, `sở`, or `dữ` may be excluded from the index. Lowering the minimum to 2 indexes those syllables, but also increases common tokens. The default stopword list is geared toward English, so do not assume it filters Vietnamese function words semantically.

The ngram parser creates fixed-length character groups, not a Vietnamese word segmenter. It can assist substring matching, yet also generates overlapping tokens and may return different results from word-based search. If the application requires semantic Vietnamese word segmentation, consider an application-layer tokenizer or a dedicated search pipeline; when using MySQL FULLTEXT, test on a real Vietnamese corpus and measure false positives/false negatives before choosing a parser.

## 9. Stopwords with ngram Follow Different Rules

The standard parser drops a token if the token equals an entry in the stopword list.

The ngram parser behaves differently: it drops an ngram token if that token **contains** a stopword. Therefore, a single short stopword can cause many ngrams to be dropped.

For example, with `ngram_token_size=2`, the text `a,b` produces tokens `a,` and `,b`. If the comma is defined as a stopword, both tokens are dropped because each contains a comma.

### 9.1. Default Stopwords for ngram

By default, the ngram parser uses MySQL's default stopword list, which contains English stopwords. For Chinese, Japanese, or Korean, consider a custom stopword list appropriate for the language.

Stopwords longer than `ngram_token_size` are ignored. For example, with token size 2, a 3-character stopword is not used to filter ngrams.

### 9.2. Example of Stopword Impact

Suppose:

    ngram_token_size=2

and the stopword list contains the word `a`. Text can produce bigrams containing the character `a`; tokens containing that stopword are dropped. Consequently, searching a short word containing characters matching stopwords may yield unexpected results.

When configuring ngram for CJK data, do not look only at the number of stopwords. Test indexing representative phrases, inspect actual tokens, and verify search results.

### 9.3. An Unsuitable Stopword List Can Lose Signal

If the stopword list contains punctuation, symbols, or characters common in product codes, the ngram parser may drop many useful tokens. Do not add delimiters to the stopword list arbitrarily.

## 10. Building FULLTEXT Indexes

FULLTEXT indexes support CHAR, VARCHAR, or TEXT columns on FULLTEXT-capable storage engines such as InnoDB and MyISAM.

### 10.1. Creating an InnoDB Table and Index

    CREATE TABLE articles (
        id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
        title VARCHAR(255) NOT NULL,
        body MEDIUMTEXT NOT NULL,
        published_at DATETIME NOT NULL,
        FULLTEXT KEY ft_title_body (title, body)
    ) ENGINE=InnoDB
      DEFAULT CHARSET=utf8mb4;

A FULLTEXT index can cover multiple columns. When querying with `MATCH()`, the column list must match the column list of an appropriate FULLTEXT index.

Example:

    SELECT
        id,
        MATCH(title, body)
            AGAINST ('database indexing' IN NATURAL LANGUAGE MODE)
            AS relevance
    FROM articles
    WHERE MATCH(title, body)
        AGAINST ('database indexing' IN NATURAL LANGUAGE MODE)
    ORDER BY relevance DESC;

### 10.2. Creating an Index After the Table Has Data

    ALTER TABLE articles
    ADD FULLTEXT INDEX ft_title_body (title, body);

When building a FULLTEXT index, MySQL must read existing data, tokenize it, and build the inverted index. Large tables can consume significant CPU, I/O, memory, and disk space.

### 10.3. MyISAM Index

Example:

    CREATE TABLE legacy_articles (
        id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
        title VARCHAR(255),
        body TEXT,
        FULLTEXT KEY ft_legacy_articles (title, body)
    ) ENGINE=MyISAM
      DEFAULT CHARSET=utf8mb4;

MyISAM token size and stopword settings apply separately as described in earlier sections.

### 10.4. Index Using ngram

    CREATE TABLE product_descriptions (
        id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
        product_name VARCHAR(255),
        description TEXT,
        FULLTEXT KEY ft_product_text (product_name, description)
            WITH PARSER ngram
    ) ENGINE=InnoDB
      DEFAULT CHARSET=utf8mb4;

Choose the parser before creating the index. If you change the parser or `ngram_token_size`, you must rebuild the corresponding index.

## 11. Configure Before Creating the Index

A common deployment mistake is creating the FULLTEXT index first and only adjusting token size or the stopword list afterward. By then, the index has already been built using the old settings.

The workflow should be:

1. Identify the storage engine.
2. Decide between the standard parser or ngram.
3. Determine the shortest/longest tokens that need to be searchable.
4. Define the stopword list.
5. Configure system variables and option files.
6. Restart if variables require startup configuration.
7. Create or rebuild FULLTEXT indexes.
8. Verify tokens and search results.

### 11.1. Example InnoDB Configuration for 2-Character Tokens

    [mysqld]
    innodb_ft_min_token_size=2
    innodb_ft_max_token_size=84

After restarting, rebuild the InnoDB FULLTEXT index:

    ALTER TABLE articles
    DROP INDEX ft_title_body,
    ADD FULLTEXT INDEX ft_title_body (title, body);

Perform this inside a maintenance window if rebuild time or DDL impact is significant.

### 11.2. Example MyISAM Configuration for 2-Character Tokens

    [mysqld]
    ft_min_word_len=2
    ft_max_word_len=84
    ft_stopword_file=/etc/mysql/myisam-stopwords.txt

After restarting:

    REPAIR TABLE legacy_articles QUICK;

If multiple MyISAM tables contain FULLTEXT indexes, rebuild every affected table. Do not repair just one sample table and forget the rest.

### 11.3. Example ngram Configuration

    [mysqld]
    ngram_token_size=2

After restarting, rebuild FULLTEXT indexes using the ngram parser. Changing `ngram_token_size` does not alter previously created FULLTEXT indexes.

## 12. Which Changes Require a Restart and Rebuild?

| Change | Server Restart | Rebuild FULLTEXT Index |
|---|---|---|
| InnoDB innodb_ft_min_token_size | Yes | Yes |
| InnoDB innodb_ft_max_token_size | Yes | Yes |
| InnoDB innodb_ft_server_stopword_table | Not required (dynamic variable) | Yes |
| InnoDB innodb_ft_user_stopword_table | Not required (dynamic variable) | Yes |
| InnoDB innodb_ft_enable_stopword | Not required (dynamic variable) | Yes |
| InnoDB ngram_token_size | Yes | Yes |
| MyISAM ft_min_word_len | Yes | Yes |
| MyISAM ft_max_word_len | Yes | Yes |
| MyISAM ft_stopword_file or file contents | Yes | Yes |

The InnoDB stopword variables listed above can be dynamic within their documented scope. Even when no restart is needed, existing indexes still require a rebuild for the new token policy to take effect.

For MyISAM, after changing word length or the stopword file, the server must be restarted and then the FULLTEXT indexes rebuilt.

## 13. Rebuilding InnoDB FULLTEXT Indexes

MySQL requires rebuilding InnoDB FULLTEXT indexes after changing any of the following variables:

- innodb_ft_min_token_size
- innodb_ft_max_token_size
- innodb_ft_server_stopword_table
- innodb_ft_user_stopword_table
- innodb_ft_enable_stopword
- ngram_token_size

For changes to min/max token size or `ngram_token_size`, a server restart is required. Stopword changes can be dynamic, yet still require a rebuild.

### 13.1. Drop and Recreate the Index

    ALTER TABLE articles
    DROP INDEX ft_title_body,
    ADD FULLTEXT INDEX ft_title_body (title, body);

If you prefer splitting into two steps:

    ALTER TABLE articles
    DROP INDEX ft_title_body;

    ALTER TABLE articles
    ADD FULLTEXT INDEX ft_title_body (title, body);

Two separate steps create a window during which the table lacks that FULLTEXT index. Plan application behavior and maintenance timing accordingly.

### 13.2. Controlling Rebuild Impact

Before rebuilding:

- Measure table and index sizes.
- Check available disk space.
- Estimate DDL duration and workload impact.
- Check replica lag if replication is active.
- Plan a configuration rollback in case search quality worsens.
- Take a backup or verify recoverability.

Do not assume rebuilding a FULLTEXT index is always online or non-locking. DDL behavior depends on version, engine, table structure, and change type; test in a production-like environment.

### 13.3. OPTIMIZE TABLE Does Not Replace Every Configuration Rebuild

`OPTIMIZE TABLE` on an InnoDB table with a FULLTEXT index can rebuild the index to purge deleted Document IDs and merge entries. This is an index maintenance operation and should not be confused with changing token configuration without following the required rebuild procedure.

When changing token size or stopword policy, follow the documented drop/recreate FULLTEXT index procedure.

## 14. Rebuilding MyISAM FULLTEXT Indexes

After changing `ft_min_word_len`, `ft_max_word_len`, `ft_stopword_file`, or stopword file contents:

1. Restart MySQL.
2. Rebuild FULLTEXT indexes on each affected MyISAM table.

The simplest method:

    REPAIR TABLE legacy_articles QUICK;

You can also use `ALTER TABLE` to drop and recreate the index. `REPAIR TABLE`, `ANALYZE TABLE`, `OPTIMIZE TABLE`, or `ALTER TABLE` are all executed by the server and use the server's full-text configuration.

### 14.1. Notes When Using myisamchk

If using `myisamchk` to operate on MyISAM indexes outside the server, the program must receive the exact same full-text values used by `mysqld`.

Example option file:

    [mysqld]
    ft_min_word_len=3
    ft_max_word_len=84

    [myisamchk]
    ft_min_word_len=3
    ft_max_word_len=84

Without matching parameters, `myisamchk` may rebuild the index with default values, causing search results to diverge from the server. Prefer performing operations through the server unless there is a specific operational reason to use `myisamchk`.

## 15. Inspecting Actual Tokens in InnoDB

Checking configuration variables alone is not enough. Inspect the tokens MySQL actually places into the FULLTEXT index.

### 15.1. Select the Table to Inspect

    SET GLOBAL innodb_ft_aux_table = 'app/articles';

`innodb_ft_aux_table` points to the InnoDB table to observe. Reading FTS INFORMATION_SCHEMA tables may require the `PROCESS` privilege.

### 15.2. View Tokens in the Index

    SELECT
        word,
        doc_count
    FROM INFORMATION_SCHEMA.INNODB_FT_INDEX_TABLE
    ORDER BY word;

`INNODB_FT_INDEX_TABLE` provides information from the inverted index used to process searches.

### 15.3. View New Tokens in the Cache

    SELECT
        word,
        doc_id,
        position
    FROM INFORMATION_SCHEMA.INNODB_FT_INDEX_CACHE
    ORDER BY doc_id, position;

Newly added tokens can sit in the index cache before being synchronized to the main full-text index. The cache is merged when `OPTIMIZE TABLE` runs, when the server shuts down, or when the cache exceeds its configured limit. Therefore, not seeing a token in `INDEX_TABLE` is not enough to conclude the token was never created; check `INDEX_CACHE` and synchronization status.

### 15.4. View Default Stopwords

    SELECT value
    FROM INFORMATION_SCHEMA.INNODB_FT_DEFAULT_STOPWORD
    ORDER BY value;

Cross-check missing words against the stopword list and token size. This is a fast way to distinguish parser behavior from configuration issues.

## 16. Verifying FULLTEXT Indexes and Table Configuration

View DDL:

    SHOW CREATE TABLE articles;

View indexes:

    SHOW INDEX FROM articles;

Or:

    SELECT
        TABLE_SCHEMA,
        TABLE_NAME,
        INDEX_NAME,
        COLUMN_NAME,
        SEQ_IN_INDEX,
        INDEX_TYPE
    FROM INFORMATION_SCHEMA.STATISTICS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'articles'
    ORDER BY INDEX_NAME, SEQ_IN_INDEX;

A FULLTEXT index has `INDEX_TYPE` equal to `FULLTEXT`. Inspect the column list and parser in the DDL when confirming index configuration.

### 16.1. Confirm the Engine

    SELECT
        TABLE_SCHEMA,
        TABLE_NAME,
        ENGINE
    FROM INFORMATION_SCHEMA.TABLES
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'articles';

The engine determines which token length variables and stopword mechanism take effect.

### 16.2. Confirm Character Set/Collation

    SHOW FULL COLUMNS FROM articles;

Or:

    SELECT
        COLUMN_NAME,
        CHARACTER_SET_NAME,
        COLLATION_NAME
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'articles';

Character set/collation can influence how the parser classifies characters and how stopwords are compared. When results deviate from expectations, check column settings alongside server collation.

## 17. Diagnosing Words Present in Text but Not Found

When a word is visible in `title`/`body` yet `MATCH ... AGAINST` returns no rows, check in order:

1. Is the column included in the right FULLTEXT index?
2. Does `MATCH()` use the exact column list of that index?
3. Is the storage engine InnoDB or MyISAM?
4. Is the token shorter than the minimum or longer than the maximum?
5. Is the token on the stopword list?
6. Was the index rebuilt after the most recent configuration change?
7. Does the parser segment words appropriately for the data's language?
8. If using ngram, are `ngram_token_size` and stopword behavior appropriate?
9. Does character set/collation cause differences during tokenization or comparison?
10. Is the query affected by natural language/boolean mode and its mode-specific rules?

### 17.1. Short Word Example

Suppose InnoDB uses the default minimum of 3. The word `DB` has 2 characters and is therefore not indexed by the standard parser.

If the data contains:

    DB server configuration

searching for `DB` may return no rows, whereas searching for `server` returns results.

Possible solutions are lowering `innodb_ft_min_token_size` and rebuilding the index, or designing a separate field/index for short codes. Do not change configuration if most queries do not need short tokens, because the index can grow larger.

### 17.2. Stopword Example

If the word `the` is on the stopword list, it is excluded even though it meets the minimum length. Check:

    SELECT value
    FROM INFORMATION_SCHEMA.INNODB_FT_DEFAULT_STOPWORD
    WHERE value = 'the';

If using a custom list, check the exact stopword table bound to the index.

### 17.3. Wrong Parser Example

Chinese or Japanese text does not use spaces to separate words like English. With the standard parser, tokens may not be created as the application expects.

Try creating a FULLTEXT index with the ngram parser in a test environment, choose `ngram_token_size`, rebuild, and inspect the actual tokens.

## 18. Impact of Configuration on Quality and Cost

There is no single optimal token size configuration for every system. Every choice is a trade-off:

| Change | Potential Benefit | Risk / Cost |
|---|---|---|
| Decrease minimum token size | Find short codes/words | Larger index, more common tokens |
| Increase minimum token size | Smaller index, less noise | Loses meaningful short words |
| Decrease maximum token size | Drops unhelpful very long strings | Loses long identifiers |
| Disable stopwords | Find common words | Larger index, noisier results |
| Add custom stopwords | Filter domain-specific noise words | Might accidentally drop important terms |
| Decrease ngram_token_size | Match shorter phrases | More overlapping tokens, larger index |
| Increase ngram_token_size | Fewer tokens | Harder to match short phrases, possible misses |

### 18.1. Impact on Storage Size and Build Time

Lowering minimum token size usually increases the number of indexed tokens. Small ngram sizes create more overlapping ngrams. Both can enlarge the FULLTEXT index, increasing build cost and maintenance overhead during INSERT/UPDATE/DELETE.

When changing configuration, measure:

- Index size before and after.
- Index rebuild duration.
- CPU, I/O, and memory during build.
- Query response time.
- Result counts and relevance on representative queries.
- Replica lag and binary log volume if replication is used.

### 18.2. MyISAM Natural Language Threshold

MyISAM natural language search has a 50% threshold rule under its default weighting scheme. A word appearing in more than half of the rows may not be returned in natural language mode, even though the token exists in the index.

This is a separate search rule, distinct from stopwords and token length. When inspecting tokens, distinguish "token absent from index" from "token present but omitted by the search mode due to threshold."

Do not modify MySQL source code to change the weighting scheme just to fix one query without fully understanding the impact on relevance. If you need to search common words, consider boolean mode and test the corresponding behavior.

## 19. Designing a Stopword List for Real Data

A stopword list should be built from your application's queries and corpus, not merely copied from the default English list.

### 19.1. Classifying Words Before Adding to Stopwords

Consider:

- Frequency in the corpus.
- How often users search for the word.
- Whether the word has power to distinguish documents.
- Whether the word is a product name, error code, technical term, or proper noun.
- Whether the word can be part of an important search phrase.

A frequent word is not automatically a stopword. For example, `SQL` may appear in many technical articles yet remain an important search keyword.

### 19.2. Language-Specific Stopwords

An English list cannot substitute for a list tailored to Vietnamese, Chinese, Japanese, or Korean. Consider how the parser segments the language, punctuation, word variants, and collation.

With ngram, remember tokens are dropped when they contain a stopword; therefore, an overly broad list or single-character entries can eliminate far more tokens than intended.

### 19.3. Versioning the Stopword List

Manage the stopword list as part of schema/index configuration:

- Store changes in migrations or configuration management.
- Record the effective date and reason for adding/removing words.
- Document which indexes were built with that list.
- Test a query suite before and after.
- Plan index rebuilds whenever the list changes.

Do not edit stopword tables directly in production without recording a migration and rebuild plan.

## 20. Deployment Process for FULLTEXT Configuration Changes

A single stopword/token size change can affect every query using the index. Roll it out under control.

### Step 1: Identify affected engines and indexes

    SELECT
        TABLE_NAME,
        ENGINE
    FROM INFORMATION_SCHEMA.TABLES
    WHERE TABLE_SCHEMA = 'app'
      AND TABLE_NAME IN ('articles', 'product_descriptions');

    SHOW CREATE TABLE app.articles;

Record FULLTEXT indexes, columns, parser, and storage engine.

### Step 2: Collect baseline

Save:

- System variable values.
- Current stopword list.
- Index sizes.
- A representative query suite and its results.
- Response times and relevance scores.

### Step 3: Test configuration in staging

Test token size values, stopword lists, or `ngram_token_size`. Avoid changing multiple parameters simultaneously when you need to isolate what caused result changes.

### Step 4: Configure the server

Edit the option file or set dynamic variables in the appropriate scope. For startup-only variables, schedule a restart.

### Step 5: Restart if needed

Verify the server starts cleanly and running variables reflect the desired values.

### Step 6: Rebuild indexes

Rebuild each affected FULLTEXT index per engine:

- InnoDB: ALTER TABLE DROP INDEX and ADD FULLTEXT INDEX.
- MyISAM: REPAIR TABLE ... QUICK or ALTER TABLE per plan.

### Step 7: Verify

Check:

- SHOW CREATE TABLE and SHOW INDEX.
- INFORMATION_SCHEMA.INNODB_FT_INDEX_TABLE/INDEX_CACHE for InnoDB.
- Queries containing short words, stopwords, long words, and domain terms.
- CJK queries if using ngram.
- Results and relevance compared against the baseline.

### Step 8: Document and monitor

Record configuration, rebuild duration, index sizes, query timings, and any issues encountered. Monitor server load and replication after deployment.

## 21. Hands-On Lab: Testing Token Size and Stopwords

This lab uses InnoDB on a test database. Do not change production server-wide variables solely to run this exercise.

### Step 1: Create the table

    USE app;

    CREATE TABLE fts_lab (
        id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
        title VARCHAR(255),
        body TEXT,
        FULLTEXT KEY ft_lab (title, body)
    ) ENGINE=InnoDB
      DEFAULT CHARSET=utf8mb4;

### Step 2: Insert data

    INSERT INTO fts_lab(title, body)
    VALUES
        ('DB and SQL', 'The DB server stores SQL data.'),
        ('Database guide', 'A database index helps search.'),
        ('Search engine', 'Full text indexing uses tokens.');

### Step 3: View configuration

    SHOW GLOBAL VARIABLES LIKE 'innodb_ft_min_token_size';
    SHOW GLOBAL VARIABLES LIKE 'innodb_ft_max_token_size';
    SHOW GLOBAL VARIABLES LIKE 'innodb_ft_enable_stopword';

### Step 4: Search short word and stopword

    SELECT id,
           MATCH(title, body)
               AGAINST ('DB' IN NATURAL LANGUAGE MODE) AS score
    FROM fts_lab
    WHERE MATCH(title, body)
        AGAINST ('DB' IN NATURAL LANGUAGE MODE);

    SELECT id,
           MATCH(title, body)
               AGAINST ('the' IN NATURAL LANGUAGE MODE) AS score
    FROM fts_lab
    WHERE MATCH(title, body)
        AGAINST ('the' IN NATURAL LANGUAGE MODE);

Observe results under the running configuration. If `DB` is too short or `the` is a stopword, they may not be found.

### Step 5: Inspect default stopwords

    SELECT value
    FROM INFORMATION_SCHEMA.INNODB_FT_DEFAULT_STOPWORD
    WHERE value IN ('the', 'and', 'a', 'to');

### Step 6: Inspect indexed tokens

    SET GLOBAL innodb_ft_aux_table = 'app/fts_lab';

    SELECT word, doc_count
    FROM INFORMATION_SCHEMA.INNODB_FT_INDEX_TABLE
    ORDER BY word;

If new tokens do not appear yet in `INDEX_TABLE`, check `INDEX_CACHE`.

### Step 7: Test a custom stopword table

    CREATE TABLE fts_lab_stopwords (
        value VARCHAR(100) NOT NULL
    ) ENGINE=InnoDB
      DEFAULT CHARSET=utf8mb4;

    INSERT INTO fts_lab_stopwords(value)
    VALUES ('database');

In the same session, drop the current index, set the user stopword table, and recreate the FULLTEXT index on the table:

    ALTER TABLE fts_lab
    DROP INDEX ft_lab;

    SET SESSION innodb_ft_enable_stopword = ON;
    SET SESSION innodb_ft_user_stopword_table =
        'app/fts_lab_stopwords';

    ALTER TABLE fts_lab
    ADD FULLTEXT INDEX ft_lab (title, body);

The rebuilt index uses the specified stopword table. For tables with multiple FULLTEXT indexes, apply a consistent stopword policy for the table and rebuild related indexes under the same configuration.

### Step 8: Compare results

Re-run queries for `database`, `DB`, `SQL`, and `the`. Note which tokens are found, which are excluded, and why.

## 22. Hands-On Lab: ngram and CJK Text

This lab requires a test server that can be restarted to configure `ngram_token_size`.

### Step 1: Configure ngram

    [mysqld]
    ngram_token_size=2

Restart the server and confirm:

    SHOW GLOBAL VARIABLES LIKE 'ngram_token_size';

### Step 2: Create an ngram table

    USE app;

    CREATE TABLE cjk_articles (
        id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
        title VARCHAR(200),
        body TEXT,
        FULLTEXT KEY ft_cjk (title, body)
            WITH PARSER ngram
    ) ENGINE=InnoDB
      DEFAULT CHARSET=utf8mb4;

### Step 3: Insert text

    INSERT INTO cjk_articles(title, body)
    VALUES
        ('数据库管理', '数据库管理和应用开发'),
        ('数据库应用', '学习数据库应用程序开发');

### Step 4: Inspect tokens

    SET GLOBAL innodb_ft_aux_table = 'app/cjk_articles';

    SELECT word, doc_id, position
    FROM INFORMATION_SCHEMA.INNODB_FT_INDEX_CACHE
    ORDER BY doc_id, position;

If the cache has already been synchronized, check `INDEX_TABLE`.

### Step 5: Test queries

    SELECT
        id,
        MATCH(title, body)
            AGAINST ('数据库' IN NATURAL LANGUAGE MODE) AS score
    FROM cjk_articles
    WHERE MATCH(title, body)
        AGAINST ('数据库' IN NATURAL LANGUAGE MODE);

Try additional phrases of different lengths and record the tokens produced by ngram.

### Step 6: Change ngram_token_size on staging

Change to `1` or `3` in the option file, restart, rebuild the FULLTEXT index, and compare:

- Number of tokens generated.
- Index size.
- Number of matching rows found.
- Query execution time.

Do not pick a value solely because a sample query returns results; validate against the application's actual query suite.

## 23. Common Mistakes

- Assuming a word in a column is guaranteed to be in the FULLTEXT index.
- Using InnoDB variables to control MyISAM indexes or vice versa.
- Forgetting the stopword list when investigating unfound words.
- Thinking stopwords are deleted from the source data.
- Changing the stopword table without rebuilding the FULLTEXT index.
- Changing token size and restarting without rebuilding.
- Editing MyISAM's stopword file without restarting/rebuilding.
- Running `myisamchk` with different full-text values from `mysqld`.
- Thinking ngram uses `innodb_ft_min_token_size` or `ft_min_word_len`.
- Forgetting `ngram_token_size` can only be changed at startup.
- Using English stopwords for CJK data without testing.
- Failing to realize ngram drops tokens that *contain* a stopword.
- Adding punctuation to an ngram stopword list and unintentionally dropping many tokens.
- Ignoring server and stopword list character sets/collations.
- Confusing a token missing from the index with a token dropped by the natural-language threshold.
- Creating a FULLTEXT index while `MATCH()` uses a mismatched column list.
- Rebuilding indexes in production without budgeting disk space, CPU, I/O, and DDL duration.
- Checking only `SHOW VARIABLES` without inspecting actual indexed tokens.

## 24. Operational Checklist

- Identified the storage engine of each table with a FULLTEXT index.
- Confirmed the parser in use: standard parser or ngram.
- Checked min/max token size for the specific engine.
- Checked the stopword list applied to the index.
- Checked character set and collation.
- Identified short words, long words, and business-critical stopwords.
- Tested representative terms on a real corpus.
- Configured startup-only variables in the option file and scheduled a restart.
- Configured dynamic stopword variables in the proper scope.
- Created the stopword table/file with the proper structure and permissions.
- Rebuilt all affected FULLTEXT indexes.
- Inspected tokens in INFORMATION_SCHEMA when using InnoDB.
- Verified `MATCH ... AGAINST` queries after rebuilding.
- Measured index size and search cost.
- Checked replication and backup/restore plans.
- Recorded configuration and rebuild procedures in migrations/runbooks.

## 25. References

- MySQL 8.4 Reference Manual — Full-Text Stopwords: https://dev.mysql.com/doc/refman/8.4/en/fulltext-stopwords.html
- MySQL 8.4 Reference Manual — Fine-Tuning MySQL Full-Text Search: https://dev.mysql.com/doc/refman/8.4/en/fulltext-fine-tuning.html
- MySQL 8.4 Reference Manual — ngram Full-Text Parser: https://dev.mysql.com/doc/refman/8.4/en/fulltext-search-ngram.html
- MySQL 8.4 Reference Manual — Natural Language Full-Text Searches: https://dev.mysql.com/doc/refman/8.4/en/fulltext-natural-language.html
- MySQL 8.4 Reference Manual — InnoDB Startup Options and System Variables: https://dev.mysql.com/doc/refman/8.4/en/innodb-parameters.html
- MySQL 8.4 Reference Manual — Server System Variables: https://dev.mysql.com/doc/refman/8.4/en/server-system-variables.html
- MySQL 8.4 Reference Manual — InnoDB INFORMATION_SCHEMA FULLTEXT Index Tables: https://dev.mysql.com/doc/refman/8.4/en/innodb-information-schema-fulltext_index-tables.html

Stopwords, token length, and the parser together determine which tokens enter a FULLTEXT index. InnoDB and MyISAM have separate configuration variables and stopword lists; ngram uses `ngram_token_size` and drops tokens that contain a stopword. Any change affecting indexed tokens requires rebuilding the FULLTEXT index, and some variables also require restarting the server. Identify the engine, parser, language, and real queries before choosing a configuration; after rebuilding the index, inspect tokens in INFORMATION_SCHEMA and re-run a representative query suite to confirm both accuracy and operational cost.
