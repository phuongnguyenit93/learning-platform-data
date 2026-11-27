# Mapping Results to DTOs and Reading Raw `Document` Outputs

## 1. When Aggregation No Longer Returns the Source Document Shape

In the **Basic Aggregation** chapter of **Spring Data MongoDB**, a pipeline often starts with `$match`, followed by `$group`, `$project`, and `$sort`. Unlike a regular `find` query, **the document shape after a pipeline may no longer resemble the source entity**.

For example, the `sales_orders` collection contains orders:

~~~json
{
  "_id": "o-101",
  "tenantId": "tenant-a",
  "status": "PAID",
  "region_code": "HCM",
  "amount_vnd": 120000,
  "createdAt": { "$date": "2026-11-20T08:00:00Z" }
}
~~~

A regional revenue report instead needs one row per region:

~~~json
{
  "regionCode": "HCM",
  "orderCount": 2,
  "revenueVnd": 200000
}
~~~

There is no longer an "order" object corresponding to that result row. `regionCode` is a group key, `orderCount` is an order count, and `revenueVnd` is an aggregated sum. Therefore:

- **DTO / Java record** is the right result type when the report structure **is well-defined**.
- **`org.bson.Document`** fits flexible inspection, BSON debugging, evolving pipeline structures, or checking fields not yet placed into a DTO.
- **`AggregationResults<T>`** holds mapped results while also exposing raw command-level aggregation reply details when inspection is needed.

Mapping a report row into `SalesOrder` merely because the pipeline reads from `sales_orders` leaves missing fields as `null`/defaults or causes materialization failures. **The output type must reflect the *pipeline's output schema*, not just the input collection.**

### Lesson Objectives

1. Clearly separate source entities, per-stage BSON shapes, and target DTOs.
2. Use `MongoTemplate.aggregate(...)` and `AggregationResults<T>` to materialize record/class DTOs.
3. Understand `getMappedResults()`, `getUniqueMappedResult()`, and `getRawResults()`.
4. Read row-by-row results via `AggregationResults<Document>` without confusing it with **raw command replies**.
5. Handle `$group`'s `_id`, `$project`, aliases, `@Field`, and BSON data types.
6. Test against real MongoDB to verify DTO results, `Document` structure, and performance.

> Examples use Java 17+, Spring Boot 3.x, Spring Data MongoDB 4.x, and compatible MongoDB versions. Exact overloads, mapping behavior, and metadata details can vary across versions. Always check the API and run integration tests on your project's versions rather than inferring from class names.

## 2. Three Data Layers: Source Entity, Output Document, and DTO

| Data Layer | Definition | Sample Shape |
|---|---|---|
**Source entity** | Stored document; mapped via `@Document`/`@Field` | `SalesOrder`: `id`, `tenantId`, `status`, `regionCode`, `amountVnd` |
**Pipeline output BSON** | MongoDB document returned after `$group`/`$project` | `{ regionCode, orderCount, revenueVnd }` |
**Target DTO** | Java object materialized from pipeline output | `RegionRevenueDto` record or `RegionRevenueClassDto` |

Conceptual data flow:

~~~mermaid
flowchart TD
    A["Collection sales_orders"] --> B["Entity metadata: @Document, @Field"]
    B --> C["$match: filter tenant and PAID"]
    C --> D["$group: _id and accumulators"]
    D --> E["$project: define output aliases"]
    E --> F["$sort: rank results"]
    F --> G["Result BSON documents"]
    G --> H["MappingConverter"]
    H --> I["RegionRevenueDto"]
    G --> J["org.bson.Document"]
    F --> K["AggregationResults: data and raw reply"]
~~~

**Note:** `$group` turns many input documents into one document per group. `$project` can rename fields, evaluate expressions, and drop fields. As a result, the final output no longer needs every field of the source entity.

Separate two questions:

- "**Which fields did MongoDB produce?**" → inspect BSON output or `Document`.
- "**Which Java types should represent those fields?**" → design the DTO and test conversion.

## 3. Source Entity and Shared Dataset

We use the `sales_orders` collection; each document represents a paid or cancelled order. In this example, monetary amounts are **integer VND**; multi-currency or fractional-unit systems must design `Decimal128`/`BigDecimal` and explicit rounding rules.

**SalesOrder.java**

~~~java
package com.example.sales;

import java.time.Instant;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.mapping.MongoId;

@Document(collection = "sales_orders")
public record SalesOrder(
        @MongoId(FieldType.STRING) String id,
        String tenantId,
        String status,
        @Field("region_code") String regionCode,
        @Field("amount_vnd") long amountVnd,
        Instant createdAt) {
}
~~~

Entity metadata:

- Java property `id` maps to BSON `_id`; `@MongoId(FieldType.STRING)` stores IDs as BSON String.
- Java property `regionCode` maps to BSON `region_code`.
- Java property `amountVnd` maps to BSON `amount_vnd`.
- `tenantId` and `status` share identical names in Java and BSON.
- `createdAt` uses `Instant`; conversion and timestamp precision depend on Spring Data configuration and BSON Date.

We have five sample documents:

| ID | tenantId | status | region_code | amount_vnd |
|---|---|---|---|---:|
| `o-101` | `tenant-a` | `PAID` | `HCM` | 120,000 |
| `o-102` | `tenant-a` | `PAID` | `HCM` | 80,000 |
| `o-103` | `tenant-a` | `PAID` | `HN` | 50,000 |
| `o-104` | `tenant-a` | `CANCELLED` | `HN` | 999,000 |
| `o-105` | `tenant-b` | `PAID` | `HCM` | 700,000 |

The report "PAID order revenue for tenant-a" must yield **two rows**, excluding CANCELLED orders and never leaking tenant-b:

| regionCode | orderCount | revenueVnd |
|---|---:|---:|
| `HCM` | 2 | 200,000 |
| `HN` | 1 | 50,000 |

This serves as our reference baseline when comparing DTO and `Document` outputs in the sections below.

## 4. Defining the Target DTO as a Java Record

When an API defines three fixed report fields, a record expresses the contract concisely:

**RegionRevenueDto.java**

~~~java
package com.example.sales;

public record RegionRevenueDto(
        String regionCode,
        long orderCount,
        long revenueVnd) {
}
~~~

Spring Data uses record metadata to instantiate objects via the canonical constructor where mapping/version supports it. Accessors are `regionCode()`, `orderCount()`, and `revenueVnd()`, **not** `getRegionCode()`.

Example:

~~~java
RegionRevenueDto row =
        new RegionRevenueDto("HCM", 2L, 200000L);

String code = row.regionCode();
long count = row.orderCount();
long sum = row.revenueVnd();
~~~

Advantages:

- Clear field names, avoiding `Document.get(...)` calls scattered across service code.
- Shallowly immutable, with no setters to accidentally mutate results.
- Built-in value-based `equals`/`hashCode`, convenient for assertions in tests.
- Clean API response shapes without leaking source document metadata.

**Caveat:** a record does not guarantee MongoDB schema validity. If the pipeline omits `regionCode`, outputs mismatched types, or returns `null` for `revenueVnd` when the DTO declares primitive `long`, mapping may fail or produce unexpected defaults depending on configuration. **Always verify actual BSON output, not just DTO types.**

### 4.1. Class-Based DTOs with Constructors Also Work

Records are not the only option. An explicit DTO class:

**RegionRevenueClassDto.java**

~~~java
package com.example.sales;

import org.springframework.data.annotation.PersistenceCreator;

public final class RegionRevenueClassDto {
    private final String regionCode;
    private final long orderCount;
    private final long revenueVnd;

    @PersistenceCreator
    public RegionRevenueClassDto(
            String regionCode, long orderCount, long revenueVnd) {
        this.regionCode = regionCode;
        this.orderCount = orderCount;
        this.revenueVnd = revenueVnd;
    }

    public String getRegionCode() { return regionCode; }
    public long getOrderCount() { return orderCount; }
    public long getRevenueVnd() { return revenueVnd; }
}
~~~

Class DTOs require proper constructor mapping. `@PersistenceCreator` tells Spring Data which constructor to use when multiple constructors exist; with a single constructor, the annotation is typically optional. For standard Java classes, preserving parameter names via the `-parameters` compiler flag enables property-name-based constructor binding.

Never annotate an aggregated DTO with `@Document(collection = "sales_orders")` just because its data comes from that collection. A DTO is an **output shape**, not an aggregate root to pass to `save`.

## 5. Building the `$match → $group → $project → $sort` Pipeline

Before writing Java, define the target MongoDB pipeline:

~~~javascript
db.sales_orders.aggregate([
  {
    $match: {
      tenantId: "tenant-a",
      status: "PAID"
    }
  },
  {
    $group: {
      _id: "$region_code",
      orderCount: { $sum: 1 },
      revenueVnd: { $sum: "$amount_vnd" }
    }
  },
  {
    $project: {
      _id: 0,
      regionCode: "$_id",
      orderCount: 1,
      revenueVnd: 1
    }
  },
  {
    $sort: { revenueVnd: -1, regionCode: 1 }
  }
]);
~~~

### 5.1. How Each Stage Transforms Data

| Stage | Shape and Meaning |
|---|---|
`$match` | Keeps `tenant-a` and `PAID` orders; documents still retain `_id`, `region_code`, `amount_vnd`, ... |
`$group` | Creates one document per region key: `{ "_id": "HCM", "orderCount": 2, "revenueVnd": 200000 }` |
`$project` | Renames group `_id` to `regionCode` and excludes `_id` from output |
`$sort` | Orders regions by revenue descending, then region code ascending |

**Easy-to-miss detail:** `$group` outputs the group key in `_id`; it **does not automatically emit `regionCode`**. For the record's `regionCode` component to bind, add `$project` or an equivalent output alias.

Stages see only the preceding stage's output, so the final `$sort` must reference fields **surviving in the output**. If `$project` drops `revenueVnd` and `$sort` still references it, the pipeline no longer reflects the original intent.

### 5.2. `$match` Before `$group`: Correct and Usually Faster

Putting tenant/status conditions in `$match` before grouping reduces documents entering `$group` and allows index usage. Filtering tenant after `$group` risks losing tenant metadata, aggregating out-of-scope records, and leaking cross-tenant data.

Never filter by tenant in Java **after receiving a multi-tenant group summary**. By then amounts have already been mixed on the server; filtering the response cannot restore correctness or security.

## 6. `MongoTemplate.aggregate` Returning a DTO

Here is the complete Java implementation of Section 5's pipeline. We use `aggregate(aggregation, SalesOrder.class, RegionRevenueDto.class)` so Spring Data knows both the **source entity** and the **target type**.

**RegionSalesReportService.java**

~~~java
package com.example.sales;

import java.util.List;
import org.bson.Document;
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.aggregation.Aggregation;
import org.springframework.data.mongodb.core.aggregation.AggregationResults;
import org.springframework.stereotype.Service;
import org.springframework.data.mongodb.core.query.Criteria;

import static org.springframework.data.mongodb.core.aggregation.Aggregation.*;

@Service
public class RegionSalesReportService {
    private final MongoTemplate mongo;

    public RegionSalesReportService(MongoTemplate mongo) {
        this.mongo = mongo;
    }

