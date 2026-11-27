# Query Pagination and Limits When Data Is Emitted as a Flux

In Spring Data Elasticsearch Reactive, a query can return data as a Reactor `Flux<T>`. This lets applications process results as a stream, compose them with reactive operators, and pace consumption. However, **Flux does not automatically mean Elasticsearch will stream the entire index infinitely or automatically advance to the next page**.

A single search request still caps the number of hits returned by Elasticsearch. To read subsequent pages, the application must issue a new request with `Pageable`, or use a deep-pagination mechanism such as `search_after`. Reactor backpressure regulates demand on the subscriber side; it does not change `size`, `from`, or automatically issue additional search requests.

This lesson covers how to paginate reactive queries, limit emitted results, process multiple pages in a controlled way, and choose the right mechanism for large datasets.

## 1. Flux in Reactive Elasticsearch Queries

`Flux<T>` is a publisher that can emit zero, one, or many elements. In Spring Data Elasticsearch Reactive, search APIs typically return `Flux<SearchHit<T>>` or `Flux<T>`, depending on the method invoked.

Example:

~~~java
import reactor.core.publisher.Flux;

import org.springframework.data.elasticsearch.core.SearchHit;
import org.springframework.data.elasticsearch.core.ReactiveElasticsearchOperations;

Flux<SearchHit<ProductDocument>> hits =
        operations.search(query, ProductDocument.class);
~~~

Each `SearchHit<ProductDocument>` represents one result and can contain:

- The entity converted via Spring Data.
- Document ID and index name.
- Relevance score.
- Sort values.
- Highlight fields and other metadata if requested.

If only the entity is needed, you can map it:

~~~java
Flux<ProductDocument> products =
        operations.search(query, ProductDocument.class)
                .map(SearchHit::getContent);
~~~

A `Flux` from a single search request is usually a finite stream containing that request's hits. The number of hits is bounded by the query and pagination configuration. It completes once the request's results have been emitted.

## 2. Flux Does Not Paginate Automatically

Suppose a query is sent with `size = 20`. Elasticsearch returns at most 20 hits for that request. Once the subscriber receives all 20 hits, the Flux completes.

~~~text
Single search request:
  Elasticsearch returns hit 1 ... hit 20
                |
                v
       Flux<SearchHit<T>>
                |
                v
       Subscriber receives 20 hits
                |
                v
             complete
~~~

If an index has 10,000 documents, receiving 20 hits does not mean Reactor automatically issues the next request for hits 21 through 40.

Three distinct limits must be separated:

| Limit | Controlled by | Meaning |
|---|---|---|
| Hits returned by Elasticsearch | `size` and `from`, or `search_after` | Page size and position at the backend |
| Elements requested by subscriber | Reactive Streams demand | Elements the subscriber is ready to accept |
| Elements held in application memory | Operators and data structures | Client-side buffering/accumulation |

These three limits interact but do not substitute for one another. For example, `take(5)` may emit only five elements to the subscriber even if the backend request already fetched a full page of 100 hits.

## 3. Paginating with Pageable

For standard pagination, Spring Data uses `Pageable`. `PageRequest.of(page, size)` constructs a zero-based page request.

Example fetching the first 20 products:

~~~java
import org.springframework.data.domain.PageRequest;
import org.springframework.data.elasticsearch.client.elc.NativeQuery;

NativeQuery query = NativeQuery.builder()
        .withQuery(elasticsearchQuery)
        .withPageable(PageRequest.of(0, 20))
        .build();
~~~

Next page:

~~~java
NativeQuery nextQuery = NativeQuery.builder()
        .withQuery(elasticsearchQuery)
        .withPageable(PageRequest.of(1, 20))
        .build();
~~~

With `page = 0` and `size = 20`, the request fetches the initial positions. With `page = 1`, the request fetches the next page at the corresponding offset.

Offset formula:

\[
from = page \times size
\]

Example:

