# `@Indexed`, `@CompoundIndex`, and Specialized Index Annotations

## 1. The Problem: Is Declaring Indexes in Java Enough?

An e-commerce system stores millions of products in MongoDB. Admin screens commonly query:

- Find a product by **tenantId + sku**.
- List active products for a tenant, sorted by **updatedAt descending**.
- Find orders by **tenantId + status + createdAt**.
- Expire tokens or sessions after a period of time.
- Search documents by keywords, or stores near geographic coordinates.

These queries can run even without indexes, but as data grows, MongoDB may have to read far too many documents. *Indexes* accelerate finding matching data when the query shape and key order align. In exchange, indexes consume storage and add update overhead on writes.

In Spring Data MongoDB, we can express index creation intent on entities using:

- **@Indexed** for a single field.
- **@CompoundIndex / @CompoundIndexes** for multiple ordered fields.
- **@TextIndexed**, **@GeoSpatialIndexed**, **@HashIndexed**, **@WildcardIndexed** for specialized query types.

However, a vital principle is: **declaring annotation metadata does not mean the index exists on MongoDB Server**. Actual index creation depends on `auto-index-creation` configuration, application startup behavior, and migration strategy.

The lesson **@Indexed, @CompoundIndex, and Specialized Index Annotations** belongs to the **Indexes** chapter in the **SPRING_DATA_MONGODB** module. The module uses Spring Data MongoDB to connect, map documents, and operate via MongoTemplate or repositories; understanding indexes supports designing queries, aggregations, transactions, reactive access, testing, and data performance diagnostics.

After this lesson, you can:

1. Place index annotations properly on entities and understand Java/BSON field names.
2. Choose single-field or compound indexes for real queries.
3. Distinguish unique, sparse, partial, and TTL indexes to avoid data loss or wrong uniqueness locks.
4. Use text, 2dsphere, hashed, and wildcard indexes in appropriate contexts.
5. Decide when to create indexes automatically, on startup, or via controlled migrations.
6. Inspect indexes on MongoDB, run explain, and measure outcomes.
7. Test index constraints with repositories/MongoTemplate against real MongoDB.

## 2. Sample Data for the Indexes Chapter

Collection **products**:

~~~javascript
{
  _id: ObjectId("507f1f77bcf86cd799439011"),
  tenant_id: "shop-a",
  sku: "BOOK-001",
  name: "Spring Data MongoDB",
  active: true,
  priceMinor: NumberLong("199000"),
  updatedAt: ISODate("2025-06-01T09:00:00Z"),
  tags: ["JAVA", "MONGODB"]
}
~~~

Two scenarios:

1. **sku** may repeat between **shop-a** and **shop-b**, but must never duplicate within the same tenant.
2. Active products of a tenant are browsed by latest updatedAt, so we must check whether an index supports both **filtering and sorting**.

Minimal entity:

~~~java
package com.example.catalog;

import java.time.Instant;
import java.util.List;
import org.bson.types.ObjectId;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;

@Document(collection = "products")
public class ProductDocument {

    @Id
    private ObjectId id;

    @Field("tenant_id")
    private String tenantId;

    private String sku;
    private String name;
    private boolean active;
    private long priceMinor;
    private Instant updatedAt;
    private List<String> tags;

    public ObjectId getId() { return id; }
    public String getTenantId() { return tenantId; }
    public String getSku() { return sku; }
    public boolean isActive() { return active; }
    public long getPriceMinor() { return priceMinor; }
    public Instant getUpdatedAt() { return updatedAt; }
}
~~~

This class illustrates the fields relevant to indexing; real applications need constructors/validation matching the project's Spring Data mapping style.

### 2.1. Indexes Live on the Collection, Not Inside Java Objects

When declaring indexes on ProductDocument, Spring Data uses mapping metadata to identify indexes for the **products** collection. MongoDB maintains indexes over physical BSON data, regardless of whether queries originate from a repository or MongoTemplate.

A single index serves all queries against that collection sharing compatible filter/sort shapes, including queries from mongosh and the plain MongoDB Java Driver.

## 3. How Do MongoDB Indexes Operate?

Standard MongoDB indexes are structures optimized for searching/sorting by key instead of forcing the server to read every document.

~~~mermaid
flowchart LR
    A["Repository / MongoTemplate query"] --> B["MongoDB query planner"]
    B --> C{"Suitable index?"}
    C -->|Yes| D["IXSCAN and additional steps"]
    C -->|No or not beneficial| E["COLLSCAN"]
    D --> F["Return documents / projection"]
    E --> F
~~~

An index can help:

- Filter equality/ranges faster.
- Serve sorts for certain query shapes.
- Enforce unique constraints.
- Power specialized mechanisms such as TTL, text search, and geospatial search.

In exchange:

- Each insert/update/delete may need to maintain affected indexes.
- Indexes consume disk and memory.
- Building an index on a large collection carries operational cost.
- A misordered index may fail to support actual filters/sorts.

**Having an index does not guarantee the query planner will pick it**, and **IXSCAN does not automatically mean a fast query**. Measure keys/documents examined, latency, and sort/fetch demands.

### 3.1. Default Index on _id

MongoDB creates a unique index on **_id** for normal collections. If ProductDocument already has @Id, do not add another @Indexed(unique=true) just to enforce _id uniqueness.

~~~javascript
db.products.getIndexes();
~~~

A newly created collection typically has:

~~~javascript
{ key: { _id: 1 }, name: "_id_", unique: true }
~~~

The structure of `getIndexes` output may include version, options, and other metadata depending on the server.

## 4. @Indexed: One Property, One Single-Field Index

Annotation:

~~~java
import org.springframework.data.mongodb.core.index.Indexed;

public class ProductDocument {
    @Indexed
    private String sku;
}
~~~

This declares that Spring Data may create an ascending index on **sku** when index creation is enabled.

Equivalent intent:

~~~javascript
db.products.createIndex({ sku: 1 });
~~~

This index **does not bind tenantId**. In a multi-tenant system requiring per-tenant SKU uniqueness, do not mark `sku` as collection-wide unique; use a compound unique index.

### 4.1. Naming Indexes Explicitly

~~~java
@Indexed(name = "idx_products_sku")
private String sku;
~~~

Explicit names make indexes easy to recognize in `getIndexes`, migrations, and monitoring. However, if an index with the same key pattern already exists under a different name or options, editing the annotation does not rename the existing server index automatically.

### 4.2. Ascending/Descending Direction

~~~java
import org.springframework.data.mongodb.core.index.IndexDirection;

@Indexed(
    name = "idx_products_updated_desc",
    direction = IndexDirection.DESCENDING
)
private Instant updatedAt;
~~~

Illustrative descending index:

~~~javascript
db.products.createIndex(
  { updatedAt: -1 },
  { name: "idx_products_updated_desc" }
);
~~~

With standard single-field indexes, MongoDB can scan the index in reverse, so not every descending sort needs a separate DESC index. Key direction matters much more in **mixed-direction compound sorts**.

### 4.3. Two @Indexed Annotations Do Not Make a Compound Index

~~~java
@Indexed
private String tenantId;

@Indexed
private String sku;
~~~