    private Aggregation revenuePipeline(String tenantId) {
        if (tenantId == null || tenantId.isBlank()) {
            throw new IllegalArgumentException("Invalid tenantId");
        }

        return newAggregation(
                match(Criteria.where("tenantId").is(tenantId)
                        .and("status").is("PAID")),
                group("regionCode")
                        .count().as("orderCount")
                        .sum("amountVnd").as("revenueVnd"),
                project("orderCount", "revenueVnd")
                        .and("_id").as("regionCode")
                        .andExclude("_id"),
                sort(Sort.by(
                        Sort.Order.desc("revenueVnd"),
                        Sort.Order.asc("regionCode"))));
    }

    public AggregationResults<RegionRevenueDto> typed(
            String tenantId) {
        return mongo.aggregate(
                revenuePipeline(tenantId),
                SalesOrder.class,
                RegionRevenueDto.class);
    }

    public AggregationResults<Document> documents(
            String tenantId) {
        return mongo.aggregate(
                revenuePipeline(tenantId),
                SalesOrder.class,
                Document.class);
    }

    public List<RegionRevenueClassDto> classDtos(
            String tenantId) {
        return mongo.aggregate(
                revenuePipeline(tenantId),
                SalesOrder.class,
                RegionRevenueClassDto.class)
                .getMappedResults();
    }
}
~~~

Key highlights:

1. `revenuePipeline` constructs the **aggregation pipeline** without executing a query yet.
2. `group("regionCode")` and `sum("amountVnd")` use **Java properties** from the source entity; during typed execution, Spring Data applies mapping metadata to target BSON `region_code` and `amount_vnd`.
3. `project(...).and("_id").as("regionCode")` produces the output field name matching the DTO.
4. `andExclude("_id")` drops the `_id` group key; the DTO only wants `regionCode`.
5. `sort(...)` runs on the **output fields** emitted by the projection stage.
6. The exact same pipeline can materialize into a Java record, class DTO, or `Document`.

**Overload note:** If you call `aggregate(aggregation, "sales_orders", RegionRevenueDto.class)` passing only a **collection name** instead of the source entity type, Spring Data may lack metadata to translate Java properties via `SalesOrder`'s `@Field` annotations. When authoring pipelines with Java property names, prefer the overload taking `SalesOrder.class` and inspect the emitted BSON.

### 6.1. Reading the DTO List

~~~java
AggregationResults<RegionRevenueDto> results =
        reportService.typed("tenant-a");

List<RegionRevenueDto> rows =
        results.getMappedResults();

for (RegionRevenueDto row : rows) {
    System.out.println(
            row.regionCode() + ": " +
            row.orderCount() + " orders, " +
            row.revenueVnd() + " VND");
}
~~~

`reportService` is a `RegionSalesReportService` bean. With Section 3's data, expected output is:

~~~text
HCM: 2 orders, 200000 VND
HN: 1 orders, 50000 VND
~~~

`getMappedResults()` returns the list of objects **mapped by Spring Data**. When a pipeline produces zero rows, the list is empty; do not expect a zero-filled DTO row. With `$group`, empty input produces zero group rows, so define explicit service semantics if the API requires a zero-total fallback.

## 7. `AggregationResults<T>`: `getMappedResults` and `getUniqueMappedResult`

`AggregationResults<T>` is the primary wrapper returned by `MongoTemplate.aggregate(...)`. Common methods:

| Method | Return Value | Best Used For |
|---|---|---|
`getMappedResults()` | `List<T>` of all documents mapped to `T` | Regional reports, group lists, rankings |
`getUniqueMappedResult()` | Single `T` or `null` if none; multiple results violate uniqueness contract | Tenant-wide summary expected to return at most one row |
`getRawResults()` | `org.bson.Document` containing raw command-level reply | Diagnosing command/metadata replies, not listing DTOs |

**Never call `getUniqueMappedResult()`** on a regional breakdown pipeline when two or more regions can exist. Its contract expects at most one result and throws an error when multiple documents return.

### 7.1. A Pipeline Returning a Single Summary Row

To report total orders and revenue across an entire tenant **without grouping by region**:

**TotalRevenueDto.java**

~~~java
package com.example.sales;

public record TotalRevenueDto(
        long orderCount,
        long revenueVnd) {
}
~~~

Additional method in the service:

~~~java
import org.springframework.data.mongodb.core.aggregation.Aggregation;
import org.springframework.data.mongodb.core.aggregation.AggregationResults;
import org.springframework.data.mongodb.core.query.Criteria;

import static org.springframework.data.mongodb.core.aggregation.Aggregation.*;

public TotalRevenueDto totalForTenant(String tenantId) {
    Aggregation pipeline = newAggregation(
            match(Criteria.where("tenantId").is(tenantId)
                    .and("status").is("PAID")),
            group()
                    .count().as("orderCount")
                    .sum("amountVnd").as("revenueVnd"),
            project("orderCount", "revenueVnd")
                    .andExclude("_id"));

    AggregationResults<TotalRevenueDto> results =
            mongo.aggregate(pipeline, SalesOrder.class, TotalRevenueDto.class);

    return results.getUniqueMappedResult();
}
~~~

This method is meant to be **added inside `RegionSalesReportService`** which owns the `mongo` field, not placed as a standalone Java file. Keyless `group()` puts the entire filtered set into one group; `$project` retains only the two summary values.

If zero orders match, `$group` emits **zero rows**, so `getUniqueMappedResult()` returns `null`. The service layer must establish a clear contract: return `null`, `Optional.empty()`, or an application-created zero-total DTO. Never let an API silently alternate between `null` and a zero object without a contract.

### 7.2. Output Row Count Does Not Equal Source Document Count

A regional report returning **two DTOs** does not mean only two orders matched `$match`. In the sample data, `tenant-a` has **three PAID orders** yet only two **groups**. When interpreting counts:

- `rows.size() == 2` is the number of **pipeline output documents**.
- Summing `orderCount` across the two rows equals 3, the number of orders grouped.
- Source document counts must be derived from an explicit accumulator or separate count query, never from DTO list length.

## 8. Raw `Document` at the Result-Row Level

When a DTO is not finalized yet, or you want to inspect the exact fields produced by aggregation, return `AggregationResults<org.bson.Document>`:

~~~java
AggregationResults<Document> rawRowsResult =
        reportService.documents("tenant-a");

List<Document> rows = rawRowsResult.getMappedResults();

for (Document row : rows) {
    String region = row.getString("regionCode");
    Object count = row.get("orderCount");
    Object revenue = row.get("revenueVnd");

    System.out.println(region + " / " + count + " / " + revenue);
}
~~~

Here `reportService.documents(...)` called `aggregate(..., SalesOrder.class, Document.class)`. Because the **target type is `Document.class`**, each element in `getMappedResults()` is one **post-pipeline** document:

~~~json
{
  "regionCode": "HCM",
  "orderCount": 2,
  "revenueVnd": 200000
}
~~~

Notice how this differs from source `SalesOrder`: `tenantId`, `status`, and `amount_vnd` are gone—dropped or aggregated away.

### 8.1. Read Numbers via `Number`, Never Guess Int32 vs. Int64

`$sum: 1` or `$sum: "$amount_vnd"` can return different BSON numeric types depending on inputs, value ranges, and operators. Avoid assuming:

~~~java
long count = row.getLong("orderCount"); // May fail if BSON is Int32.
~~~

Safer handling when an integer count is expected:

~~~java
Object countValue = row.get("orderCount");
if (!(countValue instanceof Number countNumber)) {
    throw new IllegalStateException("orderCount is not a number");
}

long count = countNumber.longValue();
~~~

Still, `Number.longValue()` can truncate fractions or overflow if values exceed 64-bit integer bounds. In production code, **check both type and range** before converting; for `Decimal128`, convert to `BigDecimal` rather than blindly calling `longValue()`.

### 8.2. `Document` Is Dynamic

`Document` supports:

~~~java
String region = row.getString("regionCode");
boolean hasRevenue = row.containsKey("revenueVnd");
Object rawRevenue = row.get("revenueVnd");
String diagnosticJson = row.toJson();
~~~

`toJson()` is handy for inspecting structures, though it may emit Extended JSON for certain BSON types. It **does not replace an API JSON contract**, and you should never log full documents if they contain emails, tokens, financial figures, or sensitive tenant data.

If a pipeline renames a field, `row.get("revenueVnd")` returns `null` when absent. On a primitive DTO field, that mismatch may surface during mapping; with `Document`, the risk of **silently accepting missing fields** is higher unless validated explicitly.

## 9. `getRawResults` Is Not `getMappedResults<Document>`

Two distinct things are often both loosely called "raw":

~~~java
AggregationResults<RegionRevenueDto> typed =
        reportService.typed("tenant-a");

// 1) Result rows mapped into DTOs.
List<RegionRevenueDto> dtoRows = typed.getMappedResults();

// 2) Server/driver-level raw BSON reply of the aggregation command.
Document commandReply = typed.getRawResults();
~~~

`getRawResults()` returns a `Document` representing the **raw command reply** retained by Spring Data, which may hold metadata like `ok`, cursor structures, or protocol/version-dependent fields. It is **not** a single regional report `Document`, nor should it be treated as a stable API for walking batches by guessing keys.

To read **individual BSON output rows**, use:

~~~java
List<Document> dataRows =
        reportService.documents("tenant-a")
                .getMappedResults();
~~~

To read **each row as a DTO**:

~~~java
List<RegionRevenueDto> mappedRows =
        reportService.typed("tenant-a")
                .getMappedResults();
~~~

To inspect the **actual MongoDB command sent to the server**, `getRawResults()` is usually not what you want. Use the MongoDB Java Driver's `CommandListener` in tests or authorized profiler/explain tools to inspect the real BSON pipeline.

### 9.1. Why Not Extract `cursor.firstBatch` Manually?

Depending on `commandReply.get("cursor", ...).get("firstBatch")` couples application code to internal protocol/cursor shapes and Spring Data's internal reply handling. Driver updates, batch sizes, or response format shifts can break it while `getMappedResults()` continues working normally.

Use the high-level `AggregationResults<T>` APIs for business data. Reserve raw command replies strictly for **diagnostics** written to tolerate version changes.

## 10. `$group._id`, Aliases, and Constructor Mapping

This is the single most common source of bugs when mapping aggregations into DTOs.

### 10.1. Missing `$project`: Only `_id` Exists, Not `regionCode`

Pipeline:

~~~javascript
db.sales_orders.aggregate([
  { $match: { tenantId: "tenant-a", status: "PAID" } },
  {
    $group: {
      _id: "$region_code",
      orderCount: { $sum: 1 },
      revenueVnd: { $sum: "$amount_vnd" }
    }
  }
]);
~~~

Returns:

~~~json
{
  "_id": "HCM",
  "orderCount": 2,
  "revenueVnd": 200000
}
~~~

Yet `RegionRevenueDto` expects:

~~~java
public record RegionRevenueDto(
        String regionCode, long orderCount, long revenueVnd) {}
~~~

`regionCode` does not exist in the BSON output. Depending on converter/constructor behavior, that component may receive `null` or mapping may fail on invariants. **Never assume group `_id` automatically binds to a constructor parameter named `regionCode`.**

### 10.2. The Fix: Explicit Alias After Grouping

~~~javascript
{
  $project: {
    _id: 0,
    regionCode: "$_id",
    orderCount: 1,
    revenueVnd: 1
  }
}
~~~

Now the **output document's** field name matches the record's component name. When API contracts require a different name, alias it in the pipeline or apply DTO field/annotation mapping and verify with tests.

