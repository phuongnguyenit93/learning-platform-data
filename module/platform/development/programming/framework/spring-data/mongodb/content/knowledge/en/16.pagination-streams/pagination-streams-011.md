# Reactive Pagination with Flux and Separate Counts When Needed

## 1. Why is reactive pagination not just swapping List for Flux?

In a Spring Data MongoDB application, an API might need to list tens of thousands of orders while returning only 20–50 records at a time. Querying the entire collection and splitting it into pages in Java does not scale: network traffic, memory, response time, and database load all grow with total data volume.

In reactive programming, **Flux<T>** is a publisher that can emit multiple elements over time; **Mono<T>** emits at most one element. However, **Flux itself carries no total page count or total document count**. To paginate properly, the application still must push **skip/limit/sort or cursor conditions** down to MongoDB, while deciding whether a total result count is genuinely needed.

That is the focus of **Reactive Pagination with Flux and Separate Counts When Needed**, in the **Pagination and Streams** chapter of the **SPRING_DATA_MONGODB** module. These concepts connect Spring Data MongoDB, reactive repositories, `ReactiveMongoTemplate`, queries, indexes, testing, and performance diagnostics.

After this lesson, you will know how to:

1. Declare repositories returning **Flux<Entity>** that accept **Pageable**.
2. Distinguish **a single page's data**, **a window with hasNext**, and a **Page requiring totalElements**.
3. Write a separate **Mono<Long> count...**, invoked only when the UI or business logic needs it.
4. Use **ReactiveMongoTemplate** to fetch one extra record and determine `hasNext` without counting.
5. Design **stable sorting**, indexes, and **seek/keyset pagination** for large datasets.
6. Avoid `block()`, unbounded `collectList()`, N+1 queries, and inconsistencies under concurrent mutations.
7. Test reactive pagination with Reactor Test / `StepVerifier` and a test MongoDB instance.

**Core rule:** Return **Flux** when streaming a page's data; use **Mono<Long>** for a separate count; combine both into **Mono<Page<T>>** only when total metadata is genuinely required.

## 2. The Order model used throughout

Suppose the **orders** collection holds these documents:

~~~javascript
{
  _id: ObjectId("507f1f77bcf86cd799439011"),
  tenantId: "shop-a",
  orderNumber: "ORD-1001",
  status: "PAID",
  createdAt: ISODate("2025-06-01T10:00:00Z"),
  totalMinor: NumberLong("159000")
}
~~~

~~~javascript
{
  _id: ObjectId("507f1f77bcf86cd799439012"),
  tenantId: "shop-a",
  orderNumber: "ORD-1002",
  status: "PAID",
  createdAt: ISODate("2025-06-01T09:00:00Z"),
  totalMinor: NumberLong("89000")
}
~~~

~~~javascript
{
  _id: ObjectId("507f1f77bcf86cd799439013"),
  tenantId: "shop-b",
  orderNumber: "ORD-2001",
  status: "PAID",
  createdAt: ISODate("2025-06-01T08:00:00Z"),
  totalMinor: NumberLong("49000")
}
~~~

**tenantId** defines the data scope. An API call for `shop-a` must never return `shop-b`'s orders. **createdAt** is a BSON Date and **_id** is an `ObjectId`; together they provide a deterministic pagination ordering.

Java entity:

~~~java
package com.example.orders;

import java.time.Instant;
import org.bson.types.ObjectId;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "orders")
public record OrderDocument(
    @Id ObjectId id,
    String tenantId,
    String orderNumber,
    String status,
    Instant createdAt,
    long totalMinor
) {}
~~~

Throughout these examples, the system uses Spring Data MongoDB reactive and the reactive driver. Reactive methods execute only when the publisher is **subscribed**; constructing a `Mono`/`Flux` does not mean a command has been sent to MongoDB yet.

## 3. Differences among Flux, Mono, Page, and Slice

| Type | Meaning | Knows total result count? |
| --- | --- | --- |
| **Flux<OrderDocument>** | Stream of multiple Orders, possibly a bounded page | No, unless another query is run. |
| **Mono<List<OrderDocument>>** | All collected data of **a single page** | Knows only the number of records on that page. |
| **Mono<Long>** | Result of a count query | Knows the number of matching documents at count time. |
| **Mono<Page<OrderDocument>>** | A page of data plus page metadata and total | Has total if computed or supplied. |
| **Mono<Slice<OrderDocument>>** | A window capable of reporting `hasNext` | Does not require a total. |

Visual overview:

~~~mermaid
flowchart TD
    A["Client requests order list"] --> B{"Which metadata is needed?"}
    B -->|"Data only"| C["Flux<Order> + Pageable"]
    B -->|"Needs hasNext"| D["Read size + 1 → Mono<Slice<Order>>"]
    B -->|"Needs total count"| E["Read page + separate count"]
    E --> F["Mono<Page<Order>> or DTO with totalElements"]
~~~

**Important:** `Pageable` describes page number, page size, and `Sort`. It is neither a publisher nor something that magically gives a `Flux` a total page count.

In reactive Spring Data repositories, a method can accept `Pageable` and return `Flux`; this is an intentional design choice to avoid running an extra count query every time you only want a list.

## 4. Declaring a ReactiveMongoRepository with Pageable

Repository for Order:

~~~java
package com.example.orders;

