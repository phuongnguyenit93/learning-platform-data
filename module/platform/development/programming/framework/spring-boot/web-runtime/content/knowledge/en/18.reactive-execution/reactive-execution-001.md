# The Publisher Chain from Request Reading to Response Writing in Spring WebFlux

> **Scope:** Spring Boot web runtime in the **reactive** model, using Spring WebFlux and Project Reactor. This lesson traces the complete path of **an HTTP request**: from bytes on the network connection, decoding the request body into a `Publisher`, processing by handler/service, to encoding and writing the HTTP response. Examples run with **Spring Boot 4.1.2**, **Java 17+**, and **Maven 3.6.3+**. Core concepts also apply to WebFlux in Spring Boot 3.x, though corresponding dependencies and versions should be used.

## Objectives

After this lesson, you will be able to:

1. Accurately describe the roles of `Publisher`, `Subscriber`, `Subscription`, `Mono`, `Flux`, `DataBuffer`, and `Mono<Void>` in the HTTP processing chain.
2. Explain how WebFlux **streams the body**, decodes it into objects, transforms it with operators, and writes the response according to downstream demand.
3. Distinguish between **pipeline assembly** and **execution upon subscription**, knowing who subscribes and why typical handlers do not call `subscribe()` or `block()` themselves.
4. Understand the propagation of `onNext`, `onError`, `onComplete`, `request(n)`, and `cancel` signals across layers.
5. Build and invoke two endpoints: a single-result JSON POST and a multi-result Server-Sent Events GET; recognize common pitfalls regarding blocking, buffering, errors, and disconnection.

## 1. Mental Model: An HTTP Request and a Publisher Are Not the Same Thing

**Reactive Streams** defines a protocol between a producer `Publisher<T>` and a consumer `Subscriber<T>`. A Publisher can emit **0 to many elements**, complete successfully, or terminate with an error; the subscriber uses `Subscription` to request data and cancel the stream.

In Reactor, two commonly used types are:

| Type | Number of data elements | Common usage in WebFlux |
| --- | --- | --- |
| `Mono<T>` | 0 or 1 | Decoding a single JSON object, looking up a record, creating a response, awaiting an asynchronous task |
| `Flux<T>` | 0 to N | Body chunks, sequences of JSON/NDJSON elements, SSE events, continuous data streams |
| `Mono<Void>` | No useful value `T`; emits only completion or error signals | Representing **completion of an operation**, such as handling an exchange or finishing writing a response |
| `Flux<DataBuffer>` | Multiple byte buffers | Representing the request body or response body at the raw data layer, before/after codecs |

An HTTP request has **method, path, headers**, and potentially a **body**. Headers are usually read sufficiently for routing when the handler is selected; the body may still be arriving over the network. WebFlux represents body data as a Publisher for asynchronous processing without needing to hold the entire request in memory before starting work if the codec/use case supports streaming.

Example: `POST /api/echo` carries `{"name":"Lan"}`. At the transport layer there are bytes; at the application layer, `request.bodyToMono(EchoRequest.class)` provides `Mono<EchoRequest>`. The service transforms the object into a `Mono<String>` result; WebFlux uses `HttpMessageWriter` to turn the result into bytes for the response. This is a **chain linking multiple Publishers/Subscribers and adapters**, not a single `Publisher` object spanning every layer.

**Important distinction:** WebFlux supports a reactive HTTP server on Reactor Netty and also provides adapters for compatible Servlet containers. Using Netty is a common choice with the WebFlux starter, but `reactive` is not synonymous solely with Netty; the primary criteria are non-blocking APIs and the Publisher/Subscriber protocol. Do not bring Spring MVC's `DispatcherServlet` architecture into the WebFlux pipeline; WebFlux's front controller is **`DispatcherHandler`**.

## 2. Full Request-to-Response Map

With Spring Boot + WebFlux + Reactor Netty, this can be visualized as:

~~~text
Client sends POST /api/echo and JSON over TCP/HTTP
             |
             v
Reactor Netty: receives request, manages non-blocking I/O
             |
             v
ReactorHttpHandlerAdapter -> HttpHandler
             |
             v
WebHttpHandlerBuilder: builds the WebHandler chain
    +--> WebExceptionHandler (wraps error handling)
    +--> WebFilter chain (filters request/response)
    +--> DispatcherHandler (WebFlux front controller)
            |
            +--> HandlerMapping (finds route/handler)
            +--> HandlerAdapter (invokes handler)
            |       |
            |       +--> Handler reads body:
            |       |    Flux<DataBuffer>
            |       |       -> HttpMessageReader / Decoder
            |       |       -> Mono<EchoRequest>
            |       |       -> map / flatMap / service
            |       |       -> Mono<ServerResponse>
            |       |
            |       +--> HandlerResult
            |
            +--> HandlerResultHandler / ServerResponse.writeTo
                    |
                    +--> HttpMessageWriter / Encoder
                    +--> Publisher<DataBuffer> to write body
             |
             v