| Page (0-based) | Size | From |
|---:|---:|---:|
| 0 | 20 | 0 |
| 1 | 20 | 20 |
| 2 | 20 | 40 |
| 3 | 20 | 60 |

Do not confuse the page index with the hit position. Pages start at 0, and hit offsets start at 0.

## 4. Reactive Repositories with Pageable and Flux

A reactive repository can accept `Pageable` as a parameter and return results as `Flux<T>`.

~~~java
import org.springframework.data.domain.Pageable;
import org.springframework.data.elasticsearch.repository.ReactiveElasticsearchRepository;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public interface ProductRepository
        extends ReactiveElasticsearchRepository<ProductDocument, String> {

    Flux<ProductDocument> findByStatus(
            String status,
            Pageable pageable
    );

    Mono<Long> countByStatus(String status);
}
~~~

Invocation:

~~~java
Pageable firstPage = PageRequest.of(0, 25);

Flux<ProductDocument> products =
        productRepository.findByStatus("PUBLISHED", firstPage);
~~~

The `Flux` emits the documents on the requested page. If the total number of matching documents is needed, call a separate count method:

~~~java
Mono<Long> total =
        productRepository.countByStatus("PUBLISHED");
~~~

In reactive flows, do not expect a synchronous `Page<T>` containing both content and total count unless your repository API specifically supports that return pattern. Retrieving the count can be a separate asynchronous query.

Another option is calling `ReactiveElasticsearchOperations.searchForPage(...)` to receive `Mono<SearchHits<T>>`, which provides both the hit list and response-level metadata.

## 5. Comparing search Returning Flux vs. searchForPage Returning Mono

Spring Data Elasticsearch Reactive provides result types suited to two needs:

| API | Result | When to use |
|---|---|---|
| `search(query, Entity.class)` | `Flux<SearchHit<Entity>>` | Processing individual hits of a request |
| `searchForPage(query, Entity.class)` | `Mono<SearchHits<Entity>>` | Need metadata and hit list for a single page |
| Repository method returning `Flux<Entity>` | `Flux<Entity>` | Need entities directly from a query method |
| Repository count method | `Mono<Long>` | Need total count of matching documents |

Example using `searchForPage`:

~~~java
Mono<SearchHits<ProductDocument>> pageResult =
        operations.searchForPage(query, ProductDocument.class);

Flux<ProductDocument> productsInPage =
        pageResult.flatMapMany(result ->
                Flux.fromIterable(result.getSearchHits())
                        .map(SearchHit::getContent)
        );
~~~

`SearchHits<T>` provides:

- `getSearchHits()`: list of hits on the page.
- `getTotalHits()`: total hits reported in the response.
- `getMaxScore()`: highest score if available.
- `getAggregations()`: aggregation container if the query included aggregations.
- Other metadata depending on request type and version.

`searchForPage` still returns only a single page per `Pageable`. Its `Mono` return type does not automatically fetch subsequent pages.

## 6. Building Queries per Page

You can write a helper that builds a query for a page index:

~~~java
import org.springframework.data.domain.PageRequest;
import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.elasticsearch.core.query.Query;

private Query queryForPage(int page, int pageSize) {
    return NativeQuery.builder()
            .withQuery(elasticsearchQuery)
            .withPageable(PageRequest.of(page, pageSize))
            .build();
}
~~~

Then execute a single page:

~~~java
Mono<SearchHits<ProductDocument>> fetchPage(int page) {
    Query query = queryForPage(page, 50);
    return operations.searchForPage(query, ProductDocument.class);
}
~~~

To read the first page:

~~~java
Flux<ProductDocument> firstPage =
        fetchPage(0)
                .flatMapMany(result ->
                        Flux.fromIterable(result.getSearchHits())
                                .map(SearchHit::getContent)
                );
~~~

If only one page is needed, stop here. There is no need to loop or count the entire index.

## 7. Reading Multiple Pages Sequentially into One Flux

If business logic needs to process the entire result set page by page, the application must explicitly construct each subsequent request.

One straightforward approach uses deferred recursion with `Flux.defer(...)`. Each step only fetches the next page after the current page has finished emitting.

