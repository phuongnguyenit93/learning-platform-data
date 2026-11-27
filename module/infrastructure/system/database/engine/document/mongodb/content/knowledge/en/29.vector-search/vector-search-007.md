# Evaluating Relevance, Latency, Memory, and Storage Cost of Vectors in MongoDB

## 1. Why Multi-Dimensional Evaluation Is Necessary

When deploying **MongoDB Vector Search** for similar-document search, product recommendations, or RAG (*retrieval-augmented generation*), seeing `$vectorSearch` return a few plausible-looking documents does not prove the design is sound. A system can:

- Answer a few sample queries well while **missing** critical documents on real queries.
- Have **low average latency**, yet suffer severe p99 spikes under concurrency.
- Store compact vectors in the collection, while the **Search index / HNSW graph** demands substantial RAM.
- Save RAM via quantization while **hurting recall**, or incur heavy I/O during rescoring.
- Have reasonable database fees while **embedding APIs, Search Nodes, networking, reranking, LLMs, and reindexing** blow past the budget.
- Return semantically close documents that belong to **another tenant**, were deleted, or are unauthorized.
- Achieve nearly 100% ANN recall against ENN while still delivering poor **business relevance**.

This lesson belongs to the **Vector Search** chapter and focuses on four decision axes:

| Axis | Question to answer | Common metrics |
| --- | --- | --- |
| **Relevance** | Do results solve real user needs and rank properly? | Precision@k, Recall@k, nDCG@k, MRR, hit rate |
| **Vector retrieval accuracy** | Does ANN find nearly all of ENN's top-k under the same model and metric? | ANN recall@k, overlap with ENN |
| **Latency and throughput** | How fast is search as load grows? | p50/p95/p99, QPS, timeout/error rate |
| **RAM and storage** | How many bytes do source data, indexes, and headroom require? | Bytes/vector, Search index RAM/disk, IOPS |
| **Total cost** | How does TCO scale with vector count, requests, and updates? | USD/month, USD/million queries, cost/successful answer |

The ultimate goal is finding the **lowest-cost configuration that still meets mandatory quality, latency, freshness, and security constraints**, rather than optimizing a single metric in isolation.

### After This Lesson, You Will Be Able To

1. Distinguish **human relevance** from **ANN recall against ENN**.
2. Choose similarity metrics, `limit`, `numCandidates`, `exact`, and pre-filters.
3. Measure MongoDB and end-to-end p95/p99 without confusing mean latency with tail latency.
4. Estimate vector payload size via `N × D × bytesPerDimension`.
5. Distinguish BSON numeric arrays, BinData float32, quantization, graph overhead, and Search indexes.
6. Design benchmarks with golden queries, labels, ENN baselines, concurrency, and filter selectivity.
7. Estimate costs for source data, replication, Search Nodes, embeddings, reranking, LLMs, and reindexing.
8. Select configurations using a scorecard while preventing ACL/tenant isolation violations.

## 2. Where Does Vector Search Sit in MongoDB's Architecture?

A typical pipeline:

```text
Source documents / products / passages
             |
      Clean + chunk + metadata
             |
         Embedding model
             |
      D-dim vector / chunk
             |
      MongoDB source collection
             |
    MongoDB Vector Search index
       HNSW / flat + filters
             |
User query -> query embedding (same model/space)
             |
         $vectorSearch
             |
      Top-k IDs + scores
             |
      Hydrate / rerank
             |
    UI, API, or RAG context
```

**Three resource classes must not be conflated:**

- **Source data**: text, metadata, and vectors stored as BSON documents on `mongod`.
- **Vector Search index**: vector/index representations, HNSW graph, filter structures, and Search service runtime (`mongot`/Search Nodes depending on deployment).
- **External/adjacent services**: query embedding models, preprocessing, rerankers, LLMs, caches, and APIs.

On some Atlas tiers, Search and MongoDB processes share resources; with **dedicated Search Nodes**, search compute/RAM can be isolated. Configurations, topologies, and self-managed setups vary across versions. Never infer from **`mongod`'s free RAM** that the Search index has sufficient RAM.

## 3. Embeddings, Dimensions, and Similarity

An embedding is a vector:

\[
\mathbf{x} = [x_1,x_2,\ldots,x_D]
\]

`D` is **dimensionality**. Query vectors and document vectors must share the same embedding space: the same model, version, preprocessing, and index dimensionality.

### 3.1. Proximity Functions

| Similarity | Meaning | Trade-offs |
| --- | --- | --- |
| `cosine` | Measures angle between vectors | Suited when direction matters more than magnitude |
| `dotProduct` | Inner product | Affected by magnitude if vectors are unnormalized |
| `euclidean` | L2 distance | Suited when the model/index uses Euclidean distance |

Formulas:

\[
\mathrm{cosine}(\mathbf{q},\mathbf{x}) =
\frac{\mathbf{q}\cdot\mathbf{x}}{\|\mathbf{q}\|_2\|\mathbf{x}\|_2}
\]

\[
\mathbf{q}\cdot\mathbf{x}=\sum_{i=1}^{D}q_ix_i
\]

\[
\mathrm{distance}_{L2}=\sqrt{\sum_{i=1}^{D}(q_i-x_i)^2}
\]

If all vectors are **L2-normalized**, cosine and dotProduct can yield identical rankings. This **does not hold in general** when magnitudes differ. Choose the similarity function matching the embedding model and evaluate on real queries—never swap metrics just to make scores look higher.

### 3.2. `vectorSearchScore` Is Not a Probability

MongoDB Vector Search returns score metadata:

```javascript
{
  $project: {
    title: 1,
    score: { $meta: "vectorSearchScore" }
  }
}
```

`vectorSearchScore` lies between **0 and 1**, following the score transformation of the similarity metric used. A score of `0.87` **does not mean** an 87% probability that the answer is right. It is not calibrated to business ground truth.

A threshold like `score >= 0.80` might fit one corpus/model yet break when changing models, dimensions, chunking, or quantization. To pick thresholds, use relevance labels, false-positive/false-negative costs, and per-query-segment evaluation.

## 4. Two Kinds of “Correctness”: Relevance and ANN Recall

**Relevance** asks: “Do the results solve the user's need?”

**ANN accuracy** asks: “Did ANN find the same nearby vectors that **exact nearest neighbors** (ENN) finds?”

Both must be measured. ANN matching ENN 100% can still return semantically wrong content if the model or data is poor.

### 4.1. Golden Query Set and Qrels

Use a representative question set with relevance labels:

```text
queryId, question, documentId, relevanceGrade, tenant, locale

Q1, "how to get a refund", DOC-101, 3, tenantA, vi
Q1, "return policy", DOC-102, 2, tenantA, vi
Q1, "shipping rates", DOC-103, 0, tenantA, vi
Q2, "fix error E42", DOC-217, 3, tenantA, vi
```

Example grading scale:

- **3:** Direct, complete answer with evidence.
- **2:** Strongly relevant, helps answer.
- **1:** Partially relevant or same general topic.
- **0:** Irrelevant.

