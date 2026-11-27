# Pagination, Sorting, and Limits of Offset-Based Pagination in Spring Data MongoDB

An order-management screen cannot load millions of documents in a single API call. Instead, the application displays pages of 20–50 orders, sorted by creation date or status, with page navigation controls. In **Spring Data MongoDB**, abstractions such as `Pageable`, `PageRequest`, `Sort`, `Page<T>`, and `Slice<T>` make this convenient to implement, while `MongoTemplate` gives fine-grained control over queries.

However, **offset-based pagination** has two fundamental limitations that a single `findAll(pageable)` call does not solve on its own:

1. **Cost of deep pages:** to return a page at a large offset, MongoDB typically still has to scan through all preceding results before the target page, even when the query uses an index. The response holds only 20 documents, yet server-side work can be huge.
2. **Unstable results when data changes:** inserting a new document or deleting an older one before the offset can cause subsequent pages to **duplicate or skip** records. Sorting on a non-unique field causes ordering issues even without concurrent writes.

This lesson belongs to the **Spring Data MongoDB** chapter of the *Database Engine Document MongoDB* module. We will progress from basic pagination APIs, index design, and frontend response contracts to diagnosing `skip`, choosing `Slice`, and implementing **keyset/seek pagination** for large lists. Examples use Java, Spring Data MongoDB, Spring Boot, and `mongosh`; framework, driver, and server versions vary, so always check the exact APIs of your dependencies before deploying.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain page index, page size, offset, sort, and limit; distinguish 1-based UI page numbers from Spring Data's 0-based index.
2. Construct `PageRequest.of(...)` and multi-field `Sort` specifications with ascending/descending directions and a tie-breaker key.
3. Define repositories returning `Page<Order>` and `Slice<Order>` with proper tenant filters.
4. Understand why `Page` typically requires total count computation and when to avoid count overhead.
5. Use `MongoTemplate` with `Query.with(Pageable)` and an independent count query.
6. Explain how offset pagination maps to MongoDB's `sort + skip + limit`.
7. Understand how compound indexes aligned with filter/sort affect query plans and read `explain("executionStats")`.
8. Identify how `skip` cost grows with offset and why adding an index does not eliminate all traversal cost.
9. Establish deterministic ordering using `createdAt` combined with `_id`; handle duplicate values and missing fields.
10. Describe how duplicate/missing records occur when data is inserted, deleted, or updated between page requests.
11. Distinguish offset pagination, MongoDB server cursor batching, and keyset/seek pagination.
12. Write a keyset query using the `(createdAt, _id)` pair in descending order.
13. Understand `Window<T>`/`ScrollPosition` in Spring Data versions that support scrolling.
14. Design REST APIs that bound page size, whitelist sort fields, enforce tenant scope, and validate continuation tokens.
15. Evaluate consistency, read concern, count accuracy, sharding, and criteria for choosing offset vs. keyset.
16. Plan benchmarks and tests to verify pagination performance and correctness.

## 2. Why Paginate?

Suppose an `orders` collection holds 5 million documents. An API calling:

~~~java
List<Order> all = orderRepository.findAll();
~~~

creates severe problems:

- Transfers massive numbers of BSON documents from MongoDB to the backend.
- Spikes RAM, GC pauses, and JSON serialization time to the frontend.
- Increases network bytes and latency.
- Causes request timeouts.
- Fetches data the UI screen does not even display.
- Makes tenant isolation and resource bounding harder under broad queries.

Instead of loading everything, the API returns a small page:

~~~text
GET /api/orders?page=0&size=20

content: first 20 orders
page: 0
size: 20
hasNext: true
~~~

Principle: **read and transmit only the records needed for the current interaction**, with explicit filters, sorting, size bounds, and authorization.

### 2.1. A Page Is Not a Default Snapshot

Page 0 read at 10:00 and page 1 read at 10:01 are two separate queries. If data changes during that minute, the combined pages no longer correspond to a frozen list. Business workflow correctness dictates whether that trade-off is acceptable.

### 2.2. Pagination Does Not Replace Projections

A page of 20 documents where each document carries a 10 MiB array still consumes massive bandwidth. Combine pagination with database projections/DTOs and select only required fields.

## 3. Terminology: page, size, offset, sort, limit

Suppose data is already ordered:

~~~text
Position:    0   1   2   3   4   5   6   7   8   9   10  11
Document:    A   B   C   D   E   F   G   H   I   J    K   L

size = 4
page 0 -> A B C D
page 1 -> E F G H
page 2 -> I J K L
~~~

With 0-based page indexing:

\[
\text{offset} = \text{pageNumber}\times\text{pageSize}
\]

And in MongoDB, conceptually:

~~~javascript
db.orders.find(filter)
  .sort(sort)
  .skip(offset)
  .limit(size)
~~~

| Concept | Meaning |
|---|---|
| `pageNumber` | Page index; Spring Data starts at `0` |
| `pageSize` | Maximum requested items per page |
| `offset` | Number of preceding results to skip before the page |
| `sort` | Ordering defining which items come before/after others |
| `limit` | Maximum number of records returned by the query |
| `totalElements` | Total matching documents for the filter, if counted |
| `totalPages` | Total pages derived from `totalElements` and `pageSize` |
| `hasNext` | Signal indicating whether another page is available |

### 3.1. Arithmetic Example

`PageRequest.of(4, 25)` has an offset of `4 × 25 = 100`. MongoDB must skip 100 preceding results before returning up to 25 results.

### 3.2. UI Page Indexing

The UI might display "Page 1" for `page=0`. If the frontend uses 1-based indexing, **convert it at a single well-defined boundary** before constructing `PageRequest`—never subtract 1 across multiple layers.

## 4. Three Return Types to Distinguish

Spring Data offers multiple abstractions:

| Type | Primary Data | Additional Metadata | Trade-off |
|---|---|---|---|
| `List<T>` | List of elements | No built-in page metadata | Simple, but app handles `hasNext`/totals itself |
| `Slice<T>` | Content of a data slice | Page info, `hasNext()`, `hasPrevious()` | Avoids total record count |
| `Page<T>` | Content of a page | `getTotalElements()`, `getTotalPages()`, navigation | May require an extra count query |
| `Window<T>` | A scrolling window | Scroll positions and next-window semantics | Used for scrolling in supporting Spring Data versions |

### 4.1. `Page<T>` When Exact Page Counts Are Needed

For example, an admin dashboard showing:

~~~text
Page 7 / 231
Total 11,542 orders
~~~

The application needs the total count. `Page<Order>` fits well here, though the count query can be expensive on large datasets.

### 4.2. `Slice<T>` When You Only Need "Load More"

For example, a mobile feed:

~~~text
20 orders
[Load more] if hasNext=true
~~~

There is no need to display "231 pages." `Slice` avoids total count overhead—typically by fetching one extra element to determine whether more data exists, depending on the repository/query implementation.

### 4.3. `List<T>` Does Not Inherently Cap Result Counts

A repository method returning `List<Order>` can still accept a `Pageable` to limit results per its contract, but without a limit parameter it may return unbounded documents. Returning `List` **does not generate pagination metadata**.

## 5. Order Model for Spring Data Examples

Suppose orders are stored in the `orders` collection with fields:

~~~javascript
{
  _id: ObjectId("..."),
  tenantId: "t-01",
  orderNo: "O-1001",
  status: "PAID",
  totalMinor: NumberLong(120000),
  createdAt: ISODate("2026-11-01T10:00:00Z")
}
~~~

Java domain class:

~~~java
package example.orders;

import java.time.Instant;
import org.bson.types.ObjectId;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "orders")
public class Order {
    @Id
    private ObjectId id;
    private String tenantId;
    private String orderNo;
    private String status;
    private long totalMinor;
    private Instant createdAt;

    protected Order() {}

    public ObjectId getId() { return id; }
    public String getTenantId() { return tenantId; }
    public String getOrderNo() { return orderNo; }
    public String getStatus() { return status; }
    public long getTotalMinor() { return totalMinor; }
    public Instant getCreatedAt() { return createdAt; }

    // Constructors/setters/validation per application aggregate design.
}
~~~

`@Document` selects the collection. `@Id` maps `id` to the BSON `_id` field per Spring Data MongoDB rules. Throughout these examples, `ObjectId` is used as a tie-breaker for sorting and keyset pagination.

### 5.1. Why Use `createdAt`?

Screens commonly show "newest first." A stable creation timestamp, written consistently and properly indexed, is a natural primary sort key. However, **multiple documents can share the exact same `createdAt`**, especially at millisecond precision.

### 5.2. Why Include `tenantId`?

In multi-tenant applications, the tenant filter must come from an authenticated context. Paginating across the entire collection and filtering tenants afterward in application code causes partial pages, wasted bandwidth, and data-leak risks.

### 5.3. Monetary Amount Field

`totalMinor` illustrates storing integer minor currency units. Choosing monetary types and precision belongs to business schema design; pagination does not alter data-type semantics.

## 6. Basic Repository with MongoRepository

Definition:

~~~java
package example.orders;

import org.bson.types.ObjectId;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Slice;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface OrderRepository
        extends MongoRepository<Order, ObjectId> {

    Page<Order> findByTenantIdAndStatus(
        String tenantId,
        String status,
        Pageable pageable
    );

    Slice<Order> readByTenantIdAndStatus(
        String tenantId,
        String status,
        Pageable pageable
    );
}
~~~

