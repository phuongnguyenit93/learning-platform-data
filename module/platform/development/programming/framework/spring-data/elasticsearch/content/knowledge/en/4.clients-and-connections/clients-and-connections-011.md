# Distinguishing Synchronous and Reactive Clients

When a Java application calls Elasticsearch, requests can be executed synchronously or reactively. The core difference lies in how the application awaits the result and utilizes resources while waiting on I/O.

- **Synchronous client:** the call returns control to the program only after the operation completes or raises an error. The calling thread is typically blocked while waiting for Elasticsearch's response.
- **Reactive client:** represents results using publisher types such as Mono and Flux. Calling the method constructs a pipeline describing the operation; I/O executes reactively once the publisher is subscribed to. Threads do not need to remain blocked waiting on network responses.

In Spring Data Elasticsearch, these two styles map to their respective APIs:

- Synchronous style: ElasticsearchClient, ElasticsearchOperations, ElasticsearchTemplate, and ElasticsearchRepository.
- Reactive style: reactive client integration, ReactiveElasticsearchOperations, ReactiveElasticsearchTemplate, and ReactiveElasticsearchRepository.

Choosing the right style aligns the application with the request-handling model of Spring MVC or Spring WebFlux and avoids accidentally introducing blocking calls into a non-blocking execution path.

## 1. Where do synchronous and reactive differ?

Suppose a service needs to look up a product in Elasticsearch. Both approaches send the same kind of request to the server and receive similar data. The difference is what the application thread does while waiting for the response.

### Synchronous approach

    Product product = repository.findById(id)
        .orElseThrow();

When calling `findById`, the calling thread waits for the result. If Elasticsearch takes 100 ms to respond, the thread may remain held for that duration. Once the result returns, execution continues to the next statement.

This model is straightforward to read and trace:

    Thread A
       |
       v
    Send request to Elasticsearch
       |
       v
    Wait for response (thread held)
       |
       v
    Receive response
       |
       v
    Process result

### Reactive approach

    Mono<Product> productMono = repository.findById(id);

The call returns a `Mono<Product>`. A Mono is a publisher that emits at most one item, completes empty, or emits an error. Creating the publisher does not mean the result has been fetched yet.

When the pipeline is subscribed to, the reactive client performs I/O and emits the result once the response arrives:

    Request
       |
       v
    Build reactive pipeline
       |
       v
    Subscribe
       |
       v
    Send request via non-blocking I/O
       |
       v
    Receive signal when response is ready
       |
       v
    Process and emit data

The thread does not sit idle waiting for the network response. During the wait, the runtime can reuse that thread for other work. When data arrives, the pipeline resumes according to the scheduling of Reactor and participating components.

Reactive does not mean every piece of code always runs on a different thread or automatically executes in parallel. It describes how asynchronous signals are represented and composed; actual execution threads depend on schedulers, clients, and operators used.

## 2. Synchronous clients in Spring Data Elasticsearch

In the synchronous model, applications usually work with these abstractions:

- ElasticsearchRepository for repository operations.
- ElasticsearchOperations and ElasticsearchTemplate for more flexible operations than repositories.
- ElasticsearchClient when calling the Elasticsearch Java API Client directly.

Repository example:

    public interface ProductRepository
            extends ElasticsearchRepository<Product, String> {

        List<Product> findByCategory(String category);
    }

A service can call the repository sequentially:

    @Service
    public class ProductService {

        private final ProductRepository repository;

        public ProductService(ProductRepository repository) {
            this.repository = repository;
        }

        public List<Product> findBooks() {
            return repository.findByCategory("book");
        }
    }

`findBooks` returns `List<Product>`. By the time the method returns, the repository operation has completed and the service can immediately use the result list.

When calling the Elasticsearch Java API Client directly, synchronous code looks like:

    SearchResponse<Product> response = elasticsearchClient.search(
        request -> request
            .index("products")
            .query(query -> query
                .match(match -> match
                    .field("name")
                    .query("coffee")
                )
            ),
        Product.class
    );

The `search` call executes synchronously and may throw `IOException`. The calling thread waits until the HTTP response and deserialization complete. This fits synchronous processing flows naturally.

### Characteristics of the synchronous approach

