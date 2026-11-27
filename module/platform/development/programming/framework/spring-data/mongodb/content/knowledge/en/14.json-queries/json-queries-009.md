# Choosing @Query, Derived Queries, or Custom Implementations

> **Chapter:** JSON Queries  
> **Module:** `SPRING_DATA_MONGODB`

Spring Data MongoDB supports three common ways to query documents: **derived queries inferred from repository method names**, the **`@Query`** annotation using JSON expressions, and **custom repository implementations** using `MongoTemplate`/`Criteria`. The same filter condition can be expressed in all three ways, yet each fits a different level of complexity.

Overusing derived queries produces long, hard-to-edit method names. Using `@Query` for everything turns JSON strings hard to maintain when conditions must toggle on and off dynamically. Writing custom classes for simple equality checks adds unnecessary boilerplate. **Choosing the simplest form that accurately expresses the business contract** is the main goal of this lesson.

This lesson belongs to the `SPRING_DATA_MONGODB` module, covering connections, document mapping, `MongoTemplate` or repository operations, query design, aggregation, indexes, transactions, reactive access, testing, and data-performance diagnostics. The content focuses on how to **choose and implement queries** in a real-world system.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Choose between derived queries, `@Query`, and custom repository fragments based on condition complexity and dynamism.
2. Use `@Query` with positional parameters `?0`, `?1`, projection, and pagination without string concatenation from input.
3. Write a repository fragment with interface and implementation, building dynamic queries using `MongoTemplate`, `Query`, and `Criteria`.
4. Understand the impact of Java/BSON field mapping, enums, `Instant`, empty conditions, sorting, and tenant authorization.
5. Test queries against real MongoDB, measure indexes, and distinguish regular filters from aggregation.

## 2. Quick Decision Matrix

| Criterion | Derived Query | `@Query` JSON | Custom Implementation |
| --- | --- | --- | --- |
| How it is written | Repository method name | Annotation holding static JSON | Java code building the filter |
| Best suited for | Few common, stable conditions | Specific MongoDB operators, fixed queries | Optional filters, dynamic or complex criteria |
| Requires implementation class | No | No | Yes, typically via fragment |
| Readability | High when name is short | High when JSON is moderate | High when logic is factored cleanly |
| Adding/dropping filters at runtime | Awkward | Awkward with static JSON | Easy using `if` branches |
| Projection, sorting, paging | Supported via repository | Supported via repository and `fields` | Must be applied to `Query` |
| Code boilerplate | Low | Low–medium | Higher |
| Query execution speed | Depends on BSON query/indexes | Depends on BSON query/indexes | Depends on BSON query/indexes |

**Selection rule:** use **derived queries** while method names stay clear; use **`@Query`** when static JSON expresses the requirement more cleanly than a long name; use a **custom fragment** when filters can be omitted, involve many conditional branches, or need reusable query-building logic.

Key point: the MongoDB server does not know which Java mechanism generated the command. Given identical filters, projections, sorts, and indexes, MongoDB processing cost is broadly equivalent.

## 3. Running Model: Searching Orders

Suppose an e-commerce app stores orders in the `orders` collection with store ID `storeId`, `status`, monetary amount `totalMinor`, creation timestamp `createdAt`, and a `tags` array. Simple screens filter by store and status, while advanced screens offer optional filters and pagination.

File `OrderStatus.java`:

```java
package com.example.shop.orders;

public enum OrderStatus {
    NEW,
    PAID,
    CANCELLED
}
```

File `OrderDocument.java`:

```java
package com.example.shop.orders;

import java.time.Instant;
import java.util.List;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "orders")
public record OrderDocument(
    @Id String id,
    String orderCode,
    String storeId,
    OrderStatus status,
    long totalMinor,
    Instant createdAt,
    List<String> tags
) {}
```

`id` is the Java property mapped to `_id` in BSON. IDs such as `O-101` are not 24-character ObjectId hex strings, so they remain strings as shown. If your real model uses `@Field` or custom converters, verify queries against the actual BSON field names and types.

### 3.1. Seeding Data via mongosh

**Run only in an isolated test database:**