Both methods share the same filter criteria but have **different return types**. Both `findBy` and `readBy` are valid Spring Data derived-query prefixes; using different prefixes simply avoids a Java method-signature collision and implies no difference in auth or consistency semantics.

### 6.1. Scope of the Repository Method

`tenantId` and `status` go directly into the database filter rather than merely tagging the response. Sorting and limits come from `Pageable`.

### 6.2. Repository Methods Do Not Enforce Tenant Ownership Automatically

If a service passes an arbitrary tenant ID from a request parameter, the repository will happily return that tenant's data under the service account's privileges. Always validate tenant ownership against the authenticated principal/security context before calling the repository.

### 6.3. Differences Across Spring Data Versions

APIs like `MongoRepository`, `Pageable`, `Page`, and `Slice` are widely established, though repository interfaces and scrolling extensions can evolve across major Spring Data releases. Pin compatible versions via your BOM and consult the matching Javadoc rather than mixing snippets across distant releases.

## 7. `PageRequest.of()` and `Sort`

To fetch the first page of PAID orders, newest first:

~~~java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;

Sort orderByNewest = Sort.by(
    Sort.Order.desc("createdAt"),
    Sort.Order.desc("id")
);

Pageable pageable = PageRequest.of(
    0,    // page index: 0-based
    20,   // page size
    orderByNewest
);

Page<Order> page = orderRepository.findByTenantIdAndStatus(
    "t-01", "PAID", pageable
);
~~~

Spring Data translates the `@Id` property `id` to BSON field `_id` when generating the MongoDB query. The sort pair corresponds to:

~~~javascript
{ createdAt: -1, _id: -1 }
~~~

### 7.1. Ascending and Descending

~~~java
Sort asc = Sort.by(Sort.Order.asc("totalMinor"));
Sort desc = Sort.by(Sort.Order.desc("createdAt"));
~~~

A compound sort prioritizes the first field, then uses subsequent fields to order ties:

~~~java
Sort stable = Sort.by(
    Sort.Order.desc("createdAt"),
    Sort.Order.desc("id")
);
~~~

### 7.2. Sort Fields Use Java Property Names

On the `Order` entity, `"createdAt"` is the Java property and `"id"` maps to `_id`. If a property uses `@Field("created_at")`, Spring Data mapping translates the Java property name to the BSON field name. Avoid passing raw BSON field names blindly into Spring Data APIs without understanding the mapping layer.

### 7.3. PageRequest Starts at 0

~~~java
PageRequest.of(0, 20); // offset = 0
PageRequest.of(1, 20); // offset = 20
PageRequest.of(5, 20); // offset = 100
~~~

Negative page numbers or invalid sizes are rejected. The service should validate inputs upfront and return clear HTTP errors rather than letting raw framework exceptions leak out.

## 8. Reading Metadata from `Page<T>`

~~~java
Page<Order> page = orderRepository.findByTenantIdAndStatus(
    "t-01",
    "PAID",
    PageRequest.of(
        2, 20,
        Sort.by(Sort.Order.desc("createdAt"),
                Sort.Order.desc("id"))
    )
);

System.out.println(page.getNumber());        // 2
System.out.println(page.getSize());          // 20
System.out.println(page.getNumberOfElements());
System.out.println(page.getTotalElements());
System.out.println(page.getTotalPages());
System.out.println(page.hasNext());
System.out.println(page.isFirst());
System.out.println(page.isLast());
~~~

### 8.1. Page Size vs. Content Length

The final page might contain 7 documents even when page size is 20. Here `getSize()` remains `20` (requested size), while `getNumberOfElements()` is `7`.

### 8.2. Total Elements and Total Pages

If count = 105 and size = 20:

\[
\text{totalPages}=\left\lceil \frac{105}{20}\right\rceil=6
\]

Page indices `0–5` can contain data. Index `6` or higher returns an empty page, depending on the data and query.

### 8.3. Totals Can Shift Between Page Requests

`getTotalElements()` reflects the count query executed during that specific request. Concurrent inserts or deletes can make page 2 report a different total than page 1 did moments earlier.

## 9. Why Can `Page<T>` Trigger a Count Query?

To return accurate total element and page counts, Spring Data must know **how many documents match the filter**, beyond just the current page slice. In MongoDB, this typically corresponds to:

~~~javascript
// Fetch content
db.orders.find({
  tenantId: "t-01",
  status: "PAID"
})
.sort({ createdAt: -1, _id: -1 })
.skip(40)
.limit(20)

// Fetch total
db.orders.countDocuments({
  tenantId: "t-01",
  status: "PAID"
})
~~~

These snippets express the two logical operations; Spring Data may optimize away or skip count queries when total elements can be inferred from the content result. Never assert that every `Page` query executes exactly two commands across every framework version.

### 9.1. Counts Can Be Expensive

With broad filters, counting millions of matching documents consumes CPU and index traversal—especially when indexes are suboptimal or the cluster is sharded. If the frontend never displays a total count, that cost is wasted.

### 9.2. `estimatedDocumentCount()` Cannot Replace Filtered Counts

MongoDB provides an API to estimate collection document counts from metadata in appropriate contexts, but it cannot compute the exact count for `tenantId="t-01" AND status="PAID"`. Never substitute a collection-wide estimate for a filtered count to compute `totalPages`.

### 9.3. Page Content and Count Do Not Share a Snapshot Automatically

When the content query and count query run separately, data can change in between. `totalElements` may slightly disagree with the slice just read. If the business requires a point-in-time consistent view, use an appropriate snapshot read or transaction with its associated operational costs; `Page` alone does not guarantee snapshot consistency.

## 10. Using `Slice<T>` to Avoid Total Counts When Unneeded

Repository method:

~~~java
Slice<Order> slice = orderRepository.readByTenantIdAndStatus(
    "t-01",
    "PAID",
    PageRequest.of(
        0, 20,
        Sort.by(Sort.Order.desc("createdAt"),
                Sort.Order.desc("id"))
    )
);

System.out.println(slice.getNumberOfElements());
System.out.println(slice.hasNext());
System.out.println(slice.hasPrevious());
~~~

`Slice` indicates whether further navigation is possible **without exposing `totalElements` or `totalPages`**. Typically, the repository fetches `size + 1` elements to determine `hasNext` rather than counting all matching documents; exact query mechanics depend on the framework and driver implementation.

### 10.1. "Load More" Example

~~~text
Page 0: 20 records, hasNext=true
Page 1: 20 records, hasNext=true
Page 2: 11 records, hasNext=false
~~~

The API does not need to report "Page 3 of 3"—only whether a Load More button should remain active.

### 10.2. Slice Can Still Use Offsets

This is a common misconception: constructing a `Slice` with `PageRequest.of(page, size, sort)` **still uses `offset`/`skip`** to reach deeper pages. `Slice` avoids the count query, **but does not eliminate `skip` overhead or insert/delete drift**.

### 10.3. When Is Page Still Reasonable?

An administrator wants to jump to page 7 out of 20; the dataset is moderate and the indexed count is fast. Here `Page` delivers a better UI experience. Do not "ban `Page`"; choose based on UX requirements and dataset depth.

## 11. `Pageable` and `MongoTemplate`

When you need explicit control over projections, dynamic criteria, and collection operations, use `MongoTemplate`:

~~~java
import java.util.List;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

public List<Order> getOrderPage(
        MongoTemplate mongoTemplate,
        String tenantId,
        String status,
        int page,
        int size
) {
    Pageable pageable = PageRequest.of(
        page,
        size,
        Sort.by(Sort.Order.desc("createdAt"),
                Sort.Order.desc("id"))
    );

    Query query = Query.query(
        Criteria.where("tenantId").is(tenantId)
            .and("status").is(status)
    ).with(pageable);

    return mongoTemplate.find(query, Order.class);
}
~~~

`Query.with(pageable)` applies `Pageable`'s sort, skip, and limit to the MongoDB query via Spring Data APIs.

### 11.1. Why Is MongoTemplate Useful?

- Easy to compose controlled dynamic filters.
- Can configure projections via `query.fields().include(...)`.
- Easy to write an independent count query.
- Enables multi-field keyset queries cleanly.
- Gives fine-grained control where derived repository method names become unreadable.

### 11.2. Passing Pageable Across Layers

Construct `PageRequest` only after validating API inputs. Pass a trusted `Pageable` into services and repositories rather than mutating page/size/sort differently across multiple layers.

## 12. Building a `Page` Manually with MongoTemplate

When you need a `Page<Order>` from `MongoTemplate`, execute a content query and a **count query without `skip` or `limit`**:

~~~java
import java.util.List;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageImpl;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

public Page<Order> findOrderPage(
        MongoTemplate mongoTemplate,
        String tenantId,
        String status,
        int pageNumber,
        int pageSize
) {
    Pageable pageable = PageRequest.of(
        pageNumber, pageSize,
        Sort.by(Sort.Order.desc("createdAt"),
                Sort.Order.desc("id"))
    );

    Query dataQuery = Query.query(
        Criteria.where("tenantId").is(tenantId)
            .and("status").is(status)
    ).with(pageable);

    List<Order> content = mongoTemplate.find(
        dataQuery, Order.class
    );

    Query countQuery = Query.query(
        Criteria.where("tenantId").is(tenantId)
            .and("status").is(status)
    );

    long total = mongoTemplate.count(countQuery, Order.class);
    return new PageImpl<>(content, pageable, total);
}
~~~

### 12.1. Mistake: Counting Using the Paginated Data Query

