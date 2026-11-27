# Aggregation with Spring Data and Result Mapping in MongoDB

The MongoDB Aggregation Framework processes data through a **multi-stage pipeline**. In Spring Boot applications using Spring Data MongoDB, developers do not always have to write the entire pipeline as manual BSON/JSON: you can use the **Aggregation API**, **Criteria**, **MongoTemplate**, operations like **project, group, sort, unwind, and lookup**, and map results into **Java DTOs or records**. This is well suited for revenue dashboards, order analytics, activity reports, time-series rollups, or joining data across collections.

Common pitfalls go beyond pipeline syntax. After **$group**, MongoDB places the grouping key inside **_id**; after **$project**, fields may be renamed or dropped; computed values may emerge as **Decimal128**, **Long**, **Double**, **Date**, or **null**. If the Java DTO does not match the actual output shape and types, Spring Data can miss fields, fail type conversions, or yield unexpected results. Furthermore, **@Field** on entities affects how Spring Data translates Java property names to BSON field names in certain aggregation styles.

This lesson belongs to the **Spring Data MongoDB** chapter and focuses simultaneously on **building correct pipelines**, **mapping results accurately**, and **controlling performance, resource lifecycles, and data integrity**.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain data flow across stages in a MongoDB aggregation pipeline.
2. Use **Aggregation.newAggregation(...)** and **MongoTemplate.aggregate(...)**.
3. Distinguish **Aggregation**, **TypedAggregation**, **AggregationOperation**, and **AggregationResults**.
4. Build pipelines using **$match, $project, $group, $sort, $limit, and $skip**.
5. Handle arrays with **$unwind**, joins with **$lookup**, and multi-branch reports with **$facet**.
6. Map grouping **_id** keys, aliases, Number/Date types, and nested documents into DTOs or Java records.
7. Understand the roles of **@Document**, **@Id**, and **@Field** in input mapping and collection selection.
8. Know when to use **Document**, custom stages, or **@Aggregation** on repositories.
9. Use **AggregationOptions**, streams, and cursors properly on large datasets.
10. Inspect output shapes, test on small datasets, and read `explain` plans to optimize pipelines.

**Scope:** Examples use Spring Data MongoDB with **MongoTemplate**, Java 17+, and a MongoDB server supporting the illustrated stages. APIs can vary across Spring Data and Spring Boot lines; in real projects, consult the official documentation and API reference for your exact dependency version. These examples are educational, not audited production financial/billing calculations.

## 2. How Does the Aggregation Framework Process Data?

A pipeline is an ordered sequence of stages:

~~~text
Collection orders
      |
      v
$match: select orders for the tenant with PAID status
      |
      v
$group: group by region, count and sum revenue
      |
      v
$project: rename _id to region, select returned fields
      |
      v
$sort: revenue descending
      |
      v
Result documents
      |
      v
Spring Data converter -> Java DTO
~~~

Each stage's output becomes the next stage's input. Consequently:

- **$match** before **$group** filters individual source documents.
- **$match** after **$group** filters **aggregated groups**, not raw source documents.
- **$project** can drop a field needed by a later stage.
- **$sort** before **$limit** yields a meaningful top-N; limiting before sorting only orders an arbitrary subset.
- **$unwind** multiplies document counts, meaning subsequent **count/sum** operations operate on unwound item rows.

### 2.1. Distinguishing find() from aggregate()

**find()** fits standard queries: filtering, projection, sorting, limiting, and reading documents.

**aggregate()** fits transforming data, computing aggregates, grouping, joining, branching, or producing output shapes distinct from input documents.

Example:

~~~javascript
db.orders.find({
  tenant_id: "TENANT-A",
  status: "PAID"
});
~~~

versus:

~~~javascript
db.orders.aggregate([
  { $match: { tenant_id: "TENANT-A", status: "PAID" } },
  {
    $group: {
      _id: "$region",
      orderCount: { $sum: 1 },
      revenue: { $sum: "$gross_amount" }
    }
  },
  { $project: { _id: 0, region: "$_id", orderCount: 1, revenue: 1 } },
  { $sort: { revenue: -1 } }
]);
~~~

The second example returns **one row per region**, rather than one row per order.

## 3. Setting Up Spring Data MongoDB

### 3.1. Dependency

In Spring Boot projects, typically use the starter:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-mongodb</artifactId>
</dependency>
~~~

Gradle Groovy DSL example:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-mongodb'
}
~~~

Let **Spring Boot BOM/dependency management** select compatible Spring Data MongoDB and Java Driver versions. Never pair a newer Spring Data release with an older MongoDB driver arbitrarily without verification.

### 3.2. Connection

Example **application.yml**:

~~~yaml
spring:
  data:
    mongodb:
      uri: ${MONGODB_URI}
~~~

The **MONGODB_URI** environment variable supplies the connection string from the runtime environment. Never place real credentials in source code, lessons, or logs. Some Spring Boot versions alter configuration property namespaces; check the documentation for your exact Boot version.

Spring Boot provides **MongoTemplate** as a bean via auto-configuration. A service can inject it:

~~~java
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.stereotype.Service;

@Service
public class ReportService {
    private final MongoTemplate mongoTemplate;

    public ReportService(MongoTemplate mongoTemplate) {
        this.mongoTemplate = mongoTemplate;
    }
}
~~~

Never create a new **MongoClient** for every report run. **MongoTemplate** and the client are managed for the application lifecycle.

### 3.3. Common Imports

~~~java
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.aggregation.Aggregation;
import org.springframework.data.mongodb.core.aggregation.AggregationResults;
import org.springframework.data.mongodb.core.aggregation.TypedAggregation;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.domain.Sort;

import static org.springframework.data.mongodb.core.aggregation.Aggregation.*;
~~~

Static imports keep pipelines concise:

~~~java
Aggregation agg = newAggregation(
        match(Criteria.where("status").is("PAID")),
        group("region").count().as("orderCount"),
        sort(Sort.Direction.DESC, "orderCount")
);
~~~

## 4. Sample Dataset: Multi-Tenant Orders

To keep outputs predictable, use the **spring_agg_lab.orders** collection in a **test database**. The data uses BSON field names differing from Java property names to illustrate mapping.

### 4.1. Sample Documents

~~~javascript
use spring_agg_lab

db.orders.insertMany([
  {
    _id: "O-1001",
    tenant_id: "TENANT-A",
    status: "PAID",
    region: "NORTH",
    gross_amount: NumberDecimal("120.50"),
    placed_at: ISODate("2026-10-01T09:00:00Z"),
    customer_ref: "C-1",
    items: [
      { sku: "BOOK-1", quantity: 2 },
      { sku: "PEN-1", quantity: 3 }
    ]
  },
  {
    _id: "O-1002",
    tenant_id: "TENANT-A",
    status: "PAID",
    region: "SOUTH",
    gross_amount: NumberDecimal("75.00"),
    placed_at: ISODate("2026-10-02T12:00:00Z"),
    customer_ref: "C-2",
    items: [{ sku: "BOOK-1", quantity: 1 }]
  },
  {
    _id: "O-1003",
    tenant_id: "TENANT-A",
    status: "NEW",
    region: "NORTH",
    gross_amount: NumberDecimal("10.00"),
    placed_at: ISODate("2026-10-03T08:00:00Z"),
    customer_ref: "C-1",
    items: [{ sku: "PEN-1", quantity: 1 }]
  },
  {
    _id: "O-1004",
    tenant_id: "TENANT-A",
    status: "PAID",
    region: "NORTH",
    gross_amount: NumberDecimal("60.25"),
    placed_at: ISODate("2026-10-04T16:00:00Z"),
    customer_ref: "C-3",
    items: [{ sku: "BAG-1", quantity: 1 }]
  },
  {
    _id: "O-1005",
    tenant_id: "TENANT-B",
    status: "PAID",
    region: "NORTH",
    gross_amount: NumberDecimal("999.00"),
    placed_at: ISODate("2026-10-05T09:00:00Z"),
    customer_ref: "C-B",
    items: [{ sku: "BOOK-1", quantity: 100 }]
  },
  {
    _id: "O-1006",
    tenant_id: "TENANT-A",
    status: "CANCELLED",
    region: "SOUTH",
    gross_amount: NumberDecimal("30.00"),
    placed_at: ISODate("2026-10-06T15:00:00Z"),
    customer_ref: "C-2",
    items: [{ sku: "PEN-1", quantity: 5 }]
  },
  {
    _id: "O-1007",
    tenant_id: "TENANT-A",
    status: "PAID",
    region: "SOUTH",
    gross_amount: NumberDecimal("40.00"),
    placed_at: ISODate("2026-10-07T10:00:00Z"),
    customer_ref: "C-2",
    items: [{ sku: "PEN-1", quantity: 4 }]
  },
  {
    _id: "O-1008",
    tenant_id: "TENANT-A",
    status: "PAID",
    region: "NORTH",
    gross_amount: NumberDecimal("24.25"),
    placed_at: ISODate("2026-10-08T14:00:00Z"),
    customer_ref: "C-1",
    items: [{ sku: "BOOK-1", quantity: 1 }]
  }
]);
~~~

**Note:** because **_id values are fixed**, re-running `insertMany` on the same collection causes a duplicate key error. Run once in a clean lab or use controlled upserts; **never delete production data** to run examples.

### 4.2. Expected Results

Considering only **TENANT-A** and **PAID**, there are **5 orders**:

| Region | Orders | orderCount | revenue |
|---|---|---:|---:|
| NORTH | O-1001, O-1004, O-1008 | 3 | 205.00 |
| SOUTH | O-1002, O-1007 | 2 | 115.00 |

Order **O-1005** from **TENANT-B** must be excluded despite its large revenue; **NEW** and **CANCELLED** orders must also be excluded. This serves as a **tenant isolation** check as well.

### 4.3. Creating an Index for the Query Pattern

~~~javascript
db.orders.createIndex({
  tenant_id: 1,
  status: 1,
  placed_at: -1
});
~~~

This index reflects a realistic query filtering by tenant, status, and time range. Whether the index is chosen, its cost, and its benefit for a given pipeline must be verified with `explain`; adding an index does not automatically make every `$group` or `$sort` stage fast.

## 5. Mapping MongoDB Documents to the Java Domain Model

Spring Data MongoDB distinguishes **Java property names** from **BSON field names**. This is critical for `TypedAggregation`.

### 5.1. Entity for Orders

~~~java
import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;

import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;
import org.springframework.data.mongodb.core.mapping.FieldType;

@Document("orders")
public class OrderEntity {
    @Id
    private String id;

    @Field("tenant_id")
    private String tenantId;

    private String status;
    private String region;

    @Field(value = "gross_amount", targetType = FieldType.DECIMAL128)
    private BigDecimal grossAmount;

    @Field("placed_at")
    private Instant placedAt;

    @Field("customer_ref")
    private String customerRef;

    private List<OrderLine> items;

    public OrderEntity() {
    }

    // Getters/setters or constructor binding per project standard.
}

public class OrderLine {
    private String sku;
    private int quantity;

    public OrderLine() {
    }

    // Getters/setters.
}
~~~

In a real Java project, each public top-level class belongs in **its own file**; both declarations appear in one block here for readability.

**Key points:**

- Property **tenantId** maps to BSON field **tenant_id**.
- Property **grossAmount** maps to **gross_amount**, stored as **Decimal128** in the sample data.
- Property **placedAt** maps to **placed_at**.
- **@Document("orders")** specifies the default collection when using the domain type.
- **@Id** corresponds to **_id**.

In typed aggregations, Spring Data uses entity metadata to translate Java field references to BSON names. If you write raw JSON, make sure you understand when that mapping applies.

## 6. Four Core Concepts of the Spring Data Aggregation API

| Component | Role |
|---|---|
| **AggregationOperation** | Represents a single pipeline stage, e.g., match/group/project |
| **Aggregation** | Holds the full pipeline and execution options |
| **TypedAggregation<T>** | Aggregation bound to an input domain class for field mapping |
| **AggregationResults<R>** | Wraps mapped result objects and raw response metadata |

Overview:

~~~text
Java domain / input collection
              |
              v
newAggregation(operation1, operation2, ...)
              |
              v
MongoTemplate.aggregate(...)
              |
              v
MongoDB executes BSON pipeline
              |
              v
AggregationResults<ResultDto>
              |
              +--> getMappedResults()
              +--> getUniqueMappedResult()
              +--> getRawResults()
