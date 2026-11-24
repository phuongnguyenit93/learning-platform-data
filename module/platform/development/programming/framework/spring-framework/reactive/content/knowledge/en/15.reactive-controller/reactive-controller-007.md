# Mono, Flux, and Return Value Types in Spring WebFlux Controllers

> **Module:** Spring Framework – reactive · **Parent topic:** Controller. This lesson explains how Spring WebFlux interprets return values of `@Controller`/`@RestController`: from `Mono<T>` and `Flux<T>` to `ResponseEntity`, `HttpHeaders`, `ProblemDetail`, views/models, Server-Sent Events, and other async types.

## 1. Learning Objectives

1. Distinguish `Mono<T>` (0..1 values), `Flux<T>` (0..N values), and `Mono<Void>` (completion signal only).
2. Understand the roles of `@ResponseBody`, `HttpMessageWriter`, and `ReactiveAdapterRegistry`.
3. Choose the right `ResponseEntity` forms based on when status/header/body need to be decided.
4. Know how to return JSON, NDJSON, SSE, HTML views, `ProblemDetail`, `HttpHeaders`, and `Mono<Void>`.
5. Test endpoints with HTTP integration tests, without calling `block()`/`subscribe()` inside the controller.

**Rule:** the return type expresses cardinality and when the result is available; `ResponseEntity` expresses status/headers/body; `@ResponseBody` decides whether data is written to the HTTP response instead of being used to resolve a view.

## 2. How Does Spring Handle Return Values?

An annotated controller is invoked through `RequestMappingHandlerAdapter`. The invocation result is passed to the appropriate `HandlerResultHandler`. With `@ResponseBody` or `@RestController`, `ResponseBodyResultHandler` coordinates with `HttpMessageWriter` to encode and write the body. With `@Controller` returning a view/model, `ViewResolutionResultHandler` handles the view.

~~~text
HTTP request
    |
    v
RequestMappingHandlerMapping
    |
    v
RequestMappingHandlerAdapter
    |
    v
Controller method
    |
    v
HandlerResult
    |
    +-- @ResponseBody → HttpMessageWriter → HTTP body
    |
    +-- String / View / Model → ViewResolver → HTML
~~~

Spring Framework 7.0.8 lists the supported return types in the WebFlux documentation. Reactive types such as Reactor and RxJava can generally wrap those return value forms; Spring adapts them through `ReactiveAdapterRegistry`.

### 2.1. @RestController and @ResponseBody

`@RestController` is a composed annotation of `@Controller` and `@ResponseBody`. Therefore:

~~~java
@RestController
class GreetingController {
    @GetMapping("/greeting")
    String greeting() {
        return "Hello WebFlux";
    }
}
~~~

The HTTP body is `Hello WebFlux`; Spring does not look for a template with that name. With a plain `@Controller`, `String` is usually a logical view name:

~~~java
@Controller
class PageController {
    @GetMapping("/home")
    String home() {
        return "home";
    }
}
~~~

To make a method in `@Controller` return a body directly, mark `@ResponseBody` on the method or class.

## 3. Mono and Flux: Choosing by Number of Values

### 3.1. Mono<T>: Zero or One Value

`Mono<T>` represents an asynchronous result with 0 or 1 `onNext` followed by complete, or an error signal.

~~~java
@GetMapping("/items/{id}")
Mono<Item> findOne(@PathVariable String id) {
    return repository.findById(id);
}
~~~

- Has an item: downstream receives one `Item`.
- Has no item: `Mono.empty()` completes with no body.
- Has an error: `Mono.error(...)` goes to exception handling.

**`Mono.empty()` does not automatically mean HTTP 404.** If the business logic wants 404, turn empty into `ResponseEntity.notFound()` or an exception mapped to 404.

~~~java
Mono<ResponseEntity<Item>> findExplicit(String id) {
    return repository.findById(id)
        .map(ResponseEntity::ok)
        .defaultIfEmpty(ResponseEntity.notFound().build());
}
~~~

### 3.2. Flux<T>: Zero or Many Values

`Flux<T>` represents a sequence of 0..N elements. It fits lists, event streams, and multi-record query results.

~~~java
@GetMapping("/items")
Flux<Item> findAll() {
    return repository.findAll();
}
~~~

With `application/json`, multiple elements can be encoded as a JSON array; WebFlux processes elements as they arrive, without collecting the entire Flux into a List by default.

~~~java
@GetMapping(value = "/items.ndjson",
            produces = MediaType.APPLICATION_NDJSON_VALUE)
Flux<Item> streamNdjson() {
    return repository.findAll();
}
~~~

`application/x-ndjson` represents each JSON object on its own line.

### 3.3. Mono<Void>: Completion Only

`Mono<Void>` is commonly used for operations that return no data:

~~~java
@DeleteMapping("/items/{id}")
@ResponseStatus(HttpStatus.NO_CONTENT)
Mono<Void> delete(@PathVariable String id) {
    return repository.deleteById(id);
}
~~~

