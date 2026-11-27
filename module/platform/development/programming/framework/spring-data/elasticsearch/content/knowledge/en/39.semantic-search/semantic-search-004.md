# Similarity, kNN, and the Trade-off Between Speed and Accuracy

Vector search represents each document and query as a numeric sequence (embedding) and ranks documents by how close the two vectors are. Elasticsearch supports multiple similarity metrics and two primary search approaches: exact search across all eligible documents (exact kNN) and approximate search using index structures such as HNSW (approximate kNN).

Exact search returns accurate results under the chosen metric, but must score every vector in the candidate set. Approximate kNN skips most vectors to reduce latency at the cost of potentially missing some nearest neighbors. In Elasticsearch, `k` specifies how many neighbors to retrieve, while `num_candidates` controls how many candidates are explored per shard. Increasing `num_candidates` typically improves recall but makes queries slower.

Spring Data Elasticsearch provides `FieldType.Dense_Vector`, `KnnSimilarity`, and `NativeQuery.withKnnSearches(...)` to declare fields and issue kNN queries. Choosing the metric, embedding model, vector size, HNSW settings, and candidate budget should be evaluated against real data.

## 1. Vector Similarity and k-Nearest Neighbors

An embedding is a numeric vector capturing semantic features of text, images, or other data. For instance, a model might convert the phrase "lightweight laptop" into a 384-dimensional vector:

~~~text
[0.12, -0.08, 0.31, ..., -0.04]
~~~

Documents and queries pass through the same embedding model to produce vectors in the same space. The system measures the distance or similarity between the query vector and document vectors, then ranks documents accordingly.

**k-nearest neighbors (kNN)** is the problem of finding the `k` vectors closest to a query under a specific metric. The letter `k` in kNN stands for the number of neighbors to retrieve, not the name of a metric.

Example:

- A query vector represents a question about "how to cook beef pho".
- Elasticsearch finds documents whose embeddings are close to the query vector.
- Results may include articles about pho broth, selecting beef cuts, and blanching rice noodles.
- These documents might not contain the exact wording of the question yet are semantically close.

Results are only meaningful when the embedding model and metric match. If document vectors were generated with model A while the query vector was generated with model B, both vectors may have the same dimensions yet live in different representation spaces. Distance measurements then become unreliable.

### 1.1. Similarity and Distance

Two common ways of expressing closeness:

- **Similarity:** larger values indicate two vectors are more alike.
- **Distance:** smaller values indicate two vectors are closer.

Elasticsearch ranks by `_score` in ascending order of relevance: higher scores rank higher. For distance-based metrics, Elasticsearch converts distances into positive scores to preserve the same ranking convention.

Do not directly compare raw similarity values with `_score`. They are two distinct quantities. Likewise, do not assume `_score = 0.9` means a 90% probability of relevance.

## 2. Common Similarity Metrics

Elasticsearch supports the following primary metrics for dense vectors:

- `cosine`
- `dot_product`
- `max_inner_product`
- `l2_norm`

Metric selection must match how the embedding model was trained and normalized.

### 2.1. Cosine Similarity

Cosine similarity measures the angle between two vectors, independent of vector magnitude.

For vectors A and B:

\[
\operatorname{cosine}(A,B)
=
\frac{A \cdot B}{\|A\| \|B\|}
\]

Mathematical values range from -1 to 1:

| Value | Geometric meaning |
| ---: | --- |
| 1 | Same direction. |
| 0 | Orthogonal. |
| -1 | Opposite direction. |

Example of two vectors pointing in the same direction with different magnitudes:

~~~text
A = [1, 2]
B = [2, 4]
~~~

Cosine similarity equals 1 because both vectors share the same direction. Euclidean distance between them, however, is non-zero.

Cosine often suits text embeddings and many semantic embeddings, especially when vector magnitude carries no relevance signal. You cannot conclude all models must use cosine; inspect how the model was trained.

With `similarity: cosine` in the mapping, Elasticsearch normalizes document vectors at index time to optimize internal computations. Vectors with magnitude zero are invalid for cosine because direction is undefined.

Elasticsearch converts cosine into a document score:

\[
\_score = \frac{1 + \operatorname{cosine}(q,d)}{2}
\]

This maps scores into a non-negative range. It is a ranking transformation, not a probability.

### 2.2. Dot Product

Dot product is the sum of element-wise products:

\[
A \cdot B = \sum_{i=1}^{n} A_i B_i
\]

Dot product is sensitive to both direction and magnitude. If vectors are normalized to unit length, dot product equals cosine similarity.

With `element_type: float`, Elasticsearch requires both document vectors and query vectors to have unit length when the mapping uses `similarity: dot_product`. The score is computed as:

\[
\_score = \frac{1 + (q \cdot d)}{2}
\]

The benefit is efficient computation. The risk is that if the application forgets to normalize query vectors or document vectors, results violate the metric's assumptions.

Use `dot_product` when the model or embedding pipeline specifies unit-normalized vectors. Do not choose it merely because the name sounds simple or scores appear higher.

### 2.3. Maximum Inner Product

`max_inner_product` (MIP) is also based on the inner product, but does not require normalized vectors. Vector magnitude can strongly influence scores.

This metric fits certain models trained with a maximum inner product search objective, where magnitude carries meaning in the objective function.

Elasticsearch transforms the result so scores remain non-negative:

- If inner product is less than 0: `score = 1 / (1 - inner_product)`.
- If inner product is greater than or equal to 0: `score = inner_product + 1`.

Do not arbitrarily substitute MIP for cosine. The two metrics can rank differently because one accounts for magnitude while the other focuses on vector direction.

### 2.4. L2 Norm (Euclidean Distance)

L2 norm measures the Euclidean distance between two vectors:

\[
d(A,B) = \sqrt{\sum_{i=1}^{n}(A_i-B_i)^2}
\]

