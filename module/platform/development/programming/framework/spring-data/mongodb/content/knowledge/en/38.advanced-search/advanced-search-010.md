# Distinguishing Capabilities of MongoDB Server, the Search Service, and Spring Data APIs

> **Chapter:** Advanced Search  
> **Module:** `SPRING_DATA_MONGODB` — using Spring Data MongoDB to connect, map documents, and interact with MongoDB via `MongoTemplate` or repositories. Practicing queries, aggregation, indexes, transactions, reactive access, testing, and data performance diagnostics.  
> **Objective:** Clearly separate **MongoDB Database Server (`mongod`/`mongos`) capabilities**, the **MongoDB Search/Vector Search service (`mongot`)**, and **Spring Data MongoDB APIs**; identify exact feature gates by deployment and version; design exact/range, `$regex`, `$text`, `$search`, `$searchMeta`, and `$vectorSearch` queries; use `MongoTemplate`, repositories, and aggregation per their contracts; and organize Search indexes, scoring, pagination, tenant filters, consistency, testing, and fallbacks verifiably.

## 1. Three Layers Commonly Lumped Together

In a Java application using Spring Data MongoDB, a developer might write:

~~~java
mongoTemplate.aggregate(aggregation, ProductDocument.class, SearchHit.class);
~~~

Yet that Java statement **does not prove** the cluster can execute every aggregation stage sent to it. You must distinguish:

1. **MongoDB Database Server**: executes CRUD, standard aggregation, the query planner, and B-tree/text/2dsphere/hashed/wildcard indexes according to server version features.
2. **MongoDB Search / MongoDB Vector Search service**: a separate search/indexing engine (`mongot`) providing lexical search, relevance, autocomplete, fuzzy matching, facets, and semantic vector search when deployed and supported.
3. **Spring Data MongoDB / Java Driver**: client-side APIs for building BSON queries, managing search indexes, and sending commands/aggregations to the server; provides type mapping, repositories, reactive streams, and query helpers, **without replacing server-side engines**.

~~~mermaid
flowchart LR
    U["UI / HTTP API"] --> A["Spring service"]
    A --> D["Spring Data MongoDB / Java Driver"]
    D --> M["mongod / mongos"]
    M --> I["Database indexes: B-tree, text, geo..."]
    M -->|"Search stages when capable"| S["mongot / MongoDB Search"]
    S --> SI["Search / Vector indexes"]
    M --> C["Current documents"]
    S -. "Synced from DB data; has index lag" .- C
~~~

**Core takeaway:** Spring Data can serialize a `$search` stage into valid BSON, but a MongoDB deployment lacking the Search service or index still cannot execute it. Similarly, adding search or vector libraries in Java does not make `mongod` generate Search indexes automatically.

### 1.1. Quick Identification Reference

| Question | Responsible Layer |
| --- | --- |
| Does `find({sku:"X"})` use a B-tree index? | MongoDB Server, index/query plan |
| Does `$text` use the collection's text index? | MongoDB Server, text index |
| Can `$search`, fuzzy, autocomplete, or highlights run? | Search service + index + deployment/version |
| Can `$vectorSearch` and vector pre-filters run? | Vector Search service/index + deployment/version |
| Does Java have the `VectorSearchOperation` class? | Spring Data MongoDB version |
| Does the query use the physical BSON field name from `@Field`? | Spring Data mapping and how BSON was constructed |
| When an index is newly created, is a document immediately searchable? | Search index synchronization and readiness |
| Do AI embeddings match the expected dimensions and model? | Embedding pipeline, vector index, query input |
| Who is allowed to see another tenant's documents? | Business authorization **and** filters enforced at the search engine |

## 2. MongoDB Server and the Search Service Are Not the Same Index Engine

### 2.1. Database Query Engine

Typical syntax:

~~~javascript
db.catalog_advanced_010.find({
  tenant_id: "t01",
  active: true,
  category: "laptop",
  price_vnd: { $gte: 10000000, $lte: 30000000 }
});
~~~

MongoDB Server can serve this query using a suitable index:

~~~javascript
db.catalog_advanced_010.createIndex(
  { tenant_id: 1, active: 1, category: 1, price_vnd: 1 },
  { name: "ix_catalog_tenant_active_cat_price" }
);
~~~

This is a **database index**, not a Search index. Likewise, the Server has `$regex` and `$text`, but their lexical processing, relevance, and ranking capabilities **are not equivalent** to a dedicated search service.

### 2.2. Search Service

MongoDB Search runs the `mongot` process (built on Apache Lucene), synchronizing index data from MongoDB documents and handling `$search`/`$searchMeta`. MongoDB Vector Search uses the Search engine to process `$vectorSearch` over vector indexes. Clients still send aggregations through the database endpoint: applications **never connect directly to `mongot`**.

Capabilities typically provided by the Search service:

- Language analyzers/tokenization, autocomplete, phrases, fuzzy matching, and wildcards/regexes in the **Search DSL**.
- Relevance scoring, score boosting, and compound scoring mechanisms.
- Highlights and search metadata/facets.
- Vector similarity / approximate nearest neighbors (ANN), and exact nearest neighbors (ENN) where supported by version.
- Dedicated Search-index mappings and separate build/status lifecycles.

**Never infer** that `createIndex({title:"text"})` creates a MongoDB Search index or that `createSearchIndex(...)` creates a B-tree index.

### 2.3. Differences in Index Updates

~~~text
MongoDB write acknowledged
        |
        +-- Database index maintained on the DB write path
        |
        +-- Search service syncs from mongod data
                 -> updates may appear later in Search results
~~~

Therefore, “I just inserted a record, `findById` sees it, but `$search` doesn't” **does not prove an application bug**. Check that the Search index is `READY`, mappings are right, and account for Search indexing lag. Never build strict read-after-write guarantees assuming instant Search index updates.

## 3. Capabilities Depend on **Deployment and Version**, Not Just the URI

Naming has evolved: older documentation often says **Atlas Search/Atlas Vector Search**, while current MongoDB documentation says **MongoDB Search/MongoDB Vector Search** and covers supported self-managed deployments.

### 3.1. Deployment Matrix to Remember

| Environment | CRUD / B-tree / `$text` | `$search` / `$searchMeta` | `$vectorSearch` | Extra Verification Required |
| --- | --- | --- | --- | --- |
| MongoDB Atlas cluster with Search configured | Yes | Yes when Search index/service is ready | Yes when Vector index/service is ready | Cluster tier/region/version, index `READY`, permissions |
| Standard self-managed MongoDB Community **prior to 8.2** | Yes | Not supported natively by default | Not supported natively by default | Do not treat standalone `mongo:7/8.0` like Atlas |
| Self-managed MongoDB Community **8.2+** via supported Search path | Yes | Yes when `mongot` is deployed/configured properly | Yes when index/features match | Check self-managed guide, version/edition, resources |
| Self-managed MongoDB Enterprise **8.2+** with Kubernetes Operator per docs | Yes | Yes per supported setup | Yes per supported setup | Check operator, topology, license/support conditions |
| `mongodb-atlas-local` for testing | Yes | Yes per provided image/config | Yes per provided image/config | Development image, **not production HA** |

**Important note:** Conditions in this table reflect MongoDB documentation at the time of writing. They **do not imply** “every Community 8.2+ automatically includes Search just by upgrading `mongod`”. Self-managed Search requires deploying and operating `mongot` per the guide, and specific features have compatibility rules and limitations. Also, some Spring Data docs still use “Atlas-only” phrasing written before MongoDB expanded self-managed support; verify **server docs + Spring Data version** instead of relying on a single older Javadoc sentence.

### 3.2. Distinct Version Gates

- `$search`, `$searchMeta`: require a Search deployment and Search index.
- `$vectorSearch`: requires a Search-capable environment/version + vector index and valid vector/filter parameters.
- `VectorSearchOperation` in Spring Data was added in newer versions than classic `TextQuery`; **do not** use that class on older Spring Data releases without checking dependencies.
- Repository `@VectorSearch`/`Vector`/`SearchResults<T>` belong to newer Spring Data releases; code snippets from `current` docs may not compile on older project versions.
- Certain hybrid/fusion/pagination features carry specific version and index constraints; feature-detect and test in your target environment.

### 3.3. Verify Deployment Instead of Guessing

In `mongosh` on an authorized environment:

~~~javascript
db.adminCommand({ buildInfo: 1 }).version;
db.adminCommand({ hello: 1 });

// Only on a specific collection and with proper privileges:
db.catalog_advanced_010.aggregate([
  { $listSearchIndexes: {} }
]);
~~~

`buildInfo` tells you the `mongod` version; it **does not guarantee `mongot` is ready**. `$listSearchIndexes` is a helpful index/status check when the deployment supports Search; it will fail on environments lacking that feature or permission. Never lump `Unauthorized`, `Unknown pipeline stage`, and `index not found` together as the same root cause.

### 3.4. Short Capability Checklist

1. MongoDB server version, edition, and topology?
2. Is the Search process/service deployed and healthy?
3. Does the Search/Vector index exist with the exact **collection, name, type, and paths**?
4. Is the index `READY` or still `BUILDING`/`STALE`?
5. Do Java Driver and Spring Data versions include the required APIs?
6. Do the query DSL and BSON fields match the mapping?
7. Are auth/tenant filters applied inside the search stage?
8. Have integration tests run against a representative environment?

## 4. Choose the Engine by Requirement, Not by Pretty Syntax

| Requirement | Preferred Option | Why |
| --- | --- | --- |
| Lookup by `_id`, SKU, canonical email | Database exact match + B-tree | Exact, proper index |
| Date, price, status filters and sorting | Database query/aggregation + compound index | No Search engine needed |
| Bounded SKU prefix | Anchored `$regex` or prefix search per index/collation requirements | Simple prefix may suffice |
| Basic multi-word search in title/description | Database `$text` + text index if acceptable | Built-in mechanism, limited features |
| Autocomplete, fuzzy typos, language analyzers, highlights | MongoDB Search `$search` | Search-specific index and operators |
| Category/brand facets from search results | `$searchMeta` facet or `$search` + metadata | Search facet semantics |
| “Semantically similar products” via embeddings | MongoDB Vector Search `$vectorSearch` | Vector similarity query |
| Combining keyword relevance and vector relevance | Search/hybrid/fusion per version features; or app-side fusion | Ranking needs; check capability |
| Order writes, transactions, optimistic locking | MongoDB Server + Spring Data CRUD/tx | Never solve with a Search index |
| Must see results immediately after a critical write | Primary DB query by ID/status or explicit freshness design | Search indexing has lag |