Never reuse a query containing `skip`/`limit` without stripping them when computing the total:

~~~java
// Avoid blindly reusing a query with .with(pageable)
// to derive total count.
~~~

Building a separate count query with the **exact same filter and no pagination** keeps intent unambiguous and avoids depending on version-specific count method behavior.

### 12.2. Lazy Count Optimization Where Appropriate

Spring Data Commons provides `PageableExecutionUtils.getPage(...)` to defer or skip the count query whenever the total can be inferred from the content size:

~~~java
import org.springframework.data.support.PageableExecutionUtils;

Page<Order> result = PageableExecutionUtils.getPage(
    content,
    pageable,
    () -> mongoTemplate.count(countQuery, Order.class)
);
~~~

This is useful when keeping `Page` while avoiding unnecessary counts. It does not solve deep `skip` or turn offset pagination into keyset pagination.

## 13. Mapping Page to DTOs: A Note on Projections

A service might do:

~~~java
Page<Order> orders = orderRepository.findByTenantIdAndStatus(
    tenantId, "PAID", pageable
);

Page<OrderListItem> dtoPage = orders.map(order ->
    new OrderListItem(
        order.getId().toHexString(),
        order.getOrderNo(),
        order.getStatus(),
        order.getTotalMinor(),
        order.getCreatedAt()
    )
);
~~~

With DTO:

~~~java
import java.time.Instant;

public record OrderListItem(
    String id,
    String orderNo,
    String status,
    long totalMinor,
    Instant createdAt
) {}
~~~

### 13.1. `Page.map()` Does Not Automatically Reduce MongoDB Network Transfer

If the repository loaded **full `Order` documents** before mapping them to DTOs in Java, large fields like `items` or `auditTrail` have already traveled over the wire. Mapping only trims payload between service and frontend; to optimize MongoDB → backend transfer, use **database projections**.

### 13.2. Projections with MongoTemplate

~~~java
Query query = Query.query(
    Criteria.where("tenantId").is(tenantId)
        .and("status").is("PAID")
).with(pageable);

query.fields()
    .include("orderNo")
    .include("status")
    .include("totalMinor")
    .include("createdAt")
    .include("_id");

List<Order> projected = mongoTemplate.find(query, Order.class);
~~~

Properties of `Order` omitted from the projection receive default/null values during mapping. To prevent callers from mistaking a partial object for a full aggregate, design dedicated read-model DTOs or projection interfaces.

### 13.3. Never Expose Persistence Page Directly as an Immutable HTTP Contract

Serializing `PageImpl` directly produces a JSON structure coupled to framework versions and configuration. For public APIs, define an explicit response DTO containing `content`, `page`, `size`, `total`/`hasNext` tailored to your frontend contract.

## 14. Sorting Requires a Deterministic Order

Suppose three orders share the exact same `createdAt`:

~~~text
A: createdAt = 10:00:00.000
B: createdAt = 10:00:00.000
C: createdAt = 10:00:00.000
~~~

If you only specify:

~~~java
Sort.by(Sort.Order.desc("createdAt"))
~~~

then **the relative order of A/B/C is not guaranteed**: query plans, indexes, storage layout, or execution changes can reorder ties. Offset pagination with a non-unique sort can skip or duplicate records even when the dataset has not changed.

### 14.1. Add a Unique Tie-Breaker

~~~java
Sort stableSort = Sort.by(
    Sort.Order.desc("createdAt"),
    Sort.Order.desc("id")
);
~~~

Because `_id` is unique within a collection, the pair `(createdAt, _id)` establishes a total ordering (assuming consistent field types and values).

### 14.2. Sort Does Not Default to Insert Order

MongoDB makes no guarantee about "natural" document order when no sort is specified. Never build pagination on the assumption that today's query "happens to come back ordered by `_id`."

### 14.3. `ObjectId` Does Not Fully Replace `createdAt`

`ObjectId` embeds a generation timestamp, but it is not a precise, globally synchronized transaction clock proving commit order across all writers. Here `_id` serves as a **unique tie-breaker**, while the primary business sort key remains `createdAt`.

## 15. Sort Edge Cases Requiring Extra Design

| Situation | Risk | Handling Strategy |
|---|---|---|
| Tied `createdAt` | Non-deterministic order | Add `_id` tie-breaker |
| Mutable `createdAt` | Records jump across pages | Prefer immutable sort keys or snapshot strategies |
| Null/missing sort field | Ordering and keyset tokens break | Normalize schema, filter, or apply explicit policy |
| Mixed BSON types in sort field | Unexpected BSON comparison order | Enforce consistent types and validation |
| Text sorting with collation | Differs from binary order | Keep collation identical across query, index, and token |
| Sorting on array/multikey field | Complex index/plan semantics | Benchmark and consider an alternate read model |
| User selects arbitrary field | Slow queries or unauthorized field access | Whitelist allowed sort keys |

### 15.1. Sort by Creation Time or Update Time?

`updatedAt` changes constantly, reshuffling a "recently updated" list while a user flips pages. Even with a tie-breaker, pagination is not an immutable snapshot. If the UX demands stability, design an appropriate bookmark, snapshot, or anchor mechanism.

### 15.2. Ascending and Descending Directions Must Align

Index suitability depends on equality prefixes, sort field order, and index key directions. A compound index can support exact full-key-direction reversals, but not every mixed combination of directions is equivalent. Always verify with `explain` instead of relying on oversimplified rules of thumb.

## 16. How Does MongoDB Execute Offset Pagination?

In Spring Data:

~~~java
PageRequest.of(
    500, 20,
    Sort.by(Sort.Order.desc("createdAt"),
            Sort.Order.desc("id"))
)
~~~

conceptually translates to:

~~~javascript
db.orders.find({
  tenantId: "t-01",
  status: "PAID"
})
.sort({ createdAt: -1, _id: -1 })
.skip(10000)
.limit(20)
~~~

MongoDB must determine the first 10,020 elements in sort order to discard 10,000 and return 20. With a good index, the server walks index entries instead of sorting in memory, yet **it cannot jump straight to the "10,001st element" of an ordered index scan by rank like a direct key lookup**.

### 16.1. Cost Scales with Offset

For many query plans, the number of index entries traversed scales roughly as:

\[
O(\text{offset}+\text{pageSize})
\]

This is an analytical model for deep offset scans, not a strict mathematical guarantee across all optimizers, versions, or topologies. Response size remains `pageSize`, while server work increases linearly.

### 16.2. Same `pageSize`, Vastly Different Cost

~~~text
Page 0:      skip 0,       limit 20
Page 100:    skip 2000,    limit 20
Page 5000:   skip 100000,  limit 20
~~~

If `Page` also runs a filtered count across millions of matching records, total cost combines **deep `skip` + count**.

### 16.3. Indexes Help, but Do Not Eliminate the Limit

A filter-and-sort index eliminates expensive in-memory sorts and collection scans. Even so, at extreme offsets the server still walks many index positions. That is why keyset pagination excels when users paginate sequentially.

## 17. Designing a Compound Index for Filter and Sort

Common query:

~~~javascript
db.orders.find({
  tenantId: "t-01",
  status: "PAID"
})
.sort({ createdAt: -1, _id: -1 })
.limit(20)
~~~

Candidate index:

~~~javascript
db.orders.createIndex(
  {
    tenantId: 1,
    status: 1,
    createdAt: -1,
    _id: -1
  },
  { name: "idx_tenant_status_created_id" }
)
~~~

### 17.1. Rationale Behind the Index Key Order

- `tenantId` and `status` are equality predicates.
- `createdAt` and `_id` satisfy the sort.
- The index narrows down to the tenant/status range and scans already in the desired sort order.

This is a strong candidate for **that specific access pattern**, not a universal index for unrelated filters or sorts.

### 17.2. When the Filter Changes

If a query filters only on `tenantId` without `status`, this index may not support the sort as expected because `status` sits between the equality prefix and the sort keys. An "all statuses" workload may need a separate index.

### 17.3. When the UI Sorts by Total

An index on `createdAt` does not optimize `sort(totalMinor)`. If the UI supports multiple sort options, combine a sort whitelist with frequency and cost analysis rather than creating an index for every conceivable combination.

### 17.4. Indexes Carry Overhead

Every index consumes storage and RAM cache and adds overhead to inserts, updates, and deletes. Measure query frequency, execution plans, and write throughput before adding multiple compound indexes.

## 18. Indexes via Annotations and Operational Considerations

Spring Data MongoDB allows declaring indexes on entities:

~~~java
import org.springframework.data.mongodb.core.index.CompoundIndex;
import org.springframework.data.mongodb.core.mapping.Document;

@Document("orders")
@CompoundIndex(
    name = "idx_tenant_status_created_id",
    def = "{'tenantId': 1, 'status': 1, 'createdAt': -1, '_id': -1}"
)
public class Order {
    // Properties of the Order aggregate.
}
~~~

This illustrates declaring metadata on the class; do not duplicate another `Order` class in the same codebase. **Auto-index creation is not always enabled** depending on Spring Data MongoDB version and configuration. In production, manage indexes through controlled migrations and runbooks, measure build impact, and verify deployment completion.

### 18.1. MongoDB Index Names and Property Mapping

When annotating an entity with `@Id`, verify the actual index definition created in MongoDB:

~~~javascript
db.orders.getIndexes()
~~~

Never read a Java annotation and assume the index exists on the server.

### 18.2. Index Validation

