# HTTP Service Client: Configuring Headers, URIs, Data Conversion, and Error Handling

## 1. What Is an HTTP Service Client and Where Do Configuration Layers Live?

Spring Framework's HTTP Service Client lets you define HTTP call contracts using a **Java interface**, combining `@HttpExchange`, `@GetExchange`, `@PostExchange`, and parameter annotations. `HttpServiceProxyFactory` creates a proxy implementing the interface and delegates request sending/response reading to an actual HTTP client. This mechanism has existed since Spring Framework 6.0; `RestClientAdapter` has supported `RestClient` since Spring Framework 6.1. Examples in this lesson use **Java 17+, Spring Boot 3.3.x (Spring Framework 6.1.x)**.

```text
Business calling code
      │
      ▼
CatalogApi interface (@HttpExchange, @GetExchange, @PostExchange)
      │  method parameters → request path/query/header/body
      ▼
HttpServiceProxyFactory (creates proxy)
      │
      ▼
RestClientAdapter / WebClientAdapter
      │  baseUrl, defaultHeader, request factory/connector,
      │  converters/codecs, status handlers, timeout...
      ▼
HTTP request → server → HTTP response → Java object / exception
```

There are **two complementary configuration layers**:

- **On the interface and methods:** relative URLs, HTTP methods, `Accept`/`Content-Type`, paths, queries, per-call headers, body, and return data types. This is the readable, testable API contract.
- **On the underlying HTTP client:** base URL (host/service), default headers, authentication, message converters/codecs, timeouts/transport, and shared HTTP error rules. The proxy does not provide a separate set of codecs or transport independent of its attached adapter.

`RestClient` uses synchronous calls, suitable for interfaces returning `T`, `List<T>`, or `ResponseEntity<T>`. `WebClient` is a reactive client and can be used with interfaces returning `Mono<T>` or `Flux<T>`. Do not declare `Mono<T>` on an interface backed by `RestClientAdapter` expecting reactive execution.

## 2. Defining the Interface and Creating the Proxy

Product management contract example:

```java
import java.util.List;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.service.annotation.GetExchange;
import org.springframework.web.service.annotation.HttpExchange;
import org.springframework.web.service.annotation.PostExchange;

record Product(long id, String name, String category) {}
record CreateProduct(String name, String category) {}

@HttpExchange(url = "/api/products", accept = MediaType.APPLICATION_JSON_VALUE)
interface CatalogApi {

    @GetExchange("/{id}")
    Product findById(
        @PathVariable("id") long id,
        @RequestHeader("X-Request-Id") String requestId
    );

    @GetExchange("/search")
    List<Product> findByCategory(@RequestParam("category") String category);

    @PostExchange(contentType = MediaType.APPLICATION_JSON_VALUE)
    Product create(@RequestBody CreateProduct request);
}
```

This is **illustrative code** (no `main` included). `@HttpExchange` on the interface sets the shared URL and `Accept: application/json`. `@GetExchange`/`@PostExchange` define the HTTP method and remaining URL path. The `X-Request-Id` header is accepted per call. The `CreateProduct` body is encoded as JSON when a suitable converter exists, and the JSON response is decoded into `Product`.

Synchronous configuration using `RestClient`:

```java
import org.springframework.web.client.RestClient;
import org.springframework.web.client.support.RestClientAdapter;
import org.springframework.web.service.invoker.HttpServiceProxyFactory;

RestClient restClient = RestClient.builder()
    .baseUrl("https://catalog.example.com")
    .defaultHeader("X-Client-App", "java-learning")
    .build();

CatalogApi catalog = HttpServiceProxyFactory
    .builderFor(RestClientAdapter.create(restClient))
    .build()
    .createClient(CatalogApi.class);

Product item = catalog.findById(7, "req-007");
```

This is **illustrative code**; the URL must point to a real service. As of Spring Framework 6.1, `builderFor(RestClientAdapter.create(...))` is the appropriate API. In Spring Boot applications, register the proxy once as a bean and inject it into services instead of creating a factory per request.

Bean example:

```java
@Configuration
class CatalogClientConfiguration {

    @Bean
    CatalogApi catalogApi(RestClient.Builder builder) {
        RestClient client = builder
            .baseUrl("https://catalog.example.com")
            .defaultHeader("X-Client-App", "java-learning")
            .build();

        return HttpServiceProxyFactory
            .builderFor(RestClientAdapter.create(client))
            .build()
            .createClient(CatalogApi.class);
    }
}
```