`@ResponseStatus(NO_CONTENT)` defines status 204; `Mono<Void>` indicates when the operation completes.

## 4. Cardinality Table

| Type | Cardinality | Meaning |
| --- | --- | --- |
| `Item` | One synchronous value | Object is ready when the method returns. |
| `Mono<Item>` | 0..1 | One result that may arrive later. |
| `Flux<Item>` | 0..N | Multiple elements that can be written incrementally. |
| `Mono<Void>` | 0 values, terminal signal | Only need to know when work completes/errors. |
| `List<Item>` | One synchronous collection | Entire list is already in memory. |
| `Mono<List<Item>>` | One async collection | Waits to collect the list before emitting one value. |
| `CompletableFuture<Item>` | One async result | Adapter supported when present on the classpath. |
| Kotlin `Flow<Item>` | 0..N | Coroutine-style data stream. |

Do not use `collectList()` for large or infinite streams: it turns `Flux<T>` into `Mono<List<T>>` and holds all elements in memory.


## 5. ResponseEntity: Controlling Status, Headers, and Body

`ResponseEntity<T>` declares status, headers, and body. `HttpEntity<T>` is similar but does not carry a status.

### 5.1. ResponseEntity<T>: Everything Available Immediately

~~~java
@GetMapping("/items/42")
ResponseEntity<Item> getItem() {
    Item item = new Item("42", "Keyboard");
    return ResponseEntity.ok()
        .header("X-Source", "catalog")
        .eTag("\"item-42-v1\"")
        .body(item);
}
~~~

### 5.2. ResponseEntity<Mono<T>>: Status/Headers Immediately, Body Later

~~~java
ResponseEntity<Mono<Item>> asyncBody() {
    return ResponseEntity.ok()
        .header("X-Response-Mode", "body-later")
        .body(repository.findById("42"));
}
~~~

Use when status/headers do not depend on the asynchronous result, while the body arrives later. If the body Mono is empty, the chosen status is still kept; Spring does not automatically change 200 to 404.

### 5.3. Mono<ResponseEntity<T>>: Status/Headers/Body Decided Asynchronously

~~~java
Mono<ResponseEntity<Item>> lookup(String id) {
    return repository.findById(id)
        .map(ResponseEntity::ok)
        .defaultIfEmpty(ResponseEntity.notFound().build());
}
~~~

Use when the async result decides status, headers, and body together.

### 5.4. ResponseEntity<Flux<T>>: Metadata Immediately, Stream Body

~~~java
ResponseEntity<Flux<Item>> stream() {
    return ResponseEntity.ok()
        .contentType(MediaType.APPLICATION_NDJSON)
        .body(repository.findAll());
}
~~~

### 5.5. Mono<ResponseEntity<Flux<T>>>: Async Metadata Then Stream Body

~~~java
Mono<ResponseEntity<Flux<Item>>> delayedStream() {
    return repository.checkAccess()
        .map(allowed -> allowed
            ? ResponseEntity.ok()
                .contentType(MediaType.APPLICATION_NDJSON)
                .body(repository.findAll())
            : ResponseEntity.status(HttpStatus.FORBIDDEN)
                .<Flux<Item>>build());
}
~~~

### 5.6. Comparing Shapes

| Return type | When are status/headers known? | When is the body available? |
| --- | --- | --- |
| `ResponseEntity<T>` | Immediately | Immediately |
| `ResponseEntity<Mono<T>>` | Immediately | Later |
| `ResponseEntity<Flux<T>>` | Immediately | Incrementally |
| `Mono<ResponseEntity<T>>` | After Mono emits | Later |
| `Mono<ResponseEntity<Flux<T>>>` | Later | Incrementally thereafter |

Do not nest Publishers arbitrarily; choose the simplest shape that matches when status/headers must be decided and the body cardinality.

## 6. Other Return Types Supported by WebFlux

| Type | Default meaning |
| --- | --- |
| `@ResponseBody` | Encoded via `HttpMessageWriter` and written to the response body. |
| `HttpEntity<B>`, `ResponseEntity<B>` | Headers and body; ResponseEntity adds status. |
| `HttpHeaders` | Returns headers, with no body. |
| `ErrorResponse`, `ProblemDetail` | Error response per RFC 9457. |
| `String` | `@Controller`: view name; `@ResponseBody`: body. |
| `View` | Renders a View with a model. |
| `Map`, `Model` | Attributes of the implicit model; view name is usually inferred from the request path. |
| `@ModelAttribute` | Adds a model attribute to the model. |
| `Rendering` | Builder for model/view rendering. |
| `FragmentsRendering`, `Flux<Fragment>`, `Collection<Fragment>` | Renders multiple HTML fragments. |
| `void` | Response handled, empty body, or default view depending on context. |
| `Flux<ServerSentEvent<T>>` | Emits Server-Sent Events. |
| Other types | Usually a model attribute; simple types may not be resolved. |

