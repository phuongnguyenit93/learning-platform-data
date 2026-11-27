# Atlas Search: Service Scope and Deployment Requirements

**Atlas Search** is the familiar name for the full-text search capability built into **MongoDB Atlas**. In current MongoDB documentation, this capability is commonly referred to as **MongoDB Search**. It uses **Apache Lucene** under the hood to build search indexes and solve problems that MongoDB B-tree indexes or the legacy `$text` operator were not designed to fully address: natural-language search, relevance ranking, autocomplete, fuzzy search, synonyms, highlighting, facets, multi-criteria filtering, and custom scoring.

However, "Atlas Search" is not simply an operator you tack onto `find()`. Using it properly requires understanding **where the service is supported**, **who operates the search process**, **which cluster tiers are suitable**, **how to create a Search index**, **when the index becomes ready**, **synchronization and resource limits**, as well as the security and operational requirements for running it in production.

This lesson in the **Text Search** chapter answers:

1. What capabilities does Atlas Search provide, and what MongoDB features does it not replace?
2. How does a Search index differ from a regular B-tree index and a `$text` text index?
3. How does the `mongod` — `mongot` architecture work?
4. Can it run on Free, Flex, Dedicated, Dedicated Search Nodes, local environments, and self-managed deployments?
5. What prerequisites must be verified before creating a Search index or running `$search` / `$searchMeta`?
6. Why can Search return stale results relative to a recently acknowledged write?
7. When should you scale out to Dedicated Search Nodes, and which metrics should you measure?
8. How do you design security, capacity planning, monitoring, and safe rollout procedures?

> **Key takeaway:** Atlas Search is a **search engine integrated into MongoDB's query path**, yet a Search index maintains its own lifecycle and asynchronous sync lag relative to source data. **Creating an index does not mean it is immediately ready, running `$search` does not guarantee transactionally fresh results, and availability on Free/Flex tiers does not equate to the capacity or SLA of Dedicated Search Nodes.**

## 1. Placing Atlas Search in the MongoDB Ecosystem

MongoDB serves two related but distinct sets of requirements:

- **Exact, transactional data access:** fetching documents by `_id`, order code, price range, conditional updates, transactions, uniqueness, and access control.
- **Content and relevance search:** users type a few words, look for "likely intended" matches, tolerate typos, expect typeahead suggestions, rank by relevance, and filter across multiple dimensions.

Example product collection:

```javascript
{
  _id: "SKU-001",
  tenantId: "SHOP-A",
  title: "Tai nghe không dây",
  description: "Tai nghe Bluetooth có chống ồn",
  category: "audio",
  price: 1350000,
  published: true
}
```

Different questions call for different tools:

| Question | Typically Suitable Tool |
|---|---|
| Find exact `_id = "SKU-001"` | B-tree index on `_id` |
| Filter `tenantId` and `price` range | Compound B-tree index |
| Guarantee `sku` uniqueness | Unique index |
| Search `"tai nghe"` across title/description and rank | MongoDB Search / Atlas Search |
| Suggest product names after typing `"tai ng"` | Search `autocomplete` with appropriate mapping |
| Tolerate minor typos | Search `text`/`autocomplete` with fuzzy options |
| Find semantically similar products via embeddings | MongoDB Vector Search—related, yet a **different** problem |
| Place an order and enforce inventory invariants | Atomic update / transaction—**never** enforced by a Search index |

Atlas Search strengthens search capabilities, **without replacing** B-tree indexes, unique constraints, transactions, schema validation, or application-layer security rules.

### 1.1. Why Naming Can Cause Confusion

In older docs and codebases, the term **Atlas Search** appears extensively. Newer documentation uses **MongoDB Search** to refer to the search engine and the `$search` and `$searchMeta` stages.

Distinguish three contexts:

- **Atlas Search on MongoDB Atlas:** Atlas provisions and operates the Search tier as a managed service.
- **MongoDB Search on self-managed deployments:** supported on compatible MongoDB Server / `mongot` combinations, where **your operations team installs, configures, monitors, and upgrades** the Search process.
- **Local Atlas deployment:** a test environment bundling `mongod` and `mongot`; great for learning, not inherently HA for production.

Because product naming and support matrices evolve across releases, avoid outdated assumptions such as "no self-managed MongoDB can run Search" as well as the opposite mistake that "installing any Community Edition makes `$search` work."

## 2. Search Engine: A Separate Indexing Layer

High-level architecture of a Search query:

```text
Client / Java / mongosh
          |
          | MongoDB aggregation pipeline
          v
       mongod / mongos
          |
          | $search or $searchMeta
          v
       mongot (Apache Lucene)
          |
          | Search index
          v
   Document IDs + score + metadata
          |
          v
  MongoDB reads source documents
  or uses stored source when appropriate
          |
          v
       Results to client
```

`mongot` is a Search process separate from `mongod`. It:

1. Builds and maintains Lucene indexes from MongoDB collections.
2. Tracks source data changes via a change-stream-based synchronization mechanism.
3. Executes search queries and computes search relevance scores.
4. Coordinates with `mongod`/`mongos` to return results within the aggregation pipeline.

**Applications connect to MongoDB**—they do not open direct connections to `mongot` to issue `$search`.

### 2.1. A Search Index Is Not a B-Tree Index

The index-creation commands differ:

```javascript
// B-tree index for standard filtering and sorting.
db.products.createIndex({
  tenantId: 1,
  price: 1
});

// Search index for $search queries.
db.products.createSearchIndex(
  "product_text",
  { mappings: { dynamic: true } }
);
```

These two index types have **different structures and lifecycles**. `db.collection.getIndexes()` lists traditional database indexes; inspecting Search indexes uses dedicated management mechanisms such as `$listSearchIndexes` on supported versions.

### 2.2. Inverted Index and Term Analysis

Conceptually, Lucene maintains a mapping like:

```text
"tai"       -> DOC-01, DOC-02, DOC-09
"nghe"      -> DOC-01, DOC-03, DOC-09
"bluetooth" -> DOC-01, DOC-07
"chống"     -> DOC-01, DOC-08
"ồn"        -> DOC-01, DOC-08
```

When a user enters `"tai nghe bluetooth"`, the search engine does not scan every document character-by-character. It uses the inverted index and scoring model to retrieve and rank candidates.

This is a conceptual model; actual Lucene internals include token positions, term frequencies, segment structures, analyzers, and further optimizations.

### 2.3. Relevance Scores Are Not Absolute Business Sort Keys

Search ranks results by relevance score. Rankings can change whenever:

- Documents are inserted or deleted;
- Analyzers or mappings change;
- Queries or boosts are adjusted;
- Indexes are rebuilt;
- Corpus statistics shift as data evolves;
- Filters or explicit sorts are added by the app.

Never treat a score as a **unique identifier** or transactional version. If the product needs deterministic pagination, design explicit tie-breakers or use supported Search pagination methods for your version.

## 3. Feature Scope of Atlas Search

Typical capability groups:

| Group | Goal | Example |
|---|---|---|
| Full-text | Search text content | `"tai nghe chống ồn"` |
| Relevance ranking | Order results by relevance | Title matches outrank description matches |
| Autocomplete | Suggest while typing | `"tai ng…"` |
| Fuzzy search | Tolerate bounded typos | `"blutooth"` matches `"bluetooth"` |
| Phrase / proximity | Match ordered/proximate terms | `"sạc nhanh"` |
| Synonyms | Map equivalent terms | `"điện thoại"` / `"smartphone"` via dictionary |
| Compound query | Combine `must`/`should`/`filter`/`mustNot` | Text query + tenant + published |
| Highlighting | Return matched snippets/fields | Bold matching terms |
| Facets | Bucket results by filter dimensions | Category, price bands |
| Search metadata | Counts and query statistics | `$searchMeta` |
| Search-as-you-type | Responsive typeahead UX | Suggestion list |
| Structured search filters | Combine `equals`/`range`/`geo` where mapped | Products under 2,000,000 VND |

Each feature has **specific mappings, operators, and version/tier restrictions**. Do not assume creating an index with `dynamic: true` automatically optimizes every feature.

### 3.1. What Atlas Search Does Not Do Automatically

Atlas Search is not:

- A **uniqueness** engine preventing duplicate SKUs;
- A transaction coordinator;
- A data replica sufficient to replace backups;
- A machine translation service;
- A content legality or factuality validator;
- A user authorization system replacing MongoDB/application ACLs;
- A linearizable, zero-lag synchronization tool;
- A road-routing or ETA calculation engine;
- A drop-in B-tree replacement for every `find()` query.

Strong search features never substitute for proper data modeling and access control.

## 4. Atlas Search vs. Legacy `$text`

MongoDB includes **text indexes** and `$text` in its legacy database indexing layer:

```javascript
db.products.createIndex({
  title: "text",
  description: "text"
});

db.products.find({
  $text: {
    $search: "tai nghe"
  }
});
```

Atlas Search uses a **Search index** and the `$search` aggregation stage:

```javascript
db.products.aggregate([
  {
    $search: {
      index: "product_text",
      text: {
        query: "tai nghe",
        path: ["title", "description"]
      }
    }
  }
]);
```

The two approaches do not share indexes.

| Criterion | MongoDB `$text` | Atlas Search / MongoDB Search |
|---|---|---|
| Index | Database B-tree/text index | Lucene-based Search index |
| Query entry point | `$text` in `find` or equivalent predicate | `$search`/`$searchMeta` in aggregation |
| Basic full-text | Yes | Yes |
| Advanced autocomplete | Not a strength | Dedicated operator and mapping |
| Fuzzy matching | Much more limited | Configurable fuzzy options |
| Custom ranking | More limited | Rich scoring and boosting options |
| Facets / highlighting | Out of scope | Native Search features |
| Index lifecycle | Tied to database indexes | Separate Search index, synced asynchronously |
| Deployment requirement | Any MongoDB supporting text index | Requires Search service / `mongot` available |
| Results right after write | Governed by database read/index mechanics | Subject to **indexing lag** |
| Operational cost | Primarily database resources | Database + Search compute/index storage |

Never migrate from `$text` to `$search` by **merely swapping operators**. You must build the Search index, configure mappings, test relevance, and adapt application flows.

## 5. Deployment Scope on MongoDB Atlas

MongoDB Atlas offers several deployment tiers. Separate two questions:

1. **Can this tier run MongoDB Search?**
2. **Does this tier have enough resources, features, and SLA for my workload?**

Those two questions can yield very different answers.

### 5.1. Environment Matrix

| Environment | Is Search Available? | Architecture / Target Use |
|---|---|---|
| Atlas Free cluster (formerly M0) | Yes, with tier limits | Learning and lightweight experiments |
| Atlas Flex cluster | Yes, with tier limits | Development, small apps, query prototyping |
| Atlas Dedicated M10/M20 and above | Yes, per version/tier capabilities | Prototypes and production depending on sizing |
| Atlas Dedicated with Dedicated Search Nodes | Yes on eligible tiers/regions | Workload isolation and production Search |
| Atlas local deployment | Yes in supported local Search setups | Development/CI; not inherently HA |
| Atlas Infinite | Support depends on current program/release status | Verify limits/preview status before committing to an SLA |
| Self-managed Community / Enterprise | Yes on **supported server + `mongot` combinations** | Self-deployed and self-operated, not Atlas-managed |

This table reflects MongoDB models published as of **2026**; tiers, regions, limits, product names, and versions evolve. Always check the official Compatibility & Limitations page for your exact release and region before deploying.

### 5.2. Free and Flex Do Not Mean Unlimited Support

Per MongoDB Search documentation at the time of writing, tier-specific limits may include:

- **Free:** up to **3 combined Search/Vector indexes** per cluster.
- **Flex:** up to **10 Search/Vector indexes** per cluster.
- **Maximum 3 KB JSON index definition** on both tiers.
- **One synonym mapping** per index definition under tier limits.
- Additional limits on indexed field counts, synonym collections, Lucene clause counts, and features.

These figures are **version/tier limits**, not sizing recommendations. Verify current docs and the Atlas UI before relying on any limit for a specific product.

For example, if a Free cluster already has three Search/Vector indexes, creating a fourth will be rejected. Renaming an index does not bypass the quota.

### 5.3. Is Free Suitable for Learning?

Yes—you can use it to:

- Practice creating Search indexes;
- Run `$search` and `$searchMeta`;
- Experiment with mappings and analyzers;
- Build proofs of concept;
- Observe index build/update flows;
- Evaluate basic search UX.

Never use benchmarks on a few thousand documents in a Free cluster as proof that your system will hold strong p99 latency across tens of millions of products or heavy production traffic.

### 5.4. When Does Flex Fit?

Flex works for testing or small applications, provided you verify:

- Search index count and definition size;
- Indexing throughput and storage capacity;
- Shared resource limits;
- Availability of advanced features;
- Actual SLOs and concurrency;
- A migration path to Dedicated when needed.

Do not conclude from Flex's ability to run `autocomplete` that it provides the same scalability or node isolation as a Dedicated cluster.

## 6. Dedicated Clusters and Dedicated Search Nodes

An Atlas Dedicated cluster can run `mongod` and `mongot` **on the same node** (co-located), or deploy **Dedicated Search Nodes** where eligible.

### 6.1. Co-Located Search

```text
Atlas database node
  ├── mongod: reads/writes, replication, database indexes
  └── mongot: Lucene index, search queries, indexing

CPU / RAM / disk / I/O resources may contend
```

This is a straightforward starting point and can be cost-effective for moderate workloads.

Pros:

- Simpler configuration;
- No separate Search Node bill from day one;
- Well suited for prototypes and modest traffic;
- Atlas manages the Search process.

Trade-offs:

- Search indexing and queries compete with database operations for resources;
- An autocomplete traffic burst can degrade read/write latency;
- As data and indexes grow, memory and disk pressure rise;
- Scaling Search independently of the database is constrained.

### 6.2. Dedicated Search Nodes

```text
Application
      |
   mongod/mongos                       Search Nodes
   (database)                       (mongot / Lucene)
      |                                     |
      |       search request                |
      +------------------------------------>
      |                                     |
      <------------------------------------+
      |
   Return results
```

Dedicated Search Nodes let you:

- Isolate search compute from database compute;
- Scale CPU, RAM, and storage for Lucene independently for Search workloads;
- Reduce resource contention;
- Gain additional HA and workload-isolation options depending on configuration;
- Track Search infrastructure costs more transparently.

However, isolating nodes does not make `$search` **strongly consistent**. Search still maintains its own asynchronous index.

### 6.3. Baseline Requirements for Dedicated Search Nodes

Per Atlas documentation, Dedicated Search Nodes apply to **Dedicated clusters M10 and higher**, subject to server version, cloud provider, region, and search tier requirements. Free and Flex tiers **cannot add Dedicated Search Nodes**.

Atlas Deployment Options often cite **M10+ database clusters** paired with **S20+ Search tiers** in supported cloud regions as a starting production example. That is an initial sizing guideline—**not a guarantee that every M10 in every region supports every configuration**.

Verify:

1. Atlas cluster tier eligibility;
2. MongoDB Server version supports Search Nodes;
3. Cloud provider and region offer the desired Search tier;
4. No incompatible cluster topology constraints (such as certain global clusters);
5. Minimum Search Node count and HA topology;
6. Search index size, query throughput, CPU, and RAM;
7. Node and cross-node network transfer costs.

### 6.4. Search Nodes Carry Separate Costs

Adding Dedicated Search Nodes introduces cost components such as:

- **Number of Search Nodes** provisioned;
- **Search tier** (CPU/RAM/storage);
- **Data transfer** between Search and database nodes;
- Usage duration;
- Compute/storage overhead during index rebuilds.

Do not call Atlas Search "free" simply because co-located deployments do not show a separate Search Node line item. Co-located Search consumes cluster resources; Dedicated Search Nodes are billed per Atlas configuration.

### 6.5. Signals to Separate Nodes

Watch for:

- Rising Search QPS degrading database write latency;
- High `mongot` CPU/RAM spikes during index builds/rebuilds;
- Growing Search indexes causing memory pressure;
- Scaling database nodes solely to survive Search load when DB capacity is otherwise idle;
- Wide p95/p99 Search latency swings during batch writes;
- Need for independent Search HA and scaling;
- Many collections, analyzers, and large Search indexes.

