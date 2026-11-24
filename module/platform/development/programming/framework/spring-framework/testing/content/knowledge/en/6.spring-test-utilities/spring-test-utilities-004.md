# MockServerHttpRequest, MockServerHttpResponse and MockServerWebExchange

When testing Spring WebFlux applications, many components process requests and responses in a reactive model without running a real HTTP server. To test these components at the unit test level, Spring Test provides three important mock objects: `MockServerHttpRequest`, `MockServerHttpResponse`, and `MockServerWebExchange`.

These three classes let you construct an HTTP request in memory, observe the response written out, and place both inside an exchange identical to the object WebFlux passes through `WebFilter` and `WebHandler` instances. As a result, you can test processing logic at the WebFlux layer directly with JUnit without opening ports, sending requests over the network, or starting the whole application.

## 1. Roles of the three mock objects

In WebFlux, `ServerHttpRequest` represents the server-side request, `ServerHttpResponse` represents the server-side response, and `ServerWebExchange` bundles the request, response, and context of a single HTTP exchange.

| Mock class | Package | Simulates | When to use |
|---|---|---|---|
| `MockServerHttpRequest` | `org.springframework.mock.http.server.reactive` | A reactive server request | Creating input method, URI, headers, cookies, and body |
| `MockServerHttpResponse` | `org.springframework.mock.http.server.reactive` | A reactive server response | Setting status, headers, cookies, and inspecting written body |
| `MockServerWebExchange` | `org.springframework.mock.web.server` | A complete HTTP exchange | Testing `WebFilter`, `WebHandler`, and components accepting `ServerWebExchange` |

These classes belong to the `spring-test` module. They implement Spring WebFlux contracts, so production code can accept `ServerHttpRequest`, `ServerHttpResponse`, or `ServerWebExchange` interfaces while tests pass in mock implementations without modifying production code.

The processing flow can be visualized as follows:

```text
MockServerHttpRequest
          |
          v
   MockServerWebExchange
       /          \
      v            v
 request        response
                  |
                  v
        MockServerHttpResponse
                  ^
                  |
       WebFilter / WebHandler
```

`MockServerWebExchange` holds both request and response. In most tests, you only need to build the request and call `MockServerWebExchange.from(request)` to get an exchange with an accompanying mock response.

## 2. Preparing test dependencies

If the application already uses Spring WebFlux, the reactive interfaces and Reactor are already present in the main dependencies. The mock classes live in `spring-test`, so you need the corresponding test dependency.

Example using Gradle Groovy DSL:

```groovy
dependencies {
    testImplementation("org.springframework:spring-test")
    testImplementation("org.springframework:spring-webflux")
    testImplementation("io.projectreactor:reactor-test")
}
```

In a real application, `spring-webflux` is usually already declared under `implementation`; there is no need to redeclare it in `testImplementation` if tests already receive it on the test runtime classpath. `reactor-test` is only needed when using `StepVerifier` or other Reactor testing utilities. Let the existing Spring BOM or dependency management keep Spring versions aligned.

If the project uses Spring Boot, `spring-boot-starter-test` typically already provides `spring-test` and JUnit Jupiter. The application still needs the WebFlux dependency when testing WebFlux reactive contracts.

Common imports:

```java
import org.springframework.http.HttpCookie;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.mock.http.server.reactive.MockServerHttpRequest;
import org.springframework.mock.http.server.reactive.MockServerHttpResponse;
import org.springframework.mock.web.server.MockServerWebExchange;
import org.springframework.web.server.ServerWebExchange;
```

## 3. Creating requests with MockServerHttpRequest

`MockServerHttpRequest` provides factory methods to create requests with common HTTP methods. After configuring properties, call `build()` to create the request object.

### 3.1. Creating a simple GET request

```java
MockServerHttpRequest request = MockServerHttpRequest
        .get("/api/orders/42")
        .build();
```

Basic information can be read via the `ServerHttpRequest` contract:

```java
assertEquals(HttpMethod.GET, request.getMethod());
assertEquals("/api/orders/42", request.getURI().getPath());
```

A mock request does not send data over a socket. The URI is simply request metadata seen by the component under test.

### 3.2. Configuring method, URI, and query parameters

You can build a request with an explicit method when testing a less common HTTP method:

```java
MockServerHttpRequest request = MockServerHttpRequest
        .method(HttpMethod.PATCH, "/api/orders/42?notify=false")
        .build();
```

The query string is parsed into a `MultiValueMap`:

```java
assertEquals("false", request.getQueryParams().getFirst("notify"));
```

When multiple values share the same name, such as `?tag=java&tag=spring`, `getQueryParams()` retains the values in a list. Tests should verify the exact rule the controller or filter needs: taking the first value, handling all values, or rejecting duplicate parameters.

### 3.3. Adding headers and cookies

Headers can be added via the builder:

```java
MockServerHttpRequest request = MockServerHttpRequest
        .get("/api/profile")
        .header("X-Request-Id", "req-100")
        .header("X-Feature", "preview")
        .build();

assertEquals("req-100", request.getHeaders().getFirst("X-Request-Id"));
```

To add a cookie, use `HttpCookie`:

```java
MockServerHttpRequest request = MockServerHttpRequest
        .get("/api/profile")
        .cookie(new HttpCookie("SESSION", "session-value"))
        .build();

assertEquals("session-value", request.getCookies()
        .getFirst("SESSION").getValue());
```

Headers and cookies are separate mechanisms. Request cookies are sent in the `Cookie` header, yet Spring provides a cookie API so tests and application code can work by name/value without parsing header strings manually.

### 3.4. Creating a request with a body

For POST, PUT, or PATCH, you can set the content type and body directly on the builder:

```java
MockServerHttpRequest request = MockServerHttpRequest
        .post("/api/orders")
        .contentType(MediaType.APPLICATION_JSON)
        .header("X-Request-Id", "req-101")
        .body("""
                {
                  "productId": 42,
                  "quantity": 2
                }
                """);
```

`body(String)` creates a text body for the mock request. If you need to test binary content or a special encoding, build a `DataBuffer` matching the data type and content type being simulated.

Request metadata can be verified as follows:

```java
assertEquals(HttpMethod.POST, request.getMethod());
assertEquals(MediaType.APPLICATION_JSON, request.getHeaders().getContentType());
assertEquals("req-101", request.getHeaders().getFirst("X-Request-Id"));
```

The body is exposed via `getBody()` as a `Flux<DataBuffer>`, not a synchronous `String`. When a test needs to read the body directly, it must subscribe to or collect the publisher and release the `DataBuffer` after reading.

### 3.5. Reading the request body safely

The following example joins the body into a single `DataBuffer`, reads the bytes, and releases the buffer:

```java
import java.nio.charset.StandardCharsets;

import org.springframework.core.io.buffer.DataBuffer;
import org.springframework.core.io.buffer.DataBufferUtils;
import org.springframework.http.server.reactive.ServerHttpRequest;

private String readBody(ServerHttpRequest request) {
    DataBuffer buffer = DataBufferUtils.join(request.getBody()).block();
    if (buffer == null) {
        return "";
    }

    try {
        byte[] bytes = new byte[buffer.readableByteCount()];
        buffer.read(bytes);
        return new String(bytes, StandardCharsets.UTF_8);
    } finally {
        DataBufferUtils.release(buffer);
    }
}
```

In a test:

```java
assertTrue(readBody(request).contains("\"productId\": 42"));
```

`DataBufferUtils.join` combines the buffers in the publisher into a single composite buffer. You must release the buffer after reading to avoid resource leaks, especially when implementations use pooled buffers. For a request body handled by a real handler, it is generally best to let the handler read the body rather than having the test consume it beforehand, since the body is a stream that may not be replayable.

### 3.6. Other request properties

Depending on the test case, the request builder can also simulate additional details such as remote/local addresses, SSL metadata, and context path. These properties are helpful when testing logic that depends on client address, security protocol, or application path.

Do not populate every header, cookie, or address in every test. Configure only the data that affects the behavior under test; the smaller the fixture, the easier it is to identify why a failure happened.

## 4. Using MockServerHttpResponse to observe responses

`MockServerHttpResponse` is a mock implementation of `ServerHttpResponse`. Usually, you obtain the response from the exchange to ensure the request and response belong to the same exchange.

```java
MockServerWebExchange exchange = MockServerWebExchange.from(
        MockServerHttpRequest.get("/api/orders").build());

MockServerHttpResponse response = exchange.getResponse();
```

### 4.1. Checking status and headers

The response can be configured using `ServerHttpResponse` APIs:

```java
response.setStatusCode(HttpStatus.CREATED);
response.getHeaders().setContentType(MediaType.APPLICATION_JSON);
response.getHeaders().set("X-Request-Id", "req-101");

assertEquals(HttpStatus.CREATED, response.getStatusCode());
assertEquals(MediaType.APPLICATION_JSON, response.getHeaders().getContentType());
assertEquals("req-101", response.getHeaders().getFirst("X-Request-Id"));
```

