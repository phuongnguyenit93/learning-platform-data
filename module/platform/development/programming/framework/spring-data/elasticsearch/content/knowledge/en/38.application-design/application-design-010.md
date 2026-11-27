# Choosing Imperative or Reactive Based on Real Load Patterns

Spring Data Elasticsearch provides two API families for working with Elasticsearch: imperative (synchronous) APIs and reactive (non-blocking) APIs. Choosing between them should be based on workload characteristics, application architecture, how other dependencies behave, and the team's operational capabilities.

Imperative APIs generally fit standard request-response services, moderate CRUD, Spring MVC applications, and business flows naturally expressed sequentially. Reactive APIs benefit applications that hold many concurrent I/O requests waiting simultaneously, already use Reactor/WebFlux end-to-end, or need stream processing with backpressure.

Reactive does not make Elasticsearch execute a single query faster, nor does it automatically raise cluster throughput. It helps the application utilize threads more efficiently while waiting on I/O, while offering a model for data streams and demand regulation. If concurrency increases excessively, a reactive application can still overload Elasticsearch, triggering HTTP 429s, timeouts, and queue backlogs.

A sound decision weighs request rate, concurrency, latency, result sizes, batch sizes, CPU processing time, blocking dependencies, and the operational complexity the system can sustain.

## 1. Two models in Spring Data Elasticsearch

Spring Data Elasticsearch offers imperative and reactive APIs with corresponding abstractions:

| Model | Repository | Template/Operations | Common return types |
|---|---|---|---|
| Imperative | `ElasticsearchRepository` | `ElasticsearchOperations` / `ElasticsearchTemplate` | Entity, `Optional`, `List`, `Page`, `SearchHits` |
| Reactive | `ReactiveElasticsearchRepository` | `ReactiveElasticsearchOperations` / `ReactiveElasticsearchTemplate` | `Mono<T>`, `Flux<T>`, `Mono<SearchHits<T>>` or `Flux<SearchHit<T>>` depending on API |

Imperative repository example:

```java
public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {

    Optional<Product> findBySku(String sku);

    List<Product> findByStatus(String status);
}
```

Reactive repository:

```java
public interface ReactiveProductRepository
        extends ReactiveElasticsearchRepository<Product, String> {

    Mono<Product> findBySku(String sku);

    Flux<Product> findByStatus(String status);
}
```

Both repositories describe the same domain operations yet differ in how results are represented and how callers wait for data.

### 1.1. Imperative: call and wait for result

With imperative APIs, a repository call returns the result after the operation completes:

```java
public Product findRequired(String id) {
    return repository.findById(id)
            .orElseThrow(() -> new ProductNotFoundException(id));
}
```

The calling thread waits for I/O to finish before continuing. This style is easy to read, easy to debug via call stacks, and suits sequential programming models.

### 1.2. Reactive: return a publisher

With reactive APIs, the service returns a publisher describing a future result:

```java
public Mono<Product> findRequired(String id) {
    return repository.findById(id)
            .switchIfEmpty(Mono.error(
                    new ProductNotFoundException(id)));
}
```

Publishers are typically lazy: requests execute when subscribed to. Threads do not sit idle waiting for Elasticsearch responses; when I/O finishes, signals emit to subscribers and Reactor resumes the chain.

Reactive APIs fit when upstream layers also understand publishers, such as WebFlux controllers returning `Mono`/`Flux`. If code ends up calling `block` on every request, most non-blocking benefits are lost.

## 2. Distinguishing blocking I/O and non-blocking I/O

In the blocking model, a thread typically executes a request, waits for a response, and then continues processing. With many concurrent requests, the application generally needs many request threads to hold waiting requests.

In the non-blocking model, a thread initiates I/O and yields execution while waiting. Once data is ready, the runtime invokes callbacks/signals to resume processing. A small pool of event-loop threads can serve many concurrent I/O connections.

```text
Blocking
Request A: [process] [wait for Elasticsearch] [process response]
Request B: [process] [wait for Elasticsearch] [process response]
Request C: [process] [wait for Elasticsearch] [process response]
             each request holds a thread while waiting

Non-blocking
Event loop: [start A] [start B] [start C] [handle A] [handle C] [handle B]
             threads are reused while requests wait for I/O
```

This does not mean reactive uses no threads or makes Elasticsearch process faster on its own. Reactive still needs threads for callbacks, serialization/deserialization, mapping, and business logic. The primary difference is threads are not pinned solely waiting on network I/O.

### 2.1. Blocking does not mean bad design

A service handling a few requests per second with fast queries and straightforward logic can run very well on imperative APIs. Simple call stacks, exception handling, and transaction boundaries may outweigh rewriting the whole codebase as reactive.

### 2.2. Non-blocking does not mean parallel

A reactive chain does not automatically run every step concurrently. For example:

```java
return repository.save(product)
        .flatMap(saved -> repository.findById(saved.getId()));
```