Moving to Search Nodes does not excuse unoptimized mappings or unbounded queries. An overly broad index or unconstrained query can still saturate larger nodes.

## 7. Local Development and Self-Managed: Understanding the Scope

### 7.1. Atlas Local Deployment

MongoDB supports local Search development via **Atlas CLI local deployments** or the `mongodb/mongodb-atlas-local` container image.

Architecture:

```text
Developer laptop / CI
   └── local MongoDB deployment
         ├── mongod
         └── mongot

Application connects to MongoDB normally.
```

Well suited for:

- Learning the `$search` API;
- Developing analyzers and mappings;
- Running integration tests;
- Prototyping queries before provisioning cloud resources;
- POC demos.

However, a **local single-node deployment is not a production HA solution**. It lacks replication/high availability, backup policies, and operational hardening.

Example image command from MongoDB documentation:

```bash
docker pull mongodb/mongodb-atlas-local:preview
docker run -p 27017:27017 mongodb/mongodb-atlas-local
```

This is a reference command for Docker hosts; image tags and requirements may change. On Windows or macOS, the image runs inside a Linux container—it does not imply native Windows/macOS `mongot` binaries.

### 7.2. Self-Managed MongoDB Search

Modern MongoDB Search documentation provides self-managed deployment paths. Architecture:

```text
Self-managed replica set / sharded cluster
      mongod / mongos
            |
      gRPC / search integration
            |
         mongot
            |
      Lucene index files
```

Unlike Atlas:

- Your operations team **installs and manages `mongot`**;
- You provision hosts, containers, or Kubernetes clusters;
- You manage storage and networking;
- You configure topology and connection security;
- You track version compatibility matrices;
- You manage upgrades, restarts, restores, and scaling.

`mongot` is not a drop-in plugin for any arbitrary `mongod` version. You must match **MongoDB Server, `mongot` version, OS, and deployment management** per the official compatibility matrix.

### 7.3. Compatibility Matrices Evolve by Release

In current self-managed documentation (2026), Kubernetes-managed deployments list example baseline milestones such as:

```text
MongoDB Server:        8.3.4 or compatible newer version
mongot:                1.70.1 or compatible newer version
Kubernetes Operator:   1.9.1 or compatible newer version
```

These are **minimum baselines for a specific deployment track and documentation snapshot**, not universal rules across every packaging format or future release. Compatibility matrices also retire older server branches. Always consult the matrix **on the actual deployment date**.

For Community self-managed deployments, MongoDB documents installing `mongot` via Linux tarballs/containers and compatible operator options. Enterprise deployments carry their own management rules, particularly around the Kubernetes Operator.

**Never conclude that "every MongoDB 8.x includes Search out of the box."** Search works only when both the server and the Search process are properly deployed, integrated, and supported.

### 7.4. Do Not Confuse Atlas-Managed with Self-Managed

| Responsibility | Atlas Search Managed | Self-Managed Search |
|---|---|---|
| Provision Search process | Managed by Atlas | Operations team |
| Define Search indexes | App / DB admin | App / DB admin |
| Compute sizing | Atlas tier / Search tier | Self-selected hosts/containers |
| Index synchronization | Handled by Search service; monitored by team | Handled by Search process; fully owned by team |
| Version compatibility | Largely managed by Atlas; still verify | Must manually verify matrix |
| Network / TLS | Atlas project/network controls | End-to-end self-designed |
| Logs / metrics | Atlas monitoring/API | Self-integrated observability |
| Backup / recovery | Per Atlas plan and Search strategy | Fully self-designed |
| Cost | Cluster / Search Nodes / network per tier | Infrastructure + operational staffing |

## 8. Prerequisites Before Running Search on Atlas

Before creating an index, verify at least six groups of prerequisites.

### 8.1. Valid Atlas Cluster

- Project and deployment created;
- Cluster running and not suspended;
- Tier supports the desired features;
- Server version is compatible;
- Target collection and data exist;
- Region supports required Search options.

A Search index is bound to a **supported collection or view**, not a standalone database-independent object.

### 8.2. Permissions to Manage Search Indexes

Different operations require different privileges:

- Inspecting Search index definitions and status;
- Creating a Search index;
- Updating a definition;
- Dropping an index;
- Running read queries against the collection.

In the Atlas UI, Project roles govern management access. In `mongosh` or drivers, database privileges matter equally.

Per Search Index Management documentation, built-in database roles such as `read` allow listing indexes while `readWrite` includes index-management privilege actions; for least privilege, grant custom roles tailored to your organization's workflow.

Never grant Project Owner or full database admin privileges just so a search API service can query products.

### 8.3. Connectivity to MongoDB

Required:

- Cluster connection string;
- Valid database user and credentials;
- Atlas IP access list or private endpoint/VPC networking as needed;
- TLS per connection policy;
- DNS/SRV resolution;
- Compatible driver able to reach the deployment;
- Application secret management.

Applications **do not** expose `mongot` ports to the Internet. On Atlas, send aggregation queries to MongoDB just like any standard query.

### 8.4. Search Index Definition Matching the Schema

Determine:

- Which fields are full-text searchable;
- Which fields need exact filtering;
- Which fields need sorting or faceting;
- Which analyzer each string field uses;
- Whether data is multilingual;
- Whether autocomplete, fuzzy matching, or synonyms are needed;
- Whether dynamic mapping should be enabled or disabled;
- Whether PII must be excluded from indexing.

A misconfigured index mapping can cause queries to miss or mis-match documents even when the cluster is completely healthy.

### 8.5. Index Must Finish Building and Become Queryable

Creating a Search index is an **asynchronous operation**. The API may return success as soon as the creation request is accepted, while indexing continues in the background.

Proper workflow:

```text
Create Search Index
       |
       v
Index definition accepted
       |
       v
Initial index build / sync
       |
       v
Index becomes queryable / ready
       |
       v
Run Search tests and enable traffic
```

Never treat an `ok: 1` response from an index management command as proof that the index is READY.

### 8.6. Capacity and Security Plan

Even for a POC, bound:

- Indexed data size;
- Search index count;
- Expected QPS;
- Results returned per query;
- Analyzer/index definition size;
- Network access;
- Collections holding sensitive data.

For production, add SLAs, monitoring, backup/recovery plans, index lifecycle management, and budgets.

## 9. Creating a Search Index: Different from `createIndex()`

This example uses a test collection `searchProductsLab` on a properly configured MongoDB Search deployment. **Never run `drop()` on a production collection.**

### 9.1. Preparing Data

```javascript
use searchLab;

db.searchProductsLab.insertMany([
  {
    _id: "SKU-101",
    tenantId: "SHOP-A",
    title: "Tai nghe Bluetooth chống ồn",
    description: "Tai nghe không dây chụp tai, pin dùng lâu",
    category: "audio",
    price: 1350000,
    published: true
  },
  {
    _id: "SKU-102",
    tenantId: "SHOP-A",
    title: "Tai nghe có dây",
    description: "Tai nghe nhẹ dành cho học tập và họp trực tuyến",
    category: "audio",
    price: 250000,
    published: true
  },
  {
    _id: "SKU-103",
    tenantId: "SHOP-A",
    title: "Bàn phím cơ",
    description: "Bàn phím có kết nối Bluetooth",
    category: "keyboard",
    price: 950000,
    published: true
  },
  {
    _id: "SKU-104",
    tenantId: "SHOP-B",
    title: "Tai nghe du lịch",
    description: "Thiết kế gọn, dễ mang theo",
    category: "audio",
    price: 720000,
    published: true
  },
  {
    _id: "SKU-105",
    tenantId: "SHOP-A",
    title: "Tai nghe thử nghiệm",
    description: "Chưa công bố sản phẩm",
    category: "audio",
    price: 500000,
    published: false
  }
]);
```

Re-running with the same `_id` values will trigger duplicate key errors. Use a fresh test database or clean up only authorized test documents.

### 9.2. Explicit Mapping

Desired behavior:

- `title`, `description`: searchable text;
- `tenantId`, `category`: exact filters;
- `published`: boolean filter;
- `price`: numeric range.

Example:

```javascript
db.searchProductsLab.createSearchIndex(
  "catalog_text",
  {
    mappings: {
      dynamic: false,
      fields: {
        title: {
          type: "string",
          analyzer: "lucene.standard"
        },
        description: {
          type: "string",
          analyzer: "lucene.standard"
        },
        tenantId: {
          type: "token"
        },
        category: {
          type: "token"
        },
        published: {
          type: "boolean"
        },
        price: {
          type: "number"
        }
      }
    }
  }
);
```

**Version note:** `db.collection.createSearchIndex()` is available when MongoDB Server, drivers/`mongosh`, and the deployment support programmatic index management commands. Older Atlas tools/versions may require using the Atlas UI or Administration API instead.

### 9.3. Why `dynamic: false`?

`dynamic: true` automatically indexes all supported fields, which is handy for quick experiments.

In production, you usually want to:

- Index only fields needed for Search use cases;
- Reduce index size and indexing cost;
- Prevent unnecessary PII from entering the Search index;
- Control exactly which text analyzers apply;
- Keep index definitions predictable as schemas evolve.

`dynamic: false` enforces explicit field control. The trade-off is updating the mapping whenever a new searchable field is introduced.

### 9.4. `string` and `token` Are Not the Same

In Search mappings:

- `string`: designed for full-text analysis, tokenization, and relevance scoring.
- `token`: designed for **exact matching, filtering, faceting, and sorting** per Search operator and version rules.

If `tenantId` is mapped as tokenized `string` instead of `token`, exact-match filters may not behave as expected. Before using `equals`, verify the field is mapped to the data type required by that operator.

### 9.5. Checking Index Status

One way to check in `mongosh`:

```javascript
db.searchProductsLab.aggregate([
  {
    $listSearchIndexes: {
      name: "catalog_text"
    }
  }
]);
```

Inspect the status/queryable fields in the actual output. Exact fields vary across versions and tools, but the rule is always **wait until the index is ready** before enabling Search traffic in the UI.

Note that `$listSearchIndexes` is an **index-management aggregation stage**, not a `$search` query.

## 10. `$search`: Basic Full-Text Query

Once the Search index is ready:

```javascript
db.searchProductsLab.aggregate([
  {
    $search: {
      index: "catalog_text",
      text: {
        query: "tai nghe",
        path: ["title", "description"]
      }
    }
  },
  {
    $project: {
      _id: 1,
      title: 1,
      description: 1,
      category: 1,
      score: {
        $meta: "searchScore"
      }
    }
  },
  { $limit: 10 }
]);
```

`$search` uses the `"catalog_text"` index to find matching documents. `searchScore` is the relevance score computed by the Search engine according to mapping and query rules.

### 10.1. `$search` Must Sit at the Proper Pipeline Position

In a standard pipeline, `$search` must be the **first stage**. Do not place `$match` ahead of it expecting Search to behave like an arbitrary downstream filter stage.

Conceptually wrong:

```javascript
db.searchProductsLab.aggregate([
  { $match: { published: true } },
  {
    $search: {
      index: "catalog_text",
      text: {
        query: "tai nghe",
        path: "title"
      }
    }
  }
]);
```

Instead, push Search-supported predicates into **`compound.filter`**, or run `$search` first and follow with `$match` if source-document verification is required.

Certain cases allow `$search` at the start of **nested subpipelines inside `$lookup`/`$unionWith` or on views**, depending on server version; the "first stage" rule applies to the Search pipeline itself rather than blindly across an entire outer script.

## 11. Combining Text, Tenant, and Published Status

In multi-store systems, a search API typically needs to:

- Search keywords;
- Restrict to the authorized `tenantId`;
- Show only `published` products.

Use `compound`:

```javascript
db.searchProductsLab.aggregate([
  {
    $search: {
      index: "catalog_text",
      compound: {
        must: [
          {
            text: {
              query: "tai nghe",
              path: ["title", "description"]
            }
          }
        ],
        filter: [
          {
            equals: {
              path: "tenantId",
              value: "SHOP-A"
            }
          },
          {
            equals: {
              path: "published",
              value: true
            }
          }
        ]
      }
    }
  },
  {
    $project: {
      title: 1,
      category: 1,
      price: 1,
      score: {
        $meta: "searchScore"
      }
    }
  },
  { $limit: 10 }
]);
```

Key details:

- `must` participates in matching and scoring per Search semantics.
- `filter` enforces mandatory predicates **without contributing to score**.
- `tenantId` must use a mapping compatible with `equals`.
- Indexing `published` lets Search filter it directly at the Search layer.

### 11.1. Filters Inside a Search Index Are Not the Only Security Layer

Search indexes have **synchronization lag**. If a product was just unpublished or tenant access was just revoked, the index may not reflect the update immediately.

Therefore, for sensitive data, never rely solely on Search index filtering for access control.

Safer architecture:

1. Authenticate the user and verify tenant permissions in the API.
2. Apply tenant/visibility filters in Search to narrow candidate results.
3. Re-verify authorization against source data or a trusted permission layer when required.
4. Never return PII or secrets simply because they reside in stored source or search results.
5. Handle stale Search index states gracefully without leaking data.

**Search is a retrieval tool; authorization remains an application and database security contract.**

### 11.2. Why Not Always Use `$match` After Search?

A `$match` stage after `$search` checks live MongoDB documents, yet it:

- Does not make the Search index sync faster;
- Can return fewer results than the requested limit if many candidates are filtered out afterward;
- Does not replace index-level filtering for performance;
- Requires careful pagination and ranking design.

Before indexing sensitive data into Search, map out the data flow and authorization policy clearly.

## 12. `$searchMeta`: Counts and Aggregate Metadata

MongoDB Search supports the `$searchMeta` stage to return metadata about a query.

Example:

```javascript
db.searchProductsLab.aggregate([
  {
    $searchMeta: {
      index: "catalog_text",
      text: {
        query: "tai nghe",
        path: ["title", "description"]
      },
      count: {
        type: "total"
      }
    }
  }
]);
```

This requests the total matching result count via Search. Depending on scale and cost, approximate or lower-bound counts may be used where documented.

### 12.1. `$searchMeta` Does Not Replace `$group` for All Analytics

`$searchMeta` serves Search request metadata such as counts and facets in supported configurations. It is not a general-purpose BI engine replacing standard aggregation pipelines.

For accounting reports like "total revenue of all paid orders," compute directly from source data at the required consistency level—never treat counts from a potentially lagging Search index as a financial ledger.

### 12.2. Facets Require Proper Field Mappings

To facet by category, number, or date, Search indexes enforce specific field types and operator rules. A field indexed only for full-text is not automatically valid for faceting.

In modern MongoDB Server/Search releases, `token` participates in facets under supported rules, whereas older docs used `stringFacet`/`numberFacet`. Never copy an outdated facet snippet without verifying against your current Search index mapping version.

## 13. Analyzers: The Deciding Factor in Search Quality

An **analyzer** defines how strings are processed at index time and/or query time:

```text
Input:
  "Tai nghe Bluetooth chống ồn"

Analyzer:
  normalize / tokenize / optional filters

Tokens:
  "tai", "nghe", "bluetooth", "chống", "ồn"
```

This is an illustration; exact tokens depend on the chosen analyzer.

### 13.1. Why Can Index Creation Succeed Yet Search Quality Be Poor?

Examples:

- Users search `"tai nghe"` while data says `"Tai-nghe"`.
- Users omit accents: `"chong on"` while data says `"chống ồn"`.
- Product code `"USB-C"` gets split into `"usb"` and `"c"`.
- Users omit letters or make typos.
- Multiple languages mix inside one field.
- Synonyms like `"laptop"` and `"máy tính xách tay"` are not defined.

Successful index creation only proves the mapping syntax is valid; **relevance quality** must still be validated against a representative query set.

### 13.2. Vietnamese Requires Dedicated Testing

Do not assume an English analyzer handles:

- Vietnamese diacritics;
- Multi-syllable word splitting;
- Casing;
- Compound words;
- Brand names;
- Abbreviations;
- Product codes;
- Users omitting accents;
- Industry-specific synonyms.

You may need MongoDB-supported analyzers/token filters, custom analyzers, or multi-field designs tailored to different query shapes. **Never promise that `lucene.standard` alone gives Search full Vietnamese linguistic understanding.**

