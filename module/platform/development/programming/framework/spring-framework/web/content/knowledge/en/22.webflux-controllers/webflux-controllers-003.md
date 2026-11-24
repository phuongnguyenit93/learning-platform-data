# @RequestBody with Mono/Flux and Reactive Responses via ResponseEntity in Spring WebFlux

## 1. Real-World Problem and Objectives

A Spring WebFlux HTTP API often needs to accept JSON from a client, process it asynchronously, and then decide the HTTP status, headers, and body. Three questions are easily confused:

1. How does `@RequestBody Mono<NewOrder>` differ from `@RequestBody NewOrder` in how the body is read and processed?
2. Does `@RequestBody Flux<Event>` mean "read an entire JSON array" or "process each record in a stream"?
3. How do `ResponseEntity<Mono<Order>>`, `Mono<ResponseEntity<Order>>`, and `ResponseEntity<Flux<Order>>` differ in **when HTTP status/headers are known**, body writing, streaming, and error handling?

If you only see `Mono` or `Flux` and conclude that every operation is non-blocking, the API easily runs into bugs: blocking the event loop, returning HTTP 200 before knowing whether a resource exists, decoding the wrong Content-Type, writing the response after headers have committed, or holding too much data in RAM.

**Scope:** Annotated controllers in **Spring WebFlux 6.1.x**, **Java 17**, and **Spring Boot 3.3.5**. This article belongs to **WebFlux Controllers**, not Servlet Spring MVC. It uses `org.springframework.web.bind.annotation` for `@RequestBody`, Reactor `reactor.core.publisher.Mono`/`Flux`, `ResponseEntity` from Spring HTTP, WebFlux HTTP codecs, and `WebTestClient`.

### Learning Outcomes

After this lesson, you will be able to:

- Read reactive request bodies with `@RequestBody Mono<T>`/`Flux<T>` and know when to use a direct DTO.
- Understand the role of `HttpMessageReader`, the Jackson decoder, `DataBuffer`, backpressure, and one-shot request bodies.
- Distinguish `application/json`, `application/x-ndjson`, and JSON streaming conventions.
- Choose the right response type among `ResponseEntity<T>`, `Mono<T>`, `ResponseEntity<Mono<T>>`, `ResponseEntity<Flux<T>>`, `Mono<ResponseEntity<T>>`, and `Mono<ResponseEntity<Flux<T>>>`.
- Produce HTTP 201 + `Location` after saving succeeds, or return 404 properly when not found.
- Use `@Valid` with reactive bodies and recognize `WebExchangeBindException`.
- Avoid accidentally swallowing errors with `onErrorResume`, producing incorrect HTTP 4xx/5xx responses, or leaking data.
- Build a Boot WebFlux application with JSON POST, NDJSON batch input, dynamic status, and reactive output, along with WebTestClient tests.
- Identify boundaries around cancellation, buffering, timeouts, streaming response commits, Spring Security, and persistence.

## 2. The Two Data Directions of an HTTP Exchange

An endpoint has two independent yet coordinated pipelines:

```text
HTTP request bytes
       |
       v
Reactive HTTP server adapter (Reactor Netty...)
       |
       v
ServerHttpRequest.getBody() : Flux<DataBuffer>
       |
       v
HttpMessageReader + Decoder (e.g., Jackson JSON)
       |
       +--> @RequestBody Mono<DTO> (0..1 DTO)
       |
       +--> @RequestBody Flux<DTO> (0..N DTOs)
       |
       v
Controller -> service -> Mono/Flux result
       |
       v
HandlerResultHandler / HttpMessageWriter + Encoder
       |
       v
ServerHttpResponse headers/status + body publisher
       |
       v
HTTP client
```

`@RequestBody` does not read bytes via `InputStream`/`HttpServletRequest` as in Servlet MVC. WebFlux receives the body as a `Publisher<DataBuffer>` and decodes it through the `HttpMessageReader` matching the Content-Type.

Key points:

- **The request body** belongs to the HTTP exchange and is normally consumed **once**. Do not subscribe to `exchange.getRequest().getBody()` in a filter and expect the controller to read it again.
- **`Mono<T>`** emits at most one element, and can complete empty or with an error.
- **`Flux<T>`** emits 0 to many elements, and may complete or run long depending on the source.
- **Reactive I/O** means composing publishers/demand/cancellation properly, not merely changing Java type names.
- When returning a response, the status/headers and the body publisher can be decided at different times. This is why there are multiple forms of `ResponseEntity` wrapping publishers.

## 3. @RequestBody Direct DTO, Mono<T>, Flux<T>

### 3.1. Direct DTO

```java
@PostMapping("/items")
public Mono<Item> create(@RequestBody NewItem input) {
    return store.create(input);
}
```

This is a snippet; `Item`/`NewItem`/`store` will be defined completely in the project below. With a direct `NewItem` parameter, WebFlux must decode the body before invoking the controller method. A reactive return type can still be used for subsequent processing.

This style is convenient for small single-object requests needing annotated-controller binding/validation. It does **not** turn the entire body read into "blocking" I/O. The WebFlux codec still reads the request reactively; method argument resolution supplies the DTO once decoded.

### 3.2. @RequestBody Mono<T>

```java
@PostMapping("/items")
public Mono<Item> create(
        @RequestBody Mono<NewItem> incoming) {
    return incoming.flatMap(store::create);
}
```

When the controller method receives `incoming`, it is a `Mono<NewItem>` describing the body decoding. The method actively chains steps using `map`/`flatMap` and **returns the publisher for the framework to subscribe to**.

- `flatMap` is appropriate when `store.create` returns `Mono<Item>`.
- If `store.create` is a synchronous method returning `Item`, `map(store::createSync)` can be used, though a blocking call inside `map` can still block the event loop.
- Never call `incoming.block()` to extract `NewItem` before processing.
- Never call `incoming.subscribe()` and return a different Mono, as that can consume the body outside the HTTP request lifecycle.

`Mono<NewItem>` does not mean an extra HTTP request or a dedicated waiting thread. It simply represents the result of the decoding process.

### 3.3. @RequestBody Flux<T>

```java
@PostMapping(path = "/events",
        consumes = MediaType.APPLICATION_NDJSON_VALUE)
public Mono<Long> accept(@RequestBody Flux<Event> events) {
    return events
            .flatMap(eventStore::save)
            .count();
}
```

This is a snippet assuming `Event` and `eventStore`. NDJSON (`application/x-ndjson`) delivers **one JSON value per line**, allowing the decoder to emit elements into the Flux from the request body stream when the media type is supported.

`Flux<Event>` does not require the framework to buffer all data into a `List<Event>` before calling the handler. With an appropriate streaming Content-Type, the decoder can emit multiple `Event` items over time as data arrives. However, buffers, codecs, `flatMap` concurrency, clients/proxies, and serialization all affect actual streaming and backpressure.

**Do not treat `Flux<T>` as a guarantee that every JSON format emits objects one by one immediately.** A JSON array `[{"x":1},{"x":2}]` with `application/json` has different semantics from NDJSON lines; the decoder and content negotiation determine how elements are emitted and flushed. If the contract is NDJSON, declare the NDJSON Content-Type and test the real bytes/wire format.

## 4. application/json vs application/x-ndjson

### JSON object

```http
POST /api/items HTTP/1.1
Content-Type: application/json

{"name":"Spring Book"}
```

This is a single JSON document. `@RequestBody Mono<NewItem>` is usually the natural choice.

### JSON array

```http
POST /api/items/batch HTTP/1.1
Content-Type: application/json

[{"name":"A"},{"name":"B"}]
```

If a business operation needs the whole list or transactional validation, you can use `@RequestBody Mono<List<NewItem>>` or a wrapper DTO with a max size limit. Using Flux with a JSON array depends on codec semantics, so **do not equate it** with line-delimited streaming.

### NDJSON

