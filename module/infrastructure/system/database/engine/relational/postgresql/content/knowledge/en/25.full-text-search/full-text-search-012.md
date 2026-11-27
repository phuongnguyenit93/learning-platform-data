# Evaluating Search Quality and Choosing Between PostgreSQL FTS and a Dedicated Search Engine

## 1. Scenario: “Fast” Search Results Where Users Still Cannot Find What They Need

An e-commerce application maintains a catalog of products, user guides, and support articles. The engineering team uses PostgreSQL as its primary database and builds search on top of PostgreSQL Full Text Search (FTS).

A user types:

```text
cà phê pha phin
```

The system returns ten documents in 25 ms. Yet the top three hits merely mention “cà phê” in passing footnotes, while the actual phin brewing guide sits at rank eight. From a database perspective, the query is fast. From a user perspective, **search quality is poor**.

Another query:

```text
ca phe phin
```

is typed without Vietnamese diacritics; the system matches accented tokens strictly and replies “No results found”. Another query:

```text
bảo hành máy xay
```

pushes products with expired warranties to the top even though the user is looking for support policy rules.

These examples show that search quality has **multiple dimensions**:

- **Relevance:** returned documents match user intent.
- **Good ranking:** the most helpful documents appear near the top.
- **Coverage:** valid queries do not return empty results due to tokenization, accents, or spelling variants.
- **Safety:** results never leak restricted tenants, unauthorized items, unpublished drafts, or deleted rows.
- **Freshness:** document content and permissions reflect the source of truth within acceptable lag.
- **Performance:** p95/p99 latency, CPU/I/O load, and throughput meet SLOs.
- **Operability:** indexing, synchronization, monitoring, recovery, and cost stay manageable for the team.

> Key lesson: **never decide “PostgreSQL vs. dedicated search engine” solely from a single EXPLAIN plan, a record count, or whether a query feels fast or slow.** First define search quality and measure it against a realistic workload.

### Learning Objectives

After completing this lesson, you will be able to:

1. Build an evaluation query set with **labeled relevance judgments (*qrels*)**.
2. Understand and apply Precision@k, Recall@k, Success@k, MRR, MAP, NDCG@k, and zero-result rate.
3. Distinguish **candidate retrieval** quality from **ranking** quality.
4. Design segmented evaluations broken down by query intent, language, tenant, and popularity.
5. Apply `tsvector`, `tsquery`, `@@`, `ts_rank`, `ts_rank_cd`, GIN, and `pg_trgm` effectively in PostgreSQL.
6. Recognize limitations around Vietnamese text, diacritics, typos, synonyms, compound phrases, and semantics.
7. Read `EXPLAIN (ANALYZE, BUFFERS)` and measure p50/p95/p99 execution latency.
8. Evaluate when PostgreSQL FTS suffices and when a dedicated search engine provides real value.
9. Design synchronization from PostgreSQL as **source of truth** to an external search index handling creates, updates, deletes, replays, rebuilds, and access control.
10. Understand differences between lexical full-text search, trigram fuzzy matching, and vector/semantic search.
11. Run offline evaluation, A/B testing, rollout, and rollback workflows without sacrificing business correctness.

---

## 2. “Search Quality” Is a Product Contract

Before measuring anything, answer these questions:

- **Who are the users?** Shoppers, support agents, administrators, or internal tools?
- **What are they looking for?** Exact item codes, how-to guides, policies, semantic answers, or all matching records?
- **What defines a good outcome?** One exact record, a handful of helpful suggestions, or exhaustive recall across thousands of records?
- **Which documents may be displayed?** Tenant scope, permission groups, publication state, region, and expiration windows.
- **How fresh must results be?** Immediate post-commit visibility, seconds, or minutes?
- **What happens when nothing matches?** Spell correction, synonyms, query fallback, or returning “no results”?

If the search box looks up order codes:

```text
ORD-2026-000123
```

quality means **exactness and correctness**: return the exact order, never a “similar” order from another tenant. A B-tree index on the order code beats complex fuzzy ranking.

If the search box handles documentation questions:

```text
làm sao khôi phục mật khẩu khi mất số điện thoại
```

users need **the document that solves their problem**, even if its title does not repeat every typed word. That involves semantics, synonyms, intent, and ranking.

### 2.1. Classifying Query Intent

| Type | Example | Primary Goal |
|---|---|---|
| Exact ID | `ORD-12345` | Exact authorized record |
| Navigational | `chính sách đổi trả` | Official page/article ranked first |
| Product lookup | `máy pha cà phê` | Matching product type, currently visible |
| Informational | `cách vệ sinh máy xay` | Content answering the question |
| Exploratory | `quà tặng dưới 500k` | Combining keywords and filters |
| Typo | `may pha cafe` | Tolerating typos or missing accents |
| Multi-language | `coffee grinder` | Handling mixed languages/vocabularies |
| No-answer | `sản phẩm không tồn tại` | Never fabricating false matches |
| Restricted | `hồ sơ nội bộ của tenant khác` | Zero unauthorized data leakage |

Never collapse all queries into a single aggregate score and ignore these segments.

## 3. Core Concepts: Candidates, Relevance, and Ranking

A search system usually separates into at least two logical stages:

```text
User query
       |
       v
Parse/build tsquery, tokens, typo fixes...
       |
       v
Candidate retrieval
  (fetch potentially relevant documents)
       |
       v
Filter by tenant, permissions, and status
       |
       v
Ranking
  (score and sort)
       |
       v
Top-k results, snippets, highlights
       |
       v
User interaction
```

**Retrieval** decides which documents have a chance to appear. **Ranking** decides the order among them.

If a truly relevant document **is missed by retrieval**, tuning `ORDER BY ts_rank(...)` can never lift it to the top. Conversely, if it sits in the candidate pool at position 50, ranking needs improvement.

### 3.1. Relevance Differs from Lexical Overlap

A document repeating the word “bảo hành” (warranty) three times is not necessarily more helpful than “Quy trình yêu cầu sửa chữa sau mua” (Post-purchase repair request workflow) when a user asks how to submit a warranty claim.

Relevance usually spans:

- Topic alignment.
- Intent alignment.
- Problem-solving usefulness.
- Factual accuracy.
- Freshness and validity.
- Document type expected by the user.
- Filter alignment (price, status, tenant, permissions).

### 3.2. Ranking Never Replaces Hard Filters

If a row has `is_published = false` or belongs to the wrong `tenant_id`, you cannot “fix” it by subtracting a large score penalty. It must be **excluded from the valid candidate set** by access rules.

Writing:

```sql
WHERE tenant_id = ...
  AND is_published = true
  AND search_vector @@ query
```

is fundamentally safer than fetching restricted records and attempting to demote them in ranking.

## 4. What PostgreSQL Full Text Search Provides

PostgreSQL offers built-in components:

| Component | Role |
|---|---|
| `to_tsvector(config, text)` | Converts text into lexemes using a text search configuration |
| `plainto_tsquery` | Builds a `tsquery` from plain text input |
| `phraseto_tsquery` | Builds a `tsquery` preserving token order/adjacency |
| `websearch_to_tsquery` | Web-style search syntax convenient for user queries |
| `@@` | Tests whether a `tsvector` matches a `tsquery` |
| `ts_rank` | Relevance score from lexeme frequencies and weights |
| `ts_rank_cd` | Cover-density ranking sensitive to lexeme proximity when positions exist |
| `setweight` | Assigns weights A/B/C/D to different document sections |
| `ts_headline` | Generates excerpts with matched terms highlighted |
| `GIN(search_vector)` | Accelerates candidate lookup across many `tsquery` patterns |

FTS works well for internal tools, mid-sized knowledge bases, catalogs with explicit keyword search, or teams already running PostgreSQL who do not need an independent search cluster.

Be realistic about limits: **strong built-in FTS does not automatically supply every feature of a dedicated search engine**, such as multi-language synonym management, typo-tolerant autocomplete, massive real-time faceted aggregations, distributed multi-node sharding, or full hybrid ML ranking.

## 5. Lab: Creating an Evaluation Corpus

The following SQL runs only inside a learning database—never on production data.

### 5.1. Creating the Schema and Table

```sql
CREATE SCHEMA IF NOT EXISTS search330;

CREATE TABLE search330.documents (
    document_id integer PRIMARY KEY,
    tenant_id integer NOT NULL,
    title text NOT NULL,
    body text NOT NULL,
    category text NOT NULL,
    language_code text NOT NULL DEFAULT 'vi',
    is_published boolean NOT NULL DEFAULT true,
    published_at timestamptz NOT NULL,
    search_vector tsvector GENERATED ALWAYS AS (
        setweight(
            to_tsvector('pg_catalog.simple'::regconfig, coalesce(title, '')),
            'A'
        )
        ||
        setweight(
            to_tsvector('pg_catalog.simple'::regconfig, coalesce(body, '')),
            'B'
        )
    ) STORED
);
```

Using `simple` keeps our focus on **evaluating quality**. It is not a specialized Vietnamese word segmenter or analyzer. For Vietnamese, whitespace-delimited syllables, diacritics, and compound words strongly influence relevance.

`GENERATED ... STORED` keeps `search_vector` synchronized whenever `title` or `body` is written. `to_tsvector` receives an explicit configuration so generated expressions satisfy PostgreSQL immutability requirements.

### 5.2. Inserting Sample Documents

