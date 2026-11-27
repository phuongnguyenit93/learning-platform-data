# vector and Version-Specific Additional Types in Apache Cassandra

Apache Cassandra's type system is not an immutable list across all releases. A CQL statement valid in Cassandra 5.0 may fail to parse in Cassandra 4.1, or may be implemented with different limits in another distribution. A prime example is **`vector`**: a **fixed-dimension** data type introduced in the **Apache Cassandra 5.0** line to store numeric vectors and support *vector similarity search* when paired with a **Storage-Attached Index (SAI)**.

This lesson belongs to the **Data Types** chapter of the **DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA** module. In a distributed wide-column system, clearly separate three layers: **whether the cluster version supports the CQL type**, **whether queries have an appropriate access path**, and **whether the Java Driver has compatible codecs and APIs**. With vectors, this separation is especially critical: being able to store a vector **does not mean** you can query millions of vectors by similarity, and ANN does not share the same properties as an exact partition-key lookup.

## 1. Why Check Versions Before Choosing a Type?

A data design rolls out simultaneously across multiple components: Cassandra cluster nodes, Java driver, migration tools, cqlsh, embedding pipelines, index libraries, and operational runbooks. If even one component lacks support for a new type, deployment can halt at `CREATE TABLE`, or the application can fail with codec errors when binding data.

Guidance table:

| Environment | Vector-Related Capability | Practical Decision |
|---|---|---|
| **Apache Cassandra 3.x / 4.0 / 4.1** | Lacks Cassandra 5.0 CQL `vector` type and SAI/ANN vector search | Do not deploy `vector<float,n>` schemas directly; upgrade or choose an alternative |
| **Apache Cassandra 5.0** | Includes CQL `vector`, SAI, and ANN syntax per release capabilities | Verify exact patch release, dimension caps, indexing, and query constraints |
| **CQL-compatible distribution / managed service** | May support vectors with different syntax, limits, metrics, or lifecycle | Read documentation for the **exact product and version**, do not infer from the Cassandra name |
| **Older Java Driver 4.x** | May lack `CqlVector`/matching codecs or have different APIs | Check dependencies; upgrade the driver when required by features |
| **Apache Cassandra Java Driver 4.17+**, e.g., 4.19.x | Provides `CqlVector`, `setVector`, `getVector` per version | Use the matching artifact/version and test against the target cluster |

Command to check server version when system table access is available:

~~~cql
SELECT release_version
FROM system.local;
~~~

This result reflects **only the node answering the query**. During a rolling upgrade of a multi-node cluster, verify capabilities and readiness across **the entire cluster** before running schema migrations using new types. Operational tooling can assist, but never treat one node reporting `"5.0"` as proof that all nodes are ready.

To verify the Java client, inspect **the actual dependencies packaged and executed at runtime**, rather than relying on versions shown in examples. When multiple Java services share a keyspace, every service reading or writing new columns needs a compatibility and rollout plan.

**Principle:** never write a schema "valid in the latest docs" and deploy it blindly to an older cluster. Lock minimum versions, limits, and verified behaviors into your design, tests, and migration plan.

## 2. What Is CQL vector?

CQL `vector<T, N>` represents a **fixed sequence of exactly N elements**, all of **type T**, with **no NULL elements allowed**. A vector is read and written as a **monolithic value**; it is not a non-frozen collection allowing individual element updates.

Example:

~~~cql
CREATE TABLE sample_vectors_by_id (
    sample_id uuid PRIMARY KEY,
    sensor_values vector<int, 3>,
    embedding vector<float, 3>
);
~~~

Here:

- `sensor_values vector<int,3>` stores three integers. According to Apache Cassandra 5.0 vector documentation, `vector` can hold other element types, yet **SAI/ANN vector search is specifically for `float` vectors**.
- `embedding vector<float,3>` holds exactly **three 32-bit floats** per row. This is a practice example; real embedding models usually have **many more dimensions**.
- `sample_id uuid` remains the **partition key** for exact ID lookups. Adding a vector column does not change how Cassandra hashes the partition key or replicates data.

~~~cql
INSERT INTO sample_vectors_by_id (sample_id, sensor_values, embedding)
VALUES (
    11111111-1111-4111-8111-111111111111,
    [10, 20, 30],
    [0.12, 0.34, 0.56]
);

SELECT sensor_values, embedding
FROM sample_vectors_by_id
WHERE sample_id = 11111111-1111-4111-8111-111111111111;
~~~

Like list literals, **vector literals** use square brackets, e.g., `[0.12, 0.34, 0.56]`. However, **`vector<float,3>` is not an alias for `list<float>`**.

### 2.1. Comparing vector with list, tuple, and blob

| Feature | `vector<float,3>` | `list<float>` | `tuple<float,float,float>` | `blob` |
|---|---|---|---|---|
| Element count | **Fixed at 3** | Variable | Fixed by tuple schema | No CQL element count |
| NULL elements | **No** | Avoid NULL elements as normal members | Positional NULLs permitted where appropriate | Arbitrary bytes |
| Individual position updates | **No** | Some index-based mutations | No, tuples are always frozen | No, write new bytes |
| Dimension semantics | **Enforced by the type** | No N constraint from type | Positional count, not meant for ANN | Application-defined |
| Usable for SAI/ANN vector search | **Yes**, when elements are float and deployment supports it | Not an ANN vector column | Not an ANN vector column | Not an ANN vector column |
| Java Driver | `CqlVector<Float>` | `List<Float>` | `TupleValue` | `ByteBuffer` |

Vectors enforce **exact dimension and element type**, not whether the numbers make semantic sense. A vector `[0.12,0.34,0.56]` is meaningless unless you know which model produced it, in which embedding space, and under which metric.

### 2.2. Wrong Dimensions and Monolithic Updates

Suppose a column is `vector<float,3>`:

~~~cql
-- Correct dimension count:
UPDATE sample_vectors_by_id
SET embedding = [0.10, 0.20, 0.30]
WHERE sample_id = 11111111-1111-4111-8111-111111111111;
~~~