These are **two separate single-field indexes** on `tenantId` and `sku`, not a compound index **{ tenantId: 1, sku: 1 }**.

MongoDB has strategies to combine indexes in certain queries, but index intersection should not be treated as a default substitute for a workload-tailored compound index.

## 5. @Indexed(unique = true): Protecting Business Keys

~~~java
@Indexed(name = "uk_products_sku", unique = true)
private String sku;
~~~

Meaning: prevents any two documents in the entire collection from sharing the same `sku` per unique index rules.

~~~javascript
db.products.createIndex(
  { sku: 1 },
  { unique: true, name: "uk_products_sku" }
);
~~~

### 5.1. Why Is Checking `exists` Before Insert Not Enough?

If two concurrent requests execute:

~~~java
if (!repository.existsBySku(sku)) {
    repository.insert(product);
}
~~~

both can observe the SKU does not exist yet and both proceed to insert. This is a classic race condition (**check-then-act**).

Only a **unique index on MongoDB** enforces uniqueness under concurrency. The application can still pre-check for friendly UX errors, yet must catch duplicate-key errors on the write path.

### 5.2. Errors When Duplicate Data Already Exists

If the collection already holds two products with the same `sku`, creating a **unique index** on `sku` will fail until the data is resolved.

**Never auto-delete duplicate records just to make index creation pass**. Identify canonical records, merge/migrate per business rules, back up, and deploy in a controlled manner.

### 5.3. Unique on Optional Fields

With standard single-field unique indexes, absent fields and null values follow special indexing rules that cause duplicate-key errors once more than one missing/null record exists. **Never assume a unique index permits unlimited documents lacking the field**.

Depending on requirements, consider a **partial unique index** to enforce uniqueness only across documents with valid fields or target statuses.

## 6. @CompoundIndex: Combining Multiple Properties in Order

In a multi-tenant system, SKUs need to be unique only **within each tenant**.

~~~java
import org.springframework.data.mongodb.core.index.CompoundIndex;

@Document(collection = "products")
@CompoundIndex(
    name = "uk_products_tenant_sku",
    def = "{ 'tenant_id': 1, 'sku': 1 }",
    unique = true
)
public class ProductDocument {
    // tenantId maps to BSON tenant_id; sku stays sku.
}
~~~

Intended MongoDB command:

~~~javascript
db.products.createIndex(
  { tenant_id: 1, sku: 1 },
  {
    name: "uk_products_tenant_sku",
    unique: true
  }
);
~~~

Examples:

| tenant_id | sku | Inserted? |
| --- | --- | --- |
| shop-a | BOOK-001 | Yes, if key does not exist yet |
| shop-b | BOOK-001 | Yes, different tenant |
| shop-a | BOOK-002 | Yes |
| shop-a | BOOK-001 a second time | **No**, duplicate compound key |

### 6.1. Annotation Placed on the Type

**@CompoundIndex** is placed on the entity class (or a suitable embedded type per mapping). **def** specifies the key pattern and field order.

Do not assume every field inside `def` also needs its own `@Indexed`. Adding redundant single-field `@Indexed` annotations creates extra indexes and increases write overhead.

### 6.2. Java Properties vs. BSON Field Names

The entity uses **@Field("tenant_id")** for `tenantId`. Inside index definitions, Spring Data has mechanisms to resolve property paths to BSON names. Depending on configuration, `def` passes through Spring Data's resolver; for security/unique indexes, **always verify actual `getIndexes` output** to ensure the index targets **tenant_id**, not an unintended field.

Never look at the annotation alone and assume the server index has the right name or options.

## 7. Multiple @CompoundIndex and @CompoundIndexes

An entity often serves multiple query patterns:

1. Look up by tenant + sku.
2. List active products for a tenant sorted by updatedAt.

Declaring multiple compound indexes:

~~~java
import org.springframework.data.mongodb.core.index.CompoundIndex;
import org.springframework.data.mongodb.core.index.CompoundIndexes;

@Document(collection = "products")
@CompoundIndexes({
    @CompoundIndex(
        name = "uk_products_tenant_sku",
        def = "{ 'tenant_id': 1, 'sku': 1 }",
        unique = true
    ),
    @CompoundIndex(
        name = "idx_products_tenant_active_updated",
        def = "{ 'tenant_id': 1, 'active': 1, 'updatedAt': -1 }"
    )
})
public class ProductDocument {
    // Fields as in section 2.
}
~~~

In Spring Data releases supporting repeatable annotations, multiple `@CompoundIndex` annotations can be placed directly; **@CompoundIndexes** remains clear for grouping indexes on a class.

Note: this is an **alternative variant** to the single `@CompoundIndex` in the previous section—do not paste both into the same class and accidentally create duplicate indexes.

### 7.1. Why Does Key Order Matter?

Index:

~~~javascript
{ tenant_id: 1, active: 1, updatedAt: -1 }
~~~

is well suited to evaluate for:

~~~javascript
db.products.find({
  tenant_id: "shop-a",
  active: true
}).sort({ updatedAt: -1 }).limit(20);
~~~

Because the first two fields are fixed by equality, MongoDB can traverse along `updatedAt` to satisfy sort and limit.

Yet the same index does not automatically optimize:

~~~javascript
db.products.find({ active: true });
~~~

because **tenant_id** is the leading key and goes unconstrained. The prefix rule is crucial when evaluating compound indexes.

### 7.2. Equality, Sort, Range

A practical guideline is considering **equality → sort → range** ordering, though it is a **heuristic**, not a rigid formula for every workload. Optimal key order depends on selectivity, actual filters, sorts, limits, and existing indexes.

Example:

~~~javascript
db.orders.find({
  tenantId: "shop-a",
  status: "PAID",
  createdAt: {
    $gte: ISODate("2025-06-01T00:00:00Z"),
    $lt: ISODate("2025-07-01T00:00:00Z")
  }
}).sort({ createdAt: -1 });
~~~

Candidate index to evaluate:

~~~javascript
{ tenantId: 1, status: 1, createdAt: -1 }
~~~

Verify with explain on representative data rather than applying rules mechanically.

### 7.3. Mixed-Direction Sorts

Example sort:

~~~javascript
.sort({ priceMinor: 1, updatedAt: -1 })
~~~

An index with mixed directions:

~~~javascript
{ priceMinor: 1, updatedAt: -1 }
~~~

differs semantically from **{ priceMinor: 1, updatedAt: 1 }**. With multi-field sorts, key direction alignment determines whether forward or reverse index traversal can serve the sort.

## 8. Indexes on Nested Objects and Arrays

MongoDB supports indexing nested field paths, for example:

~~~javascript
db.products.createIndex({ "supplier.region": 1 });
~~~

If an entity embeds `SupplierInfo`:

~~~java
public class SupplierInfo {
    private String code;

    @Indexed(name = "idx_supplier_region")
    private String region;
}
~~~

and `ProductDocument` contains:

~~~java
private SupplierInfo supplier;
~~~

Spring Data's index resolver can follow nested path metadata to create the index on the root collection. Index naming and prefixing inside nested types depend on mapping context; check **getIndexes** to confirm the actual name and keys.

### 8.1. Multikey Indexes

~~~java
@Indexed(name = "idx_products_tags")
private List<String> tags;
~~~