```sql
INSERT INTO search330.documents(
    document_id, tenant_id, title, body, category,
    language_code, is_published, published_at
)
VALUES
(101, 7, 'Hướng dẫn pha cà phê phin',
 'Các bước chọn cà phê, ủ bột và pha phin tại nhà.',
 'guide', 'vi', true, '2026-08-10 00:00+00'),

(102, 7, 'Cách vệ sinh phin cà phê',
 'Làm sạch dụng cụ pha phin và giữ hương vị cà phê.',
 'guide', 'vi', true, '2026-08-20 00:00+00'),

(103, 7, 'Cà phê hạt rang mộc',
 'Giới thiệu loại hạt cà phê và mức rang phù hợp.',
 'product', 'vi', true, '2026-08-15 00:00+00'),

(104, 7, 'Máy xay cà phê mini',
 'Máy xay dùng cho cà phê phin và pha máy.',
 'product', 'vi', true, '2026-08-14 00:00+00'),

(105, 7, 'Quy định bảo hành máy xay',
 'Điều kiện bảo hành, thời gian và cách gửi yêu cầu sửa chữa.',
 'policy', 'vi', true, '2026-09-01 00:00+00'),

(106, 7, 'Câu hỏi thường gặp về đổi trả',
 'Quy trình đổi trả sản phẩm và hoàn tiền.',
 'policy', 'vi', true, '2026-08-08 00:00+00'),

(107, 7, 'Cách chọn phin và cà phê',
 'Lựa chọn phin theo khẩu vị, kích thước và cách pha.',
 'guide', 'vi', true, '2026-08-12 00:00+00'),

(108, 7, 'Cà phê pha lạnh',
 'Cách ủ cold brew và bảo quản nước cà phê.',
 'guide', 'vi', true, '2026-08-05 00:00+00'),

(109, 7, 'Mẹo xay cà phê',
 'Điều chỉnh độ mịn cho phin, espresso và pour over.',
 'guide', 'vi', true, '2026-08-11 00:00+00'),

(110, 7, 'Máy pha cà phê tự động',
 'Hướng dẫn sử dụng và làm sạch máy pha cà phê.',
 'product', 'vi', true, '2026-09-10 00:00+00'),

(111, 7, 'Bảo hành và sửa máy pha',
 'Liên hệ trung tâm hỗ trợ để bảo hành máy pha.',
 'policy', 'vi', true, '2026-09-20 00:00+00'),

(112, 7, 'Hỗ trợ lấy lại mật khẩu',
 'Khôi phục quyền truy cập tài khoản bằng email.',
 'support', 'vi', true, '2026-10-01 00:00+00'),

(113, 7, 'Bản nháp chính sách bảo hành',
 'Dự thảo chưa công bố về điều kiện bảo hành.',
 'policy', 'vi', false, '2026-10-03 00:00+00'),

(114, 8, 'Tài liệu máy xay của tenant khác',
 'Hướng dẫn nội bộ cho tenant 8.',
 'guide', 'vi', true, '2026-10-04 00:00+00');
```

Rows **113** and **114** serve as security checks:

- Document 113 is unpublished.
- Document 114 belongs to another tenant.

A normal search by a user in tenant 7 **must never return either document**, regardless of how high the text score is.

### 5.3. Creating a GIN Index for FTS

```sql
CREATE INDEX idx_search330_doc_vector
ON search330.documents
USING gin (search_vector);

CREATE INDEX idx_search330_doc_tenant_visibility
ON search330.documents(tenant_id, is_published);

ANALYZE search330.documents;
```

On a tiny 14-row table, these indexes simply illustrate structure. The planner will likely choose a `Seq Scan` because the table is tiny—not because GIN is broken.

## 6. Baseline Query: Candidate Retrieval and Ranking

Use the exact same text search configuration for both `tsvector` and `tsquery`:

```sql
WITH q AS (
    SELECT websearch_to_tsquery(
        'pg_catalog.simple'::regconfig,
        'cà phê phin'
    ) AS tsq
)
SELECT
    d.document_id,
    d.title,
    ts_rank_cd(d.search_vector, q.tsq) AS relevance_score
FROM search330.documents AS d
CROSS JOIN q
WHERE d.tenant_id = 7
  AND d.is_published = true
  AND d.search_vector @@ q.tsq
ORDER BY
    relevance_score DESC,
    d.document_id ASC
LIMIT 10;
```

Key points to verify:

- `@@` filters documents matching `tsquery`.
- `ts_rank_cd` produces a **ranking score**, not a probability of correctness.
- `ORDER BY ... document_id` provides a deterministic tie-breaker.
- `LIMIT 10` reflects a top-k UI; anything ranked 11th is omitted from the first view.
- Tenant and publication filters sit inside the retrieval query itself.

### 6.1. Inspecting Parsed Query and Document Lexemes

```sql
SELECT
    websearch_to_tsquery(
        'pg_catalog.simple'::regconfig,
        'cà phê phin'
    ) AS parsed_query,
    to_tsvector(
        'pg_catalog.simple'::regconfig,
        'Cà phê pha phin'
    ) AS parsed_document;
```

Observe actual lexemes rather than assuming PostgreSQL splits Vietnamese into linguistic words.

In Vietnamese, space-separated units are usually **syllables**, while compound words span multiple syllables. Capturing the concept “cà phê” differs from simply matching tokens “cà” and “phê”.

### 6.2. Choosing Between ts_rank and ts_rank_cd

`ts_rank` and `ts_rank_cd` are built-in ranking functions with different formulas. `ts_rank_cd` rewards lexeme proximity via cover density when positions are stored.

Never judge which is better solely by name. Evaluate **NDCG@k and MRR** against labeled qrels while checking query latency.

## 7. Title/Body Weights and Other Ranking Signals

In our schema, `title` carries weight `A` and `body` carries weight `B`:

```sql
setweight(to_tsvector('simple', title), 'A')
||
setweight(to_tsvector('simple', body), 'B')
```

Rationale:

- A match in the title is usually a stronger signal.
- Body matches matter, typically with lower weight.
- Stored weights influence `ts_rank` and `ts_rank_cd`.

### 7.1. Never Combine Uncalibrated Score Scales Arbitrarily

Suppose you add extra signals:

- Text relevance score.
- Document recency.
- Official-document boost.
- Usage counts.
- Commercial value.

Do not invent arbitrary formulas like:

```text
score = ts_rank + 10 * popularity + 0.5 * recency
```

when components sit on incompatible scales. Popularity can completely drown out relevance and surface popular yet irrelevant documents.

Follow a disciplined process:

1. Normalize scales and assign explicit weights.
2. Keep hard filters completely separate.
3. Evaluate offline against qrels.
4. Inspect metrics per segment.
5. Run A/B tests with guardrails.
6. Manually review top critical queries.

### 7.2. Distinguishing Commercial Priority from Relevance

Ranking in-stock products higher than out-of-stock products makes sense for shopping. Yet for “điều kiện bảo hành” (warranty policy), policy documentation should outrank product promotions.

Define the **objective** for each query category rather than optimizing the entire search system strictly for clicks or revenue.

## 8. Snippets and Highlighting: Part of UX, Not Just Ranking

PostgreSQL's `ts_headline` extracts snippets around matched lexemes:

```sql
WITH q AS (
    SELECT websearch_to_tsquery(
        'pg_catalog.simple'::regconfig,
        'bảo hành máy xay'
    ) AS tsq
)
SELECT
    d.document_id,
    d.title,
    ts_headline(
        'pg_catalog.simple'::regconfig,
        d.body,
        q.tsq,
        'StartSel=<mark>, StopSel=</mark>, MaxWords=25'
    ) AS snippet
FROM search330.documents AS d
CROSS JOIN q
WHERE d.tenant_id = 7
  AND d.is_published
  AND d.search_vector @@ q.tsq
ORDER BY ts_rank_cd(d.search_vector, q.tsq) DESC,
         d.document_id
LIMIT 10;
```

**Security warning:** never insert `ts_headline` output straight into the DOM as trusted HTML. Source text may contain HTML markup or unsafe characters. Properly escape or sanitize source text while cleanly rendering highlight markers.

Evaluate snippet quality on whether it:

- Explains why the document matched.
- Clearly highlights matched terms.
- Preserves enough context without misleading readers.
- Avoids leaking restricted text spans.
- Displays legibly on mobile devices and meets accessibility standards.

## 9. Vietnamese Must Be Evaluated Explicitly

Vietnamese search introduces distinct challenges:

| Issue | Example | Impact |
|---|---|---|
| Accented / unaccented | `cà phê` / `ca phe` | Tokens fail to match |
| Multi-syllable compounds | `máy pha cà phê` | Tokenization misses phrase boundaries |
| Typos | `may pha ca phee` | Lexical FTS misses completely |
| Synonyms | `đổi trả` / `hoàn hàng` | Weak lexical overlap |
| Abbreviations | `BH` / `bảo hành` | Needs context-aware alias dictionaries |
| Product codes | `MX-100` / `MX100` | Hyphen tokenization diverges |
| Mixed English/Vietnamese | `coffee grinder máy xay` | Requires multi-config/language handling |
| Places / proper nouns | `Đà Nẵng` / `Da Nang` | Requires careful normalization |

The `simple` configuration does not solve these automatically.

### 9.1. unaccent Is a Tool, Not a Complete Solution

The `unaccent` extension folds accented characters into simpler forms:

```sql
-- Only in environments permitted to install extensions:
CREATE EXTENSION IF NOT EXISTS unaccent;

SELECT unaccent('Cà phê pha phin');
```

Keep in mind:

- Check extension availability and role privileges.
- Accent removal can conflate distinct proper nouns and homographs.
- Normalization must be applied **consistently** to both documents and queries.
- `unaccent` functions/dictionaries carry volatility constraints; never place `unaccent(...)` directly inside generated columns or expression indexes expecting `IMMUTABLE`.
- Updating dictionary rules requires rebuilding derived vectors/indexes.

Never bypass PostgreSQL checks with a false `IMMUTABLE` wrapper without strict dictionary versioning and rebuild governance.

### 9.2. Evaluate Unaccented Queries as a Dedicated Segment

Create a dedicated evaluation slice:

```text
q1: cà phê pha phin
q2: ca phe pha phin
q3: máy xay cà phê
q4: may xay ca phe
```

Never look only at overall averages; a system scoring well on accented queries while failing completely on unaccented typing can still fail real users.

### 9.3. Advanced Linguistic Segmentation

For high-precision Vietnamese search over large corpora, evaluate:

- Dedicated Vietnamese NLP word-segmentation pipelines.
- Keyword normalization and domain synonym expansion.
- Custom analyzers inside a dedicated search engine.
- A query-rewriting layer.
- Hybrid lexical + semantic retrieval when justified by cost and data.

Measure every change on qrels rather than demoing a couple of cherry-picked queries.

## 10. LIKE, Trigrams, and FTS Serve Different Goals

Compare:

```sql
WHERE title ILIKE '%cafe%'
```

with:

```sql
WHERE search_vector @@ websearch_to_tsquery(...)
```

and with trigram similarity matching.

### 10.1. LIKE / ILIKE