### 10.3. Aliases Are Part of the Contract Between Pipeline and DTO

A naming mismatch such as:

~~~javascript
{ $project: { region: "$_id", orderCount: 1, revenueVnd: 1 } }
~~~

will not resolve itself just because the Java record has `regionCode`. There is no implicit link between `region` and `regionCode`. For dynamic results or multi-report handlers, prefer an explicit translation step rather than scattering "alias guessing" logic across controllers.

## 11. Mapping `@Field`: Input Properties vs. Output Aliases

In `SalesOrder`:

~~~java
@Field("region_code") String regionCode,
@Field("amount_vnd") long amountVnd,
~~~

Suppose you write a typed aggregation:

~~~java
Aggregation aggregation = newAggregation(
        group("regionCode")
                .sum("amountVnd").as("revenueVnd"));
~~~

When `SalesOrder.class` is given as the **input type**, Spring Data MongoDB translates source property references into:

~~~javascript
{
  $group: {
    _id: "$region_code",
    revenueVnd: { $sum: "$amount_vnd" }
  }
}
~~~

After `$project`, however, `regionCode` is a **new output field created by the pipeline**, no longer a direct reference to a source property in every stage. Think of a pipeline as a **schema transformation chain**:

~~~text
Input:
    region_code, amount_vnd, tenantId, status

After $group:
    _id, revenueVnd, orderCount

After $project:
    regionCode, revenueVnd, orderCount
~~~

Therefore:

- `@Field` on the source entity describes fields **stored in MongoDB**.
- `as("regionCode")` names fields **in pipeline output**.
- Target DTOs/records must match names and types **post-pipeline**.
- When using raw `Document` stages, be careful because paths inside raw BSON may bypass the typed builder's mapping metadata.

### 11.1. Input Collection Name Instead of Input Class

Example lacking source metadata:

~~~java
// When the pipeline uses Java property names but only passes collection name,
// verify whether the mapper has enough context.
mongo.aggregate(
        aggregation, "sales_orders", RegionRevenueDto.class);
~~~

In this lesson we prefer:

~~~java
mongo.aggregate(
        aggregation, SalesOrder.class, RegionRevenueDto.class);
~~~

Reason: passing the source entity type explicitly gives Spring Data `regionCode -> region_code` and `amountVnd -> amount_vnd`. If a project requires passing a collection name string, construct a `TypedAggregation<SalesOrder>` or write the pipeline using **physical BSON names** and test it.

Never mix `regionCode` and `region_code` haphazardly across stages: doing so can let filters match while grouping into a single `null` bucket or projecting missing fields.

## 12. BSON Numeric Types, Null/Missing, and `Decimal128`

### 12.1. Why Must Sum/Count Outputs Be Type-Tested?

MongoDB uses BSON numeric types such as Int32, Int64, Double, and Decimal128. When computing `$sum`:

- Small numbers may come back as Int32 or Int64 depending on operators and data.
- Operations on Double or Decimal128 sources yield corresponding numeric types.
- Overflow, nulls, huge totals, and mistyped fields obey MongoDB semantics and business contracts.

With the DTO:

~~~java
public record RegionRevenueDto(
        String regionCode, long orderCount, long revenueVnd) {}
~~~

Spring Data converters can translate compatible BSON numbers into Java `long`. Yet they cannot guarantee every dataset stays within `long` bounds. Test large values and real data types, not just small amounts of a few thousand dong.

### 12.2. `Document` Requires Explicit Type Checking

~~~java
Document row = dataRows.get(0);

Object revenue = row.get("revenueVnd");
if (revenue instanceof Number number) {
    long value = number.longValue();
    // Valid only when business rules guarantee integers without overflow.
} else {
    throw new IllegalStateException("revenueVnd is not a number");
}
~~~

When reports use `Decimal128`, expect `org.bson.types.Decimal128` and convert to `BigDecimal`:

~~~java
import java.math.BigDecimal;
import org.bson.types.Decimal128;

Object value = row.get("revenueVnd");
if (value instanceof Decimal128 decimal) {
    BigDecimal exact = decimal.bigDecimalValue();
}
~~~

Never default to converting via `double` and then constructing `BigDecimal` for financial figures: binary floating-point introduces precision errors.

### 12.3. Null Group Keys and Missing Fields

If some orders have `region_code: null` or omit `region_code`, `$group` by region emits an `_id: null` group. After `$project`, the DTO gets `regionCode == null`. Your application must decide:

- Reject/migrate documents missing a region.
- Group under an explicit `UNKNOWN` bucket by policy.
- Filter out region-less documents before `$group` if defined by the report.

Never silently convert `null` into `"HCM"` or merge it into another region simply because a DTO dislikes nulls. In financial reports, dropping a group can cause report totals to diverge from source totals.

### 12.4. Missing or Mistyped Values in `$sum`

If `amount_vnd` is missing or non-numeric, `$sum` follows specific accumulator rules that can drop contributions or produce unexpected results. On unnormalized legacy data, explicitly define:

1. Which orders qualify for the report?
2. Is the monetary field mandatory, and which BSON types are accepted?
3. Are malformed records **excluded, logged separately, or fatal to the report**?
4. Is reconciliation against another source of truth required?

A clean DTO cannot rescue a pipeline that selects or aggregates flawed data.

## 13. Nested Documents, Array Outputs, and When Not to Map a DTO Yet

Aggregations do not only emit flat documents. `$push` creates arrays, `$facet` creates multi-branch structures, and `$lookup` creates joined document arrays. While output shapes evolve frequently, `Document` is useful for exploration:

~~~json
{
  "regionCode": "HCM",
  "orderCount": 2,
  "sampleOrders": [
    { "id": "o-101", "amountVnd": 120000 },
    { "id": "o-102", "amountVnd": 80000 }
  ]
}
~~~

