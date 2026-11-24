# Integrating HTTP Service Interfaces with `@HttpExchange` and `WebClientAdapter` in Spring WebFlux

> **Module:** Spring Framework – reactive · **Parent topic:** Sending WebClient Requests. This lesson builds an HTTP client around an interface contract: declaring endpoints with `@HttpExchange`, `@GetExchange`, `@PostExchange`, then creating a proxy that executes requests via `WebClientAdapter`. We progress from method/parameter mapping, reactive return types, and WebClient configuration to error handling, timeouts, security, HTTP tests, and choosing between interface proxies and the WebClient fluent API.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain what an HTTP Service Client is and how proxies created by `HttpServiceProxyFactory` work.
2. Distinguish the roles of `@HttpExchange`, method annotations such as `@GetExchange`, and `WebClientAdapter`.
3. Declare an HTTP API contract as a Java interface, including path, query, header, body, cookie, and multipart.
4. Choose the right return type: `Mono<T>`, `Flux<T>`, `Mono<Void>`, or `Mono<ResponseEntity<T>>`.
5. Configure `WebClient`, base URL, codecs, filters, authentication, timeouts, and error handlers before creating the proxy.
6. Register the proxy as a Spring bean and inject it into services/controllers.
7. Test real requests with a mock HTTP server, verifying method, URL, headers, body, status, and response.
8. Know when an interface proxy makes code clearer and when to call `WebClient` directly.

**Key idea:** `@HttpExchange` describes the HTTP contract as an interface; `HttpServiceProxyFactory` creates an implementation for the interface; `WebClientAdapter` connects the proxy to a configured `WebClient`. The interface makes calling the service feel like calling a Java dependency, while network connections, codecs, filters, and the reactive lifecycle remain WebClient's responsibility.

## 2. Where Does HTTP Service Client Sit in the Architecture?

When using WebClient directly, each service call usually has to describe the method, URI, headers, body, and how to decode the response:

~~~java
Mono<CatalogItem> item = webClient.get()
    .uri("/api/catalog/{id}", id)
    .header("X-Request-Id", requestId)
    .retrieve()
    .bodyToMono(CatalogItem.class);
~~~

HTTP Service Client turns that endpoint description into an interface:

~~~java
public interface CatalogHttpService {

    @GetExchange("/api/catalog/{id}")
    Mono<CatalogItem> getById(
        @PathVariable("id") String id,
        @RequestHeader("X-Request-Id") String requestId);
}
~~~

Once the proxy is created, code calls:

~~~java
Mono<CatalogItem> item =
    catalogHttpService.getById(id, requestId);
~~~

The proxy reads annotations and method arguments, constructs request values, passes them through the adapter to WebClient, and returns the reactive result to the caller.

~~~text
Business service / controller
            |
            v
    CatalogHttpService
       Java interface
            |
            v
   HttpServiceProxyFactory
     reads annotations + args
            |
            v
      WebClientAdapter
            |
            v
         WebClient
   filters / codecs / connector
            |
            v
        HTTP network
            |
            v
    Remote HTTP service
            |
            v
      response decoding
            |
            v
       Mono / Flux / entity
~~~

Each component has a distinct role:

| Component | Role |
| --- | --- |
| `@HttpExchange` | Declares shared attributes for methods in the interface, such as base path, default Accept, and Content-Type. |
| `@GetExchange`, `@PostExchange`, `@PutExchange`, `@PatchExchange`, `@DeleteExchange` | Declares the HTTP method and path of each operation. |
| `@PathVariable`, `@RequestParam`, `@RequestHeader`, `@RequestBody` | Maps method arguments to URL, query, headers, and request body. |
| `HttpServiceProxyFactory` | Reads the interface contract and creates the client proxy. |
| `WebClientAdapter` | Implements `ReactorHttpExchangeAdapter`, bridging proxy invocations to WebClient. |
| `WebClient` | Performs HTTP I/O, encodes/decodes bodies, and manages connectors, filters, and reactive responses. |

HTTP Service Client is a declarative API layer over WebClient. It does not create an HTTP server, implement the remote service itself, or replace the WebClient connector.

## 3. When Should You Use an Interface Proxy?

An interface proxy is appropriate when an application calls an API with a stable contract used across multiple places:

- Multiple services call the same Catalog, Billing, or Identity API.
- You want endpoint paths, headers, request/response DTOs, and method documentation centralized in one place.
- You want to mock the dependency in unit tests via an interface.
- You want to swap client execution while keeping the caller's Java API unchanged.
- You want to separate clients by downstream host or bounded context.

The WebClient fluent API remains appropriate when requests have complex dynamic logic, responses require manual branching by status/headers, or there is only a one-off request not worth creating a dedicated interface for.

| Criterion | HTTP Service interface | Direct WebClient |
| --- | --- | --- |
| Endpoint declaration | Annotations on methods | Fluent chain at call site |
| Contract reuse | Good; many callers share the interface | Requires extracting helper/client classes manually |
| URI/path/header/body | Mapped via method arguments | Declared directly in the chain |
| Reactive | `Mono`, `Flux`, and reactive adapter types | `Mono`, `Flux`, and Publisher |
| Filters, codecs, TLS, pool | Configured on the underlying WebClient | Configured directly on WebClient |
| Advanced response handling | May require a custom adapter decorator or dedicated WebClient method | Full control with `exchangeToMono`/`exchangeToFlux` |
| Testing callers | Easy to mock interface | Usually mock WebClient chain or test with mock server |
| Best suited for | Stable, widely reused contracts | Specialized requests, flexible HTTP logic |

You do not need to turn every request into an interface. Create an HTTP service interface when it represents a named dependency with a meaningful domain contract.

## 4. Declaring an Interface with `@HttpExchange`

`@HttpExchange` is placed at the type level to define shared attributes. Specific method annotations determine the HTTP verb and path.

