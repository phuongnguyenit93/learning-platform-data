# Nested Projections and Limiting Loaded Data

> **Chapter:** Projection and DTO  
> **Module:** `SPRING_DATA_MONGODB` — using Spring Data MongoDB to connect, map documents, query with `MongoTemplate` or repositories, design queries, and benchmark performance.  
> **Goal:** Distinguish nested interface projections from class-based DTOs, know when Spring Data can limit queried fields, write explicit MongoDB field projections, and avoid confusing hiding fields in the API with not loading them from the database.

## 1. What Problem Does Projection Solve?

An order document can contain a lot of information: customer details, shipping address, product line items, internal notes, and operation history. Yet a list screen usually only needs **order ID, state, customer name, and city**.

If every request reads the entire document before converting it into a small DTO, the application may still:

- Receive unnecessary fields over the MongoDB connection.
- Decode BSON and instantiate Java objects for redundant data.
- Increase heap usage, GC pressure, and processing time, especially with large arrays.
- Accidentally expose information when logging or mistakenly serializing a full entity.

**Projection** is the technique of fetching or presenting only a subset of an entity's properties. In Spring Data MongoDB, separate three layers:

| Layer | Question | Example |
| --- | --- | --- |
| **MongoDB field projection** | Which BSON fields does the server return? | `{ state: 1, "customer.name": 1 }` |
| **Spring Data projection** | Which Java shape does the repository provide? | `OrderCardView`, `OrderCardDto` |
| **API DTO/JSON** | Which fields does the client see? | `{ "id": "o401", "customer": { "name": "An" } }` |

A DTO without an email field **does not by itself prove** that email was not read from MongoDB. Especially with nested projections, a Java proxy might expose only `customer.name`, while the query still fetches the entire `customer` object or other data depending on the projection style and query optimization.

The goal of this lesson is to understand both the **result shape** and the **actual data volume loaded**.

## 2. Test Data and Domain Model

The `mongosh` commands below are only for an isolated practice database. Create a dedicated collection for this lesson:

~~~javascript
use spring_data_mongodb_lab

const orders = db.orders_projection_demo_004;

orders.insertMany([
  {
    _id: "o401",
    state: "PAID",
    customer: {
      name: "An",
      email: "an@example.invalid",
      phone: "0000000001",
      segment: "VIP"
    },
    shippingAddress: {
      city: "Hanoi",
      street: "Street A",
      postalCode: "100000",
      deliveryInstructions: "Deliver during business hours"
    },
    lines: [
      { sku: "A", quantity: 1, unitPriceVnd: 120000, internalCostVnd: 80000 },
      { sku: "B", quantity: 8, unitPriceVnd: 20000, internalCostVnd: 9000 }
    ],
    internalNotes: "Staff-only information",
    auditTrail: [
      "CREATED", "CONFIRMED", "PACKED", "PAID"
    ],
    createdAt: ISODate("2026-10-01T08:00:00Z")
  },
  {
    _id: "o402",
    state: "PAID",
    customer: {
      name: "Binh",
      email: "binh@example.invalid",
      phone: "0000000002",
      segment: "STANDARD"
    },
    shippingAddress: {
      city: "Ho Chi Minh City",
      street: "Road B",
      postalCode: "700000",
      deliveryInstructions: "Call before delivery"
    },
    lines: [
      { sku: "A", quantity: 6, unitPriceVnd: 120000, internalCostVnd: 80000 }
    ],
    internalNotes: "Internal processing note",
    auditTrail: ["CREATED", "PAID"],
    createdAt: ISODate("2026-10-02T08:00:00Z")
  },
  {
    _id: "o403",
    state: "DRAFT",
    customer: { name: "Chi", email: "chi@example.invalid" },
    lines: [],
    internalNotes: "Address not yet confirmed",
    auditTrail: ["CREATED"],
    createdAt: ISODate("2026-10-03T08:00:00Z")
    // No shippingAddress.
  }
]);
~~~

Results of the illustrative queries are computed from the three documents above, prior to any data changes. `_id` is a **BSON string**. Running `insertMany` again on the same collection raises a duplicate `_id` error; use a fresh test database/collection when resetting, and never drop a real application collection.

### 2.1. Corresponding Java Domain

Each class below resides in its own file in package `com.example.projections`. In this example, customer, address, and line item objects **are embedded**, not documents in separate collections.

~~~java
// CustomerInfo.java
package com.example.projections;

public class CustomerInfo {
    private String name;
    private String email;
    private String phone;
    private String segment;

    protected CustomerInfo() { }

    public String getName() { return name; }
    public String getEmail() { return email; }
    public String getPhone() { return phone; }
    public String getSegment() { return segment; }
}
~~~

~~~java
// ShippingAddress.java
package com.example.projections;

public class ShippingAddress {
    private String city;
    private String street;
    private String postalCode;
    private String deliveryInstructions;

    protected ShippingAddress() { }

    public String getCity() { return city; }
    public String getStreet() { return street; }
    public String getPostalCode() { return postalCode; }
    public String getDeliveryInstructions() {
        return deliveryInstructions;
    }
}
~~~

