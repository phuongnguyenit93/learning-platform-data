# MockMvc or HTTP Client for Gateway Server Web MVC

## 1. Why Distinguish `MockMvc` from a Real HTTP Client?

**Spring Cloud Gateway** typically serves as the entry point to microservices: choosing routes by path, method, or header; running filters to transform paths/headers; resolving services via `lb://`; and handling authentication, rate limiting, retries, circuit breaking, TLS, and observability. Even a tiny mistake at the edge can send malformed requests to multiple backends, leak user data, or return wrong HTTP statuses.

Specifically, **Spring Cloud Gateway Server Web MVC** runs on **Spring MVC, the Servlet API, and WebMvc.fn**. It does not share the reactive request lifecycle or `GatewayFilterChain.filter(exchange)` returning `Mono<Void>` of Gateway Server WebFlux. Choosing the right testing tool is therefore part of architectural design:

- **`MockMvc`** dispatches requests into Spring MVC using **mock Servlet requests/responses**, without opening a real inbound HTTP port. It excels at testing mappings, controllers, Servlet security, validation, statuses, and much of route/filter behavior.
- **An HTTP client connecting to a live port**, such as JDK `HttpClient`, `RestClient`, or another HTTP test client, sends requests over sockets to a **real Servlet container**. This is essential for verifying inbound HTTP transport, outbound proxying, TLS, encoding, streaming, cancellation, and reverse-proxy setup.
- **A backend stub** (fake HTTP server or mock server) verifies **what method/path/headers/body upstream actually received**, what status it returned, and how many times it was called.

Crucial point: **`MockMvc` does not automatically mock the Gateway's outbound HTTP client.** If Gateway MVC's `HandlerFunctions.http()` calls Catalog over the network, running `MockMvc` without a configured backend stub will still issue a real HTTP call and fail because no backend is listening.

This lesson, **"MockMvc or HTTP Client for Gateway Server Web MVC"**, belongs to the **Testing** chapter of the **SPRING_CLOUD_GATEWAY** module, aiming to turn route predicates, filter chains, rewrites/headers, discovery, security, retries, and TLS into **evidence-backed assertions at the right layer**.

### Learning Outcomes

After this lesson, learners will be able to:

1. Describe what `MockMvc` can verify and what only live HTTP integration tests can prove.
2. Distinguish `@WebMvcTest`, `@SpringBootTest(webEnvironment = MOCK)`, and `RANDOM_PORT`.
3. Use `@AutoConfigureMockMvc`, `MockMvc.perform(...)`, `@LocalServerPort`, and JDK `HttpClient` in the right contexts.
4. Build an HTTP backend stub with a **request counter/journal** to verify path rewrites, custom request headers, and attempt counts.
5. Assert both the **final client response** and the **actual request reaching the backend**, rather than only HTTP 200.
6. Design negative tests for **authentication, authorization, rate limiting, retry/idempotency, circuit breakers, TLS, and route misses**.
7. Avoid mixing WebFlux/reactive `WebTestClient` APIs improperly with MVC, while knowing when `WebTestClient` still works as a **network client**.
8. Isolate tests in CI, avoiding hardcoded ports, real tokens, live backends, or destructive tests against production.

> **Version scope:** Examples apply to **Gateway Server Web MVC** with compatible Spring Boot/Spring Cloud releases, using route namespace `spring.cloud.gateway.server.webmvc.routes` on supported versions. Starters, namespaces, filter factories, and configuration properties may differ on older lines (`spring.cloud.gateway.mvc.routes`) or newer releases. Always check your actual BOM/APIs. Most code snippets target Java 17+, Spring MVC, and Spring Boot Test; other variants require matching imports/configuration.

## 2. Architecture from a Testing Perspective

A request flowing through Gateway MVC has distinct observation points:

~~~mermaid
flowchart TD
    C["Test HTTP client / Browser"] --> S["Servlet container"]
    S --> F["Servlet FilterChain + Spring Security"]
    F --> D["DispatcherServlet"]
    D --> R["WebMvc.fn RouterFunctionMapping"]
    R --> P["Gateway MVC predicates + before/after filters"]
    P --> H["Gateway outbound HTTP handler/client"]
    H --> B["Backend HTTP stub / service"]
    B --> H
    H --> P
    P --> D
    D --> S
    S --> C
    M["MockMvc"] -. "Mock Servlet request directly" .-> F
~~~

In this lesson, we separate **three kinds of truth**:

| Layer | Core question | Tool |
| --- | --- | --- |
| **Inbound Servlet/MVC** | Did Spring Security let the request through? Which route/method/path matched? | `MockMvc` with appropriate application context |
| **Outbound Gateway → backend** | What URL, method, headers, and body did the backend receive? Were there retries/redirects? | Backend stub with request journal/counter |
| **End-to-end HTTP** | What status/headers/body does a real client receive over sockets and the Servlet container? | HTTP client targeting `RANDOM_PORT`; separate TLS/ingress tests when needed |

For example, a client sends `GET /edge/catalog/items/42?lang=vi`:

1. Servlet Security may return 401/403 **before the Gateway route runs**.
2. `Path=/edge/catalog/**` and `Method=GET` determine which route is chosen.
3. `StripPrefix=1` turns the backend path into `/catalog/items/42`; query `lang=vi` must stay intact per contract.
4. Header `X-Gateway-Probe: catalog-edge` may be added **only to the outbound request**.
5. Catalog may return HTTP 200/404/503, `ETag`, `Cache-Control`, redirects, or a large body.
6. Gateway returns the response via the Servlet container; response filters may alter headers/status.

**A `status().isOk()` assertion in `MockMvc` does not automatically prove steps 3–5 succeeded.** You need backend evidence and, when transport matters, requests over a real port.

## 3. Selection Matrix: Which Tool to Use First?

| Goal | `MockMvc` | HTTP client + backend stub | Staging/E2E system |
| --- | --- | --- | --- |
| MVC `HandlerMapping` and route predicates | Great when full Gateway context loads | Good | Useful when ingress path is needed |
| Servlet Security/CSRF/authorization rules | Great, fast | Required to verify real tokens/JWKS | Required for identity/network policies |
| Before/after filter logic | Testable | Verifies real HTTP outcomes | Tests multi-proxy interactions |
| Outbound request path/headers/body | Needs backend stub; `MockMvc` **does not mock outbound** | Great | Needed when real discovery/network matters |
| TCP connect, TLS handshake, socket reset | Does not simulate real inbound transport | Testable with stub/HTTPS test server | Needed with real ingress/mTLS |
| Header serialization, HTTP framing | Servlet simulation level only | Verified over HTTP sockets | Tests HTTP/2/ingress/CDN |
| SSE/large downloads/cancellation | Limited; does not reflect real network | Great for streaming tests | Needed for full proxy chains |
| Multi-replica routing, DNS/discovery | Insufficient | Sufficient only if testing matching infra | Suitable |
| Retry/breaker attempts | Needs stub counter in both | Stub counter fits well | Needed for fleet-level policies |
| Test speed | Fast | Slightly slower | Higher cost and flakiness risk |

**Recommendation:** A balanced suite keeps **many `MockMvc` tests** for mappings/security, a **smaller set of HTTP integration tests** for critical proxy contracts, and **targeted E2E tests** for TLS, ingress, discovery, and rolling deployments. Neither push every edge case to staging nor rely exclusively on mocks.

## 4. Right Dependencies, Web Application Type, and Test Context

For Gateway **Server Web MVC**, the starter in modern lines is typically:

~~~xml
<!-- Version managed by Spring Cloud BOM compatible with Spring Boot. -->
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-gateway-server-webmvc</artifactId>
</dependency>

<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

On older releases, the starter may be `spring-cloud-starter-gateway-mvc`. When testing auth with Spring Security, add the matching test support:

~~~xml
<dependency>
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

Inspect your dependency graph to ensure the runtime is **Servlet MVC**. Accidentally pulling in `spring-cloud-starter-gateway-server-webflux` or importing `web.reactive.function.server.RouterFunction` invalidates tests meant for Gateway Server MVC.

### How Does `@WebMvcTest` Differ from `@SpringBootTest`?

| Annotation/config | Primary effect | When to use |
| --- | --- | --- |
| `@WebMvcTest(Controller.class)` | Slices MVC controllers and required beans; **does not load full Gateway MVC auto-configuration by default** | Standalone controller or request validation tests |
| `@SpringBootTest(webEnvironment = MOCK)` + `@AutoConfigureMockMvc` | Loads application context without opening an inbound HTTP port; `MockMvc` calls mocked Servlet stack | Testing route mappings/security/filters near production config |
| `@SpringBootTest(webEnvironment = RANDOM_PORT)` | Starts Servlet container on a random port | Real HTTP integration tests over the network stack |
| `@SpringBootTest(RANDOM_PORT)` + `@AutoConfigureMockMvc` | Supports **both `MockMvc` and HTTP clients** in one context | Comparing behavior across both layers |

For Gateway routes registered by auto-configuration, `@WebMvcTest` easily returns **404 because `RouterFunction` beans are omitted**, even though production works. Prefer a full context for route tests, or explicitly import required components if intentionally slicing.

### `MockMvc` Is Not Reactive `WebTestClient`