```javascript
use shop

db.orders.insertMany([
  {
    _id: "O-101",
    orderCode: "ORD-101",
    storeId: "STORE-HCM",
    status: "NEW",
    totalMinor: NumberLong(120000),
    createdAt: ISODate("2026-11-19T02:00:00Z"),
    tags: ["web", "priority"]
  },
  {
    _id: "O-102",
    orderCode: "ORD-102",
    storeId: "STORE-HCM",
    status: "PAID",
    totalMinor: NumberLong(850000),
    createdAt: ISODate("2026-11-19T04:00:00Z"),
    tags: ["web"]
  },
  {
    _id: "O-103",
    orderCode: "ORD-103",
    storeId: "STORE-HCM",
    status: "CANCELLED",
    totalMinor: NumberLong(400000),
    createdAt: ISODate("2026-11-20T01:00:00Z"),
    tags: ["app"]
  },
  {
    _id: "O-104",
    orderCode: "ORD-104",
    storeId: "STORE-HCM",
    status: "PAID",
    totalMinor: NumberLong(1500000),
    createdAt: ISODate("2026-11-20T03:00:00Z"),
    tags: ["app", "priority"]
  },
  {
    _id: "O-105",
    orderCode: "ORD-105",
    storeId: "STORE-HN",
    status: "PAID",
    totalMinor: NumberLong(2000000),
    createdAt: ISODate("2026-11-20T04:00:00Z"),
    tags: ["priority"]
  }
])
```

All business-screen query examples include `storeId` to isolate each store's data scope. In a real system, the service must resolve `storeId` from the authenticated user; never treat a client-supplied value as authorization.

## 4. Option 1: Derived Queries

Derived queries combine property names and Spring Data keywords such as `And`, `In`, `GreaterThanEqual`, `LessThan`, and `True`. For small criteria sets, this is usually the cleanest and easiest approach to maintain.

File `OrderRepository.java`:

```java
package com.example.shop.orders;

import java.time.Instant;
import java.util.Collection;
import java.util.List;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface OrderRepository
        extends MongoRepository<OrderDocument, String> {

    List<OrderDocument> findByStoreIdAndStatus(
        String storeId, OrderStatus status);

    Page<OrderDocument> findByStoreIdAndStatusIn(
        String storeId,
        Collection<OrderStatus> statuses,
        Pageable pageable);

    List<OrderDocument>
    findByStoreIdAndCreatedAtGreaterThanEqualAndCreatedAtLessThan(
        String storeId,
        Instant fromInclusive,
        Instant toExclusive);
}
```

Call:

```java
List<OrderDocument> paid =
    repository.findByStoreIdAndStatus(
        "STORE-HCM", OrderStatus.PAID);
```

Logically equivalent query:

```javascript
db.orders.find({
  storeId: "STORE-HCM",
  status: "PAID"
})
// O-102 and O-104
```

The time-range method uses `>= fromInclusive` and `< toExclusive`, forming a half-open interval `[from, to)` suitable for chaining adjacent time windows without double-counting boundaries.

### 4.1. When to Choose Derived Queries

- Only a few fixed fields are involved.
- Keywords match the requirement cleanly and parameter order is obvious.
- No special JSON condition groupings or aggregation pipelines are needed.
- Most readers can understand the method without opening another file.

If you only need `findByStoreIdAndOrderCode(...)`, creating a custom class adds overhead without meaningful benefit.

### 4.2. Signs You Need Another Approach

A name such as:

```java
findByStoreIdAndStatusInAndCreatedAtGreaterThanEqualAndCreatedAtLessThanAndTotalMinorGreaterThanEqual(...)
```

may still be derivable from properties, yet becomes very hard to inspect. If all conditions are mandatory and fixed, JSON `@Query` may be clearer. If several conditions are *optional*, a custom query builder fits better; do not create a separate derived method for every filter combination.

## 5. Option 2: @Query with Fixed JSON

`@Query` lives in `org.springframework.data.mongodb.repository.Query`. Its JSON expression is used by Spring Data to build the MongoDB filter. Placeholders `?0`, `?1`, ... bind to the corresponding Java parameters **by position**.

### 5.1. Multi-Operator Fixed Filters

File `OrderJsonQueryRepository.java`, illustrating an **alternative** to methods in the base repository:

```java
package com.example.shop.orders;

import java.time.Instant;
import java.util.Collection;
import java.util.List;
import org.springframework.data.mongodb.repository.MongoRepository;
import org.springframework.data.mongodb.repository.Query;

public interface OrderJsonQueryRepository
        extends MongoRepository<OrderDocument, String> {

    @Query("""
        {
          'storeId': ?0,
          'status': { '$in': ?1 },
          'createdAt': { '$gte': ?2, '$lt': ?3 },
          'totalMinor': { '$gte': ?4 }
        }
        """)
    List<OrderDocument> findWithFixedFilters(
        String storeId,
        Collection<OrderStatus> statuses,
        Instant fromInclusive,
        Instant toExclusive,
        long minimumTotalMinor
    );
}
```