```http
POST /api/items/batch HTTP/1.1
Content-Type: application/x-ndjson

{"name":"A"}
{"name":"B"}
```

NDJSON puts one JSON object per line, which is well suited to streaming and backpressure. An `application/x-ndjson` response likewise lets the server write JSON objects line by line, unlike `application/json` which is typically a single valid JSON array/document.

In Spring, `MediaType.APPLICATION_NDJSON` and `MediaType.APPLICATION_NDJSON_VALUE` represent the NDJSON media type. `application/stream+json` was historically used in the Spring ecosystem, but for new APIs prefer NDJSON when client and server agree.

### When Should You Avoid Streaming?

- You need an "all succeed or nothing" transaction.
- You need to validate the entire batch before writing data.
- You need the total record count to determine the final status.
- The client/proxy requires a single JSON document response.
- Memory bounds and complexity fit small payloads better.

When a batch has a few dozen items, decoding into a bounded list can be simpler than streaming. Streaming shines when avoiding buffering the entire payload, supporting incremental processing/cancellation, and letting the client receive elements early.

## 5. HttpMessageReader, Decoder, and Body Errors

WebFlux `@RequestBody` uses the configured `HttpMessageReader` and `Decoder` codecs; by default, Boot WebFlux uses Jackson to read JSON into records/DTOs. Based on `Content-Type`, the framework selects a reader supporting both the target type and media type.

Errors to distinguish:

| Scenario | Meaning |
| --- | --- |
| Malformed JSON | Body cannot be decoded; usually 400 |
| `Content-Type: text/plain` when handler expects JSON | May result in 415 Unsupported Media Type |
| Required body is empty | May return 400 when `@RequestBody(required=true)` applies |
| DTO missing required field per Bean Validation | 400 when `@Valid`/validation is active |
| DTO decoded but business resource does not exist | 404 per business/response mapping |
| Body too large | May hit codec buffer limit or a 413 policy |
| Client disconnects | Cancellation/network errors; does not necessarily produce a JSON response |
| Decoder hits an error mid-NDJSON stream | Publisher emits an error and may stop reading remaining parts |

Do not assume a single exact exception class for every decode error; `ServerWebInputException` and its subclasses or converter exceptions may occur depending on Spring configuration. Bean Validation on an annotated `@RequestBody` typically throws `WebExchangeBindException`. With method-level validation from constraints placed directly on parameters, you may see `HandlerMethodValidationException`.

## 6. Bean Validation with Mono<T>/Flux<T>

Suppose:

```java
public record NewItem(
        @NotBlank
        @Size(max = 80)
        String name) {}
```

In a WebFlux controller, you can write:

```java
@PostMapping
public Mono<ResponseEntity<Item>> create(
        @Valid @RequestBody Mono<NewItem> request) {
    return request
            .flatMap(store::create)
            .map(item -> ResponseEntity
                    .created(URI.create("/api/items/" + item.id()))
                    .body(item));
}
```

This is a snippet requiring the Java record, store, and imports, shown in full in section 13.

- `@Valid` only requests validation of the nested object's constraints; it is **not** itself a constraint like `@NotBlank`.
- With `Mono<NewItem>`, validation can emit an error **inside the Mono** once the value is decoded. Spring MVC and WebFlux argument resolution differ, so do not use Servlet MVC exception names in place of WebFlux exceptions.
- Validation errors are normally translated into **HTTP 400 Bad Request**, unless you change the mapping.
- If you place constraints directly on method parameters (e.g., `@Min` on a numeric query argument) in Spring 6.1, method validation may throw `HandlerMethodValidationException`.
- With `Flux<NewItem>`, pay attention to each element of the streaming body and the possibility of errors occurring **after the response has started**. With streaming output, there is no guarantee you can change the status to 400 once partially committed.

**Do not handle validation by calling `block()`.** If you want a custom error schema, use `@RestControllerAdvice`/`@ExceptionHandler` or error operators **inside the reactive chain** with the exact scope and exception class.

### @Valid Does Not Replace Business Validation

A non-blank name does not prove the user is authorized to create the resource, is not spamming, or has not supplied out-of-policy domain values. Authorization, idempotency, rate limits, uniqueness, input length, and SQL injection defenses must be implemented separately at service/persistence/security boundaries.

## 7. What Does ResponseEntity<T> Mean in WebFlux?

`ResponseEntity<T>` holds:
- HTTP status code.
- Headers such as `Location`, `ETag`, `Cache-Control`, `Content-Type`, `X-Request-ID`.
- Body `T` (which may be a publisher).

A `@RestController` returning a DTO directly usually implies status 200. When you need 201, 202, 204, 404, or specific headers, use `ResponseEntity`.

```java
return ResponseEntity
        .status(HttpStatus.CREATED)
        .location(URI.create("/api/items/42"))
        .body(new Item(42, "Java"));
```

This is a snippet assuming `Item` is already defined. It sets the status and headers before the body is serialized.

In WebFlux, `ResponseEntity` can wrap publishers; **whether Mono/Flux sits inside or outside ResponseEntity determines when the status and headers are known**.

## 8. The Four Most Important Reactive ResponseEntity Patterns

### 8.1. ResponseEntity<Mono<T>>

```java
public ResponseEntity<Mono<Item>> accepted() {
    Mono<Item> body = service.computeLater();
    return ResponseEntity.accepted()
            .header("X-Mode", "body-later")
            .body(body);
}
```

This snippet is not runnable because `service` is hypothetical. When the method returns, **status 202 and X-Mode are already determined**. `body` remains a publisher that can emit an item or an error later.

Appropriate when:
- The HTTP status/headers are known immediately when building the response.
- The body result may become available later.
- The body has at most one element.

**Important pitfall:** If `body` completes empty, the initial status remains 202; it does not automatically become 404. If you need 404 when a resource is absent, wait for the lookup and return `Mono<ResponseEntity<Item>>`.

### 8.2. ResponseEntity<Flux<T>>

```java
public ResponseEntity<Flux<Item>> stream() {
    Flux<Item> body = service.streamItems();
    return ResponseEntity.ok()
            .contentType(MediaType.APPLICATION_NDJSON)
            .body(body);
}
```

Status 200 and Content-Type are chosen **up front**, and the body emits multiple items afterward. With NDJSON, the client can receive individual JSON lines as the body publisher emits them, subject to buffering/transport.

When a normal JSON array is needed, `ResponseEntity<Flux<Item>>` + `application/json` can still be used. The codec serializes the Flux into an array and flushes differently from NDJSON. Never assume that using `Flux` guarantees each item becomes a separate HTTP chunk; chunk boundaries are not record boundaries.

### 8.3. Mono<ResponseEntity<T>>

```java
public Mono<ResponseEntity<Item>> find(long id) {
    return repository.find(id)
            .map(ResponseEntity::ok)
            .defaultIfEmpty(ResponseEntity.notFound().build());
}
```

This is a snippet where `repository.find(id)` returns `Mono<Item>`. **The ResponseEntity is constructed after the lookup completes**:

- Item present → HTTP 200 and JSON body.
- Empty → HTTP 404 with no body.

Here, the HTTP status **depends** on the asynchronous result. This is usually the right choice for single-resource GETs, lookup/permission decisions, resource creation that can fail, conditional responses, and business conflicts.

### 8.4. Mono<ResponseEntity<Flux<T>>>

```java
public Mono<ResponseEntity<Flux<Item>>> export() {
    return permissionService.check()
            .map(allowed -> {
                if (!allowed) {
                    return ResponseEntity
                            .status(HttpStatus.FORBIDDEN)
                            .<Flux<Item>>build();
                }
                return ResponseEntity.ok()
                        .contentType(MediaType.APPLICATION_NDJSON)
                        .body(service.streamItems());
            });
}
```

Snippet with hypothetical `permissionService`/`service`. **Two asynchronous stages:**
1. The outer Mono determines status/headers after an async check.
2. The inner Flux supplies the body once the response is selected.

