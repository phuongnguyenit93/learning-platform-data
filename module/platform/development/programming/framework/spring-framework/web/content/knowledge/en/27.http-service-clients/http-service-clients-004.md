# HTTP Service Client: Synchronous, Reactive Return Types, and ResponseEntity Responses

## Objectives

Spring Framework allows declaring remote HTTP calls as a **Java interface** with `@HttpExchange`, `@GetExchange`, `@PostExchange`, etc., and then generating an implementation via `HttpServiceProxyFactory`. The interface itself contains no code that makes HTTP calls; the **adapter** decides whether to use `RestClient`, `RestTemplate`, or `WebClient`.

After this lesson, you will be able to:
- Choose **synchronous return types** such as `Book`, `List<Book>`, `void`, `HttpHeaders`, and `ResponseEntity<Book>`.
- Choose **reactive return types** such as `Mono<Book>`, `Flux<Book>`, `Mono<Void>`, `Mono<ResponseEntity<Book>>`, and `Mono<ResponseEntity<Flux<Book>>>`.
- Understand when HTTP I/O actually occurs, when the body has been decoded, and how to inspect status/headers.
- Design semantically sound client APIs, handle 4xx/5xx errors, avoid accidentally blocking the event loop, and avoid confusing HTTP client return types with Spring MVC/WebFlux controller return types.

The scope is **service-calling HTTP Interface Clients** in Spring Framework 6.1–6.2, Java 17+, rather than a comprehensive survey of all controller return types.

## 1. Why Does the Return Type Depend on the HTTP Adapter?

For example, for the same endpoint `GET /books/7`, the following two interfaces can read the same JSON body, yet have very different usage models:

```java
interface SyncBooks {
    @GetExchange("/books/{id}")
    Book getBook(@PathVariable("id") long id);
}

interface ReactiveBooks {
    @GetExchange("/books/{id}")
    Mono<Book> getBook(@PathVariable("id") long id);
}
```

`Book` is a DTO, for example `record Book(long id, String title) {}`.

- `SyncBooks.getBook(7)`: the call only returns `Book` after HTTP I/O and body reading finish, or throws an exception. The caller's execution thread **waits for the result**.
- `ReactiveBooks.getBook(7)`: the call immediately returns a `Mono<Book>` describing the HTTP operation. **Subscription** starts the pipeline and later emits the body or an error signal. `Mono<Book>` must not be mistaken for a `Book` that is already available.
- If status/headers are needed alongside the body, use `ResponseEntity<Book>` or `Mono<ResponseEntity<Book>>`, depending on the adapter and execution model.

`HttpServiceProxyFactory` is the component that creates the proxy, while the adapter connects the proxy to the actual client. Conceptual diagram:

```text
Interface @GetExchange/@PostExchange
           |
           v
HttpServiceProxyFactory -> dynamic proxy
           |
           +-- RestClientAdapter / RestTemplateAdapter
           |       -> synchronous HTTP I/O -> T, HttpHeaders, ResponseEntity<T>, ...
           |
           +-- WebClientAdapter
                   -> reactive HTTP I/O -> Mono<T>, Flux<T>,
                      Mono<ResponseEntity<T>>, ...
```

**Core rule:** The return type must be **supported by the underlying adapter**. You cannot arbitrarily declare `Mono<Book>` and use `RestClientAdapter` expecting Spring to turn the request into non-blocking automatically. Besides reactive types, `WebClientAdapter` also supports synchronous types, though synchronous calls on a reactive client still wait for the result; generally use reactive forms when the application runs on WebFlux.

## 2. Initializing an HTTP Service Client

### 2.1. The Interface Only Describes the HTTP Contract

```java
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.service.annotation.GetExchange;

record Book(long id, String title) {}

interface BookHttpApi {
    @GetExchange("/books/{id}")
    ResponseEntity<Book> getBook(@PathVariable("id") long id);
}
```

`@GetExchange` marks HTTP GET and the URI template; `@PathVariable` provides the `id` variable. A Java interface can contain multiple methods for different endpoints. The annotations declare the request and do not independently decide blocking vs. reactive behavior.

### 2.2. Synchronous Adapter with RestClient

