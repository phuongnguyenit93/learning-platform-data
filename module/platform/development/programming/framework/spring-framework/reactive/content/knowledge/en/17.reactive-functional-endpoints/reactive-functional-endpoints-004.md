# Reading Bodies and Parameters with `ServerRequest` in Spring WebFlux

## 1. `ServerRequest` in the Functional Endpoint Model

Spring WebFlux has two common ways to build HTTP endpoints:

- **Annotated controller:** uses `@RestController`, `@GetMapping`, `@RequestParam`, `@RequestBody`, and similar annotations.
- **Functional endpoint (WebFlux.fn):** declares routes with `RouterFunction` and handles requests with `HandlerFunction`.

In a functional endpoint, the handler receives a **`ServerRequest`** object. This is Spring's abstraction representing the current HTTP request, providing an API to read:

- JSON, text, or streaming data bodies.
- Path variables in the URL.
- Query parameters, including repeated parameters.
- Headers and cookies.
- Form URL-encoded and multipart data.
- Principal, session, request attributes, and `ServerWebExchange`.

A handler usually has the signature:

```java
HandlerFunction<ServerResponse> handler = request -> {
    // Read the request and return a ServerResponse.
    return ServerResponse.ok().build();
};
```

In terms of data types, `HandlerFunction<ServerResponse>` receives a `ServerRequest` and returns a `Mono<ServerResponse>`. `ServerRequest` is not a servlet request and does not provide a synchronous body-reading API. Body-reading operations return `Mono` or `Flux`, so we combine them with reactive operators.

Processing flow:

```text
HTTP client
    |
    | HTTP request
    v
RouterFunction
    |
    | select matching route
    v
HandlerFunction<ServerResponse>
    |
    | receive ServerRequest
    +---- path/query/header/cookie
    |
    +---- bodyToMono / bodyToFlux
    |
    v
Mono<ServerResponse>
    |
    | write status, headers, and body
    v
HTTP response
```

`ServerRequest` is the input for the handler to read the request; `ServerResponse` is the abstraction to build the response. There is no need to call `.subscribe()` yourself inside the handler. Return the Publisher so WebFlux manages the subscription, errors, cancellation, and response writing process.

## 2. Commonly Used Request-Reading APIs

| Need | `ServerRequest` API | Return type |
|---|---|---|
| Read a path variable | `pathVariable("id")` | `String` |
| Read all path variables | `pathVariables()` | `Map<String, String>` |
| Read the first query parameter | `queryParam("status")` | `Optional<String>` |
| Read all query parameters | `queryParams()` | `MultiValueMap<String, String>` |
| Read the first header | `headers().firstHeader("X-Trace-Id")` | `String` or `null` |
| Read header values | `headers().header("Accept")` | `List<String>` |
| Read cookies | `cookies()` | `MultiValueMap<String, HttpCookie>` |
| Read body into a single object | `bodyToMono(MyDto.class)` | `Mono<MyDto>` |
| Read body into multiple objects | `bodyToFlux(MyDto.class)` | `Flux<MyDto>` |
| Read form URL-encoded | `formData()` | `Mono<MultiValueMap<String, String>>` |
| Read multipart | `multipartData()` | `Mono<MultiValueMap<String, Part>>` |
| Read principal | `principal()` | `Mono<Principal>` |
| Read WebSession | `session()` | `Mono<WebSession>` |
| Read request attributes | `attributes()` | `Map<String, Object>` |
| Access low-level API | `exchange()` | `ServerWebExchange` |

Values in paths, queries, and headers are still strings. If you need `Long`, `UUID`, `LocalDate`, or an enum, parse/convert in a controlled manner or use an appropriate conversion service. With functional endpoints, there is no automatic step to bind parameters to method arguments as in annotated controllers; the handler explicitly calls the needed API on `ServerRequest`.

## 3. Reading Path Variables

A path variable is part of the route URL, for example:

```text
GET /customers/42
```

Declare the route and read the value:

```java
RouterFunction<ServerResponse> routes =
        RouterFunctions.route()
                .GET("/customers/{customerId}", request -> {
                    String rawId = request.pathVariable("customerId");
                    return ServerResponse.ok().bodyValue("customer=" + rawId);
                })
                .build();
```

