# retrieve and decoding with bodyToMono, bodyToFlux

**Context:** Spring Framework Reactive → **Reading WebClient Responses**.

After sending a request with `WebClient`, the application needs to decide how to receive the response body. For the standard flow, `retrieve()` creates a `ResponseSpec` to declare how to extract the response. The two most important APIs are:

- `bodyToMono(T.class)`: decodes the body into at most one value of type `T` and returns `Mono<T>`.
- `bodyToFlux(T.class)`: decodes the body into a stream of zero, one, or more elements of type `T` and returns `Flux<T>`.

Both use Spring WebFlux codecs to convert bytes into Java objects. The target Java type, the response `Content-Type`, and the configured codecs must be compatible. By default, responses with a 4xx or 5xx status become a `WebClientResponseException`; this can be changed with `onStatus`.

This lesson focuses on **reading the response**. Distinguish between the request header `Accept` (which representation the client wants to receive) and the response header `Content-Type` (which representation the server actually sends).

## 1. Where does retrieve() sit in the request chain?

A WebClient call typically consists of four stages:

```text
WebClient
   |
   v
get() / post() / method(...)
   |
   v
uri(...) + headers(...) + body(...)
   |
   v
retrieve()
   |
   v
ResponseSpec
   |
   +---- onStatus(...)       map HTTP error
   |
   +---- bodyToMono(T)       decode 0..1 value
   |
   +---- bodyToFlux(T)       decode 0..N values
   |
   +---- toEntity(T)         status + headers + body
   |
   v
Mono / Flux
   |
   v
subscribe / compose with caller
```

Example of fetching a single book:

```java
Mono<Book> book = webClient.get()
        .uri("/books/{id}", 42)
        .accept(MediaType.APPLICATION_JSON)
        .retrieve()
        .bodyToMono(Book.class);
```

`retrieve()` does not return `Book` yet. It returns a `ResponseSpec` so you can continue choosing how to decode. `bodyToMono` returns a publisher; the request typically only executes when the publisher is subscribed to by the framework or caller.

Example of reading a list:

```java
Flux<Book> books = webClient.get()
        .uri("/books")
        .accept(MediaType.APPLICATION_JSON)
        .retrieve()
        .bodyToFlux(Book.class);
```

If you want to obtain HTTP metadata along with the body, use `toEntity` or its corresponding variants instead of fetching only the body.

## 2. bodyToMono: decoding at most one object

`bodyToMono(Class<T>)` instructs the codec to decode the response body into a single value of type `T`:

```java
Mono<Book> bookMono = webClient.get()
        .uri("/books/42")
        .retrieve()
        .bodyToMono(Book.class);
```

`Mono<T>` has three important outcomes:

- Emits exactly one object and then completes.
- Completes without emitting an object if the response has no body.
- Emits an error if the status is treated as an error, transport fails, or decoding fails.

`Mono` does not mean "always has a value." If the endpoint can return 204 or an empty body, handle the empty branch explicitly.

### 2.1. When to use it?

`bodyToMono` is suitable for:

- GETting a resource by ID.
- POSTing to create a resource and receiving the created object.
- An endpoint returning a single JSON object.
- A text or bytes response that needs to be read as a single value.
- An API that only confirms success via status and needs no content (you can use `Void.class` or `toBodilessEntity()`).

Example:

```java
Mono<Book> book = webClient.get()
        .uri("/books/42")
        .retrieve()
        .bodyToMono(Book.class);

Mono<String> text = webClient.get()
        .uri("/health/message")
        .retrieve()
        .bodyToMono(String.class);

Mono<byte[]> bytes = webClient.get()
        .uri("/files/cover")
        .retrieve()
        .bodyToMono(byte[].class);
```

The appropriate codec will be selected based on the target type and response media type. For example, `String` typically uses a text decoder, `byte[]` uses a byte-array decoder, and a JSON DTO uses the Jackson codec if dependencies and configuration provide that codec.

### 2.2. Empty body and Mono.empty()

With a 204 response or a body with no content, `bodyToMono(Book.class)` may complete empty. Do not assume it creates an empty `Book`.

```java
Mono<Book> result = webClient.get()
        .uri("/books/42")
        .retrieve()
        .bodyToMono(Book.class)
        .switchIfEmpty(Mono.error(
                new IllegalStateException("Book response is empty")));
```