~~~java
@HttpExchange(
    url = "/api/catalog",
    accept = MediaType.APPLICATION_JSON_VALUE
)
public interface CatalogHttpService {

    @GetExchange("/{id}")
    Mono<CatalogItem> getById(
        @PathVariable("id") String id);

    @PostExchange(
        contentType = MediaType.APPLICATION_JSON_VALUE)
    Mono<CatalogItem> create(
        @RequestBody CreateCatalogItem request);

    @DeleteExchange("/{id}")
    Mono<Void> delete(
        @PathVariable("id") String id);
}
~~~

In this example:
- `url="/api/catalog"` is the shared prefix.
- `accept` sets the `Accept: application/json` header.
- `@GetExchange("/{id}")` produces a GET to `/api/catalog/{id}`.
- `@PostExchange` produces a POST to `/api/catalog`.
- `contentType` declares `Content-Type: application/json`.
- `@RequestBody` instructs WebClient to serialize the DTO into the body.
- `Mono` keeps the request/response reactive.

You can declare the full URL on each method if the interface only has a few distinct endpoints. Use a type-level prefix when operations belong to the same resource/API.

### 4.1. HTTP Method Annotations

| Annotation | HTTP method | Example |
| --- | --- | --- |
| `@HttpExchange(method = "GET")` | GET | Custom method with the general annotation |
| `@GetExchange` | GET | Read a resource |
| `@PostExchange` | POST | Create a resource or execute a command |
| `@PutExchange` | PUT | Replace a resource |
| `@PatchExchange` | PATCH | Partial update |
| `@DeleteExchange` | DELETE | Delete a resource |

`@GetExchange`, `@PostExchange`, `@PutExchange`, `@PatchExchange`, and `@DeleteExchange` are shortcuts for `@HttpExchange` with the corresponding HTTP method. Do not declare two methods with conflicting annotations/paths for the same contract; keep each method representing a specific operation.

### 4.2. Attributes of `@HttpExchange`

Commonly used attributes:

- `url`: URL or URI template; a prefix can be set at the type level.
- `method`: HTTP method, especially when using `@HttpExchange` directly.
- `contentType`: request content type.
- `accept`: desired response type.
- `headers`: static headers in `name=value` format.

Method-level mappings identify the specific endpoint; type-level annotations share base paths and media types. If headers must change per request, use `@RequestHeader` or a WebClient filter rather than hardcoding dynamic values in annotations.

## 5. Mapping Method Arguments to HTTP Requests

HTTP Service Client supports parameters annotated with Spring Web annotations. These parameters are analyzed when creating the proxy and converted into request values when methods are invoked.

### 5.1. Path Variable

~~~java
@GetExchange("/orders/{orderId}")
Mono<Order> getOrder(
    @PathVariable("orderId") String orderId);
~~~

With `orderId="A-100"`, the proxy expands the URI template to `/orders/A-100`. Explicitly specify the name in `@PathVariable("orderId")` so you do not rely on compiler parameter-name metadata.

You can use a `Map<String, ?>` to supply multiple path variables when the contract genuinely requires it:

~~~java
@GetExchange("/customers/{customerId}/orders/{orderId}")
Mono<Order> getOrder(
    @PathVariable Map<String, ?> pathVariables);
~~~

### 5.2. Query Parameter

~~~java
@GetExchange("/orders")
Flux<Order> findOrders(
    @RequestParam("status") String status,
    @RequestParam("page") int page,
    @RequestParam("size") int size);
~~~

Calling `findOrders("PAID", 0, 20)` produces the corresponding query string:

~~~http
GET /orders?status=PAID&page=0&size=20
~~~

`@RequestParam` also supports collections, maps, and `MultiValueMap` for multi-value query parameters. Non-String values are converted to text form.

When `Content-Type` is `application/x-www-form-urlencoded`, `@RequestParam` is encoded into the form body instead of the query string. Therefore, declare `contentType` properly at the method or type level.

### 5.3. Request Header

~~~java
@GetExchange("/orders/{id}")
Mono<Order> getOrder(
    @PathVariable("id") String id,
    @RequestHeader("X-Request-Id") String requestId);
~~~

A header can be a single value, collection, map, or `MultiValueMap`. Use header parameters for data that varies per method call such as request ID, tenant key, or locale.

Fixed headers for all requests should be configured on WebClient:

~~~java
WebClient webClient = builder
    .defaultHeader("X-Client-Name", "order-service")
    .build();
~~~

### 5.4. Request Body

~~~java
@PostExchange(
    url = "/orders",
    contentType = MediaType.APPLICATION_JSON_VALUE)
Mono<Order> create(@RequestBody CreateOrder request);
~~~

`@RequestBody` can accept an object for codecs to serialize or a reactive Publisher such as `Mono<T>`/`Flux<T>`:

~~~java
@PostExchange(
    url = "/orders/bulk",
    contentType = MediaType.APPLICATION_NDJSON_VALUE)
Mono<Void> importOrders(
    @RequestBody Flux<CreateOrder> orders);
~~~

Publisher request bodies enable streaming data while preserving backpressure. Do not `collectList()` a large stream just to send HTTP; pass the Publisher directly if the remote API accepts the corresponding framing.

### 5.5. Cookie and Multipart

Cookie:

~~~java
@GetExchange("/profile")
Mono<Profile> profile(
    @CookieValue("SESSION") String sessionId);
~~~

Multipart:

~~~java
@PostExchange(
    url = "/documents",
    contentType = MediaType.MULTIPART_FORM_DATA_VALUE)
Mono<DocumentReceipt> upload(
    @RequestPart("description") String description,
    @RequestPart("file") Resource file);
~~~