### 4.1. A Decision Workflow

~~~mermaid
flowchart TD
    A["Search requirement"] --> B{"Exact code / structured filter?"}
    B -->|"Yes"| C["MongoDB find / aggregation + indexes"]
    B -->|"No"| D{"Simple keywords?"}
    D -->|"Yes, limitations acceptable"| E["$text + text index"]
    D -->|"Needs fuzzy/autocomplete/relevance"| F["MongoDB Search $search"]
    D -->|"Needs semantic similarity"| G["MongoDB Vector Search $vectorSearch"]
    F --> H{"Deployment/index supported?"}
    G --> H
    H -->|"No"| I["Upgrade deployment or fallback with explicit contract"]
    H -->|"Yes"| J["Use Spring Data / Driver to send pipeline"]
~~~

Never replace `$text` with `$search` merely because the name sounds “more powerful” when your product only needs exact filters. Conversely, do not try to build high-quality autocomplete using collection-wide regex scans when the requirement is scored search-as-you-type.

## 5. Running Dataset: Multi-Tenant Catalog

Create the test collection:

~~~javascript
use spring_data_mongodb_lab

db.createCollection("catalog_advanced_010");

db.catalog_advanced_010.insertMany([
  {
    _id: "p010-01",
    tenant_id: "t01",
    sku: "LT-A100",
    title: "Laptop văn phòng 14 inch",
    description: "Máy nhẹ, pin lâu, phù hợp văn phòng",
    category: "laptop",
    active: true,
    price_vnd: NumberLong(18500000),
    tags: ["văn phòng", "mỏng nhẹ"],
    embedding: [0.14, 0.31, 0.07, 0.92]
  },
  {
    _id: "p010-02",
    tenant_id: "t01",
    sku: "LT-B200",
    title: "Laptop đồ họa 16 inch",
    description: "GPU hiệu năng cao cho thiết kế hình ảnh",
    category: "laptop",
    active: true,
    price_vnd: NumberLong(29800000),
    tags: ["đồ họa", "GPU"],
    embedding: [0.81, 0.12, 0.73, 0.05]
  },
  {
    _id: "p010-03",
    tenant_id: "t01",
    sku: "TB-C300",
    title: "Bàn phím cơ không dây",
    description: "Gõ êm, kết nối bluetooth",
    category: "peripheral",
    active: false,
    price_vnd: NumberLong(1650000),
    tags: ["bàn phím", "không dây"],
    embedding: [0.06, 0.88, 0.15, 0.19]
  },
  {
    _id: "p010-04",
    tenant_id: "t02",
    sku: "LT-A100",
    title: "Laptop văn phòng cho doanh nghiệp",
    description: "Máy tính công việc",
    category: "laptop",
    active: true,
    price_vnd: NumberLong(17200000),
    tags: ["văn phòng"],
    embedding: [0.17, 0.33, 0.08, 0.88]
  }
]);
~~~

**Do not run on production or shared databases.** Running the fixture twice without cleanup causes duplicate `_id` errors; use a clean test database/unique IDs and targeted cleanup rather than recklessly running `dropDatabase()`.

### 5.1. Why Are Embeddings Only 4 Dimensions Long?

Vectors like `[0.14,0.31,0.07,0.92]` are **simulated numbers to demonstrate syntax**. They **are not trained semantic embeddings** and do not prove any real semantic relationship between laptops and keyboards.

Real applications must choose an embedding model, consistent dimensionality, normalization, and versioning, and store vectors for **every searchable document**. Query vectors must come from the **exact same model/space** as indexed vectors and share the exact dimension.

### 5.2. Database Indexes for Filtering

~~~javascript
db.catalog_advanced_010.createIndex(
  { tenant_id: 1, active: 1, category: 1, price_vnd: 1 },
  { name: "ix_tenant_active_category_price" }
);

db.catalog_advanced_010.createIndex(
  { tenant_id: 1, sku: 1 },
  { unique: true, name: "uq_tenant_sku" }
);
~~~

Do not confuse these two indexes with Search indexes; they are database indexes serving standard `find`/aggregation queries and uniqueness constraints.

### 5.3. Basic Java Schema

~~~java
// CatalogProduct.java
package com.example.advancedsearch;

import java.util.List;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.mapping.MongoId;

@Document(collection = "catalog_advanced_010")
public class CatalogProduct {
    @MongoId(FieldType.STRING)
    private String id;

    @Field("tenant_id")
    private String tenantId;

    private String sku;
    private String title;
    private String description;
    private String category;
    private boolean active;

    @Field("price_vnd")
    private long priceVnd;

    private List<String> tags;
    private List<Double> embedding;

    protected CatalogProduct() {}

    public String getId() { return id; }
    public String getTenantId() { return tenantId; }
    public String getSku() { return sku; }
    public String getTitle() { return title; }
    public String getDescription() { return description; }
    public String getCategory() { return category; }
    public boolean isActive() { return active; }
    public long getPriceVnd() { return priceVnd; }
}
~~~

`@MongoId(FieldType.STRING)` maps string `_id` values matching the fixture. `@Field("tenant_id")`/`@Field("price_vnd")` illustrate the difference between **Java properties** and **BSON field paths**; raw `Document` queries must use exact BSON names rather than assuming automatic mapping in every API.

## 6. Exact Lookup and Structured Filtering: `find` + B-Tree Index

### 6.1. MongoDB Server Query

~~~javascript
db.catalog_advanced_010.find(
  {
    tenant_id: "t01",
    active: true,
    sku: "LT-A100"
  },
  {
    _id: 1,
    sku: 1,
    title: 1,
    price_vnd: 1
  }
);
~~~

When you only need exact filtering and standard comparisons, neither Search indexes nor embedding models are needed.

### 6.2. Spring Data `Query`/`Criteria`

~~~java
import java.util.List;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

Query query = Query.query(
    Criteria.where("tenantId").is("t01")
        .and("active").is(true)
        .and("category").is("laptop")
        .and("priceVnd").gte(10000000L).lte(30000000L)
).limit(20);

List<CatalogProduct> products =
    mongoTemplate.find(query, CatalogProduct.class);
~~~

In an entity-aware query, `tenantId` and `priceVnd` are mapped by Spring Data to `tenant_id` and `price_vnd`. Actual MongoDB behavior still depends on the database data and indexes, not merely on calling a Java method named `find`.

### 6.3. Repository Derived Query

~~~java
import java.util.List;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface CatalogRepository
        extends MongoRepository<CatalogProduct, String> {

    List<CatalogProduct> findTop20ByTenantIdAndActiveTrueAndCategoryOrderByPriceVndAsc(
        String tenantId,
        String category
    );
}
~~~

This is Spring Data query derivation producing a database query; it does **not** emit `$search` or touch a Lucene Search index. The repository method name states intent, while performance still depends on the query planner and MongoDB indexes.

### 6.4. Measuring with `explain`

~~~javascript
db.catalog_advanced_010.find({
  tenant_id: "t01",
  active: true,
  category: "laptop"
}).explain("executionStats");
~~~

Inspect `winningPlan`, `totalKeysExamined`, `totalDocsExamined`, `nReturned`, and `executionTimeMillis` in context. Specific metrics depend on version and execution engine. A `COLLSCAN` on a 4-document fixture is not necessarily wrong; on large production datasets, evaluate index selectivity and cost.

## 7. `$regex`: String Pattern Matching, Not a Full-Text Search Engine

### 7.1. Simple Prefix Regex

~~~javascript
db.catalog_advanced_010.find({
  tenant_id: "t01",
  sku: { $regex: "^LT-" }
});
~~~

A regex with a `^` anchor for a prefix, combined with appropriate indexes and collation, can perform much better than an unanchored regex like `.*LT.*`. Still, performance depends on pattern shape, case sensitivity, indexes, and the query planner.

### 7.2. Arbitrary Substring Regex

~~~javascript
db.catalog_advanced_010.find({
  tenant_id: "t01",
  description: { $regex: "văn phòng", $options: "i" }
});
~~~

This performs pattern matching; it **lacks** a tokenizer, relevance ranking, fuzzy edit distance, and semantic search comparable to MongoDB Search. Case-insensitive `$regex` is also not equivalent to a Vietnamese accented/unaccented analyzer.

### 7.3. Security and Performance Warning

**Never** concatenate arbitrary user strings into a regex query without validation, escaping, and bounds:

- Complex regexes can exhaust CPU and force full collection scans.
- Limit input/pattern length and enforce query timeouts.
- When only a literal prefix is needed, escape regex metacharacters before prepending `^`.
- Always include the tenant filter; never fetch 10 cluster-wide results and filter tenants afterward.

Java example for literal prefixes only:

~~~java
import java.util.regex.Pattern;

String userPrefix = "LT-";
Pattern safePrefix = Pattern.compile(
    "^" + Pattern.quote(userPrefix)
);

Query query = Query.query(
    Criteria.where("tenantId").is(authenticatedTenantId)
        .and("sku").regex(safePrefix)
).limit(20);
~~~

`authenticatedTenantId` must come from an authenticated principal/context, never a client-supplied tenant field. The regex is escaped so users cannot inject arbitrary pattern operators.

## 8. `$text` Is **MongoDB Server's** Built-In Text Search

### 8.1. Creating a Regular **Text Index**

~~~javascript
db.catalog_advanced_010.createIndex(
  { title: "text", description: "text" },
  {
    name: "ix_catalog_text",
    weights: { title: 5, description: 1 }
  }
);
~~~

A MongoDB Server collection enforces a text index limit (typically **one text index per collection**, though spanning multiple fields), and `$text` has operator, hint, and sort restrictions. This index **differs** from a `type: "search"` index managed by the Search service.

### 8.2. Querying and Sorting by `textScore`

~~~javascript
db.catalog_advanced_010.find(
  {
    tenant_id: "t01",
    active: true,
    $text: { $search: "laptop văn phòng" }
  },
  {
    title: 1,
    sku: 1,
    score: { $meta: "textScore" }
  }
).sort({
  score: { $meta: "textScore" }
}).limit(10);
~~~

For `$text`, relevance score is retrieved via `$meta: "textScore"`, **distinct** from MongoDB Search's `$meta: "searchScore"` or Vector Search's `"vectorSearchScore"`.

### 8.3. Important Limitations