### 6.1. HttpHeaders

~~~java
@GetMapping("/metadata")
HttpHeaders metadata() {
    HttpHeaders headers = new HttpHeaders();
    headers.setCacheControl(CacheControl.noStore());
    headers.set("X-Api-Version", "1");
    return headers;
}
~~~

If you need a custom status, use `ResponseEntity<Void>`.

### 6.2. ErrorResponse and ProblemDetail

~~~java
@GetMapping("/invalid")
Mono<Item> invalid() {
    return Mono.error(new IllegalArgumentException("Invalid item id"));
}

@RestControllerAdvice
class ApiExceptionHandler {
    @ExceptionHandler(IllegalArgumentException.class)
    ProblemDetail handleInvalid(IllegalArgumentException exception) {
        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
            HttpStatus.BAD_REQUEST, exception.getMessage());
        problem.setTitle("Invalid request");
        problem.setProperty("errorCode", "ITEM_INVALID");
        return problem;
    }
}
~~~

When an error occurs before the response commits, the exception handler can convert the error into a ProblemDetail and status 400. If the stream has already written part of the body, the server cannot change the status or write a brand-new error response.

### 6.3. String, View, Map, and Model

~~~java
@Controller
class PageController {
    @GetMapping("/dashboard")
    String dashboard(Model model) {
        model.addAttribute("title", "Dashboard");
        return "dashboard";
    }

    @GetMapping("/report")
    Rendering report() {
        return Rendering.view("report")
            .modelAttribute("title", "Monthly report")
            .build();
    }
}
~~~

In `@Controller`, String is a view name; in `@RestController`, String is the body. Map/Model in an HTML controller add model attributes; in a RestController, they are usually serialized as JSON.

### 6.4. HTML Fragments

`FragmentsRendering`, `Flux<Fragment>`, and `Collection<Fragment>` render one or more HTML fragments, each with its own view and model. Used for server-rendered UI composition, not for regular JSON REST APIs.

### 6.5. void and Mono<Void>

`void`, `Mono<Void>`, or `null` can be considered a handled response if the method has `ServerHttpResponse`, `ServerWebExchange`, `@ResponseStatus`, or a positive ETag/Last-Modified check. Otherwise, `void` can mean an empty body in a REST controller or the default view in an HTML controller.

~~~java
@DeleteMapping("/items/{id}")
@ResponseStatus(HttpStatus.NO_CONTENT)
Mono<Void> delete(@PathVariable String id) {
    return repository.deleteById(id);
}
~~~

### 6.6. Writing the Response Manually

~~~java
@GetMapping("/manual")
Mono<Void> manual(ServerHttpResponse response) {
    byte[] bytes = "done".getBytes(StandardCharsets.UTF_8);
    DataBuffer buffer = response.bufferFactory().wrap(bytes);
    response.getHeaders().setContentType(MediaType.TEXT_PLAIN);
    return response.writeWith(Mono.just(buffer));
}
~~~

This is a fragment that requires Spring/Reactor imports. Do not both write the response manually and return another body.

## 7. SSE and Streaming Responses

### 7.1. ServerSentEvent<T>

~~~java
@GetMapping(value = "/events",
            produces = MediaType.TEXT_EVENT_STREAM_VALUE)
Flux<ServerSentEvent<String>> events() {
    return Flux.just(
        ServerSentEvent.<String>builder()
            .id("1").event("created").data("Item created").build(),
        ServerSentEvent.<String>builder()
            .id("2").event("updated").data("Item updated").build()
    );
}
~~~

SSE uses `text/event-stream`. `ServerSentEvent` can contain `id`, `event`, `retry`, `comment`, and `data`. If only data is needed, you can omit the wrapper:

~~~java
@GetMapping(value = "/messages",
            produces = MediaType.TEXT_EVENT_STREAM_VALUE)
Flux<String> messages() {
    return Flux.just("first", "second", "third");
}
~~~

The client sends `Accept: text/event-stream` or the mapping declares `produces`.

~~~bash
curl -N -H "Accept: text/event-stream" http://localhost:8080/api/returns/events
~~~

SSE suits one-way push. If two-way communication is needed, consider WebSocket.

### 7.2. NDJSON and JSON Streams

| Media type | Writing model | When to use |
| --- | --- | --- |
| `application/json` | JSON object/array; Flux can write incrementally | Regular JSON APIs. |
| `application/x-ndjson` | Each JSON object on one line | Processing record by record. |
| `text/event-stream` | SSE events | Pushing events to browsers. |
| `application/json+stream` | Write/flush each value | Continuous JSON streams. |

WebFlux processes Flux elements as they arrive by default, without collecting the entire stream into a List. With streaming media types, values can be written and flushed individually; exact flushing behavior depends on the writer/media type.

### 7.3. Errors After a Stream Has Started

