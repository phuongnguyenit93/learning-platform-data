# Returning Reactive Types in Spring MVC and Response Write Limitations

> **Scope:** Spring Web MVC on the Servlet stack, Java 17+, and Spring Boot 3.x/Spring Framework 6.x; the core concepts remain foundational for Spring Framework 7.x though Boot 4 dependency configuration may differ. This article explains how MVC accepts `Mono<T>`, `Flux<T>`, `Publisher<T>`, or reactive types supported by `ReactiveAdapterRegistry`; distinguishes **single values**, **SSE/NDJSON streaming**, and **regular JSON collections**; and clarifies the most common misconception: **a reactive source does not make Spring MVC's Servlet response writes non-blocking I/O**. Includes a runnable Java 17 Spring Boot 3.x demo, `AsyncTaskExecutor` setup, cURL, MockMvc, memory bounds, and error/disconnect handling.

## 1. Problem: wanting to use reactive sources in an MVC app

A REST service uses Spring MVC yet retrieves data from Reactor `Mono`, `Flux`, a reactive repository, or `WebClient`. Common questions:

- Can a `@RestController` return `Mono<Book>` directly instead of `Book`?
- Does returning `Flux<Book>` mean sending each element immediately to the browser?
- When the response is `application/json`, does Spring buffer the entire `Flux` in memory before returning?
- If a client is slow or disconnects, to what extent does backpressure work?
- How many threads are needed to run 1,000 SSE connections?
- Between Spring MVC and WebFlux, how does writing the response differ?

**Short answer:** Spring MVC supports reactive return types. It coordinates them through Servlet asynchronous request processing; `Mono` is typically adapted like `DeferredResult`, while `Flux` chooses between **streaming** or **collection** depending on the media type. When actually writing the response, Spring MVC still performs **blocking writes on a dedicated thread/executor**, rather than switching to the WebFlux non-blocking HTTP I/O model. Without configuring the executor, buffers, timeouts, and source bounds, the app can still stall or run out of RAM.

## 2. Data flow diagram

```text
HTTP client
     |
Servlet container (Tomcat)
     |
DispatcherServlet + HandlerAdapter
     |
@GetMapping returns Mono<T> / Flux<T>
     |
ReactiveAdapterRegistry
     |
     +--> Mono<T> / single value
     |      -> DeferredResult-style async processing
     |      -> single value / ResponseEntity / JSON / error
     |
     +--> Flux<T> + application/json
     |      -> collect values into List-like result
     |      -> Jackson serializes JSON array after completion
     |
     +--> Flux<T> + text/event-stream or application/x-ndjson
            -> emitter-style streaming
            -> encode and write each part/chunk
            -> blocking ServletResponse write via AsyncTaskExecutor
     |
HTTP response / Servlet output stream
```

**Key takeaway:** never equate **Reactive Streams backpressure between publisher/subscriber** with **non-blocking socket writes**. Spring MVC can throttle demand from the publisher to match the write pace, yet each write to the Servlet response can still block a worker thread. <https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-ann-async.html>

## 3. Reactive Streams and Reactor types

### 3.1. Mono and Flux

| Type | Cardinality | Example meaning |
| --- | --- | --- |
| `Mono<T>` | 0 or 1 value, or error | Load details for one account |
| `Flux<T>` | 0 to N values, finite or infinite | Lists, changes over time, events |
| `Publisher<T>` | Reactive Streams interface | Source abstraction |
| `CompletionStage<T>` | One asynchronous JDK result | Future-like result |
| `Single<T>` (RxJava) | One value | Another reactive adapter when the library is present |

`Mono.just(value)` does not make I/O non-blocking on its own. `Mono.fromCallable(() -> blockingRepository.find(...))` still runs the blocking code on the subscribing thread unless shifted to an appropriate scheduler. Reactor provides `subscribeOn(Schedulers.boundedElastic())` for controlled blocking sources, though moving threads only avoids blocking the event loop; it does not make JDBC or Servlet I/O non-blocking.

### 3.2. ReactiveAdapterRegistry

Spring's `org.springframework.core.ReactiveAdapterRegistry` bridges reactive libraries with MVC infrastructure. It recognizes single-value/multi-value semantics and adapts them into data flows. Reactor is the common choice; RxJava can also be supported if the corresponding library and adapter are present.

Do not try to write:

```java
// Anti-pattern: subscribing in controller and returning null.
@GetMapping("/bad")
public Object bad() {
    service.getBook().subscribe(book -> System.out.println(book));
    return null;
}
```

This illustrative snippet detaches the subscription from the response lifecycle; results may arrive after the handler has ended, and errors/cancellation are hard to tie to the HTTP response. **Return the publisher directly** to MVC:

```java
@GetMapping("/good")
public Mono<BookView> good() {
    return service.getBook();
}
```

This is a snippet; service/DTO definitions are needed separately. When the framework manages the subscription, it can integrate timeouts, exception dispatching, message conversion, and subscription cancellation in the appropriate cases.

## 4. Single value: Mono<T> acts as an asynchronous result

Example:

```java
@RestController
class BookController {
    @GetMapping("/api/book")
    Mono<BookView> book() {
        return Mono.just(new BookView(1L, "Spring MVC"));
    }
}
```

This is a fragment requiring `BookView` and imports. `@RestController` sends the value to the HTTP response body; `Mono<BookView>` is not serialized as JSON describing a Mono—MVC **waits for the actual value** emitted by the publisher.

