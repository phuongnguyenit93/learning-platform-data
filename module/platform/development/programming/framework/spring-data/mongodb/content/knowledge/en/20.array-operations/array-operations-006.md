# Updating Every Element with `$[]`

> **Chapter:** Array Operations  
> **Module:** `SPRING_DATA_MONGODB` — using Spring Data MongoDB to connect, map documents, and work with MongoDB via `MongoTemplate` or repositories; practicing queries, aggregations, indexes, transactions, reactive access, testing, and data performance diagnostics.  
> **Objective:** Understand the scope of the **all positional** operator `$[]`; update numeric arrays and embedded-document arrays; distinguish `$[]` from `$` and `$[identifier]`; integrate with `MongoTemplate`; handle nested arrays, missing values, `upsert`, concurrency control, and testing.

## 1. Why Do We Need the `$[]` Operator?

Suppose an order contains score entries:

~~~javascript
{
  _id: "o601",
  scores: [70, 80, 90]
}
~~~

If the business requirement is to **add 5 to every score**, the right MongoDB operation is:

~~~javascript
db.orders_array_demo_006.updateOne(
  { _id: "o601" },
  { $inc: { "scores.$[]": 5 } }
);
// scores: [75, 85, 95]
~~~

`$[]` is the *all positional operator*: a special token in an update path meaning **every element of the array at that level**. It is neither a Java array nor a generic wildcard symbol replaceable by `*`.

General syntax:

~~~javascript
db.collection.updateOne(
  { /* condition selecting documents */ },
  {
    $set: {
      "arrayField.$[]": newValue
    }
  }
);
~~~

For arrays of objects, append the field path after `$[]`:

~~~javascript
db.collection.updateOne(
  { _id: "some-id" },
  {
    $set: {
      "line_items.$[].reviewed": true
    }
  }
);
~~~

In the second example, every element of `line_items` has its `reviewed` property set to `true`, even elements that never matched a SKU condition.

### 1.1. Two Scope Levels Must Not Be Conflated

This is the most important rule of the lesson:

1. **The query selects documents:** `{ _id: "o601" }` or `{ tenant_id: "t01", state: "OPEN" }`.
2. **`$[]` selects elements inside the array:** **all elements** of that array field in **each selected document**.

~~~mermaid
flowchart TD
    Q["Filter: select matching documents"] --> D1["Document o601"]
    Q --> D2["Document o602"]
    D1 --> A1["scores[0]"]
    D1 --> A2["scores[1]"]
    D1 --> A3["scores[2]"]
    D2 --> B1["scores[0]"]
    D2 --> B2["scores[1]"]
    A1 --> U["Apply the same update operator"]
    A2 --> U
    A3 --> U
    B1 --> U
    B2 --> U
~~~

When using `updateMany`, multiple documents may be selected; when using `$[]`, multiple **array elements within each document** may also be modified. `UpdateResult.modifiedCount` counts **documents**, **not array elements**.

## 2. Hands-On Practice Dataset

Examples use `mongosh` against a **dedicated learning database**, never a live business collection. Seed the initial data once:

~~~javascript
use spring_data_mongodb_lab

const orders = db.orders_array_demo_006;

orders.insertMany([
  {
    _id: "o601",
    tenant_id: "t01",
    state: "OPEN",
    scores: [70, 80, 90],
    line_items: [
      { sku: "A", qty: 2, reviewed: false, unitPriceVnd: 120000 },
      { sku: "B", qty: 4, reviewed: false, unitPriceVnd: 50000 }
    ],
    shipments: [
      {
        warehouse: "HN",
        packages: [
          { sku: "A", scanned: false },
          { sku: "B", scanned: false }
        ]
      },
      {
        warehouse: "DN",
        packages: [
          { sku: "C", scanned: false }
        ]
      }
    ]
  },
  {
    _id: "o602",
    tenant_id: "t01",
    state: "OPEN",
    scores: [65, 75],
    line_items: [
      { sku: "A", qty: 5, reviewed: false, unitPriceVnd: 120000 },
      { sku: "C", qty: 1, reviewed: false, unitPriceVnd: 70000 }
    ],
    shipments: [
      {
        warehouse: "HN",
        packages: [{ sku: "A", scanned: false }]
      }
    ]
  },
  {
    _id: "o603",
    tenant_id: "t01",
    state: "DONE",
    scores: [],
    line_items: [],
    shipments: []
  },
  {
    _id: "o604",
    tenant_id: "t02",
    state: "OPEN",
    scores: [90],
    line_items: [
      { sku: "A", qty: 9, reviewed: false, unitPriceVnd: 120000 }
    ],
    shipments: []
  },
  {
    _id: "o605",
    tenant_id: "t01",
    state: "OPEN",
    shipments: []
    // Legacy data: missing scores and line_items.
  }
]);

orders.createIndex({ tenant_id: 1, state: 1 });
orders.find({}, { _id: 1, tenant_id: 1, state: 1, scores: 1 });
~~~

IDs are fixed so results can be compared easily. Re-running `insertMany` on a collection that already contains those IDs will throw a duplicate `_id` key error. Avoid calling `drop()`/`deleteMany({})` on a shared database just to “reset” the lesson; use a fresh test collection or delete only the data you own.

| ID | Tenant | Scores | Line Count | Key Note |
| --- | --- | --- | ---: | --- |
| `o601` | t01 | `[70,80,90]` | 2 | Lines A and B, two warehouses HN/DN |
| `o602` | t01 | `[65,75]` | 2 | Lines A and C, warehouse HN |
| `o603` | t01 | `[]` | 0 | Empty array |
| `o604` | t02 | `[90]` | 1 | Different tenant |
| `o605` | t01 | Missing | Missing | Legacy document missing array fields |

**Convention:** Each update snippet below is explained against the **initial fixture**; unless explicitly noted as sequential, treat each snippet as an **independent scenario**. After an `$inc` or `$set`, the data has changed so subsequent examples would otherwise see different inputs.

## 3. Scalar Arrays: Updating All Elements

### 3.1. `$inc` on a Numeric Array

~~~javascript
const result = orders.updateOne(
  { _id: "o601" },
  { $inc: { "scores.$[]": 5 } }
);

printjson(result);
orders.findOne({ _id: "o601" }, { scores: 1 });
// scores: [75, 85, 95]
~~~

