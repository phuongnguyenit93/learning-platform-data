# Embedding, `dense_vector`, and Data Dimensions

Keyword search typically relies on the occurrence of words or phrases inside a document. This works well when users know the exact terms to search for, but it can miss documents that express the same idea using different words. Semantic search adds a meaning-based representation of content: an embedding model converts text into a numeric vector, and Elasticsearch searches for vectors that are close in multi-dimensional space.

In Spring Data Elasticsearch, applications typically store embedding vectors in a `dense_vector` field and then use k-nearest neighbors (kNN) to find documents whose vectors are close to the query vector. For this to work properly, you must consistently manage:

- The embedding model and model version.
- Content normalization, chunking, and preprocessing rules.
- Vector dimensions.
- The data type and mapping of the `dense_vector` field.
- The similarity or distance function.
- How embeddings are generated for documents and for queries.
- Procedures for updating, testing, and rebuilding indexes when models change.

Dimensions are not merely a configuration number. They are part of the contract between the embedding model, indexed data, and query vectors. Vectors with the wrong dimensions or produced by an incompatible model can cause write/query failures or yield meaningless results.

## 1. What Is an Embedding?

An embedding is a numeric representation of content. An embedding model accepts text, images, or other data and outputs a vector of floating-point numbers. In text search, vectors are commonly generated from a sentence, paragraph, or document.

Illustrative example:

~~~text
"How do I reset my password?"
              |
              v
       Embedding model
              |
              v
[0.12, -0.08, 0.31, 0.44, ...]
              |
              v
         Dense vector
~~~

Two sentences phrased differently with the same meaning can have close vectors:

- "How can I reset my password?"
- "I forgot my password. How do I create a new one?"

Semantic search leverages distances or similarities between vectors rather than relying solely on word matching.

An embedding is not a human-readable summary. Individual vector elements do not correspond simply to a single word or named feature. Meaning is distributed across the entire vector and learned from the model's training data.

## 2. The Embedding Model Determines the Vector

An application does not arbitrarily pick a dimension count and ask a model to produce vectors of that size. A model has its own architecture and output configuration. When called, it returns a vector whose dimension count is determined by the model or by output dimension options supported by that model.

Common dimension sizes seen across different models include 384, 512, 768, 1024, or 1536. These are examples only; do not infer dimensions from a model name or from another model in the same family. Always read the metadata and documentation of the model in use, or verify the returned vector length in an integration environment.

### 2.1. One Model, One Embedding Contract

For a specific model, the embedding contract should define:

| Attribute | Meaning |
|---|---|
| Model ID | Which model generates the vector |
| Model revision | Model version or snapshot |
| Dimensions | Number of elements in the vector |
| Input type | Text, image, or other input modality |
| Preprocessing | Normalization, markup stripping, language, and cleaning rules |
| Chunking | How long documents are split into segments |
| Normalization | Whether vectors are normalized to unit length |
| Similarity | Cosine, dot product, or L2 |

Document embeddings and query embeddings must be compatible with each other. If documents are indexed with model A while query vectors are generated with model B, even matching dimensions do not guarantee the two vectors reside in the same semantic space.

### 2.2. Document Embedding and Query Embedding

The pipeline typically has two branches:

~~~text
        Source content
              |
       Clean / chunk
              |
       Embedding model
              |
        Document vector
              |
       Elasticsearch index

        Search query
              |
       Query preprocessing
              |
       Same embedding model
              |
         Query vector
              |
       Elasticsearch kNN
              |
       Search results
~~~

In some systems, a model provides distinct encoding modes for documents and queries (such as different prompts or task types). In those cases, use the exact mode specified by the model documentation. Both branches must still belong to a compatible embedding space.

Do not change prompts, pooling strategies, or preprocessing on one branch without re-evaluating search quality.

## 3. What Do Data Dimensions Mean?

A vector with `D` dimensions is a list of `D` numeric values:

~~~text
v = [v1, v2, v3, ..., vD]
~~~

If a model returns 768 elements, that vector has 768 dimensions. The `dense_vector` field is declared with that corresponding dimension count. Every document indexed into the field must contain that exact number of elements; query vectors must also have the same number of dimensions.

Example:

~~~json
{
  "embedding": [0.12, -0.08, 0.31, 0.44]
}
~~~