If Flux has already written 20 elements and the next element fails JSON encoding, the response may already be committed; the server cannot change status 200 to 500 and write a new ProblemDetail.

If you need to collect results before starting the response:

~~~java
Mono<List<Item>> allItems = repository.findAll().collectList();
~~~

`collectList()` turns Flux into Mono<List> and keeps all data in memory before emitting the list. Costs RAM and increases time-to-first-byte; do not use for large/infinite streams.

### 7.4. Backpressure and Slow Clients

- A slow client can slow down consumption rate.
- Buffers, codecs, and connections still consume resources.
- Do not use `collectList()` for infinite data.
- Set timeouts/deadlines and size limits.
- Client disconnect can cancel the subscription; upstream needs cleanup.
- Do not call `block()` to wait for a stream in a controller.


## 8. ReactiveAdapterRegistry and Other Async Types

Spring does not understand only Reactor. `ReactiveAdapterRegistry` adapts many kinds of async/reactive values into Reactive Streams Publishers so WebFlux handles them uniformly. Default adapters depend on the classpath and may include:
- Reactor `Mono`/`Flux`.
- Java `CompletableFuture` and `java.util.concurrent.Flow.Publisher`.
- RxJava 3.
- Kotlin Coroutines (`Deferred`, `Flow`, suspending functions) when the dependency is present.
- SmallRye Mutiny when the corresponding library is on the classpath.
- Other reactive types if the application registers an adapter.

**Do not assume an adapter exists without checking that the dependency is added.**

### 8.1. CompletableFuture

~~~java
@GetMapping("/future")
CompletableFuture<Item> future() {
    return CompletableFuture.completedFuture(
        new Item("f-1", "Future item"));
}
~~~

This is a single async result. Spring can adapt CompletableFuture when the registry has a matching adapter. `supplyAsync` uses the common ForkJoinPool by default; in a real application choose a suitable executor for CPU/blocking tasks and manage its lifecycle.

### 8.2. RxJava and Mutiny

If the application already uses RxJava or Mutiny, types supported by the adapters can be returned directly from the controller. Do not mix multiple reactive libraries in the same module without a clear benefit; each library has its own semantics for cardinality, cancellation, schedulers, and errors.

### 8.3. Kotlin Coroutines: suspend and Flow

Spring WebFlux supports Kotlin suspending functions and `Flow` in annotated controllers. Requires `kotlinx-coroutines-core` and `kotlinx-coroutines-reactor`.

~~~kotlin
@RestController
@RequestMapping("/api/kotlin")
class KotlinItemController(private val service: ItemService) {

    @GetMapping("/{id}")
    suspend fun one(@PathVariable id: String): Item =
        service.findOne(id)

    @GetMapping
    fun all(): Flow<Item> =
        service.findAll()
}
~~~

Conceptual mapping:
- `Mono<Void>` → `suspend fun handler()`.
- `Mono<T>` → `suspend fun handler(): T` or `T?` if it can be empty.
- `Flux<T>` → `fun handler(): Flow<T>`.
- `Flow<T>` is similar to Flux in cardinality, but backpressure is expressed through suspension rather than direct Reactive Streams requests.

This is a Kotlin fragment, not part of the hands-on Java project.

### 8.4. Raw Publisher and Unclear Cardinality

If returning `org.reactivestreams.Publisher<T>` without a specific adapter expressing cardinality, Spring may treat it as a 0..N stream. If you know the source has at most one element, convert explicitly:

~~~java
Mono<Item> one = Mono.from(rawPublisher);
Flux<Item> many = Flux.from(rawPublisher);
~~~

`Mono.from(Publisher)` takes at most one value; `Flux.from(Publisher)` preserves multi-value semantics. Choose the right wrapper so the writer understands the exact cardinality.

## 9. Choosing a Return Type by Need

| Need | Suitable return type | Reason |
| --- | --- | --- |
| One ready object | `Item` or `ResponseEntity<Item>` | Simple, clear status/headers. |
| One object from a reactive repository | `Mono<Item>` | 0..1, non-blocking. |
| Not found needs 404 | `Mono<ResponseEntity<Item>>` | Decides status after the async result. |
| Delete operation with no body | `Mono<Void>` + `@ResponseStatus(NO_CONTENT)` | Only needs completion. |
| Multiple records | `Flux<Item>` | Emits element by element, does not collect into a List by default. |
| Small, complete snapshot | `Mono<List<Item>>` | Waits for all data then serializes the collection. |
| Fixed headers, body arrives later | `ResponseEntity<Mono<Item>>` | Metadata available immediately. |
| Status depends on service | `Mono<ResponseEntity<Item>>` | Decides the full response after the async call. |
| Stream with fixed headers | `ResponseEntity<Flux<Item>>` | Metadata first, body streams later. |
| Event stream for browser | `Flux<ServerSentEvent<T>>` | SSE with id/event/data. |
| One JSON line per record | `Flux<T>` + `application/x-ndjson` | Client processes line-by-line. |
| Structured error | `ProblemDetail` / `ErrorResponse` | RFC 9457. |
| Render HTML template | `String`, `View`, `Rendering`, `Model` in `@Controller` | View resolution. |
| HTML fragments | `FragmentsRendering` / `Flux<Fragment>` | Renders multiple fragments. |
| A future from an SDK | `CompletableFuture<T>` or `Mono<T>` | Adapter handles the async result. |