The example uses a **Java text block** (Java 15+). `@Query` still accepts a regular String; the single-quoted JSON syntax shown is accepted by Spring Data MongoDB. On older Java versions, place the string on one line or concatenate static string literals.

Call:

```java
jsonRepository.findWithFixedFilters(
    "STORE-HCM",
    List.of(OrderStatus.PAID),
    Instant.parse("2026-11-19T00:00:00Z"),
    Instant.parse("2026-11-21T00:00:00Z"),
    500000L
);
// O-102 and O-104
```

`jsonRepository` is an instance of `OrderJsonQueryRepository`. Bindings are `?0 = storeId`, `?1 = statuses`, `?2 = from`, `?3 = to`, `?4 = minimum amount`. Reordering method parameters without updating placeholders is an easy bug to introduce while the JSON expression remains syntactically valid.

**Do not define two equivalent repositories scanning and managing the same entity unnecessarily.** In production, you normally group derived and annotated methods inside `OrderRepository`; splitting interfaces here only clarifies each option.

### 5.2. Use Placeholders, Not Input Concatenation into JSON

Never construct queries from user strings like:

```java
// ANTI-PATTERN: avoid concatenating strings from input.
String unsafeQuery =
    "{ 'storeId': '" + storeId + "' }";
```

Instead:

```java
@Query("{ 'storeId': ?0 }")
List<OrderDocument> byStore(String storeId);
```

Placeholders let the framework bind and escape values through mapping rather than manually splicing quotes. Still validate inputs, authorization, `$in` element counts, and prevent users from deciding MongoDB operator structure arbitrarily.

### 5.3. MongoDB Operators Are Clearer Than Long Method Names

Suppose you want orders containing **all** tags in a list:

```java
@Query("{ 'storeId': ?0, 'tags': { '$all': ?1 } }")
List<OrderDocument> findHavingAllTags(
    String storeId, Collection<String> requiredTags);
```

Corresponding query:

```javascript
db.orders.find({
  storeId: "STORE-HCM",
  tags: { $all: ["web", "priority"] }
})
// O-101
```

`$all` requires the array to contain **every** element, whereas `$in` only requires a single matching element. When multiple criteria must hold on **the same element** of an embedded document array, consider `$elemMatch`. In such cases, short JSON is far easier to verify than a method name cramming multiple keywords together.

### 5.4. Do Not Treat Null as "Ignore Condition"

```java
@Query("{ 'storeId': ?0, 'status': ?1 }")
List<OrderDocument> byStoreAndStatus(
    String storeId, OrderStatus status);
```

If `status` is null, the condition still binds as a MongoDB null match; it does **not** vanish automatically. For requests with optional parameters, build `Criteria` conditionally or define dedicated methods with explicit contracts.

## 6. Projection, Pageable, and @Aggregation

### 6.1. Projection for Read-Only Lists

If a screen only needs a few fields, avoid loading the entire entity:

```java
package com.example.shop.orders;

import java.time.Instant;

public interface OrderBrief {
    String getOrderCode();
    OrderStatus getStatus();
    long getTotalMinor();
    Instant getCreatedAt();
}
```

In the repository:

```java
@Query(
    value = "{ 'storeId': ?0, 'status': { '$in': ?1 } }",
    fields = """
        {
          'orderCode': 1,
          'status': 1,
          'totalMinor': 1,
          'createdAt': 1
        }
        """
)
List<OrderBrief> findBriefByStatuses(
    String storeId,
    Collection<OrderStatus> statuses);
```

`fields` defines the **BSON projection**. Returning `OrderBrief` instead of the full entity prevents code from passing a partial object into `save`, which could wipe out unloaded fields. `_id` is normally included unless explicitly excluded.

### 6.2. Pagination and Sorting

`Pageable` works with `@Query` as well:

```java
@Query("{ 'storeId': ?0, 'status': { '$in': ?1 } }")
Page<OrderDocument> pageByStatuses(
    String storeId,
    Collection<OrderStatus> statuses,
    Pageable pageable);
```

Caller:

```java
Pageable pageable = PageRequest.of(
    0, 20,
    Sort.by(
        Sort.Order.desc("createdAt"),
        Sort.Order.desc("id"))
);

Page<OrderDocument> page =
    repository.pageByStatuses(
        "STORE-HCM",
        List.of(OrderStatus.NEW, OrderStatus.PAID),
        pageable);
```