```java
import org.springframework.web.client.RestClient;
import org.springframework.web.client.support.RestClientAdapter;
import org.springframework.web.service.invoker.HttpServiceProxyFactory;

RestClient restClient = RestClient.builder()
        .baseUrl("https://catalog.example.com")
        .build();

BookHttpApi api = HttpServiceProxyFactory
        .builderFor(RestClientAdapter.create(restClient))
        .build()
        .createClient(BookHttpApi.class);

ResponseEntity<Book> response = api.getBook(7);
```

This is **illustrative code placed inside a method/configuration**, not a standalone runnable Java file. `RestClientAdapter` was introduced in Spring Framework 6.1, implements `HttpExchangeAdapter`, and supports synchronous return types.

### 2.3. Reactive Adapter with WebClient

```java
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.reactive.function.client.support.WebClientAdapter;
import org.springframework.web.service.invoker.HttpServiceProxyFactory;

WebClient webClient = WebClient.builder()
        .baseUrl("https://catalog.example.com")
        .build();

ReactiveBookApi api = HttpServiceProxyFactory
        .builderFor(WebClientAdapter.create(webClient))
        .build()
        .createClient(ReactiveBookApi.class);
```

In the example above, `ReactiveBookApi` is a separate interface with methods returning `Mono`/`Flux`; it is defined in the next section. `WebClientAdapter` supports `ReactorHttpExchangeAdapter`. If the project uses Spring 6.0, some builder factory APIs differ from the Spring 6.1+ examples; check the Javadoc for your exact version.

In Spring Boot, prefer framework-provided builders to inherit shared settings, codecs, and customizers. If using only `RestClient`, include the corresponding Spring Web dependency; if using `WebClient` and Reactor, `spring-boot-starter-webflux` is usually needed. Using WebClient as an HTTP client does not force server-side controllers to run on WebFlux.

## 3. Synchronous Return Types

Adapters for `RestClient` or `RestTemplate` support the following return types:

| Interface return type | Meaning after method completes | When to use |
| --- | --- | --- |
| `void` | Request has executed; response content discarded | Commands needing neither body nor status |
| `HttpHeaders` | Response headers available; body not kept as result | Only ETag, content type, or metadata needed |
| `T` | Response body decoded into `T` | Only business data needed |
| `ResponseEntity<Void>` | HTTP status + headers available, no body needed | DELETE/POST/HEAD needing status inspection |
| `ResponseEntity<T>` | Status + headers + `T` body available | Both payload and HTTP metadata needed |

Example:

```java
import org.springframework.http.HttpHeaders;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.service.annotation.DeleteExchange;
import org.springframework.web.service.annotation.GetExchange;
import org.springframework.web.service.annotation.PostExchange;
import org.springframework.web.service.annotation.RequestBody;

interface SyncBookApi {
    @GetExchange("/books/{id}")
    Book getBook(@PathVariable("id") long id);

    @GetExchange("/books")
    java.util.List<Book> listBooks();

    @GetExchange("/books/{id}")
    HttpHeaders getBookHeaders(@PathVariable("id") long id);

    @GetExchange("/books/{id}")
    ResponseEntity<Book> getBookResponse(@PathVariable("id") long id);

    @DeleteExchange("/books/{id}")
    ResponseEntity<Void> deleteBook(@PathVariable("id") long id);

    @PostExchange("/books/refresh")
    void requestRefresh();
}
```

This is an **illustrative contract**: the backend must actually expose these endpoints. `Book` is the DTO from earlier, and `List<Book>` represents a JSON array when supported by the codec. Note that `void` only means no return value in Java; HTTP still has an actual status and can report errors.

### 3.1. T (DTO, String, List<T>)

```java
Book book = api.getBook(7);
System.out.println(book.title());
```

With `T`, the calling code receives the body directly after the request completes. If the server returns HTTP 204 or an empty body, do not assume a valid DTO always exists; missing-body outcomes must be handled according to the endpoint contract. Avoid dereferencing `book.title()` when the result may be null.

For collection/generic bodies, the proxy can use generic info from the method signature so the codec decodes `List<Book>` properly; do not use `Object`/raw `List` when structure control is needed.

### 3.2. void and HttpHeaders

`void` fits when success/failure of the HTTP call is the only thing the caller cares about, such as triggering an operation that returns no data. `HttpHeaders` fits when only metadata is needed, for example:

