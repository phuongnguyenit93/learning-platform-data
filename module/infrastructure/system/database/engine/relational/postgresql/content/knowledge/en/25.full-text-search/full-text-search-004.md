# Parser, Dictionary, Stop Word, and Text Search Configuration in PostgreSQL

PostgreSQL includes a **Full Text Search (FTS)** system for searching documents by vocabulary and search semantics rather than mere substring matching. When you write:

~~~sql
SELECT to_tsvector(
    'pg_catalog.english',
    'The runners are running quickly'
);
~~~

PostgreSQL does not simply lowercase the sentence into a string. It **splits the text into tokens**, classifies each token's type, passes tokens through configured **dictionaries**, drops **stop words** such as `the` and `are`, and normalizes variants like `runners` and `running` into **lexemes**.

That explains why a query for `run` can match a sentence containing `running` under the English configuration, yet may not match under the `simple` configuration.

A typical FTS processing pipeline:

~~~text
                  input text
                      |
                      v
               TEXT SEARCH PARSER
          split tokens + classify types
                      |
        +-------------+-------------+
        |             |             |
    asciiword       word          email/...
        |             |             |
        v             v             v
      MAPPING in TEXT SEARCH CONFIGURATION
        |             |             |
        v             v             v
   DICTIONARY 1 -> DICTIONARY 2 -> ...
        |             |             |
    lexeme(s)     stop word      unrecognized
        |             |             |
        +-------------+-------------+
                      |
                      v
        TSVECTOR (lexeme, position, weight)
                      ^
                      |
      TSQUERY processed with matching config
                      |
                      v
                 @@ operator
~~~

**Four concepts that cannot be used interchangeably:**

- **Parser:** splits text into tokens and assigns each a *token type*; it does not decide which words are stop words.
- **Dictionary:** receives a token and normalizes it into lexemes, rejects the token so the next dictionary can process it, or treats the token as a stop word.
- **Stop word:** a word discarded from search lexemes by a dictionary per language/configuration rules.
- **Text search configuration:** connects a parser to **a chain of dictionaries for each token type**, governing the entire normalization process.

This lesson covers the FTS architecture, functions for inspecting and managing configurations, how stop words affect phrase search, creating custom configurations, attaching GIN indexes, handling Vietnamese/multilingual text, SQL scenarios, and exercises with solutions.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish *token*, *token type*, *lexeme*, *tsvector*, and *tsquery*.
2. Describe the distinct roles of parser, dictionary, stop word, and text search configuration.
3. Use `ts_parse`, `ts_token_type`, `ts_debug`, and `ts_lexize` to inspect the pipeline.
4. Understand dictionary chains: returning lexemes, returning an empty list for stop words, or returning SQL `NULL` when unrecognized.
5. Compare `simple` with `english` and explain stemming.
6. Create a custom text search configuration with `CREATE TEXT SEARCH CONFIGURATION`.
7. Modify token-type mappings with `ALTER TEXT SEARCH CONFIGURATION ... ALTER/ADD MAPPING`.
8. Understand how stop words affect `plainto_tsquery`, `phraseto_tsquery`, and word positions.
9. Use explicit configurations to build `tsvector`, `tsquery`, and corresponding GIN indexes.
10. Recognize why a stored `tsvector` column or expression index can become stale when dictionary rules change.
11. Analyze the limitations of English stemming on Vietnamese content.
12. Choose an appropriate FTS design based on query requirements, languages, and update costs.

## 2. When to Use Full Text Search?

Suppose we have an articles table:

~~~sql
SELECT *
FROM articles
WHERE body ILIKE '%running%';
~~~

`ILIKE` performs a case-insensitive substring check (per applicable semantics). It does not inherently understand that `run`, `running`, and `runs` belong to the same word family.

FTS expresses a different intent:

~~~sql
SELECT *
FROM articles
WHERE to_tsvector('pg_catalog.english', body)
      @@ plainto_tsquery('pg_catalog.english', 'running');
~~~

For English words normalized properly by the dictionary, a shared lexeme allows variants to match.

### 2.1. FTS is not arbitrary substring matching

If a user searches for `gram` in the middle of `programming`, standard FTS **does not treat that as a standalone word**. When substring matching is required, consider `LIKE`, `ILIKE`, or a `pg_trgm` trigram index.

### 2.2. FTS is also not AI semantic search

FTS relies on tokens, dictionaries, lexemes, logical operators, positions, and ranking. It does not automatically infer deep synonyms or sentence meaning like embedding/vector search. It can be extended with synonym/thesaurus dictionaries or external systems, but requires explicit configuration.

### 2.3. An appropriate configuration depends on language

`english` includes English stemming algorithms and stop words. Applying it to Vietnamese content does not automatically produce a complete Vietnamese word-segmentation/normalization system. Thus FTS configuration **is part of data design**, not just a technical knob.

## 3. Core Data Types and Operators

| Component | Role |
| --- | --- |
| `text` | Source text |
| `tsvector` | Set of normalized lexemes, optionally keeping positions and weights |
| `tsquery` | Search expression with lexemes and operators |
| `to_tsvector` | Converts text into a `tsvector` using a configuration |
| `to_tsquery` | Converts a `tsquery`-syntax expression into a query |
| `plainto_tsquery` | Normalizes plain user text into an AND-joined query |
| `phraseto_tsquery` | Builds a query considering word order/distance |
| `websearch_to_tsquery` | Accepts search syntax similar to web search engines |
| `@@` | Checks whether a `tsvector` matches a `tsquery` |
| `ts_rank`, `ts_rank_cd` | Computes relevance scores from vector and query |
| `ts_headline` | Generates a text excerpt highlighting matched terms |

### 3.1. A minimal example

~~~sql
SELECT
    to_tsvector(
        'pg_catalog.english',
        'The quick brown fox jumps'
    ) AS document_vector,
    plainto_tsquery(
        'pg_catalog.english',
        'quick fox'
    ) AS search_query;
~~~

`to_tsvector` returns a structure containing lexemes accepted by the dictionaries. `plainto_tsquery` creates a condition matching the corresponding lexemes, usually combined with `&`.

### 3.2. Checking @@

~~~sql
SELECT
    to_tsvector(
        'pg_catalog.english',
        'The quick brown fox jumps'
    )
    @@ plainto_tsquery(
        'pg_catalog.english',
        'quick fox'
    ) AS matches;
~~~

The result is `true` because both `quick` and `fox` are present in the normalized vector.

### 3.3. tsvector is not a copy of the text

A vector may have stripped stop words, collapsed stemmed variants, and lost original casing. Therefore **never store only `tsvector` and delete the original text** if you need to display content, audit, highlight, or restore the original.

## 4. Token, Token Type, and Lexeme

A **token** is a text segment extracted by the parser from the input. Each token is assigned a **token type**.

Example sentence:

~~~text
The runners are running at example.org
~~~

The parser may classify unaccented English words as `asciiword`, while a web address or hostname gets its own token type.

A **lexeme** is the normalized string produced by a dictionary:

~~~text
Token           Dictionary        Lexeme
-------------------------------------------------
The             english_stem      (stop word)
runners         english_stem      runner
are             english_stem      (stop word)
running         english_stem      run
~~~

Exact lexeme outputs depend on the dictionary and relevant language/version files.

### 4.1. One token can produce multiple lexemes

Some dictionaries can emit multiple lexemes from a single token or return lexemes with additional dictionary-specific structure. Do not assume "one token always yields exactly one lexeme" for every configuration.

### 4.2. One lexeme can appear at multiple positions

~~~sql
SELECT to_tsvector(
    'pg_catalog.english',
    'running runs run'
);
~~~

Multiple variants can fold into the single lexeme `run`, retaining their source word positions. Those positions matter for phrase/proximity queries and certain ranking functions.

### 4.3. Token types are not SQL types

`asciiword`, `word`, `email`, and `host` are **parser labels**. They are not SQL column types like `text`, `integer`, or `jsonb`.

## 5. Parser: Splitting and Classifying, Not Stemming

PostgreSQL's default FTS parser is named `pg_catalog.default`, capable of classifying many token types: words, hyphenated words, numbers, emails, URLs, hostnames, etc.

### 5.1. Inspecting tokens with ts_parse

~~~sql
SELECT
    tokid,
    token
FROM ts_parse(
    'pg_catalog.default'::regparser,
    'The runner sent mail to team@example.org'
);
~~~

`ts_parse` returns the **token type ID** and token text. This function does not apply stop words or stemming yet, so words like `The` and `to` still appear in the token stream when recognized by the parser.

### 5.2. Viewing the token type list

~~~sql
SELECT
    tokid,
    alias,
    description
FROM ts_token_type(
    'pg_catalog.default'::regparser
)
ORDER BY tokid;
~~~

The `alias` values are used when declaring mappings, such as `asciiword` and `word`.

### 5.3. Joining token IDs with names

~~~sql
WITH parsed AS (
    SELECT *
    FROM ts_parse(
        'pg_catalog.default'::regparser,
        'PostgreSQL helps search e-mail@example.org'
    )
),
types AS (
    SELECT *
    FROM ts_token_type(
        'pg_catalog.default'::regparser
    )
)
SELECT
    p.tokid,
    t.alias,
    t.description,
    p.token
FROM parsed AS p
JOIN types AS t ON t.tokid = p.tokid;
~~~

### 5.4. The parser does not know "the" should be dropped

The parser is responsible for turning a text stream into tokens like `The`. Whether `The` becomes a stop word or a lexeme depends on the **dictionaries assigned by the configuration** for that token type.

### 5.5. Hyphenated words and multiple token types

Hyphenated words such as `high-speed` may generate both a whole compound token and component sub-tokens depending on how the default parser is defined. Thus a source segment can yield multiple lexemes with specific positions; do not count FTS tokens using `string_to_array(text, ' ')`.

## 6. Dictionary: Normalizing Tokens into Lexemes

The parser produces tokens, while **dictionaries** decide how each token is processed.

A dictionary receives a token and can:

1. **Accept the token:** return one or more lexemes.
2. **Recognize the token as a stop word:** return an empty lexeme array.
3. **Reject the token:** return SQL `NULL` so the next dictionary in the mapping tries to handle it.
4. **Filtering dictionary:** transform the token and pass it on to subsequent dictionaries, depending on dictionary type.