If empty is valid, use a fallback or an optional representation:

```java
Mono<Book> result = webClient.get()
        .uri("/books/42")
        .retrieve()
        .bodyToMono(Book.class)
        .defaultIfEmpty(Book.notAvailable());
```

`Book.notAvailable()` is an illustrative factory method on the DTO. You can use `blockOptional()` at an imperative boundary to distinguish presence/absence of a value, but in a reactive service, compose using `switchIfEmpty`, `defaultIfEmpty`, or `hasElement`.

Do not use `defaultIfEmpty` to mask an error response or a decode error. Empty and error are two different signals.

### 2.3. Reading a response with no body

If you only need to wait for the HTTP operation to complete and do not need the body:

```java
Mono<Void> deleted = webClient.delete()
        .uri("/books/42")
        .retrieve()
        .bodyToMono(Void.class);
```

If you also need the status and headers without the body:

```java
Mono<ResponseEntity<Void>> deleted = webClient.delete()
        .uri("/books/42")
        .retrieve()
        .toBodilessEntity();
```

`Void.class` is not a DTO type to deserialize. It indicates that the caller does not need to receive a body.

## 3. bodyToFlux: decoding multiple elements

`bodyToFlux(Class<T>)` returns `Flux<T>`. The publisher can emit 0..N elements, suitable for lists, event streams, or long data sources:

```java
Flux<Book> books = webClient.get()
        .uri("/books")
        .accept(MediaType.APPLICATION_JSON)
        .retrieve()
        .bodyToFlux(Book.class);
```

You can process each element without collecting the entire list:

```java
return webClient.get()
        .uri("/books")
        .retrieve()
        .bodyToFlux(Book.class)
        .filter(book -> book.active())
        .map(Book::toSummary);
```

Each item is emitted as soon as the decoder can decode that item. Downstream can apply backpressure, cancel the subscription, or combine with other publishers.

### 3.1. JSON array and NDJSON

A JSON array response can be decoded into individual items:

```json
[
  {"id": 1, "title": "Reactive"},
  {"id": 2, "title": "WebFlux"}
]
```

`bodyToFlux(Book.class)` can emit two `Book` instances when the codec supports that representation.

For data emitted line by line, NDJSON (newline-delimited JSON) is an appropriate choice:

```http
HTTP/1.1 200 OK
Content-Type: application/x-ndjson

{"id":1,"title":"Reactive"}
{"id":2,"title":"WebFlux"}
```

Client:

```java
Flux<Book> books = webClient.get()
        .uri("/books/stream")
        .accept(MediaType.APPLICATION_NDJSON)
        .retrieve()
        .bodyToFlux(Book.class);
```

NDJSON represents each JSON object on a single line. The server can send lines over time, and the client receives the corresponding objects as the data arrives. Use the media type that matches the protocol the server actually emits.

### 3.2. Flux does not automatically turn a response into a streaming protocol

The return type `Flux<T>` does not by itself determine framing on the wire. Decoding and incremental emission depend on:

- `Content-Type` and body format.
- The configured codec/decoder.
- Whether the server flushes incrementally or buffers the whole response.
- The HTTP connector, proxy, and network buffering.
- Whether client-side operators aggregate the data.

For long streams, use an appropriate streaming media type such as NDJSON or SSE. Do not assume a large JSON array always has the same memory and latency behavior as NDJSON.

### 3.3. Do not call collectList() on an unbounded source

`collectList()` turns a Flux into a `Mono<List<T>>` and must hold all elements before emitting the list:

```java
Mono<List<Book>> allBooks = webClient.get()
        .uri("/books")
        .retrieve()
        .bodyToFlux(Book.class)
        .collectList();
```

This approach is suitable for finite, bounded lists where you genuinely need to process everything at once. Do not use it for SSE, unbounded event streams, or very large responses; memory will grow with the number of items.

If aggregation is needed, consider `take(n)`, `bufferTimeout`, pagination, limiting results, or processing item by item.

## 4. Codecs determine how bytes become objects

`retrieve()` does not parse JSON on its own with a separate converter. WebClient uses `HttpMessageReader` and codecs registered in `ExchangeStrategies` to decode the body.

Some common types:

| Response body | Target type | Example |
|---|---|---|
| JSON object | DTO | `bodyToMono(Book.class)` |
| JSON array | each DTO | `bodyToFlux(Book.class)` |
| JSON object with generics | `ParameterizedTypeReference` | `bodyToMono(typeRef)` |
| NDJSON | each DTO | `bodyToFlux(Book.class)` |
| Text | `String` | `bodyToMono(String.class)` |
| Binary | `byte[]` or `DataBuffer` | `bodyToMono(byte[].class)` |
| No body needed | `Void` | `bodyToMono(Void.class)` |

The request header `Accept` helps the server choose a representation. The response `Content-Type` indicates the actual format so the codec can select a decoder. If the server returns XML while the client only has a JSON codec, decoding may fail even if the Java class is right.

Example of explicitly declaring Accept:

```java
Mono<Book> result = webClient.get()
        .uri("/books/42")
        .accept(MediaType.APPLICATION_JSON)
        .retrieve()
        .bodyToMono(Book.class);
```

`Accept` does not force the server to comply; the server may return 406 if it cannot provide the requested representation, or return an unexpected type due to a misconfigured API/proxy.

## 5. Decoding generic types with ParameterizedTypeReference

Java type erasure means `List<Book>.class` does not exist. If the response is a generic object such as:

```json
{
  "data": [
    {"id": 1, "title": "Reactive"},
    {"id": 2, "title": "WebFlux"}
  ],
  "nextCursor": "page-2"
}
```

Create a type reference to preserve full type information:

```java
record Page<T>(List<T> data, String nextCursor) {}

ParameterizedTypeReference<Page<Book>> type =
        new ParameterizedTypeReference<>() {};

Mono<Page<Book>> page = webClient.get()
        .uri("/books")
        .retrieve()
        .bodyToMono(type);
```

Or declare it inline:

```java
Mono<Page<Book>> page = webClient.get()
        .uri("/books")
        .retrieve()
        .bodyToMono(
                new ParameterizedTypeReference<Page<Book>>() {});
```

With a Flux emitting generic elements:

```java
ParameterizedTypeReference<Map<String, Object>> rowType =
        new ParameterizedTypeReference<>() {};

Flux<Map<String, Object>> rows = webClient.get()
        .uri("/reports/rows")
        .retrieve()
        .bodyToFlux(rowType);
```

The type reference describes **the type of the body or of each element**, depending on the method:

- `bodyToMono(Page<Book>)` describes a single Page containing Book items.
- `bodyToFlux(Map<String,Object>)` describes each emitted item as a Map.

Do not use `List.class` and then cast elements to DTOs. The decoder will lack the generic type information to deserialize accurately, and errors may only surface at the later cast step.

## 6. Getting status and headers with toEntity

`bodyToMono` and `bodyToFlux` only return the body. If you need the status, headers, or `Location`, use `toEntity`:

```java
Mono<ResponseEntity<Book>> response = webClient.get()
        .uri("/books/42")
        .retrieve()
        .toEntity(Book.class);
```

After receiving the entity:

```java
return response.map(entity -> {
    HttpStatusCode status = entity.getStatusCode();
    HttpHeaders headers = entity.getHeaders();
    Book book = entity.getBody();

    return new BookResult(status, headers.getETag(), book);
});
```

`toEntity` still decodes the body via the codec, and default error status handling still applies. Use it when the caller needs HTTP metadata alongside the DTO.

Related options:

| Method | Result | When to use |
|---|---|---|
| `bodyToMono(T.class)` | `Mono<T>` | Only a single body object is needed |
| `bodyToFlux(T.class)` | `Flux<T>` | Only a stream of items is needed |
| `toEntity(T.class)` | `Mono<ResponseEntity<T>>` | Status, headers, and body are needed |
| `toEntityList(T.class)` | `Mono<ResponseEntity<List<T>>>` | Metadata and an aggregated list are needed |
| `toEntityFlux(T.class)` | `Mono<ResponseEntity<Flux<T>>>` | Metadata and a body stream are needed |
| `toBodilessEntity()` | `Mono<ResponseEntity<Void>>` | Status/headers are needed, no body needed |

### 6.1. toEntityFlux and body lifecycle

`toEntityFlux` returns response metadata in `Mono<ResponseEntity<Flux<T>>>`. The body is still a publisher; the caller must consume it:

```java
Mono<List<Book>> books = webClient.get()
        .uri("/books/stream")
        .retrieve()
        .toEntityFlux(Book.class)
        .flatMap(entity -> entity.getBody().collectList());
```