The snippet above requires imports for `@Configuration`, `@Bean`, `RestClient`, `RestClientAdapter`, `HttpServiceProxyFactory`, and `CatalogApi`. When using the `RestClient.Builder` provided by Spring Boot, you can inherit customizers already configured in the application.

## 3. Headers: Default, Static per API, and Dynamic per Call

Headers control request metadata: content negotiation, body format, authentication, correlation IDs, locale, etc. Choose where to declare them by **scope of responsibility**:

| Header source | Example | When to use |
| --- | --- | --- |
| `RestClient.Builder.defaultHeader(name, value)` | `X-Client-App: java-learning` | Default values applied across methods on the same client |
| `WebClient.Builder.defaultHeader(name, value)` | `Accept-Language: vi` | Same, for WebClient |
| `@HttpExchange(accept=..., contentType=...)` | `Accept: application/json` | Specify media types in the HTTP interface contract |
| `@GetExchange(accept=...)` / `@PostExchange(contentType=...)` | `Content-Type: application/json` | Override media types per method when APIs differ |
| `@RequestHeader("X-Request-Id")` | Value from Java parameter | Header varying per call |
| `@RequestHeader HttpHeaders` or suitable map | Multiple dynamic headers | When header count/names vary per request |
| Underlying client interceptor/filter | Bearer token, trace propagation | Cross-cutting policy, especially when tokens refresh or vary per user |

Commonly misunderstood point: in Spring Framework 6.1, `@HttpExchange` **does not have a general `headers` attribute like `@RequestMapping`**. Use `accept`, `contentType`, `@RequestHeader`, or builder/filters on the underlying client. `defaultHeader` only adds a default value if that header is not already specified on the request; avoid relying on stacking duplicate header names without knowing how the client/server interprets them.

Dynamic header example:

```java
@GetExchange("/{id}")
Product findById(
    @PathVariable("id") long id,
    @RequestHeader("X-Request-Id") String requestId,
    @RequestHeader("Authorization") String authorization
);

// How to call:
Product p = catalog.findById(7, "req-007", "Bearer <access-token>");
```

This is a **signature-variant illustration**; to run it, update the `CatalogApi` interface and pass a valid token. Do not log sensitive access tokens/cookies and do not embed long-lived tokens in annotations or source code. If auth is a shared concern, an interceptor (`RestClient`) or filter (`WebClient`) is usually a better place.

**`Accept` differs from `Content-Type`:** `Accept` describes the media types the client wants to receive; `Content-Type` describes the type of the **outgoing** body. GET requests without a body typically do not need `Content-Type`. For JSON POSTs, both request `Content-Type: application/json` and response `Accept: application/json` are helpful. Wrong media types can cause HTTP 406/415 or content conversion failures.

## 4. URIs: Base URL, Path Variables, Queries, and Dynamic URIs

With a client having `baseUrl("https://catalog.example.com")`, these annotations:

```java
@HttpExchange(url = "/api/products")
interface CatalogApi {

    @GetExchange("/{id}")
    Product findById(@PathVariable("id") long id);

    @GetExchange("/search")
    List<Product> search(
        @RequestParam("category") String category,
        @RequestParam("page") int page
    );
}
```

produce corresponding URIs (for example):

```text
GET https://catalog.example.com/api/products/7
GET https://catalog.example.com/api/products/search?category=office&page=2
```

`@PathVariable` replaces placeholders in the URL template; `@RequestParam` adds query parameters for GET and typical HTTP scenarios. For `application/x-www-form-urlencoded` requests, `@RequestParam` can become corresponding form fields under the HTTP interface contract. `@PathVariable("id")`/`@RequestParam("page")` declare names explicitly, avoiding reliance on compiler-retained parameter-name metadata.

Dynamic options:

```java
import java.net.URI;

@GetExchange
Product loadFrom(URI absoluteUri);

@GetExchange("/search")
List<Product> searchWithBase(
    UriBuilderFactory uriBuilderFactory,
    @RequestParam("category") String category
);
```

