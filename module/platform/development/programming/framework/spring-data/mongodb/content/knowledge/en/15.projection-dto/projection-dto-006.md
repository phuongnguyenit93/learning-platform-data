# Including or Excluding Returned Fields and the _id Exception

## 1. Context and Objectives

A MongoDB document may contain many fields serving different business workflows. A product list screen typically needs only name, price, and product SKU; a detail page may need description, inventory, supplier, and other details. If every query loads the entire document, the application transfers and maps unnecessary data while risking accidental exposure of internal fields.

**Projection** is how you specify which fields MongoDB returns for a query. In a **find** query, projections have two basic forms: **inclusion** (selecting fields to keep) and **exclusion** (omitting fields you do not want). The key field **_id** is an important exception: it is returned by default even when you only include other fields, and it can be excluded independently without violating the rule against mixing inclusion and exclusion.

This topic belongs to the **Projection and DTO** chapter in the **SPRING_DATA_MONGODB** module. It connects directly to document mapping, `MongoTemplate`, repositories, and returning response DTOs. Projection design also impacts aggregation, indexes, testing, query performance, and reactive data-access paths.

After this lesson, you should be able to:

1. Understand the projection modes in MongoDB `find`.
2. Remember accurately the default rule and exception for the **_id** field.
3. Use **@Query(fields = ...)** and **MongoTemplate Query.fields()**.
4. Select fields for DTO/interface projections and avoid mapping into partial entities by mistake.
5. Distinguish embedded field selection from array element filtering and aggregation transformations.
6. Evaluate projections against API safety principles and real-world performance.
7. Test the returned BSON shape, not just DTO getter values.

## 2. Sample Document: products

Suppose the **products** collection has a document:

~~~javascript
{
  _id: ObjectId("507f1f77bcf86cd799439011"),
  sku: "BOOK-001",
  name: "Spring Data MongoDB Handbook",
  priceMinor: NumberLong("159000"),
  active: true,
  description: "Guide documentation on document storage.",
  tags: ["JAVA", "SPRING", "MONGODB"],
  supplier: {
    code: "SUP-01",
    internalNote: "Internal discount policy."
  },
  createdAt: ISODate("2025-06-01T09:00:00Z")
}
~~~

Here, `priceMinor` is an integer in the smallest currency unit per business contract; `createdAt` is a BSON Date; `_id` is a BSON ObjectId. A list API might need `_id`, `sku`, `name`, `priceMinor` without needing `description`, `tags`, or `supplier.internalNote`.

Illustrative entity as a Java record:

~~~java
package com.example.catalog;

import java.time.Instant;
import java.util.List;
import org.bson.types.ObjectId;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "products")
public record ProductDocument(
    @Id ObjectId id,
    String sku,
    String name,
    long priceMinor,
    boolean active,
    String description,
    List<String> tags,
    Supplier supplier,
    Instant createdAt
) {
    public record Supplier(String code, String internalNote) {}
}
~~~

The collection name is specified by **@Document**. Java property `id` maps to BSON `_id` via **@Id**. In this example, the remaining properties match the BSON field names; applications using **@Field** may use different BSON names.

## 3. Two Roles: Filter and Projection

A `find` command can accept a filter and a projection:

~~~javascript
db.products.find(
  { active: true },       // Filter: which documents?
  { sku: 1, name: 1 }    // Projection: which fields to return?
);
~~~

The filter selects documents matching `active = true`. The projection reduces the results to only the requested fields, aside from the `_id` exception. **Projection does not modify stored documents**, does not create another collection, and does not turn filter criteria into update operations.

~~~mermaid
flowchart LR
    A["Full products document"] --> B["Filter active = true"]
    B --> C["Projection sku, name"]
    C --> D["Slimmed BSON result"]
    D --> E["Spring Data mapping / DTO"]
~~~

In simple `find` projections, **1** indicates keeping a field (inclusion) and **0** indicates omitting a field (exclusion).

### 3.1. Inclusion: Selecting Only Needed Fields

~~~javascript
db.products.find(
  { active: true },
  { sku: 1, name: 1, priceMinor: 1 }
);
~~~

Sample result:

~~~javascript
{
  _id: ObjectId("507f1f77bcf86cd799439011"),
  sku: "BOOK-001",
  name: "Spring Data MongoDB Handbook",
  priceMinor: NumberLong("159000")
}
~~~