Code reading the array with validation:

~~~java
Document report = dataRows.get(0);
List<Document> orders =
        report.getList("sampleOrders", Document.class);

if (orders != null) {
    for (Document order : orders) {
        String id = order.getString("id");
        Object amount = order.get("amountVnd");
        // Validate type before further monetary processing.
    }
}
~~~

**This illustrates an extended output shape**, not the output of the current regional pipeline (which has no `sampleOrders` yet). To test it, add the corresponding stages first; do not copy this verbatim into current tests expecting `sampleOrders` to exist.

Once the shape stabilizes, define nested DTOs:

~~~java
package com.example.sales;

import java.util.List;

public record OrderSnippetDto(
        String id, long amountVnd) {}

public record RegionDetailsDto(
        String regionCode,
        long orderCount,
        List<OrderSnippetDto> sampleOrders) {}
~~~

Place these two records in **two separate Java files** if both are top-level `public`, or make one non-public when sharing a file. This illustrates the DTO contract rather than output automatically produced by `RegionSalesReportService`.

Never return an unbounded array of orders via `$push` inside a summary report. In regions with millions of orders, arrays bloat memory and hit the **16 MiB BSON document size limit**. Cap items, expose a separate detail endpoint, or paginate as needed.

## 14. Choosing DTO vs. `Document` in Practice

| Criterion | DTO/Record | `org.bson.Document` |
|---|---|---|
Fixed output schema | Ideal | Usable, though requires manual key/type checks |
Business service/API integration | Clearer, more type-safe | Easy to leak DB structure if returned directly |
Debugging a new pipeline | Requires editing/rebuilding DTO on shape changes | Flexible; easy to inspect every field |
Catching missing fields / changed aliases | Mapping error or null depending on types | `get()` returns null; easy to overlook without validation |
Varying BSON numeric types | Converters can assist | Must handle Int32/Int64/Decimal128 manually |
Nested results | Nested DTOs once schema stabilizes | Easy to traverse documents/arrays during exploration |
Refactorability | Field names checked in code | Uses string keys; needs heavier test coverage |
Performance | Materialization cost | Also incurs BSON/Document materialization cost |
Exposing over public APIs | Design explicit response DTOs | Never expose raw `Document` directly |

**Practical guideline:** use `Document` to inspect and explore, then **lock in a DTO contract** for stable read paths. Never turn "DTOs are always faster" or "Document always avoids conversion" into unmeasured performance claims; the dominant costs are usually query plans, data volume, and network transfer.

### 14.1. Keep MongoDB Out of HTTP Contracts

Never return raw `Document` directly over HTTP just because it serializes easily. A `Document` may carry `_id`, internal fields, aggregation metadata, or BSON types needing explicit formatting. The API layer should:

- Select only publicly allowed fields.
- Return stable names defined by the API contract.
- Format money and timestamps consistently.
- Enforce tenant and role checks before running aggregation.
- Bound row counts and query execution times.

DTOs do not enforce security by themselves: **tenant filtering must happen in MongoDB**, not by mapping DTOs after aggregating the whole collection.

## 15. Performance, Indexes, and Result Volume

Aggregations returning DTOs or `Document` execute the **exact same server pipeline** when stages are identical. Switching Java output from `Document.class` to `RegionRevenueDto.class` does not make `$group` cheaper.

### 15.1. Index for the Leading `$match`

Candidate index:

~~~javascript
db.sales_orders.createIndex(
  { tenantId: 1, status: 1, region_code: 1 },
  { name: "idx_tenant_status_region" }
);
~~~

This can assist tenant/status filtering and read paths depending on the query, though always verify with actual `explain`. If `amount_vnd` is also regularly queried, evaluate a covering index if benchmarks justify it; wide indexes increase write overhead and storage, so do not blindly index every field.

### 15.2. Inspecting the Pipeline Plan

In MongoDB shell:

~~~javascript
db.sales_orders.explain("executionStats").aggregate([
  { $match: { tenantId: "tenant-a", status: "PAID" } },
  {
    $group: {
      _id: "$region_code",
      orderCount: { $sum: 1 },
      revenueVnd: { $sum: "$amount_vnd" }
    }
  },
  {
    $project: {
      _id: 0, regionCode: "$_id",
      orderCount: 1, revenueVnd: 1
    }
  }
]);
~~~

Measure examined documents/keys, execution time, and memory-intensive stages. `$group` can consume substantial memory with high group cardinality; depending on server version, limits, and settings, you may need disk spill or pre-aggregated/materialized views.

### 15.3. `getMappedResults` Materializes a List

`getMappedResults()` returns a `List<T>`, holding all result objects in application memory. For a handful of regions, cost is negligible. For pipelines emitting millions of documents, never materialize an unbounded `List` out of convenience.

In supported versions, `MongoTemplate.aggregateStream(...)` provides a `Stream<T>` for sequential processing with proper resource closing:

~~~java
try (java.util.stream.Stream<RegionRevenueDto> stream =
        mongo.aggregateStream(
                aggregation, SalesOrder.class, RegionRevenueDto.class)) {
    stream.forEach(row -> {
        // Process row by row; avoid buffering all results.
    });
}
~~~

Here `aggregation` is a pipeline in scope. Streams/cursors must be **closed** and never held open across HTTP requests. Switching to streaming does not fix an inefficient server-side pipeline.

### 15.4. Limiting and Sorting After Grouping

`$sort` + `$limit` is useful for "top 10 regions by revenue." Keep these rules in mind:

- `$limit` **before grouping** groups only a slice of orders, producing wrong revenue totals.
- `$limit` **after grouping/sorting** trims output rows while still aggregating all relevant source data.
- When sorting by revenue, add a tie-breaker like `regionCode` for stable order on ties.

