# Content negotiation with `Accept` and `Content-Type` in Spring WebFlux

## 1. Goal: two headers that answer two different questions

In an HTTP API, the client and server need to agree on the **data format**. A request can send JSON and also want JSON back, or send JSON but want a plain-text response. The two most important headers are:

- **`Content-Type`** describes the format of the representation in the **current request body**: is the client sending JSON, XML, NDJSON, form data, or some other format?
- **`Accept`** describes the representation formats the client **wants to receive in the response**: does the client accept JSON, XML, text, or a set of formats with priorities?

Do not swap the roles of the two headers. `Content-Type` answers "which format is the body I am sending encoded in?", while `Accept` answers "which format can the response sent back to me use?".

In Spring WebFlux, the two headers take part in two different stages:

1. When reading the request body, `HttpMessageReader` and the decoder must find a codec that can read the media type of `Content-Type` into the Java type the handler requires.
2. When writing the response body, `HttpMessageWriter` and the encoder must find a codec that can write the Java type into a media type that matches `Accept` and mapping conditions such as `produces`.

This lesson helps you understand the media range syntax and quality values (`q`), how Spring handles `consumes`/`produces`, why HTTP 406 and 415 occur, how to declare functional routes, and how to test content negotiation.

~~~text
                 REQUEST
Client ----------------------------------------> Spring WebFlux
       Content-Type: application/json
       Accept: application/json, text/plain;q=0.5
       Body: JSON bytes

                 READ
       Content-Type + target Java type
                    |
                    v
             HttpMessageReader
                    |
                    v
             Decoder -> Java object
                    |
                    v
             Controller / HandlerFunction

                 RESPONSE
       Controller returns Mono<T> / Flux<T>
                    |
                    v
             HttpMessageWriter
                    ^
                    |
       Accept + produces + available codecs
                    |
                    v
             Encoder -> response bytes
                    |
                    v
Client <---------------------------------------- Spring WebFlux
       Content-Type: application/json
       Body: JSON bytes
~~~

## 2. What is a media type?

A media type describes the format and kind of content of a representation. Basic structure:

~~~text
type / subtype ; parameter=value
~~~

Examples:

| Media type | Meaning |
| --- | --- |
| `application/json` | JSON |
| `application/xml` | XML |
| `text/plain` | Plain text |
| `text/html` | HTML |
| `application/x-www-form-urlencoded` | Form URL-encoded |
| `multipart/form-data` | Multi-part form, often with files |
| `application/x-ndjson` | JSON objects separated by lines |
| `text/event-stream` | Server-Sent Events |
| `application/problem+json` | JSON in the Problem Details format |
| `application/octet-stream` | Generic byte data |

A media type can carry parameters:

~~~http
Content-Type: application/json; charset=UTF-8
Accept: text/html;level=1
~~~

A parameter can affect how the representation is interpreted or how the framework matches it. With modern JSON, UTF-8 is the common default choice; there is no need to add a charset to every request yourself if the client and server have already agreed.

**A media type is not a content encoding.** Related concepts:

| Header | Role |
| --- | --- |
| `Content-Type` | The representation format of the current body |
| `Accept` | The representation format the client accepts in the response |
| `Content-Encoding` | How the representation being sent is encoded/compressed, for example `gzip` |
| `Accept-Encoding` | The content encoding types the client accepts |
| `Accept-Language` | The representation language the client prefers |
| `Vary` | Tells caches which request headers affect the choice of response |

For example, a response can have `Content-Type: application/json` and `Content-Encoding: gzip` at the same time: the logical content is JSON, while the bytes sent over the wire are gzip-compressed. `Accept-Encoding` does not replace `Accept`.

## 3. `Accept`: which representation does the client want?

### 3.1. Basic syntax

The client can send one or more media ranges:

~~~http
GET /api/products/1 HTTP/1.1
Host: localhost:8080
Accept: application/json
~~~

This means the client wants to receive JSON. You can list several types:

~~~http
Accept: application/json, text/plain, application/xml
~~~

There are two common wildcards:

- `application/*`: accepts every subtype in the `application` group.
- `*/*`: accepts every media type.

If `Accept` is not sent, the client states no specific format preference; the server can choose a suitable representation. `Accept: */*` also indicates acceptance of every type through the media range.

### 3.2. Quality value (`q`): priority

Each media range can have a quality value from `0` to `1`. If `q` is omitted, the default value is `1`. A higher value expresses a higher priority; `q=0` means the corresponding representation is not acceptable.

~~~http
Accept: application/json;q=0.9, text/plain;q=0.5, application/xml;q=0.2
~~~

This example prefers JSON, then text, then XML. A quality value can have at most three decimal places under the HTTP syntax:

~~~http
Accept: application/json;q=1.0, text/plain;q=0.75, application/xml;q=0
~~~

`q` is the client's priority weight; it is not a percentage probability and not a quality score of the data.

### 3.3. Wildcards and specificity

