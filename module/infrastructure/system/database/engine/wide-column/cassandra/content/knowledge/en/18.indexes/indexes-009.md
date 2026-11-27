# Vector/ANN Queries via SAI on Supporting Versions

## Objectives and scope

In Apache Cassandra, **Storage-Attached Indexing (SAI)** enables querying data through indexes attached directly to the storage engine. Starting in **Apache Cassandra 5.0**, vector search uses SAI to perform **Approximate Nearest Neighbor (ANN)** queries: finding the vectors closest to a query vector according to a chosen similarity or distance function. This provides a way to build semantic search, content recommendations, or document retrieval for Java applications directly on Cassandra data.

This topic belongs to the **Indexes** chapter of the `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA` module. Related concepts include the wide-column model, partition keys, query-driven table design, replication, consistency levels, compaction, repair, and Java connectivity. SAI adds a vector query path; it does not eliminate the need for partition-key design and cost control in a distributed system.

After this lesson, you will be able to:

- Verify **version prerequisites** before using CQL `VECTOR` and `ANN OF`.
- Distinguish *embeddings*, similarity metrics, ANN queries, and SAI indexes.
- Create a table with `vector<float, N>`, build an SAI index, ingest data, and query top-k via CQL.
- Combine attribute filtering with vector search when supported by the query engine.
- Connect from Java using `CqlVector<Float>` and `PreparedStatement`, while recognizing accuracy, latency, and operational limits.

## 1. Check version compatibility before running examples

**Not all Cassandra versions support ANN queries via SAI.** Official Apache Cassandra documentation introduces SAI and vector search in the **5.0** release line. On Cassandra 4.x or older versions, never assume the syntax below will run; upgrade to a supporting release or choose another compatible vector search system. Managed Cassandra services may impose different limits or syntax; check documentation for your exact deployment.

| Component | Requirement |
| --- | --- |
| Server | Apache Cassandra **5.0+** with SAI/vector search enabled; verify actual version across nodes. |
| Data | `VECTOR<FLOAT, N>` column with fixed dimension `N`. |
| Index | SAI on the vector column, e.g., `CREATE INDEX ... USING 'sai'`. |
| Query | `SELECT ... ORDER BY embedding ANN OF [...] LIMIT k`. |
| Java Application | Java Driver 4.x **with vector type support**; `CqlVector` API appeared in driver 4.16 and was refined in 4.17. |

On a node connected via `cqlsh`, inspect:

~~~sql
SELECT release_version FROM system.local;
~~~

This result reflects only the queried node. In a cluster undergoing a rolling upgrade, confirm version/feature support across the **entire cluster** and follow upgrade procedures before enabling new queries in production. Never treat a newer Java Driver on the client as proof that the server supports vectors.

> The CQL examples below target Apache Cassandra 5.0 with SAI/vector search. If syntax fails in a specific installation, verify server version, driver compatibility, and release docs before modifying statements.

## 2. What roles do embeddings, SAI, and ANN play?

An **embedding** is an array of floating-point numbers produced by a machine learning model to represent text, images, or objects. Semantically similar items typically produce vectors that are geometrically close under a chosen metric. Cassandra **stores and searches** these vectors; Cassandra does not automatically convert text into embeddings merely because you declare a `vector` column.

For this lesson, a three-dimensional vector is illustrated:

~~~text
Document A: [1.00, 0.00, 0.00]
Document B: [0.95, 0.05, 0.00]
Document C: [0.00, 1.00, 0.00]
Query Q:    [1.00, 0.00, 0.00]
~~~

Under a suitable similarity function, A and B are closer to Q than C. These numbers are **geometric illustration data**, not real semantic embeddings. In production, documents and queries must be encoded by **the same compatible embedding model**, with identical dimensions and preprocessing pipelines.

Three distinct components:

| Component | Responsibility |
| --- | --- |
| `VECTOR<FLOAT, N>` | Stores a floating-point vector with **exactly N elements** in a CQL column. |
| **SAI vector index** | Builds local index structures attached to Cassandra storage to locate nearby candidates efficiently. |
| **ANN query** | Queries a top-k set of **approximate nearest neighbors** to an input vector. |