Response status + headers + bytes -> Reactor Netty -> client

The entire exchange completes via a Mono<Void>-style task
when writing finishes, an error occurs, or the request is cancelled.
~~~

**Do not interpret the diagram as synchronous steps occupying one thread until the end.** This is a diagram of responsibilities and pipeline linkages. Reading, processing, and writing can occur across multiple asynchronous callbacks; `onNext` flows from source to downstream according to demand, and steps can interleave with I/O.

### What Does Each Layer Handle?

| Layer | Interface/component | Responsibility |
| --- | --- | --- |
| Server transport | Reactor Netty | Receives/sends bytes, signals socket read/write readiness |
| HTTP adapter | `HttpHandler`, `ServerHttpRequest`, `ServerHttpResponse` | Bridges a specific server with server-agnostic HTTP handling |
| Web chain | `WebFilter`, `WebExceptionHandler`, `WebHandler` | Handles cross-cutting concerns, defines processing chain and error interception points |
| Front controller | `DispatcherHandler` | Looks up handler, invokes handler, delegates result to response writing |
| Routing | `HandlerMapping` | Matches route in annotated controllers or functional `RouterFunction` |
| Invocation | `HandlerAdapter` | Resolves arguments and invokes handler; wraps `HandlerResult` |
| Request codec | `HttpMessageReader` + `Decoder` | Converts `DataBuffer` into Java objects, strings, multipart, or element streams |
| Business pipeline | `Mono`/`Flux` + Reactor operators | Applies validation, services, data transformations, and application-owned error handling |
| Response codec | `HandlerResultHandler` or functional `ServerResponse`, `HttpMessageWriter`/`Encoder` | Selects status/headers, encodes values to bytes, and writes response |
| Exchange completion | `Mono<Void>` and terminal signals | Signals completion/error of HTTP work; cancel can short-circuit the process |

In the **annotated controller** style, `RequestMappingHandlerMapping` selects the `@GetMapping`/`@PostMapping` method; `RequestMappingHandlerAdapter` performs invocation; `ResponseBodyResultHandler` writes the result from `@RestController`. In the **functional endpoint** style, `RouterFunctionMapping` selects a `HandlerFunction` taking `ServerRequest` and returning `Mono<ServerResponse>`. Both run on the same reactive web foundation underneath; the way routes are declared and responses are written differs.

## 3. Step by Step: From Request Reading to Response Writing

### Step 1 — Request Arrives and Body Is Represented as a Byte Stream

When a request is accepted, the server adapter creates/exposes the request-response abstraction. At a low level, you can look at:

~~~java
// Illustrates WebFlux API inside a WebHandler; not a standalone program.
Flux<DataBuffer> rawBody = exchange.getRequest().getBody();
~~~

`DataBuffer` is the abstraction for a byte buffer. With Netty, buffers may use pooled memory and reference counting. TCP packet splitting, HTTP chunks, and the `DataBuffer` instances you see do not mean each chunk corresponds to one JSON object. Never assume "one buffer = one message".

`getBody()` enables non-blocking processing in a runtime-appropriate way; it does not mean the entire body is automatically preloaded. To read raw byte streams, you must properly handle framing, encoding, size limits, and buffer release. In typical applications, **prefer high-level codecs** like `bodyToMono(...)` or `@RequestBody Mono<T>`.

### Step 2 — Routing Happens Before the Handler Consumes the Body

`DispatcherHandler` queries the `HandlerMapping` instances to find a handler matching the path, method, headers, and route predicates. Then a `HandlerAdapter` or functional handler is used to produce the result.

Key point: **routing is typically based on method/path/headers, without waiting to decode the entire body**. A handler can be selected before the body has fully arrived. Subsequent body chunks are pushed into the stream as I/O and demand allow.

If no route matches, the framework produces the corresponding HTTP error without running that route's business pipeline. If a `WebFilter` is present, the filter can perform pre/post-handler work through the `Mono<Void>` chain.

### Step 3 — `HttpMessageReader` Decodes the Body Publisher

Functional WebFlux can be written as:

~~~java
Mono<EchoRequest> input = request.bodyToMono(EchoRequest.class);
~~~

Conceptually equivalent annotated WebFlux:

~~~java
@PostMapping("/api/echo")
public Mono<EchoResponse> echo(@RequestBody Mono<EchoRequest> input) {
    return input.flatMap(req -> service.reply(req.name()))
                .map(EchoResponse::new);
}
~~~

The annotated snippet is illustrative, assuming `service.reply(...)` returns `Mono<String>`, with imports and `EchoRequest`/`EchoResponse` available. Do not add this route with the same path into the functional project below.

`bodyToMono(EchoRequest.class)`/`@RequestBody Mono<EchoRequest>` uses `HttpMessageReader` implementations matching the `Content-Type` and target type, such as a JSON decoder. Byte data is decoded into an object and emits **one** `onNext(EchoRequest)`, then `onComplete`; an empty body may become `Mono.empty()`; malformed JSON or an unsupported media type results in an HTTP error / `onError` emission at the corresponding stage.

When multiple elements are needed, `bodyToFlux(T.class)` can decode into multiple objects **if the codec and media type support stream representation**, such as NDJSON. However, `Flux<T>` in the API **does not automatically guarantee** the server streams each object immediately for regular `application/json`. Streaming capability depends on the format, codec, data source, and flushing behavior.

**The body is not an infinitely repeatable resource.** Do not manually `subscribe()` twice to the body Publisher to read the same payload multiple times; an HTTP body is by default a single stream of bytes from the connection, with no built-in replay mechanism. If you need to process the body for multiple purposes, decode once and share the result in a controlled manner, or use a caching/request-decorating mechanism with explicit size limits and `DataBuffer` rules.

### Step 4 — Assembling Business Logic with Operators

Example processing chain:

~~~java
return request.bodyToMono(EchoRequest.class)            // Mono<EchoRequest>
    .flatMap(value -> service.reply(value.name()))     // Mono<String>
    .map(message -> new EchoResponse(message))         // Mono<EchoResponse>
    .flatMap(result -> ServerResponse.ok()
        .contentType(MediaType.APPLICATION_JSON)
        .bodyValue(result));                           // Mono<ServerResponse>
~~~

Differences among operators:

- `map(T -> R)`: **synchronous, fast** transformation producing one `R` value per `T` value; do not use it to call a function returning `Mono<R>` expecting the result to be automatically awaited/flattened.
- `flatMap(T -> Mono<R>)`: turns each `T` into an asynchronous publisher and **flattens/merges** the results. With `Flux.flatMap`, multiple inner publishers can be processed concurrently, causing output element order to differ from input order; use `concatMap` if sequential ordering is required.
- `filter`: can turn the chain empty when a value does not match; you must explicitly decide whether empty means "no data", 404, 400, or 204.
- `switchIfEmpty`: switches to another publisher when upstream completes without data, commonly used to turn empty into an HTTP error or fallback result.
- `onErrorResume`: converts a type of error into a fallback/response publisher; do not use it to swallow all errors unconditionally.
- `then()`: ignores upstream data values, awaits completion, and returns `Mono<Void>`; suitable when the goal is completing an operation rather than needing a body.

**A pipeline is not a sequence of synchronous calls:** the `flatMap(...)` line describes how to process when upstream provides a value. When the handler method returns `Mono<ServerResponse>`, unsubscribed work may not have run yet. The service performs reactive I/O when subscription occurs.

### Step 5 — Handler Returns a Publisher, Framework Orchestrates Subscription

In WebFlux, handlers typically **return** `Mono<T>`, `Flux<T>`, or `Mono<ServerResponse>`; the framework/server handles integrating it into the exchange and **subscribing** at the runtime boundary.

Therefore, do not write:

~~~java
// Wrong in a WebFlux handler:
service.save(input).subscribe();  // drops errors, cancellation, and completion ordering
return Mono.empty();              // HTTP may complete before save finishes
~~~

Instead, **compose and return the Publisher**:

~~~java
// Correct composition, assuming save(input) returns Mono<?>:
return service.save(input).then();
~~~

Explicit `subscribe()` can be appropriate at an imperative boundary truly owned by the application, such as an event listener designed to manage its own lifecycle and errors. However, inside an HTTP handler, subscribing early **breaks error, context, cancellation, and completion propagation** between the work and the response.

`block()`/`blockFirst()`/`blockLast()` wait synchronously for results, risking blocking the event loop, and Reactor may even reject blocking on schedulers marked as non-blocking. If you must call a blocking legacy library, isolate it (e.g., `Mono.fromCallable(...)` + `subscribeOn(Schedulers.boundedElastic())`) and bound concurrency; the long-term solution is using a non-blocking driver or client.

