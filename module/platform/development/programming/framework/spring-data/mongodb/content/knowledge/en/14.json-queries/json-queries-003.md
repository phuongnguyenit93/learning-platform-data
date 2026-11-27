# Limiting Returned Fields Using the fields Attribute

## 1. Problem: Querying the Right Documents but Returning Too Much Data

An e-commerce system stores orders in the `orders` collection. Each document contains summary information for a list view—such as order ID, status, and total amount—alongside details only needed on a detail screen, such as shipping address, internal notes, and line items.

When a customer opens a list of their 20 most recent orders, the API actually only needs:

- Order ID (`_id`).
- Status (`status`).
- Total amount (`totalAmount`).
- Order timestamp (`placedAt`).

If the repository returns the entire entity containing a long `items` list and shipping details, the application receives far more data than necessary. Network cost, BSON decoding, Java object allocation, and the risk of accidentally leaking private data into responses all increase.

**MongoDB projection** solves this need: specify which fields are returned by the query instead of returning the whole document. In Spring Data MongoDB, the **`fields` attribute of the `@Query` annotation** declares projection directly on the repository method.

This lesson belongs to the **JSON Queries** chapter of the **SPRING_DATA_MONGODB** module. We will practice writing JSON for `@Query(value=..., fields=...)`, inspect results via repositories or `MongoTemplate`, understand include/exclude rules, nested fields, and arrays, and then analyze impacts on mapping, indexes, aggregation, transactions, reactive access, testing, and performance.

> **Core idea:** `value` (or `query` depending on API context) determines **which documents match**, whereas `fields` determines **which fields of those matching documents are returned**. Projection does not modify data stored in MongoDB.

## 2. Sample Data and How to Read It in `mongosh`

Suppose the `orders` collection holds the following document. Commands in this lesson should only be run on a dedicated database for learning/testing.

```javascript
db.orders.insertOne({
  _id: "ord-1001",
  customerId: "cus-01",
  status: "PAID",
  totalAmount: NumberDecimal("1850000.00"),
  placedAt: ISODate("2026-11-20T02:00:00Z"),
  shippingAddress: {
    recipientName: "Nguyễn An",
    city: "Đà Nẵng",
    phone: "0900000000"
  },
  internalNote: "Call customer before delivery",
  items: [
    {
      productId: "p-10",
      productName: "Mechanical keyboard",
      quantity: 2,
      unitPrice: NumberDecimal("925000.00")
    }
  ]
});
```

A standard query:

```javascript
db.orders.find({ customerId: "cus-01" });
```

returns all fields in the document unless another projection option is specified.

### 2.1. Projection in MongoDB Before Applying Spring Data

The second argument of `find(filter, projection)` in `mongosh` limits returned fields:

```javascript
db.orders.find(
  { customerId: "cus-01" },
  {
    _id: 1,
    status: 1,
    totalAmount: 1,
    placedAt: 1
  }
);
```

Illustrative output:

```javascript
{
  _id: "ord-1001",
  status: "PAID",
  totalAmount: NumberDecimal("1850000.00"),
  placedAt: ISODate("2026-11-20T02:00:00Z")
}
```

The `shippingAddress`, `internalNote`, and `items` fields **are not in the returned payload**. They still exist in the collection; running a projection does not delete or alter those fields.

MongoDB typically represents projection as a BSON/JSON document mapping field names to directives: `1` to include the field, `0` to exclude it from results. Certain projection operators such as `$slice` or `$elemMatch` also have their own syntax.

## 3. Syntax of `@Query(fields = "...")` in Spring Data MongoDB

In a repository, the `@Query` annotation accepts a JSON query string and a JSON projection string:

```java
@Query(
    value = "{ 'customerId': ?0 }",
    fields = "{ '_id': 1, 'status': 1, 'totalAmount': 1, 'placedAt': 1 }"
)
List<OrderDocument> findOrderHeaders(String customerId);
```

How to read this:

- `value` is the filter part: only documents with `customerId` equal to the first parameter (`?0`).
- `fields` is the projection part: return only `_id`, `status`, `totalAmount`, and `placedAt`.
- `?0` is a placeholder bound by Spring Data; never concatenate JSON from user strings directly.
- `List<OrderDocument>` in this example will contain **partially populated entities**. Unloaded properties may become `null`/default values—which is why a dedicated return type for list views is normally preferred, as shown below.

The `@Query` annotation lets you define criteria without writing `MongoTemplate` code for every query. However, `fields` is not SQL `SELECT`, does not perform joins, and does not remove fields from stored documents.

