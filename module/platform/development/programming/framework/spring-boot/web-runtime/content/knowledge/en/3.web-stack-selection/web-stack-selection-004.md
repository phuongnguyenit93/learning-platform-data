# spring-boot-starter-webflux and the Reactive Model with Reactor

## Learning Objectives

After this lesson, you will be able to:

- Explain the roles of `spring-boot-starter-webflux`, Spring WebFlux, and Project Reactor in a Spring Boot application.
- Describe the lifecycle of Publisher, Subscriber, Subscription, and the Reactive Streams backpressure mechanism.
- Distinguish `Mono<T>` and `Flux<T>`, and know how to combine them using common operators.
- Handle data, errors, timeouts, and cancellation in a reactive pipeline.
- Understand the event loop, Schedulers, and how to isolate blocking calls.
- Build reactive REST endpoints, call HTTP services with WebClient, and test with StepVerifier/WebTestClient.
- Identify scenarios where WebFlux should be used and mistakes that cause reactive applications to lose non-blocking benefits.

## 1. Three components to distinguish

These names often appear together, yet they belong to different layers:

| Component | Role |
|---|---|
| Spring Boot | Auto-configures the application based on dependencies and settings; manages library versions via dependency management. |
| Spring WebFlux | Spring's reactive web framework: routing, controllers/handlers, request/response, codecs, and server integration. |
| Project Reactor | Reactive library implementing Reactive Streams; provides Publisher, Mono, Flux, operators, and Scheduler. |
| Reactor Netty | Non-blocking HTTP server typically selected by default by Spring Boot when running WebFlux. |

`spring-boot-starter-webflux` is the starter dependency for bringing the WebFlux stack into a Spring Boot project. This starter pulls in the libraries required for Spring WebFlux and the default reactive runtime, including Reactor and Reactor Netty at the versions managed by Spring Boot.

You can visualize the layers as follows:

~~~text
Spring Boot application
        |
        +-- spring-boot-starter-webflux
                 |
                 +-- Spring WebFlux
                 |      +-- annotated controllers
                 |      +-- functional endpoints
                 |      +-- codecs / HTTP integration
                 |
                 +-- Project Reactor
                 |      +-- Mono<T>
                 |      +-- Flux<T>
                 |      +-- operators / Scheduler
                 |
                 +-- Reactor Netty (default server)
                        +-- non-blocking HTTP I/O
~~~

Spring WebFlux uses Reactor as its primary reactive API. Reactor can be used independently outside the web layer, for example in services or stream processing. Conversely, a WebFlux application is not just a collection of Mono/Flux: the framework also manages request lifecycle, subscriptions, response writing, and server integration.

## 2. Adding spring-boot-starter-webflux to a project

### Maven

If the project uses the Spring Boot parent or BOM for version management, you do not need to declare a separate version for the starter:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-webflux</artifactId>
</dependency>
~~~

### Gradle

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
}
~~~

Do not arbitrarily mix versions of Spring Framework, Reactor, and Reactor Netty. Let Spring Boot dependency management pick compatible versions. When upgrading Spring Boot, check the release notes and dependency tree to spot compatibility changes.

### Minimal application setup

~~~java
package com.example.reactive;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ReactiveApplication {

    public static void main(String[] args) {
        SpringApplication.run(ReactiveApplication.class, args);
    }
}
~~~

When WebFlux is the only web stack, Spring Boot typically configures the application with the reactive web application type and starts Reactor Netty. The default port is typically 8080; it can be changed in `application.properties`:

~~~properties
server.port=8081
~~~

### If the project has both MVC and WebFlux starters

When the classpath contains both `spring-boot-starter-web` and `spring-boot-starter-webflux`, Spring Boot prioritizes Spring MVC by default. One common reason is that an MVC application may want to use WebClient without switching its server to WebFlux.

If you genuinely want to run a reactive web application in this situation, you can explicitly set:

~~~properties
spring.main.web-application-type=reactive
~~~

