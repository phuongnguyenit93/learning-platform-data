# Indexing Cost, Memory, and Evaluating Result Quality

Semantic search uses vector embeddings to represent the meaning of content. Elasticsearch stores vectors, constructs approximate search structures, and compares query vectors against document vectors. This enables finding semantically similar content even when users do not use the exact keywords in the documents. However, semantic search introduces new costs: generating embeddings, storing many numbers per document, building vector indexes, maintaining HNSW structures, provisioning memory, and evaluating retrieval quality.

A good semantic search system does not merely return results quickly. It must find the right content, preserve access permissions, process fresh data at acceptable cost, and allow quality measurement over a representative query set. Therefore, you must measure in parallel:

- Cost of generating embeddings and updating vectors.
- Storage size of vectors, metadata, `_source`, and replicas.
- CPU, heap, native memory, page cache, and disk.
- Indexing, refresh, merge, and reindex durations.
- Search latency, throughput, and scalability.
- Relevance: whether top-k results are genuinely useful.
- Recall after applying access control and business filters.

In Spring Data Elasticsearch, the application typically incurs the cost of calling the embedding model, batching, serialization, mapping, and retries. Elasticsearch bears the cost of storing and searching vectors. You must evaluate the entire pipeline from source content to API response.

## 1. Lifecycle of a Vector Document

A typical semantic search flow:

    Source content
         |
         v
    Clean / normalize
         |
         v
    Chunking
         |
         v
    Embedding model
         |
         v
    Vector + metadata + source
         |
         v
    Elasticsearch indexing
         |
         v
    Vector index / HNSW
         |
         v
    Query embedding
         |
         v
    kNN retrieval + filters
         |
         v
    Rerank / business rules
         |
         v
    Results for user

Each step carries its own cost. If the embedding model is slow, adding Elasticsearch nodes will not resolve the vector generation bottleneck. If the vector index consumes excessive RAM or disk, optimizing prompts or queries will not solve capacity issues. If results are irrelevant, increasing `num_candidates` may improve recall without fixing a poor embedding model or poorly chunked data.

## 2. Embedding Generation Cost

An embedding model converts text into a multi-dimensional numeric vector. For example, a 768-dimensional model produces a vector of 768 values for every chunk.

Embedding cost depends on:

- Model and parameter count.
- Input token count.
- Number of chunks to process.
- Batch size.
- CPU/GPU hardware or external embedding service.
- Throughput and concurrency.
- Text length.
- How frequently embeddings must be regenerated when content or models change.

When using a token-billed service, costs scale directly with total tokens submitted. When self-hosting models, costs shift to GPU/CPU compute, RAM/VRAM, operations, and latency.

Do not measure only average time for a single sentence. Measure tokens/second, documents/second, p95 latency, cost per million tokens or million chunks, and error rates.

## 3. Chunking Directly Impacts Cost

Long documents are commonly split into multiple chunks before generating embeddings. If a document splits into 20 chunks, the application must generate and store 20 vectors instead of one.

Small chunks:

- Increase vector count.
- Increase embedding and storage costs.
- Can improve pinpoint localization of relevant passages.
- Can lose context if chunks become too short.

Large chunks:

- Reduce vector count.
- Increase tokens per embedding.
- Can blend multiple topics into a single vector.
- Return less precise matches for specific passages.

For instance, a 20,000-token document split into 500-token chunks with a 50-token overlap produces roughly 45 chunks. Lowering chunk size to 200 tokens with a 40-token overlap raises the chunk count substantially. Every chunk adds a vector, metadata, and a graph entry.

Choose chunk size and overlap by testing on real queries. Do not choose based solely on the model's maximum token limit.

## 4. Estimating Vector Counts

If each document produces an average of `C` chunks across `D` documents, the approximate vector count is:

    vector_count = document_count * average_chunks_per_document

Examples:

| Documents | Average chunks | Vectors |
|---:|---:|---:|
| 100,000 | 4 | 400,000 |
| 1,000,000 | 8 | 8,000,000 |
| 5,000,000 | 12 | 60,000,000 |

Vector count can vastly exceed document count. Capacity planning must be based on actual chunk counts, not database record counts alone.

Beyond active chunks, also account for:

- Stale vectors from previous content versions awaiting cleanup.
- New index copies during reindexing.
- Replica shard copies.
- Vectors for multiple languages or models stored in parallel.
- Application-side query vector caches if any.

## 5. Raw Vector Size

With `float32` vectors, each dimension typically occupies 4 bytes. Approximate raw vector size:

    raw_vector_bytes = vector_count * dimensions * 4

For example, with 1 million vectors of 768 dimensions each:

    1,000,000 * 768 * 4
      = 3,072,000,000 bytes
      ~= 3.07 GB
      ~= 2.86 GiB

With 10 million vectors of the same dimensions:

    10,000,000 * 768 * 4
      ~= 30.72 GB

This covers only the `float32` values, excluding the HNSW graph, metadata, `_source`, Lucene segment overhead, doc values if present, translogs, replicas, and temporary space required during merges and reindexing.

Never use raw vector size as total disk sizing. Index a representative sample with production mappings and settings, then measure actual store size.

## 6. Dimensions Affect Memory and Latency

More dimensions mean:

- Higher raw storage per vector.
- More distance calculations.
- Higher transfer cost for query vectors.
- Potentially higher embedding cost depending on the model.
- More values accessed by ANN search.

Examples:

| Dimensions | `float32` bytes/vector |
|---:|---:|
| 128 | 512 bytes |
| 384 | 1,536 bytes |
| 768 | 3,072 bytes |
| 1,024 | 4,096 bytes |
| 1,536 | 6,144 bytes |

Reducing dimensions saves storage and search cost, though it may lose semantic detail and lower relevance. Never truncate dimensions by taking the first 384 values of a 768-dimensional vector unless the model was trained for Matryoshka/truncation usage.

To use fewer dimensions, select a model supporting that output dimension or use a dimensionality reduction method validated by relevance benchmarks.

## 7. Chunk Metadata Also Consumes Storage

Each chunk typically needs metadata to return contextual results:

- `documentId`.
- `chunkId`.
- `tenantId`.
- `ownerId`.
- `allowedRoles` or ACL.
- `sourceType`.
- `language`.
- `title`.
- `section`.
- `createdAt`/`updatedAt`.
- `visibility`/`status`.
- Source text or excerpt.

Vectors often make up the bulk of storage, yet metadata and `_source` can still be substantial, especially when chunks store lengthy text.

If every chunk stores the entire parent document, storage multiplies many times over. Typically store only the chunk text plus a reference to the original document, or keep full sources elsewhere and retain only fields needed for search and display.

Never omit access control metadata just to save a few bytes. Tenant, ACL, and visibility fields are mandatory to prevent data leaks.

## 8. HNSW and Vector Index Cost