Use `explain` on real queries rather than just `getIndexes`, since the optimizer can choose a different index when data statistics or query shapes change.

## 19. Using `explain("executionStats")` to Inspect Deep Page Costs

In the lab database:

~~~javascript
db.orders.find({
  tenantId: "t-01",
  status: "PAID"
})
.sort({ createdAt: -1, _id: -1 })
.skip(10000)
.limit(20)
.explain("executionStats")
~~~

Key metrics to inspect:

| Metric | Question to Ask |
|---|---|
| `nReturned` | Did it return at most 20 documents? |
| `totalKeysExamined` | Did it traverse a huge number of index entries? |
| `totalDocsExamined` | Did it FETCH many documents? |
| Winning plan | Does it show `IXSCAN`, `COLLSCAN`, `SORT`, `SKIP`, or related stages? |
| Execution time | Server execution time reported by `explain` |
| Count query explain | Does the count query have an efficient index/filter? |

### 19.1. Comparing Two Offsets

~~~javascript
// Shallow page:
db.orders.find({ tenantId: "t-01", status: "PAID" })
  .sort({ createdAt: -1, _id: -1 })
  .skip(0).limit(20)
  .explain("executionStats")

// Deep page:
db.orders.find({ tenantId: "t-01", status: "PAID" })
  .sort({ createdAt: -1, _id: -1 })
  .skip(100000).limit(20)
  .explain("executionStats")
~~~

Run both queries on a dataset large enough for deep offsets to exist; a lab with a few dozen records cannot represent production scale.

### 19.2. Explain Is Not Total API Latency

`executionStats` excludes HTTP serialization, connection pool wait times, and network latency to the browser. Measure end-to-end p95/p99 latency, CPU, memory, and command rates as well.

### 19.3. Covered Queries in MongoDB

With a projection selecting only fields present in the compound index, MongoDB can avoid `FETCH` stages under appropriate conditions. That reduces document reads, yet **deep `skip` still has to traverse many index keys**.

## 20. How New Data Causes Duplicates in Offset Pagination

Suppose results are sorted newest first, with `size = 3`:

~~~text
At T1:
List: A B C D E F G H
page 0 (skip 0): A B C
~~~

Immediately after the user views page 0, a new order `X` newer than `A` is inserted:

~~~text
At T2:
List: X A B C D E F G H
page 1 (skip 3): C D E
~~~

Record `C` appears **twice**: at the end of page 0 and at the start of page 1.

### 20.1. Why Doesn't a Tie-Breaker Fix This?

Even with a completely deterministic `(createdAt, _id)` sort, inserting `X` shifts every subsequent element's position by one. Offset measures **how many positions to skip**, not a bookmark of the last record seen.

### 20.2. What UX Can Tolerate This?

Slowly changing admin lists may tolerate an occasional duplicate row. However, if pagination drives data exports or batch processing requiring exactly-once handling, duplicates cause serious business errors.

## 21. How Deletions Cause Missing Records in Offset Pagination

Continuing from T1:

~~~text
At T1:
List: A B C D E F G H
page 0: A B C
~~~

Then `A` is deleted:

~~~text
At T2:
List: B C D E F G H
page 1 (skip 3): E F G
~~~

Record `D` shifted up to index 2 and falls inside the slice skipped by `skip(3)`. The user never sees `D` on either page 0 or page 1.

### 21.1. Updating Sort Keys Also Causes Duplicates or Skips

If `createdAt` or `updatedAt` changes and moves a document across a page boundary, offset pagination shifts consecutive positions. Keyset pagination also needs policies for mutable sort keys; no pagination mechanism automatically provides cross-request transactional snapshots over independent HTTP calls.

### 21.2. "Accurate Total Counts" Do Not Solve Drift

Counts may reflect the latest total on each request while offsets still shift as data mutates. Distinguish **total count accuracy** from **continuation consistency**.

## 22. Comparing Offset vs. Keyset/Seek Pagination

| Characteristic | Offset `skip+limit` | Keyset/Seek |
|---|---|---|
| Jump directly to page N | Easy | Hard; typically sequential continuation |
| First pages | Usually fast with an index | Fast |
| Deep pages | Cost can grow steeply | More stable with a matching index |
| Insert before boundary | Can duplicate records | Resists position shift when sort keys are immutable |
| Delete before boundary | Can skip records | No absolute rank offset, so more stable |
| Requires deterministic sort | Yes | Yes, critically important |
| Requires last sort keys | No | Yes |
| Native `totalPages` support | Can combine with count | Not directly |
| Sorting on nullable/mutable fields | Tricky | Harder; requires explicit policy/tokens |
| "Load more" APIs | Usable | Typically ideal |

### 22.1. Keyset Is Not a Silver Bullet

Keyset requires a compatible sort order and a cursor/token. It cannot jump straight to "page 50" without a prior anchor. And if a user needs a strict point-in-time report, keyset alone is not enough.

### 22.2. When Is Offset Still Appropriate?

- Small datasets or strictly bounded page depth.
- UIs requiring direct page-number jumps.
- Rarely changing data, or where occasional duplicates/skips are acceptable.
- Totals are required and counts execute efficiently.
- Benchmarks confirm `skip` at maximum allowed depth meets SLAs.

Do not replace every offset pagination endpoint with keyset simply because "offset is slow"; evaluate actual product requirements.

## 23. Keyset Queries: The "After the Last Record" Idea

Suppose the sort is:

~~~javascript
{ createdAt: -1, _id: -1 }
~~~

First page:

~~~javascript
db.orders.find({
  tenantId: "t-01",
  status: "PAID"
})
.sort({ createdAt: -1, _id: -1 })
.limit(20)
~~~

Save the key pair from the last returned document, for example:

~~~text
lastCreatedAt = 2026-11-01T10:00:00.000Z
lastId = ObjectId("64b000000000000000000123")
~~~

Next page in descending order:

~~~javascript
db.orders.find({
  tenantId: "t-01",
  status: "PAID",
  $or: [
    { createdAt: { $lt: ISODate("2026-11-01T10:00:00Z") } },
    {
      createdAt: ISODate("2026-11-01T10:00:00Z"),
      _id: { $lt: ObjectId("64b000000000000000000123") }
    }
  ]
})
.sort({ createdAt: -1, _id: -1 })
.limit(20)
~~~

### 23.1. Why Use `$or`?

With a two-field descending sort, the next record must have:

1. `createdAt` strictly less than the last timestamp; **or**
2. `createdAt` equal to the last timestamp and `_id` strictly less than `lastId`.

This is lexicographic comparison over the key tuple.

### 23.2. Why Avoid `skip`?

Instead of asking to "skip 100,000 items," the query asks to "continue after this key tuple." With a matching index, the server can seek directly to the key range instead of walking from the start. Still verify the query plan with `explain`, especially when `$or` or sharding is involved.

### 23.3. Why Save `_id` Too?

If multiple documents share the same timestamp, storing only `lastCreatedAt` with `$lt` skips remaining documents at that timestamp. The `_id` tie-breaker defines an exact boundary.

## 24. Keyset in MongoTemplate with Criteria

An implementation fetching the next page from the last sort keys:

~~~java
import java.time.Instant;
import java.util.List;
import org.bson.types.ObjectId;
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

public List<Order> findAfter(
        MongoTemplate mongoTemplate,
        String tenantId,
        String status,
        Instant lastCreatedAt,
        ObjectId lastId,
        int size
) {
    if (size < 1 || size > 100) {
        throw new IllegalArgumentException("INVALID_PAGE_SIZE");
    }

    Criteria scope = Criteria.where("tenantId").is(tenantId)
        .and("status").is(status);

    Criteria after = new Criteria().orOperator(
        Criteria.where("createdAt").lt(lastCreatedAt),
        new Criteria().andOperator(
            Criteria.where("createdAt").is(lastCreatedAt),
            Criteria.where("_id").lt(lastId)
        )
    );

    Query query = new Query(
        new Criteria().andOperator(scope, after)
    );
    query.with(Sort.by(
        Sort.Order.desc("createdAt"),
        Sort.Order.desc("id")
    ));
    query.limit(size);

    return mongoTemplate.find(query, Order.class);
}
~~~

### 24.1. Explaining the Query

`scope` is the mandatory filter. `after` defines the range following the last record. The query uses the same sort as the first page and caps results at `size`. `Criteria.where("_id")` targets MongoDB's identifier field; with entity mapping, verify the exact emitted field names in the final query.

### 24.2. Never Use Arbitrary `lastCreatedAt` or Current Time

The cursor must come from the **actual last record returned to the client** under the same filter and sort. Using "current time" as the last key can skip unseen records.

### 24.3. Limitations of This Example

This is a basic seek query; it does not yet include continuation token packaging, page metadata, user authorization, null handling, snapshot anchors, or ascending sort direction handling. Subsequent sections address those requirements.

## 25. Determining `hasNext` in Keyset via `size + 1`

For a keyset API with page size 20, query 21 documents:

~~~java
int requestedSize = 20;
query.limit(requestedSize + 1);

List<Order> fetched = mongoTemplate.find(query, Order.class);
boolean hasNext = fetched.size() > requestedSize;

List<Order> content = hasNext
    ? fetched.subList(0, requestedSize)
    : fetched;
~~~

When `hasNext=true`, build the next token from the **last record in the actually returned `content`**, not the 21st probe record that was trimmed off.

### 25.1. Why Is No Total Count Needed?

