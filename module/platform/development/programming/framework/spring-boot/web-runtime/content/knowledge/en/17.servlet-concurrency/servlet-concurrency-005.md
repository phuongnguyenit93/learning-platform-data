# Returning Mono or Flux from MVC Controllers and Limits of Conversion to Non-Blocking I/O

## 1. The problem: does a reactive return type turn Spring MVC into WebFlux?

In a **Spring Boot application using Spring MVC (Servlet stack)**, a `@RestController` method can return `Mono<T>` or `Flux<T>` from Project Reactor. This is very useful when a controller calls a reactive HTTP client (`WebClient`) or a service that already returns a reactive publisher.

However, there is a critical architectural boundary: **Spring MVC supports async requests and reactive return values; it does not convert the entire Servlet HTTP pipeline into Spring WebFlux non-blocking I/O**. According to Spring Framework 6.2 documentation, when writing streaming responses, Spring MVC supports reactive backpressure, yet **writes to the Servlet response remain blocking and run on another thread via an `AsyncTaskExecutor`**.

Lesson objectives:

- Understand why `Mono` and `Flux` are valid in MVC controllers and how the framework adapts them to MVC async.
- Distinguish `Mono<T>`, `Flux<T>` returning `application/json`, and `Flux<T>` returning streaming media types such as `text/event-stream` or `application/x-ndjson`.
- Understand `ReactiveAdapterRegistry`, `DeferredResult`, `ResponseBodyEmitter`, `SseEmitter`, Servlet `AsyncContext`, `AsyncTaskExecutor`, and the limits of blocking response writes.
- Build a runnable Spring Boot 3.5 + Java 17 + Spring MVC example and test it with `MockMvc`.
- Structure `WebClient` calls, timeouts, cancellation, backpressure, context propagation, and choose between MVC and WebFlux based on workload rather than just return types.

The examples use **Spring Boot 3.5.x / Spring Framework 6.2.x / Java 17**. On Spring Boot 4.x, check the corresponding starters, packages, test annotations, and version-specific configuration.

## 2. From HTTP request to reactive publisher in Spring MVC

Example of a valid controller:

```java
@GetMapping("/api/greeting")
public Mono<Greeting> greeting() {
    return Mono.just(new Greeting("Hello"));
}
```

With `@RestController` and Reactor on the classpath, Spring MVC does not treat `Mono` as a plain JSON object to serialize directly. The framework recognizes the reactive type via `ReactiveAdapterRegistry`, registers MVC async handling, and awaits the result signal.

Overview diagram:

```text
HTTP request
    |
    v
Tomcat/Jetty/Undertow (Servlet container)
    |
    v
DispatcherServlet -> HandlerMapping -> HandlerAdapter
    |
    v
@RestController method returns Mono or Flux
    |
    v
ReactiveAdapterRegistry recognizes Publisher
    |
    +--> Mono<T> / 0..1 publisher
    |       |
    |       v
    |   MVC asynchronous handling (~ DeferredResult)
    |       |
    |       v
    |   When result is ready -> ASYNC dispatch -> response
    |
    +--> Flux<T> with streaming media type
    |       |
    |       v
    |   MVC streaming (~ ResponseBodyEmitter / SseEmitter)
    |       |
    |       v
    |   Blocking Servlet response writes on AsyncTaskExecutor
    |
    +--> Flux<T> with non-streaming media type
            |
            v
        Collect into List (~ DeferredResult<List<?>>)
            |
            v
        Serialize a normal response
```

**Do not conflate:**

- `Mono` and `Flux`: abstractions for data and when elements are emitted.
- Servlet async: the mechanism for temporarily releasing the container request thread and resuming when a result arrives.
- Non-blocking network I/O: a property of transport reads/writes; it is not created automatically just because a method returns a Reactor type.

## 3. What is the role of ReactiveAdapterRegistry?

`ReactiveAdapterRegistry` belongs to `org.springframework.core` and is used to recognize and adapt supported reactive types such as Reactor `Mono`/`Flux`, certain other publishers, or `CompletionStage` depending on version support.

For MVC annotated controllers, return value handlers use this information to decide:

1. Whether the publisher emits **0 or 1 value** or **multiple values**.
2. Whether the response uses a streaming media type.
3. Whether the result should go through single-value async handling, item-by-item streaming, or aggregation into a `List`.
4. When the framework should register async processing, redispatch the request, and handle errors.

You do not need to manually register a `ReactiveAdapterRegistry` just for Reactor `Mono`/`Flux` to work in a standard project. Other reactive libraries require the appropriate adapters and dependencies.

References to `DeferredResult`/`ResponseBodyEmitter` are **comparisons of processing behavior**; they do not mean the framework literally instantiates those exact objects in your code every time. Understand them in terms of the documented lifecycle.

## 4. Mono<T> in MVC: similar to DeferredResult

For a single asynchronous value:

```java
@GetMapping("/api/one")
public Mono<Item> one() {
    return service.fetchItem();
}
```

Overview:

1. The controller returns `Mono<Item>` without calling `.block()`.
2. MVC registers Servlet async request processing and can release the initial container thread.
3. When the publisher emits an item or error, MVC performs the appropriate response-completion steps, typically including an async dispatch.
4. MVC's `HttpMessageConverter` serializes the item to JSON when the endpoint is `@RestController` with Jackson present.

