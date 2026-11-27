# In, NotIn, True, False, and Empty Parameter Collections

> **Chapter:** Derived Queries  
> **Module:** `SPRING_DATA_MONGODB`

Spring Data MongoDB lets you declare queries from **repository method names** instead of writing every MongoDB expression by hand. For example, `findByStatusIn(...)` derives a query checking whether a status belongs to a list; `findByStatusNotIn(...)` excludes listed statuses; `findByActiveTrue()` and `findByActiveFalse()` filter on fixed boolean flags.

These keywords are concise, yet error-prone when **the parameter collection is empty**, when documents **omit the field** or hold **`null`**, and when an application confuses "no filter applied" with "no matching results". In particular, an exclusion query with an empty list can accidentally return a huge dataset if no protective filter is present.

This lesson belongs to `SPRING_DATA_MONGODB`: document mapping, querying via repositories or `MongoTemplate`, along with indexes, aggregations, transactions, reactive access, testing, and performance diagnostics. The direct focus is **the semantics of `In`, `NotIn`, `True`, `False`, and intentional handling of empty inputs**.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Write repository methods using `In`, `NotIn`, `True`, and `False`, and explain the generated MongoDB expressions.
2. Contrast the results of `$in: []` with `$nin: []`, including `null` input arguments.
3. Understand how `$nin` treats missing/`null` fields and why boolean `false` does not equate to a missing field.
4. Combine tenant/store scoping filters, boolean flags, pagination, sorting, and sensible indexes.
5. Write integration tests against real BSON to catch wrong results on empty lists or legacy documents with incomplete fields.

## 2. Four Keywords and Derived Query Expressions

| Keyword in method name | Repository example | Typical MongoDB semantics |
| --- | --- | --- |
| `In` / `IsIn` | `findByStatusIn(statuses)` | `{ status: { $in: [...] } }` |
| `NotIn` / `IsNotIn` | `findByStatusNotIn(statuses)` | `{ status: { $nin: [...] } }` |
| `True` / `IsTrue` | `findByActiveTrue()` | `{ active: true }` |
| `False` / `IsFalse` | `findByActiveFalse()` | `{ active: false }` |

The keywords `True` and `False` in the method name **do not accept a boolean parameter**. The true/false value is fixed by the method name itself.

Examples:

```java
List<OrderDocument> findByActiveTrue();
List<OrderDocument> findByActiveFalse();
```

Unlike:

```java
List<OrderDocument> findByActive(Boolean active);
```

The third method takes **one parameter**, letting the caller supply the value to match. All three operate on **Java property names** in the entity; Spring Data maps property names to BSON field names using mapping metadata.

### 2.1. Membership and Exclusion Semantics

- `$in` returns documents where the field matches **at least one** element in the target list.
- `$nin` returns documents where the field does **not** match any value in the exclusion list; it can also match documents **missing that field**.
- If the field holds an **array**, `$in` matches when at least one array element belongs to the set, while `$nin` matches when no element belongs to the excluded set. This lesson primarily uses scalar `status`.
- `True` and `False` perform **exact boolean matching**, not checks for "has a value" or "has no value".

Do not assume from everyday language that "NotIn" always means "field exists and differs from the given values". MongoDB follows specific rules for missing fields; verify against actual data.

## 3. Sample Dataset: Order Statuses and Activation Flag

An e-commerce application stores documents in the `orders` collection. Statuses can be `NEW`, `PAID`, or `CANCELLED`; the `active` field indicates whether a record is visible in active workflows.

To highlight legacy data cases, we intentionally create documents with **missing fields** or `status: null`.

### 3.1. Seeding Data via mongosh

```javascript
use shop

db.orders.insertMany([
  {
    _id: "O-1",
    storeId: "STORE-HCM",
    status: "NEW",
    active: true,
    createdAt: ISODate("2026-11-20T01:00:00Z")
  },
  {
    _id: "O-2",
    storeId: "STORE-HCM",
    status: "PAID",
    active: false,
    createdAt: ISODate("2026-11-20T02:00:00Z")
  },
  {
    _id: "O-3",
    storeId: "STORE-HCM",
    status: "CANCELLED",
    active: true,
    createdAt: ISODate("2026-11-20T03:00:00Z")
  },
  {
    _id: "O-4",
    storeId: "STORE-HCM",
    active: true,                    // intentionally missing status
    createdAt: ISODate("2026-11-20T04:00:00Z")
  },
  {
    _id: "O-5",
    storeId: "STORE-HCM",
    status: null,                    // BSON null, not a missing field
    active: false,
    createdAt: ISODate("2026-11-20T05:00:00Z")
  },
  {
    _id: "O-6",
    storeId: "STORE-HCM",
    status: "PAID",
    active: true,
    createdAt: ISODate("2026-11-20T06:00:00Z")
  },
  {
    _id: "O-7",
    storeId: "STORE-HCM",
    status: "NEW",
    createdAt: ISODate("2026-11-20T07:00:00Z") // intentionally missing active
  }
])
```