~~~java
// OrderLine.java
package com.example.projections;

public class OrderLine {
    private String sku;
    private int quantity;
    private long unitPriceVnd;
    private long internalCostVnd;

    protected OrderLine() { }

    public String getSku() { return sku; }
    public int getQuantity() { return quantity; }
    public long getUnitPriceVnd() { return unitPriceVnd; }
    public long getInternalCostVnd() { return internalCostVnd; }
}
~~~

~~~java
// OrderDocument.java
package com.example.projections;

import java.time.Instant;
import java.util.List;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.mapping.MongoId;

@Document(collection = "orders_projection_demo_004")
public class OrderDocument {
    @MongoId(FieldType.STRING)
    private String id;
    private String state;
    private CustomerInfo customer;
    private ShippingAddress shippingAddress;
    private List<OrderLine> lines;
    private String internalNotes;
    private List<String> auditTrail;
    private Instant createdAt;

    protected OrderDocument() { }

    public String getId() { return id; }
    public String getState() { return state; }
    public CustomerInfo getCustomer() { return customer; }
    public ShippingAddress getShippingAddress() {
        return shippingAddress;
    }
    public List<OrderLine> getLines() { return lines; }
    public String getInternalNotes() { return internalNotes; }
    public List<String> getAuditTrail() { return auditTrail; }
    public Instant getCreatedAt() { return createdAt; }
}
~~~

`@MongoId(FieldType.STRING)` ensures `_id` is always a BSON string, even if a value happens to be a 24-character hex string. `CustomerInfo`, `ShippingAddress`, and `OrderLine` do not need `@Document` because they only serve as embedded components of `OrderDocument`.

## 3. Closed Interface Projection: Declare Only Needed Getters

In Spring Data, a **closed interface projection** is an interface whose accessors can be derived from properties of the aggregate/domain. For instance, a list screen needs:

~~~java
// CustomerNameView.java
package com.example.projections;

public interface CustomerNameView {
    String getName();
}
~~~

~~~java
// AddressCityView.java
package com.example.projections;

public interface AddressCityView {
    String getCity();
}
~~~

~~~java
// LineBriefView.java
package com.example.projections;

public interface LineBriefView {
    String getSku();
    int getQuantity();
}
~~~

~~~java
// OrderCardView.java
package com.example.projections;

import java.util.List;

public interface OrderCardView {
    String getId();
    String getState();
    CustomerNameView getCustomer();
    AddressCityView getShippingAddress();
    List<LineBriefView> getLines();
}
~~~

`OrderCardView` is a **nested** projection:

~~~text
OrderCardView
├── id
├── state
├── customer: CustomerNameView
│   └── name
├── shippingAddress: AddressCityView
│   └── city
└── lines: List<LineBriefView>
    ├── sku
    └── quantity
~~~

It does not declare `customer.email`, `customer.phone`, `shippingAddress.street`, `lines.internalCostVnd`, or `internalNotes`. Those attributes are therefore **absent from the projection API**. However, **not exposing a getter** does not guarantee the server only sends the declared leaf fields.

### 3.1. Repository Returning Projections Instead of Entities

~~~java
// OrderRepository.java
package com.example.projections;

import java.util.List;
import java.util.Optional;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface OrderRepository
        extends MongoRepository<OrderDocument, String> {

    List<OrderCardView> findByState(String state);

    Page<OrderCardView> findByState(
        String state, Pageable pageable
    );

    <T> Optional<T> findById(String id, Class<T> type);
}
~~~

Usage:

~~~java
List<OrderCardView> cards =
    repository.findByState("PAID");

for (OrderCardView card : cards) {
    System.out.println(card.getId());
    System.out.println(card.getCustomer().getName());
    System.out.println(card.getShippingAddress().getCity());
}
// On the original data: o401/An/Hanoi and o402/Binh/Ho Chi Minh City.
~~~

Spring Data creates the projection at the repository layer—typically via a proxy for interfaces—so calling code depends only on the defined accessors. When an embedded field is missing, such as `shippingAddress` on `o403`, `getShippingAddress()` can be `null`; avoid dereferencing it directly without null checks.

### 3.2. Does a Closed Projection Always Make MongoDB Load Only Individual Getters?

**Do not assume so.** Spring Data MongoDB can use projection metadata to optimize the query's field list, yet the scope of optimization depends on:

- Projection kind (closed, open, dynamic, class/DTO).
- Whether a field is a **top-level** property or a nested object/array.
- Repository-derived query, manually declared query, or `MongoTemplate`.
- The Spring Data MongoDB version and mapping rules in use.

For nested projections, the framework may need to load **the entire parent property**—such as `customer`, `shippingAddress`, or `lines`—to construct the nested proxy, even if the nested interface exposes only a few getters. Spring Data projection documentation notes optimization limitations for nested properties. Thus, distinguish:

~~~text
CustomerNameView only has getName()
          ≠
Guarantee that MongoDB only sends customer.name
~~~

