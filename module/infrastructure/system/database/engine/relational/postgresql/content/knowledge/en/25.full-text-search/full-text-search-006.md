# Field Weights, Ranking, and Result Highlighting in PostgreSQL

A search engine needs to do more than report which documents contain a keyword. When thousands of documents match, users need to see the **most relevant results first**, along with an **excerpt showing where the match occurred**.

For example, a user searches for `search ranking`. Article A has both words right in the title; Article B mentions both only near the end of a long body; Article C has them close together in a short paragraph; Article D is an unpublished draft. A solid design must separate:

- **Matching** — Which documents satisfy the query? Use `tsvector @@ tsquery`.
- **Ranking** — Which documents belong at the top? Use weights `A/B/C/D`, `ts_rank`, or `ts_rank_cd`.
- **Highlighting** — Which passage should the user see? Use `ts_headline` on the original text.
- **Authorization** — Which documents is the user allowed to view? Use filters/RLS, never rank scores.

~~~mermaid
flowchart TD
    D["title / summary / category / body"] --> V["setweight + to_tsvector"]
    V --> I["tsvector / GIN"]
    U["User keywords"] --> Q["websearch_to_tsquery"]
    I --> M["@@: select matching documents"]
    Q --> M
    M --> R["ts_rank / ts_rank_cd"]
    R --> S["ORDER BY score + tie-breakers"]
    S --> L["LIMIT top-N"]
    L --> H["ts_headline on original text"]
    H --> UI["Safe renderer, preventing XSS"]
~~~

This lesson belongs to the **Text Search** chapter, **Database Engine Relational PostgreSQL** module, focusing on using PostgreSQL Full-Text Search (FTS) to prioritize fields, score relevance, and generate highlighted snippets, along with performance and display-safety constraints.

## 1. Matching Conditions Differ from Ranking Scores

In FTS, a document is converted to a `tsvector` and a search request is converted to a `tsquery`.

~~~sql
SELECT
    to_tsvector(
        'english'::regconfig,
        'Search ranking improves search results'
    )
    @@
    plainto_tsquery(
        'english'::regconfig,
        'search ranking'
    ) AS matched;
~~~

Here the expected result is `true`, with no numeric score.

If you need to rank multiple matching documents, you can compute:

~~~sql
SELECT
    ts_rank(
        to_tsvector(
            'english'::regconfig,
            'Search ranking improves search results'
        ),
        plainto_tsquery(
            'english'::regconfig,
            'search ranking'
        )
    ) AS relevance_score;
~~~

`@@` returns a boolean; `ts_rank` returns a score based on lexemes and ranking signals. **Never use scores in place of access-control checks.**

## 2. Why Is FTS Not Like ILIKE?

`ILIKE '%search%'` searches for a case-insensitive character pattern. FTS performs tokenization and uses dictionaries to convert words into **lexemes**.

~~~sql
SELECT
    to_tsvector(
        'english'::regconfig,
        'Searching through documents'
    ) AS english_vector,
    to_tsvector(
        'simple'::regconfig,
        'Searching through documents'
    ) AS simple_vector;
~~~

Two configurations can produce different lexemes due to stemming and stop words. FTS does not automatically solve all typos, synonyms, or semantic meanings like embedding search.

**Rule:** the configuration used to analyze content, parse queries, and generate highlights must be compatible. If you change the configuration, stored `tsvector` data and associated indexes may need to be rebuilt.

## 3. Weights A, B, C, D

PostgreSQL lets you attach weight labels to lexeme positions using `setweight`.

| Weight | Suggested Field | Default Priority |
| --- | --- | --- |
| A | Title | Highest |
| B | Summary | High |
| C | Category, tags | Medium |
| D | Body | Lowest |

Example:

~~~sql
SELECT
    setweight(
        to_tsvector(
            'english'::regconfig,
            'Search ranking'
        ),
        'A'
    ) AS title_vector,
    setweight(
        to_tsvector(
            'english'::regconfig,
            'Search ranking'
        ),
        'D'
    ) AS body_vector;
~~~

Identical lexemes can carry different weight labels. `setweight` **only attaches labels**; how those labels contribute to the score belongs to the ranking function.

## 4. Concatenating Multiple Fields with the || Operator

An article has `title`, `summary`, `category`, and `body`. We build a combined vector:

~~~sql
SELECT
      setweight(
          to_tsvector(
              'english'::regconfig,
              'PostgreSQL search ranking'
          ),
          'A'
      )
   || setweight(
          to_tsvector(
              'english'::regconfig,
              'Weighted text search'
          ),
          'B'
      )
   || setweight(
          to_tsvector(
              'english'::regconfig,
              'Database'
          ),
          'C'
      )
   || setweight(
          to_tsvector(
              'english'::regconfig,
              'Search documents and rank matching results'
          ),
          'D'
      ) AS weighted_vector;
~~~

In this context, `||` concatenates `tsvector` values, not text strings or JSONB.

Vector concatenation shifts lexeme positions. That matters for phrase/proximity queries: if a phrase must not cross the boundary between `title` and `summary`, evaluate phrase queries on each field separately rather than assuming concatenated vectors enforce hard boundaries.

### NULL and empty fields

Use `coalesce(field, '')` before `to_tsvector` if a field is nullable. An empty string produces an empty vector and avoids wiping out content from the other fields.

## 5. Lab: Creating the Schema and Articles Table

The SQL statements below use a practice database with schema `fts_rank_lab`.

**Warning:** `DROP SCHEMA ... CASCADE` deletes every existing object in that schema. Run it only in a **dedicated lab database**, never in production.

~~~sql
-- RUN ONLY ON A PRACTICE DATABASE.
DROP SCHEMA IF EXISTS fts_rank_lab CASCADE;
CREATE SCHEMA fts_rank_lab;

CREATE TABLE fts_rank_lab.articles (
    article_id bigint PRIMARY KEY,
    title text NOT NULL,
    summary text NOT NULL DEFAULT '',
    category text NOT NULL DEFAULT '',
    body text NOT NULL,
    published_at timestamptz NOT NULL,
    is_published boolean NOT NULL DEFAULT true,
    search_vector tsvector GENERATED ALWAYS AS (
        setweight(
            to_tsvector(
                'english'::regconfig,
                coalesce(title, '')
            ),
            'A'
        )
        ||
        setweight(
            to_tsvector(
                'english'::regconfig,
                coalesce(summary, '')
            ),
            'B'
        )
        ||
        setweight(
            to_tsvector(
                'english'::regconfig,
                coalesce(category, '')
            ),
            'C'
        )
        ||
        setweight(
            to_tsvector(
                'english'::regconfig,
                coalesce(body, '')
            ),
            'D'
        )
    ) STORED
);
~~~

