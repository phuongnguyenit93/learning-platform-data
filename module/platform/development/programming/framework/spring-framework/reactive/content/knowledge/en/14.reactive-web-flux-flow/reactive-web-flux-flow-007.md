# When the Framework Subscribes to Read the Body and Write the Response in Spring WebFlux

## 1. Core question: when is data actually read and written?

In Spring WebFlux, controllers usually return `Mono<T>` or `Flux<T>`. These types describe a process that will emit data after someone subscribes. Invoking a controller method and the framework actually reading the request body or writing the response body can therefore happen at **different times**.

Two questions must be separated:

- **Reading the request body:** when does Spring start subscribing to the Publisher representing the body and use codecs to decode bytes into objects?
- **Writing the response body:** when does Spring subscribe to the Publisher returned by the controller, select a writer, encode objects into bytes, and send the bytes down to the HTTP server?

Most important point: in a typical WebFlux request, **the framework manages the HTTP pipeline's subscription**. The application creates and composes Publishers and returns them; do not call `subscribe()` or `block()` yourself in a controller to trigger reading/writing.

~~~text
HTTP server receives request
        |
        v
WebFlux routes to handler/controller
        |
        +--> resolves method parameters
        |       |
        |       +--> @RequestBody Object
        |       |       -> reads/decodes body before invoking method
        |       |
        |       +--> @RequestBody Mono<T>/Flux<T>
        |               -> passes Publisher to method
        |                  body is consumed when the Publisher is subscribed
        |
        v
Invoke controller/HandlerFunction
        |
        v
Receive return value (Object, Mono, Flux, ResponseEntity, ...)
        |
        v
HandlerResultHandler / response writer
        |
        +--> selects HttpMessageWriter based on data type + media type
        |
        v
Framework subscribes to the response-writing Publisher
        |
        v
Encode -> write bytes -> commit response -> complete/error/cancel
~~~

This diagram is a lifecycle view. The server receiving bytes from the socket may happen before the codec consumes them; "reading the body" in this lesson refers to **the process where the framework subscribes to and decodes the request body**, not claiming the NIC/server only receives bytes at that exact moment.

## 2. Assembly and subscription: creating a Publisher does not mean running it

### 2.1. Assembly time

Assembly is when Java executes the statements that create Publishers and chain operators:

~~~java
Mono<String> result = Mono.fromSupplier(() -> {
    System.out.println("supplier executed");
    return "hello";
}).map(String::toUpperCase);

System.out.println("publisher assembled");
~~~

Stdout:

~~~text
publisher assembled
~~~

The supplier has not run yet because there is no subscriber. Similarly, calling `request.bodyToMono(Order.class)` creates a Publisher representing reading/decoding the body; creating the Publisher object does not mean the body has already been completely consumed.

### 2.2. Subscription time

Once there is a subscriber, the pipeline begins executing according to demand:

~~~java
result.subscribe(System.out::println);
~~~

Subsequent stdout:

~~~text
supplier executed
HELLO
~~~

In an HTTP server, Spring performs the subscription to the request/response processing pipeline. When the subscriber requests data, the source and upstream operators start working according to the Reactive Streams contract.

### 2.3. Why does the controller not need to subscribe itself?

For a controller:

~~~java
@GetMapping("/message")
public Mono<String> message() {
    return Mono.fromSupplier(() -> "hello");
}
~~~

Spring receives `Mono<String>`, chooses the appropriate way to write the response, and manages the subscription to send the content. If the controller writes:

~~~java
@GetMapping("/wrong")
public Mono<String> wrong() {
    Mono<String> source = service.load();
    source.subscribe(); // Should not be done in a handler
    return Mono.just("accepted");
}
~~~

then the subscription created by the application runs independently of the response. HTTP may return before `service.load()` completes; errors and cancellation are no longer properly tied to the request lifecycle. Return or compose the Publisher instead:

~~~java
@GetMapping("/correct")
public Mono<String> correct() {
    return service.load().map(value -> "loaded=" + value);
}
~~~

Do not call `block()` to get data synchronously on the event loop. It blocks the I/O-handling thread and defeats WebFlux's non-blocking benefit.

## 3. When does Spring read the request body?

Spring WebFlux uses `HttpMessageReader<T>` to decode the HTTP body into a Java object or reactive publisher. `ServerCodecConfigurer` provides the default readers and allows configuring codecs. The reader is selected based on the target data type, `Content-Type`, and codec support.

### 3.1. `@RequestBody Object`: resolve the body before invoking the controller

Example:

~~~java
@PostMapping("/orders")
public Mono<String> create(@RequestBody CreateOrder request) {
    System.out.println("controller invoked");
    return orderService.create(request).thenReturn("created");
}
~~~

With an ordinary `CreateOrder` parameter, Spring must read and decode the body into an object before it can invoke the controller method. Conceptual sequence:

1. Routing finds the right handler method.
2. The argument resolver asks `HttpMessageReader` to read the body and create `CreateOrder`.
3. Only after the object has been resolved successfully does Spring invoke `create(request)`.
4. The method returns `Mono<String>`.
5. The framework subscribes to the resulting Publisher to write the response.

If the JSON is invalid, the body is missing when required, or conversion fails, the error can occur **before the log line inside the controller runs**. This is an important difference compared to accepting `Mono<CreateOrder>`.

"Reading before invoking the method" does not mean Spring has to block a thread until the entire network transfer finishes. Resolving the parameter is still coordinated through the reactive pipeline; the method is simply invoked once the non-reactive parameter value is ready.

### 3.2. `@RequestBody Mono<T>`: the method receives the Publisher first; the body is read upon subscription

Example:

~~~java
@PostMapping("/orders")
public Mono<String> create(@RequestBody Mono<CreateOrder> requestMono) {
    System.out.println("controller invoked");
    return requestMono
        .doOnNext(order -> System.out.println("decoded=" + order.name()))
        .flatMap(orderService::create)
        .thenReturn("created");
}
~~~

Here the method receives a `Mono<CreateOrder>`. Spring can invoke the method with that Publisher without waiting for the `CreateOrder` object to be decoded yet. The body is actually consumed when the returned chain is subscribed to and the subscription reaches `requestMono`.

~~~text
Spring resolves argument -> creates requestMono
             |
             v
Invokes controller method
             |
             v
Controller returns requestMono.flatMap(...).thenReturn(...)
             |
             v
Framework subscribes to response Publisher
             |
             v
Subscription reaches requestMono
             |
             v
HttpMessageReader reads bytes and decodes CreateOrder
             |
             v
flatMap -> service -> response
~~~

This lets the controller combine reading the body with subsequent reactive operations without managing subscriptions itself.

If the controller receives `Mono<T>` but does not include it in the returned chain, does not subscribe itself, and does not pass it to another reactive component, the body Publisher may not be consumed by that logic. Therefore, check that the request body is actually composed into the pipeline managed by the framework.

### 3.3. `@RequestBody Flux<T>`: reading multiple elements on demand

For a body that can be represented as multiple elements:

~~~java
@PostMapping("/events")
public Mono<Long> receive(@RequestBody Flux<Event> events) {
    return events
        .doOnNext(event -> System.out.println("event=" + event.id()))
        .count();
}
~~~

`Flux<Event>` allows processing each element as the decoder produces it. When the downstream subscriber requests data, demand can propagate backward through the operators to the reader and request source. The application does not necessarily have to collect the entire body into a `List<Event>` before processing.

However, `Flux<T>` does not automatically guarantee that every format streams in the same way. Decoding capability depends on the codec and media type. For example, the Jackson decoder can split JSON content into objects once enough bytes arrive for each object; NDJSON/JSON Lines is also suitable for line-delimited object streams.

### 3.4. Comparing the three parameter types

| Controller parameter | When the method is invoked | When the body is consumed | Suitable for |
| --- | --- | --- | --- |
| `@RequestBody Order` | After the argument is read/decoded into Order | Before the method is invoked | A small object, simple logic |
| `@RequestBody Mono<Order>` | The method receives a Publisher | When the Publisher is subscribed to in the pipeline | A single asynchronous object, composed with a service |
| `@RequestBody Flux<Event>` | The method receives a Publisher | When downstream subscribes and requests elements | Stream of many events, item-by-item processing |

Choose the parameter type according to the data contract and processing style. Do not use `Flux` just to look "reactive" if the business logic actually needs a single small object.

## 4. `HttpMessageReader` and codecs decide how decoding works

### 4.1. Conversion chain

~~~text
Bytes from HTTP request
        |
        v
DataBuffer
        |
        v
Decoder (e.g. JacksonJsonDecoder)
        |
        v
HttpMessageReader<T>
        |
        v
T or Publisher<T> (Mono/Flux)
        |
        v
Controller / handler
~~~

`Decoder` is the lower-level contract for decoding bytes into objects. `HttpMessageReader` connects the decoder to HTTP semantics, including media types and the request body. `DataBuffer` is the abstraction for byte data; on some servers such as Netty, buffers may be pooled and reference-counted.

In ordinary applications, use `@RequestBody`, `ServerRequest.bodyToMono`, `ServerRequest.bodyToFlux`, or `ServerWebExchange` APIs instead of manipulating `DataBuffer` yourself. If you read/retain buffers yourself, you must release them according to their lifecycle to avoid memory leaks.

### 4.2. `Content-Type` and Java type must be compatible

Examples:

- `Content-Type: application/json` with `@RequestBody CreateOrder`: the JSON reader decodes a single object.
- `Content-Type: application/json` with `@RequestBody Flux<CreateOrder>`: the decoder can split objects in supported JSON structures.
- `Content-Type: application/x-ndjson` with `Flux<CreateOrder>`: each JSON line is one element in the stream.
- `Content-Type: application/x-www-form-urlencoded`: uses the form-data reader.
- `Content-Type: multipart/form-data`: uses the appropriate multipart reader.

If no reader supports the data-type/media-type pair, Spring may report an unsupported media type error or fail to read the body. Do not fix it by parsing strings arbitrarily yourself; check the exact `Content-Type`, codec dependencies, and parameter types.

### 4.3. Reader configuration and memory limits

`ServerCodecConfigurer` lets you add readers, writers, and customize default codecs. Some decoders/readers buffer part or all of the body to construct a single object. Cases that usually require attention:

- `@RequestBody byte[]` or a single JSON object.
- URL-encoded forms converted into a map.
- Map-like multipart that needs to collect parts.
- Streams that must buffer each object before decoding.

Spring enforces memory limits on some codecs through `maxInMemorySize`. The limit applies according to how the codec buffers: for a body aggregated into one object, it can limit the entire part that must be aggregated; for streams, it can apply per split object. Do not raise the limit just to hide clients sending oversized payloads; choose streaming types and appropriate limits.

## 5. The body is usually a one-time stream: avoid reading or subscribing twice

The HTTP request body is a byte stream whose lifecycle is tied to the request. Do not assume the raw body can be read multiple times:

~~~java
@PostMapping("/bad")
public Mono<String> bad(@RequestBody Mono<CreateOrder> body) {
    Mono<CreateOrder> first = body;
    Mono<CreateOrder> second = body;

    // Two branches may attempt to consume the same request body.
    return first.flatMap(a ->
        second.map(b -> a.name() + b.name()));
}
~~~

The snippet above is not a safe way to share a body. Two subscriptions to the same body publisher can violate the single-read assumption, causing errors or unexpected behavior depending on the resolver/reader. Subscribe once and share the **decoded value** within the same pipeline:

~~~java
@PostMapping("/good")
public Mono<String> good(@RequestBody Mono<CreateOrder> body) {
    return body.map(order ->
        order.name() + ":" + order.quantity());
}
~~~

If you genuinely need to use the data in multiple branches, decode once and then use that value inside the same `flatMap`/`zipWhen`, or cache intentionally with a memory limit and short lifetime. Do not cache an entire large body stream without a policy.

### 5.1. Form data and multipart have their own caching APIs

`ServerWebExchange.getFormData()` reads and caches parsed form data so multiple components can access the same result. `getMultipartData()` also provides map-like multipart access and caches the parsed result. However, after using these APIs, **the original raw request body can no longer be read again** arbitrarily. Be consistent: if you already used a cached form/multipart API, continue using that API instead of reading the raw body again.

When handling streaming multipart with `Flux<PartEvent>`, the content of each part must be consumed, forwarded, or released properly. Ignoring DataBuffers without releasing them can cause memory leaks on servers using buffer pools.

## 6. When does the framework write the response body?

After the handler/controller returns a value, Spring decides how to handle the return value. With `@ResponseBody` or `@RestController`, data is encoded via `HttpMessageWriter`. `ResponseEntity` adds status and headers; WebFlux.fn uses `ServerResponse` and `BodyInserter`.

### 6.1. Response-writing chain

~~~text
Controller returns Object / Mono<T> / Flux<T>
                 |
                 v
HandlerResultHandler selects how to process the return value
                 |
                 v
Determine body type + Content-Type/Accept
                 |
                 v
Select matching HttpMessageWriter
                 |
                 v
Framework subscribes to the response Publisher
                 |
                 v
Encoder converts objects into DataBuffers/bytes
                 |
                 v
HTTP server writes bytes and commits response
                 |
                 v
Complete, error, or client cancel
~~~

With `Mono<T>` or `Flux<T>`, the framework does not need `subscribe()` to be called inside the controller. It creates the response-writing chain and manages the subscription at the server layer. The Publisher returned from the controller is part of that pipeline.

### 6.2. `@RestController` and `@ResponseBody`

`@RestController` is an annotation combining `@Controller` and `@ResponseBody`. Return values are written to the HTTP body via `HttpMessageWriter`:

~~~java
@GetMapping("/account")
public Mono<Account> account() {
    return accountService.findCurrent();
}
~~~

The controller returns a Publisher. When the framework handles the result and subscribes to the response-writing pipeline, `accountService.findCurrent()` is consumed in the way its Publisher was designed. The writer picks the corresponding codec, for example Jackson JSON when the media type matches.

### 6.3. Functional endpoints have the same reactive lifecycle

With WebFlux.fn:

~~~java
public Mono<ServerResponse> create(ServerRequest request) {
    Mono<CreateOrder> order = request.bodyToMono(CreateOrder.class);

    return order.flatMap(service::save)
        .flatMap(saved ->
            ServerResponse.ok()
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(saved));
}
~~~