### 6.1. The simple dictionary

`pg_catalog.simple` generally lowercases tokens without English grammatical stemming. Without a custom stopword list, it retains many function words that the English configuration discards.

~~~sql
SELECT
    to_tsvector(
        'pg_catalog.simple',
        'The runners are running'
    ) AS simple_vector;
~~~

### 6.2. The english_stem dictionary

`pg_catalog.english_stem` applies English stemming rules and comes with a corresponding stopword list.

~~~sql
SELECT
    to_tsvector(
        'pg_catalog.english',
        'The runners are running'
    ) AS english_vector;
~~~

The two vectors differ in lexemes: under the English configuration, `runners` may become `runner`, `running` becomes `run`, and function words such as `the` and `are` are dropped.

### 6.3. Dictionaries are not full-text translators

Stemming does not translate languages. `english_stem` does not turn `mèo` into `cat` or `tìm kiếm` into `search`. Synonyms/thesauri require dedicated dictionary mechanisms or additional search structures.

## 7. ts_lexize: Testing a Single Dictionary in Isolation

`ts_lexize` invokes a text search dictionary on **a single token**:

~~~sql
SELECT
    ts_lexize(
        'pg_catalog.simple'::regdictionary,
        'Running'
    ) AS simple_lexeme,
    ts_lexize(
        'pg_catalog.english_stem'::regdictionary,
        'Running'
    ) AS english_lexeme;
~~~

Typically:

- `simple` returns a nearly unmodified lowercased lexeme such as `running`.
- `english_stem` returns a stemmed lexeme such as `run`.

### 7.1. Stop words return an empty array

~~~sql
SELECT
    ts_lexize(
        'pg_catalog.english_stem'::regdictionary,
        'the'
    ) AS english_stop_word;
~~~

`the` is a common English stop word, so the dictionary returns an **empty array** (it accepted the token but emitted no lexemes).

### 7.2. SQL NULL differs from an empty array

- `NULL`: the dictionary **did not recognize** the token; the dictionary chain moves on to the next dictionary.
- `{}` (empty array): the token was recognized as a stop word; **stop** trying subsequent dictionaries.
- `{run}`: the token was processed into a lexeme.

This distinction is crucial when designing dictionary chains.

### 7.3. ts_lexize does not simulate the full parser

`ts_lexize` takes a single pre-separated token; it does not parse all token types in a whole passage. To watch parser + mapping + dictionaries work together, use `ts_debug`.

## 8. Text Search Configurations Orchestrate the Pipeline

A text search configuration contains:

1. The chosen **parser**.
2. A **mapping** from each token type emitted by the parser to an ordered list of one or more dictionaries.

For instance, `pg_catalog.english` uses the default parser and maps appropriate token groups to English stemming dictionaries.

### 8.1. A token type can have a dictionary chain

Illustration:

~~~text
asciiword
    |
    v
dictionary A
    |
    +--> lexeme      : accept, stop
    +--> stop word   : discard, stop
    +--> NULL        : pass to dictionary B
    +--> filter      : transform and continue
    |
    v
dictionary B
~~~

Key point: **dictionary order in a mapping can change the outcome.**

### 8.2. Unmapped token types

If the parser emits a token type that has no mapping in the configuration, that token is skipped when building `tsvector`/`tsquery`.

For example, if a custom configuration only maps `asciiword` while the data contains `word` tokens with accented characters, those tokens may not be processed as intended.

### 8.3. Configurations are schema objects

PostgreSQL manages text search configurations within schemas, with qualified names such as:

~~~text
pg_catalog.english
pg_catalog.simple
fts_lab.en_no_stem
~~~

When `search_path` or defaults change, unqualified names may resolve differently. For indexes, migrations, and large applications, using **explicit schema-qualified configuration names** makes behavior predictable.

## 9. Viewing the Current Default Configuration

~~~sql
SHOW default_text_search_config;
~~~

This setting indicates which configuration is used by FTS functions when **no configuration name is passed**.

### 9.1. Functions with and without an explicit config

~~~sql
SELECT
    to_tsvector('The runners are running')
      AS dependent_on_session_default,
    to_tsvector(
        'pg_catalog.english',
        'The runners are running'
    ) AS explicit_english;
~~~

The first expression depends on `default_text_search_config`. The second does not depend on the session's default setting.

### 9.2. Setting temporarily in a transaction

~~~sql
BEGIN;
SET LOCAL default_text_search_config = 'pg_catalog.simple';

SELECT to_tsvector('The runners are running');

ROLLBACK;
~~~

`SET LOCAL` takes effect within the transaction scope per PostgreSQL rules. This example shows that with the same source text, **FTS output can change due to configuration**, even when the data did not change.

### 9.3. Why must queries and indexes use the same configuration?

If vectors are built with `english` while queries are normalized with `simple`, `running` may become `run` on one side and `running` on the other. The query can fail to match even though the document "has that word" to a human reader.

Therefore you must ensure the **vector-building config** and **query-building config** are lexeme-compatible.

## 10. ts_debug: The Most Important Inspection Tool

`ts_debug` returns each token-processing step in a configuration:

~~~sql
SELECT
    alias,
    description,
    token,
    dictionaries,
    dictionary,
    lexemes
FROM ts_debug(
    'pg_catalog.english',
    'The runners are running quickly'
);
~~~

These columns mean:

| Column | Meaning |
| --- | --- |
| `alias` | Token type name assigned by the parser |
| `description` | Token type description |
| `token` | Raw input token string |
| `dictionaries` | Dictionaries mapped for this token type |
| `dictionary` | Dictionary that actually accepted the token, if any |
| `lexemes` | Final lexeme(s); empty array for a stop word |

### 10.1. Observing stop words

In `The runners are running quickly`, tokens like `The` and `are` are recognized by the English dictionary as stop words and emit no lexemes.

### 10.2. Observing stemming

`runners` and `running` pass through the English stemmer rules, producing shorter lexemes than the raw tokens.

### 10.3. Comparing english with simple

~~~sql
SELECT
    alias,
    token,
    dictionary,
    lexemes
FROM ts_debug(
    'pg_catalog.simple',
    'The runners are running quickly'
);
~~~

In the `simple` configuration, tokens are generally kept in lowercase without stemming; stopword behavior differs as well.

### 10.4. Debug the actual failing case

If a query misses an expected document, do not look only at the `tsvector` output. Run `ts_debug` on:

1. The exact source text.
2. The user's search phrase.
3. The exact configuration used to build the index/`tsvector`.

This reveals which tokens were dropped, what lexemes were produced, and which dictionary handled them.

## 11. What Are Stop Words?

**Stop words** are high-frequency words with low distinguishing value in search contexts, designated by a dictionary to be excluded from the lexeme set.

In English, common examples include:

~~~text
the, a, an, and, of, to, are ...
~~~

Exact lists and behavior depend on the system's dictionary/version files. Do not assume every short word is a stop word.

### 11.1. Direct example

~~~sql
SELECT
    to_tsvector(
        'pg_catalog.english',
        'the quick fox'
    ) AS english_vector,
    to_tsvector(
        'pg_catalog.simple',
        'the quick fox'
    ) AS simple_vector;
~~~

`english` drops the `the` lexeme, while `simple` normally keeps it.

### 11.2. Stop words do not delete the original text

Stop-word removal happens when creating **`tsvector`/`tsquery`**; the original `text` column still retains those words. When `ts_headline` displays text, `the` can still appear in the excerpt.

### 11.3. Stop-word selection is not just about index size

Dropping common words shrinks vectors and reduces noisy matches. However, in certain domains (legal, medical, product names, command codes, fixed idioms), common words can be **critical**. For example, negation phrases or titles may lose meaning if tokens are dropped.

### 11.4. Stopword lists are language-dependent

Do not blindly apply an English stopword list to Vietnamese articles and expect better results. Analyze common corpus terms, search intent, and phrase-search requirements before tuning stop words.

## 12. Stop Words and Positions in tsvector

When building a vector, word positions still affect proximity even when some tokens are treated as stop words.

~~~sql
SELECT to_tsvector(
    'pg_catalog.english',
    'quick and brown'
);
~~~

Under the standard English parser/configuration, lexemes `quick` and `brown` are **two positions apart** because the intervening `and` token was discarded as a stop word.

### 12.1. Why not simply collapse the two words together?

If dropping a stop word also erased the positional gap, phrase search would treat:

~~~text
quick brown
quick and brown
~~~

as positionally identical, even when a user wants adjacent words. PostgreSQL retains the positional metadata in `tsvector`/`tsquery` needed to distinguish these cases according to the search condition.

### 12.2. Positions are metadata, not empty strings

In a `tsvector`, only retained lexemes appear, yet their positions still reflect tokenization and stopword gaps per FTS mechanics.

### 12.3. The same word can appear at multiple positions

~~~sql
SELECT to_tsvector(
    'pg_catalog.english',
    'quick fox and quick brown fox'
);
~~~

Lexemes `quick` and `fox` appear multiple times and can carry multiple position entries. This supports ranking and phrase matching.

## 13. plainto_tsquery: Creating a Query from a Plain Sentence

~~~sql
SELECT plainto_tsquery(
    'pg_catalog.english',
    'the quick brown fox'
);
~~~

`plainto_tsquery`:

1. Parses input using the configuration.
2. Normalizes via dictionaries.
3. Discards stop words per rules.
4. Combines remaining lexemes with **AND**.

### 13.1. No need to manually join with &

A user types `quick brown fox`; the application can write:

~~~sql
WHERE search_vector @@ plainto_tsquery(
    'pg_catalog.english',
    $1
)
~~~

instead of manually building the string `quick & brown & fox`.

### 13.2. Plain input is not full tsquery syntax

If a user types `&`, `|`, or parentheses in plain input, `plainto_tsquery` handles them as plain text per parser rules rather than letting the user inject arbitrary `tsquery` operators.

### 13.3. Finding words without requiring exact order