`_id` appears even though the projection does not write `_id: 1`. In inclusion mode, **MongoDB returns `_id` by default**. Other fields such as `description`, `active`, `tags`, `supplier`, and `createdAt` are omitted because they are not in the inclusion list.

### 3.2. Exclusion: Omitting Specific Fields

~~~javascript
db.products.find(
  { active: true },
  { description: 0, "supplier.internalNote": 0 }
);
~~~

In this mode, the result retains all remaining fields, including `_id`, `sku`, `name`, `priceMinor`, `active`, `tags`, `supplier.code`, and `createdAt`. The two specified fields are removed.

Important note: **exclusion is not a whitelist**. If a `privateCost` field is added to the collection tomorrow, the projection above can start returning `privateCost`. Therefore, for public APIs, prefer explicit inclusion over trying to enumerate every field to exclude.

## 4. The _id Exception in MongoDB

This is the core rule: **`_id` is returned by default, yet it can be excluded on its own with `_id: 0`**. MongoDB permits including other fields while simultaneously excluding `_id`. It also permits excluding other fields while explicitly specifying `_id`.

| Projection | Mode | Result |
| --- | --- | --- |
| { name: 1 } | Inclusion | `name` and `_id` |
| { name: 1, _id: 1 } | Inclusion | `name` and `_id` |
| { name: 1, _id: 0 } | Inclusion + `_id` exception | Only `name` |
| { description: 0 } | Exclusion | Everything except `description`, still includes `_id` |
| { description: 0, _id: 0 } | Exclusion + `_id` exception | Everything except `description` and `_id` |
| { description: 0, _id: 1 } | Exclusion, specifying `_id` | Everything except `description`, still includes `_id` |
| { _id: 0 } | Exclude `_id` only | All other fields |
| {} | Unrestricted | Full document, including `_id` |

### 4.1. Selecting `name` Without Returning `_id`

~~~javascript
db.products.find(
  { active: true },
  { name: 1, _id: 0 }
);
~~~

Result:

~~~javascript
{ name: "Spring Data MongoDB Handbook" }
~~~

The combination **name: 1, _id: 0** is valid. This is an exception specifically designed by MongoDB for the `_id` field.

### 4.2. Excluding Both `description` and `_id`

~~~javascript
db.products.find(
  { active: true },
  { description: 0, _id: 0 }
);
~~~

The result contains all fields except `description` and `_id`. If a new field is added later, it can still appear.

### 4.3. When Should You Keep the ID?

Keep the ID when building links to detail pages, calling update/delete APIs, distinguishing documents with identical names, or providing stable keys for caches/UIs. Drop the ID when exporting reports that do not need identifiers, when the API intentionally uses a separate public code, or when a task needs only aggregate values.

Do not drop `_id` merely to save a few bytes if downstream steps need to look up the document again. Conversely, avoid accidentally exposing technical IDs when the API contract forbids it.

## 5. Do Not Arbitrarily Mix Inclusion and Exclusion

For standard `find` projections, MongoDB forbids both including one field and excluding another field **except `_id`**.

Valid:

~~~javascript
{ sku: 1, name: 1, _id: 0 }
{ description: 0, "supplier.internalNote": 0, _id: 0 }
{ sku: 1, name: 1 }
{ description: 0 }
~~~

Invalid under the basic rule:

~~~javascript
{ sku: 1, description: 0 }
{ name: 1, "supplier.internalNote": 0 }
~~~

The first case asks to keep `sku` while excluding `description`. The second also mixes include/exclude outside `_id`. Choose one of the two strategies rather than trying to mix them.

### 5.1. Fixing a Projection to Return Only Three Public Fields

**Wrong:**

~~~javascript
{ sku: 1, name: 1, priceMinor: 1, "supplier.internalNote": 0 }
~~~

**Right if `_id` is not needed:**

~~~javascript
{ sku: 1, name: 1, priceMinor: 1, _id: 0 }
~~~

**Right if `_id` is needed:**

~~~javascript
{ sku: 1, name: 1, priceMinor: 1 }
~~~

In inclusion mode, there is no need to exclude `internalNote` because it is not selected. This is the simplest way to express a public data contract.

## 6. Projection with @Query(fields = ...)

Spring Data MongoDB provides the annotation:

~~~java
import org.springframework.data.mongodb.repository.Query;
~~~

The **value** attribute expresses the filter, while **fields** expresses the projection. Example:

~~~java
@Query(
    value = "{ 'active': true }",
    fields = "{ 'sku': 1, 'name': 1, 'priceMinor': 1 }"
)
List<ProductCardView> findActiveCards();
~~~

The `_id` field is not mentioned, so it is still returned by default. If `_id` is not needed:

~~~java
@Query(
    value = "{ 'active': true }",
    fields = "{ 'sku': 1, 'name': 1, 'priceMinor': 1, '_id': 0 }"
)
List<ProductExportView> findActiveForExport();
~~~

When the filter takes a parameter:

~~~java
@Query(
    value = "{ 'sku': ?0 }",
    fields = "{ 'name': 1, '_id': 0 }"
)
Optional<ProductNameView> findNameBySku(String sku);
~~~

**?0** is the placeholder for the first method parameter. It has nothing to do with the `0` in the projection: **?0** indicates parameter position, whereas **_id: 0** requests excluding the `_id` field.

### 6.1. Interface Projections

~~~java
import org.bson.types.ObjectId;

public interface ProductCardView {
    ObjectId getId();
    String getSku();
    String getName();
    long getPriceMinor();
}

public interface ProductExportView {
    String getSku();
    String getName();
    long getPriceMinor();
}

public interface ProductNameView {
    String getName();
}
~~~

`ProductCardView` has `getId` because the query does not exclude `_id`. `ProductExportView` and `ProductNameView` do not need the ID. These interfaces are **read-only views**, not entities for saving back.

### 6.2. Complete Repository

~~~java
package com.example.catalog;

import java.util.List;
import java.util.Optional;
import org.bson.types.ObjectId;
import org.springframework.data.mongodb.repository.MongoRepository;
import org.springframework.data.mongodb.repository.Query;

public interface ProductRepository
        extends MongoRepository<ProductDocument, ObjectId> {

    @Query(
        value = "{ 'active': true }",
        fields = "{ 'sku': 1, 'name': 1, 'priceMinor': 1 }"
    )
    List<ProductCardView> findActiveCards();

    @Query(
        value = "{ 'active': true }",
        fields = "{ 'sku': 1, 'name': 1, 'priceMinor': 1, '_id': 0 }"
    )
    List<ProductExportView> findActiveForExport();

    @Query(
        value = "{ 'sku': ?0 }",
        fields = "{ 'name': 1, '_id': 0 }"
    )
    Optional<ProductNameView> findNameBySku(String sku);
}
~~~

The example uses repository signatures to express clearly which result shape each endpoint requires. When a projection omits fields while the return type remains `ProductDocument`, the framework may construct an incomplete object or fail materialization, especially with primitives and required constructors.

### 6.3. Exclusion with @Query

~~~java
@Query(
    value = "{ 'active': true }",
    fields = "{ 'description': 0, 'supplier.internalNote': 0 }"
)
List<ProductDocument> findWithoutDescriptions();
~~~

This is a syntax example; **do not pass a partial `ProductDocument` result to `save`** or return that entity directly over a public API. For APIs with explicit contracts, use inclusion combined with interface projections/DTOs.

## 7. MongoTemplate: Include and Exclude via Query.fields()

`MongoTemplate` lets you build projections without embedding JSON strings in annotations:

~~~java
import java.util.List;
import org.bson.Document;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

public List<Document> loadCards(MongoTemplate template) {
    Query query = Query.query(Criteria.where("active").is(true));

    query.fields()
        .include("sku")
        .include("name")
        .include("priceMinor")
        .exclude("_id");

    return template.find(query, Document.class, "products");
}
~~~

Here, `MongoTemplate` returns raw `Document` instances to show the projection result contains strictly `sku`, `name`, and `priceMinor` without `_id`. In real business code, you should usually map results to a read-purpose DTO.

Exclusion:

~~~java
Query query = Query.query(Criteria.where("active").is(true));
query.fields()
    .exclude("description")
    .exclude("supplier.internalNote")
    .exclude("_id");

List<Document> results =
    mongoTemplate.find(query, Document.class, "products");
~~~

Remember that any field not excluded can still appear in the results.

### 7.1. A Builder API Mistake

