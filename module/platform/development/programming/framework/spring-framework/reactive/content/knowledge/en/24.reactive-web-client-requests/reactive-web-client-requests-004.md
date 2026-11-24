# Method, Headers, Cookies, and Authentication with Spring WebClient

## 1. Objective: Building a Complete HTTP Request

`WebClient` is Spring WebFlux's reactive HTTP client. It provides a fluent API to choose the HTTP method, build the URI, add headers, cookies, body, and read the response. Operations are composed into a `Mono` or `Flux`, so the application can call remote services without blocking threads to wait for results.

An outbound request typically requires four groups of information:

1. **HTTP method and URI** identify the operation and target resource.
2. **Headers** describe the request, body format, desired response type, and metadata such as trace ID.
3. **Cookies** send session state or information required by the server via cookies.
4. **Authentication** provides credentials via Basic, Bearer token, API key, cookie session, or OAuth2 mechanisms.

This lesson focuses on configuring each group with `WebClient`, distinguishing default configuration from per-request configuration, using `ExchangeFilterFunction` for shared behavior, managing credentials safely, and testing real requests.

After this lesson, you will be able to:

- Select methods using shortcuts or `method(HttpMethod)`.
- Build URIs with path variables and query parameters.
- Add, replace, and set default headers.
- Send per-request cookies and understand the limitations of persisting cookies across multiple calls.
- Send Basic credentials, Bearer tokens, and API keys.
- Integrate reactive OAuth2 Client to obtain access tokens for outbound requests.
- Inspect method, headers, cookies, and authentication using a simulated HTTP test server.

## 2. Structure of a WebClient Request

A request is typically built as a chain:

```java
Mono<Item> result = webClient.get()
        .uri("/items/{id}", "42")
        .accept(MediaType.APPLICATION_JSON)
        .header("X-Request-Id", "req-123")
        .retrieve()
        .bodyToMono(Item.class);
```

Each step has a specific meaning:

- `get()` selects the HTTP GET method.
- `uri(...)` builds the target URI and substitutes path variables.
- `accept(...)` sets the `Accept` header, indicating which representation the client wants to receive.
- `header(...)` adds custom metadata.
- `retrieve()` starts the response processing flow using the simple API.
- `bodyToMono(Item.class)` decodes the response body into `Item`.

A request is not sent merely by calling `get()`, `uri()`, or `header()`. Those calls construct the request specification. The HTTP exchange begins when the publisher is subscribed to, usually managed by WebFlux or a reactive pipeline at the calling layer.

Do not call `.block()` in production reactive controllers/services. You may use `block(Duration)` in small programs or synchronous tests, but WebFlux application flows should return and compose `Mono`/`Flux`.

### Creating a WebClient

```java
WebClient client = WebClient.builder()
        .baseUrl("https://inventory.example.com")
        .build();
```

Or using the factory:

```java
WebClient client = WebClient.create(
        "https://inventory.example.com");
```

Once built, `WebClient` is immutable and can be reused across multiple requests. If a variant with different filters/headers is needed, use `mutate()` to create a new builder and build a new client:

```java
WebClient partnerClient = client.mutate()
        .defaultHeader("X-Client-Name", "partner-adapter")
        .build();
```

Do not create a new `WebClient` for every request without reason. Reusing the client takes advantage of connection pooling and connector configuration.

## 3. Selecting the HTTP Method and Building the URI

### 3.1. Method Shortcuts

`WebClient` provides shortcuts for common methods:

| API | HTTP method | Common purpose |
|---|---|---|
| `get()` | GET | Read a resource |
| `post()` | POST | Create a resource or execute an action |
| `put()` | PUT | Replace a resource's representation |
| `patch()` | PATCH | Partially update a resource |
| `delete()` | DELETE | Delete a resource |
| `head()` | HEAD | Fetch headers without a response body |
| `options()` | OPTIONS | Query supported capabilities/methods |

Example:

```java
Mono<Item> item = client.get()
        .uri("/items/{id}", "42")
        .retrieve()
        .bodyToMono(Item.class);

Mono<Item> created = client.post()
        .uri("/items")
        .contentType(MediaType.APPLICATION_JSON)
        .bodyValue(new CreateItem("Keyboard"))
        .retrieve()
        .bodyToMono(Item.class);

Mono<Void> deleted = client.delete()
        .uri("/items/{id}", "42")
        .retrieve()
        .bodyToMono(Void.class);
```

### 3.2. Selecting a Dynamic Method with `method(HttpMethod)`

When the method is decided at runtime or passed from another abstraction, use `method(...)`:

```java
HttpMethod method = HttpMethod.PATCH;

Mono<String> response = client.method(method)
        .uri("/items/{id}", "42")
        .contentType(MediaType.APPLICATION_JSON)
        .bodyValue(Map.of("displayName", "Mechanical keyboard"))
        .retrieve()
        .bodyToMono(String.class);
```