### Step 6 — Writing the Response Is Another Publisher Pipeline

In annotated WebFlux, `HandlerResultHandler` chooses how to handle the `Mono<EchoResponse>`/`Flux<T>` result. In functional WebFlux, `ServerResponse` with status, headers, and body is written via `ServerResponse.writeTo(...)`. `HttpMessageWriter` selects an encoder matching the type/`Content-Type`, converts objects into `DataBuffer` instances, and passes them to the response layer.

If a handler returns `Mono<ServerResponse>`, do not confuse these three:

1. **Outer `Mono<ServerResponse>`:** asynchronously determines the response (status/headers/body strategy).
2. **Response body Publisher:** may be `Mono<T>`, `Flux<T>`, or a value adapted into a publisher for the codec to write.
3. **Exchange write completion `Mono`:** represents the runtime completing the commit and write of the response or an error during that process.

With `Mono<EchoResponse>` and regular JSON, the response is usually a single JSON object. With `Flux<EchoResponse>` and `application/json`, the codec may construct **one JSON array**; depending on the codec/format, buffering may occur. With `text/event-stream`, events are encoded/flushed as an SSE stream so the client receives them incrementally. With `application/x-ndjson`, each JSON object sits on its own line, useful for streaming records continuously. Do not assume every returned `Flux<T>` streams immediately to the HTTP client.

**Commit timing matters:** once status/headers have been sent, an error occurring mid-stream during body writing usually cannot turn an in-flight 200 response into a new 500 response. Applications should handle errors before commit whenever possible; for long-lived SSE/NDJSON streams, design error signaling within the stream protocol and client reconnection behavior.

### Step 7 — Completion, Errors, and Cancellation

Reactive Streams has these core signals:

~~~text
Subscriber <- onSubscribe(Subscription)
Subscriber  -> request(n)    // downstream requests up to n elements
Publisher   -> onNext(value) // emitted when source produces and demand exists
Publisher   -> onNext(value) // ... possibly multiple times with Flux
Publisher   -> onComplete()  // successful terminal signal
         OR
Publisher   -> onError(err)  // error terminal signal
         OR
Subscriber  -> cancel()      // stop receiving data from upstream
~~~

`onComplete` and `onError` are mutually exclusive within a valid subscription. `cancel()` is neither `onError` nor `onComplete`, and cancellation may take time to propagate to the source. For a `Mono<Void>` completing successfully, there is no `onNext(value)`, yet `onComplete()` still fires.

Client disconnection can cause the transport to cancel/close the write chain. A properly composed Publisher can receive cancel to stop queries, timers, or data sources. However, cancellation **does not automatically roll back** an already committed external operation (e.g., a database write). Cancellation propagation depends on the adapter, Publisher source, and I/O state; never promise that closing a connection halts every side effect instantaneously.

## 4. Assembly, Subscription, and Backpressure: Three Things You Must Separate

### Assembly: Creating the Publisher Object

Example:

~~~java
Mono<String> pipeline = Mono.just("lan")
    .map(String::toUpperCase)
    .doOnNext(System.out::println);
~~~

Here the pipeline is only **described**; `System.out.println` inside `doOnNext` does not run just because the code created the `Mono`. Only when a subscriber actually requests and the source emits `onNext` does the side effect happen. Some factories are eager at object creation time—for instance, the argument expression passed to `Mono.just(expensiveCall())` runs immediately. Use `Mono.defer(...)` or `Mono.fromCallable(...)` when you need to defer data creation until subscription.

### Subscription: Establishing the Upstream/Downstream Relationship

When the runtime subscribes, Reactor builds the subscriber chain across operators. `Subscription` links both sides, after which downstream issues demand. For handlers, WebFlux does this as part of the HTTP lifecycle; controller authors do not subscribe manually.

If you call `subscribe()` twice on a **cold publisher**, the work may execute twice (e.g., two HTTP calls or two queries). A **hot publisher** may emit data independently of any subscriber, so latecomers may miss earlier elements. `share()`, `cache()`, and `publish()` change semantics and carry memory, lifecycle, and subscription-count implications; do not use them merely to "patch" a bug you do not fully understand.

### Demand/Backpressure: How Much Data the Subscriber Requests

`request(n)` expresses downstream demand; a Reactive Streams-compliant source must not emit `onNext` beyond unsatisfied demand. When a client reads slowly, the server can throttle receiving/pushing data upstream via I/O adapters and backpressure-aware operators.