The following violate type rules:

~~~cql
-- Invalid: missing one dimension.
-- UPDATE sample_vectors_by_id
-- SET embedding = [0.10, 0.20]
-- WHERE sample_id = 11111111-1111-4111-8111-111111111111;

-- Invalid: null element.
-- UPDATE sample_vectors_by_id
-- SET embedding = [0.10, null, 0.30]
-- WHERE sample_id = 11111111-1111-4111-8111-111111111111;

-- Not a valid vector mutation:
-- UPDATE sample_vectors_by_id
-- SET embedding[0] = 0.10
-- WHERE sample_id = 11111111-1111-4111-8111-111111111111;
~~~

To change one coordinate, the application builds a **complete vector value** and updates the entire column. Never treat `vector` as a per-element change log or a list for appending dimensions.

A vector column **can remain unwritten** or be deleted as a column where CQL allows; what is forbidden is **NULL inside its elements**. Distinguish "an unwritten embedding column" from "an embedding containing a null element."

### 2.3. Dimension Limits Depend on Version and Distribution

**Apache Cassandra 5.0** vector documentation specifies an **8K (2¹³ = 8192) dimension** limit for the vector type. Some CQL-compatible products/distributions document different caps. Therefore:

- Explicitly record the **Apache Cassandra 5.0 release, build, patch**, or exact product in your design.
- Never assume "every Cassandra supports 65,535 dimensions" or "every service caps at exactly 8,192" based on docs from another release.
- Choose practical dimensions from your **embedding model** and index/runtime capacity, not just parser limits.
- For `vector<float,1536>`, raw float payload alone is **1536 × 4 = 6144 bytes** before metadata, indexing, compression, and replication overhead; higher dimensions raise network, disk, RAM, and ANN costs.

A `CREATE TABLE` succeeding does not prove a workload of 1 million × 8,192-dimension vectors will meet SLAs.

## 3. Embeddings: Vectors Have Meaning Only When Tied to a Model

An **embedding** is a numeric vector produced by a machine learning model transforming text, images, audio, or entities into a feature-space representation. Vectors close under the chosen metric often reflect similarity useful for the trained task.

Practical examples:

- Learning platforms: finding document passages semantically related to a learner's question.
- E-commerce: recommending products with similar descriptions.
- Image systems: finding visually similar images.
- Incident analysis: finding bug reports resembling previously resolved incidents.

**CQL does not generate embeddings.** Cassandra stores and searches vectors **generated by applications or AI services**. Model choice, preprocessing, language handling, document chunking, vector normalization, and quality evaluation belong to the application.

### 3.1. Same Dimension Does Not Mean Same Vector Space

Two distinct models can both output 768-dimensional vectors, yet their values **cannot be meaningfully compared** if trained in different spaces. A vector from model A is not compatible with vectors from model B just because both fit `vector<float,768>`.

Your embedding contract should capture:

| Metadata | Example | Reason |
|---|---|---|
| `embedding_model` | `edu-embedding-v1` | Identifies which model generated the vector |
| `model_revision` | `2026-10` | Ensures reproducibility and upgrades |
| `embedding_dim` | 1536 (fixed in schema) | Catches dimension mismatches |
| `normalization` | `unit_l2` or `none` | Aligns with dot/cosine metric |
| `content_hash` | Digest of input text | Detects when text changed while vector is stale |
| `chunker_version` | `chunks-v2` | Tracks how text chunks were produced |
| `created_at` | `timestamp` | Auditing and lifecycle management |

Store metadata in the same table or in a model/chunk management table; **never store bare vectors alone** and lose track of source text and model version.

### 3.2. float Carries Numerical Precision Error

`vector<float,n>` uses **32-bit float (IEEE 754)** for ANN. It is not `decimal` and cannot represent every decimal fraction exactly. When upstream data uses `double`, narrowing to `float` introduces rounding; closely spaced values can collapse to the same float.

Never use float vectors for **money, exact identifiers, or exact-reconciliation data**. They serve approximate arithmetic and similarity scoring.

Applications should validate:

1. Exact dimension count matching the schema.
2. No null elements.
3. Every float is **finite** (no `NaN`, `+Infinity`, or `-Infinity`) before sending to the ANN service.
4. Non-zero norm when cosine similarity requires directional vectors.
5. Query vectors are produced by **the exact same model and normalization** as indexed vectors.

A vector of the right length consisting of all zeros or unnormalized values still produces nonsensical search results; numerical validation must live at both ingest and query boundaries.

## 4. How Do Vector Search, SAI, and ANN Differ from Key Lookups?

Cassandra supports two fundamentally different query modes:

**Exact lookup**:

~~~cql
SELECT *
FROM sample_vectors_by_id
WHERE sample_id = 11111111-1111-4111-8111-111111111111;
~~~

Cassandra uses the **partition key** to locate tokens and replicas. The result maps to **one specific ID**.

**Nearest-vector search**:

~~~cql
-- Requires an SAI vector index on the queried embedding column.
SELECT chunk_id, content_preview
FROM document_chunks_by_id
ORDER BY embedding ANN OF [0.10, 0.20, 0.30]
LIMIT 5;
~~~

Cassandra uses the **SAI vector index** to find candidates near the query vector. This is **Approximate Nearest Neighbor (ANN)**: answering "which points are *close* to the query point?" under a metric, not an equality lookup.

### 4.1. ANN Is Approximate, Not Exact Global Top-K

Across millions of vectors, computing exact distances to **every vector** is prohibitively expensive. ANN uses index structures to narrow the search space, trading some **recall** for speed and scalability. Consequently:

- Results may **differ slightly** from brute-force top-k.
- Ordering and candidate sets can vary as data/indexes update, algorithm settings change, or cluster state shifts.
- `LIMIT 5` caps returned rows; it does not prove Cassandra exhaustively verified those 5 are globally optimal.
- Vectors "close" under a metric do not guarantee a document is **factually true**, authorized for the caller, or business-valid.

A RAG (retrieval-augmented generation) system should include **tenant/ACL filtering**, result evaluation, optional **reranking**, and source citations rather than treating ANN as truth verification.