`@RequestPart` supports String, Resource, objects encoded into parts, `HttpEntity`, Spring `Part`, and reactive Publishers of appropriate part types. For large files, use Resource/Publisher and configure bounded streaming uploads; avoid reading entire files into `byte[]` unnecessarily.

`@CookieValue` on an HTTP service interface means adding a cookie to the outbound request. It is not the server controller API for reading cookies from an inbound request.

### 5.6. Dynamic URI and HTTP Method

A method can accept a `URI` to override the URL declared in the annotation:

~~~java
@GetExchange("/orders/{id}")
Mono<Order> getOrder(
    URI uri);
~~~

Or accept an `HttpMethod` to override the annotation's HTTP method:

~~~java
@HttpExchange("/resource")
Mono<String> exchange(
    HttpMethod method,
    @RequestBody(required = false) String body);
~~~

This is an advanced option. If dynamic URLs/methods make the interface contract hard to read, separate methods or direct WebClient calls are clearer.

### 5.7. Request Attributes and Custom Argument Resolvers

`@RequestAttribute` provides internal request attributes to the client adapter; it is only supported by certain adapters such as `RestClient` and `WebClient`, and is not an HTTP header sent to the remote server.

If your domain has custom parameter types, you can implement `HttpServiceArgumentResolver` and register it via `HttpServiceProxyFactory.Builder.customArgumentResolver(...)`. The resolver translates that object into path/query/header/body values. Only add resolvers when multiple interfaces genuinely share a convention; for a single endpoint, standard annotations are easier to understand.

Method parameters must not be passed `null` unless the annotation supports `required=false` or the parameter type is explicitly optional. Declare optionality clearly and verify how it is encoded into requests.

## 6. Choosing a Reactive Return Type

Because `WebClientAdapter` is a `ReactorHttpExchangeAdapter`, HTTP Service Client can use synchronous or reactive return types. In WebFlux applications, prefer `Mono` and `Flux` so the event loop is not blocked.

| Return type | Meaning |
| --- | --- |
| `Mono<T>` | A single response body object or no value |
| `Flux<T>` | Stream of elements in the response body |
| `Mono<Void>` | Executes request, consumes/releases response body if any, and signals completion only |
| `Mono<HttpHeaders>` | Returns response headers after the body is released |
| `Mono<ResponseEntity<Void>>` | Returns status and headers, without retaining body |
| `Mono<ResponseEntity<T>>` | Returns status, headers, and decoded body |
| `Mono<ResponseEntity<Flux<T>>>` | Returns status/headers first while keeping the body as a stream for the caller to consume |
| `HttpHeaders`, `T`, `ResponseEntity<T>` | Synchronous types; the adapter may have to wait/block to return the result |

### 6.1. Mono for a Single Response

~~~java
@GetExchange("/{id}")
Mono<CatalogItem> getById(
    @PathVariable("id") String id);
~~~

Use when the endpoint returns a single resource. If the remote server returns 404 or 500, WebClient emits an exception by default; `Mono` will terminate with an error signal rather than emitting an empty object.

### 6.2. Flux for Multi-Element Responses

~~~java
@GetExchange
Flux<CatalogItem> findAll(
    @RequestParam("category") String category);
~~~

Use when the body is a JSON list or codec-compatible stream. `Flux<T>` decodes elements on demand, allowing callers to process items individually while preserving backpressure. If the caller calls `collectList()`, data is collected into memory; only do so when result size is appropriately bounded.

### 6.3. ResponseEntity When Status and Headers Are Needed

~~~java
@PostExchange
Mono<ResponseEntity<CatalogItem>> create(
    @RequestBody CreateCatalogItem request);
~~~

`ResponseEntity` is useful when you need to read `Location`, `ETag`, rate limit headers, or status codes. With `Mono<ResponseEntity<T>>`, the body is decoded before the entity is emitted.

### 6.4. ResponseEntity with a Streaming Body

~~~java
@GetExchange(value = "/events",
             accept = MediaType.TEXT_EVENT_STREAM_VALUE)
Mono<ResponseEntity<Flux<ServerSentEvent<CatalogEvent>>>> events();
~~~

The outer `Mono` receives status and headers; the inner `Flux` continues reading the stream. The caller must subscribe/consume the body to release the response and connection. If you only need the body stream, `Flux<T>` is usually simpler.

### 6.5. Why Avoid Synchronous Types in Reactive Flows?

The WebClient adapter supports synchronous return types, but the caller has to wait for the result to obtain the object. Calling synchronous methods on the event loop or inside a reactive chain can block threads and reduce throughput.

Do not write:

~~~java
CatalogItem item = catalogClient.getByIdBlocking("42");
return Mono.just(item);
~~~

Prefer:

~~~java
return catalogClient.getById("42")
    .map(this::toView);
~~~

`block()` is appropriate in tests, command-line boundaries, or explicitly designed synchronous code; do not use it in WebFlux controllers/services handling requests.

## 7. Creating WebClientAdapter and HttpServiceProxyFactory

This step connects the interface to a configured WebClient.

~~~java
WebClient webClient = WebClient.builder()
    .baseUrl("https://catalog.example.test")
    .defaultHeader(
        HttpHeaders.ACCEPT,
        MediaType.APPLICATION_JSON_VALUE)
    .build();

WebClientAdapter adapter = WebClientAdapter.create(webClient);

HttpServiceProxyFactory factory =
    HttpServiceProxyFactory.builderFor(adapter).build();

CatalogHttpService catalogClient =
    factory.createClient(CatalogHttpService.class);
~~~

Steps:

1. Create `WebClient` with the base URL and required settings.
2. Call `WebClientAdapter.create(webClient)` to create the reactive adapter.
3. Create `HttpServiceProxyFactory` via `builderFor(adapter)`.
4. Call `createClient(CatalogHttpService.class)` to obtain the proxy implementing the interface.
5. Inject the proxy into components that need to call the remote API.

