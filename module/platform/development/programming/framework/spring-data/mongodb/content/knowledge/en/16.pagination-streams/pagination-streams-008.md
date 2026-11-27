# Scrolling, ScrollPosition, and Window by Version

## 1. Why is Scrolling needed alongside regular pagination?

A sales system holds millions of orders in MongoDB. The `GET /orders` endpoint only needs to display 20 orders at a time, while a background job needs to scan hundreds of thousands of orders in a stable order.

The familiar approach uses `Pageable`:

```java
PageRequest.of(0, 20);
PageRequest.of(1, 20);
PageRequest.of(2, 20);
```

Here each call specifies a page number and page size; MongoDB typically uses `skip` and `limit` for offset pagination. This works well when users want to jump to **page N**, yet it has two notable drawbacks:

- With large offsets, the database may have to skip past many results before returning 20 documents.
- If documents are inserted, deleted, or reordered between reads, users can observe **duplicate or skipped** records.

**Scrolling** traverses data sequentially one **window** at a time. The application receives a `Window<T>` containing at most a bounded number of results, obtains a `ScrollPosition` to **continue after the last element**, and reads the next window. This lesson belongs to the **Pagination and Streams** chapter in the **SPRING_DATA_MONGODB** module: using Spring Data MongoDB to access documents via repositories or `MongoTemplate`, while understanding the impact of sorting, indexes, consistency, reactive access, testing, and performance.

**Clarify right away:** a `Window<T>` is not a MongoDB tailable cursor, not a `Stream<T>` holding a long-lived open cursor, and not an immutable snapshot of the whole collection. Each request for the next window can execute a new query.

## 2. Support by Spring Data version

The title emphasizes **by version** because the Scroll API is not uniformly present across all Spring Data generations.

| Component and milestone | Meaning for examples in this lesson |
| --- | --- |
| **Spring Data Commons 3.1+** | Introduces `ScrollPosition`, `OffsetScrollPosition`, `KeysetScrollPosition`, `Window<T>`, and the `WindowIterator` utility. |
| **Spring Data MongoDB 4.1+** | Adds scrolling support at the repository layer and `MongoOperations.scroll(Query, Class<T>)`; corresponding APIs exist in imperative and reactive templates. |
| **Spring Data MongoDB 4.0 and below** | Do not copy `MongoTemplate.scroll(...)` examples directly; typically use `skip/limit`, manual keyset queries, or upgrade. |
| **4.2, 4.3, 4.4, 4.5, 5.x lines** | The Scroll API remains available, though overload signatures, utilities, and baseline requirements must be checked against the exact version's Javadoc. |
| **Spring Boot dependency management** | Determine the **actual** `spring-data-mongodb` and `spring-data-commons` versions from your dependency tree/BOM; do not pick APIs solely from the Spring Boot version name. |

These milestones reflect Spring Data APIs, **not** a new `scroll()` feature built into MongoDB Server itself. Spring Data constructs MongoDB queries to perform the scrolling. Differences such as `Query.with(ScrollPosition)`, reactive return types, or newer overloads must be checked against your deployed version.

The code below takes **Spring Data MongoDB 4.1+ / Spring Data Commons 3.1+** as the minimum baseline for the illustrated scrolling APIs; use Java and dependencies compatible with that release.

**Official references to verify against your version:**