`$inc` adds to each numeric element. All three positions are updated in **a single single-document update command**. If the array contains non-numeric elements, do not expect addition to succeed as with valid data; check the schema or fix mistyped values first.

### 3.2. `$set` Assigning the Same Value to Every Element

~~~javascript
orders.updateOne(
  { _id: "o601" },
  { $set: { "scores.$[]": 0 } }
);
// scores: [0, 0, 0]
~~~

`$set` on the path `scores.$[]` **does not** replace the entire array with the number 0; it replaces **each element's value** with 0 while preserving array length. To replace the whole array with a new array, use:

~~~javascript
orders.updateOne(
  { _id: "o601" },
  { $set: { scores: [10, 20] } }
);
// scores: [10, 20]
~~~

These two approaches differ in scope, preserved data, and concurrency behavior. Replacing the entire array can overwrite elements just appended by another writer.

### 3.3. Empty Array: No Elements to Update

~~~javascript
const result = orders.updateOne(
  { _id: "o603" },
  { $set: { "scores.$[]": 0 } }
);

// scores on o603 remains [].
~~~

Document `o603` **matches** on `_id`, yet `scores` is empty so there are no elements to modify. In a direct driver update like this, `matchedCount` can be 1 while `modifiedCount` is 0. Note that when using `MongoTemplate` with an entity carrying `@Version`, the framework may auto-increment version, making `modifiedCount` differ from the raw driver case; never equate document counts with element counts.

### 3.4. `$unset`, `$pull`, and Deleting an Array Are Different

To **remove elements** from an array, use an operator like `$pull`:

~~~javascript
// Remove numbers >= 80 (on original fixture o601).
orders.updateOne(
  { _id: "o601" },
  { $pull: { scores: { $gte: 80 } } }
);
// scores: [70].
~~~

To **remove the array field completely**:

~~~javascript
orders.updateOne(
  { _id: "o601" },
  { $unset: { scores: "" } }
);
// Document no longer has the scores field.
~~~

To **keep the field while clearing all elements**:

~~~javascript
orders.updateOne(
  { _id: "o601" },
  { $set: { scores: [] } }
);
// scores: [].
~~~

Do not use `$unset` on an array position expecting elements to compact like `$pull`. When business logic requires removing elements matching a condition, choose `$pull`/pipeline instead of an inappropriate positional update.

## 4. Embedded-Document Arrays: Updating a Field Across Every Object

In `o601`:

~~~javascript
line_items: [
  { sku: "A", qty: 2, reviewed: false, unitPriceVnd: 120000 },
  { sku: "B", qty: 4, reviewed: false, unitPriceVnd: 50000 }
]
~~~

To mark **every line item** as reviewed:

~~~javascript
orders.updateOne(
  { _id: "o601" },
  { $set: { "line_items.$[].reviewed": true } }
);
~~~

Result:

~~~javascript
line_items: [
  { sku: "A", qty: 2, reviewed: true, unitPriceVnd: 120000 },
  { sku: "B", qty: 4, reviewed: true, unitPriceVnd: 50000 }
]
~~~

There is no need to enumerate indexes `line_items.0.reviewed`, `line_items.1.reviewed`. `$[]` also works regardless of how many elements the array holds, provided the elements share the right type and structure.

### 4.1. Incrementing Quantity Across All Lines

~~~javascript
orders.updateOne(
  { _id: "o601" },
  { $inc: { "line_items.$[].qty": 1 } }
);
// A qty: 2 -> 3; B qty: 4 -> 5.
~~~

This adds to every line item and is **not** a safe way to increment quantity for SKU A alone. If business rules require targeting lines by SKU or quantity predicates, see `$[identifier]` in section 6.

### 4.2. Replacing the Whole Object vs. Updating a Sub-Field

~~~javascript
// Modifies only the flag, preserving sku/qty/unitPriceVnd.
{ $set: { "line_items.$[].reviewed": true } }

// Replaces each array element with a brand-new document:
{ $set: { "line_items.$[]": { reviewed: true } } }
~~~

The second command **drops** `sku`, `qty`, and `unitPriceVnd` in every element because it replaces the entire embedded object. To avoid losing data, target the exact **sub-field path** to modify.

## 5. Common Mistake: Query Matches One Element, Yet `$[]` Updates All of Them

Consider:

~~~javascript
orders.updateOne(
  {
    _id: "o601",
    "line_items.sku": "A"
  },
  {
    $set: { "line_items.$[].reviewed": true }
  }
);
~~~

Actual meaning:

1. `"line_items.sku": "A"` checks whether **the order contains at least one SKU A line**.
2. Since `o601` has A, that document is selected.
3. `"line_items.$[].reviewed"` applies to **both line A and line B** in `o601`.

| Line Item | SKU | Matches `"line_items.sku":"A"` Individually? | Updated by `$[]`? |
| --- | --- | --- | --- |
| `o601.lines[0]` | A | Yes | **Yes** |
| `o601.lines[1]` | B | No | **Yes** |

**There is no implicit binding** between the element that caused the *document* to match the query and the elements updated by `$[]`.

This is especially dangerous when the requirement is “discount only SKU A lines” or “mark only unprocessed lines”. In those cases, switch from `$[]` to `$` or `$[identifier]` to match intent.

### 5.1. Comparing All Three Positional Operators

| Operator | Which Elements Are Selected? | What Does It Require? | Example |
| --- | --- | --- | --- |
| `$` | **First element matching** the query's array condition | Query must constrain the corresponding array | `"line_items.$.reviewed"` |
| `$[]` | **All elements** of the array in each matched document | Array field must exist and match expected structure | `"line_items.$[].reviewed"` |
| `$[line]` | **All elements matching** `arrayFilters` | Define identifier `line` in `arrayFilters` | `"line_items.$[line].reviewed"` |

`$` fits when only the first matching element should update; it has limitations when queries span multiple arrays or in upserts. `$[]` fits when every element truly needs the same update. `$[identifier]` lets you filter by **each element's attributes**.

### 5.2. Updating Only the First Matching Element with `$`

~~~javascript
orders.updateOne(
  { _id: "o601", "line_items.sku": "A" },
  { $set: { "line_items.$.reviewed": true } }
);
// Only the first element A matching the query is updated.
~~~