### 3.1. Java Property Names and BSON Names

In the main example, Java properties and BSON fields share the same names (`customerId`, `status`, `totalAmount`). With `@Field("customer_id")`, the Java name can differ from the stored name. Repository queries go through Spring Data mapping metadata; you should not assume strings used in raw `mongosh` and in annotations are handled identically across every configuration, especially when converters or naming strategies are involved.

A safe workflow is to **verify actual BSON field names**, then write integration tests for the query/projection, especially after changing `@Field` or data converters.

## 4. Java Model for the Examples

Using Java 17+ and Spring Data MongoDB. The code snippets below are conceptually standalone examples; each top-level type should reside in its own Java file.

```java
import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;

import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.mapping.MongoId;

@Document(collection = "orders")
public record OrderDocument(
    @MongoId(FieldType.STRING)
    String id,

    String customerId,
    String status,

    @Field(targetType = FieldType.DECIMAL128)
    BigDecimal totalAmount,

    Instant placedAt,
    ShippingAddress shippingAddress,
    String internalNote,
    List<OrderItem> items
) {
    public record ShippingAddress(
        String recipientName,
        String city,
        String phone
    ) {}

    public record OrderItem(
        String productId,
        String productName,
        int quantity,
        @Field(targetType = FieldType.DECIMAL128)
        BigDecimal unitPrice
    ) {}
}
```

`@MongoId(FieldType.STRING)` explicitly stores `id` in the BSON `_id` field as a string. `@Field(targetType=DECIMAL128)` stores monetary values as BSON Decimal128 under Spring Data mapping.

If an entity is loaded without `items`, `shippingAddress`, or `internalNote` due to projection, the mapped record cannot represent a complete `OrderDocument` as originally written. Never treat missing-data records as evidence that those fields did not exist.

## 5. Include Projection: Selecting Only Needed Fields

### 5.1. Repository Using `@Query(fields=...)`

```java
import java.util.List;

import org.springframework.data.mongodb.repository.MongoRepository;
import org.springframework.data.mongodb.repository.Query;

public interface OrderRepository
        extends MongoRepository<OrderDocument, String> {

    @Query(
        value = "{ 'customerId': ?0 }",
        fields = "{ '_id': 1, 'status': 1, 'totalAmount': 1, 'placedAt': 1 }"
    )
    List<OrderDocument> findOrderHeaders(String customerId);
}
```

When called:

```java
List<OrderDocument> orders =
    orderRepository.findOrderHeaders("cus-01");

for (OrderDocument order : orders) {
    System.out.println(order.id());
    System.out.println(order.status());
    System.out.println(order.totalAmount());

    // Do not expect items or shippingAddress to be loaded.
}
```

This is a simple way to see the `fields` attribute in action. However, because the return type is still the full entity, some `OrderDocument` fields will lack values. Section 9 introduces interface projections better suited for read-only APIs.

### 5.2. Default Rule for `_id`

MongoDB **includes `_id` by default**, even when you only list other fields:

```javascript
db.orders.find(
  { customerId: "cus-01" },
  { status: 1, totalAmount: 1 }
);
```

The result still contains `_id`. If you genuinely do not want the ID returned, add `_id: 0`:

```javascript
db.orders.find(
  { customerId: "cus-01" },
  { _id: 0, status: 1, totalAmount: 1 }
);
```

Correspondingly in the repository:

```java
@Query(
    value = "{ 'customerId': ?0 }",
    fields = "{ '_id': 0, 'status': 1, 'totalAmount': 1 }"
)
List<OrderDocument> findAmountsWithoutIds(String customerId);
```

**Be careful:** if `_id` is excluded while the Java return type has an `id` property, that property will lack data. This works for read-only data/DTOs when the ID is unneeded, not when the application later wants to update the document by ID.

### 5.3. Combining Multiple Fields and Sort

An order list typically needs pagination and sorting by `placedAt`. Projection only decides returned fields; sorting and paging are separate concerns:

```java
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Slice;
import org.springframework.data.mongodb.repository.Query;

@Query(
    value = "{ 'customerId': ?0 }",
    fields = "{ '_id': 1, 'status': 1, 'totalAmount': 1, 'placedAt': 1 }"
)
Slice<OrderDocument> findHeadersByCustomer(
    String customerId,
    Pageable pageable
);
```

Usage example:

```java
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;

PageRequest pageRequest = PageRequest.of(
    0, 20, Sort.by(Sort.Direction.DESC, "placedAt")
);

Slice<OrderDocument> first =
    orderRepository.findHeadersByCustomer("cus-01", pageRequest);
```

`Slice` is usually suitable when you only need to know whether a next page exists; `Page` may require an additional count query. If data changes continuously, offset pagination can duplicate or skip items across reads; for long histories, consider keyset pagination over a stable key tuple.

## 6. Exclude Projection: Omitting Unneeded Fields

Instead of listing fields to receive, you can **exclude** one or more fields from the result:

```javascript
db.orders.find(
  { customerId: "cus-01" },
  { internalNote: 0, items: 0 }
);
```

The result still includes `_id`, `customerId`, `status`, `totalAmount`, `placedAt`, and `shippingAddress`. Only `internalNote` and `items` are omitted.

In the repository:

```java
@Query(
    value = "{ 'customerId': ?0 }",
    fields = "{ 'internalNote': 0, 'items': 0 }"
)
List<OrderDocument> findWithoutLargeDetails(String customerId);
```

### 6.1. Rule Against Mixing Include and Exclude

With the common exception of `_id`, **you cannot arbitrarily mix** inclusion (`1`) and exclusion (`0`) in the same standard projection:

```javascript
// Invalid: status is included while items is excluded.
db.orders.find(
  {},
  { status: 1, items: 0 }
);
```

Two valid alternatives:

```javascript
// Return only selected fields, omitting _id:
db.orders.find({}, { status: 1, totalAmount: 1, _id: 0 });

// Return all fields except items and internalNote:
db.orders.find({}, { items: 0, internalNote: 0 });
```

MongoDB has special exceptions/projection operators such as `$meta` or `$slice` with their own rules; before using them, verify exact syntax and the deployed server version. For list APIs, the easiest option to read is usually explicitly including each allowed field.

### 6.2. Why Is Include Safer for Stable APIs?

Suppose next year a `fraudAssessment` or `paymentProviderSecret` field is added to documents. A projection **excluding two old fields** may accidentally return the new field, whereas a projection **including the four required fields** will not expand automatically with schema changes.

That does not turn projection into a standalone security mechanism. The API must still authenticate users, enforce document- and field-level permissions, and use controlled DTOs. Still, for fixed-list endpoints, inclusion is easier to review and less prone to unintended data exposure.

## 7. Projection with Nested Objects

We have an address:

```javascript
shippingAddress: {
  recipientName: "Nguyễn An",
  city: "Đà Nẵng",
  phone: "0900000000"
}
```

If you only want the city, use dot notation:

```javascript
db.orders.find(
  { customerId: "cus-01" },
  {
    _id: 1,
    "shippingAddress.city": 1
  }
);
```

Illustrative result:

```javascript
{
  _id: "ord-1001",
  shippingAddress: {
    city: "Đà Nẵng"
  }
}
```

Similarly with `@Query(fields=...)`:

```java
@Query(
    value = "{ 'customerId': ?0 }",
    fields = "{ '_id': 1, 'shippingAddress.city': 1 }"
)
List<OrderDocument> findOrderCities(String customerId);
```

The `shippingAddress` field is partially loaded, so `recipientName` and `phone` are absent from the returned subdocument. **Never pass a partially loaded nested object into a `save` operation to update the entire entity**; doing so can wipe out unloaded fields.

### 7.1. A Nested Field Is a BSON Field, Not an Arbitrary Java Accessor

If the model uses `@Field("shipping_address")`, the BSON field name can differ. With `MongoTemplate` or a repository using mapping metadata, property names can be mapped according to schema; when writing `mongosh` queries, you must use the real BSON path.

Queries involving nested objects, field renames, or custom converters should have **BSON tests and query tests** to confirm the `fields` annotation selects the right post-mapping path.

## 8. Projection on Arrays: An Easily Overlooked Limitation

Suppose an order has multiple line items. If you write:

```javascript
db.orders.find(
  { _id: "ord-1001" },
  { "items.productName": 1, status: 1 }
);
```

MongoDB can still return the `items` array with elements containing only `productName`. This statement **limits fields per element**; it does not mean returning only one element or keeping only elements matching a condition.

Given the document:

```javascript
{
  items: [
    { productId: "p-10", productName: "Mechanical keyboard", quantity: 2 },
    { productId: "p-11", productName: "Mouse", quantity: 1 }
  ]
}
```

projecting `items.productName` can still return both names. To limit element count or select elements by condition, dedicated operators are needed.

