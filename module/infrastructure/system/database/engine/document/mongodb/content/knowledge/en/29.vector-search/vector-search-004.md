# Vector Indexes, Similarity Metrics, and Search Parameter Selection in MongoDB

## 1. Objectives and Context

A user asks: **“How do I recover my account if I lose my authenticator device?”** The right document might be titled **“Recovering Two-Factor Authentication”**, even though the question does not match all exact words in the title. Keyword search only solves part of this problem; vector search retrieves content that is **close in semantic representation**.

MongoDB Vector Search uses **embedding vectors**—arrays of numbers representing text, images, or other objects. MongoDB indexes vectors and finds those closest to a query vector under a chosen **similarity metric**.

This lesson belongs to the **Vector Search** chapter in the **Database Engine Document MongoDB** module, covering **Vector Indexes, Similarity Metrics, and Search Parameter Selection**.

After completing this lesson, you will be able to:

1. Explain embeddings, vector dimensions, and embedding model compatibility.
2. Create a MongoDB Vector Search index of type `vectorSearch`.
3. Compare `cosine`, `dotProduct`, and `euclidean`.
4. Run queries using the `$vectorSearch` aggregation stage.
5. Distinguish ANN (*Approximate Nearest Neighbors*) and ENN (*Exact Nearest Neighbors*).
6. Choose `limit` and `numCandidates` according to the recall–latency trade-off.
7. Declare metadata `filter` fields and apply tenant/permission pre-filtering.
8. Interpret `vectorSearchScore` without mistaking scores for accuracy probabilities.
9. Understand dimension limits, quantization, and HNSW/flat indexing.
10. Evaluate ANN against ENN using recall@k and p95 latency measurements.
11. Organize chunk data, embedding versions, and index lifecycles.
12. Write mongosh and Java Sync Driver examples for a retrieval/RAG system.

**Core principle:** A shared embedding space, matching vector dimensions, an appropriate metric, permission-safe filtering, and benchmarked ANN parameters are essential for reliable vector search. Never treat a high `score` as proof that a document is factually right or that the user is authorized to read it.

> **Lesson scope:** Examples use **BYO embeddings** (*Bring Your Own Embeddings*): the application generates or provides vectors, stores them in MongoDB, and builds an index with field type `vector`. MongoDB's automated embedding modes (*Automated Embedding*) use different index/query syntax and are distinguished to avoid confusion.

## 2. From Raw Data to Embedding Vectors

An embedding is an array of numbers:

~~~javascript
[0.12, -0.43, 0.08, 0.95]
~~~

This is a 4-dimensional vector; real embeddings typically have hundreds or thousands of dimensions. Coordinates are learned by the model and do not correspond by default to explicit labels like “price” or “password”.

~~~text
Document content                 User question
      |                                  |
      v                                  v
Embedding model M                 Embedding model M
      |                                  |
      v                                  v
Document embedding                 Query embedding
      |                                  |
      v                                  |
 MongoDB collection                      |
      |                                  |
      v                                  v
 Vector Search index  ------>  $vectorSearch
                                        |
                                        v
                                 Top-k documents
~~~

### 2.1. Same Model Is a Key Requirement

If documents are embedded with model M1 while queries use an incompatible model M2, vector distance no longer accurately reflects similarity. Even if M1 and M2 both have 1,536 dimensions, their coordinate systems can be completely different.

A query vector must be generated using the same model/version—or a verified compatible mechanism—as the vectors stored in the index.

### 2.2. Using a Single Collection to Store Embeddings

~~~javascript
{
  _id: "doc-001",
  tenantId: "tenant-A",
  title: "Password recovery",
  content: "Use backup codes or the verification workflow...",
  embedding: [0.96, 0.17, 0.04],
  embeddingModel: "toy-3d-v1",
  published: true
}
~~~

The advantage is storing metadata, text, and vectors together in one document. The drawback is that large embeddings increase storage size and bandwidth if the entire document is returned.

### 2.3. When Should a Long Document Be Split into Chunks?

For multi-page documents, a single vector for the whole document tends to blur multiple topics together. You can split it into **chunks**:

~~~javascript
{
  _id: "doc-001:chunk-03",
  documentId: "doc-001",
  chunkIndex: 3,
  tenantId: "tenant-A",
  content: "How to reissue backup codes...",
  embedding: [/* ... */],
  embeddingModel: "embedding-v1"
}
~~~

Chunking improves passage-level retrieval accuracy at the expense of higher vector counts, index size, and cost. Balance chunk size, overlap, and potential context loss.

### 2.4. Three-Dimensional Vectors in This Lesson Are Simulated Data

For clarity, we define three **illustrative** axes:

~~~text
Dimension 1: account / sign-in
Dimension 2: billing / payment
Dimension 3: device
~~~

For example:

~~~javascript
[0.99, 0.08, 0.03] // Primarily account-related.
[0.02, 0.99, 0.02] // Primarily billing-related.
[0.04, 0.08, 0.99] // Primarily device-related.
~~~

These are not outputs of a trained embedding model and do not prove the system understands Vietnamese. Production must use real, separately evaluated embeddings.

## 3. Vector Search Indexes Differ from B-Tree Indexes

In MongoDB, distinguish:

| Index type | How created/defined | Used for |
|---|---|---|
| Ordinary B-tree | `createIndex({tenantId:1})` | Equality, range, sort |
| Native text index | `createIndex({content:"text"})` | `$text` and textScore |
| MongoDB Search index | `createSearchIndex(...,"search",...)` | `$search` lexical/advanced |
| MongoDB Vector Search index | `createSearchIndex(...,"vectorSearch",...)` | `$vectorSearch` nearest neighbor |

A command like:

~~~javascript
db.knowledgeChunks.createIndex({ embedding: 1 });
~~~

does **not** create a Vector Search index. That is a regular MongoDB index, not the nearest-neighbor structure used by `$vectorSearch`.

### 3.1. Search Indexes Are a Separate Component

A MongoDB Vector Search index is managed and synchronized by the deployment's search infrastructure. Therefore, a lag can occur between:

~~~text
insertOne succeeds
        |
        v
document readable via find()
        |
        v
Search index ingests/syncs document
        |
        v
document becomes returnable by $vectorSearch
~~~

Never promise that `$vectorSearch` immediately sees every write right after `insertOne` returns success.

### 3.2. Environment Requirements

You need a MongoDB deployment with **Vector Search** enabled and supporting this index type, such as a compatible Atlas deployment. MongoDB also supports dedicated local/self-managed configurations in newer versions, but you cannot assume every default standalone Community MongoDB install includes full search services.

Before practicing:

1. Confirm the deployment supports Vector Search.
2. Ensure privileges to create search indexes.
3. Use a compatible mongosh/driver.
4. Create the index with the right type and wait until it is queryable/READY.
5. Never run DDL on production just for a demo.

## 4. Three Key Similarity Metrics

MongoDB Vector Search supports:

~~~text
cosine
dotProduct
euclidean
~~~

Each metric measures closeness differently.

### 4.1. Cosine Similarity

Cosine measures the **angle** between two nonzero vectors:

\[
\operatorname{cosine}(a,b)=
\frac{\sum_{i=1}^{d}a_i b_i}
{\sqrt{\sum_{i=1}^{d}a_i^2}
 \sqrt{\sum_{i=1}^{d}b_i^2}}
\]

Example:

~~~text
a = [1,0]
b = [2,0]

cosine(a,b)=1 because they point in the same direction.
~~~

Cosine is typically suitable when embedding direction is the primary semantic signal and magnitude should not dictate similarity.

**Never use zero vectors** with cosine because a zero norm makes the denominator undefined.

### 4.2. Dot Product

Dot product:

\[
a\cdot b=\sum_{i=1}^{d}a_i b_i
\]

Example:

~~~text
a = [1,0]
b = [2,0]
dotProduct(a,b) = 2
~~~

