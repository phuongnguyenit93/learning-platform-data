# Backpressure, Concurrency Limits, and Memory Control

In Spring Data Elasticsearch Reactive, data is processed through Project Reactor's `Mono` and `Flux`. Reactivity allows applications to handle I/O asynchronously and stream data, yet it does not automatically guarantee low memory usage or prevent overloading Elasticsearch. If upstream emits faster than downstream processes, if `flatMap` opens too many concurrent requests, or if the application buffers all results into a `List`, the system can still exhaust heap memory.

Three mechanisms must be designed together:

- **Backpressure:** paces how many elements downstream requests from upstream.
- **Concurrency limit:** caps how many Elasticsearch operations or processing tasks run simultaneously.
- **Memory bound:** caps page size, prefetch, queues, batches, and data held in RAM.

In a reactive pipeline, backpressure regulates demand per Reactive Streams; `flatMap`/`concatMap` determines concurrency; page size, prefetch, and buffers govern how much data can remain queued. Reliable ingestion or search requires explicit limits across all three layers.

## 1. Reactivity Does Not Mean Unbounded Memory Safety

A pipeline can be non-blocking yet still accumulate huge numbers of objects on the heap:

```java
repository.findAll()
    .collectList()
    .flatMap(products -> processAll(products));
```

`findAll()` returns a `Flux`, yet `collectList()` buffers every element until the source completes. If an index holds millions of documents, that list can exceed available memory.

Likewise, the following pipeline can launch too many concurrent requests:

```java
ids.flatMap(id -> repository.findById(id));
```

The `flatMap` overload without an explicit concurrency argument uses Reactor's default. That default may suit small pipelines, yet it should not be treated as a limit engineered for your Elasticsearch capacity and document sizes.

Reactivity only provides signal propagation and demand pacing. The application must still choose page sizes, concurrency, prefetch, queue capacities, and slow-downstream policies.

## 2. Reactive Streams Demand and Backpressure

Reactive Streams has four foundational components:

- `Publisher`: emits data.
- `Subscriber`: receives data.
- `Subscription`: connects both sides, allowing the subscriber to request more elements or cancel.
- `request(n)`: the subscriber signals it wants at most `n` additional elements.

Backpressure is how downstream paces the rate at which it requests data from upstream. Downstream finishes processing an item or group of items before requesting more.

```text
Elasticsearch / Publisher
          |
          | onNext(item)
          v
       Operator A
          |
          v
       Operator B
          |
          v
      Subscriber
          |
          | request(n)
          +-----------------------> upstream
```

In Reactor, most operators preserve and propagate Reactive Streams demand. Some operators maintain queues or prefetch ahead to improve throughput. Consequently, backpressure does not mean upstream emits strictly one item after downstream finishes the previous item; pipelines may hold a bounded number of prefetched or queued items.

### Example of Batch Demand from a Subscriber

At the Reactive Streams level, a subscriber can request 10 items, process them, and then request 10 more. When using standard Reactor operators, the framework manages subscriptions and demand for you; applications configure operators rather than writing custom `Subscriber` implementations.

## 3. Backpressure in Spring Data Elasticsearch

Spring Data Elasticsearch reactive APIs return `Mono<T>` or `Flux<T>`. Repository example:

```java
import org.springframework.data.elasticsearch.repository.ReactiveElasticsearchRepository;
import reactor.core.publisher.Flux;

public interface ProductRepository
        extends ReactiveElasticsearchRepository<ProductDocument, String> {

    Flux<ProductDocument> findByCategory(String category);
}
```

Service example reading results:

```java
import org.springframework.data.elasticsearch.core.ReactiveElasticsearchOperations;
import org.springframework.data.elasticsearch.core.SearchHit;
import org.springframework.data.elasticsearch.core.query.Query;
import reactor.core.publisher.Flux;

public Flux<ProductDocument> search(Query query) {
    return operations.search(query, ProductDocument.class)
        .map(SearchHit::getContent);
}
```