`method(HttpMethod)` returns the appropriate request specification to continue configuring URI, headers, and body. Only allow methods from the list supported by the application; do not take an arbitrary string from a user and use it directly to drive an outbound request.

### 3.3. Path Variables and Query Parameters

You can use URI templates:

```java
client.get()
        .uri("/items/{id}", "item-42")
        .retrieve()
        .bodyToMono(Item.class);
```

For query parameters, use `UriBuilder` to encode values properly:

```java
client.get()
        .uri(uriBuilder -> uriBuilder
                .path("/items")
                .queryParam("category", "office supplies")
                .queryParam("page", 2)
                .queryParam("tag", "new")
                .queryParam("tag", "featured")
                .build())
        .retrieve()
        .bodyToFlux(Item.class);
```

Values containing spaces or special characters must be encoded by the URI builder. Avoid assembling query strings via string concatenation because it easily produces invalid URIs or exposes sensitive data in URLs.

### 3.4. Method, Body, and HTTP Semantics

GET typically does not send a body. POST, PUT, and PATCH usually have a body; DELETE usually does not need a body, though some APIs have specific contracts. Follow the server's contract rather than relying on whether the client API lets you call a given method with a body.

Methods have different semantics:

- GET is expected to be safe and not alter business state.
- PUT usually carries the semantics of replacing the resource at the URI.
- PATCH applies a partial change; the patch media type must follow the contract, such as JSON Merge Patch or JSON Patch.
- POST is usually not idempotent by default. If retrying POST, consider an API-supported idempotency key.
- DELETE is usually designed to be idempotent in effect, though the response for subsequent deletions may differ.

Do not automatically retry every request on network errors. The request may have reached the server and created side effects even though the client did not receive a response.

## 4. Headers: Adding, Replacing, and Setting Defaults

HTTP headers carry request metadata. Common headers:

| Header | Meaning |
|---|---|
| `Accept` | Media type the client wants to receive |
| `Content-Type` | Media type of the request body |
| `Authorization` | Credentials per the authentication scheme |
| `Accept-Language` | Desired response language |
| `If-None-Match` | Conditional request by ETag |
| `If-Modified-Since` | Conditional request by modification timestamp |
| `X-Request-Id` | Correlation/request ID per internal contract |
| `X-Api-Key` | API key if the service specifies this header |

### 4.1. Using Built-in Shortcuts

```java
client.get()
        .uri("/catalog")
        .accept(MediaType.APPLICATION_JSON)
        .acceptCharset(StandardCharsets.UTF_8)
        .header("Accept-Language", "vi-VN")
        .retrieve()
        .bodyToMono(String.class);
```

For requests with a body:

```java
client.post()
        .uri("/items")
        .contentType(MediaType.APPLICATION_JSON)
        .accept(MediaType.APPLICATION_JSON)
        .bodyValue(new CreateItem("Keyboard"))
        .retrieve()
        .bodyToMono(Item.class);
```

`Content-Type` describes the body being sent. `Accept` describes the representation desired in response. The two headers apply to opposite directions of communication; do not use one in place of the other.

### 4.2. `header(...)` Appends Values

```java
client.get()
        .uri("/catalog")
        .header("X-Feature", "search")
        .header("X-Feature", "recommendations")
        .retrieve()
        .bodyToMono(String.class);
```

`header(name, values...)` adds values under the header name. If the header already has a value, it may produce multiple values or multiple field values according to HTTP and specific header semantics.

Do not use repeated additions for headers where the API expects a single value such as `Authorization`. For those headers, use `headers(...)` and `set(...)` to replace the current value.

### 4.3. `headers(...)` to Set, Add, or Remove

```java
client.get()
        .uri("/profile")
        .headers(headers -> {
            headers.set("X-Tenant", "tenant-42");
            headers.set("X-Request-Id", "req-2026-001");
            headers.remove("X-Debug-Only");
        })
        .retrieve()
        .bodyToMono(Profile.class);
```

`headers(Consumer<HttpHeaders>)` lets you manipulate the declared `HttpHeaders`:

- `set(name, value)` replaces existing values with a single value.
- `add(name, value)` adds a value.
- `remove(name)` removes the header.

Authentication helpers also live on `HttpHeaders`, such as `setBasicAuth(...)` and `setBearerAuth(...)`.

### 4.4. Default Headers at the WebClient Level

If every request to a service needs the same metadata, configure defaults on the builder:

```java
WebClient inventoryClient = WebClient.builder()
        .baseUrl("https://inventory.example.com")
        .defaultHeader("X-Client-Name", "order-service")
        .defaultHeader(
                HttpHeaders.ACCEPT,
                MediaType.APPLICATION_JSON_VALUE)
        .build();
```

`defaultHeader` only adds the default header if the specific request has not declared that header. Thus a request can override it with its own value:

```java
inventoryClient.get()
        .uri("/items")
        .header("X-Client-Name", "catalog-sync")
        .retrieve()
        .bodyToFlux(Item.class);
```

Similarly, `defaultHeaders(...)` lets you manage the declared set of default headers:

```java
WebClient client = WebClient.builder()
        .defaultHeaders(headers -> {
            headers.set("X-Client-Name", "report-service");
            headers.setAccept(List.of(MediaType.APPLICATION_JSON));
        })
        .build();
```

Do not put a user's token or cookie into the default headers/cookies of a client shared across multiple users or multiple hosts. Credentials could be sent unintentionally to another request if the client is used with an unexpected URI.

### 4.5. Conditional Headers

WebClient provides helpers for some conditional requests:

```java
client.get()
        .uri("/documents/42")
        .ifNoneMatch("\"version-7\"")
        .retrieve()
        .bodyToMono(Document.class);
```

Or:

```java
client.get()
        .uri("/documents/42")
        .ifModifiedSince(
                ZonedDateTime.parse("2026-10-01T00:00:00Z"))
        .retrieve()
        .toBodilessEntity();
```

The server may return `304 Not Modified` if the resource has not changed according to the validator. This is the HTTP cache validation mechanism; it does not replace application-side response caching.

### 4.6. Headers You Should Not Set Arbitrarily

Typically do not manually set `Host`, `Content-Length`, `Connection`, or hop-by-hop headers. The HTTP connector is responsible for computing and managing transport-related headers. Only customize them when explicitly required by a server/proxy and once you understand the impact on framing, connection reuse, and streaming.

Header names are case-insensitive in HTTP. However, do not assume all header values are case-insensitive; follow the semantics of each specific header.

## 5. Cookies: Sending Session or State per Request

Cookies are name/value pairs sent in the `Cookie` request header. In WebClient, use `cookie(...)` or `cookies(...)`:

```java
client.get()
        .uri("/account")
        .cookie("SESSION", "session-token-value")
        .retrieve()
        .bodyToMono(Account.class);
```

Multiple cookies:

```java
client.get()
        .uri("/preferences")
        .cookies(cookies -> {
            cookies.add("locale", "vi-VN");
            cookies.add("theme", "dark");
        })
        .retrieve()
        .bodyToMono(Preferences.class);
```

Use `cookie(name, value)` for a single specific cookie; use `cookies(Consumer<MultiValueMap<String, String>>)` when you need to add, replace, or remove multiple cookies in the same request.

### 5.1. Default Cookies

```java
WebClient client = WebClient.builder()
        .baseUrl("https://portal.example.com")
        .defaultCookie("client-locale", "vi-VN")
        .build();
```

A default cookie is only added if the request does not already have a cookie with the same name. A specific request can provide its own value:

```java
client.get()
        .uri("/settings")
        .cookie("client-locale", "en-US")
        .retrieve()
        .bodyToMono(Settings.class);
```

Do not set a user's session cookie as a default cookie on a shared singleton WebClient. User sessions must be passed per request or managed by an appropriately scoped cookie store.

### 5.2. `Cookie` and `Set-Cookie` Are Two Different Directions

- Requests send `Cookie: SESSION=...` to supply existing cookies.
- Responses send `Set-Cookie: SESSION=...; Path=/; HttpOnly; Secure; SameSite=Lax` to instruct the client to store/update cookies.

`WebClient.cookie(...)` sets outgoing cookies. Attributes like `HttpOnly`, `Secure`, `SameSite`, `Domain`, `Path`, and `Expires` belong to the `Set-Cookie` directive returned by the server; they are not attributes sent back in the `Cookie` request header.

If session state must persist across multiple requests, the application must decide how to store and resend cookies received from `Set-Cookie`. Do not assume WebClient's fluent API automatically provides a portable browser cookie jar across every `ClientHttpConnector`. You can manage cookies in an application/session store or configure the dedicated cookie store of the underlying HTTP connector.

### 5.3. Cookies Are Not Arbitrary Storage for All Data

Cookies can be sent on every request to a matching domain/path. Avoid stuffing large payloads or unnecessary sensitive data into cookies. Session cookies usually contain a random session identifier; actual session data is managed on the server or in a session store.

If the server uses cookies for authentication, follow the server's policy. For browser-facing applications, the server should set `Secure`, `HttpOnly`, and `SameSite` appropriately. `WebClient` is a backend HTTP client; sending cookies does not automatically create server-side protective attributes.

## 6. Basic Authentication

HTTP Basic Authentication transmits a username and password in a header:

```http
Authorization: Basic base64(username:password)
```

Base64 is only encoding, not cryptographic encryption. Only use Basic Authentication over HTTPS/TLS.

### 6.1. Setting per Request

