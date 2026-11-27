# Constructor DTOs and Java Records

## 1. Why Do We Need DTO Projections When We Already Have Entities?

In the **Projection and DTO** chapter of **Spring Data MongoDB**, an important question is: *When an API only needs three fields of a product, should we load the whole document and return the entity directly?*

Suppose the products collection stores name, price, stock, status, internal notes, and update metadata. The catalog screen only needs **ID, name, and price**. Returning the entire entity not only increases the volume of data processed but also tightly couples the API contract to the storage model. A change in the entity could accidentally alter the serialized output if the API returns the entity directly.

A **DTO** (*Data Transfer Object*) is a data type designed for passing results between layers or to clients. A **projection** is a way to select a subset of data or a result shape from a source; in Spring Data, projections can be implemented via interfaces or classes/records. The two concepts are related but **not identical**:

- A DTO can be **instantiated directly by Spring Data during a query**: that is a *class-based DTO projection*.
- A DTO can also be **constructed manually from a fully loaded entity**: still a DTO, though it does not necessarily reduce the fields read from MongoDB.
- A projection can be an **interface proxy** instead of a concrete DTO instance.
- MongoDB's `$project` aggregation stage is a **server-side stage**; aggregation results can subsequently be mapped into a DTO, including Java records.

The goal of this lesson is to use **DTO class constructors** and **Java record canonical constructors** to return clean data, understand field selection mechanics, and learn how to inspect the **actual queried BSON**.

> Examples use Java 17+, Spring Boot 3.x, Spring Data MongoDB 4.x, and the MongoDB Java Sync Driver. Field inference and projection support depend on the query type and framework version. Always verify with integration tests before assuming a particular API optimizes fetched fields.

## 2. Common Result Types

| Result approach | Object received | How it is constructed | When appropriate |
|---|---|---|---|
| Return `CatalogProduct` entity | Full entity | Converter maps document to entity | Business flows needing full state for processing |
| Interface projection | Proxy implementing the interface | Spring Data creates a proxy and delegates accessors | A subset of properties, including nested interface projections |
| Class-based DTO projection | Instance of DTO class | Matching constructor and parameter metadata | Concrete, immutable output contract with simple presentation logic |
| Java record projection | Instance of record | Canonical constructor | Compact DTO, explicit fields, easy value comparison |
| Aggregation + DTO | DTO/record from pipeline output documents | `$project`/`$group`/etc. then mapping | Reports, grouping, calculations, or reshaping data |

Minimal interface projection example:

~~~java
package com.example.catalog;

public interface ProductNameView {
    String getName();
    long getPriceVnd();
}
~~~

The difference: interface-based projections are typically provided by Spring Data via proxies; class/record projections **do not require creating a proxy per DTO** and instead use a constructor to instantiate the object. Java records also automatically provide `equals`, `hashCode`, `toString`, and component-named accessors.

This does not mean "records are always faster than interfaces." Performance must be measured based on data, selected fields, conversion, round trips, pagination, and indexes.

## 3. Source Entity and BSON Data

We use the `catalog_products` collection. Example classes belong to the `com.example.catalog` package so Spring Boot can scan repositories by convention.

**CatalogProduct.java**

~~~java
package com.example.catalog;

import org.springframework.data.annotation.Version;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.mapping.MongoId;

@Document(collection = "catalog_products")
public class CatalogProduct {
    @MongoId(FieldType.STRING)
    private String id;
    private String name;
    private String category;
    private long priceVnd;
    private int stock;
    private String status;
    private String internalNote;
    @Version
    private Long version;

    protected CatalogProduct() {
        // For Spring Data materialization.
    }

    public CatalogProduct(
            String id, String name, String category,
            long priceVnd, int stock, String status, String internalNote) {
        this.id = id;
        this.name = name;
        this.category = category;
        this.priceVnd = priceVnd;
        this.stock = stock;
        this.status = status;
        this.internalNote = internalNote;
    }

    public String getId() { return id; }
    public String getName() { return name; }
    public String getCategory() { return category; }
    public long getPriceVnd() { return priceVnd; }
    public int getStock() { return stock; }
    public String getStatus() { return status; }
    public String getInternalNote() { return internalNote; }
    public Long getVersion() { return version; }
}
~~~