**Choose by contract first, syntax second.** Do not return Flux just because the service uses Flux if the endpoint needs a small snapshot; and do not call `collectList()` just to make the controller look like Spring MVC when the data is actually a large stream.

## 10. Common Mistakes and Fixes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Using `Flux<T>` for a single result | Unclear cardinality contract | Use `Mono<T>`. |
| Using `Mono<T>` when there are actually many results | Takes at most one value | Use `Flux<T>`. |
| Thinking `Mono.empty()` automatically produces HTTP 404 | API returns empty 200 unexpectedly | Map empty to `ResponseEntity.notFound()` or an exception. |
| Thinking `Mono<Void>` holds null | Violates Reactive Streams semantics | Use `Mono<Void>` for complete/error. |
| Using String in `@Controller` and expecting a text body | Spring interprets it as a view name | Add `@ResponseBody` or use `@RestController`. |
| Using Map in `@Controller` and expecting JSON | Map becomes model attributes | Use `@ResponseBody` or `@RestController`. |
| Using `ResponseEntity<Mono<T>>` when status depends on the result | Status/headers are chosen too early | Use `Mono<ResponseEntity<T>>`. |
| Using `Mono<ResponseEntity<T>>` when multiple values are needed | Wrong body cardinality | Use `Mono<ResponseEntity<Flux<T>>>` or `ResponseEntity<Flux<T>>`. |
| `collectList()` for large/infinite streams | Grows RAM, loses streaming | Return `Flux<T>` with an appropriate media type. |
| Thinking Flux JSON waits for all data | Misses that the response can commit before an error | Understand streaming and handle errors before writing if needed. |
| Returning SSE without declaring `text/event-stream` | Wrong content negotiation/codec | Use `produces` or proper Accept. |
| Returning a raw Publisher with unclear cardinality | Spring may treat it as 0..N | Wrap with `Mono.from` or `Flux.from`. |
| Calling `block()` in a controller | Can lock the event loop | Compose the Publisher and return it to the framework. |
| Calling `subscribe()` in a controller to write the body yourself | Detaches lifecycle and errors from the request | Return Mono/Flux to the framework. |
| Thinking reactive types make JDBC non-blocking automatically | Still blocks threads | Use a reactive driver or offload blocking sources. |
| Returning null from a reactive chain | `onNext(null)` is invalid | Use `Mono.empty()` or `Mono.just(value)`. |

## 11. How to Debug When the Response Is Not as Expected

1. **Annotation:** does the method belong to `@RestController` or `@Controller`? Does it have `@ResponseBody`?
2. **Cardinality:** does the method return Mono, Flux, a collection, or a synchronous object? Is the source empty/error?
3. **Response shape:** do status/headers depend on the async result? Choose the corresponding ResponseEntity.
4. **Content negotiation:** check Accept, produces, Content-Type.
5. **Codec:** which HttpMessageWriter encodes the body? Does Jackson/the codec support the type?
6. **Streaming:** did the body fail after part of it was sent? Is the client reading a JSON array, NDJSON, or SSE?
7. **Lifecycle:** does the Publisher complete? Is there a `Mono.never()`/infinite Flux? Does client disconnect cancel the source?
8. **Blocking:** are there block(), JDBC, Thread.sleep, or blocking SDK calls on the request path?
9. **Exception:** did the error occur before or after the response committed? Is there a matching @ExceptionHandler?
10. **HTTP test:** verify status, headers, body, media type, and cancellation with integration tests.

## 12. Production Checklist

- [ ] Return type reflects exact cardinality: Mono for 0..1, Flux for 0..N.
- [ ] `@RestController`/`@ResponseBody` used properly when writing a body; `@Controller` used for views/models.
- [ ] Empty results have a clear status contract; never assume empty automatically becomes 404.
- [ ] ResponseEntity has a shape matching when status/headers/body are decided.
- [ ] Media type declared via produces/Accept; codec supports the body type.
- [ ] Streaming has timeouts, backpressure, cancellation, and cleanup.
- [ ] Post-commit errors are handled per the stream protocol; do not expect to change status/body already sent.
- [ ] collectList is used only when size is bounded and buffering is intentional.
- [ ] ProblemDetail/ErrorResponse has an appropriate status without leaking stack traces.
- [ ] No block()/subscribe() called on the controller/service request path.
- [ ] Blocking libraries are replaced by reactive APIs or boundedly offloaded.
- [ ] Async adapters are used only when dependencies and adapters are present.
- [ ] Integration tests verify status, headers, body, media type, empty/error, and SSE/streams.

