# Mapping Results to DTO, Scalar, or `AggregationResults`

> **Chapter:** Aggregation repository  
> **Module:** `SPRING_DATA_MONGODB` — use Spring Data MongoDB to connect, map documents, and work with data via `MongoTemplate` or repositories; practice aggregation, indexes, transactions, reactive access, testing, and performance diagnostics.  
> **Goal:** Declare `@Aggregation` on a repository; choose among return types including DTO/record, interface projection, scalar, `List<T>`, `Slice<T>`, `Stream<T>`, or `AggregationResults<T>`; understand how a `Document` is extracted into a scalar, distinguish `$group`'s `_id` from the original ID, handle empty results, aliases, mismatched types, and execution costs.

## 1. The problem: one pipeline, multiple ways to consume results

An `orders` collection stores many orders. The admin UI has different requirements:

1. **Summary list**: each status with its order count and total value.
2. **Numeric KPI**: total revenue of `PAID` orders for a tenant.
3. **Single-field list**: retrieve the statuses present in the dataset.
4. **Diagnostic report**: retrieve both mapped results and the raw aggregation response.

All of them use MongoDB aggregation, but the **Java return types differ**. A pipeline might produce documents like:

~~~javascript
[
  { state: "PAID", orderCount: 4, grossVnd: 1250000 },
  { state: "NEW", orderCount: 1, grossVnd: 100000 },
  { state: "CANCELLED", orderCount: 1, grossVnd: 80000 }
]
~~~

If the repository declares `List<StateSummary>`, Spring Data maps each document into a DTO. If the pipeline yields one document containing only `{ total: 1250000 }` and the method returns `Long`, Spring Data can **extract a scalar value**. If it returns `AggregationResults<StateSummary>`, the caller receives a wrapper containing both mapped data and raw response information.

~~~mermaid
flowchart TD
    A["Repository @Aggregation"] --> B["MongoDB aggregation pipeline"]
    B --> C["Document / Documents"]
    C --> D{"Method return type"}
    D --> E["DTO / record / interface projection"]
    D --> F["Scalar: Long / String"]
    D --> G["List / Slice / Stream"]
    D --> H["AggregationResults<T>"]
    H --> I["mappedResults + rawResults"]
~~~

**Core principle:** Mapping correctness depends on the **BSON shape after the final stage** — not on what fields the original entity still had. After `$group` and `$project`, the data has become a **read model**; you must design the output intentionally.

## 2. Sample dataset and baseline numbers for verification

### 2.1. Creating the fixture on a learning MongoDB instance

In `mongosh`, select an **isolated test database**. Do not run on a production collection:

~~~javascript
use spring_data_mongodb_lab

const orders = db.orders_repository_agg_demo_003;

orders.insertMany([
  {
    _id: "o701", tenant_id: "t01", state_code: "PAID",
    amount_vnd: NumberLong(120000),
    placed_at: ISODate("2026-10-01T08:00:00Z"),
    buyer_doc: { city_name: "Hà Nội" },
    order_lines: [{ sku: "A", qty: 2 }, { sku: "B", qty: 1 }]
  },
  {
    _id: "o702", tenant_id: "t01", state_code: "PAID",
    amount_vnd: NumberLong(350000),
    placed_at: ISODate("2026-10-02T08:00:00Z"),
    buyer_doc: { city_name: "Huế" },
    order_lines: [{ sku: "A", qty: 3 }]
  },
  {
    _id: "o703", tenant_id: "t01", state_code: "NEW",
    amount_vnd: NumberLong(100000),
    placed_at: ISODate("2026-10-03T08:00:00Z"),
    buyer_doc: { city_name: "Hà Nội" },
    order_lines: [{ sku: "C", qty: 1 }]
  },
  {
    _id: "o704", tenant_id: "t01", state_code: "PAID",
    amount_vnd: NumberLong(530000),
    placed_at: ISODate("2026-10-04T08:00:00Z"),
    buyer_doc: { city_name: "Hà Nội" },
    order_lines: [{ sku: "C", qty: 4 }]
  },
  {
    _id: "o705", tenant_id: "t02", state_code: "PAID",
    amount_vnd: NumberLong(900000),
    placed_at: ISODate("2026-10-05T08:00:00Z"),
    buyer_doc: { city_name: "Hồ Chí Minh" },
    order_lines: [{ sku: "A", qty: 9 }]
  },
  {
    _id: "o706", tenant_id: "t01", state_code: "CANCELLED",
    amount_vnd: NumberLong(80000),
    placed_at: ISODate("2026-10-06T08:00:00Z"),
    buyer_doc: { city_name: "Hà Nội" },
    order_lines: []
  },
  {
    _id: "o707", tenant_id: "t01", state_code: "PAID",
    amount_vnd: NumberLong(250000),
    placed_at: ISODate("2026-10-07T08:00:00Z"),
    buyer_doc: { city_name: "Đà Nẵng" },
    order_lines: [{ sku: "B", qty: 2 }]
  }
]);

orders.createIndex({
  tenant_id: 1,
  state_code: 1,
  placed_at: -1,
  _id: -1
});
~~~

Do not rerun `insertMany` when these IDs already exist; MongoDB will return a duplicate key error. The aggregation commands below are read-only, so they can be rerun repeatedly if there are no concurrent writers. For examples that write extra data in the testing section, use only dedicated fixture IDs.

### 2.2. Baseline numbers

| Scope | Order count | Total amount (VND) |
| --- | ---: | ---: |
| t01, PAID | 4 | 1,250,000 |
| t01, NEW | 1 | 100,000 |
| t01, CANCELLED | 1 | 80,000 |
| t01, all states | 6 | 1,430,000 |
| t02, PAID | 1 | 900,000 |

For t01 and state PAID:

\[
120000 + 350000 + 530000 + 250000 = 1250000
\]

The figure **1,250,000** is the expected value to catch queries that forget to filter tenant, mappers that extract the wrong field, or additions over mismatched types.

### 2.3. Reference BSON pipeline

Before writing Java, run the equivalent pipeline in `mongosh`:

~~~javascript
orders.aggregate([
  { $match: { tenant_id: "t01" } },
  {
    $group: {
      _id: "$state_code",
      orderCount: { $sum: 1 },
      grossVnd: { $sum: "$amount_vnd" }
    }
  },
  {
    $project: {
      _id: 0,
      state: "$_id",
      orderCount: 1,
      grossVnd: 1
    }
  },
  { $sort: { state: 1 } }
]);
~~~

Expect three states: CANCELLED, NEW, PAID; totals of **80,000**, **100,000**, and **1,250,000** VND respectively. `$sort` sits **after `$project`** and uses the alias `state`, not `state_code`, which was excluded.

## 3. Input entity: mapping Java properties to BSON

### 3.1. Domain model

Example classes in package `com.example.repositoryagg`:

~~~java
// OrderState.java
package com.example.repositoryagg;

public enum OrderState {
    NEW, PAID, CANCELLED
}
~~~

~~~java
// BuyerInfo.java
package com.example.repositoryagg;

import org.springframework.data.mongodb.core.mapping.Field;

public class BuyerInfo {
    @Field("city_name")
    private String city;

    protected BuyerInfo() { }

    public String getCity() { return city; }
}
~~~

~~~java
// OrderLine.java
package com.example.repositoryagg;