The `find` depends on the `save` result, so it begins only after `save` emits a value. Reactive avoids blocking threads while waiting; it does not eliminate sequential business dependencies.

When multiple operations are independent, combine them with `zip` or bounded-concurrency `flatMap`. Pick operators based on dependency order and allowed load.

## 3. Load patterns matter more than the sync/reactive label

Before choosing an API, characterize application load:

- Average and peak request rate (requests/second).
- Concurrent requests at peak times.
- p50, p95, and p99 Elasticsearch latency.
- Read/write ratio.
- Request/response sizes and documents per operation.
- CPU time for transforming, validating, and mapping data.
- Number of dependencies called per request.
- Rates of timeouts, retries, HTTP 429s, and bulk item errors.
- Load growth over time and latency/SLA targets.

Two applications both handling 100 requests/second can have very different needs. One completing requests in 5 ms and another waiting 300 ms on Elasticsearch have vastly different in-flight request counts.

### 3.1. Request rate and concurrency

A helpful estimate from Little's Law:

```text
Approximate in-flight requests
    throughput (requests/second) x latency (seconds)
```

For example, if an application processes 200 requests/second and average dependency wait time is 50 ms:

```text
200 requests/second x 0.05 seconds = about 10 in-flight requests
```

This is only a steady-state estimate, not a direct thread or connection pool sizing formula. Measure CPU work, queueing, bursts, and latency distributions as well.

When latency rises, in-flight requests climb even if request rate stays flat. Without concurrency limits, backlogs grow and trigger cascading timeouts.

### 3.2. I/O-bound vs. CPU-bound workloads

| Load type | Examples | Impact of reactive |
|---|---|---|
| I/O-bound | Waiting on Elasticsearch, databases, or HTTP services | Can use threads more efficiently when many requests wait simultaneously. |
| CPU-bound | Image analysis, heavy encryption, large calculations, complex document transforms | Does not reduce required CPU; needs dedicated workers/schedulers and CPU limits. |
| Mixed | Querying Elasticsearch then processing heavy data in app | Helps on the I/O portion, but heavy CPU work must be isolated off the event loop. |

If most time is spent on CPU, switching to reactive adds zero CPU capacity. If most time is waiting on I/O under high concurrency, reactive can reduce the need for numerous platform threads.

## 4. When are imperative APIs usually suitable?

Choose imperative APIs when most of these hold:

- The application uses Spring MVC and dependencies are largely blocking.
- Request-response flows have few sequential steps cleanly expressed synchronously.
- Concurrency is moderate and already meets SLAs.
- Services do not need to stream continuous results downstream.
- Batch operations can run via bounded jobs/workers.
- The team prefers direct call stacks, debugging, and simple exception handling.
- Measurements show no thread bottleneck from waiting on I/O.

Imperative service example:

```java
@Service
public class ProductService {

    private final ProductRepository repository;

    public ProductService(ProductRepository repository) {
        this.repository = repository;
    }

    public Product create(Product product) {
        return repository.save(product);
    }

    public Product getRequired(String id) {
        return repository.findById(id)
                .orElseThrow(() -> new ProductNotFoundException(id));
    }
}
```

Spring MVC controller:

```java
@RestController
@RequestMapping("/products")
public class ProductController {

    private final ProductService service;

    public ProductController(ProductService service) {
        this.service = service;
    }

    @PostMapping
    public Product create(@RequestBody Product product) {
        return service.create(product);
    }

    @GetMapping("/{id}")
    public Product get(@PathVariable String id) {
        return service.getRequired(id);
    }
}
```

This model is readable and typically a sensible starting point for CRUD services. Only evaluate non-blocking or virtual threads if measurements show platform threads piling up on I/O waits.

## 5. When is reactive usually suitable?

Reactive is worth considering when:

- The application holds many concurrent waiting I/O-bound requests.
- Most dependencies already offer non-blocking APIs.
- The application uses Spring WebFlux/Reactor end-to-end.
- Multiple publishers must be composed with explicit concurrency control.
- Large data streams must be processed on demand rather than buffered in memory.
- Cancellation/deadline propagation is needed in asynchronous workflows.
- The team understands Reactor, backpressure, context propagation, and debugging reactive chains.

Reactive service example:

```java
@Service
public class ReactiveProductService {

    private final ReactiveProductRepository repository;

    public ReactiveProductService(ReactiveProductRepository repository) {
        this.repository = repository;
    }

    public Mono<Product> create(Product product) {
        return repository.save(product);
    }

    public Mono<Product> getRequired(String id) {
        return repository.findById(id)
                .switchIfEmpty(Mono.error(
                        new ProductNotFoundException(id)));
    }

    public Flux<Product> findActive() {
        return repository.findByStatus("ACTIVE");
    }
}
```

WebFlux controller:

```java
@RestController
@RequestMapping("/products")
public class ReactiveProductController {

    private final ReactiveProductService service;

    public ReactiveProductController(ReactiveProductService service) {
        this.service = service;
    }

    @PostMapping
    public Mono<Product> create(@RequestBody Product product) {
        return service.create(product);
    }

    @GetMapping("/{id}")
    public Mono<Product> get(@PathVariable String id) {
        return service.getRequired(id);
    }

    @GetMapping
    public Flux<Product> findActive() {
        return service.findActive();
    }
}
```

The controller returns publishers so the WebFlux runtime manages subscriptions and response lifecycles. Services do not call `subscribe` or `block`.

### 5.1. Reactive shines when multiple dependencies are non-blocking

Suppose a request calls Elasticsearch and another HTTP service:

```java
public Mono<ProductView> loadProductView(String id) {
    Mono<Product> product = productRepository.findById(id);
    Mono<Inventory> inventory = inventoryClient.getInventory(id);

    return Mono.zip(product, inventory)
            .map(tuple -> new ProductView(
                    tuple.getT1(),
                    tuple.getT2()
            ));
}
```

Both independent operations run concurrently and combine once both emit results. With blocking APIs, equivalent code needs two threads or sequential execution. Real gains depend on per-dependency latency and system concurrency.

If one dependency remains blocking, handle it separately; merely wrapping an entire flow in `Mono` does not make a blocking call non-blocking.

## 6. Operational comparison

| Criterion | Imperative | Reactive |
|---|---|---|
| Programming model | Sequential call/return | Publishers, signals, and operators |
| Threads while waiting on I/O | Typically held | Can be reused |
| High concurrent requests | Usually needs more request threads | Event loop can serve many waiting I/Os |
| Backpressure | Usually manual via queues/workers/batches | Built-in demand mechanism in Reactive Streams |
| Debugging | Direct call stacks | More complex chains/operators and context |
| Exceptions | `try/catch` and `throw` | `onError` signals and error operators |
| Cancellation | Typically per thread/request/task | Subscription cancellation, though no server rollback guarantee |
| Composing dependencies | Sequential calls or concurrency utilities | `zip`/`flatMap`/`concatMap` and publisher composition |
| Integrating blocking libraries | Natural | Must isolate on schedulers or adapters |
| Team complexity | Usually lower | Requires Reactor expertise and fitting observability |
| Performance | Good for moderate load and simple models | Can be more efficient at high I/O concurrency |
| Elasticsearch capacity | Bounded by cluster/client | Still bounded by cluster/client |

Neither model is universally faster. Evaluate using real workloads and end-to-end metrics.

## 7. Understanding threads and connection pools accurately

Reactive does not eliminate connection limits. Even when event-loop threads do not block, requests still need sockets/connections and Elasticsearch still has to execute them.

An application may have:

- Event-loop threads.
- HTTP connection pools.
- Connection acquisition queues.
- In-flight requests.
- Send/receive buffers.
- Workers for CPU or blocking tasks.

If a pool permits only a fixed number of connections, spawning more publishers does not increase simultaneous executions indefinitely. On the contrary, creating too many publishers inflates queues, memory, and latency.

### 7.1. Connection limits are not the only concurrency limit

Effective concurrency also depends on:

- Connection pools and available connections.
- HTTP transport.
- Node counts and shard distribution.
- Elasticsearch queues/thread pools.
- Request sizes and processing times.
- Requests from other services sharing the cluster.

Never increase the connection pool merely to clear queue warnings. If Elasticsearch is already saturated, more connections worsen overload.

### 7.2. Connection pools in the imperative model

Imperative clients typically reuse connections via pools. Threads may wait when connections are busy or requests have not completed. Monitor pool acquisition timeouts, leased/available counts, and request durations.

### 7.3. Connection pools in the reactive model

Reactive clients also enforce connection caps and pending acquire queues. Non-blocking changes how the application waits; it does not turn a finite pool into infinite capacity. Size pending acquire limits and in-flight work to match cluster capacity.

## 8. Reactive does not increase Elasticsearch throughput by itself

Suppose a cluster stably handles 1,000 writes/second under the current workload. Switching the client from imperative to reactive does not turn capacity into 2,000 operations/second.

Reactive can help the application:

- Maintain many waiting requests without a platform thread per request.
- Compose independent I/Os.
- Regulate demand in certain pipelines.
- Reduce context switching from excessive waiting threads.

Cluster throughput still hinges on CPU, disk, shards, refreshes, replicas, mappings, ingest pipelines, and request sizes. If reactive lets the application push requests faster, the cluster can receive more traffic than it can handle and begin returning 429s.

### 8.1. Increasing concurrency can worsen p99

At low load, raising concurrency can raise throughput. Near saturation, adding concurrency usually increases queueing and tail latency. p50 may look fine while p99 spikes because some requests wait longer or retry.

Measure p50/p95/p99, 429s, timeouts, and queue depths before raising concurrency.

## 9. Backpressure and load limiting

Reactive Streams implements demand: subscribers request the number of elements they can handle. This regulates flow between publishers and subscribers.

