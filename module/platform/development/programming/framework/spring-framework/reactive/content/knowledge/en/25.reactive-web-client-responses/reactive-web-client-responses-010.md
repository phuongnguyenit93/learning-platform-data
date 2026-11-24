# Boundaries for using block in imperative code and avoiding blocking on the event loop in Spring WebFlux

## 1. Why is a blocking boundary needed?

WebClient returns a Mono<T> or Flux<T>. A publisher describes an asynchronous operation; it is not an immediately available Java value at the time the method is called.

In WebFlux, the natural approach is to keep the publisher flowing throughout the request path:

~~~java
@GetMapping("/products/{id}")
Mono<Product> getProduct(@PathVariable String id) {
    return productClient.getProduct(id);
}
~~~

Spring WebFlux subscribes and writes the response according to the reactive lifecycle. The request-handling thread does not need to wait synchronously until the upstream replies.

However, not every part of a system is reactive. An application may need to integrate with a batch job, command-line tool, legacy library exposing only synchronous APIs, adapter for a legacy system, or test code needing a value for assertions.

At those boundaries, block() can be a valid choice if the current thread is permitted to wait. What matters is **where the block call executes**, not the name of the class or method containing it.

A method named ImperativeAdapter is still unsafe if invoked from the WebFlux event loop. Conversely, a method calling block() from a CLI main thread or a standard worker thread can be completely appropriate.

## 2. What is the event loop and why must it never be blocked?

WebFlux typically runs on a non-blocking server such as Reactor Netty. Instead of dedicating one thread per request and letting that thread wait on I/O, the server uses a small, fixed pool of event-loop workers to handle many connections.

~~~text
Multiple HTTP connections
   |       |       |
   v       v       v
+-----------------------+
| Event-loop workers    |
|                       |
| receive I/O events    |
| run callbacks         |
| forward reactive sigs |
| write responses       |
+-----------------------+
           |
           v
    upstream I/O events
~~~

One event-loop thread may serve many requests and callbacks. When one request performs a blocking operation, that thread cannot continue processing other work while waiting.

Consequences can include:

- Many other requests suffer increased latency even when their upstreams are ready.
- New connections and I/O callbacks are processed slowly.
- Throughput drops sharply under higher load.
- Timers, timeouts, and other reactive tasks on the same worker are delayed.
- If code waits for a result that the same event loop must process to produce, the application can deadlock or time out.
- Reactor may throw IllegalStateException when it detects a blocking API called on a thread marked non-blocking.

This is why you must never call block() on the event loop, even if a request only waits on a fast API taking a few milliseconds. Even a brief block ties up a shared thread.

## 3. What does block() actually do?

Mono.block() subscribes to the current publisher and waits for a value or terminal signal:

~~~java
Product product = webClient.get()
    .uri("/products/{id}", 42)
    .retrieve()
    .bodyToMono(Product.class)
    .block();
~~~

The call above turns an asynchronous pipeline into a synchronous call on the thread executing it. The calling thread must wait for the response.

Key characteristics:

1. block() creates a new subscription every time it is called. With a cold WebClient request publisher, calling block twice usually sends two HTTP requests.
2. block() returns the value when the Mono emits an item and completes.
3. If the Mono completes without emitting an item, block() returns null.
4. If the Mono emits an error, that error is thrown on the thread calling block.
5. If the publisher emits no signal, unbounded block() has no timeout and can wait forever.
6. block(Duration) caps the caller's wait time; it does not make the waiting thread non-blocking.
7. For Mono<Void>, normal completion returns null because the publisher emits no object.

Example with a timeout:

~~~java
Product product = webClient.get()
    .uri("/products/{id}", 42)
    .retrieve()
    .bodyToMono(Product.class)
    .block(Duration.ofSeconds(5));
~~~

If no signal arrives within five seconds, the wait terminates with a timeout exception. Distinguish Reactor's timeout from connect/read/response timeouts on the HTTP client; transport timeouts are still necessary.

### 3.1. blockOptional() to represent empty results

If a publisher can complete without emitting a value, blockOptional() represents that case more cleanly:

~~~java
Optional<Product> product = productMono
    .blockOptional(Duration.ofSeconds(5));
~~~

The result is Optional.of(product) if the Mono emits a Product, or Optional.empty() if the Mono completes without emitting an item.

This differs from a ResponseEntity<Product> whose body is null. In the latter case, the Mono still emits a ResponseEntity, so the outer Optional remains present.

Do not use blockOptional() to swallow errors. Errors from the publisher are still thrown.

## 4. Valid boundaries for using block

You may use block() when the program is at a true synchronous boundary and the current thread is allowed to wait.