When a field is an array, MongoDB creates a **multikey index**. It accelerates finding documents containing matching elements, such as:

~~~javascript
db.products.find({ tags: "JAVA" });
~~~

However, multikey indexes carry constraints on combining multiple array paths in one compound index, sorting, and matching across array elements. **Never assume a compound index can contain two independent array fields across documents**.

With embedded arrays and multiple predicates targeting the **same element**, understand **$elemMatch** semantics and how MongoDB constructs index bounds.

## 9. Sparse Indexes: Including Only Documents with the Field

A sparse index can be declared:

~~~java
@Indexed(name = "idx_optional_code_sparse", sparse = true)
private String optionalCode;
~~~

This aims to exclude documents **missing `optionalCode`**. Equivalent command:

~~~javascript
db.products.createIndex(
  { optionalCode: 1 },
  { sparse: true }
);
~~~

**Sparse does not mean skipping all null values.** Documents where the field exists with value `null` are still indexed per that index type's rules. Therefore, if uniqueness is needed only for populated/valid values, understand null vs. missing and prefer partial indexes in most cases.

### 9.1. Sparse Affects Planner Eligibility

Because a sparse index omits some documents, MongoDB cannot use it to return complete results for queries that might need documents lacking the field without suitable filters.

Never force a query onto a sparse index via hint and then assume the collection contains only the returned documents. The index does not represent the entire collection.

## 10. Partial Indexes: Indexing a Conditional Subset

A partial index uses **partialFilterExpression** to index only documents matching a filter condition.

Suppose display codes need lookup/uniqueness only among active products:

~~~javascript
db.products.createIndex(
  { tenant_id: 1, displayCode: 1 },
  {
    name: "uk_active_tenant_display_code",
    unique: true,
    partialFilterExpression: { active: true }
  }
);
~~~

Compound annotation declaration:

~~~java
@CompoundIndex(
    name = "uk_active_tenant_display_code",
    def = "{ 'tenant_id': 1, 'displayCode': 1 }",
    unique = true,
    partialFilter = "{ 'active': true }"
)
public class ProductDocument {
    // Corresponding fields.
}
~~~

**Meaning:** the unique compound constraint applies **to documents matching `active=true`**. Inactive documents sit outside the partial index and are not constrained by it.

### 10.1. Changing `active` Can Trigger Duplicate Key

Two inactive documents may share the same `displayCode`. When one or both switch to active, MongoDB updates the index; any write that violates uniqueness is rejected.

Application error handling must cover **both inserts and updates**, not just creation.

### 10.2. Queries Must Align with the Partial Filter

A partial index holds only a subset. MongoDB generally uses it safely only when the query contains/implies predicates proving no matching documents are omitted.

For example:

~~~javascript
db.products.find({
  tenant_id: "shop-a",
  active: true,
  displayCode: "TOP-01"
});
~~~

is eligible to use the index, unlike a query omitting `active:true` when inactive documents must also be returned.

### 10.3. Sparse and Partial Cannot Be Arbitrarily Combined

In MongoDB index options, **sparse and partialFilterExpression have combination restrictions**; never declare both merely to index fewer documents. Choose the single mechanism matching requirements and verify server acceptance.

### 10.4. When to Choose Partial Over Sparse?

| Goal | Option to evaluate |
| --- | --- |
| Skip documents missing a field | Sparse may suffice |
| Index only active documents | Partial filter |
| Enforce unique only when field meets type/condition | Partial filter matching schema/rules |
| Avoid indexing soft-deleted records | Partial filter on deleted/active |
| Every document must satisfy uniqueness | Full unique index, unfiltered |

Do not use a partial index to hide dirty data: it explicitly narrows the enforcement scope.

## 11. TTL Indexes via `@Indexed`

TTL (*time-to-live*) indexes let MongoDB automatically delete expired documents over time.

Example `login_sessions` collection with `createdAt` and a fixed-duration expiration policy:

~~~java
@Document(collection = "login_sessions")
public class LoginSessionDocument {

    @Id
    private String id;

    @Indexed(expireAfterSeconds = 3600)
    private Instant createdAt;
}
~~~

This snippet uses **expireAfterSeconds** for illustration, which may be marked deprecated in newer Spring Data versions. Newer releases provide duration-based **expireAfter**; pick the syntax matching your project version and verify the created index.

Corresponding MongoDB index:

~~~javascript
db.login_sessions.createIndex(
  { createdAt: 1 },
  { expireAfterSeconds: 3600 }
);
~~~

A document with `createdAt = 10:00Z` is eligible for expiration after `11:00Z`, yet **never assume deletion at exactly 11:00:00Z**. The TTL monitor runs asynchronously and lags based on load, topology, and configuration.

### 11.1. TTL Is Not an Exact Scheduler

Never rely on TTL as the sole mechanism to:

- Send expiration notifications at an exact second.
- Revoke access permissions at the exact expiration instant.
- Trigger time-exact business workflows.

Applications should **check expiration timestamps on read/validation**. TTL is background cleanup, not authorization.

### 11.2. TTL Works Only with Compatible Time Types

Standard TTL indexes require a BSON Date field (or array of Dates per MongoDB semantics). If an entity stores:

~~~javascript
{ createdAt: "2025-06-01T10:00:00Z" }
~~~

do not expect a standard TTL index to interpret that String as an expiration timestamp. Map `Instant`/BSON Date properly and test it.

### 11.3. Single-Field TTL Differs from Compound Indexes

Standard TTL requires a **single-field index** with `expireAfterSeconds`; never attach TTL to an arbitrary compound index expecting MongoDB to expire across composite keys.

If multi-tenant data needs per-tenant retention, store a per-document **expiresAt** deadline or use separate collections/policies. Never try to force TTL onto a compound `tenant+createdAt` index where unsupported by the server.

### 11.4. The `expiresAt` Approach

~~~java
@Document(collection = "login_sessions")
public class LoginSessionDocument {

    @Id
    private String id;

    @Indexed(expireAfterSeconds = 0)
    private Instant expiresAt;
}
~~~

This policy uses **expiresAt** as the document's deletion deadline with `expireAfterSeconds=0`. Physical cleanup still lags asynchronously: expired sessions must be rejected in business logic even while the document remains present.

## 12. `@TextIndexed`: Full-Text Term Search

MongoDB provides **text indexes** for text search using tokenization and language rules.

~~~java
import org.springframework.data.mongodb.core.index.TextIndexed;

@Document(collection = "articles")
public class ArticleDocument {

    @Id
    private String id;

    @TextIndexed(weight = 5)
    private String title;

    @TextIndexed(weight = 1)
    private String body;
}
~~~

Spring Data combines `@TextIndexed` fields into a collection text index. *Weights* indicate relative importance for relevance scoring.

Conceptual MongoDB equivalent:

~~~javascript
db.articles.createIndex(
  { title: "text", body: "text" },
  { weights: { title: 5, body: 1 } }
);
~~~

### 12.1. One Text Index per Collection

MongoDB restricts traditional **text indexes** per collection: normally **only one text index** is permitted, though it can span multiple fields. Therefore, do not treat each `@TextIndexed` as creating unlimited independent text indexes.