### 4.2. Why Is SAI Required?

In Apache Cassandra 5.0, vector search relies on **Storage-Attached Index** structures for embedding lookups. A table with a `vector<float,3>` column **without an SAI vector index** can still write and read embeddings by primary key, but cannot execute the ANN query shown above.

An SAI vector index adds operational cost:

- Extra write amplification and index structures.
- Higher RAM/disk demand and build/backfill load when indexing existing data.
- Impact on compaction and SSTable/index lifecycle.
- Release-specific limits on queries, metrics, and compatibility.

**SAI does not replace the partition key.** The table still relies on its primary key for row placement and updates; ANN is an **additional query path** for similarity search.

## 5. Practical CQL: Embedding Table and ANN Queries

The example below uses **3 dimensions** so learners can enter values manually. These are **not real model embeddings**; the numbers strictly illustrate CQL syntax on an **Apache Cassandra 5.0 cluster supporting SAI vector indexes**.

### 5.1. Creating the ID-Keyed Table

~~~cql
CREATE TABLE document_chunks_by_id (
    chunk_id uuid PRIMARY KEY,
    tenant_id uuid,
    document_id uuid,
    chunk_no int,
    embedding_model text,
    content_preview text,
    embedding vector<float, 3>,
    created_at timestamp
);
~~~

Explanation:

- `chunk_id` is the **partition key**, serving exact lookups and per-chunk updates/deletes.
- `tenant_id` identifies owner and access scope. **Having this column alone does not automatically isolate ANN queries by tenant.**
- `document_id` and `chunk_no` link each chunk back to its source document.
- `embedding_model` records which model produced the vector; never compare vectors from different models blindly.
- `content_preview` holds a short snippet for display; large content can reside in another table or object storage.
- `embedding` is a **fixed-dimension numeric column**, not an ID or clustering key.

### 5.2. Creating an SAI Vector Index

Using Apache Cassandra 5.0 syntax:

~~~cql
CREATE INDEX IF NOT EXISTS chunk_embedding_ann_idx
ON document_chunks_by_id (embedding)
USING 'sai';
~~~

Another syntax seen in docs/drivers on compatible deployments:

~~~cql
-- Alternate SAI syntax; choose whichever syntax your cluster supports.
-- CREATE CUSTOM INDEX chunk_embedding_ann_idx
-- ON document_chunks_by_id (embedding)
-- USING 'StorageAttachedIndex';
~~~

**Do not run both statements on the same column "just to be safe."** Pick **one SAI creation form** for your version/deployment. `IF NOT EXISTS` prevents name collisions, but does not verify an existing index has the metric or options your app expects.

**The default similarity metric is cosine** per Apache Cassandra 5.0 documentation. To use another metric, pass supported `WITH OPTIONS`, for example:

~~~cql
-- Alternative index definition only; do NOT run alongside
-- the cosine index above.
-- CREATE INDEX chunk_embedding_dot_idx
-- ON document_chunks_by_id (embedding) USING 'sai'
-- WITH OPTIONS = {'similarity_function': 'DOT_PRODUCT'};
~~~

The metric is bound to the **index**, not switched per query request. Changing metrics requires an **index rebuild / drop-and-recreate** workflow plus data/model evaluation.

### 5.3. Writing Vectors with Stable IDs

~~~cql
INSERT INTO document_chunks_by_id (
    chunk_id, tenant_id, document_id, chunk_no,
    embedding_model, content_preview, embedding, created_at
) VALUES (
    11111111-1111-4111-8111-111111111111,
    99999999-9999-4999-8999-999999999999,
    22222222-2222-4222-8222-222222222222,
    0,
    'demo-3d-v1',
    'Cassandra distributes data by partition key',
    [0.90, 0.10, 0.05],
    '2026-11-21T08:00:00Z'
);

INSERT INTO document_chunks_by_id (
    chunk_id, tenant_id, document_id, chunk_no,
    embedding_model, content_preview, embedding, created_at
) VALUES (
    33333333-3333-4333-8333-333333333333,
    99999999-9999-4999-8999-999999999999,
    22222222-2222-4222-8222-222222222222,
    1,
    'demo-3d-v1',
    'SAI supports finding similar vectors',
    [0.75, 0.20, 0.10],
    '2026-11-21T08:01:00Z'
);

INSERT INTO document_chunks_by_id (
    chunk_id, tenant_id, document_id, chunk_no,
    embedding_model, content_preview, embedding, created_at
) VALUES (
    44444444-4444-4444-8444-444444444444,
    99999999-9999-4999-8999-999999999999,
    55555555-5555-4555-8555-555555555555,
    0,
    'demo-3d-v1',
    'Network latency affects distributed systems',
    [0.05, 0.80, 0.55],
    '2026-11-21T08:02:00Z'
);
~~~

Fixed UUIDs are used for illustration. In production, assign `chunk_id` **once** before writing and reuse it on retries; generating a fresh ID after a timeout turns one chunk into **two rows**, hurting both search accuracy and index footprint.

### 5.4. Running an ANN Query

~~~cql
SELECT chunk_id, document_id, content_preview
FROM document_chunks_by_id
ORDER BY embedding ANN OF [0.85, 0.15, 0.10]
LIMIT 3;
~~~

Key syntax points:

- `ORDER BY embedding ANN OF [...]` requests vectors **closest to the query vector** under the index metric.
- `LIMIT 3` bounds returned results; **Apache Cassandra 5.0** documents a **maximum `LIMIT` of 1000** for ANN queries.
- You do not supply `chunk_id` for an index-wide ANN query, unlike partition-key lookups.
- ANN ordering is **not** primary-key `CLUSTERING ORDER BY`. It is specialized search syntax backed by SAI.

Exact ID lookup remains just as useful:

~~~cql
SELECT embedding_model, embedding, content_preview
FROM document_chunks_by_id
WHERE chunk_id = 11111111-1111-4111-8111-111111111111;
~~~

These two access paths serve different goals; keep both when the domain needs **exact chunk retrieval** alongside **similarity search**.