A "Load more" button only needs to know whether records exist beyond the current page. Fetching one extra record is usually far cheaper than counting the entire dataset, though actual cost depends on query, index, and page size.

### 25.2. Never Emit a Next Token When Content Is Empty

When zero records are returned, never call `content.get(content.size() - 1)`. Check for empty results and return `hasNext=false`.

### 25.3. First-Page Query Without a Token

When no last key is provided, run the query with only filter, sort, and `limit(size + 1)`, then generate the next token if `hasNext` is true. Never invent a synthetic `"lastId=0"` placeholder, as BSON types and sort rules may not behave as expected.

## 26. Secure Continuation Tokens

A continuation token might logically hold:

~~~json
{
  "v": 1,
  "sort": "createdAt_DESC_id_DESC",
  "createdAt": "2026-11-01T10:00:00.000Z",
  "lastId": "64b000000000000000000123",
  "tenant": "t-01",
  "filterHash": "hash-of-authorized-query",
  "expiresAt": "2026-11-01T11:00:00.000Z"
}
~~~

This example shows the **logical payload**, not a production token format. In an API, serialize it as an opaque Base64url string protected with an **HMAC signature or appropriate integrity/authentication mechanism**, backed by a key rotation policy.

### 26.1. Never Trust Tokens as Free-Form Client Input

Without protection, clients can tamper with timestamps, tenant IDs, filters, and sort orders. The server must:

- Verify the signature, token version, and expiration.
- Verify the token belongs to the current authenticated principal/tenant.
- Verify sort and filters match the authorized request.
- Validate `ObjectId`, timestamp, and data types.
- Enforce page size limits independently of the token.

### 26.2. Tokens Are Not Credentials

Never embed passwords, MongoDB URIs, or unnecessary PII inside a cursor. Base64url **does not encrypt payloads**; anyone can decode it. If a cursor must hold sensitive data, encrypt it in addition to signing, or store state server-side.

### 26.3. Timestamp Precision

MongoDB BSON Date has millisecond resolution. When serializing `Instant` into a token, round-trip the exact stored precision—such as ISO UTC with milliseconds. Truncating timestamps to whole seconds breaks seek boundaries when multiple records fall within the same second.

### 26.4. Filters Cannot Silently Change Mid-Pagination

If page 1 filtered `status=PAID` and page 2 changes to `PENDING` while reusing the old cursor, the boundary no longer belongs to the same dataset. Bind tokens to a filter hash/policy so mismatched requests are rejected or restarted cleanly.

## 27. Spring Data Scroll API: `Window` and `ScrollPosition`

In Spring Data versions supporting repository scrolling, the framework provides `Window<T>` and `ScrollPosition` to iterate results window by window. There are two modes:

- **Offset scrolling:** tracks a numeric offset, retaining `skip`/`offset` limitations.
- **Keyset scrolling:** tracks the sort field values of the last element to query the next range by key.

Conceptually:

~~~java
// Dependent on Spring Data MongoDB / Spring Data Commons version:
// Window<Order> first = repository
//     .findFirst20ByTenantIdAndStatusOrderByCreatedAtDescIdDesc(
//         tenantId, status, ScrollPosition.keyset()
//     );
//
// ScrollPosition next = first.positionAt(first.size() - 1);
// Window<Order> second = repository
//     .findFirst20ByTenantIdAndStatusOrderByCreatedAtDescIdDesc(
//         tenantId, status, next
//     );
~~~

This is **conceptual pseudocode**, not a guarantee that the exact method signature or derivation works across every release. Check the Spring Data MongoDB documentation and Javadoc for `Window`/`ScrollPosition` in your target version before adopting it.

### 27.1. Do Not Confuse `ScrollPosition.offset()` with Keyset

An abstraction named "scroll" does not automatically avoid `skip`. Always verify which `ScrollPosition` variant you are using.

### 27.2. Keyset Scrolling Requires Sort Fields in Results

Every field needed to construct the scroll position must be present in the returned projection and hold comparable values. If a projection strips `createdAt` or `id` before the framework builds the keyset position, scrolling will break.

### 27.3. MongoDB Server Cursors Are Not REST Cursors

A MongoDB server cursor (`getMore`) streams **a single query result** in network batches. A REST continuation token/keyset initiates **independent page queries** across stateless HTTP calls. They are completely different mechanisms—never expose raw MongoDB `cursorId` values to frontend clients.

## 28. Where Keyset Beats Offset—and Where It Still Falls Short

### 28.1. Resilience to Inserts/Deletes Before the Boundary

If a user has read up to `C` and a new record `X` is inserted ahead of `A`, requesting "after `C`" still locates `D/E/F` by key comparison rather than hitting a shifted `skip(3)`.

### 28.2. Mutable Sort Keys

If an older document's `createdAt` is edited or you sort by `updatedAt`, records can jump across boundaries; even keyset pagination can duplicate or skip items when **the positioning keys themselves mutate**. Prefer immutable sort keys, snapshots/anchors, or explicit eventual-feed semantics.

### 28.3. No Direct Jump to Page N

A cursor token only knows how to resume after the previous page's last key. You cannot jump straight to "page 1000" by multiplication unless you maintain precomputed page anchors.

### 28.4. Multi-Column Dynamic Sorts

A UI letting users sort by `status`, `totalMinor`, `createdAt`, and customer name requires matching token formats, null/collation policies, and indexes for each sort. Do not expose arbitrary dynamic sorts via keyset without explicit design.

## 29. Paginating User-Selected Dynamic Sorts

Suppose an API accepts:

~~~text
GET /api/orders?sort=createdAt,desc&size=20
~~~

Never accept an arbitrary user-supplied field path and pass it straight to `Sort.by(rawInput)`. Sorting on large arrays or unindexed fields enables expensive queries.

### 29.1. Enforce a Whitelist

~~~java
import java.util.Set;
import org.springframework.data.domain.Sort;

public Sort safeSort(String requestedField, String direction) {
    Set<String> allowed = Set.of(
        "createdAt", "totalMinor", "status"
    );

    if (!allowed.contains(requestedField)) {
        throw new IllegalArgumentException("UNSUPPORTED_SORT_FIELD");
    }

    Sort.Direction dir = "asc".equalsIgnoreCase(direction)
        ? Sort.Direction.ASC
        : Sort.Direction.DESC;

    return Sort.by(
        new Sort.Order(dir, requestedField),
        new Sort.Order(dir, "id")
    );
}
~~~

Here the `id` tie-breaker shares the primary sort's direction to maintain deterministic ordering. When implementing keyset pagination across mixed sort directions or multiple fields, construct comparison operators matching each direction—never reuse `$lt` blindly for ascending sorts.

### 29.2. Indexes per Sort Option

Sorting by `createdAt desc` and `totalMinor asc` follow different access patterns. Add indexes for frequently used sorts; for rare sorts, tighten filters/page limits or restrict them to small datasets.

### 29.3. Collation and Text Sorting

Sorting by customer name may require locale-specific collation (case, diacritics). Query, index, and cursor token comparisons must share the exact same collation. Never evaluate a token using binary string comparison and apply it to a locale-collated query.

## 30. Missing and Null Sort Keys

Simple keyset queries assume `createdAt` is non-null and consistently typed. If some documents lack the field:

- MongoDB applies BSON type ordering and query rules for null/missing values.
- Predicates like `createdAt < lastCreatedAt` may handle nulls differently than business logic expects.
- Tokens missing required key values cannot anchor the next page cleanly.

### 30.1. Standardize the Schema

For critical lists, require `createdAt` to be non-null and set once at creation. Enforce this via application validation, MongoDB `$jsonSchema` collection validators, and legacy data backfills.

### 30.2. When Sorting on Nullable Fields Is Unavoidable

Design a **normalized sort key** (e.g., a non-null fallback value) or explicit branching for null values. Verify behavior with tests and `explain` rather than assuming a single inequality handles every BSON type.

### 30.3. Timestamps and Timezones

Store timestamps consistently (typically UTC BSON Date) and format for local timezones in the UI. Never sort on unnormalized local-time strings.

## 31. Read Concern and Cross-Page Consistency

### 31.1. Majority Does Not Turn Separate HTTP Requests into a Shared Snapshot

`ReadConcern.MAJORITY` (when supported by the deployment) guarantees reading majority-committed data, yet page 0 and page 1 requested at different times can still observe different committed states.

### 31.2. Snapshot Reads / Transactions When Required

If business requirements demand exporting a **point-in-time consistent** dataset:

- Use a transaction with snapshot semantics or server/driver-supported snapshot reads.
- Account for transaction lifetime limits, WiredTiger cache pressure, and MongoDB operational constraints.
- Never keep an interactive transaction open for tens of minutes while a user clicks through pages without thorough operational evaluation.

### 31.3. Export Strategies

For large reports, consider a background **export job** using an explicit snapshot/anchor that writes to file/object storage instead of making the frontend click through thousands of offset pages. When only aggregates are needed, run server-side aggregation rather than paging records into Java to sum them.

### 31.4. Page Content and Count Are Separate Operations

Even within `Page<T>`, content and count are not guaranteed to be an atomic read at the exact same cluster timestamp. UIs displaying totals should tolerate slight drift or use an explicit consistency mechanism.

## 32. Multi-Tenant Pagination and Security

Common bugs arise when paginating without locking down tenant scope:

~~~java
// Anti-pattern in a multi-tenant API:
Page<Order> page = orderRepository.findAll(pageable);
~~~