`HttpServiceProxyFactory` reads annotations and generates a runtime implementation for the interface. Do not manually write classes implementing every method, and do not create a new proxy per HTTP request.

### 7.1. Bean Lifecycle

In a Spring application, create the proxy once as a singleton bean:

~~~java
@Configuration(proxyBeanMethods = false)
class CatalogClientConfiguration {

    @Bean
    CatalogHttpService catalogHttpService(
            WebClient.Builder builder,
            @Value("${catalog.base-url}") String baseUrl) {

        WebClient webClient = builder
            .baseUrl(baseUrl)
            .build();

        WebClientAdapter adapter =
            WebClientAdapter.create(webClient);

        HttpServiceProxyFactory factory =
            HttpServiceProxyFactory.builderFor(adapter).build();

        return factory.createClient(CatalogHttpService.class);
    }
}
~~~

`WebClient.Builder` auto-configured by Spring Boot can be injected and customized before building. A built WebClient can be reused across many requests; the builder is a configuration object and should not be arbitrarily mutated after being used to build a client.

Configure the base URL via properties:

~~~properties
catalog.base-url=https://catalog.example.test
~~~

Do not hardcode production hosts inside the interface. The same interface can target local, test, staging, or production by changing properties and client configuration.

### 7.2. Injecting into Services

~~~java
@Service
public class CatalogService {

    private final CatalogHttpService catalogClient;

    public CatalogService(CatalogHttpService catalogClient) {
        this.catalogClient = catalogClient;
    }

    public Mono<CatalogView> getCatalogItem(
            String id, String requestId) {

        return catalogClient.getById(id, requestId)
            .map(item ->
                new CatalogView(item.id(), item.name()));
    }
}
~~~

The business service depends only on the interface. It does not need to know where WebClient, the adapter, or the factory are configured. When testing the business service, `CatalogHttpService` can be mocked directly.

## 8. Customizing WebClient Before Creating the Proxy

The interface describes the endpoint contract; WebClient controls how requests are executed. Filters and connector settings apply to every proxy method sharing that client.

### 8.1. Default Headers and Codecs

~~~java
WebClient webClient = builder
    .baseUrl(baseUrl)
    .defaultHeader("X-Client-Name", "checkout-service")
    .codecs(codecs ->
        codecs.defaultCodecs().maxInMemorySize(2 * 1024 * 1024))
    .build();
~~~

Default headers suit client identity or shared Accept headers. Codec configuration suits APIs returning large payloads or needing custom serializers. Buffer limits must match actual responses; do not raise them unbounded just to avoid `DataBufferLimitException`.

### 8.2. ExchangeFilterFunction

Use filters for cross-cutting request behavior, such as correlation IDs, metrics, tracing, or authentication:

~~~java
ExchangeFilterFunction requestIdFilter =
    (request, next) -> {
        ClientRequest updated = ClientRequest.from(request)
            .header("X-Client-Name", "checkout-service")
            .build();

        return next.exchange(updated);
    };

WebClient webClient = builder
    .baseUrl(baseUrl)
    .filter(requestIdFilter)
    .build();
~~~

Filters can read Reactor Context when request metadata must flow per subscription. Do not log full request headers or bodies in filters; they can contain Authorization, cookies, and PII. Only log allowlisted fields.

### 8.3. Authentication and OAuth2

You can attach an authentication filter to WebClient so tokens are issued/refreshed according to policy. For OAuth2, prefer Spring Security reactive authorized client integration rather than manually assembling tokens in every interface method.

The interface only needs to describe the API request:

~~~java
@GetExchange("/me")
Mono<UserProfile> currentUser();
~~~

Tokens are added in the WebClient filter/authorized client manager. This keeps the credential lifecycle inside controlled client configuration rather than repeating it on every method.

### 8.4. Timeouts, Connection Pool, and TLS

Timeouts are not attributes of `@HttpExchange`. Configure them on the HTTP connector/WebClient:
- Connect timeout limits the time to establish TCP/TLS connections.
- Response/read timeout limits the time waiting for data per client policy.
- `Mono.timeout(...)` can bound the duration of an operation at the reactive chain level.
- Connection pools limit concurrent connections and connection retention time.
- TLS trust, client certificates, and proxies are configured on the connector.

Do not use a single timeout for all APIs if latency profiles differ. A fast search request, a large file upload, and an SSE stream have different timeout requirements.

## 9. Handling HTTP Errors from Remote Services

By default, WebClient treats 4xx and 5xx statuses as errors and emits `WebClientResponseException`. Because HTTP Service Client runs through WebClientAdapter, the underlying WebClient's default status behavior still applies.

Example:

~~~java
catalogClient.getById("missing", "req-404")
    .onErrorResume(
        WebClientResponseException.NotFound.class,
        error -> Mono.empty());
~~~

Do not turn every error into `Mono.empty()`. Distinguish:
- 404 may mean a resource does not exist per business semantics.
- 400 usually indicates an invalid client request.
- 401/403 are authentication or authorization issues.
- 429 may be retried after the server-specified interval.
- 5xx and connection errors may be transient failures or dependency outages.

### 9.1. Preserving Status and Headers When Needed

Use `Mono<ResponseEntity<T>>` when status and headers are needed:

~~~java
catalogClient.create(request)
    .flatMap(response -> {
        URI location = response.getHeaders().getLocation();
        CatalogItem item = response.getBody();

        return saveRemoteReference(location, item);
    });
~~~

By default, 4xx/5xx may be converted into exceptions before the method returns `ResponseEntity`. If 404 is a normal outcome that needs to be preserved as a `ResponseEntity` with a null body, you can configure custom status handling or use Spring's `NotFoundWebClientAdapterDecorator` for the WebClient adapter.

### 9.2. Customizing Status Handlers

The WebClient builder can register a default status handler for all calls through the client:

~~~java
WebClient webClient = builder
    .baseUrl(baseUrl)
    .defaultStatusHandler(
        HttpStatusCode::isError,
        response -> response.createException())
    .build();
~~~

The example above shows where to configure it; it retains WebClient's default exception behavior. In real applications, you can decode a stable error DTO and map it to a custom domain exception. If the error body does not follow the contract or decoding fails, provide a fallback and avoid exposing sensitive remote service internals.

### 9.3. Selective Retries

Do not retry every exception automatically. Retry:
- Transient errors such as connection resets or 503 if policy permits.
- Only idempotent operations, or POSTs with an idempotency key.
- With bounded attempt counts and backoff.
- With an overall timeout so requests do not drag on indefinitely.
- Preserving the same request/correlation ID across retry attempts.

Example of a GET that may retry transient failures:

~~~java
catalogClient.getById("42", requestId)
    .retryWhen(
        Retry.backoff(2, Duration.ofMillis(200))
            .filter(this::isTransient));
~~~

`isTransient` is an application-defined policy based on actual exceptions/statuses. Do not blindly retry 400, 401, or 403; retrying resource-creating POSTs without idempotency protection can create duplicate data.

## 10. Testing HTTP Service Client

Two layers of testing are valuable:

1. **Caller unit tests:** mock the interface proxy to confirm the business service handles results and errors properly.
2. **HTTP client integration tests:** use a mock HTTP server to confirm annotations actually produce the expected method, path, query, headers, body, and response decoding.

Mocking the interface does not prove annotation mappings are correct. For clients used in production, maintain at least one HTTP contract test suite.

### 10.1. MockWebServer

OkHttp's `MockWebServer` starts a local HTTP server, receives real requests, and lets tests enqueue responses. It lets you test `WebClientAdapter` without calling the Internet or depending on external services.

Tests should verify:
- Exact method and path.
- Properly encoded query parameters.
- Sent request headers.
- Serialized request DTOs.
- Decoded response JSON.
- Status 201 and `Location` preserved in `ResponseEntity`.
- 4xx/5xx emitting errors as configured.

## 11. Complete Example: Spring Boot 4.0.9 and Java 17+

The following project can run standalone. The application creates a `CatalogHttpService` proxy; tests start MockWebServer and point the `catalog.base-url` property to the local server.

### 11.1. Directory Structure

~~~text
http-service-client/
├── pom.xml
├── src/main/resources/application.properties
├── src/main/java/com/example/catalog/
│   ├── CatalogClientApplication.java
│   ├── CatalogItem.java
│   ├── CreateCatalogItem.java
│   ├── CatalogHttpService.java
│   └── CatalogClientConfiguration.java
└── src/test/java/com/example/catalog/
    └── CatalogHttpServiceTest.java
~~~

### 11.2. pom.xml

Spring Boot 4.0.9 and Java 17+ are used for the example. MockWebServer is only in test scope.

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
    <artifactId>http-service-client</artifactId>
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

        <dependency>
            <groupId>com.squareup.okhttp3</groupId>
            <artifactId>mockwebserver</artifactId>
            <version>4.12.0</version>
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

### 11.3. application.properties

~~~properties
catalog.base-url=https://catalog.example.test
~~~

In production, configure the base URL via environment variables or secret/config management. Tests override the property with the URL provided by MockWebServer.

### 11.4. CatalogClientApplication.java

~~~java
package com.example.catalog;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CatalogClientApplication {

    public static void main(String[] args) {
        SpringApplication.run(CatalogClientApplication.class, args);
    }
}
~~~

### 11.5. DTOs

`CatalogItem.java`:

~~~java
package com.example.catalog;

public record CatalogItem(
    String id,
    String name,
    String category
) {}
~~~

`CreateCatalogItem.java`:

~~~java
package com.example.catalog;

public record CreateCatalogItem(
    String name,
    String category
) {}
~~~

DTOs form the data contract understood by the client. If the remote API changes fields or data types, use versioning/compatibility tests instead of letting silent changes break callers.

### 11.6. CatalogHttpService.java

~~~java
package com.example.catalog;

import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.service.annotation.DeleteExchange;
import org.springframework.web.service.annotation.GetExchange;
import org.springframework.web.service.annotation.HttpExchange;
import org.springframework.web.service.annotation.PostExchange;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@HttpExchange(
    url = "/api/catalog",
    accept = MediaType.APPLICATION_JSON_VALUE
)
public interface CatalogHttpService {

    @GetExchange("/{id}")
    Mono<CatalogItem> getById(
        @PathVariable("id") String id,
        @RequestHeader("X-Request-Id") String requestId);

    @GetExchange
    Flux<CatalogItem> findByCategory(
        @RequestParam("category") String category);

    @PostExchange(
        contentType = MediaType.APPLICATION_JSON_VALUE)
    Mono<ResponseEntity<CatalogItem>> create(
        @RequestBody CreateCatalogItem request);

    @DeleteExchange("/{id}")
    Mono<Void> delete(
        @PathVariable("id") String id);
}
~~~

The interface describes four operations:
- GET an item by ID and send a request ID.
- GET a list by category using a query parameter.
- POST an item and receive status/headers/body.
- DELETE an item, caring only about request completion.

Callers do not need to know full paths or how JSON is decoded; everything is centralized in the contract.

### 11.7. CatalogClientConfiguration.java

~~~java
package com.example.catalog;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.reactive.function.client.support.WebClientAdapter;
import org.springframework.web.service.invoker.HttpServiceProxyFactory;

@Configuration(proxyBeanMethods = false)
public class CatalogClientConfiguration {

