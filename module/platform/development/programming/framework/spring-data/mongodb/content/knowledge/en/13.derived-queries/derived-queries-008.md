# Querying Collections, Embedded Documents, and Element-Matching Limits

> **Chapter:** Derived Queries  
> **Module:** `SPRING_DATA_MONGODB` — document mapping, querying MongoDB via repositories or `MongoTemplate`, plus testing and performance diagnostics.  
> **Objective:** Write derived queries on properties of embedded documents and arrays; understand how MongoDB matches array elements; recognize when `And` does not mean "same element"; switch to `$elemMatch`, `@Query`, or `MongoTemplate` when exact element-level constraints are required.

## 1. At What Level Do Derived Queries Operate?

Spring Data MongoDB can derive queries from repository method names, such as:

~~~java
List<OrderDocument> findByState(String state);
List<OrderDocument> findByShippingAddressCity(String city);
List<OrderDocument> findByLinesSku(String sku);
~~~

Spring Data parses everything after `By` into **Java property paths** and operators (`And`, `GreaterThan`, `In`, …), then maps them to BSON queries targeting the entity's **MongoDB collection**. For example:

| Repository method | Semantically equivalent MongoDB condition |
| --- | --- |
| `findByState("OPEN")` | `{ state: "OPEN" }` |
| `findByShippingAddressCity("Hà Nội")` | `{ "shippingAddress.city": "Hà Nội" }` |
| `findByLinesSku("A")` | `{ "lines.sku": "A" }` |
| `findByLinesQuantityGreaterThan(5)` | `{ "lines.quantity": { $gt: 5 } }` |

A `MongoRepository<OrderDocument, String>` operates on the **collection** declared by `@Document(collection = "...")`, and never automatically joins another collection just because a method traverses a reference property. In this lesson, the term **collection** also refers to Java `List`/array fields stored as **BSON arrays**. Distinguish the two clearly:

- **MongoDB collection**: a group of documents under one collection name, e.g., `orders_derived_demo_008`.
- **Collection-valued property**: a field such as `List<OrderLine> lines` or `List<String> tags` stored *inside* a document.

Derived queries return the **root documents** matching the filter. If a query matches one element inside `lines`, the returned `OrderDocument` still carries the entire `lines` array unless you explicitly configure a projection or aggregation.

## 2. Dataset Used Throughout This Lesson

In `mongosh`, seed data into an **isolated test database**. Fixed IDs are for illustration only; do not re-run `insertMany` on the same collection while documents remain present.

~~~javascript
use spring_data_mongodb_lab

const orders = db.orders_derived_demo_008;

orders.insertMany([
  {
    _id: "o001",
    state: "OPEN",
    shippingAddress: { city: "Hà Nội", district: "Cầu Giấy" },
    tags: ["online", "priority"],
    lines: [
      { sku: "A", quantity: 1, unitPriceVnd: 120000 },
      { sku: "B", quantity: 8, unitPriceVnd: 20000 }
    ],
    createdAt: ISODate("2026-10-01T08:00:00Z")
  },
  {
    _id: "o002",
    state: "OPEN",
    shippingAddress: { city: "Hồ Chí Minh", district: "Quận 1" },
    tags: ["online"],
    lines: [
      { sku: "A", quantity: 6, unitPriceVnd: 120000 },
      { sku: "C", quantity: 1, unitPriceVnd: 45000 }
    ],
    createdAt: ISODate("2026-10-02T08:00:00Z")
  },
  {
    _id: "o003",
    state: "PAID",
    shippingAddress: { city: "Hà Nội", district: "Ba Đình" },
    tags: ["store"],
    lines: [
      { sku: "B", quantity: 7, unitPriceVnd: 20000 }
    ],
    createdAt: ISODate("2026-10-03T08:00:00Z")
  },
  {
    _id: "o004",
    state: "DRAFT",
    shippingAddress: { city: "Đà Nẵng", district: "Hải Châu" },
    tags: [],
    lines: [],
    createdAt: ISODate("2026-10-04T08:00:00Z")
  },
  {
    _id: "o005",
    state: "OPEN",
    shippingAddress: { city: "Hà Nội", district: "Đống Đa" },
    tags: ["priority"],
    lines: [
      { sku: "A", quantity: 3, unitPriceVnd: 120000 },
      { sku: "A", quantity: 9, unitPriceVnd: 120000 }
    ],
    createdAt: ISODate("2026-10-05T08:00:00Z")
  }
]);

orders.find({}, { _id: 1, state: 1, lines: 1 }).sort({ _id: 1 });
~~~

Purpose of each document in the dataset:

| Order | City | Line items | What it tests |
| --- | --- | --- | --- |
| `o001` | Hà Nội | A × 1; B × 8 | Has A and has a high-quantity line, **but not an A line with high quantity** |
| `o002` | Hồ Chí Minh | A × 6; C × 1 | Has A with high quantity on a single line |
| `o003` | Hà Nội | B × 7 | Does not contain A |
| `o004` | Đà Nẵng | No line items | Empty array |
| `o005` | Hà Nội | A × 3; A × 9 | Two A lines, one meeting the threshold |

Subsequent queries assume this initial dataset. If you modify the collection during practice, recalculate expected results accordingly.

## 3. Mapping Embedded Documents in Spring Data MongoDB

An order contains **a single embedded object** `shippingAddress` and **an array of embedded objects** `lines`. To MongoDB, these are two distinct structures:

~~~text
OrderDocument
├── _id: "o001"
├── shippingAddress: { city, district }     ← single embedded document
├── tags: ["online", "priority"]             ← scalar array
└── lines: [                                  ← array of embedded documents
      { sku: "A", quantity: 1 },
      { sku: "B", quantity: 8 }
    ]
~~~

### 3.1. Entity Declarations

Each snippet below represents a Java file in package `com.example.derived`.

~~~java
// ShippingAddress.java
package com.example.derived;

public class ShippingAddress {
    private String city;
    private String district;

    protected ShippingAddress() {}

    public ShippingAddress(String city, String district) {
        this.city = city;
        this.district = district;
    }

    public String getCity() { return city; }
    public String getDistrict() { return district; }
}
~~~

~~~java
// OrderLine.java
package com.example.derived;

public class OrderLine {
    private String sku;
    private int quantity;
    private long unitPriceVnd;

    protected OrderLine() {}

    public OrderLine(String sku, int quantity, long unitPriceVnd) {
        this.sku = sku;
        this.quantity = quantity;
        this.unitPriceVnd = unitPriceVnd;
    }

    public String getSku() { return sku; }
    public int getQuantity() { return quantity; }
    public long getUnitPriceVnd() { return unitPriceVnd; }
}
~~~

~~~java
// OrderDocument.java
package com.example.derived;

import java.time.Instant;
import java.util.List;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.mapping.MongoId;

@Document(collection = "orders_derived_demo_008")
public class OrderDocument {
    @MongoId(FieldType.STRING)
    private String id;

    private String state;
    private ShippingAddress shippingAddress;
    private List<String> tags;
    private List<OrderLine> lines;
    private Instant createdAt;

    protected OrderDocument() {}

    public String getId() { return id; }
    public String getState() { return state; }
    public ShippingAddress getShippingAddress() { return shippingAddress; }
    public List<String> getTags() { return tags; }
    public List<OrderLine> getLines() { return lines; }
    public Instant getCreatedAt() { return createdAt; }
}
~~~

`ShippingAddress` and `OrderLine` do not need `@Document` when stored solely **embedded** inside orders. `@MongoId(FieldType.STRING)` keeps `_id` as a BSON String, avoiding implicit conversion of hex strings to `ObjectId` as can occur with default `@Id String`.

### 3.2. Base Repository

~~~java
// OrderRepository.java
package com.example.derived;

import java.util.List;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface OrderRepository
        extends MongoRepository<OrderDocument, String> {

    List<OrderDocument> findByState(String state);

    List<OrderDocument> findByShippingAddressCity(String city);

    List<OrderDocument> findByLinesSku(String sku);

    List<OrderDocument> findByLinesQuantityGreaterThan(int quantity);

    List<OrderDocument> findByLinesSkuAndLinesQuantityGreaterThan(
        String sku, int quantity
    );

    List<OrderDocument> findByTags(String tag);

    Page<OrderDocument> findByState(String state, Pageable pageable);
}
~~~

Methods are **derived from their names** by Spring Data when the repository proxy is built. If a Java path is wrong (e.g., `ShippingCity` when the entity only has `shippingAddress.city`), startup can fail during repository initialization with a property-path error; this differs from MongoDB returning empty results.

## 4. Single Embedded Document: Querying by Property Path

### 4.1. Dot Notation in MongoDB

To find orders shipping to Hà Nội:

~~~javascript
orders.find({ "shippingAddress.city": "Hà Nội" });
// Result on initial data: o001, o003, o005.
~~~

Corresponding derived query:

~~~java
List<OrderDocument> hanoi =
    repository.findByShippingAddressCity("Hà Nội");
// Expected to contain o001, o003, o005 (order not guaranteed).
~~~

Spring Data splits `ShippingAddressCity` into Java path `shippingAddress.city`, then translates field names into BSON paths on execution.

Do not write the query like this when matching a child property:

~~~javascript
orders.find({ shippingAddress: { city: "Hà Nội" } });
~~~