Sample queries from real authorized usage, including easy/hard queries, error codes, natural questions, accented/unaccented Vietnamese, unanswerable queries, and permission-scoped queries. For RAG, add labels for **evidence coverage** and **answer faithfulness**.

### 4.2. Precision@k

\[
\mathrm{Precision@k} =
\frac{\text{number of results deemed relevant in top-k}}{k}
\]

If top-5 has three results with grade ≥ 2, then Precision@5 = **3/5 = 0.6**.

### 4.3. Label-Based Recall@k

\[
\mathrm{Recall@k} =
\frac{\text{relevant documents found in top-k}}
{\text{total known relevant documents}}
\]

If labels identify four relevant documents and top-5 retrieves three, Recall@5 = **0.75**.

Caution: on very large corpora, labeling **every** relevant document is difficult. Qrel-based “recall” can be skewed if qrels lack coverage; use pooling across multiple retrieval methods, expert review, and document scope clearly.

### 4.4. MRR and nDCG

**MRR** focuses on the position of the first relevant result:

\[
\mathrm{RR}(q)=\frac{1}{\mathrm{rank\ of\ first\ relevant\ result}}
\]

If the first relevant result is at rank 2, RR = **0.5**. Averaging across queries gives MRR.

**DCG@k** uses relevance grades:

\[
\mathrm{DCG@k} =
\sum_{i=1}^{k} \frac{2^{rel_i}-1}{\log_2(i+1)}
\]

**nDCG@k = DCG@k / IDCG@k**, where IDCG is the DCG of the ideal ordering. nDCG captures that placing a grade-3 result at rank 1 is better than placing it at rank 10.

Choose metrics aligned with UX: customer support often prioritizes getting the first result right; RAG may prioritize evidence coverage across top-N chunks.

## 5. ENN and ANN: Understanding Trade-Offs Before Benchmarking

MongoDB Vector Search supports:

- **ENN** (*Exact Nearest Neighbor*): compares proximity against all eligible vectors under the metric/index, choosing exact top-k.
- **ANN** (*Approximate Nearest Neighbor*): uses index structures like **HNSW** to locate candidates without exhaustive comparisons, accepting occasional missed neighbors.

| Criterion | ENN | ANN |
| --- | --- | --- |
| Results per embedding metric | Exact within index/filter scope | Approximate |
| Benchmark role | Baseline for ANN recall | Measured against ENN |
| Large unfiltered corpus | Can be very resource-intensive | Usually better suited |
| Ultra-selective filter | Can be sensible | Graph traversal may struggle |
| Business quality | Not guaranteed | Not guaranteed |
| Latency scaling with N | Often substantial | Usually efficient at large N |

### 5.1. ANN Recall@k

Let \(T_k(q)\) be the IDs of **ENN top-k** and \(A_k(q)\) be the IDs of **ANN top-k**.

\[
\mathrm{ANNRecall@k}(q) =
\frac{|A_k(q)\cap T_k(q)|}{|T_k(q)|}
\]

Mean across queries:

\[
\overline{\mathrm{ANNRecall@k}} =
\frac{1}{Q}\sum_{q=1}^{Q}\mathrm{ANNRecall@k}(q)
\]

Example:

```text
ENN top-5 = [A, B, C, D, E]
ANN top-5 = [A, B, F, D, G]

Intersection = [A, B, D]
ANN recall@5 = 3/5 = 0.60
```

Crucial point: **ENN is only “exact” with respect to the chosen embeddings and similarity metric**; it does not understand business labels. A system with ANN recall@10 = 0.99 yet human nDCG@10 = 0.35 likely needs a better model or chunking, not higher `numCandidates`.

If many tied scores sit at the top-k boundary, ID overlap may exaggerate minor tie differences; record ties or measure relevance concurrently.

## 6. `numCandidates`, `limit`, and Speed

In MongoDB Vector Search:

- `limit`: maximum number of results returned.
- `numCandidates`: size of the HNSW candidate pool evaluated in an ANN query.
- `exact: true`: requests ENN; omits `numCandidates` used in ANN.
- `exact: false` or omitted `exact`: ANN per supported configuration.

```javascript
{
  $vectorSearch: {
    index: "embedding_index",
    path: "embedding",
    queryVector: queryEmbedding,
    numCandidates: 200,
    limit: 10
  }
}
```

MongoDB provides a common starting point: **`numCandidates` at least roughly 20 times `limit`**, then measure against your real corpus, filters, quantization, and workload. Never interpret this as a recall guarantee.

| limit | numCandidates | Ratio | Guidance |
| ---: | ---: | ---: | --- |
| 10 | 50 | 5× | Can be fast; must check recall |
| 10 | 100 | 10× | Intermediate comparison point |
| 10 | 200 | 20× | Reference starting point |
| 10 | 500 | 50× | May raise both recall and latency |
| 20 | 400 | 20× | Example for top-20 |

In current applicable APIs, ANN `numCandidates` must be at least `limit` and has an upper cap (e.g., 10,000 per MongoDB docs). Check your version/index type before configuring values beyond limits.

**Increasing candidates does not guarantee monotonic recall gains at every step.** Plateaus exist and vary by query alongside CPU/latency cost.

### 6.1. HNSW and Flat

MongoDB Vector Search offers index methods depending on version:

- **`hnsw`**: graph-based, serving ANN on large corpora; can also execute ENN with `exact: true`.
- **`flat`**: builds no HNSW graph and uses exhaustive search, suited when post-filter subsets are tiny or exactness is required.

With `flat`, tuning `numCandidates` does not mean the same thing as with HNSW. Base the index method on version support, corpus size, filter selectivity, and benchmarks.

### 6.2. When Is ENN Worth Choosing?

- The post-filter subset contains very few documents.
- The corpus is small and exact neighbors are needed.
- Generating technical ground truth for ANN.
- Strict vector-neighbor exactness outweighs latency cost.
- Testing differences introduced by quantization or graph indexing.

Never assume ENN suits unfiltered queries over tens of millions of vectors.

## 7. Pre-Filter vs. Post-Filter: More Than Just Latency

Common filters: `tenantId`, `isActive`, `language`, `category`, `securityLevel`, document viewing permissions.

### 7.1. Proper Pre-Filter

```javascript
{
  $vectorSearch: {
    index: "embedding_index",
    path: "embedding",
    queryVector: queryEmbedding,
    filter: {
      tenantId: "tenantA",
      isActive: true
    },
    numCandidates: 200,
    limit: 10
  }
}
```

Fields used in `filter` must be declared with **`filter` type** in the Vector Search index. This filter restricts eligible vectors right inside Search.

**Watch out:** More selective filters do not always run faster. On HNSW, tight selectivity can force the search to traverse more graph nodes to gather enough candidates. Benchmark unfiltered, broad-filter, and ultra-narrow-filter queries.

### 7.2. Post-Filtering Is Not Equivalent

```javascript
[
  {
    $vectorSearch: {
      index: "embedding_index",
      path: "embedding",
      queryVector: queryEmbedding,
      numCandidates: 200,
      limit: 10
    }
  },
  { $match: { tenantId: "tenantA" } }
]
```