Run this illustrative seed only in an isolated test database. In production applications, `status` and `active` may be required via schema validation; here missing/`null` values are intentional to demonstrate legacy data compatibility.

Summary:

| `_id` | `status` | `active` |
| --- | --- | --- |
| `O-1` | `NEW` | `true` |
| `O-2` | `PAID` | `false` |
| `O-3` | `CANCELLED` | `true` |
| `O-4` | *Missing field* | `true` |
| `O-5` | `null` | `false` |
| `O-6` | `PAID` | `true` |
| `O-7` | `NEW` | *Missing field* |

Subsequent queries evaluate against **these exact seven documents**.

## 4. `In`: Selecting Allowed Values

Suppose an order-processing screen needs all orders with status `NEW` or `PAID`.

```javascript
db.orders.find({
  status: { $in: ["NEW", "PAID"] }
})
```

Matched IDs (order unspecified):

```text
O-1, O-2, O-6, O-7
```

`O-3` is excluded because `CANCELLED` is not in the list; `O-4` lacks `status` and `O-5` has `null`, so neither matches the two string values.

In the repository:

```java
List<OrderDocument> findByStatusIn(
    Collection<OrderStatus> statuses);
```

Invocation:

```java
repository.findByStatusIn(
    List.of(OrderStatus.NEW, OrderStatus.PAID));
```

Under standard enum mapping, Spring Data writes `OrderStatus.NEW` as the string `"NEW"` and derives an `$in` query on `status`. If a project uses a custom converter or alters enum storage, verify the generated BSON and legacy data accordingly.

### 4.1. Combined Conditions

An admin view may only want **active orders with allowed statuses**:

```java
List<OrderDocument> findByStatusInAndActiveTrue(
    Collection<OrderStatus> statuses);
```

Expected expression:

```javascript
db.orders.find({
  status: { $in: ["NEW", "PAID"] },
  active: true
})
```

Results are `O-1` and `O-6`. `O-2` has an allowed status but `active: false`; `O-7` lacks `active`, so it also fails to match.

### 4.2. When the Field Is an Array

For `tags: ["sale", "featured"]`:

```javascript
db.products.find({
  tags: { $in: ["featured", "new"] }
})
```

A document matches if it has **at least one** tag in the given set. Do not confuse `$in` with "document must contain all values"; requiring all values is expressed with `$all` or equivalent conditions.

## 5. `NotIn`: Exclusion Does Not Imply the Field Must Exist

Suppose we need orders **whose status is not `CANCELLED`**:

```javascript
db.orders.find({
  status: { $nin: ["CANCELLED"] }
})
```

Results:

```text
O-1, O-2, O-4, O-5, O-6, O-7
```

Notable detail: **`O-4` (missing `status`) and `O-5` (`status: null`) are still returned**. Neither has the value `CANCELLED`, so `$nin` does not exclude them.

Repository:

```java
List<OrderDocument> findByStatusNotIn(
    Collection<OrderStatus> excludedStatuses);
```

Invocation:

```java
repository.findByStatusNotIn(
    List.of(OrderStatus.CANCELLED));
```

### 5.1. Why `NotIn` Is Not Equivalent to "Remaining Valid Statuses"?

If the current enum has three statuses `NEW`, `PAID`, and `CANCELLED`, one might assume:

```text
status NOT IN (CANCELLED)
  == status IN (NEW, PAID)
```

This assumption is **false** when the collection contains missing fields, `null`, or unrecognized values not yet in the enum. `$nin` only states **what you do not want**, so everything else can still match.

In business workflows or authorization-sensitive queries, pulling in records with unknown statuses can be dangerous. When valid values form a closed set, a safer choice is **positive filtering via `In` with an explicit list of allowed statuses**.

### 5.2. When `status` Must Exist and Be Non-Null

You can use `MongoTemplate` to express the exact criteria:

```java
import java.util.Collection;
import java.util.List;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

public List<OrderDocument> findKnownStatusesNotExcluded(
        MongoTemplate template,
        Collection<OrderStatus> excludedStatuses) {

    Criteria status = Criteria.where("status")
        .exists(true)
        .ne(null)
        .nin(excludedStatuses);

    Query query = Query.query(status);
    return template.find(query, OrderDocument.class);
}
```

