# Executing Queries via `NativeQuery` or Client Based on Version Support

Semantic search uses vector embeddings to find documents whose content is close in meaning to a query. Instead of matching only keywords, the application converts text into numeric vectors and finds the nearest vectors in Elasticsearch.

In Spring Data Elasticsearch, the standard way to send advanced queries is **`NativeQuery`**. `NativeQuery` uses the query builders from the Elasticsearch Java API Client, allowing you to express kNN, `bool` queries, filters, aggregations, and many other Query DSL features. When a Spring Data version or builder does not yet expose a newer server feature, the application can call the configured Elasticsearch Java API Client directly.

One critical detail is that APIs change across releases. Starting in Spring Data Elasticsearch 5.4, **`NativeQueryBuilder.withKnnQuery`** was replaced by **`withKnnSearches`** for top-level kNN search. **`KnnSearch`** and **`KnnQuery`** are two distinct types in the Elasticsearch Java API Client. Copying code from another version without verifying dependencies can lead to compile errors or requests with unexpected semantics.

This lesson explains how to prepare vectors, map `dense_vector`, build `NativeQuery` for kNN and hybrid search, invoke the client directly when needed, choose APIs by version, read `SearchHits`, and handle common pitfalls.

## 1. Semantic Search Flow

### 1.1. What Is an Embedding?

An embedding is a numeric vector representing content. An embedding model accepts text and produces a fixed-dimension sequence of numbers.

~~~text
"wireless keyboard"
    -> embedding model
    -> [0.12, -0.08, 0.31, ..., 0.04]
~~~

Two phrases with similar meanings typically produce vectors that are close under the metric used by the model and search engine. A vector is not a human-readable summary; it is a numeric representation for arithmetic comparison.

### 1.2. Two Embedding Steps

A semantic search pipeline typically has two branches:

1. **Indexing time**: generate embeddings for document content and store the vectors in Elasticsearch.
2. **Query time**: generate an embedding for the user's question using the same model and find the nearest vectors.

~~~mermaid
flowchart TD
    A[Source document] --> B[Text preprocessing]
    B --> C[Embedding model]
    C --> D[Document vector]
    D --> E[(Elasticsearch dense_vector)]
    F[User query] --> G[Same embedding model]
    G --> H[Query vector]
    H --> I[kNN NativeQuery]
    E --> I
    I --> J[Ranked SearchHits]
~~~

If document vectors are produced by model A while query vectors are produced by model B, matching dimensions alone do not guarantee both vectors share the same semantic space.

### 1.3. Responsibilities of Spring Data and the Embedding Model

Spring Data Elasticsearch handles sending queries, mapping documents, and reading results. Embedding generation may be handled by:

- A dedicated embedding service.
- An internally hosted model.
- A managed inference service.
- An Elasticsearch inference endpoint or semantic field workflow if supported by the version and configuration.

Do not assume `NativeQuery` automatically generates embeddings from a question. With standard `dense_vector` fields, the application must pass a precomputed `queryVector`. If using server-side inference or a query vector builder, the request must specify the model and structure supported by your Elasticsearch version.

### 1.4. Use the Same Model on Both Sides

Store model metadata alongside the document or in projection metadata:

~~~json
{
  "id": "DOC-1001",
  "embeddingModel": "catalog-embedding-v3",
  "embeddingVersion": 3,
  "embedding": [0.12, -0.08, 0.31, 0.04]
}
~~~

This metadata identifies which model produced the vector. In practice, duplicating the model ID in every document is unnecessary if an index contains only one model version, though you still need a way to track model versions during re-embedding or migrations.

### 1.5. Normalize Content Before Embedding

Document text and query text should follow compatible preprocessing:

- Decide which fields are embedded: `title`, `description`, `body`, or combined text.
- Strip markup or boilerplate with no search value.
- Preserve essential context such as product names, codes, language, and units.
- Stay within the model's input token limit.
- Avoid running two divergent preprocessing pipelines unless intentional.

If document embeddings are built from `title` + `description` while query embeddings use a different format, evaluate retrieval quality using real data.

## 2. Choosing a Vector Search Approach

### 2.1. Approximate kNN

Approximate k-nearest neighbors (kNN) uses a vector index structure such as HNSW to locate nearest vectors without scoring every document.

Advantages:

- Lower latency on large datasets.
- Well-suited for top-k retrieval at production scale.
- Can combine filters to narrow candidate sets.

In return, results are approximate. Some true nearest neighbors might not be visited among the explored candidates.

### 2.2. Exact Vector Scoring with `script_score`

Exact search computes similarity over every document matching a query/filter using `script_score`.

Advantages:

- Exact scoring over the filtered document set.
- Helpful when candidate sets are small.
- Easy to combine with a business condition as a pre-filter.

Disadvantages:

- Cost grows linearly with the number of scored documents.
- Unsuitable for brute-forcing large indexes.
- Scripts must be carefully designed and bounded.

### 2.3. Comparison