Approximate nearest neighbor (ANN) search commonly uses graph structures such as HNSW. HNSW connects vectors into a multi-layer graph to find vectors near a query without comparing against every vector in the index.

HNSW adds overhead beyond raw vector values:

- Graph links between nodes.
- Segment metadata and structures.
- Memory/page cache for reading graphs and vector values.
- CPU for building graphs and searching.
- Disk and I/O for storing and reading vector indexes.

HNSW generally accelerates retrieval compared to brute force on large datasets, yet is not free. Graph parameters affect indexing cost, storage, and search quality.

## 9. HNSW Parameter: `m`

The `m` parameter controls the maximum or target number of connections per node in the graph under the HNSW implementation.

Increasing `m`:

- Creates a denser graph with more links.
- Increases storage and memory overhead.
- Consumes more CPU and memory when indexing the graph.
- Can improve recall on some workloads.
- May allow more effective graph traversal in certain cases.

Decreasing `m`:

- Produces a smaller graph.
- Can make indexing lighter.
- Reduces memory/disk overhead.
- Can lower recall or graph navigability.

No single `m` value fits all datasets. Benchmark using the same dataset, query set, and recall targets.

## 10. Parameter `ef_construction`

`ef_construction` controls how thoroughly candidates are searched while building the HNSW graph. Higher values can produce higher-quality graphs at the expense of slower, more resource-intensive indexing.

Trade-off:

| `ef_construction` | Typical impact |
|---|---|
| Low | Faster builds, potentially weaker graph connectivity |
| High | Higher CPU/time during build, potentially higher recall |

`ef_construction` is a build-time parameter. Do not confuse it with query-time candidate count. Changing build parameters generally requires creating/reindexing the vector index so the new graph is constructed.

## 11. `num_candidates` and Search Cost

In Elasticsearch kNN search, `num_candidates` specifies how many candidates are examined on each shard before merging to pick the global top-k under API semantics.

Increasing `num_candidates` typically:

- Increases chances of finding better nearest neighbors.
- Improves recall.
- Increases CPU and latency.
- Can raise temporary memory and shard-to-coordinator network traffic.

Decreasing `num_candidates` is generally faster, yet risks missing close results.

Query example:

    {
      "knn": {
        "field": "embedding",
        "query_vector": [0.12, 0.31, 0.08],
        "k": 10,
        "num_candidates": 100
      }
    }

The example vector has three dimensions strictly to illustrate syntax; real models must supply the exact dimensions declared in the mapping.

Tuning `num_candidates` balances Recall@k against p95/p99 latency. Do not raise it arbitrarily high just to chase better hits if costs violate your SLO.

## 12. `dense_vector` Mapping

A typical vector mapping:

    PUT knowledge-chunks
    {
      "mappings": {
        "properties": {
          "chunkId": {
            "type": "keyword"
          },
          "documentId": {
            "type": "keyword"
          },
          "tenantId": {
            "type": "keyword"
          },
          "visibility": {
            "type": "keyword"
          },
          "updatedAt": {
            "type": "date"
          },
          "content": {
            "type": "text"
          },
          "embedding": {
            "type": "dense_vector",
            "dims": 768,
            "index": true,
            "similarity": "cosine",
            "index_options": {
              "type": "hnsw",
              "m": 16,
              "ef_construction": 100
            }
          }
        }
      }
    }

This is an illustrative example. Supported fields, default indexing behavior, `index_options`, vector types, and dimension limits change across Elasticsearch versions. Consult the mapping reference matching your cluster.

Set `index=true` only when vector search is needed. If vectors are merely stored for retrieval or external processing, building an ANN index may be unnecessary, though API and mapping support must be considered.

## 13. Selecting the Right Similarity Metric for Your Model

Vector search typically uses:

- Cosine similarity.
- Dot product.
- L2 distance.

The metric must be compatible with how the model generates and normalizes vectors.

Cosine measures vector direction, useful when vector magnitude does not carry the primary signal.

Dot product computes inner product; for normalized vectors, rankings correlate with cosine.

L2 measures Euclidean distance; closer vectors have smaller distances.

Do not swap metrics solely hoping for faster execution without understanding semantics. The same pair of vectors can rank differently under different metrics.

## 14. Vector Normalization

Some embedding models already normalize vectors; others do not. When using `cosine`, Elasticsearch applies metric-specific semantics. When using `dot_product`, many configurations require vectors to be normalized per corresponding limits or implementation rules.

Before indexing:

- Read the model documentation.
- Validate dimensions.
- Validate finite values, rejecting `NaN`/`Infinity`.
- Verify normalization if required by the metric.
- Apply identical preprocessing to documents and queries.

If document vectors are normalized while query vectors are not, or vice versa, scores can shift unexpectedly under magnitude-sensitive metrics.

Never normalize or switch metrics without measuring relevance on a labeled query set.

## 15. Quantization Reduces Vector Cost

Quantization represents vectors at lower precision than `float32`. The goal is reducing storage and memory bandwidth, and sometimes improving search speed.

Common formats:

- `int8`: roughly one byte per dimension.
- `int4`: roughly half a byte per dimension.
- Binary/bit quantization: roughly one bit per dimension before overhead.

Actual disk usage depends on format, metadata, alignment, and how Elasticsearch/Lucene stores vector indexes. Never treat theoretical payload math as total disk usage.

Quantization trade-offs:

- Fewer bytes.
- Potentially lower memory pressure.
- Potentially lower I/O.
- Potentially lower recall or shifted rankings.
- May require oversampling and rescoring against higher-precision vectors.

Enable quantization only after measuring both recall and latency on real data.

## 16. `float32`, `int8`, `int4`, and Binary

Approximate raw vector payload sizes:

| Representation | Approximate bytes per dimension |
|---|---:|
| `float32` | 4 |
| `int8` | 1 |
| `int4` | 0.5 |
| 1-bit | 0.125 |

For 768 dimensions:

| Representation | Approximate raw payload |
|---|---:|
| `float32` | 3,072 bytes |
| `int8` | 768 bytes |
| `int4` | 384 bytes |
| 1-bit | 96 bytes |

These are not exact predictions of index file sizes. HNSW graphs, metadata, and encoding overhead remain. Some quantization modes retain original vectors or dedicated rescoring structures, making real storage higher than raw payload estimates.

## 17. Oversampling and Rescoring

When vectors are quantized, the system can gather a candidate set larger than `k` and recompute scores on a higher-precision representation to choose final results.

Flow:

    Quantized ANN search
          |
          v
    Oversampled candidates
          |
          v
    Rescore with higher precision
          |
          v
       Final top-k

Oversampling can recover recall lost to quantization, while increasing CPU and latency because more candidates are evaluated.

Tuning should measure:

- Recall@k.
- p95/p99 latency.
- Candidate count after oversampling.
- Rescore cost.
- Disk/memory footprint.