This is an **illustrative service method**; it omits empty-input validation and store-level scoping. `$exists: true` requires the key to be present; `$ne: null` removes `null` values; `$nin` excludes disallowed statuses.

Equivalent MongoDB expression:

```javascript
db.orders.find({
  status: {
    $exists: true,
    $ne: null,
    $nin: ["CANCELLED"]
  }
})
```

On the sample data, this returns `O-1`, `O-2`, `O-6`, and `O-7`. If you need **only enum values explicitly approved by the system**, checking existence and non-null is still not enough: a document with `status: "UNKNOWN"` matches `$nin` even though it is not an approved status. In that case, use `$in` with an explicit allowlist.

## 6. `True` and `False`: Exact Boolean Matching

Filtering active orders:

```javascript
db.orders.find({ active: true })
```

Results:

```text
O-1, O-3, O-4, O-6
```

Filtering inactive orders:

```javascript
db.orders.find({ active: false })
```

Results:

```text
O-2, O-5
```

`O-7` **lacks the `active` field**, so it appears in neither set. When the field is `null` or legacy data stores the string `"false"` instead of BSON Boolean `false`, it likewise does not match boolean `false` under standard BSON type matching.

In the repository:

```java
List<OrderDocument> findByActiveTrue();
List<OrderDocument> findByActiveFalse();

// Is-prefixed variants also work:
List<OrderDocument> findByActiveIsTrue();
List<OrderDocument> findByActiveIsFalse();
```

### 6.1. `False` Differs from `Not(True)`

`findByActiveFalse()` means `active == false`. By contrast, the MongoDB query:

```javascript
db.orders.find({ active: { $ne: true } })
```

also matches documents **lacking the `active` field**, as well as non-boolean values (e.g., `null`). Therefore:

```text
active == false   DIFFERS FROM   active != true
```

Never use `$ne: true` as a substitute for `False` when you specifically want BSON Boolean `false`.

### 6.2. Difference Between Primitive `boolean` and Wrapper `Boolean`

In Java:

```java
private boolean active; // only true/false at the Java object level
private Boolean activeFlag; // nullable
```

When reading legacy documents missing the field, primitive `boolean` cannot represent "unknown"; depending on mapping/constructor behavior, a missing value may default to `false` or cause instantiation issues. The `Boolean` wrapper explicitly captures all three states (`true`/`false`/`null`) in the Java model.

If business logic requires `active` to always be present, enforce validation and migrate legacy documents; do not simply switch the Java type and assume missing fields behave properly.

## 7. Empty Parameter Collections: The Most Common Pitfall

Consider two MongoDB queries:

```javascript
db.orders.find({ status: { $in: [] } })
db.orders.find({ status: { $nin: [] } })
```

On the sample dataset:

| Condition | Result | Reason |
| --- | --- | --- |
| `status: { $in: [] }` | **0 documents** | No values can match |
| `status: { $nin: [] }` | **All 7 documents** | No values are excluded |
| `status: { $in: ["NEW"] }` | `O-1, O-7` | Matches only listed statuses |
| `status: { $nin: ["NEW"] }` | `O-2, O-3, O-4, O-5, O-6` | Excludes NEW, still matches missing/null |
| `active: true` | `O-1, O-3, O-4, O-6` | Matches only BSON boolean true |
| `active: false` | `O-2, O-5` | Matches only BSON boolean false |

These are **MongoDB server operator semantics**, assuming Spring Data actually emits `$in`/`$nin` with an empty array. Always test with your actual Spring Data and driver versions instead of guessing whether the framework optimizes away or skips empty conditions uniformly in every context.

### 7.1. "No Status Selected" Has at Least Three Meanings

Suppose a list page receives a `statuses` filter from the UI. If the user selects nothing, the product might intend:

1. **No results:** nothing selected → empty list.
2. **No status filter applied:** show every status the user is authorized to view.
3. **Invalid input:** at least one status must be chosen before querying.

These are three **different** contracts. Do not handle them uniformly by blindly passing `List.of()` into every repository method. In particular:

- For an **allowlist**, empty usually means returning **0 results**.
- For a **denylist**, empty usually means **excluding nothing**, which can return huge datasets if unguarded by other filters.
- For an **authorization scope filter**, "no permissions" must mean **no results**, never accidentally becoming "no restrictions".

### 7.2. A `null` Collection Is Not an Empty Collection