ANN trades off some **recall** to avoid the work of computing exact distances from the query to every stored vector. Consequently, ANN ordering and result sets do not necessarily match an exhaustive computation (*exact nearest neighbor*). `LIMIT 5` means returning up to five discovered matches, not guaranteeing the globally exact five rows by distance.

~~~mermaid
flowchart LR
    A["Text / documents"] --> B["Embedding model"]
    B --> C["VECTOR column"]
    C --> D["SAI vector index"]
    Q["New query"] --> E["Same embedding model"]
    E --> F["Query vector"]
    F --> G["CQL ANN OF"]
    D --> G
    G --> H["Top-k nearest results"]
    H --> I["Java app processes results"]
~~~

## 3. CQL practice: creating table, index, and loading data

Examples use the `vector_lab` keyspace for easy execution via `cqlsh` on a **single-node test** environment. `SimpleStrategy` and replication factor 1 are strictly for lab use; production should use `NetworkTopologyStrategy` with datacenter-appropriate RF.

~~~sql
CREATE KEYSPACE IF NOT EXISTS vector_lab
WITH replication = {
    'class': 'SimpleStrategy',
    'replication_factor': 1
};

USE vector_lab;

CREATE TABLE IF NOT EXISTS documents_semantic (
    doc_id uuid PRIMARY KEY,
    tenant_id text,
    title text,
    content text,
    embedding_model text,
    embedding vector<float, 3>
);
~~~

Design explanation:

- `doc_id` is the table's **partition key**; Cassandra distributes records by its token, avoiding cramming every customer's documents into one massive partition.
- `tenant_id` scopes searches by organization/customer. To filter on it without putting the partition key in `WHERE`, we need an appropriate index.
- `embedding_model` records which model version produced the vector; never mix vectors from incompatible models in the same similarity space.
- `vector<float, 3>` uses three dimensions **solely to keep lab examples concise**. In practice, `N` must match the model's output dimension. Apache Cassandra 5.0 caps vectors at **8192 dimensions**, though you should verify limits in your actual deployment.

Create SAI on the vector column and on `tenant_id`:

~~~sql
CREATE INDEX IF NOT EXISTS documents_embedding_sai
ON documents_semantic (embedding)
USING 'sai'
WITH OPTIONS = {'similarity_function': 'COSINE'};

CREATE INDEX IF NOT EXISTS documents_tenant_sai
ON documents_semantic (tenant_id)
USING 'sai';
~~~

`similarity_function` governs how the index measures closeness. Cassandra docs list `COSINE`, `DOT_PRODUCT`, and `EUCLIDEAN`, with `COSINE` as the default in the reference docs. Choose the function matching how your embedding model was trained and normalized. Never treat scores from different similarity functions as sharing the same scale.

Load sample data:

~~~sql
INSERT INTO documents_semantic
    (doc_id, tenant_id, title, content, embedding_model, embedding)
VALUES (
    11111111-1111-4111-8111-111111111111,
    'team-a', 'Introducing Cassandra', 'Cassandra distributes data by partition key.',
    'demo-3d-v1', [1.0, 0.0, 0.0]
);

INSERT INTO documents_semantic
    (doc_id, tenant_id, title, content, embedding_model, embedding)
VALUES (
    22222222-2222-4222-8222-222222222222,
    'team-a', 'Choosing a partition key', 'The partition key governs distribution and queries.',
    'demo-3d-v1', [0.95, 0.05, 0.0]
);

INSERT INTO documents_semantic
    (doc_id, tenant_id, title, content, embedding_model, embedding)
VALUES (
    33333333-3333-4333-8333-333333333333,
    'team-a', 'Repair in Cassandra', 'Repair helps synchronize data across replicas.',
    'demo-3d-v1', [0.0, 1.0, 0.0]
);

INSERT INTO documents_semantic
    (doc_id, tenant_id, title, content, embedding_model, embedding)