Option names and rescoring availability depend on Elasticsearch version and vector index type.

## 18. HNSW and Memory Footprint

Vector index memory cost extends beyond raw vector bytes. Graph links, metadata, and read structures consume resources too. Portions of the data may be memory-mapped and served via the filesystem page cache; exact management depends on Lucene/Elasticsearch version and vector index type.

Do not assume the entire vector index always sits inside the JVM heap. Nor should you assume the entire graph always stays completely resident in RAM. Monitor heap, process RSS, page cache, and disk I/O under realistic workloads.

If the vector working set exceeds RAM available for caching, random searches can trigger heavy disk reads and spike tail latency.

## 19. Shard Count Affects Vector Search

A kNN request across multiple shards may have to locate candidates on each shard and merge results on a coordinating node.

More shards can:

- Increase parallelism.
- Increase the number of graphs traversed.
- Increase request fan-out and network traffic.
- Increase metadata and merge overhead.
- Add candidate merging work.

Too few shards can create oversized shards, slow recovery, and limit parallelism. Too many shards add overhead and fan-out.

Benchmark vector queries on the exact planned shard topology. Do not extrapolate production latency from a single-shard development index.

## 20. Replicas and Vector Search

Replicas increase storage and indexing costs because each copy maintains full data and indexes. However, search load can distribute across primary and replica copies, increasing query throughput in certain workloads.

When choosing replica counts, measure:

- Search throughput.
- p95/p99 latency.
- Indexing throughput.
- Disk usage.
- Recovery time.
- Node distribution.

Replicas do not shrink vector values. They multiply copies of data and increase total build, merge, and recovery effort.

## 21. Filters Affect Vector Search Cost

Semantic search typically restricts results by tenant, ACL, status, language, time, or document type.

Example conditions:

- Documents belonging to the current tenant only.
- Public documents or documents granted to the user.
- Published content only.
- Excluding soft-deleted documents.
- Languages supported by the user.
- Unexpired/effective documents only.

Filters change the eligible document set. When filters are highly selective, ANN search must work harder to find enough candidates within that narrow subset. How filters are applied impacts both recall and latency.

Mandatory access control filters must be enforced within the retrieval query itself or a trustworthy security layer. Never fetch global index top-k and filter only on the frontend.

## 22. Pre-Filter and Post-Filter in kNN

Distinguish two concepts:

- **Pre-filter:** filter conditions applied during kNN search so the algorithm searches nearest neighbors within documents matching the filter.
- **Post-filter:** selects candidates first and filters afterward. Some candidates get discarded, leaving fewer than `k` hits even when other valid documents exist in the index.

Example requiring 10 results for tenant A:

    Index-wide top 10
          |
          v
    Filter tenant A
          |
          v
    May leave only 2 results

When pre-filtering is applied properly:

    Tenant A document set
          |
          v
    kNN within eligible set
          |
          v
    Top 10 for tenant A if enough data exists

In Elasticsearch, `knn` queries provide a `filter` field inside `knn` to act as a pre-filter under API semantics. Filters placed elsewhere, such as `post_filter` or certain wrapper queries, can carry different semantics depending on version and kNN API form.

Read the API reference for your exact query form and test filtered hit counts. Never assume every `bool` filter wrapping a vector query shares identical pre-filter semantics.

## 23. Filtering Inside a kNN Query

Example kNN query with a filter:

    GET knowledge-chunks/_search
    {
      "size": 10,
      "query": {
        "knn": {
          "field": "embedding",
          "query_vector": [0.12, 0.31, 0.08],
          "k": 10,
          "num_candidates": 100,
          "filter": {
            "bool": {
              "filter": [
                {
                  "term": {
                    "tenantId": "tenant-a"
                  }
                },
                {
                  "term": {
                    "visibility": "PUBLISHED"
                  }
                }
              ]
            }
          }
        }
      }
    }

The three-dimensional vector is purely illustrative. Real query vectors must match field mapping dimensions. API syntax and filter placement must be checked against your Elasticsearch version.

Filters inside a `knn` query can serve as pre-filters in Query DSL kNN. Top-level `knn` search options also provide their own `filter` field depending on version. Do not mix syntax across the two APIs arbitrarily.

## 24. Post-Filtering Can Return Fewer Than `k` Results

Example:

    GET knowledge-chunks/_search
    {
      "size": 10,
      "knn": {
        "field": "embedding",
        "query_vector": [0.12, 0.31, 0.08],
        "k": 10,
        "num_candidates": 100
      },
      "post_filter": {
        "term": {
          "tenantId": "tenant-a"
        }
      }
    }

If global top candidates belong mostly to other tenants, `post_filter` strips them after retrieval. The response can contain fewer than 10 hits even though tenant A has plenty of eligible documents.

This degrades user experience and can expose design flaws if permission checks run only post-retrieval. Use pre-filters or proper authorization controls for mandatory conditions.

## 25. Mandatory Security Filters and Optional Business Filters

Separate conditions into two groups:

**Mandatory security filters**

- `tenantId` derived from the authenticated principal.
- ACL/allowed users or roles.
- Document visibility.
- Data classification.
- Soft-delete exclusion.

**Optional business filters**

- Category.
- Language.
- Date range.
- Product status.
- Price range.
- Region.
- Source type.

Mandatory filters must always be applied regardless of client inputs. Optional filters may combine per business needs without weakening security boundaries.

Example `bool` filter:

    {
      "bool": {
        "filter": [
          { "term": { "tenantId": "tenant-a" } },
          { "term": { "visibility": "PUBLISHED" } },
          { "term": { "status": "ACTIVE" } },
          { "terms": { "language": ["vi", "en"] } },
          { "range": { "publishedAt": { "lte": "now" } } }
        ]
      }
    }

Filter context does not calculate relevance scores like query context. Business and security conditions typically belong in filter context because they govern eligibility rather than contributing similarity scores.

## 26. Tenant Filters Must Come from Security Context

Never trust a client-supplied `tenantId` as a source of authority:

    GET /search?tenantId=tenant-b

If the current user belongs to tenant A, the backend must resolve tenant A from the verified principal or security context. Clients must never switch tenants to read another tenant's data.

Safe flow:

1. Authenticate request.
2. Resolve tenant and user identity from a trusted principal.
3. Authorize search action.
4. Construct mandatory tenant/ACL filters on the backend.
5. Merge validated business filters.
6. Send query to Elasticsearch.
7. Map results to response DTOs.

Never let request DTOs overwrite or strip mandatory filters. If an endpoint supports cross-tenant admin search, guard it with an explicit, separately verified permission.

## 27. User and Role ACLs