If you keep `ResponseEntity<Flux<T>>` to return elsewhere, ensure the stream is subscribed to/consumed with the proper lifecycle. Do not inspect the headers and abandon the body; unconsumed response content can hold connections/resources until released according to the client's contract.

## 7. Default handling of 4xx and 5xx statuses

When using `retrieve()`, Spring treats statuses of 400 and above as errors by default. The body publisher will emit a `WebClientResponseException` or a status-specific subclass, such as `WebClientResponseException.NotFound`.

Example:

```java
Mono<Book> book = webClient.get()
        .uri("/books/999")
        .retrieve()
        .bodyToMono(Book.class);
```

If the server returns 404, `Mono<Book>` does not complete empty by default. It emits a `WebClientResponseException.NotFound` error.

You can handle it downstream:

```java
return webClient.get()
        .uri("/books/{id}", id)
        .retrieve()
        .bodyToMono(Book.class)
        .onErrorResume(
                WebClientResponseException.NotFound.class,
                error -> Mono.empty());
```

Only do this if the API contract genuinely treats 404 as "no result." Do not turn every 4xx/5xx error into empty, because doing so can hide authentication failures, rate limits, server outages, or contract violations.

### 7.1. Distinguishing HTTP errors, transport errors, and decode errors

| Category | Example | How it is observed |
|---|---|---|
| HTTP status error | 404, 429, 500 | `WebClientResponseException` |
| Transport/request error | DNS, connect reset, TLS, timeout | Typically `WebClientRequestException` or a connector error |
| Decode error | Malformed JSON, incompatible data type | Codec/decoder exception, typically `DecodingException` |
| Cancellation | Caller no longer needs the response | Cancel signal; not an HTTP status exception |

Proper classification prevents mistakes in retry and error mapping. For example, retrying a 500 may make sense depending on policy, but retrying malformed-schema JSON usually will not fix the problem. A cancelled request is also not an error to retry automatically.

## 8. Customizing errors with onStatus

`onStatus(predicate, exceptionFunction)` lets you map a response status to a domain exception. The callback receives `ClientResponse` and must return `Mono<? extends Throwable>`.

Example mapping 404:

```java
Mono<Book> book = webClient.get()
        .uri("/books/{id}", id)
        .retrieve()
        .onStatus(
                status -> status.value() == 404,
                response -> response.bodyToMono(ApiError.class)
                        .defaultIfEmpty(
                                new ApiError("NOT_FOUND", "Book not found"))
                        .map(BookNotFoundException::new))
        .bodyToMono(Book.class);
```

This snippet requires the `ApiError` and `BookNotFoundException` record/exception types. Processing flow:

1. If the status is not 404, processing continues with default handling.
2. If the status is 404, the callback reads the error body into `ApiError`.
3. If the server sends no error body, `defaultIfEmpty` creates a fallback error object.
4. `map` creates the domain exception.
5. `bodyToMono(Book.class)` is not executed as a successful response; the publisher terminates with the domain exception.

Example mapping all 5xx errors:

```java
.onStatus(
        HttpStatusCode::is5xxServerError,
        response -> response.bodyToMono(String.class)
                .defaultIfEmpty("")
                .map(body -> new RemoteServiceException(
                        response.statusCode(), body)))
```

Do not put the entire error body into logs or public responses if the body may contain sensitive data. Limit length, mask data, and prefer stable error codes.

### 8.1. The onStatus callback must consume the error body when needed

The `ClientResponse` body is a stream. If you need the payload to build an exception, decode it inside the callback as shown in the example. Do not read the body multiple times or expect downstream to decode the same response body again after it has been consumed.

If the error body can be empty, use `defaultIfEmpty` when you still want to create an exception. If the callback returns `Mono.empty()`, Spring does not treat that status as an error and the response continues to be processed as a normal response. This is a way to intentionally skip an error handler for a specific case, not a way to discard the entire response.

### 8.2. Error bodies are not always JSON

An upstream may return JSON Problem Details, plain text, or an empty body. If the callback always uses `bodyToMono(ApiError.class)` while the server returns HTML/text, decoding may fail and obscure the original status.

You can read raw text when the format is unstable:

```java
.onStatus(
        HttpStatusCode::isError,
        response -> response.bodyToMono(String.class)
                .defaultIfEmpty("")
                .map(body -> new RemoteApiException(
                        response.statusCode(), body)))
```