When an array has multiple SKU A lines, `$` updates only the **first matching element**. To update **all A lines**, use the filtered positional operator `$[line]`.

## 6. `$[identifier]` + `arrayFilters` When Element Filtering Is Needed

### 6.1. Marking Only SKU A Lines

~~~javascript
orders.updateOne(
  { _id: "o601" },
  { $set: { "line_items.$[line].reviewed": true } },
  {
    arrayFilters: [
      { "line.sku": "A" }
    ]
  }
);
// Line A is marked; line B retains reviewed:false.
~~~

`line` is an **array element variable name**, not a real field stored in MongoDB. It is declared in the `$[line]` path and referenced inside `arrayFilters` via `line.sku`.

Identifier names must obey MongoDB rules (starting with a lowercase letter, followed by alphanumeric characters). Do not insert spaces inside `$[ line ]`; write `$[line]`.

### 6.2. Quantity Predicate in the Array Filter

~~~javascript
orders.updateOne(
  { _id: "o601" },
  { $set: { "line_items.$[line].reviewed": true } },
  {
    arrayFilters: [
      {
        "line.qty": { $gte: 3 }
      }
    ]
  }
);
// On the original fixture: only line B (qty:4) is modified.
~~~

The `arrayFilters` filter is not the query that selects orders; it only determines which **elements** get updated inside each document already selected by the query.

### 6.3. `$[]` Does Not Take Its Own `arrayFilters`

`$[]` carries no identifier name and therefore **does not need** a corresponding `arrayFilters` entry:

~~~javascript
orders.updateOne(
  { _id: "o601" },
  { $set: { "line_items.$[].reviewed": true } }
);
~~~

Do not pass `arrayFilters: [{"line.sku":"A"}]` with an update that only uses `$[]` and has no `$[line]`. To filter elements, **change the update path itself** to `$[line]`.

### 6.4. Limitations of `arrayFilters`

According to the MongoDB Manual, an array filter document does not support certain query operators such as `$expr`, `$text`, or `$where`. When complex cross-field calculations or array reconstruction are needed, consider an **aggregation pipeline update** (`$map`/`$cond`) instead of forcing logic into `arrayFilters`.

Do not mix `arrayFilters` with an **update pipeline** expecting them to work together; `arrayFilters` is an option for operator-based updates and does not apply to aggregation pipeline updates.

## 7. Nested Arrays: `$[]` at Each Level

Order `o601` has multiple shipments, each with multiple packages:

~~~text
shipments
├── HN
│   └── packages: [A:false, B:false]
└── DN
    └── packages: [C:false]
~~~

### 7.1. Marking Every Package in Every Shipment

~~~javascript
orders.updateOne(
  { _id: "o601" },
  {
    $set: {
      "shipments.$[].packages.$[].scanned": true
    }
  }
);
~~~

Path breakdown by level:

~~~text
shipments             shipments array
    .$[]              every shipment
    .packages         packages array inside each shipment
    .$[]              every package
    .scanned          boolean field to update
~~~

Result: A and B in HN as well as C in DN all get `scanned: true`. Using two `$[]` tokens does not select only the first package in each shipment; it traverses **every element of both array levels**.

### 7.2. All Shipments, Only SKU A Packages

~~~javascript
orders.updateOne(
  { _id: "o601" },
  { $set: { "shipments.$[].packages.$[pkg].scanned": true } },
  {
    arrayFilters: [
      { "pkg.sku": "A" }
    ]
  }
);
// A in HN is updated; B in HN and C in DN remain unchanged.
~~~

At the `shipments` level, `$[]` still iterates across all shipments. At the `packages` level, `$[pkg]` updates only packages matching `pkg.sku = "A"`.

### 7.3. Only HN Shipment, All Packages in That Shipment

~~~javascript
orders.updateOne(
  { _id: "o601" },
  { $set: { "shipments.$[ship].packages.$[].scanned": true } },
  {
    arrayFilters: [
      { "ship.warehouse": "HN" }
    ]
  }
);
// A/B in HN are updated; package C in DN stays scanned:false.
~~~

### 7.4. Filtering Both Levels Simultaneously

~~~javascript
orders.updateOne(
  { _id: "o601" },
  {
    $set: {
      "shipments.$[ship].packages.$[pkg].scanned": true
    }
  },
  {
    arrayFilters: [
      { "ship.warehouse": "HN" },
      { "pkg.sku": "A" }
    ]
  }
);
// Only A inside shipment HN.
~~~

**Design rule:** place `$[]` at levels where you want **all** elements, and `$[identifier]` at levels where you want to **filter**. With multiple nested arrays, specify each level explicitly and test non-matching cases as well.

### 7.5. When Nested Arrays Lack Uniform Structure

If one shipment is missing `packages`, has `packages: null`, or contains non-document elements, paths like `shipments.$[].packages.$[].scanned` can fail because the path is missing or mistyped. `$[]` does not auto-create missing child arrays so traversal can continue.

For schemas mixing old and new records, **normalize the schema** or write a separate update targeting malformed records. Do not assume `$[]` silently skips mistyped elements.

## 8. Spring Data MongoDB: Mapping `$[]` via `MongoTemplate`

### 8.1. Java Models for Document and Arrays

Each class in this example goes in its own file under package `com.example.arrayops`.

~~~java
// OrderLine.java
package com.example.arrayops;

import org.springframework.data.mongodb.core.mapping.Field;

public class OrderLine {
    private String sku;

    @Field("qty")
    private int quantity;

    private boolean reviewed;
    private long unitPriceVnd;

    protected OrderLine() { }

    public String getSku() { return sku; }
    public int getQuantity() { return quantity; }
    public boolean isReviewed() { return reviewed; }
    public long getUnitPriceVnd() { return unitPriceVnd; }
}
~~~

~~~java
// PackageItem.java
package com.example.arrayops;

public class PackageItem {
    private String sku;
    private boolean scanned;

    protected PackageItem() { }

    public String getSku() { return sku; }
    public boolean isScanned() { return scanned; }
}
~~~

~~~java
// Shipment.java
package com.example.arrayops;

import java.util.List;

public class Shipment {
    private String warehouse;
    private List<PackageItem> packages;

    protected Shipment() { }

    public String getWarehouse() { return warehouse; }
    public List<PackageItem> getPackages() { return packages; }
}
~~~