`Flux` lets consumers receive results asynchronously. When downstream is a WebFlux response or another reactive operator, demand can propagate backward through the pipeline. However, a search request still retrieves a page of the configured size; downstream demand does not automatically cause Elasticsearch to return smaller pages.

### Backpressure Is Not a Page Size Limit

Two separate layers exist:

1. Elasticsearch decides how many hits each search request returns via `size`/pageable.
2. Reactor decides how downstream receives and processes elements from the publisher via demand and prefetch.

If a search request fetches 5,000 hits, the entire response page may already be deserialized before downstream processes each hit. Setting `limitRate(10)` does not turn a 5,000-hit page into an Elasticsearch request with `size=10`.

## 4. Limiting Concurrency with `flatMap`

`flatMap` transforms each element into an inner publisher and lets multiple inner publishers run concurrently. The `concurrency` parameter caps how many inner publishers are active simultaneously.

```java
Flux<ProductDocument> saved = products
    .flatMap(repository::save, 8);
```

Here at most 8 save operations are subscribed to concurrently through this pipeline. This is a per-subscription/per-pipeline cap, not a cluster-wide cap. With 10 application instances each running concurrency 8, total simultaneous operations can reach around 80, excluding other pipelines.

### Choosing Concurrency

| Concurrency | Behavior | Trade-off |
|---:|---|---|
| 1 | One inner publisher at a time | Easy to control, throughput may be lower |
| 4–8 | Bounded concurrent requests | Good starting point for benchmarking |
| 16–32 | Higher parallelism | Can raise throughput while increasing in-flight requests and heap |
| Very large / unbounded | Many simultaneous requests | Easily causes large queues, connection pool, thread, heap, and Elasticsearch pressure |

There is no universal optimal number. Start with low concurrency, measure throughput and p95/p99 latency, and increase incrementally until throughput plateaus or resources begin saturating.

### `flatMap` Does Not Preserve Order

Inner publishers finish at their own pace, so outputs may differ from input order. When ordering does not matter, `flatMap` usually delivers good throughput. When emission order must be preserved, consider `flatMapSequential` or `concatMap`.

## 5. `concatMap` for Sequential Processing

`concatMap` subscribes to the next inner publisher only after the current one completes:

```java
Flux<UpdateResult> results = ids
    .concatMap(id -> updateOne(id));
```

Advantages:

- Only one inner operation runs at a time.
- Preserves processing order naturally.
- Minimizes in-flight requests and simplifies sequentially dependent state.

The trade-off is lower throughput when each request has high latency. If documents are independent, `flatMap(..., concurrency)` with a moderate cap can be used.

## 6. `flatMapSequential` When Ordered Output Is Needed

`flatMapSequential` runs multiple inner publishers concurrently while emitting results in source order:

```java
Flux<Result> results = ids
    .flatMapSequential(this::loadAndTransform, 8, 16);
```

`8` caps concurrency; `16` sets prefetch per inner publisher. Because later publishers may finish before earlier ones, early completions wait in a buffer to preserve ordering.

Thus, preserving order can raise memory usage if an early task stalls. If ordering is unnecessary, `flatMap` avoids this waiting buffer.

## 7. Distinguishing Concurrency, Prefetch, and `limitRate`

These parameters solve different problems:

| Mechanism | Controls | Does not mean |
|---|---|---|
| `flatMap(mapper, concurrency)` | Number of concurrent inner publishers | Elasticsearch page size |
| `flatMap(mapper, concurrency, prefetch)` | Concurrency and demand prefetched from each inner | Exact byte limit |
| `limitRate(highTide)` | Splits upstream demand into smaller batches | Limit on concurrent Elasticsearch requests |
| `buffer(n)` | Item count gathered into a single batch | Limit on total source items |
| `onBackpressureBuffer(n)` | Queue capacity when downstream slows down | Automatic throttling of all producers |

Example:

```java
Flux<Result> results = source
    .limitRate(64)
    .flatMap(this::callElasticsearch, 8, 16);
```