`MockMvc` uses `MockHttpServletRequest`/`MockHttpServletResponse` on the Servlet/MVC stack. `WebTestClient` is commonly associated with WebFlux, **yet it can also act as a real HTTP client** via `bindToServer()` against a running Gateway MVC port. Never assume "using `WebTestClient` turns Gateway into WebFlux"—separate the **test client** from the **application runtime**.

In this lesson, examples use `MockMvc` for Servlet testing and **JDK `HttpClient`** to keep stacks unambiguous.

## 5. Creating a Verifiable Route

Suppose a Catalog backend stub listens at a URL supplied by property `catalog.stub.base-url`. A client sends:

~~~text
GET /edge/catalog/items/42?lang=vi
~~~

We expect the Gateway to send:

~~~text
GET /catalog/items/42?lang=vi
X-Gateway-Probe: catalog-edge
~~~

Example `application-test.yml` **for instructional reference**, not a file to create in a worker workspace:

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webmvc:
          routes:
            - id: catalog-read
              uri: ${catalog.stub.base-url}
              predicates:
                - Path=/edge/catalog/**
                - Method=GET
              filters:
                - StripPrefix=1
                - SetRequestHeader=X-Gateway-Probe,catalog-edge
~~~

This example targets Gateway Server MVC versions reading namespace `spring.cloud.gateway.server.webmvc.routes`. If your version uses `spring.cloud.gateway.mvc.routes`, switch to the **exact namespace** and check supported filter factories; **never declare both simultaneously and guess which binder runs**.

Because `StripPrefix=1` drops the `edge` segment, the path becomes `/catalog/items/42`. If the backend expects `/items/42`, pick `StripPrefix=2` or an appropriate rewrite and verify at the backend instead of guessing. We use **`SetRequestHeader`**, not `AddRequestHeader`, to overwrite values spoofed by clients. For non-security headers, `AddRequestHeader` has its place, though it generally **does not replace** existing values.

### Why Must the URI Property Be Test-Controlled?

If a CI route calls a real dev/staging host, tests risk side effects, network flakiness, token leaks, or failures when that service changes. `catalog.stub.base-url` should point to a **loopback/isolated test backend stub** with a dynamic port and request journal.

If a route uses `lb://catalog-service`, provide a test `ServiceInstance` supplier rather than hitting a production service registry.

## 6. Building an HTTP Backend Stub with a Request Journal

To verify the Gateway **actually sent an outbound request**, you need an observable HTTP endpoint. WireMock, MockWebServer, or a dedicated test Spring Boot backend all work. The example below uses **JDK `com.sun.net.httpserver.HttpServer`** to avoid extra dependencies; it is for lab use only, never a production HTTP server.

~~~java
import java.io.IOException;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;

final class CatalogStubFixture {

    static final AtomicInteger HITS = new AtomicInteger();
    static final AtomicReference<String> LAST_PATH =
            new AtomicReference<>();
    static final AtomicReference<String> LAST_QUERY =
            new AtomicReference<>();
    static final AtomicReference<String> LAST_MARKER =
            new AtomicReference<>();
    static final AtomicReference<String> LAST_METHOD =
            new AtomicReference<>();

    private static final HttpServer SERVER = start();

    private CatalogStubFixture() {}

    private static HttpServer start() {
        try {
            HttpServer server = HttpServer.create(
                    new InetSocketAddress("127.0.0.1", 0), 0);
            server.createContext("/", CatalogStubFixture::reply);
            server.start();
            return server;
        } catch (IOException error) {
            throw new ExceptionInInitializerError(error);
        }
    }

    static String baseUrl() {
        return "http://127.0.0.1:" + SERVER.getAddress().getPort();
    }

    static void reset() {
        HITS.set(0);
        LAST_PATH.set(null);
        LAST_QUERY.set(null);
        LAST_MARKER.set(null);
        LAST_METHOD.set(null);
    }

    static void stop() {
        SERVER.stop(0);
    }

    private static void reply(HttpExchange exchange) throws IOException {
        HITS.incrementAndGet();
        String path = exchange.getRequestURI().getRawPath();
        LAST_PATH.set(path);
        LAST_QUERY.set(exchange.getRequestURI().getRawQuery());
        LAST_METHOD.set(exchange.getRequestMethod());
        LAST_MARKER.set(
                exchange.getRequestHeaders().getFirst("X-Gateway-Probe"));

        int status = path.endsWith("/missing") ? 404
                : path.endsWith("/busy") ? 503 : 200;
        String body = status == 404
                ? "{\"error\":\"NOT_FOUND\"}"
                : status == 503
                ? "{\"error\":\"UPSTREAM_BUSY\"}"
                : "{\"id\":\"42\",\"source\":\"catalog-stub\"}";
        byte[] bytes = body.getBytes(StandardCharsets.UTF_8);

        exchange.getResponseHeaders().set(
                "Content-Type", "application/json;charset=UTF-8");
        exchange.getResponseHeaders().set(
                "X-Catalog-Backend", "stub");
        exchange.sendResponseHeaders(status, bytes.length);
        try (OutputStream stream = exchange.getResponseBody()) {
            stream.write(bytes);
        }
    }
}
~~~

**What this fixture provides:**

- Port `0` asks the OS for an ephemeral port, avoiding collisions on `9001` with other apps.
- The fixture receives real TCP/HTTP traffic when the Gateway outbound client calls it; it is **not a mocked Gateway bean**.
- `HITS` counts **outbound HTTP attempts**, `LAST_PATH`/`LAST_QUERY` record the final URI, and `LAST_MARKER` captures the backend-visible header.
- The stub returns 200, 404, or 503 by path—**normal HTTP responses**, quite distinct from TCP/TLS exceptions.
- The `AtomicReference` fields are minimal examples; when testing **concurrent** requests, use a thread-safe journal keyed by request ID rather than overwriting a single `LAST_*` field.

This code records paths/queries for **non-sensitive test data**. Never log access tokens, cookies, or PII into default request journals/logs in production. When using Java modules (JPMS), JDK `HttpServer` resides in `jdk.httpserver`; configure build/test flags to make that module accessible.

### Every Test Must Include an Outbound Counter

If a route applies `SetRequestHeader` and `StripPrefix`, you must prove not only that the client sees a 200 JSON body, but also:

~~~text
HITS        = 1
LAST_METHOD = GET
LAST_PATH   = /catalog/items/42
LAST_QUERY  = lang=vi
LAST_MARKER = catalog-edge
~~~

These are **expected values when the Gateway uses the right config**, not live execution output. If `HITS` is 0, a `MockMvc` 200 response could still come from Spring Security, another MVC controller, a fallback, or a cache; never conclude upstream was called.

## 7. `MockMvc` Testing Routes/Filters in a Spring Boot Context

To load full Gateway MVC auto-configuration, use:

~~~java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureMockMvc
@ActiveProfiles("test")
class GatewayMvcMockTest {
    // @Autowired MockMvc mockMvc;
}
~~~

In the hands-on test in the next section, we use **`RANDOM_PORT` combined with `@AutoConfigureMockMvc`** to run both test styles inside one application context. If you need only `MockMvc`, `MOCK` is lighter.

### 7.1. Common `MockMvc` Assertions

~~~java
mockMvc.perform(get("/edge/catalog/items/42")
                .queryParam("lang", "vi"))
        .andExpect(status().isOk())
        .andExpect(content().contentTypeCompatibleWith(
                MediaType.APPLICATION_JSON))
        .andExpect(jsonPath("$.id").value("42"));
~~~

Core imports:

~~~java
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;
~~~

**This snippet goes inside a class that has `MockMvc mockMvc`**, not as a standalone Java file. Ensure the route matches and the backend stub runs. Notably, `jsonPath("$.id")` checks only the final response—**it does not prove `StripPrefix` rewrote the path**, so assert `LAST_PATH` on the stub as well.

### 7.2. Testing Route Misses and Method Mismatches

~~~java
int before = CatalogStubFixture.HITS.get();

mockMvc.perform(post("/edge/catalog/items/42")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{}"))
        .andExpect(status().is4xxClientError());

assertEquals(before, CatalogStubFixture.HITS.get());
~~~

**Do not rigidly expect 404 for every method mismatch.** A Servlet handler mapping can return 405 when a path matches another handler that rejects the method, route misses can return 404, and deny-by-default security can return 403 **before MVC selects a route**. That is why the example asserts `is4xxClientError()`, while the critical invariant is **zero unauthorized calls reaching Catalog through a GET-only route**. In production tests, assert the exact expected status per your security/router contract once you know which layer handles it.

### 7.3. What Does `MockMvc` Observe vs. Skip?

`MockMvc` verifies status, response headers, cookies, body content, and resolved exceptions. However, Servlet mocks **do not simulate all HTTP details**:

- TCP socket lifecycle and congestion.
- HTTP/1.1 keep-alive, chunked transfer framing, or HTTP/2 multiplexing.
- Reverse proxies rewriting URLs, Host, or forwarded headers.
- TLS handshakes, client certificates, and mTLS.
- Client disconnects mid-response.
- Servlet connectors and outbound HTTP client pools under real load.

Testing those requires a **real HTTP client** and a production-like test environment.

## 8. One Integration Test Using Both `MockMvc` and an HTTP Client

This is the centerpiece example. **One test class** uses `@SpringBootTest(RANDOM_PORT)` to open a real inbound HTTP port alongside `@AutoConfigureMockMvc` for in-process requests. The HTTP backend stub starts via `CatalogStubFixture` from section 6.

~~~java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;

import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.http.MediaType;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureMockMvc
@ActiveProfiles("test")
class GatewayMvcProxyIntegrationTest {

    @Autowired
    MockMvc mockMvc;

    @LocalServerPort
    int gatewayPort;

    @DynamicPropertySource
    static void backendUrl(DynamicPropertyRegistry properties) {
        properties.add(
                "catalog.stub.base-url",
                CatalogStubFixture::baseUrl);
    }

    @BeforeEach
    void resetJournal() {
        CatalogStubFixture.reset();
    }

    @AfterAll
    static void stopBackend() {
        CatalogStubFixture.stop();
    }

    @Test
    void mockMvcChecksMvcRouteAndOutboundHeaders() throws Exception {
        mockMvc.perform(get("/edge/catalog/items/42")
                        .queryParam("lang", "vi")
                        .header("X-Gateway-Probe", "attacker"))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON));

        assertEquals(1, CatalogStubFixture.HITS.get());
        assertEquals("GET", CatalogStubFixture.LAST_METHOD.get());
        assertEquals("/catalog/items/42",
                CatalogStubFixture.LAST_PATH.get());
        assertEquals("lang=vi",
                CatalogStubFixture.LAST_QUERY.get());
        assertEquals("catalog-edge",
                CatalogStubFixture.LAST_MARKER.get());
    }

    @Test
    void realHttpClientChecksServletTransportAndStatus() throws Exception {
        HttpClient client = HttpClient.newBuilder()
                .followRedirects(HttpClient.Redirect.NEVER)
                .build();

        URI address = URI.create("http://127.0.0.1:"
                + gatewayPort + "/edge/catalog/items/busy");
        HttpRequest request = HttpRequest.newBuilder(address)
                .GET()
                .build();

        HttpResponse<String> response = client.send(
                request, HttpResponse.BodyHandlers.ofString());

        assertEquals(503, response.statusCode());
        assertTrue(response.body().contains("UPSTREAM_BUSY"));
        assertEquals(1, CatalogStubFixture.HITS.get());
    }
}
~~~

**Run preconditions:** The test application must actually include Gateway Server Web MVC, load the section 5 route YAML under profile `test`, and either allow test requests or supply valid authentication in `SecurityFilterChain`. `CatalogStubFixture` must reside in the test source tree. Only this test class owns the fixture; if splitting across multiple classes, manage lifecycles via a JUnit extension or context listener so one class does not stop the stub while another still uses it.

**Boot versions:** Packages for `@AutoConfigureMockMvc`, `@LocalServerPort`, and test helpers can shift across major releases; check your active version. In modular Java projects, ensure `jdk.httpserver` is readable.

### 8.1. What Does This Test Prove?

- **The `MockMvc` test** enters the MVC handler/router/filter pipeline via Servlet mocks, while outbound HTTP still hits the real stub.
- **The `HttpClient` test** flows from a client socket into the Gateway's live Servlet container, then out over a socket to the stub.
- In both tests, `HITS` counts upstream requests and `LAST_*` records what the backend received.
- Client-visible responses produced by Spring/Gateway are checked from the caller's perspective.

This is **illustrative code, not executed against a repo here**. To prevent Spring Security from blocking the first test, define an explicit test-profile security policy—**never ship `permitAll()` across all routes to production**.

### 8.2. Test Lifecycle and Parallel Execution

Because the fixture resets `HITS` and `LAST_*`, running two test methods concurrently will **race**. Disable parallel execution for the class (`@Execution(SAME_THREAD)` in JUnit 5 if needed), or build a thread-safe request journal keyed by correlation ID.

An `HttpServer` handles concurrent requests, yet `LAST_*` stores only the **latest request**; it cannot prove attempt order or fan-out. For retries and circuit breakers, use a thread-safe queue/journal recording timestamps and attempt numbers.

## 9. Choosing `MockMvc` Test Styles by Goal

### 9.1. Testing Standalone MVC Controllers

If your application exposes its own `@RestController`, use `@WebMvcTest` to verify validation, argument binding, statuses, and exception handlers, mocking collaborators with your Spring Boot version's mock annotations. **It does not load Gateway MVC's full route/filter setup** unless explicitly imported.

### 9.2. Testing Gateway Route Definitions

For YAML or `RouterFunction` Gateway MVC routes, use `@SpringBootTest` with full auto-configuration. `MockMvc` checks that `Path` and `Method` dispatch to the HTTP handler, while the backend journal verifies final path and headers.

### 9.3. Testing Custom Servlet Filters/Security

`MockMvc` excels at testing `SecurityFilterChain`, CSRF, and `Filter` ordering with security request post-processors. However, `MockMvcBuilders.standaloneSetup(controller)` bypasses the Servlet filter chain and Gateway routing, making it **unrepresentative of production**. Use the Spring Boot context or full `webAppContextSetup`/filter registration when testing cross-cutting filters.

### 9.4. Testing Gateway MVC Before/After Filters

Route filters like `SetRequestHeader`, `StripPrefix`, `AddResponseHeader`, or `RewritePath` require two sets of assertions:

1. **Backend-side request:** method, raw path, raw query, headers, and body after filters.
2. **Client-side response:** status, response headers, and body after all layers finish.

Checking only a response header **does not prove** the request header filter ran. Likewise, seeing the right backend path **does not prove** the response body or security ran properly.

## 10. Things `MockMvc` Usually Cannot Prove

| Observed in `MockMvc` | Do not infer | Complementary test |
| --- | --- | --- |
| `status().isOk()` | TCP/TLS/streaming behave properly under load | HTTP client + transport tests |
| Mock security `jwt()` with scope | Real JWT signatures/issuers/audiences validate | Signed test JWT through real resource-server decoder |
| Valid JSON body | HTTP/2 framing, compression, and `Content-Length` match | HTTP client and real proxies |
| Route matches | Registry has healthy backend instances | LoadBalancer/discovery tests |
| Fast 503 returned | Real circuit breaker is OPEN | Breaker metrics + outbound counter |
| Header present in mock response | CDN/ingress preserves that header | E2E through ingress |
| Timeout test with mocked Mono/scheduler | Real Servlet socket timeouts work | Fault injection on HTTP stub |
| Single request returns 200 | No hidden retries or POST side effects | Backend request journal/idempotency tests |
| Text response body | Cookies/CORS/caching work in browsers | Real HTTP + browser contract tests |

Core rule: **Place assertions at the exact layer of the claim you want to prove.** If you claim "clients connect over HTTPS", run a TLS/HTTP test. If you claim "JWT scope is enforced", `MockMvc`/Spring Security tests verify the **authorization rule**, yet **not** end-to-end signed token verification.

## 11. Testing Servlet Security with `MockMvc`

Gateway Server Web MVC uses **Spring Security Servlet**, not WebFlux's `SecurityWebFilterChain`. Incoming requests normally traverse `SecurityFilterChain` before `RouterFunctionMapping` picks a route.

Suppose the contract states:

- `GET /edge/catalog/**` is public.
- `GET /edge/orders/**` requires an access token with `SCOPE_orders.read`.
- All other methods/paths must be denied per policy.

An **illustrative stateless Bearer-only security configuration**:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableWebSecurity
public class GatewaySecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers(
                                HttpMethod.GET, "/edge/catalog/**")
                            .permitAll()
                        .requestMatchers(
                                HttpMethod.GET, "/edge/orders/**")
                            .hasAuthority("SCOPE_orders.read")
                        .anyRequest()
                            .denyAll()
                )
                .oauth2ResourceServer(resourceServer ->
                        resourceServer.jwt(Customizer.withDefaults()))
                .sessionManagement(session ->
                        session.sessionCreationPolicy(
                                SessionCreationPolicy.STATELESS))
                .csrf(csrf -> csrf.disable())
                .build();
    }
}
~~~

**Important condition:** Disabling CSRF here makes sense only for pure Bearer-token APIs without browser cookie/session authentication. If you serve cookie/CSRF-protected admin UIs, configure CSRF protection rather than blindly copying `.disable()`. Also configure **JWT issuer, signature verification, expiry, and audience** to match your real API—never trust `issuer-uri` presence alone.

### 11.1. `MockMvc` Negative Tests for Orders Read Access

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class GatewayMvcAuthorizationTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void anonymousCannotReadOrders() throws Exception {
        mockMvc.perform(get("/edge/orders/42"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void tokenWithoutOrdersScopeIsForbidden() throws Exception {
        mockMvc.perform(get("/edge/orders/42")
                        .with(jwt().authorities(
                                new SimpleGrantedAuthority(
                                        "SCOPE_catalog.read"))))
                .andExpect(status().isForbidden());
    }
}
~~~

Neither test **needs the Orders backend running** when security blocks ahead of the handler; pair this with asserting **outbound counter = 0** on blocked requests. Statuses 401/403 reflect default Resource Server authentication entry point and access-denied behavior under this config; custom entry points may emit other statuses.

### 11.2. Mock JWTs Are Not Real Signed JWTs

`.with(jwt())` from `spring-security-test` injects a valid mocked authentication into the security test context. It is great for verifying **authorization rules, test-supplied authority mappings, and matcher ordering**, yet it normally **skips signature validation, JWKS fetching, issuer checks, expiration, and audience validation** performed by a production resource server.

To test authentication end-to-end:

1. Run a **test Identity Provider/JWKS server** or sign test JWTs using a lab-only key.
2. Configure the decoder to validate issuer/audience/scopes per policy.
3. Send tokens through a **real HTTP client** via `Authorization: Bearer ...`.
4. Test invalid signatures, expired `exp`, wrong `iss`, wrong `aud`, and missing scopes.
5. Never use production tokens or log raw JWTs in test output.

**Split the problem:** Spring Security 401/403 tests, Gateway route matching tests, and backend authorization tests **are all required**, because backends must still enforce ownership/tenant permissions rather than blindly trusting the Gateway.

### 11.3. Route Predicates Are Not Authorization

`Method=GET`, `Path=/edge/orders/**`, or `Host=admin.example.test` only govern route selection. They do not verify caller identity or permissions. Tests for path traversal, encoded paths, query strings, and forwarded headers must cross the **real trust boundary** so an alternate path cannot sneak into a backend unprotected by Spring Security matchers.

### 11.4. Test Actuator Separately

If Gateway MVC exposes Actuator, test `/actuator/health` with probe permissions and write negative tests for sensitive endpoints. Gateway route filters do not automatically protect Actuator handler mappings. With a **separate management port**, run HTTP tests against that exact port and security context; `MockMvc` on the main app context may not cover a separate management server.

## 12. Testing Methods, Paths, Queries, Headers, and Encoded URIs

A `Path=/edge/catalog/**` route can work on plain ASCII URLs yet break on slashes, encodings, or forwarded hosts.

| Inbound request | What to check | Notes |
| --- | --- | --- |
| `GET /edge/catalog/items/42` | Backend receives `/catalog/items/42` | Baseline `StripPrefix=1` |
| `GET /edge/catalog/items/42?lang=vi` | Query intact at backend | Check stub's `getRawQuery()` |
| `POST /edge/catalog/items/42` | Not proxied through GET-only route | MVC may return 404/405 |
| `GET /edge/unknown` | Does not reach Catalog | Verify route miss / catch-all |
| `GET /edge/catalog/items/%2F42` | Intentional encoded-slash handling | Container/proxy may decode or reject |
| `GET /edge/catalog/items/a%2Bb` | Encoded plus not turned into space | Inspect raw path and backend semantics |
| `GET /edge/catalog/items/42?tag=a%2Bb` | Query `+` preserved properly | Do not compare decoded form alone |
| `GET /edge/catalog//items/42` | Double slash handled intentionally | Ingress may normalize it |
| `GET /edge/catalog/items/42/` | Trailing slash semantics | Test exact MVC version |
| `HEAD /edge/catalog/items/42` | Is HEAD routed? | HEAD has distinct MVC semantics |
| `GET` with spoofed header | `SetRequestHeader` overwrites cleanly | Client header never becomes trusted identity |
| `Host: attacker.example` | Does not redirect target backend arbitrarily | Never build backend URI from client Host |

**Never assume `%2F` passes through Servlet containers unchanged.** Tomcat/Jetty, ingress proxies, and Spring MVC path matching have differing decode/reject rules. Test with **real HTTP sockets** on your production container/version; `MockMvc` can bypass HTTP connector normalization.

### 12.1. Raw Queries Differ from Decoded Parameters

If a test asserts only:

~~~java
assertEquals("a+b", request.getParameter("tag"));
~~~

you cannot tell whether the client sent `tag=a%2Bb` or `tag=a+b` or which decoding rules the container applied. For proxy path/query integrity, record the **raw query** on the backend stub and compare it with decoded parameters when needed—critical when request signing or authorization depends on canonical URIs.

### 12.2. Handling Forwarded Headers

HTTP clients can send forged `Forwarded` and `X-Forwarded-*` headers. Behind an ingress, trust only headers **sanitized by trusted proxies** per configuration. Testing the Gateway port directly vs. behind ingress yields different results; document the test entry point clearly.

Never send `X-User-Role: ADMIN` and expect backend middleware to accept it. Backends must trust only verified principals/tokens/mTLS identities.

## 13. Testing Response Statuses, Headers, and Bodies on the Right Side

A Gateway contract covers more than route URLs. HTTP clients must receive the right status, end-to-end headers, and body representation:

| Backend returns | Client expects in normal pass-through | Notes |
| --- | --- | --- |
| 200 + JSON | 200, JSON `Content-Type`, intact body | Not a fake fallback 200 |
| 201 + `Location` | 201 and `Location` per public policy | Internal `Location`s need rewrite/allowlist |
| 204 No Content | 204, no body | Must not inject `{}` |
| 304 Not Modified | 304 with valid validators, no body | Do not strip `ETag` |
| 400 | 400 for valid client error | Do not retry endlessly |
| 401/403 | Security status preserved per contract | Never turn 403 into 200 |
| 404 | 404; distinguish backend 404 vs. route miss | Check backend counter |
| 429 + `Retry-After` | 429 and retry guidance if policy allows | Never silently bypass quotas |
| 503 | Transparent 503/fallback per route policy | Verify circuit breaker/retries |
| 206 + `Content-Range` | 206, exact byte ranges | Requires live HTTP/streaming tests |
| 302 + `Location` | Per redirect policy | Never auto-follow external hosts |

### 13.1. Checking Real Response Headers

A `MockMvc` request:

~~~java
mockMvc.perform(get("/edge/catalog/items/42"))
        .andExpect(status().isOk())
        .andExpect(header().string(
                "X-Catalog-Backend", "stub"));
~~~

If the Gateway config applies response header filters or ingress modifies headers, a **real HTTP client** must inspect the final response at the real URL and port rather than checking stub headers alone. Example:

~~~java
HttpResponse<String> response = client.send(
        request, HttpResponse.BodyHandlers.ofString());
assertEquals("stub",
        response.headers()
                .firstValue("X-Catalog-Backend")
                .orElse(""));
~~~

For multi-valued `Set-Cookie` or `Vary` headers, avoid checking only `firstValue()` when contracts require multiple values. HTTP response header names are case-insensitive.

### 13.2. Hop-by-Hop Headers and Body Encoding

Do not expect the Gateway to copy `Connection`, `Transfer-Encoding`, or `Content-Length` verbatim from the backend—they carry hop-by-hop semantics. If the Gateway rewrites or decompresses bodies, `Content-Encoding`, `ETag`, `Vary`, `Content-Range`, and `Content-Length` must match the actual bytes transmitted.

`jsonPath` alone cannot catch framing bugs, gzip issues, or truncated bodies; test raw/binary bytes over live connections whenever APIs rely on them.

### 13.3. 404 Can Come from Three Sources

~~~text
1. MVC/Gateway route miss -> 404
2. Gateway matches and Catalog returns 404 -> 404
3. Security/error handler intentionally masks details -> 404
~~~

In all three cases, the client may see 404. The **backend stub counter** separates #2 from #1/#3; sanitized logs/traces and security tests distinguish #1 from #3.

## 14. Fault Injection: Timeouts, Refused Connections, Resets, and Upstream 5xx

Gateway MVC tests must inject faults at the right layer to understand final outcomes.

| Fault | How to simulate in the lab | Signals to measure |
| --- | --- | --- |
| Backend returns 503 | Stub returns normal HTTP 503 | Upstream HTTP status, attempts, final status |
| Backend returns 429 | Stub returns 429 + `Retry-After` | Rate/budget, header policy |
| TCP refused | Route points to test port with no listener | Connect exception and error handler response |
| Connect timeout | Controlled network blackhole / test proxy | Bounded timeout, never hangs forever |
| Response timeout | Stub accepts socket then delays boundedly | Read/response timeout and latency |
| Reset mid-headers/body | Stub closes socket mid-stream | Partial response / connection error |
| Invalid TLS certificate | HTTPS stub using untrusted CA | Fails closed; never skips TLS verification |
| No service instance | Fake discovery returns empty list | Does not call arbitrary host |
| Circuit breaker OPEN | Breaker test fixture forced OPEN | Upstream counter stays unchanged |
| Retry budget exhausted | Stub fails continuously | Attempts stop at exact limit |

**Never simulate timeouts by calling `Thread.sleep()` inside a Gateway filter**, as that creates an internal thread bottleneck unrelated to backend faults. Put delays in the **backend stub** or a bounded test network proxy with explicit test timeouts. Never disrupt production connections.

### 14.1. Backend 503 Differs from Transport Exceptions

When a stub returns HTTP 503 with JSON, the Gateway completes the HTTP transport exchange normally—only the status indicates an error. On a TCP reset, there may be **no `ResponseEntity` from the backend at all**. The Gateway or framework must synthesize an error response whose exact status depends on filters, error handlers, and version.

Do not write tests assuming "every exception becomes 503"; define your project contract (e.g., backend unavailable → 502/503, response timeout → 504, auth failure → 401/403) and add tests distinguishing transport exceptions from backend-generated 503s.

### 14.2. Deadlines and Bounded Test Duration

A timeout test requires:

- Gateway HTTP client timeouts.
- Test HTTP client timeouts so assertions never wait forever.
- Test-runner/CI deadlines.
- Guarantees that the backend stub finishes or tears down cleanly.

Testing only "fails in under 30 seconds" makes suites slow and flaky. Use smaller values with **plenty of margin** over CI scheduling jitter. Tests must never depend on execution order or external thread pools shared with other tests.

### 14.3. Why Is `MockMvc` Alone Insufficient for Socket Timeouts?

`MockMvc` has no inbound TCP socket, so client disconnects, HTTP parser limits, server keep-alive, and inbound TLS behave differently from live Tomcat. Yet **outbound** calls from Gateway MVC to an HTTP stub can still hit real network sockets even when triggered through `MockMvc`. Keep both directions distinct when interpreting results.

## 15. Testing Routes Using `lb://` and Service Discovery

In production, routes often point to `lb://catalog-service` rather than `http://127.0.0.1:port`. The Gateway must resolve that service ID into one or more **`ServiceInstance`** objects via Spring Cloud LoadBalancer and discovery integration suited to MVC.

~~~mermaid
flowchart TD
    R["Gateway MVC route: lb://catalog-service"] --> LB["LoadBalancer / discovery adapter"]
    LB --> A["Catalog stub A: random HTTP port"]
    LB --> B["Catalog stub B: random HTTP port"]
    A --> J["Backend request journal"]
    B --> J
~~~

### 15.1. Unit/Slice Testing Instance Selection

When testing with synthetic `ServiceInstance`s, register a **test bean/service-instance supplier** matching your Spring Cloud LoadBalancer API. Never try forcing a WebFlux `ReactiveLoadBalancerClientFilter` into Gateway MVC; class names and wiring differ.

Key assertions:

1. `lb://catalog-service` resolves strictly from the **configured service ID**, never from client queries or headers.
2. Test instances A/B expose host/port pairs from two actually listening stubs.
3. When only A exists, requests reach A.
4. When zero instances exist, requests fail per contract—**never falling back to localhost/admin endpoints**.
5. After an instance leaves discovery, new requests stop picking it once the supported refresh/cache window elapses.
6. When instance metadata indicates HTTPS, outbound client certificates/trust are verified per policy.

### 15.2. Do Not Test Load Distribution with One Request

Load balancing does not guarantee A and B each get exactly 50% across two requests. Algorithms, caches, concurrent traffic, versions, and health filtering shift selection. If policy requires round-robin or weighted distribution, send an adequate sample **in the lab** within bounded time, allow statistical tolerance, and check instrumentation. Never write flaky assertions like "the second request must hit B" unless the algorithm is pinned deterministically in the test fixture.

### 15.3. Checking Consistency Across Multiple Gateway Replicas

Testing one Gateway instance does not prove every replica holds identical route definitions or discovery views. In staging E2E, query each Gateway pod/instance via approved channels, compare route/config revisions, and inspect backend journals. During rollouts, test readiness probes so out-of-sync instances receive no user traffic.

## 16. Testing `Retry`, `CircuitBreaker`, and Rate Limiting

All three mechanisms improve resilience, yet each has **different testing requirements**:

| Mechanism | Primary question | Mandatory evidence |
| --- | --- | --- |
| **`Retry`** | When faults occur, how many extra upstream attempts happen? | Backend journal/counter, final status, and latency |
| **`CircuitBreaker`** | When a dependency degrades, are calls short-circuited before HTTP? | Breaker state, outbound call count, fallback behavior |
| **`RateLimiter`** | Are over-quota requests blocked at the Gateway before upstream? | Quota/clock/key policy, 429 or contract status, outbound counter |

**Gateway Server MVC and WebFlux can differ in filter factory options**, so do not copy configurations verbatim from the other stack. Lock down version, filter order, and policy before asserting behavior.

### 16.1. `Retry` Must Check More Than the Final Response

Suppose one extra retry is configured for GET when Catalog returns 503:

~~~text
Inbound request: 1
Attempt #1: Catalog returns 503
Attempt #2: Catalog returns 200
Final response: 200
~~~

Expectations:

- `HITS = 2` on the stub.
- Client receives 200 with the body from attempt #2.
- If Catalog keeps returning 503, `HITS` must cap at **at most 2** instead of growing unboundedly.
- When the backend returns non-retryable 400/401/403/404, `HITS = 1`.
- Once the client deadline expires, the system stops issuing futile calls.

Note: `retries: 1` commonly means **one additional attempt after the initial call**, though you must verify exact Gateway MVC version semantics. If a test checks only final status 200, a buggy implementation firing **5 attempts then 200** still passes.

### 16.2. Multi-Layer Retries Amplify Load

For example, 3 client attempts × 3 Gateway attempts × 2 backend SDK attempts:

\[
A_{\max} = 3\times3\times2 = 18
\]

This is an upper bound **for a single sequential path**, excluding parallel fan-out and hedging. Single-layer tests miss multi-tier amplification: track operation-level client metrics and per-service outbound attempts. Never bump `retries` while a backend is overloaded just because callers see 503s.

### 16.3. `CircuitBreaker` OPEN

When a breaker is OPEN, a strong test verifies:

1. Gateway receives a valid inbound request.
2. **Backend request counter does not increment**, because calls are short-circuited.
3. Response is fail-fast or fallback per API contract, never serving another tenant's data.
4. Metrics record short-circuited calls rather than misreporting them as Catalog-returned 503s.
5. After transitioning to HALF_OPEN/CLOSED per policy, tests reset breaker state before the next test.

**Avoid testing breakers by "sending exactly 3 errors so it must be OPEN"** unless sliding windows, minimum calls, failure thresholds, wait durations, and recorded exceptions are pinned. Use test clocks and controlled breaker instances where supported.

### 16.4. Rate Limiters and Shared State

Rate limiters backed by Redis or shared stores cannot be faithfully tested with a mock bean hardcoded to return "allowed". Test:

- Key resolver extracts trusted identity rather than unauthenticated client `X-User-Id` headers.
- Requests pass within quota, then hit the configured rejection status once exceeded.
- Blocked requests **never call the backend**.
- Across multiple replicas, enforcement is **cluster-wide or per-node** as designed.
- When the backing store fails, fail-open vs. fail-closed matches API and security policy.

To make timing/rate tests deterministic, avoid arbitrary `Thread.sleep(1000)` calls; use fake clocks, test windows, or isolated store dependencies where possible. Available filters/rate limiters vary across Gateway MVC releases, so confirm the policy actually loaded before asserting.

## 17. Request/Response Bodies, Streaming, and Client Cancellation

**`MockMvc` handles small bodies well**: you can post JSON and assert responses with `content().json(...)` or `jsonPath(...)`. Yet many API Gateways also proxy files, multipart uploads, or long-lived event streams.

### 17.1. Small JSON/Body Tests

On a POST route (if permitted), a test request:

~~~java
mockMvc.perform(post("/edge/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"sku\":\"A-42\",\"quantity\":2}"))
        .andExpect(status().isAccepted());
~~~

This is a **sketch for a dedicated Orders route**: section 5's YAML has no POST route or handler yet. To make it meaningful, add an Orders stub and configure matching security, method/predicates, and response contracts—sending POST alone does not make the Gateway accept it.

Log **body bytes**, media type, charset, and actual `Content-Length` or transfer encoding in the backend journal. For sensitive payloads, record a **hash or bounded length** rather than storing raw request bodies.

### 17.2. Multipart Uploads

Multipart requests use boundaries generated by HTTP clients/Servlet parsers and can carry large files and metadata. `MockMultipartFile` in `MockMvc` tests MVC argument binding nicely, but **does not prove** HTTP connector, backend streaming, timeout, or memory behavior on real files. Add live HTTP tests with moderate payloads, verify max size limits, and confirm the backend receives every byte.

### 17.3. Streaming Responses and SSE

SSE/NDJSON responses keep connections open and flush chunks incrementally. With a **real HTTP client**, you can do:

~~~java
HttpClient client = HttpClient.newHttpClient();
HttpRequest request = HttpRequest.newBuilder(
                URI.create("http://127.0.0.1:" + gatewayPort
                        + "/edge/reports/stream"))
        .GET()
        .build();

HttpResponse<java.io.InputStream> response = client.send(
        request, HttpResponse.BodyHandlers.ofInputStream());

try (java.io.InputStream body = response.body()) {
    // Read bounded initial bytes/events in the lab.
    // Never buffer an infinite stream into a String or byte[].
}
~~~

This is a **sketch for a dedicated streaming route**, not section 5's Catalog route. Set body-read deadlines, test timeouts, and teardown; merely calling `close()` on the stream does not prove the backend noticed cancellation immediately. Verify cleanup through server metrics/journals rather than assuming from a local callback.

### 17.4. Already-Committed Responses

Once the client receives status 200 and part of an SSE/file stream, the Gateway cannot send a new HTTP 503 on that same response. Tests should simulate a backend sending partial bytes then resetting the connection, verifying the client **does not receive a JSON error appended mid-stream**. Final symptoms may be a connection reset or truncated body depending on transport—not a brand-new HTTP status code.

### 17.5. Cancellation Does Not Equal Rollback

If a POST reached Orders and the backend committed to its DB before the client disconnected, Gateway cancellation **does not undo the side effect**. Transaction tests need idempotency keys, atomic backend deduplication, operation states, and status-lookup endpoints. Never auto-retry POST simply because a socket closed.

## 18. Testing HTTPS, mTLS, and Live Reverse Proxies

`MockMvc` performs no inbound TLS handshake, so it cannot verify:

- Whether server certificates match hostnames/SANs and trust chains.
- Whether client certificates are required and verified via mTLS per policy.
- How HTTP/1.1 vs. HTTP/2 ALPN or TLS versions/ciphers negotiate.
- Whether ingress accepts and sanitizes `Forwarded`/`X-Forwarded-*` properly.
- Whether HSTS/CORS/`SameSite`/cookie attributes behave properly in browsers.

### 18.1. HTTPS Test Server for Outbound Calls

To test Gateway MVC → backend TLS:

1. Start an HTTPS stub with a **test certificate** whose SAN matches the test host.
2. Configure the Gateway HTTP client's truststore to trust the test CA.
3. Call the route and assert the backend receives the request.
4. Test expired/untrusted certs and hostname mismatches; connections must **fail closed**.
5. If mTLS is required, test valid client certs, missing certs, and untrusted certs.

**Never use `trustAllCertificates` or `NoopHostnameVerifier` to turn tests green.** Such tests prove the system *skips security checks*, defeating the purpose.

### 18.2. Inbound HTTPS and Ingress

To test client → Gateway TLS, run the Gateway on an HTTPS port or place a test ingress/nginx/service mesh in front. Testing a plain HTTP random port is insufficient when TLS terminates at ingress. Document **where TLS terminates and which hop each test covers**.

### 18.3. Forwarded Headers and Trusted Proxies

A vital test sends from an Internet/untrusted test client:

~~~http
X-Forwarded-Host: attacker.example
X-Forwarded-Proto: http
~~~

The Gateway **must not trust those values** unless they arrive from a configured trusted proxy. Run inbound HTTP tests through ingress to verify header normalization, CORS, redirects, and absolute links; never construct backend URIs from client-supplied `Host` or `X-Forwarded-Host` (SSRF risk).

## 19. Test Double Techniques: Stub, Mock Bean, or Real Service?

| Test double | Strengths | Limits |
| --- | --- | --- |
| **Mock bean** of internal service | Fast; isolates controller/security logic | Proves nothing about outbound HTTP |
| **JDK `HttpServer` stub** | Real sockets, dynamic port, zero extra dependencies | Hard to simulate HTTP/2, TLS, complex network faults |
| **WireMock / MockWebServer** | Request journals, header matching, delays, resets, fault injection | Requires test dependency/config and server lifecycle management |
| **Containerized backend** | Closer to production HTTP/server behavior | Slower; requires container runtime and cleanup |
| **Real staging service** | Exercises live discovery/TLS/networking | Shifting data, flakiness, side-effect and secret-exposure risks |

### 19.1. Can `MockRestServiceServer` Be Used?

Spring's `MockRestServiceServer` tests HTTP clients **only if** the Gateway actually uses a `RestClient`/`RestTemplate` or request factory that the test intercepts. **Do not assume it automatically intercepts every Gateway MVC outbound call.** If Gateway MVC creates its own HTTP client or route handlers use a different request factory, a `MockRestServiceServer` bound to the wrong bean will see zero requests.

Therefore, until you verify exact HTTP client injection/mocking support for your Gateway version, a **loopback HTTP backend stub** is simpler and clearer proof of wire-level requests.

### 19.2. `@MockBean` / `@MockitoBean` and Versions

Spring Boot/Spring Framework evolved mock-bean annotations across releases; some codebases use `@MockBean`, others `@MockitoBean`. Proxy tests using a backend stub need neither annotation. When unit/slice testing standalone controllers with mocked collaborators, pick the annotation matching your BOM.

### 19.3. Avoid Tests Depending on External Services

A Gateway test must never point at staging Catalog via a developer-hardcoded hostname and treat HTTP 200 as passing. That causes flakiness, irreproducibility, unintended writes, and uncertain backend versions. Use controlled test backends, unique request IDs, and explicit timeouts; reserve staging calls for explicitly approved E2E runs.

## 20. Comprehensive Test Matrix for Gateway Server Web MVC

A systematic test suite should have **at least one piece of evidence per critical boundary**, not dozens of repetitive tests asserting HTTP 200:

| ID | Scenario | Primary tool | Required assertions |
| --- | --- | --- | --- |
| T01 | GET matches Catalog route | `MockMvc` + stub | 200, `HITS=1`, right raw path |
| T02 | GET with query | `MockMvc` + stub | Raw query preserved per contract |
| T03 | POST to GET-only route | `MockMvc` | Zero outbound attempts on that route |
| T04 | Request matches no route | `MockMvc` | Never reaches Catalog; status per `HandlerMapping` |
| T05 | Two overlapping routes | `MockMvc` + stub | Route/destination picked by expected `order` |
| T06 | Client spoofs internal header | `MockMvc` + stub | `SetRequestHeader` overwrites client value |
| T07 | Response header added | `MockMvc` and HTTP client | Client observes expected response header |
| T08 | Backend returns HTTP 404 | HTTP client + stub | 404, `HITS=1`; distinct from route miss |
| T09 | Backend returns HTTP 503 | HTTP client + stub | Final 503/fallback per policy |
| T10 | Backend returns HTTP 204 | HTTP client | No invalid body emitted |
| T11 | Backend returns 302 | HTTP client | Redirect/destination policy preserved |
| T12 | `Cookie`/`Authorization` headers | Security + stub | No unauthorized credential forwarding |
| T13 | Spoofed `Host`/`X-Forwarded-Host` | HTTP client via edge | No SSRF, untrusted proxy headers ignored |
| T14 | Encoded slash/plus | HTTP client + stub | Path/query normalization matches policy |
| T15 | Small JSON/body | `MockMvc` + stub | `Content-Type`, charset, and payload intact |
| T16 | Multipart/large body | HTTP client + stub | No dropped bytes; size limit enforced |
| T17 | Gzip/`Content-Encoding` | Raw-byte HTTP client | Encoding and headers consistent |
| T18 | 206 Partial Content | HTTP client + stub | `Content-Range`/bytes accurate |
| T19 | Anonymous calls Orders | `MockMvc` Security | Blocked; `HITS=0` |
| T20 | JWT missing scope | `MockMvc` Security | 403 per policy; `HITS=0` |
| T21 | Signed JWT wrong issuer/audience | HTTP client + test IdP | Rejected by real JWT decoder |
| T22 | Valid token | `MockMvc`/HTTP client | Reaches right backend; backend checks authz |
| T23 | Backend connect refused | HTTP client + fault fixture | Never hangs; safe status/error |
| T24 | Backend response timeout | HTTP client + delayed stub | Aborts within deadline |
| T25 | Bad TLS cert | HTTPS stub | Never bypasses cert/hostname verification |
| T26 | LoadBalancer with 2 instances | HTTP client + 2 stubs | Calls only approved instances |
| T27 | LoadBalancer with 0 instances | HTTP client + fake discovery | Never calls arbitrary destination |
| T28 | Retry 503 then 200 | HTTP client + counter | Attempts within budget; right final status |
| T29 | Circuit breaker OPEN | `MockMvc`/HTTP client + counter | Backend skipped; valid fallback |
| T30 | Rate limit exceeded | `MockMvc`/HTTP client | Request blocked; backend `HITS` unchanged |
| T31 | Partial SSE stream | HTTP client streaming | Does not append 503 JSON post-commit |
| T32 | Client disconnect | Real HTTP client + stub | Resources cleaned up within timeouts |
| T33 | 2 Gateway replicas | E2E | Routes/security/metrics consistent |
| T34 | Actuator management | HTTP client to management port | Public clients cannot read/edit routes |
| T35 | Repeated CI runs | Test suite | No port collisions, races, or order dependence |

**Not every project must implement all 35 tests** in a single sprint. Prioritize by threat model and API contracts. Still, maintain **positive, negative, and failure-path coverage**, prioritizing high-severity risks: auth bypasses, misrouting, token leaks, retry duplication, and TLS.

### Grouping into Smoke, Regression, and Deep Tests

- **Smoke (every commit):** T01–T04, T06, T08/T09, T19/T20, T23, plus backend `HITS` checks.
- **Route/header regression (pull requests):** T05, T07, T10–T18, T22, plus encoded-path and header-spoofing cases.
- **Resilience/security integration (scheduled CI or pre-release):** T21, T24–T30, TLS/circuit breaker/real JWTs, and resource limits.
- **Approved E2E/soak/chaos:** T31–T35, multi-replica, ingress, cancellations, and sustained load.

Some tests belong in earlier tiers depending on risk. An e-commerce team, for instance, may run idempotency/retry tests on **every pull request** rather than waiting until pre-release.

## 21. Making Tests Deterministic and Safe in CI

Gateway tests face many sources of flakiness: TCP ports, Spring startup, caching, time-based policies, schedulers, and async I/O. Good results must be **repeatable**.

### 21.1. Managing Ports and Fixture Lifecycles

**Do:**

- Use `@SpringBootTest(webEnvironment = RANDOM_PORT)` for Gateway inbound traffic.
- Bind backend stubs to port `0` and read the assigned port after startup.
- Provide the backend base URL to routes via `@DynamicPropertySource`.
- Clean up fixtures/servers in `@AfterAll` or an owning test extension.
- Set timeouts on both outbound clients and test clients.
- Avoid sharing a single mutable `LAST_REQUEST` across parallel test methods.

**Avoid:**

- Hardcoding `8080`/`9001` across all CI test classes.
- Stopping a shared static HTTP server from one class while another class still uses it.
- Using `Thread.sleep` to "wait for routes to be ready" without explicit readiness checks.
- Calling real Internet/DNS endpoints unintentionally without permission.
- Omitting HTTP client timeouts so builds can hang forever.

### 21.2. Static State, Profiles, and Context Caching

Spring Test **caches application contexts** across test classes. If class A uses `@DynamicPropertySource` pointing to stub A, and class B shares the same context key while expecting stub B, improper context caching can leak stale URLs or hit a stopped server.

For large test suites:

1. Pin fixtures consistently per test/context group.
2. Use test extensions or container lifecycles with clear ownership.
3. Use `@DirtiesContext` sparingly—only when state/config genuinely changes, as it slows down the suite.
4. Vary profiles/configuration keys whenever separate contexts are required.
5. Reset circuit breaker/rate limiter/store state after tests so execution order never matters.
6. Attach correlation IDs **only to synthetic test data**; never put user IDs or secrets into metric labels.

### 21.3. Never Use Production Secrets in Tests

Test JWTs must be signed by test-only keys or issued by a test IdP. Never commit production private keys, API keys, or refresh tokens to the repository. Never print `Authorization`, `Cookie`, or full URIs containing sensitive queries into request-journal logs or CI artifacts.

A string like `Bearer fake-demo-token` used to test header stripping is **synthetic data**, yet when Spring Security's resource server is active, that token will be rejected **before the Gateway handler**. Keep header-forwarding tests in a security-isolated context separate from valid signed-JWT authentication tests.

### 21.4. Do Not Mask Bugs with Test-Harness Retries

A test may appear "more stable" if the test HTTP client retries on connection refused, yet that hides application startup/readiness bugs. Use explicit readiness probes/wait strategies, then send requests with **known attempt counts**. When testing retries themselves, configure them in the Gateway policy or test client per contract and count backend attempts—never silently raise test-framework retries.

### 21.5. Running Tests in a Pipeline

A sensible sequence:

~~~mermaid
flowchart LR
    A["Compile / unit tests"] --> B["MockMvc routes & Security"]
    B --> C["HTTP Gateway + stub integration"]
    C --> D["Fault/TLS/discovery tests"]
    D --> E["Staging E2E + rollout checks"]
~~~

Decide whether to fail or rerun a stage based on **root cause**. A repeated failure on a 404 route misconfiguration must never be dismissed as a "flake" merely because the app works for a different route.

## 22. Diagnosing Divergent Results Between `MockMvc` and HTTP Clients

When `MockMvc` passes and an HTTP client fails on the exact same URL, inspect each changed boundary in order:

| Symptom | Likely hypothesis | What to check |
| --- | --- | --- |
| `MockMvc` 200, HTTP client connection refused | Servlet server not started / wrong port | `@SpringBootTest(MOCK)` opens no socket; use `RANDOM_PORT` |
| `MockMvc` 200, HTTP client 401/403 | Different security chain, forwarded headers, or auth context | Compare mock JWT vs. real Bearer token |
| `MockMvc` 200, HTTP client 404 | Context path, ingress rewrite, normalization, `HandlerMapping` | Safely log raw URL and servlet context path |
| `MockMvc` 200, HTTP client 405 | Different real HTTP method or preflight | Inspect HTTP method, CORS/OPTIONS |
| `MockMvc` 200, HTTP client 502/503 | Backend URL/port, TLS/DNS, instance resolution | Check outbound stub/journal and transport exceptions |
| `MockMvc` header right, HTTP client missing it | Container/ingress/response filters altered header | Compare pre- and post-proxy responses |
| `MockMvc` body right, HTTP client corrupted | Encoding, gzip, `Content-Length`, HTTP framing | Inspect raw bytes and response headers |
| `MockMvc` cannot test cancellation | No inbound TCP socket | Use real HTTP client and streaming backend |
| HTTP client tests flake in parallel | Port/static state/context caching | Use port `0`, isolated journals, per-context fixtures |
| Backend `HITS=0` despite 200 response | Cache, fallback, or different handler | Verify route match and response provenance |
| Backend `HITS > 1` | Retries, redirects, or repeated client calls | Enable attempt tracing; check budgets |
| HTTP client misses 302 redirect | Client auto-follows redirects | Disable redirect following in tests; check Gateway outbound client separately |
| 503 happens on only one replica | Route/config/discovery mismatch | Run E2E against individual instances |
| 401/403 happens only on `/actuator` | Separate management context/security | Inspect management port and matchers |
| `MockMvc` green yet CPU spikes under load | Connector threads/HTTP pools untested | Run bounded load tests; inspect thread/connection metrics |

### 10-Step Investigation Workflow

1. **Identify the entry point:** `MockMvc` or HTTP client? Direct to Gateway or via ingress?
2. **Confirm the stack:** Gateway Server Web MVC/Servlet, not mixed with reactive Gateway Server.
3. **Confirm the server is listening:** `MockMvc` runs without an HTTP listener; is `RANDOM_PORT` live and ready?
4. **Spring Security:** Was the request rejected during authentication, authorization, or CSRF before routing?
5. **Route binding:** Did the YAML namespace and Java DSL/factories load?
6. **Predicates:** How do Path, Method, Host, and Header match after Servlet URL normalization?
7. **Filters:** What did `StripPrefix`/`SetRequestHeader`/`RewritePath` transform inputs into?
8. **Outbound:** Was a real HTTP attempt made? What happened with `ServiceInstance`, DNS/TCP/TLS/pool/timeouts?
9. **Response:** Did status come from the backend or a fallback/error handler? What are the final headers/body/encoding?
10. **Reproduce:** Use isolated fixtures and profiles with matching versions/containers—never relax security policies just to pass a test.

Specifically, if a bug appears only in the HTTP client, **do not tweak Mockito controller mocks** before checking sockets, forwarded headers, and real JWTs. Conversely, if it appears only in `MockMvc`, check whether the mock request lacked context paths/headers or whether a slice test omitted needed filters.

## 23. Guided Lab: Verifying the Same Route Both Ways

**Scenario:** Your team runs a Gateway Server Web MVC instance proxying Catalog and Orders. Catalog is a read API; Orders requires a valid access token. You are tasked with verifying pre-deployment that routes/paths/headers are accurate, security cannot be bypassed, unnecessary calls never reach backends, and real HTTP clients observe the contract.

### Part A — Initialize the Test Project

1. Choose a **Spring Boot + Spring Cloud BOM** compatible with Gateway Server Web MVC, matching JDK, test dependencies, and `spring-security-test` as needed.
2. Create a Spring Boot app running **Servlet Web MVC**, ensuring Server WebFlux is not pulled in accidentally.
3. Add the section 5 Catalog route to the test profile under your release's exact namespace.
4. Use `CatalogStubFixture` from section 6 to expose a backend URL on a dynamic port.
5. Inject the stub URI into the route via `@DynamicPropertySource`; never call staging backends.
6. Boot the Gateway with `@SpringBootTest(RANDOM_PORT)` and `@AutoConfigureMockMvc`.
7. If Spring Security protects Catalog, add proper auth/permission test fixtures; never silently disable production security via an unreviewed test profile.

### Part B — Testing with `MockMvc`

1. Send a valid GET `/edge/catalog/items/42?lang=vi`.
2. Assert HTTP 200, JSON `Content-Type`, and expected body.
3. Assert backend `HITS=1`, method `GET`, raw path `/catalog/items/42`, and raw query `lang=vi`.
4. Send client header `X-Gateway-Probe: attacker` and verify the backend **sees only the trusted value** `catalog-edge` from `SetRequestHeader`.
5. Send POST to the GET-only route and verify backend `HITS` does not increment.
6. Send a URL matching no Catalog route and verify the backend is not called by mistake.
7. Have the stub return 404 and 503, verifying the client response is not turned into 200 outside the contract.

### Part C — Testing with a Real HTTP Client

1. Read the Gateway's inbound port via `@LocalServerPort`.
2. Build a JDK `HttpClient` with sensible test timeouts and explicit redirect handling.
3. Send the same GET to `http://127.0.0.1:<port>/edge/catalog/items/42`.
4. Assert status/`Content-Type`/body on the **real response from the Servlet container**.
5. Compare the backend journal for this request with `MockMvc`: identical path, query, and marker.
6. Call `/edge/catalog/items/busy` and verify status 503.
7. Send encoded slashes, plus signs, and special queries via valid URIs; record where the container rejects or decodes differently from `MockMvc`.
8. Document what the HTTP client proved that `MockMvc` could not, especially inbound sockets/TLS/encoding.

### Part D — Security Negative Tests

1. Enable Servlet `SecurityFilterChain` for Orders.
2. For an anonymous GET to Orders, assert rejection before the backend.
3. For a mock JWT lacking `SCOPE_orders.read`, assert 403 per policy.
4. With a signed test JWT having valid issuer/audience/scope over the HTTP client, test access and backend authorization (tenant/ownership) separately.
5. With an expired JWT, bad signature, or wrong audience, verify the resource server rejects it.
6. Send `X-User-Role: ADMIN` with no valid token; access must be denied.
7. If Actuator is enabled, verify the management port and route-listing protection separately rather than assuming Gateway route filters cover them.

### Part E — Reliability and Fault Injection

1. Have the stub always return 503; verify final status and **attempt counts** against Gateway MVC's `Retry` config.
2. Have the stub return 503 first then 200; verify attempt counts and total duration.
3. Simulate TCP refused, response delays, and resets to distinguish HTTP errors from transport failures.
4. Test `CircuitBreaker` OPEN: inbound requests get the policy-defined response while the backend **receives zero calls**.
5. Test rate limiting: exceeding quota blocks requests before the backend.
6. If using `lb://`, provide test instances and simulate zero instances.
7. Test TLS failures with an HTTPS stub and untrusted CA without disabling verification.
8. For uploads or SSE, verify memory/streaming behavior over a real HTTP client rather than expecting `MockMvc` to simulate full network behavior.

### Part F — Comparing Both Approaches

Fill in this table with **actual observed results**, never copying expectations as results:

| Criterion | `MockMvc` | Real HTTP client | Conclusion |
| --- | --- | --- | --- |
| Opens inbound TCP port? | Not needed | Yes | |
| Runs Spring MVC `HandlerMapping`? | Yes with full context | Yes | |
| Sends real outbound HTTP to stub? | Can do so | Yes | |
| Inspects backend path/headers? | Yes with stub/journal | Yes with stub/journal | |
| Tests inbound TLS handshake? | No | Yes when testing HTTPS | |
| Tests socket disconnects? | Partially | Yes within setup limits | |
| Tests auth matchers? | Yes | Yes | |
| Validates real signed JWTs? | No if using mock `jwt()` alone | Yes with real decoder/test IdP | |
| Tests real HTTP content encoding/framing? | Limited | Yes | |
| Catches retry amplification? | Only if measuring backend attempts | Yes when measuring backend attempts | |

### Part G — Deliverable Report

- **Version matrix:** Spring Boot, Spring Cloud Gateway Server Web MVC, Java, Servlet container.
- **Test context:** `MockMvc` vs. `RANDOM_PORT`, profiles, and backend fixtures/ports.
- **Call-path diagram:** client/`MockMvc` → Security → `DispatcherServlet` → Gateway MVC → outbound HTTP stub.
- **Routing results:** raw path/query, method, inbound and allowlisted outbound headers.
- **HTTP contract:** client status/headers/body for 200, 404, 503, and transport faults.
- **Security evidence:** anonymous/wrong-scope/signed JWT cases; backend counter = 0 when blocked.
- **Reliability evidence:** retry attempts, OPEN breaker, timeouts, rate limiting.
- **Transport evidence:** TLS, encoded paths, streaming/large bodies within lab scope.
- **CI evidence:** repeatable runs with no port conflicts, order dependence, or leaked secrets.

**Passing criteria:** Learners do not merely show **how to call `MockMvc.perform()` or `HttpClient.send()`**, but also prove **every Gateway claim with evidence at the right layer** while recognizing each tool's limits.

## 24. Anti-Patterns to Eliminate from Your Test Suite

| Anti-pattern | Why it is dangerous | Replace with |
| --- | --- | --- |
| Asserting only HTTP 200 | Could be a fallback/cache with zero upstream calls | Assert backend counter and path/headers |
| Using `@WebMvcTest` to claim full Gateway MVC routing works | Omits full Gateway auto-configuration | Full context when testing routes |
| Treating `MockMvc` as an inbound TCP socket | Skips connector/TLS/framing | HTTP client against `RANDOM_PORT` |
| Mocking a service bean to claim Gateway proxying works | Fires no outbound request | HTTP stub over sockets |
| Binding `MockRestServiceServer` to a `RestClient` Gateway does not use | Mock intercepts nothing | Verify exact client bean/wiring or use HTTP stub |
| Hardcoding ports 8080/9001 across all tests | Port collisions and CI flakes | Port `0` / `RANDOM_PORT` + `@DynamicPropertySource` |
| Sending test requests to staging/prod Catalog | Side effects and data coupling | Backend stub / isolated test namespace |
| Using `AddRequestHeader` expecting to overwrite spoofed headers | May merely append new value | `SetRequestHeader` or header sanitizer |
| Treating client-sent `X-User-Id` as principal | Authorization bypass | Trusted signed JWT / mTLS identity |
| Testing `.with(jwt())` and claiming issuer/audience verification works | Mock auth skips real JWT decoder | Signed test token + HTTP client |
| Disabling `SecurityFilterChain` in every integration test | Misses 401/403 and policy drift | Dedicated security integration suite |
| Disabling CSRF unconditionally so POST tests pass | Masks cookie/session auth vulnerabilities | Align CSRF policy with auth model |
| Testing retry by checking only final status | Misses 10 backend attempts | Request journal + attempt budget |
| Leaving circuit breaker OPEN without resetting state | Test-order dependency | Per-test fixture and controlled resets |
| Waiting via long `sleep` calls | Slow and flaky | Test clocks/controlled delays and bounded deadlines |
| Sending SSL requests with trust-all certs | Disables TLS security checks | Test truststore and negative cert cases |
| Logging full raw HTTP bodies | Leaks tokens/PII and blows up log cardinality | Synthetic data, metadata allowlists, content hashes |
| Collecting infinite SSE into `byte[]` | Exhausts memory and hangs tests | Streaming client with bounded reads |
| Seeing HTTP 404 and assuming no route matched | Backend can also return 404 | Counter and traces |
| Demanding 50/50 split over two LB requests | Randomness, algorithms, and caching vary | Sampled distribution tests with pinned config |
| Firing POST/DELETE at prod management endpoints to "prove" they're blocked | Executes real changes if misconfigured | Test sandboxes and network/security policies |
| Ignoring flaky test failures because reruns pass | Hides races, timeouts, or route drift | Reproduce and explain root cause |

## 25. Pre-Merge Checklist for Gateway MVC Changes

A pull request modifying routes, filters, or security should verify at least:

~~~text
[ ] BOM/starter and property namespace match Gateway Server Web MVC.
[ ] Route Path/Method/Host predicates tested with real requests.
[ ] StripPrefix/RewritePath preserve method, raw query, and encoding per contract.
[ ] Outbound headers verified via backend request journal.
[ ] Response headers/status/body verified from the client side.
[ ] Tokens/cookies never forwarded to unauthorized upstreams.
[ ] Client-spoofed Host/X-Forwarded-*/X-User-* headers never trusted.
[ ] Anonymous/insufficient-scope requests never reach the backend.
[ ] Signed JWT decoder tested whenever authn/issuer/audience changes.
[ ] Route-miss 404 separated from backend 404; backend 503 separated from transport faults.
[ ] Retry/circuit breaker/rate limit count upstream attempts and prevent storms.
[ ] Timeout and TLS hostname verification have negative tests.
[ ] Large bodies/streaming/cancellation tested when relevant to the API.
[ ] Tests use random ports and clean fixture teardown.
[ ] Staging/production never called unless explicitly approved for E2E.
[ ] No credentials, PII, or raw sensitive payloads logged.
[ ] CI runs reliably without order dependence or parallel races.
~~~

