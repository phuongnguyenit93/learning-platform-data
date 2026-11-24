# WebClient: Sending Reactive Requests and Configuring URI, Headers, Cookies, and Body

## Objectives

This lesson guides you through using Spring WebFlux `WebClient` to **send HTTP requests in a reactive style**, configure **URIs, headers, cookies, and request bodies**, read responses, and handle errors properly. After this lesson, you will be able to build GET/POST requests with dynamic parameters, send JSON/form/multipart payloads, compose `Mono`/`Flux` pipelines, and avoid common pitfalls when combining HTTP with Reactive Streams. Examples use Java 17+, Spring Framework 6.x, and Spring Boot 3.x.

## 1. How Does WebClient Work?

`WebClient` is an HTTP client with a fluent API supporting non-blocking I/O and streaming. It lives in `org.springframework.web.reactive.function.client` and uses Reactor to model asynchronous results. A typical pipeline:

```text
WebClient
  -> GET / POST / PUT / PATCH / DELETE
  -> URI (path, path variable, query parameter)
  -> request headers + cookies + body if present
  -> retrieve() or exchangeToMono(...)
  -> bodyToMono(...) / bodyToFlux(...) / toEntity(...)
  -> subscription -> HTTP I/O -> decode response
```

Example:

```java
WebClient client = WebClient.create("https://api.example.com");

Mono<String> pending = client.get()
        .uri("/health")
        .retrieve()
        .bodyToMono(String.class);
```

`Mono<T>` represents at most one element; `Flux<T>` represents multiple elements. **Creating a `Mono` does not mean the request has been sent**: WebClient publishers are *cold*, and HTTP I/O is triggered when a subscriber subscribes. In a WebFlux application, return `Mono`/`Flux` so the framework manages the subscription. In a console demo, `block` can be used at an intentional synchronous boundary.

Do not call `subscribe()` arbitrarily inside a service just to "make the request run": detaching the pipeline loses error propagation, cancellation, and execution context. Each subscription to a cold publisher can trigger a new request; this is especially critical for POST requests with side effects.

## 2. Initializing the Client and Default Configuration

When a Spring Boot project already manages library versions, the common dependency is:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
}
```

You can use WebClient inside a Spring MVC application to call HTTP services; adding the client does not force converting controllers to WebFlux. Spring Boot provides a `WebClient.Builder` preconfigured for the application environment:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
class ClientConfig {
    @Bean
    WebClient catalogClient(WebClient.Builder builder) {
        return builder
                .baseUrl("https://catalog.example.com/api")
                .defaultHeader("X-Application", "web-learning")
                .build();
    }
}
```

You can quickly initialize with `WebClient.create()`, `WebClient.create(baseUrl)`, or `WebClient.builder()`. Use a shared, preconfigured client and reuse it rather than creating a new HTTP client/connection pool per request.

`baseUrl` sets the shared URI prefix; `defaultHeader` and `defaultCookie` set default values; `filter` is used for cross-cutting concerns such as safe logging, correlation, or auth; `clientConnector` configures the HTTP transport layer. `mutate()` creates a builder from an existing configuration. Never place **per-user** tokens or cookies on a shared singleton client.

## 3. Building Safe URIs

### 3.1. URI Templates with Path Variables

```java
Mono<String> response = client.get()
        .uri("/orders/{id}", 42)
        .retrieve()
        .bodyToMono(String.class);
```

With base URL `https://api.example.com`, the request targets `https://api.example.com/orders/42`. `{id}` is a variable placeholder; using URI templates is more readable and safer for encoding than manual string concatenation.

### 3.2. URI Builder with Query Parameters

```java
Mono<String> response = client.get()
        .uri(uriBuilder -> uriBuilder
                .path("/books")
                .queryParam("keyword", "spring reactive")
                .queryParam("page", 1)
                .queryParam("size", 20)
                .build())
        .retrieve()
        .bodyToMono(String.class);
```

The request carries `keyword`, `page`, and `size` in the query string. Spaces in `keyword` must be encoded; depending on the URI builder configuration, spaces may be represented as `%20`. Do not manually concatenate `?`/`&` or double-encode already encoded values.

Combining path variables and query parameters:

```java
Mono<String> response = client.get()
        .uri(builder -> builder
                .path("/customers/{customerId}/orders")
                .queryParam("status", "OPEN")
                .queryParam("page", 0)
                .build(7))
        .retrieve()
        .bodyToMono(String.class);
```

The path identifies the resource, e.g., `/customers/7/orders`; the query holds filters and pagination, e.g., `?status=OPEN&page=0`. `pathSegment(...)` is useful when appending individual segments; `queryParamIfPresent(...)` is useful when you only want to send a parameter if an `Optional` has a value.

### 3.3. Relative vs. Absolute Addresses

`baseUrl(...)` applies to relative URIs. Passing an absolute URI directly can override the base URL. If a URI or host comes from external input, validate the scheme and an allowlist of permitted hosts to prevent SSRF; URI encoding is not target authorization.

## 4. HTTP Methods and Headers

Common HTTP methods:

| Method | Common Purpose | WebClient |
| --- | --- | --- |
| GET | Read a resource or list | `client.get()` |
| POST | Create a resource, send a command or data | `client.post()` |
| PUT | Replace a resource | `client.put()` |
| PATCH | Partially update | `client.patch()` |
| DELETE | Delete a resource | `client.delete()` |

The API contract dictates exact semantics. GET typically passes read criteria via URI/query rather than a body.

### 4.1. Attaching Headers

```java
Mono<String> product = client.get()
        .uri("/products/{id}", 42)
        .accept(MediaType.APPLICATION_JSON)
        .header("X-Request-Id", "req-42")
        .headers(h -> h.setBearerAuth(accessToken))
        .retrieve()
        .bodyToMono(String.class);
```

Important APIs:

- `header("X-Request-Id", "req-42")` adds a header value to the request.
- `headers(h -> h.set("X-Request-Id", "req-42"))` operates directly on `HttpHeaders`; `set` replaces previous values of the same header name.
- `accept(MediaType.APPLICATION_JSON)` declares the expected response format: `Accept: application/json`.
- `contentType(MediaType.APPLICATION_JSON)` declares the format of the payload **being sent**: `Content-Type: application/json`.
- `headers(h -> h.setBearerAuth(token))` sets `Authorization: Bearer ...`.
- `headers(h -> h.setBasicAuth(username, password))` creates Basic auth; use only over HTTPS.

**Common confusion:** `Accept` describes the data type you want to *receive*; `Content-Type` describes the data type you are *sending*. Setting `Content-Type` does not create a body by itself. A GET without a body usually only needs `Accept` when specifying response format.

HTTP header names are case-insensitive. `header(...)` can add multiple values; when you want a single value, use `headers(h -> h.set(...))`. Never log Authorization, cookies, or secrets, and never hardcode passwords/tokens in source code.

## 5. Cookies in Requests

Cookies are sent via the `Cookie` header, often carrying session identifiers or values defined by the API contract:

```java
Mono<String> profile = client.get()
        .uri("/me")
        .cookie("session", sessionToken)
        .cookies(c -> c.add("locale", "vi-VN"))
        .retrieve()
        .bodyToMono(String.class);
```

The equivalent HTTP form is typically `Cookie: session=...; locale=vi-VN`. If a cookie applies across all requests of a client:

```java
WebClient client = WebClient.builder()
        .baseUrl("https://api.example.com")
        .defaultCookie("locale", "vi-VN")
        .build();
```

Distinguish clearly: `Cookie` is a request header; `Set-Cookie` is a response header. WebClient does not automatically maintain a browser-like cookie jar. If you need to store `Set-Cookie` and resend it on subsequent requests, the application must manage it explicitly and avoid leaking across users.

Do not put a single user's session token in `defaultCookie` on a singleton client; attach per-request cookies and transmit sensitive data only over HTTPS to trusted destinations.

## 6. Sending a Request Body

The HTTP body carries the payload, commonly used with POST, PUT, and PATCH. WebClient uses Spring HTTP message writers/codecs to encode Java objects into JSON, text, form, or multipart.

### 6.1. Ready JSON DTO: bodyValue

