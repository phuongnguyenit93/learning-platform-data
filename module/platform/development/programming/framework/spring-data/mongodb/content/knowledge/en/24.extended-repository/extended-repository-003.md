# Combining MongoOperations with Domain-Modeled Queries

> **Chapter:** Extended Repositories  
> **Module:** `SPRING_DATA_MONGODB` — using Spring Data MongoDB to connect, map documents, and work with MongoDB through `MongoTemplate` or repositories; practicing query design, aggregations, indexes, transactions, reactive access, testing, and data performance diagnostics.  
> **Goal:** Combine a standard repository with a custom repository fragment using `MongoOperations`, translate query criteria from business language into controlled `Criteria`/`Query` objects, preserve entity mapping, tenant isolation, and pagination order; know when to use `find`, `count`, `findAndModify`, projections, or aggregations and how to test those queries against real MongoDB.

## 1. Why Are Standard Repositories Not Enough?

`MongoRepository<OrderDocument, String>` is convenient for `findById`, `save`, `deleteById`, and short derived queries:

~~~java
List<OrderDocument> findByTenantIdAndState(
    String tenantId,
    OrderState state
);
~~~

However, real-world order search screens often have multiple **optional** criteria:

- Orders belonging to the authenticated tenant and matching one or more business states.
- Creation time within an interval `[from, before)`.
- Minimum total amount.
- Having **a specific line item** that satisfies both SKU and minimum quantity.
- Paginating by creation time descending, using `_id` as a secondary key for stable results.

If you create a derived method for **every combination** of fields, the repository accumulates long names, near-duplicate methods, and fragile control over critical business conditions. Concatenating `@Query` JSON strings from requests also increases the risk of wrong types, wrong BSON field names, and missing authorization predicates.

Solution: keep the **standard repository** for CRUD and use a **custom repository fragment** for complex querying. The fragment contains an implementation class using `MongoOperations` — the interface implemented by `MongoTemplate`.

~~~mermaid
flowchart TD
    A["HTTP / scheduled job"] --> B["Application service"]
    B --> C["OrderRepository"]
    C --> D["MongoRepository: CRUD / derived finder"]
    C --> E["OrderSearchRepository: custom fragment"]
    E --> F["OrderSearchRepositoryImpl"]
    F --> G["MongoOperations / MongoTemplate"]
    D --> H[("MongoDB")]
    G --> H
~~~

**Design perspective:** Queries are built from **domain concepts** (`OrderSearchFilter`, `OrderState`, "a line item with SKU A and quantity at least 5"), rather than letting the controller know about `$elemMatch`, `$gte`, collection names, or BSON field names.

## 2. Distinguishing Three Conceptual Layers

| Layer | Example | Responsibility |
| --- | --- | --- |
| **Business criteria** | `OrderSearchFilter(state, from, before, minTotal, sku, minQty)` | Expresses what the user wants to find; validates constraints and semantics |
| **Spring Data query** | `Criteria.where("state").is(PAID)`, `Query`, `Pageable` | Translates criteria into predicates, sort, limit, projection |
| **Executed BSON query** | `{ state_code: "PAID", tenant_id: "t01" }` | Contract with MongoDB; uses actual BSON names and types |

`MongoOperations` bridges the second layer to the third through `MappingMongoConverter`/`QueryMapper` when you call methods taking an **entity class**. That means:

~~~java
Criteria.where("tenantId").is("t01");
~~~

maps to a predicate on BSON field `tenant_id` if the entity declares `@Field("tenant_id")`.

Conversely, when using the MongoDB Java Driver directly:

~~~java
Filters.eq("tenant_id", "t01");
~~~

you must use the **actual BSON field name**, because the driver does not automatically interpret Spring Data's `@Field`. This lesson prioritizes `MongoOperations` with entity metadata and uses raw BSON only for verification.

## 3. Sample Dataset for Practice

### 3.1. Test Collection

Open `mongosh` on a **dedicated test database** and create the fixture below. The fixed IDs are solely for verifying results; do not re-run `insertMany` if the collection already contains these IDs.

~~~javascript
use spring_data_mongodb_lab

const orders = db.orders_extended_demo_003;

orders.insertMany([
  {
    _id: "o301", tenant_id: "t01", state_code: "NEW",
    created_at: ISODate("2026-10-01T08:00:00Z"),
    total_vnd: 150000,
    line_items: [
      { sku: "A", quantity: 1 },
      { sku: "B", quantity: 8 }
    ],
    version: NumberLong(0)
  },
  {
    _id: "o302", tenant_id: "t01", state_code: "PAID",
    created_at: ISODate("2026-10-02T08:00:00Z"),
    total_vnd: 450000,
    line_items: [
      { sku: "A", quantity: 6 },
      { sku: "C", quantity: 2 }
    ],
    version: NumberLong(0)
  },
  {
    _id: "o303", tenant_id: "t01", state_code: "NEW",
    created_at: ISODate("2026-10-03T08:00:00Z"),
    total_vnd: 800000,
    line_items: [
      { sku: "A", quantity: 3 },
      { sku: "A", quantity: 9 }
    ],
    version: NumberLong(0)
  },
  {
    _id: "o304", tenant_id: "t01", state_code: "PAID",
    created_at: ISODate("2026-10-04T08:00:00Z"),
    total_vnd: 250000,
    line_items: [
      { sku: "B", quantity: 7 }
    ],
    version: NumberLong(0)
  },
  {
    _id: "o305", tenant_id: "t02", state_code: "PAID",
    created_at: ISODate("2026-10-05T08:00:00Z"),
    total_vnd: 900000,
    line_items: [
      { sku: "A", quantity: 10 }
    ],
    version: NumberLong(0)
  },
  {
    _id: "o306", tenant_id: "t01", state_code: "CANCELLED",
    created_at: ISODate("2026-10-06T08:00:00Z"),
    total_vnd: 100000,
    line_items: [],
    version: NumberLong(0)
  },
  {
    _id: "o307", tenant_id: "t01", state_code: "PAID",
    created_at: ISODate("2026-10-04T08:00:00Z"),
    total_vnd: 650000,
    line_items: [
      { sku: "A", quantity: 5 }
    ],
    version: NumberLong(0)
  }
]);

orders.createIndex({
  tenant_id: 1,
  state_code: 1,
  created_at: -1,
  _id: -1
});
~~~

Expected results in this lesson use the **initial fixture**; write examples later on are treated as independent scenarios on the test database.