~~~

**An `Aggregation` object does not execute the query by itself**; it describes the pipeline. **`MongoTemplate.aggregate(...)`** dispatches the command through the driver and runs it.

### 6.1. Without an Input Class

~~~java
Aggregation agg = newAggregation(
        match(Criteria.where("status").is("PAID")),
        group("region").count().as("orderCount")
);

AggregationResults<Document> results =
        mongoTemplate.aggregate(agg, "orders", Document.class);
~~~

In this variant, you must pass the **collection name `"orders"`** explicitly because the aggregation has no input class. Field names in the pipeline must match the stored BSON names directly.

### 6.2. With an Input Class

~~~java
TypedAggregation<OrderEntity> agg = newAggregation(
        OrderEntity.class,
        match(Criteria.where("tenantId").is("TENANT-A")),
        group("region").count().as("orderCount")
);

AggregationResults<Document> results =
        mongoTemplate.aggregate(agg, Document.class);
~~~

Here Spring Data receives **`OrderEntity`**, derives the collection **`orders`**, and translates **`tenantId`** to **`tenant_id`**.

Since Spring Data MongoDB 3.2, referencing a non-existent field or property inside a typed aggregation **no longer throws an exception by default**. For strict validation, check **`AggregationOptions.strictMapping()`** in your version.

## 7. Complete Example: Calculating Revenue by Region

### 7.1. Target MongoDB Pipeline

Before writing Java code, define the expected result with raw MongoDB aggregation:

~~~javascript
db.orders.aggregate([
  { $match: { tenant_id: "TENANT-A", status: "PAID" } },
  {
    $group: {
      _id: "$region",
      orderCount: { $sum: 1 },
      revenue: { $sum: "$gross_amount" }
    }
  },
  {
    $project: {
      _id: 0,
      region: "$_id",
      orderCount: 1,
      revenue: 1
    }
  },
  { $sort: { revenue: -1 } }
]);
~~~

Expected output:

~~~javascript
[
  { region: "NORTH", orderCount: 3, revenue: NumberDecimal("205.00") },
  { region: "SOUTH", orderCount: 2, revenue: NumberDecimal("115.00") }
]
~~~

**Key detail:** `$group` places the region value into **`_id`**. `$project` then renames **`_id` to `region`** so the DTO maps cleanly.

### 7.2. DTO as a Java Record

With Java 17+ and Spring Data MongoDB constructor/record mapping:

~~~java
import java.math.BigDecimal;

public record RegionRevenue(
        String region,
        long orderCount,
        BigDecimal revenue
) {
}
~~~

This is an **output DTO**, not the `OrderEntity` input entity. Because the pipeline emits **region**, **orderCount**, and **revenue**, the record declares those exact names.

### 7.3. Reporting Repository Using TypedAggregation

~~~java
import java.util.List;

import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.aggregation.AggregationResults;
import org.springframework.data.mongodb.core.aggregation.TypedAggregation;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.stereotype.Repository;

import static org.springframework.data.mongodb.core.aggregation.Aggregation.*;

@Repository
public class OrderAnalyticsRepository {
    private final MongoTemplate mongoTemplate;

    public OrderAnalyticsRepository(MongoTemplate mongoTemplate) {
        this.mongoTemplate = mongoTemplate;
    }

    public List<RegionRevenue> revenueByRegion(String tenantId) {
        if (tenantId == null || tenantId.isBlank()) {
            throw new IllegalArgumentException("tenantId is required");
        }

        TypedAggregation<OrderEntity> aggregation = newAggregation(
                OrderEntity.class,
                match(Criteria.where("tenantId").is(tenantId)
                        .and("status").is("PAID")),
                group("region")
                        .count().as("orderCount")
                        .sum("grossAmount").as("revenue"),
                project("orderCount", "revenue")
                        .and("_id").as("region")
                        .andExclude("_id"),
                sort(Sort.Direction.DESC, "revenue")
        );

        AggregationResults<RegionRevenue> results =
                mongoTemplate.aggregate(
                        aggregation, RegionRevenue.class);

        return results.getMappedResults();
    }
}
~~~

**Component breakdown:**

1. **`newAggregation(OrderEntity.class, ...)`** tells Spring Data the input domain type and field mappings.
2. **`Criteria.where("tenantId")`** uses the Java property; typed mapping translates it to BSON **`tenant_id`**.
3. **`group("region")`** groups by region.
4. **`count().as("orderCount")`** counts orders per group.
5. **`sum("grossAmount").as("revenue")`** sums the mapped BSON **`gross_amount`** field.
6. **`project(...).and("_id").as("region")`** flattens the grouping key into the DTO field.
7. **`andExclude("_id")`** drops `_id` from the final output.
8. **`sort(DESC, "revenue")`** sorts by the alias emitted by `$group`, not a source field.
9. **`getMappedResults()`** returns the list of Java records.

In multi-tenant services, `tenantId` **must come from the authentication/authorization context**—never trust a caller-supplied `tenantId` without validation.

### 7.4. Why Not Just Map _id Directly to region?

If you omit the `$project` stage:

~~~javascript
{ _id: "NORTH", orderCount: 3, revenue: NumberDecimal("205.00") }
~~~

then **`RegionRevenue(String region, ...)`** has no `region` field in BSON to read directly. While you could declare `_id` on the DTO or use annotations/constructor mapping, projecting **`_id` → `region`** inside the pipeline keeps the report contract explicit, stable, and free of implicit mapping assumptions.

### 7.5. Never Map Group Results Back into OrderEntity

After `$group`, the output no longer contains `id`, `tenantId`, `grossAmount`, `placedAt`, or `OrderEntity`'s shape. Calling:

~~~java
mongoTemplate.aggregate(aggregation, OrderEntity.class);
~~~

produces entities full of **null/default** fields, drops `revenue` and `orderCount`, or triggers mapping errors. Always use a **dedicated output DTO** matching the final stage shape (or **`Document`** while exploring).

## 8. AggregationResults and Extracting Output

**AggregationResults<T>** holds both mapped objects and the raw driver response.

~~~java
AggregationResults<RegionRevenue> results =
        mongoTemplate.aggregate(
                aggregation, RegionRevenue.class);

List<RegionRevenue> rows = results.getMappedResults();
org.bson.Document raw = results.getRawResults();
~~~

Key methods:

| Method | Meaning |
|---|---|
| **getMappedResults()** | List of mapped DTOs; empty list if zero rows |
| **getUniqueMappedResult()** | Single object or `null`; throws `IllegalArgumentException` if more than one row |
| **getRawResults()** | Driver-level raw `Document` response, useful for diagnostics |
| **iterator()** | Iterates over mapped objects in `AggregationResults` |

### 8.1. When to Use getUniqueMappedResult()?

A pipeline that **does not group by region**, instead computing a tenant-wide total:

~~~java
Aggregation agg = newAggregation(
        match(Criteria.where("tenant_id").is("TENANT-A")
                .and("status").is("PAID")),
        group()
                .count().as("orderCount")
                .sum("gross_amount").as("revenue"),
        project("orderCount", "revenue").andExclude("_id")
);

AggregationResults<TotalRevenue> results =
        mongoTemplate.aggregate(agg, "orders", TotalRevenue.class);

TotalRevenue total = results.getUniqueMappedResult();
~~~

DTO:

~~~java
import java.math.BigDecimal;

public record TotalRevenue(
        long orderCount,
        BigDecimal revenue
) {}
~~~

On the sample data, expected output is:

~~~javascript
{ orderCount: 5, revenue: NumberDecimal("320.00") }
~~~

Here **`group()`** aggregates all matching documents into a single summary group (returning one row or zero rows). Never call `getUniqueMappedResult()` on a **per-region** report, which can return multiple rows.

### 8.2. Empty Results Differ from Zero

If zero orders match, a **`$group` pipeline with empty input** produces **zero documents**—not a document with `revenue = 0`. Your reporting API must decide whether to:

- Return an empty list.
- Return a zeroed totals DTO per business contract.
- Return a report envelope with a **`NO_DATA`** status.

Never call **`getUniqueMappedResult().revenue()`** when the result can be `null`.

### 8.3. RawResults Is for Diagnostics, Not Public APIs

Never return **`getRawResults()`** straight to HTTP clients just for convenience; it exposes internal command metadata, raw BSON structures, or sensitive data. Always return a controlled DTO.

## 9. $match with Criteria: Before vs. After Group

### 9.1. Match at the Start of the Pipeline

~~~java
match(Criteria.where("tenantId").is(tenantId)
        .and("status").is("PAID"))
~~~

In **`TypedAggregation<OrderEntity>`**, `tenantId` maps to `tenant_id` via **`@Field`**. With an untyped **`Aggregation`** and a raw collection name, you must write:

~~~java
match(Criteria.where("tenant_id").is(tenantId)
        .and("status").is("PAID"))
~~~

This is a very common bug: a pipeline returns **zero matches** because Java property names were passed into an untyped BSON pipeline expecting actual stored field names.

### 9.2. Match After Group Filters Aggregated Groups

For example, keeping only regions with `revenue >= 150`:

~~~java
TypedAggregation<OrderEntity> agg = newAggregation(
        OrderEntity.class,
        match(Criteria.where("tenantId").is("TENANT-A")
                .and("status").is("PAID")),
        group("region")
                .sum("grossAmount").as("revenue")
                .count().as("orderCount"),
        match(Criteria.where("revenue").gte(
                new java.math.BigDecimal("150.00"))),
        project("revenue", "orderCount")
                .and("_id").as("region")
                .andExclude("_id")
);
~~~

On the sample dataset, only **NORTH** satisfies `>= 150`. The second `$match` references **`revenue`**, the group output alias, not the source property **`grossAmount`**.

### 9.3. Never Defer Security Filters After $lookup or to the End of a Pipeline

A pipeline might return only the right tenant's final rows while still scanning or joining vast unauthorized data beforehand. For multi-tenant workloads, apply the **mandatory tenant filter** as early as semantics allow, and verify access controls on every joined collection.

Never assume "the final output has the right `tenantId`" proves intermediate stages never processed unauthorized records. Design authorization before execution.

## 10. $project and Field Aliases

**$project** selects fields, renames fields, and computes expression fields. Fields dropped in one stage are generally unavailable in subsequent stages.

### 10.1. Selecting and Renaming Fields

~~~java
Aggregation agg = newAggregation(
        match(Criteria.where("status").is("PAID")),
        project()
                .and("_id").as("orderId")
                .and("gross_amount").as("amount")
                .and("region").as("region")
                .andExclude("_id")
);
~~~

With this untyped pipeline, output is:

~~~javascript
{
  orderId: "O-1001",
  amount: NumberDecimal("120.50"),
  region: "NORTH"
}
~~~

### 10.2. Fields Dropped by Project

~~~text
Input:
  _id, tenant_id, region, status, gross_amount

$project:
  region, gross_amount

Next stage:
  status no longer exists
~~~

If filtering on `status`, place **`$match` before `$project`** when semantics match so indexes can be used.

### 10.3. Computing Fields with Expressions

MongoDB aggregation offers expression operators such as **$add, $multiply, $cond, $ifNull, and $dateToString**. Spring Data provides builders in **ArithmeticOperators**, **ConditionalOperators**, and **DateOperators**, plus fluent projection arithmetic APIs.

Illustrative arithmetic example (not for production tax/billing):

~~~java
Aggregation agg = newAggregation(
        project("region")
                .and("gross_amount")
                .multiply(2)
                .as("doubleAmount")
);
~~~

This creates **`doubleAmount`** from BSON field `gross_amount`. With a typed input, you can reference **`grossAmount`** instead of BSON **`gross_amount`**.

**Watch numeric types:** integer, double, or `Decimal128` multipliers affect result types. Never mix `Double` into production monetary arithmetic without defined rounding and scale policies.

### 10.4. previousOperation() and _id

Spring Data offers syntax to project the grouping key from the preceding group stage:

~~~java
Aggregation agg = newAggregation(
        group("region").count().as("n"),
        project("n").and("region").previousOperation()
);
~~~

This Spring Data idiom binds the previous group key to an alias. Alternatively, **`.and("_id").as("region")`** mirrors raw MongoDB pipelines directly. Pick one clear convention and verify the emitted `Document`.

## 11. $group and Aggregate Data Types

Common accumulators:

| Spring Data GroupOperation | MongoDB Accumulator | Meaning |
|---|---|---|
| **count().as("n")** | `$sum: 1` | Count documents in group |
| **sum("grossAmount").as("total")** | `$sum` | Numeric sum |
| **avg("grossAmount").as("average")** | `$avg` | Arithmetic mean |
| **min("grossAmount").as("minimum")** | `$min` | Minimum value |
| **max("grossAmount").as("maximum")** | `$max` | Maximum value |
| **first("field").as("firstValue")** | `$first` | First value in input order |
| **last("field").as("lastValue")** | `$last` | Last value in input order |
| **push("field").as("values")** | `$push` | Collect values into array |
| **addToSet("field").as("uniqueValues")** | `$addToSet` | Collect distinct values per MongoDB semantics |

### 11.1. Grouping by Multiple Fields

~~~javascript
{
  $group: {
    _id: { region: "$region", status: "$status" },
    n: { $sum: 1 }
  }
}
~~~

In Spring Data:

~~~java
group("region", "status")
        .count().as("n")
~~~

The output **`_id` is an object**:

~~~javascript
{ _id: { region: "NORTH", status: "PAID" }, n: 3 }
~~~

Do not map this object `_id` straight into **`String id`**. Use a nested DTO or project flattened fields:

~~~javascript
{
  $project: {
    _id: 0,
    region: "$_id.region",
    status: "$_id.status",
    n: 1
  }
}
~~~

When using Spring Data's projection builder, reference the exact nested **`_id`** paths produced by `$group`; for complex alias mappings, inspect the output with **`Document`** first before finalizing the DTO.

### 11.2. $first/$last Require Meaningful Ordering

To find the first/last order per region, you must **`$sort` before `$group`** when semantics rely on order:

~~~javascript
[
  { $sort: { placed_at: 1, _id: 1 } },
  {
    $group: {
      _id: "$region",
      firstOrder: { $first: "$_id" },
      lastOrder: { $last: "$_id" }
    }
  }
]
~~~

Never assume `$first` returns the "earliest date" without an upstream sort or a dedicated accumulator.

### 11.3. $sum Does Not Convert Strings into Numbers

If legacy documents store `gross_amount` as **`"120.50"`** (String), `$sum` will not produce a reliable numeric sum like `Decimal128`. Standardize schemas, validate types, and run migrations instead of adding ad-hoc runtime casts without error checks.

## 12. $unwind: Turning Each Array Element into a Row

An order contains:

~~~javascript
{
  _id: "O-1001",
  items: [
    { sku: "BOOK-1", quantity: 2 },
    { sku: "PEN-1", quantity: 3 }
  ]
}
~~~

**`$unwind: "$items"`** emits two pipeline documents:

~~~javascript
{ _id: "O-1001", items: { sku: "BOOK-1", quantity: 2 } }
{ _id: "O-1001", items: { sku: "PEN-1", quantity: 3 } }
~~~

### 12.1. Summing Quantities Sold by SKU

Raw MongoDB:

~~~javascript
db.orders.aggregate([
  { $match: { tenant_id: "TENANT-A", status: "PAID" } },
  { $unwind: "$items" },
  {
    $group: {
      _id: "$items.sku",
      quantitySold: { $sum: "$items.quantity" }
    }
  },
  { $project: { _id: 0, sku: "$_id", quantitySold: 1 } },
  { $sort: { quantitySold: -1, sku: 1 } }
]);
~~~

Spring Data:

~~~java
TypedAggregation<OrderEntity> agg = newAggregation(
        OrderEntity.class,
        match(Criteria.where("tenantId").is("TENANT-A")
                .and("status").is("PAID")),
        unwind("items"),
        group("items.sku")
                .sum("items.quantity").as("quantitySold"),
        project("quantitySold")
                .and("_id").as("sku")
                .andExclude("_id"),
        sort(Sort.by(
                Sort.Order.desc("quantitySold"),
                Sort.Order.asc("sku")))
);

List<SkuSales> rows = mongoTemplate
        .aggregate(agg, SkuSales.class)
        .getMappedResults();
~~~

DTO:

~~~java
public record SkuSales(String sku, long quantitySold) {}
~~~

On the sample dataset:

| SKU | Quantity sold |
|---|---:|
| PEN-1 | 7 |
| BOOK-1 | 4 |
| BAG-1 | 1 |

Calculated from **PAID orders in TENANT-A**: `PEN-1` = 3+4; `BOOK-1` = 2+1+1; `BAG-1` = 1.

### 12.2. Double-Counting Orders After Unwind

If you count:

~~~javascript
[
  { $unwind: "$items" },
  { $group: { _id: "$region", orderCount: { $sum: 1 } } }
]
~~~

then **`orderCount`** counts **item rows** after unwind, **not distinct orders**. An order with five items contributes five to the count. To count distinct orders, group by order ID first, collect `addToSet(orderId)` and take its size where appropriate, or structure the pipeline to avoid inflation.

### 12.3. preserveNullAndEmptyArrays

When a document lacks `items` or has `items: []`, default `$unwind` drops that document from the pipeline. To retain it:

~~~java
unwind("items", true)
~~~

In Spring Data versions supporting this overload, **`true`** enables `preserveNullAndEmptyArrays`. Subsequent stages must then handle **`items = null/missing`** without treating absent values as valid data.

### 12.4. Include Array Index

MongoDB supports **`includeArrayIndex`** to preserve each element's original array index. Spring Data provides builders/overloads on `UnwindOperation` depending on version. Use this only when **original element position** matters; do not assume elements retain an array index automatically after unwind.

## 13. $lookup: Joining Data Across Collections

Create a small `customers` collection:

~~~javascript
db.customers.insertMany([
  {
    _id: "C-1",
    tenant_id: "TENANT-A",
    name: "An",
    tier: "GOLD"
  },
  {
    _id: "C-2",
    tenant_id: "TENANT-A",
    name: "Binh",
    tier: "STANDARD"
  },
  {
    _id: "C-3",
    tenant_id: "TENANT-A",
    name: "Chi",
    tier: "GOLD"
  },
  {
    _id: "C-B",
    tenant_id: "TENANT-B",
    name: "Other tenant",
    tier: "PRIVATE"
  }
]);
~~~

### 13.1. Simple Lookup

Each order has **`customer_ref`**, pointing to **`customers._id`**.

~~~javascript
db.orders.aggregate([
  { $match: { tenant_id: "TENANT-A", status: "PAID" } },
  {
    $lookup: {
      from: "customers",
      localField: "customer_ref",
      foreignField: "_id",
      as: "customer"
    }
  },
  { $unwind: "$customer" },
  {
    $project: {
      _id: 0,
      orderId: "$_id",
      customerName: "$customer.name",
      region: 1
    }
  }
]);
~~~

Spring Data:

~~~java
TypedAggregation<OrderEntity> agg = newAggregation(
        OrderEntity.class,
        match(Criteria.where("tenantId").is("TENANT-A")
                .and("status").is("PAID")),
        lookup("customers", "customerRef", "_id", "customer"),
        unwind("customer"),
        project("region")
                .and("_id").as("orderId")
                .and("customer.name").as("customerName")
                .andExclude("_id")
);
~~~

DTO:

~~~java
public record OrderCustomerRow(
        String orderId,
        String region,
        String customerName
) {}
~~~

**Mapping note:** inside **`TypedAggregation<OrderEntity>`**, Spring Data translates **`customerRef`** to **`customer_ref`** via `@Field`. In raw/untyped pipelines, use exact stored BSON names. For `$lookup` output, **`customer`** is a stage-created alias, not a pre-existing property on `OrderEntity`.

### 13.2. $lookup Always Returns an Array

Even when joining to a single customer by `_id`, the output of **`$lookup`** is an **array**:

~~~javascript
{
  _id: "O-1001",
  customer: [
    { _id: "C-1", name: "An", tier: "GOLD" }
  ]
}
~~~

**`$unwind("customer")`** flattens the single-element array into an object so the DTO can read **`customerName`** cleanly. If a customer is missing, default unwind drops the order; to keep the order, use `preserveNullAndEmptyArrays` and make `customerName` nullable in the DTO.

### 13.3. Preventing Cross-Tenant Leaks in Lookups

In this example, customer IDs are globally unique, reducing accidental cross-joins. In production, however, external IDs may only be unique **within a tenant**, or data may drift.

Ensure joins enforce:

- Orders match the authenticated tenant.
- Joined customers also match the same tenant or authorized ACL.
- Clients never pass arbitrary collection names or join keys.
- Projections emit only fields the user is authorized to view.
- When complex join conditions are needed, use the **pipeline form of `$lookup`** and verify indexes and correctness.

Never assume matching `orders.tenantId` alone guarantees every record in `customers` is safe to join.

### 13.4. Lookup Performance

An index on **`foreignField`** in the foreign collection is crucial. With **`foreignField="_id"`**, MongoDB already has the `_id` index. When joining on another field, index it for the query pattern. High-cardinality joins can explode pipeline memory; never use `$lookup` to join two entire collections without upfront filters and limits.

## 14. $facet: Multiple Reports in One Pipeline

**$facet** runs multiple subpipelines over the same input document stream—for instance, a dashboard needing both regional revenue and order counts by status.

### 14.1. Structured Output

~~~javascript
{
  revenueByRegion: [
    { region: "NORTH", revenue: NumberDecimal("205.00") },
    { region: "SOUTH", revenue: NumberDecimal("115.00") }
  ],
  statusCounts: [
    { status: "PAID", count: 5 },
    { status: "NEW", count: 1 },
    { status: "CANCELLED", count: 1 }
  ]
}
~~~

Note: if an initial `$match` filters only **PAID**, the **`statusCounts`** branch **cannot count NEW or CANCELLED orders**. To retain all statuses, filter only by **tenant** before `$facet`, and apply branch-specific filters inside each facet branch.

### 14.2. Facet in Spring Data

~~~java
Aggregation agg = newAggregation(
        match(Criteria.where("tenant_id").is("TENANT-A")),
        facet(
                match(Criteria.where("status").is("PAID")),
                group("region").sum("gross_amount").as("revenue"),
                project("revenue")
                        .and("_id").as("region")
                        .andExclude("_id")
        ).as("revenueByRegion")
         .and(
                group("status").count().as("count"),
                project("count")
                        .and("_id").as("status")
                        .andExclude("_id")
        ).as("statusCounts")
);

AggregationResults<Document> result =
        mongoTemplate.aggregate(agg, "orders", Document.class);

Document dashboard = result.getUniqueMappedResult();
~~~

Here **`Document`** illustrates the nested arrays; below we design a typed DTO for nested output. Although facet branches share an input stream, never assume one `$facet` is always faster than separate queries—evaluate execution cost and stage memory limits.

### 14.3. $facet Has Different Limits from $group

**$facet** emits a single document containing all output arrays. Watch the 16 MiB BSON document size limit and stage memory constraints. **`allowDiskUse`** does not lift every internal `$facet` limit. Never stuff hundreds of thousands of raw documents into a facet array to send straight to a UI.

## 15. $bucket and $bucketAuto for Distribution Reports

**$bucket** groups documents into explicit boundary ranges, such as order value tiers. **$bucketAuto** asks MongoDB to automatically partition data into roughly equal-sized buckets.

Raw MongoDB:

~~~javascript
db.orders.aggregate([
  { $match: { tenant_id: "TENANT-A", status: "PAID" } },
  {
    $bucket: {
      groupBy: "$gross_amount",
      boundaries: [
        NumberDecimal("0"),
        NumberDecimal("50"),
        NumberDecimal("100"),
        NumberDecimal("200")
      ],
      default: "OTHER",
      output: {
        count: { $sum: 1 }
      }
    }
  }
]);
~~~

Spring Data provides **`bucket(...)`** and **`bucketAuto(...)`** builders. Boundaries must use matching BSON types and respect MongoDB's lower-inclusive/upper-exclusive semantics; out-of-range values go into **`default`** when specified. A bucket result can return **`_id` as either a Number or a String** (when `default: "OTHER"` is used), so do not map `_id` blindly to a Java `Integer`.

### 15.1. Why Are Buckets Useful?

A distribution report needs counts per range:

~~~text
[0, 50)
[50, 100)
[100, 200)
OTHER
~~~

This differs from `$group` on exact `gross_amount`, which creates a separate group for every distinct amount. Choose explicit boundaries from business rules and data analysis rather than relying solely on `bucketAuto` when financial reports demand fixed price bands.