### 5.5. Computing Similarity Scores to Explain Results

Apache Cassandra 5.0 provides built-in functions over float vectors:

~~~cql
SELECT chunk_id,
       content_preview,
       similarity_cosine(embedding, [0.85, 0.15, 0.10]) AS score
FROM document_chunks_by_id
ORDER BY embedding ANN OF [0.85, 0.15, 0.10]
LIMIT 3;
~~~

Functions listed in Cassandra documentation include:

- `similarity_cosine(vector, vector)`
- `similarity_dot_product(vector, vector)`
- `similarity_euclidean(vector, vector)`

**Never assume all score functions share the same scale or are directly comparable across metrics.** Cassandra's `similarity_...` functions return **similarity scores** defined by its implementation, not necessarily raw Euclidean distances computed manually by the app. Define the metric and score interpretation clearly when evaluating search quality.

## 6. Metrics: Cosine, Dot Product, or Euclidean?

The three common metrics serve distinct roles:

| Index Metric | Intuitive Meaning | When Suitable | Caveats |
|---|---|---|---|
| **COSINE** | Prefers vectors pointing in the **same direction** | Language/semantic embeddings where vector norms may vary | Zero-norm vectors are invalid for cosine; approximate results |
| **DOT_PRODUCT** | Inner product of components | When embeddings are **L2-normalized** and required by the model/metric | On unnormalized vectors, vector magnitude skews rankings |
| **EUCLIDEAN** | Geometric distance in vector space | When absolute distance matters | Sensitive to per-dimension scale and normalization |

For two unit vectors, **cosine similarity and dot product** yield equivalent rankings in typical tasks. When vector norms differ, dot product no longer reflects angle alone.

L2-normalization definition:

\[
\hat{\mathbf v} = \frac{\mathbf v}{\|\mathbf v\|_2},
\qquad
\|\mathbf v\|_2 = \sqrt{\sum_i v_i^2}
\]

When \(\|\mathbf v\|_2 = 0\), division is undefined; handle zero vectors prior to storage/querying. Floats also carry rounding error and overflow/underflow risks, requiring application validation.

Simple Java example normalizing a vector:

~~~java
import java.util.ArrayList;
import java.util.List;

static List<Float> unitVector(List<Float> values) {
    double sumSquares = 0.0;
    for (Float value : values) {
        if (value == null || !Float.isFinite(value)) {
            throw new IllegalArgumentException("Embedding contains invalid value");
        }
        sumSquares += (double) value * value;
    }
    double norm = Math.sqrt(sumSquares);
    if (!(norm > 0.0) || !Double.isFinite(norm)) {
        throw new IllegalArgumentException("Cannot normalize a zero vector");
    }
    List<Float> result = new ArrayList<>(values.size());
    for (float value : values) {
        result.add((float) (value / norm));
    }
    return result;
}
~~~

This illustrates the **numerical rule**, not a mandate to normalize every embedding. Normalize only when dictated by your model contract and chosen metric. If a model already emits normalized unit vectors, avoid re-normalizing unnecessarily if it alters pipeline precision.

## 7. Java Driver 4.17+/4.19: CqlVector<Float>

### 7.1. Vectors Are Not List<Float> in the Driver

In Java Driver versions supporting CQL vectors, the default Java mapping is **`com.datastax.oss.driver.api.core.data.CqlVector<T>`**. For `vector<float,3>`, use **`CqlVector<Float>`**.

Key APIs:

| Operation | Vector-Capable Java Driver |
|---|---|
| Create a 3D value | `CqlVector.newInstance(0.90f, 0.10f, 0.05f)` |
| Create from a list | `CqlVector.newInstance(List<Float>)` |
| Bind a vector column | `setVector(index, value, Float.class)` |
| Read a vector | `row.getVector("embedding", Float.class)` |
| Check dimension count | `vector.size()` |
| Read coordinate at index | `vector.get(index)` |
| Codec for `float[]` | `ExtraTypeCodecs.floatVectorToArray(dim)` when explicitly registered/used |

**Version warning:** driver 4.17 docs describe vector API updates; snippets using `CqlVector.newInstance` require a driver dependency providing that method. Never copy code to an older 4.x driver assuming every 4.x release exposes identical APIs.

`CqlVector.newInstance(List)` can **wrap an `ArrayList` directly** without copying elements, and `CqlVector` supports mutation via `set(index, value)`. When executing statements asynchronously, never mutate the underlying list/vector after binding; take an immutable snapshot if data crosses threads.

### 7.2. Writing Vectors with Prepared Statements

Assume `session` is a `CqlSession` connected to the cluster/keyspace containing `document_chunks_by_id`:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.data.CqlVector;

import java.time.Instant;
import java.util.UUID;

// CqlSession session = ...; // Initialized per environment configuration.

UUID chunkId =
    UUID.fromString("11111111-1111-4111-8111-111111111111");
UUID tenantId =
    UUID.fromString("99999999-9999-4999-8999-999999999999");
UUID documentId =
    UUID.fromString("22222222-2222-4222-8222-222222222222");

CqlVector<Float> embedding =
    CqlVector.newInstance(0.90f, 0.10f, 0.05f);

if (embedding.size() != 3) {
    throw new IllegalArgumentException("Vector must have 3 dimensions");
}

PreparedStatement insert = session.prepare(
    "INSERT INTO document_chunks_by_id "
  + "(chunk_id, tenant_id, document_id, chunk_no, "
  + " embedding_model, content_preview, embedding, created_at) "
  + "VALUES (?, ?, ?, ?, ?, ?, ?, ?)");

BoundStatement bound = insert.boundStatementBuilder()
    .setUuid(0, chunkId)
    .setUuid(1, tenantId)
    .setUuid(2, documentId)
    .setInt(3, 0)
    .setString(4, "demo-3d-v1")
    .setString(5, "Cassandra distributes data by partition key")
    .setVector(6, embedding, Float.class)
    .setInstant(7, Instant.parse("2026-11-21T08:00:00Z"))
    .build();