Dot product is affected by magnitude. When two vectors are normalized to unit length (*unit-normalized*), dot product mathematically equals cosine.

For **BYO** embeddings, MongoDB documentation requires vectors to be unit-length normalized at **index time** and **query time** when choosing `dotProduct`. Never mix unnormalized vectors with this metric.

### 4.3. Euclidean Distance

Euclidean is geometric distance:

\[
d(a,b)=\sqrt{\sum_{i=1}^{d}(a_i-b_i)^2}
\]

Example:

~~~text
a = [1,0]
b = [2,0]
euclidean(a,b)=1
~~~

A **smaller** distance means two vectors are closer under Euclidean.

### 4.4. Comparison Table

| Metric | Meaning | Magnitude | Key constraint |
|---|---|---|---|
| `cosine` | Angle between vectors | Unaffected when collinear | No zero vectors |
| `dotProduct` | Inner product | Affected if unnormalized | BYO must be unit-normalized |
| `euclidean` | Geometric distance | Affected | Smaller means closer |

No single metric is best for all systems. Choose based on the embedding model and empirical evaluation. Some models recommend dot product, others cosine.

### 4.5. Same Direction, Different Distances

~~~text
O ---> A=[1,0] ----> B=[2,0]

Cosine:     A and B point in the same direction.
DotProduct: depends on length.
Euclidean:  distance A-B is nonzero.
~~~

## 5. `vectorSearchScore` Is Normalized by MongoDB

In `$vectorSearch`, MongoDB returns `vectorSearchScore` metadata in the range **0 to 1**; larger values indicate higher similarity within that metric/query.

~~~javascript
{
  $project: {
    title: 1,
    score: { $meta: "vectorSearchScore" }
  }
}
~~~

**A score of 0.93 does not mean a 93% probability that the answer is right.** It is a ranking score that depends on the metric, embedding model, index, and query.

### 5.1. Cosine Normalization Formula

\[
score_{cosine}=\frac{1+\operatorname{cosine}(a,b)}{2}
\]

| Raw cosine | Score |
|---:|---:|
| -1 | 0 |
| 0 | 0.5 |
| 0.6 | 0.8 |
| 1 | 1 |

### 5.2. Euclidean Normalization Formula

\[
score_{euclidean}=\frac{1}{1+d(a,b)}
\]

If distance=0 then score=1. If distance=3 then score=0.25.

### 5.3. Normalized Dot Product Score

For normalized vectors, dot product lies in [-1,1]:

\[
score_{dot}=\frac{1+\operatorname{dotProduct}(a,b)}{2}
\]

Thus, the unit-length normalization requirement affects not only performance but also score semantics.

### 5.4. Do Not Compare Scores Arbitrarily Across Indexes or Models

A score of 0.86 from model A/cosine index is not inherently equivalent to 0.86 from model B/Euclidean index or a reranker. If you need a threshold, calibrate it on your own application's queries and ground truth.

## 6. Choosing `numDimensions`

A vector index needs to know the dimensionality:

~~~javascript
{
  type: "vector",
  path: "embedding",
  numDimensions: 3,
  similarity: "cosine"
}
~~~

If the index has `numDimensions:3`, then:

~~~javascript
queryVector: [1, 0, 0]    // Valid.
queryVector: [1, 0]       // Wrong dimensions.
queryVector: [1, 0, 0, 0] // Wrong dimensions.
~~~

Verify:

- Does every document have vectors with the right dimensionality?
- Does the query vector have the right dimensionality?
- Does any document use a newer model version with different dimensions?
- Are there any NaN/Infinity or zero vectors?
- Are BSON/numeric types appropriate?

### 6.1. The 8,192-Dimension Limit

MongoDB Vector Search currently supports up to **8,192 dimensions** for corresponding vector/quantization types. For certain `int1` BinData types or binary quantization, dimensions must be a **multiple of 8**. Automated Embedding has its own supported dimension tiers.

Do not apply a single limit to every ingestion/indexing method without checking documentation for the exact version.

### 6.2. Choose Model and Dimensions by Quality, Not Highest Number

A 3,072-dimensional vector does not automatically search better than a 1,024-dimensional vector. Evaluate quality, embedding cost, index RAM/storage, and latency.

## 7. Hands-On Data: Eight Simulated Documents

The 3-dimensional vectors below are crafted manually for easy observation; **they do not represent real semantic embeddings**.

Run on a deployment with MongoDB Vector Search:

~~~javascript
use vector_search_lab
~~~

Insert test documents:

~~~javascript
const sampleDocuments = [
  {
    _id: "A-001",
    tenantId: "tenant-A",
    published: true,
    category: "account",
    title: "Account password recovery",
    content: "Steps to regain access to your account.",
    embedding: [0.99, 0.08, 0.03],
    embeddingModel: "toy-3d-v1"
  },
  {
    _id: "A-002",
    tenantId: "tenant-A",
    published: true,
    category: "account",
    title: "Enable two-factor authentication",
    content: "Authenticator apps and backup recovery codes.",
    embedding: [0.93, 0.30, 0.03],
    embeddingModel: "toy-3d-v1"
  },
  {
    _id: "A-003",
    tenantId: "tenant-A",
    published: true,
    category: "billing",
    title: "Invoice payment",
    content: "Information about payment methods.",
    embedding: [0.02, 0.99, 0.02],
    embeddingModel: "toy-3d-v1"
  },
  {
    _id: "A-004",
    tenantId: "tenant-A",
    published: true,
    category: "device",
    title: "Connect sensor",
    content: "How to register a new IoT device.",
    embedding: [0.04, 0.08, 0.99],
    embeddingModel: "toy-3d-v1"
  },
  {
    _id: "B-001",
    tenantId: "tenant-B",
    published: true,
    category: "account",
    title: "Tenant B account recovery",
    content: "Restore access for tenant B.",
    embedding: [0.98, 0.12, 0.03],
    embeddingModel: "toy-3d-v1"
  },
  {
    _id: "A-005",
    tenantId: "tenant-A",
    published: false,
    category: "account",
    title: "Account lock - draft",
    content: "Unpublished document.",
    embedding: [0.92, 0.20, 0.10],
    embeddingModel: "toy-3d-v1"
  },
  {
    _id: "A-006",
    tenantId: "tenant-A",
    published: true,
    category: "billing",
    title: "Change payment method",
    content: "Update your payment card.",
    embedding: [0.16, 0.96, 0.09],
    embeddingModel: "toy-3d-v1"
  },
  {
    _id: "A-007",
    tenantId: "tenant-A",
    published: true,
    category: "account",
    title: "Manage access tokens",
    content: "Create, revoke, and rotate tokens.",
    embedding: [0.80, 0.51, 0.08],
    embeddingModel: "toy-3d-v1"
  }
];

db.knowledgeChunks.insertMany(sampleDocuments);
~~~

On a fresh, empty collection:

- There are 8 documents.
- Tenant-A has 7 documents (6 published and 1 unpublished).
- Tenant-B has 1 document.
- Every embedding has 3 dimensions and is nonzero.
- Every document has `embeddingModel:"toy-3d-v1"`.

Verify:

~~~javascript
db.knowledgeChunks.countDocuments({});
db.knowledgeChunks.find(
  {},
  { _id: 1, tenantId: 1, published: 1, title: 1 }
).sort({ _id: 1 });
~~~

**Do not** re-run the insert on an already populated collection if you want to avoid duplicate `_id` errors. Expected results in this lesson assume no leftover data from prior runs or external writes.

## 8. Creating a Vector Search Index

Create an index with the vector field and metadata filters:

~~~javascript
db.knowledgeChunks.createSearchIndex(
  "embedding_v1",
  "vectorSearch",
  {
    fields: [
      {
        type: "vector",
        path: "embedding",
        numDimensions: 3,
        similarity: "cosine"
      },
      { type: "filter", path: "tenantId" },
      { type: "filter", path: "published" },
      { type: "filter", path: "category" },
      { type: "filter", path: "embeddingModel" }
    ]
  }
);
~~~