- [MongoDB-specific Query Methods – Scrolling](https://docs.spring.io/spring-data/mongodb/reference/mongodb/repositories/query-methods.html)
- [Spring Data Commons – Scrolling](https://docs.spring.io/spring-data/commons/reference/repositories/scrolling.html)
- [MongoOperations Javadoc](https://docs.spring.io/spring-data/mongodb/reference/api/java/org/springframework/data/mongodb/core/MongoOperations.html)
- [ReactiveMongoOperations Javadoc](https://docs.spring.io/spring-data/mongodb/reference/api/java/org/springframework/data/mongodb/core/ReactiveMongoOperations.html)

Default reference URLs may point to the latest documentation; when compiling a specific application, check the Javadoc matching your exact artifact version.

## 3. Three primary objects in the Scroll API

| Concept | Role | Do not confuse with |
| --- | --- | --- |
| `Window<T>` | A bounded group of results with the ability to get a position for reading further | `Page<T>` with total record/page counts |
| `ScrollPosition` | An **exclusive** position: the next query starts **after** that position | Page number or MongoDB cursor ID |
| `OffsetScrollPosition` | Represents an index-based position within an ordered result set | An initial offset always starting at `0` |
| `KeysetScrollPosition` | Represents a position by the values of sort keys and tie-breaker keys | Using only `_id` for every sort pattern |
| `WindowIterator<T>` | Utility that iterates across multiple `Window`s by requesting subsequent windows | `Stream` keeping a server cursor continuously open |

A scrolling query requires three ingredients: **filter predicates**, a **stable sort order**, and a **limit per window**. A position is only meaningful when those ingredients stay consistent across reads.

### 3.1. The exclusive position rule

Suppose a result set is ordered by timestamp then ID:

```text
Position   0        1        2        3        4
Order      A        B        C        D        E
            └── Window 1 ──┘  └── Window 2 ──┘
               A, B, C          D, E
```

If the first window contains `A, B, C`, the position obtained from `C` is passed to the next call. The next window starts **after C**, without returning `C` again.

Pay close attention to:

- `ScrollPosition.offset()`: **initial position**, pointing before any indexed element.
- `ScrollPosition.offset(0)`: points to element at index 0; because the position is **exclusive**, the window following it **skips the first element**.
- `ScrollPosition.keyset()`: **initial keyset position**, with no key-continuation predicate applied yet.
- `window.positionAt(window.size() - 1)`: gets the position of the last element in a **non-empty** window in order to fetch the next one.

Never call `positionAt(-1)` or assume an empty window still has a last element.

## 4. Creating sample data to observe

Example `orders` collection where each order has `customerId`, `placedAt`, `status`, and `totalAmount`. When learning scrolling, use a test database; never run write commands on production.

```javascript
db.orders.insertMany([
  {
    _id: "ord-001",
    customerId: "cus-01",
    placedAt: ISODate("2026-11-20T02:06:00Z"),
    status: "PAID",
    totalAmount: NumberDecimal("100000")
  },
  {
    _id: "ord-002",
    customerId: "cus-01",
    placedAt: ISODate("2026-11-20T02:05:00Z"),
    status: "PAID",
    totalAmount: NumberDecimal("200000")
  },
  {
    _id: "ord-003",
    customerId: "cus-01",
    placedAt: ISODate("2026-11-20T02:05:00Z"),
    status: "PAID",
    totalAmount: NumberDecimal("300000")
  },
  {
    _id: "ord-004",
    customerId: "cus-01",
    placedAt: ISODate("2026-11-20T02:04:00Z"),
    status: "PAID",
    totalAmount: NumberDecimal("400000")
  },
  {
    _id: "ord-005",
    customerId: "cus-01",
    placedAt: ISODate("2026-11-20T02:03:00Z"),
    status: "PAID",
    totalAmount: NumberDecimal("500000")
  }
]);
```

Orders `ord-002` and `ord-003` share the exact same timestamp. If you sort only by `placedAt`, their relative order may not be stable enough for an element-level scroll pointer. We add `_id` as a tie-breaker key.

Check the data in `mongosh`:

```javascript
db.orders.find({ customerId: "cus-01" })
  .sort({ placedAt: -1, _id: -1 });
```

Sorted descending by `placedAt` and then descending by `_id`, the sequence starts with `ord-001`, `ord-003`, `ord-002`, `ord-004`, `ord-005`.

## 5. Defining the entity and repository

### 5.1. Entity suitable for keyset keys

Java 17+ example:

```java
import java.math.BigDecimal;
import java.time.Instant;

import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.mapping.MongoId;

@Document(collection = "orders")
public record OrderDocument(
    @MongoId(FieldType.STRING)
    String id,

    String customerId,
    Instant placedAt,
    String status,

    @Field(targetType = FieldType.DECIMAL128)
    BigDecimal totalAmount
) {}
```

`@MongoId(FieldType.STRING)` keeps `_id` consistent as a BSON string and avoids confusion with `ObjectId`. `placedAt` must be **non-null**, share the same BSON Date type across documents, and remain effectively immutable after the order is created. With keyset scrolling, missing/null sort fields can cause comparisons or cursor construction to fail.

### 5.2. Repository scrolling by placement time and ID

```java
import org.springframework.data.domain.ScrollPosition;
import org.springframework.data.domain.Window;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface OrderRepository
        extends MongoRepository<OrderDocument, String> {

    Window<OrderDocument>
    findFirst2ByCustomerIdOrderByPlacedAtDescIdDesc(
        String customerId,
        ScrollPosition position
    );
}
```

Meaning of the method:

- `findFirst2By...`: each window fetches a small count (e.g., **2**) for this exercise.
- `ByCustomerId`: filters by a single customer.
- `OrderByPlacedAtDescIdDesc`: sorts descending by timestamp then ID, establishing a total order when `_id` is unique.
- `ScrollPosition`: passes the initial or continuation position.
- `Window<OrderDocument>`: scrolling result, distinct from `Page` and `Slice`.

In production examples, you might use `findFirst20By...` or dynamic limits via a version-supported API; avoid overly large windows. Spring Data has mechanisms to append the primary key when keyset needs uniqueness guarantees; here we include ID explicitly in the sort so the contract and index are easy to inspect.

## 6. Offset scrolling with `ScrollPosition.offset()`

### 6.1. Reading window by window

```java
import org.springframework.data.domain.ScrollPosition;
import org.springframework.data.domain.Window;

public void readOrdersByOffset(
    OrderRepository repository,
    String customerId
) {
    ScrollPosition position = ScrollPosition.offset();

    while (true) {
        Window<OrderDocument> window =
            repository.findFirst2ByCustomerIdOrderByPlacedAtDescIdDesc(
                customerId, position
            );

        for (OrderDocument order : window) {
            System.out.println(order.id());
        }

        if (window.isEmpty() || window.isLast()) {
            break;
        }

        position = window.positionAt(window.size() - 1);
    }
}
```

Execution flow:

1. `ScrollPosition.offset()` starts at the beginning of the list.
2. The first window receives up to 2 documents.
3. If more data remains, retrieve `positionAt` from the last document and pass it back.
4. Repeat after each read until `isLast()` or `isEmpty()`.

`Window.isLast()` indicates the last window within the result set at query execution time; it does not promise that the collection will **never** receive new documents.

### 6.2. The off-by-one trap

The two calls below are **not equivalent**:

```java
ScrollPosition start = ScrollPosition.offset();

// Not the first position, but the position right AFTER the element at index 0.
ScrollPosition afterFirst = ScrollPosition.offset(0);
```

Because the pointer is **exclusive**, to receive the first element you must use `ScrollPosition.offset()` or `OffsetScrollPosition.initial()` in versions providing that API. If you accidentally initialize with `offset(0)`, the first order is silently skipped.

### 6.3. Large offset cost

Conceptually equivalent to a `skip` query:

```javascript
db.orders.find({ customerId: "cus-01" })
  .sort({ placedAt: -1, _id: -1 })
  .skip(100000)
  .limit(20);
```

A single request returns only 20 documents, yet MongoDB may have to traverse a large number of preceding results. Cost typically grows with `skip` depth. Offset scrolling helps by **not holding the whole result set in client RAM**, but it does not eliminate server-side skip cost.

**Choose offset** when datasets are small/moderate, or when the application needs index-based positions and prioritizes simplicity over deep-scroll optimization. When scrolling through very large sets, keyset is usually worth considering.

## 7. Keyset scrolling with `ScrollPosition.keyset()`

### 7.1. Principle

Instead of saying "skip 100,000 documents", keyset stores the **sort keys of the last seen element**, such as:

```text
placedAt = 2026-11-20T02:05:00Z
id       = ord-003
```

To find subsequent elements under descending `placedAt`, `_id`, MongoDB can filter documents **strictly after** that last key:

```javascript
// Illustrative logic, not BSON guaranteed to be generated by Spring Data.
const lastTime = ISODate("2026-11-20T02:05:00Z");
const lastId = "ord-003";

db.orders.find({
  customerId: "cus-01",
  $or: [
    { placedAt: { $lt: lastTime } },
    { placedAt: lastTime, _id: { $lt: lastId } }
  ]
})
.sort({ placedAt: -1, _id: -1 })
.limit(2);
```

Because both timestamp and ID are included, `ord-002` is still returned after `ord-003` despite sharing the same `placedAt`. Comparing only `placedAt < lastTime` would skip `ord-002`.

**Spring Data builds the keyset predicate from the sort and ID metadata**, so you do not have to write `$or` manually for a standard derived repository query. The illustrative query explains the underlying mechanism, not a byte-for-byte promise of what the framework emits across every version.

### 7.2. Calling the repository

Using the exact same method from section 5:

```java
import org.springframework.data.domain.ScrollPosition;
import org.springframework.data.domain.Window;

public void readOrdersByKeyset(
    OrderRepository repository,
    String customerId
) {
    ScrollPosition position = ScrollPosition.keyset();

    while (true) {
        Window<OrderDocument> window =
            repository.findFirst2ByCustomerIdOrderByPlacedAtDescIdDesc(
                customerId, position
            );

        for (OrderDocument order : window) {
            System.out.printf(
                "%s - %s%n", order.id(), order.placedAt()
            );
        }

        if (window.isEmpty() || window.isLast()) {
            return;
        }

        position = window.positionAt(window.size() - 1);
    }
}
```

The calling pattern is nearly identical to offset scrolling, yet the backend uses **sort keys to filter instead of skipping past preceding records**. With a suitable index and large dataset, keyset can sustain more consistent latency during deep scrolling.

### 7.3. Mandatory preconditions for keyset

- **Stable sort:** identical filter and sort order across all requests.
- **Non-null sort keys:** avoid missing/null fields; MongoDB cannot reliably build normal `$gt/$lt` continuation predicates over null/missing sort keys.
- **Unique tie-breaker key:** MongoDB `_id` is commonly used by Spring Data as the tie-breaker separating records with identical sort values.
- **Projections include all keys:** if a projection returns only `status` and omits `placedAt` or `id`, Spring Data cannot reliably construct the next keyset position; include them in the projection/DTO.
- **Consistent BSON types:** do not mix string `placedAt` with BSON Date, or String and ObjectId `_id` values across documents.
- **Matching index:** prefer an index covering the filter and sort order, and verify with `explain`.
- **Business-immutable sort fields:** if `placedAt` is edited, a document can jump across the boundary; keyset does not create a snapshot.

A frequent mistake is sorting solely by `status` when statuses change constantly and many records share the same `status`. Without adding an ID and accounting for mutations between requests, scrolling results can become unstable.

## 8. Choosing indexes for Keyset

For a query filtering by `customerId` and sorting `placedAt DESC, _id DESC`, a potentially suitable index is:

```javascript
db.orders.createIndex({
  customerId: 1,
  placedAt: -1,
  _id: -1
});
```

In keyset queries, MongoDB filters `customerId` and continues from a key tuple. A matching index can support filtering, sorting, and the continuation condition.

Verify in `mongosh`:

```javascript
db.orders.find({
  customerId: "cus-01",
  $or: [
    { placedAt: { $lt: ISODate("2026-11-20T02:05:00Z") } },
    {
      placedAt: ISODate("2026-11-20T02:05:00Z"),
      _id: { $lt: "ord-003" }
    }
  ]
})
.sort({ placedAt: -1, _id: -1 })
.limit(2)
.explain("executionStats");
```

Inspect metrics such as `totalKeysExamined`, `totalDocsExamined`, `IXSCAN`/`COLLSCAN` stages, sort costs, and execution time. Never claim a keyset query always uses an index just because the code calls `ScrollPosition.keyset()`; index selection depends on cardinality, predicates, collation, and the query planner.

**Do not create indexes solely based on an example's shape.** If your real use case filters by `status` and sorts by `placedAt`, you may need a different index. Wider indexes increase storage and write cost; measure performance on representative data.

## 9. How does `Window<T>` differ from `Page<T>`, `Slice<T>`, and Stream?

| API | Purpose | Needs total element count? | How to continue |
| --- | --- | --- | --- |
| `Page<T>` | UI needing total pages / total results | Usually requires count | `Pageable`, page number and size |
| `Slice<T>` | UI only needing to know if another page follows | Does not necessarily need count | `Pageable` and next pageable |
| `Window<T>` | Continue from a position in sorted results | No total count needed | `ScrollPosition` from the last element |
| `Stream<T>` from repository | Sequential processing, may involve open cursor | Not by default | Read from stream, **close resources** |
| `Flux<T>` from reactive repository | Non-blocking result sequence with source-dependent backpressure | Not by default | Publisher; does not turn into `Window` automatically |
| Tailable / change stream | Watching newly arriving MongoDB data/events | No | Specialized cursor or subscription |

### 9.1. Do not confuse `Window` with a server cursor

`Window<T>` holds a finite number of elements at a time. When continuing with `ScrollPosition`, the application sends **another query**. It does not keep a MongoDB cursor open across the entire traversal.

A repository `Stream<T>` can use a server cursor and must be closed with `try-with-resources` to avoid leaking resources. MongoDB change streams/tailable cursors are APIs for new data or events, not variants of `Window<T>`.

### 9.2. `Window` is not always better than `Slice` or `Page`

If an application needs to jump directly to page 17 and show a total of 1,250 orders, `Page` fits the functional requirement despite higher count/offset cost. If an application only has a "View more" button or runs a sequential export scan, `Window` is often appropriate.

Do not migrate every endpoint to scrolling just to use a newer API. Clarify user experience and consistency requirements first.

## 10. `WindowIterator`: cleaner traversal across multiple windows

Repeatedly checking `isEmpty()`, `isLast()`, and extracting positions creates boilerplate. Spring Data Commons provides `WindowIterator<T>` in versions supporting scrolling.

```java
import org.springframework.data.domain.ScrollPosition;
import org.springframework.data.support.WindowIterator;

public void processAll(
    OrderRepository repository,
    String customerId
) {
    WindowIterator<OrderDocument> iterator = WindowIterator
        .of(position ->
            repository
                .findFirst2ByCustomerIdOrderByPlacedAtDescIdDesc(
                    customerId, position
                )
        )
        .startingAt(ScrollPosition.keyset());

    while (iterator.hasNext()) {
        OrderDocument order = iterator.next();
        System.out.println("Processing: " + order.id());
    }
}
```

`WindowIterator` takes a function accepting `ScrollPosition` to fetch subsequent `Window`s automatically and presents a standard `Iterator<T>`. It is handy for sequential processing, though keep in mind:

- It does **not** wrap the queries into a transaction.
- It does **not** automatically perform idempotent retries if the job fails mid-run.
- It does **not** guarantee an immutable ordering if documents are updated, deleted, or inserted concurrently.
- For large datasets, you still must manage per-item processing speed, checkpoints, and query frequency.

Do not use `WindowIterator` in place of a partitioned parallel batch design when scale and SLAs require it. Nor should you use it as a tailable cursor watching new data forever.

## 11. Using `MongoTemplate.scroll(...)` when dynamic queries are needed

Derived repository queries are convenient for relatively fixed filters and sorts. When you need dynamic predicates, varying limits, or custom projections, use **MongoTemplate** on a version that supports scrolling.

### 11.1. Query with a starting position

```java
import org.springframework.data.domain.ScrollPosition;
import org.springframework.data.domain.Sort;
import org.springframework.data.domain.Window;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

public Window<OrderDocument> fetchWindow(
    MongoTemplate template,
    String customerId,
    ScrollPosition position
) {
    Query query = Query.query(
        Criteria.where("customerId").is(customerId)
    );

    query.with(
        Sort.by(
            Sort.Order.desc("placedAt"),
            Sort.Order.desc("id")
        )
    );
    query.limit(20);
    query.with(position);

    return template.scroll(query, OrderDocument.class);
}
```

`Query.with(position)` attaches the offset or keyset position to the query; `limit(20)` caps the documents returned per window. Passing `OrderDocument.class` lets Spring Data apply entity mapping metadata (for example, mapping `id` to `_id`).

Some versions provide an overload `scroll(query, entityType, collectionName)` to specify the collection explicitly. Check the Javadoc of your exact version before using that overload.

### 11.2. Fetching the next window

```java
ScrollPosition pos = ScrollPosition.keyset();

while (true) {
    Window<OrderDocument> window =
        fetchWindow(mongoTemplate, "cus-01", pos);

    for (OrderDocument order : window) {
        System.out.println(order.id());
    }

    if (window.isEmpty() || window.isLast()) {
        break;
    }

    pos = window.positionAt(window.size() - 1);
}
```

This is a finite query loop. When rebuilding the query on each iteration, **filters, sort, page size, and options affecting result ordering must remain identical**. Passing the same position to a query with a different sort is unsafe.

### 11.3. Projections and keyset pointers

Suppose you want a list DTO containing only `id`, `status`, `totalAmount`, and `placedAt`. With keyset scrolling, **you must retain `id` and `placedAt`** because they are the sort/positioning keys. If a projection drops `placedAt`, the framework may fail to extract a keyset position from the last element.

```java
query.fields()
    .include("id")
    .include("placedAt")
    .include("status")
    .include("totalAmount");
```

In a query carrying `OrderDocument` metadata, Java property `id` maps to `_id` in BSON. When using raw driver APIs or custom DTO mappings, verify the actual field names and avoid confusing `id` with `_id`.

With interface/record DTOs, ensure constructors/getters include **all sort keys and the ID**. You can still omit them from the HTTP response DTO while retaining them in the repository result to construct the continuation pointer.

## 12. Reactive scrolling: a window as `Mono<Window<T>>`

In Spring Data MongoDB versions supporting `ReactiveMongoTemplate` scrolling, `scroll(...)` returns `Mono<Window<T>>`. This is an important API distinction compared to assuming every reactive query returns `Flux<T>`.

```java
import org.springframework.data.domain.ScrollPosition;
import org.springframework.data.domain.Sort;
import org.springframework.data.domain.Window;
import org.springframework.data.mongodb.core.ReactiveMongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

import reactor.core.publisher.Mono;

public Mono<Window<OrderDocument>> fetchReactiveWindow(
    ReactiveMongoTemplate template,
    String customerId,
    ScrollPosition position
) {
    Query query = Query.query(
        Criteria.where("customerId").is(customerId)
    );
    query.with(
        Sort.by(
            Sort.Order.desc("placedAt"),
            Sort.Order.desc("id")
        )
    );
    query.limit(20);
    query.with(position);

    return template.scroll(query, OrderDocument.class);
}
```

In Reactor, one `Mono<Window<T>>` represents **a single window read**. If you need multiple windows, chain follow-up calls using `positionAt` and `isLast`/`isEmpty`. Ensure sequential chaining does not accidentally run out of order in parallel, never call `.block()` on a WebFlux thread, and do not emit unbounded data after a client cancels its subscription.

Conceptual example chaining multiple windows into a `Flux<Window<OrderDocument>>`:

```java
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

Flux<Window<OrderDocument>> windows =
    fetchReactiveWindow(
        reactiveMongoTemplate,
        "cus-01",
        ScrollPosition.keyset()
    ).expand(window -> {
        if (window.isEmpty() || window.isLast()) {
            return Mono.empty();
        }

        ScrollPosition next =
            window.positionAt(window.size() - 1);

        return fetchReactiveWindow(
            reactiveMongoTemplate,
            "cus-01",
            next
        );
    });
```

This pattern processes **one sequential continuation** per window. In a real application, add error handling, cancellation propagation, total element caps, checkpoints, and monitoring. Reactive execution does not eliminate query cost, create a transaction, or turn keyset scrolling into a snapshot.

For continuous unbounded streaming, consider reactive cursors or change streams per your use case rather than using `scroll` to poll for new data.

## 13. Cursor tokens for "View more" APIs

Web and mobile clients generally cannot hold a Java `ScrollPosition` instance directly across HTTP requests. You can design endpoints like:

```text
GET /orders?customerId=cus-01&limit=20
→ { items: [...], nextCursor: "opaque-token" }

GET /orders?customerId=cus-01&limit=20&cursor=opaque-token
→ { items: [...], nextCursor: "next-token-or-null" }
```

**Do not expose `ScrollPosition.toString()` directly over HTTP and assume it is a stable serialization protocol.** Define an application-controlled cursor format or a validated codec with versioning and integrity protection.

### 13.1. What should a cursor contain?

A keyset cursor typically needs the following information (shown here in an illustrative unencoded structure):

```json
{
  "v": 1,
  "mode": "keyset",
  "customerId": "cus-01",
  "sort": ["placedAt:DESC", "id:DESC"],
  "lastPlacedAt": "2026-11-20T02:05:00Z",
  "lastId": "ord-003",
  "limit": 20
}
```

This example explains how an application stores position state; **it is not JSON automatically generated by Spring Data**. From these fields, the application can reconstruct the keyset condition per its contract or restore a `KeysetScrollPosition` using the version's factory API after validating values and BSON types.

A production token should:

- Carry a **version** to support schema and sort evolution.
- Bind to the **filter/tenant/permissions** so customer A's cursor cannot be used for customer B.
- Include a signature/HMAC or tamper-resistance mechanism depending on sensitivity; base64 is not data protection.
- Avoid exposing sensitive private data in readable plaintext; consider encryption if needed.
- Bound token size, lifetime, sort order, and item limits.
- Reject malformed cursors or cursors incompatible with the current query.

Cursor pagination must never bypass authorization checks. On every request, the API must still authenticate the user and verify query permissions.

### 13.2. When should a cursor be invalidated?

If the system switches sorting from `placedAt DESC` to `paidAt DESC`, old cursors are no longer compatible. If `_id` or `placedAt` BSON types change, keys inside old tokens can no longer compare accurately. If permissions or filters change, the application may need to require reloading from the start.

Return a clear error or instruct the client to restart, **never silently continue using a different sort**.

## 14. Concurrent changes: both offset and keyset have limits

### 14.1. Offset can duplicate or skip records

Suppose window 1 returns `A, B` in a newest-first list. Before the client requests window 2, someone inserts a new document ordered ahead of `A`. If the client requests offset = 2 based on the earlier ordering, the result may include `B` again, producing duplicates.

Likewise, if a document prior to the offset is deleted, subsequent documents shift forward and an unread item can be skipped.

### 14.2. Keyset reduces position shifting, yet does not create a snapshot

Because the cursor stores `B`'s sort keys, a new document inserted **ahead of B** usually does not affect fetching documents **after B**. This is why keyset fits deep scrolling over large datasets.

However:

- An unread document whose `placedAt` changes to move ahead of the cursor can be **skipped**.
- An already-read document whose sort keys change to move behind the cursor can be **read again**.
- A deleted document will not appear in subsequent windows.
- Concurrent writes can affect ordering and windows; individual windows are not pinned inside a single MongoDB snapshot by default.

Therefore, scrolling is a **result traversal strategy**, not a guarantee that "every record in a live dataset is processed strictly once."

### 14.3. Background jobs need checkpoints and idempotency

For jobs processing millions of orders, verify:

1. Are the sort keys **immutable** or sufficiently stable?
2. According to what business rule is the checkpoint saved **after** successfully processing an item or group?
3. If the process crashes mid-window, can a rerun reprocess some documents?
4. Are output writes idempotent by `orderId`/job version?
5. Should you bound the time window—for example, scanning only orders with `placedAt < cutoff` to cap the dataset?
6. If a strict snapshot is required, can your data model/transactions/sessions support it within operational limits?

An export job might filter `placedAt <= cutoff` to avoid picking up newly created orders during traversal. Still, a cutoff **does not** prevent edits/deletes to existing documents; if an immutable snapshot is mandatory, use a dedicated sync or extraction strategy.

## 15. Offset, keyset, and pagination from MongoDB's perspective

### 15.1. Query shapes

**Offset:**

```javascript
db.orders.find({ customerId: "cus-01" })
  .sort({ placedAt: -1, _id: -1 })
  .skip(40000)
  .limit(20);
```

**Keyset:**

```javascript
db.orders.find({
  customerId: "cus-01",
  $or: [
    { placedAt: { $lt: ISODate("2026-11-20T02:05:00Z") } },
    {
      placedAt: ISODate("2026-11-20T02:05:00Z"),
      _id: { $lt: "ord-003" }
    }
  ]
})
.sort({ placedAt: -1, _id: -1 })
.limit(20);
```

These two queries illustrate the traversal patterns and are not meant to be identical ranges, as the specific cursor and offset 40000 point to different positions. The goal is to contrast **skipping N results** with **filtering by continuation keys**.

### 15.2. Suitability

| Scenario | Usually preferred | Reason |
| --- | --- | --- |
| UI wants to jump directly to page 15 | Offset `Pageable` | Page numbers are part of the UI contract |
| Chronological "View more" feed | Keyset scrolling | Deep reads with indexes, avoiding large skips |
| Small datasets, prototyping | Offset scrolling | Easy to understand and implement |
| Background job scanning many documents | Keyset with checkpoints | Resumable by keys; still requires idempotency |
| Total page count needed | `Page` | `Window` does not provide total count automatically |
| Watching real-time new events | Change stream or tailable cursor per constraints | Not a `Window` use case |
| Multi-step query/aggregation | `MongoTemplate` or dedicated aggregation | Needs pipeline control beyond derived queries |

There is no universal default for every system. Even with keyset scrolling, if the sort/filter lacks a suitable index or sort fields mutate constantly, benefits diminish and behavior becomes unpredictable.

## 16. Projections, mapping, and keyset: easy-to-miss details

### 16.1. Do not drop sort keys from DTOs

Example of a compatible projection:

```java
import java.time.Instant;

public interface OrderListView {
    String getId();
    Instant getPlacedAt();
    String getStatus();
}
```

With keyset sorting by `placedAt DESC, id DESC`, the projection must return **both `id` and `placedAt`**. Using an interface with only `getStatus()` leaves the framework without enough information to compute `positionAt` accurately from returned items.

Additionally, if a field is stored under a different BSON name via `@Field`, verify that mapping and projections preserve the exact keys. When using custom converters for timestamps or IDs, verify both BSON and Java types inside the keyset position.

### 16.2. Null or missing fields make keyset unreliable

Example documents:

```javascript
{ _id: "ord-100", customerId: "cus-01", placedAt: null }
{ _id: "ord-101", customerId: "cus-01" }
```

MongoDB compares null/missing values differently from Date values. Spring Data cannot safely reconstruct keyset position predicates when sort keys are null or missing. Therefore:

- Validate `placedAt` on write.
- Audit legacy data and migrate before enabling keyset scrolling.
- If necessary, choose another required non-null sort field.
- Write integration tests with null/missing fields to observe how the system behaves.

### 16.3. Distinguishing String IDs from ObjectIds

`@MongoId(FieldType.STRING)` defines `_id` as a BSON string. If legacy documents store BSON `ObjectId`, ID-based keyset comparisons and `_id` queries can run into type mismatches, especially when restoring cursors. Never infer solely from `String id` in Java that the entire collection uses the same BSON type.

Inspect stored types:

```javascript
db.orders.aggregate([
  {
    $group: {
      _id: {
        idType: { $type: "$_id" },
        timeType: { $type: "$placedAt" }
      },
      documents: { $sum: 1 }
    }
  },
  { $sort: { documents: -1 } }
]);
```

On large datasets, a type-audit aggregation can be expensive; run it only in an authorized environment or on a controlled copy.

## 17. Integration testing: no skips or duplicates on static data

### 17.1. Core test scenarios

Use a real test MongoDB database, not just a mocked repository. Seed multiple documents with the **exact same `placedAt`** to exercise the ID tie-breaker.

Keep the dataset **static during the test**. Expectations:

1. Window 1 contains 2 orders in the right order.
2. Window 2 continues **after** the last order of window 1.
3. The full ID sequence traversed by keyset has no skips or duplicates.
4. Offset scrolling starting with `ScrollPosition.offset()` also reads the first element.
5. `ScrollPosition.offset(0)` intentionally skips the first element due to exclusive semantics.
6. The final window sets `isLast()` accurately for the query's result set.
7. DTOs used with keyset retain all required sort keys.
8. Sorts missing tie-breakers or encountering null fields are caught and resolved before deployment.

### 17.2. Keyset test example

```java
import static org.assertj.core.api.Assertions.assertThat;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.data.domain.ScrollPosition;
import org.springframework.data.domain.Window;

@DataMongoTest
class OrderScrollingIntegrationTest {

    @Autowired OrderRepository orders;

    @Test
    void keysetScrollVisitsEveryOrderOnceWithDuplicateTime() {
        String customer = "cus-scroll-test";
        Instant time = Instant.parse("2026-11-20T02:05:00Z");

        for (int i = 1; i <= 5; i++) {
            orders.insert(new OrderDocument(
                "scroll-" + i,
                customer,
                time,
                "PAID",
                new BigDecimal("100000")
            ));
        }

        ScrollPosition position = ScrollPosition.keyset();
        List<String> ids = new ArrayList<>();

        while (true) {
            Window<OrderDocument> window =
                orders.findFirst2ByCustomerIdOrderByPlacedAtDescIdDesc(
                    customer, position
                );

            for (OrderDocument order : window) {
                ids.add(order.id());
            }

            if (window.isEmpty() || window.isLast()) {
                break;
            }

            position = window.positionAt(window.size() - 1);
        }

        assertThat(ids)
            .containsExactly(
                "scroll-5", "scroll-4", "scroll-3",
                "scroll-2", "scroll-1"
            );
    }
}
```

This test assumes a configured test database with no colliding IDs from previous runs. If running repeatedly against the same database, clean up test records or use unique namespaces/IDs. This is a sample test **not yet executed in a project**; it illustrates verifying order, boundaries, and final output.

### 17.3. Testing concurrent mutation scenarios

Beyond static-data tests, write tests that perform:

- Inserting a new order ahead of the cursor after reading the first window.
- Deleting an already-read or unread order.
- Editing `placedAt` of an unread order so its position changes.
- Comparing results between offset and keyset, documenting the differences.
- Inserting a document with `placedAt=null` in a separate test to verify how the system rejects or handles errors.

There is no "single universally right answer" for every concurrent write pattern; expected behavior must align with your product contract, consistency guarantees, and data model.

## 18. Diagnostics: query plans, load, and consistency

### 18.1. Inspecting `explain("executionStats")`

Before concluding keyset is faster, compare equivalent queries on a sufficiently large dataset:

```javascript
db.orders.getIndexes();

db.orders.find({ customerId: "cus-01" })
  .sort({ placedAt: -1, _id: -1 })
  .skip(10000)
  .limit(20)
  .explain("executionStats");
```

Then run the keyset query using a cursor near an equivalent depth. Measure:

| Metric | Question |
| --- | --- |
| `totalKeysExamined` | Are too many index keys being traversed? |
| `totalDocsExamined` | Are unnecessary documents read before returning the window? |
| `IXSCAN`/`COLLSCAN` | Is the query using an index or scanning the whole collection? |
| Sort stage | Is an in-memory sort running outside the index? |
| Query duration | Does latency spike when scrolling deep? |
| Request count for full scan | Is the window size too small or too large? |
| Bytes received and mapping time | Do projections meaningfully cut transferred data? |
| Duplicates/skips under concurrent writes | Do the sort keys and cursor contract fit? |

A well-chosen index can keep keyset query cost roughly proportional to window size in many situations, though never promise constant complexity across every query or cluster topology.

### 18.2. Timeouts, errors, and retries

If the query for window 10 fails:

- Do not advance the cursor to a new position before confirming that the current window's data was processed successfully per business requirements.
- For jobs with side effects, processing operations must be **idempotent** because retries can re-read elements.
- Distinguish transient timeouts from invalid cursor tokens or mismatched sort field types.
- Selectively log scroll type (offset/keyset), window size, index plan, and timing, without logging sensitive tokens or IDs arbitrarily.
- Cap retry attempts and use backoff when appropriate; avoid infinite loops if a sort/keyset query is broken.

In MongoDB, transactions and read concerns can help certain multi-operation consistency problems, yet you should never open **one long transaction spanning millions of records** just to scroll data. Long transactions increase resource pressure and conflict risk, and scrolling itself is non-transactional.

## 19. Common mistakes

**Mistake 1: starting with `ScrollPosition.offset(0)`.** That points past element index 0 and can skip the first item. Use `ScrollPosition.offset()` or `OffsetScrollPosition.initial()`.

**Mistake 2: omitting a sort.** Without a stable ordering, positions between reads are unreliable; keyset scrolling requires explicit sort keys.

**Mistake 3: sorting only by `placedAt` when timestamps tie.** A tie-breaker such as ID is needed. Spring Data also has mechanisms to append the ID to ensure keyset uniqueness.

**Mistake 4: keyset on `null` or missing fields.** Comparison predicates cannot resume reliably; validate/migrate data or choose another key.

**Mistake 5: projections omitting `id` or sort fields.** The framework cannot construct the next keyset position if returned items lack the needed keys.

**Mistake 6: exposing `ScrollPosition.toString()` externally as a cursor token.** There is no stability or security guarantee for its serialization format; use an application-controlled format.

**Mistake 7: treating `Window<T>` as a continuously open MongoDB stream.** Each window is a bounded result batch typically backed by a fresh query on continuation; it is neither a tailable cursor nor a change stream.

**Mistake 8: assuming keyset provides an immutable snapshot.** Concurrent updates can move documents across position boundaries.

**Mistake 9: using Scroll APIs on Spring Data MongoDB 4.0 without checking.** APIs such as `MongoTemplate.scroll(...)` were introduced in 4.1; older dependencies require compatible alternatives.

**Mistake 10: passing a cursor from one filter into a different filter.** A pointer is only meaningful with the same filter, sort, and schema; bind or revalidate all parameters against the token.

**Mistake 11: using extremely deep offset scrolling and expecting cheap queries.** Even though the client receives small windows, the server may still have to skip many results.

**Mistake 12: letting clients pass arbitrary window sizes.** Bound window sizes sensibly to prevent huge queries/object allocations and protect server resources.

## 20. Practice exercises and pre-deployment checklist

### 20.1. Practice exercises

1. Seed 5–10 order documents; deliberately give 2–3 documents the exact same `placedAt`.
2. Create `OrderRepository` with `Window<OrderDocument> findFirst2ByCustomerIdOrderByPlacedAtDescIdDesc(..., ScrollPosition)`.
3. Read all data using `ScrollPosition.offset()` and observe each window's position.
4. Test `ScrollPosition.offset(0)` separately to explain why the first element is skipped.
5. Switch to `ScrollPosition.keyset()` and compare results and query counts.
6. Use `WindowIterator` to traverse sequentially without writing the `isLast()` loop manually.
7. Build a `Query` with `Sort`, `limit`, and `with(position)` and invoke `MongoTemplate.scroll(...)`.
8. Create `{customerId:1, placedAt:-1, _id:-1}` and compare deep-offset vs. keyset plans using `explain`.
9. Test a projection dropping `placedAt` to observe keyset key errors; fix the DTO/projection.
10. Insert/delete/update records between reads and describe the consistency limitations.
11. Write an integration test verifying every ID is visited strictly once on **static data**.
12. If using reactive stacks, try `ReactiveMongoTemplate.scroll(...)` and inspect `Mono<Window<T>>`.

### 20.2. Checklist

| Check | Question to answer |
| --- | --- |
| Version | Are `ScrollPosition`/`Window` and MongoDB `scroll` APIs present in your actual dependencies? |
| Use case | Do users need page N, total count, or just sequential continuation? |
| Pointer mode | Offset or keyset? What is the deep-scroll cost? |
| Initialization | Are you using the **initial position** rather than mistakenly calling `offset(0)`? |
| Sort | Is the sort stable with an ID tie-breaker? |
| Sort fields | Non-null, non-missing, consistent BSON types, and low-churn? |
| Projection | Does it return all sort keys and ID required for keyset? |
| Index | Do filter, sort, and continuation predicates have a matching index? |
| Cursor token | Versioned, signed, bound to filter/tenant, and bounded in lifetime? |
| Access control | Are authentication and authorization enforced on every read? |
| Concurrent writes | Are duplicates/skips acceptable when data mutates? |
| Background jobs | Do you have checkpoints, retries, and idempotency? |
| Reactive | Using `Mono<Window<T>>`/context properly without blocking the event loop? |
| Testing | Tested across multiple windows, tied keys, nulls, bad cursors, and concurrent mutations? |
| Performance | Measured `explain`, keys/docs examined, latency, and bandwidth? |

**Conclusion:** `Window<T>` is the result unit, `ScrollPosition` is the continuation point, and **offset/keyset** are two distinct execution strategies. Starting from **Spring Data Commons 3.1 / Spring Data MongoDB 4.1**, the scrolling APIs enable windowed reads with repositories or `MongoTemplate`, including reactive templates where supported. **Offset** is simple yet can become costly on deep scrolls; **keyset** leverages sorting and indexes yet requires non-null keys, complete projections, valid pointers, and acceptance of concurrent-mutation limits. For reliable operation, verify your exact library version, design indexes/cursors/authorization explicitly, and test continuation across multiple consecutive windows.