session.execute(bound);
~~~

Using a prepared statement lets the driver bind using the **`vector<float,3>` column's** codec. On production write paths, validate upfront: model name, dimension, finite floats, norm if applicable, tenant permissions, payload limits, and stable IDs.

### 7.3. Reading CqlVector from a Row

~~~java
import com.datastax.oss.driver.api.core.cql.Row;
import com.datastax.oss.driver.api.core.data.CqlVector;

PreparedStatement byId = session.prepare(
    "SELECT embedding_model, embedding, content_preview "
  + "FROM document_chunks_by_id WHERE chunk_id = ?");

Row row = session.execute(byId.bind(chunkId)).one();
if (row != null && !row.isNull("embedding")) {
    CqlVector<Float> stored = row.getVector("embedding", Float.class);
    int dimension = stored.size();
    float first = stored.get(0);
    String model = row.getString("embedding_model");
}
~~~

A row may exist while its **embedding column is not yet written**. This differs from a **vector containing a NULL element** (which is invalid). When ingesting metadata first, you can leave `embedding` unset and backfill via `UPDATE` later; during index/search, rows without a live vector simply **do not participate meaningfully in ANN scores**.

### 7.4. Querying ANN from Java

A prepared statement uses a **bind marker** for the ANN query vector. Verify that your driver and cluster support the parser and codec:

~~~java
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;
import com.datastax.oss.driver.api.core.data.CqlVector;
import java.util.UUID;

CqlVector<Float> queryVector =
    CqlVector.newInstance(0.85f, 0.15f, 0.10f);

PreparedStatement ann = session.prepare(
    "SELECT chunk_id, document_id, content_preview "
  + "FROM document_chunks_by_id "
  + "ORDER BY embedding ANN OF ? LIMIT 3");

for (Row hit : session.execute(
        ann.boundStatementBuilder()
           .setVector(0, queryVector, Float.class)
           .build())) {

    UUID matchedId = hit.getUuid("chunk_id");
    String preview = hit.getString("content_preview");
}
~~~

**Operational note:** ANN in Cassandra 5.0 carries specific restrictions on consistency levels, paging, and filter predicates depending on build. Never assume an ANN query works with **the same paging or `LOCAL_QUORUM` settings as normal partition-key SELECTs**. Test your exact version and supported CLs; before production rollout, verify your distribution's support status rather than stopping once a query returns 3 rows.

### 7.5. Can You Pass float[]?

Per Java Driver 4.18+/4.19 docs, `ExtraTypeCodecs.floatVectorToArray(int dimensions)` exists for Java codebases preferring **`float[]`**. However, this is an **explicitly registered codec**, not an automatic rule where `setList` with a `float[]` turns into a CQL vector.

For learning examples, `CqlVector<Float>` is clearest; for high-throughput ML pipelines, evaluate the `float[]` codec while testing copying overhead, heap/off-heap behavior, GC, and version compatibility.

## 8. Never Mix Embedding Models in One Arbitrary Index

Suppose a system uses two models:

- `model-v1` produces 384-dimensional vectors.
- `model-v2` produces 768-dimensional vectors.

You cannot store both in **the same `vector<float,384>` column**. Upgrading to a model with different dimensions means **changing the schema/query path**, not just editing metadata.

Even if both models emit 384 dimensions, they **do not live in the same vector space**. If an index mixes v1 and v2 vectors, approximate top-k loses semantic validity. Practical strategies:

1. **Separate tables/indexes per model version**, e.g., `chunks_embedding_v1_by_id` and `chunks_embedding_v2_by_id`.
2. **A new vector column + new index** in the same table when migrations and queries are cleanly governed, never sharing one index across incompatible embedding spaces.
3. **Time-boxed dual-write/dual-read** during migration so the application explicitly selects which model and index to query.
4. **Backfill from source content** using the exact target model/revision, verifying `content_hash` and source snapshots.
5. **Cut off old-path queries and clean up** once data, index, and search accuracy on the new path are verified.

**Do not expect `ALTER TABLE ... ALTER embedding TYPE vector<float,768>` to be a safe in-place migration.** Changing vector dimensionality requires creating new schemas/indexes and migrating data per cluster capacity.

### 8.1. Designing Chunk IDs and Idempotency

One document splits into multiple chunks. Use stable keys:

~~~text
tenant_id
document_id
source_revision
chunk_no / chunk_id
embedding_model_version
~~~

If an embedding worker times out and retries, **keep the exact same chunk ID for the same content revision and model**. Generating a new UUID on each retry duplicates chunks in ANN results, degrading recall/precision and bloating the index.

When source content is edited, trigger **re-embedding**. Never leave stale embeddings paired with updated text, or ANN results will return previews that no longer match the vector.

## 9. Query-Driven Table Design: Vectors Do Not Replace Partition Keys

A document search app typically needs **at least two read paths**:

1. **Exact lookup and listing chunks of a document**: given `tenant_id` and `document_id`.
2. **Finding chunks similar to a query**: using an ANN index with tenant authorization.

These two paths may require separate tables or index structures.

### 9.1. Table for Listing Chunks by Document

~~~cql
CREATE TABLE document_chunks_by_document (
    tenant_id uuid,
    document_id uuid,
    chunk_no int,
    chunk_id uuid,
    source_revision text,
    content_preview text,
    PRIMARY KEY ((tenant_id, document_id), chunk_no)
) WITH CLUSTERING ORDER BY (chunk_no ASC);
~~~

Query to reconstruct a document's chunks in order:

~~~cql
SELECT chunk_no, chunk_id, content_preview
FROM document_chunks_by_document
WHERE tenant_id = 99999999-9999-4999-8999-999999999999
  AND document_id = 22222222-2222-4222-8222-222222222222;
~~~

This table has **no vector index**, because it strictly serves exact partition reads. `document_chunks_by_id` holds vectors/SAI for ID lookups and ANN; when the same content spans both tables, implement **sync, retries, and reconciliation**.

### 9.2. Tenant Boundaries and ACLs Must Be Enforced