This snippet assumes `repository` declares `pageByStatuses` with imports for `Page`, `Pageable`, `PageRequest`, `Sort`, and `List`. `id` is the Java property mapped to `_id`, serving as a secondary sort key for deterministic ordering when `createdAt` collides. `Page` can trigger a count query; if you only need to check whether a next page exists, consider `Slice` or keyset pagination.

Never allow requests to pick arbitrarily huge page sizes or unvetted sort fields. Projection, sorting, and paging are **part of the query contract**, not harmless UI details.

### 6.3. When Is @Aggregation Needed?

When the requirement involves grouping daily revenue, `$lookup` across collections, `$unwind`ing arrays, or pipeline computations, use **`@Aggregation`** or `MongoTemplate.aggregate(...)`. Regular `@Query` handles document filtering and projection, not full Aggregation Framework pipelines.

## 7. Option 3: Repository Fragment with MongoTemplate

When a request has multiple **optional** criteria, static JSON would require encoding complicated conditional expressions. A fragment separates a custom search interface and an implementation that builds the query step by step:

```text
OrderRepository
  ├── MongoRepository<OrderDocument, String>
  └── OrderSearchRepository
         └── OrderSearchRepositoryImpl
                └── MongoTemplate + Criteria + Query
```

### 7.1. Fragment Interface

File `OrderSearchRepository.java`:

```java
package com.example.shop.orders;

import java.time.Instant;
import java.util.Collection;
import java.util.List;
import org.springframework.data.domain.Pageable;

public interface OrderSearchRepository {

    List<OrderDocument> search(
        String storeId,
        Collection<OrderStatus> statuses,
        Instant fromInclusive,
        Instant beforeExclusive,
        Long minimumTotalMinor,
        Pageable pageable
    );
}
```

Illustrative conventions chosen intentionally by the application:

- `storeId` is mandatory and must be authorized by the service.
- `statuses == null`: omit status filter; `statuses.isEmpty()`: no statuses allowed, return empty list.
- `fromInclusive`/`beforeExclusive` are optional time bounds.
- `minimumTotalMinor == null`: omit minimum amount filter.
- `pageable` must be bounded and paged.

### 7.2. Implementation

File `OrderSearchRepositoryImpl.java`:

```java
package com.example.shop.orders;

import java.time.Instant;
import java.util.Collection;
import java.util.List;
import java.util.Objects;
import org.springframework.data.domain.Pageable;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

public class OrderSearchRepositoryImpl
        implements OrderSearchRepository {

    private final MongoTemplate template;

    public OrderSearchRepositoryImpl(MongoTemplate template) {
        this.template = template;
    }

    @Override
    public List<OrderDocument> search(
            String storeId,
            Collection<OrderStatus> statuses,
            Instant fromInclusive,
            Instant beforeExclusive,
            Long minimumTotalMinor,
            Pageable pageable) {

        Objects.requireNonNull(storeId, "storeId");
        Objects.requireNonNull(pageable, "pageable");

        if (storeId.isBlank()) {
            throw new IllegalArgumentException("storeId is blank");
        }
        if (pageable.isUnpaged() || pageable.getPageSize() > 100) {
            throw new IllegalArgumentException(
                "Pagination required, pageSize <= 100");
        }
        if (fromInclusive != null && beforeExclusive != null
                && !fromInclusive.isBefore(beforeExclusive)) {
            throw new IllegalArgumentException(
                "Invalid time range");
        }
        if (statuses != null && statuses.stream()
                .anyMatch(Objects::isNull)) {
            throw new IllegalArgumentException(
                "statuses contains null");
        }
        if (statuses != null && statuses.isEmpty()) {
            return List.of();
        }

        Query query = Query.query(
            Criteria.where("storeId").is(storeId));

        if (statuses != null) {
            query.addCriteria(
                Criteria.where("status").in(statuses));
        }
        if (fromInclusive != null || beforeExclusive != null) {
            Criteria time = Criteria.where("createdAt");
            if (fromInclusive != null) {
                time.gte(fromInclusive);
            }
            if (beforeExclusive != null) {
                time.lt(beforeExclusive);
            }
            query.addCriteria(time);
        }
        if (minimumTotalMinor != null) {
            query.addCriteria(
                Criteria.where("totalMinor")
                    .gte(minimumTotalMinor));
        }

        query.with(pageable);
        return template.find(query, OrderDocument.class);
    }
}
```

`Query` always retains the `storeId` condition. Other criteria are added only when supplied by inputs. This avoids passing null into a fixed `@Query` expression hoping the criterion disappears automatically.