Because the service account has broad read access, this exposes orders across all tenants. The safe query is:

~~~java
Page<Order> page = orderRepository.findByTenantIdAndStatus(
    authenticatedTenantId,
    "PAID",
    pageable
);
~~~

### 32.1. Never Trust `tenantId` Inside a Cursor Token

A token may carry `tenant` for continuity verification, yet the server must still validate tenant identity **against the authentication context**. Never authorize access based solely on a client-supplied token payload.

### 32.2. Pagination Alone Is Not a Resource Limit

A client can still scrape thousands of pages sequentially. Pair pagination with authorization, rate limiting, quotas, max page/size caps, and observability.

### 32.3. Filter Invariant

If page 1 filters `status=PAID` and page 2 changes filters while reusing the same offset or cursor, results no longer come from the same logical set. Keep filters immutable within a pagination session or reset pagination whenever filters change.

## 33. Counting Overhead and UI Metadata

On a 10-million-record feed, the frontend can show:

~~~text
First 20 results
"Load more" button
~~~

instead of:

~~~text
20 of 10,234,987 results
Page 1 / 511,750
~~~

When total counts do not drive any user decision, `Slice` or count-free keyset APIs cut database load significantly.

### 33.1. When Totals Are Still Needed

Consider:

- Filtered counts backed by a tight index.
- Caching counts with a TTL while marking them as approximate/delayed.
- Precomputed counters maintained per business rules.
- Computing totals asynchronously rather than on every page flip.

If using cached or estimated counts, **never present them as exact real-time totals** unless guaranteed.

### 33.2. Counts Are Not Always Slow

On small collections or highly selective filters, filtered counts run quickly. Do not re-architect away from `Page` if benchmarks prove it comfortably meets your SLAs.

## 34. Deep Offsets in a Sharded Cluster

In sharded MongoDB deployments, a `sort/skip/limit` query routes through `mongos` to one or more shards depending on shard key and filter. Check:

- Does the filter include enough of the shard key to target a small subset of shards?
- Does each shard perform substantial work before `mongos` merges and re-sorts results?
- Do shard indexes support both filter and sort?
- How severely do large offsets inflate intermediate data read, transferred, and merged?

### 34.1. Tenant Filters Can Aid Shard Targeting

When sharding aligns with tenant, filtering on `tenantId` can target specific shards. Never assume every sharded cluster targets a single shard automatically just because `tenantId` is in the filter—that depends on the shard key and chunk distribution.

### 34.2. Keyset Still Needs Proper Routing

Keyset avoids deep `skip`, yet a scatter-gather query with a poor sort across shards remains expensive. Align shard keys, indexes, and query shapes together.

### 34.3. Inspecting `explain` via `mongos`

Review both the overall cluster plan and individual shard plans (per tool/server version). Never check `explain` on a single shard and assume `mongos` queries are optimal.

## 35. REST API Contract for Offset Pagination

Responses should be self-describing:

~~~json
{
  "items": [
    {
      "id": "64b000000000000000000123",
      "orderNo": "O-1001",
      "status": "PAID",
      "totalMinor": 120000,
      "createdAt": "2026-11-01T10:00:00Z"
    }
  ],
  "page": 0,
  "size": 20,
  "numberOfElements": 1,
  "totalElements": 53,
  "totalPages": 3,
  "hasNext": true,
  "sort": "createdAt,desc;id,desc"
}
~~~

This is an **illustrative response**, not output from a live database. In real systems, `hasNext` and totals must stay consistent with actual request results (for example, page 0 having 1 item while total is 53 would only happen under unusual constraints, so do not copy these sample numbers into test assertions). Normally a first page returns a full `size` items when enough matching records exist.

### 35.1. Input Validation

~~~java
public PageRequest validatedPageRequest(int page, int size) {
    if (page < 0) {
        throw new IllegalArgumentException("PAGE_MUST_BE_NONNEGATIVE");
    }
    if (size < 1 || size > 100) {
        throw new IllegalArgumentException("INVALID_PAGE_SIZE");
    }
    if (page > 1000) {
        throw new IllegalArgumentException("PAGE_TOO_DEEP_USE_CURSOR");
    }

    return PageRequest.of(
        page,
        size,
        Sort.by(Sort.Order.desc("createdAt"),
                Sort.Order.desc("id"))
    );
}
~~~

`100` and `1000` are **illustrative API limits**, not MongoDB defaults. Tune them to your UX, dataset size, indexes, SLAs, and security policies.

### 35.2. Never Allow `Pageable.unpaged()` from Raw Input

Allowing clients to disable pagination lets a single request dump an entire collection. Reserve unpaged access for controlled internal jobs with explicit streaming and quotas.

### 35.3. Page Too Deep

When users need to browse deeper into large lists, return a clear error directing the client to cursor-based pagination instead of executing huge `skip` queries. Define both the error response and migration contract clearly for the frontend.

## 36. REST API Contract for Keyset Pagination

~~~text
GET /api/orders?size=20
GET /api/orders?size=20&after=<opaque-signed-token>
~~~

Example response:

~~~json
{
  "items": [
    {
      "id": "64b000000000000000000123",
      "orderNo": "O-1001",
      "createdAt": "2026-11-01T10:00:00Z"
    }
  ],
  "hasNext": true,
  "nextCursor": "opaque-signed-token",
  "sort": "createdAt,desc;id,desc"
}
~~~

`totalPages` is omitted because no count runs. The token is opaque to the frontend; the server validates signature, filter/tenant/sort bindings, and expiration.

### 36.1. Changing Sort Order

If the user switches from newest-first to total-descending, the old cursor token is invalid. Start a fresh pagination session rather than trying to interpret old keys under a new sort order.

### 36.2. Previous Page

Navigating backward with keyset requires inverting the comparison and sort direction (and reversing the returned slice) or caching prior cursor tokens on the frontend. Never try to use `skip(-20)`.

### 36.3. Tokens Do Not Replace Authorization

A cursor token does not replace access control. The service must still verify read permissions on every request.

## 37. Keyset Pagination on Mutable Ordered Datasets

In a "newest first" feed receiving continuous new inserts, keyset holds its position cleanly as the user scrolls **toward older records**. Still, edge cases remain:

1. An older record's `createdAt` is updated to be newer than the boundary: it can disappear from the user's remaining traversal.
2. An already-viewed record's timestamp is shifted older: the user may encounter it again.
3. A record is deleted: it simply vanishes; unlike offset, deleting earlier items does not shift subsequent positions.
4. A filtered field like `status` changes: records can enter or leave the result set mid-pagination.

### 37.1. Time Anchors

You can bound a query with an upper cutoff:

~~~javascript
{
  tenantId: "t-01",
  status: "PAID",
  createdAt: { $lte: ISODate("2026-11-14T08:00:00Z") }
}
~~~

An upper cutoff prevents **records with newer `createdAt` timestamps** from entering the feed, though it does not create an ACID snapshot: deletions, status updates, or edits to older `createdAt` values can still affect results. Never label a timestamp anchor a consistent snapshot without backing snapshot mechanisms.

### 37.2. Immutable Sort Keys

Whenever possible, sort on a field set once at creation and never modified. If the UI must sort by `updatedAt`, document "dynamic feed" semantics clearly and never promise zero duplicates or skips across widely separated HTTP calls.

## 38. mongosh Lab: Generating Data with Tied Timestamps

Run only on a lab MongoDB instance:

~~~javascript
use paging_lab

db.orders.createIndex(
  { tenantId: 1, status: 1, createdAt: -1, _id: -1 },
  { name: "idx_tenant_status_created_id" }
)

const base = ISODate("2026-11-01T00:00:00Z").getTime()

const docs = Array.from({ length: 120 }, (_, i) => ({
  tenantId: i % 10 === 0 ? "t-02" : "t-01",
  orderNo: "O-" + (1000 + i),
  status: i % 4 === 0 ? "PENDING" : "PAID",
  totalMinor: 10000 + i * 100,
  createdAt: new Date(base + Math.floor(i / 3) * 1000)
}))

db.orders.insertMany(docs)
~~~

This intentionally gives every group of three documents the same timestamp so you can observe tie-breaking. `_id` is auto-generated when omitted. Re-running inserts another 120 records, so avoid benchmarking the same lab collection after multiple runs without resetting it.

### 38.1. Reading the First Page

~~~javascript
db.orders.find(
  { tenantId: "t-01", status: "PAID" },
  { orderNo: 1, status: 1, createdAt: 1 }
).sort({ createdAt: -1, _id: -1 })
 .skip(0).limit(10)
~~~

### 38.2. Reading the Third Page

~~~javascript
db.orders.find(
  { tenantId: "t-01", status: "PAID" },
  { orderNo: 1, status: 1, createdAt: 1 }
).sort({ createdAt: -1, _id: -1 })
 .skip(20).limit(10)
~~~

### 38.3. Measuring with `explain`

~~~javascript
db.orders.find({
  tenantId: "t-01",
  status: "PAID"
})
.sort({ createdAt: -1, _id: -1 })
.skip(20).limit(10)
.explain("executionStats")
~~~

A 120-record lab illustrates the mechanics; it does not reflect latency at millions of records.

## 39. Testing Ordering Logic with Tied Timestamps

In the lab, multiple orders share the same `createdAt`. Compare:

~~~javascript
// Without tie-breaker:
db.orders.find({ tenantId: "t-01" })
  .sort({ createdAt: -1 })
  .limit(10)

