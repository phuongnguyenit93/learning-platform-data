# Environment and Version Requirements for Atlas Vector Search

## Lesson Objectives

**Atlas Vector Search**, which in newer MongoDB documentation is often referred to more broadly as **MongoDB Vector Search**, allows storing embeddings alongside document data, creating a **vector search index**, and querying via the `$vectorSearch` aggregation stage. This capability serves semantic search, content recommendations, internal knowledge question-answering systems (RAG), and hybrid search.

However, a syntactically valid `$vectorSearch` query can still fail because the application is running on an **unsupported environment or version**, the cluster lacks the search service, the index is not ready yet, index creation privileges are missing, or a feature is only supported in a specific version. You must distinguish at least five layers of requirements:

1. **Deployment:** Atlas cloud, Atlas CLI local, self-managed MongoDB Community/Enterprise.
2. **Version:** MongoDB Server version thresholds and tool/driver versions.
3. **Tier and architecture:** Free, Flex, Dedicated, Search Nodes, Linux self-managed, resources.
4. **Index and data:** `vectorSearch` index type, path, dimensions, similarity, filter fields, embedding model.
5. **Operations:** access permissions, networking, search process availability, consistency, quotas, and benchmarks.

This lesson belongs to **Database Engine Document MongoDB → Vector Search → Environment and Version Requirements for Atlas Vector Search**. After completing it, you will be able to:

- Distinguish vector search from B-tree indexes, text indexes, `2dsphere`, `$search`, and computing vector distances in application code.
- Identify the requirements to run `$vectorSearch` on Atlas and local/self-managed deployments.
- Know the version thresholds for **ANN** and **ENN** as well as related aggregation features.
- Distinguish **Atlas Free**, **Flex**, **Dedicated**, and **Dedicated Search Nodes**.
- Understand why “MongoDB Server is running” does not prove the search service is active.
- Check permissions, network access, TLS, drivers, and index readiness.
- Create and test a vector index with unrelated GeoJSON, sample data, and valid query vectors.
- Distinguish application-generated `queryVector` from automated embeddings (where supported by the environment).
- Troubleshoot unsupported stage errors, command not found, index not found, dimension mismatch, and filter index mismatch.
- Design a compatibility check matrix prior to upgrades, CI/CD, and production rollouts.
- Plan costs, RAM, index build time, search latency, recall, and resource isolation.

> **Note on timing:** Specific version/tier requirements in this lesson are presented according to MongoDB reference documentation as of **2026-11-14**. MongoDB may change Free/Flex policies, Search Nodes, preview/GA status, and index creation capabilities across releases. Before deploying, always check the official documentation and your **actual cluster configuration**; never treat a historical version number as a permanent guarantee.

---

## 1. What Is Vector Search and What Components Does It Require?

### 1.1. From Text to Vector

Suppose we have two products:

~~~javascript
{
  _id: "P-101",
  title: "Waterproof jacket",
  category: "OUTDOOR",
  tenantId: "tenant-a",
  status: "PUBLISHED",
  embedding: [0.10, 0.60, 0.20, 0.30]
}

{
  _id: "P-102",
  title: "Compact folding umbrella",
  category: "ACCESSORY",
  tenantId: "tenant-a",
  status: "PUBLISHED",
  embedding: [0.14, 0.57, 0.23, 0.28]
}
~~~

The `embedding` field illustrates a vector of four numeric values. In real applications, embedding models typically output higher-dimensional vectors. A question such as “rainy weather gear” is converted into a **query embedding** by the same embedding model (or a compatible one), and the system then finds the vectors closest to the query according to the configured metric.

### 1.2. Minimum Flow

~~~text
Content / document
        |
        v
Embedding model / inference service
        |
        v
Vector [v1, v2, ..., vn]
        |
        v
Store vector in MongoDB document
        |
        v
Create MongoDB Vector Search index
        |
        v
Application generates query vector
        |
        v
Aggregation: $vectorSearch
        |
        v
Results + vectorSearchScore
~~~

### 1.3. Five Minimum Requirements

To run real vector search:

1. The MongoDB deployment has **Vector Search support** for the running version/tier.
2. The corresponding search process or indexing service is active.
3. The collection has embedding data with the right type, dimensions, and path.
4. The Vector Search index is created and **finished building**.
5. The `$vectorSearch` query is valid, using matching index name/path and query vector.

Creating a vector array in BSON does not automatically allow MongoDB to perform nearest-neighbor search; you need the appropriate index/service and stage.

### 1.4. Commonly Confused Concepts

| Component | Purpose | Does it replace a Vector Search index? |
|---|---|---|
| MongoDB document field `embedding` | Stores the vector | No |
| B-tree index `{embedding:1}` | Standard field index | No |
| MongoDB text index | Full-text using text index tokenizer | No |
| MongoDB Search index | Full-text/search features, some legacy/hybrid vector approaches | Not automatically a dedicated `vectorSearch` index |
| MongoDB Vector Search index | Indexes vectors and filter fields | Yes, this is the index required for `$vectorSearch` |
| `$search` | Search pipeline (full-text/hybrid and related features) | Different from the `$vectorSearch` stage |
| `$vectorSearch` | ANN/ENN vector query | Requires compatible environment, index, and data |
| Embedding model | Generates vectors | Does not create or operate the search index |
| `mongot` | Search service/process in MongoDB Search architecture | Must be deployed/managed depending on the deployment |

---

## 2. Distinguishing MongoDB Atlas from Self-Managed MongoDB

### 2.1. Atlas Cloud

**MongoDB Atlas** is a managed cloud database service. On compatible clusters, Atlas manages the database infrastructure and Search/Vector Search components according to the deployment architecture. This is the simplest way to get started with `$vectorSearch`.

An application can connect via a MongoDB connection string and run aggregations through mongosh or a driver once the index is created.

### 2.2. Self-Managed MongoDB Community/Enterprise

By 2026, it is no longer accurate to state that “Vector Search **only** runs on Atlas cloud”. MongoDB has announced Search/Vector Search support for **self-managed** deployments, with support starting at MongoDB **8.2 and later** in compatible deployments and requiring deployment of the search component.

Key differences:

- Atlas cloud: Atlas manages much of the search infrastructure.
- Self-managed: operations teams must deploy, configure, and monitor `mongod`/`mongot` and supporting infrastructure.
- Not every older MongoDB Community release can gain `$vectorSearch` simply by upgrading the driver.

### 2.3. Local Atlas Deployment

**Atlas CLI local deployment** is an option for local learning and development, typically via containers, allowing you to test Search/Vector Search on a developer machine in a MongoDB-supported way.

This does **not** mean installing an arbitrary standalone `mongod` gives you Vector Search. Local Atlas deployments have their own setup workflow, images, and search services.

### 2.4. True/False Examples of Environment Requirements

| Environment | Can it run `$vectorSearch`? | Key conditions |
|---|---|---|
| Atlas cloud with supported server/tier | Yes | Version, index, permissions, cluster capacity |
| Supported Atlas Free/Flex | Yes, for learning/testing with limits | Quotas, index creation method, resources, not production-ready by default |
| Atlas Dedicated | Yes | Appropriate cluster/search configuration |
| Atlas Dedicated + Search Nodes | Yes | Search node support in region/tier, sizing |
| Compatible Atlas CLI local version | Yes | Atlas CLI, Docker/image, and compatible deployment |
| Properly configured self-managed Community 8.2+ | Yes | OS support, `mongot`, connectivity, and resources |
| Supported self-managed Enterprise 8.2+ model | Yes | Operator/deployment/edition requirements per docs |
| Standard self-managed Community 6.0/7.0/8.0 | Cannot assume supported | Not identical to an Atlas cluster of the same version |
| Older standalone MongoDB with `mongod` only | Cannot be considered ready | Lacks appropriate search process/index |

**Conclusion:** Server version is a **necessary condition per branch**, not a sufficient condition. Verify deployment type, search infrastructure, and feature support.

---

## 3. Compatibility Matrix by MongoDB Version

### 3.1. ANN on Atlas

**Approximate Nearest Neighbors (ANN)** via `$vectorSearch` is documented by MongoDB for Atlas:

- **6.0** branch: from **6.0.11** per published thresholds.
- **7.0** branch: from **7.0.2**.
- Newer branches: according to versions officially supported by MongoDB.

Do not read “6.0.11+” as meaning “every 7.0.0/7.0.1 release is guaranteed supported”; each branch has its **own minor/patch threshold**.

### 3.2. ENN — Exact Nearest Neighbors

**Exact Nearest Neighbors (ENN)** has a higher version threshold than ANN. MongoDB documentation lists **6.0.16**, **7.0.10**, **7.3.2**, or subsequent supported versions per branch.

Why distinguish them?

- ANN uses approximate search structures to balance recall and latency.
- ENN evaluates vectors via an exhaustive/precise search mechanism, typically at higher cost.
- Adding `exact:true` in code against an older server does not enable ENN.
- Compatibility behavior must be verified against the actual cluster, not merely by comparing major versions.

### 3.3. `$unionWith` and `$vectorSearch`

According to the MongoDB Manual, starting from **MongoDB 8.0**, `$vectorSearch` is supported inside `$unionWith` subject to corresponding stage constraints.

On older versions, a pipeline nesting `$vectorSearch` inside `$unionWith` may fail compatibility even though a standalone vector query works.

### 3.4. `$facet` and `$lookup` Subpipelines

`$vectorSearch` **cannot be placed inside**:

- A `$facet` pipeline.
- A `$lookup` subpipeline.

However, you can pass results from `$vectorSearch` into appropriate downstream stages, such as `$lookup` after vector results are produced. That is the difference between a **stage inside a subpipeline** and a **downstream stage processing Vector Search output**.

### 3.5. New Features Depend on More Than Binary Version

Some Search/Vector Search capabilities (such as hybrid ranking configurations, automated embeddings, indexing options, view support, tuning/quantization) also depend on:

- Search component and rollout.
- Cluster tier/search architecture.
- Preview/GA status.
- Region and edition.
- Index definition format.
- API options currently supported in docs.