| ID | Tenant | State | Total Amount (VND) | Notable Detail |
| --- | --- | --- | ---: | --- |
| `o301` | t01 | NEW | 150,000 | Has A × 1 and B × 8; the two conditions do not belong to the same line |
| `o302` | t01 | PAID | 450,000 | Has line A × 6 |
| `o303` | t01 | NEW | 800,000 | Has A × 3 and A × 9 |
| `o304` | t01 | PAID | 250,000 | Only has B × 7 |
| `o305` | t02 | PAID | 900,000 | Belongs to another tenant |
| `o306` | t01 | CANCELLED | 100,000 | Empty line-item array |
| `o307` | t01 | PAID | 650,000 | Has A × 5; shares creation timestamp with o304 |

`o304` and `o307` have the same `created_at`. When paginating, **never sort by timestamp alone** if you want deterministic ordering; add `_id` as a tie-breaker.

### 3.2. Verifying Expected Queries with `mongosh`

Example: find orders for tenant `t01`, state `PAID`, total amount >= 400,000, and having a line with SKU `A` and `quantity >= 5`:

~~~javascript
orders.find({
  tenant_id: "t01",
  state_code: "PAID",
  total_vnd: { $gte: 400000 },
  line_items: {
    $elemMatch: {
      sku: "A",
      quantity: { $gte: 5 }
    }
  }
}).sort({ created_at: -1, _id: -1 });
// o307, o302
~~~

`o305` has A × 10 but belongs to tenant `t02`; `o303` has enough quantity and amount but is in state `NEW`; `o304` is `PAID` but lacks SKU A. This dataset lets us test both **domain predicates** and **tenant isolation**.

## 4. Domain Model and Mapping Metadata

### 4.1. State Enum

~~~java
// OrderState.java
package com.example.extended;

public enum OrderState {
    NEW, PAID, PROCESSING, CANCELLED
}
~~~

Spring Data MongoDB maps enum values by default to strings such as `"PAID"`. If the application uses a custom converter or another BSON type, verify against the real fixture.

### 4.2. Embedded Line Item

~~~java
// OrderLine.java
package com.example.extended;

public class OrderLine {
    private String sku;
    private int quantity;

    protected OrderLine() { }

    public String getSku() { return sku; }
    public int getQuantity() { return quantity; }
}
~~~

`OrderLine` is an object **embedded inside the order document**, not a separate collection. If a real design uses `@DBRef` or `@DocumentReference`, queries and reference resolution costs require different analysis.

### 4.3. Aggregate Root

~~~java
// OrderDocument.java
package com.example.extended;

import java.time.Instant;
import java.util.List;
import org.springframework.data.annotation.Version;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.mapping.MongoId;

@Document(collection = "orders_extended_demo_003")
public class OrderDocument {
    @MongoId(FieldType.STRING)
    private String id;

    @Field("tenant_id")
    private String tenantId;

    @Field("state_code")
    private OrderState state;

    @Field("created_at")
    private Instant createdAt;

    @Field("total_vnd")
    private long totalVnd;

    @Field("line_items")
    private List<OrderLine> lineItems;

    @Version
    private Long version;

    protected OrderDocument() { }

    public String getId() { return id; }
    public String getTenantId() { return tenantId; }
    public OrderState getState() { return state; }
    public Instant getCreatedAt() { return createdAt; }
    public long getTotalVnd() { return totalVnd; }
    public List<OrderLine> getLineItems() { return lineItems; }
    public Long getVersion() { return version; }
}
~~~

In this example:

- `@Document` specifies the collection.
- `@MongoId(FieldType.STRING)` stores `_id` as a BSON string.
- `@Field("tenant_id")` and similar annotations tell `MongoOperations` how to map Java paths to BSON names.
- `@Version` supports versioning in appropriate Spring Data operations; it does **not** mean every query automatically knows which version the client saw.

Do not return this entity directly from public APIs if in a real system it contains internal properties. This lesson uses a read DTO in the service when returning data externally.

## 5. Designing a MongoDB-Independent Business Filter

Controllers and services should not receive `Criteria`/`Query` from clients. Instead, define a data type representing the **search request**:

~~~java
// OrderSearchFilter.java
package com.example.extended;

import java.time.Instant;

public record OrderSearchFilter(
    OrderState state,
    Instant createdFromInclusive,
    Instant createdBeforeExclusive,
    Long minTotalVnd,
    String sku,
    Integer minLineQuantity
) {
    public OrderSearchFilter {
        if (createdFromInclusive != null
                && createdBeforeExclusive != null
                && !createdFromInclusive.isBefore(createdBeforeExclusive)) {
            throw new IllegalArgumentException(
                "createdFrom must be before createdBefore");
        }
        if (minTotalVnd != null && minTotalVnd < 0) {
            throw new IllegalArgumentException("minTotalVnd must be >= 0");
        }
        if (sku != null && sku.isBlank()) {
            throw new IllegalArgumentException("sku must not be blank");
        }
        if (minLineQuantity != null && minLineQuantity < 1) {
            throw new IllegalArgumentException(
                "minLineQuantity must be >= 1");
        }
        if (minLineQuantity != null && sku == null) {
            throw new IllegalArgumentException(
                "minLineQuantity requires sku");
        }
    }
}
~~~

`OrderSearchFilter` does not contain `tenantId`. This is deliberate: **tenant comes from the security context at the service layer**, not from an arbitrary client-chosen field.

### 5.1. Semantics of the `[from, before)` Time Interval

If `createdFromInclusive` is present, the query uses `createdAt >= from`. If `createdBeforeExclusive` is present, the query uses `createdAt < before`.

~~~text
          from                        before
           [--------------------------)
     Includes from                 Excludes before
~~~

This rule is very useful for hourly/daily reports and processing consecutive intervals without double-counting boundary timestamps. Use `Instant`/BSON Date on the UTC timeline; user display time zones should be resolved before building the filter rather than storing arbitrary `LocalDateTime` values into the database.

### 5.2. Do Not Accept Raw Field Names from HTTP

Criteria like `state`, `minTotalVnd`, and `sku` form a pre-designed set. Avoid APIs accepting:

~~~json
{
  "field": "internalDiscount",
  "operator": "$gt",
  "value": 0
}
~~~

and turning it directly into `Criteria.where(field)` without checks. That allows clients to query out-of-scope fields, issue expensive queries, or bypass tenant predicates. If the UI needs dynamic filtering over optional fields, use a server-owned **allowlist** of fields and operators.

## 6. Creating a Custom Repository Fragment

Spring Data lets you compose the main repository from a base repository and **project-defined fragment interfaces**.

### 6.1. Fragment Interface

~~~java
// OrderSearchRepository.java
package com.example.extended;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;

public interface OrderSearchRepository {
    Page<OrderDocument> search(
        String authorizedTenantId,
        OrderSearchFilter filter,
        Pageable pageable
    );
}
~~~

The name `authorizedTenantId` emphasizes that the service must pass an **authenticated tenant** into the query. In production code, the string can be replaced by a `TenantId` value object to avoid swapping parameters accidentally.