import org.bson.types.ObjectId;
import org.springframework.data.domain.Pageable;
import org.springframework.data.mongodb.repository.ReactiveMongoRepository;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public interface OrderRepository
        extends ReactiveMongoRepository<OrderDocument, ObjectId> {

    Flux<OrderDocument> findByTenantIdAndStatus(
        String tenantId,
        String status,
        Pageable pageable
    );

    Mono<Long> countByTenantIdAndStatus(
        String tenantId,
        String status
    );
}
~~~

Explanation:

- **findByTenantIdAndStatus** is a derived query: Spring Data builds filters on `tenantId` and `status`.
- **Pageable** is a special parameter for limit, offset, and sort; it is not bound as a BSON field.
- **Flux<OrderDocument>** emits the documents matching the page; it is not a `Page` with a built-in total.
- **countByTenantIdAndStatus** is a **separate count query** returning `Mono<Long>`.

Both methods share the same tenant/status predicate, yet **they do not run automatically together**. If the caller only subscribes to the data `Flux`, the count is never invoked.

### 4.1. Sorting must be stable

~~~java
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;

Pageable firstPage = PageRequest.of(
    0,
    20,
    Sort.by(
        Sort.Order.desc("createdAt"),
        Sort.Order.desc("id")
    )
);
~~~

In Spring Data, `id` is the Java property mapped to MongoDB's **_id**. Sorting descending by `createdAt` and using `id` descending as a secondary key establishes a deterministic order when multiple orders share the same timestamp.

**Never paginate without an explicit sort.** MongoDB's natural order is not a stable contract for paginated APIs.

## 5. Simple pagination: returning only Flux

A service can expose just the page's `Flux`:

~~~java
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;
import reactor.core.publisher.Flux;

public class OrderReadService {
    private final OrderRepository repository;

    public OrderReadService(OrderRepository repository) {
        this.repository = repository;
    }

    public Flux<OrderDocument> page(
            String tenantId, String status, int page, int size) {
        if (page < 0 || size < 1 || size > 100) {
            return Flux.error(
                new IllegalArgumentException("Invalid page or size")
            );
        }

        Pageable pageable = PageRequest.of(
            page, size,
            Sort.by(
                Sort.Order.desc("createdAt"),
                Sort.Order.desc("id")
            )
        );

        return repository.findByTenantIdAndStatus(
            tenantId, status, pageable
        );
    }
}
~~~

This example caps pages at **1–100 records**. Even if a client sends `size = 1,000,000`, the service refuses to load all data. In real systems, verify `tenantId` from the authenticated context; never let users supply an arbitrary `tenantId` outside their permissions.

Calling it:

~~~java
Flux<OrderDocument> first =
    service.page("shop-a", "PAID", 0, 20);
~~~

The publisher represents a query with filter, offset, limit, and sort. It emits data only upon subscription (e.g., by WebFlux) and **does not automatically emit page numbers or total order counts**.

### 5.1. Never paginate over an unbounded Flux in memory

Avoid:

~~~java
// Avoid: reading a huge dataset and skipping elements on the client.
Flux<OrderDocument> all = repository.findAll();

Flux<OrderDocument> page =
    all.skip((long) pageNumber * size).take(size);
~~~

This can cause MongoDB to transmit/scan huge amounts of data only for Reactor to discard them. **Pageable or Query.skip/limit must be pushed down to MongoDB** so the server handles pagination.

Likewise, never use **repository.findAll().collectList()** followed by `List.subList` on large collections: `collectList()` buffers the entire result set in memory before slicing.

### 5.2. Is Flux an infinite stream?

No. A `Flux` returned by a `find` query with `Pageable` is typically **finite**: it emits at most `size` records for that page and completes. It is not a tailable cursor, a MongoDB Change Stream, or a continuous live-update subscription.

Backpressure lets the consumer pace element demand, yet it does not replace `skip`/`limit`, indexes, or closing cursors upon cancellation.

## 6. Counting separately only when a total is needed

A screen showing "12,345 matching orders" or "Page 3/618" needs **totalElements**. A page `Flux` does not supply that metadata.

With the repository:

~~~java
Mono<Long> totalPublisher =
    repository.countByTenantIdAndStatus("shop-a", "PAID");
~~~

**Mono<Long>** emits the total document count matching `tenantId` and `status` at count time. If the UI only has a "View more" button, the count may be completely unnecessary.

### 6.1. Why not count on every request?

Counting is a separate query. On large datasets or complex filters, it consumes extra resources, especially if no matching index exists.

| Use case | Is count strictly needed? | Approach |
| --- | --- | --- |
| Continuous scroll feed | No | Page `Flux` or `Slice` with `hasNext`. |
| "Load more" button | Usually no | Read `size + 1` to detect `hasNext`. |
| Displaying "Page 3/100" | Yes | Separate count and compute `totalPages`. |
| Report of total matching orders | Yes | Separate `Mono<Long>`. |
| Multi-batch streaming export | Not per batch | Iterate batches with keyset/cursor and count only if the report requires it. |
| Dashboard with multiple stat widgets | Depends on requirements | Consider batch/aggregation, caching, or clearly labeled approximate counts. |

**Never treat the number of items emitted by Flux as the collection total.** If page size is 20, receiving 20 items only proves at least 20 items matched in that range; it does not prove whether a next page exists.

## 7. Combining Flux with count into Mono<Page<T>>

When an API genuinely needs the total, execute both publishers and combine the results:

~~~java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageImpl;
import org.springframework.data.domain.Pageable;
import reactor.core.publisher.Mono;