- `$text` relies on a MongoDB Server text index, not a Search index/`mongot`.
- Tokenization, stemming, and language support differ from Search analyzers.
- Adding `$regex` does not give `$text` Search DSL fuzzy/autocomplete features.
- In aggregation, `$match` containing `$text` must be the first stage of its pipeline and carries restrictions.
- `$text` results are not sorted by relevance by default unless score sorting is requested.
- Accented/unaccented Vietnamese search must be **tested on real data**; do not assume default text analyzers handle all Vietnamese variations as users expect.

### 8.4. When Is `$text` Still Worth Using?

When the goal is basic keyword matching on small-to-medium data, text index semantics are acceptable, and operating a dedicated Search service is unnecessary. Benchmark with your deployment version and relevance requirements in mind; do not claim `$text` is always “good enough” for an e-commerce storefront requiring typos, autocomplete, and rich Vietnamese analysis.

## 9. Spring Data `TextCriteria`/`TextQuery` Still Target MongoDB `$text`

~~~java
import java.util.List;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.TextCriteria;
import org.springframework.data.mongodb.core.query.TextQuery;

TextCriteria criteria = new TextCriteria()
    .matchingAny("laptop", "văn phòng");

TextQuery query = TextQuery.queryText(criteria)
    .sortByScore()
    .includeScore();

// Combine tenant + active in the same query.
query.addCriteria(
    Criteria.where("tenantId").is(authenticatedTenantId)
        .and("active").is(true)
);
query.limit(10);

List<CatalogProduct> results =
    mongoTemplate.find(query, CatalogProduct.class);
~~~

`TextQuery`/`TextCriteria` are abstractions specifically for **database `$text`**; they never emit `$search`. Having “Text” or “Search” in a Java method name does not decide which engine runs; inspect the generated BSON query and actual indexes.

### 9.1. Is the Text Score Populated in the Entity?

`TextQuery.includeScore()` asks MongoDB to return score metadata, yet the `CatalogProduct` entity in section 5 defines no corresponding score property. Do not expect `getScore()` to magically exist or populate without configuring the entity property/DTO projection metadata for your version.

To inspect raw BSON while learning:

~~~java
List<org.bson.Document> documents = mongoTemplate.find(
    query,
    org.bson.Document.class,
    "catalog_advanced_010"
);
~~~

**Mapping caveat:** A query written with entity property names (`tenantId`) gets mapped when executed against `CatalogProduct.class`; if you switch to raw `Document.class`, pass exact BSON names (`tenant_id`). Never copy the typed Java query verbatim into raw `Document` mode and wonder why the tenant filter fails to match. When running raw, construct `TextQuery` and filter `tenant_id` explicitly.

### 9.2. Repository `@TextScore` Does Not Mean Atlas Search Score

Spring Data provides helpers to map `$text` scores in certain versions, yet never mix them with `searchScore` or `vectorSearchScore`. Their scoring engines and result shapes differ:

~~~text
MongoDB text index -> $text -> $meta "textScore"
MongoDB Search      -> $search -> $meta "searchScore"
MongoDB Vector      -> $vectorSearch -> $meta "vectorSearchScore"
~~~

Scores from different engines **do not share a scale or meaning**; never add or directly compare them without a proper normalization and ranking strategy.

## 10. MongoDB Search Index: Specialized Mappings and `READY` Status

MongoDB Search uses a **Search index definition** distinct from B-tree and text indexes. For the `catalog_advanced_010` fixture, create an index named `catalog_lexical` on a Search-enabled deployment:

~~~javascript
db.catalog_advanced_010.createSearchIndex(
  "catalog_lexical",
  {
    mappings: {
      dynamic: false,
      fields: {
        title: { type: "string" },
        description: { type: "string" },
        tags: { type: "string" },
        tenant_id: { type: "token" },
        active: { type: "boolean" },
        category: { type: "token" },
        price_vnd: { type: "number" }
      }
    }
  }
);
~~~

Here `token` handles exact-match filter fields (`tenant_id`, `category`) while `string` handles fields needing text analyzers. Exact options for analyzers, normalizers, facets, sortable fields, nested documents, and field types depend on feature version. For Vietnamese search, design custom analyzers/synonyms and measure quality rather than assuming the standard analyzer handles all diacritics and variants.

### 10.1. Checking `READY`

~~~javascript
db.catalog_advanced_010.aggregate([
  { $listSearchIndexes: {} }
]);
~~~

Filter for the target index:

~~~javascript
db.catalog_advanced_010.aggregate([
  { $listSearchIndexes: { name: "catalog_lexical" } }
]);
~~~

A successful create command or `exists` returning `true` **does not mean the index is ready to serve queries**. Check build/`READY` status (and queryable flags per version/deployment), especially in CI and right after deployments.

### 10.2. Search Indexes Do Not Share the B-Tree Query Planner

~~~text
db.collection.createIndex({sku:1})
    -> Database B-tree / classic query plan.

db.collection.createIndex({title:"text"})
    -> Database text index for $text.

db.collection.createSearchIndex("catalog_lexical", {...})
    -> MongoDB Search index for $search/$searchMeta.

db.collection.createSearchIndex("catalog_vector", "vectorSearch", {...})
    -> Vector Search index for $vectorSearch.
~~~

Calling `hint("catalog_lexical")` inside `find` will not turn a normal query into a Search query. Likewise, `$search` will not use the B-tree index `ix_tenant_active_category_price` to run lexical search; Search requires fields mapped inside the **Search index definition**.

### 10.3. Modifying a Search Index Definition Is an Operational Event

Changing analyzers, field mappings, or similarity functions can trigger a rebuild/reindex. You need:

- Version-controlled index definitions managed via migrations/infrastructure.
- Planned rollout windows and readiness verification.
- Testing in a production-like Search environment.
- Coordinated cutover from old index names to new index version names when running side-by-side indexes.
- A rollback plan and capacity budgeting for index builds and Search nodes.

Never create or drop Search indexes on every HTTP request or inside business transactions.

## 11. `$search` Is an Aggregation Stage of the Search Service

### 11.1. Lexical Search Example with Tenant Filter

~~~javascript
db.catalog_advanced_010.aggregate([
  {
    $search: {
      index: "catalog_lexical",
      compound: {
        must: [
          {
            text: {
              query: "laptop",
              path: ["title", "description", "tags"]
            }
          }
        ],
        filter: [
          { equals: { path: "tenant_id", value: "t01" } },
          { equals: { path: "active", value: true } }
        ]
      }
    }
  },
  {
    $project: {
      _id: 1,
      title: 1,
      sku: 1,
      price_vnd: 1,
      score: { $meta: "searchScore" }
    }
  },
  { $limit: 10 }
]);
~~~

**Meaning of each part:**

- `$search` is the first stage of the pipeline.
- `index` is the **Search index name**, not a database index name.
- `text.query` and `path` define the lexical search.
- `compound.must` expresses scoring search conditions.
- `compound.filter` expresses non-scoring predicates, ideal for tenant, active, and ACL metadata.
- `$meta: "searchScore"` returns relevance scores for display or ranking adjustments.
- `$limit` caps output to avoid transferring thousands of unnecessary documents.

### 11.2. Why Must the Tenant Filter Sit Inside `$search`?

Dangerous:

~~~javascript
db.catalog_advanced_010.aggregate([
  { $search: {
      index: "catalog_lexical",
      text: { query: "laptop", path: "title" }
  }},
  { $limit: 5 },
  { $match: { tenant_id: "t01" } }
]);
~~~

If Search returns the global top 5 across all tenants before filtering, you can get **fewer than 5 valid results even when tenant t01 has plenty of matches at rank 6+**. The query also wastes candidate retrieval and ranking effort on other tenants' data.

Push tenant/ACL filters into the **Search DSL before top-K ranking**, using fields mapped for filtering. Add a defensive post-Search `$match` if policy requires, but never replace early filtering with post-filtering when accurate top-K matters.

### 11.3. Search-Index Field Types Must Match Operators

For example, `equals:{path:"tenant_id",value:"t01"}` requires a field type supporting exact matching, typically `token`. Indexing `tenant_id` only as analyzed `string` text and applying `equals` can fail or miss matches depending on mapping/version.

Similarly:

- `range` on prices requires `number` mapping.
- `exists`/boolean filters require compatible field mappings.
- Autocomplete requires `autocomplete` field types/operators rather than default `text`.
- String facets require index mappings supporting token/facet behavior per version.

### 11.4. Relevance Is Not Business Sorting

If a user requests “lowest price among matching products”, decide between:

1. Keeping top-K by relevance, then sorting those top-K items by price?
2. Sorting all matching products by price regardless of relevance?
3. Combining score and business signals?

These three behaviors **differ**. Putting `$sort:{price_vnd:1}` after `$limit:10` only sorts **the 10 items already fetched**, rather than finding the 10 cheapest matches across the catalog.

### 11.5. Stage Ordering

`$search` must be the **first stage of the sub-pipeline containing it** per MongoDB Search rules. Never put `$match`/`$project` before `$search` in the same pipeline expecting Search to run. Nested pipelines inside `$lookup`/`$unionWith` carry version-specific rules; never assume every nested stage combination works everywhere.

## 12. `$searchMeta`: Metadata, Facets, and Counts vs. Hit Lists

### 12.1. Counting Search Results

~~~javascript
db.catalog_advanced_010.aggregate([
  {
    $searchMeta: {
      index: "catalog_lexical",
      text: {
        query: "laptop",
        path: ["title", "description"]
      },
      count: { type: "total" }
    }
  }
]);
~~~

`$searchMeta` returns metadata document(s), **not** a list of product hits like `$search`. When using `lowerBound` instead of `total`, present and interpret it as a **lower-bound estimate**, never “exactly 18,204 results”.

### 12.2. Faceting by Category

~~~javascript
db.catalog_advanced_010.aggregate([
  {
    $searchMeta: {
      index: "catalog_lexical",
      facet: {
        operator: {
          compound: {
            must: [
              { text: {
                  query: "laptop",
                  path: ["title", "description"]
              }}
            ],
            filter: [
              { equals: { path: "tenant_id", value: "t01" } },
              { equals: { path: "active", value: true } }
            ]
          }
        },
        facets: {
          byCategory: {
            type: "string",
            path: "category",
            numBuckets: 10
          }
        }
      }
    }
  }
]);
~~~

Facets have specific semantics and index mapping requirements; verify that `category` is facetable under your feature version rather than assuming every analyzed string can be faceted.

### 12.3. `$$SEARCH_META`

Following a `$search` stage, an aggregation can read `$$SEARCH_META` in permitted downstream stages. Never use it casually after `$lookup`/`$unionWith` where metadata context is no longer valid; check MongoDB Search rules for your version.