Appropriate when **permissions/status/headers depend on async I/O**, while the payload is a multi-element stream. Never replace real Spring Security/service authorization with a merely illustrative check.

### Summary Table

| Return type | When are status/headers known? | Body | Use when |
| --- | --- | --- | --- |
| `ResponseEntity<T>` | Immediately on return | One object/value | Result and status are already ready |
| `Mono<T>` | Typically default 200 response, unless handled otherwise | 0..1 value | No conditional status/headers needed |
| `Flux<T>` | Typically default 200 response, unless handled otherwise | 0..N values | Collection/stream |
| `ResponseEntity<Mono<T>>` | **Before the body Mono emits** | 0..1 reactive | Status/headers known early |
| `ResponseEntity<Flux<T>>` | **Before the body Flux emits** | 0..N reactive | Status/headers known early, stream/list |
| `Mono<ResponseEntity<T>>` | **After the outer Mono emits** | One DTO or empty | Status depends on lookup/async result |
| `Mono<ResponseEntity<Flux<T>>>` | **After outer Mono, before body Flux** | Stream after auth/status decision | Async envelope decision, streaming body |

**Note:** "status known early" refers to when the software has **selected the status/headers**, not a guarantee that header bytes are already written to the socket the instant the Java method returns. The HTTP response typically commits only when the body writes/completes; exact timing depends on server, codec, and flow.

## 9. Mono.empty(), Flux.empty(), and HTTP Status

A common contract mistake:

```java
@GetMapping("/{id}")
public ResponseEntity<Mono<Item>> wrong(@PathVariable long id) {
    return ResponseEntity.ok().body(repository.find(id));
}
```

If the repository does not find the item, `Mono.empty()` does not automatically produce 404. Status 200 was already chosen immediately.

Better:

```java
@GetMapping("/{id}")
public Mono<ResponseEntity<Item>> correct(@PathVariable long id) {
    return repository.find(id)
            .map(ResponseEntity::ok)
            .defaultIfEmpty(ResponseEntity.notFound().build());
}
```

Similarly:
- `Flux.empty()` + 200 is an empty list response, usually valid.
- `Mono.empty()` + 204 can fit a bodyless action, yet you must **explicitly** choose 204 if the contract requires it.
- `Mono.error(ex)` enters reactive error handling; the HTTP status depends on exception resolvers and response commit state.
- `onErrorReturn(defaultValue)` can mask business errors, unintentionally turning 5xx into 200 if poorly designed.

Never confuse "a Publisher emitted no elements" with "resource does not exist" or "user is unauthorized."

## 10. HTTP Status, Location, Cache-Control, and ETag

### 201 Created

When POST creates an item successfully, a REST contract typically returns:
- `201 Created`.
- `Location: /api/items/42` pointing to the new item.
- The server-created DTO body containing the server-owned ID.

With a reactive body:

```java
return body.flatMap(store::create)
        .map(created -> ResponseEntity
                .created(URI.create("/api/items/" + created.id()))
                .body(created));
```

Here Status and Location are chosen **only after the create Mono emits successfully**. If creation fails, no erroneous 201 is sent.

### 202 Accepted

`202 Accepted` indicates the request was accepted for processing but is not yet complete; if an actual background job exists, return an appropriate job ID/status URL. **Do not** return 202 simply because the body is a Mono taking a few milliseconds. A `Mono` that finishes within the same HTTP request can still return 200/201 normally.

### 204 No Content

`ResponseEntity.noContent().build()` produces 204. Per HTTP semantics, no body is sent. Never attach a `Flux<Item>` body to 204 and expect clients to read a stream.

### Cache Headers

`ResponseEntity.ok().cacheControl(CacheControl.noStore()).body(...)` is useful when the body is sensitive; cache policies apply to the response independently of Mono/Flux. If a list is user-specific, prevent public shared caches from leaking data. ETag/conditional GET requires stable values and a proper 304 status before the body commits; never compute an ETag from an incomplete stream without accounting for buffering cost.

### Response Already Committed

With NDJSON:
- Status/headers are committed when the response begins.
- The third item fails after two lines have already reached the client.
- The server is **not guaranteed** to be able to change 200 into a 500 ProblemDetail or 400 validation body.
- Clients must understand incomplete-stream/retry/idempotency policies and side-effect boundaries.

Therefore, if atomic batch validation and a final error status are required, you generally must **complete all checks before committing** rather than returning a Flux output immediately.

## 11. Reactive Streams, Backpressure, and Serialization

WebFlux uses Reactive Streams to regulate consumer demand rather than making each request thread sleep waiting on the network.

- `Mono.just(dto)` emits one item when subscribed.
- `Flux.fromIterable(items)` emits multiple items.
- `flatMap` introduces concurrency and may alter ordering; `concatMap` preserves sequential ordering.
- `collectList()` buffers the entire Flux into memory; unsuitable for infinite inputs or unbounded bodies.
- `buffer(n)` creates batches, also increasing memory usage.
- `take(n)` takes at most n items and cancels upstream once satisfied, though misuse can silently discard the rest.
- `doOnCancel`/`doFinally` support cleanup when a client disconnects or the response cancels.

**Backpressure only helps end-to-end** when the source, decoder, persistence client, and HTTP writer all respect demand. If a controller calls synchronous JDBC or builds an unbounded `Flux.create`, using Flux will not save the system from thread or memory exhaustion.

### Blocking Code Inside map/flatMap

```java
// ANTI-PATTERN: blocking JDBC on the event loop.
return incoming.map(dto ->
        jdbcRepository.save(dto));
```

In WebFlux Netty, operators may execute on the event loop. Synchronous JDBC can block the event loop, stalling many other connections.

Temporary workaround when a blocking dependency is unavoidable:

```java
return incoming.flatMap(dto ->
        Mono.fromCallable(() -> jdbcRepository.save(dto))
                .subscribeOn(Schedulers.boundedElastic()));
```

This is a snippet assuming `jdbcRepository` and `Schedulers` imports. `boundedElastic` **offloads blocking work to bounded workers**; it does not turn JDBC into a non-blocking driver. For real databases, consider R2DBC or an appropriate non-blocking client while managing transactions, pools, timeouts, and backpressure.

## 12. Designing Safe NDJSON Batches

An `@RequestBody Flux<NewItem>` can receive thousands of JSON lines. If you write:

```java
return requests.collectList()
        .flatMap(store::saveBatch);
```

without a size limit, a client can stream indefinitely and exhaust server RAM.

For an API allowing at most 100 items/batch:
- Read at most **101** entries to detect an oversized batch, then fail.
- Check constraints on every entry before writing.
- Build the result list once all entries are valid.
- Return `Mono<ResponseEntity<List<Item>>>` **after** the batch finishes.
- Use a DB transaction if the contract requires all-or-nothing.
- Enforce request byte limits and connection timeouts at the proxy/runtime because a record count limit alone does not protect against **a single huge record**.

Example:

```java
return items.take(101)
        .collectList()
        .flatMap(list -> {
            if (list.size() > 100) {
                return Mono.error(new ResponseStatusException(
                        HttpStatus.PAYLOAD_TOO_LARGE,
                        "At most 100 items"));
            }
            return store.saveBatch(list);
        });
```

This snippet returns whatever type `store.saveBatch` produces; the full project in section 13 returns `Mono<ResponseEntity<List<Item>>>`. When the source has 101 items, `take(101)` suffices to detect the overflow instead of **silently accepting** the first 100. When the source has more than 101, subscription cancels the rest per the reactive contract. For HTTP keep-alive/streaming uploads, verify the server/client connection drain/cancel policy when rejecting a request early.

**Atomicity:** `collectList()` does not create a DB transaction. If code saves items one by one and fails on the last item, earlier items may already be persisted. The demo validates before calling the service, and production systems must use a transactional database service if atomic batches are required.

## 13. Runnable Maven Project: JSON Mono, Flux NDJSON, ResponseEntity