### 12.2. Querying Text via Spring Data

~~~java
import org.springframework.data.mongodb.core.query.TextCriteria;
import org.springframework.data.mongodb.core.query.TextQuery;

TextCriteria criteria = TextCriteria
    .forDefaultLanguage()
    .matching("mongodb");

TextQuery query = TextQuery.queryText(criteria)
    .sortByScore();

List<ArticleDocument> articles =
    mongoTemplate.find(query, ArticleDocument.class);
~~~

This snippet invokes text search and score sorting via Spring Data APIs. For multilingual or non-English text, configure appropriate languages/analyzers and never assume default tokenization handles Vietnamese the same as English.

### 12.3. Text Search Is Not Arbitrary Substring Search

Do not equate a text index with:

~~~javascript
db.articles.find({ body: /mongo/i });
~~~

Regex/substring matching and `$text` have distinct semantics. Text indexes also do not natively provide fuzzy matching or autocomplete like dedicated search engines. For rich natural-language relevance, consider solutions such as Atlas Search.

### 12.4. `@Language` and `@TextScore`

Spring Data supports language and text-score metadata in compatible versions. **@Language** configures language handling for text indexes, while **@TextScore** maps relevance scores when queries project that metadata.

Do not add `@TextScore` expecting every ordinary `find` to populate a score; scores are computed only by matching text queries.

## 13. `@GeoSpatialIndexed`: `2dsphere` Indexes and GeoJSON

Store location example:

~~~javascript
{
  name: "Store A",
  location: {
    type: "Point",
    coordinates: [106.70, 10.78]
  }
}
~~~

In GeoJSON, coordinates follow **[longitude, latitude]** order, never reversed.

~~~java
import org.springframework.data.mongodb.core.geo.GeoJsonPoint;
import org.springframework.data.mongodb.core.index.GeoSpatialIndexType;
import org.springframework.data.mongodb.core.index.GeoSpatialIndexed;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "stores")
public class StoreDocument {

    private String name;

    @GeoSpatialIndexed(type = GeoSpatialIndexType.GEO_2DSPHERE)
    private GeoJsonPoint location;
}
~~~

Equivalent index:

~~~javascript
db.stores.createIndex({ location: "2dsphere" });
~~~

### 13.1. `2d` Differs from `2dsphere`

| Index | Common Target |
| --- | --- |
| 2d | Planar/legacy coordinates or specialized flat geometries |
| 2dsphere | Geographic coordinates on Earth's surface; GeoJSON and spherical queries |

Do not pick index type from the Java class alone without checking BSON format, distance/radius units, and query operators.

### 13.2. Geospatial Queries

~~~javascript
db.stores.find({
  location: {
    $near: {
      $geometry: {
        type: "Point",
        coordinates: [106.70, 10.78]
      },
      $maxDistance: 5000
    }
  }
});
~~~

For GeoJSON/`2dsphere`, `$maxDistance` is measured in meters. Never swap coordinate order or copy distance constants from legacy planar APIs without verifying units.

In Spring Data MongoDB, you can use **NearQuery**, **geoNear aggregations**, repository geo methods, or `MongoTemplate` depending on requirements.

### 13.3. Protecting Sensitive Locations

Geo indexes accelerate spatial lookups; they do not enforce access control or obfuscate coordinates. Sensitive user or warehouse coordinates require proper authorization, retention, and projection policies.

## 14. `@HashIndexed`: Equality Lookups and Hashed Keys

MongoDB supports **hashed indexes** on hashed field values to support equality lookups and hashed shard-key distribution.

~~~java
import org.springframework.data.mongodb.core.index.HashIndexed;

@Document(collection = "tracking_events")
public class TrackingEventDocument {

    @HashIndexed
    private String deviceId;
}
~~~

Index intent:

~~~javascript
db.tracking_events.createIndex({ deviceId: "hashed" });
~~~

### 14.1. Hashed Indexes Are Not for Range or Sort

Hashed values do not preserve the comparison order of the original values. Consequently:

- Exact equality lookups on the key can be a valid use case.
- Range queries like **deviceId > value** are not optimized like an ordered B-tree index.
- Never use a hashed index to satisfy sorting by `deviceId`.
- Hashed indexes **do not support unique constraints** like regular unique indexes.

To enforce uniqueness, use an appropriate unique index on the unhashed key rather than treating a hashed index as duplicate protection.

### 14.2. Sharding Is More Than an Annotation

Choosing a hashed shard key requires analyzing cardinality, tenant/key query patterns, write distribution, and range query needs. Adding `@HashIndexed` does not shard a collection or define cluster partitioning.

## 15. `@WildcardIndexed`: Querying Unknown Dynamic Fields

Products may carry varying dynamic metadata per category:

~~~javascript
{
  sku: "LAPTOP-01",
  attributes: {
    ramGb: 16,
    cpu: "i7",
    keyboardLayout: "US"
  }
}
~~~

Another document:

~~~javascript
{
  sku: "SHIRT-01",
  attributes: {
    size: "L",
    color: "navy"
  }
}
~~~

When exact field names inside **attributes** are unknown upfront, MongoDB offers **wildcard indexes**.

~~~java
import java.util.Map;
import org.springframework.data.mongodb.core.index.WildcardIndexed;

@Document(collection = "products")
public class ProductDocument {

    @WildcardIndexed
    private Map<String, Object> attributes;
}
~~~

For compatible nested structures, the MongoDB index intent looks like:

~~~javascript
db.products.createIndex({ "attributes.$**": 1 });
~~~

Inspect **getIndexes()** after running the index resolver to verify the actual BSON path. Fields renamed via `@Field` must also be checked.

### 15.1. Wildcard Indexes Are Not for Every Query

Wildcard indexes suit flexible schemas, yet carry limitations:

- Limited support for complex compound filters and sorting.
- Index storage grows rapidly when many dynamic fields exist.
- Certain predicates do not optimize as tightly as dedicated field indexes.
- Query plans can vary when field presence is uneven.

For heavily queried fields, a **dedicated index** often outperforms a broad wildcard index.

### 15.2. Avoid Blindly Indexing Sensitive Fields

A document-wide wildcard index creates entries and lookup paths for fields never meant to be searched. Scope wildcards to **attributes** or a dedicated subtree, and control field counts, document sizes, retention, and access permissions.

### 15.3. Wildcard Does Not Replace Schema Validation

`Map<String,Object>` holding dynamic attributes still needs validation for types, sizes, and key counts. A wildcard index neither normalizes JSON/BSON nor validates input structure.

## 16. Comparison Table of Index Annotations

| Annotation | Placement | Index Type | Problem Solved |
| --- | --- | --- | --- |
| @Indexed | Property | Single-field; supports unique/sparse/TTL | Equality/range/sort, single-key constraints |
| @CompoundIndex | Type/class | Ordered compound keys | Tenant + business key; filter + sort |
| @CompoundIndexes | Type/class | Multiple compound indexes | Multiple query patterns |
| @TextIndexed | Property | Text index (multi-field supported) | Keyword text search |
| @GeoSpatialIndexed | Property | 2d or 2dsphere | Spatial/geographic queries |
| @HashIndexed | Property | Hashed index | Equality/shard-key distribution patterns |
| @WildcardIndexed | Supported property/type | Wildcard path index | Dynamic fields / nested metadata |