These are **illustrative methods**, requiring the additional import `org.springframework.web.util.UriBuilderFactory`. A `URI` parameter can set a dynamic URL and replace the URL value from the method annotation. `UriBuilderFactory` provides a way to swap the base URI/factory while still using the relative path described by the annotation. Choose an absolute `URI` parameter only when a different endpoint is genuinely needed; **do not allow arbitrary externally supplied URLs** without a host/scheme allowlist and SSRF checks.

**Encoding:** use templates + variable resolvers instead of string concatenation:

```java
// Preferred:
@GetExchange("/customers/{customerId}")
Customer findCustomer(@PathVariable("customerId") String customerId);

// Avoid assembling URLs by concatenating unencoded input strings:
// "https://api.example.com/customers/" + untrustedCustomerId
```

For spaces, `&`, `?`, `/`, or Unicode characters, understand path/query placement and client URI encoding settings. In particular, `/` inside a path variable can alter path segments unless encoded per the intended policy. Do not manually call `URLEncoder.encode` on the entire URL because it is meant for form encoding and does not replace a URI builder. For queries with multiple values under one name, use collection parameters or a suitable resolver; verify the upstream's actual contract.

## 5. Request/Response Conversion: Java Objects, JSON, Collections

HTTP Service Client delegates conversion to the underlying client:

- `RestClient` uses Spring Web `HttpMessageConverter`s to write/read bodies. With Jackson on the classpath, `MappingJackson2HttpMessageConverter` typically handles JSON.
- `WebClient` uses `HttpMessageReader`/`HttpMessageWriter` and reactive codecs. WebClient's decoder/buffer settings apply to proxies using `WebClientAdapter`.
- `@RequestBody` only identifies the parameter as the request body; JSON serialization requires a suitable converter/codec, matching `Content-Type`, and a valid DTO.
- The method return type determines the object/collection to decode. JSON/schema errors can happen **even when the HTTP status is 200**.

Java 17 DTO example:

```java
public record CreateProduct(String name, String category) {}

public record Product(long id, String name, String category) {}
```

When calling:

```java
Product created = catalog.create(new CreateProduct("Pen", "office"));
```

The JSON converter sends a payload like:

```json
{"name":"Pen","category":"office"}
```

Suppose the server responds with:

```json
{"id":8,"name":"Pen","category":"office"}
```

then the `Product` return type is deserialized into `new Product(8, "Pen", "office")`. For a JSON list `[{"id":7,...}]`, return `List<Product>` so Spring preserves generic element type info; do not use raw `List` and manually cast `Map` entries to DTOs. When the response has no body (204), `void`/`ResponseEntity<Void>` can be used; forcing a required DTO from an empty body usually violates the endpoint contract.

Common return types:

| HTTP interface return type | Meaning | Appropriate adapter |
| --- | --- | --- |
| `Product`, `List<Product>` | Decode body | `RestClientAdapter` / `WebClientAdapter` |
| `ResponseEntity<Product>` | Keep status, headers, and body | Both |
| `ResponseEntity<Void>` | Get status/headers, no body needed | Both |
| `Mono<Product>` | Decode at most one item asynchronously | `WebClientAdapter` |
| `Flux<Product>` | Decode a stream of 0..N items | `WebClientAdapter` |
| `Mono<ResponseEntity<Flux<Product>>>` | Capture metadata and stream | `WebClientAdapter` |

Note: `ResponseEntity<Product>` does not mean 404 will automatically be returned normally; the client may throw a status error **before** building `ResponseEntity`. If business logic needs to keep 404 as a data result, configure an appropriate status policy and design clear DTOs/bodies.

### Customizing Conversion

`RestClient.Builder` has `messageConverters(...)` to add/modify converters. Only add converters when genuinely needed (vendor-specific formats, custom media types, ObjectMapper policies...). Ensure converter ordering does not unintentionally replace standard Jackson.

```java
RestClient custom = RestClient.builder()
    .baseUrl("https://catalog.example.com")
    .messageConverters(converters -> {
        // Add a custom converter here once the media type is clearly defined.
        // Do not remove default converters just to change one DTO.
    })
    .build();
```

With WebClient, customize via `WebClient.Builder.codecs(configurer -> ...)`. For example, increasing the decode buffer reasonably for large JSON payloads: `configurer.defaultCodecs().maxInMemorySize(1024 * 1024)`. This is a memory limit **per buffered decode operation**, not a cap on total memory across an entire stream or all downstream collections. Prefer pagination, streaming, or server-side payload limits over raising buffer limits indiscriminately.