However, inspect the dependency tree and remove the MVC starter if the application does not need it. Forcing the application type does not turn blocking libraries into non-blocking ones. Adding WebFlux solely to use WebClient also does not require switching the entire server to reactive.

Inspect dependencies with:

~~~bash
mvn dependency:tree
~~~

Or with Gradle:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

## 3. Reactive Streams: the foundational protocol

Reactive Streams defines a protocol for asynchronous data streaming with a mechanism to regulate data volume. The four core components are:

- `Publisher<T>`: the data producer.
- `Subscriber<T>`: the data consumer.
- `Subscription`: the link between Publisher and Subscriber; enables requesting element counts and unsubscribing.
- `Processor<T, R>`: acts as both a Subscriber of type T and a Publisher of type R.

A standard signal flow proceeds as follows:

~~~text
Subscriber                    Publisher
    |                             |
    |-------- subscribe() ------->|
    |<------ onSubscribe(s) ------|
    |                             |
    |-------- request(n) ------->|  Subscriber requests n elements
    |<--------- onNext(x) --------|  May emit up to the requested demand
    |<--------- onNext(y) --------|
    |                             |
    |<------- onComplete ---------|  Normal completion
    |              or             |
    |<--------- onError ----------|  Terminates with an error
    |                             |
    |-------- cancel() --------->|  Cancels subscription when needed
~~~

Rules to remember:

1. A Subscriber receives `onSubscribe` before any data signals.
2. The Subscriber calls `request(n)` to indicate how many elements it is ready to receive; n must be greater than 0.
3. The Publisher must not emit more `onNext` signals than the demand requested.
4. A subscription terminates with `onComplete` or `onError`; after a terminal signal, no further data follows.
5. The Subscriber can call `cancel()` to request stopping the stream.

### What is backpressure?

Backpressure is the mechanism that allows a consumer to regulate the rate at which it receives data. For example, a source might emit millions of records, while the destination writer can only handle a small batch at a time. Demand allows the subscriber to request an amount of data matching its consumption capacity.

Backpressure is useful for large streams, HTTP streaming, and pipelines where stage speeds differ. However:

- Backpressure does not turn a blocking API into a non-blocking one.
- Not every external source can throttle according to demand; an adapter may have to buffer or apply its own policy.
- Operators may prefetch or hold buffers. Understand memory limits and operator behavior.
- `onBackpressureBuffer` can cause memory to grow if the producer is consistently faster than the consumer; you must configure appropriate limits and overflow policies.

## 4. Mono and Flux

Project Reactor provides two primary Publisher types:

| Type | Number of elements | Usage examples |
|---|---:|---|
| `Mono<T>` | 0 or 1 | Finding a user, retrieving an order, completing a record save. |
| `Flux<T>` | 0 to N | Product lists, events, streaming data. |

Important cases:

- `Mono.just(value)`: emits an already-available value.
- `Mono.empty()`: completes without emitting a value.
- `Mono.error(exception)`: terminates with an error.
- `Mono.justOrEmpty(nullableValue)`: emits the value if non-null, or completes empty if null.
- `Flux.just(a, b, c)`: emits the given values.
- `Flux.fromIterable(items)`: emits elements from an Iterable.
- `Flux.range(start, count)`: emits a finite sequence of integers.
- `Flux.empty()` and `Flux.error(exception)`: correspond to an empty stream and an error stream.

Example:

~~~java
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

Mono<String> oneName = Mono.just("An");

Flux<Integer> numbers = Flux.range(1, 5);

Mono<String> noName = Mono.empty();

Flux<String> names = Flux.just("An", "Binh", "Chi");
~~~

`Mono<T>` is not equivalent to an already-started Future. It is a Publisher describing a result that may be emitted in the future. Similarly, `Flux<T>` does not necessarily hold the entire list in memory upfront; it can emit data over time.

### Assembly and subscription

When chaining operators, you are typically building the pipeline (assembly). Actual work usually starts when a subscription occurs.

~~~java
Mono<Integer> pipeline = Mono.fromSupplier(() -> {
    System.out.println("Creating value");
    return 10;
}).map(value -> value * 2);