In recent Spring versions, the return type of `getStatusCode()` is `HttpStatusCode`; `HttpStatus` is a concrete implementation. You can compare directly against the corresponding `HttpStatus` constant.

### 4.2. Writing a reactive body

The response body is written using a `DataBuffer` publisher. For example:

```java
import java.nio.charset.StandardCharsets;

import reactor.core.publisher.Mono;

response.setStatusCode(HttpStatus.OK);
response.getHeaders().setContentType(MediaType.TEXT_PLAIN);

byte[] bytes = "order accepted".getBytes(StandardCharsets.UTF_8);
Mono<Void> writeResult = response.writeWith(
        Mono.just(response.bufferFactory().wrap(bytes)));

writeResult.block();
```

In unit tests, calling `block()` at the test boundary waits for the reactive operation to finish before making assertions. Do not carry this practice into production WebFlux code; in the application, continue returning and composing `Mono`/`Flux` to keep the flow non-blocking.

### 4.3. Reading the written body

`MockServerHttpResponse` provides the `getBodyAsString()` utility to retrieve the body content as a `Mono<String>`:

```java
String body = response.getBodyAsString().block();

assertEquals("order accepted", body);
```

Set the appropriate content type/charset if the body does not use UTF-8 by default. For JSON, you can inspect the JSON string, parse it into a DTO, or use JSON assertions appropriate to your project. Avoid comparing the entire raw string if field ordering or whitespace is not part of the response contract.

### 4.4. Checking cookies in the response

Response cookies are represented by `ResponseCookie`:

```java
import org.springframework.http.ResponseCookie;

response.addCookie(ResponseCookie.from("SESSION", "new-session")
        .httpOnly(true)
        .secure(true)
        .path("/")
        .build());

ResponseCookie cookie = response.getCookies().getFirst("SESSION");
assertNotNull(cookie);
assertTrue(cookie.isHttpOnly());
assertTrue(cookie.isSecure());
assertEquals("/", cookie.getPath());
```

Cookies can carry security attributes such as `HttpOnly`, `Secure`, `SameSite`, `Path`, and `Max-Age`. When testing session or authentication behavior, verify the attributes required by application policy. Do not merely check that the cookie exists while ignoring security flags.

### 4.5. Completing a response without a body

For an empty response, you can call `setComplete()`:

```java
response.setStatusCode(HttpStatus.NO_CONTENT);
response.setComplete().block();

assertEquals(HttpStatus.NO_CONTENT, response.getStatusCode());
```

This is how you simulate an endpoint returning `204 No Content` or a filter completing the response without writing a body. If the contract requires an empty body, you can check the body after completion using the mock response API.

## 5. Combining request and response with MockServerWebExchange

`MockServerWebExchange` implements `ServerWebExchange`, the central object passed through WebFlux. It holds the request, response, and additional context such as attributes, session, and principal.

### 5.1. Creating an exchange from a request

The simplest way:

```java
MockServerHttpRequest request = MockServerHttpRequest
        .get("/api/orders/42")
        .header("X-Request-Id", "req-102")
        .build();

MockServerWebExchange exchange = MockServerWebExchange.from(request);
```

Then both sides can be accessed:

```java
assertEquals("/api/orders/42", exchange.getRequest().getURI().getPath());
assertNotNull(exchange.getResponse());
```

`from(request)` creates a mock exchange with a response and the default supporting components needed for many simple tests. If a test needs a custom session manager, principal, or locale context, you can use `MockServerWebExchange`'s builder to supply configuration matching the Spring version in use.

### 5.2. Exchange attributes

`ServerWebExchange` has an attributes map so filters and handlers can share data within a single request. Tests can set or check attributes:

```java
exchange.getAttributes().put("tenantId", "tenant-42");

assertEquals("tenant-42", exchange.getAttribute("tenantId"));
```

A `WebFilter` can put a correlation id, tenant, tracing info, or locale resolution result into attributes. When testing, verify the key and value actually used by downstream handlers, avoiding dependence on an internal attribute outside the component's contract.

### 5.3. WebSession

The exchange provides the session via `getSession()`, returning `Mono<WebSession>`. Tests can await session creation and inspect attributes:

```java
WebSession session = exchange.getSession().block();
assertNotNull(session);

session.getAttributes().put("userId", "user-42");

WebSession sameSession = exchange.getSession().block();
assertEquals("user-42", sameSession.getAttribute("userId"));
```

Because the session is reactive, it is not retrieved directly as a synchronous object from the exchange. When a test needs to verify session storage or session id issuance, also consider the session manager/store and response cookies according to your specific configuration.

### 5.4. Principal and locale context

`ServerWebExchange` provides the principal via `getPrincipal()` as a `Mono`. In tests, you can use the exchange builder to configure an appropriate principal or test a filter with an exchange that already has a principal set.

Locale context is accessed via `getLocaleContext()`. If logic depends on locale, fix the locale in the test and restore any thread-local state once finished. Never let tests depend on the host machine's default locale.

### 5.5. Form data and multipart data

The exchange also exposes reactive APIs for accessing form data and multipart data:

- `getFormData()` returns `Mono<MultiValueMap<String, String>>`.
- `getMultipartData()` returns `Mono<MultiValueMap<String, Part>>`.

These APIs may require corresponding body readers/codecs. When the goal is to test parsing or controller binding, make sure the test uses codec configuration matching the scope being verified. `MockServerWebExchange` creates an in-memory HTTP exchange environment, but it does not automatically prove that all codecs or configurations of the real application are registered.

## 6. Testing WebFilter with a mock exchange

A `WebFilter` accepts a `ServerWebExchange` and a `WebFilterChain`. It can read the request, add attributes/headers, short-circuit the request, or forward it to the next filter.

Example of a filter that copies a correlation id from the request to the response:

```java
import org.springframework.http.HttpStatus;
import org.springframework.util.StringUtils;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;

import reactor.core.publisher.Mono;

public class CorrelationIdWebFilter implements WebFilter {

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange, WebFilterChain chain) {

        String correlationId = exchange.getRequest()
                .getHeaders().getFirst("X-Correlation-Id");

        if (!StringUtils.hasText(correlationId)) {
            exchange.getResponse().setStatusCode(HttpStatus.BAD_REQUEST);
            return exchange.getResponse().setComplete();
        }

        exchange.getAttributes().put("correlationId", correlationId);
        exchange.getResponse().getHeaders()
                .set("X-Correlation-Id", correlationId);

        return chain.filter(exchange);
    }
}
```

A unit test can supply a stub `WebFilterChain` as a lambda. The chain only needs to return a `Mono<Void>` and can record that it was invoked:

```java
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;
import org.springframework.mock.http.server.reactive.MockServerHttpRequest;
import org.springframework.mock.web.server.MockServerWebExchange;
import org.springframework.web.server.WebFilterChain;

import java.util.concurrent.atomic.AtomicBoolean;

import static org.junit.jupiter.api.Assertions.*;

class CorrelationIdWebFilterTest {

    private final CorrelationIdWebFilter filter = new CorrelationIdWebFilter();

    @Test
    void copiesCorrelationIdAndContinuesChain() {
        var request = MockServerHttpRequest.get("/api/orders")
                .header("X-Correlation-Id", "trace-42")
                .build();
        var exchange = MockServerWebExchange.from(request);
        var chainCalled = new AtomicBoolean(false);

        WebFilterChain chain = nextExchange -> {
            chainCalled.set(true);
            nextExchange.getResponse().setStatusCode(HttpStatus.OK);
            return nextExchange.getResponse().setComplete();
        };

        filter.filter(exchange, chain).block();

        assertTrue(chainCalled.get());
        assertEquals("trace-42", exchange.getAttribute("correlationId"));
        assertEquals("trace-42", exchange.getResponse()
                .getHeaders().getFirst("X-Correlation-Id"));
        assertEquals(HttpStatus.OK, exchange.getResponse().getStatusCode());
    }

    @Test
    void rejectsRequestWithoutCorrelationId() {
        var request = MockServerHttpRequest.get("/api/orders").build();
        var exchange = MockServerWebExchange.from(request);
        var chainCalled = new AtomicBoolean(false);
        WebFilterChain chain = nextExchange -> {
            chainCalled.set(true);
            return nextExchange.getResponse().setComplete();
        };

        filter.filter(exchange, chain).block();

        assertFalse(chainCalled.get());
        assertEquals(HttpStatus.BAD_REQUEST, exchange.getResponse().getStatusCode());
    }
}
```

The first test verifies that the filter reads the header properly, sets the attribute, writes the response header, and delegates to the chain. The second test confirms that a request missing the required data is rejected before the chain is called. These two cases represent the two main behavioral branches of the filter.