Here `limitRate(64)` paces demand from upstream in batches; `flatMap` allows up to 8 inner publishers; each inner has prefetch 16. You cannot infer that exactly 64 or 128 requests are running. Understand how each publisher emits data and where operators place queues.

## 8. Using `limitRate` to Regulate Demand

`limitRate` splits large upstream requests into smaller batches. Example:

```java
Flux<ProductDocument> products = repository.findAll()
    .limitRate(100);
```

Reactor regulates upstream demand using the operator's high-tide and replenishment strategy. You can also pass `lowTide` to control the replenishment threshold:

```java
Flux<ProductDocument> products = repository.findAll()
    .limitRate(100, 75);
```

`limitRate` is helpful when preventing upstream from receiving overly large demand requests and smoothing element emission through the pipeline. However, it is not a per-second rate limiter, does not cap concurrency of multiple inner publishers, and does not shrink the `size` of an already-issued search request.

## 9. `onBackpressureBuffer`: Bounded Buffering

When upstream cannot or does not honor downstream pacing, a buffer can be used. However, unbounded buffers by default are dangerous if the source can emit large volumes.

Example bounded buffer holding at most 1,000 items:

```java
import reactor.core.publisher.BufferOverflowStrategy;

Flux<Event> buffered = eventSource
    .onBackpressureBuffer(
        1_000,
        dropped -> log.warn("Backpressure buffer overflow: {}", dropped.id()),
        BufferOverflowStrategy.ERROR
    );
```

When the queue fills, the `ERROR` strategy emits an error instead of growing memory indefinitely. The application can catch the error at the pipeline boundary, record metrics, and respond per business policy.

### Never Use Unbounded Buffers on Unbounded Sources

```java
source.onBackpressureBuffer();
```

The overload without a capacity limit can accumulate data indefinitely if the producer outpaces the consumer over time. This turns a non-blocking system into one retaining ever more objects on the heap.

### Choosing an Overflow Strategy

| Strategy | When queue is full | Suitable for |
|---|---|---|
| `ERROR` | Terminates pipeline with error | Data that must not be lost; caller can retry or halt producer |
| `DROP_OLDEST` | Discards oldest item in buffer | Only latest state matters; dropping stale data is acceptable |
| `DROP_LATEST` | Discards newly arriving item | Keep queued items; dropping newer updates is acceptable |

Choose the strategy based on data semantics. Never drop orders, payments, or events requiring guaranteed processing unless a durable retry mechanism exists.

## 10. `onBackpressureDrop`, `onBackpressureLatest`, and `onBackpressureError`

Reactor provides operators for when downstream falls behind:

```java
source.onBackpressureDrop(item -> recordDropped(item));
```

`onBackpressureDrop` discards elements that cannot be forwarded under current demand. This represents intentional data loss.

```java
source.onBackpressureLatest();
```

`onBackpressureLatest` retains only the newest element while downstream is busy; intermediate values may be dropped. Useful for snapshot states, telemetry, or UI values needing only the latest update.

```java
source.onBackpressureError();
```

`onBackpressureError` turns unmet demand into an error. This fails fast rather than holding uncontrolled amounts of data.

These operators do not replace durable queues. If the producer is a message broker, evaluate ack/nack, offsets, retries, and dead-letter queues so events are not lost on pipeline failures.

## 11. Controlling Memory with Page Size

For Elasticsearch searches, page size is a primary driver of how much data is fetched per request. Example creating a query with page size 500:

```java
import org.springframework.data.domain.PageRequest;
import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.elasticsearch.core.query.Query;

Query query = NativeQuery.builder()
    .withQuery(q -> q.matchAll(m -> m))
    .withPageable(PageRequest.of(0, 500))
    .build();
```

Then process each hit:

```java
return operations.search(query, ProductDocument.class)
    .map(SearchHit::getContent)
    .flatMap(this::processProduct, 8);
```

Page size and concurrency affect different aspects:

- Larger page size: each response holds more hits, reducing page calls while increasing payload size and response memory.
- Higher concurrency: more processing tasks or requests run simultaneously, increasing in-flight data.
- Larger prefetch: operators request more items ahead, increasing queues.