~~~http
Accept: application/*;q=0.8, application/json;q=1.0, */*;q=0.1
~~~

Media ranges have different levels of specificity. When determining the quality of a specific media type, the more specific range can take precedence over the general range. For example, `application/json` is described directly with `q=1.0`, so it takes priority over the general level of `application/*` or `*/*`.

Do not write your own media-type selection algorithm just by sorting all `q` values in descending order while ignoring specificity. Spring also considers mapping conditions, the Java type, and the writing capability of the available codecs.

### 3.4. `Accept` is a preference, not a command forcing the server to have a codec

If the client sends:

~~~http
Accept: application/xml
~~~

but the endpoint can only produce JSON, the server cannot turn an object into XML by itself without a supporting writer/encoder. Depending on the mapping and configuration, the result may be HTTP **406 Not Acceptable**.

If the endpoint only produces JSON and the client sends `Accept: application/json`, the request has a matching representation. If the client sends `Accept: application/*`, JSON can also match this wildcard.

### 3.5. `q=0` removes a format from the accepted set

~~~http
Accept: application/json;q=0, text/plain;q=1
~~~

The client explicitly says it does not want JSON and prefers text. If the server only has a JSON endpoint/representation, it should not return JSON as if the client had accepted it; a 406 may result. If the server has a suitable text representation, it can choose text.

## 4. `Content-Type`: which format is the request body being sent in?

### 4.1. Sending JSON requires declaring JSON

~~~http
POST /api/products HTTP/1.1
Content-Type: application/json
Accept: application/json

{"name":"Keyboard","price":120}
~~~

`Content-Type: application/json` tells the server the body bytes must be decoded as JSON. `Accept: application/json` tells the server the client wants a JSON response. The two headers can have the same value, but they serve two different directions.

A request can perfectly well use:

~~~http
Content-Type: application/json
Accept: text/plain
~~~

This means the client sends JSON but wants the server to return plain text. The server can only satisfy this if the endpoint can produce a suitable text representation.

### 4.2. A non-JSON body must be declared correctly

Form example:

~~~http
POST /login HTTP/1.1
Content-Type: application/x-www-form-urlencoded

username=linh&password=secret
~~~

Multipart example:

~~~http
POST /upload HTTP/1.1
Content-Type: multipart/form-data; boundary=----client-boundary
~~~

NDJSON example:

~~~http
POST /events HTTP/1.1
Content-Type: application/x-ndjson

{"id":1,"type":"created"}
{"id":2,"type":"updated"}
~~~

If you send JSON bytes but declare `Content-Type: text/plain`, the server will choose a reader according to text/plain. If the handler only accepts JSON, the request may be rejected with 415.

### 4.3. A request without a body usually does not need `Content-Type`

An ordinary GET request has no body, so it usually does not need `Content-Type`. This header does not tell the server which format to return. To choose the response, send `Accept`.

This is a common mistake:

~~~http
GET /api/products/1
Content-Type: application/json
~~~

The header above does not mean the client requests a JSON response. The correct header for that goal is:

~~~http
GET /api/products/1
Accept: application/json
~~~

## 5. Distinguishing `consumes` and `produces` in Spring WebFlux

In an annotated controller, Spring uses two mapping attributes to constrain media types.

### 5.1. `consumes` matches the request `Content-Type`

~~~java
@PostMapping(
    path = "/products",
    consumes = MediaType.APPLICATION_JSON_VALUE
)
public Mono<Product> create(@RequestBody Mono<CreateProduct> body) {
    return body.flatMap(service::create);
}
~~~

`consumes` describes the kind of request body the handler can accept. If the client sends `Content-Type: text/plain` but the mapping only has `consumes=application/json`, the mapping does not match and Spring usually returns **415 Unsupported Media Type**.

If a method has no body, `consumes` is usually unnecessary. If there are several input formats, you can declare multiple media types:

~~~java
@PostMapping(
    path = "/import",
    consumes = {
        MediaType.APPLICATION_JSON_VALUE,
        "application/x-ndjson"
    }
)
public Mono<Void> importData(@RequestBody Flux<ImportRow> rows) {
    return service.importRows(rows);
}
~~~

This is an illustrative snippet: besides the mapping, the application must also have a reader/decoder that supports each declared format.

### 5.2. `produces` matches the request `Accept` and the response format

~~~java
@GetMapping(
    path = "/products/{id}",
    produces = MediaType.APPLICATION_JSON_VALUE
)
public Mono<Product> get(@PathVariable String id) {
    return service.findById(id);
}
~~~

`produces` describes the representations the handler can return. Spring matches this condition against the request's `Accept` and uses the chosen media type when writing the response.

If the client sends `Accept: text/plain` while the mapping only produces JSON, the mapping does not match and this usually leads to **406 Not Acceptable**.

### 5.3. Multiple media types can be declared

~~~java
@GetMapping(
    path = "/report",
    produces = {
        MediaType.APPLICATION_JSON_VALUE,
        MediaType.APPLICATION_XML_VALUE
    }
)
public Mono<Report> report() {
    return reportService.load();
}
~~~

