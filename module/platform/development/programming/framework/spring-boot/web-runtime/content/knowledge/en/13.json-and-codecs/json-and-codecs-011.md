# Negotiating application/json, application/problem+json, and Streaming Formats in Spring Boot

## 1. Lesson Objectives

Spring Boot Web Runtime can return a JSON object, a **ProblemDetail** error payload, or a data stream transferred incrementally over HTTP. Although all three use Jackson, they **do not share the same `Content-Type`, encoding mechanics, or client parsing model**. You must clearly distinguish **application/json**, **application/problem+json**, and streaming media types such as **application/x-ndjson** or **text/event-stream**.

This lesson belongs to the **JSON and codecs** group. After studying it, you will be able to:

1. Explain the difference between **Content-Type** and **Accept**, and between Spring's **consumes** and **produces**.
2. Understand why requests can return **406 Not Acceptable**, **415 Unsupported Media Type**, **400 Bad Request**, or **404 Not Found**.
3. Use **ProblemDetail** per **RFC 9457** and choose **application/problem+json** for structured HTTP error responses.
4. Understand why **Flux<T> + application/json** does not necessarily stream, whereas **application/x-ndjson** emits one JSON document per line.
5. Use **text/event-stream** and **ServerSentEvent<T>** to push SSE events.
6. Build a runnable **Spring Boot 3.5, Java 17, WebFlux/Reactor Netty** demo supporting JSON, ProblemDetail, NDJSON, and SSE.
7. Test bodies, media types, status codes, streaming, post-commit error handling, and proxy/cache impacts.

The runnable project uses **Spring Boot 3.5.x + Spring Framework 6.2**, while **Spring MVC** equivalents are compared where useful. In Boot 4/Framework 7, consult branch-specific docs before copying configurations.

## 2. Three Different Questions in One HTTP Exchange

Example client request:

~~~http
POST /api/items HTTP/1.1
Content-Type: application/json
Accept: application/json, application/problem+json

{"name":"Book"}
~~~

Meaning:

- **Request Content-Type** states what **the outgoing body** is. Here it is `application/json`.
- **Request Accept** states **which response formats** the client can process; this may cover both success and error formats.
- **Response Content-Type** states which media type the server **actually returned**.

Success response:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"id":1,"name":"Book"}
~~~

Error response:

~~~http
HTTP/1.1 404 Not Found
Content-Type: application/problem+json

{
  "type": "about:blank",
  "title": "Item not found",
  "status": 404,
  "detail": "Item 99 does not exist",
  "instance": "/api/items/99",
  "code": "ITEM_NOT_FOUND"
}
~~~

**Common mistake:** sending `Content-Type: application/json` on a bodyless GET request to "ask the server for JSON." The header expressing **response** format preference is **Accept**.

| Component | Owner | Purpose |
|---|---|---|
| Request **Content-Type** | Client | Request body format |
| Request **Accept** | Client | Acceptable response representations |
| Controller **consumes** | Server | Restricts request body types accepted by the handler |
| Controller **produces** | Server | Restricts response types the handler can produce |
| Response **Content-Type** | Server | Actual format of the returned body |
| HTTP status | Server | Processing outcome, independent of body syntax |
| **Vary: Accept** | Server/cache | Useful when one URL returns different representations based on `Accept` |

### 2.1. Accept Can List Multiple Values

Example:

~~~http
Accept: application/json;q=0.9, application/problem+json;q=1.0
~~~

The **q** parameter indicates preference weight from 0 to 1. It does not mean the server must return ProblemDetail for successful requests. When choosing a representation, Spring evaluates mappings, media types, quality factors, and available converters/codecs.