Checklists never replace threat modeling or SLO reviews; they ensure small changes—like **adding a header, tweaking a predicate, or adjusting retries**—do not accidentally turn the Gateway into a privilege-escalation vector or load amplifier.

## 26. Summary

- **Gateway Server Web MVC** runs on Servlet/Spring MVC/WebMvc.fn; test against the MVC runtime rather than Server WebFlux.
- **`MockMvc`** excels at fast route mapping, MVC filter, Servlet Security, and response assertions, **yet opens no inbound TCP socket** and does not mock outbound HTTP.
- **A real HTTP client** hitting `@SpringBootTest(RANDOM_PORT)` adds verification for HTTP transport/serialization, network errors, TLS, and streaming, without replacing backend assertions.
- **An HTTP backend stub with a request journal** bridges the gap: proving outbound method/path/query/headers/body and retry attempt counts instead of guessing from final HTTP statuses.
- **`@WebMvcTest`** is an MVC slice test; **`@SpringBootTest`** fits when full Gateway auto-configuration is needed. Test contexts and starters must match your version/namespace.
- **Security tests work at two levels:** `MockMvc` with `.with(jwt())` tests authorization rules, while signed JWTs over an HTTP client/real decoder verify issuer, audience, signatures, and expiry.
- **Route predicates and Gateway filters do not replace authorization.** Test header spoofing, encoded paths, and trust boundaries; use `SetRequestHeader` when overwriting client-supplied values.
- **Fault tests must separate HTTP errors from transport failures**, measuring retries, circuit breakers, rate limiting, and client-visible statuses—never "fixing" tests with infinite retries or disabled TLS checks.
- **Large bodies, SSE, WebSockets, client disconnects, HTTP/2, and ingress/mTLS** need targeted live HTTP/E2E tests because `MockMvc` cannot fully simulate sockets and streaming.
- **Reliable CI** relies on random ports, isolated test backends, deterministic fixtures, bounded timeouts, and synthetic secrets—never production data or leftover state from prior tests.

A trustworthy **SPRING_CLOUD_GATEWAY** test suite is not the one with the most `status().isOk()` assertions, but the one that **knows exactly what is mocked, what actually traverses HTTP, and what has been proven at both the backend and the client**. Use **`MockMvc` to verify Servlet/MVC behavior**, and an **HTTP client paired with a backend stub to verify network-level proxy contracts**, then expand to TLS, discovery, and multiple replicas as system risk demands.