| Criterion | Approximate kNN | Exact `script_score` |
|---|---|---|
| Computation | Searches via vector index | Scores each document in the filtered set |
| Accuracy | Approximate | Exact over the scored set |
| Scalability | Suited to large datasets | Suited to small or narrowly filtered sets |
| Main parameters | `k`, `num_candidates` | Query filter and vector scoring script |
| Use case | General semantic retrieval | Small subset needing exact scoring |

Do not pick exact just because "exact" sounds better. If a filter still matches millions of documents, `script_score` can impose heavy load.

### 2.4. kNN Query and kNN Search Are Two Different Request Placements

Elasticsearch offers two key places for kNN:

- Top-level `knn` in a search request, typically represented by `KnnSearch`.
- Query DSL `knn` inside `query`, represented by `KnnQuery`.

They carry different parameters and composition rules. In a search request, top-level `knn` can combine with a lexical `query`. Inside Query DSL, `KnnQuery` can be placed within `bool`/query composition according to server-supported semantics.

## 3. Preparing `dense_vector` Mappings

### 3.1. Declaring a Vector Field

A vector field requires dimensions matching the embedding model. For example, if a model outputs 768 dimensions:

~~~json
{
  "mappings": {
    "properties": {
      "title": {
        "type": "text"
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

`dims` must match the element count of every indexed and queried vector. For approximate kNN, the vector field must have suitable indexing enabled; check the mapping and defaults for your running Elasticsearch version rather than guessing.

### 3.2. Mapping with Spring Data Elasticsearch

Spring Data provides `FieldType.Dense_Vector` and the `dims` attribute:

~~~java
@Document(indexName = "articles-v1")
public class ArticleDocument {

    @Id
    private String id;

    @Field(type = FieldType.Text)
    private String title;

    @Field(type = FieldType.Text)
    private String content;

    @Field(type = FieldType.Dense_Vector, dims = 768)
    private float[] embedding;
}
~~~

This example assumes a 768-dimensional model. You can use `float[]`, `List<Float>`, or a type compatible with your project's converter/client. Verify which Java types are supported by your Spring Data version and serializer.

### 3.3. `Dense_Vector` Attributes Across Versions

Spring Data Elasticsearch added vector mapping support over several releases:

- `dims` on `FieldType.Dense_Vector` has been available since Spring Data Elasticsearch 4.2.
- `elementType`, `knnSimilarity`, and `knnIndexOptions` arrived in 5.4.
- Enum names and mapping serialization must match the running Spring Data/Elasticsearch version.

If you want to configure similarity or index options via annotations, check the API docs for your exact release. Do not copy attributes introduced in 5.4 into a 5.3 or older project.

### 3.4. Choosing Similarity

Common metrics include:

- `cosine`: compares the angle between vectors.
- `dot_product`: inner product; semantics and requirements depend on element type and vector normalization.
- `l2_norm`: based on Euclidean distance.
- `max_inner_product`: suitable for certain embeddings and scoring setups.

The metric must fit how the model creates vectors. Do not change similarity just to boost scores. Changing metrics or models requires re-evaluating retrieval and usually reindexing/re-embedding.

### 3.5. Validating Vectors Before Indexing

Before saving:

- Ensure the vector is non-null.
- Ensure dimensions are exact.
- Ensure all values are finite numbers, not `NaN` or `Infinity`.
- Apply normalization if required by the model/metric.
- Store model/version metadata.
- Do not mix vectors from incompatible models into the same field.

You can validate in an application service:

~~~java
private void validateEmbedding(float[] vector, int expectedDimensions) {
    if (vector == null || vector.length != expectedDimensions) {
        throw new IllegalArgumentException("Unexpected embedding dimensions");
    }

    for (float value : vector) {
        if (!Float.isFinite(value)) {
            throw new IllegalArgumentException("Embedding contains a non-finite value");
        }
    }
}
~~~

Application-side validation catches errors early; Elasticsearch still validates mappings and payloads upon receiving requests.

### 3.6. Indexing Documents with Vectors

Example with Spring Data:

~~~java
ArticleDocument document = new ArticleDocument();
document.setId("A-1001");
document.setTitle("Designing resilient services");
document.setContent("...");
document.setEmbedding(embeddingModel.embed(document.getContent()));

articleRepository.save(document);
~~~

`embeddingModel` is an application abstraction, not a built-in Spring Data Elasticsearch class. You can invoke the embedding provider before saving or build a separate indexing pipeline for independent retries and batching.

## 4. What Is `NativeQuery`?

### 4.1. Role of `NativeQuery`

Spring Data Elasticsearch offers several query abstractions:

- `CriteriaQuery`: builds queries via a simple criteria API.
- `StringQuery`: sends Query DSL as a raw JSON string.
- `NativeQuery`: uses query builders from the Elasticsearch Java API Client.

`NativeQuery` fits complex queries or features not conveniently expressed via the Criteria API, such as kNN, aggregations, nested queries, scripts, highlighting, and advanced Query DSL constructs.

### 4.2. Importing `NativeQuery` from the Right Package

With the Elasticsearch Java API Client integration (ELC), `NativeQuery` lives in:

~~~java
import org.springframework.data.elasticsearch.client.elc.NativeQuery;
~~~

Do not confuse it with legacy query classes from earlier client generations. Check your dependency tree and IDE imports to make sure the class comes from the Spring Data Elasticsearch release your project uses.

### 4.3. Regular Query Example

~~~java
NativeQuery query = NativeQuery.builder()
    .withQuery(q -> q
        .match(m -> m
            .field("title")
            .query("resilient services")
        )
    )
    .withPageable(PageRequest.of(0, 10))
    .build();

SearchHits<ArticleDocument> hits =
    operations.search(query, ArticleDocument.class);
~~~

The builder uses Elasticsearch Java API Client lambdas. This is one of the key differences from the old `RestHighLevelClient` query builders.

### 4.4. `NativeQuery` Is Not Raw HTTP

`NativeQuery` builds requests via the Java API Client. The application does not manually assemble URLs or JSON strings for every query.

Benefits:

- Compile-time API for many query constructs.
- Type-safe builders.
- Integration with Spring Data mapping.
- Results mapped into `SearchHits<T>`.
- Ability to add `Pageable`, sorting, filters, aggregations, and source filtering.

If a newer Elasticsearch API is not yet exposed by `NativeQueryBuilder`, you can call the Java API Client directly.

## 5. Executing kNN with `NativeQuery`

### 5.1. Example with Spring Data Elasticsearch 5.4 and Later

Starting in 5.4, the builder provides `withKnnSearches` to declare top-level kNN searches:

~~~java
import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.elasticsearch.core.SearchHits;

List<Float> queryVector = embeddingService.embed(queryText);

NativeQuery query = NativeQuery.builder()
    .withKnnSearches(knn -> knn
        .field("embedding")
        .queryVector(queryVector)
        .k(10)
        .numCandidates(100)
    )
    .withPageable(PageRequest.of(0, 10))
    .build();

SearchHits<ArticleDocument> hits =
    operations.search(query, ArticleDocument.class);
~~~

Example parameters:

- `field`: name of the `dense_vector` field in the mapping.
- `queryVector`: vector of the query.
- `k`: number of nearest neighbors to retrieve.
- `numCandidates`: number of candidates examined per shard before merging results.

The query vector must share the same dimensions and embedding space as the indexed vectors.

### 5.2. Adding Filters to kNN

Example restricting search to an authorized tenant and published status:

~~~java
NativeQuery query = NativeQuery.builder()
    .withKnnSearches(knn -> knn
        .field("embedding")
        .queryVector(queryVector)
        .k(10)
        .numCandidates(100)
        .filter(filter -> filter
            .bool(bool -> bool
                .filter(f -> f
                    .term(term -> term
                        .field("tenantId")
                        .value(tenantId)
                    )
                )
                .filter(f -> f
                    .term(term -> term
                        .field("published")
                        .value(true)
                    )
                )
            )
        )
    )
    .withPageable(PageRequest.of(0, 10))
    .build();
~~~

Filters inside kNN search have pre-filter semantics: Elasticsearch finds top `k` within documents matching the filter. This matters when tenant or status must be enforced prior to selecting nearest neighbors.

Tenant criteria must still come from the authenticated principal. Never trust an arbitrary client-supplied `tenantId` as an authorization mechanism.

### 5.3. Choosing `k` and `num_candidates`

- `k` is the desired number of vector results.
- `num_candidates` is the number of candidates evaluated per shard.
- `num_candidates` must be sufficiently large relative to `k` and respects server version limits.
- Increasing `num_candidates` typically improves recall while increasing CPU/latency.

Start with moderate values and measure recall and latency on real data. Do not default to huge `num_candidates`.

### 5.4. Reading Scores with `SearchHits`

Spring Data returns `SearchHits<T>`:

~~~java
for (SearchHit<ArticleDocument> hit : hits) {
    ArticleDocument article = hit.getContent();
    float score = hit.getScore();

    log.debug("articleId={}, score={}", article.getId(), score);
}
~~~

`score` represents relevance under the query's scoring mechanism. Do not treat `score` as a probability or similarity percentage without a dedicated calibration step.

### 5.5. Reading Results in `ReactiveElasticsearchOperations`

The same `Query` can be passed to reactive operations:

~~~java
Mono<ReactiveSearchHits<ArticleDocument>> result =
    reactiveOperations.search(query, ArticleDocument.class);
~~~

`ReactiveSearchHits` provides search metadata and streams `SearchHit<T>` according to the version's API. Process results in a reactive pipeline; never call `block()` on an application event loop.

## 6. `NativeQueryBuilder` Differences Before and After Spring Data 5.4

### 6.1. Builder Name and Type Changes

An important breaking change:

| Spring Data Elasticsearch | Top-level kNN API in `NativeQueryBuilder` |
|---|---|
| 4.4 to 5.3 | Had version-specific `withKnnQuery` API |
| 5.4 and later | `withKnnSearches` |

From 5.4 onward, Spring Data replaced `withKnnQuery` with `withKnnSearches` for top-level kNN searches. This is not just a method rename; the Elasticsearch Java API Client has two separate classes:

- `KnnSearch`: top-level `knn` in a search request.
- `KnnQuery`: `knn` query nested inside Query DSL.

### 6.2. When You Need `KnnQuery` Inside Query DSL in 5.4+

Construct the query with the Elasticsearch Java API Client and pass it to `withQuery`:

~~~java
import co.elastic.clients.elasticsearch._types.query_dsl.Query;

Query knnQuery = Query.of(q -> q
    .knn(knn -> knn
        .field("embedding")
        .queryVector(queryVector)
        .k(10)
        .numCandidates(100)
    )
);

NativeQuery query = NativeQuery.builder()
    .withQuery(knnQuery)
    .withPageable(PageRequest.of(0, 10))
    .build();
~~~

This uses Query DSL `knn`, not top-level `KnnSearch`. Use this approach when embedding kNN inside a Query DSL structure supported by your server version.

### 6.3. Do Not Blindly Swap `KnnSearch` for `KnnQuery`

Both classes share similar field names, yet sit in different places within a search request. Decide based on semantics:

- Need top-level vector retrieval combined with a lexical query on the search request: consider `withKnnSearches`.
- Need kNN nested inside `bool`/query composition: create a `KnnQuery` via `withQuery`.
- Need a newer API not yet supported by the builder: call the Elasticsearch Java API Client directly.

### 6.4. Projects on 5.3 or Earlier

If your dependency is 5.3 or older, do not copy 5.4+ code expecting it to compile. Check the Javadoc and migration guide for your exact version to see available builder methods.

If you need an unexposed feature, you can use the Java API Client compatible with your release train, but do not arbitrarily override the client dependency. It is better to upgrade Spring Data via supported dependency management when a feature requires newer APIs.

### 6.5. Projects Before Spring Data Elasticsearch 4.4

Older examples may use `NativeSearchQuery`, `NativeSearchQueryBuilder`, and `RestHighLevelClient`. That is an older API generation.

Do not mix:

- `NativeSearchQuery` with `NativeQuery`.
- `RestHighLevelClient` builders with Elasticsearch Java API Client builders.
- Arbitrary client dependency versions with Spring Data dependency management.

When upgrading from legacy APIs, read each release's migration guide and check the compatibility matrix between Spring Data and Elasticsearch server.

## 7. Hybrid Search: Combining Keywords and Vectors

### 7.1. Why Hybrid Search?

Vector retrieval finds semantically similar content, yet may miss important exact-match signals:

- SKUs or product codes.
- Proper names.
- Model numbers.
- Mandatory keywords.
- Exact phrases in titles.

BM25/full-text search handles lexical matching well, while vector search handles semantic similarity. Combining both sources improves retrieval quality.

### 7.2. Combining a Lexical Query and Top-Level kNN

Example with Spring Data 5.4+:

~~~java
NativeQuery query = NativeQuery.builder()
    .withQuery(q -> q
        .match(m -> m
            .field("content")
            .query(queryText)
            .boost(1.0f)
        )
    )
    .withKnnSearches(knn -> knn
        .field("embedding")
        .queryVector(queryVector)
        .k(50)
        .numCandidates(200)
        .boost(1.0f)
        .filter(f -> f
            .term(t -> t
                .field("published")
                .value(true)
            )
        )
    )
    .withPageable(PageRequest.of(0, 10))
    .build();
~~~

The search request combines lexical and vector results under top-level kNN semantics. Elasticsearch can merge scores from these branches. `boost` adjusts weights, though it does not automatically place two different scoring scales onto the same footing.

### 7.3. Why Direct Score Addition Can Be Unstable

BM25 scores and vector similarity follow different distributions. Simply summing scores with arbitrary boosts can cause:

- One branch to dominate the other.
- Results to shift drastically depending on the corpus.
- Embedding model tweaks to skew rankings.
- Exact-match queries to be pushed down by vector hits.

Evaluate rankings on a labeled query set or relevance judgments instead of guessing boost values.

### 7.4. Reciprocal Rank Fusion (RRF)

RRF combines rankings across multiple retrievers instead of directly adding raw scores. It helps balance lexical and vector hits when the two scores sit on incompatible scales.

Elasticsearch supports `retriever` APIs and RRF depending on server/client version. If your project's Spring Data `NativeQueryBuilder` does not yet expose the required retriever structure, invoke the Elasticsearch Java API Client directly using the request model supported by your client version.

Do not assume a retriever API exists in every Elasticsearch 8.x or Spring Data release. Check your server version and generated Java client before implementing.

### 7.5. Hybrid Queries Do Not Generate Embeddings Automatically

The hybrid example above still requires a precomputed `queryVector`. The lexical branch takes `queryText`, while the vector branch takes an embedding from the same model used at index time.

Keep both inputs tied to the same request context so lexical search never runs on query A while vector search runs on query B.

## 8. Using `script_score` for Exact Semantic Scoring

### 8.1. Restricting the Document Set Before Computing Vector Scores

Query DSL example:

~~~json
{
  "query": {
    "script_score": {
      "query": {
        "bool": {
          "filter": [
            { "term": { "tenantId": "tenant-1" } },
            { "term": { "published": true } }
          ]
        }
      },
      "script": {
        "source": "cosineSimilarity(params.query_vector, 'embedding') + 1.0",
        "params": {
          "query_vector": [0.12, -0.08, 0.31, 0.04]
        }
      }
    }
  }
}
~~~

This is an abbreviated example; actual vectors must match mapping dimensions. The filter query narrows the document set before the script computes similarity.

### 8.2. Using `NativeQuery` with `script_score`

You can build the query using the Elasticsearch Java API Client:

~~~java
NativeQuery query = NativeQuery.builder()
    .withQuery(q -> q
        .scriptScore(ss -> ss
            .query(inner -> inner
                .bool(b -> b
                    .filter(f -> f
                        .term(t -> t
                            .field("tenantId")
                            .value(tenantId)
                        )
                    )
                )
            )
            .script(script -> script
                .source(
                    "cosineSimilarity(params.query_vector, 'embedding') + 1.0"
                )
                .params("query_vector", JsonData.of(queryVector))
            )
        )
    )
    .withPageable(PageRequest.of(0, 10))
    .build();
~~~

Builder method names and `JsonData` usage must match your project's Elasticsearch Java API Client version. If a builder lacks a specific script option, construct the `Query` directly from the client model and pass it into `NativeQuery`.

### 8.3. Do Not Use `script_score` Across Large Indexes

`script_score` scores every document matched by the inner query. If the inner query matches too broadly, CPU cost can be high.

Use it when:

- Filters narrow the dataset significantly.
- Exact scoring is required.
- The corpus is small.
- Evaluating quality or reranking a candidate set.

For large datasets, approximate kNN is typically the better choice.

## 9. Calling the Elasticsearch Java API Client Directly

### 9.1. When Is Direct Client Access Needed?

Call the client directly when:

- The Spring Data builder does not yet expose a newer request option.
- Newer retriever APIs or search features are needed.
- Response metadata unavailable through the abstraction is required.
- Specialized Elasticsearch APIs are needed.
- Exact control over a specific integration's request/response is desired.

If you only need `bool`, `match`, `filter`, kNN, or aggregations supported by `NativeQuery`, keeping queries in Spring Data is usually simpler.

### 9.2. Injecting the Configured Client

Example service receiving `ElasticsearchClient` from Spring:

~~~java
import co.elastic.clients.elasticsearch.ElasticsearchClient;

@Service
public class SemanticSearchClient {

    private final ElasticsearchClient client;

    public SemanticSearchClient(ElasticsearchClient client) {
        this.client = client;
    }
}
~~~

The bean must share the same endpoint, TLS, and credential configuration used by the rest of the application. Do not create a second client with separate endpoints or authentication just to run one query.

Bean names and auto-configuration depend on your Spring Boot/Spring Data release; inject by type or configure the bean explicitly in your project.

### 9.3. Executing Top-Level kNN Directly

~~~java
SearchResponse<ArticleDocument> response =
    client.search(search -> search
        .index("articles-v1")
        .knn(knn -> knn
            .field("embedding")
            .queryVector(queryVector)
            .k(10)
            .numCandidates(100)
        )
        .size(10),
        ArticleDocument.class
    );
~~~

This uses the Java API Client style. Generated methods and vector types can vary across Elasticsearch client major versions. Check the API docs for the exact `co.elastic.clients:elasticsearch-java` in your dependency tree.

### 9.4. Direct Client Calls Differ from Spring Data Mapping

When using `ElasticsearchOperations.search`, Spring Data applies domain type mapping metadata and its conversion service.

When calling `ElasticsearchClient.search` directly, the client uses the transport's `JsonpMapper`/serializer to deserialize responses. Do not assume all Spring Data annotations or custom converters apply identically.

If your entity relies on Spring Data custom conversions, field name mappings, or type conversions, consider:

- Using `NativeQuery` through `ElasticsearchOperations`.
- Defining a dedicated response DTO for the low-level client.
- Converting responses with an explicit mapper.
- Inspecting JSON source/field names.

### 9.5. Avoid Legacy Clients in New Code

`RestHighLevelClient` is a legacy client generation. Modern Spring Data Elasticsearch uses the Elasticsearch Java API Client in its ELC integration. Legacy projects may still use the older client depending on version, but avoid mixing old and new APIs in the same codebase without explicitly documenting dependencies.

## 10. Selecting Query Approaches by Version

### 10.1. Start from Actual Resolved Dependencies

Inspect the Spring Data Elasticsearch and Elasticsearch Java API Client versions actually resolved by your build. Do not rely solely on numbers written in `build.gradle` if a Spring Boot BOM or dependency constraint manages versions transitively.

Maven:

~~~bash
mvn dependency:tree -Dincludes=org.springframework.data:spring-data-elasticsearch,co.elastic.clients:elasticsearch-java
~~~

Gradle:

~~~bash
./gradlew dependencyInsight --dependency spring-data-elasticsearch --configuration runtimeClasspath
./gradlew dependencyInsight --dependency elasticsearch-java --configuration runtimeClasspath
~~~

### 10.2. The Compatibility Matrix Is Authoritative

Spring Data publishes a version table per release train listing compatible Spring Data Elasticsearch and Elasticsearch server versions.

Examples of recent release trains in the compatibility table:

| Spring Data release train | Spring Data Elasticsearch | Referenced Elasticsearch |
|---|---:|---:|
| 2026.0 | 6.1.x | 9.4.7 |
| 2025.1 | 6.0.x | 9.2.2 |
| 2025.0 | 5.5.x | 8.18.1 |
| 2024.1 | 5.4.x | 8.15.5 |
| 2024.0 | 5.3.x | 8.13.4 |
| 2023.1 | 5.2.x | 8.11.1 |

These figures reflect reference points in the compatibility table at the time of writing; they are not an instruction to upgrade every application to the latest release. Always check the current matrix and the release train used by your project's Spring Boot version.

### 10.3. API Selection Guide

| Spring Data Elasticsearch version | Recommended approach |
|---|---|
| Before 4.4 | May encounter legacy `NativeSearchQuery`/`RestHighLevelClient` APIs; consult migration guides |
| 4.4 to 5.3 | `NativeQuery` uses Elasticsearch Java API Client; check kNN APIs for your exact minor release |
| 5.4 and later | `withKnnSearches` for top-level kNN; `KnnQuery` can be constructed in Query DSL |
| 6.x | Use the Java API Client version managed by the release train; check corresponding 9.x server APIs |

Do not treat this table as a replacement for the official compatibility matrix. It is strictly a high-level API guide.

### 10.4. Upgrading from 5.3 to 5.4

The migration guide specifies that `withKnnQuery` in `NativeQueryBuilder` was replaced by `withKnnSearches` for kNN search, while distinguishing top-level `KnnSearch` from Query DSL `KnnQuery`.

When upgrading:

1. Update Spring Data via a compatible release train.
2. Check the resolved Java API Client version.
3. Update imports and builder methods.
4. Determine whether queries require top-level kNN or Query DSL kNN.
5. Run integration tests against a supported server version.
6. Re-evaluate filters and ranking semantics.

### 10.5. Do Not Arbitrarily Override the Elasticsearch Java API Client

Spring Data depends on classes generated from a specific client version. Manually bumping only the client version can trigger:

- `NoSuchMethodError`.
- `ClassNotFoundException`.
- Serialization/deserialization errors.
- Request models mismatched with the server.
- Missing builder methods shown in sample code.

Let the Spring Boot BOM / Spring Data dependency management select the client version. Only override when backed by compatibility evidence and thorough tests.

## 11. Semantic Fields and Elasticsearch-Managed Inference

### 11.1. `dense_vector` with Self-Managed Embeddings

With standard `dense_vector`:

1. The application generates document embeddings.
2. Stores vectors in the field.
3. The application generates query embeddings.
4. Sends `query_vector` in kNN requests.

This is the bring-your-own-vectors model. The application controls the model, preprocessing, and versioning.

### 11.2. `semantic_text` and Inference Workflows

Certain Elasticsearch versions support `semantic_text` and inference integration to generate or consume embeddings inside Elasticsearch. With this field type, requests can pass text input and query vector builders configured around a model/inference setup.

Key considerations:

- Feature availability depends on Elasticsearch server version and inference setup.
- Models/deployments must be ready.
- Documents and queries must share consistent model semantics.
- Do not assume `semantic_text` accepts every top-level kNN parameter identical to `dense_vector`.

### 11.3. Top-Level `knn` and `semantic_text`

Current Elasticsearch documentation distinguishes:

- The top-level `knn` search option supports indexed `dense_vector` fields.
- For `semantic` or `semantic_text` fields, use a `knn` query inside Query DSL according to server version guidelines.
- `match` queries on `semantic_text` can be used in certain workflows so the server runs appropriate inference.

Therefore, when using `semantic_text`, do not copy top-level `withKnnSearches` examples meant for `dense_vector` and expect them to work automatically. Choose the query form supported by the server.

### 11.4. Query Vector Builder

A request can use `query_vector_builder` instead of passing a precomputed vector:

~~~json
{
  "query": {
    "knn": {
      "field": "semantic_field",
      "k": 10,
      "num_candidates": 100,
      "query_vector_builder": {
        "text_embedding": {
          "model_id": "my-embedding-model",
          "model_text": "How do I design resilient services?"
        }
      }
    }
  }
}
~~~

This is an Elasticsearch Query DSL example. With `semantic_text`, the model ID may be inferred from the mapping depending on configuration; with `dense_vector` or other models, you may need to specify the model explicitly. Verify against your exact API version before deploying.

## 12. Filters and Security in Semantic Search

### 12.1. Filter Before Selecting Nearest Neighbors

If users may only search within one tenant, filters must reside inside the kNN request with supported pre-filter semantics.

Do not fetch the top 10 vectors across the whole index and filter by tenant in Java afterward. That approach can:

- Drop valid tenant results when global top-10 entries belong to other tenants.
- Waste resources unnecessarily.
- Risk metadata leakage if intermediate results are logged or mishandled.

### 12.2. Filtering by Business Status

You can filter by:

- `published = true`.
- `language`.
- `documentType`.
- `tenantId`.
- `accessLevel`.
- `validFrom`/`validTo`.
- `deleted = false`.

Filters must target fields with proper mappings, typically `keyword`, `boolean`, or `date`.

### 12.3. Do Not Confuse Relevance with Authorization

Semantic score only ranks relevance. It never determines whether a user is authorized to read a document.

Authorization must be enforced in the service/security layer, and appropriate filters must be included in the Elasticsearch request. When stronger isolation is required, consider separate indexes/keys or Elasticsearch security features.

### 12.4. Filters Affect Recall

Overly narrow filters can leave a query with zero results even when close vectors exist outside the filter. This is not necessarily an embedding flaw.

When debugging, log filter criteria (without sensitive values), the count of filter-matching documents, and returned hit counts.

## 13. Pagination, Scores, and Search Results

### 13.1. Top-k Is the Primary Contract of Vector Retrieval

kNN is generally designed to retrieve top-k nearest neighbors. Do not assume deep offset pagination behaves identically to ordinary lexical search across every kNN request.

If the UI needs multiple pages, evaluate retrieval strategies, candidate windows, and server paging APIs. You can pair a reranking step or cache session-scoped candidate lists if stable paging is required.

### 13.2. `SearchHits` Provides Metadata

Spring Data `SearchHits<T>` can include:

- Total hits and relation.
- Max score.
- List of `SearchHit<T>`.
- Individual hit scores.
- Sort values.
- Highlight fields.
- Aggregations and suggest results when requested.

Use this metadata to populate response DTOs. Avoid exposing raw Elasticsearch internal responses in public APIs unless needed.

### 13.3. Scores Are Not Probabilities

Vector scores depend on the similarity function and how Elasticsearch converts metrics into scores. BM25 scores follow their own semantics as well.

Do not interpret `0.82` as "82% match" without a calibration dataset and proper statistical definition.

### 13.4. Reranking

A pipeline may:

1. Retrieve 50–200 candidates via lexical and vector retrieval.
2. Combine candidates using RRF.
3. Rerank a small subset with a cross-encoder or specialized model.
4. Return top 10.

Reranking adds cost and latency, so cap the candidate count. Reranker models can run outside Elasticsearch or via server-supported features in specific releases.

## 14. Optimizing Quality and Performance

### 14.1. Measuring Recall and Latency

Track:

- Recall@k or an equivalent retrieval metric.
- NDCG/MRR when relevance judgments exist.
- Query latency p50/p95/p99.
- Indexing throughput.
- Vector index size.
- Memory/page cache usage.
- Candidate counts and filter selectivity.
- Documents missing embeddings.

Do not evaluate quality based on a handful of ad-hoc queries.

### 14.2. Tuning `num_candidates`

Raising `num_candidates` typically improves recall at higher cost. Test several levels on representative datasets and compare latency/recall.

Do not use one fixed value across all indexes if shard counts, vector dimensions, and data distributions vary widely.

### 14.3. Vector Dimensions and Memory

Large vector dimensions inflate storage and compute cost. Never pick a model solely for higher dimensions.

Evaluate:

- Semantic retrieval quality.
- Memory footprint.
- Index size.
- Ingest throughput.
- Query latency.
- Embedding inference cost.

Quantization and index options can shrink footprint with recall/accuracy trade-offs; availability depends on server version and mapping configuration.

### 14.4. Optimizing Filters and Shard Layout

Filtering by tenant, language, or document type affects candidate counts. Evaluate shard counts and data partitioning alongside query workloads.

Do not create excessive tiny shards solely expecting faster filtering. Shard design must consider ingestion, search concurrency, memory, and cluster overhead.

### 14.5. Keeping Vectors in the Page Cache

Approximate kNN relies on efficient access to vector indexes. If vector data does not fit well in memory/page cache, latency can spike sharply.

Monitor node memory, page cache, disk I/O, and search thread pools. Elasticsearch JVM heap sizing does not replace page cache memory requirements for vector indexes.

## 15. Common Pitfalls

| Symptom | Possible cause | Resolution |
|---|---|---|
| `withKnnSearches` does not compile | Spring Data is older than 5.4 or dependencies conflict | Check dependency tree and migration guide |
| `withKnnQuery` no longer exists | Upgraded to 5.4+ | Use `withKnnSearches` or construct `KnnQuery` in `withQuery` |
| Confusing `KnnSearch` and `KnnQuery` | Wrong placement of kNN in request | Determine top-level search vs Query DSL |
| 400 vector dimension mismatch | Query vector does not match `dims` | Check model output and mapping |
| 400 field does not support kNN | Field is not `dense_vector`/indexed vector or server lacks support | Check mapping and server version |
| Query returns 0 hits | Filter too narrow, vectors unindexed, or model mismatch | Check filters, data, and embedding pipeline |
| Poor recall | Low `num_candidates` or ill-suited model/preprocessing | Measure recall and tune candidates/model |
| Query too slow | Excessive candidates, `script_score` on broad set, or low page cache | Narrow scope, use approximate kNN, and profile resources |
| Lexical scores overwhelm vectors | Incompatible score scales | Tune boosts with relevance tests or use RRF |
| Query runs yet mapping annotation fails | Vector attribute unavailable in Spring Data version | Check `FieldType`/`@Field` Javadoc for your release |
| `NoSuchMethodError` | Incompatible Spring Data and Elasticsearch Java API Client | Let BOM manage client and inspect dependency tree |
| Wrong tenant results | Misplaced filter or untrusted tenant ID | Pass authorization-derived filters into requests |
| `semantic_text` query rejected | Top-level `knn` does not support that field type | Use Query DSL `knn` or `match` per server docs |
| Direct client deserializes fields wrong | Bypasses Spring Data mapping/converters | Use a dedicated DTO or mapping adapter |
| Re-embedding causes erratic rankings | Mixed vectors from two model versions | Reindex/re-embed consistently per model version |

## 16. Semantic Query Implementation Workflow

When building semantic search with Spring Data Elasticsearch:

1. Define the use case, content types, and authorization filters.
2. Choose an embedding model and record model version.
3. Lock down vector dimensions, metric, and preprocessing.
4. Create a `dense_vector` index mapping suited to your server version.
5. Generate document embeddings and index with deterministic IDs.
6. Generate query vectors using the same model.
7. Verify Spring Data release and Elasticsearch Java API Client version.
8. Use `NativeQuery` with supported query builders.
9. From Spring Data 5.4+, use `withKnnSearches` for top-level kNN search.
10. When `KnnQuery` inside Query DSL is needed, construct the query model and pass it via `withQuery`.
11. If builders lack a needed feature, invoke the configured Java API Client directly.
12. Add pre-filters for tenant, status, and access control.
13. Combine lexical/vector retrieval when both exact matching and semantic relevance matter.
14. Evaluate RRF/reranking against a relevance dataset.
15. Measure recall, latency, memory, and indexing throughput.
16. Run integration tests against a compatible Elasticsearch server version.
17. When changing models/dimensions/mappings, create a new index version and re-embed safely.

## 17. Key Takeaways

- Semantic search requires embeddings for both documents and queries; both sides must share identical model semantics.
- `dense_vector` mappings must declare accurate `dims` along with appropriate index and similarity settings.
- `NativeQuery` wraps query builders from the Elasticsearch Java API Client.
- `ElasticsearchOperations.search` preserves Spring Data mapping and returns `SearchHits<T>`.
- Approximate kNN fits large-scale retrieval; exact `script_score` fits small filtered subsets.
- `k` sets the number of nearest neighbors, while `num_candidates` affects recall and latency.
- Filters in kNN should apply prior to retrieval when scoping by tenant or status.
- Since Spring Data Elasticsearch 5.4, use `withKnnSearches` for top-level kNN; `KnnSearch` differs from `KnnQuery`.
- `KnnQuery` can be created via the Elasticsearch Java API Client and passed to `NativeQueryBuilder.withQuery`.
- On older versions, read matching Javadocs/migration guides; never paste newer APIs into older dependencies.
- Call the client directly when Spring Data builders lack a required feature, while managing mapping and serialization explicitly.
- Hybrid search combines lexical and vector retrieval; raw scores live on different scales, so consider RRF.
- `semantic_text` and inference queries carry different semantics/versions from `dense_vector`; choose the right query form.
- Scores are not probabilities and must be evaluated against relevance data.
- When changing embedding models or dimensions, never mix incompatible vectors; re-embed/reindex with proper versioning.
- Monitor recall, latency, page cache, memory, candidate counts, and mapping/query errors.

`NativeQuery` serves as a convenient bridge between Spring Data and the Elasticsearch Java API Client for complex semantic queries. By selecting the right query form, using release-appropriate builders, synchronizing embedding models, and controlling filters and rankings, applications can combine semantic retrieval with other search capabilities while remaining inside the Spring Data ecosystem.