Smaller distance means two vectors are closer. Elasticsearch converts distance into score:

\[
\_score = \frac{1}{1 + d(q,d)^2}
\]

Thus documents with smaller distances receive higher scores.

L2 fits when the vector space and training objective rely on Euclidean distance. When magnitude variations carry meaning, L2 reflects differences in both direction and magnitude.

### 2.5. Comparing the Metrics

| Metric | Primary quantity | Vector normalization | When to consider |
| --- | --- | --- | --- |
| `cosine` | Angle between two vectors | Not required on client; Elasticsearch normalizes stored vectors | Semantic embeddings where magnitude does not matter. |
| `dot_product` | Inner product | For float, both query and document must be unit length | Models designed for normalized vectors and inner product. |
| `max_inner_product` | Inner product, includes magnitude | Unit length not required | Models trained for MIP where magnitude is meaningful. |
| `l2_norm` | Euclidean distance | Not required | Models trained or evaluated using L2 distance. |

What must stay consistent is the metric used during model evaluation, field configuration, and querying. Never switch metrics merely to alter result ordering without re-benchmarking relevance.

### 2.6. Do Not Compare Scores Across Different Metrics or Models

Suppose a cosine query returns `_score = 0.82` and an L2 query returns `_score = 0.82`. Those two scores do not necessarily represent the same level of relevance.

Scores also depend on:

- Metric and score transformation.
- Embedding model and model version.
- Vector normalization.
- Dimensions and preprocessing.
- Boosts, filters, hybrid queries, and rescoring.
- Quantization configuration.

If you need a threshold such as "accept only sufficiently close results", calibrate the threshold on a validation set for the specific metric/model. Elasticsearch offers a `similarity` parameter on kNN queries to set a raw similarity threshold; this parameter is not the document `_score`.

## 3. Preparing Vectors Before Indexing

Vector search quality begins in the embedding pipeline. Well-tuned HNSW settings cannot fix unsuitable embeddings.

### 3.1. Use the Same Model for Documents and Queries

Document vectors and query vectors must come from the same embedding model or models designed to be compatible within the same vector space.

Retain metadata about:

- Model ID and model version.
- Dimensions.
- Text normalization/preprocessing.
- Chunking strategy if documents are split.
- Metric and normalization.
- Timestamp or pipeline version that generated the vector.

When switching embedding models, even if dimensions remain 384, old and new vectors may be incompatible. You typically need to create a new field/index, regenerate vectors for existing data, and swap aliases after validation.

### 3.2. Dimensions Must Match

If a field declares `dims: 384`, every document vector and query vector must contain exactly 384 elements.

Common errors:

- Model returns 768-dimensional vectors while the mapping declares 384.
- New model changes dimensions while the index still uses the old schema.
- Some documents get truncated or concatenated improperly.
- Query vector loses trailing elements during serialization.
- Using vectors from another model despite matching dimensions.

Validate dimensions before sending requests and emit metrics for invalid vectors. Do not wait for dimension errors to surface after a bulk request has sent thousands of items.

### 3.3. Reject Empty Vectors or Non-Finite Values

Check:

- Vector is non-null.
- Exact dimension count.
- Contains no `NaN` or positive/negative infinity.
- For cosine, vector magnitude is not zero.
- For float dot product, vector is normalized to unit length.

Java validation example:

~~~java
static void validateEmbedding(float[] vector, int expectedDims) {
    if (vector == null || vector.length != expectedDims) {
        throw new IllegalArgumentException("Invalid embedding dimensions");
    }

    double normSquared = 0.0;

    for (float value : vector) {
        if (!Float.isFinite(value)) {
            throw new IllegalArgumentException("Embedding contains non-finite value");
        }
        normSquared += value * value;
    }

    if (normSquared == 0.0) {
        throw new IllegalArgumentException("Zero vector is invalid for cosine");
    }
}
~~~

If a model requires unit vectors, check that norm is near 1 within a tolerance. Do not manually normalize if the model pipeline dictates against it or if the metric is MIP and magnitude carries meaning.

### 3.4. Chunking Affects Nearest-Neighbor Quality

If a long document is split into multiple passages, each passage gets its own embedding. Queries return the closest passages, though the application may need to display the parent document.

Store metadata such as:

- `documentId`
- `chunkId`
- `chunkIndex`
- `title`
- `tenantId`
- `embeddingModelVersion`

Indexing a single vector for an entire long document can dilute smaller subtopics. Splitting too finely loses context and yields meaningless fragments. Chunk size and overlap should be evaluated alongside the embedding model.

## 4. `dense_vector` Mapping in Elasticsearch

Elasticsearch uses the `dense_vector` field type to store numeric vectors.

Example mapping:

~~~http
PUT products
Content-Type: application/json