`pathVariable("customerId")` returns a `String`. If you need a number, convert it explicitly:

```java
long customerId;
try {
    customerId = Long.parseLong(request.pathVariable("customerId"));
} catch (NumberFormatException ex) {
    return ServerResponse.badRequest()
            .bodyValue("customerId must be a number");
}
```

This is an illustrative snippet inside the handler, returning `Mono<ServerResponse>`. Do not let a parse error become a 500 server error if it is only invalid client input; return 400 or map the exception with an error handler.

You can get all path variables:

```java
Map<String, String> variables = request.pathVariables();
```

The key names must match the names given in the route template. For example, `/teams/{teamId}/members/{memberId}` provides two keys: `teamId` and `memberId`.

## 4. Reading Query Parameters

Query parameters appear after the `?`:

```text
GET /orders?status=PAID&page=2
```

Use `queryParam` when you only need a single value:

```java
Optional<String> status = request.queryParam("status");
String selectedStatus = status.orElse("ALL");
```

The result is an `Optional<String>` because the parameter might not be sent. For optional data, define a clear default. For required data, return a 400 error if missing:

```java
Optional<String> customer = request.queryParam("customer");
if (customer.isEmpty() || customer.get().isBlank()) {
    return ServerResponse.badRequest()
            .bodyValue("query parameter 'customer' is required");
}
```

### Multi-valued query parameters

The client can send the same key multiple times:

```text
GET /orders?tag=urgent&tag=export&tag=paid
```

`queryParam("tag")` only provides one value; use `queryParams()` if you need all of them:

```java
List<String> tags = request.queryParams().getOrDefault(
        "tag", List.of()
);
```

`queryParams()` is a `MultiValueMap<String, String>`, so each key can hold a list of values. Do not use `Map<String, String>` if the API allows repeated parameters.

### Parsing numeric and date types

```java
int page;
try {
    page = Integer.parseInt(
            request.queryParam("page").orElse("1")
    );
    if (page < 1) {
        return ServerResponse.badRequest()
                .bodyValue("page must be positive");
    }
} catch (NumberFormatException ex) {
    return ServerResponse.badRequest()
            .bodyValue("page must be an integer");
}
```

If there are many types that need conversion, locale rules, or value objects, you can use a configured `ConversionService`/`Formatter`. Do not duplicate complex parsing logic across multiple handlers.

## 5. Reading Headers and Cookies

Headers are commonly used for trace IDs, language, content negotiation, or protocol metadata:

```java
String traceId = request.headers().firstHeader("X-Trace-Id");
String accept = request.headers().firstHeader("Accept");

if (traceId == null || traceId.isBlank()) {
    traceId = "not-provided";
}
```

If a header has multiple values, use:

```java
List<String> accepts = request.headers().header("Accept");
```

Headers sent by the client are not implicitly trustworthy. Do not use `X-User-Id`, `X-Role`, or `X-Tenant-Id` as proof of authentication/authorization unless the system has a trusted proxy that authenticates and overwrites them. For logged-in users, obtain the identity from the Spring Security mechanism and `request.principal()` or the corresponding reactive security API.

Cookies can be read with:

```java
HttpCookie sessionCookie =
        request.cookies().getFirst("SESSION");
```

`getFirst` returns the first cookie or `null`. Do not log raw session cookie values or tokens; they could allow someone to hijack the login session.

## 6. Reading the Body into One Object with `bodyToMono`

For a JSON request containing only one object, use `bodyToMono`:

```java
public record CreateOrderRequest(
        String product,
        int quantity
) {}

Mono<CreateOrderRequest> body =
        request.bodyToMono(CreateOrderRequest.class);
```

Spring uses an `HttpMessageReader`/codec matching the request's `Content-Type` to decode bytes into a Java object. In a typical WebFlux application, the Jackson codec can read JSON when the corresponding dependency is on the classpath.

A handler can combine the body and query parameters:

```java
Mono<ServerResponse> create(ServerRequest request) {
    return request.bodyToMono(CreateOrderRequest.class)
            .flatMap(body -> {
                String source = request.queryParam("source")
                        .orElse("web");

                return ServerResponse.ok().bodyValue(
                        "created " + body.product()
                                + ", quantity=" + body.quantity()
                                + ", source=" + source
                );
            });
}
```