If you want to verify the publisher without calling `block()`, you can use `StepVerifier`:

```java
StepVerifier.create(filter.filter(exchange, chain))
        .verifyComplete();
```

`StepVerifier` is well suited for checking completion, errors, or signal ordering of a `Mono`/`Flux`. For a filter that only returns `Mono<Void>`, `verifyComplete()` confirms the stream finishes normally.

## 7. Testing WebHandler

`WebHandler` is WebFlux's low-level exchange-handling contract. It accepts a `ServerWebExchange` and returns a `Mono<Void>` upon completion.

Example handler returning text:

```java
import java.nio.charset.StandardCharsets;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebHandler;

import reactor.core.publisher.Mono;

public class HealthWebHandler implements WebHandler {

    @Override
    public Mono<Void> handle(ServerWebExchange exchange) {
        exchange.getResponse().setStatusCode(HttpStatus.OK);
        exchange.getResponse().getHeaders().setContentType(MediaType.TEXT_PLAIN);

        byte[] body = "healthy".getBytes(StandardCharsets.UTF_8);
        return exchange.getResponse().writeWith(
                Mono.just(exchange.getResponse().bufferFactory().wrap(body)));
    }
}
```

Handler test:

```java
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;
import org.springframework.mock.http.server.reactive.MockServerHttpRequest;
import org.springframework.mock.web.server.MockServerWebExchange;

import static org.junit.jupiter.api.Assertions.assertEquals;

class HealthWebHandlerTest {

    @Test
    void writesHealthResponse() {
        var exchange = MockServerWebExchange.from(
                MockServerHttpRequest.get("/health").build());

        new HealthWebHandler().handle(exchange).block();

        assertEquals(HttpStatus.OK, exchange.getResponse().getStatusCode());
        assertEquals("healthy", exchange.getResponse().getBodyAsString().block());
    }
}
```

Here, the handler is invoked directly, so the test focuses on exchange-handling logic. If you need to verify routing, filter chains, codecs, exception handlers, or the application's WebFlux configuration, a broader integration test is required.

## 8. Testing components that depend on ServerWebExchange

It is not only `WebFilter` and `WebHandler` that use the exchange. Resolvers, security components, locale handlers, and utility logic can accept `ServerWebExchange` to access the request, session, principal, or attributes.

An example component that reads a tenant id from a header and returns it from the exchange:

```java
public class TenantResolver {

    public String resolve(ServerWebExchange exchange) {
        String tenantId = exchange.getRequest()
                .getHeaders().getFirst("X-Tenant-Id");

        if (tenantId == null || tenantId.isBlank()) {
            throw new IllegalArgumentException("Tenant id is required");
        }

        return tenantId.trim();
    }
}
```

Tests can build exchanges with different headers:

```java
@Test
void trimsTenantId() {
    var exchange = MockServerWebExchange.from(
            MockServerHttpRequest.get("/resource")
                    .header("X-Tenant-Id", " tenant-a ")
                    .build());

    assertEquals("tenant-a", new TenantResolver().resolve(exchange));
}

@Test
void rejectsMissingTenantId() {
    var exchange = MockServerWebExchange.from(
            MockServerHttpRequest.get("/resource").build());

    assertThrows(IllegalArgumentException.class,
            () -> new TenantResolver().resolve(exchange));
}
```

For components that only read data from the exchange, this approach is usually enough. If the component also depends on beans, security context, or preceding filters, the test should provide the right dependencies or use a small context to simulate the integration chain.

## 9. Distinguishing mock exchange from MockMvc and WebTestClient

Spring has several web testing tools. They serve different layers and do not completely replace one another.

| Tool | Foundation | Appropriate scope |
|---|---|---|
| `MockServerHttpRequest` / `MockServerHttpResponse` / `MockServerWebExchange` | WebFlux reactive | Unit testing filters, handlers, or components working directly with reactive server contracts |
| `MockMvc` | Spring MVC / Servlet | Testing MVC controllers through `DispatcherServlet` in a mock Servlet environment |
| `WebTestClient` | WebFlux and usable with MVC | Client-level HTTP testing; can bind to controllers, an application context, or a real server |

Do not use `MockServerWebExchange` to replace Spring MVC's `MockHttpServletRequest`. The two APIs reflect two different server contracts: Servlet is a synchronous request/response model based on the Servlet API; WebFlux uses `ServerHttpRequest`, `ServerHttpResponse`, and reactive streams.