// Without a subscriber, the supplier has not been called yet.
pipeline.subscribe(value -> System.out.println("Result: " + value));
~~~

Output:

~~~text
Creating value
Result: 20
~~~

In a WebFlux application, the framework subscribes to the Publisher returned by the controller to handle the request and response. Therefore, controllers typically only need to return a Mono or Flux; do not manually call `subscribe()` to spawn an independent flow.

A note on when data is produced:

- `Mono.just(value)` captures the value at assembly time and replays it to subscribers.
- `Mono.fromSupplier(...)` invokes the supplier when subscribed.
- `Mono.defer(...)` creates a new Publisher per subscription, useful when computing or reading state at subscribe time.

## 5. Common operators

Operators transform one Publisher into another. Check the input types, output types, and how an operator handles empty/error signals before composing pipelines.

### map: synchronous element-by-element transformation

~~~java
Mono<Integer> doubled = Mono.just(5)
    .map(number -> number * 2);
~~~

The result is a `Mono<Integer>` emitting 10. Use `map` when the transformation returns a plain value, not a Publisher.

### flatMap: chaining another reactive operation

~~~java
Mono<Order> order = orderRepository.findById(orderId);

Mono<Customer> customer = order
    .flatMap(foundOrder -> customerRepository.findById(foundOrder.customerId()));
~~~

`flatMap` takes a value, calls a function that returns a Publisher, and flattens the result into the pipeline. This is the key operator when the next step is also an asynchronous operation.

### filter: keeping elements matching a condition

~~~java
Flux<Integer> evenNumbers = Flux.range(1, 6)
    .filter(number -> number % 2 == 0);
~~~

The result emits 2, 4, 6.

### concatMap, flatMap, and flatMapSequential

When each element needs to invoke another Publisher:

- `flatMap` allows inner Publishers to run concurrently; emission order is not guaranteed.
- `concatMap` processes inner Publishers sequentially and preserves source order.
- `flatMapSequential` can subscribe concurrently while preserving source emission order; it may buffer early-arriving results.

Choose based on ordering and concurrency requirements rather than substituting them mechanically.

### zip: combining multiple results

~~~java
Mono<Product> product = productRepository.findById(id);
Mono<Stock> stock = stockRepository.findStock(id);

Mono<ProductView> view = Mono.zip(product, stock)
    .map(tuple -> new ProductView(tuple.getT1(), tuple.getT2()));
~~~

`zip` waits for each source to emit a value to form a tuple. If one source completes empty, the combined result may complete empty. If one source errors, the error propagates according to the operator's rules.

### defaultIfEmpty and switchIfEmpty

`Mono.empty()` is not an error. Use `defaultIfEmpty` to substitute a default value or `switchIfEmpty` to switch to another Publisher:

~~~java
Mono<Product> product = productRepository.findById(id)
    .switchIfEmpty(Mono.error(new ProductNotFoundException(id)));
~~~

### take, collectList, and limitRate

- `take(n)`: receives at most n elements and then completes.
- `collectList()`: collects elements into a List inside a Mono; suitable for bounded datasets.
- `limitRate(n)`: adjusts how upstream demand is requested in batches; it does not limit total element count like `take(n)`.

Do not use `collectList()` on unbounded streams or very large datasets without a clear reason, because the entire result will be held in memory.

## 6. Error handling in Reactor

In Reactive Streams, an error is a terminal signal of a Publisher. When an operator raises an exception, the pipeline switches to the error path and subsequent normal data-processing steps do not continue as on success.

Common operators:

| Operator | Purpose |
|---|---|
| `onErrorReturn(value)` | Replaces an error with a fixed fallback value. |
| `onErrorResume(error -> publisher)` | Switches to a fallback Publisher, optionally based on error type. |
| `onErrorMap(error -> newError)` | Transforms an exception into another error type. |
| `doOnError(...)` | Performs a side effect such as logging; does not handle or recover from the error. |
| `retry(n)` / `retryWhen(...)` | Re-subscribes to the source on error according to a retry policy. |

