# Single-Field Indexes, Compound Indexes, and Field Ordering

## 1. Why Can a Correct Query Still Be Very Slow?

In the **Indexes** chapter of **Spring Data MongoDB**, two queries that both return the exact same 20 products can have completely different execution costs:

~~~javascript
db.catalog_products.find({
  tenantId: "tenant-a",
  status: "ACTIVE"
})
.sort({ createdAt: -1, _id: 1 })
.limit(20);
~~~

If the collection only has a few dozen documents, MongoDB can search quickly even without a dedicated index. However, when it grows to millions of documents, the server may have to inspect a vast number of documents and perform a resource-intensive sort. An **index** is a data structure that helps MongoDB locate matching keys and, when the index structure is compatible, **return results in the requested order without needing a large blocking sort step**.

The issue does not stop at the question "is there an index or not?". An index that includes all the fields but has **the wrong field order** can still force the planner to read many keys, filter many documents, or sort again.

For example, the following indexes are not equivalent:

~~~javascript
// Single-field index
db.catalog_products.createIndex({ tenantId: 1 });

// Compound: tenant first, status second
db.catalog_products.createIndex({ tenantId: 1, status: 1 });

// Compound: status first, tenant second
db.catalog_products.createIndex({ status: 1, tenantId: 1 });

// Compound containing both filter conditions and display order
db.catalog_products.createIndex({
  tenantId: 1,
  status: 1,
  createdAt: -1,
  _id: 1
});
~~~

These compound indexes can have different value depending on the actual queries. In a multi-tenant system, queries almost always include `tenantId`, whereas `status` is sometimes optional; in that case, which field comes first becomes very important.

**Lesson objectives:** distinguish single-field and compound indexes, understand leftmost prefix, sort direction, the *Equality–Sort–Range* (ESR) guideline, declaring indexes in Spring Data MongoDB, inspecting `explain("executionStats")`, write cost trade-offs, and writing integration tests.

> Examples use Java 17+, Spring Boot 3.x, Spring Data MongoDB 4.x, and a compatible MongoDB version. The query planner, `explain` output formatting, and optimizations may vary by server version and topology. The ESR rule and prefix rule are **starting-point** design tools, not a guarantee that MongoDB will always pick the exact index we predict.

## 2. What Does an Index Do and What Does It Not Do?

A standard MongoDB B-tree index stores keys in a defined order. An index on `tenantId` helps locate documents for a specific tenant without necessarily scanning the entire collection:

~~~javascript
db.catalog_products.createIndex(
  { tenantId: 1 },
  { name: "idx_product_tenant" }
);
~~~

The notation `1` indicates **ascending** order for the field in the index; `-1` indicates **descending** order. With a **single-field** index, MongoDB can usually traverse the index in both forward and reverse directions to satisfy a simple sort. With **multiple fields**, the sign pattern of the fields involved in sorting is an important part of the design.

An index can help:

- Narrow the key range to scan for equality/range conditions when the index is suitable.
- Traverse keys in the requested order for certain forms of `sort`.
- Reduce the number of documents read if predicates and projections are supported by the index.
- Enforce uniqueness when defined as a **unique index**.

An index **does not automatically**:

- Make every query fast; MongoDB may choose a collection scan on small datasets or when a filter is not selective.
- Guarantee that all queries will use that index, even with `hint`.
- Create a consistent snapshot across pagination pages.
- Fix an incorrect tenant filter or wrong query semantics.
- Eliminate write costs; inserts/updates/deletes must maintain affected indexes.
- Make multi-document operations transactional.

A new collection already has a default `_id` index; there is no need to recreate a `{ _id: 1 }` index just because the entity has a Java `id` property.

## 3. Sample Data and Query Requirements

Suppose the `catalog_products` collection stores:

~~~json
{
  "_id": "p-101",
  "tenantId": "tenant-a",
  "sku": "BOTTLE-500",
  "display_name": "Water Bottle 500 ml",
  "status": "ACTIVE",
  "stock_qty": 12,
  "tags": ["outdoor", "premium"],
  "createdAt": { "$date": "2026-11-20T08:00:00Z" }
}
~~~

Common read APIs:

| Requirement | Filter | Sort | Returned data |
|---|---|---|---|
Get one product by ID | `_id = ?` | Not required | At most one |
Get products for a tenant | `tenantId = ?` | `createdAt DESC` | One page |
Get ACTIVE products for a tenant | `tenantId = ? AND status = ACTIVE` | `createdAt DESC, _id ASC` | One page |
Find SKU within a tenant | `tenantId = ? AND sku = ?` | None | At most one if a unique index exists |
Find stock of 5 or more | `tenantId = ? AND status = ACTIVE AND stock_qty >= 5` | `stock_qty ASC` or `createdAt DESC` | One page |
Find products with tag outdoor | `tenantId = ? AND tags = outdoor` | `createdAt DESC` | One page |

If the application has 100 tenants, and each tenant has vastly different product counts and statuses, the **selectivity** of `tenantId` and `status` also differs. Do not decide index order solely from field names; you must examine the actual query set, data distribution, and sorting.

### Spring Data Entity

**CatalogProduct.java**

~~~java
package com.example.catalog;

import java.time.Instant;
import java.util.List;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.mapping.MongoId;

@Document(collection = "catalog_products")
public record CatalogProduct(
        @MongoId(FieldType.STRING) String id,
        String tenantId,
        String sku,
        @Field("display_name") String name,
        String status,
        @Field("stock_qty") long stock,
        List<String> tags,
        Instant createdAt) {
}
~~~

`@MongoId(FieldType.STRING)` specifies that BSON `_id` is a String. `@Field` causes `name` to be stored as `display_name` and `stock` as `stock_qty`. Typed queries in `MongoTemplate` can use Java property names; the MongoDB shell and raw BSON must use **physical field names**.

Do not assume `@Document` creates all required indexes. Indexes must be intentionally declared and deployed, then verified on the database.

## 4. Single-Field Indexes

### 4.1. Single Equality Field

~~~javascript
db.catalog_products.createIndex(
  { status: 1 },
  { name: "idx_product_status" }
);

db.catalog_products.find({ status: "ACTIVE" });
~~~

This index can help when the status condition is sufficiently selective. However, if 95% of documents are ACTIVE, reading most of the collection via index + FETCH may not be cheaper than a collection scan. The query planner decides based on statistics/cost and server version.