However, **backpressure does not eliminate all buffering**. External sources might not support throttling, or a codec/operator might need to buffer to decode a large JSON object. `flatMap` has prefetch, `buffer` groups elements, `collectList` gathers the entire sequence into RAM, and `cache` retains data; you must measure memory and bound real payloads.

Rate example: a `Flux` of 100,000 events does not necessarily create 100,000 response objects immediately. With SSE and a demand-aware source, data can be generated/written incrementally; however, if you call `collectList()` before returning the response, you have switched from streaming to accumulating all data before replying.

**Rule of thumb:** do not manually call `subscribe()` or `request(Long.MAX_VALUE)` to "force" a handler to run; return the Publisher to the framework and monitor buffering/backpressure under realistic load.

## 5. Runnable Java 17 Project: POST JSON and GET SSE

This example intentionally uses **functional endpoints** so `ServerRequest.bodyToMono(...)` and `ServerResponse.body(...)` are clearly visible. It uses no database and creates no custom threads; `Flux.interval` is used solely to illustrate emitting events over time.

Directory structure:

~~~text
webflux-publisher-flow/
  pom.xml
  src/main/java/com/example/publisherflow/
    PublisherFlowApplication.java
    RouteConfig.java
    EchoHandler.java
    EchoService.java
~~~

**`pom.xml`** — the WebFlux starter includes Reactor Netty; the parent manages compatible dependency versions.

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.2</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>webflux-publisher-flow</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**`src/main/java/com/example/publisherflow/PublisherFlowApplication.java`**

~~~java
package com.example.publisherflow;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class PublisherFlowApplication {
    public static void main(String[] args) {
        SpringApplication.run(PublisherFlowApplication.class, args);
    }
}
~~~

**`src/main/java/com/example/publisherflow/RouteConfig.java`**

~~~java
package com.example.publisherflow;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.server.RouterFunction;
import org.springframework.web.reactive.function.server.RouterFunctions;
import org.springframework.web.reactive.function.server.ServerResponse;

@Configuration(proxyBeanMethods = false)
public class RouteConfig {
    @Bean
    RouterFunction<ServerResponse> routes(EchoHandler handler) {
        return RouterFunctions.route()
                .POST("/api/echo", handler::echo)
                .GET("/api/ticks", handler::ticks)
                .build();
    }
}
~~~

**`src/main/java/com/example/publisherflow/EchoService.java`**

~~~java
package com.example.publisherflow;

import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;
import reactor.core.publisher.Mono;

@Service
public class EchoService {
    public Mono<String> reply(String name) {
        return Mono.justOrEmpty(name)
                .map(String::trim)
                .filter(value -> !value.isEmpty())
                .switchIfEmpty(Mono.error(new ResponseStatusException(
                        HttpStatus.BAD_REQUEST, "name must not be blank")))
                .map(value -> "Hello, " + value + "!");
    }
}
~~~

Here `Mono.justOrEmpty(null)` creates an empty publisher and `switchIfEmpty(...)` turns `null`/blank strings into HTTP 400. There are no side effects to wait on; using `Mono` still keeps the pipeline connected and demonstrates how a service can later be backed by reactive I/O.

**`src/main/java/com/example/publisherflow/EchoHandler.java`**

~~~java
package com.example.publisherflow;

import java.time.Duration;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.server.ServerRequest;
import org.springframework.web.reactive.function.server.ServerResponse;
import org.springframework.web.server.ResponseStatusException;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Component
public class EchoHandler {
    private final EchoService service;

    public EchoHandler(EchoService service) {
        this.service = service;
    }

    // Single JSON object -> single JSON object response.
    public Mono<ServerResponse> echo(ServerRequest request) {
        return request.bodyToMono(EchoRequest.class)
                .switchIfEmpty(Mono.error(new ResponseStatusException(
                        HttpStatus.BAD_REQUEST, "request body is required")))
                .flatMap(body -> service.reply(body.name()))
                .map(EchoResponse::new)
                .flatMap(result -> ServerResponse.ok()
                        .contentType(MediaType.APPLICATION_JSON)
                        .bodyValue(result));
    }

    // Flux emits three items, every 500 ms, as SSE.
    public Mono<ServerResponse> ticks(ServerRequest request) {
        Flux<String> events = Flux.interval(Duration.ofMillis(500))
                .take(3)
                .map(index -> "tick-" + index);

        return ServerResponse.ok()
                .contentType(MediaType.TEXT_EVENT_STREAM)
                .body(events, String.class);
    }

    public record EchoRequest(String name) {}
    public record EchoResponse(String message) {}
}
~~~

