# Creating Builders, Reusing Clients, and Mutating Configurations

**Context:** Spring Framework Reactive → **Sending WebClient Requests**.

`WebClient` is Spring WebFlux's reactive HTTP client. It sends requests using `Mono`/`Flux`, decodes responses via codecs, and integrates outbound HTTP into the Reactor pipeline. When an application calls multiple APIs, configure the client at startup, build it into a reusable `WebClient`, and create intentional variants with `mutate()` when needed.

Four core concepts:

- **Builder:** a mutable configuration object used to set the base URL, default headers, filters, codecs, connector, timeouts, and other policies.
- **build():** creates a `WebClient` from the builder's current configuration.
- **Reuse:** a built `WebClient` is immutable and thread-safe; it can be used concurrently across multiple requests.
- **mutate():** creates a new builder initialized from the existing client's configuration; modify the new builder and build to create another client. The original client is not modified.

The key principle is separating shared configuration from per-request data. Base URL, codecs, and connection pools usually belong to the client; a user's bearer token, tenant ID, or correlation ID usually belong to the current request.

## 1. WebClient Configuration Lifecycle

An application typically creates clients when the Spring context starts up:

```text
Application startup
       |
       v
WebClient.Builder
       |
       +-- baseUrl / URI strategy
       +-- default headers / cookies
       +-- ExchangeFilterFunction
       +-- codecs / ExchangeStrategies
       +-- ClientHttpConnector
       +-- timeout / connection pool
       |
       v
     build()
       |
       v
Reusable WebClient
       |
       +---- request A
       +---- request B
       +---- request C
       |
       v
Reactor pipeline + HTTP transport
```

The builder is where configuration is assembled. After calling `build()`, the client holds the created configuration and can be shared across multiple threads. Each request still creates its own request specification via `get()`, `post()`, `put()`, or `method(...)`.

There is no need to create a new `WebClient` for every HTTP call. Doing so duplicates configuration, may create extra connection providers/connection pools, and makes resource management harder.

## 2. Creating a WebClient with a Builder

Basic approach:

```java
WebClient client = WebClient.builder()
        .baseUrl("https://catalog.example.com")
        .defaultHeader(
                HttpHeaders.ACCEPT,
                MediaType.APPLICATION_JSON_VALUE)
        .build();
```

`WebClient.builder()` creates a new builder. `baseUrl` sets the base URI for relative URIs. `defaultHeader` declares a default header when a specific request has not provided that header. `build()` creates the client.

A shorter factory can be used:

```java
WebClient client = WebClient.create(
        "https://catalog.example.com");
```

`WebClient.create(baseUrl)` is convenient for simple clients. When filters, codecs, connectors, timeouts, or multiple defaults are needed, the builder is more flexible.

Separating configuration into a bean:

```java
@Configuration
class OutboundClientConfiguration {

    @Bean
    WebClient catalogClient(WebClient.Builder builder) {
        return builder
                .baseUrl("https://catalog.example.com")
                .defaultHeader(
                        HttpHeaders.ACCEPT,
                        MediaType.APPLICATION_JSON_VALUE)
                .build();
    }
}
```

This is a Spring Boot snippet requiring appropriate imports and component scanning. When injecting the auto-configured builder provided by Spring Boot, the builder has already been configured by Boot with the application's customizers and codec settings.

If not using Spring Boot, you can create `WebClient.builder()` manually and register the required connector/codecs. Do not assume a manually created builder has all the customizers Boot provides.

## 3. baseUrl and URI Resolution

`baseUrl` is convenient when multiple endpoints share a host:

```java
WebClient client = WebClient.builder()
        .baseUrl("https://api.example.com/v1")
        .build();

Mono<Item> item = client.get()
        .uri("/items/{id}", 42)
        .retrieve()
        .bodyToMono(Item.class);
```

The URI is built from the template and passed-in variables. You can use a lambda to configure the URI builder:

```java
Mono<Item> item = client.get()
        .uri(builder -> builder
                .path("/items/{id}")
                .queryParam("include", "details")
                .build(42))
        .retrieve()
        .bodyToMono(Item.class);
```

Several rules:

- Relative URIs are resolved against the base URI.
- Absolute URIs in a request call can specify a different host and do not use the base URL as the host.
- If `uriBuilderFactory` is configured, it is the primary URI-building strategy; do not simultaneously expect `baseUrl` to control the same configuration.
- `defaultUriVariables` provides default values for URI template variables when appropriate.
- With multiple hosts or tenants, you can pass absolute URIs per request or create separate clients for each upstream with different policies.

Do not concatenate URL strings by arbitrarily appending paths and queries. Use URI templates or a URI builder to encode path segments, query parameters, and special characters properly.

## 4. Default Headers and Cookies

The builder supports `defaultHeader`, `defaultHeaders`, `defaultCookie`, and `defaultCookies`.

```java
WebClient client = WebClient.builder()
        .defaultHeader(
                HttpHeaders.ACCEPT,
                MediaType.APPLICATION_JSON_VALUE)
        .defaultHeader("X-Application", "order-service")
        .defaultCookie("client-version", "2")
        .build();
```

Default headers are applied when the request does not already have a header with the same name. A request can supply its own value for that specific request:

```java
Mono<Item> result = client.get()
        .uri("/items/42")
        .header("X-Request-Source", "mobile")
        .retrieve()
        .bodyToMono(Item.class);
```

Use `defaultHeaders(Consumer<HttpHeaders>)` when you want to edit the default header set as a group:

```java
WebClient client = WebClient.builder()
        .defaultHeaders(headers -> {
            headers.setAccept(
                    List.of(MediaType.APPLICATION_JSON));
            headers.set("X-Application", "inventory");
        })
        .build();
```

Similarly, `defaultCookies` lets you add or modify default cookies. Default cookies should not contain sessions or user-identifying information that changes per request.

### 4.1. Default Headers Are Not Mandatory Overrides

Default headers are fallback values. The request specification can set its own headers. This is useful when one client calls multiple endpoints where each request has a different correlation ID, locale, or tenant.

Do not put user A's token into the default header of a singleton client and then use that client for user B. Attach credentials per request:

```java
Mono<Account> account = client.get()
        .uri("/accounts/me")
        .headers(headers ->
                headers.setBearerAuth(accessToken))
        .retrieve()
        .bodyToMono(Account.class);
```

`accessToken` here must belong to the current request and be obtained from the appropriate security context. Do not hold user tokens in mutable fields of a `WebClient` bean.

If each client represents a fixed service account, service-level credentials may live in that client's dedicated configuration; secrets must still be protected in configuration/secret managers and rotated according to policy.

## 5. Reusing WebClient Across Multiple Requests

`WebClient` is designed to be immutable once built and thread-safe. A singleton bean can be injected into multiple services:

```java
@Service
class CatalogService {

    private final WebClient catalogClient;

    CatalogService(WebClient catalogClient) {
        this.catalogClient = catalogClient;
    }

    Mono<Item> findItem(String id) {
        return catalogClient.get()
                .uri("/items/{id}", id)
                .retrieve()
                .bodyToMono(Item.class);
    }
}
```

Multiple calls to `findItem` can occur concurrently. A new request specification is created for each invocation; client configuration is not altered by requests.

Benefits of reuse:

- Reuses the connection pool and HTTP connector configuration.
- Centralizes base URL, codecs, TLS, timeouts, and filters.
- Reduces repeated creation of configuration objects.
- Easy to test by swapping the bean or connector configuration.
- Provides a clear place to manage observability and outbound policies.

**Reusing a client does not mean reusing a request builder.** Do not store `RequestHeadersSpec`, `RequestBodySpec`, or request-specific mutable objects in singleton fields. Create a new request from the client for each call.

## 6. WebClient.Builder in Spring Boot