`null` may mean no input was supplied, whereas an empty collection means an input with zero elements was passed. Passing `null` straight to an `In`/`NotIn` repository parameter can cause binding errors or unexpected behavior depending on framework version and settings.

Define the contract clearly in the service/API:

```java
Objects.requireNonNull(statuses, "statuses");
```

If `null` is defined by the product to mean "skip this filter", express that via an explicit named branch in service code rather than passing `null` and hoping the repository drops the condition.

### 7.3. Never Confuse an Empty Collection with a Collection Containing `null`

`List.of()` is an empty list; `[null]` in BSON is a list **containing one null element**. MongoDB operators have special rules for `null` and missing fields, so `$in: [null]` is not equivalent to `$in: []`.

For ordinary enum/boolean queries, **reject `null` elements when the contract forbids them**, and write explicit tests if the application genuinely needs to query null/missing fields.

## 8. Complete Spring Data MongoDB Model and Repository

### 8.1. Status Enum

File `OrderStatus.java`:

```java
package com.example.shop.orders;

public enum OrderStatus {
    NEW,
    PAID,
    CANCELLED
}
```

### 8.2. Entity

File `OrderDocument.java`:

```java
package com.example.shop.orders;

import java.time.Instant;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "orders")
public record OrderDocument(
    @Id String id,
    String storeId,
    OrderStatus status,
    Boolean active,
    Instant createdAt
) {}
```

`Boolean active` is chosen to model legacy documents missing the field: on read, the object can hold `null` instead of assuming missing equals `false`. `OrderStatus` values are stored as enum name strings by default when no custom converter is registered. IDs like `O-1` are not ObjectId-shaped, so they are stored as BSON Strings in this example.

### 8.3. Repository with the Four Keywords

File `OrderRepository.java`:

```java
package com.example.shop.orders;

import java.util.Collection;
import java.util.List;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface OrderRepository
        extends MongoRepository<OrderDocument, String> {

    List<OrderDocument> findByStatusIn(
        Collection<OrderStatus> statuses);

    List<OrderDocument> findByStatusNotIn(
        Collection<OrderStatus> statuses);

    List<OrderDocument> findByActiveTrue();

    List<OrderDocument> findByActiveFalse();

    List<OrderDocument> findByStatusInAndActiveTrue(
        Collection<OrderStatus> statuses);

    List<OrderDocument> findByStatusNotInAndActiveTrue(
        Collection<OrderStatus> excludedStatuses);

    Page<OrderDocument> findByStoreIdAndStatusInAndActiveTrue(
        String storeId,
        Collection<OrderStatus> statuses,
        Pageable pageable);
}
```

Spring Data parses method names from the **properties** `status`, `active`, and `storeId`. No manual implementation is needed when repositories are scanned/registered properly. If a BSON field is renamed with `@Field("order_status")`, the method name still uses **`Status`** because that is the Java property name; mapping infrastructure handles the target field.

### 8.4. Method Name → Derived Query Mapping

| Method | Derived condition |
| --- | --- |
| `findByStatusIn([NEW, PAID])` | `status: { $in: ["NEW","PAID"] }` |
| `findByStatusNotIn([CANCELLED])` | `status: { $nin: ["CANCELLED"] }` |
| `findByActiveTrue()` | `active: true` |
| `findByActiveFalse()` | `active: false` |
| `findByStatusInAndActiveTrue([NEW, PAID])` | `$in` on status **and** active equals true |
| `findByStatusNotInAndActiveTrue([CANCELLED])` | `$nin` on status **and** active equals true |
| `findByStoreIdAndStatusInAndActiveTrue("STORE-HCM", [...], page)` | Scopes to store, filters status and active, and applies paging |

`And` combines conditions with logical intersection. As criteria grow, method names become hard to read; for complex queries, consider `MongoTemplate`, `@Query`, or `Aggregation` instead of cramming every keyword into a single long name.

## 9. Handling Empty Inputs Deliberately in the Service Layer

The repository should not decide the business meaning of "no selection". The service should enforce the contract and scope data before querying.

### 9.1. Allowlist: Empty Means No Results

File `OrderFilterService.java`:

```java
package com.example.shop.orders;

import java.util.Collection;
import java.util.List;
import java.util.Objects;
import org.springframework.stereotype.Service;

@Service
public class OrderFilterService {
    private final OrderRepository repository;

    public OrderFilterService(OrderRepository repository) {
        this.repository = repository;
    }

    public List<OrderDocument> findAllowedStatuses(
            Collection<OrderStatus> statuses) {
        Objects.requireNonNull(statuses, "statuses");

        // No statuses permitted.
        if (statuses.isEmpty()) {
            return List.of();
        }
        if (statuses.stream().anyMatch(Objects::isNull)) {
            throw new IllegalArgumentException(
                "statuses list must not contain null");
        }
        return repository.findByStatusIn(statuses);
    }
}
```