    @Bean
    CatalogHttpService catalogHttpService(
            WebClient.Builder builder,
            @Value("${catalog.base-url}") String baseUrl) {

        WebClient webClient = builder
            .baseUrl(baseUrl)
            .build();

        WebClientAdapter adapter =
            WebClientAdapter.create(webClient);

        HttpServiceProxyFactory factory =
            HttpServiceProxyFactory.builderFor(adapter).build();

        return factory.createClient(CatalogHttpService.class);
    }
}
~~~

This is the core integration:
- WebClient Builder receives the base URL from properties.
- The adapter bridges WebClient with the HTTP service infrastructure.
- The factory builds the proxy for the interface.
- Spring manages the proxy as a bean for other services to inject.

Do not create a factory inside every method call. A single proxy bean can serve many concurrent requests; connection pooling and reactive execution belong to the underlying WebClient.

### 11.8. CatalogHttpServiceTest.java

~~~java
package com.example.catalog;

import java.io.IOException;
import java.net.URI;
import java.time.Duration;
import java.util.concurrent.TimeUnit;

import okhttp3.mockwebserver.MockResponse;
import okhttp3.mockwebserver.MockWebServer;
import okhttp3.mockwebserver.RecordedRequest;

import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.web.reactive.function.client.WebClientResponseException;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.NONE)
class CatalogHttpServiceTest {

    private static final MockWebServer SERVER = startServer();

    @Autowired
    CatalogHttpService catalog;

    private static MockWebServer startServer() {
        MockWebServer server = new MockWebServer();
        try {
            server.start();
            return server;
        }
        catch (IOException error) {
            throw new ExceptionInInitializerError(error);
        }
    }

    @DynamicPropertySource
    static void properties(DynamicPropertyRegistry registry) {
        registry.add(
            "catalog.base-url",
            () -> SERVER.url("/").toString());
    }

    @AfterAll
    static void stopServer() throws IOException {
        SERVER.shutdown();
    }

    @Test
    void getByIdMapsPathAndHeader() throws Exception {
        SERVER.enqueue(new MockResponse()
            .setResponseCode(200)
            .addHeader("Content-Type", "application/json")
            .setBody("""
                {
                  "id": "42",
                  "name": "Keyboard",
                  "category": "hardware"
                }
                """));

        CatalogItem item = catalog
            .getById("42", "request-001")
            .block(Duration.ofSeconds(3));

        assertNotNull(item);
        assertEquals("42", item.id());
        assertEquals("Keyboard", item.name());

        RecordedRequest request =
            SERVER.takeRequest(2, TimeUnit.SECONDS);

        assertNotNull(request);
        assertEquals("GET", request.getMethod());
        assertEquals("/api/catalog/42", request.getPath());
        assertEquals(
            "request-001",
            request.getHeader("X-Request-Id"));
        assertEquals(
            "application/json",
            request.getHeader("Accept"));
    }

    @Test
    void queryParameterAndFluxResponseAreMapped() throws Exception {
        SERVER.enqueue(new MockResponse()
            .setResponseCode(200)
            .addHeader("Content-Type", "application/json")
            .setBody("""
                [
                  {"id":"1","name":"Keyboard","category":"books"},
                  {"id":"2","name":"Mouse","category":"books"}
                ]
                """));

        var items = catalog.findByCategory("books")
            .collectList()
            .block(Duration.ofSeconds(3));

        assertNotNull(items);
        assertEquals(2, items.size());
        assertEquals("Keyboard", items.get(0).name());

        RecordedRequest request =
            SERVER.takeRequest(2, TimeUnit.SECONDS);

        assertNotNull(request);
        assertEquals("GET", request.getMethod());
        assertEquals(
            "/api/catalog?category=books",
            request.getPath());
    }

    @Test
    void postMapsJsonBodyAndReturnsLocation() throws Exception {
        SERVER.enqueue(new MockResponse()
            .setResponseCode(201)
            .addHeader("Content-Type", "application/json")
            .addHeader("Location", "/api/catalog/99")
            .setBody("""
                {
                  "id": "99",
                  "name": "Keyboard",
                  "category": "hardware"
                }
                """));

        var response = catalog.create(
            new CreateCatalogItem("Keyboard", "hardware"))
            .block(Duration.ofSeconds(3));

        assertNotNull(response);
        assertEquals(201, response.getStatusCode().value());
        assertEquals(
            URI.create("/api/catalog/99"),
            response.getHeaders().getLocation());
        assertNotNull(response.getBody());
        assertEquals("99", response.getBody().id());

        RecordedRequest request =
            SERVER.takeRequest(2, TimeUnit.SECONDS);

        assertNotNull(request);
        assertEquals("POST", request.getMethod());
        assertEquals("/api/catalog", request.getPath());
        assertTrue(request.getHeader("Content-Type")
            .startsWith("application/json"));

        String json = request.getBody().readUtf8();
        assertTrue(json.contains("\"name\":\"Keyboard\""));
        assertTrue(json.contains("\"category\":\"hardware\""));
    }

    @Test
    void notFoundStatusBecomesWebClientException() {
        SERVER.enqueue(new MockResponse()
            .setResponseCode(404)
            .addHeader("Content-Type", "application/problem+json")
            .setBody("""
                {"title":"Not Found","status":404}
                """));

        WebClientResponseException error = assertThrows(
            WebClientResponseException.class,
            () -> catalog.getById("missing", "request-404")
                .block(Duration.ofSeconds(3)));

        assertEquals(404, error.getStatusCode().value());
    }

    @Test
    void deleteCompletesAfterNoContentResponse() throws Exception {
        SERVER.enqueue(new MockResponse().setResponseCode(204));

        catalog.delete("42").block(Duration.ofSeconds(3));

        RecordedRequest request =
            SERVER.takeRequest(2, TimeUnit.SECONDS);

        assertNotNull(request);
        assertEquals("DELETE", request.getMethod());
        assertEquals("/api/catalog/42", request.getPath());
    }
}
~~~

