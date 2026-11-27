# Combining Keyword Search, Vector Search, and Reranking

A strong search engine should not merely return documents **containing the exact keywords from a question**; it must also find documents that are **semantically related** despite different wording, preserve **exact product codes, API names, and clauses**, and surface the most helpful results at the top. In MongoDB, this approach is commonly called **hybrid search**: combining **keyword search (lexical/full-text search)**, **vector search (semantic/vector search)**, and, when warranted, **reranking** over a small candidate pool.

For example, a user searches: **“how to fix error E11000 when adding an account”**. Keyword search excels on the exact string `E11000`, whereas a document titled **“Handling unique index collisions”** may not contain the exact phrasing of the question. Embedding search can locate documents with matching meaning, while a **reranker** can prioritize the passage describing exact remediation steps over a glossary page that merely mentions the error code.

Why not rely on a single search method?

- **Keyword only:** easily misses synonyms, alternative phrasing, and cross-lingual queries; yet excels at error codes, proper names, SKUs, and exact terminology.
- **Vector only:** captures general intent well, yet can confuse version numbers, short symbols, negation, or exact constraints; also incurs embedding/index/ANN overhead.
- **Combining both lists:** raises the chance that the **right candidate** appears, though the top-5 ordering may still be suboptimal.
- **Reranking:** inspects the relationship between the question and candidate texts more deeply to **reorder** them; however, it cannot rescue a document that never entered the candidate list.

This lesson belongs to the **Vector Search** chapter of the *Database Engine Document MongoDB* module. Examples use MongoDB Search (`$search`), MongoDB Vector Search (`$vectorSearch`), `$rankFusion`, `$scoreFusion`, and a reranking layer either in the application or via MongoDB `$rerank` when supported by the environment. This lesson covers **search pipeline design, syntax, compatibility requirements, relevance evaluation, and operations**, not merely calling a single API.

## Learning Objectives

After this lesson, you will be able to:

1. Distinguish lexical retrieval, vector retrieval, rank/score fusion, and semantic reranking.
2. Explain the strengths and weaknesses of BM25/Atlas Search versus embedding similarity on queries with codes, proper names, Vietnamese, synonyms, or long sentences.
3. Design a MongoDB schema for searchable documents with `title`, `body`, `embedding`, `tenantId`, `visibility`, and `version`.
4. Create MongoDB Search and Vector Search indexes with appropriate vector dimensions/similarity and indexed filter fields.
5. Write `$search`, `$vectorSearch`, and hybrid `$rankFusion` pipelines while respecting practical constraints.
6. Use or distinguish `$scoreFusion`, application-side RRF, and know when raw scores must be normalized.
7. Design a **rerank step** (cross-encoder/relevance model) after fusion, accounting for cost, latency, and input length.
8. Enforce **authorization, tenant isolation, document status, and freshness** across both lexical and vector branches.
9. Evaluate Recall@K, Precision@K, MRR, nDCG, query subsets, and latency/cost—avoiding tuning based solely on technical scores.
10. Handle failure modes such as unready indexes, mismatched embedding dimensions, empty branches, duplicate chunks, unstable rankings, and fallbacks.

> **Runtime prerequisites:** MongoDB Search and MongoDB Vector Search must be supported on the deployment (for example, Atlas or a local/self-managed deployment with compatible search services). `$vectorSearch` ANN on Atlas has server gates such as **6.0.11/7.0.2+**, with ENN on applicable patch releases; hybrid `$rankFusion` requires **MongoDB 8.0+**, and `$scoreFusion` requires **8.3+**. `$rerank` is a separate **Native Reranking** feature requiring current MongoDB version/feature-toggle/model availability; current `$rerank` documentation specifies **9.0+** alongside model/tier restrictions. Never assume any cluster supporting `aggregate()` runs all of these stages. Always cross-check docs for your exact server version, FCV, Atlas project/cluster tier, and region.

## 1. End-to-End Hybrid Retrieval Pipeline Map

~~~text
User query: "docs for fixing E11000"
                        |
                        v
             Normalize / identify intent
                        |
             +----------+----------+
             |                     |
             v                     v
     Keyword / BM25 search    Embedding model
      $search (top L)         Query vector
             |                     |
             |                     v
             |                $vectorSearch
             |                  (top V)
             |                     |
             +----------+----------+
                        |
                        v
               Merge + deduplicate
              RRF / score fusion
                        |
                        v
              Candidate list top M
                        |
                        v
           Optional semantic reranker
              (query + each text)
                        |
                        v
             Business / safety rules
             tenant, ACL, status, time
                        |
                        v
              Top K with snippets
                (e.g. top 5/10)
~~~

**Careful with this diagram:** ACL/tenant filtering **must be applied inside each retrieval branch**, not only at the end. The final step is only a **recheck/formatting** layer; if you filter only after picking top M, authorized results may already have been pushed out of the candidate pool. Furthermore, never send documents the user is not authorized to view to a reranker or external model.

### 1.1. Stages Have Distinct Responsibilities

| Stage | Input | Output | Question answered |
|---|---|---|---|
| Lexical retrieval | Query text + inverted index | Top L docs by token/relevance | Are the exact terms, names, or codes present? |
| Vector retrieval | Embedding(query) + vector index | Top V neighbors | How close is the meaning to the question? |
| Fusion | Two or more ranked lists | Unified list and combined score | Which documents have strong signals across multiple sources? |
| Rerank | Query + top M document texts | Reordered ranking over those M docs | Which document best addresses the specific intent? |
| Final presentation | Top K + metadata | Title, snippet, link, provenance | Can the user consume and verify the results? |

Letters L, V, M, and K are **candidate budgets**, not mandatory constants. An experimental setup might pull 40 lexical + 40 vector → merge up to 80 unique docs → rerank 20–40 → return 10. Production values must be measured against quality and latency.

### 1.2. Three Questions to Ask Before Writing Code

1. **What data must be searched?** One document collection or multiple sources; whole documents or chunks; multi-tenant or public?
2. **Which queries matter most?** API names/error codes, natural language, Vietnamese/English, time/version filters, precision-critical questions?
3. **What guarantees are required?** Fast search, zero ACL leaks, trustworthy provenance, freshness and snippet formatting, model inference budget?

Good hybrid search is an **end-to-end retrieval system**, not merely adding an operator to a pipeline.

## 2. Keyword Search: Indispensable Lexical Signals

Keyword search typically uses **MongoDB Search**'s inverted index via the `$search` stage. It analyzes terms and can apply stemming/language analyzers, synonyms, fuzzy matching, phrases, wildcards, autocomplete, and configurable scoring.

### 2.1. When Lexical Outperforms Vector

- **Error codes:** `E11000`, `HTTP 429`, `ORA-00001`.
- **Exact names:** `MongoBulkWriteException`, `TransactionOptions`, `$setOnInsert`.
- **Identifiers:** SKUs, unit codes, model names, ticket IDs, clause numbers.
- **Negation / version strings:** `NOT NULL`, `TLS 1.3`, `v8.0.10`.
- **Exact quotes** or phrase queries.

An embedding model may place `MongoDB 8.0` and `MongoDB 8.3` close together, even though the version difference determines whether `$scoreFusion` runs. Lexical matching lets you weight exact version tokens heavily.

### 2.2. BM25 Scoring and Analyzers

MongoDB Search typically provides relevance scoring built on lexical signals such as BM25; scores reflect term frequency, corpus rarity, field length, and analyzer/boost configuration. **BM25 is not a probability** and does not share a fixed scale with cosine similarity.

Example:

~~~text
Query: "duplicate key E11000"

Doc A title: "Handling duplicate key error E11000"
Doc B title: "Explaining unique indexes"
Doc C title: "Index concepts in MongoDB"
~~~

Lexical search can push A to the top via exact token matches; vector search can surface B for related meaning. Both signals are useful.

### 2.3. `$search` Differs from `$text`

`$text` is MongoDB's traditional native text index with its own capabilities and limitations. MongoDB Search (`$search`) uses dedicated search indexes, query operators/analyzers, and scoring. Do not mix their syntax:

~~~javascript
// MongoDB Search:
{ $search: { index: "kb_text_v1", text: { query: "E11000", path: "body" } } }

// Regular text index $text query, not equivalent:
{ $match: { $text: { $search: "E11000" } } }
~~~

In this lesson, “keyword search” defaults to **MongoDB Search** for direct integration with `$rankFusion`/`$scoreFusion`. Another lexical engine can be used with application-side fusion if architecture requires it.

## 3. Vector Search: Semantic Signals from Embeddings

An embedding model transforms text into a multi-dimensional numeric vector. Semantically similar passages tend to have nearby vectors under the similarity metric chosen at index time.

For example, three sentences:

~~~text
Q: "fix duplicate data error when creating a user"
D1: "How to handle duplicate keys from unique indexes"
D2: "Indexing for date-range queries"
~~~

The embedding for Q can be close to D1 even with different vocabulary. However, this **does not guarantee** accurate discrimination of version numbers, method names, or negations.

### 3.1. Query Embeddings Must Match Document Embeddings

A collection may store:

~~~javascript
{
  _id: "KB-001",
  title: "Handling duplicate keys",
  body: "If an insert violates a unique index, the server returns E11000...",
  embedding: [0.12, 0.48, -0.23, 0.09]
}
~~~

Four numbers are **toy vectors for code illustration**, not outputs of an evaluated embedding model. Production typically uses hundreds or thousands of dimensions; the **query vector must match `numDimensions`** and be generated by the **same model version and preprocessing** as document vectors.

### 3.2. ANN and ENN

- **ANN (Approximate Nearest Neighbors):** uses approximate indexes/algorithms to reduce latency, potentially missing a few neighbors compared to exhaustive search.
- **ENN (Exact Nearest Neighbors):** finds exact neighbors over the evaluated scope, useful as ground truth for checking ANN recall or when the dataset/filtered subset is small.

In `$vectorSearch`, ANN typically uses `numCandidates` and `limit`; raising `numCandidates` can improve recall at higher CPU/latency cost. ENN uses `exact:true` and has its own version requirements.

### 3.3. Similarity Metrics and Scores

Vector indexes support metrics such as `cosine`, `dotProduct`, and `euclidean`. Never assume every vector score equals raw cosine similarity or a probability like “87% chance this document is right”. MongoDB may normalize metric scores in engine-specific ways. Use scores for **relative ranking within one branch**; when combining with lexical BM25, use RRF or proper score normalization.

### 3.4. Vector Search Does Not Understand Business Filters Automatically

A semantically close document may belong to another tenant, be retracted, be expired, or target the wrong product version. **Embeddings do not reliably encode access rights or policies.** Attach structured metadata and apply **filters before selecting nearest neighbors**.

## 4. Hands-On Dataset: Multi-Tenant Knowledge Base

Suppose the application searches collection `search315_lab.kb_docs`. Each document has `_id`, `title`, `body`, `tenantId`, `visibility`, `status`, `sourceUrl`, and `embedding`. Example:

~~~javascript
{
  _id: "DOC-001",
  tenantId: "tenant-a",
  visibility: "PUBLIC",
  status: "PUBLISHED",
  title: "Fixing duplicate key error E11000",
  body: "MongoDB returns E11000 when an insert violates a unique index...",
  language: "vi",
  sourceUrl: "/kb/duplicate-key",
  updatedAt: ISODate("2026-10-10T00:00:00Z"),
  embeddingModel: "demo-4d-v1",
  embedding: [0.86, 0.32, 0.01, 0.07]
}
~~~

### 4.1. Creating a Small Lab Fixture

~~~javascript
const lab = db.getSiblingDB("search315_lab")

