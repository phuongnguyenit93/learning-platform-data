# Embedded Document Paths and Dot Notation

## 1. Goal and Context

MongoDB allows a document to contain another document, an array, and an array of documents. This design fits orders with a shipping address or a list of line items very well: data commonly read together with an order can be stored directly inside one BSON document. When searching, however, we must express the **path to nested fields** accurately.

For example, to find orders shipped to the city Hà Nội, instead of matching the entire `shippingAddress` object, MongoDB lets you specify a nested field using **dot notation**:

```javascript
db.orders.find({ "ship_to.city_name": "Hà Nội" });
```

This path has a different meaning from matching the entire `ship_to` subdocument. And when the queried field sits inside an **array of documents**, conditions on the same path can even match **different elements** unless `$elemMatch` is used.

This lesson belongs to the **Query and Criteria** chapter in the **SPRING_DATA_MONGODB** module. When using Spring Data MongoDB to connect, map documents, and operate via `MongoTemplate` or repositories, understanding dot notation helps you build accurate filters, projections, sorts, updates, and indexes. This knowledge also connects to aggregation, transactions, reactive access, testing, and performance diagnostics.

After this lesson, you will be able to:

1. Distinguish Java property paths from BSON field paths when `@Field` is used.
2. Write `mongosh` queries and `Query`/`Criteria` for embedded documents.
3. Query arrays containing documents, clearly explaining when `$elemMatch` is required.
4. Distinguish missing fields, BSON Null, and missing nested paths.
5. Use repository derived queries for nested properties and design appropriate multikey indexes.
6. Update a nested field without accidentally replacing the entire subdocument, while testing real queries.

## 2. Data Model: Orders, Addresses, and Line Items

### 2.1. Actual BSON

Suppose the `orders` collection stores documents in this form:

```javascript
db.orders.insertMany([
  {
    _id: "ord-001",
    tenantId: "tenant-a",
    status: "PAID",
    ship_to: {
      city_name: "Hà Nội",
      district: "Cầu Giấy",
      street: "Xuân Thủy"
    },
    items: [
      { sku_code: "BOOK-A", quantity: 1, unitPriceVnd: NumberLong("90000") },
      { sku_code: "BOOK-B", quantity: 4, unitPriceVnd: NumberLong("60000") }
    ],
    createdAt: ISODate("2026-11-18T08:00:00Z")
  },
  {
    _id: "ord-002",
    tenantId: "tenant-a",
    status: "PAID",
    ship_to: {
      city_name: "Đà Nẵng",
      district: "Hải Châu",
      street: "Bạch Đằng"
    },
    items: [
      { sku_code: "BOOK-A", quantity: 3, unitPriceVnd: NumberLong("90000") }
    ],
    createdAt: ISODate("2026-11-19T09:00:00Z")
  },
  {
    _id: "ord-003",
    tenantId: "tenant-a",
    status: "NEW",
    ship_to: {
      city_name: null,
      district: "Ba Đình"
    },
    items: [],
    createdAt: ISODate("2026-11-20T06:00:00Z")
  },
  {
    _id: "ord-004",
    tenantId: "tenant-b",
    status: "PAID",
    items: [
      { sku_code: "BOOK-C", quantity: 2, unitPriceVnd: NumberLong("50000") }
    ],
    createdAt: ISODate("2026-11-20T07:00:00Z")
  }
]);
```

This is illustrative data for a test collection. Do not run `insertMany` on production data without verifying IDs and existing constraints.

```text
orders / document ord-001
├── _id: "ord-001"
├── tenantId: "tenant-a"
├── status: "PAID"
├── ship_to: {...}
│   ├── city_name: "Hà Nội"
│   ├── district: "Cầu Giấy"
│   └── street: "Xuân Thủy"
└── items: [...]
    ├── [0]
    │   ├── sku_code: "BOOK-A"
    │   ├── quantity: 1
    │   └── unitPriceVnd: 90000
    └── [1]
        ├── sku_code: "BOOK-B"
        ├── quantity: 4
        └── unitPriceVnd: 60000
```

### 2.2. Java Entity with Property Names Different from BSON Names

To clearly see the role of mapping, use Java 17+ types:

```java
import java.time.Instant;
import java.util.List;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.mapping.MongoId;

@Document(collection = "orders")
public record OrderDocument(
    @MongoId(FieldType.STRING) String id,
    String tenantId,
    String status,
    @Field("ship_to") ShippingAddress shippingAddress,
    List<OrderLine> items,
    Instant createdAt
) {}

record ShippingAddress(
    @Field("city_name") String city,
    String district,
    String street
) {}

record OrderLine(
    @Field("sku_code") String sku,
    int quantity,
    long unitPriceVnd
) {}
```

With the model above:

| Java Property | BSON Path |
| --- | --- |
| `id` | `_id` |
| `shippingAddress` | `ship_to` |
| `shippingAddress.city` | `ship_to.city_name` |
| `shippingAddress.district` | `ship_to.district` |
| `items` | `items` |
| `items.sku` | `items.sku_code` |
| `items.quantity` | `items.quantity` |

**Rule:** In `mongosh` or when calling the MongoDB driver directly, use **BSON field names**. When creating `Query`/`Criteria` with an entity class in Spring Data, normally use **Java property paths** so the mapper converts them into BSON paths. Avoid mixing the two conventions arbitrarily.

## 3. What Is Dot Notation?

### 3.1. Reading a Deeper Field

A path such as `ship_to.city_name` has two parts:

```text
ship_to.city_name
   │        │
   │        └── child field inside the embedded document
   └─────────── field on the parent document
```

In `mongosh`:

```javascript
db.orders.find({
  tenantId: "tenant-a",
  "ship_to.city_name": "Hà Nội"
});
```

This query returns `ord-001`, because `ship_to.city_name` is the string `"Hà Nội"`. Dot notation is a **field path**, not JavaScript object property access syntax; you must wrap dotted paths in quotes when writing JavaScript object literals.

You can go deeper across multiple levels if the schema contains nested documents:

```javascript
// Example if another schema has:
// delivery: { recipient: { contact: { phone: "..." } } }
db.orders.find({
  "delivery.recipient.contact.phone": "0900000000"
});
```

The path in the second example applies only if real documents have that structure; it does not exist in the sample data in section 2.

### 3.2. Matching an Entire Subdocument Differs from Matching a Child Field

The following two queries are **not equivalent**:

```javascript
// Care only about the city:
db.orders.find({ "ship_to.city_name": "Hà Nội" });

// Match the entire subdocument:
db.orders.find({
  ship_to: {
    city_name: "Hà Nội",
    district: "Cầu Giấy",
    street: "Xuân Thủy"
  }
});
```

The second query requires the entire BSON subdocument to match the specified shape and values, including field order in embedded-document equality matching. If a `ship_to` document has extra fields, missing fields, or a different stored field order, the result can differ. When you only need one or a few attributes, **dot notation queries are usually clearer and less coupled to the full structure**.

### 3.3. Combining Multiple Child Fields with AND

```javascript
db.orders.find({
  tenantId: "tenant-a",
  "ship_to.city_name": "Hà Nội",
  "ship_to.district": "Cầu Giấy"
});
```

For a **regular single subdocument** like `ship_to`, both conditions apply to child fields of that same document. However, when entering an **array of documents**, multiple conditions can match different elements; that is the critical distinction in section 5.

## 4. Query and Criteria for Embedded Documents

### 4.1. MongoTemplate with Java Property Paths

```java
import java.util.List;
import org.springframework.data.mongodb.core.MongoOperations;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

public class OrderQueryService {
    private final MongoOperations mongo;

    public OrderQueryService(MongoOperations mongo) {
        this.mongo = mongo;
    }

    public List<OrderDocument> findByShippingCity(
        String authenticatedTenantId,
        String city
    ) {
        Query query = Query.query(
            Criteria.where("tenantId").is(authenticatedTenantId)
                .and("shippingAddress.city").is(city)
        );
        query.limit(50);
        return mongo.find(query, OrderDocument.class);
    }
}
```

With `OrderDocument.class`, Spring Data uses mapping metadata to convert Java property path `shippingAddress.city` to BSON field path `ship_to.city_name`. The method limits results to at most 50 to avoid accidentally loading too many documents; in production APIs, add a stable sort and pagination as needed.

The path `shippingAddress.city` does not require Java to have a method with that name. It is a **property path** that Spring Data resolves using the entity and its nested types.

### 4.2. Comparing Criteria with the MongoDB Filter

```java
Query query = Query.query(
    Criteria.where("tenantId").is("tenant-a")
        .and("shippingAddress.city").is("Hà Nội")
);
```

Expected BSON intent:

```javascript
{
  tenantId: "tenant-a",
  "ship_to.city_name": "Hà Nội"
}
```

**Note:** `query.getQueryObject()` may display the query structure before mapping to physical field names. To confirm the actual BSON sent, use integration tests, command monitoring, or appropriate inspection tools. Do not look only at the String produced by `Query.toString()` to conclude whether `@Field` was applied.

### 4.3. Multiple OR Branches

For example, finding orders belonging to the logged-in tenant shipped to Hà Nội **or** Đà Nẵng:

```java
Criteria cityCondition = new Criteria().orOperator(
    Criteria.where("shippingAddress.city").is("Hà Nội"),
    Criteria.where("shippingAddress.city").is("Đà Nẵng")
);

Query query = Query.query(
    new Criteria().andOperator(
        Criteria.where("tenantId").is(authenticatedTenantId),
        cityCondition
    )
);
```

You can use `in("Hà Nội", "Đà Nẵng")` for this simple case:

```java
Query simpler = Query.query(
    Criteria.where("tenantId").is(authenticatedTenantId)
        .and("shippingAddress.city").in("Hà Nội", "Đà Nẵng")
);
```

Prefer simple, readable expressions. When using complex `$or` clauses, remember to keep the tenant condition outside so no OR branch accidentally bypasses access-control constraints.

## 5. Dot Notation When Paths Traverse an Array

### 5.1. Finding Documents with at Least One Matching Element

In `ord-001`, `items` is an array of documents. MongoDB allows:

```javascript
db.orders.find({
  tenantId: "tenant-a",
  "items.sku_code": "BOOK-A"
});
```

This query matches if **at least one element** in `items` has `sku_code` equal to `"BOOK-A"`. With the dataset in section 2, both `ord-001` and `ord-002` match.

In Spring Data:

```java
Query query = Query.query(
    Criteria.where("tenantId").is("tenant-a")
        .and("items.sku").is("BOOK-A")
);
var matched = mongo.find(query, OrderDocument.class);
```

Because `OrderLine.sku` is annotated with `@Field("sku_code")`, property path `items.sku` corresponds to storage path `items.sku_code`.

### 5.2. Two Conditions Can Match Two Different Elements

Consider document `ord-001`:

```javascript
items: [
  { sku_code: "BOOK-A", quantity: 1 },
  { sku_code: "BOOK-B", quantity: 4 }
]
```

Query:

```javascript
db.orders.find({
  _id: "ord-001",
  "items.sku_code": "BOOK-A",
  "items.quantity": { $gte: 3 }
});
```

**Still matches `ord-001`**, because the SKU condition is satisfied by the first element while the quantity condition is satisfied by the second element. When using multiple predicates across an array, MongoDB **does not require the predicates to hold on the same element by default**.

This is a serious logic bug if the business requirement means "orders having at least one BOOK-A line with quantity 3 or more". Use `$elemMatch` to bind those conditions onto the same element.

### 5.3. $elemMatch: Conditions on the Same Element

```javascript
db.orders.find({
  tenantId: "tenant-a",
  items: {
    $elemMatch: {
      sku_code: "BOOK-A",
      quantity: { $gte: 3 }
    }
  }
});
```

From the sample data, the result contains only `ord-002`: its `BOOK-A` element has `quantity = 3`. `ord-001` does not match because its `BOOK-A` line only has quantity 1.

Illustration:

```text
ord-001:
  items[0] -> sku=BOOK-A  ✓, quantity>=3 ✗
  items[1] -> sku=BOOK-B  ✗, quantity>=3 ✓
  No single element satisfies both.

ord-002:
  items[0] -> sku=BOOK-A  ✓, quantity>=3 ✓
  One element satisfies both.
```

**Rule of thumb:** When conditions must apply to the same object inside an array, use `$elemMatch` on the **outer array field**.

### 5.4. $elemMatch in Criteria

```java
Criteria sameLine = Criteria.where("sku").is("BOOK-A")
    .and("quantity").gte(3);

Query query = Query.query(
    Criteria.where("tenantId").is(authenticatedTenantId)
        .and("items").elemMatch(sameLine)
);

List<OrderDocument> orders = mongo.find(
    query, OrderDocument.class
);
```

The query intent is:

```javascript
{
  tenantId: "tenant-a",
  items: {
    $elemMatch: {
      sku_code: "BOOK-A",
      quantity: { $gte: 3 }
    }
  }
}
```

Property path mapping inside `$elemMatch` depends on the array element metadata and the `QueryMapper` implementation of the version in use. Verify the sent BSON via integration tests, especially when nested entities use `@Field` or custom conversions. With the raw driver API or `mongosh`, always use the physical name `sku_code`.

### 5.5. Reading an Element by Position

When you need to check **the first element**, MongoDB can use an array index:

```javascript
db.orders.find({
  "items.0.sku_code": "BOOK-A"
});
```

The path `items.0.sku_code` means something very different from `items.sku_code`: it checks only the element at index 0. Use this only if array order is part of the data contract. For order line arrays, element order can change when users edit their cart or during data imports; fixed positional indexing is usually unsuitable for business search.

## 6. Distinguishing Embedded Documents, Arrays, and Referenced Documents

Dot notation only traverses **real BSON structures stored directly inside the queried document**.

### 6.1. Embedded Document

```javascript
{
  _id: "ord-001",
  ship_to: { city_name: "Hà Nội" }
}
```

Querying `"ship_to.city_name"` works because `ship_to` is genuinely an embedded document.

### 6.2. Reference Storing Only an ID

If you replace the address with a reference:

```javascript
// orders:
{ _id: "ord-001", shippingAddressId: "addr-001" }

// addresses:
{ _id: "addr-001", city_name: "Hà Nội" }
```

Querying `"shippingAddressId.city_name"` **will not look up the city name in the `addresses` collection**. The `shippingAddressId` field holds only a String ID, not an embedded document.

Similarly, `@DocumentReference` may materialize the Java property as an object when reading, yet typically stores the reference ID value in BSON. MongoDB `find` does not automatically join collections. To filter by an address in another collection, consider `$lookup`, a two-step query, or appropriate denormalization.

### 6.3. Choosing Embed vs. Reference from Access Patterns

| Need | Usually Suitable Model |
| --- | --- |
| Shipping address must be preserved as a snapshot at order placement | Embedded `ship_to` |
| Many orders should point to up-to-date customer info | Reference ID, optionally storing needed snapshots |
| Frequently searching orders by city | Store the city field inside `orders` with a suitable index |
| Linked info changes constantly or grows very large | Reference or dedicated projection/collection |

Do not turn every relationship into an embedded document merely to use dot notation. Document size, update frequency, and cardinality should drive the decision.

## 7. Null, Missing, and Nested Paths

In the sample data:

- `ord-001` has `ship_to.city_name = "Hà Nội"`.
- `ord-003` has `ship_to.city_name = null`.
- `ord-004` **lacks the `ship_to` field**.

### 7.1. Finding Child Fields Equal to Null

```javascript
db.orders.find({ "ship_to.city_name": null });
```

In MongoDB, equality with `null` using this syntax usually matches **both fields with BSON Null and missing fields**. Therefore, both `ord-003` and `ord-004` match. Do not use this filter if business rules must distinguish "explicitly recorded as null" from "never had an address".

### 7.2. Finding Existing or Missing Child Fields

```javascript
// Has the path ship_to.city_name, even if its value is null.
db.orders.find({
  "ship_to.city_name": { $exists: true }
});

// Path ship_to.city_name does not exist.
db.orders.find({
  "ship_to.city_name": { $exists: false }
});
```

When parent document `ship_to` does not exist, child path `ship_to.city_name` is also considered missing. However, if `ship_to.city_name` exists and holds null, `$exists: true` still matches.