`@MongoId(FieldType.STRING)` instructs storing the `_id` key as a BSON String, preventing a 24-hex-character `String` from being unintentionally converted to a BSON ObjectId. `@Version` supports optimistic locking on Spring Data-managed write paths and is not a field to expose publicly in product listings.

Example document:

~~~json
{
  "_id": "prd-101",
  "name": "Water Bottle 500 ml",
  "category": "drinkware",
  "priceVnd": 129000,
  "stock": 42,
  "status": "ACTIVE",
  "internalNote": "Cost price is internal information",
  "version": 0
}
~~~

On the catalog screen, we want to return:

~~~json
{
  "id": "prd-101",
  "name": "Water Bottle 500 ml",
  "priceVnd": 129000
}
~~~

**Returning fewer fields in the response** is one goal; **reading fewer fields from MongoDB** is a complementary goal. Both goals must be verified separately.

## 4. Class-Based DTO: Mapping via Constructor

A traditional DTO can be a `final` class with `private final` properties, a constructor accepting the required data, and getters.

**ProductCardDto.java**

~~~java
package com.example.catalog;

import org.springframework.data.annotation.PersistenceCreator;

public final class ProductCardDto {
    private final String id;
    private final String name;
    private final long priceVnd;

    @PersistenceCreator
    public ProductCardDto(String id, String name, long priceVnd) {
        this.id = id;
        this.name = name;
        this.priceVnd = priceVnd;
    }

    // Convenience constructor for manually constructing the DTO, not used for reading projections.
    public ProductCardDto(String name, long priceVnd) {
        this(null, name, priceVnd);
    }

    public String getId() { return id; }
    public String getName() { return name; }
    public long getPriceVnd() { return priceVnd; }
}
~~~

For **class-based projections**, Spring Data relies on constructor metadata to know which properties the DTO requires. Here, the parameter names `id`, `name`, and `priceVnd` match the properties of `CatalogProduct`. The entity's `id` corresponds to `_id` in BSON.

### 4.1. Why Must the Constructor Be Selected Explicitly?

With a class having multiple constructors as in the example, `@PersistenceCreator` designates **the constructor used to materialize the object**. If a class has only one suitable constructor, the framework can usually pick it automatically without the annotation.

Parameter names matter:

- `ProductCardDto(String id, String name, long priceVnd)` expresses the input properties.
- If the Java class is compiled without retaining parameter name metadata, Spring Data may fail to identify the properties to bind.
- In standard Java projects, enable the `-parameters` compiler flag or use metadata mechanisms supported by your Spring Data version.
- Renaming a parameter from `name` to `label` without updating the corresponding mapping model **is not** a purely cosmetic change across all projection types.

If a DTO has multiple constructors and the target constructor cannot be determined, an error may appear either when the repository initializes the query or during result mapping, depending on the version's bootstrap mechanism.

### 4.2. How Does a Class DTO Differ from an Entity?

`ProductCardDto` has no `@Document`, `@Id`, or `save`. It is an **output shape**, not an aggregate root to be updated. Never take a DTO containing only three fields and call `save` on the products collection, as other fields may not be preserved as business logic intends.

A DTO constructor should also not send emails, call HTTP APIs, or perform I/O. A query returning 100 documents may materialize 100 DTOs; the constructor must be a lightweight, deterministic data instantiation operation.

## 5. Java Record: Concise and Immutable DTO Projections

With Java 17+, records are a natural fit for data-only DTOs:

**ProductCardRecord.java**

~~~java
package com.example.catalog;

public record ProductCardRecord(
        String id,
        String name,
        long priceVnd) {
}
~~~

A record has a **canonical constructor** accepting the declared components. Spring Data can use the record's constructor and component metadata to map results. There is no need to write JavaBean-style getters; default accessors are `id()`, `name()`, and `priceVnd()`.

Advantages of records:

- Accurately describes the allowed return data contract.
- No setters; component references cannot be reassigned after creation.
- Provides component-based `equals`/`hashCode`, useful for testing and value-based caching.
- Eliminates boilerplate compared to class DTOs with manual fields/getters/constructors.

**Shallow immutability, not automatically deep immutability.** A record containing `List<String> tags` can still be mutated via a mutable list passed in. For DTOs containing collections, consider defensive copying:

~~~java
package com.example.catalog;

import java.util.List;

public record ProductDetailRecord(
        String id,
        String name,
        List<String> tags) {

    public ProductDetailRecord {
        tags = tags == null ? List.of() : List.copyOf(tags);
    }
}
~~~

