# Preparing Vectors and Keeping Them Synchronized with Document Content

Semantic search in Spring Data Elasticsearch begins by transforming content into vector embeddings. Each vector is a numeric representation of text produced by an embedding model. Elasticsearch can compare these vectors to find passages that are close in meaning, even when they do not share the same keywords.

Search quality depends on the entire data preparation process. If the application embeds the wrong text, splits chunks inconsistently, uses mismatched models or dimensions, or leaves stale vectors behind after a document changes, nearest-neighbor results will no longer reflect the current content.

Therefore, vectors must be managed as a regenerable projection derived from source content. The application must know which content version, which model, and which chunking configuration produced a vector, and when it needs to be regenerated. This lesson explains how to prepare embedding inputs, split documents into chunks, store `dense_vector` fields, stay synchronized during document creation/updates/deletions, handle retries and model changes, and test the pipeline.

## 1. Vector Embeddings in Semantic Search

An embedding model accepts text and returns an array of floating-point numbers. Illustrative example:

~~~text
"Spring Data Elasticsearch supports vector search"
                  |
                  v
             Embedding model
                  |
                  v
[0.12, -0.08, 0.31, 0.44, ...]
~~~

Each vector has a fixed number of dimensions dictated by the model. A model might return 384, 768, 1024, or another size. The actual dimension count must come from the model contract; never guess or truncate a vector to make it fit a mapping.

In semantic search:

1. The application normalizes and splits content into appropriate units.
2. The embedding model generates a vector for each unit.
3. The application stores text, metadata, and vectors in Elasticsearch.
4. When a user searches, the same embedding model generates a vector for the query.
5. Elasticsearch compares the query vector against stored vectors and returns the nearest chunks.

A vector alone does not contain human-readable text. Store text and metadata alongside the vector so you can display results, trace back to source documents, and regenerate embeddings when needed.

## 2. Identifying the Authoritative Data Source

Elasticsearch should be treated as a search index or projection serving queries. The source of truth is typically the application's database, CMS, object store, or document repository.

For example, a document may look like:

~~~json
{
  "documentId": "guide-1001",
  "title": "Spring Data Elasticsearch",
  "body": "Document content...",
  "version": 17,
  "updatedAt": "2026-11-13T10:30:00Z"
}
~~~

From this record, the pipeline generates one or more chunks and vectors. Do not store content solely in Elasticsearch with no way to track the source version, model, or rules used to generate its vectors.

Keeping a source of truth enables:

- Rebuilding vectors if the index is lost.
- Re-embedding when the model changes.
- Re-running chunking when the segmentation strategy changes.
- Controlled handling of document updates/deletes.
- Comparing indexed content against current content.
- Recovering from errors or delayed events.

Each document should have a stable identifier and a monotonically increasing version or reliable revision token. Versions help detect stale events and prevent a slow job from overwriting newer results.

## 3. Preparing Text Before Calling the Embedding Model

Embeddings should be generated from the exact content users expect to find. Before calling the model, clearly define the text transformation steps.

A pipeline typically includes:

~~~text
Raw source
    |
    v
Extract text
    |
    v
Normalize content
    |
    v
Remove/transform unwanted markup
    |
    v
Split into chunks
    |
    v
Build embedding input
    |
    v
Embedding model
    |
    v
Vector + chunk metadata
~~~

### 3.1. Content Extraction

Documents can come from HTML, Markdown, PDF, DOCX, emails, or database records. Extraction should preserve important structure:

- Titles and headings.
- Paragraphs.
- Lists.
- Tables and column labels.
- Source code or configuration blocks.
- Meaningful captions and notes.
- Source paths or identifiers.

Do not flatten all extracted content into a single unstructured string. Headings and context help chunks remain meaningful when retrieved independently.

### 3.2. Normalizing Without Destroying Content

Normalization steps can include:

- Normalizing newlines and whitespace.
- Stripping markup that adds no search value.
- Preserving Vietnamese diacritics and proper Unicode.
- Standardizing character encoding.
- Removing repeated boilerplate when clear rules apply.
- Preserving code, API names, and exact identifiers when they matter.

Do not strip Vietnamese diacritics just to simplify embeddings. Do not lowercase all text if doing so loses semantics for codes, class names, or case-sensitive tokens. Embedding models often have their own preprocessing; the application should follow the model's guidelines and apply the exact same process to both documents and queries.

### 3.3. Separating Content from Metadata

Metadata such as `documentId`, `tenantId`, `sourceVersion`, access level, and timestamps should generally be stored in separate fields for filtering, sorting, or source lookup.

Only include metadata inside embedding text when it carries genuine semantic value. For example, a document title is often helpful when prepended to chunk text; an internal database ID usually does not help semantic similarity.

An embedding input can be constructed as:

~~~text
Document title: Spring Data Elasticsearch
Section: Vector search
Content: Elasticsearch stores dense vectors and supports kNN search...
~~~