If payload reduction is a critical requirement for performance or security, declare **explicit field selection** (`@Query(fields=...)`/`MongoTemplate`/aggregation), then verify the actual BSON and executed command.

## 4. MongoDB Field Projection: Limiting BSON Right at the Server

### 4.1. From Full Queries to Field-Selected Queries

A query without field projection:

~~~javascript
orders.find({ state: "PAID" });
~~~

ordinarily returns **all fields** of `o401` and `o402`, including `email`, `phone`, `internalNotes`, `auditTrail`, and all `lines` elements.

If you only need ID, state, customer name, and city:

~~~javascript
orders.find(
  { state: "PAID" },
  {
    _id: 1,
    state: 1,
    "customer.name": 1,
    "shippingAddress.city": 1
  }
);
~~~

For `o401`, the returned BSON structure has equivalent meaning to:

~~~javascript
{
  _id: "o401",
  state: "PAID",
  customer: { name: "An" },
  shippingAddress: { city: "Hanoi" }
}
~~~

`customer.email`, `customer.phone`, `shippingAddress.street`, `lines`, and `internalNotes` are absent from the result. This is proof that **the server returned less data**, rather than a Java DTO merely hiding getters.

### 4.2. Include/Exclude Rules

MongoDB field projections typically use `1` to include and `0` to exclude. Key rules:

- If no projection is specified, MongoDB returns all fields of matching documents.
- `_id` **is included by default** even when you only include a few other fields, unless `_id: 0` is set.
- Do not mix **include** and **exclude** for ordinary fields in the same projection; `_id` is the common exception.
- Dot notation `"customer.name": 1` lets you include only the needed child field in the resulting BSON.
- Projection does not modify source documents; it affects only the data returned by the query.

Example without `_id`:

~~~javascript
orders.find(
  { state: "PAID" },
  { _id: 0, state: 1, "customer.name": 1 }
);
~~~

However, if a DTO needs to distinguish each order by ID, do not mechanically strip `_id`. A DTO without an ID may suit statistics, yet is unsuitable for detail-view APIs or stable keyset pagination.

### 4.3. Including a Parent Object vs. Including a Child Path

~~~javascript
// Fetches all customer details inside the embedded object.
orders.find(
  { _id: "o401" },
  { customer: 1 }
);

// Fetches only the customer name inside the embedded object.
orders.find(
  { _id: "o401" },
  { "customer.name": 1 }
);
~~~

The first query brings back `email`, `phone`, and `segment` as well; the second brings only `customer.name` (plus `_id` by default). This difference explains why "nested projection in Java" and "nested field projection in MongoDB" should not be equated.

## 5. Limiting Fields via `@Query(fields = ...)`

Spring Data MongoDB lets you specify which fields to retrieve on a repository method using the `fields` attribute of `@Query`.

### 5.1. A Lean Interface Matching Selected Fields

~~~java
// OrderLightCard.java
package com.example.projections;

public interface OrderLightCard {
    String getId();
    String getState();
    CustomerNameView getCustomer();
    AddressCityView getShippingAddress();
}
~~~

Add the following method to **the same `OrderRepository` declared in Section 3.1**:

~~~java
import org.springframework.data.mongodb.repository.Query;

@Query(
    value = "{ 'state': ?0 }",
    fields = "{ '_id': 1, 'state': 1, " +
             "  'customer.name': 1, 'shippingAddress.city': 1 }"
)
List<OrderLightCard> findLightCardsByState(String state);
~~~

Invocation:

~~~java
List<OrderLightCard> lightCards =
    repository.findLightCardsByState("PAID");
~~~

Here:

1. `value` expresses the document selection criteria (filtering by `state`).
2. `fields` describes the **server-side field projection**: only the listed fields are returned.
3. The return type `OrderLightCard` defines the Java interface consuming the result.

The `?0` placeholder is bound by Spring Data from the `state` parameter, avoiding direct string concatenation of user input into JSON. If the model uses `@Field` to rename a property's BSON name, verify both the mapping and JSON query to ensure actual paths match.

### 5.2. Why Are Both `fields` and an Interface Needed?

`fields` controls the **returned BSON**; the interface controls the **Java data shape**. Think of them as two contracts:

~~~text
MongoDB:
  state, customer.name, shippingAddress.city, _id
                         ↓
Spring Data:
  OrderLightCard / CustomerNameView / AddressCityView
                         ↓
API:
  DTO serialized according to application rules
~~~

If `fields` omits a property that the projection needs, the property may become `null` or lack the data required for construction. **Do not configure a field mask that diverges from the DTO contract and silently fill defaults** so users believe data existed.

### 5.3. When Should You Avoid Fixed `fields`?

For screens with dynamic columns or multiple user roles needing different fields, repository methods with hardcoded field masks can become hard to maintain. Alternatives:

- Create a few fixed projections per use case (`OrderListCard`, `OrderDetailCard`).
- Use `MongoTemplate` and build `Query.fields()` from a predefined field **allowlist**.
- Use aggregation if you need to compute/reshape data, filter array elements, or join multiple collections.