### 12.4. Distinguishing Three Ways to Count

| Method | What It Counts |
| --- | --- |
| `db.collection.countDocuments({tenant_id:"t01"})` | Documents matching a DB predicate |
| `$searchMeta.count` | Matches in the Search query/index, as `total` or `lowerBound` |
| `$count` after `$search` and downstream filters | Documents surviving the pipeline stages up to that point |

If you filter after Search or `$limit`, `$count` may differ from `$searchMeta`. Search index lag can also create temporary differences between `countDocuments` and `$searchMeta`.

## 13. Search Scoring, Highlights, and Pagination

### 13.1. Every Score Has Context

~~~text
$text          -> textScore
$search        -> searchScore
$vectorSearch  -> vectorSearchScore
~~~

Search scores are not probabilities that “the user definitely wants this product”. They are ranking signals tied to the operator, index, analyzer, scoring options, and dataset. Scores shift when indexes or engines change and cannot be compared directly across different queries.

### 13.2. Boosting `title` Over `description`

Search DSL example:

~~~javascript
db.catalog_advanced_010.aggregate([
  {
    $search: {
      index: "catalog_lexical",
      compound: {
        should: [
          { text: {
              query: "laptop",
              path: "title",
              score: { boost: { value: 4 } }
          }},
          { text: {
              query: "laptop",
              path: "description"
          }}
        ],
        minimumShouldMatch: 1,
        filter: [
          { equals: { path: "tenant_id", value: "t01" } },
          { equals: { path: "active", value: true } }
        ]
      }
    }
  },
  {
    $project: {
      title: 1,
      score: { $meta: "searchScore" }
    }
  },
  { $limit: 10 }
]);
~~~

`boost` amplifies title matches relative to description matches, but it does not guarantee a title match always ranks first if other scoring signals dominate. Measure relevance quality with a query set and human judgments.

### 13.3. Highlights Are Not Default Metadata on Every Search Query

To get hit snippets/highlights, enable Search `highlight` options and project the corresponding metadata in `$search` (where supported by field/operator). Never assume `$search` automatically highlights matched terms in `title`.

### 13.4. Offset Pagination Has Costs

~~~javascript
[
  { $search: {/* lexical query */} },
  { $skip: 10000 },
  { $limit: 20 }
]
~~~

Large offsets increase resource cost and become unstable when data or the search index changes. MongoDB Search provides token-based `searchAfter`/`searchBefore` pagination on supported versions, though note:

- The token is not a hand-crafted `_id` from the last hit.
- It requires deterministic sorting/ranking per contract.
- Search index mutations can prevent strict snapshot consistency across multi-page requests.
- You must manage token lifecycles, query consistency, and tenant/ACL validation.

**Never treat** cursor pagination as a guarantee of snapshot isolation across Search results.

### 13.5. When Stronger Stability Is Needed

Once a customer picks a product and proceeds to checkout, read the **current state from MongoDB Server** by ID and verify price, active flag, tenant, and stock inside a business transaction rather than treating a Search hit as the transactional source of truth.

## 14. Vector Search: “Semantic Similarity” Is a Separate System

Lexical search matches words and phrases. Vector search finds **nearby numeric representations** in an embedding space. A vector:

~~~javascript
embedding: [0.14, 0.31, 0.07, 0.92]
~~~

does not inherently encode “laptop meaning” unless generated by an appropriate embedding model. MongoDB handles **vector storage, indexing, and nearest-neighbor search**; the embedding generation pipeline, model versioning, and evaluation remain the responsibility of the application or an external embedding service.

### 14.1. Components

~~~mermaid
flowchart LR
    P["Product title + description"] --> EM["Embedding model / pipeline"]
    EM --> V["Vector in MongoDB document"]
    V --> VI["MongoDB Vector Search index"]
    Q["User question"] --> QM["Same embedding model"]
    QM --> VS["$vectorSearch"]
    VI --> VS
    VS --> R["Top-K similar items + score"]
~~~

### 14.2. Critical Parameters

| Parameter | Meaning |
| --- | --- |
| `path` | Indexed embedding field |
| `numDimensions` | Size of each vector; queries must match |
| `similarity` | Proximity metric (`cosine`, `dotProduct`, `euclidean` per index) |
| `queryVector` | Query vector from the same embedding space |
| `limit` | Desired number of results |
| `numCandidates` | Candidate pool size for approximate search in modes that require it |
| `filter` | Pre-filter conditions on fields indexed with `type: "filter"` |
| `exact` | Exact nearest-neighbor mode when supported by server/search version |

**Never** compare lexical Search scores and vector scores as calibrated probabilities on the same scale.

### 14.3. ANN and ENN

**ANN** prioritizes performance by approximating nearest neighbors, trading recall against speed via `numCandidates`/index/data characteristics. **ENN** (exact) evaluates vectors exhaustively for exact nearest neighbors at higher resource cost, subject to version support and limits.

Never blindly set `numCandidates = limit` expecting strong recall. Benchmark on a ground-truth dataset using Recall@K, nDCG@K, p95 latency, and tenant-filtered candidate cardinality.

## 15. Creating a **Vector Search Index**, Not a B-Tree Index

For our 4-dimensional fixture:

~~~javascript
db.catalog_advanced_010.createSearchIndex(
  "catalog_vector",
  "vectorSearch",
  {
    fields: [
      {
        type: "vector",
        path: "embedding",
        numDimensions: 4,
        similarity: "cosine"
      },
      { type: "filter", path: "tenant_id" },
      { type: "filter", path: "active" },
      { type: "filter", path: "category" }
    ]
  }
);
~~~

The three-argument `createSearchIndex(name, type, definition)` syntax requires a supporting `mongosh` and server version. These examples use 4-dimensional vectors to test syntax; production typically uses hundreds or thousands of dimensions depending on the embedding model and must obey server version dimension/format limits.

### 15.1. Why Are Separate `filter` Fields Needed?

A vector index does not automatically allow filtering by arbitrary document fields inside `$vectorSearch.filter`. Pre-filter fields like `tenant_id`, `active`, and `category` must be declared as `type: "filter"` in the vector index with compatible BSON types.

If you omit `tenant_id` from the index and put the tenant filter in a `$match` **after** top-K, the application risks missing valid tenant hits and running ANN over other tenants' data.

### 15.2. Check Status Before Querying

~~~javascript
db.catalog_advanced_010.aggregate([
  { $listSearchIndexes: { name: "catalog_vector" } }
]);
~~~

Only send business queries once the index is ready and the deployment supports the stage. `createSearchIndex()` returning does not mean all vectors are immediately indexed.

## 16. Querying `$vectorSearch` with Proper Filtering

~~~javascript
db.catalog_advanced_010.aggregate([
  {
    $vectorSearch: {
      index: "catalog_vector",
      path: "embedding",
      queryVector: [0.15, 0.32, 0.06, 0.90],
      numCandidates: 100,
      limit: 5,
      filter: {
        tenant_id: "t01",
        active: true
      }
    }
  },
  {
    $project: {
      _id: 1,
      title: 1,
      category: 1,
      score: { $meta: "vectorSearchScore" }
    }
  }
]);
~~~

**Read the semantics carefully:**

- `$vectorSearch` targets the `catalog_vector` Vector Search index.
- `queryVector` here is a **dummy vector** and proves nothing about semantic correctness.
- `numCandidates`/`limit` control candidate evaluation and result cap.
- `filter` sits **inside the stage** before top-K selection, using indexed filter fields.
- `$meta: "vectorSearchScore"` retrieves the vector score, not `searchScore` or `textScore`.

### 16.1. Stage Restrictions

`$vectorSearch` carries different placement and composition rules from ordinary aggregation stages; per current MongoDB docs, it cannot be placed inside `$facet` or `$lookup`. Certain compositions like `$unionWith` are supported in specific server versions (documented for MongoDB 8.0+)—verify on your exact target environment.

Never assume “any aggregation stage can nest inside any other stage” merely because Spring Data provides an `AggregationOperation` API.

### 16.2. Difference Between Vector Scores and Lexical Scores

~~~javascript
{ $meta: "textScore" }         // database $text
{ $meta: "searchScore" }       // Search $search
{ $meta: "vectorSearchScore" } // Vector Search $vectorSearch
~~~

When combining results, use an appropriate normalization or rank-fusion method rather than adding the three numbers directly. A query vector being “close” in embedding space does not mean the document satisfies exact business predicates if pre-filters are missing.

### 16.3. Do Not Use Vector Search for Every Problem

Looking up `sku="LT-A100"` via cosine similarity wastes embedding calls and can return a “similar-looking” product that is **not the requested SKU**. Exact IDs, ACLs, tenants, inventory, and transactional predicates belong in database business queries. Vector Search handles semantic retrieval and ranking, not source-of-truth validation.

## 17. Hybrid Search: Combining Lexical and Semantic Signals with a Ranking Strategy

A user typing “laptop mỏng nhẹ cho văn phòng” (lightweight office laptop) may want both **exact keyword matches** and **semantically similar products**.

~~~text
User query
   |
   +-- lexical $search  -> ranked list A
   |
   +-- embed(query) -> $vectorSearch -> ranked list B
                                  |
                         Fusion / reranking
                                  |
                            top-K results
~~~

| Method | Idea | Requirements |
| --- | --- | --- |
| Reciprocal Rank Fusion (RRF) | Uses rank positions instead of raw scores | Two ranked lists share comparable document IDs |
| Weighted score fusion | Normalizes scores before combining | Proper calibration and evaluation on data |
| Native search fusion stage | Uses MongoDB stages in supported versions | Verify Search/DB version and stage limits |
| Application-side fusion | Runs two queries and merges in Java | Extra latency and consistency trade-offs |

**Never** directly add `searchScore + vectorSearchScore` and call it “90% relevant”. Their scales, models, indexes, operators, and scoring algorithms differ.

### 17.1. Deployment/Version Notes

Newer MongoDB versions offer dedicated fusion stages or composition via `$unionWith` under specific rules. Some hybrid capabilities arrived after older Java Driver/Spring Data releases. Never hard-code a single fusion syntax across all MongoDB versions; consult docs for your **exact production version** and run integration tests before enabling.

### 17.2. Candidate Filtering Before Fusion

Each retrieval branch must filter **tenant, active, visibility, and ACLs** when gathering candidates. If the vector branch takes the cluster-wide top 10 before filtering `tenant_id = "t01"`, valid `t01` products at rank 11+ get dropped and fusion can never recover items that were never retrieved.