public Mono<Page<OrderDocument>> pageWithTotal(
        String tenantId, String status, Pageable pageable) {

    Mono<java.util.List<OrderDocument>> rows =
        repository.findByTenantIdAndStatus(
            tenantId, status, pageable
        ).collectList();

    Mono<Long> total =
        repository.countByTenantIdAndStatus(tenantId, status);

    return Mono.zip(rows, total)
        .map(tuple -> new PageImpl<>(
            tuple.getT1(),
            pageable,
            tuple.getT2()
        ));
}
~~~

In this example, `repository` is an injected dependency. **`collectList()` is safer when `Flux` is already bounded by `Pageable`**, because memory is bounded to a typical page size rather than the whole collection.

**Mono.zip** subscribes to both publishers when the combined `Mono` is subscribed. The count is an independent database operation that can run concurrently with the page query. There is no guarantee the two observe the exact same data snapshot under concurrent inserts or deletes.

### 7.1. Computing page counts

A `Page` typically provides:

- **getContent()**: list of documents on the current page.
- **getNumber()**: current page index (0-based).
- **getSize()**: requested page size.
- **getTotalElements()**: total matching documents per the count.
- **getTotalPages()**: total pages derived from `totalElements` and `size`.

`PageImpl` is an implementation of `Page` and can adjust total metadata in certain end-of-list cases to reduce discrepancies from mutating data. **Do not treat `PageImpl` as a consistent snapshot mechanism** across the two queries.

### 7.2. Cost of building a Page

Constructing a `Page` with totals generally entails:

1. A query fetching the page's documents.
2. A count query with the identical filter.
3. Collecting the page's elements before emitting the `Page`.

That is why returning **Mono<Page<T>>** makes sense only when the UI or business contract demands a total. Never force every reactive endpoint to construct a `Page`.

## 8. Designing responses with an optional total

Many APIs support a lightweight list by default while allowing clients to request a total via **includeTotal=true**. That avoids forcing a mandatory total count on every request.

Illustrative DTO:

~~~java
import java.util.List;

public record OrderWindow(
    List<OrderRow> items,
    int page,
    int size,
    boolean hasNext,
    Long totalElements
) {}
~~~

Here **`totalElements == null`** means **"total was not requested or computed"**, not that the total is 0. In JSON serialization, you can omit null fields per your API conventions; document this contract clearly for clients.

**One critical design fix to note:** If you load only `size` records, you **cannot tell `hasNext` accurately** from the list length alone. To provide `hasNext` without counting, fetch **one extra record** and return only the first `size` records. The next section shows how.

## 9. Slice: reading size + 1 to detect hasNext

Strategy:

1. Client requests `size = 20`.
2. Query MongoDB for at most **21** records under the same sort.
3. If 21 records arrive, **`hasNext = true`**; return the first 20 records.
4. If at most 20 records arrive, **`hasNext = false`** at query time.

~~~mermaid
flowchart LR
    A["Request page=2, size=20"] --> B["MongoDB skip=40, limit=21"]
    B --> C["Flux of at most 21 documents"]
    C --> D["collectList up to 21"]
    D --> E["Return 20 items + hasNext"]
~~~

**Important note on offset:** If you build `Pageable` with **PageRequest.of(2, 21)**, the offset becomes **42**, not **40**. Therefore, when reading one extra record, keep the offset derived from the **client's requested `size`**, and override only the limit to **`size + 1`**.

### 9.1. ReactiveMongoTemplate: limiting to one extra element

~~~java
import java.util.List;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Slice;
import org.springframework.data.domain.SliceImpl;
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.ReactiveMongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import reactor.core.publisher.Mono;

public class OrderSliceService {
    private final ReactiveMongoTemplate template;

    public OrderSliceService(ReactiveMongoTemplate template) {
        this.template = template;
    }

    public Mono<Slice<OrderDocument>> findSlice(
            String tenantId, String status, int page, int size) {

        if (page < 0 || size < 1 || size > 100) {
            return Mono.error(
                new IllegalArgumentException("Invalid page or size")
            );
        }

        Pageable pageable = PageRequest.of(
            page, size,
            Sort.by(
                Sort.Order.desc("createdAt"),
                Sort.Order.desc("id")
            )
        );

        Query query = Query.query(
            Criteria.where("tenantId").is(tenantId)
                .and("status").is(status)
        );
        query.with(pageable);        // Keep offset = page * size.
        query.limit(size + 1);       // Only increase limit.

        return template.find(query, OrderDocument.class)
            .collectList()
            .map(rows -> {
                boolean hasNext = rows.size() > size;
                List<OrderDocument> content = rows.subList(
                    0, Math.min(size, rows.size())
                );
                return new SliceImpl<>(
                    content, pageable, hasNext
                );
            });
    }
}
~~~

With **Query.with(pageable)**, Spring Data applies skip, limit, and sort for the requested page. **query.limit(size + 1)** overrides the query's limit without altering the offset just applied. This avoids the shifted-offset bug from creating a `PageRequest` of size 21.

**`Slice` needs no count.** It supplies the window's content and `hasNext` from the single executed query.

### 9.2. Do not turn hasNext into an absolute quantity

`hasNext = true` only means at least one record existed beyond the page during that query. It does not tell you how many pages or documents remain. If a writer deletes that record right afterward, the next page can still be empty—that is an inherent limit of paginating over mutating data.

### 9.3. Returning lean DTOs instead of full entities

If the client only needs `orderNumber`, `createdAt`, and `totalMinor`, use a projection or map to a DTO:

~~~java
public record OrderRow(
    String id,
    String orderNumber,
    java.time.Instant createdAt,
    long totalMinor
) {}
~~~