### Common Conversion Errors

- `415 Unsupported Media Type`: the server rejects the request's `Content-Type`. Check the method, converter, and body.
- `406 Not Acceptable`: the server cannot produce content matching `Accept`; check API negotiation.
- HTTP 200 but invalid JSON body or DTO mismatch: may raise `RestClientException` wrapping a message conversion error, or `CodecException`/`DecodingException` with WebClient.
- Missing Jackson converter on classpath or missing configuration: JSON will not serialize/deserialize as expected.
- Very large JSON objects with WebClient: can throw `DataBufferLimitException` due to codec memory limits, distinct from server-returned HTTP 413.

## 6. HTTP Service Client Error Handling at the Underlying Client Layer

**The proxy has no `onStatus` method to chain after an interface method call.** Define error-handling policies on the `RestClient` / `WebClient` passed into `HttpServiceProxyFactory`. By default, both usually throw exceptions upon HTTP 4xx/5xx (`RestClientException` family for RestClient, typically `WebClientResponseException` for WebClient).

With `RestClient` (Spring Framework 6.1):

```java
RestClient restClient = RestClient.builder()
    .baseUrl("https://catalog.example.com")
    .defaultStatusHandler(
        status -> status.value() == 404,
        (request, response) -> {
            throw new ProductNotFoundException(
                "Product not found: HTTP " + response.getStatusCode().value()
            );
        }
    )
    .build();

CatalogApi catalog = HttpServiceProxyFactory
    .builderFor(RestClientAdapter.create(restClient))
    .build()
    .createClient(CatalogApi.class);
```

`ProductNotFoundException` is a business exception you define; this snippet is illustrative code. `defaultStatusHandler` lets you map 404 to a consistent exception across **every** proxy method using that client. Handlers are evaluated in registration order; place specific rules before broad 4xx/5xx rules. If no custom handler matches, default HTTP 4xx/5xx mapping still applies.

With reactive `WebClient`, the handler form differs:

```java
WebClient webClient = WebClient.builder()
    .baseUrl("https://catalog.example.com")
    .defaultStatusHandler(
        status -> status.value() == 404,
        response -> response.bodyToMono(String.class)
            .defaultIfEmpty("Not found")
            .map(message -> new ProductNotFoundException(message))
    )
    .build();

CatalogReactiveApi api = HttpServiceProxyFactory
    .builderFor(WebClientAdapter.create(webClient))
    .build()
    .createClient(CatalogReactiveApi.class);
```

This is also **illustrative code** (requires declaring `CatalogReactiveApi` with reactive returns and imports). `WebClient`'s callback returns a publisher emitting a `Throwable`; `RestClient`'s callback is synchronous handling, typically using `throw`. Do not mix the two APIs' handler styles.

### Four Error Categories to Keep Separate

1. **HTTP 4xx/5xx:** the upstream actually returned a response with status, headers, and sometimes an error body. Examples: business 404, 429 rate limit, upstream 500/503.
2. **Connection/timeout/TLS:** no HTTP response may have been received; handle with transport settings, bounded retries, and cause inspection. HTTP status predicates cannot catch these errors.
3. **Serialization/deserialization:** malformed JSON, DTO mismatch, missing converters/codecs, oversized payload. Even HTTP 200 can fail here.
4. **Post-decode business errors:** valid JSON object that violates domain requirements. Check after receiving the DTO; do not conflate with HTTP status errors.

For error responses carrying detailed JSON, the handler can read the body into an error DTO or String and build a business exception, but the response body is a single-consumption stream. Limit error content size and avoid logging tokens/sensitive fields. A **default** handler on the client applies to all proxies using that client; if two APIs have different error rules, configure separate clients/adapters or choose a more granular handler mechanism.

### Retries, Fallbacks, and HTTP Statuses

`onStatus` or `defaultStatusHandler` only decides which error is emitted; retry is a **separate** policy. Retrying can make sense for transient connection errors, 502/503, or 429 per API contract, but must have bounds, backoff, deadlines, and honor `Retry-After` when appropriate. Do not blindly retry side-effecting POSTs without an idempotency key. With synchronous proxies, use an external resilience layer (such as Spring Retry/Resilience4j per configuration); with reactive proxies, you can place `retryWhen(...)` on `Mono`/`Flux` with a clear error taxonomy.