import org.springframework.data.mongodb.core.mapping.Field;

public class OrderLine {
    private String sku;

    @Field("qty")
    private int quantity;

    protected OrderLine() { }

    public String getSku() { return sku; }
    public int getQuantity() { return quantity; }
}
~~~

~~~java
// OrderDocument.java
package com.example.repositoryagg;

import java.time.Instant;
import java.util.List;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.mapping.MongoId;

@Document(collection = "orders_repository_agg_demo_003")
public class OrderDocument {
    @MongoId(FieldType.STRING)
    private String id;

    @Field("tenant_id")
    private String tenantId;

    @Field("state_code")
    private OrderState state;

    @Field("amount_vnd")
    private long amountVnd;

    @Field("placed_at")
    private Instant placedAt;

    @Field("buyer_doc")
    private BuyerInfo buyer;

    @Field("order_lines")
    private List<OrderLine> lines;

    protected OrderDocument() { }

    public String getId() { return id; }
    public String getTenantId() { return tenantId; }
    public OrderState getState() { return state; }
    public long getAmountVnd() { return amountVnd; }
    public Instant getPlacedAt() { return placedAt; }
    public BuyerInfo getBuyer() { return buyer; }
    public List<OrderLine> getLines() { return lines; }
}
~~~

| Java Property | Actual BSON Name |
| --- | --- |
| `id` | `_id` |
| `tenantId` | `tenant_id` |
| `state` | `state_code` |
| `amountVnd` | `amount_vnd` |
| `placedAt` | `placed_at` |
| `buyer.city` | `buyer_doc.city_name` |
| `lines.quantity` | `order_lines.qty` |

`@MongoId(FieldType.STRING)` keeps `_id` as a BSON string, consistent with the fixture. In repository `@Aggregation`, the pipeline is mapped based on the **repository's domain type** (`OrderDocument`) to resolve metadata such as `@Field` when the framework processes field references.

**Convention:** When writing a repository pipeline on this entity, prefer **Java property paths** such as `tenantId`, `state`, `amountVnd` in expressions where Spring Data supports mapping. In `mongosh` or the raw driver, use **BSON names**.

### 3.2. Do not confuse the input entity and output DTO

The repository uses `OrderDocument` to know the collection and input metadata, but the `$group` result **is no longer an OrderDocument**:

~~~javascript
{
  _id: "PAID",
  orderCount: 4,
  grossVnd: 1250000
}
~~~

`_id` is now the **group key** (state), not an order ID. Returning this document into `OrderDocument` merely because the repository uses `OrderDocument` creates an unsuitable mapping, easily yielding objects with missing fields or wrong semantics.

## 4. `@Aggregation` on a repository

### 4.1. Annotation and parameters

Spring Data MongoDB provides:

~~~java
import org.springframework.data.mongodb.repository.Aggregation;
~~~

You can declare a single stage:

~~~java
@Aggregation("{ '$group': { '_id': '$state', 'orders': { '$sum': 1 } } }")
List<StateCount> countByState();
~~~

or an array of stages:

~~~java
@Aggregation(pipeline = {
    "{ '$match': { 'tenantId': ?0 } }",
    "{ '$group': { '_id': '$state', 'orders': { '$sum': 1 } } }"
})
List<StateCount> countByStateForTenant(String tenantId);
~~~

`?0` is the **first** parameter placeholder, `?1` is the second parameter. SpEL `?#{...}` can be used when needed, but never concatenate JSON directly from user text.

For `@Aggregation`, the **method name does not need to be parsed as a derived query**: the annotation pipeline itself defines the operation. The method still belongs to the `OrderDocument` repository, so Spring Data has the input domain type information.

### 4.2. Reading the pipeline flow

~~~text
OrderRepository (@Aggregation)
    |
    |  JSON pipeline declared in annotation
    v
Spring Data: bind parameters, map @Field
    |
    v
MongoDB: $match -> $group -> $project -> $sort
    |
    v
BSON document after final stage
    |
    v
DTO | scalar | List | Slice | Stream | AggregationResults
~~~

**The deciding factor is the output shape.** When the return type changes from `StateSummary` to `Long`, recheck the final pipeline rather than only changing the Java signature.

## 5. Returning a DTO/record for aggregation reports

### 5.1. Declaring the output record

~~~java
// StateSummary.java
package com.example.repositoryagg;

public record StateSummary(
    String state,
    long orderCount,
    long grossVnd
) {
}
~~~

Record component names should **match output BSON aliases**; constructor parameters must have compatible types. Java records are supported by Spring Data in class-based mapping when using compatible versions.

### 5.2. Repository returning `List<StateSummary>`

~~~java
// OrderRepository.java
package com.example.repositoryagg;

import java.util.List;
import org.springframework.data.mongodb.repository.Aggregation;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface OrderRepository
        extends MongoRepository<OrderDocument, String> {

    @Aggregation(pipeline = {
        "{ '$match': { 'tenantId': ?0 } }",
        "{ '$group': { " +
            "'_id': '$state', " +
            "'orderCount': { '$sum': 1 }, " +
            "'grossVnd': { '$sum': '$amountVnd' } " +
        "} }",
        "{ '$project': { " +
            "'_id': 0, " +
            "'state': '$_id', " +
            "'orderCount': 1, " +
            "'grossVnd': 1 " +
        "} }",
        "{ '$sort': { 'state': 1 } }"
    })
    List<StateSummary> summarizeByState(String tenantId);
}
~~~

The Java code above uses concatenation of **constant string literals** to keep the code readable on the page; the compiler joins them into individual JSON stage strings before Spring Data parses them. This is not concatenating user input into JSON. In real code, you can write each stage on a single line or use text blocks/full JSON strings for simplicity.

Calling it:

~~~java
List<StateSummary> summaries =
    repository.summarizeByState("t01");

// By $sort state ASC:
// CANCELLED: orderCount=1, grossVnd=80000
// NEW:       orderCount=1, grossVnd=100000
// PAID:      orderCount=4, grossVnd=1250000
~~~

### 5.3. Why is `$project` needed after `$group`?

If the pipeline stops at:

~~~javascript
{
  $group: {
    _id: "$state_code",
    orderCount: { $sum: 1 },
    grossVnd: { $sum: "$amount_vnd" }
  }
}
~~~

the result has `_id`, `orderCount`, and `grossVnd` — **no `state` field**. Record `StateSummary(String state, ...)` will miss its required value unless special alias mapping is configured.

The stage:

~~~javascript
{
  $project: {
    _id: 0,
    state: "$_id",
    orderCount: 1,
    grossVnd: 1
  }
}
~~~

explicitly creates `state`, matching the record component name. Excluding `_id` also avoids ambiguity between the group key and the original ID.

### 5.4. When you want to keep the group's `_id`

Spring Data can map `_id` onto a property annotated with `@Id` in a DTO/class-based projection:

~~~java
// Example DTO class, if intentionally keeping _id as the group key:
public class StateGroup {
    @org.springframework.data.annotation.Id
    private String state;
    private long orderCount;
    private long grossVnd;

    protected StateGroup() { }

    public String getState() { return state; }
    public long getOrderCount() { return orderCount; }
    public long getGrossVnd() { return grossVnd; }
}
~~~