### 7.3. Finding Explicit BSON Null

```javascript
db.orders.find({
  "ship_to.city_name": { $type: "null" }
});
```

With a single subdocument structure like `ship_to`, the condition above finds documents whose child field has BSON type Null, distinct from missing. Cases where the parent field or path goes through complex arrays should be tested against real BSON rather than over-extrapolated.

### 7.4. Criteria.exists(...) and Exact Checks

```java
Query missingCity = Query.query(
    Criteria.where("tenantId").is(authenticatedTenantId)
        .and("shippingAddress.city").exists(false)
);
```

Like `mongosh`, `exists(false)` checks that the child field does not exist; it does not mean "empty string", "Null", or "invalid address". If business logic needs to distinguish those states, design proper validation and data migrations.

## 8. Derived Queries in MongoRepository for Nested Properties

### 8.1. Derived Queries by Property Path

Spring Data can parse nested property paths in method names:

```java
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Slice;
import org.springframework.data.repository.Repository;

public interface OrderSearchRepository
    extends Repository<OrderDocument, String> {

    Slice<OrderDocument> findByTenantIdAndShippingAddress_City(
        String tenantId,
        String city,
        Pageable pageable
    );
}
```

The underscore `_` in `ShippingAddress_City` explicitly marks the property path boundary: `shippingAddress.city`. This is the **Java model** path, not the BSON field name `ship_to.city_name`. Spring Data mapping can apply `@Field` to query the stored data accurately.

Calling the repository:

```java
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;

var page = repository.findByTenantIdAndShippingAddress_City(
    authenticatedTenantId,
    "Hà Nội",
    PageRequest.of(
        0,
        20,
        Sort.by(Sort.Order.desc("createdAt"), Sort.Order.desc("id"))
    )
);
```

Here `repository` is an injected `OrderSearchRepository` bean. `Slice` is used to get `hasNext()` without requiring a total page count; deep offsets can still be expensive.

### 8.2. Avoid Ambiguous Method Names

Suppose the entity later acquires both a `shippingAddressCity` property and a `shippingAddress.city` object; a method like `findByShippingAddressCity` can cause ambiguity during property path parsing. Use the `_` separator when you need to make nested paths explicit, and name model fields to avoid confusing collisions.

Derived queries are not always superior to `@Query`. For complex nested array conditions, `$elemMatch`, and multiple AND/OR combinations, `MongoTemplate` or explicit JSON queries are usually easier to review.

### 8.3. @Query with BSON Paths

When you want to express the filter as JSON in a repository:

```java
import java.util.List;
import org.springframework.data.mongodb.repository.Query;

public interface OrderJsonQueryRepository
    extends Repository<OrderDocument, String> {

    @Query("{ 'tenantId': ?0, 'ship_to.city_name': ?1 }")
    List<OrderDocument> findByStoredCity(
        String tenantId,
        String city
    );
}
```

Here the query is written using **actual BSON paths**. `?0` and `?1` are parameter-bound by Spring Data; never concatenate JSON strings from user input. Note that the method returns an unbounded `List`; production applications should use `Pageable`/`Slice` or an explicit limit as appropriate.

In some APIs, Spring Data also performs field name mapping on JSON queries. To avoid confusion when using `@Field` aliases alongside manual JSON, always inspect the real query and stay consistent within repositories.

## 9. Projection and Sorting on Nested Paths

### 9.1. Projection Selecting Only Needed Fields

MongoDB lets you project just a nested field:

```javascript
db.orders.find(
  { tenantId: "tenant-a" },
  {
    "ship_to.city_name": 1,
    status: 1
  }
);
```

The resulting BSON normally preserves the nested structure, for example:

```javascript
{
  _id: "ord-001",
  status: "PAID",
  ship_to: { city_name: "Hà Nội" }
}
```

To omit `_id` from a MongoDB projection, specify `_id: 0`. This projection does not preserve all original fields inside `ship_to`; if mapping into an entity with required fields, verify constructor/default behavior. For list APIs, a dedicated DTO/projection is usually safer than loading a partial entity and accidentally calling `save`.

### 9.2. Projection via Query.fields()

```java
Query query = Query.query(
    Criteria.where("tenantId").is(authenticatedTenantId)
);
query.fields()
    .include("shippingAddress.city")
    .include("status");
query.limit(20);
```

When run against `OrderDocument.class`, the property path can be translated by the mapper to `ship_to.city_name`. Verify the actual BSON, especially if results are mapped to a DTO rather than the domain entity.

### 9.3. Sorting by a Child Field

```javascript
db.orders.find({ tenantId: "tenant-a" })
  .sort({ "ship_to.city_name": 1, _id: 1 });
```

In Spring Data:

```java
import org.springframework.data.domain.Sort;

query.with(Sort.by(
    Sort.Order.asc("shippingAddress.city"),
    Sort.Order.asc("id")
));
```

Sorting by `shippingAddress.city` uses metadata when a domain type is provided. If data contains `null`, missing fields, or inconsistent BSON types, sort order may differ from business expectations. If you want city names sorted according to Vietnamese alphabetical rules, consider an appropriate `Collation` **and an index with the same collation**.

## 10. Indexes for Embedded Document Paths

### 10.1. Compound Index by Tenant and City

If you frequently look up a tenant's orders by city:

```javascript
db.orders.createIndex(
  { tenantId: 1, "ship_to.city_name": 1 },
  { name: "ix_orders_tenant_ship_city" }
);
```