- Straightforward control flow: call a method, get a result, continue processing.
- Fits Spring MVC/Servlet applications and batch or command-line jobs structured synchronously.
- Integrates easily with other blocking libraries.
- Threads are held while waiting for I/O, so thread and connection pools must be sized appropriately for load.
- Error handling can be simpler because exceptions surface directly at the call site.

Synchronous does not automatically mean slow in all scenarios. Under moderate load, short operations, and traditional application architectures, synchronous code is often simpler to operate and maintain.

## 3. Reactive clients and Spring Data Elasticsearch reactive APIs

Spring Data Elasticsearch provides reactive APIs to integrate with Reactor. Common abstractions include:

- ReactiveElasticsearchRepository: repository whose methods return Mono or Flux.
- ReactiveElasticsearchOperations: reactive data operations API.
- ReactiveElasticsearchTemplate: implementation of reactive operations.
- Reactive client integration: the underlying client layer executing requests reactively as supported by your Spring Data Elasticsearch version.

A reactive repository follows the same repository concept with different return types:

    public interface ProductReactiveRepository
            extends ReactiveElasticsearchRepository<Product, String> {

        Flux<Product> findByCategory(String category);
    }

A service can return the publisher directly:

    @Service
    public class ProductReactiveService {

        private final ProductReactiveRepository repository;

        public ProductReactiveService(ProductReactiveRepository repository) {
            this.repository = repository;
        }

        public Flux<Product> findBooks() {
            return repository.findByCategory("book");
        }
    }

`findBooks` does not return an eagerly loaded list. It returns `Flux<Product>`, describing a stream capable of emitting multiple products upon subscription.

For queries more flexible than repository methods, use `ReactiveElasticsearchOperations`:

    Flux<SearchHit<Product>> searchHits =
        reactiveElasticsearchOperations.search(query, Product.class);

Exact APIs and method return types depend on your Spring Data Elasticsearch version. The core idea is keeping operations inside a reactive pipeline and representing results as publishers instead of blocking at the call site.

### Mono and Flux

Reactor provides two primary publisher types:

| Type | Emitted Element Count | Examples |
|---|---:|---|
| Mono<T> | 0 or 1 | Find a product by id, save a single document |
| Flux<T> | 0 to many | Find a list of products, stream multiple search hits |

A publisher may complete normally, complete empty, or terminate with an error. Reactive code therefore handles data, completion signals, and error signals.

Example transforming data:

    Mono<Product> productMono =
        repository.findById(id);

    Mono<ProductView> viewMono =
        productMono.map(product ->
            new ProductView(product.getId(), product.getName())
        );

`map` transforms the emitted element when data arrives. It does not need to unwrap `Product` from the publisher while assembling the pipeline.

## 4. Reactive is not simply wrapping a synchronous client in Mono

This distinction is critical. Calling a blocking method and placing its result inside a `Mono` still performs blocking I/O. Returning `Mono` by itself does not make a network call non-blocking.

Anti-pattern in a reactive pipeline:

    Mono<Product> productMono = Mono.just(
        blockingRepository.findById(id).orElseThrow()
    );

`findById` executes eagerly before `Mono.just` is even constructed. The current thread still blocks waiting for the result. `Mono` merely wraps an already-computed value.

Another example that still does not produce non-blocking I/O:

    Mono.fromCallable(() -> blockingRepository.findById(id));

This publisher defers method invocation until subscription, yet without shifting work onto an appropriate scheduler, the blocking call still executes on the thread performing subscription.

If you must integrate a blocking call into a reactive pipeline during a transition, isolate it on `boundedElastic`:

    Mono.fromCallable(() ->
            blockingRepository.findById(id).orElseThrow()
        )
        .subscribeOn(Schedulers.boundedElastic());

This avoids stalling WebFlux's event-loop threads, though the underlying operation remains blocking and consumes a worker thread while waiting. Treat this as a temporary bridge for blocking libraries, not a substitute for a true reactive client.

Never call a blocking client directly on an event-loop thread. A slow call can stall the event loop, forcing unrelated requests to wait and degrading application concurrency.

## 5. Async client, reactive client, and synchronous client

These three concepts are related but not synonymous:

| Type | How Results Are Received | Does Calling Thread Block? | Reactor Integration |
|---|---|---|---|
| Synchronous | Returns result directly or throws exception | Typically yes | Needs an adapter to enter a pipeline |
| Asynchronous | Callback or Future/CompletableFuture | No blocking wait for result | Can be adapted into Mono/Flux |
| Reactive | Publishers like Mono/Flux | Does not hold thread waiting on I/O if client is truly non-blocking | Integrates natively with Reactor |

