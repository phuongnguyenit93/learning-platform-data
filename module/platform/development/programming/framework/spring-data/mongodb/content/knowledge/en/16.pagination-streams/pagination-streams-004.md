# Slice and Determining Whether More Data Follows

## 1. The pagination problem when total record count is not needed

In the **Pagination and Streams** chapter of **Spring Data MongoDB**, many screens only need to display a set of results and answer the question: **"Is there more data to load?"** For example, a product catalog page has a *View more* button; each time, the user requests 10 active products.

If 23 matching products exist, the desired experience is:

| Request | Page size | Items returned | More data follows? |
|---|---:|---:|---|
| Page 0 | 10 | 10 | Yes |
| Page 1 | 10 | 10 | Yes |
| Page 2 | 10 | 3 | No |
| Page 3 (beyond current range) | 10 | 0 | No |

To build this UI, the client **does not have to know the total document count or total page count**. Spring Data provides the `Slice<T>` return type for this situation. `Slice` is a **loaded chunk of results** accompanied by information about the current page and whether a next page exists, rather than a result with a total count like `Page<T>`.

Lesson objectives:

1. Understand the exact meaning of `Slice`, `hasNext()`, `hasPrevious()`, and their limitations.
2. Write `MongoRepository` methods returning `Slice<T>` with `Pageable` and stable sorting.
3. Understand the **page size + 1 element** query technique to detect whether more data follows without counting everything.
4. Build an API returning a list and next-page information without exposing entity internals.
5. Analyze `skip/limit` costs, the problem of data changing between pages, and when to switch to keyset/cursor pagination.
6. Test first-page, last-page, empty-page, tied sort-key scenarios, and actual MongoDB queries.

> The examples use Java 17+, Spring Boot 3.x, and Spring Data MongoDB 4.x. Exact `Slice`/`Page` implementation behavior and BSON commands can vary by version; pagination principles should be verified against your project's MongoDB and driver versions.

## 2. Distinguishing List, Slice, Page, Stream, and Window

| Return type | Has current list? | Has `hasNext()`? | Has total element count? | Key characteristics |
|---|---|---|---|---|
| `List<T>` | Yes | Not by contract | No | Just the results; the application determines whether a next page exists |
| `Slice<T>` | Yes | Yes | No | Ideal for "View more" buttons and pages not needing total count |
| `Page<T>` | Yes | Yes | Yes, via `getTotalElements()` | Ideal for UIs needing page numbers or total record counts |
| `Stream<T>` | Element-by-element stream | Not per `Slice` semantics | No | May involve open cursors/resources; must be closed properly |
| `Window<T>` and scrolling API | A window of results | Has window-level continuation indicators | No | Can support offset/keyset scrolling if API and version allow |

`Page<T>` extends slice semantics and adds total metadata, but a query returning `Page` may have to run an extra count operation. The framework sometimes optimizes or skips the count if it has enough information to deduce the total, so **never claim every `Page` always runs exactly two queries**.

`Slice<T>` does not have `getTotalElements()` or `getTotalPages()`. Useful calls include:

~~~java
Slice<CatalogProduct> slice = repository.findByStatus("ACTIVE", pageable);

List<CatalogProduct> currentItems = slice.getContent();
boolean hasMore = slice.hasNext();
boolean hasPrevious = slice.hasPrevious();
int currentPage = slice.getNumber();      // 0-based
int requestedSize = slice.getSize();
int itemsInSlice = slice.getNumberOfElements();
Sort appliedSort = slice.getSort();
~~~

The snippet assumes `repository` and `pageable` exist as in section 3; import `org.springframework.data.domain.Slice`, `Sort`, and `java.util.List`. `Slice` already holds the current page's data—it is not an iterator keeping a server cursor open across multiple HTTP requests.

### Understanding hasNext accurately

- `hasNext() == true`: at query time, there was evidence that at least one record exists after the **returned result chunk**, under the query's filter and ordering.
- `hasNext() == false`: no additional elements were found after the current chunk in that query. It is **not a guarantee** that new data will not be added to the collection later.
- `hasPrevious()`: indicates whether a previous page is possible based on page index, **not a count or re-check confirming that previous-page documents still exist**.
- `getNumberOfElements()` is the number of elements **currently returned**, distinct from the total count of records matching the filter.