Do not use the minimum ANN version to infer that **all** new Search features are present.

### 3.6. Quick Check Matrix

| Feature | Atlas version cited in docs | Other conditions |
|---|---|---|
| ANN with `$vectorSearch` | 6.0.11 on 6.0 branch; 7.0.2 on 7.0 branch; newer supported releases | Vector Search index and compatible cluster |
| ENN (`exact:true`) | 6.0.16, 7.0.10, 7.3.2 and supported branches/releases | Compatible index and query, compute cost |
| `$vectorSearch` inside `$unionWith` | Starting in 8.0 | Current aggregation constraints |
| `$vectorSearch` inside `$facet` | Unsupported under current constraints | Redesign the pipeline |
| `$vectorSearch` inside `$lookup` subpipeline | Unsupported under current constraints | Can run `$lookup` after vector results |
| Self-managed Community Vector Search | 8.2+ on supported environments/OS | Install and operate search components |
| Self-managed Enterprise Vector Search | 8.2+ per published deployment requirements | Verify Kubernetes Operator/edition support |
| Atlas CLI local Vector Search | Compatible local deployment; local docs cite MongoDB 7.0.5+ | Atlas CLI, Docker, supported images |
| Automated embedding | Depends on deployment/feature; some self-managed capabilities in preview | Check dedicated feature page; do not infer from ANN gate |

This table is a guide as of writing; **actual capability must be verified** on the target deployment.

---

## 4. Why Are Atlas and Self-Managed Different Even on the “Same MongoDB 7.0”?

### 4.1. Server Version Does Not Include the Entire Search Architecture

A compatible 7.0.x Atlas cluster has search services deployed by Atlas. A machine with a plain MongoDB Community 7.0.x installation does not automatically include that same infrastructure.

~~~text
Compatible Atlas:
  mongod
    + managed search process/index
    + Atlas control plane
    + appropriate permissions and configuration
  -> $vectorSearch

Standard Community 7.0 installation:
  mongod
  -> do not expect $vectorSearch to be available out of the box
~~~

### 4.2. What Is `mongot`?

MongoDB Search/Vector Search relies on search process/index infrastructure (commonly known as `mongot`). This is not a B-tree index stored inside the `mongod` engine in the same manner as `createIndex({field:1})`.

On Atlas, search workloads may use resources co-located with database nodes or **Dedicated Search Nodes**. On self-managed 8.2+, operators must deploy these search components per the corresponding documentation.

### 4.3. Both Parts Must Be Checked

~~~text
Is the MongoDB version sufficient?
        |
        +-- No -> upgrade/migrate
        |
        +-- Yes
              |
              v
Does the deployment/tier support it?
        |
        +-- No -> switch deployment
        |
        +-- Yes
              |
              v
Is the search service/index active?
        |
        +-- No -> configure/build/diagnose
        |
        +-- Yes
              |
              v
Is the vector query valid?
~~~

### 4.4. Easy-to-Make Mistakes

- Installing Atlas CLI does not automatically upgrade an old cloud cluster to a new version.
- Upgrading the Java driver does not upgrade MongoDB Server or the search service.
- Creating a B-tree index on a vector array does not replace a vector index.
- A fresh MongoDB 8.2 server still requires proper Search/Vector Search setup for self-managed environments.
- Testing on Atlas Flex does not guarantee production throughput.
- Testing on Atlas local does not automatically guarantee identical versions/index options on Atlas cloud.

---

## 5. Atlas Free, Flex, and Dedicated: Which Environment Should You Choose?

### 5.1. Free Cluster

The Free tier (called `M0` in many older docs) is intended for learning and experimenting with certain Search/Vector Search capabilities within limits.

Several limits documented by MongoDB include:

- Maximum of **3 combined Search/Vector indexes** on Free.
- Possible restrictions on **creating indexes via mongosh/driver**; when programmatic creation fails on Free, check creating the index in the **Atlas UI** per tier documentation.
- Small CPU/RAM/storage and throughput; never set production SLOs on a Free lab.

### 5.2. Flex Cluster

Flex is a low-cost option for development/POC:

- Per related index limit docs, maximum of **10 Search/Vector indexes** on Flex.
- Subject to resource contention and variable latency, not equivalent to dedicated Search Nodes.
- Atlas manages version upgrades automatically under Flex policies; users do not necessarily choose release cadence.

### 5.3. Dedicated Cluster

Dedicated tiers from `M10` upward allow sizing capacity more appropriately. M10/M20 can be used for prototyping, though RAM/index size and shared resource contention remain important.

For production, benchmark your workload to choose an appropriate cluster tier and Search Nodes count/tier.

### 5.4. Dedicated Search Nodes

For large search workloads, separating Search Nodes from database nodes helps:

- Reduce RAM/CPU contention between `mongod` and the search service.
- Scale search and database relatively independently.
- Dedicate resources to indexes and queries.
- Monitor latency, memory, and search saturation more clearly.

However, **Dedicated Search Nodes are not available in every region/provider/tier**. Per Vector Search deployment docs, availability varies across AWS, Azure, and Google Cloud. Always verify your cluster's cloud region.

### 5.5. Selection Table

| Goal | Suggested environment | Notes |
|---|---|---|
| Learning syntax, 10–100 documents | Atlas Free or compatible Atlas CLI local | Check permissions, index quotas |
| Small team demo | Flex or small Dedicated | Do not extrapolate production SLA |
| POC with backend integration | Small/mid Dedicated or local if suitable | Measure indexing latency and query p95 |
| Stable production latency | Dedicated and consider separate Search Nodes | Capacity planning, alerts, region support |
| Data required on-prem/self-managed | Community/Enterprise 8.2+ with search infrastructure | OS support, operating `mongot`, backup/upgrades |
| CI needing end-to-end Vector Search | Atlas test cluster or supported Atlas local | Do not use old standalone MongoDB expecting the stage to run |

### 5.6. Do Not Equate “Allowed on Free” with “Sufficient for Production”

A feature being supported on Free does not mean:

- There are no quotas.
- Latency is always low.
- Every API is permitted to create indexes.
- Index rebuilds have zero impact.
- Dedicated Search Nodes are included.
- Backups, HA, and SLOs match Dedicated.

---

## 6. Atlas Local and Running on a Development Machine

### 6.1. Atlas CLI Local Model

MongoDB documents creating a **local Atlas deployment** via Atlas CLI, using Docker or a supported runtime to spin up a single-node replica set with Search capabilities.

Example interactive command:

~~~bash
atlas local setup
~~~

Once the deployment is created and drivers can connect, create Search/Vector Search indexes using tools supported by the local deployment, such as Atlas CLI local search index commands or mongosh depending on compatibility.

### 6.2. Documented Requirements

Atlas CLI local docs specify:

- A **compatible Atlas CLI version** (current commands use the `atlas local` namespace).
- Docker or a supported container runtime installed.
- For local Vector Search, docs specify **MongoDB 7.0.5 or newer** in the local Atlas deployment for appropriate capability.
- Older local deployments may not upgrade seamlessly; images/deployments may need replacing per guidance after preserving important data.
- Local machine CPU/RAM/disk resources are real practical limits.

### 6.3. Windows and macOS: Distinguish Two Cases

There are two distinct statements:

1. Atlas CLI local deployments using containers are documented for development OSes, including Windows/macOS under container runtime requirements.
2. Self-managed MongoDB Community Search/Vector Search 8.2+ is described in product docs as supporting **Linux**, including Docker/containers, and **not supporting native Search/Vector Search installation on Windows/macOS** per that documentation.

Do not take the ability to run **Atlas local via Docker on Windows** as implying that **native Community `mongot` on Windows** is equally supported.

### 6.4. Watch Out for Plain Docker MongoDB

For example:

~~~bash
docker run --name ordinary-mongo -p 27017:27017 mongo:7
~~~

only starts an ordinary MongoDB image and does **not** mean MongoDB Vector Search is enabled. It may also be a standalone `mongod` with no search service. Running `db.collection.aggregate([{$vectorSearch:...}])` on this image can therefore fail.

### 6.5. Local Is for Learning, Not a Production Replica

Single-node local deployments lack multi-region HA, autoscaling, backup policies, and Search Node isolation like production Atlas. Demo data and indexes must have a migration/re-initialization plan when promoting to Atlas cloud or self-managed production.

---

## 7. Self-Managed Community/Enterprise Starting from MongoDB 8.2

### 7.1. Product Milestone

MongoDB announced a preview of Search/Vector Search for self-managed Community/Enterprise in 2025, followed by broader release announcements in 2026. Older articles claiming “Atlas only” may therefore be outdated.

### 7.2. More Than Just the `mongod` Binary

A self-managed deployment requires:

- A suitable MongoDB Server version, at minimum a supported branch like 8.2+.
- The Search/Vector Search process `mongot`, properly configured and connected.
- A supported operating system/architecture per documentation.
- Security configuration, TLS, users/roles.
- Sufficient RAM/CPU/disk for vectors/indexes.
- Operational procedures for index builds, backups, and upgrades.
- Network connectivity between components.
- Monitoring for both the search service and the database.

### 7.3. Community Edition

MongoDB Community Edition documentation describes Search/Vector Search for Community 8.2+ on supported Linux distributions, including Docker/container and Kubernetes scenarios. Do not assume native Windows/macOS installations have the same capability.

### 7.4. Enterprise

The MongoDB Manual states `$vectorSearch` support on MongoDB Enterprise 8.2+ deployments **with Kubernetes Operator** under corresponding conditions. Self-managed Enterprise Advanced models must consult deployment docs and `mongot` compatibility for the exact version/edition.

Do not claim that every standalone Enterprise 8.2 started with a single command comes with a search process pre-configured.

### 7.5. Self-Managed Trade-Offs

Benefits:

- Control over data residency/on-prem hosting.
- Infrastructure customization.
- Integration with internal security policies.
- Avoiding complete reliance on Atlas cloud for search capability.

Trade-offs:

- Operations team owns version compatibility and the search process.
- Must size RAM/index/query workloads manually.
- Must manage upgrades, failover, monitoring, and maintenance.
- Preview/GA features or certain advanced options may differ from Atlas.
- Local benchmark results do not automatically translate to production.

---

## 8. Index Requirements: Search Indexes Differ from B-Tree Indexes

### 8.1. Do Not Use `createIndex({embedding:1})`

The command:

~~~javascript
db.products.createIndex({
  embedding: 1
});
~~~

creates an ordinary index, **not** a vector-search ANN index.

### 8.2. Index Definition for `vectorSearch`

Example Vector Search index for 4-dimensional embeddings:

~~~javascript
{
  name: "product_vector_index",
  type: "vectorSearch",
  definition: {
    fields: [
      {
        type: "vector",
        path: "embedding",
        numDimensions: 4,
        similarity: "cosine"
      },
      {
        type: "filter",
        path: "tenantId"
      },
      {
        type: "filter",
        path: "status"
      },
      {
        type: "filter",
        path: "category"
      }
    ]
  }
}
~~~

- `type:"vectorSearch"` specifies the Search index type.
- The `type:"vector"` field specifies the vector path and dimensionality.
- `numDimensions` must match the embedding model.
- `similarity` selects a metric from those supported in documentation.
- `type:"filter"` fields enable pre-filtering on corresponding metadata.
- The index name will be referenced by `$vectorSearch.index`.

### 8.3. Creating an Index via mongosh When Supported by Tier/Version

~~~javascript
use vector_compat_lab

db.products.createSearchIndex({
  name: "product_vector_index",
  type: "vectorSearch",
  definition: {
    fields: [
      {
        type: "vector",
        path: "embedding",
        numDimensions: 4,
        similarity: "cosine"
      },
      {
        type: "filter",
        path: "tenantId"
      },
      {
        type: "filter",
        path: "status"
      },
      {
        type: "filter",
        path: "category"
      }
    ]
  }
});
~~~

**Important:** This example uses the Search index creation API, which the environment must support. If a Free cluster restricts programmatic creation, create it via the **Atlas UI** per tier docs rather than treating `Command not found` as proof that Vector Search is completely unavailable.

### 8.4. Index Status

An index creation command succeeding does not mean the index is finished. It may still be building/syncing. Queries immediately afterward may return incomplete results or report the index is not ready.

Use the Atlas UI / Search index list or corresponding APIs to confirm index status before integration testing.

### 8.5. Modifying an Index Definition

When changing fields, dimensions, similarity, or quantization:

- The search index may need to rebuild.
- There is a period during which the index has not finished updating.
- Search resource consumption increases during the build.
- Backward compatibility with currently querying applications must be verified.
- Production should have a rollout/rollback strategy, potentially using a new index name prior to cutover.

Do not change `numDimensions` in the index while stored data and queries still use vectors of the old dimensionality.

---

## 9. Embedding Dimensionality and Data Requirements

### 9.1. `numDimensions` Must Match

Suppose the embedding model outputs 768-element vectors. The index must declare the matching dimension, for example:

~~~javascript
{
  type: "vector",
  path: "embedding",
  numDimensions: 768,
  similarity: "cosine"
}
~~~

If a query vector has 384 dimensions while the index expects 768, the query is invalid or will not behave as expected.

### 9.2. Dimensionality Limits

MongoDB Vector Search documentation cites a maximum vector limit of **8192 dimensions** for supported types/configurations. Some quantized vector formats impose extra rules, such as multiples of 8 when using binary quantization.

Do not just check `length <=8192`; also check representation type, exact dimensionality, model, and quantization options.

### 9.3. Sample Vector Data

~~~javascript
use vector_compat_lab

db.products.insertMany([
  {
    _id: "P-101",
    tenantId: "tenant-a",
    title: "Waterproof rain jacket",
    category: "OUTDOOR",
    status: "PUBLISHED",
    embedding: [0.10, 0.60, 0.20, 0.30]
  },
  {
    _id: "P-102",
    tenantId: "tenant-a",
    title: "Compact folding umbrella",
    category: "ACCESSORY",
    status: "PUBLISHED",
    embedding: [0.14, 0.57, 0.23, 0.28]
  },
  {
    _id: "P-103",
    tenantId: "tenant-b",
    title: "Kids raincoat",
    category: "OUTDOOR",
    status: "PUBLISHED",
    embedding: [0.12, 0.59, 0.19, 0.31]
  },
  {
    _id: "P-104",
    tenantId: "tenant-a",
    title: "Unpublished product",
    category: "OUTDOOR",
    status: "DRAFT",
    embedding: [0.13, 0.56, 0.25, 0.29]
  }
]);
~~~

The four-dimensional vectors here are **only for testing execution and syntax**. They are not generated by a real embedding model, so do not use these results to judge semantic search quality.

### 9.4. Vectors Must Share the Same Embedding Space

Do not mix embeddings from model A (384 dims) and model B (768 dims). Even if two models happen to share the same dimensionality, they do not necessarily share the same semantic space.

A query vector produced by a different model can yield meaningless rankings even when sizes match.

### 9.5. Upgrading the Embedding Model

You need a plan:

1. Select the new model/version.
2. Add a new embedding field, e.g. `embeddingV2`.
3. Re-embed data using a retry-capable pipeline.
4. Create the corresponding new index.
5. Query and verify recall/latency.
6. Gradually shift traffic to the new index.
7. Clean up the old index/field once stable.

Never switch the query model before re-indexing the data accordingly.

### 9.6. Data Types

Vectors can be stored as numeric arrays or supported BSON BinData formats in certain configurations. When using quantization, additional precision/encoding constraints apply. Never convert float arrays into arbitrary binary blobs expecting the vector index to understand them.

---

## 10. ANN and ENN: Different Query Requirements

### 10.1. ANN — Approximate Nearest Neighbors

ANN uses approximate search structures to reduce latency compared to an exhaustive scan. Queries typically specify:

~~~javascript
{
  $vectorSearch: {
    index: "product_vector_index",
    path: "embedding",
    queryVector: [0.11, 0.58, 0.22, 0.29],
    numCandidates: 100,
    limit: 5
  }
}
~~~

`numCandidates` controls how many candidates the algorithm considers. Raising it can improve recall but also increases latency and cost.

### 10.2. Guidelines for Choosing `numCandidates`

MongoDB suggests a starting guideline of setting `numCandidates` to at least roughly **20 times `limit`** for ANN to improve recall, though you must benchmark against your data distribution and filtering selectivity. For example, `limit:5` and `numCandidates:100` is an experimental starting point.

This is not a formula guaranteeing minimum recall on every dataset.

### 10.3. ENN — Exact Nearest Neighbors

ENN uses `exact:true`:

~~~javascript
{
  $vectorSearch: {
    index: "product_vector_index",
    path: "embedding",
    queryVector: [0.11, 0.58, 0.22, 0.29],
    exact: true,
    limit: 5
  }
}
~~~

Do not supply `numCandidates` as a required parameter for ENN. Check ENN version thresholds before using it, as a cluster may support ANN without yet supporting ENN.

### 10.4. When to Use Which?

| Scenario | ANN | ENN |
|---|---|---|
| Large dataset, low latency matters | Usually appropriate | Can be very expensive |
| Need to benchmark recall | Query being tuned | Serves as ground-truth reference |
| Small dataset after tight pre-filter | Can be used | May fit for exact top-k |
| Cluster version supports ANN only | Yes | No |
| Require exact nearest vector ranking | Not strictly guaranteed | Suitable if supported and resources allow |

### 10.5. Do Not Confuse “Exact Vector” with Business Truth

ENN only computes exact nearest neighbors under the metric on indexed vectors. If the embedding model does not represent meaning well, ENN will still return unhelpful results to the user. Exact nearest does not guarantee factual correctness in RAG.

---

## 11. End-to-End Query Example on a Compatible Atlas Cluster

### 11.1. Prerequisites Check

- Cluster supports `$vectorSearch`.
- Collection `vector_compat_lab.products` exists.
- Index `product_vector_index` has finished building.
- Index `embedding` has 4 dimensions.
- User has read privilege on the collection.
- Valid four-dimensional query vector.

### 11.2. Query with Pre-Filter

~~~javascript
const queryEmbedding = [0.11, 0.58, 0.22, 0.29];

db.products.aggregate([
  {
    $vectorSearch: {
      index: "product_vector_index",
      path: "embedding",
      queryVector: queryEmbedding,
      numCandidates: 100,
      limit: 5,
      filter: {
        tenantId: "tenant-a",
        status: "PUBLISHED"
      }
    }
  },
  {
    $project: {
      _id: 1,
      title: 1,
      category: 1,
      tenantId: 1,
      status: 1,
      score: {
        $meta: "vectorSearchScore"
      }
    }
  }
]);
~~~

### 11.3. Role of the Pre-Filter

`filter` restricts the candidate space to avoid bringing documents with the wrong tenant or status into ranking. This is especially critical for multi-tenant applications.

**Never** trust a client-supplied tenantId to determine access rights. In production, tenant/permission filters must be constructed from an authenticated context.

### 11.4. Requirement for Pre-Filterable Fields

Fields filtered in `$vectorSearch.filter` must be indexed with `type:"filter"` in the vector search index. Supported filter data types and operators are **not identical** to all MongoDB aggregation/MQL operators.

For example, if the index only defines `embedding` without `tenantId`, a query filtering on `tenantId` may error or fail to behave as intended.

### 11.5. Do Not Assume `filter` Supports All of MQL

Documentation lists supported filter field types such as boolean, date, numeric, ObjectId, string, UUID, and corresponding arrays; the list of supported operators is bounded. Do not put geo predicates, complex regexes, or arbitrary aggregation expressions inside `filter` without checking the support page.

### 11.6. `$project` at the End

`$project` ensures only necessary fields and the score are returned, avoiding sending large embedding vectors to the frontend unnecessarily.

### 11.7. What Is Score?

`{$meta:"vectorSearchScore"}` returns the score computed by the search stage. The score serves for **relative ranking** within the same query/index, not as a probability such as “94% chance this product is right”.

