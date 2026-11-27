# Combining Keyword and Vector Search Based on Elasticsearch Capabilities

Keyword search and vector search address two different kinds of queries. Keyword search fits when users need names, codes, phrases, or terms appearing in documents. Vector search fits when users express intent in natural language and want semantically similar content even without overlapping wording. A product or document search system commonly needs both.

**Hybrid search** combines lexical and vector results into a single experience. Elasticsearch can execute these search branches and fuse rankings using capabilities such as `retriever` and Reciprocal Rank Fusion (RRF) on supported versions. On versions without suitable built-in fusion APIs, the application can execute two separate branches and merge results in a service.

This lesson explains how BM25 and vector retrieval work, how to prepare embeddings and mappings, how to combine both branches, how to use Spring Data Elasticsearch as an access layer, as well as decisions around filtering, performance, relevance evaluation, and testing.

## 1. Why Combine Keywords and Vectors?

Suppose a user searches for:

> lightweight laptop for studying, long battery life

Keyword search may prioritize documents containing the words "laptop", "lightweight", "battery", or variants processed by the analyzer. Yet a product described as "ultrabook 14 inch, 12-hour battery life, 1.1 kg weight" may be an ideal match even without containing the exact phrasing entered by the user.

Vector search converts queries and content into embeddings — numeric vectors representing meaning. Two phrases close in meaning generally yield close vectors under the model's metric, even when different words are used.

Each approach has distinct strengths:

| Capability | Keyword / lexical search | Vector search |
|---|---|---|
| Product codes, SKUs, proper names | Very well-suited | Can be unstable |
| Exact phrases | Suitable with `term`/phrase queries | Does not guarantee exact match |
| Intent phrased in different words | Depends on analyzers and synonyms | Typically handles well |
| Rare terms or technical codes | Usually strong | Embeddings can blur distinctions |
| Semantics and similar meaning | More limited | Core strength |
| Result explainability | Can inspect term/query scores | Harder to interpret vector scores directly |
| Processing cost | Typically lower | Requires embeddings and vector retrieval |

Hybrid search leverages lexical matches for codes, names, and critical keywords while using vectors to locate semantically related content.

Do not assume vector search is always superior to keyword search. For a query like "SKU-AX91-RED", an exact `term` or `prefix` query can be far more accurate than embeddings. For a long descriptive need, vector retrieval supplements what lexical search misses.

## 2. Hybrid Search Processing Flow

Systems typically generate embeddings at two stages:

- **Index time:** generate embeddings for content stored in Elasticsearch.
- **Query time:** generate an embedding for the user's query.

Both vectors must come from compatible models sharing the same vector space, dimensions, and preprocessing steps.

~~~text
                    INDEX TIME
Product/document
      |
      +------------------------------+
      |                              |
      v                              v
Text fields                      Embedding model
      |                              |
      v                              v
Inverted index                  Dense vector
      |                              |
      +---------------+--------------+
                      |
                      v
                Elasticsearch


                    QUERY TIME
User query
      |
      +------------------------------+
      |                              |
      v                              v
Lexical query                    Embedding model
      |                              |
      v                              v
BM25 / standard search          kNN vector search
      |                              |
      +---------------+--------------+
                      |
                      v
                Rank fusion
                      |
                      v
              ProductSearchResponse
~~~

In Spring Data Elasticsearch, repositories or `ElasticsearchOperations` send queries and map results. Invoking the embedding model can live inside an `EmbeddingService`, an inference endpoint, or be managed by Elasticsearch via semantic fields depending on version and configuration.

Do not confuse a vector field with a model. Elasticsearch stores and searches vectors; generating embeddings requires a model or corresponding inference pipeline.

## 3. Keyword Search and BM25

Elasticsearch uses an inverted index for `text` fields. Analyzers can tokenize, normalize casing, strip stop words, or apply stemming/synonyms depending on configuration.

Example mapping:

~~~json
{
  "properties": {
    "name": {
      "type": "text"
    },
    "description": {
      "type": "text"
    },
    "sku": {
      "type": "keyword"
    },
    "brand": {
      "type": "keyword"
    },
    "status": {
      "type": "keyword"
    }
  }
}
~~~

`name` and `description` fit full-text queries. `sku`, `brand`, and `status` fit exact filters or `term` queries.

Lexical query example:

~~~http
GET /products/_search
{
  "query": {
    "bool": {
      "must": [
        {
          "multi_match": {
            "query": "lightweight laptop long battery",
            "fields": [
              "name^3",
              "description",
              "categoryText"
            ]
          }
        }
      ],
      "filter": [
        {
          "term": {
            "status": "ACTIVE"
          }
        }
      ]
    }
  }
}
~~~