**Annotations do not invent new query planners**. Once indexes exist, repositories, MongoTemplate, and Java Driver queries all rely on MongoDB's query planner.

### 16.1. Annotations and Version Compatibility

Certain options and annotations may not exist in older Spring Data versions. In particular, TTL duration attributes, nested/map handling, and newer index options should be checked against your actual dependency API.

Do not paste options from newer docs into an older project and mistake compile errors for MongoDB Server errors.

## 17. Auto-Index-Creation: Annotations Do Not Appear in the Database Automatically

Since Spring Data MongoDB **3.0**, **automatic index creation from annotations is disabled by default**. Simply writing:

~~~java
@Indexed(unique = true)
private String sku;
~~~

provides no guarantee the index is created on startup unless auto-index creation is enabled or a separate migration runs.

### 17.1. Spring Boot Configuration

In many Spring Boot versions, the setting is:

~~~yaml
spring:
  data:
    mongodb:
      auto-index-creation: true
~~~

This is an **example configuration**—verify it against your Spring Boot version and auto-configuration setup. It permits Spring Data to create declared indexes for entities in the mapping context.

### 17.2. Java Configuration When Extending `AbstractMongoClientConfiguration`

~~~java
import org.springframework.data.mongodb.config.AbstractMongoClientConfiguration;

public class MongoConfig extends AbstractMongoClientConfiguration {

    @Override
    protected String getDatabaseName() {
        return "catalog";
    }

    @Override
    protected boolean autoIndexCreation() {
        return true;
    }
}
~~~

This illustrates Spring Data's configuration hook; real applications also declare connection settings and proper bean wiring. **Do not add a second `AbstractMongoClientConfiguration` alongside Spring Boot auto-configuration if it duplicates connection beans**.

### 17.3. When Does Auto-Index Run?

Spring Data creates indexes for entities discovered in the mapping context during initialization or first access, depending on setup. However, **never treat this as a complete migration tool**:

- It does not drop stale indexes removed from annotations.
- It does not safely migrate changed options or names on existing indexes.
- It does not automatically recreate indexes if a collection is dropped and recreated at runtime.
- It does not replace reviewing build impact on large collections.
- Startup can fail if a new unique index hits existing duplicates.

In production, most teams prefer versioned migrations with controlled rollouts instead of letting every app instance manage indexes on boot.

### 17.4. Local Has the Index, Production Does Not

If local dev enables `auto-index-creation=true` while production disables it without a migration, repositories still return accurate data yet `explain` reveals `COLLSCAN`.

**Seeing an annotation in source code never proves the index exists on the server.** Inspect `getIndexes` in the exact deployment under investigation.

## 18. Creating Indexes Explicitly via `MongoTemplate`

Spring Data provides **IndexOperations** for explicit index creation:

~~~java
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.index.Index;

public void ensureTenantSkuIndex(MongoTemplate template) {
    template.indexOps(ProductDocument.class).ensureIndex(
        new Index()
            .on("tenantId", Sort.Direction.ASC)
            .on("sku", Sort.Direction.ASC)
            .unique()
            .named("uk_products_tenant_sku")
    );
}
~~~

When calling **indexOps(ProductDocument.class)**, mapping metadata translates Java properties to matching BSON field names. Still inspect `getIndexes` to verify the physical `tenant_id` key and options.

### 18.1. `IndexDefinition`

`IndexOperations.ensureIndex` accepts an **IndexDefinition**. Builders and definitions can specify:

- Key pattern and sort directions.
- Unique, sparse, partial options.
- TTL where supported by the server.
- Index name.
- Additional options such as collation or language per version support.

Never assume every builder method exists in every Spring Data version.

### 18.2. Programmatic Partial Index

~~~java
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.index.Index;
import org.springframework.data.mongodb.core.index.PartialIndexFilter;
import org.springframework.data.mongodb.core.query.Criteria;

Index index = new Index()
    .on("tenantId", Sort.Direction.ASC)
    .on("displayCode", Sort.Direction.ASC)
    .unique()
    .partial(PartialIndexFilter.of(
        Criteria.where("active").is(true)
    ))
    .named("uk_active_tenant_display_code");

template.indexOps(ProductDocument.class).ensureIndex(index);
~~~

This snippet assumes `displayCode` was added to the entity and your Spring Data version includes the partial filter API. Extend the section 2 entity schema before using it.

### 18.3. `ensureIndex` Does Not Replace Migrations

"Ensure" guarantees an index matching that definition exists—**it does not migrate existing indexes with conflicting options, clean duplicate data, or drop incompatible indexes**.

Production workflow:

1. Inspect existing indexes.
2. Audit duplicates and index build cost.
3. Create new indexes per plan.
4. Confirm queries switch to the new indexes.
5. Clean up obsolete indexes only after stability is confirmed.

Never auto-drop indexes in startup hooks just because an annotation changed.

## 19. `IndexResolver`: Reading Index Metadata from Entities

**MongoPersistentEntityIndexResolver** uses mapping metadata to collect declared indexes.

~~~java
import org.springframework.data.mongodb.core.index.IndexDefinition;
import org.springframework.data.mongodb.core.index.MongoPersistentEntityIndexResolver;
import org.springframework.data.mongodb.core.mapping.MongoMappingContext;

public void ensureDeclaredIndexes(
        MongoTemplate template,
        MongoMappingContext mappingContext) {

    var resolver =
        new MongoPersistentEntityIndexResolver(mappingContext);

    for (IndexDefinition definition :
            resolver.resolveIndexFor(ProductDocument.class)) {
        template.indexOps(ProductDocument.class)
            .ensureIndex(definition);
    }
}
~~~

This illustrates **annotation → IndexDefinition → ensureIndex**. Never execute resolver/ensureIndex calls per HTTP request, since index creation is a schema operation with real cost.

### 19.1. Map-Like Properties

The index resolver cannot predict runtime keys inside a dynamic `Map`. Use `@WildcardIndexed` or explicit index definitions for known paths. Entity scanning never replaces inspecting real BSON shapes.

### 19.2. Activation Timing

In many setups, index resolution runs once the application context and mapping metadata are initialized. In multi-instance deployments, coordinate through a dedicated migration runner or controlled lifecycle hook to avoid races and duplicate load.

**IndexResolver does not fix existing data**: it only translates metadata into index definitions.

## 20. Inspecting Real Indexes: `getIndexes`/`listIndexes`

After creation:

~~~javascript
db.products.getIndexes();
~~~

A concise sample output:

~~~javascript
[
  {
    name: "_id_",
    key: { _id: 1 },
    unique: true
  },
  {
    name: "uk_products_tenant_sku",
    key: { tenant_id: 1, sku: 1 },
    unique: true
  },
  {
    name: "idx_products_tenant_active_updated",
    key: { tenant_id: 1, active: 1, updatedAt: -1 }
  }
]
~~~

The output above is simplified; real MongoDB metadata includes additional fields.

### 20.1. Java Driver

~~~java
import org.bson.Document;

for (Document index :
        mongoTemplate.getCollection("products").listIndexes()) {
    System.out.println(index.toJson());
}
~~~