This is an example of a **different record DTO** from `ProductCardRecord`. Converting `null` into an empty list is appropriate if the API contract does not distinguish "field absent" from "empty field." When that distinction carries business meaning, choose an explicit policy instead of silently converting.

### 5.1. Constructors with Invariants Must Account for Historical Data

A record can validate parameters:

~~~java
public ProductCardRecord {
    if (id == null || name == null || priceVnd < 0) {
        throw new IllegalArgumentException("Invalid product data");
    }
}
~~~

The snippet above is a **compact constructor body added to the `ProductCardRecord` declaration**, not a standalone Java class. When reading legacy documents missing `name` or storing a negative price, the constructor may throw an exception. Therefore, new constraints on a DTO must be evaluated alongside the source data schema and migration strategy.

Do not use a DTO constructor to automatically "fix" invalid data silently in ways that are hard to observe. If the source has an inconsistent schema, clearly define which data is accepted, rejected, or requires transformation.

## 6. Returning Class DTOs and Records from MongoRepository

Create a repository on the root entity:

**CatalogProductRepository.java**

~~~java
package com.example.catalog;

import java.util.List;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface CatalogProductRepository
        extends MongoRepository<CatalogProduct, String> {

    // Record projection: declares only the contract the screen needs.
    List<ProductCardRecord> findByStatus(String status);

    // Class DTO projection with an explicitly chosen constructor.
    List<ProductCardDto> findTop10ByStatusOrderByPriceVndAsc(String status);

    // Dynamic projection: caller decides the result type at invocation time.
    <T> List<T> findByCategory(String category, Class<T> type);

    // When total count and pagination are needed.
    Page<ProductCardRecord> findByStatus(String status, Pageable pageable);
}
~~~

The application only needs the Spring Data MongoDB starter and appropriate connection configuration; Spring Data generates the interface implementation at runtime. Methods use **Java property names** of `CatalogProduct`, without needing to stitch BSON field names into method names.

Example service:

~~~java
package com.example.catalog;

import java.util.List;
import org.springframework.stereotype.Service;

@Service
public class CatalogReadService {
    private final CatalogProductRepository products;

    public CatalogReadService(CatalogProductRepository products) {
        this.products = products;
    }

    public List<ProductCardRecord> activeCards() {
        return products.findByStatus("ACTIVE");
    }

    public List<ProductCardDto> cheapestTenActive() {
        return products.findTop10ByStatusOrderByPriceVndAsc("ACTIVE");
    }
}
~~~

With `ProductCardRecord`, results can be instantiated with `id`, `name`, and `priceVnd` without creating the full entity and writing manual mapping code, when Spring Data MongoDB supports class-based projections for the query type used.

### 6.1. Which Fields Does the Projection Select on MongoDB?

A `find` command projecting only the DTO fields has equivalent meaning to:

~~~javascript
db.catalog_products.find(
  { status: "ACTIVE" },
  { _id: 1, name: 1, priceVnd: 1 }
);
~~~

Here:

- `{ status: "ACTIVE" }` is the **filter**.
- `{ _id: 1, name: 1, priceVnd: 1 }` is the **field projection** of the `find` command.
- `_id` is returned by MongoDB by default unless excluded; written explicitly in the example for clarity.
- `stock` and `internalNote` do not need to be transferred to the client in a query with proper field projection.

**Important:** The snippet above illustrates the field-selection goal and **does not guarantee** that every derived repository method returning a DTO sends that exact BSON command. Spring Data can optimize selection based on constructor properties for supported projection forms; when using annotations, custom queries, or special types, inspect the actual command. Returning only a DTO from the API does not by itself prove MongoDB read fewer fields.

### 6.2. Page, Sort, and Returned Data

Example:

~~~java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;

Page<ProductCardRecord> page = repository.findByStatus(
        "ACTIVE",
        PageRequest.of(0, 20,
                Sort.by(Sort.Order.asc("priceVnd"),
                        Sort.Order.asc("id"))));
~~~

`repository` here is of type `CatalogProductRepository`. Sorting uses Java properties; `id` is mapped to `_id`. The second field ensures deterministic ordering when multiple products have the same price.

Returning `Page<T>` may issue a total count query to compute page metadata; inspect the actual command count. If you only need to know whether a next page exists, consider `Slice<T>` or cursor/keyset pagination depending on API support. Narrowing DTO fields does not eliminate `skip` overhead at deep pages.