| Field | Role |
|---|---|
| `"embedding_v1"` | Search index name referenced by queries |
| `"vectorSearch"` | Search index type |
| `type:"vector"` | Defines the field holding vectors |
| `path:"embedding"` | Vector field in the document |
| `numDimensions:3` | Vector size |
| `similarity:"cosine"` | Similarity metric |
| `type:"filter"` | Metadata field for pre-filtering before vector retrieval |

### 8.1. Filter Indexes Differ from B-Tree Indexes

An ordinary index:

~~~javascript
db.knowledgeChunks.createIndex({ tenantId: 1 });
~~~

may work well for `find()` queries, but **does not replace** `type:"filter",path:"tenantId"` inside a Vector Search index. `$vectorSearch.filter` queries require metadata fields indexed via Vector Search.

### 8.2. Asynchronous Index Builds

After creating the search index, wait for the ready state:

~~~javascript
db.knowledgeChunks.getSearchIndexes();
~~~

Or:

~~~javascript
db.knowledgeChunks.getSearchIndexes("embedding_v1");
~~~

Depending on the version, results may contain `status:"READY"` or `queryable:true`. Never assume `createSearchIndex()` returning success means all indexing work finished immediately.

### 8.3. Index Name Differs from Path

~~~javascript
index: "embedding_v1"  // Search index name.
path: "embedding"      // Vector array field.
~~~

Do not confuse these two values.

### 8.4. Documents Without Valid Vectors

If a document lacks `embedding` or has the wrong dimensionality, it cannot participate in retrieval as a valid 3-dimensional vector. Monitor embedding ingest completeness rather than equating insert success with being indexed.

## 9. Running Your First `$vectorSearch`

Once `embedding_v1` is ready:

~~~javascript
const q = [1.0, 0.0, 0.0];

db.knowledgeChunks.aggregate([
  {
    $vectorSearch: {
      index: "embedding_v1",
      path: "embedding",
      queryVector: q,
      numCandidates: 100,
      limit: 3
    }
  },
  {
    $project: {
      _id: 1,
      title: 1,
      category: 1,
      tenantId: 1,
      score: { $meta: "vectorSearchScore" }
    }
  }
]);
~~~

This is an **ANN search** because `exact:true` is not set.

### 9.1. Parameter Reference

| Property | Meaning |
|---|---|
| `index` | Vector Search index name |
| `path` | Indexed vector field |
| `queryVector` | Query vector in the same embedding space |
| `numCandidates` | ANN candidate search breadth |
| `limit` | Maximum documents returned from vector retrieval |
| `$meta:"vectorSearchScore"` | Similarity ranking score |

### 9.2. Interpreting Results

The query `[1,0,0]` points toward account topics, so account documents tend to receive higher cosine scores than billing/device documents with our simulated vectors.

Because ANN is approximate, do not claim all clusters/indexes will return the exact same ID ordering in every situation.

### 9.3. Mandatory First Stage

`$vectorSearch` must be the **first stage** of any pipeline containing it. Never place `$match` before it:

~~~javascript
// Wrong:
db.knowledgeChunks.aggregate([
  { $match: { tenantId: "tenant-A" } },
  {
    $vectorSearch: {
      index: "embedding_v1",
      path: "embedding",
      queryVector: q,
      numCandidates: 100,
      limit: 3
    }
  }
]);
~~~

To scope the corpus before retrieval, use `filter` **inside** `$vectorSearch`.

## 10. ANN: Fast but Approximate

Approximate Nearest Neighbors finds points near the query **without comparing against every** indexed embedding.

MongoDB uses **HNSW (Hierarchical Navigable Small Worlds)** as its graph algorithm for ANN. The graph links nearby vectors so traversal homes in on relevant regions.

~~~text
Query embedding
      |
      v
Traverse HNSW graph
      |
      v
Collect nearby candidates
      |
      v
Rank by similarity
      |
      v
Return top-k
~~~

### 10.1. Why Can ANN Miss a True Nearest Neighbor?

Suppose ENN finds the exact top-5:

~~~text
[A, B, C, D, E]
~~~

ANN might return:

~~~text
[A, B, C, D, F]
~~~

ANN missed E and placed F into the top-k even though E's distance is better. This is the speed-versus-recall trade-off.

### 10.2. Role of `numCandidates`

`numCandidates` controls candidate exploration breadth in ANN:

- **Smaller:** usually faster, with higher risk of missing neighbors.
- **Larger:** usually raises recall, potentially increasing latency/CPU.
- Must not be smaller than `limit`.
- Under current documentation, the maximum value is **10,000**.

It is **not** the number of results returned to the user; `limit` determines the maximum result count.

### 10.3. The 20 × `limit` Heuristic

MongoDB recommends starting with:

~~~text
numCandidates >= 20 * limit
~~~

For example:

| limit | Starting numCandidates |
|---:|---:|
| 5 | 100 |
| 10 | 200 |
| 20 | 400 |
| 50 | 1,000 |

This is a **starting point**, not a guarantee of 95% recall. Test against your real corpus and queries.

### 10.4. When to Increase `numCandidates`?

- ANN misses true nearest neighbors compared to ENN.
- Many vectors sit very close together.
- The index uses quantization that reduces precision.
- Filters have high selectivity.
- The search corpus grows substantially.
- Recall requirements outweigh current latency savings.

Measure quality and latency after each step; do not set it to 10,000 merely thinking “bigger is better”.

## 11. ENN: Finding Exact Nearest Neighbors

Exact Nearest Neighbors computes nearest neighbors via exhaustive comparison across matching indexed vectors rather than approximate ANN traversal.

~~~javascript
db.knowledgeChunks.aggregate([
  {
    $vectorSearch: {
      index: "embedding_v1",
      path: "embedding",
      queryVector: [1, 0, 0],
      exact: true,
      limit: 3
    }
  },
  {
    $project: {
      title: 1,
      score: { $meta: "vectorSearchScore" }
    }
  }
]);
~~~

### 11.1. How Do ANN and ENN Differ?

| Criterion | ANN | ENN |
|---|---|---|
| Query config | `numCandidates`, `limit` | `exact:true`, `limit` |
| Method | Approximate graph traversal | Exhaustive nearest neighbor |
| Recall vs. true top-k | Can be below 100% | Ground truth for indexed vectors/metric |
| Large-set cost | Usually lower | Usually higher |
| Role | Real-time queries on large corpora | Benchmarking / small / high-selectivity sets |

### 11.2. Do Not Pass `numCandidates` in ENN Queries

`numCandidates` governs ANN; ENN uses `exact:true` and does not need a candidate budget parameter.

### 11.3. ENN Does Not Guarantee “Semantically Right” Documents

ENN is exact **with respect to vector distance**, which does not prove the embedding model understood the question. If the model is weak or data is skewed, ENN still returns unhelpful nearest neighbors.

## 12. Pre-Filtering by Metadata

A multi-tenant system must ensure searches only cover documents the user is allowed to view.

~~~javascript
db.knowledgeChunks.aggregate([
  {
    $vectorSearch: {
      index: "embedding_v1",
      path: "embedding",
      queryVector: [1, 0, 0],
      numCandidates: 100,
      limit: 3,
      filter: {
        tenantId: "tenant-A",
        published: true
      }
    }
  },
  {
    $project: {
      title: 1,
      tenantId: 1,
      published: 1,
      score: { $meta: "vectorSearchScore" }
    }
  }
]);
~~~

Here, tenant-B and unpublished documents are excluded from the candidate pool the application wants to retrieve from.

### 12.1. Filter Fields Must Be Indexed First

In the Vector Search index we have:

~~~javascript
{ type: "filter", path: "tenantId" }
{ type: "filter", path: "published" }
~~~

