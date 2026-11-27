# Property Name Mapping, `@Field`, Aliases, and `strictMapping`

> **Chapter:** Basic Aggregation  
> **Module:** `SPRING_DATA_MONGODB` — using Spring Data MongoDB to connect, map documents, and operate on MongoDB via `MongoTemplate` or repositories; designing queries, aggregations, indexes, transactions, reactive access, testing, and data performance diagnostics.  
> **Goal:** Distinguish Java property names, BSON field names, and aggregation aliases; understand how `TypedAggregation` uses `@Field`; track exposed fields after `$project`/`$group`; use `AggregationOptions.strictMapping()` appropriately; and test real pipelines to prevent empty or silently wrong results.

## 1. Three Kinds of Names Easily Confused in Aggregation

A Java application may call an order amount `totalVnd`, while MongoDB stores the field as `amount_vnd`, and a report wants to emit `revenue`.

Those are **three distinct names**:

| Layer | Example | Who Defines It? |
| --- | --- | --- |
| **Java domain property** | `totalVnd` | Property in `OrderDocument` |
| **BSON field name** | `amount_vnd` | `@Field("amount_vnd")` and MongoDB document |
| **Pipeline alias** | `revenue` | `$project`, `$group`, `.as("revenue")` |

When input entity metadata is available, Spring Data MongoDB translates **Java property names** into **BSON names** in framework-supported stages. Once an alias is created via `$project` or `$group`, downstream stages must reference **the output name emitted by the previous stage**.

~~~mermaid
flowchart LR
    A["Java: totalVnd"] -->|"@Field"| B["MongoDB: amount_vnd"]
    B -->|"$project / $group"| C["Output: revenue"]
    C --> D["DTO: revenue"]
    D --> E["API JSON: revenue"]
~~~

**Do not conflate:**

- `@Field` is mapping metadata **between the entity and BSON**.
- `.as("revenue")` is an **alias generated inside the pipeline**.
- Output **DTO property names** map the pipeline result; they do not rename fields stored in the collection.
- `strictMapping` is a rule validating **field references while building a mapped pipeline**, not a database-wide MongoDB schema validator.

### 1.1. Why Can Field-Name Bugs Be Hard to Spot?

A `$match` that mistakenly uses:

~~~javascript
{ totalVnd: { $gte: 500000 } }
~~~

against a collection that only has `amount_vnd` usually returns **0 documents**, without necessarily throwing an error. A `$group` referencing a non-existent field may compute over null/missing values and produce a subtly broken report.

Worse, the pipeline executes cleanly while yielding numbers that misrepresent the business. This lesson focuses on preventing these bugs via **typed inputs**, **stage-accurate aliases**, **strict mapping**, and **integration tests**.

## 2. Dedicated Fixture for This Lesson

### 2.1. Data in `mongosh`

Run the commands below only on an **isolated learning database**, never on production data:

~~~javascript
use spring_data_mongodb_lab

const orders = db.orders_aggregation_demo_008;

orders.insertMany([
  {
    _id: "o801",
    tenant_id: "t01",
    state_code: "PAID",
    amount_vnd: 300000,
    placed_at: ISODate("2026-10-01T08:00:00Z"),
    buyer_doc: { display_name: "An", city_name: "Hà Nội" },
    order_lines: [
      { sku: "A", qty: 2 },
      { sku: "B", qty: 4 }
    ]
  },
  {
    _id: "o802",
    tenant_id: "t01",
    state_code: "PAID",
    amount_vnd: 800000,
    placed_at: ISODate("2026-10-02T08:00:00Z"),
    buyer_doc: { display_name: "Bình", city_name: "Hà Nội" },
    order_lines: [{ sku: "A", qty: 5 }]
  },
  {
    _id: "o803",
    tenant_id: "t01",
    state_code: "NEW",
    amount_vnd: 150000,
    placed_at: ISODate("2026-10-03T08:00:00Z"),
    buyer_doc: { display_name: "Chi", city_name: "Đà Nẵng" },
    order_lines: [{ sku: "A", qty: 1 }]
  },
  {
    _id: "o804",
    tenant_id: "t02",
    state_code: "PAID",
    amount_vnd: 999000,
    placed_at: ISODate("2026-10-04T08:00:00Z"),
    buyer_doc: { display_name: "Dũng", city_name: "Hà Nội" },
    order_lines: [{ sku: "A", qty: 6 }]
  },
  {
    _id: "o805",
    tenant_id: "t01",
    state_code: "PAID",
    amount_vnd: 400000,
    placed_at: ISODate("2026-10-05T08:00:00Z"),
    buyer_doc: { display_name: "An", city_name: "Huế" },
    order_lines: [{ sku: "C", qty: 3 }]
  },
  {
    _id: "o806",
    tenant_id: "t01",
    state_code: "PAID",
    amount_vnd: 600000,
    placed_at: ISODate("2026-10-05T08:00:00Z"),
    buyer_doc: { display_name: "Hoa", city_name: "Hà Nội" },
    order_lines: [{ sku: "A", qty: 5 }]
  }
]);

orders.createIndex({
  tenant_id: 1,
  state_code: 1,
  placed_at: -1,
  _id: -1
});
~~~

These fixed IDs are strictly for practice. Running `insertMany` a second time causes duplicate `_id` errors. Use a dedicated test database/collection or reset only fixtures you own; **never wipe a shared collection**.

### 2.2. Reference Data Table

| ID | Tenant | State | Amount (VND) | Buyer | City |
| --- | --- | --- | ---: | --- | --- |
| `o801` | t01 | PAID | 300,000 | An | Hà Nội |
| `o802` | t01 | PAID | 800,000 | Bình | Hà Nội |
| `o803` | t01 | NEW | 150,000 | Chi | Đà Nẵng |
| `o804` | t02 | PAID | 999,000 | Dũng | Hà Nội |
| `o805` | t01 | PAID | 400,000 | An | Huế |
| `o806` | t01 | PAID | 600,000 | Hoa | Hà Nội |

In tenant t01, there are **4 PAID orders** totaling **2,100,000 VND**: `300000 + 800000 + 400000 + 600000`. These numbers act as our oracle when testing aggregations. Although `o804` is PAID, it **must not be counted** because it belongs to another tenant.

### 2.3. Checking Native BSON Syntax

Direct MongoDB queries must use physical field names:

~~~javascript
orders.find(
  { tenant_id: "t01", state_code: "PAID" },
  { _id: 1, amount_vnd: 1, "buyer_doc.city_name": 1 }
);
~~~

A `{ tenantId: "t01" }` query in `mongosh` **will not** be translated into `tenant_id` by MongoDB. That translation belongs to Spring Data's mapping layer when supplied with entity metadata and a mapping-aware operation.

## 3. Domain Model with `@Field` and Nested Properties

### 3.1. Status Enum

~~~java
// OrderState.java
package com.example.aggregation;

public enum OrderState {
    NEW, PAID, CANCELLED
}
~~~