The example vector has 4 dimensions. The mapping declares `dims` as 4. If a document sends 3 or 5 elements, Elasticsearch can reject the document. If a query vector has a length different from the mapping, the query is also invalid.

### 3.1. Dimensions Are a Schema Contract

Dimensions affect:

- Index mapping.
- Storage size per vector.
- Similarity computation cost.
- Memory and index footprint.
- Approximate nearest neighbor algorithm configuration.
- Compatibility between older and newer data.

For a `float32` vector before overhead, `D` dimensions occupy roughly `4 × D` bytes for the numeric payload. For instance, 768 dimensions take around 3 KB per vector, while 1536 dimensions take around 6 KB per vector. This is an estimate for the numeric payload alone; actual size also depends on metadata, index structures, graphs, quantization, and Elasticsearch/Lucene overhead.

### 3.2. More Dimensions Are Not Automatically Better

Higher-dimensional vectors can encode more information, but they also increase storage, indexing, and search costs. Quality depends on the model, data, task, and evaluation method; you cannot conclude that 1536 dimensions always outperform 384 dimensions.

When selecting a model/dimensions, evaluate:

- Recall@k or an appropriate retrieval metric.
- NDCG/MRR if result ordering matters.
- p50/p95/p99 latency.
- Throughput and embedding cost.
- Index size and memory usage.
- Quality on the actual language and domain.

Choose the configuration that meets quality targets and SLAs at an acceptable cost.

## 4. `dense_vector` in Elasticsearch

Elasticsearch provides the `dense_vector` field type for storing fixed-length numeric vectors. The mapping declares the field, dimensions, and version-appropriate similarity/index options.

Example mapping:

~~~json
PUT products-semantic-v1
{
  "mappings": {
    "properties": {
      "productId": {
        "type": "keyword"
      },
      "name": {
        "type": "text"
      },
      "embedding": {
        "type": "dense_vector",
        "dims": 4,
        "index": true,
        "similarity": "cosine"
      }
    }
  }
}
~~~

This example uses a 4-dimensional vector for illustration. In a real application, replace `dims` with the exact dimension count of your model. `dense_vector` properties and defaults vary across Elasticsearch versions; explicitly declare required settings and check the documentation for the running cluster.

### 4.1. `dims`

`dims` is the number of dimensions of the vector. It must be the exact number of dimensions actually returned by the model. Never choose an arbitrary dimension count just to fit an existing mapping.

Before indexing, the application can check:

~~~java
if (embedding == null || embedding.length != EXPECTED_DIMENSIONS) {
    throw new IllegalArgumentException(
            "Embedding dimension does not match index mapping"
    );
}
~~~

Checking at the application layer catches errors close to where data is produced. Elasticsearch remains the final schema safeguard.

### 4.2. `index`

Depending on version and configuration, `dense_vector` can be stored for script scoring or indexed for approximate kNN. When efficient kNN is needed on large datasets, configure the field according to your version's vector indexing capabilities.

Do not rely on default `index` behavior if the system requires stable behavior across upgrades. Declare it explicitly and verify the resulting mapping after index creation.

### 4.3. `similarity`

Common options:

- `cosine`: compares the angle between two vectors.
- `dot_product`: inner product; normalization requirements depend on vector type and usage.
- `l2_norm`: based on Euclidean distance.

Do not choose a similarity metric by name alone. Use the function suited to the model and how vectors are normalized. If the model recommends cosine similarity, use `cosine` or an equivalent option supported by the model and Elasticsearch documentation.

## 5. Cosine, Dot Product, and L2

### 5.1. Cosine Similarity

Cosine similarity measures the cosine of the angle between two vectors:

\[
\operatorname{cosine}(a,b)=
\frac{a \cdot b}{\|a\|\|b\|}
\]

Larger values generally indicate vectors pointing in closer directions. Cosine depends less on vector magnitude than dot product because it normalizes by vector norms.

### 5.2. Dot Product

Dot product:

\[
a \cdot b = \sum_{i=1}^{D} a_i b_i
\]

If two vectors are L2-normalized to unit length (norm 1), the dot product equals cosine similarity. If unnormalized, vector magnitude also influences the score.

Some models are trained specifically for dot product over normalized vectors or under a particular scoring convention. Follow the model guidelines.