### 8.1. Using `$slice` to Return Only a Few Elements

In `mongosh`:

```javascript
db.orders.find(
  { _id: "ord-1001" },
  {
    status: 1,
    items: { $slice: 2 }
  }
);
```

`$slice: 2` retrieves at most the first two elements of the `items` array. If the array has only one element, only one element is returned. This is **not** stable pagination for long arrays; it is simply an element cap in projection.

In the annotation, `fields` is also a JSON string for declaring supported projection operators:

```java
@Query(
    value = "{ '_id': ?0 }",
    fields = "{ 'status': 1, 'items': { '$slice': 2 } }"
)
OrderDocument findWithFirstTwoItems(String id);
```

This pattern shows how to write an operator inside field projection. Across different MongoDB APIs and Spring Data versions, verify generated queries and BSON output with integration tests.

### 8.2. `$elemMatch` Only Retrieves the First Matching Element

If you want details of the first element with `productId = "p-10"`:

```javascript
db.orders.find(
  { _id: "ord-1001" },
  {
    status: 1,
    items: { $elemMatch: { productId: "p-10" } }
  }
);
```

The `$elemMatch` projection operator selects the **first element** of the array matching the condition, if any. It is not equivalent to the document filter `{ "items.productId": "p-10" }`: the filter decides *which orders* match, while projection decides *which line items* are returned inside a matched order.

If you need complex array transformation, pagination, or grouping, consider `$filter` or `$slice` in an aggregation `$project`, or an alternative document model. Do not cram overly complex logic into `@Query(fields=...)` just to avoid writing a clear pipeline.

## 9. Do Not Use a Partially Loaded Entity to Overwrite Data

This is the single biggest risk when combining projection with CRUD.

Suppose:

```java
@Query(
    value = "{ '_id': ?0 }",
    fields = "{ '_id': 1, 'status': 1 }"
)
OrderDocument findStatusOnly(String orderId);
```

The result may carry `id` and `status`, while `customerId`, `totalAmount`, `placedAt`, `items`, `shippingAddress`, and `internalNote` are not loaded.

If afterwards:

```java
OrderDocument partial = orderRepository.findStatusOnly("ord-1001");

// DO NOT save the partial entity back to update status:
orderRepository.save(partial);
```

saving/replacing may wipe out the unread fields or fail because entity invariants/mappings are unmet. **Never treat a partial entity as a complete aggregate.**

### 9.1. When Updating One Field: Use a Conditional Update

Example transitioning an order from `PAID` to `SHIPPED` using `MongoTemplate`:

```java
import com.mongodb.client.result.UpdateResult;

import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;

public boolean markShipped(MongoTemplate template, String id) {
    Query query = Query.query(
        Criteria.where("_id").is(id)
            .and("status").is("PAID")
    );

    Update update = new Update()
        .set("status", "SHIPPED");

    UpdateResult result = template.updateFirst(
        query,
        update,
        OrderDocument.class
    );
    return result.getModifiedCount() == 1;
}
```

Only the `status` field changes. The rest of the document is not overwritten by an under-loaded entity. The status filter helps prevent invalid updates under concurrent requests.

### 9.2. Interface Projections Are a Great Choice for Read-Only APIs

Define a view with only four fields:

```java
import java.math.BigDecimal;
import java.time.Instant;

public interface OrderListView {
    String getId();
    String getStatus();
    BigDecimal getTotalAmount();
    Instant getPlacedAt();
}
```

Declare the repository method:

```java
@Query(
    value = "{ 'customerId': ?0 }",
    fields = "{ '_id': 1, 'status': 1, 'totalAmount': 1, 'placedAt': 1 }"
)
List<OrderListView> findListViewsByCustomerId(String customerId);
```

The result is an **interface-based projection** meant for reading data. It makes the return contract explicit; services cannot treat a partially populated `OrderDocument` as a full entity.

Note: projection interfaces in Spring Data have their own mapping rules. A **closed** projection with simple accessors as above usually favors optimizing the field list; an **open** projection containing SpEL expressions or target-based computations may force the framework to read more data. Do not rely on assumed optimizations without checking the actual query.

### 9.3. DTOs and API Mapping

You can convert `OrderListView` into a dedicated response DTO to avoid exposing persistence types directly in the API:

```java
import java.math.BigDecimal;
import java.time.Instant;

public record OrderSummaryResponse(
    String id,
    String status,
    BigDecimal totalAmount,
    Instant placedAt
) {
    public static OrderSummaryResponse from(OrderListView view) {
        return new OrderSummaryResponse(
            view.getId(),
            view.getStatus(),
            view.getTotalAmount(),
            view.getPlacedAt()
        );
    }
}
```