### 6.2. Main Repository Composing the Fragment

~~~java
// OrderRepository.java
package com.example.extended;

import org.springframework.data.mongodb.repository.MongoRepository;

public interface OrderRepository
        extends MongoRepository<OrderDocument, String>,
                OrderSearchRepository {
    // MongoRepository CRUD and fragment's search method.
}
~~~

Now the service layer can use a single `OrderRepository` object to call `findById`, `save`, and `search`. You do not have to subclass `SimpleMongoRepository` merely to add one complex query.

### 6.3. Implementation Naming Rules

Under repository composition rules, the fragment implementation is typically named:

~~~text
Interface:       OrderSearchRepository
Implementation:  OrderSearchRepositoryImpl
Repository:      OrderRepository extends ..., OrderSearchRepository
~~~

`OrderSearchRepositoryImpl` must lie within the package scope scanned by Spring Data and provide valid constructor injection. The default suffix is `Impl`; if your project configures a different implementation postfix, follow that configuration.

**Do not randomly create `OrderRepositoryImpl` assuming Spring Data always treats it as the fragment's sole implementation.** Tying the implementation class to the **fragment interface name** is clearer, reusable, and aligns with modern repository fragment design.

### 6.4. How Repository Composition Differs from a Second Service

You could always inject `MongoOperations` into a separate `@Service` to run queries. Fragments are helpful when you want to:

- Keep **a single data access gateway** `OrderRepository` for both CRUD and custom queries.
- Hide Spring Data implementation details from calling services.
- Reuse query logic across multiple business flows.
- Change query internals inside the fragment without altering the main repository contract.

Not every query warrants a new fragment. If you only need a simple `findByState` or `findByTenantId`, a standard derived query suffices.

## 7. Implementing the Fragment with `MongoOperations`

The class below uses read-only APIs, builds domain criteria, and separates the **count query** from the **page content query**.

~~~java
// OrderSearchRepositoryImpl.java
package com.example.extended;

import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageImpl;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.MongoOperations;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

public class OrderSearchRepositoryImpl
        implements OrderSearchRepository {

    private final MongoOperations operations;

    public OrderSearchRepositoryImpl(MongoOperations operations) {
        this.operations = operations;
    }

    @Override
    public Page<OrderDocument> search(
            String authorizedTenantId,
            OrderSearchFilter filter,
            Pageable pageable) {

        if (authorizedTenantId == null || authorizedTenantId.isBlank()) {
            throw new IllegalArgumentException("Tenant is required");
        }
        Objects.requireNonNull(filter, "filter");
        Objects.requireNonNull(pageable, "pageable");

        // Repository owns the sort rules, not trusting arbitrary UI sorts.
        if (pageable.isUnpaged()) {
            throw new IllegalArgumentException("Pagination is required");
        }
        if (pageable.getPageSize() > 100) {
            throw new IllegalArgumentException("Page size exceeds 100");
        }

        Criteria criteria = buildCriteria(authorizedTenantId, filter);
        Sort stableSort = Sort.by(
            Sort.Order.desc("createdAt"),
            Sort.Order.desc("id")
        );

        Pageable stablePageable =
            org.springframework.data.domain.PageRequest.of(
                pageable.getPageNumber(),
                pageable.getPageSize(),
                stableSort
            );

        Query contentQuery = Query.query(criteria).with(stablePageable);
        List<OrderDocument> content =
            operations.find(contentQuery, OrderDocument.class);

        // Count using the exact predicate, without skip/limit.
        Query countQuery = Query.query(
            buildCriteria(authorizedTenantId, filter)
        );
        long total = operations.count(countQuery, OrderDocument.class);

        return new PageImpl<>(content, stablePageable, total);
    }

    private Criteria buildCriteria(
            String tenantId, OrderSearchFilter filter) {

        List<Criteria> parts = new ArrayList<>();
        parts.add(Criteria.where("tenantId").is(tenantId));

        if (filter.state() != null) {
            parts.add(Criteria.where("state").is(filter.state()));
        }

        if (filter.createdFromInclusive() != null
                || filter.createdBeforeExclusive() != null) {
            Criteria time = Criteria.where("createdAt");
            if (filter.createdFromInclusive() != null) {
                time.gte(filter.createdFromInclusive());
            }
            if (filter.createdBeforeExclusive() != null) {
                time.lt(filter.createdBeforeExclusive());
            }
            parts.add(time);
        }

        if (filter.minTotalVnd() != null) {
            parts.add(
                Criteria.where("totalVnd").gte(filter.minTotalVnd())
            );
        }

        if (filter.sku() != null) {
            Criteria sameLine = Criteria.where("sku").is(filter.sku());
            if (filter.minLineQuantity() != null) {
                sameLine.and("quantity").gte(filter.minLineQuantity());
            }
            parts.add(
                Criteria.where("lineItems").elemMatch(sameLine)
            );
        }

        return new Criteria().andOperator(
            parts.toArray(new Criteria[0])
        );
    }
}
~~~

Here `MongoOperations` is an **interface**. Spring Boot/Spring Data typically provides `MongoTemplate` as the implementation bean when synchronous MongoDB is configured. Queries pass `OrderDocument.class` so the converter knows which entity is being mapped.

### 7.1. Why Doesn't This Code Accept `@Query` JSON Strings?

Conditions are built from **pre-known** fields: `tenantId`, `state`, `createdAt`, `totalVnd`, `lineItems`. Values are passed into `Criteria` using typed `OrderState`, `Instant`, `Long`, and `String`.

As a result, the same domain filter flows through:

~~~text
OrderSearchFilter
    ↓ validate
Criteria / Query
    ↓ MappingMongoConverter + QueryMapper
BSON filter with tenant_id, state_code, created_at, total_vnd, line_items
    ↓
MongoDB
~~~

There is no need to write a custom parser accepting MongoDB operators from user input.

### 7.2. Why Is the Count Query Built Separately?

The content `Query` carries `skip`, `limit`, and `sort` from `Pageable`. To return the total document count matching the filter, the code builds **a separate query** without those bounds.

~~~java
Query contentQuery = Query.query(criteria).with(stablePageable);

Query countQuery = Query.query(
    buildCriteria(authorizedTenantId, filter)
);
~~~

If you copy one query and forget to strip `skip`/`limit`, it is easy to misinterpret count semantics or rely on version-specific metadata handling. Keeping two explicit queries preserves **the exact same predicate** while clarifying intent.

Calling `operations.count(...)` can trigger an extra query, so `Page` is not always the best fit for infinite scrolling or very large lists.

### 7.3. Pagination Ordering Must Be Deterministic

`createdAt` can collide across multiple orders. The sort:

~~~java
Sort.by(
    Sort.Order.desc("createdAt"),
    Sort.Order.desc("id")
);
~~~