`name^3` boosts the `name` field. This query can use BM25 to score relevance based on term matches, term rarity, and field length.

### When Do Lexical Matches Matter More?

- SKUs, serial numbers, or order codes.
- Brand names and specific model numbers.
- Legal or technical terms that must match.
- Rare keywords carrying decisive intent.
- Exact business conditions such as `status`, `category`, or `tenant`.

You can combine `match`, `match_phrase`, `term`, `prefix`, or synonyms as required. Do not blindly dump every field into `multi_match`; choose fields and boosts based on real data.

## 4. Vector Search and Embeddings

An embedding model converts text into a fixed-dimension vector. For example, a model generating 768-dimensional vectors:

~~~text
"lightweight laptop, long battery"
          |
          v
    Embedding model
          |
          v
[0.12, -0.08, 0.44, ..., 0.03]
          |
          v
       768 values
~~~

A document's embedding can be built from:

- Product name and description.
- Document body.
- Title plus summary.
- Fields combined via an explicit template.

User queries pass through the same model to produce vectors of the same dimension.

### Dimensions Must Match

If the mapping declares 768 dimensions, both indexed vectors and query vectors must have exactly 768 elements. Dimension mismatches cause requests to be rejected.

Do not swap to another model with the same dimension count and assume vectors remain compatible. Different models produce different embedding spaces even at identical dimensions. Re-embed data or maintain compatible model versions.

### Similarity Metrics

Common metrics include:

- **`cosine`:** measures directional similarity between vectors; commonly used with text embeddings.
- **`dot_product`:** inner product; semantics depend on how the model normalizes vectors.
- **`l2_norm`:** Euclidean distance; closer vectors under this distance indicate stronger similarity per model training.

Choose the metric according to the embedding model and how vectors are produced. Do not arbitrarily change metrics after indexing data.

### Do Not Treat Vector Scores as Probabilities

Scores from cosine, dot product, or L2 are not match percentages. Values and directional interpretations depend on the metric, mapping, and Elasticsearch version. Do not display "92% match" without separate calibration.

## 5. `dense_vector` Mapping

With application-generated embeddings, one option is a `dense_vector` field.

Example mapping:

~~~http
PUT /products-v1
{
  "mappings": {
    "properties": {
      "name": {
        "type": "text"
      },
      "description": {
        "type": "text"
      },
      "sku": {
        "type": "keyword"
      },
      "status": {
        "type": "keyword"
      },
      "embedding": {
        "type": "dense_vector",
        "dims": 768,
        "index": true,
        "similarity": "cosine"
      }
    }
  }
}
~~~

`dims`, `index`, `similarity`, and vector index options must fit your Elasticsearch version. Older releases have different limits or defaults than newer ones; verify the mapping capabilities of your running cluster.

If vectors are stored without indexing for ANN search, query behavior and performance differ. For approximate kNN, configure appropriate vector indexing.

### Spring Data Entity

Illustrative entity example:

~~~java
@Document(indexName = "products-v1")
public class ProductDocument {

    @Id
    private String id;

    @Field(type = FieldType.Text)
    private String name;

    @Field(type = FieldType.Text)
    private String description;

    @Field(type = FieldType.Keyword)
    private String sku;

    @Field(type = FieldType.Keyword)
    private String status;

    // Dense vector mapping is configured for the deployed
    // Spring Data Elasticsearch / Elasticsearch version.
    private float[] embedding;
}
~~~

Dense vector annotations and conversions evolve across release trains. When strict control over `dims`, `similarity`, and index options is needed, manage mappings via index templates or provisioning resources and verify the live mapping.

Do not assume simply declaring `float[]` in an entity creates the right `dense_vector` mapping in every version.

## 6. Generating and Storing Embeddings

If the application calls the model directly, wrap the model behind an interface:

~~~java
public interface EmbeddingService {

    float[] embed(String text);
}
~~~

Implementations can call a local model, model service, or inference endpoint:

~~~java
@Service
public class ProductEmbeddingService {

    private final EmbeddingService embeddingService;

    public ProductEmbeddingService(
            EmbeddingService embeddingService) {
        this.embeddingService = embeddingService;
    }

    public ProductDocument prepare(ProductDocument product) {
        String text = product.getName()
            + "\n"
            + product.getDescription();

        product.setEmbedding(
            embeddingService.embed(text)
        );

        return product;
    }
}
~~~

This is an illustrative structure. Production systems must handle timeouts, bounded retries, model availability, and dimension errors. Avoid calling the embedding model repeatedly for unchanged content when previously computed embeddings can be reused.