Spring Boot auto-configures `WebClient.Builder` with customizers and codecs matching the present dependencies. You can inject the builder into bean factory methods to create specialized clients:

```java
@Configuration
class ApiClients {

    @Bean
    WebClient inventoryClient(WebClient.Builder builder) {
        return builder
                .baseUrl("https://inventory.example.com")
                .defaultHeader("X-Client", "inventory-adapter")
                .build();
    }

    @Bean
    WebClient pricingClient(WebClient.Builder builder) {
        return builder
                .baseUrl("https://pricing.example.com")
                .defaultHeader("X-Client", "pricing-adapter")
                .build();
    }
}
```

In Spring Boot, the auto-configured builder has prototype scope: each injection can receive a separate builder with Boot's customizers already applied. This lets client beans be configured independently without accidentally sharing the same mutable builder. Check the documentation for your specific Boot version if changing scope or defining a custom builder bean.

If you manually declare a shared singleton builder, calling configuration methods on the builder can affect subsequent builds. Do not mutate a shared builder concurrently from multiple threads or per request.

### 6.1. Multiple Clients, One Shared Configuration Set

If multiple clients need the same policy, create a shared customizer or factory method:

```java
private WebClient.Builder configureCommon(
        WebClient.Builder builder) {

    return builder
            .defaultHeader(
                    HttpHeaders.ACCEPT,
                    MediaType.APPLICATION_JSON_VALUE);
}
```

Each bean then applies the common part and adds its own configuration. With Boot, `WebClientCustomizer` can be used to configure the auto-configured builder at the application level. Restrict customizers to policies that are genuinely shared; do not put a specific upstream's base URL or credentials into a global customizer.

## 7. mutate(): Creating Variants from a Built Client

`WebClient.mutate()` returns a builder initialized from the client's current configuration. You can change the base URL, default headers, filters, connector, or other builder settings and build a new client.

Example:

```java
WebClient publicClient = WebClient.builder()
        .baseUrl("https://api.example.com")
        .defaultHeader("X-Client", "public")
        .build();

WebClient adminClient = publicClient.mutate()
        .defaultHeaders(headers ->
                headers.set("X-Client", "admin"))
        .build();
```

Result:

- `publicClient` still keeps the default header `X-Client: public`.
- `adminClient` is a new client with the default header `X-Client: admin`.
- Shared configuration already present in the public client is carried over to the new builder, except for what you change.
- `mutate()` does not modify the original client in place.

This is a suitable way to create clients for variants that share connectors, codecs, or filters but differ in base URL, default headers, or policies.

### 7.1. mutate Does Not Change the Existing Singleton Configuration

The following example does not alter the initial client:

```java
WebClient original = WebClient.builder()
        .baseUrl("https://api.example.com")
        .build();

WebClient regional = original.mutate()
        .baseUrl("https://eu-api.example.com")
        .build();
```

`original` still points to the old host. `regional` uses the new host. If a service keeps calling `original`, it will not automatically switch to the regional configuration.

Store the new client in an appropriate bean/field or return it from a factory. Do not expect `mutate()` to update every place referencing the old client.

### 7.2. When Should You Use mutate?

- Same upstream but having public/admin clients with different default headers.
- Same codecs and connector but different base URLs per region.
- Creating a specialized client for an integration test or an API group.
- Adding dedicated filters/observations to a derived client.
- Keeping common configuration and changing only a few policies.

If two clients differ significantly in TLS, credentials, timeouts, proxies, or connection pools, consider creating independent builders. Using mutate merely for convenience can carry over unwanted filters or default headers.

## 8. Builder Filter Configuration

`ExchangeFilterFunction` allows intercepting requests/responses on the client side. Filters are commonly used for correlation IDs, metrics, tracing, selective logging, service-level authentication, or error transformation.

Example adding a filter that records method and URL:

```java
ExchangeFilterFunction requestMetric =
        ExchangeFilterFunction.ofRequestProcessor(request -> {
            metrics.recordRequest(
                    request.method().name(),
                    request.url().getHost());

            return Mono.just(request);
        });

WebClient client = WebClient.builder()
        .filter(requestMetric)
        .build();
```