Example:

```java
Flux<Product> products = repository.findByStatus("ACTIVE");

products
        .limitRate(100)
        .map(this::toExportRow)
        .subscribe(exportWriter::write);
```

`limitRate` adjusts how Reactor requests data from upstream. It does not mean Elasticsearch queries only 100 documents total, nor does it cap total results. To bound total elements, use `take(n)` or configure query sizes appropriately.

Backpressure only works end-to-end when publishers/operators and data sources honor demand. If code collects everything into a `List`, calls `collectList`, or buffers in unbounded queues, the application can still blow up heap.

### 9.1. flatMap can issue too many requests

Example without concurrency limits:

```java
Flux<Void> writes = products
        .flatMap(product -> repository.save(product))
        .then();
```

On large sources, many saves can be subscribed simultaneously, pressuring connection pools and Elasticsearch.

Bound concurrency:

```java
Mono<Void> writes = products
        .flatMap(product -> repository.save(product), 8)
        .then();
```

Or process sequentially when order matters:

```java
Mono<Void> writes = products
        .concatMap(repository::save)
        .then();
```

`8` is purely an example. Benchmark and monitor rejections/latency to pick suitable concurrency.

### 9.2. concatMap, flatMap, and flatMapSequential

| Operator | Behavior | When suitable |
|---|---|---|
| `concatMap` | Subscribes to inner publishers sequentially; waits for current one to complete. | Ordering required and low concurrency. |
| `flatMap` | Allows inner publishers to run concurrently; outputs may interleave. | Independent operations with bounded concurrency. |
| `flatMapSequential` | Inner publishers can run concurrently while outputs preserve source order. | Concurrency wanted while preserving output order. |

Never choose an operator based on speed alone. If operations mutate the same document, ordering can be part of correctness.

## 10. Large read workloads: streaming or pagination?

An endpoint returning dozens of products can use standard queries/pages. Exporting millions of documents needs a different design:

- Limit hits per fetch.
- Process batch by batch instead of holding all results in heap.
- Use PIT and `search_after` for large dataset scans when appropriate.
- Maintain checkpoints to resume after failures.
- Rate-limit to match downstream sinks (file writers, object storage, message brokers).
- Close resources/scrolls/PITs properly per lifecycle.

Reactive can express downstream processing with `Flux`, yet it does not guarantee Elasticsearch queries always stream document-by-document from the server without buffering. Behavior depends on Spring Data APIs, how searches execute, and client versions. Inspect specific APIs and measure actual memory.

Imperative code can also process large datasets using batches, scroll/PIT, iterators, or bounded workers. Do not rewrite an entire app as reactive just for one export job.

## 11. Large write workloads: bulk matters more than reactive

For writing many documents, the decisive factors are:

- Bulk requests instead of one request per document.
- Batch sizes by byte size and item count.
- In-flight bulk request count.
- Mappings, analyzers, and ingest pipelines.
- Shard distribution and refresh policies.
- Retrying 429s with backoff/jitter.
- Checkpoints and dead-letter handling for failed items.

A reactive pipeline can build batches and dispatch them with bounded concurrency. An imperative job can use a worker pool and bulk adapter. Both perform well when queues and batches are bounded reasonably.

Reactive batch example:

```java
Mono<Void> importProducts(Flux<Product> source) {
    return source
            .buffer(500)
            .concatMap(batch -> bulkWriter.write(batch))
            .then();
}
```

Limiting two concurrent batches:

```java
Mono<Void> importProducts(Flux<Product> source) {
    return source
            .buffer(500)
            .flatMap(batch -> bulkWriter.write(batch), 2)
            .then();
}
```

These illustrate orchestration; `bulkWriter.write` needs a contract for item-level failures, retries, and checkpoints. Never assume `saveAll(Publisher)` always equals a single optimal Bulk API request.

If the data source is blocking JDBC, putting `Flux` downstream does not make JDBC non-blocking. Use a dedicated batch reader/worker or isolate blocking sources on an appropriate scheduler.

## 12. Spring MVC, WebFlux, and persistence models

### 12.1. Spring MVC + imperative repository

```text
HTTP request
    |
Spring MVC request thread
    |
Imperative service
    |
ElasticsearchRepository
    |
Blocking HTTP client
    |
Elasticsearch
```

The request thread waits for the result. Size thread pools, connection pools, and timeouts according to load.

### 12.2. WebFlux + reactive repository

```text
HTTP request
    |
WebFlux event loop
    |
Reactive service (Mono/Flux)
    |
ReactiveElasticsearchRepository
    |
Non-blocking HTTP client
    |
Elasticsearch
```

Event-loop threads are not pinned waiting on Elasticsearch responses. Other dependencies in the same request should also be non-blocking to preserve end-to-end benefits.

### 12.3. Can Spring MVC return publishers?

Spring MVC supports certain reactive return types and can adapt publishers. However, returning `Mono`/`Flux` from a controller does not turn the whole application into WebFlux or make blocking dependencies non-blocking.