Stored generated columns were introduced in PostgreSQL 12. The `to_tsvector` expression uses `'english'::regconfig` explicitly so it does not implicitly depend on session configuration and meets the immutability requirement of generated expressions.

### Why store search_vector?

- Avoids recomputing the entire expression on every `SELECT` that uses ranking.
- `INSERT`/`UPDATE` automatically maintains the generated column per PostgreSQL rules.
- Allows creating a GIN index on the stored vector.
- Matching and ranking share one consistent representation.

**Trade-off:** vector values consume storage and add computation/write cost when source columns change.

## 6. Loading Seed Data with Diverse Document Types

~~~sql
INSERT INTO fts_rank_lab.articles (
    article_id, title, summary, category,
    body, published_at, is_published
)
VALUES
(
    1,
    'PostgreSQL search ranking',
    'Weighted full-text search and relevant results',
    'Database',
    'Use tsvector and tsquery to search documents. '
        || 'Ranking places useful articles first. '
        || 'Highlights help readers see matched terms.',
    '2026-01-10 08:00:00+00',
    true
),
(
    2,
    'Building a documentation portal',
    'Navigation, layout, and category filters',
    'Architecture',
    'A search ranking system helps users find documents. '
        || 'Search ranking should consider titles and summaries.',
    '2026-02-10 08:00:00+00',
    true
),
(
    3,
    'Search indexes in PostgreSQL',
    'GIN indexes and query planning',
    'Database',
    'A GIN index helps full text search matching. '
        || 'Ranking and highlighting improve the results page.',
    '2026-03-10 08:00:00+00',
    true
),
(
    4,
    'PostgreSQL transaction locks',
    'Concurrency and lock waits',
    'Database',
    'Row locks protect concurrent updates. '
        || 'An index does not remove every lock wait.',
    '2026-04-10 08:00:00+00',
    true
),
(
    5,
    'Relevance and phrase proximity',
    'How distance between words affects ranking',
    'Search',
    'Search systems can reward close matching terms. '
        || 'Full text search ranking can use cover density.',
    '2026-05-10 08:00:00+00',
    true
),
(
    6,
    'High volume logging guide',
    'Operational logging and retention',
    'Operations',
    'This long technical note discusses many operations. '
        || repeat(
            'The application stores events and rotates logs. ',
            6
        )
        || 'It mentions search ranking once near the end.',
    '2026-06-10 08:00:00+00',
    true
),
(
    7,
    'Search results highlighting',
    'Make matching search words easy to see',
    'Search',
    'PostgreSQL ts_headline builds excerpts from original '
        || 'text, but the output is not automatically safe HTML.',
    '2026-07-10 08:00:00+00',
    true
),
(
    8,
    'Ranking product listings',
    'Relevance, freshness, and popularity',
    'Product',
    'Product search can use title and category matches. '
        || 'Query relevance is not the same as popularity.',
    '2026-08-10 08:00:00+00',
    true
),
(
    9,
    'PostgreSQL text search concepts',
    'Lexemes, stop words, stemming, and phrase queries',
    'Database',
    'A vector contains normalized lexemes and positions. '
        || 'A search query should use matching configuration.',
    '2026-09-10 08:00:00+00',
    true
),
(
    10,
    'Writing faster SQL queries',
    'Reduce work and examine query plans',
    'Performance',
    'Search terms may be selective or common. '
        || 'Indexes can reduce I/O but also increase write cost.',
    '2026-10-10 08:00:00+00',
    true
),
(
    11,
    'Search ranking draft',
    'Unpublished experimental ranking notes',
    'Draft',
    'This draft discusses weighted search fields.',
    '2026-11-10 08:00:00+00',
    false
),
(
    12,
    'PostgreSQL and JSONB',
    'Working with JSON documents',
    'Database',
    'JSONB stores flexible structures and supports indexes.',
    '2026-11-11 08:00:00+00',
    true
);

ANALYZE fts_rank_lab.articles;
~~~

The dataset is designed intentionally:

- Article 1 matches `search ranking` right in the title.
- Article 2 mentions that phrase only in the body.
- Article 5 discusses proximity.
- Article 6 has a long body with the keywords near the end.
- Article 11 is unpublished despite having a relevant title.
- Article 12 is not directly about ranking.

Do not guess exact score numbers in advance: inspect results from running actual queries.

## 7. Creating the GIN Index and Inspecting Vectors

~~~sql
CREATE INDEX idx_articles_vector_gin
ON fts_rank_lab.articles
USING gin (search_vector);

ANALYZE fts_rank_lab.articles;

SELECT
    article_id,
    title,
    search_vector
FROM fts_rank_lab.articles
WHERE article_id IN (1, 2, 6)
ORDER BY article_id;
~~~

`search_vector` contains lexemes and positions with weight labels. Do not expect the vector to retain punctuation, uppercase letters, or original formatting.

On a 12-row table, PostgreSQL may choose `Seq Scan` because it is very cheap. Having an index does not force the planner to use it.

## 8. Preparing tsquery from User Keywords

| Function | Meaning |
| --- | --- |
| `plainto_tsquery` | Plain text; lexemes normally joined with AND |
| `phraseto_tsquery` | Expresses phrase search based on position |
| `websearch_to_tsquery` | Search-box syntax: quotes, OR, minus sign |
| `to_tsquery` | Full `tsquery` syntax, used when constructing controlled expressions |

~~~sql
SELECT
    plainto_tsquery(
        'english'::regconfig,
        'search ranking'
    ) AS plain_query,
    phraseto_tsquery(
        'english'::regconfig,
        'search ranking'
    ) AS phrase_query,
    websearch_to_tsquery(
        'english'::regconfig,
        '"search ranking" OR PostgreSQL'
    ) AS web_query;
~~~

Use bind parameters when keywords come from the application. Never concatenate user input directly into SQL or raw `tsquery` syntax without control.

## 9. Separating Matching Conditions from Access Filters