Even so, for read DTO APIs, **creating an explicit `state` alias** via `$project` is usually easier to understand. If the client expects an output named `groupKey`, create `groupKey` explicitly; do not let `_id` mapping carry two different meanings in the codebase.

### 5.5. DTO class vs. record

A traditional DTO class is also valid if it has appropriate constructors/getters and metadata:

~~~java
public class StateSummaryDto {
    private final String state;
    private final long orderCount;
    private final long grossVnd;

    public StateSummaryDto(
            String state, long orderCount, long grossVnd) {
        this.state = state;
        this.orderCount = orderCount;
        this.grossVnd = grossVnd;
    }

    public String getState() { return state; }
    public long getOrderCount() { return orderCount; }
    public long getGrossVnd() { return grossVnd; }
}
~~~

For non-record classes, the Java compiler/build must retain constructor parameter names or use appropriate mapping configuration (`@PersistenceCreator` if there are multiple constructors). If the output BSON is missing a field or has the wrong type, mapping errors can happen right at the constructor or silently turn into unintended defaults. That is why you must test **every field's value**, not just the list size.

## 6. Interface projections from aggregation documents

You do not have to create concrete classes for every read model. Repository aggregations can return **interface-based projections** using proxies that read fields from the output `Document`.

~~~java
// StateSummaryView.java
package com.example.repositoryagg;

public interface StateSummaryView {
    String getState();
    long getOrderCount();
    long getGrossVnd();
}
~~~

Declare a method with the same pipeline but a different return type:

~~~java
@Aggregation(pipeline = {
    "{ '$match': { 'tenantId': ?0 } }",
    "{ '$group': { '_id': '$state', " +
        "'orderCount': { '$sum': 1 }, " +
        "'grossVnd': { '$sum': '$amountVnd' } } }",
    "{ '$project': { '_id': 0, 'state': '$_id', " +
        "'orderCount': 1, 'grossVnd': 1 } }"
})
List<StateSummaryView> summarizeViews(String tenantId);
~~~

Add this method to `OrderRepository` in the example. Spring Data can create a projection proxy reading `state`, `orderCount`, and `grossVnd` from the result documents.

### 6.1. Choosing between DTO and interface projection

| Criterion | Record / class DTO | Interface projection |
| --- | --- | --- |
| Mechanism | Maps document into an object | Proxy accessing result fields |
| Field contract | Explicit constructor/component names and types | `get...()` getters matching fields |
| Immutability | Immutable record | Interface exposes getters, not mutable data |
| Debugging | Concrete object, easy to log/toString | Proxy requires understanding backing document |
| When to use | Stable read model, shared across business layers | Small report, only simple getters needed |

A projection only accesses **fields already present in the output**. If the pipeline creates `revenue` while the interface declares `getGrossVnd()`, Spring Data does not automatically infer that the two names share the same business meaning.

### 6.2. Do not confuse with server-side optimization

Having return type `StateSummaryView` **does not automatically ensure** the pipeline only loads needed fields in earlier stages. The pipeline itself controls `$project`, `$group`, and processed data size. Inspect the BSON command and execution plan instead of inferring from Java getters.

## 7. Scalar: mapping a `Document` into `Long`, `String`

### 7.1. Pipeline returning a single value

KPI "total PAID revenue of t01":

~~~javascript
orders.aggregate([
  { $match: { tenant_id: "t01", state_code: "PAID" } },
  {
    $group: {
      _id: null,
      total: { $sum: "$amount_vnd" }
    }
  },
  { $project: { _id: 0, total: 1 } }
]);
// [{ total: 1250000 }]
~~~

In Java:

~~~java
@Aggregation(pipeline = {
    "{ '$match': { 'tenantId': ?0, 'state': ?1 } }",
    "{ '$group': { '_id': null, " +
        "'total': { '$sum': '$amountVnd' } } }",
    "{ '$project': { '_id': 0, 'total': 1 } }"
})
Long totalAmountForState(String tenantId, OrderState state);
~~~

Call:

~~~java
Long total = repository.totalAmountForState(
    "t01", OrderState.PAID
);
// total == 1_250_000L on the baseline fixture.
~~~

In this case, `@Aggregation` returns **one document containing one value**, and Spring Data MongoDB supports extracting that value directly into a **simple type** like `Long`.

### 7.2. Spring Data's simple-type extraction rules

For a **single result document**, Spring Data MongoDB checks possibilities in order:

1. The document has only **one entry**: return that entry.
2. The document has **two entries**, one of which is `_id`: return the other entry.
3. If there are multiple entries: find the **first value assignable/convertible to the return type**.
4. If no suitable value exists: **throw an exception**.

Illustration:

| Result BSON document | Return type | Assessment |
| --- | --- | --- |
| `{total:1250000}` | `Long` | Clear, recommended |
| `{_id:null,total:1250000}` | `Long` | Can extract `total` via the two-entry rule |
| `{total:1250000,count:4}` | `Long` | **Ambiguous**, more than one number |
| `{total:"not-a-number"}` | `Long` | Wrong type, may fail conversion |
| `{_id:"PAID"}` | `String` | One entry, receives `"PAID"` |

**Design rule:** When you want a scalar, **output only the exact single field you intend to retrieve**, ideally via `$project` with `_id:0`. Do not rely on "first assignable value" in a multi-field document because selection order and meaning can break easily when the pipeline changes.

### 7.3. Do not treat a scalar and a one-row summary as the same type

~~~java
public record TotalAmount(Long total) { }

@Aggregation(pipeline = {
    "{ '$match': { 'tenantId': ?0, 'state': ?1 } }",
    "{ '$group': { '_id': null, " +
        "'total': { '$sum': '$amountVnd' } } }",
    "{ '$project': { '_id': 0, 'total': 1 } }"
})
TotalAmount totalAmountWrapped(
    String tenantId, OrderState state
);
~~~

`Long` returns **the number** directly; `TotalAmount` preserves **an object with a named field**. A wrapper DTO is usually easier to extend later with currency, order count, or time window, and the JSON API conveys clearer meaning too.

### 7.4. Empty results: `$group` does not automatically return 0

Suppose tenant `t99` has no PAID orders. The pipeline:

~~~javascript
[
  { $match: { tenant_id: "t99", state_code: "PAID" } },
  { $group: { _id: null, total: { $sum: "$amount_vnd" } } }
]
~~~

does not automatically synthesize a `{total:0}` document for an empty input set; the result is typically **no document**. A single-result repository method may return `null` or a wrapper depending on signature and version; **do not assume 0 is always returned**.

Safe design:

~~~java
public long totalPaidOrZero(
        String tenantId, OrderRepository repository) {
    Long value = repository.totalAmountForState(
        tenantId, OrderState.PAID
    );
    return value != null ? value : 0L;
}
~~~

If using `Optional<Long>` on a repository method supported by your Spring Data version, you can use `orElse(0L)`. For aggregations that may return multiple rows, do not apply a zero fallback to **results lost due to errors** — database/converter errors must still be surfaced separately.

### 7.5. `BigDecimal` and numeric types in MongoDB

The fixture uses `NumberLong(...)` and `$sum`. Depending on input numeric types, aggregation can return `Int32`, `Int64`, `Double`, or `Decimal128` per MongoDB and converter rules. `Long` fits **whole currency amounts** within 64-bit integer limits.