`request.bodyToMono` creates a Publisher that reads the body. Reading occurs when the Publisher is subscribed to in the processing chain. `Mono<ServerResponse>` is a response created asynchronously; the framework executes the handler and writes the response through the same reactive infrastructure.

If the save operation returns `Mono<Void>`, you can use `ServerResponse.ok().build(savePublisher)` so the response only completes after the save Publisher finishes. This is how you compose work into the response lifecycle instead of calling `savePublisher.subscribe()` separately.

## 7. `HttpMessageWriter`, media types, and flush timing

`HttpMessageWriter` chooses how to encode the body based on the element type and media type. **A `Flux<T>` does not automatically mean the HTTP client receives each item immediately.** How it is written also depends on the codec and response format.

### 7.1. `application/json`: a JSON array may be aggregated

With the default Jackson JSON encoder, a multi-element Publisher with media type `application/json` is typically collected into a collection and serialized as a single JSON array:

~~~java
@GetMapping(value = "/items", produces = MediaType.APPLICATION_JSON_VALUE)
public Flux<Item> items() {
    return Flux.just(
        new Item(1, "A"),
        new Item(2, "B"),
        new Item(3, "C")
    );
}
~~~

The HTTP body looks like:

~~~json
[
  {"id":1,"name":"A"},
  {"id":2,"name":"B"},
  {"id":3,"name":"C"}
]
~~~

Even though the source is `Flux<Item>`, the default writer may need to collect the values before serializing the JSON array. Therefore, do not assume `application/json` will flush each item as soon as the source emits it.

In return, if the writer must wait for all data and serialize it into an array, an error occurring while the source emits/encodes before writing can still be handled before the response commits. However, aggregation increases memory with element count. Bound the data size.

### 7.2. NDJSON: encode and write line by line

With `application/x-ndjson`, each element is encoded as a JSON object on one line:

~~~java
@GetMapping(value = "/events", produces = MediaType.APPLICATION_NDJSON_VALUE)
public Flux<Event> events() {
    return Flux.just(
        new Event(1, "created"),
        new Event(2, "updated"),
        new Event(3, "closed")
    );
}
~~~

Body format:

~~~text
{"id":1,"type":"created"}
{"id":2,"type":"updated"}
{"id":3,"type":"closed"}
~~~

Streaming media types let the encoder write and flush each value. The client can start processing the first line while the server is still producing the next line. This is a good fit for event streams or large batches that need item-by-item processing.

### 7.3. Server-Sent Events (SSE)

With `text/event-stream`, Spring can write each `ServerSentEvent<T>` and flush the event so the client receives it without waiting for the entire stream:

~~~java
@GetMapping(value = "/notifications", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
public Flux<ServerSentEvent<String>> notifications() {
    return Flux.interval(Duration.ofSeconds(1))
        .map(index -> ServerSentEvent.<String>builder()
            .id(Long.toString(index))
            .event("tick")
            .data("message-" + index)
            .build());
}
~~~

SSE fits server-to-client event streams. An infinite stream does not complete on its own; it needs cancellation, timeouts, or a clear lifecycle. For long-lived connections, heartbeats can help detect client disconnects earlier.

### 7.4. Comparing writing styles

| Media type | Typical writing behavior | Consequence |
| --- | --- | --- |
| `application/json` with one object/Mono | Encodes one object | Single body |
| `application/json` with a multi-element Flux | Default Jackson aggregates then serializes an array | May need memory for the entire collection |
| `application/x-ndjson` | Encodes, writes, and flushes each item | Fits line-by-line data streams |
| `text/event-stream` | Writes and flushes each SSE event | Fits long-lived event connections |

If the client needs to see each item early, choose an appropriate streaming media type and also test proxies/gateways because some intermediate layers may buffer responses.

## 8. When are status/headers decided and when is the response committed?

An HTTP response has parts: status, headers, and body. Spring needs to know the status/headers before or as it begins writing the body. Once a response is **committed**, status and headers can no longer be changed; body bytes already sent cannot be recalled either.

There are three common cases with `ResponseEntity`:

| Return type | When status/headers are determined | When the body has data |
| --- | --- | --- |
| `ResponseEntity<T>` | When the method returns the entity synchronously | Body is already present |
| `ResponseEntity<Mono<T>>` / `ResponseEntity<Flux<T>>` | Available immediately from the entity | Body is supplied asynchronously later |
| `Mono<ResponseEntity<T>>` | When the Mono produces the ResponseEntity | Body/metadata are determined at the same time |
| `Mono<ResponseEntity<Flux<T>>>` | When the Mono produces the outer entity | Body Flux continues running afterward |

Example:

~~~java
@GetMapping("/accepted")
public ResponseEntity<Mono<String>> accepted() {
    Mono<String> body = service.loadMessage();
    return ResponseEntity.accepted().body(body);
}
~~~

Status 202 and headers are known as soon as the entity is returned; the body is still subscribed to and written afterward.

If the status needs to depend on an asynchronous result:

~~~java
@GetMapping("/conditional")
public Mono<ResponseEntity<String>> conditional() {
    return service.findMessage()
        .map(value -> ResponseEntity.ok(value))
        .defaultIfEmpty(ResponseEntity.notFound().build());
}
~~~

Here it must wait for the service's Publisher to emit a value or complete empty before knowing whether to build a 200 or 404 response.

### 8.1. After commit, the response cannot be replaced with another error JSON

Suppose an NDJSON stream has already sent two lines and the third element causes an encoding error. The first two lines may already have reached the client and the response is committed. The exception handler cannot change the status from 200 to 500 and send a replacement JSON error body for the whole response.

For streaming protocols, design an appropriate way to represent errors if needed (for example an error event in the stream contract before terminating). If the response is already committed, the application must not pretend it can send a new HTTP response.

## 9. Backpressure and cancellation affect read/write timing

### 9.1. Request body: reading on demand

A `Flux<T>` from the request body can be consumed according to downstream demand. Example:

~~~java
@PostMapping("/count")
public Mono<Long> count(@RequestBody Flux<Row> rows) {
    return rows
        .limitRate(32)
        .count();
}
~~~

`limitRate` regulates the pace of requests through the pipeline; the reader does not need to build the entire list in RAM before downstream processes it. However, individual codecs may buffer bytes to complete an object before emitting. Backpressure does not mean every byte is processed immediately, nor does it eliminate decoder memory limits.

### 9.2. Response body: the server's subscriber throttles the source

When a writer writes a `Flux<T>`, demand from the response-writing side can propagate back to the source Publisher. This prevents the source from necessarily emitting all data faster than the write rate. Operators with prefetch or buffers can still hold a certain amount of data; evaluate the whole pipeline.

### 9.3. Client disconnect and cancellation

If the client closes the connection while the server is streaming, the server can cancel the downstream subscription. Cancellation typically propagates back to the source and reactive operators to stop producing more data where possible.

Attach cleanup to the lifecycle:

~~~java
@GetMapping("/stream")
public Flux<String> stream() {
    return Flux.interval(Duration.ofMillis(250))
        .map(index -> "item-" + index)
        .doFinally(signal ->
            System.out.println("stream ended: " + signal));
}
~~~

`doFinally` observes complete, error, and cancel paths. If the source manages resources such as files, sockets, or database cursors, use reactive resource-management mechanisms such as `using`/`usingWhen` or the driver's API to release at the right time.

Cancellation does not guarantee that an external operation that has already started will be rolled back or stopped immediately. For example, if a downstream server has already received a write request, the client disconnecting does not automatically reverse the transaction.

## 10. Complete Spring Boot 3.5.7 + Java 17 program

This program illustrates four cases:

1. `@RequestBody Mono<CreateRequest>`: the controller is invoked before the body is decoded; the body is subscribed to in the response chain.
2. `@RequestBody CreateRequest`: the framework resolves the body before invoking the controller.
3. `@RequestBody Flux<CreateRequest>`: receives an NDJSON body item by item and aggregates the count.
4. `Flux<StreamItem>` returning NDJSON: the framework subscribes to write the response line by line.

Project structure:

~~~text
webflux-body-lifecycle/
├── pom.xml
└── src/main/java/example/webflux/
    ├── BodyLifecycleApplication.java
    ├── RequestLifecycleFilter.java
    └── BodyLifecycleController.java
~~~

### 10.1. `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>webflux-body-lifecycle</artifactId>
    <version>1.0.0</version>

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

### 10.2. `BodyLifecycleApplication.java`

~~~java
package example.webflux;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BodyLifecycleApplication {

    public static void main(String[] args) {
        SpringApplication.run(BodyLifecycleApplication.class, args);
    }
}
~~~

### 10.3. `RequestLifecycleFilter.java`

~~~java
package example.webflux;

import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;

import reactor.core.publisher.Mono;

@Component
@Order(0)
public class RequestLifecycleFilter implements WebFilter {

    @Override
    public Mono<Void> filter(
        ServerWebExchange exchange,
        WebFilterChain chain
    ) {
        String path = exchange.getRequest().getPath().value();

        System.out.println("[" + path + "] exchange started");

        return chain.filter(exchange)
            .doFinally(signal ->
                System.out.println(
                    "[" + path + "] exchange finished: " + signal));
    }
}
~~~

The filter does not subscribe itself. It returns the Publisher of `chain.filter(exchange)` and only observes when the HTTP chain completes or is cancelled. Therefore, the final filter log helps observe the entire request/response lifecycle at the WebFlux layer.

### 10.4. `BodyLifecycleController.java`

~~~java
package example.webflux;

import java.time.Duration;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api")
public class BodyLifecycleController {

    public record CreateRequest(String name, int quantity) {}

    public record Receipt(String id, String name, int quantity) {}

    public record ImportSummary(long received) {}

    public record StreamItem(long sequence, String value) {}

    @PostMapping(
        path = "/echo",
        consumes = MediaType.APPLICATION_JSON_VALUE,
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    public Mono<Receipt> echo(
        @RequestBody Mono<CreateRequest> body
    ) {
        log("/echo controller invoked; body Publisher prepared");

        return body
            .doOnSubscribe(subscription ->
                log("/echo request body subscribed"))
            .doOnNext(request ->
                log("/echo decoded request: " + request.name()))
            .map(this::toReceipt)
            .doOnSubscribe(subscription ->
                log("/echo response Publisher subscribed"));
    }

    @PostMapping(
        path = "/eager",
        consumes = MediaType.APPLICATION_JSON_VALUE,
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    public Mono<Receipt> eager(
        @RequestBody CreateRequest request
    ) {
        log("/eager controller invoked after body argument resolved");

        return Mono.fromSupplier(() -> toReceipt(request))
            .doOnSubscribe(subscription ->
                log("/eager response Publisher subscribed"));
    }

    @PostMapping(
        path = "/bulk",
        consumes = MediaType.APPLICATION_NDJSON_VALUE,
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    public Mono<ImportSummary> bulk(
        @RequestBody Flux<CreateRequest> body
    ) {
        log("/bulk controller invoked; body Flux prepared");

        return body
            .doOnSubscribe(subscription ->
                log("/bulk request Flux subscribed"))
            .doOnNext(request ->
                log("/bulk decoded: " + request.name()))
            .count()
            .map(ImportSummary::new)
            .doOnSubscribe(subscription ->
                log("/bulk response Publisher subscribed"));
    }

    @GetMapping(
        path = "/stream",
        produces = MediaType.APPLICATION_NDJSON_VALUE
    )
    public Flux<StreamItem> stream() {
        log("/stream controller invoked; response Flux prepared");

        return Flux.interval(Duration.ofMillis(250))
            .take(3)
            .map(index -> new StreamItem(
                index + 1,
                "item-" + (index + 1)))
            .doOnSubscribe(subscription ->
                log("/stream response Flux subscribed"))
            .doOnNext(item ->
                log("/stream response item ready: " + item.sequence()));
    }

    private Receipt toReceipt(CreateRequest request) {
        return new Receipt(
            "R-" + request.name(),
            request.name(),
            request.quantity()
        );
    }

    private static void log(String message) {
        System.out.println(message);
    }
}
~~~

### 10.5. Running the application

Requires JDK 17+ and Maven. From the directory containing `pom.xml`:

~~~bash
mvn spring-boot:run
~~~

Try the request using a reactive body:

~~~bash
curl -i -X POST http://localhost:8080/api/echo \
  -H "Content-Type: application/json" \
  -d '{"name":"pen","quantity":2}'
~~~

Expected response body:

~~~json
{"id":"R-pen","name":"pen","quantity":2}
~~~

Expected log in logical order:

~~~text
[/api/echo] exchange started
/api/echo controller invoked; body Publisher prepared
/api/echo response Publisher subscribed
/api/echo request body subscribed
/api/echo decoded request: pen
[/api/echo] exchange finished: onComplete
~~~

Point to observe: the controller is invoked and returns the Publisher before `request body subscribed`. When the framework subscribes to the response chain to write the response, the subscription enters `body` and the reader starts decoding the request. Log timing may interleave with other server logs; do not rely on ordering across independent requests.

Try the non-reactive parameter:

~~~bash
curl -i -X POST http://localhost:8080/api/eager \
  -H "Content-Type: application/json" \
  -d '{"name":"book","quantity":1}'
~~~

Expected response body:

~~~json
{"id":"R-book","name":"book","quantity":1}
~~~

Relevant log:

~~~text
[/api/eager] exchange started
/eager controller invoked after body argument resolved
/eager response Publisher subscribed
[/api/eager] exchange finished: onComplete
~~~

In this endpoint, Spring resolved `CreateRequest` before invoking the controller. `Mono.fromSupplier` still executes when the response Publisher is subscribed to.

Try the NDJSON streaming request:

~~~bash
curl -i -X POST http://localhost:8080/api/bulk \
  -H "Content-Type: application/x-ndjson" \
  --data-binary $'{"name":"pen","quantity":1}\n{"name":"book","quantity":2}\n'
~~~

Expected response body:

~~~json
{"received":2}
~~~

The request body is decoded into `CreateRequest` elements. The `count` operator requires consuming the entire stream before producing `ImportSummary`.

Try the streaming response:

~~~bash
curl -N http://localhost:8080/api/stream
~~~

Expected body (one object per line, roughly 250 ms apart):

~~~text
{"sequence":1,"value":"item-1"}
{"sequence":2,"value":"item-2"}
{"sequence":3,"value":"item-3"}
~~~

In this endpoint, the response Publisher is subscribed to when the framework begins writing the body. NDJSON lets the writer encode/flush each item; the filter only logs "exchange finished" after the response-writing pipeline completes.

**Note on logs:** the application's log lines illustrate the subscription and decoding points. When the first byte is pushed down to the socket depends on the server, codecs, buffering, network, and client; it cannot be inferred accurately from the timing of the controller's `doOnNext` alone.

## 11. Testing the lifecycle with WebTestClient

In a real project, add the `spring-boot-starter-test` dependency in the test scope and write integration tests:

~~~java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class BodyLifecycleIntegrationTest {

    @Autowired
    WebTestClient client;

    @Test
    void reactiveBodyIsDecodedAndWritten() {
        client.post()
            .uri("/api/echo")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(new BodyLifecycleController.CreateRequest("pen", 2))
            .exchange()
            .expectStatus().isOk()
            .expectHeader().contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
            .expectBody()
            .jsonPath("$.id").isEqualTo("R-pen")
            .jsonPath("$.quantity").isEqualTo(2);
    }

    @Test
    void streamingResponseContainsThreeItems() {
        client.get()
            .uri("/api/stream")
            .accept(MediaType.APPLICATION_NDJSON)
            .exchange()
            .expectStatus().isOk()
            .expectHeader().contentTypeCompatibleWith(MediaType.APPLICATION_NDJSON)
            .expectBody(String.class)
            .value(body -> {
                org.junit.jupiter.api.Assertions.assertTrue(
                    body.contains("\"sequence\":1"));
                org.junit.jupiter.api.Assertions.assertTrue(
                    body.contains("\"sequence\":3"));
            });
    }
}
~~~

This is an illustrative test snippet; the corresponding JUnit, Spring Boot Test, and WebTestClient imports are needed. The response stream test here checks the final content, not the flush timing of individual lines. To test real streaming, you need a client that reads individual chunks/events and measures arrival times with reasonable tolerances, avoiding overly tight timing-dependent assertions.

Lifecycle tests should include:

- Valid and invalid JSON bodies.
- Empty body when the endpoint requires data.
- Multi-element bodies, verifying no items are dropped.
- Client cancelling midway while sending/receiving a stream.
- Source failing before response commit and source failing after part of the response has been sent.
- Large payloads exceeding codec limits.
- Two concurrent requests, ensuring data and log correlation do not mix.

## 12. Common mistakes and how to fix them

**Mistake 1 — Thinking creating a `Mono` means the body has been read.** Assembly only creates the Publisher. The body is consumed when the reader is subscribed to.

**Mistake 2 — Thinking a controller receiving `Mono<T>` means the method waits for the body before running.** The method can receive the Publisher first; the body is read when subscription reaches that Publisher. If you need the object before the method runs, declare a non-reactive object parameter and understand that Spring must resolve the body before invoking the method.

**Mistake 3 — The controller receives a body Publisher but ignores it.** No operator in the returned chain consumes the body. Compose the Publisher into the response pipeline or design an explicit processing flow.

**Mistake 4 — Calling `body.subscribe()` manually in a controller.** Creates a subscription outside the HTTP lifecycle, easily causing the response to return before processing finishes and detaching errors/cancel.

**Mistake 5 — Calling `block()` to wait for the body.** Blocks a non-blocking thread. Use `flatMap`/`map`/`then` to compose Publishers.

**Mistake 6 — Subscribing twice to the raw request body.** The body is usually a one-time stream. Decode once and share the decoded value within the same pipeline if needed.

**Mistake 7 — Thinking every `Flux<T>` response flushes item by item.** `application/json` with default Jackson may aggregate into a JSON array. Use NDJSON/SSE or an appropriate streaming media type if item-by-item writing is needed.

**Mistake 8 — Using NDJSON while the client sends `application/json`.** The reader is chosen by Content-Type and codec. Declare matching media types on both client and controller.

**Mistake 9 — Thinking `onNext` in the controller means the client has received the bytes.** The item still has to go through the encoder, writer, server, network, and client buffers.

**Mistake 10 — Trying to change status/body after the response is committed.** Status and headers cannot be changed after bytes have been sent. For streams, design an error event or close the connection per policy.

**Mistake 11 — Collecting a large stream into `collectList()` or `byte[]` without limits.** Can grow memory with the size of the entire body. Choose streaming, payload limits, and codec configuration.

**Mistake 12 — Reading the raw body in a filter and then reading it again in the controller.** The body has already been consumed. Use the appropriate form/multipart caching API or design a single read.

**Mistake 13 — Ignoring DataBuffer/PartEvent content.** Pooled buffers must be released or relayed/consumed properly. Prefer high-level codecs unless manual byte handling is genuinely required.

**Mistake 14 — Assuming client cancel always rolls back the operation.** Cancel stops the reactive stream when possible; it does not undo side effects that already happened on the server or in external services.

**Mistake 15 — Using `doOnNext` to measure when the response has finished sending.** That callback sits upstream of the writer. Observe the full chain with a filter's `doFinally`, yet even when the server finishes writing, that is not a business acknowledgement from the client.

**Mistake 16 — Using streaming without considering proxy buffering.** The server may flush item by item while a reverse proxy or client library still buffers. Test the entire path with a client that truly reads streaming responses.

**Mistake 17 — Confusing the request publisher and the response publisher.** The request body Publisher is produced by `HttpMessageReader`; the response body Publisher is consumed by `HttpMessageWriter`. They are two different directions of the same request lifecycle.

## 13. Self-check exercises

1. With `@RequestBody Order order`, does Spring need to read the body before invoking the controller? **Yes**, because the method needs the resolved object.
2. With `@RequestBody Mono<Order> order`, can the method be invoked before body decoding completes? **Yes**; the method receives the Publisher and the body is consumed when the Publisher is subscribed to.
3. Who subscribes to the response Publisher in a typical WebFlux controller? **The framework in the response-writing pipeline**, not the controller calling `subscribe()` itself.
4. What do `HttpMessageReader` and `HttpMessageWriter` do? **The reader decodes the HTTP body into objects; the writer encodes objects into the HTTP body.**
5. Does `Flux<Event>` guarantee the entire body is buffered before processing? **No**; it can be processed streaming according to demand and codec capability.
6. Does returning `Flux<Item>` with `application/json` always flush item by item? **No**; default Jackson JSON may aggregate into an array before serializing.
7. Which media type is commonly suitable for streaming individual JSON objects line by line? **`application/x-ndjson`.**
8. Once the response is committed, can an exception handler change the status from 200 to 500? **No.**
9. What signal can a client disconnect during a stream send upstream? **Cancellation.**
10. Should you read the raw body in a filter and then also use `@RequestBody` in a controller? **No**, unless a valid cache/replay mechanism has been designed.
11. Why does `doOnNext` not prove the client received the data? **The item still has to go through the encoder, writer, server, network, and client buffers.**
12. When should you use `getFormData()` instead of reading the raw body? **When you need map-like form data and want to use the parsed/cached result via ServerWebExchange.**
13. Why should you not collect a large file upload into a `byte[]`? **It wastes memory and loses streaming/backpressure benefits.**
14. If the HTTP status needs to depend on an asynchronous service result, do you choose `ResponseEntity<Flux<T>>` or `Mono<ResponseEntity<T>>`? **`Mono<ResponseEntity<T>>` when status/headers depend on the Mono result before the response is created.**

## 14. Key takeaways and official documentation

- **Creating a Publisher ≠ reading the body.** Assembly creates the processing description; subscription triggers consumption.
- **`@RequestBody T`**: Spring resolves the object before invoking the method.
- **`@RequestBody Mono<T>/Flux<T>`**: the controller receives a Publisher; the body is read when subscription reaches that Publisher.
- **Reading the body:** `HttpMessageReader` + decoder + `DataBuffer`.
- **Writing the body:** `HttpMessageWriter` + encoder + response Publisher.
- **The framework manages the subscription** of request/response; the controller returns a Publisher, and does not subscribe/block itself.
- **Flux does not guarantee item-by-item flushing on its own.** Media type and writer decide aggregation vs streaming.
- **Response commit is an important boundary.** After commit, already-sent status/headers/body cannot be changed.
- **Backpressure and cancellation** affect reading/writing; resource cleanup must be tied to the lifecycle.

Official documentation for cross-checking:

1. [Spring Framework — @RequestBody in WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/requestbody.html): resolving request bodies, reactive arguments, validation, and HttpMessageReader.
2. [Spring Framework — @ResponseBody in WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/responsebody.html): reactive return values and HttpMessageWriter.
3. [Spring Framework — Reactive Core](https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html): HttpHandler, WebHandler, codecs, DataBuffer, JSON streaming, form/multipart caching, and buffer limits.
4. [Spring Framework — Functional Endpoints](https://docs.spring.io/spring-framework/reference/web/webflux-functional.html): ServerRequest.bodyToMono/bodyToFlux, ServerResponse, and composing a body Publisher into the response.
5. [Spring Framework — ResponseEntity](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/responseentity.html): when status/headers are determined compared to a reactive body.
6. [Spring Framework — HTTP Message Codecs](https://docs.spring.io/spring-framework/reference/web/webflux/config.html): configuring ServerCodecConfigurer and codec memory limits.