If you change the metric/model or compare ANN vs. ENN, score distributions can differ; never hard-code thresholds without evaluation.

---

## 12. Creating Indexes via Atlas UI and via API

### 12.1. Why Know Both Approaches?

Some environments/tiers allow index creation through the Atlas UI while restricting programmatic commands; conversely, production CI/CD typically requires index-as-code.

### 12.2. Atlas UI

General workflow:

1. Select the correct Atlas project and cluster.
2. Open the Search/Vector Search indexes section.
3. Choose the database and collection.
4. Create an index of type `Vector Search`.
5. Declare the vector path, dimensions, similarity, and filter fields.
6. Wait for the index status to become active/ready.
7. Run a test query in the UI or mongosh.

Screen labels may change across UI updates; follow current documentation when performing these steps.

### 12.3. Programmatic Index Creation

On supported deployments:

~~~javascript
db.products.createSearchIndex({
  name: "product_vector_index",
  type: "vectorSearch",
  definition: {
    fields: [
      {
        type: "vector",
        path: "embedding",
        numDimensions: 4,
        similarity: "cosine"
      },
      {
        type: "filter",
        path: "tenantId"
      },
      {
        type: "filter",
        path: "status"
      }
    ]
  }
});
~~~

This command demonstrates creation; when re-running with the same index name or when the index quota is full, handle the existing state instead of creating duplicates.

### 12.4. Checking the Index List

On supported servers/drivers, helper methods exist to list search indexes, for example:

~~~javascript
db.products.getSearchIndexes();
~~~

The output includes metadata/index status depending on the version. If the helper is unavailable, use the Atlas UI or equivalent API; do not assume a missing helper means all vector features are unsupported.

### 12.5. Do Not Rely on `getIndexes()` Alone

`getIndexes()` is normally used to inspect standard collection indexes. MongoDB Search/Vector Search indexes are managed through separate Search index APIs; do not look solely at the B-tree index list and conclude no vector index exists.

---

## 13. Access Permissions and Network Configuration

### 13.1. Distinct Permission Layers

- **Atlas project permissions**: permission to manage Search indexes via UI/API.
- **Database user permissions**: permission to read data and run queries.
- **Index management privileges**: permission to create/edit/delete Search indexes in the corresponding environment.
- **Network allowlist/private endpoints**: whether the client is allowed to connect.
- **TLS/credentials**: connection authentication.

A user who can read a collection does not necessarily have permission to create indexes.

### 13.2. Search Index Creation Privileges

Atlas documentation lists relevant roles such as `Project Search Index Editor` or a higher role sufficient to manage/inspect Search indexes. Corresponding database privileges and index management methods via UI/driver must also be determined.

In production, prefer least privilege:

- CI/CD or an admin service manages indexes.
- Application runtime only needs required read/query permissions.
- Do not grant Project Owner to a service that only performs retrieval.

### 13.3. Network Errors Differ from Vector Search Errors

If the client cannot connect to Atlas due to IP allowlists, DNS, TLS, username/password, or private endpoints, `$vectorSearch` has not even had a chance to run. Do not modify index definitions to troubleshoot MongoDB connection failures.

### 13.4. Embedding Providers Have Their Own Requirements

If the application uses an external API to generate embeddings:

- Provider API keys and quotas.
- Model and dimensionality.
- Data residency and PII policies.
- Latency and timeouts.
- Rate limiting.
- Authorization to send data to a third party.

MongoDB Vector Search **does not automatically** guarantee that the embedding provider is always available.

---

## 14. Search Indexes Are Eventually Consistent

### 14.1. Index Builds Are Not Instantaneous

When the application inserts/updates documents, the Search process must receive and index the changes. Search indexes update **asynchronously**; indexing lag may occur.

~~~text
T0: insert MongoDB document
T1: commit/ack succeeds
T2: Search index receives change
T3: Vector Search query begins seeing the document
~~~

At T1, the document write succeeded, yet a vector query may not return the new document yet.

### 14.2. Vector Search Does Not Promise Read-Your-Writes

A MongoDB transaction committed with `w:"majority"` does not prove the Search index updated synchronously. Vector Search is not a tool to immediately verify whether a write exists the way a normal primary read does.

### 14.3. For Business Flows Requiring Immediate Accuracy

For example, checking whether a product is in stock before selling:

1. `$vectorSearch` suggests candidates based on indexed metadata.
2. The application can re-read authoritative state from MongoDB.
3. When creating the order, use an **atomic conditional update/transaction** to verify inventory and permissions.
4. Never use the vector index as a lock or reservation.

### 14.4. During Index Rebuilds

A new index definition needs to build/rebuild. Avoid rolling out queries depending on new fields before the index is ready. Per documentation, some rebuilds continue serving queries using the old index definition while the new index is built, which does not mean the new capability is active yet.

### 14.5. RAG and Retrieving Newly Uploaded Documents

If a RAG application needs to show documents right after upload, you can:

- Wait for the embedding/indexing pipeline to finish via dedicated status tracking.
- Let clients view the newly uploaded document through standard MongoDB reads.
- Show a “processing” UI state.
- Avoid claiming “immediately after upload, retrieval queries are guaranteed to find it”.

---

## 15. Aggregation Constraints by Version and Stage

### 15.1. `$vectorSearch` at the Start of the Pipeline

Standard query:

~~~javascript
db.products.aggregate([
  {
    $vectorSearch: {
      index: "product_vector_index",
      path: "embedding",
      queryVector: [0.11, 0.58, 0.22, 0.29],
      numCandidates: 100,
      limit: 5
    }
  },
  {
    $project: {
      title: 1,
      score: {
        $meta: "vectorSearchScore"
      }
    }
  }
]);
~~~

### 15.2. Why Not `$match` First?

Do not write:

~~~javascript
db.products.aggregate([
  { $match: { tenantId: "tenant-a" } },
  {
    $vectorSearch: {
      index: "product_vector_index",
      path: "embedding",
      queryVector: [0.11, 0.58, 0.22, 0.29],
      numCandidates: 100,
      limit: 5
    }
  }
]);
~~~

`$vectorSearch` must be the first stage in any pipeline where it appears. Move supported predicates into the indexed `filter`; business filters that do not support pre-filtering can run afterward, keeping in mind that post-filtering can reduce result counts.

### 15.3. Pre-Filter vs. Post-Filter

If you retrieve 5 candidates and only then apply `$match:{tenantId:"tenant-a"}`, you might end up with 0–2 docs even though tenant-a has many other similar docs outside the global top 5.

If the goal is “top 5 **within tenant-a**”, you must use a **tenant pre-filter** inside `$vectorSearch` with a corresponding filter field in the vector index.

### 15.4. `$facet` / `$lookup` / `$unionWith`

- Do not nest `$vectorSearch` inside a `$facet` stage.
- Do not nest `$vectorSearch` inside a `$lookup` subpipeline.
- You may place `$lookup` **after** `$vectorSearch` to enrich results per pipeline semantics.
- Starting in MongoDB 8.0, rules exist for using `$vectorSearch` inside `$unionWith`.

If hybrid search requires combining text and vector results, choose a compatible pipeline and feature/version rather than copying an 8.x example onto 6.0.

### 15.5. Views and Time-Series Collections

MongoDB Search/Vector Search has limitations by collection/view type and version. Search feature compatibility docs state time-series collections are not supported; starting in certain newer releases like 8.3, Search/Vector Search queries on time-series collections may return an explicit error instead of empty results.

Do not move a pipeline from a regular collection onto a time-series collection or view assuming stage support is identical. Check documentation for the **exact version**.

---

## 16. Vector Search Index and Filter Index Fields

### 16.1. Indexing Multiple Field Types

~~~javascript
{
  fields: [
    {
      type: "vector",
      path: "embedding",
      numDimensions: 768,
      similarity: "cosine"
    },
    {
      type: "filter",
      path: "tenantId"
    },
    {
      type: "filter",
      path: "status"
    },
    {
      type: "filter",
      path: "price"
    }
  ]
}
~~~

This example enables pre-filtering by tenant, status, and price within the operators/field types MongoDB supports.

### 16.2. Filtering Is Not Arbitrary

Supported types include string, numeric, boolean, date, ObjectId, UUID, and corresponding arrays. Do not assume that because `$match` allows `$regex`, `$geoWithin`, or a complex `$expr`, `$vectorSearch.filter` will also accept them.

### 16.3. Boolean Combinations

You can use supported operators such as `$and`, `$or`, `$in`, `$eq`, and range comparisons within documented limits. For example:

~~~javascript
filter: {
  $and: [
    { tenantId: "tenant-a" },
    { status: "PUBLISHED" },
    { category: { $in: ["OUTDOOR", "ACCESSORY"] } }
  ]
}
~~~

If a field is not indexed as `filter`, add it to the index definition and wait for the build to finish.

### 16.4. Security Matters

A vector index can hold embeddings from multiple tenants. If the application fails to pre-filter by a trusted tenant context and returns results across all tenants, data can leak through similarity results.

Never allow clients to pass arbitrary BSON filters to decide the tenant; construct filters from user auth and whitelisted fields.

### 16.5. Indexing Many Fields Increases Cost

Every Search index consumes RAM/CPU/disk and adds sync overhead as documents change. Do not create indexes for every possible filter combination; design for primary workloads and measure.

---

## 17. Java Sync Driver: Running `$vectorSearch` When the Server Supports It

### 17.1. Driver and Server Are Separate Conditions

The Java Sync Driver provides the MongoDB aggregation API. A newer driver does not make an older cluster support a new stage; conversely, a newer cluster may also require a driver version/codec supporting index creation and proper BSON handling.

Typically, raw aggregation stages can be built with `Document` on drivers supporting aggregation even when specialized builder helpers vary by version.

### 17.2. Java Query Example

~~~java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import org.bson.Document;

import java.util.List;

public class AtlasVectorSearchExample {