Notice the code above does **not** call `subscribe()` itself. `echo()` constructs a Publisher for the result. With `ticks()`, `Mono<ServerResponse>` builds response metadata and `Flux<String>` acts as the body source; WebFlux subscribes/writes data according to the HTTP exchange lifecycle. `Flux.interval(...)` uses Reactor's timer scheduler; this simulates a non-blocking source and is not a real data-query example.

### Testing It Out

In the directory containing `pom.xml`:

~~~bash
mvn spring-boot:run
~~~

By default the server listens on port 8080 unless overridden by configuration. In Bash or a shell supporting single quotes, send a request:

~~~bash
curl -i -X POST http://localhost:8080/api/echo \
  -H "Content-Type: application/json" \
  -d '{"name":" Lan "}'
~~~

Expect status **HTTP 200**, JSON `Content-Type`, and body:

~~~json
{"message":"Hello, Lan!"}
~~~

Whitespace in `name` is stripped by `String::trim`. HTTP header ordering, response timestamps, and connection info may vary by environment.

Test the blank-name error:

~~~bash
curl -i -X POST http://localhost:8080/api/echo \
  -H "Content-Type: application/json" \
  -d '{"name":"   "}'
~~~

Expect **HTTP 400**; the error body is determined by the Spring Boot/WebFlux error handler and may vary by configuration/version, so do not hardcode exact error JSON content.

Read the event stream:

~~~bash
curl -N -i http://localhost:8080/api/ticks
~~~

Expect HTTP 200, `Content-Type: text/event-stream`, and three payloads in order carrying values `tick-0`, `tick-1`, `tick-2`; each event arrives on the timer tick rather than being buffered into one JSON array. With a typical SSE writer, the data looks roughly like:

~~~text
data:tick-0

data:tick-1

data:tick-2

~~~

This is an **illustration of an SSE body**; actual line endings, headers, and timing are determined by the writer/server/client. `curl -N` disables curl's output buffering so you can observe each event.

On Windows PowerShell, you can send JSON with this command instead of Bash multiline syntax:

~~~powershell
Invoke-RestMethod -Uri "http://localhost:8080/api/echo" -Method Post -ContentType "application/json" -Body '{"name":" Lan "}'
~~~

And use `curl.exe -N http://localhost:8080/api/ticks` to view SSE as a stream.

### Tracing the Concrete Publisher Chain on POST

| Stage | Object/publisher | When does data exist? |
| --- | --- | --- |
| Server receives HTTP request | `ServerHttpRequest` / raw `Flux<DataBuffer>` | When the transport has bytes and the body is consumed |
| Functional handler calls `bodyToMono` | `Mono<EchoRequest>` | When the codec has read enough payload to construct the object |
| `flatMap(body -> service.reply(...))` | `Mono<String>` | When input is decoded and the service publisher emits data |
| `map(EchoResponse::new)` | `Mono<EchoResponse>` | When the `String` result is produced |
| `flatMap(result -> ServerResponse...)` | `Mono<ServerResponse>` | When HTTP response metadata and body strategy are built |
| WebFlux writes body | `HttpMessageWriter` + data-buffer Publisher | When the outer response is ready and the runtime subscribes to the response data publisher |
| Completion | `Mono<Void>` from exchange/write | When writing finishes or fails/cancels according to the lifecycle |

For GET SSE, there is **no** request body decoding step; `Flux.interval().take(3)` directly produces data to write. This illustrates that every HTTP exchange has its own pipeline, and not every exchange passes through `bodyToMono`.

## 6. When Real Applications Connect to Data Sources

Suppose a service uses a reactive database client:

~~~java
// Illustrative, depends on the project's actual reactive repository:
public Mono<OrderDto> findOrder(String id) {
    return reactiveRepository.findById(id)
            .map(order -> new OrderDto(order.getId(), order.getTotal()));
}
~~~

`reactiveRepository.findById` must genuinely provide an asynchronous publisher (e.g., R2DBC or a compatible reactive driver). Do not conclude that wrapping a synchronous JDBC call in `Mono.just(...)` makes it non-blocking; JDBC has already executed before the Mono is created.

If you are forced to temporarily integrate a blocking API:

~~~java
// Illustrative inside a service with an existing legacyClient; not standalone code.
Mono<Result> result = Mono.fromCallable(() -> legacyClient.load())
        .subscribeOn(Schedulers.boundedElastic());
~~~

This **isolates the blocking operation from the event loop**, but the inner operation remains blocking and consumes a thread; you need timeouts, pool monitoring, concurrency limits, and a migration plan to non-blocking APIs. `publishOn` and `subscribeOn` switch execution contexts—they do not turn synchronous libraries into asynchronous I/O.

When calling WebClient:

~~~java
// Illustrative with a pre-configured WebClient:
Mono<CustomerDto> customer = webClient.get()
        .uri("/customers/{id}", customerId)
        .retrieve()
        .bodyToMono(CustomerDto.class);
~~~

This too is just a pipeline. Do not call `block()` to obtain `CustomerDto` immediately inside a WebFlux handler; `flatMap` the publisher returned by WebClient into the response flow. `WebClient` handles client-side HTTP and returns a Publisher to compose into the server-side chain.

## 7. Handling Errors, Empty, and Cancellation by Stage

| Error stage | Example | Appropriate handling |
| --- | --- | --- |
| Routing | No handler found for `/api/missing` | Framework produces a 404-style response; check router/mappings |
| Decode | Invalid JSON, wrong media type, payload exceeds limit | Let WebFlux return appropriate 4xx; configure codec/limits and test |
| Validation/business | Blank `name` or missing record | Return `ResponseStatusException` or explicit 400/404 mapping |
| Downstream I/O | Service/database/WebClient timeout or error | Use `timeout`, selective `onErrorMap`/`onErrorResume`, contextual logging |
| Encode/write response | Cannot serialize type; socket failure | Diagnose writer/codec and whether response was already committed |
| Client cancel | User closes tab/closes SSE connection | Stop upstream source when possible; do not assume side effects roll back |

Inside a `Mono<T>` chain, empty differs from error:

~~~java
// Assuming repository.findById returns Mono<Order>:
return repository.findById(id)
        .switchIfEmpty(Mono.error(
                new ResponseStatusException(HttpStatus.NOT_FOUND, "Order not found")))
        .map(OrderDto::from);
~~~

If `Mono.empty()` flows straight to the response without an explicit policy, the outcome may violate the API contract. With `onErrorResume`, catch only exceptions you understand; avoid a blanket `onErrorResume(error -> Mono.empty())` for all exceptions because it hides failures and yields missing-data responses.

To observe the lifecycle (the snippet below is illustrative inside a method returning a Publisher):

~~~java
return somePublisher
        .doOnSubscribe(subscription -> log.debug("subscribed"))
        .doOnNext(value -> log.debug("emitted"))
        .doOnError(error -> log.warn("failed", error))
        .doFinally(signal -> log.debug("terminated: {}", signal));
~~~

`doFinally` can receive signals such as `ON_COMPLETE`, `ON_ERROR`, or `CANCEL`. Do not assume every component in a pipeline always passes through `doOnNext`: `Mono.empty()` and `Mono<Void>` can complete without emitting any value.

**When a streaming response has already sent partial data:** the server cannot retract bytes already transmitted. An exception at the 10th SSE event may close the stream mid-way; design consumers to detect disconnects, apply bounded retries, idempotency, or event IDs when needed. Never blindly `retry()` a Publisher reading a raw HTTP request body, as the network body source is not guaranteed to be replayable and retries may execute duplicate side effects.

## 8. Distinguishing Common Response Formats

| Application return type | Common Content-Type | Wire behavior to understand |
| --- | --- | --- |
| `Mono<T>` | `application/json` | One JSON object/value, or empty/error |
| `Flux<T>` | `application/json` | Usually a single JSON array; incremental sending depends on codec and may buffer |
| `Flux<T>` | `application/x-ndjson` | Multiple JSON objects, one per line; suitable for record streams |
| `Flux<ServerSentEvent<T>>` or SSE-supported data | `text/event-stream` | Events over time; suitable for server → browser/client |
| `Flux<DataBuffer>` | Depends on byte type | Passes raw buffers; application must handle release/cancellation |
| `Mono<Void>` | No body needed | Succeeds upon work completion; may fit 204 or bodyless response per chosen contract |

**SSE is not WebSocket.** SSE is a server → client HTTP response formatted as an event stream; WebSocket supports bidirectional communication through a different mechanism. **Mono is not inherently faster than blocking for every task**: the greatest value of reactive design shows when many operations are waiting on I/O and both sources and sinks are truly non-blocking.

## 9. Resource Limits and Common Mistakes When Building Publisher Chains