`bodyToMono` emits at most one object. If the body has no data, the Mono may complete empty. When the body is required, handle that case with `switchIfEmpty`:

```java
return request.bodyToMono(CreateOrderRequest.class)
        .flatMap(this::saveOrder)
        .switchIfEmpty(
                ServerResponse.badRequest()
                        .bodyValue("request body is required")
        );
```

`saveOrder` here is an illustrative function returning `Mono<ServerResponse>`. In real code, check the return type so `flatMap` composes the right Publisher.

## 7. Reading Generic or Collection Bodies

If the body is a collection such as `List<LineItem>`, simply passing `List.class` loses the element type information at runtime. Use `ParameterizedTypeReference`:

```java
private static final ParameterizedTypeReference<List<LineItem>>
        LINE_ITEMS_TYPE = new ParameterizedTypeReference<>() {};

Mono<List<LineItem>> lines =
        request.bodyToMono(LINE_ITEMS_TYPE);
```

Where `LineItem` is an application record or DTO class. `ParameterizedTypeReference` preserves the generic information so the codec knows to decode each element into `LineItem`.

If the body is actually a stream of multiple objects, you do not necessarily have to read it into a large List. Use `bodyToFlux` when the media type and codec support a suitable streaming format.

## 8. Reading Multi-Element Bodies with `bodyToFlux`

`bodyToFlux` is suitable for streaming bodies with multiple elements, such as JSON Lines/NDJSON:

```java
Flux<EventInput> events =
        request.bodyToFlux(EventInput.class);
```

If the request uses `application/x-ndjson`, each JSON line can be decoded into an `EventInput` when the codec supports it. The handler can process each element:

```java
return request.bodyToFlux(EventInput.class)
        .concatMap(event -> eventService.accept(event))
        .then(ServerResponse.accepted().build());
```

`eventService.accept(event)` is an illustrative function returning `Mono<?>`; in a real application you need to choose the appropriate result type. `concatMap` processes sequentially and preserves order. If you use `flatMap`, multiple elements can be processed concurrently; you need to set a concurrency limit under heavy load and accept that completion order may differ from input order.

`Flux` enables streaming processing and respects demand in reactive operators. Avoid `.collectList()` for unbounded or very large bodies if you do not need to store the entire payload in RAM.

## 9. The Body Should Only Be Consumed Once

The HTTP request body is a data stream. In a functional handler, you should not call `bodyToMono` twice for the same request:

```java
// ANTI-PATTERN: trying to read the same body twice.
Mono<CreateOrderRequest> first =
        request.bodyToMono(CreateOrderRequest.class);

Mono<CreateOrderRequest> second =
        request.bodyToMono(CreateOrderRequest.class);
```

A body usually cannot be replayed automatically; the second read may receive an empty body, an error, or source-dependent behavior. Decode once and then pass the read object through the processing steps:

```java
return request.bodyToMono(CreateOrderRequest.class)
        .flatMap(body ->
                validate(body)
                        .then(save(body))
        );
```

`validate` and `save` are illustrative functions. If you truly need to cache/replay the body for multiple components to read, you must have a bounded buffering design, handle DataBuffer ownership properly, and consider the maximum size. Do not buffer the entire body arbitrarily because large requests can exhaust memory.

## 10. Reading Form URL-Encoded Data

An HTML form of type `application/x-www-form-urlencoded` is not JSON. Use `formData()`:

```java
Mono<ServerResponse> submitForm(ServerRequest request) {
    return request.formData()
            .flatMap(form -> {
                String email = form.getFirst("email");
                String note = form.getFirst("note");

                if (email == null || email.isBlank()) {
                    return ServerResponse.badRequest()
                            .bodyValue("email is required");
                }

                return ServerResponse.ok()
                        .bodyValue("received " + email);
            });
}
```

`formData()` returns `Mono<MultiValueMap<String, String>>`; each field can have multiple values. Only call this API when the request sends the right kind of form data. For JSON bodies, use `bodyToMono`/`bodyToFlux`.