At the infrastructure level, a single-value reactive return is adapted similarly to `DeferredResult<T>`:

1. The controller returns the publisher; Spring MVC registers asynchronous handling.
2. The Servlet request switches to async mode; the initial request thread can return to the pool.
3. Mono emits `onNext(book)` then `onComplete`, or `onError`.
4. Spring MVC resumes processing the result via async dispatch and writes the body using `HttpMessageConverter`.
5. Once the response finishes, the async lifecycle ends.

**Note:** `Mono.just(...)` can emit the value immediately upon subscription; an asynchronous return type does not guarantee work actually runs on another thread or that operations inside are non-blocking. To demonstrate a delayed value, use `Mono.delay(...)` or a real async service.

### 4.1. Mono.empty()

`Mono.empty()` emits no `T`. The default HTTP status can depend on method signature, Spring MVC return handlers, and application-chosen annotations/statuses. Never assume `Mono.empty()` is always HTTP 404. If the business contract means "not found", map it explicitly to an error or `ResponseEntity.notFound()`.

```java
@GetMapping("/api/books/{id}")
Mono<ResponseEntity<BookView>> find(@PathVariable long id) {
    return repository.findById(id)
            .map(book -> ResponseEntity.ok(toView(book)))
            .defaultIfEmpty(ResponseEntity.notFound().build());
}
```

This snippet requires a reactive repository/mapper; the goal is showing the HTTP status chosen after the result is known.

### 4.2. When are Status/Headers decided?

Two different structures:

```java
// Status and headers are determined immediately.
ResponseEntity<Mono<BookView>> immediateHeaders() {
    return ResponseEntity.accepted()
            .header("X-Demo", "value")
            .body(Mono.just(new BookView(1L, "Example")));
}
```

```java
// Entire ResponseEntity is decided asynchronously.
Mono<ResponseEntity<BookView>> deferredHeaders() {
    return Mono.just(
            ResponseEntity.ok(new BookView(1L, "Example")));
}
```

The two methods above are standalone snippets without `@GetMapping`. With `ResponseEntity<Mono<T>>`, the server knows the status/headers early while the body arrives later. With `Mono<ResponseEntity<T>>`, status, headers, and body are all decided when the Mono completes. In practice, if you need to return 404/409 depending on asynchronous data, `Mono<ResponseEntity<T>>` expresses it better because the status is not locked when creating the controller return value.

## 5. Multiple values: Flux<T> does NOT always stream

The exact same `Flux<BookView>` can exhibit two different behaviors depending on the **response media type**.

### 5.1. Flux + application/json: collect then serialize a JSON array

```java
@GetMapping(path = "/api/books",
            produces = MediaType.APPLICATION_JSON_VALUE)
Flux<BookView> books() {
    return Flux.just(
            new BookView(1, "A"),
            new BookView(2, "B"));
}
```

Spring MVC adapts a multi-value reactive type with a non-streaming media type such as `application/json` into a result similar to `DeferredResult<List<?>>`. Once the publisher completes, MVC serializes the list into a single JSON array:

```json
[{"id":1,"title":"A"},{"id":2,"title":"B"}]
```

**It does not emit each object as items arrive** in the SSE/NDJSON sense. With very large sources, `collectList`-style buffering can grow memory proportionally to item count. With infinite sources, a JSON array response **has no completion point**; the client may wait forever or time out while memory keeps growing.

**Common mistake:** returning an infinite `Flux.interval(...)` with `produces="application/json"` and expecting the browser to see continuous events. Pick a streaming media type or bound/aggregate data appropriately.

### 5.2. Flux + text/event-stream: SSE

```java
@GetMapping(path = "/api/events",
            produces = MediaType.TEXT_EVENT_STREAM_VALUE)
Flux<ServerSentEvent<String>> events() {
    return Flux.just(
            ServerSentEvent.builder("first")
                    .id("1").event("tick").build(),
            ServerSentEvent.builder("second")
                    .id("2").event("tick").build());
}
```

This is a snippet requiring Reactor and `org.springframework.http.codec.ServerSentEvent`. SSE has text framing like:

```text
id:1
event:tick
data:first

id:2
event:tick
data:second

```

Field order/formatting and line endings depend on the serializer; the sample shows event semantics rather than byte-for-byte output across every Spring version.

With SSE, Spring MVC adapts the reactive stream into an emitter-style response. As items arrive, MVC can serialize and flush so the client receives them incrementally, provided reverse proxies/networks do not buffer. Use a client like `curl -N` to avoid stdout buffering when testing.

### 5.3. Flux + application/x-ndjson: each element is one JSON line

```java
@GetMapping(path = "/api/records",
            produces = "application/x-ndjson")
Flux<BookView> records() {
    return Flux.just(
            new BookView(1, "A"),
            new BookView(2, "B"));
}
```

**Format-illustrating snippet:** for output to actually be NDJSON, you need `HttpMessageConverter`/Jackson configuration supporting that media type on the version in use. When streaming is selected, an NDJSON response typically looks like:

```text
{"id":1,"title":"A"}
{"id":2,"title":"B"}
```

Each line is a complete JSON value, unlike a traditional JSON array. For a specific Spring/container/converter version, test actual serialization and flushing rather than trusting `produces` alone. Some setups require registering additional media types on converters.

### 5.4. Choosing the output shape