If missing, `filter:{tenantId:...}` queries may be invalid.

### 12.2. Pre-Filter and Post-Filter Are Not Equivalent

Pre-filter:

~~~javascript
{
  $vectorSearch: {
    // Other fields unchanged.
    filter: {
      tenantId: "tenant-A",
      published: true
    }
  }
}
~~~

Post-filter:

~~~javascript
[
  { $vectorSearch: { /* parameters */ } },
  { $match: { tenantId: "tenant-A", published: true } }
]
~~~

If vector retrieval takes the top-10 **across the whole corpus** and post-filtering leaves only one tenant-A result, the application never sees the other tenant-A documents ranked 11, 12, ... Filtering afterward can return fewer than `limit` results and drop relevant neighbors within the user's scope.

### 12.3. Pre-Filtering Still Has a Cost

Highly selective filters can make ANN traversal costly and hurt recall if candidates are sparse. Benchmark ENN or flat indexing when the post-filter subset is small.

### 12.4. Filter Data Types

MongoDB Vector Search supports pre-filtering fields typed as Boolean, Date, ObjectId, numeric, String, UUID, and arrays of supported types. Only a **subset** of MQL operators work inside `filter`, such as equality, `$in`, and supported range comparisons.

Do not assume `$regex` or arbitrary aggregation expressions work inside `filter`.

### 12.5. Adding `category`

~~~javascript
filter: {
  tenantId: "tenant-A",
  published: true,
  category: { $in: ["account", "billing"] }
}
~~~

Remember to declare `category` with type `filter` in the index, as done in our dataset setup.

## 13. Tenant and ACL as a Security Boundary

The application must never trust a user-supplied `tenantId`:

~~~javascript
// Not safe:
const tenantId = request.query.tenantId;
~~~

The API layer must resolve tenant/role/ACL from the authenticated identity and inject those restrictions before retrieval.

~~~text
User request
      |
      v
Authentication + Authorization
      |
      v
Resolve allowed tenant / ACL
      |
      v
$vectorSearch.filter
      |
      v
Only authorized documents
      |
      v
Optional reranker / LLM
~~~

Never filter tenant only after sending unauthorized results to a reranker or LLM. When document permissions change, audit search index sync, caches, and source fetching.

### 13.1. Why Can Retrieval Leak Data?

An LLM can weave unauthorized document contents into its answer if retrieval handed them over. Similarity scores do not replace access control.

### 13.2. Permission Filtering Also Applies When Fetching Source Documents

If a vector result contains `documentId` and the application fetches the document from another collection, that fetch step must also verify permissions; never treat a vector hit as proof that access is still valid.

## 14. Projecting and Filtering `vectorSearchScore`

To retrieve the score:

~~~javascript
db.knowledgeChunks.aggregate([
  {
    $vectorSearch: {
      index: "embedding_v1",
      path: "embedding",
      queryVector: [1, 0, 0],
      numCandidates: 100,
      limit: 10
    }
  },
  {
    $project: {
      title: 1,
      score: { $meta: "vectorSearchScore" }
    }
  }
]);
~~~

Score is **query-time metadata**, not a persisted field in the document.

### 14.1. Post-Filtering by Score

~~~javascript
db.knowledgeChunks.aggregate([
  {
    $vectorSearch: {
      index: "embedding_v1",
      path: "embedding",
      queryVector: [1, 0, 0],
      numCandidates: 100,
      limit: 20,
      filter: {
        tenantId: "tenant-A",
        published: true
      }
    }
  },
  {
    $addFields: {
      score: { $meta: "vectorSearchScore" }
    }
  },
  {
    $match: {
      score: { $gte: 0.85 }
    }
  },
  {
    $project: {
      embedding: 0
    }
  }
]);
~~~

The `0.85` value is **purely illustrative**. Never adopt a universal threshold across models/indexes because normalized scores are not probabilities.

### 14.2. No Score Without Running Vector Search

~~~javascript
db.knowledgeChunks.find({
  score: { $gte: 0.85 }
});
~~~

has no retrieval meaning for a new query vector unless you explicitly stored a score for one fixed query in the document. Scores change whenever the query vector changes.

## 15. Tuning `numCandidates`: Recall and Latency

Suppose an endpoint returns **10 results**:

~~~text
Example target SLO:
p95 latency < 250ms
recall@10 >= 0.92 vs. ENN
~~~

These are example application targets, not quality levels guaranteed by MongoDB.

Test configurations:

| Configuration | limit | numCandidates |
|---|---:|---:|
| Fast | 10 | 50 |
| Moderate | 10 | 100 |
| 20× baseline | 10 | 200 |
| Broader | 10 | 400 |
| Very broad | 10 | 1,000 |

Run the same query/filter on a representative corpus:

~~~javascript
const q = [1, 0, 0];

function searchWithCandidates(n) {
  return db.knowledgeChunks.aggregate([
    {
      $vectorSearch: {
        index: "embedding_v1",
        path: "embedding",
        queryVector: q,
        numCandidates: n,
        limit: 5,
        filter: {
          tenantId: "tenant-A",
          published: true
        }
      }
    },
    {
      $project: {
        _id: 1,
        title: 1,
        score: { $meta: "vectorSearchScore" }
      }
    }
  ]).toArray();
}

printjson(searchWithCandidates(100));
~~~

On an 8-document lab, changing candidate counts is insufficient to evaluate production latency or recall. You need a realistic large corpus and query distribution.

### 15.1. Increasing Candidates Does Not Always Yield Proportional Gains

Going from 50 to 200 may boost recall substantially, whereas going from 2,000 to 4,000 can add far more latency than recall improvement. Pick the sweet spot from benchmark curves.

### 15.2. Filtered Queries Require Separate Benchmarking

ANN top-k with a tenant-A filter can behave very differently from unfiltered cluster-wide ANN top-k. Measure across selectivity bands rather than a single unfiltered query.

### 15.3. Result Count Can Be Less Than `limit`

Reasons include few matching documents after filtering, missing/invalid vectors, unsynchronized index state, or downstream post-filtering. `limit` is a **maximum**, not a guarantee of always returning that many documents.

## 16. Recall@k: Measuring ANN Quality Against ENN

Given ENN top-5:

~~~text
[A, B, C, D, E]
~~~

and ANN top-5:

~~~text
[A, B, C, F, G]
~~~

There are 3 overlapping IDs, so:

\[
recall@5=\frac{|ANN@5\cap ENN@5|}{5}=\frac35=0.6
\]

This is **nearest-neighbor recall**, which is not the same as human-judged content precision.

### 16.1. mongosh Example

~~~javascript
const q = [1, 0, 0];

function searchIds(exact, candidates, limit) {
  const stage = {
    index: "embedding_v1",
    path: "embedding",
    queryVector: q,
    limit: limit,
    filter: {
      tenantId: "tenant-A",
      published: true
    }
  };

  if (exact) {
    stage.exact = true;
  } else {
    stage.numCandidates = candidates;
  }

  return db.knowledgeChunks.aggregate([
    { $vectorSearch: stage },
    { $project: { _id: 1 } }
  ]).toArray().map(item => String(item._id));
}

const exactIds = searchIds(true, null, 5);
const annIds = searchIds(false, 100, 5);

const groundTruth = new Set(exactIds);
const hits = annIds.filter(id => groundTruth.has(id)).length;

printjson({
  exactIds,
  annIds,
  hits,
  recallAt5: hits / exactIds.length
});
~~~

If ENN returns 0 documents, handle the zero-denominator case in a general benchmark harness.

### 16.2. Conditions for a Fair Comparison

- Identical query vector.
- Identical filters, tenant, and ACLs.
- Identical indexed corpus and embedding version.
- Identical metric.
- Identical `limit`.
- No significant data or index changes between the two queries.

### 16.3. Additional Metrics