| Boundary | Can block? | Condition |
| --- | --- | --- |
| CLI main method | Yes | Waits on the program-control thread, with a timeout |
| Batch worker thread | Yes | Worker designed to execute synchronous tasks |
| JUnit test method | Yes | Test thread is not an event loop; StepVerifier is often preferred |
| One-off migration tool | Yes | Controlled waiting and proper resource lifecycle cleanup |
| Adapter for legacy sync API | Possibly | Called only from blocking-safe threads |
| WebFlux controller | No | Return Mono/Flux to the framework |
| WebFlux WebFilter | No | Compose publishers and return Mono<Void> |
| Reactor Netty event loop | No | Never wait synchronously |
| parallel/single schedulers | No | These are non-blocking schedulers |
| WebClient callbacks | No | Continue with map/flatMap/then |

A clean boundary usually has a method name and contract indicating synchronous behavior, such as fetchForBatchBlocking. That method must never be called from controllers, WebFilters, or callbacks running on an event loop.

### 4.1. Example adapter for a batch job

~~~java
public final class ProductBatchAdapter {
    private final ProductService productService;

    public ProductBatchAdapter(ProductService productService) {
        this.productService = productService;
    }

    // Call only from a batch/CLI worker thread, never from the WebFlux event loop.
    public ProductSnapshot fetchForBatch(String productId) {
        return productService.fetch(productId)
            .blockOptional(Duration.ofSeconds(5))
            .orElseThrow(() ->
                new IllegalStateException("Product response was empty")
            );
    }
}
~~~

The adapter blocks at the proper boundary with a timeout. The underlying service can keep a reactive API so it remains reusable by WebFlux controllers.

Adding a suffix like Blocking or ForBatch helps callers recognize the contract, though naming never replaces controlling actual execution threads.

## 5. Never block in a WebFlux controller

This is wrong:

~~~java
@GetMapping("/products/{id}")
Mono<Product> getProduct(@PathVariable String id) {
    Product product = productClient.getProduct(id)
        .block(Duration.ofSeconds(5));

    return Mono.just(product);
}
~~~

The controller runs on WebFlux's request-processing path. Calling block holds the thread while waiting on WebClient. Wrapping the result in a new Mono afterward does not make the wait that just happened asynchronous.

The right way:

~~~java
@GetMapping("/products/{id}")
Mono<Product> getProduct(@PathVariable String id) {
    return productClient.getProduct(id);
}
~~~

If you need status, headers, and body from the WebClient response, keep ResponseEntity in the reactive pipeline:

~~~java
@GetMapping("/products/{id}")
Mono<ResponseEntity<Product>> getProduct(@PathVariable String id) {
    return productClient.getProductEntity(id);
}
~~~

Or transform metadata with operators:

~~~java
Mono<ProductView> view = productClient.getProductEntity(id)
    .map(response -> new ProductView(
        response.getStatusCode().value(),
        response.getHeaders().getETag(),
        response.getBody()
    ));
~~~

If another API must be called depending on the first result, use flatMap:

~~~java
Mono<ProductView> view = productClient.getProduct(id)
    .flatMap(product ->
        inventoryClient.getInventory(product.id())
            .map(inventory -> new ProductView(product, inventory))
    );
~~~

If two requests are independent, combine them with Mono.zip so a single result emits when both finish. Neither request needs blocking.

## 6. Never block in WebFilters, handlers, or reactive callbacks

The same rule applies outside controllers:

- WebFilter.filter must return a publisher to the chain.
- Functional handlers should return Mono<ServerResponse>.
- map, flatMap, doOnNext, and WebClient callbacks must never wait synchronously.
- Do not call Thread.sleep to wait for events or retries.
- Do not call Future.get() or CompletableFuture.join() on the event loop.
- Do not call toStream() or toIterable() to iterate unbounded publishers on the request path.

Correct WebFilter example:

~~~java
@Component
public class RequestAuditFilter implements WebFilter {
    private final AuditService auditService;

    public RequestAuditFilter(AuditService auditService) {
        this.auditService = auditService;
    }

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain) {

        return auditService.recordRequest(exchange.getRequest())
            .then(chain.filter(exchange));
    }
}
~~~

then chains completion of the audit publisher with the filter chain. No block() call is needed to wait for auditing to finish.

If the audit library only provides a blocking API, wrap that specific operation with Mono.fromCallable and boundedElastic.

## 7. Integrating blocking libraries with boundedElastic

You may encounter synchronous JDBC, legacy SDKs, filesystem APIs, or blocking HTTP libraries. Never call them directly on the event loop.

Reactor provides the standard pattern:

~~~java
Mono<Inventory> inventory =
    Mono.fromCallable(() -> legacyInventoryClient.lookup(sku))
        .subscribeOn(Schedulers.boundedElastic());
~~~

The two parts have distinct roles:

- Mono.fromCallable defers the blocking call until subscription and turns its return value into a Mono.
- subscribeOn(Schedulers.boundedElastic()) shifts subscription and source execution onto a worker suited for blocking tasks.