```java
HttpHeaders headers = syncApi.getBookHeaders(7);
String etag = headers.getETag();
```

This does not mean you always know the specific status code. If you need to distinguish HTTP 200 from 202 or check `Location` alongside status 201, choose `ResponseEntity<Void>` or `ResponseEntity<T>`.

### 3.3. ResponseEntity<T> and ResponseEntity<Void>

`org.springframework.http.ResponseEntity<T>` is an object containing three parts:

```text
ResponseEntity<T>
  - statusCode : HttpStatusCode
  - headers    : HttpHeaders
  - body       : T, may be null
```

Example:

```java
ResponseEntity<Book> response = syncApi.getBookResponse(7);

int status = response.getStatusCode().value();
String etag = response.getHeaders().getETag();
Book body = response.getBody();
```

`ResponseEntity<Void>` is an explicit choice for endpoints requiring no payload:

```java
ResponseEntity<Void> response = syncApi.deleteBook(7);
boolean noContent = response.getStatusCode().value() == 204;
```

**Note:** A `ResponseEntity` received from an HTTP client is **the remote service's response**. It is not automatically forwarded to the browser. When returned from a controller, Spring MVC/WebFlux uses `ResponseEntity` to **build your own application's server response**. Both contexts share the same class but have different responsibilities.

## 4. Reactive Return Types

With `WebClientAdapter`, the synchronous types from the previous section **can still be used**, while these reactive types are available:

| Type | Data and when it becomes available | Use case |
| --- | --- | --- |
| `Mono<Void>` | Completion/error signal, emits no body value | Commands needing no data |
| `Mono<HttpHeaders>` | Headers arrive asynchronously | Reading metadata only |
| `Mono<T>` | 0 or 1 decoded body object | Single resource |
| `Flux<T>` | Multiple items as a reactive stream | Lists/streams |
| `Mono<ResponseEntity<Void>>` | Async status + headers, no body needed | Operations needing status observation |
| `Mono<ResponseEntity<T>>` | Async status + headers + `T` body | Reading one body + status |
| `Mono<ResponseEntity<Flux<T>>>` | Async status + headers, plus `Flux<T>` body stream | Need metadata before/while consuming multi-item stream |

Illustrative interface:

```java
import org.springframework.http.HttpHeaders;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.service.annotation.DeleteExchange;
import org.springframework.web.service.annotation.GetExchange;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

interface ReactiveBookApi {
    @GetExchange("/books/{id}")
    Mono<Book> getBook(@PathVariable("id") long id);

    @GetExchange("/books")
    Flux<Book> streamBooks();

    @GetExchange("/books/{id}")
    Mono<HttpHeaders> getBookHeaders(@PathVariable("id") long id);

    @GetExchange("/books/{id}")
    Mono<ResponseEntity<Book>> getBookResponse(@PathVariable("id") long id);

    @GetExchange("/books")
    Mono<ResponseEntity<Flux<Book>>> streamWithResponse();

    @DeleteExchange("/books/{id}")
    Mono<ResponseEntity<Void>> deleteBook(@PathVariable("id") long id);
}
```

Not every JSON endpoint emits items continuously. `Flux<Book>` is a multi-element reactive type; whether data streams incrementally during download depends on the server, media type, and codec. A JSON array can often be decoded into a Flux of elements, but if true long-lived streaming is required, an appropriate protocol/media type such as NDJSON or SSE is needed.

### 4.1. Mono<T> and Flux<T>

```java
Mono<Book> one = reactiveApi.getBook(7);
Flux<Book> many = reactiveApi.streamBooks();

Mono<String> name = one.map(Book::title);
Mono<java.util.List<Book>> collected = many.collectList();
```

`one` and `many` are only publishers; there is no value here yet for synchronous use. Inside a WebFlux controller:

```java
@GetMapping("/my-books/{id}")
public Mono<Book> fetch(@PathVariable long id) {
    return reactiveApi.getBook(id)
            .map(book -> new Book(book.id(), book.title()));
}
```

This controller snippet only illustrates returning a publisher; it requires importing `org.springframework.web.bind.annotation.GetMapping` and placing it inside a real controller. The framework orchestrates subscription; `block()` is not needed here.