1. **Blocking on the event loop:** calling `Thread.sleep`, JDBC, `InputStream.read`, `Future.get`, or `block()` inside the I/O processing pipeline. As a result, other requests slow down because the event loop cannot keep serving them.
2. **Manual subscribe in a controller:** creates a "fire and forget" branch where the HTTP response may complete before business work finishes; loses error/cancel/context propagation.
3. **Reading the request body multiple times:** calling `bodyToMono`/subscribing repeatedly on the same request without a replay strategy; leads to empty bodies or consumption errors.
4. **Holding `DataBuffer` without releasing:** on backends using pooled buffers this causes memory leaks; in regular controllers, rely on codecs so the framework manages buffers.
5. **Unbounded `collectList`:** accumulates a large stream in memory and defeats incremental processing; bound item counts/sizes.
6. **Using `Flux.flatMap` when ordering is required:** async results may finish out of order; consider `concatMap` or explicit ordering strategies.
7. **Confusing empty with error:** absence of data does not automatically mean 404/400; decide the API contract and use `switchIfEmpty` if needed.
8. **Returning SSE without a heartbeat:** some proxies/clients drop idle connections; for long-lived streams, send keep-alive events/comments using an appropriate strategy.
9. **Assuming all Flux = streaming:** `application/json`, codecs, proxies, and clients can buffer; use appropriate media types and verify with `curl -N`/network tracing.
10. **Storing request data in `ThreadLocal`:** operators may execute on different threads. When propagating metadata/correlation IDs across a chain, consider Reactor `Context` and supported context propagation mechanisms.
11. **Misconfiguring MVC/WebFlux:** in a Spring Boot app containing both MVC and WebFlux starters, Boot usually defaults to MVC. To run a WebFlux server, ensure the right web application type/dependencies and avoid applying servlet filters/interceptors instead of `WebFilter`.
12. **Modifying the response too late:** status and headers can only be modified before commit. For long streams, design an appropriate error protocol and timeouts.

### Practical Check Questions

**Q1.** Why is `return service.save(body).then()` better than `service.save(body).subscribe(); return Mono.empty();`?

**Answer:** The HTTP chain still waits for the work to complete, receives errors/cancellations along the pipeline, and ties its lifecycle to the HTTP exchange. With manual subscribe, `save` runs independently and the response may complete before `save` finishes.

**Q2.** When does `bodyToMono(Order.class)` read `Flux<DataBuffer>`?

**Answer:** It creates a Publisher for the decoder to read the request body; actual data consumption is coordinated when the pipeline is subscribed to and demand/I/O permit. Headers/routing may already have been processed earlier.

**Q3.** If a handler returns `Flux<Event>`, will the client always see each event immediately?

**Answer:** No. This depends on `Content-Type`, writer, buffering, flushing, and the client. SSE/NDJSON are better suited when per-event/per-record delivery is the goal; always measure in practice.

**Q4.** Does a client disconnect automatically roll back an already committed insert statement?

**Answer:** No. Cancel can stop pending work if the source supports it, but it does not reverse completed side effects. Appropriate transactions and idempotency are required.

**Q5.** What acts as WebFlux's front controller, and who writes the response?

**Answer:** `DispatcherHandler` coordinates `HandlerMapping`/`HandlerAdapter`/`HandlerResultHandler`. The response is encoded by writers/codecs and written through the HTTP adapter/server; the application describes the response with `Mono`/`Flux` or `ServerResponse`.

## 10. Official Documentation

- [Spring Framework — WebFlux Reactive Core: HttpHandler, WebHandler, DataBuffer, codecs](https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html)
- [Spring Framework — WebFlux DispatcherHandler: routing, adapter, result handler](https://docs.spring.io/spring-framework/reference/web/webflux/dispatcher-handler.html)
- [Spring Framework — WebFlux Functional Endpoints: ServerRequest/ServerResponse](https://docs.spring.io/spring-framework/reference/web/webflux-functional.html)
- [Spring Framework — WebFlux @RequestBody](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/requestbody.html)
- [Spring Framework — WebFlux @ResponseBody](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/responsebody.html)
- [Spring Boot — Reactive Web Applications and WebFlux configuration](https://docs.spring.io/spring-boot/reference/web/reactive.html)
- [Project Reactor — Subscription and backpressure](https://projectreactor.io/docs/core/release/reference/coreFeatures/simple-ways-to-create-a-flux-or-mono-and-subscribe-to-it.html)
- [Project Reactor — Threading and Schedulers](https://projectreactor.io/docs/core/release/reference/coreFeatures/schedulers.html)
- [Spring Boot — System Requirements](https://docs.spring.io/spring-boot/reference/getting-started/system-requirements.html)

**Key takeaway:** A request body can be a `Flux<DataBuffer>` converted by codecs into `Mono<T>`/`Flux<T>`; the application **composes** operators and returns a Publisher; the framework **subscribes and writes** the response; demand, errors, completion, and cancellation flow upstream/downstream through the chain. Understanding this path helps keep I/O non-blocking, control memory, and pinpoint when a request truly finishes.