The application demonstrates:

- `POST /api/items` accepts `@Valid @RequestBody Mono<NewItem>` and returns `Mono<ResponseEntity<Item>>` with 201 + Location after saving.
- `GET /api/items/{id}` returns `Mono<ResponseEntity<Item>>` choosing 200/404 based on lookup.
- `GET /api/items/accepted` returns `ResponseEntity<Mono<StatusMessage>>` with early status/header and delayed body.
- `GET /api/items` returns `ResponseEntity<Flux<Item>>` with `application/json` to produce a JSON array.
- `GET /api/items/stream` returns `ResponseEntity<Flux<Item>>` with `application/x-ndjson` to stream each item.
- `POST /api/items/batch` accepts `@Valid @RequestBody Flux<NewItem>` as NDJSON, capped at 100 items, returning `Mono<ResponseEntity<List<Item>>>`.
- `@RestControllerAdvice` returns a consistent error body for `WebExchangeBindException`.
- `WebTestClient` tests verify headers/status/JSON/NDJSON/validation and the batch limit.

Data lives in RAM. There is no database, Spring Security, or real transaction; the store keeps focus on reactive HTTP semantics.

### 13.1. File Tree

```text
webflux-body-response-demo/
├── pom.xml
└── src/
    ├── main/java/example/bodyresponse/
    │   ├── BodyResponseApplication.java
    │   ├── NewItem.java
    │   ├── Item.java
    │   ├── StatusMessage.java
    │   ├── ApiError.java
    │   ├── ItemStore.java
    │   ├── ItemController.java
    │   └── ApiErrors.java
    └── test/java/example/bodyresponse/
        └── ItemControllerTest.java
```

### 13.2. Maven pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>webflux-body-response-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-validation</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
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
```

Add only `spring-boot-starter-webflux` (not `spring-boot-starter-web`) so the app uses the WebFlux reactor stack as covered in this lesson. Jackson comes via the WebFlux starter and Jakarta Bean Validation via the validation starter. WebTestClient is included in starter-test.

### 13.3. Spring Boot Application

**`src/main/java/example/bodyresponse/BodyResponseApplication.java`**

```java
package example.bodyresponse;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BodyResponseApplication {
    public static void main(String[] args) {
        SpringApplication.run(BodyResponseApplication.class, args);
    }
}
```

### 13.4. DTOs and Response Records

**`src/main/java/example/bodyresponse/NewItem.java`**

```java
package example.bodyresponse;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record NewItem(
        @NotBlank
        @Size(max = 80)
        String name) {}
```

**`src/main/java/example/bodyresponse/Item.java`**

```java
package example.bodyresponse;

public record Item(long id, String name) {}
```

**`src/main/java/example/bodyresponse/StatusMessage.java`**

```java
package example.bodyresponse;

public record StatusMessage(String state) {}
```

**`src/main/java/example/bodyresponse/ApiError.java`**

```java
package example.bodyresponse;

public record ApiError(String code) {}
```

The records use Java 17 and are serialized/deserialized by Jackson. `@NotBlank` checks for null/empty/whitespace; `@Size(max=80)` checks only string length. That is **DTO validation**, not authorization or SQL/input safety.

### 13.5. In-Memory Store Returning Mono/Flux

**`src/main/java/example/bodyresponse/ItemStore.java`**

```java
package example.bodyresponse;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicLong;

import org.springframework.stereotype.Service;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Service
public class ItemStore {

    private final AtomicLong sequence = new AtomicLong();
    private final ConcurrentHashMap<Long, Item> data =
            new ConcurrentHashMap<>();

    private Item save(NewItem input) {
        long id = sequence.incrementAndGet();
        Item item = new Item(id, input.name().strip());
        data.put(id, item);
        return item;
    }

    public Mono<Item> create(NewItem input) {
        return Mono.fromSupplier(() -> save(input));
    }

    public Mono<Item> find(long id) {
        return Mono.defer(() ->
                Mono.justOrEmpty(data.get(id)));
    }

    public Flux<Item> all() {
        return Flux.defer(() -> {
            List<Item> snapshot =
                    new ArrayList<>(data.values());
            snapshot.sort(Comparator.comparingLong(Item::id));
            return Flux.fromIterable(snapshot);
        });
    }

    public Mono<List<Item>> saveBatch(List<NewItem> input) {
        return Mono.fromSupplier(() -> {
            List<Item> saved = new ArrayList<>();
            for (NewItem draft : input) {
                saved.add(save(draft));
            }
            return List.copyOf(saved);
        });
    }
}
```

**Key points to understand:**

1. `Mono.fromSupplier` runs `save` when the Publisher is subscribed to, not when the controller creates the Mono.
2. `Mono.defer` queries the Map only at subscription time, which is helpful for observing fresh state in tests.
3. `Flux.defer` creates a snapshot list at subscription time and emits items ordered by ID.
4. Without JDBC/file/network blocking, short in-memory operations on the event loop do not cause I/O waits; however, in a real app using a blocking DB driver, you must offload or pick a reactive data client.
5. `ConcurrentHashMap` and `AtomicLong` keep the demo safe under basic concurrency, **not replacing DB transactions**.
6. `saveBatch` can leave partial writes if an unexpected runtime failure occurs midway; production needs transactions/idempotency if the contract requires atomicity.
7. The store is a Spring `@Service`, separated from the HTTP controller for easier testing and business reuse.
8. Do not use `Thread.sleep` to simulate non-blocking latency.

### 13.6. REST Controller: Six Illustrative Endpoints

**`src/main/java/example/bodyresponse/ItemController.java`**

```java
package example.bodyresponse;

import java.net.URI;
import java.time.Duration;
import java.util.List;

import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/items")
public class ItemController {

    private final ItemStore store;

    public ItemController(ItemStore store) {
        this.store = store;
    }

    @PostMapping(consumes = MediaType.APPLICATION_JSON_VALUE)
    public Mono<ResponseEntity<Item>> create(
            @Valid @RequestBody Mono<NewItem> request) {

        return request.flatMap(store::create)
                .map(item -> ResponseEntity
                        .created(URI.create(
                                "/api/items/" + item.id()))
                        .body(item));
    }

    @GetMapping("/{id}")
    public Mono<ResponseEntity<Item>> find(
            @PathVariable long id) {

        return store.find(id)
                .map(ResponseEntity::ok)
                .defaultIfEmpty(
                        ResponseEntity.notFound().build());
    }

    @GetMapping("/accepted")
    public ResponseEntity<Mono<StatusMessage>> accepted() {
        Mono<StatusMessage> body =
                Mono.just(new StatusMessage("queued"))
                        .delayElement(Duration.ofMillis(10));

        return ResponseEntity.accepted()
                .header("X-Body-Mode", "mono")
                .body(body);
    }

    @GetMapping
    public ResponseEntity<Flux<Item>> list() {
        return ResponseEntity.ok()
                .contentType(MediaType.APPLICATION_JSON)
                .body(store.all());
    }

    @GetMapping(
            path = "/stream",
            produces = MediaType.APPLICATION_NDJSON_VALUE)
    public ResponseEntity<Flux<Item>> stream() {
        return ResponseEntity.ok()
                .contentType(MediaType.APPLICATION_NDJSON)
                .body(store.all());
    }