### 5.3. L2 Distance

Euclidean distance:

\[
\operatorname{L2}(a,b)=
\sqrt{\sum_{i=1}^{D}(a_i-b_i)^2}
\]

Smaller distance means vectors are closer. When using L2, understand how Elasticsearch converts distance into `_score` in search results; the returned score is not necessarily the raw distance itself.

### 5.4. Do Not Arbitrarily Compare Scores

Scores from cosine, dot product, and L2 may be transformed to fit Elasticsearch's scoring model. Do not directly compare a score across two different embedding models, two different similarity functions, two indexes with different vector configurations, or two queries with different normalization.

To evaluate quality, use ranking metrics over a labeled query/document set or actual evaluation data rather than setting one universal score threshold across all models.

## 6. Declaring `dense_vector` in Spring Data Elasticsearch

Create a dedicated class for the search document:

~~~java
@Document(indexName = "products-semantic-v1")
public class ProductVectorDocument {

    @Id
    private String id;

    @Field(type = FieldType.Keyword)
    private String productId;

    @Field(type = FieldType.Text)
    private String name;

    @Field(type = FieldType.Dense_Vector, dims = 4, similarity = "cosine")
    private float[] embedding;

    @Field(type = FieldType.Keyword)
    private String embeddingModel;

    @Field(type = FieldType.Keyword)
    private String embeddingVersion;

    // getters and setters
}
~~~

This example illustrates mapping in Spring Data Elasticsearch versions that support `FieldType.Dense_Vector`, `dims`, and `similarity`. Enum/annotation attribute names and Java type mapping capabilities depend on the release train. Check the Javadoc of your dependency; some versions support `float[]`, `List<Float>`, or other vector types with specific constraints.

If your Spring Data version does not yet expose needed mapping attributes, manage the index mapping via JSON or an index template and use an appropriate client to execute queries. What matters is that the actual mapping in Elasticsearch matches the vectors being written.

### 6.1. Storing Model Metadata Alongside the Document

Alongside the vector, store metadata that helps track provenance:

- `embeddingModel`: model identifier.
- `embeddingVersion`: revision or version of the embedding pipeline.
- `sourceVersion`: version of the source data.
- `chunkId`: segment identifier if the document is chunked.
- `contentHash`: hash of the embedded content to avoid recomputing when content has not changed.

Not every piece of metadata needs to live in Elasticsearch. However, the system needs somewhere to determine which model and content produced a vector.

### 6.2. Do Not Share the Same Field Across Incompatible Models

If model A returns 768 dimensions and model B returns 1536 dimensions, you cannot write both into the same `dense_vector` field declared with a fixed `dims`.

Even when A and B both return 768 dimensions, do not mix their vectors in the same field as if they shared one space. Vector distance is only meaningful when produced within a compatible embedding space.

## 7. Generating and Validating Embeddings Before Saving

Embeddings are typically generated by a model service or ML library. Spring Data Elasticsearch is responsible for storing and querying documents; it does not automatically convert content into embeddings unless the application integrates a model.

You can define an abstraction:

~~~java
public interface EmbeddingService {

    EmbeddingResult embedDocument(String text);

    EmbeddingResult embedQuery(String text);
}

public record EmbeddingResult(
        float[] vector,
        String model,
        String modelVersion
) {
}
~~~

Service invoking the model:

~~~java
EmbeddingResult result = embeddingService.embedDocument(
        product.getName() + " " + product.getDescription()
);

if (result.vector().length != EXPECTED_DIMENSIONS) {
    throw new IllegalStateException("Unexpected embedding dimensions");
}

ProductVectorDocument document = new ProductVectorDocument();
document.setId(product.getId().toString());
document.setProductId(product.getId().toString());
document.setName(product.getName());
document.setEmbedding(result.vector());
document.setEmbeddingModel(result.model());
document.setEmbeddingVersion(result.modelVersion());

elasticsearchOperations.save(document);
~~~

Method and class names are domain examples. In production, handle model service errors, timeouts, rate limits, batch requests, bounded retries, and appropriate logging.

### 7.1. Validating Vectors

In addition to length, check:

- The vector is non-null.
- Dimensions are exact.
- No `NaN` or `Infinity` values exist.
- Values fall within the range permitted by the model.
- Norm is valid if the pipeline requires normalized vectors.
- Model/version matches the target index.

Example:

~~~java
static void validateEmbedding(float[] vector, int dimensions) {
    if (vector == null || vector.length != dimensions) {
        throw new IllegalArgumentException("Invalid embedding dimensions");
    }

    for (float value : vector) {
        if (!Float.isFinite(value)) {
            throw new IllegalArgumentException(
                    "Embedding contains a non-finite value"
            );
        }
    }
}
~~~

If a model can emit a zero-norm vector or has specific normalization rules, validate according to the model contract. Do not normalize manually if the model already handles it or if doing so breaks semantics.

### 7.2. Do Not Generate Document Embeddings on Every Search Read

Document embeddings should be generated when content is created/updated or through a batch pipeline. Query embeddings are generated when users search. Never call the model to recompute embeddings for all documents on every search request.

For frequent queries, you can cache query embeddings if data policy and latency permit. Cache keys must include model version and preprocessing version to avoid serving vectors built by an outdated pipeline.

## 8. Indexing Documents with Vectors

Example document:

~~~json
{
  "productId": "p-100",
  "name": "Wireless Keyboard",
  "embedding": [0.12, -0.08, 0.31, 0.44],
  "embeddingModel": "catalog-embed",
  "embeddingVersion": "v1"
}
~~~

The application can save via a repository:

~~~java
public interface ProductVectorRepository
        extends ElasticsearchRepository<ProductVectorDocument, String> {
}
~~~

Or via `ElasticsearchOperations`:

~~~java
productVectorRepository.save(document);

// Equivalent write use case via operations:
elasticsearchOperations.save(document);
~~~

Repository `save` is convenient for CRUD. When bulk indexing, custom routing, or specific APIs are required, `ElasticsearchOperations` or the Elasticsearch Java Client may be more suitable.

Do not generate embeddings inside an entity setter. Calling a model is an I/O operation that can fail and take time; place it in an application service or background projection pipeline.

## 9. kNN Querying with Vectors

Once you have a query embedding, Elasticsearch can find the `k` nearest vectors.

Search API example:

~~~http
POST /products-semantic-v1/_search
Content-Type: application/json

{
  "knn": {
    "field": "embedding",
    "query_vector": [0.10, -0.07, 0.30, 0.42],
    "k": 10,
    "num_candidates": 100
  },
  "_source": [
    "productId",
    "name",
    "embeddingModel",
    "embeddingVersion"
  ]
}
~~~

`k` is the desired number of nearest results. `num_candidates` controls how many candidates are examined per shard during approximate kNN search. Increasing `num_candidates` can generally improve recall at the cost of higher compute and latency. Measure on real data.

Specific parameters and semantics depend on the Elasticsearch version. Confirm the kNN API supported by your cluster before designing requests.

### 9.1. Calling via Elasticsearch Java Client

With Elasticsearch Java API Client 8.x supporting `KnnSearch`, a call looks like:

~~~java
SearchResponse<ProductVectorDocument> response =
        elasticsearchClient.search(search -> search
                .index("products-semantic-v1")
                .knn(knn -> knn
                        .field("embedding")
                        .queryVector(toFloatList(queryVector))
                        .k(10)
                        .numCandidates(100)
                ),
                ProductVectorDocument.class
        );
~~~

This is an illustrative structure; builder methods and query vector types must match your Java Client version. If using Spring Data Elasticsearch `NativeQuery`, use the kNN search API supported by that release train or a custom repository calling the Java Client. Do not assume all Spring Data versions share identical builder methods.

### 9.2. Filters in kNN

You often need to filter by status, tenant, category, or access permissions. Some versions support filters inside the kNN request so filtering participates in candidate selection. Lexical and vector queries can also be combined in a hybrid search strategy.

Conceptual example:

~~~json
{
  "knn": {
    "field": "embedding",
    "query_vector": [0.10, -0.07, 0.30, 0.42],
    "k": 10,
    "num_candidates": 100,
    "filter": {
      "bool": {
        "filter": [
          { "term": { "status": "ACTIVE" } },
          { "term": { "categoryId": "cat-7" } }
        ]
      }
    }
  }
}
~~~