    public static void search(MongoClient client) {
        MongoDatabase database =
            client.getDatabase("vector_compat_lab");

        MongoCollection<Document> products =
            database.getCollection("products");

        List<Double> queryVector =
            List.of(0.11, 0.58, 0.22, 0.29);

        Document filter =
            new Document("tenantId", "tenant-a")
                .append("status", "PUBLISHED");

        Document vectorSpec =
            new Document(
                "index",
                "product_vector_index"
            )
                .append("path", "embedding")
                .append("queryVector", queryVector)
                .append("numCandidates", 100)
                .append("limit", 5)
                .append("filter", filter);

        Document vectorStage =
            new Document("$vectorSearch", vectorSpec);

        Document projection =
            new Document(
                "$project",
                new Document("title", 1)
                    .append("category", 1)
                    .append(
                        "score",
                        new Document(
                            "$meta",
                            "vectorSearchScore"
                        )
                    )
            );

        products.aggregate(
            List.of(vectorStage, projection)
        ).forEach(System.out::println);
    }
}
~~~

### 17.3. Conditions for Successful Execution

- `MongoClient` is connected and authenticated.
- Vector Search is supported on the deployment.
- Index name is exact.
- Index path and dimensions match.
- Query vector consists of numeric values properly serialized by the codec.
- `tenantId` and `status` are indexed as filter fields.
- Index build is complete.
- Server allows the `$vectorSearch` stage.

### 17.4. Java Model Dimension

In a real application, do not hard-code a four-dimensional vector. You can design:

~~~java
public final class EmbeddingRequest {
    private final String modelId;
    private final List<Double> vector;

    public EmbeddingRequest(
            String modelId,
            List<Double> vector) {

        this.modelId = modelId;
        this.vector = vector;
    }

    public int dimension() {
        return vector.size();
    }
}
~~~

The service should validate model ID, dimension, finite numeric values, and the matching index before querying.

### 17.5. Java 5.x Requirement for Advanced Features

Some MongoDB Vector Search guides show Java 5.x driver examples when introducing newer APIs or automated embeddings. Do not take a version table for an **automated embedding** feature and conclude all raw `$vectorSearch` aggregations share the exact same minimum driver version; check the specific driver API.

### 17.6. Do Not Create a New Client per Query

Maintain a long-lived `MongoClient` in the application to leverage connection pooling. Configure appropriate timeout/retry policies and never print URIs/passwords in logs.

---

## 18. Diagnosing Errors by Environment and Version

### 18.1. `Unrecognized pipeline stage name: '$vectorSearch'`

Likely causes:

- Server/deployment does not support the stage yet.
- Connected to the wrong cluster/host.
- Self-managed deployment runs `mongod` only without search infrastructure.
- Server version is on an older branch.

Diagnostic steps:

1. Print `db.version()` or `buildInfo` from the actual cluster.
2. Inspect the cluster in Atlas UI to confirm deployment/tier.
3. Check the compatibility matrix.
4. Inspect the index and search service.
5. Run a minimal query on the right collection.

“Just upgrade the driver” will not help when the server lacks the feature.

### 18.2. `Command not found` When Creating an Index

Likely causes:

- Cluster/version does not support the createSearchIndex command/helper.
- Free tier restricts programmatic creation.
- Driver/mongosh is too old for the helper method.
- Connected to the wrong environment.

Resolution: use Atlas UI per tier capabilities; check version requirements for programmatic Search index management; verify permissions.

### 18.3. Index Does Not Exist or Wrong Name

Query:

~~~javascript
{
  $vectorSearch: {
    index: "product_vector_index",
    path: "embedding",
    queryVector: [0.11, 0.58, 0.22, 0.29],
    numCandidates: 100,
    limit: 5
  }
}
~~~

If `product_vector_index` is misspelled or not ready yet, the query may error or return no results. Verify the exact database, collection, and index.

### 18.4. Zero Results Even Though the Collection Has Documents

Check:

- Is the index still building?
- Does the vector field have the right path and type?
- Are the embeddings indexed?
- Do dimensions match?
- Are the query model and stored model compatible?
- Did the pre-filter exclude all documents?
- Wrong tenant/status selected?
- Is ANN recall/numCandidates too low?
- Is the search index lagging behind writes?
- Are there collection/view restrictions?

### 18.5. Filter Field Not Indexed

If using:

~~~javascript
filter: {
  tenantId: "tenant-a"
}
~~~

while the index only defines the vector field, you must add:

~~~javascript
{
  type: "filter",
  path: "tenantId"
}
~~~

in the appropriate index definition version and wait for rebuild/sync.

### 18.6. Dimension Mismatch

A 768-dim index with a 1536-dim query vector is invalid. Never fix this by arbitrarily slicing the first 768 numbers; use the right embedding model and dimension.

### 18.7. Query Timeout / Error 489

MongoDB Vector Search has overload protection and can reject queries when demand exceeds search capacity. You should:

- Check search node saturation, queue, and rejection metrics.
- Lower `numCandidates` if benchmarks permit.
- Limit concurrency and apply backoff on retries.
- Adjust the cluster tier or Search Nodes.
- Optimize pre-filters, index, and payload.
- Never retry endlessly at the same load, making overload worse.

### 18.8. Query Is Too Slow Without Errors

Possible causes:

- ANN numCandidates is too high.
- ENN on an overly large dataset.
- Poor filter selectivity or representation.
- Insufficient search memory.
- No dedicated Search Nodes.
- Very large index without suitable quantization.
- Heavy downstream projections, network transfer, or extra aggregation stages.

Benchmark `p50/p95/p99`, recall, and index memory rather than looking at a single query execution.

---

## 19. Step-by-Step Environment Verification Workflow

A practical checklist when onboarding a new cluster:

~~~text
1. Can we connect to MongoDB?
          |
          v
2. Confirm deployment type:
   Atlas cloud / Atlas local / self-managed
          |
          v
3. Check MongoDB Server version
   and feature compatibility
          |
          v
4. Check tier, region, search service
          |
          v
5. Check Search index privileges
          |
          v
6. Create/inspect Vector Search index
          |
          v
7. Wait for index READY / ACTIVE
          |
          v
8. Run minimal $vectorSearch
          |
          v
9. Test pre-filter and score
          |
          v
10. Measure recall/latency/resources
          |
          v
11. Confirm production readiness
~~~

### 19.1. Checking Version in mongosh

~~~javascript
db.version();

db.adminCommand({
  buildInfo: 1
});
~~~

Do not share output containing sensitive environment details outside authorized teams when reporting errors.

### 19.2. Version Checks Do Not Replace Deployment Inspection

`db.version()` identifies MongoDB Server, but does not reveal everything:

- Free/Flex/Dedicated tier.
- Search Node availability.
- Preview flags or feature rollouts.
- Remaining index quota.
- Runtime resource pressure.
- Search service readiness.

Check Atlas UI/management APIs or self-managed configuration as well.

### 19.3. Checking Collection/Index

~~~javascript
use vector_compat_lab

db.products.countDocuments();

db.products.getSearchIndexes();
~~~

`getSearchIndexes()` works only when the environment/tooling supports the helper. If unavailable, inspect via Atlas UI or documented admin methods.

### 19.4. Smoke Test Query

~~~javascript
db.products.aggregate([
  {
    $vectorSearch: {
      index: "product_vector_index",
      path: "embedding",
      queryVector: [0.11, 0.58, 0.22, 0.29],
      numCandidates: 100,
      limit: 5
    }
  },
  {
    $project: {
      title: 1,
      score: {
        $meta: "vectorSearchScore"
      }
    }
  }
]);
~~~

Once the smoke test passes, proceed to add tenant filters, semantic evaluation, and throughput testing.

---

## 20. Applicability Matrix Across Application Environments

### 20.1. Personal Machine with Newly Installed MongoDB Community 7.0

- Can store embedding arrays as BSON.
- Should not expect `$vectorSearch` to work merely because the data holds vectors.
- Use compatible Atlas cloud/local or self-managed 8.2+ with search components per documentation.

### 20.2. Atlas Free Cluster on a Supported Version

- Can test features within tier limits.
- Small index quota.
- If the index creation helper fails, use Atlas UI as supported on Free.
- Never use Free benchmarks to predict production performance.

### 20.3. Atlas Flex

- Suitable for development/POC per docs.
- Watch total Search/Vector index counts and quotas.
- Versions are managed by Atlas.
- May experience contention and latency variation.

### 20.4. Atlas Dedicated on AWS/Azure/Google Cloud

- Confirm Search Nodes availability in your exact region and tier.
- Size for data/traffic and latency SLOs.
- Benchmark on a production-like dataset.
- Plan for index rebuilds and scaling.
- Tune the search tier independently when using Dedicated Search Nodes.

### 20.5. Self-Managed 8.2+ on Linux

- Configure mongod/mongot.
- Verify OS, container/Kubernetes support.
- Test Search index management and queries.
- Set up monitoring, resource limits, and backups/upgrades.
- Do not assume preview or Atlas-only features are available.

### 20.6. Java Backend Against a Compatible Cluster

- Verify the MongoDB Java driver supports the APIs used.
- Use raw BSON aggregation or appropriate builders.
- Manage connection pooling.
- Bound query concurrency.
- Provide fallbacks while search indexes are building or unavailable.

---

## 21. Comparing `$vectorSearch` with Legacy `knnBeta`

### 21.1. Why Do Old Articles Show Up Often?

Some early Atlas Vector Search articles used `$search` with the `knnBeta` operator. Current guides use `$vectorSearch` and `vectorSearch`-type indexes.

### 21.2. Do Not Copy Half of Each Syntax

A legacy form might look like:

~~~javascript
{
  $search: {
    index: "legacy_index_name",
    knnBeta: {
      vector: [0.11, 0.58, 0.22, 0.29],
      path: "embedding",
      k: 5
    }
  }
}
~~~

This example is only for **recognizing older documentation**, not recommended for new deployments. Support, deprecation, and migration paths depend on version.

### 21.3. Current API

~~~javascript
{
  $vectorSearch: {
    index: "product_vector_index",
    path: "embedding",
    queryVector: [0.11, 0.58, 0.22, 0.29],
    numCandidates: 100,
    limit: 5
  }
}
~~~