| Return type | Media type / mapping | Common behavior in MVC | Best suited for |
| --- | --- | --- | --- |
| `Mono<Book>` | `application/json` | One JSON body after Mono yields result | Looking up one item |
| `Flux<Book>` | `application/json` | Collects all into a List/JSON array | **Finite, bounded** lists |
| `Flux<Book>` | `application/x-ndjson` | Individual JSON objects per line | Streaming multiple records |
| `Flux<ServerSentEvent<T>>` | `text/event-stream` | Emits SSE events incrementally | Notifications/telemetry |
| `Flux<T>` | Other streaming type with compatible converter | Depends on converter & media config | Specialized streaming |
| `ResponseEntity<Flux<T>>` | Streaming type | Status/headers fixed upfront, reactive body | Streams with static metadata |
| `Mono<ResponseEntity<T>>` | Non-streaming | Status/headers/body decided asynchronously | HTTP status depends on result |

**Remember:** `Flux<T>` is a reactive data stream; the **media type** decides whether MVC handles it as incremental streaming or collects it before rendering.

## 6. Backpressure in MVC and the response-write bottleneck

Reactive Streams let downstream request items from upstream via `Subscription.request(n)`. In the Spring MVC streaming bridge:

```text
Reactor Publisher (with backpressure)
           |
           v
ReactiveAdapter / Subscriber
           |
           v
Spring MVC emitter/queue
           |
           v
AsyncTaskExecutor worker
           |
           v
HttpMessageConverter
           |
           v
ServletOutputStream.write(...)     <-- BLOCKING when client/network is slow
           |
HTTP client
```

Spring MVC supports backpressure when streaming reactive values so it does not blindly pull millions of items while the network has not caught up. Still, **blocking writes do not disappear**: a worker thread can get stuck waiting on the socket/container/network. With many slow clients or long-lived SSE connections, required worker counts and buffering can become bottlenecks.

### 6.1. Backpressure does not automatically make every Publisher safe

For instance, `Flux.interval(Duration.ofMillis(5))` emits events on a clock. If downstream cannot keep up, some sources signal overflow/cancellation when demand is absent; hot sources like topics/message brokers may have different drop/buffer policies. Specify:

- `limitRate` or demand policies where appropriate;
- `onBackpressureBuffer(maxSize, overflowStrategy)` with **explicit bounds**, never unbounded buffering;
- `onBackpressureDrop`/`onBackpressureLatest` when **business rules tolerate losing events**;
- timeouts, cancellation, and total event caps;
- client reconnection/resume semantics with SSE event IDs if required.

**Never introduce data-dropping strategies into payment or audit flows** just to save RAM; those flows require different delivery semantics.

### 6.2. Reactive does not mean non-blocking when calling services

```java
// Anti-pattern: blocking JDBC call running on the subscription-emitting thread.
return Mono.fromCallable(() -> jdbcRepository.findById(id));
```

If the source runs on an event loop, it can block the event loop. For temporary blocking code:

```java
return Mono.fromCallable(() -> jdbcRepository.findById(id))
        .subscribeOn(Schedulers.boundedElastic());
```

This snippet shifts work to a relatively bounded scheduler; **it does not turn JDBC into an async driver**. Under high load, you may need a reactive driver, connection pool tuning, or keeping a standard MVC/blocking service. Choosing MVC vs. WebFlux must be based on the entire real pipeline, not just return types.

## 7. Why Spring MVC does not become WebFlux

| Criterion | Spring MVC + Mono/Flux return | Spring WebFlux |
| --- | --- | --- |
| Foundation | Servlet API + DispatcherServlet | Reactive stack + WebHandler |
| Controller return | Mono/Flux supported via adapters | Native reactive pipeline |
| Request body parsing | MVC `HttpMessageConverter` and Servlet request | Reactive `HttpMessageReader` / `Flux<DataBuffer>` |
| Streaming writes | **Blocking Servlet output writes** on async executor | Non-blocking I/O per supported runtime |
| Backpressure | Present at the reactive publisher bridge | Across multiple stages of the reactive pipeline |
| Servlet thread | Returned when async request starts; another thread may write | Event-loop/non-blocking approach |
| MVC form binding | `@ModelAttribute`/Servlet binding | Different reactive-aware APIs |
| Streaming CPU/thread cost | Thread held during blocking write | Different resource model, still needs resource bounds |
| Switching from MVC to WebFlux | Does not happen just by returning Flux | Requires selecting the Spring reactive web runtime/stack |

Spring MVC does not support `Mono<@RequestBody T>` as a streamed reactive handler parameter at the framework contract level, nor does it have explicit reactive model-attribute support equivalent to WebFlux. **Returning reactive types** does not make the whole request path non-blocking.

### 7.1. Can you add Reactor while still running MVC?

Yes. With Spring Boot 3.x, the primary server dependency for MVC is `spring-boot-starter-web`; add `io.projectreactor:reactor-core` if you want Mono/Flux. You do **not** need to add `spring-boot-starter-webflux` just to return Reactor types in MVC. If both MVC and WebFlux starters are present, Spring Boot typically prefers Servlet MVC auto-configuration, but avoid adding unnecessary stacks to reduce confusion.

If an actual `WebClient` is needed, `spring-webflux` and the corresponding Reactor Netty/HTTP client libraries can be added as client dependencies; having WebClient does not force server controllers to switch to WebFlux.

### 7.2. When should you switch to WebFlux?

Consider WebFlux when:
- You have very large numbers of slow/concurrent streaming connections where blocking write threads is a genuine bottleneck.
- The backend/call chain uses non-blocking clients/drivers, avoiding blocking at every step.
- The team can design cancellation, backpressure, error handling, context propagation, and end-to-end reactive testing.