Spring MVC still uses **Servlet APIs** and async dispatch; it does not turn `DispatcherServlet` into WebFlux's `DispatcherHandler`.

An empty publisher `Mono.empty()` also does not automatically mean **404 Not Found**. If business logic needs to report a missing resource, express it explicitly:

```java
return service.fetchItem(id)
        .switchIfEmpty(Mono.error(
            new ResponseStatusException(
                HttpStatus.NOT_FOUND, "Item not found")));
```

The snippet above is an MVC/Reactor fragment requiring imports for `Mono`, `ResponseStatusException`, and `HttpStatus`. Do not assume `Mono.empty()` produces a stable HTTP 404 contract on its own.

## 5. Flux<T> returning application/json: may aggregate entirely into a List

When a controller returns a `Flux<Item>` while the response media type is regular `application/json`:

```java
@GetMapping(
    path = "/api/items",
    produces = MediaType.APPLICATION_JSON_VALUE)
public Flux<Item> items() {
    return Flux.just(
        new Item(1, "A"),
        new Item(2, "B"));
}
```

According to Spring Framework MVC async docs, a **multi-value publisher + non-streaming media type** is handled similarly to `DeferredResult<List<?>>`. Elements are collected first and then serialized as a JSON response, for example:

```json
[
  {"id":1,"name":"A"},
  {"id":2,"name":"B"}
]
```

Key point: **`Flux` does not guarantee that HTTP output is emitted continuously element by element**. If the publisher emits one million elements under a non-streaming media type, collecting them can consume huge memory and delay when the client receives the body.

For small JSON arrays, this is convenient. For millions of records or infinite streams, choose a **streaming** format and bound resources.

## 6. Flux<T> returning a streaming media type: response is streamed incrementally

When `Flux` uses a streaming-capable media type such as:

- `text/event-stream`: Server-Sent Events (SSE).
- `application/x-ndjson`: newline-delimited JSON.
- Other streaming representations supported by MVC message converters in the specific stack.

Spring MVC switches to behavior similar to `ResponseBodyEmitter` or `SseEmitter`, emitting items incrementally using the matching `HttpMessageConverter`.

```java
@GetMapping(
    path = "/api/events",
    produces = MediaType.TEXT_EVENT_STREAM_VALUE)
public Flux<ServerSentEvent<String>> events() {
    return Flux.interval(Duration.ofMillis(200))
        .take(3)
        .map(i -> ServerSentEvent.<String>builder(
                    "tick-" + i)
            .id(Long.toString(i))
            .event("tick")
            .build());
}
```

This is a method inside an MVC `@RestController`; it requires imports for Reactor `Mono`/`Flux`, `java.time.Duration`, `MediaType`, and `org.springframework.http.codec.ServerSentEvent`.

The response may contain three SSE events with IDs 0, 1, and 2. Exact byte-delivery timing is not guaranteed, as the servlet container, TCP/TLS, and reverse proxies can buffer or flush on their own cadence.

**Crucially:** Streaming a `Flux` in MVC can apply reactive backpressure, yet when writing to the Servlet HTTP response, the framework performs **blocking writes on an executor**. Do not call this “WebFlux running on Tomcat” or “end-to-end non-blocking I/O.”

## 7. Three comparison scenarios to remember

| Controller return | HTTP representation | MVC handling per docs | Streams element by element? |
|---|---|---|---|
| `Mono<Item>` | `application/json` | Like `DeferredResult` for 0..1 results | No, single item |
| `Flux<Item>` | `application/json` | Like `DeferredResult<List<?>>` | Normally **no**; collects first |
| `Flux<Item>` | `application/x-ndjson` | Like response emitter with streaming | Yes, when writer/codec supports it |
| `Flux<ServerSentEvent<T>>` | `text/event-stream` | Like `SseEmitter` | Yes |
| `Callable<Item>` | `application/json` | Async task executor produces one result | No, single item |
| `StreamingResponseBody` | e.g. `application/octet-stream` | Writes directly to `OutputStream` on worker thread | Writes in chunks, but blocking |

An infinite `Flux` with `application/json` will never complete the aggregation step as expected. If the endpoint is a live event source, pick SSE or another streaming format with a clear contract.

Do not judge the response solely from the method signature. Inspect `produces`, `Accept`, `Content-Type`, and the converters on the classpath.

## 8. Complete example: Spring Boot 3.5 + Java 17, still MVC

To build an MVC controller returning Reactor publishers, create a Java 17 Maven project with **Spring Web** and **reactor-core**:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
        <groupId>io.projectreactor</groupId>
        <artifactId>reactor-core</artifactId>
    </dependency>
</dependencies>
```

The `<dependencies>` section above is for a `pom.xml` that already has the Spring Boot parent/dependency management. `reactor-core` provides `Mono`/`Flux`, while `spring-boot-starter-web` provides the Servlet MVC runtime (typically Tomcat by default) and JSON converter.

If `WebClient` is also needed, you can add `spring-boot-starter-webflux`; when both `starter-web` and `starter-webflux` are present, **Spring Boot defaults to web application type SERVLET/MVC**. To keep this example clear, we do not add the WebFlux starter.

Structure:

```text
src/main/java/com/example/mvcasync/
    MvcAsyncApplication.java
    ReactiveReturnController.java
    MvcAsyncConfiguration.java