```java
client.get()
        .uri("/private/profile")
        .headers(headers ->
                headers.setBasicAuth("demo-user", "demo-password"))
        .retrieve()
        .bodyToMono(Profile.class);
```

`HttpHeaders.setBasicAuth(username, password)` constructs the Authorization header using the Basic scheme.

### 6.2. Using a Filter for a Dedicated WebClient

Spring provides `ExchangeFilterFunctions.basicAuthentication(...)`:

```java
WebClient basicClient = WebClient.builder()
        .baseUrl("https://legacy.example.com")
        .filter(ExchangeFilterFunctions.basicAuthentication(
                "demo-user", "demo-password"))
        .build();
```

Every request through this client will have the Basic authentication filter applied. Restrict the client to a trusted service/origin; do not use a client with default Basic credentials to call arbitrary URLs.

Do not hardcode usernames/passwords in source code. Read credentials from a secret manager or secure deployment configuration mechanism. Avoid logging the `Authorization` header or enabling HTTP wiretap configurations that might record credentials.

## 7. Bearer Tokens and API Keys

### 7.1. Per-Request Bearer Token

Bearer tokens are typically sent via a header:

```http
Authorization: Bearer access-token
```

Use the `HttpHeaders` helper:

```java
client.get()
        .uri("/api/private/orders")
        .headers(headers ->
                headers.setBearerAuth(accessToken))
        .retrieve()
        .bodyToFlux(Order.class);
```

A token is a credential granting resource access. Anyone possessing the token can use it within its scope and lifetime. Do not write tokens to logs, URL query strings, exception messages, or metric tags.

If the token varies per user/request, pass the token on that request or use the OAuth2 Client filter. Avoid storing dynamic tokens in default headers of a singleton client.

### 7.2. API Key in a Custom Header

Some services use an API key:

```java
client.get()
        .uri("/v1/metrics")
        .header("X-Api-Key", apiKey)
        .retrieve()
        .bodyToMono(Metrics.class);
```

The header name must follow the API provider's contract. Do not assume every API uses `X-Api-Key`; some services use different headers or custom schemes.

An API key is also a secret. Store it in a secret manager/environment config, restrict permissions, rotate periodically, and avoid sending it to untrusted hosts. Do not put keys in query strings because URLs frequently appear in access logs, proxy logs, tracing, and system history.

### 7.3. How Basic, Bearer, API Key, and Cookie Differ

| Mechanism | Where sent | Typical contents | Lifecycle management |
|---|---|---|---|
| Basic | `Authorization` | Encoded username/password | Static credentials or changed per policy |
| Bearer | `Authorization` | Access token | Time-limited; requires issuance/refresh via OAuth2 flow |
| API key | Custom header per contract | Key identifying application/client | Issued, scoped, and rotated secret |
| Session cookie | `Cookie` | Session identifier | Server manages session and cookie expiry |

Do not choose a scheme merely because it is easy to write. Use the mechanism supported by the target API and follow your system's credential policies.

## 8. Reactive OAuth2 Client with WebClient

When calling an API protected by OAuth2, the application typically needs to obtain an access token from an authorization server, attach the Bearer token to outbound requests, and manage expiration. Spring Security OAuth2 Client provides `ReactiveOAuth2AuthorizedClientManager` and `ServerOAuth2AuthorizedClientExchangeFilterFunction` to integrate with WebClient.

Add the Spring Boot dependency:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-client</artifactId>
</dependency>
```

Configure a client registration, for example using `client_credentials` for service-to-service communication:

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          inventory:
            provider: company-auth
            client-id: ${INVENTORY_CLIENT_ID}
            client-secret: ${INVENTORY_CLIENT_SECRET}
            authorization-grant-type: client_credentials
            scope: inventory.read
        provider:
          company-auth:
            token-uri: https://auth.example.com/oauth2/token
```

This is an illustrative configuration. Token URI, grant type, scope, and credentials must match the actual authorization server. Do not commit secrets to the repository.

Configure the WebClient filter:

```java
@Configuration
public class OAuthWebClientConfiguration {

    @Bean
    WebClient inventoryWebClient(
            ReactiveOAuth2AuthorizedClientManager authorizedClientManager) {

        ServerOAuth2AuthorizedClientExchangeFilterFunction oauth =
                new ServerOAuth2AuthorizedClientExchangeFilterFunction(
                        authorizedClientManager);

        return WebClient.builder()
                .baseUrl("https://inventory.example.com")
                .filter(oauth)
                .build();
    }
}
```

When calling the API, select the client registration:

```java
import static org.springframework.security.oauth2.client.web.reactive.function.client
        .ServerOAuth2AuthorizedClientExchangeFilterFunction.clientRegistrationId;

Mono<Item> item = inventoryWebClient.get()
        .uri("/items/{id}", "42")
        .attributes(clientRegistrationId("inventory"))
        .retrieve()
        .bodyToMono(Item.class);
```