The simple ANN example in Section 5 searches across all indexed rows in the table. In multi-tenant systems:

- Never expose results from another tenant in the UI merely because ANN found a close vector.
- Check **tenant filtering support inside ANN queries** on your exact Cassandra 5.0 patch/distribution. `WHERE` clauses may require a partition key or an appropriate index.
- Where filtered ANN is supported, benchmark recall and latency across both high- and low-selectivity filters.
- If required filtering is unsupported, consider **per-tenant data/index isolation** or a search engine built for those predicates; **never** treat post-filtering after `LIMIT k` as equivalent to top-k within a single tenant.

For example, table-wide ANN returns top 5, where 4 belong to another tenant. Filtering those 4 out afterward leaves only 1 result—even if dozens of great matches for the valid tenant sat at ranks 6–50. That is the difference between **pre-/in-search filtering** and **post-top-k filtering**.

In RAG systems, beyond tenant boundaries, enforce document ACLs, classifications, retention, and user permissions. A vector index is not an access control engine.

### 9.3. Search Is Not Fact Lookup

When the question is "retrieve the exact clause text of contract X," use the **contract primary key/ID** and verified version. ANN fits "find relevant passages," not authoritative lookups for billing, authorization, or compliance decisions.

A safer RAG pipeline:

~~~text
User query
  -> Check tenant / ACL / data permissions
  -> Normalize / chunk / embed with registered model
  -> Run ANN within permitted scope
  -> Inspect / rerank candidates and fetch source content by ID
  -> Attach source, version, and relevance checks
  -> Generate answer from authorized context
~~~

Clearly separate **model search scores** from **factual truth**. ANN top-k yields candidates, not verified facts.

## 10. ANN Has Different Limits from Partition-Key SELECTs

In **Apache Cassandra 5.0** documentation, ANN carries key constraints:

- An **SAI index is required** on the queried float vector column.
- **`LIMIT` is mandatory**, and working-with vector search docs state a **maximum of 1000**.
- ANN performs **approximate nearest neighbors**, not exhaustive exact KNN.
- "Least similar" queries are not supported as a symmetric default variant.
- Frequent **vector overwrites/deletes** can slow searches compared to relatively append-mostly workloads.
- **Combinations of filters, consistency levels, paging, and grouping** depend on build limits. Some Apache Cassandra 5.0 sources even flag ANN/SAI vector search as **experimental** with restrictions on consistency levels higher than `ONE/LOCAL_ONE`, paging, and extra clauses. Verify your exact build **before production use**.

Therefore, do not carry normal CQL habits blindly into ANN:

~~~cql
-- Never assume every common SELECT pattern works with ANN:
-- SELECT ... FROM ... ORDER BY embedding ANN OF [..];
-- SELECT ... FROM ... ORDER BY embedding ANN OF [..] LIMIT 100000;
-- SELECT ... FROM ... ORDER BY embedding ANN OF [..]
--   PER PARTITION LIMIT 10;
~~~

A query rejected by the parser should **never** be "fixed" with `ALLOW FILTERING` in production. `ALLOW FILTERING` does not add an ANN index and can trigger unpredictable scans in other queries.

Before deploying, build an **acceptance test suite** covering all real ANN queries: with/without `WHERE`, metrics, `LIMIT`, CL, paging, schema/index lifecycle, deleted/TTL-expired rows, and recovery after node failures.

## 11. Replication, Consistency, Tombstones, Compaction, and Repair with Vectors

### 11.1. Replication Does Not Make ANN an ACID Transaction

Cassandra still distributes rows by **partition key** and copies them per the replication strategy. An embedding in a `vector` column is **replicated row data**. SAI adds index structures for ANN, without replacing consistency rules, primary keys, or cell mutation semantics.

Questions to answer:

- How many replicas acknowledge writes before the client confirms?
- Which **consistency levels are supported by your version** for ANN queries?
- Immediately after a write finishes, is the index visible across all read paths?
- When a node or index rebuilds, how do ANN counts and results behave?

**Never assume ANN queries share the same read/write guarantees as `SELECT ... WHERE primary_key=?` at `LOCAL_QUORUM`.** For read-your-writes or accuracy-critical flows, benchmark and test consistency directly on your cluster.

### 11.2. Vector Updates/Deletes and Tombstones

`UPDATE ... SET embedding = [ ... ]` replaces **the entire vector**; it never mutates one dimension. Deleting the column or row generates tombstones; TTL expiration also removes data per Cassandra rules.

Indexes must track live vectors and recent writes/deletes. Workloads that rewrite embeddings en masse increase index, SSTable, and compaction pressure. If the application switches models frequently, prefer **versioned tables/indexes per model** with controlled cutovers rather than overwriting one column repeatedly.

### 11.3. Compaction, Repair, and Memory Limits

- **Compaction** reorganizes SSTables and associated index structures, consuming CPU, disk I/O, and write bandwidth; monitor closely when backfilling millions of embeddings.
- **Repair** converges replica data state, but cannot fix embeddings generated by the wrong model or flawed preprocessing.
- **Replication factor** multiplies storage for both raw vectors and indexes; size capacity per replica, disk tier, RAM, and index build throughput.
- **GC/heap/off-heap** memory on Java clients and Cassandra nodes can come under pressure when queries or batches carry high-dimensional vectors; measure p95/p99 latency, QPS, memory, and payload size.

Never use an arbitrary hardcoded batch rule like "write 10,000 vectors in one `BATCH`" expecting higher throughput. Cassandra `BATCH` is not a general bulk loader; tune ingestion rate, concurrency, and backpressure to match cluster capacity.

### 11.4. Dedicated Monitoring for Search Quality

Beyond database metrics (latency, throughput, disk, tombstones, compaction, repair), search applications need:

- **Recall@k** measured against a ground-truth / brute-force evaluation set.
- **Precision@k** or human relevance ratings.
- **p50/p95/p99 latency** broken down by tenant/metric filters.
- **Empty-result rates, timeouts, dimension errors**, and codec failures.
- **Model version drift** and embedding coverage: chunks with vs. without vectors.
- **Index quality after reindex/compaction** and during node incidents.