### Index Flow

~~~java
public ProductDocument index(ProductDocument product) {
    ProductDocument prepared = embeddingService.prepare(product);
    return repository.save(prepared);
}
~~~

Embedding generation can also occur inside an Elasticsearch ingest pipeline if the cluster is configured with an appropriate inference processor. In that case, the application sends text and Elasticsearch/inference generates the vector. Clearly assign responsibility to avoid embedding twice or overwriting vectors with another model.

### Model Versioning and Re-embedding

Store or track metadata indicating which model/version produced each vector. When changing models, follow a migration plan:

1. Create a new field or index for the new embedding version.
2. Re-embed data using the new model.
3. Verify dimensions and retrieval quality.
4. Run shadow queries or offline comparisons.
5. Shift traffic once results meet targets.
6. Retire the old field/index after the rollback window closes.

Do not mix vectors from two incompatible models into the same field merely because they share dimensions.

## 7. kNN Search with `dense_vector`

kNN locates vectors closest to the query vector under the configured metric. Request example:

~~~http
GET /products-v1/_search
{
  "knn": {
    "field": "embedding",
    "query_vector": [0.12, -0.08, 0.44],
    "k": 20,
    "num_candidates": 200
  },
  "size": 20
}
~~~

The example vector is abbreviated to illustrate structure; real requests must supply the full dimension count declared in the mapping.

Key parameters:

- `field`: `dense_vector` field.
- `query_vector`: query embedding.
- `k`: number of nearest neighbors to retrieve.
- `num_candidates`: candidates evaluated per shard before picking final results under ANN.
- `size`: maximum hits returned.

Raising `num_candidates` can generally improve recall while increasing CPU/latency cost. Choose `k` and `num_candidates` via benchmarking rather than inflating them arbitrarily in hopes of better results.

### Approximate kNN and Exact Search

Approximate nearest neighbor (ANN) uses a vector index structure for fast approximate search over large datasets. Exact vector scoring scans more vectors and suits small sets or reranking over bounded candidates.

Core trade-offs:

| Approach | Strengths | Limitations |
|---|---|---|
| ANN / HNSW | Fast lookup across large vector datasets | May miss true neighbors |
| Exact scoring on bounded set | Exact control over candidate set | Unsuitable for scanning large indexes |
| Full-corpus exact scan | Exact nearest results under the metric | Cost can be prohibitive |

Do not confuse `k` with the final document count of the full hybrid result. A vector branch may fetch a larger candidate set than the final `size` so rank fusion has sufficient overlap to work with.

## 8. Hybrid Search: Two Branches, One Result

Hybrid search can be structured as:

1. Lexical retriever: searches using BM25 or Query DSL.
2. Vector retriever: searches using kNN.
3. Rank fusion: merges both result lists.
4. Optional reranker: reorders a small candidate set using a model or business signals.

~~~text
              User query
                  |
          +-------+-------+
          |               |
          v               v
    Lexical branch    Embedding model
          |               |
          v               v
      BM25 search       kNN search
          |               |
          +-------+-------+
                  |
                  v
             Rank fusion
                  |
                  v
             Top results
                  |
             Optional rerank
                  |
                  v
             API response
~~~

A single document may appear in both branches. Fusion must merge by document identity, prevent duplicates, and retain required metadata from both sources.

### Why Not Directly Add Both Scores?

BM25 scores and vector similarity scores follow different distributions. For example, BM25 can range from 0 up to large values depending on corpus and query; cosine similarity has its own range and semantics. Directly summing two uncalibrated values can let one branch overwhelm the other.

Score normalization/weighted combination can work when backed by evaluation data and clear calibration. A commonly used alternative is Reciprocal Rank Fusion.

## 9. Reciprocal Rank Fusion (RRF)

RRF merges results based on rank rather than adding raw scores.

For each document, its RRF score is the sum of contributions across lists:

\[
RRF(d) = \sum_{r \in R} \frac{1}{k_0 + rank_r(d)}
\]

Where:

- `R` is the set of result lists from retrievers.
- `rank_r(d)` is the document's position in retriever `r`'s list.
- `k_0` is the rank constant controlling how strongly top ranks dominate.

If a document does not appear in a list, that branch contributes zero points to the document.

Example:

| Document | Lexical rank | Vector rank |
|---|---:|---:|
| P-100 | 1 | 8 |
| P-200 | 3 | 2 |
| P-300 | 2 | Not present |
| P-400 | Not present | 1 |