```java
record CreateBookRequest(String title, int quantity) {}

Mono<String> created = client.post()
        .uri("/books")
        .contentType(MediaType.APPLICATION_JSON)
        .accept(MediaType.APPLICATION_JSON)
        .bodyValue(new CreateBookRequest("Java", 2))
        .retrieve()
        .bodyToMono(String.class);
```

When a Jackson JSON codec is present, the record is encoded into a JSON object with `title` and `quantity`. Use `bodyValue` when you already have a concrete value such as a DTO, record, or string.

### 6.2. Input as Mono/Flux: body(Publisher, Class)

```java
Mono<CreateBookRequest> requestBody =
        Mono.just(new CreateBookRequest("Java", 2));

Mono<String> created = client.post()
        .uri("/books")
        .contentType(MediaType.APPLICATION_JSON)
        .body(requestBody, CreateBookRequest.class)
        .retrieve()
        .bodyToMono(String.class);
```

`body(publisher, elementClass)` is used when the input data is already a reactive publisher. **Do not pass a `Mono` to `bodyValue`**; a publisher is not a DTO to serialize. With `Flux<T>`, the server must support an appropriate streaming media type/format; an endpoint expecting a single JSON object does not automatically become a streaming endpoint.

### 6.3. Form URL Encoded

```java
Mono<String> response = client.post()
        .uri("/login")
        .body(BodyInserters.fromFormData("username", "demo")
                .with("locale", "vi"))
        .retrieve()
        .bodyToMono(String.class);
```

Import `org.springframework.web.reactive.function.BodyInserters`. Data is encoded by the writer as `application/x-www-form-urlencoded`. Both form bodies and query parameters hold key/value pairs, but they reside in different parts of the HTTP request.

### 6.4. Multipart with Files

```java
MultipartBodyBuilder parts = new MultipartBodyBuilder();
parts.part("description", "Sample file");
parts.part("file", new FileSystemResource(Path.of("report.txt")));

Mono<String> response = client.post()
        .uri("/upload")
        .bodyValue(parts.build())
        .retrieve()
        .bodyToMono(String.class);
```

Import `org.springframework.http.client.MultipartBodyBuilder`, `org.springframework.core.io.FileSystemResource`, and `java.nio.file.Path`. The snippet assumes `report.txt` exists and the API expects `description`/`file`. Let the writer set the multipart boundary; do not manually add `Content-Type: multipart/form-data` without a boundary.

### 6.5. Distinguishing the Four Information Groups

| Request Part | Example | Role |
| --- | --- | --- |
| URI/path/query | `/books/42?lang=vi` | Target resource and URL parameters |
| Header | `Accept: application/json` | Metadata and content negotiation |
| Cookie | `Cookie: session=abc` | State/session information |
| Body | `{"title":"Java","quantity":2}` | Data sent to the server |

Do not place passwords or access tokens in the query string when an appropriate header can be used: URLs are easily recorded in logs, caches, or access histories.

## 7. Runnable Java 17+ Demo: Sending URI, Header, Cookie, and JSON Body

The following example runs a local HTTP server using JDK `HttpServer`, then uses WebClient to POST to that server. The server verifies four elements of the request; if valid, it returns HTTP 201 and JSON, otherwise 400. The goal is to verify the full pipeline without relying on an external API.

**Project structure:**

```text
webclient-demo/
  build.gradle
  src/main/java/demo/WebClientRequestDemo.java
```

**build.gradle** (Gradle and JDK 17+, Spring Boot 3.3.x BOM pins compatible versions):

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
    mainClass = 'demo.WebClientRequestDemo'
}
```

**src/main/java/demo/WebClientRequestDemo.java:**

```java
package demo;

import com.sun.net.httpserver.HttpServer;
import org.springframework.http.MediaType;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.time.Duration;

public class WebClientRequestDemo {
    public record CreateOrderRequest(String product, int quantity) {}
    public record OrderResult(long id, boolean accepted) {}

    public static void main(String[] args) throws Exception {
        // Port 0 lets the OS pick an available local port.
        HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 0);