// With tie-breaker:
db.orders.find({ tenantId: "t-01" })
  .sort({ createdAt: -1, _id: -1 })
  .limit(10)
~~~

Lab outputs may happen to match on a small collection; that **does not prove** sorting solely by `createdAt` is stable. Rely on deterministic query semantics rather than single-run observation.

### 39.1. Why Not Sort Arbitrarily by `orderNo`?

If `orderNo` is not unique—or changes format or string padding—it is unreliable as a tie-breaker. `_id` is unique and immutable within a collection, making it the standard choice.

## 40. Testing Data Mutations Between Pages

A simulation exercise:

1. Query page 0, size 3, and record the `_id` values.
2. Insert a document with a `createdAt` newer than all existing documents.
3. Query page 1 using `skip(3)`.
4. Compare `_id` values across both pages and spot the duplicate record.
5. Repeat by deleting a record ahead of the offset in an **isolated lab**.
6. Run the keyset query "after `(lastCreatedAt, lastId)`" to compare.

Never inject test inserts or deletes to experiment with pagination in production. In test environments, verify dataset counts before and after and clean up per lab procedures.

### 40.1. Key Takeaway

A sort tie-breaker establishes deterministic order **within a single query**, but cannot freeze positions when the result set changes between requests. Keyset pagination anchors on the last-seen keys instead of skipping positions.

## 41. Benchmarking Page, Slice, and Keyset

Design three variants sharing the exact same filter and index:

| Variant | Returned Content | Count | Pagination |
|---|---|---|---|
| A: `Page` | 20 records | May execute count | Offset |
| B: `Slice` | 20 records + `hasNext` | No total count | Offset |
| C: Keyset | 20 records + next token | No total count | Seek by sort keys |

Run at offsets equivalent to pages 0, 50, 1,000, and 10,000 on a representative dataset under realistic concurrency. For keyset, obtain actual cursor keys from sequential reads—**a benchmark is unfair if you fabricate a random key without reflecting how it is obtained**.

### 41.1. Metrics to Collect

- Backend p50/p95/p99 latency.
- MongoDB query execution time and count time.
- `totalKeysExamined` and `totalDocsExamined`.
- Command counts and cursor batches.
- MongoDB CPU, memory, disk I/O, and WiredTiger cache activity.
- Network bytes transferred and HTTP response payload size.
- Error/timeout rates at peak concurrency.
- Result correctness: record counts, tie-breaking, and tenant scoping.

### 41.2. Warm vs. Cold Benchmarks

Caches, connection pools, TLS handshakes, and JVM JIT warm-up affect numbers. Run multiple iterations, separate cold from warm runs, and keep dataset and query shapes identical before drawing conclusions.

### 41.3. Count Is a Separate Cost

If `Page` is slower than `Slice`, verify whether the overhead comes from the count query or the page query; never blame `skip` when total count is the actual bottleneck.

## 42. Anti-Patterns to Avoid

| Anti-Pattern | Consequence | Alternative |
|---|---|---|
| `findAll()` then `subList` in Java | Loads entire collection, OOM | `Pageable` / MongoDB query |
| No sort specified | Non-deterministic order | Deterministic sort |
| Sorting only by `createdAt` when ties exist | Duplicates/skips during paging | Add `id` tie-breaker |
| `PageRequest.of(page, size)` for extreme pages | Growing server scan work | Cap max page or use keyset |
| Using `Page` when UI only needs `hasNext` | Unnecessary count queries | `Slice` or keyset |
| Assuming `Slice` avoids `skip` | Deep offsets still scan | Keyset when needed |
| Reusing paginated query for count | Wrong/confusing totals | Separate count query with same filter, no skip/limit |
| Mapping entity to DTO after full load | MongoDB still sends large fields | Database projections |
| Accepting raw sort field from client | Slow queries / unauthorized field access | Whitelist sort fields |
| Omitting tenant filter and filtering in Java | Leaks/transfers other tenants' data | Filter by authenticated tenant in DB query |
| Missing filter/sort index | `COLLSCAN` or blocking `SORT` | Compound index matching access pattern |
| Indexing every conceivable sort combination | Write/storage overhead | Index only validated workloads |
| Treating `ObjectId` as exact commit clock | Broken ordering assumptions | Business timestamp + unique tie-breaker |
| Cursor lacking sort/filter binding | Wrong continuation / data leak | Signed token + validation |
| Treating Base64 as encryption | Token readable and forgeable | Integrity signature and policy |
| Promising stability with mutable keyset keys | Duplicates/skips still occur | Immutable keys / snapshot semantics |
| Treating `ReadConcern.MAJORITY` as cross-request snapshot | Misunderstood consistency | Explicit snapshot read design |
| Using collection-wide count instead of filtered count | Wrong `totalPages` | Filtered count |
| Testing 100 docs and claiming deep `skip` is fast | Unrepresentative benchmark | Realistic dataset and timing |

## 43. Practice Exercise A — 0-Based PageRequest

Given page size 25, compute the offsets for `PageRequest.of(0, 25)`, `PageRequest.of(3, 25)`, and `PageRequest.of(40, 25)`. Write the equivalent MongoDB query with sort `{ createdAt: -1, _id: -1 }`.

## 44. Practice Exercise B — Repository Page and Slice

Create `MongoRepository<Order, ObjectId>` with one method returning `Page<Order>` and one returning `Slice<Order>`, filtering by `tenantId` and `status`. Describe when a UI needs `totalPages` vs. only "Load more."

## 45. Practice Exercise C — MongoTemplate and Count

Write a `MongoTemplate.find` using `PageRequest.of(2, 20, stableSort)`. Write the count query **without `skip`/`limit`**. Explain why total matching documents must be counted across the full filter rather than just page 2's content.

## 46. Practice Exercise D — Sort Tie-Breaker

Three documents share the same `createdAt` but have different `_id` values. Why is sorting solely by `createdAt` insufficient? When adding `_id` to the sort, which problem is solved and which problem **still remains unsolved**?

## 47. Practice Exercise E — Index and Explain

Given filter `{ tenantId: "t-01", status: "PAID" }` and sort `{ createdAt: -1, _id: -1 }`, propose a compound index. If `explain` for page 5000 shows huge `totalKeysExamined` despite `nReturned = 20`, explain why.

## 48. Practice Exercise F — Inserts Causing Duplicates

Initially `A B C D E F` (newest first), size 3; the user has viewed `A B C`. After `X` is inserted at the front, what does offset page 1 return? Propose a keyset boundary that avoids duplicates.

## 49. Practice Exercise G — Deletes Causing Missing Records

Initially `A B C D E F`; the user has viewed page 0 (`A B C`). `A` is deleted before requesting page 1. What does `skip(3)` return? Which record is skipped?

## 50. Practice Exercise H — Keyset Query

With descending sort `createdAt, -_id`, the last key is timestamp `T` and `ObjectId` `I`. Write the condition `createdAt < T OR (createdAt = T AND _id < I)`. Explain why both fields are required.

## 51. Practice Exercise I — Continuation Token

Design a token containing version, timestamp, last `ObjectId`, filter hash, tenant, sort, and expiration. Which fields must be validated against the authentication context? Why is Base64 insufficient against tampering?

## 52. Practice Exercise J — Dynamic Sorting

An API supports newest-first, oldest-first, and total-descending. Define a sort key/direction whitelist and candidate indexes. Explain when a keyset comparator uses `$gt` instead of `$lt`.

## 53. Practice Exercise K — Mutable Data

A feed sorts by `updatedAt`, and a record is updated immediately after the user reads page 0. Why can both offset and keyset shift results? When is a snapshot/export job required instead of a live feed?

## 54. Practice Exercise L — Multi-Tenant and Sharding

A sharded collection holds data for thousands of tenants. An API forgets to filter `tenantId` while keeping `limit(20)`. Identify both the security bug and the routing/network impact. Once `tenantId` is filtered, what enables efficient shard targeting?

## 55. Practice Exercise M — Projections and DTOs

The `Order` entity has massive `items` and `auditTrail` fields. A service calls repository `Page<Order>` and then `Page.map(...)` to build summaries. Does this reduce BSON bytes transferred from MongoDB to Java? Propose a query-level projection.

## 56. Practice Exercise N — Choosing the API Design

Three screens:

1. A 300-product catalog where users want to jump to "page 7/15."
2. An activity feed with millions of events and only a "Load more" button.
3. An audit export requiring a consistent point-in-time snapshot.

Choose `Page`/offset, `Slice`/keyset, or a snapshot/export job for each, and explain the trade-offs.

## 57. Practice Answer Hints

**A:** Offsets are `0`, `75`, and `1000` respectively; MongoDB runs `skip(offset).limit(25)` after a deterministic sort.

**B:** `Page<Order> findByTenantIdAndStatus(..., Pageable)` serves `totalPages`; `Slice<Order> readByTenantIdAndStatus(..., Pageable)` serves `hasNext`. `Slice` does not eliminate deep offsets.

**C:** The content query uses `Query.with(pageable)`. The separate count query uses the exact tenant/status criteria without `skip`/`limit`; total counts all matching records.

**D:** Adding `_id` as a tie-breaker produces deterministic order within each query; it still does not prevent concurrent inserts/deletes from shifting offsets between requests.

**E:** `{ tenantId: 1, status: 1, createdAt: -1, _id: -1 }` is the candidate index. Deep `skip` still scans many preceding index keys before returning the requested page.