~~~sql
WITH q AS (
    SELECT websearch_to_tsquery(
        'english'::regconfig,
        'search ranking'
    ) AS search_query
)
SELECT
    a.article_id,
    a.title
FROM fts_rank_lab.articles AS a
CROSS JOIN q
WHERE a.is_published
  AND a.search_vector @@ q.search_query
ORDER BY a.article_id;
~~~

The two predicates play distinct roles:

- `is_published` is a **mandatory visibility rule**.
- `@@` is **matching**.

An unpublished article must never be exposed even if its rank score is high. In multi-tenant systems, add tenant/authorization filters or appropriate RLS. Never turn security into a score boost.

## 10. Ranking with ts_rank

~~~sql
WITH q AS (
    SELECT plainto_tsquery(
        'english'::regconfig,
        'search ranking'
    ) AS search_query
)
SELECT
    a.article_id,
    a.title,
    ts_rank(
        a.search_vector,
        q.search_query
    ) AS score
FROM fts_rank_lab.articles AS a
CROSS JOIN q
WHERE a.is_published
  AND a.search_vector @@ q.search_query
ORDER BY score DESC, a.article_id DESC;
~~~

Scores depend on lexeme frequency, weight labels, distribution, and normalization. **A score of 0.8 does not mean an 80% probability that the article is right.**

A mention in the title contributes with weight `A` while one in the body typically contributes with `D`, yet **there is no guarantee that every title match always outranks every body match**, because scoring involves multiple factors.

## 11. Passing Custom Weights: The D, C, B, A Order

This is an important detail that is easy to mix up.

`ts_rank` and `ts_rank_cd` accept an array of four coefficients in the order:

| Array Element | Weight Label | Common Default |
| ---: | --- | ---: |
| 1 | D | 0.1 |
| 2 | C | 0.2 |
| 3 | B | 0.4 |
| 4 | A | 1.0 |

**The order is D, C, B, A — not A, B, C, D.**

~~~sql
WITH q AS (
    SELECT plainto_tsquery(
        'english'::regconfig,
        'search ranking'
    ) AS search_query
)
SELECT
    a.article_id,
    a.title,
    ts_rank(
        ARRAY[0.05, 0.15, 0.40, 1.00]::real[],
        a.search_vector,
        q.search_query
    ) AS custom_score
FROM fts_rank_lab.articles AS a
CROSS JOIN q
WHERE a.is_published
  AND a.search_vector @@ q.search_query
ORDER BY custom_score DESC, a.article_id DESC;
~~~

Here `D = 0.05`, `C = 0.15`, `B = 0.40`, `A = 1.00`. We reduce the body's contribution relative to the title; the `@@` matching predicate **does not change**.

Weights are a business choice: product names may matter more than descriptions; in certain legal texts, clause paragraphs may matter more than titles.

## 12. ts_rank_cd and Keyword Proximity

`ts_rank_cd` uses **cover-density ranking**, leveraging positional information to reward matches that occur close together.

~~~sql
WITH q AS (
    SELECT plainto_tsquery(
        'english'::regconfig,
        'search ranking'
    ) AS search_query
)
SELECT
    a.article_id,
    a.title,
    ts_rank(a.search_vector, q.search_query) AS rank_simple,
    ts_rank_cd(
        a.search_vector,
        q.search_query
    ) AS rank_cover_density
FROM fts_rank_lab.articles AS a
CROSS JOIN q
WHERE a.is_published
  AND a.search_vector @@ q.search_query
ORDER BY rank_cover_density DESC, a.article_id DESC;
~~~

Intuition: `search ranking` as two adjacent words can signify stronger relevance than `search` at the start of an article and `ranking` far away at the end.

| Characteristic | `ts_rank` | `ts_rank_cd` |
| --- | --- | --- |
| Scores from lexemes/weights | Yes | Yes |
| Evaluates proximity/cover via its own formula | No | Yes |
| Requires positions to compute cover | Unlike `ts_rank_cd` | Yes |
| Always better on every dataset | No | No |

Do not pick a function merely because it sounds more advanced; compare top-K quality on a real corpus.

### Why not strip positions?

~~~sql
SELECT
    ts_rank_cd(
        to_tsvector(
            'english'::regconfig,
            'Search ranking improves results'
        ),
        plainto_tsquery(
            'english'::regconfig,
            'search ranking'
        )
    ) AS with_positions,
    ts_rank_cd(
        strip(
            to_tsvector(
                'english'::regconfig,
                'Search ranking improves results'
            )
        ),
        plainto_tsquery(
            'english'::regconfig,
            'search ranking'
        )
    ) AS without_positions;
~~~

`strip` removes lexeme positions; `ts_rank_cd` lacks cover data and can score 0. Never strip vectors casually if proximity ranking is needed.

## 13. Normalization and Long Documents

Long documents may mention a keyword many times without necessarily being more relevant than a concise paragraph answering the question directly. PostgreSQL supports a `normalization` bitmask.

| Bit | Meaning |
| ---: | --- |
| 0 | No extra normalization |
| 1 | Divides by `1 + log(document length)` |
| 2 | Divides by document length |
| 4 | Mean harmonic distance between extents, used with `ts_rank_cd` |
| 8 | Divides by number of unique lexemes |
| 16 | Divides by `1 + log(unique lexemes)` |
| 32 | Maps score to `rank / (rank + 1)` |

Combining bits `2 | 32 = 34`:

~~~sql
SELECT ts_rank(
    to_tsvector(
        'english'::regconfig,
        'Search ranking and search ranking'
    ),
    plainto_tsquery(
        'english'::regconfig,
        'search ranking'
    ),
    34
);
~~~

### Flag 32 does not turn rank into a probability

If the raw score is `r`:

\[
r_{\mathrm{new}}=\frac{r}{r+1}
\]

For non-negative scores, values map into `[0, 1)`. This is merely a scale transformation, not "0.8 = 80% relevant". Applying a monotonic transform alone does not alter the relative ordering of scores.

### Do not compare scores across different configurations

`ts_rank(..., 0)` and `ts_rank(..., 34)` are not on the same scale. Whenever weights or normalization change, re-evaluate thresholds and ranking quality.

## 14. Complete Ranking Query

~~~sql
WITH q AS (
    SELECT websearch_to_tsquery(
        'english'::regconfig,
        'search ranking'
    ) AS search_query
)
SELECT
    a.article_id,
    a.title,
    ts_rank_cd(
        ARRAY[0.10, 0.20, 0.45, 1.00]::real[],
        a.search_vector,
        q.search_query,
        32
    ) AS relevance_score