        server.createContext("/api/orders/", exchange -> {
            try {
                String uri = exchange.getRequestURI().toString();
                String requestId = exchange.getRequestHeaders()
                        .getFirst("X-Request-Id");
                String cookie = exchange.getRequestHeaders()
                        .getFirst("Cookie");
                String contentType = exchange.getRequestHeaders()
                        .getFirst("Content-Type");
                String json = new String(
                        exchange.getRequestBody().readAllBytes(),
                        StandardCharsets.UTF_8);

                boolean valid = "POST".equals(exchange.getRequestMethod())
                        && "/api/orders/42?source=guide".equals(uri)
                        && "req-42".equals(requestId)
                        && "session=demo-token".equals(cookie)
                        && "application/json".equals(contentType)
                        && json.contains("\"product\":\"book\"")
                        && json.contains("\"quantity\":2");

                int status = valid ? 201 : 400;
                String data = valid
                        ? "{\"id\":42,\"accepted\":true}"
                        : "{\"error\":\"invalid request\"}";
                byte[] responseBytes = data.getBytes(StandardCharsets.UTF_8);
                exchange.getResponseHeaders()
                        .set("Content-Type", "application/json");
                exchange.sendResponseHeaders(status, responseBytes.length);
                try (OutputStream out = exchange.getResponseBody()) {
                    out.write(responseBytes);
                }
            } finally {
                exchange.close();
            }
        });

        server.start();
        try {
            int port = server.getAddress().getPort();
            WebClient client = WebClient.builder()
                    .baseUrl("http://127.0.0.1:" + port)
                    .build();

            Mono<OrderResult> pending = client.post()
                    .uri(uri -> uri.path("/api/orders/{id}")
                            .queryParam("source", "guide")
                            .build(42))
                    .header("X-Request-Id", "req-42")
                    .cookie("session", "demo-token")
                    .contentType(MediaType.APPLICATION_JSON)
                    .accept(MediaType.APPLICATION_JSON)
                    .bodyValue(new CreateOrderRequest("book", 2))
                    .retrieve()
                    .bodyToMono(OrderResult.class);

            // block only at the console demo boundary; do not block on the event loop.
            OrderResult result = pending.block(Duration.ofSeconds(5));
            System.out.println("id=" + result.id()
                    + ", accepted=" + result.accepted());
        } finally {
            server.stop(0);
        }
    }
}
```

Run in the demo directory using `gradle run` if Gradle is installed; or `./gradlew run` when the project includes a Gradle Wrapper.

**Line printed to stdout by the program:**

```text
id=42, accepted=true
```

Step-by-step explanation:

1. `uri(...)` constructs `/api/orders/42?source=guide` from template/path/query.
2. `header(...)` creates `X-Request-Id: req-42` to identify the request.
3. `cookie(...)` sends `session=demo-token`.
4. `contentType(...)` and `bodyValue(...)` send the record as JSON.
5. `retrieve().bodyToMono(OrderResult.class)` decodes the JSON response; a 400 status emits an HTTP error.
6. `block` in `main` lets the console wait for the result and print it; a real WebFlux service should return `Mono<OrderResult>`.

This sample app is not a production server. It simply lets you observe that missing or incorrect values in any component break the expected HTTP request contract.

## 8. Receiving Responses, Status, and Errors

Commonly used methods:

```java
Mono<String> text = client.get()
        .uri("/status")
        .retrieve()
        .bodyToMono(String.class);

Mono<ResponseEntity<String>> full = client.get()
        .uri("/status")
        .retrieve()
        .toEntity(String.class);

Flux<EventDto> events = client.get()
        .uri("/events")
        .accept(MediaType.TEXT_EVENT_STREAM)
        .retrieve()
        .bodyToFlux(EventDto.class);
```

Here `EventDto` is only an illustrative application-defined DTO type; the server must actually emit a matching stream to use `bodyToFlux` with that type. `toEntity` reads both status and headers; `bodyToMono` reads at most one body object; for bodyless responses (e.g., HTTP 204), use `toBodilessEntity()` or `bodyToMono(Void.class)` as appropriate.

### 8.1. Default HTTP Errors and onStatus

By default, `retrieve()` converts 4xx and 5xx statuses into `WebClientResponseException` and its subtypes. Handle 404 with custom semantics using `onStatus`:

```java
Mono<Book> book = client.get()
        .uri("/books/{id}", 42)
        .retrieve()
        .onStatus(
                status -> status.value() == 404,
                response -> response.bodyToMono(String.class)
                        .defaultIfEmpty("")
                        .map(body -> new IllegalStateException(
                                "Book not found: " + body)))
        .bodyToMono(Book.class)
        .timeout(Duration.ofSeconds(3));