This query pulls the **corpus-wide top-10** and filters afterward. Only two results for tenant A might remain even when tenant A has thousands of relevant documents. For ACL/tenant isolation, never treat post-filtering top-k as returning all authorized candidates.

### 7.3. Filter Selectivity Matrix to Test

| Scenario | % docs passing filter (hypothetical) | Purpose |
| --- | ---: | --- |
| Unfiltered | 100% | Baseline |
| Large category | 40% | Broad filter |
| Small category | 5% | Selective filter |
| Small tenant | 0.2% | Test ANN/ENN after filter |
| Recent documents | 1% | Freshness and selectivity |

Measure quality, result counts, latency, and resources for each case. **Do not treat filters as free add-ons.**

## 8. Self-Contained MongoDB Vector Search Lab

Examples only run on a **deployment supporting MongoDB Vector Search and Search indexes**. A standalone MongoDB lacking a compatible Search service/index will not execute `$vectorSearch` merely because a collection contains numeric arrays.

Lab data uses **hand-crafted four-dimensional vectors** for syntax clarity; they are **not production-quality semantic embeddings**.

### 8.1. Preparing the Collection

Open `mongosh` against a test environment—**never run `drop()` on production**:

```javascript
const lab = db.getSiblingDB("vector_eval_lab");

lab.items.drop();

lab.items.insertMany([
  {
    _id: "D1",
    tenantId: "A",
    isActive: true,
    category: "database",
    title: "Introduction to MongoDB",
    embedding: [1.0, 0.0, 0.0, 0.0]
  },
  {
    _id: "D2",
    tenantId: "A",
    isActive: true,
    category: "database",
    title: "Replica sets and failover",
    embedding: [0.8, 0.2, 0.0, 0.0]
  },
  {
    _id: "D3",
    tenantId: "A",
    isActive: true,
    category: "database",
    title: "Sharding",
    embedding: [0.5, 0.5, 0.0, 0.0]
  },
  {
    _id: "D4",
    tenantId: "A",
    isActive: true,
    category: "search",
    title: "Vector Search",
    embedding: [0.0, 0.8, 0.2, 0.0]
  },
  {
    _id: "D5",
    tenantId: "B",
    isActive: true,
    category: "database",
    title: "Tenant B private document",
    embedding: [0.99, 0.01, 0.0, 0.0]
  },
  {
    _id: "D6",
    tenantId: "A",
    isActive: false,
    category: "database",
    title: "Hidden document",
    embedding: [0.98, 0.02, 0.0, 0.0]
  },
  {
    _id: "D7",
    tenantId: "A",
    isActive: true,
    category: "search",
    title: "Text analysis",
    embedding: [0.0, 0.6, 0.4, 0.0]
  },
  {
    _id: "D8",
    tenantId: "A",
    isActive: true,
    category: "other",
    title: "Other document",
    embedding: [0.0, 0.0, 0.0, 1.0]
  }
]);
```

### 8.2. Creating the Vector Search Index

Example with `mongosh` and a deployment supporting `createSearchIndex`:

```javascript
lab.items.createSearchIndex({
  name: "toy_vector_index",
  type: "vectorSearch",
  definition: {
    fields: [
      {
        type: "vector",
        path: "embedding",
        numDimensions: 4,
        similarity: "cosine"
      },
      { type: "filter", path: "tenantId" },
      { type: "filter", path: "isActive" },
      { type: "filter", path: "category" }
    ]
  }
});
```

Index builds are **asynchronous**. Inspect with:

```javascript
lab.items.listSearchIndexes().toArray();
```

Query only after the index reports `queryable`/READY per your version's API. Options such as `quantization`, `indexingMethod`, and HNSW parameters must follow documentation for your active deployment.

### 8.3. ANN Query

```javascript
const q = [0.9, 0.1, 0.0, 0.0];

const ann = lab.items.aggregate([
  {
    $vectorSearch: {
      index: "toy_vector_index",
      path: "embedding",
      queryVector: q,
      filter: { tenantId: "A", isActive: true },
      numCandidates: 40,
      limit: 3
    }
  },
  {
    $project: {
      _id: 1,
      title: 1,
      category: 1,
      score: { $meta: "vectorSearchScore" }
    }
  }
]).toArray();

printjson(ann);
```

`$vectorSearch` must be the **first stage** of the pipeline. Because of pre-filtering, results will never contain `D5` (tenant B) or `D6` (inactive).

### 8.4. ENN as Baseline

```javascript
const enn = lab.items.aggregate([
  {
    $vectorSearch: {
      index: "toy_vector_index",
      path: "embedding",
      queryVector: q,
      filter: { tenantId: "A", isActive: true },
      exact: true,
      limit: 3
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

printjson(enn);
```

ENN finds exact neighbors **within the eligible set per index and filter**, without guaranteeing relevance to real user intent. On an eight-doc lab, ANN and ENN may return identical top-3; that does not prove ANN achieves 100% recall across millions of vectors.

### 8.5. Computing Overlap

```javascript
function recallAtK(annDocs, ennDocs) {
  const groundTruth = new Set(ennDocs.map(d => String(d._id)));
  const hits = annDocs.filter(
    d => groundTruth.has(String(d._id))
  ).length;

  return groundTruth.size ? hits / groundTruth.size : 1;
}

print("ANN recall@3:", recallAtK(ann, enn));
```

In production, average across many queries and `numCandidates` levels, keeping **identical filters, similarity, and index** when comparing.

## 9. Lab: Label-Based Relevance Evaluation

Create simulated labels:

```javascript
const relevance = {
  Q1: { D1: 3, D2: 2, D3: 1, D4: 0, D7: 0, D8: 0 },
  Q2: { D4: 3, D7: 2, D3: 1, D1: 0, D2: 0, D8: 0 }
};

function precisionAtK(ids, labels, k, relevantGrade = 2) {
  let n = 0;
  for (const id of ids.slice(0, k)) {
    if ((labels[id] || 0) >= relevantGrade) n++;
  }
  return n / k;
}

function dcgAtK(ids, labels, k) {
  return ids.slice(0, k).reduce((sum, id, i) => {
    const rel = labels[id] || 0;
    return sum + (Math.pow(2, rel) - 1) / Math.log2(i + 2);
  }, 0);
}

function ndcgAtK(ids, labels, k) {
  const ideal = Object.keys(labels).sort(
    (a, b) => labels[b] - labels[a]
  );
  const best = dcgAtK(ideal, labels, k);
  return best ? dcgAtK(ids, labels, k) / best : 1;
}

const resultIds = ["D1", "D3", "D2", "D4", "D7"];

print("P@3:", precisionAtK(resultIds, relevance.Q1, 3));
print("nDCG@3:", ndcgAtK(resultIds, relevance.Q1, 3));
```

For Q1, treating grade ≥ 2 as relevant, `[D1,D3,D2]` gives Precision@3 = **2/3**. nDCG drops because D3 (grade 1) precedes D2 (grade 2).

Never use vector search scores in place of **human labels**. Keep the evaluation set fixed when comparing models/indexes/chunking, and maintain a holdout set to guard against overfitting.

## 10. Latency: Breaking Down Time per Stage

A search request may include:

```text
User request
    |
    +-- Authentication + network
    +-- Preprocessing
    +-- Query embedding API
    +-- MongoDB $vectorSearch
    +-- Hydration / $project
    +-- Optional reranker
    +-- Optional LLM generation
    +-- Serialization / response
```

If users experience 600 ms while MongoDB Vector Search takes only 35 ms, shaving MongoDB down to 25 ms will not solve most of the latency.

| Metric | Measurement boundary | Purpose |
| --- | --- | --- |
| `embeddingLatencyMs` | Text sent to embedding model → vector received | Provider/model latency |
| `vectorQueryLatencyMs` | Aggregation sent → all results received | MongoDB/search + network |
| `hydrationLatencyMs` | Fetching source content/metadata | Payload/I/O |
| `rerankLatencyMs` | Candidates sent → new order received | Reranker |
| `searchApiLatencyMs` | HTTP request → response | User-facing SLO |
| `ragAnswerLatencyMs` | Question → answer | RAG UX |

When stages run in parallel, you cannot simply add component p95s to get total p95; **measure end-to-end directly**.

## 11. p50, p95, p99, and Error Rates

Mean latency hides tail latency. If most queries return in 40 ms while 1% take 1,000 ms, high-percentile users suffer noticeable delays.

- **p50:** half of requests complete within this threshold.
- **p95:** 95% of requests complete within this threshold (per dataset percentile calculation).
- **p99:** focuses on the tail.
- **QPS:** actual sustained throughput achieved, not merely load-generator send rate.
- **Error rate:** timeouts, rejections, and stale/incomplete results where measurable.

### 11.1. Mini Benchmark in mongosh

```javascript
const candidatesList = [20, 40, 80, 160];
const vectors = [
  [0.9, 0.1, 0, 0],
  [0.1, 0.9, 0, 0],
  [0.5, 0.5, 0, 0]
];

function searchOnce(queryVector, numCandidates) {
  return lab.items.aggregate([
    {
      $vectorSearch: {
        index: "toy_vector_index",
        path: "embedding",
        queryVector,
        filter: { tenantId: "A", isActive: true },
        numCandidates,
        limit: 3
      }
    },
    {
      $project: {
        _id: 1,
        score: { $meta: "vectorSearchScore" }
      }
    }
  ]).toArray();
}

function percentile(samples, p) {
  const sorted = [...samples].sort((a, b) => a - b);
  const i = Math.ceil(p * sorted.length) - 1;
  return sorted[Math.max(0, Math.min(i, sorted.length - 1))];
}

for (const n of candidatesList) {
  // Warm up before measuring.
  for (const v of vectors) searchOnce(v, n);

  const samplesMs = [];

  for (let i = 0; i < 30; i++) {
    const v = vectors[i % vectors.length];
    const t0 = Date.now();
    searchOnce(v, n);  // .toArray() drains full results.
    samplesMs.push(Date.now() - t0);
  }

  printjson({
    numCandidates: n,
    p50: percentile(samplesMs, 0.50),
    p95: percentile(samplesMs, 0.95),
    p99: percentile(samplesMs, 0.99)
  });
}
```

**Warning:** 30 iterations, 8 docs, and millisecond timers are insufficient to judge production p99; network jitter, caches, and scheduling dominate. This merely demonstrates instrumentation. Production benchmarking needs **hundreds or thousands of representative queries**, sufficient duration, warm/cold runs, concurrency, error rates, ready Search indexes, and consistent environment configs.

### 11.2. Track p95/p99 by Query Segment

Do not rely on a single service-wide number. Break out:

- Small-tenant vs. large-tenant filtered queries.
- Vietnamese, English, and identifier queries.
- Queries returning 5/10/20/50 results.
- Queries across different dimensions/models.
- Queries running during index updates.
- Concurrency of 1, 10, 50, 100 users.
- Small/large corpora and cached/uncached runs.

A `numCandidates` setting good for global queries is not necessarily good for highly selective filters.

## 12. Concurrency and Serving Capacity

With one client, a 70 ms query may look fine. With 100 concurrent clients, Search CPU, thread pools, network, or disk I/O can saturate; requests queue up and p99 spikes.

**Little's Law** for a stable system:

\[
L=\lambda W
\]

- \(L\): average number of requests in the system.
- \(\lambda\): throughput in requests/sec.
- \(W\): average time in the system (seconds).

At \(\lambda=100\) QPS and \(W=0.1\) s, on average roughly **10 requests are in flight**. This does not guarantee 10 concurrent slots suffice for bursts or tail latency.

Concurrency levels to test:

```text
1, 5, 10, 20, 50, 100 clients
```

At each level, record achieved QPS, p50/p95/p99, timeouts/rejections, Search node CPU/RAM, disk I/O, network, and index freshness. When QPS stops climbing while latency/errors spike, the system is saturated.

**Hold quality constant when optimizing load.** If you lower `numCandidates` or change quantization to run faster, re-measure recall and human relevance.

## 13. Fundamental Vector Memory Formulas

With:

- \(N\): number of vectors.
- \(D\): dimensions per vector.
- \(b\): bytes per dimension for the representation.

Ideal numeric payload:

\[
B=N\times D\times b
\]

| Type | Bytes/dimension | D=1536, payload/vector |
| --- | ---: | ---: |
| Float64/double | 8 | 12,288 bytes |
| Float32 | 4 | 6,144 bytes |
| Int8/scalar | 1 | 1,536 bytes |
| Int1/binary | 1/8 | 192 bytes |

When D is not divisible by 8, bit-packed representations must round up to whole bytes. These figures **exclude** metadata, array overhead, graph structures, runtime, replicas, disk pages, and compression.

### 13.1. One Million 1536-Dimensional Vectors

\[
1{,}000{,}000 \times1536\times4
=6{,}144{,}000{,}000 \text{ bytes}
\]

That is roughly **6.144 GB decimal** or **5.72 GiB** of float32 payload.

Comparison:

| Representation | 1 million vectors, 1536D |
| --- | ---: |
| Float64 | 12.288 GB |
| Float32 | 6.144 GB |
| Int8 | 1.536 GB |
| Binary int1 | 0.192 GB |

**10 million 1536D float32 vectors = 61.44 GB payload**, not total index size or cluster RAM.

### 13.2. BSON Numeric Arrays vs. BinData Float32

```javascript
{
  embedding: [0.1, 0.2, 0.3]
}
```

In BSON, JavaScript Numbers typically store as **64-bit Doubles** (8 bytes), and BSON arrays add per-element **type + key name** overhead.

With **BSON BinData float32 vector subtypes** supported by drivers/SDKs, numeric payloads can approach 4 bytes/dimension. However:

- Requires the exact subtype/format supported by MongoDB Vector Search.
- Source storage still includes document fields, metadata, and compression.
- The Search index still maintains its own representation, graph, and runtime.

Never use JSON string size or \(N×D×4\) alone to predict exact `storageSize`.

### 13.3. Raw Payload Size Table