~~~java
// OrderDocument.java
package com.example.arrayops;

import java.util.List;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.mapping.MongoId;

@Document(collection = "orders_array_demo_006")
public class OrderDocument {
    @MongoId(FieldType.STRING)
    private String id;

    @Field("tenant_id")
    private String tenantId;

    private String state;
    private List<Integer> scores;

    @Field("line_items")
    private List<OrderLine> lineItems;

    private List<Shipment> shipments;

    protected OrderDocument() { }

    public String getId() { return id; }
    public String getTenantId() { return tenantId; }
    public String getState() { return state; }
    public List<Integer> getScores() { return scores; }
    public List<OrderLine> getLineItems() { return lineItems; }
    public List<Shipment> getShipments() { return shipments; }
}
~~~

Notable points:

- Java property `lineItems` is stored as BSON field `line_items`.
- Java property `OrderLine.quantity` is stored as BSON `qty`.
- `MongoTemplate` uses entity metadata to map **update/query paths** when `OrderDocument.class` is supplied.
- `$[]` and `$[line]` are not Java properties; they are MongoDB **path operators**.

### 8.2. Updating a Scalar Array with `Update.inc`

~~~java
import com.mongodb.client.result.UpdateResult;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;

// Inside a service with MongoTemplate template available:
Query byId = Query.query(Criteria.where("id").is("o601"));

Update incrementEachScore =
    new Update().inc("scores.$[]", 5);

UpdateResult result = template.updateFirst(
    byId, incrementEachScore, OrderDocument.class
);
// On original data: scores [70,80,90] -> [75,85,95].
~~~

`Update.inc("scores.$[]", 5)` expresses `{ $inc: { "scores.$[]": 5 } }` in Spring Data. There is no separate mandatory `updateAllElements()` method; you place `$[]` directly inside the **property path**.

### 8.3. Updating Every Embedded Object with `Update.set`

~~~java
Query query = Query.query(
    Criteria.where("id").is("o601")
);

Update update =
    new Update().set("lineItems.$[].reviewed", true);

UpdateResult result = template.updateFirst(
    query, update, OrderDocument.class
);
~~~

With the declared metadata, Java path `lineItems.$[].reviewed` maps to BSON `line_items.$[].reviewed`. Both line A and line B of `o601` are marked without loading `OrderDocument` or editing `List<OrderLine>` in memory.

### 8.4. Updating All Elements Across Multiple Documents

~~~java
Query query = Query.query(
    Criteria.where("tenantId").is("t01")
        .and("state").is("OPEN")
        .and("scores").type(4) // BSON array; Type 4.
);

Update update = new Update().inc("scores.$[]", 5);

UpdateResult result = template.updateMulti(
    query, update, OrderDocument.class
);
~~~

On the original fixture, the filter selects `o601` and `o602`: `o603` is not OPEN, `o604` belongs to t02, and `o605` has no `scores`. A total of **5 score elements** are incremented across **2 documents**. With acknowledged writes and no version/callback fields, `matchedCount = 2` and `modifiedCount = 2`; the number `5` does not appear in `modifiedCount`.

In production code, you can use `org.bson.BsonType.ARRAY.getValue()` instead of magic number 4 for readability if supported by your criteria/driver version; the key point is enforcing a **real array field** rather than guessing.

### 8.5. Fluent Update Uses the Same Path Syntax

~~~java
UpdateResult result = template.update(OrderDocument.class)
    .matching(Criteria.where("id").is("o601"))
    .apply(new Update().set("lineItems.$[].reviewed", true))
    .first();

UpdateResult all = template.update(OrderDocument.class)
    .matching(Criteria.where("tenantId").is("t01")
        .and("state").is("OPEN")
        .and("scores").type(4))
    .apply(new Update().inc("scores.$[]", 5))
    .all();
~~~

`first()` corresponds to `updateFirst`; `all()` corresponds to `updateMulti`. Changing the number of **documents** does not change `$[]` semantics: each selected document still updates **all elements** at the specified path.

### 8.6. Spring Data `Update.filterArray` for `$[identifier]`

If you only want lines with `qty >= 3`:

~~~java
Update filtered = new Update()
    .set("lineItems.$[line].reviewed", true)
    .filterArray(
        Criteria.where("line.qty").gte(3)
    );

template.updateFirst(
    Query.query(Criteria.where("id").is("o601")),
    filtered,
    OrderDocument.class
);
// Only line B (qty:4) of o601 is marked.
~~~

**Mapping trap:** Spring Data's `Update.filterArray(...)` documentation specifies that `CriteriaDefinition`/expressions inside `arrayFilters` are **passed straight to the driver without field-name mapping**. Thus writing `line.qty` uses the right BSON name; `line.quantity` is the Java property and **is not automatically translated** inside `arrayFilters`.

Conversely, `set("lineItems.$[line].reviewed",...)` is mapped using entity metadata where supported by Spring Data. Whenever Java/BSON names differ in nested arrays, write integration tests to inspect actual BSON and avoid writing wrong fields.

## 9. Errors When the Array Is Missing, Null, or Wrong Type

`$[]` is designed to update **existing arrays**. Do not expect it to auto-create `[]` for a missing field:

~~~javascript
// o605 lacks scores.
orders.updateOne(
  { _id: "o605" },
  { $inc: { "scores.$[]": 5 } }
);
// Can error because path scores does not exist / is not an array.
~~~

Similarly, with documents:

~~~javascript
{ _id: "legacy-001", scores: null }
{ _id: "legacy-002", scores: "70,80" }
~~~

`scores` is not a valid numeric array; positional updates can fail due to type/path errors. Never treat Java `null` as proof that BSON is an empty array: **missing**, BSON `null`, and `[]` are all distinct.

### 9.1. Normalize Missing Fields to Empty Arrays First

~~~javascript
// Applies only to documents without a scores field.
orders.updateMany(
  { scores: { $exists: false } },
  { $set: { scores: [] } }
);
~~~

If business rules allow BSON null and you want to convert null to an empty array:

~~~javascript
orders.updateMany(
  { scores: { $type: "null" } },
  { $set: { scores: [] } }
);
~~~

Both commands have **distinct filters** so they do not overwrite arrays that already contain values. After normalization, `$[]` on `[]` modifies zero elements; if you need default scores, use an explicit element/array initialization policy instead of positional updates alone.