**F:** After inserting `X`, the list is `X A B C D E F`, so page 1 with `skip(3)` returns `C D E`—duplicating `C`. Keyset "after `C`" returns `D E F` when keys are immutable.

**G:** After deleting `A`, the list is `B C D E F`, so page 1 with `skip(3)` returns `E F`—skipping `D`.

**H:** `$or` combines `createdAt < T` or (`createdAt == T` and `_id < I`); `_id` is needed because timestamps can tie.

**I:** The server verifies signature, expiration, tenant, filter/sort bindings, and typed keys; Base64 only encodes and provides zero integrity protection.

**J:** Whitelist allowed fields and directions with a unique tie-breaker. Ascending sorts generally use `$gt` for "after," combining multi-field conditions in strict key order.

**K:** Mutable `updatedAt` can move records across boundaries even under keyset. When strict snapshot consistency is needed, use a supported export/snapshot strategy.

**L:** Omitting the tenant filter leaks data and forces scatter-gather; always derive the filter from the authenticated principal. Efficient shard targeting occurs when the filter aligns with the shard key and routing rules.

**M:** `Page.map` executes after loading full entities and does not cut MongoDB wire bytes. Use `query.fields()` or a repository projection.

**N:** Small catalog with page jumping: `Page`/offset is appropriate. Huge feed: keyset/scrolling with `hasNext` and no total count. Audit export: controlled snapshot/export pipeline for consistency.

## 58. Review Questions

**1. What does `PageRequest.of(0, 20)` mean?** — First page (0-based), up to 20 records.

**2. What is the offset for page 5 with size 20?** — `100`.

**3. What extra metadata does `Page<T>` return beyond content?** — Total elements/pages and navigation metadata.

**4. When should you use `Slice<T>`?** — When you only need content and `hasNext`, without a total count.

**5. Does `Slice` eliminate deep `skip`?** — No, not when backed by an offset `PageRequest`.

**6. Why can `Page` be slower than `Slice`?** — It may execute an extra filtered count query.

**7. Are `countDocuments` and `estimatedDocumentCount` interchangeable?** — No; a collection-wide estimate cannot replace an accurate filtered count.

**8. What does `MongoTemplate` `Query.with(pageable)` do?** — Applies `Pageable`'s sort, skip, and limit to the `Query`.

**9. Should a count query reuse the content query's `skip` and `limit`?** — No, if you need the total matching records.

**10. Why must you sort before paginating?** — To establish a well-defined ordering.

**11. Is sorting solely by `createdAt` always deterministic?** — No, whenever multiple records share the same timestamp.

**12. Why append `_id`?** — To provide a unique tie-breaker and keyset boundary.

**13. Does `ObjectId` prove exact commit ordering?** — No.

**14. Can deep `skip` still be slow even with an index?** — Yes, because MongoDB must still walk through all preceding entries.

**15. Suggested compound index for tenant/status + time sort?** — `{ tenantId: 1, status: 1, createdAt: -1, _id: -1 }`.

**16. Does an index eliminate all `skip` cost?** — No.

**17. What does `explain("executionStats")` reveal?** — Keys/docs examined, winning plan, `nReturned`, and server execution stats.

**18. What does inserting before a page boundary cause in offset pagination?** — Offset pagination can duplicate documents.

**19. What does deleting before a page boundary cause in offset pagination?** — Offset pagination can skip documents.

**20. Does a tie-breaker fix insert/delete drift?** — No.

**21. What does keyset pagination rely on?** — The sort key values of the last returned record, rather than rank offset.

**22. Can keyset jump straight to page 500?** — Not naturally; it requires sequential continuation or precomputed anchors.

**23. Is `ScrollPosition.offset()` keyset pagination?** — No, it represents offset scrolling.

**24. Does keyset benefit from immutable sort keys?** — Yes; mutable sort keys can still cause duplicates or skips across pages.

**25. Does a Base64 token prevent tampering?** — No; you need cryptographic signatures and an integrity policy.

**26. Does a cursor token replace authorization?** — No; every request must still verify access permissions.

**27. Why reject raw client sort fields?** — They enable slow unindexed sorts or unauthorized field access.

**28. Does `Page.map` create a database projection?** — No.

**29. Does `ReadConcern.MAJORITY` create a snapshot across two HTTP requests?** — No.

**30. Should you hold a long transaction open while a user clicks through pages?** — Not by default; evaluate transaction limits and resource overhead.

**31. Does sharding make deep `skip` free?** — No; it can add scatter-gather routing and merge overhead.

**32. Why should APIs cap `maxPage` and `maxSize`?** — To block oversized/deep queries and protect server resources.

**33. Why measure p95/p99 instead of averages alone?** — Deep pages and concurrent writes drive tail latency spikes.

**34. When is offset still fine?** — Small datasets, shallow depth, page-number jumping, and verified SLAs.

**35. When should you consider keyset?** — Large feeds/lists, sequential loading, and avoiding deep `skip` costs.

## 59. Quick Reference Table

| Purpose | API / Concept |
|---|---|
| Create page request | `PageRequest.of(page, size, sort)` |
| Multi-field sort | `Sort.by(Order.desc("createdAt"), Order.desc("id"))` |
| Repository `Page` | `Page<T> findBy...(filters, Pageable)` |
| Repository `Slice` | `Slice<T> readBy...(filters, Pageable)` |
| Get content | `page.getContent()` |
| Total elements/pages | `page.getTotalElements()` / `getTotalPages()` |
| Check next page | `slice.hasNext()` |
| `MongoTemplate` | `Query.query(criteria).with(pageable)` |
| Total filtered records | `mongoTemplate.count(countQuery, Order.class)` |
| Avoid unneeded counts | `Slice` or keyset |
| Offset query | `sort + skip + limit` |
| Stable sort | `createdAt DESC, _id DESC` |
| Candidate index | `tenantId, status, createdAt DESC, _id DESC` |
| Query plan | `explain("executionStats")` |
| Avoid deep `skip` | Switch to keyset/seek where appropriate |
| Keyset boundary | `createdAt < T OR (createdAt = T AND _id < I)` |
| Keyset API | `nextCursor` with integrity validation |
| Spring Data scrolling | `Window` / `ScrollPosition` in supporting versions |
| Projection | `Query.fields().include(...)` |
| Security | Filter by authenticated tenant + whitelist sort |
| Stable export | Snapshot/export job instead of live offset |

## 60. Production Pre-Deployment Checklist

- [ ] Is 0-based vs. 1-based page indexing aligned cleanly between frontend and backend?
- [ ] Are maximum `pageSize` and maximum `pageNumber` enforced?
- [ ] Do repository/`MongoTemplate` queries filter by verified tenant and permissions?
- [ ] Is an explicit sort always specified instead of relying on natural order?
- [ ] Does every sort include a unique tie-breaker such as `_id`?
- [ ] Do sort fields have consistent types and matching indexes?
- [ ] Have you inspected `explain` at representative offsets, including the deepest allowed page?
- [ ] Have you measured `totalKeysExamined` and `totalDocsExamined`?
- [ ] Have you separated count query cost from page query cost?
- [ ] Does the UI genuinely need `totalElements`/`totalPages`, or is `hasNext` sufficient?
- [ ] If using `Slice`, is everyone aware that offset/`skip` still applies?
- [ ] If using keyset, does the token include all sort keys, filter/sort bindings, and validation?
- [ ] Is the token signed, tenant-checked, expiring, and free of secrets?
- [ ] Does changing sort or filter reset pagination cleanly?
- [ ] Does keyset handle timestamp precision, `ObjectId`, nulls, and collations accurately?
- [ ] Are sort keys mutable, and does the UX accept dynamic-feed semantics?
- [ ] Is there a dedicated snapshot/export strategy for audit or reporting needs?
- [ ] Are raw user inputs blocked from specifying arbitrary sort fields or namespaces?
- [ ] On sharded clusters, do filters align with shard keys and routing policies?
- [ ] Have database projections reduced wire payloads instead of relying solely on `Page.map`?
- [ ] Is the API response DTO decoupled from internal `PageImpl` JSON serialization?
- [ ] Do tests cover tied timestamps, mid-pagination inserts/deletes, and the final page?
- [ ] Have you benchmarked realistic data volumes, p95/p99 latency, and peak concurrency?
- [ ] Is monitoring active for deep page requests, slow counts, and timeouts?
- [ ] Can the pagination/API design be rolled back safely if a deployment regresses?

## 61. Conclusion

Spring Data MongoDB makes pagination convenient with **`Pageable`, `PageRequest`, `Sort`, `Page`, and `Slice`**. For moderate datasets and UIs needing direct page jumps, offset pagination is clear and easy to implement—provided you use **stable filters and sorts**, back them with proper indexes, and avoid loading unneeded full documents.

The core limitation of offset pagination is that MongoDB must still walk preceding results: `skip(100000)` remains expensive even when returning only 20 documents. Moreover, inserts or deletions ahead of the boundary cause **duplicate or skipped records** across requests. `Slice` avoids total counts, but does not remove these limits while offsets are used.

For large lists, sequential loading, and predictable deep-page latency, **keyset/seek pagination** over keys like `createdAt` and `_id` is usually the stronger choice. Even so, keyset does not create point-in-time snapshots and requires stable sort keys, matching indexes, signed tokens, and clear API contracts. Choose among **`Page`/offset, `Slice`, or keyset/scrolling** based on UX, dataset scale, correctness, consistency, and benchmarks—not merely brevity of code.