If you want the repository to return a DTO directly, Spring Data provides class-based projection mechanisms, though behavior depends on constructors, metadata, and query methods. Check mapping rules for your version and always verify BSON/queries. Using an interface projection and mapping to a DTO is a clean way to demonstrate `fields` without relying on complex subtleties.

## 10. Comparing `@Query(fields=...)` with `MongoTemplate`

### 10.1. Repository: Static, Reusable Projection

A method:

```java
@Query(
    value = "{ 'status': ?0 }",
    fields = "{ '_id': 1, 'status': 1, 'totalAmount': 1 }"
)
List<OrderListView> findViewsByStatus(String status);
```

fits when an endpoint or use case uses a stable field set. The method name conveys query intent, while `fields` publishes the loaded data contract.

### 10.2. MongoTemplate: Dynamic Projection per Use Case

When building queries with multiple dynamic conditions, you can use `Query.fields()`:

```java
import java.util.List;

import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

public List<OrderDocument> findPaidHeads(
    MongoTemplate template,
    String customerId
) {
    Query query = Query.query(
        Criteria.where("customerId").is(customerId)
            .and("status").is("PAID")
    );

    query.fields()
         .include("_id")
         .include("status")
         .include("totalAmount")
         .include("placedAt");

    return template.find(query, OrderDocument.class);
}
```

Semantically, this is equivalent to setting `fields = "{ '_id': 1, 'status': 1, 'totalAmount': 1, 'placedAt': 1 }"` in the repository. The resulting `OrderDocument` here is still a partial entity; use it strictly for reads.

To exclude fields:

```java
query.fields()
     .exclude("internalNote")
     .exclude("items");
```

Do not chain `include("status")` and `exclude("items")` on the same query in an invalid include/exclude mix. The `_id` exception can be included or excluded as needed.

### 10.3. When to Choose Which Approach?

| Criterion | `@Query(fields=...)` | `MongoTemplate Query.fields()` |
| --- | --- | --- |
| Fixed projection | Concise in repository interface | Must build query in service/helper |
| Dynamic conditions and field sets | Not the most flexible option | Easy to add conditional include/exclude |
| JSON query requiring review | Visible right in the annotation | Visible in `Query`-building code |
| Multi-stage operations like `$group`, `$lookup` | Not suitable for general pipelines | Use `Aggregation` and `aggregate` |
| Testing | Call repository method and verify results | Call service/template and inspect data |
| Impact on partial entities | Yes, if returning an entity | Yes, if returning an entity |

Both options use the Spring Data MongoDB model, and both require measurement. Do not switch to `MongoTemplate` merely thinking `@Query` lacks projection support; the `fields` attribute addresses this common need directly.

## 11. `fields` Is Not the Same as Aggregation `$project`

In MongoDB, `find(..., projection)` selects fields in standard query results. In an aggregation pipeline, the `$project` stage can create fields, rename them, evaluate expressions, and drop fields.

Example: display only order ID, amount, and a status label:

```javascript
db.orders.aggregate([
  { $match: { customerId: "cus-01" } },
  {
    $project: {
      _id: 1,
      totalAmount: 1,
      statusLabel: {
        $cond: [
          { $eq: ["$status", "PAID"] },
          "Paid",
          "Unpaid"
        ]
      }
    }
  }
]);
```

`statusLabel` is not an original document field; it is computed inside the pipeline. That goes beyond a simple inclusion projection.

In Spring Data MongoDB, you can use `Aggregation` with `MongoTemplate.aggregate(...)` to express the equivalent pipeline. Do not treat `@Query(fields=...)` as a full replacement for aggregation when the use case needs `$lookup`, `$group`, or complex calculations.

Another distinction to note: `fields` in `@Query` **does not alter the filter**. For example, a query filtering by `customerId` without including `customerId` still finds the customer's orders; filtered fields do not have to appear in the response.

## 12. Projection and Indexes: Is It Actually Faster?

### 12.1. Projection Reduces Transferred Data, Not Always Documents Read

When projection returns only a few small fields, MongoDB normally sends less data over the wire and the client decodes fewer fields. On the server side, however, **it may still need to read the original documents** to extract the selected fields.

Therefore, never claim "projection makes queries many times faster" without measuring. For collections with small documents over a fast network, the difference may be minor; for large documents containing long arrays, data-transfer savings can be substantial.