### 9.2. Restrict Updates to Documents That Have an Array

~~~javascript
orders.updateMany(
  {
    tenant_id: "t01",
    state: "OPEN",
    scores: { $type: "array" }
  },
  { $inc: { "scores.$[]": 5 } }
);
~~~

`$type: "array"` excludes missing/null/scalar fields at the checked level, yet **does not verify every element inside is a number**. If the array holds strings, objects, or null, `$inc` on that element can still fail. Use schema validation and data audits where strict element type integrity is required.

### 9.3. Do Not Use Broad Filters as a Way to Ignore Errors

~~~javascript
orders.updateMany(
  { tenant_id: "t01" },
  { $inc: { "scores.$[]": 5 } }
);
~~~

A broad query can hit both `o605` (missing `scores`) and `o603` (empty array). On mixed data, the operation can error partway through updating multiple documents. **Multi-document updates are not an all-or-nothing transaction**: a failure does not guarantee earlier document updates roll back.

Therefore, validate schemas, narrow queries, and use transactions/retries when business rules require it.

## 10. `upsert` and an Important Exception for `$[]`

In MongoDB, `upsert` updates if a match is found, or inserts a new document if none matches. With `$[]`, the **insert branch** has a special requirement:

> If an upsert results in an insert, the query must contain an **exact equality match on the array field referenced by `$[]`**.

### 10.1. Valid Example: Exact Equality on the Whole Array

Run on a **secondary collection** reserved for testing:

~~~javascript
const arrays = db.array_upsert_demo_006;

arrays.updateOne(
  { values: [2, 4] },
  { $set: { "values.$[]": 0 } },
  { upsert: true }
);
// If no matching document exists, this can insert:
// { _id: ObjectId(...), values: [0, 0] }
~~~

`{ values: [2, 4] }` is an **exact equality match** on the array field. MongoDB has the array structure needed to apply `$[]` during insert. Note: running the same command again can insert another document because `values` became `[0,0]` and no longer matches `[2,4]`; this illustrates the operator rule, **not an idempotent business upsert recipe**.

### 10.2. Error Example Without Array Equality

~~~javascript
arrays.updateOne(
  { _id: "new-order-without-array" },
  { $set: { "values.$[]": 0 } },
  { upsert: true }
);
// If _id does not exist: the insert branch lacks a values array
// to apply $[]; MongoDB returns an error.
~~~

Do not assume `upsert:true` will auto-create an empty array and then run `$[]`. When you need to create a new document with an initial array and update existing ones, **separate the two write paths** or design an upsert that matches the data contract.

### 10.3. Spring Data Fluent `upsert()` Does Not Bypass MongoDB's Limit

~~~java
template.update(OrderDocument.class)
    .matching(Criteria.where("id").is("o699"))
    .apply(new Update().set("lineItems.$[].reviewed", true))
    .upsert();
// If o699 does not exist, this can fail due to missing array equality.
~~~

The fluent API only changes how the update command is expressed in Java; it **does not** alter the server's requirement for `$[]` in the insert branch. In practice, if a document does not exist yet, create it with a properly structured array on insert, and then use all-positional updates in subsequent operations.

## 11. Modified Documents vs. Modified Elements

Example:

~~~javascript
const result = orders.updateMany(
  {
    tenant_id: "t01",
    state: "OPEN",
    scores: { $type: "array" }
  },
  { $inc: { "scores.$[]": 5 } }
);
~~~

On the initial data:

- `o601` has 3 scores incremented.
- `o602` has 2 scores incremented.
- **5 elements total** were modified.
- `matchedCount` is **2 documents** and `modifiedCount` is **2 documents** (assuming acknowledged writes, no concurrent writes, and no other side effects).

Reading `UpdateResult` in Java:

~~~java
UpdateResult result = template.updateMulti(
    Query.query(Criteria.where("tenantId").is("t01")
        .and("state").is("OPEN")
        .and("scores").type(4)),
    new Update().inc("scores.$[]", 5),
    OrderDocument.class
);

if (!result.wasAcknowledged()) {
    throw new IllegalStateException("Update was not acknowledged");
}

long matchedDocuments = result.getMatchedCount();
long modifiedDocuments = result.getModifiedCount();
~~~

**There is no `result.getModifiedArrayElementCount()`** in the standard update API. If business logic needs statistics on modified element counts, count array lengths/conditions before and after in a verification flow, accounting for concurrent writes and query cost; never read `modifiedCount` as element count.

### 11.1. Document Matched with No Changes

If `scores: []` is selected by the query, `$[]` has no elements to update. A raw MongoDB command can return `matchedCount=1` and `modifiedCount=0`. If `$set` assigns the same value already stored, it also produces no BSON change.

For Spring Data entities with `@Version`, automatic version updates can increment `modifiedCount` even when no array elements changed. Always check the **complete update actually sent to the server** when interpreting counts.

## 12. `@Version`, Concurrent Updates, and Idempotency

### 12.1. Auto-Incrementing Version vs. Checking Expected Version

If the entity adds:

~~~java
@Version
private Long version;
~~~

then in some mapped Spring Data MongoDB update operations, version may be auto-incremented when not specified in `Update`. However, that **does not mean the query automatically knows the version the user read**.

When preventing a stale client from updating the entire array after another writer modified the order:

~~~java
Query query = Query.query(
    Criteria.where("id").is("o601")
        .and("version").is(3L)
);

Update update = new Update()
    .set("lineItems.$[].reviewed", true);

UpdateResult result = template.updateFirst(
    query, update, VersionedOrderDocument.class
);

if (result.getMatchedCount() == 0) {
    throw new IllegalStateException("Stale order version or missing order");
}
~~~

Here `VersionedOrderDocument` is an **entity variant carrying `@Version` mapped to the same collection**, not the class declared in section 8.1. This illustrates optimistic locking; implement a concrete variant/model when using it rather than running it verbatim on an unversioned fixture.

### 12.2. `$set` Is Nearly Idempotent; `$inc` Is Not

~~~javascript
{ $set: { "line_items.$[].reviewed": true } }
// Run multiple times: reviewed remains true,
// barring other side effects/version changes.

{ $inc: { "scores.$[]": 5 } }
// Run twice: every element increases by 10 total.
~~~