**Note:** checking that `storeId` is non-blank does not authenticate the user's access to that store. Authorization must occur before calling the fragment, and integration tests should confirm every branch preserves the scope filter.

### 7.3. Composing the Fragment with the Main Repository

File `OrderRepository.java` when adopting the fragment pattern:

```java
package com.example.shop.orders;

import org.springframework.data.mongodb.repository.MongoRepository;

public interface OrderRepository
        extends MongoRepository<OrderDocument, String>,
                OrderSearchRepository {
}
```

Spring Data wires `OrderSearchRepositoryImpl` into the repository by following the fragment interface and `Impl` suffix convention, provided classes live within the repository scan packages. If your project customizes the implementation postfix or has conflicting bean names, check the actual composition configuration.

In this lesson, the `OrderRepository` variants across sections represent **alternative organizational choices**; in a real codebase, merge the kept methods into **one repository interface** per project architecture.

### 7.4. If Page<OrderDocument> Is Needed

The fragment returns a `List` already skipped/limited/sorted per `Pageable`, **without a total count**. If the UI needs a `Page`, run a count query using the exact same filter **without paging** and construct a `PageImpl`/equivalent utility. Never mistake the current page's element count for `totalElements`, and do not assume a count query runs automatically just because the fragment accepts `Pageable`.

## 8. Examples Mapping Requirements to Approaches

| Requirement | Sensible Choice | Why |
| --- | --- | --- |
| Lookup order by `storeId` + `orderCode` | Derived query | Short, stable, self-explanatory name |
| Find orders having every tag in `tags` | `@Query` | `$all` expresses the requirement cleanly |
| Search with multiple optional filters | Custom fragment | Conditions added dynamically per request |
| Group revenue by day/currency | `@Aggregation`/Aggregation API | Requires `$group` and computations, not just filtering |
| Complex query with dynamic `$or`, `$elemMatch` | Custom fragment | Easy to group criteria and test each branch |
| Fixed query with list projection | `@Query(fields=...)` | Returned fields are visible at a glance |

Choosing a mechanism is not about "which tool is more powerful", but about **the nature of the query**, how filters vary, and long-term readability for maintainers.

## 9. Common Pitfalls When Switching Between the Three Approaches

### 9.1. Java Property Names vs. BSON Field Names

Suppose a model declares:

```java
@Field("created_at")
private Instant createdAt;
```

A derived query must use the Java property:

```java
findByCreatedAtGreaterThanEqual(Instant start);
```

With `@Query` on an entity repository and `Criteria` executed via `MongoTemplate`, Spring Data normally applies mapping metadata for field names and value types. Direct paths via `MongoTemplate.getCollection(...)` or the MongoDB Java driver **do not apply entity metadata automatically**. Therefore, verify actual BSON whenever `@Field` or converters change; do not rely solely on IDE autocomplete.

### 9.2. BSON Types and Converters

`OrderStatus.PAID` is normally mapped as the string `"PAID"` unless a custom converter overrides it. `Instant` is stored as BSON Date under mapping config. `long` in the model corresponds to a numeric BSON value, while legacy documents might have stored strings.

If a legacy record stores `totalMinor: "850000"` (BSON String) while a new query uses numeric comparison, that document will **fail to match** even if a custom reading converter can deserialize it into the Java object. MongoDB evaluates filters on BSON **before** Spring Data converts results to Java.

Similarly, range/pagination queries cannot fix timezone skew if legacy data saved `LocalDateTime` under different conventions. Maintain legacy fixtures and clear migration strategies.

### 9.3. Keep Tenant Conditions Outside OR Branches

A sound query:

```javascript
db.orders.find({
  storeId: "STORE-HCM",
  $or: [
    { status: "PAID" },
    { totalMinor: { $gte: NumberLong(1000000) } }
  ]
})
```

`storeId` sits outside `$or`, constraining all branches to the authorized store. Accidentally placing `storeId` **inside only one branch** lets the other branch leak records from other tenants. Test this explicitly, especially when assembling `andOperator`/`orOperator` groups in custom query builders.

### 9.4. Operators Do Not Disappear on Null Inputs

In `{ status: ?0 }`, a null parameter produces a query matching `null`/missing fields under MongoDB semantics rather than dropping the filter. `$in: []` matches nothing; `$nin: []` can match nearly everything. The service must define **the business meaning** of empty inputs.

In section 7's custom fragment, `statuses = null` means do not filter, whereas `statuses = []` means no status is permitted. That is an **application contract**, not a universal framework default.

### 9.5. JSON Binding Does Not Replace Validation

Using `?0` prevents concatenating user input directly into JSON. Even so, the service must still:

- Cap list sizes passed to `$in`, `$all`, or `$nin`.
- Verify filters respect user permissions.
- Guard user-supplied regexes: escape or offer literal search modes, cap length, and bound execution cost.
- Never allow clients to supply arbitrary MongoDB field names/operators or raw JSON fragments spliced into queries.

When users may choose a search field, map from an application-defined **field allowlist** to `Criteria`, rather than passing raw client-supplied field names.

## 10. Boundary Between Filter, Projection, and Aggregation

| Requirement | What to Use? | Why |
| --- | --- | --- |
| Select documents with matching status | Derived, `@Query`, or `Query`/`Criteria` | Standard filter |
| Return only a few fields | Repository projection or `Query.fields()` | Reduces read/transferred data |
| Sort and paginate documents | `Pageable`/`Sort` or `Query.with(...)` | List presentation |
| Aggregate order counts and revenue per day | Aggregation API, `@Aggregation` | Requires `$group`/`$dateTrunc` |
| Join data from another collection | Aggregation `$lookup` or separate reads | Normal filters do not auto-join |
| Bulk update by filter | `MongoTemplate.updateMulti(...)`/update API | Write operation, not read-only query |

`@Query` offers options such as `fields` for projection. It does not turn grouping calculations into aggregations. A custom repository can invoke `MongoTemplate.aggregate(...)` when needed, yet choosing **where the code lives** and choosing **which MongoDB command to run** are two separate decisions.

## 11. Safe Pagination, Indexes, and Performance Diagnostics

The app frequently queries orders by `storeId`, `status`, and creation time, sorted newest first:

```javascript
db.orders.createIndex({
  storeId: 1,
  status: 1,
  createdAt: -1,
  _id: -1
})
```

This is a **candidate index**, not a mandatory universal configuration. If a screen filters by store and time **without a `status` condition**, that index may not support the sort order as well as:

```javascript
db.orders.createIndex({
  storeId: 1,
  createdAt: -1,
  _id: -1
})
```

Do not create every conceivable index: each index adds storage and write-update overhead. Measure against common queries and representative dataset sizes.

Inspect with:

```javascript
db.orders
  .find({
    storeId: "STORE-HCM",
    status: { $in: ["NEW", "PAID"] }
  })
  .sort({ createdAt: -1, _id: -1 })
  .limit(20)
  .explain("executionStats")
```

Check `totalKeysExamined`, `totalDocsExamined`, `nReturned`, index usage, and whether an out-of-index sort occurs. When benchmarking the three Java options, ensure all three **produce the exact same BSON filter/projection/sort/limit**. Changing the Java call style while keeping the query identical rarely changes MongoDB execution speed meaningfully.

Beyond the single query, also measure: count queries for `Page`, network round-trips, BSON-to-Java mapping, serialization, follow-up queries, and selectivity of `$in`/`$nin`. A single command's `explain` does not equal total API latency.

## 12. Integration Testing: Same Requirement, Same Outcome

A mocked repository can pass even when a derived method name parses wrongly, `@Query` binds parameters in the wrong order, or a custom fragment drops `storeId`. Test against isolated MongoDB with real BSON. Spring Boot's `@DataMongoTest` (using the package import matching your version) supports data-layer testing; infrastructure can run via a test MongoDB instance or Testcontainers.

### 12.1. Seeding and Testing a Derived Query

JUnit 5/AssertJ example:

```java
package com.example.shop.orders;

import java.time.Instant;
import java.util.List;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.data.mongodb.core.MongoTemplate;

import static org.assertj.core.api.Assertions.assertThat;

@DataMongoTest
class OrderQueryIntegrationTest {

    @Autowired MongoTemplate template;
    @Autowired OrderRepository repository;

    @BeforeEach
    void seed() {
        // Use only on an isolated test database.
        template.dropCollection(OrderDocument.class);

        template.insertAll(List.of(
            new OrderDocument(
                "O-101", "ORD-101", "STORE-HCM",
                OrderStatus.NEW, 120000L,
                Instant.parse("2026-11-19T02:00:00Z"),
                List.of("web", "priority")),
            new OrderDocument(
                "O-102", "ORD-102", "STORE-HCM",
                OrderStatus.PAID, 850000L,
                Instant.parse("2026-11-19T04:00:00Z"),
                List.of("web")),
            new OrderDocument(
                "O-103", "ORD-103", "STORE-HCM",
                OrderStatus.CANCELLED, 400000L,
                Instant.parse("2026-11-20T01:00:00Z"),
                List.of("app")),
            new OrderDocument(
                "O-104", "ORD-104", "STORE-HCM",
                OrderStatus.PAID, 1500000L,
                Instant.parse("2026-11-20T03:00:00Z"),
                List.of("app", "priority")),
            new OrderDocument(
                "O-105", "ORD-105", "STORE-HN",
                OrderStatus.PAID, 2000000L,
                Instant.parse("2026-11-20T04:00:00Z"),
                List.of("priority"))
        ));
    }

    @Test
    void derivedQueryFiltersStoreAndStatus() {
        var ids = repository.findByStoreIdAndStatus(
                "STORE-HCM", OrderStatus.PAID)
            .stream()
            .map(OrderDocument::id)
            .toList();

        assertThat(ids).containsExactlyInAnyOrder(
            "O-102", "O-104");
    }
}
```