The Elasticsearch Java API Client provides both a synchronous `ElasticsearchClient` and an asynchronous `ElasticsearchAsyncClient`. Async APIs typically represent results with `CompletableFuture`. `CompletableFuture` does not inherently carry Reactive Streams backpressure semantics.

Meanwhile, Spring Data reactive APIs use publishers such as `Mono` and `Flux` to compose data operations within the Reactor ecosystem. An async client can be converted into a `Mono` via `Mono.fromFuture`, though doing so does not automatically introduce HTTP-layer backpressure or convert a blocking client into a non-blocking one.

When reading documentation or selecting dependencies, identify explicitly whether you mean `ElasticsearchClient`, `ElasticsearchAsyncClient`, or Spring Data's reactive client integration. Avoid lumping all three under the single term "reactive client".

## 6. Backpressure and stream processing

Reactive Streams defines backpressure: a subscriber can regulate how many items it is ready to receive. This helps when a stream emits many elements and production can outpace downstream processing.

For example, a `Flux` can be processed incrementally:

    repository.findByCategory("book")
        .map(this::toProductView)
        .filter(ProductView::isAvailable)
        .take(100);

Operators describe how items are processed as they arrive. `take(100)` caps how many items the pipeline requests.

However, do not interpret Reactor backpressure as automatically propagating pressure all the way back into the Elasticsearch server across every layer. Elasticsearch executes a search request and builds its response in its own way; the client, HTTP transport, and how Spring Data emits items govern buffering versus incremental emission. Backpressure coordinates publisher and subscriber, while network/server flow control depends on the implementation.

For very large result sets, add explicit pagination, `search_after`, page size caps, or appropriate scrolling strategies. Do not assume `Flux` automatically makes an unbounded query memory-efficient.

## 7. Error handling and pipeline lifecycle

In synchronous code, errors surface as exceptions at the call site:

    try {
        Product product = repository.findById(id)
            .orElseThrow();
        return product;
    } catch (RuntimeException ex) {
        // Handle or propagate the error
        throw ex;
    }

In a reactive pipeline, an error is a terminal signal. It can be handled with operators like `onErrorMap`, `onErrorResume`, or `doOnError`:

    return repository.findById(id)
        .switchIfEmpty(Mono.error(
            new ProductNotFoundException(id)
        ))
        .onErrorMap(
            ElasticsearchException.class,
            ex -> new ProductSearchException(ex)
        );

`onErrorMap` transforms the error type; `onErrorResume` provides a fallback publisher; `doOnError` fits side effects like logging. Do not use `doOnError` as error recovery, since it does not recover the pipeline.

A reactive pipeline can also be cancelled if a subscriber cancels. The client and transport may use cancellation signals to abort or release part of the in-flight work depending on implementation. Do not assume every request already dispatched to Elasticsearch can be recalled or that the server is guaranteed to halt processing immediately upon subscriber cancellation.

### Do not subscribe manually inside services

Normally, services should return `Mono` or `Flux` to the calling layer:

    public Mono<Product> findProduct(String id) {
        return repository.findById(id);
    }

Avoid calling `subscribe` inside a service solely to trigger execution and return `void`:

    repository.findById(id).subscribe(product -> {
        // Process product
    });

This detaches the pipeline from its caller. Errors may fail to propagate to controllers, request cancellation loses control over the operation, and ordering execution becomes harder. Let the framework or boundary layer manage subscriptions.

## 8. Choosing a client by application model

### Spring MVC / Servlet applications

Spring MVC generally processes requests using the Servlet model with per-request threads. Using synchronous `ElasticsearchRepository`, `ElasticsearchOperations`, or `ElasticsearchClient` is the natural choice when the rest of the business stack relies on blocking I/O.

This model is straightforward and integrates seamlessly with JDBC, file I/O, or blocking SDKs. Size thread pools, connection pools, and timeouts to match expected load.

### Spring WebFlux applications

Spring WebFlux is built for non-blocking I/O. When requests flow through WebFlux and all data layers support reactive execution, use `ReactiveElasticsearchRepository` or `ReactiveElasticsearchOperations`.