~~~java
// Invalid: mixing inclusion and exclusion outside _id.
query.fields()
    .include("name")
    .exclude("description");
~~~

The Java API may let you build the `Query` object, yet the server can reject the projection for violating the basic rule. Use only `include`, only `exclude`, or `include` combined with `exclude("_id")`.

### 7.2. Choosing the Collection by Entity or Name

~~~java
// Collection inferred from @Document(collection = "products").
List<ProductDocument> mapped =
    mongoTemplate.find(query, ProductDocument.class);

// Collection specified directly.
List<Document> raw =
    mongoTemplate.find(query, Document.class, "products");
~~~

When querying through `ProductDocument` metadata, `@Field` and `@Id` can affect BSON field names. When working with raw `Document` or the driver directly, you must use the exact stored field names.

## 8. Differences Between BSON _id and Java id

An entity may have:

~~~java
import org.bson.types.ObjectId;
import org.springframework.data.annotation.Id;

@Id
private ObjectId id;
~~~

MongoDB stores the **_id** field, whereas the Java object has an **id** property. The default inclusion and exclusion exception rules apply to **BSON _id**, even if the application names the Java property differently.

If a projection excludes `_id` while an interface still declares `getId`, the ID has no data to map according to the contract. Design matching views: keep `_id` when identity is needed, or remove the ID accessor when the query intentionally excludes `_id`.

### 8.1. IDs in Public DTOs

MongoDB may store:

~~~javascript
{ _id: ObjectId("507f1f77bcf86cd799439011") }
~~~

An API may publish:

~~~json
{
  "id": "507f1f77bcf86cd799439011"
}
~~~

This is **converting representation** from `ObjectId` to a hex string for HTTP/JSON. Do not confuse a JSON hex string with a BSON `ObjectId`. If an API does not want to expose technical IDs, use a separate public ID and design the relationship between the two IDs.

## 9. DTOs Are the Published Data Contract

Projection decides which fields MongoDB returns, whereas the **DTO** decides what structure the service or API presents. The two mechanisms work together rather than replacing one another.

~~~mermaid
flowchart LR
    A["MongoDB products"] --> B["Projection: _id, sku, name, priceMinor"]
    B --> C["ProductCardView"]
    C --> D["ProductCardDto"]
    D --> E["JSON response"]
~~~

A DTO independent of Java's `ObjectId` class:

~~~java
public record ProductCardDto(
    String id,
    String sku,
    String name,
    long priceMinor
) {}
~~~

Mapping in the service:

~~~java
import java.util.List;

public List<ProductCardDto> listCards() {
    return repository.findActiveCards().stream()
        .map(p -> new ProductCardDto(
            p.getId().toHexString(),
            p.getSku(),
            p.getName(),
            p.getPriceMinor()
        ))
        .toList();
}
~~~

This snippet assumes `repository` is a service dependency and valid documents have an ID. A DTO lets the API control field names and ID types while avoiding returning a `ProductDocument` containing internal data directly.

### 9.1. DTOs That Do Not Need an ID

~~~java
public record ProductExportDto(
    String sku,
    String name,
    long priceMinor
) {}
~~~

With this DTO, the projection can include `sku`, `name`, `priceMinor` and **exclude `_id`**. Do not write code calling `getId` when the result type excludes the ID.

### 9.2. Why Prefer Inclusion for Public APIs?

Suppose a project has an exclusion projection:

~~~javascript
{ description: 0, "supplier.internalNote": 0 }
~~~

Later a developer adds `supplier.bankAccount` and `internalCost`. Those new fields may be returned in results before ever being reviewed for public exposure.

With inclusion:

~~~javascript
{ sku: 1, name: 1, priceMinor: 1, _id: 1 }
~~~

Only the selected fields are returned, even if the document is extended later. This keeps the **response contract stable** and reduces the risk of unexpectedly leaking fields.

### 9.3. Using Class/Record Projections Directly

Spring Data supports multiple projection forms, including interface projections and class-based DTOs depending on version and constructor-binding support. If returning a record DTO directly from a repository, the constructor must have parameters mappable from the results. An arbitrary DTO will not automatically materialize cleanly when required fields are missing.

**An easy-to-control approach** is having the repository return an interface projection and the service convert it to a record DTO, especially when converting `ObjectId` to `String` or normalizing display values.

## 10. Projection on Embedded Objects