With `plainto_tsquery('english', 'quick fox')`, a vector containing `fox` and `quick` matches even in different positions, because the relation is AND, **not an adjacent phrase**.

## 14. to_tsquery: Explicit Operator Syntax

Use `to_tsquery` when you want to write expressions with FTS logical operators:

~~~sql
SELECT to_tsquery(
    'pg_catalog.english',
    'fox & run'
);
~~~

Common operators:

| Symbol | Meaning |
| --- | --- |
| `&` | AND |
| `|` | OR |
| `!` | NOT |
| `<->` | FOLLOWED BY, distance of one position |
| `<N>` | FOLLOWED BY with distance of N positions |
| `:*` | Prefix matching on a lexeme in supported contexts |

### 14.1. Logic example

~~~sql
SELECT to_tsquery(
    'pg_catalog.english',
    'postgresql & (search | index)'
);
~~~

Meaning: contains the `postgresql` lexeme and at least one of `search` or `index` after normalization.

### 14.2. Invalid syntax can raise errors

`to_tsquery` requires valid `tsquery` grammar. Never pass arbitrary raw user text directly to this function and assume it cannot fail syntax parsing.

### 14.3. Do not concatenate SQL strings

Even when using `to_tsquery`, always **bind parameters** to prevent SQL injection. The `tsquery` string itself still requires syntax handling and control over which search operators are permitted.

## 15. phraseto_tsquery: Order and Distance

~~~sql
SELECT phraseto_tsquery(
    'pg_catalog.english',
    'quick fox'
);
~~~

The output has a structure like:

~~~text
'quick' <-> 'fox'
~~~

This requires `quick` followed immediately by `fox` at the next position.

### 15.1. Stop words are reflected in distance

~~~sql
SELECT phraseto_tsquery(
    'pg_catalog.english',
    'quick and fox'
);
~~~

Because `and` is a stop word, the phrase query still reflects the positional gap, in a form like:

~~~text
'quick' <2> 'fox'
~~~

Hence:

~~~sql
SELECT
    to_tsvector(
        'pg_catalog.english',
        'quick and fox'
    ) @@ phraseto_tsquery(
        'pg_catalog.english',
        'quick and fox'
    ) AS spaced_match;
~~~

can match based on exact position without requiring the `and` lexeme to remain in the vector.

### 15.2. Phrase and AND differ

~~~sql
SELECT
    to_tsvector('pg_catalog.english', 'fox is quick')
      @@ plainto_tsquery('pg_catalog.english', 'quick fox')
        AS and_match,
    to_tsvector('pg_catalog.english', 'fox is quick')
      @@ phraseto_tsquery('pg_catalog.english', 'quick fox')
        AS phrase_match;
~~~

Logical outcome: AND is true because both lexemes exist, whereas the phrase requiring `quick` then `fox` is false.

### 15.3. Prefix does not replace phrase

Finding lexemes by prefix is a different problem from "two adjacent lexemes". Choose the right operator for the requirement rather than substituting `:*` for `<->`.

## 16. websearch_to_tsquery: Search-Box-Friendly Syntax

~~~sql
SELECT websearch_to_tsquery(
    'pg_catalog.english',
    '"quick fox" OR running -sleeping'
);
~~~

This function supports a friendlier search syntax than `to_tsquery`, such as:

- Words/phrases in double quotes for phrase matching.
- `OR` for alternatives.
- A minus sign before a word for negation within supported syntax.

### 16.1. Suitable for free-form user strings

`websearch_to_tsquery` is designed to parse web-style search input, generally avoiding the syntax errors `to_tsquery` raises on unformatted input.

### 16.2. Not a perfect intent-understanding engine

It still uses the configuration, parser, and dictionaries. If a query contains only stop words, the result can still have no search lexemes. Nor does it automatically match unconfigured synonyms.

### 16.3. Separate validation and parsing

The application should still enforce input length limits, handle empty queries, bind parameters, and apply query-cost safeguards rather than relying solely on the function's forgiving syntax.

## 17. When Input Contains Only Stop Words

~~~sql
SELECT
    plainto_tsquery(
        'pg_catalog.english',
        'the and of'
    ) AS only_stopwords;
~~~

An input consisting solely of dictionary stop words can produce an **empty `tsquery`**, with no useful lexemes to match.

### 17.1. Checking the node count

~~~sql
SELECT
    numnode(
        plainto_tsquery(
            'pg_catalog.english',
            'the and of'
        )
    ) AS query_nodes;
~~~

When all words are stop words, the result is `0` nodes.

### 17.2. Application scenario

A user may enter:

~~~text
the
and
of the
~~~

If the configuration discards every token, the application should handle it explicitly:

- Inform the user that no usable keywords were entered.
- Suggest adding more specific terms.
- Fall back to another strategy when business rules require matching the exact phrase.

Do not treat an empty `tsquery` as a request to "return all rows" unless the product explicitly intends that and bounds its cost.

## 18. Creating a Lab Database for FTS

The following examples use a **test schema** only and do not touch production data.

~~~sql
CREATE SCHEMA fts_lab;

CREATE TABLE fts_lab.articles (
    article_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    title text NOT NULL,
    body text NOT NULL,
    lang text NOT NULL DEFAULT 'en'
        CHECK (lang IN ('en','vi')),
    published_at timestamptz NOT NULL
);
~~~

### 18.1. English and Vietnamese data

~~~sql
INSERT INTO fts_lab.articles
    (title, body, lang, published_at)
VALUES
    (
      'Running with the foxes',
      'The quick brown foxes are running across the field.',
      'en', '2026-01-01 08:00:00+00'
    ),
    (
      'PostgreSQL full text search',
      'A text search configuration connects a parser to dictionaries.',
      'en', '2026-01-02 08:00:00+00'
    ),
    (
      'Stemming and stop words',
      'An English dictionary can normalize running and remove the word the.',
      'en', '2026-01-03 08:00:00+00'
    ),
    (
      'Database indexes',
      'A GIN index can accelerate matching a tsvector with a tsquery.',
      'en', '2026-01-04 08:00:00+00'
    ),
    (
      'The little green house',
      'A greenhouse stands near a quiet garden.',
      'en', '2026-01-05 08:00:00+00'
    ),
    (
      'Colour and color',
      'Color and colour are different spellings in English.',
      'en', '2026-01-06 08:00:00+00'
    ),
    (
      'Tìm kiếm văn bản tiếng Việt',
      'PostgreSQL hỗ trợ tìm kiếm theo từ khóa và chỉ mục GIN.',
      'vi', '2026-01-07 08:00:00+00'
    ),
    (
      'Cơ sở dữ liệu và phân tích',
      'Cấu hình tìm kiếm phải phù hợp với ngôn ngữ của dữ liệu.',
      'vi', '2026-01-08 08:00:00+00'
    );
~~~

### 18.2. Viewing the source data

~~~sql
SELECT
    article_id,
    title,
    lang,
    published_at
FROM fts_lab.articles
ORDER BY article_id;
~~~

Each row is one document. The two `lang='vi'` rows illustrate the limits of the English configuration rather than claiming PostgreSQL ships a dedicated Vietnamese word segmenter.

## 19. Parser Hands-On: Inspecting Individual Tokens

~~~sql
SELECT
    p.tokid,
    t.alias,
    p.token
FROM ts_parse(
    'pg_catalog.default'::regparser,
    'The quick fox runs at info@example.org'
) AS p
JOIN ts_token_type(
    'pg_catalog.default'::regparser
) AS t
    ON t.tokid = p.tokid;
~~~

The output shows each token and its corresponding alias, including the token types the parser recognizes from text.

### 19.1. Why inspect token types before ALTER MAPPING?

`ALTER TEXT SEARCH CONFIGURATION ... MAPPING FOR ...` uses **token type aliases**, such as `asciiword`, `word`, and `email`. If you pick the wrong alias, the mapping may fail to affect the desired text or the command may be invalid.

### 19.2. The parser already handles punctuation

You do not need to manually run:

~~~sql
regexp_replace(body, '[[:punct:]]', ' ', 'g')
~~~

in every query before `to_tsvector`. The FTS parser already defines tokenization rules. Manual preprocessing can strip URLs, hyphens, emojis, and traits the application needs.

### 19.3. The default parser is not a deep linguistic tokenizer

For Vietnamese, which uses spaces within compound words, the default parser does not understand linguistic word boundaries. Token-based FTS may need external dictionaries/tokenizers or a different search architecture when high recall/search quality is required.

## 20. Dictionary Hands-On: Identifying Stop Words and Stemming

~~~sql
SELECT
    token,
    ts_lexize(
        'pg_catalog.simple'::regdictionary,
        token
    ) AS simple_result,
    ts_lexize(
        'pg_catalog.english_stem'::regdictionary,
        token
    ) AS english_result
FROM (
    VALUES
        ('running'),
        ('runners'),
        ('the'),
        ('quickly'),
        ('foxes')
) AS sample(token);
~~~

### 20.1. How to read the output

Observe:

- Was the token reduced to a root lexeme?
- Was any token discarded as an empty array?
- Did any case return SQL `NULL` because the dictionary did not recognize it?

### 20.2. Stemming is not translation

If a dictionary maps `running` to `run`, that is **stemming**. It does not mean you can query every semantically similar word using a single default dictionary.

### 20.3. Note on non-English words

~~~sql
SELECT
    ts_lexize(
        'pg_catalog.english_stem'::regdictionary,
        'tìm'
    ) AS english_on_vietnamese;
~~~

Even when the dictionary returns a lexeme, that does not mean it understands **Vietnamese grammar or compound words**.

## 21. Practicing ts_debug on Mixed Text

~~~sql
SELECT
    alias,
    token,
    dictionaries,
    dictionary,
    lexemes
FROM ts_debug(
    'pg_catalog.english',
    'Running, THE foxes; docs@example.org, high-speed.'
);
~~~

### 21.1. Things to look for

1. Which dictionary handled `Running`?
2. Was `THE` treated as a stop word?
3. What token type did the parser assign to the email?
4. Which tokens did `high-speed` produce?
5. Can different tokens yield overlapping lexemes?

### 21.2. Do not judge solely from one PostgreSQL build's output