Stay on MVC when:
- The application primarily uses blocking JDBC/JPA/Servlet integrations.
- Async needs are limited to a few single results or moderate-scale SSE.
- You want to leverage the existing MVC ecosystem, simpler debugging, and properly sized executors/capacity.

Do not switch frameworks just because returning `Flux` looks "more modern"; measure actual load, memory, threads, and latency.

## 8. Configuring AsyncTaskExecutor for response writes

Spring MVC documentation emphasizes: when streaming reactively, the framework performs blocking writes using a dedicated `AsyncTaskExecutor` to avoid blocking upstream sources. The default executor for async support is **not suitable for production load**; configure bounded sizing and plan capacity.

Example `WebMvcConfigurer#configureAsyncSupport`:

```java
@Configuration
class MvcAsyncConfig implements WebMvcConfigurer {

    @Bean
    ThreadPoolTaskExecutor mvcAsyncExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setThreadNamePrefix("mvc-async-");
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(64);
        executor.initialize();
        return executor;
    }

    @Override
    public void configureAsyncSupport(AsyncSupportConfigurer configurer) {
        configurer.setTaskExecutor(mvcAsyncExecutor());
        configurer.setDefaultTimeout(15_000L);
    }
}
```

This is a class snippet requiring imports for `@Configuration`, `@Bean`, `WebMvcConfigurer`, `AsyncSupportConfigurer`, and `ThreadPoolTaskExecutor`. The complete example in section 9 has full imports and methods.

**Important:**
- `@Configuration` bean methods are proxied by Spring by default so the same bean is reused when calling `mvcAsyncExecutor()` from the config instance; if `proxyBeanMethods=false` is set, inject the instance instead of calling the method directly.
- `corePoolSize/maxPoolSize/queueCapacity` are example figures, not a universal standard. Under overload, tasks can be rejected; add metrics, capacity planning, fallbacks, and error rules before response commit.
- `setDefaultTimeout(15_000L)` sets a default async request timeout; for SSE lasting longer than 15 seconds, configure an appropriate timeout. Do not mechanically copy demo timeouts into long-lived production streams.
- A thread blocked writing to a slow client can be held for a long time. An 8-thread executor pool does not mean the server handles 10,000 SSE streams infinitely without latency/queue issues.
- If using Spring Security/Micrometer context, also check context propagation across async threads.

### 8.1. Async Servlet dispatch/filter config

Spring MVC async relies on Servlet 3.0+ async capability. Filters must apply proper dispatcher types and `asyncSupported`. In typical Boot apps, the embedded Servlet container/DispatcherServlet is configured appropriately; in traditional deployments/custom filter registrations, verify explicitly:

```xml
<!-- web.xml snippet for traditional Servlet applications -->
<servlet>
    <servlet-name>dispatcher</servlet-name>
    <servlet-class>
        org.springframework.web.servlet.DispatcherServlet
    </servlet-class>
    <async-supported>true</async-supported>
</servlet>
```

For filters that must participate in async dispatches, set `<async-supported>true</async-supported>` and map `<dispatcher>ASYNC</dispatcher>` as needed. If a non-async filter sits in the chain, `request.startAsync()` may fail. An async dispatch is not a fresh client request; `HandlerInterceptor` callbacks also have a special lifecycle.

## 9. Complete, runnable example: Spring Boot 3.x / Java 17

The example provides three endpoints:
- `GET /api/mono`: returns a delayed single JSON object via `Mono<Message>`.
- `GET /api/array`: returns `Flux<Message>` with `application/json`, producing one JSON array once the publisher finishes.
- `GET /api/events`: `Flux<ServerSentEvent<String>>` + `text/event-stream`, emitting three SSE events over time.

The demo uses only finite data, with no database or authentication. The executor is bounded; the timeout is sufficient for 3 events. The WebFlux starter is omitted so the server remains MVC.

### 9.1. Maven dependencies