Do not let clients pass arbitrary raw JSON projections/filters into the database when the application must enforce read permissions and limit query complexity.

## 6. `MongoTemplate`: Controlling Exactly Which Fields Are Loaded

When queries require dynamic criteria or field lists, `MongoTemplate` lets you configure field projection programmatically:

~~~java
import java.util.List;
import org.bson.Document;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

// Inside a @Service with injected MongoTemplate template:
Query query = Query.query(
    Criteria.where("state").is("PAID")
);
query.fields()
    .include("_id")
    .include("state")
    .include("customer.name")
    .include("shippingAddress.city");

List<Document> rawCards = template.find(
    query,
    Document.class,
    "orders_projection_demo_004"
);
~~~

In this example, results are read into `org.bson.Document` so you can directly observe which fields **are actually present** in BSON after MongoDB applies field projection. Unlike converting an `OrderDocument` into a DTO after full retrieval, this sends a request to the server to reduce the field list.

### 6.1. Embedded Object Structure Is Still Preserved

When including `"customer.name"`, MongoDB returns a `customer` object containing a `name` property; it **does not flatten** into a top-level field named `"customer.name"` in the resulting JSON. Thus, nested DTOs are a sensible choice for the response.

~~~java
Document first = rawCards.get(0);
Document customer = first.get("customer", Document.class);
String customerName = customer.getString("name");
~~~

The code above illustrates `o401`/`o402`, which have `customer.name`. Missing or null `customer` cases must be checked before calling `getString`.

### 6.2. Projection Can Leave an Entity Partially Loaded

You can also write:

~~~java
OrderDocument partial = template.findOne(
    query,
    OrderDocument.class
);
~~~

Yet `partial` is **not a complete entity**: fields omitted by the server may be `null`, Java default values, or unpopulated depending on property types and constructors.

**Important warning:** Do not read an entity with a partial field mask and then call `repository.save(partial)` as a normal update. In MongoDB, `save` can replace the document, causing unloaded fields to be lost or reset to defaults; `@Version` may also affect the outcome. Partially read objects should be treated as **read models**, not aggregates to be written back.

When you only want to modify a few fields, use `MongoTemplate.updateFirst()`/`updateMulti()` with `Update.set` or appropriate operators. When you need to read in order to modify the whole document, load the full entity and apply optimistic locking if business rules require it.

### 6.3. Limiting Fields via an Allowlist

A service can allow selecting specific fields, provided the list is controlled on the server:

~~~java
import java.util.Set;
import org.springframework.data.mongodb.core.query.Query;

Set<String> allowed = Set.of(
    "_id",
    "state",
    "customer.name",
    "shippingAddress.city",
    "createdAt"
);

Query query = Query.query(Criteria.where("state").is("PAID"));

for (String requestedField : requestedFields) {
    if (!allowed.contains(requestedField)) {
        throw new IllegalArgumentException("Unsupported projection field");
    }
    query.fields().include(requestedField);
}
~~~

`requestedFields` here is a size-bounded list passed in from the API layer; the snippet assumes `Criteria` is imported. Never allow selecting `customer.email` or `internalNotes` if the caller's role is not permitted. Enforce limits/pagination and prevent users from issuing overly broad queries.

## 7. Arrays of Embedded Documents: Limiting Fields **Does Not** Mean Limiting Elements

This limitation is especially easy to misunderstand when nested projections include `List<LineBriefView>`.

### 7.1. Including Only `lines.sku`

~~~javascript
orders.find(
  { _id: "o401" },
  {
    _id: 0,
    "lines.sku": 1
  }
);
~~~

Result has equivalent meaning to:

~~~javascript
{
  lines: [
    { sku: "A" },
    { sku: "B" }
  ]
}
~~~

MongoDB removed `quantity`, `unitPriceVnd`, and `internalCostVnd` **from each element**, yet it still returned **both elements** in the array. Selecting **fields** inside an array and selecting **elements** of an array are two separate questions.

### 7.2. A Filter `$elemMatch` Does Not Truncate the Returned Array

~~~javascript
orders.find({
  lines: {
    $elemMatch: {
      sku: "B",
      quantity: { $gte: 5 }
    }
  }
});
~~~

On the original data, this query selects `o401` thanks to line B × 8, yet **the returned document still contains the entire `lines` array** unless a separate field projection is used. `$elemMatch` in a **filter** selects documents; it does not mean the server trims arrays to matching elements.

### 7.3. Projection `$elemMatch` Returns Only the First Matching Element

~~~javascript
orders.find(
  { _id: "o401" },
  {
    lines: {
      $elemMatch: {
        sku: "B",
        quantity: { $gte: 5 }
      }
    }
  }
);
~~~

In the `lines` portion of the result, MongoDB returns only **the first element** satisfying `$elemMatch`. It may still carry other fields of that element such as `internalCostVnd`. If the goal is to return **all matching lines while keeping only selected fields**, use aggregation `$filter` combined with `$map`.

### 7.4. `$slice` Reduces Element Count but Not Inner Fields

