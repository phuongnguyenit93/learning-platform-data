# Avoiding Blocking Calls and Stalls in Processing Flows

In Spring Data Elasticsearch applications using Reactive, the goal is preventing execution threads from being held idle waiting for I/O. When a request waits on Elasticsearch, a database, an HTTP service, or a filesystem, the thread can continue serving other work instead of sitting blocked waiting for a result. This lets the application use threads more efficiently, especially under high concurrency.

A reactive call does not automatically guarantee the entire processing chain is non-blocking. If a Reactor pipeline invokes a synchronous repository, calls block(), calls Future.get(), runs Thread.sleep(), or performs blocking I/O, the thread executing the pipeline is still stalled. In WebFlux, that thread may be an event-loop thread serving many connections.

This lesson focuses on identifying and eliminating blocking operations in Spring Data Elasticsearch reactive flows. Topics include Reactor's thread model, Spring Data reactive APIs, composing Mono/Flux, isolating unavoidable blocking libraries, backpressure, context propagation, error handling, cancellation, and testing.

## 1. How Do Blocking and Non-Blocking Differ?

A **blocking** operation holds the current thread until the operation completes or times out. Example:

~~~java
Product product = blockingRepository.findById(id).orElse(null);
~~~

If this repository is synchronous, the call waits for Elasticsearch to return a response. The calling thread cannot perform other work while waiting.

A **non-blocking** operation returns a publisher representing a result that will arrive later:

~~~java
Mono<Product> product = reactiveRepository.findById(id);
~~~

This call returns a Mono. When a subscriber requests data, the reactive client performs asynchronous I/O. The thread does not need to block waiting for the response while the network handles the request.

~~~text
Blocking:
Thread A ---- send request ---- wait for response ---- continue
                                (thread is held)

Non-blocking:
Thread A ---- register request ---- do other work
                     |
                     +---- response arrives ---- callback processes
~~~

Non-blocking does not mean the request completes instantaneously. Elasticsearch still takes time to process, yet the thread does not sit idle waiting in blocking mode.

## 2. Why Is Blocking Dangerous in WebFlux?

WebFlux typically runs on an event-loop model. A small number of threads handle many connections by alternating across ready events. When an event-loop thread is blocked, other tasks scheduled on that thread must wait as well.

Example to avoid:

~~~java
@GetMapping("/products/{id}")
public Mono<Product> getProduct(@PathVariable String id) {
    Product product = blockingRepository.findById(id).orElse(null);
    return Mono.justOrEmpty(product);
}
~~~

The controller returns a Mono, yet the query already ran synchronously before the Mono was created. While the repository waited on Elasticsearch, the request-handling thread was blocked.

Consequences can include:

- Multiple requests slow down simultaneously even while the Elasticsearch cluster still has capacity.
- The event loop runs out of threads available to accept new work.
- Latency spikes sharply as concurrency grows.
- Timeouts at gateways or clients.
- Unrelated endpoints slow down because they share the same event loop.
- Thread pool exhaustion if blocking happens on a small pool.

An endpoint returning Mono does not guarantee the endpoint is non-blocking. You must inspect every operation inside the pipeline and every function invoked by it.

## 3. Reactivity Does Not Automatically Make Code Non-Blocking

Reactor provides two common publisher types:

- **Mono<T>**: emits at most one value or completes without a value.
- **Flux<T>**: emits zero to many values.

A publisher describes a processing sequence. It does not convert a blocking function into a non-blocking one.

Incorrect example:

~~~java
Mono<Product> product = Mono.just(
        blockingRepository.findById(id).orElse(null)
);
~~~

The blockingRepository call runs immediately when evaluating the argument to Mono.just. The publisher is only created after the blocking call finishes.

Another example:

~~~java
Mono<Product> product = reactiveRepository.findById(id)
        .map(item -> blockingPricingService.loadPrice(item.getSku()));
~~~

The Elasticsearch query may be non-blocking, yet blockingPricingService still blocks the thread running the map callback.

Any synchronous function called inside a pipeline still executes synchronously on the thread driving the pipeline, unless offloaded to an appropriate scheduler or replaced with an asynchronous API.

## 4. Using ReactiveElasticsearchOperations Instead of Synchronous APIs

Spring Data Elasticsearch provides separate synchronous and reactive abstractions:

| API | Typical return types | How it works |
|---|---|---|
| ElasticsearchOperations | Entity, SearchHits, List, or synchronous result | Waits for operation to complete |
| ReactiveElasticsearchOperations | Mono or Flux | Returns a publisher |
| ElasticsearchRepository | Optional, List, Page, or entity | Synchronous repository |
| ReactiveElasticsearchRepository | Mono or Flux | Reactive repository |

When the application's processing path is reactive, use reactive repositories or ReactiveElasticsearchOperations for Elasticsearch operations.

Service example:

~~~java
import org.springframework.data.elasticsearch.core.ReactiveElasticsearchOperations;
import org.springframework.data.elasticsearch.core.SearchHit;
import org.springframework.data.elasticsearch.core.query.Query;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Service
public class ProductSearchService {

    private final ReactiveElasticsearchOperations operations;

    public ProductSearchService(
            ReactiveElasticsearchOperations operations) {
        this.operations = operations;
    }

    public Mono<Product> save(Product product) {
        return operations.save(product);
    }

    public Flux<Product> search(Query query) {
        return operations.search(query, Product.class)
                .map(SearchHit::getContent);
    }
}
~~~

This example shows returning publishers to the caller. The service neither waits with block() nor subscribes manually.

Package names and ReactiveElasticsearchOperations overloads can vary across Spring Data Elasticsearch versions. Check the API matching your project's dependencies. The core rule is calling reactive methods returning Mono/Flux rather than calling synchronous methods and wrapping results in publishers.

## 5. Using ReactiveElasticsearchRepository

For repositories, choose the reactive interface:

~~~java
import org.springframework.data.elasticsearch.repository.ReactiveElasticsearchRepository;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public interface ProductRepository
        extends ReactiveElasticsearchRepository<Product, String> {

    Mono<Product> findBySku(String sku);

    Flux<Product> findByStatus(String status);
}
~~~

Methods return publishers:

~~~java
@Service
public class ProductService {

    private final ProductRepository repository;

    public ProductService(ProductRepository repository) {
        this.repository = repository;
    }

    public Mono<Product> findById(String id) {
        return repository.findById(id);
    }

    public Flux<Product> findActiveProducts() {
        return repository.findByStatus("ACTIVE");
    }

    public Mono<Product> save(Product product) {
        return repository.save(product);
    }
}
~~~

Do not inject both synchronous and reactive repositories into the same service and mix calls indiscriminately. Bean names and interface names look similar, yet execution semantics differ fundamentally.

If a use case calls multiple systems, use reactive APIs for each system. Switching Elasticsearch to reactive while still calling synchronous JPA or RestTemplate in the same pipeline leaves the overall flow blocking.

## 6. Do Not Call block(), blockFirst(), or blockLast() in Pipelines

The following methods force the current thread to wait for the publisher:

- **block()**: waits for a Mono to emit a value or complete.
- **blockFirst()**: waits for the first element of a Flux.
- **blockLast()**: waits for a Flux to complete and returns the last element.

Example to avoid in reactive services:

~~~java
public Mono<Product> findProduct(String id) {
    Product product = repository.findById(id).block();
    return Mono.justOrEmpty(product);
}
~~~

The right approach is returning the publisher:

~~~java
public Mono<Product> findProduct(String id) {
    return repository.findById(id);
}
~~~

If you need to transform the result, use operators:

~~~java
public Mono<ProductView> findProductView(String id) {
    return repository.findById(id)
            .map(ProductView::from);
}
~~~

Never call block inside WebFlux controllers, reactive services, callbacks like map/flatMap/doOnNext, event listeners running on reactive threads, or other composed publishers.

There may be imperative boundaries requiring a synchronous result, such as a command-line runner, test code, or an adapter explicitly designed for imperative callers. In those cases, block belongs at the outermost edge of the flow, with a reasonable timeout and never on an event-loop thread. In WebFlux applications, controllers are not the place to block.

## 7. Do Not Call subscribe() Manually Inside Services

A common mistake is calling subscribe inside a service:

~~~java
public void save(Product product) {
    repository.save(product)
            .subscribe();
}
~~~

This creates an independent subscription and returns immediately. The caller receives no publisher to know when the operation finishes, compose it with other work, handle errors uniformly, cancel when the request is canceled, or enforce ordering.

Return the publisher instead:

~~~java
public Mono<Product> save(Product product) {
    return repository.save(product);
}
~~~

In WebFlux, the framework subscribes to the publisher returned by the controller. In scheduled processes or CLI applications, an entry point may explicitly create a subscription and manage lifecycle, errors, and shutdown. That belongs at the application boundary, not inside every service method.

Avoid fire-and-forget inside services. If background work must run independently of a request, place it in a scheduler, queue, or job processor with lifecycle management and observability.

## 8. Using map and flatMap for Their Intended Purposes

In Reactor:

- **map** performs a synchronous transformation from T to R.
- **flatMap** is used when the transformation returns another Publisher.
- **concatMap** processes each element sequentially, preserving order.
- **flatMapSequential** executes asynchronously while emitting results in source order.

Synchronous transformation example:

~~~java
Mono<ProductView> view = repository.findById(id)
        .map(ProductView::from);
~~~

Example calling another reactive service:

~~~java
Mono<ProductDetails> details = repository.findById(id)
        .flatMap(product ->
                inventoryService.findBySku(product.getSku())
                        .map(inventory ->
                                ProductDetails.from(product, inventory)
                        )
        );
~~~

Do not use map and return a nested Mono:

~~~java
Mono<Mono<Inventory>> wrong = repository.findById(id)
        .map(product ->
                inventoryService.findBySku(product.getSku())
        );
~~~

The result type becomes Mono<Mono<Inventory>>. Use flatMap to chain two publishers into one sequence.

Likewise, do not use flatMap just to run a trivial calculation. When a function simply returns a synchronous value, map is clearer.

## 9. Combining Multiple Reactive Operations Without Blocking

When two operations are independent, they can execute and be combined with zip:

~~~java
Mono<Product> productMono = repository.findById(id);
Mono<Inventory> inventoryMono = inventoryService.findByProductId(id);

return Mono.zip(productMono, inventoryMono)
        .map(tuple ->
                ProductDetails.from(tuple.getT1(), tuple.getT2())
        );
~~~

Mono.zip waits for its component publishers to emit values and combines them. Both sources can proceed independently instead of calling one, blocking for its result, and then calling the other.

If you only need to wait for multiple operations to complete without collecting values, use Mono.when:

~~~java
return Mono.when(
        auditService.recordViewed(productId),
        metricsService.incrementProductView(productId)
).then();
~~~

Keep in mind that an error in one source can affect the combined publisher. If a secondary task may fail without breaking the primary use case, handle its error separately and define an explicit fallback policy.

Do not use zip on publishers that emit no values when you expect tuple elements. Mono<Void> usually pairs better with when/then than zip.

## 10. Isolating Blocking Libraries with boundedElastic

In practice, an application may still depend on synchronous libraries without reactive APIs. When they cannot yet be replaced, isolate blocking operations on **Schedulers.boundedElastic()**.

Example:

~~~java
public Mono<LegacyPrice> loadLegacyPrice(String sku) {
    return Mono.fromCallable(() ->
                    blockingPricingClient.loadPrice(sku)
            )
            .subscribeOn(Schedulers.boundedElastic());
}
~~~

Explanation:

- Mono.fromCallable defers invoking the function until subscription.
- subscribeOn shifts subscription and the source operation onto the specified scheduler.
- boundedElastic is designed for potentially blocking tasks with bounded resources.

Combining with reactive Elasticsearch:

~~~java
public Mono<ProductDetails> findDetails(String id) {
    return repository.findById(id)
            .flatMap(product ->
                    loadLegacyPrice(product.getSku())
                            .map(price ->
                                    ProductDetails.from(product, price)
                            )
            );
}
~~~

In this flow, the Elasticsearch query uses the reactive API, while the legacy blocking call runs on boundedElastic. While the legacy call waits, event-loop threads are not held.

boundedElastic does not make a blocking library non-blocking. It merely isolates blocked threads away from the event loop and caps threads/queues per scheduler settings.

## 11. Why Use fromCallable Instead of Mono.just?

These two snippets behave differently:

~~~java
Mono<Price> wrong = Mono.just(blockingClient.loadPrice(sku));
~~~

~~~java
Mono<Price> right = Mono.fromCallable(
        () -> blockingClient.loadPrice(sku)
).subscribeOn(Schedulers.boundedElastic());
~~~

In the first snippet, the blocking function executes immediately when constructing the Mono, before subscription. subscribeOn cannot move work that has already executed onto another scheduler.

In the second snippet, the function runs only upon subscription and executes on boundedElastic.

If you need to create a publisher based on data changing per subscription, you can use Mono.defer:

~~~java
Mono<Price> price = Mono.defer(() ->
        Mono.fromCallable(() -> blockingClient.loadPrice(sku))
).subscribeOn(Schedulers.boundedElastic());
~~~

Never wrap an existing reactive publisher inside fromCallable just to move it onto boundedElastic. For genuine reactive sources, compose directly.

## 12. Choosing the Right Scheduler

Reactor offers several standard schedulers:

| Scheduler | Purpose | Example |
|---|---|---|
| Schedulers.parallel() | Short, non-blocking CPU-bound work | Data transformations, scoring calculations |
| Schedulers.boundedElastic() | Bounded blocking tasks | JDBC, synchronous libraries, blocking file I/O |
| Schedulers.single() | Single sequential thread | Work requiring serialized execution on one worker |
| Schedulers.immediate() | Executes immediately on the current thread | Special cases, not a way to avoid blocking |
| Default WebFlux/Reactor Netty scheduler | Event-loop I/O and callbacks | Non-blocking network I/O |

Do not put every operation on boundedElastic simply because it seems safe. Doing so spawns unnecessary threads and queues while hiding APIs that are already reactive.

Do not use parallel for JDBC, Thread.sleep, or blocking HTTP clients. parallel is designed for CPU-bound work, not holding threads idle waiting on I/O.

If a blocking library has unpredictable load or wait times, you can create a dedicated bounded elastic scheduler with explicit caps:

~~~java
Scheduler legacyScheduler =
        Schedulers.newBoundedElastic(
                8,
                500,
                "legacy-pricing"
        );