`WebTestClient` is suitable when you want to send requests in a way closer to an HTTP client and verify responses with a fluent API. It can bind to controllers or a context without a real server, or connect to a live running server. Mock exchange is more suitable when you want to invoke a filter/handler directly and verify how the component manipulates the exchange.

Example selection decisions:

- Testing a filter that adds a header: use `MockServerWebExchange`.
- Testing a `WebHandler` writing status/body: use `MockServerWebExchange`.
- Testing WebFlux route mappings, serialization, and exception handling: consider `WebTestClient`.
- Testing Spring MVC controllers: use `MockMvc`.
- Testing behavior over sockets, server connectors, and a real network environment: use an appropriate test that starts a server.

## 10. Limitations to understand when using mock exchange

Mock exchange simulates WebFlux contracts in memory. It does not reproduce the entire behavior of server connectors or network infrastructure.

Points to keep in mind:

- There are no real sockets, real TLS handshakes, or real client connections.
- It does not automatically verify Netty, Reactor Netty, server timeout, or connection pool configuration.
- It does not automatically prove all route mappings, codecs, and filter chains of the application are registered properly.
- The request body is a reactive stream; consuming the body in a test before the handler runs can alter the behavior the handler observes.
- `DataBuffer` instances may need to be released properly when tests read or allocate buffers themselves.
- Session, principal, locale, and attributes must be set explicitly if logic depends on them.
- Default mock exchange settings may differ from production configuration for codecs, session stores, or security context.

Therefore, use mock exchange for unit tests and add integration tests in the right places to protect real configuration or infrastructure. There is no need to turn every test into an end-to-end server test; choose scope based on the behavior to verify.

## 11. Common pitfalls

**Using Servlet mocks for WebFlux by mistake.** `MockHttpServletRequest` belongs to Spring MVC/Servlet. Components accepting `ServerWebExchange` require the corresponding reactive mocks.

**Forgetting to call `build()` on the request builder.** `MockServerHttpRequest` factory methods return a builder; you must finish configuring and build before passing the request into an exchange.

**Not waiting for publishers to complete.** `writeWith`, `setComplete`, `getSession`, and many other APIs return `Mono`. If assertions run before the publisher finishes, the response or session may not yet be in the expected state. Use `StepVerifier` or await the publisher in tests.

**Calling `block()` in production code.** `block()` should only be used at synchronous test boundaries or inside appropriate tools. In production WebFlux pipelines, return publishers and compose reactive steps.

**Reading a DataBuffer without releasing it.** When tests read the body directly, manage the buffer lifecycle. Skipping release can cause memory leaks in implementations using pooled buffers.

**Reading the request body multiple times.** The body is a stream. If a test step already consumed the body, a downstream handler may have no data left. Let the component under test read the body or explicitly cache/replay according to production requirements.

**Asserting only response status.** A filter or handler can return the right status while returning wrong headers, cookies, or body. Verify all elements belonging to the contract.

**Assuming mock exchange verifies server configuration.** A unit test calling a filter directly does not prove the filter is registered in the chain. If registration is the target, test the configuration or use WebTestClient.

**Overcomplicating the exchange setup.** Only add session, principal, locale, multipart, or attributes when the behavior under test requires them. Minimal fixtures keep tests readable and low-dependency.

## 12. Workflow for building tests with the three mock classes

When testing a WebFlux component, you can follow this sequence:

1. Determine whether the component accepts `ServerHttpRequest`, `ServerHttpResponse`, or `ServerWebExchange`.
2. If only the request is needed, build a `MockServerHttpRequest` with the required method, URI, headers, cookies, and body.
3. If both request and response are needed, create `MockServerWebExchange.from(request)`.
4. Invoke the filter, handler, or component directly via the production interface it uses.
5. Await `Mono`/`Flux` completion using `StepVerifier` or `block()` at the test boundary.
6. Verify status, headers, cookies, body, attributes, session, or principal according to the contract.
7. If the test consumes `DataBuffer` itself, release the buffer and avoid draining the body before the component under test runs.
8. Add WebTestClient or integration tests when you need to verify routing, codecs, filter registration, or server connectors.

When used within their proper scope, `MockServerHttpRequest`, `MockServerHttpResponse`, and `MockServerWebExchange` keep WebFlux logic testing fast and focused. They let you construct exact HTTP conditions, observe reactive responses, and verify how filters/handlers interact with the exchange without starting a server for every unit test.