Maintain a consistent `buildEmbeddingText` function and version this rule. If you change how title/heading/body are assembled, vectors must be regenerated because the model is receiving different input.

## 4. Splitting Documents into Chunks

A long document often exceeds an embedding model's input limit and is also not the best retrieval unit. Splitting documents into chunks keeps each embedding focused on a single topic and lets search return relevant passages instead of the entire document.

Example:

~~~text
Document: guide-1001
  Chunk 0: Introduction and concepts
  Chunk 1: Mapping configuration
  Chunk 2: Generating vectors
  Chunk 3: kNN querying
  Chunk 4: Updates and synchronization
~~~

### 4.1. Chunk by Structure Before Cutting by Size

If a document has headings and paragraphs, prioritize semantic boundaries:

1. Split by section or heading.
2. Keep the heading as context for child chunks.
3. Split overly long sections into smaller segments.
4. Avoid splitting mid-sentence, mid-table, or mid-code block whenever possible.
5. Preserve chunk order and position within the document.

Blindly slicing every 500 characters can cut sentences in half or separate explanations from their examples. Token-based chunking is generally a better fit when models enforce token-based input limits.

### 4.2. Chunk Size

There is no single optimal chunk size for every document type. Size depends on:

- The embedding model's token limit.
- Content length and structure.
- Typical user queries.
- Granularity needed at the passage level.
- Embedding cost and vector count.
- Storage and nearest-neighbor search costs.

Chunks that are too large can span multiple topics, making vectors less focused. Chunks that are too small can lose context and generate excessive vectors. Benchmark against a representative query set and evaluate retrieval quality.

### 4.3. Overlap

Adjacent chunks can overlap slightly to preserve context across boundaries.

Example:

~~~text
Chunk 0: tokens 0 - 400
Chunk 1: tokens 340 - 740
Chunk 2: tokens 680 - 1080
~~~

Overlap reduces the risk of splitting an important sentence in two, but increases embedded tokens, vector count, and duplicate context in results. Choose just enough overlap rather than applying a fixed rule blindly.

### 4.4. Preserving Section Context

Because a chunk is retrieved independently, it may need the document's title or heading. Example chunk text:

~~~text
Title: Spring Data Elasticsearch
Section: Keeping vectors synchronized
Content: When a source document changes, regenerate affected chunks...
~~~

Headings help the embedding capture what topic the chunk covers. However, do not repeat all metadata in every chunk if it inflates token costs without improving retrieval.

## 5. Designing Chunk Identity and Metadata

Each chunk needs a stable ID so the exact piece of data can be updated or deleted.

A document can be represented by separate Elasticsearch documents per chunk:

~~~json
{
  "chunkId": "guide-1001-v17-c03",
  "documentId": "guide-1001",
  "sourceVersion": 17,
  "chunkNumber": 3,
  "title": "Spring Data Elasticsearch",
  "section": "Keeping vectors synchronized",
  "content": "When a source document changes...",
  "embeddingModel": "embedding-model-v2",
  "embeddingVersion": 2,
  "contentHash": "sha256:...",
  "updatedAt": "2026-11-13T10:30:00Z"
}
~~~

Useful metadata:

- `documentId`: source document identifier.
- `chunkId`: chunk identifier.
- `sourceVersion`: revision of the source content.
- `chunkNumber` or ordinal: position within the document.
- `section`/`title`: context.
- `contentHash`: hash of the embedding input.
- `embeddingModel`: model that generated the vector.
- `embeddingVersion`: version of the preprocessing/chunking contract.
- `tenantId`/access metadata: access scope.
- `source URI`: link to the original document.
- `updatedAt`: timestamp when the projection was updated.

### 5.1. Choosing a Deterministic Chunk ID

An ID can be formed from document ID, version, chunking version, and ordinal:

~~~text
documentId + ":" + sourceVersion + ":" + chunkingVersion + ":" + chunkNumber
~~~

Or a hash of the canonical key if IDs get long. Stable IDs ensure retries overwrite the exact same chunk instead of creating duplicate documents.

If IDs are random UUIDs regenerated on every retry, the same chunk can appear multiple times. If IDs are based on ordinal alone while content shifts and chunks move, stale ordinals no longer used must be updated or deleted.

### 5.2. Content Hash

Compute the hash from the exact embedding input after normalization, combined with model/preprocessing version in the cache key:

~~~text
hashKey = SHA-256(
    modelVersion + "|" +
    preprocessingVersion + "|" +
    normalizedEmbeddingText
)
~~~

Hashes help:

- Skip embedding when input has not changed.
- Detect when chunk content changed.
- Reuse embedding caches when policy allows.
- Diagnose which content produced a given vector.

Hashes do not replace `sourceVersion`. Two revisions may differ in metadata while sharing text; conversely, the same `sourceVersion` should not be reused if content changed outside the contract.

## 6. Mapping `dense_vector` in Elasticsearch

Elasticsearch uses the `dense_vector` field type to store floating-point vectors. The mapping must declare dimensions matching the embedding model's output.