| Metric | What it evaluates |
|---|---|
| Recall@k vs. ENN | Whether ANN misses true nearest neighbors |
| Precision@k from labels | How many returned results are useful |
| NDCG@k | Quality of ranking order |
| MRR | Position of the first useful result |
| p50/p95/p99 latency | Speed experience |
| Cost/query | CPU/RAM/Search Nodes cost |
| Freshness lag | How slowly new data appears in the index |

If ANN has high recall against ENN yet the embedding model misunderstands the question, the product can still fail. Evaluate retrieval relevance using real labels.

## 17. Quantization and Resource Trade-Offs

A 1,536-dimensional float32 vector takes roughly:

~~~text
1536 * 4 bytes = 6144 bytes
~~~

for raw numeric payload alone, excluding BSON overhead or index structures.

MongoDB Vector Search offers ways to reduce precision/index RAM depending on mode and version:

- **float:** high fidelity, higher RAM/storage cost.
- **scalar quantization:** uses fewer bits (typically int8-equivalent) for the index.
- **binary quantization:** compresses down to very few bits per dimension, optionally rescoring with full vectors depending on mode.
- **binaryNoRescore:** an option in Automated Embedding mode on supported deployments; trades potential accuracy drop for speed/resource savings.

### 17.1. Scalar Quantization Example

You can test with a separate index name:

~~~javascript
db.knowledgeChunks.createSearchIndex(
  "embedding_scalar_v1",
  "vectorSearch",
  {
    fields: [
      {
        type: "vector",
        path: "embedding",
        numDimensions: 3,
        similarity: "cosine",
        quantization: "scalar"
      },
      { type: "filter", path: "tenantId" },
      { type: "filter", path: "published" }
    ]
  }
);
~~~

Check driver/server compatibility and vector types. With binary quantization, dimension constraints such as **multiples of 8** may apply.

### 17.2. Why Can Quantization Reduce Recall?

Lowering precision makes vectors that were originally distinct harder to differentiate, especially for closely clustered scores. Compare against a **float ENN baseline** on a representative dataset.

### 17.3. Proper Evaluation

Using the same queries/filters and corpus:

1. Float ENN as ground truth.
2. Float ANN with tuned `numCandidates`.
3. Scalar ANN.
4. Binary ANN if supported.
5. Compare recall, p95, index size/RAM, and build time.

**Note:** Compressing the search index does not automatically shrink the embedding field stored inside BSON documents. To optimize total storage, evaluate storage formats/types separately.

## 18. HNSW, Flat Indexing, and Choosing Between Them

HNSW suits large-corpus ANN using a proximity graph of nearby points.

In newer versions supporting `indexingMethod`:

~~~javascript
{
  type: "vector",
  path: "embedding",
  numDimensions: 3,
  similarity: "cosine",
  indexingMethod: "hnsw"
}
~~~

Some deployments also offer `"flat"`.

### 18.1. When to Choose HNSW?

- Large corpus.
- Queries are not overly narrowed by pre-filters.
- Need low latency with sufficiently high recall.
- Can afford graph index build and maintenance costs.

### 18.2. When to Try Flat or ENN?

- Post-filter result sets are very small—for example, a user has only 100 chunks.
- The use case prioritizes full recall.
- Small/medium datasets.
- Tight filters render HNSW graph traversal inefficient.

Flat indexing was introduced on newer deployments, so verify availability. Never assume every MongoDB version supports every `indexingMethod` value.

### 18.3. Should You Tune HNSW Graph Parameters?

Options like `hnswOptions.maxEdges` and `hnswOptions.numEdgeCandidates` affect graph construction and resource consumption. Start with defaults; only tune graph settings if recall remains inadequate on a large index after tuning query `numCandidates`.

## 19. Optimizing Pre-Filters and Tenant Partitioning

A filter index may declare:

~~~javascript
{ type: "filter", path: "tenantId" }
{ type: "filter", path: "published" }
{ type: "filter", path: "category" }
~~~

Query:

~~~javascript
filter: {
  tenantId: "tenant-A",
  published: true,
  category: "account"
}
~~~

If an application holds 10 million vectors yet each tenant owns only a few hundred documents, **selectivity is very high**. ANN graph traversal may not be optimal; test ENN or flat indexing and measure empirically.

### 19.1. Adding a Date Range

If documents have a Date-typed `createdAt`, declare:

~~~javascript
{ type: "filter", path: "createdAt" }
~~~

Then:

~~~javascript
filter: {
  tenantId: "tenant-A",
  createdAt: {
    $gte: ISODate("2026-01-01T00:00:00Z")
  }
}
~~~

Apply this only if the field exists with the right type and those filter operators are supported by your version.

### 19.2. Too Many Filters Also Have a Cost

Every indexed filter field consumes index resources. Add only fields with real business/query value; do not add the entire document schema to the filter index without reason.

## 20. Managing Score Thresholds and Ranking

An endpoint might retrieve top-20 and keep only chunks with `score >= 0.85`, yet **0.85 is not a universal threshold**.

Calibrate according to:

- Embedding model and score distribution.
- Cosine / dotProduct / Euclidean.
- Query type and corpus.
- Quantization.
- Precision/recall requirements.
- Real user behavior.

### 20.1. Never Add Lexical Scores and Vector Scores Directly

If text search returns score=8.3 and `vectorSearchScore`=0.86, adding them raw is semantically invalid because their scales differ.

### 20.2. RRF — Reciprocal Rank Fusion

A hybrid search approach using ranks:

\[
RRF(d)=\sum_{r \in rankers}\frac{1}{k+rank_r(d)}
\]

where `k` is the RRF smoothing constant, not Vector Search's `limit`.

RRF combines rankings from lexical and vector branches without assuming the two scores share units.

### 20.3. Reranking

You can retrieve 50 chunks, run a reranker scoring query + content, and select 8 chunks for the LLM. This boosts precision at the cost of extra latency, expense, and data privacy checks.

## 21. Hybrid Search: When Semantic Alone Is Not Enough

Vector search may return on-topic content while missing exact characters in:

- Error codes like `ERR-4012`.
- SKUs like `INV-1234`.
- Person or company names.
- Contract numbers.
- Phrases requiring near-verbatim matches.

Diagram:

~~~text
                 Query
                   |
            +------+------+
            |             |
            v             v
         Lexical        Vector
          Search         Search
            |             |
            +------+------+
                   |
              Rank fusion
                   |
                   v
               Top results
~~~

Native `$text`, MongoDB Search `$search`, and `$vectorSearch` are distinct mechanisms. Do not treat them as sharing one index or having directly addable similarity scores.

## 22. RAG — Retrieval-Augmented Generation

A common RAG pipeline:

~~~text
User question
     |
     v
Authenticate / resolve tenant and ACL
     |
     v
Embedding model generates query vector
     |
     v
$vectorSearch + pre-filter
     |
     v
Top-k chunks + scores
     |
     v
Optional rerank / dedup / fetch source
     |
     v
LLM receives only authorized context
     |
     v
Answer + source citations
~~~

### 22.1. Search Top-k Differs from Context Top-k

For example:

~~~text
Vector search limit: 40
Reranker keeps: 10
LLM consumes: 6
~~~

No single `limit` is ideal for every application. Short queries, long queries, duplicate documents, and synthesis answers have different recall/cost profiles.

### 22.2. High Vector Score Does Not Guarantee a Grounded Answer

A high-scoring chunk may be on-topic yet lack the specific fact needed to answer. Evaluate citation accuracy, hallucination rates, and “insufficient evidence” handling.

### 22.3. RAG Still Faces Injection and Authorization Risks

Never execute instructions embedded in retrieved text. Source content is untrusted data, never a system instruction. Only pass context the user is authorized to view.

## 23. Embedding Migration and Index Versioning

A new model can change:

- Dimensionality.
- Normalization.
- Recommended metric.
- Vietnamese/multilingual quality.
- Embedding cost/latency.
- Score distribution.