Conditional fallback example:

~~~java
Mono<Product> result = productService.findById(id)
    .onErrorResume(TimeoutException.class,
        error -> cacheService.findById(id));
~~~

Error transformation example:

~~~java
Mono<Product> result = productService.findById(id)
    .onErrorMap(error ->
        new ProductLookupException("Unable to look up product", error));
~~~

Retry with backoff example:

~~~java
import java.time.Duration;
import reactor.util.retry.Retry;

Mono<Response> response = remoteClient.call()
    .retryWhen(Retry.backoff(3, Duration.ofMillis(200)));
~~~

Retries can repeat side effects. Only retry operations that are safe to repeat or have idempotency keys/duplicate-prevention mechanisms. Do not retry every exception; validation errors or missing data typically do not resolve themselves on retry.

In WebFlux, you can centralize HTTP error handling using `@ExceptionHandler`, `@ControllerAdvice`, or the application's error-handling mechanism. Do not turn every error into HTTP 200 with an error body; keep status codes reflective of the actual outcome.

## 7. Cancellation and the request lifecycle

Cancellation occurs when a subscriber no longer needs data. For example, a client closes the connection before the server finishes emitting a stream. The framework can cancel the subscription so downstream/upstream steps stop work if the source and operators support cancellation.

Things to keep in mind:

- Cancellation does not guarantee recalling an external I/O operation already sent.
- A side effect already executed is not automatically rolled back when a client disconnects.
- When processing long streams, let cancellation propagate naturally through the pipeline.
- Avoid creating background subscriptions inside controllers because it detaches work from the request lifecycle and makes error/cancellation management difficult.

You can observe the lifecycle using hooks such as `doOnSubscribe`, `doOnNext`, `doOnError`, `doOnCancel`, and `doFinally`. Use these hooks only for observational side effects like metrics/logging; do not place core business logic there if it needs to produce a return value.

## 8. Threads, event loop, and Scheduler

### Event loop in WebFlux

When using Reactor Netty, WebFlux typically handles I/O on a pool of event-loop threads. One event-loop thread can serve many connections because it does not synchronously wait for each I/O operation. When a socket has data or a non-blocking operation completes, the corresponding callback is scheduled for execution.

This model is efficient when code quickly yields control back to the event loop and dependencies also support non-blocking operations. If an event loop is held by a blocking call, other connections can be affected.

### Schedulers in Reactor

A Scheduler determines where part of a pipeline executes. Common schedulers:

- `Schedulers.parallel()`: thread pool intended for CPU-bound tasks, suitable for short, non-blocking computations.
- `Schedulers.boundedElastic()`: bounded thread pool intended for blocking work or tasks that may wait longer.
- `Schedulers.single()`: a shared sequential thread for tasks requiring single-thread execution.
- `Schedulers.immediate()`: executes immediately on the current thread.

Do not switch every operator to another scheduler without reason. Switching schedulers incurs thread-hopping overhead and can negate event-loop benefits.

### subscribeOn and publishOn

- `subscribeOn(scheduler)` affects the subscription process and upstream sources; typically used to move a blocking source onto an appropriate scheduler.
- `publishOn(scheduler)` switches execution of downstream operators from that point onward to the chosen scheduler.

Example isolating a blocking API:

~~~java
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

Mono<User> user = Mono.fromCallable(() -> legacyJdbcDao.findUser(id))
    .subscribeOn(Schedulers.boundedElastic());
~~~

This snippet avoids running JDBC directly on the event loop. However, JDBC is still blocking and still occupies a thread while waiting. If a matching reactive driver exists, consider using it for true non-blocking I/O.

### Things to avoid

- Calling `Thread.sleep()`, blocking JDBC/JPA, or a blocking HTTP client directly on the event loop.
- Calling `block()` inside a controller or a pipeline running on a non-blocking thread.
- Manually calling `subscribe()` in a controller just to obtain a result.
- Using `boundedElastic` as a dumping ground for all work without measuring load or bounding blocking sources.
- Assuming operators always run on the same thread or on a specific thread.