### 12.2. Covered Queries

If every field needed for filtering and every field to return resides in a suitable index, MongoDB can answer the query solely from the index without reading base documents: this is a **covered query**. Example on a test database:

```javascript
db.orders.createIndex({
  customerId: 1,
  status: 1,
  totalAmount: 1
});

db.orders.find(
  { customerId: "cus-01", status: "PAID" },
  {
    _id: 0,
    customerId: 1,
    status: 1,
    totalAmount: 1
  }
).explain("executionStats");
```

Because `_id` is normally returned automatically yet is absent from the index above, this covered-query example **explicitly sets `_id: 0`**. When other conditions align, a covered query plan can achieve `totalDocsExamined = 0`. This is a **possibility**, not a guarantee across all MongoDB versions, datasets, and query planners.

If you also need to sort by `placedAt`, project `shippingAddress.city`, or use a mismatched collation, that index may not suffice. Multikey indexes, array projections, and certain expression types also carry specific restrictions. Design indexes for **filter + sort + projection** and measure with `explain("executionStats")`.

### 12.3. Indexing for Actual Read Patterns

A customer's most recent orders typically filter by `customerId` and sort by `placedAt`:

```javascript
db.orders.createIndex({
  customerId: 1,
  placedAt: -1
});

db.orders.find(
  { customerId: "cus-01" },
  { status: 1, totalAmount: 1, placedAt: 1 }
)
.sort({ placedAt: -1 })
.limit(20)
.explain("executionStats");
```

This index helps filter and sort, yet **does not necessarily cover** the entire projection because `status` and `totalAmount` are not in the index; moreover, `_id` is returned by default. Before adding every field into an index just to "cover" a single use case, weigh index size, write amplification, cache footprint, and query frequency. Do not index every field mechanically.

### 12.4. Separating Query Measurement from End-to-End API Measurement

Client-perceived latency includes network, deserialization, Java mapping, service logic, and response serialization. You can measure:

- `totalDocsExamined` and `totalKeysExamined` in `explain("executionStats")`.
- Returned document payload size and network time.
- Number of fields and array sizes loaded.
- Time converting `Document` into entities or projection interfaces.
- Total endpoint latency and tail percentiles under load.

An observation breakdown prevents optimizing projection when the real bottleneck is a missing-index query or N+1 queries loading references.

## 13. Impact on Security and API Contracts

An endpoint listing a customer's orders must never use `@Query(value="{}")` and only restrict `fields`, because projection **does not filter which customer owns an order**. You need a filter condition tied to the authenticated identity and business-layer authorization checks.

Example:

```java
@Query(
    value = "{ 'customerId': ?0 }",
    fields = "{ '_id': 1, 'status': 1, 'totalAmount': 1, 'placedAt': 1 }"
)
List<OrderListView> findCustomerHistory(String customerId);
```

`customerId` must come from the authenticated identity or an authorized workflow; **never blindly trust a customer ID supplied by the API caller** if they are not allowed to view other customers' orders.

Using an include projection lowers the chance of accidentally returning `internalNote` and `shippingAddress.phone`, but is insufficient on its own to protect data from unauthorized users. Access policies, validation, masking/redaction, and response DTOs must be designed explicitly.

Never let clients pass an arbitrary JSON string directly into `@Query` or `MongoTemplate`. Use properly typed parameter binding and an application-controlled allowlist of fields. Any "dynamic field selection" API needs an allowlist, depth/count caps, and per-field-group permission checks.

## 14. Do Reactive Repositories Use Projection Similarly?

Yes. With `ReactiveMongoRepository`, `@Query(fields=...)` still expresses projection in JSON queries, while results arrive via `Flux`/`Mono`:

```java
import org.springframework.data.mongodb.repository.Query;
import org.springframework.data.mongodb.repository.ReactiveMongoRepository;

import reactor.core.publisher.Flux;

public interface ReactiveOrderRepository
        extends ReactiveMongoRepository<OrderDocument, String> {

    @Query(
        value = "{ 'customerId': ?0 }",
        fields = "{ '_id': 1, 'status': 1, 'totalAmount': 1, 'placedAt': 1 }"
    )
    Flux<OrderListView> findListViews(String customerId);
}
```

Reactive access does not change include/exclude/`_id` rules, does not automatically strip sensitive fields, and does not guarantee index usage. If using `ReactiveMongoTemplate`, you can build a `Query` with `fields().include(...)` similarly and call `find(...)` returning `Flux`.