Do not choose a huge page size merely to cut request counts. Measure average `_source` size, deserialization time, and heap footprint per batch.

## 12. Backpressure Does Not Replace Pagination

A `Flux<SearchHit<T>>` can emit hits from one page, yet a single search request still caps results by `size`. To scan multiple pages, the application must implement a proper pagination loop.

For deep pagination or large exports, Point in Time (PIT) combined with `search_after` can be used when a snapshot and stable sort are required. Scroll can also suit certain batch/export tasks depending on Elasticsearch and client versions.

```text
Open PIT
   |
   v
Search page 1 (size = 500)
   |
   v
Process page 1 with bounded concurrency
   |
   v
Extract sort values of last hit
   |
   v
Search next page with search_after
   |
   +----> repeat until no hits remain
   |
   v
Close PIT
```

Fetch the next page only after the current page has been processed or placed into a bounded queue. Continuously loading new pages before consumers finish earlier ones puts multiple pages on the heap and defeats backpressure.

## 13. Processing Pages Sequentially

With cursor pagination, typically only one next-page request should be active at a time. You can use a reactive recursive flow or `expand`/`concatMap` depending on how cursors are modeled.

Pseudocode:

```java
Mono<Void> scanPages(Cursor cursor) {
    return fetchPage(cursor)
        .flatMap(page -> processPage(page)
            .then(Mono.defer(() -> {
                if (page.nextCursor() == null) {
                    return Mono.empty();
                }
                return scanPages(page.nextCursor());
            })));
}
```

This is a conceptual control pattern; `Cursor`, `Page`, and `fetchPage` are application-defined. The key point is fetching the next cursor only after `processPage` finishes, keeping the number of pages in RAM bounded.

If hits within a page must be processed in parallel, cap concurrency:

```java
Mono<Void> processPage(Page<ProductDocument> page) {
    return Flux.fromIterable(page.items())
        .flatMap(this::processOne, 8)
        .then();
}
```

Do not use unbounded `flatMap` across thousands of hits in a page if every `processOne` opens an Elasticsearch request or external service call.

## 14. Application-Wide Concurrency Limits

The `flatMap(..., 8)` parameter only bounds a single subscription. In a system handling many HTTP requests, schedulers, and consumers, each request creates its own pipeline. Total concurrency scales with simultaneous requests.

Example:

```text
8 active HTTP requests
Each request has flatMap concurrency = 8

Total inner operations can approach 64
```

If each instance runs 64 operations across 5 instances, the cluster can receive roughly 320 operations from this path alone—before counting retries, pagination, and other flows.

### Using a Bulkhead/Semaphore for Shared Limits

If you need to cap total operations against a dependency across multiple requests within an instance, use `flatMap` gated by a reactive semaphore or a bulkhead mechanism like Resilience4j Reactor. Conceptual semaphore example:

```java
Mono<Result> guardedCall(Input input) {
    return Mono.usingWhen(
        acquirePermit(),
        permit -> callElasticsearch(input),
        Permit::release
    );
}
```

`acquirePermit()` and `Permit` are application abstractions implemented so permit acquisition never blocks the event loop and release always runs on complete, error, or cancel. Never call `java.util.concurrent.Semaphore.acquire()` in blocking mode directly on an event-loop thread.

Across multiple instances, an in-JVM semaphore only limits each instance. For a cluster-wide quota, enforce limits at the gateway, queue consumer group, distributed rate limiter, or appropriate operational tier.

## 15. Concurrency Limits for Writes

When writing many documents, do not open a separate request for every element simultaneously:

```java
Flux<ProductDocument> saved = Flux.fromIterable(products)
    .flatMap(repository::save, 8);
```

Concurrency 8 is a starting point for measurement. Tune upward or downward based on:

- Connections available to the reactive client.
- Per-request latency.
- Document size.
- Shard and replica counts.
- Data node CPU, heap, and indexing pressure.
- Retry rate or 429 errors.