When a request times out after sending a command, you cannot be sure whether the first write committed. **Blindly retrying** an `$inc` can add points twice. Design state guards, idempotency keys, event markers, or checkpoints fit for the business domain.

### 12.3. Write Conflicts on the Same Document

An update using multiple operators on **one document** is executed atomically at the document level by MongoDB. Still, two requests editing fields on the same order can race; depending on filter/version guards, the later request may write on top of the already-changed state.

When `$[]` can modify many elements at once, verify:

- Is the client allowed to modify **the entire array**?
- Are `state`/`tenant`/`version` constraints required?
- After the update, does the data still satisfy schema validation and business rules?
- Are other writers concurrently appending or removing array elements?

## 13. Transactions and Multi-Document Updates

`updateOne` with `$[]` can update many elements, yet all belong to **one document**, so single-document atomicity holds. `updateMany` with `$[]` updates multiple documents, but does not make the whole batch an atomic transaction.

~~~javascript
orders.updateMany(
  { tenant_id: "t01", state: "OPEN", line_items: { $type: "array" } },
  { $set: { "line_items.$[].reviewed": true } }
);
~~~

With multiple matching documents, each document is updated atomically on its own. If an error occurs midway, some documents may be modified while others are not. Inconsistent partial updates can leave jobs stuck mid-run.

When **all-or-nothing** across multiple documents is mandatory, evaluate MongoDB multi-document transactions and `MongoTransactionManager` (or `ReactiveMongoTransactionManager` in reactive apps) on a supported topology. Transactions carry overhead and limits; very large array-update jobs are often better served by batching, idempotency, and progress tracking.

### 13.1. Do Not Stuff Everything Into One Giant Transaction

A MongoDB document has a BSON size limit, and large arrays make updates on each document heavier. Beyond size, consider:

- Transaction hold duration and server resource usage.
- Volume of data/oplog written and replication overhead.
- Write conflicts with other requests modifying the same documents.
- Retries after errors and observability into completed batches.

For millions of documents, a batched job with checkpoints is usually more practical than one long-running transaction.

## 14. Performance: Filter Documents First, Yet `$[]` Still Modifies Every Element

Indexes help **locate target documents**, not narrow the scope of `$[]` inside the array.

Index creation example:

~~~javascript
orders.createIndex({ tenant_id: 1, state: 1 });
orders.createIndex({ "line_items.sku": 1 });
~~~

The first index supports tenant/state filters. The second is a **multikey index** helping filter documents by SKU when needed. Still, the query:

~~~javascript
orders.updateMany(
  { "line_items.sku": "A", tenant_id: "t01" },
  { $set: { "line_items.$[].reviewed": true } }
);
~~~

still updates **every line item**, not just A. An index on `line_items.sku` does not turn `$[]` into `$[line]`. If you want only A, use an array filter.

### 14.1. High Cost Even When Updating One Document

A document with 50,000 array elements forces `$[]` to touch many values inside that single document. `modifiedCount = 1` does not mean the work was cheap. For large arrays:

- Measure document size, operation latency, and array length.
- Check which indexes include modified fields, since updates must maintain indexes.
- Assess concurrent write frequency on very large documents.
- Consider extracting elements into a separate collection if elements need independent lifecycles, updates, and pagination.

### 14.2. Verify with Queries and Logs

`explain("executionStats")` on a **find query with the same filter** helps evaluate document lookup (index scan vs. collection scan), though it does not fully measure the cost of updating thousands of elements. Monitor `matchedCount`, `modifiedCount`, p95/p99 latency, bytes written, replication, and write conflicts in staging/test environments.

Never “optimize” by dropping tenant/authorization filters just to make a query faster; an under-scoped `updateMany` can modify unauthorized data.

## 15. Do Not Use `$[]` When Transforming an Array via Complex Expressions

`$[]` fits applying **one uniform operator** to every element or a sub-field of every element, such as:

~~~javascript
{ $inc: { "scores.$[]": 5 } }
{ $set: { "line_items.$[].reviewed": true } }
~~~

If elements need **conditional transformations**, use `$[identifier]` when expressible via `arrayFilters`. If you need to recompute the array structure using expressions (e.g., building new objects, type conversions, values depending on multiple fields), consider an **aggregation pipeline update** with `$map`, `$cond`, `$ifNull`, and server-supported expressions.

Example marking `reviewed` only for lines with `qty >= 3` while keeping all other fields:

~~~javascript
orders.updateOne(
  { _id: "o601" },
  [
    {
      $set: {
        line_items: {
          $map: {
            input: "$line_items",
            as: "item",
            in: {
              $mergeObjects: [
                "$$item",
                {
                  reviewed: {
                    $cond: [
                      { $gte: ["$$item.qty", 3] },
                      true,
                      "$$item.reviewed"
                    ]
                  }
                }
              ]
            }
          }
        }
      }
    }
  ]
);
// On o601: line B (qty:4) becomes true, line A (qty:2) stays false.
~~~

This is a **pipeline update**, not `$[]`. It constructs a resulting array from the original elements. Ensure `line_items` is truly an array; if missing/null, you may need `$ifNull` to normalize it. Do not pass `arrayFilters` to this pipeline update.

Spring Data MongoDB offers `AggregationUpdate` to build pipeline updates. For a simple “modify only lines with qty >= 3” requirement, `$[line]` is usually shorter, clearer, and easier to maintain.

## 16. ReactiveMongoTemplate: Operator Semantics Do Not Change

Reactive access does not alter the BSON semantics of `$[]`. Example:

~~~java
import com.mongodb.client.result.UpdateResult;
import reactor.core.publisher.Mono;
import org.springframework.data.mongodb.core.ReactiveMongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Update;

// reactiveTemplate is an injected ReactiveMongoTemplate:
Mono<UpdateResult> updateAllScores =
    reactiveTemplate.update(OrderDocument.class)
        .matching(Criteria.where("tenantId").is("t01")
            .and("state").is("OPEN")
            .and("scores").type(4))
        .apply(new Update().inc("scores.$[]", 5))
        .all();
~~~

This is a `Mono<UpdateResult>`; execution starts only when subscribed to. Never call `block()` on the WebFlux event loop. When adding retries, remember that re-subscribing to a publisher triggers **another update**, so `$inc` can double-apply unless guarded by idempotency.