This example only works fully if the application has a codec/writer that can write `Report` as both JSON **and** XML. Declaring two strings in `produces` does not install an XML encoder by itself. If the XML writer is missing, a client requesting XML still does not receive a valid representation.

Spring can choose a suitable representation according to `Accept`, the mapping, and the writers. Check both the codec dependencies and the actual response.

### 5.4. Quick reference table

| Component | What does it check? | Data direction |
| --- | --- | --- |
| `consumes` | Request `Content-Type` | Client → Server |
| `produces` | Request `Accept` and the ability to produce a response | Server → Client |
| `@RequestBody` | Reads/decodes the request body | Client → Java |
| `@ResponseBody` / `@RestController` | Encodes the return value into the response body | Java → Client |
| `HttpMessageReader` | Can it read the media type into a Java type? | Decode |
| `HttpMessageWriter` | Can it write the Java type into the media type? | Encode |

## 6. HTTP 406, 415, and easily confused errors

### 6.1. 406 Not Acceptable

Occurs when the server cannot find a response representation that matches the media ranges the client accepts, while the endpoint/framework requires negotiation to be honored.

Example:

~~~http
GET /api/product
Accept: text/csv
~~~

If the endpoint only supports JSON, the server has no CSV representation to return and may return 406.

### 6.2. 415 Unsupported Media Type

Occurs when the server does not support the media type of the request body, or the handler mapping does not accept that `Content-Type`.

Example:

~~~http
POST /api/echo
Content-Type: application/xml
Accept: application/json

<message>hello</message>
~~~

If the endpoint only accepts JSON, the request is rejected with 415 even though the client is willing to receive a JSON response. A correct `Accept` cannot compensate for a wrong `Content-Type`.

### 6.3. 400 Bad Request differs from 415

~~~http
POST /api/echo
Content-Type: application/json
Accept: application/json