A search pipeline can have low latency yet return semantically wrong results if models or preprocessing drift. Application-level accuracy tests cannot be replaced by "the CQL query ran without error."

## 12. Compatibility Options When Your Cluster Lacks vector

If your cluster runs Cassandra 4.x or a distribution without `vector`/SAI ANN, several alternatives exist. **Do not treat them as full equivalents.**

| Option | Advantages | Limitations |
|---|---|---|
| **Upgrade to vector-capable Cassandra** | Keeps data and ANN queries inside Cassandra if SLA fits | Requires migration/rolling upgrade, driver updates, and production ANN evaluation |
| **Store `list<float>`** | Stores a numeric sequence on older clusters | No type-enforced fixed dimension; **no ANN index** |
| **Store `blob`** of float bytes | Compact custom format, external codecs possible | Must specify endianness/schema/normalization; **no ANN search** |
| **Offload vectors to a dedicated vector store** | May offer richer ANN/filtering/index lifecycles | Requires cross-system ID, version, and data sync |
| **Application brute force** for tiny datasets | Easy to verify exact results on small sets | Linear cost per vector; unsuitable at scale without bounds |

For instance, storing raw vectors as `blob` requires defining **float32**, **byte order**, **dimension N**, **model version**, **endianness**, and reader codecs. Yet Cassandra cannot interpret those bytes as `vector<float,N>` or an SAI vector index until you **migrate and change the schema**.

Nor does `list<float>` turn into an ANN index automatically upon upgrade. Moving to `vector` requires **creating new columns/tables, validating N, converting, and backfilling**. It is a true migration, not just swapping a Java type name.

## 13. Version-Safe Vector Migration Plan

Rollouts should proceed in stages:

### Stage 1 — Inventory and Test in a Matching Environment

Verify:

- Apache Cassandra version on **all nodes** and schema agreement status.
- Does the distribution/managed service truly support `vector`, `SAI`, `ANN OF`, and your target metric?
- Does the Java Driver include `CqlVector` and compatible codecs?
- Dimensionality, model, value/norm distributions, dataset size, and recall/latency targets.

Create a **sandbox test table** on a compatible cluster and run 3D vector smoke tests. Never put new syntax into a shared migration script running on older clusters.

### Stage 2 — Create New Schema and Index

Create the vector column/table alongside **model version** fields. Choose exact lookup keys, tenant access controls, metadata types, and indexes. Only create the index after verifying compatibility limits and metrics.

When indexing an already populated table, provision capacity for **index build/backfill**. Keep an application-level rollback path; never assume dropping an index has zero operational impact.

### Stage 3 — Rate-Limited, Idempotent Backfill

- Generate embeddings from trusted source content.
- Attach `chunk_id`, `source_revision`, `embedding_model`, and a stable content hash.
- Validate exact dimensions, finite floats, and normalization.
- Write with bounded throughput, backpressure, and retries reusing the same ID.
- Reconcile source chunk counts against embedded chunks; classify unrecoverable errors.

If the model changed, never swap in same-dimension vectors while hiding the version change, or search quality becomes unverifiable.

### Stage 4 — Dual-Read / Evaluation

Maintain old and new search paths temporarily:

- Run identical query sets to compare top-k quality.
- Verify ACLs, tenant filters, empty results, and timeouts.
- Measure read/write p95/p99, index build/compaction load, and impact on other Cassandra tables.
- Validate content ↔ embedding sync on user edits and deletions.
- Confirm fallback paths if ANN or the index becomes unavailable.

### Stage 5 — Cutover and Cleanup

Switch production queries only after quality and operational criteria pass. Afterward, schedule cleanup of old columns, indexes, and tables per retention and audit rules. Tombstones and index resources do not vanish immediately when queries stop hitting the old path.

If the cluster cannot meet your ANN consistency or query requirements, keep Cassandra for transactional/domain data and use a search engine suited to those queries. Never force `vector` just because a newer release offers it.

## 14. Common Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Running `CREATE TABLE ... vector<float,n>` on Cassandra 4.1 | Syntax/unsupported-type failure | Check version, upgrade, or pick an alternative |
| Assuming `list<float>` equals `vector<float,n>` | No N validation and no ANN index | Use `vector` schema when version supports it |
| Writing a vector with wrong dimension count | Write/bind failure | Validate dimension count before sending |
| Allowing nulls inside a vector | Invalid at element level | Drop incomplete data or compute full embeddings |
| Creating an ANN index on `vector<int,n>` | Vector search requires float vectors | Use `vector<float,n>` for ANN embeddings |
| Mixing embeddings from two models of equal dimension | Numerically close yet semantically broken search | Separate indexes by model/version |
| Choosing dot product for unnormalized vectors | Vector norm distorts rankings | Normalize or pick the right metric |
| Treating ANN as exact top-k | Misses valid candidates due to approximate search | Measure recall@k and rerank when needed |
| Querying ANN without creating SAI | No valid vector search path | Create SAI matching version and metric |
| Running ANN without `LIMIT` or with huge `LIMIT` | Violates query limits | Use supported bounds and benchmark |
| Running global ANN then filtering permissions after `LIMIT` | Missing valid hits and risk of data leaks | Filter before/within search and enforce ACLs |
| Reusing normal SELECT CL/paging on ANN blindly | Rejected queries or false assumptions | Test limits on your exact build |
| Overwriting vectors repeatedly during ingest/rebuilds | Heavy index/compaction overhead | Version tables/indexes and stream backfills |
| Generating a new chunk UUID on each retry | Duplicate chunks in ANN and index bloat | Stable IDs by chunk/revision/model |
| Treating float embeddings as exact reconciliation numbers | IEEE 754 error and wrong semantics | Use decimal/bigint for money; float for embeddings |
| Upgrading model while only updating metadata | Old vectors remain in the old model's space | Re-embed and switch to a versioned index |
| Ignoring Java Driver version | Missing `CqlVector` codecs/APIs | Inspect runtime dependencies and upgrade driver |
| Applying vendor-specific limits to Apache Cassandra | Limits and syntax differ | Check docs for your exact server/distribution |