RRF can promote `P-100` and `P-200` to the top because both branches rated them well. `P-400` has a strong vector rank without lexical matches; `P-300` has a strong lexical rank without vector matches. Final ordering depends on the rank constant and rank window.

RRF avoids directly comparing BM25 scores against cosine scores, making it a solid starting point for hybrid retrieval.

### `rank_window_size` and `rank_constant`

- `rank_window_size` determines how many hits from each retriever are considered during fusion.
- `rank_constant` adjusts how rank positions contribute.

If the rank window is too small, good documents sitting just outside one branch's window cannot participate in fusion. If it is too large, intermediate memory and compute rise.

There is no fixed optimal value. Evaluate using representative queries and your latency budget.

## 10. Hybrid Search via the Retriever API

Elasticsearch versions supporting the retriever API can combine a `standard` retriever and a `knn` retriever with `rrf` directly inside a single search request.

Query DSL example:

~~~http
GET /products-v1/_search
{
  "retriever": {
    "rrf": {
      "retrievers": [
        {
          "standard": {
            "query": {
              "multi_match": {
                "query": "lightweight laptop long battery",
                "fields": [
                  "name^3",
                  "description"
                ]
              }
            }
          }
        },
        {
          "knn": {
            "field": "embedding",
            "query_vector": [0.12, -0.08, 0.44],
            "k": 50,
            "num_candidates": 200
          }
        }
      ],
      "rank_window_size": 100,
      "rank_constant": 60
    }
  },
  "size": 20
}
~~~

The example vector is abbreviated. Replace it with the full vector produced by your embedding model.

The retriever API and sub-retrievers are supported depending on Elasticsearch version. The RRF retriever also has version/license requirements depending on distribution and deployment environment. Verify your cluster's API capabilities before choosing this path.

### Applying Filters in Both Branches

If the API searches within a tenant or active products only, filters must be applied properly in each retriever branch.

Example:

~~~http
GET /products-v1/_search
{
  "retriever": {
    "rrf": {
      "retrievers": [
        {
          "standard": {
            "query": {
              "bool": {
                "must": [
                  {
                    "multi_match": {
                      "query": "long battery laptop",
                      "fields": ["name", "description"]
                    }
                  }
                ],
                "filter": [
                  { "term": { "tenantId": "tenant-A" } },
                  { "term": { "status": "ACTIVE" } }
                ]
              }
            }
          }
        },
        {
          "knn": {
            "field": "embedding",
            "query_vector": [0.12, -0.08, 0.44],
            "k": 50,
            "num_candidates": 200,
            "filter": {
              "bool": {
                "filter": [
                  { "term": { "tenantId": "tenant-A" } },
                  { "term": { "status": "ACTIVE" } }
                ]
              }
            }
          }
        }
      ],
      "rank_window_size": 100,
      "rank_constant": 60
    }
  },
  "size": 20
}
~~~

This illustrates the modern retriever API structure. Exact syntax and filter placement must match your Elasticsearch version. Crucially, tenant/status scoping must be enforced on both lexical and vector retrieval. Filtering only one branch allows out-of-scope documents from the other branch to enter fusion.

`tenantId` must come from server-side authenticated context, never as a trusted value sent by the client.

## 11. Hybrid Search on Versions Without an RRF Retriever

If your cluster does not support the retriever API or RRF, you can execute two independent queries:

~~~text
Search service
    |
    +---- lexical query ---> top N lexical hits
    |
    +---- vector query ----> top N vector hits
    |
    v
Application-side RRF
    |
    v
Deduplicate by document ID
    |
    v
Fetch/map response DTO
~~~

The service can run both independent requests in parallel if the client, connection pool, and resource budget allow. Afterward, the application builds a rank map keyed by document ID and computes RRF.

Pseudocode:

~~~java
Map<String, Double> scores = new HashMap<>();

addRrfScores(scores, lexicalHits, rankConstant);
addRrfScores(scores, vectorHits, rankConstant);

List<String> orderedIds = scores.entrySet().stream()
    .sorted(Map.Entry.<String, Double>comparingByValue().reversed())
    .map(Map.Entry::getKey)
    .toList();
~~~

Helper:

~~~java
private void addRrfScores(
        Map<String, Double> scores,
        List<SearchHit<Product>> hits,
        int rankConstant) {

    for (int i = 0; i < hits.size(); i++) {
        String id = hits.get(i).getId();
        int rank = i + 1;

        scores.merge(
            id,
            1.0 / (rankConstant + rank),
            Double::sum
        );
    }
}
~~~

The pseudocode assumes document IDs are unique across merged results. If IDs can collide across indexes or tenants, use a composite key combining index/tenant and ID per contract.

