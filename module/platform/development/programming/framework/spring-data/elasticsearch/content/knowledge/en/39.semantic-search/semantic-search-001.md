# Distinguishing Keyword Search and Semantic Search

In Elasticsearch, keyword search (lexical search) and meaning-based search (semantic search) address two different ways of expressing queries. Lexical search finds documents based on terms appearing in analyzed content; it fits when users know a specific name, code, phrase, or keyword. Semantic search represents queries and content as vector embeddings and finds nearby documents in vector space; it fits when users describe their need in natural language, use synonyms, or do not know the exact terminology in the documents.

The two approaches are not mutually exclusive. Keyword search is usually more accurate for SKUs, proper names, serial numbers, technical terms, and filtering conditions. Semantic search can often find relevant content even without matching words. Good search systems commonly combine lexical retrieval, vector retrieval, and reranking to balance precision, recall, and semantic relevance.

This lesson explains the inverted index, analyzers, BM25, and `text`/`keyword` fields; embeddings, vector similarity, kNN, and chunking; how to organize mappings and queries in Spring Data Elasticsearch; how to build hybrid search; how to evaluate relevance; and how to operate an embedding pipeline.

## 1. Two Different Ways of Understanding a Query

Suppose a document repository has an article titled "How to recover data after a hard drive failure". A user enters:

~~~text
How can I get files back when the computer cannot read the hard drive?
~~~

Keyword search may look for tokens such as `get`, `files`, `back`, `hard`, `drive`. If the document only uses the words "recover data", results may not rank highly due to few overlapping tokens.

Semantic search can recognize that both expressions refer to the same intent: recovering files from an inaccessible drive. It can find the document even though key words do not match verbatim.

Another example:

~~~text
Query: KB-100
Document: Wireless keyboard model KB-100
~~~

For product code queries, lexical/exact search is usually more reliable. Embeddings are not designed to guarantee exact character-by-character matching of codes.

| Characteristic | Keyword / lexical search | Semantic search |
|---|---|---|
| Primary signal | Tokens, phrases, fields, and occurrence frequency | Vector embeddings and similarity |
| Synonyms | Depends on analyzers, synonym graphs, or query expansion | Can be found through embedding meaning |
| Codes, SKUs, exact names | Very suitable when mapping/query is configured properly | Can be less accurate |
| Natural phrasing | Depends on token overlap | Usually more suitable |
| Explainability | Can inspect matches, scores, fields, and analyzers | Score represents similarity, harder to interpret directly |
| Cost | Typically low, uses inverted index | Requires generating/storing embeddings and computing vector similarity |
| Data preparation needed | Text and appropriate mapping | Text, embedding model, vector mapping |

Not every type of text search should be called "exact keyword". In Elasticsearch, the `keyword` field type is for values not analyzed into tokens; whereas full-text search typically uses the `text` field type with an analyzer. Both belong to lexical retrieval, but serve different matching behaviors.

## 2. What Is Keyword Search?

Keyword search typically relies on an inverted index. Instead of scanning every document for a string, Elasticsearch analyzes content into tokens and builds an index mapping each token to the documents containing that token.

Example documents:

~~~text
Document A: Spring Data Elasticsearch supports repositories.
Document B: Elasticsearch can perform vector search.
Document C: Spring Boot configures repositories.
~~~

Illustrative inverted index:

~~~text
spring        -> A, C
data          -> A
elasticsearch -> A, B
repository    -> A, C
vector        -> B
boot          -> C
~~~

When a query contains the token `Elasticsearch`, the engine looks up the inverted index to find candidate documents and then computes relevance scores.

### 2.1. Text Analysis with Analyzers

Before indexing or running a full-text query, an analyzer can perform:

1. Character filters: transform the input string before tokenization.
2. Tokenizer: split the string into tokens.
3. Token filters: lowercase, stemming, stop words, synonyms, and other transformations.

For example, a simple analyzer can turn:

~~~text
Spring Data Elasticsearch
~~~

into the tokens:

~~~text
spring
data
elasticsearch
~~~

When the query is analyzed with a compatible analyzer, Elasticsearch can match documents by tokens rather than requiring an identical string.

The analyzer directly affects searchability. If an index uses an English analyzer while the content is Vietnamese, stemming and stop-word rules may be inappropriate. For Vietnamese, you need to consider tokenizers, Vietnamese diacritics, compound words, and domain-specific word segmentation.

### 2.2. `text` Fields and `keyword` Fields

Elasticsearch has two important field types:

- `text`: analyzed into tokens, suitable for full-text search.
- `keyword`: keeps the value as a single term, suitable for exact match, sorting, aggregation, and filtering.

Example mapping:

~~~json
{
  "mappings": {
    "properties": {
      "name": {
        "type": "text",
        "fields": {
          "keyword": {
            "type": "keyword"
          }
        }
      },
      "sku": {
        "type": "keyword"
      },
      "description": {
        "type": "text"
      },
      "category": {
        "type": "keyword"
      }
    }
  }
}
~~~

With the mapping above:

- `name` uses a `match` query to search by token.
- `name.keyword` uses a `term` query to match the entire indexed value.
- `sku` uses a `term` query for product codes.
- `description` uses `match` or other full-text queries.
- `category` is used for filtering/aggregation.

### 2.3. Exact Matching Is Not Full-Text Matching

`term` query on a `keyword` field:

~~~json
{
  "query": {
    "term": {
      "sku": "KB-100"
    }
  }
}
~~~

`match` query on a `text` field:

~~~json
{
  "query": {
    "match": {
      "description": "wireless keyboard"
    }
  }
}
~~~

`term` looks up an exact term according to how the field is indexed. `match` analyzes the query into tokens and then performs full-text matching. Do not use a `term` query on a `text` field expecting it to analyze phrases like a `match` query.

### 2.4. Keyword Search Does Not Always Require Every Word to Appear

By default, a `match` query typically combines tokens using the `OR` operator. You can require `AND`:

~~~json
{
  "query": {
    "match": {
      "description": {
        "query": "wireless mechanical keyboard",
        "operator": "and"
      }
    }
  }
}
~~~

With `AND`, a document must match all tokens after analysis. This increases strictness, but can miss relevant documents if the author used synonyms or different phrasing.

## 3. Relevance Scoring and BM25

Lexical search commonly ranks documents using BM25, an algorithm based on term frequency in the document, term rarity across the corpus, and document length.

Key intuitions:

- A term appearing multiple times in a document can make the document more relevant, though the gain does not grow linearly without bound.
- A rare term in the dataset generally has higher discriminative power than a term appearing in most documents.
- Long documents are normalized so they do not always have an advantage simply by containing more words.

A query with two terms:

~~~text
Spring Elasticsearch
~~~

A document containing both terms in the `title` can rank higher than a document containing only one term inside a long body.

### 3.1. Field Boosting

You can weight `title` higher than `description`:

~~~json
{
  "query": {
    "multi_match": {
      "query": "reactive repository",
      "fields": [
        "title^4",
        "summary^2",
        "content"
      ]
    }
  }
}
~~~

The `^4` and `^2` notation represents field boosts. `title` is prioritized over `summary`, and `summary` over `content`.

### 3.2. Filter and Query Context

Business conditions should use `filter` when scoring is not needed:

~~~json
{
  "query": {
    "bool": {
      "must": [
        {
          "multi_match": {
            "query": "reactive repository",
            "fields": ["title^3", "content"]
          }
        }
      ],
      "filter": [
        {
          "term": {
            "status": "PUBLISHED"
          }
        },
        {
          "term": {
            "tenantId": "tenant-7"
          }
        }
      ]
    }
  }
}
~~~

Query context affects relevance score; filter context only checks yes/no eligibility and can be cached. Never let vector similarity or BM25 replace authorization/tenant filtering.

### 3.3. Synonyms in Lexical Search

A synonym filter or synonym graph helps lexical search understand declared equivalent terms:

~~~text
laptop, notebook
cell phone, mobile phone
elasticsearch, es
~~~

This improves recall without embeddings. However, a synonym dictionary must be maintained per domain and can broaden queries. Synonyms do not automatically understand arbitrary new phrasing like an embedding model.

## 4. What Is Semantic Search?

Semantic search converts content into numeric vectors (embeddings). An embedding model takes text and produces a multi-dimensional vector. Texts with similar meaning usually have vectors that are close under the metric the model was trained to support.

Illustrative example:

~~~text
"how to recover deleted files"
          |
          v
     Embedding model
          |
          v
 [0.12, -0.31, 0.08, ...]

"restore lost documents"
          |
          v
     Embedding model
          |
          v
 [0.11, -0.29, 0.10, ...]
~~~

Two vectors can be close even if the sentences do not share many tokens. At search time, the system generates an embedding for the query and finds the nearest document vectors.

### 4.1. Embeddings Are Not a Synonym Dictionary

Embeddings learn representations from context and training data. They can find semantic relationships without declaring every synonym pair, but they do not guarantee:

- Two synonymous phrases always have close vectors in every domain.
- Product codes or serial numbers are distinguished accurately.
- The model understands internal terminology absent from training data.
- Vector scores are probabilities of correctness.

Quality depends on the model, language, domain, chunking strategy, training, and query distribution.

### 4.2. Queries and Documents Must Use the Same Embedding Space

Query and document vectors need to be produced by compatible models:

- The same model or a model pair designed to be compatible.
- The same number of dimensions.
- The same normalization and preprocessing per the model's guidelines.
- The same embedding contract version.

Do not swap the query vector model while still comparing against old vectors if the two models are incompatible. When changing models, you usually need to regenerate embeddings for all documents or maintain a separate versioned field/index.

### 4.3. Dense Vector Mapping

A document can store both text and embeddings:

~~~json
{
  "mappings": {
    "properties": {
      "title": {
        "type": "text"
      },
      "content": {
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

Here `768` is just an example. `dims` must match the embedding model's output. Choose `similarity` according to the model and how vectors are produced; `cosine`, `dot_product`, and `l2_norm` are common options.

### 4.4. Storing Embeddings in a Spring Data Entity

Example entity:

~~~java
@Document(indexName = "knowledge-articles")
public class KnowledgeArticle {

    @Id
    private String id;

    @Field(type = FieldType.Text)
    private String title;

    @Field(type = FieldType.Text)
    private String content;

    @Field(type = FieldType.Dense_Vector, dims = 768,
            similarity = "cosine")
    private float[] embedding;
}
~~~

Annotation property names and vector mapping support depend on the Spring Data Elasticsearch release in use. The actual index mapping must match the dimensions, similarity, and `dense_vector` options supported by the Elasticsearch version.

If using JSON-managed mappings or index templates, ensure entity metadata and actual mapping do not conflict. Do not let Spring auto-create a mapping with dimensions different from the model output.

## 5. Vector Similarity and k-Nearest Neighbors

Once a query is converted into a vector, Elasticsearch finds the nearest vectors using k-nearest neighbors (kNN).

Common metrics:

| Metric | Intuition | Notes |
|---|---|---|
| cosine similarity | Compares angle between two vectors | Commonly used with embeddings trained for cosine |
| dot product | Inner product | Magnitude can affect score; model may require normalization |
| L2 distance | Euclidean distance | Smaller values indicate closer vectors |

Do not directly compare scores across two different metrics or models. Scores are only meaningful within their corresponding query and configuration.

### 5.1. `k` and `num_candidates`

In kNN search:

- `k` is the target number of neighbors to retrieve.
- `num_candidates` is the number of candidates considered per shard in approximate kNN, usually required to be greater than or equal to `k`.
- Filters can restrict the candidate set according to business rules.

REST example:

~~~http
POST knowledge-articles/_search
{
  "knn": {
    "field": "embedding",
    "query_vector": [0.12, -0.31, 0.08],
    "k": 10,
    "num_candidates": 100
  }
}
~~~

The example vector only has three dimensions to illustrate syntax; in a real index, the number of elements must match the mapping's `dims`.

Increasing `num_candidates` generally improves recall of approximate search at higher compute cost. Choose it by benchmarking on real data and queries.

### 5.2. Approximate and Exact Vector Search

Approximate nearest neighbor (ANN) uses a vector index structure to quickly find the closest candidates and may not return the exact absolute top-k. Exact search can evaluate all vectors in the filtered set and is usually more expensive on large datasets.

The choice depends on:

- Number of vectors.
- Target latency.
- Required recall.
- Filter selectivity.
- Memory and shard configuration.
- Elasticsearch version and vector index options.

Do not assume ANN is always better than exact search. For small datasets or very selective filters, exact search may be more appropriate.

## 6. Generating Embeddings for Content

Elasticsearch stores and searches vectors, while embeddings are usually generated by an external model or inference service. An indexing pipeline typically consists of:

~~~text
Source content
      |
      v
Normalize / clean text
      |
      v
Split into chunks (if needed)
      |
      v
Embedding model
      |
      v
Vector + source metadata
      |
      v
Elasticsearch index
~~~

Query pipeline:

~~~text
User query
     |
     v
Query normalization
     |
     v
Same compatible embedding model
     |
     v
Query vector
     |
     v
Elasticsearch kNN / hybrid search
     |
     v
Relevant documents or chunks
~~~

### 6.1. Embeddings at Index Time and Query Time

Document embeddings are typically computed when content is created or updated. Query embeddings are computed each time a user searches.

Both pipelines must use the same contract:

- Model ID and model version.
- Output dimensions.
- Text normalization.
- Language handling.
- Prefix/instruction if required by the model.
- Vector normalization if required by the model.

If documents use model A while queries use an incompatible model B, vector distances no longer reflect true meaning.

### 6.2. The Embedding Model Does Not Have to Run Inside Elasticsearch

You can invoke the model via:

- An internal embedding service.
- A cloud inference API.
- A dedicated model server.
- Elasticsearch inference integration if supported by the cluster and version.

Spring Data Elasticsearch focuses on data mapping and querying. Embedding generation can be encapsulated in a dedicated `EmbeddingService` to make swapping models and testing easier.

Example contract:

~~~java
public interface EmbeddingService {

    float[] embedDocument(String text);

    float[] embedQuery(String text);
}
~~~

Some models use different prompts/instructions for queries and documents. In that case, do not merge both methods into one if doing so loses that necessary distinction.

## 7. Chunking Long Documents

A long document can contain multiple topics. Generating a single embedding for the entire text can blur specific subtopics. Chunking splits content into appropriately sized segments:

~~~text
Article
  |
  +-- Chunk 0: Introduction and objectives
  +-- Chunk 1: Connection configuration
  +-- Chunk 2: Authentication
  +-- Chunk 3: Troubleshooting
~~~

Each chunk can have its own vector:

~~~json
{
  "chunkId": "article-42#2",
  "articleId": "article-42",
  "chunkNumber": 2,
  "title": "Authentication configuration",
  "content": "The application configures username and API key...",
  "embedding": [0.12, -0.31, 0.08]
}
~~~

### 7.1. Chunk Size and Overlap

Chunks that are too large:

- Can contain multiple unrelated topics.
- Make it difficult for the embedding to represent smaller ideas.
- Return too much unnecessary content.

Chunks that are too small:

- Lose context.
- Increase vector count and index size.
- Can split a single idea across two chunks.

Overlap retains some tokens between adjacent chunks to reduce context loss at boundaries. Chunk size and overlap should be measured against the tokenizer/model and document structure rather than picking one universal number for all data types.

### 7.2. Storing Metadata to Trace Back to the Original Document

Chunk documents should store `articleId`, `chunkNumber`, `title`, source URL, `tenantId`, permissions, and other required metadata. After retrieval, the application can:

- Return the relevant excerpt.
- Group chunks by original document.
- Deduplicate hits from the same article.
- Display the source and passage location.
- Enforce document-level access permissions.

If you only store vectors without source identity, displaying sources and deleting/reindexing documents becomes much harder.

## 8. Keyword Queries with Spring Data Elasticsearch

Spring Data Elasticsearch supports repository query methods, `CriteriaQuery`, and `NativeQuery`. For simple queries, repository methods may suffice:

~~~java
public interface ArticleRepository
        extends ElasticsearchRepository<KnowledgeArticle, String> {

    List<KnowledgeArticle> findByTitle(String title);

    Page<KnowledgeArticle> findByStatus(
            String status,
            Pageable pageable);
}
~~~

For full-text queries requiring control over operators, field boosts, or `bool` queries, use `NativeQuery`:

~~~java
NativeQuery query = NativeQuery.builder()
        .withQuery(q -> q
                .multiMatch(m -> m
                        .query("reactive search repository")
                        .fields("title^3", "summary^2", "content")))
        .withPageable(PageRequest.of(0, 10))
        .build();

SearchHits<KnowledgeArticle> hits = operations.search(
        query,
        KnowledgeArticle.class,
        IndexCoordinates.of("knowledge-articles"));
~~~

`SearchHits` holds the score and metadata of each hit. If you only need the entities, you can map `SearchHit::getContent`.

### 8.1. Exact Identifier Query

For a SKU or external ID:

~~~java
NativeQuery query = NativeQuery.builder()
        .withQuery(q -> q
                .term(t -> t
                        .field("sku")
                        .value("KB-100")))
        .build();
~~~

The `sku` field should be mapped as `keyword`. Do not put product codes solely into vector search and expect a semantic model to distinguish every character accurately.

### 8.2. Filtering by Tenant and Status

~~~java
NativeQuery query = NativeQuery.builder()
        .withQuery(q -> q
                .bool(b -> b
                        .must(m -> m
                                .multiMatch(mm -> mm
                                        .query(userQuery)
                                        .fields("title^3", "content")))
                        .filter(f -> f
                                .term(t -> t
                                        .field("tenantId")
                                        .value(tenantId)))
                        .filter(f -> f
                                .term(t -> t
                                        .field("status")
                                        .value("PUBLISHED")))))
        .withPageable(PageRequest.of(0, 10))
        .build();
~~~

Tenant and access filters must be applied on the server. Do not trust a client-supplied `tenantId` if the request's authorization context provides a trustworthy value.

## 9. Vector Queries with Spring Data Elasticsearch

With the Elasticsearch Java API Client, a kNN query can be expressed in Query DSL. An example using `NativeQuery`:

~~~java
float[] embedding = embeddingService.embedQuery(userQuery);
List<Float> queryVector = toList(embedding);

NativeQuery query = NativeQuery.builder()
        .withQuery(q -> q
                .knn(k -> k
                        .field("embedding")
                        .queryVector(queryVector)
                        .k(10)
                        .numCandidates(100)))
        .build();

SearchHits<KnowledgeArticle> hits = operations.search(
        query,
        KnowledgeArticle.class,
        IndexCoordinates.of("knowledge-articles"));
~~~

Builder method names and kNN representation can vary by Elasticsearch Java API Client / Spring Data Elasticsearch version. Verify against the API of the dependency in use. If the current Spring Data version does not expose part of a newer Query DSL, you can use the Elasticsearch Java API Client directly in a dedicated adapter.

### 9.1. Vector Dimensions Must Match

If the mapping declares `dims = 768`, the query vector must have exactly 768 elements. Mismatched dimensions can cause the request to be rejected.

Validate dimensions immediately after calling the embedding service:

~~~java
float[] vector = embeddingService.embedQuery(queryText);

if (vector.length != EXPECTED_DIMENSIONS) {
    throw new IllegalStateException("Unexpected embedding dimensions");
}
~~~

Do not log the entire vector. If debugging is needed, log the model version and vector length.

### 9.2. Filters in kNN

Example vector query with a tenant filter:

~~~http
POST knowledge-articles/_search
{
  "knn": {
    "field": "embedding",
    "query_vector": [0.12, -0.31, 0.08],
    "k": 10,
    "num_candidates": 100,
    "filter": {
      "bool": {
        "filter": [
          {"term": {"tenantId": "tenant-7"}},
          {"term": {"status": "PUBLISHED"}}
        ]
      }
    }
  }
}
~~~

Filters restrict results to the permitted tenant/status scope. Use filters inside vector retrieval if the version/API supports the right semantics; do not fetch global top-k and filter in the application, as that can miss valid results and create data exposure risks.

## 10. Hybrid Search: Combining Lexical and Semantic

Keyword and semantic approaches have different strengths:

- Lexical finds exact codes, names, phrases, and specific terms.
- Semantic finds content close in meaning.

Hybrid search runs both retrieval sources and combines the results:

~~~text
                  User query
                      |
          +-----------+-----------+
          |                       |
          v                       v
   Lexical retrieval        Query embedding
   BM25 / inverted index           |
          |                        v
          |                 Vector retrieval
          |                   kNN / ANN
          |                        |
          +-----------+------------+
                      |
                      v
               Merge candidates
                      |
                      v
                 Reranking
                      |
                      v
              Final ranked results
~~~

Hybrid search is useful when queries contain both exact keywords and semantic intent, for example "how to configure TLS for Elasticsearch Java client".

Lexical search can match `Elasticsearch`, `TLS`, `Java client` verbatim. Semantic search can find articles discussing certificate validation, CA fingerprints, or secure transport even without using the exact query wording.

### 10.1. Combining with Reciprocal Rank Fusion

Reciprocal Rank Fusion (RRF) combines rankings from multiple retrievers without normalizing raw BM25 scores and vector scores onto the same scale.

Intuitive formula:

\[
\operatorname{RRF}(d) =
\sum_{r \in R}
\frac{1}{k_0 + \operatorname{rank}_r(d)}
\]

Where `rank_r(d)` is the rank of document `d` in retriever `r`, and `k0` is a constant that dampens the impact of very high positions. Documents appearing strongly across multiple lists are promoted.

RRF is useful because BM25 scores and vector similarity scores usually live on different scales. You should not directly add two uncalibrated scores together.

Recent Elasticsearch versions support `retriever`/`rrf` depending on cluster capabilities. Syntax and Spring Data support depend on version. If the current Spring Data abstraction does not expose the retriever API, you can call the search endpoint via a client adapter and map results back to your domain model.

### 10.2. Hybrid Queries via Multiple Application-Side Searches

A version-independent approach is to execute lexical and vector searches separately:

~~~java
List<SearchHit<KnowledgeArticle>> lexical =
        searchLexically(userQuery);

List<SearchHit<KnowledgeArticle>> semantic =
        searchSemantically(embeddingService.embedQuery(userQuery));

List<RankedArticle> merged = fusionService.rrf(
        lexical,
        semantic,
        60);
~~~

The fusion service must identify the same document using a stable document ID or source ID. Do not merge by `title`, since titles can collide or change.

Two separate searches issue two requests and may observe different data snapshots if the index is updating. If consistency is required, use a snapshot/PIT mechanism or built-in hybrid queries supported by Elasticsearch.

### 10.3. Do Not Arbitrarily Sum Raw Scores

Erroneous example:

~~~java
combinedScore = bm25Score + cosineSimilarity;
~~~

BM25 can be much larger and vary by corpus/query; cosine similarity has a different scale. Direct addition can allow one retriever to dominate.

Better approaches:

- Rank-based RRF.
- Score normalization across the candidate set using an evaluated method.
- Training/validating a reranker on relevance labels.
- Using Elasticsearch's native hybrid retriever if suitable.

## 11. Reranking After Retrieval

Retrieval typically prioritizes recall: finding a sufficiently broad set of candidates. Reranking reorders candidates using a richer model or additional signals.

Example pipeline:

1. Lexical retrieval takes top 50.
2. Semantic retrieval takes top 50.
3. Merge and deduplicate by document ID.
4. Reranker scores query-document pairs.
5. Return top 10.

Bi-encoder embeddings produce query and document vectors separately, suitable for fast search across large indexes. Cross-encoders inspect query and document together, often capturing finer-grained interactions but at higher cost over many candidates.

Do not run a cross-encoder over the entire corpus. Use retrieval to narrow candidates and then rerank the top N.

## 12. Designing an Index for Both Lexical and Semantic Search

A document can store both text fields and an embedding:

~~~json
{
  "id": "article-42",
  "title": "Configure TLS for Elasticsearch client",
  "content": "The application can verify the CA certificate...",
  "category": "security",
  "status": "PUBLISHED",
  "tenantId": "tenant-7",
  "embedding": [0.12, -0.31, 0.08]
}
~~~

Mapping can include:

~~~json
{
  "mappings": {
    "properties": {
      "title": {
        "type": "text",
        "fields": {
          "keyword": {"type": "keyword"}
        }
      },
      "content": {"type": "text"},
      "category": {"type": "keyword"},
      "status": {"type": "keyword"},
      "tenantId": {"type": "keyword"},
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

`text` fields serve lexical retrieval; `keyword` fields serve exact matching/filtering/sorting; `dense_vector` serves vector retrieval. One document can be retrieved through all three types of signals.

### 12.1. Do Not Embed Every Field

You do not need to include SKU, timestamp, tenant ID, status, or serial numbers in embedding text. Fields with structured semantics should be queried/filtered exactly.

Text used to generate embeddings is usually intentionally composed content:

~~~text
Title: Configure TLS for Elasticsearch client
Category: Security
Content: The application verifies the CA certificate...
~~~

Do not concatenate arbitrary metadata; metadata can skew embeddings away from the core content.

### 12.2. Multi-Field and Analyzers

A field may need both full-text and exact forms:

~~~json
{
  "title": {
    "type": "text",
    "analyzer": "standard",
    "fields": {
      "keyword": {
        "type": "keyword",
        "ignore_above": 256
      }
    }
  }
}
~~~

If sorting or exact title matching is needed, use `title.keyword`. If searching by tokens, use `title`.

## 13. Mapping with Spring Data Elasticsearch

An entity can use annotations:

~~~java
@Document(indexName = "knowledge-articles")
public class KnowledgeArticle {

    @Id
    private String id;

    @Field(type = FieldType.Text)
    private String title;

    @Field(type = FieldType.Text)
    private String content;

    @Field(type = FieldType.Keyword)
    private String category;

    @Field(type = FieldType.Keyword)
    private String tenantId;

    @Field(type = FieldType.Dense_Vector, dims = 768,
            similarity = "cosine")
    private float[] embedding;
}
~~~

When `title` needs a `keyword` multi-field, you can declare appropriate field mapping metadata via annotations or manage JSON mappings separately depending on version capabilities. Verify the actual mapping using the get mapping API.

Creating the index/mapping:

~~~java
IndexOperations indexOps = operations.indexOps(KnowledgeArticle.class);

if (!indexOps.exists()) {
    indexOps.createWithMapping();
}
~~~

The `dense_vector` mapping generally needs to be defined accurately before indexing data. Changing dimensions or similarity after data exists may require creating a new index and reindexing.

## 14. Organizing the Embedding Service

Do not call the embedding provider directly from controllers or repositories. Place an abstraction in between:

~~~java
public interface EmbeddingService {
    float[] embedQuery(String text);
    float[] embedDocument(String text);
}
~~~

Indexer:

~~~java
public void indexArticle(Article article) {
    String embeddingText = article.getTitle()
            + "\n"
            + article.getContent();

    float[] vector = embeddingService.embedDocument(embeddingText);

    KnowledgeArticle document = mapper.toDocument(article, vector);
    repository.save(document);
}
~~~

Search:

~~~java
public SearchHits<KnowledgeArticle> semanticSearch(String queryText) {
    float[] vector = embeddingService.embedQuery(queryText);
    return vectorSearchRepository.search(vector);
}
~~~

Benefits:

- Swap providers/models without modifying repositories.
- Mock the embedding service in unit tests.
- Centralize timeouts, retries, rate limits, and caching.
- Track model version and dimensions.
- Run embedding asynchronously in an ingestion pipeline.

### 14.1. Timeouts and Retries for the Embedding Provider

An embedding API is a network dependency. You need:

- Appropriate timeouts.
- Bounded retries for transient errors.
- Backoff and jitter to prevent retry storms.
- Rate limiting and concurrency control.
- A circuit breaker if the provider experiences prolonged outages.
- Monitoring for latency, token usage, and error rates.

Do not retry indefinitely or generate embeddings synchronously on every request if user latency does not allow it.

### 14.2. Caching Query Embeddings

Common queries can be cached if privacy policies and freshness permit. The cache key should include normalized query, model ID/version, language, and instruction context. When switching models, old cached entries must not be served by mistake.

Do not cache query embeddings containing sensitive data in unauthorized storage.

## 15. Updating and Versioning Embeddings

Embeddings are derived data built from text and a model. When content changes, old embeddings no longer represent the updated document.

An update workflow:

1. Receive new source content.
2. Re-normalize/re-chunk if necessary.
3. Generate embeddings with the current model version.
4. Write text, metadata, vector, and `embeddingVersion` together in one document/indexing operation.
5. Ensure the query service uses a compatible model.

Store metadata:

~~~json
{
  "embeddingModel": "embedding-model-v3",
  "embeddingVersion": 3,
  "embeddingDimensions": 768
}
~~~

### 15.1. Re-embedding When Changing Models

You cannot assume vectors from model v2 share the same space as model v3. You can create a new index:

~~~text
knowledge-v2
knowledge-v3
      |
      v
Build vectors using model v3
      |
      v
Validate retrieval quality
      |
      v
Switch alias / application config
~~~

Keep the old index for rollback during the transition window. Do not mix vectors from two different models into the same field if they are incompatible.

### 15.2. Embedding Drift

Even when the model stays unchanged, preprocessing, chunking, or source content can change. Track the version of the vector generation pipeline, not just the model name.

## 16. Semantic Search and Security Filters

Semantic retrieval does not replace authorization. A document having a vector close to the query does not mean the user is allowed to view it.

Every query needs appropriate filters:

- Tenant ID taken from authenticated context.
- Published status.
- ACL/visibility.
- Project or group scope.
- Effective date if required by business rules.

Example:

~~~json
{
  "knn": {
    "field": "embedding",
    "query_vector": [0.12, -0.31, 0.08],
    "k": 10,
    "num_candidates": 100,
    "filter": {
      "term": {
        "tenantId": "tenant-7"
      }
    }
  }
}
~~~

If using multiple separate retrievers, ensure both lexical and semantic branches enforce the same access conditions. Do not only filter after merging if candidates already contain unauthorized data leaving the search layer.

## 17. Evaluating Search Quality

You cannot choose keyword, semantic, or hybrid by intuition alone. You need a representative query set and relevance judgments.

Create an evaluation set:

| Query | Relevant document | Relevance level |
|---|---|---|
| KB-100 | Product KB-100 | Exact |
| wireless keyboard | Wireless keyboard article | High |
| recover lost files | Data recovery guide | High |
| how to verify certificate | TLS verification guide | High |
| Elasticsearch vector dimensions | Dense vector mapping guide | High |

Run each retriever and record top-k results. Compare against relevance labels.

### 17.1. Recall@k

Recall@k measures the fraction of relevant documents found in the top k:

\[
\operatorname{Recall@k} =
\frac{\text{relevant documents in top k}}
{\text{all relevant documents}}
\]

Semantic retrieval can improve recall when wording differs.

### 17.2. Precision@k

Precision@k measures the fraction of top-k results that are actually relevant:

\[
\operatorname{Precision@k} =
\frac{\text{relevant documents in top k}}{k}
\]

Exact keyword search can achieve high precision on product codes, but low recall when queries use synonyms.

### 17.3. MRR and nDCG

- Mean Reciprocal Rank (MRR) measures the position of the first relevant result.
- Normalized Discounted Cumulative Gain (nDCG) evaluates ranking with graded relevance and discounts results at lower positions.

These metrics are useful when the system has graded relevance rather than binary relevant/not relevant.

### 17.4. Evaluating by Query Group

Categorize queries:

- Exact identifiers: SKU, ID, error code.
- Proper names: product name, framework, API.
- Natural-language questions.
- Synonyms/paraphrases.
- Multilingual queries.
- Long multi-intent queries.
- Ambiguous queries.

One method may perform well on natural-language questions while doing poorly on SKUs. Evaluating by group highlights trade-offs rather than hiding them behind a single aggregate metric.

## 18. Observing Relevance and Debugging Results

For lexical search:

- Use the Explain API to understand scores.
- Inspect analyzers with the Analyze API.
- Check field mappings.
- Inspect query tokens and document tokens.
- Adjust field boosts, operators, and synonyms.

For semantic search:

- Check model version and dimensions.
- Inspect the text used to generate embeddings.
- Check chunk boundaries.
- Check the similarity metric and vector normalization.
- Check filters and candidate counts.
- Inspect nearest documents using test queries.

Do not blindly increase `num_candidates` or swap models before identifying whether the issue lies in retrieval, mapping, filtering, or data preparation.

## 19. Latency, Cost, and Operations

Keyword search usually requires only an Elasticsearch query. Semantic search adds a query embedding step and vector retrieval. Hybrid search may invoke multiple retrievers and a reranker.

| Component | Cost/latency to monitor |
|---|---|
| Lexical retrieval | Query latency, shard fan-out, analyzer/query complexity |
| Query embedding | Provider latency, tokens, rate limits |
| Vector retrieval | Vector index size, memory, `num_candidates`, shard count |
| Hybrid fusion | Request count, merge/deduplication |
| Reranking | Model inference latency and candidate count |
| Document embedding | Ingestion throughput, model cost, re-embedding backlog |

Mitigations:

- Cache query embeddings with version-aware keys.
- Batch document embeddings when supported by the provider.
- Use async ingestion for large updates.
- Limit candidate counts and rerank only top N.
- Keep text/vector indexes versioned together during migrations.
- Measure p50, p95, and p99 latency.
- Monitor embedding failures and backlog.

## 20. When to Use Keyword, Semantic, or Hybrid?

| Use case | Starting choice | Reason |
|---|---|---|
| Lookup by SKU/order ID/error code | Exact keyword/term | Requires exact match |
| Searching by API or class name | Lexical, optionally combined with semantic | Technical names need clear matching |
| Finding docs via natural-language questions | Semantic or hybrid | Users may phrase differently from content |
| Product search by descriptive need | Hybrid | Keeps exact filters/brand/price while capturing intent |
| Finding docs with mandatory terminology | Lexical + semantic | Avoids dropping essential keywords |
| Q&A over a long document corpus | Semantic/hybrid over chunks | Needs to locate relevant passages by meaning |
| Filtering by status, tenant, date | Filter/keyword | Structured conditions |
| Searching by proper names and paraphrases | Hybrid | Combines exact terms and semantics |

If data is small or queries are simple, keyword search may already be enough. Do not add embeddings solely for novelty; a semantic pipeline carries operational, evaluation, and vector update costs.

## 21. Example Hybrid Service in Spring

You can create an orchestrating service:

~~~java
@Service
public class ArticleSearchService {

    private final LexicalArticleSearch lexicalSearch;
    private final SemanticArticleSearch semanticSearch;
    private final EmbeddingService embeddingService;
    private final SearchFusionService fusionService;

    public ArticleSearchService(
            LexicalArticleSearch lexicalSearch,
            SemanticArticleSearch semanticSearch,
            EmbeddingService embeddingService,
            SearchFusionService fusionService) {
        this.lexicalSearch = lexicalSearch;
        this.semanticSearch = semanticSearch;
        this.embeddingService = embeddingService;
        this.fusionService = fusionService;
    }

    public List<ArticleResult> search(String query, String tenantId) {
        List<SearchHit<KnowledgeArticle>> lexical =
                lexicalSearch.search(query, tenantId, 50);

        float[] queryVector = embeddingService.embedQuery(query);

        List<SearchHit<KnowledgeArticle>> semantic =
                semanticSearch.search(queryVector, tenantId, 50);

        return fusionService.rrf(lexical, semantic, 10);
    }
}
~~~

This is an illustrative structure; search adapters are responsible for building `NativeQuery` and converting `SearchHits`. In production, both branches can run in parallel if independent and timeouts/cancellations are managed. If a server-side hybrid retriever is needed, use the API corresponding to your Elasticsearch version.

### 21.1. Deduplicating by Document Identity

The fusion service should map by document ID or source identity:

~~~java
Map<String, RankedCandidate> candidates = new LinkedHashMap<>();
~~~

Do not deduplicate by `title` or display text, because two distinct documents can share a title. If the index uses chunks, you can deduplicate on `articleId` after selecting suitable chunks.

### 21.2. Preserving Separate Scores and Ranks

When merging, keep:

- Lexical rank and lexical score.
- Semantic rank and semantic score.
- Fused rank/score.
- Reranker score if applicable.

This helps observe why a result ranked where it did and tune fusion. Do not call a fused score a relevance probability without calibration.

## 22. Limitations of Semantic Search

Semantic search can find content close in meaning but does not guarantee detail-level precision:

- Two products with similar names but different models.
- Two different API versions.
- Error codes differing by a single digit.
- Negation conditions like "TLS disabled".
- Numeric values, dates, and thresholds.
- Newly added content not yet embedded.
- Multi-intent queries where a single vector loses focus.

For critical conditions, combine with filters/exact lexical matching. If complex logic understanding is needed, query parsing or a reranker can help, though data must still be verified.

### 22.1. Semantic Similarity Is Not Truth

A document with a close vector does not necessarily provide the right answer. A model may treat two related concepts as close even when they differ in version, conditions, or outcomes. Systems should display sources and allow inspecting original content.

### 22.2. Short or Ambiguous Queries

A single-word query like "Java" might refer to the language, runtime, coffee, or a product named Java. Lexical search may return too many results; semantic search also cannot infer intent without context.

You can:

- Ask the user for clarification.
- Apply category/context filters.
- Prioritize history or current scope when justified.
- Display grouped results across categories.

## 23. Common Mistakes

### Using a `term` query on a `text` field

`term` does not analyze queries like `match`. Use `match` for full-text or a `keyword` field for exact terms.

### Using a `match` query for SKUs

Analyzers may split or alter codes. Use `keyword` mapping and a `term` query for exact identifiers.

### Assuming keyword search only finds identical strings

Full-text lexical search can tokenize, lowercase, stem, and apply synonyms. Exact match is a specific case.

### Assuming semantic search understands every synonym automatically

Embeddings depend on model, language, and domain. Evaluate on real queries.

### Using different embedding models at index time and query time

Vectors will no longer share the same space. Attach model/version metadata and re-embed when switching models.

### Mismatched dimensions

Query vectors must match mapping dimensions. Validate dimensions in the adapter.

### Choosing an unsuitable similarity metric

Cosine, dot product, and L2 have different semantics. Follow model guidelines and benchmark.

### Chunks too large or too small

Large chunks blur meaning; small chunks lose context and inflate vector counts. Evaluate chunk size/overlap.

### Not storing source IDs in chunks

Makes it impossible to group results, display sources, or delete/reindex cleanly. Store `articleId` and chunk metadata.

### Skipping filters in vector search

Can return unauthorized tenant/ACL data. Apply security filters across every retrieval branch.

### Adding BM25 and cosine scores directly

The two scores are on different scales. Use RRF, evaluated normalization, or a reranker.

### Using only semantic search for technical codes

Embeddings do not guarantee character-level distinction. Keep lexical exact matching.

### Not re-embedding when content changes

Stale vectors represent stale content. Regenerate embeddings in the update pipeline.

### Changing models without rebuilding vectors

Query and document vectors become incompatible. Version and migrate indexes.

### Measuring only latency without measuring relevance

Fast but wrong search still fails the goal. Use query sets with relevance labels.

### Evaluating with only one query group

Results may look great for natural-language questions yet fail for SKUs or proper names. Split evaluation by query group.

## 24. Search Implementation Workflow

When implementing search in Spring Data Elasticsearch:

1. Classify queries: exact identifier, full-text, natural-language, structured filter, or mixed.
2. Design `text`/`keyword` mappings for lexical search.
3. Choose analyzers suited to the language and domain.
4. Use BM25/full-text queries with clear field boosts and filters.
5. Select an embedding model compatible with the language and data.
6. Define the text to embed and chunking strategy.
7. Create a `dense_vector` mapping with matching dimensions/similarity.
8. Decouple `EmbeddingService` from repositories and version the model contract.
9. Generate query embeddings with a model compatible with document embeddings.
10. Use kNN with appropriate `k`, `num_candidates`, and filters.
11. Combine lexical and vector retrieval when both signals complement each other.
12. Use RRF or a reranker instead of adding raw scores.
13. Apply tenant/ACL filters in every search branch.
14. Plan re-embedding and reindexing when models or chunking change.
15. Evaluate Recall@k, Precision@k, and MRR/nDCG per query group.
16. Monitor latency, provider errors, vector index size, and embedding backlog.
17. Test exact identifiers, paraphrases, synonyms, filters, duplicate chunks, and model migrations.

## 25. Summary

Keyword search (lexical retrieval) relies on an inverted index, analyzers, tokens, and relevance scoring such as BM25. It fits keywords, proper names, product codes, APIs, error codes, and exact conditions. In Elasticsearch, full-text typically uses `text` fields with `match`/`multi_match`; exact matching and filtering typically use `keyword` fields with `term` queries.

Semantic search converts queries and documents into embedding vectors and finds nearest vectors using cosine, dot product, or L2. It can locate documents phrased differently yet sharing the same meaning. Quality depends on the model, language, chunking, preprocessing, dimensions, and candidate selection.

Hybrid search combines lexical and semantic retrieval to preserve keyword accuracy while expanding semantic recall. You can use RRF or reranking; avoid adding raw BM25 and vector scores arbitrarily. Spring Data Elasticsearch supports mappings/queries through repositories, `CriteriaQuery`, and `NativeQuery`; when newer vector/retriever APIs are not yet exposed by the abstraction, isolate the Elasticsearch Java API Client in a dedicated adapter.

Semantic search does not replace security filters or exact matching. Keep tenant/ACL/status filters in every branch, use lexical search for identifiers and numbers, version embedding models, re-embed when content or models change, and evaluate with labeled query sets. Only add semantic search when retrieval quality gains justify the embedding, vector index, and operational costs.

## References

- [Spring Data Elasticsearch – Query Methods and Repositories](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/repositories.html)
- [Spring Data Elasticsearch – NativeQuery API](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/client/elc/NativeQuery.html)
- [Spring Data Elasticsearch – Field Mapping API](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/annotations/Field.html)
- [Elasticsearch – Full-text search](https://www.elastic.co/guide/en/elasticsearch/reference/current/full-text-search.html)
- [Elasticsearch – Text field type](https://www.elastic.co/guide/en/elasticsearch/reference/current/text.html)
- [Elasticsearch – Keyword field type](https://www.elastic.co/guide/en/elasticsearch/reference/current/keyword.html)
- [Elasticsearch – Dense vector field type](https://www.elastic.co/guide/en/elasticsearch/reference/current/dense-vector.html)
- [Elasticsearch – kNN search](https://www.elastic.co/guide/en/elasticsearch/reference/current/knn-search.html)
- [Elasticsearch – Hybrid search and RRF](https://www.elastic.co/guide/en/elasticsearch/reference/current/rrf.html)
- [Elasticsearch – Semantic search](https://www.elastic.co/guide/en/elasticsearch/reference/current/semantic-search.html)