A document may be shared with specific users or roles:

    {
      "documentId": "doc-100",
      "tenantId": "tenant-a",
      "allowedUserIds": ["user-1", "user-7"],
      "allowedRoles": ["EDITOR", "LEGAL"],
      "visibility": "RESTRICTED"
    }

Queries can use `terms` filters:

    {
      "bool": {
        "filter": [
          { "term": { "tenantId": "tenant-a" } },
          {
            "bool": {
              "should": [
                { "terms": { "allowedUserIds": ["user-1"] } },
                { "terms": { "allowedRoles": ["EDITOR"] } },
                { "term": { "visibility": "PUBLIC" } }
              ],
              "minimum_should_match": 1
            }
          }
        ]
      }
    }

This example only illustrates `OR` logic across user, role, and public visibility. Real policies may involve different `AND`/`OR` rules, deny rules, inheritance, or group memberships. Write out the policy explicitly before translating it into Query DSL.

Never read roles from request parameters. Roles must come from the authenticated principal or a trusted authorization service.

## 28. Nested ACLs When Preserving Attribute Relationships

When an ACL has multiple coupled attributes, `nested` mappings may be necessary to prevent cross-matching fields across array elements.

Example:

    "permissions": [
      {
        "principalType": "USER",
        "principalId": "user-1",
        "permission": "READ"
      },
      {
        "principalType": "ROLE",
        "principalId": "EDITOR",
        "permission": "WRITE"
      }
    ]

If `permissions` is a regular object array, Elasticsearch flattens field values and a query can match `principalId` from one entry with `permission` from another. When conditions must hold on the same element, `nested` mappings and `nested` queries are appropriate.

Example:

    {
      "nested": {
        "path": "permissions",
        "query": {
          "bool": {
            "filter": [
              { "term": { "permissions.principalType": "USER" } },
              { "term": { "permissions.principalId": "user-1" } },
              { "term": { "permissions.permission": "READ" } }
            ]
          }
        }
      }
    }

Nested queries carry higher cost than flat object fields and inflate Lucene document counts. Use them only when relational tuple semantics are strictly needed.

## 29. Business Conditions in Semantic Search

Beyond access permissions, results usually must satisfy business constraints:

- Active products only.
- Published documents only.
- Exclude expired content.
- Regions supported by the user.
- Current active version only.
- Appropriate language only.
- Exclude soft-deleted records.
- In-stock inventory only.

These conditions belong in filter context when they strictly determine document eligibility.

Example:

    {
      "bool": {
        "filter": [
          { "term": { "status": "ACTIVE" } },
          { "term": { "isDeleted": false } },
          { "range": { "validFrom": { "lte": "now" } } },
          {
            "bool": {
              "should": [
                { "range": { "validUntil": { "gte": "now" } } },
                { "bool": { "must_not": { "exists": { "field": "validUntil" } } } }
              ],
              "minimum_should_match": 1
            }
          }
        ]
      }
    }

Time conditions must use a consistent timezone and business clock. Never let clients inject unvalidated `now` or timezone values if doing so can alter eligibility.

## 30. Combining Filters with kNN Retrieval

A production semantic query often combines:

- Vector similarity.
- Tenant filter.
- ACL filter.
- Visibility/status.
- Language.
- Date range.
- Business category.

Example:

    GET knowledge-chunks/_search
    {
      "size": 10,
      "query": {
        "knn": {
          "field": "embedding",
          "query_vector": [0.12, 0.31, 0.08],
          "k": 10,
          "num_candidates": 200,
          "filter": {
            "bool": {
              "filter": [
                { "term": { "tenantId": "tenant-a" } },
                { "term": { "visibility": "PUBLISHED" } },
                { "term": { "language": "vi" } },
                { "term": { "isDeleted": false } },
                { "range": { "publishedAt": { "lte": "now" } } }
              ]
            }
          }
        }
      }
    }

If ACL rules are complex, include nested ACL conditions or cluster-level security enforcement. Do not filter solely by tenant if documents within the same tenant still have private access rules.

## 31. Filter Selectivity and Performance

Filter selectivity is the fraction of documents remaining after applying conditions.

Examples:

| Filter | Remaining document share |
|---|---:|
| `status = ACTIVE` | 90% |
| `language = vi` | 35% |
| `tenant = small tenant` | 0.2% |
| `user ACL` | 0.01% |

Highly selective filters shrink the search space considerably. Depending on configuration and version, Elasticsearch may switch to exact search over the filtered subset when beneficial; in other cases ANN remains active.

Do not assume more selective filters always yield lower latency. Nested ACLs, shard counts, graph traversal, and candidate strategies all influence execution.

Benchmark across selectivity tiers:

- Large tenants.
- Small tenants.
- Public access.
- Restricted users.
- Multi-role ACLs.
- Combined business conditions.

Measure recall and latency for every tier rather than benchmarking only one common filter.

## 32. Filters Alter Recall

With post-filtering, top-k counts can drop or miss valid documents. With pre-filtering, ANN searches within the eligible set, yet ANN quality still depends on the graph, candidate budget, and selectivity.

When evaluating recall, ground truth must be computed over the eligible document set after filtering. Do not compare tenant A's query results against global index nearest neighbors and conclude recall is low.

Example:

1. Filter down to tenant A's documents.
2. Compute exact top-k over tenant A's vectors.
3. Run ANN with the same tenant A filter.
4. Compare result IDs.

This is the proper way to evaluate filtered vector retrieval.

## 33. Exact Vector Search as Ground Truth

ANN is approximate search. To measure recall, you need an exact nearest-neighbor baseline over a controlled dataset or a reliable brute-force calculation.

You can use `script_score` to compute vector similarity over filtered documents:

    GET knowledge-chunks/_search
    {
      "size": 10,
      "query": {
        "script_score": {
          "query": {
            "bool": {
              "filter": [
                { "term": { "tenantId": "tenant-a" } },
                { "term": { "visibility": "PUBLISHED" } }
              ]
            }
          },
          "script": {
            "source": "cosineSimilarity(params.query_vector, 'embedding') + 1.0",
            "params": {
              "query_vector": [0.12, 0.31, 0.08]
            }
          }
        }
      }
    }

The three-dimensional vector is illustrative. `script_score` evaluates every document matching the filter, making it CPU-intensive on large sets. Use it for ground truth generation or sufficiently small subsets, not by default at production scale.

The script metric must align with the model/mapping metric. Adding a constant to cosine scores in the example keeps scores non-negative for certain setups without changing relative document rankings.

## 34. Recall@k

Recall@k measures how many items from the exact top-k appear in ANN top-k.

    recall@k =
      |ANN_top_k ∩ Exact_top_k| / k

Example exact top-5:

    [A, B, C, D, E]

ANN top-5:

    [A, C, F, D, G]

Intersection contains A, C, D, so:

    recall@5 = 3 / 5 = 0.60

Recall measures how well ANN recovers nearest neighbors under the vector metric. It does not prove those documents are actually useful to users; exact vector neighbors can still lack business relevance.