If nearly every query filters by tenant, an index on `status` alone may be a weak choice compared to a compound index starting with `tenantId`. Do not automatically create an index for every entity property.

### 4.2. Single Range and Sort Field

~~~javascript
db.catalog_products.createIndex(
  { createdAt: -1 },
  { name: "idx_product_created_desc" }
);

db.catalog_products.find({}).sort({ createdAt: -1 }).limit(20);
~~~

A single-field index can be traversed in reverse, so `{ createdAt: -1 }` does not necessarily require a companion `{ createdAt: 1 }` index to support both single-field sort directions.

However, the query above can still return products from all tenants. **An index does not replace access control**: the `tenantId` filter must be present when data requires tenant isolation.

### 4.3. Built-in _id Index

~~~javascript
db.catalog_products.find({ _id: "p-101" });
~~~

A collection normally already has the unique `_id_` index. Use `findById`/`findOne` by ID along with tenant protection conditions when business logic requires it. In a multi-tenant application, having a unique `_id` does not entitle a user to read another tenant's ID; authorization is still required.

### 4.4. A Single-Field Index Does Not Replace a Compound Business Key

If the same tenant must not have two products with the same `sku`, a `{ sku: 1 }` index with `unique: true` will **prevent duplicate SKUs across the entire collection**, which may be wrong when two tenants are allowed to use the same SKU.

When uniqueness is tenant-scoped, see `{ tenantId: 1, sku: 1 }` in the compound index section below.

## 5. Compound Indexes and Leftmost Prefix

A compound index stores multiple fields in a fixed order. For example:

~~~javascript
db.catalog_products.createIndex(
  { tenantId: 1, status: 1, createdAt: -1, _id: 1 },
  { name: "idx_product_tenant_status_created_id" }
);
~~~

Intuitively, index keys are sorted first by `tenantId`, within each tenant by `status`, within each status by `createdAt` descending, and when `createdAt` values tie, by `_id` ascending.

Diagram:

~~~text
tenantId ASC
  └── status ASC
       └── createdAt DESC
            └── _id ASC

Example key entries:
tenant-a / ACTIVE  / 2026-11-20T10:00Z / p-001
tenant-a / ACTIVE  / 2026-11-20T10:00Z / p-002
tenant-a / ACTIVE  / 2026-11-20T09:00Z / p-003
tenant-a / PENDING / 2026-11-20T11:00Z / p-004
tenant-b / ACTIVE  / 2026-11-20T12:00Z / p-005
~~~

### 5.1. Leftmost Prefix

A compound index is usually most effective for conditions starting from its **leftmost prefix**:

| Filter | Prefix match level | Notes |
|---|---|---|
`{ tenantId: "tenant-a" }` | Has leading field | Can use the leading part of the index |
`{ tenantId: "tenant-a", status: "ACTIVE" }` | Has first two fields | Can narrow the key range better |
`{ tenantId: "tenant-a", status: "ACTIVE", createdAt: { $gte: t } }` | Has fields in order | Can combine equality and range on the next field |
`{ status: "ACTIVE" }` | Missing leading tenant field | Does not leverage the prefix like the rows above |
`{ createdAt: { $gte: t } }` | Missing tenant and status | Not a good target query for this index |
`{ tenantId: "tenant-a", createdAt: { $gte: t } }` | Missing status field in the middle | Can leverage tenant, but may not bound/sort well by createdAt |

**Do not state absolutely that a query missing the leading field "cannot use the index".** MongoDB may still select the index for a non-prefix condition, a broader scan, or another optimization strategy; the point is that **its ability to narrow the scan range and provide order** can be much worse. Use `explain` to verify.

### 5.2. Why Should tenantId Usually Come Before status?

In multi-tenant APIs, nearly every query includes `tenantId`. If you choose:

~~~javascript
{ status: 1, tenantId: 1, createdAt: -1, _id: 1 }
~~~

then a query with only tenant and **no status** no longer matches the leading prefix. An index with `tenantId` first is usually better suited for both "all statuses of a tenant" and "a specific status of a tenant".

However, if the workload **always** has equality on both tenant and status, the relative order between the two equality fields may yield roughly comparable narrowing for that single query. The final decision also depends on **other queries sharing the index, sorting, cardinality, and existing index prefixes**.

### 5.3. A Compound Index Does Not Optimize Every Field Combination

An index `{ tenantId: 1, status: 1, createdAt: -1, _id: 1 }` does not automatically optimize filtering `stock_qty >= 5`, because `stock_qty` is not an index key. MongoDB still has to check the condition on documents or use another strategy.

Adding every field to a single index increases index size and write cost, and **does not resolve the conflict between range and sort**. Design indexes around *query shapes* rather than "an index containing every field in the application".

## 6. Ascending/Descending Direction in Compound Indexes and Sort

With the index:

~~~javascript
{ tenantId: 1, status: 1, createdAt: -1, _id: 1 }
~~~

a common query is:

~~~javascript
db.catalog_products.find({
  tenantId: "tenant-a",
  status: "ACTIVE"
})
.sort({ createdAt: -1, _id: 1 })
.limit(20);
~~~

When both `tenantId` and `status` have **equality** conditions, the index keys belonging to a tenant/status pair are already ordered by `createdAt DESC, _id ASC`. Therefore, MongoDB can leverage the index order to return the result page without re-sorting the entire candidate set.

### 6.1. Reversing the Entire Sort Pattern

With two sort fields `createdAt` and `_id`:

| Sort after two equalities | Compatible with index scan direction? |
|---|---|
`{ createdAt: -1, _id: 1 }` | Yes, same sign pattern |
`{ createdAt: 1, _id: -1 }` | Can scan the entire pattern in **reverse** |
`{ createdAt: -1, _id: -1 }` | Not a full reversal of the defined pattern |
`{ createdAt: 1, _id: 1 }` | Not a full reversal of the defined pattern |

The "not a full reversal" rows do not mean MongoDB cannot serve the sort with **any index**; it may use a different index or a separate sort stage. When equalities are present, certain fixed sort keys or sort prefixes may create exceptions that require analyzing each query. The table illustrates the basic view of a **compound index's sign pattern**.

### 6.2. Missing Equality on status

~~~javascript
db.catalog_products.find({
  tenantId: "tenant-a"
})
.sort({ createdAt: -1, _id: 1 });
~~~