Reactive `first()` updates one document; reactive `all()` updates multiple documents. Both still update **all elements** of the array in each selected document along the `$[]` path.

## 17. Integration Testing: Confirm Each Element Changed

Mocking `MongoTemplate` does not prove MongoDB interprets `$[]` correctly, verify `lineItems → line_items` mapping, or catch mistyped data. Use an isolated test MongoDB instance or Testcontainers.

### 17.1. Recommended Test Matrix

| Case | Expected Result |
| --- | --- |
| Numeric array with 3 elements | `$inc` increments all 3 elements |
| Object array A/B | `$set line_items.$[].reviewed` updates both A and B |
| Query with `line_items.sku=A` | With `$[]`, line B is still modified |
| `$[line]` + `arrayFilters` | Only lines matching the filter change |
| Empty array | No new elements added |
| Missing/null array | Error or schema normalization per design; does not auto-create array |
| Nested arrays | Two `$[]` update all packages in all shipments |
| Nested `$[]` + filtered identifier | Only packages matching the filter change |
| `updateMulti` across documents | Verify document counts; do not confuse with element counts |
| `upsert` missing array equality | Insert branch fails as expected |
| `@Field("line_items")` and `@Field("qty")` | Java/BSON paths map properly |
| `@Version` | Verify auto-version, version predicates, and retry effects |

### 17.2. Testing Directly with `MongoTemplate` and Raw BSON

The example below uses an **isolated test database**. It inserts its own fixture, updates all elements via `$[]`, and verifies via the MongoDB Java Driver:

~~~java
package com.example.arrayops;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;
import org.bson.Document;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;
import com.mongodb.client.model.Filters;

@DataMongoTest
class AllPositionalOperatorTest {
    @Autowired MongoTemplate template;

    @Test
    void updatesEveryArrayElementAndMapsAliases() {
        String id = "fixture-array-006";
        var collection = template.getDb()
            .getCollection("orders_array_demo_006");

        collection.deleteOne(Filters.eq("_id", id));
        try {
            collection.insertOne(new Document("_id", id)
                .append("tenant_id", "fixture-tenant")
                .append("state", "OPEN")
                .append("scores", List.of(10, 20, 30))
                .append("line_items", List.of(
                    new Document("sku", "A")
                        .append("qty", 2)
                        .append("reviewed", false),
                    new Document("sku", "B")
                        .append("qty", 4)
                        .append("reviewed", false)
                )));

            var scored = template.updateFirst(
                Query.query(Criteria.where("id").is(id)),
                new Update().inc("scores.$[]", 5),
                OrderDocument.class
            );
            assertThat(scored.getMatchedCount()).isEqualTo(1L);

            var reviewed = template.update(OrderDocument.class)
                .matching(Criteria.where("id").is(id))
                .apply(new Update()
                    .set("lineItems.$[].reviewed", true))
                .first();
            assertThat(reviewed.getMatchedCount()).isEqualTo(1L);

            Document raw = collection.find(
                Filters.eq("_id", id)
            ).first();
            assertThat(raw).isNotNull();
            assertThat(raw.getList("scores", Integer.class))
                .containsExactly(15, 25, 35);

            List<Document> lines =
                raw.getList("line_items", Document.class);
            assertThat(lines).hasSize(2);
            assertThat(lines.get(0).getBoolean("reviewed")).isTrue();
            assertThat(lines.get(1).getBoolean("reviewed")).isTrue();
            assertThat(raw.containsKey("lineItems")).isFalse();
        } finally {
            collection.deleteOne(Filters.eq("_id", id));
        }
    }
}
~~~

This example assumes `@DataMongoTest` configures a valid test MongoDB connection; depending on the project, Testcontainers can spin up an isolated test database. Do not run against production or shared databases: setup/cleanup deletes only the test's fixture ID.

### 17.3. Dedicated Test for “Query Matches A, Yet B Is Also Modified”

Using two lines A/B in the fixture, test two **independent** branches:

~~~java
// Branch 1 — with $[]:
template.updateFirst(
    Query.query(Criteria.where("id").is(id)
        .and("lineItems.sku").is("A")),
    new Update().set("lineItems.$[].reviewed", true),
    OrderDocument.class
);
// Both A and B have reviewed=true.
~~~

~~~java
// Branch 2 — reset fixture, then use filtered positional:
template.updateFirst(
    Query.query(Criteria.where("id").is(id)),
    new Update()
        .set("lineItems.$[line].reviewed", true)
        .filterArray(Criteria.where("line.sku").is("A")),
    OrderDocument.class
);
// A=true, B=false.
~~~

`id` is the test fixture variable from section 17.2. Do not run both branches sequentially without resetting `reviewed`, because branch 1's result would mask branch 2's difference. This is the single most important test to catch confusion between **filtering documents** and **filtering array elements**.

## 18. Common Pitfalls

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Query selects SKU A, yet SKU B also changed | `$[]` updates all elements in the matching document | Use `$[line]` + `arrayFilters` if only A is desired |
| Only one element updated | Used `$` instead of `$[]` | Pick the operator matching desired scope |
| `matchedCount=1` yet array unchanged | Empty array, same value written, or condition made no change | Inspect before/after BSON and `modifiedCount` |
| `modifiedCount=1` despite modifying 500 elements | Count is **documents** | Do not derive element count from `UpdateResult` |
| “path must exist” error | Array field is missing/null/mistyped or upsert insert lacked array equality | Normalize data, filter valid arrays; check upsert rules |
| Using `scores.$[]` on string element errors | `$inc` requires numeric elements | Validate types/schema and fix data beforehand |
| Nested path fails on legacy documents | Shipment lacks `packages` or has wrong element type | Normalize schema; use targeted filter/update |
| `filterArray("line.quantity", ...)` does not match | `arrayFilters` does not auto-map Java field aliases | Use BSON name `line.qty` |
| `Update.set("lineItems.$[].reviewed")` updates wrong path | Missing entity metadata or wrong collection/property name | Use entity-typed overload and inspect BSON |
| Multi-document update partially applied then errored | `updateMany` is not an automatic transaction | Clean schemas first, use transactions, or batch with retries |
| Upsert creates duplicate documents | Exact array equality changed after update or lacked unique key | Do not treat `$[]` upsert examples as idempotent business upserts |
| Values doubled after retry | `$inc` is not idempotent | Use state guards/idempotency keys or check outcome |
| Reactive variant never runs | `Mono` was never subscribed to | Compose into reactive pipeline; test with `StepVerifier` |
| Very slow updates on large arrays | Many elements and index entries updated in one document | Measure latency, bound array size, consider extracting a collection |