## 35. Precision@k

Precision@k measures the fraction of top-k results judged relevant:

    precision@k =
      relevant results in top-k / k

If 4 out of the top 5 results are relevant:

    precision@5 = 4 / 5 = 0.8

Precision requires relevance judgments supplied by human raters or trustworthy interaction data. Precision cannot be derived from vector distance alone.

## 36. MRR

Mean Reciprocal Rank (MRR) evaluates the position of the first relevant hit.

For a single query:

    reciprocal_rank = 1 / rank_of_first_relevant_result

If the first relevant result appears at rank 2:

    RR = 1 / 2 = 0.5

MRR is the mean reciprocal rank across multiple queries. MRR suits scenarios where users mainly seek one right answer near the top, though it does not capture overall quality across the entire top-k.

## 37. NDCG@k

Normalized Discounted Cumulative Gain (NDCG) evaluates rankings with graded relevance levels. Higher-relevance documents appearing higher in the list receive greater credit.

Standard DCG:

    DCG@k = sum((2^rel_i - 1) / log2(i + 1))

    NDCG@k = DCG@k / IDCG@k

Where `rel_i` is the relevance grade at position `i`, and `IDCG` is the ideal DCG when results are sorted by descending relevance.

NDCG works well when raters assign grades such as:

- 0: not relevant.
- 1: weakly relevant.
- 2: relevant.
- 3: highly relevant.

NDCG helps compare rankings across lexical, vector, and hybrid retrieval.

## 38. MAP and Hit Rate

Mean Average Precision (MAP) summarizes precision at every position holding a relevant result and averages across queries. MAP is useful when multiple relevant documents exist per query and overall ranking quality matters.

Hit Rate@k measures the share of queries having at least one relevant result in top-k:

    hit_rate@k =
      queries with >= 1 relevant hit in top-k
      / total queries

Hit Rate is intuitive for use cases seeking one matching document or product. However, it does not show how many relevant items appeared or their rank positions.

## 39. Business Relevance Differs from ANN Recall

Two distinct questions:

- ANN recall: does vector search approximate the nearest vectors under the metric?
- Business relevance: do results actually solve the user's intent?

A system with high Recall@10 yet low NDCG may be recovering exact nearest vectors while the embedding model fails to capture domain semantics.

Conversely, a reranker may order top candidates well while low ANN recall prevents essential documents from ever reaching the candidate set.

Therefore evaluate both retrieval and ranking:

1. ANN Recall@k against exact vector neighbors.
2. Precision/NDCG/MRR against relevance judgments.
3. Latency and throughput.
4. Results after mandatory filters and business rules.

## 40. Building a Query Evaluation Set

An evaluation set should contain realistic queries or queries authored by domain experts:

- Short and long queries.
- Natural-language questions.
- Synonyms.
- Typos.
- Proper names.
- Multi-intent questions.
- Multilingual queries.
- Queries with no matching documents.
- Queries requiring restricted access permissions.
- Queries with business filters such as status/date/category.

Each query entry should specify:

- Query text.
- Simulated user/tenant context.
- Business filters.
- Relevant document/chunk IDs.
- Relevance grades if computing NDCG.
- Query family.
- Expected behavior when no matches exist.

Do not rely only on easy queries sharing exact wording with documents. Semantic search must be tested on paraphrases, synonyms, and natural phrasing.

## 41. Creating Relevance Judgments

Relevance judgments can come from:

- Human annotation by domain experts.
- Pairwise comparisons.
- Audited, de-biased search logs.
- Click/conversion signals adjusted for position bias.
- Expert-validated synthetic queries.

Never treat raw clicks as absolute ground truth. Users often click the top result due to position bias rather than true relevance.

Provide clear annotation guidelines:

- Does the document answer the question accurately?
- Does it contain sufficient information?
- Is it still valid and unexpired?
- Does it belong to the right tenant/visibility?
- Is it directly relevant or merely topically adjacent?

A strong evaluation set should be versioned to track model and mapping comparisons over time.

## 42. Train/Test Split for Query Evaluation

When using query logs for tuning or training rerankers, separate tuning sets from holdout sets:

- Development set for crafting queries and filters.
- Validation set for selecting parameters.
- Holdout test set for final evaluation.

Repeatedly tuning against the same queries and labels risks overfitting. A change that improves validation while degrading holdout warrants investigation.

For time-ordered data, time-based splits simulate future unseen queries and documents.

## 43. Evaluating by Tenant and ACL

Crucially, relevance is meaningful only over documents the user is permitted to read.

Evaluations must simulate:

- Large and small tenants.
- Users with broad and narrow permissions.
- Public and restricted documents.
- Users belonging to multiple groups.
- ACLs changing over time.
- Documents whose permissions were revoked.

Metrics should be computed after applying security filters. A relevant hit that the user is unauthorized to view must be treated as invalid, not counted as a good hit.

Alongside relevance, add security assertions:

- Zero documents from other tenants.
- Zero documents outside ACL grants.
- Revoked documents never appear.
- Post-filtering never leaks snippets/metadata in other response fields.

## 44. Evaluating Multilingual Search

If the system supports multiple languages, stratify the evaluation set by language and cross-language queries:

- Vietnamese query, Vietnamese document.
- English query, English document.
- Vietnamese query, English document.
- Queries containing untranslated technical terms.
- Queries containing proper names or product codes.

Multilingual embedding models support cross-language retrieval, yet quality varies unevenly across languages. Measure NDCG/Recall per language pair rather than averaging everything together.

Language filters can improve precision or shrink candidate spaces, though they may exclude valid answers when a user queries in one language and helpful documentation exists in another.

## 45. Evaluating Chunking

Chunking shapes the retrieval unit. Overly small chunks lack context; overly large chunks blend multiple ideas into one vector.

Experiment with:

- Chunk size.
- Overlap.
- Paragraph/heading boundaries.
- Title/section metadata inclusion.
- Parent document retrieval.
- Returning chunks versus whole documents.

Metrics:

- Recall@k by chunk ID.
- Recall by parent document ID.
- NDCG by chunk relevance.
- Context completeness.
- Duplicate chunk rate.
- Index size and embedding cost.

If multiple chunks from one document dominate top-k, results lack diversity. Consider collapsing by document or reranking to surface distinct sources.

## 46. Evaluating Embedding Models

When comparing models:

- Use the exact same source corpus.
- Use the exact same chunking strategy.
- Generate embeddings for both documents and queries using each candidate model.
- Never mix vectors from two models in the same space unless designed for compatibility.
- Build a separate index per model/version.
- Compare relevance, latency, cost, and storage.

Larger models can raise semantic relevance while slowing embedding generation and expanding vector dimensions. Smaller models cut cost yet may struggle on domain vocabulary or less common languages.