With default mapping, enums are typically stored as the string name of each constant. If a project uses custom converters, BSON may differ; never guess solely from the Java type without checking stored data.

### 3.2. Embedded Buyer

~~~java
// BuyerInfo.java
package com.example.aggregation;

import org.springframework.data.mongodb.core.mapping.Field;

public class BuyerInfo {
    @Field("display_name")
    private String displayName;

    @Field("city_name")
    private String city;

    protected BuyerInfo() { }

    public String getDisplayName() { return displayName; }
    public String getCity() { return city; }
}
~~~

### 3.3. Embedded Order Line

~~~java
// OrderLine.java
package com.example.aggregation;

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

### 3.4. Aggregate Root

~~~java
// OrderDocument.java
package com.example.aggregation;

import java.time.Instant;
import java.util.List;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.mapping.MongoId;

@Document(collection = "orders_aggregation_demo_008")
public class OrderDocument {
    @MongoId(FieldType.STRING)
    private String id;

    @Field("tenant_id")
    private String tenantId;

    @Field("state_code")
    private OrderState state;

    @Field("amount_vnd")
    private long totalVnd;

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
    public long getTotalVnd() { return totalVnd; }
    public Instant getPlacedAt() { return placedAt; }
    public BuyerInfo getBuyer() { return buyer; }
    public List<OrderLine> getLines() { return lines; }
}
~~~

In this model:

| Java Path | BSON Path |
| --- | --- |
| `id` | `_id` |
| `tenantId` | `tenant_id` |
| `state` | `state_code` |
| `totalVnd` | `amount_vnd` |
| `placedAt` | `placed_at` |
| `buyer` | `buyer_doc` |
| `buyer.displayName` | `buyer_doc.display_name` |
| `buyer.city` | `buyer_doc.city_name` |
| `lines` | `order_lines` |
| `lines.quantity` | `order_lines.qty` |

`@MongoId(FieldType.STRING)` stores `_id` as a BSON string. Embedded objects `BuyerInfo` and `OrderLine` **are not separate documents**; their metadata drives nested path mapping.

## 4. `Aggregation`, `TypedAggregation`, and Mapping Context

Spring Data MongoDB offers two main ways to construct pipelines:

~~~java
import static org.springframework.data.mongodb.core.aggregation.Aggregation.*;

// Pipeline without input type at creation time:
Aggregation untyped = newAggregation(
    match(Criteria.where("tenant_id").is("t01"))
);

// Pipeline with input type:
TypedAggregation<OrderDocument> typed = newAggregation(
    OrderDocument.class,
    match(Criteria.where("tenantId").is("t01"))
);
~~~

`TypedAggregation<OrderDocument>` retains **input document type** metadata. When Spring Data translates standard operations into BSON, this metadata maps properties such as `tenantId`, `totalVnd`, and nested paths honoring `@Field`.

### 4.1. Executing with `MongoTemplate`

~~~java
import org.bson.Document;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.aggregation.Aggregation;
import org.springframework.data.mongodb.core.aggregation.AggregationResults;
import org.springframework.data.mongodb.core.aggregation.TypedAggregation;
import org.springframework.data.mongodb.core.query.Criteria;

// template is an injected MongoTemplate:
TypedAggregation<OrderDocument> pipeline = Aggregation.newAggregation(
    OrderDocument.class,
    Aggregation.match(Criteria.where("tenantId").is("t01"))
);

AggregationResults<Document> results = template.aggregate(
    pipeline, Document.class
);

var rows = results.getMappedResults();
~~~

With typed aggregation, Spring Data derives the collection name from `@Document(collection = "orders_aggregation_demo_008")`. Overloads `aggregate(aggregation, collectionName, outputType)` and `aggregate(aggregation, inputType, outputType)` also exist; never confuse input collection/type with the output DTO type.

### 4.2. Untyped Aggregation Pattern

~~~java
Aggregation rawNames = Aggregation.newAggregation(
    Aggregation.match(
        Criteria.where("tenant_id").is("t01")
    )
);

var result = template.aggregate(
    rawNames,
    "orders_aggregation_demo_008",
    Document.class
);
~~~

When **no input type** is supplied and only a collection name is passed, never assume Spring Data knows `OrderDocument` to translate `tenantId`. To write Java property names, supply a typed/input entity context rather than expecting the framework to guess from the collection name.

### 4.3. Responsibility Map

~~~text
TypedAggregation<OrderDocument>
    |
    +-- input type / MappingMongoConverter
    |       +-- @Field, @MongoId, enum/custom converters where applicable
    |
    +-- AggregationOperationContext
    |       +-- maps field references on standard operations
    |       +-- tracks fields/aliases exposed by stages
    |
    +-- MongoDB aggregation pipeline
    |       +-- $match, $project, $group, $sort, $unwind...
    |
    +-- output mapping
            +-- Document or result DTO/record
~~~

A **typed pipeline** aids domain-aware mapping and path checks, yet it does not automatically solve BSON discrepancies, dynamic fields, raw stages, legacy schemas, or access control.

## 5. `$match`: Write Java Names, Let Spring Data Map to BSON

### 5.1. Filtering by Tenant and Enum

~~~java
TypedAggregation<OrderDocument> pipeline = newAggregation(
    OrderDocument.class,
    match(Criteria.where("tenantId").is("t01")
        .and("state").is(OrderState.PAID))
);

var result = template.aggregate(pipeline, Document.class);
~~~

Logical BSON pipeline:

~~~javascript
[
  {
    $match: {
      tenant_id: "t01",
      state_code: "PAID"
    }
  }
]
~~~

On the fixture, results are `o801`, `o802`, `o805`, and `o806`. `o804` is PAID but belongs to t02, so it is excluded.

**Rule:** Inside a DSL carrying an input entity type, write **Java properties** (`tenantId`, `state`). In `mongosh` or the raw driver, write **BSON names** (`tenant_id`, `state_code`).

### 5.2. Range Predicate on `@Field`-Mapped Property

~~~java
match(Criteria.where("tenantId").is("t01")
    .and("totalVnd").gte(500_000L))
~~~

Equivalent BSON condition:

~~~javascript
{
  tenant_id: "t01",
  amount_vnd: { $gte: 500000 }
}
~~~

On the fixture, orders in t01 totaling at least 500,000 are `o802` and `o806`. Adding `state = PAID` yields the same two orders.

### 5.3. Why Avoid BSON Names Inside a Typed Pipeline?

Code like:

~~~java
// DO NOT use BSON names instead of properties when writing TypedAggregation:
match(Criteria.where("amount_vnd").gte(500_000L))
~~~

behaves differently depending on mapping mode and version: the framework finds no Java property named `amount_vnd`, so `strictMapping` may throw an error while relaxed mode passes the unknown path through verbatim. This makes pipelines brittle and prone to breaking when Java properties are renamed or mapping settings change.