VALUES (
    44444444-4444-4444-8444-444444444444,
    'team-b', 'Another customer document', 'Data belonging to a different tenant.',
    'demo-3d-v1', [0.99, 0.01, 0.0]
);
~~~

If the index is created **after** data already exists, initial indexing can consume CPU, I/O, and time. Monitor index readiness before evaluating results, especially on large tables.

## 4. ANN query syntax and similarity scoring

Find the three documents closest to `[1.0, 0.0, 0.0]`:

~~~sql
SELECT doc_id, tenant_id, title
FROM documents_semantic
ORDER BY embedding ANN OF [1.0, 0.0, 0.0]
LIMIT 3;
~~~

`ORDER BY embedding ANN OF [...]` requests nearest neighbors via the vector index. This is **not** standard clustering-key sorting (`ORDER BY ... ASC/DESC`). The vector column must have a suitable SAI index. `LIMIT` is essential for top-k queries; in Apache Cassandra 5.0 docs, `LIMIT` for vector search **cannot exceed 1000**.

To also return the cosine similarity score for display or analysis:

~~~sql
SELECT doc_id, title,
       similarity_cosine(embedding, [1.0, 0.0, 0.0]) AS score
FROM documents_semantic
ORDER BY embedding ANN OF [1.0, 0.0, 0.0]
LIMIT 3;
~~~

CQL provides scoring functions such as `similarity_cosine`, `similarity_dot_product`, and `similarity_euclidean` for vectors. Here, **the index uses COSINE and the displayed score also uses cosine**. If an index is configured with `DOT_PRODUCT` while the app prints `similarity_cosine`, do not expect result ordering to match the displayed score column.

Notes when reading results:

- Because this is **ANN**, on tiny datasets documents A and B appear closest to the query vector, yet you should not write tests asserting a rigid identical order across every configuration or moment.
- Raising `LIMIT` increases query cost; avoid defaulting to `LIMIT 1000` if the UI only displays 5 to 20 suggestions.
- There is no symmetric "find the **least similar** vectors" query with the same ANN syntax.
- `SELECT *` ships long vectors over the network; select only the fields the UI needs, such as ID, title, and score.
- Similarity scores are only a ranking signal. Applications must still enforce read authorization and may add business-specific *reranking*.

## 5. Filtering by tenant/attributes and table design

In a multi-tenant application, returning `team-b`'s data when a `team-a` user searches is a serious bug. Scope the query with a filter predicate:

~~~sql
SELECT doc_id, title,
       similarity_cosine(embedding, [1.0, 0.0, 0.0]) AS score
FROM documents_semantic
WHERE tenant_id = 'team-a'
ORDER BY embedding ANN OF [1.0, 0.0, 0.0]
LIMIT 3;
~~~

In section 3's table, `tenant_id` has its **own SAI index**, so it can filter alongside ANN search on versions supporting this query shape. For other filters like `category`, `published`, or `language`, verify whether each column is reachable via primary key or an appropriate index. Never add `ALLOW FILTERING` arbitrarily to mask missing access paths.

Distinguish two concerns:

1. **Functional correctness:** `WHERE tenant_id = 'team-a'` constrains eligible rows in the result scope; enforcing user authorization remains the responsibility of application and security layers.
2. **Performance:** SAI indexes support filtering non-partition-key attributes, yet still incur cluster-wide coordination and filtering costs. Partition-keyed queries are generally cheaper when scope is known.

A table with `PRIMARY KEY (tenant_id, doc_id)` packs an entire tenant into **one partition** if `tenant_id` is the sole partition key. For very large tenants, that partition can turn hot or oversized. Never switch to that design just to eliminate an index without assessing distribution and query load. When you need ID lookups, ANN, and tenant filtering together, weigh index sets, separate tables, or partitioning strategies tailored to real load.

## 6. ANN, consistency, and cluster operations

SAI is attached to node-level data storage, not a search server external to Cassandra. Writes, memtables/SSTables, compaction, and replication all impact availability, indexing speed, and latency. Note:

- **Replication** keeps copies per RF; it does not turn ANN into exact exhaustive search.
- **Consistency levels** like `LOCAL_ONE` or `LOCAL_QUORUM` should match read guarantees and topology; raising consistency does not guarantee higher ANN *recall@k*.
- **Compaction** and SSTable index building add background work and affect latency. Never judge performance solely by the first query.
- **Repair** reconciles replica discrepancies via Cassandra mechanisms; it does not fix embeddings generated by the wrong model or wrong dimensionality.
- Frequent updates/deletes on vectors can degrade search speed relative to mostly append-only data. Official docs recommend preferring vector data with minimal overwrites/deletions.

### Limits to verify before deployment

| Constraint | Consequence / mitigation |
| --- | --- |
| Version lacks `VECTOR` or vector SAI | Cannot enable ANN merely with `CREATE INDEX`; requires a supporting Cassandra version. |
| Wrong vector dimension | Fails to match declared `VECTOR<FLOAT, N>`; validate before writing or querying. |
| Changing embedding models | Old and new vectors become incomparable; plan a new table/index and backfill. |
| Excessively large `LIMIT` | Bounded by vector search limits and increases latency. |
| Contention updating vectors on the same key | Generates write/index load and impacts queries; prefer a more stable data model. |
| Query without tenant filter | Risks leaking cross-tenant data; always apply filters and app-layer authorization. |
| Using vector indexes for data analytics | ANN returns only nearest candidates; not `GROUP BY`, joins, or exact whole-set computation. |

Measure retrieval-specific metrics:

- **Recall@k**: fraction of true relevant items retrieved against an offline *exact* ground-truth set.
- **Latency p50/p95/p99**: measured under realistic concurrent load, not a single isolated request.
- **Ingest rate**, CPU, RAM, disk/I/O, compaction, timeouts, index errors, and data volume per tenant.
- **Semantic quality**: whether queries retrieve relevant documents; the embedding model and *chunking* strategy directly drive quality.

If a node issue increases latency or reduces availability, inspect topology, consistency level, and index state together. Do not conclude that two queries returning slightly different top-k sets indicate data corruption: ANN is approximate by nature and sensitive to cluster state.

## 7. Connecting from Java applications

The example below uses **Cassandra Java Driver 4.17+** (or a compatible 4.x release with vector APIs) and Java 17. Assume `CqlSession` is configured for a Cassandra 5.0 cluster supporting SAI, the table/indexes from section 3 exist, and an external system produces compatible 3D embeddings.

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.Row;
import com.datastax.oss.driver.api.core.data.CqlVector;

import java.util.ArrayList;
import java.util.List;
import java.util.UUID;

public final class SemanticDocumentSearch {
    private final CqlSession session;
    private final PreparedStatement findSimilar;

    public record Hit(UUID id, String title, float cosineScore) {}

    public SemanticDocumentSearch(CqlSession session) {
        this.session = session;
        this.findSimilar = session.prepare(
            "SELECT doc_id, title, " +
            "similarity_cosine(embedding, ?) AS score " +
            "FROM vector_lab.documents_semantic " +
            "WHERE tenant_id = ? " +
            "ORDER BY embedding ANN OF ? " +
            "LIMIT 3");
    }

    public List<Hit> search(String tenantId, float[] embedding) {
        if (tenantId == null || tenantId.isBlank()) {
            throw new IllegalArgumentException("tenantId is required");
        }
        if (embedding == null || embedding.length != 3) {
            throw new IllegalArgumentException("Vector must have exactly 3 dimensions");
        }
        for (float value : embedding) {
            if (!Float.isFinite(value)) {
                throw new IllegalArgumentException("Vector contains NaN/Infinity");
            }
        }

        CqlVector<Float> query = CqlVector.newInstance(
            embedding[0], embedding[1], embedding[2]);
        BoundStatement bound = findSimilar.bind(query, tenantId, query)
            .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM);