Store:

~~~javascript
{
  _id: "doc-001",
  embedding: [/* vector */],
  embeddingModel: "model-v1",
  embeddingVersion: 1,
  updatedAt: ISODate("2026-11-14T08:00:00Z")
}
~~~

### 23.1. Do Not Mix Two Models in the Same Embedding Field

If half the corpus uses M1 and the other half uses M2 while queries always use M2, rankings can break even when dimensions match.

### 23.2. Dual-Embeddings Approach

~~~javascript
{
  embeddingV1: [/* vector M1 */],
  embeddingV2: [/* vector M2 */]
}
~~~

Create two indexes on the two paths. Then:

1. Backfill `embeddingV2`.
2. Wait for `indexV2` to reach READY.
3. Query with model M2 against `indexV2`.
4. Compare recall/relevance and p95 against pipeline M1.
5. Shift traffic incrementally.
6. Retain a rollback plan before deleting M1.

### 23.3. What If the New Model Changes Dimensions?

Create a new path/index with the model's exact `numDimensions`. Never alter an existing index's dimensionality leaving mixed old and new vectors uncontrolled.

## 24. Freshness, Index Readiness, and Failures

A document may be visible to `find()` before appearing in `$vectorSearch` due to asynchronous index syncing.

### 24.1. Practical Ingest Workflow

1. Validate content/tenant/ACL.
2. Split into chunks if needed.
3. Generate embeddings with consistent model/version.
4. Validate dimensions and numeric validity.
5. Insert/upsert documents/chunks.
6. Monitor search index synchronization state.
7. Mark searchable only when a clear consistency contract is met.
8. Use bounded retry/backoff if the search index is not ready.
9. When sources are deleted or edited, update chunks and permissions accordingly.

### 24.2. Why Not Retry Indefinitely?

If the index is building, hammering `$vectorSearch` at high rate only increases load. APIs should surface indexing status or apply bounded retries, backoff, circuit breakers, or fallbacks per SLA.

### 24.3. Error Categories to Distinguish

| Scenario | Handling |
|---|---|
| Index does not exist | Check index name/type/rollout |
| Index not queryable yet | Monitor build/READY state |
| Vector dimension mismatch | Validation error, do not retry blindly |
| Filter field not indexed | Update index definition |
| Query timeout | Throttle load, inspect candidates and performance |
| Search overload | Backpressure and bounded retries |
| Zero results after filter | Can be a valid empty result |
| Results missing newly written doc | Check index freshness |
| Irrelevant rankings | Evaluate model/metric/chunking |
| Cross-tenant document returned | Security incident requiring immediate remediation |

## 25. Optimizing Bandwidth with Projection

Most APIs only need title, content, ID, and score—not long vectors:

~~~javascript
db.knowledgeChunks.aggregate([
  {
    $vectorSearch: {
      index: "embedding_v1",
      path: "embedding",
      queryVector: [1, 0, 0],
      numCandidates: 100,
      limit: 5,
      filter: {
        tenantId: "tenant-A",
        published: true
      }
    }
  },
  {
    $project: {
      _id: 1,
      title: 1,
      content: 1,
      category: 1,
      score: { $meta: "vectorSearchScore" }
    }
  }
]);
~~~

This inclusion projection omits the `embedding` field, saving bandwidth and avoiding exposing unnecessary data to clients.

### 25.1. Raw Storage Estimate

With 1 million 1,536-dimensional float32 embeddings:

~~~text
1,000,000 * 1536 * 4 = 6,144,000,000 bytes
~~~

This is strictly **raw numeric payload**, excluding BSON, index graphs, redundancy, other search indexes, or caches. Never use this calculation in place of real infrastructure sizing.

### 25.2. Many Chunks Multiply Vector Count

100,000 documents with 30 chunks each:

~~~text
100000 * 30 = 3,000,000 vectors
~~~

Fine-grained chunking aids precision but raises cost. Deduplicate repeated chunks and remove old versions when documents update.

## 26. Java Sync Driver: ANN Queries

The Java Sync Driver can submit a raw `$vectorSearch` aggregation stage via `Document`, keeping syntax explicit without tying you to a specific builder helper.

Assuming `client` is a connected `MongoClient` against a Vector Search cluster with a READY index:

~~~java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import org.bson.Document;
import org.bson.conversions.Bson;

import java.util.Arrays;
import java.util.List;

MongoDatabase database =
    client.getDatabase("vector_search_lab");

MongoCollection<Document> chunks =
    database.getCollection("knowledgeChunks");

List<Double> queryVector = Arrays.asList(
    1.0, 0.0, 0.0
);

Bson searchStage = new Document("$vectorSearch",
    new Document("index", "embedding_v1")
        .append("path", "embedding")
        .append("queryVector", queryVector)
        .append("numCandidates", 100)
        .append("limit", 5)
        .append("filter",
            new Document("tenantId", "tenant-A")
                .append("published", true)
        )
);

Bson projectionStage = new Document("$project",
    new Document("_id", 1)
        .append("title", 1)
        .append("category", 1)
        .append("score",
            new Document("$meta", "vectorSearchScore")
        )
);

for (Document doc : chunks.aggregate(
        Arrays.asList(searchStage, projectionStage))) {
    System.out.println(doc.toJson());
}
~~~

### 26.1. Query Vector Is a Numeric Array

Use `List<Double>` rather than a string `"[1,0,0]"`. For BSON vector subtype/BinData formats, use compatible codec/driver APIs—never pack arrays into arbitrary bytes manually.

### 26.2. Use Real Embeddings in Production

In real applications, never use manual `[1,0,0]` vectors. The backend must generate query embeddings with the same model as the corpus, check dimensions, and pass only valid vectors to MongoDB.

### 26.3. ENN in Java

~~~java
Bson exactStage = new Document("$vectorSearch",
    new Document("index", "embedding_v1")
        .append("path", "embedding")
        .append("queryVector", queryVector)
        .append("exact", true)
        .append("limit", 5)
);
~~~

ENN uses `exact:true` and does not need `numCandidates`.

### 26.4. Deadlines and Errors

In production, configure timeouts/deadlines on `AggregateIterable`/driver and collect metrics. Never swallow all exceptions into an empty list; distinguish missing indexes, invalid dimensions, timeouts, and overload.

## 27. Creating a Vector Search Index in Java

You can use driver helper methods for search index management if supported by your version, or issue the raw `createSearchIndexes` command.

Raw BSON command example:

~~~java
import org.bson.Document;
import java.util.Arrays;

Document definition = new Document("fields",
    Arrays.asList(
        new Document("type", "vector")
            .append("path", "embedding")
            .append("numDimensions", 3)
            .append("similarity", "cosine"),
        new Document("type", "filter")
            .append("path", "tenantId"),
        new Document("type", "filter")
            .append("path", "published")
    )
);

Document command = new Document(
        "createSearchIndexes", "knowledgeChunks")
    .append("indexes", Arrays.asList(
        new Document("name", "embedding_v1")
            .append("type", "vectorSearch")
            .append("definition", definition)
    ));

database.runCommand(command);
~~~

Run this only when the deployment/driver supports the command, the index does not yet exist, and you have permissions. Index creation is asynchronous; check READY before querying.

**Do not confuse:** `chunks.createIndex(new Document("embedding",1))` creates an ordinary index, not a Vector Search index.

## 28. Compass and Atlas UI

Inspection workflow:

1. Connect to the Atlas cluster or deployment with Vector Search.
2. Open the `vector_search_lab` database.
3. Open the `knowledgeChunks` collection.
4. Create index `embedding_v1` of type Vector Search.
5. Set path `embedding`, numDimensions 3, similarity cosine.
6. Add filter fields `tenantId` and `published`.
7. Wait for the index to reach READY/queryable.
8. Open Aggregations and place `$vectorSearch` as the first stage.
9. Test ANN `numCandidates=100`/`limit=3`.
10. Test ENN `exact=true`/`limit=3`.
11. Project `vectorSearchScore` and compare results.
12. Apply the `tenant-A`/`published` filter and compare remaining doc counts.