## 7. Dynamic Projection: Same Query, Multiple Result Types

Method:

~~~java
<T> List<T> findByCategory(String category, Class<T> type);
~~~

allows the caller to choose the projection type:

~~~java
List<ProductCardRecord> cards =
        repository.findByCategory("drinkware", ProductCardRecord.class);

List<ProductCardDto> classDtos =
        repository.findByCategory("drinkware", ProductCardDto.class);

List<CatalogProduct> fullEntities =
        repository.findByCategory("drinkware", CatalogProduct.class);
~~~

Differences:

- `ProductCardRecord.class`: receives record instances with three components.
- `ProductCardDto.class`: receives DTO class instances via its constructor.
- `CatalogProduct.class`: receives entities for flows requiring full state.

This is **dynamic projection**, not returning `Object` and casting manually. The `Class<T>` parameter is normally used by Spring Data as a marker to determine the projection type and may not be treated as an ordinary query parameter; when writing `@Query`/SpEL, verify how that parameter is bound.

**Do not indiscriminately change every controller to accept `Class<T>` from HTTP input.** Allowed DTO types must be decided by the server according to contracts and access rights; do not let callers choose arbitrary classes to request fields that are not permitted to be public.

## 8. Using MongoTemplate and Fluent Projection

Not every case requires adding another repository method. `MongoTemplate` supports building dynamic `Query` objects; the fluent API can specify the output type:

~~~java
package com.example.catalog;

import java.util.List;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.stereotype.Service;

@Service
public class ProductCardQueryService {
    private final MongoTemplate mongo;

    public ProductCardQueryService(MongoTemplate mongo) {
        this.mongo = mongo;
    }

    public List<ProductCardRecord> activeAbovePrice(long minimumPrice) {
        Query query = Query.query(
                Criteria.where("status").is("ACTIVE")
                        .and("priceVnd").gte(minimumPrice));

        return mongo.query(CatalogProduct.class)
                .as(ProductCardRecord.class)
                .matching(query)
                .all();
    }
}
~~~

`mongo.query(CatalogProduct.class)` establishes the source entity and mapping metadata; `as(ProductCardRecord.class)` specifies the projection type. This is a clean way to express queries whose criteria depend on input.

If you need to control the exact fields MongoDB returns, you can specify field projections on `Query` and inspect the command:

~~~java
Query query = Query.query(Criteria.where("status").is("ACTIVE"));
query.fields().include("name").include("priceVnd").include("id");

// Execute with the source entity so appropriate mapping metadata is applied.
List<ProductCardRecord> cards = mongo.query(CatalogProduct.class)
        .as(ProductCardRecord.class)
        .matching(query)
        .all();
~~~

In a typed query, `id` is mapped to `_id` of the source entity according to mapping configuration. Verify via tests that the projection class receives all required constructor fields and handles `@Field` name mappings properly. Avoid calling `fields().exclude(...)` to drop a required constructor property and then being surprised when the DTO receives null or fails instantiation.

### DTOs Are Not Managed Entities

Spring Data MongoDB does not provide a JPA-style persistence context or identity map for DTOs. A returned DTO is a result snapshot and **does not automatically synchronize** when the source document changes. To update the database, use write APIs intended for the entity/collection with proper concurrency control rather than calling `save` on a field-incomplete DTO as if it were the full aggregate.

## 9. When the Query Creates a New Shape: Aggregation into a Record

Class-based DTO projections from `find` queries work well when selecting existing fields. However, if you need to **sum, group, rename, and combine data**, aggregation is usually clearer.

Example computing total stock by category for ACTIVE products:

**CategoryStockReport.java**

~~~java
package com.example.catalog;

public record CategoryStockReport(
        String category,
        long totalStock) {
}
~~~

Aggregation example:

~~~java
package com.example.catalog;

import java.util.List;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.aggregation.Aggregation;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.stereotype.Service;

import static org.springframework.data.mongodb.core.aggregation.Aggregation.*;

@Service
public class CategoryStockReportService {
    private final MongoTemplate mongo;

    public CategoryStockReportService(MongoTemplate mongo) {
        this.mongo = mongo;
    }

    public List<CategoryStockReport> activeStockByCategory() {
        Aggregation pipeline = newAggregation(
                match(Criteria.where("status").is("ACTIVE")),
                group("category").sum("stock").as("totalStock"),
                project("totalStock").and("_id").as("category"));

        return mongo.aggregate(
                pipeline, CatalogProduct.class, CategoryStockReport.class)
                .getMappedResults();
    }
}
~~~