This reads index metadata directly. Never expose an unauthenticated public endpoint dumping all index/schema details without authorization.

### 20.2. Verify Both Keys and Options

For compound unique indexes, verify:

- **Key pattern**, fields, and order.
- **unique**, **sparse**, **partialFilterExpression**.
- **collation** when uniqueness has case/locale rules.
- **expireAfterSeconds** for TTL.
- **Index type**: text, 2dsphere, hashed, wildcard.
- **Name** for operational tracking.

Matching the name while having wrong keys or options still breaks invariants or performance.

## 21. Explain: Evaluating Whether an Index Helps Queries

Repository method:

~~~java
List<ProductDocument> findTop20ByTenantIdAndActiveOrderByUpdatedAtDesc(
    String tenantId, boolean active
);
~~~

Equivalent MongoDB query:

~~~javascript
db.products.find({
  tenant_id: "shop-a",
  active: true
})
.sort({ updatedAt: -1 })
.limit(20)
.explain("executionStats");
~~~

Candidate index:

~~~javascript
{ tenant_id: 1, active: 1, updatedAt: -1 }
~~~

| Metric | Question |
| --- | --- |
| winningPlan | Did the planner select the expected index? |
| IXSCAN/COLLSCAN | Index scan or collection scan? |
| totalKeysExamined | How many index keys were scanned? |
| totalDocsExamined | How many documents were read? |
| nReturned | How many documents were returned? |
| SORT | Was an extra RAM/engine sort required? |
| executionTimeMillis | Latency on representative data? |

### 21.1. Examined vs. Returned

Returning 20 documents while scanning millions indicates an inadequate index. Still, never judge from one ratio alone: factor in filters, projections, sorts, data distribution, and reporting needs.

### 21.2. Covered Queries

Some queries can be satisfied directly from index entries without fetching source documents when all filter and projected fields lie inside the index and other constraints hold.

~~~javascript
db.products.find(
  { tenant_id: "shop-a", sku: "BOOK-001" },
  { _id: 0, tenant_id: 1, sku: 1 }
);
~~~

Do not assume repository methods returning full `ProductDocument` instances are covered, since non-indexed fields require fetching. Mapping to a smaller Java DTO also does not automatically exclude fields at the database unless projection is configured.

### 21.3. Hints Require Evidence

MongoDB supports **hint** to force an index for a query. Forcing an inappropriate index can degrade performance—especially with sparse/partial indexes. Use hints only after measuring and stabilizing the index lifecycle.

## 22. Collation and Case-Insensitive Uniqueness

Suppose two emails:

~~~text
Alice@example.com
alice@example.com
~~~

must be treated as duplicates. A unique index with default collation **does not necessarily treat them as equal**. Use normalization or an appropriate collation:

~~~javascript
db.accounts.createIndex(
  { tenantId: 1, email: 1 },
  {
    unique: true,
    name: "uk_tenant_email_ci",
    collation: {
      locale: "en",
      strength: 2
    }
  }
);
~~~

**Collation governs string comparison**; queries wanting to leverage the index efficiently generally need a compatible collation.

### 22.1. Spring Data Compatibility

Certain index options can be declared via annotations or index builders depending on Spring Data version. When uniqueness/collation is a critical invariant, use explicit `IndexDefinition` or migrations where needed and test case-variant inputs.

### 22.2. Normalization Is a Separate Policy

Lowercasing emails before persistence can enforce a consistent contract, subject to application policy. Never assume Vietnamese strings, personal names, and business keys share identical case-folding rules.

## 23. Changing Production Indexes: Treat as Schema Migrations

On collections with tens of millions of documents, creating an index is a **data infrastructure change**, not just an annotation added in a pull request.

### 23.1. Recommended Workflow

1. **Identify workload:** real filters, sorts, projections, frequency, and data shape.
2. **Capture baseline:** explain, latency, index sizes, and write overhead.
3. **Propose index:** key order, unique, partial, TTL, or specialized type.
4. **Audit legacy data:** null/missing, duplicates, BSON types, `@Field` mappings.
5. **Rehearse in staging with representative data**, including concurrent writes.
6. **Plan the build:** disk capacity, CPU/I/O, server version, and availability.
7. **Apply via controlled migration** rather than having all app instances build on boot.
8. **Verify `getIndexes`:** exact keys, name, and options.
9. **Re-check query plans:** do queries pick the new index and improve latency?
10. **Monitor write performance** before considering dropping obsolete indexes.

### 23.2. Editing Annotations Does Not Upgrade Existing Indexes

Changing:

~~~java
@Indexed(unique = false)
private String sku;
~~~

to:

~~~java
@Indexed(unique = true)
private String sku;
~~~

does not automatically turn an existing non-unique index into unique, nor does it clean duplicate records. Inspect existing options and run a migration compatible with your MongoDB Server.

### 23.3. Never Drop Indexes Unplanned

~~~javascript
db.products.dropIndex("idx_old_name");
~~~

This command has immediate production impact—**never run it in production merely because an annotation was deleted from source code**. Another query may still rely on it. Cross-check metrics and query plans and prepare a rollback before dropping.

## 24. Integration Testing Compound Unique Indexes

Unit tests mocking repositories cannot prove MongoDB Server created the index or enforces uniqueness. Use a **real MongoDB test instance** and inspect physical metadata.

### 24.1. Test Entity

~~~java
package com.example.catalog;

import org.bson.types.ObjectId;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.index.CompoundIndex;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "index_test_products")
@CompoundIndex(
    name = "uk_test_tenant_sku",
    def = "{ 'tenantId': 1, 'sku': 1 }",
    unique = true
)
public record IndexedProduct(
    @Id ObjectId id,
    String tenantId,
    String sku,
    String name
) {}
~~~

Here no `@Field` renames `tenantId`, so the index definition uses BSON key **tenantId**.

### 24.2. JUnit 5 Test with `MongoTemplate`

~~~java
package com.example.catalog;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.util.List;
import org.bson.Document;
import org.bson.types.ObjectId;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.index.Index;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

@DataMongoTest
class ProductIndexIntegrationTest {

    @Autowired MongoTemplate template;

    @Test
    void compoundUniqueWorksWithinTenant() {
        // Test ensures index explicitly instead of relying on auto-index flag.
        template.indexOps(IndexedProduct.class).ensureIndex(
            new Index()
                .on("tenantId", Sort.Direction.ASC)
                .on("sku", Sort.Direction.ASC)
                .unique()
                .named("uk_test_tenant_sku")
        );

        IndexedProduct first = new IndexedProduct(
            new ObjectId(), "shop-test-a", "BOOK-001", "A"
        );
        IndexedProduct otherTenant = new IndexedProduct(
            new ObjectId(), "shop-test-b", "BOOK-001", "B"
        );
        IndexedProduct duplicate = new IndexedProduct(
            new ObjectId(), "shop-test-a", "BOOK-001", "Duplicate"
        );

        try {
            template.insert(first);
            template.insert(otherTenant);

            assertThatThrownBy(() -> template.insert(duplicate))
                .isInstanceOf(DuplicateKeyException.class);

            long countA = template.count(
                Query.query(Criteria.where("tenantId").is("shop-test-a")),
                IndexedProduct.class
            );
            assertThat(countA).isEqualTo(1L);

            boolean hasUniqueIndex = false;
            for (Document index :
                    template.getCollection(
                        "index_test_products").listIndexes()) {
                if ("uk_test_tenant_sku".equals(
                        index.getString("name"))) {
                    hasUniqueIndex = Boolean.TRUE.equals(
                        index.getBoolean("unique")
                    );
                }
            }
            assertThat(hasUniqueIndex).isTrue();
        } finally {
            template.remove(
                Query.query(Criteria.where("_id").in(
                    List.of(
                        first.id(),
                        otherTenant.id(),
                        duplicate.id()
                    )
                )),
                IndexedProduct.class
            );
        }
    }
}
~~~