~~~

Then use:

~~~java
Mono.fromCallable(() -> legacyClient.fetch(sku))
        .subscribeOn(legacyScheduler);
~~~

Custom schedulers must be disposed on application shutdown, such as via bean lifecycle or @PreDestroy. Never allocate a new scheduler per request, as that loses resource control.

## 13. Understanding subscribeOn and publishOn

Both operators can switch execution threads, yet their scopes differ.

- **subscribeOn** affects subscription to the source and is commonly used to offload a blocking source onto another scheduler.
- **publishOn** switches downstream operators following it onto the specified scheduler.

Example:

~~~java
Mono.fromCallable(() -> legacyClient.fetch(id))
        .subscribeOn(Schedulers.boundedElastic())
        .map(this::toView);
~~~

The blocking source runs on boundedElastic. map then continues on the current downstream thread per the scheduler chain.

Example moving CPU-bound calculation to parallel:

~~~java
return repository.findById(id)
        .publishOn(Schedulers.parallel())
        .map(this::calculateExpensiveScore);
~~~

Results from Elasticsearch cross publishOn, and the CPU computation runs on the parallel scheduler.

If a single blocking helper sits mid-pipeline, wrap that specific call with fromCallable and subscribeOn boundedElastic instead of shifting the entire remainder of the chain onto boundedElastic.

Do not sprinkle publishOn or subscribeOn randomly by trial and error. Identify which code is blocking or CPU-intensive and apply schedulers at the exact boundary.

## 14. Never Use Thread.sleep in Reactive Chains

Thread.sleep holds the current thread for the entire wait interval. In a reactive pipeline, this can block the event loop.

Incorrect example:

~~~java
return repository.findById(id)
        .map(product -> {
            Thread.sleep(1000);
            return product;
        });
~~~

If you need a one-second delay, use Mono.delay:

~~~java
return Mono.delay(Duration.ofSeconds(1))
        .then(repository.findById(id));
~~~

Mono.delay creates a publisher that emits a signal after the specified duration without tying up a sleeping thread during the wait.

When implementing retries, use retryWhen with backoff instead of writing manual sleep loops.

## 15. Never Call Future.get() or CompletableFuture.join()

Future.get() and CompletableFuture.join() wait synchronously for results. They can block the thread driving the pipeline.

Incorrect example:

~~~java
return repository.findById(id)
        .map(product -> {
            Price price = priceFuture.join();
            return ProductView.from(product, price);
        });
~~~

If a source returns CompletableFuture, convert it into a publisher:

~~~java
Mono<Price> priceMono = Mono.fromFuture(
        () -> priceClient.fetchAsync(sku)
);
~~~

Then combine:

~~~java
return repository.findById(id)
        .flatMap(product ->
                Mono.fromFuture(
                        () -> priceClient.fetchAsync(product.getSku())
                ).map(price -> ProductView.from(product, price))
        );
~~~

This works properly only if the Future-returning API is genuinely asynchronous. If the method constructing the Future blocks before returning it, isolate that method itself or replace the API.

Never call get()/join() merely to extract a value from a publisher. Keep results as Mono/Flux up to imperative boundaries.

## 16. Avoid Synchronous HTTP APIs in Reactive Pipelines

RestTemplate and synchronous HTTP clients hold threads while waiting for responses. If a reactive service makes HTTP calls, prefer WebClient:

~~~java
public Mono<Price> findPrice(String sku) {
    return webClient.get()
            .uri("/prices/{sku}", sku)
            .retrieve()
            .bodyToMono(Price.class);
}
~~~

Then compose directly:

~~~java
return repository.findById(id)
        .flatMap(product ->
                priceClient.findPrice(product.getSku())
                        .map(price ->
                                ProductDetails.from(product, price)
                        )
        );
~~~

Never call block on a Mono returned by WebClient. Calling block turns a non-blocking WebClient call into a synchronous wait.

If RestTemplate cannot be replaced yet, isolate it with fromCallable and boundedElastic. Long-term, migrate blocking clients on high-concurrency paths to reactive alternatives.

## 17. JDBC/JPA Are Also Blocking

Traditional Spring Data JPA and JDBC are synchronous APIs. Placing them inside a service returning Mono does not make database queries reactive.

Example to avoid:

~~~java
return reactiveProductRepository.findById(id)
        .map(product -> jpaRepository.findBySku(product.getSku()));
~~~

If migrating the database layer to R2DBC or a reactive API is not yet feasible, isolate the JPA query:

~~~java
Mono<LegacyRecord> legacyRecord =
        Mono.fromCallable(() ->
                jpaRepository.findBySku(sku)
        )
        .subscribeOn(Schedulers.boundedElastic());
~~~

Combining with the Elasticsearch publisher:

~~~java
return reactiveProductRepository.findById(id)
        .flatMap(product ->
                Mono.fromCallable(() ->
                        jpaRepository.findBySku(product.getSku())
                )
                .subscribeOn(Schedulers.boundedElastic())
                .map(record ->
                        ProductDetails.from(product, record)
                )
        );
~~~

boundedElastic has finite capacity. Under heavy traffic, blocking task queues can still grow and add latency. Monitor the scheduler and consider moving to reactive database drivers if the use case demands end-to-end scalability.

## 18. File I/O and Heavy Data Processing

File operations such as Files.readString, Files.writeString, or InputStream.read are blocking. Never call them directly inside map or doOnNext callbacks on an event loop.

Example isolating a file read:

~~~java
Mono<String> content = Mono.fromCallable(
        () -> Files.readString(path)
).subscribeOn(Schedulers.boundedElastic());
~~~

If your framework or library provides reactive/asynchronous file APIs, use those to avoid holding threads on I/O.

Also distinguish blocking I/O from CPU computation:

- Synchronous file read: boundedElastic or asynchronous file APIs.
- Parsing huge JSON or heavy CPU calculation: consider parallel or dedicated CPU workers.
- Synchronous HTTP call: boundedElastic or switch to WebClient.
- Synchronous database call: boundedElastic or migrate to R2DBC.

Do not dump every heavy task onto boundedElastic. Long-running CPU-bound tasks can saturate the scheduler intended for blocking I/O as well.

## 19. Backpressure and Controlled Flux Processing

**Backpressure** lets subscribers control how much data they are willing to receive. It keeps producers from overwhelming slower downstream consumers.

Sequential processing example:

~~~java
return productRepository.findByStatus("ACTIVE")
        .concatMap(product ->
                enrichmentService.enrich(product)
        );
~~~

concatMap processes each element's publisher sequentially, avoiding unbounded concurrent tasks.

If parallel execution with an explicit concurrency level is desired:

~~~java
return productRepository.findByStatus("ACTIVE")
        .flatMap(
                product -> enrichmentService.enrich(product),
                8
        );
~~~

8 is just an example. Choose concurrency based on Elasticsearch capacity, downstream services, connection pools, and rate limits.

Using flatMap without setting a sensible concurrency bound on large streams can launch too many simultaneous tasks. Backpressure does not replace explicit per-dependency concurrency limits.

### limitRate Is Not Elasticsearch Pagination

You can use limitRate to pace demand on the Reactor side:

~~~java
return productRepository.findByStatus("ACTIVE")
        .limitRate(64);
~~~

However, limitRate does not guarantee Elasticsearch fetches pages of 64 documents or uses search_after automatically. How data is fetched from the cluster depends on the reactive API implementation and query used.

For large datasets, pick a pagination/scroll/search_after strategy supported by your Spring Data Elasticsearch API. Never call collectList on millions of results when sequential per-document processing suffices.

## 20. Avoiding Unnecessary collectList

collectList buffers every element of a Flux into a List and emits only once the source completes.

Example:

~~~java
Mono<List<Product>> allProducts =
        productRepository.findByStatus("ACTIVE")
                .collectList();
~~~

This makes sense when datasets are small and the use case truly needs the whole list. For large datasets, it retains many objects on the heap, delays time-to-first-item processing, increases GC pressure, and risks OutOfMemoryError.

If you only need to transform and write each element, compose directly:

~~~java
return productRepository.findByStatus("ACTIVE")
        .flatMap(product ->
                exportService.write(product)
        )
        .then();
~~~

If batching is needed, group into bounded chunks:

~~~java
return productRepository.findByStatus("ACTIVE")
        .buffer(100)
        .concatMap(batch ->
                bulkWriter.write(batch)
        )
        .then();
~~~

buffer(100) creates batches of at most 100 elements. Account for the trailing batch having fewer than 100 items and handle per-item errors if bulk writes partially succeed.

## 21. Avoid Blocking Threads with synchronized or Locks

Code using synchronized, ReentrantLock.lock(), or semaphore acquire() can hold threads waiting. Inside reactive chains, avoid blocking locks unless genuinely required.

Example:

~~~java
return repository.findById(id)
        .map(product -> {
            synchronized (sharedState) {
                sharedState.update(product);
            }
            return product;
        });
~~~

Even if a critical section is very short, synchronization still blocks threads contending on the lock. Under contention, event loops can suffer.

Consider:

- Designing immutable state.
- Using appropriate concurrent data structures.
- Using reactive serialization such as concatMap when operations must be ordered.
- Using a dedicated scheduler/actor for state requiring sequential updates.
- Never holding a lock across network I/O.

Never hold a synchronized lock across an Elasticsearch or HTTP call. Unpredictable network waits will stall other requests behind the lock.

## 22. Error Handling and Retries in Reactive Pipelines

Reactive pipelines express errors as terminal signals. Errors can be handled using onErrorResume, onErrorMap, doOnError, or retryWhen.

Example translating errors into domain exceptions:

~~~java
return repository.findById(id)
        .switchIfEmpty(Mono.error(
                new ProductNotFoundException(id)
        ))
        .onErrorMap(
                ElasticsearchException.class,
                ProductSearchException::new
        );
~~~

Example backoff retry for transient failures:

~~~java
return repository.findById(id)
        .retryWhen(
                Retry.backoff(3, Duration.ofMillis(200))
                        .filter(this::isTransientFailure)
        );
~~~

Retrying means resubscribing to the source publisher. Evaluate:

- Is the operation idempotent?
- Is the failure genuinely transient?
- Are attempt counts and total time bounded?
- Could retries worsen load while the cluster is overloaded?
- Could the previous request have succeeded while the response was lost?

Never retry every exception. Mapping, validation, or unauthorized errors typically require fixing data or configuration. Retrying 429 or certain 5xx responses can be reasonable with backoff and limits.

To log errors while preserving the error signal, use doOnError:

~~~java
return repository.findById(id)
        .doOnError(error ->
                log.warn("Unable to load product {}", id, error)
        );
~~~

doOnError is a synchronous side effect. Do not perform blocking I/O inside it.

## 23. Timeouts and Cancellation

You can attach a timeout to a publisher:

~~~java
return repository.findById(id)
        .timeout(Duration.ofSeconds(3));
~~~

Timeouts cap how long the caller waits. However, a Reactor-layer timeout does not always prove Elasticsearch never processed the request. Depending on timing and transport, the request may already have been sent or executed on the server.

For writes, consider idempotency and state reconciliation if timeouts leave outcomes uncertain.

Cancellation occurs when the subscriber no longer wants the result, such as a browser closing its connection or a request being aborted. Reactive chains can propagate cancel signals upstream to release resources or abort requests if supported by the transport.

Never swallow cancellation by spawning a detached subscription inside a service. When a service returns a publisher to the controller, the framework propagates cancellation cleanly through the chain.

Use doFinally when observing termination signals:

~~~java
return repository.findById(id)
        .doFinally(signal ->
                log.debug("Product lookup finished: {}", signal)
        );
~~~

Signals can include complete, error, or cancel. Never assume every request finishes normally.

## 24. Context Propagation and ThreadLocal

In imperative applications, code often relies on ThreadLocal for request IDs, security principals, or MDC logging context. Reactive pipelines can hop across threads, making ThreadLocal unreliable for request-scoped state.

Reactor provides **Context**, bound to each subscription. Reactive Spring Security and Micrometer Context Propagation integrations help carry security or observability metadata across thread switches.

Avoid:

- Reading the current user arbitrarily from ThreadLocal after switching schedulers.
- Storing request-scoped data in mutable static fields.
- Assuming the entire pipeline runs on one thread.
- Assuming MDC automatically follows every operator in all configurations.

With Spring Security WebFlux, use the reactive security context APIs instead of imperative SecurityContextHolder. For trace IDs and logging contexts, enable context propagation mechanisms matching your Spring/Reactor version.

Example accessing Reactor Context:

~~~java
Mono<String> currentRequestId =
        Mono.deferContextual(context ->
                Mono.just(context.get("requestId"))
        );
~~~

Context is supplied at subscription:

~~~java
currentRequestId.contextWrite(context ->
        context.put("requestId", "req-1001")
);
~~~

Context is subscription-scoped data, not a global variable. Avoid placing large payloads or mutable objects into Context.

## 25. WebFlux Controllers Should Return Mono/Flux

WebFlux controllers should return publishers directly:

~~~java
@RestController
@RequestMapping("/products")
public class ProductController {

    private final ProductService service;

    public ProductController(ProductService service) {
        this.service = service;
    }

    @GetMapping("/{id}")
    public Mono<Product> findById(@PathVariable String id) {
        return service.findById(id);
    }

    @GetMapping
    public Flux<Product> findActive() {
        return service.findActiveProducts();
    }

    @PostMapping
    public Mono<Product> create(@RequestBody Mono<Product> body) {
        return body.flatMap(service::save);
    }
}
~~~

The WebFlux framework subscribes and writes the response using reactive response handling. Never call subscribe or block inside controllers.

If HTTP status or headers depend on the outcome, use reactive ResponseEntity:

~~~java
public Mono<ResponseEntity<Product>> findById(String id) {
    return service.findById(id)
            .map(ResponseEntity::ok)
            .defaultIfEmpty(ResponseEntity.notFound().build());
}
~~~

Never return a Mono containing another publisher. Use flatMap when a step produces the next publisher.

## 26. Mixing Spring MVC and WebFlux

A Spring application uses either Spring MVC or WebFlux. Publisher handling and thread models differ across the two stacks.

- WebFlux is built for reactive request handling.
- Spring MVC can support returning Mono/Flux via asynchronous request processing, yet that does not magically make synchronous dependencies non-blocking.
- An MVC controller calling synchronous JPA still performs blocking I/O.
- A reactive service called from imperative code may require an adapter at the boundary.