## 9. Building a REST API with WebFlux

The following example illustrates a small REST API using Java 17+, Spring Boot, and in-memory data. These are source files of a Spring Boot application; the `spring-boot-starter-webflux` dependency is declared as shown earlier.

### DTO

~~~java
package com.example.reactive;

public record Product(long id, String name) {
}
~~~

### Service returning a Publisher

~~~java
package com.example.reactive;

import java.util.Map;

import org.springframework.stereotype.Service;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Service
public class ProductService {

    private final Map<Long, Product> products = Map.of(
        1L, new Product(1L, "Keyboard"),
        2L, new Product(2L, "Mouse"),
        3L, new Product(3L, "Monitor")
    );

    public Mono<Product> findById(long id) {
        return Mono.justOrEmpty(products.get(id));
    }

    public Flux<Product> findAll() {
        return Flux.fromIterable(products.values());
    }
}
~~~

### Controller

~~~java
package com.example.reactive;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/products")
public class ProductController {

    private final ProductService service;

    public ProductController(ProductService service) {
        this.service = service;
    }

    @GetMapping("/{id}")
    public Mono<ResponseEntity<Product>> findById(@PathVariable long id) {
        return service.findById(id)
            .map(ResponseEntity::ok)
            .defaultIfEmpty(ResponseEntity.notFound().build());
    }

    @GetMapping
    public Flux<Product> findAll() {
        return service.findAll();
    }
}
~~~

When running the application:

~~~bash
mvn spring-boot:run
~~~

Calling the API:

~~~bash
curl http://localhost:8080/api/products/1
curl http://localhost:8080/api/products/99
curl http://localhost:8080/api/products
~~~

JSON result for product id 1:

~~~json
{"id":1,"name":"Keyboard"}
~~~

For id 99, the endpoint returns HTTP 404 because `Mono.empty()` is mapped to `ResponseEntity.notFound()`. The list endpoint returns a Flux; WebFlux writes elements into the response using the appropriate HTTP message writer.

This example uses an in-memory Map, so lookups are very fast and do not demonstrate real asynchronous I/O. In a real application, use repositories/drivers suitable for your data model and system load.

## 10. Calling HTTP services with WebClient

WebClient is Spring's reactive HTTP client. It can be used in WebFlux applications as well as in Spring MVC applications. WebClient supports non-blocking I/O, streaming, and returning Mono/Flux.

Example client calling a catalog service:

~~~java
package com.example.reactive;

import java.time.Duration;

import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.core.publisher.Mono;

@Component
public class CatalogClient {

    private final WebClient webClient;

    public CatalogClient(WebClient.Builder builder) {
        this.webClient = builder
            .baseUrl("https://catalog.example")
            .build();
    }

    public Mono<CatalogItem> findById(String id) {
        return webClient.get()
            .uri("/items/{id}", id)
            .retrieve()
            .bodyToMono(CatalogItem.class)
            .timeout(Duration.ofSeconds(3));
    }
}
~~~

`CatalogItem` is a DTO of the catalog service. `retrieve()` converts the response into a body; 4xx/5xx statuses are represented by default as WebClient response errors. You can use `onStatus(...)` to map status codes or error bodies to custom business exceptions.

Example integrating the client into a controller/service:

~~~java
public Mono<CatalogItem> loadCatalogItem(String id) {
    return catalogClient.findById(id)
        .onErrorResume(error -> fallbackCatalog.findById(id));
}
~~~

In real code, fallbacks should be chosen by error type. Do not fall back on all errors if doing so masks authentication errors, programming bugs, or invalid data.

Do not call `block()` just to unwrap a WebClient result in the request path. Return Mono/Flux so the pipeline continues asynchronously. If an MVC application needs to call WebClient, the MVC controller can still use an MVC-compatible return type; that does not automatically switch the server to WebFlux.

## 11. Streaming and functional endpoints

WebFlux supports streaming because controllers can return a Flux and the framework writes data element by element when supported by the media type/protocol.

Common use cases:

- Server-Sent Events (SSE) for pushing events from the server to browsers.
- Streaming large datasets instead of collecting everything into a List.
- Proxying data between services.
- Event streams or status updates over time.

SSE endpoint example:

~~~java
import java.time.Duration;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Flux;

@RestController
public class EventController {

    @GetMapping(value = "/events", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public Flux<String> events() {
        return Flux.interval(Duration.ofSeconds(1))
            .map(sequence -> "event-" + sequence);
    }
}
~~~

In this example, an event string is emitted every second. For real connections, consider connection limits, timeouts, heartbeats, authentication, cancellation, and scalability of the event source. Do not use infinite streams if clients or infrastructure lack appropriate termination and resource management policies.

In addition to annotated controllers, WebFlux supports functional endpoints with `RouterFunction` and `HandlerFunction`. This approach is useful when you want to define routes and handlers using a Java DSL; both styles use reactive types and share the WebFlux runtime foundation.

## 12. Testing pipelines and HTTP endpoints

### StepVerifier

StepVerifier belongs to Reactor Test and verifies a Publisher's signals in order without manually subscribing and waiting.

Example:

~~~java
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

class NumberServiceTest {

    @Test
    void emitsEvenNumbers() {
        Flux<Integer> numbers = Flux.range(1, 6)
            .filter(number -> number % 2 == 0);

        StepVerifier.create(numbers)
            .expectNext(2, 4, 6)
            .verifyComplete();
    }
}
~~~

StepVerifier can verify empty signals, errors, demand, cancellation, and time-dependent flows. For tests using timers/delays, virtual time can be used to test quickly without waiting in real time.

### WebTestClient

WebTestClient tests WebFlux endpoints over HTTP without starting a real server, or it can bind to a running server in integration tests. Example endpoint check:

~~~java
webTestClient.get()
    .uri("/api/products/1")
    .exchange()
    .expectStatus().isOk()
    .expectBody()
    .jsonPath("$.name").isEqualTo("Keyboard");
~~~

In integration tests, you can use `@SpringBootTest` combined with WebTestClient configuration matching how the application starts. Test status codes, headers, bodies, errors, timeouts, and client disconnects on streaming endpoints.

## 13. Common mistakes when starting with Reactor

### Using map for a function returning Mono/Flux

If the inner function returns a Publisher, use `flatMap` or `concatMap` depending on ordering requirements. Using `map` produces a nested Publisher such as `Mono<Mono<T>>`.

### Calling block() to obtain a value

`block()` turns a reactive operation into synchronous waiting. In a WebFlux request path, this can block the event loop and reduce concurrency capacity. Compose Publishers with operators and return them to the framework.

### Calling subscribe() in a controller

Manually subscribing creates a flow detached from the request lifecycle. The framework no longer manages that result as the request's response; errors, cancellation, and completion timing become hard to control. Return the Publisher from the controller.

### Placing JDBC/JPA on the event loop

Mono/Flux does not make blocking libraries non-blocking. Use a reactive driver if suitable, or isolate blocking segments on boundedElastic during transition.

### Confusing empty with error

`Mono.empty()` is a normal completion with no element. If you need to signal "not found," use `switchIfEmpty` to emit an error or return a 404 response according to the API semantics.

### Using flatMap when ordering matters

`flatMap` can emit results out of source order. Use `concatMap` when sequential execution is needed; use `flatMapSequential` when concurrent execution is needed while preserving source emission order.

### Collecting an unbounded stream into a List

`collectList()` holds every element in memory. For large or unbounded data, process element by element, paginate, or use streaming/backpressure.

### Uncontrolled retries

Retries can repeat side effects, amplify load on a failing service, and trigger cascading failures. Configure retry counts, backoff, timeouts, error classification, and ensure idempotency.

### Using ThreadLocal as in the thread-per-request model

A reactive pipeline can switch threads via Schedulers. Do not assume ThreadLocal always stays with a request. For per-subscription data, consider Reactor Context and appropriate context propagation integrations.

## 14. When should you choose WebFlux?

WebFlux is suitable when a system has high concurrent I/O, needs streaming, coordinates multiple services, and all critical libraries support non-blocking operations. The event-loop model can serve many connections without holding a dedicated worker thread throughout I/O waits.

Spring MVC is often a simpler and more effective choice when an application relies heavily on JDBC/JPA or blocking libraries, business flows are primarily synchronous, and the team is already familiar with the Servlet stack. MVC also supports async requests and can use WebClient.

Before choosing WebFlux, evaluate:

1. Is the workload primarily I/O-waiting or CPU-bound?
2. Do database drivers and HTTP clients support non-blocking operations?
3. Are there blocking libraries running in the request path?
4. Does the system require streaming or a high volume of concurrent connections?
5. Can the team operate, debug, and test Reactor pipelines?
6. Do benchmarks reflect realistic latency, throughput, memory, and downstream load?

Reactive is not automatically faster than imperative. Effectiveness depends on workload, dependencies, pipeline design, resource limits, and operational capability. A WebFlux application full of blocking calls can be harder to understand than MVC without yielding corresponding benefits.

## 15. Self-check questions

1. How do `spring-boot-starter-webflux`, Spring WebFlux, and Project Reactor differ in their roles?
2. How do Publisher, Subscriber, and Subscription coordinate to transfer data?
3. How does `Mono<T>` differ from `Flux<T>`? Is `Mono.empty()` an error?
4. Why should a WebFlux controller return a Publisher instead of calling `subscribe()` itself?
5. When should you use `map`, `flatMap`, `concatMap`, and `flatMapSequential`?
6. What does backpressure regulate? Does it automatically turn JDBC into non-blocking?
7. What is the main difference between `subscribeOn` and `publishOn`?
8. Why should you not call `block()` on the event loop?
9. If an application only needs WebClient but has both the MVC and WebFlux starters, which web stack does Spring Boot typically select?
10. When should you choose WebFlux over Spring MVC?

### Suggested answers

1. The starter is a dependency bundle; WebFlux is the web framework; Reactor is the reactive library providing Mono, Flux, operators, and Schedulers.
2. The Subscriber registers with the Publisher, receives a Subscription, and calls request(n); the Publisher emits onNext up to demand and finishes with onComplete or onError. The Subscriber can cancel.
3. Mono emits 0 or 1 element; Flux emits 0 to many elements. Mono.empty completes normally without emitting a value.
4. The framework needs to manage the subscription and tie the outcome to the HTTP request lifecycle, including errors and cancellation.
5. map performs synchronous transformation; flatMap chains a Publisher; concatMap processes sequentially and preserves order; flatMapSequential runs inner Publishers concurrently while preserving emission order.
6. Backpressure regulates the amount of data requested by the subscriber. JDBC remains blocking even when wrapped in a Mono.
7. subscribeOn affects subscription/upstream sources; publishOn switches downstream execution starting from where the operator is placed.
8. block holds the thread waiting for a result, which can prevent the event loop from serving other connections.
9. Spring Boot prioritizes MVC by default when both starters are present; WebClient can still be used inside MVC.
10. When the workload has high concurrent I/O or streaming, most dependencies support non-blocking operations, and the team is capable of operating a reactive stack.

## 16. Official references

- [Spring Boot: Reactive Web Applications](https://docs.spring.io/spring-boot/reference/web/reactive.html) — starters, auto-configuration, and reactive web runtime.
- [Spring Framework: Web on Reactive Stack](https://docs.spring.io/spring-framework/reference/web/webflux.html) — WebFlux architecture, controllers, functional endpoints, and runtime.
- [Project Reactor Reference Guide](https://projectreactor.io/docs/core/release/reference/index.html) — Mono, Flux, operators, Schedulers, error handling, and testing.
- [Reactive Streams Specification](https://www.reactive-streams.org/) — Publisher/Subscriber protocol and backpressure.
- [Spring WebClient](https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html) — Spring's reactive HTTP client.
- [Spring WebFlux Testing](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html) — HTTP testing with WebTestClient.