Evaluate the full request lifecycle, executors, streaming responses, and dependencies before deciding. Do not adopt WebFlux just because one controller returns `Flux`.

### 12.4. Never call blocking repositories on the event loop

This is an anti-pattern:

```java
@GetMapping("/{id}")
public Mono<Product> get(@PathVariable String id) {
    Product product = blockingRepository.findById(id).orElseThrow();
    return Mono.just(product);
}
```

The repository call already blocked before `Mono` was returned. The event-loop thread was held waiting.

If a blocking dependency cannot be replaced yet, isolate it:

```java
@GetMapping("/{id}")
public Mono<Product> get(@PathVariable String id) {
    return Mono.fromCallable(() ->
                    blockingRepository.findById(id).orElseThrow())
            .subscribeOn(Schedulers.boundedElastic());
}
```

This is a temporary bridge. It remains blocking I/O, merely offloaded onto a scheduler meant for blocking tasks. Cap load and plan replacement if workloads demand end-to-end non-blocking execution.

Never call `block` on a WebFlux event-loop thread.

## 13. Should an app that only calls Elasticsearch use reactive?

Not necessarily. If a request calls one repository method, maps a few fields, and returns a response, imperative APIs can be simpler and fast enough.

Reactive can still help if:

- Request concurrency is very high and Elasticsearch wait time dominates the lifecycle.
- Current thread pools are a measured bottleneck.
- The application holds many streaming connections.
- Other dependencies already expose reactive APIs.

Conversely, if Elasticsearch is the only reactive dependency while the rest is blocking JPA/JDBC, blocking filesystems, and synchronous libraries, converting part of the stack to reactive can introduce awkward conversion boundaries that outweigh the gains.

Decide from measurements, not because reactive seems more modern.

## 14. Virtual threads and imperative APIs

On Java 21+, virtual threads can make blocking models scale better in I/O-bound applications. Virtual threads allow many blocking tasks to exist without dedicating an OS platform thread to each task in most suitable situations.

This shifts the trade-off between imperative and reactive:

- Imperative code keeps call stacks and exception flows simple.
- Many I/O-bound tasks can park on virtual threads with lower thread overhead than platform threads.
- You do not need to rewrite the whole app to Reactor just to avoid creating too many platform threads.
- Connection pools, Elasticsearch capacity, CPU, memory, and queues remain hard limits.
- Some blocking/native operations or `synchronized` regions can affect virtual thread unmounting depending on JDK/version.

Virtual threads do not turn imperative clients into non-blocking clients. They change how the JVM manages waiting threads. Benchmark with your JDK, Spring Boot, HTTP client, and real workload.

If a project already uses WebFlux/Reactor end-to-end, reactive retains advantages in composition, backpressure, and streaming. If an MVC app uses blocking libraries and prefers simpler code, virtual threads are worth evaluating.

## 15. Never mix imperative and reactive haphazardly

An application can use both models at clear boundaries, but explicit rules are required.

Avoid:

- Reactive services calling `block` to fetch imperative results.
- Imperative services calling `subscribe` and returning before work completes.
- WebFlux event loops calling JDBC or imperative Elasticsearch directly.
- Reactive pipelines bouncing across multiple schedulers unnecessarily.
- Stacking retries across HTTP client, service, and queue consumer without an overall retry budget.

### 15.1. Do not use subscribe for fire-and-forget in services

Anti-pattern:

```java
public void save(Product product) {
    reactiveRepository.save(product).subscribe();
}
```

Callers cannot tell whether the operation succeeded or failed. Errors may go unhandled, and request lifecycles no longer encompass the save.

Return the publisher instead:

```java
public Mono<Product> save(Product product) {
    return reactiveRepository.save(product);
}
```

If background execution is genuinely needed, use a scheduler/queue/job runner with clear ownership, state tracking, error handling, and shutdown management.

### 15.2. Do not use block as a default adapter

Example:

```java
public Product find(String id) {
    return reactiveRepository.findById(id).block();
}
```

This turns a reactive API blocking. If invoked from an event loop, it can throw or cause starvation. If the caller layer is imperative, use an imperative repository or a dedicated boundary rather than bridging back and forth in every method.

## 16. Managing CPU-bound work in reactive applications

Reactor event loops must stay responsive. Never execute heavy CPU work or long blocking operations directly on event-loop threads.

Example:

```java
return repository.findById(id)
        .publishOn(Schedulers.parallel())
        .map(this::expensiveCpuTransformation);
```

Choose the scheduler matching the workload. `Schedulers.parallel()` suits short CPU-bound tasks; `Schedulers.boundedElastic()` is meant for blocking tasks. Do not hop across schedulers on every reactive step without good reason.

If transforms are heavy, bound concurrency and monitor queue/scheduler saturation. A `Flux` can deliver data faster than downstream CPUs can process; backpressure and buffers must stay bounded.