In the sample document, `supplier` is an object:

~~~javascript
{
  supplier: {
    code: "SUP-01",
    internalNote: "Internal policy"
  }
}
~~~

To fetch only the supplier code:

~~~javascript
db.products.find(
  { active: true },
  { "supplier.code": 1, _id: 0 }
);
~~~

Illustrative result:

~~~javascript
{
  supplier: {
    code: "SUP-01"
  }
}
~~~

**supplier.code** is dot notation selecting one field inside a subdocument. It does not require reading another collection and does not flatten `code` into a top-level field.

In a repository:

~~~java
@Query(
    value = "{ 'active': true }",
    fields = "{ 'supplier.code': 1, '_id': 0 }"
)
List<SupplierCodeView> findSupplierCodes();
~~~

Nested interfaces can mirror the BSON structure:

~~~java
public interface SupplierCodeView {
    SupplierView getSupplier();

    interface SupplierView {
        String getCode();
    }
}
~~~

If you want to **exclude** one nested field while keeping others:

~~~javascript
db.products.find(
  { active: true },
  { "supplier.internalNote": 0 }
);
~~~

With exclusion, `supplier.code` is still returned. If `supplier` later gains a new field, that field can also appear.

### 10.1. When Java Uses @Field Different from the BSON Name

Example:

~~~java
import org.springframework.data.mongodb.core.mapping.Field;

@Field("supplier_code")
private String supplierCode;
~~~

Spring Data can map the `supplierCode` property to BSON `supplier_code` across query/projection paths using entity metadata. When querying directly via `mongosh` or the MongoDB Java Driver, you must use **supplier_code**. With custom converters or complex nested mappings, test the exact BSON names sent to the server.

## 11. Array Projection Does Not Mean Element Filtering

Another document has a `variants` array:

~~~javascript
{
  sku: "KIT-001",
  variants: [
    { color: "RED", stock: NumberInt(0) },
    { color: "BLUE", stock: NumberInt(5) }
  ]
}
~~~

Projection:

~~~javascript
db.products.find(
  { sku: "KIT-001" },
  { "variants.color": 1, _id: 0 }
);
~~~

MongoDB returns **both `variants` elements**, keeping only `color` in each element. Selecting a field on an array **does not** filter elements by `stock` or `color`.

Even the query:

~~~javascript
db.products.find(
  { "variants.stock": { $gt: 0 } },
  { "variants.color": 1, _id: 0 }
);
~~~

still only selects **documents having at least one in-stock variant**. Projecting the `variants.color` path does not shrink the array down to only in-stock variants.

MongoDB provides the **$elemMatch** projection operator to return a single matching array element. When you need to filter multiple elements or perform complex array transformations, aggregation with **$filter** and **$project** is usually easier to control.

### 11.1. $slice Has Special Combination Rules

~~~javascript
db.products.find(
  { active: true },
  { tags: { $slice: 2 } }
);
~~~

`$slice` in a projection limits `tags` to the first two elements without modifying the stored array. **Starting in MongoDB 4.4, `$slice` is treated as an exclusion projection** with respect to include/exclude combination rules, so do not combine it with `name: 1` assuming it is valid. For results needing complex transformations, use aggregation and test on your actual server version.

## 12. Find Projection vs. Aggregation $project

Simple `find` projection:

~~~javascript
db.products.find(
  { active: true },
  { sku: 1, name: 1, priceMinor: 1, _id: 0 }
);
~~~

Aggregation `$project` can rename or compute fields:

~~~javascript
db.products.aggregate([
  { $match: { active: true } },
  {
    $project: {
      _id: 0,
      sku: 1,
      displayName: "$name",
      priceMinor: 1
    }
  }
]);
~~~

Here `displayName` is derived from `name`. This is **transforming the result**, not merely picking existing fields. A pipeline can also contain `$group`, `$lookup`, `$filter`, and many other stages.

Therefore, when you need complex calculations, data joins, array filtering, or shaped reports, **@Aggregation** or **MongoTemplate.aggregate** is usually better suited than `@Query(fields)`. Do not cram aggregation expressions into a `find` projection without checking the specific rules of each query type.

## 13. Projection and Performance

Projection typically helps:

- Reduce BSON bytes transferred from server to client.
- Reduce BSON-to-Java object decoding work.
- Avoid loading large unused fields.
- Clarify which fields the API needs, reducing accidental forwarding of excess data.