This index fits equality queries on `tenantId` and `ship_to.city_name`. MongoDB can use it to limit scanned documents; there is no guarantee it is always chosen if the dataset is tiny or another index is cheaper.

### 10.2. Choosing Indexes for Both Filter and Sort

If business logic needs the newest orders shipped to Hà Nội:

```javascript
db.orders.find({
  tenantId: "tenant-a",
  "ship_to.city_name": "Hà Nội"
})
  .sort({ createdAt: -1, _id: -1 })
  .limit(20);
```

A candidate compound index:

```javascript
db.orders.createIndex(
  {
    tenantId: 1,
    "ship_to.city_name": 1,
    createdAt: -1,
    _id: -1
  },
  { name: "ix_orders_tenant_city_recent" }
);
```

The first two fields filter by equality, and the trailing fields support the sort order. Verify the actual query using `explain("executionStats")` and measure on representative data. Do not create many nearly identical indexes without weighing write and storage costs.

### 10.3. Indexes Do Not Enforce Schema or Permissions

An index on `ship_to.city_name` does not guarantee every document contains `ship_to` or `city_name`, does not validate city names, and does not enforce tenant isolation. Those guarantees require application-layer validation and/or MongoDB schema validation, plus authorization tests.

## 11. Multikey Indexes for Arrays of Documents

### 11.1. Indexing `items.sku_code`

When indexing a field whose values come from an array, MongoDB can create a **multikey index**:

```javascript
db.orders.createIndex(
  { tenantId: 1, "items.sku_code": 1 },
  { name: "ix_orders_tenant_item_sku" }
);
```

For `ord-001`, the array has two lines, so the index can contain entries for both SKU values. This helps queries like:

```javascript
db.orders.find({
  tenantId: "tenant-a",
  "items.sku_code": "BOOK-A"
});
```

However, multikey indexes carry storage and update overhead whenever the array changes; large arrays or many duplicate values can impact performance.

### 11.2. $elemMatch and Compound Multikey Indexes

If you often search line items by both SKU and quantity:

```javascript
db.orders.find({
  tenantId: "tenant-a",
  items: {
    $elemMatch: {
      sku_code: "BOOK-A",
      quantity: { $gte: 3 }
    }
  }
});
```

An index to evaluate:

```javascript
db.orders.createIndex(
  {
    tenantId: 1,
    "items.sku_code": 1,
    "items.quantity": 1
  },
  { name: "ix_orders_tenant_item_sku_qty" }
);
```

With conditions on **the same array element** via `$elemMatch`, the query planner can utilize tighter compound multikey index bounds compared to independent conditions that can match different elements.

**Limitation to remember:** Not every compound index involving multiple array fields is valid. MongoDB enforces constraints on compound multikey indexes and indexing multiple independent arrays. The example index above traverses fields of **the same `items` array**; if you add another independent array field to the design, re-check index validity and benefit.

### 11.3. Using explain to Separate Wrong Queries from Poor Indexes

```javascript
db.orders.find({
  tenantId: "tenant-a",
  items: {
    $elemMatch: {
      sku_code: "BOOK-A",
      quantity: { $gte: 3 }
    }
  }
}).explain("executionStats");
```

Inspect `winningPlan`, `IXSCAN` or `COLLSCAN`, `totalKeysExamined`, `totalDocsExamined`, and `nReturned`. If the query does not return `ord-001`, that is **correct `$elemMatch` logic**, not an index failure. Never remove `$elemMatch` just to see more results.

## 12. Updating Nested Fields Using Dot Notation

Dot notation is not only for reading. MongoDB lets you update a single nested field in a subdocument with `$set`.

### 12.1. Updating City While Keeping District and Street

```javascript
db.orders.updateOne(
  { _id: "ord-001", tenantId: "tenant-a" },
  { $set: { "ship_to.city_name": "Hải Phòng" } }
);
```

After this command, `ship_to.district` and `ship_to.street` remain intact.

Conversely:

```javascript
db.orders.updateOne(
  { _id: "ord-001", tenantId: "tenant-a" },
  { $set: { ship_to: { city_name: "Hải Phòng" } } }
);
```

The second command **replaces the entire `ship_to` value** with a new subdocument, wiping out `district` and `street` if they existed before. These two updates are not equivalent.

### 12.2. Updating via MongoTemplate

```java
import org.springframework.data.mongodb.core.query.Update;

Query query = Query.query(
    Criteria.where("id").is("ord-001")
        .and("tenantId").is(authenticatedTenantId)
);

Update update = new Update()
    .set("shippingAddress.city", "Hải Phòng");

var result = mongo.updateFirst(
    query, update, OrderDocument.class
);
```

In the context of `OrderDocument.class`, Spring Data can map property path `shippingAddress.city` to BSON `ship_to.city_name`. For production data, always verify that the `Update` portion is mapped accurately according to `@Field` aliases.

A MongoDB command on a single document is atomic. Still, if address modification depends on order status or current version, put the appropriate business conditions right inside the filter rather than relying solely on an earlier read.

### 12.3. Conditionally Updating an Array Element

When you want to update the `BOOK-A` line without modifying `BOOK-B`, you can use the filtered positional operator `$[line]` and `arrayFilters`:

```javascript
db.orders.updateOne(
  {
    _id: "ord-001",
    tenantId: "tenant-a"
  },
  { $set: { "items.$[line].quantity": 3 } },
  {
    arrayFilters: [
      { "line.sku_code": "BOOK-A" }
    ]
  }
);
```