If the API has a Problem Details contract, use an appropriate DTO or `ProblemDetail.class`. Do not assume every 4xx/5xx system shares the same schema.

## 9. When is retrieve() not enough?

`retrieve()` fits well when response handling is fairly uniform: error statuses are mapped, and then the body is decoded into a single type.

If you need to decide the body type based on status, inspect headers before decoding, or handle multiple distinct response branches, use `exchangeToMono` or `exchangeToFlux`:

```java
Mono<Book> result = webClient.get()
        .uri("/books/{id}", id)
        .exchangeToMono(response -> {
            if (response.statusCode().is2xxSuccessful()) {
                return response.bodyToMono(Book.class);
            }
            if (response.statusCode().value() == 404) {
                return Mono.empty();
            }
            return response.createError();
        });
```

This example intentionally maps 404 to empty and uses `createError()` for remaining statuses. Choose semantics according to the API contract.

A lifecycle difference to keep in mind: with `exchangeToMono`/`exchangeToFlux`, the callback must declare how to handle the body. After the callback publisher completes, Spring automatically releases the response body if the callback did not consume it. If you need the body, decode or consume it inside the callback; do not return a detached response publisher while ignoring ownership.

Do not use `exchangeToMono` simply because it looks lower-level. For most simple body cases, `retrieve()` is shorter and easier to read.

## 10. Media types and content negotiation

The client can request a representation using `Accept`:

```java
webClient.get()
        .uri("/books/stream")
        .accept(MediaType.APPLICATION_NDJSON)
        .retrieve()
        .bodyToFlux(Book.class);
```

The server returns `Content-Type` to identify the actual representation. Some common media types:

| Media type | Meaning | Common read pattern |
|---|---|---|
| `application/json` | JSON object or array | `bodyToMono` / `bodyToFlux` |
| `application/x-ndjson` | One JSON object per line | `bodyToFlux` |
| `text/event-stream` | Server-Sent Events | `bodyToFlux(ServerSentEvent<T>)` |
| `text/plain` | Text | `bodyToMono(String.class)` |
| `application/octet-stream` | Binary | `byte[]` or `DataBuffer` |
| `application/problem+json` | HTTP Problem Details | Error DTO or `ProblemDetail` |

Example of reading SSE:

```java
ParameterizedTypeReference<ServerSentEvent<Book>> eventType =
        new ParameterizedTypeReference<>() {};

Flux<ServerSentEvent<Book>> events = webClient.get()
        .uri("/books/events")
        .accept(MediaType.TEXT_EVENT_STREAM)
        .retrieve()
        .bodyToFlux(eventType);
```

If you only need the event data, you can map `ServerSentEvent<Book>::data` after decoding. However, if you need the event ID, event name, or retry metadata, keep `ServerSentEvent` intact.

If `Accept` and server capabilities do not overlap, the server may return 406. If the response `Content-Type` has no matching decoder, the client may encounter a decode error. Do not work around codec issues by forcing every response into a String and parsing manually when standard codecs can handle it properly.

## 11. Memory, streaming, and backpressure

`bodyToMono` generally suits finite, single-value bodies. `bodyToFlux` suits multiple elements, but does not by itself guarantee stable memory usage.

Guidelines:

- Use a streaming media type and appropriate decoder for large or long-lived streams.
- Avoid `collectList()` if the item count is unbounded.
- Configure codec memory limits appropriate to the payload; do not raise them indefinitely to hide bugs.
- Avoid `bodyToMono(String.class)` for large files.
- When handling `DataBuffer` directly, follow buffer ownership and release contracts.
- Limit downstream concurrency if each item triggers another request.
- Use `limitRate` or appropriate operators when demand throttling is needed; understand the prefetch of the operators you use.
- Let cancellation propagate through publishers; do not call a detached `subscribe()` in a service.

Example of processing item by item:

```java
return webClient.get()
        .uri("/events")
        .accept(MediaType.APPLICATION_NDJSON)
        .retrieve()
        .bodyToFlux(Event.class)
        .concatMap(event ->
                eventService.process(event));
```

`concatMap` processes sequentially and preserves order; if concurrency is needed, choose `flatMap` with an appropriate limit. Do not use `collectList()` merely so you can run an imperative loop if the source can emit many items.