| N vectors | D | Float32 | Int8 | Int1 |
| ---: | ---: | ---: | ---: | ---: |
| 100,000 | 768 | 0.3072 GB | 0.0768 GB | 0.0096 GB |
| 1,000,000 | 1536 | 6.144 GB | 1.536 GB | 0.192 GB |
| 5,000,000 | 1536 | 30.72 GB | 7.68 GB | 0.96 GB |
| 10,000,000 | 2048 | 81.92 GB | 20.48 GB | 2.56 GB |

This is **payload excluding overhead**, not a MongoDB benchmark.

## 14. Search Index Memory Differs from Vector Payload

A RAM model:

```text
Search RAM ≈
   vector representations
 + HNSW graph connections
 + segment / doc ID structures
 + metadata filter index
 + JVM/runtime/buffers
 + safety headroom
```

The HNSW graph stores edges between vectors for fast ANN lookup. Graph size depends on N, edge count, segment layout, parameters, version, and data distribution.

Never assume a 6.144 GB payload means Search RAM needs exactly 6.144 GB. And never mistake `totalIndexSize` of B-tree indexes on the MongoDB source collection for the size of the MongoDB Vector Search index.

### 14.1. Three Distinct Disk Layers

1. **Document storage**: text/chunk metadata and source vectors.
2. **Search index storage**: vector index representations, graph, filter structures, and potentially full-precision vectors for ENN/rescoring.
3. **Backup/replica/auxiliary storage**: replicas, snapshots, rebuild workspace, and disk headroom.

On Atlas, inspect **Search Index Size** and **Required Memory** in Search UI/metrics to separate actual disk and memory usage. Exact metrics vary by tier and version.

### 14.2. Budget for Rebuilds

When changing index definitions, models/dimensions, or quantization, the index may rebuild asynchronously. During that window:

- Extra CPU, I/O, and network are consumed.
- Temporary extra disk space may be needed.
- Old and new indexes may coexist during transition depending on deployment mechanics.
- Search freshness and serving capacity may fluctuate.

This is a lifecycle cost that must be budgeted, not a zero-cost config tweak.

## 15. Quantization: Saving RAM with Trade-Offs

**Quantization** converts multi-bit vectors into lower-bit representations. The primary goal is reducing RAM and memory bandwidth, sometimes improving latency/cost—without guaranteeing identical relevance.

### 15.1. Float / Full Precision

- Preserves full fidelity of the original embedding.
- Typically consumes more RAM.
- Serves as the baseline for comparing quantized setups.
- Does not by itself guarantee the model understands every query.

### 15.2. Scalar Quantization

Float32 → roughly 8-bit representation per dimension:

- Ideal vector payload shrinks by roughly **4×**.
- Can reduce serving RAM and compute cost.
- Because values are quantized, nearest-neighbor ordering can shift.
- Must verify ANN recall and nDCG.

### 15.3. Binary Quantization

Float32 → roughly **1-bit representation per dimension**:

- Ideal numeric payload is roughly **32×** smaller.
- Can yield dramatic RAM savings.
- Vector distortion relative to full precision increases.
- With **binary + rescoring**, the engine reads full vectors from disk to re-rank top candidates, improving accuracy at the cost of extra CPU, I/O, and latency.

With automatic quantization, MongoDB may retain **full-precision vectors on disk** to support ENN or rescoring. Thus, shrinking index RAM **does not mean** disk usage drops 32×.

### 15.4. Overhead Makes Real Ratios Differ from Theory

MongoDB benchmark docs report Search index RAM reductions in some configurations of roughly **3.75× for scalar** and **24× for binary**, lower than raw 4×/32× payload ratios because graphs and other structures do not compress at the same rate.

These ratios are **workload-specific references**, not guarantees for your index. Size based on measured Search index RAM/disk.

### 15.5. `binaryNoRescore` and Auto Embedding

Newer docs include options such as `binaryNoRescore` in certain Automated Embedding setups: eliminating rescoring overhead at the cost of potential accuracy loss. Available quantization options and defaults **differ across BYO vectors, automated embeddings, index types, and versions**. Never copy an option from another environment's tutorial without checking the API.

| Configuration | RAM | Recall/relevance | Query latency | Disk |
| --- | --- | --- | --- | --- |
| Float/HNSW | High | Baseline vector fidelity | ANN usually fast at large N | Full precision + graph |
| Scalar/HNSW | Lower | May dip slightly | Often faster | May retain full-precision disk |
| Binary+rescore/HNSW | Very low | Can approach baseline after rerank | Extra rescoring I/O | Full-precision disk may remain |
| Binary no rescore | Very low | Can drop noticeably | Avoids rescore cost | Index-dependent |
| Flat/ENN | Minimal graph | Exact per metric/index | Can be slow at large N | Format-dependent |

**No single choice fits every application.** Decide using SLO + relevance + latency + cost after measuring.

## 16. Vector Count and Chunking Are Major Cost Multipliers

A single source document can generate many chunks:

```text
100,000 documents
20 chunks/document
= 2,000,000 vectors
```

Increasing overlap or splitting into smaller chunks at **40 chunks/document** turns vector count into **4 million**, doubling source embedding payload and impacting search index and embedding costs.

### 16.1. Chunks Too Large

- One vector covers many topics, diluting semantic signals.
- Returned results include excessive irrelevant text.
- Reranking/LLM contexts waste tokens.
- Short answer passages may lose ranking score.

### 16.2. Chunks Too Small

- Loss of surrounding context.
- Embeddings and index entries multiply.
- Near-duplicate chunks cause repetitive results.
- Higher embedding API cost, storage, and index rebuild times.

Evaluate **nDCG/MRR/answer correctness across chunking strategies** alongside vector count—not index memory alone.

### 16.3. Dimensions Also Multiply Cost

Growing from D=768 to D=1536 at fixed N and float32 **doubles** ideal vector payload. Quality **does not automatically double**; evaluate for your model and domain.

### 16.4. Changing the Embedding Model Is a Migration

A safe plan:

1. Version models, vectors, and indexes.
2. Generate new embeddings in a new field or collection.
3. Build a Search index with the matching dimensions and similarity.
4. Measure quality, recall, p95/p99, and TCO.
5. Switch query embeddings to the new model.
6. Canary/cutover while retaining rollback to the old index.
7. Clean up old vectors/indexes once the rollback window closes.

**Matching dimensions does not mean matching embedding spaces.** Never mix vectors from two incompatible models.

## 17. Estimating Source Storage and Replication

For 1 million vectors, D=1536, float32:

```text
1,000,000 × 1,536 × 4 = 6.144 GB payload
```

If MongoDB source data has **three full data-bearing copies** ignoring compression and overhead:

```text
6.144 GB × 3 = 18.432 GB source vector payload
```

However, the Search index stores its own representation plus graph/filter structures, and managed billing may already price replication into the tier. Do not triple-count if your tier bill already includes replicas.

A structured breakdown:

```text
Source storage footprint =
   document/chunk text + original embedding
 + BSON overhead + MongoDB indexes
 × replication/storage policy

Search footprint =
   search vectors/quantized representations
 + graph/filters/segments
 + full-precision disk for ENN/rescore (if any)
 × serving topology

Extra =
   backups/snapshots + temporary rebuild
 + network transfer + logs/monitoring
```