With this contract, `findAllowedStatuses(List.of())` returns an empty list **without hitting MongoDB**. This is explicit, saves a query round trip, and avoids depending on how the framework treats empty `In`.

### 9.2. Denylist: Empty Can Be Rejected

If a method serves an export requiring at least one exclusion criterion, require callers to supply at least one status:

```java
public List<OrderDocument> findWithExclusions(
        Collection<OrderStatus> excludedStatuses) {
    Objects.requireNonNull(
        excludedStatuses, "excludedStatuses");

    if (excludedStatuses.isEmpty()) {
        throw new IllegalArgumentException(
            "Must select at least one status to exclude");
    }
    if (excludedStatuses.stream().anyMatch(Objects::isNull)) {
        throw new IllegalArgumentException(
            "Exclusion list must not contain null");
    }

    return repository.findByStatusNotIn(excludedStatuses);
}
```

This is an **illustrative method** you could add to `OrderFilterService` above. It is not a mandatory framework rule: an ordinary search feature might legitimately define "empty denylist = exclude nothing".

If you choose "exclude nothing", call **a query with explicit limits and scoping**, such as `findByActiveTrue()` only in a single-store system, or better `findByStoreIdAndActiveTrue(storeId)` in multi-store systems. Never let an empty input turn into an unbounded full collection scan.

### 9.3. Never Trust Tenant/`storeId` Blindly from Untrusted Input

Suppose each user may only view orders belonging to authorized stores. In the service, `storeId` must be resolved/verified from the security context, not blindly trusted from a request string. The repository method:

```java
Page<OrderDocument> findByStoreIdAndStatusInAndActiveTrue(
    String storeId,
    Collection<OrderStatus> statuses,
    Pageable pageable);
```

expresses that scoping in the query. If `statuses` is empty, return an empty page intentionally; never fall back to a method without the store filter when "no status is chosen".

## 10. Pagination and Sorting

When an `In` list covers multiple statuses, matched records can be numerous. Bound page sizes and enforce deterministic sorting:

```java
import java.util.List;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;

PageRequest pageRequest = PageRequest.of(
    0,
    20,
    Sort.by(
        Sort.Order.desc("createdAt"),
        Sort.Order.desc("id")
    )
);

Page<OrderDocument> page =
    repository.findByStoreIdAndStatusInAndActiveTrue(
        "STORE-HCM",
        List.of(OrderStatus.NEW, OrderStatus.PAID),
        pageRequest
    );
```

`id` is the Java property mapped to `_id`. Adding `id` as a tie-breaker yields deterministic ordering when multiple documents share the same `createdAt`. This snippet assumes an injected `repository` field.

`Page` usually entails computing the total element count for total pages, adding count-query cost. If the UI only needs a "load more" button, consider `Slice` or keyset pagination depending on framework version and product needs.

**Do not treat `Pageable` as a total safety net**: enforce max page sizes at the API layer and retain access-scoping criteria. A low-selectivity `NotIn` query with a huge page size can still impose heavy load.

## 11. Interacting with Null, Missing Data, and Migrations

When upgrading a live system, older documents may lack `status`/`active`, use different data types, or hold retired enum values.

### 11.1. Checking Actual Field Presence

```javascript
// Missing status field.
db.orders.find({
  status: { $exists: false }
})

// Status field exists and is non-null.
db.orders.find({
  status: { $exists: true, $ne: null }
})

// Boolean active is actually false.
db.orders.find({
  active: false
})
```

On the sample data, the first returns `O-4`, the second returns `O-1`, `O-2`, `O-3`, `O-6`, and `O-7`, and the third returns `O-2` and `O-5`.

**Never rely on `$exists: true` alone to claim a field has a value:** a field present with BSON `null` still satisfies `$exists: true`.

### 11.2. When New Enum Values Are Added

Suppose a new release adds `REFUNDED` as a status. `NotIn([CANCELLED])` will automatically include `REFUNDED`, even if a legacy UI only expects `NEW` and `PAID`. `In([NEW, PAID])` does not silently expand when the enum grows.

This is a major reason to prefer **allowlists** for actions requiring approved statuses, such as settlement, sensitive exports, or batch processing. Expanding the accepted domain should be a tested business decision, not an accidental side effect of `NotIn`.

### 11.3. Three-Valued Boolean States