The tests verify real requests/responses over HTTP:
- `@PathVariable` constructs the right path.
- `@RequestHeader` sends the right header.
- `@RequestParam` creates the query string.
- `Flux<CatalogItem>` decodes the JSON array.
- `@RequestBody` serializes the DTO to JSON.
- `Mono<ResponseEntity<T>>` preserves status and Location.
- Status 404 emits `WebClientResponseException` by default.
- `Mono<Void>` completes after receiving 204.

`block()` appears only in tests to obtain synchronous results for assertions. Production code should compose `Mono`/`Flux` instead of blocking.

### 11.9. Running Tests

Requires JDK 17+ and Maven:

~~~bash
java -version
mvn -version
mvn test
mvn spring-boot:run
~~~

Tests automatically start MockWebServer and shut it down upon completion. When running the application normally, `catalog.base-url` must point to a real HTTP service.

## 12. Comparing Proxy Calls and Direct WebClient Calls

Both approaches share the same WebClient connector, codecs, and filters. The primary difference is where requests are declared.

HTTP Service interface:

~~~java
catalog.getById("42", requestId);
~~~

Direct WebClient:

~~~java
webClient.get()
    .uri("/api/catalog/{id}", "42")
    .header("X-Request-Id", requestId)
    .retrieve()
    .bodyToMono(CatalogItem.class);
~~~

Proxies give endpoint contracts a clear name and make injection and mocking easy. Direct WebClient lets callers control every step of request/response handling. Both can coexist in one application: interfaces for stable APIs, direct WebClient for operations needing `exchangeToMono`/`exchangeToFlux` or specialized protocol logic.

### 12.1. Preserving Full WebClient Customizability

Creating a proxy does not mean giving up:
- `ExchangeFilterFunction`.
- Custom codecs and `maxInMemorySize`.
- TLS, proxy, connection pool, and connector.
- Default headers/cookies.
- Metrics, observations, and tracing.
- OAuth2 authorized client filters.
- Default status handlers.

All configuration on WebClient is used by every method of the interface proxy backed by that adapter.

## 13. Multiple HTTP Services and HTTP Service Groups

An application often calls multiple downstream hosts. Do not use a single base URL for all interfaces if they belong to different systems.

One manual approach is creating each client group separately:
- `CatalogHttpService` using a WebClient pointing to the catalog host.
- `BillingHttpService` using a WebClient pointing to the billing host.
- `IdentityHttpService` using a WebClient with its own OAuth2 filter and timeouts.

Each proxy can use a different factory/adapter while keeping its interface contract independent.

Starting in Spring Framework 7.0, HTTP Service Groups are also available to register multiple interfaces as proxy beans by group. A group typically shares the same client setup and `HttpServiceProxyFactory`; it can be declared via `@ImportHttpServices` or a registrar. This reduces repetitive configuration when an application has many interfaces and multiple hosts. For small applications, creating beans manually as in the example above remains easy to follow.

## 14. Important Contract Considerations

### 14.1. Client and Server Can Share an Interface, but Consider Coupling

Spring also supports `@HttpExchange` on an interface implemented by a `@Controller` on the server side. That can be useful for internal APIs when client and server need to share a contract.

However, sharing an interface also creates coupling between two applications:
- Method changes can force client/server to deploy in lockstep.
- DTOs may not fit both bounded contexts.
- Client annotations and server validation/concerns can differ.
- Public APIs typically require independent versioning and compatibility.

Do not default to sharing Java interfaces for all public APIs. You can share OpenAPI/schemas or contract tests without sharing entire codebases.

### 14.2. `@HttpExchange` and `@RequestMapping` Do Not Serve the Same Purpose

`@HttpExchange` describes a specific HTTP operation for a client interface. `@RequestMapping` on the server can express richer mapping conditions such as method, path, params, headers, consumes, and produces. Spring permits `@HttpExchange` on server controller methods in some scenarios, but a client interface is not automatically registered as a controller.

### 14.3. Parameter Names Must Be Explicit

Prefer writing:

~~~java
@GetExchange("/{id}")
Mono<CatalogItem> get(
    @PathVariable("id") String id);
~~~

Avoid relying on parameter names retained by the compiler. When refactoring methods or building with different compiler options, explicit names in annotations keep the contract stable.

### 14.4. Response Bodies Must Be Consumed

- `Mono<T>` decodes a single object.
- `Flux<T>` consumes the response body as a stream.
- `Mono<Void>` returns no body, yet response content is still released.
- `Mono<ResponseEntity<Flux<T>>>` returns headers first; the caller is responsible for consuming the stream.

Never drop an unsubscribed response Publisher. Doing so can retain connections/buffers or prevent the request from executing at all because reactive pipelines are lazy.

## 15. Common Mistakes and Fixes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Creating an interface but forgetting to create the proxy bean | HTTP service cannot be injected | Create WebClientAdapter, factory, and `createClient(...)` |
| Using `@HttpExchange` as if it sends HTTP requests by itself | No requests are ever sent | Requires adapter and `HttpServiceProxyFactory` |
| Putting production base URLs inside annotations | Hard to switch environments and test | Set base URL on WebClient from properties |
| Missing `@PathVariable` or mismatched names | URI does not expand as intended | Declare placeholder names explicitly |
| Using `@RequestParam` while expecting a JSON body | Incorrect query/form encoding | Use `@RequestBody` for JSON; configure form content type when needed |
| Choosing synchronous `T` on reactive request paths | Can block callers/event loops | Use `Mono<T>` or `Flux<T>` |
| Choosing `Mono<T>` for multi-element responses | Does not represent the right cardinality | Use `Flux<T>` or a wrapper DTO if the API returns an object containing a list |
| Expecting `ResponseEntity` to automatically ignore all 404s | Default status handler may emit an exception | Use a custom status handler or intentional adapter decorator |
| Catching every exception and returning `Mono.empty()` | Hides 401/500 errors and loses root causes | Map specifically by status/domain error |
| Retrying every POST | Creates duplicate resources when the server processed the first attempt | Use idempotency keys and clear retry policies |
| Logging entire WebClient requests | Leaks tokens, cookies, PII, or bodies | Allowlist log fields and redact credentials |
| Creating a factory on every method call | Wastes configuration, complicates lifecycle management | Register a singleton proxy bean |
| Sharing one WebClient across all trust boundaries | Credentials/filters may be sent to the wrong host | Separate clients per host/policy |
| Only mocking interfaces in tests | Does not verify real annotation mappings | Add MockWebServer HTTP integration tests |
| Not configuring timeouts | Requests can hold resources too long | Set appropriate connector and operation timeouts |
| Not consuming `Flux` responses | Lazy request never executes or connection is not released | Subscribe/compose the body in the caller |