## 17. Timeouts, cancellation, and retries in both models

Imperative:

- Timeouts are typically expressed via client/request timeouts and exceptions.
- Callers wait until results or errors return.
- Cancellation may involve thread interruption or request aborts depending on client.

Reactive:

- The `timeout` operator enforces publisher deadlines.
- Subscriber cancellation stops waiting/receiving signals on the app side.
- Cancellation does not guarantee Elasticsearch rolls back a write already received by the server.
- Retries are expressed via operators yet still require idempotency and retry budgets.

Reactive timeout example:

```java
return repository.findById(id)
        .timeout(Duration.ofSeconds(2))
        .onErrorMap(TimeoutException.class,
                error -> new ProductSearchTimeoutException(id, error));
```

Publisher timeouts are not necessarily identical to HTTP transport timeouts. Configure and observe connection timeouts, response timeouts, application deadlines, and proxy timeouts together.

Never blindly retry every timeout. For writes, the server may have processed the request before the response was lost. Use stable IDs, versions, or reconciliation mechanisms.

## 18. Read loads: choosing by size and consumption pattern

| Use case | Recommendation |
|---|---|
| GET by ID returning one document | Either imperative or reactive fits; match app stack. |
| Search returning dozens of results for an API | Imperative is usually simpler; reactive helps if already on WebFlux. |
| Multiple independent searches in one request | Reactive can zip publishers; imperative can use concurrency utilities. |
| Large data exports | Use batching/cursors/PIT, memory bounds, and checkpoints; reactive is optional, not mandatory. |
| Streaming responses to clients | Reactive/WebFlux fits well if the full path supports streaming and backpressure. |
| Searches with heavy aggregations | Optimizing queries, mappings, and aggregation size matters more than API style. |

For large exports, avoid loading all data into a `List` or `collectList`. Stream in batches/cursors to the destination. Close PITs/scrolls on completion or cancellation.

## 19. Write loads: choosing by batching and reliability

For writing many documents, key factors are:

- Bulk API and batch sizes.
- Payload byte sizes.
- In-flight batch counts.
- Refresh policies.
- 429 retries and item-level failure handling.
- Idempotency and checkpoints.
- Dead-letter handling for invalid records.

Imperative jobs can read batches, call bulk operations, and inspect responses. Reactive jobs can express sources as `Flux`, buffer into batches, and bound concurrency. Both must inspect individual items in bulk responses.

Never assume `ReactiveElasticsearchRepository.saveAll` automatically sends an optimal single bulk request or guarantees every item succeeds. Check your version's API/implementation and use explicit bulk APIs when throughput matters.

## 20. Decision matrix by load pattern

| Load pattern / architecture | Initial choice | Reason |
|---|---|---|
| Internal CRUD, low/moderate concurrency, Spring MVC | Imperative | Simple, easy to operate, usually sufficient capacity. |
| Request-response API, one Elasticsearch query | Imperative or reactive matching stack | Do not switch stacks for a single repository call. |
| End-to-end WebFlux, all dependencies non-blocking | Reactive | Keeps execution non-blocking from HTTP to Elasticsearch. |
| Very high concurrent I/O-bound requests | Evaluate reactive or virtual threads | Reduces platform threads held waiting on I/O. |
| Multiple reactive dependencies to compose | Reactive | Clean publisher composition with cancellation/backpressure. |
| Heavy CPU-bound transformations | Either, with suitable worker model | Reactive does not reduce required CPU work. |
| High-volume import/export | Batching + bounded concurrency; imperative or reactive | Batching, memory, and checkpoints matter far more than API style. |
| App uses blocking JPA/JDBC throughout | Imperative is usually simpler | Avoids multiple blocking/reactive boundaries. |
| Java 21+ MVC, I/O-bound workload | Benchmark imperative with virtual threads vs. reactive | Both options have distinct trade-offs. |
| Team inexperienced with Reactor | Imperative first | Lowers operational risk and learning overhead. |

This matrix guides only initial selection. Benchmarks and production telemetry must drive final conclusions.

## 21. Benchmarking procedure before switching

Do not decide from a single isolated microbenchmark. Simulate the real request path:

1. Use the same Elasticsearch version, mappings, shards, and dataset.
2. Use the same queries, sorts, aggregations, and result sizes.
3. Use the same HTTP client timeouts, connection limits, and TLS/security settings.
4. Simulate low, average, peak, and burst traffic.
5. Measure p50/p95/p99 latency, throughput, and error rates.
6. Monitor CPU, heap, GC, platform threads, event-loop utilization, and connection pools.
7. Monitor Elasticsearch thread pools, indexing pressure, 429s, and search latency.
8. Run long enough to observe queue/backlog growth and memory stability.
9. Test dependency faults, timeouts, retries, and cancellations.
10. Compare code complexity, debuggability, and operational cost.

When comparing imperative against reactive, do not simultaneously alter batch sizes, connection pools, shard counts, or queries. Changing multiple variables hides where improvements actually came from.