~~~java
public OrderRow toRow(OrderDocument document) {
    return new OrderRow(
        document.id().toHexString(),
        document.orderNumber(),
        document.createdAt(),
        document.totalMinor()
    );
}
~~~

Projections reduce payload transfer and conversion work, though they do not solve deep offsets or make a query index-covered by themselves. Combine all three: proper filters, matching sorts/indexes, and fetching only needed fields.

## 10. When the client requests total: combining Slice and count

If an API always returns `hasNext` and includes **totalElements** only when requested, you can reuse `findSlice`:

~~~java
public Mono<OrderWindow> findWindow(
        String tenantId,
        String status,
        int page,
        int size,
        boolean includeTotal) {

    Mono<org.springframework.data.domain.Slice<OrderDocument>> sliceMono =
        findSlice(tenantId, status, page, size);

    if (!includeTotal) {
        return sliceMono.map(slice -> new OrderWindow(
            slice.getContent().stream().map(this::toRow).toList(),
            page,
            size,
            slice.hasNext(),
            null
        ));
    }

    Mono<Long> countMono =
        repository.countByTenantIdAndStatus(tenantId, status);

    return Mono.zip(sliceMono, countMono)
        .map(pair -> new OrderWindow(
            pair.getT1().getContent().stream().map(this::toRow).toList(),
            page,
            size,
            pair.getT1().hasNext(),
            pair.getT2()
        ));
}
~~~

The snippet above is an illustrative service method assuming **findSlice** and **repository** are provided as in earlier sections. When `includeTotal=false`, this branch **neither constructs nor subscribes to `countMono`**. When `includeTotal=true`, it fetches the total via a separate query, and the two queries can be subscribed concurrently.

The **toRow(OrderDocument)** helper shown earlier converts entities into response DTOs. This keeps hex string IDs and exposes only required fields; `OrderWindow` thus holds **`List<OrderRow>`** instead of full entities.

This design works nicely when serving two client types:

- **Mobile infinite scroll** needs only `items` and `hasNext`.
- **Admin web UI** adds `totalElements` to draw page numbers or summary stats.

Never return **totalElements = 0** when you have not counted, as clients may misinterpret that as zero matching records.

## 11. Why does offset pagination slow down on deep pages?

With offset pagination, MongoDB must step through records prior to the `skip` position to reach the current page. Example:

~~~javascript
db.orders.find({
  tenantId: "shop-a",
  status: "PAID"
})
.sort({ createdAt: -1, _id: -1 })
.skip(100000)
.limit(20);
~~~

Even though only 20 documents are returned, MongoDB may traverse a huge number of index keys before reaching offset 100,000. Small projections do not eliminate deep skip overhead.

| Pagination style | Advantages | Limitations |
| --- | --- | --- |
| Offset + `Pageable` | Simple, supports requesting page N | Large skips are costly; prone to drift on mutating data. |
| `Slice` with `size+1` | Knows `hasNext` without counting | Still incurs `skip` cost when using offsets. |
| Keyset / seek | Better for "load more" on large datasets | Cannot jump straight to arbitrary page numbers; needs stable cursors. |
| Stream / cursor batch | Suitable for sequential processing of many records | Must manage bounds, cancellation, lifetime, and mutating data. |

Therefore, for APIs sequentially browsing very large datasets, consider **keyset pagination** instead of only optimizing projections.

## 12. Keyset pagination: fetching records after a cursor

Suppose sorting is **createdAt descending**, then **_id descending**. The client received the last record of the previous window with:

~~~text
lastCreatedAt = 2025-06-01T09:00:00Z
lastId = 507f1f77bcf86cd799439012
~~~

The next window must fetch documents:

- With `createdAt` **less than** `lastCreatedAt`; **or**
- With `createdAt` **equal to** `lastCreatedAt` and `_id` **less than** `lastId`.

In `mongosh`:

~~~javascript
db.orders.find({
  tenantId: "shop-a",
  status: "PAID",
  $or: [
    { createdAt: { $lt: ISODate("2025-06-01T09:00:00Z") } },
    {
      createdAt: ISODate("2025-06-01T09:00:00Z"),
      _id: { $lt: ObjectId("507f1f77bcf86cd799439012") }
    }
  ]
})
.sort({ createdAt: -1, _id: -1 })
.limit(21);
~~~

With `size = 20`, `limit(21)` still detects `hasNext`. **Never use `skip`**, because the cursor defines the starting boundary of the next window.

### 12.1. Writing with ReactiveMongoTemplate

~~~java
import java.time.Instant;
import org.bson.types.ObjectId;
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.ReactiveMongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import reactor.core.publisher.Flux;

public Flux<OrderDocument> findAfter(
        ReactiveMongoTemplate template,
        String tenantId,
        String status,
        Instant lastCreatedAt,
        ObjectId lastId,
        int size) {

    if (size < 1 || size > 100) {
        return Flux.error(new IllegalArgumentException("Invalid size"));
    }

    Criteria after = new Criteria().orOperator(
        Criteria.where("createdAt").lt(lastCreatedAt),
        new Criteria().andOperator(
            Criteria.where("createdAt").is(lastCreatedAt),
            Criteria.where("_id").lt(lastId)
        )
    );

    Criteria filter = new Criteria().andOperator(
        Criteria.where("tenantId").is(tenantId),
        Criteria.where("status").is(status),
        after
    );

    Query query = Query.query(filter)
        .with(Sort.by(
            Sort.Order.desc("createdAt"),
            Sort.Order.desc("id")
        ))
        .limit(size + 1);

    return template.find(query, OrderDocument.class);
}
~~~