FROM fts_rank_lab.articles AS a
CROSS JOIN q
WHERE a.is_published
  AND a.search_vector @@ q.search_query
ORDER BY
    relevance_score DESC,
    a.published_at DESC,
    a.article_id DESC
LIMIT 10;
~~~

This structure illustrates three independent layers:

- `WHERE ... @@`: only matching documents are considered.
- `ts_rank_cd`: computes scores.
- `ORDER BY` / `LIMIT`: selects the prioritized list.

**A small `LIMIT` does not mean the database only scores that many rows.** PostgreSQL may still need to score many candidates to find the top rows.

## 15. Matching Only in Title Using Weight Restrictions

If business rules require `search` to appear in `title` rather than merely giving title matches a higher score:

~~~sql
SELECT
    to_tsquery(
        'english'::regconfig,
        'search:A'
    ) AS title_only,
    to_tsquery(
        'english'::regconfig,
        'search:AB'
    ) AS title_or_summary;
~~~

Usage:

~~~sql
SELECT article_id, title
FROM fts_rank_lab.articles
WHERE is_published
  AND search_vector @@ to_tsquery(
      'english'::regconfig,
      'search:A'
  );
~~~

This is a **filter condition**, distinct from setting `A=1.0` so title matches earn more points.

### GIN and rechecks

A GIN index on `tsvector` primarily stores lexemes to find candidates, **not full weight labels in a way that resolves every weight-restricted query purely from the index**. For `:A` queries, PostgreSQL may need to recheck matching rows.

## 16. Phrase Matching Differs from Cover-Density Ranking

~~~sql
SELECT
    phraseto_tsquery(
        'english'::regconfig,
        'search ranking'
    ) AS phrase_query,
    to_tsquery(
        'english'::regconfig,
        'search <-> ranking'
    ) AS adjacent_query;
~~~

`<->` expresses adjacent lexemes. Other proximity expressions can use `tsquery` distance syntax.

- A phrase query determines **whether a document matches** by position.
- Cover-density ranking determines the **score** from matches and their positions.

A document with two words far apart can match an AND query while failing an adjacent phrase query. When concatenating vectors across multiple fields, note that merged positions can allow phrases to cross field boundaries under that structure.

## 17. Prefixes, Stemming, and Vocabulary Limits

~~~sql
SELECT to_tsquery(
    'english'::regconfig,
    'rank:*'
);
~~~

Lexeme prefix search **is not the same as** substring matching `ILIKE '%ank%'`. Nor does FTS automatically fix typos, understand all synonyms, or match paraphrases.

For autocomplete, typo tolerance, substring search, or semantic search, consider `pg_trgm`, synonym dictionaries, another search engine, or embeddings. Do not adopt extra technology without concrete goals and empirical metrics.

## 18. Empty Queries and Stop Words

Input like `the and of` can leave zero useful lexemes after English processing.

~~~sql
SELECT
    websearch_to_tsquery(
        'english'::regconfig,
        'the and of'
    ) AS query,
    numnode(
        websearch_to_tsquery(
            'english'::regconfig,
            'the and of'
        )
    ) AS node_count;
~~~

You need a product policy:

1. Prompt the user to enter other words.
2. Display a message that the query contained no searchable terms.
3. Return recent/popular items under safe permission filters.
4. Use a separate mechanism designed for empty input.

Do not accidentally score the entire corpus or generate thousands of `ts_headline` calls just because input lacked lexemes.

## 19. Tie-Breakers Keep Results Stable

If two documents have the exact same score, `ORDER BY score DESC` **does not guarantee their relative order**.

Add:

~~~sql
ORDER BY
    relevance_score DESC,
    published_at DESC,
    article_id DESC
~~~

where unique `article_id` breaks ties. This helps UI consistency, testing, and pagination.

Another option is prioritizing newer documents first and ranking second, which is a **different search policy** that must be chosen intentionally.

## 20. Combining Relevance with Freshness/Popularity

Some applications combine text scores with non-FTS signals.

\[
S_{\mathrm{total}} =
\alpha S_{\mathrm{text}} +
\beta S_{\mathrm{freshness}} +
\gamma S_{\mathrm{quality}}
\]

This is a conceptual model, **not a built-in PostgreSQL formula**. Combining components requires calibrating scales, guarding against gaming/manipulation, and evaluating against labeled data.

Specifically:

- **Authorization/tenant/`is_published`** must be filters, not boosts.
- A brand-new but irrelevant article should not outrank an exact match solely due to freshness.
- `ts_rank` is a lexical score, not a probability.

## 21. ts_headline Generates Excerpts from Original Text

~~~sql
SELECT ts_headline(
    'english'::regconfig,
    'PostgreSQL full text search improves search results.',
    plainto_tsquery(
        'english'::regconfig,
        'search results'
    )
) AS highlighted_text;
~~~

`ts_headline` takes **original text** and a `tsquery`, selects a passage containing matched words, and inserts markers. Stored `tsvector` values are normalized into lexemes/positions and are unsuitable for verbatim display.

Default markers may be `<b>`-style markup depending on options.

## 22. Customizing StartSel and StopSel Markers

~~~sql
SELECT ts_headline(
    'english'::regconfig,
    'Search ranking improves search results.',
    websearch_to_tsquery(
        'english'::regconfig,
        'search ranking'
    ),
    'StartSel=<mark>,StopSel=</mark>'
) AS snippet;
~~~

Output meaning:

~~~text
<mark>Search</mark> <mark>ranking</mark>
improves <mark>search</mark> results.
~~~

Output containing markers is **plain text**, not safe HTML yet. You can use markers like `[[...]]` for plain-text UIs, or build a renderer that emits escaped text segments and highlight spans separately.

## 23. Creating Short Snippets with MaxFragments

~~~sql
WITH q AS (
    SELECT websearch_to_tsquery(
        'english'::regconfig,
        'search ranking'
    ) AS search_query
)
SELECT
    a.article_id,
    a.title,
    ts_headline(
        'english'::regconfig,
        a.body,
        q.search_query,
        'StartSel=<mark>,StopSel=</mark>,'
            || 'MaxFragments=2,MinWords=5,MaxWords=18,'
            || 'FragmentDelimiter=...'
    ) AS snippet