boundedElastic bounds thread counts and queues to absorb blocking tasks without spawning unbounded threads. Under load exceeding capacity, tasks may wait in a queue or be rejected per configured limits.

Do not treat boundedElastic as an infinite resource. Monitor wait times, active tasks, queues, and overload errors.

### 7.1. Do not use Mono.just for blocking calls

Wrong:

~~~java
Mono<Inventory> inventory =
    Mono.just(legacyInventoryClient.lookup(sku))
        .subscribeOn(Schedulers.boundedElastic());
~~~

lookup(sku) runs eagerly when evaluating the Mono.just expression, before the scheduler can shift source execution to a worker. If this code runs on an event loop, the blocking operation has already happened on the event loop.

Right:

~~~java
Mono<Inventory> inventory =
    Mono.fromCallable(() -> legacyInventoryClient.lookup(sku))
        .subscribeOn(Schedulers.boundedElastic());
~~~

fromCallable invokes lookup only when subscription occurs on the chosen scheduler.

### 7.2. Blocking APIs that return no value

If a synchronous library returns void, use Mono.fromRunnable:

~~~java
Mono<Void> saveAudit(AuditRecord record) {
    return Mono.fromRunnable(() -> blockingAuditClient.write(record))
        .subscribeOn(Schedulers.boundedElastic())
        .then();
}
~~~

If an operation returns multiple results that a synchronous API already aggregated into a List, Mono.fromCallable with List can work. If the source is genuinely a stream, consider a suitable streaming API rather than loading everything into RAM.

### 7.3. Nulls from legacy libraries

Mono.fromCallable emits no value if the Callable returns null; it completes empty. If a legacy API uses null to represent missing data, translate that semantics explicitly:

~~~java
Mono<Inventory> inventory =
    Mono.fromCallable(() -> legacyInventoryClient.lookup(sku))
        .subscribeOn(Schedulers.boundedElastic())
        .switchIfEmpty(Mono.error(
            new InventoryNotFoundException(sku)
        ));
~~~

Use switchIfEmpty only when null genuinely means not found. If null represents another state, convert to Optional or a clear domain result type.

## 8. How do subscribeOn and publishOn differ?

Both operators switch execution context, but where they take effect differs.

| Operator | Effect | Typical usage |
| --- | --- | --- |
| subscribeOn(scheduler) | Switches subscription and source execution to the scheduler | Wrapping a blocking source with fromCallable |
| publishOn(scheduler) | Switches downstream signals and operators after publishOn | Moving subsequent processing steps to a worker |

subscribeOn example:

~~~java
Mono<Data> result =
    Mono.fromCallable(() -> blockingClient.fetch())
        .subscribeOn(Schedulers.boundedElastic())
        .map(this::convert);
~~~

The blocking source and subsequent map run on the chosen execution context unless another operator switches schedulers.

publishOn example:

~~~java
Mono<String> result =
    webClient.get()
        .uri("/data")
        .retrieve()
        .bodyToMono(Data.class)
        .publishOn(Schedulers.boundedElastic())
        .map(legacyFormatter::format);
~~~

WebClient still performs I/O non-blockingly via its connector. publishOn moves the downstream map step to boundedElastic because formatter is blocking.

For an isolated blocking call, the fromCallable(...).subscribeOn(boundedElastic()) pattern is usually easier to read and isolate.

### 8.1. Do not confuse a scheduler with permission to call block

The following is still wrong if invoked from the event loop:

~~~java
Product product = webClient.get()
    .uri("/products/42")
    .retrieve()
    .bodyToMono(Product.class)
    .subscribeOn(Schedulers.boundedElastic())
    .block(Duration.ofSeconds(5));
~~~

subscribeOn may shift subscription and source work. Yet block() still blocks the calling thread until a result arrives. If the calling thread is the event loop, that exact event loop remains blocked.

Similarly, publishOn(Schedulers.boundedElastic()) does not make a block() placed before publishOn safe.

**Schedulers change where reactive operators execute; they do not change the synchronous blocking nature of calling block on the current thread.**

## 9. Do not use boundedElastic to hide a WebClient block

Do not write:

~~~java
Mono<Product> product =
    Mono.fromCallable(() ->
        webClient.get()
            .uri("/products/42")
            .retrieve()
            .bodyToMono(Product.class)
            .block()
    ).subscribeOn(Schedulers.boundedElastic());
~~~

WebClient is already non-blocking. Wrapping it in a Callable and calling block occupies a boundedElastic worker for the entire network wait, turning non-blocking I/O into blocking I/O, wasting threads, and losing reactive benefits.

Right:

~~~java
Mono<Product> product = webClient.get()
    .uri("/products/42")
    .retrieve()
    .bodyToMono(Product.class);
~~~