Equivalent MongoDB pipeline meaning:

~~~javascript
db.catalog_products.aggregate([
  { $match: { status: "ACTIVE" } },
  {
    $group: {
      _id: "$category",
      totalStock: { $sum: "$stock" }
    }
  },
  {
    $project: {
      _id: 0,
      category: "$_id",
      totalStock: 1
    }
  }
]);
~~~

`CategoryStockReport` matches **the output shape of the aggregation**, not the source document shape. After the `$group` stage, the `_id` field of the grouped result represents the grouping key rather than a product ID. Therefore, an explicit `category` field must be projected.

The Java code and pipeline example illustrate the same **output semantics**; the framework may generate an equivalent yet slightly different projection structure. When mapping aggregations to records, pay attention to `$sum` types, null/missing values, and result field names. Do not use ordinary constructor DTO projections as a substitute for calculations that belong in the database.

## 10. DTOs, Nested Fields, and Projection Limits

### 10.1. Nested Fields Do Not Imply Nested DTO Projections

Suppose an entity has `SupplierInfo supplier` with `name`, `email`, and `address`. We want the DTO:

~~~java
public record SupplierMini(String name) {}
public record ProductWithSupplier(String id, SupplierMini supplier) {}
~~~

These two records are **output model examples**; you cannot assume a class-based DTO projection will automatically create nested DTO projections at each level the way interface-based nested projections do. In Spring Data, **class-based projections do not provide nested projection proxies** the way interface projections typically do.

Safe approaches:

1. Use interface-based nested projections if the query type and mapping mechanism support them, while measuring actual loaded fields.
2. Use `MongoTemplate` or aggregation `$project` to build the exact result shape and map it into the target type.
3. Return a flat DTO containing `supplierName` and assemble the API structure in the application layer.
4. If the full entity is already loaded, use a manual mapper; accept that this does not necessarily reduce I/O.

### 10.2. @Field and BSON Name Mapping

When an entity declares:

~~~java
@Field("display_name")
private String name;
~~~

the actual BSON field is `display_name`, while the Java property remains `name`. A DTO constructor using `name` must be verified against the entity's mapping metadata and the chosen projection type; do not rename the constructor parameter to `display_name` just because the collection uses snake_case.

Especially with raw JSON queries, custom DTOs, or aggregation `$project`, **field names in the output** may differ from the entity's field names. If a record has component `name` while the pipeline output returns `display_name`, project/map/alias to the matching name or use a tested converter.

### 10.3. Missing Fields, Nulls, and Primitives

A DTO with `long priceVnd` cannot accept `null` like a reference type. If the projection omits `priceVnd`, a legacy document is missing the field, or a converter does not match, materialization may fail or yield unintended values depending on the mapping path. For optional data, consider `Long` or a record with an explicit default policy.

For sensitive properties, **do not rely solely on DTOs to protect information**:

- Use only approved DTOs per API and verify permissions before querying.
- Inspect the actual field projection sent to MongoDB so sensitive data is not over-fetched.
- Do not log full entities/documents before mapping to DTOs.
- For multi-tenant systems, place `tenantId`/access criteria **in the query**, not just as post-query filtering.

## 11. Verifying BSON Projections and Returned Data

A test that merely checks a JSON response has three fields **does not prove** MongoDB only returned those three fields. You should verify three layers:

| Layer | What to verify | Technique |
|---|---|---|
| Repository/service | Exact `ProductCardRecord` type and values | Repository integration test |
| MongoDB command | Expected `filter`, `projection`, `sort`, `limit` are sent | Java Driver `CommandListener` or safe profiler |
| Server performance | Keys/documents examined, selected index, data volume returned | `explain("executionStats")` and metrics |

### 11.1. Integration Testing Records and Class DTOs

In Spring Boot 3.x, `@DataMongoTest` supports the Spring Data MongoDB test slice, but **does not start a MongoDB server by itself**. Provide a real MongoDB instance in the test environment, such as Testcontainers, with an isolated collection/database.

~~~java
package com.example.catalog;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;

@DataMongoTest
class CatalogProductProjectionTest {
    @Autowired
    CatalogProductRepository products;