src/main/resources/
    application.properties
src/test/java/com/example/mvcasync/
    ReactiveReturnControllerTest.java
```

Do not add `@EnableWebFlux` or `@EnableWebMvc` for this example. Boot's MVC auto-configuration is enough to detect `@RestController` and handle async return values.

## 9. Entry point and configuration

File `src/main/java/com/example/mvcasync/MvcAsyncApplication.java`:

```java
package com.example.mvcasync;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MvcAsyncApplication {

    public static void main(String[] args) {
        SpringApplication.run(MvcAsyncApplication.class, args);
    }
}
```

File `src/main/resources/application.properties`:

```properties
server.port=8080

# Default maximum duration for MVC asynchronous requests
spring.mvc.async.request-timeout=30s

# Spring Boot auto-configured applicationTaskExecutor (when conditions apply)
spring.task.execution.pool.core-size=4
spring.task.execution.pool.max-size=16
spring.task.execution.pool.queue-capacity=100
spring.task.execution.thread-name-prefix=mvc-async-
```

The `spring.task.execution.pool.*` settings above only apply when Boot uses its auto-configured `ThreadPoolTaskExecutor` (on Java 17 without virtual threads enabled). If the application defines a custom `Executor` bean causing Boot auto-configuration to back off, verify which bean MVC actually uses.

A finite queue size is important: if the queue is unbounded, increasing `max-size` may not spawn additional worker threads under load; the queue can keep growing instead of the pool expanding.

`spring.mvc.async.request-timeout` is the async request timeout, **not** `WebClient`'s connect/read timeout, not an end-to-end HTTP limit across every proxy, and not a cap on `Flux` element count.

## 10. Runnable controller: Mono, Flux JSON, and SSE

File `src/main/java/com/example/mvcasync/ReactiveReturnController.java`:

```java
package com.example.mvcasync;

import java.time.Duration;

import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/reactive")
public class ReactiveReturnController {