Offload only code that is truly blocking, such as legacy SDKs or synchronous JDBC. Never offload WebClient just because its publisher does not immediately yield a synchronous value.

## 10. Imperative code needing multiple WebClient requests

If a batch job needs two independent APIs, do not block after each request:

~~~java
Product product = productClient.getProduct(id)
    .block(Duration.ofSeconds(5));

List<Review> reviews = reviewClient.getReviews(id)
    .collectList()
    .block(Duration.ofSeconds(5));
~~~

This creates two sequential waits. Total time can approach the sum of both upstream latencies.

Compose first, then block once at the boundary:

~~~java
Mono<BatchProductReport> report =
    Mono.zip(
        productClient.getProduct(id),
        reviewClient.getReviews(id).collectList()
    ).map(tuple ->
        new BatchProductReport(tuple.getT1(), tuple.getT2())
    );

BatchProductReport result =
    report.block(Duration.ofSeconds(8));
~~~

The two independent requests run concurrently. The caller waits once for a combined result.

If the second request depends on data from the first, use flatMap and block once at the end:

~~~java
Mono<OrderDetails> details =
    orderClient.getOrder(orderId)
        .flatMap(order ->
            customerClient.getCustomer(order.customerId())
                .map(customer -> new OrderDetails(order, customer))
        );

OrderDetails result =
    details.block(Duration.ofSeconds(8));
~~~

## 11. Handling Flux at a synchronous boundary

Flux<T> can emit many elements. If the source is finite and bounded in size, you can aggregate into a List and block:

~~~java
List<Product> products = webClient.get()
    .uri("/products")
    .retrieve()
    .bodyToFlux(Product.class)
    .collectList()
    .block(Duration.ofSeconds(10));
~~~

This fits a finite list with a well-bounded size.

Do not call collectList() on unbounded streams or very large datasets. It must hold all elements in memory before returning the List.

APIs like blockFirst(), blockLast(), toIterable(), and toStream() can also block the caller. Never use them on the event loop. For large streams, keep the publisher reactive or design a dedicated synchronous consumer with explicit queues/backpressure and resource limits.

## 12. CompletableFuture and equivalent blocking calls

Mono.block() is not the only thing that blocks. The following calls also block threads:

~~~java
future.get();
future.join();
mono.toFuture().get();
mono.toFuture().join();
~~~

toFuture() itself builds a CompletableFuture bridge; calling get() or join() is the synchronous wait.

If you already have a CompletableFuture, bring it into the reactive pipeline:

~~~java
Mono<Customer> customer =
    Mono.fromFuture(legacyAsyncClient.fetchCustomer(id));
~~~

If an API returns a CompletionStage, use Mono.fromCompletionStage. Then compose with map/flatMap instead of calling get/join.

If an imperative caller genuinely needs the value, block once at the outer boundary with a timeout. Do not block mid-pipeline.

## 13. Timeouts, cancellation, and limits of blocking calls

Timeouts are necessary, though they do not solve every problem.

### 13.1. block(Duration) limits the caller's wait time

~~~java
Product product = productMono
    .block(Duration.ofSeconds(4));
~~~

The caller does not wait forever. When expired, Reactor terminates the wait with a timeout exception and cancels the subscription per API semantics.

### 13.2. Timeout does not guarantee a blocking library stops immediately

If the source is a JDBC driver or blocking SDK unresponsive to interruption, cancelling the subscription does not necessarily halt the in-flight I/O operation immediately. Therefore:

- Configure connection timeouts, socket/read timeouts, or query timeouts in the underlying library.
- Limit blocking worker counts and queues.
- Do not rely on a Reactor timeout as the sole timeout for blocking APIs.
- Monitor tasks still running after the caller has timed out.

### 13.3. WebClient timeouts

WebClient can configure connector/client timeouts aligned with transport behavior. Additionally, a Reactor timeout can be placed on the whole publisher:

~~~java
Mono<ResponseEntity<Product>> response =
    webClient.get()
        .uri("/products/{id}", id)
        .retrieve()
        .toEntity(Product.class)
        .timeout(Duration.ofSeconds(4));
~~~

Transport timeouts and publisher timeouts address different layers. Set both per SLA; avoid unbounded automatic retries when an upstream is overloaded.

## 14. Which scheduler for which workload?

| Scheduler | Purpose | Suitable for blocking I/O? |
| --- | --- | --- |
| Schedulers.parallel() | CPU-bound work, workers roughly equal to CPU cores | No |
| Schedulers.single() | A single shared worker for sequential tasks | No |
| Schedulers.boundedElastic() | Isolating blocking I/O or legacy synchronous APIs | Yes, within limits |
| Schedulers.immediate() | Executes immediately on the current thread | Provides no isolation |
| Schedulers.newBoundedElastic(...) | Dedicated bounded pool managed by the application | Yes, when separate isolation is needed |