- Intuitive for substring and prefix checks.
- Prefix patterns can use B-tree indexes under compatible collations/operator classes.
- Infix substrings like `'%abc%'` cannot use standard B-trees effectively.
- `ILIKE` does not handle missing accents, typos, or synonyms.

### 10.2. pg_trgm

`pg_trgm` helps with substring matching and string similarity:

```sql
-- If extension is available and permitted:
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE INDEX idx_search330_title_trgm
ON search330.documents
USING gin (title gin_trgm_ops);
```

Example:

```sql
SELECT document_id, title
FROM search330.documents
WHERE title ILIKE '%pha phin%'
ORDER BY document_id;
```

And similarity matching:

```sql
SELECT document_id, title,
       similarity(title, 'may xay ca phe') AS sim
FROM search330.documents
WHERE title % 'may xay ca phe'
ORDER BY sim DESC, document_id;
```

The `%` operator compares against the session's `similarity_threshold`; matching trigrams do not automatically guarantee intent match, and very short strings behave differently under trigram splits.

### 10.3. pg_trgm Does Not Become Semantic Search

“hoàn tiền” (refund in Vietnamese) and “refund” share meaning yet share almost no character trigrams. Trigrams measure **surface character similarity**, not synonym dictionaries or semantic retrieval.

### 10.4. Match the Tool to the Query Class

A combined strategy might use:

- Exact IDs → B-tree equality.
- Keyword documents → FTS.
- Product name typos/fuzzy → trigrams.
- Synonyms / domain terms → controlled query expansion.
- Natural-language intent with low lexical overlap → consider semantic/hybrid search.

Avoid forcing a single technique onto every query type.

## 11. Building an Evaluation Query Set

A representative query set underpins every search metric.

Collect queries from:

1. Anonymized search logs.
2. Real customer support tickets.
3. Commonly searched product names and SKUs.
4. Zero-result queries.
5. Queries followed immediately by query reformulation.
6. Queries with typos or omitted diacritics.
7. Rare *tail queries*.
8. Cross-tenant, authorization, newly published, and deleted edge cases.
9. True no-answer queries.
10. Business-critical queries regardless of frequency.

### 11.1. Never Evaluate Only the Top 10 Popular Queries

If your test suite overflows with “máy pha cà phê” while ignoring “mất hóa đơn đổi trả”, headline scores can look rosy while real users struggle when they need help most.

Stratify your query set by:

```text
Exact match / navigational / informational / exploratory
Accented / unaccented / English / mixed language
Head / torso / tail queries
New / old / long / short documents
Answerable / no-answer
Public / tenant-restricted
```

### 11.2. Separate Development and Holdout Sets

Use:

- A **Development set** to tune weights, synonyms, tokenizers, and ranking.
- A **Validation/holdout set** for final evaluation to avoid “teaching to the test”.

When the engineers tuning ranking also label and optimize exclusively on the same queries, metrics overfit. Use independent reviewers and clear labeling rubrics.

## 12. Qrels: Measuring Degree of Relevance

In information retrieval, **qrels** (query relevance judgments) record graded relevance pairs:

```text
(query_id, document_id) -> relevance_grade
```

A standard graded scale:

| Grade | Meaning |
|---:|---|
| 0 | Irrelevant |
| 1 | Marginally related / mentions keyword without solving intent |
| 2 | Clearly relevant and helpful |
| 3 | Highly relevant or canonical target result |

This scale is an **evaluation convention** that annotators must apply consistently.

Example for the query “cà phê pha phin”:

| Document | Sample Grade | Reason |
|---|---:|---|
| 101 — Hướng dẫn pha cà phê phin | 3 | Directly answers intent |
| 107 — Cách chọn phin và cà phê | 2 | Useful for the same intent |
| 102 — Cách vệ sinh phin cà phê | 1 | Related topic, different step |
| 104 — Máy xay cà phê mini | 1 | Companion product, not brewing steps |
| 103 — Cà phê hạt rang mộc | 1 | Related ingredient |
| 105 — Bảo hành máy xay | 0 | Off-topic for brewing intent |

No single grade is universally “absolute”; grades reflect the defined user intent.

### 12.1. Judge Using Full Documents

Annotators should not grade from titles or snippets alone when relevance depends on body content. They need the full document or sufficient context to verify whether it solves the query.

### 12.2. Never Treat Raw Clicks as Automatic Ground Truth

Users disproportionately click top positions (**position bias**), influenced heavily by titles, snippets, and UI layout. High click counts often reflect high placement rather than highest quality.

Click logs provide valuable signals, yet **are not equivalent to independent qrels**.

## 13. Storing Queries and Qrels in PostgreSQL

A minimal evaluation schema:

```sql
CREATE TABLE search330.eval_queries (
    query_id integer PRIMARY KEY,
    query_text text NOT NULL,
    intent text NOT NULL,
    segment text NOT NULL
);

CREATE TABLE search330.eval_qrels (
    query_id integer NOT NULL
        REFERENCES search330.eval_queries(query_id),
    document_id integer NOT NULL
        REFERENCES search330.documents(document_id),
    relevance_grade smallint NOT NULL
        CHECK (relevance_grade BETWEEN 0 AND 3),
    PRIMARY KEY (query_id, document_id)
);

INSERT INTO search330.eval_queries(
    query_id, query_text, intent, segment
)
VALUES
    (1, 'cà phê pha phin', 'informational', 'vi_accented'),
    (2, 'ca phe pha phin', 'informational', 'vi_unaccented'),
    (3, 'bảo hành máy xay', 'navigational', 'vi_accented'),
    (4, 'máy xay cà phê', 'product', 'vi_accented');

INSERT INTO search330.eval_qrels(
    query_id, document_id, relevance_grade
)
VALUES
    (1, 101, 3),
    (1, 107, 2),
    (1, 102, 1),
    (1, 103, 1),
    (1, 104, 1),
    (1, 105, 0),

    (2, 101, 3),
    (2, 107, 2),
    (2, 102, 1),

    (3, 105, 3),
    (3, 111, 2),
    (3, 104, 1),
    (3, 106, 1),

    (4, 104, 3),
    (4, 110, 2),
    (4, 109, 1),
    (4, 103, 1);
```

### 13.1. These Sample Qrels Are Not “Complete Judgments”

This fixture labels only a subset of pairs for illustration. Assuming **every unlabeled document is irrelevant** skews metrics.

In real evaluations:

- Pool candidates from multiple retrievers.
- Judge deeply enough into top-k results.
- Track `judgment coverage`.
- Distinguish **unjudged** from grade 0.
- Expand qrels whenever a new ranker surfaces previously unseen top-k items.

Never treat a tiny fixture as complete ground truth for a full production corpus.

## 14. Precision@k: How Many Top-k Results Are Useful?

**Precision@k** measures the share of relevant results inside the top-k once a relevance threshold is defined.

Suppose `grade >= 2` counts as relevant.

Formula:

\[
P@k = \frac{\#\{\text{relevant results in top-k}\}}{k}
\]

Illustrative ranking for query `q1`:

| Position | Document | Grade | Relevant (>=2)? |
|---:|---|---:|---|
| 1 | 101 | 3 | Yes |
| 2 | 104 | 1 | No |
| 3 | 107 | 2 | Yes |
| 4 | 103 | 1 | No |
| 5 | 102 | 1 | No |

In top-3 there are 2 relevant hits:

\[
P@3 = 2/3 \approx 0.667
\]

In top-5 there are 2 relevant hits:

\[
P@5 = 2/5 = 0.4
\]

This is a **synthetic ranking for walking through the metric**, not output from running the FTS lab.

### 14.1. Precision@k Fits Top-k UIs

If a page shows 5 items first, P@5 answers intuitively: “how many useful choices appear on screen?”

However, P@k says nothing about how many great documents **were missed altogether**.

### 14.2. When Fewer Than k Results Are Returned

Under standard top-k definitions, you still divide by `k`. If the system returns only one relevant document when `k = 5`:

```text
P@5 = 1/5
```

Document your convention clearly, because some dashboards divide by actual returned count instead. Never compare numbers computed under conflicting denominators.

### 14.3. P@k Is Binary

Grades 2 and 3 both count equally as relevant. When distinguishing “excellent” from “acceptable” and penalizing lower ranks matters, use NDCG@k.

## 15. Recall@k: How Many Relevant Documents Did the System Find?

**Recall@k** measures the fraction of all relevant documents captured in the top-k:

\[
R@k = \frac{\#\{\text{relevant results in top-k}\}}
{\#\{\text{all relevant documents in the evaluated scope}\}}
\]

Suppose `q1` has three relevant documents in the corpus: 101, 107, and 120. If top-3 returns only 101 and 107:

\[
R@3 = 2/3 \approx 0.667
\]

**Document 120 is strictly hypothetical for hand-calculation** and is not part of the `search330` fixture.

### 15.1. Recall Depends on Knowing “All Relevant Documents”

If a corpus holds one million documents and only 10 are labeled, true corpus-wide recall is unknown.

In practice, teams rely on:

- Multi-retriever candidate pooling.
- Representative labeled samples.
- Explicit Recall@k definitions scoped to the judged pool.
- Separate evaluation of retrieval-stage coverage.

### 15.2. When Zero Documents Are Truly Relevant

The denominator is 0. Never divide by zero or report Recall@k = 100%. Track **no-answer queries** separately or exclude them explicitly from Recall@k aggregations.

## 16. Success@k and MRR: Where Is the First Right Result?

For navigational “find the right answer” queries, **Success@k** is helpful:

```text
Success@k = 1 if at least one relevant document appears in top-k
            0 otherwise
```

For “chính sách bảo hành máy xay”:

- First hit at rank 1 → Success@3 = 1.
- First hit at rank 3 → Success@3 = 1.
- First hit at rank 8 → Success@3 = 0.

Success@k does not differentiate rank 1 from rank 3 once both sit inside top-k.

### 16.1. Reciprocal Rank (RR)

If the first relevant document sits at rank `r`:

\[
RR = 1/r
\]

Examples:

| First Relevant Position | RR |
|---:|---:|
| 1 | 1.0 |
| 2 | 0.5 |
| 3 | 0.333 |
| 5 | 0.2 |
| Not within cutoff | 0 |

**Mean Reciprocal Rank (MRR)** averages RR across the query set.

### 16.2. When to Use MRR

MRR shines when users want **one canonical target**:

- The exact user guide page.
- A policy document.
- A specific record ID or support article.
- A task entry point.

MRR does not evaluate the rest of the list; a query with five good documents still scores RR = 1 if only the top slot is good.

## 17. Average Precision and MAP

**Average Precision (AP)** averages precision evaluated at every relevant rank position, normalized by total relevant count.

Standard binary-relevance formula:

\[
AP = \frac{1}{R}
\sum_{i=1}^{n} P@i \cdot rel_i
\]

Where:

- `R` is the total number of relevant documents in the evaluation set.
- `rel_i` equals 1 if result `i` is relevant, else 0.
- `P@i` is Precision@i.
- `n` is the evaluated cutoff length.

**MAP** = mean AP across all queries.

### 17.1. Why MAP Helps

Packing relevant items near the top yields high AP; scattering them deep amid irrelevant hits lowers AP.

Caveats:

- Requires reasonably complete relevance labels to know `R`.
- Needs an explicit cutoff when not scoring entire rankings.
- Binarizes graded 0–3 judgments; NDCG leverages multi-level grades better.

Never compute MAP solely from unlabeled click logs and claim exact accuracy.

## 18. NDCG@k: Measuring Graded Order Quality

**Normalized Discounted Cumulative Gain** is standard when qrels use grades 0, 1, 2, 3.

Common formulation:

\[
DCG@k =
\sum_{i=1}^{k}
\frac{2^{rel_i}-1}{\log_2(i+1)}
\]

Where:

- `rel_i` is the relevance grade at rank `i`.
- Higher grades receive exponentially higher gains.
- The logarithmic denominator discounts lower ranks smoothly.

Normalized form:

\[
NDCG@k = \frac{DCG@k}{IDCG@k}
\]

`IDCG@k` is the DCG of the **ideal** descending grade order within the same evaluation scope.

### 18.1. Why NDCG Suits Document Search

Suppose grade 3 solves the question directly, grade 2 helps significantly, and grade 1 only touches on the topic.

Putting grade 3 at rank 1 clearly beats putting grade 1 at rank 1 and grade 3 at rank 5. P@5 with threshold `>= 2` ignores that distinction, whereas NDCG rewards **both higher relevance and earlier placement**.

### 18.2. NDCG Cannot Be Trusted If Qrels Have Severe Gaps

If a new ranker promotes a relevant document that was never judged, defaulting unjudged items to grade 0 unfairly penalizes the improved ranker.

Always report alongside NDCG@k:

- Judgment coverage across top-k.
- Judged pool size.
- Segment/query coverage.
- Treatment of unjudged items.

### 18.3. What NDCG Does Not Measure

NDCG does not capture:

- Latency.
- Access control enforcement.
- Index freshness.
- Operational cost.
- Whether users actually completed their task.

It is one lens, never a universal “total search quality score”.

## 19. An SQL Calculation: Precision@5 on a Labeled Query

Using the `search330` fixture, we can run an **illustrative metric calculation**. Unjudged items must normally be handled transparently; here we deliberately map `unjudged -> 0` solely to demonstrate the SQL query—**do not treat this as a production judgment**.

```sql
WITH q AS (
    SELECT
        query_id,
        websearch_to_tsquery(
            'pg_catalog.simple'::regconfig,
            query_text
        ) AS tsq
    FROM search330.eval_queries
    WHERE query_id = 1
),
candidate_scores AS (
    SELECT
        d.document_id,
        ts_rank_cd(d.search_vector, q.tsq) AS score
    FROM search330.documents AS d
    CROSS JOIN q
    WHERE d.tenant_id = 7
      AND d.is_published
      AND d.search_vector @@ q.tsq
),
ranked AS (
    SELECT
        document_id,
        row_number() OVER (
            ORDER BY score DESC, document_id
        ) AS position
    FROM candidate_scores
)
SELECT
    COALESCE(
        SUM(
            CASE WHEN COALESCE(j.relevance_grade, 0) >= 2
                 THEN 1 ELSE 0 END
        ),
        0
    )::numeric / 5 AS precision_at_5
FROM ranked AS r
LEFT JOIN search330.eval_qrels AS j
    ON j.query_id = 1
   AND j.document_id = r.document_id
WHERE r.position <= 5;
```

### 19.1. Interpreting the Output Correctly

This query evaluates **P@5 for a single query on one run**, not overall system quality.

If only two hits return and both are relevant, the formula still divides by 5 under the fixed P@5 definition.

If an unjudged hit is actually relevant, `COALESCE(grade, 0)` underestimates true P@5.

### 19.2. Evaluating Many Queries Together

Execute the same pipeline across every `query_id`, store top-k ranked lists and scores tagged with a **fixed run/version**, then join against `qrels` and compute averages by segment.

To keep runs reproducible, record:

```text
run_id
query_id
document_id
rank_position
score
retriever_version
ranker_version
index_snapshot
evaluated_at
```

Never log a bare “P@5 = 0.8” without knowing which index snapshot and version produced it.

## 20. Checking Coverage and Zero-Result Rate

Important queries often return zero results due to:

- Unaccented queries failing accented tokens.
- Spelling mistakes.
- Renamed products.
- Missing synonym expansion.
- Tokenization mismatches.
- Unsynced or unpublished documents.
- Valid access restrictions yielding an empty authorized set.

**Zero-result rate (ZRR)**:

\[
ZRR = \frac{\#\{\text{queries returning 0 results}\}}
{\#\{\text{evaluated queries}\}}
\]

### 20.1. Low ZRR Does Not Guarantee Good Search

Returning popular filler documents for every query achieves `ZRR = 0` with terrible relevance.

Monitor ZRR alongside:

- Precision / NDCG.
- No-answer correctness.
- Query reformulation rate.
- Search abandonment.
- Click-through and task completion where measurable.

### 20.2. Returning Zero Results Can Be Right

When users search for nonexistent items or restricted records they cannot view, returning nothing is the correct answer. Never reduce ZRR by returning wrong documents or leaking unauthorized data.

## 21. Search Abandonment and Query Reformulation

Common online signals:

| Signal | Possible Meaning | Caveat |
|---|---|---|
| No result clicked | Poor results, or answer already visible in snippet | Not always a failure |
| Immediate query rewrite | Weak initial keywords or zero hits | Could be normal exploration |
| Top result clicked | Strong relevance | Subject to position bias |
| Quick return to search | Page failed to satisfy intent | Needs session context |
| Long dwell time | Deep reading | Could also indicate confusing page |
| Task completed | Strong positive outcome | Hard to attribute across funnels |

Never treat any single behavioral metric as absolute ground truth.

### 21.1. Privacy and Search Logs

Search queries often carry customer names, order numbers, emails, medical info, internal secrets, or commercial data.

When logging searches:

- Strip or anonymize sensitive queries per policy.
- Enforce retention limits.
- Restrict log access tightly.
- Never log tokens or API credentials.
- Never train or build recommendations for tenant B using tenant A's logs without explicit authorization and policy compliance.
- Separate evaluation datasets from user-identifiable telemetry.

## 22. Segment Analysis Beats Overall Averages

Suppose overall metrics report:

```text
Overall NDCG@10 = 0.86
```

Yet segmented breakdown reveals:

| Segment | Illustrative NDCG@10 | Issue |
|---|---:|---|
| Accented popular queries | 0.93 | Strong |
| Unaccented queries | 0.42 | Poor lexical overlap |
| Exact product SKUs | 0.98 | Excellent |
| Policy questions | 0.61 | Canonical docs ranked too low |
| English queries | 0.53 | Mismatched analyzer/vocabulary |

These are **illustrative numbers**, not measurements from the lab or any specific product.

If many users type without accents, a blended 0.86 hides a broken experience.

### 22.1. Segmenting by Tenant

In multi-tenant systems:

- Tiny tenants behave very differently from tenants with millions of docs.
- RLS and ACL rules can drastically reshape candidate sets.
- Ranking tuned on large tenants may break on small tenants.

Always include automated tests verifying **zero cross-tenant leakage**—this is a hard invariant, not a 99% target metric.

### 22.2. Head vs. Tail Queries

Head queries accumulate abundant clicks and qrels. Rare tail queries need deliberate sampling and manual labeling so they are not neglected.

Optimizing exclusively for head queries breaks high-value specialized searches.

## 23. Offline Evaluation: Comparing Fairly on One Corpus and Query Set

A clean offline workflow:

1. Snapshot or freeze a corpus version.
2. Lock the evaluation query set.
3. Annotate qrels using a consistent rubric.
4. Run the baseline PostgreSQL FTS setup.
5. Run candidate improvements (weights, trigrams, analyzers, or an external engine).
6. Save top-k results for every run.
7. Compute identical metrics with identical cutoffs and unjudged policies.
8. Inspect breakdowns by segment.
9. Review individual query-level regressions, not only averages.
10. Advance to online tests only once hard constraints and quality bars pass.

### 23.1. Never Compare Systems Against Differing Corpora

If PostgreSQL reflects today's commits while an external search index reflects yesterday's snapshot, output differences stem from **freshness lag**, not ranking quality.

For pure relevance comparisons, freeze equivalent snapshots. Measure **freshness lag as its own dedicated metric** in end-to-end tests.

### 23.2. Record Full Experiment Metadata

Every benchmark report should capture:

```text
dataset_id
snapshot_time
query_set_version
qrels_version
retriever_version
ranking_version
normalization_version
index_configuration
hardware/configuration
metric_definition
cutoff
```

Without versioned metadata, improvements cannot be reproduced reliably.

## 24. A/B Testing: Strong Offline Scores Are Not Enough

Offline relevance efficiently filters bad ranking ideas, yet never fully captures live user behavior.

Online A/B tests measure:

- Search success / task completion.
- Query reformulation and abandonment.
- Bias-adjusted click behavior.
- Conversion or support resolution rates.
- End-to-end p95/p99 latency.
- Error and timeout rates.
- Authorization filtering rates.
- CPU, memory, and cost impact on PostgreSQL and search clusters.

### 24.1. Avoid Optimizing for “Clicks at Any Cost”

An informative snippet can answer a question directly (reducing clicks while improving UX), whereas clickbait titles boost clicks while ruining task success.

Pair **primary business outcome metrics** with strict **guardrail metrics**.

### 24.2. Experiment Randomization

Randomize consistently by user, session, or tenant depending on isolation needs, ensuring a user does not flip between competing rankers mid-session.

In multi-tenant setups, never design an experiment that risks mixing documents across tenants.

### 24.3. Feedback Loops in Ranking

Changing ranking shifts click logs, which in turn shifts future click-trained models or boosts. Separate short-term experiment lifts from long-term behavioral feedback loops.

## 25. Latency: Measure End-to-End, Not Just One SELECT

Measure the entire request path:

```text
Query request received
    |
    +-- authentication / authorization
    +-- normalization / query parsing
    +-- PostgreSQL or external retrieval
    +-- ranking / optional reranking
    +-- hydrate display fields
    +-- render snippets / facets
    +-- send response
```

User-perceived latency equals the sum of every step plus network and queuing delays.

### 25.1. Percentiles and System Metrics to Watch

| Metric | Meaning |
|---|---|
| p50 | Median, typical user experience |
| p95 | 95% of requests complete within this latency |
| p99 | Slow tail critical for SLO compliance |
| Error rate | Failed, timed-out, or throttled queries |
| Throughput | Queries per second under workload |
| CPU / I/O | Resource consumption cost |
| Connection pool waits | Time spent waiting for a DB connection |
| Index freshness lag | Sync delay in external search setups |

**SLOs belong to each specific product**—targets such as “200 ms at p95” are purely illustrative unless backed by product requirements. Never treat one threshold as universal.

### 25.2. Inspect p95 Instead of Averages Alone

Averages of 20 ms hide painful 3-second sorts on broad terms. Measure latency sliced by:

- Query length.
- Number of `tsquery` tokens.
- High-frequency terms.
- Zero-hit queries.
- Large tenants.
- Page 1 vs. deep pagination.
- Concurrent load.
- Cold vs. warm caches.

## 26. EXPLAIN: Seeing Retrieval vs. Ranking Costs

Diagnostic query:

```sql
EXPLAIN (ANALYZE, BUFFERS)
WITH q AS (
    SELECT websearch_to_tsquery(
        'pg_catalog.simple'::regconfig,
        'cà phê'
    ) AS tsq
)
SELECT
    d.document_id,
    ts_rank_cd(d.search_vector, q.tsq) AS score
FROM search330.documents AS d
CROSS JOIN q
WHERE d.tenant_id = 7
  AND d.is_published
  AND d.search_vector @@ q.tsq
ORDER BY score DESC, d.document_id
LIMIT 10;
```

Common plan nodes:

- `Seq Scan`.
- `Bitmap Index Scan` on GIN.
- `Bitmap Heap Scan`.
- `Sort` or `top-N heapsort` where applicable.
- `Limit`.

### 26.1. GIN Does Not Pre-Sort by Dynamic Rank

GIN locates rows matching `tsquery` lexemes. It **does not** store precomputed `ts_rank_cd` scores for arbitrary runtime queries.

Consequently, when a keyword matches many candidates, PostgreSQL still has to **score and sort many rows** before returning top-k even when GIN retrieval itself is fast.

This explains why complex ranking over massive corpora outgrows “just add a GIN index”.

### 26.2. ts_rank / ts_rank_cd Are Not Quality Metrics

They are **runtime scoring functions**, not Precision@10 or NDCG@10. Use them to rank hits, then evaluate output quality against qrels.

### 26.3. EXPLAIN ANALYZE Executes SELECT

On `SELECT`, `EXPLAIN ANALYZE` runs the query to collect actual timings. On DML (`INSERT`/`UPDATE`/`DELETE`), it mutates data. Never run DML `EXPLAIN ANALYZE` casually in production.

### 26.4. Tiny Fixtures Do Not Benchmark Scale

On 14 rows, `Seq Scan` easily beats GIN—that is smart cost-based planning, not evidence that PostgreSQL FTS fails to scale.

## 27. Write Overhead and Maintaining search_vector

FTS indexes carry ongoing write cost:

- `INSERT` builds `search_vector` and updates GIN postings.
- `UPDATE` on `title`/`body` recomputes vectors and updates index entries.
- `DELETE` creates MVCC/index cleanup work.
- `VACUUM`, WAL generation, checkpoints, and backups all absorb extra volume.
- Very large documents amplify ranking, snippet extraction, and storage costs.

### 27.1. Generated Columns vs. Expression Indexes

You can create a GIN expression index:

```sql
CREATE INDEX idx_example_expression_fts
ON some_table
USING gin (
    to_tsvector('simple'::regconfig, coalesce(body, ''))
);
```

or store `search_vector` via `GENERATED ALWAYS ... STORED` as in our lab. Weigh:

- Complexity of title/body weights.
- Update frequency.
- Whether `tsvector` must be accessed at runtime for ranking or `ts_headline`.
- Keeping query expressions identical to index expressions.
- Stability of the text search configuration.

Avoid relying on single-argument `to_tsvector(body)` inside indexes if you want session-independent behavior and clean immutability guarantees.

### 27.2. Watch OLTP Contention

If the same PostgreSQL instance handles orders, payments, or hot transactions, heavy multi-candidate search queries compete directly for CPU, RAM, and I/O with OLTP traffic.

Offloading to a dedicated search engine can provide valuable **workload isolation** even when PostgreSQL lexical quality suffices—at the cost of sync complexity and operational overhead.

## 28. Technical Boundary: When Is PostgreSQL Usually Enough?

PostgreSQL is often the right first choice when:

- Corpus size and query rates fit comfortably inside measured resource budgets.
- Queries focus on exact lookups, structured filters, light prefix/fuzzy matching, or lexical FTS.
- Strict transactional consistency with primary records is essential.
- Permissions and tenant scope tie closely to relational tables and RLS.
- Requirements do not demand complex synonyms, multi-language morphology, massive real-time faceting, or semantic ranking.
- The team prefers operating fewer distributed systems.
- p95/p99 latency meets SLOs under realistic concurrency.
- Operating an external search cluster yields insufficient marginal benefit.

### 28.1. “Small Corpus” Alone Is Not Sufficient Criteria

Even a small corpus can justify a dedicated search engine when product experience relies heavily on:

- High-accuracy Vietnamese morphological segmentation.
- Typo-tolerant search-as-you-type autocomplete.
- Rich synonym management.
- Multi-signal personalized ranking.
- Deep multi-dimensional faceting.
- Integrated vector/hybrid retrieval tooling.

Conversely, very large tables queried by key plus focused predicates run smoothly on PostgreSQL given solid indexing, partitioning, and workload isolation.

**Draw the boundary using requirements and measurements, never a raw row threshold.**

## 29. When to Consider a Dedicated Search Engine

Common warning signs include:

1. **Low recall from tokenization/analyzers** that cannot be fixed cleanly within PostgreSQL constraints.
2. **High shares of unaccented, typo-ridden, or synonym-heavy queries** with strict UX demands.
3. **Sub-second typo-tolerant autocomplete** with custom ranking under tight latency budgets.
4. **Rich faceted navigation** combining many dynamic buckets and filters at scale.
5. **Rapidly iterating relevance tuning** requiring rich scoring signals and test tooling.
6. **Search load starving OLTP traffic**, requiring independent horizontal scaling and isolation.
7. **Distributed multi-node corpus scale** exceeding reasonable single-primary PostgreSQL limits.
8. **Specialized phonetic, fuzzy, or multilingual analyzers**.
9. **Hybrid lexical + semantic ranking pipelines** needing purpose-built tooling.
10. Failing SLO latency or error budgets even after tuning PostgreSQL properly.

Options depending on context include Elasticsearch, OpenSearch, Solr, Typesense, Meilisearch, and managed search services. **Never assume every engine offers identical features.** Verify version capabilities, data limits, licensing, operational footprint, and team readiness.

### 29.1. A Dedicated Search Engine Does Not Guarantee Good Relevance

Poor analyzer configuration, weak qrels, bad field mappings, or sloppy ranking weights still produce poor results on any specialized search engine.

Swapping infrastructure without a quality evaluation loop changes **where** bad search runs, not **how good** it is.

## 30. Decision Matrix: PostgreSQL vs. Dedicated Search Engine

| Criterion | PostgreSQL FTS / SQL | Dedicated Search Engine |
|---|---|---|
| Exact lookup by ID | Natural with B-tree / `UNIQUE` | Possible, usually unnecessary |
| Basic lexical FTS | Built-in `tsvector` / `tsquery` | Specialized analyzers and scorers per product |
| Complex relational joins | Core strength | Usually requires denormalization or extra lookups |
| Transactional consistency | Shared database with source data | Requires sync pipeline with eventual lag |
| RLS / SQL permissions | Native PostgreSQL enforcement | Must re-implement ACL checks carefully |
| Complex typos / autocomplete | Possible with trigrams/custom logic | Many offer built-in specialized features |
| Synonyms / language analysis | Text search config, dictionaries, custom prep | Richer analyzer and tokenizer ecosystems |
| Heavy facets / aggregations | SQL `GROUP BY` + filters; benchmark carefully | Optimized for search aggregations |
| Multi-signal ranking | Custom SQL expressions and tuning | Purpose-built scoring/rescoring frameworks |
| Semantic / hybrid search | Possible via extensions (`pgvector`) or external | Built-in support varies by engine |
| Independent search scaling | Shares primary or read replicas | Independent cluster scaling |
| Operations | Single DB system, plus index/tuning work | Extra cluster, sync, monitoring, and recovery |
| Authoritative data | Can act as source of truth and search | Should operate strictly as derived index |
| Freshness | Visible immediately upon transaction commit | Bounded by sync pipeline and refresh interval |
| Total cost | Lower for moderate requirements | Higher infra, engineering, and service costs |

Treat this matrix as a **decision framework**, not an absolute scorecard or product benchmark.

## 31. Decision Gates: Defining Clear Bars Instead of Endless Tuning

Teams can specify concrete release gates:

| Gate Category | Example Target (Illustrative) |
|---|---|
| Relevance | NDCG@10 matches or exceeds baseline across every key segment |
| Navigational | Policy lookup MRR meets product threshold |
| Typo / Unaccented | Success@5 clears bar on unaccented query suite |
| Security | Zero unauthorized hits in restricted access tests |
| Freshness | p99 index lag stays within update SLO |
| Latency | p95/p99 search latency under product budget |
| Reliability | Error/timeout rates below threshold |
| Cost | Total infra + operations cost stays within budget |
| Operations | Tested rollback, replay, and reindex runbooks exist |

**No universal SLO numbers apply everywhere.** Fill targets from real business risk, traffic, and cost. Running one fast query on an empty lab DB never clears a production decision gate.

## 32. Separated Search Architecture: PostgreSQL as Source of Truth

When adopting an external search engine, the standard topology is:

```text
Application writes data
        |
        v
PostgreSQL (source of truth)
        |
        +---- transaction commit
        |
        +---- outbox / CDC / sync job
                      |
                      v
              Search indexing pipeline
                      |
                      v
              Dedicated search index
                      |
                      v
                 Search API
                      |
                      +---- query/filter/rank top-k
                      |
                      v
                Results for user
```

Keep the **source of truth** unambiguous. Search documents are **derived query views**, never the authoritative legal or transactional record.

### 32.1. Why Naive Dual-Write Fails

Avoid:

```text
1. UPDATE PostgreSQL succeeds
2. Send API call to update search engine
3. If step 2 fails, then ...
```

If PostgreSQL commits and step 2 fails, the search index turns stale. If the search index updates first and the DB rolls back, deleted or uncommitted records appear in search.

This is the classic **non-atomic dual-write problem**. Naive client retries without durable logs silently drop updates.

### 32.2. Transactional Outbox Pattern

Pattern outline:

```sql
BEGIN;

UPDATE documents
SET title = ..., body = ...
WHERE document_id = ...;

INSERT INTO search_outbox(
    entity_type, entity_id, event_type, payload
)
VALUES ('document', ..., 'UPSERT', ...);

COMMIT;
```

This is a structural template, not runnable lab SQL since the outbox table and `...` placeholders are illustrative.

Key mechanics:

- Source rows and outbox events commit **atomically inside the same PostgreSQL transaction**.
- Workers consume the outbox and update the search index.
- Failures leave events intact for retry.
- Consumers must be idempotent because at-least-once delivery repeats events.
- Acknowledge processed events only safely so crashes never drop updates.

## 33. CDC: Streaming Changes Instead of Patching Every Writer

**Change Data Capture (CDC)** reads PostgreSQL changes directly from the write-ahead log.

Architecture:

```text
PostgreSQL WAL / logical decoding
         |
         v
      CDC stream
         |
         v
 Transformation + enrichment
         |
         v
      Search index
```

Potential strengths:

- Captures writes across services without requiring every writer to emit search calls.
- Reusable stream serving multiple downstream consumers.
- Durable log offsets supporting replay and recovery.

Engineering complexities to handle:

- Initial consistent snapshot plus seamless transition to live streaming.
- Schema evolutions.
- Transaction boundaries and event ordering.
- Deletes and tombstones.
- Retries and deduplication.
- Lag and backpressure.
- Replication privileges and data security.
- Selecting and joining related data needed by the index.

CDC **does not improve relevance**; it solves reliable state synchronization.

## 34. Data Integrity: Out-of-Order Events, Updates, and Deletes

A pipeline may encounter out-of-order delivery:

```text
Event A: document 101 -> version 5
Event B: document 101 -> version 6
```

Processing B before A can **overwrite version 6 backward** to version 5 without version guards.

### 34.1. Track Versions/Revisions to Reject Stale Events

Track metadata such as:

```text
document_id
source_version
last_modified_at
is_deleted
payload
```

During indexing, the consumer uses the engine's concurrency/versioning controls so older events never overwrite newer versions.

Never trust application wall-clock timestamps alone to determine order across distributed workers due to clock skew. Use monotonic database sequences or explicit row versions.

### 34.2. Deletes Are Critical Events

When a row is deleted, unpublished, moved to another tenant, or loses permissions, the search index must reflect that immediately.

Broken state:

```text
DELETE in PostgreSQL
    yet search index retains stale copy
    -> search results leak deleted content
```

Every sync pipeline needs:

- Tombstone or explicit delete events.
- Actual removal from the search index.
- Periodic reconciliation to sweep ghost documents.
- Retries for failed deletes.
- Retention/deletion compliance matching legal and privacy rules.

### 34.3. Rebuilds Colliding with Live Updates

Rebuilding an index from a point-in-time snapshot while live writes continue risks letting stale snapshot records overwrite newer updates unless cutover and checkpoints are coordinated via version numbers.

Coordinate snapshots, change streams, and monotonic version checks.

## 35. Freshness and Consistency: How Much Lag Is Acceptable?

With PostgreSQL as source of truth:

```text
T=0s:  DB commits updated title
T=1s:  search index has not yet processed event
T=3s:  search index applies update
```

During `T = 0..3s`, search queries can still show old titles or miss new entries.

### 35.1. Varying Freshness Requirements

| Scenario | Freshness Requirement |
|---|---|
| Searching articles published days ago | Short lag per SLO is fine |
| Updating product catalog titles | Depends on UX expectations and ops workflows |
| Revoking access to confidential documents | Must hide immediately per security policy |
| Deleting legal or private content | Needs prompt deletion and verification |
| Immediately looking up a newly created order | Often requires read-your-writes or direct DB lookup |

### 35.2. Read-Your-Writes

When a user places an order and immediately searches its ID, an eventually consistent index may miss it.

Patterns to handle this:

- Serve exact-ID lookups straight from PostgreSQL.
- Redirect users to the newly created resource API response without forcing a search round-trip.
- Prioritize urgent sync paths or leverage engine read-your-writes mechanisms where available.
- Show an explicit “indexing in progress” indicator when acceptable.

Never promise “instantaneous searchability for every edit” on top of an asynchronous pipeline.

## 36. ACLs, RLS, and Permissions in External Search Indexes

PostgreSQL RLS protects rows based on database roles and policies. Replicating documents into an external search engine **does not carry PostgreSQL RLS over automatically**.

Every external search request must enforce:

1. Authenticated caller identity.
2. Correct tenant scope.
3. Document-level ACL groups and permissions.
4. Publication status, soft deletes, and expiration dates.
5. Zero leakage of sensitive metadata in facets, counts, snippets, or suggestions.
6. Prompt enforcement of permission revocations despite sync lag or caches.

### 36.1. Application Post-Filtering After Search Is Risky

If an external search engine returns the top 10 hits across the entire corpus and the app drops unauthorized items afterward:

- Pages shrink to a handful of hits—or empty—even when authorized hits sit further down.
- Corpus statistics and rankings leak influence from restricted documents.
- Counts, facets, and autocomplete still expose restricted entries beforehand.
- A bug in application post-filtering leaks sensitive rows directly.

Push tenant and ACL predicates **into retrieval filters**, and where sensitive data demands extra defense, re-verify permissions against PostgreSQL during hydration.

### 36.2. Counts Are Sensitive Information

Even without returning titles or bodies, displaying “147 matches” for a keyword inside an unauthorized tenant proves those confidential items exist.

Enforce permissions uniformly across counts, aggregations, autocomplete, and analytics.

### 36.3. Permissions Change Faster Than Content

An ACL revocation is urgent security state—treat it on a high-priority path with tight SLOs rather than queuing it behind bulk content reindexing jobs.

## 37. Reindexing and Blue-Green Cutover

Changing analyzers, synonyms, or mapped fields in a search engine frequently requires rebuilding the index.

A safe workflow:

```text
index_v1 (live traffic)
      |
      +-- snapshot source of truth
      |
      v
build index_v2
      |
      +-- replay changes from checkpoint
      +-- reconcile counts / IDs / ACLs
      +-- run offline quality & latency checks
      |
      v
canary traffic to index_v2
      |
      v
switch routing/alias to index_v2
      |
      +-- monitor during rollback window
      |
      v
retire index_v1 once safe
```

### 37.1. Pre-Cutover Verification

Verify:

- Missing or extra document counts.
- Schema mappings and analyzer versions.
- Query compatibility under the new schema.
- Tenant, ACL, and visibility fidelity.
- Proper processing of deletes/tombstones.
- Zero residual freshness lag.
- Segment-level NDCG@k/MRR vs. baseline.
- p95/p99 latency and error rates.
- Verified fast rollback procedure.

Never rely on matching total document counts alone: two indexes can share identical counts while differing in IDs or permissions.

## 38. Hybrid Retrieval: Lexical, Trigram, and Semantic

Some workloads benefit from combining candidate streams:

```text
                  Query
                    |
          +---------+----------+
          |         |          |
       Lexical    Trigram    Semantic
         FTS       fuzzy      vectors
          |         |          |
          +---------+----------+
                    |
               Deduplicate
                    |
              Merge / rerank
                    |
               ACL filtering
                    |
                  Top-k
```

Logical diagram; in production, **enforce ACL filtering inside retrieval itself** wherever possible rather than waiting blindly until the final step.

### 38.1. What Is Semantic Search?

Semantic retrieval uses meaning representations (typically embedding vectors) to find related content even without exact shared words.

For example, matching:

```text
"không nhận được mã xác minh"
```

to a document titled:

```text
"khắc phục lỗi OTP không gửi về điện thoại"
```

Keep in mind that embeddings do not guarantee factual accuracy, exact ID matching, legal precision, or access control.

### 38.2. Vector Search Inside PostgreSQL Can Delay Splitting Systems

PostgreSQL supports vector similarity extensions (such as `pgvector` where permitted), so moderate semantic search needs **do not automatically force** adding a dedicated search engine.

Still evaluate extension capabilities, index behavior, filtered vector performance, recall/latency trade-offs, and operations against real scale.

### 38.3. Merging Rankings with RRF

**Reciprocal Rank Fusion (RRF)** combines heterogeneous ranked lists purely from rank positions:

\[
RRF(d) = \sum_{r \in \text{retrievers}}
\frac{1}{c + rank_r(d)}
\]

where `c` is a smoothing constant dampening the weight of very high ranks.

Advantage: lexical scores and vector distances do not need compatible numeric scales.

Limitations:

- Still requires strong candidates from each underlying retriever.
- Cannot invent relevance if every retriever missed the target document.
- Access control must still be enforced strictly.
- Still demands qrels, NDCG/MRR evaluation, and latency benchmarks.
- No single constant `c` is optimal across every system.

## 39. Personalized Ranking Adds Risks and Evaluation Needs

When incorporating user history or personalization:

- A great result for one user may fail another.
- Static context-free qrels alone no longer suffice.
- Feedback loops amplify popular hits disproportionately.
- Filter bubbles narrow discovery of newer content.
- User privacy rules must govern behavioral tracking.

Balanced strategies combine:

- Baseline lexical relevance.
- Hard business and security filters.
- Permitted user preferences.
- Recency and quality signals.
- Result diversification.
- Segmented testing across user cohorts.

Never let personalization promote an unauthorized item into candidates regardless of affinity score.

## 40. Production Observability: Essential Dashboard Metrics

A solid search dashboard tracks four pillars:

### 40.1. Quality

- NDCG@5 and NDCG@10 on curated qrels.
- MRR / Success@k on navigational queries.
- Precision@k, Recall@k, or retrieval recall on qrels.
- Zero-result rate.
- Query reformulation and abandonment rates.
- Qrels coverage and unjudged@k ratios.
- Breakdowns by language, tenant, and query type.

### 40.2. Performance

- Query rate (QPS).
- End-to-end p50/p95/p99 latency.
- Search backend query latency.
- Timeouts and error counts.
- CPU, RAM, and disk I/O utilization.
- Connection pool and thread queue waits.
- Top slow query patterns and resource consumers.

### 40.3. Freshness and Reliability

- Outbox / CDC / consumer sync lag.
- Pending event backlog depth.
- Retry and replay rates.
- Missing or orphaned index document counts.
- Pending deletes / unpublishes.
- Index rebuild duration.
- Search backend health, disk capacity, and quotas.

### 40.4. Security

- Continuous tests for tenant, ACL, and visibility isolation.
- Share of candidates rejected due to permissions.
- Audits checking whether counts or autocomplete leak restricted terms.
- Audit trail for permission changes and deletion propagation.
- Log sanitization ensuring zero raw PII/secret leaks in queries, snippets, or metrics.

### 40.5. Do Not Turn Dashboards Into Vanity Mirrors

If average NDCG improves while p99 latency doubles, small tenants suffer permission glitches, or unaccented recall drops sharply, **do not treat it as a shippable win**.

## 41. Structured Process for Deciding to Migrate Search

Follow a staged roadmap:

### Phase A — Define Goals

- Publish search SLOs.
- Document hard security and correctness constraints.
- Define evaluation segments.
- Curate query sets and qrels.
- Measure current baseline quality, latency, and cost.

### Phase B — Optimize PostgreSQL Thoroughly

- Audit query parsing and text search configs.
- Build and maintain appropriate GIN indexes.
- Tune title/body weights.
- Route exact IDs through B-trees.
- Evaluate `pg_trgm` for typos and substrings.
- Address Vietnamese normalization needs cleanly.
- Inspect `EXPLAIN` plans and trim wasted work.
- Measure impact on OLTP workloads.

### Phase C — Prototype a Dedicated Search Engine

- Index the exact same corpus snapshot.
- Implement versioned analyzers and synonyms.
- Mirror tenant and ACL boundaries faithfully.
- Run the exact same offline quality metrics.
- Benchmark latency under matching realistic traffic.
- Estimate engineering effort for sync and ongoing ops.

### Phase D — End-to-End Validation

- Build outbox/CDC sync with replay.
- Verify update and delete propagation.
- Test sync lag and read-your-writes paths.
- Practice full rebuilds and rollbacks.
- Audit ACLs across facets, counts, and suggestions.
- Compare full Total Cost of Ownership (TCO).

### Phase E — Canary, A/B Test, and Decision

- Shift a controlled slice of traffic to the new path.
- Monitor system health and query-level regressions.
- Roll back immediately if security, latency, or quality regresses.
- Ramp traffic gradually on solid evidence.
- Retain the old path until migration and rollback verification complete.

## 42. Common Anti-Patterns

### 42.1. “The FTS Query Runs in 30 ms, So Search Is Good”

Latency is just one dimension; it says nothing about relevance or coverage.

### 42.2. “FTS Doesn't Handle Typos Out of the Box, So We Must Switch Immediately”

Evaluate normalization, `pg_trgm`, or query expansion first. Adopt new infrastructure only when workload evidence justifies total cost.

### 42.3. “A Dedicated Search Engine Is Always Faster Than PostgreSQL”

False universal rule. Workload, indexes, network hops, analyzers, sorting, and scale decide; primary-key lookups in PostgreSQL are often simpler, faster, and strictly consistent.

### 42.4. “More Synonyms Are Always Better”

Overly broad synonym expansion hurts precision—for example matching unrelated uses of “phin”. Measure impact per query segment.

### 42.5. “Higher CTR Means Better Relevance”

CTR suffers position bias, presentation bias, and varies by intent. Protect experiments with task-success metrics and guardrails.

### 42.6. “Precision@10 Tells Us Everything”

P@10 ignores total recall, first-hit position, graded relevance, latency, fairness, and security.

### 42.7. “Zero Results Is Always a Bug”

No-answer responses are right when matching items do not exist or the caller lacks permission.

### 42.8. “Unjudged Documents Equal Irrelevant”

Penalizing unjudged hits biases evaluations against newer retrievers. Expand qrels iteratively.

### 42.9. “Treat the Search Index as the Source of Truth”

Derived indexes lag asynchronously and undergo full rebuilds. Primary entities, constraints, and transactions belong in PostgreSQL.

### 42.10. “Dual-Writing DB and Search API Is Safe Enough”

Two independent writes outside one atomic transaction drift on worker/network errors. Use an outbox, CDC, or durable replication.

### 42.11. “The Search Index Automatically Inherits PostgreSQL RLS”

False. Re-implement tenant/ACL rules explicitly and test counts, snippets, and suggestions too.

### 42.12. “Client-Side Filtering Fixes All Permission Bugs”

Exposes intermediate unauthorized data and breaks top-k completeness. Enforce permissions during retrieval.

### 42.13. “Reindexing Is Complete Once Document Counts Match”

Counts can match while IDs, revisions, analyzers, or deleted docs remain wrong.

### 42.14. “One Sample Query Proves Our Vietnamese Analyzer Works”

Evaluate across accented, unaccented, typo, compound, proper-noun, short, and long query sets.

### 42.15. “Adding GIN Makes `ORDER BY ts_rank` Pre-Sorted”

GIN finds matching candidates; dynamic `ts_rank` still requires computing and sorting scores at query time.

### 42.16. “Vector Search Understands Everything Semantically”

Embeddings still exhibit false positives and false negatives. Exact IDs and permissions require deterministic guards, and quality still needs labeled evaluation.

### 42.17. “Our p50 Latency Looks Good, So We're Done”

p95/p99 tail spikes and timeouts drive most user frustration.

### 42.18. “Higher Scores on Development Qrels Mean Every Query Improved”

Risk of overfitting—validate on holdout sets, segments, and live traffic.

## 43. Practice Exercises with Guided Solutions

### Exercise 1. Picking Metrics for Exact Order-ID Lookup

**Prompt:** Users enter `ORD-123` expecting one exact order.

**Answer:** prioritize exact correctness, Success@1/MRR, zero cross-tenant leakage, and predictable low latency. Exact B-tree equality fits better than fuzzy ranking.

### Exercise 2. Picking Metrics for How-To Guides

**Prompt:** One query has multiple useful guides with varying levels of helpfulness.

**Answer:** NDCG@5/@10 works well with graded qrels, complemented by Recall@k and Success@k.

### Exercise 3. What Is P@5 with Three Relevant Results?

**Answer:** `3/5 = 0.6`, under the defined relevance threshold.

### Exercise 4. What Is R@5 When 8 Corpus Docs Are Relevant and Top-5 Captures 3?

**Answer:** `3/8 = 0.375`, assuming all 8 relevant documents were verified.

### Exercise 5. What Is RR When the First Relevant Document Is at Rank 4?

**Answer:** `1/4 = 0.25`.

### Exercise 6. What Is Success@3 When the First Relevant Document Is at Rank 4?

**Answer:** `0`.

### Exercise 7. Can MRR Evaluate All 20 Relevant Results?

**Answer:** MRR primarily tracks the position of the **first** relevant hit. When multiple relevant documents matter, pair it with MAP, NDCG, or Recall.

### Exercise 8. Why Can NDCG@10 Outperform P@10?

**Answer:** NDCG captures both **graded relevance levels and rank positions**, whereas P@10 treats relevance as binary across top-10.

### Exercise 9. Can You Trust NDCG If Top-10 Consists Mostly of Unjudged Documents?

**Answer:** no—never default unjudged items to 0 and declare victory. Expand judged coverage and report judgment uncertainty.

### Exercise 10. Why Not Rely Solely on Clicks as Ground Truth?

**Answer:** clicks suffer from position bias, snippet bias, feedback loops, and ambiguous user intent.

### Exercise 11. Search Tenant 7 Documents with FTS

```sql
WITH q AS (
    SELECT websearch_to_tsquery('simple', 'máy xay') AS tsq
)
SELECT d.document_id, d.title
FROM search330.documents d CROSS JOIN q
WHERE d.tenant_id=7
  AND d.is_published
  AND d.search_vector @@ q.tsq;
```

**Answer:** keep both tenant and visibility predicates so documents 113 and 114 never appear.

### Exercise 12. Why Isn't `ts_rank_cd` the Same Thing as NDCG?

**Answer:** `ts_rank_cd` computes a query-time ranking score to order hits; NDCG evaluates ranking quality offline against human qrels.

### Exercise 13. Distinguish Candidate Retrieval from Ranking

**Answer:** retrieval determines which documents enter the candidate pool; ranking orders them. If a relevant document fails retrieval, changing ranking cannot surface it.

### Exercise 14. Why Does “ca phe” Fail to Match “cà phê” in the Lab?

**Answer:** accented and unaccented tokens differ; `simple` does not fold Vietnamese diacritics automatically. Evaluate explicit normalization or analyzers.

### Exercise 15. Can `unaccent` Be Used Directly in a Generated Column?

**Answer:** not by default; consider volatility/immutability restrictions, mutable dictionary rules, and index rebuild workflows when rules change.

### Exercise 16. What Does `pg_trgm` Improve?

**Answer:** substring matching and surface character similarity—it does not understand synonyms or semantics.

### Exercise 17. Does GIN Pre-Sort Results by `ts_rank_cd`?

**Answer:** no. GIN locates matching candidates; dynamic rank depends on each query and requires scoring and sorting.

### Exercise 18. Does a Zero-Result Rate of 0 Prove Search Works Well?

**Answer:** no. A system returning junk hits on every query hits ZRR = 0 while destroying precision and no-answer correctness.

### Exercise 19. Which Segments Should You Track When Testing Long Queries?

**Answer:** slice by intent, token count, language, accented vs. unaccented, head vs. tail frequency, and answerable vs. no-answer queries.

### Exercise 20. Why Must Comparative Benchmarks Share the Same Corpus Snapshot?

**Answer:** to avoid mistaking freshness lag, recent edits, deletes, or ACL drift for ranking differences.

### Exercise 21. When Should You Stay on PostgreSQL?

**Answer:** when FTS meets relevance, latency, and cost SLOs, transactions/ACLs map cleanly to PostgreSQL, and workload does not require features exclusive to an external engine.

### Exercise 22. When Should You Consider Dedicated Search?

**Answer:** when analyzer complexity, typo/autocomplete UX, large-scale facets, rich relevance tuning, or independent OLTP load isolation exceed practical PostgreSQL boundaries based on measurements.

### Exercise 23. Why Isn't a Dedicated Search Engine Automatically Better?

**Answer:** misconfigured analyzers, mappings, permissions, or ranking weights still produce poor search; verify with benchmarks and qrels.

### Exercise 24. What Is the Weakness of Naive Dual-Write?

**Answer:** committing to PostgreSQL and calling a search API separately is non-atomic; partial failures leave the two stores out of sync.

### Exercise 25. How Does the Transactional Outbox Help?

**Answer:** it commits sync events inside the same PostgreSQL transaction as business writes, enabling durable retry and replay.

### Exercise 26. Does CDC Improve Search Ranking on Its Own?

**Answer:** no. CDC synchronizes data reliably; ranking only improves when retrieval/scoring improves.

### Exercise 27. Why Do Consumers Need Monotonic Versions?

**Answer:** out-of-order deliveries can overwrite newer index entries with stale updates unless guarded by source revisions.

### Exercise 28. What Happens When a Document Is Deleted in PostgreSQL but Remains Indexed?

**Answer:** users can retrieve stale or unauthorized deleted records; prevent this with tombstones, delete retries, and reconciliation jobs.

### Exercise 29. Does PostgreSQL RLS Follow Documents into External Search Engines?

**Answer:** no; re-implement and test tenant and ACL enforcement directly inside the search index and API.

### Exercise 30. Why Does Post-Filtering Top-10 Permissions Hurt Recall?

**Answer:** unauthorized hits crowd out top slots and get dropped, while valid items ranked 11th and lower were never retrieved.

### Exercise 31. If MRR Improves While p99 Latency Spikes Sharply, Should You Roll Out?

**Answer:** not automatically. Weigh quality gains against SLOs, tail latency impact, query frequency, and guardrail limits first.

### Exercise 32. When Is a Full Search Reindex Needed?

**Answer:** when changing analyzers, mappings, or schema tokenization rules affecting indexed fields; verify exact impact per engine instead of assuming every edit needs a full rebuild.

### Exercise 33. Define Hard Filters vs. Soft Ranking

**Answer:** hard filters enforce authorization, tenant scope, publication status, and mandatory business rules; soft ranking orders only the valid candidate set by relevance and auxiliary signals.

### Exercise 34. Why Should True No-Answer Queries Return Empty Results?

**Answer:** padding results with wrong or unauthorized records just to lower ZRR erodes correctness and user trust.

### Exercise 35. Why Keep a Holdout Query Set?

**Answer:** to prevent overfitting weights and rules onto development queries and verify real generalization.

### Exercise 36. What If Offline Metrics Improve While Online Task Success Drops?

**Answer:** investigate segments, instrumentation bugs, presentation bias, and corpus drift; enforce guardrails and canary/rollback rather than treating offline scores as infallible.

## 44. Search Design and Evaluation Checklist

| Question | What to Verify |
|---|---|
| What task is search solving? | Navigational, informational, exact, or exploratory |
| Are qrels judged deeply enough? | Never conflate unjudged with non-relevant |
| Are grades and thresholds defined? | Comparable metrics across runs |
| Is a holdout query set maintained? | Guard against overfitting |
| Are unaccented, typo, and English queries tested? | Reflects real user input |
| Are no-answer queries included? | Measures no-answer correctness |
| Do metrics match the task? | Precision, Recall, Success, MRR, NDCG per goal |
| Are query-level regressions checked? | Averages do not hide localized failures |
| Do query parser and `tsvector` share configs? | Avoid dropped candidates |
| Are title/body weights balanced? | Prevent ranking skew |
| Is exact ID lookup handled directly? | Preserve deterministic accuracy |
| Are tenant, ACL, and visibility rules enforced? | Zero unauthorized leaks |
| Does PostgreSQL search impact OLTP? | Isolate load and cost |
| Are p50/p95/p99 and throughput measured? | Never monitor averages alone |
| Are index update and write costs tracked? | WAL, GIN maintenance, and memory |
| Does external search have a clear source of truth? | Avoid split-brain state |
| Are outbox/CDC and replay implemented? | Zero lost sync events |
| Are out-of-order versions handled? | Prevent stale overwrites |
| Do deletes and unpublishes propagate promptly? | Prevent ghost documents |
| Is freshness lag monitored? | Meets update SLO |
| Are index IDs and ACLs reconciled? | Never trust raw counts alone |
| Are reindex, cutover, and rollback tested? | Rapid recovery on error |
| Is total infra + ops TCO evaluated? | Avoid unnecessary complexity |
| Are canary/A-B tests guarded by guardrails? | Validate real user impact |
| Are logging, privacy, and retention compliant? | Protect user and tenant data |

## 45. References and Further Reading

Official PostgreSQL documentation (check for your exact installed version):

- [Text Search Introduction](https://www.postgresql.org/docs/current/textsearch-intro.html): Full Text Search concepts.
- [Text Search Controls](https://www.postgresql.org/docs/current/textsearch-controls.html): `tsquery`, `websearch_to_tsquery`, ranking, and highlighting.
- [Text Search Dictionaries](https://www.postgresql.org/docs/current/textsearch-dictionaries.html): configuring lexeme processing.
- [Text Search Indexes](https://www.postgresql.org/docs/current/textsearch-indexes.html): GIN and GiST for FTS.
- [Text Search Configuration](https://www.postgresql.org/docs/current/textsearch-configuration.html): parser and dictionary bindings.
- [pg_trgm](https://www.postgresql.org/docs/current/pgtrgm.html): trigram similarity and index support.
- [unaccent](https://www.postgresql.org/docs/current/unaccent.html): accent-filtering dictionary and its constraints.
- [Generated Columns](https://www.postgresql.org/docs/current/ddl-generated-columns.html): expression rules for generated columns.
- [GIN Indexes](https://www.postgresql.org/docs/current/gin.html): GIN internals and trade-offs.
- [Using EXPLAIN](https://www.postgresql.org/docs/current/using-explain.html): interpreting query plans and actual runtime stats.
- [Row Security Policies](https://www.postgresql.org/docs/current/ddl-rowsecurity.html): row-level security policies.
- [Logical Decoding](https://www.postgresql.org/docs/current/logicaldecoding.html): foundation for CDC.

Information Retrieval Evaluation Concepts:

- **Precision, Recall, AP/MAP, Reciprocal Rank/MRR, DCG/NDCG**: standard IR metrics; pay close attention to exact formulas, cutoffs, and unjudged-document conventions.
- **Offline relevance judgments, pooling, inter-annotator agreement, click/position bias**: foundational practices for reliable benchmarks.
- **Online experimentation / A/B testing**: monitor primary outcomes alongside latency, reliability, privacy, and security guardrails.

Never assume all search engines offer identical behavior from this lesson alone. Verify exact versions, configurations, licensing, and run benchmarks on representative data.

## 46. Summary: Measure Quality Before Splitting Search Out of PostgreSQL

### 46.1. PostgreSQL Can Still Be a Strong Search Engine

Combining `tsvector`, `tsquery`, `@@`, `ts_rank`/`ts_rank_cd`, GIN, `pg_trgm`, B-trees, and relational SQL filters lets PostgreSQL handle many search workloads cleanly without external infrastructure.

Yet built-in capabilities do not automatically produce great search UX—always measure against real queries.

### 46.2. Three Essential Evaluation Pillars

```text
                       SEARCH QUALITY
                              |
        +---------------------+----------------------+
        |                     |                      |
  Relevance/coverage    Latency/cost           Correctness/safety
        |                     |                      |
  P@k, R@k, MRR,        p50,p95,p99,            Tenant, ACL,
  MAP, NDCG, ZRR        throughput, CPU         delete, freshness
```

A system passing only two of these three pillars is still incomplete.

### 46.3. The System Boundary Is Never a Single Row Count

Avoid simplistic rules such as:

```text
1 million documents -> must use Elasticsearch
```

or:

```text
PostgreSQL has GIN -> never need a search engine
```

Instead:

1. Define search intent and SLOs.
2. Curate a query set and qrels.
3. Measure ranking quality across every segment.
4. Measure candidate recall, zero-result rates, typos, and unaccented coverage.
5. Measure p95/p99 latency, resource cost, and OLTP contention.
6. Optimize PostgreSQL carefully first.
7. Prototype a dedicated engine over the exact same snapshot if clear gaps remain.
8. Validate sync, ACLs, deletes, freshness, and recovery.
9. Roll out only when measured benefits clearly outweigh cost and operational complexity.

### 46.4. A Dedicated Search Engine Is a Derived Data Store

When separating search:

```text
PostgreSQL (source of truth)
       |
   Outbox / CDC
       |
   Search index
       |
  Search API
```

Treat:

- Out-of-order updates,
- Retries and idempotency,
- Deletes and tombstones,
- ACL and tenant boundaries,
- Rebuilds and cutovers,
- Freshness lag,
- Read-your-writes, and
- Monitoring and rollback

as **mandatory architectural components**, never afterthoughts.

**One takeaway to remember:** PostgreSQL Full Text Search handles many real-world workloads effectively; **evaluate relevance, coverage, ranking quality, tail latency, and access safety on real traffic** before committing to a dedicated search engine—and if you do separate search, govern that external index strictly as a derived replica that can lag, drift, and require rebuilding.