maps to BSON sort `created_at DESC, _id DESC`. `_id` is unique, guaranteeing a stable order when multiple documents share the same timestamp.

However, **a stable sort does not create an immutable snapshot**: if inserts/deletes/updates touch the result set between offset-page requests, records can still repeat or be skipped. For continuous traversal at large scale, consider keyset/seek pagination.

### 7.4. Limiting Page Size and Offset

In this example, page size is capped at 100. Production systems should also cap **maximum offset** or switch to cursors for deep pages. Indexes help filtering/sorting, but do not turn `skip(200000)` into a constant-cost random jump.

If the UI only needs "Load more", return `Slice<OrderDocument>` or an `items/hasNext/nextCursor` DTO instead of computing full `totalPages`.

## 8. Array Domain Semantics: Using `$elemMatch` in the Right Place

Requirement:

> An order must contain **one line item** with SKU A and `quantity >= 5`.

This is not equivalent to:

~~~javascript
{
  "line_items.sku": "A",
  "line_items.quantity": { $gte: 5 }
}
~~~

Two independent dot-notation conditions can match **two different elements** in the array. `o301` has A × 1 and B × 8: the document satisfies both predicates individually, yet **has no line with A × 5 or more**.

When the filter specifies both SKU and quantity, the fragment uses:

~~~java
Criteria sameLine = Criteria.where("sku").is("A")
    .and("quantity").gte(5);

Criteria items = Criteria.where("lineItems")
    .elemMatch(sameLine);
~~~

Thanks to `$elemMatch`, every condition inside `sameLine` is evaluated against **the same array element**.

Equivalent BSON query semantically:

~~~javascript
{
  line_items: {
    $elemMatch: {
      sku: "A",
      quantity: { $gte: 5 }
    }
  }
}
~~~

On the fixture:

| Order | Has SKU A? | Any line with quantity ≥ 5? | Has **same line A** with quantity ≥ 5? |
| --- | --- | --- | --- |
| `o301` | Yes | Yes, B × 8 | **No** |
| `o302` | Yes | Yes, A × 6 | Yes |
| `o303` | Yes | Yes, A × 9 | Yes |
| `o304` | No | Yes, B × 7 | No |
| `o305` | Yes | Yes, A × 10 | Yes, but different tenant |
| `o306` | No | No | No |
| `o307` | Yes | Yes, A × 5 | Yes |

### 8.1. Element Scope vs. Order Scope

`$elemMatch` is a predicate that **selects orders** having a matching line item. It **does not** restrict the `lineItems` field in the returned entity to only matching elements. By default, MongoDB still returns the entire array unless a separate projection/aggregation is used.

If the API needs only matching lines, design a projection (`$elemMatch` projection returns only the first matching element; aggregation `$filter` returns all matching elements). Do not confuse "filtering which documents match" with "filtering output structure."

### 8.2. Java Names vs. BSON Names

In the entity:

~~~java
@Field("line_items")
private List<OrderLine> lineItems;
~~~

With `MongoOperations.find(query, OrderDocument.class)`, Spring Data uses this metadata to map `lineItems` to `line_items`. If you drop down directly to the Java driver via `MongoCollection<Document>`, you must use `"line_items"` in BSON filters.

Isolating domain queries inside a fragment prevents the service layer from juggling two naming schemes.

## 9. Calling the Fragment from an Application Service

The controller can convert validated inputs into `OrderSearchFilter`. The service must attach the **authenticated tenant** before calling the repository:

~~~java
// OrderCard.java
package com.example.extended;

import java.time.Instant;

public record OrderCard(
    String id,
    OrderState state,
    Instant createdAt,
    long totalVnd
) {
    public static OrderCard from(OrderDocument source) {
        return new OrderCard(
            source.getId(),
            source.getState(),
            source.getCreatedAt(),
            source.getTotalVnd()
        );
    }
}
~~~

~~~java
// OrderQueryService.java
package com.example.extended;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.stereotype.Service;

@Service
public class OrderQueryService {
    private final OrderRepository repository;

    public OrderQueryService(OrderRepository repository) {
        this.repository = repository;
    }

    public Page<OrderCard> searchOrders(
            String authenticatedTenantId,
            OrderSearchFilter filter,
            Pageable pageable) {
        // authenticatedTenantId must come from a verified security context;
        // never trust a client-supplied tenant identifier.
        return repository.search(
            authenticatedTenantId, filter, pageable
        ).map(OrderCard::from);
    }
}
~~~

`Page.map(...)` transforms page content into a read DTO while keeping pagination metadata. Never return raw `OrderDocument` to external APIs if the aggregate contains internal info, large embedded structures, or sensitive fields.

**Performance warning:** The code above converts to DTO **after reading the entity**. It **does not guarantee** MongoDB sends only the four DTO fields; the server may still return the entire `line_items` array. When payload reduction matters, see field projection in section 11.

### 9.1. Sample Request

~~~java
OrderSearchFilter filter = new OrderSearchFilter(
    OrderState.PAID,
    null,
    null,
    400_000L,
    "A",
    5
);

var pageable = org.springframework.data.domain.PageRequest.of(0, 10);

Page<OrderCard> page = service.searchOrders(
    "t01", filter, pageable
);
// Initial fixture: [o307, o302], ordered by createdAt DESC, id DESC.
~~~

The query is built from `OrderSearchFilter` and the server-provided tenant. Never pass a client-created `PageRequest` straight to the repository without bounding size/sort; the fragment in section 7 replaces the sort and enforces a size cap.

## 10. Flexible Queries Without Breaking Domain Boundaries

Several refinements keep fragments maintainable as filters grow:

### 10.1. Centralize Scope Conditions in One Builder

Instead of repeating `Criteria.where("tenantId")` across the application, put the tenant predicate into a **single helper** inside the repository fragment. This reduces the chance of forgetting tenant scoping when adding new filters.

~~~java
private Criteria mandatoryScope(String tenantId) {
    return Criteria.where("tenantId").is(tenantId);
}
~~~

In applications with soft-delete rules, `deletedAt == null/missing` or an appropriate status flag can sit in the same scope helper. However, verify exact MongoDB `null` vs. missing-field semantics rather than adding speculative filters not defined by the schema.

### 10.2. Avoid an Unbounded All-Purpose "Query Object"

A record with dozens of nullable fields, arbitrary operators, multi-level `AND/OR` combinations, and client-supplied expressions is hard to validate and audit. Create focused use-case methods instead:

- `searchForBackOffice(...)`: rich filters, yet bounded.
- `findOrdersToRetry(...)`: system criteria with fixed states and time windows.
- `claimNextOrder(...)`: atomic find-and-modify operation, not search pagination.