Controllers can return publishers directly:

    @RestController
    @RequestMapping("/products")
    public class ProductController {

        private final ProductReactiveRepository repository;

        public ProductController(ProductReactiveRepository repository) {
            this.repository = repository;
        }

        @GetMapping("/{id}")
        public Mono<Product> findById(@PathVariable String id) {
            return repository.findById(id);
        }

        @GetMapping
        public Flux<Product> findByCategory(
                @RequestParam String category) {
            return repository.findByCategory(category);
        }
    }

The framework manages subscription and writes results to the HTTP response. The controller never blocks for a `Product` or manually subscribes to the repository.

### Batch jobs and background tasks

A sequential batch job can use the synchronous client if it is clearer and meets requirements. If a batch processes many independent requests, async or reactive approaches can help regulate concurrency, provided concurrent request counts, retries, partial errors, and backpressure are explicitly bounded.

Reactive does not automatically make a batch job faster. If Elasticsearch itself is the bottleneck, firing more concurrent requests can overload the cluster instead of improving throughput.

## 9. Principles when combining reactive with Elasticsearch

1. **Stay consistent within a processing flow:** prefer reactive repositories/operations end-to-end when running on WebFlux.
2. **Never block the event loop:** avoid calling synchronous `ElasticsearchClient` or `block()` on reactive request paths.
3. **Do not subscribe in services:** return publishers so controllers or the framework manage the lifecycle.
4. **Limit concurrency:** do not unleash thousands of simultaneous requests against Elasticsearch just because the pipeline is reactive.
5. **Manage large result sets:** use pagination or appropriate read strategies; `Flux` does not eliminate response memory limits.
6. **Handle errors via signals:** use proper operators to map, recover from, or observe errors.
7. **Pick the right client:** distinguish synchronous `ElasticsearchClient`, `ElasticsearchAsyncClient`, and reactive client integration.
8. **Verify compatibility:** match dependencies and configuration to your deployed Spring Boot/Spring Data Elasticsearch versions.

## 10. Common mistakes

### Using synchronous ElasticsearchClient in WebFlux

The call can hold an event-loop thread while waiting for the HTTP response. For a temporary bridge, offload blocking calls to `boundedElastic`; long-term, switch to the appropriate reactive API.

### Thinking Mono.just makes a call non-blocking

Arguments to `Mono.just` are evaluated eagerly before the `Mono` is created. If the argument is a blocking call, the current thread already blocked beforehand.

### Using fromCallable without switching schedulers

`fromCallable` defers invocation until subscription but does not automatically move execution onto another thread. If the callable invokes a blocking library, isolate it on an appropriate scheduler.

### Calling block() inside a WebFlux controller

`block()` forces the current thread to wait for the result. This negates non-blocking benefits and can stall the event loop.

### Subscribing inside a service

Manual subscription detaches the pipeline from the caller and makes error propagation, cancellation, and ordering harder. Return the publisher to the upper layer.

### Assuming reactive is always faster than synchronous

Reactive can improve thread utilization under high I/O concurrency, yet it does not make Elasticsearch execute a single query faster. Overall performance depends on load, latency, connection limits, cluster resources, and the entire dependency chain.

### Mixing blocking and reactive without clear boundaries

A pipeline can combine reactive and blocking code, provided blocking segments are explicitly identified and isolated. Otherwise, event-loop threads risk blocking even when the outer return type is `Mono` or `Flux`.

## Conclusion

Synchronous clients return results directly and typically hold the calling thread while awaiting I/O. Reactive clients represent operations as publishers such as `Mono` and `Flux`, enabling non-blocking I/O composition and handling of data, error, completion, and cancellation signals.

In Spring Data Elasticsearch, the synchronous side typically uses `ElasticsearchRepository`, `ElasticsearchOperations`, and `ElasticsearchClient`; the reactive side uses `ReactiveElasticsearchRepository`, `ReactiveElasticsearchOperations`, and the corresponding reactive client integration. Base your choice on your application's execution model: Spring MVC/Servlet usually fits synchronous APIs, whereas Spring WebFlux should use reactive APIs consistently to avoid blocking the event loop.

The essential point is understanding the behavior of the underlying call. Wrapping a blocking method in a `Mono` does not make it non-blocking. When integrating blocking libraries, isolate them on a suitable scheduler; when building genuinely reactive systems, use a reactive client and keep publishers intact throughout the request flow.