Matching an **entire subdocument** requires all fields and field ordering in the filter document to match the stored document. Since the sample documents also have `district`, a filter containing only `city` will miss all three orders above. Always use dot notation when filtering on one or a subset of child fields.

### 4.2. Combining Criteria Inside and Outside the Subdocument

~~~java
List<OrderDocument> findByStateAndShippingAddressCity(
    String state, String city
);
~~~

Meaning:

~~~javascript
orders.find({
  state: "OPEN",
  "shippingAddress.city": "Hà Nội"
});
// Result: o001 and o005.
~~~

`And` joins **independent conditions on the same order**. Because `shippingAddress` is a single embedded object, there is no question of "whether two criteria match the same array element".

### 4.3. Resolving Ambiguous Property Paths

Spring Data Commons attempts to resolve direct properties first before splitting camelCase segments. If an entity has both `shippingAddress` and `shippingAddressCity`, `findByShippingAddressCity` will resolve to the direct `shippingAddressCity` property.

To specify the split point explicitly, use `_`:

~~~java
List<OrderDocument> findByShippingAddress_City(String city);
~~~

The underscore here is a **parser hint for splitting Java paths**, not a literal character required in BSON. When no property-name conflict exists, the shorter `findByShippingAddressCity` is often easier to read.

If you annotate `shippingAddress` with `@Field("shipping_address")`, the method name still uses **Java property names**, while the converter maps the path to `shipping_address.city`. When investigating unexpected results, check both Java names and actual BSON names.

## 5. Collection Fields: Matching One Element via Dot Notation

Because `lines` is `List<OrderLine>`, this query:

~~~javascript
orders.find({ "lines.sku": "A" });
// Result: o001, o002, o005.
~~~

means the `lines` array has **at least one element** with `sku: "A"`. Corresponding derived method:

~~~java
List<OrderDocument> containingSkuA =
    repository.findByLinesSku("A");
~~~

Similarly:

~~~javascript
orders.find({ "lines.quantity": { $gt: 5 } });
// Result: o001 (B×8), o002 (A×6), o003 (B×7), o005 (A×9).
~~~

~~~java
List<OrderDocument> someLineHasLargeQuantity =
    repository.findByLinesQuantityGreaterThan(5);
~~~

Traversing `List<OrderLine>` maps to dotted paths such as `"lines.sku"`. MongoDB returns **documents where at least one element** satisfies the condition; the repository does not return only the matched `OrderLine`.

### 5.1. Scalar Arrays: Matching a Value Inside an Array

`tags` is `List<String>`, not an embedded document array:

~~~javascript
orders.find({ tags: "priority" });
// Result: o001, o005.
~~~

For equality on a scalar array field, MongoDB matches if **any element equals the value**. A derived query:

~~~java
List<OrderDocument> priorityOrders =
    repository.findByTags("priority");
~~~

has the same meaning for `tags` in this model. It differs from comparing the entire array `tags: ["priority"]`, which requires an exact array match.

With `Containing`, interpret based on **property type**: `findByNameContaining("abc")` on `String` normally generates a regex search, whereas `Containing` on a `Collection` involves membership testing. Do not assume `Containing` shares one single behavior across all data types.

## 6. Central Trap: `And` Can Match **Two Different Elements**

Suppose the business requirement is:

> Find orders containing **a line item with SKU A and quantity greater than 5**.

Someone might write:

~~~java
List<OrderDocument> findByLinesSkuAndLinesQuantityGreaterThan(
    String sku, int quantity
);
~~~

and invoke:

~~~java
var results = repository
    .findByLinesSkuAndLinesQuantityGreaterThan("A", 5);
~~~

Spring Data derives the semantically equivalent filter:

~~~javascript
orders.find({
  "lines.sku": "A",
  "lines.quantity": { $gt: 5 }
});
~~~

**Common misconception:** MongoDB does not force these two dot-notation conditions to match the **same `lines` element**. One element can satisfy `sku = A`, while a different element satisfies `quantity > 5`.

| Order | Has an element with SKU A? | Has an element with quantity > 5? | Derived query with `And` | Has **same line A** with quantity > 5? |
| --- | --- | --- | --- | --- |
| `o001` | Yes, A × 1 | Yes, B × 8 | **Yes** | **No** |
| `o002` | Yes, A × 6 | Yes, A × 6 | Yes | Yes |
| `o003` | No | Yes, B × 7 | No | No |
| `o004` | No | No | No | No |
| `o005` | Yes, A × 3 / A × 9 | Yes, A × 9 | Yes | Yes |

The derived query returns **o001, o002, o005**. Yet the **correct answer for the same-line requirement** is only **o002, o005**.

Diagram illustrating `o001`:

~~~text
Order o001
lines[0] = { sku: "A", quantity: 1 }   ← satisfies lines.sku = "A"
lines[1] = { sku: "B", quantity: 8 }   ← satisfies lines.quantity > 5

Both conditions hold across the whole order.
No individual element satisfies both at once.
~~~

### 6.1. `And` in a Method Name Is Not `$elemMatch`

`And` expresses a logical conjunction between **document-level query predicates**. It does not scope both predicates to the same array index/element. Even rewriting it as:

~~~javascript
orders.find({
  $and: [
    { "lines.sku": "A" },
    { "lines.quantity": { $gt: 5 } }
  ]
});
~~~

still returns `o001`. `$and` merely combines predicates; it does not enforce "same element".

Whenever multiple criteria must hold on **a single embedded object inside an array**, use `$elemMatch`.

## 7. Using `$elemMatch` to Constrain a Single Element

### 7.1. Standard MongoDB Query

~~~javascript
orders.find({
  lines: {
    $elemMatch: {
      sku: "A",
      quantity: { $gt: 5 }
    }
  }
});
// Result: o002 and o005. o001 is excluded.
~~~

`$elemMatch` requires **at least one element of the `lines` array** to satisfy **all conditions inside it**. Here `sku` and `quantity` belong to **one `OrderLine`**, not independent branches across the whole order.

An extra benefit: `$elemMatch` only matches **arrays**. If corrupt data accidentally stored `lines` as a single object, dot notation might still match `lines.sku`, whereas `$elemMatch` will not treat a non-array object as a valid array.

### 7.2. Writing `@Query` in the Repository

When a derived query cannot express element-level scope accurately, declare an explicit BSON query:

~~~java
package com.example.derived;

import java.util.List;
import org.springframework.data.mongodb.repository.MongoRepository;
import org.springframework.data.mongodb.repository.Query;

public interface OrderRepository
        extends MongoRepository<OrderDocument, String> {

    @Query(
        "{ 'lines': { '$elemMatch': { " +
        "  'sku': ?0, " +
        "  'quantity': { '$gt': ?1 }" +
        "} } }"
    )
    List<OrderDocument> findHavingLineWithQuantityGreaterThan(
        String sku, int minExclusive
    );
}
~~~

This is an **abbreviated version** of `OrderRepository` from Section 3: in a real project, add the `@Query` import and the new method to the **same existing interface** rather than creating two interfaces with the same name in one package.

Usage:

~~~java
List<OrderDocument> result =
    repository.findHavingLineWithQuantityGreaterThan("A", 5);
// Expected: o002, o005.
~~~

In `@Query`, `?0` and `?1` bind positional arguments (0-based). Spring Data handles parameter binding and string escaping, so never manually concatenate user input into query JSON. The method name `findHavingLineWithQuantityGreaterThan` is **not derived** here because `@Query` supplies the MongoDB query directly.

Limitation to remember: `@Query` returns **whole order documents** under default mapping. `$elemMatch` in the **filter** only selects which orders are returned; **it does not slice the `lines` array down to matching elements**.

### 7.3. Writing with `MongoTemplate` and `Criteria.elemMatch`

~~~java
import java.util.List;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

// Inside a service with injected MongoTemplate template:
Criteria oneLine = Criteria.where("sku").is("A")
    .and("quantity").gt(5);

Query query = Query.query(
    Criteria.where("lines").elemMatch(oneLine)
);

List<OrderDocument> result =
    template.find(query, OrderDocument.class);
// Expected: o002, o005.
~~~

`Criteria.where("lines").elemMatch(...)` generates the same MongoDB operator. This style is helpful when building queries dynamically across optional filters, or when adding projections, sorting, and pagination.

### 7.4. Combining Order-Level Conditions with Single-Line Conditions

~~~javascript
orders.find({
  state: "OPEN",
  "shippingAddress.city": "Hà Nội",
  lines: {
    $elemMatch: {
      sku: "A",
      quantity: { $gt: 5 }
    }
  }
});
// Initial data: only o005.
~~~

Equivalent via `MongoTemplate`:

~~~java
Criteria criteria = Criteria.where("state").is("OPEN")
    .and("shippingAddress.city").is("Hà Nội")
    .and("lines")
    .elemMatch(
        Criteria.where("sku").is("A")
            .and("quantity").gt(5)
    );

List<OrderDocument> found = template.find(
    Query.query(criteria),
    OrderDocument.class
);
~~~

Here `state` and `shippingAddress.city` filter at the **order** level, while `sku`/`quantity` filter within **one element of `lines`**. Understanding scope boundaries is central when designing queries on embedded documents.

## 8. Limitations of Array Queries

### 8.1. Distinguishing "One Element" from "Two Elements"