Never apply offset pagination to a live mutating aggregation expecting a multi-request snapshot without dedicated consistency handling.

## 16. Testing DTOs and `Document` Against Real MongoDB

Mocking `MongoTemplate` verifies that a service calls `aggregate`, but fails to prove stage mapping, BSON aliases, or real numeric types. Write integration tests against real MongoDB, such as Testcontainers. In Spring Boot 3.x, `@DataMongoTest` configures the MongoDB test slice without **starting a server on its own**.

### 16.1. Seeding and Testing Record/Class DTO Mapping

**RegionSalesAggregationTest.java**

~~~java
package com.example.sales;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Instant;
import java.util.List;
import org.bson.Document;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.context.annotation.Import;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Query;

@DataMongoTest
@Import(RegionSalesReportService.class)
class RegionSalesAggregationTest {
    @Autowired
    MongoTemplate mongo;

    @Autowired
    RegionSalesReportService reports;

    private SalesOrder order(
            String id, String tenant, String status,
            String region, long amount, int hour) {
        return new SalesOrder(
                id, tenant, status, region, amount,
                Instant.parse("2026-11-20T00:00:00Z")
                        .plusSeconds(3600L * hour));
    }

    @BeforeEach
    void seed() {
        // Run only against an isolated test MongoDB.
        mongo.remove(new Query(), SalesOrder.class);
        mongo.insert(List.of(
                order("o-101", "tenant-a", "PAID", "HCM", 120000L, 8),
                order("o-102", "tenant-a", "PAID", "HCM", 80000L, 9),
                order("o-103", "tenant-a", "PAID", "HN", 50000L, 10),
                order("o-104", "tenant-a", "CANCELLED", "HN", 999000L, 11),
                order("o-105", "tenant-b", "PAID", "HCM", 700000L, 12)
        ), SalesOrder.class);
    }

    @Test
    void groupsSourceOrdersIntoTwoDtoRows() {
        List<RegionRevenueDto> rows =
                reports.typed("tenant-a").getMappedResults();

        assertThat(rows).containsExactly(
                new RegionRevenueDto("HCM", 2L, 200000L),
                new RegionRevenueDto("HN", 1L, 50000L));
    }

    @Test
    void classDtoUsesConstructorMapping() {
        List<RegionRevenueClassDto> rows =
                reports.classDtos("tenant-a");

        assertThat(rows).hasSize(2);
        assertThat(rows.get(0).getRegionCode()).isEqualTo("HCM");
        assertThat(rows.get(0).getOrderCount()).isEqualTo(2L);
        assertThat(rows.get(0).getRevenueVnd()).isEqualTo(200000L);
    }

    @Test
    void documentRowsHaveProjectedShapeAndNumericValues() {
        List<Document> rows =
                reports.documents("tenant-a").getMappedResults();

        assertThat(rows).hasSize(2);
        Document hcm = rows.get(0);

        assertThat(hcm.getString("regionCode")).isEqualTo("HCM");
        assertThat(hcm.containsKey("_id")).isFalse();
        assertThat(hcm.containsKey("amount_vnd")).isFalse();

        Object count = hcm.get("orderCount");
        Object revenue = hcm.get("revenueVnd");
        assertThat(count).isInstanceOf(Number.class);
        assertThat(revenue).isInstanceOf(Number.class);
        assertThat(((Number) count).longValue()).isEqualTo(2L);
        assertThat(((Number) revenue).longValue()).isEqualTo(200000L);
    }

    @Test
    void sourceFieldMappingAndTenantFilterRemainCorrect() {
        Document rawOrder = mongo.getCollection("sales_orders")
                .find(new Document("_id", "o-101")).first();

        assertThat(rawOrder).isNotNull();
        assertThat(rawOrder.getString("region_code")).isEqualTo("HCM");
        assertThat(rawOrder.containsKey("regionCode")).isFalse();
        assertThat(rawOrder.get("amount_vnd")).isInstanceOf(Number.class);

        assertThat(reports.typed("tenant-b").getMappedResults())
                .containsExactly(
                        new RegionRevenueDto("HCM", 1L, 700000L));
    }
}
~~~

Tests are organized around three contracts:

1. **Business results:** only tenant-a and PAID are included, with accurate totals.
2. **Java typed results:** record and class DTOs hold expected fields and values.
3. **Actual BSON:** source uses `region_code`/`amount_vnd`; output is aliased to `regionCode`/`revenueVnd` with `_id` removed.

This relies on a real MongoDB provided for testing. `@DataMongoTest` does not ensure a server is running on its own. Never call `remove(new Query(), ...)` or `dropCollection` on a database shared by concurrent tests; isolate test databases/collections or seed unique namespaces.

### 16.2. Additional Recommended Tests

| Scenario | Expectation to Verify |
|---|---|
Zero orders matching tenant/status | `getMappedResults()` empty; unique total may be null |
Single region | `getUniqueMappedResult()` works only when pipeline truly emits at most one doc |
Two regions | Never use unique result to mean "first region" |
Missing/null `region_code` | Null group or defined handling policy applied |
`amount_vnd` stored as another BSON type | Converter/`Document` reads accurately or errors clearly |
Pipeline omits `$project` alias | DTO shape breaks; test catches it |
`$match` omits tenant | Test with tenant-b data catches cross-tenant mixing |
Two regions tie in revenue | Tie-breaker sort yields deterministic order |
CANCELLED order with huge amount | Excluded from PAID report |
Aggregation using collection name instead of type | Verify mapping metadata explicitly rather than guessing |
Large output | Memory bounded or cursor-closed stream used |

### 16.3. Diagnosing the BSON Pipeline