- `Mono.empty()` represents completion with no item, **not** `Mono.just(null)` (Reactor forbids null elements).
- `Flux<T>` may complete, error, or run indefinitely depending on the server.
- `flatMap` is used when the next step returns another publisher, whereas `map` is used when the transformation returns a regular value.
- On error, the publisher emits `onError`; returning `Mono<T>` does not turn HTTP 404 into an "empty result" by default.

### 4.2. Mono<Void> as a Completion Signal

```java
interface ReactiveCommandApi {
    @PostExchange("/refresh")
    Mono<Void> refresh();
}
```

`Mono<Void>` emits no DTO; it lets you wait for request completion, chain operations, and receive errors:

```java
Mono<Void> next = commandApi.refresh()
        .then(Mono.fromRunnable(() ->
                System.out.println("Refresh request completed")));
```

In the snippet above, the print runs only when the publisher is subscribed to and the request finishes successfully. If status 202 or a `Retry-After` header is needed, use `Mono<ResponseEntity<Void>>`.

## 5. ResponseEntity in Reactive: Choosing the Right Wrapper Order

This is the easiest place to make mistakes because the types look very similar.

### 5.1. Mono<ResponseEntity<T>>

```java
Mono<ResponseEntity<Book>> pending = reactiveApi.getBookResponse(7);

Mono<String> summary = pending.map(entity ->
        "status=" + entity.getStatusCode().value()
                + ", title=" + entity.getBody().title());
```

The item emitted by `Mono` is **one ResponseEntity that already has status/headers and the decoded Book body**. `getBody()` can still be null if the endpoint returns no body; the example code above assumes HTTP 200 with valid JSON. Use `Mono<ResponseEntity<T>>` when you want to handle both body and status together.

### 5.2. Mono<ResponseEntity<Flux<T>>>

```java
Mono<ResponseEntity<Flux<Book>>> pending =
        reactiveApi.streamWithResponse();

Mono<Integer> count = pending.flatMap(entity -> {
    int status = entity.getStatusCode().value();
    Flux<Book> body = entity.getBody();
    if (status != 200 || body == null) {
        return Mono.error(new IllegalStateException(
                "Unexpected status or missing body"));
    }
    return body.count().map(Long::intValue);
});
```

**Two async levels:** the outer `Mono` emits the `ResponseEntity` containing status/headers; the inner `Flux<Book>` represents the body that can be consumed as a stream. This type is useful when you need access to response metadata **without collecting the entire stream into a list first**. Because it can stream, avoid `collectList()` on very large or unbounded streams without bounds.

### 5.3. Why Not Default to ResponseEntity<Mono<T>>?

In a **WebFlux controller** (server), types like `ResponseEntity<Mono<Book>>` or `Mono<ResponseEntity<Book>>` differ depending on whether status/headers are available before or after the publisher. However, **return types supported by an HTTP Interface Client proxy depend on the HTTP adapter's documentation**. With `WebClientAdapter`, choose officially supported types such as `Mono<ResponseEntity<T>>` or `Mono<ResponseEntity<Flux<T>>>`; do not copy the WebFlux controller return table onto a client interface assuming every type is supported.

## 6. Runnable Java 17+ Example: Comparing Against the Same Server

The demo below runs an in-process HTTP server using the JDK and calls it via both `RestClientAdapter` and `WebClientAdapter`. The server exposes two endpoints:

- `GET /books/7`: returns one `Book` with header `X-Source`.
- `GET /books`: returns a JSON array of two books.

The demo verifies `Book`, `ResponseEntity<Book>`, `Mono<Book>`, `Mono<ResponseEntity<Book>>`, and `Flux<Book>`. The console program is allowed to use `block(Duration)` to wait for final results; typical reactive applications should continue returning publishers.

**Structure:**

```text
http-service-client-demo/
  build.gradle
  src/main/java/demo/HttpServiceReturnDemo.java
```

**build.gradle**:

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation platform('org.springframework.boot:spring-boot-dependencies:3.3.6')
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
}

application {
    mainClass = 'demo.HttpServiceReturnDemo'
}
```

**src/main/java/demo/HttpServiceReturnDemo.java**:

```java
package demo;