    @BeforeEach
    void setUp() {
        products.deleteAll();
        products.save(new CatalogProduct(
                "prd-101",
                "Water Bottle 500 ml",
                "drinkware",
                129000,
                42,
                "ACTIVE",
                "Do not expose this note"));
    }

    @Test
    void recordProjectionContainsPublicFields() {
        ProductCardRecord card = products.findByStatus("ACTIVE")
                .get(0);

        assertThat(card.id()).isEqualTo("prd-101");
        assertThat(card.name()).isEqualTo("Water Bottle 500 ml");
        assertThat(card.priceVnd()).isEqualTo(129000);
    }

    @Test
    void classDtoAndDynamicProjectionReadExpectedValues() {
        ProductCardDto cheapest =
                products.findTop10ByStatusOrderByPriceVndAsc("ACTIVE")
                        .get(0);
        assertThat(cheapest.getName()).isEqualTo("Water Bottle 500 ml");

        ProductCardRecord dynamic =
                products.findByCategory(
                        "drinkware", ProductCardRecord.class).get(0);
        assertThat(dynamic.id()).isEqualTo("prd-101");

        CatalogProduct entity =
                products.findByCategory(
                        "drinkware", CatalogProduct.class).get(0);
        assertThat(entity.getInternalNote())
                .isEqualTo("Do not expose this note");
    }
}
~~~

This test verifies **construction and result mapping**, not driver-level field selection. Never run `deleteAll` on a database shared across parallel tests; isolate data or clean up by specific IDs.

### 11.2. Inspecting the Command Projection

The MongoDB Java Driver offers `CommandListener` receiving `CommandStartedEvent`. In tests, you can use `MongoClientSettingsBuilderCustomizer` to register a listener on the Spring Boot-created client and filter `find` commands targeting `catalog_products`.

A `find` command might contain:

~~~json
{
  "find": "catalog_products",
  "filter": { "status": "ACTIVE" },
  "projection": {
    "_id": 1,
    "name": 1,
    "priceVnd": 1
  }
}
~~~

This is **illustrative**. When capturing, inspect the *actual BSON document*: the driver may produce different expressions or syntax with the same effect. If the command has no `projection`, the query may be requesting all fields even though Java returns a DTO. In that case, use explicit query field selection or adjust the query path and measure again.

Do not enable logging of full production commands if filters contain user IDs, emails, payment data, or sensitive fields. Keep command capture restricted to tests, and avoid retaining listeners holding data across multiple tests/instances.

### 11.3. Checking Indexes and Data Volume

Example index supporting `status` filtering and sorting by price:

~~~javascript
db.catalog_products.createIndex(
  { status: 1, priceVnd: 1 },
  { name: "idx_status_price" }
);
~~~

Evaluating a query with projection:

~~~javascript
db.catalog_products.find(
  { status: "ACTIVE" },
  { _id: 1, name: 1, priceVnd: 1 }
).sort({ priceVnd: 1, _id: 1 })
 .explain("executionStats");
~~~

Projection **does not automatically guarantee a covered query**. To avoid fetching source documents purely from the index, filter, sort, and projection fields must all be covered by an appropriate index per MongoDB's capabilities, including `_id` if returned; a small compound index with only `status` and `priceVnd` is not enough to cover `name`. Creating wider indexes increases write overhead and storage, so only do it when the workload genuinely benefits.

## 12. DTOs in Reactive Access

With `ReactiveMongoRepository` and `ReactiveMongoTemplate`, projections can be expressed using `Flux`/`Mono` publishers when the query type and projection style are supported:

~~~java
package com.example.catalog;

import org.springframework.data.mongodb.repository.ReactiveMongoRepository;
import reactor.core.publisher.Flux;

public interface ReactiveCatalogProductRepository
        extends ReactiveMongoRepository<CatalogProduct, String> {

    Flux<ProductCardRecord> findByStatus(String status);
}
~~~

Reading example:

~~~java
Flux<ProductCardRecord> activeCards =
        reactiveProducts.findByStatus("ACTIVE");
~~~

In the example, `reactiveProducts` is a bean of type `ReactiveCatalogProductRepository`. The publisher is subscribed to by the appropriate calling layer; do not call `block()` on an event loop just to force DTOs into synchronous data.

**Projections do not alter database consistency guarantees.** If a product changes after being read, an already-constructed record does not update itself. Using DTOs/reactive access does not solve transactions, read concern, replica lag, or write contention; those topics must be handled at the appropriate business boundaries.