## 16. Conditional Expressions and Null Handling

In many datasets, **`discount`** can be missing or null; adding or subtracting directly can yield `null` or fail depending on operators and types.

### 16.1. $ifNull in MongoDB

~~~javascript
db.orders.aggregate([
  {
    $project: {
      _id: 1,
      discountSafe: {
        $ifNull: ["$discount", NumberDecimal("0")]
      }
    }
  }
]);
~~~

Spring Data offers **`ConditionalOperators.IfNull`** and conditional builders. Depending on version, you can write:

~~~java
import org.springframework.data.mongodb.core.aggregation.ConditionalOperators;

Aggregation agg = newAggregation(
        project()
                .and(ConditionalOperators.ifNull("discount")
                        .then(0))
                .as("discountSafe")
);
~~~

When monetary fields require `Decimal128`, an integer fallback **`0`** in a snippet is purely illustrative; supply a matching decimal value and conversion so subsequent arithmetic preserves type and precision.

### 16.2. $cond and Conditional Classification

Raw MongoDB example:

~~~javascript
{
  $project: {
    label: {
      $cond: [
        { $gte: ["$gross_amount", NumberDecimal("100")] },
        "LARGE",
        "SMALL"
      ]
    }
  }
}
~~~

Spring Data provides **`ConditionalOperators.when(...).then(...).otherwise(...)`**. Ensure expressions reference fields that actually exist at that stage, especially after earlier `$project` or rename steps.

### 16.3. Null and Missing Fields in DTOs

Example projection:

~~~javascript
{ region: "NORTH", revenue: null }
~~~

If the DTO declares **`long revenue`**, `null` has no primitive representation; mapping failures or silent zero defaults can mask missing data. Prefer nullable **`Long`/`BigDecimal`** when outputs can be null or missing, or normalize defaults explicitly in the pipeline and verify with tests.

Never equate null revenue with `0` in business logic if `null` means **no data yet** or **unable to compute**.

## 17. Mapping Output DTOs: Align Field Names with the Pipeline

**Result mapping** is separate from **domain input mapping**. Spring Data converts the BSON documents emitted by the aggregation into instances of **`outputType`**.

### 17.1. Inspect Output Shape Before Defining the DTO

Example MongoDB output:

~~~javascript
{
  region: "NORTH",
  orderCount: NumberLong(3),
  revenue: NumberDecimal("205.00")
}
~~~

Matching DTO:

~~~java
public record RegionRevenue(
        String region,
        long orderCount,
        java.math.BigDecimal revenue
) {}
~~~

Avoid:

~~~java
public record RegionRevenue(
        String area,
        int numberOfOrders,
        double totalPrice
) {}
~~~

unless the pipeline aliases those exact names or custom conversions are configured. In the second DTO, **`area`**, **`numberOfOrders`**, and **`totalPrice`** mismatch the output fields, and **`double`** risks monetary precision loss.

### 17.2. Record Constructor Mapping

A Java **record** is an immutable type with a canonical constructor. Modern Spring Data MongoDB supports constructor/record mapping when constructor parameter names and field mappings align cleanly.

Advantages:

- Concise DTOs with minimal boilerplate.
- Explicit output fields.
- Clean fit for read models and API responses.

Still, **records do not eliminate null or type-mismatch bugs**. If the pipeline omits **`region`** or emits **`revenue`** as a `String`, mapping can fail or yield unexpected values.

### 17.3. Class-Based Java DTOs

If the codebase does not use records yet:

~~~java
import java.math.BigDecimal;

public class RegionRevenueDto {
    private String region;
    private long orderCount;
    private BigDecimal revenue;

    public RegionRevenueDto() {
    }

    public String getRegion() {
        return region;
    }

    public void setRegion(String region) {
        this.region = region;
    }

    public long getOrderCount() {
        return orderCount;
    }

    public void setOrderCount(long orderCount) {
        this.orderCount = orderCount;
    }

    public BigDecimal getRevenue() {
        return revenue;
    }

    public void setRevenue(BigDecimal revenue) {
        this.revenue = revenue;
    }
}
~~~

Ensure constructors and property accessors align with **`MappingMongoConverter`** and project conventions.

### 17.4. Nested DTOs for $facet

Facet returns **a single document holding nested arrays**:

~~~javascript
{
  revenueByRegion: [
    { region: "NORTH", revenue: NumberDecimal("205.00") },
    { region: "SOUTH", revenue: NumberDecimal("115.00") }
  ],
  statusCounts: [
    { status: "PAID", count: 5 },
    { status: "NEW", count: 1 },
    { status: "CANCELLED", count: 1 }
  ]
}
~~~

Define:

~~~java
import java.math.BigDecimal;
import java.util.List;

public record DashboardReport(
        List<RegionTotal> revenueByRegion,
        List<StatusCount> statusCounts
) {}

public record RegionTotal(
        String region,
        BigDecimal revenue
) {}

public record StatusCount(
        String status,
        long count
) {}
~~~

In production code, place each public record in **its own `.java` file**. The Spring Data converter maps nested arrays into `List`s when BSON shapes match and record mapping is supported.

~~~java
AggregationResults<DashboardReport> results =
        mongoTemplate.aggregate(
                agg, "orders", DashboardReport.class);

DashboardReport dashboard = results.getUniqueMappedResult();
~~~

Do not map a facet result directly to **`List<RegionRevenue>`**, because the **top-level document** is a single wrapper holding multiple arrays rather than one region per document.

### 17.5. Nested DTOs from $lookup

Without `$unwind`/`$project`:

~~~javascript
{
  _id: "O-1001",
  customer: [
    { _id: "C-1", name: "An", tier: "GOLD" }
  ]
}
~~~

the DTO must hold a collection:

~~~java
public record CustomerSummary(
        String id,
        String name,
        String tier
) {}

public record OrderJoinResult(
        String id,
        java.util.List<CustomerSummary> customer
) {}
~~~

Note that `_id` on both the joined customer and the order must map to **`id`** via Spring Data conventions or explicit projections/annotations. To avoid relying on implicit mapping, project **`orderId`, `customerId`, and `customerName`** explicitly.

## 18. Numeric Mapping: Int32, Int64, Double, Decimal128

MongoDB supports multiple BSON numeric types:

| MongoDB/BSON | Raw Java Driver | Typical Java DTO | Risk |
|---|---|---|---|
| Int32 | `Integer` | `int`/`Integer` | Potential overflow |
| Int64 | `Long` | `long`/`Long` | Primitives cannot hold `null` |
| Double | `Double` | `double`/`Double` | Binary floating-point error for money |
| Decimal128 | `Decimal128` | `BigDecimal` via Spring conversion | Needs compatible converter, scale, and rounding |

### 18.1. Why Use BigDecimal for Money?

Using **`double`**:

~~~java
double amount = 0.1 + 0.2;
~~~

does not equal exact **`0.3`** in binary floating-point. For financial reports, store `Decimal128` or integer minor units per business policy and map to **`BigDecimal`/`long`** accordingly.

### 18.2. $sum Can Emit a Different Type Than Its Input

Depending on operator and input types:

- **`$sum: 1`** emits a numeric count (`int` or `long`, widening if overflow occurs).
- **`$sum`** over `Decimal128` returns `Decimal128`.
- **`$avg`** over integers can return `Double`; over `Decimal128` it preserves `Decimal128`.

Never force every **count** into `Integer` if row counts can exceed 32-bit bounds. Use **`long`/`Long`** for totals in output DTOs.

### 18.3. Inspect outputType on Conversion Errors

If the pipeline emits:

~~~javascript
{ revenue: NumberDecimal("205.00") }
~~~

while the DTO declares:

~~~java
public record RevenueDto(int revenue) {}
~~~

the conversion contract is broken. Temporarily aggregate into **`Document.class`**, inspect the actual BSON types, and fix the output DTO rather than forcing a lossy conversion.

### 18.4. Missing Fields Must Not Silently Default to Zero

Record:

~~~java
public record Stats(long orderCount, BigDecimal revenue) {}
~~~

with result:

~~~javascript
{ orderCount: 3 }
~~~

leaves `revenue` **absent (`null`)**; avoid calling `revenue.add(...)` without null checks. If the API contract requires `0`, explicitly emit or normalize it in the pipeline or mapper.

## 19. Date, Instant, and Timezones

BSON Date represents a UTC instant. Java domains commonly use **`Instant`**, **`Date`**, or other time types supported by Spring Data converters.

### 19.1. Grouping by Day Requires an Explicit Timezone

An order occurs at:

~~~text
2026-10-01T23:30:00Z
~~~

In **`Asia/Ho_Chi_Minh` (UTC+07:00)**, that timestamp falls on **`2026-10-02`**, a different calendar date from UTC.

If revenue reports follow **Vietnam business days**, grouping by UTC date puts late-night orders into the wrong daily bucket.

### 19.2. MongoDB $dateToString with Timezone

~~~javascript
db.orders.aggregate([
  { $match: { tenant_id: "TENANT-A", status: "PAID" } },
  {
    $group: {
      _id: {
        $dateToString: {
          format: "%Y-%m-%d",
          date: "$placed_at",
          timezone: "Asia/Ho_Chi_Minh"
        }
      },
      orderCount: { $sum: 1 },
      revenue: { $sum: "$gross_amount" }
    }
  },
  {
    $project: {
      _id: 0,
      businessDate: "$_id",
      orderCount: 1,
      revenue: 1
    }
  },
  { $sort: { businessDate: 1 } }
]);
~~~

Spring Data provides **`DateOperators`** and builders supporting date expressions and timezones depending on version. When a builder does not conveniently express an operator, use a custom **`AggregationOperation`** with a tested BSON stage.

### 19.3. Date DTOs Can Use String or Date

In the pipeline above, **`$dateToString`** emits a **`"YYYY-MM-DD"`** string, so an appropriate DTO is:

~~~java
public record DailyRevenue(
        String businessDate,
        long orderCount,
        java.math.BigDecimal revenue
) {}
~~~

Never map that date string straight into **`Instant`** without custom conversion; a calendar date without time or timezone does not denote a unique instant.

### 19.4. $dateTrunc and Time Bucketing

MongoDB versions supporting **`$dateTrunc`** let you bucket by day, hour, or week with timezone and week-start options. When output stays a BSON Date, the DTO can map directly to **`Instant`** using the standard converter.

Never slice ISO date strings manually when DST, historical timezones, or custom week starts apply. Use proper date operators aligned with business semantics.

## 20. Strict Mapping and Field Names from @Field

When executing **`TypedAggregation<OrderEntity>`**, stage builders evaluate against domain metadata. Yet the same conceptual field can appear under three distinct names:

~~~text
OrderEntity Java property:
  grossAmount

MongoDB document field:
  gross_amount

Aggregation result alias:
  revenue
~~~

Never use these three names interchangeably.

### 20.1. Input Fields vs. Output Fields

Before **`$group`**, reference:

~~~java
sum("grossAmount").as("revenue")
~~~

Inside typed aggregation, **`grossAmount`** maps to **`gross_amount`**.

After **`$group`**, the sort stage references:

~~~java
sort(Sort.Direction.DESC, "revenue")
~~~

**`revenue`** is the newly created output alias, not a Java domain property.

### 20.2. Non-Existent Fields

Suppose a developer makes a typo:

~~~java
match(Criteria.where("tennatId").is("TENANT-A"))
~~~

Field **`tennatId`** does not exist. Since Spring Data MongoDB 3.2, typed aggregation does not raise an error by default for every missing field reference—the query simply returns empty results.

When strict checking is desired, enable **`strictMapping`** per version:

~~~java
import org.springframework.data.mongodb.core.aggregation.AggregationOptions;

AggregationOptions options = AggregationOptions.builder()
        .strictMapping()
        .build();

TypedAggregation<OrderEntity> aggregation = newAggregation(
        OrderEntity.class,
        match(Criteria.where("tenantId").is("TENANT-A"))
).withOptions(options);
~~~

Keep in mind that strict mapping must also account for fields **created dynamically by earlier stages** and custom raw stages. Do not toggle strict mapping blindly to silence a failing pipeline; trace which field reference or alias is mismatched.

### 20.3. Raw JSON and Custom Stages

A hand-written stage:

~~~javascript
{ $match: { tenant_id: "TENANT-A" } }
~~~

is not automatically rewritten using **`@Field`** metadata the way `TypedAggregation` builders are. When writing raw BSON stages, use **exact stored BSON names** and document stage semantics carefully.