## 13. Hands-On Exercises

**Exercise 1 – Cardinality.** Write three endpoints returning Item, Mono<Item>, and Flux<Item>. Test the not-found case; explain why Mono.empty() does not automatically become 404.

**Exercise 2 – Choosing ResponseEntity.** Write ResponseEntity<Mono<Item>> and Mono<ResponseEntity<Item>>. Have the repository return empty; observe which method decides 404 after knowing the result.

**Exercise 3 – Mono<Void>.** Write a DELETE endpoint returning Mono<Void> with @ResponseStatus(NO_CONTENT). Verify status 204 and an empty body.

**Exercise 4 – Flux JSON and NDJSON.** Return the same Flux with application/json and application/x-ndjson. Write a client reading element by element; compare the parser and flush behavior.

**Exercise 5 – SSE.** Return Flux<ServerSentEvent<Item>> with id/event/data. Open curl -N, disconnect the client midway, and verify upstream cleanup.

**Exercise 6 – Errors during streaming.** Create a Flux that emits two items then errors. Compare with collectList; pay attention to RAM and time-to-first-byte.

**Exercise 7 – Kotlin.** Convert Mono<Item> to suspend fun one(): Item? and Flux<Item> to Flow<Item>. Note the coroutines dependencies.

**Exercise 8 – View and REST.** Create a @Controller returning String and a @RestController returning the same String. Explain why one resolves a view while the other writes the body.

## 14. Official References

1. Spring Framework 7.0.8 – Controller Return Values: https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/return-types.html
2. Spring Framework – ResponseEntity: https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/responseentity.html
3. Spring Framework – @ResponseBody: https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/responsebody.html
4. Spring Framework – Annotated Controllers: https://docs.spring.io/spring-framework/reference/web/webflux/controller.html
5. Spring Framework – Reactive Core, codecs, and streaming: https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html
6. Spring Framework – Kotlin Coroutines: https://docs.spring.io/spring-framework/reference/languages/kotlin/coroutines.html
7. Spring Framework – ReactiveAdapterRegistry Javadoc: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/ReactiveAdapterRegistry.html
8. Spring Boot – Reactive Web Applications: https://docs.spring.io/spring-boot/reference/web/reactive.html

**Self-check:** When a repository returns Mono.empty(), does the API automatically return 404? When status depends on async data, do you choose ResponseEntity<Mono<T>> or Mono<ResponseEntity<T>>? Why can Flux commit the response before an element fails encoding? How does @RestController change the meaning of String?


## 9. Runnable Java 17+ Example with Spring Boot 4.0.9

The project illustrates return forms: `Item`, `Mono<Item>`, `Flux<Item>`, NDJSON, empty, `Mono<Void>`, `ResponseEntity` shapes, `HttpHeaders`, `CompletableFuture`, SSE, and `ProblemDetail`.

### 9.1. Project Structure

~~~text
webflux-return-types/
├── pom.xml
├── src/main/java/com/example/returns/ReturnTypesApplication.java
├── src/main/java/com/example/returns/Item.java
├── src/main/java/com/example/returns/ItemController.java
├── src/main/java/com/example/returns/ApiExceptionHandler.java
└── src/test/java/com/example/returns/ReturnTypesIntegrationTest.java
~~~

### 9.2. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.0.9</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>webflux-return-types</artifactId>
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
~~~

### 9.3. ReturnTypesApplication.java

~~~java
package com.example.returns;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ReturnTypesApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReturnTypesApplication.class, args);
    }
}
~~~

### 9.4. Item.java

~~~java
package com.example.returns;

public record Item(String id, String name) {}
~~~

### 9.5. ItemController.java

~~~java
package com.example.returns;

import java.util.concurrent.CompletableFuture;

import org.springframework.http.CacheControl;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/returns")
public class ItemController {

    private Item item(String id) {
        return new Item(id, "Item " + id);
    }

    @GetMapping("/direct/{id}")
    public Item direct(@PathVariable String id) {
        return item(id);
    }

    @GetMapping("/mono/{id}")
    public Mono<Item> mono(@PathVariable String id) {
        return Mono.just(item(id));
    }

    @GetMapping("/flux")
    public Flux<Item> flux() {
        return Flux.just(item("1"), item("2"));
    }

    @GetMapping(value = "/ndjson",
                produces = MediaType.APPLICATION_NDJSON_VALUE)
    public Flux<Item> ndjson() {
        return Flux.just(item("1"), item("2"));
    }

    @GetMapping("/empty")
    public Mono<Item> empty() {
        return Mono.empty();
    }

    @GetMapping("/void")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    public Mono<Void> noContent() {
        return Mono.empty();
    }

    @GetMapping("/string")
    public String stringBody() {
        return "plain text";
    }

    @GetMapping("/headers")
    public HttpHeaders headers() {
        HttpHeaders headers = new HttpHeaders();
        headers.setCacheControl(CacheControl.noStore());
        headers.set("X-Api-Version", "1");
        return headers;
    }