~~~javascript
orders.find(
  { _id: "o401" },
  { lines: { $slice: 1 } }
);
~~~

`$slice: 1` takes **the first element** of the `lines` array, but does not automatically remove `unitPriceVnd` or `internalCostVnd` from that element. To limit both elements **and** fields simultaneously, use an expressive projection/aggregation. `$slice` is also not equivalent to paginating all line items in a system with huge arrays; consider alternative data modeling when independent line pagination is needed.

### 7.5. Aggregation `$filter` + `$map`: Selecting Both Elements and Fields

Requirement: for paid orders, return only lines with `quantity >= 5`, and include only `sku` and `quantity` in each line.

~~~javascript
orders.aggregate([
  { $match: { state: "PAID" } },
  {
    $project: {
      _id: 1,
      state: 1,
      "customer.name": 1,
      lines: {
        $map: {
          input: {
            $filter: {
              input: "$lines",
              as: "line",
              cond: { $gte: ["$$line.quantity", 5] }
            }
          },
          as: "line",
          in: {
            sku: "$$line.sku",
            quantity: "$$line.quantity"
          }
        }
      }
    }
  },
  { $sort: { _id: 1 } }
]);
~~~

Expected result:

~~~javascript
[
  {
    _id: "o401",
    state: "PAID",
    customer: { name: "An" },
    lines: [{ sku: "B", quantity: 8 }]
  },
  {
    _id: "o402",
    state: "PAID",
    customer: { name: "Binh" },
    lines: [{ sku: "A", quantity: 6 }]
  }
]
~~~

Here:

- `$match` filters **orders**.
- `$filter` filters **array elements** by `quantity`.
- `$map` rebuilds each element with only **two fields**.
- `$project` limits fields of the **output documents**.

For real data where `lines` can be null/missing, normalize it to an array, e.g., `$ifNull: ["$lines", []]`; otherwise array operators have specific rules for null or wrong-typed inputs. Spring Data MongoDB provides an Aggregation API and `MongoTemplate.aggregate(...)` to execute similar pipelines when computed DTOs are needed.

## 8. Class-Based DTOs and Records: Not Like Nested Interface Proxies

Interface projections use proxies to expose getters. **Class-based projections** return DTOs/records instantiated via constructors and do not use the same nested proxy mechanism.

### 8.1. Flat DTO

~~~java
// OrderHeadlineDto.java
package com.example.projections;

public record OrderHeadlineDto(String id, String state) {
}
~~~

In `OrderRepository`, add method:

~~~java
List<OrderHeadlineDto> findHeadlineByState(String state);
~~~

Where Spring Data supports DTO projections, constructor parameter names of the class/record are used to infer the properties to map. Records are a convenient choice thanks to their explicit canonical constructor. If a class has multiple constructors, an appropriate constructor is needed and `@PersistenceCreator` can be used per mapping rules.

**Note:** a two-field DTO does not mean every query path/version selects exactly two fields on the server. Inspect commands and field masks when payload size matters.

### 8.2. Nested DTOs Do Not Automatically Work Like Nested Interface Projections

~~~java
public record CustomerNameDto(String name) { }

public record OrderCardDto(
    String id,
    String state,
    CustomerNameDto customer
) { }
~~~

Do not assume the repository automatically generates **nested class-based projections** from these classes the way it does with `CustomerNameView` in `OrderCardView`. Class-based projections do not support nested proxying like interface projections; if exact nested results are required, consider:

- Nested **interface** projections for simple read models.
- MongoDB field projection/aggregation then mapping `Document` to a DTO with an explicit mapper.
- Dedicated DTOs receiving aggregation results directly when shape and constructor align.

For aggregated results, such as `OrderCardDto` containing `CustomerNameDto`, an explicit mapper also helps control null/missing handling and field exposure rules.

### 8.3. Open Projection with `@Value`

An interface using SpEL to compute an attribute:

~~~java
package com.example.projections;

import org.springframework.beans.factory.annotation.Value;

public interface OrderDisplayOpenView {
    @Value("#{target.customer != null ? " +
           "target.customer.name + ' / ' + target.state " +
           ": target.state}")
    String getDisplayLabel();
}
~~~

This is an **open projection**: the SpEL expression can access arbitrary properties of `target`. Because the framework cannot safely infer all fields the expression will use, it typically **does not apply closed-projection field-selection optimization**. Do not choose an open projection when the primary goal is ensuring MongoDB loads only a few BSON fields.

If display logic is complex, instead of SpEL invoking multiple properties/functions, consider computing the result in the service after querying with an **explicit field mask** or using server-side aggregation.

### 8.4. Dynamic Projection

With a generic method:

~~~java
<T> List<T> findByState(String state, Class<T> type);
~~~

You can choose the result shape at each call site:

~~~java
List<OrderCardView> cards =
    repository.findByState("PAID", OrderCardView.class);

List<OrderHeadlineDto> headlines =
    repository.findByState("PAID", OrderHeadlineDto.class);
~~~