If a missing `active` flag means "undetermined", do not silently coerce it to `false` without a data decision. You may need a migration backfilling the field from an authoritative source or introducing a business state like `UNKNOWN`.

When the Java model uses `Boolean`, handle `null` explicitly in the service. `findByActiveFalse()` will not automatically match documents missing `active` to fill in for undetermined items.

## 12. Performance, Indexes, and Collection Size Limits

Derived keywords only construct the **query**; actual speed depends on data distribution, indexes, and parameter list sizes.

For an endpoint commonly filtering by `storeId`, `active`, a set of `status` values, and sorting newest `createdAt` first:

```javascript
db.orders.createIndex({
  storeId: 1,
  active: 1,
  status: 1,
  createdAt: -1,
  _id: -1
})
```

This index is a **candidate to benchmark** against your query pattern, not a universal guarantee for every `In` set. With multiple values in `$in`, index scanning and sorting behavior differ from single-value equality; some plans still require an extra sort stage.

Inspect the query plan:

```javascript
db.orders
  .find({
    storeId: "STORE-HCM",
    active: true,
    status: { $in: ["NEW", "PAID"] }
  })
  .sort({ createdAt: -1, _id: -1 })
  .limit(20)
  .explain("executionStats")
```

Monitor `totalKeysExamined`, `totalDocsExamined`, `nReturned`, and execution time on representative data. Running `explain` in `mongosh` does not measure total service overhead (serialization, network round trips, count queries, object mapping), yet it reveals how MongoDB executes the query.

### 12.1. `$nin` Usually Has Poor Selectivity

`$nin` can match most of a collection, especially when the exclusion list is small. Having an index on `status` does not guarantee `$nin` runs fast; MongoDB may still examine many documents.

When only a small set of statuses is valid, `$in` with the allowed statuses both expresses business intent clearly and constrains the result set better.

### 12.2. Oversized `In` Lists

When `statuses` holds a few enum values, overhead is negligible. However, another endpoint might call `findByIdIn(Collection<String> ids)` with tens of thousands of IDs. Huge lists inflate command size, processing cost, and can hit BSON request limits. For large batches, consider chunking, staging collections, or alternative query designs depending on the problem.

Never construct `In`/`NotIn` lists from unbounded user input. Enforce length limits at the API/service boundary and measure against realistic data distributions.

### 12.3. Counting and Aggregation Queries

Derived methods can also count or check existence:

```java
long countByStatusIn(Collection<OrderStatus> statuses);
boolean existsByStatusIn(Collection<OrderStatus> statuses);
```

They follow the same set semantics and must apply the same empty-input contracts. For dashboards grouping multiple statuses or summing revenue, `Aggregation`/`MongoTemplate` fits better than calling multiple repository methods repeatedly.

## 13. Integration Testing Against Real MongoDB

Rules around `$in`, `$nin`, and missing fields must be tested against **actual stored BSON**. Mocked repository tests cannot prove how MongoDB handles empty lists.

The example below uses Spring Boot `@DataMongoTest` against a dedicated test MongoDB instance (configurable via Testcontainers depending on project setup).

### 13.1. Seeding via Driver to Create Both Missing and Null Fields

File `OrderDerivedQueriesTest.java`:

```java
package com.example.shop.orders;

import java.time.Instant;
import java.util.Date;
import java.util.List;
import org.bson.Document;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.data.mongodb.core.MongoTemplate;

import static org.assertj.core.api.Assertions.assertThat;

@DataMongoTest
class OrderDerivedQueriesTest {
    @Autowired
    MongoTemplate template;

    @Autowired
    OrderRepository repository;

    private static Document order(
            String id, String status, Boolean active) {
        Document document = new Document("_id", id)
            .append("storeId", "STORE-HCM")
            .append(
                "createdAt",
                Date.from(Instant.parse("2026-11-20T01:00:00Z"))
            );
        if (status != null) {
            document.append("status", status);
        }
        if (active != null) {
            document.append("active", active);
        }
        return document;
    }

    private static List<String> ids(List<OrderDocument> documents) {
        return documents.stream()
            .map(OrderDocument::id)
            .toList();
    }

    @BeforeEach
    void seed() {
        var collection = template.getCollection("orders");
        collection.deleteMany(new Document());

        Document missingStatus = order("O-4", null, true);
        Document nullStatus = order("O-5", null, false);
        nullStatus.append("status", null);
        Document missingActive = order("O-7", "NEW", null);

        collection.insertMany(List.of(
            order("O-1", "NEW", true),
            order("O-2", "PAID", false),
            order("O-3", "CANCELLED", true),
            missingStatus,
            nullStatus,
            order("O-6", "PAID", true),
            missingActive
        ));
    }

    @Test
    void inMatchesOnlyAllowedStatuses() {
        assertThat(ids(repository.findByStatusIn(
            List.of(OrderStatus.NEW, OrderStatus.PAID))))
            .containsExactlyInAnyOrder(
                "O-1", "O-2", "O-6", "O-7");
    }

    @Test
    void notInCanIncludeMissingAndNullStatuses() {
        assertThat(ids(repository.findByStatusNotIn(
            List.of(OrderStatus.CANCELLED))))
            .containsExactlyInAnyOrder(
                "O-1", "O-2", "O-4", "O-5", "O-6", "O-7");
    }

    @Test
    void trueAndFalseDoNotTreatMissingAsFalse() {
        assertThat(ids(repository.findByActiveTrue()))
            .containsExactlyInAnyOrder(
                "O-1", "O-3", "O-4", "O-6");

        assertThat(ids(repository.findByActiveFalse()))
            .containsExactlyInAnyOrder("O-2", "O-5");
    }

    @Test
    void emptyCollectionsHaveOppositeServerSemantics() {
        assertThat(repository.findByStatusIn(List.of()))
            .isEmpty();

        assertThat(repository.findByStatusNotIn(List.of()))
            .hasSize(7);
    }

    @Test
    void combinedFiltersExcludeWrongBooleanValues() {
        assertThat(ids(repository.findByStatusInAndActiveTrue(
            List.of(OrderStatus.NEW, OrderStatus.PAID))))
            .containsExactlyInAnyOrder("O-1", "O-6");
    }
}
```

The test seeds data directly via `MongoTemplate.getCollection(...)` (driver) instead of saving `OrderDocument`, ensuring missing `status` truly differs from `status: null`. That distinction is hard to observe when using mocks or saving entities from a new Java model.

**Prerequisites:** the test must run against an isolated test MongoDB; `deleteMany(new Document())` clears the entire `orders` collection in the test database. Never point this test at a real database or one shared with another process. The `@DataMongoTest` import reflects Spring Boot versions providing the annotation in that namespace; when upgrading major versions, check the package import of your actual dependency.

If `emptyCollectionsHaveOppositeServerSemantics` behaves unexpectedly, inspect the exact MongoDB commands sent by your Spring Data/driver version and any custom query configuration. The goal of the test is to **lock in the contract** and catch behavioral changes across upgrades.

### 13.2. Direct BSON Check for Both Empty Operators

To separate MongoDB server semantics from repository method parsing, run:

```javascript
db.orders.countDocuments({ status: { $in: [] } })   // 0
db.orders.countDocuments({ status: { $nin: [] } })  // 7
```

If the repository layer returns different counts, inspect Spring Data's parameter binding or query transformation rather than assuming MongoDB behaves differently.

### 13.3. Additional Scenarios to Cover

| Scenario | Expected behavior |
| --- | --- |
| `null` input instead of collection | Service rejects or applies contract properly without passing straight to repository |
| Collection containing `null` | Service rejects or explicitly tests MongoDB semantics if permitted |
| New status introduced | `In` does not expand beyond allowlist; `NotIn` may match unknown values |
| Missing/null/string `active` field | `True`/`False` match only the corresponding BSON Boolean |
| Multiple statuses with store scope | Never leaks another store's documents, even on empty input |
| Paging with equal `createdAt` | Tie-break by `_id` keeps order deterministic |
| `NotIn` on large collections | Measure documents examined and latency to spot low-selectivity queries |
| Custom enum converter changes | Verify BSON queries and legacy records, not only new enums |

## 14. Do Reactive Repositories Have Different Semantics?

With reactive access, derived method names express the same conditions; differences lie in return types and asynchronous execution:

```java
import java.util.Collection;
import org.springframework.data.mongodb.repository.ReactiveMongoRepository;
import reactor.core.publisher.Flux;

public interface ReactiveOrderRepository
        extends ReactiveMongoRepository<OrderDocument, String> {

    Flux<OrderDocument> findByStatusIn(
        Collection<OrderStatus> statuses);

    Flux<OrderDocument> findByStatusNotIn(
        Collection<OrderStatus> excludedStatuses);

    Flux<OrderDocument> findByActiveTrue();

    Flux<OrderDocument> findByActiveFalse();
}
```