Token classification and normalization depend on parser and dictionary versions. Use `ts_debug` as **evidence from your actual environment** rather than hardcoding every token/lexeme string in your application.

## 22. Creating a Custom Text Search Configuration

Suppose you want to preserve exact word forms for stricter word matching without English stemming on ordinary word tokens.

### 22.1. Copy an existing configuration

~~~sql
CREATE TEXT SEARCH CONFIGURATION fts_lab.en_no_stem (
    COPY = pg_catalog.english
);
~~~

`COPY` creates a new configuration based on an existing one; you can then adjust mappings **on the new configuration** without altering the shared `pg_catalog.english`.

### 22.2. Change mappings for common word token types

~~~sql
ALTER TEXT SEARCH CONFIGURATION fts_lab.en_no_stem
ALTER MAPPING FOR asciiword, word
WITH pg_catalog.simple;
~~~

This means tokens of these types are handled by the `simple` dictionary instead of the previous dictionary list.

### 22.3. Compare results

~~~sql
SELECT
    to_tsvector(
        'pg_catalog.english',
        'The runners are running'
    ) AS english_vector,
    to_tsvector(
        'fts_lab.en_no_stem',
        'The runners are running'
    ) AS no_stem_vector;
~~~

Since the example tokens are unaccented ASCII words, the updated mapping causes `The`/`are` to be kept by `simple` and `runners`/`running` to bypass the English stemmer for those two token types.

### 22.4. Why name it en_no_stem rather than simple?

We **copied** the English configuration and changed only the mappings for `asciiword` and `word`. Other token types still inherit mappings from the original configuration. Therefore the new configuration is **not completely identical to `pg_catalog.simple`**.

### 22.5. Do not edit pg_catalog.english directly

Never run:

~~~sql
-- Do not do this in a shared environment:
ALTER TEXT SEARCH CONFIGURATION pg_catalog.english ...
~~~

Modifying a system/shared configuration can affect multiple applications, index expressions, and search results. Use a dedicated configuration in an application schema.

## 23. Creating a Configuration from a Parser

Another option is creating a configuration **with no initial mappings**, then adding mappings per token type.

~~~sql
CREATE TEXT SEARCH CONFIGURATION fts_lab.lab_words (
    PARSER = pg_catalog.default
);
~~~

### 23.1. Add mappings

~~~sql
ALTER TEXT SEARCH CONFIGURATION fts_lab.lab_words
ADD MAPPING FOR asciiword, word
WITH pg_catalog.simple;
~~~

### 23.2. Test it

~~~sql
SELECT
    to_tsvector(
        'fts_lab.lab_words',
        'Simple running café and email@example.org'
    ) AS partial_mapped;
~~~

Only token types with mappings are processed by this configuration. For example, the parser may emit a token type for email and other unmapped groups; they will not appear in the `tsvector`.

### 23.3. When is this suitable?

Building from a `PARSER` is useful when you want to **explicitly opt in each token type**, for instance indexing only ordinary word groups and ignoring irrelevant token types.

### 23.4. Trade-off

It is easy to accidentally omit an important token type such as emails, numbers, or hyphenated words. When your goal is close to an existing configuration, `COPY` followed by targeted mapping edits is usually clearer.

## 24. Adjusting the Dictionary Chain with ALTER MAPPING

General syntax:

~~~sql
ALTER TEXT SEARCH CONFIGURATION config_name
ALTER MAPPING FOR token_type [, ...]
WITH dictionary_name [, ...];
~~~

### 24.1. Dictionary order matters

If a mapping contains:

~~~text
dictionary_A, dictionary_B
~~~

then `dictionary_A` is tried first. If `A` accepts the token and returns lexemes or a stopword, `B` is not tried in the normal fallback flow.

### 24.2. Mistake: putting simple first and expecting stemming

Suppose:

~~~sql
ALTER TEXT SEARCH CONFIGURATION fts_lab.en_no_stem
ALTER MAPPING FOR asciiword
WITH pg_catalog.simple, pg_catalog.english_stem;
~~~

`simple` usually **accepts almost any token** in that group and returns its lowercase form. Because it already accepted the token, `english_stem` behind it never gets a chance to run.

**Appending a stemmer at the end does not automatically cause stemming.**

### 24.3. When the first dictionary returns SQL NULL

A specialized dictionary might accept only certain tokens and return SQL `NULL` for others; in that case, the next dictionary acts as a **true fallback**.

### 24.4. Filtering dictionaries are a special case

A filtering dictionary, such as `unaccent` when the extension is installed, can transform a token and pass it forward to subsequent dictionaries. That differs from a standard dictionary that returns a lexeme and terminates the chain.

### 24.5. Do not assemble chains in arbitrary order

Before configuring:

- Which dictionary **pre-filters/normalizes**?
- Which dictionary performs **stemming**?
- Which dictionary is the **fallback**?
- At which stage should stop words be caught?

Test every case with `ts_debug` and `ts_lexize`.

## 25. Creating a simple Dictionary with Stop Words

PostgreSQL provides the `pg_catalog.simple` template and can use an appropriate stopword file to build a new dictionary.

Example using the English stopword list typically distributed with PostgreSQL:

~~~sql
CREATE TEXT SEARCH DICTIONARY fts_lab.stop_only_en (
    TEMPLATE = pg_catalog.simple,
    StopWords = english
);
~~~

### 25.1. How this dictionary differs from english_stem

`stop_only_en` uses the `simple` template combined with a stopword list; it does not turn into a Snowball English stemmer.

~~~sql
SELECT
    ts_lexize(
        'fts_lab.stop_only_en'::regdictionary,
        'the'
    ) AS stopword_result,
    ts_lexize(
        'fts_lab.stop_only_en'::regdictionary,
        'running'
    ) AS ordinary_result;
~~~

`the` is expected to be discarded by the stopword list; `running` is kept in lowercase without stemming to `run`.

### 25.2. Create a configuration using this dictionary

~~~sql
CREATE TEXT SEARCH CONFIGURATION fts_lab.stop_words_only (
    PARSER = pg_catalog.default
);

ALTER TEXT SEARCH CONFIGURATION fts_lab.stop_words_only
ADD MAPPING FOR asciiword, word
WITH fts_lab.stop_only_en;
~~~

### 25.3. Compare three strategies

~~~sql
SELECT
    to_tsvector(
        'pg_catalog.simple',
        'The runners are running'
    ) AS simple,
    to_tsvector(
        'fts_lab.stop_words_only',
        'The runners are running'
    ) AS stop_without_stem,
    to_tsvector(
        'pg_catalog.english',
        'The runners are running'
    ) AS english_stemmed;
~~~

Meaning:

- `simple`: typically retains stop words, no stemming.
- `stop_words_only`: removes configured stop words, no stemming.
- `english`: English stop words and stemming.

### 25.4. Server-side file dependency

The `StopWords = english` option references a stopword file on the **PostgreSQL server**, not a SQL table or an application-local path. Available files and privileges can differ across distributions; if files or privileges are missing in your environment, dictionary creation must be handled by a DBA.

### 25.5. Do not edit stopword files casually in production

Changing dictionary file contents alters data lexemes even when SQL stays unchanged. Deployments must include configuration versioning, vector/index rebuilds, and safe rollouts.

## 26. Stemming, Synonyms, and Thesauri Differ

| Mechanism | Example Idea | Goal |
| --- | --- | --- |
| Lowercasing | `Running` → `running` | Case-insensitive tokens |
| Stemming | `running` → `run` | Collapse morphological variants |
| Stop words | `the` → no lexeme | Drop low-value words |
| Synonym dictionary | `db` → `database` | Normalize defined abbreviations/synonyms |
| Thesaurus dictionary | Multi-word phrase → another representation | Normalize phrases/dictionary semantics |
| Unaccent filtering | `café` → `cafe` | Strip diacritics when required |

### 26.1. The English stemmer does not create arbitrary synonyms

`colour` and `color` should not be assumed to collapse into a single lexeme just because both are English. If the application needs both variants to match, check the actual dictionary or configure explicit synonyms.

### 26.2. Synonym dictionaries need their own files and workflow

A synonym dictionary usually relies on a server-side definition file. It does not materialize automatically when you run `CREATE TEXT SEARCH CONFIGURATION`. Any synonym rules added must be tested to avoid blurring domain distinctions.

### 26.3. A thesaurus does not replace the parser

A thesaurus can handle certain multi-word phrases at the dictionary layer, yet the parser still determines which tokens and token types are generated.

### 26.4. Do not strip diacritics for every business case

In Vietnamese, diacritics carry linguistic information. Accent-insensitive search can improve UX in some products, while increasing false matches in others. Weigh precision requirements and test on real data.

## 27. unaccent: Optional Filtering Dictionary

The `unaccent` extension provides a filtering dictionary that can remove diacritics/transform characters before the next dictionary performs stemming.

In an environment with privileges to install extensions:

~~~sql
CREATE EXTENSION IF NOT EXISTS unaccent WITH SCHEMA public;
~~~

**Note:** If the extension is installed in another schema, qualify the dictionary name with that actual schema. The SQL below assumes it is installed in `public`.

### 27.1. Copy the English configuration

~~~sql
CREATE TEXT SEARCH CONFIGURATION fts_lab.en_unaccent (
    COPY = pg_catalog.english
);
~~~

### 27.2. Place unaccent before english_stem

~~~sql
ALTER TEXT SEARCH CONFIGURATION fts_lab.en_unaccent
ALTER MAPPING FOR word, asciiword
WITH public.unaccent, pg_catalog.english_stem;
~~~

### 27.3. Why does this order matter?

`unaccent` is a filtering dictionary that converts accented tokens into unaccented form and passes them on to `english_stem`. If a regular dictionary that always accepts tokens were placed first, subsequent dictionaries would not run.

### 27.4. Test it

~~~sql
SELECT
    to_tsvector(
        'pg_catalog.english',
        'café'
    ) AS original_config,
    to_tsvector(
        'fts_lab.en_unaccent',
        'café'
    ) AS normalized_config;
~~~

The output shows the effect of `unaccent` in a supported environment. Use `ts_debug('fts_lab.en_unaccent', ...)` to inspect the dictionary chain instead of guessing from the configuration name.