Spring Data recognizes the `Class<T>` parameter used to select a dynamic projection. The return type and specific projection method can affect query optimization capabilities. Dynamic projection **does not** automatically enforce access constraints: do not let clients pass `OrderDocument.class` just because an endpoint accepts a DTO type name.

## 9. Nested Projections and Special Data Cases

### 9.1. Missing or Null Embedded Objects

`o403` has no `shippingAddress`. A projection:

~~~java
OrderCardView draft = repository.findById(
    "o403", OrderCardView.class
).orElseThrow();

AddressCityView address = draft.getShippingAddress();
String city = address == null ? null : address.getCity();
~~~

Do not immediately call `draft.getShippingAddress().getCity()` because the embedded object may be missing. Java `null` also does not reliably distinguish BSON `null` from a nonexistent field; if business logic needs that distinction, query raw BSON or use aggregation `$type`.

### 9.2. Large Arrays and Nested `List<...>`

`List<LineBriefView> getLines()` restricts only the **Java interface** of each line item. With thousands of elements, even if each line exposes only two getters, the application may still need to allocate **thousands of values/proxies**, and loading the source array can be expensive.

When the screen only needs "total line count" or "first five lines," better options include:

- Storing a summary field like `lineCount` kept consistent on updates.
- Using aggregation `$size` when data and indexes permit.
- Using `$slice` or `$filter`/`$map` for targeted cases.
- Splitting line items into a separate collection if independent searching, sorting, and pagination at scale are needed.

Projection cannot fix all drawbacks of storing an overly large array inside a single document.

### 9.3. `@DBRef`/`@DocumentReference` References Differ from Embedded Documents

Nested projection of an **embedded object** differs from resolving a **document reference**:

- With embedded objects, data lives inside the same BSON document.
- With `@DBRef`/`@DocumentReference`, Spring Data may have to execute queries **to other documents** to resolve values; lazy loading and round-trip counts are separate concerns.
- A nested getter does not guarantee the framework turns the reference into a server-side `$lookup` or optimizes only a few fields of the referenced target.

If a screen needs data from multiple collections, consider writing appropriate queries yourself (two reads, a separate projected read model, or `$lookup` in an aggregation). Do not view nested interface projections as a silver bullet for cross-collection query design.

## 10. Limiting Loaded Data and Real-World Performance

### 10.1. Four Costs to Observe

~~~text
MongoDB stores BSON documents
          |
          | (1) Read documents / index in the database
          v
MongoDB applies filter + projection
          |
          | (2) Transfer BSON over the network
          v
MongoDB Java Driver + Spring Data Converter
          |
          | (3) Decode / materialize Java objects or proxies
          v
Service / HTTP JSON serialization
          |
          | (4) Build response returned to client
          v
Client
~~~

A projection can reduce network traffic and object allocation. However, **do not assume** the server only needs to read a physical slice of the document from storage to produce the result. If the query still has to fetch the full document before applying projection, `totalDocsExamined` may not drop.

### 10.2. Measuring Query Results with `explain`

~~~javascript
// Compare a query returning full documents.
orders.find({ state: "PAID" })
  .explain("executionStats");

// With the same filter, but limiting fields.
orders.find(
  { state: "PAID" },
  {
    _id: 1,
    state: 1,
    "customer.name": 1,
    "shippingAddress.city": 1
  }
).explain("executionStats");
~~~

Inspect `winningPlan`, `totalKeysExamined`, `totalDocsExamined`, and `nReturned`. To measure network load and Java decoding, you also need driver/application metrics, BSON/response sizes, and benchmarks with representative data; `explain` does not directly replace end-to-end measurement.

### 10.3. Indexes and Covered Queries

Example:

~~~javascript
orders.createIndex({
  state: 1,
  "customer.name": 1,
  _id: 1
});
~~~

A query filtering on `state` and projecting only fields present in the index **may** qualify for a *covered query*, depending on the query plan and index limitations. If you also select `shippingAddress.city` and the index lacks that field, MongoDB may have to fetch the document. Array/multikey fields also impose specific constraints on covered queries.

**Do not create an index merely to satisfy a single DTO** if the workload does not warrant it. Indexes add write, storage, and maintenance overhead. Before adding one, identify important filters/sorts, run `explain` on representative real data, and evaluate selectivity.

### 10.4. Projection Is Not a Security Control

Do not rely solely on the `OrderCardView` interface to guarantee sensitive data never leaves the database or cannot appear in logs. To reduce risk:

1. Enforce access permissions by user/role and order scope right in the filter/service.
2. Use explicit DTO allowlists per endpoint.
3. When needed, send an **explicit field selection** to MongoDB so email, phone, internal cost, and internal notes are never received.
4. Never log raw full documents and never return domain entities directly if they hold internal data.
5. Test JSON responses and actual query BSON; do not only count getter methods on an interface.

Fields excluded by projection reduce the data surface the application touches, yet do not replace authentication, authorization, and tenant access checks.

## 11. Testing Nested Projections and Field Masks