Apply multipliers strictly to the right scope and avoid double counting. Validate against live cluster metrics and cloud/region/tier cost estimators.

## 18. Embedding and Re-Embedding Costs

For BYO embeddings from an external provider, vector generation cost can be modeled as:

\[
C_{\mathrm{embed}} =
\frac{\mathrm{inputTokens}}{10^6}
\times \mathrm{pricePerMillionTokens}
\]

**Hypothetical example, not a vendor price quote:**

- 2 million chunks.
- 1,000 tokens/chunk.
- Total **2 billion tokens**.
- Assume \$0.05 per 1 million input tokens.

Initial cost: \(2000\times0.05=\) **\$100** under those assumptions. Changing the embedding model and regenerating all vectors incurs fresh embedding charges plus index rebuild/dual-serving costs.

### 18.1. Query Embedding Costs

At 1 million queries/month with 100 tokens/query:

```text
100,000,000 tokens/month
= 100 million tokens
```

At the example rate of \$0.05/million tokens, query embedding cost = **\$5/month**. This excludes Search Nodes, source storage, retrieval, networking, reranking, and LLM costs.

### 18.2. Rerankers and LLMs Are Often the Largest Expense

```text
Query embedding
   -> vectorSearch top-50
   -> rerank top-8
   -> LLM answers from evidence
```

Sending 50 long chunks straight to an LLM incurs heavy token costs. A reranker can raise relevance and trim context, yet carries its own latency and price. Measure **cost per useful answer**, not cost per vector search alone.

## 19. Total Cost of Ownership (TCO)

Monthly model:

\[
\begin{aligned}
C_{\mathrm{month}} ={}&
C_{\mathrm{DatabaseCompute}}+
C_{\mathrm{SourceStorage}}+
C_{\mathrm{SearchNodes}}\\
&+C_{\mathrm{Embedding}}+
C_{\mathrm{Rerank}}+
C_{\mathrm{LLM}}\\
&+C_{\mathrm{Network}}+
C_{\mathrm{Backup}}+
C_{\mathrm{Operations}}
\end{aligned}
\]

A UX-aligned economic metric:

\[
C_{\mathrm{perUsefulAnswer}} =
\frac{C_{\mathrm{month}}}
{\mathrm{numberOfUsefulAnswers}}
\]

### 19.1. Hypothetical Search Nodes Pricing Example

Two Search Nodes at an assumed **\$0.50/hour** each, running 720 hours/month:

```text
2 × $0.50/h × 720 h = $720/month
```

If forced to scale up to a Search tier assumed at **\$1.20/hour/node**:

```text
2 × $1.20/h × 720 h = $1,728/month
```

A difference of \$1,008/month. **These are not real MongoDB Atlas prices**; check current pricing for your region, cloud provider, and tier before submitting budgets.

### 19.2. Cost per Million Searches

Suppose Search serving and direct overhead = \$1,200/month across 2 million search requests:

```text
$1,200 / 2 = $600 per million search queries
```

This excludes embedding APIs, source reads, RAG generation, and operations. When relevance is poor, **cost per useful result** climbs much higher.

### 19.3. Three Estimation Mistakes

- **Undercounting:** Counting only vector bytes while ignoring Search graphs, replicas, index rebuilds, and reranking.
- **Double counting:** Multiplying storage replicas when managed tiers already price them in.
- **Unit confusion:** Mixing GB (10^9 bytes) with GiB (2^30 bytes), or confusing resident memory with disk index size.

Maintain a transparent BOM table citing price and configuration sources.

## 20. Optimizations and What Must Be Re-Measured

| Optimization | Potential benefit | Must re-measure |
| --- | --- | --- |
| Reduce vector dimensions | Smaller numeric payload | Human nDCG, ANN recall |
| Sensible chunking | Lower N or better context | Coverage, tokens, index size |
| BinData float32 | Smaller source storage than BSON Double arrays | Driver/index compatibility |
| Scalar quantization | Less Search RAM | Recall, p99, disk |
| Binary + rescore | Minimal RAM | Rescore I/O/QPS, accuracy |
| Lower `numCandidates` | Less ANN work | ANN recall, critical misses |
| Raise `numCandidates` | Potentially higher recall | Tail latency/QPS |
| Proper pre-filter | Enforces scope and relevant pool | Selectivity/latency |
| Flat/ENN on small sets | Exact neighbors | Latency as N grows |
| Project out embeddings | Lower network/hydration cost | E2E latency |
| Cache query vectors | Fewer embedding API calls | Freshness/privacy |
| Rerank top-N | Potentially higher nDCG | Latency/cost |
| Hybrid lexical + semantic | Exact codes and meaning | Fusion/relevance |
| Dedicated Search Nodes | Resource isolation | TCO and Search capacity |

### 20.1. Omit Long Embedding Arrays When the UI Doesn't Need Them

```javascript
lab.items.aggregate([
  {
    $vectorSearch: {
      index: "toy_vector_index",
      path: "embedding",
      queryVector: q,
      numCandidates: 40,
      limit: 3
    }
  },
  {
    $project: {
      _id: 1,
      title: 1,
      category: 1,
      score: { $meta: "vectorSearchScore" }
    }
  }
]);
```

Projection shrinks payloads by omitting long `embedding` arrays. At large scale and high QPS, cutting JSON/serialization/network overhead lowers overall latency.

## 21. Hybrid Search, Reranking, and Business Accuracy

Queries containing **error codes, SKUs, API fields**, or specific versions may not rank highly on vector similarity alone.

Example:

```text
"Fix MongoDB ERR-1042"
         |
         +-- Lexical text search -> exact error code match
         |
         +-- Vector Search ------> semantic match
         |
       Merge/rerank
         |
       Top-k to user
```

Hybrid search can boost coverage, at the cost of extra indexes, queries, merging, and reranking. Compare against vector-only on the same golden queries, especially for Vietnamese questions and identifier queries.

For RAG, add metrics:

- **Context recall/precision:** do chunks contain the right evidence?
- **Answer correctness:** does the answer solve the question?
- **Groundedness/faithfulness:** is the answer supported by retrieved evidence?
- **Citation accuracy:** do citations point to the right passages?
- **Cost per successful answer** and end-to-end latency.

Good retrieval metrics do not automatically guarantee good generation.

## 22. Freshness and Access Control

The Vector Search index synchronizes asynchronously with source MongoDB writes. After inserts, updates, or deletes, search results **may not reflect changes immediately**.

Measure:

- Time from source insert to searchable.
- Time from deletion/visibility change until search stops returning the document.
- Index lag during ingest bursts.
- Index build/rebuild status.
- Re-embedding cost when documents change.

### 22.1. Multi-Tenant/ACL Enforcement Cannot Rely Solely on Scores

If a document's permissions are revoked, vector search may briefly still return its ID due to index lag. The API must verify access rights against an authoritative source at serving time—never treat the Search index or `vectorScore` as an authorization engine.

Information inside embeddings, metadata, and logs must also follow security policies. Never log sensitive documents verbatim just to run benchmarks.

## 23. Designing a Fair Benchmark

### 23.1. Three Data Pillars