import com.sun.net.httpserver.HttpServer;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.support.RestClientAdapter;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.reactive.function.client.support.WebClientAdapter;
import org.springframework.web.service.annotation.GetExchange;
import org.springframework.web.service.invoker.HttpServiceProxyFactory;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.List;

public class HttpServiceReturnDemo {
    public record Book(long id, String title) {}

    interface SyncBooks {
        @GetExchange("/books/{id}")
        Book getBook(@PathVariable("id") long id);

        @GetExchange("/books/{id}")
        ResponseEntity<Book> getResponse(@PathVariable("id") long id);
    }

    interface ReactiveBooks {
        @GetExchange("/books/{id}")
        Mono<Book> getBook(@PathVariable("id") long id);

        @GetExchange("/books/{id}")
        Mono<ResponseEntity<Book>> getResponse(
                @PathVariable("id") long id);

        @GetExchange("/books")
        Flux<Book> getAllBooks();
    }

    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 0);

        server.createContext("/books", exchange -> {
            try {
                String path = exchange.getRequestURI().getPath();
                String json;
                int status;

                if (!"GET".equals(exchange.getRequestMethod())) {
                    json = "{\"error\":\"method not allowed\"}";
                    status = 405;
                } else if ("/books/7".equals(path)) {
                    json = "{\"id\":7,\"title\":\"Reactive Java\"}";
                    status = 200;
                } else if ("/books".equals(path)) {
                    json = "[{\"id\":7,\"title\":\"Reactive Java\"},"
                            + "{\"id\":8,\"title\":\"Spring HTTP\"}]";
                    status = 200;
                } else {
                    json = "{\"error\":\"not found\"}";
                    status = 404;
                }

                byte[] data = json.getBytes(StandardCharsets.UTF_8);
                exchange.getResponseHeaders()
                        .set("Content-Type", "application/json");
                exchange.getResponseHeaders().set("X-Source", "local-api");
                exchange.sendResponseHeaders(status, data.length);
                try (OutputStream out = exchange.getResponseBody()) {
                    out.write(data);
                }
            } finally {
                exchange.close();
            }
        });

        server.start();
        try {
            String baseUrl = "http://127.0.0.1:"
                    + server.getAddress().getPort();

            RestClient restClient = RestClient.builder()
                    .baseUrl(baseUrl)
                    .build();
            SyncBooks sync = HttpServiceProxyFactory
                    .builderFor(RestClientAdapter.create(restClient))
                    .build()
                    .createClient(SyncBooks.class);

            WebClient webClient = WebClient.builder()
                    .baseUrl(baseUrl)
                    .build();
            ReactiveBooks reactive = HttpServiceProxyFactory
                    .builderFor(WebClientAdapter.create(webClient))
                    .build()
                    .createClient(ReactiveBooks.class);

            Book direct = sync.getBook(7);
            System.out.println("sync=" + direct.id()
                    + "/" + direct.title());

            ResponseEntity<Book> syncResponse = sync.getResponse(7);
            System.out.println("sync status="
                    + syncResponse.getStatusCode().value()
                    + ", source="
                    + syncResponse.getHeaders().getFirst("X-Source"));

            Mono<Book> pending = reactive.getBook(7);
            Book asyncBook = pending.block(Duration.ofSeconds(5));
            System.out.println("reactive=" + asyncBook.id()
                    + "/" + asyncBook.title());

            ResponseEntity<Book> asyncResponse = reactive
                    .getResponse(7)
                    .block(Duration.ofSeconds(5));
            System.out.println("reactive status="
                    + asyncResponse.getStatusCode().value());

            List<Book> allBooks = reactive.getAllBooks()
                    .collectList()
                    .block(Duration.ofSeconds(5));
            System.out.println("books=" + allBooks.size());
        } finally {
            server.stop(0);
        }
    }
}
```

To run: install JDK 17+ and Gradle; in the `http-service-client-demo` directory run:

```bash
gradle run
```

If the project has a Gradle Wrapper, use `./gradlew run` on Unix/macOS or `gradlew.bat run` on Windows.

**Lines printed to stdout by the program** (excluding dependency download/Gradle logs):

```text
sync=7/Reactive Java
sync status=200, source=local-api
reactive=7/Reactive Java
reactive status=200
books=2
```

Explanation:

1. `sync.getBook(7)` uses `RestClient` and returns a `Book` object after the synchronous HTTP call.
2. `sync.getResponse(7)` additionally returns status 200 and header `X-Source: local-api`.
3. `reactive.getBook(7)` returns `Mono<Book>`; `block` in `main` triggers the pipeline and waits for the value.
4. `reactive.getResponse(7)` wraps the entire response in `Mono<ResponseEntity<Book>>`.
5. `reactive.getAllBooks()` returns `Flux<Book>`, and `collectList` gathers it into two elements. This is reasonable for a two-item example; for large streams, keep processing item by item.

The demo uses the JDK's `HttpServer`; no separate Spring Boot server is required. The URL uses an OS-assigned port so it does not depend on a fixed port.

## 7. When to Choose Which Return Type?

| Practical need | Appropriate adapter | Suggested return type |
| --- | --- | --- |
| Sequential app, needs one DTO | `RestClientAdapter` | `Book` |
| Call API to trigger, discard body | `RestClientAdapter` | `void` |
| Only need synchronous headers | `RestClientAdapter` | `HttpHeaders` |
| DELETE needing 204 check | `RestClientAdapter` | `ResponseEntity<Void>` |
| Read body and HTTP metadata synchronously | `RestClientAdapter` | `ResponseEntity<Book>` |
| WebFlux service reading one DTO | `WebClientAdapter` | `Mono<Book>` |
| WebFlux reading multi-item stream | `WebClientAdapter` | `Flux<Book>` |
| WebFlux command caring only about completion | `WebClientAdapter` | `Mono<Void>` |
| WebFlux needing status/headers with one DTO | `WebClientAdapter` | `Mono<ResponseEntity<Book>>` |
| WebFlux needing status/headers before consuming body stream | `WebClientAdapter` | `Mono<ResponseEntity<Flux<Book>>>` |

The choice rests on three questions: (1) is the caller running synchronously or reactively? (2) do you need only the body or also status/headers? (3) does the response have 0, 1, or many elements, and is true streaming required?

**Do not convert reactive into blocking** just to return `Book`. If upper layers use `Mono`/`Flux`, keep the reactive chain to the system boundary. If the application needs synchronous calls, `RestClient` is usually simpler than `WebClient` with synchronous return types.

## 8. HTTP Errors, Timeouts, and ResponseEntity Scope

### 8.1. ResponseEntity Does Not Mean Accepting Every Status

With default configuration, HTTP 4xx/5xx statuses are usually turned into exceptions/error signals by the client:

- `RestClientAdapter`: via `RestClient`, HTTP errors are normally reflected as `RestClientResponseException` and related subtypes.
- `WebClientAdapter`: via `WebClient`, HTTP errors are normally reflected as `WebClientResponseException` on the reactive error channel.

This still holds when declaring `ResponseEntity<T>`; do not expect `ResponseEntity<Book>` to automatically hold a 404 error body in all cases. To map statuses differently, configure an **error/status handler on the underlying HTTP client** or handle errors intentionally in the service layer.

Reactive error handling example while keeping `Mono<Book>`:

```java
Mono<Book> book = reactiveApi.getBook(7)
        .onErrorResume(
                org.springframework.web.reactive.function.client
                        .WebClientResponseException.NotFound.class,
                notFound -> Mono.empty());