This snippet returns a `Flux` of at most `size+1` elements. Callers can `collectList()`, slice the first `size` items, and construct `nextCursor` and `hasNext` just like the `Slice` example. On the first page when no cursor exists yet, apply only the tenant/status filter with the same sort and limit, omitting the **`after`** branch.

### 12.2. Why is the secondary key `_id` needed?

If two `Order`s share the same `createdAt` and the cursor uses only `createdAt`, `createdAt < lastTime` will skip other documents sharing that timestamp. Adding `_id` as a secondary key defines a total ordering and a consistent seek predicate.

### 12.3. Cursor contract

Clients should treat the cursor as an opaque token. The server can encode:

- `lastCreatedAt`;
- `lastId`;
- tenant scope and allowed filter/sort;
- cursor format version.

Tokens must be validated on receipt; if tamper protection is required, sign or protect them appropriately. **Never trust a `tenantId` claimed inside a cursor** without checking it against the authenticated context.

Keyset pagination requires stable sort keys. If `createdAt` is edited or documents are deleted/inserted between reads, results can still change. It avoids many deep-offset issues, yet **it is not an immutable snapshot of the entire collection**.

## 13. Indexes for filtering and sorting

Common query pattern:

~~~javascript
db.orders.find({
  tenantId: "shop-a",
  status: "PAID"
})
.sort({ createdAt: -1, _id: -1 })
.limit(20);
~~~

An index worth evaluating:

~~~javascript
db.orders.createIndex({
  tenantId: 1,
  status: 1,
  createdAt: -1,
  _id: -1
});
~~~

`tenantId` and `status` serve equality predicates; `createdAt` and `_id` support descending sort order. The index is a **candidate suited to this specific query**, not a blanket rule to create every index for every query.

### 13.1. Using explain to verify

~~~javascript
db.orders.find({
  tenantId: "shop-a",
  status: "PAID"
})
.sort({ createdAt: -1, _id: -1 })
.limit(20)
.explain("executionStats");
~~~

When diagnosing, inspect:

| Metric / component | What to check |
| --- | --- |
| `winningPlan` | Is the expected index being used? |
| `totalKeysExamined` | How many index keys were scanned? |
| `totalDocsExamined` | How many documents had to be fetched? |
| `nReturned` | How many records were returned? |
| `SORT` stage | Is there an in-memory sort outside the index? |
| `executionTimeMillis` | Observed time under test conditions |

With deep offsets, `totalKeysExamined` can far exceed `nReturned` even when the query uses an index. Keyset narrows the scan range via the cursor predicate, yet you must still verify with `explain` on realistic data.

### 13.2. Count also needs matching filters and indexes

Corresponding count query:

~~~javascript
db.orders.countDocuments({
  tenantId: "shop-a",
  status: "PAID"
});
~~~

The count needs the exact same tenant scope, status, and any other business predicates as the page query. If you add soft-delete, time-range, or authorization predicates to the list query and forget them in the count, **`totalElements` will no longer match the list**.

Never assume `countDocuments` is cheap simply because it returns a single number. It still executes a query; cost depends on predicates, indexes, data volume, and execution plans.

## 14. Data changing during pagination

Suppose page 1 returned the 20 newest Orders. Afterward, a new Order is inserted with a `createdAt` newer than all existing ones. When the client requests page 2 via **`skip(20)`**, document positions have shifted. The result may **duplicate an element from the previous page or skip an element**.

~~~mermaid
flowchart TD
    A["Page 1: 20 newest orders"] --> B["Writer inserts a new order at the top"]
    B --> C["Page 2 using skip=20"]
    C --> D["Positions shifted → possible duplicates/skips"]
    B --> E["Page 2 using keyset from last record"]
    E --> F["Continues from received sort boundary"]
~~~

Keyset anchored on the last item's cursor prevents a new insert ahead of the cursor from shifting offsets. Still, it does not prevent documents in the older range from being updated/deleted, nor does it freeze data at the moment page 1 was read.

### 14.1. Count and items may come from different points in time

When using:

~~~java
Mono.zip(
    repository.findByTenantIdAndStatus(
        tenantId, status, pageable
    ).collectList(),
    repository.countByTenantIdAndStatus(tenantId, status)
);
~~~

The two publishers can observe different database states under concurrent writes. **`totalElements` and `items` do not have to match strictly.**

For ordinary APIs, approximate consistency at read time is usually acceptable. If business logic demands a strict snapshot, design reads with snapshot/transaction semantics compatible with your MongoDB deployment and Spring Data reactive transaction manager. Calling `Mono.zip` alone does not create a transaction.

### 14.2. Do not treat count as proof of existence during updates

A UI seeing `totalElements = 10` does not guarantee all ten documents still exist when a user clicks "Delete." Update and delete operations must check filters/IDs, optimistic locking, or `matchedCount` per business rules—never rely on a prior page's count.

## 15. Reactive: subscriptions, backpressure, timeouts, and errors

### 15.1. Never call block() on an event loop

Avoid writing:

~~~java
// Avoid in WebFlux/reactive services.
long total = repository.countByTenantIdAndStatus(
    tenantId, status
).block();
~~~

`block()` breaks the non-blocking model and can stall event-loop threads. If you need the total, keep it in a `Mono` and compose with `zip`/`flatMap`.

### 15.2. Never collect an entire collection

~~~java
// Unsuitable for large collections.
Mono<java.util.List<OrderDocument>> everything =
    repository.findAll().collectList();