    @PostMapping(
            path = "/batch",
            consumes = MediaType.APPLICATION_NDJSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<ResponseEntity<List<Item>>> batch(
            @Valid @RequestBody Flux<NewItem> incoming) {

        return incoming.take(101)
                .collectList()
                .flatMap(drafts -> {
                    if (drafts.size() > 100) {
                        return Mono.error(
                                new ResponseStatusException(
                                    HttpStatus.PAYLOAD_TOO_LARGE,
                                    "At most 100 items"));
                    }
                    return store.saveBatch(drafts);
                })
                .map(saved -> ResponseEntity
                        .status(HttpStatus.CREATED)
                        .body(saved));
    }
}
```

### Why Does Each Method Return a Different Type?

- **`create`**: `201 Location` is unknown until the item is created, so it returns `Mono<ResponseEntity<Item>>`.
- **`find`**: must decide between 200 and 404 based on `Mono<Item>`, so it also returns `Mono<ResponseEntity<Item>>`.
- **`accepted`**: status 202 and `X-Body-Mode` are fixed up front; the body is a `Mono<StatusMessage>` that may emit later.
- **`list`**: status/headers are known immediately; `Flux<Item>` is serialized into a standard JSON response.
- **`stream`**: status/headers are known immediately, but the Flux is encoded as NDJSON, allowing multiple JSON lines.
- **`batch`**: NDJSON is the input Flux, yet we want to **confirm the batch is valid and saved** before returning 201, so it returns `Mono<ResponseEntity<List<Item>>>`.

**These six endpoints suffice to show** that the placement of Mono/Flux in the type signature reflects business response semantics rather than mere coding style.

### Why Limit batch to 101?

If you used `incoming.take(100)` and saved, a 101-line request would silently drop the 101st element and still report success. `take(101)` lets you observe the 101st element and **reject** the entire batch (before calling `saveBatch`) when exceeding the 100-item limit.

The demo caps record count; production must also enforce max body bytes, max JSON nesting, per-record size, connection timeouts, rate limits, and cancellation cleanup. Never assume `collectList()` is safe for unbounded input.

### Validation in batch

`@Valid @RequestBody Flux<NewItem>` enables per-DTO validation to catch constraint violations during reactive body handling. For a batch collected before writing, a validation error fails the Publisher and `store.saveBatch` is never called. By contrast, in a streaming handler that saves each item immediately upon reading, items before an invalid one may already be persisted; when atomicity is needed, define a transaction/compensation policy.

## 14. Custom Error Handler for Validation

**`src/main/java/example/bodyresponse/ApiErrors.java`**

```java
package example.bodyresponse;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.bind.support.WebExchangeBindException;

@RestControllerAdvice
public class ApiErrors {