The filter uses the authorized client manager to obtain an authorized client and places the access token in `Authorization: Bearer ...`. Issuance/refresh behavior depends on the configured grant type and provider. With `client_credentials`, the manager can acquire new access tokens according to token and provider lifecycles.

### OAuth2 Client vs. Propagating the Current Token

There are two distinct scenarios:

- **OAuth2 Client**: the application is actively authorized and obtains an access token to call another API. Use `ReactiveOAuth2AuthorizedClientManager` with `ServerOAuth2AuthorizedClientExchangeFilterFunction`.
- **Bearer token propagation**: the incoming request is already authenticated with a Bearer token and the application wants to forward that token to downstream services. Spring Security provides `ServerBearerExchangeFilterFunction` for this purpose.

Bearer propagation does not automatically refresh expired tokens. If authorization flows, token acquisition, and refresh are needed, use OAuth2 Client.

## 9. `ExchangeFilterFunction`: Applying Shared Behavior

`ExchangeFilterFunction` lets you intercept and modify outbound requests before they are sent, or observe responses after they are received. Filters fit shared metadata such as correlation IDs, client names, metrics, and authentication policies.

Example adding a header to every request of a client:

```java
ExchangeFilterFunction clientNameFilter =
        (request, next) -> {
            ClientRequest filtered = ClientRequest.from(request)
                    .headers(headers ->
                            headers.set("X-Client-Name", "billing-service"))
                    .build();

            return next.exchange(filtered);
        };

WebClient client = WebClient.builder()
        .baseUrl("https://billing.example.com")
        .filter(clientNameFilter)
        .build();
```

`ClientRequest.from(request)` creates a builder based on the current request. The filter modifies headers and calls `next.exchange(filtered)` to continue the filter chain and send the request.

### Filter Generating a Correlation ID

```java
ExchangeFilterFunction correlationFilter =
        (request, next) -> {
            String correlationId = UUID.randomUUID().toString();

            ClientRequest filtered = ClientRequest.from(request)
                    .headers(headers ->
                            headers.set("X-Correlation-Id", correlationId))
                    .build();

            return next.exchange(filtered);
        };
```

In applications with tracing, integrate Micrometer Observation/Tracing or existing context propagation instead of generating an isolated correlation ID unrelated to the trace. The example above only illustrates how to mutate a request.

### Filters Must Preserve Reactive Composition

`ExchangeFilterFunction.filter` returns `Mono<ClientResponse>`. Return the publisher from `next.exchange(...)` and compose the necessary operators. Never call `.subscribe()` or `.block()` inside a filter.

If a filter reads the response body to decide on a retry or token refresh, it must consume or release the body properly before sending the next request. Otherwise, connections/buffers may be held. Spring documentation shows handling 401 and calling `response.releaseBody()` before retrying.

### Filter Ordering

Multiple filters can be registered on the builder:

```java
WebClient client = WebClient.builder()
        .filter(correlationFilter)
        .filter(clientNameFilter)
        .filter(authenticationFilter)
        .build();
```

Filters form a chain. Order filters according to what subsequent filters need to read. Avoid filters that log all headers because they may record `Authorization`, session cookies, or API keys.

A built `WebClient` is immutable. Use `mutate()` to create a new client if you need to change the filter list or configuration.

## 10. Per-Request or Default Headers, Cookies, and Authentication?

| Scope | API | When to use |
|---|---|---|
| Single request | `header`, `headers`, `cookie`, `cookies` | Specific tenant, user token, trace ID, or session |
| All requests of a client | `defaultHeader`, `defaultCookie` | Client name, default locale, or fixed headers |
| Cross-cutting request logic | `ExchangeFilterFunction` | Correlation, metrics, authentication integration |
| Managed credentials | OAuth2 filter | Access tokens acquired/refreshed per registration |

Example of a request with its own token and tenant:

```java
Mono<Order> order = client.get()
        .uri("/orders/{id}", "order-42")
        .headers(headers -> {
            headers.setBearerAuth(accessToken);
            headers.set("X-Tenant-Id", tenantId);
        })
        .cookie("SESSION", sessionCookie)
        .retrieve()
        .bodyToMono(Order.class);
```

Do not use default headers for credentials that vary by user. If a WebClient calls multiple hosts, do not attach sensitive credentials to every request of that client.

## 11. Handling Error Responses When Authentication Fails

`retrieve()` by default converts 4xx/5xx status responses into `WebClientResponseException` errors. You can handle 401/403 statuses explicitly:

```java
Mono<Profile> profile = client.get()
        .uri("/profile")
        .headers(headers ->
                headers.setBearerAuth(accessToken))
        .retrieve()
        .onStatus(
                status -> status.value() == 401,
                response -> response.createException())
        .onStatus(
                status -> status.value() == 403,
                response -> response.createException())
        .bodyToMono(Profile.class);
```