Never offload blocking I/O to parallel(). Reactor marks default single/parallel threads as non-blocking; calling blocking APIs like block on those threads can trigger IllegalStateException.

boundedElastic is designed to absorb blocking work with bounds. If every request pushes heavy blocking work onto it, the pool can still saturate. Optimize at the root with reactive drivers or non-blocking APIs when available.

If creating a custom scheduler via newBoundedElastic, the application must manage and dispose of it when no longer needed. Never create a new scheduler per request.

## 15. Spring MVC, Spring WebFlux, and synchronous code

Spring MVC and Spring WebFlux use different concurrency models.

| Aspect | Spring MVC | Spring WebFlux |
| --- | --- | --- |
| Typical model | Servlet request thread handles a request | Event-loop worker handles many requests |
| Default assumption | Blocking I/O allowed on servlet worker | Never block request-processing threads |
| Reactive return types | Can return Mono/Flux | Natural programming model |
| Blocking code | Holds one servlet thread; requires pool sizing | Can block the event loop and affect many requests |
| Synchronous HTTP client | RestClient fits imperative flows | Prefer non-blocking WebClient |
| Integrating blocking libraries | Can run on servlet worker or executor | Offload to boundedElastic or dedicated workers |

A Spring MVC controller running in a synchronous model can use blocking APIs, though each waiting request ties up a servlet thread and requires capacity planning. If using Mono or Flux, return the publisher to Spring rather than blocking and re-wrapping it.

In WebFlux, never call block in a controller. Keep the request path non-blocking.

If an application is entirely imperative and needs no reactive composition, RestClient is the idiomatic synchronous choice in modern Spring Framework. WebClient can still be used synchronously by blocking at the end of an imperative flow outside controllers and event loops.

## 16. How to inspect and detect blocking

Signs that help uncover blocking calls:

- Thread dumps showing event-loop workers stuck in socket reads, JDBC, file I/O, monitor waits, or Thread.sleep.
- Logged thread names showing request-path code executing on threads like reactor-http-nio-*.
- Latency rising across unrelated endpoints simultaneously despite different upstreams.
- Reactor throwing exceptions stating block() is unsupported on non-blocking threads.
- boundedElastic thread pool showing long queues or many workers waiting on I/O.

You can log thread names during investigation:

~~~java
.doOnNext(value ->
    log.debug("Processing on thread {}",
        Thread.currentThread().getName()))
~~~

Do not base production logic on thread names; names vary by server and configuration.

### 16.1. BlockHound in tests

BlockHound helps detect certain blocking calls on threads marked non-blocking. You can install it in tests/integration tests:

~~~java
@BeforeAll
static void installBlockHound() {
    BlockHound.install();
}
~~~

BlockHound does not replace code review and load testing. Some libraries require integrations or allow-lists; zero warnings do not prove an entire code path is non-blocking.

## 17. Common anti-patterns

| Anti-pattern | Why it is problematic | Fix |
| --- | --- | --- |
| block in WebFlux controller | Holds the event loop while waiting | Return Mono/Flux |
| block in WebFilter | Blocks the request chain on a worker | Compose publishers and return Mono<Void> |
| block in map/flatMap callbacks | Callback may run on the event loop | Use reactive operators or offload the blocking segment |
| Mono.just(blockingCall()) | Blocking call executes eagerly at assembly | Mono.fromCallable(...).subscribeOn(boundedElastic) |
| Mono.fromCallable(() -> webClient...block()) | Turns non-blocking WebClient into blocking | Use the WebClient publisher directly |
| subscribeOn then block on event loop | Caller is still blocked | Block only at an imperative boundary |
| publishOn then block before the operator | Scheduler switch has not happened at block site | Never block mid-pipeline |
| Multiple block calls on the same Mono | Each call can trigger a new subscription/request | Compose first and block once |
| Unbounded block in batch jobs | Can wait indefinitely | Use block(Duration) and transport timeouts |
| collectList on an unbounded Flux | Never completes and grows memory endlessly | Stream or bound with take |
| Future.get/join on event loop | Blocks just like block() | Use Mono.fromFuture and compose |
| Thread.sleep in reactive chains | Blocks worker and delays signals | Use delayElement/delaySubscription or Reactor timers |
| Using parallel for JDBC | Blocks non-blocking CPU scheduler | Use boundedElastic or a reactive driver |
| Creating a scheduler per request | Leaks threads and pool allocation cost | Use shared boundedElastic or managed pools |
| Swallowing timeout into empty | Loses root cause and can return fake results | Map timeout to an explicit domain error |

## 18. Java 17+ Spring Boot WebFlux demo

The demo includes a WebClient calling an upstream, a service keeping publishers reactive, a WebFlux controller returning Mono, and a batch adapter illustrating blocking at an imperative boundary.

### 18.1. Project structure