FROM fts_rank_lab.articles AS a
CROSS JOIN q
WHERE a.article_id = 2;
~~~

| Option | Meaning |
| --- | --- |
| `StartSel` | Opening marker |
| `StopSel` | Closing marker |
| `MaxFragments` | Maximum number of fragments |
| `MinWords` | Minimum words per fragment rule |
| `MaxWords` | Length limit per fragment rule |
| `FragmentDelimiter` | Separator between fragments |
| `HighlightAll` | Highlight the entire text |
| `ShortWord` | Handling of short words |

Output word counts and fragment boundaries depend on `ts_headline`'s internal heuristics, not an exact fixed character/word count. Test against realistic `body` text.

## 24. Highlighting Title and Body Separately

~~~sql
WITH q AS (
    SELECT websearch_to_tsquery(
        'english'::regconfig,
        'search ranking'
    ) AS search_query
)
SELECT
    a.article_id,
    ts_headline(
        'english'::regconfig,
        a.title,
        q.search_query,
        'StartSel=<mark>,StopSel=</mark>,HighlightAll=true'
    ) AS highlighted_title,
    ts_headline(
        'english'::regconfig,
        a.body,
        q.search_query,
        'StartSel=<mark>,StopSel=</mark>,'
            || 'MaxFragments=2,MinWords=6,MaxWords=24'
    ) AS body_snippet
FROM fts_rank_lab.articles AS a
CROSS JOIN q
WHERE a.article_id = 1;
~~~

Short titles can use `HighlightAll=true`; long bodies should use fragment snippets.

### Can a document match yet have no highlight in body?

Yes. Matching uses the combined vector of `title`, `summary`, `category`, and `body`. A document can match the keyword in **`title`** while **lacking that word in `body`**. `ts_headline(body, ...)` will then highlight nothing.

The UI should highlight `title` and `summary` as well when appropriate, rather than treating the body snippet as sole proof of why a document matched.

## 25. XSS: ts_headline Does Not Sanitize HTML

This is a mandatory security point when delivering results to browsers.

`ts_headline` **is not an HTML sanitizer**. Original text in the database may contain HTML or characters supplied by users or external feeds. The function inserts markers into text; it does not escape other characters.

If the frontend passes raw output into `innerHTML`, it risks HTML injection and **cross-site scripting (XSS)**.

**Safety rules:**

1. Treat both snippets and titles as untrusted data.
2. Never render `ts_headline` output directly as pre-sanitized HTML.
3. If rich markup is required, use context-aware escaping/sanitization allowing only controlled tags and attributes.
4. Prefer renderers that build **text nodes** and separate `mark` elements from safely parsed highlight spans.
5. Never write a quick regex to "strip dangerous tags".

### SQL injection vs XSS

- **SQL injection**: untrusted input alters SQL syntax; prevent with parameterized queries.
- **XSS**: untrusted output is rendered unsafely in a browser; prevent with output encoding/safe rendering.

You can defend against SQL injection completely and still suffer XSS if you render raw `ts_headline` output.

## 26. Rank First, Highlight After LIMIT

A common performance mistake is running `ts_headline` for 100,000 candidates when only 20 results are shown.

`ts_headline` parses original text and selects fragments, consuming CPU and I/O. Instead:

1. Match documents with `@@`.
2. Compute `ts_rank`/`ts_rank_cd`.
3. Sort and `LIMIT 20`.
4. Highlight only those 20 results.

Example:

~~~sql
WITH
q AS MATERIALIZED (
    SELECT websearch_to_tsquery(
        'english'::regconfig,
        'search ranking'
    ) AS search_query
),
top_hits AS MATERIALIZED (
    SELECT
        a.article_id,
        a.published_at,
        ts_rank_cd(
            ARRAY[0.10, 0.20, 0.40, 1.00]::real[],
            a.search_vector,
            q.search_query,
            32
        ) AS score
    FROM fts_rank_lab.articles AS a
    CROSS JOIN q
    WHERE a.is_published
      AND a.search_vector @@ q.search_query
    ORDER BY
        score DESC,
        a.published_at DESC,
        a.article_id DESC
    LIMIT 20
)
SELECT
    a.article_id,
    a.title,
    h.score,
    ts_headline(
        'english'::regconfig,
        a.title,
        q.search_query,
        'StartSel=<mark>,StopSel=</mark>,HighlightAll=true'
    ) AS highlighted_title,
    ts_headline(
        'english'::regconfig,
        a.body,
        q.search_query,
        'StartSel=<mark>,StopSel=</mark>,'
            || 'MaxFragments=2,MinWords=6,MaxWords=24'
    ) AS body_snippet
FROM top_hits AS h
JOIN fts_rank_lab.articles AS a
    ON a.article_id = h.article_id
CROSS JOIN q
ORDER BY
    h.score DESC,
    h.published_at DESC,
    a.article_id DESC;
~~~

### Why use MATERIALIZED?

In PostgreSQL 12+, CTEs can be inlined conditionally. `MATERIALIZED` here makes explicit that `top_hits` is computed before calling `ts_headline` outside.

**`MATERIALIZED` is not always optimal:** it can block other pushdown optimizations. Use it intentionally and verify with `EXPLAIN`.

`LIMIT` still does not avoid all ranking work: if very many documents match, the server may still score many candidates to find the top 20.

## 27. JDBC: Using Bind Parameters for User Input

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;

public static void search(
        Connection connection,
        String userQuery
) throws SQLException {

    String sql = """
        WITH q AS (
            SELECT websearch_to_tsquery(
                'english'::regconfig,
                ?
            ) AS search_query
        )
        SELECT
            a.article_id,
            a.title,
            ts_rank(
                a.search_vector,
                q.search_query
            ) AS score
        FROM fts_rank_lab.articles AS a
        CROSS JOIN q
        WHERE a.is_published
          AND a.search_vector @@ q.search_query
        ORDER BY score DESC, a.article_id DESC
        LIMIT 20
        """;

    try (PreparedStatement ps =
             connection.prepareStatement(sql)) {
        ps.setString(1, userQuery);

        try (ResultSet rs = ps.executeQuery()) {
            while (rs.next()) {
                long id = rs.getLong("article_id");
                String title = rs.getString("title");
                float score = rs.getFloat("score");
                System.out.println(
                    id + ": " + title + " (" + score + ")"
                );
            }
        }
    }
}
~~~