### 13.3. Analyzers Are Part of the Schema Contract

If the index uses analyzer A while the query path analyzes terms incompatibly, results will diverge from expectations.

When changing an analyzer:

1. Prepare a test query set;
2. Compare precision, recall, and ranking;
3. Create/update the index using supported methods;
4. Wait for build/sync completion;
5. Prepare a rollout and rollback plan;
6. Monitor Search p95/p99 latency and zero-result rates.

Never swap an analyzer directly in production assuming the Search index updates instantaneously without impact.

## 14. Autocomplete Is Not `$regex` Across Every Field

As a user types:

```text
t
ta
tai
tai n
tai ng
```

running unanchored regexes across millions of documents is expensive and ranks poorly.

Atlas Search provides the **`autocomplete`** operator backed by an **`autocomplete` index mapping**. This feature is purpose-built for search-as-you-type and differs from full-text `text`.

An autocomplete index can define a field like:

```javascript
db.searchProductsLab.createSearchIndex(
  "catalog_autocomplete",
  {
    mappings: {
      dynamic: false,
      fields: {
        title: {
          type: "autocomplete",
          tokenization: "edgeGram",
          minGrams: 2,
          maxGrams: 15,
          foldDiacritics: true
        }
      }
    }
  }
);
```

Query example:

```javascript
db.searchProductsLab.aggregate([
  {
    $search: {
      index: "catalog_autocomplete",
      autocomplete: {
        query: "tai ng",
        path: "title"
      }
    }
  },
  {
    $project: {
      title: 1,
      score: {
        $meta: "searchScore"
      }
    }
  },
  { $limit: 10 }
]);
```

Verify `autocomplete` index support, configuration, and gram limits on your exact version.

### 14.1. Autocomplete Trade-Offs

- Larger indexes due to generated prefix/n-gram tokens.
- Short queries produce noisy results.
- Client-side debouncing is often needed.
- Minimum query length is needed.
- Fuzziness boosts recall at the cost of looser matches and higher CPU.
- Having an autocomplete index ready does not mean newly updated products appear instantaneously.

A great search-as-you-type experience requires **UI/UX, analyzers, index mappings, and capacity planning**—not just a single operator.

## 15. Search Indexes Synchronize Asynchronously

This is a critical correctness consideration.

Source data lives in MongoDB. Search indexes are maintained by the Search process via change synchronization, introducing a **lag window** between an acknowledged write and Search index visibility.

Timeline:

```text
T0: Product SKU-101 has published=true.
T1: Application updates published=false.
T2: MongoDB acknowledges the write per write concern.
T3: Search index has not finished processing the change.
T4: A $search query may still observe stale data.
T5: Search index catches up; queries reflect the new state.
```

At T4, returning stale state does not mean MongoDB lost the write. It reflects the difference between the **database source of truth** and the **search projection**.

### 15.1. `$search` Does Not Guarantee Read-Your-Writes

If a user adds a product and immediately searches for its name, Search may not see it yet.

The application must choose how to handle this:

- Show an "Indexing in progress" status;
- Fetch the document directly by `_id` to confirm;
- Poll within a bounded window;
- Use an optimistic UI update workflow;
- Accept eventual consistency for catalog search.

Never use `$search` as a post-write verification step when linearizable read-your-writes semantics are required.

### 15.2. Never Ignore Search Lag in Security Checks

Example:

```text
T1: Admin revokes access to a document.
T2: Database persists the new permission.
T3: Search index has not updated yet.
T4: User queries Search.
```

The Search index may still hold stale terms or metadata. The decision of **whether a user is authorized to receive a document** must come from authoritative authorization checks, never solely from a recently updated field in the Search index.

### 15.3. Search Indexes Do Not Replace Write Concerns

`writeConcern: "majority"` strengthens durability across MongoDB data-bearing replicas; it **does not force the Search index to sync before acknowledging the write**.

Therefore:

> **Majority-acknowledged writes and Search-index visibility are two separate milestones.**

Whenever an application needs immediate visibility of a security permission or order state, read the source document with an appropriate read concern.

## 16. Index Lifecycle: Build, Update, Rollback, and Delete

A Search index has a full operational lifecycle beyond a single config block.

### 16.1. Initial Creation

```text
Definition submitted
        |
        v
Index build / initial sync
        |
        v
Queryable / ready
        |
        v
Serving production search
```

Depending on dataset size, builds take time and consume CPU, RAM, disk, and network. Monitor index status and resources rather than relying on the initial command response.

### 16.2. Modifying a Definition

Example—adding a field:

```text
catalog_text v1: title, description
catalog_text v2: title, description, brand
```

A definition change can trigger an index rebuild or a rolling update taking time. Decide:

- How can the active index be updated safely?
- Should a parallel index be built for side-by-side comparison?
- Will concurrent indexes exceed tier quotas?
- Is there enough storage for the transition period?
- Can the backend toggle index names via a feature flag?

On Free/Flex tiers, index-count limits can block parallel v1/v2 blue/green rollouts.

### 16.3. Listing Search Indexes

```javascript
db.searchProductsLab.aggregate([
  { $listSearchIndexes: {} }
]);
```

`$listSearchIndexes` is distinct from `getIndexes()` for regular database indexes.

### 16.4. Dropping a Search Index

```javascript
db.searchProductsLab.dropSearchIndex(
  "catalog_autocomplete"
);
```

Dropping an index immediately breaks queries referencing that index name. Before dropping:

1. Verify the application has switched to the replacement index.
2. Confirm no background jobs or endpoints still depend on it.
3. Prepare a rollback plan.
4. Verify Search metadata after dropping.
5. Perform drops in production only through approved change control.

Do not use `db.collection.dropIndex()` as the default command to drop a MongoDB Search index.

### 16.5. Never Assume Every Backup Automatically Restores Search Indexes Ready to Query

After a restore, migration, or cluster tier change, inspect Search index definitions and build states. Depending on Atlas plan, snapshot/restore method, and deployment, Search indexes may require **resyncing or rebuilding**.

Restore runbooks must verify **both source data and Search readiness**, not merely that the app reconnects to MongoDB.

## 17. Atlas Permissions and Governance Scope

Atlas involves at least two permission layers:

- **Atlas project/organization roles:** create/view deployments, manage Search indexes via UI/API, provision Search Nodes.
- **MongoDB database user privileges:** read collections, run aggregations, manage Search indexes via `mongosh`/driver.

Having a connection string does not imply having every privilege.

### 17.1. Separating Application and Operator Roles

An application Search API typically needs:

- Connectivity and read access to authorized collections;
- Permission to run Search aggregations;
- No permission to drop or rebuild indexes;
- No Atlas project or billing permissions.

Operators and CI/CD pipelines need:

- Create/modify Search indexes;
- View index status;
- Provision Search Nodes where applicable;
- Monitor metrics and settings.

Separating duties reduces blast radius if an application credential is compromised.

### 17.2. Never Embed Credentials in Code

Wrong:

```javascript
// Avoid hardcoding URIs with usernames/passwords in repositories.
const uri = "mongodb+srv://username:password@example.mongodb.net";
```

In practice, use a secret manager or environment variables with TLS. Lesson examples assume an already-authenticated `db` handle in `mongosh` to avoid placing secrets in files.

### 17.3. What Does a Search Index Store?

Search indexes store derived representations of document data—tokens, field values, stored source, or query-supporting structures.

Do not equate "not storing the full document" with "contains no sensitive data." Text indexes hold sensitive keywords, and stored source keeps copies of fields. Protect Search Nodes and access paths as strictly as source data.

## 18. Version-Dependent Features

Not all MongoDB Search features appear across every MongoDB Server version simultaneously.

Feature areas with version dependencies include:

- Programmatic Search index management;
- Search queries on views;
- Search on sharded views;
- Search inside `$lookup`/`$unionWith`;
- Sorting and faceting on sharded clusters;
- Stored Source;
- Pagination via `searchAfter`/`searchBefore`;
- Newer ranking and hybrid-search operators;
- Queries/indexes on specialized collection types.

Illustrative milestones from Atlas Compatibility documentation:

| Feature | Illustrative Version Requirement |
|---|---|
| Create Search indexes on views | MongoDB 8.0+ per docs |
| Query views directly with `$search`/`$searchMeta` | MongoDB 8.1+ |
| Search on sharded views | MongoDB 8.2+ |
| `$lookup` with `$search` | Specific version support branches |
| `searchAfter`/`searchBefore` pagination | Minimum patch versions per docs |
| Dedicated Search Nodes | Requires supported Atlas tier, server version, and cloud/region |

**Never treat this table as a substitute for the official compatibility matrix.** Whenever a new release arrives or a cluster runs an older patch, verify each specific feature before adopting it.

### 18.1. Time-Series Collections

MongoDB Search has **restrictions on time-series collections**. Current compatibility docs note that Search is unsupported on time-series collections, and newer versions may raise explicit errors rather than silently returning empty results.

For sensor/time-series data, consider:

- Querying time-series data using standard indexes/queries;
- Materializing searchable metadata into a regular collection;
- Separating the searchable catalog from raw time-series measurements;
- Checking exact server-version restrictions.

Never create a Search index on a time-series collection expecting regular-collection behavior.

### 18.2. Preview Features Do Not Carry Universal SLAs

Newer offerings like Atlas Infinite or expanded Search capabilities may be in preview. Preview status can entail:

- Functional limits;
- Breaking API changes;
- Region/tier restrictions;
- Limited support/SLA coverage;
- Separate pricing models.

In production designs, check **actual release status** and organizational policy—not merely whether a toggle appears in the Atlas UI.

## 19. Atlas Search vs. MongoDB Vector Search

Both share `mongot` infrastructure, yet they solve different problems.

**MongoDB Search**:

```text
User types "tai nghe chống ồn"
      |
Lucene / analyzer / keywords
      |
Matching text + relevance score
```

**MongoDB Vector Search**:

```text
User describes intent
      |
Embedding model -> vector
      |
Vector similarity / ANN
      |
Semantically similar documents in embedding space
```

Common stages:

- `$search` / `$searchMeta`: lexical Search and search metadata.
- `$vectorSearch`: vector similarity search in supported configurations.

Never claim "Atlas Search understands all synonyms automatically" without configured synonym dictionaries or a suitable vector model.

### 19.1. Hybrid Search

An application can combine:

- Lexical Search for names, SKUs, and exact keywords;
- Vector Search for natural-language semantic queries;
- Re-ranking or rank fusion per supported features and versions.

However, hybrid pipelines may require multiple Search and Vector indexes, increasing cost and hitting tier index quotas. Verify compatibility and measure real relevance gains before committing to the design.

## 20. Performance: What Slows Search Down?

Primary factors:

1. **Index size:** document count, field count, token count, analyzers.
2. **Query complexity:** fuzzy matching, deep compounds, broad text, synonyms.
3. **Result count:** fetching top 10 differs vastly from scanning millions.
4. **Stored source:** whether documents must be fetched from the database.
5. **Cluster QPS / concurrency:** simultaneous query volume.
6. **Indexing rate:** ingest, update, and delete velocity.
7. **Resource contention:** whether `mongod` and `mongot` share or separate nodes.
8. **Network RTT:** app ↔ cluster and database ↔ Search nodes.
9. **Sharding:** number of shards/partitions Search must fan out across.
10. **Index freshness / rebuilds:** whether Search is performing initial sync or catching up.

### 20.1. Search Does Not Replace Application-Level Data Limits

An unbounded query without `$limit` or uncontrolled `returnStoredSource` can return massive payloads.

Well-structured API example:

```javascript
db.searchProductsLab.aggregate([
  {
    $search: {
      index: "catalog_text",
      text: {
        query: "tai nghe",
        path: "title"
      }
    }
  },
  { $limit: 20 },
  {
    $project: {
      _id: 1,
      title: 1,
      price: 1
    }
  }
]);
```

API safeguards should include:

- Maximum query length;
- Minimum character threshold for autocomplete;
- Maximum page size;
- Rate limiting;
- Timeouts;
- Bounds on fuzzy/prefix expansions;
- Business-valid query allowlists;
- Query pattern monitoring.

### 20.2. Do Not Count Every Match Unnecessarily

If the UI only displays the "top 20 results," computing exact total counts over massive result sets adds overhead. Choose count/facet strategies aligned with UX needs and evaluate `$searchMeta` carefully.

### 20.3. A High Search Score Does Not Prove a Query Is Fast

Relevance scores have nothing to do with p95 latency or resource consumption. Never use scores to judge execution performance.

## 21. Monitoring Search in Production

Essential metric groups:

| Group | What to Measure |
|---|---|
| Search queries | QPS, p50/p95/p99 latency, error rate |
| Index sync | Indexing lag, pending unprocessed changes |
| Index lifecycle | BUILDING/READY/STALE/error states, rebuild duration |
| Resources | Search and DB CPU, RAM, disk, IOPS |
| Search Nodes | Node count, health, restarts, capacity |
| Network | DB↔Search transfer, RTT, saturation |
| Query quality | Zero-result rate, click-through, relevance benchmarks |
| Autocomplete | Prefix lengths, query volume, debouncing effectiveness |
| Index footprint | Index size/count, field mapping growth |
| Application | Timeouts, fallback rate, authorization rejections |
| Cost | Search Nodes/tier, bandwidth, cluster resources |

### 21.1. Stale Search Results Cannot Be Detected by Uptime Alone

A cluster can report:

```text
mongod: healthy
mongot: queryable
Search index: lagging / stale
API: HTTP 200
```

Users still receive responses, yet the content is out of date.

Therefore, monitor **index freshness**, not just successful HTTP/query counts.

### 21.2. Canary Monitoring for Freshness

A practical check in appropriate environments:

1. Write a synthetic canary document with a dedicated ID into a canary collection.
2. Measure elapsed time from MongoDB write ACK until Search returns it.
3. Update/delete the canary and measure time until Search reflects the change.
4. Alert if lag exceeds the freshness budget.
5. Exclude canary documents from user-facing results.

Never treat canary measurements as an absolute consistency guarantee; it is an **empirical observability signal** along that tested path.

## 22. Cost and Sizing: Co-Located vs. Dedicated Search Nodes?

Guiding comparison:

| Criterion | Co-Located `mongot` | Dedicated Search Nodes |
|---|---|---|
| Provisioning | Simple | Requires configuring Search tier/nodes |
| Upfront cost | Often lower | Separate node billing |
| CPU/RAM contention with DB | Possible | Greatly reduced |
| Independent Search scaling | More limited | Much better |
| Index rebuild load | Shares DB infrastructure | Better isolated |
| Dev / prototype fit | Excellent | Usually unnecessary |
| High production QPS | Benchmark carefully | Usually recommended to evaluate |
| HA / region options | Follows cluster | Follows supported Search Node options |
| Network between Search and DB | Local (co-located) | Incurs cross-node RTT and transfer cost |

**Never choose Search Nodes based solely on a single document count.** One million documents with long text, multiple analyzers, and fuzzy queries can be heavier than tens of millions of short documents queried via simple equality.

MongoDB documentation lists **guidelines** for testing vs. sizing (such as document counts, indexed data volume, or query rates), not universal hard cutoffs. Always benchmark and size for your specific workload.

## 23. Java MongoDB Driver: Running `$search`

With the Java Sync Driver, you can build the aggregation pipeline using `Document`. This example keeps the BSON structure close to the MongoDB shell command.

```java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import org.bson.Document;

import java.util.Arrays;
import java.util.List;

MongoDatabase database = mongoClient.getDatabase("searchLab");
MongoCollection<Document> products =
    database.getCollection("searchProductsLab");

Document search = new Document(
    "$search",
    new Document("index", "catalog_text")
        .append("text",
            new Document("query", "tai nghe")
                .append("path", Arrays.asList("title", "description")))
);

Document project = new Document(
    "$project",
    new Document("title", 1)
        .append("price", 1)
        .append("score", new Document("$meta", "searchScore"))
);

Document limit = new Document("$limit", 10);

List<Document> pipeline = Arrays.asList(search, project, limit);

for (Document item : products.aggregate(pipeline)) {
    System.out.println(item.toJson());
}
```

Requirements for this code to run:

- `MongoClient` connected to a Search-enabled deployment;
- Matching `catalog_text` Search index exists;
- Index is queryable;
- Database user has read privileges;
- Collection contains documents with matching fields;
- Driver/server compatibility with the pipeline.