~~~

**`collectList()` holds every element in memory.** Use it only after enforcing a tight bound such as `Pageable` `size <= 100` or `size+1`, or when the input stream is known to be small.

### 15.3. Timeouts and error handling

Reactive operations can fail due to network issues, server errors, mapping bugs, authorization failures, or timeouts. The API layer must map exceptions cleanly while retaining useful logs/metrics. When setting Reactor timeouts, understand how they affect subscription/cancellation and note that they do not replace server-side query timeouts.

Do not blindly retry heavy queries at high rates. For **read-only** queries, bounded retries on transient errors may be reasonable while monitoring load. When retrying read-write flows, ensure independent idempotency.

### 15.4. Flux is not an infinite data stream

A `Flux` from a repository `find` may use a cursor and emit driver batches. Yet when a caller requests a page, it remains a **finite query**. Cancelling the subscription releases cursor resources via the driver; do not keep unneeded subscriptions alive or subscribe twice merely to "peek" at data.

Each new subscription can re-execute the query. Therefore, if a request needs both items and metadata, compose publishers cleanly instead of accidentally subscribing to the same `Flux` twice.

## 16. What semantics can a count have?

Developers frequently confuse three questions:

1. **How many documents match the filter?** — use a filtered count (e.g., `countByTenantIdAndStatus`).
2. **How many elements are in the page just received?** — use the `content` size after reading the page.
3. **Is there a next page?** — read `size+1` and check for the extra item, or derive from total if already computed.

These are not identical.

For example, with 105 orders matching the filter, `size = 20`, `page = 5` (the sixth page, 0-based):

| Value | Result |
| --- | --- |
| `totalElements` | 105 |
| `totalPages` | 6 |
| Page 5 offset | 100 |
| Items on page 5 | 5 |
| `hasNext` on page 5 | false |

If the client only wants to scroll further, **`hasNext`** is usually sufficient. If it must display "105 orders", run a count query or maintain a dedicated counter with clearly documented accuracy guarantees.

### 16.1. Exact counts vs. estimates

**`countDocuments(filter)`** counts matching records visible to the query, still affected by execution timing and write concurrency. Estimation techniques or cached counts can be faster in certain workloads, yet must never be labeled an "exact total" if they lag behind updates.

Never replace a filtered count with whole-collection **`estimatedDocumentCount`**: it does not report counts scoped to a specific tenant or status.

### 16.2. When should counts be cached?

If a dashboard tolerates slightly stale numbers, you can cache counts or maintain separate stats. Define clearly:

- Cache keys including all necessary filters and tenant scopes.
- Explicit TTLs or invalidation mechanisms.
- Clear API documentation indicating approximate or near-real-time numbers.
- Never rely on cached counts to enforce business invariants or authorization checks.

## 17. Using @Query with Flux and Pageable

Derived queries are not the only option. You can declare explicit BSON filters:

~~~java
import org.springframework.data.domain.Pageable;
import org.springframework.data.mongodb.repository.Query;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public interface OrderRepository
        extends ReactiveMongoRepository<OrderDocument, ObjectId> {

    @Query("{ 'tenantId': ?0, 'status': ?1 }")
    Flux<OrderDocument> findForTenantAndStatus(
        String tenantId,
        String status,
        Pageable pageable
    );

    @Query(
        value = "{ 'tenantId': ?0, 'status': ?1 }",
        count = true
    )
    Mono<Long> countForTenantAndStatus(
        String tenantId,
        String status
    );
}
~~~

In this example, **`?0`** and **`?1`** bind positionally, while `Pageable` is a special parameter applying pagination. You do not bind `Pageable` as a field value inside the JSON filter.

**Keep both filters identical.** If the data query adds a date range, soft-delete check, or tenant permission predicate, the count query must apply the exact same conditions. When filter logic branches dynamically across many fields, use `ReactiveMongoTemplate` or a shared query builder so the two definitions cannot drift apart.

## 18. Result DTOs and WebFlux APIs

An API should explicitly decide whether to include totals. Example response for "view more" mode:

~~~json
{
  "items": [
    {
      "id": "507f1f77bcf86cd799439011",
      "orderNumber": "ORD-1001",
      "createdAt": "2025-06-01T10:00:00Z",
      "totalMinor": 159000
    }
  ],
  "page": 0,
  "size": 20,
  "hasNext": true
}
~~~

When the client requests the total, you can add:

~~~json
{
  "items": [],
  "page": 6,
  "size": 20,
  "hasNext": false,
  "totalElements": 105
}
~~~

These two JSON payloads illustrate response shapes in separate scenarios, not the same data snapshot. The second deliberately requests **page=6**, past the final page of a 105-item set (valid pages are 0–5), so `items` is empty while `totalElements` remains 105. In your API contract, be consistent about whether **`totalElements` is omitted** or **`null`** when not computed.

### 18.1. Controllers need not call block()

A WebFlux controller can return a `Mono` directly:

~~~java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class OrderController {
    private final OrderWindowService service;

    public OrderController(OrderWindowService service) {
        this.service = service;
    }

    @GetMapping("/orders")
    public Mono<OrderWindow> getOrders(
            @RequestParam String status,
            @RequestParam(defaultValue = "0") int page,
            @RequestParam(defaultValue = "20") int size,
            @RequestParam(defaultValue = "false") boolean includeTotal) {

        // tenantId must be obtained from the request's authentication context.
        String tenantId = authenticatedTenantId();

        return service.findWindow(
            tenantId, status, page, size, includeTotal
        );
    }
}
~~~