Do not conclude an entire system is non-blocking merely by seeing Mono return types. Inspect the actual web stack, server, clients, and every dependency on the request path.

If an application uses MVC with many blocking dependencies, converting a single repository to reactive may add complexity without commensurate benefit. Adopt reactive end-to-end on paths where concurrency and I/O scalability matter.

## 27. BlockHound Helps Detect Blocking Operations

**BlockHound** is a tool that detects certain blocking calls executed on threads marked non-blocking, such as Reactor non-blocking threads.

In test environments, you can install BlockHound:

~~~java
import org.junit.jupiter.api.BeforeAll;
import reactor.blockhound.BlockHound;

class ReactiveBlockingTest {

    @BeforeAll
    static void installBlockHound() {
        BlockHound.install();
    }
}
~~~

If a pipeline invokes Thread.sleep or a blocking API instrumented by BlockHound, tests fail with a blocking operation error.

BlockHound does not catch every form of blocking across every library. Some libraries need explicit integrations or instrumentation; false positives or compatibility limits can also occur depending on JDK, Reactor, and framework versions.

Use BlockHound as a detection aid alongside code reviews and load testing. Do not treat passing BlockHound tests as absolute proof that no blocking exists anywhere.

## 28. Testing Reactive Code with StepVerifier

You do not need to block to test publishers. Reactor provides **StepVerifier** to assert signals in sequence.

Example:

~~~java
@Test
void findsProductById() {
    Mono<Product> result = service.findById("p-1001");

    StepVerifier.create(result)
            .expectNextMatches(product ->
                    "p-1001".equals(product.getId())
            )
            .verifyComplete();
}
~~~

Testing missing data:

~~~java
@Test
void completesEmptyWhenProductDoesNotExist() {
    Mono<Product> result = service.findById("missing");

    StepVerifier.create(result)
            .verifyComplete();
}
~~~

Testing errors:

~~~java
@Test
void propagatesNotFoundError() {
    Mono<Product> result = service.findRequired("missing");

    StepVerifier.create(result)
            .expectError(ProductNotFoundException.class)
            .verify();
}
~~~

StepVerifier subscribes to the publisher and verifies signals. It eliminates the need to call block in business test code.

### Testing Schedulers and Time

When testing retries/backoff or delays, use Reactor virtual time to avoid waiting in real time:

~~~java
StepVerifier.withVirtualTime(() ->
        Mono.delay(Duration.ofHours(1))
)
.thenAwait(Duration.ofHours(1))
.expectNext(0L)
.verifyComplete();
~~~

Construct the publisher inside the withVirtualTime supplier so the virtual scheduler attaches at assembly/subscription time.

## 29. Integration Testing Reactive Elasticsearch

Unit tests and StepVerifier confirm composition, yet they do not prove the reactive Elasticsearch client works properly against a cluster.

Integration tests should verify:

1. Application context initializes the reactive client and ReactiveElasticsearchOperations.
2. Saving entities via the reactive repository.
3. Reading entities via reactive search or findById.
4. Mapping and conversion accuracy.
5. Mapping errors or missing-document handling.
6. Timeout/cancellation behavior within environment capabilities.
7. Absence of synchronous API calls on critical reactive paths.
8. BlockHound checks where test environment compatibility permits.

When measuring execution behavior, do not test only a single isolated request. Generate concurrent load and monitor event-loop threads, scheduler queues, latency, and connection pools.

When using Testcontainers or dedicated test clusters, choose an Elasticsearch version compatible with your Spring Data Elasticsearch and client dependencies. Never assume an arbitrary cluster version matches your current dependencies.

## 30. Monitoring Schedulers and Event Loops

To detect blocking in production, monitor multiple layers:

- Endpoint latency.
- Pending request counts.
- Busy or unresponsive event-loop threads.
- boundedElastic thread and queue counts.
- Rejected or long-queued tasks.
- Elasticsearch request latency.
- Connection pool usage.
- Timeouts, cancellations, and error rates.
- CPU, heap, and garbage collection.

If endpoint latency climbs while Elasticsearch response times remain steady, the bottleneck may lie in application processing, thread pool saturation, or a blocking dependency.

If the boundedElastic queue grows steadily, blocking work may exceed capacity or a library is waiting too long. Never merely raise thread limits to mask the symptom; inspect the blocking source, timeouts, and concurrency.

## 31. Common Anti-Patterns