### 17.3. Evaluating Quality

Using 100 labeled representative queries:

- Recall@K: how many relevant results were retrieved?
- nDCG@K / MRR: is the ranking order helpful?
- P95 latency: are responses fast enough?
- No-result rate: do zero-match queries have clean handling/fallbacks?
- Tenant leakage: did any cross-tenant document leak?
- Freshness: how quickly do recent data changes become searchable?

Never pick fusion weights just because a single demo search “looked nice”.

## 18. Spring Data `MongoTemplate.aggregate` Can Send Raw Search Stages

Spring Data MongoDB provides `AggregationOperation` to assemble aggregation pipelines. When a Search DSL feature lacks a type-safe builder in your Spring Data version, construct BSON using `org.bson.Document`.

### 18.1. Lexical Search Service with Tenant Filter

~~~java
// CatalogSearchService.java
package com.example.advancedsearch;

import java.util.List;
import org.bson.Document;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.aggregation.Aggregation;
import org.springframework.data.mongodb.core.aggregation.AggregationOperation;
import org.springframework.stereotype.Service;

@Service
public class CatalogSearchService {
    private final MongoTemplate mongo;

    public CatalogSearchService(MongoTemplate mongo) {
        this.mongo = mongo;
    }

    public List<Document> lexicalSearch(
            String trustedTenantId, String keyword, int limit) {
        if (trustedTenantId == null || trustedTenantId.isBlank()
                || keyword == null || keyword.isBlank()) {
            throw new IllegalArgumentException(
                "Tenant and keyword are required");
        }

        int safeLimit = Math.max(1, Math.min(limit, 20));
        Document text = new Document("text",
            new Document("query", keyword)
                .append("path", List.of("title", "description")));

        Document tenant = new Document("equals",
            new Document("path", "tenant_id")
                .append("value", trustedTenantId));
        Document active = new Document("equals",
            new Document("path", "active")
                .append("value", true));

        Document searchSpec = new Document(
            "index", "catalog_lexical")
            .append("compound", new Document("must", List.of(text))
                .append("filter", List.of(tenant, active)));

        AggregationOperation search =
            context -> new Document("$search", searchSpec);

        AggregationOperation project =
            context -> new Document("$project",
                new Document("title", 1)
                    .append("sku", 1)
                    .append("price_vnd", 1)
                    .append("score",
                        new Document("$meta", "searchScore")));

        Aggregation pipeline = Aggregation.newAggregation(
            search, project, Aggregation.limit(safeLimit)
        );

        return mongo.aggregate(
            pipeline, "catalog_advanced_010", Document.class
        ).getMappedResults();
    }
}
~~~

**This example is relatively portable** because:

- `keyword` is a **BSON value**, never concatenated into JSON syntax.
- `trustedTenantId` is passed by a trusted caller, though the controller must derive it from the **authenticated principal**, not an arbitrary request body field.
- Search field paths are server constants defined in the Search index.
- The Search stage sits **first** in the pipeline.
- Results are capped at 20 to avoid large payloads.

However, compiling Java code **does not guarantee** the server supports `$search`. On standalone MongoDB without the Search service and index, `aggregate` will fail at runtime.

### 18.2. Warning on `@Field` Mapping with Raw `Document`

In the entity:

~~~java
@Field("tenant_id")
private String tenantId;
~~~

Yet the custom `AggregationOperation` above constructs a raw BSON `Document`. Therefore:

~~~text
Java property: tenantId
Raw BSON path: tenant_id
~~~

Never write `"tenantId"` inside `$search.compound.filter.path` just because Java APIs use that property name, unless your mapping/index literally uses that name. By contrast, Spring Data's type-aware builders can map property paths via the entity mapping context.

### 18.3. Spring Data Does Not Automatically Fix Stage Order

Wrong:

~~~java
Aggregation wrong = Aggregation.newAggregation(
    Aggregation.match(
        org.springframework.data.mongodb.core.query.Criteria
            .where("tenantId").is("t01")),
    search
);
~~~

`$search` must be the first stage of its pipeline. Put tenant filters in `compound.filter` inside the Search stage. Inserting `$match` ahead of Search does not become valid merely because Java DSL compiles it.

### 18.4. Never Return Raw BSON Straight to Clients

The projection above intentionally selects only `title`, `sku`, `price_vnd`, and `score`. In real APIs, map to dedicated DTOs; never return full MongoDB Documents containing `embedding`, private metadata, or unauthorized fields.

## 19. Spring Data Type-Safe `VectorSearchOperation` and `SearchIndexOperations`

Spring Data MongoDB releases supporting Vector Search provide `VectorSearchOperation`, `VectorIndex`, and `SearchIndexOperations`. These are **client-side abstractions** that still require the Search service and real Vector indexes on the server.

### 19.1. Creating a Vector Index via Spring Data

~~~java
import org.springframework.data.mongodb.core.index.VectorIndex;
import static org.springframework.data.mongodb.core.index.VectorIndex.SimilarityFunction.COSINE;

VectorIndex definition = new VectorIndex("catalog_vector")
    .addVector("embedding",
        v -> v.dimensions(4).similarity(COSINE))
    .addFilter("tenantId")
    .addFilter("active");

String name = mongoTemplate
    .searchIndexOps(CatalogProduct.class)
    .createIndex(definition);
~~~

When calling `searchIndexOps(CatalogProduct.class)`, the entity mapping context maps `tenantId` to BSON `tenant_id` in the index definition. This differs from raw `mongosh` `createSearchIndex(...)` in section 15.

### 19.2. Checking Search Index Readiness

~~~java
var ops = mongoTemplate.searchIndexOps(CatalogProduct.class);
boolean exists = ops.exists("catalog_vector");
var status = ops.status("catalog_vector");
~~~

`exists==true` does not guarantee the index is **READY**; inspect the actual status, enforce a deadline, and define degraded behavior if the index is building or rebuilding. Never create or drop Search indexes per HTTP request.

### 19.3. Querying with `VectorSearchOperation`

~~~java
import static org.springframework.data.mongodb.core.aggregation.Aggregation.newAggregation;
import org.springframework.data.mongodb.core.aggregation.VectorSearchOperation;
import org.bson.Document;

// queryVector: vector matching the API type supported by your Spring Data version.
VectorSearchOperation vectorStage = VectorSearchOperation
    .search("catalog_vector")
    .path("embedding")
    .vector(queryVector)
    .numCandidates(100)
    .limit(5)
    .filter(new Document("tenant_id", trustedTenantId)
        .append("active", true))
    .withSearchScore("score");

var results = mongoTemplate.aggregate(
    newAggregation(CatalogProduct.class, vectorStage),
    Document.class
).getMappedResults();
~~~

Here `queryVector` is a pre-computed variable of the type accepted by your **actual dependency Javadoc** (some versions accept `Vector`, arrays, or collections). Treat this snippet as an **API blueprint**, not something to copy without defining variables or aligning versions. `VectorSearchOperation` builds `$vectorSearch`—it **does not generate embeddings**, resolve the caller's tenant, or replace dimension checks.

### 19.4. Why New Java Classes Are Not Enough

~~~text
Spring Data has VectorSearchOperation
                 |
                 v
Driver sends BSON $vectorSearch
                 |
                 v
MongoDB Server / Search service DOES NOT support it
                 |
                 v
Operation fails at runtime
~~~

Passing Java compilation and mocked repository unit tests **does not prove** Search features work in a real environment.

### 19.5. Version Note

Spring Data `VectorIndex`/`VectorSearchOperation` overloads can vary across 4.5, 5.0, 5.1, and newer releases. Consult the Javadoc for your **exact release** regarding imports, `.vector(...)`, search scores, index status, and repository support; if you need newer MongoDB syntax not yet wrapped by a builder, use raw `AggregationOperation` with BSON and test on the target deployment.

## 20. Repository `@Aggregation` and `@VectorSearch` Are Two Different Approaches

### 20.1. `@Aggregation` with Search DSL

~~~java
import java.util.List;
import org.springframework.data.mongodb.repository.Aggregation;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface CatalogSearchRepository
        extends MongoRepository<CatalogProduct, String> {

    @Aggregation(pipeline = {
      "{ '$search': { 'index': 'catalog_lexical', " +
      "  'compound': { " +
      "    'must': [ { 'text': { " +
      "      'query': ?1, 'path': 'title' " +
      "    }} ], " +
      "    'filter': [ " +
      "      { 'equals': { 'path': 'tenant_id', 'value': ?0 } }, " +
      "      { 'equals': { 'path': 'active', 'value': true } } " +
      "    ] " +
      "  } " +
      "} }",
      "{ '$limit': 10 }"
    })
    List<CatalogProduct> searchTitleByTenant(
        String trustedTenantId,
        String keyword
    );
}
~~~

`@Aggregation` declares BSON aggregation stages; `?0`/`?1` bind method parameters per query annotation rules. It still requires the `catalog_lexical` Search index and a Search-capable server. For large DSL pipelines, `MongoTemplate` or a custom repository implementation is usually easier to review and test than long annotation strings.

### 20.2. Standard Repository Query Derivation Produces Database Queries

~~~java
List<CatalogProduct> findByTitleContaining(String term);
~~~

This derived query method builds a query using **MongoDB repository query derivation** (which uses regex depending on keyword semantics); it **does not automatically invoke `mongot`** or `$search` just because the method name starts with `find`.

### 20.3. Repository `@VectorSearch` by Spring Data Version

Newer Spring Data MongoDB versions introduce `@VectorSearch` and `SearchResults<T>`/`Vector`. Per official documentation, a typical example looks like:

~~~java
import org.springframework.data.mongodb.repository.VectorSearch;
import org.springframework.data.domain.Vector;
import org.springframework.data.domain.Score;
import org.springframework.data.domain.SearchResults;

public interface SimilarityRepository
        extends org.springframework.data.repository.Repository<CatalogProduct, String> {

    @VectorSearch(
        indexName = "catalog_vector",
        numCandidates = "200"
    )
    SearchResults<CatalogProduct> searchTop10ByEmbeddingNear(
        Vector vector,
        Score score
    );
}
~~~

**Verify API by version:** check package names `Vector`/`Score` and method signatures against your project's Spring Data release. Repository vector queries require the exact index name, matching vector dimensionality, and valid score/limit parameters; this simple example lacks a tenant filter and is **unsafe for direct use on multi-tenant endpoints**.