## 7. Standalone Java 17+ Example: GET, Query, Header, JSON POST, and 404

This hands-on example uses `com.sun.net.httpserver.HttpServer` built into the JDK to run an HTTP server on localhost. Calls do not depend on the internet, though Gradle needs to download dependencies on the first run if uncached. The client uses **`RestClientAdapter`**; the Java code demonstrates all key topics: dynamic URL via server port, global + method headers, path variables, queries, JSON bodies via Jackson, record responses, and an HTTP 404 handler.

Project structure:

```text
http-service-client-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/HttpServiceClientDemo.java
```

**`settings.gradle`**

```groovy
rootProject.name = 'http-service-client-demo'
```

**`build.gradle`** (Gradle 8.x, JDK 17+)

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web:3.3.13'
}

application {
    mainClass = 'demo.HttpServiceClientDemo'
}
```

**`src/main/java/demo/HttpServiceClientDemo.java`**

```java
package demo;

import java.io.IOException;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.List;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.support.RestClientAdapter;
import org.springframework.web.service.annotation.GetExchange;
import org.springframework.web.service.annotation.HttpExchange;
import org.springframework.web.service.annotation.PostExchange;
import org.springframework.web.service.invoker.HttpServiceProxyFactory;

public class HttpServiceClientDemo {
    private static final ObjectMapper JSON = new ObjectMapper();

    public record Product(long id, String name, String category) {}
    public record CreateProduct(String name, String category) {}

    @HttpExchange(url = "/api/products", accept = MediaType.APPLICATION_JSON_VALUE)
    public interface CatalogApi {
        @GetExchange("/{id}")
        Product findById(
            @PathVariable("id") long id,
            @RequestHeader("X-Request-Id") String requestId
        );

        @GetExchange("/search")
        List<Product> search(@RequestParam("category") String category);

        @PostExchange(contentType = MediaType.APPLICATION_JSON_VALUE)
        Product create(@RequestBody CreateProduct request);
    }

    public static class ProductNotFoundException extends RuntimeException {
        public ProductNotFoundException(String message) {
            super(message);
        }
    }

    public static void main(String[] args) throws IOException {
        HttpServer server = HttpServer.create(
            new InetSocketAddress("127.0.0.1", 0), 0
        );
        server.createContext("/api/products", HttpServiceClientDemo::handle);
        server.start();

        try {
            RestClient underlyingClient = RestClient.builder()
                .baseUrl("http://127.0.0.1:" + server.getAddress().getPort())
                .defaultHeader("X-Client-App", "java-learning")
                .defaultStatusHandler(
                    status -> status.value() == 404,
                    (request, response) -> {
                        throw new ProductNotFoundException(
                            "HTTP " + response.getStatusCode().value()
                        );
                    }
                )
                .build();

            CatalogApi api = HttpServiceProxyFactory
                .builderFor(RestClientAdapter.create(underlyingClient))
                .build()
                .createClient(CatalogApi.class);

            Product item = api.findById(7, "request-007");
            System.out.println("GET: " + item);

            List<Product> results = api.search("office");
            System.out.println("SEARCH count: " + results.size());

            Product added = api.create(new CreateProduct("Pen", "office"));
            System.out.println("POST: " + added);

            try {
                api.findById(99, "request-099");
            } catch (ProductNotFoundException error) {
                System.out.println("ERROR: " + error.getMessage());
            }
        } finally {
            server.stop(0);
        }
    }