Because the index sorts by `status` **before** `createdAt`, ACTIVE and PENDING products of a tenant reside in separate key ranges. A single traversal in that index order **is not equivalent** to sorting all products in the tenant by createdAt.

If the "all statuses" screen is a primary query, an additional index may be needed:

~~~javascript
db.catalog_products.createIndex(
  { tenantId: 1, createdAt: -1, _id: 1 },
  { name: "idx_product_tenant_created_id" }
);
~~~

This is a trade-off: the additional index supports another query, but increases index maintenance cost. Do not create both just because an example shows two query shapes; use access statistics and `explain` to decide.

## 7. ESR: Equality – Sort – Range

The **ESR** rule is a heuristic for designing compound index field order:

1. **E (Equality):** fields typically compared for exact equality (`=`, and in many cases small `$in`).
2. **S (Sort):** fields that determine result ordering.
3. **R (Range):** fields using inequalities (`$gt`, `$gte`, `$lt`, `$lte`, etc.), and regex/ranges depending on form.

Example:

~~~javascript
db.catalog_products.find({
  tenantId: "tenant-a",
  status: "ACTIVE",
  stock_qty: { $gte: 5 }
})
.sort({ createdAt: -1, _id: 1 })
.limit(20);
~~~

An ESR candidate:

~~~javascript
db.catalog_products.createIndex(
  {
    tenantId: 1,
    status: 1,
    createdAt: -1,
    _id: 1,
    stock_qty: 1
  },
  { name: "idx_product_esr_created_stock" }
);
~~~

The first two equality fields select the tenant and status; the next sort fields enable ordered traversal; `stock_qty` at the end can be checked during the key scan, but **does not necessarily strongly narrow the scan range** before finding 20 documents with matching stock.

### 7.1. When a Range Is Highly Selective: Consider ERS

If only 0.01% of products have `stock_qty >= 50000`, putting the range before the sort can drastically reduce the number of keys scanned:

~~~javascript
db.catalog_products.createIndex(
  {
    tenantId: 1,
    status: 1,
    stock_qty: 1,
    createdAt: -1,
    _id: 1
  },
  { name: "idx_product_ers_stock_created" }
);
~~~

In exchange, because the `stock_qty` range appears before `createdAt`, the index **cannot provide a global sort by createdAt** across different stock values. The query planner may need to sort after filtering.

Therefore:

- **ESR** is often beneficial when avoiding a blocking sort is important and the first few rows are needed quickly.
- **ERS** can be beneficial when the range is extremely selective, shrinking the candidate set to the point where sorting the remainder is cheap.
- No single order is "right for every workload"; you must measure latency, keys/docs examined, sort memory, and match ratio.

### 7.2. Equality Does Not Mean Every $in Behaves Like a Single Value

An `$in` with a small list may be handled by the planner much like multiple equality ranges, sometimes supporting sorts in specific ways. With a large list, behavior can be closer to a range, and optimizations vary across MongoDB versions.

Therefore, do not write rules like "`$in` is **always** equality" or "**always** range" and apply them mechanically to compound indexes. An application allowing filtering over thousands of SKUs must be measured separately.

### 7.3. Do Not Force hint Without Justification

~~~javascript
db.catalog_products.find({
  tenantId: "tenant-a", status: "ACTIVE"
})
.hint("idx_product_tenant_status_created_id");
~~~

`hint` requests using a specific index, which is useful when experimenting or handling a clearly diagnosed case. In production, however, a hardcoded hint can degrade queries when data shifts, indexes are modified, or query shapes change. By default, let the planner choose and use `explain` to verify before adding a hint.

## 8. Indexes Supporting Sort, Range, and Pagination

### 8.1. Offset Pagination

~~~javascript
db.catalog_products.find({
  tenantId: "tenant-a", status: "ACTIVE"
})
.sort({ createdAt: -1, _id: 1 })
.skip(10000)
.limit(20);
~~~

A suitable index avoids re-sorting a large set, but `skip(10000)` may still have to **traverse and skip** many keys. An index does not make arbitrary offset depths constant-cost.

### 8.2. Keyset Pagination with Multi-Field Sort

Suppose the previous page ended at:

~~~text
lastCreatedAt = 2026-11-20T08:00:00Z
lastId = "p-101"
sort = { createdAt: -1, _id: 1 }
~~~

To fetch documents positioned **after the cursor** in this exact order:

~~~javascript
db.catalog_products.find({
  tenantId: "tenant-a",
  status: "ACTIVE",
  $or: [
    { createdAt: { $lt: ISODate("2026-11-20T08:00:00Z") } },
    {
      createdAt: ISODate("2026-11-20T08:00:00Z"),
      _id: { $gt: "p-101" }
    }
  ]
})
.sort({ createdAt: -1, _id: 1 })
.limit(20);
~~~

Explanation of the two branches:

1. Products **older** by `createdAt` come after in a descending sort.
2. If timestamps tie, **larger** IDs by `_id ASC` come after the cursor.

The index `{ tenantId: 1, status: 1, createdAt: -1, _id: 1 }` is a suitable candidate to evaluate for this pagination style. However, the actual efficiency of the `$or` filter, bounds, and read order must be verified with `explain`.

**Note:** keyset pagination is more stable than offset when new data is inserted at the top of the list, but it **does not automatically create a transactional snapshot**. If a document changes `createdAt` or is deleted, results across multiple pages remain affected by concurrent updates. The cursor must carry all sort keys and tenant scope information; validate it and never trust client-tampered cursor values.

## 9. Unique Compound Indexes and Business Keys

Suppose the system rule is:

> Each tenant must not have two products with the same normalized SKU, but two different tenants can use the same SKU.

Appropriate index:

~~~javascript
db.catalog_products.createIndex(
  { tenantId: 1, sku: 1 },
  { unique: true, name: "uq_product_tenant_sku" }
);
~~~

| tenantId | sku | Allowed to coexist? |
|---|---|---|
| tenant-a | BOTTLE-500 | Yes |
| tenant-a | BOTTLE-500 (second document) | No |
| tenant-b | BOTTLE-500 | Yes |

A **unique index** is the database mechanism that protects uniqueness under concurrent writes. The `existsByTenantIdAndSku(...)` then `save(...)` pattern is not equivalent: two requests can both observe that the SKU does not exist yet before either creates the document.