If you need fractional amounts, exchange rates, or exact accounting, consider `Decimal128`/`BigDecimal` and explicit rounding rules. Do not switch the return type to `Double` just to "make the mapping error go away" without considering precision loss.

## 8. `List<String>`, `List<Long>`: multiple scalars from multiple documents

If each output document represents **one status**, you can output a single field and return `List<String>`:

~~~java
@Aggregation(pipeline = {
    "{ '$match': { 'tenantId': ?0 } }",
    "{ '$group': { '_id': '$state' } }",
    "{ '$project': { '_id': 0, 'state': '$_id' } }",
    "{ '$sort': { 'state': 1 } }"
})
List<String> findDistinctStateNames(String tenantId);
~~~

Result for `t01`:

~~~java
List<String> states =
    repository.findDistinctStateNames("t01");
// ["CANCELLED", "NEW", "PAID"]
~~~

This does **not** collapse three documents into **one** `String`; the mapper extracts one value from **each** result document and collects them into a list.

### 8.1. Avoid an ambiguous list of numbers

For example, a `List<Long>` containing only each group's `grossVnd` without the `state` field loses which status each number belongs to.

~~~javascript
[
  { grossVnd: 80000 },
  { grossVnd: 100000 },
  { grossVnd: 1250000 }
]
~~~

If the UI must label them, returning `List<StateSummary>` is better. `List<Long>` makes sense when values are already identified by another fixed ordering, or the client only needs a numeric sequence with a stable ordering contract.

### 8.2. Multiple result documents with a singular return type

If a `$group` pipeline by state returns **three documents** while the method declares:

~~~java
StateSummary oneSummary(String tenantId);
~~~

there is no clear definition of which document should be chosen. Singular Spring Data query methods normally require at most one result or explicit limiting rules; exceeding one result can throw a result-size error depending on execution mechanics. Do not rely on "picking the first row arbitrarily."

If you genuinely want the top group, put `$sort` then `$limit:1` **in the pipeline** and verify ordering; if you want all groups, return `List<StateSummary>`.

## 9. `AggregationResults<T>`: keeping mapped data and raw response

Sometimes the application needs **both mapped results and the raw response**, or needs to debug converters without losing BSON details.

Spring Data MongoDB supports:

~~~java
import org.springframework.data.mongodb.core.aggregation.AggregationResults;
~~~

### 9.1. Repository returning the generic wrapper

~~~java
// TotalAmount.java
package com.example.repositoryagg;

public record TotalAmount(Long total) {
}
~~~

In `OrderRepository`:

~~~java
@Aggregation(pipeline = {
    "{ '$match': { 'tenantId': ?0, 'state': ?1 } }",
    "{ '$group': { '_id': null, " +
        "'total': { '$sum': '$amountVnd' } } }",
    "{ '$project': { '_id': 0, 'total': 1 } }"
})
AggregationResults<TotalAmount> totalAmountRaw(
    String tenantId, OrderState state
);
~~~

Call:

~~~java
AggregationResults<TotalAmount> results =
    repository.totalAmountRaw("t01", OrderState.PAID);

List<TotalAmount> mapped = results.getMappedResults();
TotalAmount unique = results.getUniqueMappedResult();
org.bson.Document response = results.getRawResults();

// mapped.size() == 1.
// unique.total() == 1_250_000L on the baseline fixture.
~~~

`AggregationResults<T>` has these main APIs:

| API | Meaning |
| --- | --- |
| `getMappedResults()` | List of `T` mapped by Spring Data; empty if none |
| `getUniqueMappedResult()` | Returns `T` when there is exactly 1; `null` if none; throws if more than 1 |
| `getRawResults()` | Raw response `Document` from server/driver |
| `getServerUsed()` | Server address information used when available; may be null |
| `iterator()` | Iterates mapped results; the wrapper implements `Iterable<T>` |

### 9.2. `getUniqueMappedResult()` does not mean "get first row"

Suppose a pipeline grouped by status produces three rows. If code calls:

~~~java
var unique = results.getUniqueMappedResult();
~~~

that **violates the contract**: `getUniqueMappedResult()` requires **0 or 1** result and throws `IllegalArgumentException` when the list has more than one. When you need one of the groups, use a sufficiently narrow filter or `$sort` + `$limit` with a clear goal.

### 9.3. When to use `getRawResults()`?

Raw results are useful when:

- Inspecting actual BSON types (`Long`/`Double`/`Decimal128`).
- Cross-checking output fields when a DTO has null or mismatched names.
- Inspecting response metadata from the driver/server as exposed by the API.
- Temporarily diagnosing why an aggregation fails to map cleanly into a record.

However, `getRawResults()` **should not be returned directly to public APIs**: it may contain internal metadata, BSON details, or data needing access control. Raw response structure can vary by server/driver and is not a stable business contract.

### 9.4. `AggregationResults<Document>` before defining a DTO

~~~java
@Aggregation(pipeline = {
    "{ '$match': { 'tenantId': ?0 } }",
    "{ '$group': { '_id': '$state', " +
        "'orderCount': { '$sum': 1 } } }"
})
AggregationResults<org.bson.Document> countRaw(String tenantId);
~~~

The `Document` generic wrapper lets you inspect `_id` and `orderCount` keys directly. This is good for prototyping a pipeline or building a very low-level adapter, but once output stabilizes, switch to a meaningful DTO/record.

### 9.5. Comparing the wrapper with the template API

`MongoTemplate.aggregate(...)` commonly returns `AggregationResults<T>` directly:

~~~java
AggregationResults<StateSummary> results =
    template.aggregate(
        aggregation,
        "orders_repository_agg_demo_003",
        StateSummary.class
    );
~~~

`@Aggregation` on a repository can **unwrap a scalar or list** to keep callers simple, while also supporting returning `AggregationResults<T>` directly when raw info is needed. Both execute MongoDB aggregation underneath; they differ in where the pipeline is declared and how the return-type contract is chosen.

## 10. Limits of `Sort`, `Pageable`, `Slice`, and `Page`

### 10.1. `Sort` is appended to the end of the pipeline

A repository method can accept a `Sort` parameter:

~~~java
@Aggregation(pipeline = {
    "{ '$match': { 'tenantId': ?0 } }",
    "{ '$group': { '_id': '$state', " +
        "'orderCount': { '$sum': 1 }, " +
        "'grossVnd': { '$sum': '$amountVnd' } } }",
    "{ '$project': { '_id': 0, 'state': '$_id', " +
        "'orderCount': 1, 'grossVnd': 1 } }"
})
List<StateSummary> summarizeSorted(
    String tenantId,
    org.springframework.data.domain.Sort sort
);
~~~

Call:

~~~java
List<StateSummary> topFirst = repository.summarizeSorted(
    "t01",
    Sort.by(Sort.Order.desc("grossVnd"))
);
// PAID, NEW, CANCELLED.
~~~

Spring Data appends `$sort` according to the parameter at the **end of the annotation pipeline**. Crucially: `Sort` is mapped using the **return type** (`StateSummary`), not just the input `OrderDocument`.

### 10.2. Output aliases and `@Id` on the return type

The Spring Data documentation notes an example where if the return DTO has a `lastname` field annotated with `@Id`, `Sort.by("lastname")` may be translated into `$sort` on `_id` of the grouped result. Therefore:

- If the output created alias `grossVnd`, sort by `grossVnd`.
- If you want to sort by `state`, ensure the output actually contains `state`.
- If a DTO marks `@Id` on a field receiving group `_id`, verify the mapped BSON name before relying on sorting.

Do not write `Sort.by("amountVnd")` simply because the source entity has that property if the output after `$group` only has `grossVnd`.

### 10.3. `Pageable` adds sort, skip, and limit to the end of the pipeline

~~~java
@Aggregation(pipeline = {
    "{ '$match': { 'tenantId': ?0 } }",
    "{ '$group': { '_id': '$state', " +
        "'orderCount': { '$sum': 1 }, " +
        "'grossVnd': { '$sum': '$amountVnd' } } }",
    "{ '$project': { '_id': 0, 'state': '$_id', " +
        "'orderCount': 1, 'grossVnd': 1 } }"
})
org.springframework.data.domain.Slice<StateSummary> summarizeSlice(
    String tenantId,
    org.springframework.data.domain.Pageable pageable
);
~~~

Call:

~~~java
var slice = repository.summarizeSlice(
    "t01",
    org.springframework.data.domain.PageRequest.of(
        0, 2,
        Sort.by(Sort.Order.asc("state"))
    )
);

// The first page has at most 2 groups; slice.hasNext() indicates whether more groups remain.
~~~

`Pageable` applies to the **output after the declared stages**, so if the pipeline has already grouped by state, it paginates **the groups**, not the original orders. If you want to "read only the first 100 orders and then group," you must intentionally place `$limit` **before `$group`** — and accept that the statistics reflect only that subset.

### 10.4. `@Aggregation` does not support `Page<T>`

**Do not declare**:

~~~java
// NOT supported for repository @Aggregation:
// @Aggregation(...)
// Page<StateSummary> summarizePage(
//     String tenantId, Pageable pageable);
~~~

The Spring Data MongoDB documentation specifies: repository methods using `@Aggregation` **do not support the `Page` return type**. You can accept `Pageable` and pick `Slice<T>`, `List<T>`, or another supported type.

Why? `Page` requires **`totalElements` / `totalPages`**; for aggregations with `$group`, `$unwind`, `$facet`, stages reshape the output and make an auto-generated count query non-trivial. If the UI truly needs the total number of **groups** after the pipeline, design a separate pipeline to count groups or use `$facet`/`MongoTemplate`, and build a page DTO in the service layer per your contract.

### 10.5. Do not equate order count with group count

`t01` has **6 orders**, whereas the `$group` by state pipeline returns **3 groups**. If the user asks for "page 1 / total 3 statuses," `totalElements` must be 3 groups, not 6 orders. This is one reason to clarify the **unit being paginated** before thinking about total metadata.

## 11. `Stream<T>`: consuming results via a cursor

A repository aggregation can return `Stream<StateSummary>`:

~~~java
@Aggregation(pipeline = {
    "{ '$match': { 'tenantId': ?0 } }",
    "{ '$project': { '_id': 0, 'state': 1, " +
        "'amountVnd': 1 } }"
})
java.util.stream.Stream<org.bson.Document> streamProjected(
    String tenantId
);
~~~

To process:

~~~java
try (var stream = repository.streamProjected("t01")) {
    stream.forEach(row -> {
        // Read each result document; avoid holding the entire set in a large List.
        System.out.println(row);
    });
}
~~~

**Always close the Stream** after reading: a stream can be backed by a server-side MongoDB cursor, and leaving it open wastes connection/cursor resources. If there are really only three groups, `List<StateSummary>` is simpler; streams are typically useful when a pipeline returns a large number of results.

Do not call `stream.toList()` and claim memory was saved: that materializes the entire output anyway. When a stream can be long-lived, enforce processing rate limits, timeouts, retry/checkpointing, and appropriate logging.

### 11.1. Stream does not mean `$match`/`$group` are free

The pipeline still has to execute its stages on the server. `$group` or `$sort` can be blocking stages and consume resources before emitting results. A stream only controls **how the client consumes output**, without automatically optimizing server work.

## 12. Reactive repositories and return types

`ReactiveMongoRepository` supports `@Aggregation` with reactive types:

~~~java
package com.example.repositoryagg;

import org.springframework.data.mongodb.repository.Aggregation;
import org.springframework.data.mongodb.repository.ReactiveMongoRepository;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public interface ReactiveOrderRepository
        extends ReactiveMongoRepository<OrderDocument, String> {

    @Aggregation(pipeline = {
        "{ '$match': { 'tenantId': ?0 } }",
        "{ '$group': { '_id': '$state', " +
            "'orderCount': { '$sum': 1 }, " +
            "'grossVnd': { '$sum': '$amountVnd' } } }",
        "{ '$project': { '_id': 0, 'state': '$_id', " +
            "'orderCount': 1, 'grossVnd': 1 } }"
    })
    Flux<StateSummary> summarizeByState(String tenantId);

    @Aggregation(pipeline = {
        "{ '$match': { 'tenantId': ?0, 'state': ?1 } }",
        "{ '$group': { '_id': null, " +
            "'total': { '$sum': '$amountVnd' } } }",
        "{ '$project': { '_id': 0, 'total': 1 } }"
    })
    Mono<Long> totalAmountForState(
        String tenantId, OrderState state
    );
}
~~~

`Flux<StateSummary>` emits multiple groups; `Mono<Long>` emits at most one scalar. When there are no results (e.g., tenant t99 has no orders), `Mono` can complete empty:

~~~java
Mono<Long> total = reactiveRepository
    .totalAmountForState("t99", OrderState.PAID)
    .defaultIfEmpty(0L);
~~~

A publisher only executes when subscribed. Never call `block()` on a WebFlux event loop. Reactive execution does not alter the **BSON shape** of `$group`/`$project`, does not automatically add a total count, and does not make large sorts/groups cheaper.

### 12.1. `Mono<Page<T>>` is not supported in reactive repositories

If you need reactive pagination, use `Pageable` to limit `Flux` results where supported by the framework, or design custom windowing/cursors. Do not declare `Mono<Page<T>>` on an annotation expecting the framework to run a count aggregation underneath.

## 13. `@Meta`: resource options for aggregation

Large aggregations may need a time limit, a comment for tracing, or disk use allowed:

~~~java
import org.springframework.data.mongodb.repository.Meta;

@Meta(allowDiskUse = "true", maxExecutionTimeMs = 10_000)
@Aggregation(pipeline = {
    "{ '$match': { 'tenantId': ?0 } }",
    "{ '$group': { '_id': '$state', " +
        "'orderCount': { '$sum': 1 } } }"
})
List<org.bson.Document> countWithOptions(String tenantId);
~~~

`allowDiskUse` and `maxExecutionTimeMs` are **options**; they do not dictate DTO/scalar shape. Only enable `allowDiskUse` when the workload genuinely requires it and resources have been evaluated; do not treat disk spill as a fix for wrong indexes, unnecessary pipelines, or inputs missing a tenant filter.

`@Meta` also has `comment` to attach diagnostic labels. Never put PII, tokens, or sensitive data into comments/logs.

## 14. When to switch to `MongoTemplate.aggregate`?