```

Here 404 is intentionally converted to an empty completion. Do not apply this blindly to every endpoint: some APIs use 404 to indicate misconfiguration or access issues that should not be silently ignored.

Synchronous example:

```java
try {
    Book book = syncApi.getBook(7);
} catch (org.springframework.web.client.HttpClientErrorException.NotFound ex) {
    // Handle specifically when the server returns HTTP 404.
}
```

The error handling snippets above assume `syncApi`/`reactiveApi` were created with default client settings. Actual exception types depend on the adapter and status handler.

### 8.2. Timeouts and Blocking

With `RestClientAdapter`, sync calls block until completion or timeout/configuration error. With `WebClientAdapter`, `Mono`/`Flux` do not force the caller thread to wait; however, **synchronous types** used with the reactive adapter will wait for the result. That can stall the event loop and negate reactive benefits.

Choose appropriate connect/read/response timeouts on the underlying HTTP client. With `WebClientAdapter`, Spring also supports configuring a block timeout for blocking calls, though configuring actual timeouts on the HTTP connector is usually better for controlling connection/read behavior. `Mono.timeout(Duration)` applies at the reactive pipeline level but does not replace all network settings.

Do not call `block()` inside a WebFlux controller, Netty event loop, or code maintaining continuous reactive processing. If interacting with a blocking library is necessary, consider isolating a boundary and offloading blocking work to a dedicated scheduler; this **does not make a blocking library non-blocking**.

### 8.3. Retries and HTTP Request Counts

A cold reactive publisher may re-issue the request upon re-subscription or when using `retry(...)`. For idempotent GETs, bounded retries can fit certain network/transient errors; for POSTs creating records/orders, a clear idempotency contract is required. Do not blindly retry 4xx errors, and do not equate `Mono.empty()` signals with HTTP 404.

## 9. Common Confusions

1. **Declaring `Mono<T>` while using RestClientAdapter.** The sync adapter does not support reactive returns like WebClientAdapter; keep adapter/return type consistent.
2. **Thinking WebClient is always non-blocking when returning `T`.** A sync method still waits for a value; reactive client support for sync returns does not make every execution flow non-blocking.
3. **Thinking `Mono<T>` is an already-available result.** It is a publisher; typically no HTTP I/O happens before subscription.
4. **Using `ResponseEntity<T>` when only the body is needed.** Return `T` or `Mono<T>` directly to reduce coupling to HTTP details.
5. **Discarding status/headers when workflows need ETag, Location, or 202.** Use `ResponseEntity<T>`, `ResponseEntity<Void>`, or their reactive equivalents.
6. **Confusing `Mono<ResponseEntity<T>>` with `ResponseEntity<Mono<T>>`.** Wrapper order determines when status/headers become available; controller return tables are not the HTTP Interface Client contract.
7. **Assuming `Flux<T>` means the server always streams.** Appropriate media type/codec and endpoint are required; a small JSON array may be sent as a complete response.
8. **Ignoring empty responses.** `Mono<Void>` and `ResponseEntity<Void>` have distinct meanings; `getBody()` can be null.
9. **Using ResponseEntity to "catch" 404 errors in all cases.** The underlying client's default error handler may already turn 404 into an exception.
10. **Blocking on the event loop or retrying POSTs uncontrolled.** Respect the execution model and idempotency.
11. **Loading too much data into memory with `collectList()`.** Useful for small lists, but unsuitable for unbounded streams or large payloads.
12. **Confusing server controllers with HTTP interface proxies.** Client-side `ResponseEntity` carries a response from another service; controller-side builds the application's own HTTP response.

## 10. Practice Exercises

**Exercise 1 — Choose the type:** Endpoint `DELETE /jobs/{id}` returns 204 and header `X-Audit-Id`. Write one synchronous method and one reactive method that can still read status/headers. Hint: `ResponseEntity<Void>` and `Mono<ResponseEntity<Void>>`.

**Exercise 2 — Compare returns:** In the demo, add `HttpHeaders getHeaders(long id)` to `SyncBooks` and print `X-Source`. Then add the corresponding `Mono<HttpHeaders>` to `ReactiveBooks`. Explain how accessing headers differs from decoding the body.

**Exercise 3 — Status and stream:** Suppose `/books` returns many books via NDJSON and you need to read `X-Next-Cursor`. Explain why `Mono<ResponseEntity<Flux<Book>>>` expresses this need better than `Mono<List<Book>>`, and why `collectList()` must be avoided with unbounded streams.

**Exercise 4 — Debug errors:** Replace `/books/7` with `/books/404` in the demo. The server will return HTTP 404. Observe the difference: the sync method throws at call time, while the reactive `Mono` emits an error when subscribed. Why does returning `ResponseEntity<Book>` not guarantee you can read status 404 as a normal response?

## Official References

- Spring Framework 6.2, REST Clients / HTTP Interface / Return Values: https://docs.spring.io/spring-framework/reference/6.2/integration/rest-clients.html
- Spring WebClient: https://docs.spring.io/spring-framework/reference/6.2/web/webflux-webclient.html
- WebClientAdapter Javadoc: https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/web/reactive/function/client/support/WebClientAdapter.html
- RestClientAdapter Javadoc: https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/web/client/support/RestClientAdapter.html