### Pros and Cons of Application-Side Fusion

Pros:

- Works on older clusters.
- Easy to experiment with different fusion formulas.
- Easy to incorporate business signals or rerankers.
- Decouples retrieval strategy from API endpoints.

Cons:

- Two requests add extra network round trips.
- Service must hold and merge candidate lists.
- Pagination over fused results becomes more complex.
- Partial failures must be handled if one branch fails.
- Identical filter/tenant scope must be maintained across both branches.

If one branch fails, do not silently return the other branch's results as if hybrid search succeeded. If a fallback applies, signal degraded mode in the response or log/emit metrics clearly per contract.

## 12. Spring Data Elasticsearch and `NativeQuery`

Spring Data Elasticsearch provides `ElasticsearchOperations` and `NativeQuery` to build and execute queries using the Elasticsearch Java API Client abstraction.

A lexical query:

~~~java
NativeQuery query = NativeQuery.builder()
    .withQuery(q -> q.multiMatch(m -> m
        .query(searchText)
        .fields("name^3", "description")
    ))
    .withPageable(PageRequest.of(0, 50))
    .build();

SearchHits<ProductDocument> hits =
    operations.search(query, ProductDocument.class);
~~~

You can then map `SearchHit::getContent` or retain hit metadata to build the response.

### Vector and Hybrid APIs Depend on the Release Train

Support for expressing kNN, `retriever`, and RRF via `NativeQuery` evolves across Spring Data Elasticsearch and Elasticsearch Java API Client releases. Some releases expose kNN search APIs; the retriever API may not yet be exposed by the abstraction.

Verify all three version layers:

1. Elasticsearch server version and feature availability.
2. Spring Data Elasticsearch version.
3. Elasticsearch Java API Client version managed by Spring Data.

Do not copy a builder method from another release assuming it will compile. If the abstraction does not yet expose a needed retriever, call the Java API Client directly inside a dedicated gateway and map responses back to application models.

### Isolating a Query Gateway

You can define an interface:

~~~java
public interface ProductHybridSearchGateway {

    ProductHybridSearchResult search(
        ProductSearchCriteria criteria,
        float[] queryVector,
        String tenantId
    );
}
~~~

The implementation handles:

- Selecting the version-appropriate hybrid strategy.
- Constructing lexical and vector branches.
- Enforcing mandatory filters.
- Running RRF or calling the retriever API.
- Preserving required metadata.
- Translating Elasticsearch responses into application results.

Services do not need to know about the retriever API or low-level fusion details.

## 13. `semantic_text` and Elasticsearch-Managed Inference

Some Elasticsearch versions provide `semantic_text` to simplify semantic search. This field type integrates an inference endpoint to generate embeddings for content and handle semantic queries based on cluster configuration.

Conceptual model:

~~~text
Document text
     |
     v
Elasticsearch semantic field
     |
     v
Configured inference endpoint
     |
     v
Embedding + semantic indexing
~~~

Query:

~~~http
GET /products/_search
{
  "query": {
    "semantic": {
      "field": "semanticDescription",
      "query": "thin lightweight laptop suitable for school"
    }
  }
}
~~~

Syntax, field types, inference configuration, model deployment, and availability depend on version, distribution, and license. Verify that your cluster supports `semantic_text` and `semantic` queries before building an application around them.

### Differences Between Self-Managed `dense_vector` and `semantic_text`

| Criterion | `dense_vector` | `semantic_text` |
|---|---|---|
| Embedding generation | Typically managed by application or ingest pipeline | Can be managed by inference integration |
| Vector control | Explicit, direct | Abstracts away many details |
| Model lifecycle | Application manages | Requires managing cluster inference endpoints/models |
| Pipeline customization | Flexible | Depends on semantic field capabilities |
| Hybrid with lexical | Combinable via retriever/fusion | Can pair with lexical branches per supported APIs |
| Portability | Requires carrying model and vector schema | Coupled to Elasticsearch feature set and inference setup |

`semantic_text` does not mean Elasticsearch understands content without a model. An inference model, endpoint, and configuration are still required.

## 14. Chunking When Searching Long Documents

For long documents, one embedding for the whole document can obscure details. You can split content into chunks and generate a vector for each chunk.

Example:

~~~text
Document
  |
  +-- Chunk 1 -> embedding 1
  +-- Chunk 2 -> embedding 2
  +-- Chunk 3 -> embedding 3
  +-- Chunk 4 -> embedding 4
~~~

Each chunk typically needs metadata:

- `documentId`.
- `chunkId` or position.
- `title`.
- `tenantId`/permission scope.
- `content`.
- `embedding`.
- Source/version.
- Parent document reference.