~~~java
private static final int PAGE_SIZE = 200;
private static final int MAX_PAGES = 100;

private Flux<ProductDocument> readPages(int page) {
    if (page >= MAX_PAGES) {
        return Flux.error(
                new IllegalStateException("Maximum page limit reached")
        );
    }

    Query query = queryForPage(page, PAGE_SIZE);

    return operations.searchForPage(query, ProductDocument.class)
            .flatMapMany(result -> {
                List<SearchHit<ProductDocument>> pageHits =
                        result.getSearchHits();

                Flux<ProductDocument> currentPage =
                        Flux.fromIterable(pageHits)
                                .map(SearchHit::getContent);

                if (pageHits.size() < PAGE_SIZE) {
                    return currentPage;
                }

                return currentPage.concatWith(
                        Flux.defer(() -> readPages(page + 1))
                );
            });
}
~~~

How this works:

1. Send the query for the current page.
2. Receive `Mono<SearchHits<T>>`.
3. Convert the page's hits into a Flux.
4. If the hit count is smaller than the page size, this is the final page.
5. If the page is full, request the next page only after the current page finishes emitting.
6. If the page limit is exceeded, the publisher emits an error so the caller knows the scan was capped.

If the total number of documents is an exact multiple of the page size—for instance, 400 documents with a page size of 200—the flow will request one extra empty page to confirm no more data remains. This is valid behavior.

The `MAX_PAGES` cap protects a job from running indefinitely or reading more data than expected. In real applications, configure this limit externally and emit logs/metrics if it is reached.

## 8. Why Use concatWith and Flux.defer?

`concatWith` chains two publishers sequentially: the first publisher completes before the second publisher is subscribed to.

`Flux.defer` defers creating the next page's publisher until the subscriber actually needs it and the current page has finished.

Compare:

~~~java
return currentPage.concatWith(
        Flux.defer(() -> readPages(page + 1))
);
~~~

With this pattern, pages are read sequentially. It avoids eagerly creating hundreds of search requests simultaneously.

Avoid writing:

~~~java
return Flux.concat(
        readPages(page + 1),
        currentPage
);
~~~

That snippet also reverses page order and fails to express emitting the current page before the next page.

Also avoid building a large list of publishers by eagerly invoking the page-fetch method upfront when unnecessary. Defer requests and only construct the next page as the stream is consumed.

## 9. Backpressure Controls Consumption Rate

Reactive Streams includes demand signaling. Subscribers can request how many elements they are ready to accept. Reactor propagates this demand upstream when publishers support backpressure.

Example:

~~~java
Flux<ProductDocument> products = readPages(0);

products
        .limitRate(32)
        .subscribe(this::processProduct);
~~~

`limitRate(32)` tunes how Reactor requests data upstream in batches. It can pace emission inside the pipeline, yet it **does not change Elasticsearch's page size to 32**.

If a backend page contains 200 hits, the search request still retrieves 200 hits. Reactor paces how those elements are emitted downstream.

Backpressure is helpful when:

- A consumer writes to another system slower than reads arrive.
- Each item requires CPU or I/O processing.
- You want to prevent downstream from accumulating too many items at once.
- A multi-step pipeline can propagate demand cleanly.

Backpressure alone does not lower Elasticsearch query cost if each request still asks for an overly large page.

## 10. Distinguishing take, limitRate, and Pageable Size

These operators are frequently confused:

| Mechanism | Effect | Changes Elasticsearch size? |
|---|---|---|
| `PageRequest.of(page, size)` | Determines page and hit count returned by backend | Yes |
| `take(n)` | Emits at most n elements downstream | Not automatically |
| `limitRate(n)` | Paces demand between subscriber and upstream | No |
| `buffer(n)` | Collects n elements into a batch | No |
| `collectList()` | Collects all elements into a single List | No |
| `onBackpressureBuffer()` | Temporarily buffers elements when downstream falls behind | No |

Example:

~~~java
operations.search(queryWithPageSize100, ProductDocument.class)
        .take(5);
~~~

Elasticsearch may have already returned a page of 100 hits, while downstream receives at most 5 hits. This is not equivalent to querying the backend with `size = 5`.

If only 5 documents are needed, set the page size to 5:

~~~java
NativeQuery query = NativeQuery.builder()
        .withQuery(elasticsearchQuery)
        .withPageable(PageRequest.of(0, 5))
        .build();
~~~

You can combine both to protect both backend and downstream, provided you understand which boundary each limit enforces.

## 11. Page Size Limits and Memory

Larger page sizes reduce request round trips, yet increase the amount of data that must be:

- Found and serialized by Elasticsearch.
- Transferred over the network.
- Deserialized on the client.
- Held in memory during processing.
- Converted into entities and emitted downstream.

Too small a page size increases round trips and per-request overhead.

A practical choice depends on document size, returned fields, network latency, and downstream processing speed. No single page size is optimal for every index.

You can enforce bounds at the service layer:

~~~java
private int normalizePageSize(int requestedSize) {
    int defaultSize = 50;
    int maxSize = 500;

    if (requestedSize <= 0) {
        return defaultSize;
    }

    return Math.min(requestedSize, maxSize);
}
~~~

Never trust client-supplied page sizes blindly. A request asking for hundreds of thousands of hits can create heavy load and spike heap usage in both the application and Elasticsearch.

Consider additional limits:

- Maximum pages per export.
- Total execution timeout.
- Maximum concurrent requests.
- Output batch sizes.
- Maximum documents processed in a single job.

## 12. Elasticsearch from/size Limits

Pagination via `Pageable` usually translates to `from/size`. Elasticsearch enforces `index.max_result_window`, which defaults commonly to 10,000.

Examples:

- `page = 0, size = 100`: from = 0.
- `page = 50, size = 100`: from = 5,000.
- `page = 100, size = 100`: from = 10,000.

Requests whose `from + size` exceeds this limit may be rejected.

Raising `max_result_window` allows deeper requests to pass validation, yet Elasticsearch must still collect and sort many results prior to the returned window. Increasing the limit does not make offset pagination efficient across millions of documents.

Use `from/size` for UI pagination at moderate depths. For exports or scanning large numbers of documents, consider `search_after` paired with PIT.

## 13. Stable Sorting When Reading Multiple Pages

When paginating, result order must be deterministic. Sorting solely by a non-unique field like `createdAt` means multiple documents can share the same value. Their relative order can shift between requests.

Add a unique tie-breaker field mapped to support sorting:

~~~java
Sort sort = Sort.by(
        Sort.Order.asc("createdAt"),
        Sort.Order.asc("productId")
);

Pageable pageable = PageRequest.of(0, 100, sort);
~~~

Here `productId` should be a keyword field with unique values across the scanned dataset.

Avoid sorting directly on `_id` metadata as if it were a keyword field with doc values. If an ID tie-breaker is needed, store a corresponding keyword field in the document source.

Stable sorting reduces the risk of duplicate or skipped documents caused by equal sort values. However, it does not maintain a snapshot if the index changes between requests.

## 14. Data Changes Between Pages

`from/size` issues independent requests. If documents are added, deleted, or updated between requests, offsets can shift.

Example:

1. Page 1 fetches documents 1 through 20.
2. A new document is inserted at the start of the sort order.
3. The next page uses `from = 20`.
4. A previously seen document may appear again, or another document may be skipped.

If the application needs a consistent snapshot while reading multiple pages, consider Point in Time (PIT) combined with `search_after`. PIT preserves the point-in-time view of data; `search_after` uses the last hit's sort values to resume.

PIT does not block writes. Changes made after opening the PIT are excluded from that snapshot. Close the PIT when finished and set a keep-alive matching gaps between requests.

## 15. Deep Pagination with search_after

`search_after` resumes from the previous page's final hit sort values instead of using large offsets.

Query example:

~~~java
NativeQuery firstPage = NativeQuery.builder()
        .withQuery(elasticsearchQuery)
        .withSort(byCreatedAt, byProductId)
        .withPageable(PageRequest.of(0, 500))
        .build();
~~~

After receiving the page, read the sort values of the last hit:

~~~java
List<SearchHit<ProductDocument>> hits = searchHits.getSearchHits();

List<Object> searchAfter = hits
        .get(hits.size() - 1)
        .getSortValues();
~~~

The next query keeps the exact same query and sort while passing the cursor:

~~~java
NativeQuery nextPage = NativeQuery.builder()
        .withQuery(elasticsearchQuery)
        .withSort(byCreatedAt, byProductId)
        .withPageable(PageRequest.of(0, 500))
        .withSearchAfter(searchAfter)
        .build();
~~~

`search_after` does not use page numbers. Keep the page index at 0 and rely on sort values to determine the continuation point.

For mutable data, pair with PIT so all pages read from the same snapshot. APIs for opening/closing PIT and attaching PIT to queries must use the reactive API supported by your Spring Data Elasticsearch version; some versions provide reactive methods on operations, while others may require the appropriate Java API Client calls.

When receiving each new response, update the PIT ID if Elasticsearch returns a new one. Use the latest ID for subsequent requests and when closing the PIT.

## 16. Reading Multiple search_after Pages into a Flux

Each page can be modeled as a reactive step:

1. Send the current query.
2. Emit the page's hits.
3. Extract the sort values of the final hit.
4. Build the next query using search_after.
5. Repeat until a page is empty or smaller than page size.

Pseudocode:

~~~java
private Flux<ProductDocument> readAfter(List<Object> cursor) {
    NativeQuery query = buildQueryWithSearchAfter(cursor);

    return operations.searchForPage(query, ProductDocument.class)
            .flatMapMany(result -> {
                List<SearchHit<ProductDocument>> hits =
                        result.getSearchHits();

                Flux<ProductDocument> current =
                        Flux.fromIterable(hits)
                                .map(SearchHit::getContent);

                if (hits.size() < PAGE_SIZE) {
                    return current;
                }

                List<Object> nextCursor =
                        hits.get(hits.size() - 1).getSortValues();

                return current.concatWith(
                        Flux.defer(() -> readAfter(nextCursor))
                );
            });
}
~~~

`buildQueryWithSearchAfter(...)` must preserve the query, sort, page size, and PIT metadata. This pseudocode focuses on stream structure; exact PIT open/close signatures and builders must match your Spring Data Elasticsearch version.

Do not recompute the cursor from the entity. Use `getSortValues()` from the response to preserve exact types and sort order.

## 17. Using concatMap and flatMap Correctly

When each page is fetched via a publisher, the combining operator governs order and concurrency.

| Operator | Behavior | When to use |
|---|---|---|
| `concatMap` | Subscribes sequentially, preserving source order | Next page depends on the previous page's cursor |
| `flatMap` | Can run multiple publishers concurrently; results interleave | Independent requests where order does not matter |
| `flatMapSequential` | Runs concurrently while emitting in source order | Order must be preserved and buffering is acceptable |

With `search_after` pagination, the next page depends on the current page's sort values. You cannot pre-build all requests in parallel because later cursors are not yet known.

With independent page numbers, bounded concurrency can be used if ordering does not matter:

~~~java
Flux.range(0, 10)
        .flatMap(
                page -> fetchPage(page),
                2
        );
~~~

The concurrency parameter is 2, so at most two page requests are subscribed to simultaneously. However, if emitted directly, pages can finish out of order. If page order must be preserved, use `flatMapSequential` or `concatMap`, keeping buffering trade-offs in mind.

Never use unbounded concurrency across hundreds or thousands of pages.

## 18. Limiting Total Results with take

If an API lets clients request at most N results, enforce limits at two layers:

- Cap page size or total page count on the backend.
- Use `take(N)` as an additional guard in the reactive pipeline.

Example:

~~~java
Flux<ProductDocument> limited =
        readPages(0)
                .take(1_000);
~~~

`take(1_000)` stops emitting after 1,000 elements and cancels the upstream subscription. When pagination creates the next request via `defer`, cancellation prevents unstarted pages from being requested.

However, an in-flight request may already have been sent to Elasticsearch and fetched an entire page. Therefore, `take` does not replace page size or backend limits.

If page size is 200 and take is 1,000, the stream fetches only as many pages as needed to emit 1,000 results. The final page may only be partially consumed.

## 19. Avoid collectList on Large Datasets

`collectList()` gathers all elements into a single List and emits a Mono only once the entire stream finishes:

~~~java
Mono<List<ProductDocument>> allProducts =
        readPages(0).collectList();
~~~

This is convenient when result counts are small and all items must be processed together. With hundreds of thousands or millions of documents, however, the list consumes substantial heap and risks an OutOfMemoryError.

For exports or batch processing, process element by element or group into fixed-size batches:

~~~java
readPages(0)
        .buffer(200)
        .concatMap(batch -> exportBatch(batch));
~~~

`buffer(200)` creates lists of at most 200 elements, bounding memory to a single batch rather than the full dataset.

If `exportBatch(...)` performs I/O, return a reactive publisher instead of calling blocking APIs inside the pipeline.

## 20. Error Handling During Pagination

A paginated stream can fail on any page request:

- Timeout or connection loss.
- Invalid query.
- Incompatible mapping.
- Exceeding `max_result_window`.
- Expired PIT.
- Shard failure.
- Downstream failure when writing batches.

If one page fails, the Flux typically emits an error and terminates. Subsequent pages do not continue automatically.

You can log and translate errors into domain exceptions:

~~~java
readPages(0)
        .doOnError(error ->
                log.error("Product export failed", error)
        )
        .onErrorMap(error ->
                new ProductExportException("Unable to read products", error)
        );
~~~

Do not use `onErrorResume(error -> Flux.empty())` indiscriminately. Doing so turns a partial/failed export into an apparently successful empty result.

When retrying, only retry recoverable errors. For timeouts where it is unclear whether the request completed, read searches are generally safer than updates, while still keeping the same query/cursor and snapshot policy. If a PIT expires, opening a new PIT does not recreate the old snapshot; decide whether to restart or reconcile.

## 21. Timeouts, Cancellation, and Deadlines

A reactive export should have time limits and support cancellation:

~~~java
readPages(0)
        .timeout(Duration.ofMinutes(10))
        .doOnCancel(() -> log.info("Product export cancelled"));
~~~

`timeout(...)` caps wait time per Reactor operator semantics. If exceeded, the publisher emits a timeout error.

`doOnCancel(...)` logs when a subscriber cancels. This does not prove all backend requests stopped immediately; request cancellation depends on the client and network call state.

If using PIT, ensure cleanup executes on completion, error, or cancellation. You can use `usingWhen` to bind an asynchronous resource's lifecycle to the publisher:

~~~java
Flux<ProductDocument> export =
        Flux.usingWhen(
                openPit(),
                pitId -> readPagesWithPit(pitId),
                this::closePit,
                (pitId, error) -> closePit(pitId),
                this::closePit
        );
~~~

This illustrates the pattern. `openPit()` and `closePit(...)` must return reactive publishers matching your version's PIT API. The goal is closing the PIT on completion, error, or cancellation.

## 22. Limiting Request Rate and Downstream Backpressure

When each hit is forwarded to another service, downstream processing may be slower than reading.

Example sequential processing:

~~~java
readPages(0)
        .concatMap(product -> inventoryClient.update(product));
~~~

`concatMap` waits for one product's publisher to complete before moving to the next. This keeps concurrency low at the cost of lower throughput.

You can allow a bounded number of concurrent tasks:

~~~java
readPages(0)
        .flatMap(
                product -> inventoryClient.update(product),
                8
        );
~~~

At most eight downstream operations run concurrently. If order does not matter and the target system tolerates the load, this can increase throughput.