~~~text
webflux-block-boundary/
  build.gradle
  src/
    main/
      java/demo/
        DemoApplication.java
        Product.java
        ProductClient.java
        ProductService.java
        ProductController.java
        ProductBatchAdapter.java
      resources/
        application.properties
    test/
      java/demo/
        BlockingBoundaryTest.java
~~~

### 18.2. build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.6'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
    testImplementation 'com.squareup.okhttp3:mockwebserver:4.12.0'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

### 18.3. application.properties

~~~properties
spring.application.name=webflux-block-boundary
catalog.base-url=http://localhost:9090
~~~

In tests, DynamicPropertySource replaces the base URL with the local MockWebServer.

### 18.4. DemoApplication.java

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

### 18.5. Product.java

~~~java
package demo;

import java.math.BigDecimal;

public record Product(
    long id,
    String name,
    BigDecimal price
) {
}
~~~

### 18.6. ProductClient.java

~~~java
package demo;

import org.springframework.core.env.Environment;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

@Service
public class ProductClient {
    private final WebClient webClient;

    public ProductClient(
            WebClient.Builder builder,
            Environment environment) {
        String baseUrl =
            environment.getRequiredProperty("catalog.base-url");
        this.webClient = builder.baseUrl(baseUrl).build();
    }

    public Mono<ResponseEntity<Product>> getProduct(String id) {
        return webClient.get()
            .uri("/products/{id}", id)
            .accept(MediaType.APPLICATION_JSON)
            .retrieve()
            .toEntity(Product.class);
    }
}
~~~

The method returns Mono<ResponseEntity<Product>>. It keeps status, headers, and body in a single publisher. No block calls exist in the client.

### 18.7. ProductService.java

~~~java
package demo;

import org.springframework.http.HttpHeaders;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class ProductService {
    private final ProductClient client;

    public ProductService(ProductClient client) {
        this.client = client;
    }

    public Mono<ResponseEntity<Product>> getProduct(String id) {
        return client.getProduct(id)
            .map(remote -> {
                HttpHeaders headers = new HttpHeaders();

                String etag = remote.getHeaders().getETag();
                if (etag != null) {
                    headers.setETag(etag);
                }

                String requestId =
                    remote.getHeaders().getFirst("X-Request-Id");
                if (requestId != null) {
                    headers.set("X-Request-Id", requestId);
                }

                return new ResponseEntity<>(
                    remote.getBody(),
                    headers,
                    remote.getStatusCode()
                );
            });
    }
}
~~~

The service forwards only selected headers. It does not blindly forward all upstream headers.

### 18.8. ProductController.java

~~~java
package demo;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class ProductController {
    private final ProductService service;

    public ProductController(ProductService service) {
        this.service = service;
    }

    @GetMapping("/api/products/{id}")
    public Mono<ResponseEntity<Product>> getProduct(
            @PathVariable String id) {
        return service.getProduct(id);
    }
}
~~~

The controller returns the publisher to WebFlux. It calls neither block nor subscribe.

### 18.9. ProductBatchAdapter.java

~~~java
package demo;

import java.time.Duration;
import org.springframework.http.ResponseEntity;

public class ProductBatchAdapter {
    private final ProductService service;

    public ProductBatchAdapter(ProductService service) {
        this.service = service;
    }

    // Call only from a batch/CLI worker thread, never from an event loop.
    public ResponseEntity<Product> fetchForBatch(String id) {
        return service.getProduct(id)
            .blockOptional(Duration.ofSeconds(5))
            .orElseThrow(() ->
                new IllegalStateException("No response entity")
            );
    }
}
~~~

This is the imperative boundary. The adapter blocks once with a timeout and turns an empty publisher into an explicit exception. In real applications, register the adapter through appropriate configuration or instantiate it at the batch composition root; never call this method from a controller.

### 18.10. BlockingBoundaryTest.java

~~~java
package demo;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