```

`Book` is an assumed declared DTO. `onStatus` handles a specific status; other errors still use default handling. `timeout` caps duration at the reactive layer; when needed, also configure connect/read timeouts on the HTTP connector.

When you need to decide by status and process the response at a lower level:

```java
Mono<String> result = client.get()
        .uri("/status")
        .exchangeToMono(response -> {
            if (response.statusCode().is2xxSuccessful()) {
                return response.bodyToMono(String.class);
            }
            return response.createException().flatMap(Mono::error);
        });
```

With `exchangeToMono`, you must consume or release the body in every branch so connection resources are not leaked. Do not use the lower-level API merely to read the body when `retrieve` already suffices.

### 8.2. Retries and Timeouts

Retrying re-subscribes to the pipeline and **can resend the HTTP request**. Retry only when the operation is considered safe/idempotent or the API supports an idempotency key, with bounded attempts and error classification. An order-creation POST should not be retried blindly. Client-side timeouts avoid waiting forever, though they do not guarantee the server did not already execute the action.

## 9. Common Mistakes

1. **Creating a Mono without a subscriber:** the request is never sent. In WebFlux, return the publisher; do not sprinkle `subscribe()` arbitrarily and swallow errors.
2. **Calling `block()` on the event loop:** breaks the non-blocking model, reduces throughput, or gets rejected by Reactor. `block` in the console demo is intentional, not a pattern for reactive controllers.
3. **Concatenating URIs from input strings:** prone to encoding bugs, missing `?`/`&`, or unintended host changes. Use URI templates/builders and validate targets.
4. **Confusing `Accept` with `Content-Type`:** the first describes the expected response, the second describes the request payload.
5. **Passing `Mono<Dto>` to `bodyValue`:** use `body(mono, Dto.class)` for publishers; `bodyValue(dto)` for a concrete DTO.
6. **Assuming WebClient automatically stores cookies from `Set-Cookie`:** an explicit management/forwarding mechanism is required.
7. **Putting per-user tokens or sessions in global default headers/cookies:** risks mixing data across users. Attach credentials per request.
8. **Ignoring HTTP status codes:** 4xx/5xx usually emit error signals rather than silently decoding into a success DTO.
9. **Retrying every POST error:** can create duplicate data. Enforce idempotency criteria and a finite retry count.
10. **Expecting `Flux` to always stream incrementally:** the media type and server must truly support streaming; a reactive client does not turn a single JSON response into an infinite event stream.
11. **Creating a new WebClient on every call:** scatters configuration and can waste connection resources.
12. **Logging sensitive bodies/headers:** passwords, access tokens, cookies, and private data must be masked in tracing and logs.

## 10. Self-Check

Before sending a request, review: Is the HTTP method right? Are URI path and query properly encoded? Is the host allowed? Are `Accept`/`Content-Type` correct? Do headers/cookies leak secrets? Is the body a DTO or a publisher? Does the server expect JSON, form, or multipart? Where is the pipeline subscribed to? How are 4xx/5xx, timeouts, and retries handled?

**Exercise A:** Given `baseUrl("https://api.example.com")`, write a GET `/books/12?lang=vi&page=1` with `Accept: application/json` and `X-Request-Id: learning-1`, returning `Mono<String>`. Use `uri(builder -> ...)`, `accept(...)`, `header(...)`, and `retrieve()`.

**Exercise B:** Write a POST `/books` sending record `BookCreate(String title, int quantity)` with `bodyValue`. When the input body becomes `Mono<BookCreate>`, switch to `body(mono, BookCreate.class)`. Explain why.

**Exercise C:** Run the local server example; try removing the `X-Request-Id` header or changing the cookie name and predict the error. Restore the request and verify the successful output.

## Official Documentation

- WebClient overview: https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html
- WebClient builder/configuration: https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-builder.html
- Request body, form, multipart: https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-body.html
- retrieve / response / onStatus: https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-retrieve.html
- URI building: https://docs.spring.io/spring-framework/reference/web/webflux/uri-building.html