Projection also **does not create a transaction** or a consistent snapshot across multiple queries. If the system requires multi-document transactions, configure the proper manager/session (imperative uses `MongoTransactionManager`; reactive has `ReactiveMongoTransactionManager`) and define business boundaries. For an ordinary list-read query, opening a transaction just because `fields` is used is usually unnecessary.

Avoid calling `block()` inside a WebFlux pipeline just to retrieve a projection. And never take a partial entity read from a reactive repository and `save` it as if it held complete data.

## 15. Testing: Verifying Real MongoDB Only Returns Selected Fields

A unit test mocking `OrderRepository` does not prove `@Query(fields=...)` was translated into the right BSON projection. To verify, run an **integration test against MongoDB** (for example using Testcontainers) writing a full document and reading via the repository/template.

### 15.1. Writing a Repository Projection Test

Example using `@DataMongoTest` and JUnit 5; the environment needs a dedicated test MongoDB configuration. In real tests, IDs should be unique or data cleaned between runs:

```java
import static org.assertj.core.api.Assertions.assertThat;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;

@DataMongoTest
class OrderQueryFieldsTest {

    @Autowired OrderRepository orders;

    @Test
    void returnsOnlyRequestedFieldsInListProjection() {
        OrderDocument full = new OrderDocument(
            "ord-projection-test",
            "cus-test",
            "PAID",
            new BigDecimal("1850000.00"),
            Instant.parse("2026-11-20T02:00:00Z"),
            new OrderDocument.ShippingAddress(
                "Nguyễn An", "Đà Nẵng", "0900000000"
            ),
            "Internal note",
            List.of(new OrderDocument.OrderItem(
                "p-10", "Mechanical keyboard", 2,
                new BigDecimal("925000.00")
            ))
        );

        orders.insert(full);

        List<OrderListView> views =
            orders.findListViewsByCustomerId("cus-test");

        assertThat(views).hasSize(1);
        assertThat(views.get(0).getId())
            .isEqualTo("ord-projection-test");
        assertThat(views.get(0).getStatus()).isEqualTo("PAID");
        assertThat(views.get(0).getTotalAmount())
            .isEqualByComparingTo("1850000.00");
    }
}
```

This test verifies the fields returned at the Java layer and that the method runs against real data. However, it **does not by itself prove** MongoDB omitted other fields over the wire, because interface projections can sometimes be backed by more data than necessary depending on mapping behavior.

### 15.2. Verifying the Actual BSON Projection

Using `mongosh` after creating the test document:

```javascript
const projected = db.orders.findOne(
  { _id: "ord-projection-test" },
  { _id: 1, status: 1, totalAmount: 1, placedAt: 1 }
);

print(EJSON.stringify(projected, null, 2, { relaxed: false }));

// Verify sensitive/unselected fields do not appear in the projected result:
print(Object.prototype.hasOwnProperty.call(projected, "internalNote"));
print(Object.prototype.hasOwnProperty.call(projected, "shippingAddress"));
print(Object.prototype.hasOwnProperty.call(projected, "items"));
```

The last three `hasOwnProperty` calls are expected to print `false`. This checks the **equivalent projection in MongoDB**, not yet proof that Spring Data sent that exact projection from the annotation. To verify the actual path, enable command monitoring in a test environment or inspect the MongoDB command sent by the driver/Spring Data (avoiding logging sensitive data). Inspect the projection fields of the executed query.

### 15.3. Negative and Regression Testing

| Case | What to Verify |
| --- | --- |
| No `fields` declared | Query returns full document per standard mapping |
| Include `status` and `totalAmount` | `items`/`internalNote` are absent from returned BSON |
| Include with `_id: 0` | No `_id`; ID accessor may be missing |
| Exclude `items` | Remaining fields are still returned |
| Nested projection `shippingAddress.city` | Only subfield `city` is kept inside address |
| `items.productName` | Returns names in array without implicitly capping element count |
| `$slice` on `items` | Returned element count is capped per syntax |
| Entity read with missing fields then `save` | Must not be used as safe update; service must use another path |
| Changing `@Field` or converter | Projection and query still target the real BSON field |
| Index differs from projection | Measure `explain`; do not assume a covered query |

If the system holds multi-version legacy data, add tests where documents lack fields or store different types (e.g., `totalAmount` as string instead of BSON decimal). Projection does not fix legacy data types.

## 16. Common Mistakes When Using `fields`