The example above preserves the exception from the response. If fallback or token refresh is needed, implement it in the OAuth2 authorized client manager/filter or a credential-aware mechanism. Do not loop requests infinitely upon receiving 401.

Common meanings:

- **401 Unauthorized**: credentials are missing, invalid, expired, or rejected; the API may require re-authentication.
- **403 Forbidden**: the server understands the identity/credentials but denies permission to perform the operation.

Some APIs use other statuses per their contract. Read the target service's documentation instead of treating these two statuses as universal rules.

## 12. Runnable Java 17+ Project: Testing Method, Headers, Cookies, and Auth

The small project below uses Spring Boot 3.3.5, Java 17, WebFlux, and OkHttp MockWebServer. MockWebServer runs a local HTTP server in tests, records received requests, and returns simulated responses. Tests do not need to call a real Internet API.

### 12.1. Structure

```text
webclient-request-metadata/
├── pom.xml
└── src/
    └── test/java/edu/demo/client/
        └── WebClientRequestTests.java
```

### 12.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>edu.demo</groupId>
    <artifactId>webclient-request-metadata</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <properties>
        <java.version>17</java.version>
        <okhttp.version>4.12.0</okhttp.version>
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
            <version>${okhttp.version}</version>
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
```

### 12.3. `WebClientRequestTests.java`

```java
package edu.demo.client;

import java.io.IOException;
import java.time.Duration;
import java.util.concurrent.TimeUnit;

import okhttp3.mockwebserver.MockResponse;
import okhttp3.mockwebserver.MockWebServer;
import okhttp3.mockwebserver.RecordedRequest;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.web.reactive.function.client.ExchangeFilterFunctions;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.core.publisher.Mono;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

class WebClientRequestTests {

    private MockWebServer server;
    private WebClient client;

    @BeforeEach
    void setUp() throws IOException {
        server = new MockWebServer();
        server.start();

        client = WebClient.builder()
                .baseUrl(server.url("/").toString())
                .build();
    }

    @AfterEach
    void tearDown() throws IOException {
        server.shutdown();
    }

    @Test
    void sendsMethodHeadersBearerTokenAndCookie() throws Exception {
        server.enqueue(new MockResponse()
                .addHeader("Content-Type", "application/json")
                .setBody("""
                        {"id":"42","name":"Keyboard"}
                        """));

        String body = """
                {"name":"Keyboard"}
                """;

        String response = client.method(HttpMethod.PATCH)
                .uri("/items/{id}", "42")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_JSON)
                .header("X-Trace-Id", "trace-123")
                .headers(headers ->
                        headers.setBearerAuth("test-access-token"))
                .cookie("SESSION", "session-abc")
                .bodyValue(body)
                .retrieve()
                .bodyToMono(String.class)
                .block(Duration.ofSeconds(3));

        assertNotNull(response);
        assertTrue(response.contains("Keyboard"));

        RecordedRequest request =
                server.takeRequest(2, TimeUnit.SECONDS);

        assertNotNull(request);
        assertEquals("PATCH", request.getMethod());
        assertEquals("/items/42", request.getPath());
        assertEquals("trace-123",
                request.getHeader("X-Trace-Id"));
        assertEquals("Bearer test-access-token",
                request.getHeader(HttpHeaders.AUTHORIZATION));
        assertEquals("application/json",
                request.getHeader(HttpHeaders.CONTENT_TYPE));
        assertEquals("application/json",
                request.getHeader(HttpHeaders.ACCEPT));
        assertTrue(request.getHeader("Cookie")
                .contains("SESSION=session-abc"));
    }

    @Test
    void requestValuesTakePrecedenceOverDefaults() throws Exception {
        server.enqueue(new MockResponse()
                .addHeader("Content-Type", "text/plain")
                .setBody("ok"));

        WebClient withDefaults = WebClient.builder()
                .baseUrl(server.url("/").toString())
                .defaultHeader("X-Client-Name", "default-client")
                .defaultCookie("locale", "vi-VN")
                .build();

        withDefaults.get()
                .uri("/settings")
                .header("X-Client-Name", "request-client")
                .cookie("locale", "en-US")
                .retrieve()
                .bodyToMono(String.class)
                .block(Duration.ofSeconds(3));

        RecordedRequest request =
                server.takeRequest(2, TimeUnit.SECONDS);

        assertNotNull(request);
        assertEquals("request-client",
                request.getHeader("X-Client-Name"));

        String cookie = request.getHeader("Cookie");
        assertNotNull(cookie);
        assertTrue(cookie.contains("locale=en-US"));
        assertTrue(!cookie.contains("locale=vi-VN"));
    }

    @Test
    void basicAuthenticationFilterCreatesAuthorizationHeader()
            throws Exception {

        server.enqueue(new MockResponse()
                .addHeader("Content-Type", "text/plain")
                .setBody("authenticated"));

        WebClient basicClient = WebClient.builder()
                .baseUrl(server.url("/").toString())
                .filter(ExchangeFilterFunctions.basicAuthentication(
                        "demo-user", "demo-password"))
                .build();

        basicClient.get()
                .uri("/private")
                .retrieve()
                .bodyToMono(String.class)
                .block(Duration.ofSeconds(3));

        RecordedRequest request =
                server.takeRequest(2, TimeUnit.SECONDS);

        assertNotNull(request);
        assertEquals(
                "Basic ZGVtby11c2VyOmRlbW8tcGFzc3dvcmQ=",
                request.getHeader(HttpHeaders.AUTHORIZATION));
    }
}
```

The tests use `block(Duration)` to synchronize assertions in JUnit. This is a test boundary; reactive code in production applications should compose publishers instead of blocking.

### 12.4. Running the Tests

From the directory containing `pom.xml`:

```bash
mvn test
```

Once Maven downloads dependencies and assertions hold, Surefire runs three tests:

1. The PATCH request sends the expected URI, Content-Type, Accept, custom header, Bearer token, and session cookie.
2. Per-request header/cookie overrides the corresponding default values.
3. The Basic authentication filter constructs the expected Authorization header.

MockWebServer records the actual requests that passed through the HTTP connector, so the tests verify both how WebClient builds requests and how the connector sends them.

### 12.5. Equivalent Request Example with curl

```bash
curl -i -X PATCH "https://inventory.example.com/items/42" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  -H "X-Trace-Id: trace-123" \
  -H "Authorization: Bearer ACCESS_TOKEN" \
  -H "Cookie: SESSION=session-abc" \
  -d '{"name":"Keyboard"}'