Choose concurrency based on target capacity, connection pools, and rate limits. Do not raise concurrency just to make the Flux emit faster if Elasticsearch or downstream services are overloaded.

## 23. Avoiding Blocking Inside Reactive Pipelines

Never call `block()` or `toIterable()` inside a reactive pipeline:

~~~java
// Avoid:
Flux<ProductDocument> products =
        operations.search(query, ProductDocument.class)
                .map(SearchHit::getContent)
                .map(product -> blockingService.enrich(product).block());
~~~

Blocking stalls the reactive processing thread and can cause starvation or deadlocks on some schedulers.

If a library only provides blocking APIs, isolate it on an appropriate scheduler:

~~~java
Flux<ProductDocument> enriched =
        products.flatMap(product ->
                Mono.fromCallable(() -> blockingService.enrich(product))
                        .subscribeOn(Schedulers.boundedElastic())
        );
~~~

This is a compatibility workaround for bounded blocking work. Prefer end-to-end reactive clients when available.

Never call `subscribe()` inside a service just to launch work and return void. Return `Flux` or `Mono` to the caller so the caller controls subscription, cancellation, and errors.

## 24. Total Hits Is Not Always an Exact Count

`SearchHits.getTotalHits()` is useful when the UI displays result counts. However, Elasticsearch may cap exact total-hit counting based on tracking configuration.

If an exact total is needed to compute total pages, verify whether the query enables appropriate total-hit tracking. For large datasets, exact counting can be expensive.

For sequential scan jobs, you can usually stop when a page returns fewer hits than page size or returns empty. This avoids running an upfront count. If the final page happens to match the exact page size, one extra empty request is needed to confirm the end.

Do not compute `totalPages` from a capped total hit count and assume the page count is always exact.

## 25. search_after and PIT for Large Data Streams

For deep exports or millions of documents, `from/size` is not appropriate. `search_after` uses the last hit's sort values to resume, while PIT maintains a consistent snapshot across requests.

General workflow:

~~~mermaid
flowchart TD
    A["Open PIT"] --> B["Search first page"]
    B --> C["Emit page hits"]
    C --> D["Read last hit sort values"]
    D --> E["Update PIT ID if response returns a new ID"]
    E --> F["Search with search_after"]
    F --> G{"More hits?"}
    G -->|Yes| C
    G -->|No| H["Close PIT"]
~~~

Guidelines:

- Keep query and sort identical across pages.
- Include a stable tie-breaker in the sort.
- Use sort values from the last hit; do not construct cursors from entities.
- Use the latest PIT ID if the response returns a new one.
- Set keep-alive long enough to cover processing gaps between requests.
- Close PIT on completion, error, or cancellation.
- If a PIT expires, do not open a new PIT and reuse an old cursor as if it belonged to the same snapshot.

Reactive flow only changes how the application coordinates I/O and processes results. It does not alter cursor rules, stable sort requirements, or PIT lifecycle management.

## 26. Pagination and API Security

If an API lets clients supply page and size, validate and bound them:

~~~java
int page = Math.max(requestedPage, 0);
int size = normalizePageSize(requestedSize);

Pageable pageable = PageRequest.of(page, size);
~~~

Beyond page/size, queries must enforce server-side filters for tenant, permissions, and data scope. Never let clients bypass security filters via arbitrary queries or cursors.

For `search_after` cursors, avoid letting clients tamper with raw sort values or PIT IDs. Wrap them in an opaque server-generated signed/encrypted token. Bind the token to the query fingerprint, tenant, page size, and expiration.

Backpressure is not a security or quota mechanism. A subscriber can request data very slowly or hold a subscription open indefinitely; APIs still need timeouts, rate limits, page caps, and resource cleanup.

## 27. Common Pitfalls

### Assuming Flux Automatically Fetches the Entire Index

A search Flux typically emits only the hits of the current request. Issue next-page requests or use a cursor explicitly.

### Using take Instead of Backend Page Size