Pick **one clear convention**: entity-aware DSL uses Java names; raw BSON uses MongoDB names—and test the boundary between them.

## 6. `$project` and Pipeline-Generated Aliases

This is where `@Field` and `.as(...)` are most easily confused.

### 6.1. Projection Keeping Existing Fields Only

~~~java
TypedAggregation<OrderDocument> projection = newAggregation(
    OrderDocument.class,
    match(Criteria.where("tenantId").is("t01")),
    project("state", "totalVnd")
);
~~~

Logically, MongoDB receives `$project` with the **mapped BSON field names**, namely `state_code` and `amount_vnd`. Because this is an inclusion projection, MongoDB's `_id` **remains included by default** unless explicitly excluded.

### 6.2. Aliasing to Produce a New Result Shape

Suppose the API wants fields `orderId`, `buyerName`, and `amount`:

~~~java
TypedAggregation<OrderDocument> cards = newAggregation(
    OrderDocument.class,
    match(Criteria.where("tenantId").is("t01")
        .and("state").is(OrderState.PAID)),
    project()
        .and("_id").as("orderId")
        .and("buyer.displayName").as("buyerName")
        .and("totalVnd").as("amount")
        .andExclude("_id"),
    sort(Sort.Direction.DESC, "amount")
);
~~~

This pipeline uses **Java properties on the source side**:

- `buyer.displayName` maps to `buyer_doc.display_name`.
- `totalVnd` maps to `amount_vnd`.
- `orderId`, `buyerName`, and `amount` are **output field names**, not new fields written into the collection.

Logically equivalent MongoDB pipeline:

~~~javascript
[
  { $match: { tenant_id: "t01", state_code: "PAID" } },
  {
    $project: {
      _id: 0,
      orderId: "$_id",
      buyerName: "$buyer_doc.display_name",
      amount: "$amount_vnd"
    }
  },
  { $sort: { amount: -1 } }
]
~~~

Fixture output sorted by descending amount:

~~~javascript
[
  { orderId: "o802", buyerName: "Bình", amount: 800000 },
  { orderId: "o806", buyerName: "Hoa", amount: 600000 },
  { orderId: "o805", buyerName: "An", amount: 400000 },
  { orderId: "o801", buyerName: "An", amount: 300000 }
]
~~~

In the `$sort` stage after `$project`, we reference the alias `amount`, **not `totalVnd` or `amount_vnd`**, because those source names are no longer exposed by the preceding stage.

### 6.3. Common Bug: Sorting by a Dropped Property

~~~java
newAggregation(
    OrderDocument.class,
    project().and("totalVnd").as("amount"),
    sort(Sort.Direction.DESC, "totalVnd")
);
// Semantically wrong: previous stage only outputs amount, no longer totalVnd.
~~~

Under Spring Data aggregation's field exposure rules, subsequent stages may only reference **retained fields or newly exposed aliases**. Reference `amount` instead:

~~~java
newAggregation(
    OrderDocument.class,
    project().and("totalVnd").as("amount"),
    sort(Sort.Direction.DESC, "amount")
);
~~~

Some operation/version combinations catch stale references when constructing the pipeline; others emit a pipeline that silently fails to return expected results. Never rely solely on exceptions—**inspect the generated BSON pipeline and actual output**.

### 6.4. `@Field` Is Not `.as(...)`

~~~java
@Field("amount_vnd")
private long totalVnd;
~~~

is completely different from:

~~~java
project().and("totalVnd").as("amount");
~~~

The first maps **fields stored in the collection**; the second creates **a field in pipeline output**. Even if an alias happens to match another Java property name, Spring Data does not modify collection data or rename entity fields.

### 6.5. `_id` and the `orderId` Alias

MongoDB `$project` preserves `_id` by default unless `_id: 0` is set. Creating `orderId: "$_id"` without excluding `_id` outputs **both**.

~~~javascript
// To keep only orderId and drop _id:
{ $project: { _id: 0, orderId: "$_id" } }
~~~

In Spring Data, call `andExclude("_id")` to drop the original ID field. Define output schemas explicitly so DTOs do not accidentally carry both `id` and `orderId`.

## 7. `$group`: Source Field Names, Group `_id`, and Result Aliases

### 7.1. Grouping PAID Orders by Status

~~~java
TypedAggregation<OrderDocument> totals = newAggregation(
    OrderDocument.class,
    match(Criteria.where("tenantId").is("t01")
        .and("state").is(OrderState.PAID)),
    group("state")
        .count().as("orderCount")
        .sum("totalVnd").as("grossVnd")
);

var result = template.aggregate(totals, Document.class)
    .getMappedResults();
~~~

Logically, the corresponding BSON is:

~~~javascript
[
  { $match: { tenant_id: "t01", state_code: "PAID" } },
  {
    $group: {
      _id: "$state_code",
      orderCount: { $sum: 1 },
      grossVnd: { $sum: "$amount_vnd" }
    }
  }
]
~~~

Result contains **one summary document**:

~~~javascript
{
  _id: "PAID",
  orderCount: 4,
  grossVnd: 2100000
}
~~~

Here `state` and `totalVnd` in the Spring DSL are Java names; `state_code` and `amount_vnd` are BSON names; `orderCount` and `grossVnd` are accumulator **aliases**. After `$group`, `_id` **is the group key**, no longer the original order ID.

### 7.2. After `$group`, Source Fields Are No Longer Directly Available

Available fields after `$group` above are `_id`, `orderCount`, and `grossVnd`. Hence:

~~~java
sort(Sort.Direction.DESC, "grossVnd")
~~~

is valid because `grossVnd` was emitted by `group`. Conversely:

~~~java
sort(Sort.Direction.DESC, "totalVnd")
~~~

makes no semantic sense: each output document is now a **group**, no longer holding an individual order's `totalVnd`.

### 7.3. Renaming the Group Key to a DTO Property

Add `$project` after `$group`:

~~~java
TypedAggregation<OrderDocument> totals = newAggregation(
    OrderDocument.class,
    match(Criteria.where("tenantId").is("t01")),
    group("state")
        .count().as("orderCount")
        .sum("totalVnd").as("grossVnd"),
    project("orderCount", "grossVnd")
        .and("_id").as("stateName")
        .andExclude("_id"),
    sort(Sort.Direction.DESC, "grossVnd")
);
~~~

With alias `stateName`, output includes:

~~~javascript
{
  stateName: "PAID",
  orderCount: 4,
  grossVnd: 2100000
}
~~~

This example pipeline matches **tenant t01** without restricting status, so it actually outputs a NEW group document too. The JSON above shows the **PAID group**, not the full output. To include only PAID, add the status filter to the leading `$match`.

## 8. Nested Paths and `@Field` at Every Level

Given:

~~~java
@Field("buyer_doc")
private BuyerInfo buyer;

// Inside BuyerInfo:
@Field("city_name")
private String city;
~~~

the Java path `buyer.city` maps to BSON `buyer_doc.city_name`.