Unit tests mocking `OrderRepository` can verify service-level DTO mapping, yet **do not** prove how many fields MongoDB returns or whether converters handle nested projections properly. When limiting data is required, use integration tests against a test MongoDB instance or Testcontainers.

### 11.1. Test Matrix

| Scenario | What to assert |
| --- | --- |
| Closed projection by state | Returns expected orders and nested getters |
| Missing `shippingAddress` | Does not throw `NullPointerException` when mapping DTO |
| Nested `List<LineBriefView>` | Element getters map SKU/quantity accurately |
| `@Query(fields)` | Does not load `customer.email`, `phone`, or `internalNotes` |
| `MongoTemplate` with `include("customer.name")` | Resulting BSON has `customer.name` but lacks `customer.email` |
| `lines.sku` field projection | Keeps array elements, drops unrequested fields |
| `$elemMatch` in filter | Selects matching documents without slicing the array |
| `$filter` + `$map` | Selects expected elements and expected fields in output |
| Public DTO/JSON | Does not serialize internal fields |
| Partially read entity | Never passed to `save` to overwrite other data |

### 11.2. Test Checking the Actual Returned BSON

Example test using an **exclusively test-dedicated** database and `MongoTemplate`:

~~~java
package com.example.projections;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;
import org.bson.Document;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

@DataMongoTest
class NestedProjectionFieldsTest {
    @Autowired MongoTemplate template;

    @Test
    void queryReturnsOnlyExplicitlySelectedNestedFields() {
        var collection = template.getDb()
            .getCollection("orders_projection_demo_004");
        String id = "fixture-projection-004";

        collection.deleteOne(new Document("_id", id));
        try {
            collection.insertOne(
                new Document("_id", id)
                    .append("state", "PAID")
                    .append("customer",
                        new Document("name", "Test")
                            .append("email", "private@example.invalid"))
                    .append("internalNotes", "INTERNAL")
            );

            Query query = Query.query(
                Criteria.where("_id").is(id)
            );
            query.fields()
                .include("_id")
                .include("state")
                .include("customer.name");

            List<Document> result = template.find(
                query,
                Document.class,
                "orders_projection_demo_004"
            );

            assertThat(result).hasSize(1);
            Document raw = result.get(0);
            assertThat(raw.containsKey("internalNotes")).isFalse();

            Document customer = raw.get(
                "customer", Document.class
            );
            assertThat(customer.getString("name"))
                .isEqualTo("Test");
            assertThat(customer.containsKey("email")).isFalse();
        } finally {
            collection.deleteOne(new Document("_id", id));
        }
    }
}
~~~

This test intentionally inspects the **BSON document after field projection** with `containsKey` rather than only asserting on a DTO. Fixtures are inserted/deleted only in an isolated test database; never use this ID in a shared environment. A second test should load `OrderCardView` through the repository and verify nested getters, while **not inferring from it that all nested fields were excluded on the server**.

### 11.3. Verifying Behavior of Your Spring Data Version

When upgrading Spring Data MongoDB, re-check:

- Whether derived-method queries add field masks.
- Whether nested closed projections fetch the entire parent object or only child fields.
- Whether `@Query(fields)` maps BSON names properly for `@Field` aliases.
- How DTO constructor binding behaves on missing/null fields.
- Projections of embedded arrays, especially when the array is empty or an element lacks a field.

These checks matter far more than guessing from method names or Java getter counts.

## 12. Common Errors and Diagnostics

| Symptom | Common cause | Resolution |
| --- | --- | --- |
| Small DTO yet query remains slow/network-heavy | DTO constructed **after** loading full entity; nested projection loads parent object | Inspect field mask; use `@Query(fields)`/`MongoTemplate` |
| Nested getter returns `null` | Missing field, BSON null, or omitted by query projection | Check source BSON and field selection |
| `customer.email` appears in logs even though DTO only has `getName()` | Logging entity/raw document before converting to DTO | Restrict fields fetched from server; fix logging |
| Interface getters work yet JSON has wrong shape | DTO mapping/serializer yields a different shape from API | Use explicit API DTOs and JSON tests |
| `findByState` returns entity instead of view | Return type declared as `OrderDocument` or wrong overload called | Update return type/method and test |
| Record DTO fails constructor binding | Parameters mismatch properties or ambiguous constructor | Verify property names, constructor/`@PersistenceCreator` |
| `lines.sku` returns more rows than expected | Field projection limits **fields**, not elements | Use `$filter`/`$map` or appropriate projection |
| `$elemMatch` in filter still includes whole `lines` array | Filter selects documents, not output elements | Add projection/aggregation |
| `save(partial)` drops fields | Entity was previously loaded partially | Never save partial entities; use update operators |
| `explain` does not show reduced `docsExamined` | Projection cuts network/decode but still fetches documents | Measure response size and app metrics; consider covered queries |
| Open projection does not reduce fetched fields | SpEL can access target arbitrarily | Use closed projection or explicit field masks |
| Projection exposes data outside tenant rights | Projection does not create authorization | Add tenant filters, authorization, and DTO allowlists |

## 13. Safe Projection Design Workflow