lab.kb_docs.insertMany([
  {
    _id: "DOC-001", tenantId: "tenant-a",
    visibility: "PUBLIC", status: "PUBLISHED",
    title: "Fixing duplicate key error E11000",
    body: "MongoDB returns E11000 when inserting a duplicate key on a unique index. Validate data and idempotency.",
    language: "vi", sourceUrl: "/kb/duplicate-key",
    updatedAt: ISODate("2026-10-10T00:00:00Z"),
    embeddingModel: "demo-4d-v1",
    embedding: [0.86, 0.32, 0.01, 0.07]
  },
  {
    _id: "DOC-002", tenantId: "tenant-a",
    visibility: "PUBLIC", status: "PUBLISHED",
    title: "Unique indexes and duplicate data",
    body: "A unique index rejects two documents with duplicate values. Handling duplicate keys and null/missing values.",
    language: "vi", sourceUrl: "/kb/unique-index",
    updatedAt: ISODate("2026-10-08T00:00:00Z"),
    embeddingModel: "demo-4d-v1",
    embedding: [0.78, 0.40, 0.03, 0.01]
  },
  {
    _id: "DOC-003", tenantId: "tenant-a",
    visibility: "PUBLIC", status: "PUBLISHED",
    title: "Configuring the connection pool",
    body: "Tune maxPoolSize, timeouts, and monitor connection counts in the Java Driver.",
    language: "vi", sourceUrl: "/kb/pool",
    updatedAt: ISODate("2026-10-09T00:00:00Z"),
    embeddingModel: "demo-4d-v1",
    embedding: [0.02, 0.01, 0.95, 0.17]
  },
  {
    _id: "DOC-004", tenantId: "tenant-a",
    visibility: "PUBLIC", status: "PUBLISHED",
    title: "MongoDB backup and recovery",
    body: "Guide to backups, restores, snapshot verification, and rollback preparation.",
    language: "vi", sourceUrl: "/kb/backup",
    updatedAt: ISODate("2026-09-01T00:00:00Z"),
    embeddingModel: "demo-4d-v1",
    embedding: [0.05, 0.05, 0.25, 0.92]
  },
  {
    _id: "DOC-005", tenantId: "tenant-b",
    visibility: "PRIVATE", status: "PUBLISHED",
    title: "Tenant B internal key reconciliation",
    body: "Private operational details, must never be shown to other tenants.",
    language: "vi", sourceUrl: "/private/tenant-b/keys",
    updatedAt: ISODate("2026-11-01T00:00:00Z"),
    embeddingModel: "demo-4d-v1",
    embedding: [0.93, 0.26, 0.02, 0.03]
  },
  {
    _id: "DOC-006", tenantId: "tenant-a",
    visibility: "PUBLIC", status: "DRAFT",
    title: "Draft guide for E11000",
    body: "Unapproved draft document about duplicate keys.",
    language: "vi", sourceUrl: "/drafts/e11000",
    updatedAt: ISODate("2026-11-10T00:00:00Z"),
    embeddingModel: "demo-4d-v1",
    embedding: [0.91, 0.31, 0.00, 0.02]
  }
])
~~~

**Lab note:** Run the script once in a practice database; re-running hits duplicate `_id`. The **4-dimensional vectors are illustrative numbers**, not generated by a real model, so do not judge semantic search quality from the resulting order. In production, generate vectors with the **same model and dimensionality** before building indexes.

### 4.2. Metadata and Access Permissions Are Part of Retrieval

A query for `"internal duplicate key"` could give Tenant B's DOC-005 and the DRAFT DOC-006 very high vector scores. **Filter within each retrieval branch**; never rely on a reranker to strip unauthorized documents. Example filter:

~~~javascript
const auth = {
  tenantId: "tenant-a",
  visibility: "PUBLIC",
  status: "PUBLISHED"
}
~~~

In production, `tenantId`/`visibility`/`roles` must be resolved from a **trusted server-side authorization context**, never taken raw from client input.

## 5. Creating Indexes for Keyword and Vector Search

MongoDB Search and MongoDB Vector Search use **separate search indexes**, distinct from regular B-tree indexes. `db.kb_docs.createIndex({embedding:1})` does not create an ANN index.

### 5.1. Search Index for Keywords

~~~javascript
const lab = db.getSiblingDB("search315_lab")

lab.kb_docs.createSearchIndex("kb_text_v1", {
  mappings: {
    dynamic: false,
    fields: {
      title: { type: "string" },
      body: { type: "string" },
      tenantId: { type: "token" },
      visibility: { type: "token" },
      status: { type: "token" },
      language: { type: "token" }
    }
  }
})
~~~

This is a **sample index** for MongoDB Search with string fields and exact-token filters in versions supporting the `token` type. Analyzers, stemming, Vietnamese/English synonyms, punctuation splitting, and case folding must be configured and evaluated against your corpus. Do not assume a `dynamic:true` index is automatically optimal for every query.

### 5.2. Vector Search Index and Filter Fields

~~~javascript
lab.kb_docs.createSearchIndex("kb_vec_v1", {
  type: "vectorSearch",
  fields: [
    {
      type: "vector",
      path: "embedding",
      numDimensions: 4,
      similarity: "cosine"
    },
    { type: "filter", path: "tenantId" },
    { type: "filter", path: "visibility" },
    { type: "filter", path: "status" },
    { type: "filter", path: "language" }
  ]
})
~~~

**numDimensions=4 is strictly for the lab.** If your production model emits 768/1024/1536 dimensions, both the index and query vectors must use that dimension. Filter fields must be indexed with `type:"filter"` inside the **Vector Search index**, not only in the keyword index. MongoDB Search `equals` and vector `filter` do not share identical syntax even for the same business condition.

### 5.3. Search Indexes Build Asynchronously

`createSearchIndex()` initiates the build; returning does not mean the index is **READY**. Inspect with:

~~~javascript
lab.kb_docs.aggregate([
  { $listSearchIndexes: {} }
])
~~~

Practical rollout: create index `kb_vec_v2`, wait for completion, run benchmarks/shadow queries, flip a feature flag to v2, retain v1 briefly for rollback, and only then drop v1. Never update an embedding model and search mixed old and new vectors without version partitioning.

### 5.4. Who Generates Query Embeddings?

- **BYO embeddings:** the ingest pipeline computes a vector per document using model v1 and stores it in `embedding`; the query service also invokes **model v1** to produce `queryVector`.
- **Managed/automated embedding:** may be available on compatible deployments; check release/version, cost, and data privacy terms before using.

In the examples below, `queryEmbedding` is **passed from the preceding embedding step**. `$vectorSearch` does not automatically take a Vietnamese sentence and embed it into a vector on every MongoDB cluster.

## 6. Running the Two Queries Independently

Do not fuse results before validating **each branch individually**. If vector dimensions are wrong or the lexical index does not index `title`, fusion cannot fix upstream errors.

### 6.1. `$search`: Keyword + Title Boost + Filter

~~~javascript
const lab = db.getSiblingDB("search315_lab")
const q = "fix error E11000"

const lexical = lab.kb_docs.aggregate([
  {
    $search: {
      index: "kb_text_v1",
      compound: {
        should: [
          {
            text: {
              query: q,
              path: "title",
              score: { boost: { value: 3 } }
            }
          },
          { text: { query: q, path: "body" } }
        ],
        minimumShouldMatch: 1,
        filter: [
          { equals: { path: "tenantId", value: "tenant-a" } },
          { equals: { path: "visibility", value: "PUBLIC" } },
          { equals: { path: "status", value: "PUBLISHED" } }
        ]
      }
    }
  },
  { $limit: 20 },
  {
    $project: {
      title: 1, body: 1, sourceUrl: 1,
      lexicalScore: { $meta: "searchScore" }
    }
  }
]).toArray()

printjson(lexical)
~~~

`compound.should` matches `title` or `body`, and `minimumShouldMatch:1` requires at least one clause. Boosting `title` can make sense for a knowledge base, though it should be tuned on a judgment set. `$meta:"searchScore"` is the Search branch's lexical score; it is **not on the same scale** as a vector score.

### 6.2. `$vectorSearch`: ANN + Pre-Filter

~~~javascript
const queryEmbedding = [0.82, 0.39, 0.02, 0.03]

const semantic = lab.kb_docs.aggregate([
  {
    $vectorSearch: {
      index: "kb_vec_v1",
      path: "embedding",
      queryVector: queryEmbedding,
      numCandidates: 100,
      limit: 20,
      filter: {
        tenantId: "tenant-a",
        visibility: "PUBLIC",
        status: "PUBLISHED"
      }
    }
  },
  {
    $project: {
      title: 1, body: 1, sourceUrl: 1,
      vectorScore: { $meta: "vectorSearchScore" }
    }
  }
]).toArray()

printjson(semantic)
~~~

ANN's `numCandidates` is the number of neighbors examined during retrieval; `limit` is how many results the branch returns. Choose `numCandidates >= limit`—usually much larger—to trade latency for recall. `100/20` is only an example, not a universal optimum for large collections.

### 6.3. ENN to Evaluate ANN Recall

~~~javascript
// On deployments supporting exact vector search:
lab.kb_docs.aggregate([
  {
    $vectorSearch: {
      index: "kb_vec_v1",
      path: "embedding",
      queryVector: queryEmbedding,
      exact: true,
      limit: 20,
      filter: {
        tenantId: "tenant-a",
        visibility: "PUBLIC",
        status: "PUBLISHED"
      }
    }
  },
  { $project: { title: 1, vectorScore: { $meta: "vectorSearchScore" } } }
])
~~~

ENN serves as a reference for top neighbors under the same query and filter. ANN is faster on large workloads, yet you must measure **recall against ENN**; never put ENN on a tight-SLA online path without benchmarking.

### 6.4. Wrong: Post-Filtering After ANN Returns Top 20

~~~javascript
// AVOID: ANN evaluates all tenants/statuses first, then filters afterward.
[
  {
    $vectorSearch: {
      index: "kb_vec_v1", path: "embedding",
      queryVector: queryEmbedding, numCandidates: 100, limit: 20
    }
  },
  { $match: { tenantId: "tenant-a", visibility: "PUBLIC" } }
]
~~~

If 18 of the first 20 neighbors belong to another tenant, post-filtering leaves only two results while valid neighbors at ranks 21–40 are never examined. That is **recall loss due to post-filtering**. Moreover, never pass unauthorized content to a reranker or external model. **Apply indexed filters in both branches before fusion.**

## 7. Rank Fusion: Combining Lists with Reciprocal Rank Fusion (RRF)

The two branches return **different score scales**. A document with `lexicalScore:12.4` and `vectorScore:0.82` does not mean the lexical signal is 15 times stronger. Summing raw scores lets lexical dominate purely from scale.

**Reciprocal Rank Fusion (RRF)** solves this by using **rank positions within each list**, ignoring raw scores:

\[
\mathrm{RRF}(d)=\sum_{i:\,d\in L_i}
\frac{w_i}{k+\operatorname{rank}_i(d)}
\]

Where:

- \(d\): document being ranked.
- \(L_i\): result list from retriever \(i\).
- \(\operatorname{rank}_i(d)\): **1-based** rank position in list \(i\).
- \(w_i\): branch weight.
- \(k\): smoothing constant; **MongoDB `$rankFusion` uses `k=60` and does not expose tuning it** in current APIs.

### 7.1. Manual Calculation Example

~~~text
Lexical:               Vector:
  1. DOC-A               1. DOC-B
  2. DOC-B               2. DOC-D
  3. DOC-C               3. DOC-A
~~~

With equal branch weights of 1 and \(k=60\):

| Document | Lexical rank | Vector rank | Total RRF (approx.) |
|---|---:|---:|---:|
| DOC-A | 1 | 3 | \(1/61+1/63\approx0.03227\) |
| DOC-B | 2 | 1 | \(1/62+1/61\approx0.03252\) |
| DOC-C | 3 | Not present | \(1/63\approx0.01587\) |
| DOC-D | Not present | 2 | \(1/62\approx0.01613\) |

RRF favors B and A because they have signals in **both branches**, while still retaining DOC-C/DOC-D as candidates. A document appearing in only one branch is **not discarded**.

### 7.2. Strengths and Limitations

**Strengths:** No need to calibrate BM25 against cosine, insensitive to model/index score scales, easy to explain via ranks, merges and deduplicates multiple signals.

**Limitations:** Whether rank 1 beats rank 2 by a razor-thin margin or a huge margin looks identical in rank spacing. RRF does not understand the question, detect wrong document versions, or enforce authorization. For exact-code queries, you may increase lexical weight or add hard lexical filters.

### 7.3. RRF Is Not Semantic Reranking

`$rankFusion` **does not re-read `title`/`body` with a semantic model**. It only combines ranks produced by retrievers. A **cross-encoder reranker** reads **query and candidate text jointly** to judge relevance more deeply; that is a **post-fusion** step incurring extra latency and cost.

### 7.4. Deduplicate by the Right Identity

DOC-A appearing at lexical rank 1 and vector rank 3 must appear **once** with a combined score, not twice. When documents are split into chunks:

- Deduplicate by `chunkId` if the app supplies passages to RAG.
- Deduplicate/group by `parentDocumentId` if the UI displays one article per item.
- Avoid merging distinct chunks too early if they answer independent parts of the question.

Choice of identity also affects **Recall@K** (chunk-level vs. parent-level).

### 7.5. Weighted RRF by Query Category

~~~text
Query: "E11000 MongoDB v8.0.10"
  lexical weight = 0.70
  semantic weight = 0.30

Query: "how to avoid duplicate data when many users sign up concurrently"
  lexical weight = 0.35
  semantic weight = 0.65
~~~

These weights are **illustrative hypotheses** that must be tuned with judgment sets and A/B tests. An intent classifier recognizing error codes, versions, and SKUs can help, though classifiers can also misclassify.

### 7.6. Candidate Cutoffs and Recall

If lexical and vector each return only top 3, a relevant document ranked 4th in both branches **never reaches fusion**. Raising top-L/top-V to 20/50 improves recall at higher runtime/reranking cost. **Final K=5 does not mean each branch should fetch only 5**.

## 8. MongoDB `$rankFusion`: Hybrid Search in One Aggregation