If the requirement is "orders having SKU A **and** SKU B, not necessarily on the same line", use:

~~~javascript
orders.find({
  "lines.sku": { $all: ["A", "B"] }
});
// On initial data: o001.
~~~

`$all` suits matching multiple values in an **array**. On `"lines.sku"` across embedded documents, the query checks that the set of SKU values contains both A and B; each value can come from a different element. A single line normally cannot have `sku` equal to both A and B simultaneously.

To find orders **having one A line > 5 and one B line > 5**, use two `$elemMatch` expressions on the same array combined with `$and`:

~~~javascript
orders.find({
  $and: [
    { lines: { $elemMatch: { sku: "A", quantity: { $gt: 5 } } } },
    { lines: { $elemMatch: { sku: "B", quantity: { $gt: 5 } } } }
  ]
});
// On initial data: no order satisfies both.
~~~

Two independent `$elemMatch` clauses can match two different elements, matching the requirement of having **two kinds of line items**.

### 8.2. Which Array Level Does `$elemMatch` Target?

Consider nested arrays:

~~~javascript
{
  _id: "nested-001",
  shipments: [
    {
      warehouse: "HN",
      packages: [
        { sku: "A", quantity: 1 },
        { sku: "B", quantity: 8 }
      ]
    }
  ]
}
~~~

To find "a shipment from HN containing **a package of A > 5**", place `$elemMatch` at each corresponding level:

~~~javascript
db.nested_orders_demo_008.find({
  shipments: {
    $elemMatch: {
      warehouse: "HN",
      packages: {
        $elemMatch: {
          sku: "A",
          quantity: { $gt: 5 }
        }
      }
    }
  }
});
// The sample document above does not match.
~~~

The outer `$elemMatch` binds fields within **one shipment**. The inner `$elemMatch` binds `sku` and `quantity` within **one package**. Each operator scopes to its own array level.

This snippet uses a separate collection to show syntax; to execute it, insert the document into `nested_orders_demo_008` first. Avoid altering the main sample dataset just to test an unrelated structure.

### 8.3. `$elemMatch` Filter vs. `$elemMatch` Projection

~~~javascript
// Filter: selects orders with at least one A line having quantity > 5.
orders.find({
  lines: { $elemMatch: { sku: "A", quantity: { $gt: 5 } } }
});
~~~

That query returns the **entire `lines` array** of matching orders. To include only the **first matching element** in the response, use `$elemMatch` projection:

~~~javascript
orders.find(
  { _id: "o005" },
  {
    lines: {
      $elemMatch: { sku: "A", quantity: { $gt: 5 } }
    }
  }
);
// Only line A×9 is included in the returned lines array.
~~~

This projection **does not return all matching elements** if multiple lines qualify. To produce an array containing every matching element, consider aggregation `$filter`. That is **result transformation**, distinct from finding orders satisfying a predicate.

### 8.4. Whole-Subdocument Matching Can Depend on Field Order

~~~javascript
// Matches an embedded document against a value having only 2 fields.
orders.find({
  lines: {
    sku: "A",
    quantity: 6
  }
});
~~~

Here `lines` holds subdocuments that also contain `unitPriceVnd`. Whole-document equality requires exact field structure and field ordering, so it cannot replace partial field matching. Use dot notation or `$elemMatch` to query a subset of subdocument fields rather than ad-hoc object equality.

### 8.5. `Not` and Null on Arrays Are Easily Misread

Questions like "has no SKU A line", "has a non-A line", and "only has non-A lines" are **not equivalent**. For instance:

~~~javascript
// No lines.sku element equals A; can match orders with empty lines.
orders.find({ "lines.sku": { $ne: "A" } });
~~~

This differs from:

~~~javascript
// At least one lines element has sku != A.
orders.find({
  lines: { $elemMatch: { sku: { $ne: "A" } } }
});
~~~

`o001` has both A and B: the first query **excludes** it, while the second query **includes** it (via line B). Never guess the meaning of `Not` in method names from English phrasing; verify actual BSON semantics, especially with arrays and missing fields.

## 9. Sorting, Pagination, and Array Results

Repositories can combine derived queries with `Pageable`:

~~~java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;

Page<OrderDocument> page = repository.findByState(
    "OPEN",
    PageRequest.of(
        0, 2,
        Sort.by(Sort.Order.desc("createdAt"), Sort.Order.asc("id"))
    )
);
~~~

`Page<OrderDocument>` paginates **order documents**, not elements inside `lines`. `totalElements` counts matching orders (and may issue a count query). Calling `findByLinesSku("A", pageable)` returns pages of orders containing SKU A, not individual `OrderLine` pages.

Never assume order ordering without an explicit sort. When paginating, add a deterministic tie-breaker such as `_id` to reduce duplicates or skipped items when documents share `createdAt`.