    @GetMapping("/entity")
    public ResponseEntity<Item> entity() {
        return ResponseEntity.ok()
            .header("X-Response-Mode", "immediate")
            .body(item("entity"));
    }

    @GetMapping("/entity-async")
    public Mono<ResponseEntity<Item>> entityAsync() {
        return Mono.just(
            ResponseEntity.accepted().body(item("async-entity")));
    }

    @GetMapping("/body-async")
    public ResponseEntity<Mono<Item>> bodyAsync() {
        return ResponseEntity.ok()
            .header("X-Response-Mode", "body-later")
            .body(Mono.just(item("async-body")));
    }

    @GetMapping(value = "/entity-stream",
                produces = MediaType.APPLICATION_NDJSON_VALUE)
    public ResponseEntity<Flux<Item>> entityStream() {
        return ResponseEntity.ok()
            .header("X-Response-Mode", "stream")
            .contentType(MediaType.APPLICATION_NDJSON)
            .body(Flux.just(item("stream-1"), item("stream-2")));
    }

    @GetMapping(value = "/sse",
                produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public Flux<ServerSentEvent<Item>> sse() {
        return Flux.just(
            ServerSentEvent.<Item>builder()
                .id("1").event("created").data(item("sse-1")).build(),
            ServerSentEvent.<Item>builder()
                .id("2").event("updated").data(item("sse-2")).build()
        );
    }

    @GetMapping("/future")
    public CompletableFuture<Item> future() {
        return CompletableFuture.completedFuture(item("future"));
    }

    @GetMapping("/problem")
    public Mono<Item> problem() {
        return Mono.error(new IllegalArgumentException("Invalid item"));
    }
}
~~~

### 9.6. ApiExceptionHandler.java

~~~java
package com.example.returns;

import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class ApiExceptionHandler {

    @ExceptionHandler(IllegalArgumentException.class)
    public ProblemDetail invalidItem(IllegalArgumentException exception) {
        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
            HttpStatus.BAD_REQUEST, exception.getMessage());
        problem.setTitle("Invalid request");
        problem.setProperty("errorCode", "ITEM_INVALID");
        return problem;
    }
}
~~~

### 9.7. ReturnTypesIntegrationTest.java

The test uses `java.net.http.HttpClient` built into JDK 17. `RANDOM_PORT` starts a real server; the test goes through the HTTP connector, mapping, return value handling, and message writers.