For high-throughput ingestion, bulk indexing is usually far more efficient than individual index requests per document. Still, bulk batches must have bounded batch sizes and bounded concurrent bulk requests.

## 16. Grouping Data into Bounded Batches

Reactor can group elements into batches using `buffer(n)` or `bufferTimeout(n, duration)`:

```java
Flux<List<ProductDocument>> batches = source
    .bufferTimeout(500, Duration.ofSeconds(2));
```

A batch is emitted once 500 elements accumulate or 2 seconds elapse. This avoids holding a partial batch indefinitely when source throughput is low.

Sending batches with bounded concurrency:

```java
return source
    .bufferTimeout(500, Duration.ofSeconds(2))
    .flatMap(batch -> bulkIndex(batch), 2);
```

Here each bulk batch has at most 500 items and at most 2 bulk operations run concurrently from this pipeline. If documents are large, 500 items may still create an oversized payload; measure in bytes, not just document counts.

### `buffer` Also Consumes Memory

`buffer(500)` holds up to 500 items per batch prior to emission. With concurrency 2, multiple batches may be in flight simultaneously alongside the batch currently filling. Heap estimates must account for all of these buffers.

Do not use the parameterless `buffer()` on unbounded sources when controlling memory; it can wait for the entire source to finish and emit a single massive list.

## 17. Estimating Pipeline Memory

Exact heap cannot be calculated purely from item counts because document sizes vary and Java objects add overhead. Still, a rough estimate helps pick initial bounds:

```text
Memory in-flight ≈
  active operations × average response/batch size
  + operator queues
  + prefetch buffers
  + application transformation objects
  + client/network buffers
```

For example, a pipeline with 8 concurrent operations, each holding roughly a 4 MB batch, already accounts for around 32 MB of active batch data—excluding queues, source objects, JSON decoding, client buffers, and heap overhead.

If each operation also queues 16 items averaging 100 KB each, the queues can add roughly:

\[
8 \times 16 \times 100\text{ KB} \approx 12.8\text{ MB}
\]

This is only an estimation model. Actual usage depends on operators, prefetch, client response decoding, object graphs, and garbage collection.

### Counting Items Alone Is Not Enough

A queue capped at 1,000 items may be safe for 200-byte events yet dangerous for 2 MB documents. For large payloads, capping page size, byte-based batching, and source filtering matter more than item-count queue caps alone.

## 18. Reducing Payloads with Source Filtering

If only a few fields are needed, avoid fetching the entire `_source`:

```json
{
  "_source": ["id", "name", "category"],
  "query": {
    "term": {
      "status": "ACTIVE"
    }
  }
}
```

Trimming returned fields reduces network payloads, JSON decoding work, and heap object allocations. With Spring Data, use query source filtering or projections supported by your API version.

Avoid fetching blob fields, long descriptions, or large nested payloads when downstream steps do not use them. When details are occasionally needed, fetch them by ID in a separate step with bounded concurrency.

## 19. Avoid `collectList()` on Unbounded Streams

`collectList()` can be fine for small, explicitly bounded results:

```java
return repository.findByCategory("accessories")
    .take(100)
    .collectList();
```

However, it is unsuitable for full index scans or unbounded sources:

```java
return repository.findAll().collectList();
```

Instead, process per element or per batch:

```java
return repository.findByCategory("accessories")
    .flatMap(this::processOne, 8)
    .then();
```

Or group into fixed-size batches:

```java
return repository.findByCategory("accessories")
    .buffer(500)
    .concatMap(this::processBatch)
    .then();
```

If an API must return a list to a client, enforce small page sizes and return a `Page`/cursor instead of buffering the entire dataset into one response.

## 20. Schedulers and Blocking Calls

The reactive Elasticsearch client should be used through its reactive API; never call `.block()` inside an event-loop pipeline.

Avoid:

```java
return repository.findById(id)
    .map(product -> {
        ProductDocument saved = repository.save(product).block();
        return saved;
    });
```

This blocks inside a callback and can stall the event loop. Use composition instead:

```java
return repository.findById(id)
    .flatMap(product -> {
        product.setName("Updated name");
        return repository.save(product);
    });
```