They share a bounded context, yet **each operation has its own business contract**. `MongoOperations` is a query-expression tool, not a substitute for defining domain constraints.

### 10.3. Internal Queries Do Not Expose MongoDB Operators

The controller receives business criteria:

~~~json
{
  "state": "PAID",
  "minTotalVnd": 400000,
  "sku": "A",
  "minLineQuantity": 5
}
~~~

It never accepts a `{ "$where": "..." }` fragment or arbitrary field names. The fragment chooses allowed operators. Request validation, authentication, and authorization belong at their respective layers; `OrderSearchFilter` only enforces **structural request validity**, not the full permission model.

## 11. Projections and Reducing Data Transfer

If a list screen only needs ID, state, timestamp, and total amount, reading the whole `OrderDocument` may transfer a huge `line_items` array. Declare a field mask **before calling `find`**:

~~~java
Query lightQuery = Query.query(
    Criteria.where("tenantId").is("t01")
        .and("state").is(OrderState.PAID)
);

lightQuery.fields()
    .include("id")
    .include("state")
    .include("createdAt")
    .include("totalVnd");

List<OrderDocument> lightResults =
    operations.find(lightQuery, OrderDocument.class);
~~~

With entity type `OrderDocument.class`, Spring Data maps `id`, `state`, `createdAt`, and `totalVnd` to BSON `_id`, `state_code`, `created_at`, and `total_vnd` using entity metadata. Predicates and projections should be verified in integration tests whenever `@Field` aliases or custom converters are used.

**Important:** Each `OrderDocument` returned here is a **partial entity** — missing `lineItems` and other excluded fields. **Never call `repository.save(lightResults.get(0))`** to update a few fields: `save` may overwrite the whole document and wipe unloaded fields.

For read models, convert immediately to `OrderCard`:

~~~java
List<OrderCard> cards = lightResults.stream()
    .map(OrderCard::from)
    .toList();
~~~

To reduce overhead and avoid partial entities more cleanly, you can use aggregation `$project` mapped directly to a DTO, or define use-case projections. With **nested projections**, do not assume Java getters limit which embedded fields MongoDB sends over the wire; inspect the actual query and BSON response.

### 11.1. Count Queries Do Not Need to Fetch Entities

If you only need a total count, call:

~~~java
long total = operations.count(
    Query.query(Criteria.where("tenantId").is("t01")
        .and("state").is(OrderState.PAID)),
    OrderDocument.class
);
~~~

`count` asks the server to count matching documents; there is no need for `find(...).size()` materializing every document. At large scale, filtered counts still have a cost — use `Slice`/cursors when the UI does not need total page counts.

## 12. Beyond `find`: Domain-Driven Queries and Writes

`MongoOperations` provides more than `find`. When the domain logic is **"take the oldest NEW order and transition it to PROCESSING"**, reading an entity and later calling `save` creates a race between two workers.

### 12.1. Anti-Pattern: Read Followed by Unconditional Update

~~~java
// Do not use this pattern for concurrent job claiming:
// OrderDocument oldest = repository.search(...).getContent().get(0);
// oldest.setState(PROCESSING);
// repository.save(oldest);
~~~

Two workers can read the same `NEW` order and both believe they claimed the job. Using `@Version` with `save` detects conflicts, yet still requires retry handling; **do not rely on separate read/write steps** when an atomic claim is needed.

### 12.2. `findAndModify` Selects and Updates One Document

Add a dedicated method to the fragment:

~~~java
// Add to OrderSearchRepository:
OrderDocument claimOldestNew(String authorizedTenantId);
~~~

In `OrderSearchRepositoryImpl`, add:

~~~java
import org.springframework.data.mongodb.core.FindAndModifyOptions;
import org.springframework.data.mongodb.core.query.Update;

@Override
public OrderDocument claimOldestNew(String authorizedTenantId) {
    if (authorizedTenantId == null || authorizedTenantId.isBlank()) {
        throw new IllegalArgumentException("Tenant is required");
    }

    Query query = Query.query(
        Criteria.where("tenantId").is(authorizedTenantId)
            .and("state").is(OrderState.NEW)
    );
    query.with(Sort.by(
        Sort.Order.asc("createdAt"),
        Sort.Order.asc("id")
    ));

    return operations.findAndModify(
        query,
        new Update().set("state", OrderState.PROCESSING),
        FindAndModifyOptions.options().returnNew(true),
        OrderDocument.class
    );
}
~~~

`findAndModify` performs a **single-document find-and-update** in MongoDB, honoring sort order and returning the modified document. On the initial fixture for tenant `t01`, the oldest `NEW` order is `o301`; the first call transitions `o301` to `PROCESSING`, and the next call selects `o303` assuming no other changes.

The `state = NEW` condition is evaluated **atomically with the update**. This fits worker queues well, though claiming multiple orders in a loop does not turn the loop into a multi-document atomic transaction.

### 12.3. Conditional Counter Increment

Another domain behavior is "increment retry count for an order in PROCESSING":

~~~java
import com.mongodb.client.result.UpdateResult;

UpdateResult result = operations.updateFirst(
    Query.query(
        Criteria.where("id").is("o301")
            .and("tenantId").is("t01")
            .and("state").is(OrderState.PROCESSING)
    ),
    new Update().inc("retryCount", 1),
    OrderDocument.class
);
~~~

**Separate example:** the `OrderDocument` entity in section 4 does not declare `retryCount`. To run this snippet, add the Java property (and mapping if BSON uses a different name) and initialize numeric values on documents; this illustrates extending the model rather than running verbatim on the current fixture.

To keep the fixture schema intact, a schema-compatible update is:

~~~java
UpdateResult result = operations.updateFirst(
    Query.query(Criteria.where("id").is("o301")
        .and("tenantId").is("t01")
        .and("state").is(OrderState.NEW)),
    new Update().set("state", OrderState.PROCESSING),
    OrderDocument.class
);
~~~

When no document matches, `getMatchedCount()` is 0. That could mean the ID does not exist, tenant mismatches, or state already changed. Do not automatically translate that to `404` or `409` without defining the API contract.

## 13. Versioning, Entity Lifecycle, and Consistency

The entity declares `@Version`. Distinguish carefully:

1. `repository.save(loadedEntity)` performs optimistic locking based on the entity's mapped version.
2. `operations.updateFirst(Query, Update, Class)` is a **query-based update**; Spring Data may auto-increment version when the update does not explicitly set it.
3. If business rules require **rejecting stale writers**, the query must carry the **expected version**, or use a version-aware entity operation.

Example filtering by ID, tenant, state, and version:

~~~java
long expectedVersion = 0L;

Query guarded = Query.query(
    Criteria.where("id").is("o301")
        .and("tenantId").is("t01")
        .and("state").is(OrderState.NEW)
        .and("version").is(expectedVersion)
);