    @ExceptionHandler(WebExchangeBindException.class)
    public ResponseEntity<ApiError> invalidBody(
            WebExchangeBindException error) {
        return ResponseEntity.badRequest()
                .body(new ApiError("invalid_item"));
    }
}
```

Points to distinguish:

- `WebExchangeBindException` is the binding/validation error in **WebFlux**, unlike `MethodArgumentNotValidException` in Servlet MVC.
- The client error body contains only a stable code, leaking no rejected values, exception stacks, or internal validation messages.
- This handles only `WebExchangeBindException`; malformed JSON, `HandlerMethodValidationException`, request size, authorization, and downstream exceptions still need their own error policies.
- `@RestControllerAdvice` handles errors inside the annotated controller pipeline; `WebExceptionHandler` is an abstraction on the outer WebHandler chain with different scope/ordering. Do not write a custom low-level WebExceptionHandler just to map a standard validation error.
- Never catch `Throwable` and return 400 for everything; doing so can mask 500s, ignore cancellation, or leak information.

## 15. Running Maven and Sending Real Requests

Install **JDK 17+** and Maven. From the `webflux-body-response-demo` directory containing `pom.xml`:

```bash
mvn test
mvn spring-boot:run
```

These are two commands **run sequentially**. With Boot defaults, the app listens on `http://localhost:8080`; other servers/proxies may change the URL/port.

### 15.1. POST a JSON Object, Receive 201 + Location

```bash
curl -i -X POST \
  'http://localhost:8080/api/items' \
  -H 'Content-Type: application/json' \
  -d '{"name":"Spring WebFlux"}'
```

Expected (freshly started JVM with no prior data):

```http
HTTP/1.1 201 Created
Location: /api/items/1
Content-Type: application/json

{"id":1,"name":"Spring WebFlux"}
```

`Location` is a relative URI reference pointing to the GET endpoint on the same origin. It does not depend on an unverified request Host header. If public clients need an absolute URL, configure a trusted external base/forwarded-header policy properly; never concatenate raw Host into redirects.

### 15.2. GET Existing or Missing Item

```bash
curl -i 'http://localhost:8080/api/items/1'
curl -i 'http://localhost:8080/api/items/999999'
```

The first call after POST returns 200 and the JSON Item; the second returns **404 Not Found** with no item. Status 404 comes from `Mono<ResponseEntity<Item>>` after `store.find(id)` completes empty, not because a body Mono generates 404 automatically.

### 15.3. ResponseEntity Wrapping Mono with Early Status

```bash
curl -i 'http://localhost:8080/api/items/accepted'
```

Expected:

```http
HTTP/1.1 202 Accepted
X-Body-Mode: mono
Content-Type: application/json

{"state":"queued"}
```

Status/headers were selected by the controller before the delayed Mono emitted the object. **This does not mean a real background job is running**; the demo endpoint uses 202 to illustrate the HTTP envelope. In a real 202 production implementation, clear job tracking and processing semantics are required.

### 15.4. JSON Array with ResponseEntity<Flux<Item>>

```bash
curl -i 'http://localhost:8080/api/items'
```

After creating the first item, the JSON body looks like:

```json
[{"id":1,"name":"Spring WebFlux"}]
```

A Flux can emit multiple DTOs, yet `application/json` Content-Type here represents the list as a single JSON document/array. Never rely on network chunk boundaries to split items.

### 15.5. NDJSON Output Streaming

```bash
curl -i -N \
  -H 'Accept: application/x-ndjson' \
  'http://localhost:8080/api/items/stream'
```

If two items with IDs 1 and 2 exist, the body consists of separate JSON lines:

```text
{"id":1,"name":"Spring WebFlux"}
{"id":2,"name":"Reactor"}
```

curl's `-N` disables some client output buffering; servers/proxies may still buffer depending on configuration. If there are no items, an NDJSON 200 response can have an empty body. With transport streaming, flushing and per-item observability depend on the source, decoder/encoder, and intermediary proxies.

### 15.6. NDJSON Input Batch

```bash
curl -i -X POST \
  'http://localhost:8080/api/items/batch' \
  -H 'Content-Type: application/x-ndjson' \
  -H 'Accept: application/json' \
  --data-binary $'{"name":"Alpha"}\n{"name":"Beta"}\n'
```

In Bash, `$'...'` syntax produces literal newlines. Windows PowerShell has different quoting/newline rules; create an NDJSON file and use `--data-binary @batch.ndjson` for portability.

Expected HTTP 201 and a JSON array containing two new Items with server-owned IDs:

```json
[{"id":3,"name":"Alpha"},{"id":4,"name":"Beta"}]
```

Example IDs assume only two items were created previously. If additional requests/tests ran or the server restarted, IDs will differ. Do not write client code relying on hardcoded absolute IDs in the body.

### 15.7. Validation Error

```bash
curl -i -X POST \
  'http://localhost:8080/api/items' \
  -H 'Content-Type: application/json' \
  -d '{"name":"   "}'
```

Expected `400 Bad Request` and error body:

```json
{"code":"invalid_item"}
```

This happens because `NewItem` has `@NotBlank` and the controller uses `@Valid @RequestBody Mono<NewItem>`. Switching to plain `@RequestBody Mono<NewItem>` without validation elsewhere would let an invalid name pass through, causing corrupt business data.

## 16. WebTestClient Integration Tests

To ensure you have not just code snippets but verified HTTP contracts, use `@SpringBootTest(webEnvironment=RANDOM_PORT)` with `WebTestClient`. Tests do not depend on fixed IDs or execution order.

**`src/test/java/example/bodyresponse/ItemControllerTest.java`**

```java
package example.bodyresponse;

import java.net.URI;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(webEnvironment =
        SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class ItemControllerTest {

    @Autowired
    WebTestClient client;

    @Test
    void monoRequestBodyCreates201AndLocation() {
        String location = client.post()
                .uri("/api/items")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(new NewItem("Spring"))
                .exchange()
                .expectStatus().isCreated()
                .expectHeader().exists(HttpHeaders.LOCATION)
                .expectBody(Item.class)
                .returnResult()
                .getResponseHeaders()
                .getFirst(HttpHeaders.LOCATION);

        assertNotNull(location);
        assertTrue(location.matches("/api/items/[1-9][0-9]*"));

        client.get().uri(location).exchange()
              .expectStatus().isOk()
              .expectBody()
              .jsonPath("$.name").isEqualTo("Spring");
    }

    @Test
    void validationForMonoBodyProduces400() {
        client.post()
              .uri("/api/items")
              .contentType(MediaType.APPLICATION_JSON)
              .bodyValue(new NewItem("   "))
              .exchange()
              .expectStatus().isBadRequest()
              .expectBody()
              .jsonPath("$.code").isEqualTo("invalid_item");
    }

    @Test
    void monoResponseEntityCanChoose404() {
        client.get()
              .uri("/api/items/999999999")
              .exchange()
              .expectStatus().isNotFound();
    }

    @Test
    void entityWithMonoHasEarlyStatusAndHeaders() {
        client.get().uri("/api/items/accepted")
              .exchange()
              .expectStatus().isAccepted()
              .expectHeader().valueEquals(
                      "X-Body-Mode", "mono")
              .expectBody()
              .jsonPath("$.state").isEqualTo("queued");
    }

    @Test
    void entityWithFluxCanProduceJsonArray() {
        client.get().uri("/api/items")
              .exchange()
              .expectStatus().isOk()
              .expectHeader().contentTypeCompatibleWith(
                      MediaType.APPLICATION_JSON)
              .expectBody()
              .jsonPath("$").isArray();
    }

    @Test
    void fluxInputSupportsNdjsonBatch() {
        String ndjson =
                "{\"name\":\"Kotlin\"}\n"
                + "{\"name\":\"Reactor\"}\n";

        client.post()
              .uri("/api/items/batch")
              .contentType(MediaType.APPLICATION_NDJSON)
              .bodyValue(ndjson)
              .exchange()
              .expectStatus().isCreated()
              .expectBody()
              .jsonPath("$").isArray()
              .jsonPath("$.length()").isEqualTo(2);
    }

    @Test
    void ndjsonOutputHasDeclaredStreamingMediaType() {
        client.get().uri("/api/items/stream")
              .accept(MediaType.APPLICATION_NDJSON)
              .exchange()
              .expectStatus().isOk()
              .expectHeader().contentTypeCompatibleWith(
                      MediaType.APPLICATION_NDJSON);
    }
}
```

The test suite has **7 test methods**.

**Notably:** The first test posts, reads the actual Location header, and GETs that URI instead of hardcoding ID 1. The remaining tests check JSON array structure rather than depending on item counts created by other tests. The NDJSON input test uses raw body text containing two JSON lines; do not confuse it with a JSON string literal encoded as `"..."`.

**Static QA note:** The test suite is authored against Spring WebFlux/Spring Boot 3.3.5 APIs. `@AutoConfigureWebTestClient` works with `RANDOM_PORT` to test the reactive server. This code was not executed with Maven within the scope of Google Sheets; before production use, run the full `mvn test`/integration tests with the proper toolchain.

### Useful Test Extensions

Add coverage for:
- Empty body with `@RequestBody(required=true)`.
- Wrong Content-Type / unsupported media type.
- Malformed JSON and field type mismatches.
- 100 vs 101 NDJSON records.
- Validation failure on the second element after the batch has read the first element.
- Client cancel mid-NDJSON stream.
- Slow consumers/response buffering/backpressure.
- Reactor Context/trace ID propagation.
- Spring Security authentication/authorization/CSRF/CORS.
- Large bodies, max in-memory size, and response timeouts.
- R2DBC or other truly non-blocking database client behavior.

## 17. A Small Note on WebTestClient and BodyExtractors

`WebTestClient` offers several ways to assert on a response body:

- `expectBody(Item.class)` for a single object.
- `expectBodyList(Item.class)` for a JSON list/array.
- `expectBody().jsonPath(...)` for a JSON tree.
- `returnResult(Item.class).getResponseBody()` to consume streamed Flux items with Reactor operators/StepVerifier.
- `exchange()` starts the HTTP request/response exchange.

With long-running NDJSON streams, `expectBodyList` can **wait for the stream to complete**; for infinite SSE/Flux streams, tests must not wait for the entire publisher. Use `returnResult(Item.class)` with `StepVerifier`/`take(n)`/timeouts, ensuring cancellation and subscription cleanup after the test.

### Do Not Infer HTTP Status from Body Item Count

`Flux.empty()` can be a valid 200 result. For a missing resource, status should be decided based on lookup/metadata before returning the response (typically `Mono<ResponseEntity<...>>`). On an active stream, the status cannot be changed per element once committed.

## 18. Choosing Mono or Flux for Request Bodies

| Input | Which type to choose? | Reason |
| --- | --- | --- |
| Small single JSON object | `Mono<DTO>` or direct DTO | At most one object |
| Small JSON array, atomic batch | `Mono<List<DTO>>`/wrapper DTO | Validate everything before writing |
| Multi-record NDJSON | `Flux<DTO>` | Emits objects individually, supports backpressure |
| SSE input | Uncommon for POST; choose explicit protocol | SSE is normally server→client |
| Large binary upload | `Flux<DataBuffer>`/file upload APIs | Manage pooled buffers, sizes, cancellation |
| Multipart | WebFlux `@RequestPart`/`FilePart`/`Part` | Dedicated API; do not treat as JSON DTO |
| Form URL encoded | WebFlux form data APIs | Different media type/decoder from JSON |
| Client sends 0 bytes | Explicit `required`/optional policy | Empty Mono differs from validation error |
| Client sends malformed JSON | Error handling, 400 | Never turn silently into a default DTO |

With `application/json` carrying a single object, there is no reason to use `Flux<T>` simply because the app is reactive. Using the right **cardinality contract** matters far more than "the more Flux the better."

## 19. Choosing Reactive ResponseEntity Based on Status Decisions

One quick question to ask:

**Do the status/headers depend on an asynchronous result?**

- **No** → `ResponseEntity<Mono<T>>` or `ResponseEntity<Flux<T>>`. If the body is already ready, `ResponseEntity<T>`.
- **Yes** → `Mono<ResponseEntity<T>>`.
- **Yes, and the body continues streaming after the envelope is chosen** → `Mono<ResponseEntity<Flux<T>>>`.

Examples:
- `GET /items/{id}` must return 404 if absent: `Mono<ResponseEntity<Item>>`.
- `GET /stream` is always 200 NDJSON: `ResponseEntity<Flux<Item>>`.
- `POST /items` needs the ID/Location after creation: `Mono<ResponseEntity<Item>>`.
- `GET /long-operation` is always 202 with a status body emitted later: `ResponseEntity<Mono<StatusMessage>>` (though real job semantics are needed if truly async background work).
- `GET /export` must check permissions/quotas first and then stream: `Mono<ResponseEntity<Flux<byte[]>>>`, or better yet stream DataBuffer/Resource per codec with cancellation/backpressure tests.

### Why Doesn't ResponseEntity<Mono<T>> Automatically Replace 200 with 404?

When `ResponseEntity.ok().body(sourceMono)` is created, HTTP 200 has already been selected. When `sourceMono` completes empty, the framework cannot "guess" it means a missing resource. If the source emits `ResponseStatusException` before commit, the framework may alter the status depending on resolvers, yet relying on errors as a substitute for conditional success/absence leads to unpredictable API design. For normal missing-resource cases, choose `Mono<ResponseEntity<T>>`.

## 20. Error Operators: Where Should Errors Be Handled?

In a pipeline:

```java
return incoming.flatMap(store::create)
        .onErrorResume(DuplicateItemException.class, e ->
                Mono.error(new ResponseStatusException(
                        HttpStatus.CONFLICT, "Duplicate item")));
```

This is a snippet assuming `DuplicateItemException` and `store`. It maps **a known domain error** to HTTP 409 rather than turning every Exception into 409.

Wrong:

```java
return incoming
        .onErrorReturn(new NewItem("default"))
        .flatMap(store::create);
```

If JSON is malformed, validation fails, or the body is missing, the code above could silently create a default item and return 201—altering the meaning of the HTTP request and endangering data integrity. Never use `onErrorReturn` to mask invalid input.

### When the HTTP Response Has Already Committed

A `ResponseEntity<Flux<T>>` for a long stream may already have sent status 200 and several items. If a later item signals an error:
- The app cannot guarantee a clean JSON 500 response.
- The HTTP connection may terminate early or the client may observe a broken stream.
- Protocol-level retry/resume semantics are needed if required.
- Logging and tracing must distinguish partial responses from full successes.
- Never automatically retry non-idempotent POSTs in reactive operators when side effects exist.

### Exceptions in WebFlux

`@RestControllerAdvice`/`@ExceptionHandler` handles exceptions within the annotated endpoint flow; `WebExceptionHandler` on the outer WebHandler chain handles errors that propagate further. `ResponseStatusException` can be mapped to a status by the framework. Components can be ordered; never declare a "catch-all" WebExceptionHandler that hides every error as 400.

## 21. Content Negotiation, 406/415, and Streaming Codecs

- Request `Content-Type` specifies **the format of data sent to the server**.
- Request `Accept` specifies **the format the client wants to receive**.
- `consumes` on `@PostMapping` restricts the request media type.
- `produces` on `@GetMapping` restricts the response media type.
- `ResponseEntity.contentType(...)` sets the response Content-Type.

Example:

```java
@GetMapping(path="/stream",
            produces=MediaType.APPLICATION_NDJSON_VALUE)
public ResponseEntity<Flux<Item>> stream() {
    return ResponseEntity.ok()
            .contentType(MediaType.APPLICATION_NDJSON)
            .body(store.all());
}
```

If a client sends `Accept: text/plain` and the endpoint only specifies `produces=application/x-ndjson`, content negotiation may return 406 (Not Acceptable). If a client POSTs `Content-Type: text/plain` to a handler consuming only JSON, it may return 415. Exact statuses also depend on mappings, codecs, exception handling, and framework configuration; verify via tests rather than guessing.

## 22. One-Shot Request Bodies, Filter Logging, and DataBuffer

`ServerHttpRequest.getBody()` returns `Flux<DataBuffer>`. A WebFilter trying to log the raw request body by calling `subscribe()` can consume the body before `@RequestBody Mono<T>` reads it, causing failures.

Anti-pattern:

```java
exchange.getRequest().getBody().subscribe(buffer ->
        unsafeLog(buffer));
return chain.filter(exchange);
```

This is pseudocode; `unsafeLog` is undefined because the pattern itself is broken. Consequences:
- Two subscribers compete for the same network stream.
- Downstream body readers may see empty or malformed data.
- Passwords, tokens, and PII get written to logs.
- Pooled DataBuffers can leak if not properly released.
- Reactive cancellation/backpressure becomes inconsistent.

If request body instrumentation is needed, use dedicated APIs/tooling with redaction, byte limits, `ServerHttpRequestDecorator`, and clear `DataBufferUtils` ownership; prefer not logging sensitive bodies at all.

**Never buffer entire request bodies in memory for production debugging** without size caps and a privacy policy.

## 23. Security, Concurrency, and Operations

### 23.1. Input Size and Codec Limits

- Cap max in-memory codec buffers (`spring.codec.max-in-memory-size` per Spring Boot config).
- Enforce HTTP body size/JSON depth limits at the proxy/server where needed.
- Cap items per batch and max name lengths.
- Set request/idle timeouts, connection limits, and concurrency limits.
- Enforce rate limits and body chunk sizes against slow clients.
- Never allow clients to send an unbounded Flux into an unbounded `collectList()`.

### 23.2. Authentication and Authorization

`@Valid` validates DTO syntax; it does not mean the principal is authorized to create or read an Item. In WebFlux, use Spring Security `SecurityWebFilterChain` with reactive SecurityContext, then verify ownership/tenant in the service. Never treat client-provided `userId`/`X-Role` as an authenticated identity. With browser cookie/session auth, POST requests are also subject to CSRF policy.

### 23.3. Idempotency and Retries

POST creation is typically non-idempotent. If a client times out after the server already saved the item, retries can create duplicates. In real systems, consider server-validated `Idempotency-Key` headers, transactions/unique constraints, trace IDs, and explicit retry policies. Reactor `retry()` does not distinguish side-effecting operations from read-only operations.

### 23.4. Backpressure and Slow Clients

With Flux NDJSON, if a client reads slowly, upstream demand/cancellation can propagate to the source. However, if code caches too many items, buffers unboundedly, or a remote producer ignores demand, RAM will still grow. Monitor active connections, pending buffers, response write latency, cancellations, DB connections, and scheduler saturation.

### 23.5. Logging, Context Propagation, and Metrics

Reactive execution can switch schedulers; never rely on custom ThreadLocals for request IDs or SecurityContext. Use Reactor Context/tracing integration and route-template metrics to avoid high cardinality. Never log raw queries or bodies containing secrets.

### 23.6. Reverse Proxies and HTTP Framing

Servers can stream NDJSON over chunked transfer encoding or HTTP/2 frames; **TCP/HTTP chunk boundaries do not match JSON line boundaries**. Client parsers must rely on newline/codec framing rather than assuming one network read equals one record. Reverse proxies can buffer or compress responses, affecting streaming latency. Test through the real deployment topology when early per-item delivery is a business requirement.

## 24. Common Mistakes and How to Fix Them

| Symptom | Cause | Fix |
| --- | --- | --- |
| GET missing Item returns 200 with empty body | `ResponseEntity.ok().body(Mono.empty())` | `Mono<ResponseEntity<Item>>` to select 404 |
| POST returns 200 instead of 201 | Returning DTO/Mono with no status override | `Mono<ResponseEntity<Item>>` + `created(Location)` |
| `Mono<NewItem>` is never processed | Created Mono without returning/subscribing in lifecycle | Return reactive composition; do not subscribe manually |
| Event loop blocked | Synchronous JDBC/file/network calls in `map/flatMap` | Non-blocking driver or bounded scheduler offload |
| Invalid DTO saved | Missing `@Valid`/business validation | `@Valid @RequestBody Mono<DTO>` and service checks |
| Malformed JSON produces wrong status/body | Error policy does not cover WebFlux decoder errors | Test malformed JSON and exception mappings |
| Flux input does not stream | Used JSON document/array instead of NDJSON, or decoder buffering | Use matching Content-Type and wire format |
| Output items not received immediately | `application/json` encodes as array, or proxy buffering | Use NDJSON/SSE and streaming tests |
| Client fails parsing NDJSON response | Parser relied on HTTP chunks instead of newlines | Use NDJSON framing |
| Batching causes OOM | Unbounded `Flux.collectList()` | Limit items/bytes, use streaming processing |
| 101-item batch still returns 201 for first 100 | `take(100)` truncates silently | `take(101)` then reject if size>100 |
| Stream fails mid-way while status stays 200 | Response already committed | Resume/retry protocol; never promise JSON 500 |
| Spring MVC classes appear in WebFlux | Wrong import or starter-web included | Use WebFlux stack with proper dependencies |
| `Mono.empty()` causes unclear "not found" API | Lack of distinction between absent vs empty success | Define explicit status/DTO contract |
| Too many publisher subscriptions | Manual `subscribe()` or sharing one-shot body | Let framework subscribe; do not duplicate reads |
| Wrong headers/Location behind proxy | Misconfigured Host/Forwarded trust | Canonical base/trusted proxy policy |
| CORS 403 on browser POST | Preflight/security ordering | WebFlux CORS/Spring Security integration |
| 401/403 handled by controller instead of Security | Missing auth policy in HTTP filter chain | SecurityWebFilterChain + service ACL |
| `@Valid` exception class differs from MVC | WebFlux validation flow differs from Servlet | Handle `WebExchangeBindException` and method validation appropriately |
| Lost tracing/principal across scheduler switch | Custom ThreadLocal | Reactor Context/official context propagation |
| Reactive retry creates duplicates | Retrying POST without idempotency | Idempotency key and transactions |
| ResponseEntity outside Flux sets wrong status | Chose 200 before knowing result | Mono<ResponseEntity<...>> |
| JSON array body treated as NDJSON | Media type mismatch | Content-Type/Accept matching and tests |
| Body too large even with single record | Limited record count without byte limits | Codec byte/size limits |
| DataBuffer leak in WebFilter | Cached/retained without releasing | Use DataBufferUtils and test cancellation |

## 25. Code Review Checklist

- [ ] Controller is WebFlux, with no Servlet MVC mix-up.
- [ ] `@RequestBody Mono<T>` used for single objects, `Flux<T>` for multiple elements/streaming contracts with the right media type.
- [ ] `@Valid` placed on reactive input when Bean Validation is needed.
- [ ] No `block()`/`subscribe()` on request threads or the event loop.
- [ ] Body publisher never consumed twice, and raw secrets never logged.
- [ ] Status/headers decided before commit and based on the proper async result.
- [ ] `Mono<ResponseEntity<T>>` for 200/404, 201/409, or dynamic business conditions.
- [ ] `ResponseEntity<Flux<T>>` for early status alongside a multi-item stream.
- [ ] JSON arrays distinguished from line-delimited NDJSON; client parsers do not rely on network chunks.
- [ ] Limits enforced on item count, bytes, nesting, timeouts, concurrency, and queues.
- [ ] Streaming errors after commit have dedicated retry/resume/cancellation policies.
- [ ] Validation, auth, ownership, CSRF, idempotency, and transactions kept distinct.
- [ ] Location set to valid server resource without blindly trusting client Host/Forwarded headers.
- [ ] Tests cover empty/invalid/malformed bodies and unsupported content types.
- [ ] WebTestClient covers 200, 201, 202, 204 if applicable, 400, 404, 413 if applicable, Content-Type, headers, arrays, and NDJSON.
- [ ] Every external blocking dependency is handled properly rather than merely "wrapping in Mono" and calling it non-blocking.
- [ ] `Flux.collectList()` never used on unbounded input.
- [ ] Metrics track latency, downstream errors, slow clients, and cancelled streams.
- [ ] Route-template metrics used to avoid high-cardinality tags.
- [ ] Every API has a clear error schema and content negotiation contract.

## 26. Self-Check Exercises

1. How does `@RequestBody NewItem` differ from `@RequestBody Mono<NewItem>`?
2. Must `@RequestBody Flux<NewItem>` receive each object immediately on arrival if Content-Type is a `application/json` array?
3. Why is NDJSON convenient for streaming multiple JSON objects?
4. How does `Mono<ResponseEntity<Item>>` differ from `ResponseEntity<Mono<Item>>` in when 404 is decided?
5. Why can `Flux.empty()` usually return 200 with an empty list, while a missing resource needs 404?
6. When do you choose `Mono<ResponseEntity<Flux<T>>>` instead of `ResponseEntity<Flux<T>>`?
7. Which WebFlux exception can `@Valid` on a reactive body produce?
8. Should you catch `WebExchangeBindException` and return raw `error.getMessage()` to public clients?
9. Should `Location` for a POSTed resource be constructed before or after the server determines the ID?
10. How do `ResponseEntity<Flux<Item>>` with `application/json` and `application/x-ndjson` differ in format?
11. Why can calling `collectList()` on an infinite NDJSON input lead to OOM?
12. For a batch maximum of 100, up to which element must you read to detect "too many"?
13. When an NDJSON response has already sent three lines and the fourth errors, can the status cleanly switch from 200 to 500?
14. Why should you not call `incoming.block()` inside a WebFlux controller on the event loop?
15. Does `Mono.fromCallable(() -> jdbc.save(...)).subscribeOn(boundedElastic())` make JDBC non-blocking?
16. At what level of abstraction do `@RequestBody Flux<T>` and `Flux<DataBuffer>` differ?
17. When does a server use `413 Payload Too Large`?
18. Why does 202 Accepted not equate to every delayed `Mono`?
19. Why should you not use `onErrorReturn(new DefaultItem(...))` for malformed JSON or validation errors?
20. Should clients parse NDJSON by HTTP chunks or newline framing?
21. Does CORS replace authorization?
22. How can retrying a POST cause duplicate data?
23. Why should response headers be determined before writing the body?
24. When a resource is absent and the body Publisher is empty, how do you return 404 properly?
25. What can `WebTestClient` verify, and why can't it replace benchmarks or production proxy tests?

**Hints:** (1) Direct DTO decodes before the handler; Mono represents the reactive decode result. (2) No, it depends on codecs/media type. (3) Each JSON line is an independent record. (4) Mono<ResponseEntity> waits for lookup before picking 200/404; ResponseEntity<Mono> fixes status early. (5) An empty collection differs from an absent resource. (6) When envelope/status depends on an async decision while the body is a Flux. (7) WebExchangeBindException; method constraints can also yield HandlerMethodValidationException. (8) No. (9) After the server assigns the ID. (10) JSON array vs newline-delimited objects. (11) Unbounded memory accumulation. (12) 101. (13) Not guaranteed. (14) Blocks the event loop. (15) No, it only offloads blocking work. (16) Decoded DTOs vs raw pooled buffers. (17) When the request exceeds limits per HTTP policy. (18) 202 is business semantics. (19) Masks invalid input and can persist bogus data. (20) NDJSON delimiters. (21) No. (22) Repeated side effects. (23) Response commitment. (24) Mono<ResponseEntity>. (25) Basic contract/runtime behavior; it does not prove throughput, backpressure, or reverse-proxy behavior.

## 27. Official References

- [Spring Framework — WebFlux @RequestBody](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/requestbody.html)
- [Spring Framework — WebFlux ResponseEntity](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/responseentity.html)
- [Spring Framework — WebFlux Controller Method Arguments](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/arguments.html)
- [Spring Framework — WebFlux Controller Return Values](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/return-types.html)
- [Spring Framework — WebFlux Validation](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-validation.html)
- [Spring Framework — WebFlux HTTP Codecs](https://docs.spring.io/spring-framework/reference/web/webflux/config.html)
- [Spring Framework — WebFlux Annotated Controllers](https://docs.spring.io/spring-framework/reference/web/webflux/controller.html)
- [Spring Framework — WebFlux Reactive Core](https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html)
- [Spring Framework — WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html)
- [Spring Framework 6.1 — ResponseEntity Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/http/ResponseEntity.html)
- [Project Reactor — Mono/Flux Operators](https://projectreactor.io/docs/core/release/reference/coreFeatures/simple-ways-to-create-a-flux-or-mono-and-subscribe-to-it.html)
- [Project Reactor — Error Handling](https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html)
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110.html)

**Summary:** `@RequestBody Mono<T>` represents a single-object request body as a reactive publisher; `@RequestBody Flux<T>` fits receiving multiple objects, especially NDJSON/streaming. For responses, choose the type according to **when status/headers must be decided**: `ResponseEntity<Mono<T>>` and `ResponseEntity<Flux<T>>` know the envelope early; `Mono<ResponseEntity<T>>` waits for the async result to pick statuses like 201/404; `Mono<ResponseEntity<Flux<T>>>` lets you decide the envelope asynchronously and then emit a stream. All of this must be paired with proper media types, validation, bounds, error policies, cancellation handling, and non-blocking event-loop discipline.