### 9.1. Uniqueness Scope Depends on Null/Missing Data

A compound unique index compares **combinations of index key values**. Missing or null fields follow specific indexing rules; if documents without a `sku` are allowed, verify whether the design can hit unexpected duplicate keys.

Options:

- Require `tenantId` and `sku` via schema validation/application validation.
- Normalize SKUs into a consistent format before writing.
- When uniqueness applies only to a conditional subset of documents, consider a **partial unique index** with an appropriate `partialFilterExpression`.
- If case-insensitive SKU comparison is required, define a consistent **collation** for the index and query rules.

Do not merely put `unique: true` on the entity's `sku` field if the true requirement is uniqueness per (`tenantId`, `sku`).

### 9.2. Creating an Index on a Populated Collection

MongoDB may reject creating a unique index if existing data already has duplicate keys. A production procedure needs:

1. Inventory duplicates and non-conforming data.
2. Define a policy to merge/resolve duplicates.
3. Check resources for the index build process.
4. Deploy the index via a controlled migration/operation.
5. Verify the index exists and the application handles duplicate-key exceptions according to contract.

Do not fix duplicate data by arbitrarily deleting documents just to make the index build pass; a clear business decision is required.

## 10. Compound Indexes with Arrays: Multikey and Limits

`tags` in `CatalogProduct` is `List<String>`, stored as a BSON array. The index:

~~~javascript
db.catalog_products.createIndex(
  { tenantId: 1, tags: 1 },
  { name: "idx_product_tenant_tags" }
);
~~~

can become a **multikey index** because `tags` is an array. Array elements contribute to indexing, helping queries such as:

~~~javascript
db.catalog_products.find({
  tenantId: "tenant-a",
  tags: "outdoor"
});
~~~

However, multikey indexes have important constraints:

- Do not arbitrarily create a compound index on **two fields containing independent arrays** in the same document. MongoDB has a rule disallowing a compound multikey index with multiple independent array paths (*parallel arrays*).
- Indexing large arrays can generate many index entries, affecting index size, memory, and update cost.
- `$elemMatch` is sometimes needed to require multiple conditions on the same array element document and can affect how the planner combines index bounds.
- Multikey indexes have specific limitations with covered queries, sorting, and certain field paths; do not assume every array query is "covered".

If using `{ tenantId: 1, tags: 1, createdAt: -1 }`, measure the query with actual tag filters and sorting; seeing `IXSCAN` alone is not enough to conclude there is no blocking sort.

**An index does not change array semantics.** For example, two conditions `variants.color = RED` and `variants.quantity >= 10` on two dot paths can match on **two different elements**; if they must match the same variant, `$elemMatch` is needed regardless of whether an index exists.

## 11. Declaring Indexes with Annotations in Spring Data MongoDB

Spring Data MongoDB supports index metadata on entities via annotations such as `@Indexed`, `@CompoundIndex`, and `@CompoundIndexes`.

### 11.1. @Indexed for a Single Field

For example, if a screen frequently searches products by `sku` in a **single-tenant collection**, or business needs only require an index on SKU:

~~~java
import org.springframework.data.mongodb.core.index.Indexed;

@Indexed(name = "idx_product_sku")
private String sku;
~~~

This snippet illustrates a field in a **class entity**, not part of the `CatalogProduct` record defined in section 3. In a multi-tenant application using unique (`tenantId`, `sku`), do not automatically add a single-field SKU index if the query workload does not need it.

### 11.2. @CompoundIndex on an Entity

The annotation can be placed on the entity:

~~~java
import org.springframework.data.mongodb.core.index.CompoundIndex;

@CompoundIndex(
        name = "idx_product_tenant_status_created_id",
        def = "{ 'tenantId': 1, 'status': 1, 'createdAt': -1, '_id': 1 }")
@Document(collection = "catalog_products")
public class IndexedProduct {
    // Define corresponding fields, e.g. tenantId, status, createdAt, id.
}
~~~

This is an **annotation metadata illustration**, not a complete entity to copy and run standalone. In a real project, use the actual entity name and declare all schema fields. `@CompoundIndex` is placed at the class level, not on individual fields.

If multiple compound indexes are needed:

~~~java
@CompoundIndexes({
    @CompoundIndex(
            name = "idx_product_tenant_status_created_id",
            def = "{ 'tenantId': 1, 'status': 1, 'createdAt': -1, '_id': 1 }"),
    @CompoundIndex(
            name = "uq_product_tenant_sku",
            def = "{ 'tenantId': 1, 'sku': 1 }",
            unique = true)
})
~~~

This is an annotation fragment placed on the **same entity class** and requires importing both `CompoundIndexes` and `CompoundIndex`. In versions supporting repeatable annotations, the alternative syntax can also work. Naming rules and property mapping inside `def` must be verified against the entity/version, especially with `@Field` and nested paths.

### 11.3. Annotations Do Not Mean Indexes Are Created Immediately

Since Spring Data MongoDB 3.x, **automatic index creation from annotations is disabled by default**. In Spring Boot, the corresponding configuration may be:

~~~yaml
spring:
  data:
    mongodb:
      auto-index-creation: true
~~~

This is an **illustrative configuration** when a project decides to allow automatic index creation. Do not enable it indiscriminately in production without reviewing the migration process, data volume, duplicate keys, index creation permissions, and deployment timing. Having an annotation in source code **does not confirm the index exists on the server**.

In production, an explicit index management process with change verification and a planned rollback is usually required; do not treat repository initialization as a complete migration tool.

## 12. Creating and Inspecting Indexes with MongoTemplate

Spring Data provides `IndexOperations` to work with an entity/collection's indexes. Example of a controlled index management component:

**CatalogIndexProvisioner.java**

~~~java
package com.example.catalog;

import java.util.List;
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.index.Index;
import org.springframework.data.mongodb.core.index.IndexInfo;
import org.springframework.stereotype.Component;

@Component
public class CatalogIndexProvisioner {
    private final MongoTemplate mongo;

    public CatalogIndexProvisioner(MongoTemplate mongo) {
        this.mongo = mongo;
    }

    public void ensureReadIndex() {
        Index index = new Index()
                .on("tenantId", Sort.Direction.ASC)
                .on("status", Sort.Direction.ASC)
                .on("createdAt", Sort.Direction.DESC)
                .on("_id", Sort.Direction.ASC)
                .named("idx_product_tenant_status_created_id");

        mongo.indexOps(CatalogProduct.class).ensureIndex(index);
    }