    private static void handle(HttpExchange request) throws IOException {
        String method = request.getRequestMethod();
        String path = request.getRequestURI().getPath();

        int status = 200;
        String response;

        if (!"java-learning".equals(
                request.getRequestHeaders().getFirst("X-Client-App"))) {
            status = 401;
            response = "{\"error\":\"missing app header\"}";
        } else if (method.equals("GET")
                && path.equals("/api/products/7")
                && "request-007".equals(
                    request.getRequestHeaders().getFirst("X-Request-Id"))) {
            response = "{\"id\":7,\"name\":\"Notebook\",\"category\":\"office\"}";
        } else if (method.equals("GET")
                && path.equals("/api/products/search")
                && "category=office".equals(request.getRequestURI().getRawQuery())) {
            response = "[{\"id\":7,\"name\":\"Notebook\",\"category\":\"office\"}]";
        } else if (method.equals("POST") && path.equals("/api/products")) {
            CreateProduct input = JSON.readValue(
                request.getRequestBody(), CreateProduct.class
            );

            if ("Pen".equals(input.name()) && "office".equals(input.category())) {
                response = "{\"id\":8,\"name\":\"Pen\",\"category\":\"office\"}";
            } else {
                status = 400;
                response = "{\"error\":\"invalid product\"}";
            }
        } else {
            status = 404;
            response = "{\"error\":\"not found\"}";
        }

        byte[] bytes = response.getBytes(StandardCharsets.UTF_8);
        request.getResponseHeaders().set("Content-Type", "application/json");
        request.sendResponseHeaders(status, bytes.length);
        try (OutputStream stream = request.getResponseBody()) {
            stream.write(bytes);
        }
    }
}
```

Run in the project directory (using installed Gradle; if a wrapper exists, replace `gradle` with `./gradlew` on Unix/macOS or `gradlew.bat` on Windows):

```bash
gradle run --quiet
```

**Expected output lines printed by the program:**

```text
GET: Product[id=7, name=Notebook, category=office]
SEARCH count: 1
POST: Product[id=8, name=Pen, category=office]
ERROR: HTTP 404
```

Execution flow explanation:

1. `HttpServer` binds an ephemeral port (`0`), and the client gets the dynamic base URL.
2. `findById(7, "request-007")` sends GET `/api/products/7` with global header `X-Client-App` and dynamic header `X-Request-Id`. The server validates both, then returns a JSON object converted into `Product`.
3. `search("office")` builds query `category=office`; the JSON array response is decoded into `List<Product>`.
4. `create(new CreateProduct(...))` sends a JSON POST body; the server reads it with Jackson into `CreateProduct` and returns the new `Product`.
5. `findById(99, ...)` receives 404; `RestClient.defaultStatusHandler` converts it into `ProductNotFoundException`. The caller catches it and prints `ERROR: HTTP 404`.

In this example, the server is local HTTP for learning purposes. In real environments, use HTTPS, proper credential/tracing policies, timeouts, and monitoring. The example focuses on the concepts being studied; it does not implement authentication, real pagination, or production retries.

## 8. Comparing RestClientAdapter and WebClientAdapter

| Criterion | `RestClientAdapter` | `WebClientAdapter` |
| --- | --- | --- |
| Execution foundation | Synchronous `RestClient` | Reactive/non-blocking `WebClient` |
| Typical return types | `Product`, `List<Product>`, `ResponseEntity<Product>` | `Mono<Product>`, `Flux<Product>`, `Mono<ResponseEntity<T>>` |
| Default headers | `RestClient.Builder.defaultHeader` | `WebClient.Builder.defaultHeader` |
| JSON conversion | Spring `HttpMessageConverter` | Spring reactive codecs |
| Handling HTTP 4xx/5xx | `RestClient.Builder.defaultStatusHandler` | `WebClient.Builder.defaultStatusHandler` |
| Transport configuration | Client request factory, HTTP engine | Client connector (usually Reactor Netty) |
| Best suited for | Sync/MVC apps, scripts, small APIs | WebFlux pipelines, streaming, high concurrent I/O |

Shared contract interfaces can be reused when return types are compatible; not every synchronous method returning objects should be carried verbatim into reactive flows. Name APIs clearly and avoid calling `block()` on the event loop just to reuse a synchronous signature.

Illustrative reactive configuration:

```java
import reactor.core.publisher.Mono;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.reactive.function.client.support.WebClientAdapter;

@HttpExchange(url = "/api/products", accept = "application/json")
interface ReactiveCatalogApi {
    @GetExchange("/{id}")
    Mono<Product> findById(@PathVariable("id") long id);
}

WebClient webClient = WebClient.builder()
    .baseUrl("https://catalog.example.com")
    .defaultHeader("X-Client-App", "java-learning")
    .build();

ReactiveCatalogApi api = HttpServiceProxyFactory
    .builderFor(WebClientAdapter.create(webClient))
    .build()
    .createClient(ReactiveCatalogApi.class);