In production, use `@VectorSearch(filter=...)` or derived pre-filters in supported versions; always verify the generated BSON in tests to prove the tenant filter lives inside `$vectorSearch.filter` rather than post-filtering after top-K.

### 20.4. Distinguishing the Spring APIs

| Spring Data API | Expected MongoDB Command/Stage | Requires Search Service? |
| --- | --- | --- |
| `MongoRepository.findBy...` | `find`/query predicates | No for regular filters |
| `TextQuery`/`TextCriteria` | `$text` | No; needs database text index |
| `MongoTemplate.aggregate` with `$search` | `aggregate: [$search,...]` | **Yes** |
| `MongoTemplate.aggregate` with `$vectorSearch` | `aggregate: [$vectorSearch,...]` | **Yes** |
| `VectorSearchOperation` | Builder for `$vectorSearch` | **Yes** |
| `SearchIndexOperations` | Search index management commands | **Yes** to succeed |
| `@Aggregation` with `$search` | Annotation's BSON aggregation | **Yes** |
| `@VectorSearch` | Vector-search repository pipeline | **Yes** |

## 21. Reactive Search Uses the Same Server Capabilities, Different Execution Model

Reactive Spring Data offers `ReactiveMongoTemplate`, reactive repositories, and Reactor `Mono`/`Flux`. They provide non-blocking I/O, **without adding a Search service** or creating Search indexes.

### 21.1. Sending a Search Pipeline via the Reactive API

~~~java
// Inside a reactive service with injected ReactiveMongoTemplate.
import org.bson.Document;
import org.springframework.data.mongodb.core.ReactiveMongoTemplate;
import org.springframework.data.mongodb.core.aggregation.Aggregation;
import reactor.core.publisher.Flux;

public Flux<Document> searchReactive(
        Aggregation tenantScopedPipeline) {
    return reactiveMongoTemplate.aggregate(
        tenantScopedPipeline,
        "catalog_advanced_010",
        Document.class
    );
}
~~~

`tenantScopedPipeline` must include the Search/Vector tenant filter and `limit` as shown earlier. The Reactive MongoDB Driver sends the exact same BSON stage to MongoDB; if the Search index is missing, the reactive publisher emits an error upon execution.

### 21.2. Publishers Are Typically Lazy

~~~java
Flux<Document> hits = reactiveMongoTemplate.aggregate(
    pipeline, "catalog_advanced_010", Document.class
);
// Command is not sent to the server until subscribed.
~~~

In WebFlux, return the Publisher to the controller so the framework subscribes. Never call `subscribe()` inside a service and return `Flux.empty()`—that detaches errors, deadlines, context, and results from the caller.

### 21.3. `block()` Does Not Turn Search into a Synchronous Transaction

~~~java
// Avoid on the WebFlux event loop:
// hits.collectList().block();
~~~

Blocking risks thread starvation; nor does it create indexes or make Search results “fresher”. Use bounded `flatMap`/`collectList` if an endpoint needs `Mono<List<DTO>>`; if streaming results, test client disconnect handling.

### 21.4. Cancellation and Timeouts

An HTTP client may disconnect mid-search. `Flux.timeout` or cancellation manages client/driver lifecycles, **without guaranteeing the server Search engine instantly frees all resources**. Enforce deadlines, max query lengths, result caps, and rate limits, and monitor Search query latency and queues.

### 21.5. Streaming Results Does Not Alter Index Consistency

Search indexes update asynchronously from the database. Streaming hits reactively does not create a read-after-write snapshot like a MongoDB transaction. When latest price or stock is needed at checkout, re-read the current document via a database query and verify versions/business invariants.

## 22. Security Design: Tenant, ACLs, and Injection

### 22.1. Enforcing Authenticated Tenant in Both Query and Search Engine

~~~text
Authenticated principal -> tenantId t01
                             |
             Build Search DSL with tenant filter
                             |
                   $search / $vectorSearch
                             |
                 topK for tenant t01
                             |
              Project whitelisted fields
~~~

Never trust a `tenantId` passed in a request body. Never search cluster-wide and filter `tenant_id` only after `$limit`, as that corrupts top-K and wastes work on unauthorized data. For user/role ACLs, push Search-supported predicates into pre-filters and re-verify permissions at the DB business boundary when required.

### 22.2. Search Score Is Not a Permission Check

A high score does not mean a user has permission to view a document. `$search.compound.filter` or `$vectorSearch.filter` must constrain the candidate set. Moreover, because Search indexes can lag behind `active`/`visibility` updates, applications requiring instant permission revocation must **revalidate permissions/current state before returning sensitive data**.

### 22.3. Never Interpolate User Input into Raw JSON DSL

Wrong:

~~~java
// DO NOT DO THIS:
// String json = "{'$search': {'text': {'query': '"
//     + userInput + "', 'path': '" + userPath + "'}}}";
~~~

Special characters can break parsing; user-controlled index, path, or operator names can widen query scope beyond intent.

Right in principle:

~~~java
Document text = new Document("query", userKeyword)
    .append("path", "title");

Document stage = new Document("$search",
    new Document("index", "catalog_lexical")
        .append("text", text));
~~~

`userKeyword` is bound as a **BSON value**; `index` and `path` come from constants or an allowlist. Still, query strings retain Search operator semantics; if an API expects plain literal terms, validate, escape, or define a syntax policy. Never mistake parameter binding for authorization.

### 22.4. Resource Exhaustion and Expensive Queries

Cap query length, clause/path counts, `limit`, `numCandidates`, vector dimensions, fuzzy/wildcard complexity, concurrent requests, and pagination depth. Monitor timeouts and Search CPU/memory/queueing, and enforce per-tenant quotas. Never let untrusted clients pick `numCandidates=1000000` or submit raw Search DSLs.

### 22.5. Embeddings Still Require Privacy Controls

Although embeddings are numeric arrays, they can leak properties or context of the source text depending on your threat model. Never treat vectors as “non-identifiable” data. Apply access control, retention/deletion policies, tenant isolation, logging limits, and vendor reviews for embedding providers.

## 23. Data Freshness: Search Is Not Read-Your-Writes

~~~text
t0: insert product p010-05 into MongoDB.
t1: MongoDB acknowledges write.
t2: findById("p010-05") sees document.
t3: $search query might NOT see p010-05 yet.
t4: Search index finishes syncing.
t5: $search begins returning p010-05.
~~~

**Never** assume MongoDB Search/Vector Search provides transactional read-after-write parity with primary DB queries at all times.

### 23.1. Index Update Differences

| Mechanism | Freshness to Understand |
| --- | --- |
| Database B-tree / `find` after acknowledged write | DB query honors configured read concern / read preference |
| Database `$text` | Backed by text index updated inside the database engine |
| MongoDB Search/Vector Search | Search index syncs from data; exhibits indexing lag |
| Newly created/rebuilt Search index | Undergoes build/`READY` lifecycle and initial sync lag |
| New document lacking generated embedding | Vector Search cannot match an embedding that doesn't exist yet |

### 23.2. “Deleted Yet Still Appearing in Search”

A Search index may lag behind deletions or visibility changes. Therefore, Search results **must not act as the final permission source of truth** for sensitive documents. Re-validate against canonical DB/security state when serving or mutating protected objects.

### 23.3. Separating Search from Transactions

~~~text
Search retrieval -> user selects product ID
    -> re-verify current document/tenant/price/stock
    -> run guarded write / business transaction
~~~

`$search` excels at **discovery and suggestions**; it never replaces guarded `findOneAndUpdate` stock reservations or unique constraints.

### 23.4. When “Created Items Must Be Found Immediately” Is Mandatory

Options:

1. Return the created product ID/details directly from the creation API without waiting on Search.
2. Provide an optimistic UI view or pin recent items by ID.
3. Read recent records from the primary DB by ID.
4. Design a bounded wait-for-index mechanism with a strict deadline if the Search subsystem exposes reliable status checks—never poll infinitely.

Never promise zero indexing lag unless your deployment explicitly guarantees it.

## 24. Investigating Performance in the Right Engine

### 24.1. Database `find`/`$text`

~~~javascript
db.catalog_advanced_010.find({
  tenant_id: "t01",
  category: "laptop",
  active: true
}).explain("executionStats");
~~~

Inspect `winningPlan`, `totalKeysExamined`, `totalDocsExamined`, `nReturned`, index selectivity, sort/limit, and query shape. Database `explain` does not fully describe Lucene Search internals; never use a `COLLSCAN` from a different query to claim `$search` is broken.

### 24.2. Search Metrics

Track:

- Search index health, build/`READY` status, and indexing lag.
- Search query latency (p50/p95/p99), timeout rate, and failure rate.
- Search node CPU/memory, queue depth, and concurrent load.
- Candidate counts, facets/highlights cost, and query complexity.
- Returned result counts vs. limit/filter, and zero-result rate.
- Index version, analyzer version, and relevance scores after rollouts.

### 24.3. Vector-Specific Metrics

Additionally track dimensions, index size, `numCandidates`, top-K, recall@K, tenant/category filter selectivity, embedding generation latency, model error rate, and ANN resource trade-offs. Never measure only MongoDB query latency while ignoring time spent generating query vectors locally or calling external embedding APIs.

### 24.4. Benchmarking by Mode

~~~text
mode: EXACT / TEXT_BASIC / LEXICAL / SEMANTIC / HYBRID
serverVersion:
springDataVersion:
indexDefinitionVersion:
datasetSize:
tenantCardinality:
queryP95Ms:
throughput:
recallAt10:
timeoutRate:
indexLagP95Ms:
~~~

Benchmark data must represent production size, title length, tenant distribution, index definitions, and Search node sizing. Never change model, index, and query simultaneously and attribute gains to a single factor.

### 24.5. Limits on Search Nodes

Raising `numCandidates` or fuzzy complexity does not yield unbounded relevance gains. Too many candidates spike CPU and latency while lowering Search node concurrency. When p99 climbs and queues back up, analyze capacity, indexes, and query shapes before blindly increasing the Java connection pool.

## 25. Testing That Distinguishes MongoDB Server from the Search Service

### 25.1. At Least Two Test Environment Types

| Environment | What to Test |
| --- | --- |
| Standard local/CI MongoDB | CRUD, exact/range, `$regex`, `$text`, typed Spring mapping |
| MongoDB deployment with Search/`mongot` | `$search`, `$searchMeta`, `$vectorSearch`, index readiness/score/filters |
| MongoDB replica set with transactions | Business consistency and guarded updates |
| Production-like Search | Index freshness, latency, resource load, fallback/recovery |