This snippet illustrates **controller method signatures and returning publishers**, not a copy-pasteable complete controller: `authenticatedTenantId()` is a placeholder helper that must be backed by your authentication system, and `OrderWindowService` must provide `findWindow` as shown earlier. Never accept `tenantId` straight from a query parameter and trust it as the user's scope.

In WebFlux, the framework subscribes to the publisher and serializes the response once the `Mono` emits; the controller must never call `subscribe()` or `block()`.

## 19. Testing reactive pagination

Unit tests that only mock a repository verify how `Pageable` and count are called, yet **never verify filters, sorting, skip/limit, or BSON mapping against real MongoDB**. Include integration tests using a dedicated MongoDB test instance, such as Testcontainers.

Behaviors to verify:

| Scenario | Expectation |
| --- | --- |
| `size=2`, 5 matching records | Page 0 returns up to 2, page 1 up to 2, page 2 returns 1. |
| Two Orders sharing `createdAt` | Secondary `id` sort produces deterministic ordering. |
| Data for `shop-a` and `shop-b` | `shop-a` never sees `shop-b`'s Orders. |
| Subscribing only to page `Flux` | Does not automatically trigger a count query. |
| `includeTotal=false` | Response omits `totalElements` or sets it to `null` per contract. |
| `includeTotal=true` | Count is invoked separately with the exact same filter. |
| Reading `size+1` | Returns at most `size` items; `hasNext` is accurate at query time. |
| Page past end of list | `Flux` completes empty; `Slice` has `hasNext=false`. |
| Negative page or `size > max` | Validation error is returned. |
| Client cancels subscription | No extra unintended queries are executed outside the subscribed path. |
| Large offset | Measured/bounded; evaluate keyset pagination. |
| Count and page under concurrent writes | Do not expect a strict snapshot without an explicit consistency mechanism. |

### 19.1. Using StepVerifier

Example testing the limit on a sorted `Flux`:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;
import reactor.test.StepVerifier;

@SpringBootTest
class ReactiveOrderPaginationTest {

    @Autowired
    OrderRepository repository;

    @Test
    void returnsAtMostRequestedPageSize() {
        var pageable = PageRequest.of(
            0, 2,
            Sort.by(
                Sort.Order.desc("createdAt"),
                Sort.Order.desc("id")
            )
        );

        StepVerifier.create(
            repository.findByTenantIdAndStatus(
                "test-tenant", "PAID", pageable
            ).collectList()
        )
        .assertNext(rows -> {
            assertThat(rows).hasSizeLessThanOrEqualTo(2);
        })
        .verifyComplete();
    }
}
~~~

This test only **illustrates the size bound**; to test actual pagination, seed test documents with an isolated `tenantId` and controlled timestamps/IDs. Without seeded data, an empty result still passes `size <= 2` and proves nothing about real data handling.

### 19.2. Complete fixture and order verification

A reliable integration test should:

1. Generate a unique random `tenantId` per test.
2. Insert at least 5 `PAID` Orders, including two sharing the same `createdAt`.
3. Insert at least one Order from another tenant and one with another status.
4. Request `page=0,size=2` and then `page=1,size=2`.
5. Assert exact ordering by `createdAt DESC, id DESC`, not merely element count.
6. Verify `countByTenantIdAndStatus` returns the exact seeded count.
7. Verify `Slice` reading `size+1` returns accurate `hasNext=true/false`.
8. Clean up data by `tenantId` after the test, **only on the test database**.

### 19.3. Testing that count runs only when needed

You can unit-test the service with a mocked repository:

~~~java
import static org.mockito.Mockito.*;
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

@Test
void pageOnlyDoesNotInvokeCount() {
    when(repository.findByTenantIdAndStatus(
        eq("shop-a"), eq("PAID"), any()
    )).thenReturn(Flux.empty());

    StepVerifier.create(
        service.page("shop-a", "PAID", 0, 20)
    ).verifyComplete();

    verify(repository, never())
        .countByTenantIdAndStatus(anyString(), anyString());
}
~~~

This snippet assumes `repository` and `service` are mock/SUT instances initialized in the test class, with Mockito and Reactor Test imported. This unit test confirms the service uses only `Flux`, while integration tests prove MongoDB applies `Pageable` accurately.

### 19.4. Inspecting in mongosh

Cross-check the actual queries:

~~~javascript
db.orders.find({
  tenantId: "shop-a",
  status: "PAID"
})
.sort({ createdAt: -1, _id: -1 })
.skip(40)
.limit(21);

db.orders.countDocuments({
  tenantId: "shop-a",
  status: "PAID"
});
~~~

These two commands let you diagnose discrepancies between window data and total document count. Invoked separately, they carry no guarantee of running on the same snapshot.

## 20. Common mistakes