## 12. Common decode errors

### 12.1. DTO does not match JSON

If the JSON contains a field incompatible with the Java type, the decoder may emit an error. Check:

- Field names and nested object structure.
- Numeric types, booleans, enums, timestamps.
- Constructors/records and Jackson configuration.
- Nullability and required fields.
- Upstream version/schema.

Do not map an error payload into a default DTO by swallowing all exceptions. Doing so can let bad data travel deep into the domain.

### 12.2. Wrong Content-Type

A server may return JSON while declaring `text/plain`, or return an HTML proxy error while declaring JSON. Codecs choose a decoder based on media type; errors can occur even if the bytes look like JSON.

Fix the server contract if possible. If you must work with a non-compliant upstream, isolate the workaround in a dedicated adapter and test it explicitly.

### 12.3. Body already consumed

The response body is a stream that can be consumed once. If a filter or callback has already read the body, downstream cannot read it again by default. When you need to log and decode the same body, you must design bounded buffering/rebuilding with proper memory management; better yet, log metadata or normalized error codes.

## 13. Runnable Java 17+ program: retrieve, Mono, Flux, and onStatus

The example below spins up a local HTTP server using Reactor Netty. WebClient calls that server to read a JSON object, an NDJSON stream, an empty response, and a 404 response. It demonstrates both default error handling and mapping errors to a custom exception.

Structure:

```text
webclient-response-decode-demo/
├── pom.xml
└── src/main/java/demo/WebClientResponseDecodeDemo.java
```

### 13.1. pom.xml

```xml
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

    <groupId>demo</groupId>
    <artifactId>webclient-response-decode-demo</artifactId>
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
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.4.1</version>
            </plugin>
        </plugins>
    </build>
</project>
```

### 13.2. WebClientResponseDecodeDemo.java

```java
package demo;

import org.springframework.core.ParameterizedTypeReference;
import org.springframework.http.HttpStatusCode;
import org.springframework.http.MediaType;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.reactive.function.client.WebClientResponseException;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.netty.DisposableServer;
import reactor.netty.http.server.HttpServer;

import io.netty.handler.codec.http.HttpResponseStatus;

import java.util.List;

public class WebClientResponseDecodeDemo {

    public record Book(int id, String title) { }

    public record ApiError(String code, String message) { }

    public static final class RemoteApiException
            extends RuntimeException {

        private final ApiError error;

        public RemoteApiException(ApiError error) {
            super(error.code() + ": " + error.message());
            this.error = error;
        }

        public ApiError error() {
            return error;
        }
    }

    public static void main(String[] args) {
        DisposableServer server = HttpServer.create()
                .host("127.0.0.1")
                .port(0)
                .route(routes -> routes
                        .get("/book", (request, response) ->
                                response.header(
                                                "Content-Type",
                                                "application/json")
                                        .sendString(Mono.just(
                                                "{\"id\":42,"
                                                + "\"title\":\"Reactive WebClient\"}")))
                        .get("/books", (request, response) ->
                                response.header(
                                                "Content-Type",
                                                "application/x-ndjson")
                                        .sendString(Flux.just(
                                                "{\"id\":1,\"title\":\"Reactive\"}\n",
                                                "{\"id\":2,\"title\":\"WebFlux\"}\n")))
                        .get("/empty", (request, response) ->
                                response.status(
                                                HttpResponseStatus.NO_CONTENT)
                                        .send())
                        .get("/missing", (request, response) ->
                                response.status(
                                                HttpResponseStatus.NOT_FOUND)
                                        .header(
                                                "Content-Type",
                                                "application/json")
                                        .sendString(Mono.just(
                                                "{\"code\":\"BOOK_NOT_FOUND\","
                                                + "\"message\":\"Book not found\"}")))
                )
                .bindNow();

        try {
            String baseUrl =
                    "http://127.0.0.1:" + server.port();

            WebClient client = WebClient.builder()
                    .baseUrl(baseUrl)
                    .build();

            Book book = client.get()
                    .uri("/book")
                    .accept(MediaType.APPLICATION_JSON)
                    .retrieve()
                    .bodyToMono(Book.class)
                    .block();

            List<Book> books = client.get()
                    .uri("/books")
                    .accept(MediaType.APPLICATION_NDJSON)
                    .retrieve()
                    .bodyToFlux(Book.class)
                    .collectList()
                    .block();

            boolean emptyBody = client.get()
                    .uri("/empty")
                    .retrieve()
                    .bodyToMono(Book.class)
                    .blockOptional()
                    .isEmpty();

            try {
                client.get()
                        .uri("/missing")
                        .retrieve()
                        .bodyToMono(Book.class)
                        .block();
            }
            catch (WebClientResponseException ex) {
                System.out.println(
                        "default error status="
                        + ex.getStatusCode().value());
            }

            try {
                client.get()
                        .uri("/missing")
                        .retrieve()
                        .onStatus(
                                HttpStatusCode::is4xxClientError,
                                response -> response
                                        .bodyToMono(ApiError.class)
                                        .defaultIfEmpty(new ApiError(
                                                "UNKNOWN",
                                                "No error body"))
                                        .map(RemoteApiException::new))
                        .bodyToMono(Book.class)
                        .block();
            }
            catch (RemoteApiException ex) {
                System.out.println(
                        "mapped error=" + ex.error().code());
            }

            System.out.println(
                    "book: " + book.id() + " / " + book.title());
            System.out.println("books count=" + books.size());
            System.out.println("empty body=" + emptyBody);
        }
        finally {
            server.disposeNow();
        }
    }
}
```