    public List<IndexInfo> listIndexes() {
        return mongo.indexOps(CatalogProduct.class).getIndexInfo();
    }
}
~~~

`indexOps(CatalogProduct.class)` retrieves the corresponding collection metadata. `ensureIndex(...)` requests creating the index if it does not yet exist with a compatible definition; if an index with the same name already exists but with **different keys/options**, MongoDB may report a conflict instead of silently modifying the index.

**Do not run ensureIndex uncontrolled on every HTTP request.** Use a migration/deployment step or a managed initialization process; building an index on a large collection has real cost and requires appropriate permissions.

### 12.1. Verifying Actual Indexes on MongoDB

In mongosh:

~~~javascript
db.catalog_products.getIndexes();
~~~

Illustrative output:

~~~json
[
  { "v": 2, "key": { "_id": 1 }, "name": "_id_" },
  {
    "v": 2,
    "key": {
      "tenantId": 1,
      "status": 1,
      "createdAt": -1,
      "_id": 1
    },
    "name": "idx_product_tenant_status_created_id"
  }
]
~~~

Fields like `v` and server metadata may differ by version; do not compare the entire JSON output literally. Verify **key order, direction, name, and options** such as unique/partial/collation.

### 12.2. IndexOptions Are Part of the Definition

Two indexes with the same key pattern but different `unique`, `partialFilterExpression`, or `collation` do not necessarily substitute for one another. If options change, the migration process may need to create a new index, switch reads over, and then clean up the old index when safe.

Do not casually run `dropIndex` in production just to test a hypothesis. An index may be serving other APIs; you must inventory the workload and have a rollback plan.

## 13. Writing Typed Queries and Sorts in MongoTemplate

The following service uses the index designed in section 5. `Query` uses Java property names, not raw BSON paths for `name` and `stock`.

**CatalogSearchService.java**

~~~java
package com.example.catalog;

import java.time.Instant;
import java.util.List;
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.stereotype.Service;

@Service
public class CatalogSearchService {
    private final MongoTemplate mongo;

    public CatalogSearchService(MongoTemplate mongo) {
        this.mongo = mongo;
    }

    public List<CatalogProduct> newestActive(
            String authenticatedTenantId, int limit) {
        if (authenticatedTenantId == null
                || authenticatedTenantId.isBlank()
                || limit < 1 || limit > 100) {
            throw new IllegalArgumentException("Invalid filter or limit");
        }

        Query query = Query.query(
                Criteria.where("tenantId").is(authenticatedTenantId)
                        .and("status").is("ACTIVE"));

        query.with(Sort.by(
                Sort.Order.desc("createdAt"),
                Sort.Order.asc("id")));
        query.limit(limit);

        return mongo.find(query, CatalogProduct.class);
    }

    public List<CatalogProduct> newestWithStock(
            String authenticatedTenantId, long minimumStock, int limit) {
        if (minimumStock < 0) {
            throw new IllegalArgumentException("Invalid minimumStock");
        }
        if (authenticatedTenantId == null
                || authenticatedTenantId.isBlank()
                || limit < 1 || limit > 100) {
            throw new IllegalArgumentException("Invalid filter or limit");
        }

        Query query = Query.query(
                Criteria.where("tenantId").is(authenticatedTenantId)
                        .and("status").is("ACTIVE")
                        .and("stock").gte(minimumStock));
        query.with(Sort.by(
                Sort.Order.desc("createdAt"),
                Sort.Order.asc("id")));
        query.limit(limit);
        return mongo.find(query, CatalogProduct.class);
    }
}
~~~

With `CatalogProduct.class`, `Criteria.where("stock")` is mapped to BSON `stock_qty`; `Sort.Order.asc("id")` is mapped to `_id: 1`. However, fields with `@Field`, nested properties, or complex aliases should be verified via command capture/integration tests, not merely by reading Java method names.

### 13.1. Expected BSON

~~~javascript
db.catalog_products.find({
  tenantId: "tenant-a",
  status: "ACTIVE",
  stock_qty: { $gte: 5 }
})
.sort({ createdAt: -1, _id: 1 })
.limit(20);
~~~

The index `{ tenantId: 1, status: 1, createdAt: -1, _id: 1 }` can provide the sort order, but must additionally filter `stock_qty` on candidate documents. If many products have stock below 5, it may have to scan many keys before collecting 20 matching products. This is when the ESR/ERS indexes from section 7 should be compared.

## 14. explain("executionStats"): Verify Instead of Guessing

An index that **exists** is not guaranteed to be **used** by the query planner, and an index that **is used** is not guaranteed to make the query fast. Inspect it:

~~~javascript
db.catalog_products.find({
  tenantId: "tenant-a",
  status: "ACTIVE"
})
.sort({ createdAt: -1, _id: 1 })
.limit(20)
.explain("executionStats");
~~~

### 14.1. Fields to Read

| Field / Info | Meaning | Interpretation |
|---|---|---|
`queryPlanner.winningPlan` | Selected plan | Look for index scan/collection scan/sort stages according to version format |
`IXSCAN` or equivalent index scan plan | Accessed via index | Can be good, but check the number of keys/documents examined |
`COLLSCAN` | Collection scan | Sometimes reasonable for small collections or broad filters |
`SORT` / blocking sort | Separate sort step | Can consume significant memory with many candidates |
`executionStats.totalKeysExamined` | Number of index keys scanned | Compare against result count and selectivity |
`executionStats.totalDocsExamined` | Number of documents examined | Much higher than returned docs may indicate an insufficiently selective index |
`executionStats.nReturned` | Number of documents returned | Use as denominator when comparing |
`executionStats.executionTimeMillis` | Time for the explain run | Not production p95/p99 latency |

MongoDB may display plans differently between the classic engine and Slot-Based Execution (SBE); do not write tests expecting a single `winningPlan.inputStage...` JSON path across all versions. Observe the general semantics and metrics.

### 14.2. Comparing Three Important Queries

**A — Two equalities and matching sort:**

~~~javascript
db.catalog_products.find({
  tenantId: "tenant-a", status: "ACTIVE"
})
.sort({ createdAt: -1, _id: 1 })
.limit(20).explain("executionStats");
~~~