In your application, ensure tests import/configure the active repository bean. Tests calling `dropCollection` erase data and must run strictly on a **test-dedicated database**, never connected to shared or production databases.

### 12.2. Testing @Query

When injecting `OrderJsonQueryRepository` from section 5 (or after moving the method into `OrderRepository`), test parameter binding thoroughly:

```java
var ids = jsonRepository.findWithFixedFilters(
        "STORE-HCM",
        List.of(OrderStatus.PAID),
        Instant.parse("2026-11-19T00:00:00Z"),
        Instant.parse("2026-11-21T00:00:00Z"),
        500000L)
    .stream()
    .map(OrderDocument::id)
    .toList();

assertThat(ids).containsExactlyInAnyOrder(
    "O-102", "O-104");
```

This is an **illustrative test body**; `jsonRepository` must be injected with the declared repository type. Add tests that vary min/max timestamps or monetary thresholds to catch accidental swaps of `?2`, `?3`, and `?4`.

### 12.3. Testing the Custom Fragment via a Test Matrix

Using `OrderRepository` composed with the fragment from section 7, test these cases:

| Input | Expectation |
| --- | --- |
| `storeId=STORE-HCM`, all other filters null | Only HCM orders, paginated |
| `statuses=[PAID]`, `minimumTotalMinor=1000000` | Only `O-104` |
| `statuses=[]` | Returns empty list per contract |
| `fromInclusive >= beforeExclusive` | Throws invalid-input error |
| `pageable=unpaged` or excessive page size | Throws validation error |
| `storeId=STORE-HCM` while HN records also match filters | `O-105` is excluded |
| Only one time boundary supplied | Query remains valid and applies the open-ended bound |

In access-scope tests, do not merely assert expected IDs appear: explicitly **assert other tenants' IDs do not appear**. Also include fixtures stored in older BSON formats when upgrading models or converters.

### 12.4. Inspecting the Emitted BSON

For `MongoTemplate` queries, you can inspect `Query.getQueryObject()` and log it safely in tests, keeping in mind `Query` may still hold Java property names prior to BSON mapping. To verify exact queries sent to the server, use **MongoDB command monitoring** or suitable logging rather than assuming a `Criteria` object represents the final wire command.

Never leave unbounded profiling or command debug logging enabled in production. When measuring query cost, factor in real data volume and log access controls.

## 13. Reactive Access and Shared Caveats

With `ReactiveMongoRepository` and `ReactiveMongoTemplate`, selection guidelines are similar, except methods return `Flux<T>` or `Mono<T>`:

```java
import java.util.Collection;
import org.springframework.data.mongodb.repository.Query;
import org.springframework.data.mongodb.repository.ReactiveMongoRepository;
import reactor.core.publisher.Flux;

public interface ReactiveOrderRepository
        extends ReactiveMongoRepository<OrderDocument, String> {

    Flux<OrderDocument> findByStoreIdAndStatusIn(
        String storeId,
        Collection<OrderStatus> statuses);

    @Query("{ 'storeId': ?0, 'totalMinor': { '$gte': ?1 } }")
    Flux<OrderDocument> findExpensiveOrders(
        String storeId, long minimumTotalMinor);
}
```

For dynamic filters, a custom reactive fragment must use `ReactiveMongoTemplate` rather than calling blocking `MongoTemplate` inside a reactive flow expecting it to become non-blocking. Reactive tests must **subscribe** to publishers, such as with `StepVerifier`.

Decisions on field mapping, BSON types, tenant isolation, pagination, indexes, and consistency do not change just by adopting reactive APIs. If a business operation updates multiple documents atomically, that is a **transaction** design concern independent of the three read-query styles.