Never assume Reactive automatically optimizes `NotIn(empty)` or skips missing fields. In reactive pipelines, services must still **validate parameters upfront**, enforce access boundaries, and write tests with `StepVerifier` or equivalent tools. A slow `Flux` caused by an unselective query remains a performance issue even when it does not block threads imperatively.

## 15. Common Pitfalls and Fixes

| Symptom | Common cause | Solution |
| --- | --- | --- |
| `findByStatusIn(empty)` returns no data | `$in: []` has no values to match | If intended, return empty list in service; if "unfiltered", write a separate branch |
| `findByStatusNotIn(empty)` returns too much data | `$nin: []` excludes nothing | Reject empty input when required or enforce tight scoping filters |
| `NotIn([CANCELLED])` returns documents missing status | `$nin` matches missing fields | Use positive allowlist `In`, or add `$exists`/`$ne` per contract |
| `findByActiveFalse()` misses documents without active | Boolean false differs from missing/null | Migrate/validate data or define explicit handling for unknown states |
| Query returns wrong results after BSON field rename | Confused Java property name with stored field | Check `@Field`, metadata, and query mapper |
| New enum values appear in `NotIn` results | Query uses a denylist instead of allowlist | Define a positive set of allowed statuses |
| `NotIn` very slow despite index on status | Low-selectivity filter matching most documents | Run `explain` and add filters/indexes by tenant, active, time |
| Pagination duplicates/misses items between reads | Missing tie-break sort, concurrent writes | Sort by `createdAt` + `_id`, use keyset paging where suitable |
| Mocked repository tests pass, production fails | Mocks do not execute BSON queries | Add integration tests with real missing/null documents |
| Empty input widens data access scope | Service drops filters without keeping security checks | Retain store/tenant bounds and fail-closed on empty allowlists |

## 16. Applied Exercise

A device management system stores documents in a `devices` collection with fields:

- `region`: tenant-scoped region code.
- `state`: `ONLINE`, `OFFLINE`, `MAINTENANCE`, possibly missing in older records.
- `verified`: BSON Boolean, possibly `null` if unverified.
- `lastSeenAt`: BSON Date.

An admin dashboard must display devices in allowed states, only verified devices, sorted newest first. Meanwhile, a separate report accepts a list of states to exclude.

Complete the following:

1. Write repository method `findByRegionAndStateInAndVerifiedTrue(...)` supporting `Pageable`; specify which parameters must be non-null/non-empty.
2. When `allowedStates = []`, should you return 0 results or drop the filter? Explain using access-control policy.
3. When `excludedStates = []`, explain why `NotIn` could return every device if scoping filters are missing.
4. Insert one document with `verified: false`, one missing `verified`, and one with `verified: null`, and check which documents `findByVerifiedFalse()` returns.
5. Propose a candidate index for querying by `region`/`verified`/`state` and sorting by `lastSeenAt`; verify using `explain`.
6. Introduce a new state `QUARANTINED` and check whether allowlist and denylist queries still obey business rules.

**Solution guidance:** for an access-controlled allowlist, an empty set should return **no records**. For a denylist, an empty set means no values excluded in MongoDB, so tenant/region scoping and page limits must still remain enforced. `False` matches only BSON Boolean false, not null or missing. Efficient queries come from data modeling, indexes, and tight scoping — not shorter repository method names.

## 17. References

- Spring Data MongoDB — [Query Methods](https://docs.spring.io/spring-data/mongodb/reference/mongodb/repositories/query-methods.html): declaring derived queries and MongoDB keywords.
- Spring Data Commons — [Repository Query Keywords](https://docs.spring.io/spring-data/commons/reference/repositories/query-keywords-reference.html): repository method syntax and keywords.
- MongoDB Manual — [`$in`](https://www.mongodb.com/docs/manual/reference/operator/query/in/): set membership, array fields, and performance notes.
- MongoDB Manual — [`$nin`](https://www.mongodb.com/docs/manual/reference/operator/query/nin/): set exclusion and rules for missing fields.
- MongoDB Manual — [`$exists`](https://www.mongodb.com/docs/manual/reference/operator/query/exists/): distinguishing present vs. missing fields.

## Summary

`In`/`NotIn` are derived by Spring Data MongoDB into set membership/exclusion conditions; `True`/`False` perform **exact boolean matching**. The key takeaway is that **`$in: []` matches zero documents, whereas `$nin: []` excludes zero documents**. Moreover, `$nin` can match documents missing the field, whereas `False` never matches missing or null fields. Define explicit contracts for empty inputs at the service layer, prefer allowlists for permission-sensitive logic, preserve store/tenant filters, test against real BSON with null and missing values, and measure queries with indexes and `explain` before deploying.