This is a snippet requiring a metrics implementation and imports. The filter receives the request before sending, then returns the request to the exchange chain. You can use `ofResponseProcessor` to observe the response status:

```java
ExchangeFilterFunction responseMetric =
        ExchangeFilterFunction.ofResponseProcessor(response -> {
            metrics.recordStatus(
                    response.statusCode().value());

            return Mono.just(response);
        });
```

Do not read the response body in a filter just for logging unless intentionally designed. The body is a stream with ownership; reading it can consume data the caller needs. If you need to inspect the body, design proper buffering/rebuilding and enforce size limits.

### 8.1. filter and filters

- `filter(filter)` appends a filter to the chain.
- `filters(consumer)` lets you inspect and modify the existing list of filters.
- `mutate()` can carry over filters from the original client; adding the same filter again can cause logic to run repeatedly.

When creating a derived client, be aware of which filters already exist. If you need to replace or remove a filter, use `filters(...)` with a clear predicate and test the actual chain.

Do not log Authorization, cookies, passwords, queries containing tokens, or sensitive response bodies. Correlation ID and method/path are usually sufficient for basic request observability.

## 9. Codecs and Memory Limits

The builder allows customizing codecs through `codecs`:

```java
WebClient client = WebClient.builder()
        .codecs(configurer ->
                configurer.defaultCodecs()
                        .maxInMemorySize(512 * 1024))
        .build();
```

This example sets a 512 KiB limit for aggregating codec operations that apply this limit. Choose the number based on actual payloads; do not treat this as a total RAM limit for the client or a limit on all buffers.

Custom codecs can be registered when the application needs specialized media types or serialization. Prefer configuring default codecs when only one property needs changing; only replace the entire `ExchangeStrategies` when you genuinely need control over the full reader/writer list.

Notes:

- Large bodies may require streaming instead of aggregating into a single object.
- `bodyToMono(String.class)` can aggregate the body into a String; set an appropriate limit.
- `bodyToFlux(DataBuffer.class)` hands raw byte buffers to the application; ownership/release must be managed.
- Do not raise `maxInMemorySize` indefinitely just to hide oversized-payload errors.
- Request/response bodies need matching Content-Type and Accept headers so codecs select the right representation.

## 10. ClientHttpConnector and Transport

`ClientHttpConnector` connects WebClient to the HTTP runtime. WebClient does not perform socket I/O itself; the connector translates requests into operations on a client implementation such as Reactor Netty.

You can specify a connector:

```java
HttpClient httpClient = HttpClient.create()
        .responseTimeout(Duration.ofSeconds(3));

WebClient client = WebClient.builder()
        .clientConnector(
                new ReactorClientHttpConnector(httpClient))
        .build();
```

The snippet requires Reactor Netty dependencies, `HttpClient`, `ReactorClientHttpConnector`, and imports. `responseTimeout` is the timeout for response reads according to the connector's semantics; it does not replace connect timeout, pool acquisition timeout, or full-request business timeouts.

When a dedicated connection pool is needed:

```java
ConnectionProvider provider =
        ConnectionProvider.builder("catalog-pool")
                .maxConnections(50)
                .build();

HttpClient httpClient = HttpClient.create(provider)
        .responseTimeout(Duration.ofSeconds(3));

WebClient client = WebClient.builder()
        .clientConnector(
                new ReactorClientHttpConnector(httpClient))
        .build();
```

This is an illustrative snippet. `ConnectionProvider` is a resource with a lifecycle; if the application creates a provider manually, it must dispose of it on application shutdown. Do not create a new pool per request or per `mutate()` call without a clear reason.

Other transport settings may include proxy, TLS, connect timeout, response timeout, wiretap, and connection limits. Set timeouts at each appropriate layer; pool acquisition, connect, response read, and entire-workflow timeouts have different meanings.