## 11. Reading Multipart and File Uploads

A `multipart/form-data` request can contain text fields and files. Use `multipartData()`:

```java
Mono<MultiValueMap<String, Part>> multipart =
        request.multipartData();
```

Example of reading a file part:

```java
return request.multipartData()
        .flatMap(parts -> {
            Part part = parts.getFirst("document");

            if (!(part instanceof FilePart file)) {
                return ServerResponse.badRequest()
                        .bodyValue("document file is required");
            }

            String originalFilename = file.filename();

            // Pass file.content() to the application-defined upload service.
            return uploadService.store(file.content(), originalFilename)
                    .then(ServerResponse.accepted().build());
        });
```

`uploadService.store(...)` is an illustrative function; the application must implement file storage itself and return `Mono<?>`. For file uploads, you need to:

- Limit the size of the request and each individual file.
- Check the actual content type; do not blindly trust the filename or `Content-Type` sent by the client.
- Generate the destination filename on the server side; do not concatenate client-supplied paths directly onto the filesystem.
- Handle streams and cleanup properly on error or client cancellation.
- Do not call `collectList()` or read the entire file into RAM if the file can be large.
- Configure multipart and memory buffer limits appropriate for your WebFlux version/configuration.

`Part` represents one multipart part; `FilePart` is a part containing a file. For large files, process `file.content()` as a stream or use `transferTo(Path)` with a server-controlled path.

## 12. Principal, Session, and Attributes

In addition to direct HTTP data, `ServerRequest` also allows access to runtime information:

```java
Mono<Principal> principal = request.principal();

Mono<WebSession> session = request.session();

Map<String, Object> attributes = request.attributes();
```

- `principal()` returns the identity set by the security layer if present; it does not authenticate the user on its own just because this method exists.
- `session()` returns a reactive `WebSession`. Reading/writing the session must be chained in the pipeline, avoiding blocking.
- `attributes()` provides attributes attached to the request/exchange by the framework or filters.
- `exchange()` gives access to `ServerWebExchange` when a lower-level API is needed that `ServerRequest` does not directly provide.

Do not store sensitive request data in attributes or log the entire map. For authentication and authorization, use reactive Spring Security APIs and check permissions at the service/domain layer.

## 13. Content-Type, Codecs, and Decode Errors

`bodyToMono` and `bodyToFlux` do not parse every format by themselves. Spring selects an `HttpMessageReader` based on the target type and media type.

Example:

| Content-Type | Common reading approach |
|---|---|
| `application/json` | `bodyToMono(Dto.class)` or `bodyToFlux(Dto.class)` |
| `application/x-ndjson` | `bodyToFlux(Dto.class)` for JSON Lines |
| `text/plain` | `bodyToMono(String.class)` |
| `application/x-www-form-urlencoded` | `formData()` |
| `multipart/form-data` | `multipartData()` |

If the client sends JSON but omits or sends the wrong `Content-Type`, the server may not be able to select the corresponding codec. If the JSON is syntactically invalid or cannot be converted into the DTO, the decode process emits a reactive error; the handler or global error handler must map it to HTTP 400. Unsupported media types typically lead to HTTP 415.

When custom codecs are needed, configure `ServerCodecConfigurer` via `WebFluxConfigurer.configureHttpMessageCodecs(...)` or `HandlerStrategies` if building a WebFlux.fn server manually. Do not use `Converter`/`Formatter` to replace a JSON codec: the conversion service handles type conversion in binding, whereas message readers/writers handle the HTTP body.

Set body size and in-memory buffering limits. For large JSON requests or file uploads, consider streaming with `Flux` instead of buffering unbounded data into a single object.

## 14. A Complete Java 17+ Example with Spring Boot WebFlux

This example has two functional routes:

- `POST /customers/{customerId}/orders?source=web`: reads the path variable, query parameter, and JSON body, then validates the data.
- `GET /orders?status=PAID&tag=urgent&tag=export`: reads a repeated query parameter and the `X-Trace-Id` header.

Structure:

```text
server-request-demo/
├── pom.xml
└── src/main/java/demo/Main.java
└── src/main/java/demo/OrderHandler.java
```