## 16. Debugging Steps When a Proxy Calls the Wrong API

1. Confirm the right interface class is proxied and the bean is injected.
2. Check the base URL from the active property/profile.
3. Check the type-level `@HttpExchange` and method-level exchange annotations.
4. Verify path variable names, query parameters, request headers, and Content-Type.
5. Check whether `WebClient.Builder` has filters/default headers/codecs altering the request.
6. Inspect `RecordedRequest` in MockWebServer to see the actual request sent.
7. If the response errors, inspect WebClient's status and exception type; do not just read the message.
8. If the body fails to decode, check response Content-Type, JSON schema, and codec configuration.
9. If requests hang, inspect subscriptions, timeouts, remote response bodies, and the connection pool.
10. If errors happen only in production, compare base URL, TLS, proxy, DNS, and authentication configs across profiles.

Use controlled HTTP wire logging in test/staging. Never enable broad body/Authorization header logging in production.

## 17. Production Checklist

- [ ] Each interface represents a downstream API with a clear contract.
- [ ] Type-level base path and method-level paths are declared consistently.
- [ ] Path variables, queries, headers, cookies, and bodies have explicit annotations/names.
- [ ] Return types accurately reflect cardinality and reactive lifecycle.
- [ ] WebClientAdapter and HttpServiceProxyFactory are created once in configuration.
- [ ] The proxy is registered as a bean and injected via constructor.
- [ ] Base URL, TLS, credentials, and timeouts come from environment configuration.
- [ ] WebClient filters only add headers within the right trust boundary.
- [ ] 4xx/5xx statuses are mapped to appropriate domain errors.
- [ ] Retries apply only to transient errors and safe operations.
- [ ] Response body streams are always consumed or released.
- [ ] Logging never records raw credentials, cookies, or request bodies.
- [ ] HTTP integration tests verify method/path/query/header/body/status.
- [ ] Tests cover 404, 5xx, timeouts, and malformed responses as needed.
- [ ] A compatibility/versioning strategy exists for remote DTOs/APIs.
- [ ] HTTP Service Groups are used when the number of interfaces/client configs warrants grouped management.

## 18. Practice Exercises

**Exercise 1 – GET proxy.** Create `CatalogHttpService` with `@GetExchange("/{id}")`. Use MockWebServer to verify the path variable and JSON response.

**Exercise 2 – Query.** Create `findByCategory` accepting `@RequestParam`; verify the query string and decode the response into `Flux<CatalogItem>`.

**Exercise 3 – Header.** Pass `X-Request-Id` via `@RequestHeader`. Verify the value in RecordedRequest.

**Exercise 4 – POST.** Create a method taking `@RequestBody` and returning `Mono<ResponseEntity<T>>`. Verify the JSON body, 201, and Location.

**Exercise 5 – DELETE.** Return `Mono<Void>` and verify the 204 response is properly consumed.

**Exercise 6 – Error mapping.** Return 404 and 503 from the mock server. Map 404 to domain not-found; keep 503 as a dependency failure.

**Exercise 7 – Filter.** Add an `ExchangeFilterFunction` attaching client name and correlation ID. Inspect headers in the mock server.

**Exercise 8 – Timeout.** Configure a short response timeout; use mock server delay to confirm the timeout error is mapped properly.

**Exercise 9 – Streaming.** Declare `Flux<CatalogEvent>` for NDJSON/SSE. Verify the caller consumes the stream on demand.

**Exercise 10 – Multiple hosts.** Create Catalog and Billing interfaces, each backed by a WebClient with its own base URL and authentication policy.

## 19. Official References

1. Spring Framework 7.0.8 – REST Clients and HTTP Service Clients: https://docs.spring.io/spring-framework/reference/integration/rest-clients.html
2. Spring Framework 7.0.8 – `WebClient` and Reactive Client: https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html
3. Spring Framework Javadoc – `WebClientAdapter`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/reactive/function/client/support/WebClientAdapter.html
4. Spring Framework Javadoc – `HttpServiceProxyFactory`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/service/invoker/HttpServiceProxyFactory.html
5. Spring Framework Javadoc – `HttpExchange` and Method Annotations: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/service/annotation/HttpExchange.html
6. Spring Framework – WebClient Filters: https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-filter.html
7. Spring Framework – WebClient Exchange and Response Handling: https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-exchange.html
8. Spring Boot 4.0 – Calling REST Services: https://docs.spring.io/spring-boot/4.0/reference/io/rest-client.html
9. Reactor Core – Reference Guide: https://projectreactor.io/docs/core/release/reference/

**Final self-check:** What does `@HttpExchange` describe, and which component creates the implementation for the interface? Why does `WebClientAdapter` still require a configured WebClient? When do you choose `Mono<ResponseEntity<T>>` over `Mono<T>`? Why is `Flux<T>` suitable for response streams and why must the caller consume the body? If you have verified real requests through MockWebServer, you have confirmed that the interface contract maps accurately to HTTP.