**B — Omitting equality on status while keeping sort:**

~~~javascript
db.catalog_products.find({
  tenantId: "tenant-a"
})
.sort({ createdAt: -1, _id: 1 })
.limit(20).explain("executionStats");
~~~

**C — Including stock range with sort:**

~~~javascript
db.catalog_products.find({
  tenantId: "tenant-a",
  status: "ACTIVE",
  stock_qty: { $gte: 1000 }
})
.sort({ createdAt: -1, _id: 1 })
.limit(20).explain("executionStats");
~~~

Compare keys/docs examined and the presence of a sort stage. The plan for C can differ significantly between data where high stock is extremely rare and data where high stock is common.

### 14.3. Explain Is Not the Only Benchmark

- A single explain on 5 test documents is not enough to conclude production indexing.
- Cache, warm-up, concurrency, write traffic, and tenant distribution can affect results.
- Low keys examined is not enough: fetching large documents or large sort memory can still be expensive.
- Index creation and write latency must be measured alongside read latency.
- When comparing, keep the query shape, representative data, and read preference/collation consistent.

## 15. Covered Queries and Projections

A query is **covered by an index** when MongoDB can return the requested fields from the index without reading the source documents, under appropriate conditions. With:

~~~javascript
db.catalog_products.createIndex(
  { tenantId: 1, status: 1, createdAt: -1, _id: 1 },
  { name: "idx_product_tenant_status_created_id" }
);
~~~

the query:

~~~javascript
db.catalog_products.find(
  { tenantId: "tenant-a", status: "ACTIVE" },
  { _id: 1, createdAt: 1 }
)
.sort({ createdAt: -1, _id: 1 });
~~~

can be a **covered query** candidate because all filter, sort, and projection fields are in the index key pattern. In a suitable plan, `totalDocsExamined` can be **0** and the plan reflects projection from the index.

Conversely:

~~~javascript
db.catalog_products.find(
  { tenantId: "tenant-a", status: "ACTIVE" },
  { _id: 1, display_name: 1 }
);
~~~

requests `display_name`, which **is not in the index**, so MongoDB usually must fetch the document to return the name. Do not add every display field to a compound index just to achieve a covered query if the index becomes too wide and write cost outweighs the benefit.

With arrays/multikey, missing fields, collation, and special projections, check the covered query limitations of your MongoDB version. `totalDocsExamined = 0` in explain is a useful signal, but must be cross-checked against actual results and the specific plan.

## 16. Collation, Null, and Data Types: Right Keys Alone Do Not Guarantee Right Semantics

### 16.1. Index and Query Collation

If products are searched by SKU or name case-insensitively, a consistent policy is required. An index created with a specific collation may not serve string comparisons using a **different collation** well.

Example:

~~~javascript
db.catalog_products.createIndex(
  { tenantId: 1, sku: 1 },
  {
    name: "idx_tenant_sku_ci",
    collation: { locale: "en", strength: 2 }
  }
);
~~~

To use the same semantics:

~~~javascript
db.catalog_products.find({
  tenantId: "tenant-a",
  sku: "bottle-500"
}).collation({ locale: "en", strength: 2 });
~~~

`strength: 2` typically supports case-insensitive matching in the selected collation; diacritic/Unicode and other locale rules must be reviewed against actual data. Do not assume a collation chosen for `name` works properly for SKU codes or all languages.

### 16.2. Null/Missing Fields

MongoDB indexes values according to BSON rules; a `{ field: null }` condition has semantics involving both null and missing fields in equality queries. With unique indexes, null/missing also affect uniqueness keys.

If business logic requires distinguishing "no SKU", "null SKU", and "empty SKU", use schema validation and explicit queries—do not rely on indexes to define business semantics automatically.

### 16.3. Mixed BSON Types

`stock_qty` should consistently store numeric types. If historical documents store String `"12"` or null, the index can still exist, but range comparisons and mapping to Java `long` will not behave as expected. Run a migration and test with raw BSON; an index does not coerce legacy data types to the standard.

## 17. Index Cost: Faster Reads, Heavier Writes

Every additional index consumes resources:

| Cost | Why does it happen? | How to control |
|---|---|---|
Disk space | Additional key structures | Keep index count intentional; inspect `$indexStats` |
Memory/cache | Indexes compete with data for cache | Monitor working set |
Insert | Write document and update affected indexes | Benchmark import speed |
Update | Indexed field changes → update index | Avoid unnecessarily wide indexes |
Delete | Must remove corresponding entries | Measure write workload |
Index build | Can consume CPU/I/O/time | Schedule and monitor deployments |
Low selectivity | Overly broad index scan | Measure `keysExamined`/`docsExamined` |
Long compound index | Many keys and complex options | Design to match query shapes |

There is no fixed percentage like "each index slows inserts by X%". The cost depends on document size, field count, cardinality, hardware, and workload.

### 17.1. Inventorying Unused Indexes

MongoDB provides `$indexStats` to observe index usage statistics within the scope provided by the server:

~~~javascript
db.catalog_products.aggregate([
  { $indexStats: {} }
]);
~~~

However, metrics have a server-dependent window/lifetime and can reset due to restarts, rebuilds, or administrative events. **Do not drop an index just because usage counts appear low at one point in time.** Cross-check with weekend batch jobs, monthly reports, maintenance tasks, and other consumers.

### 17.2. Prefix-Redundant Indexes

If you already have:

~~~javascript
{ tenantId: 1, status: 1, createdAt: -1, _id: 1 }
~~~

then `{ tenantId: 1, status: 1 }` may become **redundant** for certain prefix equality queries. However, deciding to drop it depends on index size, other queries, uniqueness, sparse/partial/collation options, and planner behavior.

Do not remove an index with a **unique constraint** just because a longer non-unique index shares the same prefix: a unique constraint is an independent business invariant.

## 18. Integration Testing Against Real MongoDB

Mocking `MongoTemplate` only verifies that code called a method; it does not prove that the index was actually created, the key order is right, or the planner uses the index. Integration tests against real MongoDB (for example, Testcontainers) are needed. In Spring Boot 3.x, `@DataMongoTest` configures the MongoDB test slice but **does not provide a server by itself**.

### 18.1. Seeding Data and Verifying Sort Results

**CatalogIndexIntegrationTest.java**