{
  "mappings": {
    "properties": {
      "productId": {
        "type": "keyword"
      },
      "name": {
        "type": "text"
      },
      "tenantId": {
        "type": "keyword"
      },
      "embedding": {
        "type": "dense_vector",
        "dims": 384,
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
~~~

Key properties:

- `dims`: vector dimension count.
- `index`: enables index structures supporting approximate kNN.
- `similarity`: metric used to compare vectors.
- `index_options`: selects the vector index type and construction parameters.
- `m`, `ef_construction`: HNSW construction parameters when using an index type that supports them.

Values `m: 16` and `ef_construction: 100` are common starting baselines for benchmarking, not optimal settings for every dataset. Elasticsearch mappings may choose a default index type based on version, dimensions, and element type; if strict control is required, declare them explicitly and verify the resulting mapping.

### 4.1. Declaring Vector Fields in Spring Data Elasticsearch

Spring Data Elasticsearch provides `FieldType.Dense_Vector`, `dims`, and `knnSimilarity`.

Example entity:

~~~java
import java.util.List;
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;
import org.springframework.data.elasticsearch.annotations.KnnSimilarity;

@Document(indexName = "products")
public class ProductDocument {

    @Id
    private String id;

    @Field(type = FieldType.Keyword)
    private String tenantId;

    @Field(type = FieldType.Text)
    private String description;

    @Field(
        type = FieldType.Dense_Vector,
        dims = 384,
        knnSimilarity = KnnSimilarity.COSINE
    )
    private List<Float> embedding;

    // Constructor, getters and setters
}
~~~

`knnSimilarity` provides options `COSINE`, `DOT_PRODUCT`, `L2_NORM`, `MAX_INNER_PRODUCT`, and `DEFAULT`. Enum constants follow Java uppercase conventions.

To customize HNSW settings, current Spring Data releases also offer `knnIndexOptions` and `KnnIndexOptions`; exact syntax depends on options supported by your Spring Data and Elasticsearch versions. You can manage mappings via JSON/index templates to keep schemas explicit and decoupled from entities.

Do not just look at annotations and assume the index was created properly. If an index already exists, Spring Data cannot arbitrarily alter field dimensions or similarity. Inspect `GET /products/_mapping`.

### 4.2. Indexing Documents with Embeddings

Example payload:

~~~http
PUT /products/_doc/P-100
Content-Type: application/json

{
  "productId": "P-100",
  "tenantId": "tenant-001",
  "name": "Wireless keyboard",
  "embedding": [0.12, -0.08, 0.31, 0.07]
}
~~~

The vector in the example has four elements for illustration. With mapping `dims: 384`, the actual vector must contain 384 elements.

Vectors can be written in batches via the Bulk API. Building vector graphs increases indexing and memory costs compared to storing only `keyword`/`text` fields. Benchmark both ingest throughput and search latency.

### 4.3. Dense Vectors Are Not Fields for Sorting or Aggregating

`dense_vector` is designed for vector search and scoring. Do not treat it like a regular numeric field for sorting or terms aggregations. If you need statistics by category, price, tenant, or status, store separate scalar fields with appropriate mappings.

## 5. Exact kNN: Brute-Force Exact Search

Exact kNN computes similarity for every document carrying a vector within the eligible document set. It does not skip vectors based on exploration cutoffs.

Advantages:

- Exact results under the chosen metric over the filtered document set.
- Serves as ground truth for measuring ANN recall.
- Useful when candidate sets are small.
- Works when exact scoring or complex queries/filters are needed.

Disadvantages:

- Cost scales with the number of scored vectors and dimensions.
- Can be very slow on large indexes.
- Does not leverage HNSW to skip most vectors.

### 5.1. Exact Search with `script_score`

REST request example using cosine:

~~~http
POST /products/_search
Content-Type: application/json

{
  "size": 10,
  "query": {
    "script_score": {
      "query": {
        "bool": {
          "filter": [
            {
              "term": {
                "tenantId": "tenant-001"
              }
            }
          ]
        }
      },
      "script": {
        "source": "cosineSimilarity(params.query_vector, 'embedding') + 1.0",
        "params": {
          "query_vector": [0.12, -0.08, 0.31, 0.07]
        }
      }
    }
  }
}
~~~

The script runs on every document matching the query inside `script_score`. Place narrow filters inside the inner query to shrink the scored document set.

`cosineSimilarity(...) + 1.0` shifts the score to avoid negative values. This is an example for cosine; for other metrics, use the appropriate function and transformation.

Do not run `script_score` across millions of documents just to find top 10 if approximate kNN already meets your recall targets.

### 5.2. Exact Search on Small Datasets

Suppose a tenant owns 2,000 documents, and filtering by `tenantId` leaves 300 documents. Exact scoring across 300 vectors can be reasonable, especially when high accuracy is required and latency stays within SLA.

Conversely, if the filter still leaves 2 million documents, exact scoring can consume heavy CPU and raise latency. In that case, benchmark ANN or partition indexes to narrow candidate sets.

### 5.3. Exact Does Not Mean Perfect Relevance

Exact kNN only guarantees finding the exact top `k` under the metric over indexed vectors. It does not guarantee those results satisfy user intent.

If the embedding model poorly captures semantics, data is noisy, or chunking is weak, exact search still returns the nearest documents inside an unsuitable space.

Distinguish:

- **Search recall:** Does ANN retrieve the same nearest neighbors that exact search finds?
- **Human relevance:** Do users actually find those documents useful?

Both metrics must be measured separately.

## 6. Approximate kNN and HNSW

Approximate kNN (ANN) reduces the number of vectors examined by building a search structure prior to querying.

Elasticsearch uses HNSW (Hierarchical Navigable Small World) for many dense vector index types. HNSW constructs a multi-layer graph in which each vector connects to nearby neighbor vectors. At search time, the algorithm starts from an entry point in the graph and follows edges to move closer to the query vector.

~~~text
                Entry point
                    |
                    v
             Upper graph layers
                /       \
               v         v
           Layer 1     Layer 1
             /  \        |
            v    v       v
          Layer 0: graph of vector neighbors
          o---o---o---o---o---o---o
             \   \     /     /
              o---o---o-----o
~~~

The diagram only illustrates the concept. Real graphs have multi-layered structures and more complex connections.

HNSW avoids scoring every vector. It explores a set of candidates likely near the query and ranks those candidates.

### 6.1. Why Is HNSW Faster?

With brute force, the system computes similarity for every vector in the candidate set. With HNSW, the algorithm traverses the graph and focuses on regions likely to contain nearest neighbors.

In exchange, graph search may bypass a vector that truly belongs in the top `k`. That is why ANN is fast yet does not always return identical results to exact search.

### 6.2. Graph Construction Parameter: `m`

`m` is the number of neighbor connections each node maintains in the graph under the HNSW implementation.

Typical effects:

- Larger `m`: denser graph, potentially improving navigability and recall.
- Larger `m`: increases memory usage and graph build/merge costs.
- Smaller `m`: lighter graph, though finding good neighborhoods may be harder.

Do not increase `m` expecting faster queries. It is an index-build parameter affecting storage, indexing, and recall.

### 6.3. Graph Construction Parameter: `ef_construction`

`ef_construction` controls the number of candidates evaluated when building the neighbor list for a newly inserted node.

Typically:

- Higher values can produce higher-quality graphs.
- Indexing slows down because more candidates are explored.
- Can improve recall at search time.
- Increases CPU usage and ingest duration.

`ef_construction` is an index-time parameter. It differs from `num_candidates`, which controls search-time candidate exploration in a kNN query.

### 6.4. Search Parameter: `num_candidates`

`num_candidates` is the number of nearest-neighbor candidates considered per shard/segment under Elasticsearch's search mechanism.

Rules of thumb:

- Increasing `num_candidates`: usually improves recall, while latency and CPU rise.
- Decreasing `num_candidates`: usually speeds up searches, but may miss nearest neighbors.
- Must be greater than or equal to `k`.
- For HNSW, Elasticsearch enforces an upper bound of 10,000.

`num_candidates` is typically the primary parameter for balancing speed and recall in HNSW queries.

## 7. Distinguishing `k`, `num_candidates`, and `size`

These three parameters serve different purposes:

| Parameter | Meaning |
| --- | --- |
| `k` | Number of nearest neighbors to retrieve from each shard before global merging. |
| `num_candidates` | Number of candidates explored per shard/segment during approximate search. |
| `size` | Final number of search hits returned to the client. |

Example:

~~~json
{
  "size": 10,
  "knn": {
    "field": "embedding",
    "query_vector": [0.12, -0.08, 0.31, 0.07],
    "k": 10,
    "num_candidates": 100
  }
}
~~~

How it works:

1. Elasticsearch explores candidates up to `num_candidates`.
2. Each shard retains its best `k` vector results.
3. Shard results are merged.
4. The search response returns up to `size` hits.

With multiple shards, total candidates explored across the cluster can far exceed a single shard's `num_candidates`. If an index has many segments, HNSW graphs are searched across segments individually, so segment count also impacts cost.

Do not set `num_candidates = size` out of habit. If `size = 10`, `num_candidates = 10` can be overly tight and produce low recall. Test different ratios, such as 2x, 5x, or 10x `k`, and measure on real data.

### 7.1. Candidate Budget Tuning Example

Suppose `k = 10`:

| `num_candidates` | Trend | Risk |
| ---: | --- | --- |
| 10 | Lowest valid candidate budget. | May miss nearest neighbors. |
| 30 | Explores more candidates. | Higher latency compared to 10. |
| 100 | Broader candidate set. | Higher CPU cost, but generally improves recall. |
| 500 | Very broad exploration. | Latency may rise with diminishing recall gains. |

These numbers are examples for designing benchmarks, not defaults or recommendations for every system. Dataset, dimensions, shard count, filter selectivity, and HNSW graph all affect outcomes.

## 8. kNN Queries in Elasticsearch

Top-level kNN search example:

~~~http
POST /products/_search
Content-Type: application/json

{
  "size": 10,
  "knn": {
    "field": "embedding",
    "query_vector": [0.12, -0.08, 0.31, 0.07],
    "k": 10,
    "num_candidates": 100,
    "filter": {
      "term": {
        "tenantId": "tenant-001"
      }
    }
  }
}
~~~

The `embedding` field must be a `dense_vector` with indexing enabled, and the query vector must have matching dimensions.

`filter` inside `knn` is a pre-filter. Elasticsearch applies this condition during approximate search to gather enough eligible candidates.

### 8.1. Pre-Filter and Post-Filter

This distinction is critical when filtering by tenant, category, or status.

**Pre-filter** is placed inside `knn.filter`:

~~~json
{
  "knn": {
    "field": "embedding",
    "query_vector": [0.12, -0.08, 0.31, 0.07],
    "k": 10,
    "num_candidates": 100,
    "filter": {
      "term": {
        "tenantId": "tenant-001"
      }
    }
  }
}
~~~

Pre-filtering runs during nearest-neighbor search so kNN can retrieve up to `k` matching documents if enough eligible documents exist.

**Post-filter** is placed in a query scope outside kNN, for example:

~~~json
{
  "query": {
    "bool": {
      "must": [
        {
          "knn": {
            "field": "embedding",
            "query_vector": [0.12, -0.08, 0.31, 0.07],
            "k": 10,
            "num_candidates": 100
          }
        }
      ],
      "filter": [
        {
          "term": {
            "tenantId": "tenant-001"
          }
        }
      ]
    }
  }
}
~~~

Post-filtering runs after approximate search has already selected candidates. If many candidates belong to other tenants, the final result may contain fewer than 10 hits even though that tenant has plenty of eligible documents in the index.

When you need the top `k` within a business scope such as tenant, category, or access control, place the filter properly inside `knn.filter`. Do not rely on post-filtering as a substitute for pre-filtering.

### 8.2. Filter Selectivity and Actual Behavior

Pre-filter semantics do not mean Elasticsearch executes identically in every scenario. When a filter matches a large percentage of documents on a shard, Elasticsearch may gather unfiltered approximate candidates first and filter afterward. If very few documents match, Elasticsearch may switch to filtering during search to preserve result semantics.

Therefore, benchmark queries across different filter selectivity levels. A tenant holding 80% of the index and a tenant holding 0.1% can exhibit very different latency profiles.

## 9. Filtering, Shards, and Result Counts

A kNN query across a multi-shard index must merge shard-level results into a global top `k`.

Example index with 4 shards:

~~~text
Query vector
     |
     +------> Shard 0: local candidates
     |
     +------> Shard 1: local candidates
     |
     +------> Shard 2: local candidates
     |
     +------> Shard 3: local candidates
                    |
                    v
             Coordinator merge
                    |
                    v
             Global top k hits
~~~

One shard may contain closer documents to the query than another shard. Elasticsearch retrieves enough candidates from each shard so the merged results have a good chance of capturing the true global top `k`.

Several effects:

- More shards increase fan-out and merge costs.
- More segments increase the number of graphs traversed.
- Imbalanced shards cause uneven latency.
- Highly selective filters reduce eligible documents and alter search execution.
- Returned document count need not equal `k` if `size`, filters, or available matching data are smaller.

Do not add shards merely to parallelize vector search. Every shard adds overhead and must be benchmarked at an appropriate shard size.

## 10. Exact vs. Approximate: Choosing by Scale and SLA

| Criterion | Exact kNN | Approximate kNN (HNSW) |
| --- | --- | --- |
| Approach | Scores every eligible vector. | Traverses a graph to find candidates near the query. |
| Nearest-neighbor accuracy | Exact under the metric over the filtered set. | May miss some true neighbors. |
| Latency on large sets | Scales with number of scored vectors. | Typically lower if graph is well-configured. |
| CPU | High for large candidate sets. | Depends on graph traversal and candidate budget. |
| Indexing | No HNSW graph build if using flat/exact path. | Incurs extra graph-building cost. |
| Memory/storage | Stores vectors and scoring structures. | Adds graph and optional quantization structures. |
| Small datasets | Usually suitable. | May be unnecessary. |
| Large datasets | May fail SLA. | Usually suitable for production retrieval. |
| Ground truth benchmark | Serves as baseline for measuring recall. | Compared against exact top `k`. |

There is no fixed document count threshold for switching from exact to ANN. 50,000 384-dimensional vectors on strong hardware behave very differently from 50,000 3,072-dimensional vectors on small nodes. Filters can also shrink candidate sets small enough for exact search to remain viable.

## 11. Quantization: Reducing Memory at an Accuracy Trade-Off

`float32` vectors require roughly 4 bytes per dimension before overhead. A 768-dimensional vector therefore needs about 3 KB for raw float values. With tens or hundreds of millions of vectors, storage and memory costs become substantial.

Quantization reduces the number of bits used to represent vectors:

- `int8_hnsw`: 8-bit scalar quantization.
- `int4_hnsw`: 4-bit scalar quantization.
- `bbq_hnsw`: binary quantization.
- `bbq_disk`: disk-based vector search type, depending on version and license.

These compression formats reduce memory and storage, but discard some vector precision. Loss depends on data distribution, model, and queries.

### 11.1. Choosing Quantization

| Type | Idea | General trade-off |
| --- | --- | --- |
| `float32` + HNSW | Keeps full float vectors. | High fidelity, high memory cost. |
| `int8` | 8-bit quantization. | Memory savings, minor potential recall drop. |
| `int4` | 4-bit quantization. | Stronger compression, typically greater fidelity loss. |
| `BBQ` | Binary quantization representation. | Major memory savings, requires verifying recall and rescoring. |

Default index types change across Elasticsearch versions and dimensions. Do not rely on defaults observed on another cluster. Check `index_options` mappings and documentation for your exact target version.

### 11.2. Oversampling and Rescoring

With quantized vectors, you can retrieve more candidates than `k`, then recompute similarity using original vectors to refine ordering.

Example:

~~~json
{
  "knn": {
    "field": "embedding",
    "query_vector": [0.12, -0.08, 0.31, 0.07],
    "k": 10,
    "num_candidates": 100,
    "rescore_vector": {
      "oversample": 2.0
    }
  }
}
~~~

If `k = 10` and `oversample = 2`, Elasticsearch can rescore around 20 top candidates per shard using the original vectors before merging final results.

Oversampling helps when quantization perturbs the relative order of close neighbors. In return, rescoring reads original vectors and increases CPU/latency. Pick `oversample` via benchmarks; no universal factor works for all models.

`rescore_vector` applies to quantized dense vector fields. On unquantized vectors, rescoring in this manner offers no comparable benefit because search already uses the original vectors.

## 12. Tuning HNSW: Index-Time and Search-Time

Two groups of parameters should be kept distinct.

| Stage | Parameter | Impact |
| --- | --- | --- |
| Graph/index creation | `m` | Graph connectivity, memory, and graph quality. |
| Graph/index creation | `ef_construction` | Candidates evaluated during graph construction, graph quality, and indexing time. |
| Querying | `k` | Number of nearest neighbors to retrieve. |
| Querying | `num_candidates` | Candidate budget, recall, and latency. |
| Querying quantized vectors | `rescore_vector.oversample` | Number of candidates rescored with original vectors. |

If recall is low, you may need to raise `num_candidates`, improve the graph via `m`/`ef_construction`, or revisit the embedding model. If latency is high, reducing the candidate budget can help, though recall must be re-measured afterward.

Changing `m` or `ef_construction` generally requires rebuilding graphs for existing data via reindex/merge depending on Elasticsearch version capabilities. Do not confuse them with query parameters that can be adjusted per request.

## 13. kNN in Spring Data Elasticsearch

Spring Data Elasticsearch uses the Elasticsearch Java API Client underneath. In modern releases, `NativeQueryBuilder.withKnnSearches(...)` builds the top-level `knn` option in the Search API.

### 13.1. Entity with a Dense Vector

~~~java
import java.util.List;
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;
import org.springframework.data.elasticsearch.annotations.KnnSimilarity;

@Document(indexName = "products")
public class ProductDocument {

    @Id
    private String id;

    @Field(type = FieldType.Keyword)
    private String tenantId;

    @Field(type = FieldType.Text)
    private String description;

    @Field(
        type = FieldType.Dense_Vector,
        dims = 384,
        knnSimilarity = KnnSimilarity.COSINE
    )
    private List<Float> embedding;

    // Constructors, getters and setters
}
~~~

Ensure the Java type is supported for dense vectors by your project's Spring Data converter. `List<Float>` represents the vector as a numeric list; the query vector passed to the Java API Client must also contain 384 values.

### 13.2. Building a kNN `NativeQuery`

Example using top-level kNN search:

~~~java
import co.elastic.clients.elasticsearch._types.FieldValue;
import co.elastic.clients.elasticsearch._types.KnnSearch;
import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.SearchHit;
import org.springframework.data.elasticsearch.core.SearchHits;

public class ProductVectorSearchService {

    private final ElasticsearchOperations operations;

    public ProductVectorSearchService(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public List<ProductDocument> findSimilar(
            List<Float> queryVector,
            String tenantId) {

        KnnSearch knnSearch = KnnSearch.of(knn -> knn
                .field("embedding")
                .queryVector(queryVector)
                .k(10)
                .numCandidates(100)
                .filter(filter -> filter.term(term -> term
                        .field("tenantId")
                        .value(FieldValue.of(tenantId))
                ))
        );

        NativeQuery query = NativeQuery.builder()
                .withKnnSearches(knnSearch)
                .build();

        SearchHits<ProductDocument> hits =
                operations.search(query, ProductDocument.class);

        return hits.getSearchHits().stream()
                .map(SearchHit::getContent)
                .toList();
    }
}
~~~

This example demonstrates the current Spring Data Elasticsearch API:

- `KnnSearch` comes from the Elasticsearch Java API Client.
- `NativeQuery` resides in `org.springframework.data.elasticsearch.client.elc`.
- `withKnnSearches(...)` configures top-level kNN.
- `ElasticsearchOperations.search(...)` returns `SearchHits<T>`.
- The filter is placed inside `KnnSearch` to act as a pre-filter.

Older Spring Data versions have different APIs. Starting in Spring Data Elasticsearch 5.4, `withKnnQuery` was replaced by `withKnnSearches` for top-level kNN search. `KnnQuery` is a query nested inside Query DSL; `KnnSearch` is a top-level `knn` option. Do not confuse these two classes.

### 13.3. `SearchHit` and Score

You can inspect metadata for each hit:

~~~java
for (SearchHit<ProductDocument> hit : hits) {
    ProductDocument product = hit.getContent();

    String id = hit.getId();
    float score = hit.getScore();

    // Use score for sorting/displaying according to the application contract.
}
~~~

`_score` is calculated by Elasticsearch. If a query combines vector scores with text scores or boosts, the final score may already be merged. Do not use one fixed threshold across all query types without calibration.

### 13.4. `ReactiveElasticsearchOperations`

In reactive applications, you can use `ReactiveElasticsearchOperations` with the same `NativeQuery`:

~~~java
public Flux<ProductDocument> findSimilarReactive(
        List<Float> queryVector,
        String tenantId) {

    KnnSearch knnSearch = KnnSearch.of(knn -> knn
            .field("embedding")
            .queryVector(queryVector)
            .k(10)
            .numCandidates(100)
            .filter(filter -> filter.term(term -> term
                    .field("tenantId")
                    .value(FieldValue.of(tenantId))
            ))
    );

    NativeQuery query = NativeQuery.builder()
            .withKnnSearches(knnSearch)
            .build();

    return reactiveOperations.search(query, ProductDocument.class)
            .map(SearchHit::getContent);
}
~~~

Reactive pipelines must be subscribed to by the framework or caller. Never call `block()` or `subscribe()` inside a service just to wait for results. Limit concurrency if many vector queries execute in parallel.

### 13.5. Exact Queries in Spring Data

If exact scoring is needed, build a `NativeQuery` from an Elasticsearch Java API Client `Query` containing `script_score`, then call `ElasticsearchOperations.search(...)`. Alternatively, call the REST/API client directly when a request option is not yet supported by the abstraction.

Exact queries must restrict the document set before the script runs. Never invoke `script_score` across a large index if low-latency semantic retrieval is the goal.

## 14. Combining Vector Search with Business Filters

Vector similarity does not replace business filters. Applications commonly need to combine:

- Tenant isolation.
- Active status.
- Language.
- Category.
- Access permissions.
- Publication time.
- Document type.

Example vector query with tenant and status:

~~~json
{
  "knn": {
    "field": "embedding",
    "query_vector": [0.12, -0.08, 0.31, 0.07],
    "k": 10,
    "num_candidates": 100,
    "filter": {
      "bool": {
        "filter": [
          { "term": { "tenantId": "tenant-001" } },
          { "term": { "status": "ACTIVE" } },
          { "term": { "language": "vi" } }
        ]
      }
    }
  }
}
~~~

Filters must be constructed from server-side authenticated context. Never allow clients to supply arbitrary tenant filters and treat them as a security boundary.

### 14.1. Overly Selective Filters

If a filter leaves only a handful of documents, the HNSW graph may not be the most efficient search path. Elasticsearch can fall back to brute-force search in certain cases when the filtered set is small or candidate search is inefficient.

This is not a bug. Benchmark across actual filter selectivity. You can design index partitions or routing if tenant/filter workloads are heavily skewed, though routing never replaces security filters.

## 15. Hybrid Search: Combining Lexical and Vector

Vector search excels at semantics, whereas lexical search remains important for:

- Product codes.
- Proper names.
- Error codes.
- Rare keywords.
- Exact strings.
- Terms requiring verbatim matches.

Hybrid search combines text query results and vector query results. One approach runs two retrievers and merges results using Reciprocal Rank Fusion (RRF), or combines scores per an appropriate configuration.

Illustrative request combining a text query and top-level kNN:

~~~http
POST /products/_search
Content-Type: application/json

{
  "size": 10,
  "query": {
    "match": {
      "description": "wireless keyboard for office"
    }
  },
  "knn": {
    "field": "embedding",
    "query_vector": [0.12, -0.08, 0.31, 0.07],
    "k": 50,
    "num_candidates": 200
  }
}
~~~

When combining top-level `query` and `knn`, Elasticsearch can merge matching documents according to Search API semantics. Because text and vector scores sit on different scales, directly adding scores can allow one branch to overpower the other.

RRF relies on ranks rather than adding raw scores directly, making it a strong starting point when two retrievers have differing score distributions. Regardless of method, measure relevance on a labeled query set.

## 16. Measuring Accuracy: `recall@k`

When tuning ANN, you need an exact baseline to know how many true nearest neighbors ANN misses.

**Recall@k** of ANN relative to exact top `k`:

\[
\operatorname{Recall@k}
=
\frac{|\operatorname{ANNTopK} \cap \operatorname{ExactTopK}|}{k}
\]

Example exact top 5:

~~~text
Exact:      A, B, C, D, E
ANN result: A, B, D, F, E
~~~

There are 4 overlapping documents out of 5:

\[
\operatorname{Recall@5} = \frac{4}{5} = 0.8
\]

`Recall@k = 0.8` means ANN recovered 80% of the exact top-k documents in this example. It does not mean 80% of the results are useful to users.

### 16.1. Exact Ground Truth Must Use Identical Conditions

For a fair comparison, exact and ANN must share:

- The same query vector.
- The same embedding model/version.
- The same metric.
- The same eligible document set.
- The same filters and tenant scope.
- The same `k`.
- The same data and benchmark snapshot.

If the exact query omits the tenant filter while ANN includes it, recall calculations no longer compare the same search set.

### 16.2. Recall and Relevance Are Two Separate Problems

Recall@k measures proximity to exact vector rankings. Metrics such as nDCG@k, MRR, or precision@k based on relevance labels measure business utility.

An ANN index achieving 99% recall can still return poor results if the embedding model fails to capture the domain. Conversely, an ANN index at 95% recall may deliver strong relevance if the missed neighbors do not matter to users.

Measure both for user-facing search systems.

## 17. Benchmarking Speed and Accuracy

Do not choose `num_candidates` by guesswork. Create a benchmark with representative queries and measure multiple candidate budgets.

Example test matrix:

| Trial | `k` | `num_candidates` | Objective |
| --- | ---: | ---: | --- |
| A | 10 | 10 | Low candidate baseline. |
| B | 10 | 30 | Check recall gain at a moderate budget. |
| C | 10 | 100 | Broader candidate budget. |
| D | 10 | 300 | Check whether recall continues improving. |
| E | 10 | 500 | Identify diminishing returns. |

Measure at minimum:

- Recall@k against exact baseline.
- p50, p95, and p99 latency.
- Query throughput (QPS).
- CPU utilization.
- Heap and memory pressure.
- Vector memory / filesystem cache.
- Disk I/O.
- Indexing throughput.
- Refresh/merge time during concurrent ingestion.
- Index and HNSW graph size.

Raising `num_candidates` can improve recall while raising p95/p99 latency. The optimal point is where both target recall and SLA are met, not maximum possible recall at all costs.

### 17.1. Use Realistic Queries

Benchmark query sets should include:

- Short and long queries.
- Vietnamese queries with and without diacritics if both are supported.
- Multilingual queries.
- Rare queries and frequent queries.
- Broad-filter and narrow-filter queries.
- Queries with no good matches.
- Queries on small tenants and large tenants.
- Queries with many near-tie documents.

Do not benchmark solely with random vectors. Random vectors fail to reflect real embedding distributions and query difficulty.

### 17.2. Test Across Multiple Index States

HNSW search can be affected by segment count. Newly ingested indexes may contain many segments, whereas after merges graphs may be rebuilt. Benchmarks must reflect production index states, not only a freshly built quiet index.

If data is ingested continuously, measure during merges and refreshes too. Benchmarking only on an idle index can misrepresent production latency.

## 18. Tuning for Business Goals

### 18.1. Prioritizing Low Latency

When SLAs demand fast responses:

- Start with a `k` sufficient for the UI.
- Keep `num_candidates` small while maintaining acceptable recall.
- Scope filters and document sets tightly.
- Check shard and segment counts.
- Consider quantization if memory is a bottleneck.
- Rescore only as many candidates as necessary.
- Cache query vectors or embeddings when data consistency permits.

Do not lower the candidate budget blindly without checking recall. Fast responses missing good documents degrade user experience.

### 18.2. Prioritizing Accuracy

When high recall is required:

- Increase `num_candidates` incrementally.
- Increase `m` or `ef_construction` on new graph builds if benchmarks justify it.
- Consider exact search on small filtered candidate sets.
- Use oversampling and rescoring for quantized vectors.
- Review the embedding model and chunking strategy.
- Regularly compare ANN against exact ground truth.

Do not assume raising `num_candidates` fixes everything. If the graph quality is weak or embeddings are poorly suited, improve the index or model.

### 18.3. Prioritizing Memory and Storage

When vector datasets grow very large:

- Evaluate int8/int4/binary quantization supported by your version.
- Use `bbq_disk` when license and architecture fit.
- Measure quantization's impact on recall.
- Consider on-disk rescoring when original vectors do not fit in RAM.
- Control replica and shard counts.
- Provision nodes with enough memory and filesystem cache for the workload.

Vector compression saves memory, but is not free. Queries may need rescoring to recover recall, adding disk I/O or latency.

### 18.4. Prioritizing Ingest Throughput

Indexing vectors costs more than indexing scalar fields because vector index structures must be built.

Consider:

- Bulk indexing with controlled batch size and concurrency.
- Refresh intervals suited to the ingestion window.
- Keeping HNSW `m`/`ef_construction` no higher than necessary.
- Creating a new index followed by an alias swap for initial loads.
- Monitoring merges, disk, and vector memory.

Do not sacrifice recall or overload indexing without measuring. Balance ingestion speed against graph quality and query performance.

## 19. Common Pitfalls When Deploying kNN

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| kNN query fails with dimension mismatch | Query vector differs from field `dims` | Check model version and dimensions |
| No results returned | Missing vector values, unmatched filter, or wrong index | Check mapping, `_source`, filters, and index |
| Poor semantic results | Queries/documents use different models or preprocessing | Standardize embedding pipeline and evaluate model |
| Negative or unexpected scores | Confusing raw similarity with `_score` or wrong metric | Check metric and score formula |
| Dot product gives anomalous results | Float vectors not unit-length normalized | Normalize both document and query vectors per model contract |
| Cosine fails with zero vector error | Vector has zero magnitude | Reject empty vectors and check embedding pipeline |
| Fewer than `k` results returned | Post-filter drops candidates or too few eligible documents | Move conditions into `knn.filter` and check selectivity |
| High latency | Large `num_candidates`, too many shards/segments, or memory pressure | Measure candidate budget, shards, and cache |
| Low recall | Low candidate budget, weak graph, quantization, or model | Raise `num_candidates`, benchmark graph and rescoring |
| Slow ingestion | Vector graph construction consumes CPU/memory and oversized bulks | Tune batch/concurrency and HNSW build parameters |
| Results shift after model update | Embedding space changed | Re-embed data and migrate to a new index version |
| Search alias behaves inconsistently | Underlying indexes have differing mappings/dimensions/models | Inspect mapping and version of each index |
| Skewed hybrid scores | Text and vector scores on different scales | Use RRF or tune boosts against a relevance set |

## 20. Inspecting Mappings and Data During Diagnostics

### 20.1. Inspecting the Mapping

~~~http
GET /products/_mapping
~~~

Verify:

- Field type is `dense_vector`.
- `dims` matches the model.
- `similarity` matches the metric.
- `index` is enabled if using approximate kNN.
- `index_options` specifies the intended graph/quantization type.
- No index behind the alias has a conflicting dimension mapping.

### 20.2. Inspecting a Document

~~~http
GET /products/_doc/P-100
~~~

Verify whether the vector was written to the document and has the right dimension count. If your version's `_source` or vector storage configuration omits raw vectors as expected, check the corresponding field/docvalue API and storage mapping.

### 20.3. Checking Field Capabilities

When searching across multiple indexes:

~~~http
GET /products-*/_field_caps?fields=embedding
~~~

Field capabilities detect mapping type conflicts. However, dense vector dimensions and similarity still need to be checked in each index's mapping.

### 20.4. Profiling Queries

You can enable `profile: true` in the Search API to inspect query execution cost:

~~~http
POST /products/_search
Content-Type: application/json

{
  "profile": true,
  "size": 10,
  "knn": {
    "field": "embedding",
    "query_vector": [0.12, -0.08, 0.31, 0.07],
    "k": 10,
    "num_candidates": 100
  }
}
~~~

Profiling helps investigate queries, but adds overhead. Do not enable it on all production requests and do not treat profiled latencies as normal benchmark measurements.

## 21. Implementation and Tuning Workflow

A practical workflow:

1. Select an embedding model and lock down its version.
2. Determine dimensions, normalization, and metric per the model.
3. Create an index mapping with explicit `dense_vector`, `dims`, and `similarity`.
4. Index a representative dataset.
5. Build an exact baseline via brute-force scoring over the eligible document set.
6. Run approximate kNN with initial `k` and `num_candidates`.
7. Compare ANN against exact using recall@k.
8. Adjust candidate budget up/down to find the latency-recall balance.
9. If recall stays low, inspect graph parameters, quantization, and embedding quality.
10. Verify pre-filter/post-filter behavior and shard count.
11. Benchmark with realistic queries, realistic filters, and concurrent ingest/search workloads.
12. Set SLAs for recall, p95/p99 latency, and QPS.
13. Monitor drift when models, mappings, index types, or data change.
14. Reindex and swap aliases whenever dimensions or model space change.

Save configurations and benchmark results per version. Whenever changing `num_candidates`, `m`, `ef_construction`, quantization, or the embedding model, capture before/after metrics to see which indicators improved.

## 22. References

- [Spring Data Elasticsearch — Field annotation](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/annotations/Field.html)
- [Spring Data Elasticsearch — FieldType](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/annotations/FieldType.html)
- [Spring Data Elasticsearch — KnnSimilarity](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/annotations/KnnSimilarity.html)
- [Spring Data Elasticsearch — NativeQueryBuilder](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/client/elc/NativeQueryBuilder.html)
- [Spring Data Elasticsearch — Migration guide 5.3 to 5.4](https://docs.spring.io/spring-data/elasticsearch/reference/migration-guides/migration-guide-5.3-5.4.html)
- [Elasticsearch — Dense vector field type](https://www.elastic.co/docs/reference/elasticsearch/mapping-reference/dense-vector)
- [Elasticsearch — kNN query](https://www.elastic.co/docs/reference/query-languages/query-dsl/query-dsl-knn-query)
- [Elasticsearch — Dense vector query](https://www.elastic.co/docs/reference/query-languages/query-dsl/query-dsl-dense-vector-query)
- [Elasticsearch — Optimize approximate kNN performance and accuracy](https://www.elastic.co/docs/solutions/search/vector/knn/optimize-performance-accuracy)
- [Elasticsearch — kNN search](https://www.elastic.co/docs/solutions/search/vector/knn)

The metric defines what "close" means; exact kNN establishes an accurate baseline under that metric, while HNSW reduces cost by exploring only a subset of vectors. In Elasticsearch, `k` is the number of neighbors to retrieve, `num_candidates` controls the candidate budget, and filters inside `knn` act as pre-filters. Measure recall@k against exact search alongside p95/p99 latency on real queries and filters, then tune graph settings, candidate budgets, and quantization to meet your SLA. Spring Data Elasticsearch integrates these capabilities through dense vector mappings and `NativeQuery.withKnnSearches(...)`.