Create a Maven Spring Boot **3.5.x** project from [Spring Initializr](https://start.spring.io/), Java 17, select **Spring Web**, and add Reactor Core managed by the Spring Boot BOM:

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

This is a `pom.xml` fragment already using the Spring Boot parent/BOM; do not hardcode an arbitrary Reactor version conflicting with the BOM. `spring-boot-starter-web` includes Spring MVC, Jackson, and embedded Tomcat by default. Reactor Core provides `Mono`, `Flux`, and schedulers.

### 9.2. Source structure

```text
src/main/
└── java/
    └── com/example/demo/
        └── DemoApplication.java
```

Place all Java source below in the single file `src/main/java/com/example/demo/DemoApplication.java`.

### 9.3. Complete Java source

```java
package com.example.demo;

import java.time.Duration;
import java.util.List;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.config.annotation.AsyncSupportConfigurer;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}

record Message(int id, String text) {
}

@Configuration
class MvcAsyncConfiguration implements WebMvcConfigurer {

    @Bean
    public ThreadPoolTaskExecutor mvcAsyncExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setThreadNamePrefix("mvc-write-");
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(64);
        executor.initialize();
        return executor;
    }

    @Override
    public void configureAsyncSupport(
            AsyncSupportConfigurer configurer) {

        configurer.setTaskExecutor(mvcAsyncExecutor());
        configurer.setDefaultTimeout(15_000L);
    }
}

@RestController
@RequestMapping("/api")
class ReactiveReturnController {

    @GetMapping(
            path = "/mono",
            produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<Message> single() {
        return Mono.delay(Duration.ofMillis(100))
                .map(tick -> new Message(1, "ready"));
    }

    @GetMapping(
            path = "/array",
            produces = MediaType.APPLICATION_JSON_VALUE)
    public Flux<Message> array() {
        return Flux.fromIterable(List.of(
                new Message(1, "alpha"),
                new Message(2, "beta"),
                new Message(3, "gamma")))
                .delayElements(Duration.ofMillis(100));
    }

    @GetMapping(
            path = "/events",
            produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public Flux<ServerSentEvent<String>> events() {
        return Flux.interval(Duration.ofMillis(200))
                .take(3)
                .map(i -> ServerSentEvent.<String>builder()
                        .id(Long.toString(i))
                        .event("tick")
                        .data("event-" + i)
                        .build());
    }
}
```

### 9.4. Why is this example MVC and not WebFlux?

- `spring-boot-starter-web` activates Servlet MVC and embedded Tomcat; there is no WebFlux server starter.
- Reactor `Flux/Mono` are simply return value types adapted by MVC.
- `MvcAsyncConfiguration` registers `AsyncTaskExecutor` for Servlet async and writes.
- `ServerSentEvent<String>` lets MVC format SSE; the class lives in `org.springframework.http.codec` provided by Spring Web.
- `Mono.delay` and `Flux.interval` simulate async publishers without blocking the handler thread via `Thread.sleep()`.
- `/array` has three finite items, so collecting into a JSON array is safe in the demo.
- `/events` has `take(3)` so it terminates; production long-lived SSE needs appropriate timeouts, heartbeats, reconnection, and limits.
- There are no manual `.block()` or `.subscribe()` calls in the controller; MVC manages subscriptions and the response lifecycle.

### 9.5. Running

```bash
# Linux/macOS
./mvnw spring-boot:run

# Windows PowerShell / Command Prompt
mvnw.cmd spring-boot:run
```

If no custom port is configured, the API runs at `http://localhost:8080`.

### 9.6. Mono result

```bash
curl -i 'http://localhost:8080/api/mono'
```

Expected body:

```json
{"id":1,"text":"ready"}
```

HTTP status `200 OK`, JSON content type. The value is emitted by Mono after a short delay, though actual latency depends on the scheduler/server. Do not treat 100 ms as an SLA.

### 9.7. Flux JSON array result

```bash
curl -i 'http://localhost:8080/api/array'
```

Body after all elements are collected:

```json
[
  {"id":1,"text":"alpha"},
  {"id":2,"text":"beta"},
  {"id":3,"text":"gamma"}
]
```

Actual JSON is usually on a single line without the whitespace above. What matters is **one complete JSON array**, not three separate responses. Because MVC collects Flux for `application/json`, clients normally do not receive items during the first 100 ms.

### 9.8. SSE result

```bash
curl -N -i \
  -H 'Accept: text/event-stream' \
  'http://localhost:8080/api/events'
```

One response with 3 events, with fields equivalent to:

```text
id:0
event:tick
data:event-0

id:1
event:tick
data:event-1

id:2
event:tick
data:event-2

```

Normally they are emitted over time without waiting for all 3. `curl -N` disables curl's output buffering; if Nginx/CDN or compression buffering sits in between, events may arrive in batches rather than individually. To test real streaming, measure arrival timestamps of each event on the client rather than just inspecting the final body.

### 9.9. Windows PowerShell

PowerShell may alias `curl`; use `curl.exe`:

```powershell
curl.exe -i "http://localhost:8080/api/mono"
curl.exe -i "http://localhost:8080/api/array"
curl.exe -N -i -H "Accept: text/event-stream" "http://localhost:8080/api/events"
```

### 9.10. Do not keep SSE connections open forever with the demo

The demo's `take(3)` ends quickly to produce verifiable output. If changed to an unbounded `Flux.interval(...)`:

- the demo's 15-second `async timeout` may terminate the request;
- reverse proxies/ingress/load balancers have their own idle timeouts;
- each slow writer can occupy an async executor thread;
- browser EventSource typically auto-reconnects when the connection closes;
- event IDs, resume logic, replay bounds, and per-client resource limits must be designed.

Do not replace `take(3)` with unbounded `retry()` to "auto-fix" all errors: it can create infinite loops, duplicate events, or overload the source.

## 10. Async testing with MockMvc

For Spring Boot **3.5.x**, add the test dependency:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
```

Place in `src/test/java/com/example/demo/ReactiveMvcTest.java`:

```java
package com.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.asyncDispatch;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.request;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ReactiveMvcTest {

    @Autowired
    MockMvc mvc;

    @Test
    void monoReturnsJsonAfterAsyncDispatch() throws Exception {
        MvcResult pending = mvc.perform(get("/api/mono"))
                .andExpect(request().asyncStarted())
                .andReturn();

        mvc.perform(asyncDispatch(pending))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value(1))
                .andExpect(jsonPath("$.text").value("ready"));
    }

    @Test
    void fluxWithNormalJsonIsCollectedAsArray() throws Exception {
        MvcResult pending = mvc.perform(get("/api/array"))
                .andExpect(request().asyncStarted())
                .andReturn();

        mvc.perform(asyncDispatch(pending))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$[0].text").value("alpha"))
                .andExpect(jsonPath("$[2].text").value("gamma"));
    }
}
```

**Test explanation:**
- Reactive return types are processed via Spring MVC async infrastructure.
- With MockMvc, assert `request().asyncStarted()` and call `asyncDispatch(...)` to receive the complete response in tests; asserting directly on the initial request can fail because the result is not yet ready.
- The JSON array test observes Flux being collected before serialization.
- SSE requires dedicated checks for media type/event framing and streaming timing in a real servlet/container environment; a single final MockMvc response **does not prove network streaming**.

Run:

```bash
# macOS / Linux
./mvnw test