| Symptom | Common cause | Fix |
| --- | --- | --- |
| `Flux` returns a page without a total | `Flux` carries no `Page` metadata | Run a separate count if the UI needs it. |
| Every page runs a slow count | Using `Page` by default even when only "View more" is needed | Return `Flux`/`Slice`, counting only on demand. |
| `hasNext=true` even on the last page | Checking `rows.size()==size` | Read `size+1` or use a computed total. |
| Page 2 starts at the wrong item | Using `PageRequest.of(page,size+1)` | Keep offset from original `size` and increase only `limit`. |
| Same Order repeats across two pages | Missing stable sort or concurrent writes | Add secondary `_id` sort; consider keyset. |
| Deep pages respond very slowly | MongoDB must skip large counts | Check `explain` and switch to seek/keyset when appropriate. |
| `totalElements` disagrees with expected items | Count filter missing predicates or concurrent mutations | Keep filters identical and recognize snapshot limits. |
| API leaks another tenant's orders | Missing tenant filter or trusting input tenant | Derive tenant from auth and enforce on every query. |
| Memory usage spikes sharply | Calling `collectList` on an unbounded `Flux` | Bound on the server before collecting. |
| WebFlux hangs / blocks | Calling `.block()` in a service or controller | Compose `Mono`/`Flux` using Reactor operators. |
| Count is positive yet page is empty | Page index past the end or documents just deleted | Verify offset and 0-based page numbering. |
| Query is slow despite having an index | Index mismatches filter/sort, or deep offset | Check `winningPlan`/`keysExamined`/`docsExamined`. |
| Tests always pass despite broken paging | Empty seed or asserting only `size <= limit` | Seed fixtures and assert exact ordering and `hasNext`. |
| `Flux` runs the query twice | Two independent subscriptions | Compose pipelines cleanly and avoid accidental double subscription. |

## 21. Practice exercises

### Exercise 1: Flux repository and count

Write two methods to find `PAID` Orders for a tenant with `Pageable` and count matching Orders.

**Suggested solution:**

~~~java
Flux<OrderDocument> findByTenantIdAndStatus(
    String tenantId, String status, Pageable pageable
);

Mono<Long> countByTenantIdAndStatus(
    String tenantId, String status
);
~~~

### Exercise 2: knowing hasNext without counting

Client requests `page=3,size=25`. How many records does the query read and how many does it skip?

**Answer:** offset **`3 * 25 = 75`**, limit **`26`**; return at most 25 items. If 26 records come back, `hasNext=true`. Do not use `PageRequest.of(3,26)`, as that sets offset to 78.

### Exercise 3: is total needed?

A mobile API only shows a list and a "View more" button. Does it need to call `countByTenantIdAndStatus` on every request?

**Answer:** no. Use `Slice`/`size+1` or keyset with one extra record to detect whether a next page follows.

### Exercise 4: why must sort include `_id`?

Two `PAID` Orders share the same `createdAt`. What can happen if you sort only by `createdAt`?

**Answer:** relative order among tied `createdAt` records is not deterministically guaranteed. Append `_id` as a secondary key and keep the exact same order across all queries and cursors.

### Exercise 5: concurrent writes and totals

`Mono.zip` combines the page `Flux` and `Mono<Long>` count. Do both results always reflect the exact same snapshot?

**Answer:** no. They are two separate queries and can observe the database at different times. Use appropriate transaction/snapshot reads if the contract demands strong consistency.

### Exercise 6: deep pagination

A page at offset 500,000 runs very slowly despite returning only 20 records. Propose a fix.

**Suggested solution:** inspect `explain`, tune indexes for filter and sort, consider keyset/seek pagination on `createdAt` and `_id` instead of huge skips, and cap overly deep pages if arbitrary jumps are unnecessary.

### Exercise 7: reactive anti-pattern

~~~java
List<OrderDocument> all =
    repository.findAll().collectList().block();
~~~

**Question:** why is this inappropriate for reactive pagination?

**Answer:** it loads all data into memory, blocks the thread via `block()`, and pushes no limit down to MongoDB. Use `Flux` with `Pageable` or a `Query` with sort/limit, keeping `Mono`/`Flux` non-blocking.

### Exercise 8: mismatched count filter

The list filters by `tenantId`, `status`, and `deleted=false`, while count filters only by `tenantId` and `status`. Is `totalElements` trustworthy?

**Answer:** no, because count measures a broader set than the page data. Both must apply identical authorization and business predicates.

### Exercise 9: keyset cursor

Sort is `createdAt DESC` and `_id DESC`. The last cursor has `createdAt=T`, `_id=I`. Write the condition for the next page.

**Answer:** fetch documents with **`createdAt < T`** or **`createdAt = T` and `_id < I`**, keeping the exact same tenant/status filter, sort, and `limit(size+1)`.

## 22. Principles to remember

1. **Flux is a stream of elements, not a Page**, and carries no automatic `totalElements`.
2. **Pageable/skip/limit/sort must be pushed to MongoDB**—never fetch an entire `Flux` and slice in Java.
3. **Counting is a separate query**; `Mono<Long>` only needs to be subscribed when the client actually wants a total.
4. **`Mono.zip(data.collectList(), count)` can build a Page**, yet the two queries do not share a snapshot automatically.
5. **Slice reading `size+1` detects `hasNext` without counting**; compute offset from `page * size`, not `size+1`.
6. **Sorting needs a stable secondary key** such as `_id` to reduce duplicate/skip risks across pages.
7. **Deep offsets are costly**; keyset/seek pagination usually fits "load more" flows better on large datasets.
8. **Indexes must match filter and sort**; verify with `explain("executionStats")` instead of guessing.
9. **Never call `block()` on a WebFlux thread**, never `collectList` an unbounded query, and avoid accidental double subscriptions.
10. **Count filters must match page data filters**, especially tenant, status, soft-delete, and authorization checks.
11. **Test with `StepVerifier` and a test MongoDB instance** to verify ordering, limits, `hasNext`, counts, and behavior under mutating data.

Mastering **reactive pagination with Flux and separate counts when needed** helps **SPRING_DATA_MONGODB** services build lean, non-blocking APIs that optimize query costs and choose deliberately among paginated streams, `Slice` with `hasNext`, and `Page` with totals according to business requirements.