1. **Identify the use case**: list, detail page, report, or export API; each needs a different set of fields.
2. **Design the return contract**: which fields are public, which are internal, what nested shape and nullability apply.
3. **Choose the Java representation**: simple closed interface projection, flat DTO/record, or explicit mapper for complex results.
4. **Verify fields fetched from MongoDB**: for nested views, never deduce from getters; use explicit field projections when payload reduction is required.
5. **Handle arrays separately**: select fields via dot notation, select elements via `$elemMatch` projection, `$slice`, or `$filter`/`$map` depending on intent.
6. **Paginate at the right level**: `Page<OrderCardView>` paginates orders, not `lines` inside each order.
7. **Do not write back read models**: partial entities/DTOs are read-only; update via conditional `Update`.
8. **Test and measure**: check actual BSON, nested getters, JSON output, `explain`, and application performance on representative scale.

## 14. Practice Exercises

Exercises are based on the `orders_projection_demo_004` collection from Section 2, before any examples modify data.

### Exercise 1 — Predict the BSON Returned by the Server

Given:

~~~javascript
orders.find(
  { _id: "o401" },
  { _id: 0, state: 1, "customer.name": 1 }
);
~~~

List the fields present in the result and explain why `customer.email` does not appear.

**Answer:** the resulting document has `state: "PAID"` and `customer: { name: "An" }`; `_id` is absent because of `_id: 0`. The MongoDB server received a field projection including only `customer.name`; email is not returned.

### Exercise 2 — Does a Nested Interface Guarantee Less Data Is Loaded?

A `CustomerNameView` has only `String getName()`. Does that guarantee MongoDB does not load `customer.email` or `customer.phone`?

**Answer:** No. The interface restricts Java accessors, while query optimization for nested properties depends on projection style and Spring Data version. To be certain, configure a field mask such as `"customer.name": 1` and verify actual BSON/queries.

### Exercise 3 — Selecting One Field of Each Line Item

Write a query returning `lines.sku` for `o401`, without returning `quantity` and `unitPriceVnd`.

~~~javascript
orders.find(
  { _id: "o401" },
  { _id: 0, "lines.sku": 1 }
);
~~~

**Answer:** returns `lines: [{sku:"A"},{sku:"B"}]`. Both elements remain because this is a **field projection**, not element filtering.

### Exercise 4 — Returning Only High-Quantity Lines

Requirement: return **all** lines with `quantity >= 5`, including only `sku` and `quantity`. Should you use `$elemMatch` projection?

**Answer:** No, because `$elemMatch` projection returns only the first matching element. Use `$filter` to select all matching lines, then `$map` to rebuild each line with the two desired fields; see the pipeline in Section 7.5.

### Exercise 5 — Partial Read Followed by Save

A service uses `Query.fields().include("state").include("customer.name")` to read `OrderDocument`, updates `state`, and calls `repository.save(partial)`. What is the risk?

**Answer:** the entity is missing many fields because they were not loaded, and `save` can replace/overwrite the document, causing old fields to be lost or reset to defaults. Use `MongoTemplate.updateFirst()` with `Update.set("state", ...)` or load the full aggregate if you need to update the whole document and check version.

### Exercise 6 — Performance Analysis

A query returns 1,000 orders, each with 100 line items. The screen only uses customer name and status. Propose measurement and improvement steps.

**Reference answer:** use field projection including only `_id`, `state`, and `customer.name`, excluding `lines`. Add filters, result limits/pagination, and verify indexes matching filter/sort criteria. Compare BSON/response bytes, latency, and allocated Java objects; inspect `explain` without expecting `totalDocsExamined` to drop solely from selecting fewer fields.

## References

- [Spring Data Commons — Projections](https://docs.spring.io/spring-data/commons/reference/repositories/projections.html): closed/open interface projections, nested projections, DTOs, and dynamic projections.
- [Spring Data MongoDB — MongoDB-specific Query Methods](https://docs.spring.io/spring-data/mongodb/reference/mongodb/repositories/query-methods.html): `@Query(fields=...)`, projections, and repository methods.
- [Spring Data MongoDB — Template Query Operations](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-query-operations.html): `Query.fields()` and `MongoTemplate`.
- [MongoDB Manual — Project Fields to Return from Query](https://www.mongodb.com/docs/manual/tutorial/project-fields-from-query-results/): include/exclude, dot notation, and `_id` default.
- [MongoDB Manual — `$elemMatch` Projection](https://www.mongodb.com/docs/manual/reference/operator/projection/elemmatch/): returning the first matching array element.
- [MongoDB Manual — `$slice` Projection](https://www.mongodb.com/docs/manual/reference/operator/projection/slice/): limiting returned element count.
- [MongoDB Manual — `$filter` Aggregation](https://www.mongodb.com/docs/manual/reference/operator/aggregation/filter/) and [`$map`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/map/): filtering elements and reshaping results.
- [MongoDB Manual — Covered Queries](https://www.mongodb.com/docs/manual/core/query-optimization/): when queries can be satisfied from an index, and inspecting execution plans.