Every `items` element matching the `line` condition is updated. This differs from the positional operator `$`, which binds only to the element matched by the query predicate in supported updates.

With Spring Data MongoDB versions supporting `Update.filterArray(...)`:

```java
Update update = new Update()
    .set("items.$[line].quantity", 3)
    .filterArray(
        Criteria.where("line.sku_code").is("BOOK-A")
    );

Query query = Query.query(
    Criteria.where("id").is("ord-001")
        .and("tenantId").is(authenticatedTenantId)
);

mongo.updateFirst(query, update, OrderDocument.class);
```

**Important:** `arrayFilters` conditions can be passed down to the driver **without going through the same field-name mapping mechanism** as entity-bound Criteria. Therefore, use the physical BSON name `line.sku_code` inside the filter instead of assuming `line.sku` will auto-translate via `@Field`. Verify the API version and generated BSON update in integration tests.

### 12.4. Caution with Invalid Update Paths

If `ship_to` does not exist or is not a document matching the schema, an update setting `ship_to.city_name` may create a nested object or fail depending on the document state. Dot notation should not be treated as an automatic repair tool for malformed data. Enforce validation and run migrations when legacy records hold mismatched parent types.

## 13. Aggregation and $lookup Using BSON Paths

Dot notation also appears in aggregation:

```javascript
db.orders.aggregate([
  { $match: {
      tenantId: "tenant-a",
      "ship_to.city_name": "Hà Nội"
  }},
  { $unwind: "$items" },
  { $group: {
      _id: "$items.sku_code",
      orderedQuantity: { $sum: "$items.quantity" }
  }},
  { $sort: { orderedQuantity: -1 } }
]);
```

This pipeline:

1. Filters orders by tenant and city.
2. Uses `$unwind` to flatten elements of the `items` array.
3. Groups by the SKU of **each unwound element**.
4. Sums quantities to produce a report.

This illustrates that `"$items.sku_code"` in an **aggregation expression** has value-lookup semantics distinct from filter field names in `find`. The `$` prefix denotes a field path expression; in a JSON filter `{ "items.sku_code": "BOOK-A" }`, no `$` is used.

If the stored data uses reference IDs rather than embedded objects, `$lookup` can join the appropriate collections; dot notation by itself performs no joins.

## 14. Correct and Safe Queries in Multi-Tenant Systems

### 14.1. Never Accept Arbitrary Field Paths from Clients

Suppose a UI allows filtering orders by city, status, and SKU. Never accept a raw string like `fieldPath = "items.0.unitPriceVnd"` and pass it directly into:

```java
// Unsafe when fieldPath comes uncontrolled from a client.
Criteria.where(fieldPath).is(value);
```

This can expose internal structure, produce uncontrolled queries, or cause heavy load. Instead, map a valid set of options to approved property paths:

```java
String field = switch (filterName) {
    case "city" -> "shippingAddress.city";
    case "sku" -> "items.sku";
    case "status" -> "status";
    default -> throw new IllegalArgumentException("Unsupported filter");
};

Query query = Query.query(
    Criteria.where("tenantId").is(authenticatedTenantId)
        .and(field).is(value)
);
```

This snippet illustrates field allowlisting; `filterName`/`value` must be validated and converted to the right type before production use. For multiple conditions on the same array element, do not chain `.and("items.quantity")` while forgetting `$elemMatch`.

### 14.2. Combining Tenant Conditions with Nested Paths

A query filtering only on `"ship_to.city_name"` can return orders from other tenants. In a multi-tenant system, use:

```javascript
db.orders.find({
  tenantId: "tenant-a",
  "ship_to.city_name": "Hà Nội"
});
```

The tenant parameter must come from a trusted security context or authorization logic. Having a `tenantId` field in a query **does not by itself authenticate** the passed value.

### 14.3. Never Mix AND/OR Logic in a Way That Drops Mandatory Conditions

The following example is dangerous when a developer wants "tenant-a and (Hà Nội or Đà Nẵng)":

```javascript
// Wrong if all results must belong to tenant-a:
db.orders.find({
  $or: [
    { tenantId: "tenant-a", "ship_to.city_name": "Hà Nội" },
    { "ship_to.city_name": "Đà Nẵng" }
  ]
});
```

The second branch does not constrain the tenant. Correct version:

```javascript
db.orders.find({
  tenantId: "tenant-a",
  "ship_to.city_name": { $in: ["Hà Nội", "Đà Nẵng"] }
});
```

With more complex branches, place tenant at the top level and inspect the actual BSON filter. No index or annotation can compensate for a miswritten authorization condition.

## 15. Testing Mapping and Array Conditions

### 15.1. Minimum Test Matrix

| Test | Expected Outcome |
| --- | --- |
| Search `shippingAddress.city = "Hà Nội"` in tenant-a | Matches `ord-001` |
| Search same city in a different tenant | Does not return `ord-001` |
| Search `items.sku = "BOOK-A"` | Matches `ord-001` and `ord-002` in tenant-a |
| Two independent conditions `items.sku=BOOK-A` and `items.quantity>=3` | Can match `ord-001` across two different elements |
| Use `$elemMatch` for BOOK-A and quantity>=3 | Only `ord-002` |
| Search `ship_to.city_name: null` | Matches Null and missing per MongoDB semantics |
| `$exists: false` on city | Matches documents lacking the child path |
| `$type: "null"` on city | Only documents with BSON Null at the child field |
| Update `shippingAddress.city` | Existing district/street remain preserved |
| Replace entire `shippingAddress` | Fields omitted from the new object can be lost |
| ArrayFilter update on BOOK-A | Does not alter the BOOK-B line |
| Index on nested path | Query is accurate and plan is observed |