import java.io.IOException;
import java.math.BigDecimal;
import okhttp3.mockwebserver.MockResponse;
import okhttp3.mockwebserver.MockWebServer;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.web.reactive.server.WebTestClient;
import reactor.test.StepVerifier;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class BlockingBoundaryTest {
    private static final MockWebServer UPSTREAM = startServer();

    private static MockWebServer startServer() {
        MockWebServer server = new MockWebServer();
        try {
            server.start();
            return server;
        } catch (IOException error) {
            throw new ExceptionInInitializerError(error);
        }
    }

    @DynamicPropertySource
    static void properties(DynamicPropertyRegistry registry) {
        registry.add(
            "catalog.base-url",
            () -> UPSTREAM.url("/").toString()
        );
    }

    @AfterAll
    static void stopServer() throws IOException {
        UPSTREAM.shutdown();
    }

    @Autowired
    ProductService service;

    @Autowired
    WebTestClient webTestClient;

    @Test
    void reactiveServiceCanBeVerifiedWithoutBlock() {
        UPSTREAM.enqueue(new MockResponse()
            .setResponseCode(200)
            .addHeader("Content-Type", "application/json")
            .addHeader("ETag", "\"p-42\"")
            .addHeader("X-Request-Id", "req-42")
            .setBody("""
                {"id":42,"name":"Keyboard","price":79.90}
                """));

        StepVerifier.create(service.getProduct("42"))
            .assertNext(response -> {
                assertEquals(HttpStatus.OK, response.getStatusCode());
                assertEquals("\"p-42\"", response.getHeaders().getETag());
                assertEquals("req-42",
                    response.getHeaders().getFirst("X-Request-Id"));
                assertEquals(
                    new Product(42, "Keyboard", new BigDecimal("79.90")),
                    response.getBody()
                );
            })
            .verifyComplete();
    }

    @Test
    void webFluxControllerReturnsReactiveResponse() {
        UPSTREAM.enqueue(new MockResponse()
            .setResponseCode(200)
            .addHeader("Content-Type", "application/json")
            .addHeader("ETag", "\"p-7\"")
            .setBody("""
                {"id":7,"name":"Mouse","price":25.50}
                """));

        webTestClient.get()
            .uri("/api/products/7")
            .exchange()
            .expectStatus().isOk()
            .expectHeader().valueEquals("ETag", "\"p-7\"")
            .expectBody()
            .json("""
                {"id":7,"name":"Mouse","price":25.50}
                """);
    }

    @Test
    void blockIsUsedOnlyAtTheImperativeTestBoundary() {
        UPSTREAM.enqueue(new MockResponse()
            .setResponseCode(200)
            .addHeader("Content-Type", "application/json")
            .addHeader("X-Request-Id", "batch-9")
            .setBody("""
                {"id":9,"name":"Screen","price":199.90}
                """));

        ProductBatchAdapter adapter = new ProductBatchAdapter(service);

        ResponseEntity<Product> response =
            adapter.fetchForBatch("9");

        assertNotNull(response);
        assertEquals(200, response.getStatusCode().value());
        assertEquals("batch-9",
            response.getHeaders().getFirst("X-Request-Id"));
        assertEquals("Screen", response.getBody().name());
    }
}
~~~

The first test uses StepVerifier to verify the reactive service without blocking. The second test exercises the WebFlux controller via WebTestClient. The third test invokes the adapter from the JUnit test thread to illustrate blocking at a synchronous boundary.

### 18.11. Running the application and tests

From the project directory:

~~~bash
./gradlew bootRun
~~~

Or:

~~~bash
gradle bootRun
~~~

When running the application, catalog.base-url must point to an active upstream. Example:

~~~bash
curl -i http://localhost:8080/api/products/42
~~~

Run tests:

~~~bash
./gradlew test
~~~

MockWebServer provides the local upstream for tests. Tests do not depend on the Internet or external services.

The demo illustrates two ways to use the same service:

- The WebFlux controller retains the Mono and lets the framework subscribe.
- The batch adapter awaits the result at the imperative boundary with a timeout.

## 19. Checklist for deciding whether to block

Before calling block(), ask yourself:

1. Is the current thread a Reactor Netty event loop or non-blocking thread?
2. Is the call inside a controller, WebFilter, handler, or reactive callback?
3. Is this a clearly defined synchronous boundary such as a CLI, batch worker, or test?
4. Could you return Mono/Flux and let the caller compose further?
5. Are there multiple independent requests to combine with zip before waiting?
6. Could the publisher be empty; is blockOptional needed?
7. Is there a finite timeout for the caller?
8. Does the HTTP client/SDK/JDBC already have its own connect/read/query timeouts?
9. If using a blocking library in a reactive chain, is it wrapped in fromCallable and subscribeOn(boundedElastic)?
10. Did you accidentally wrap WebClient and call block inside Callable?
11. If handling a Flux, is the source finite and bounded in size?
12. Are cancellation and cleanup propagated upstream?
13. Can the blocking API be replaced with a reactive driver/client?
14. Are tests or observability in place to detect blocking on the event loop?

| Scenario | Approach |
| --- | --- |
| WebFlux controller calling WebClient | Return Mono/Flux |
| WebFlux controller needing status/headers/body | Compose Mono<ResponseEntity<T>> |
| Batch job needing one result | block(Duration) once at worker boundary |
| Mono that may be empty | blockOptional(Duration) |
| Batch needing multiple independent APIs | Mono.zip then block once |
| Legacy blocking library in reactive chain | fromCallable + subscribeOn(boundedElastic) |
| Blocking library returning void | fromRunnable + subscribeOn(boundedElastic) |
| CPU-bound transformation | Use parallel when needed, do not block |
| Finite, small Flux | collectList then block at boundary |
| Long-lived/large Flux | Keep streaming; do not aggregate everything |
| CompletableFuture in reactive code | Mono.fromFuture |
| Testing publishers | StepVerifier or WebTestClient |