Do not pick a model based solely on public leaderboards. Domain vocabulary, internal docs, and query distributions often differ sharply from benchmark datasets.

## 47. Embedding Model Versioning

Tag every vector with model/version metadata or isolate it via versioned indexes:

    {
      "documentId": "doc-100",
      "chunkId": "doc-100-03",
      "embeddingModel": "embedding-model-v2",
      "embeddingVersion": 2,
      "embedding": [ ... ]
    }

Never index vectors from model v1 alongside query vectors from model v2 in the same space unless compatible.

When switching models:

1. Create a new index version.
2. Re-chunk if needed.
3. Generate new embeddings.
4. Index in batches.
5. Run the evaluation set.
6. Compare latency, storage, and relevance.
7. Cut over aliases or traffic routing.
8. Retain rollback capability per policy.

## 48. Re-embedding Can Be the Largest Cost

Changing models, dimensions, or preprocessing typically requires regenerating embeddings across the whole corpus.

Costs include:

- Reading the entire source corpus.
- Tokenization/chunking.
- Calling the embedding model.
- API fees or GPU compute time.
- Bulk indexing.
- Disk space for old and new indexes coexisting.
- Merges and refreshes.
- Validation and cutover.

Estimate:

    total_embedding_tokens =
      sum(tokens in all chunks)

    embedding_cost =
      total_embedding_tokens * provider_price_per_token

When self-hosting, estimate from throughput benchmarks and GPU-hours. Factor in retries, failures, and backfill headroom.

Do not run full-corpus re-embedding during peak hours if jobs compete for CPU/GPU/disk with live interactive traffic. Use queues, rate limits, and backpressure.

## 49. Embedding Caching and Deduplication

When identical text appears repeatedly, embeddings can be cached by a hash of:

- Normalized content.
- Model/version.
- Preprocessing version.
- Chunking configuration.

Cache keys must include model and preprocessing versions. Identical text under a different model must yield a different embedding.

Deduplication lowers cost for repeated documents or chunks, though access controls and metadata require care. Two documents with identical text in different tenants do not share access permissions or lifecycles.

Never let a shared cache key leak content across tenant boundaries. Even vector-only caches may require metadata governance and retention controls.

## 50. Batching and Concurrency for Embeddings

Batching improves model throughput by amortizing per-request overhead. Yet oversized batches:

- Spike memory/VRAM.
- Raise latency for the first item.
- Risk exceeding token limits.
- Make retries costlier when a batch fails.

Too little concurrency leaves GPUs/CPUs idle; too much creates queuing and memory pressure.

Benchmark:

- Batch size by input count.
- Total tokens per batch.
- Model latency.
- Throughput in tokens/second.
- p95/p99 latency.
- GPU memory/utilization or CPU usage.
- Error/retry rate.

For external embedding services, respect provider rate limits and retry policies. Never infinitely retry validation errors or oversized inputs.

## 51. Spring Data Model for Vector Documents

An entity can store vectors alongside metadata:

    @Document(indexName = "knowledge-chunks")
    public class KnowledgeChunk {

        @Id
        private String chunkId;

        private String documentId;
        private String tenantId;
        private String visibility;
        private String language;
        private String content;

        @Field(type = FieldType.Dense_Vector, dims = 768)
        private float[] embedding;
    }

This is a high-level example. Enum names, annotation attributes, similarity, and index options vary across Spring Data Elasticsearch versions. Some projects manage mappings via JSON/index templates instead of annotations for exact control over vector index options.

Annotation/mapping dimensions must match the model. Never index vectors whose length differs from the mapping.

## 52. Generating Embeddings Before Saving

Services usually invoke the embedding model prior to constructing the document:

    public KnowledgeChunk indexChunk(SourceChunk source) {
        float[] vector = embeddingClient.embed(source.text());

        KnowledgeChunk chunk = new KnowledgeChunk();
        chunk.setChunkId(source.id());
        chunk.setDocumentId(source.documentId());
        chunk.setTenantId(source.tenantId());
        chunk.setContent(source.text());
        chunk.setEmbedding(vector);

        return repository.save(chunk);
    }

In production, you do not necessarily call embedding synchronously during document creation requests. Persist the source and an outbox event first, then let workers embed and index asynchronously. This gives control over retries, throughput, and backpressure.

If embedding generation fails, never mark the document as semantically indexed. Record pending/failed status for retry.

## 53. Bulk Indexing Vectors in Spring Data

Vector documents are usually indexed in batches:

    List<IndexQuery> queries = chunks.stream()
        .map(chunk -> IndexQuery.builder()
            .withId(chunk.getChunkId())
            .withObject(chunk)
            .build())
        .toList();

    operations.bulkIndex(
        queries,
        BulkOptions.builder()
            .withRefreshPolicy(RefreshPolicy.NONE)
            .build(),
        IndexCoordinates.of("knowledge-chunks")
    );

Size batches by byte weight. A batch of 1,000 768-dimensional `float32` vectors takes roughly 3 MB for raw vectors alone, before adding source text, metadata, JSON encoding, and request overhead. At 10,000 vectors, payloads grow to tens of megabytes.

Bulk responses can contain partial failures. Inspect per-item outcomes, retry transient errors, and send mapping/dimension errors to a DLQ or error store. Never infinitely retry the entire batch.

## 54. Querying Vectors via Spring Data

Spring Data Elasticsearch offers vector search abstractions, though APIs change across versions and Elasticsearch Java API Client releases.

In modern versions, `NativeQuery` expresses kNN search via corresponding vector/kNN APIs. Builder names and `KnnSearch` types differ across releases. In real implementations:

- Check your Spring Data Elasticsearch version.
- Check the managed Elasticsearch Java API Client version.
- Use APIs aligned with your server version.
- Verify filters sit in the proper pre-filter slot.
- Confirm the final Query DSL via integration tests or redacted request logging.

Never copy builder APIs from a different major release assuming compatibility.

## 55. Query DSL with Vector Filters

When exact control over semantics is needed, use `NativeQuery` or the Java API Client to build filtered kNN requests.

DSL example:

    {
      "size": 10,
      "query": {
        "knn": {
          "field": "embedding",
          "query_vector": [ ... ],
          "k": 10,
          "num_candidates": 200,
          "filter": {
            "bool": {
              "filter": [
                { "term": { "tenantId": "tenant-a" } },
                { "term": { "visibility": "PUBLISHED" } }
              ]
            }
          }
        }
      }
    }

Filters must be built on the backend from security context and business policy. Never accept arbitrary DSL from clients and splice it into queries unvalidated.

## 56. Exact Scoring with `script_score`