## 14. Common Mistakes

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Repository method fails to parse | Wrong Java property or derived-query keyword | Check model, shorten method name, or use `@Query` |
| `@Query` returns wrong data from swapped parameters | `?0`, `?1` order disagrees with signature | Test with distinct values per parameter |
| Invalid JSON inside annotation | Broken operator syntax or braces | Write integration tests; move to `Criteria` if too long |
| Request omits filters yet gets empty results | Passed null/empty hitting operator semantics | Define empty-input contracts in the service |
| Cross-tenant data leak | Omitted `storeId` in an `$or` branch or fallback query | Enforce permissions, keep tenant in every branch, add anti-leak tests |
| Projection returns partial entity | Used `fields` returning full entity then called `save` | Use read-only projections/DTOs |
| Custom repository method never invoked | Wrong fragment impl name/package or interface not extended | Check fragment interface, `Impl` suffix, and repository scan |
| Custom query is very slow | Unselective filters or missing indexes | Run `explain` and profile end-to-end request cost |
| `Page` is expensive | Large count query or unindexed sort | Consider `Slice`/keyset and tune indexes |
| Legacy records skipped | Legacy BSON type differs from current query type | Keep golden fixtures, audit types, and migrate |
| Reactive endpoint blocks threads | Used blocking `MongoTemplate` or blocking repository | Use genuine reactive infrastructure end to end |

## 15. Query-Technique Selection Checklist

Before creating a method:

1. **Are conditions fixed or optional?** How many branches toggle at runtime?
2. **Is a derived method name easy to read?** With only a few criteria, avoid extra abstraction.
3. **Do MongoDB operators express it cleaner in JSON?** For example, `$all` or `$elemMatch`.
4. **Is this actually an aggregation?** If yes, pick `@Aggregation` or the Aggregation API.
5. **Are projection and paging needed?** Never save back partially loaded entities.
6. **Is the tenant condition always present and authenticated?**
7. **What do empty lists, nulls, and missing values mean in the business domain?**
8. **Do converters, enums, IDs, timestamps, and field names match stored BSON?**
9. **Do indexes support filter/sort, and was `explain` checked?**
10. **Is it tested against MongoDB with multi-tenant and legacy fixtures?**

## 16. Applied Exercise

A logistics system has a `shipments` collection with `tenantId`, `trackingCode`, `status`, `priority`, `createdAt`, and an `events` array of `{ at, kind, locationCode }`. It needs to support:

1. Looking up a shipment by `tenantId` and `trackingCode`.
2. Finding shipments with status in a list and `priority >= 5`, using fixed filters.
3. Advanced search with optional status, time window, and event location, with pagination.
4. Aggregating shipment counts by status and week in the business timezone.

**Guidance:**

- Task 1: derived query, such as `findByTenantIdAndTrackingCode(...)`.
- Task 2: `@Query` with `$in` and `$gte`, or a derived query if the name stays readable.
- Task 3: custom fragment with `Criteria`; use `$elemMatch` if multiple criteria must match **the same element** of `events`.
- Task 4: Aggregation API/`@Aggregation` with `$group` and timezone-aware date/week bucketing.

Also test empty status lists, invalid time boundaries, and records from another tenant. Write tests proving every query enforces `tenantId`, then benchmark indexes on production-like data.

## 17. References

- Spring Data MongoDB — [Query Methods](https://docs.spring.io/spring-data/mongodb/reference/mongodb/repositories/query-methods.html): derived queries, `@Query`, and repositories.
- Spring Data Commons — [Custom Repository Implementations](https://docs.spring.io/spring-data/commons/reference/repositories/custom-implementations.html): repository fragments and implementation conventions.
- Spring Data MongoDB — [Querying Documents](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-query-operations.html): `MongoTemplate`, `Query`, and `Criteria`.
- Spring Data MongoDB — [Aggregation Framework](https://docs.spring.io/spring-data/mongodb/reference/mongodb/aggregation-framework.html): pipelines and Aggregation API.
- MongoDB Manual — [Query Documents](https://www.mongodb.com/docs/manual/tutorial/query-documents/): MongoDB filters and operators.
- MongoDB Manual — [Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/): execution plans and metrics.

## Key Takeaways

**Derived queries** excel for short, stable criteria with readable names. **`@Query`** fits fixed JSON filters, specialized operators, and projections. **Custom repository fragments with `MongoTemplate`** fit dynamic criteria assembly and reusable query builders. Given the exact same BSON query, none of the three holds magic performance advantages; what matters is **matching business contracts, tenant isolation, BSON types, indexes, and integration testing**. Choose the simplest option that satisfies all those requirements.