## 20. Self-check questions with answers

**Question 1.** Why must you not call block in a WebFlux controller?

**Answer:** Controllers typically execute on shared event-loop workers. block holds the worker while waiting, delaying other requests and callbacks.

**Question 2.** Does block() create a subscription?

**Answer:** Yes. Each call to block creates a new subscription; with cold publishers, calling it multiple times can execute requests or side effects multiple times.

**Question 3.** What does block() return when a Mono completes empty?

**Answer:** It returns null. Use blockOptional to receive Optional.empty more cleanly.

**Question 4.** Does block(Duration) make the call non-blocking?

**Answer:** No. It only limits how long the caller waits; the thread remains blocked during that interval.

**Question 5.** Which scheduler should isolate a synchronous JDBC call?

**Answer:** Wrap the call in Mono.fromCallable and use subscribeOn(Schedulers.boundedElastic()).

**Question 6.** Why is Mono.just(legacyCall()) unsafe?

**Answer:** legacyCall runs immediately when creating the Mono, before the scheduler can move source execution to a worker. Use fromCallable.

**Question 7.** How do subscribeOn and publishOn differ?

**Answer:** subscribeOn shifts subscription/source execution; publishOn shifts downstream signals and operators from the point where it is placed.

**Question 8.** Does placing subscribeOn(boundedElastic) before block protect an event loop calling block?

**Answer:** No. block still blocks its calling thread. The scheduler only shifts the reactive execution controlled by operators.

**Question 9.** Should you wrap WebClient and call block inside fromCallable?

**Answer:** No. WebClient is inherently non-blocking; return the publisher and compose directly.

**Question 10.** What should you do when there are two independent WebClient requests in a batch job?

**Answer:** Combine them with Mono.zip or an appropriate operator, then block once at the imperative boundary.

**Question 11.** Does block replace HTTP client connect/read timeouts?

**Answer:** No. block(Duration) caps the caller's wait time; the transport still needs its own timeouts.

**Question 12.** Can boundedElastic be used without limits?

**Answer:** No. Its pool and queue are bounded; excessive blocking work still causes bottlenecks. Limit load and prefer non-blocking APIs.

## 21. Key takeaways and official references

- block() turns a reactive publisher into a synchronous call on the current thread.
- Blocking boundaries must be determined by execution context: CLI, batch worker, or test threads may wait; WebFlux event loops may not.
- WebFlux uses a small number of event-loop workers; one blocking call can affect many requests.
- block(Duration) limits wait time, without making the caller non-blocking.
- Each block call creates a new subscription; do not call it repeatedly on the same publisher unless repeating requests/side effects is intended.
- blockOptional represents an empty Mono as Optional.empty.
- Use Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic()) for legacy synchronous APIs.
- Use publishOn to switch downstream steps; use subscribeOn to switch source subscription/execution.
- Never use Mono.just(blockingCall()) and never wrap WebClient to call block inside Callable.
- Never call Future.get, join, Thread.sleep, or toStream on the event loop.
- Keep WebClient pipelines reactive; combine multiple requests and block only once at the outer imperative boundary if needed.
- Configure timeouts on transport and blocking libraries; do not rely solely on Reactor timeouts.
- boundedElastic is bounded and must be monitored; reactive drivers remain the better option for I/O when available.

Official references:

1. [Spring Framework Reference — WebFlux Concurrency Model](https://docs.spring.io/spring-framework/reference/web/webflux/new-framework.html): concurrency model differences between MVC and WebFlux, event-loop workers, and blocking I/O warnings.
2. [Spring Framework Reference — WebClient Synchronous Use](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-synchronous.html): using WebClient synchronously via block at the end of a pipeline and composing multiple calls before waiting.
3. [Spring Framework Reference — WebClient](https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html): WebClient as a reactive, non-blocking, streaming HTTP client.
4. [Project Reactor Reference — Threading and Schedulers](https://projectreactor.io/docs/core/release/reference/coreFeatures/schedulers.html): subscribeOn, publishOn, boundedElastic, parallel, and execution contexts.
5. [Project Reactor Reference — FAQ: Wrap a Synchronous, Blocking Call](https://projectreactor.io/docs/core/release/reference/faq.html): the fromCallable combined with subscribeOn(boundedElastic) pattern.
6. [Project Reactor Javadoc — Mono](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html): block, block(Duration), blockOptional, and subscription semantics.
7. [Project Reactor Reference — Testing](https://projectreactor.io/docs/core/release/reference/testing.html): StepVerifier and testing publishers.
8. [BlockHound](https://github.com/reactor/BlockHound): tool for detecting blocking calls on non-blocking threads during development/testing.