### 20.4. Using Document While Exploring Mapping

Example:

~~~java
AggregationResults<org.bson.Document> raw =
        mongoTemplate.aggregate(
                aggregation, org.bson.Document.class);

for (org.bson.Document row : raw.getMappedResults()) {
    System.out.println(row.toJson());
}
~~~

In a lab with synthetic data, this quickly reveals field shapes and types. **Never print sensitive documents** to production logs. Once the output shape is confirmed, switch to a typed DTO and add assertions.

## 21. When to Use @Aggregation in a Spring Data Repository?

Spring Data MongoDB lets you declare pipelines directly on repository methods with **`org.springframework.data.mongodb.repository.Aggregation`**.

~~~java
import java.util.List;

import org.springframework.data.mongodb.repository.Aggregation;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface OrderSpringRepository
        extends MongoRepository<OrderEntity, String> {

    @Aggregation(pipeline = {
            "{ '$match': { 'tenant_id': ?0, 'status': 'PAID' } }",
            "{ '$group': { '_id': '$region', " +
                    "'orderCount': { '$sum': 1 }, " +
                    "'revenue': { '$sum': '$gross_amount' } } }",
            "{ '$project': { '_id': 0, 'region': '$_id', " +
                    "'orderCount': 1, 'revenue': 1 } }",
            "{ '$sort': { 'revenue': -1 } }"
    })
    List<RegionRevenue> revenueByRegion(String tenantId);
}
~~~

**`?0`** binds the first method parameter. The pipeline strings inside the annotation are JSON-like templates processed by Spring Data; this example uses stored BSON field names to avoid mapping ambiguity. Never concatenate raw user input into pipeline JSON strings, as that invites operator injection and broken semantics.

### 21.1. Good Fits

- Short, stable pipelines with minimal branching.
- Reporting queries closely tied to a repository.
- Output maps cleanly to a well-defined DTO.
- No runtime-conditional stage additions needed.

### 21.2. When Is MongoTemplate Better?

- Dynamic pipelines with many optional filters.
- Complex **`$facet`/`$lookup`/`$unwind`** pipelines.
- Need for **`AggregationOptions`**, streaming, or custom operations.
- Reusable stage-builder helper functions.
- Tight control over schema and result mapping.

Choose based on complexity and testability, not dogma. While repository methods can support `Sort`/`Pageable` depending on version, remember that the total number of groups after `$group` **does not equal the source document count**.

If an API needs:

~~~text
items: top 20 region groups
totalGroups: 183
~~~

explicitly define how **`totalGroups`** is computed (after which filters) using a separate count pipeline or a `$facet` stage.

## 22. Dynamic Pipelines with Optional Filters

A report may enforce a mandatory **`tenantId`** while making status and date range optional.

~~~java
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;

import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.aggregation.AggregationOperation;
import org.springframework.data.mongodb.core.aggregation.TypedAggregation;
import org.springframework.data.mongodb.core.query.Criteria;

import static org.springframework.data.mongodb.core.aggregation.Aggregation.*;

public class DynamicRevenueReport {
    private final MongoTemplate template;

    public DynamicRevenueReport(MongoTemplate template) {
        this.template = template;
    }

    public List<RegionRevenue> run(
            String trustedTenantId,
            String optionalStatus,
            Instant fromInclusive,
            Instant toExclusive) {

        if (trustedTenantId == null || trustedTenantId.isBlank()) {
            throw new IllegalArgumentException(
                    "Authenticated tenant is required");
        }

        Criteria criteria =
                Criteria.where("tenantId").is(trustedTenantId);

        if (optionalStatus != null && !optionalStatus.isBlank()) {
            criteria = criteria.and("status").is(optionalStatus);
        }

        if (fromInclusive != null || toExclusive != null) {
            Criteria dates = criteria.and("placedAt");
            if (fromInclusive != null) {
                dates = dates.gte(fromInclusive);
            }
            if (toExclusive != null) {
                dates = dates.lt(toExclusive);
            }
        }

        List<AggregationOperation> stages = new ArrayList<>();
        stages.add(match(criteria));
        stages.add(group("region")
                .count().as("orderCount")
                .sum("grossAmount").as("revenue"));
        stages.add(project("orderCount", "revenue")
                .and("_id").as("region")
                .andExclude("_id"));
        stages.add(sort(Sort.Direction.DESC, "revenue"));

        TypedAggregation<OrderEntity> agg =
                newAggregation(OrderEntity.class, stages);

        return template.aggregate(agg, RegionRevenue.class)
                .getMappedResults();
    }
}
~~~

**Principle:** **`tenantId` is never optional**. Fields and operators are selected in code—never accepted arbitrarily from client-supplied query structures. For complex boolean logic, compose **`Criteria.andOperator`/`orOperator`** explicitly and avoid colliding BSON keys.

### 22.1. Controlling Sort and Limit from Requests

Never pass an arbitrary **`userField`** string into `Sort` without an allowlist. Restrict sorting to approved output aliases such as **`revenue`**, **`orderCount`**, and **`region`**, and enforce maximum row limits.

## 23. Custom AggregationOperation for Newer Stages

MongoDB servers frequently introduce new stages before your project's Spring Data version ships dedicated builders. Pass raw BSON through **`AggregationOperation`**.

~~~java
import org.bson.Document;
import org.springframework.data.mongodb.core.aggregation.AggregationOperation;

AggregationOperation rawMatch = context -> new Document(
        "$match",
        new Document("tenant_id", "TENANT-A")
                .append("status", "PAID")
);
~~~

Usage:

~~~java
Aggregation agg = Aggregation.newAggregation(
        rawMatch,
        Aggregation.group("region")
                .count().as("orderCount")
);
~~~

### 23.1. Mapping Context

**`AggregationOperationContext`** provides **`getMappedObject(Document)`**:

~~~java
AggregationOperation mappedMatch = context -> {
    Document raw = new Document(
            "$match",
            new Document("tenantId", "TENANT-A")
    );
    return context.getMappedObject(raw);
};
~~~

Whether domain mapping applies depends on the typed context and exposed fields; never assume every raw `Document` maps identically to typed builders. When writing raw stages, carefully control **actual BSON names, stage order, MongoDB server version, injection safety, and aliases**.

### 23.2. Custom Stages Do Not Create Server Compatibility

A MongoDB server that lacks a stage will not magically support it simply because Java constructs the `Document`. A custom `AggregationOperation` only builds and emits BSON; execution validity depends on your database version and data.

## 24. AggregationOptions: Execution Time, Memory, and Behavior

Reporting pipelines can consume substantial CPU, memory, and I/O. **`AggregationOptions`** lets you configure execution parameters.

~~~java
import java.time.Duration;
import org.springframework.data.mongodb.core.aggregation.AggregationOptions;

AggregationOptions options =
        AggregationOptions.builder()
                .allowDiskUse(true)
                .maxTime(Duration.ofSeconds(10))
                .comment("region-revenue-report")
                .build();

Aggregation agg = newAggregation(
        match(Criteria.where("tenant_id").is("TENANT-A")),
        group("region")
                .sum("gross_amount").as("revenue")
).withOptions(options);
~~~

Depending on version, the builder also supports **`cursorBatchSize`, `hint`, `collation`, `readPreference`/`readConcern`, and `explain`**.

### 24.1. allowDiskUse Is Not a Free Speedup

**`allowDiskUse(true)`** permits certain stages to spill temporary files to disk instead of failing in RAM. However:

- It increases disk I/O and requires temporary storage headroom.
- It does not fix missing indexes or poor filters.
- It does not lift the 16 MiB BSON document limit.
- Not all stages support spilling; `$facet`, for instance, has its own internal constraints.
- Default spill behavior varies across MongoDB server versions and configuration.

### 24.2. maxTime Differs from HTTP Request Timeouts

**`maxTime(Duration)`** bounds server-side command processing time per MongoDB semantics; it does not cover DNS resolution, connection pool waits, network latency, mapping large result sets, or HTTP response serialization.

Design end-to-end deadlines, bound returned rows, and monitor full request latency.

### 24.3. Comments Must Never Contain Secrets

Comments are helpful for identifying workloads:

~~~text
region-revenue-report
~~~

Never put emails, passwords, tokens, national IDs, or sensitive customer data into comments because they appear in database logs and profilers.

### 24.4. Explain Is Not Report Output

Enabling **`explain(true)`** collects execution plan diagnostics rather than `RegionRevenue` rows. Never leave explain mode active on user-facing DTO endpoints.

## 25. Streaming Results Instead of Collecting Everything in a List

**`MongoTemplate.aggregate(...)`** materializes `AggregationResults` and mapped lists in memory. When outputs contain many rows, collecting everything into a `List` spikes RAM usage. Spring Data provides **`aggregateStream(...)`** backed by a database cursor.

~~~java
import java.util.stream.Stream;

Aggregation agg = newAggregation(
        match(Criteria.where("tenant_id").is("TENANT-A")),
        project()
                .and("_id").as("orderId")
                .and("region").as("region")
                .andExclude("_id")
);

try (Stream<RegionOrder> stream =
             mongoTemplate.aggregateStream(
                     agg, "orders", RegionOrder.class)) {
    stream.forEach(row -> {
        // Process each row without holding all rows in RAM.
        System.out.println(row.orderId());
    });
}
~~~

DTO:

~~~java
public record RegionOrder(String orderId, String region) {}
~~~

**Always close the `Stream`**, even on exceptions or early termination. Never store a `Stream` in a singleton field or return it outside a closed scope.

### 25.1. When Streaming Still Falls Short

Streaming reduces heap memory by **avoiding full materialization**, yet keeps a server cursor open longer, holding resources. Always:

- Bound queries and filter early.
- Choose an appropriate `batchSize`.
- Handle cancellation and errors cleanly.
- Never call **`stream.toList()`** on millions of rows—that defeats streaming.
- Never return an unclosed `Stream` to a controller and forget to close it.

### 25.2. cursorBatchSize Is Not Limit

**`cursorBatchSize`** controls driver network batch sizing where supported; **`$limit`** caps total returned rows. Never set `cursorBatchSize(100)` thinking the query will stop at 100 rows.

### 25.3. Reactive Stack

When using **`ReactiveMongoTemplate`**, aggregations return **`Flux<DTO>`** with reactive backpressure and non-blocking driver execution. Standard **`MongoTemplate`** is blocking—never invoke it directly on a non-blocking event-loop thread assuming it becomes reactive.

## 26. Performance: Stage Ordering and Index Utilization

A functionally accurate pipeline can still perform poorly.

### 26.1. Place $match and Projections Strategically

Filter by tenant, status, and date early:

~~~javascript
[
  { $match: { tenant_id: "TENANT-A", status: "PAID" } },
  { $group: { _id: "$region", revenue: { $sum: "$gross_amount" } } },
  { $sort: { revenue: -1 } }
]
~~~

Grouping all tenants first and filtering by tenant at the end forces `$group` over far more documents—and `tenantId` may not even exist anymore to filter.

While MongoDB's pipeline optimizer can coalesce or reorder certain `$project` stages, **never** rely on that to excuse placing tenant filters late or writing unsafe pipelines.

### 26.2. Sorting Before vs. After Group

~~~text
$sort(placed_at desc) before $group:
  sorts source documents

$sort(revenue desc) after $group:
  sorts summary rows
~~~

A B-tree index can satisfy a leading `$sort` under appropriate conditions, but no index covers **`revenue`** computed dynamically after `$group`. Post-group sorts always sort the aggregated rows.

### 26.3. $match + $sort + $limit

If a query simply fetches the latest orders:

~~~javascript
[
  { $match: { tenant_id: "TENANT-A" } },
  { $sort: { placed_at: -1, _id: -1 } },
  { $limit: 20 }
]
~~~

an index:

~~~javascript
db.orders.createIndex({
  tenant_id: 1,
  placed_at: -1,
  _id: -1
});
~~~

is beneficial. A regional `$group` report follows a different pattern. **Design indexes for concrete workloads**, not just because a collection has many pipelines.

### 26.4. Explain

In the `mongosh` lab:

~~~javascript
db.orders.explain("executionStats").aggregate([
  { $match: { tenant_id: "TENANT-A", status: "PAID" } },
  {
    $group: {
      _id: "$region",
      revenue: { $sum: "$gross_amount" }
    }
  }
]);
~~~