### 23.1. Do You Need the Latest Java Driver Just to Send BSON?

When simply **running** `$search` aggregations, many driver versions can forward the BSON stage as long as the server supports it. However, to **manage Search indexes** programmatically via helper APIs, your driver version must support those methods.

Atlas Search index management documentation specifies **minimum driver versions** (e.g., Java 4.11+ for certain management features). Check your exact driver's API docs before calling create/update/drop Search index methods from code.

### 23.2. Java: Never Hardcode Credentials

Load the connection URI from secrets or environment configuration:

```java
String uri = System.getenv("MONGODB_URI");

if (uri == null || uri.isBlank()) {
    throw new IllegalStateException("MONGODB_URI is required");
}

// MongoClient is created via MongoClients.create(uri)
// and closed per the application's lifecycle.
```

Never check real URIs, usernames/passwords, or certificates into source code or logs.

## 24. Why Search Should Never Be Used to Enforce Transactional Correctness

Suppose a product was just hidden:

```javascript
db.products.updateOne(
  { _id: "SKU-001" },
  { $set: { published: false } }
);
```

If an API **must guarantee hidden products never appear**, a Search query filtering `published: true` can still return stale candidates during indexing lag.

In that case:

- Filter inside Search for efficiency;
- Verify live state at the source when strict guarantees are needed;
- Never treat indexed fields as the sole source of authorization;
- Define fallback behavior when the database/read concern cannot confirm;
- Be deliberate about what enters `storedSource`.

Similarly, never rely on `$search` as the single source of truth to answer:

```text
"Has this order been paid yet?"
"Does this user still have permission to access the document?"
"Is there enough inventory to deduct 1 item?"
```

Those invariants require database queries, transactions, and unique constraints aligned with business rules.

## 25. When Search Fails: Classify Before Fixing

A Search query can fail for many distinct reasons.

| Symptom | Likely Cause | What to Check |
|---|---|---|
| Unrecognized pipeline stage `$search` | Server/deployment lacks Search or Search is unconfigured | Cluster tier, version, `mongot`, connection target |
| Search index not found | Wrong index name or index not created | `$listSearchIndexes`, namespace |
| Index not queryable yet | Initial build incomplete | Status, logs, resources |
| Zero results | Analyzer/mapping/query mismatch, lag, missing data | Sample docs, mapping, query paths |
| Missing newest results | Indexing lag | Freshness metric, source read |
| Type error on `equals` | Incompatible field mapping | `token`/number/boolean types |
| `$search` disallowed at position | Invalid pipeline ordering | Place stage first in its pipeline |
| High Search latency | Insufficient resources, index size, broad query, contention | Atlas metrics, explain/search tracing if available |
| Index creation failed | Permissions, tier limits, invalid definition | Role, index count, JSON size, server logs |
| Cannot add Search Nodes | Ineligible tier, region, or topology | Atlas Search tier availability |
| Search returns nothing after restore | Index not yet synced/rebuilt | Index status and deployment runbook |
| Used `$text` expecting fuzzy/autocomplete | Wrong engine | Create a Search index and use `$search` |

Never assume every `$search` error means "index is still building." Troubleshoot layer by layer: **deployment → permissions → index definition → index status → query shape → resources**.

### 25.1. Avoid Repeatedly Recreating Indexes to "Fix" Issues

A large index in `BUILDING` state needs time and compute. Triggering repeated rebuilds piles on load and worsens delays. Inspect status, logs, and resource headroom first before deciding to update, drop, or recreate.

### 25.2. Zero Search Results Does Not Mean the Document Is Missing

The document may exist in the collection while:

- The field is not mapped;
- The analyzer diverges from query expectations;
- The index has not caught up yet;
- A filter uses the wrong type;
- The Search index is in an error state;
- Tenant or visibility filters exclude it;
- The query targets the wrong index name.

Run an authorized `findOne({_id: ...})` against the source collection when debugging.

## 26. Phased Production Rollout

### Phase 1 — Define Search Goals

Specify:

- Which fields do users search?
- What are real query examples?
- Is accented and unaccented Vietnamese needed?
- Are autocomplete, fuzziness, or synonyms needed?
- Target QPS, p95 latency, zero-result rate?
- Document count and average size?
- Sensitive data constraints?
- Acceptable freshness SLO in seconds?
- Any strict read-after-write requirements?

### Phase 2 — Confirm Deployment Capabilities

Verify:

- Atlas tier and region;
- Server version;
- Search index quota;
- Whether Dedicated Search Nodes are needed;
- Project and database roles;
- Network and TLS setup;
- Budget/cost;
- If self-managed: `mongot` compatibility and topology.

### Phase 3 — Prepare Index Definition

- Choose dynamic vs. static mapping;
- Select searchable paths;
- Map `token` fields for exact filters;
- Select analyzers;
- Configure synonym and autocomplete fields;
- Define facet, sort, and stored-source needs;
- Enforce privacy exclusions;
- Adopt index naming and versioning conventions.

### Phase 4 — Build and Verify Status

- Create index via UI, API, `mongosh`, or driver;
- Wait until queryable;
- Measure initial sync duration;
- Run smoke-test queries;
- Measure indexing lag;
- Record resource metrics.

### Phase 5 — Business-Logic Testing

- Exact product name queries;
- Unaccented and misspelled queries;
- Tenant isolation queries;
- Newly published and unpublished products;
- Newly inserted products;
- Recently deleted products;
- Behavior during index rebuilds;
- Concurrent user load;
- Timeouts and fallbacks;
- Source-level authorization re-checks where required.

### Phase 6 — Rollout

- Gate the Search endpoint behind a feature flag;
- Shadow/compare results against the legacy system on representative queries;
- Canary traffic ramp-up;
- Monitor p95/p99 latency and search quality;
- Roll back by routing application traffic back, without rushing to drop the index;
- Clean up unused legacy indexes only after stability is confirmed.

### Phase 7 — Runbook

Document clear answers for:

- What does the API do if the Search index enters error or `STALE`?
- Is there a fallback while an index is rebuilding?
- Who responds if Search Nodes run out of RAM or disk?
- What is the UX when source data exists but Search lags?
- How are secrets and ACLs rotated?
- After a restore or regional failover, how is Search readiness verified?
- When index counts hit tier limits, when do we scale?
- When changing analyzers, how is relevance compared?

## 27. Practice Exercises

### Exercise 1 — Search Scope vs. Database Indexes

Given these requirements:

1. Fetch an exact product by `_id`.
2. Prevent duplicate `sku` values.
3. Search products matching `"tai nghe chống ồn"`.
4. Suggest products after typing 3 characters.
5. Confirm an order is paid before shipping.
6. Filter listings by price range and tenant.

Assign MongoDB B-tree index, unique index, transaction, or Atlas Search to each requirement. Explain why no single Search index replaces all of them.

### Exercise 2 — Classify Deployment Environments

Compare:

- Atlas Free;
- Atlas Flex;
- Atlas Dedicated co-located;
- Dedicated Search Nodes;
- Atlas local deployment;
- Self-managed Search with `mongot`.

For each, state: who manages the Search process, key limitations, best-fit use cases, and prerequisites to verify before production.

### Exercise 3 — Create a Search Index

On a test MongoDB Search deployment:

1. Create `searchProductsLab` with 5 documents.
2. Create the `catalog_text` index.
3. Map `title` and `description` as `string`.
4. Map `tenantId` and `category` as `token`.
5. Check status via `$listSearchIndexes`.
6. Run queries only once the index is queryable.

### Exercise 4 — Text Search and Score

Write a `$search` query for `"tai nghe"` across `title` and `description`.

1. Project `title`, `price`, and `score`.
2. Limit to 10.
3. Compare top results.
4. Change the keyword to `"bluetooth"`.
5. Why is `searchScore` not a business version number?

### Exercise 5 — Compound Search

Return only results belonging to `SHOP-A` with `published: true`.

1. Put the text query in `compound.must`.
2. Put `tenantId` and `published` in `compound.filter`.
3. Explain why `equals` requires matching field mappings.
4. Why is application-layer authorization still required?
5. What happens when `published` changes while the Search index is lagging?