### 21.4. When Upgrading Legacy Systems

Review:

- Legacy Search index definitions.
- `knnBeta` syntax/behavior.
- `$vectorSearch` stage availability.
- Dedicated vectorSearch index creation.
- Similarity metric.
- Embedding dimensions.
- Pre-filter fields/operators.
- Result scores and ranking.
- Query latency/recall.
- Feature flags and rollback.

Never simply rename `knnBeta` to `$vectorSearch`.

---

## 22. Automated Embeddings and BYO Embeddings

### 22.1. BYO (Bring Your Own) Embeddings

The application generates vectors via an external model:

~~~text
Document
   |
Embedding provider/model
   |
Embedding array
   |
MongoDB store/index
   |
Query embedding from the same model
   |
$vectorSearch
~~~

Pros: full control over model, version, chunking, and where data is sent. Trade-offs: managing embedding jobs, retries, model upgrades, and index compatibility yourself.

### 22.2. Automated Embeddings

MongoDB offers an **Automated Embedding** capability in certain environments/features, generating embeddings from text during ingestion/query within supported bounds.

Do not assume this feature exists on every Free/Flex, self-managed deployment, region, or MongoDB version simply because basic `$vectorSearch` runs.

### 22.3. Preview vs. GA

Some Automated Embedding deployments/features are marked **Preview** in documentation. Preview capabilities may:

- Change API or availability.
- Have region and data-processing restrictions.
- Lack production SLAs equivalent to GA.
- Carry specific model/inference/cost terms.

Before using sensitive data, verify data residency, inference scope, retention policies, quotas, and current Preview warnings.

### 22.4. Impact on Index Design

BYO vectors typically use:

~~~javascript
{
  type: "vector",
  path: "embedding",
  numDimensions: 768,
  similarity: "cosine"
}
~~~

Automated embedding may use a different index definition and query shape—such as auto-generated field mappings or passing text queries instead of `queryVector` depending on the docs. **Do not mix syntax from one workflow into the other**.

---

## 23. RAM, Index Size, Quantization, and Search Nodes

### 23.1. Vectors Consume Memory

Suppose there are 1,000,000 documents with 1,536-dimensional float32 embeddings:

\[
1\,000\,000 \times 1\,536 \times 4\text{ bytes}
=6\,144\,000\,000\text{ bytes}
\]

That is approximately **6.14 GB** of raw vector data (decimal GB), **excluding** ANN graph/index metadata, runtime, JVM, and other data.

This is only a formula for estimating raw float data size, not sufficient RAM sizing for the Search index.

### 23.2. Search Indexes Need Both RAM and Disk

MongoDB Vector Search documentation notes that search indexes and `mongot` require memory; full precision typically demands significantly more resources than quantized forms. When automatic quantization retains full-fidelity vectors for rescoring/ENN, corresponding disk space may be required.

### 23.3. Quantization

Quantization can reduce vector memory footprint in exchange for quality/latency trade-offs and specific version/encoding requirements. Never enable binary/scalar quantization solely for RAM savings; measure recall and verify deployment support.

### 23.4. Co-Located vs. Dedicated Search

| Architecture | Benefits | Trade-offs |
|---|---|---|
| Search co-located on database nodes | Simple, fits demos/POCs | Competes for CPU/RAM with `mongod` |
| Dedicated Search Nodes | Isolates workloads, scales search independently | Cost and region/tier requirements |
| Self-managed co-located | Fewer nodes to manage | Shared resources and operations |
| Self-managed separate hosts | Isolates resources by design | More complex networking and operations |

### 23.5. Capacity Planning

Determine:

- Number of documents/vector fields.
- Dimensions and representation.
- Ingest/update rate.
- Query requests per second.
- `numCandidates`, `limit`, filter selectivity.
- RAM for indexes/JVM.
- Disk for index builds/quantized full fidelity.
- Search node CPU and network.
- Index rebuild time.
- p95/p99 latency and recall targets.

Never deploy an M10 just because “the feature can be enabled” if the workload exceeds its resources.

---

## 24. ANN Recall, Latency, and ENN as a Reference Baseline

### 24.1. What Is Recall?

Suppose ENN returns the exact top 10 document IDs under the metric, and ANN also returns top 10, overlapping on 9 IDs. A common measure is:

\[
\text{Recall@10} =
\frac{\#\text{documents overlapping with ENN top 10}}{10}
\]

In this example it is 0.9 (90%).

### 24.2. Trade-Off

Increasing `numCandidates` can improve recall at the cost of higher resources/latency. Decreasing it can lower latency at the risk of missing good neighbors.

### 24.3. ENN Benchmarks Require the Right Version

Before using ENN as ground truth, confirm your version supports `exact:true`. If the cluster supports ANN only, you can use a controlled offline distance calculator on a small dataset for benchmarking, provided you use the exact same metric and vector preprocessing.

### 24.4. Do Not Look at Single-Query Timing Alone

Measure:

- p50/p95/p99.
- Recall@K.
- Candidate counts.
- Filter selectivity.
- Vector index memory.
- Search node CPU.
- Query rejections.
- Indexing lag.
- Cost per query.

### 24.5. During Version Upgrades

Approximate search can shift rankings in some cases due to search engine updates and index rebuilds. Integration tests should assert **quality bands/recall** rather than demanding 100% identical IDs in every ANN response across versions.

---

## 25. Availability and Consistency in RAG Applications

### 25.1. RAG Pipeline

~~~text
User question
    |
    v
Embedding of question
    |
    v
$vectorSearch
    |
    v
Retrieve authorized relevant chunks
    |
    v
Optional reranking
    |
    v
LLM receives context
    |
    v
Generated answer with references
~~~

### 25.2. Having Vector Search Enabled Is Not Enough for Good RAG

You also need:

- Chunking policy.
- An embedding model suited to the language/domain.
- Metadata/permission filters.
- Source document and citation IDs.
- Versioning and re-embedding.
- Retrieval evaluation.
- Freshness/indexing latency handling.
- Prompt/context safety.
- Query cost/latency controls.
- Sensitive data policy.

### 25.3. Enforce Permissions Before Sending Context to the LLM

If Vector Search returns internal text chunks, document viewing permissions must be enforced **before providing them to the model**. Never rely on the LLM to “choose not to read” data that retrieval already placed into its context.

### 25.4. When Search Is Unavailable

The application can:

- Return a message stating retrieval is temporarily unavailable.
- Fall back to keyword search if designed and permission-checked.
- Serve from a cache with an appropriate TTL and policy.
- Never fabricate results or claim sources were checked when search failed.

### 25.5. When New Documents Are Not Indexed Yet

The UI can show a `PROCESSING` state and only mark documents `SEARCHABLE` once the embedding pipeline and index readiness are verified per application mechanisms. Never treat insert acknowledgment as meaning the vector index is already updated.

---

## 26. Production Rollout: From POC to Deployment

### Phase 1 — POC

- Choose compatible Atlas Free/Flex/local.
- Test with a small sample and index.
- Run `$vectorSearch` ANN.
- Test tenant/status filters.
- Verify dimensions and model.
- Measure baseline latency.
- Record exact server/tier/driver versions.

### Phase 2 — Staging

- Dataset close to production scale.
- Build index with the same model/dimensions.
- Benchmark ANN/ENN when supported.
- Test high-selectivity and low-selectivity filters.
- Test index rebuilds.
- Test search-unavailable failure modes.
- Monitor disk/RAM/search queues.

### Phase 3 — Production

- Dedicated tier/Search Nodes per demand and region support.
- Separate credentials for runtime and index admin.
- Backups/source embeddings for rebuilds.
- Monitoring p95/p99, indexing lag, resources, and errors.
- Canary queries and rollback plan.
- Capacity planning for incoming vector growth.
- Index migration strategy for model upgrades.

### 26.1. Do Not Jump Straight from Free to Production by Intuition

Resource limits on Free/Flex make latency, index builds, search node architecture, and autoscaling behave differently from Dedicated. Benchmark in staging resembling production.

### 26.2. Rolling Back Search Indexes

When changing an index definition or model:

1. Create a new index with a distinct name when possible.
2. Dual-ingest old/new embeddings or backfill.
3. Verify the new index is ready.
4. Canary traffic.
5. Compare quality/latency.
6. Shift traffic gradually.
7. Keep a rollback path for a defined window.
8. Delete the old index per quota/cost policy.

### 26.3. Managing Index Quotas

Free allows only a handful of indexes; you cannot create new indexes indefinitely on every deploy. When managing rollouts on small tiers, clean up demo indexes or upgrade deliberately. Avoid deleting an active production index before its replacement is ready.

---

## 27. Checking Versions and Capabilities in the Application

### 27.1. Do Not Just `if` on Version Strings

Code like:

~~~javascript
if (db.version() >= "7.0.2") {
  // use vectorSearch
}
~~~

has two problems:

- String comparison does not reflect numeric semver.
- Version alone does not reveal deployment type, tier, or search service status.

### 27.2. Capability Probe

An integration check can:

1. Verify connectivity.
2. Inspect version/topology.
3. Verify the search index exists and is ready.
4. Run a small valid query.
5. Classify any errors.
6. Mark the application search-ready once the probe succeeds.

This tests **actual capability**, rather than guessing from version numbers.

### 27.3. Do Not Run Probes Too Frequently

A vector probe query still consumes search resources. Health checks should use appropriate caching/intervals rather than firing search queries 10 times per second from every application instance.

### 27.4. Readiness vs. Liveness

- **Liveness:** the application process is still running.
- **Readiness:** the application has all dependencies needed to serve vector search.
- **Degraded mode:** the API stays up while vector retrieval is temporarily disabled.

If vector search is a secondary feature, a search outage should not automatically fail liveness checks for every API and trigger a restart storm.

---

## 28. Managing Driver, mongosh, and Atlas CLI Versions

### 28.1. The Three-Way Version Triad

~~~text
MongoDB Server/search service version
        +
MongoDB Driver/mongosh version
        +
Atlas CLI/management tooling version
~~~

Each layer has distinct capabilities.

### 28.2. Driver

Drivers can run raw BSON aggregations if they support the core aggregation API, though specialized helpers and index management APIs appear only in specific versions. Check the exact Java Sync Driver docs for your project's version.

### 28.3. Mongosh

`db.collection.createSearchIndex()` and `getSearchIndexes()` depend on helper availability; older mongosh versions may lack these methods even when the cluster supports Search. You can use the Atlas UI or management API when appropriate.

### 28.4. Atlas CLI

Some historical commands like `atlas deployments` have changed or been deprecated; current local docs point to the `atlas local` namespace. When reading older blog posts, check your Atlas CLI version and syntax rather than copying verbatim.

### 28.5. Pin Versions and Test

In CI/staging:

- Record exact server version/FCV as needed.
- Pin Java driver version and appropriate BOM.
- Pin container images for local integration tests.
- Pin the embedding model ID.
- Store index definitions in version control.
- Run compatibility tests before major/minor upgrades.

### 28.6. FCV and Cluster Upgrades

Feature Compatibility Version (FCV) can govern certain features after upgrading MongoDB binaries. Do not assume upgrading binaries immediately unlocks every feature gate. With Atlas Auto Upgrades, FCV management may differ from self-managed; check version management docs.

---

## 29. Quick Troubleshooting Matrix

| Symptom | Primary likelihood | Verification step |
|---|---|---|
| Atlas connection refused | IP allowlist/TLS/auth | Test `ping` and Atlas network/user settings |
| `$vectorSearch` stage unrecognized | Unsupported version/deployment | `db.version()` + Atlas/self-managed compatibility |
| Creating index via mongosh gives `Command not found` | Free tier restriction / old API / server | Atlas UI + version/index management docs |
| Query says index does not exist | Wrong name / not created / wrong collection | Search index listing / Atlas UI |
| Query returns zero results | Index not ready / dimensions / filter | Check index status, path, filter fields |
| Query missing tenant results | Filtering after `limit` | Move tenant into indexed pre-filter |
| Query fails with dimension error | Model/index/query vector mismatch | Check dimensions and model version |
| `exact:true` fails | ENN unsupported on that version | Check ENN minimum patch version |
| `$vectorSearch` inside `$facet` fails | Unsupported stage placement | Redesign pipeline |
| `$unionWith` fails on older version | Version feature gate | Check 8.0+ requirement and branch docs |
| Slow queries on Free/Flex | Resource contention / tier limit | Benchmark Dedicated/search capacity |
| Error 489 / load shedding | Search overload | Reduce concurrency / tune / scale |
| Newly inserted document not found | Indexing eventual consistency | Check index lag and readiness |
| Query returns another tenant's documents | Missing trusted pre-filter | Security fix + isolation test |
| Local Docker `mongo:7` won't run vector search | Lacks Search infrastructure | Use proper Atlas local setup or self-managed 8.2+ |
| Self-managed Windows fails | Platform support mismatch | Check Linux/container/Atlas CLI local option |
| Deployed new index but old schema still used | Rebuild not finished | Check active index definition/status |

---

## 30. Misconceptions to Avoid

**Misconception 1:** “Atlas Vector Search will forever exist only on Atlas cloud.”

→ Self-managed support exists in newer versions/environments. Always verify exact conditions.

**Misconception 2:** “Any MongoDB 6.0 runs `$vectorSearch`.”

→ The published ANN threshold for the 6.0 branch starts at 6.0.11, not all 6.0.x releases.

**Misconception 3:** “MongoDB 7.0.0 behaves identically to 7.0.10.”

→ ANN/ENN and related APIs have patch-version gates.

**Misconception 4:** “Installing a new Java driver enables the feature on an old server.”

→ Drivers and servers have separate responsibilities.

**Misconception 5:** “Self-managed MongoDB Community 7.0 is the same as Atlas 7.0.”

→ Atlas provides managed Search infrastructure; newer self-managed Community support has its own thresholds and setup.

**Misconception 6:** “Plain Docker MongoDB is equivalent to Atlas CLI local.”

→ You need a proper local deployment with the Search/Vector Search service.

**Misconception 7:** “The Free tier can never use Vector Search.”

→ You can experiment on supported tiers, subject to quotas, API restrictions, and resource limits.

**Misconception 8:** “If Free/Flex has Vector Search, it is production-ready.”

→ Resource contention, latency, scaling, and index quotas differ from Dedicated.

**Misconception 9:** “Creating a B-tree index on the array is enough.”

→ You must create a MongoDB Vector Search index.

**Misconception 10:** “Index creation returning success means all data is immediately queryable.”

→ Index building/syncing is asynchronous.

**Misconception 11:** “Changing index dimensions fixes a mismatched query vector.”

→ Model, stored embeddings, and query embeddings must all be compatible.

**Misconception 12:** “Matching dimensions alone makes two embedding models compatible.”

→ Not sufficient; their semantic spaces may differ.

**Misconception 13:** “ENN is available on every version that has ANN.”

→ ENN has its own minimum version threshold.

**Misconception 14:** “`numCandidates:100` guarantees 100% recall.”

→ ANN is approximate; benchmark against ENN or ground truth.

**Misconception 15:** “`$vectorSearch` can be placed after any `$match`.”

→ Stage placement has strict rules; use `filter` appropriately.

**Misconception 16:** “Vector Search pre-filter understands every MQL predicate.”

→ Only specific field types and operators are supported, and filter fields must be declared.

**Misconception 17:** “Running vectorSearch limit 5 and then matching tenant yields the tenant's top 5.”

→ Post-filtering can discard results and miss valid top-K; always pre-filter.

**Misconception 18:** “MongoDB write concern majority means the Search index has received the data.”

→ Search indexes are eventually consistent.

**Misconception 19:** “VectorSearchScore is the probability of truth.”

→ It is a ranking score that must be evaluated per model and index.

**Misconception 20:** “Running on Atlas local proves production performance.”

→ You must test on production-like infrastructure and tiers.

**Misconception 21:** “Preview features can be used in production without extra checks.”

→ Preview features carry specific limits and caveats.

**Misconception 22:** “Every region offers Search Nodes.”

→ Availability depends on cloud provider, region, and tier.

**Misconception 23:** “Search indexes are managed with `getIndexes()` like B-trees.”

→ Use dedicated Search index management APIs.

**Misconception 24:** “If index creation is disallowed, vector queries must also be disallowed.”

→ Index creation privileges/tier rules and query privileges are separate concerns.

**Misconception 25:** “Having vector search means data is automatically secure.”

→ You must enforce authenticated metadata filters and keep unauthorized data out of RAG context.

---

## 31. Environment Pre-Deployment Checklist

### 31.1. Deployment Checks

- [ ] Atlas cloud, Atlas local, or self-managed?
- [ ] Are server version and branch patch sufficient for ANN/ENN?
- [ ] Is the search service/process actually running?
- [ ] Does the cluster tier support the feature and have enough quota?
- [ ] If using Dedicated Search Nodes, are they available in this region/tier?
- [ ] If self-managed, do OS and `mongot` setup meet requirements?
- [ ] If local, are Atlas CLI/Docker/image versions compatible?
- [ ] Is there an upgrade/rollback policy?

### 31.2. Index Checks

- [ ] Do the collection and vector path exist?
- [ ] Are embeddings valid numeric values?
- [ ] Does `numDimensions` match the model?
- [ ] Was the similarity metric chosen intentionally?
- [ ] Are filter fields declared with type `filter`?
- [ ] Is the Search index ready?
- [ ] Within Free/Flex index quotas?
- [ ] Are index size and build status monitored?

### 31.3. Query Checks

- [ ] Is `$vectorSearch` placed in the required position?
- [ ] Are index name and path exact?
- [ ] Does the query vector match the model and dimensions?
- [ ] Does ANN have appropriate `numCandidates`, or ENN `exact:true` with version support?
- [ ] Is `limit` valid and within policy?
- [ ] Do tenant/visibility filters come from a trusted source?
- [ ] Does `$project` return only needed fields?
- [ ] Is the stage absent from `$facet`/`$lookup` subpipelines?
- [ ] Was the query tested without filters first, then with filters?

### 31.4. Production Checks

- [ ] Defined p95/p99 query SLOs and target recall?
- [ ] Benchmarked realistic data at expected index size?
- [ ] Sized memory/disk/search nodes?
- [ ] Implemented retry/backoff for overload?
- [ ] Measured indexing lag?
- [ ] Tracked model/embedding/index versions?
- [ ] Backed up data sufficiently to re-embed/rebuild?
- [ ] Designed fallback behavior when search is unavailable?
- [ ] Verified logs do not expose credentials or sensitive embeddings?
- [ ] Avoided relying on search results for real-time business invariants?

---

## 32. Practice Exercises

### Exercise 1 — Environment Assessment

Given five environments:

1. Atlas 6.0.10.
2. Atlas 6.0.11.
3. Atlas 7.0.2.
4. Community 7.0 running plain Docker `mongo:7`.
5. Community 8.2+ Linux with Search infrastructure configured.

Classify `$vectorSearch` ANN support; explain what additional conditions must be verified beyond version numbers.

### Exercise 2 — ANN and ENN

An Atlas v7.0.5 cluster can run ANN. Can you assume `exact:true` works? Look up the ENN threshold and propose an upgrade path or ANN/benchmark alternative.

### Exercise 3 — Atlas Free Index

Create a Vector Search index on Free via the UI. Then try programmatic creation (if desired) and record the behavior and quota. Why shouldn't you conclude “Command not found = Vector Search unsupported”?

### Exercise 4 — Atlas Flex

Design a POC with three vector indexes and two text Search indexes on Flex. Check current total quotas, cost, and scaling options.

### Exercise 5 — Atlas Local

Set up an Atlas CLI local environment per docs, verify Docker/image versions, create a collection and vector index, and run a query. Compare against a plain standalone MongoDB Docker image.

### Exercise 6 — Self-Managed 8.2

Design a checklist to run MongoDB Community 8.2+ with Search/Vector Search on Linux. Describe the role of `mongot`, memory, TLS, monitoring, and failover.

### Exercise 7 — Vector Index Definition

Create index `product_vector_index` with a 4-dimensional `embedding` and filter fields `tenantId`/`status`. Explain each field.

### Exercise 8 — ANN Query

Write a `$vectorSearch` query with a four-dimensional query vector, `numCandidates:100`, `limit:5`, and title/score projection.

### Exercise 9 — ENN Query

Switch the query to `exact:true` on a supported environment. Compare results and latency across several vector values.

### Exercise 10 — Dimension Mismatch

Configure a 4-dimensional index but query with 3 dimensions. Record the mongosh error and explain why you should not pad/truncate vectors arbitrarily.

### Exercise 11 — Unindexed Filter

Try filtering by `tenantId` when the index only defines the vector field. Add `type:"filter"`, wait for rebuild, and retry.

### Exercise 12 — Pre-Filter vs. Post-Filter

Compare:

- `$vectorSearch.filter:{tenantId:"tenant-a"}`.
- `$vectorSearch.limit:5` followed by `$match:{tenantId:"tenant-a"}`.

Explain when the latter misses valid tenant results.

### Exercise 13 — Index Build Readiness

Insert documents, create the index, and query immediately. Observe build status and when complete results start appearing; do not assume data is ready right after the command.

### Exercise 14 — Java Sync Driver

Write Java code using `Document` for `$vectorSearch`. Separate query vector, trusted tenant filter, and projection.

### Exercise 15 — Search Nodes

Estimate the raw vector size of 500,000 embeddings with 1,536 float32 dimensions. Explain why final RAM sizing cannot be inferred from that calculation alone.

### Exercise 16 — ANN Recall

Use a dataset small enough to run both ENN and ANN. Measure recall@10 and p95 latency across `numCandidates` values.

### Exercise 17 — Version Upgrade

An app on Atlas 7.0.2 wants to use ENN and `$unionWith` containing Vector Search. Plan the upgrade based on compatibility gates and integration tests.

### Exercise 18 — Hybrid Retrieval

Sketch a pipeline combining semantic and keyword retrieval; check stage support for your exact MongoDB version. Do not confuse legacy `knnBeta` with a dedicated vector index.

### Exercise 19 — Model Migration

Currently using 768-dim embeddings and migrating to a 1024-dim model. Design a dual-index rollout without breaking live queries.

### Exercise 20 — Troubleshooting

A query returns 0 results even though data exists. Write the diagnostic sequence: server/tier → index ready → path/dimensions → model → filter → ANN candidates → indexing lag.

### Exercise 21 — Tenant Isolation

Write an integration test ensuring a tenant-a user cannot receive tenant-b results even if a tenant-b vector is closer to the query.

### Exercise 22 — Production SLOs

Propose metrics: p50/p95/p99, errors, query rejections, index memory, build latency, indexing lag, ANN recall, cost/query, and alerts.

### Exercise 23 — Automated Embedding

Compare BYO embeddings vs. Automated Embedding: who manages the model, data residency, API availability, preview status, and version gates?

### Exercise 24 — Environment-Based QA

Design a test matrix covering Atlas Free, Flex, Dedicated, Atlas Local, and self-managed 8.2. Identify which tests must run on real deployments rather than unit tests/mocks.

---

## 33. Review Questions

1. How do Atlas Vector Search and MongoDB Vector Search differ in naming across newer documentation?
2. Why is storing a vector array insufficient for nearest-neighbor search?
3. Why does a standard MongoDB index not replace a vector index?
4. What role does `mongot` play?
5. How does Atlas cloud differ from self-managed in search process operational responsibilities?
6. What are the patch-version thresholds for `$vectorSearch` ANN on Atlas?
7. Why cannot Atlas 7.0.0 and 7.0.10 be treated as identical?
8. Does ENN share the same support threshold as ANN?
9. What is `exact:true` used for?
10. What does `numCandidates` mean?
11. Why can increasing numCandidates increase latency?
12. Is `$vectorSearch` supported inside `$facet`?
13. Can `$vectorSearch` be nested inside a `$lookup` subpipeline?
14. Starting in which version is `$vectorSearch` supported inside `$unionWith`?
15. Does self-managed Community 7.0 support Vector Search out of the box?
16. What OS/search infrastructure checks are required for self-managed Community Vector Search 8.2+?
17. Why is running Atlas Local via Docker on Windows different from native Community Search on Windows?
18. What does Atlas CLI local require?
19. Why is plain Docker `mongo:7` not enough?
20. What Search index count limits apply to Free/Flex?
21. What restrictions may the Free tier have when creating indexes via mongosh?
22. How do Dedicated Search Nodes differ from co-located search processes?
23. Why are Search Nodes not available in every cloud region?
24. What fields are needed in an index definition?
25. What must `numDimensions` match?
26. What is the maximum dimensionality documented for MongoDB Vector Search?
27. What does the similarity metric determine?
28. Must stored embeddings and query embeddings come from the same model?
29. Why can two models with the same dimensionality still produce wrong results?
30. What is the purpose of a `type:"filter"` field?
31. Why can post-filtering after limit miss top-K results for a tenant?
32. Where must `$vectorSearch` be placed in a pipeline?
33. How do you retrieve `vectorSearchScore`?
34. Is the score the probability of a correct answer?
35. Does the Search index update immediately after a MongoDB insert?
36. Does `w:"majority"` guarantee the document immediately appears in Vector Search?
37. Why must you wait for readiness before rolling out queries after an index rebuild?
38. Why is server version alone insufficient to assess search readiness?
39. Can a newer driver upgrade server capabilities on its own?
40. When should you choose ANN vs. ENN?
41. Does a “Command not found” error always mean Vector Search is unsupported?
42. How should a dimension mismatch be fixed?
43. Why should you lower concurrency or scale Search Nodes during query overload?
44. How does Automated Embedding differ from BYO embedding?
45. What extra checks are required for Preview features?
46. Why should cross-tenant documents never enter RAG context?
47. How should model/version/index be protected during migration?
48. Why is a Free POC insufficient to prove production p99?
49. When is a fallback needed if vector search is unavailable?
50. What criteria must be included in a compatibility test matrix?

---

## 34. Summary

**Whether Atlas/MongoDB Vector Search can be used cannot be determined solely by asking “Which MongoDB version?”.** You must inspect **deployment type, version branch, tier, search process, index state, data/embedding schema, driver/API, permissions, and resources**.

Key milestones to remember:

- Atlas ANN `$vectorSearch`: documented thresholds such as **6.0.11** on the 6.0 branch, **7.0.2** on the 7.0 branch, and subsequent supported releases.
- Atlas ENN: thresholds **6.0.16**, **7.0.10**, **7.3.2** per branch, distinct from ANN.
- `$vectorSearch` inside `$unionWith`: supported starting from **8.0** per the Manual.
- Self-managed Community/Enterprise Search/Vector Search: supported models starting from **8.2+**, with `mongot` and specific deployment requirements.
- Atlas CLI local: requires a compatible Atlas CLI/container deployment; local docs specify MongoDB **7.0.5+** for Vector Search.
- Free/Flex: intended for learning/POC within index/quota/resource limits, not production-ready by default.
- Dedicated Search Nodes: isolate search workloads, but require supported tiers/regions.
- Vector Search index must have the right `type:"vectorSearch"`, vector path, dimensions, and filter fields; the index must be ready.
- Search indexes update asynchronously; **MongoDB commit does not mean Vector Search already sees the new document**.
- RAG requires authorization filters, model/version consistency, recall/latency evaluation, and data protection.

Practical decision flow:

~~~text
Right environment?
    |
Right version and tier?
    |
Search service/index available?
    |
Embedding model and dimensions match?
    |
Query/API/permissions right?
    |
Benchmarked on real workload?
    |
Only then assess production readiness.
~~~

Once you understand each layer of requirements, you can distinguish **syntax errors**, **missing indexes**, **version incompatibilities**, **tier limits**, **missing Search service**, and **performance issues**—avoiding fixing the wrong root cause.

## Official MongoDB Documentation and References

- [MongoDB Vector Search — Overview](https://www.mongodb.com/docs/vector-search/)
- [MongoDB Vector Search — Deployment Options](https://www.mongodb.com/docs/vector-search/deployment/deployment-options/)
- [MongoDB Vector Search — Create Vector Search Indexes](https://www.mongodb.com/docs/vector-search/indexes/vector-search-type/)
- [MongoDB Vector Search — Run ANN and ENN Queries](https://www.mongodb.com/docs/vector-search/query/aggregation-stages/vector-search-stage/)
- [MongoDB Vector Search — Troubleshooting](https://www.mongodb.com/docs/vector-search/troubleshooting/)
- [MongoDB Manual — $vectorSearch Aggregation Stage](https://www.mongodb.com/docs/manual/reference/operator/aggregation/vectorsearch/)
- [MongoDB Atlas — Cluster Types](https://www.mongodb.com/docs/atlas/create-database-deployment/)
- [MongoDB Atlas CLI — Create a Local Atlas Deployment](https://www.mongodb.com/docs/atlas/cli/current/atlas-cli-deploy-local/)
- [MongoDB Community Edition — Search and Vector Search Support](https://www.mongodb.com/products/self-managed/community-edition)
- [MongoDB Search — Compatibility and Limitations](https://www.mongodb.com/docs/search/deployment/feature-compatibility/)
- [MongoDB Search — Manage Search Indexes](https://www.mongodb.com/docs/search/indexes/manage-indexes/)
- [MongoDB Search — Improve Search Index Performance](https://www.mongodb.com/docs/search/performance/index-performance/)
- [MongoDB Versions and Upgrade Paths](https://www.mongodb.com/docs/mongodb-versions/)
- [MongoDB Search and Vector Search Now Run Anywhere — 01/07/2026](https://www.mongodb.com/company/blog/product-release-announcements/mongodb-search-vector-search-now-run-anywhere)
- [MongoDB Java Sync Driver Documentation](https://www.mongodb.com/docs/drivers/java/sync/current/)