### 21.1. Metrics to collect

| Group | Metrics |
|---|---|
| Requests | Requests/second, in-flight requests, p50/p95/p99 latency. |
| Errors | HTTP 429, timeouts, 5xx, mapping errors, bulk item failures. |
| JVM | CPU, heap, GC pauses, allocation rate, platform thread count. |
| Reactive runtime | Event-loop utilization, scheduler queues, pending tasks. |
| HTTP client | Leased/available connections, pending acquires, connection timeouts. |
| Elasticsearch | Search/write latency, thread pool queues/rejections, indexing pressure, node CPU/disk. |
| Pipeline | Batch counts/bytes, queue depths, retry counts, DLQ counts, checkpoint lag. |

Do not look solely at average throughput. A setup with higher throughput yet surging p99 or frequent 429s may violate SLAs.

## 22. Warning signs of a mismatched model or configuration

### 22.1. Signs imperative needs re-evaluation

- Platform thread counts climb sharply alongside waiting requests.
- Thread pools frequently exhaust or request queues grow.
- I/O wait dominates total request duration.
- Many concurrent requests simply wait on non-blocking-capable dependencies.
- Peak traffic triggers thread exhaustion even when Elasticsearch still has headroom.

These symptoms alone do not prove reactive is mandatory. First evaluate tuning timeouts, pools, caching, queries, virtual threads, or reducing round trips.

### 22.2. Signs reactive is overloading the system

- HTTP 429s/rejections climb as concurrency rises.
- Pending connection acquires or scheduler queues grow.
- Heap climbs due to unbounded buffers/`collectList`/queues.
- p99 worsens even while throughput flattens.
- Event loops get blocked by JDBC, logging, or heavy CPU transforms.
- Layered retries amplify request volume.

The fix is bounding in-flight work, adding backpressure, capping buffers/concurrency, and moving blocking work off event loops.

## 23. Hybrid architectures can make sense

A system does not have to force one model on every module. For example:

```text
Spring MVC API
   |
   +---- ProductService (imperative)
   |          |
   |          +---- ElasticsearchRepository
   |
   +---- ExportJob
              |
              +---- ReactiveElasticsearchOperations
                        |
                        +---- bounded Flux -> file/object storage
```

A hybrid architecture makes sense when boundaries are clear:

- CRUD APIs use imperative because dependencies and load fit.
- An export worker uses reactive publishers to coordinate streaming.
- A bulk import worker uses a batch queue and bounded concurrency.

Never mix both models inside the same call chain without explicit adapter/lifecycle boundaries. Choose the right API per module and avoid arbitrary `block`/`subscribe` calls.

## 24. Testing according to the chosen model

Imperative services:

- JUnit/Mockito for service logic.
- Repository integration tests with real Elasticsearch/Testcontainers.
- Test timeouts, mapping errors, and bulk partial failures at the adapter.

Reactive services:

- `StepVerifier` for asserting `onNext`/`onComplete`/`onError`.
- Test empty results, cancellation, and timeouts.
- Test concurrency/backpressure in critical pipelines.
- Repository integration tests with real Elasticsearch and explicit refreshes for Search APIs.
- Verify no blocking calls run on event-loop threads along hot paths.

Example reactive service test:

```java
when(repository.findById("P-100"))
        .thenReturn(Mono.just(product));

StepVerifier.create(service.getRequired("P-100"))
        .expectNext(product)
        .verifyComplete();
```

Example asserting an empty publisher:

```java
when(repository.findById("P-404"))
        .thenReturn(Mono.empty());

StepVerifier.create(service.getRequired("P-404"))
        .expectError(ProductNotFoundException.class)
        .verify();
```

Reactive unit tests do not replace integration tests. Mocked publishers cannot verify Elasticsearch queries or mappings.

## 25. Common mistakes

| Symptom | Possible cause | Fix |
|---|---|---|
| Switched to reactive yet query latency did not drop | Time is spent in Elasticsearch/query/network. | Optimize queries, mappings, shards, and payloads; reactive does not speed up the engine. |
| Reactive app hits more 429s | Concurrency exceeds cluster capacity. | Cap in-flight work, add backoff, and measure thread pools/indexing pressure. |
| WebFlux event loop blocked | Calling imperative repository, JDBC, or blocking libraries directly. | Use reactive APIs or isolate blocking on `boundedElastic`. |
| Using `Mono` yet requests still block | Calling a blocking method before constructing the publisher. | Wrap at the right boundary or replace dependency with non-blocking API. |
| Calling `block` inside controllers | Converting reactive back to synchronous on event loop. | Return `Mono`/`Flux` to the WebFlux runtime. |
| Data not saved despite calling `save` | Publisher dropped without subscribing/returning. | Wire publisher into workflow and return it to caller. |
| Background errors silently lost | Internal `subscribe` lacking lifecycle/error handling. | Return publisher or use a managed job runner. |
| Heap grows during exports | Unbounded `collectList`, `buffer`, or queues. | Use bounded streaming/batching, page limits, and demand. |
| `flatMap` fires too many requests | Unbounded concurrency on a large `Flux`. | Use `flatMap` concurrency limit, `concatMap`, or bounded queues. |
| Reactive code hard to debug | Long chains, unclear context propagation. | Split methods by step, attach trace context, and test with `StepVerifier`. |
| Bigger connection pool worsens latency | Elasticsearch is already saturated. | Shed load and fix bottlenecks instead of merely adding connections. |
| Reactive API calls blocking JPA/JDBC | Mismatched dependency models. | Consider an imperative stack or isolate blocking dependencies. |
| Reactive bulk still loses items | Checking only request completion, ignoring item-level errors. | Inspect each item, retry/DLQ, and checkpoint. |
| Using reactive just because data is large | Confusing reactive with automatic bulk/streaming optimization. | Design batches/cursors and memory caps; benchmark both models. |