`script_score` can evaluate vector similarity over a filtered document set:

    {
      "query": {
        "script_score": {
          "query": {
            "bool": {
              "filter": [
                { "term": { "tenantId": "tenant-a" } },
                { "term": { "visibility": "PUBLISHED" } }
              ]
            }
          },
          "script": {
            "source": "cosineSimilarity(params.q, 'embedding') + 1.0",
            "params": {
              "q": [ ... ]
            }
          }
        }
      }
    }

This performs exact scoring over candidates selected by the inner query, yet usually evaluates every document matching the filter. If a tenant holds millions of chunks, cost can be high.

Use exact scoring for:

- Small ground-truth evaluations.
- Very small filtered subsets.
- Exhaustive scoring requirements that have been benchmarked.

On large corpora, ANN is usually preferable. You can retrieve candidates with ANN and rerank within that candidate set.

## 57. Hybrid Search and Combination Cost

Semantic search is often paired with lexical search because vectors capture meaning while lexical search handles exact terms, IDs, proper names, and technical codes.

A hybrid pipeline:

    Lexical retrieval ----\
                           +--> Fusion / rerank --> top results
    Vector retrieval -----/

Two common strategies:

- Reciprocal Rank Fusion (RRF).
- Weighted score combination or a reranker model.

RRF merges ranks without requiring lexical and vector scores to share a scale. Weighted scores require calibration because both score types follow distinct distributions.

Hybrid search improves quality in many domains while adding query cost, candidate merging, and potentially reranker inference.

Evaluate lexical-only, vector-only, and hybrid search on the identical evaluation set. Never assume hybrid is better merely because it returns more hits.

## 58. Reranking

Rerankers take candidate documents and the query to score relevance in greater detail, often using cross-encoders or specialized models.

Reranking can raise NDCG/MRR while increasing:

- Model inference cost.
- Latency.
- CPU/GPU usage.
- Memory.
- Network and payload transfer.

Cap candidate counts and rerank only top-N items. Measure marginal relevance gain relative to added latency and cost.

If ANN fails to bring a relevant document into the candidate set, the reranker cannot discover it on its own. Candidate recall remains critical.

## 59. Evaluating the Entire Pipeline

A search pipeline spans multiple stages:

1. Query normalization.
2. Query embedding.
3. Security/business filter construction.
4. Vector/lexical retrieval.
5. Candidate fusion.
6. Reranking.
7. Duplicate collapsing or parent document grouping.
8. Response projection.

Measure per-stage and end-to-end latency:

| Stage | Metrics |
|---|---|
| Query embedding | latency, tokens, errors, cost |
| Filter construction | duration, policy failures |
| ANN retrieval | took, candidate count, recall |
| Lexical retrieval | latency, hit count |
| Fusion | duration, overlap |
| Rerank | latency, model cost |
| Response mapping | allocations, serialization |
| End-to-end | p50/p95/p99, error rate |

If query embedding accounts for 70% of latency, tuning HNSW will barely budge user-perceived latency. If the reranker is slow, trimming candidate counts or optimizing the reranker model helps far more.

## 60. Measuring Index Throughput and Ingestion Lag

Because semantic indexing spans multiple stages, measuring Elasticsearch `documents/second` alone is insufficient.

Monitor:

- Source records discovered.
- Chunks generated/second.
- Embedding tokens/second.
- Embedding latency.
- Embedding failures/retries.
- Vector documents indexed/second.
- Bulk item failures.
- Time from source update to searchable.
- Backlog age.

A pipeline may index fast in Elasticsearch while embedding workers lag behind, leaving search projections stale. Alternatively, embedding may run fast while Elasticsearch bulk writes reject payloads.

Place bounded queues and backpressure between chunking, embedding, and indexing. Never accumulate millions of pending chunks inside JVM heap.

## 61. Reindexing and Model Migration

Changing dimensions, similarity, or vector index options typically requires a fresh index. Vector mappings generally cannot be altered arbitrarily after index creation.

Workflow:

1. Create a new index version with the target mapping.
2. Lock down model and preprocessing versions.
3. Generate embeddings in batches.
4. Index and inspect bulk failures.
5. Measure store size, segments, memory, and latency.
6. Run the evaluation set.
7. Reconcile document/chunk counts.
8. Switch aliases or query routing.
9. Monitor quality and latency post-cutover.
10. Retain the old index for rollback per retention policy.

Never mix vectors from incompatible models inside the same field just to avoid reindexing.

## 62. Rebuilding HNSW and Build-Time Costs

Changing `m`, `ef_construction`, or vector representation may require rebuilding graph indexes. This is a build-time cost separate from query-time `num_candidates` tuning.

Build cost depends on:

- Vector count.
- Dimensions.
- Graph parameters.
- Bulk concurrency.
- CPU and disk.
- Shard topology.
- Quantization.

Measure ingestion duration until the index settles, not merely bulk HTTP response times. Refreshes and merges continue executing after bulk requests return.

Never alter HNSW build parameters directly on a production index without checking reindex and version requirements.

## 63. Disk, RAM, and Capacity Planning for Vector Indexes

A capacity model:

    vector_raw_bytes =
      vector_count * dimensions * bytes_per_value

    primary_index_size =
      vector_raw_bytes
      + graph_overhead
      + source_and_metadata
      + lucene_overhead

    cluster_storage =
      primary_index_size * (1 + replicas)

    required_capacity =
      cluster_storage
      + merge_and_recovery_headroom
      + reindex_overlap
      + growth_margin

Graph overhead and remaining terms must be measured from a sample index. No universal multiplier fits every mapping, version, and vector index type.

RAM serves heap, native memory, and page cache. Large vector indexes do not mean every raw vector must fit inside JVM heap. Measure working sets, page cache hit ratios, disk latency, and query access patterns.

## 64. Benchmarking Vector Indexing

An indexing benchmark should hold fixed:

- Vector count.
- Dimensions.
- Vector distribution.
- Chunk size.
- Mapping and similarity.
- HNSW parameters.
- Quantization type.
- Shard/replica count.
- Bulk size in bytes.
- Refresh interval.
- Hardware.

Measure:

- Embedding generation throughput.
- Bulk indexing throughput.
- p95 bulk latency.
- Primary and total index size.
- Segment count.
- Merge time.
- Heap/RSS/page cache.
- Disk throughput/latency.
- 429s and item failures.
- Time until search visibility stabilizes.

Test across several batch sizes and concurrency levels. Never pick the largest batch size simply for brief peak throughput if merge backlogs and memory grow unbounded.

## 65. Benchmarking Vector Search

A search benchmark requires:

- Representative query set.
- Exact top-k ground truth.
- Tenant/ACL/business filters.
- Varying `k` and `num_candidates`.
- Production-like shard topology.
- Recorded cache state.
- Realistic concurrency and arrival rates.

Measure:

- Recall@k.
- Precision/NDCG/MRR against labels.
- p50/p95/p99 latency.
- Throughput.
- Error/rejection rate.
- Candidate counts.
- CPU, heap, RSS, page cache, and disk I/O.
- Result counts after filtering.