When sorting directly on an array field like `lines.quantity`, MongoDB applies element-selection rules across array items, which may differ from "sort by the quantity of line A". To sort by a **specific line A**, you generally need aggregation to extract the relevant sort value before sorting.

## 10. Multikey Indexes and Query Performance

MongoDB supports **multikey indexes** whenever an indexed field contains an array. Examples:

~~~javascript
orders.createIndex({ "shippingAddress.city": 1 });
orders.createIndex({ "lines.sku": 1 });
~~~

The `"shippingAddress.city"` index serves queries on the embedded object. The `"lines.sku"` index becomes multikey because `lines` is an array, accelerating SKU lookups.

### 10.1. Compound Multikey Index for Same Line Item

If you frequently search by **SKU and quantity on the same line**:

~~~javascript
orders.createIndex({
  "lines.sku": 1,
  "lines.quantity": 1
});
~~~

Because both fields belong to the **`lines` array**, a compound multikey index can be helpful. Furthermore, constraining **the same element** with `$elemMatch` impacts how MongoDB **intersects index bounds**.

~~~javascript
orders.find({
  lines: {
    $elemMatch: {
      sku: "A",
      quantity: { $gt: 5 }
    }
  }
}).explain("executionStats");
~~~

With separate dot-notation predicates without `$elemMatch`, MongoDB cannot assume both criteria apply to a single element to tighten index bounds the way it can with `$elemMatch`. Hence this distinction impacts both **business correctness** and **performance**.

### 10.2. Not Every Compound Index Across Two Array Fields Is Valid

MongoDB restricts compound multikey indexes: a document cannot simultaneously contain **two separate indexed array fields** in ways that violate the "parallel arrays" limit. For instance, an index combining `tags` and `lines.sku` requires careful validation because both can be arrays.

With `"lines.sku"` and `"lines.quantity"`, both paths stem from the same embedded-document array `lines`, so test and evaluate it under **compound bounds for the same array**. Do not apply scalar index intuition blindly to nested arrays.

### 10.3. Measure Before Optimizing

When inspecting `explain("executionStats")`, check:

- `winningPlan`: does it use an index (`IXSCAN`) or scan the collection (`COLLSCAN`)?
- `totalKeysExamined` and `totalDocsExamined`: how many index keys and documents were inspected?
- `nReturned`: how many orders were actually returned?
- Was an in-memory sort stage required?

The goal is not indexing **every** path; each index adds write overhead and storage cost. Choose indexes based on high-frequency queries, selectivity, and benchmarks on representative datasets.

## 11. Limits of Derived Queries and When Other APIs Are Needed

| Requirement | Derived query | Recommended approach |
| --- | --- | --- |
| Filter orders by `state` | Clear | `findByState` |
| Filter by `shippingAddress.city` | Clear | `findByShippingAddressCity` |
| **Any** line has SKU A | Clear | `findByLinesSku` |
| Has an SKU A line **and** a line with quantity > 5, possibly different lines | Expressible with `And` | `findByLinesSkuAndLinesQuantityGreaterThan` |
| Has **the same line** with SKU A and quantity > 5 | Method name easily misleads | `@Query` + `$elemMatch` or `Criteria.elemMatch` |
| Multiple conditions inside nested arrays | Hard to express safely | `MongoTemplate`/`@Query` with nested `$elemMatch` |
| Return only matching line items | Derived filter cannot slice arrays | Aggregation `$filter` or suitable projection |
| Sum quantities per SKU across orders | Not a simple filter | Aggregation `$unwind`, `$match`, `$group` |
| Combine documents across two collections | Not simple property traversal | `$lookup`, two-step queries, or appropriate embedding |

Use derived query names when **the condition meaning reads unambiguously**. For a "same element" rule, `findByLinesSkuAndLinesQuantityGreaterThan` misleads reviewers into believing both conditions bind to one element even though the generated query lacks `$elemMatch`. In such cases, an explicit `@Query` is far safer.

### 11.1. Do Not Mechanically Replace `$elemMatch` with Query by Example

Spring Data supports `Query by Example` to query from a probe object. However, QBE has its own matcher scope and limitations; never assume placing an `OrderLine` inside a probe makes MongoDB bind all its fields to **the same element** like `$elemMatch`. When array semantics matter, inspect the actual query or use an API that expresses `$elemMatch` explicitly.

### 11.2. Reactive Repositories Share the Same MongoDB Semantics

~~~java
import org.springframework.data.mongodb.repository.ReactiveMongoRepository;
import reactor.core.publisher.Flux;

public interface ReactiveOrderRepository
        extends ReactiveMongoRepository<OrderDocument, String> {

    Flux<OrderDocument> findByLinesSku(String sku);
}
~~~