### 27.5. Distinguish from the unaccent(text) SQL function

The extension also provides a string-processing SQL function. However, **using a filtering dictionary inside an FTS pipeline** is a different architecture from `WHERE unaccent(col) LIKE ...` and requires a matching index strategy.

### 27.6. Do not treat unaccent as a complete Vietnamese tokenizer

`unaccent` primarily transforms diacritics/characters according to the extension's rules. It does not segment Vietnamese compound words into linguistic search units, nor does it understand synonyms.

## 28. Viewing Configurations in the Catalogs

PostgreSQL stores FTS metadata in system catalogs.

~~~sql
SELECT
    n.nspname AS config_schema,
    c.cfgname AS config_name,
    p.prsname AS parser_name
FROM pg_ts_config AS c
JOIN pg_namespace AS n
    ON n.oid = c.cfgnamespace
JOIN pg_ts_parser AS p
    ON p.oid = c.cfgparser
WHERE n.nspname IN ('pg_catalog','fts_lab')
ORDER BY n.nspname, c.cfgname;
~~~

### 28.1. Main catalogs

| Catalog | Contents |
| --- | --- |
| `pg_ts_parser` | Text search parsers |
| `pg_ts_config` | Configurations and their selected parser |
| `pg_ts_config_map` | Ordered mapping from token type to dictionaries |
| `pg_ts_dict` | Dictionary names and options |
| `pg_ts_template` | Dictionary templates |
| `pg_namespace` | Schemas owning the objects |

### 28.2. Do not edit catalogs directly

Catalogs are for **reading metadata**. To change mappings, use dedicated SQL DDL such as `ALTER TEXT SEARCH CONFIGURATION`, never direct edits to `pg_ts_config_map`.

## 29. Inspecting Actual Dictionary Mappings

This query shows which dictionaries apply to each token type in `pg_catalog.english`:

~~~sql
SELECT
    t.alias AS token_type,
    m.mapseqno AS dictionary_order,
    nd.nspname || '.' || d.dictname AS dictionary_name
FROM pg_ts_config AS c
JOIN pg_ts_config_map AS m
    ON m.mapcfg = c.oid
JOIN pg_ts_dict AS d
    ON d.oid = m.mapdict
JOIN pg_namespace AS nd
    ON nd.oid = d.dictnamespace
CROSS JOIN LATERAL ts_token_type(
    c.cfgparser::regparser
) AS t
WHERE c.oid = 'pg_catalog.english'::regconfig
  AND t.tokid = m.maptokentype
ORDER BY t.alias, m.mapseqno;
~~~

### 29.1. Meaning of mapseqno

`mapseqno` indicates the **dictionary order** for a given token type. In normal lookup chains, earlier dictionaries get first chance to process the token.

### 29.2. Why join ts_token_type?

`pg_ts_config_map.maptokentype` stores numeric token type IDs. `ts_token_type` translates those IDs into readable aliases like `asciiword`.

### 29.3. Inspecting your custom configuration

Change:

~~~sql
WHERE c.oid = 'pg_catalog.english'::regconfig
~~~

to:

~~~sql
WHERE c.oid = 'fts_lab.en_no_stem'::regconfig
~~~

to view the mapping after your `ALTER`.

### 29.4. Metadata does not replace ts_debug

Catalogs tell you which dictionaries are mapped and in what order. `ts_debug` shows **for an actual token**, which dictionary accepted it and what final lexemes were produced. You need both when troubleshooting FTS bugs.

## 30. Querying with an Explicit Configuration

For English articles:

~~~sql
SELECT
    article_id,
    title
FROM fts_lab.articles
WHERE lang = 'en'
  AND to_tsvector(
      'pg_catalog.english',
      title || ' ' || body
  ) @@ plainto_tsquery(
      'pg_catalog.english',
      'running fox'
  )
ORDER BY article_id;
~~~

### 30.1. Why use the same configuration?

Both sides are normalized with `english`; stemming and stopword rules stay consistent.

### 30.2. What if the query uses simple?

~~~sql
SELECT
    to_tsvector(
        'pg_catalog.english',
        'runners are running'
    ) @@ plainto_tsquery(
        'pg_catalog.simple',
        'running'
    ) AS mismatched_config;
~~~

Because the English vector may store the lexeme `run` while the `simple` query looks for `running`, the result can **fail to match**. This is a common bug when indexes use configuration A while the API uses configuration B.

### 30.3. Different configs are not always wrong

Sometimes two configurations are intentionally different yet compatible on specific lexeme sets. However, ensuring consistent recall requires **explicit design rules and testing**, not luck.

## 31. Creating a Stored Generated tsvector Column

If the application searches the same documents repeatedly, recomputing `to_tsvector` for every row on every query can burn CPU.

One option is a **generated `tsvector` column**:

~~~sql
ALTER TABLE fts_lab.articles
ADD COLUMN search_vector tsvector
GENERATED ALWAYS AS (
    setweight(
        to_tsvector(
            'pg_catalog.english'::regconfig,
            coalesce(title, '')
        ),
        'A'
    )
    ||
    setweight(
        to_tsvector(
            'pg_catalog.english'::regconfig,
            coalesce(body, '')
        ),
        'B'
    )
) STORED;
~~~

### 31.1. Two design points

- Uses `english` **explicitly**, independent of session defaults.
- Builds separate vectors for `title` and `body` and applies **weights A/B** before concatenating, helping ranking favor title matches.

### 31.2. Language limitation in the lab

The `search_vector` column above applies English to **all rows**, including `lang='vi'`. That suffices to demonstrate generated columns and GIN, but is not an optimal multilingual setup. Later sections show a separate query/index for Vietnamese.

### 31.3. Stored generated column

`STORED` means the vector is persisted when rows are inserted/updated rather than recomputed on every `SELECT`. It increases storage and write cost, while reducing CPU on repeated searches.

### 31.4. Why not call to_tsvector(body) without a config?

The implicit-config form depends on the session's `default_text_search_config`. For generated columns and expression indexes, use the **fixed-configuration** form to satisfy expression immutability requirements and avoid semantics shifting across sessions.

## 32. GIN Index for tsvector

~~~sql
CREATE INDEX idx_articles_search_vector
ON fts_lab.articles
USING gin (search_vector);

ANALYZE fts_lab.articles;
~~~

Query:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    article_id,
    title
FROM fts_lab.articles
WHERE lang = 'en'
  AND search_vector @@ plainto_tsquery(
      'pg_catalog.english',
      'running fox'
  );
~~~

### 32.1. GIN finds lexemes, it does not auto-sort by rank

GIN accelerates finding documents containing matching lexemes. If a query requests:

~~~sql
ORDER BY ts_rank(search_vector, query) DESC
~~~

the planner still generally needs to score and sort the matched documents; GIN does not provide the desired rank order automatically.

### 32.2. Does the query match the right tsvector?

If you index `search_vector` yet query:

~~~sql
WHERE to_tsvector('pg_catalog.simple', body) @@ ...
~~~

that is a **different expression**, and will not automatically use the GIN index on `search_vector`.

### 32.3. Small tables often use Seq Scan

The lab has eight articles, so PostgreSQL may legitimately choose `Seq Scan` as cheaper than GIN. Do not conclude an index is broken if the planner skips it for a handful of rows.

## 33. Expression GIN Index Without a tsvector Column

If you do not want to store a separate `tsvector` column:

~~~sql
CREATE INDEX idx_articles_body_english_fts
ON fts_lab.articles
USING gin (
    to_tsvector(
        'pg_catalog.english'::regconfig,
        body
    )
);
~~~

Matching query:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT article_id, title
FROM fts_lab.articles
WHERE to_tsvector(
        'pg_catalog.english'::regconfig,
        body
    ) @@ plainto_tsquery(
        'pg_catalog.english',
        'dictionary parser'
    );
~~~

### 33.1. Index and query expressions must align

An index on `to_tsvector('english', body)` is not automatically an index for `to_tsvector('english', title || ' ' || body)`.

### 33.2. Do not keep both index types in production

This lesson creates **both generated-column GIN and expression GIN** to contrast the two designs. A real system chooses based on workload, update frequency, storage, ranking, and query patterns. Keeping redundant indexes increases write cost.

### 33.3. Updates from source columns

PostgreSQL maintains an expression index when referenced columns change; stored vectors are likewise recomputed by the generated column expression. However, when **mapping/dictionary rules themselves change**, DML-triggered row updates **do not automatically re-normalize all existing rows**.

## 34. Ranking with ts_rank

~~~sql
WITH q AS (
    SELECT plainto_tsquery(
        'pg_catalog.english',
        'search parser'
    ) AS query
)
SELECT
    a.article_id,
    a.title,
    ts_rank(a.search_vector, q.query) AS rank
FROM fts_lab.articles AS a
CROSS JOIN q
WHERE a.lang = 'en'
  AND a.search_vector @@ q.query
ORDER BY rank DESC, a.article_id;
~~~

### 34.1. Why does title have weight A?

In the generated column, lexemes from `title` receive weight `A` and from `body` receive `B`. A ranking function can leverage weights to favor matches in more important sections.

### 34.2. Ranking is not absolute correctness

`ts_rank`/`ts_rank_cd` provide scoring models based on lexemes, frequency, weights, and positions. They do not evaluate business factors such as freshness, source authority, or personalization.

### 34.3. LIMIT and the number of scored documents

~~~sql
ORDER BY rank DESC
LIMIT 20
~~~

caps the final output rows, yet PostgreSQL may still have to compute ranks for **many matching documents** to pick the top 20. GIN filters candidates; it does not make ranking free.

## 35. Highlighting with ts_headline

~~~sql
SELECT
    article_id,
    title,
    ts_headline(
        'pg_catalog.english',
        body,
        plainto_tsquery(
            'pg_catalog.english',
            'running fox'
        )
    ) AS excerpt
FROM fts_lab.articles
WHERE lang = 'en'
  AND search_vector @@ plainto_tsquery(
      'pg_catalog.english',
      'running fox'
  );
~~~

`ts_headline` produces a passage with matches highlighted per its options. Its output is **marked-up text**, not HTML automatically sanitized for every application.