Never trade away security to improve recall or cut latency. Unauthorized hits must be excluded before returning responses.

## 66. Evaluating Filtered Recall

For each query and user context:

1. Build the eligible document set using mandatory filters.
2. Compute exact top-k over that eligible set.
3. Execute ANN with the identical pre-filter.
4. Compare ID sets and calculate Recall@k.
5. Compute relevance metrics over valid hits.
6. Record latency and hit counts.

Repeat for large/small tenants, broad/narrow ACLs, public/restricted visibility, language, and date filters.

If post-filtering is used in a specific flow, measure the rate of queries returning fewer than `k` hits and compare against pre-filtering. Mandatory access control must never rely on frontend filtering.

## 67. A/B Testing and Online Quality

Offline evaluation enables rapid, repeatable comparisons, while online behavior can differ due to real query distributions and live user intent.

An A/B test should:

- Split traffic randomly and deterministically.
- Enforce identical security policies across variants.
- Never show one group data denied to another.
- Track clicks, useful results, conversions, or task completion.
- Monitor latency and errors.
- Segment metrics by query family and tenant cohort.
- Include guardrails for zero-result rates and restricted access.

Never optimize raw click-through rate alone when clicks do not reflect quality. Pair with human reviews, dwell time, or task success.

## 68. Cost per Useful Result

A helpful operational metric is the cost incurred to deliver one result judged useful.

Track:

    cost_per_useful_result =
      total_embedding_and_search_cost
      / useful_results_count

This composite metric requires clear definitions of useful results and cost windows. It helps compare a larger/slower model against a smaller/faster model when quality differs.

For example, model A might cost twice as much per inference yet lift the share of queries returning useful results from 60% to 90%. Its cost per useful result can still be lower.

Do not optimize cost per vector alone if the system produces many irrelevant vectors or poor chunks.

## 69. Tracking Costs by Model and Tenant

Consider recording:

- Embedding tokens by model/version.
- Chunks per tenant.
- Re-embedding runs.
- Vector counts and index sizes.
- Query and rerank counts.
- CPU/GPU time.
- Search latency and quality.

Avoid overly high metric tag cardinality. For large multi-tenant systems, write usage to dedicated tables or analytics stores instead of creating per-document or per-user metric series.

Never log raw content just for cost accounting. Token counts, model names, dimensions, and event IDs suffice for operational metrics.

## 70. Common Pitfalls

### Sizing Storage by Document Count Alone

One document can generate many chunks and vectors. Size around vector counts.

### Treating `float32` Raw Size as Total Index Size

Omits HNSW graphs, metadata, `_source`, Lucene overhead, replicas, and merge headroom. Measure on a sample index.

### Increasing Dimensions Without Measuring Quality

Larger vectors raise storage and search costs without guaranteeing higher relevance. Evaluate on a query set.

### Reducing Dimensions by Truncating Vectors

Can break the embedding space. Use models supporting smaller dimensions or validated reduction techniques.

### Arbitrarily Raising `m` and `ef_construction`

Raises indexing CPU/memory and storage. Benchmark recall vs. build time.

### Raising `num_candidates` Without Bounds

Recall may climb while latency and CPU spike. Find the balance matching your SLO.

### Using Post-Filters for Access Control

Can return fewer than `k` results and creates risks if filters are missed on a response path. Use mandatory pre-filters and security enforcement.

### Trusting Client-Supplied `tenantId`

Clients can alter tenants to access unauthorized data. Resolve tenants from verified principals.

### Evaluating Only Nearest-Neighbor Recall

Nearest vectors are not necessarily relevant hits. Use human relevance judgments with NDCG/MRR/Precision.

### Evaluating Relevance Without Measuring ANN Recall

Leaves you blind to whether candidate generation missed documents or the embedding model failed. Measure both exact-neighbor recall and business relevance.

### Running `script_score` on Large Corpora Like ANN

Exact scoring can scan the whole filtered set and exhaust CPU. Reserve it for ground truth or small subsets.

### Mixing Embeddings from Two Models

Vector spaces can be incompatible. Use separate index versions and re-embed.

### Re-embedding Without Queues or Backpressure

Can exhaust GPU, memory, or disk. Batch, rate-limit, and monitor backlogs.

### Forgetting Index Overlap During Migrations

Old and new indexes coexist temporarily. Capacity must reserve reindex headroom.

### Evaluating Only with Easy Queries

Omits paraphrases, multilingual cases, rare terms, zero-result queries, and ACL scenarios. Use a representative query set.

### Skipping Permission Checks After Filtering

A relevant hit that the user lacks permission to read is still a security bug. Enforce security assertions independently of relevance metrics.

## 71. Semantic Search Optimization Workflow

An ordered optimization process:

1. Measure current document, chunk, and vector counts.
2. Measure token distributions and embedding costs.
3. Select suitable models, dimensions, normalization, and similarity.
4. Optimize chunking using an evaluation set.
5. Estimate raw vector storage, then index a sample to measure actual footprint.
6. Benchmark HNSW parameters and quantization.
7. Size shards and replicas for throughput, recovery, and capacity.
8. Construct mandatory security filters from trusted principals.
9. Place business conditions in filter context.
10. Verify kNN filters execute as pre-filters per API/version.
11. Build exact ground truth over eligible documents.
12. Measure Recall@k and relevance metrics.
13. Tune `num_candidates` and reranking for quality/latency targets.
14. Run mixed workloads and benchmark concurrent indexing and searching.
15. Version models, mappings, datasets, and evaluations.
16. Reindex into a new index version for incompatible changes.
17. Monitor cost, lag, recall, relevance, and access violations post-launch.

## Conclusion

Semantic search incurs costs across both the embedding pipeline and the Elasticsearch vector index. Vector counts depend on document count and chunking; raw `float32` vectors require roughly dimensions times 4 bytes, while total index size also includes HNSW graphs, metadata, `_source`, Lucene segments, replicas, and merge/reindex headroom. Dimensions, `m`, `ef_construction`, quantization, and `num_candidates` govern trade-offs across indexing time, storage, memory, latency, and recall. Benchmark on data, queries, and shard topologies resembling production.

Results must be evaluated at two layers: ANN recall against exact nearest neighbors, and business relevance via Precision@k, Recall@k, MRR, NDCG, or MAP using relevance judgments. With tenant/ACL and business rules, ground truth must be computed strictly over eligible documents. Mandatory access filters must derive from authenticated principals and apply in the retrieval/security layer; never trust client-supplied tenants or rely solely on frontend post-filtering. Combining monitoring for cost, embedding throughput, vector count, disk/RAM, p95/p99 latency, quality, and security assertions enables choosing models, chunking, HNSW, quantization, and query strategies that deliver measurable real-world impact.