# Windows
mvnw.cmd test
```

Tests using `Mono.delay`/`Flux.delayElements` rely on real schedulers; if CI is overly slow or times out, raise test bounds with a clear reason or use virtual schedulers in Reactor unit tests rather than abusing `Thread.sleep(...)` in tests.

## 11. Streaming errors: once committed, you cannot go back and change HTTP status

With a single-value Mono, if an error happens **before** MVC writes headers/body, `@ExceptionHandler` or `@RestControllerAdvice` can produce a 4xx/5xx response. For example:

```java
@GetMapping("/api/error")
Mono<Message> failEarly() {
    return Mono.error(new IllegalStateException("upstream unavailable"));
}
```

This is a controller snippet requiring an error policy. If the error is handled before the response commits, Spring MVC can dispatch the error through exception resolvers.

**With streaming Flux, however**, the server may already have sent initial events:

```text
event:tick
data:first

event:tick
data:second

... publisher errors ...
```

At that point HTTP headers/status may already be committed. The server **cannot guarantee** changing status 200 to 500, changing Content-Type, or replacing the body with standard error JSON. Behavior may be closing the connection, cancelling the stream, logging the exception, or signaling an error via an **event/application protocol** if the response is still writable and the design permits it.

### 11.1. Error reporting protocol inside the stream

With SSE, you can define a dedicated event:

```text
event:app-error
data:{"code":"UPSTREAM_LOST","message":"Retry later"}

```

This is an **application protocol** inside the SSE body, not switching an already-sent HTTP status to 500. If the client needs reliable error awareness, it must understand the `app-error` event and have a retry/backoff strategy. Never put stack traces, tokens, or system internals into error events.

### 11.2. When the response is not yet committed

With `Mono<ResponseEntity<T>>`, response metadata is decided along with the async result; therefore selecting status from data is easier than with `ResponseEntity<Mono<T>>`. With a streaming `Flux`, status is usually fixed before all items arrive. Validate/authenticate before starting the stream and verify source availability/permissions appropriately to reduce late failures.

### 11.3. Client disconnect

If a client closes the tab/disconnects, the writer can throw `IOException` or a container-specific exception; publisher subscription/cancellation must be managed so tasks/connections are not retained after the response dies. Reactor provides `doOnCancel`/`doFinally` to observe cleanup, for example:

```java
Flux<Long> events = Flux.interval(Duration.ofSeconds(1))
        .doFinally(signal -> {
            // Clean up subscription-scoped resources if any.
            // Do not log raw tokens/sessions/cookies.
        });
```

This snippet does not replace a full cleanup policy if upstream is a hot stream/shared subscription or holds a database cursor. Test disconnects over a real network.

### 11.4. Timeouts and partially written responses

Servlet async request timeouts, gateway read/write timeouts, and upstream publisher timeouts **are different**. When a timeout occurs after bytes have streamed, error handlers usually can no longer change status/body. For infinite Fluxes, define policies for long-lived connections, heartbeats, idle timeouts, maximum duration, retries, and quotas instead of trusting a single default timeout.

## 12. Threading, context propagation, and security

### 12.1. ThreadLocal does not cross every async boundary automatically

In synchronous Servlet MVC, `RequestContextHolder`, MDC, and certain security contexts can be bound to the request thread. When a reactive pipeline switches to a scheduler or Servlet async write thread, **do not assume** ThreadLocals remain intact.

Spring integrates Micrometer Context Propagation when the corresponding library is present and `ThreadLocalAccessor`s are registered; accessors like Locale/Request attributes may require deliberate registration. Reactive `Context` and ThreadLocal are two separate mechanisms.

**Do not do:**

```java
return Mono.delay(Duration.ofMillis(50))
        .map(tick -> SecurityContextHolder.getContext()
                .getAuthentication()
                .getName());