### 35.1. Be careful when rendering on the web

If the application renders HTML, apply context-appropriate escaping/sanitization to prevent XSS when source content is untrusted. Never inject a highlighted string straight into the DOM as safe HTML.

### 35.2. Use the same configuration

For consistent highlighting, pass the configuration matching your vectors, queries, and source data.

### 35.3. Highlighting does not replace the original text

`ts_headline` reads the original text to build excerpts; `tsvector` lacks enough information to restore all original words, punctuation, and formatting verbatim.

## 36. Vietnamese FTS: Understanding the Limits

Try:

~~~sql
SELECT
    to_tsvector(
        'pg_catalog.simple',
        'Tìm kiếm văn bản tiếng Việt'
    ) AS simple_vi;
~~~

The `simple` configuration keeps text tokens in lowercase without applying English stemming.

### 36.1. Vietnamese diacritics and tokenization

The default parser processes Unicode characters per its rules, yet **does not understand Vietnamese compound words**. The phrase `cơ sở dữ liệu` may be split into multiple whitespace-delimited tokens even though linguistically it contains multi-syllable lexical units.

### 36.2. English stemming can distort expectations

~~~sql
SELECT
    to_tsvector(
        'pg_catalog.english',
        'Tìm kiếm dữ liệu'
    ) AS english_on_vi,
    to_tsvector(
        'pg_catalog.simple',
        'Tìm kiếm dữ liệu'
    ) AS simple_on_vi;
~~~

Do not treat the presence of lexemes in both outputs as proof that the English stemmer understands Vietnamese.

### 36.3. Unaccent has trade-offs

If accent-insensitive search is required, `unaccent` or similar normalization can be one component. However, stripping diacritics collapses distinct words together and does not replace Vietnamese word segmentation or semantics.

### 36.4. Match the solution to your requirements

Options include:

- Using `simple` with default tokenization and validating quality on a real corpus.
- Using a Vietnamese dictionary/tokenizer (if a suitable extension is available).
- Using trigrams for substrings or name matching.
- Using a dedicated search service with specialized tokenizers and ranking when requirements are high.

No single configuration is simultaneously optimal for every language and domain.

## 37. Practicing a Separate Index for Vietnamese Documents

The lab already has an English-generated vector. For `lang='vi'` rows, you can try an **expression GIN index** using `simple`:

~~~sql
CREATE INDEX idx_articles_vi_simple_fts
ON fts_lab.articles
USING gin (
    to_tsvector(
        'pg_catalog.simple'::regconfig,
        title || ' ' || body
    )
)
WHERE lang = 'vi';
~~~

Matching query:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT article_id, title
FROM fts_lab.articles
WHERE lang = 'vi'
  AND to_tsvector(
      'pg_catalog.simple'::regconfig,
      title || ' ' || body
  ) @@ plainto_tsquery(
      'pg_catalog.simple',
      'tìm kiếm'
  );
~~~

### 37.1. Why a partial index?

This index targets rows with `lang='vi'`. The query must include the matching language predicate so the planner recognizes that the partial index covers the query.

### 37.2. Why not use the English generated index?

In the lab, `search_vector` was built with English even for Vietnamese rows. A query normalized with `simple` can produce different lexemes, so never mix two inconsistent configurations.

### 37.3. Scope of support

This is a **minimal technical baseline**, not a guarantee of linguistic-grade Vietnamese search quality. You need test suites covering accented/unaccented keywords, multi-syllable phrases, proper names, slang, and abbreviations.

## 38. Multilingual Design with Per-Row Configs

If a table has a `lang` column, you can choose the configuration by language.

Example query:

~~~sql
SELECT article_id, title, lang
FROM fts_lab.articles
WHERE (
    lang = 'en'
    AND search_vector @@ plainto_tsquery(
        'pg_catalog.english',
        'database'
    )
)
OR (
    lang = 'vi'
    AND to_tsvector(
        'pg_catalog.simple',
        title || ' ' || body
    ) @@ plainto_tsquery(
        'pg_catalog.simple',
        'cơ sở dữ liệu'
    )
);
~~~

### 38.1. Two branches with two strategies

- English: uses the stored vector + corresponding GIN index.
- Vietnamese: uses the `simple` expression and can leverage the Vietnamese partial GIN index created above.

### 38.2. Mixed queries are more complex than single-language queries

In applications, when the search language is known, you can usually route to a single branch and configuration. When unknown, you need language detection/user selection and a strategy to merge and rank results.

### 38.3. Do not compare rank scores across languages as absolute numbers

Different dictionaries stem, drop stop words, and tokenize differently, so score distributions can diverge noticeably. When merging multilingual results, design and test an application-level ranking/normalization formula.

## 39. Changing a Configuration When Indexes Already Exist: Stale Data Risk

Suppose you built an index on:

~~~sql
to_tsvector('fts_lab.en_no_stem'::regconfig, body)
~~~

and later changed `fts_lab.en_no_stem`'s mapping from `simple` to `english_stem`.

### 39.1. The problem

Lexemes created under the **old mapping** can differ from the new mapping:

~~~text
Old mapping: running -> running
New mapping: running -> run
~~~

However, entries inside the **expression index** were built under the old rules and do not automatically transform just because you altered the mapping.

### 39.2. Plan for rebuilds

If an expression GIN index depends on a modified configuration, evaluate running **`REINDEX`** on that index so the expression is recomputed from source data under the new rules.

### 39.3. Stored tsvector differs from an expression index

If a table persists `tsvector` in a `STORED` generated column, changing a mapping **does not automatically trigger an `UPDATE` on every existing row**. You must plan to **recompute the vector values** from source text (for example via backfill/update/expression migration per your rollout strategy), and ensure the index on that column stays in sync.

**Running `REINDEX` on an index over a stored `tsvector` column does not regenerate lexemes from source text**; it only re-indexes the **already stored `tsvector` values**.

### 39.4. If using triggers to update tsvector

With trigger-based or manual updates instead of a generated column, run a corresponding backfill and verify the trigger uses an explicit configuration. If a trigger changes without updating old rows, the index will hold lexemes from multiple normalization eras.

### 39.5. Dictionary/stopword files are also part of versioning

Even when SQL configuration DDL does not change, upgrading or replacing dictionary files or extensions can alter lexemes. FTS migrations should track **configuration versions and rebuild/backfill procedures**.

## 40. Measuring Performance and Reading EXPLAIN

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT article_id, title
FROM fts_lab.articles
WHERE search_vector @@ plainto_tsquery(
    'pg_catalog.english',
    'parser dictionary'
);
~~~

Key details to inspect:

| Component | How to Interpret |
| --- | --- |
| `Seq Scan` | PostgreSQL scans the table sequentially; often reasonable for small tables |
| `Bitmap Index Scan` | Uses GIN to find candidate documents/tuples |
| `Bitmap Heap Scan` | Fetches tuples from candidate heap blocks |
| `Index Cond` | Condition evaluated via the index |
| `Recheck Cond` | Condition re-verified per plan semantics |
| `Filter` | Additional condition applied after the scan |
| `actual rows` | Average rows actually returned per loop |
| `loops` | Number of times the node executed |
| `Buffers: shared hit/read` | Activity across shared buffers |
| `Execution Time` | Total instrumented statement execution time |

### 40.1. GIN does not guarantee the planner uses it

With eight rows, `Seq Scan` can be faster than GIN. On millions of documents, a GIN index helps for selective lexemes, while overly common keywords can still read many matches.

### 40.2. Ranking may still require a Sort

Even when GIN filters candidates, `ORDER BY ts_rank(...) DESC` can require scoring and sorting. Never assume "uses an index" means "no Sort".

### 40.3. Stop words affect selectivity

If a word is discarded as a stop word, it cannot serve as an independent lexeme to narrow results. A query containing only stop words does not yield a selective index condition.

### 40.4. Buffers are not row counts

`shared hit=100` counts shared buffer accesses, not 100 individual documents read. One block can hold many tuples, and parent/child nodes report inclusive buffer counts.

## 41. Safety When Accepting User Queries

### 41.1. Always bind parameters

Example prepared statement:

~~~sql
PREPARE search_articles(text) AS
SELECT article_id, title
FROM fts_lab.articles
WHERE search_vector @@ websearch_to_tsquery(
    'pg_catalog.english',
    $1
);

EXECUTE search_articles('running fox');
~~~

### 41.2. Never concatenate input into SQL

Do not concatenate:

~~~text
"... @@ to_tsquery('english','" + user_input + "')"
~~~

because of SQL injection and escaping/syntax errors. Always use properly typed parameterized SQL.

### 41.3. FTS can still be abused for resources

Users can submit very long queries, many OR/NOT clauses, or ultra-common terms. These can consume CPU, memory, huge candidate sets, or expensive ranking. Enforce input size caps, page size limits, statement timeouts, and rate limits as needed.

### 41.4. Do not expose unauthorized documents

FTS is a search mechanism, not a permission boundary. Tenant, ownership, RLS, or ACL predicates must still be enforced on every query.

### 41.5. Highlights require escaping

Never embed `ts_headline` markup directly into unescaped HTML, especially when `body` is user-supplied.

## 42. Common Mistakes

### Mistake 1. Thinking the parser performs stemming

The parser only splits and classifies tokens; dictionaries normalize lexemes or drop stop words.

### Mistake 2. Thinking dictionaries decide token types

Token types are assigned by the parser. The configuration uses each token type to choose a dictionary chain.

### Mistake 3. Thinking every token emits one lexeme

A dictionary can emit multiple lexemes, zero lexemes, or reject the token for another dictionary to process.

### Mistake 4. Confusing SQL NULL with an empty array from ts_lexize

SQL `NULL` means the dictionary did not recognize the token; an empty array means it recognized the token as a stop word.

### Mistake 5. Putting simple first in a chain and expecting english_stem to run

`simple` usually accepts tokens, so subsequent dictionaries are not invoked under normal fallback rules.

### Mistake 6. Using COPY and assuming the new config is completely independent of all files

`COPY` creates separate mappings, yet dictionaries can still reference shared dictionary objects/files. Changing underlying dictionary rules/files can affect multiple configurations.