- **Accept: */*** accepts whatever format the server can produce.
- **Accept: application/json** requests standard JSON.
- **Accept: application/problem+json** accepts Problem Details; it does not make normal data endpoints switch to an error format.
- **Accept: application/x-ndjson** is for line-delimited JSON records.
- **Accept: text/event-stream** is for SSE.
- **q=0** marks a media range as unacceptable; specificity and wildcards also affect the outcome.

If a client calls an endpoint with `produces=application/json` while sending only `Accept: text/event-stream`, it cannot force Spring to turn the response into SSE. The endpoint must provide a matching implementation.

### 2.2. consumes/produces on Annotations

~~~java
@PostMapping(
        path = "/api/items",
        consumes = MediaType.APPLICATION_JSON_VALUE,
        produces = MediaType.APPLICATION_JSON_VALUE)
~~~

- **consumes** constrains the request's `Content-Type`.
- **produces** constrains `Accept` and response writing capabilities.
- Avoid listing a broad set of media types on an endpoint unless the return type and encoder can genuinely produce each format.

In **Spring MVC**, bodies are handled via **HttpMessageConverter**. In **Spring WebFlux**, the equivalents are **HttpMessageReader/HttpMessageWriter** and encoders/decoders. Both implement content negotiation, but manage data streams differently.

## 3. Handler and Codec Selection Flow

~~~mermaid
flowchart TD
    A[HTTP request] --> B[DispatcherHandler or DispatcherServlet]
    B --> C[HandlerMapping checks path method consumes produces]
    C --> D{Matching handler?}
    D -->|Yes| E[Decode @RequestBody via reader/converter]
    E --> F[Controller, service]
    F --> G{Success or error?}
    G -->|Success| H[Encoder / writer for JSON, NDJSON, SSE]
    G -->|Error| I[ExceptionHandler / ProblemDetail]
    D -->|Condition mismatch| J[404, 405, 406, 415...]
    H --> K[Status + Content-Type + body]
    I --> K
    J --> K
~~~

Representative scenarios:

| Scenario | Typical HTTP Status | Cause |
|---|---:|---|
| POST expects JSON but receives `text/plain` | **415** | Fails `consumes` or reader check |
| GET returns JSON only, client sends `Accept: text/plain` | **406** | No compatible response representation |
| Malformed JSON body syntax | **400** | Decoder cannot parse |
| URL has no matching handler | **404** | Route/resource not found |
| URL has GET mapping, client sends POST | **405** | HTTP method mismatch |
| Business object does not exist | **404** if defined by business handler | Exception/error mapping |
| Stream already started, then errors | May keep committed status | Headers/body already flushed |

**Note:** 406/415 are **content negotiation** errors, not "the JSON serializer is broken." Besides `Content-Type` and `Accept`, also check paths, methods, security, interceptors/filters, and proxies.

## 4. application/json: Standard JSON Documents

Per **RFC 8259**, JSON exchanged across open systems must use UTF-8. Standard media type:

~~~http
Content-Type: application/json
~~~

Example object:

~~~json
{"id":1,"name":"Book"}
~~~

Example array:

~~~json
[
  {"id":1,"name":"Book"},
  {"id":2,"name":"Pen"}
]
~~~

Both are **a single valid JSON document**. JSON also permits top-level scalars, though APIs generally use objects/arrays for clear schemas.

### 4.1. Do Not Confuse Flux with Per-Object Streaming

In WebFlux, this illustrative snippet:

~~~java
@GetMapping(path = "/api/items",
            produces = MediaType.APPLICATION_JSON_VALUE)
public Flux<Item> all() {
    return repository.findAll();
}
~~~

does not mean the client immediately receives each item as it is emitted. Under the default behavior of **Jackson2Encoder in Spring Framework 6.2**, a multi-value publisher with **application/json** is typically **collected into a collection** and serialized as one JSON array.

This snippet cannot run standalone because `repository` and `Item` are undefined. For large or unbounded datasets, buffering everything increases memory and latency. For bounded collections, a JSON array remains a clean contract. When true streaming is needed, pick a streaming media type and matching decoder.

### 4.2. Charset and JSON

Networked JSON uses **UTF-8**. A `charset` parameter is not defined in RFC 8259's `application/json` registration; adding `charset=UTF-8` is normally unnecessary. Never emit a UTF-8 BOM.

Distinguish **JSON escaping** from character corruption: a body can represent `é` directly or as `\u00e9` and still parse to the exact same Unicode String. Never compare raw bytes naively and assume two valid representations differ semantically.

## 5. application/problem+json: RFC 9457 Problem Details

**Problem Details for HTTP APIs** (**RFC 9457**) is the standard format for HTTP errors, obsoleting RFC 7807. For JSON, the media type is:

~~~http
Content-Type: application/problem+json
~~~

Example:

~~~json
{
  "type": "https://api.example.org/problems/not-found",
  "title": "Item not found",
  "status": 404,
  "detail": "Item 99 does not exist",
  "instance": "/api/items/99",
  "code": "ITEM_NOT_FOUND"
}
~~~

| Property | Meaning |
|---|---|
| **type** | URI identifying the problem type. Defaults to `about:blank` when omitted |
| **title** | Short human-readable summary of the problem type |
| **status** | Matching HTTP status code; does not replace the HTTP status line |
| **detail** | Specific explanation for this occurrence, safe to expose publicly |
| **instance** | URI/identifier for this specific occurrence |
| **code** | Custom extension property outside the five standard members |

Responses do not have to include all five standard members. **ProblemDetail** standardizes error contracts so clients handle errors via HTTP status + machine-readable fields instead of parsing arbitrary body strings.

### 5.1. Creating ProblemDetail in Spring Framework 6.2

~~~java
import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;

ProblemDetail problem = ProblemDetail.forStatusAndDetail(
        HttpStatus.NOT_FOUND, "Item 99 does not exist");
problem.setTitle("Item not found");
problem.setProperty("code", "ITEM_NOT_FOUND");
~~~

This is an illustrative snippet inside a handler method with Spring dependencies, not a standalone Java program.

When an **@ExceptionHandler** or controller returns **ProblemDetail**:

- The HTTP status is derived from `ProblemDetail`'s **status**.
- Spring's JSON codecs/converters prefer **application/problem+json** when serializing `ProblemDetail`.
- Extension properties in the underlying `Map` serialize as top-level JSON properties via Spring's Jackson mixin.
- In **Spring Framework 6.2**, **instance** can be populated automatically with the request path when unset.

**Important:** merely changing `Content-Type` to `application/problem+json` on an arbitrary error `Map` does not make it an RFC-compliant `ProblemDetail`.

### 5.2. Configuration for Spring Boot 3.5

For Spring WebFlux:

~~~yaml
spring:
  webflux:
    problemdetails:
      enabled: true
~~~

`spring.webflux.problemdetails.enabled` enables auto-configuration so many built-in WebFlux exceptions render as Problem Details. For Spring MVC/Servlet, the equivalent property on a **different stack** is:

~~~yaml
spring:
  mvc:
    problemdetails:
      enabled: true
~~~

If you write your own **@RestControllerAdvice** returning `ProblemDetail` for business errors, those handlers still work without solely relying on the auto-configuration property. Manage **@Order** when multiple advices exist, and verify no two handlers compete.

### 5.3. Accept for Both Success and Error Responses

A clean way to call a standard JSON endpoint:

~~~http
Accept: application/json, application/problem+json
~~~

The client accepts **application/json** for success and **application/problem+json** for errors. Sending only `Accept: application/problem+json` to an endpoint with `produces=application/json` can trigger **406** right at handler mapping. Never send an error-only `Accept` header expecting normal success responses to still return JSON.

Conversely, a custom exception handler can return `ProblemDetail` using the preferred error media type once execution enters the handler, per Spring's content negotiation rules. Check actual HTTP status and `Content-Type` rather than guessing from exception names.

### 5.4. Security and Contract Stability

Never include stack traces, SQL queries, internal file paths, credentials, raw sensitive bodies, or access tokens in **detail**. For 5xx errors, return a safe message and a request/correlation ID for log lookup.

An API can standardize **code=ITEM_NOT_FOUND** or **code=INVALID_ITEM**; clients branch on status + `code`, rather than parsing Vietnamese or English prose inside **detail**.

## 6. Streaming Formats: Why Are Different Media Types Needed?

An HTTP response can remain open so the server pushes items incrementally instead of waiting for all data. In WebFlux, **Flux<T>** is a convenient abstraction for multiple items, while **the media type dictates the wire serialization format**.

| Spring Return Type | Response Media Type | Default/Common Wire Format |
|---|---|---|
| **Mono<Item>** | `application/json` | Single JSON object |
| **Flux<Item>** | `application/json` | Single JSON array; codec typically buffers the collection |
| **Flux<Item>** | `application/x-ndjson` | One JSON document per line, flushed per record |
| **Flux<ServerSentEvent<Item>>** | `text/event-stream` | SSE frames containing data/event/id |
| **Flux<String>** | `text/plain` or text stream | Text chunks; not a JSON array by default |

Do not reuse the same client parser across every row in this table.

## 7. NDJSON: application/x-ndjson

**NDJSON – Newline Delimited JSON** is a sequence of JSON documents, each on its own line.

~~~json
{"id":1,"name":"Book"}
{"id":2,"name":"Pen"}
{"id":3,"name":"Notebook"}
~~~

**Each individual line** is valid JSON, yet **the whole payload is not a single JSON document**. Clients must never call `JSON.parse` on the entire response expecting an array.

Media type:

~~~http
Content-Type: application/x-ndjson
~~~

Per Spring Framework 6.2 documentation, the Jackson encoder can serialize and flush **each `Flux` element** line-delimited when using a streaming media type like `application/x-ndjson`.

### 7.1. When Does NDJSON Fit?

- Exporting potentially huge record lists.
- Pushing logs, event records, or incremental processing results.
- Clients processing each JSON object as soon as it arrives.
- Systems wanting per-record JSON schemas without needing SSE event metadata.

Aspects to control:

- A single oversized record still needs memory for encoding/decoding.
- One TCP chunk does not equal one line; a line can span multiple chunks.
- Never call unbounded `collectList()` when reading streams on the client.
- Proxies/nginx/CDNs may buffer responses and negate real-time delivery.
- NDJSON defines no built-in reconnect/replay protocol; design your own if needed.

### 7.2. Do Not Confuse NDJSON with JSON-seq

**application/json-seq** per **RFC 7464** delimits JSON texts with the **RS (0x1E)** byte, unlike NDJSON's newline boundaries.

Some older systems use **application/stream+json**. When building APIs on Spring 6.2, pick and document one explicit media type; never swap headers without updating parsers, encoders, and tests.

## 8. SSE: text/event-stream

**Server-Sent Events** allow a server to push a stream of events over one HTTP response, commonly consumed in browsers via **EventSource**.

~~~http
Content-Type: text/event-stream
~~~

Example of **two SSE frames**:

~~~text
id:1
event:item
data:{"id":1,"name":"Book"}

id:2
event:item
data:{"id":2,"name":"Pen"}

~~~

- **id:** event identifier, helpful for reconnects if the backend supports replay.
- **event:** event type name, e.g., `item` or `update`.
- **data:** payload; may be serialized JSON string/object, though **the overall response remains SSE**.
- **retry:** suggested reconnection delay for `EventSource` clients.
- A blank line terminates an event; **comment-only lines** starting with `:` can serve as heartbeats.

### 8.1. How SSE Differs from NDJSON

| Factor | NDJSON | SSE |
|---|---|---|
| Media type | `application/x-ndjson` | `text/event-stream` |
| Item boundary | Newline | Blank line between events |
| Data format | Each line is a JSON document | SSE frame; `data` may contain JSON |
| Event metadata | None by default | `id`/`event`/`retry`/comment |
| Browser client | Fetch streaming + line parser | **EventSource** |
| Reconnect | Client implements manually | `EventSource` provides basic reconnect |
| Typical direction | Server → client, occasionally request streaming | Server → client |
| Low latency | Flushed per record | Flushed per event |

**EventSource** does not offer bidirectional communication like WebSocket. For server-to-client status updates or notifications, SSE can be simpler than WebSocket.

### 8.2. Important Limitations

- SSE uses **UTF-8** and text framing; parsers must split by lines rather than raw TCP chunks.
- Events can arrive delayed due to proxy buffering or compression.
- Long-lived streams need **heartbeats**, timeouts, cancellation, and resource cleanup.
- When `EventSource` reconnects with **Last-Event-ID**, the server must implement replay if missed events must not be lost.
- Never treat SSE as a single JSON document; calling `JSON.parse(responseBody)` on the raw SSE response fails.

## 9. Handling Errors After a Stream Has Committed

Before a response starts writing bytes, the server can still return:

~~~http
HTTP/1.1 404 Not Found
Content-Type: application/problem+json
~~~

Once the first NDJSON record or SSE frame has flushed, **status and headers may already be committed**. If an upstream error occurs afterward, the application usually **cannot change HTTP 200 to 500** or replace the body with a `ProblemDetail` response.

Handling strategies:

1. **Check authorization and preconditions** before emitting the first record; early failures return `ProblemDetail`.
2. If an error occurs mid-stream, **log/record metrics and close the stream**, or emit a **stream-protocol error event** if defined in the contract.
3. For SSE, you can emit `event:error` with JSON data understood by clients; this **does not** alter the HTTP status.
4. For NDJSON, error records need a distinct schema so they are not parsed as normal data; never inject a random `ProblemDetail` JSON object or switch `Content-Type` mid-stream.
5. Clients must handle interrupted streams, retries, duplicate events, and checkpoints.

**Never promise** that every Reactor `Flux` error becomes an HTTP 5xx after bytes have already been sent.

## 10. Runnable Spring Boot 3.5 / Java 17 Demo

A pure **WebFlux with Reactor Netty** demo exposing these routes:

- `GET /api/items/1` → 200 `application/json`.
- `GET /api/items/99` → 404 `application/problem+json`.
- `GET /api/items` → JSON array.
- `POST /api/items` → receives/returns JSON.
- `GET /api/stream/ndjson` → NDJSON with three records.
- `GET /api/stream/sse` → SSE with three events.

### 10.1. Directory Structure

~~~text
media-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/media/
    │   │   ├── MediaApplication.java
    │   │   ├── ItemController.java
    │   │   ├── ItemNotFoundException.java
    │   │   └── ApiProblemHandler.java
    │   └── resources/application.yml
    └── test/java/com/example/media/
        └── MediaNegotiationTest.java
~~~

### 10.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>media-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
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
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-test</artifactId>
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

Do not add **spring-boot-starter-web** to this project; when both MVC and WebFlux are present, Spring Boot typically prefers Servlet/MVC.

### 10.3. MediaApplication.java

~~~java
package com.example.media;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MediaApplication {
    public static void main(String[] args) {
        SpringApplication.run(MediaApplication.class, args);
    }
}
~~~

### 10.4. ItemNotFoundException.java

~~~java
package com.example.media;

public class ItemNotFoundException extends RuntimeException {
    private final long id;

    public ItemNotFoundException(long id) {
        super("Item " + id + " does not exist");
        this.id = id;
    }

    public long getId() {
        return id;
    }
}
~~~

### 10.5. ItemController.java

~~~java
package com.example.media;

import java.time.Duration;

import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api")
public class ItemController {

    @GetMapping(
            path = "/items/{id}",
            produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<Item> find(@PathVariable long id) {
        if (id == 1L) {
            return Mono.just(new Item(1, "Book"));
        }
        return Mono.error(new ItemNotFoundException(id));
    }

    @GetMapping(
            path = "/items",
            produces = MediaType.APPLICATION_JSON_VALUE)
    public Flux<Item> list() {
        return Flux.just(
                new Item(1, "Book"),
                new Item(2, "Pen"));
    }

    @PostMapping(
            path = "/items",
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<Item> create(@RequestBody Mono<NewItem> request) {
        return request.flatMap(input -> {
            if (input.name() == null || input.name().isBlank()) {
                return Mono.error(
                        new IllegalArgumentException("name is required"));
            }
            return Mono.just(new Item(3, input.name().trim()));
        });
    }

    @GetMapping(
            path = "/stream/ndjson",
            produces = "application/x-ndjson")
    public Flux<Item> ndjson() {
        return Flux.just(
                new Item(1, "Book"),
                new Item(2, "Pen"),
                new Item(3, "Notebook"))
                .delayElements(Duration.ofMillis(150));
    }

    @GetMapping(
            path = "/stream/sse",
            produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public Flux<ServerSentEvent<Item>> sse() {
        return Flux.just(
                new Item(1, "Book"),
                new Item(2, "Pen"),
                new Item(3, "Notebook"))
                .delayElements(Duration.ofMillis(200))
                .index()
                .map(tuple -> ServerSentEvent.<Item>builder()
                        .id(Long.toString(tuple.getT1() + 1))
                        .event("item")
                        .data(tuple.getT2())
                        .build());
    }

    public record Item(long id, String name) {}
    public record NewItem(String name) {}
}
~~~

**Code explanation:**

- **find** returns a `Mono` of one item or `Mono.error` so the exception handler generates a `ProblemDetail`.
- **list** uses `Flux`, yet `produces=application/json`, so Jackson collects items into a JSON array.
- **create** requires a JSON request, validates `name`, and returns a JSON object; the demo does not persist to a database.
- **ndjson** creates three JSON records emitted line-by-line with a 150ms delay between elements.
- **sse** creates three `ServerSentEvent`s with `id`, event name `item`, and `data` as a JSON DTO. Delays demonstrate per-event flushing.

### 10.6. ApiProblemHandler.java

~~~java
package com.example.media;

import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
@Order(Ordered.HIGHEST_PRECEDENCE)
public class ApiProblemHandler {

    @ExceptionHandler(ItemNotFoundException.class)
    public ProblemDetail notFound(ItemNotFoundException ex) {
        ProblemDetail detail = ProblemDetail.forStatusAndDetail(
                HttpStatus.NOT_FOUND, ex.getMessage());
        detail.setTitle("Item not found");
        detail.setProperty("code", "ITEM_NOT_FOUND");
        return detail;
    }

    @ExceptionHandler(IllegalArgumentException.class)
    public ProblemDetail invalid(IllegalArgumentException ex) {
        ProblemDetail detail = ProblemDetail.forStatusAndDetail(
                HttpStatus.BAD_REQUEST, ex.getMessage());
        detail.setTitle("Invalid item");
        detail.setProperty("code", "INVALID_ITEM");
        return detail;
    }
}
~~~

**@Order** gives the business-specific handler explicit priority if the application also has Boot-configured advices. Never write `@ExceptionHandler(Exception.class)` catching everything and returning 500, because it can mask framework 400/404/405/406/415 responses.

### 10.7. application.yml

~~~yaml
server:
  port: 8080

spring:
  webflux:
    problemdetails:
      enabled: true
~~~

In Boot 3.5, `spring.webflux.problemdetails.enabled` standardizes several built-in WebFlux error responses. The two custom handlers above remain responsible for domain-specific errors.

### 10.8. Starting Up

In the directory with `pom.xml`, with JDK 17+ and Maven:

~~~bash
mvn spring-boot:run
~~~

Or:

~~~bash
mvn clean package
java -jar target/media-demo-1.0.0.jar
~~~

## 11. HTTP Testing with curl

### 11.1. Successful JSON

~~~bash
curl -i \
  -H "Accept: application/json, application/problem+json" \
  "http://localhost:8080/api/items/1"
~~~

Expect HTTP **200**, `Content-Type` compatible with **application/json**, and body:

~~~json
{"id":1,"name":"Book"}
~~~

### 11.2. ProblemDetail

~~~bash
curl -i \
  -H "Accept: application/json, application/problem+json" \
  "http://localhost:8080/api/items/99"
~~~

Expect HTTP **404**, `Content-Type` compatible with **application/problem+json**. Body fields:

~~~json
{
  "type": "about:blank",
  "title": "Item not found",
  "status": 404,
  "detail": "Item 99 does not exist",
  "instance": "/api/items/99",
  "code": "ITEM_NOT_FOUND"
}
~~~

Spring Framework 6.2 may set `instance` automatically. JSON key order does not matter.

### 11.3. JSON Array

~~~bash
curl -i \
  -H "Accept: application/json" \
  "http://localhost:8080/api/items"
~~~

Expect a JSON array:

~~~json
[
  {"id":1,"name":"Book"},
  {"id":2,"name":"Pen"}
]
~~~

The JSON serializer may print on a single line if pretty-printing is disabled.

### 11.4. Successful JSON POST

~~~bash
curl -i \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, application/problem+json" \
  --data-binary '{"name":"Hanoi"}' \
  "http://localhost:8080/api/items"
~~~

Expect HTTP **200** (the demo does not persist to a database and does not return 201):

~~~json
{"id":3,"name":"Hanoi"}
~~~

### 11.5. Wrong Content-Type → 415

~~~bash
curl -i \
  -H "Content-Type: text/plain" \
  --data-binary "Hello" \
  "http://localhost:8080/api/items"
~~~

Expect HTTP **415 Unsupported Media Type** because the endpoint consumes `application/json`.

### 11.6. Wrong Accept → 406

~~~bash
curl -i \
  -H "Accept: text/plain" \
  "http://localhost:8080/api/items/1"
~~~

Expect HTTP **406 Not Acceptable**, because the endpoint only produces `application/json`.

### 11.7. Invalid Body → 400

~~~bash
curl -i \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, application/problem+json" \
  --data-binary '{"name":"  "}' \
  "http://localhost:8080/api/items"
~~~

Expect HTTP **400** with ProblemDetail **code=INVALID_ITEM**.

### 11.8. NDJSON Record-by-Record

~~~bash
curl -i -N \
  -H "Accept: application/x-ndjson" \
  "http://localhost:8080/api/stream/ndjson"
~~~

**-N** disables curl buffering. Expect three JSON lines:

~~~json
{"id":1,"name":"Book"}
{"id":2,"name":"Pen"}
{"id":3,"name":"Notebook"}
~~~

**Do not** parse the whole block as a JSON array.

### 11.9. SSE Event-by-Event

~~~bash
curl -i -N \
  -H "Accept: text/event-stream" \
  "http://localhost:8080/api/stream/sse"
~~~

Expected shape:

~~~text
id:1
event:item
data:{"id":1,"name":"Book"}

id:2
event:item
data:{"id":2,"name":"Pen"}

id:3
event:item
data:{"id":3,"name":"Notebook"}

~~~

These are SSE frames; **event.data** is what contains JSON. Multiline commands use Bash; on Windows, use **curl.exe** on one line and mind escaping.

## 12. Integration Testing with WebTestClient

Testing over real HTTP with **Reactor Netty** verifies statuses and `Content-Type`; the demo streams are finite so tests can read the full body. This is not the recommended way to consume infinite streams in production.

**src/test/java/com/example/media/MediaNegotiationTest.java**

~~~java
package com.example.media;

import java.nio.charset.StandardCharsets;
import java.time.Duration;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class MediaNegotiationTest {

    @LocalServerPort
    int port;

    WebTestClient client;

    @BeforeEach
    void setUp() {
        client = WebTestClient.bindToServer()
                .baseUrl("http://localhost:" + port)
                .responseTimeout(Duration.ofSeconds(8))
                .build();
    }

    @Test
    void successUsesApplicationJson() {
        client.get().uri("/api/items/1")
                .accept(MediaType.APPLICATION_JSON)
                .exchange()
                .expectStatus().isOk()
                .expectHeader().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON)
                .expectBody()
                .jsonPath("$.name").isEqualTo("Book");
    }

    @Test
    void missingItemUsesProblemJson() {
        client.get().uri("/api/items/99")
                .accept(MediaType.APPLICATION_JSON,
                        MediaType.parseMediaType("application/problem+json"))
                .exchange()
                .expectStatus().isNotFound()
                .expectHeader().contentTypeCompatibleWith(
                        MediaType.parseMediaType("application/problem+json"))
                .expectBody()
                .jsonPath("$.status").isEqualTo(404)
                .jsonPath("$.code").isEqualTo("ITEM_NOT_FOUND");
    }

    @Test
    void unsupportedAcceptGives406() {
        client.get().uri("/api/items/1")
                .accept(MediaType.TEXT_PLAIN)
                .exchange()
                .expectStatus().isEqualTo(406);
    }

    @Test
    void unsupportedRequestContentTypeGives415() {
        client.post().uri("/api/items")
                .contentType(MediaType.TEXT_PLAIN)
                .bodyValue("Hello")
                .exchange()
                .expectStatus().isEqualTo(415);
    }

    @Test
    void ndjsonHasThreeRecords() {
        client.get().uri("/api/stream/ndjson")
                .accept(MediaType.parseMediaType("application/x-ndjson"))
                .exchange()
                .expectStatus().isOk()
                .expectHeader().contentTypeCompatibleWith(
                        MediaType.parseMediaType("application/x-ndjson"))
                .expectBody()
                .consumeWith(result -> {
                    byte[] bytes = result.getResponseBody();
                    assertThat(bytes).isNotNull();
                    String body = new String(bytes, StandardCharsets.UTF_8);
                    assertThat(body.lines()
                            .filter(line -> !line.isBlank()).count())
                            .isEqualTo(3L);
                });
    }

    @Test
    void sseContainsEventFrames() {
        client.get().uri("/api/stream/sse")
                .accept(MediaType.TEXT_EVENT_STREAM)
                .exchange()
                .expectStatus().isOk()
                .expectHeader().contentTypeCompatibleWith(
                        MediaType.TEXT_EVENT_STREAM)
                .expectBody()
                .consumeWith(result -> {
                    byte[] bytes = result.getResponseBody();
                    assertThat(bytes).isNotNull();
                    String body = new String(bytes, StandardCharsets.UTF_8);
                    assertThat(body).contains("event:");
                    assertThat(body).contains("data:");
                    assertThat(body).contains("Book");
                });
    }
}
~~~

Run:

~~~bash
mvn test
~~~

When tests succeed, Maven exits with code 0. The tests above verify **media types and bodies after full reception**; they do not prove per-record flush timing or proxy buffering behavior. To test latency/heartbeats, use a subscriber observing per-event timing through production-like infrastructure.

## 13. How Clients Parse Each Format

**application/json:** reads one JSON document and parses it into a DTO/array. Check the HTTP status before parsing under the success schema.

**application/problem+json:** parses `ProblemDetail`, using `status` and extension `code` to drive UI messages or retries. Never rely entirely on the **detail** string.

**application/x-ndjson:** reads a UTF-8 byte stream by **line boundaries**, parsing each complete line. One network chunk may contain half a line, multiple lines, or a split UTF-8 character; never equate network chunks with records.

`WebClient` example (illustrative snippet inside an application class):

~~~java
Flux<Item> records = webClient.get()
        .uri("/api/stream/ndjson")
        .accept(MediaType.parseMediaType("application/x-ndjson"))
        .retrieve()
        .bodyToFlux(Item.class);
~~~

Subscribe to or process the `Publisher` in a pipeline. For unbounded streams, never call unbounded `collectList()`.

**text/event-stream:** use an SSE parser or the browser's **EventSource**, then parse each `event.data` if its payload is JSON.

~~~javascript
const source = new EventSource("/api/stream/sse");

source.addEventListener("item", event => {
  const item = JSON.parse(event.data);
  console.log(item.id, item.name);
});

source.onerror = () => {
  console.log("SSE connection interrupted");
};
~~~

This JavaScript runs in browsers; if using bearer token `Authorization`, native `EventSource` does not allow custom HTTP headers like `fetch`. Design authentication, CORS, and cookies/sessions accordingly.

## 14. Production Operational Considerations

### 14.1. Streaming and Proxies

- Reverse proxies, ingresses, or CDNs may **buffer responses**, delaying NDJSON/SSE arrival even when Spring flushes per item.
- **Compression** can also increase buffering; measure on real servers/proxies.
- For long-lived streams, enforce **heartbeats**, timeouts, cancellation, and connection limits.
- Never force `Content-Length` when stream length is unknown. HTTP/1.1 uses chunked transfer; HTTP/2 uses its own framing.
- When caching multiple representations at one URL, evaluate `Vary: Accept` and ensure personalized responses are never cached improperly.
- Never treat `Content-Type` as an authorization mechanism: still enforce authentication/authorization.

### 14.2. Buffer Limits and Backpressure

In Spring WebFlux, codecs enforce aggregation caps such as **maxInMemorySize**. In Boot 3.5 you can configure:

~~~yaml
spring:
  http:
    codecs:
      max-in-memory-size: 256KB
~~~

This limit is not a total byte cap for an entire NDJSON stream. A stream of many small records can exceed that byte total; a single huge record can still exceed the cap. Furthermore, if code calls unbounded `collectList()`, caches, or joins, returning `Flux` will not prevent memory accumulation.

### 14.3. Client Reconnection

- SSE `EventSource` reconnects automatically; to avoid losing events, backends must honor **Last-Event-ID** and provide replay/offsets.
- NDJSON has no default reconnect protocol; design cursors/checkpoints, idempotency, and duplicate handling.
- Never auto-retry non-idempotent POSTs merely because a stream connection dropped.

### 14.4. Mid-Stream Errors

Once a response commits, you cannot send a new **ProblemDetail JSON response** replacing the active status/body. Define an in-band error event in the stream protocol if needed, or close the stream and rely on metrics/logs for diagnosis.

## 15. Common Errors Table

| Symptom | Cause | Resolution |
|---|---|---|
| POST returns 415 | Request `Content-Type` mismatches `consumes` | Send matching `Content-Type`/`application/json` |
| GET returns 406 | `Accept` mismatches `produces` | Request a media type supported by the endpoint |
| Error JSON returns 200 | Handler did not set HTTP status | Use `ProblemDetail`/`ResponseEntity` with the right status |
| Client parses error with success DTO | Failed to distinguish `problem+json` | Inspect status and `Content-Type` |
| 404 body lacks `ProblemDetail` | Auto-config disabled or overridden by another handler | Check WebFlux/MVC property and advices |
| `Flux` returns JSON array instead of streaming | `produces=application/json` | Use NDJSON or SSE for streaming |
| `JSON.parse` fails on NDJSON | Multiple root JSON documents | Parse line by line |
| `JSON.parse` fails on SSE | Receiving event frames | Use `EventSource`/SSE parser |
| SSE lags behind ingress | Proxy buffering/compression | Check flushing and proxy config |
| Mid-stream error keeps status 200 | Response already committed | Use in-band error events or close stream |
| Many NDJSON records cause OOM | Code collects `Flux` into `List` | Stream with backpressure and bound records |
| `application/json-seq` parses wrong | RS framing differs from newlines | Use an RFC 7464 parser |
| `EventSource` reconnects continuously | Timeout/auth/stream termination | Heartbeats, auth, reconnect policy |
| Cache returns wrong media type | Cache key ignores `Accept` | `Vary: Accept` and cache policy |

## 16. QA Checklist

- [ ] Every endpoint defines an explicit `consumes`/`produces` contract.
- [ ] Success `application/json` emits a valid JSON document.
- [ ] Business errors use accurate HTTP statuses and `application/problem+json`.
- [ ] `ProblemDetail` never leaks stack traces, SQL, tokens, or private info.
- [ ] Boot WebFlux sets `spring.webflux.problemdetails.enabled` if enabling auto-handlers.
- [ ] Tests cover 406/415, malformed JSON, and missing resources.
- [ ] NDJSON emits one JSON document per line, not a JSON array.
- [ ] SSE uses proper event framing and `Content-Type: text/event-stream`.
- [ ] Tested with `curl -N` and appropriate client parsers.
- [ ] Accounted for proxy buffering, compression, timeouts, and cancellation.
- [ ] Never collects unbounded `Flux` streams into memory.
- [ ] Defined error handling for post-commit stream failures.
- [ ] When serving multiple representations per URL, caches distinguish by `Accept`.
- [ ] Planned authentication/authorization, reconnection, and replay strategies.

## 17. Official References

1. Spring Framework 6.2 – Mapping Requests, consumes/produces: https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-requestmapping.html
2. Spring Framework 6.2 – Reactive Core, Jackson encoding and streaming: https://docs.spring.io/spring-framework/reference/6.2/web/webflux/reactive-spring.html
3. Spring Framework 6.2 – WebFlux Error Responses: https://docs.spring.io/spring-framework/reference/6.2/web/webflux/ann-rest-exceptions.html
4. Spring Framework 6.2 – MVC Error Responses: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-ann-rest-exceptions.html
5. Spring Boot 3.5 – Reactive Web Applications: https://docs.spring.io/spring-boot/3.5/reference/web/reactive.html
6. Spring Boot 3.5 – Common Application Properties: https://docs.spring.io/spring-boot/3.5/appendix/application-properties/
7. RFC 9457 – Problem Details for HTTP APIs: https://www.rfc-editor.org/rfc/rfc9457
8. RFC 8259 – JSON: https://www.rfc-editor.org/rfc/rfc8259
9. RFC 9110 – HTTP Semantics: https://www.rfc-editor.org/rfc/rfc9110
10. RFC 7464 – JSON Text Sequences: https://www.rfc-editor.org/rfc/rfc7464
11. WHATWG HTML – Server-Sent Events: https://html.spec.whatwg.org/multipage/server-sent-events.html

## 18. Conclusion

In Spring Boot, **Accept**, **Content-Type**, **consumes**, and **produces** determine accepted formats and handler/codec selection. **application/json** serves single JSON documents, **application/problem+json** serves RFC 9457 `ProblemDetail` payloads, while **application/x-ndjson** and **text/event-stream** serve two distinct streaming models with different framing and client parsers.

**`Flux<T>` does not guarantee response streaming** under `application/json`, because Jackson defaults to collecting items into one JSON array. When selecting streaming formats, account for flushing, proxies, memory, backpressure, reconnection, and errors after the HTTP response has committed.