### 8.1. Grouping Order Count by City

~~~java
TypedAggregation<OrderDocument> byCity = newAggregation(
    OrderDocument.class,
    match(Criteria.where("tenantId").is("t01")
        .and("state").is(OrderState.PAID)),
    group("buyer.city")
        .count().as("orders"),
    sort(Sort.Direction.DESC, "orders")
);
~~~

Logically, `$group._id` uses `"$buyer_doc.city_name"`. Fixture output:

~~~javascript
[
  { _id: "Hà Nội", orders: 3 },
  { _id: "Huế", orders: 1 }
]
~~~

If `@Field("city_name")` were omitted in `BuyerInfo`, Spring Data would default to `city`, querying the wrong path while BSON still holds `city_name`.

### 8.2. Arrays of Embedded Documents and `$unwind`

To aggregate quantity sold by SKU:

~~~java
TypedAggregation<OrderDocument> unitsBySku = newAggregation(
    OrderDocument.class,
    match(Criteria.where("tenantId").is("t01")),
    unwind("lines"),
    group("lines.sku")
        .sum("lines.quantity").as("units"),
    sort(Sort.Direction.DESC, "units")
);
~~~

Typed mapping translates:

~~~text
lines                 -> order_lines
lines.sku             -> order_lines.sku
lines.quantity        -> order_lines.qty
~~~

After `$unwind`, each line item becomes an intermediate record. `$group` sums BSON field `qty`. `unwind("lines")` never alters the stored collection; it transforms documents **in the pipeline**.

In tenant t01's fixture, total `qty` per SKU is:

| SKU | Contributions | Total |
| --- | --- | ---: |
| A | 2 (o801) + 5 (o802) + 1 (o803) + 5 (o806) | 13 |
| B | 4 (o801) | 4 |
| C | 3 (o805) | 3 |

`o804` belongs to tenant t02 and is excluded. This shows nested `@Field` annotations on both the **array** and **element** matter.

### 8.3. Use `$elemMatch` When Filtering Must Match the Same Element

To find orders containing a line with `sku = A` and `quantity >= 5`, bind both predicates to **the same line item**:

~~~java
match(Criteria.where("lines").elemMatch(
    Criteria.where("sku").is("A")
        .and("quantity").gte(5)
))
~~~

Never write two independent dot-notation predicates assuming they must match the same array element. Alongside field mapping, **MongoDB matching semantics** must also be right.

## 9. `strictMapping`: Catching Non-Existent Properties in Typed Pipelines

Earlier versions of Spring Data MongoDB strictly validated property references against the input type. **Since version 3.2**, referencing a non-existent property no longer **throws an error by default** under relaxed mapping. To restore strict checking, enable `AggregationOptions.strictMapping()`.

### 9.1. Configuring `TypedAggregation`

~~~java
import org.springframework.data.mongodb.core.aggregation.AggregationOptions;
import org.springframework.data.mongodb.core.aggregation.TypedAggregation;

AggregationOptions strictOptions =
    AggregationOptions.builder()
        .strictMapping()
        .build();

TypedAggregation<OrderDocument> strictPipeline =
    Aggregation.newAggregation(
        OrderDocument.class,
        Aggregation.match(
            Criteria.where("tenantId").is("t01")
        ),
        Aggregation.project("state", "totalVnd")
    ).withOptions(strictOptions);

var rows = template.aggregate(
    strictPipeline,
    Document.class
).getMappedResults();
~~~

This references valid properties (`tenantId`, `state`, `totalVnd`), which map cleanly to their BSON fields.

### 9.2. Detecting Typos in Property Names

~~~java
TypedAggregation<OrderDocument> typo = Aggregation.newAggregation(
    OrderDocument.class,
    Aggregation.project("totalVNDD") // Typo: only totalVnd exists.
).withOptions(
    AggregationOptions.builder()
        .strictMapping()
        .build()
);

// When building/rendering/executing typed aggregation,
// Spring Data throws an error for non-existent property reference.
template.aggregate(typo, Document.class);
~~~

Do not assert on one narrow exception class across every Spring Data version and operation type; in tests, assert that an error is raised at the **property/pipeline translation boundary** before treating aggregation output as valid.

**Note:** `strictMapping` does not catch typos inside **raw JSON stages** that bypass the mapping context, nor does it verify that real BSON documents on MongoDB contain those fields or types.

### 9.3. Comparing the Three Mapping Modes

`AggregationOptions.Builder` provides three key modes:

| Mode | How It Works | When to Consider |
| --- | --- | --- |
| `strictMapping()` | Maps domain properties honoring `@Field`; **errors** when referencing unknown properties within checked scopes | Typed pipelines needing early detection of renames/typos |
| `relaxedMapping()` | Maps known properties; if unknown, **keeps the user-supplied name** | Pipelines intentionally referencing dynamic/unmodeled fields or special output stages |
| `noMapping()` | **Skips domain type mapping**; uses field names verbatim as written | Intentionally authoring BSON/raw-schema pipelines with every path verified |

Examples:

~~~java
AggregationOptions strict = AggregationOptions.builder()
    .strictMapping()
    .build();

AggregationOptions relaxed = AggregationOptions.builder()
    .relaxedMapping()
    .build();

AggregationOptions raw = AggregationOptions.builder()
    .noMapping()
    .build();
~~~

All three modes are **pipeline-level options** attached via `withOptions(...)`. Never confuse `noMapping()` with returning `Document.class`: **output type** and **input reference mapping policy** are orthogonal concepts.

### 9.4. Bugs Can Hide Under Relaxed Mapping

Suppose someone mistypes `totalVnd` as `totalVNDD`:

~~~java
Aggregation.project("totalVNDD");
~~~

In relaxed mode, Spring Data keeps the unknown field name as-is. MongoDB finds no such field in documents, so outputs silently miss the field without failing. If reports only check row counts, the defect slips into production.

**Recommendation:** Use `strictMapping()` for pipelines built against **stable entity schemas**. When dynamic fields from earlier stages or unmodeled legacy fields are genuinely needed, opt into relaxed/raw handling **deliberately**, inspect the emitted pipeline, and test outputs—rather than disabling mapping to silence errors.

### 9.5. `strictMapping` Is Not MongoDB Schema Validation

It **does not guarantee**:

- That the real collection contains every field declared on the entity.
- That every document stores the right data type (`amount_vnd` might occasionally be stored as a String).
- That `tenantId` was enforced by authorization.
- That aliases after `$project` serialize into DTOs as desired.
- That a hand-built raw `Document` `AggregationOperation` is fully checked.
- That pipeline business logic is accurate simply because property names are valid.

Pair mapping checks with **MongoDB schema validation**, legacy data audits, and result integration tests.

## 10. Raw Aggregation Stages and Mapping Boundaries

Not every stage goes through typed builders identically. Spring Data lets you supply raw stages for driver/MongoDB features not yet modeled by the DSL.

Example:

~~~java
AggregationOperation rawMatch = context ->
    new Document("$match",
        new Document("tenant_id", "t01"));

TypedAggregation<OrderDocument> pipeline =
    Aggregation.newAggregation(
        OrderDocument.class,
        rawMatch,
        Aggregation.project("state", "totalVnd")
    );
~~~

In `rawMatch`, you return a **hand-built** BSON `Document`; `"tenant_id"` here is the real BSON field. Never write `tenantId` expecting every raw stage implementation to invoke the converter automatically.

### 10.1. If You Need Mapping on a Raw `Document`

A custom operation can explicitly invoke the context:

~~~java
AggregationOperation mappedMatch = context -> {
    Document stage = new Document("$match",
        new Document("tenantId", "t01"));
    return context.getMappedObject(stage);
};
~~~

Here `getMappedObject(...)` asks the context to apply domain mapping where possible. Still, custom stages and field references must be tested carefully against your Spring Data version and stage shape—especially with newer operators, nested expressions, or aliases from prior stages.

Never pass raw JSON that **already uses BSON field names** blindly through `getMappedObject`, as it can behave unexpectedly. On complex pipelines, the cleanest split is **Spring DSL for entity-aware parts** and **tested raw BSON** where low-level APIs are truly required.

### 10.2. `Aggregation.stage(...)` and Raw Field Names

Spring Data MongoDB versions providing `Aggregation.stage(String json)` let you embed a literal JSON/BSON stage. Such raw stages **do not automatically apply `@Field` renaming**:

~~~java
AggregationOperation raw = Aggregation.stage(
    "{ $match: { tenant_id: 't01' } }"
);
~~~

This illustrates a raw stage. In real code, use actual BSON names and never concatenate user input into raw JSON strings. When a stage takes request parameters, prefer typed DSL/parameter binding or safe programmatic BSON construction.

### 10.3. Do Not Turn `noMapping()` Into a "Fix-All" Escape Hatch

Example:

~~~java
TypedAggregation<OrderDocument> rawNames =
    Aggregation.newAggregation(
        OrderDocument.class,
        Aggregation.match(
            Criteria.where("tenant_id").is("t01")
        )
    ).withOptions(
        AggregationOptions.builder().noMapping().build()
    );
~~~

With `noMapping`, `tenant_id` is passed verbatim. If you switch to `Criteria.where("tenantId")` while keeping `noMapping()`, the query looks for a **BSON field literally named `tenantId`** (absent in the fixture), yielding empty results.

**Never mix Java and BSON names arbitrarily** inside a pipeline with mapping disabled.

## 11. Field Exposure: Which Fields Does Each Stage Output?

An aggregation is a **data transformation chain**. Each stage receives documents from the previous stage, not always the original entity.

### 11.1. Name Flow Across Stages

~~~text
OrderDocument (input)
  tenantId, state, totalVnd, buyer.displayName
             |
             | typed mapping
             v
MongoDB $match
  tenant_id, state_code, amount_vnd, buyer_doc.display_name
             |
             | $project creates aliases
             v
orderId, buyerName, amount
             |
             | $sort uses aliases
             v
orderId, buyerName, amount
~~~

Once `$project` drops `amount_vnd` and emits `amount`, subsequent stages **cannot behave as if they were reading the source document**.

### 11.2. `$addFields` Keeps Old Fields; `$project` Can Drop Them

MongoDB example:

~~~javascript
[
  { $addFields: { amountWithTax: { $multiply: ["$amount_vnd", 1.1] } } },
  { $sort: { amountWithTax: -1 } }
]
~~~

`$addFields` appends new fields while **retaining** existing ones. By contrast:

~~~javascript
[
  { $project: { amount: "$amount_vnd", _id: 0 } },
  { $sort: { amount: -1 } }
]
~~~

`$project` here retains only `amount`; every unincluded source name disappears. Respect these exact semantics when writing the Spring DSL.

### 11.3. `$group` Replaces the Entire Document Shape

~~~javascript
{
  $group: {
    _id: "$state_code",
    revenue: { $sum: "$amount_vnd" }
  }
}
~~~

After this stage, `tenant_id`, `buyer_doc`, and per-document `amount_vnd` **no longer exist in the output**, unless collected in an accumulator. If a later stage needs a field, keep it earlier or carry it through an accumulator/alias.

### 11.4. Do Not Assume `strictMapping` Understands Arbitrary Dynamic Outputs

An arbitrary raw stage can emit fields outside the model that Spring Data cannot predict completely. When using `strictMapping`:

- Express dynamic fields through DSL operations that track aliases where supported.
- Keep raw stages at clear boundaries with accurate output names.
- Inspect the rendered BSON pipeline.
- Write integration tests covering every key alias.

`strictMapping` validates **references against metadata the framework knows**; it does not prove every MongoDB stage emits a fixed schema.

## 12. Output DTOs: Record Field Names Differ from Stored Names

An aggregation can return `org.bson.Document` for debugging, whereas APIs usually want a DTO:

~~~java
// OrderCard.java
package com.example.aggregation;

public record OrderCard(
    String orderId,
    String buyerName,
    long amount
) {
}
~~~

Pipeline:

~~~java
TypedAggregation<OrderDocument> pipeline = newAggregation(
    OrderDocument.class,
    match(Criteria.where("tenantId").is("t01")
        .and("state").is(OrderState.PAID)),
    project()
        .and("_id").as("orderId")
        .and("buyer.displayName").as("buyerName")
        .and("totalVnd").as("amount")
        .andExclude("_id"),
    sort(Sort.Direction.DESC, "amount")
);

List<OrderCard> cards = template.aggregate(
    pipeline, OrderCard.class
).getMappedResults();
~~~

`OrderCard` has a canonical constructor matching the output fields `orderId`, `buyerName`, and `amount`. For record or class-based DTO projections, constructor parameter names and types must align with returned BSON; complex constructors may require `@PersistenceCreator` or custom converters.

### 12.1. Why Separate Input Type from Output Type?

In the call:

~~~java
template.aggregate(pipeline, OrderCard.class);
~~~

- `OrderDocument.class` (carried by `TypedAggregation`) supplies **input metadata** to map Java properties to BSON.
- `OrderCard.class` defines **how to materialize outputs** produced by the pipeline.

Switching output to `Document.class` **does not disable input mapping** if the pipeline remains typed. Conversely, passing `OrderCard.class` as output **does not make the framework infer** `OrderDocument`'s `@Field` annotations if the pipeline lacks an input type.

### 12.2. `@Field` on a DTO Does Not Replace Pipeline Aliases

Output class mapping metadata may apply in certain scenarios, yet the simplest, most testable design is generating output aliases **that directly match DTO property names**.

~~~javascript
{ buyerName: "An", amount: 300000 }
~~~

maps cleanly to:

~~~java
record OrderCard(String orderId, String buyerName, long amount) { }
~~~