## 11. defaultStatusHandler and Common Error Policy

The builder supports `defaultStatusHandler` to map response statuses into exceptions for requests using `retrieve()`:

```java
WebClient client = WebClient.builder()
        .defaultStatusHandler(
                HttpStatusCode::isError,
                response -> response.bodyToMono(String.class)
                        .defaultIfEmpty("")
                        .map(body -> new RemoteApiException(
                                response.statusCode(), body)))
        .build();
```

This snippet requires `RemoteApiException` and imports. The handler reads the error body once to build the exception. Do not log the entire body if it may contain sensitive data; extract only a normalized error code or limit the content.

If only one request has a special error policy, use `retrieve().onStatus(...)` on that request. With `exchangeToMono`/`exchangeToFlux`, the application decides how to handle status and body inside the callback; the body must be consumed or released according to its lifecycle.

Do not confuse HTTP 4xx/5xx errors with connection errors. `defaultStatusHandler` handles response statuses; DNS failures, connection resets, TLS failures, or timeouts are transport errors and require separate error mapping.

## 12. Shared Configuration vs. Per-Request Configuration

Place each type of data in the proper scope:

| Configuration | Appropriate scope | Example |
|---|---|---|
| Upstream base URL | Client | `https://catalog.example.com` |
| Default Accept | Client | `application/json` |
| Codecs and max in-memory size | Client | JSON, NDJSON, 512 KiB |
| Connection pool/TLS/proxy | Connector/client | Catalog pool |
| Metrics/tracing filters | Client | Request timing |
| Fixed service account | Dedicated client with protected secret | Integration credentials |
| Current user's bearer token | Request | `headers.setBearerAuth(token)` |
| Per-request tenant ID | Request | `X-Tenant-Id` |
| Per-request correlation ID | Request/context | `X-Request-Id` |
| Query/path variables | Request | `uri("/items/{id}", id)` |

Do not modify the default headers of a singleton client per request. If code calls `client.mutate()` and builds a new client per user, it creates unnecessary clients/configurations. Instead, keep the shared client and place per-user data on the request specification.

## 13. Runnable Java 17+ Example: Build, Reuse, and Mutate

This example starts a Reactor Netty HTTP server on a dynamic port, builds a base WebClient, creates a derived client via `mutate()`, and sends multiple requests. The server echoes the item ID and the `X-Client` header so you can observe which configuration was used.

Structure:

```text
webclient-builder-demo/
├── pom.xml
└── src/main/java/demo/WebClientBuilderDemo.java
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
    <artifactId>webclient-builder-demo</artifactId>
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

### 13.2. WebClientBuilderDemo.java

```java
package demo;

import org.springframework.web.reactive.function.client.WebClient;

import reactor.core.publisher.Mono;
import reactor.netty.DisposableServer;
import reactor.netty.http.server.HttpServer;

public class WebClientBuilderDemo {

    public static void main(String[] args) {
        DisposableServer server = HttpServer.create()
                .host("127.0.0.1")
                .port(0)
                .route(routes -> routes.get(
                        "/items/{id}",
                        (request, response) -> response.sendString(
                                Mono.just(
                                        "item=" + request.param("id")
                                        + ";client="
                                        + request.requestHeaders()
                                                .get("X-Client")))))
                .bindNow();

        try {
            String baseUrl =
                    "http://127.0.0.1:" + server.port();

            WebClient baseClient = WebClient.builder()
                    .baseUrl(baseUrl)
                    .defaultHeader("X-Client", "base")
                    .build();

            WebClient adminClient = baseClient.mutate()
                    .defaultHeaders(headers ->
                            headers.set("X-Client", "admin"))
                    .build();

            String baseResult = baseClient.get()
                    .uri("/items/{id}", 42)
                    .retrieve()
                    .bodyToMono(String.class)
                    .block();

            String adminResult = adminClient.get()
                    .uri("/items/{id}", 43)
                    .retrieve()
                    .bodyToMono(String.class)
                    .block();

            String requestOverride = baseClient.get()
                    .uri("/items/{id}", 44)
                    .headers(headers ->
                            headers.set("X-Client", "request"))
                    .retrieve()
                    .bodyToMono(String.class)
                    .block();

            String baseAgain = baseClient.get()
                    .uri("/items/{id}", 45)
                    .retrieve()
                    .bodyToMono(String.class)
                    .block();

            System.out.println("base: " + baseResult);
            System.out.println("admin: " + adminResult);
            System.out.println("request override: " + requestOverride);
            System.out.println("base again: " + baseAgain);
        }
        finally {
            server.disposeNow();
        }
    }
}
```

Run from the directory containing `pom.xml` with JDK 17+ and Maven:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.WebClientBuilderDemo
```