UpdateResult result = operations.updateFirst(
    guarded,
    new Update().set("state", OrderState.PROCESSING),
    OrderDocument.class
);

if (result.getMatchedCount() == 0) {
    throw new IllegalStateException(
        "Order missing, state changed or version conflict"
    );
}
~~~

`@Version` cannot infer from a versionless query that the user previously read version 0. Do not confuse **auto-incrementing version** with **checking expected version**.

### 13.1. Single Document vs. Multiple Documents

A suitable `updateFirst`/`findAndModify` is atomic at the **single-document** level. If a fragment calls `updateMulti` across multiple orders, each document update is atomic individually, but the batch does not automatically commit/roll back as a transaction.

When all-or-nothing across multiple documents is required, evaluate `MongoTransactionManager`, shared MongoDB database factory/session, and transaction-capable topology. Transactions carry overhead and constraints; do not apply them mechanically to every complex query.

### 13.2. Query-Based Writes Are Not `save(entity)`

Do not assume `Update`/`findAndModify` triggers all entity callbacks, Bean Validation, or custom audit/write logic the way `save` does. For critical business invariants:

- Put state-transition preconditions directly into the query.
- Choose proper update operators and check matched/modified counts.
- Design audit/outbox records or transactions when needed.
- Test against real MongoDB with your configured converters.

## 14. When to Use Aggregation via `MongoOperations`?

`find(Query, Class)` suits filtering and loading documents. When the task is **computing across orders** (revenue by status, grouping by day, summarizing SKUs), `MongoOperations.aggregate(...)` is the better tool.

Example totaling amounts by status for a tenant:

~~~java
import org.bson.Document;
import org.springframework.data.mongodb.core.aggregation.Aggregation;

Aggregation aggregation = Aggregation.newAggregation(
    Aggregation.match(Criteria.where("tenantId").is("t01")),
    Aggregation.group("state")
        .count().as("orderCount")
        .sum("totalVnd").as("totalValueVnd")
);

var results = operations.aggregate(
    aggregation,
    OrderDocument.class,
    Document.class
);
~~~

Here, input type `OrderDocument.class` supplies the mapping context so `tenantId`/`state`/`totalVnd` map according to entity annotations. Grouping results typically contain `_id` and aggregated fields; map to a DTO based on the actual output shape.

**Note:** the snippet uses basic aggregation APIs for illustration; do not leak raw `Document` objects to controllers. When output shape is fixed, create a statistics DTO and test expected fields. Because Spring Data versions differ in typed aggregation mapping rules, verify the emitted BSON pipeline and mapper output.

### 14.1. When Not to Use Aggregation?

Do not replace a simple derived query `findByTenantIdAndState` with an unnecessary multi-stage pipeline. Aggregation fits `$group`, computed `$project` fields, `$unwind` on arrays, or `$lookup`—not every optional filter.

## 15. Indexes and Performance Measurement for Domain Queries

Fragments do not make queries fast automatically. Indexes must match actual **filters + sorts**.

The fixture created:

~~~javascript
orders.createIndex({
  tenant_id: 1,
  state_code: 1,
  created_at: -1,
  _id: -1
});
~~~

This index matches queries filtering by tenant and state and sorting by creation date and ID. For queries with only tenant (no state), or adding ranges on `total_vnd` and `line_items` predicates, the database may pick a different plan; **never assume one compound index optimizes every combination**.

### 15.1. `$elemMatch` and Multikey Indexes

If you frequently search orders by line items:

~~~javascript
orders.createIndex({
  "line_items.sku": 1,
  "line_items.quantity": 1
});
~~~

When indexed fields traverse an array of embedded documents, MongoDB builds a multikey index. `$elemMatch` not only guarantees **matching the same element**, it also governs how index bounds combine on compound multikey indexes when fields share the same array path.

Do not index every field mechanically. Choose indexes based on actual workloads, selectivity, data size, and write amplification costs.

### 15.2. Inspecting Queries on Representative Data

~~~javascript
orders.find({
  tenant_id: "t01",
  state_code: "PAID",
  total_vnd: { $gte: 400000 },
  line_items: {
    $elemMatch: {
      sku: "A",
      quantity: { $gte: 5 }
    }
  }
})
  .sort({ created_at: -1, _id: -1 })
  .explain("executionStats");
~~~

Inspect `winningPlan`, `totalKeysExamined`, `totalDocsExamined`, `nReturned`, and any sort stages. With only a handful of orders, `explain` clarifies the plan structure, but cannot prove performance at millions of documents.

### 15.3. Count and Pagination Have Separate Costs

`PageImpl` in the fragment always returns total counts from `count`. With heavy filters, counting can noticeably increase response latency. When the UI only asks "is there a next page?", consider returning `Slice` or cursor/keyset pagination, and measure payload from BSON to Java/HTTP.

## 16. Security and Authorization in Domain-Modeled Queries

A sound domain filter not only expresses **what the user wants**, but also enforces **what they are allowed to see**. Three principles:

1. **Server-side tenant:** obtain tenant from the authenticated security context/call; never let users select another tenant via query parameter.
2. **Mandatory filters cannot be overridden:** combine tenant via `AND` with optional criteria; never let a client-driven `OR` escape tenant scope.
3. **Projection/DTO allowlist:** returned results include only authorized fields; never log entities or raw BSON containing sensitive data.

### 16.1. Unscoped `OR` Trap

Wrong:

~~~javascript
{
  $or: [
    { tenant_id: "t01" },
    { state_code: "PAID" }
  ]
}
~~~

This query returns **every PAID order**, even from other tenants. Correct when filtering a tenant plus optional statuses:

~~~javascript
{
  tenant_id: "t01",
  $or: [
    { state_code: "NEW" },
    { state_code: "PAID" }
  ]
}
~~~

In `Criteria` code, mandatory tenant predicates must always be part of the **outer AND**. Test data must include at least one other-tenant document in the same state to catch data leaks.

### 16.2. Read Models vs. Write Models

Never take a lightweight DTO holding `id/state/totalVnd` and pass a partial entity to `repository.save(partialEntity)`. Unloaded fields can be overwritten and lost. For conditional updates, call `MongoOperations.updateFirst`/`findAndModify` with explicit operators and filters.

## 17. Testing Fragments Against Real MongoDB

Mocking `MongoOperations` tests Java branching logic, yet does not verify that:

- `@Field("tenant_id")` and `@Field("state_code")` map to the right BSON fields.
- Enum `OrderState.PAID` serializes properly.
- `$elemMatch` constrains multiple predicates to **a single line item**.
- Sorting by `createdAt/id` produces the right order and pagination.
- The count query avoids skip/limit and preserves the tenant filter.
- `findAndModify` is truly atomic per document.