Yet **returning fewer fields does not mean MongoDB always reads less data from disk**. If the server must fetch the original document to retrieve one field, projection still reduces network transfer without necessarily avoiding document reads.

### 13.1. Covered Queries

Suppose a workload frequently filters `active` and returns only `sku`, `name`, `priceMinor`. You can evaluate an index like:

~~~javascript
db.products.createIndex({
  active: 1,
  sku: 1,
  name: 1,
  priceMinor: 1
});
~~~

Query:

~~~javascript
db.products.find(
  { active: true },
  { sku: 1, name: 1, priceMinor: 1, _id: 0 }
).explain("executionStats");
~~~

Because both the filter and projection need only fields present in the index, the query **can** run as a **covered query** (using only the index without fetching documents), depending on index characteristics and execution plan.

### 13.2. How the _id Exception Affects Covered Queries

The example index does not contain `_id`. If the projection is simply:

~~~javascript
{ sku: 1, name: 1, priceMinor: 1 }
~~~

MongoDB still must return `_id` by default, and the index above may be unable to supply `_id`. When the API genuinely does not need the ID, adding **_id: 0** can allow the query to qualify as index-covered.

Do not drop `_id` everywhere by default: if the client needs identifiers, keep the ID and evaluate an appropriate index or accept the `FETCH` after measuring. Indexes with too many fields also increase storage and update overhead.

### 13.3. Metrics to Observe

| Metric / component | What to understand |
| --- | --- |
| `winningPlan` | Which plan did the query planner choose? |
| `totalKeysExamined` | Number of index keys read |
| `totalDocsExamined` | Number of source documents examined |
| `nReturned` | Number of documents returned after filtering |
| `FETCH` stage | Did it need to fetch the full document? |
| `executionTimeMillis` | Observed execution time during the test |

In a true covered query, `totalDocsExamined` can be 0. Do not claim an index always helps based on a tiny test; measure with realistic data, sorting, filtering, and workloads.

### 13.4. Projection Does Not Replace Pagination

Returning 100,000 documents—even if each document contains only `name`—still creates heavy network and processing overhead. Combine projections with record limits, `Sort`/`Pageable`, or keyset pagination strategies as needed.

## 14. Using Sort and Pageable with Projections

A repository can declare:

~~~java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;

@Query(
    value = "{ 'active': true }",
    fields = "{ 'sku': 1, 'name': 1, 'priceMinor': 1 }"
)
Page<ProductCardView> findActiveCards(Pageable pageable);
~~~

Usage:

~~~java
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;

PageRequest request = PageRequest.of(
    0,
    20,
    Sort.by(Sort.Order.desc("createdAt"), Sort.Order.desc("id"))
);

Page<ProductCardView> page =
    repository.findActiveCards(request);
~~~

Fields used for sorting do not necessarily have to be returned in the projection. However, if you use a keyset cursor on sort fields, design a way to retrieve the corresponding cursor keys. `Page` may run a count query to compute total elements; if totals are unnecessary, `Slice` may fit better. Sorting on unindexed fields can still consume significant resources.

## 15. Projection Is Not the Only Security Measure

For public APIs, an **inclusion whitelist** is an important step:

~~~java
@Query(
    value = "{ 'active': true }",
    fields = "{ '_id': 1, 'sku': 1, 'name': 1, 'priceMinor': 1 }"
)
List<ProductCardView> findPublicCards();
~~~

Newly added `supplier.internalNote` and `privateCost` fields will not automatically appear when only approved fields are included. Public DTOs further govern the types and names of serialized data.

However, you cannot rely on projection alone and conclude the application has authorization. Another `MongoTemplate` method could read more fields; a MongoDB user might have collection-wide permissions; other tenants could be read if filters omit **tenantId**.

Verify separately:

1. Is the caller permitted to see documents belonging to that tenant and data scope?
2. Does the projection fetch only fields allowed to be published?
3. Can the DTO/serializer expose unexpected new fields?
4. Do any other repository, `MongoTemplate`, or aggregation paths bypass policy?

### 15.1. Do Not Save Back Partially Loaded Entities

If a repository returns `ProductDocument` while `fields` loads only `name` and `sku`, remaining fields may become `null`, primitive defaults, or fail materialization with immutable constructors.