```

`ACCESS_TOKEN` and the session cookie in the example are illustrative values only. Never put real credentials into shell history, public documentation, or logs.

## 13. Common Mistakes and How to Fix Them

| Mistake | Consequence | Fix |
|---|---|---|
| Confusing `Accept` with `Content-Type` | Client describes sent/received formats incorrectly | `Content-Type` for outgoing body; `Accept` for desired response |
| Using repeated `header()` for `Authorization` | Can produce multiple invalid Authorization values | Use `headers(h -> h.setBearerAuth(...))` or `setBasicAuth(...)` |
| Thinking `defaultHeader` always overrides request headers | Request-specific headers fail to behave as intended | Defaults are only added if the request lacks that header |
| Putting user tokens in `defaultHeader` of a shared client | Credentials can be sent across users/requests/hosts | Set tokens per request or use an OAuth2 filter |
| Sending cookies by manually concatenating `Cookie` strings | Prone to encoding errors or duplicate values | Use `cookie()`/`cookies()` |
| Confusing `Set-Cookie` with `Cookie` | Fails to manage cookie lifecycle properly | Read response `Set-Cookie`, then store/resend per cookie-store policy |
| Thinking WebClient automatically maintains sessions like a browser | Subsequent requests may lack session cookies | Manage a cookie store explicitly or pass cookies per request |
| Using Basic Auth over plain HTTP | Username/password can be read in transit | Use HTTPS/TLS |
| Putting Bearer tokens or API keys in URLs | Credentials may appear in logs/history/tracing | Use Authorization/custom headers per contract |
| Hardcoding secrets in Java | Secrets leak via source or artifacts | Use a secret manager/environment configuration |
| Logging all headers | Logs may contain Authorization and session cookies | Mask/strip credentials before logging |
| Using a client with default credentials to call arbitrary URIs | Credentials may be sent to other hosts | Restrict base URL and client scope |
| Manually setting Content-Length/Host unnecessarily | Can break framing or connector behavior | Let the HTTP connector manage transport headers |
| Subscribing manually inside a filter | Detaches the request from the reactive lifecycle | Return the publisher from `next.exchange(...)` |
| Retrying POST without idempotency | Can cause duplicate side effects | Use idempotency keys and retry policies per API contract |
| Treating 401 and 403 as identical | Misdirects handling of credentials vs. permissions | Distinguish authentication failure from authorization denial |

## 14. Pre-Flight Checklist Before Calling External APIs

- Does the HTTP method match the endpoint's contract and semantics?
- Are path variables/query parameters encoded by the URI builder?
- Does the request body have the appropriate `Content-Type`?
- Does `Accept` list representations the client can read?
- Which headers are defaults and which must vary per request?
- Is `set(...)` used for single-value headers like Authorization?
- Does the session cookie match the right user/request?
- Is receiving, storing, and resending `Set-Cookie` understood?
- Are Basic credentials, Bearer tokens, and API keys loaded from proper secret storage?
- Are credentials kept out of URLs and logs?
- Can WebClient be used to call untrusted hosts while carrying default credentials?
- Does OAuth2 Client have the correct registration, provider, scope, and grant type?
- Is token acquisition/refresh managed by Spring Security's authorized client manager?
- Are 401/403 statuses and error response bodies checked?
- Are retries safe with respect to method and side effects?
- Are real requests tested using MockWebServer or an equivalent test server?

## 15. Self-Check Exercises

**Exercise 1.** When sending JSON with WebClient, which header describes the body format and which describes the desired response?

**Answer:** `Content-Type` describes the outgoing body; `Accept` describes the response representation the client accepts.

**Exercise 2.** To select a method from an `HttpMethod method` variable, which API do you call?

**Answer:** `client.method(method)`, then continue configuring URI, headers, and body if the method carries a body.

**Exercise 3.** What can `header("X-Mode", "a")` followed by `header("X-Mode", "b")` produce?

**Answer:** Two header values are added according to header semantics. If you want to replace the value, use `headers(h -> h.set("X-Mode", "b"))`.

**Exercise 4.** Does `defaultHeader("X-Client", "default")` override an `X-Client` already set on the request?

**Answer:** No. A default header is only added if the request does not already have that header.

**Exercise 5.** Why should you not use Basic Authentication over plain HTTP?

**Answer:** Basic only Base64-encodes the username/password string; Base64 is not encryption. HTTPS/TLS is needed to protect credentials in transit.

**Exercise 6.** Where should a Bearer token be sent?

**Answer:** In `Authorization: Bearer ...`, which can be set with `headers(h -> h.setBearerAuth(token))`.

**Exercise 7.** How do `Set-Cookie` and `Cookie` differ?

**Answer:** The server returns `Set-Cookie` to instruct the client to store a cookie; the client sends `Cookie` in later requests to supply stored cookies.

**Exercise 8.** How does the OAuth2 Client filter differ from setting a Bearer token manually?

**Answer:** Setting a token manually only sends an existing credential. The OAuth2 Client filter integrates with the authorized client manager to acquire and manage tokens per registration/grant/provider.

**Exercise 9.** What kind of work is `ExchangeFilterFunction` suited for?

**Answer:** Shared behavior across outbound requests such as correlation metadata, client identity, authentication integration, or metrics.

**Exercise 10.** Why should you not log all request headers?

**Answer:** Headers can contain Authorization, API keys, and session cookies. Mask or strip credentials before logging.

## 16. Key Takeaways

- `WebClient` provides shortcuts for HTTP methods and `method(HttpMethod)` when the method is decided at runtime.
- `uri(...)` supports URI templates; `UriBuilder` helps build paths and query parameters with encoding.
- `Accept` specifies the desired response; `Content-Type` specifies the request body.
- `header(...)` appends values; `headers(...)` allows set/add/remove.
- `defaultHeader` and `defaultCookie` are only added if the request has not declared the corresponding value.
- `cookie()`/`cookies()` set outbound cookies; `Set-Cookie` is the directive returned by the server.
- Basic uses `setBasicAuth` or `ExchangeFilterFunctions.basicAuthentication`; use only over HTTPS.
- Bearer tokens use `setBearerAuth`; API keys use a custom header per the service's contract.
- Reactive OAuth2 Client uses `ReactiveOAuth2AuthorizedClientManager` and `ServerOAuth2AuthorizedClientExchangeFilterFunction`.
- `ExchangeFilterFunction` is suited for shared behavior and must preserve reactive composition.
- Credentials must be managed as secrets; do not place them in URLs, logs, or shared default clients outside trusted boundaries.
- Testing real requests with MockWebServer verifies method, URI, headers, cookies, and Authorization.

When debugging an outbound request, check in order: **method → URI → Content-Type/Accept → custom headers → cookies → Authorization → response status**. This order helps pinpoint which part of the request mismatches the target API's contract.

## Official Documentation

- Spring Framework 6.2, **WebClient**: https://docs.spring.io/spring-framework/reference/6.2/web/webflux-webclient.html
- Spring Framework 6.2, **WebClient Configuration**: https://docs.spring.io/spring-framework/reference/6.2/web/webflux-webclient/client-builder.html
- Spring Framework 6.2, **WebClient Filters**: https://docs.spring.io/spring-framework/reference/6.2/web/webflux-webclient/client-filter.html
- Spring Framework 6.2, **WebClient Attributes**: https://docs.spring.io/spring-framework/reference/6.2/web/webflux-webclient/client-attributes.html
- Spring Framework 6.2, **`WebClient.Builder` API**: https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/web/reactive/function/client/WebClient.Builder.html
- Spring Framework 6.2, **`WebClient.RequestHeadersSpec` API**: https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/web/reactive/function/client/WebClient.RequestHeadersSpec.html
- Spring Security, **OAuth2 WebFlux Client**: https://docs.spring.io/spring-security/reference/reactive/oauth2/
- Spring Security, **Reactive Bearer Token Propagation**: https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/bearer-tokens.html