Do not let clients dictate tenant/security filters. Security conditions must be added server-side and enforced across every search branch.

## 10. Approximate kNN and Exact Scoring

Finding nearest neighbors can be done in two ways:

**Exact scoring:** computes scores for every document in the considered set, for instance using a script score. Results are exact within that set, but can be expensive on large datasets.

**Approximate nearest neighbors (ANN):** uses a vector index structure, typically HNSW, to quickly find nearest neighbors with the trade-off of potentially missing some results compared to exact search.

| Approach | Advantages | Cost/limitations |
|---|---|---|
| Exact script scoring | Exact computation over the selected candidate/filtered set | CPU-intensive when scoring very large numbers of documents |
| Approximate kNN | Fast lookup across large vector datasets | Trade-off among recall, latency, memory, and indexing cost |

With ANN, HNSW builds a graph linking nearby vectors. Queries traverse the graph to find candidates instead of computing every distance. Index parameters such as `m`, `ef_construction`, or `index_options` depend on the Elasticsearch/Lucene version and configuration.

Do not pick `num_candidates` based on a single demo query. Build a benchmark suite with representative queries and ground truth or an exact baseline, then compare recall@k and latency.

### 10.1. When to Use Exact Scoring?

Exact scoring can work well when the dataset is small, filters narrow candidates down to a low count, an ANN quality baseline is needed, or a specialized scoring script cannot be expressed via ANN.

On large datasets, running similarity scripts across the whole index can be very resource-intensive. Filter candidates appropriately and benchmark first.

## 11. Hybrid Search: Combining Keywords and Vectors

Vector search captures semantics, but may not prioritize exact SKUs, proper names, model numbers, or mandatory phrases. Lexical search such as BM25 excels at word matching. Hybrid search combines both ranking sources.

Example:

- Query: "keyboard for quiet office".
- Vector search finds descriptions like "silent typing" or "low-noise keys".
- BM25 finds documents containing "keyboard", "office", and specific terms.
- The system combines both lists for final ranking.

One combination method is Reciprocal Rank Fusion (RRF), based on each document's rank in each list:

\[
\operatorname{RRF}(d)=
\sum_{r \in R}
\frac{1}{k_0+\operatorname{rank}_r(d)}
\]

RRF avoids directly normalizing BM25 scores and vector scores, which have different scales. Elasticsearch supports various ways to combine lexical and kNN queries depending on version; check the semantics of query-level `knn`, top-level `knn`, and the `retriever` API.

Do not directly add BM25 and cosine scores with an arbitrary multiplier and treat that as stable ranking. If using weighted scores, calibrate on an evaluation set.

## 12. Chunking Long Documents

A long document can cover multiple topics. Generating a single embedding for the entire text can dilute important sections. Chunking divides a document into smaller segments and generates an embedding for each segment.

Example:

~~~text
Long document
   |
   +--> Chunk 1: overview
   |
   +--> Chunk 2: installation
   |
   +--> Chunk 3: troubleshooting
   |
   +--> Chunk 4: examples
~~~

A vector document might look like:

~~~json
{
  "documentId": "guide-42",
  "chunkId": "guide-42-03",
  "chunkIndex": 3,
  "title": "Troubleshooting",
  "content": "When the client cannot connect...",
  "embedding": [0.12, -0.08, 0.31, 0.44]
}
~~~

When returning results, the application can group chunks by document ID, pick the best chunk, or use a reranker. Store chunk index and metadata to display accurate excerpts and link back to the source.

### 12.1. Choosing Chunk Size

Chunks that are too small lose context; chunks that are too large can exceed token limits or mix multiple topics. Choose based on the model's token limit, document structure, user query patterns, overlap between chunks, and retrieval quality on real queries.

Do not assume a fixed character count equals the same token count across all languages. Tokenization depends on the model and language. Prefer splitting by headings/paragraphs first and then applying token limits to preserve content structure.

### 12.2. Overlap

Overlap repeats part of the end of the previous chunk at the start of the next chunk to reduce context loss at boundaries. Too much overlap creates near-duplicate copies, inflates index size, and causes redundant search results.

Evaluate overlap using retrieval metrics and check for duplicate results. You can collapse results by document ID or use reranking to select diverse chunks.

## 13. Managing Model Versions and Changing Dimensions