Vector retrieval returns matching chunks. The application can group by `documentId`, take the top chunks, or rerank at the document level.

### Choosing Chunk Size

Chunks that are too large blend multiple topics into one embedding. Chunks that are too small lose context and inflate vector counts. Overlap can help preserve sentences or paragraphs across chunk boundaries.

Size and overlap must be tested with the real corpus, model tokenizer, and user query patterns. No single token count fits every document type.

### Deduplicating at the Document Level

A document with many chunks can occupy multiple slots in the vector candidate list. If the API returns a list of documents, group chunks by document ID and define how scores/ranks aggregate.

Do not simply sum chunk scores without defining semantics. You can use max score, top chunk, weighted aggregation, or a document-level reranker.

## 15. Filters, Tenants, and Access Control in Hybrid Search

Filters must be applied consistently across every branch. For example, `status`, `category`, time ranges, and tenant scope must never be dropped in the vector query while present in the lexical query.

For multi-tenant systems:

- `tenantId` is obtained from the authenticated principal.
- Lexical queries include the tenant filter.
- kNN queries include the appropriate pre-filter.
- Application-side fusion merges only hits from the same scope.
- Post-fusion fetches by ID still verify tenant ownership.

Do not use routing as an authorization mechanism. Routing picks a shard; tenant filters and access permissions restrict which documents are returned.

### Pre-Filter and Post-Filter in kNN

A filter applied prior to ANN candidate selection affects recall and the number of candidates explored. Post-retrieval filtering can leave fewer than `k` final results if many candidates are discarded.

Elasticsearch supports filter constructs inside kNN depending on version and API. Verify pre-filter/post-filter semantics of your endpoint. For tenant isolation, never remove filters just to boost recall.

If a filter is very narrow, you may need to raise the candidate budget or design appropriate index partitioning, while preserving access boundaries.

## 16. Choosing How to Combine Scores and Rankings

Several strategies exist for combining lexical and vector results.

### RRF

Combines by rank without normalizing raw scores. Usually an easy baseline to evaluate and insensitive to score scale differences.

### Weighted Score Combination

Scores can be normalized and combined:

\[
S(d) = \alpha \cdot S_{lexical}(d)
      + (1-\alpha) \cdot S_{vector}(d)
\]

Where `alpha` tunes the weight. This formula is only meaningful after both scores are properly normalized/calibrated. Using raw BM25 and raw vector scores can allow one branch to dominate.

### Reranking

Retrieve top candidates from hybrid retrieval and use a reranker model or business rules to reorder them. Rerankers are more expensive, so apply them only to a bounded candidate set.

Signals you can combine:

- Lexical rank.
- Vector rank.
- Reranker model score.
- Exact SKU/name match.
- Popularity or freshness.
- Business availability.
- Permitted personalization signals.

Never let business boosts override filters or access policies. Security filters must run before ranking.

## 17. Pagination and Candidate Windows

Pagination in hybrid search is more complex than in simple queries because results pass through multiple retrieval and fusion stages.

Distinguish:

- `k`: nearest neighbors in the vector branch.
- `num_candidates`: vector candidates examined per shard.
- `rank_window_size`: results each retriever supplies to fusion.
- `size`: final results returned to the client.

`size = 20` does not mean each branch only needs 20 candidates. A larger rank window lets fusion promote documents ranking moderately well in both branches.

### Deep Pages

Offset pagination over hybrid results can be costly or unsupported like standard queries depending on the retriever API. If deep traversal is needed, check PIT/`search_after` or cursor support for your specific hybrid API.

Do not fetch top 20 from both branches and try to serve page 5 by skipping 80 results when candidate windows lack coverage. Responses should document pagination semantics and limits clearly.

In interactive search UIs, prioritizing the top 10–50 results and query refinement is usually preferable to allowing very deep pages.

## 18. Performance and Operational Costs

Hybrid search introduces extra costs:

- Generating query embeddings.
- Storing and indexing vectors.
- ANN candidate search.
- Running lexical queries.
- Fusion or reranking.
- Network and memory for candidate lists.
- Re-embedding when models or content change.

Factors to monitor:

| Component | Metrics to track |
|---|---|
| Embedding service | latency, timeouts, error rate, queue depth |
| Lexical branch | latency, hit count, shard fan-out |
| Vector branch | latency, candidate count, recall estimate |
| Fusion | merge duration, candidate size |
| Reranker | latency, throughput, error rate |
| End-to-end | p50/p95/p99, timeouts, result counts |
| Index | vector count, disk, segments, indexing throughput |