Returning `Flux<OrderDocument>` only changes the **asynchronous execution model**; it does not alter dot notation or `$elemMatch` semantics. If a reactive query must match the same element, still use `@Query` or `ReactiveMongoTemplate` with `Criteria.elemMatch`. Publishers execute only when subscribed to in a reactive pipeline.

## 12. Troubleshooting and Testing

### 12.1. Common Mistakes

| Symptom | Possible cause | How to verify |
| --- | --- | --- |
| `findByShippingAddressCity` fails at startup | Missing Java property `shippingAddress.city` or parser picked wrong path | Inspect model; use `ShippingAddress_City` to disambiguate |
| City query returns empty | Wrong BSON name/alias, wrong type, wrong database or collection | Compare with `mongosh` and `@Field` mappings |
| `findByLinesSku("A")` returns orders also holding line B | Derived query filters orders, does not project matching lines only | Inspect the full `lines` array of returned orders |
| `And` returns `o001` despite A having quantity 1 | Both predicates matched different array elements | Switch to `$elemMatch` |
| `$elemMatch` fails on documents where `lines` is a single object | `$elemMatch` only matches arrays | Audit schema/type of `lines` and fix malformed documents |
| Mongo query succeeds yet repository returns unexpected data | Converter/mapping BSON type mismatch or wrong repository | Verify property paths, `@Document`, `@MongoId`, and generated query |
| Fast on tiny data, slow in production | Missing multikey index or scanning too many documents | Run `explain("executionStats")` and design indexes for predicates |
| `@Query` returns matching orders without slicing `lines` | `$elemMatch` was in filter, not projection | Use `$elemMatch` projection or aggregation `$filter` |
| Sorting by `lines.quantity` seems unpredictable | Each order has multiple quantities | Compute an explicit sort key via aggregation |

### 12.2. Mandatory Tests Separating the Two Cases

A common mistake is writing unit tests where orders contain only a single `lines` element. Both the derived query and `$elemMatch` return the exact same result, hiding the bug. Tests should include at least:

1. **Cross-element trap:** order `o001` with A×1 and B×8. The `And` derived query **matches**, while `$elemMatch` **does not**.
2. **Same-element match:** order `o002` with A×6. Both queries match.
3. **Multiple elements with same SKU:** order `o005` with A×3, A×9. `$elemMatch` matches via A×9.
4. **Empty array:** order `o004` with empty line items; does not match.
5. **Wrong type / missing array:** only add fixtures in an isolated test collection if the domain permits non-standard legacy documents.

### 12.3. Integration Test with Real MongoDB or Testcontainers

The example below uses `OrderRepository` with the `@Query` method from Section 7.2 against an isolated test MongoDB:

~~~java
package com.example.derived;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;
import org.bson.Document;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.data.mongodb.core.MongoTemplate;

@SpringBootTest
class EmbeddedArrayQueryTest {
    @Autowired MongoTemplate template;
    @Autowired OrderRepository repository;

    @Test
    void elemMatchExcludesCrossElementFalsePositive() {
        // Run against an isolated test MongoDB and test-only collection.
        var collection = template.getDb()
            .getCollection("orders_derived_demo_008");

        collection.deleteMany(new Document("_id", new Document("$in",
            List.of("test-cross-008", "test-same-008"))));

        try {
            collection.insertOne(new Document("_id", "test-cross-008")
                .append("state", "OPEN")
                .append("lines", List.of(
                    new Document("sku", "A").append("quantity", 1),
                    new Document("sku", "B").append("quantity", 8)
                )));

            collection.insertOne(new Document("_id", "test-same-008")
                .append("state", "OPEN")
                .append("lines", List.of(
                    new Document("sku", "A").append("quantity", 6)
                )));

            var broad = repository
                .findByLinesSkuAndLinesQuantityGreaterThan("A", 5)
                .stream().map(OrderDocument::getId).toList();

            var precise = repository
                .findHavingLineWithQuantityGreaterThan("A", 5)
                .stream().map(OrderDocument::getId).toList();

            assertThat(broad).contains("test-cross-008", "test-same-008");
            assertThat(precise).contains("test-same-008");
            assertThat(precise).doesNotContain("test-cross-008");
        } finally {
            collection.deleteMany(new Document("_id", new Document("$in",
                List.of("test-cross-008", "test-same-008"))));
        }
    }
}
~~~

This test needs a live repository in `ApplicationContext`, a test database, and converters matching the entity. On an empty test collection, even if extra fixtures match SKU A, `contains`/`doesNotContain` remain valid since they check specific IDs. In real projects, prefer a **dedicated test collection** so other data is untouched; the setup cleanup deletes only those two fixture IDs and is strictly for isolated test environments.