To inspect the exact MongoDB command executed, attach MongoDB Java Driver's `CommandListener` and observe `CommandStartedEvent` in tests. Aggregation commands carry a `pipeline` array; verify `$match`, `$group`, `$project`, and `$sort` against **actual BSON field names**.

To inspect query plans, run `explain("executionStats")` on the equivalent pipeline in MongoDB shell. `AggregationResults.getRawResults()` returns the server's reply after execution; it does not replace command capture or explain.

When logging pipelines, redact sensitive information (tenants, accounts, amounts, or PII filters) and never enable full command logging in production without proper policies.

## 17. Common Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
Mapping `$group` output to the source order entity | Missing/null fields; misrepresents a grouped row | Design DTO matching the output schema |
Assuming `$group` preserves the grouped property name | Actual output puts key in `_id` | Add explicit `$project`/alias |
Forgetting to drop `_id` when DTO does not want it | Leaks metadata or mismatches contract | Use `andExclude("_id")` when appropriate |
Confusing `getRawResults()` with raw result rows | Code breaks parsing cursor/metadata structure | Use `AggregationResults<Document>.getMappedResults()` |
Calling `Document.getLong()` on BSON Int32 | Cast/type error | Check `Number` and value bounds |
Casting `Decimal128` through `double` for money | Precision loss | Keep `BigDecimal`/`Decimal128` per policy |
Renaming a DTO property without updating pipeline alias | Null fields or materialization errors | Test mapping and output shapes |
Mixing Java properties and physical BSON fields carelessly | Wrong grouping, zero/null sums, or empty filters | Use typed source mapping and inspect BSON |
Confusing DTO row count with grouped order count | Wrong document counts reported | Use an `orderCount` accumulator |
Missing tenant filter before grouping | Mixes revenue across tenants | Enforce auth-context tenant `$match` before aggregating |
Putting `$limit` before `$group` in summary reports | Revenue totals undercounted | Group all matching docs; limit after grouping |
Testing with only one region | Hides `getUniqueMappedResult()` misuse | Test zero, one, and multiple rows |
Collecting unbounded raw documents into a `List` | Memory exhaustion | Limit/stream and paginate appropriately |
Assuming switching DTO to `Document` speeds up queries | Misdiagnoses bottlenecks | Measure explain, network, conversion, and indexes |
Serializing raw `Document` directly in public APIs | Leaks MongoDB internals/BSON types | Use explicit response DTO contracts |
Testing only with mocks and no real MongoDB | Misses `@Field`/alias/type bugs | Run isolated MongoDB integration tests |

## 18. Practice Exercises

**Exercise 1 — Summary DTO.** Create `SalesOrder`, `RegionRevenueDto`, and the `$match → $group → $project → $sort` pipeline. Seed the 5 orders from Section 3; verify HCM has 2 orders / 200,000 VND and HN has 1 order / 50,000 VND.

**Exercise 2 — Raw `Document`.** Run the exact pipeline from Exercise 1 with `Document.class` as output. Print keys after `$project` and read `orderCount`/`revenueVnd` via `Number` into validated `long` values.

**Exercise 3 — Two Meanings of "Raw."** Compare `results.getRawResults()` with `aggregate(..., Document.class).getMappedResults()`. Explain why one is a **command-level reply** while the other is **individual result documents**.

**Exercise 4 — Missing Alias.** Remove `$project`. Observe `_id` in `Document`, then run against a DTO expecting `regionCode`. Fix the pipeline to satisfy the record contract and add a regression test.

**Exercise 5 — Unique Total.** Use `group()` to summarize all PAID orders of one tenant into `TotalRevenueDto`. Compare `getUniqueMappedResult()` vs. `getMappedResults()` on zero, one, and multiple rows.

**Exercise 6 — `@Field` and Source Type.** Keep `@Field("region_code")` and `@Field("amount_vnd")`. Compare typed input `SalesOrder.class` against the collection-name overload; inspect actual BSON filters/groups to recognize when mapping metadata is missing.

**Exercise 7 — Null/Missing.** Insert an order missing `region_code` and an order with `amount_vnd: null` in a test database (using raw BSON if needed). Define handling policy and test null groups/totals to prevent silent report corruption.

**Exercise 8 — Financial Arithmetic.** Test revenue values stored as Int32, Int64, Double, and Decimal128 in a test schema. Design a DTO and `Document` reader preserving exact amounts; explain the risks of `double`.

**Exercise 9 — Nested Aggregation.** Add `sampleOrders` via `$push` per region, then inspect shapes using `Document.getList`. Once stabilized, design nested record DTOs and cap item counts to avoid unbounded array growth.

**Exercise 10 — Performance.** Seed a large dataset and compare indexed vs. unindexed filters, running the same pipeline with DTO and `Document` outputs. Measure `explain("executionStats")`, documents scanned, elapsed time, app memory, and conversion cost; conclude only from real measurements.

## 19. Key Takeaways

In **Spring Data MongoDB**, `MongoTemplate.aggregate(...)` can return `AggregationResults<DTO>` when pipeline outputs have a defined schema, or `AggregationResults<Document>` when inspecting raw result documents directly. **`getMappedResults()`** returns materialized rows; **`getUniqueMappedResult()`** applies strictly when the pipeline emits at most one row; **`getRawResults()`** returns the command-level BSON reply, **not** the list of report rows.

When mapping from `$group` to a DTO, handle `_id` carefully and **alias via `$project`** so output documents match DTO field names. Pass the input entity type so Spring Data maps Java properties through `@Field`, while always verifying post-stage BSON names, numeric types, null/missing cases, and converter boundaries.

Choose **DTOs for stable application contracts and `Document` for inspection/schema exploration**, and verify both with integration tests against real MongoDB. Cleanly separating **source entity — output BSON — target DTO** keeps aggregations accurate, maintainable, and safely scoped.