## 13. Common Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Returning full entity from an API when only a few fields are needed | Leaks extra state, couples to schema, large payloads | Use controlled DTOs and verify permissions |
| Assuming returning a record means MongoDB only sends three fields | Over-fetches data despite compact response | Inspect `projection` in the actual command |
| DTO constructor parameters do not match Java property names | Spring Data fails to select/map fields properly | Align names, metadata, and tests |
| Multiple constructors without specifying the materialization constructor | Wrong constructor picked or DTO creation fails | Use `@PersistenceCreator` or a single clear constructor |
| Forgetting `-parameters` for class DTOs using constructor binding | Missing parameter name metadata | Configure compilation properly and test |
| Confusing record accessors with JavaBean getters | Calling `getName()` on a record fails to compile | Use `name()` on records, `getName()` on class DTOs |
| Projection excludes a required constructor field | Record/class fails creation or misses data | Keep required fields or design nullable/default handling |
| Assuming class-based DTOs automatically support nested projections at all levels | Mapping errors or unintended loading of nested documents | Use interface nested projections, aggregation, or explicit mappers |
| Using a partial DTO to `save` the entity back | Lost state or corrupted updates | Use entities/targeted updates with concurrency control |
| Assuming Java records are deeply immutable | Nested lists/maps can still be mutated | Use defensive copies when needed |
| Aggregation `$group` returns `_id` while DTO expects another field name | DTO receives null or conversion fails | Use `$project` to alias output fields |
| Letting HTTP input arbitrarily pick the DTO class | Clients request types containing internal fields | Server controls the list of allowed projections |
| Running DTO tests without real MongoDB | Fails to verify BSON, driver, and query behavior | Isolated Testcontainers/MongoDB and command capture |

## 14. Practice Exercises

**Exercise 1 — Class DTO.** Create `ProductCardDto` with a constructor taking `id`, `name`, `priceVnd` and a convenience constructor. Mark `@PersistenceCreator` on the right constructor, declare a repository method returning `List<ProductCardDto>`, and verify all three values are populated correctly.

**Exercise 2 — Java record.** Convert the DTO from Exercise 1 to `ProductCardRecord`. Compare boilerplate, accessors, immutability, and `equals` behavior. Add a list component; try mutating the external list after record creation and propose defensive copying.

**Exercise 3 — Dynamic projection.** Declare `<T> List<T> findByCategory(String category, Class<T> type)`. Call it with the entity, class DTO, and record; explain when full state is needed and why `Class<T>` must not be exposed directly through a public API.

**Exercise 4 — Inspecting sent BSON.** Use a MongoDB `CommandListener` in tests to observe `find` when calling a repository method returning a record. Record `filter`, `projection`, and payload size. Try `MongoTemplate` fluent projection and compare results; never guess optimization levels from the return type alone.

**Exercise 5 — Mapping renamed fields.** Add `@Field("display_name")` on the entity's `name` property and prepare real MongoDB data. Test record projection, constructor DTO, and aggregation with `$project`. Write any required migration or alias if legacy data still stores `name`.

**Exercise 6 — Aggregation report.** Use `$match`, `$group`, and `$project` to compute stock per category; return `CategoryStockReport`. Test missing/null categories, verify sum types, and check document counts per result.

**Exercise 7 — Performance.** Create product data with a large notes field and compare: (a) loading entity then mapping manually, (b) repository DTO projection, (c) `MongoTemplate` with field selection. Measure bytes transferred, query time, conversion time, plan, and indexes, then decide on an approach.

## 15. Key Takeaways

In **Spring Data MongoDB**, **class-based DTO projections** rely on constructors and property names determined by Spring Data; `@PersistenceCreator` is helpful when a class has multiple constructors. **Java records** are a concise option for shallowly immutable DTOs with canonical constructors, accessors, and value semantics.

`MongoRepository` can return DTOs/records from derived queries and dynamic projections. `MongoTemplate` provides flexible criteria and field selection; `$project`/`$group` aggregations create a **new result shape** before mapping to a DTO.

Distinguish between a **lean DTO in Java/API** and a **BSON projection that actually saves read bandwidth**. Verify constructor metadata, BSON fields, null/missing data, nested mappings, sorting/pagination, and query plans via integration tests. Never use DTOs as a substitute for access control or to overwrite incomplete entities.