Never cite “CI MongoDB Docker started” as proof all Search stages work. For local Search, use an Atlas test environment or MongoDB's `mongodb-atlas-local` development image—remembering a single-node dev image is not production HA.

### 25.2. Database-Only Integration Test

~~~java
// Snippet in a test with injected MongoTemplate + AssertJ
@Test
void exactLookupUsesDatabaseQuery() {
    Query q = Query.query(
        Criteria.where("tenantId").is("t01")
            .and("sku").is("LT-A100")
    );

    CatalogProduct result =
        mongoTemplate.findOne(q, CatalogProduct.class);

    assertThat(result).isNotNull();
    assertThat(result.getTenantId()).isEqualTo("t01");
    assertThat(result.getSku()).isEqualTo("LT-A100");
}
~~~

This test only requires database indexes and fixtures; it proves nothing about Search indexes or scoring.

### 25.3. Search Integration Test Checklist

1. Provision a Search-capable test deployment.
2. Seed fixtures with at least two tenants having very similar titles/embeddings.
3. Apply Search/Vector index definitions.
4. Wait for index `READY` with a bounded deadline.
5. Wait/verify fixture ingestion so assertions do not run too early due to async indexing.
6. Run bounded `$search`/`$vectorSearch` with tenant filtering inside the stage.
7. Assert **zero cross-tenant documents** and proper response fields.
8. Verify score fields/metadata if the API surfaces scores.
9. Clean up only records and indexes owned by the test; never drop shared data.

### 25.4. Testing Capabilities and Fallbacks

~~~text
GET /catalog/search?mode=lexical
  -> FEATURE_UNAVAILABLE / SERVICE_UNAVAILABLE when Search is absent.

GET /catalog/search?mode=exact
  -> Continues working via database query.
~~~

If a product intentionally falls back from lexical to basic text, the response and UX must disclose the actual mode used rather than pretending quality and semantics are identical.

### 25.5. Testing Field Mappings

With `CatalogProduct.tenantId` annotated `@Field("tenant_id")`:

- `Criteria.where("tenantId")` on a typed `Query` maps to `tenant_id`.
- Raw `$search.compound.filter.path` must be `tenant_id`.
- Vector index fields created in `mongosh` must use `tenant_id`.
- Java `VectorIndex.addFilter("tenantId")` can map when tied to the entity context.

Test with at least two tenants to catch missing conditions or wrong field names. A fixture with only tenant `t01` cannot detect an accidentally dropped tenant filter.

### 25.6. Testing Relevance with Golden Queries

An integration test asserting `result.size() > 0` does not prove Search is useful. Maintain a labeled dataset and queries:

~~~text
query="laptop văn phòng" -> expected relevant IDs/ranking band
query="laptpo"           -> expected fuzzy matches (if enabled)
query="máy tính đồ họa"  -> expected semantic matches
query="LT-A100"          -> expected exact SKU lookup
~~~

Run regressions whenever changing analyzers, index schemas, boosts, or embedding models. Measure recall/ranking plus latency, not just compilation.

## 26. Common Errors: Pinpointing the Fault to the Right Layer

| Symptom | Possible Cause | Check |
| --- | --- | --- |
| `findById` works, `$search` throws unknown stage | Deployment lacks Search stage/`mongot`/version | MongoDB compatibility + Search setup |
| `$search` reports index not found | Wrong name/collection, index not created | `$listSearchIndexes` |
| Search index created, yet query misses records | Index not `READY` or ingestion lag | Status, readiness, lag metrics |
| `$text` works, `$search` fails | Database text index is not a Search index | Create a proper Search index |
| `$search` works, `$text` fails | Missing database text index | `createIndex({field:"text"})` |
| `$vectorSearch` dimension error | Query vector mismatches index model/dimension | Check model, dimensions, format |
| Vector scores low or nonsensical results | Embedding model mismatch or dummy vectors | Verify embedding pipeline, evaluate recall |
| Search returns empty despite clear keyword match | Wrong analyzer, mapping, path, index, or tenant filter | List index definition, test filters individually |
| Tenant `equals` fails to match | Wrong `tenant_id` index type or Java field name used | Token/filter mapping + BSON paths |
| Other tenant's results appear | Missing or late tenant filter | Filter inside `$search`/`$vectorSearch` |
| Top-K missing valid items | `$limit` placed before tenant post-filter | Filter before candidate ranking |
| `$text` score differs from `$search` score | Different engines and `$meta` names | `textScore` vs. `searchScore` |
| `$searchMeta` returns no products | Metadata stage is not a hits stage | Use `$search` to retrieve documents |
| Facet lacks category buckets | Wrong facet field type/mapping | Check Search facet mapping |
| `$vectorSearch` inside `$lookup` errors | Stage composition restriction | Use supported pipeline/topology |
| Spring Data class compiles, runtime fails | Client API newer than deployment capability | Capability matrix + feature tests |
| Older Spring Data lacks `VectorIndex` | API absent in that dependency version | Align versions or use raw BSON |
| `TextQuery` does not enable autocomplete | `TextQuery` is `$text` | Use Search autocomplete index/operator |
| `@Aggregation` returns empty while `mongosh` gets hits | Field name mapping or annotation binding | Inspect generated BSON + tenant |
| Deleted document still appears in Search | Search index lag | Revalidate current state/ACL |
| Index memory/CPU climbs rapidly | Dynamic mapping, vector cardinality, index churn | Audit index capacity and definitions |
| Fuzzy queries run slowly | Query complexity and candidate explosion | Input limits, fuzzy bounds, profiling |
| Local tests pass, prod lacks feature | Topology/version/index/service mismatch | Integration tests on real deployment |
| HTTP 200 `[]` during Search outage | Catch-all swallows unavailable error | Error classification / degraded response |

### 26.1. Recommended Diagnostic Flow

~~~text
Search query error
  |
  +-- Stage unrecognized?
  |      -> Server version, deployment, or Search service.
  |
  +-- Stage valid, but index not found?
  |      -> Collection, index name/type/`READY` status.
  |
  +-- Query runs, yet no matches?
  |      -> Index mappings, analyzer, BSON fields, filters.
  |
  +-- Matches wrong tenant?
  |      -> Security/tenant filter placement and mapping.
  |
  +-- Accurate results, but slow?
         -> Index size, candidate limits, search nodes, network,
            embedding latency, query shape, and p95/p99.
~~~

Never write `catch(Exception) { return Collections.emptyList(); }` to “stabilize the API”; it turns Search outages into zero-match responses and masks recovery needs.

## 27. Search Feature Deployment Checklist

1. Confirm **requirements**: exact filter, `$text`, lexical, autocomplete, semantic, or hybrid?
2. Confirm **MongoDB Server version, edition, and topology**.
3. Confirm **`mongot`/Search service** is deployed and healthy on target environments.
4. Confirm **Spring Data/Java Driver versions** include the APIs used.
5. Design database indexes for exact and range queries.
6. Design a separate text index if using `$text`; do not confuse with a Search index.
7. Create Search/Vector indexes with exact names, types, and versioned rollouts.
8. Wait for Search index `READY` with deadlines and explicit health checks.
9. Place tenant/ACL filters **inside the search/vector stage**, before top-K.
10. Never let raw user input select index names, paths, or operators.
11. Validate query length, clauses, candidate counts, and result limits.
12. Define analyzer, synonym, fuzzy, and autocomplete behavior for user languages.
13. For vectors, use identical embedding models and dimensions across documents and queries.
14. Place `$search`/`$searchMeta`/`$vectorSearch` in valid aggregation pipeline positions.
15. Read the right `textScore`/`searchScore`/`vectorSearchScore` without adding them directly.
16. Define pagination and sorting without assuming snapshot stability.
17. Enforce projection/DTO allowlists; never expose embeddings or private metadata.
18. Never use Search results as permission checks or stock/price sources of truth.
19. Account for Search indexing lag in UI and API contracts.
20. Track latency, recall, zero-match rate, and index readiness via metrics.
21. Test capabilities on a **Search-enabled environment**, not only local `mongod`.
22. Test two tenants, wrong index names, field mappings, and vector dimension mismatches.
23. Manage degraded/fallback behavior explicitly.
24. Prepare a rollback plan for index definition, analyzer, or model changes.

## 28. Practice Exercises with Answers

### Exercise 1 — Three Layers of a Search Request

A Spring Data MongoDB repository method returns `List<CatalogProduct>`. Can you infer from its return type that it uses Atlas/MongoDB Search?

**Answer:** No. Inspect the actual BSON query/stage: derived repository `find` methods usually emit database queries, whereas `$search`/`$vectorSearch` only appear when explicitly constructed. The Search service/index and Spring client API are separate layers.

### Exercise 2 — SKU Lookup

A user types exact `LT-A100`, needing the single matching SKU in tenant `t01`. Choose `$vectorSearch` or database `find`?

**Answer:** Database `find` with `{tenant_id:"t01", sku:"LT-A100"}` and unique/compound index `{tenant_id:1, sku:1}`. Vector Search can return semantically close items that are **the wrong SKU** and cannot replace unique constraints.

### Exercise 3 — Finding All Laptops by Price

Requirement: `category=laptop`, `active=true`, price 10–30 million; do you need to create a Search index?

**Answer:** Not by default. MongoDB Server queries plus a suitable compound index handle equality and range filters well. Only pick Search if lexical/fuzzy/relevance or Search-specific faceting is added.

### Exercise 4 — Prefix Regex

Which regex finds SKUs starting with `LT-`?

**Answer:**

~~~javascript
db.catalog_advanced_010.find({
  tenant_id: "t01",
  sku: { $regex: "^LT-" }
});
~~~

For user-supplied input, escape regex metacharacters and cap length to prevent arbitrary regexes. Anchored prefixes can use indexes much better than unanchored regexes, though you should always verify with `explain`.

### Exercise 5 — Which Index Does `$text` Use?

Does `db.collection.createIndex({title:"text"})` create `catalog_lexical` for `$search`?

**Answer:** No. It creates a MongoDB **database text index** for `$text`; Search indexes are created via `createSearchIndex` on deployments running the Search service.

### Exercise 6 — Relevance Scores

Which `$meta` name does `$text` use to return scores? What about `$search`?

**Answer:** `"textScore"` for `$text` and `"searchScore"` for `$search`. Vector Search uses `"vectorSearchScore"`. Never mix or sum raw scores directly.

### Exercise 7 — Spring `TextQuery`

Does `TextQuery.queryText(...)` execute `$search` and support Search DSL highlights?