## 19. Checklist Before Using `$[]`

1. Confirm business logic truly intends to update **every element** rather than selected elements.
2. Choose **document filters** with proper ID, tenant, state, and access checks.
3. Ensure the field is a **BSON array** across all selectable documents; address missing/null/legacy records first.
4. Confirm each element's type fits the operator (`$inc` requires numbers).
5. On embedded objects, update the **sub-field** instead of replacing the entire object.
6. With nested arrays, specify which levels use `$[]` and which use `$[identifier]`.
7. In Spring Data, verify Java/BSON property mapping; remember `arrayFilters` is not auto-mapped.
8. Do not use `$[]` on the insert branch of an upsert unless exact array equality is satisfied.
9. Interpret `UpdateResult` counts as **documents**, not elements.
10. Evaluate versioning, idempotency, transactions, indexes, and array sizes.
11. Test empty arrays, missing fields, multiple elements, and partial-match queries.

## 20. Practice Exercises

Each exercise assumes the original fixture from section 2; run independently without chaining updates unless you reset test data.

### Exercise 1 — Numeric Array

`o601.scores = [70,80,90]`. Write a command incrementing **every element** by 3.

**Answer:**

~~~javascript
orders.updateOne(
  { _id: "o601" },
  { $inc: { "scores.$[]": 3 } }
);
// [73, 83, 93]
~~~

### Exercise 2 — Spot the Logic Bug

A developer writes:

~~~javascript
orders.updateOne(
  { _id: "o601", "line_items.sku": "A" },
  { $set: { "line_items.$[].reviewed": true } }
);
~~~

Question: Does line B change? **Yes.** The query only requires the order to contain an A line; `$[]` still updates both A and B. For only A, use `$[line]` with `arrayFilters`, or `$` when targeting only the first match.

### Exercise 3 — Update All A Lines

Requirement: set `reviewed = true` for **all SKU A lines**, leaving B/C untouched.

**Answer:**

~~~javascript
orders.updateMany(
  { tenant_id: "t01", line_items: { $type: "array" } },
  { $set: { "line_items.$[line].reviewed": true } },
  { arrayFilters: [{ "line.sku": "A" }] }
);
~~~

### Exercise 4 — Nested Arrays

In `o601`, mark scanned=true for every package across **all shipments**, regardless of warehouse/SKU.

**Answer:**

~~~javascript
orders.updateOne(
  { _id: "o601" },
  { $set: { "shipments.$[].packages.$[].scanned": true } }
);
~~~

If you want only package A across all warehouses, change `packages.$[]` to `packages.$[pkg]` with `arrayFilters:[{"pkg.sku":"A"}]`.

### Exercise 5 — Distinguishing Document Count from Element Count

Using the original fixture, run `updateMany` on `t01/OPEN` where `scores` is an array, incrementing every score by 5. What are `matchedCount`, `modifiedCount`, and how many scores changed?

**Answer:** `matchedCount=2`, `modifiedCount=2`, and **5 scores** changed (3 in o601 + 2 in o602), assuming no concurrent writers/other side effects and acknowledged writes.

### Exercise 6 — Missing Array and Upsert

`o605` is missing `scores`. Should you expect `{ $set: { "scores.$[]": 0 } }` to create the array automatically? If an upsert insert uses `$[]`, what must the filter include?

**Answer:** No; `$[]` requires an applicable array path. If an upsert inserts a new document, the filter must have an **exact equality match** on that array field. In normal workflows, initialize the array via a proper schema insert/set before updating.

### Exercise 7 — Spring Data Field Aliases

Java has `OrderDocument.lineItems` stored as `line_items`, and `OrderLine.quantity` stored as `qty`. Write:

1. An update setting `reviewed=true` on all lines.
2. An update setting `reviewed=true` only on lines with `qty >= 3`.

**Answer:**

~~~java
new Update().set("lineItems.$[].reviewed", true);

new Update()
    .set("lineItems.$[line].reviewed", true)
    .filterArray(Criteria.where("line.qty").gte(3));
~~~

`line.qty` inside `arrayFilters` must use the **BSON name**, because Spring Data does not auto-map that filter.

### Exercise 8 — Unsafe Retry

A request incrementing all scores with `$inc` was sent to the server, but the connection dropped before receiving the response. Should the client immediately retry the same command?

**Answer:** Do not retry blindly. The first attempt may have succeeded; resending would increment a second time. Design idempotency keys, state conditions, or business verification/reconciliation.

## References

- [MongoDB Manual — `$[]` All Positional Operator](https://www.mongodb.com/docs/manual/reference/operator/update/positional-all/): syntax, scope, nested arrays, upsert exact array equality rule.
- [MongoDB Manual — `$` Positional Operator](https://www.mongodb.com/docs/manual/reference/operator/update/positional/): first matching element, positional `$` limitations.
- [MongoDB Manual — `$[identifier]` Filtered Positional Operator](https://www.mongodb.com/docs/manual/reference/operator/update/positional-filtered/): `arrayFilters` and per-element filtering.
- [MongoDB Manual — Update Operators](https://www.mongodb.com/docs/manual/reference/mql/update/): distinguishing `$set`, `$inc`, `$pull`, and positional operators.
- [MongoDB Manual — `updateMany()`](https://www.mongodb.com/docs/manual/reference/method/db.collection.updatemany/): `arrayFilters` option, update results, and atomicity.
- [Spring Data MongoDB — Saving, Updating, and Removing Documents](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-crud-operations.html): `MongoTemplate`, `Update`, fluent updates, and versioning.
- [Spring Data MongoDB — `Update` API](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/query/Update.html): `set`, `inc`, `filterArray`, and non-mapping note for array filters.
- [Spring Data MongoDB — `MongoOperations` API](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/MongoOperations.html): `updateFirst`/`updateMulti` and fluent equivalents.
- [MongoDB Manual — Atomicity and Transactions](https://www.mongodb.com/docs/manual/core/write-operations-atomicity/): document-level atomicity and limits of multi-document updates.