The test:

- Explicitly ensures the index so it does not rely on `auto-index-creation`.
- Inserts the same SKU in two different tenants (succeeds).
- Inserts a duplicate SKU in the same tenant (expects `DuplicateKeyException`).
- Inspects metadata to verify the index is unique.
- Cleans up fixture documents by created IDs.

**Run tests only on a dedicated test MongoDB.** For parallel test runs, use unique tenant/SKU values or isolated databases so fixtures do not collide.

### 24.3. Testing Annotation Metadata Independently

The test above verifies uniqueness **after an explicit `ensureIndex`**, without proving `@CompoundIndex` itself was resolved by the index resolver.

To test annotations directly:

1. Use `MongoPersistentEntityIndexResolver` to read `IndexedProduct` metadata.
2. Assert the `IndexDefinition` has key pattern `tenantId+sku` and the unique option.
3. Apply the resolved definition to create the index on a test database.
4. Read `getIndexes` to verify keys and options.

Separating these helps distinguish annotation/mapping bugs from server-side index errors.

## 25. Testing TTL and Partial Unique

### 25.1. Never Test TTL with Very Short Sleeps

Tests that insert an expired session, sleep 100ms, and assert deletion are inherently flaky because the TTL monitor runs asynchronously.

Better approach:

- Verify the index on **expiresAt** has **expireAfterSeconds=0**.
- Verify `expiresAt` is stored as BSON Date.
- Test that the application rejects sessions once `expiresAt` has passed.
- If testing physical cleanup end-to-end, poll with a generous timeout in an integration suite rather than expecting millisecond precision.

**TTL handles data cleanup, not session validity enforcement.**

### 25.2. Partial Unique Must Test State Transitions

For a unique index scoped to `active=true`:

1. Two inactive documents sharing `displayCode` can coexist if no other constraint forbids it.
2. Transitioning the first document to active succeeds.
3. Transitioning the second document to active with the same tenant/displayCode is rejected by the unique constraint.
4. Verify whether `active=true` queries can leverage the partial index.

Testing transitions matters because partial unique applies on **both inserts and updates** moving documents into the indexed set.

## 26. Reactive Repositories and Indexes

**ReactiveMongoRepository** shares the exact same collections, indexes, and query planner as imperative repositories.

~~~java
import org.bson.types.ObjectId;
import org.springframework.data.mongodb.repository.ReactiveMongoRepository;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public interface ReactiveProductRepository
        extends ReactiveMongoRepository<ProductDocument, ObjectId> {

    Mono<ProductDocument> findByTenantIdAndSku(
        String tenantId, String sku
    );

    Flux<ProductDocument> findByTenantIdAndActive(
        String tenantId, boolean active
    );
}
~~~

If the database has a compound index on **tenant_id + sku**, `findByTenantIdAndSku` on the reactive repository can use that same index once Spring Data maps the query and the MongoDB planner selects it.

### 26.1. Reactive Does Not Eliminate Index Cost

Non-blocking I/O does not make a `COLLSCAN` any cheaper in server CPU or disk I/O. Unindexed queries still degrade reactive application response times.

### 26.2. `ReactiveMongoTemplate` `indexOps`

Spring Data provides reactive `indexOps`. Creating an index via `ReactiveMongoTemplate` returns a `Mono`, which **requires subscription/awaiting within the lifecycle** for the command to actually execute.

In migrations, ensure startup waits for completion before accepting traffic per project policy. Never fire off an unsubscribed `Mono`, and never call `block()` on the WebFlux event loop.

## 27. Common Mistakes

| Symptom / Assumption | Cause | Resolution |
| --- | --- | --- |
| `@Indexed` present, yet explain shows COLLSCAN | Index wasn't created or planner skipped it | Check `getIndexes`, configuration, and query plan |
| Two fields have `@Indexed`, yet query is slow | Two single indexes do not form a compound index | Design `@CompoundIndex` for the workload |
| Same SKU rejected across two tenants | Unique index on `sku` collection-wide | Use compound unique on tenant+sku |
| Unique index creation fails | Legacy duplicates or null/missing collisions | Perform safe data migration |
| Partial unique ignores inactive records | Partial filter intentionally excludes inactive | Review business invariant |
| Expired session still exists | TTL monitor is asynchronous | Enforce `expiresAt` in business logic |
| TTL ignores String timestamps | Field is not BSON Date | Fix schema and migrate data |
| Text search differs from regex | Text tokenization differs from substring matching | Pick text vs. regex vs. dedicated search properly |
| Geo query returns wrong locations | Swapped lon/lat or wrong distance unit | Verify GeoJSON and 2dsphere |
| Hashed index fails to speed up sort | Hashes do not preserve sort order | Use an ordered B-tree index |
| Wildcard index grows huge | Too many dynamic fields | Scope path, add dedicated index for hot fields |
| Query misses partial index | Filter does not imply partial condition | Check query predicates and explain |
| Nested field index fails | `@Field` or path/prefix mismatch | Inspect `getIndexes` and raw BSON |
| Auto-index causes startup failure | Duplicate data or index conflict | Use controlled migrations |
| Annotation edited, old index remains | Index creation does not drop/recreate automatically | Plan explicit index migrations |
| Writes slow down after adding many indexes | Each write updates multiple indexes | Review and safely remove redundant indexes |
| Reactive API still slow | Suboptimal server query plan | Tune filters and indexes |

### 27.1. Ten-Step Slow Query Diagnostic Workflow

1. Identify the actual filter, sort, projection, and limit.
2. Verify the collection and physical BSON field names (especially `@Field`).
3. Inspect `getIndexes` instead of guessing from annotations.
4. Check index key order, unique, partial, sparse, TTL, and collation.
5. Run `explain("executionStats")` on representative data.
6. Inspect IXSCAN/COLLSCAN, keysExamined/docsExamined, SORT/FETCH.
7. Measure latency under matching limit and realistic load.
8. If indexes are wrong, adjust queries or propose a new index.
9. Measure write/storage cost after adding indexes.
10. Run regression tests and roll out incrementally.

## 28. Practice Exercises

### Exercise 1: Single-Field

Need to look up products by SKU without uniqueness. Declaration?

~~~java
@Indexed(name = "idx_products_sku")
private String sku;
~~~

**Explanation:** the annotation declares intent and still needs auto-index or migration to exist on MongoDB.

### Exercise 2: Per-Tenant Unique