`take(n)` caps emitted elements, not necessarily how many hits Elasticsearch fetched. Set `Pageable` appropriately.

### Assuming limitRate Reduces Search Request Size

`limitRate` paces Reactor demand. It does not change `size` in Elasticsearch.

### Returning Synchronous Page in a Reactive Repository

Reactive repositories should return `Flux`/`Mono`. If total count is needed, use a count publisher or `searchForPage` as appropriate.

### Issuing All Page Requests in Parallel

Pages using `search_after` depend on the previous page's cursor. Use `concatMap` or chain publishers sequentially.

### Using Unbounded flatMap

Excessive concurrency can overload Elasticsearch, connection pools, and downstream services. Set a finite concurrency limit.

### Calling collectList on Large Datasets

`collectList` retains every element on the heap. Process per hit or buffer in small batches.

### Using from/size Beyond max_result_window

Deep pagination may be rejected or consume heavy resources. Switch to search_after/PIT for large exports.

### Omitting a Stable Sort

Documents sharing identical sort values can shift order between pages. Add a unique tie-breaker.

### Ignoring Data Mutations Between Pages

Independent offset requests can observe changing index states. Use PIT when a consistent snapshot is needed.

### Swallowing Errors with Flux.empty()

Exports may appear successful despite reading only partial data. Propagate explicit errors and store checkpoints if resumability is needed.

### Failing to Clean Up PIT on Cancellation

Subscribers can cancel before reading everything. Attach cleanup to completion, error, and cancellation paths.

## 28. Workflow for Choosing a Pagination Strategy

When building reactive queries:

1. If only a small result set is needed, set an explicit page size and return `Flux<SearchHit<T>>` or `Flux<T>`.
2. If single-page metadata is needed, use `searchForPage(...)` returning `Mono<SearchHits<T>>`.
3. If a moderate number of pages is needed, build each `PageRequest` and chain publishers with `concatMap`/`concatWith`.
4. Cap page size, page count, duration, and concurrency.
5. Use `take(n)` as an extra emission guard, not as a substitute for backend limits.
6. Avoid `collectList` on large result sets.
7. For deep pagination, switch to `search_after` with stable sorting.
8. Use PIT when a consistent snapshot across requests is needed.
9. Handle cancellation, timeouts, errors, and resource cleanup.
10. If exposing cursors to clients, protect cursors and bind them to the authenticated query/tenant.
11. Monitor hit counts, page counts, per-page latency, retries, and downstream errors.
12. Test empty pages, final pages shorter than page size, and final pages matching exact page size.

## References

- [Spring Data Elasticsearch — Reactive Elasticsearch Operations](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/template.html)
- [Spring Data Elasticsearch — Reactive Repositories](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/repositories/reactive-repositories.html)
- [Spring Data Elasticsearch — Search Operations API](https://docs.spring.io/spring-data/elasticsearch/docs/current/api/org/springframework/data/elasticsearch/core/ReactiveSearchOperations.html)
- [Elasticsearch — Paginate search results](https://www.elastic.co/guide/en/elasticsearch/reference/current/paginate-search-results.html)
- [Elasticsearch — Point in time API](https://www.elastic.co/guide/en/elasticsearch/reference/current/point-in-time-api.html)
- [Project Reactor — Reference Guide](https://projectreactor.io/docs/core/release/reference/)
- [Reactive Streams — Specification](https://www.reactive-streams.org/)

## Conclusion

In Spring Data Elasticsearch Reactive, `Flux` represents streamed results yet does not paginate automatically. Backend page size is controlled by `Pageable` or cursors; Reactor backpressure paces demand and downstream consumption. For a single page, use `search(...)` or `searchForPage(...)`; for multiple pages, issue subsequent requests explicitly and chain them sequentially via `concatWith`/`concatMap`. Cap page size, page count, concurrency, and duration; avoid collecting large datasets with `collectList`. When deep and consistent reads are needed, use `search_after` with stable sorting and PIT, while managing cancellation and resource cleanup.