### File `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>server-request-demo</artifactId>
    <version>1.0-SNAPSHOT</version>

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

### File `src/main/java/demo/Main.java`

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.web.reactive.function.server.RouterFunction;
import org.springframework.web.reactive.function.server.RouterFunctions;
import org.springframework.web.reactive.function.server.ServerResponse;

@SpringBootApplication
public class Main {

    public static void main(String[] args) {
        SpringApplication.run(Main.class, args);
    }

    @Bean
    RouterFunction<ServerResponse> routes(OrderHandler handler) {
        return RouterFunctions.route()
                .POST("/customers/{customerId}/orders", handler::create)
                .GET("/orders", handler::search)
                .build();
    }
}
```

### File `src/main/java/demo/OrderHandler.java`

```java
package demo;

import java.util.List;
import java.util.Set;
import java.util.stream.Collectors;

import jakarta.validation.ConstraintViolation;
import jakarta.validation.Validator;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Positive;

import org.springframework.core.codec.DecodingException;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.server.ServerRequest;
import org.springframework.web.reactive.function.server.ServerResponse;

import reactor.core.publisher.Mono;

@Component
public class OrderHandler {

    private final Validator validator;

    public OrderHandler(Validator validator) {
        this.validator = validator;
    }

    public Mono<ServerResponse> create(ServerRequest request) {
        final long customerId;

        try {
            customerId = Long.parseLong(
                    request.pathVariable("customerId")
            );
        } catch (NumberFormatException ex) {
            return ServerResponse.badRequest()
                    .bodyValue("customerId must be a number");
        }

        return request.bodyToMono(CreateOrderRequest.class)
                .flatMap(body -> {
                    Set<ConstraintViolation<CreateOrderRequest>> violations =
                            validator.validate(body);

                    if (!violations.isEmpty()) {
                        String message = violations.stream()
                                .map(v -> v.getPropertyPath()
                                        + ": " + v.getMessage())
                                .collect(Collectors.joining("; "));

                        return ServerResponse.badRequest()
                                .bodyValue(message);
                    }

                    String source = request.queryParam("source")
                            .filter(value -> !value.isBlank())
                            .orElse("web");

                    CreateOrderResponse response =
                            new CreateOrderResponse(
                                    customerId,
                                    body.product(),
                                    body.quantity(),
                                    source
                            );

                    return ServerResponse.status(HttpStatus.CREATED)
                            .contentType(MediaType.APPLICATION_JSON)
                            .bodyValue(response);
                })
                .switchIfEmpty(
                        ServerResponse.badRequest()
                                .bodyValue("JSON request body is required")
                )
                .onErrorResume(DecodingException.class, error ->
                        ServerResponse.badRequest()
                                .bodyValue("Request JSON is invalid")
                );
    }

    public Mono<ServerResponse> search(ServerRequest request) {
        String status = request.queryParam("status").orElse("ALL");

        List<String> tags = request.queryParams().getOrDefault(
                "tag", List.of()
        );

        String traceId = request.headers().firstHeader("X-Trace-Id");
        if (traceId == null) {
            traceId = "";
        }

        SearchResponse response =
                new SearchResponse(status, tags, traceId);

        return ServerResponse.ok()
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(response);
    }

    public record CreateOrderRequest(
            @NotBlank String product,
            @Positive int quantity
    ) {}

    public record CreateOrderResponse(
            long customerId,
            String product,
            int quantity,
            String source
    ) {}

    public record SearchResponse(
            String status,
            List<String> tags,
            String traceId
    ) {}
}
```

Run from the project directory using JDK 17+ and Maven:

```bash
mvn spring-boot:run
```

### Try the POST route

```bash
curl -i -X POST "http://localhost:8080/customers/42/orders?source=web" \
  -H "Content-Type: application/json" \
  -d '{"product":"book","quantity":2}'
```

JSON response body:

```json
{"customerId":42,"product":"book","quantity":2,"source":"web"}
```

In this request:

- `42` is retrieved from `request.pathVariable("customerId")`.
- `{"product":"book","quantity":2}` is decoded using `bodyToMono(CreateOrderRequest.class)`.
- `source=web` is read using `queryParam("source")`.
- `Validator` checks `@NotBlank` and `@Positive` after decoding.

### Try the GET route

```bash
curl -i \
  -H "X-Trace-Id: req-17" \
  "http://localhost:8080/orders?status=PAID&tag=urgent&tag=export"