Depending on server version and explain format, check:

- **`COLLSCAN`** vs. **`IXSCAN`** on the input stage.
- Documents and index keys scanned.
- Stages performing sorts/grouping and memory consumption.
- Execution time reported in stats.
- Whether `allowDiskUse` or disk spilling occurred.

**`explain` on an 8-document collection does not reflect production.** Small collections make collection scans look fast; that does not mean indexes are unnecessary at scale.

### 26.5. $lookup and N×M Joins

Unindexed joins scan huge numbers of documents. With `$lookup`:

- Filter parent documents early.
- Index the join key on the foreign collection.
- Restrict fields and cardinality.
- Beware nested arrays and `$unwind` multiplying rows.
- Enforce tenant isolation on both parent and foreign sides where required.

### 26.6. Avoid Overusing $facet

`$facet` is convenient for multi-widget dashboards, yet can produce huge documents and high resource consumption. Independent widgets updating on different cadences often work better as **separate queries** or **materialized summaries** instead of one giant `$facet` pipeline.

## 27. Paginating Grouped Results

A report may emit thousands of region or category groups. Use:

~~~java
sort(Sort.Direction.DESC, "revenue"),
skip(20),
limit(20)
~~~

to paginate grouped results. However:

- Large **`skip`** incurs cost skipping preceding groups.
- Sorting must be deterministic; add a tie-breaker such as **`region`** when revenues tie.
- Total group counts must reflect **grouped results**, not source orders.
- If data mutates between pages, offset pagination can cause duplicate or skipped groups.

### 27.1. Deterministic Sort Example

~~~java
sort(Sort.by(
        Sort.Order.desc("revenue"),
        Sort.Order.asc("region")
)),
skip(20),
limit(20)
~~~

When deep pagination or continuous updates are involved, evaluate keyset/seek pagination or snapshot reporting models—noting that **keyset over computed group results** requires dedicated boundary conditions and stability design.

### 27.2. Never Use Source Collection `count()` for Group Pages

If a collection has 1,000,000 orders across 250 regions/categories, **`totalGroups = 250`**, not 1,000,000. Run a group-counting pipeline after filtering/grouping or use a dedicated `$facet` branch to return accurate group totals.

## 28. Testing Aggregations in Spring Data

A pipeline can execute cleanly and still **return wrong numbers** due to:

- Placing `$match` at the wrong stage.
- Mixing up **`tenantId`** and **`tenant_id`**.
- Counting items instead of orders after `$unwind`.
- Rounding or converting money via `Double`.
- Mapping `_id` to the wrong field.
- Confusing `null` and missing fields.
- Joining wrong customers when IDs collide across tenants.
- Sorting before `$group` or placing `$limit` incorrectly.

Therefore, write **integration tests against real MongoDB**, seeded with small datasets covering edge cases.

### 28.1. Revenue Integration Test

JUnit 5 / Spring Boot example, assuming the test database is created and seeded with **the dataset from section 4**:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.math.BigDecimal;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class OrderAnalyticsRepositoryIT {

    @Autowired
    private OrderAnalyticsRepository reports;

    @Test
    void reportsPaidRevenueOnlyForRequestedTenant() {
        List<RegionRevenue> rows =
                reports.revenueByRegion("TENANT-A");

        assertEquals(2, rows.size());

        RegionRevenue north = rows.stream()
                .filter(r -> "NORTH".equals(r.region()))
                .findFirst()
                .orElseThrow();

        assertEquals(3L, north.orderCount());
        assertEquals(0, north.revenue()
                .compareTo(new BigDecimal("205.00")));

        assertTrue(rows.stream().noneMatch(r ->
                r.revenue().compareTo(
                        new BigDecimal("999.00")) == 0));
    }
}
~~~

This is strictly a **test template**. Never run it against production. Real tests should use an isolated database with per-test setup/cleanup and verify **`SOUTH = 115.00`** alongside `NORTH`. Re-running `insertMany` with fixed `_id` values on an uncleaned collection will trigger duplicate key errors.

### 28.2. Independent Output Mapping Tests

Test suites should cover:

| Scenario | What to Verify |
|---|---|
| No matching orders | Empty list or null result per contract |
| Single region | Single DTO with accurate aliases |
| Multiple regions | List sorted properly |
| Two regions with tied revenue | Deterministic tie-breaker |
| `Decimal128` values | No decimal precision loss |
| Multiple items in one order | Accurate quantity sum without double-counting orders |
| Missing customer in `$lookup` | Unwind keeps or drops document as specified |
| High-revenue Tenant B | Never included in Tenant A's totals |
| Dates near UTC midnight | Bucketed under the declared business timezone |
| Null/missing output fields | Handled safely by DTO or converter |

### 28.3. Unit Testing Builders Alone Is Not Enough

A unit test asserting an `Aggregation` object is non-null **does not prove** MongoDB understands the stages or that the output mapper parses the result cleanly. Bugs involving BSON field names, `Decimal128`, `$lookup`, indexes, and server versions usually surface only in integration tests.

### 28.4. Testcontainers

With Testcontainers, spin up MongoDB for tests and set **`spring.data.mongodb.uri`** to the container URL compatible with your Testcontainers and Spring Boot versions. This lesson does not mandate a single Testcontainers API because `MongoDBContainer` packages and connection helpers vary by release.

Precautions:

- Never use production credentials.
- Never run init scripts dropping collections outside test scope.
- When running tests in parallel, avoid sharing a single collection with colliding `_id`s.
- When testing `$lookup`, `$setWindowFields`, or `$dateTrunc`, use a MongoDB image version supporting those stages.
- Ensure tests do not depend on the test runner host's local timezone.

### 28.5. Pipeline Snapshots Are Helpful but Insufficient

You can snapshot-test the rendered BSON pipeline produced by Spring Data, yet distinguish formatted strings from the exact pipeline `MongoTemplate` sends. A snapshot test without domain mapping context may misrepresent production behavior.

Never rely solely on JSON string comparisons without verifying real numerical results from MongoDB.

## 29. Security and Correctness in Multi-Tenant Analytics

### 29.1. Tenant Filters Are Mandatory

When one collection holds multiple tenants, every tenant-scoped report must filter by tenant. Yet:

~~~java
public List<RegionRevenue> report(String tenantId)
~~~

does not guarantee `tenantId` is trustworthy. Controllers and services must resolve `tenantId` from the **verified identity/token/session**, never trusting an arbitrary query-string parameter.

### 29.2. Aggregations Can Leak Sensitive Information via Summaries

An API returning:

~~~javascript
{ department: "EXECUTIVE", totalPayroll: 9000000 }
~~~

can disclose sensitive business information even without returning individual employee rows. Enforce authorization on **the report itself**, not just raw collection documents.

### 29.3. Access Control in $lookup

When joining foreign collections, enforce `tenantId`/ACLs on both sides. If two tenants reuse the same `customerRef` or `productRef`, joining solely on that reference key leaks cross-tenant records.

Never return raw joined documents to APIs; project only authorized fields.

### 29.4. Never Allow Clients to Submit Arbitrary Raw Pipelines

A request like:

~~~json
{
  "pipeline": [
    { "$match": {} },
    { "$lookup": { "from": "privateCollection" } }
  ]
}
~~~

must never be executed directly by a privileged backend. Whitelist report types, filters, sort fields, and output schemas—never grant arbitrary collection access just because MongoDB pipelines are flexible.

### 29.5. Resource Limits on Reports

A user can request a report spanning an enormous date range and overload the server. Bound:

- Maximum date range.
- Maximum group/result rows.
- Allowed stages and report branches.
- `maxTime`, cancellation, and concurrency.
- Sort fields.
- Per-user/per-tenant report rate limits.

Never use **`allowDiskUse(true)`** as an abuse-prevention control.

## 30. Common Errors and Troubleshooting

### 30.1. Query Returns Empty Despite Data Visible in mongosh

**Likely cause:** pipeline used Java property **`tenantId`** in untyped/`Document` mode while the collection stores **`tenant_id`**.

**Fix:** verify typed vs. untyped aggregation, `@Field` mappings, and generated BSON pipeline. Cross-check with a raw `mongosh` query on sample data.

### 30.2. Revenue Is Null After $group

**Likely cause:** grouped on **`grossAmount`** in an untyped pipeline expecting **`gross_amount`**, or stored values are strings, nulls, or inconsistent types.

**Fix:** check field names, BSON types, stage order, and raw output `Document`s. Never force `null` to `0` before finding the root cause.

### 30.3. DTO region Is Null Even Though _id Holds NORTH

**Cause:** group output is:

~~~javascript
{ _id: "NORTH", orderCount: 3 }
~~~

while the DTO expects **`region`**. **Fix:** project **`region: "$_id"`** and exclude `_id`, or configure matching mapping annotations/constructors.

### 30.4. BigDecimal Values Are Inaccurate

**Cause:** inputs stored as `Double`, intermediate Java `double` arithmetic, `$avg` returning `Double`, or legacy strings.

**Fix:** verify BSON `Decimal128`, `@Field` `targetType`, numeric expression types, converters, and scale/rounding policies.

### 30.5. aggregateStream Keeps Cursors Open Too Long

**Cause:** stream was not closed, per-row processing is slow, or the stream escaped its method scope.

**Fix:** use try-with-resources, bounded batches, backpressure, and cancellation.

### 30.6. $lookup Returns an Array Instead of an Object

**Cause:** `$lookup` always emits an array. **Fix:** model a `List` in the DTO or `$unwind`/`$project` the joined object fields.

### 30.7. $unwind Inflates orderCount

**Cause:** grouping/counting after `$unwind` counts **item rows**, not orders. **Fix:** reorder pipeline stages or deduplicate by order ID.

### 30.8. getUniqueMappedResult() Throws an Exception

**Cause:** the aggregation returned **more than one document**, while this method expects 0 or 1. **Fix:** use `getMappedResults()` for multi-group outputs; reserve unique calls for contracts guaranteed to return at most one row.

### 30.9. NullPointerException in Controller

**Cause:** empty `$group` input or missing result field while code assumes non-null primitives or fields.

**Fix:** define explicit **no-data** behavior, validate/normalize DTOs, and guard against nulls.

### 30.10. Incorrect Sort Results

**Cause:** sorting on a field already dropped by `$project`, or sorting before `$group` when trying to sort by computed `revenue`.

**Fix:** trace document shapes stage by stage, sort on existing aliases, and add a tie-breaker for stable pagination.

### 30.11. Poor Performance Despite Indexes

**Cause:** `$match` placed after `$group`/`$project`, index does not match filter, scanning too many documents, sorting on computed fields, or unindexed `$lookup`.

**Fix:** inspect `explain("executionStats")`, measure keys/docs examined, and tune pipeline and indexes for the workload.

### 30.12. Pipeline Fails with Stage Unsupported Error

**Cause:** MongoDB server version lacks the stage, or Spring Data version lacks a builder. **Fix:** distinguish the two—a custom `AggregationOperation` fixes a missing Java builder, not an unsupported server feature.

### 30.13. Report Includes Other Tenants' Data

**Cause:** missing tenant filter, trusting an unverified `tenantId`, or `$lookup` joining across tenants. **Fix:** treat as a security incident, fix authorization and isolation, and add regression tests with high-revenue data in another tenant.

### 30.14. Report Confuses Product Quantities with Order Counts

**Cause:** mixing up document counts, line-item counts, summed quantities, and distinct order counts. **Fix:** write exact metric definitions and match grouping stages accordingly.

### 30.15. $facet Returns an Oversized Document

**Cause:** stuffing too many rows into facet output arrays, exceeding BSON or memory limits. **Fix:** emit bounded summaries only, split into separate queries, paginate, or use materialized views.

### 30.16. Wrong Group Count When Paginating

**Cause:** calling `MongoTemplate.count(Query...)` on the source collection instead of counting post-aggregation groups. **Fix:** compute `totalGroups` via a filtered/grouped count pipeline or dedicated `$facet`.

### 30.17. Timezone Shifts Report Dates

**Cause:** grouping in UTC when business days follow `Asia/Ho_Chi_Minh` or another local zone. **Fix:** pass `timezone` to date operators and test timestamps near midnight.

### 30.18. Report Consumes Excessive RAM

**Cause:** returning millions of rows via `getMappedResults()` into a `List`, or huge `$facet` documents. **Fix:** tighten filters, projections, and limits; use scoped `aggregateStream`; or adopt batch/materialized summaries.