UIs evolve across versions; if Compass does not expose a newer option, use mongosh or the JSON editor. Never rely on old UI screenshots to conclude an API is unsupported.

## 29. Constraints on `$vectorSearch` in Aggregation

- `$vectorSearch` must be the **first** stage in any pipeline where it appears.
- Cannot be placed inside a `$facet` pipeline.
- Cannot be used inside a `$lookup` sub-pipeline; where supported, you can join **after** vector search returns results.
- Filters inside `$vectorSearch` only support operators and data types specified in documentation.
- `index` name must match a `vectorSearch`-type index, and `path` must be an indexed vector field.
- Never use `$meta:"textScore"` in place of `"vectorSearchScore"`.
- Support on views depends on server version; do not assume support on older deployments.
- Nested vectors, flat indexing, and Automated Embedding must be verified against version-specific docs.

Invalid example:

~~~javascript
db.knowledgeChunks.aggregate([
  {
    $facet: {
      semantic: [
        {
          $vectorSearch: {
            index: "embedding_v1",
            path: "embedding",
            queryVector: [1, 0, 0],
            numCandidates: 100,
            limit: 3
          }
        }
      ]
    }
  }
]);
~~~

For hybrid or multi-branch search, consider separate pipelines, version-supported fusion stages, or merging in the application layer.

## 30. Workload-Based Design Examples

### 30.1. Internal Knowledge Search

~~~text
Corpus: 2 million chunks
Filter: tenant + published
limit: 10
SLO: low latency, sufficiently high recall
~~~

Start with HNSW ANN `numCandidates:200`, then compare 100, 400, and 800 against an ENN baseline and p95 latency.

### 30.2. Querying a Small Subset After ACLs

~~~text
Cluster-wide corpus: 5 million vectors
After user filter: 120 vectors
limit: 10
~~~

ENN or flat indexing (if supported by your version) is worth testing since the subset is tiny, though still measure empirically.

### 30.3. Legal Review

High recall requirements (avoid missing documents): increase retrieval breadth, test ENN, combine with exact keyword search and manual review. Never use a vector score to certify a document as “legally irrelevant”.

### 30.4. E-Commerce

Filters require `inStock`/`category`/`store`, while vector search ranks semantically within valid products. Re-check stock, price, and permissions before display or checkout because the search index can lag.

### 30.5. Customer Support RAG

ANN limit=30–50, reranker keeps 5–10 chunks, LLM receives referenced sources. Benchmark end-to-end latency covering embedding time + retrieval + reranking + generation.

## 31. Common Misconceptions and Errors

| Symptom | Cause | Resolution |
|---|---|---|
| `$vectorSearch` does not work | Deployment lacks support | Verify Search/Vector Search service |
| “Index not found” | Wrong name, type, or still building | Inspect `getSearchIndexes` |
| `find` sees doc, vector search doesn't | Search index sync lag | Wait for READY/sync, use appropriate fallback |
| 2D query vector, 3D index | Wrong `numDimensions` | Validate before sending |
| Cosine with zero vector | Norm is 0 | Block zero vectors |
| `dotProduct` with unnormalized BYO | Contract/similarity violation | Normalize to unit length |
| ANN missing `numCandidates` | Required field omitted | Specify `numCandidates` |
| `numCandidates < limit` | Invalid | Adjust values |
| `numCandidates > 10000` | Exceeds limit | Adjust or paginate differently |
| `exact:true` paired with ANN logic | Confusing ENN/ANN | Remove candidate tuning |
| `$match` before `$vectorSearch` | Invalid stage position | Use pre-filter |
| Tenant filter not indexed | Missing `filter` type | Add filter field to index |
| Fewer results than `limit` | Small filtered set, missing vectors, post-filter | Check completeness and filters |
| Post-filter drops too many results | Global top-k picked across all data | Pre-filter within scope |
| Score 0.9 yet wrong answer | Score is not probability | Human eval / rerank |
| Mixed model versions | Vectors from different spaces | Dual indexing / versioning |
| Quantization drops recall | Loss of precision | Compare against float ENN baseline |
| p95 spikes | High candidates, tight filters, load | Benchmark, test flat/ENN, scale |
| Index too large | High dims, many chunks, HNSW overhead | Quantization, data lifecycle |
| API leaks other tenant's data | Missing ACL | Enforce checks before retrieval/LLM |
| Directly comparing vector and text scores | Different scales | Rank fusion / normalization |
| Overload errors | Infrastructure saturated | Backpressure, bounded retries |
| Cannot retrieve score | Used `textScore` or omitted projection | Project `vectorSearchScore` |
| Created B-tree index on embedding | Wrong index type | Create `vectorSearch` search index |
| Query embedding from a new model | Space mismatch with index | Keep model versions aligned |
| Returning full vector field to client | Omitted projection | Project only needed fields |

## 32. Practice Exercises

Exercises use collection `vector_search_lab.knowledgeChunks` and index `embedding_v1` unless stated otherwise. Never create or drop indexes on production for exercises.

### Exercise 1 — Vector Dimensions

Index `numDimensions:3`. Which query is valid?

~~~javascript
[1,0,0]
[1,0]
[1,0,0,0]
~~~

**Answer:** Only the 3-dimensional vector.

### Exercise 2 — Cosine / Dot / Euclidean Differences

Given a=[1,0], b=[2,0]. Compute all three metrics and explain the difference regarding magnitude.

### Exercise 3 — Zero Vector

Why is `[0,0,0]` unsuitable for cosine?

### Exercise 4 — Create Index

Create a 3-dimensional `vectorSearch` index on path `embedding`, cosine similarity, with `tenantId`/`published` filters.

### Exercise 5 — ANN

Write `$vectorSearch` with q=[1,0,0], limit=5, numCandidates=100, and projection for title and score.

### Exercise 6 — ENN

Write an `exact:true`, limit=5 query. Why is `numCandidates` not needed?

### Exercise 7 — `numCandidates` Bounds

Is `limit:10,numCandidates:8` valid? Why or why not?

### Exercise 8 — 20× Heuristic

Given `limit=20`, propose a starting `numCandidates` and explain why benchmarking is still required.

### Exercise 9 — Pre-Filter

Return only published documents for `tenant-A`. Which filter must appear and what must the index declare?

### Exercise 10 — Post-Filter Dropping Top-k

Global ANN returns 10 results, leaving 1 after filtering for `tenant-A`. Why isn't simply running `limit:10` sufficient?

### Exercise 11 — `vectorSearchScore`

Is a score of 0.85 an 85% probability of being correct? Why or why not?

### Exercise 12 — Cosine Normalization

What normalized score does `cosine=0.6` yield?

**Answer:** 0.8.

### Exercise 13 — Euclidean Normalization

What score does `distance=3` yield?

**Answer:** 0.25.

### Exercise 14 — Dot Product

Why must BYO vectors using `dotProduct` be normalized? At norm 1, how does dot product relate to cosine?

### Exercise 15 — Recall@5

ENN returns [A,B,C,D,E] and ANN returns [A,C,E,F,G]. What is Recall@5?

**Answer:** 0.6.

### Exercise 16 — Benchmark ANN

On a large corpus, run `numCandidates=50/100/200/400`. Compare recall@k against ENN and p95 latency.

### Exercise 17 — Quantization

Why does scalar quantization save RAM yet potentially change top-k? What is the right baseline?

### Exercise 18 — 8,192 Dimensions

If a model outputs 10,000 dimensions, can it be stored in an index capped at 8,192? What choice must change?

### Exercise 19 — Model Version

Two models both have 1,536 dimensions from different training runs. Why must their vectors never be mixed?