If calling a legacy blocking API is unavoidable, isolate it on `Schedulers.boundedElastic()`:

```java
Mono<Result> result = Mono.fromCallable(() -> legacyBlockingCall())
    .subscribeOn(Schedulers.boundedElastic());
```

Do not move reactive Elasticsearch I/O onto `boundedElastic` by default; the reactive client is already built for asynchronous I/O. `boundedElastic` is for unavoidable blocking segments.

## 21. Cancellation and Resource Cleanup

Reactive Streams allows downstream to cancel a subscription. For example, when a user closes an HTTP connection or a job stops, cancellation can propagate backward through the pipeline.

Applications must ensure cleanup for resources opened during execution:

- PIT contexts.
- Scroll contexts if the API uses scroll.
- Semaphore permits.
- Files or output streams.
- Temporary resources and batch staging state.

For asynchronous resources, `usingWhen` binds cleanup to completion, error, and cancellation paths:

```java
Flux<SearchHit<ProductDocument>> scan = Flux.usingWhen(
    openPit(),
    pit -> fetchPages(pit),
    pit -> closePit(pit),
    (pit, error) -> closePit(pit),
    pit -> closePit(pit)
);
```

`openPit`, `fetchPages`, and `closePit` are application methods implemented for your Elasticsearch client. This demonstrates resource lifecycle management; ensure `closePit` returns a `Publisher` and executes safely even when an active request is canceled.

Client-side cancellation does not always mean Elasticsearch immediately halts a server operation already underway. Treat cancellation as a request to tear down the pipeline/client request, while still managing resources and tasks per the API contract.

## 22. Retries and Backpressure

Retries can amplify concurrency and load if left unbounded. When Elasticsearch returns transient errors such as 429 or certain 5xx responses, retry with backoff:

```java
return repository.save(product)
    .retryWhen(Retry.backoff(3, Duration.ofMillis(200))
        .maxBackoff(Duration.ofSeconds(3))
        .jitter(0.5)
    );
```

This example illustrates retry count and backoff; in production, classify errors before retrying. Never retry mapping, validation, or 400 errors. Version conflicts (409) require re-reading and recomputing state per business rules rather than resending the same payload.

When many concurrent requests retry together, request rates can spike abruptly. Jittered backoff, concurrency caps, and circuit breakers/bulkheads help prevent retry storms.

### Idempotency When Retrying Writes

Retrying a write must be safe if the prior request succeeded yet its response was lost. Use stable document IDs, suitable upsert semantics, or application-level idempotency keys. Never automatically retry operations generating random IDs if duplicates could result.

## 23. Handling Partial Failures in Bulk Pipelines

Bulk requests can partially succeed. A reactive pipeline must not treat a successful HTTP response as proof that every document was indexed.

A sound design can:

1. Assemble bounded-size batches.
2. Send the bulk request.
3. Inspect `errors` and individual item responses.
4. Classify retryable vs. permanent failures.
5. Perform bounded retries only for eligible items.
6. Route permanent failures to a dead-letter store or fail the job.

When using `flatMap` to process multiple bulk batches, limit concurrent batches. Never let an unbounded source queue thousands of pending bulk requests.

## 24. Backpressure in WebFlux Endpoints

Reactive controllers should return `Flux`/`Mono` so the framework coordinates subscription rather than subscribing inside the controller.

Example:

```java
@RestController
@RequestMapping("/products")
public class ProductController {

    private final ProductService service;

    public ProductController(ProductService service) {
        this.service = service;
    }

    @GetMapping(produces = MediaType.APPLICATION_NDJSON_VALUE)
    public Flux<ProductView> streamProducts() {
        return service.streamProducts()
            .map(ProductView::from);
    }
}
```

WebFlux can stream the response and pace demand according to its ability to write data to the client. Yet if the service already called `collectList()` on everything before returning, streaming benefits are lost. Keep the pipeline streaming from Elasticsearch to the response and bound pages and buffers at intermediate stages.