Never expect `@Field("amount_vnd")` on the input entity to automatically rename output alias `amount`. Input mapping and output DTOs are separate layers.

### 12.3. Missing/Null and Primitives in DTOs

If a pipeline fails to emit `amount` while the DTO declares primitive `long amount`, mapping may fail or fill defaults depending on constructor/converter rules. When numbers can be absent, prefer `Long`/`BigDecimal` with an explicit null policy. For money, never multiply carelessly with floating-point numbers when financial accuracy is required; design explicit types and rounding rules.

## 13. Measuring and Verifying Pipelines Before Trusting Results

### 13.1. Compare Against a `mongosh` Pipeline First

When mapping looks suspicious, write a transparent **BSON pipeline**:

~~~javascript
orders.aggregate([
  {
    $match: {
      tenant_id: "t01",
      state_code: "PAID"
    }
  },
  {
    $project: {
      _id: 0,
      orderId: "$_id",
      buyerName: "$buyer_doc.display_name",
      amount: "$amount_vnd"
    }
  },
  { $sort: { amount: -1 } }
]);
~~~

Compare record counts, ordering, key names, and values against `TypedAggregation`. If raw BSON works while Spring Data returns wrong values, check `@Field`, pipeline context, stage aliases, and DTO mapping.

### 13.2. Observing the Actual Command Sent

In test environments, enable appropriate logging or attach a MongoDB Java Driver `CommandListener` to inspect the **actual `aggregate` command sent**. When logging:

- Never log raw requests containing PII, emails, or tokens to shared log systems.
- Mask/redact sensitive values.
- Inspect BSON field names inside `$match`, `$project`, `$group`, and `$sort`.

`Aggregation.toString()` or printing Java objects does not always show **the fully mapped pipeline** across all configurations. Inspect the real driver/database command whenever certainty is required.

### 13.3. Debug Stage by Stage

When a 4-stage pipeline misbehaves, run sequentially:

1. `$match` alone to verify filtering and tenant isolation.
2. Add `$project` to check source fields and aliases.
3. Add `$group` if aggregating, verifying `_id` and accumulators.
4. Add `$sort`/`$limit`, referencing only surviving fields.
5. Run DTO mapping and cross-check against `Document.class`.

Do not rewrite all 4 stages simultaneously; isolating stages locates field-naming mistakes much faster.

## 14. Mapping, Indexes, and Performance

Renaming Java properties or defining aliases does not speed up queries by itself. **Indexes apply to BSON field names stored in the collection**, not DTO names:

~~~javascript
orders.createIndex({
  tenant_id: 1,
  state_code: 1,
  placed_at: -1,
  _id: -1
});
~~~

When the app writes:

~~~java
match(Criteria.where("tenantId").is("t01")
    .and("state").is(OrderState.PAID))
~~~

and typed mapping translates it to BSON `tenant_id/state_code`, that index can support document lookups depending on selectivity and the query planner.

### 14.1. Early `$match` to Narrow the Dataset

In principle, placing a selective `$match` near the start of a pipeline reduces the volume processed by later stages; MongoDB's optimizer also performs stage reordering where valid. Still, verify via `explain("executionStats")` rather than just counting stages.

~~~javascript
orders.explain("executionStats").aggregate([
  { $match: { tenant_id: "t01", state_code: "PAID" } },
  { $group: { _id: "$state_code", revenue: { $sum: "$amount_vnd" } } }
]);
~~~

This analyzes the **execution plan**, without replacing application-level latency and payload-size measurements. With only 6 fixture documents, you cannot draw production performance conclusions.

### 14.2. Aliases After `$project` Are Not Pre-Indexed Fields

If `$project` emits:

~~~javascript
{ amount: "$amount_vnd" }
~~~

`amount` is an output **inside the pipeline**, not a physical collection field. Creating `{ amount: 1 }` on the source collection will not automatically optimize sorting on an alias computed mid-pipeline. Identify which stages can leverage indexes and whether sorting can occur before transformations while preserving semantics.

### 14.3. `allowDiskUse` and Large Pipelines

For pipelines with large sorts or groups, `AggregationOptions` supports options like `allowDiskUse(true)` where MongoDB allows it. This is a **resource management setting**, not a fix for wrong field names:

~~~java
AggregationOptions options = AggregationOptions.builder()
    .strictMapping()
    .allowDiskUse(true)
    .build();

TypedAggregation<OrderDocument> configured =
    pipeline.withOptions(options);
~~~

Do not enable disk spill without controlling workload, deadlines, and memory; benchmark on sufficiently large data and review indexes and per-stage document counts.

## 15. Distinguishing `strictMapping` from Access Control and Business Correctness

A pipeline with completely valid property names can still leak data if it omits the tenant filter:

~~~java
TypedAggregation<OrderDocument> unsafe = newAggregation(
    OrderDocument.class,
    match(Criteria.where("state").is(OrderState.PAID)),
    group("state").sum("totalVnd").as("revenue")
).withOptions(AggregationOptions.builder().strictMapping().build());
~~~

`strictMapping` accepts every property here, yet the result sums **all tenants**, including t02's `o804`. In multi-tenant apps, tenant scope must be **enforced server-side** inside `$match`.

### 15.1. Safe Queries Require Multiple Control Layers

- **Field correctness:** input types and `@Field`/`strictMapping` validate property names.
- **Business correctness:** filters, same-element array matching, group keys, and aliases match requirements.
- **Security scope:** tenant and permissions checked before execution.
- **Data correctness:** valid BSON types, null/missing policies, consistent converters.
- **Operational safety:** limits, timeouts, indexes, and metrics for heavy reports.

Never treat `strictMapping` as proof that an entire pipeline is secure and correct.

## 16. Integration Tests Confirming Mapping and Aliases

Unit tests that merely mock `MongoTemplate.aggregate` verify method invocations, but **fail to prove**:

- `tenantId` actually maps to `tenant_id`.
- `buyer.displayName` actually maps to `buyer_doc.display_name`.
- Alias `amount` remains available when `sort` runs.
- `strictMapping` catches typos.
- Output DTO records map returned structures cleanly.

Run integration tests against an isolated test MongoDB or Testcontainers with dedicated fixtures.

### 16.1. Testing Typed Projection and Aliases

~~~java
package com.example.aggregation;

import static org.assertj.core.api.Assertions.assertThat;

import com.mongodb.client.model.Filters;
import java.time.Instant;
import java.util.Date;
import java.util.List;
import org.bson.Document;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.aggregation.Aggregation;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.domain.Sort;

@DataMongoTest
class AggregationFieldMappingTest {
    @Autowired MongoTemplate template;