**Expected standard output:**

```text
base: item=42;client=base
admin: item=43;client=admin
request override: item=44;client=request
base again: item=45;client=base
```

Explanation:

1. The server binds port 0 so the OS selects a free port; the program reads the actual port from `server.port()`.
2. `baseClient` is built with a base URL and default header.
3. `baseClient.mutate()` creates a new builder carrying the base configuration; `adminClient` changes the default header to admin.
4. The third request overrides the header at request scope; there is no need to create a new client for each header value.
5. The final request proves that `baseClient` still keeps its original default header after creating `adminClient`.
6. `block()` appears only in the demo program's `main` to await the HTTP response; never call `block()` in a WebFlux handler or reactive service.

This example illustrates the builder/client lifecycle with a local server. Real applications usually inject a `WebClient` bean and compose `Mono`/`Flux` instead of calling `block()`.

## 14. Testing Client Configuration

Test actual HTTP behavior, not just that the bean exists.

Options:

- Use `MockWebServer` or an HTTP stub server to verify request method, path, query, headers, and body.
- Use WireMock or an equivalent mock HTTP server to simulate timeouts, 4xx/5xx, malformed bodies, and slow responses.
- Use a mock `ExchangeFunction` when you only need to unit-test request building and response mapping logic.
- Use integration tests with a local server when you need to confirm connector, codec, and connection lifecycle behavior.

Example using a mock `ExchangeFunction`:

```java
ExchangeFunction exchange = request -> {
    assertEquals("https://catalog.example.com/items/42",
            request.url().toString());

    return Mono.just(
            ClientResponse.create(HttpStatus.OK)
                    .header(
                            HttpHeaders.CONTENT_TYPE,
                            MediaType.APPLICATION_JSON_VALUE)
                    .body("{\"id\":42,\"name\":\"Reactive\"}")
                    .build());
};

WebClient client = WebClient.builder()
        .exchangeFunction(exchange)
        .baseUrl("https://catalog.example.com")
        .build();
```

This is a test snippet requiring JUnit/AssertJ and imports. A fake ExchangeFunction helps verify URI and mapping without opening a socket; it does not test DNS, TLS, pooling, or real transport.

With `mutate()`, test both clients:

- The original client retains its old base URL/default headers.
- The derived client receives the new configuration.
- Request-level headers override default headers properly.
- Filters are not unintentionally duplicated.
- Both clients have the expected codecs/connector.

## 15. Common Pitfalls