### Avoid Calling `subscribe()` in Services for Out-of-Band Side Effects

Avoid:

```java
public void reindex() {
    repository.findAll()
        .flatMap(this::saveToTarget, 8)
        .subscribe();
}
```

The method returns immediately, errors may go unobserved by the caller, and lifecycle/cancellation are hard to control. Return `Mono<Void>` instead:

```java
public Mono<Void> reindex() {
    return repository.findAll()
        .flatMap(this::saveToTarget, 8)
        .then();
}
```

The caller at the application boundary decides when to subscribe. In WebFlux, the framework subscribes for the request; in a scheduler/job runner, the runner manages subscription and job status.

## 25. Observing Demand, Concurrency, and Queues

To tune backpressure, measure key metrics:

- In-flight Elasticsearch requests.
- Active inner publishers.
- Completion latency per search/index/bulk request.
- Page size and average response size.
- Batch size by item count and by bytes.
- Items sitting in buffers/queues.
- Buffer overflow/drop counts.
- Retry counts and actual retry delays.
- 429, 5xx, and timeout rates.
- Heap usage, allocation rate, and GC pauses.
- Connection pool usage and pending acquisitions.
- Elasticsearch search/indexing thread pools, indexing pressure, and node CPU.

Reactor offers the `doOnRequest` hook to inspect demand during diagnostics:

```java
Flux<ProductDocument> pipeline = repository.findAll()
    .doOnRequest(n -> metrics.recordRequested(n))
    .flatMap(this::processOne, 8, 16);
```

`doOnRequest` can fire repeatedly with varying demand values. Never log every call at INFO level in high-throughput production; use metrics/counters or sampled logging instead.

## 26. Choosing Page Size, Concurrency, and Prefetch per Workload

A practical approach is tuning one variable at a time:

| Workload | Initial page/batch size | Initial concurrency | Notes |
|---|---:|---:|---|
| Interactive search API | 20–100 hits | 1–4 downstream calls | Prioritize low latency and small payloads |
| Data export | 500 hits/page | 2–4 page processors | Use PIT + search_after or suitable scan; avoid holding multiple pages |
| Bulk ingestion | 200–1,000 docs/batch | 1–4 bulk requests | Tune by byte size and bulk latency |
| External service enrichment | Small batches | 4–8 calls | Respect dependency rate limits |
| CPU-heavy processing | Heap-budgeted batches | Workers sized to CPU | Separate CPU work from reactive I/O when needed |

These are starting points for benchmarking, not universal production defaults. Document size, cluster topology, and SLAs can shift optimal values significantly.

## 27. An End-to-End Bounded Reactive Pipeline

Example combining page size, bounded concurrency, and batched output:

```java
public Mono<Void> exportProducts(Query query) {
    return operations.search(query, ProductDocument.class)
        .map(SearchHit::getContent)
        .limitRate(64)
        .flatMap(this::transformProduct, 8, 8)
        .buffer(200)
        .concatMap(this::writeExportBatch)
        .then();
}
```

Explanation:

- The search query must define an appropriate page size; `limitRate` only paces demand on the publisher.
- `flatMap(..., 8, 8)` limits concurrent transform publishers and per-inner prefetch.
- `buffer(200)` groups up to 200 transformed items into a batch.
- `concatMap` writes each batch sequentially, one batch at a time.
- `then()` turns the pipeline into a `Mono<Void>` signaling completion.

If `writeExportBatch` slows down, demand scales back through upstream operators. Buffers remain finitely bounded as configured. For datasets larger than a single page, add a sequential pagination loop/cursor to fetch subsequent pages; this snippet does not turn a single search page into a full index scan.

## 28. Common Pitfalls

### Assuming `Flux` Automatically Protects the Heap

`collectList`, unbounded buffers, oversized pages, or too many inner publishers can still retain unbounded data. Cap every queue and page.

### Using Unbounded `flatMap` for Elasticsearch Requests

In-flight requests can grow with source speed. Specify explicit concurrency and factor in total concurrency across requests and instances.

### Confusing `limitRate` with Concurrency Limits