Suppose the current index uses model A with 768 dimensions. Later, the team switches to model B with 1024 dimensions. You cannot simply edit the `dims` annotation and write new vectors into the old index:

- The old mapping still declares 768 dimensions.
- Old documents contain 768-dimensional vectors.
- New query vectors have 1024 dimensions.
- Vectors from models A and B do not share the same embedding space, even if their dimensions matched.

A safe strategy is usually creating a new index version:

~~~text
products-vector-v1
  model A
  dims = 768
        |
        v
Build products-vector-v2
  model B
  dims = 1024
        |
        v
Backfill all documents
        |
        v
Validate retrieval quality
        |
        v
Switch semantic-search alias
~~~

### 13.1. Attaching Versions to Vectors

Track at least model identifier and revision, dimensions, preprocessing/chunking version, similarity function, index mapping version, and creation timestamp or source version.

These metadata fields can live in documents, index settings/alias conventions, or an application registry. Do not rely solely on index names if you need to audit which model produced a vector.

### 13.2. Do Not Mix Vectors from Different Models

Two models returning 768 dimensions does not mean their vectors are comparable. Each model learns its own representation space. kNN between model A vectors and a model B query vector will return a numeric ranking, but that ranking has no semantic guarantee.

Keep each embedding space in its own index/field. If running a gradual migration, maintain two indexes and route queries to the index matching the model.

### 13.3. Re-embedding

When changing models or preprocessing, you need to regenerate embeddings for existing data. Workflow:

1. Lock down the new model/version and dimensions.
2. Create a new index with the corresponding mapping.
3. Backfill source content in batches.
4. Call the embedding service and validate vectors.
5. Bulk index, save checkpoints, and handle item failures.
6. Replay changes that occurred during backfill.
7. Evaluate retrieval quality and latency.
8. Switch the alias/query routing.
9. Keep the old index for a rollback window.

Do not compute new embeddings and gradually overwrite the old index while queries still generate vectors using the old model. During migration, documents and queries must follow the same model version.

## 14. Testing Dimensions and Mappings

Have unit tests for the embedding contract:

~~~java
@Test
void rejectsEmbeddingWithWrongDimensions() {
    float[] vector = {0.1f, 0.2f, 0.3f};

    assertThatThrownBy(
            () -> validateEmbedding(vector, 4)
    ).isInstanceOf(IllegalArgumentException.class);
}
~~~

Integration tests against real Elasticsearch should confirm:

- The index is created with `dense_vector` and expected `dims`.
- Documents with valid dimensions are indexed successfully.
- Documents with wrong dimensions are rejected.
- Query vectors with wrong dimensions are rejected.
- Similarity/index options match the mapping.
- kNN returns expected results on a small fixture.

You can inspect the mapping:

~~~http
GET /products-semantic-v1/_mapping
~~~

Verify the `embedding` field has type `dense_vector`, accurate `dims`, and similarity/index options as designed. Do not rely only on Java annotations because an existing index may retain an old mapping.

### 14.1. Testing Vector Content

You do not necessarily assert the entire embedding vector against a fixed array of numbers if the model service can update or output is not strictly deterministic. Instead:

- Test dimensions and finite values.
- Test model ID/version.
- Test contracts with fixtures or a mocked embedding service in unit tests.
- Use integration/acceptance tests to evaluate ranking on a known query/document set.

If strictly reproducible tests are needed, use a pinned model snapshot and versioned fixture vectors.

## 15. Evaluating Semantic Retrieval Quality

A query returning 10 results does not prove search is good. You need an evaluation dataset containing queries and labeled relevant documents.

Common metrics:

| Metric | Question |
|---|---|
| Recall@k | Out of all relevant documents, how many did the system find in the top k? |
| Precision@k | How many of the top-k results are actually relevant? |
| MRR | At what position does the first relevant result appear? |
| NDCG@k | Does the ranking prioritize more relevant documents, including graded relevance? |
| p95 latency | How long does it take for 95% of queries to complete? |

Evaluate across diverse queries: natural-language questions, synonyms, typos, proper names, product codes, Vietnamese with/without diacritics, and filtered queries.

If using hybrid search, compare BM25 baseline, vector kNN, hybrid/RRF, and hybrid with reranking (if used).