### Mistake 7. Omitting mappings for important token types

Unmapped token types are omitted from `tsvector`. Check `ts_token_type` and `ts_debug`.

### Mistake 8. Treating stop words as deleting words from body

Stop words affect `tsvector`/`tsquery`; the source text remains intact.

### Mistake 9. Thinking stop words do not affect phrase distance

Positions still reflect gaps from removed tokens; `phraseto_tsquery` encodes those distances.

### Mistake 10. Using plainto_tsquery when an adjacent phrase is desired

`plainto_tsquery` normally joins lexemes with AND without enforcing order. Use `phraseto_tsquery` or appropriate phrase syntax.

### Mistake 11. Passing raw input to to_tsquery

`to_tsquery` requires valid syntax; user input can trigger errors. Consider `plainto_tsquery` or `websearch_to_tsquery`.

### Mistake 12. Ignoring empty tsqueries

Stop-word-only input can yield a query with zero lexemes, which the application must handle explicitly.

### Mistake 13. Relying implicitly on default_text_search_config everywhere

Sessions can have different defaults, causing queries and indexes to produce different lexemes. Use explicit configurations for important data and indexes.

### Mistake 14. Using simple in queries and english in vectors

Different stemming prevents similar forms from matching.

### Mistake 15. Thinking english is a full Vietnamese tokenizer

It is not. Evaluate word segmentation, compound words, diacritics, and ranking on a Vietnamese corpus.

### Mistake 16. Thinking unaccent understands synonyms/semantics

`unaccent` is rule-based character/diacritic transformation, not a compound-word dictionary or semantic search.

### Mistake 17. Thinking the English stemmer merges all words with similar meanings

Stemming handles morphological variants, not a comprehensive synonym list.

### Mistake 18. Changing mappings without rebuilding indexes/vectors

Old lexemes may no longer match new queries. Plan reindexing/backfilling.

### Mistake 19. Running REINDEX on an old tsvector column and thinking data re-normalized

`REINDEX` on a stored `tsvector` reuses the already stored lexemes. Recompute vectors from source text when dictionaries change.

### Mistake 20. Thinking GIN automatically sorts by rank

GIN locates lexemes/candidates; it does not deliver `ts_rank` ordering for free.

### Mistake 21. Treating Seq Scan on a small table as a failure

The planner may be right to scan a few rows sequentially; measure on representative data.

### Mistake 22. Measuring only speed without testing search quality

A fast index with a dictionary dropping key terms or mismatched queries still yields poor UX. Maintain test queries with expected documents.

### Mistake 23. Using one-arg to_tsvector in an expression index

Expressions depending on the default configuration are unsuitable for immutable/consistent indexes. Pass an explicit `regconfig`.

### Mistake 24. Thinking ts_headline is safe HTML

It is FTS-generated marked-up text; the application must apply proper escaping/sanitization before rendering.

### Mistake 25. Updating dictionaries without a versioning process

Changing stopword/synonym files or extensions alters lexemes of existing data. Use migrations and rollback plans.

### Mistake 26. Inspecting tokens by splitting on spaces

The parser handles emails, URLs, hyphens, and many token types; whitespace splitting cannot replicate it.

## 43. Hands-on Exercises

Exercises apply to PostgreSQL and the `fts_lab` schema. Configuration and index DDL should only be executed in a **lab database** or authorized environment.

### Exercise 1. Four roles

Explain the roles of parser, dictionary, stop word, and text search configuration in one sentence each.

### Exercise 2. Token vs lexeme

What is the difference between the token `running` and the lexeme `run`?

### Exercise 3. Token types

Write SQL to list the token types of the default parser.

### Exercise 4. ts_parse

Write SQL to tokenize the sentence `The user emailed team@example.org`.

### Exercise 5. ts_debug

Write SQL to inspect tokens, dictionaries, and lexemes when analyzing `The runners are running` with `english`.

### Exercise 6. ts_lexize

Compare `ts_lexize` output for `Running` with `simple` and `english_stem`.

### Exercise 7. Stopword

Why does `ts_lexize('english_stem','the')` return an empty array rather than SQL `NULL`?

### Exercise 8. Dictionary order

Why does the mapping `simple, english_stem` usually not stem the token `running`?

### Exercise 9. Unmapped token type

What happens to a token type for which the configuration assigns no dictionary?

### Exercise 10. Viewing default config

Write SQL to check the session's `default_text_search_config`.

### Exercise 11. Same config on both sides

Why can `to_tsvector('english', ...) @@ plainto_tsquery('simple', ...)` easily cause false negatives?

### Exercise 12. Plain query

Write a query finding documents containing both `parser` and `dictionary` via `plainto_tsquery`.

### Exercise 13. to_tsquery logic

Write a `to_tsquery` for "postgresql AND (search OR index)".

### Exercise 14. Phrase

Write a `phraseto_tsquery` for `quick fox` and explain how it differs from a plain query.

### Exercise 15. Stopwords and phrases

For `quick and fox`, why does the phrase query preserve a gap of two positions?

### Exercise 16. Empty stopword query

Write SQL using `numnode` to detect that input `the and of` leaves no useful lexemes under English.

### Exercise 17. Web search

Write a `websearch_to_tsquery` for input matching phrase `"quick fox"` or `running`.

### Exercise 18. CREATE CONFIGURATION COPY

Create configuration `fts_lab.my_english` based on `pg_catalog.english`.

### Exercise 19. ALTER MAPPING

Change the mapping for `asciiword` and `word` to `pg_catalog.simple`.

### Exercise 20. PARSER config

Create a new configuration using `pg_catalog.default`, then add a mapping for `asciiword` with `simple`.

### Exercise 21. Stopwords dictionary

Create a dictionary from template `simple` with stopword file `english` and explain how it differs from `english_stem`.

### Exercise 22. Catalog mapping

Write SQL to find the dictionaries mapped to token type `asciiword` in `pg_catalog.english`.

### Exercise 23. Generated tsvector

Write DDL adding a stored generated `tsvector` from `title` and `body` under the English config; title weight A, body weight B.

### Exercise 24. GIN

Create a GIN index on `search_vector`.

### Exercise 25. Expression GIN

Create an expression GIN index on `to_tsvector('english', body)` using an explicit configuration.

### Exercise 26. Rank

Write a query filtering and sorting articles by `ts_rank` for keywords `parser dictionary`.

### Exercise 27. Highlight

Write a query using `ts_headline` and state what must be done before displaying results in HTML.

### Exercise 28. Vietnamese

Why is `simple` a starting point for trying Vietnamese FTS, yet insufficient to replace a dedicated Vietnamese tokenizer?

### Exercise 29. Multilingual

If English uses `english` and Vietnamese uses `simple`, why must both vectors and `tsquery` follow the same per-language policy?

### Exercise 30. Dictionary migration

When a dictionary changes `running` from lexeme `running` to `run`, what must be done for expression indexes and stored `tsvector`s?

### Exercise 31. EXPLAIN

Write `EXPLAIN (ANALYZE, BUFFERS)` checking a query on `search_vector` and name two signs of GIN usage.

### Exercise 32. Distinguishing FTS and substring

A user wants to find all documents containing `gram` inside `programming`. Why might default FTS be unsuitable?

### Exercise 33. Query parameter

Write a prepared statement with `websearch_to_tsquery` accepting `text` input without manual SQL concatenation.

### Exercise 34. Data access check

Does an FTS index automatically ensure users only see permitted articles? What must be added?

## 44. Suggested Solutions

### Exercises 1–2. Processing pipeline

The parser splits and classifies tokens; the configuration maps token types to dictionary chains; dictionaries turn tokens into lexemes or stop words; stop words are discarded yet still affect positions. `running` is the source token; `run` is the normalized lexeme under English stemming.

### Exercise 3. Token types

~~~sql
SELECT tokid, alias, description
FROM ts_token_type('pg_catalog.default'::regparser)
ORDER BY tokid;
~~~

### Exercise 4. Parser

~~~sql
SELECT tokid, token
FROM ts_parse(
    'pg_catalog.default'::regparser,
    'The user emailed team@example.org'
);
~~~

### Exercise 5. ts_debug

~~~sql
SELECT alias, token, dictionaries, dictionary, lexemes
FROM ts_debug(
    'pg_catalog.english',
    'The runners are running'
);
~~~

### Exercises 6–8. Dictionary chain

~~~sql
SELECT
    ts_lexize(
        'pg_catalog.simple'::regdictionary,
        'Running'
    ),
    ts_lexize(
        'pg_catalog.english_stem'::regdictionary,
        'Running'
    );
~~~

`simple` usually accepts and lowercases the token to `running`; `english_stem` can stem it to `run`. A dictionary returning an empty array **recognized a stopword**, rather than failing to recognize the token. If `simple` comes first and accepts the token, the trailing stemmer does not run in normal fallback order.

### Exercises 9–11. Mapping and config

Unmapped token types are omitted from vectors/queries. Check:

~~~sql
SHOW default_text_search_config;
~~~

English vectors and Simple queries can produce mismatched lexemes, causing false negatives.

### Exercise 12. Plain query

~~~sql
SELECT article_id, title
FROM fts_lab.articles
WHERE search_vector @@ plainto_tsquery(
    'pg_catalog.english',
    'parser dictionary'
);
~~~

### Exercise 13. Logic

~~~sql
SELECT to_tsquery(
    'pg_catalog.english',
    'postgresql & (search | index)'
);
~~~

### Exercises 14–15. Phrase

~~~sql
SELECT phraseto_tsquery(
    'pg_catalog.english',
    'quick fox'
);

SELECT phraseto_tsquery(
    'pg_catalog.english',
    'quick and fox'
);
~~~

`quick fox` yields `'quick' <-> 'fox'`; `quick and fox` has stopword `and`, so the positional gap is reflected via `<2>`. Plain queries do not require lexemes to be adjacent.

### Exercise 16. Empty tsquery

~~~sql
SELECT numnode(
    plainto_tsquery(
        'pg_catalog.english',
        'the and of'
    )
);
~~~

If all words are stopwords, the result is `0`.

### Exercise 17. Web input