### Exercise 6 — Search Index Lag

A product is inserted and MongoDB returns majority ACK. Immediately afterward, the Search UI does not show the product.

1. Can this be valid expected behavior?
2. How do majority ACK and Search visibility differ?
3. Design a UX for when the index is catching up.
4. How do you measure latency from write ACK to Search visibility?
5. When must you read directly from the database instead of Search?

### Exercise 7 — Autocomplete

Create an autocomplete index on `title` in a supported environment.

1. Query `"tai ng"`.
2. Measure result count and latency.
3. Experiment carefully with different `minGrams`/`maxGrams`.
4. Why does autocomplete enlarge index size?
5. Design debouncing and minimum length rules for the UI.

### Exercise 8 — Vietnamese and Analyzers

Prepare a test query set:

```text
tai nghe
tai-nghe
Tai Nghe
chống ồn
chong on
điện thoại
smartphone
bluetooth
blutooth
```

Check:

- Which queries match under the current analyzer?
- Do you need a custom analyzer or diacritic folding?
- Do you need synonyms?
- Do you need fuzzy typo tolerance?
- How do precision and recall change?

Never claim an index understands Vietnamese without testing on real data.

### Exercise 9 — Free/Flex Limits

A project on a Free cluster already has 3 Search/Vector indexes.

1. Can a fourth index be created under current docs limits?
2. Why does renaming an index not avoid the quota?
3. If a blue/green index rollout is needed, what must you plan for?
4. When scaling to Flex/Dedicated, what rebuild/sync checks are needed?
5. Where can exact current quota limits be verified?

### Exercise 10 — Dedicated Search Nodes

Suppose database p99 latency spikes during high Search QPS.

1. How do you identify contention between `mongod` and `mongot`?
2. What do Dedicated Search Nodes improve?
3. Do they make Search linearizable?
4. Which costs can increase?
5. Which metrics must be compared before and after separating nodes?

### Exercise 11 — Self-Managed Compatibility

A team runs an older MongoDB Community Edition on a standalone Windows server.

1. Can you immediately assume `$search` works?
2. What components are needed besides `mongod`?
3. Why must you check the MongoDB Server–`mongot` compatibility matrix?
4. Is native Windows `mongot` supported in current documentation?
5. Why does a local container not equal production HA?

### Exercise 12 — Search Index Lifecycle

The `catalog_text` index needs an analyzer change.

1. What is the pre-change testing plan?
2. Is the index immediately ready right after updating the definition?
3. Should you keep the old index running in parallel?
4. Which resources spike during a rebuild?
5. When is it safe to drop the old index?

### Exercise 13 — Search vs. Vector Search

Requirements:

- Exact lookup for model code `"ABC-123"`;
- Text search for `"tai nghe chống ồn"`;
- Similar-product search from long natural-language descriptions.

Recommend lexical Search, Vector Search, or hybrid, and explain the **index, data, and infrastructure prerequisites** of each.

### Exercise 14 — Production API Design

Design:

```text
GET /products/search?q=...&tenant=...&limit=...
```

Specify:

- Authentication and authorization;
- Tenant filtering;
- Text analyzer;
- Page size;
- Search index name/version;
- Retries, timeouts, and fallbacks;
- Index freshness SLO;
- Monitoring and alerting;
- Handling an unavailable index;
- When to fall back to source data reads;
- How to roll out a new index.

### Exercise 15 — Recovery

An Atlas cluster recovers from an outage. MongoDB `find()` works, but `$search` returns an index-not-ready error.

1. Is this necessarily source data corruption?
2. Which Search index states must be inspected?
3. Should the app send live search traffic right away?
4. When should a fallback be engaged?
5. Why must DR runbooks include Search readiness verification?

## 28. Pre-Deployment Checklist

- [ ] Clearly identified **Atlas-managed**, local, or **self-managed `mongot`**.
- [ ] Checked cluster tier, region, and server version against compatibility docs.
- [ ] Distinguished Free/Flex feature quotas from production capacity.
- [ ] Assigned least-privilege Project and database roles.
- [ ] Configured valid MongoDB network, TLS, and credentials.
- [ ] Created Search indexes with the proper supported API/UI.
- [ ] Distinguished `createSearchIndex()` from B-tree `createIndex()`.
- [ ] Waited for index READY/queryable status after initial build.
- [ ] Explicitly mapped searchable text, token filters, numeric, and boolean fields.
- [ ] Tested analyzers on target languages and real data.
- [ ] Placed `$search`/`$searchMeta` at supported pipeline positions.
- [ ] Bounded query length, page size, and autocomplete load.
- [ ] Avoided relying on Search indexes to enforce uniqueness or authorization.
- [ ] Designed around **eventual consistency / indexing lag**.
- [ ] Instrumented p95/p99 latency, Search QPS, index size, sync lag, and node health.
- [ ] Built a capacity/cost plan for co-located or Dedicated Search Nodes.
- [ ] Avoided hard production dependencies on preview features lacking SLAs.
- [ ] Prepared rollback and recovery steps if indexes rebuild or become non-queryable.
- [ ] Established a test workflow before editing mappings or analyzers.
- [ ] If self-managed, verified `mongot` runtime, OS, security, and version compatibility.

## 29. Official References

The references below cover concepts, deployment scopes, and version limits. Because MongoDB documentation evolves across releases, always verify the **current documentation on the day of deployment**.

- [MongoDB Search — Overview](https://www.mongodb.com/docs/search/)
- [MongoDB Search Deployment Options](https://www.mongodb.com/docs/search/deployment/deployment-options/)
- [MongoDB Search Compatibility & Limitations](https://www.mongodb.com/docs/search/deployment/feature-compatibility/)
- [MongoDB Search — Manage Indexes](https://www.mongodb.com/docs/search/indexes/manage-indexes/)
- [MongoDB Search and Vector Search on Self-Managed Deployments](https://www.mongodb.com/docs/search/self-managed/current/)
- [Self-Managed mongot Compatibility and Requirements](https://www.mongodb.com/docs/search/self-managed/current/deployment/compatibility-requirements/)
- [MongoDB Atlas Search Node Costs](https://www.mongodb.com/docs/atlas/billing/search-node/)
- [MongoDB Atlas Search Node Workload Isolation](https://www.mongodb.com/docs/atlas/cluster-config/multi-cloud-distribution/)
- [createSearchIndexes Database Command](https://www.mongodb.com/docs/manual/reference/command/createsearchindexes/)
- [$search Aggregation Stage](https://www.mongodb.com/docs/atlas/atlas-search/aggregation-stages/search/)
- [$searchMeta Aggregation Stage](https://www.mongodb.com/docs/atlas/atlas-search/aggregation-stages/searchMeta/)
- [MongoDB Search Index Mapping](https://www.mongodb.com/docs/atlas/atlas-search/define-field-mappings/)
- [MongoDB Java Sync Driver](https://www.mongodb.com/docs/drivers/java/sync/current/)

## Conclusion

**Atlas Search** is a Lucene-powered full-text search capability offered as a **managed** service on MongoDB Atlas. In modern product documentation it sits under **MongoDB Search**, providing `$search`, `$searchMeta`, Search indexes, relevance ranking, autocomplete, fuzzy matching, synonyms, facets, and highlighting.

Deployment eligibility spans multiple layers: **the deployment must support Search**, permissions must be granted, Search index mappings must match queries, **the index must be queryable**, and infrastructure must have adequate capacity. Atlas **Free/Flex** fit learning and small workloads within tier quotas; **Dedicated clusters** handle heavier traffic; **Dedicated Search Nodes** isolate Search from database compute where eligible. **Local** deployments serve development, while **self-managed MongoDB Search** is viable on supported versions and architectures when your operations team manages `mongot`.

Search indexes synchronize **asynchronously** with source data. Consequently, **Search never replaces transactions, uniqueness, backups, authorization, or queries requiring read-after-write/linearizable consistency**. A production Search API must plan for indexing lag, index lifecycles, analyzers, security filtering, resource contention, version compatibility, infrastructure costs, and disaster recovery.

**Deploying Atlas Search properly goes beyond getting `$search` to run: it requires picking the right environment, indexing the right fields, respecting consistency boundaries, and proving infrastructure handles your workload before promising a search experience to users.**