After reading page 2 and seeing `hasNext() == false`, the UI can hide the *View more* button. If a new product is inserted one second later, the UI will not automatically know; the user needs to refresh or use a separate update mechanism.

## 3. Java model and MongoRepository returning Slice

To run the examples, the application uses the `spring-boot-starter-data-mongodb` starter, configures a MongoDB URI, and places classes under packages scanned by Spring Boot. Data is stored in the `catalog_products` collection.

**CatalogProduct.java**

~~~java
package com.example.catalog;

import java.time.Instant;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.mapping.MongoId;

@Document(collection = "catalog_products")
public record CatalogProduct(
        @MongoId(FieldType.STRING) String id,
        String title,
        String status,
        long priceVnd,
        @Field("created_at") Instant createdAt) {
}
~~~

`@MongoId(FieldType.STRING)` preserves the ID as a BSON String and maps the Java property `id` to `_id`. `@Field("created_at")` maps the property `createdAt` to the BSON field `created_at`. We assume `createdAt` is non-null and not mutated during a product's lifecycle; this makes it a **less volatile sort key** than `updatedAt`.

Example BSON (omitting `_class` type metadata):

~~~json
{
  "_id": "p-023",
  "title": "Insulated Flask",
  "status": "ACTIVE",
  "priceVnd": 129000,
  "created_at": { "$date": "2026-11-20T08:00:00Z" }
}
~~~

**CatalogProductRepository.java**

~~~java
package com.example.catalog;

import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Slice;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface CatalogProductRepository
        extends MongoRepository<CatalogProduct, String> {

    Slice<CatalogProduct> findByStatus(
            String status, Pageable pageable);
}
~~~

This is a derived query: `findByStatus` filters on the `status` property; the `Pageable` parameter specifies **offset, limit, and sort**. When the return type is `Slice<CatalogProduct>`, Spring Data uses the query results to determine `hasNext` **without exposing a `Page` total count contract**.

### 3.1. Calling the repository with Pageable

~~~java
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Slice;
import org.springframework.data.domain.Sort;

Pageable pageZero = PageRequest.of(
        0,
        10,
        Sort.by(
                Sort.Order.desc("createdAt"),
                Sort.Order.desc("id")));

Slice<CatalogProduct> first =
        repository.findByStatus("ACTIVE", pageZero);

boolean hasMore = first.hasNext();
~~~

`PageRequest.of(0, 10, ...)` requests the first page (**0-based**) with size 10. `Sort` uses **Java property names**: `createdAt` maps to `created_at`, and `id` maps to `_id` in MongoDB.

Why sort by two fields?

- `createdAt DESC` prioritizes the most recently created products.
- `id DESC` acts as a *tie-breaker* when multiple products share the same `createdAt`, producing a deterministic order because `_id` is unique within the collection.

If you sort only by `createdAt` and hundreds of documents share the same timestamp, the order within that tied group is **not guaranteed** across queries. Paginating over an indeterminate order can duplicate or skip items even when data has not changed.

### 3.2. Sorting does not replace a snapshot

Even with a total order over (`createdAt`, `id`), **offset pagination does not create an immutable snapshot across requests**. If a new product appears ahead of the already-read position, data at the next offset can shift. Likewise, deleting a product on an earlier page can cause an element to be skipped.

Thus there are two separate levels of guarantees:

1. **Stable ordering when data is unchanged:** provide a unique tie-breaker.
2. **No duplicates/skips when data mutates:** requires an appropriate scrolling model, checkpoint/snapshot, or additional business mechanism—not merely adding `OrderBy`.

## 4. The pageSize + 1 fetch mechanism for hasNext

Suppose `pageSize = 10`. A common technique for building a `Slice` is to query for **at most 11 documents**:

~~~mermaid
flowchart TD
    A["Filter + sort + offset"] --> B["Fetch up to pageSize + 1 records"]
    B --> C{"More than pageSize records?"}
    C -->|"Yes"| D["Return first 10 records, hasNext = true"]
    C -->|"No"| E["Return all records, hasNext = false"]
    D --> F["No total count needed"]
    E --> F
~~~