JDBC uses `?` and `setString`. Never construct SQL by concatenating keywords. In production deployments, add permission filters, empty-input checks, result caps, timeouts, and safe rendering.

## 28. GIN Does Not Pre-Sort by Rank

A GIN index on `search_vector` speeds up lexeme lookup. Ranking scores depend on the **specific user's `tsquery`**, so there is no fixed score ordering for GIN to return top-N directly.

A conceptual plan might look like:

~~~text
Bitmap Index Scan on GIN
  -> Bitmap Heap Scan fetching candidates
     -> Compute ts_rank / ts_rank_cd
        -> Sort score DESC
           -> Limit
~~~

Plans are not guaranteed to have those exact nodes. For very broad queries or small tables, PostgreSQL may pick `Seq Scan`.

**Do not treat the presence of a `Sort` node as an automatic bug**, because query-dependent scores usually must be computed and sorted.

## 29. Benchmarking on a Larger Table

A 12-row table works for learning syntax, not for representing systems with millions of documents. Create a dedicated benchmark table:

~~~sql
CREATE TABLE fts_rank_lab.search_bench (
    article_id bigint PRIMARY KEY,
    title text NOT NULL,
    body text NOT NULL,
    search_vector tsvector GENERATED ALWAYS AS (
        setweight(
            to_tsvector('english'::regconfig, title),
            'A'
        )
        ||
        setweight(
            to_tsvector('english'::regconfig, body),
            'D'
        )
    ) STORED
);

INSERT INTO fts_rank_lab.search_bench (
    article_id, title, body
)
SELECT
    g::bigint,
    CASE
        WHEN g % 500 = 0
            THEN 'Search ranking explained'
        WHEN g % 13 = 0
            THEN 'PostgreSQL query guide'
        ELSE 'Technical article ' || g
    END,
    CASE
        WHEN g % 500 = 0
            THEN 'Full text search ranking and highlighting'
        WHEN g % 13 = 0
            THEN 'A guide to efficient database indexing'
        ELSE
            'Background notes about database design '
            || 'and application development'
    END
FROM generate_series(1, 50000) AS s(g);

ANALYZE fts_rank_lab.search_bench;
~~~

Baseline:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT article_id
FROM fts_rank_lab.search_bench
WHERE search_vector @@ plainto_tsquery(
    'english'::regconfig,
    'search ranking'
);
~~~

Add index:

~~~sql
CREATE INDEX idx_search_bench_vector_gin
ON fts_rank_lab.search_bench
USING gin (search_vector);

ANALYZE fts_rank_lab.search_bench;
~~~

Re-run the same SQL. Never guess millisecond timings in advance—they depend on CPU, cache, disk, statistics, and configuration.

### Common queries can get a different plan

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT article_id
FROM fts_rank_lab.search_bench
WHERE search_vector @@ plainto_tsquery(
    'english'::regconfig,
    'database'
);
~~~

A very common term can match most rows, reducing the benefit of an index. Test both common and rare query groups per real workload.

## 30. Reading EXPLAIN for FTS

Signals to inspect:

| Node / Metric | What to Check |
| --- | --- |
| `Seq Scan` | Small table or overly broad match? |
| `Bitmap Index Scan` | Did `@@` use the GIN index? |
| `Bitmap Heap Scan` | How many heap blocks/tuples were read? |
| `Index Cond` | Which conditions were pushed into the index? |
| `Recheck Cond` | Was recheck needed due to weights/lossy bitmap/operators? |
| `Filter` | Were many documents discarded due to status/permissions? |
| `Sort Key` | Is sorting by rank right? |
| `Sort Method` | Top-N heapsort or temp disk spill? |
| `Buffers: shared hit/read` | What did buffer activity look like? |
| `Execution Time` | How long did the server take on this run? |

`shared read` does not necessarily mean physical disk read; it may come from the OS page cache.

`EXPLAIN ANALYZE` measures a single execution with instrumentation overhead and is not equivalent to end-to-end API p95/p99 latency. To validate SLOs, run proper telemetry and load benchmarks.

## 31. Cost of Updating search_vector and GIN

With a stored generated `search_vector` and a GIN index:

~~~sql
BEGIN;

UPDATE fts_rank_lab.articles
SET title = 'Advanced PostgreSQL search ranking'
WHERE article_id = 2
RETURNING
    article_id, title, search_vector;

ROLLBACK;
~~~

When `title` changes, the generated column must be recomputed and the GIN index entries updated.

Potential costs:

- CPU to generate lexemes and weights.
- New MVCC row version.
- Index maintenance.
- WAL and dirty pages.
- `VACUUM` and cleanup of dead tuples.
- I/O and cache contention when many articles update.

An index that accelerates `SELECT` while making `INSERT`/`UPDATE` more expensive is a trade-off to measure. Write-once, read-many archives tolerate this cost well; continuously edited systems require more care.

### Measuring index size and usage stats

~~~sql
SELECT
    pg_size_pretty(
        pg_relation_size(
            'fts_rank_lab.idx_search_bench_vector_gin'::regclass
        )
    ) AS gin_size;
~~~

~~~sql
SELECT
    schemaname,
    relname,
    indexrelname,
    idx_scan,
    idx_tup_read,
    idx_tup_fetch
FROM pg_stat_user_indexes
WHERE schemaname = 'fts_rank_lab'
ORDER BY relname, indexrelname;
~~~

Do not drop an index just because `idx_scan=0` over a short window. Statistics may not cover key search bursts, or may have been reset recently.

## 32. Ranking Quality Requires a Labeled Dataset

There are two separate kinds of testing:

**Quality test:** a representative set of queries with relevance-labeled documents. Metrics can include Precision@K, Recall@K, MRR, or NDCG@K.

**Performance test:** large corpus, common/rare term frequencies, concurrent clients, measuring p50/p95/p99, buffers, CPU/WAL, index size, and write overhead.

Examples:

| Query | Results That Should Rank Higher |
| --- | --- |
| `search ranking` | Articles explaining ranking and weights |
| `postgresql indexes` | Articles about GIN/text search indexing |
| `transaction locks` | Articles on concurrency and lock waits |
| `search highlighting` | Articles about `ts_headline` |
| `product relevance` | Articles on product listing order |

Never choose a weight array based on one good-looking query. Changing weights can improve one query while degrading many others.

## 33. Result Pagination and Ordering Drift