```

JSON response body:

```json
{"status":"PAID","tags":["urgent","export"],"traceId":"req-17"}
```

In this request, `status` is a single query, `tag` is a repeated query, and `X-Trace-Id` is read from the header.

If you send a quantity of `0` or an empty product, the validator returns a 400 error. If you send a body with no data, the handler returns 400 with a message stating that the body is required. Syntactically invalid JSON is mapped to 400 via `DecodingException` in the example; unsupported media type errors are handled by WebFlux's exception mechanism (usually 415).

This is a standalone Spring Boot WebFlux application. There is no need to create `HttpServer`, `HttpHandler`, or call `.subscribe()` yourself in the handler; Boot manages the server and functional routes.

## 15. Distinguishing `ServerRequest` from Annotated Controllers

| Task | Functional endpoint | Annotated controller |
|---|---|---|
| Get path variable | `request.pathVariable("id")` | `@PathVariable long id` |
| Get query parameter | `request.queryParam("page")` | `@RequestParam int page` |
| Get header | `request.headers().firstHeader("X-Trace-Id")` | `@RequestHeader("X-Trace-Id") String traceId` |
| Get cookie | `request.cookies().getFirst("SESSION")` | `@CookieValue("SESSION") String session` |
| Read JSON body | `request.bodyToMono(Dto.class)` | `@RequestBody Mono<Dto>` or `Dto` |
| Read stream body | `request.bodyToFlux(Event.class)` | `@RequestBody Flux<Event>` |
| Return response | `ServerResponse.ok().bodyValue(value)` | Return `Mono<T>`/`Flux<T>` or `ResponseEntity` |

Both models use the WebFlux reactive runtime and message codecs. The difference lies in how routes are declared and how input data is obtained. Use `ServerRequest` when choosing functional endpoints and needing explicit control over how the request is read in the handler; use annotated controllers if you want Spring to bind parameters directly into the method signature.

Do not mix the two styles just to read the same request. Choose one consistent endpoint model according to the application's structure.

## 16. Validation and Error Handling

**Successful decoding does not mean the data is valid.** There are three distinct steps:

1. **Reading the body:** the codec turns bytes into a Java object.
2. **Conversion/decoding:** if the JSON is invalid or types are incompatible, a decode error is emitted.
3. **Business validation:** checking that the product is non-blank, quantity is positive, ownership, or domain rules.

In a functional handler, you can use a Jakarta `Validator` as in the example above. With annotated controllers, `@Valid`/`@Validated` is integrated into argument binding according to Spring configuration.

Do not catch every exception and return 400. Database errors, programming errors, and system errors are not always client input errors. Map errors by type:

- Malformed body or undecodable fields: typically 400.
- Unsupported `Content-Type`: typically 415.
- Invalid query/path value: 400.
- Unauthenticated: 401.
- Insufficient permissions: 403.
- Resource does not exist: 404.
- Unexpected internal error: 500.

Use `WebExceptionHandler` or the application's error-handling mechanism to standardize error responses across multiple routes. Individual handlers should only recover from errors they understand and can handle properly.

## 17. Common Mistakes and How to Fix Them

| Mistake | Consequence | Fix |
|---|---|---|
| Treating a query parameter as the request body | Reads from the wrong data source or gets empty | Use `queryParam` for URL queries and `bodyToMono` for the body |
| Only using `queryParam` when the key can repeat | Loses the second and subsequent values | Use `queryParams()` and get the list |
| Parsing a path variable into a number without catching errors | Invalid input can become a 500 error | Parse in a controlled way and return 400 |
| Calling `bodyToMono` multiple times | The body may have already been consumed | Decode once and then pass the object through the pipeline |
| Collecting a large stream with `collectList()` | Increases memory, loses streaming benefits | Use `bodyToFlux` and process element by element |
| Using `bodyToMono(List.class)` | Loses the generic element type | Use `ParameterizedTypeReference<List<T>>` |
| Using `formData()` for JSON | No properly formatted form data | Choose the API based on `Content-Type` |
| Using `bodyToMono` to read multipart | Ignores part/file structure | Use `multipartData()` |
| Trusting a client-sent header as identity | Risk of user/tenant spoofing | Use Spring Security and a trusted proxy |
| Logging the entire body/cookies | May expose passwords, tokens, or personal data | Log safe metadata and mask sensitive data |
| Ignoring body/upload limits | Can exhaust memory or resources | Configure codec/multipart limits and streaming |
| Calling `.block()`/`.subscribe()` in a handler | Detaches the lifecycle or blocks the event loop | Return `Mono<ServerResponse>`/`Flux` for WebFlux to manage |
| Using a converter instead of a JSON codec | JSON body is not decoded as expected | Configure the appropriate `HttpMessageReader`/codec |
| Thinking functional endpoints automatically validate all DTOs | Business-invalid data still slips into the service | Call Jakarta Validator or domain validation explicitly |

## 18. Testing Functional Endpoints

You can test a `RouterFunction` using `WebTestClient` without opening a real TCP port:

```java
WebTestClient client = WebTestClient
        .bindToRouterFunction(routes)
        .build();