~~~java
package com.example.returns;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.test.context.SpringBootTest;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class ReturnTypesIntegrationTest {

    @Value("${local.server.port}")
    int port;

    private HttpResponse<String> get(String path, String accept)
            throws Exception {
        HttpRequest.Builder builder = HttpRequest.newBuilder(
            URI.create("http://localhost:" + port + path))
            .GET();

        if (accept != null) {
            builder.header("Accept", accept);
        }

        return HttpClient.newHttpClient().send(
            builder.build(),
            HttpResponse.BodyHandlers.ofString());
    }

    @Test
    void directAndMonoValuesBecomeJson() throws Exception {
        HttpResponse<String> direct = get(
            "/api/returns/direct/7", "application/json");
        HttpResponse<String> mono = get(
            "/api/returns/mono/7", "application/json");

        assertEquals(200, direct.statusCode());
        assertEquals(200, mono.statusCode());
        assertTrue(direct.body().contains("\"id\":\"7\""));
        assertTrue(mono.body().contains("\"name\":\"Item 7\""));
    }

    @Test
    void fluxWritesMultipleJsonValues() throws Exception {
        HttpResponse<String> response = get(
            "/api/returns/flux", "application/json");

        assertEquals(200, response.statusCode());
        assertTrue(response.body().contains("\"id\":\"1\""));
        assertTrue(response.body().contains("\"id\":\"2\""));
    }

    @Test
    void ndjsonUsesStreamingMediaType() throws Exception {
        HttpResponse<String> response = get(
            "/api/returns/ndjson", "application/x-ndjson");

        assertEquals(200, response.statusCode());
        assertTrue(response.headers()
            .firstValue("Content-Type").orElse("")
            .startsWith("application/x-ndjson"));
        assertTrue(response.body().contains("\"id\":\"1\""));
        assertTrue(response.body().contains("\"id\":\"2\""));
    }

    @Test
    void emptyMonoHasNoBodyAndNoAutomaticNotFound() throws Exception {
        HttpResponse<String> response = get(
            "/api/returns/empty", "application/json");

        assertEquals(200, response.statusCode());
        assertTrue(response.body().isEmpty());
    }

    @Test
    void monoVoidCanRepresentNoContent() throws Exception {
        HttpResponse<String> response = get(
            "/api/returns/void", "application/json");

        assertEquals(204, response.statusCode());
        assertTrue(response.body().isEmpty());
    }

    @Test
    void stringInRestControllerIsResponseBody() throws Exception {
        HttpResponse<String> response = get(
            "/api/returns/string", "text/plain");

        assertEquals(200, response.statusCode());
        assertEquals("plain text", response.body());
    }

    @Test
    void httpHeadersReturnHasNoBody() throws Exception {
        HttpResponse<String> response = get(
            "/api/returns/headers", "application/json");

        assertEquals(200, response.statusCode());
        assertEquals("1", response.headers()
            .firstValue("X-Api-Version").orElseThrow());
        assertTrue(response.body().isEmpty());
    }

    @Test
    void responseEntitySetsStatusHeadersAndBody() throws Exception {
        HttpResponse<String> response = get(
            "/api/returns/entity", "application/json");

        assertEquals(200, response.statusCode());
        assertEquals("immediate", response.headers()
            .firstValue("X-Response-Mode").orElseThrow());
        assertTrue(response.body().contains("\"id\":\"entity\""));
    }

    @Test
    void monoResponseEntityCanChooseStatusAsynchronously()
            throws Exception {
        HttpResponse<String> response = get(
            "/api/returns/entity-async", "application/json");

        assertEquals(202, response.statusCode());
        assertTrue(response.body().contains("async-entity"));
    }

    @Test
    void responseEntityMonoBodyKeepsImmediateHeaders()
            throws Exception {
        HttpResponse<String> response = get(
            "/api/returns/body-async", "application/json");

        assertEquals(200, response.statusCode());
        assertEquals("body-later", response.headers()
            .firstValue("X-Response-Mode").orElseThrow());
        assertTrue(response.body().contains("async-body"));
    }

    @Test
    void responseEntityFluxBodyStreamsNdjson() throws Exception {
        HttpResponse<String> response = get(
            "/api/returns/entity-stream", "application/x-ndjson");

        assertEquals(200, response.statusCode());
        assertEquals("stream", response.headers()
            .firstValue("X-Response-Mode").orElseThrow());
        assertTrue(response.body().contains("stream-1"));
        assertTrue(response.body().contains("stream-2"));
    }

    @Test
    void serverSentEventsUseEventStreamContentType() throws Exception {
        HttpResponse<String> response = get(
            "/api/returns/sse", "text/event-stream");

        assertEquals(200, response.statusCode());
        assertTrue(response.headers()
            .firstValue("Content-Type").orElse("")
            .startsWith("text/event-stream"));
        assertTrue(response.body().contains("created"));
        assertTrue(response.body().contains("data:"));
    }

    @Test
    void completableFutureIsAdaptedToAsyncResponse() throws Exception {
        HttpResponse<String> response = get(
            "/api/returns/future", "application/json");

        assertEquals(200, response.statusCode());
        assertTrue(response.body().contains("\"id\":\"future\""));
    }

    @Test
    void problemDetailIsReturnedForReactiveError() throws Exception {
        HttpResponse<String> response = get(
            "/api/returns/problem", "application/problem+json");

        assertEquals(400, response.statusCode());
        assertTrue(response.body().contains("Invalid item"));
        assertTrue(response.body().contains("ITEM_INVALID"));
    }
}
~~~

### 9.8. Running the Application

Requires JDK 17+ and Maven:

~~~bash
java -version
mvn -version
mvn test
mvn spring-boot:run
~~~

The application listens on port 8080 by default. Sample requests:

~~~bash
curl -i http://localhost:8080/api/returns/mono/7
curl -i http://localhost:8080/api/returns/flux
curl -i -H "Accept: application/x-ndjson" http://localhost:8080/api/returns/ndjson
curl -i http://localhost:8080/api/returns/empty
curl -i http://localhost:8080/api/returns/entity-async
curl -i -H "Accept: text/event-stream" http://localhost:8080/api/returns/sse
curl -i -H "Accept: application/problem+json" http://localhost:8080/api/returns/problem
~~~

**Key results to observe:**

| Endpoint | Status | Body/headers |
| --- | ---: | --- |
| `/mono/7` | 200 | JSON object of Item 7 |
| `/flux` | 200 | JSON with two Items |
| `/ndjson` | 200 | `application/x-ndjson`, two JSON lines |
| `/empty` | 200 | Empty body, does not automatically become 404 |
| `/void` | 204 | Empty body |
| `/string` | 200 | `plain text` |
| `/headers` | 200 | `X-Api-Version: 1`, empty body |
| `/entity-async` | 202 | ResponseEntity decided async |
| `/body-async` | 200 | Header available immediately, Mono body written later |
| `/entity-stream` | 200 | Multi-element NDJSON |
| `/sse` | 200 | `text/event-stream` |
| `/future` | 200 | JSON from CompletableFuture |
| `/problem` | 400 | ProblemDetail JSON |

In the SSE test, events can be encoded as `id:`, `event:`, and `data:` lines; spacing/order depends on the encoder. The test checks the media type and content rather than the entire byte output.