**Mistake 1: confusing `fields` with a filter.** Writing `fields="{ 'status': 1 }"` does not select only PAID orders. Filter conditions must be declared in `value`, such as `"{ 'status': 'PAID' }"`.

**Mistake 2: forgetting `_id` is still returned.** If results must omit the ID, explicitly write `'_id': 0`. Conversely, if the view needs the ID, do not exclude it.

**Mistake 3: invalidly mixing include and exclude.** `"{ 'status': 1, 'items': 0 }"` is normally invalid. Choose either inclusion or exclusion mode, with the `_id` exception.

**Mistake 4: saving back a partial entity.** A repository returns a field-missing `OrderDocument`, and the application calls `save`, potentially losing data. Create a read-model/DTO or use targeted field updates.

**Mistake 5: treating nested field projection as array pagination.** `items.productName` selects a field within each element; it does not limit the number of line items. Use `$slice` or a suitable pipeline when needed.

**Mistake 6: assuming projection always produces a covered query.** An index only covers when it contains all needed components; returning `_id` by default also affects coverability.

**Mistake 7: using exclude to protect newly added sensitive fields.** As the schema gains fields, an old exclusion list can inadvertently return new fields. Use include/DTOs and authorization checks.

**Mistake 8: using Java property names instead of BSON names in raw queries.** Repositories and `MongoTemplate` apply mapping metadata, whereas `mongosh`/raw drivers require real BSON names. Test after introducing `@Field` or converters.

**Mistake 9: looking only at interface projection results and assuming MongoDB reduced transferred data.** Verify the actual command/projection and measure latency and response size.

**Mistake 10: ignoring sort and pagination.** Returning fewer fields while still scanning/loading hundreds of thousands of orders can remain slow and memory-heavy. Combine projection with `limit`/`Pageable`, sorting, and suitable indexes.

## 17. Complete Practice Workflow

1. Create an `orders` document containing complete details, including `items`, `shippingAddress`, and `internalNote`.
2. Run `mongosh find(filter, projection)` to observe the difference between a full query and a query including only four fields.
3. Define `@Query(value=..., fields=...)` in `OrderRepository`, toggling `_id` on and off.
4. Switch to the `OrderListView` interface so the endpoint returns a read-only contract rather than a partial entity.
5. Try excluding `items` and compare payload size against the include projection.
6. Test `shippingAddress.city`, `items.productName`, and `$slice` projections and inspect the resulting JSON structure.
7. Build the equivalent query with `MongoTemplate.Query.fields()` and compare results.
8. Create an index for the actual filter/sort pattern; run `explain("executionStats")` to check for `COLLSCAN`/`IXSCAN` and whether the query is covered.
9. Write integration tests to protect DTO/projection output and verify real BSON after schema changes.
10. Review security: permission-scoped filters, field allowlists, and preventing sensitive data exposure.

## 18. Checklist Before Deploying `@Query(fields)` to Production

| Question | Rule to Verify |
| --- | --- |
| Which documents is the query **filtering**? | Check `value` and access permissions; do not confuse with `fields` |
| Which fields does the API need? | Prefer explicit include when the response contract is fixed |
| Is `_id` needed? | MongoDB includes it by default; omit via `_id: 0` when appropriate |
| Are include and exclude mixed? | Do not mix arbitrarily; remember the `_id` exception |
| Are there nested fields or arrays? | Use dot notation; distinguish selecting fields from selecting elements |
| Does the returned Java object omit fields? | Never `save` a partial entity; prefer a view/DTO |
| Are Java and BSON names aligned? | Check `@Field` and raw BSON; test when mapping changes |
| Is the dataset large? | Paginate, sort, index, and cap returned document count |
| Does it truly reduce transferred data? | Inspect actual command, payload size, and measure end-to-end |
| Is it a covered query? | Check index, `_id`, and `explain` |
| Is sensitive data protected? | Authorization, field allowlist, and response DTO |
| Is it tested against real MongoDB? | Test repository/template, projections, nesting, and schema regression |

**Conclusion:** the `fields` attribute in `@Query` is Spring Data MongoDB's direct tool for instructing MongoDB to **return only the required fields**. Understanding include/exclude, the `_id` default, nested fields, and array limitations keeps list queries leaner and easier to govern. Combine it with interface projections/DTOs, `MongoTemplate` for dynamic queries, indexes and `explain` for performance measurement, plus thorough testing and access controls. Most importantly: **projection only limits read data—it never modifies stored documents and never turns a partially loaded entity into something safe to save back**.