Do not choose a model just for a nice demo. A good model must improve metrics on domain data while meeting latency/cost constraints.

## 16. Operating the Embedding Pipeline

The embedding service is an external dependency or a separate ML workload. You must handle timeouts and bounded retries, rate limits and quotas, batch sizes, queues/backpressure, caching by content hash and model version, dead-lettering for documents that fail embedding, monitoring pending/failed embedding counts, and protecting sensitive data before sending it to a model.

Do not call the embedding API inside a long database transaction. Record an event/outbox entry and let a worker generate embeddings and update the search projection. If users must see results immediately, design states such as `EMBEDDING_PENDING` and update the search document once the vector is ready.

### 16.1. Avoiding Re-embedding When Content Is Unchanged

Compute a hash from normalized content and pipeline metadata:

~~~text
content hash
  + model version
  + preprocessing version
  + chunking version
        |
        v
embedding cache key
~~~

If none of these components change, existing embeddings can be reused. When the model or preprocessing changes, the cache key changes so stale-version vectors are never returned.

### 16.2. Protecting Data

Text sent to an embedding provider may contain personal data, internal information, or trade secrets. Determine which data is allowed to be sent, whether redaction is required, provider retention policies, and access controls on the vector index.

Embeddings should not be assumed harmless merely because they cannot be read directly as text. They remain derived representations of source content and must be protected under the application's data policies.

## 17. Common Pitfalls

| Symptom | Possible cause | Resolution |
|---|---|---|
| Indexing document fails with vector dimension mismatch | Vector does not match mapping `dims` | Check model output and index schema |
| kNN query fails with wrong dimensions | Query embedding differs from `dims` | Use matching model/index version |
| Matching dimensions yet poor results | Documents and queries use different models | Unify the embedding space |
| Search results shift after model upgrade | Embedding space or preprocessing changed | Re-embed and evaluate ranking |
| kNN slows down as data grows | Candidate count, graph, filters, or resources | Benchmark ANN, shards, and index options |
| Exact script scoring too slow | Computing similarity over too many documents | Narrow candidates or use ANN |
| Missing details in long documents | Single vector for entire document loses granularity | Chunk documents and store chunk metadata |
| Multiple duplicate hits from one document | Adjacent chunks top the ranking | Collapse/group or rerank |
| Scores cannot be compared across models | Different scales and similarity functions | Evaluate using ranking metrics |
| Model service overloaded | Synchronous embedding calls without batching/backpressure | Queue, batch, rate-limit, and retry |

## 18. Semantic Search Implementation Workflow

1. Define the use case and evaluation query/document set.
2. Select an embedding model suited to the language and domain.
3. Lock down model revision, preprocessing, chunking, and dimensions.
4. Choose `similarity` according to model guidance.
5. Create an index with an explicit `dense_vector` mapping.
6. Create a dedicated search document class in Spring Data Elasticsearch.
7. Generate embeddings via a service abstraction and validate vectors.
8. Index documents along with model/version metadata.
9. Generate query embeddings from the same embedding space.
10. Execute kNN and apply security/tenant filters.
11. Evaluate Recall@k, NDCG/MRR, and latency.
12. Consider hybrid search when lexical matching remains important.
13. Monitor the embedding pipeline, index health, and retrieval quality.
14. When changing models/dimensions, create a new index version, re-embed, and swap aliases.

## 19. Conclusion

Embeddings represent content as numeric vectors for semantic proximity search. Elasticsearch stores these vectors in `dense_vector` fields and supports kNN, while search quality and validity depend on the chosen embedding model, preprocessing, dimensions, and similarity function.

Dimensions are part of the schema: document and query vectors must share the same dimension count and belong to the same embedding space. Two models with identical dimensions can still be incompatible. Therefore, store model/version metadata, validate vectors before indexing, and never mix vectors from different models within the same search space.

In Spring Data Elasticsearch, define a dedicated search document with a dense vector field, manage versioned mappings, and use repositories/`ElasticsearchOperations` or the Java Client appropriate for your release train to write and query. Evaluate ANN using recall and latency on real data, combine with BM25 when exact term matching matters, and apply chunking for long documents. When changing models or dimensions, build a new index, re-embed data, validate quality, and switch aliases to keep document and query vectors consistent.