Starting in **MongoDB 8.0** on deployments supporting these search stages, `$search` and `$vectorSearch` can be combined via `$rankFusion` directly inside MongoDB. The stage accepts **named sub-pipelines**, executes them independently on the **same collection**, deduplicates, and computes RRF.

### 8.1. Complete Keyword + Vector + RRF Example

~~~javascript
const lab = db.getSiblingDB("search315_lab")
const q = "fix error E11000 during registration"
const queryEmbedding = [0.82, 0.39, 0.02, 0.03]

const hybridResults = lab.kb_docs.aggregate([
  {
    $rankFusion: {
      input: {
        pipelines: {
          lexical: [
            {
              $search: {
                index: "kb_text_v1",
                compound: {
                  should: [
                    {
                      text: {
                        query: q,
                        path: "title",
                        score: { boost: { value: 3 } }
                      }
                    },
                    { text: { query: q, path: "body" } }
                  ],
                  minimumShouldMatch: 1,
                  filter: [
                    { equals: { path: "tenantId", value: "tenant-a" } },
                    { equals: { path: "visibility", value: "PUBLIC" } },
                    { equals: { path: "status", value: "PUBLISHED" } }
                  ]
                }
              }
            },
            { $limit: 30 }
          ],
          semantic: [
            {
              $vectorSearch: {
                index: "kb_vec_v1",
                path: "embedding",
                queryVector: queryEmbedding,
                numCandidates: 200,
                limit: 30,
                filter: {
                  tenantId: "tenant-a",
                  visibility: "PUBLIC",
                  status: "PUBLISHED"
                }
              }
            }
          ]
        }
      },
      combination: {
        weights: {
          lexical: 0.45,
          semantic: 0.55
        }
      },
      scoreDetails: true
    }
  },
  {
    $project: {
      _id: 1, title: 1, body: 1, sourceUrl: 1,
      fusionScore: { $meta: "score" },
      fusionDetails: { $meta: "scoreDetails" }
    }
  },
  { $limit: 10 }
]).toArray()

printjson(hybridResults)
~~~

**How to read it:** lexical pulls up to 30, semantic pulls up to 30; MongoDB merges and deduplicates them, computes weighted RRF, and then projects/limits to top 10. When a document appears in both branches, both contribute to its score. `scoreDetails:true` helps inspect score breakdowns while debugging.

### 8.2. Why Does `$project` Come **After** `$rankFusion`?

`$rankFusion` requires each input pipeline to return the **exact original unmodified documents** so it can match and deduplicate them. Putting `$project`/`$addFields` inside an input pipeline is outside the supported stage set:

~~~javascript
// Wrong: mutates the document inside an input pipeline.
{
  $rankFusion: {
    input: {
      pipelines: {
        lexical: [
          { $search: { /* ... */ } },
          { $project: { title: 1 } } // Unsupported here.
        ]
      }
    }
  }
}
~~~

**Place projection after fusion**, and only then extract `$meta:"score"`/`$meta:"scoreDetails"`. Sub-pipelines accept a restricted set of stages (such as `$search`, `$vectorSearch`, `$match`, `$sort`, `$limit` depending on version); do not place arbitrary `$facet` or `$lookup` stages inside them.

### 8.3. Pipeline Names and Weights

~~~javascript
input: {
  pipelines: {
    lexical: [/* ... */],
    semantic: [/* ... */]
  }
},
combination: {
  weights: {
    lexical: 0.45,
    semantic: 0.55
  }
}
~~~

`lexical` and `semantic` are **names you choose** and must match keys in `weights`. Avoid empty names, dots (`.`), leading `$`, or forbidden characters. If a branch omits a weight, the default is typically 1—do not assume weights automatically normalize according to business intent.

### 8.4. `scoreDetails` Is Not Displayed Automatically

`scoreDetails:true` attaches **metadata**, which is not emitted as a document field automatically. Use:

~~~javascript
{ $project: {
    title: 1,
    fusionScore: { $meta: "score" },
    fusionDetails: { $meta: "scoreDetails" }
}}
~~~

Internal metadata structure may evolve across MongoDB versions; avoid parsing `fusionDetails.details[0]` deeply as a stable business contract. Use `scoreDetails` for debugging during development.

### 8.5. Practical Limitations

- `$rankFusion` only combines pipelines on **one collection**; it does not join documents across multiple collections.
- Input pipelines must emit **original documents**; project after fusion.
- Per the current MongoDB Manual, input pipelines run **sequentially**, not in parallel; hybrid latency is not necessarily `max(lexical latency, vector latency)`.
- **Pagination** support on fusion stages is limited; avoid deep paging with large `skip`/`limit` without accounting for rank stability and cost.
- Candidate pool limits affect recall, CPU/memory, and latency.
- Never fuse unauthorized documents and filter them afterward with `$match`.
- Views, time-series collections, and certain deployment features carry version-specific restrictions.

### 8.6. Query Embeddings Are Computed Outside the Stage

`queryEmbedding` is a precomputed array. A production service must call the right embedding model version before running the aggregation. If the embedding service times out, degrade to **lexical-only**—never send a random or empty vector “for MongoDB to figure out”.

### 8.7. Combining More Than Two Sources

~~~text
lexical_title      - exact names, codes
lexical_body       - body + synonyms
semantic_body      - content embeddings
semantic_title     - title embeddings
~~~

Adding more branches does not always improve search: boosting `title` in lexical search while adding a separate title branch can **double-count the same signal**. Every new branch should prove its value on an evaluation set.

## 9. `$scoreFusion`: Combining Normalized Scores

**MongoDB 8.3+** adds `$scoreFusion` to blend queries by **score**, not rank alone. While `$rankFusion` ignores the gap between rank 1 and rank 2, `$scoreFusion` can preserve magnitude differences after **normalizing** both branches.

### 9.1. Why Is Normalization Needed?

Suppose results are:

~~~text
Lexical BM25: 13.2, 8.5, 3.1
Vector score:  0.89, 0.82, 0.77
~~~

Adding raw scores lets lexical dominate purely from larger numeric values. Treating `13.2 + 0.89` as a probability makes no mathematical sense. MongoDB `$scoreFusion` supports:

| Normalization | Idea | Notes |
|---|---|---|
| `none` | Keep raw scores as-is. | Use only when both scores already share a calibrated scale. |
| `sigmoid` | \(s'=1/(1+e^{-s})\). | Compresses into (0,1) independent of current candidate list min/max; very large scores all cluster near 1. |
| `minMaxScaler` | \(s'=(s-\min)/(\max-\min)\). | Depends on the score distribution of the current list; outliers can skew the range. |

No single normalization is best for every corpus. After normalization, `weights` adjust keyword vs. vector contribution. When result sets overlap only partially, check how missing-branch scores are handled.

### 9.2. MongoDB 8.3+ Example Using `$scoreFusion`

~~~javascript
const lab = db.getSiblingDB("search315_lab")
const q = "handle duplicate key during account registration"
const queryEmbedding = [0.82, 0.39, 0.02, 0.03]

lab.kb_docs.aggregate([
  {
    $scoreFusion: {
      input: {
        pipelines: {
          lexical: [
            {
              $search: {
                index: "kb_text_v1",
                compound: {
                  must: [
                    { text: { query: q, path: ["title", "body"] } }
                  ],
                  filter: [
                    { equals: { path: "tenantId", value: "tenant-a" } },
                    { equals: { path: "visibility", value: "PUBLIC" } },
                    { equals: { path: "status", value: "PUBLISHED" } }
                  ]
                }
              }
            },
            { $limit: 30 }
          ],
          semantic: [
            {
              $vectorSearch: {
                index: "kb_vec_v1",
                path: "embedding",
                queryVector: queryEmbedding,
                numCandidates: 200,
                limit: 30,
                filter: {
                  tenantId: "tenant-a",
                  visibility: "PUBLIC",
                  status: "PUBLISHED"
                }
              }
            }
          ]
        },
        normalization: "sigmoid"
      },
      combination: {
        method: "avg",
        weights: { lexical: 0.45, semantic: 0.55 }
      },
      scoreDetails: true
    }
  },
  {
    $project: {
      _id: 1, title: 1, sourceUrl: 1,
      score: { $meta: "score" },
      details: { $meta: "scoreDetails" }
    }
  },
  { $limit: 10 }
])
~~~

Here, `normalization:"sigmoid"` is applied per branch, `method:"avg"` blends them, and `weights` control the ratio. `scoreDetails:true` aids observability. **Do not rename `$rankFusion` to `$scoreFusion` while leaving the exact same `weights` structure unchanged**: `$scoreFusion` puts `normalization` inside `input`, and `combination` takes `method`/`weights` or an expression.

### 9.3. When Does `$scoreFusion` Outperform RRF?

- You need to distinguish a document with an overwhelmingly high score from nearby competitors within the **same retriever**.
- You have established proper score calibration/normalization across retrievers.
- You want weighted score blending evaluated against graded relevance judgments.
- Corpus and models are stable, and you measured that score magnitudes carry extra signal beyond ranks.

When model scores fluctuate or distributions shift across queries, **RRF is a simpler, easier-to-maintain baseline**. Do not assume score fusion is superior merely because the API is newer.

### 9.4. `$scoreFusion` Does Not Fix Missing Candidates

If the right document appears in neither input pipeline, score fusion cannot conjure it. Top-L/top-V caps, ANN recall, index coverage, and filter semantics still dictate **candidate recall** prior to fusion.

### 9.5. Advanced Expression Scoring

`$scoreFusion` can use `combination.method:"expression"` to define custom arithmetic expressions referencing normalized pipeline scores by name. Do not supply `weights` alongside `expression` where syntax makes them mutually exclusive. This enables lightweight learning-to-rank, at the cost of harder debugging and overfitting risk.

An engineering team should progress through:

1. Lexical-only baseline.
2. Vector-only baseline.
3. Default-weight RRF.
4. Query-category weights.
5. `$scoreFusion` with normalization choices.
6. Reranker over top-M.

Evaluate each change on quality, latency, and cost—never by comparing unscaled raw scores.

## 10. Reranking: Re-Evaluating the Top-M Documents

A **reranker** is a model that scores relevance between **the question and each retrieved document/passage**. A **cross-encoder** reads the `(query, text)` pair jointly, capturing negation, troubleshooting intent, version rules, and fine-grained context better than nearest-neighbor distance in embedding space.

~~~text
Lexical top 40 + Vector top 40
             |
             v
    RRF union (up to 80)
             |
          Top M=25
             |
             v
  Reranker scores 25 (query, candidate) pairs
             |
             v
   Reorders those 25 docs
             |
          Top K=10
~~~

The reranker **does not discover** documents outside the 25 candidates. Retrieval and fusion therefore supply **candidate recall**, while the reranker optimizes **top-position precision/quality**.

### 10.1. Where Can Reranking Help?

| Scenario | How reranking helps |
|---|---|
| Query asks “how to fix”, doc only defines terms | Pushes actionable troubleshooting steps above overview pages. |
| Query requires version 8.3 | Distinguishes passages discussing `8.3` from `8.0` if clear in text. |
| Query has negation “without transactions” | Prefers docs covering exceptions/alternatives over docs merely mentioning transactions. |
| Long doc has one crucial sentence | Can select the more relevant passage/chunk among top candidates. |
| Multiple docs share the same keywords | Reads context to distinguish use cases. |

**Limitations:** Rerankers still make mistakes—especially on rare identifiers, exact strings, low-resource Vietnamese text, stale info, or truncated long documents. When a query demands `MongoDB 8.0.10`, you still need **version filters / exact lexical signals**, not blind trust in the model.

### 10.2. Rerankers Differ from “LLM Answering Questions”

A reranker outputs a **relevance score or ordering** per candidate rather than synthesizing an answer. In a RAG pipeline:

~~~text
Retrieval / Fusion -> Rerank -> Evidence top K -> Answer LLM -> Citations
~~~

Never confuse fluent LLM prose with high retrieval quality. If the wrong document enters top-K, an LLM can still craft a very convincing wrong answer. Evaluate retrieval/reranking **independently** before evaluating final generated answers.

### 10.3. Native `$rerank` in MongoDB When Eligible

MongoDB provides the `$rerank` stage to reorder results using Voyage AI models. **Version/availability note:** current `$rerank Aggregation Pipeline Stage` docs (checked Nov 2026) specify **MongoDB 9.0+** clusters, enabling **Native Reranking** in Atlas Project Settings, and **not supported on self-managed/Atlas Local**; some models require dedicated tiers. Older or differently timed overview pages may mention 8.3; when deploying, check the **dedicated Requirements page for `$rerank` and your exact cluster**, rather than generalizing one milestone across all hybrid features.

Example right after `$rankFusion` (on a cluster with **rerank enabled**):

~~~javascript
const q = "fix error E11000 during registration"

lab.kb_docs.aggregate([
  {
    $rankFusion: {
      input: {
        pipelines: {
          // Replace with the two real sub-pipelines from Section 8.1.
          lexical: [
            { $search: {
                index: "kb_text_v1",
                compound: {
                  must: [
                    { text: { query: q, path: ["title", "body"] } }
                  ],
                  filter: [
                    { equals: { path: "tenantId", value: "tenant-a" } },
                    { equals: { path: "visibility", value: "PUBLIC" } },
                    { equals: { path: "status", value: "PUBLISHED" } }
                  ]
                }
            }},
            { $limit: 30 }
          ],
          semantic: [
            { $vectorSearch: {
                index: "kb_vec_v1",
                path: "embedding",
                queryVector: [0.82, 0.39, 0.02, 0.03],
                numCandidates: 200,
                limit: 30,
                filter: {
                  tenantId: "tenant-a",
                  visibility: "PUBLIC",
                  status: "PUBLISHED"
                }
            }}
          ]
        }
      }
    }
  },
  { $addFields: { fusionScore: { $meta: "score" } } },
  {
    $rerank: {
      query: { text: q },
      path: ["title", "body"],
      numDocsToRerank: 20,
      model: "rerank-2.5-lite"
    }
  },
  { $addFields: { rerankScore: { $meta: "score" } } },
  { $project: {
      title: 1, body: 1, sourceUrl: 1,
      fusionScore: 1, rerankScore: 1
  }},
  { $limit: 10 }
])
~~~

**Important distinction:** `$rerank` sits **after fusion**, not inside `$rankFusion`'s input pipelines. `$rerank` overwrites `$meta:"score"` with the new score; if you want to keep the pre-rerank score, **materialize it into a `fusionScore` field first** as shown. `numDocsToRerank` caps how many input documents are evaluated; make sure the preceding stage already produced a **reliable ordering**.

### 10.4. Requirements and Costs of Native Reranking

Per current docs:

- Enable Native Reranking in the Atlas project, ensure model access, and account for **usage-based costs**.
- `path` must exist on all input documents; missing fields can cause the query to fail. Filter out documents missing the field or set fallback text before reranking.
- `numDocsToRerank` has a documented maximum (currently 1000), though you should not send 1000 when you only need top 10 and low latency.
- **Per-request/per-node memory limits** apply; troubleshooting docs currently note 30 MiB per request and 128 MiB total node buffer in certain deployments.
- Certain models/tiers/regions have restrictions or preview status; verify data-processing terms for the reranking service.
- Available `model` names may change across releases; use configuration flags and fallbacks.

### 10.5. When Your Cluster Lacks `$rerank`

The application can take top M from `$rankFusion` (8.0+) or app-side RRF and **call an external cross-encoder/reranking service** on the candidates:

~~~text
MongoDB -> top 25 authorized documents
   |
   v
Application strips PII/unneeded fields
   |
   v
Reranker API: query + [candidateId, text]
   |
   v
Sorted scores -> application applies final ACL/status check
   |
   v
Return top 10
~~~

Benefits include flexibility in models, tuning, and caching. Trade-offs include managing **latency, cost, networking, timeouts, rate limits, privacy, and provenance**. Never send sensitive documents to an unapproved provider.

### 10.6. When Should You Skip Reranking?

- Queries contain **only an exact code** and lexical/exact matching is already accurate.
- Ultra-low p95 SLA leaves no room for model inference or network hops.
- Candidate count is tiny and the corpus is very uniform.
- No reranker model adequately supports the target language/domain.
- Reranking cost outweighs measurable relevance gains.

A pipeline with **hybrid fusion without a reranker** is still valid hybrid search. Reranking is a **KPI-driven option**, not mandatory just because vectors are used.

## 11. When `$rankFusion` Is Unavailable: Fusing in the Application Layer

If the deployment supports MongoDB Search and Vector Search but the server does not yet support `$rankFusion`, the application can run **two independent queries**, receive two ranked lists, and merge them with RRF. This also works when combining results across **multiple collections** or an external search engine, given clear identity, deduplication, and ACL rules.

### 11.1. Pure JavaScript RRF Function

~~~javascript
// Node.js/service code, NOT a mongosh pipeline.
function reciprocalRankFusion(
  pipelines,
  weights = { lexical: 0.5, semantic: 0.5 },
  k = 60
) {
  const rows = new Map()

  for (const [name, docs] of Object.entries(pipelines)) {
    const weight = weights[name] ?? 1
    if (!Number.isFinite(weight) || weight < 0) {
      throw new Error("Invalid weight: " + name)
    }

    docs.forEach((doc, index) => {
      // Stable identity; production needs tenant/source if IDs aren't global.
      const id = String(doc._id)
      const current = rows.get(id) ?? {
        ...doc,
        rrfScore: 0,
        contributions: []
      }

      const rank = index + 1 // Ranks start at 1.
      const contribution = weight / (k + rank)
      current.rrfScore += contribution
      current.contributions.push({
        pipeline: name,
        rank,
        contribution
      })
      rows.set(id, current)
    })
  }

  return [...rows.values()].sort((a, b) =>
    b.rrfScore - a.rrfScore ||
    String(a._id).localeCompare(String(b._id))
  )
}

const lexicalResults = [
  { _id: "DOC-A", title: "Article A" },
  { _id: "DOC-B", title: "Article B" },
  { _id: "DOC-C", title: "Article C" }
]

const vectorResults = [
  { _id: "DOC-B", title: "Article B" },
  { _id: "DOC-D", title: "Article D" },
  { _id: "DOC-A", title: "Article A" }
]

const ranked = reciprocalRankFusion(
  { lexical: lexicalResults, semantic: vectorResults },
  { lexical: 1, semantic: 1 },
  60
)
console.table(ranked.map(d => ({
  id: d._id, rrf: d.rrfScore
})))
~~~

Expected **score order** is B, A, D, C as in Section 7.1's table. This code **illustrates the algorithm**, not a production library handling all failures. On large result sets, normalize ObjectId/UUID `_id` values consistently and avoid trusting `title`/`body` across unaligned revisions.

### 11.2. Guarding Against Duplicates Within a Single Branch

A retriever should normally return each document once. If an adapter accidentally returns the same `_id` twice **within the same pipeline**, the simple function above adds its contribution twice. Production code should **deduplicate each branch before computing ranks** (retaining its first rank), then fuse across branches.

Also, when one article is chunked into multiple documents, decide consistently whether ranking operates on `chunkId` or `parentDocId` per your answer goal.

### 11.3. Guarding Query Shape Before Running in Parallel

With app-side fusion, you can run both requests via `Promise.all`:

~~~javascript
// Pseudocode: lexicalQuery() and vectorQuery() are existing helpers.
const [lexicalRows, vectorRows] = await Promise.all([
  lexicalQuery({ q, tenantId, visibility: "PUBLIC", status: "PUBLISHED" }),
  vectorQuery({ queryEmbedding, tenantId, visibility: "PUBLIC", status: "PUBLISHED" })
])

const top = reciprocalRankFusion(
  { lexical: lexicalRows, semantic: vectorRows },
  { lexical: 0.5, semantic: 0.5 }
).slice(0, 10)
~~~

If queries hit **different collections or index revisions**, the two branches may observe different document versions. Enforce versioning, consistent ACL filters, and stable IDs when reconciling. If one branch fails, apply an explicit fallback policy with clear logs/metrics rather than silently returning an unlogged empty success.

### 11.4. When Is App-Side Fusion Better Than Database-Side?

| Aspect | `$rankFusion` in MongoDB | App-side RRF |
|---|---|---|
| Server version | Requires MongoDB 8.0+. | Works on deployments with two separate retrievers. |
| Collections | Single collection per stage. | Can merge multiple sources with aligned IDs/ACLs. |
| Network | One aggregate request. | Typically two requests plus candidate payloads returned. |
| Concurrency | Docs note stage inputs run sequentially. | Application can run in parallel, subject to pool/resources. |
| Tuning | Built-in weighted RRF, scoreDetails. | Full control over `k`, tie-breaks, dedupe, fallback. |
| Complexity | Less fusion boilerplate. | Must maintain custom logic, tests, and monitoring. |
| Security | Each sub-pipeline still must pre-filter. | Both queries and outbound payloads must be controlled. |

Choose based on **deployment constraints, latency, reliability, and operational cost**, rather than assuming one is universally faster.

### 11.5. Never Blend Raw Scores Arbitrarily in App Code

~~~javascript
// Avoid when lexicalScore and vectorScore are not on the same scale:
combined = 0.5 * lexicalScore + 0.5 * vectorScore
~~~

If using score fusion in the app, define normalization (per-query min-max/sigmoid or training-set calibration), handle missing-score documents, define tie-breakers, and evaluate stability across model/index updates. App-side RRF is usually a safer starting baseline.

## 12. Java Sync Driver: Building a Hybrid Pipeline with `Document`

The Java Sync Driver accepts a MongoDB aggregation pipeline as a list of `Bson` stages. You do not need specialized Java wrappers for every new stage: you can construct `org.bson.Document` to send exact MongoDB query syntax, provided the driver/server supports it and inputs are validated.

### 12.1. A Hybrid Search Method

The snippet below illustrates the structure. `queryEmbedding` must be computed using **the same embedding model as the indexed data**; the application manages `MongoClient`, timeouts, and auth context externally.

~~~java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import org.bson.Document;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

public final class HybridKnowledgeSearch {

    private final MongoCollection<Document> docs;

    public HybridKnowledgeSearch(MongoDatabase db) {
        this.docs = db.getCollection("kb_docs");
    }

    public List<Document> search(
        String authorizedTenantId,
        String text,
        List<Double> queryEmbedding
    ) {
        // Validate nonblank text, tenant from authenticated context,
        // embedding dimensions/model version at service boundary.

        Document lexicalSearch = new Document(
            "$search",
            new Document("index", "kb_text_v1")
                .append("compound",
                    new Document("must", List.of(
                        new Document("text",
                            new Document("query", text)
                                .append("path", List.of("title", "body"))
                        )
                    ))
                    .append("filter", List.of(
                        new Document("equals",
                            new Document("path", "tenantId")
                                .append("value", authorizedTenantId)),
                        new Document("equals",
                            new Document("path", "visibility")
                                .append("value", "PUBLIC")),
                        new Document("equals",
                            new Document("path", "status")
                                .append("value", "PUBLISHED"))
                    ))
                )
        );

        Document vectorSearch = new Document(
            "$vectorSearch",
            new Document("index", "kb_vec_v1")
                .append("path", "embedding")
                .append("queryVector", queryEmbedding)
                .append("numCandidates", 200)
                .append("limit", 30)
                .append("filter",
                    new Document("tenantId", authorizedTenantId)
                        .append("visibility", "PUBLIC")
                        .append("status", "PUBLISHED"))
        );

        Document fusion = new Document(
            "$rankFusion",
            new Document("input",
                new Document("pipelines",
                    new Document("lexical",
                        List.of(lexicalSearch, new Document("$limit", 30)))
                        .append("semantic", List.of(vectorSearch))
                ))
                .append("combination",
                    new Document("weights",
                        new Document("lexical", 0.45)
                            .append("semantic", 0.55)))
                .append("scoreDetails", true)
        );

        Document projection = new Document(
            "$project",
            new Document("_id", 1)
                .append("title", 1)
                .append("body", 1)
                .append("sourceUrl", 1)
                .append("score", new Document("$meta", "score"))
        );

        List<Document> stages = Arrays.asList(
            fusion,
            projection,
            new Document("$limit", 10)
        );

        return docs.aggregate(stages)
            .into(new ArrayList<>());
    }
}
~~~

**Prerequisites:** Cluster supports `$rankFusion` (8.0+), indexes `kb_text_v1`/`kb_vec_v1` are READY, `queryEmbedding` has exact 4 dimensions for the lab, and all filter values are valid. A newer driver can serialize a `Document` stage, yet an **older server version will still report an unsupported stage**.

### 12.2. Never Concatenate Query Text into Raw JSON Arbitrarily

Do not build queries by concatenating raw user input into JSON/JavaScript strings and parsing them. Use BSON constructors/builders and **parameter values** as shown; validate max query length, finite vector values and dimensions, and tenant/role scope from the auth context. If a user types `"$ne"` or `{"$gt":0}`, it must remain **searchable text**, never turning into a filter operator.

### 12.3. Per-Stage Timeouts and Fallbacks

A production service should implement:

~~~text
Generate query embedding
  |
  +-- success --> hybrid aggregate
  |                  |
  |                  +-- success --> optional rerank --> result
  |                  |
  |                  +-- timeout --> lexical-only fallback (if policy allows)
  |
  +-- timeout/fail --> lexical-only fallback
~~~

Log **degraded mode** and expose reliability metrics rather than swallowing exceptions with `return List.of()`. For error-code queries, lexical-only can be an acceptable fallback; for long natural-language questions, quality drops noticeably without the vector branch.

### 12.4. Separating Responsibilities in Java

Organize clear interfaces:

- `EmbeddingProvider`: `embed(query,modelVersion)`.
- `LexicalRetriever`: `search(query,scope,limit)`.
- `VectorRetriever`: `search(vector,scope,limit)`.
- `FusionStrategy`: RRF/score fusion controlled by feature flags.
- `Reranker`: `rerank(query,candidates)` with deadline/budget.
- `SearchPolicy`: tenant ACL, status, version, permitted fields.
- `SearchEvaluation`: query logs, feedback, judgments.

This separation enables **A/B testing** and falling back to app-side fusion without changing the controller API.

## 13. Access Permissions, Versions, and Metadata Filters in Hybrid Search

**Relevance must never override authorization.** A vector score of 0.99 on another tenant's document must still be excluded. This is a non-negotiable invariant of multi-tenant semantic search.

### 13.1. Checkpoints in Each Branch

| Branch / step | Mandatory requirement |
|---|---|
| `$search.compound.filter` | Tenant, visibility, status, and ACLs indexed with proper types. |
| `$vectorSearch.filter` | Equivalent business scope; fields declared as `filter` in the vector index. |
| Fusion | Merge only authorized candidates; never mix other tenants into the shared list. |
| Reranker | Send only allowed candidate texts; minimize PII and token count. |
| Final output | Recheck permissions/status/freshness when needed and strip unpublished fields. |
| Logs/analytics | Do not log full private bodies or sensitive queries outside policy. |

### 13.2. Why Both Branches?

Suppose semantic search ranks Tenant B's private DOC-005 at #1, while lexical search returns only Tenant A documents. If only lexical search filtered by tenant, **fusion could promote DOC-005 to the top**, letting the reranker read Tenant B's private content. Hiding it in the final response **does not undo intermediate data exposure**.

### 13.3. Document Version and Publishing Status

A knowledge base may contain:

~~~javascript
{
  tenantId: "tenant-a",
  status: "PUBLISHED",
  product: "MongoDB",
  version: "8.0",
  effectiveFrom: ISODate("2026-01-01T00:00:00Z"),
  effectiveTo: null
}
~~~

A question `"Does MongoDB 8.0 support scoreFusion yet?"` must not return an 8.3 page just because it is semantically close. Combine exact/keyword matching with a metadata filter `version:"8.0"`, use version-range logic where appropriate, and surface `version`/`updatedAt` in the final result for user verification.

### 13.4. Time-Range Filters and Changing ACLs

A document switched from PUBLIC to PRIVATE may remain in the search index briefly due to **index propagation/index lag**. Search indexes are not the sole authorization layer: verify permissions strongly when serving sensitive data, and define a **revocation latency** policy. Under strict confidentiality requirements, never send sensitive content to a reranker before re-verifying access.

### 13.5. Advanced Filtering: Lexical Filters and Vector Filters Differ

`$search.compound.filter` uses Search operators like `equals`, `range`, `in`, etc. By contrast, `$vectorSearch.filter` uses Vector Search's supported **pre-filter operators and field types**; fuzzy or phrase matching is not available inside `$vectorSearch.filter`.

If you need **fuzzy text** as a **prefilter before semantic vector search**, MongoDB also offers the `vectorSearch` operator **inside `$search`** on certain deployments/versions, supporting MongoDB Search filter operators. Do not confuse the two:

~~~javascript
// Two distinct APIs:
{ $vectorSearch: { /* aggregation stage */ } }

{ $search: {
    index: "some_search_index",
    vectorSearch: { /* Search operator */ }
} }
~~~

Select the right index type, syntax, and version from documentation; never paste `$vectorSearch` stage options into the `$search` operator assuming they are identical.

## 14. Chunking: Searching Long Documents Without Duplicate Clutter

In RAG and knowledge search, a 15-page document spans multiple topics. Embedding the entire document as one vector blurs the specific answer; semantic search typically works much better on appropriately sized **chunks**.

### 14.1. Chunk Schema

~~~javascript
{
  _id: "DOC-001#CHUNK-03",
  parentDocumentId: "DOC-001",
  chunkOrdinal: 3,
  tenantId: "tenant-a",
  visibility: "PUBLIC",
  status: "PUBLISHED",
  title: "Fixing duplicate key error E11000",
  body: "Concurrent upsert case: use a unique index and handle E11000...",
  section: "Concurrency handling",
  sourceUrl: "/kb/duplicate-key#concurrency",
  embeddingModel: "embed-v2",
  embedding: [/* real vector, matching dimensions */]
}
~~~

Build both Search and Vector Search indexes on **the same chunks collection** when using `$rankFusion`. If one branch queries `kb_docs` and the other queries `kb_chunks`, they cannot be placed together in a single `$rankFusion` because sub-pipelines must read **the same collection**.

### 14.2. Chunk Size and Overlap

- Chunk too short: lacks context, loses definitions from adjacent paragraphs, creates snippet sprawl.
- Chunk too long: diluted embeddings, expensive reranker tokens, or truncation.
- Too little overlap: exact answers spanning two chunks get split in half.
- Too much overlap: nearly identical chunks dominate top-K, hurting **diversity**.

Choose chunk length by evaluating on real data. Prefer splitting on **headings, paragraphs, code fences, tables, and semantic boundaries** in technical docs before applying token/overlap caps.

### 14.3. Chunk-Level vs. Parent-Level Deduplication

~~~text
Lexical:
  DOC-001#CHUNK-03
  DOC-001#CHUNK-04

Vector:
  DOC-001#CHUNK-03
  DOC-002#CHUNK-01
~~~

Fusion by `chunkId` gives DOC-001#CHUNK-03 contributions from both sources, while DOC-001#CHUNK-04 remains a separate candidate. If the UI lists **articles**, group by `parentDocumentId` **after** selecting relevant passages while retaining exact offsets for citations.

### 14.4. Parent Fetches Must Recheck ACLs

After retrieving chunks, the app may fetch parent titles/metadata from another collection. Never assume “chunk was authorized ⇒ all parent fields are authorized”: the parent may have transitioned to PRIVATE, REVOKED, deleted, or a new revision. Check permissions against the **server-side user context** at response time.

### 14.5. Reranking with Well-Sized Context

The reranker evaluates `query + text`. If `body` is huge, send the relevant chunk, title, and brief section heading while dropping unnecessary fields. Truncating mid-sentence can cut off words like “not” or version numbers and invert meaning. Measure quality with and without truncation rather than assuming the opening lines always matter most.

## 15. Query Understanding: Weighting by Intent

The query `"E11000"` differs from `"why do duplicate key inserts happen when two users send requests concurrently"`. A lightweight classifier or heuristic can detect:

- **Exact code/identifier:** error codes, class names, API paths, SKUs, version strings.
- **Natural-language question:** long sentences, synonyms, paraphrased Vietnamese.
- **Navigation:** searching for a known title or document.
- **Comparison:** “difference between sparse and partial unique indexes”.
- **Multi-intent:** multi-part questions needing multiple evidence chunks.
- **Version/entity constraints:** MongoDB 7.0 vs. 8.3, release notes, region, or effective date.

### 15.1. Weight Selection Matrix

| Query type | Lexical | Vector | Rerank | Notes |
|---|---|---|---|---|
| Error code `E11000` | Prioritize exact terms. | Supplemental explanation. | Optional if match is already exact. | Preserve code verbatim. |
| “How to avoid duplicate data?” | Terms/synonyms. | Unique index/idempotency concepts. | Helpful for picking how-to guides. | Do not answer without evidence. |
| Java class name | Prioritize exact/phrase. | Supplemental related docs. | SLA-dependent. | Keep punctuation/casing in analyzer when needed. |
| Multilingual query | Language-specific analyzer. | Multilingual embedding. | Multilingual reranker. | Measure Vietnamese/English/diacritics & plain text. |
| “MongoDB 8.0 scoreFusion” | Exact version/name. | Conceptual context. | Can help. | Must verify version explicitly. |
| “latest guide” | Terms + freshness filter. | Topic search. | Select evidence. | Relevance differs from freshness. |

### 15.2. Abbreviations, Synonyms, and Vietnamese Diacritics

~~~text
TTL             <-> time-to-live
unique index    <-> chỉ mục duy nhất
duplicate key   <-> trùng khóa
retryable write <-> ghi có thể thử lại
~~~

Here **synonyms/analyzers** in MongoDB Search strengthen lexical matching, while embeddings bridge longer phrasings. Keep synonyms domain-scoped: the same acronym can mean different things across industries. Uncontrolled synonym expansion increases false positives.

### 15.3. Negation and Versions

~~~text
"updates are not allowed on time-series"
"deletes on time-series are supported starting in 7.0"
~~~

Both sentences share many tokens yet carry **opposite/distinct predicates**. A reranker can help differentiate them, combined with **version metadata, exact phrases, and section headings**. Never treat intent heuristics as a substitute for hard business filters.

### 15.4. Multi-Query Expansion

~~~text
Original Q: "how to handle duplicate error on upsert"
Q1: "duplicate key E11000 upsert"
Q2: "MongoDB unique index concurrent upsert"
~~~

Running multiple query variants can boost recall at higher latency/cost, easily **double-counts** identical evidence, and risks introducing unintended entities or versions. For error codes/identifiers, never let paraphrasing drop critical tokens. Expand queries only when the baseline demonstrably misses documents due to phrasing differences.

## 16. Measuring Quality: What Does Good Retrieval Mean?

Never claim a pipeline is “better” simply because you added vectors and a reranker. You need a **labeled relevance test set** covering realistic use cases and comparable metrics across versions.

### 16.1. Building a Judgment Set

Each test query can contain:

~~~javascript
{
  queryId: "Q-001",
  query: "fix error E11000 on upsert",
  tenantId: "tenant-a",
  language: "vi",
  intent: "troubleshooting",
  productVersion: "8.0",
  relevance: {
    "DOC-001#CHUNK-03": 3,
    "DOC-002#CHUNK-01": 2,
    "DOC-003#CHUNK-01": 0
  }
}
~~~

For example, **0 = irrelevant**, **1 = marginally relevant**, **2 = helpful**, **3 = directly answers**. Provide labeling guidelines and independent reviewers where possible. Include **unanswerable queries**, queries with negation, error codes/versions, accented/unaccented Vietnamese, and ACL-sensitive queries.

### 16.2. Key Metrics

| Metric | Meaning | Purpose |
|---|---|---|
| **Recall@K** | Fraction of known relevant docs appearing in top K. | Candidate coverage, especially pre-rerank. |
| **Precision@K** | Fraction of top K meeting relevance threshold. | Cleanliness of top results. |
| **MRR@K** | Mean reciprocal rank of the first relevant hit. | Good for exact/navigational queries. |
| **nDCG@K** | Graded ranking quality with position discount. | Suited for 0–3 relevance labels. |
| **Hit Rate@K** | At least one relevant document in top K. | RAG evidence retrieval. |
| **ANN Recall@K vs. ENN** | Fraction of exact nearest neighbors found by ANN. | Tuning `numCandidates`. |
| **p95/p99 latency** | Tail latency of the query pipeline. | User-facing SLOs. |
| **Cost/query** | Embeddings, search/vector index, reranker calls. | Budget and scaling. |
| **Unauthorized exposure count** | Out-of-scope ACL candidates/results processed. | Must be **0** by policy. |
| **Freshness lag** | Delay between doc/embedding/index update and search visibility. | New vs. stale content policy. |

### 16.3. MRR and nDCG Illustrated

If the system returns `[DOC-X, DOC-B, DOC-A]` and the first relevant doc is DOC-B at rank 2, the **query's reciprocal rank** is \(1/2\). MRR averages reciprocal ranks across many queries and is **not** a relevance probability.

With graded relevance \(rel_i\):

\[
\mathrm{DCG@K}=
\sum_{i=1}^{K}\frac{2^{rel_i}-1}{\log_2(i+1)}
\]

\(\mathrm{nDCG@K}=\mathrm{DCG@K}/\mathrm{IDCG@K}\), where IDCG is the ideal score when documents are sorted by descending relevance. Define how queries with zero positive judgments are handled so zero denominators do not corrupt reports.

### 16.4. Ablation Testing Each Component

| Baseline | Retrieval | Fusion | Rerank |
|---|---|---|---|
| A | Keyword only | None | None |
| B | Vector only | None | None |
| C | Keyword + vector | RRF 0.5/0.5 | None |
| D | Keyword + vector | Tuned RRF | None |
| E | Keyword + vector | Normalized `$scoreFusion` | None |
| F | Keyword + vector | Tuned RRF | Rerank top 20 |

Compare across **identical corpus/index/model states, query sets, ACL rules, and candidate budgets**. If baseline A pulls top 100 while C pulls top 5 per branch, quality conclusions will be skewed.

### 16.5. Avoiding Overfitting and Evaluating by Segment

Split a **development set** for tuning weights/chunk size/top M from a **holdout test set** for unbiased evaluation. Track segments separately:

- Exact identifiers vs. natural language.
- Accented/unaccented Vietnamese and English.
- Large/small tenants, public/private docs.
- New/old docs, product versions.
- Short/long queries, negation, multi-intent.
- Answerable queries vs. unanswerable queries.

Optimizing average nDCG while breaking exact correctness on `E11000` queries can make the product worse even as the aggregate score rises.

### 16.6. Online Evaluation

In production, you can A/B test CTR, time-to-answer, useful clicks, support ticket deflection, and human ratings. However, **click-through rate suffers from positional bias** and does not prove correctness. Combine online metrics with relevance judgments and policy checks.

## 17. Tuning Three Budgets: Retrieval, Fusion, and Rerank

A pipeline exposes parameters:

~~~text
Lexical candidate limit L = 40
Vector candidate limit V = 40
ANN numCandidates         = 400
Fusion output for rerank M = 30
Final results K           = 10
~~~

These are **reference settings for experimentation**, not ready-made optimal values. Changing one parameter impacts multiple layers.

### 17.1. Core Trade-Offs

| Increased parameter | Potential benefit | Cost / risk |
|---|---|---|
| `numCandidates` | Higher ANN recall. | Higher latency/compute. |
| Lexical top L | Captures exact-term docs deeper in list. | Larger fusion set/memory. |
| Vector top V | More semantic candidates. | Higher ANN/fusion workload. |
| Fusion top M | Gives reranker more chances to surface the right doc. | Higher inference tokens/latency/cost. |
| Final top K | User sees more evidence. | Clutter, harder UX, bloated RAG context window. |
| Title boost | Boosts navigational/exact title matches. | Keyword-stuffed titles may outrank helpful body content. |
| Semantic weight | Helps synonyms/paraphrases. | Can hurt version/code queries. |
| Lexical weight | Helps IDs/codes/exact terms. | Can miss differently worded relevant docs. |

### 17.2. Reranking Only Helps When Candidate Recall Is High Enough

If the relevant doc misses top M after fusion, no reranker—however strong—can **fix it**. When nDCG is low, diagnose which failure occurred:

- **Retrieval miss:** the right doc is absent from the lexical/vector union.
- **Fusion miss:** present in the union, but cut off below M.
- **Rerank miss:** present in top M, but demoted by the reranker.
- **Presentation miss:** present in top K, yet snippet/link/version misleads the user.

Classifying misses tells you whether to fix **indexes/analyzers/embeddings**, **weights**, the **reranker**, or the **UI**.

### 17.3. Budget Total Latency Instead of Viewing the Database in Isolation

~~~text
T_total =
  T_query_normalization
  + T_embed_query
  + T_lexical/vector_retrieval_and_fusion
  + T_rerank
  + T_format
  + T_network
~~~

This is a **sequential stage-addition budget model**. If the app runs lexical and vector **in parallel**, retrieval time tracks the slower branch plus overhead; if using MongoDB `$rankFusion`, current docs state sub-pipelines run **sequentially**, so do not assume parallel timing savings automatically. Measure real traces and tail latency.

### 17.4. Per-Layer Latency Budgets

Illustrative p95 SLO target under 300 ms:

| Stage | Illustrative budget |
|---|---:|
| Query pre-process + auth | 10 ms |
| Query embedding | 40 ms |
| Search/vector + fusion | 120 ms |
| Rerank | 100 ms |
| Format/network | 30 ms |

The 300 ms sum is **purely an illustrative budget, not a MongoDB/Voyage/model benchmark**. End-to-end p95 does not equal the naive sum of stage p95s; trace end-to-end requests under realistic workload and concurrency.

### 17.5. Adaptive Reranking

You can choose to rerank top M selectively by:

- **Query type:** rerank long/comparison questions more heavily than exact IDs.
- **Confidence:** strong exact lexical title matches may skip reranking, verified by precision measurements.
- **SLA/tier:** background research allows deeper reranking; autocomplete demands speed.
- **Cache hits:** cached query embeddings or rerank results when compliant with ACLs/versions.

When adaptive policies vary quality across user segments, check fairness/coverage and never use segmentation to bypass ACLs.

## 18. Production Operations: Indexes, Models, Costs, and Observability

Hybrid search combines **database, search indexes, embedding models, rerankers, and access control**. A single model update can shift rankings even when MongoDB query code has not changed a single line.

### 18.1. Embedding Model Version Is Data, Not Just Config

Production schemas should store:

~~~javascript
{
  _id: "DOC-100#CHUNK-02",
  embeddingModel: "embed-model-v2",
  embeddingVersion: 2,
  embeddingDim: 768,
  embedding: [/* 768 numeric values */],
  sourceRevision: 17,
  indexedAt: ISODate("2026-11-14T00:00:00Z")
}
~~~

When upgrading model v1 → v2:

1. Create separate v2 fields/indexes (e.g., `embeddingV2`, `kb_vec_v2`).
2. Backfill vectors with model v2 using checkpoints/idempotency.
3. Wait for index READY and verify vector dimensions/types.
4. Shadow query both v1 and v2; evaluate Recall/nDCG/latency/cost.
5. Switch query embeddings to model v2 **in sync** with the v2 index.
6. Retain a rollback policy and delete v1 only once SLOs hold.

**Never** mix v2 query embeddings with v1 document vectors simply because both have the same dimensionality; the two models' embedding spaces can be completely incompatible.

### 18.2. Freshness and Index Propagation

When `body` is edited, text indexes, embedding fields, and search indexes may update asynchronously at different moments. A query might see a lexical match on the new revision while semantic vectors still reflect the old revision.

Mitigations:

- Ingest/update documents with a **revision ID**.
- Regenerate embeddings when content changes (or tracked fields change).
- Set `status:"PUBLISHED"` only when indexing/embedding preconditions are met, or explicitly track and budget lag in SLOs.
- Maintain reindex/retry/dead-letter workflows for embedding failures.
- Verify final document status/ACL when required.

Never promise “real-time search” based solely on document update ACKs; verify the **Search/Vector index synchronization semantics** of your deployment.

### 18.3. Per-Stage Monitoring

| Metric | Why it matters |
|---|---|
| Lexical zero-result rate | Analyzer/keyword index/query mismatch or missing data. |
| Vector zero-result rate | Query embedding/filter/index errors or overly small candidate pool. |
| Two-branch overlap | Are branches complementary or mostly redundant? |
| Unique candidate count | Does deduplication preserve diversity? |
| ANN recall vs. ENN | Tuning `numCandidates` and index configuration. |
| Rerank inversion rate | Is the reranker moving good docs up or down too aggressively? |
| Query distribution by intent | Are code/Vietnamese/domain queries shifting? |
| P50/P95/P99 stage latency | Which endpoint—reranker or embedding—is slowing down? |
| Index build/status | Are Search indexes READY and healthy? |
| Embedding error/timeout rate | How often are fallbacks triggered? |
| Returned stale/removed docs | Index lag, ACL revocation, or freshness issues. |
| Tokens/cost per rerank | Budget consumption by top M and text length. |
| User feedback / relevance judgments | Real-world experience quality. |

### 18.4. Security-Bounded Logging

Log:

~~~javascript
{
  requestId: "SRCH-1001",
  tenantIdHash: "redacted",
  queryClass: "technical_error_code",
  pipeline: "hybrid-rrf-rerank",
  lexicalCount: 30,
  vectorCount: 30,
  uniqueCandidates: 44,
  rerankedCount: 20,
  finalCount: 10,
  embeddingModel: "embed-v2",
  vectorIndex: "kb_vec_v2",
  latencyMs: {
    embedding: 32,
    fusion: 73,
    rerank: 98
  },
  degradedMode: false
}
~~~

Numbers are **illustrative**. Avoid logging raw `query` text or full private `body` when policy forbids it. If text logging is required for quality review, enforce opt-in/consent, retention, encryption, access control, and policy-compliant deletion.

### 18.5. Caching

Useful caches include:

- **Query embedding cache** keyed by normalized query, embedding model version, and language/normalization config.
- **Lexical/vector result cache** keyed by tenant/ACL scope, index revision, filters, and query.
- **Rerank cache** keyed by model version, query, candidate IDs, **and content revision**.

Never cache a public-looking result and serve it to another tenant just because the query text matches. When permissions change or are revoked, invalidate caches or enforce TTLs compliant with policy; for sensitive data, **never treat caches as authoritative**.

### 18.6. Managing External Reranking Services

When calling a reranker model service:

- Verify **region/data residency** and data processing agreements.
- Enforce dedicated timeouts, concurrency caps, and bounded retries/backoff.
- Strip raw secrets/PII and trim document text per policy.
- Add circuit breakers and a **fusion-only** fallback.
- Account for replay/duplicate requests and per-call cost.
- Monitor model versioning/drift and Vietnamese quality.

Even with Native Reranking, review the provider/model and data-processing guarantees published by MongoDB/Atlas rather than assuming all model inference happens inside your application DB replica set.

## 19. Design Scenarios: Knowledge Search for a Technical Assistant

Suppose a system searches MongoDB developer docs divided into **public docs**, **internal team docs**, and **tenant-specific docs**, each tagged with product version and timestamp.

### 19.1. Error-Code Query

~~~text
Query: "E11000 duplicate key on upsert"

Lexical:
  exact title/body tokens -> likely finds docs mentioning the exact code

Vector:
  "unique index conflict in concurrent inserts"

Fusion:
  doc explaining E11000 + unique index gets signal from both branches

Rerank:
  ranks actionable upsert/retry steps above general theory pages
~~~

**Non-negotiable constraints:** database/version, exact error-code handling, document status, and `sourceUrl`.

### 19.2. Meaning-Based Paraphrased Query

~~~text
Query: "Why do all writes stay slow even after adding machines to the cluster?"

Lexical:
  finds "sharding", "hotspot", "monotonic shard key"

Vector:
  finds passages on "new inserts target edge chunk"

RRF:
  combines conceptual docs and practical troubleshooting guides

Rerank:
  prioritizes root-cause explanations over parameter reference tables
~~~

Here semantic search likely contributes more because the query omits the exact phrase `"monotonic shard key"`. Still, never lock in optimal weights without evaluation judgments.

### 19.3. Version-Sensitive Query

~~~text
Query: "Can MongoDB 8.0 use $scoreFusion?"

Risk:
  a MongoDB 8.3+ doc is very close semantically.

Required:
  exact version metadata/lexical signal + source status.
  Results must make clear $scoreFusion requires 8.3+,
  never presenting an 8.3 example as valid on 8.0.
~~~

Relying on vectors alone easily misses subtle version differences. This is a textbook case for **hybrid search + exact constraints**.

### 19.4. Multi-Tenant Query

~~~text
User tenant-a:
  "configure billing secret E11000"

Private document tenant-b:
  semantic score 0.99

Public doc tenant-a:
  semantic score 0.83
~~~

**Correct outcome:** Tenant B's private doc must never be selected as a candidate for Tenant A's user. Never pass it to the reranker and hide it at output. Relevance and authorization are orthogonal axes, where **authorization takes absolute priority**.

### 19.5. Unanswerable Query

If a user asks about a feature that **does not exist** in the running version, retrievers may still surface somewhat related docs. A reranker only **orders candidates**; it does not prove the question is answerable.

Implement **no-answer detection** and a threshold policy calibrated on judgments, a “no confirmed documentation found” UI state, and visible source/version metadata. Never treat `vectorScore>0.7` or `RRF>0.03` as proof of a valid answer without calibration; scores are not correctness probabilities.

## 20. Common Errors and Troubleshooting

| Symptom | Likely cause | Investigation path |
|---|---|---|
| `$rankFusion` unrecognized stage | Server < 8.0 or unsupported deployment. | Verify server/FCV/topology and feature support. |
| `$scoreFusion` unrecognized stage | Server < 8.3. | Use RRF or app-side fallback. |
| `$rerank` fails | Unsupported server/toggle/tier/model. | Check Requirements page and enable Native Reranking if eligible. |
| Vector query dimension mismatch | Query model and index field differ in dims. | Version model/index and validate vector length. |
| Query returns another tenant's doc | Missing pre-filter / ACL propagation. | Enforce filters on both lexical and vector branches. |
| Hybrid returns very few results after filter | Post-filtering top candidates or overly tight filters. | Indexed pre-filters, tune candidate budgets. |
| Lexical scores dwarf vector scores | Unscaled scores on different ranges. | Use RRF or normalized `$scoreFusion`. |
| Rerank returns wrong code/version | Model confuses identifiers. | Exact lexical, hard version filters, segment eval. |
| Newly created index fails searches | Index not READY yet or wrong mappings. | Check `$listSearchIndexes`, status, and field paths/types. |
| Vector returns irrelevant content | Model mismatch, poor chunking, low ANN recall. | Verify embedding versions, ENN, and relevance judgments. |
| Reranker fails to improve top-K | Low candidate recall or domain mismatch. | Inspect retrieval/fusion first, then rerank diagnostics. |
| Top-K filled with chunks from one article | Poor overlap/grouping configuration. | Add diversity, parent grouping, tune chunk size. |
| New documents are missing | Embedding/index lag or status filter. | Monitor reindex/backfill/READY state. |
| P99 latency spikes | Too many candidates, rerank inference/network. | Trace stages, tune L/V/M, add timeouts/caches. |
| `$rankFusion` input with `$project` fails | Sub-pipeline allows only selection/ranking stages. | Move projection after fusion. |
| Two sources in different collections won't fuse | `$rankFusion` operates on one collection. | App-side RRF, unified read model, or alternate strategy. |
| `scoreDetails` missing in output | Metadata not projected. | Project `{$meta:"scoreDetails"}` after fusion. |
| Cache returns revoked document | Cache ignores permissions/revisions. | Key by ACL, invalidate, recheck auth at output. |
| Rerank missing text field | Path absent on some documents. | Enforce schema or filter/set fallback before reranking. |
| Vector-only misses `E11000` | Semantic closeness lacks exact identifier match. | Hybrid lexical + exact-match policy. |

### 20.1. Debugging with a Single-Query Trace

~~~text
Query: "E11000 retry"
Auth scope: tenant-a PUBLIC PUBLISHED

Lexical top 30:
  15 documents, 10 relevant

Vector top 30:
  30 documents, 12 relevant

Union:
  39 unique candidates, 17 relevant

Fusion top 20:
  14 relevant

Rerank top 10:
  8 relevant
~~~

Numbers are **illustrative for error analysis**. Inspect actual document IDs and relevance labels rather than raw counts alone. A model might raise precision while dropping one essential piece of evidence; evaluate multiple KPIs and query segments.

### 20.2. Four Distinct Failure Classes

1. **Retrieval miss:** the right document never entered the lexical/vector union.
2. **Fusion miss:** present in the union, yet fell below the top-M cutoff.
3. **Rerank miss:** present in top M, yet demoted by the reranker.
4. **Output/presentation miss:** present in top K, yet missing snippets, links, versions, or authorization checks.

Fix the **right layer** instead of reflexively raising `numCandidates` or swapping in a larger model.

## 21. Practice Exercises and Solutions

Each exercise is self-contained using hypothetical data/scenarios and stated prerequisites. Where examples call MongoDB Search/Vector Search, compatible deployments and indexes are required; this text **does not claim to have executed commands** on a live cluster.

### Exercise 1 — Why Can Keyword-Only Miss Results?

**Prompt:** A user searches “how to prevent duplicate writes when multiple clients call concurrently”. The right document is titled “Unique indexes and idempotency” and never contains “duplicate writes”. What risk does keyword-only search carry?

**Answer:** It can miss the document due to different wording. Vector search can detect semantic similarity; lexical search with synonyms can also help. Hybrid search raises **candidate recall**, and reranking surfaces the document containing concrete steps.

### Exercise 2 — When Does Keyword Matter More Than Vector?

**Prompt:** The query is simply `"E11000"`, while another document mentions `"E11001"`. Which signal should take priority?

**Answer:** **Lexical/exact identifier matching** is mandatory to avoid confusing codes. Vectors can supply conceptual context but cannot replace exact constraints. Increase lexical weight or enforce exact-code filters/boosts.

### Exercise 3 — Summing Raw Scores?

**Prompt:** Lexical score is 13.2 and vector score is 0.84. Can you conclude lexical is stronger because 13.2 > 0.84?

**Answer:** No. The two retrievers have different scales and scoring semantics. Use **rank-based RRF** or score fusion with normalization/calibration. Neither score is a probability.

### Exercise 4 — How Do ANN and ENN Differ?

**Prompt:** A model produces 768-dimensional vectors and the collection has 10 million documents. Why is ANN typically used on real-time queries while ENN is used for evaluation?

**Answer:** ANN trades a bit of neighbor recall for much lower latency and compute; ENN performs exact search (within filter scope), making it valuable as a baseline. Tune `numCandidates` using ANN recall vs. ENN and latency.

### Exercise 5 — Vector Dimension Mismatch

**Prompt:** Index has `numDimensions:1536`, yet the query vector only has 768 numbers. What happens and how do you fix it?

**Answer:** Dimensions mismatch and the query is invalid. Verify the embedding model and index dimensions; use the exact same model/version for both ingestion and querying, or create a new field/index for the new model. Never zero-pad arbitrarily just to make it run.

### Exercise 6 — Hashed Identifiers vs. Embeddings

**Prompt:** A user enters product code `SKU-001`. Embeddings return `SKU-002` very closely. Should a high cosine score decide the result?

**Answer:** No. Identifiers need exact lookup/lexical matching, potentially via hard filters or a dedicated query path. Hybrid search must preserve **exact identity** rather than letting semantic similarity replace unique keys.

### Exercise 7 — Computing RRF

**Prompt:** DOC-A ranks 1st in lexical and 3rd in vector, with both weights equal to 1 and `k=60`. Compute RRF.

**Answer:** \(1/(60+1)+1/(60+3)=1/61+1/63\approx0.03227\). This is a rank-based score, not a probability of correctness.

### Exercise 8 — RRF with a Missing Branch

**Prompt:** DOC-B only ranks 2nd in vector and has no lexical hit. Is it dropped by RRF?

**Answer:** No. DOC-B receives \(w_{\text{vector}}/(60+2)\); lexical contributes zero. If DOC-B is semantically strong, it still stays in contention in the merged list.

### Exercise 9 — Weighted RRF

**Prompt:** Query `"MongoDB 8.0.10 E11000"` uses weights `lexical=0.8`, `semantic=0.2`. DOC-A has lexical rank 1 and vector rank 3. What is its score?

**Answer:** \(0.8/61 + 0.2/63 \approx 0.01629\). Raising lexical weight boosts exact token contribution, though you must measure its effect across other query categories.

### Exercise 10 — Insufficient Candidate K

**Prompt:** The right document ranks 12th in lexical and 15th in vector, while each branch returns only top 10. Can the reranker rescue it?

**Answer:** No, because the relevant doc **never entered the candidate union**. Raise lexical/vector limits, fix indexes/analyzers/embeddings, or use query expansion first; a reranker only reorders candidates it receives.

### Exercise 11 — Does MongoDB 7.0 Have `$rankFusion`?

**Prompt:** A cluster supports `$search` and `$vectorSearch` on server 7.0. Can you run the `$rankFusion` stage?

**Answer:** No per the MongoDB Manual: `$rankFusion` requires **8.0+**. You can execute two separate retrieval queries and run **RRF in the application**, or upgrade properly.

### Exercise 12 — Does MongoDB 8.0 Have `$scoreFusion`?

**Prompt:** A MongoDB 8.0 cluster runs `$rankFusion` well and you want to switch to `$scoreFusion`. Will it run immediately?

**Answer:** No. `$scoreFusion` requires **MongoDB 8.3+**. Keep using RRF or controlled app-side normalized score fusion while evaluating an upgrade.

### Exercise 13 — `$rerank` Unrecognized

**Prompt:** An Atlas cluster without Native Reranking enabled reports “unrecognized `$rerank`”. Should you switch the query to `$scoreFusion` to get semantic reranking?

**Answer:** They are not equivalent. `$scoreFusion` is **score blending**, without a query-document reranking model. Verify `$rerank` requirements/tier/version/feature toggle; if unavailable, use an **external reranker** on authorized top-M or return fusion results directly.

### Exercise 14 — Using `$project` Inside an RRF Input Pipeline

**Prompt:** A sub-pipeline:

~~~javascript
[
  { $search: { index: "kb_text_v1", text: { query: "E11000", path: "body" } } },
  { $project: { title: 1 } },
  { $limit: 20 }
]
~~~

Can you place it inside `$rankFusion.input.pipelines.lexical`?

**Answer:** No under current stage restrictions. `$project` alters the document inside an input selection pipeline. Place `$project` **after `$rankFusion`**.

### Exercise 15 — Displaying `scoreDetails`

**Prompt:** `scoreDetails:true` is set, yet the output has no `scoreDetails` field. What is wrong?

**Answer:** The stage generates **metadata**, which is not projected automatically. Project/addFields after fusion:

~~~javascript
{ $project: {
    title: 1,
    score: { $meta: "score" },
    details: { $meta: "scoreDetails" }
}}
~~~

### Exercise 16 — Deduplicating Documents Across Two Branches

**Prompt:** DOC-1 ranks 1st in lexical and 5th in vector. The API currently returns two copies of DOC-1. How do you fix it?

**Answer:** Deduplicate by stable document ID and **sum the contributions of both ranks** onto one record. Do not drop the semantic score or keep two records merely because two branches returned them separately.

### Exercise 17 — Vector Index Missing Filter Field

**Prompt:** A `$vectorSearch` pipeline uses `filter:{tenantId:"T-A"}`, yet the Vector Search index only indexes `embedding` without `tenantId` as a filter. What must be done?

**Answer:** Create or update the **Vector Search index** with `{type:"filter",path:"tenantId"}` and other filter fields, then wait for READY. Do not confuse this with a `token` field in a Search index or a B-tree index.

### Exercise 18 — Post-Filtering Causing Missing Results

**Prompt:** ANN pulls top 20 across all tenants, then `$match` for `tenant-a` leaves only 2 documents even though `tenant-a` has many relevant docs. Why?

**Answer:** Candidate budget was consumed by other tenants before filtering. Move the filter into **`$vectorSearch.filter`** and the lexical Search filter; keep a final ACL check to guard against index lag.

### Exercise 19 — Missing Rerank Path

**Prompt:** Some documents lack `body`. `$rerank` specifies `path:"body"` and throws an error. Why, and how do you resolve it?

**Answer:** The reranker requires the specified field to exist on input documents. Filter out docs missing `body` via `$match` or set fallback text via `$set` before reranking if policy permits. Never feed null or objects into a text field or ignore schema warnings.

### Exercise 20 — Does Rerank Overwrite the Fusion Score?

**Prompt:** After `$rerank`, `{$meta:"score"}` shows the reranker score rather than RRF. How can you preserve both?

**Answer:** Materialize the pre-rerank score into a field first:

~~~javascript
{ $addFields: { fusionScore: { $meta: "score" } } },
{ $rerank: {
    query: { text: "E11000" },
    path: ["title", "body"],
    numDocsToRerank: 20,
    model: "rerank-2.5-lite"
}},
{ $addFields: { rerankScore: { $meta: "score" } } }
~~~

Requires MongoDB/feature-toggle/model support. `fusionScore` is captured before reranking overwrites `score` metadata.

### Exercise 21 — Sending Private Documents to an External Reranker

**Prompt:** A service mixes Tenant B's private DOC-005 into the candidate list, calls an external model, and drops it from the final output. Is that safe?

**Answer:** **No.** Even if the user never sees it in output, private content left its authorized boundary. Pre-filter in both branches, verify authorization, and send only permitted content to approved providers. Never rely on downstream filtering as an ACL substitute.

### Exercise 22 — One Document with Many Chunks

**Prompt:** The UI displays at most 5 **articles**, yet top-5 hybrid results contain 4 chunks from the same DOC-1. What should you do?

**Answer:** Consider **grouping by `parentDocumentId` after retrieval/reranking**, selecting representative chunk(s), enforcing diversity, and linking to exact sections. Avoid discarding same-parent chunks before fusion if needed evidence would be lost; evaluate at parent-level relevance.

### Exercise 23 — Does the Rerank Model Support Vietnamese?

**Prompt:** The system is mostly Vietnamese, while the rerank model is tuned for English. Can you assume it improves top-10 results?

**Answer:** No. Build a judgment set with accented/unaccented Vietnamese, technical acronyms, and multilingual queries; compare rerank vs. RRF-only. If it fails to help or latency is too high, use a multilingual model or disable reranking for that query segment.

### Exercise 24 — Exact Version Query

**Prompt:** User asks `"Does MongoDB 8.0 support scoreFusion yet?"`. Vector search returns the `$scoreFusion` 8.3 documentation page. How do you prevent a wrong answer?

**Answer:** Include **version metadata and exact lexical evidence** in retrieval/reranking and check release requirements; `$scoreFusion` requires 8.3+, not 8.0. Never let semantic similarity override version constraints.

### Exercise 25 — Query with No Valid Answer

**Prompt:** Both lexical and vector always return a few loosely related documents even when asking about a nonexistent API. Should you force the LLM to answer from them?

**Answer:** No. Implement a calibrated **no-answer/insufficient-evidence policy** backed by judgments; show “no confirming source found” alongside related docs with caveats. Raw `vectorScore`/RRF is not answer probability.

### Exercise 26 — Choosing `numCandidates`

**Prompt:** ANN recall trails ENN with `numCandidates:40` and `limit:20`. What should you test?

**Answer:** Increase `numCandidates` methodically while measuring ANN Recall@20 and p95 latency; also inspect filter selectivity, index health, embeddings, and candidate limits. Never assume 1000 is always better if latency/cost breaches SLOs.

### Exercise 27 — `$rankFusion` Across Two Different Collections

**Prompt:** Keyword search queries `kb_articles` and vector search queries `kb_chunks`; you want to combine them directly in one `$rankFusion`. Does that work?

**Answer:** No, `$rankFusion` requires sub-pipelines on **the same collection**. Either build a unified normalized search collection/index, or run two separate queries with app-side RRF using chunk↔parent mapping and aligned ACLs.

### Exercise 28 — Score vs. Performance

**Prompt:** Before reranking, p95 is 120 ms; adding a rerank model raises p95 to 450 ms while nDCG@10 rises only 0.2 percentage points. What should you do?

**Answer:** Weigh the gain against SLOs and cost: reduce M, try a lighter model, add caching, apply selective reranking to hard queries only, or turn reranking off. Never assume reranking must stay enabled just because it is an “advanced” stage.

### Exercise 29 — Recovering After a Model Upgrade

**Prompt:** A team upgraded its embedding model from 768 to 1024 dimensions. Query code still hits the 768 index and starts failing. What is the fix procedure?

**Answer:** Create a **new 1024-dimensional embedding field/index**, backfill the corpus and wait for READY, generate query embeddings from the new model, shadow-evaluate, roll out behind a feature flag, and keep rollback ready. Never pad or truncate raw vectors to fit the old index.

### Exercise 30 — `scoreFusion` and Normalization

**Prompt:** One branch emits BM25 scores in 2–50 and the other emits vector scores in 0.7–0.9. What is the risk of `normalization:"none"` with averaging?

**Answer:** Lexical raw scores will dominate due to scale. Use `sigmoid`/`minMaxScaler` or proper calibration, inspect score distributions and relevance; RRF may be an easier baseline to control.

### Exercise 31 — Exact-ID-Only Queries

**Prompt:** An API has `GET /docs/DOC-001`, yet a developer runs a vector search for `"DOC-001"` to fetch the document. Is that sensible?

**Answer:** No. That is a **point lookup** by primary ID; use `findOne({_id:"DOC-001"})` with authorization. Hybrid search is for discovery/relevance, not replacing exact key lookups.

### Exercise 32 — Disallowed Stage in Input Pipeline

**Prompt:** Inside `$rankFusion.input.pipelines.lexical`, a developer adds `$lookup` to join an owner table before fusion. Why can this fail?

**Answer:** `$rankFusion` supports only a restricted set of selection/ranking stages, not full aggregation pipelines. Perform joins/enrichment after fusion or in the application, enforcing ACL/tenant checks and top-K bounds.

### Exercise 33 — Querying Immediately After Index Creation

**Prompt:** `createSearchIndex` returns an index name; the very next query reports the index is not ready. Did `createIndex` fail?

**Answer:** Not necessarily. Search index builds and syncs are **asynchronous**. Check `$listSearchIndexes` for READY status, path definitions, and errors; never route traffic via feature flags before the index is ready.

### Exercise 34 — Computing Recall@K

**Prompt:** Judgments identify 5 relevant docs for Q1. Hybrid top-10 contains 4 of them. What is Recall@10?

**Answer:** \(4/5=0.8\). With 4 relevant out of 10 results, Precision@10 = \(4/10=0.4\). The two metrics measure different things: **coverage** versus **top-result cleanliness**.

### Exercise 35 — MRR When the First Relevant Hit Is 4th

**Prompt:** For one query, the first relevant document sits at rank 4. What is its reciprocal rank?

**Answer:** \(1/4=0.25\). **MRR** averages reciprocal ranks across **many queries**, not a single Q1.

### Exercise 36 — Same Query, Different Tenants

**Prompt:** Tenant-a and tenant-b search the exact same string `"E11000"`. The system caches results keyed solely by query text. What is the risk?

**Answer:** The cache can return unauthorized documents or the wrong corpus. Cache keys must incorporate **authorization scope, tenant, filters, index/model version, and data revision**; for sensitive data, recheck permissions before returning output and never use cache as authority.

### Exercise 37 — High-Scoring Stale Document

**Prompt:** A MongoDB 6.0 article ranks #1 across lexical/vector/rerank for an 8.3 question. Should you solve this by raising top M?

**Answer:** Do not just raise top M. Add **productVersion/effectiveDate/status filters**, manage freshness/rerank evidence, and surface provenance. Scores only measure relative relevance, not release applicability.

### Exercise 38 — Redundant Signals

**Prompt:** A pipeline has lexical title boosting, a separate lexical title-only branch, and a semantic title-embedding branch, yet nDCG fails to improve. Why?

**Answer:** Multiple branches may be **double-counting** the same title signal, crowding out body evidence. Run branch ablations, inspect overlap and query segments, and drop branches that add no real value.

### Exercise 39 — Combining Lexical, Vector, and Rerank for RAG

**Prompt:** Design a pipeline returning 5 sourced chunks for `"difference between updateOne and transactions when reserving multiple SKUs"` in a multi-tenant knowledge base.

**Suggested answer:**

1. Resolve tenant/ACL from the auth context and classify query intent.
2. Generate the query embedding with the matching model/index version.
3. `$search` title/body for top 40 with tenant/status/version filters.
4. `$vectorSearch` for top 40 with the **exact same** policy filters.
5. `$rankFusion` RRF (8.0+) or app-side RRF over stable chunk IDs.
6. Take top 20–30 candidate chunks; run semantic rerank if model/latency permit.
7. Group/diversify by parent while preserving evidence passages and `sourceUrl`.
8. Run final ACL/authorization check and return top 5 chunks + provenance.
9. Track Recall@40, nDCG@5, p95 latency, no-answer quality, and exposure=0.

### Exercise 40 — A Production Rollout Plan

**Prompt:** A team already has stable keyword search and wants to add vectors + reranker across two releases. Outline steps to measure gains and preserve rollback.

**Suggested answer:**

1. Build a judgment set covering exact IDs, natural queries, Vietnamese, versions, and ACLs.
2. Select an embedding model, generate doc/chunk vectors, and store model/version metadata.
3. Create the Vector Search index and filter fields, wait for READY, and measure ANN recall vs. ENN.
4. Shadow-compare keyword-only vs. vector-only vs. RRF without changing user-visible results yet.
5. Roll out hybrid fusion behind a feature flag/canary, tracking p95/p99 and error rates.
6. Evaluate reranking over authorized top-M, privacy/cost, and native feature support.
7. Enable reranking selectively; A/B test top-K relevance and SLOs.
8. Keep lexical-only/fusion-only fallbacks and rollback capability to old indexes/models.
9. Monitor index freshness, embedding failures, ACL exposure, and online feedback.
10. Never declare rollout a success merely because scores look higher; verify quality and reliability KPIs.

## 22. Official MongoDB Documentation and Further Reading

When working with hybrid search, **syntax and limits change across MongoDB Server versions, search deployment types, Atlas feature flags, and model availability**. The pages below are official references; always choose the branch matching your running cluster. This lesson reflects capabilities as of Nov 2026 and does not replace verification on your actual deployment.

### 22.1. Hybrid Retrieval and Fusion

1. [How to Perform Hybrid Search — MongoDB Vector Search](https://www.mongodb.com/docs/vector-search/hybrid-search/hybrid-search-overview/) — explains RRF, relative score fusion, weights, and hybrid sub-pipeline restrictions.
2. [`$rankFusion` (aggregation)](https://www.mongodb.com/docs/manual/reference/operator/aggregation/rankfusion/) — syntax for `input.pipelines`, `combination.weights`, RRF \(k=60\), `scoreDetails`, and stage restrictions; MongoDB 8.0+.
3. [`$scoreFusion` (aggregation)](https://www.mongodb.com/docs/manual/reference/operator/aggregation/scorefusion/) — `none`/`sigmoid`/`minMaxScaler` normalization, weights/combination, score metadata; MongoDB 8.3+.
4. [Combine Multiple `$vectorSearch` Queries](https://www.mongodb.com/docs/vector-search/hybrid-search/vector-search-with-rankfusion/) — combining multiple vector pipelines, weights examples, and `scoreDetails`.
5. [`$score` Aggregation Stage](https://www.mongodb.com/docs/manual/reference/operator/aggregation/score/) — computing/normalizing scores in certain `$scoreFusion` scenarios and pipelines lacking built-in scores.

### 22.2. Lexical Search and Vector Search

6. [MongoDB Search Overview](https://www.mongodb.com/docs/atlas/atlas-search/) — inverted-index search, analyzers, operators, and scoring.
7. [`$search` Aggregation Stage](https://www.mongodb.com/docs/atlas/atlas-search/aggregation-stages/search/) — Search stage syntax.
8. [MongoDB Search `text` Operator](https://www.mongodb.com/docs/atlas/atlas-search/text/) — text search, analyzer matching, and scoring.
9. [MongoDB Search `compound` Operator](https://www.mongodb.com/docs/atlas/atlas-search/compound/) — `must`/`should`/`filter` and boosting.
10. [Run ANN and ENN Vector Search Queries](https://www.mongodb.com/docs/vector-search/query/aggregation-stages/vector-search-stage/) — `$vectorSearch`, `numCandidates`, `limit`, `exact`, `filter`, and version requirements.
11. [`vectorSearch` MongoDB Search Operator](https://www.mongodb.com/docs/atlas/atlas-search/operators-collectors/vectorsearch/) — vector search inside `$search` with advanced Search prefilters.
12. [Create Search Indexes with `createSearchIndex`](https://www.mongodb.com/docs/manual/reference/method/db.collection.createsearchindex/) — Search index and vectorSearch index definitions.
13. [`updateSearchIndex`](https://www.mongodb.com/docs/manual/reference/method/db.collection.updatesearchindex/) — rebuilding indexes, readiness, and updating definitions.
14. [Improve Vector Search Accuracy](https://www.mongodb.com/docs/vector-search/query/improve-accuracy/) — ANN vs. ENN, recall, and reranking.

### 22.3. Reranking and Operations

15. [`$rerank` Aggregation Pipeline Stage](https://www.mongodb.com/docs/vector-search/query/aggregation-stages/rerank/) — syntax, native models, deployment requirements, semantic rerank score, and limits.
16. [MongoDB Vector Search Troubleshooting](https://www.mongodb.com/docs/vector-search/troubleshooting/) — vector query errors, rerank memory limits, and operational diagnostics.
17. [Atlas Project Settings — Native Reranking](https://www.mongodb.com/docs/atlas/tutorial/manage-project-settings/) — enabling/disabling and controlling Native Reranking in Atlas.
18. [Java Sync Driver — MongoDB Search](https://www.mongodb.com/docs/drivers/java/sync/current/atlas-search/) — `Aggregate`/Search/Vector examples and Java APIs.
19. [`$listSearchIndexes`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/listSearchIndexes/) — inspecting Search index definitions and status.
20. [MongoDB 8.2 Compatibility Changes](https://www.mongodb.com/docs/manual/release-notes/8.2-compatibility/) — upgrade changes, such as `$rankFusion` on views.

**Important note when checking docs:** An overview page may cite general availability milestones differently from **a new stage's dedicated Requirements page**, because docs, models, and tiers evolve across releases. For `$rerank`, always check the **stage-specific Requirements page** and Atlas project model status before deploying—do not assume MongoDB 8.3 suffices just because `$scoreFusion` arrived in that release.

### 22.4. Checklist Questions When Reading Docs

Before copying any pipeline:

1. Which server version is the cluster running, and does it support MongoDB Search/Vector Search?
2. Is the index name exact and is the index READY?
3. Are `$rankFusion`, `$scoreFusion`, and `$rerank` supported in this deployment?
4. Are you using the `$vectorSearch` aggregation stage or the `vectorSearch` operator inside `$search`?
5. Do all input pipelines use valid stages and target the same collection?
6. Do sub-pipelines preserve original documents up to fusion?
7. Are tenant/ACL/status filters placed **before the retrieval cutoff** in both branches?
8. Are raw scores normalized if using score fusion?
9. Do query embeddings match the model version and `numDimensions`?
10. Does the rerank model meet language, cost, and data residency requirements?

## 23. Conclusion

**Combining keyword search, vector search, and reranking** is a multi-signal coordination strategy, not a single query operator. **Keyword search** preserves exact precision on names, error codes, versions, and phrases; **vector search** captures paraphrased and synonymous intent; **fusion** merges and ranks candidate lists; and a **reranker** can elevate top-result quality by reading query–document pairs closely.

In MongoDB, `$search` and `$vectorSearch` form the two branches. **`$rankFusion` (8.0+)** provides a solid RRF baseline; **`$scoreFusion` (8.3+)** supports blending normalized scores; **`$rerank`** is a separate capability whose version, feature toggle, model, tier, and region must be verified on its Requirements page. Where native fusion/rerank is unavailable, the application can still implement **RRF and reranking**, provided lists, scores, ACLs, and latency are properly managed.

Good design balances three principles: **finding the right evidence** (candidate recall), **putting useful evidence first** (ranking quality), and **never violating access permissions, freshness, or SLOs**. Start from keyword and vector baselines, measure Recall@K, MRR/nDCG, and p95/p99, and add complexity only when gains are proven. **No BM25, cosine, RRF, or reranker score can substitute for accurate source data, authorized filtering, and evaluation against real user needs.**