    @GetMapping(
        path = "/single",
        produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<Item> single() {
        return Mono.delay(Duration.ofMillis(40))
                .map(tick -> new Item(1, "one"));
    }

    @GetMapping(
        path = "/collection",
        produces = MediaType.APPLICATION_JSON_VALUE)
    public Flux<Item> collection() {
        return Flux.just(
                new Item(1, "one"),
                new Item(2, "two"))
            .delayElements(Duration.ofMillis(25));
    }

    @GetMapping(
        path = "/events",
        produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public Flux<ServerSentEvent<String>> events() {
        return Flux.interval(Duration.ofMillis(200))
            .take(3)
            .map(i -> ServerSentEvent.<String>builder(
                    "tick-" + i)
                .id(Long.toString(i))
                .event("tick")
                .build());
    }

    public record Item(long id, String name) {
    }
}
```

This is a complete Java 17 class:

- `/single`: emits one item after roughly 40 ms; MVC handles it as a single async value.
- `/collection`: emits two items with a delay; because the response is `application/json`, MVC waits to collect them and returns a JSON array.
- `/events`: emits three SSE events at intervals; MVC can stream the events instead of waiting to construct a JSON array.
- `record Item` is a simple DTO serialized to JSON by Jackson from the Spring Web starter.

`Flux.interval` and `Mono.delay` use Reactor schedulers for timing signals; delays are not real-time guarantees. Never call `.block()` inside the controller. Run within the Maven project with Spring/Reactor dependencies—**do not compile and run a single file with plain `javac`**.

## 11. AsyncTaskExecutor for Servlet blocking writes

When streaming reactive return values in MVC, Spring Framework uses an `AsyncTaskExecutor` to perform **blocking writes** to `ServletOutputStream` on another thread, avoiding blocking the upstream publisher thread. Therefore, configure and measure the executor under load.

Spring Boot 3.5 can auto-configure an **`applicationTaskExecutor`** bean (typically `ThreadPoolTaskExecutor` on Java 17 without virtual threads). MVC, WebFlux, and Spring GraphQL each have their own executor-selection rules; in MVC, the bean name and `AsyncTaskExecutor` type matter when custom executors exist.

You can explicitly tell MVC to use that executor:

File `src/main/java/com/example/mvcasync/MvcAsyncConfiguration.java`:

```java
package com.example.mvcasync;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.core.task.AsyncTaskExecutor;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.AsyncSupportConfigurer;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration(proxyBeanMethods = false)
public class MvcAsyncConfiguration implements WebMvcConfigurer {

    private final AsyncTaskExecutor executor;

    public MvcAsyncConfiguration(
            @Qualifier("applicationTaskExecutor")
            AsyncTaskExecutor executor) {
        this.executor = executor;
    }

    @Override
    public void configureAsyncSupport(
            AsyncSupportConfigurer configurer) {
        configurer.setTaskExecutor(executor);
        configurer.setDefaultTimeout(30_000L);
    }
}
```

In this demo with no other custom executor, Boot provides `applicationTaskExecutor`. This configuration is **optional to make explicit which bean MVC uses**; if properties and Boot auto-wiring suffice, this file can be omitted.

If the application already registers another `Executor` bean, conditions for the auto-configured `applicationTaskExecutor` may change. In that case, provide a bean with the proper name/type or adjust the configuration instead of assuming the example above will always inject cleanly.

`AsyncSupportConfigurer.setTaskExecutor` does not make response writes non-blocking; it only **selects the thread pool executing the blocking task**. Monitor thread count, queue depth, write duration, rejected tasks, client-disconnect errors, and how long responses remain open.

## 12. Run and observe with curl

From the Maven project root containing `mvnw`:

```bash
./mvnw spring-boot:run
```

Single JSON value:

```bash
curl -i http://localhost:8080/api/reactive/single
```

Expected body:

```json
{"id":1,"name":"one"}
```

JSON array:

```bash
curl -i http://localhost:8080/api/reactive/collection
```

Expected body:

```json
[{"id":1,"name":"one"},{"id":2,"name":"two"}]
```

Elements in the JSON array preserve the order from `Flux.just`. However, HTTP status/headers/JSON whitespace need not match identically across every container.

SSE:

```bash
curl -i -N -H 'Accept: text/event-stream' http://localhost:8080/api/reactive/events
```

`-N` tells curl not to buffer output on the client side. Expected SSE frames by content:

```text
id:0
event:tick
data:tick-0

id:1
event:tick
data:tick-1

id:2
event:tick
data:tick-2

```

Line ordering within an SSE event or flush behavior may depend on implementation; the example above represents logical data rather than a byte-for-byte transcript of `curl -i`, since `-i` also prints headers.

Even with `-N`, reverse proxies (Nginx/Ingress/CDN) can still buffer. Check headers, proxy buffering, and idle timeouts to verify whether real users actually receive events incrementally.

## 13. MockMvc: asyncDispatch is needed to inspect the final result

Because MVC handles `Mono`/`Flux` via Servlet async, a test calling only `mvc.perform(...)` may observe only the initial request stage. `MockMvc` provides `request().asyncStarted()`, `MvcResult`, and `asyncDispatch(result)` to wait and continue processing the response.

In a project that already has Spring Boot parent/dependency management, add:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
```

File `src/test/java/com/example/mvcasync/ReactiveReturnControllerTest.java`:

```java
package com.example.mvcasync;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.asyncDispatch;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.request;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ReactiveReturnControllerTest {

    @Autowired
    private MockMvc mvc;

    @Test
    void monoAsyncResultReturnsOneJsonObject() throws Exception {
        MvcResult pending = mvc.perform(
                get("/api/reactive/single"))
            .andExpect(request().asyncStarted())
            .andReturn();

        mvc.perform(asyncDispatch(pending))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(
                    MediaType.APPLICATION_JSON))
            .andExpect(jsonPath("$.id").value(1))
            .andExpect(jsonPath("$.name").value("one"));
    }

    @Test
    void fluxWithJsonIsAggregatedAsAnArray() throws Exception {
        MvcResult pending = mvc.perform(
                get("/api/reactive/collection"))
            .andExpect(request().asyncStarted())
            .andReturn();

        mvc.perform(asyncDispatch(pending))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(
                    MediaType.APPLICATION_JSON))
            .andExpect(jsonPath("$[0].id").value(1))
            .andExpect(jsonPath("$[1].name").value("two"));
    }
}
```

Run:

```bash
./mvnw test
```

This is Spring MVC test code. `MockMvc` does not prove socket response writes are non-blocking, nor does it measure network flushing or proxy buffering. Use integration tests with an embedded server and an HTTP client to test SSE streaming, cancellation, timeouts, and concurrent load.

For SSE-streaming `Flux` endpoints, testing solely with `asyncDispatch` and asserting the full response after completion verifies the final content but does not prove events arrive incrementally while the stream stays open.

## 14. Using WebClient inside an MVC application

A common reason an MVC controller returns `Mono` is to call another service via non-blocking `WebClient`:

```java
@RestController
class GatewayController {

    private final WebClient client;

    GatewayController(WebClient.Builder builder) {
        this.client = builder
            .baseUrl("https://upstream.example.org")
            .build();
    }

    @GetMapping("/api/proxy/items/{id}")
    Mono<ItemDto> proxy(@PathVariable("id") long id) {
        return client.get()
            .uri("/items/{id}", id)
            .retrieve()
            .bodyToMono(ItemDto.class);
    }
}
```

This is a **fragment**: you need to create `ItemDto`, add imports, and include `spring-boot-starter-webflux` or an appropriate `WebClient` dependency; the upstream URL is only an example. When both WebFlux and MVC starters are present, Boot normally runs **SERVLET/MVC** by default.

Advantage of this pattern: while waiting for upstream to respond, the MVC controller does not hold a request thread blocked on `WebClient.block()`; it can release the Servlet thread during the wait.

Limitation: **the HTTP response back to the client still goes through the Servlet stack**. When upstream streams a large `Flux`, MVC streaming needs an executor to run blocking writes. Concurrency gains still depend on connection pools, thread pools, client/backpressure behavior, and open HTTP connections.

Some requests need `ResponseEntity<Mono<T>>` or `Mono<ResponseEntity<T>>` to decide status/headers after upstream responds. When designing, verify your specific MVC version's API; **do not assume** every generic return-type combination behaves identically to WebFlux.

## 15. Why shouldn't you call block() in the controller?

A pattern that loses the benefit:

```java
@GetMapping("/api/slow")
public Item slow() {
    return reactiveService.load().block();
}
```

In MVC, `.block()` blocks the thread handling the controller until the publisher produces a result. It forfeits the benefit of freeing the Servlet request thread while waiting on I/O.

A generally better pattern:

```java
@GetMapping("/api/slow")
public Mono<Item> slow() {
    return reactiveService.load();
}
```

However, **not calling `.block()` does not automatically make the whole application non-blocking**. If `reactiveService.load()` actually invokes JDBC, `Thread.sleep()`, or a blocking SDK **before returning the `Mono`**, the blocking work still runs on the request thread.

Poor example:

```java
public Mono<Item> load(long id) {
    Item item = jdbcRepository.findById(id);
    return Mono.just(item);
}
```

`findById` already executed synchronously before the `Mono` was created. If you must call a blocking dependency, consider MVC's standard handling (`Callable`/async executor) or isolate blocking work when integrating Reactor:

```java
public Mono<Item> load(long id) {
    return Mono.fromCallable(
            () -> jdbcRepository.findById(id))
        .subscribeOn(Schedulers.boundedElastic());
}
```

This is a **fragment assuming** the repository returns `Item` and requires importing `Schedulers`. `boundedElastic` keeps blocking tasks off Reactor event-loop threads, yet it only **shifts blocking onto a bounded worker pool**—it does not make JDBC non-blocking and does not guarantee transaction/JPA contexts migrate automatically across threads.

Do not mix `@Transactional`, JPA lazy loading, and Reactor schedulers without verifying transaction scope and thread-bound context.

## 16. Backpressure in MVC streaming: present, but no silver bullet

Reactor provides `request(n)` so downstream can regulate how many items upstream may emit. Spring MVC supports backpressure when bridging a reactive stream to a streaming HTTP response.

Still:

```text
Reactive source (Flux<T>)
           |
     reactive demand
           |
MVC response emitter bridge
           |
AsyncTaskExecutor worker
           |
ServletOutputStream.write(...)  <-- may BLOCK
           |
Servlet container -> client/proxy
```

When `ServletOutputStream.write` waits for the client to consume data, an executor thread may stay occupied. With many slow clients or long-lived SSE connections, threads/queues and latency can become bottlenecks.

Backpressure **limits item emission when downstream is slow**; it does not guarantee:

- Zero blocked threads when writing the response.
- Zero buffering in the container, proxy, or TCP stack.
- Zero queueing in the task executor.
- Zero upstream memory growth if code uses unbounded `collectList()`, `cache()`, or `onBackpressureBuffer()`.
- Immunity to slow clients or client disconnects.

In particular, a `Flux<T>` returned with `application/json` may still be collected into a `List` **before writing**, so treat that as a separate memory-aggregation concern.

## 17. Async Servlet lifecycle and ASYNC dispatch

Servlet async is designed so the initial request thread can exit while the **response remains open**. For single-value results, the Spring MVC flow typically looks like:

```text
Container thread 1
  -> DispatcherServlet -> controller returns Mono
  -> request.startAsync()
  -> exit Filter/Servlet chain, release thread
             |
             | Publisher emits value later
             v
ASYNC dispatch on container thread
  -> DispatcherServlet receives request again
  -> process async result, convert body, complete
```

During the async dispatch, `DispatcherServlet` may be invoked again, yet **it does not re-invoke the business controller method** as a brand-new request; the result stored in async processing state continues through the pipeline.

For streaming, MVC keeps the response open and writes multiple elements incrementally; a final async dispatch may occur to finish or handle errors. This is not a new HTTP round-trip from the browser.

Servlets/filters must have `asyncSupported=true`. If adding custom filters or deploying a WAR to an external container, ensure filter dispatch types align with `ASYNC`. Do not equate `ASYNC` with `FORWARD` or `ERROR`.

In default Boot embedded Servlet setups, MVC async is usually already configured appropriately; you do not need to call `request.startAsync()` directly inside a controller returning `Mono`/`Flux`.

## 18. Timeouts, cancellation, and errors in publishers

Applications must bound how long an HTTP response stays open. In MVC:

```properties
spring.mvc.async.request-timeout=30s
```

This is the default MVC async timeout. Also align:

- HTTP client/`WebClient` **connect/read/response timeouts** when calling upstream.
- Servlet container connection/async timeouts.
- Reverse proxy or load balancer idle/read timeouts.
- Subscriber/client cancellation and publisher disposal behavior.

Example setting a timeout in a Reactor pipeline:

```java
@GetMapping("/api/upstream")
public Mono<Item> upstream() {
    return reactiveService.load()
        .timeout(Duration.ofSeconds(5))
        .onErrorMap(TimeoutException.class,
            ex -> new ResponseStatusException(
                HttpStatus.GATEWAY_TIMEOUT,
                "Upstream responded too slowly", ex));
}
```

This is a **fragment** inside `@RestController`; it needs imports for `Duration`, `TimeoutException`, `ResponseStatusException`, and `HttpStatus`. Reactor's timeout differs from MVC's async request timeout and proxy timeouts. When an upstream service fails, pick the status code matching your API contract rather than turning every timeout into 504 by reflex.

When a streaming `Flux` errors **after the HTTP response has committed**, you cannot reliably change status `200` to `500` or write a brand-new JSON error body. For SSE, you can emit an application-level **error event** if the socket is still writable; otherwise, close the stream and let the client reconnect per policy.

`doFinally` can observe completion/error/cancellation, but blocking cleanup must not run carelessly on Reactor non-blocking threads. Test resource/connection cancellation in a real HTTP environment.

## 19. Client disconnects: no reliable instant Servlet notification

According to Spring MVC async docs, the Servlet API has no universal callback guaranteed to fire immediately when a peer vanishes. While streaming, servers usually detect a client disconnect on **the next write failure** (such as an `IOException`).

For long-lived SSE, send periodic heartbeats to detect broken connections and avoid proxy idle timeouts. A heartbeat can be an SSE comment event or application-level payload ignored by the client.

Conceptual SSE example:

```text
: heartbeat

event: tick
data: 42

```

This is SSE wire format in an HTTP body, not a Java fragment. If no data is sent for a long time, a disconnected client may go undetected and continue consuming server resources.

Set limits on maximum concurrent streams, duration, client authentication, retries, and upstream subscriptions. Never implement unbounded retries without backoff or without tracking open connection counts.

## 20. Context propagation, MDC, and SecurityContext

When an MVC request crosses multiple threads (container threads, async executor threads, Reactor schedulers), `ThreadLocal` values do not automatically migrate completely. Examples include:

- `RequestContextHolder` and request attributes.
- `LocaleContextHolder`.
- Log MDC and trace/span context.
- Thread-bound security context.

Spring Framework documents using **Micrometer Context Propagation** to bridge data between `ThreadLocal` and Reactor `Context`. When the dependency is present and matching `ThreadLocalAccessor` implementations are registered, the framework can help capture and propagate context for reactive return values; do not assume accessors like request or locale are automatically registered in every project.

Do not rely on `MDC.get("traceId")` inside a callback on `Schedulers.parallel()` always matching the container thread. Test across async boundaries and Reactor schedulers. When accessing the security principal inside reactive callbacks, pass needed data safely or use stack-appropriate context propagation.

**Never store `HttpServletRequest` or mutable request-scoped data in a global singleton** to read after the initial thread finishes.

## 21. MVC @RequestBody and @RequestPart remain mostly synchronous bindings

An easily missed distinction:

- Spring MVC allows `Mono`/`Flux` as controller **return values**.
- Spring MVC does not provide a WebFlux equivalent for reactive argument types such as `@RequestBody Mono<Dto>` or `@RequestPart Flux<...>` in annotated controllers the way WebFlux does.

Example wishing to read a streaming request body reactively:

```java
@PostMapping("/api/upload")
public Mono<Void> upload(@RequestBody Flux<DataBuffer> body) {
    // This is WebFlux style, NOT a direct
    // replacement for Servlet MVC @RequestBody.
}
```

The snippet above is a **wrong-stack example** and should not be placed into the MVC demo app.

In MVC, use `HttpServletRequest.getInputStream()` or `MultipartFile.getInputStream()`/transfer for large uploads, combined with byte and resource limits. Those remain typical blocking input operations under the Servlet API. For reactive HTTP body streaming from request to response via `Flux<DataBuffer>`, **WebFlux** is the more appropriate programming model.

Therefore, **merely changing the return type to `Mono`/`Flux` does not convert request-body decoding into a reactive pipeline**.

## 22. StreamingResponseBody and ResponseBodyEmitter: when to use them?

Not every problem needs Reactor. Spring MVC provides standard async APIs:

- `DeferredResult<T>`: a single result arriving later.
- `Callable<T>`: produces a single result on an async task executor.
- `ResponseBodyEmitter`: emits multiple objects via `HttpMessageConverter`.
- `SseEmitter`: emits Server-Sent Events.
- `StreamingResponseBody`: writes raw bytes directly to `OutputStream` on a worker thread.

Large file download example:

```java
@GetMapping(
    path = "/download",
    produces = MediaType.APPLICATION_OCTET_STREAM_VALUE)
public StreamingResponseBody download() {
    return output -> {
        try (InputStream input = Files.newInputStream(
                Path.of("reports", "report.bin"))) {
            input.transferTo(output);
        }
    };
}
```

This is an **illustrative method** inside an MVC controller requiring imports for `InputStream`, `Files`, `Path`, `StreamingResponseBody`, `GetMapping`, and `MediaType`. The real file must exist with proper permissions and path validation; `InputStream.transferTo` is a blocking buffered copy, avoiding loading the whole file onto the heap.

If your data source is already a `Flux`, returning `Flux` may take less code. If your source is traditional blocking I/O and the application is MVC, `StreamingResponseBody` or `ResponseBodyEmitter` can be clearer than forcing every stream into a Reactor Publisher.

In all cases, configure an appropriate async executor, guard against slow clients, and handle committed response states.

## 23. Performance: avoid confusing thread count with request count

Suppose a `Mono<Item>` request takes 300 ms waiting on upstream HTTP while needing only a few ms of CPU. If the controller calls `.block()`, a Servlet request thread can be held for 300 ms. Returning `Mono` lets async MVC release the thread while waiting, increasing concurrency for the I/O-wait stage.

However, if many clients simultaneously request an SSE/NDJSON `Flux` with slow response writes, the async executor may need many worker threads and queues. Overall latency/throughput also depends on:

| Resource | What to observe |
|---|---|
| Servlet request threads | Busy threads, queues, rejected connections |
| MVC async executor | Active threads, queue depth, rejected tasks, write duration |
| `WebClient` connection pool | Active/pending connections, response timeouts |
| Reactor schedulers | Queues, blocked threads, saturation |
| Container output | `ServletOutputStream.write` duration, flush behavior |
| Network/proxy | RTT, buffering, idle timeouts, slow clients |
| Heap/GC | `Flux` JSON aggregation, data caches, object retention |
| Direct memory | Netty client buffers if using `WebClient` with Reactor Netty |
| Error handling | Timeouts, cancellation, disconnects, response committed |

Do not conclude “it's reactive so it saves threads” just from importing `Mono`. Measure under real load tests across single-value endpoints, JSON arrays, SSE, and slow clients. Compare against blocking MVC or non-blocking WebFlux under the same workload.

## 24. When should you use Spring WebFlux instead of MVC + Mono/Flux?

**Keep Spring MVC** when:

- The core system relies on Servlet filters, Spring MVC controllers, blocking JPA/JDBC, and synchronous libraries.
- Only a few endpoints call a reactive downstream `WebClient` and want to avoid blocking request threads while waiting.
- You have a moderate number of SSE/streaming endpoints with properly configured and load-tested executors and proxies.
- Migrating the entire stack to WebFlux costs more than any measured gain.

**Consider Spring WebFlux** when:

- The application uses predominantly non-blocking I/O from server down to database/upstream services.
- You need massive numbers of long-lived streaming connections/streams and want end-to-end non-blocking I/O.
- You need reactive types in `@RequestBody`/`@RequestPart` and request-body processing via `Flux<DataBuffer>`.
- The team has strong command of Reactor operators, backpressure, error signals, cancellation, context propagation, and blocking boundaries.

**Yet WebFlux does not rescue blocking code**: calling JDBC or blocking SDKs on the event loop also causes stalls. If most dependencies remain blocking, MVC/Servlet with appropriate async/virtual-thread configuration may be simpler. Decide via profiling and concurrency requirements, not technology buzzwords.

## 25. HTTP statuses, headers, and streaming errors

If the publisher errors **before the response commits**, the exception can flow through MVC async exception resolution such as `@ExceptionHandler` or `ResponseStatusException` and return the appropriate HTTP status.

If the publisher errors **after** bytes have already been sent to the client:

- You cannot change HTTP status/headers as you can with an uncommitted response.
- With SSE, you can emit an application-level error event if the socket is alive and clients support it.
- With NDJSON, you can emit an error record if the format contract permits; otherwise, the stream aborts mid-way and the client must treat the data as incomplete.
- When a client disconnects, `IOException`/network resets may appear at the streaming layer.

Do not emit a JSON `ProblemDetail` object in the middle of a `text/event-stream` response unless the client expects to decode it: that breaks the stream contract.

Nor is an HTTP 200 SSE response carrying an `error` event equivalent to HTTP 500; those operate at two different layers. Document the client protocol clearly: resume tokens, last event ID, reconnect delays, cancellation, and incomplete-data handling.

## 26. Common pitfalls and fixes

| Symptom | Cause | Where to investigate |
|---|---|---|
| Returns `Mono` yet app still runs Tomcat | Spring Boot still selects SERVLET due to `starter-web` | Expected MVC behavior; check `WebApplicationType` |
| JSON `Flux` does not stream item by item | Non-streaming `application/json` collects into a `List` | Use SSE/NDJSON when streaming is truly needed |
| RSS/heap spikes on large `Flux` | List aggregation, caching, buffering | Reduce payload, paginate, or use a streaming media type |
| Backpressure exists yet many worker threads are busy | Servlet response writes are blocking | Measure/bound `AsyncTaskExecutor`, inspect slow clients |
| Returns `Mono` yet request thread still blocks | Service calls synchronous I/O before creating `Mono` | Locate blocking boundary, avoid `.block()` |
| HTTP 503/timeouts under heavy traffic | Executor/queue/upstream pools saturated | Configure bounded capacity, timeouts, observability |
| `MockMvc` does not see the final response | Request is still async | Use `request().asyncStarted()` + `asyncDispatch` |
| SSE events arrive all at once | Buffering at server/proxy/client | Check flushing, proxy buffering, curl `-N` |
| SSE connection stays alive after client loses network | Servlet does not report disconnects immediately | Heartbeats, write detection, cancellation, timeouts |
| `@RequestBody Flux<DataBuffer>` does not work | WebFlux code placed in an MVC controller | Use Servlet `InputStream` or move to WebFlux |
| MDC/locale lost inside reactive callback | `ThreadLocal` does not cross async boundaries automatically | Version-appropriate context propagation |
| Spring Security principal behaves unexpectedly | Async context propagation across different threads | Inspect filters, request security context, callbacks |
| Exception after flush does not change status | HTTP response already committed | Design stream error protocol, logging/metrics |
| Having both web starters runs MVC | Boot prioritizes SERVLET by default | Manage dependencies/`web-application-type` intentionally |
| Long-lived stream fails with 500 after 30s | MVC async timeout | Tune timeout per endpoint and proxy; cap stream lifetime |

## 27. Debugging and load-testing procedure

1. **Identify the stack:** check logs for embedded Tomcat/Jetty/Undertow vs. Reactor Netty; `WebApplicationType.SERVLET` vs. `REACTIVE`.
2. **Read the controller signature:** `Mono<T>` or `Flux<T>`, with `@ResponseBody`/`@RestController`?
3. **Check media types:** `produces`, request `Accept`, response `Content-Type`; `application/json` behaves differently from streaming media types.
4. **Find blocking operations:** `.block()`, JDBC, `Thread.sleep()`, file I/O, synchronous HTTP clients.
5. **Verify async support:** `asyncSupported`, filter mappings for `ASYNC`, servlet container version.
6. **Check the executor:** `applicationTaskExecutor` bean, the `AsyncTaskExecutor` MVC actually uses, thread/queue saturation.
7. **Check timeouts:** MVC async, upstream/`WebClient`, reverse proxy, client idle.
8. **Test streaming:** use `curl -N` or a streaming HTTP client; do not only inspect the response body after completion.
9. **Observe context:** MDC, trace/span, `Locale`, Security principal across async callbacks.
10. **Test failures:** publisher error before/after commit, client disconnect, upstream timeout, executor rejection.
11. **Compare under load:** p95/p99 latency, active Servlet threads, executor threads/queues, heap, and network throughput.
12. **Verify contracts:** is List aggregation for a JSON array appropriate for data size? Do SSE/NDJSON define heartbeat/error/resume policies?

### Short checklist

- [ ] Understood `Mono` in MVC is an **async result**, not a non-blocking Servlet response write.
- [ ] Understood `Flux` + `application/json` may be collected into a `List`.
- [ ] Selected `text/event-stream` or a streaming media type when incremental emission is needed.
- [ ] Isolated blocking I/O away from Reactor non-blocking callbacks with bounded pools.
- [ ] Configured `AsyncTaskExecutor` and timeouts without unbounded queues.
- [ ] Have `MockMvc.asyncDispatch` tests plus integration tests for socket streaming.
- [ ] Have stream termination, heartbeats, cancellation, and error handling.
- [ ] Not assuming WebFlux reactive request-body binding works in MVC.
- [ ] Choosing between MVC and WebFlux using load measurements and end-to-end non-blocking readiness of the **entire pipeline**.

## 28. Summary

**Returning `Mono` or `Flux` from a Spring MVC controller is officially supported by the framework.** `ReactiveAdapterRegistry` lets Spring MVC adapt publishers to Servlet asynchronous request processing: a `Mono` behaves like `DeferredResult`; a non-streaming `Flux` can be collected into a `List`; a streaming `Flux` uses a response-emitter mechanism.

Do not miss the caveat: **response writes remain blocking at the Servlet layer** and require an `AsyncTaskExecutor` when streaming. Backpressure throttles upstream production, yet it does not eliminate thread/queue limits, proxy buffering, media-type memory aggregation, or Servlet I/O constraints.

Use MVC + `Mono`/`Flux` to integrate a few reactive services without writing `.block()`. If you require reactive request-body processing and end-to-end non-blocking I/O at high scale, evaluate Spring WebFlux as a separate architectural choice.

## 29. References

- Spring Framework 6.2 — Asynchronous Requests in Spring MVC (DeferredResult, Callable, Streaming, Reactive Types, Context, Disconnects): https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-ann-async.html
- Spring Framework — Supported MVC Controller Return Values: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/return-types.html
- Spring Framework — Synchronous and Reactive use of WebClient: https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-synchronous.html
- Spring Framework — WebFlux vs MVC: https://docs.spring.io/spring-framework/reference/web/reactive.html
- Spring Boot 3.5 — Task Execution and Scheduling: https://docs.spring.io/spring-boot/3.5/reference/features/task-execution-and-scheduling.html
- Spring Boot 3.5 — Common Application Properties (spring.mvc.async.request-timeout, spring.task.execution.pool.*): https://docs.spring.io/spring-boot/3.5/appendix/application-properties/index.html
- Spring Framework — MVC Testing Async Requests: https://docs.spring.io/spring-framework/reference/testing/spring-mvc-test-framework/async-requests.html
- Reactor — Project Reactor Reference Guide (Backpressure, Schedulers, Operators): https://projectreactor.io/docs/core/release/reference/
- MDN — Server-Sent Events/Event Stream Format: https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events/Using_server-sent_events