`@Aggregation` is great for relatively stable pipelines with rarely changing criteria and clear return types. If the pipeline is long, has many conditional branches, needs a type-safe DSL, complex logic, or fine-grained control over other options, use `MongoTemplate`/`MongoOperations`.

~~~java
import java.util.List;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.aggregation.Aggregation;
import org.springframework.data.mongodb.core.aggregation.AggregationResults;
import org.springframework.data.mongodb.core.query.Criteria;

// template is injected in the service/fragment:
Aggregation pipeline = Aggregation.newAggregation(
    OrderDocument.class,
    Aggregation.match(
        Criteria.where("tenantId").is("t01")
            .and("state").is(OrderState.PAID)
    ),
    Aggregation.group()
        .sum("amountVnd").as("total"),
    Aggregation.project("total")
        .andExclude("_id")
);

AggregationResults<TotalAmount> results =
    template.aggregate(pipeline, TotalAmount.class);

TotalAmount total = results.getUniqueMappedResult();
~~~

When using typed aggregation as above, input entity `OrderDocument` lets Spring Data map `tenantId`/`state`/`amountVnd` to BSON according to `@Field` in supported DSL operations. `TotalAmount.class` is the **output type**.

### 14.1. Requirements better expressed with the template

- Building dynamic `Criteria` from optional business filters.
- Using `AggregationOptions.strictMapping()` when strict input property checking is desired.
- Building several similar pipelines with reusable stages.
- Running `$facet` to fetch data and count in a report with well-defined semantics.
- Customizing `AggregationOperation` and inspecting the BSON pipeline.
- Using `aggregateStream` for large outputs in suitable workflows.

A custom repository fragment can use `MongoOperations` to still provide a stable repository interface to services.

### 14.2. Do not confuse template `AggregationResults` with repository `Page`

`AggregationResults<T>` is **not** `Page<T>`. It contains mapped results and raw response, **not** `totalElements` or `totalPages`. If the UI wants a real `Page`, the service must provide a count in the **exact output unit** and compute metadata/consistency explicitly.

## 15. `@Field` mapping, aliases, and DTOs: subtle bugs

### 15.1. Input mapping and output aliases are two separate things

Entity:

~~~java
@Field("amount_vnd")
private long amountVnd;
~~~

Pipeline:

~~~javascript
{ $group: { _id: null, total: { $sum: "$amountVnd" } } }
~~~

When input reference mapping applies, Spring Data uses BSON field `amount_vnd`. However, `total` is an **aggregation-created alias**, not automatically renamed to `amount_vnd`.

Output DTO:

~~~java
public record TotalAmount(Long total) { }
~~~

reads the `total` alias. Do not write `TotalAmount(Long amountVnd)` expecting the mapper to guess `amountVnd` means the same as `total`.

### 15.2. Aliases at the end of the pipeline matter more than original field names

Pipeline:

~~~javascript
[
  { $group: { _id: "$state_code", grossVnd: { $sum: "$amount_vnd" } } },
  { $project: { _id: 0, state: "$_id", grossVnd: 1 } }
]
~~~

The output has only `state` and `grossVnd`. Neither `state_code` nor `amount_vnd` remains as a top-level field. A `Sort` parameter on the repository must speak in terms of the **output type**, such as `Sort.by("grossVnd")`.

### 15.3. Using raw `Document` to locate where a bug lies

When a record receives nulls:

1. Temporarily have the method return `AggregationResults<org.bson.Document>`.
2. Check whether `getMappedResults()` has the right fields/BSON types.
3. Compare the `mongosh` pipeline with the actual command sent by the driver.
4. If the BSON is right, fix the DTO constructor/aliases/converters.
5. If the BSON is wrong, fix `$match`/`$group`/`$project` and property mapping.

Do not fix it by switching everything to `Map<String,Object>` or enabling loose conversions to hide bugs. A good read DTO should have a clear field contract.

### 15.4. `$group`'s `_id` differs from the order's `_id`

Before `$group`:

~~~javascript
{ _id: "o701", state_code: "PAID", amount_vnd: 120000 }
~~~

After `$group` by status:

~~~javascript
{ _id: "PAID", grossVnd: 1250000 }
~~~

From here on, `_id` no longer means order ID. If a DTO has `String id` without caring about semantics, readers of the code are easily misled. Use an alias like `state` or `groupKey` to make the meaning clear.

### 15.5. Numeric overflow and mapping types

Large sums can exceed `int` limits; always pick an appropriate result type, at least `long/Long` if data consists of 64-bit integers. With `$avg`, the output typically has a floating-point/decimal type depending on data; do not declare `Long` if business logic requires keeping decimal places.

If using `BigDecimal`, verify the converter with BSON `Decimal128` and input precision; do not trust financial calculations just because one small test produces the right number.

## 16. Security, authorization, and aggregation cost

`@Aggregation` does not automatically add tenant/authorization filters. If `tenantId` is omitted from `$match`:

~~~javascript
[
  { $match: { state_code: "PAID" } },
  { $group: { _id: null, total: { $sum: "$amount_vnd" } } }
]
~~~

the total on the fixture becomes **2,150,000 VND** because it includes `o705` belonging to t02:

\[
1250000 + 900000 = 2150000
\]

A wrong aggregate total is not just an arithmetic bug—it is a **cross-tenant information leak**.

### 16.1. Put the tenant filter in every pipeline

Repository method:

~~~java
@Aggregation(pipeline = {
    "{ '$match': { 'tenantId': ?0, 'state': ?1 } }",
    "{ '$group': { '_id': null, " +
        "'total': { '$sum': '$amountVnd' } } }"
})
Long totalForTenantAndState(
    String authorizedTenantId,
    OrderState state
);
~~~

`authorizedTenantId` must be resolved in the service layer from the security context; never trust an arbitrary tenant string sent by the client.

### 16.2. Limiting workload

- Place selective `$match` early and inspect the query plan.
- Create indexes on **actual BSON fields**, such as `tenant_id` and `state_code`.
- Place `$limit`/`$sort` in the right positions without distorting aggregate results.
- Limit page size and avoid deep offsets on large outputs.
- Use `@Meta`/max execution time when appropriate; monitor p95/p99 and server resources.
- Never return raw `AggregationResults.getRawResults()` to public APIs or unredacted logs.

### 16.3. Notes on `$out` and `$merge` pipelines

Aggregation is not always read-only. `$out` and `$merge` can **write data** to a target collection. For pipelines with write stages, a `void` return type can be supported, but permissions, operational planning, and testing differ completely from DTO/scalar queries.

Do not put write stages in a public analytics repository just because the annotation accepts raw pipelines.

## 17. Integration testing against a real MongoDB

A mocked repository returning a `StateSummary` with expected values **does not prove**:

- `@Field("amount_vnd")` was applied in the pipeline.
- `_id` after `$group` was aliased to `state`.
- `Long` extracted `total` rather than accidentally extracting count.
- `AggregationResults<T>` actually holds mapped documents and the raw response.
- Other tenants were excluded from totals.
- `Slice` paginates by groups rather than by orders.

You need integration tests running against a dedicated test MongoDB, such as Testcontainers or a test-owned database.

### 17.1. Test matrix