**Corpus:** large enough with production-like distributions of documents, chunks, dimensions, metadata, tenant skew, languages, dates, and duplicates.

**Queries:** short/long queries, IDs, multilingual queries, unanswerable queries, ultra-narrow pre-filters, easy/hard cases, and newly added/deleted docs.

**Qrels:** trustworthy relevance labels with a holdout split to prevent tuning overfitting.

### 23.2. Experiment Axes

| Group | Varied parameter | Metrics |
| --- | --- | --- |
| Embedding model | Model, D=768/1536 | nDCG/MRR, cost |
| ANN | `numCandidates` 50/100/200/500 | Recall@k, latency |
| Quantization | float/scalar/binary | Recall, Search RAM/disk, p99 |
| Index method | HNSW/flat | Exactness, latency, index size |
| Filter | 100%/40%/5%/0.2% | Recall, p95, result count |
| Concurrency | 1/10/50/100 | QPS, p99, errors |
| Cache | Cold/warm | Latency variance |
| Freshness | Insert/update/delete → searchable | Index lag |
| Chunking | Chunk size/overlap | N vectors, relevance |
| Rerank/hybrid | Vector-only vs. hybrid | nDCG/answer correctness |

Vary **one group at a time** while holding dataset, query mix, and resources constant to avoid misattributing causes.

### 23.3. Procedure

1. Define quality, latency, freshness SLOs, and cost budgets.
2. Load representative corpus and query labels.
3. Build indexes and wait for READY/queryable state.
4. Warm up per test mode and record cache state.
5. Run ENN baseline under the same filter and metric.
6. Run ANN and compute overlap plus relevance.
7. Ramp concurrency; collect p95/p99/QPS/errors.
8. Measure actual RAM/disk/index size/CPU/IOPS.
9. Run updates/deletes to measure index freshness.
10. Compute TCO and cost per useful answer.
11. Compare scorecards and decide.

### 23.4. Pitfalls That Invalidate Comparisons

- Testing with a single sample question.
- Query vectors from a different model than indexed vectors.
- ANN and ENN using different filters.
- Averaging successful requests while ignoring timeouts.
- Reporting p99 from 20 requests.
- Comparing a cold index against a warm index.
- Treating ANN recall as human relevance.
- Reporting Search index size as equal to source BSON vector payload.
- Ignoring Search Nodes, reindexing, and backups.
- Omitting embedding, reranking, and LLM latencies.
- Neglecting ACLs and search index freshness.

## 24. Decision Scorecard

Example SLOs (**purely hypothetical**):

- Human nDCG@10 ≥ **0.78**.
- ANN recall@10 ≥ **0.92**.
- p95 vector query ≤ **120 ms**.
- p99 vector query ≤ **250 ms**.
- Zero tenant/ACL violations.
- TCO within budget.

**Simulated** results table (not a MongoDB benchmark):

| Candidate | nDCG@10 | ANN recall@10 | p95 ms | p99 ms | Search RAM GB | Cost/mo USD | Verdict |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| A float, candidates 200 | 0.83 | 0.97 | 110 | 210 | 28 | 1,500 | Pass |
| B scalar, candidates 200 | 0.82 | 0.95 | 80 | 170 | 11 | 1,050 | Pass |
| C binary, candidates 100 | 0.73 | 0.85 | 55 | 130 | 4 | 820 | Fails relevance |
| D binary+rescore, candidates 500 | 0.80 | 0.93 | 150 | 310 | 5 | 920 | Fails latency |
| E scalar, candidates 100 | 0.79 | 0.90 | 62 | 140 | 11 | 980 | Fails ANN recall |

Based solely on the table and thresholds above, **B** is cheaper than A while meeting every requirement. Do not pick C just for low price or D just for low RAM. Different application thresholds yield different choices.

### 24.1. Pareto Efficiency and Hard Gates

A candidate is dominated if another candidate matches or beats it in quality, latency, and cost while strictly excelling in at least one dimension.

However, **non-negotiable constraints** such as ACLs, sensitive data handling, and business accuracy must act as hard *gates*—never weighted trade-offs compensated by lower cost.

## 25. Real-World Scenarios

### 25.1. Technical Documentation RAG with Many Error Codes

Combine vector search, lexical search, and reranking; measure nDCG, groundedness, and citation accuracy. When a query contains exact identifier `ERR-1042`, never rely on semantic similarity alone.

### 25.2. Product Recommendations Across Millions of Items

HNSW and quantization can cut RAM and query cost. Also measure diversity, near-duplicates, `isActive`/stock, traffic spikes, index freshness, and update rates.

### 25.3. Small Tenant with Ultra-Narrow Filters

With a few hundred eligible vectors, ENN/flat is worth considering. Measure empirically rather than assuming ANN is always faster.

### 25.4. High-Stakes Record Retrieval

When a false negative carries severe consequences, do not rely solely on raising candidate counts; add human review, hybrid retrieval, verification, and business rules.

### 25.5. Vietnamese Corpora

Test accented and unaccented queries, proper names, abbreviations, codes, and paraphrased questions. Multilingual embedding models do not automatically handle every Vietnamese writing variation flawlessly.

## 26. Common Mistakes

| Misconception | Why it is wrong | Fix |
| --- | --- | --- |
| “Score 0.9 means 90% accurate” | Score reflects proximity, not probability | Qrels and calibration |
| “100% ANN recall = semantically right” | ENN is only exact per vector metric | Human relevance eval |
| “20× limit guarantees recall” | Merely a starting heuristic | Benchmark on real data |
| “ENN is always better than ANN” | Exhaustive search is expensive | Choose by N and filter |
| “Narrower filters are always faster” | Filtered HNSW traversal can struggle | Measure selectivity |
| “Post-filtering top-k equals pre-filtering” | Can return far too few results | Filter inside `$vectorSearch` |
| “No search index needed, just store array” | `$vectorSearch` needs supported index/service | Create proper index |
| “Newly created index works immediately” | Builds can be asynchronous | Wait for queryable |
| “Quantization cuts RAM/disk by exact 32×” | Graph, full-precision disk, and rescore overhead | Measure actual RAM/disk |
| “Float32 always cuts BSON disk in half” | BSON overhead and compression differ | Measure actual storage |
| “One document equals one vector” | Chunking creates multiple vectors | Size by chunk count |
| “Larger D is always more accurate” | Quality depends on the model | Golden query evaluation |
| “Same dimensions work across models” | Different embedding spaces | Version models strictly |
| “Fast for 1 client means handles 100 QPS” | Queueing and saturation occur | Run load tests |
| “Average latency is enough” | Tail p99 can be severe | Track p95/p99 and errors |
| “Ignore rerank/LLM costs” | They dominate end-to-end cost | Trace and compute TCO |
| “Index refreshes synchronously on writes” | Indexing can be asynchronous | Monitor freshness lag |
| “High score skips permission checks” | Similarity is not authorization | Enforce authoritative ACLs |
| “MongoDB replicas include Search index sizing” | Serving and index topologies differ | Size each layer |
| “Changing index/model is free” | Reindexing and re-embedding have real costs | Migration runbook |