| Anti-pattern | Problem | Fix |
|---|---|---|
| block() in controller | Blocks event loop | Return Mono/Flux |
| block() in service | Breaks composition and cancellation | Return publisher |
| Mono.just(blockingCall()) | Runs function before subscription | fromCallable + boundedElastic |
| subscribe() in service | Detaches execution from caller | Return publisher |
| Thread.sleep() | Holds thread during wait | Mono.delay or retry backoff |
| Future.get()/join() | Waits synchronously | Mono.fromFuture |
| RestTemplate in reactive chain | Blocking HTTP | WebClient |
| JPA/JDBC inside map | Blocking database I/O | Reactive API or boundedElastic |
| parallel for blocking I/O | Holds CPU worker idle on I/O | boundedElastic or reactive client |
| boundedElastic for everything | Unnecessary queues/threads | Isolate only blocking parts |
| collectList on large datasets | Retains all data on heap | Flux streaming, bounded buffers |
| Unbounded flatMap | Too many concurrent requests | Cap concurrency or use concatMap |
| ThreadLocal for request context | Context lost across thread switches | Reactor Context and context propagation |
| I/O inside doOnNext | Blocking side effect on current thread | Compose publisher with flatMap |
| Calling sync client directly | Bypasses reactive client | Use ReactiveElasticsearchOperations/client |

## 32. Workflow for Migrating Blocking Code to Reactive

When a blocking operation is spotted, follow these steps:

1. **Locate blocking points.** Check for block(), sleep, get(), join(), synchronous APIs, and I/O calls.
2. **Identify the blocking source.** Sync Elasticsearch, JDBC/JPA, HTTP client, filesystem, or external library.
3. **Find a reactive/asynchronous equivalent.** Such as ReactiveElasticsearchOperations, reactive repositories, WebClient, or R2DBC.
4. **Update return types.** Keep Mono/Flux end-to-end across services and controllers.
5. **Apply appropriate operators.** map for synchronous transforms, flatMap for subsequent publishers, concatMap when ordering is required.
6. **Isolate what cannot yet be replaced.** fromCallable/fromRunnable paired with boundedElastic.
7. **Set concurrency caps.** Avoid spawning excessive concurrent tasks.
8. **Design errors and retries.** Retry only eligible errors and ensure idempotency.
9. **Preserve cancellation and context.** Avoid internal subscribe() and ThreadLocal reliance.
10. **Test.** Use StepVerifier, integration tests, and BlockHound where applicable.
11. **Load test.** Inspect event loops, schedulers, latency, and memory under realistic concurrency.

Before and after example:

~~~java
// Blocking
public ProductView getProduct(String id) {
    Product product = blockingRepository.findById(id).orElseThrow();
    Price price = blockingPriceClient.fetch(product.getSku());
    return ProductView.from(product, price);
}
~~~

~~~java
// Reactive
public Mono<ProductView> getProduct(String id) {
    return reactiveRepository.findById(id)
            .switchIfEmpty(Mono.error(
                    new ProductNotFoundException(id)
            ))
            .flatMap(product ->
                    webClient.get()
                            .uri("/prices/{sku}", product.getSku())
                            .retrieve()
                            .bodyToMono(Price.class)
                            .map(price ->
                                    ProductView.from(product, price)
                            )
            );
}
~~~

If the price client lacks a reactive API, isolate it temporarily:

~~~java
private Mono<Price> fetchPrice(String sku) {
    return Mono.fromCallable(() ->
                    blockingPriceClient.fetch(sku)
            )
            .subscribeOn(Schedulers.boundedElastic());
}
~~~

Then use fetchPrice inside flatMap, allowing later replacement with WebClient without altering the service contract.

## 33. Checklist When Designing Reactive Flows

- Use ReactiveElasticsearchOperations or ReactiveElasticsearchRepository.
- Never call synchronous ElasticsearchOperations inside a reactive chain.
- Never call block(), blockFirst(), or blockLast() on an event loop.
- Never subscribe manually in controllers or services.
- Never call Thread.sleep, Future.get, or CompletableFuture.join.
- Use WebClient instead of blocking HTTP clients.
- Use R2DBC or isolate JDBC/JPA on boundedElastic when needed.
- Use fromCallable for blocking functions so invocation is deferred until subscription.
- Use boundedElastic for blocking I/O and parallel for CPU-bound work.
- Do not shift the entire pipeline onto another scheduler when only one segment needs isolation.
- Choose map/flatMap/concatMap matching required semantics.
- Cap concurrency and avoid collectList on large datasets.
- Configure bounded timeouts and retries.
- Ensure write operations are safe to retry.
- Do not rely on ThreadLocal to carry request context.
- Verify with StepVerifier and integration tests.
- Use BlockHound where compatible to catch blocking calls.
- Monitor event loops, scheduler queues, latency, and timeouts.

A Spring Data Elasticsearch Reactive flow retains its non-blocking advantages only when every I/O operation along the path uses asynchronous APIs or is properly isolated. Use reactive repositories/operations for Elasticsearch, compose publishers with map and flatMap, return Mono/Flux to callers, and avoid internal block or subscribe calls. When synchronous libraries are unavoidable, wrap them with fromCallable and run on boundedElastic with proper bounds; never use parallel to wait on I/O. Combining backpressure, concurrency limits, cancellation, context propagation, and thorough testing lets applications serve high request concurrency without stalling the event loop.