The core requirement is verifying the **MongoDB query engine** and **Spring Data mapping** for real. Mocked repositories cannot reproduce two array predicates matching two different elements.

### 12.4. Inspecting Queries and Execution Plans

When suspecting a misgenerated query, reproduce the filter in `mongosh` first:

~~~javascript
// Broad: can match across different elements.
orders.find({
  "lines.sku": "A",
  "lines.quantity": { $gt: 5 }
}, { _id: 1 });

// Exact: same element.
orders.find({
  lines: { $elemMatch: { sku: "A", quantity: { $gt: 5 } } }
}, { _id: 1 });
~~~

Only after confirming the result set should you analyze indexes via `explain("executionStats")`. Never tweak indexes to fix a **semantic bug** in a query; indexes speed up execution, not turn `And` into `$elemMatch`.

## 13. Hands-on Exercises

### Exercise 1 — Single Embedded Document

Find all `OPEN` orders shipping to Hà Nội.

**Suggested solution:**

~~~java
List<OrderDocument> findByStateAndShippingAddressCity(
    String state, String city
);
~~~

Calling `findByStateAndShippingAddressCity("OPEN", "Hà Nội")` returns **o001, o005** on the initial dataset.

### Exercise 2 — Evaluating a Derived Query

Given the method:

~~~java
List<OrderDocument> findByLinesSkuAndLinesQuantityGreaterThan(
    String sku, int quantity
);
~~~

With `("A", 5)`, does the query return `o001`? **Yes.** Line A×1 and line B×8 satisfy the two separate predicates on the same order. Explain why it fails the requirement "a line A×n with n > 5".

### Exercise 3 — Rewriting the Exact Condition

Write a `mongosh` query selecting orders that have an A line with quantity `>= 5`.

**Solution:**

~~~javascript
orders.find({
  lines: {
    $elemMatch: {
      sku: "A",
      quantity: { $gte: 5 }
    }
  }
});
// Result: o002 and o005.
~~~

When translating to Spring Data, use `@Query` with `$elemMatch` or `Criteria.where("lines").elemMatch(...)`; remember to change `$gt` to `$gte` per the requirement.

### Exercise 4 — One Element or Two Elements?

Find orders containing **both an SKU A line and an SKU B line**, not necessarily on the same line. Which condition fits?

**Solution:**

~~~javascript
orders.find({
  "lines.sku": { $all: ["A", "B"] }
});
// Result: o001.
~~~

This asks about **two values across the line-item set**; never put `sku: "A"` and `sku: "B"` together inside a single `$elemMatch`.

### Exercise 5 — Projecting Array Elements

To find orders containing an A line with quantity > 5, returning only the **first matching line** instead of the whole array, what should you use?

**Solution:** use `$elemMatch` in **projection** alongside the filter; to retrieve all matching lines, use aggregation `$filter`. Separate filter criteria from response transformation when choosing an API.

### Exercise 6 — Performance Diagnostics

A frequent query is "SKU A with quantity > 5 on the same line". Propose an index and explain how to verify effectiveness.

**Reference solution:** consider a compound multikey index `{ "lines.sku": 1, "lines.quantity": 1 }`; use `$elemMatch` on `lines` and measure `explain("executionStats")` on representative data. Compare `keysExamined`, `docsExamined`, and `nReturned` before/after while accounting for index write overhead.

## References

- [Spring Data MongoDB — MongoDB-specific Query Methods](https://docs.spring.io/spring-data/mongodb/reference/mongodb/repositories/query-methods.html): derived keywords, `Containing`, `@Query`, and repository method limits.
- [Spring Data Commons — Defining Query Methods](https://docs.spring.io/spring-data/commons/reference/repositories/query-methods-details.html): `findBy...` syntax, property traversal, and `_` disambiguation.
- [Spring Data MongoDB — `Criteria` API](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/query/Criteria.html): `elemMatch(Criteria)` and other operators.
- [MongoDB Manual — Query an Array of Embedded Documents](https://www.mongodb.com/docs/manual/tutorial/query-array-of-documents/): dot notation and querying arrays of embedded documents.
- [MongoDB Manual — `$elemMatch` Query Predicate](https://www.mongodb.com/docs/manual/reference/operator/query/elemmatch/): single element satisfying all predicates.
- [MongoDB Manual — `$elemMatch` Projection](https://www.mongodb.com/docs/manual/reference/operator/projection/elemmatch/): limiting returned array elements in projections.
- [MongoDB Manual — Multikey Index Bounds](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-multikey/multikey-index-bounds/): relationship between `$elemMatch` and index bound intersection.
- [MongoDB Manual — Multikey Indexes](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-multikey/): indexing arrays and compound multikey restrictions.