    @Test
    void typedAggregationMapsNestedFieldsAndProjectionAliases() {
        String id = "fixture-agg008";
        var collection = template.getDb()
            .getCollection("orders_aggregation_demo_008");

        collection.deleteOne(Filters.eq("_id", id));
        try {
            collection.insertOne(
                new Document("_id", id)
                    .append("tenant_id", "fixture-tenant-008")
                    .append("state_code", "PAID")
                    .append("amount_vnd", 500000L)
                    .append("placed_at",
                        Date.from(Instant.parse(
                            "2026-10-01T08:00:00Z")))
                    .append("buyer_doc",
                        new Document("display_name", "Test")
                            .append("city_name", "Huế"))
                    .append("order_lines", List.of(
                        new Document("sku", "A").append("qty", 2)))
            );

            var pipeline = Aggregation.newAggregation(
                OrderDocument.class,
                Aggregation.match(
                    Criteria.where("tenantId").is("fixture-tenant-008")
                        .and("state").is(OrderState.PAID)
                ),
                Aggregation.project()
                    .and("_id").as("orderId")
                    .and("buyer.displayName").as("buyerName")
                    .and("totalVnd").as("amount")
                    .andExclude("_id"),
                Aggregation.sort(Sort.Direction.DESC, "amount")
            );

            List<OrderCard> cards = template.aggregate(
                pipeline, OrderCard.class
            ).getMappedResults();

            assertThat(cards).hasSize(1);
            assertThat(cards.get(0).orderId()).isEqualTo(id);
            assertThat(cards.get(0).buyerName()).isEqualTo("Test");
            assertThat(cards.get(0).amount()).isEqualTo(500000L);
        } finally {
            collection.deleteOne(Filters.eq("_id", id));
        }
    }
}
~~~

This runs a **real aggregation**, not a mocked converter. BSON `buyer_doc.display_name` is exercised via Java input `buyer.displayName`. Aliases `buyerName`/`amount` are verified through the DTO output.

**Run only on an isolated test database.** Setup/cleanup explicitly deletes only the fixture ID, avoiding ID collisions with parallel tests or jobs.

### 16.2. Testing `strictMapping` Rejecting Typos

Add a dedicated test (or mapping-context test):

~~~java
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import org.springframework.data.mongodb.core.aggregation.AggregationOptions;

@Test
void strictMappingRejectsUnknownInputProperty() {
    var typoPipeline = Aggregation.newAggregation(
        OrderDocument.class,
        Aggregation.project("totalVNDD")
    ).withOptions(
        AggregationOptions.builder().strictMapping().build()
    );

    assertThatThrownBy(() ->
        template.aggregate(typoPipeline, Document.class)
    ).isInstanceOf(RuntimeException.class);
}
~~~

This test belongs in the same `AggregationFieldMappingTest` class from Section 16.1, with `template` injected and `Document`/`Aggregation` imported. It verifies failure on a non-existent input property; avoid hardcoding fragile exception messages or overly narrow exception subclasses across Spring Data versions.

### 16.3. Testing Downstream Stages Do Not Reference Dropped Source Names

Run two **independent** pipelines:

~~~java
// Right: sort on the alias exposed by $project.
var correct = Aggregation.newAggregation(
    OrderDocument.class,
    Aggregation.project().and("totalVnd").as("amount"),
    Aggregation.sort(Sort.Direction.DESC, "amount")
);

// Semantically wrong: totalVnd is no longer exposed after project.
var wrong = Aggregation.newAggregation(
    OrderDocument.class,
    Aggregation.project().and("totalVnd").as("amount"),
    Aggregation.sort(Sort.Direction.DESC, "totalVnd")
);
~~~

Do not assume both versions fail with the exact same exception class. Verify that the valid pipeline sorts by `amount` with expected values, and ensure the invalid pipeline is **rejected as non-compliant**, whether the framework throws during rendering or the server produces wrong results.

### 16.4. Required Test Matrix

| Test Case | Expectation |
| --- | --- |
| Typed `$match` on `tenantId` | BSON filters `tenant_id` |
| Typed `$match` on `state` enum | BSON filters `state_code` accurately |
| Typed `$group.sum("totalVnd")` | Uses `amount_vnd`; t01 PAID sum is 2,100,000 |
| Nested `buyer.city` | Uses `buyer_doc.city_name`; Hà Nội 3, Huế 1 |
| Array `lines.quantity` | Uses `order_lines.qty`; SKU totals match |
| `project().and(...).as(...)` | Output uses requested aliases; source untouched |
| Sort after project | References alias, not dropped property |
| `_id` excluded | Output omits `_id` when `orderId` is projected |
| `strictMapping` with typo | Fails on unknown input property |
| Relaxed mapping | Unknown names may pass through; check output |
| No mapping | Hand-written BSON names stay unchanged |
| Raw stage | Uses BSON paths; does not expect implicit mapping |
| DTO output | Constructor names/types align with aliases |
| Other tenant | `o804` never enters t01 totals |
| Legacy missing/null | Handled by explicit policy, not confused with typos |

## 17. Diagnosing Common Errors

| Symptom | Common Cause | Resolution |
| --- | --- | --- |
| `$match` returns empty while `mongosh` finds docs | Java name in raw BSON or wrong BSON name in typed context | Check `@Field`, input type, and actual pipeline |
| `strictMapping` throws on `totalVNDD` | Property does not exist on input domain | Fix Java property name; never disable strict to hide typos |
| Switching to `noMapping` returns empty | Code still uses `tenantId` instead of BSON `tenant_id` | Use one consistent naming convention |
| DTO has `amount=0` despite `amount_vnd` in BSON | `$project` missed alias `amount` or DTO type mismatches | Inspect `Document` output and constructor |
| Sort after project misbehaves | Referenced `totalVnd` when only `amount` remained | Sort on exposed alias |
| Group output has `_id="PAID"` instead of order ID | `$group` puts group key in `_id` | Alias group key after grouping |
| Output has both `_id` and `orderId` | Projection forgot to exclude `_id` | Call `andExclude("_id")` |
| Nested city missing | Missing `@Field` on `buyer` or `BuyerInfo.city` | Verify `buyer.city` → `buyer_doc.city_name` |
| Wrong unit sum per SKU | Referenced `quantity` instead of `qty` or unwound wrong field | Use typed mapping and inspect raw pipeline |
| Raw `AggregationOperation` ignores `@Field` | Returned manual `Document` bypassing mapping context | Write BSON names or call `context.getMappedObject(...)` carefully |
| Turning off strict still produces wrong output | Relaxed mode lets typos pass and server treats them as missing | Keep strict on typed cases and assert actual values |
| t01 total includes t02 | Missing tenant filter | Enforce server-context tenant inside `$match` |
| Pipeline with few fields is still slow | `$group`/sort overhead or missing index support | Inspect `explain`, stage order, indexes, real data |
| Mock tests pass, production mapping fails | Mocks skip converters and MongoDB | Run integration tests via `MongoTemplate.aggregate` |
| `amount_vnd` missing in live documents | Legacy schema, not a Java property bug | Audit BSON, migrate, or define null policy |

## 18. Checklist for Correctly Mapped Aggregations