## 26. Selection process for a new project

1. **Describe the workload:** request rate, peak concurrency, latency targets, read/write ratio, and payload sizes.
2. **Inventory dependencies:** whether Elasticsearch, databases, HTTP services, filesystems, and message brokers use blocking or non-blocking APIs.
3. **Identify the web model:** Spring MVC, WebFlux, or headless workers/jobs.
4. **Classify tasks:** I/O-bound, CPU-bound, request-response, streaming, or bulk.
5. **Choose the simplest model that fits:** imperative if appropriate; reactive when there are concrete I/O concurrency or streaming wins.
6. **Set limits:** connection pools, in-flight requests, batch sizes, queue capacities, page sizes, and timeouts.
7. **Design error handling:** retry budgets, backoff/jitter, idempotency, DLQs, and checkpoints.
8. **Measure baselines:** collect latency, throughput, threads, memory, and Elasticsearch metrics.
9. **Benchmark under representative load:** include peaks, bursts, and slow dependencies.
10. **Test failure modes:** 429s, timeouts, cancellation, partial bulk failures, and cluster unavailability.
11. **Assess operational cost:** debuggability, tracing, context propagation, and team familiarity.
12. **Migrate only with evidence:** record goals, before/after metrics, and change boundaries.

## 27. Key takeaways

- Spring Data Elasticsearch offers both imperative and reactive APIs; both talk to the same cluster and face the same Elasticsearch resource limits.
- Imperative usually suits Spring MVC, CRUD, and moderate workloads when dependencies are predominantly blocking.
- Reactive helps with many concurrent I/O-bound requests, end-to-end WebFlux/Reactor stacks, or pipelines needing backpressure.
- Reactive does not make Elasticsearch queries faster and does not increase cluster throughput on its own.
- Unbounded concurrency drives up HTTP 429s, timeouts, queues, and p99 latency.
- Backpressure works only when pipelines preserve demand and avoid buffering whole datasets in memory.
- Bulk sizes, byte sizes, retries, checkpoints, and idempotency matter more than imperative vs. reactive for large imports/exports.
- Never call blocking repositories on WebFlux event loops; never use `block`/`subscribe` as default glue between layers.
- CPU-bound transformations need dedicated workers/schedulers; reactive creates no extra CPU capacity.
- Virtual threads on Java 21+ offer another option for blocking I/O workloads; benchmarking and capping connections/cluster load remain necessary.
- Hybrid architectures can work well when boundaries and lifecycles are clear.
- Measure p50/p95/p99, throughput, threads, memory, connection pools, 429s, and Elasticsearch queues before deciding.
- Choose the simplest model that meets SLAs and operational maintainability, then evolve based on metrics.

Choosing synchronous or reactive is an architectural decision grounded in real load patterns. Imperative gives straightforward structure for many request-response services; reactive helps manage many waiting I/Os and demand-regulated data streams. Both require caps on concurrency, connections, batches, and retries. By measuring workloads, understanding dependencies, and monitoring both the application and Elasticsearch, teams can choose the right model without trading stability to chase a coding style.

## References

- [Spring Data Elasticsearch — Reactive Elasticsearch Operations](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/reactive-template.html)
- [Spring Data Elasticsearch — Reactive repositories](https://docs.spring.io/spring-data/elasticsearch/reference/repositories/reactive-repositories.html)
- [Spring Data Elasticsearch — Elasticsearch Operations](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/template.html)
- [Project Reactor — Reference Guide](https://projectreactor.io/docs/core/release/reference/)
- [Reactive Streams — Specification](https://www.reactive-streams.org/)
- [Spring Framework — WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux.html)
- [Java — Virtual Threads](https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html)
- [Elasticsearch — Tune for indexing speed](https://www.elastic.co/guide/en/elasticsearch/reference/current/tune-for-indexing-speed.html)
- [Elasticsearch — Thread pool settings](https://www.elastic.co/guide/en/elasticsearch/reference/current/modules-threadpool.html)