```

This is an illustration (not a standalone Java file); it requires `spring-boot-starter-webflux`, imports for annotations/`Product`/`HttpServiceProxyFactory`, and a reactive environment.

## 9. Common Mistakes and How to Test

1. **Confusing controller annotations with HTTP interfaces.** `@GetMapping`/`@RequestMapping` are common for server controllers; in HTTP Service Client use `@GetExchange`/`@HttpExchange` so the proxy understands outbound requests.
2. **Setting headers via a `headers` attribute on `@HttpExchange`.** Spring 6.1 does not define that attribute. Use `accept`/`contentType`, `@RequestHeader`, or the builder.
3. **Misplacing dynamic headers:** fixing correlation ID or Authorization at startup even though they vary per request/user. Use method parameters, filters, or interceptors with the right scope.
4. **Building URLs by concatenating input strings.** Risks improper encoding and injection/SSRF. Use `@PathVariable`, `@RequestParam`, and URI builders; allow only valid hosts/schemes for dynamic URLs.
5. **Confusing `Accept` and `Content-Type`.** JSON GETs need to ask the server for JSON, whereas JSON POSTs need to describe the request body properly; wrong headers can cause 406/415.
6. **Assuming `@RequestBody` converts JSON without Jackson/converters.** Conversion depends on classpath dependencies and underlying client setup.
7. **Using raw `List` instead of `List<Product>`.** Loses element type information, often yielding `Map`s and cast failures.
8. **Assuming `ResponseEntity<T>` disables 404 exceptions.** Client status handlers may run first; handle errors according to the error contract.
9. **Calling `onStatus` directly on proxy methods.** Proxies return `Product` or `Mono<Product>`, not `ResponseSpec`; configure error handling on `RestClient.Builder`/`WebClient.Builder`.
10. **Retrying HTTP 400/401/403 or all POSTs.** Separate recoverable errors, protect idempotency, and bound retries.
11. **Swallowing error bodies or reading them multiple times.** Handlers should consume only the needed body once, bound size, and preserve important status/headers in exceptions.
12. **Testing one HTTP 200 mock and assuming production behaves identically.** Write dedicated integration tests for path encoding, headers, 4xx/5xx, network failures, media types, codec limits, and schema drift.

To test the client, you can use `MockRestServiceServer` (with RestClient) or a mock HTTP server like WireMock/MockWebServer; verify HTTP method, URI, headers, body, and error mapping. Contract tests should target **actual HTTP behavior** (requests/responses) rather than merely mocking the interface implementation.

## 10. Self-Check

1. **Why is declaring `@RequestHeader("Authorization") String token` better than hardcoding a bearer token on the interface?** Because tokens can vary per user/request and must be protected and refreshed.
2. **When calling `search("office")`, where does `category` go?** For normal GETs, `@RequestParam` puts it in the query string; `@PathVariable` fills a placeholder in the path.
3. **If returning `List<Product>` and HTTP 200 returns a JSON object, what happens?** The decoder may fail due to body shape mismatch; a successful HTTP status does not guarantee successful Java conversion.
4. **To map 404 to `ProductNotFoundException` across all `RestClient` proxy methods, where is it configured?** On `RestClient.Builder.defaultStatusHandler` before creating the `RestClientAdapter`/proxy.
5. **If a method needs a streaming response, which interface/adapter type should be chosen?** Use `WebClientAdapter` with return type `Flux<T>` and an upstream/codec supporting streaming; synchronous `List<T>` does not become streaming just by changing the type name.
6. **If upstream returns error JSON containing a domain code, how should it be handled?** Read the error body exactly once in the status handler, decode a bounded schema, and raise a context-rich exception separated from connection/codec errors.

## 11. References

- Spring Framework Reference — REST Clients and HTTP Service Clients: https://docs.spring.io/spring-framework/reference/integration/rest-clients.html
- Spring Framework 6.1 Javadoc — `@HttpExchange` (method arguments, URL, media types): https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/service/annotation/HttpExchange.html
- Spring Framework 6.1 Javadoc — `HttpServiceProxyFactory`: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/service/invoker/HttpServiceProxyFactory.html
- Spring Framework 6.1 Javadoc — `RestClient.Builder`: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/client/RestClient.Builder.html
- Spring Framework Reference — URI links and encoding: https://docs.spring.io/spring-framework/reference/web/webflux/uri-building.html