| Test | Expectation |
| --- | --- |
| `summarizeByState("t01")` | 3 groups; PAID has 4 orders and 1,250,000 VND |
| `totalAmountForState("t01",PAID)` | `1_250_000L` |
| `totalAmountForState("t99",PAID)` | No result; service treats as 0 if contracted |
| `findDistinctStateNames("t01")` | 3 strings: CANCELLED, NEW, PAID |
| `totalAmountRaw` | `getMappedResults` has 1, `getUniqueMappedResult` accurate |
| `getUniqueMappedResult` on 3 groups | Throws multiple-result error instead of silently picking first |
| DTO record `StateSummary` | Fields `state`, `orderCount`, `grossVnd` match aliases |
| Interface projection | Getters match output BSON data |
| Sort on `grossVnd` | PAID comes first when sorted DESC |
| `Slice` size 2 | 2 groups in first window, `hasNext` flag accurate |
| Tenant t02 | Must not leak into t01's results |
| Scalar with multiple numeric fields | Recognized as ambiguous; fix `$project` to one field |
| Reactive `Mono<Long>` | Subscribes and receives right value; completes empty on no match |
| BSON numeric type | Verify Long/Decimal128 per actual model |

### 17.2. Integration test with test-owned data

The example below uses three dedicated test IDs: two PAID orders for the test tenant and one PAID order belonging to another tenant.

~~~java
package com.example.repositoryagg;

import static org.assertj.core.api.Assertions.assertThat;

import com.mongodb.client.model.Filters;
import java.util.List;
import org.bson.Document;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.data.mongodb.core.MongoTemplate;

@DataMongoTest
class RepositoryAggregationMappingTest {
    @Autowired MongoTemplate template;
    @Autowired OrderRepository repository;

    @Test
    void mapsDtoScalarAndRawResultWithTenantIsolation() {
        List<String> ids = List.of(
            "fixture-ra003-a",
            "fixture-ra003-b",
            "fixture-ra003-other"
        );

        var collection = template.getDb()
            .getCollection("orders_repository_agg_demo_003");

        collection.deleteMany(Filters.in("_id", ids));
        try {
            collection.insertMany(List.of(
                new Document("_id", ids.get(0))
                    .append("tenant_id", "fixture-ra003")
                    .append("state_code", "PAID")
                    .append("amount_vnd", 100000L),
                new Document("_id", ids.get(1))
                    .append("tenant_id", "fixture-ra003")
                    .append("state_code", "PAID")
                    .append("amount_vnd", 200000L),
                new Document("_id", ids.get(2))
                    .append("tenant_id", "other-fixture-ra003")
                    .append("state_code", "PAID")
                    .append("amount_vnd", 900000L)
            ));

            List<StateSummary> rows =
                repository.summarizeByState("fixture-ra003");
            assertThat(rows).hasSize(1);
            assertThat(rows.get(0).state()).isEqualTo("PAID");
            assertThat(rows.get(0).orderCount()).isEqualTo(2L);
            assertThat(rows.get(0).grossVnd()).isEqualTo(300000L);

            Long scalar = repository.totalAmountForState(
                "fixture-ra003", OrderState.PAID);
            assertThat(scalar).isEqualTo(300000L);

            var wrapped = repository.totalAmountRaw(
                "fixture-ra003", OrderState.PAID);
            assertThat(wrapped.getMappedResults()).hasSize(1);
            assertThat(wrapped.getUniqueMappedResult())
                .isNotNull();
            assertThat(wrapped.getUniqueMappedResult().total())
                .isEqualTo(300000L);
            assertThat(wrapped.getRawResults()).isNotNull();
        } finally {
            collection.deleteMany(Filters.in("_id", ids));
        }
    }
}
~~~

This test is **only suitable for an isolated test MongoDB**. It cleans up only the three fixture IDs, avoiding deleting non-test data. Class/package/mapping names must match the lesson's sections when placed into a real project; `@DataMongoTest` requires repositories/entities to be within the test configuration's component scan scope.

### 17.3. Testing empty results

~~~java
@Test
void emptyAggregationIsNotImplicitlyZero() {
    Long value = repository.totalAmountForState(
        "tenant-with-no-orders", OrderState.PAID
    );

    // For a $group query over an empty set, no summary document is produced.
    assertThat(value).isNull();
}
~~~

This snippet can be placed in the same `RepositoryAggregationMappingTest` class once `repository` is injected; ensure the test tenant has no matching data. In environments/code snippets using reactive types or `Optional`, adjust expectations to match the return type's contract.

### 17.4. Testing consistency between scalar and DTO

When two methods compute the same KPI under the **same conditions**:

~~~java
Long scalar = repository.totalAmountForState(
    "fixture-ra003", OrderState.PAID);
TotalAmount value = repository.totalAmountWrapped(
    "fixture-ra003", OrderState.PAID);

assertThat(value.total()).isEqualTo(scalar);
~~~

This test compares scalar and wrapper DTO mapping. It does not guarantee the two queries share a snapshot if concurrent writers exist; run in an isolated test fixture or enforce explicit consistency requirements.

## 18. Common troubleshooting

| Symptom | Possible cause | How to fix |
| --- | --- | --- |
| DTO field `state` is null | `$group` only returns `_id`, missing projected alias | `$project` from `_id` to `state` |
| DTO `grossVnd=0` while BSON has a value | Wrong alias, incompatible numeric type, or constructor mismatch | Inspect `AggregationResults<Document>` and DTO mapping |
| Scalar returns wrong number | Output has multiple numeric fields, mapper picks another value | Project exactly one field, exclude `_id` |
| Scalar is null when no orders match | `$group` on empty input emits no document | Use `Long`/`Optional` and default to 0 in service |
| Returning single `StateSummary` when pipeline yields 3 groups | One-to-many cardinality mismatch | Return `List/Flux` or add intentional `$sort` + `$limit` |
| `getUniqueMappedResult()` throws error | More than one mapped result exists | Use `getMappedResults()` or limit pipeline |
| `Sort.by("amountVnd")` after group misbehaves | Sort mapping uses output, source field is gone | Use `grossVnd` or actual DTO alias |
| `Page<StateSummary>` fails to work | `Page` is not supported for `@Aggregation` | Use `Slice` or build custom count with template |
| Page size 2 yields 2 **groups**, not 2 **orders** | `Pageable` is appended after `$group` | Clarify pagination before/after grouping |
| Missing filter includes other tenant's data, skewing totals | `$match` missing tenant | Bind tenant from security context |
| `@Field` does not take effect as expected | Raw BSON/field names or aliases not mapped from domain | Inspect input entity and executed BSON pipeline |
| Raw response contains confusing metadata | `getRawResults()` is the driver response, not a DTO | Do not return raw directly; read mapped results |
| Stream leaks resources | Unclosed `Stream`/server cursor | `try-with-resources` |
| Reactive returns no data | Publisher not subscribed | Compose `Flux/Mono` into chain/`StepVerifier` |
| Aggregation is slow despite returning 1 scalar | `$group`/`$sort` still process large dataset | Indexes, explain, filters, workload limits |
| Monetary amounts lose fractional precision | Using `double` for money or mismatched BSON type | `Decimal128`/`BigDecimal` or integers in minor units |

## 19. Return-type selection checklist