## 31. Step-by-Step Workflow to Build an Aggregation Report from Scratch

### Step 1 — Define the Metric

Example:

~~~text
Metric name: PAID revenue by region
Scope: authenticated tenant
Time filter: placedAt in [from, to)
Eligible status: PAID only
Currency: single consistent currency per report
Output: region, orderCount, revenue
Sort: revenue descending, region ascending
~~~

In multi-currency systems, never add **100 USD + 100 VND** into `revenue = 200`; group by currency or convert under explicit FX policies.

### Step 2 — Identify BSON Data Types and Field Names

~~~text
tenantId property -> tenant_id BSON String
status -> String
region -> String
grossAmount property -> gross_amount BSON Decimal128
placedAt property -> placed_at BSON Date
~~~

Also audit null/legacy records, currency consistency, and tenant permissions.

### Step 3 — Write an Explicit MongoDB Pipeline

~~~javascript
[
  { $match: { tenant_id: "<trusted>", status: "PAID" } },
  {
    $group: {
      _id: "$region",
      orderCount: { $sum: 1 },
      revenue: { $sum: "$gross_amount" }
    }
  },
  { $project: { _id: 0, region: "$_id", orderCount: 1, revenue: 1 } },
  { $sort: { revenue: -1, region: 1 } }
]
~~~

### Step 4 — Translate to Spring Data Builders

~~~java
newAggregation(
    OrderEntity.class,
    match(Criteria.where("tenantId").is(trustedTenantId)
        .and("status").is("PAID")),
    group("region")
        .count().as("orderCount")
        .sum("grossAmount").as("revenue"),
    project("orderCount", "revenue")
        .and("_id").as("region")
        .andExclude("_id"),
    sort(Sort.by(
        Sort.Order.desc("revenue"),
        Sort.Order.asc("region")))
);
~~~

### Step 5 — Design the DTO Around the Output, Not the Input

~~~java
public record RegionRevenue(
        String region,
        long orderCount,
        BigDecimal revenue
) {}
~~~

### Step 6 — Test Edge Cases

No data, single region, multiple regions, tied revenue, multi-tenant isolation, `Decimal128`, nulls, and timestamps near date boundaries.

### Step 7 — Explain and Observe

Inspect index usage, documents scanned, grouped cardinality, sort memory, latency, and response sizes. Never extrapolate production speed from an 8-row benchmark.

### Step 8 — Expose Safely in Service/API

Resolve tenant from authentication, bound date ranges, return only authorized DTOs, and log/emit metrics without sensitive data.

## 32. Guided Practice Exercises

Exercises use **`spring_agg_lab.orders`** and **`spring_agg_lab.customers`**. They focus on writing and explaining pipelines; live execution requires a test MongoDB and Spring Data environment.

### Exercise 1. Converting `find` to `aggregate`

Query:

~~~javascript
db.orders.find({ tenant_id: "TENANT-A", status: "PAID" });
~~~

**Task:** write a `MongoTemplate` `Aggregation` using only `$match` and map to `Document`.

**Solution guide:**

~~~java
Aggregation agg = newAggregation(
        match(Criteria.where("tenant_id").is("TENANT-A")
                .and("status").is("PAID"))
);

List<Document> documents = mongoTemplate
        .aggregate(agg, "orders", Document.class)
        .getMappedResults();
~~~

### Exercise 2. Typed vs. Untyped

Java property **`tenantId`** carries `@Field("tenant_id")`. Compare:

~~~java
newAggregation(
        match(Criteria.where("tenantId").is("TENANT-A")));

newAggregation(
        OrderEntity.class,
        match(Criteria.where("tenantId").is("TENANT-A")));
~~~

**Question:** why can they emit different query field names?

**Answer:** typed aggregation reads `@Field` metadata to translate `tenantId` to `tenant_id`; untyped aggregation lacks that input mapping context and should use actual BSON names.

### Exercise 3. Group Output in `_id`

~~~javascript
{ $group: { _id: "$region", n: { $sum: 1 } } }
~~~

**Task:** design a DTO with fields `region` and `n`.

**Solution guide:** add a `$project` stage aliasing **`region: "$_id"`**, excluding `_id`, and map into **`RegionCount(String region, long n)`**.

### Exercise 4. Total Revenue by Region

**Task:** filter `TENANT-A`/`PAID`, group by region, and sum `gross_amount`. What is the expected output?

**Answer:** `NORTH` has 3 orders and revenue **`205.00`**; `SOUTH` has 2 orders and revenue **`115.00`**.

### Exercise 5. Tenant Isolation

`TENANT-B` has an order with revenue `999.00`.

**Question:** if you filter only by `status = PAID`, how are the numbers skewed?

**Answer:** the report includes `TENANT-B`'s order, inflating `NORTH` by `999` and adding `1` to count; this is an authorization/isolation breach, not just a math bug.

### Exercise 6. `getUniqueMappedResult`

A pipeline grouped by **`region`** returns two rows.

**Question:** is calling `getUniqueMappedResult()` valid?

**Answer:** no. That method assumes at most one result and throws `IllegalArgumentException` on multiple rows. Use `getMappedResults()`.

### Exercise 7. `group()` with Empty Input

A brand-new tenant has zero `PAID` orders.

**Question:** is `getUniqueMappedResult()` guaranteed to return `TotalRevenue(0, 0)`?

**Answer:** no. Empty input produces zero documents, so the method returns `null`. The API must handle no-data explicitly.

### Exercise 8. Counting After Unwind

Order `O-1001` has two items.

**Question:** why does `$unwind` on `items` followed by counting documents yield `2` instead of `1`?

**Answer:** one order expanded into two intermediate documents. The metric counts item rows rather than distinct orders.

### Exercise 9. Total SKU Quantities

**Task:** compute `quantitySold` across `PAID` orders for `TENANT-A`.

**Answer:** `PEN-1` = **`7`**, `BOOK-1` = **`4`**, `BAG-1` = **`1`**.

### Exercise 10. Lookup a Single Customer

**Question:** why is `customer` after `$lookup` an array even when `_id` matches only one document?

**Answer:** `$lookup` always emits an array. Use `$unwind` if you want a flattened object row and define handling when no customer matches.

### Exercise 11. Preserve Null

An order has no `items`.

**Question:** what does default `$unwind` do, and how do you keep the order?

**Answer:** default `$unwind` drops the document. Enable `preserveNullAndEmptyArrays`, then handle null `items` in downstream stages.

### Exercise 12. Facet Dashboard

**Task:** return `PAID` revenue by region alongside order counts across all statuses for `TENANT-A`.

**Solution guide:** match tenant before `$facet`; have the `revenueByRegion` branch match `PAID` internally, while `statusCounts` groups by `status`. Do not filter `PAID` before `$facet` or `statusCounts` will miss `NEW` and `CANCELLED`.

### Exercise 13. Nested DTO

Facet returns:

~~~javascript
{ revenueByRegion: [...], statusCounts: [...] }
~~~

**Question:** should the top-level DTO be `List<RegionRevenue>` or `DashboardReport` holding two `List`s?

**Answer:** `DashboardReport` holding two `List`s, because the top-level output is a single document wrapping both arrays.

### Exercise 14. Decimal128

The pipeline returns `revenue = NumberDecimal("205.00")`.

**Question:** should you map to Java `double` or `BigDecimal`?

**Answer:** `BigDecimal` is strongly preferred for money. Use `Decimal128`-compatible conversion and verify scale/rounding.

### Exercise 15. Missing Alias

Pipeline:

~~~text
$group as revenue
$project renames revenue -> total
$sort by revenue
~~~

**Question:** why is the sort broken?

**Answer:** after `$project`, `revenue` no longer exists; sort by `total` or reorder `$project` and `$sort` per semantics.

### Exercise 16. Summing Strings

A legacy order stores `gross_amount = "120.50"` instead of `NumberDecimal`.

**Question:** can you trust `$sum gross_amount` to return an accurate total?

**Answer:** no. Standardize BSON types and migrate legacy records; never assume strings sum numerically.

### Exercise 17. Two Group Keys

~~~javascript
{ _id: { region: "$region", status: "$status" }, n: { $sum: 1 } }
~~~

**Question:** is `_id` a `String`?

**Answer:** no, it is an object containing `region` and `status`. Use a nested DTO or project two flat fields.

### Exercise 18. `$first`/`$last`

You want the earliest order by `placed_at` in each region.

**Question:** if you call `group().first("_id")` without sorting first, is it guaranteed to be the oldest order?

**Answer:** no. Sort inputs by `placed_at` and a tie-breaker before `$group`, or use an appropriate accumulator.

### Exercise 19. Report Timezones

An order occurs at `23:30 UTC` on `2026-10-01`.

**Question:** under `Asia/Ho_Chi_Minh`, which date does it belong to?

**Answer:** **`2026-10-02`**. Specify `timezone` in date grouping when business days follow Vietnam local time.

### Exercise 20. Strict Mapping

`TypedAggregation` references a misspelled field **`tennatId`**.

**Question:** will every Spring Data version throw an error immediately?

**Answer:** no. Since 3.2, typed aggregation does not necessarily fail on non-existent properties by default; use `AggregationOptions.strictMapping()` per version and verify outputs via tests.

### Exercise 21. `@Aggregation` Repository

A report has a fixed four-stage pipeline returning `List<RegionRevenue>`.

**Question:** can you use `@Aggregation`? When should you prefer `MongoTemplate`?

**Answer:** `@Aggregation` with parameter placeholders works well. Prefer `MongoTemplate` for dynamic pipelines, multi-branch `$facet`/`$lookup`, `AggregationOptions`, or streaming.

### Exercise 22. `maxTime` vs. HTTP Timeout

The app sets `maxTime` to 10 seconds, while the API gateway times out after 2 seconds.

**Question:** does `maxTime` guarantee the whole HTTP request finishes within 2 seconds?

**Answer:** no. `maxTime` is a database command/server limit; align HTTP/app deadlines, network, mapping, and cancellation.

### Exercise 23. `allowDiskUse`

A group/sort report consumes lots of memory.

**Question:** is enabling `allowDiskUse(true)` enough optimization?

**Answer:** no. It enables disk spill for certain stages at the cost of extra I/O, but does not fix missing indexes/filters or bypass BSON document/`$facet` limits.

### Exercise 24. Streaming 1 Million Rows

Code obtains `aggregateStream`, then calls:

~~~java
List<RegionOrder> all = stream.toList();
~~~

**Question:** does it still save memory?

**Answer:** no, collecting everything into a `List` defeats streaming. Process row-by-row or in bounded batches, cap outputs, and close the stream.

### Exercise 25. Controlling Sort Input

An API lets callers pass an arbitrary field name straight into `Sort.by(fieldName)`.

**Question:** what are the risks?

**Answer:** unpermitted or non-existent fields, expensive unindexed sorts, and metadata disclosure. Whitelist allowed output fields and cap rows and time ranges.

### Exercise 26. Pagination After Group

A collection has 1 million orders across 20 regions.

**Question:** is returning `totalCount = 1,000,000` accurate for paginating regions?

**Answer:** no, `totalGroups` must count **`20`** after matching filters and grouping. Source collection count is a different metric.

### Exercise 27. Cross-Tenant `$lookup`

An order and a customer from two different tenants share the same `customerRef`. The pipeline joins on `customerRef` without checking tenant.

**Question:** why is this dangerous?

**Answer:** it can join and expose another tenant's data. Enforce tenant isolation predicates/keys/ACLs across both collections.

### Exercise 28. Shape Mismatch

Pipeline emits:

~~~javascript
{ amount: NumberDecimal("120.50"), name: "Book" }
~~~

DTO:

~~~java
public record Result(String itemName, int revenue) {}
~~~

**Task:** identify the two mapping bugs.

**Answer:** field names **`amount`/`name`** do not match **`revenue`/`itemName`**; `Decimal128` cannot safely map to `int` if fractional cents matter. Align aliases and use `BigDecimal`.

### Exercise 29. Secure Dynamic Reporting

Build a report accepting:

~~~text
Authenticated tenantId (required)
Optional status
Optional from/to
Sort: revenue / orderCount only
Limit: max 100
~~~

**Task:** outline stage order, validation, and DTO.

**Solution guide:** extract `tenantId` from auth, validate date range, build `Criteria` and `$match` early, `$group`/`sum`/`count`, `$project` aliases, sort via allowlist with bounded `$limit`, and return `RegionRevenue` rather than raw BSON.