### Caching Query Embeddings

You can cache embeddings for repeated queries if privacy and freshness policies allow. Cache keys must incorporate model version and preprocessing version.

Do not cache embeddings by raw query alone if identical text runs under different model versions. Caches also need size limits and TTLs.

### Batch Embedding

When ingesting many documents, batching requests to the model is usually more efficient than one document at a time. Cap batch size, retries, and backpressure to avoid overwhelming the inference service.

### Vector Storage and Quantization

Some Elasticsearch versions support vector element types or quantization/index options to reduce memory and disk usage. These options can affect recall and require specific configuration. Benchmark before enabling; never treat quantization as a free optimization.

## 19. Relevance Evaluation

Hybrid search must be evaluated using a representative query set and relevance judgments. A technically successful query does not prove results are useful.

Build an evaluation set containing:

- Realistic user queries scrubbed for privacy.
- Relevant documents or products.
- Graded relevance labels.
- Groups covering exact, semantic, technical code, and long queries.
- Appropriate tenant/filter contexts.
- Cases with no valid results.

Common metrics:

- **Recall@k:** fraction of relevant documents found in top `k`.
- **Precision@k:** fraction of top `k` results that are genuinely relevant.
- **MRR:** position of the first relevant result.
- **nDCG@k:** ranking quality accounting for graded relevance.
- **Latency p95/p99:** tail response times.

Compare at least three baselines:

1. Lexical only.
2. Vector only.
3. Hybrid (RRF or another fusion strategy).

You can add hybrid + reranker once baselines are established.

### Breakdown by Query Group

A strong overall average can mask regressions on a specific query category. Analyze separately:

- Exact SKU/model.
- Brand/product name.
- Natural-language intent.
- Synonyms and regional phrasing.
- Very short queries.
- Multi-constraint queries.
- Vietnamese queries with and without diacritics if supported.
- Queries with typos.

Hybrid search often boosts semantic recall yet can demote exact matches if fusion/ranking is not tuned. Test both categories.

## 20. Tuning on Real Data

An iterative tuning workflow:

1. Lock down the query set and relevance judgments.
2. Measure the lexical baseline.
3. Measure the vector baseline.
4. Add RRF with initial rank window and rank constant.
5. Inspect queries improved or degraded by hybrid search.
6. Adjust field boosts, candidate counts, and rank window.
7. Try a reranker if gains justify the cost.
8. Measure latency/cost alongside relevance.
9. Run shadow traffic or A/B tests.
10. Monitor drift as corpus or models evolve.

Do not optimize a single metric blindly. Raising Recall@100 may not improve top 10. Cutting latency with overly small candidate counts can drop key documents.

### Exact Match Boosting

If SKUs or exact names must appear at the top, add a high-boost lexical clause or pre-fusion exact-match prioritization rule. Test carefully so an overly broad exact clause does not tie scores across unrelated results.

### Query Rewriting

You can normalize queries, expand synonyms, or extract entities before retrieval. Keep both original and rewritten queries in appropriate telemetry to analyze quality while avoiding logging unnecessary sensitive data.

## 21. Testing Hybrid Search

A test suite should span multiple layers.

### Unit Tests

Mock `EmbeddingService` to return deterministic vectors. Verify:

- Query text passes cleanly to the embedding service.
- Query criteria build required lexical clauses.
- Tenant/status filters are applied.
- Fusion deduplicates by exact document identity.
- RRF computes ranks properly.
- Sorting and response metadata map accurately.
- Embedding dimension mismatches are caught before querying when possible.

### Integration Tests with Elasticsearch

Against a compatible Elasticsearch version, verify:

- `dense_vector` mapping has expected dimensions and similarity.
- Vector indexing and kNN queries work.
- Lexical queries return results under the analyzer.
- Retriever API/RRF works if used.
- Filters apply across both branches.
- Results never contain out-of-tenant documents.
- Score/rank metadata maps accurately.
- Queries with mismatched vector dimensions fail per contract.

Do not assert the top document using arbitrary random vectors without meaningful distance relationships. Construct test vectors with known distances or use a stable model fixture.

### API Contract Tests

Verify response envelopes contain:

- Items matching schema.
- Pagination metadata.
- Sort semantics.
- Optional scores/highlights when requested.
- Cursors or facets if supported by the endpoint.
- Error responses when the embedding service is unavailable.
- No leaked raw vectors or internal index metadata outside the contract.

### Model Failure Tests

Simulate:

- Inference timeouts.
- Unavailable model endpoints.
- Wrong response dimensions.
- Incompatible model versions.
- Embeddings containing `NaN`/`Infinity` or invalid values if clients can encounter them.