client.post()
        .uri("/customers/42/orders?source=web")
        .contentType(MediaType.APPLICATION_JSON)
        .bodyValue(new CreateOrderRequest("book", 2))
        .exchange()
        .expectStatus().isCreated()
        .expectBody()
        .jsonPath("$.customerId").isEqualTo(42)
        .jsonPath("$.product").isEqualTo("book")
        .jsonPath("$.quantity").isEqualTo(2);
```

This is an illustrative test snippet; it requires the `WebTestClient`, `MediaType`, `CreateOrderRequest` types and the created route. `bindToRouterFunction` is suitable for testing functional routing and handlers. If you need to test the actual codec/server, TLS, multipart limits, or network behavior, add an integration test running the server on a test port.

You should have tests for:

- Valid JSON body and empty body.
- Syntactically invalid JSON or unsupported Content-Type.
- Unparseable path variable.
- Missing, repeated, and blank-valued query parameters.
- Missing or invalid headers/cookies.
- Form URL-encoded and multipart uploads.
- Decodable DTO that fails validation.
- Client cancellation while sending a streaming body.

## 19. Handler Writing Checklist

1. Identify the route and data source: path, query, header, cookie, form, multipart, or body.
2. Use the corresponding `ServerRequest` API; do not parse raw HTTP yourself unnecessarily.
3. For the body, choose `bodyToMono` for one object and `bodyToFlux` for a stream.
4. Decode the body once; pass the read object to subsequent steps.
5. Handle `Optional`, repeated queries, empty bodies, and parse errors deliberately.
6. Check `Content-Type`, codecs, and size limits.
7. Separate decoding, validation, and business logic.
8. Do not trust client-supplied authentication metadata.
9. Keep the reactive chain; do not block or subscribe manually in the handler.
10. Test routes, body, parameters, errors, and cancellation with `WebTestClient`.

**Key takeaway:** `ServerRequest` is the gateway for reading HTTP requests in functional endpoints. Use `pathVariable` and `queryParam` for URL data, `headers()`/`cookies()` for metadata, `formData()`/`multipartData()` for forms, and `bodyToMono`/`bodyToFlux` for the body. After decoding, validation and business logic still need to be handled explicitly in the reactive pipeline.

## 20. Official References

- [Spring Framework — Functional Endpoints (WebFlux.fn)](https://docs.spring.io/spring-framework/reference/web/webflux-functional.html)
- [Spring Framework — ServerRequest Javadoc 6.1](https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/web/reactive/function/server/ServerRequest.html)
- [Spring Framework — ServerResponse Javadoc 6.1](https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/web/reactive/function/server/ServerResponse.html)
- [Spring Framework — BodyExtractors Javadoc 6.1](https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/web/reactive/function/BodyExtractors.html)
- [Spring Framework — WebFlux HTTP Message Codecs](https://docs.spring.io/spring-framework/reference/web/webflux/config.html)
- [Spring Framework — WebFlux Validation](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-validation.html)