Run from the directory containing `pom.xml` with JDK 17+ and Maven:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.WebClientResponseDecodeDemo
```

**Expected standard output:**

```text
default error status=404
mapped error=BOOK_NOT_FOUND
book: 42 / Reactive WebClient
books count=2
empty body=true
```

Explanation:

1. The server binds port 0 so the OS selects a free port; WebClient uses the actual port.
2. `/book` returns a JSON object; `bodyToMono(Book.class)` decodes it into a record.
3. `/books` returns NDJSON with two lines; `bodyToFlux(Book.class)` decodes them into two items.
4. `collectList()` is only used in the demo because the response has exactly two finite items; large production streams should be processed item by item.
5. `/empty` returns 204; `bodyToMono(Book.class)` completes empty, so `blockOptional()` returns an empty Optional.
6. The first call to `/missing` uses default handling and receives a `WebClientResponseException` with status 404.
7. The second call uses `onStatus`, decodes the error body into `ApiError`, and emits `RemoteApiException`.
8. `block()` is only used in `main` so the demo program waits for results. Do not use block in controllers or reactive services.

This program runs local HTTP and uses real WebClient codecs. It demonstrates body decoding and status handling; it does not replace integration tests against production upstreams, TLS, or proxies.

## 14. Testing WebClient response decoding

Both the payload and the reactive signals should be tested:

- A JSON object is decoded into the right DTO.
- A JSON array or NDJSON emits the right number of items in the right order.
- Generic envelopes preserve the element type.
- An empty body produces an empty publisher according to the contract.
- 4xx/5xx emits WebClientResponseException by default.
- onStatus creates the expected domain exception and consumes the error body.
- A schema-invalid body emits a decode error.
- Accept and Content-Type match appropriately.
- Cancellation stops reading the stream when the caller no longer needs it.
- Large bodies are not unexpectedly aggregated.

Example using StepVerifier:

```java
StepVerifier.create(
        client.get()
                .uri("/books")
                .retrieve()
                .bodyToFlux(Book.class))
        .expectNextMatches(book ->
                book.id() == 1 && book.title().equals("Reactive"))
        .expectNextMatches(book ->
                book.id() == 2 && book.title().equals("WebFlux"))
        .verifyComplete();