When 11 documents are fetched, the 11th record is **used solely to detect whether a next page exists** and is excluded from the current page's response. If only 10 documents are returned, there is no evidence of a next page at read time. This is the core implementation pattern for `Slice`; the exact BSON commands and optimization details may vary across Spring Data versions.

With the 23-document example:

- Query page 0: `skip(0)`, fetch up to 11; return 10, `hasNext = true`.
- Query page 1: `skip(10)`, fetch up to 11; return 10, `hasNext = true`.
- Query page 2: `skip(20)`, fetch up to 11; only 3 exist; return 3, `hasNext = false`.

**Why not fetch just 10?** If you return 10, you cannot tell from that set alone whether the collection has exactly 10 matching records (done) or 11 or more (another page exists). Fetching **one** extra record is a sufficient signal when the query uses consistent filters and sorting.

`Page` usually needs a total count to calculate total pages. `Slice` intentionally omits that metadata, fitting UIs with only *Previous*/*Next*, infinite scroll, or a *View more* button.

## 5. Building an API response from Slice

Avoid returning Spring Data's `Slice<CatalogProduct>` directly and coupling your API to the framework's default JSON serialization. An API is more stable when you explicitly define its payload and expose only needed fields.

**ProductCard.java**

~~~java
package com.example.catalog;

public record ProductCard(
        String id, String title, long priceVnd) {
}
~~~

**ProductSliceResponse.java**

~~~java
package com.example.catalog;

import java.util.List;

public record ProductSliceResponse(
        List<ProductCard> items,
        int page,
        int size,
        boolean hasNext,
        Integer nextPage) {
}
~~~

**ProductBrowseService.java**

~~~java
package com.example.catalog;

import java.util.List;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Slice;
import org.springframework.data.domain.Sort;
import org.springframework.stereotype.Service;

@Service
public class ProductBrowseService {
    private final CatalogProductRepository products;

    public ProductBrowseService(CatalogProductRepository products) {
        this.products = products;
    }

    public ProductSliceResponse listActive(int page, int size) {
        if (page < 0 || page == Integer.MAX_VALUE
                || size < 1 || size > 100) {
            throw new IllegalArgumentException("Invalid page or size");
        }

        Sort stableSort = Sort.by(
                Sort.Order.desc("createdAt"),
                Sort.Order.desc("id"));
        Pageable pageable = PageRequest.of(page, size, stableSort);

        Slice<CatalogProduct> slice =
                products.findByStatus("ACTIVE", pageable);

        List<ProductCard> cards = slice.map(p ->
                new ProductCard(p.id(), p.title(), p.priceVnd()))
                .getContent();

        boolean more = slice.hasNext();
        return new ProductSliceResponse(
                cards,
                slice.getNumber(),
                slice.getSize(),
                more,
                more ? page + 1 : null);
    }
}
~~~

In a public API, map parameter validation errors to an appropriate response (such as HTTP 400); the `size <= 100` limit here is an **example policy**, not a hard requirement of Spring Data. Depending on the product, you can also cap maximum offset and request frequency.

`slice.map(...)` transforms the **already-fetched content** into DTOs while preserving slice metadata. It **reduces fields exposed in the API**, not automatically proving that the MongoDB query loaded only `id/title/priceVnd`. If documents have large payloads, apply query-level projections or repository DTO projections and inspect the driver commands.

Example page payload:

~~~json
{
  "items": [
    { "id": "p-023", "title": "Insulated Flask", "priceVnd": 129000 },
    { "id": "p-022", "title": "Notebook", "priceVnd": 45000 }
  ],
  "page": 0,
  "size": 2,
  "hasNext": true,
  "nextPage": 1
}
~~~

The response example above assumes `size = 2`; real pages may contain different products depending on data and sorting. When `hasNext = false`, `nextPage` is `null`.

### 5.1. Using Slice.nextPageable()

Spring Data's `Slice` provides methods such as `nextPageable()` to obtain the next pagination request when more data exists. Inside a service or internal processing, check `hasNext()` first before requesting the next page; at an HTTP endpoint, typically return metadata/URLs rather than sending the framework's `Pageable` object to clients.

Do not mistake `nextPageable` for a snapshot cursor key. It mainly represents the **next offset-based page position** under the current strategy.

## 6. Building a Slice manually with MongoTemplate

When filters are constructed dynamically, `MongoTemplate` is useful for controlling filter, sort, and limits in detail. The example below implements the **pageSize+1** pattern explicitly and constructs `SliceImpl`.

~~~java
package com.example.catalog;

import java.util.List;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Slice;
import org.springframework.data.domain.SliceImpl;
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.stereotype.Service;

@Service
public class ProductSliceQueryService {
    private final MongoTemplate mongo;

    public ProductSliceQueryService(MongoTemplate mongo) {
        this.mongo = mongo;
    }

    public Slice<CatalogProduct> byStatus(
            String status, int page, int size) {
        if (page < 0 || size < 1 || size > 100) {
            throw new IllegalArgumentException("Invalid pagination");
        }

        Sort sort = Sort.by(
                Sort.Order.desc("createdAt"),
                Sort.Order.desc("id"));
        Pageable pageable = PageRequest.of(page, size, sort);

        Query query = Query.query(Criteria.where("status").is(status));
        query.with(sort);
        query.skip(pageable.getOffset());
        query.limit(size + 1);

        List<CatalogProduct> found =
                mongo.find(query, CatalogProduct.class);

        boolean hasNext = found.size() > size;
        List<CatalogProduct> current = List.copyOf(
                found.subList(0, Math.min(size, found.size())));
        return new SliceImpl<>(current, pageable, hasNext);
    }
}
~~~

Explanation:

1. `Query.query(Criteria.where("status").is(status))` creates the filter using Java properties.
2. `query.with(sort)` sets the sort explicitly; using the entity class, Spring Data translates `createdAt` to `created_at` and `id` to `_id`.
3. `query.skip(pageable.getOffset())` skips `page * size` documents in sort order.
4. `query.limit(size + 1)` fetches one extra document to determine `hasNext`.
5. `SliceImpl<>(current, pageable, hasNext)` wraps the result without running a count.

This is an **illustrative implementation** assuming no extra filtering happens after fetching. If you load 11 records and then drop some in Java before checking `hasNext`, the result will be wrong. Predicates defining the result set must be applied **inside the MongoDB query** for the extra-element check to stay accurate.

### Illustrative MongoDB command

~~~javascript
db.catalog_products.find({ status: "ACTIVE" })
  .sort({ created_at: -1, _id: -1 })
  .skip(10)
  .limit(11);
~~~

This command is logically equivalent to `page = 1`, `size = 10`. The driver sends a `find` command containing `filter`, `sort`, `skip`, and `limit` rather than the shell syntax above.

## 7. Indexes and offset pagination performance

For queries frequently filtering on `status` and sorting by (`createdAt DESC`, `id DESC`), a candidate compound index is:

~~~javascript
db.catalog_products.createIndex(
  { status: 1, created_at: -1, _id: -1 },
  { name: "idx_status_created_id" }
);
~~~

This index supports the filter and the requested result order; still verify with `explain("executionStats")` on representative data. Queries with `status` filters and matching sorts can leverage the index depending on conditions and query shape.

Example:

~~~javascript
db.catalog_products.find({ status: "ACTIVE" })
  .sort({ created_at: -1, _id: -1 })
  .skip(50000)
  .limit(11)
  .explain("executionStats");
~~~

**`Slice` does not eliminate `skip` cost.** With large offsets, the database still has to scan/skip many entries before returning the next page. Even with a suitable index and no full collection count, page 5,000 can still consume substantial resources.

Metrics to measure:

- `totalKeysExamined`, `totalDocsExamined`, and execution time on early pages versus deep pages.
- Number of MongoDB commands, elements actually loaded (`size+1`), and payload size.
- `p95`/`p99` latency under realistic load, connection pool usage, read preference, and sort stages.
- Which index was chosen, write overhead of adding a compound index, and collection size.

If the UI scrolls continuously across thousands of pages, consider **keyset/cursor scrolling** rather than allowing unbounded offsets. If direct access to "page 500" and total page counts are needed, `Page`/offset can still fit moderate datasets, provided you set performance bounds.

## 8. Why can offset pagination duplicate or drop items?

Suppose sorting newest first, with page size 2:

~~~text
Before requesting page 0: [D, C, B, A]
Page 0 (skip 0, limit 2): [D, C]

Then a new record E newer than D arrives:
New list: [E, D, C, B, A]

Page 1 (skip 2, limit 2): [C, B]
~~~

Result: **C appears twice**. If a document is deleted or changes sort position, an item can be **skipped** instead. `Slice.hasNext` only detects that an item existed after the offset at query time; it does not prevent items from shifting between requests.

Other scenarios:

- Updating `status` from `ACTIVE` to `INACTIVE` shrinks the matching set.
- If sorting by `updatedAt`, an older record that gets updated can jump to the top of the list.
- A single timestamp cannot distinguish tied records; without an `_id` tie-breaker, queries can return different pages even when no inserts/deletes occur.
- Reading from secondaries with non-primary read preferences can observe replication lag.

Therefore, claiming "using `Slice` prevents duplicates and missed records" is **incorrect**.

### How to reduce the risk

1. Use a **total, deterministic sort** with low-churn fields and a unique ID.
2. If the use case traverses frequently mutating sets, prefer a keyset cursor.
3. For batch jobs that must process every record reliably, use checkpoints/idempotency and an appropriate watermark or snapshot design rather than using a large offset as a checkpoint.
4. For regular endpoints, accept that data may change between requests, allow refreshes, and document those semantics clearly in the API.

## 9. When should you use keyset/cursor instead of offset Slice?

**Keyset pagination** remembers the sort keys of the last displayed item and queries for records **coming after those keys**. It can still use the `size + 1` and `hasNext` idea, but **it does not increment page numbers or skip**.

Suppose sort is `createdAt DESC, id DESC`. The last item on the previous page has:

~~~text
last.createdAt = 2026-11-20T08:00:00Z
last.id        = p-011
~~~

The condition for "after `last`" is:

~~~javascript
db.catalog_products.find({
  status: "ACTIVE",
  $or: [
    { created_at: { $lt: ISODate("2026-11-20T08:00:00Z") } },
    {
      created_at: ISODate("2026-11-20T08:00:00Z"),
      _id: { $lt: "p-011" }
    }
  ]
})
.sort({ created_at: -1, _id: -1 })
.limit(11);
~~~

We use `$lt` because both keys are sorted **descending**. For ascending sorts, the continuation comparisons change accordingly. These conditions must match the ID collation/data type and index. Because `_id` in the example is a BSON String, string comparison follows the chosen sort order; adjust if using another type.

With `MongoTemplate`, you can express the after-cursor filter using `Criteria`:

~~~java
import java.time.Instant;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.domain.Sort;

public Query afterCursor(Instant lastCreatedAt, String lastId, int size) {
    if (lastCreatedAt == null || lastId == null
            || lastId.isBlank() || size < 1 || size > 100) {
        throw new IllegalArgumentException("Invalid cursor");
    }

    Criteria after = new Criteria().orOperator(
            Criteria.where("createdAt").lt(lastCreatedAt),
            new Criteria().andOperator(
                    Criteria.where("createdAt").is(lastCreatedAt),
                    Criteria.where("id").lt(lastId)));

    Criteria filter = new Criteria().andOperator(
            Criteria.where("status").is("ACTIVE"), after);

    Query query = Query.query(filter);
    query.with(Sort.by(
            Sort.Order.desc("createdAt"),
            Sort.Order.desc("id")));
    query.limit(size + 1);
    return query;
}
~~~

This is a query-builder method, used afterward with `mongo.find(query, CatalogProduct.class)` and the `size+1` slicing pattern from section 6. When calling `MongoTemplate` with the entity type, Spring Data maps `createdAt`/`id` to `created_at`/`_id`.

**Limitations of keyset:** it eliminates skip cost and prevents new inserts *ahead of the cursor* from shifting offsets, yet **it does not create a transactional snapshot**. If already-read records have their sort keys mutated or filter membership changes, consistency semantics still need to be defined. Never accept an unvalidated raw cursor that clients can tamper with: production tokens should carry a version/filter scope, verify tenant/permissions, include expiration if appropriate, and use tamper protection (such as signing).

In Spring Data versions that support the **scrolling API** with `ScrollPosition` and `Window<T>`, you can use that abstraction instead of rolling your own cursor; check Spring Data MongoDB's exact support and combine with the right offset or keyset position. `Window` is distinct from `Slice`—do not assume changing the return type alone turns offset pagination into keyset pagination.

## 10. Slice is not a streaming cursor

The chapter name *Pagination and Streams* might lead learners to confuse `Slice<T>` with Java `Stream<T>`:

| Aspect | `Slice<T>` | `Stream<T>` / server cursor |
|---|---|---|
| Form | A materialized page result set | Sequential iteration as data is fetched |
| Lifecycle | Finishes the page query; response holds one chunk | Can hold resources/cursors open during traversal |
| Page `hasNext` | Has `hasNext()` metadata | Not a contract for "next HTTP page" |
| Closing resources | Do not pass `Slice` around as a closeable cursor | Stream/cursor must be closed properly, usually `try-with-resources` |
| Typical use case | List APIs, *View more* buttons | Large batch processing, controlled exports |

A Java `Stream` from a repository may use MongoDB cursor infrastructure; do not store a stream as a service field for uncontrolled long-running processing. `Stream` does not automatically handle retries, disconnects, checkpoints, or ordering.

With Reactive MongoDB, common APIs return `Flux<T>`/`Mono<T>` and use backpressure in the processing pipeline, yet **reactive does not automatically provide Slice metadata**. If you need a response with `hasNext`, query with `limit(size + 1)`, collect a bounded chunk, and compute the metadata.

Illustrative example in a reactive service using `ReactiveMongoTemplate reactiveMongo`:

~~~java
import java.util.List;
import reactor.core.publisher.Mono;
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.ReactiveMongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

public Mono<Boolean> hasMoreAfterFirstPage(
        ReactiveMongoTemplate reactiveMongo, int size) {
    if (size < 1 || size > 100) {
        return Mono.error(
                new IllegalArgumentException("Invalid size"));
    }

    Query query = Query.query(Criteria.where("status").is("ACTIVE"));
    query.with(Sort.by(
            Sort.Order.desc("createdAt"), Sort.Order.desc("id")));
    query.limit(size + 1);

    return reactiveMongo.find(query, CatalogProduct.class)
            .collectList()
            .map(items -> items.size() > size);
}
~~~

This only illustrates **computing the `hasMore` flag**, not a full pagination API; to return the items too, slice the `size+1` list and construct the response DTO. Still, it demonstrates that you do not need `.block()` to turn a `Flux` into a bounded chunk; `collectList()` produces `Mono<List<T>>` inside the reactive pipeline. Never call `collectList()` on an **unbounded** query when the data can be very large.

## 11. Testing Slice against real MongoDB

Testing with a mocked repository only proves the service handles `hasNext` as coded; it does not verify how Spring Data MongoDB applies skip/sort/limit. Include integration tests against a real MongoDB instance, such as via Testcontainers. `@DataMongoTest` focuses on Spring Boot 3.x Mongo mapping and repositories, but **does not start a MongoDB server on its own**.

### 11.1. Testing 23 products, pageSize = 10

~~~java
package com.example.catalog;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Instant;
import java.util.stream.IntStream;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Slice;
import org.springframework.data.domain.Sort;

@DataMongoTest
class CatalogProductSliceTest {
    @Autowired
    CatalogProductRepository products;

    private Pageable page(int number) {
        return PageRequest.of(number, 10,
                Sort.by(Sort.Order.desc("createdAt"),
                        Sort.Order.desc("id")));
    }

    @BeforeEach
    void seedData() {
        products.deleteAll();
        products.saveAll(IntStream.rangeClosed(1, 23)
                .mapToObj(n -> new CatalogProduct(
                        "p-" + String.format("%03d", n),
                        "Product " + n,
                        "ACTIVE",
                        100_000L + n,
                        Instant.parse("2026-11-20T08:00:00Z")))
                .toList());
    }

    @Test
    void detectsLastSliceWithoutTotalCount() {
        Slice<CatalogProduct> first =
                products.findByStatus("ACTIVE", page(0));
        Slice<CatalogProduct> second =
                products.findByStatus("ACTIVE", page(1));
        Slice<CatalogProduct> third =
                products.findByStatus("ACTIVE", page(2));
        Slice<CatalogProduct> outside =
                products.findByStatus("ACTIVE", page(3));

        assertThat(first.getNumberOfElements()).isEqualTo(10);
        assertThat(first.hasNext()).isTrue();
        assertThat(first.hasPrevious()).isFalse();
        assertThat(first.getContent().get(0).id()).isEqualTo("p-023");

        assertThat(second.getNumberOfElements()).isEqualTo(10);
        assertThat(second.hasNext()).isTrue();
        assertThat(second.hasPrevious()).isTrue();
        assertThat(second.getContent().get(0).id()).isEqualTo("p-013");

        assertThat(third.getNumberOfElements()).isEqualTo(3);
        assertThat(third.hasNext()).isFalse();
        assertThat(third.getContent().get(0).id()).isEqualTo("p-003");

        assertThat(outside.getContent()).isEmpty();
        assertThat(outside.hasNext()).isFalse();
    }
}
~~~

All records share the same `createdAt` to test the **`id` tie-breaker**. Because IDs are stored as BSON Strings formatted from `p-001` to `p-023`, sorting descending by `_id` yields a deterministic sequence.

Do not call `deleteAll()` on a database shared across parallel tests. Use an isolated database or dedicated test data namespaces; this test is a structural example.

### 11.2. Edge cases to verify

| Matching items | pageSize | Current page elements | Expected `hasNext` |
|---:|---:|---:|---|
| 0 | 10 | 0 | `false` |
| 1 | 10 | 1 | `false` |
| 10 | 10 | 10 | `false` |
| 11 | 10 | 10 | `true` on page 0 |
| 20 | 10 | 10 | `true` on page 0, `false` on page 1 |
| 23 | 10 | 3 | `false` on page 2 |

Specifically, **10 records matching pageSize exactly** differs from 11 records: without the "plus one record", looking only at the first page's size cannot determine `hasNext`.

Additional tests:

1. Filter `status = ACTIVE` excludes products with other statuses.
2. Multiple products with the same `createdAt` neither duplicate nor skip **when the dataset is static** thanks to the `id` tie-breaker.
3. Interleave updates/inserts between offset loads to observe record shifting; do not mark this as a `Slice` bug.
4. Boundary validation rejects `page < 0`, `size = 0`, or oversized `size`.
5. DTO-projected queries do not leak internal fields and do not load overly large documents unnecessarily.
6. Test behavior after deleting records on earlier pages and after the cursor; use those observations to decide between offset and keyset pagination.

## 12. Observing BSON commands, counts, and query plans

To see what the repository actually sends, use the MongoDB Java Driver's `CommandListener` and `CommandStartedEvent` in integration tests, or the MongoDB profiler where permitted. A `find` command looks conceptually like:

~~~json
{
  "find": "catalog_products",
  "filter": { "status": "ACTIVE" },
  "sort": { "created_at": -1, "_id": -1 },
  "skip": 10,
  "limit": 11
}
~~~

This example is **not a byte-for-byte guarantee** of the BSON command generated by Spring Data. The driver/framework may use different command fields, limits, cursor batch sizes, or equivalent structures; base tests on observed semantics.

Things to verify:

- `filter` actually enforces `status = ACTIVE` and includes any tenant/permission predicates.
- `sort` contains the complete order (`created_at`, `_id`) with the expected directions.
- The query does not run a count merely to fetch a total the API does not need; if infrastructure/test code issues other commands, classify them accurately.
- Roughly `size + 1` elements are read to detect the next page.
- Indexes support the filter/sort, and observe how large `skip` impacts cost.

If you switch from `Slice` to `Page`, compare command counts and actual timings. In some versions and edge cases, `Page` may skip the count; do not write fragile tests asserting that an extra `count` command always fires.

`CommandListener` can see filters containing sensitive data. Do not log full commands in production without proper access control, retention limits, and redaction rules.

## 13. Common design mistakes

| Mistake | Consequence | Remedy |
|---|---|---|
Returning `Page` when UI only needs *View more* | May pay unnecessary total count cost | Prefer `Slice` when totals are not needed
Assuming `Slice` provides total record counts | Broken API, relying on non-existent methods | Use `Page` or an explicit count query if truly required
Fetching exactly `size` records and guessing `hasNext = (size == pageSize)` | Wrong whenever total matches pageSize exactly | Fetch `size + 1` or use built-in `Slice`
Not sorting or sorting only by tied timestamps | Pages return unstable element orders | Add a unique ID as a tie-breaker
Sorting by `updatedAt` and expecting no item shifting | Records jump across pages upon updates | Use immutable/low-churn keys or an appropriate cursor/snapshot
Believing `Slice` prevents duplicates under concurrent inserts | Duplicates/skips due to offset shifts | Understand semantics and consider keyset pagination
Assuming `Slice` is always fast on every page | Deep `skip` still scans past many entries | Check `explain`, cap depth, or switch scrolling strategy
Returning raw entities in API responses | Larger payloads, risk of exposing internal fields | Map to DTOs and verify BSON projections
Implementing `hasNext` via full collection count | Loses the benefit of avoiding total counts | Use lookahead (`size + 1`) or supporting abstractions
Treating `Slice` as an open server cursor across HTTP | Confuses data and resource lifecycles | Distinguish `Slice`, `Stream`, `Flux`, and `Window`
Testing only the first page with plenty of data | Misses last-page bugs when count equals pageSize | Test 0, 1, N, N+1, and multi-page scenarios
Accepting unvalidated cursors from clients | Filter bypass or cross-tenant data leaks | Validate tokens, filter state, and permissions

## 14. Practice exercises

**Exercise 1 — Repository Slice.** Create `CatalogProduct` and `CatalogProductRepository.findByStatus(status, pageable)`. Seed 23 ACTIVE products and request pages 0, 1, and 2 with `size = 10`. Record element counts and `hasNext/hasPrevious`.

**Exercise 2 — Plus-one element.** Implement a `MongoTemplate` method returning `SliceImpl` with `skip`, `limit(size + 1)`, and `List.subList`. Test cases with 10, 11, 20, and 21 records when `size = 10`.

**Exercise 3 — Stable sort.** Insert 20 documents sharing the same `createdAt`. Compare sorting only by `createdAt` versus adding `_id`. Explain why a tie-breaker is needed and design the matching compound index.

**Exercise 4 — Page or Slice?** Build two endpoints: endpoint A displays `totalPages`, endpoint B has only a *View more* button. Choose return types, measure command counts and count cost against real MongoDB without assuming every version runs a fixed number of commands.

**Exercise 5 — Mutating data between pages.** With list `[D,C,B,A]` and size 2, insert `E` at the top after reading page 0. Fetch page 1 via offset and point out the duplicate item. Switch to a cursor on (`createdAt`, `id`) and observe the difference.

**Exercise 6 — Deep pages.** Seed a larger dataset and compare `skip(0)`, `skip(1000)`, and `skip(50000)` with the same size, sort, and index. Use `explain("executionStats")` to record keys/docs examined and latency; propose an offset cap.

**Exercise 7 — Reactive slice-like response.** Use `ReactiveMongoTemplate` to fetch up to `size + 1` elements and produce a `Mono` carrying `items` and `hasNext` without calling `block()`. Check memory as `size` increases and distinguish collecting a bounded page from streaming an entire collection.

## 15. Takeaways

In **Spring Data MongoDB**, `Slice<T>` is ideal when an application needs **a page of data and an answer to "is there a next page?"** without needing the total document count. `Slice.hasNext()` can be determined from the **`pageSize + 1`th element** under the same filter and sort; use `Page<T>` when total metadata is genuinely required.

For reliable results, **filter inside MongoDB, use a deterministic sort with a unique key tie-breaker, bound page size, and inspect indexes and query plans**. `Slice` eliminates the total count requirement, but **it does not eliminate offset `skip` cost or guarantee a snapshot when data mutates between requests**. For deep scrolling, consider keyset cursors/`Window`; for stream processing, distinguish `Slice` from `Stream` and `Flux`.

Finally, test empty pages, pages equal to `pageSize`, pages with one extra record, last pages, and concurrent inserts/deletes between reads. Those edge cases determine whether your *View more* button behaves accurately in production.