### Exercise 20 — Chunking

When should long documents be split? What is the trade-off among retrieval precision, context loss, and index size?

### Exercise 21 — Freshness

Why can `find()` read a newly inserted document while `$vectorSearch` does not return it yet? What should the UI communicate?

### Exercise 22 — Java ANN

Use `new Document("$vectorSearch",...)` with `numCandidates`/`limit` and a `$project` for score.

### Exercise 23 — Java ENN

Convert the Java ANN example to `exact=true`. Which field must be removed?

### Exercise 24 — Flat vs. HNSW

5 million vectors, where each user sees only 100 vectors. Why might flat/ENN be worth testing, yet not always the automatic winner?

### Exercise 25 — Hybrid

Error code `ERR-4012` needs an exact match. Why can vector-only search miss it? Propose lexical + vector + RRF.

### Exercise 26 — ACL

A `tenant-A` user asks about a topic where `tenant-B` has a high-scoring document. What must the query enforce before handing chunks to the LLM?

### Exercise 27 — Threshold

Why cannot a threshold of 0.85 be reused across every model and metric?

### Exercise 28 — Cost

Calculate the raw numeric size of 100,000 1,536-dimensional float32 vectors.

**Hint:** 100000 × 1536 × 4 bytes.

### Exercise 29 — Index Not Ready

A request times out while an index is building. Should you retry infinitely or use status checks and backoff? Why?

### Exercise 30 — End-to-End Design

Design a multi-tenant RAG system covering source docs, chunks, embedding versions, vector index/filters, ANN/ENN tuning, score thresholds, hybrid/reranking, ACLs, index freshness, and recall evaluation.

## 33. Quick Decision Table

| Goal | Initial choice | What to verify |
|---|---|---|
| Semantic search on large corpus | HNSW ANN | Recall, latency |
| Very few vectors after filter | ENN/flat if supported | Query performance |
| Top-10 results | `limit:10` | Filter scope |
| Initial candidate breadth | `numCandidates:200` | Recall@10 |
| Ground-truth benchmark | `exact:true` | Same corpus/filters |
| Unit-normalized model | DotProduct/cosine per model | Training metric |
| Unnormalized vectors | Cosine/Euclidean per model | Avoid misusing dot |
| Multi-tenant security | Tenant/ACL pre-filter | Indexed filter fields |
| RAM savings | Scalar/binary quantization | Recall and index size |
| Exact code matching | Hybrid lexical+vector | Fusion quality |
| New model rollout | Dual fields/indexes | Dimensions and rollback |
| Newly inserted doc missing | Monitor Search index sync | Index readiness |
| Multilingual RAG | Multilingual embedding model | Vietnamese relevance |
| Score threshold | Calibrate on data | Precision/recall |

## 34. Production Checklist

### Embeddings and Data

- [ ] Document/query embeddings use the same compatible model and version.
- [ ] All vectors have exact dimensions and valid numeric types.
- [ ] No NaN/Infinity, and no zero vectors when disallowed by the metric.
- [ ] If using BYO `dotProduct`, vectors are unit-length normalized.
- [ ] Representative test data exists for Vietnamese or target multilingual queries.
- [ ] Chunking, deduplication, and versioning lifecycles are in place.
- [ ] Incompatible embedding spaces are never mixed silently.

### Index

- [ ] Index type is `vectorSearch`, not B-tree.
- [ ] `path`, `numDimensions`, and `similarity` are exact.
- [ ] Index is READY/queryable.
- [ ] Tenant/ACL/status filter fields are indexed with `type:"filter"`.
- [ ] Quantization/`indexingMethod` has been benchmarked if used.
- [ ] Metrics exist for index size, sync lag, load, and build time.
- [ ] Rollback plan exists for model/index changes.

### Queries

- [ ] `$vectorSearch` is the first stage.
- [ ] ANN sets `numCandidates >= limit` within allowed bounds.
- [ ] ENN uses `exact:true`.
- [ ] `limit` suits the data and UX.
- [ ] Permission pre-filters are derived from an authenticated identity.
- [ ] Only needed fields are projected; embeddings are not returned by default.
- [ ] `vectorSearchScore` is spelled accurately.
- [ ] Score is never treated as a probability or universal cross-model scale.
- [ ] Recall@k vs. ENN, precision/NDCG, and p95 latency are measured.
- [ ] `maxTime`/backpressure and categorized error handling are in place.

### Operations / RAG

- [ ] Unauthorized data is never sent to rerankers or LLMs.
- [ ] Permissions are rechecked when fetching source documents.
- [ ] Mechanisms exist for deleted or permission-revoked documents.
- [ ] Indexing lag state is surfaced for newly uploaded data.
- [ ] Limits exist on query size, candidates, and page size.
- [ ] Search Node load and overload errors are monitored.
- [ ] Hybrid search is evaluated when exact codes or names matter.
- [ ] Hallucination and source citations are audited in RAG answers.
- [ ] Deployment/version support for Vector Search is verified.
- [ ] Benchmarked on a representative workload, not just 8 lab vectors.

## 35. Summary

Vector search in MongoDB is an interconnected chain of engineering decisions:

1. **Embedding space:** document and query vectors must come from a compatible model/version.
2. **Vector index:** use `vectorSearch` type, declaring `path`, `numDimensions`, `similarity`, and filter fields.
3. **Similarity metric:** cosine measures angle; dotProduct measures inner product and requires normalizing BYO vectors; Euclidean measures distance.
4. **ANN:** HNSW searches approximately and uses `numCandidates` to trade latency for recall; 20×`limit` is a starting heuristic, not a guarantee.
5. **ENN:** `exact:true` finds exact nearest neighbors over indexed vectors and serves as the baseline for measuring ANN.
6. **Score:** `vectorSearchScore` in 0–1 is a ranking signal, not the probability of a correct answer.
7. **Filters:** tenant/ACL/status should be applied before retrieval and must have matching filter fields in the index.
8. **Performance:** dimensionality, chunk count, quantization, HNSW/flat, index freshness, and concurrency determine real cost.
9. **Product quality:** evaluate recall, precision, latency, Vietnamese/multilingual data, and RAG grounding.

Aligning **embedding → index → metric → filter → ANN/ENN parameters → empirical evaluation** keeps a MongoDB Vector Search system both useful and controllable in cost, security, and quality.

## Official References

- [MongoDB Vector Search Overview](https://www.mongodb.com/docs/vector-search/)
- [MongoDB — How to Index Fields for Vector Search](https://www.mongodb.com/docs/vector-search/indexes/vector-search-type/)
- [MongoDB — Run Vector Search ANN and ENN Queries](https://www.mongodb.com/docs/vector-search/query/aggregation-stages/vector-search-stage/)
- [MongoDB — Vector Search Query Accuracy](https://www.mongodb.com/docs/vector-search/query/measure-accuracy/)
- [MongoDB — Vector Quantization](https://www.mongodb.com/docs/vector-search/about/vector-quantization/)
- [MongoDB — Explain Vector Search Results](https://www.mongodb.com/docs/vector-search/query/explain/)
- [MongoDB Manual — createSearchIndex](https://www.mongodb.com/docs/manual/reference/method/db.collection.createsearchindex/)
- [MongoDB Manual — getSearchIndexes](https://www.mongodb.com/docs/manual/reference/method/db.collection.getsearchindexes/)
- [MongoDB — Benchmark Overview](https://www.mongodb.com/docs/vector-search/benchmark/overview/)
- [MongoDB Search and Vector Search Changelog](https://www.mongodb.com/docs/atlas/search-changelog/)
- [MongoDB — Hybrid Search](https://www.mongodb.com/docs/vector-search/tutorials/reciprocal-rank-fusion/)
- [MongoDB Java Sync Driver — Aggregation](https://www.mongodb.com/docs/drivers/java/sync/current/aggregation/)