A query like:

~~~sql
ORDER BY score DESC, published_at DESC, article_id DESC
LIMIT 20 OFFSET 20;
~~~

can be expensive at deep offsets because it must score and sort many candidates only to skip the leading rows.

If the corpus is actively updated, edits to title/body or publish timestamps can shift scores and positions between page fetches.

Mitigations:

1. Always include a unique tie-breaker.
2. Cap pagination depth where needed.
3. If stable search sessions are required, consider snapshots, result caching, or cursor policies.
4. For score-based keyset pagination, keep query/weights/filters identical and watch floating-point comparison issues.
5. Define UX behavior when new articles arrive or items are hidden between requests.

Never assume search results form an immutable static list.

## 34. Vietnamese Language and Diacritics

Accented text such as:

~~~text
Hướng dẫn tối ưu tìm kiếm văn bản PostgreSQL
~~~

will not automatically match an unaccented query:

~~~text
toi uu tim kiem van ban
~~~

without a consistent normalization pipeline.

Options to consider:

- `simple` configuration for basic tokenization.
- `unaccent` extension if supported by the environment and allowed by business rules.
- Vietnamese dictionary/tokenizer for compound words.
- Unicode normalization and testing of case, diacritics, and punctuation.
- Rebuilding vectors/indexes whenever analysis rules change.

Simply installing `unaccent` does not switch existing `tsvector`s and `tsquery`s to the same rules. Configure both data and query pipelines consistently, and keep highlighting on the original text.

## 35. Common Mistakes

1. **Confusing matching with ranking:** `@@` does not produce scores.
2. **Passing the weights array in the wrong order:** it must be `D, C, B, A`.
3. **Thinking title matches always beat body matches:** scores depend on multiple factors.
4. **Treating rank scores as probabilities:** `0.8` does not mean 80% relevant.
5. **Calling `ts_rank_cd` after `strip`:** positional information is lost.
6. **Using different configurations for vectors, queries, and headlines.**
7. **Expecting the `english` dictionary to handle all of Vietnamese.**
8. **Using GIN and assuming the index pre-sorts by score.**
9. **Omitting tie-breakers when multiple articles share the same score.**
10. **Failing to filter drafts/tenants/permissions before returning results.**
11. **Calling `ts_headline` on all candidates before `LIMIT`.**
12. **Rendering raw `ts_headline` HTML and creating XSS vulnerabilities.**
13. **Assuming `body` always gets a highlight when the combined vector matched.**
14. **Concatenating user input into SQL or `to_tsquery` without control.**
15. **Failing to handle empty or stop-word-only queries.**
16. **Benchmarking on a 12-row table and extrapolating to production.**
17. **Measuring only `SELECT` while ignoring `INSERT`/`UPDATE` cost on generated vectors and GIN.**
18. **Optimizing latency alone without measuring result quality.**
19. **Tuning weights on a single query and assuming it improves all users' searches.**
20. **Putting `MATERIALIZED` on every CTE even when it blocks other optimizations.**
21. **Paginating with deep `OFFSET` and thinking `LIMIT` makes everything cheap.**
22. **Confusing a snippet with a complete explanation of the rank score.**
23. **Forgetting the PostgreSQL version requirement for stored generated columns.**
24. **Changing ranking without testing authorization and result stability.**

## 36. Exercises with Answers

Use the `fts_rank_lab` schema from the lab. Run DDL/DML only in a practice database; wrap any `UPDATE` in `BEGIN ... ROLLBACK`.

### Exercise 1. How does matching differ from ranking?

**Answer:** `@@` returns a boolean; `ts_rank`/`ts_rank_cd` compute scores for matching documents.

### Exercise 2. Default strongest weight?

**Answer:** `A`; followed by `B`, `C`, and `D`.

### Exercise 3. Order of the weights array?

**Answer:** `D, C, B, A`.

### Exercise 4. Create a title vector with weight A

~~~sql
SELECT setweight(
    to_tsvector('english', 'Search ranking'),
    'A'
);
~~~

**Answer:** Matching lexemes receive weight `A`.

### Exercise 5. Concatenate title and body

~~~sql
SELECT
    setweight(
        to_tsvector('english', 'Search ranking'),
        'A'
    )
    ||
    setweight(
        to_tsvector('english', 'Ranking search results'),
        'D'
    );
~~~

**Answer:** Contains lexemes from both fields with labels `A` and `D`.

### Exercise 6. Why use coalesce?

**Answer:** Replaces NULL fields with empty text, preventing the combined vector from turning NULL.

### Exercise 7. Test an AND query

~~~sql
SELECT
    to_tsvector('english', 'Search ranking improves results')
    @@
    plainto_tsquery('english', 'search ranking');
~~~

**Answer:** `true` when both lexemes match.

### Exercise 8. Search for `search` in title only

~~~sql
SELECT article_id, title
FROM fts_rank_lab.articles
WHERE search_vector @@ to_tsquery(
    'english', 'search:A'
);
~~~

**Answer:** Matches only positions carrying weight `A`.

### Exercise 9. Why must is_published still be filtered?

**Answer:** Matching and ranking do not enforce visibility permissions. Article 11 is unpublished.

### Exercise 10. How does ts_rank_cd differ from ts_rank?

**Answer:** `ts_rank_cd` uses cover density/proximity; neither function universally wins on every corpus.

### Exercise 11. Why does strip affect cover-density?

**Answer:** `strip` removes positional information needed by `ts_rank_cd`.

### Exercise 12. Normalization flag 32?

**Answer:** Applies `r / (r + 1)` transformation; does not turn rank into a probability.

### Exercise 13. Combining flags 2 and 32?

**Answer:** `34`.

### Exercise 14. Phrase query

~~~sql
SELECT phraseto_tsquery(
    'english', 'search ranking'
);
~~~

**Answer:** Produces a query with positional/phrase semantics.

### Exercise 15. Prefix query

~~~sql
SELECT to_tsquery('english', 'rank:*');
~~~

**Answer:** Lexeme prefix, distinct from substring `ILIKE '%ank%'`.

### Exercise 16. Highlight title

~~~sql
SELECT ts_headline(
    'english',
    title,
    plainto_tsquery('english', 'search ranking'),
    'StartSel=<mark>,StopSel=</mark>,HighlightAll=true'
)
FROM fts_rank_lab.articles
WHERE article_id = 1;
~~~