**Do not call `repository.save()` with a partial entity as if it were the complete record.** A replace operation can delete unloaded fields. If you only need to update `name`, use a conditional field update, or fetch the full entity first before applying changes according to your system's concurrency policy.

## 16. Testing Projections Against Real BSON

A test that merely calls `getName()` on an interface is not enough to prove MongoDB did not return internal fields. Inspect the **raw BSON Document** result and cross-check it with the service's projection/DTO types.

Example using `MongoTemplate` in JUnit 5 and a test MongoDB instance:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.time.Instant;
import java.util.List;
import java.util.UUID;
import org.bson.Document;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

@DataMongoTest
class ProductProjectionTest {

    @Autowired
    MongoTemplate template;

    @Test
    void inclusionExcludesIdAndInternalData() {
        String sku = "TEST-" + UUID.randomUUID();
        ProductDocument inserted = template.insert(new ProductDocument(
            null,
            sku,
            "Projection test",
            159_000L,
            true,
            "Long document",
            List.of("JAVA"),
            new ProductDocument.Supplier("SUP-T", "Private"),
            Instant.parse("2025-06-01T09:00:00Z")
        ));

        try {
            Query query = Query.query(Criteria.where("sku").is(sku));
            query.fields()
                .include("sku")
                .include("name")
                .include("priceMinor")
                .exclude("_id");

            List<Document> results =
                template.find(query, Document.class, "products");

            assertThat(results).hasSize(1);
            Document raw = results.get(0);
            assertThat(raw.containsKey("_id")).isFalse();
            assertThat(raw.containsKey("sku")).isTrue();
            assertThat(raw.containsKey("name")).isTrue();
            assertThat(raw.containsKey("priceMinor")).isTrue();
            assertThat(raw.containsKey("description")).isFalse();
            assertThat(raw.containsKey("supplier")).isFalse();
        } finally {
            template.remove(
                Query.query(Criteria.where("_id").is(inserted.id())),
                ProductDocument.class
            );
        }
    }
}
~~~

Run this test only against a **dedicated test database**, never on production. Using a random SKU prevents collisions with existing records. The example uses `Document.class` to assert the exact fields returned by the server without relying on materializing a partial entity.

### 16.1. Test Matrix for the _id Exception

| Projection | Expected |
| --- | --- |
| { name: 1 } | Has `name` and `_id` |
| { name: 1, _id: 0 } | Has `name`, no `_id` |
| { description: 0 } | No `description`, still has `_id` |
| { description: 0, _id: 0 } | Neither `description` nor `_id` |
| { name: 1, description: 0 } | Rejected under basic projection rules |
| { "supplier.code": 1, _id: 0 } | Has `supplier.code`, no `internalNote` |
| { name: 1, priceMinor: 1, _id: 0 } | Has the two requested fields, no ID |

If the project uses `@Field` and custom converters, add raw BSON fixture tests to catch mismatched field names. With `@Query(fields)` methods, test both view values and successful DTO instantiation.

## 17. Common Errors and Diagnostics

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Selected only `name` yet `_id` still appears | `_id` is included by default | Add `_id: 0` if ID is not needed |
| Server rejects projection as invalid | Mixing include and exclude outside `_id` | Pick one projection mode |
| `getId` has no value | Query excluded `_id` | Keep `_id` or update view/DTO contract |
| API leaks recently added fields | Used exclusion instead of inclusion | Switch to inclusion whitelist and public DTO |
| `supplier` returns too much data | Included whole `supplier` | Include only `supplier.code` |
| Array elements are not filtered | Field-path projection only reshapes fields | Use `$elemMatch` or aggregation `$filter` |
| DTO gets unexpected nulls/defaults | Missing fields needed by constructor/primitives | Select required fields and use matching DTOs |
| `save` wipes other fields | Saved a partially read entity | Use conditional updates or load the full entity |
| Projection has few fields yet query is slow | Filter/index/sort unsuitable or `FETCH` stage | Run `explain("executionStats")` |
| Query is not index-covered | Default `_id` or field missing from index | Review projection and index design |
| Wrong field name | Confused Java property and `@Field` BSON name | Check mapping and raw BSON |
| Right fields filtered yet wrong tenant | Projection does not enforce permissions | Add authenticated tenant policy/filter |

Investigation steps:

1. Confirm actual database, collection, and BSON documents.
2. Separate the filter from the projection.
3. Verify whether the projection is in inclusion or exclusion mode.
4. Check whether `_id` is included by default or excluded.
5. Reconcile embedded/array paths and `@Field` mappings.
6. Verify the view/DTO shape matches the selected fields.
7. For slow queries, check indexes and `explain` rather than only response size.
8. Add regression tests for field selection/exclusion, especially for sensitive fields.

## 18. Practice Exercises

### Exercise 1: Does _id Appear?

~~~javascript
db.products.find({}, { name: 1, priceMinor: 1 });
~~~

**Question:** Does the result contain `_id`?

**Answer:** Yes. MongoDB includes `_id` by default in inclusion projections. If no identifier is needed, add **_id: 0**.

### Exercise 2: Fixing an Invalid Projection

~~~javascript
{ name: 1, priceMinor: 1, description: 0 }
~~~

**Question:** Why is this wrong, and how do you fix it if you only need `name` and `priceMinor`?

**Answer:** It mixes inclusion and exclusion on ordinary fields. Fix it to **{ name: 1, priceMinor: 1, _id: 0 }** if ID is unnecessary, or omit `_id: 0` if ID is still needed.

### Exercise 3: Include or Exclude?

A public API exposes `sku`, `name`, `priceMinor`. The collection adds a new `privateCost` field. Should you use inclusion or exclusion?

**Answer:** Inclusion whitelist. It will not automatically return `privateCost` when new fields are added. Exclusion only removes known, explicitly listed fields.

### Exercise 4: @Query(fields)

Write a method finding active products, returning `sku`/`name`/`priceMinor` without `_id`.

~~~java
@Query(
    value = "{ 'active': true }",
    fields = "{ 'sku': 1, 'name': 1, 'priceMinor': 1, '_id': 0 }"
)
List<ProductExportView> findForExport();
~~~

### Exercise 5: Arrays

A document has `variants` as an array of objects. If a projection selects only **variants.color**, does that ensure only red variants are returned?

**Answer:** No. Field-path projection is not an element filter. Use appropriate array filtering if only matching elements should be returned.

### Exercise 6: Covered Query

An index contains only `active`, `sku`, `name`, `priceMinor`. A query filters `active` and includes the other three fields without writing `_id: 0`. What can prevent a covered query?

**Answer:** `_id` is returned by MongoDB by default while the index does not contain `_id`. Add `_id: 0` when ID is not needed, then inspect `explain` to verify `FETCH` can be avoided.

### Exercise 7: Partial Entity

A repository loads `ProductDocument` with only `sku` and `name`, then the service modifies `name` and calls `save`. What is the risk?

**Answer:** unloaded fields may be null/default and get wiped during replacement. Never save partial entities; use a DTO projection and conditional field-level updates.

### Exercise 8: Public DTO

Design an endpoint returning ID, `sku`, `name`, `priceMinor` without ever returning `supplier` or `description`.

**Hint:** use inclusion **_id, sku, name, priceMinor**, return `ProductCardView` and map to `ProductCardDto`. Test raw BSON to ensure `supplier`/`description` are absent, and test authorization/tenant rules independently from projection.

## 19. Rules to Remember

1. **Find projections use 1 to include and 0 to exclude** fields under basic rules.
2. **Never mix inclusion and exclusion on ordinary fields**; the exception is **_id**.
3. **_id is returned by default**, even when selecting only a few fields; add **_id: 0** to exclude it.
4. **@Query(fields = ...)** and **MongoTemplate Query.fields()** follow the same projection rules.
5. **DTOs/views must reflect the loaded fields accurately**; never use partial entities for `save`.
6. **Selecting subdocument fields is not filtering array elements**, and aggregation fits complex transformations.
7. **For public APIs, prefer an inclusion whitelist** to avoid accidentally exposing new fields.
8. **Projections reduce transferred data and mapping work**, while avoiding `FETCH` depends on indexes; default `_id` can affect covered queries.
9. **Testing raw BSON and `explain`** verifies result shape, safety, and performance.

Mastering how to include or exclude fields alongside the **_id** exception helps **SPRING_DATA_MONGODB** applications return lean DTOs, prevent data leaks, leverage `MongoTemplate`/repositories properly, and improve testability, maintainability, and MongoDB query optimization.