```

This snippet requires the `reactor-test` dependency and a test server fixture. `StepVerifier` verifies signals without calling `block()`.

For HTTP client tests, MockWebServer or WireMock helps verify actual requests, headers, status, body, delays, and connection behavior. A fake `ExchangeFunction` works for small unit tests of logic, but it does not test real sockets, TLS, or codecs/connectors if you bypass those components.

## 15. Common mistakes

1. **Using bodyToMono for a multi-item response.** Choose `bodyToFlux` if the endpoint emits multiple objects.
2. **Assuming Mono always has a value.** Mono can complete empty; handle `switchIfEmpty` or `defaultIfEmpty`.
3. **Assuming 404 automatically becomes Mono.empty().** retrieve emits `WebClientResponseException` by default for 4xx/5xx statuses.
4. **Using bodyToFlux followed by collectList on an unbounded stream.** The publisher will never complete and the list keeps growing; process item by item.
5. **Using List.class for a generic DTO.** Type erasure loses the element type; use `ParameterizedTypeReference`.
6. **Confusing Accept and Content-Type.** Accept is the client's preference; Content-Type describes the actual response.
7. **Assuming Flux always streams on the wire.** Codecs, media types, server flushing, and proxy buffering all affect it.
8. **Not reading the error body in onStatus.** If the error payload is needed, decode it in the callback before the response body is released.
9. **Reading the error body twice.** The response body is a stream; design single-pass consumption and pass the decoded data into the exception.
10. **Returning Mono.empty from onStatus thinking it skips the response.** That skips error handling for that status; the body continues to be processed as a normal response.
11. **Catching every Exception and returning empty.** This can hide transport errors, schema mismatches, and server outages.
12. **Using toEntity when only the body is needed.** Not wrong, but creates unnecessary metadata; choose the API based on need.
13. **Using bodyToMono(String.class) for large files.** The entire body may be aggregated; consider streaming/binary APIs.
14. **Not checking Content-Type.** The codec may fail to find a compatible decoder or decode the wrong representation.
15. **Retrying all decode errors.** A schema-invalid payload usually cannot be fixed by retrying.
16. **Blocking in a reactive service.** Blocks threads and breaks composition/cancellation; return Mono/Flux to the caller.
17. **Subscribing manually in a service.** The caller loses control over error management, cancellation, and lifecycle.
18. **Keeping a Flux body without consuming it.** Can hold connections/resources; consume it or let the framework manage the lifecycle properly.
19. **Logging the raw error body.** Can leak tokens, PII, or internal details; mask and limit content.
20. **Using WebTestClient and assuming outbound WebClient is tested.** WebTestClient primarily tests server-side endpoints; use a mock HTTP server or ExchangeFunction for outbound clients.
21. **Treating HTTP errors and connection errors as identical.** 404 is a status response; DNS/TLS/timeout are transport failures.
22. **Treating a JSON null body, an empty body, and 404 as the same state.** They have different semantics; design clear mappings.
23. **Using bodyToFlux for a single JSON object.** If the server only emits one object, bodyToMono usually expresses the contract more clearly.
24. **Not testing stream cancellation.** The client may stop consuming; verify the upstream receives cancel and releases resources properly.

## 16. API selection checklist

Before finalizing a WebClient call, determine:

- Is the response a single object, a stream, or bodiless?
- Do you only need the body, or also the status and headers?
- Is the server's Content-Type compatible with the codec and Java type?
- Are there generic types requiring `ParameterizedTypeReference`?
- Can the body be empty? Does empty mean valid, not found, or a contract violation?
- Should 4xx/5xx use the default exception or `onStatus`?
- Is the error body JSON, Problem Details, text, or possibly empty?
- Is status-dependent decoding needed, warranting `exchangeToMono`/`exchangeToFlux`?
- Is the stream finite? Could `collectList()` accidentally aggregate it?
- Can the caller cancel? Are the response body and transport resources released?
- Are blocking/subscribing avoided in reactive application code?
- Do tests verify payload, status, headers, decode errors, empty, and cancellation?

**Key takeaway:** `retrieve()` declares how to obtain the response. `bodyToMono` decodes at most one object and can complete empty; `bodyToFlux` decodes a stream of elements. Codecs depend on the target type and media type. 4xx/5xx statuses emit `WebClientResponseException` by default; use `onStatus` to map upstream errors to domain exceptions. Use `toEntity` when metadata is needed, `ParameterizedTypeReference` for generic types, and `exchangeToMono` when status-dependent response control is required. Always keep the body within the reactive lifecycle and avoid aggregating unbounded streams.

## References

- Spring Framework — [retrieve(): decode response with bodyToMono and bodyToFlux](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-retrieve.html).
- Spring Framework — [WebClient.ResponseSpec Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/reactive/function/client/WebClient.ResponseSpec.html).
- Spring Framework — [WebClient exchange and response handling](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-exchange.html).
- Spring Framework — [WebClient request and response body codecs](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-body.html).
- Spring Framework — [WebClient synchronous use and blocking boundaries](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-synchronous.html).
- Project Reactor — [Mono and Flux reference](https://projectreactor.io/docs/core/release/reference/).