        ResultSet rows = session.execute(bound);
        List<Hit> hits = new ArrayList<>();
        for (Row row : rows) {
            hits.add(new Hit(
                row.getUuid("doc_id"),
                row.getString("title"),
                row.getFloat("score")));
        }
        return hits;
    }
}
~~~

Key takeaways:

- `CqlVector.newInstance(...)` constructs a value matching `VECTOR<FLOAT, N>`. Validate input dimensions against model config (3 in this example, typically much larger in production).
- `?` placeholders pass the vector and tenant safely through a **prepared statement** rather than concatenating user input into CQL strings. Both vector `?` slots receive the `CqlVector`; the remaining slot receives `tenantId`.
- `LIMIT 3` is hardcoded here; if users supply `k`, validate and cap `k` within query limits before preparing/executing corresponding CQL.
- `LOCAL_QUORUM` illustrates consistency for an RF-appropriate cluster. On the RF=1 demo keyspace it provides no replica redundancy; production requires proper RF and DC design.
- Reuse `session` and `PreparedStatement`. Configure timeouts, concurrency limits, top-k UI bounds, and error handling when nodes or indexes are not ready.

To write vectors from Java, prepare an `INSERT` parameterized on `embedding` and bind `CqlVector<Float>` similarly. **Generating embeddings** belongs to an ML model or service outside the database; the storage layer receives validated, normalized numeric arrays.

## 8. Practice exercises and error checks

### Exercise 1 — Compatibility

Inspect `release_version` in your lab environment. Write down the server version, driver version, index syntax, and supported vector dimension limits. If running Cassandra 4.x, describe an upgrade or alternative plan—do **not** run `VECTOR` expecting it to work.

### Exercise 2 — Basic ANN

Create the table and two indexes, and load the four sample rows. Run the top-3 query for `[1.0, 0.0, 0.0]`. Compare with `[0.0, 1.0, 0.0]`. Explain why the results illustrate geometric distance only.

### Exercise 3 — Tenant filtering

Run the query without `WHERE`, then add `WHERE tenant_id = 'team-a'`. Confirm `team-b` documents disappear once filtered. Identify which index `documents_tenant_sai` serves and why application-level authorization is still mandatory.

### Exercise 4 — Similarity scores

Run the `similarity_cosine` query and compare scores across returned rows. Discuss what changes if the index is recreated with `DOT_PRODUCT` in a separate test environment. Never treat the two scales as identical.

### Exercise 5 — Data errors and maintenance

Attempt to insert a vector with the wrong number of dimensions and inspect the returned error. Simulate an embedding model upgrade, outlining the steps to keep the dataset consistent (model versioning, creating a new index, backfill, query cutover). Plan how to measure p95 and recall@k during writes, compaction, or a replica outage.

## 9. References

- [Apache Cassandra — Vector Search Quickstart](https://cassandra.apache.org/doc/stable/cassandra/getting-started/vector-search-quickstart.html): `VECTOR` example, creating SAI, loading data, and `ANN OF` queries.
- [Apache Cassandra — Vector CQL data type](https://cassandra.apache.org/doc/latest/cassandra/reference/vector-data-type.html): vector type, dimensions, and data limits.
- [Apache Cassandra — Working with Vector Search](https://cassandra.apache.org/doc/latest/cassandra/vector-search/vector-search-working-with.html): similarity functions, indexes, and ANN query limits.
- [Apache Cassandra — SAI concepts](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/indexing/sai/sai-concepts.html): SAI's place in the storage architecture.
- [Apache Cassandra Java Driver — Upgrade guide 4.17](https://docs.datastax.com/en/developer/java-driver/4.17/upgrade_guide/): using `CqlVector` with prepared statements.

## Key takeaways

**Cassandra 5.0+ can use SAI on `VECTOR<FLOAT, N>` columns to serve `ORDER BY ... ANN OF ... LIMIT` queries.** Vectors must be generated and managed consistently outside Cassandra. ANN returns approximate results, so evaluate recall, latency, tenant filtering, topology, and replication alongside CQL correctness. Always verify server and driver versions before adopting this feature.