Therefore, domain-modeled queries need **integration tests** with an isolated test MongoDB.

### 17.1. Test Matrix

| Case | Expectation |
| --- | --- |
| Filter tenant t01, state PAID | o302, o304, o307; excludes o305 |
| Sort `createdAt DESC, id DESC` | o307 precedes o304 on tied timestamp |
| Filter PAID, minTotal 400000, SKU A, qty 5 | o307, o302 |
| Cross-element trap on o301 | Does not match "one line A qty ≥ 5" |
| Time interval `[from, before)` | Document at `from` included; at `before` excluded |
| Page 0 size 2 | Two items and exact filter total count |
| Page size over 100 | Rejected |
| Unpaged request | Rejected per fragment contract |
| Blank tenant | Rejected |
| Blank SKU or invalid qty | Validation throws error |
| Missing tenant filter in code | Test fails if o305 appears |
| Claim oldest NEW order | One order moves to PROCESSING, no duplicate claim |

### 17.2. Illustrative Integration Test

The test below inserts dedicated fixtures into an **isolated test MongoDB**. It verifies the fragment through `OrderRepository`, not just calling the implementation class directly.

~~~java
package com.example.extended;

import static org.assertj.core.api.Assertions.assertThat;

import com.mongodb.client.model.Filters;
import java.util.Date;
import java.time.Instant;
import java.util.List;
import org.bson.Document;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.mongodb.core.MongoTemplate;

@DataMongoTest
class ExtendedRepositorySearchTest {
    @Autowired MongoTemplate template;
    @Autowired OrderRepository repository;

    @Test
    void fragmentAppliesTenantAndSameArrayElementFilter() {
        List<String> ids = List.of(
            "fixture-ext003-a",
            "fixture-ext003-b",
            "fixture-ext003-c"
        );
        var collection = template.getDb()
            .getCollection("orders_extended_demo_003");

        collection.deleteMany(Filters.in("_id", ids));
        try {
            collection.insertMany(List.of(
                new Document("_id", ids.get(0))
                    .append("tenant_id", "test-tenant-003")
                    .append("state_code", "PAID")
                    .append("created_at", Date.from(
                        Instant.parse("2026-10-01T08:00:00Z")))
                    .append("total_vnd", 500000L)
                    .append("line_items", List.of(
                        new Document("sku", "A").append("quantity", 1),
                        new Document("sku", "B").append("quantity", 8)
                    )),
                new Document("_id", ids.get(1))
                    .append("tenant_id", "test-tenant-003")
                    .append("state_code", "PAID")
                    .append("created_at", Date.from(
                        Instant.parse("2026-10-02T08:00:00Z")))
                    .append("total_vnd", 600000L)
                    .append("line_items", List.of(
                        new Document("sku", "A").append("quantity", 6)
                    )),
                new Document("_id", ids.get(2))
                    .append("tenant_id", "another-tenant-003")
                    .append("state_code", "PAID")
                    .append("created_at", Date.from(
                        Instant.parse("2026-10-03T08:00:00Z")))
                    .append("total_vnd", 700000L)
                    .append("line_items", List.of(
                        new Document("sku", "A").append("quantity", 9)
                    ))
            ));

            OrderSearchFilter filter = new OrderSearchFilter(
                OrderState.PAID, null, null, 400_000L, "A", 5
            );

            var page = repository.search(
                "test-tenant-003",
                filter,
                PageRequest.of(0, 2)
            );

            assertThat(page.getContent())
                .extracting(OrderDocument::getId)
                .containsExactly("fixture-ext003-b");
            assertThat(page.getTotalElements()).isEqualTo(1L);
        } finally {
            collection.deleteMany(Filters.in("_id", ids));
        }
    }
}
~~~

This test catches **two predicates matching two different elements**: fixture A has `A×1` and `B×8` and must be excluded; fixture B has `A×6` so it matches; fixture C matches the line predicate too but belongs to another tenant.

**Run tests only on a dedicated MongoDB**: setup/cleanup actively deletes those fixture IDs. Never run against a shared collection. This test does not replace performance benchmarking or transaction checks; it verifies **query behavior and mapping**.

### 17.3. Testing Pagination and Claiming

In addition to the test above, write separate integration tests for:

- Two orders sharing `createdAt` with different IDs, verifying `id DESC` ordering.
- Filtering a tenant with three records, requesting page size 2, and asserting total 3.
- Calling `claimOldestNew(...)` twice, confirming two distinct IDs move to `PROCESSING`; calling a third time with no candidates left returns `null`.
- To test competing workers, run two concurrent tasks against test MongoDB with `state=NEW` and confirm neither claims the same document.

Do not only mock `OrderSearchRepositoryImpl`: include at least one test via **`OrderRepository` composition** to prove Spring Data wired the fragment implementation.

## 18. Common Mistakes and Diagnostics

| Symptom | Possible cause | How to resolve |
| --- | --- | --- |
| Repository lacks `search` method at runtime | Fragment interface not extended or implementation undiscovered | Check package scan, `OrderSearchRepositoryImpl` name, and postfix config |
| Spring tries to derive `search(...)` as a property query | Fragment not composed properly | Check composition, class name, and method signature |
| `MongoOperations.find` returns empty despite BSON data | Java/BSON name mismatch or wrong enum/ID type | Compare `@Field`, `@MongoId`, and `mongosh` |
| Results contain another tenant | Missing tenant predicate, or `OR` widened scope | Always `AND` mandatory scope into all queries |
| `o301` shows up when filtering A quantity ≥ 5 | Independent dot-notation predicates instead of `$elemMatch` | Combine SKU and qty inside one `elemMatch` |
| Page content is right but total is wrong | Count uses different filter or accidentally copies skip/limit | Build separate count query from the same criteria |
| Two orders with same timestamp swap order | Sort lacks tie-breaker | Add unique `id`/`_id` to sort |
| Deep pages are slow | Large offset/skip | Review indexes, switch to keyset/cursor when suitable |
| DTO has few fields yet payload remains heavy | Loading whole entity before mapping DTO | Use server-side field projection/aggregation |
| Saving a partial entity erases fields | `fields().include(...)` loaded only a subset | Read partial entities only; use update operators for writes |
| Duplicate job claim across workers | Separate read then save without state guard | `findAndModify` with state predicate and sort |
| `@Version` exists yet stale write still succeeds | Query lacks expected version | Add version to predicate or use version-aware entity save |
| Total count shifts between two reads | Data mutated without snapshot isolation | Clarify consistency guarantees; do not promise immutable totals |
| Query slow despite custom fragment | Suboptimal index/filter/sort | Run `explain`, check metrics, measure on representative data |
| Mock tests pass, production fails mapping | Mocks do not run real converter/driver | Integration test with MongoDB and fragment composition |