### Exercise 30. End-to-End Report Design

Requirement: an e-commerce dashboard displaying three metrics:

1. `PAID` revenue by region.
2. Order count by status.
3. Quantity sold by SKU.

Must enforce tenant isolation, handle `Decimal128`, support timezones, and scale to large datasets.

**Solution guide:**

- Start with a **common tenant `$match`**.
- Use `$facet` with tailored branches (or separate pipelines if facet cost grows too high).
- Revenue branch filters `PAID` then groups by region.
- Status branch groups by status without filtering `PAID`.
- SKU branch filters `PAID`, unwinds `items`, and groups `items.sku` summing `quantity`.
- Project clean aliases and map into `DashboardReport` with three nested lists.
- Validate `BigDecimal`/`long`, apply timezone for any daily breakdown.
- Enforce authorization, resource limits, and inspect indexes with `explain`.
- Write integration tests spanning two tenants, multiple statuses, and multi-item orders.

## 33. Advanced Stages and Compatibility Notes

The MongoDB Aggregation Framework includes many stages beyond the basic examples. Spring Data MongoDB supports them directly or via custom `AggregationOperation` depending on version.

| Stage | Purpose | Considerations |
|---|---|---|
| **$addFields / $set** | Add computed fields | Can overwrite existing fields |
| **$unset** | Remove fields | Later stages cannot read dropped fields |
| **$replaceRoot / $replaceWith** | Reshape root document | DTO must match the new root |
| **$bucket / $bucketAuto** | Partition values into buckets | `_id` types and boundary inclusivity |
| **$sortByCount** | Group count and sort | Emits `_id` and `count` |
| **$setWindowFields** | Window metrics, running totals | Sort/partition/window syntax and server version |
| **$unionWith** | Combine rows from another collection/pipeline | Differing schemas need normalization |
| **$graphLookup** | Recursive relationship traversal | Depth, cycles, memory, and ACLs |
| **$geoNear** | Geospatial distance queries | Must be first stage; requires geo index |
| **$search / $vectorSearch** | Atlas Search / Vector Search | Deployment requirements and leading stage placement |
| **$out / $merge** | Write output to a collection | Side effects, write permissions, and idempotency |

### 33.1. $merge and $out Are Not Read-Only Reports

Pipelines ending with **`$merge`** or **`$out`** write into target collections. In Spring Data, handle them with compatible APIs, write privileges, retries, and dedicated lifecycles.

Never attach a writing pipeline to an HTTP `GET` endpoint as a "quick report," because retries or timeouts produce uncontrolled side effects.

### 33.2. Materialized Summaries

For dashboards read thousands of times with infrequent updates, maintain a **materialized summary**:

~~~text
Orders collection
      |
      v
Scheduled aggregation (controlled batch)
      |
      v
summary_by_region collection
      |
      v
Read API -> small indexed query
~~~

This reduces repeated aggregation load, at the cost of managing **freshness, incremental updates, backfills, idempotency, and tenant authorization**. Never label a scheduled summary table "real-time."

### 33.3. $search and $vectorSearch Have Strict Placement Rules

Atlas Search and Vector Search carry deployment, index, and pipeline-position requirements. Constructing BSON via a custom Java stage cannot bypass server rules such as requiring them as the first stage or disallowing them inside certain subpipelines.

### 33.4. AggregationUpdate Differs from Aggregate Queries

Spring Data provides **`AggregationUpdate`** for aggregation-pipeline updates in supporting versions. It transforms and updates documents in place, **unlike** reading analytics via **`MongoTemplate.aggregate(...)`**. Never pass a read pipeline containing `$group`/`$facet` into an update pipeline where MongoDB forbids those stages.

## 34. Spring Data Aggregation Report Checklist

### 34.1. Data Contract

- [ ] Metrics and filter conditions are explicitly defined.
- [ ] Tenant and authorization scoping is mandatory.
- [ ] Order counts, line-item counts, and summed quantities are clearly distinguished.
- [ ] BSON types and null/missing handling are verified.
- [ ] Currency, rounding, and timezone rules are finalized.
- [ ] Sample datasets cover edge cases.

### 34.2. Pipeline

- [ ] `$match` filters inputs accurately and early when semantics permit.
- [ ] `$group` keys and accumulators match metric definitions.
- [ ] `$unwind` does not inflate order counts.
- [ ] `$lookup` enforces join isolation and selects only required fields.
- [ ] `$facet` stays well within output size and memory limits.
- [ ] `$project` emits aliases matching the DTO without dropping fields needed later.
- [ ] `$sort` includes a tie-breaker when stable pagination is required.
- [ ] Indexes align with actual query patterns.

### 34.3. Spring Data Mapping

- [ ] Typed/untyped aggregations use matching Java vs. BSON field names.
- [ ] `@Field` mappings on domain entities are accounted for.
- [ ] Output DTO mirrors the final stage shape rather than reusing input entities blindly.
- [ ] Group `_id` values are projected or mapped intentionally.
- [ ] `Decimal128`, `Int64`, and `Date` map to appropriate Java types.
- [ ] `getUniqueMappedResult` is called only when 0..1 rows are guaranteed.
- [ ] Nested arrays and objects align with DTO structure.

### 34.4. Operations

- [ ] `maxTime` and end-to-end application deadlines are configured.
- [ ] `allowDiskUse` is evaluated per workload rather than masking missing indexes.
- [ ] Date ranges, row limits, and concurrency are bounded on report APIs.
- [ ] Large outputs use streaming, batching, or materialized summaries.
- [ ] Metrics and alerts cover latency, row counts, and failed aggregations.
- [ ] `explain` and tests run against representative datasets.
- [ ] Raw documents containing sensitive data are never logged.

## 35. Quick Reference Table

| Goal | Primary Spring Data API | MongoDB Stage |
|---|---|---|
| Filter documents | `match(Criteria...)` | `$match` |
| Select/rename fields | `project().and(...).as(...)` | `$project` |
| Group by field | `group("field")` | `$group` |
| Count in group | `count().as("n")` | `$sum: 1` |
| Sum a numeric field | `sum("amount").as("total")` | `$sum` |
| Average | `avg("amount").as("avg")` | `$avg` |
| Sort | `sort(Sort.Direction...)` | `$sort` |
| Limit rows | `limit(n)` | `$limit` |
| Skip rows | `skip(n)` | `$skip` |
| Split array into rows | `unwind("items")` | `$unwind` |
| Join collection | `lookup(...)` | `$lookup` |
| Multi-branch reports | `facet(...).as(...)` | `$facet` |
| Count and sort by field | `sortByCount("field")` | `$sortByCount` |
| Range bucketing | `bucket(...)`, `bucketAuto(...)` | `$bucket`, `$bucketAuto` |
| Execute query | `mongoTemplate.aggregate(...)` | `aggregate` command |
| Stream rows | `mongoTemplate.aggregateStream(...)` | cursor-backed aggregate |
| Map results | `AggregationResults<DTO>` | BSON result -> Java DTO |
| Input mapping | `TypedAggregation<Entity>` | `@Field` Java -> BSON |
| Options | `AggregationOptions` | `maxTime`/`allowDiskUse`/... |

### 35.1. Common Pipeline Pattern

~~~java
TypedAggregation<OrderEntity> agg = newAggregation(
        OrderEntity.class,
        match(Criteria.where("tenantId").is(trustedTenantId)
                .and("status").is("PAID")),
        group("region")
                .count().as("orderCount")
                .sum("grossAmount").as("revenue"),
        project("orderCount", "revenue")
                .and("_id").as("region")
                .andExclude("_id"),
        sort(Sort.by(
                Sort.Order.desc("revenue"),
                Sort.Order.asc("region")))
);

List<RegionRevenue> result = mongoTemplate
        .aggregate(agg, RegionRevenue.class)
        .getMappedResults();
~~~

### 35.2. Pre-Flight Checklist Before Calling `aggregate`

1. Are **input field names** Java properties or BSON field names?
2. Did earlier stages **retain** every field needed by later stages?
3. Is the group key inside **`_id`** or projected to its own alias?
4. How many **output documents** can be returned, and does the DTO match both cardinality and types?
5. Are numeric outputs `Decimal128`, `Double`, `Int64`, or `String`?
6. Does date grouping require a business timezone?
7. Are tenant and ACL checks enforced across all branches and joins?
8. Is output bounded and can the query leverage an index?

## 36. References

Capabilities and API names can vary across Spring Data and MongoDB server versions. Consult the official documentation:

- [Spring Data MongoDB — Aggregation Framework Support](https://docs.spring.io/spring-data/mongodb/reference/mongodb/aggregation-framework.html)
- [Spring Data MongoDB — Repository Query Methods and @Aggregation](https://docs.spring.io/spring-data/mongodb/reference/mongodb/repositories/query-methods.html)
- [Spring Data MongoDB — MongoTemplate API](https://docs.spring.io/spring-data/mongodb/reference/api/java/org/springframework/data/mongodb/core/MongoTemplate.html)
- [Spring Data MongoDB — Aggregation API](https://docs.spring.io/spring-data/mongodb/reference/api/java/org/springframework/data/mongodb/core/aggregation/Aggregation.html)
- [Spring Data MongoDB — TypedAggregation API](https://docs.spring.io/spring-data/mongodb/reference/api/java/org/springframework/data/mongodb/core/aggregation/TypedAggregation.html)
- [Spring Data MongoDB — AggregationResults API](https://docs.spring.io/spring-data/mongodb/reference/api/java/org/springframework/data/mongodb/core/aggregation/AggregationResults.html)
- [Spring Data MongoDB — AggregationOptions API](https://docs.spring.io/spring-data/mongodb/reference/api/java/org/springframework/data/mongodb/core/aggregation/AggregationOptions.html)
- [MongoDB Manual — Aggregation Pipeline](https://www.mongodb.com/docs/manual/core/aggregation-pipeline/)
- [MongoDB Manual — Aggregation Stages](https://www.mongodb.com/docs/manual/reference/operator/aggregation-pipeline/)
- [MongoDB Manual — Aggregation Pipeline Optimization](https://www.mongodb.com/docs/manual/core/aggregation-pipeline-optimization/)

Once Spring Boot dependency management selects a specific Spring Data release line, consult the **API reference for that exact version** rather than mixing syntax across releases.

## 37. Conclusion

Aggregation in Spring Data MongoDB spans two layers you must master:

~~~text
          JAVA / SPRING DATA LAYER

  Domain Entity + @Field metadata
                   |
                   v
  AggregationOperation / TypedAggregation
                   |
                   v
              MongoTemplate
                   |
                   v
          MONGODB SERVER LAYER

   $match -> $group -> $project -> $sort
                   |
                   v
            BSON result documents
                   |
                   v
          JAVA / SPRING DATA LAYER

         MappingMongoConverter
                   |
                   v
         AggregationResults<DTO>
                   |
                   v
            Service / REST API
~~~

**Core principles:**

1. **A pipeline is a sequential transformation**; each stage's output dictates which fields the next stage can reference.
2. **`TypedAggregation`** maps Java properties via **`@Field`**, yet you must still understand BSON names and stage-created aliases.
3. **`$group` places the grouping key in `_id`**; project explicit aliases whenever the DTO expects `region`, `status`, or `category`.
4. **The DTO is an output contract**; never reuse the input entity once `$group`, `$project`, or `$lookup` alters the schema.
5. **BSON numeric types dictate Java types.** For money, prefer `Decimal128`/`BigDecimal` with explicit rounding rules.
6. **`$unwind` multiplies intermediate rows**; never confuse item row counts with distinct order counts.
7. **`$lookup` returns an array**; handle nulls explicitly and enforce tenant permissions on joins.
8. **`$facet` simplifies multi-branch dashboards** but must stay within output size and memory limits.
9. **`AggregationResults`** distinguishes lists, unique results, and raw output; **`aggregateStream`** suits large outputs when the cursor-backed stream is properly closed.
10. **Correctness and performance go hand in hand**: tenant filtering, indexes/query plans, bounded results, timeouts, integration tests, and authorization must all be designed deliberately.

The key principle is **writing pipelines aligned with exact business metrics and mapping outputs to the exact final BSON shape**. When you clearly separate input entities, intermediate stage fields, MongoDB aliases, and Java output DTOs, Spring Data MongoDB reporting becomes readable, testable, and resilient against silent data bugs.