### 15.2. MongoTemplate Database Test

Illustrative JUnit 5 skeleton, assuming the test context injects `MongoOperations` and connects to a dedicated test MongoDB database:

```java
import static org.junit.jupiter.api.Assertions.*;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.data.mongodb.core.MongoOperations;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

class NestedPathIntegrationTest {
    MongoOperations mongo; // Injected from actual test context.

    @Test
    void nestedPathAndElemMatchMustDiffer() {
        Query independent = Query.query(
            Criteria.where("tenantId").is("tenant-a")
                .and("items.sku").is("BOOK-A")
                .and("items.quantity").gte(3)
        );
        List<OrderDocument> broad = mongo.find(
            independent, OrderDocument.class
        );

        Query sameElement = Query.query(
            Criteria.where("tenantId").is("tenant-a")
                .and("items").elemMatch(
                    Criteria.where("sku").is("BOOK-A")
                        .and("quantity").gte(3)
                )
        );
        List<OrderDocument> strict = mongo.find(
            sameElement, OrderDocument.class
        );

        assertTrue(broad.stream()
            .anyMatch(order -> order.id().equals("ord-001")));
        assertFalse(strict.stream()
            .anyMatch(order -> order.id().equals("ord-001")));
        assertTrue(strict.stream()
            .anyMatch(order -> order.id().equals("ord-002")));
    }
}
```

This is a **test skeleton**, not a standalone runnable class: you must configure the test context, dependencies, injection, fixture seeding, data cleanup, and an appropriate test MongoDB. In a complete test suite, assert exact ID lists, BSON types, tenant isolation, and the actual sent query.

### 15.3. Verifying Paths Renamed by @Field

When testing, do not compare only Java objects after reading. Inspect the physical document:

```javascript
db.orders.findOne(
  { _id: "ord-001" },
  { ship_to: 1, items: 1 }
);
```

Verify `ship_to.city_name` and `items.sku_code` match the metadata. An integration test can use `MongoTemplate.find(query, org.bson.Document.class, "orders")` to observe raw BSON without mapping into the domain entity, then compare against results queried with `OrderDocument.class`.

### 15.4. Measuring Performance After Verifying Logic

Run:

```javascript
db.orders.find({
  tenantId: "tenant-a",
  "ship_to.city_name": "Hà Nội"
})
  .sort({ createdAt: -1, _id: -1 })
  .limit(20)
  .explain("executionStats");
```

Check `winningPlan`, `IXSCAN`/`COLLSCAN`, `totalKeysExamined`, `totalDocsExamined`, `nReturned`, and sort stages. If a query misses documents due to misusing `$elemMatch`, no index can fix that logic bug. Only once results are right should you evaluate compound/multikey indexes for the workload.

## 16. Common Errors

| Symptom | Possible Cause | How to Check or Fix |
| --- | --- | --- |
| `Criteria.where("ship_to.city_name")` yields unexpected results | Mixed BSON name with Java property path, unexpected mapping | Check `@Field` and the sent BSON query |
| Querying `shippingAddress.city` in `mongosh` finds nothing | MongoDB only knows physical field `ship_to.city_name` | Use BSON names in `mongosh` |
| `ship_to.city_name` query matches while embedded-object equality fails | Subdocument has missing/extra fields or different field order | Use dot notation when only specific fields matter |
| SKU and quantity conditions match the wrong order | Two predicates traverse the array, satisfied by different elements | Use `$elemMatch` |
| `items.0.sku_code` misses orders | Only checks the first array element | Use `items.sku_code` or `$elemMatch` per business rule |
| Null city query returns orders with no address | `{field: null}` includes missing | Use `$type: "null"` or `$exists` |
| Updating city wipes district/street | `$set` replaced the entire `ship_to` subdocument | `$set` the specific child path |
| Array filter fails to match when using `sku` | Filter was not mapped to `sku_code` | Use the BSON field name in `arrayFilters` and test |
| Query on `shippingAddressId.city` fails | Field is a reference ID, not an embedded document | Query the target collection or use `$lookup` |
| Nested path index does not speed up query | Mismatched key order/sort/collation or tiny dataset | Inspect the actual execution plan |
| Cross-tenant data leak | An OR branch lacks the tenant filter | Place tenant in a top-level mandatory condition |
| Projection yields entity with missing data | Selected only child fields and mapped into full entity | Use DTO/projection and do not save partial entities |

## 17. Practice Exercises with Solutions

### Exercise 1 — Writing the Path to City

**Problem:** A document stores `ship_to: {city_name: "Hà Nội", district: "Cầu Giấy"}`. Write a `mongosh` query retrieving `tenant-a` orders shipped to Hà Nội.

**Solution:**

```javascript
db.orders.find({
  tenantId: "tenant-a",
  "ship_to.city_name": "Hà Nội"
});
```

`ship_to.city_name` is the BSON path. Do not write `shippingAddress.city` in `mongosh`, as that is the Java property name of the illustrative model.

### Exercise 2 — Predicting @Field Mapping

**Problem:** An entity has `@Field("ship_to") ShippingAddress shippingAddress`; inside `ShippingAddress` is `@Field("city_name") String city`. Write `Criteria` for city Đà Nẵng.

**Solution:**

```java
Query query = Query.query(
    Criteria.where("shippingAddress.city").is("Đà Nẵng")
);
```