1. **Creating a new WebClient for every request.** Can create multiple configurations/pools and duplicate logic; reuse the built client.
2. **Thinking mutate modifies the original client.** mutate creates a new builder; build creates a different client.
3. **Sharing a mutable builder across multiple threads.** Configure builders at startup and do not mutate them concurrently while serving requests.
4. **Storing RequestHeadersSpec in a singleton field.** Request state can leak across calls; create a fresh request spec each time.
5. **Putting a user's bearer token into defaultHeader of a shared client.** Can send the wrong user's credentials across users; attach tokens per request.
6. **Assuming defaultHeader always overrides request headers.** Defaults only apply when the request has not supplied a value for the same name.
7. **Using baseUrl for all hosts.** An absolute URI can specify a different host; create separate clients if upstreams have different policies.
8. **Configuring both baseUrl and uriBuilderFactory without understanding precedence.** uriBuilderFactory is the URI strategy; avoid conflicting configurations for the same purpose.
9. **Adding duplicate filters during mutate.** Filters from the original client can carry over to the derived client; inspect the list before adding.
10. **Reading the response body in a logging filter.** The body can be consumed; if inspection is needed, buffer/rebuild following lifecycle rules and limit size.
11. **Logging Authorization or cookies.** Can expose secrets and sessions; mask or omit them from logs.
12. **Increasing maxInMemorySize indefinitely.** Can mask invalid payloads and cause memory pressure; choose limits intentionally.
13. **Treating responseTimeout as the entire-workflow timeout.** Connect, pool acquisition, response read, and business logic have different timeouts.
14. **Creating a dedicated ConnectionProvider without disposing it.** Pools have a resource lifecycle; release them on application shutdown.
15. **Treating defaultStatusHandler as a handler for all errors.** It handles HTTP response statuses; DNS/TLS/timeout errors need separate policies.
16. **Applying automatic retries to every request.** POST or non-idempotent operations can cause duplicate side effects; design idempotency and retry policies.
17. **Using block in a reactive service.** Blocks threads and breaks composition; use only in main programs or intentional imperative boundaries.
18. **Subscribing manually inside a service to send requests.** Callers lose control of errors/cancellation; return the publisher for callers to compose.
19. **Replacing the connector during mutate while forgetting the old lifecycle.** Clarify which client owns the pool/connector and who disposes of it.
20. **Assuming a WebClient bean automatically has the right base URL.** Configure each upstream explicitly; do not rely on accidental URIs from the environment.

## 16. Production Configuration Checklist

Before putting WebClient into production, confirm:

- **Client scope:** one client per upstream or multiple clients by policy?
- **Builder:** Boot auto-configured builder or manually created builder? Which customizers were applied?
- **URI:** are base URL, URI templates, absolute URIs, and query encoding correct?
- **Defaults:** are Accept, Content-Type, default headers, and cookies genuinely shared?
- **Credentials:** are user tokens/tenant/correlation IDs at request scope?
- **Reuse:** is the client created at startup and reused; is the request specification created fresh per call?
- **mutate:** does the derived client retain required filters/codecs/connector and change the right settings?
- **Filters:** are filter order, duplicates, logging, and response body ownership clear?
- **Codecs:** are max in-memory size, streaming, and media types appropriate?
- **Transport:** are connection pool, TLS, proxy, connect/response timeouts, and shutdown lifecycle configured?
- **Errors:** do HTTP statuses, transport failures, retries, and idempotency have separate policies?
- **Observability:** do metrics/tracing include request IDs without exposing secrets?
- **Tests:** have URI/header/body, mutate isolation, 4xx/5xx, timeouts, and transport been tested?

**Key takeaway:** build configuration with `WebClient.builder()`, call `build()` to obtain a reusable immutable client, and use `mutate()` to create new variants without altering the original client. Keep base URL, codecs, filters, and transport at client scope; keep tokens, tenant, and correlation IDs at request scope. When using Spring Boot, leverage the auto-configured builder; for custom clients, manage connectors/pools, timeouts, and cleanup according to the application lifecycle.

## References

- Spring Framework — [WebClient: Configuration and Builder](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-builder.html).
- Spring Framework — [WebClient Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/reactive/function/client/WebClient.html).
- Spring Framework — [WebClient.Builder Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/reactive/function/client/WebClient.Builder.html).
- Spring Framework — [ExchangeFilterFunction Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/reactive/function/client/ExchangeFilterFunction.html).
- Spring Boot — [Calling REST Services with WebClient](https://docs.spring.io/spring-boot/reference/io/rest-client.html).
- Reactor Netty — [HTTP Client Reference: Connection Pool and Timeouts](https://projectreactor.io/docs/netty/release/reference/http-client.html).