Do not retry indefinitely. If the vector branch fails, define a lexical-only fallback policy and surface it through metrics and response semantics.

## 22. Error Handling and Fallbacks

Hybrid search depends on multiple components, so either branch can fail.

| Failure | Handling strategy |
|---|---|
| Embedding service timeout | Bounded retry or lexical-only fallback if policy allows |
| Vector dimension mismatch | Abort query, log configuration/model error |
| kNN field unmapped | Do not retry; fix mapping/index |
| Retriever API unsupported | Use version-appropriate API or application-side fusion |
| Lexical branch error | Return error or degraded mode per contract |
| One branch returns empty | Can still fuse remaining branch if semantics are defined |
| Missing tenant filter on one branch | Treat as correctness/security bug, never fall back by dropping filter |
| Reranker timeout | Can fall back to initial hybrid ordering if degraded mode is surfaced/monitored |

Do not return a response as if full hybrid succeeded when only one branch worked without recording degraded mode. Emit metrics for fallback counts and per-branch error rates.

## 23. Common Pitfalls

| Symptom | Possible cause | Resolution |
|---|---|---|
| Vector query rejected | Dimensions mismatch mapping | Verify model output and `dense_vector` `dims` |
| Vector search returns confusing results | Mismatched model/index/query preprocessing | Synchronize model and preprocessing versions |
| Exact SKU fails to rank first | Vector rank outranks lexical | Add exact lexical boost or priority rule |
| Hybrid search much slower | Oversized candidate windows or high embedding latency | Measure each branch, tune candidates and cache |
| Unexpected RRF results | One branch lacks wide enough candidates | Adjust rank window and candidate counts |
| Score addition skews ranking | BM25 and vector scores on different scales | Use RRF or calibration |
| Missing hits after filtering | Filter applied after ANN or on one branch only | Apply proper pre-filters to both branches |
| Cross-tenant documents appear | One branch missing tenant filter | Enforce tenant scope in both lexical and vector queries |
| Duplicate documents in response | Same ID appears in both branches | Deduplicate before response mapping |
| Results shift after model deployment | Embedding space changed | Version models and re-embed |
| Long document searches miss details | Single vector for overly long document | Chunk documents and aggregate by parent |
| Unstable deep pages | Insufficient candidate windows and pagination | Use supported cursors/APIs and limit page depth |
| `NativeQuery` lacks needed retriever API | Spring Data/client version does not expose feature | Use a Java API Client gateway or app-side fusion |

## 24. Hybrid Search Implementation Checklist

- [ ] Identify which queries need lexical, vector, or both.
- [ ] Map `text`/`keyword` fields with appropriate analyzers and exact filters.
- [ ] Select an embedding model suited to the language and domain.
- [ ] Track model version and preprocessing version.
- [ ] Match `dense_vector` dimensions to model output.
- [ ] Choose the similarity metric matching the model.
- [ ] Generate embeddings at index time and query time via the same pipeline.
- [ ] Evaluate `semantic_text` if the cluster supports inference integration.
- [ ] Choose kNN candidate counts and `k` via benchmarks.
- [ ] Choose RRF or calibrated score fusion.
- [ ] Never add raw BM25 and vector scores arbitrarily.
- [ ] Verify retriever API and RRF support for your Elasticsearch version.
- [ ] Verify corresponding API exposure in your Spring Data release train.
- [ ] Isolate direct client usage or app-side fusion in a gateway if needed.
- [ ] Enforce tenant/filter scope across every retrieval branch.
- [ ] Deduplicate results by document identity.
- [ ] Define pagination and cursor semantics.
- [ ] Establish a chunking strategy for long documents.
- [ ] Monitor embedding, lexical, vector, fusion, and end-to-end latencies.
- [ ] Evaluate Recall@k, Precision@k, MRR, and nDCG.
- [ ] Test exact identifiers alongside semantic intent.
- [ ] Test model timeouts, dimension mismatches, and degraded modes.
- [ ] Maintain a re-embedding plan for model changes.

Keyword search excels at finding what users explicitly wrote; vector search excels at finding semantically related content via embeddings; hybrid search combines both lists to improve accuracy across diverse query types. With Elasticsearch, you can use `retriever`/RRF where supported by the cluster, or fuse both branches in a service on older versions. Spring Data Elasticsearch supplies the mapping and access layer, while the embedding model and fusion strategy require clear design. Keep filters and tenant scoping on both branches, version embeddings, evaluate with real queries, and balance relevance against latency before deploying hybrid search to production.