**Answer:** No. `TextQuery`/`TextCriteria` are Spring Data APIs for **MongoDB `$text`**. Search highlights require the Search service/index and the `$search` DSL.

### Exercise 8 — Self-Managed Versions

Is it true that `$search` and `$vectorSearch` are always available only on MongoDB Atlas?

**Answer:** No longer strictly true. Current MongoDB docs describe supported self-managed MongoDB Community 8.2+ and Enterprise 8.2+ paths using a **separate `mongot`** with edition and operator requirements. A standard standalone Community 8.0 server **does not** gain Search merely by using a newer Spring Data version.

### Exercise 9 — Java API Present, Server Missing Feature

A developer uses Spring Data's `VectorSearchOperation`, and unit tests compile. Production runs standalone `mongod` without `mongot`. What happens?

**Answer:** Queries fail at runtime when executing `$vectorSearch` because the server/deployment lacks support. Java builders do not install the Search service, create vector indexes, or bypass MongoDB version gates.

### Exercise 10 — `$search` Ordering

Can `$match:{tenant_id:"t01"}` be placed before `$search` in the same aggregation pipeline?

**Answer:** No, `$search` must be the first stage of its pipeline. Put tenant filters inside `$search.compound.filter` with compatible index field types before ranking and limits.

### Exercise 11 — Post-Filtering After Top-K

A Search pipeline takes the global top 5 across the cluster, then `$match` filters tenant `t01`. If `t01` has 100 matching products, all ranked outside the global top 5, how many does the API return?

**Answer:** It can return **0**—missing results even though the tenant has many matches. Tenant pre-filters belong inside the search stage, not after top-K.

### Exercise 12 — Index String Type

A Search index maps `tenant_id` as analyzed `string`, while the query uses `equals` for exact token matching. Will this work reliably by default?

**Answer:** No. `equals` requires a field type supporting exact matching (such as `token`); verify Search index definition and operator compatibility.

### Exercise 13 — Search Index `READY`

`createSearchIndex()` succeeds and `exists("catalog_lexical")==true`. Can we declare the index ready for queries immediately?

**Answer:** No. Indexes have a build/sync lifecycle; check statuses via `$listSearchIndexes` or Spring Data `SearchIndexOperations.status(...)` and wait for `READY` with a deadline.

### Exercise 14 — `$searchMeta`

To retrieve category buckets and search hit counts, do you use `$searchMeta` or `$text`?

**Answer:** `$searchMeta` with Search facets/counts when supported by the Search index and service. `$searchMeta` returns **metadata**, not document hits. Note that `count.lowerBound` is not an exact total.

### Exercise 15 — Facets When a Field Is Unindexed

Search faceting by `category` returns wrong or empty results. Is Spring Data DTO projection automatically to blame?

**Answer:** Not necessarily. Check Search index field mappings/facet-compatible types, index readiness, operator paths, and Search DSL first. Java DTO mapping comes afterward.

### Exercise 16 — Embedding Dimension Mismatch

A Vector index declares `numDimensions=4`, while a query vector has 1536 elements. Does the server truncate the vector automatically?

**Answer:** Do not expect it to. Queries must match dimensions, format, and embedding space; mismatches error or fail validation. Validate model versions and vector lengths before querying.

### Exercise 17 — Vector Pre-Filtering

A Vector index indexes only `embedding`, omitting `tenant_id` as a filter field. The app retrieves global top 10 and filters tenants afterward. What is the issue?

**Answer:** Wrong candidate set, potentially dropping valid tenant products and processing unauthorized tenants' data. Add `tenant_id` as a `filter` field in the vector index and place the condition inside `$vectorSearch.filter`.

### Exercise 18 — ANN vs. ENN

If a query demands exact nearest neighbors, should you simply run ANN with `numCandidates = limit`?

**Answer:** No. ANN trades recall for speed; ENN/exact mode depends on server/version support and resource budgets. Evaluate recall@K and latency; ANN never guarantees exact top-K, especially with small candidate counts.

### Exercise 19 — Score Fusion

Lexical search returns score 5.2 and vector search returns 0.88. Can you add them to get 6.08 and claim it beats other scores?

**Answer:** No. Their scales differ. Use rank fusion (such as RRF), calibrated score normalization, or native fusion stages supported by your version.

### Exercise 20 — Spring Raw Path Mapping

Java entity field `tenantId` is annotated `@Field("tenant_id")`. What name goes into raw BSON `$search.compound.filter.equals.path`?

**Answer:** Use `"tenant_id"`, matching the physical BSON key and Search index mapping. Never assume raw `Document` objects are remapped by Spring like typed `Criteria.where("tenantId")`.

### Exercise 21 — Spring Repositories

Does `findByTitleContaining("laptop")` automatically turn on MongoDB Search fuzzy/typo matching?

**Answer:** No. It is a derived database query using regex matching depending on keyword semantics. Fuzzy matching and autocomplete require Search-specific indexes and stages/APIs.

### Exercise 22 — Reactive Search

`ReactiveMongoTemplate.aggregate(...)` returns `Flux<Document>`. Does it make Search index updates more synchronous than `MongoTemplate`?

**Answer:** No. Reactive only changes client I/O and execution lifecycles. Search service indexing and consistency are independent server-side properties.

### Exercise 23 — Indexing Lag

After `repository.insert(product)`, `findById` finds the document while `$search` does not. Should we retry `insert` until Search finds it?

**Answer:** No. Retrying creates duplicates or unintended side effects. Check Search readiness/lag and use UI read-by-ID, optimistic recent items, or bounded waits instead of repeating business writes.

### Exercise 24 — ACLs During Search Lag

A user's read permission on a document was revoked, yet the Search index hasn't synced the visibility change. Queries may return stale hits. How do you protect against this?

**Answer:** Never rely on the Search index as the final permission source of truth; revalidate permissions/current DB state before returning sensitive data. Keep visibility filters inside Search to prune candidates while still accounting for lag.

### Exercise 25 — Appropriate Testing

A `@DataMongoTest` against an older Docker `mongod` passes `findBySku`. Does that prove `$search`/`$vectorSearch` work?

**Answer:** No. You need a Search-enabled environment (Atlas, self-managed `mongot`, or `mongodb-atlas-local`), `READY` indexes, and integration tests exercising those exact stages.

### Exercise 26 — Search Outage

When `mongot` errors, an API returns `200 OK []`. What is wrong?

**Answer:** It equates “zero matches” with “service unavailable”, misleading UIs/analytics and hiding operational failures. Return classified errors or an explicit degraded contract rather than swallowing exceptions.

### Exercise 27 — Pagination

`$search` matches 10,000 items. A client runs `$skip:9900` then `$limit:20`. Should this be treated as efficient and stable by default?

**Answer:** No. Deep offsets are expensive and results can shift when indexes or data mutate. Consider Search pagination tokens (`searchAfter`/`searchBefore` in supported versions), deterministic sorting, and consistency policies.

### Exercise 28 — Index Creation Permissions

A controller lets users submit arbitrary Search index definitions and calls `searchIndexOps.createIndex(...)`. What are the risks?

**Answer:** Exposes schema/permission alterations, resource exhaustion, and potential data exposure. Manage indexes via migrations/infrastructure with restricted privileges and review/rollout controls, never per request.

## References

The following links are official references; verify against **your project's exact versions**, as MongoDB Search (especially self-managed, vector, and hybrid) continues evolving and some Spring Data Javadocs still use “Atlas Search” terminology:

- [MongoDB Manual — Index Types](https://www.mongodb.com/docs/manual/core/indexes/index-types/): B-tree, multikey, text, geospatial, wildcard, and database index classifications.
- [MongoDB Manual — Text Index Restrictions](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-text/text-index-restrictions/): `$text` and text index limitations.
- [MongoDB Manual — `$text` in Aggregation](https://www.mongodb.com/docs/manual/tutorial/text-search-in-aggregation/): `$match`, `textScore`, and stage restrictions.
- [MongoDB Search — Self-managed Deployments](https://www.mongodb.com/docs/search/self-managed/current/): `mongot`, Community/Enterprise 8.2+, local testing, and production deployment paths.
- [MongoDB Search — Self-managed Feature Limitations](https://www.mongodb.com/docs/search/self-managed/current/limitations/): similarities and differences compared to Atlas.
- [MongoDB Search — `$search`](https://www.mongodb.com/docs/search/query/aggregation-stages/search/): lexical Search DSL, index, query operators, stage placement, and scoring.
- [MongoDB Search — `$searchMeta`](https://www.mongodb.com/docs/search/query/aggregation-stages/searchmeta/): metadata, facets, counts, and restrictions.
- [MongoDB Search — Counting Results](https://www.mongodb.com/docs/search/query/counting/): `total` vs. `lowerBound`, `$$SEARCH_META`.
- [MongoDB Search — Create Search Index](https://www.mongodb.com/docs/manual/reference/method/db.collection.createsearchindex/): `createSearchIndex` syntax, Search/Vector types, and index builds.
- [MongoDB Search — Search Query Syntax](https://www.mongodb.com/docs/search/query/query-syntax/): choosing `$search`/`$searchMeta` and pipeline composition.
- [MongoDB Manual — `$vectorSearch`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/vectorsearch/): compatibility, query syntax, pre-filters, and stage limitations.
- [MongoDB Search — Feature Compatibility](https://www.mongodb.com/docs/search/deployment/feature-compatibility/): capabilities by deployment and version.
- [Spring Data MongoDB — Querying Documents](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-query-operations.html): `Criteria`, `TextQuery`, `TextCriteria`, scores, and query mapping.
- [Spring Data MongoDB — MongoDB Search](https://docs.spring.io/spring-data/mongodb/reference/mongodb/mongo-search-indexes.html): `VectorIndex`, `SearchIndexOperations`, `VectorSearchOperation`.
- [Spring Data MongoDB — Repository Vector Search](https://docs.spring.io/spring-data/mongodb/reference/mongodb/repositories/vector-search.html): `@VectorSearch`, `Vector`, `Score`, `SearchResults<T>`.
- [Spring Data MongoDB — `VectorSearchOperation` Javadoc](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/aggregation/VectorSearchOperation.html): builder, filters, score, version-specific API.
- [Spring Data MongoDB — `VectorIndex` Javadoc](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/index/VectorIndex.html): vector/filter fields and similarity configuration.
- [Spring Data MongoDB — `SearchIndexOperations` Javadoc](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/index/SearchIndexOperations.html): creating, updating, checking status, and checking existence of Search indexes.