**Answer:** Generates title text with markers around matched words.

### Exercise 17. Highlight body with at most two fragments

~~~sql
SELECT ts_headline(
    'english',
    body,
    plainto_tsquery('english', 'search ranking'),
    'StartSel=<mark>,StopSel=</mark>,'
        || 'MaxFragments=2,MinWords=6,MaxWords=20'
)
FROM fts_rank_lab.articles
WHERE article_id = 2;
~~~

**Answer:** Extracts up to two passages per options and marks matching words.

### Exercise 18. Can raw HTML from ts_headline be rendered directly?

**Answer:** Unsafe. The function does not sanitize source text; apply output encoding/safe rendering to prevent XSS.

### Exercise 19. Why highlight after LIMIT?

**Answer:** Reduces CPU/I/O cost of parsing original text for candidates that are not displayed.

### Exercise 20. Does a GIN index sort by rank?

**Answer:** No; it accelerates lexeme matching, while scores depend on the query.

### Exercise 21. How do you evaluate relevance?

**Answer:** Use Precision@K, MRR, or NDCG@K on labeled query/document sets.

### Exercise 22. What happens with stop-word-only queries?

**Answer:** Can produce an empty `tsquery`. Check `numnode` and handle it in the application.

### Exercise 23. Why might body have no highlights even when the document matches?

**Answer:** The match may come from `title`, `summary`, or `category` in the combined vector.

### Exercise 24. How does a GIN index affect UPDATE on body?

**Answer:** The vector and GIN entries may need updating, increasing CPU/I/O/WAL and potentially preventing HOT updates.

### Exercise 25. Does a score of 0.9 mean 90% relevant?

**Answer:** No; scores are not calibrated probabilities.

### Exercise 26. Why include a tie-breaker?

**Answer:** Two articles with equal scores can change order unpredictably. `published_at DESC, article_id DESC` yields deterministic ordering.

## 37. Pre-Deployment Checklist

- [ ] Identify languages, tokenizers, and text search configurations.
- [ ] Select `title`/`summary`/`category`/`body` and assign business weights.
- [ ] Remember weights array order is **`D, C, B, A`**.
- [ ] Use `coalesce` on nullable text fields.
- [ ] Choose generated vectors or expression indexes per workload and version.
- [ ] Add GIN for `@@` when selectivity and data size warrant it.
- [ ] Use bind parameters and appropriate `tsquery` parsing functions.
- [ ] Handle empty, stop-word-only, and overly broad queries.
- [ ] Enforce tenant, permission, and `is_published` filters.
- [ ] Test ranking with chosen weights and normalization.
- [ ] Test phrase/proximity and title-only queries if required.
- [ ] Sort by `rank DESC` with a unique tie-breaker.
- [ ] Generate snippets after `LIMIT`, not before.
- [ ] Pass original text and the same configuration to `ts_headline`.
- [ ] Never render raw headline output as trusted HTML.
- [ ] Account for matches in fields outside the highlighted snippet.
- [ ] Measure `EXPLAIN`/buffers on a sufficiently large corpus.
- [ ] Measure top-K quality, not just response time.
- [ ] Measure write overhead, GIN size, and WAL under updates.
- [ ] Test Unicode, accented Vietnamese, and unaccented Vietnamese.
- [ ] Plan vector/index rebuilds when changing configurations.
- [ ] Define pagination behavior for new and hidden documents.
- [ ] Document PostgreSQL major version and weights for reproducibility.
- [ ] Never sacrifice security or write SLOs solely to boost rank scores.

## 38. Official PostgreSQL Documentation

Consult the docs for your server's **exact major version**:

- [Full Text Search](https://www.postgresql.org/docs/current/textsearch.html) — FTS overview.
- [Controlling Text Search](https://www.postgresql.org/docs/current/textsearch-controls.html) — matching, weighting, ranking, highlighting.
- [Text Search Functions and Operators](https://www.postgresql.org/docs/current/functions-textsearch.html) — `setweight`, `ts_rank`, `ts_rank_cd`, `ts_headline`, `numnode`.
- [Preferred Index Types for Text Search](https://www.postgresql.org/docs/current/textsearch-indexes.html) — GIN/GiST.
- [Text Search Configuration](https://www.postgresql.org/docs/current/textsearch-configuration.html) — dictionary/parser.
- [Unaccent](https://www.postgresql.org/docs/current/unaccent.html) — diacritic removal with suitable configuration.
- [Generated Columns](https://www.postgresql.org/docs/current/ddl-generated-columns.html) — stored generated `tsvector`.
- [Indexes on Expressions](https://www.postgresql.org/docs/current/indexes-expressional.html) — expression indexes.
- [Using EXPLAIN](https://www.postgresql.org/docs/current/using-explain.html) — scans, sorts, buffers.
- [CREATE INDEX](https://www.postgresql.org/docs/current/sql-createindex.html) — index creation and maintenance.
- [Monitoring Statistics](https://www.postgresql.org/docs/current/monitoring-stats.html) — index/table stats.

`/current/` points to the latest PostgreSQL docs; for older servers, verify stored generated column support, `MATERIALIZED` CTEs, and version-specific options.

## 39. Summary

**Weights, ranking, and highlighting solve three complementary problems that cannot replace one another.**

1. **`tsvector @@ tsquery`** decides which documents match.
2. **`setweight`** distinguishes fields `A`/`B`/`C`/`D`; actual scoring belongs to `ts_rank`/`ts_rank_cd`.
3. **The weights array order is `D, C, B, A`**. Reversing it accidentally favors the body over the title.
4. **`ts_rank_cd`** evaluates cover/proximity and needs positional data; `strip` removes information it relies on.
5. **Normalization** rescales scores without turning them into probabilities.
6. **GIN accelerates matching but does not pre-sort by rank**. Inspect both query plans and ranking quality.
7. **`ts_headline` highlights original text**; run it after selecting top-N and render safely to prevent XSS.
8. **FTS configuration must stay consistent** across vectors, queries, and headlines, especially for Vietnamese.
9. **Ranking does not replace permission filters**. Score only documents the user is authorized to view.
10. **Measure both relevance and performance**, including latency, index size, WAL, and update overhead.

When you combine **field weights, scoring, deterministic sorting, and safe snippets** properly, PostgreSQL delivers text search that fits product needs, is easy to reason about, and runs within controlled operational costs.