1. **Identify the final stage's output**: one document or many, which fields, and which BSON types?
2. **Provide input metadata to the repository** via `OrderDocument` and consistent `@Field` annotations.
3. **Return a DTO/record** when the output has multiple meaningful fields (`state`, `count`, `sum`).
4. **Use an interface projection** when only simple getters over output documents are needed.
5. **Return scalar `Long`/`String`** when each output document has **only one field to extract**.
6. **Use `List<Scalar>`** when the pipeline produces multiple output documents, each representing a single value.
7. **Use `AggregationResults<T>`** when both mapped results and raw responses are needed for diagnostics/verification.
8. **Never use `getUniqueMappedResult()`** for a pipeline that can produce more than one group.
9. **Handle empty results**; never assume totals are 0 when no input documents exist.
10. **Sort by output type and aliases**, especially after `$group`/`$project`.
11. **Use `Slice` instead of `Page`** on repository `@Aggregation`; design total counts yourself when required.
12. **Close `Stream`s**, and never materialize unbounded results onto the heap.
13. **Verify tenant, indexes, and resources**; do not assume aggregations are always read-only since `$out`/`$merge` can write.
14. **Run real-BSON integration tests** for DTOs, scalars, wrappers, aliases, null/missing fields, and numeric types.

## 20. Practice exercises

Each exercise below is based on the fixture in section 2, with no changes from other writers.

### Exercise 1 — Choosing a DTO type

A pipeline grouped by state produces `{state:"PAID",orderCount:4,grossVnd:1250000}`. Is returning `Long` appropriate?

**Answer:** No, if the application needs all three fields. Use the `StateSummary` record/class or an interface projection. `Long` is only appropriate when the pipeline projects the exact single value to extract.

### Exercise 2 — Group key `_id`

`$group` result:

~~~javascript
{ _id: "PAID", orderCount: 4, grossVnd: 1250000 }
~~~

Is `_id` the order's `o701` ID?

**Answer:** No. It is the **group key** `"PAID"`. Add `$project: {state:"$_id",_id:0,...}` so the DTO has a clear `state` field.

### Exercise 3 — Scalar total

For t01/PAID, what should `Long totalAmountForState(...)` return?

**Answer:** `1_250_000L`. The pipeline should end with `{ $project: { _id:0,total:1 } }` after `$group`.

### Exercise 4 — No orders

Tenant t99 has no PAID orders. Does `$group` implicitly emit `{total:0}`?

**Answer:** No. There may be no result document, and the method receives `null`/empty depending on its return type. Convert to 0 in the service if that is the business contract.

### Exercise 5 — Ambiguous scalar

If a pipeline returns `{orders:4,total:1250000}` and the method declares `Long`, what is problematic?

**Answer:** There are two numeric values; the mapper has extraction rules, yet the business intent is **ambiguous**. Project only `total`, or return a DTO containing both `orders` and `total`.

### Exercise 6 — Scalar list

You want the list of status names for t01 without counts—choose `List<String>` or `String`?

**Answer:** `List<String>`, with a pipeline producing one single-field document per status; result is CANCELLED, NEW, PAID.

### Exercise 7 — `AggregationResults`

How do `getMappedResults()`, `getUniqueMappedResult()`, and `getRawResults()` differ?

**Answer:** Respectively, they return the list of mapped objects, the single object when at most one result exists, and the raw BSON response from the driver/server. `getUniqueMappedResult()` throws an error if more than one result exists.

### Exercise 8 — `Sort` after the pipeline

The output DTO has `grossVnd` whereas the source entity has `amountVnd`. Should you pass `Sort.by("grossVnd")` or `Sort.by("amountVnd")`?

**Answer:** `grossVnd`, because the `Sort` parameter of a repository aggregation is applied at the **end of the pipeline** and mapped against the **return type**.

### Exercise 9 — Pagination

A pipeline groups orders into three states. What does `Pageable.ofSize(2)` on a repository `@Aggregation` paginate?

**Answer:** **The post-aggregation groups**, because sort/skip/limit are appended to the end of the pipeline. With `@Aggregation`, do not declare return type `Page<T>`; use `Slice<T>` if `hasNext` is needed.

### Exercise 10 — Counting in the right unit

Tenant t01 has six orders but three states. If the UI displays a table **grouped by state**, what is the total item count?

**Answer:** **3 groups**, not 6 orders. If a manual `Page` is required, the count must count output after `$group`.

### Exercise 11 — Keeping raw data

A DTO returns `grossVnd=0` while raw MongoDB has `grossVnd: NumberLong(1250000)`. Where should you investigate?

**Answer:** Check aliases, constructor component names, and converter/output types; temporarily return `AggregationResults<Document>` to inspect the BSON shape and types.

### Exercise 12 — Tenant protection

Why can a PAID total without `tenantId` become 2,150,000 VND?

**Answer:** It added `900,000` from tenant t02. `@Aggregation` does not automatically filter by tenant; the condition must be included in `$match` from the security context.

### Exercise 13 — Reactive scalar

Does a `Mono<Long>` from a repository aggregation for a tenant with no orders emit `0L` by default?

**Answer:** No. It may complete empty; use `defaultIfEmpty(0L)` if the service defines a zero fallback. Do not call `block()` on the event loop.

### Exercise 14 — Performance

A `$group` pipeline returns a single `Long` yet is still slow. Why?

**Answer:** The return type only changes **output mapping**; the server still has to filter and aggregate many documents. Check indexes for tenant/state, `explain`, group/sort resources, and execution time rather than optimizing by switching a DTO to a scalar.

## References

- [Spring Data MongoDB — MongoDB-specific Query Methods, Aggregation Methods](https://docs.spring.io/spring-data/mongodb/reference/mongodb/repositories/query-methods.html): `@Aggregation`, placeholders, DTO/scalar, `AggregationResults`, Stream, Sort/Pageable/Slice, and `Page` limitations.
- [Spring Data MongoDB — `@Aggregation` API](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/repository/Aggregation.html): pipeline annotation, field mapping, and parameters.
- [Spring Data MongoDB — `AggregationResults<T>` API](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/aggregation/AggregationResults.html): `getMappedResults()`, `getRawResults()`, `getUniqueMappedResult()`, and `getServerUsed()`.
- [Spring Data MongoDB — Aggregation Framework Support](https://docs.spring.io/spring-data/mongodb/reference/mongodb/aggregation-framework.html): typed aggregation, aggregation operations, aliases, mapping, and `MongoTemplate`.
- [Spring Data MongoDB — Object Mapping](https://docs.spring.io/spring-data/mongodb/reference/mongodb/mapping/mapping.html): `@Field`, `@MongoId`, converters, DTO/record mapping.
- [Spring Data MongoDB — `@Meta` API](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/repository/Meta.html): `allowDiskUse`, `maxExecutionTimeMs`, and comment.
- [MongoDB Manual — `$group`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/group/): grouping and accumulators.
- [MongoDB Manual — `$project`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/project/): aliases, keeping/excluding `_id`, output shape.
- [MongoDB Manual — `$sum`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/sum/): summation, numeric types, and accumulators.
- [MongoDB Manual — Aggregation Pipeline](https://www.mongodb.com/docs/manual/core/aggregation-pipeline/): stage ordering and intermediate data.
- [MongoDB Manual — Aggregation Pipeline Optimization](https://www.mongodb.com/docs/manual/core/aggregation-pipeline-optimization/): pipeline optimization capabilities and performance analysis.