1. **Define input schema:** entity class, `@Document`, `@Field`, nested objects, and BSON types.
2. **Choose naming language:** typed DSL uses **Java properties**; raw MongoDB uses **BSON names**.
3. **Prefer typed aggregation** whenever a pipeline starts from an entity with clear mapping metadata.
4. **Enable `strictMapping()`** to catch invalid property references early, while knowing its boundaries.
5. **Distinguish `@Field` from `.as(...)`:** `@Field` maps storage, `.as(...)` names stage output.
6. **Track field exposure** across `$project`, `$group`, and `$unwind`.
7. **Sort/group on exposed names**, never on properties dropped in prior stages.
8. **Separate source `_id` from group `_id`**, designing explicit output DTOs.
9. **Do not assume raw stages auto-map**; verify BSON or invoke mapping context deliberately.
10. **Enforce tenant/authorization** in `$match`; never expect `strictMapping` to enforce security.
11. **Inspect legacy data:** handle missing/null/mistyped fields via explicit policy.
12. **Verify real pipelines** via `mongosh`/command listeners and integration tests for aliases, nested paths, and totals.
13. **Measure index/performance** on representative data; never extrapolate cost from tiny fixtures.

## 19. Practice Exercises

Exercises below use the initial fixture in Section 2, requiring no writes.

### Exercise 1 — Distinguish Three Names

An entity declares `@Field("amount_vnd") long totalVnd;`. A report needs output field `revenue`.

**Question:** Which is the Java property, which is the BSON field, and which is the alias?

**Answer:** `totalVnd` is the Java property; `amount_vnd` is the MongoDB field; `revenue` is the alias created by `project().and("totalVnd").as("revenue")`.

### Exercise 2 — Writing Typed `Criteria`

Write a condition matching orders for t01, state PAID, amount at least 500,000:

~~~java
match(Criteria.where("tenantId").is("t01")
    .and("state").is(OrderState.PAID)
    .and("totalVnd").gte(500_000L))
~~~

**Answer:** Valid in a typed aggregation over `OrderDocument.class`. MongoDB receives `tenant_id`, `state_code`, and `amount_vnd`, matching `o802` and `o806`.

### Exercise 3 — `$project` Alias

Given:

~~~java
project().and("totalVnd").as("amount")
~~~

Should the next stage sort on `totalVnd` or `amount`?

**Answer:** `amount`, since the project stage exposes only that alias. Use `sort(Sort.Direction.DESC, "amount")`.

### Exercise 4 — `_id` Changes Meaning

After:

~~~java
group("state").sum("totalVnd").as("grossVnd")
~~~

is `_id` still the order ID?

**Answer:** No. `_id` in `$group` output is the **group key**, here the state (`NEW`/`PAID`). To emit `stateName`, add `project().and("_id").as("stateName")` and exclude `_id` if desired.

### Exercise 5 — Calculating Totals to Catch Missing Tenant Filters

Tenant t01 has four PAID orders. What is the total amount?

**Answer:** **2,100,000 VND**. If `o804` from t02 leaks into the report, the total inflates and violates tenant isolation.

### Exercise 6 — Nested Property Paths

Java `buyer.city` uses `@Field("buyer_doc")` on `buyer` and `@Field("city_name")` on `city`. Which BSON path is queried?

**Answer:** `buyer_doc.city_name`. For t01/PAID, Hà Nội has 3 orders and Huế has 1.

### Exercise 7 — `strictMapping`

A developer mistypes `"totalVNDD"` inside `project` in a typed aggregation. Since Spring Data MongoDB 3.2, does it still throw by default like older versions?

**Answer:** No. To enforce checking unknown property references, apply:

~~~java
AggregationOptions.builder().strictMapping().build()
~~~

via `pipeline.withOptions(...)`. Test on your active framework version.

### Exercise 8 — `noMapping`

A pipeline enables `noMapping()` while filtering `Criteria.where("tenantId").is("t01")`. What goes wrong?

**Answer:** `noMapping` does not translate `tenantId` to `tenant_id`. Since the fixture lacks `tenantId`, the query returns empty. When deliberately using `noMapping`, write physical BSON field names.

### Exercise 9 — Raw Stages

A raw `AggregationOperation` returns:

~~~java
new Document("$match", new Document("tenantId", "t01"))
~~~

Is it guaranteed to be translated to `tenant_id`?

**Answer:** No. Raw BSON may pass straight to the driver. Use `tenant_id` or deliberately call `context.getMappedObject(...)`, then verify the emitted pipeline.

### Exercise 10 — Mapping to a DTO

To return `OrderCard(orderId, buyerName, amount)`, what must align?

**Answer:** Input type must be `OrderDocument.class` for `@Field` mapping; `$project` must emit aliases `orderId`/`buyerName`/`amount`; and the output constructor/record must match those names and BSON types. Never expect input `@Field` annotations to rename output DTO properties.

### Exercise 11 — Wrong BSON Types

A legacy document stores `amount_vnd: "500000"` as a string. Does `strictMapping` catch it?

**Answer:** No; Java property `totalVnd` exists on the class so the name is valid, even though stored data is mistyped. Use schema validation, data migration, and integration tests verifying aggregated values.

### Exercise 12 — Performance

A pipeline grouping revenue by state remains slow even with `strictMapping` enabled. What should you do?

**Answer:** Inspect indexes on `$match`'s BSON fields, tenant/state selectivity, document count entering `$group`, query plans, and metrics; `strictMapping` validates property names—it does not optimize execution.

## References

- [Spring Data MongoDB — Aggregation Framework Support](https://docs.spring.io/spring-data/mongodb/reference/mongodb/aggregation-framework.html): `TypedAggregation`, `@Field`, changes since 3.2, projection aliases, field exposure, and aggregation stages.
- [Spring Data MongoDB — `AggregationOptions.Builder` API](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/aggregation/AggregationOptions.Builder.html): `strictMapping()`, `relaxedMapping()`, `noMapping()`, and execution options.
- [Spring Data MongoDB — `TypedAggregation` API](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/aggregation/TypedAggregation.html): input type, `withOptions`, and mapping details.
- [Spring Data MongoDB — `MongoOperations` API](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/MongoOperations.html): `aggregate` and `aggregateStream` overloads.
- [Spring Data MongoDB — Object Mapping](https://docs.spring.io/spring-data/mongodb/reference/mongodb/mapping/mapping.html): mapping `@Document`, `@Field`, `@MongoId`, and embedded properties.
- [MongoDB Manual — Aggregation Pipeline](https://www.mongodb.com/docs/manual/core/aggregation-pipeline/): stage structure and intermediate documents.
- [MongoDB Manual — `$project`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/project/): include/exclude, field expressions, and aliases.
- [MongoDB Manual — `$group`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/group/): `_id` group keys and accumulators.
- [MongoDB Manual — `$unwind`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/unwind/): expanding arrays into intermediate documents.
- [MongoDB Manual — `$match`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/match/): filtering documents prior to aggregation stages.