## 27. Practice Exercises

### Exercise 1 — Relevance vs. ANN Accuracy

ANN recall@10 = 0.98 against ENN, yet human nDCG@10 = 0.42. What should you investigate?

**Answer:** ANN is not the main bottleneck; inspect the embedding model, chunking, corpus quality, query intent, and reranking.

### Exercise 2 — Computing Overlap

```text
ENN: [A,B,C,D,E]
ANN: [A,B,F,D,G]
```

What is ANN recall@5?

**Answer:** 3/5 = **0.6**.

### Exercise 3 — Precision

Top-5 has relevance grades `[3,0,2,1,3]`, with grade ≥ 2 considered relevant. What is Precision@5?

**Answer:** 3/5 = **0.6**.

### Exercise 4 — MRR

First relevant results for three queries appear at ranks 1, 2, and 5. What is MRR?

**Answer:** \((1+1/2+1/5)/3=0.5667\).

### Exercise 5 — Score

A hit has `vectorSearchScore=0.88`. Can you state an 88% chance the answer is right?

**Answer:** No; score is not a calibrated probability.

### Exercise 6 — Candidates Sweep

At `limit=10`, `numCandidates` 50/100/200/500 yield recall 0.89/0.92/0.96/0.961 and p95 35/47/70/130 ms. Requiring recall ≥ 0.95 and p95 ≤ 100 ms, which do you pick?

**Answer:** `numCandidates=200`.

### Exercise 7 — When to Use ENN?

Give two cases for choosing ENN over ANN and two cases where ANN is usually preferable. Why doesn't ENN guarantee relevance?

### Exercise 8 — Pre-Filter

Write a `$vectorSearch` stage returning only tenant A and active documents via pre-filtering. Why isn't `$match` after top-10 equivalent?

### Exercise 9 — Stage Order

Can `$match` be placed before `$vectorSearch`?

**Answer:** `$vectorSearch` must be the first stage; put filters inside the stage.

### Exercise 10 — Float32 Sizing

One million vectors × 1536D × 4 bytes equals how many decimal GB?

**Answer:** 6.144 GB payload.

### Exercise 11 — Float64 vs. Float32

One million 1536D vectors: what is the Double payload versus the float32 payload?

**Answer:** 12.288 GB and 6.144 GB, excluding BSON/index overhead.

### Exercise 12 — Scalar/Binary

What is the raw payload of a single 1536D vector in float32, int8, and int1?

**Answer:** 6144 B / 1536 B / 192 B.

### Exercise 13 — Chunking

100,000 documents at 20 chunks each. If raised to 40 chunks, how does vector count N change?

**Answer:** 2 million → 4 million vectors; ideal payload and embedding API call counts double.

### Exercise 14 — Quantization

Why can binary quantization reduce index RAM while still requiring significant disk space? What cost does rescoring incur?

### Exercise 15 — Little's Law

100 QPS with 100 ms mean latency corresponds to what average number of in-flight requests?

**Answer:** 10 requests; does not guarantee against bursts or tail spikes.

### Exercise 16 — Serving Cost

Two Search Nodes at \$0.50/hour for 720 hours/month (hypothetical pricing). Total cost?

**Answer:** \$720/month.

### Exercise 17 — Embedding Cost

Two million chunks × 1,000 tokens at an illustrative \$0.05/million tokens. Cost?

**Answer:** 2 billion tokens, \$100 at the assumed rate.

### Exercise 18 — Model Migration

Migrating from a 768D to a 1536D embedding model. Outline re-embedding, new index, canary, rollback, and avoiding mixed query/document vectors.

### Exercise 19 — Index Freshness and ACLs

A document just lost access permissions while the Search index has not synced yet. What must the API do to prevent leaking content?

**Answer:** Verify permissions against the authoritative source rather than relying solely on the Search index.

### Exercise 20 — Production Benchmark

Design a benchmark plan covering golden queries, ENN baseline, ANN sweep, 0.2%–100% filters, concurrent clients, p95/p99, Search RAM/disk, freshness, and TCO.

### Exercise 21 — Scorecard

From the table in Section 24, which candidates satisfy nDCG ≥ 0.78, ANN recall ≥ 0.92, p95 ≤ 120, and p99 ≤ 250 simultaneously? If optimizing for cost, which wins?

**Answer:** A and B pass; B is cheaper in the example.

### Exercise 22 — Hybrid Retrieval

Why might a query containing error code `ERR-1042` need lexical search combined with vector search? How do you measure its quality and cost?

## 28. Summary

Evaluating MongoDB Vector Search requires balancing **independent yet interconnected axes**:

1. **Relevance:** Precision@k, Recall@k, nDCG/MRR, and golden qrels; never treat `vectorSearchScore` as accuracy probability.
2. **ANN recall:** Compare ANN top-k with ENN top-k under the exact same metric, filter, and index; `numCandidates` governs the recall–latency trade-off.
3. **Latency:** Measure embedding, MongoDB, hydration, reranking, and full API timings—including p95/p99, QPS, and concurrency.
4. **Memory:** Compute payload `N×D×bytes`, then add BSON, HNSW graph, Search index, filters, runtime, replicas, and headroom.
5. **Cost:** Account for Search Nodes, source data, embeddings, network, backups, reindexing, and RAG serving; optimize **cost per useful result**.
6. **Correctness:** Pre-filter by tenant, track Search index freshness, and enforce ACLs at an authoritative layer.

**No single index format, dimension, or quantization fits every corpus.** Benchmark with real data and queries, choose a configuration that satisfies SLOs, and maintain observability as data grows.

### Official MongoDB Documentation

- [MongoDB Vector Search](https://www.mongodb.com/docs/vector-search/) — architecture overview.
- [Index Fields for MongoDB Vector Search](https://www.mongodb.com/docs/vector-search/indexes/vector-search-type/) — vector/filter fields, similarity, index methods, and quantization.
- [Run ANN and ENN Queries](https://www.mongodb.com/docs/vector-search/query/aggregation-stages/vector-search-stage/) — `$vectorSearch` syntax, `numCandidates`, `exact`, `filter`.
- [Explain Vector Search Results](https://www.mongodb.com/docs/vector-search/query/explain/) — query performance.
- [Vector Search Benchmark Overview](https://www.mongodb.com/docs/vector-search/benchmark/overview/) — index RAM/disk, quantization, and testing.
- [Vector Search Benchmark Results](https://www.mongodb.com/docs/vector-search/benchmark/results/) — recall/latency/concurrency.
- [Vector Search Benchmark Tests](https://www.mongodb.com/docs/vector-search/benchmark/benchmark-tests/) — how to conduct benchmarks.
- [Vector Search Deployment Options](https://www.mongodb.com/docs/vector-search/deployment/deployment-options/) — Search Nodes, RAM, disk, and serving.
- [Vector Quantization](https://www.mongodb.com/docs/atlas/atlas-vector-search/vector-quantization/) — scalar/binary and rescoring.
- [BSON Binary Data](https://www.mongodb.com/docs/manual/reference/bson-types/) — source vector formats.
- [Aggregation `$project`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/project/) — omitting large fields from results.