When executed with `OrderDocument.class`, the mapper translates it to BSON path `ship_to.city_name`. In a multi-tenant system, add the tenant condition before using this query.

### Exercise 3 — Finding a Line Satisfying Two Conditions Together

**Problem:** Find `tenant-a` orders with a `BOOK-A` line having quantity 3 or more. Why should you not use two independent dot-notation conditions?

**Solution:** Two independent conditions can be satisfied by two different elements. Use:

```javascript
db.orders.find({
  tenantId: "tenant-a",
  items: {
    $elemMatch: {
      sku_code: "BOOK-A",
      quantity: { $gte: 3 }
    }
  }
});
```

With the fixture, only `ord-002` matches. `ord-001` has BOOK-A, but its BOOK-A quantity is only 1.

### Exercise 4 — Distinguishing Null and Missing

**Problem:** Write two queries: (a) retrieve only orders whose `ship_to.city_name` is BSON Null, (b) retrieve orders missing that path.

**Solution:**

```javascript
db.orders.find({
  "ship_to.city_name": { $type: "null" }
});

db.orders.find({
  "ship_to.city_name": { $exists: false }
});
```

Do not use `{ "ship_to.city_name": null }` if exact distinction is required, as that syntax typically includes missing fields.

### Exercise 5 — Updating City While Preserving Other Fields

**Problem:** For `ord-001`, change city to Hải Phòng while keeping district and street intact.

**Solution:**

```javascript
db.orders.updateOne(
  { _id: "ord-001", tenantId: "tenant-a" },
  { $set: { "ship_to.city_name": "Hải Phòng" } }
);
```

Do not set the entire `ship_to` field to an object containing only `city_name`; doing so replaces the subdocument and loses the remaining fields.

### Exercise 6 — Designing Indexes for Two Queries

**Problem:** (a) Find `tenant-a` orders shipped to Hà Nội; (b) find `tenant-a` orders containing SKU BOOK-A. Which initial indexes would you choose?

**Solution:**

```javascript
db.orders.createIndex(
  { tenantId: 1, "ship_to.city_name": 1 },
  { name: "ix_orders_tenant_ship_city" }
);

db.orders.createIndex(
  { tenantId: 1, "items.sku_code": 1 },
  { name: "ix_orders_tenant_item_sku" }
);
```

The second index is multikey because `items` is an array. These are **initial candidates**, not proven optimal conclusions. Check `explain("executionStats")` with representative workloads and data.

### Exercise 7 — Embedded or Reference?

**Problem:** A schema stores `shippingAddressId: "addr-001"` and the actual address lives in the `addresses` collection. Will querying `shippingAddressId.city_name` find orders by city?

**Solution:** No. `shippingAddressId` holds only an ID; dot notation does not follow references into another collection. You need `$lookup`, a two-step query, or a city snapshot stored in `orders` if the access pattern requires it.

### Exercise 8 — Authorization When Combining OR

**Problem:** Only `tenant-a` users may view orders going to Hà Nội or Đà Nẵng. Write a filter preventing an OR branch from bypassing the tenant.

**Solution:**

```javascript
db.orders.find({
  tenantId: "tenant-a",
  "ship_to.city_name": { $in: ["Hà Nội", "Đà Nẵng"] }
});
```

With more complex condition branches, verify tenant always sits outside and applies to every branch; the user's tenant must be authenticated at the application layer.

## 18. Checklist and Key Takeaways

| Question to Answer | Verification Evidence |
| --- | --- |
| Is the document actually embedded or just storing an ID? | Sample BSON from MongoDB |
| Has any Java property been renamed via `@Field`? | Entity metadata and BSON path |
| Does the filter use Java names or BSON names? | The `Criteria`/`@Query`/`mongosh` API in use |
| Does the path traverse an array? | Schema and real fixtures |
| Must the predicates hold on the same element? | If yes, use `$elemMatch` |
| Is there `null`/missing/wrong-type data? | `$exists`, `$type`, data statistics |
| Is the query bound to tenant/owner? | Security context and integration tests |
| Are sort, limit, or pagination needed? | Access pattern and query shape |
| Does projection return a partial entity? | DTO/projection and mapping tests |
| Is the nested path index suitable? | `getIndexes()` and `explain` |
| Is the array index multikey? | Array schema and index metadata |
| Does the update change a child field or replace the embedded doc? | Re-read document after update |
| Do array filters use the right BSON field names? | BSON command and integration tests |
| Do aggregation expressions use exact paths? | Pipeline and results against fixtures |

### Key Takeaways

1. **Dot notation** describes the path to a nested field of a BSON document, e.g., `ship_to.city_name`. Do not confuse BSON names with Java properties like `shippingAddress.city`.
2. On a **single embedded document**, multiple dot-notation conditions inspect child fields of that same document; on an **array of documents**, they can be satisfied by different elements.
3. Use **`$elemMatch`** whenever multiple conditions must hold on **the same element** inside an array.
4. `null` and missing fields have distinct query semantics; choose `$exists`/`$type` when exact distinction is needed.
5. Queries and indexes must align with **real BSON fields**, while ensuring tenant filtering, sorting, result limits, and performance. Multikey indexes help, yet carry specific constraints and costs.
6. During updates, `$set: {"ship_to.city_name": ...}` modifies only the child field, whereas `$set: {ship_to: {...}}` replaces the whole subdocument.
7. Do not trust Criteria syntax alone: **test mapping, BSON, and real results** before optimizing with indexes.