## 19. Checklist for Designing an Extended Repository

1. **Identify domain behaviors**: order search, order claim, stats, or updates; do not lump everything into one multipurpose method.
2. **Design typed filters**: enums, time intervals, quantities, monetary amounts, and clear validation.
3. **Keep tenant/authorization mandatory** in services and query fragments; never accept raw MongoDB predicates from clients.
4. **Extend only when needed**: keep CRUD and simple finders on `MongoRepository`.
5. **Create fragment interface + implementation** per naming convention, using constructor injection of `MongoOperations`.
6. **Use Java property names** when calling `MongoOperations` with an entity class; verify BSON aliases for complex mappings.
7. **Constrain same array elements** with `$elemMatch` when multiple conditions apply to one `OrderLine`.
8. **Separate content and count queries** and use a unique tie-breaker in sorts; cap page size/offset.
9. **Handle projections carefully**: a narrow DTO does not prove the server omitted unused fields; never `save` a partial entity.
10. **Pick the right write operation**: `findAndModify` for atomic single-document claims, `updateFirst` with filters and expected version for conditional updates.
11. **Design and measure indexes** on sufficiently large datasets; never assume fragments improve performance by themselves.
12. **Integration test against real MongoDB**, checking alias mapping, tenant scope, array semantics, pagination, count, and atomic claims.

## 20. Practice Exercises

Exercises use the fixture from section 3. For write examples, run against an isolated test database and treat each exercise as an independent scenario.

### Exercise 1 — Why Use a Fragment?

The system has six optional filters. Why not create derived methods for every combination?

**Answer:** Combinations grow rapidly, method names become unwieldy, and mandatory business predicates are easily forgotten. A fragment using `MongoOperations` builds typed predicates from `OrderSearchFilter`, centralizes tenant scoping, and exposes a stable domain API.

### Exercise 2 — Java Name vs. BSON Name

An entity declares `@Field("tenant_id") String tenantId;`. When calling `MongoOperations.find(Query, OrderDocument.class)`, which field name goes into `Criteria`?

**Answer:** `Criteria.where("tenantId")` using the Java property name; Spring Data maps it to BSON `tenant_id`. If calling the Java driver's `Filters.eq(...)` directly, you must use `tenant_id`.

### Exercise 3 — Array Element Trap

Order `o301` has A × 1, B × 8. If the filter "SKU A and quantity ≥ 5" is written as two dot-notation predicates, will `o301` be matched?

**Answer:** Yes, erroneously, because each predicate matches a different element. To require both on the same line, use `Criteria.where("lineItems").elemMatch(Criteria.where("sku").is("A").and("quantity").gte(5))`.

### Exercise 4 — Domain Query Result

Find orders for `t01`, state `PAID`, total ≥ 400,000, having a line A with quantity ≥ 5; sort by creation time descending then ID descending.

**Answer:** `o307` then `o302`; `o305` belongs to tenant `t02` and must be excluded. This can be executed via `repository.search("t01", filter, PageRequest.of(0,10))`.

### Exercise 5 — Total Count

Why shouldn't `countQuery` carry `skip/limit` from `contentQuery`?

**Answer:** The content query selects one page, whereas count needs the total documents matching **the same filter**. Constructing a separate unpaginated query states intent clearly, prevents inaccurate totals, and avoids API-specific pagination handling quirks.

### Exercise 6 — Oldest Order and Race Conditions

Two workers both find the oldest `NEW` order and then call `save`. What can happen?

**Answer:** Both can read the same order; you would need optimistic-lock retries or use `findAndModify` with filter `state=NEW` and sort in **a single atomic operation**, ensuring a claimed order no longer matches the next worker.

### Exercise 7 — Partial Entity

A query includes only `id`, `state`, and `totalVnd`, receiving `OrderDocument`. Should you call `repository.save(...)` to update state?

**Answer:** No. It is a partial entity; `save` can replace the document and erase unloaded fields. Convert to a read DTO, or call `MongoOperations.updateFirst` with `Update.set` and appropriate predicates.

### Exercise 8 — Tenant Scope

A developer adds the filter `$or: [{tenant_id:"t01"},{state_code:"PAID"}]`. Is this valid?

**Answer:** No. This condition exposes `PAID` orders from every tenant. Tenant scope must sit in an outer mandatory `AND`: `tenant_id:"t01"` combined with the status condition group.

### Exercise 9 — Version Read by Client

A client viewed an order at version 2, but when the update request reaches the server, the order is already at version 3. Will a query update filtering only by `id` reliably reject it?

**Answer:** No. To reject stale writers, include the expected version in the predicate or use version-aware entity `save`. Auto-bumping version does not know which version the client saw.

### Exercise 10 — Verifying a Real Fragment

A unit test mocking `MongoOperations` returns the expected list. Does it prove `@Field` aliases and `$elemMatch` work?

**Answer:** No. You need an integration test executed through `OrderRepository` composition against real MongoDB, with fixtures creating actual BSON fields, a cross-element trap, and a document from another tenant.

## References

- [Spring Data MongoDB — Custom Repository Implementations](https://docs.spring.io/spring-data/mongodb/reference/repositories/custom-implementations.html): repository fragments, implementation rules, and repository composition.
- [Spring Data Commons — Custom Repository Implementations](https://docs.spring.io/spring-data/commons/reference/repositories/custom-implementations.html): fragment contract and `Impl` convention.
- [Spring Data MongoDB — MongoOperations API](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/MongoOperations.html): `find`, `count`, `findAndModify`, `updateFirst`, and `aggregate`.
- [Spring Data MongoDB — Query Documents](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-query-operations.html): `Criteria`, `Query`, field projection, sorting, and `MongoTemplate`.
- [Spring Data MongoDB — Object Mapping](https://docs.spring.io/spring-data/mongodb/reference/mongodb/mapping/mapping.html): `@Document`, `@Field`, `@MongoId`, and entity/BSON conversion.
- [Spring Data MongoDB — Saving, Updating, and Removing Documents](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-crud-operations.html): `findAndModify`, `Update`, `@Version`, and write atomicity.
- [MongoDB Manual — Query an Array of Embedded Documents](https://www.mongodb.com/docs/manual/tutorial/query-array-of-documents/): querying embedded arrays and limits of dot notation.
- [MongoDB Manual — `$elemMatch` Query Operator](https://www.mongodb.com/docs/manual/reference/operator/query/elemmatch/): constraining multiple criteria on a single array element.
- [MongoDB Manual — Multikey Index Bounds](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-multikey/multikey-index-bounds/): multikey indexes and `$elemMatch`.
- [MongoDB Manual — Atomicity and Transactions](https://www.mongodb.com/docs/manual/core/write-operations-atomicity/): single-document atomicity and multi-document transactions.