Example:

~~~http
PUT knowledge-chunks-v1
{
  "mappings": {
    "properties": {
      "chunkId": {
        "type": "keyword"
      },
      "documentId": {
        "type": "keyword"
      },
      "sourceVersion": {
        "type": "long"
      },
      "chunkNumber": {
        "type": "integer"
      },
      "title": {
        "type": "text"
      },
      "section": {
        "type": "keyword"
      },
      "content": {
        "type": "text"
      },
      "contentHash": {
        "type": "keyword"
      },
      "embeddingModel": {
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

In the example, `768` is illustrative. Replace it with the exact dimension count of the chosen model. You cannot write vectors whose element count differs from the declared `dims`.

Key properties:

- `dims`: number of vector dimensions.
- `index`: whether to build structures supporting approximate kNN, depending on version and configuration.
- `similarity`: similarity function used for vector search, such as `cosine`, `dot_product`, or `l2_norm`.
- `element_type`/`index_options`: additional options depending on Elasticsearch version and vector type.

For vectors indexed for kNN search, Elasticsearch can construct approximate nearest-neighbor structures such as HNSW. Enabling `index` increases storage and indexing overhead while enabling more efficient search at suitable scale.

### 6.1. Choosing Similarity Consistently

Common options:

- `cosine`: compares the angle between two vectors.
- `dot_product`: inner product; requires vector normalization per the field/model contract in standard float configurations.
- `l2_norm`: Euclidean distance.
- `max_inner_product`: suitable for certain models/training objectives.

Do not pick a similarity metric merely because its name sounds familiar. Use the metric recommended by the model provider and ensure query vectors are generated using the same model, preprocessing, and normalization rules.

Do not mix vectors from two different models just because they share the same dimensions. Their embedding spaces may be completely different.

### 6.2. Unindexed Vectors

Some workflows only need to store vectors for computation or scripts without an approximate kNN index. In that case, the mapping can leave vector indexing disabled if supported by the version. Access patterns and costs differ from indexed vectors; clarify the use case before choosing.

## 7. Spring Data Elasticsearch Entity for Chunks

A chunk can be mapped as an entity:

~~~java
import java.time.Instant;

import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "knowledge-chunks-v1")
public class KnowledgeChunk {

    @Id
    private String chunkId;

    @Field(type = FieldType.Keyword)
    private String documentId;

    @Field(type = FieldType.Long)
    private Long sourceVersion;

    @Field(type = FieldType.Integer)
    private Integer chunkNumber;

    @Field(type = FieldType.Text)
    private String title;

    @Field(type = FieldType.Keyword)
    private String section;

    @Field(type = FieldType.Text)
    private String content;

    @Field(type = FieldType.Keyword)
    private String contentHash;

    @Field(type = FieldType.Keyword)
    private String embeddingModel;

    private float[] embedding;

    @Field(type = FieldType.Date)
    private Instant updatedAt;

    // constructors, getters and setters
}
~~~

Annotation-based vector mapping can differ across Spring Data Elasticsearch versions. Some versions support `FieldType.Dense_Vector` and corresponding vector attributes; others may require explicit mapping via `IndexOperations` or JSON mappings.

Do not assume a `float[]` automatically maps to `dense_vector` in every version. Check the Javadoc and actual mapping on the cluster. If annotations cannot express all `dims`/`similarity`/`index` options, create the mapping explicitly before indexing data.

### 7.1. Creating Indexes and Mappings Explicitly

Spring Data Elasticsearch provides `IndexOperations` to manage indexes:

~~~java
IndexOperations indexOperations =
    operations.indexOps(KnowledgeChunk.class);

if (!indexOperations.exists()) {
    indexOperations.create();
    indexOperations.putMapping(
        indexOperations.createMapping()
    );
}
~~~

This snippet illustrates the general lifecycle. If vector mappings are managed via separate JSON, create the index with those settings and mappings via the corresponding API, then verify the mapping using `GET index/_mapping`.

Do not let a production application auto-create an index with a default mapping of wrong `dims` and only discover it when writing vectors. Mappings should be provisioned before ingestion.

## 8. Calling the Embedding Model in Batches

Embedding models incur network/compute cost. Sending chunks one by one can inflate latency and overhead. If the provider supports batch embeddings, group multiple inputs into a single request within token and item limits.

An application interface can be defined as:

~~~java
public interface EmbeddingService {

    int dimensions();

    String modelVersion();

    Mono<List<float[]>> embed(List<String> inputs);
}
~~~

This is an illustrative interface. For imperative applications, return `List<float[]>` directly; for reactive services, return `Mono`/`Flux` per contract.

A chunk-embedding service:

~~~java
public Mono<List<EmbeddedChunk>> embedChunks(
        List<TextChunk> chunks) {

    List<String> inputs = chunks.stream()
        .map(TextChunk::embeddingText)
        .toList();

    return embeddingService.embed(inputs)
        .map(vectors -> {
            if (vectors.size() != chunks.size()) {
                throw new IllegalStateException(
                    "Embedding count does not match chunk count"
                );
            }

            List<EmbeddedChunk> result = new ArrayList<>();

            for (int i = 0; i < chunks.size(); i++) {
                float[] vector = vectors.get(i);

                if (vector.length != embeddingService.dimensions()) {
                    throw new IllegalStateException(
                        "Unexpected embedding dimensions"
                    );
                }

                result.add(
                    new EmbeddedChunk(chunks.get(i), vector)
                );
            }

            return result;
        });
}
~~~

Validate response count, dimensions, finite values, and vector alignment with inputs. If the provider returns vectors in input order, preserve positional mapping. If the response includes an input index, use that index rather than relying on implicit order.

### 8.1. Validating Vectors Before Saving

Before indexing:

- Element count matches `dims`.
- No `NaN` or `Infinity` values.
- Vector is non-empty.
- Norm matches metric/model expectations.
- Model version is accurate.
- Embedding input hash matches metadata.
- Chunk text and vector belong to the same `sourceVersion`.

A malformed vector can cause a bulk item failure or silently degrade search quality without an obvious error.

## 9. Ingestion Pipeline from Content to Vector

A pipeline can be divided into independent steps:

~~~text
Document source
      |
      v
Read current revision
      |
      v
Extract + normalize text
      |
      v
Split into chunks
      |
      v
Compute chunk IDs + content hashes
      |
      v
Reuse unchanged embeddings
      |
      v
Generate missing embeddings
      |
      v
Validate vectors
      |
      v
Bulk index chunk documents
      |
      v
Remove stale chunks
      |
      v
Record indexed source version
~~~

Each step should have clear inputs/outputs and be safe to retry.

Do not mark a document as successfully indexed until all required chunks have been written. If the embedding provider fails mid-way, preserve job state to resume without creating duplicates.

### 9.1. Separating Extraction, Chunking, and Embedding

Do not cram all logic into a single persistence callback when the workflow involves I/O, model calls, or complex retries.

You can structure components as:

- `DocumentExtractor`: reads source content.
- `TextNormalizer`: normalizes text.
- `Chunker`: generates chunks and metadata.
- `EmbeddingService`: calls the model.
- `VectorDocumentMapper`: builds entities/documents.
- `VectorIndexer`: bulk-writes to Elasticsearch.
- `SyncCoordinator`: manages versions, retries, and state.

Separating components allows testing each part independently and swapping models/chunkers without touching source repository logic.

## 10. When Document Content Changes

A change to a source document can cause:

- Content of one or more chunks to change.
- The number of chunks to increase or decrease.
- Chunk order to change.
- Title/headings to change.
- Embedding input to change even if the body looks nearly identical.
- Access permissions or tenant metadata to change.

Therefore, never update only a `content` field while keeping the old vector. The old vector describes the old text and will produce inaccurate search results.

Update workflow:

1. Detect the new source revision.
2. Read the latest canonical content.
3. Normalize and chunk using the current chunker version.
4. Compute chunk IDs and content hashes.
5. Reuse vectors only when both input hash and model contract still match.
6. Generate embeddings for new/modified chunks.
7. Validate all vectors to be written.
8. Index new or updated chunks.
9. Delete stale chunks that no longer exist.
10. Record the synchronized revision.
11. Refresh according to read-after-write requirements and application policy.

### 10.1. Re-embedding Only Modified Chunks

If a document has 100 chunks and only one section changes, you can generate embeddings solely for the affected chunks.

To achieve this, you need stable chunking and content hashes. If editing one paragraph shifts ordinals for all subsequent chunks, hashes indicate which content actually changed even if ordinal-based IDs shifted.

One option is IDs based on content/section hashes, though two identical chunks in the same document must be handled. Another option is IDs based on document + generation + ordinal, comparing hashes to decide whether re-embedding is needed.

Choose a strategy based on chunker stability, deduplication needs, and update/delete behavior.

### 10.2. Deleting Leftover Chunks

If an old document had 8 chunks and the new version has only 6, the last two chunks must be deleted. Upserting only the first 6 chunks leaves the two stale chunks behind, where they can continue appearing in semantic search.

You can store the current list of chunk IDs in source metadata or query by `documentId`/`sourceVersion` to identify stale chunks. Delete-by-query can be convenient but requires watching cost and async behavior; deleting by explicit IDs is usually easier to control when the list is known.

## 11. Staying Synchronized with Events / Outbox

A request that updates the database and then synchronously calls the embedding provider and Elasticsearch can fail partway through:

~~~text
Database commit succeeds
        |
        v
Embedding provider timeout
        |
        v
Elasticsearch not updated
~~~

The source data has changed while the search index remains stale. If the API returns an error and the caller retries the entire transaction, unwanted side effects can occur.

A reliable pattern is the transactional outbox:

1. Within the same database transaction, update the document and write an outbox event.
2. A worker reads the event and processes it asynchronously.
3. The worker fetches the latest canonical content.
4. Generates chunks/vectors.
5. Writes to Elasticsearch.
6. Marks the event complete only after the projection is written successfully.

Diagram:

~~~text
Application
    |
    v
Database transaction
    |                 |
    | update document |
    | write outbox    |
    v                 v
Commit atomically
        |
        v
Outbox worker
        |
        v
Extract -> Chunk -> Embed
        |
        v
Elasticsearch bulk index
        |
        v
Mark event processed
~~~

An outbox does not turn embedding and Elasticsearch into a distributed transaction. It guarantees pending work events are not lost upon database commit; the worker still requires retries, idempotency, and reconciliation.

If using a message broker, you can publish outbox events to the broker and have consumers update the vector index. Ensure acknowledgment occurs only after projection completion or after work is durably persisted to a retry queue.

## 12. Handling Out-of-Order Events

Suppose a document has versions 20 and 21:

~~~text
Event v20 starts embedding, processes slowly
Event v21 starts later, completes first
Event v20 finishes last
~~~

If the v20 worker writes after v21 without checking versions, newer vectors can be overwritten by stale content.

Store `sourceVersion` and check versions before writing or publishing sync status. Strategies include:

- Serializing processing per `documentId`.
- Partitioning queues by `documentId`.
- Reading the canonical latest revision right before indexing.
- Skipping jobs whose version is older than the current version.
- Using external versioning or compare-and-set mechanisms suited to the write API.
- Storing `indexedVersion` to track which revision is in Elasticsearch.

Re-reading the latest source reduces stale event processing, though races between read and write still require handling. If strictness is required, use version conditions at the storage layer or a per-document coordinator.

Do not rely solely on timestamps, as clocks can drift and two events may share the same timestamp. Monotonically increasing revisions/sequences are more reliable.

## 13. Avoiding Half-Old Half-New State During Multi-Chunk Updates

Elasticsearch does not provide atomic transactions across all chunks of a document. When writing 10 chunks, some items can succeed while others fail.

Define a consistency contract:

- Eventual consistency: brief periods with mixed old and new chunks are acceptable.
- Per-document consistency: expose the new generation only once all new chunks are ready.
- Strong read-after-write: requires an additional coordinator/architecture to confirm completion only after projection and refresh satisfy requirements.

A generation strategy:

1. Generate a new generation ID for the document.
2. Index all new chunks with that generation ID.
3. Verify all items succeeded.
4. Update the active generation state in the source of truth/coordinator.
5. Queries accept only the active generation.
6. Clean up older generations once no longer needed.

Design how queries learn the active generation. You can use metadata synchronized through an accessible store or a publish step suited to the workload. If updating a marker on every chunk is required, that operation is also non-atomic; do not assume a bulk update performs an atomic switch.

For many systems, eventual consistency paired with reconciliation is simpler and more practical. Document these boundaries in APIs and operations.

## 14. Deleting Documents and Associated Vectors

When a source document is deleted, all of its vector chunks must be deleted or marked unavailable.

A delete event should carry:

- `documentId`.
- `sourceVersion`/tombstone version.
- `tenantId` if applicable.
- `eventId`.
- Deletion timestamp.

The worker deletes chunks by `documentId` or a list of chunk IDs. If using delete-by-query, monitor document counts and task status. If a document has thousands of chunks, deletion operations also need retries and observability.

### 14.1. Tombstones to Prevent Old Events from Resurrecting Data

A dangerous scenario:

1. Document is deleted at version 30.
2. Delete event is processed and chunks are deleted.
3. An old embedding job for version 29 finishes late.
4. The stale job re-indexes chunks and makes the document reappear.

Use tombstones/versions to reject any job with a version less than or equal to the deletion revision. Retain deletion state longer than the maximum retry/event replay window; do not purge tombstones prematurely if stale events can still arrive.

### 14.2. Deletion and Privacy

If a document contains data subject to privacy deletion requirements, identify every place content/vectors/caches/backups are stored. Deleting an Elasticsearch document does not automatically delete the source of truth, outbox payloads, embedding caches, or backups.

Vectors are derived from content and can still carry sensitive information. Apply retention, access control, and deletion policies to the vector index as well.

## 15. Retries and Idempotency in the Embedding Pipeline

Steps can fail independently:

- Reading source data.
- Extracting content.
- Calling the embedding provider.
- Validating vectors.
- Bulk writing.
- Deleting stale chunks.
- Updating `indexedVersion`.

Design each step to be retryable.

### 15.1. Embedding Requests

If a provider times out, you may not know whether the request was processed. Re-sending the same input usually does not mutate source data, though it may incur inference cost again.

Use a cache key based on model version, preprocessing version, and content hash to avoid re-embedding unchanged content. Do not assume the provider offers exactly-once execution.

### 15.2. Elasticsearch Upserts with Stable IDs

Indexing chunks with deterministic IDs and identical payloads simplifies retries:

~~~http
PUT knowledge-chunks-v1/_doc/guide-1001-v17-c03
{
  "documentId": "guide-1001",
  "sourceVersion": 17,
  "chunkNumber": 3,
  "contentHash": "sha256:...",
  "content": "When a source document changes...",
  "embeddingModel": "embedding-model-v2",
  "embedding": [0.12, -0.08, 0.31]
}
~~~

If the same ID and payload are re-sent, document state converges to the same value. However, if a newer writer updates the same ID while an older retry is in flight, the stale payload could overwrite it. Therefore, stable IDs must be paired with version guards.

### 15.3. Bulk Partial Failures

A bulk request can return some succeeded items and some failed items. Inspect each item, retry recoverable subsets, and route permanent failures to a retry/dead-letter queue.

Do not blindly retry the entire batch. When retrying, preserve chunk ID, `sourceVersion`, `contentHash`, and model version so the operation remains traceable.

### 15.4. Backoff and Retry Budgets

Use exponential backoff with jitter for transient errors such as 429 or certain 5xx responses. Cap retry attempts, job lifetime, and concurrency. Mapping/dimension mismatch errors are data or configuration errors; endless retries will not fix them.

Once the retry budget is exhausted, move the job to a failed/quarantine state that can be replayed after fixing the root cause.

## 16. Model Versions and Changing Embedding Models

Embedding models may be upgraded, switched across providers, or paired with changed preprocessing. Vectors from different models should not be compared directly merely because they share dimensions.

Store metadata:

- Model name/identifier.
- Model version.
- Output dimensions.
- Similarity metric.
- Preprocessing version.
- Chunking version.
- Creation timestamp.

If the model or embedding text builder changes, re-embedding is required. Migrations can follow:

1. Create a new index or new vector field for the new model version.
2. Keep the old index serving queries during backfill.
3. Reprocess source documents in batches.
4. Validate dimensions and retrieval quality.
5. Run shadow queries or compare results.
6. Cut traffic over to the new index/model.
7. Maintain a rollback window.
8. Retire old indexes/vectors according to retention policy.

Do not mix vectors from old and new models in the same kNN candidate set if they belong to two different embedding spaces. If hybrid search across generations is required, filter by model version or query each index separately and merge results using an evaluated strategy.

## 17. Chunking Version Is Also Part of the Schema

Changing chunk size, overlap, heading inclusion, or normalization alters embedding inputs. Thus, chunking configuration must be versioned.

Example:

~~~json
{
  "documentId": "guide-1001",
  "sourceVersion": 17,
  "chunkingVersion": "section-token-v3",
  "embeddingModel": "embedding-model-v2",
  "embeddingVersion": 2
}
~~~

If you change the chunker without updating metadata, it becomes difficult to know which vectors need regeneration. You can store versions in document fields or index names.

When changing the chunker:

- Generate a new chunk set.
- Compare chunk counts and sizes.
- Evaluate retrieval metrics.
- Reindex/re-embed.
- Remove old chunks once the new generation is ready.
- Do not let two chunking versions mix without queries filtering or understanding the semantics.

## 18. kNN Querying with Vectors from the Same Model

When a user submits a query, the application must use the exact same model and preprocessing contract to generate the query vector.

kNN DSL example:

~~~http
POST knowledge-chunks-v1/_search
{
  "knn": {
    "field": "embedding",
    "query_vector": [0.12, -0.08, 0.31],
    "k": 10,
    "num_candidates": 100
  },
  "_source": [
    "documentId",
    "chunkId",
    "title",
    "section",
    "content",
    "sourceVersion"
  ]
}
~~~

The vector in the example is shortened for illustration; actual requests must supply the full dimension count. `k` is the desired result count, and `num_candidates` affects the trade-off between recall and compute cost in approximate search.

If filtering by tenant, ACL, or document status, place filters inside the kNN query according to your Elasticsearch version's semantics to avoid returning unauthorized content. Distinguish pre-filter from post-filter because they can yield different results and recall.

### 18.1. Query Vectors Must Not Use a Different Model

If document vectors were generated with `embedding-model-v2`, query vectors must be generated with a compatible model and preprocessing. Using another model can produce vectors of identical `dims` whose coordinates do not share a semantic space.

Do not grab a stored vector from a document as a query vector unless the application explicitly verifies its model/version.

### 18.2. Hybrid Search

Semantic search can be combined with BM25 full-text search. Hybrid search helps when queries contain codes, API names, or exact keywords that embeddings do not always preserve.

You can:

- Run lexical and vector queries separately.
- Combine via reciprocal rank fusion or a suitable ranking mechanism.
- Apply shared filters for tenant/access.
- Evaluate results against a query set with relevance labels.

Do not assume vector search completely replaces lexical search. The two search methods complement each other.

## 19. Keeping Vectors Synchronized When Metadata Changes

Not every metadata update requires generating new embeddings.

Examples:

| Changed field | Re-embed needed? |
|---|---|
| Chunk content | Yes |
| Title concatenated into embedding input | Yes |
| Heading concatenated into embedding input | Yes |
| Chunking config | Yes |
| Embedding model/version | Yes |
| Tenant ID | No, if used only as metadata filter; but permissions must be updated |
| ACL/access level | No, if excluded from embedding text; must sync immediately to protect data |
| `UpdatedAt` | Usually no |
| Display URL | Usually no |
| Chunk ordinal | Depends on identity/chunking; verify chunk mapping |

The rule is to re-embed whenever embedding input or the embedding contract changes. However, filter metadata and access permissions must still be synced immediately even when vectors remain unchanged.

If `title` is included in embedding input, changing `title` must generate a new vector. If `title` is only for display, no re-embedding is needed.

## 20. Refresh and Read-After-Write

After indexing chunks, documents may not appear immediately in search because Elasticsearch refreshes periodically. Index API success does not automatically mean search sees the document immediately.

Refresh policies:

- Use default refresh for regular ingest throughput.
- Use `refresh=wait_for` when waiting for the next refresh cycle in a read-after-write workflow.
- Use `refresh=true` only when immediate visibility is genuinely required and its cost is understood.
- For large bulk imports, avoid `refresh=true` on every batch unless needed.

In Spring Data, refresh policies can be configured on operations or requests depending on version. Check the current API and choose an appropriate policy.

Do not confuse "written successfully" with "already searchable". Track both milestones separately if business requirements demand it.

## 21. Synchronizing Access Permissions and Tenant Metadata

Semantic search can return sensitive text passages. Security filters must be enforced before results are returned to users.

Each chunk should carry the necessary metadata:

- `tenantId`.
- Visibility/access level.
- Owner or ACL reference.
- Document status.
- Deleted/tombstone state if used.
- `sourceVersion`.

Queries must combine kNN with tenant/ACL filters as supported by your Elasticsearch version. Do not merely filter results after returning them to the application if doing so risks exposing content in logs, traces, or internal responses.

When ACLs change, update metadata across all related chunks or rely on a trustworthy authorization lookup. Never leave stale permissions in the vector index after access was revoked at the source.

## 22. Testing the Vector Generation Pipeline

Separate tests by responsibility.

### 22.1. Unit Testing Normalization and Chunking

Verify:

- Unicode/Vietnamese diacritics are preserved properly.
- Headings are prepended to chunks per contract.
- Code blocks/tables are not split destructively when structure-preserving rules apply.
- Chunk sizes remain within token limits.
- Overlap matches configuration.
- Chunk order is deterministic.
- Identical inputs and configs produce identical chunk IDs/hashes.

### 22.2. Unit Testing the Embedding Adapter

Use a fake embedding provider to verify:

- Vector count matches input count.
- Input/output positional mapping matches.
- Dimensions are exact.
- No `NaN`/`Infinity` values appear.
- Timeouts and provider errors propagate properly.
- Batches are split according to limits.
- Cache never returns vectors from another model version.

Do not call the production model in every unit test. Use deterministic fixture vectors to test mapping and query orchestration.

### 22.3. Integration Testing Mappings

Against a test Elasticsearch instance:

1. Create an index with the right `dense_vector` `dims` and `similarity`.
2. Index chunks with valid vectors.
3. Verify the mapping.
4. Send a kNN query with a vector of matching `dims`.
5. Confirm matching documents are returned.
6. Test a vector with wrong `dims` and verify rejection.
7. Test tenant/ACL filters.
8. Read back chunks to confirm metadata and text.

Vector indexing configuration and kNN can differ across Elasticsearch versions. Integration tests must run against a version matching production.

## 23. Testing Update, Delete, and Retry Synchronization

Scenarios to cover:

| Scenario | Expected outcome |
|---|---|
| Create new document | All chunks and vectors created |
| Replay same event | No duplicate chunks created |
| Edit one section | Modified chunks are re-embedded |
| Edit title included in embedding input | Chunks depending on title receive new vectors |
| Chunk count decreases | Stale leftover chunks are deleted |
| Provider timeout | Job retries, source/index state tracked |
| Bulk partial failure | Only recoverable failed items retried |
| Stale version event arrives late | Does not overwrite newer revision |
| Delete document | All chunks deleted/hidden |
| Delete event arrives before stale job | Stale job does not resurrect document |
| Change embedding model | New vectors generated with controlled migration |
| ACL revoked | Search does not return stale chunks with revoked access |
| Refresh has not occurred yet | Read-after-write behavior matches contract |

An important update test is verifying old vectors are no longer used after content changes. You can use a fake embedding model returning distinct vectors per input to make this easy to observe.

## 24. Observing and Operating the Pipeline

Useful metrics:

- Documents pending embedding.
- Chunks generated.
- Tokens/input size sent to the model.
- Embedding latency and error rate.
- Provider rate limits / 429s.
- Vector dimension mismatches.
- Bulk item successes/failures.
- Stale chunks deleted.
- Retried/dead-lettered jobs.
- Lag from source commit to searchable.
- Documents where `indexedVersion` < `sourceVersion`.
- Index size, vector index build time, and kNN latency.

Logs should include `documentId`, `sourceVersion`, `chunkId`, model version, batch ID, and correlation ID. Avoid logging full content or full vectors in production unless necessary.

A reconciliation job can periodically compare `sourceVersion` against `indexedVersion` to catch missed documents. It can also inspect expected chunk counts, content hashes, and model/chunking versions to detect projection drift.

## 25. Common Pitfalls

| Symptom | Possible cause | Resolution |
|---|---|---|
| Error when indexing vectors | Vector length differs from `dims` | Check model dimensions and mapping |
| kNN returns irrelevant results | Query vector from a different model | Keep model/preprocessing contract identical |
| Updated content still returns old matches | Vectors were not regenerated | Re-embed modified chunks |
| Duplicate documents in results | Unstable chunk IDs or retries creating new IDs | Use deterministic IDs and upserts |
| Stale chunks still appear | Leftover chunks not deleted after update | Track chunk sets and delete stale IDs |
| Old job overwrites newer job | Missing `sourceVersion` check | Version guards and per-document ordering |
| Deleted document reappears | Stale job completes after deletion | Tombstones and rejecting stale versions |
| Partial bulk writes | Item-level failures ignored | Inspect per-item responses and retry subset |
| Embedding cost spikes unexpectedly | Re-embedding all chunks despite unchanged input | Content hashing and embedding cache |
| New model yields poor results | Mixed model version vectors or skipped reindex | Separate generations/indexes and re-evaluate |
| Query vector has wrong dimensions | Model/query adapter out of sync with index | Validate dimensions before querying |
| Newly written chunks missing in search | Index not refreshed yet | Choose refresh policy based on requirements |
| Cross-tenant document leak | Missing tenant/ACL filter in vector search | Enforce access filters inside queries |
| Chunk count grows rapidly | Chunks too small or excessive overlap | Benchmark chunk size/overlap |
| Reindexing causes downtime | Migration lacks generation/alias plan | Backfill, validate, and perform controlled cutover |

## 26. End-to-End Implementation Workflow

An actionable workflow:

1. Select an embedding model and record model version, dimensions, and metric.
2. Identify the source of truth and source revision.
3. Define text extraction, normalization, and embedding input.
4. Design chunking around structure, token limits, and query patterns.
5. Generate deterministic chunk IDs and content hashes.
6. Create a `dense_vector` mapping with appropriate `dims`/`similarity`/`index_options`.
7. Create the index before ingestion.
8. Batch-embed and validate vectors.
9. Bulk-index chunks with metadata/version.
10. Inspect item-level bulk responses.
11. Delete stale chunks after new chunks are written successfully.
12. Use an outbox/event worker to keep source and search projection synchronized.
13. Protect updates/deletes with version guards and tombstones.
14. Configure retry/backoff, idempotency, and dead-letter handling.
15. Synchronize tenant/ACL metadata.
16. Set refresh policy according to the read-after-write contract.
17. Evaluate retrieval quality and latency.
18. Monitor backlog, `indexedVersion`, and errors for reconciliation.

## 27. Quick Reference

| Need | Approach |
|---|---|
| Convert text to vectors | Embedding model with a fixed contract |
| Preserve long document context | Section/token chunking with controlled overlap |
| Store vectors | `dense_vector` with matching `dims` |
| Find nearest neighbors | kNN query using query vector from the same model |
| Track vector provenance | `documentId`, `sourceVersion`, model/chunking versions |
| Detect content changes | Content hash and source revision |
| Retry without duplicates | Deterministic chunk ID and upsert |
| Re-embed only changed parts | Compare embedding input hashes |
| Remove stale chunks | Track chunk IDs and delete stale chunks |
| Reject stale events | Version guards and tombstones |
| Avoid losing update events | Transactional outbox or durable queue |
| Change models | Re-embed and index/generation migration |
| Sync access permissions | `tenant`/ACL metadata and filters |
| Validate vector writes | Dimensions, finite values, model version |
| Ensure search visibility | Suitable refresh policy |
| Detect index drift from source | `sourceVersion`/`indexedVersion` reconciliation |

Vectors accurately reflect content only when embedding input, chunking, and model contracts are managed consistently. Maintain an authoritative source of truth, assign stable chunk identities, store `sourceVersion`/`contentHash`/`modelVersion` alongside `dense_vector`, and validate dimensions before indexing. When documents change, regenerate vectors for affected chunks and delete stale ones; when documents are deleted, use tombstones/versions so stale jobs cannot resurrect data. Transactional outbox, bounded retries, bulk item handling, and reconciliation keep the search projection aligned with the source in asynchronous environments. When changing models or chunking, build a new generation/index, re-embed, and shift traffic only after validating quality.