`limitRate` paces demand; `flatMap` concurrency limits active inner publishers. Pick the right operator for each goal.

### Using Unbounded `onBackpressureBuffer()`

Queues can grow forever when consumers slow down. Use a finite capacity and an explicit overflow policy.

### Dropping Business Data When Buffers Fill

`DROP_OLDEST`, `DROP_LATEST`, and `onBackpressureDrop` lose elements. Only use them for droppable data; business events need durable queues or fail/retry behavior.

### Raising Page Size Just to Reduce Request Counts

Oversized responses increase heap usage and deserialization latency. Measure in bytes and apply source filtering.

### Using `flatMapSequential` Without Accounting for Buffers

Inner publishers completing early must wait for earlier ones, growing buffered data. Preserve ordering only when business rules require it.

### Calling `.block()` or `.subscribe()` in Services

Blocking can stall event loops; internal subscriptions forfeit caller control over lifecycle and errors. Compose publishers and return them to the caller.

### Retrying Indefinitely on Elasticsearch 429

Unbounded retries cause retry storms. Use backoff, jitter, max attempts, and concurrency caps.

### Loading the Next Page Before Finishing the Current Page

Multiple pages can coexist in heap simultaneously. Process pages sequentially or via a strictly bounded queue.

## 29. Workflow for Designing a Safe Reactive Pipeline

When building reactive search, export, or ingestion pipelines:

1. Define target throughput, latency, and search visibility requirements.
2. Estimate average and worst-case document/response sizes.
3. Choose a bounded page size or bulk batch size.
4. Choose `flatMap` concurrency based on dependency capacity.
5. Configure prefetch and `limitRate` if demand pacing is needed.
6. Avoid `collectList()` and unbounded buffers on large/unbounded sources.
7. Pick an overflow policy; only drop data that can safely be lost.
8. Bound total concurrency across simultaneous requests and instances.
9. Use cursor pagination for multi-page scans without pre-fetching too many pages.
10. Isolate blocking calls off the event loop and never block the reactive Elasticsearch client.
11. Implement cancellation/cleanup for PIT, scroll, permits, and other resources.
12. Retry transient errors with backoff/jitter and idempotency.
13. Monitor in-flight requests, queues, heap, GC, 429s, latency, and Elasticsearch node metrics.
14. Benchmark adjustments to each bound before production rollout.

## 30. Conclusion

Backpressure allows downstream to pace demand to upstream, yet it does not automatically cap Elasticsearch response sizes, total requests opened across pipelines, or heap memory consumption. In Reactor, `flatMap` with explicit concurrency limits active inner publishers; `concatMap` serializes; `flatMapSequential` preserves order at the cost of buffering; `limitRate` splits demand into batches; `onBackpressure...` operators govern behavior when downstream cannot keep up.

To control memory, cap page size, batch size, prefetch, queue capacity, and in-flight pages. Avoid `collectList()` on large sources, avoid unbounded buffers, and only drop data when loss is acceptable. With Spring Data Elasticsearch Reactive, keep pipelines as `Flux`/`Mono`, avoid `.block()` or manual `subscribe()` inside services, cap concurrency relative to application-wide load, paginate sequentially, and clean up resources on cancellation. Finally, rely on metrics and benchmarks to balance throughput, latency, heap usage, and Elasticsearch load.

## References

- [Project Reactor – Reference Guide: Backpressure](https://projectreactor.io/docs/core/release/reference/coreFeatures/request.html)
- [Project Reactor – `Flux` API](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html)
- [Project Reactor – `Mono` API](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html)
- [Reactive Streams – Specification](https://www.reactive-streams.org/)
- [Spring Data Elasticsearch – Reactive Elasticsearch Operations](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/reactive-template.html)
- [Spring Data Elasticsearch – Reactive Repositories](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/repositories/reactive.html)
- [Elasticsearch – Paginate search results](https://www.elastic.co/docs/reference/elasticsearch/rest-apis/paginate-search-results)
- [Elasticsearch – Point in Time API](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-open-point-in-time)