~~~java
package com.example.catalog;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Instant;
import java.util.List;
import org.bson.Document;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.context.annotation.Import;
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.index.Index;
import org.springframework.data.mongodb.core.query.Query;

@DataMongoTest
@Import(CatalogSearchService.class)
class CatalogIndexIntegrationTest {
    @Autowired MongoTemplate mongo;
    @Autowired CatalogSearchService search;

    private CatalogProduct product(
            String id, String tenant, String status,
            long stock, String time) {
        return new CatalogProduct(
                id, tenant, "SKU-" + id, "Product " + id,
                status, stock, List.of("outdoor"),
                Instant.parse(time));
    }

    @BeforeEach
    void prepare() {
        // Run only on an isolated test database.
        mongo.dropCollection(CatalogProduct.class);
        mongo.indexOps(CatalogProduct.class).ensureIndex(
                new Index()
                        .on("tenantId", Sort.Direction.ASC)
                        .on("status", Sort.Direction.ASC)
                        .on("createdAt", Sort.Direction.DESC)
                        .on("_id", Sort.Direction.ASC)
                        .named("idx_product_tenant_status_created_id"));

        mongo.insert(List.of(
                product("a-1", "tenant-a", "ACTIVE", 12,
                        "2026-11-20T10:00:00Z"),
                product("a-2", "tenant-a", "ACTIVE", 3,
                        "2026-11-20T10:00:00Z"),
                product("a-3", "tenant-a", "ACTIVE", 9,
                        "2026-11-20T09:00:00Z"),
                product("a-4", "tenant-a", "PENDING", 50,
                        "2026-11-20T11:00:00Z"),
                product("b-1", "tenant-b", "ACTIVE", 100,
                        "2026-11-20T12:00:00Z")
        ), CatalogProduct.class);
    }

    @Test
    void newestActiveHasStableOrderAndTenantIsolation() {
        List<CatalogProduct> rows = search.newestActive("tenant-a", 20);
        assertThat(rows).extracting(CatalogProduct::id)
                .containsExactly("a-1", "a-2", "a-3");
    }

    @Test
    void stockFilterUsesJavaPropertyButStoredFieldIsBsonAlias() {
        List<CatalogProduct> rows =
                search.newestWithStock("tenant-a", 5, 20);
        assertThat(rows).extracting(CatalogProduct::id)
                .containsExactly("a-1", "a-3");

        Document raw = mongo.getCollection("catalog_products")
                .find(new Document("_id", "a-1")).first();
        assertThat(raw).isNotNull();
        assertThat(raw.get("stock_qty")).isInstanceOf(Number.class);
        assertThat(raw.containsKey("stock")).isFalse();
        assertThat(raw.containsKey("display_name")).isTrue();
    }

    @Test
    void compoundIndexKeyOrderIsExactlyAsDesigned() {
        Document actual = null;
        for (Document index :
                mongo.getCollection("catalog_products").listIndexes()) {
            if ("idx_product_tenant_status_created_id"
                    .equals(index.getString("name"))) {
                actual = index;
                break;
            }
        }
        assertThat(actual).isNotNull();

        Document key = actual.get("key", Document.class);
        assertThat(key).isNotNull();
        assertThat(key.keySet()).containsExactly(
                "tenantId", "status", "createdAt", "_id");
        assertThat(((Number) key.get("tenantId")).intValue()).isEqualTo(1);
        assertThat(((Number) key.get("status")).intValue()).isEqualTo(1);
        assertThat(((Number) key.get("createdAt")).intValue()).isEqualTo(-1);
        assertThat(((Number) key.get("_id")).intValue()).isEqualTo(1);
    }
}
~~~

**Why does the test not strictly assert `IXSCAN`?** With only five documents, the query planner may reasonably choose `COLLSCAN`. Tests should verify **correct index definitions** and **correct query results**; performance tests must use representative datasets and separate criteria.

The test also does not prove that this index is optimal for every query adding a `stock` range. That is the benchmark problem in section 14.

### 18.2. Negative and Edge-Case Tests to Add

| Test case | Expectation |
|---|---|
Query `tenantId` only | Inspect explain and index selection |
Query tenant + status + sort | Verify key order and ability to avoid blocking sort |
Query tenant without status, still sort createdAt | Detect poor support from sort prefix |
Reverse entire sort pattern | Verify index traversal works in reverse |
Incompatible mixed sort | Observe planner using another index or `SORT` |
Add highly selective stock range | Compare ESR vs. ERS |
Unique (`tenantId`, `sku`) and duplicate insert | MongoDB rejects duplicate document |
Two tenants with same SKU | Allowed if unique key is properly scoped |
`tags` is an array | Verify multikey index and filter |
Java name `stock` differs from BSON `stock_qty` | Typed query still filters accurately |
Same index name with different keys/options | Migration reports conflict instead of silently altering |
Multiple tests running in parallel | Do not collide on shared database/collection |

### 18.3. Capturing Commands and Explain

To inspect the actual BSON query generated by `MongoTemplate`, use the MongoDB Java Driver's `CommandListener` with `CommandStartedEvent` in tests. Verify the `tenantId`, `status`, `stock_qty` filter and `createdAt`/`_id` sort.

In the MongoDB shell, run the same filter/sort with `explain("executionStats")`. The Java driver also provides `FindIterable.explain(...)` in supported versions; it can be used in **diagnostic tests**, but do not put explain into normal request paths.

Do not enable production command logging in modes that record customer data or tenant IDs without proper masking/retention policies.

## 19. A Practical Index Selection Workflow

A repeatable design process:

~~~mermaid
flowchart TD
    A["Collect query shapes and frequencies"] --> B["Record equality, sort, range, projection"]
    B --> C["Check existing indexes"]
    C --> D["Choose prefix/ESR or ERS candidates"]
    D --> E["Create index in test environment"]
    E --> F["Explain on representative data"]
    F --> G{"Correct results and target cost met?"}
    G -->|"No"| H["Adjust filter, schema, or index"]
    H --> D
    G -->|"Yes"| I["Measure read + write workload"]
    I --> J["Deploy via controlled migration"]
    J --> K["Monitor latency, index size, regressions"]
~~~

Follow in order:

1. **Record the query shape**, including mandatory tenant/authorization filters, full sort, limit, and projection.
2. **Profile the data**: tenant distribution, ACTIVE ratio, document counts across stock ranges, array lengths.
3. **Inventory existing indexes**: `getIndexes()`/`IndexOperations.getIndexInfo()`.
4. **Propose minimal candidate indexes**, avoiding prefix duplication without benefit.
5. **Preserve query semantics first**, then measure performance. Do not alter filter logic just to make an index look "clean".
6. **Run explain** on representative queries, including tenants of vastly different sizes.
7. **Measure read/write trade-offs**, not just latency of a single query.
8. **Deploy in a managed way**: check unique conflicts, naming, and collation.
9. **Monitor post-deployment** and have a plan to handle regressions.

An index is not an immutable property of an entity; it is a **workload-dependent physical decision** and must be reviewed as traffic and query patterns evolve.

## 20. Common Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
Assuming any index containing the fields is enough | Fails to leverage prefix or sort | Check field order |
Creating `{ status, tenantId }` when many queries only filter tenant | Prefix does not match primary query | Prioritize tenant first when workload fits |
Thinking `-1` is always faster than `1` | Creates unnecessary duplicate indexes | Understand forward/reverse traversal, especially compound |
Sorting `createdAt` when `status` between tenant and createdAt has no equality | May require a blocking SORT | Add an index matching the status-less query if worthwhile |
Applying ESR regardless of selectivity | Scans many keys to find few range-matching docs | Compare ESR/ERS using explain |
Assuming every `$in` behaves like scalar equality | Wrong planner/sort predictions | Measure by `$in` size and server version |
Seeing `IXSCAN` and declaring it fast | High keys/docs examined or SORT | Read executionStats and latency |
Thinking `COLLSCAN` is always wrong | Over-optimizing small collections | Evaluate actual cost |
Adding indexes to every property | Slow writes, wasted disk/cache | Choose by query shape |
Assuming annotations auto-create indexes on every deploy | Index missing on server | Check auto-index config and migrations |
Renaming/changing options and calling ensureIndex | May conflict instead of migrating | Manage index changes explicitly |
Forgetting `@Field` when writing raw BSON | Index on a field with no data | Use actual stored name, inspect raw BSON |
Collection-wide unique index instead of tenant+SKU | Blocks valid SKUs in other tenants | Make business key unique per scope |
Ignoring null/missing in unique indexes | Unexpected index build/insert failures | Use schema validation or partial indexes |
Compound index with multiple independent arrays | Violates multikey constraints | Redesign index or schema |
Expecting covered queries when projecting non-indexed fields | Must FETCH documents | Check filter/sort/projection fields |
Deep skip despite having an index | Scans and discards many keys | Consider keyset pagination |
Testing indexes on only 5 documents | Planner does not represent production | Benchmark on large datasets |
Ignoring write cost when adding indexes | Slow imports/updates | Measure write throughput and latency |

## 21. Practice Exercises

**Exercise 1 — Single-field index.** Create `{ tenantId: 1 }` and `{ createdAt: -1 }`. Write three different queries and use explain to observe when an index helps. Test sorting `createdAt ASC` via reverse traversal of the single-field index.

**Exercise 2 — Leftmost prefix.** Create `{ tenantId: 1, status: 1, createdAt: -1, _id: 1 }`. Compare tenant-only, tenant + status, and status-only queries. Record keys/docs examined on a sufficiently large dataset.

**Exercise 3 — Sort direction.** With both tenant/status equalities, test sorting (`createdAt DESC, _id ASC`), reversing the whole pattern, and flipping only one sign. Observe presence/absence of `SORT` in explain.

**Exercise 4 — ESR/ERS.** Query tenant + status + `stock_qty >= 1000` sorted by newest. Create both ESR and ERS candidate indexes; vary the proportion of high-stock products and measure keys scanned and latency.

**Exercise 5 — @Field.** Keep Java property `stock` while storing BSON `stock_qty`. Build a typed query with `MongoTemplate` and inspect the raw document. Create an index using the right BSON field name.

**Exercise 6 — Per-tenant unique.** Create a unique `{ tenantId: 1, sku: 1 }` index. Insert two tenants with the same SKU successfully, and verify two documents with the same tenant+SKU fail. Test the framework's duplicate-key exception.

**Exercise 7 — Offset and keyset.** Seed multiple documents sharing the same `createdAt`; use `_id ASC` as tie-breaker. Compare `skip(10000)` with a two-field cursor and verify no documents are lost on a fixed dataset.

**Exercise 8 — Multikey.** Create `{ tenantId: 1, tags: 1 }` and filter by tag `outdoor`. Then attempt to design an index across two independent arrays and explain the parallel arrays constraint.

**Exercise 9 — Covered query.** Project only `_id` and `createdAt` for tenant/status and check `totalDocsExamined`. Then add `display_name` to the projection and analyze why a FETCH may become necessary.

**Exercise 10 — Annotations and lifecycle.** Declare `@CompoundIndex` and test auto-index creation in a test environment. Disable it and use `indexOps.ensureIndex`, verifying `getIndexes()` key order and options.

**Exercise 11 — Collation.** Create a tenant+SKU index with a specific collation. Query with and without the matching collation; compare both results and explain output. Confirm SKU comparison rules against business requirements.

**Exercise 12 — Performance testing.** Seed tens or hundreds of thousands of documents in an isolated test database. Measure p50/p95 reads, insert rate, indexed-field update cost, and index sizes before and after. Select the minimal set of indexes needed for the workload.

## 22. Key Takeaways

**Single-field indexes** fit queries/sorts primarily using one field; **compound indexes** store multiple fields in a **meaningful order**. For compound indexes, understand **leftmost prefix**, forward/reverse traversal of **multi-field sort patterns**, and the **Equality–Sort–Range** design guideline as a starting point—not a universal solution for every query.

In **Spring Data MongoDB**, indexes can be declared with `@Indexed`/`@CompoundIndex` or created via `MongoTemplate.indexOps(...).ensureIndex(...)`. However, **the index must actually exist on MongoDB**, BSON field names must match `@Field`, and production index changes must be managed as migrations. Unique indexes protect business keys; multikey, collation, partial/sparse, and null/missing values each carry distinct constraints.

When optimizing, **always start from query shapes and correctness**, then verify with `explain("executionStats")`, keys/documents examined, sort stages, and benchmarks on representative data. Measure **write costs and index size** as well. The best indexing strategy is not the longest index or the most indexes, but the minimal set that satisfies the workload, tenant security, and performance goals.