{"name":
~~~

Here the JSON media type is supported, but the body syntax is invalid. The error is a parse/input error, usually mapped to **400 Bad Request**, not 415.

### 6.4. Statuses that often need to be distinguished

| Status | Common causes | What to check |
| --- | --- | --- |
| 400 Bad Request | Broken JSON, invalid input data, decode/validation errors | Body, schema, validation |
| 404 Not Found | No route/mapping, or the resource does not exist | Path, method, route, ID |
| 406 Not Acceptable | No response representation matches Accept/produces | Accept, produces, writer |
| 413 Payload Too Large | The payload exceeds the server/codec limit | Body size, buffer limit |
| 415 Unsupported Media Type | The request Content-Type is not supported by the mapping/reader | Content-Type, consumes, decoder |
| 500 Internal Server Error | A server error that has not been mapped appropriately | Log, exception, handler |

**How to diagnose:** if the error occurs before the controller is called, check the mapping and argument resolvers. If the controller has run but the response cannot be written, check the writer, media type, return type, and encoding errors.

## 7. How does Spring WebFlux choose readers and writers?

### 7.1. Reading the request: `HttpMessageReader`

Conceptual flow:

~~~text
HTTP request body bytes
       |
       v
Content-Type + target Java type
       |
       v
ServerCodecConfigurer
       |
       v
HttpMessageReader.canRead(...)
       |
       v
Decoder
       |
       v
Mono<T> / Flux<T> / object
~~~

`HttpMessageReader` checks whether it can read the Java type and media type. For example, the Jackson JSON reader can decode `application/json` into a DTO. A form or multipart reader handles the corresponding format.

In an annotated controller:

~~~java
@PostMapping(
    path = "/orders",
    consumes = MediaType.APPLICATION_JSON_VALUE
)
public Mono<OrderReceipt> create(
    @RequestBody Mono<CreateOrder> request
) {
    return request.flatMap(orderService::create);
}
~~~

With `Mono<CreateOrder>`, the controller receives a Publisher representing the body; the reader actually consumes the body when the subscription reaches that Publisher. With a non-reactive `@RequestBody CreateOrder` parameter, Spring needs to resolve the object before calling the method.

In WebFlux.fn:

~~~java
public Mono<ServerResponse> create(ServerRequest request) {
    return request.bodyToMono(CreateOrder.class)
        .flatMap(orderService::create)
        .flatMap(saved -> ServerResponse
            .created(URI.create("/orders/" + saved.id()))
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(saved));
}
~~~

`bodyToMono` uses a codec to read the body. Compose the Publisher into the returned chain; do not `subscribe()` or `block()` yourself.

### 7.2. Writing the response: `HttpMessageWriter`

Conceptual flow:

~~~text
Controller returns Mono<T> / Flux<T>
                 |
                 v
Accept + produces + declared body type
                 |
                 v
ServerCodecConfigurer
                 |
                 v
HttpMessageWriter.canWrite(...)
                 |
                 v
Encoder -> DataBuffer
                 |
                 v
HTTP response body
~~~

`HttpMessageWriter` chooses an encoder compatible with the Java type and the chosen response media type. For example:

~~~java
@GetMapping(
    path = "/products",
    produces = MediaType.APPLICATION_JSON_VALUE
)
public Flux<Product> products() {
    return repository.findAll();
}
~~~

The framework registers the response writing and consumes `Flux<Product>` according to demand. For a JSON array, the codec may aggregate the elements before serializing; with a streaming media type such as NDJSON/SSE, the writer can write element by element. The media type and the writer determine the actual behavior.

### 7.3. `ServerCodecConfigurer`

WebFlux provides default codecs and allows customization. For example, limiting memory for codecs that need to aggregate:

~~~java
@Configuration
public class CodecConfiguration implements WebFluxConfigurer {

    @Override
    public void configureHttpMessageCodecs(
        ServerCodecConfigurer configurer
    ) {
        configurer.defaultCodecs()
            .maxInMemorySize(2 * 1024 * 1024);
    }
}
~~~

This is an illustrative configuration for a 2 MiB limit. The actual value must be based on the payload, the codec type, and the system requirements. Raising the limit does not replace controlling the request size or handling streaming.

When adding a custom media type, you need to register an appropriate codec/reader/writer. Merely adding the media type to `produces` or `consumes` does not guarantee that the application knows how to decode/encode it.

## 8. Content negotiation in WebFlux.fn

In a functional endpoint, request predicates can check `Accept` and `Content-Type`.

### 8.1. Predicate `accept`

~~~java
import static org.springframework.web.reactive.function.server.RequestPredicates.accept;

RouterFunction<ServerResponse> routes =
    RouterFunctions.route()
        .GET("/api/report",
            accept(MediaType.APPLICATION_JSON),
            handler::jsonReport)
        .build();
~~~

`accept(MediaType.APPLICATION_JSON)` checks whether the request accepts JSON. This is a route condition; the handler must still produce the JSON response:

~~~java
public Mono<ServerResponse> jsonReport(ServerRequest request) {
    return ServerResponse.ok()
        .contentType(MediaType.APPLICATION_JSON)
        .bodyValue(Map.of("status", "ready"));
}
~~~

### 8.2. Predicate `contentType`

~~~java
import static org.springframework.web.reactive.function.server.RequestPredicates.contentType;

RouterFunction<ServerResponse> routes =
    RouterFunctions.route()
        .POST("/api/orders",
            contentType(MediaType.APPLICATION_JSON),
            handler::create)
        .build();
~~~

`contentType(MediaType.APPLICATION_JSON)` checks the format of the request body. This predicate does not choose the response format; to get a JSON response, the handler must set `ServerResponse.contentType` or have an appropriate configuration.

### 8.3. A predicate is not exactly the same as `consumes`/`produces` mapping

In an annotated controller, Spring has a dedicated mapping mechanism that maps the `consumes` and `produces` conditions to the appropriate HTTP errors, usually 415 and 406.

In WebFlux.fn, `accept(...)` and `contentType(...)` are RequestPredicates. When a predicate returns false, the router considers the route not matching and tries the next route. If there is no suitable route/fallback, the result is usually 404. A predicate does not automatically mean "every case that doesn't match Accept returns 406" or "every wrong Content-Type returns 415".

If a functional API needs an explicit 406/415 status, declare a fallback route by method/path or check the headers in the handler and then return the corresponding status. For example:

~~~java
RouterFunction<ServerResponse> routes =
    RouterFunctions.route()
        .GET("/api/report",
            accept(MediaType.APPLICATION_JSON),
            handler::jsonReport)
        .GET("/api/report", handler::notAcceptable)
        .POST("/api/orders",
            contentType(MediaType.APPLICATION_JSON),
            handler::create)
        .POST("/api/orders", handler::unsupportedMediaType)
        .build();
~~~

The fallback methods `notAcceptable` and `unsupportedMediaType` are defined by the application:

~~~java
public Mono<ServerResponse> notAcceptable(ServerRequest request) {
    return ServerResponse.status(HttpStatus.NOT_ACCEPTABLE).build();
}

public Mono<ServerResponse> unsupportedMediaType(ServerRequest request) {
    return ServerResponse.status(HttpStatus.UNSUPPORTED_MEDIA_TYPE).build();
}
~~~

A specific route must come before a fallback route. Otherwise, a general fallback may catch the request before the route with the predicate is evaluated.

## 9. Choosing media types for JSON, NDJSON, SSE, and files

### 9.1. A JSON object or a JSON array

`application/json` suits a single object or a complete JSON document. With `Mono<T>`, the writer usually encodes a single object. With `Flux<T>`, the default Jackson writer usually aggregates into a JSON array to produce a complete document.

~~~java
@GetMapping(
    path = "/products",
    produces = MediaType.APPLICATION_JSON_VALUE
)
public Flux<Product> products() {
    return repository.findAll();
}
~~~

If the data is very large and the client needs to receive each element as it becomes available, consider a streaming format. Do not assume that merely changing the return type to `Flux` makes the response flush each item automatically.

### 9.2. NDJSON

`application/x-ndjson` (JSON Lines) represents each JSON object on its own line:

~~~text
{"id":1,"name":"A"}
{"id":2,"name":"B"}
{"id":3,"name":"C"}
~~~

Example:

~~~java
@GetMapping(
    path = "/events",
    produces = "application/x-ndjson"
)
public Flux<Event> events() {
    return eventService.stream();
}
~~~

The client must send `Accept: application/x-ndjson` if it wants to request this format. For an NDJSON request body, the client sends `Content-Type: application/x-ndjson` and the server needs a reader that supports it.

### 9.3. Server-Sent Events

`text/event-stream` is for server-to-client event streams:

~~~java
@GetMapping(
    path = "/notifications",
    produces = MediaType.TEXT_EVENT_STREAM_VALUE
)
public Flux<ServerSentEvent<Notification>> notifications() {
    return notificationService.stream()
        .map(value -> ServerSentEvent.builder(value)
            .event("notification")
            .build());
}
~~~

The client usually sends `Accept: text/event-stream`. SSE has its own format, event framing, and reconnect rules; it is not just JSON sent continuously. A long-lived connection requires managing cancellation, heartbeat, and resources.

### 9.4. File download

A file download usually needs a media type describing the file content and the `Content-Disposition` header:

~~~java
@GetMapping("/download")
public Mono<ResponseEntity<byte[]>> download() {
    byte[] content = "example".getBytes(StandardCharsets.UTF_8);

    return Mono.just(ResponseEntity.ok()
        .contentType(MediaType.TEXT_PLAIN)
        .header(
            HttpHeaders.CONTENT_DISPOSITION,
            "attachment; filename=\"example.txt\"")
        .body(content));
}
~~~

This example illustrates a small in-memory file. For large files, prefer a streaming resource or an appropriate byte Publisher, and avoid gathering the whole file into a `byte[]`.

## 10. Configuring negotiation and custom media types

### 10.1. Defaults and configuration

In WebFlux, the requested content type resolver takes part in determining the media type the client accepts, normally based on the `Accept` header. The application can customize content type resolution through `WebFluxConfigurer.configureContentTypeResolver` if it has a specific need.

Prefer the standard `Accept` header when building an HTTP API. If the application adds a query parameter such as `?format=json`, you need to specify clearly how it interacts with `Accept`, the default format, invalid-format errors, and the cache key. Do not add multiple overlapping negotiation mechanisms without a clear contract.

### 10.2. Vendor-specific media type

An API can use a custom media type, for example:

~~~http
Accept: application/vnd.acme.product-v2+json
Content-Type: application/vnd.acme.product-v2+json
~~~

This is a way to express a version/profile through the media type. You need to register the mapping and ensure the codec can read/write that subtype. Jackson can support multiple JSON media types depending on the configuration; test in practice instead of assuming that every `+json` subtype is automatically supported in every configuration.

Versioning through a media type needs clear API documentation, deprecation rules, and a client fallback strategy. Do not use a custom media type just to arbitrarily name a JSON object that has no difference in representation.

### 10.3. Problem Details

API errors can use `application/problem+json` per Problem Details:

~~~http
HTTP/1.1 415 Unsupported Media Type
Content-Type: application/problem+json

{
  "type": "about:blank",
  "title": "Unsupported Media Type",
  "status": 415,
  "detail": "This endpoint accepts application/json."
}
~~~

The error format is a response representation, so `Accept` and the writer still matter. Do not return stack traces, SQL, or sensitive information in the `detail` field.

### 10.4. Cache and `Vary: Accept`

If the same URI returns JSON when the client sends `Accept: application/json` and returns text when the client sends `Accept: text/plain`, the representation depends on the request header `Accept`. Intermediary caches need to know that:

~~~http
Vary: Accept
~~~

`Vary` tells caches to distinguish response variants by header. If the content also depends on `Accept-Language`, the cache policy needs to reflect that header as well. Do not add `Vary` mechanically to every endpoint; declare only the headers that actually affect the representation.

You also need to design `Cache-Control`, ETag, and authorization appropriately. Content negotiation does not by itself solve cache invalidation or data leakage between users.

## 11. A complete Spring Boot 3.5.7 + Java 17 example

The application below has three endpoints:

- `GET /api/product`: returns JSON only.
- `GET /api/plain`: returns text/plain only.
- `POST /api/echo`: accepts JSON and returns JSON.

The example clearly shows that `Accept` determines the response format, while `Content-Type` determines which request body format is accepted. The project uses Spring Boot **3.5.7** and Java 17.

### 11.1. Project structure

~~~text
webflux-content-negotiation/
├── pom.xml
└── src/main/java/example/negotiation/
    ├── ContentNegotiationApplication.java
    └── NegotiationController.java
└── src/test/java/example/negotiation/
    └── NegotiationIntegrationTest.java
~~~

### 11.2. `pom.xml`

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
    <artifactId>webflux-content-negotiation</artifactId>
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

### 11.3. `ContentNegotiationApplication.java`

~~~java
package example.negotiation;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ContentNegotiationApplication {

    public static void main(String[] args) {
        SpringApplication.run(
            ContentNegotiationApplication.class, args);
    }
}
~~~

### 11.4. `NegotiationController.java`

~~~java
package example.negotiation;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api")
public class NegotiationController {

    public record ProductView(String id, String name, int price) {}

    public record CreateProduct(String name, int price) {}

    public record Receipt(String id, String name, int price) {}

    @GetMapping(
        path = "/product",
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    public Mono<ProductView> product() {
        return Mono.just(
            new ProductView("P-1", "Keyboard", 120));
    }

    @GetMapping(
        path = "/plain",
        produces = MediaType.TEXT_PLAIN_VALUE
    )
    public Mono<String> plain() {
        return Mono.just("plain response");
    }

    @PostMapping(
        path = "/echo",
        consumes = MediaType.APPLICATION_JSON_VALUE,
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    public Mono<Receipt> echo(
        @RequestBody Mono<CreateProduct> body
    ) {
        return body.map(input -> new Receipt(
            "R-" + input.name(),
            input.name(),
            input.price()
        ));
    }
}
~~~

The endpoints deliberately advertise only the media types their writers support. `/echo` uses `consumes` to restrict requests to JSON and `produces` to restrict responses to JSON. `/product` demonstrates a JSON response; `/plain` demonstrates a text response.

### 11.5. Running the application

Install JDK 17+ and Maven, then run in the directory containing `pom.xml`:

~~~bash
mvn spring-boot:run
~~~

**Request 1 — request JSON:**

~~~bash
curl -i http://localhost:8080/api/product \
  -H "Accept: application/json"
~~~

Main expected response:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
~~~

Body:

~~~json
{"id":"P-1","name":"Keyboard","price":120}
~~~

**Request 2 — request text from a JSON-only endpoint:**

~~~bash
curl -i http://localhost:8080/api/product \
  -H "Accept: text/plain"
~~~

Expected result: **406 Not Acceptable**, because the mapping only declares `produces=application/json`.

**Request 3 — request text from the text endpoint:**

~~~bash
curl -i http://localhost:8080/api/plain \
  -H "Accept: text/plain"
~~~

Main expected response:

~~~http
HTTP/1.1 200 OK
Content-Type: text/plain
~~~

Body:

~~~text
plain response
~~~

**Request 4 — send JSON and receive JSON:**

~~~bash
curl -i -X POST http://localhost:8080/api/echo \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  -d '{"name":"Pen","price":15}'
~~~

Main expected response:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
~~~

Body:

~~~json
{"id":"R-Pen","name":"Pen","price":15}
~~~

**Request 5 — send the wrong Content-Type:**

~~~bash
curl -i -X POST http://localhost:8080/api/echo \
  -H "Content-Type: text/plain" \
  -H "Accept: application/json" \
  --data "name=Pen&price=15"
~~~

Expected result: **415 Unsupported Media Type**, because the endpoint only accepts JSON. The client accepting a JSON response does not change the conditions for reading the request body.

**Request 6 — send valid JSON but do not accept a JSON response:**

~~~bash
curl -i -X POST http://localhost:8080/api/echo \
  -H "Content-Type: application/json" \
  -H "Accept: text/plain" \
  -d '{"name":"Pen","price":15}'
~~~

Expected result: **406 Not Acceptable**, because the request body has the correct media type but the response mapping only produces JSON.

**Request 7 — use a wildcard:**

~~~bash
curl -i http://localhost:8080/api/product \
  -H "Accept: application/*"
~~~

JSON is compatible with `application/*`, so the request can receive a JSON response.

**Request 8 — quality value:**

~~~bash
curl -i http://localhost:8080/api/product \
  -H "Accept: application/json;q=0.9, text/plain;q=0.4"
~~~

The endpoint only provides JSON; JSON is an accepted representation, so the request succeeds. `q` does not make the server produce a format the endpoint does not support.

### 11.6. Testing with `WebTestClient`

Create the following test file. The `spring-boot-starter-test` dependency is already in `pom.xml`:

~~~java
package example.negotiation;

import static org.springframework.http.MediaType.APPLICATION_JSON;
import static org.springframework.http.MediaType.TEXT_PLAIN;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpStatus;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
@AutoConfigureWebTestClient
class NegotiationIntegrationTest {

    @Autowired
    WebTestClient client;

    @Test
    void acceptsJsonRepresentation() {
        client.get()
            .uri("/api/product")
            .accept(APPLICATION_JSON)
            .exchange()
            .expectStatus().isOk()
            .expectHeader()
            .contentTypeCompatibleWith(APPLICATION_JSON)
            .expectBody()
            .jsonPath("$.name").isEqualTo("Keyboard");
    }

    @Test
    void rejectsUnacceptableResponseType() {
        client.get()
            .uri("/api/product")
            .accept(TEXT_PLAIN)
            .exchange()
            .expectStatus()
            .isEqualTo(HttpStatus.NOT_ACCEPTABLE);
    }

    @Test
    void rejectsUnsupportedRequestContentType() {
        client.post()
            .uri("/api/echo")
            .contentType(TEXT_PLAIN)
            .accept(APPLICATION_JSON)
            .bodyValue("name=Pen&price=15")
            .exchange()
            .expectStatus()
            .isEqualTo(HttpStatus.UNSUPPORTED_MEDIA_TYPE);
    }

    @Test
    void decodesJsonAndWritesJson() {
        client.post()
            .uri("/api/echo")
            .contentType(APPLICATION_JSON)
            .accept(APPLICATION_JSON)
            .bodyValue(new NegotiationController.CreateProduct(
                "Pen", 15))
            .exchange()
            .expectStatus().isOk()
            .expectHeader()
            .contentTypeCompatibleWith(APPLICATION_JSON)
            .expectBody()
            .jsonPath("$.id").isEqualTo("R-Pen")
            .jsonPath("$.price").isEqualTo(15);
    }

    @Test
    void acceptsPlainTextAtPlainEndpoint() {
        client.get()
            .uri("/api/plain")
            .accept(TEXT_PLAIN)
            .exchange()
            .expectStatus().isOk()
            .expectHeader()
            .contentTypeCompatibleWith(TEXT_PLAIN)
            .expectBody(String.class)
            .isEqualTo("plain response");
    }
}
~~~

Run the tests:

~~~bash
mvn test
~~~

The tests verify the actual HTTP contract: request media type, response media type, status code, and body. If you change the codecs, dependencies, or mapping, these tests help detect the change.

## 12. How to diagnose when negotiation does not work

When you encounter 406 or 415, check in this order:

1. **Look at the actual request headers:** does the client send the correct `Accept` and `Content-Type`? Tools such as curl, browser DevTools, or HTTP client logs can show the actual values.
2. **Check the endpoint mapping:** which media types do `consumes` and `produces` restrict? Is there another mapping with the same path/method?
3. **Check the parameter/return types:** which DTO does the controller require, which object does it return, or what type of Publisher?
4. **Check the codecs:** is there an `HttpMessageReader` to decode the request type and an `HttpMessageWriter` to encode the response type?
5. **Check media type parameters:** are the charset, multipart boundary, or custom parameters compatible?
6. **Check the actual error:** 400 from a malformed body differs from 415 from an unsupported media type; 404 from a missing route differs from 406 from an unacceptable response representation.
7. **Check functional predicates:** a false `accept`/`contentType` can make a route not match; if you need 406/415, look at fallback routes.
8. **Check proxies/caches:** an intermediary can modify headers or cache the response due to a missing `Vary`.

Do not fix it by immediately removing every `consumes`/`produces` condition. Those conditions may be protecting the API contract. Determine which header is wrong or which codec is missing.

## 13. Common mistakes and how to avoid them

**Mistake 1 — Using `Content-Type` to request a JSON response.** Content-Type describes the body being sent. Use `Accept: application/json` to say the client wants to receive JSON.

**Mistake 2 — Using `Accept` to describe a JSON request body.** The server reads the body according to Content-Type and the reader/decoder. Send `Content-Type: application/json`.

**Mistake 3 — Thinking the two headers must be the same.** A client can send JSON and want a text response. The two headers are independent, in two directions.

**Mistake 4 — Confusing `consumes` with `produces`.** consumes matches the request Content-Type; produces matches Accept/the response representation.

**Mistake 5 — Declaring `produces=application/xml` without an XML writer.** A mapping does not install a codec. You need to register a writer/encoder that actually supports that Java type.

**Mistake 6 — Thinking `Accept: */*` forces the server to return JSON.** A wildcard accepts every media type; it does not express a JSON preference. If you want to prefer JSON, send a JSON media range with an appropriate q.

**Mistake 7 — Thinking `q=0.9` means 90% of requests will use JSON.** This is a quality weight in negotiation, not a probability or a traffic ratio.

**Mistake 8 — Ignoring `q=0`.** A media type with q=0 is excluded from the set of acceptable representations.

**Mistake 9 — Sorting media ranges only by q and ignoring specificity.** A specific range can take precedence over a wildcard range; let the framework handle negotiation or fully follow the HTTP rules.

**Mistake 10 — Confusing 415 with 400.** 415 means the request media type is not supported; 400 is usually a body of the right type whose parsing/validation fails.

**Mistake 11 — Confusing 406 with 404.** 406 means the endpoint/handler may exist but does not produce a suitable representation; 404 usually means there is no suitable route/resource.

**Mistake 12 — Assuming a functional route predicate automatically produces 406/415.** A false predicate makes the route not match; add a fallback route or an explicit status mapping.

**Mistake 13 — Sending Content-Type on GET and expecting it to select a JSON response.** Use Accept. Content-Type is only useful when the request has a body to describe.

**Mistake 14 — Ignoring codecs when adding a media type to a mapping.** A mapping is only a condition; a reader/writer must actually support the format.

**Mistake 15 — Thinking every Flux response streams each item.** A JSON array may be aggregated; use NDJSON/SSE when the protocol needs streaming.

**Mistake 16 — Not adding `Vary: Accept` when caching multiple representations.** The cache may return the wrong variant if the content depends on Accept and the cache does not distinguish it.

**Mistake 17 — Using content negotiation as an authentication mechanism.** Accept/Content-Type are controlled by the client and do not prove identity or permission. Use Spring Security and validate data independently.

**Mistake 18 — Returning raw technical errors to the client.** A 406/415 response should have a safe error code/message; log details on the server and do not expose stack traces or internal configuration.

## 14. Self-check exercises

1. What does `Content-Type` describe? **The representation format of the current request body.**
2. What does `Accept` describe? **The media types the client accepts in the response.**
3. If a client sends JSON and wants to receive text, what could the two headers be? **`Content-Type: application/json` and `Accept: text/plain`.**
4. Which header does `consumes` correspond to? **Content-Type.**
5. Which header does `produces` correspond to? **Accept and the response representation.**
6. Does `Accept: application/*` accept `application/json`? **Yes.**
7. Does `Accept: */*` mean the server must return JSON? **No; every media type is accepted, and the server chooses a suitable representation.**
8. What does `q=0` mean? **That media range is not acceptable.**
9. When the client sends `Accept: text/plain` but the endpoint only produces JSON, what status is commonly seen? **406 Not Acceptable.**
10. When the client sends `Content-Type: text/plain` but the endpoint only consumes JSON, what status is commonly seen? **415 Unsupported Media Type.**
11. If the JSON is malformed but the Content-Type is correct, what error is it usually? **400 Bad Request.**
12. Can you declare `produces=application/xml` without needing an XML writer? **No; a mapping does not create a codec by itself.**
13. In WebFlux, which interface reads the request body? **HttpMessageReader.**
14. Which interface writes the response body? **HttpMessageWriter.**
15. Which header does `RequestPredicates.accept` check? **Accept.**
16. Which header does `RequestPredicates.contentType` check? **Content-Type.**
17. Does a non-matching functional predicate automatically guarantee 406/415? **No; it makes the route not match, and you need a fallback/status mapping if you want a specific error code.**
18. When the same URI has multiple representations depending on Accept, what should the cache know? **Add `Vary: Accept` if the response genuinely changes by that header.**
19. Is `Content-Encoding: gzip` the same as `Content-Type: application/json`? **No; one describes byte compression, the other describes the representation format.**
20. If the server supports JSON but the client sends `Accept: application/json;q=0` and there is no other suitable media range, what can the result be? **406 Not Acceptable.**

## 15. Key takeaways and references

- **`Content-Type`** states the format of the request body being sent; **`Accept`** states the response format the client accepts.
- **`consumes`** matches Content-Type; **`produces`** matches Accept and the ability to produce a response.
- `q` is a quality weight from 0 to 1; `q=0` excludes a media range.
- **406** relates to an unacceptable response representation; **415** relates to an unsupported request media type; **400** usually relates to malformed/invalid content.
- `HttpMessageReader` and the decoder read the request; `HttpMessageWriter` and the encoder write the response.
- Declaring a media type does not install a codec by itself. A compatible reader/writer must exist.
- WebFlux.fn uses the `accept` and `contentType` predicates; a false predicate can make a route not match, so design a fallback if you need an explicit status.
- Use `Vary: Accept` when a cached representation changes by Accept.
- The framework manages the subscription and writes the response; a handler should return a Publisher and not subscribe/block itself.

Official documentation:

1. [Spring Framework Reference — Mapping Requests: consumes and produces](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-requestmapping.html): mapping conditions, `consumes`, `produces`, and media types.
2. [Spring Framework Reference — @RequestBody in WebFlux](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-methods/requestbody.html): decoding the request body and `HttpMessageReader`.
3. [Spring Framework Reference — @ResponseBody in WebFlux](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-methods/responsebody.html): reactive return values and `HttpMessageWriter`.
4. [Spring Framework Reference — WebFlux Functional Endpoints](https://docs.spring.io/spring-framework/reference/6.2/web/webflux-functional.html): `RequestPredicates.accept`, `contentType`, `ServerRequest`, and `ServerResponse`.
5. [Spring Framework Reference — WebFlux Configuration](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/config.html): `ServerCodecConfigurer`, and default and custom codecs.
6. [RFC 9110 — HTTP Semantics, Content Negotiation](https://www.rfc-editor.org/rfc/rfc9110.html#name-content-negotiation): the semantics of Accept, Content-Type, media ranges, quality values, and Vary.