~~~sql
SELECT websearch_to_tsquery(
    'pg_catalog.english',
    '"quick fox" OR running'
);
~~~

### Exercises 18–19. COPY and ALTER

~~~sql
CREATE TEXT SEARCH CONFIGURATION fts_lab.my_english (
    COPY = pg_catalog.english
);

ALTER TEXT SEARCH CONFIGURATION fts_lab.my_english
ALTER MAPPING FOR asciiword, word
WITH pg_catalog.simple;
~~~

### Exercise 20. Parser-based configuration

~~~sql
CREATE TEXT SEARCH CONFIGURATION fts_lab.only_ascii (
    PARSER = pg_catalog.default
);

ALTER TEXT SEARCH CONFIGURATION fts_lab.only_ascii
ADD MAPPING FOR asciiword
WITH pg_catalog.simple;
~~~

### Exercise 21. Stopwords dictionary

~~~sql
CREATE TEXT SEARCH DICTIONARY fts_lab.stop_en_answer (
    TEMPLATE = pg_catalog.simple,
    StopWords = english
);
~~~

It removes stopwords per the list without stemming like `english_stem`. A matching stopword file must exist on the PostgreSQL server.

### Exercise 22. Catalog

~~~sql
SELECT
    t.alias,
    m.mapseqno,
    d.dictname
FROM pg_ts_config AS c
JOIN pg_ts_config_map AS m
    ON m.mapcfg = c.oid
JOIN pg_ts_dict AS d
    ON d.oid = m.mapdict
CROSS JOIN LATERAL ts_token_type(
    c.cfgparser::regparser
) AS t
WHERE c.oid = 'pg_catalog.english'::regconfig
  AND t.tokid = m.maptokentype
  AND t.alias = 'asciiword'
ORDER BY m.mapseqno;
~~~

### Exercise 23. Stored vector

~~~sql
ALTER TABLE fts_lab.articles
ADD COLUMN search_vector_answer tsvector
GENERATED ALWAYS AS (
    setweight(
        to_tsvector(
            'pg_catalog.english'::regconfig,
            coalesce(title, '')
        ), 'A'
    ) ||
    setweight(
        to_tsvector(
            'pg_catalog.english'::regconfig,
            coalesce(body, '')
        ), 'B'
    )
) STORED;
~~~

This exercise example adds a **second column**, distinct from `search_vector` created earlier in the lab. If you do not want a duplicate column, treat the statement as a template only.

### Exercises 24–25. GIN

~~~sql
CREATE INDEX idx_articles_search_answer
ON fts_lab.articles USING gin (search_vector);

CREATE INDEX idx_articles_body_answer
ON fts_lab.articles
USING gin (
    to_tsvector(
        'pg_catalog.english'::regconfig,
        body
    )
);
~~~

The lab may already have equivalent indexes. Never create near-duplicate indexes in production.

### Exercise 26. Ranking

~~~sql
WITH query AS (
    SELECT plainto_tsquery(
        'pg_catalog.english',
        'parser dictionary'
    ) AS q
)
SELECT
    a.article_id,
    a.title,
    ts_rank(a.search_vector, query.q) AS score
FROM fts_lab.articles AS a
CROSS JOIN query
WHERE a.search_vector @@ query.q
ORDER BY score DESC, a.article_id;
~~~

### Exercise 27. Highlight

~~~sql
SELECT
    article_id,
    ts_headline(
        'pg_catalog.english',
        body,
        plainto_tsquery(
            'pg_catalog.english',
            'running fox'
        )
    ) AS excerpt
FROM fts_lab.articles;
~~~

If displaying results in HTML, apply context-appropriate escaping/sanitization and never treat markup from untrusted sources as safe.

### Exercises 28–29. Vietnamese and multilingual

`simple` can preserve Vietnamese tokens, yet lacks a complete Vietnamese compound-word tokenizer or stemmer. Within each language, vector and `tsquery` configurations must align; an English vector is not automatically compatible with a `simple` query.

### Exercise 30. Migration

For an **expression index**, evaluate running `REINDEX` after changing mappings/dictionaries. For a **stored `tsvector`**, **recompute vector values from source text** and synchronize indexes; running `REINDEX` on an old vector column does not alter stored lexemes.

### Exercise 31. EXPLAIN

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT article_id, title
FROM fts_lab.articles
WHERE search_vector @@ plainto_tsquery(
    'pg_catalog.english',
    'database'
);
~~~

In a plan using GIN, you typically see `Bitmap Index Scan` on the GIN index and `Bitmap Heap Scan` to recheck/fetch rows. However, an eight-row table may reasonably use `Seq Scan`.

### Exercise 32. FTS is not substring

FTS matches normalized lexemes/words rather than arbitrary substrings inside longer words. If the requirement is `'%gram%'`, consider `LIKE`/`ILIKE` and `pg_trgm` according to workload.

### Exercise 33. Prepared statement

~~~sql
PREPARE search_articles_answer(text) AS
SELECT article_id, title
FROM fts_lab.articles
WHERE search_vector @@ websearch_to_tsquery(
    'pg_catalog.english',
    $1
);

EXECUTE search_articles_answer('"quick fox"');
~~~

### Exercise 34. Access control

No. FTS/GIN only searches content. Queries still require permission/tenant predicates or appropriate RLS/ACL enforcement so unauthorized documents are never returned.

## 45. Quick Reference Table

| Goal | Tool / Syntax |
| --- | --- |
| View parser token types | `ts_token_type('pg_catalog.default'::regparser)` |
| Split text into tokens | `ts_parse('pg_catalog.default'::regparser, text)` |
| Inspect full pipeline | `ts_debug('pg_catalog.english', text)` |
| Test dictionary directly | `ts_lexize('pg_catalog.english_stem'::regdictionary, token)` |
| View default config | `SHOW default_text_search_config` |
| Tokenize/stem text | `to_tsvector('pg_catalog.english', text)` |
| Keep simple tokens | `to_tsvector('pg_catalog.simple', text)` |
| Build query from plain text | `plainto_tsquery(config, text)` |
| Build phrase query | `phraseto_tsquery(config, text)` |
| Build web-syntax query | `websearch_to_tsquery(config, text)` |
| Build FTS operator query | `to_tsquery(config, expression)` |
| Test match | `tsvector @@ tsquery` |
| Check empty tsquery | `numnode(tsquery)` |
| Clone configuration | `CREATE TEXT SEARCH CONFIGURATION ... (COPY = ...)` |
| Create config from parser | `CREATE TEXT SEARCH CONFIGURATION ... (PARSER = ...)` |
| Replace mapping | `ALTER TEXT SEARCH CONFIGURATION ... ALTER MAPPING ... WITH ...` |
| Add mapping | `ALTER TEXT SEARCH CONFIGURATION ... ADD MAPPING ... WITH ...` |
| Stopwords dictionary | `CREATE TEXT SEARCH DICTIONARY ... (TEMPLATE = simple, StopWords = ...)` |
| Inspect mappings | `pg_ts_config_map` + `pg_ts_dict` |
| Inspect configs | `pg_ts_config` + `pg_ts_parser` |
| Full-text index | `CREATE INDEX ... USING gin (tsvector)` |
| Expression index | `USING gin (to_tsvector('english'::regconfig, body))` |
| Title/body weights | `setweight(...,'A')`, `setweight(...,'B')` |
| Ranking | `ts_rank(vector, query)` |
| Highlighting | `ts_headline(config, text, query)` |
| Measure plan | `EXPLAIN (ANALYZE, BUFFERS)` |
| Dictionary change with old index | `REINDEX`/backfill per index/vector type |

## 46. FTS Design Checklist

1. Are users searching by **word**, **phrase**, **substring**, or **semantics**?
2. What are the document and query languages? Are multiple languages mixed?
3. Does the parser properly classify emails, hyphens, Unicode words, and key token types?
4. Does the mapping cover all required token types?
5. Do dictionary stemming/stopwords fit the domain?
6. Does dictionary chain ordering cause later dictionaries to be skipped?
7. Do stop words strip critical domain terms?
8. Must phrase queries preserve gaps across stop words?
9. How does the application handle stop-word-only queries?
10. Do `to_tsvector` and `tsquery` use compatible configurations?
11. Do indexes and generated columns specify configurations explicitly?
12. For Vietnamese, have compound words, diacritics, and recall been tested on a real corpus?
13. If using `unaccent`, has its impact on precision been evaluated?
14. Is the GIN index built on the exact `tsvector`/expression used by queries?
15. Are there near-duplicate indexes that should be removed?
16. Does ranking appropriately prioritize titles and key fields?
17. Is highlighted output rendered safely?
18. Does the search endpoint bind parameters, bound query/page sizes, and enforce authorization?
19. Do dictionary/stopword/config migrations include a `REINDEX`/backfill plan?
20. Have `EXPLAIN`, match quality, and latency been measured on a representative corpus?

## 47. Summary

Full Text Search in PostgreSQL is a **configurable pipeline**, not a single string-search function:

1. **The parser** ingests text and produces typed tokens.
2. **A text search configuration** maps each token type to a **dictionary chain**.
3. **Dictionaries** normalize tokens into lexemes, reject them so the next dictionary runs, or discard them as **stop words**; filtering dictionaries can transform and pass tokens along.
4. **Stop words** trim unnecessary lexemes while still influencing positional distances in phrase search.
5. **`tsvector` and `tsquery`** must be built with compatible rules so `@@` finds the right documents.

To understand why a word matches or is missed, start with `ts_parse` to view tokens, `ts_token_type` to identify types, `ts_lexize` to inspect dictionaries, and `ts_debug` to trace the full path through a configuration.

When taking FTS to production, **do not focus solely on GIN indexes**. Indexes speed up locating normalized lexemes; result quality depends on dictionaries, stop words, language handling, and consistency between vectors and queries. Whenever configuration rules change, manage **index rebuilds and stored-vector recomputation** as data migrations that affect search outcomes.

Practical rule: **inspect tokens → choose dictionaries/stop words → define explicit configurations → build consistent vectors/queries → add indexes → measure plans and search quality**. Understanding this full pipeline lets you improve the speed, accuracy, and maintainability of PostgreSQL full-text search.