```

Without proper context propagation, you may see null or an unintended security context. For security, pass authenticated IDs/tenants through controlled service APIs or use standard context propagation, never storing whole secret tokens in global static state.

### 12.2. Authorization must happen before streaming

- Authenticate the request via the Spring Security filter chain.
- Verify the user is authorized to subscribe to the specific channel/resource.
- When streaming multi-tenant data, every event must match proper permissions or the stream must be created from an already authorized scope.
- If permissions are revoked during a long-lived connection, decide how to refresh permissions/close the stream; initial auth does not protect forever by default.
- Never create a global `Flux.share()` broadcasting every tenant's data and filter late per request.
- For cross-origin SSE, CORS allowlists and cookie/security/session policies still apply. SSE does not automatically protect other mutating endpoints from CSRF.

### 12.3. Do not block the Reactor event loop

If using WebClient/Reactor Netty inside an MVC controller, avoid calling `.block()` on the Reactor event loop or running business chains containing `Thread.sleep()` in operators executing on event-loop schedulers. MVC blocking response writes are moved to the async executor, yet blocking upstream code you write **can still stall upstream schedulers**.

## 13. Memory, latency, and slow clients

### 13.1. JSON Flux usually buffers a list

A Publisher emitting 100,000 records with `application/json` is typically collected into a `List<?>` before Jackson serializes it. Memory includes:
- Java objects in the collection;
- deserialized rows if the source repository caches them;
- JSON serialization buffers;
- servlet response/container output buffers;
- concurrency across other requests.

For large volumes, use pagination/limits or an appropriate streaming media type. Streaming NDJSON reduces holding the whole collection at once, though it is not zero-memory: each record is still converted, writers/encoders still have buffers, and slow clients can hold tasks/threads.

### 13.2. High-frequency Flux.interval

`Flux.interval(Duration.ofMillis(1))` can emit faster than clients read. Without a proper backpressure policy, overflow errors/drops/growing buffers can occur. Lower emission rates, batch/dedupe, bound queues, enforce deadlines, and consider sampling. SSE suits lightweight notifications; it is unsuitable for transferring images/video or multi-GiB files just because streaming is supported.

### 13.3. Executor saturation

If each blocking write holds a thread for a long duration, a small pool can fill up. With the demo's `core=4 max=8 queue=64` pool:
- At most 8 threads are managed by the executor as configured.
- The queue is bounded and requests/tasks can be rejected under overload.
- A huge queue usually delays responses and increases tail latency rather than increasing real throughput.

Never claim "8 threads are enough for 8, 80, or 800 SSE users" without measuring; thread occupancy depends on network speed, flushing, container behavior, streaming cadence, and framework write scheduling. Load-test with real slow consumers.

### 13.4. Proxy buffering and headers

An SSE app running directly on localhost shows events every 200 ms, yet behind a reverse proxy it may buffer until full. Depending on infrastructure:
- disable buffering specifically on authenticated SSE routes;
- configure appropriate idle/read timeouts;
- send heartbeats when needed and useful;
- test `curl -N` through public URLs, not just localhost;
- verify CDN/load balancers support streaming.

Do not blindly recommend setting `X-Accel-Buffering: no` in every environment as a universal HTTP standard; it is a directive for certain proxies like Nginx and still depends on upstream configuration. Consider it when the corresponding topology is present.

## 14. Choosing tools by requirement

| Requirement | Suitable MVC approach | Caveat |
| --- | --- | --- |
| Single result ready after a few hundred ms | `Mono<T>`, `CompletableFuture<T>`, `DeferredResult<T>` | Do not block upstream schedulers |
| Status depends on async result | `Mono<ResponseEntity<T>>` | Handle errors before commit |
| Static status/headers, body arrives later | `ResponseEntity<Mono<T>>` | Do not expect to change status when body errors |
| Small, finite JSON collection | `Flux<T>` + `application/json` | Buffers entire collection |
| Continuous one-way notifications | `Flux<ServerSentEvent<T>>` + SSE, or `SseEmitter` | Timeouts, connections, worker threads |
| Incremental stream of many JSON records | `Flux<T>` + NDJSON converter | Media type, flushing, interoperability |
| File/binary stream downloads | `StreamingResponseBody`/`Resource` | Blocking writes, bandwidth, post-commit errors |
| End-to-end non-blocking HTTP writes | Spring WebFlux | Requires choosing the proper reactive server stack |
| Blocking JDBC/JPA business logic | MVC or careful boundedElastic bridge | Reactor types do not make JDBC non-blocking |

Do not pick reactive return types just to dodge an important thread pool: identify **whether the bottleneck is request workers, upstream clients, DB, or response writers**, then pick the async/web framework matching your needs.

## 15. Common errors and fixes

| Symptom | Possible cause | Fix |
| --- | --- | --- |
| `Mono<T>` serialized as a wrapper object | MVC missing adapter/dependency or method not returning body | Check Reactor classpath, `@RestController`, converters |
| JSON Flux does not arrive item-by-item immediately | `application/json` collects into a List | Use SSE/NDJSON when streaming is needed |
| Infinite Flux hangs request, grows RAM | Non-streaming collection never finishes | Switch to streaming media, limits/timeouts |
| SSE works locally yet browser gets everything at once | Proxy/client output buffering | Test `curl -N`, inspect ingress |
| SSE drops after 15 seconds | Demo async timeout or proxy timeout | Configure matching timeouts/heartbeats |
| High CPU/threads despite returning Flux | MVC writes are still blocking | Bounded AsyncTaskExecutor, measure slow clients/WebFlux |
| `Async support must be enabled` | Servlet/filter registration lacks asyncSupported | Fix Servlet/filter config & dispatcher types |
| Manual `subscribe()` yields empty response | Subscription runs outside MVC lifecycle | Return Mono/Flux directly |
| `.block()` kills throughput | Blocking upstream/event loop | Use non-blocking sources or boundedElastic |
| Timeout does not produce standard JSON error | SSE response already committed | Custom event protocol/close/cancel/reconnect |
| Error handler fails to change status | Headers/body already sent | Handle errors before streaming when possible |
| MDC/SecurityContext lost | Async thread boundaries | Context propagation or explicit context |
| Backpressure overflow | Hot producer faster than slow subscriber | Intentional bounded buffer/drop policy |
| MockMvc test returns empty body | Forgot `asyncDispatch` | Assert asyncStarted + asyncDispatch |
| SSE receives wrong tenant data | Subscription lacks scoped authorization | Authorize every channel/data source |
| Flux/Mono returned without Reactor | Missing `reactor-core` dependency | Add BOM-managed version |
| 5xx when executor is overloaded | Bounded executor/queue saturated | Rate limit, shed load, scale capacity with data |

## 16. Production checklist

1. Server is genuinely using the **Spring MVC Servlet stack**, not confused with WebFlux merely from adding Reactor Core.
2. Return types match semantics: 0..1 `Mono` or 0..N `Flux`.
3. Endpoints define explicit media types: JSON array vs. SSE/NDJSON streaming.
4. Publishers are **finite** when output is non-streaming; pagination, timeouts, and caps exist.
5. Async Servlet support, filter dispatch types, and MVC `AsyncTaskExecutor` are configured/tested.
6. Async request counts, executor queue/active threads, slow clients, and time-to-first-byte are measured.
7. Policies exist when producers outpace consumers, with business-approved buffer/drop strategies.
8. HTTP response status/headers are decided before writing; post-commit errors use stream protocols/cancellation.
9. Long-lived connections have timeouts, heartbeats, reconnection IDs, and quotas.
10. When clients disconnect, upstream subscriptions and resources are cleaned up.
11. Security/auth/tenant scoping, CSRF/CORS, and permission revocations are handled properly.
12. ThreadLocal/MDC/locale/request context is used only via reliable propagation.
13. Integration tests through a reverse proxy confirm real streaming/flushing, not just MockMvc final bodies.
14. For Boot 4/Spring 7, check starter/test package changes before copying Boot 3 code.

## 17. Self-check questions

**Q1.** Does returning `Mono<BookView>` in an MVC `@RestController` require running a WebFlux server?

**Answer:** No. Through `ReactiveAdapterRegistry`, MVC adapts reactive return types to Servlet async processing. Only a compatible Reactor library is required.

**Q2.** Does `Flux<BookView>` with `produces="application/json"` send each object immediately?

**Answer:** Not by default; MVC collects multi-value streams into a List and serializes a single JSON array.

**Q3.** To have the browser receive incremental notifications, which media type should be used?

**Answer:** `text/event-stream` with `Flux<ServerSentEvent<T>>` or `SseEmitter`; watch out for proxy buffering and timeouts.

**Q4.** Why must you still configure `AsyncTaskExecutor` even when the source is a non-blocking Flux?

**Answer:** Because Servlet MVC still writes responses using **blocking writes** on a worker thread; you should not block the upstream Reactor event loop.

**Q5.** How does `Mono<ResponseEntity<BookView>>` differ from `ResponseEntity<Mono<BookView>>`?

**Answer:** The first decides status/headers/body asynchronously; the second fixes status/headers immediately while only the body emits later.

**Q6.** Once SSE has emitted the first event, can you switch status 200 to 500 and return ProblemDetail JSON?

**Answer:** Not guaranteed because the response may already be committed. Design dedicated error events/connection close and retry policies.

**Q7.** Does continuous `Flux.interval(1ms)` automatically prevent out-of-memory errors with slow clients?

**Answer:** No. You need backpressure/source policies, bounded buffers, quotas, and cancellation.

**Q8.** How should a MockMvc test verify `Mono.delay`?

**Answer:** Assert `request().asyncStarted()` then `asyncDispatch(result)` to verify status/JSON after async completion.

**Q9.** Should you call `.subscribe()` in a controller and return null?

**Answer:** No; it breaks integration between the publisher and response lifecycle. Return the publisher.

**Q10.** When should WebFlux be chosen over MVC?

**Answer:** When non-blocking HTTP I/O and an end-to-end reactive pipeline are needed, especially for high-concurrency streaming/slow clients; choose based on benchmarks and code complexity, not just Mono/Flux names.

## 18. Official references

- [Spring Framework 6.2 — Asynchronous Requests](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-ann-async.html): Servlet async, Reactive Types, write blocking, backpressure, context propagation, and executors.
- [Spring Framework — Controller Return Values](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/return-types.html): Mono/Flux adapters, streaming vs. JSON collection, DeferredResult, and emitters.
- [Spring Framework — ResponseEntity](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/responseentity.html): `ResponseEntity<Mono<T>>` and `Mono<ResponseEntity<T>>`.
- [Spring Framework 6.2 — HTTP Streaming](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-ann-async.html#_http_streaming): SSE, ResponseBodyEmitter, and StreamingResponseBody.
- [Spring Framework 6.2 — MVC Async Config](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-ann-async.html#_configuration): `WebMvcConfigurer#configureAsyncSupport`, task executor, and timeout.
- [Spring Framework — ReactiveAdapterRegistry Javadoc](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/core/ReactiveAdapterRegistry.html): Reactive Streams adapters.
- [Spring Framework 6.2 — ServerSentEvent Javadoc](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/http/codec/ServerSentEvent.html): SSE event representation.
- [Project Reactor — Reference](https://projectreactor.io/docs/core/release/reference/): Mono/Flux, schedulers, backpressure, cancellation, testing.
- [Spring Boot 3.5 — Web Servlet Applications](https://docs.spring.io/spring-boot/3.5/reference/web/servlet.html): Servlet MVC stack, embedded containers.
- [Spring Boot 4 — Build Systems/Starters](https://docs.spring.io/spring-boot/4.0/reference/using/build-systems.html): starter changes when upgrading to Boot 4.

**Conclusion:** in Spring MVC, **Mono = single async result**, **Flux + standard JSON = collected into an array**, **Flux + SSE/NDJSON = streaming**. MVC can manage backpressure and the Servlet async request lifecycle, yet **response writes remain blocking** and use `AsyncTaskExecutor`. Safe production streaming requires controlling executors, memory, timeouts, producer speed, cancellation, proxy buffering, and post-commit errors; merely returning reactive types does not turn an MVC app into WebFlux.