SKUs may repeat across shop-a/shop-b, not within the same tenant. Which annotation?

~~~java
@CompoundIndex(
    name = "uk_tenant_sku",
    def = "{ 'tenant_id': 1, 'sku': 1 }",
    unique = true
)
~~~

**Answer:** compound unique on tenant+sku, not single-field unique on sku.

### Exercise 3: Two `@Indexed`

~~~java
@Indexed private String tenantId;
@Indexed private String status;
~~~

Do these two lines create a compound index `{tenantId:1,status:1}`?

**Answer:** No. They declare two separate single-field indexes.

### Exercise 4: Compound Filter and Sort

Queries frequently filter by tenant, active, and sort `updatedAt DESC`. Candidate index?

**Answer:** `{ tenant_id: 1, active: 1, updatedAt: -1 }`. Run explain to confirm effectiveness.

### Exercise 5: Sparse and Null

`optionalCode` has `@Indexed(sparse=true, unique=true)`. Can you state that documents with `optionalCode=null` are never indexed?

**Answer:** No. Sparse does not skip explicit null. Understand null vs. missing and consider partial unique.

### Exercise 6: Soft Delete

Require unique `displayCode` only when product is active. Appropriate index?

**Answer:** compound unique with `partialFilterExpression: {active:true}`; test inactive→active duplicate transitions.

### Exercise 7: TTL

Sessions store `expiresAt` as BSON Date. Clean up after that timestamp:

~~~java
@Indexed(expireAfterSeconds = 0)
private Instant expiresAt;
~~~

**Explanation:** TTL deletes asynchronously in the background without guaranteeing instant removal.

### Exercise 8: Expired Session

A session remains in the database 20 seconds after `expiresAt`. Should access be allowed?

**Answer:** No. The service must check `expiresAt` during authentication.

### Exercise 9: Text

Articles need searching across `title` and `body`, with `title` weighted higher?

**Answer:** `@TextIndexed` on both fields with appropriate weights; query via `TextCriteria`/`$text`; check language and tokenization.

### Exercise 10: Geospatial

Stores persist `GeoJsonPoint` in longitude/latitude order. Index for spherical `$near`?

**Answer:** `@GeoSpatialIndexed(type=GeoSpatialIndexType.GEO_2DSPHERE)`, verify 2dsphere index.

### Exercise 11: Hashed

Does a hashed index on `deviceId` guarantee `deviceId` uniqueness?

**Answer:** No. Hashed indexes do not replace unique constraints.

### Exercise 12: Wildcard

Products have dynamic attributes such as `ramGb`, `color`, `size`. When is a wildcard index helpful?

**Answer:** When querying many unpredictable fields under a metadata subtree, after measuring index size and checking if frequent fields deserve dedicated indexes.

### Exercise 13: Auto-Creation

An entity has index annotations, yet production `getIndexes` shows only `_id`. Why?

**Answer:** Index metadata was never materialized because `auto-index-creation` is off or migrations didn't run.

### Exercise 14: Changing Unique Option

Is changing `@Indexed(unique=false)` to `unique=true` enough to protect production?

**Answer:** No. You must audit existing duplicates, handle the old index, and migrate with exact keys/options.

### Exercise 15: Explain

An index exists, yet a query returning 20 documents shows a huge `totalDocsExamined`. How to investigate?

**Answer:** Inspect filter/sort/projection, key order, index options, and explain; measure before adding new indexes.

### Exercise 16: Collation

`Alice@example.com` and `alice@example.com` must count as duplicates. Is a default unique index always enough?

**Answer:** No. Implement normalization or compatible collation and test enforcement.

## 29. Production Checklist

- **Queries:** do real filters/sorts/limits justify each index?
- **Key order:** do compound indexes have optimal prefixes and sort directions?
- **Mapping:** do `@Field`/`@Id` resolve to the intended BSON field names?
- **Unique:** collection-wide or per-tenant?
- **Null/missing:** do optional fields need partial or sparse?
- **Partial:** do filters align with active/soft-delete policies?
- **TTL:** are fields BSON Date and is async cleanup accounted for?
- **Text:** are language, scoring, and text-search semantics appropriate?
- **Geo:** proper GeoJSON longitude/latitude, 2dsphere, and distance units?
- **Hashed:** avoided for range/sort or unique constraints?
- **Wildcard:** scoped to metadata subtree with monitored storage size?
- **Creation:** are annotations materialized via IndexResolver/auto-index/migrations?
- **Rollout:** legacy data, build cost, and index conflicts checked?
- **Runtime:** does `getIndexes` match expected keys and options?
- **Performance:** does explain show reduced keys/docs examined and improved latency?
- **Write load:** is write slowdown from index count acceptable?
- **Testing:** duplicate keys, partial transitions, TTL metadata, and mapping tested?
- **Reactive:** indexes provisioned before traffic and query plans verified?

## 30. Summary

1. **@Indexed** defines a single-field index; multiple separate `@Indexed` fields do not create a compound index.
2. **@CompoundIndex** defines ordered multi-field indexes, crucial for tenant+business keys and filter+sort shapes.
3. **Unique indexes** enforce constraints inside MongoDB; Java `exists` checks cannot prevent races.
4. **Sparse/partial indexes** alter which documents enter the index; mind null/missing semantics and unique scope.
5. **TTL indexes** remove data asynchronously and never replace expiration checks in business logic.
6. **@TextIndexed** powers term search, not arbitrary regex/substring matching.
7. **@GeoSpatialIndexed** powers spatial queries, requiring proper GeoJSON/2dsphere setup.
8. **@HashIndexed** fits equality/shard-key use cases, not uniqueness or ordered scans.
9. **@WildcardIndexed** supports dynamic fields, subject to size costs and query limits.
10. **Annotations do not guarantee indexes exist on the server**; ensure `auto-index-creation` or migrations run and verify `getIndexes`.
11. **IndexOperations/IndexResolver** provide explicit programmatic index management; plan production migrations carefully.
12. **Measure index effectiveness via workloads and explain**, never assuming code compilation guarantees speed.
13. **Imperative and reactive repositories share the same indexes**, while index provisioning must be managed independently.
14. **Integration tests against real MongoDB** must prove constraints, metadata/options, mapping, and query performance.

Mastering **@Indexed, @CompoundIndex, and specialized index annotations** helps **SPRING_DATA_MONGODB** services evolve from slow correct queries to evidence-backed index designs that safeguard invariants and evolve schemas safely.

### References

- [Spring Data MongoDB — Index Creation](https://docs.spring.io/spring-data/mongodb/reference/mongodb/mapping/mapping-index-management.html) — auto-index creation, index resolver, and annotations.
- [Spring Data MongoDB — @Indexed API](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/index/Indexed.html) — unique, sparse, TTL, and partial.
- [Spring Data MongoDB — @CompoundIndex API](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/index/CompoundIndex.html) — def, unique, partial filter, and index name.
- [MongoDB Manual — Indexes](https://www.mongodb.com/docs/manual/indexes/) — query planner, compound, text, geospatial, hashed, wildcard.
- [MongoDB Manual — TTL Indexes](https://www.mongodb.com/docs/manual/core/index-ttl/) — TTL constraints and background cleanup.