## 15. Practice Exercises

### Exercise 1 — Choosing the Right Type

One system needs to store 5 float features for ANN comparison on Cassandra 5.0; another only needs a variable-length list of test scores.

**Answer:** for the first case, use `vector<float,5>` with an SAI vector index if ANN is supported by your deployment; for the second case, use `list<float>` if small and bounded, or a multi-row table if unbounded. Never use `list<float>` to simulate vector search.

### Exercise 2 — Why Are Dimensions Wrong?

Schema:

~~~cql
CREATE TABLE exercise_embeddings (
    id uuid PRIMARY KEY,
    embedding vector<float, 3>
);
~~~

One service sends `[0.1, 0.2]` and another sends `[0.1, 0.2, null]`. Which write is valid?

**Answer:** **neither**. A vector must contain **exactly 3 elements**, and elements **cannot be NULL**.

### Exercise 3 — ANN Query

`exercise_embeddings` already has an SAI vector index. Write a query finding the three closest points to `[0.2, 0.4, 0.6]`:

~~~cql
SELECT id, embedding
FROM exercise_embeddings
ORDER BY embedding ANN OF [0.2, 0.4, 0.6]
LIMIT 3;
~~~

**Explanation:** uses `ORDER BY ... ANN OF` and `LIMIT`. This is **approximate similarity search**, not standard clustering order.

### Exercise 4 — Embedding Space

Models A and B both output 768 dimensions. Engineering replaces model A with B, yet keeps a shared table/index and sets `embedding_model='B'` on rows that were never re-embedded.

**Question:** why is this a bug?

**Answer:** vectors from A and B do not occupy the same vector space. Changing metadata does not change the underlying numbers. You must backfill/re-embed using model B, version properly, and evaluate a separate index/query path.

### Exercise 5 — Tenant Filtering

Table-wide ANN returns top 5: 4 rows belong to tenant B and 1 row belongs to tenant A. The app filters out tenant B after the query and concludes tenant A has only 1 relevant match.

**Answer:** that conclusion is wrong: relevant matches for A at ranks 6+ may exist. Design tenant filtering **before or inside** search (as supported by your version) while enforcing ACLs before returning content.

### Exercise 6 — Java Driver

A Java application needs to bind a 3D vector into `embedding vector<float,3>`. Can it use `List<Double>` and `setList()`?

**Answer:** that is not a valid default mapping. Use `CqlVector<Float>`, e.g., `CqlVector.newInstance(0.1f,0.2f,0.3f)`, bound with `setVector(index, vector, Float.class)` on a supporting driver. Validate dependencies, dimensions, nulls, and finite values before writing.

## 16. Checklist for Deploying Vector / Versioned Types

- [ ] Have **all node versions** and the distribution been verified for type/feature support?
- [ ] Do the Java Driver and related services have compatible `CqlVector` codecs and APIs?
- [ ] Is **storing vectors** clearly separated from **SAI index + ANN search**?
- [ ] Does the vector column have a **fixed dimension** matching the model, with no NULL elements?
- [ ] Does the pipeline validate `NaN`, infinity, zero vectors, and normalization per metric?
- [ ] Is `vector<float,n>` used for supported ANN, avoiding `vector<int,n>` for ANN embeddings?
- [ ] Are `embedding_model`, revision, source hash, and chunking metadata persisted?
- [ ] Does the **COSINE/DOT_PRODUCT/EUCLIDEAN** metric match the model and normalization?
- [ ] Does ANN include an appropriate **LIMIT**, with queries/CL/paging/filters tested on the exact build?
- [ ] For multi-tenant workloads, are **permissions and filters** applied before/within search rather than post-filtering top-k?
- [ ] Does the partition key serve ID lookups, with an extra table if listing chunks by document is needed?
- [ ] Do benchmarks track **recall@k, relevance, and p95/p99**, not just returned row counts?
- [ ] Do ingest retries reuse `chunk_id`, preventing duplicate vectors on timeouts?
- [ ] When models change, are **schema/index versioning, re-embedding, backfill, and rollback** in place?
- [ ] Have SAI overhead, replication, compaction, repair, disk/RAM, and retention been budgeted?
- [ ] Have any features flagged experimental or restricted in your build been evaluated before production?

## References

- [Apache Cassandra 5.0 — Vector CQL data type](https://cassandra.apache.org/doc/latest/cassandra/reference/vector-data-type.html).
- [Apache Cassandra 5.0 — Working with Vector Search (SAI, ANN, LIMIT, metrics)](https://cassandra.apache.org/doc/latest/cassandra/vector-search/vector-search-working-with.html).
- [Apache Cassandra 5.0 — Vector Search Data Modeling](https://cassandra.apache.org/doc/latest/cassandra/vector-search/data-modeling.html).
- [Apache Cassandra — Working with vectors in CQL](https://cassandra.apache.org/doc/latest/cassandra/developing/cql/types.html).
- [Apache Cassandra Java Driver 4.19 — CqlVector API](https://apache.github.io/cassandra-java-driver/4.19.0/api/com/datastax/oss/driver/api/core/data/CqlVector.html).
- [Apache Cassandra Java Driver 4.19 — Upgrade Guide / vector API](https://apache.github.io/cassandra-java-driver/4.19.0/upgrade-README/).
- [Apache Cassandra Java Driver 4.19 — Custom codecs](https://apache.github.io/cassandra-java-driver/4.19.0/core/custom_codecs/).

**Remember:** a new type like **`vector` must be chosen based on your Cassandra version, Java Driver version, and actual indexing capabilities**. **`vector<T,N>`** stores a fixed sequence of N non-NULL elements; **`vector<float,N>` paired with SAI** supports **approximate ANN** search where the server supports it. It does not replace partition keys, does not provide clustering order, does not verify factual correctness, and does not isolate tenants automatically. Good designs bind **model/version, metadata, indexing, access controls, idempotent retries, and migration plans** into a single data contract.
