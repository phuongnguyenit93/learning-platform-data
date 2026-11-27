# Verifying Path, Headers, Body, and Status After Forwarding

## 1. Why Is HTTP 200 Insufficient to Prove Accurate Gateway Forwarding?

**Spring Cloud Gateway** typically sits in front of microservices to select routes by route predicates, execute filter chains, rewrite paths/headers, resolve service instances, and enforce authentication, rate limiting, circuit breaking, retries, TLS, and observability. When a Gateway is misconfigured, requests may still return **HTTP 200** yet reach the **wrong service, wrong path, wrong body, or lack critical headers**.

Consider an Orders API contract:

~~~text
Client sends:
  POST /api/orders/create?source=mobile
  X-Request-Id: req-42
  Content-Type: application/json

  {"sku":"PEN-01","quantity":2}

Gateway:
  route = orders-api
  StripPrefix=1
  SetRequestHeader=X-Gateway-Source, edge
  RemoveRequestHeader=X-Debug-Only

Upstream must actually receive:
  POST /orders/create?source=mobile
  X-Gateway-Source: edge
  Content-Type: application/json

  {"sku":"PEN-01","quantity":2}

Upstream returns:
  201 Created
  Content-Type: application/json
  X-Upstream-Result: created
  {"accepted":true}

Client must receive:
  201 Created
  JSON body {"accepted":true}
  X-Upstream-Result header unless removed/altered by a filter
~~~

A test that only runs `curl` and sees `201` cannot prove the backend received `quantity=2`, that `/api` was stripped from the path, that a spoofed header was removed, or that the Gateway did not hit the backend twice due to `Retry`.

That is why **"Verifying Path, Headers, Body, and Status After Forwarding"** in the **Testing** chapter of the **SPRING_CLOUD_GATEWAY** module focuses on the **HTTP contract observed from both sides of the Gateway**.

After this lesson, you will be able to:

1. Build expectation tables covering **requests entering the Gateway**, **requests reaching upstream**, and **responses returned to the client**.
2. Verify route predicates, `StripPrefix`, `RewritePath`, query strings, and URL encoding.
3. Distinguish testing **outbound request headers** from **inbound response headers**, including multi-value and hop-by-hop headers.
4. Test JSON, form, binary, empty, and streaming bodies without assuming bytes remain untouched when body transformations apply.
5. Verify `201/204/302/400/401/403/404/429/500/503` statuses and identify which layer generated each status.
6. Combine **`WebTestClient` + a real mock upstream** to traverse Gateway Server WebFlux's HTTP routing pipeline.
7. Write deterministic fault-finding tests independent of the Internet, fixed ports, or production upstreams.
8. Extend verification to retries, circuit breakers, rate limiting, service discovery, TLS, and tracing.

> **Scope:** Primary examples use **Spring Cloud Gateway Server WebFlux** and JUnit 5. Spring Cloud Gateway Server Web MVC or Proxy Exchange MVC use different framework/filter APIs, though the two-sided HTTP verification principles remain similar. Gateway 4.x and 5.x configuration namespaces are explicitly distinguished. Code snippets are study examples, **not executed test outputs from this lesson**.

## 2. Defining "Forwarded Successfully" Properly

Do not equate `Gateway response` with `backend request`. A typical flow looks like:

~~~mermaid
sequenceDiagram
    autonumber
    participant C as Test HTTP Client
    participant G as Gateway WebFlux
    participant U as Mock Upstream
    C->>G: HTTP method + public path + headers + body
    G->>G: Match route predicates
    G->>G: Request filters: path/header/body
    G->>U: HTTP method + transformed path + headers + body
    U-->>G: Status + headers + response body
    G->>G: Response filters / status mapping
    G-->>C: Final HTTP status + headers + body
    Note over C,U: Tests must assert both the request to mock and response to client
~~~

Four signal groups must be measured:

| Group | Question to verify | Strong evidence |
|---|---|---|
| **Path/URI** | Did the request route to the right route/upstream with the right rewritten path? | Mock upstream records method, path, query |
| **Headers** | Were required headers added/modified/removed in the right direction without leaking secrets? | Mock records request headers; test client reads response headers |
| **Body** | Are body bytes/JSON schema/content type intact after proxying? | Mock receives raw body; JSON parser; response body assertions |
| **Status** | What status did the client receive, and did it originate from backend or Gateway/filter? | Mock returns controlled status; test compares client status and upstream counter |

A reliable end-to-end test has **two observation points**: the client checks the response and the mock backend checks the request. Asserting only the Gateway response can let a misrouted request hit another backend that also returns `200`.

### 2.1. Three Outcomes Never to Conflate

- **Routing success:** the right route matched and upstream received the contract-compliant request.
- **Backend business success:** the backend executed business logic and returned an appropriate status/body, e.g., 201.
- **Gateway presentation success:** response filters transformed the response per policy and the client received the final status/body.

The Gateway may route cleanly while the backend returns 422 due to invalid input—that is not a routing bug. Conversely, the Gateway may misroute to a stub that happens to return 200—that is a routing bug despite the nice status.

## 3. Testing Tiers and Recommended Order

| Tier | Tools | Best for | Limitations |
|---|---|---|---|
| Unit tests for predicates/filters | `MockServerWebExchange`, mock `GatewayFilterChain` | Match conditions, attribute/header/path mutations | Does not prove real outbound HTTP |
| WebFlux mock application tests | `WebTestClient.bindToApplicationContext(...)` | WebFlux handlers/filters in mock context | May skip live Netty routing sockets |
| **HTTP integration tests** | `@SpringBootTest(RANDOM_PORT)` + `WebTestClient.bindToServer()` + MockWebServer/WireMock | **Public request → Gateway → HTTP upstream → Gateway response** | Slower startup than unit tests |
| Inter-service contract tests | Pact/OpenAPI + mocks or provider verification | Schema, status, and header contract compliance | Requires provider/consumer versioning |
| Staging E2E | Gateway + service discovery + TLS + auth + real environment | Infra, multi-replica, resilience, network policies | Slower, costlier, higher flake risk |

**Rule of thumb:** run fast, stable tests at lower tiers, **yet always keep a suite passing through a real HTTP server and mock upstream** to prove `NettyRoutingFilter`/HTTP client routing works.

In Server WebFlux, `WebTestClient.bindToServer()` connects to a **running HTTP server**, unlike `bindToController()` or a mock application context. Spring Boot `RANDOM_PORT` boots the server inside the test process on an OS-allocated ephemeral port.

### 3.1. Testing Without Public Internet Backends

Never point default integration tests at `https://example.org`, a shared staging service, or a production service:

- Responses can change over time.
- Network/TLS/DNS issues cause flakiness.
- Mutating real data is dangerous.
- You cannot deterministically inject specific statuses, bodies, headers, or faults.

Use a **controllable mock upstream** able to enqueue responses and record every received request—such as **OkHttp MockWebServer** or WireMock.

## 4. Building a "Two-Way Contract" Before Writing Tests

A test-case table should capture input, Gateway configuration, and expected outcomes on both sides:

| Field | Client sends | Gateway is expected to do | Upstream must receive |
|---|---|---|---|
| HTTP method | POST | Preserve | POST |
| Path | `/edge/echo` | `StripPrefix=1` | `/echo` |
| Query | `?request=integration` | Leave query untouched | `?request=integration` |
| Header `X-Gateway-Source` | `spoofed` | `SetRequestHeader=..., gateway-test` | `gateway-test` |
| Header `X-Debug-Only` | `must-not-leak` | `RemoveRequestHeader` | Absent |
| `Content-Type` | `application/json` | Preserve | `application/json` |
| Body | `{"item":"pen","quantity":2}` | Preserve | Matching contract JSON |

And a response table:

| Field | Mock upstream returns | Response filter | Client must observe |
|---|---|---|---|
| Status | `201 Created` | Unchanged | 201 |
| `Content-Type` | `application/json` | Unchanged | JSON |
| Header `X-Upstream-Result` | `v1` | Unchanged | `v1` |
| Header `X-Edge-Test` | Absent | `AddResponseHeader` | `enabled` |
| Body | `{"accepted":true}` | Unchanged | Equivalent JSON |

**These two tables form the test oracle**: an expectation source independent of Gateway code. If you generate expected paths using the same helper function used in the production filter, you copy bugs into the test and get false positives.

## 5. Test Route Configuration for Gateway Server WebFlux

### 5.1. Namespace by Version

Common WebFlux 4.x documentation defines routes under:

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: example
          uri: http://localhost:8081
          predicates:
            - Path=/edge/**
~~~

In **Server WebFlux 5.x**, configuration lives under:

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: example
              uri: http://localhost:8081
              predicates:
                - Path=/edge/**
~~~

These two snippets are **release alternatives**, not two routes to declare together. For Gateway Server Web MVC, the property is `webmvc` and the Java filter APIs also differ. Unbound route config produces 404s in tests even when the YAML itself is valid syntax.

### 5.2. Dedicated Integration Test Configuration

In the sample project, create **`src/test/resources/application-gateway-contract.yml`** (an **example path in this lesson**, not a file to create in the current repository):

~~~yaml
server:
  port: 0

spring:
  cloud:
    gateway:
      routes:
        - id: contract-proxy
          uri: ${test.backend.uri}
          predicates:
            - Path=/edge/**
          filters:
            - StripPrefix=1
            - SetRequestHeader=X-Gateway-Source, gateway-test
            - RemoveRequestHeader=X-Debug-Only
            - AddResponseHeader=X-Edge-Test, enabled
~~~

This targets **Gateway Server WebFlux 4.x**. The test activates profile `gateway-contract` and uses `@DynamicPropertySource` to inject `test.backend.uri` pointing at the mock HTTP server's **dynamically assigned port**.

Filter breakdown:

- `Path=/edge/**` matches requests starting with `/edge/`.
- `StripPrefix=1` removes the `edge` segment; `/edge/echo` becomes `/echo`.
- `SetRequestHeader` **replaces** any value for that header name with `gateway-test`, discarding the client's `spoofed` value.
- `RemoveRequestHeader` **strips** the client-sent header before the outbound hop.
- `AddResponseHeader` attaches a header to the **client-bound response**, not the mock-bound request.
- No `Retry`, `SetStatus`, `ModifyRequestBody`, or `ModifyResponseBody` exists on this route, keeping the "pass-through proxy" contract crisp.

An isolated test must know every filter applied. If the project defines `default-filters` or `GlobalFilter`s, include them in expectations or use an isolated test profile—never disable production security filters just to simplify tests.

### 5.3. Switching to WebFlux 5.x Configuration

When running this lesson on Gateway WebFlux 5.x, keep all route entries identical and update the parent key:

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: contract-proxy
              uri: ${test.backend.uri}
              predicates:
                - Path=/edge/**
              filters:
                - StripPrefix=1
                - SetRequestHeader=X-Gateway-Source, gateway-test
                - RemoveRequestHeader=X-Debug-Only
                - AddResponseHeader=X-Edge-Test, enabled
~~~

Choose **one** namespace matching your starter and release. If tests get an immediate Gateway `404` and the mock sees zero requests, inspect **config binding and route matching before blaming upstream**.

## 6. Test Dependencies

For a Maven Gateway WebFlux 4.x project already using a compatible Spring Boot parent/BOM and Spring Cloud BOM:

~~~xml
<!-- Gateway dependency managed by the matching release train. -->
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-gateway</artifactId>
</dependency>

<!-- JUnit 5, AssertJ, Spring Test, and WebTestClient tools -->
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>

<!-- Mock upstream HTTP server; sample uses 4.x API -->
<dependency>
    <groupId>com.squareup.okhttp3</groupId>
    <artifactId>mockwebserver</artifactId>
    <version>4.12.0</version>
    <scope>test</scope>
</dependency>
~~~

**Version and dependency-management notes:**

- `spring-cloud-starter-gateway` was the standard name prior to the `spring-cloud-starter-gateway-server-webflux` split in newer releases. Pick your project's matching starter.
- The Java example below uses **MockWebServer 4.x** APIs (`MockResponse`, `MockWebServer`, `RecordedRequest`); 5.x has a different API requiring matching updates.
- If your organization pins MockWebServer via a BOM or version catalog, use the approved version instead of copying `4.12.0` blindly.
- Never add MVC's `spring-boot-starter-web` into a Gateway WebFlux test just to "have an HTTP server".
- Projects with Spring Security enabled by default must supply test identities/tokens or security configs; matching a route does not bypass authentication.

## 7. Complete Integration Test: `WebTestClient` + `MockWebServer`

**Goal:** send a POST to the live Gateway, make the mock upstream return 201, and verify **both the outbound request and the final client response**.

### 7.1. Test Class

~~~java
package example.gateway.testing;

import java.io.IOException;
import java.util.concurrent.TimeUnit;

import okhttp3.mockwebserver.MockResponse;
import okhttp3.mockwebserver.MockWebServer;
import okhttp3.mockwebserver.RecordedRequest;

import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.Test;

import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.SpringBootTest.WebEnvironment;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.http.MediaType;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(webEnvironment = WebEnvironment.RANDOM_PORT)
@ActiveProfiles("gateway-contract")
class GatewayForwardingContractTest {

    // Shared within this sample class only: methods do not run in parallel.
    private static final MockWebServer upstream = startUpstream();

    @LocalServerPort
    int gatewayPort;

    private static MockWebServer startUpstream() {
        MockWebServer server = new MockWebServer();
        try {
            server.start();
            return server;
        } catch (IOException ex) {
            throw new ExceptionInInitializerError(ex);
        }
    }

    @DynamicPropertySource
    static void configureTarget(DynamicPropertyRegistry registry) {
        registry.add("test.backend.uri", () -> upstream.url("/").toString());
    }

    private WebTestClient client() {
        return WebTestClient.bindToServer()
                .baseUrl("http://localhost:" + gatewayPort)
                .build();
    }

    @Test
    void forwardsPathHeadersBodyAndStatus() throws Exception {
        upstream.enqueue(new MockResponse()
                .setResponseCode(201)
                .addHeader("Content-Type", "application/json")
                .addHeader("X-Upstream-Result", "v1")
                .setBody("{\"accepted\":true}"));

        String payload = "{\"item\":\"pen\",\"quantity\":2}";

        client().post()
                .uri("/edge/echo?request=integration")
                .header("X-Gateway-Source", "spoofed")
                .header("X-Debug-Only", "must-not-leak")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(payload)
                .exchange()
                .expectStatus().isCreated()
                .expectHeader().contentType(MediaType.APPLICATION_JSON)
                .expectHeader().valueEquals("X-Upstream-Result", "v1")
                .expectHeader().valueEquals("X-Edge-Test", "enabled")
                .expectBody()
                .jsonPath("$.accepted").isEqualTo(true);

        RecordedRequest received =
                upstream.takeRequest(5, TimeUnit.SECONDS);

        assertThat(received).isNotNull();
        assertThat(received.getMethod()).isEqualTo("POST");
        assertThat(received.getPath())
                .isEqualTo("/echo?request=integration");
        assertThat(received.getHeader("X-Gateway-Source"))
                .isEqualTo("gateway-test");
        assertThat(received.getHeader("X-Debug-Only")).isNull();
        assertThat(received.getHeader("Content-Type"))
                .startsWith("application/json");
        assertThat(received.getBody().readUtf8())
                .isEqualTo(payload);
    }

    @Test
    void preservesAnUpstream422WithoutSetStatusOrFallback()
            throws Exception {
        upstream.enqueue(new MockResponse()
                .setResponseCode(422)
                .addHeader("Content-Type", "application/json")
                .setBody("{\"code\":\"INVALID_INPUT\"}"));

        client().post()
                .uri("/edge/validate")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue("{\"quantity\":0}")
                .exchange()
                .expectStatus().isEqualTo(422)
                .expectBody()
                .jsonPath("$.code").isEqualTo("INVALID_INPUT");

        RecordedRequest received =
                upstream.takeRequest(5, TimeUnit.SECONDS);
        assertThat(received).isNotNull();
        assertThat(received.getPath()).isEqualTo("/validate");
    }

    @Test
    void missingRouteDoesNotHitTheUpstream() {
        int before = upstream.getRequestCount();

        client().get()
                .uri("/unmatched/path")
                .exchange()
                .expectStatus().isNotFound();

        assertThat(upstream.getRequestCount()).isEqualTo(before);
    }

    @AfterAll
    static void shutdownMock() throws IOException {
        upstream.shutdown();
    }
}
~~~

### 7.2. Why Is This Test Stronger Than Asserting Status Alone?

**Client side:** checks 201, `Content-Type`, upstream header `X-Upstream-Result`, Gateway-added `X-Edge-Test`, and body `accepted=true`.

**Upstream side:** MockWebServer provides `RecordedRequest` to assert:

- Method is POST.
- Actual path is `/echo`, proving `StripPrefix=1` worked.
- Query `request=integration` stayed intact.
- Header `X-Gateway-Source` was overwritten from `spoofed` to `gateway-test`.
- `X-Debug-Only` was stripped before reaching the backend.
- `Content-Type` stayed JSON.
- Raw JSON body at the mock equals the client's payload because no body rewrite runs on this route.

The `422` mock response in the second test proves the Gateway **does not blindly turn upstream 4xxs into 200/500** when no status-mapping filter/handler applies. The third test proves **unmatched requests never reach upstream**. If the app defines a local handler for `/unmatched/path`, adjust the 404 expectation per contract while still asserting upstream request count stays unchanged.

### 7.3. Things to Keep Stable

- The sample class assumes **test methods do not run in parallel**, since every method shares the `upstream.enqueue(...)` queue. If JUnit parallel execution is enabled, isolate a mock server/context per test or annotate with `@Execution(SAME_THREAD)`.
- Never assert specific port numbers. Both Gateway and mock use **ephemeral ports**.
- `@DynamicPropertySource` injects properties **before the `ApplicationContext` binds Gateway routes**. Do not mutate properties after route creation expecting automatic route refreshes.
- `MockWebServer.takeRequest(timeout)` must include a timeout so CI never hangs on route mismatches.
- Never let other tests sharing a cached Spring context keep calling a shut-down `MockWebServer`; separate classes/profiles or manage lifecycles cleanly.
- This test **does not boot a real `order-service`**; it simulates the upstream HTTP server and captures requests at the network boundary.
- When real security, rate limiting, or retries are active, expand expectations accordingly; never quietly disable security filters in production just to ease testing.

## 8. Verifying Paths: Route Predicates, `StripPrefix`, and Queries

### 8.1. Minimum Paths to Test

A route with `Path=/edge/**` and `StripPrefix=1` should cover this matrix:

| Input path | Expected upstream path | What to verify |
| --- | --- | --- |
| `/edge/echo` | `/echo` | Drops one segment |
| `/edge/v1/orders/42` | `/v1/orders/42` | Keeps remaining segments |
| `/edge/echo?lang=vi` | `/echo?lang=vi` | Query does not vanish |
| `/edge/` | `/` if route and filters support that path | Trailing-slash edge case |
| `/other/echo` | Not proxied by this route | Route predicate |
| `/edge-old/echo` | Not matched as `/edge/**` | Segment boundary |
| `/edge/a%20b` | Space-encoded path semantics intact | URI encoding |
| `/edge/a%2Fb` | Follows encoded-slash policy | Proxy/router/security check |
| `/edge/a/../admin` | Normalized or blocked per policy | Path traversal and matcher behavior |

**Do not claim every edge case behaves identically across all Netty/Spring/ingress versions.** Specifically, encoded slashes (`%2F`), dot segments, and Unicode paths must be tested against a **real port and real/mock upstream** on your target release. Different proxies normalize paths at different stages.

### 8.2. Query Parameter Ordering and Encoding

If business logic requires only `lang=vi`, you need not assert exact byte order across multiple query params when clients/URI builders vary valid encodings.

Example:

~~~text
Client:   /edge/search?q=a%20b&lang=vi
Upstream: /search?q=a%20b&lang=vi
~~~

A business-level test may parse query params to assert `q == "a b"` and `lang == "vi"`; a raw URI/encoding test can assert `%20` if exact encoding preservation is part of the contract. Avoid calling `URLDecoder` carelessly on URI paths where `+` or encoded slashes carry distinct semantics.

### 8.3. `RewritePath` Must Test Regex Capture

WebFlux 5.x example:

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: rewrite-orders
              uri: http://localhost:8081
              predicates:
                - Path=/legacy/orders/**
              filters:
                - RewritePath=/legacy/orders/?(?<remaining>.*), /orders/$\{remaining}
~~~

Under `RewritePath` rules, `(?<remaining>.*)` captures the suffix; `$\{remaining}` is the **YAML-escaped syntax shown in Gateway docs** to prevent unwanted placeholder resolution. In real projects, verify that your YAML parser/property resolver delivered the exact replacement string to the filter.

Expected table:

| Client path | Upstream path |
| --- | --- |
| `/legacy/orders/42` | `/orders/42` |
| `/legacy/orders/42/items` | `/orders/42/items` |
| `/legacy/orders/` | `/orders/` if regex/route matches as configured |
| `/legacy/orders-old/42` | Does not match this route |

Never assert only that the client got 200: a mock matching both `/legacy/orders/42` and `/orders/42` returns 200 either way and hides rewrite bugs.

### 8.4. Filter Ordering and Route Precedence

When `PrefixPath`, `StripPrefix`, `RewritePath`, and `SetPath` combine, the outcome depends on **execution order**. Likewise, a request may match multiple routes; never assume the "more specific" route always wins when `order` or route sources differ.

Verify:

1. Selected route has the expected ID and `order`.
2. Each path transformation step produces the expected intermediate output.
3. The backend receives the contract-compliant **final path**.
4. Competing routes that should not match are **never invoked**.
5. With `lb://`, instance selection and path transformation compose cleanly without building malformed URLs post-load-balancing.

## 9. Verifying Request Headers Sent Upstream

### 9.1. Headers Entering the Gateway Are Not Identical to Headers Reaching the Backend

The Gateway can:

- Add headers: `AddRequestHeader`.
- Overwrite headers: `SetRequestHeader`.
- Strip headers: `RemoveRequestHeader`.
- Change `Host`: `SetRequestHostHeader` or `PreserveHostHeader` per intent.
- Generate/sanitize `Forwarded` and `X-Forwarded-*` via filters and trust settings.
- Strip single-hop HTTP headers (hop-by-hop).
- Inject trace context via tracing instrumentation.

Tests should assert **contract-relevant business headers**, not demand the entire header set match identically between client and backend.

### 9.2. `AddRequestHeader` vs. `SetRequestHeader`

~~~yaml
filters:
  - AddRequestHeader=X-Lab-Tag, gateway
  - SetRequestHeader=X-Gateway-Source, edge
~~~

`AddRequestHeader` can produce multi-valued headers if the client also sends that header name. `SetRequestHeader` replaces prior values with one new value.

When a header carries **trusted identity/tenant metadata**, never just hardcode a route-level value while bypassing Spring Security. Derive it from the verified principal, enforce trust boundaries, and ensure downstreams validate trust independently.

### 9.3. Header Names Are Case-Insensitive

`X-Gateway-Source` and `x-gateway-source` are equivalent in HTTP. Mock HTTP libraries normally support case-insensitive `getHeader(...)` lookups.

**Never assert absolute header ordering:** HTTP/1.1 and HTTP/2 serialize headers differently, and proxies add `Via`, `Forwarded`, or client-generated headers.

### 9.4. Hop-by-Hop and Computed Headers

Headers like `Connection`, `Keep-Alive`, `Transfer-Encoding`, `TE`, and `Upgrade` receive special handling. Gateway WebFlux runs `HttpHeadersFilters` and `RemoveHopByHop` prior to outbound routing.

Therefore:

- Do not require the backend to see the client's exact `Connection: keep-alive`.
- Do not assert `Transfer-Encoding: chunked` survives every hop identically.
- `Content-Length` can change or disappear during streaming or body rewrites.
- HTTP/2 header rules differ from HTTP/1.1.
- Outbound `Host` depends on target URI and preserve-host policy.

Test these headers **only when they are explicitly part of the contract**, not as generic route-success checks.

### 9.5. `X-Forwarded-For` / `Proto` Are a Trust Boundary

Clients can forge `X-Forwarded-For` and `X-Forwarded-Proto`. Behind an ingress, accepting, generating, or appending forwarded headers must follow **configured trusted proxies** for your release.

Tests should cover:

1. Request from a trusted proxy: backend receives client scheme/host per policy.
2. Direct request from an untrusted client: client-supplied headers never become trusted identity.
3. Multiple proxy hops: list ordering and precedence match the contract.
4. HTTPS inbound / HTTP outbound: backend seeing `proto=https` does not mean the outbound socket uses TLS.

**Never use client-sent `X-Forwarded-For` as a rate-limit or authorization key** unless the proxy chain is verified. This affects both security and correctness.

## 10. Verifying Client-Side Response Headers

Gateway responses can preserve, add, strip, or deduplicate headers:

| Scenario | Upstream returns | Gateway filter | Client expects |
| --- | --- | --- | --- |
| Preserve header | `X-Upstream-Result: v1` | None | `v1` |
| Add header | No `X-Edge-Test` | `AddResponseHeader=...,enabled` | `enabled` |
| Overwrite | `X-Feature: old` | `SetResponseHeader=X-Feature,new` | `new` |
| Remove | `X-Internal-Debug: secret` | `RemoveResponseHeader=X-Internal-Debug` | Absent |
| Duplicate CORS header | Both Gateway and upstream emit it | `DedupeResponseHeader` per strategy | Single contract value |
| Redirect | `Location: http://internal/...` | `RewriteLocationResponseHeader` or policy | Valid public URL |

**Never assume all upstream headers pass through untouched.** Response headers like `Transfer-Encoding`, `Connection`, `Content-Length`, compression headers, and `Set-Cookie` follow protocol rules and may be modified by Gateway or upstream filters.

### 10.1. `DedupeResponseHeader` and CORS

If both the Gateway and backend emit `Access-Control-Allow-Origin`, browsers may reject duplicate values.

CORS tests should verify:

- Allowed origins match policy exactly, with no `*` when credentials are allowed.
- `Access-Control-Allow-Credentials` aligns with allowed origins.
- `OPTIONS` preflight respects routing/security rules.
- Duplicate headers are deduplicated per the chosen strategy.
- Rejected origins are **never re-opened by upstream headers**.

Never treat CORS as authentication: `curl` and Postman bypass browser CORS checks entirely. Test JWT/session authorization separately.

### 10.2. Never Compare Cookies by Concatenating All Headers into One String

`Set-Cookie` can appear on multiple lines, and `Secure`, `HttpOnly`, `SameSite`, `Path`, and `Domain` attributes must match the contract individually. Sorting and joining all response headers into a single string causes flaky tests from serialization or ordering shifts.

Especially when one Gateway fronts multiple backends, test `Secure`/domain/path cookie scopes to prevent session collisions or leaks to wrong domains.

## 11. Verifying Request Bodies: JSON, Form, and Binary

### 11.1. Without Body Transformation

When a route runs only `StripPrefix`, `SetRequestHeader`, and `RemoveRequestHeader`, request bodies generally pass through per HTTP semantics. For small JSON payloads, tests can assert exact UTF-8 equality as in section 7.

**Yet "unchanged body" has two levels:**

- **Byte-level equality:** upstream bytes match client bytes identically. Use for digital signatures, binaries, or strict byte contracts.
- **Semantic equality:** JSON parses into identical objects/fields despite whitespace, key ordering, or encoding differences. Use when contracts care only about data.

When routes use `ModifyRequestBody`, `CacheRequestBody`, or custom JSON serializers, byte-level equality may be **inappropriate** because the filter intentionally alters representation.

### 11.2. Compare JSON by Schema When Transformations Apply

Input example:

~~~json
{
  "sku": "PEN-01",
  "quantity": 2
}
~~~

A transformation filter may normalize it to:

~~~json
{"sku":"PEN-01","quantity":2,"source":"gateway"}
~~~

Tests should assert:

1. `sku` and `quantity` remain accurate.
2. `source` is injected per policy.
3. `Content-Type` matches, typically `application/json`.
4. `Content-Length` does not retain the stale **pre-rewrite** length.
5. The backend parses the JSON cleanly.
6. Sensitive fields are never copied unexpectedly.

Avoid comparing raw JSON strings whenever whitespace/key ordering is not part of the contract. For JSON contracts, use `jsonPath`, Jackson `JsonNode`, `JSONAssert`, or schema validation.

### 11.3. Empty Bodies, Null, and `Content-Type`

Distinguish:

| Input | What to check |
| --- | --- |
| Bodyless GET | No unexpected JSON body synthesized |
| POST with `Content-Length: 0` | Backend receives valid empty body |
| POST with `Content-Type: application/json` and empty body | Error/validation matches contract |
| JSON literal `null` | Never confused with **no body** |
| Malformed JSON | Proper status/error mapping without stack traces |
| `text/plain; charset=UTF-8` request | Unicode preserved with right charset |
| URL-encoded form | Form field order/values intact |
| Multipart upload | Boundaries, filenames, file bytes, size limits |
| Binary `application/octet-stream` | Byte arrays or checksums match |

For `ModifyRequestBody`, Spring Cloud Gateway WebFlux provides Java DSL support with explicit semantics for **missing bodies**. Write a dedicated test for an absent body rather than sending `{}` and assuming it covers the same case.

### 11.4. Never Read a `DataBuffer` Twice Carelessly

In WebFlux, request bodies are reactive `DataBuffer` streams. A custom filter that consumes or frees buffers improperly can leave upstream with an **empty body**, leak memory, or block the event loop.

Never attach a test logging filter that calls `subscribe()` independently to "peek at the body" and starves the main pipeline. Never call `block()` on a Netty event loop. When reading and replaying bodies, use compatible caching/decorating mechanisms, bound payload sizes, and release buffers properly.

**Contract tests should capture bodies at the mock HTTP upstream** rather than hooking pervasive body-reading filters into the reactive pipeline.

### 11.5. Large Payloads and Streaming

For uploads and streaming:

- Never call `.expectBody(String.class)` on multi-hundred-MB responses.
- Test streaming/chunk behavior appropriately; network chunk boundaries **need not stay identical** across proxies.
- Compare byte counts, SHA-256 checksums, and content types when contracts require them.
- Test `413 Payload Too Large` with `RequestSize`/ingress limits.
- Test client disconnects/cancellations to verify Gateway and upstream resource cleanup.
- Verify backpressure and memory stability under `CacheRequestBody`, `Retry`, or `ModifyBody`.
- Enforce bounded test timeouts so infinite upstream streams never hang CI.

For signed webhooks/payloads, verify signatures against the **bytes received at the backend**, not just parsed JSON fields.

## 12. Verifying Response Bodies: Upstream → Gateway → Client

Like request bodies, responses may:

- Pass through byte-for-byte in plain proxying.
- Be transformed by `ModifyResponseBody` (Java DSL).
- Be compressed/decompressed per `Content-Encoding` and client capabilities.
- Be replaced by a `CircuitBreaker` fallback.
- Be omitted on 204/304/HEAD responses.
- Receive header metadata or become redirects.

Status 200 + JSON body **is not enough** if the response was supposed to strip a secret field.

### 12.1. Example Filter-Transformed Response

Upstream:

~~~json
{"id":42,"secretInternalCode":"ABC","name":"Pen"}
~~~

Public contract:

~~~json
{"id":42,"name":"Pen"}
~~~

Tests must assert:

- Public body contains `id` and `name`.
- Public body **does not** contain `secretInternalCode`.
- `Content-Type` and status are right.
- `Content-Length`/compression align with the transformed body.
- JSON still parses cleanly on clients.

For `ModifyResponseBody` in Gateway WebFlux, documentation specifies configuring it via **Java DSL**. Never put `ModifyResponseBody=...` as a shortcut in YAML unless your project has written a custom factory for it.

### 12.2. Empty Responses Are Special Cases

Statuses like `204 No Content` carry no body under HTTP semantics. Tests should verify:

~~~text
Upstream: 204 No Content
Client:   204 No Content
Body:     empty
~~~

A test trying to parse JSON from a 204 response will fail even when the Gateway behaves accurately.

On `HEAD`, header metadata may appear while the client receives no response body. On `304 Not Modified`, caching rules govern headers; never force JSON bodies onto those responses.

### 12.3. `Content-Encoding`

If the backend returns `Content-Encoding: gzip`, the Gateway or client may handle compression depending on HTTP client/server settings. Tests must clarify whether they verify:

- Wire bytes are compressed/decompressed cleanly.
- Client reads valid JSON after decompression.
- `Content-Encoding`/length headers stay consistent.
- Response bodies are never double-compressed.

Do not compare raw bytes of a gzipped response against plaintext JSON and conclude the Gateway corrupted the body. Use mocks capable of testing both wire representation and decoded semantics.

## 13. Verifying HTTP Statuses: Origin Matters

Statuses originate from several places:

| Scenario | Who may generate the status | What to observe |
|---|---|---|
| Request matches no route | Gateway/WebFlux handler mapping | Mock upstream **receives no request** |
| Blocked by Security `401/403` | Spring Security `WebFilter` ahead of Gateway routes | Upstream receives nothing; identity policy enforced |
| Rate limiter returns `429` | `RequestRateLimiter` or pre-Gateway layer | Upstream receives nothing if blocked pre-routing |
| Upstream `201` | Backend | Gateway relays 201 unless overridden by filter |
| Upstream `422` | Backend | Gateway relays 422 without status mapping |
| Upstream `500/503` | Backend | Upstream hit recorded; final status depends on `Retry`/CB |
| `lb://` has zero instances | LoadBalancer/routing | Commonly 503 by default, configurable to 404 |
| TCP connection refused | Gateway HTTP client/routing error | Backend sees no HTTP request; status per error handler |
| TLS handshake failed | Gateway HTTP client | Backend app never sees HTTP request |
| `SetStatus=...` | Gateway response filter | Client status intentionally differs from backend |
| `CircuitBreaker` fallback | Gateway/fallback handler | Client may see alternate status/body |
| Timeout after backend commit | Gateway client/timeout policy | Backend may already have committed side effects |

**Never assume every `ConnectException` must return 502 or every timeout must return 504**: error mapping varies by Gateway version, Boot error handling, and custom filters. Define expected policies explicitly, or assert error classes and whether upstream was called.

### 13.1. Distinguishing Two Kinds of 404

`GET /not-a-route` matches no route → Gateway may return 404 while mock upstream **receives zero requests**.

`GET /edge/missing` matches a route → mock upstream receives `GET /missing` and **returns 404**. The Gateway relays 404 to the client unless overridden.

Both look like 404 to the client, yet stem from completely different causes. Proper tests assert **upstream request counts** and recorded paths.

### 13.2. `SetStatus` Overrides Upstream Status

~~~yaml
filters:
  - SetStatus=BAD_REQUEST
~~~

This intentionally changes the final status to 400 (depending on the route/filter pipeline). When testing a route with `SetStatus`, you cannot demand "the Gateway must preserve the backend's 201".

In Gateway WebFlux, `SetStatus` docs support exposing an original-status header via properties/config. If enabled, assert that header safely while ensuring internal details are not leaked unnecessarily.

### 13.3. Redirects Must Verify Both Status and `Location`

When the backend or Gateway returns 302/307/308, tests should verify:

- Exact status code.
- `Location` points to the expected public origin/path.
- Internal `localhost` hosts or private DNS names are not leaked.
- For `307/308`, HTTP method preservation holds.
- No redirect loops occur.
- Cookie/header security policies remain intact.

**`WebTestClient` should not silently auto-follow redirects** when tests need to inspect the initial 3xx status and `Location`. Never configure your test HTTP client to swallow the very 3xx response you need to assert.

## 14. `Retry`: One Client Request Can Trigger Multiple Upstream Requests

Example:

~~~yaml
filters:
  - name: Retry
    args:
      retries: 2
      statuses:
        - SERVICE_UNAVAILABLE
      methods:
        - GET
~~~

If the mock upstream returns `503`, `503`, `200`, a single client GET can generate **3 attempts** (initial call + 2 retries). Alongside asserting final status 200, **verify how many requests the mock received and that path/headers/body stayed consistent on every attempt**.

### 14.1. Deterministic Scenario

~~~text
Mock response queue:
  attempt #1 -> 503
  attempt #2 -> 503
  attempt #3 -> 200

Client:
  GET /edge/items/42

Assertions:
  final status = 200
  upstream request count delta = 3
  each upstream path = /items/42
  correlation ID stable per client request (if required by policy)
~~~

Never run `Retry` tests against a mock whose response order is uncontrolled. Never verify retries by total latency alone, since backoff and jitter introduce variance.

### 14.2. Never Enable POST Retries Carelessly

On order/payment POSTs, if the backend committed before the response dropped, replaying creates **duplicate transactions**. Tests require `Idempotency-Key`, atomic backend deduplication, and proof of a single side effect.

Spring Cloud Gateway's `Retry` filter can **cache request bodies** when retrying body-bearing methods, increasing memory pressure. Never use huge test payloads to "test 100 retries" outside controlled environments.

### 14.3. Filter Order and Side Effects

A filter ordered **after `Retry`** executes again on every attempt. If a custom filter injects a random header or mutates bodies non-idempotently, each attempt differs.

Tests must verify the contract across:

- One client request.
- N upstream attempts.
- One final response.
- Per-attempt headers/bodies matching policy.
- Zero unintended side effects.

## 15. Circuit Breakers, Fallbacks, and Rate Limiting

### 15.1. Circuit Breaker

When the backend fails repeatedly, a circuit breaker can:

- Allow requests to upstream in `CLOSED`/`HALF_OPEN` states.
- Short-circuit requests before upstream when `OPEN`.
- Route requests to a fallback handler.

In tests, observe both the client response **and** upstream request count. If a fallback returns 200, checking status alone mistakes fallback responses for backend success. Use fallback markers or metrics, and never let fallbacks impersonate successful write transactions.

### 15.2. Rate Limiting

For `RequestRateLimiter`, verify:

1. The key resolver derives keys from verified identity, never untrusted client headers.
2. Within quota, upstream receives requests.
3. Past quota, the Gateway rejects with the configured status (normally `429`).
4. The upstream counter **does not increment** on blocked requests.
5. Quota/`Retry-After` headers, if emitted, match contract rather than hardcoded guesses.
6. Tests isolate keys across principals to prevent flakiness from shared Redis state.

Control token buckets and windows with test clocks/configs or generous tolerances instead of brittle real-time millisecond assertions.

### 15.3. Security Blocks Ahead of Routes

Spring Security WebFlux can return 401/403 **before the Gateway route chain runs**. When a request is rejected prior to route matching, a route-level `AddResponseHeader` filter will not execute.

Thus an assertion like "every 401 always carries `X-Edge-Test`" fails if that header comes from a **route-scoped `GatewayFilter`**. If pre-route error responses require correlation/security headers, attach them in a `WebFilter`/security layer and test that lifecycle explicitly.

## 16. Testing `lb://` and Service Discovery Without Production Registries

Route example:

~~~yaml
- id: orders-lb
  uri: lb://ORDER-SERVICE
  predicates:
    - Path=/api/orders/**
  filters:
    - StripPrefix=1
~~~

With `lb://`, the logical host is not a DNS name—it is a **service ID** for Spring Cloud LoadBalancer. Good tests verify:

- Gateway selects an instance from a test-scoped `ServiceInstance` supplier.
- The mock backend at that instance receives the expected path.
- Requests use HTTP/HTTPS matching instance/security policy.
- When no instance exists, the Gateway returns the policy status (typically 503 by default, or 404 if configured).
- With multiple instances, never hardcode "request #1 must hit A" unless the test deterministically pins the algorithm/supplier.

### 16.1. Using `SimpleDiscoveryClient` in the Lab

When Spring Cloud Commons supports `SimpleDiscoveryClient`, define test instances via configuration:

~~~yaml
spring:
  cloud:
    discovery:
      client:
        simple:
          instances:
            ORDER-SERVICE:
              - uri: http://localhost:18081
~~~

This requires a mock on 18081 or a dynamic port property; **never claim `lb://` works unless the mock actually received the request**. In continuous CI runs, inject service instance URIs via dynamic properties/test suppliers instead of fixed ports.

Having an instance in discovery does not prove route path/headers/body are right; still inspect `RecordedRequest` on the chosen instance.

### 16.2. `isSecure`, TLS, and Certificates

When `ServiceInstance.isSecure()` is `true`, the target may require HTTPS; if the mock backend speaks only HTTP while the Gateway tries HTTPS, tests fail at TLS before the app handles the request.

Split your tests:

- Plain HTTP routing to verify paths, headers, and bodies.
- HTTPS upstream with a test CA/cert to verify trust, hostnames, and SNI.
- mTLS if required by architecture, using valid test client certs.
- Special scheme overrides if routes use `lb:https://...` or release-specific variants.

Never enable an **insecure trust manager** in production and cite a "passing" test as proof of TLS security.

## 17. Testing Errors: DNS, Connection Refused, Timeouts, and Resets

A mock upstream can simulate several failure modes:

| Fault | What to observe | What not to assume |
| --- | --- | --- |
| Backend returns HTTP 500 | Backend hit recorded; client status follows filter policy | Never assume Gateway caused the error |
| Backend returns HTTP 503 | HTTP 503 received; may retry | Never assume backend did no work |
| Port not listening | Connection fails before full request sent | Does not always map to exact 502 |
| Bad DNS target | Gateway cannot resolve host | Not always identical to route-miss 404 |
| TCP reset mid-response | Client sees connection error/partial body | Never assume body remained intact |
| Response slower than timeout | Gateway times out; backend may keep running | Never auto-retry writes |
| TLS handshake failure | Gateway fails cert/key verification | Not an upstream business 500 |
| Client disconnects | Cancellation, cleanup/connection reset | Never assume backend aborted work |

Tests should:

1. Record the mock-injected fault type.
2. Observe Gateway error handling, redacted logs, and contract-compliant responses.
3. Assert upstream request counts when faults happen post-send.
4. Bound every test with timeouts—never wait forever.
5. Account for attempt counts and backoffs when `Retry` is active.
6. Avoid hardcoding a "universal default status across all versions" unless your project defines that mapping explicitly.

## 18. Header and Body Security in Integration Tests

In a Gateway, correctness tests must also validate **trust boundaries**:

### 18.1. Minimum Requirements

- Which backends are authorized to receive `Authorization`? Do `TokenRelay` or service auth assertions match policy?
- Are client `X-User`, `X-Role`, and `X-Tenant-Id` headers stripped before backends could treat them as trusted?
- Can clients forge `X-Request-Id` or send unbounded lengths?
- Are `Forwarded`/`X-Forwarded-*` accepted only from configured trusted proxies?
- Do request/response bodies expose secrets or PII outside the contract?
- Could a route reach non-allowlisted hosts or internal metadata IPs?
- Are CORS/preflight policies wider than intended?
- Are trace headers/baggage ever treated as credentials?

### 18.2. Never Put Real Secrets into Fixtures or Logs

Use synthetic placeholders such as:

~~~text
Authorization: Bearer test-token-redacted
X-Request-Id: req-demo-42
X-Debug-Only: must-not-leak
~~~

Never log raw `Authorization`/cookies/sensitive bodies in production just to debug tests. CI reports and `RecordedRequest` logs store HTTP headers and bodies; restrict access, use synthetic fixtures, purge sensitive artifacts, and enforce redaction.

### 18.3. Preventing Header Spoofing

A canonical case:

~~~text
Client sends:
  X-Gateway-Source: spoofed

Gateway runs:
  SetRequestHeader=X-Gateway-Source, gateway-test

Upstream sees:
  X-Gateway-Source: gateway-test
~~~

Section 7's test demonstrates this case. Still, `X-Gateway-Source` is only a filter marker—**not proof of authentication**. For user identity, verify the authenticated principal, block client spoofing, and establish a trusted upstream boundary.

## 19. How Tracing and Metrics Aid Test Investigation

With distributed tracing (Micrometer Tracing / OpenTelemetry), tests can correlate Gateway and backend calls via W3C `traceparent`/`tracestate`. Keep in mind:

- Trace IDs match across the logical trace while per-hop span IDs **differ**.
- Never fake a static `traceparent` via `SetRequestHeader` "just to make tracing pass".
- Custom `WebClient` beans inside Gateways need instrumented builders for context propagation.
- Sampling may omit traces upstream even when trace headers are sent.
- Retries create multiple HTTP attempts and multiple child spans.
- Requests rejected with 401/429 pre-routing have **no upstream span**.

Metrics should be separated:

| Metric | Meaning |
|---|---|
| Client request count | Requests entering Gateway |
| Upstream attempt count | Outbound HTTP calls actually sent to backends |
| Response status count | Client responses grouped by status |
| Route-level latency | Processing duration across Gateway |
| Retry count | Retries beyond initial attempts |
| Circuit breaker state | `OPEN` / `HALF_OPEN` / `CLOSED` |
| Backend receive count | Requests recorded by mock/service |

Never use raw request IDs, trace IDs, or user-ID-bearing paths as **unbounded-cardinality metric labels**. Stick to bounded route IDs, status/outcome tags, and service categories; use logs/traces for per-request inspection.

## 20. Structuring Test Suites to Prevent Flakes and Catch More Bugs

### 20.1. Factors to Control

| Flakiness risk | Mitigation |
|---|---|
| Ports 8080/8081 already in use | Gateway `RANDOM_PORT`; dynamic-port mock upstream |
| Flaky staging upstream | Local mock server |
| Contention on mock response queue | Per-class/test isolation, sequential methods, or deterministic `Dispatcher` |
| Wrong YAML route namespace | Verify effective routes at startup; dedicated test profile |
| Shared Redis state | Dedicated test Redis/isolated key prefixes or stubs |
| Retry/backoff jitter | Disable jitter in unit tests or use margins/test clocks |
| Test hangs when route skips backend | `takeRequest(timeout, unit)` |
| Unclear which request hit backend | Marker headers/correlation + recorded request logs |
| Mixing YAML and Java DSL routes | Enable only one source per test scenario |
| Backend response body unflushed | Explicit mock responses; dedicated streaming tests |
| HTTP compression alters bytes | Assert semantic JSON or explicit compression config |
| Auth test lacks principal | Use test JWT mocks or dedicated test IdP |
| Test runs under altered deployment config | Document property overrides and tested versions |
| Timeouts too tight on busy CI runners | Realistic deadlines; avoid fixed `sleep`s |
| Bug occurs on only one Gateway replica | Per-node synthetic checks in staging |

### 20.2. Never Use `Thread.sleep()` Hoping the Gateway "Probably Finished"

Tests waiting for an HTTP request should use `takeRequest(5, TimeUnit.SECONDS)`, Reactor `StepVerifier`, or bounded polling. Avoid scattering `Thread.sleep(3000)`: suites become slow yet still flake under CI CPU spikes.

Never call `block()` inside a Gateway filter for test determinism. Only test-thread client code awaiting responses should block boundedly.

### 20.3. Never Share a FIFO-Enqueued `MockWebServer` Across Parallel Tests

If Test A enqueues 201 and Test B enqueues 422, yet upstream calls arrive in the opposite order, both tests fail unpredictably.

Strategies:

1. Dedicated mock upstream and Spring context per test when needed.
2. A `Dispatcher` branching by method/path or request marker.
3. Run methods sharing one queue **sequentially**.
4. Clear/reset state with zero in-flight requests between tests.
5. When `Retry` is active, enqueue enough responses for every expected attempt.

## 21. Complete Contract Test Matrix

| ID | Input/scenario | Assert on mock upstream | Assert on client |
| --- | --- | --- | --- |
| P01 | GET `/edge/items/42` | GET `/items/42` | Contract status/body |
| P02 | POST `/edge/echo?x=1` | POST `/echo?x=1` | 201/JSON |
| P03 | `/edge-old/path` | Zero requests | No-route status |
| P04 | `/edge/a%20b` | Path encoding matches policy | No 500 from encoding |
| P05 | `/edge/a%2Fb` | Encoded-slash semantics per policy | No auth/path bypass |
| P06 | `RewritePath` with named group | Exact rewritten path | Expected behavior |
| H01 | Client spoofs header | Header overwritten | Ignores raw spoofed value |
| H02 | Client sends debug-only header | Backend does not receive it | Contract response |
| H03 | Multi-value header | Value count matches Add vs. Set | No unintended value leaks |
| H04 | Hop-by-hop header | Handled per RFC/Gateway policy | Request stays valid |
| H05 | Trusted forwarded header | Value sanitized/normalized | Untrusted client headers ignored |
| H06 | Backend returns `X-Upstream-Result` | Mock emits header | Client sees header unless stripped |
| H07 | Gateway `AddResponseHeader` | Not needed on mock | Client sees marker |
| H08 | Backend sets `Set-Cookie` | Cookie security policy enforced | Client sees valid attributes |
| B01 | Small JSON request | JSON fields/bytes match | Expected response body |
| B02 | JSON `null` vs. empty body | Distinguishes both cases | Status/validation per contract |
| B03 | URL-encoded form | Fields/charset intact | Contract status |
| B04 | Binary payload | Byte count/checksum matches | Body uncorrupted |
| B05 | Multipart upload | File bytes/metadata intact | No 413 below limit |
| B06 | Oversized request | Not proxied if blocked pre-routing | 413 per policy |
| B07 | `ModifyRequestBody` | Rewritten body accurate | Backend receives valid payload |
| B08 | `ModifyResponseBody` | Mock returns raw body | Internal field removed for client |
| S01 | Upstream 201 | Request received | Client 201 |
| S02 | Upstream 422 | Request received | Client 422 if unmapped |
| S03 | No route | Zero requests | 404 or policy mapping |
| S04 | Upstream 404 | Request received | Upstream 404 |
| S05 | Upstream 503 + `Retry` GET | Exact attempt count | Final response per queue |
| S06 | Rate limit deny | Request count unchanged | 429 per config |
| S07 | Security deny | Request count unchanged | 401/403 |
| S08 | Circuit breaker open | Zero upstream calls | Fallback/status per config |
| S09 | Backend 204 | Request received | 204, empty body |
| S10 | Redirect 307 | Per backend/fallback | 307 + valid `Location` |
| S11 | Connection refused | No backend HTTP response | Gateway error status per policy |
| S12 | TLS certificate failure | Backend app sees no valid request | TLS failure recorded |
| S13 | Client disconnect | Cancellation/cleanup | Not counted as fake success |
| S14 | Controlled POST `Retry` | Side effects never duplicated | Idempotency and contract response |

Not every test belongs in one giant class. Group suites by **path, headers, body, status, and resilience/security** so failures stay easy to triage.

## 22. Investigation Workflow When an Integration Test Fails

### 22.1. Client Gets 404, Mock Sees Zero Requests

Likely causes:

- `Path`/`Method` predicate did not match.
- Wrong namespace (`spring.cloud.gateway.routes` vs. `spring.cloud.gateway.server.webflux.routes`).
- Spring Security or another handler blocked earlier.
- Route `order` or another route source captured the request.
- Test targeted the wrong Gateway port or profile.

**First step:** inspect effective route definitions or startup logs in the **test profile**, then verify the request path. Do not tweak upstream responses when upstream never received a request.

### 22.2. Mock Sees Request, Yet Path Is Wrong

Likely causes:

- `StripPrefix` counts the wrong number of segments.
- `RewritePath` regex/replacement mismatch or YAML placeholder escaping issue.
- Filter ordering runs `PrefixPath` ahead of `StripPrefix`.
- Ingress context path or forwarded prefix interference.
- Misunderstood target URI.

**First step:** compare `RecordedRequest.getPath()` against the canonical expected path. Remove filters one by one in the **test profile** to isolate path transformations.

### 22.3. Mock Sees Right Path, Yet Header Is Wrong

Likely causes:

- `AddRequestHeader` used instead of `SetRequestHeader`, creating multi-values.
- Header stripped by `RemoveRequestHeader` or `HttpHeadersFilters`.
- Proxy configuration alters `Host`/`Forwarded` headers.
- Security/`TokenRelay` lacks a principal or token.
- Custom filter mutated the request without passing `chain.filter(mutatedExchange)`.

**First step:** assert the specific header, then check filter ordering and trust boundaries. Never dump full `Authorization`/cookie headers in CI logs.

### 22.4. Mock Sees Empty or Unparseable Body

Likely causes:

- Custom filter consumed `DataBuffer` without replaying.
- `ModifyRequestBody` serialized wrong schema/`Content-Type`.
- Test client omitted body or used wrong encoding.
- `Retry`/body caching/size limits altered behavior.
- Large body exceeded size or memory limits.

**First step:** test with a tiny JSON payload, checking raw bytes and `Content-Type` at the mock. Then expand to streaming/multipart.

### 22.5. Mock Returns 422, Client Sees 200 or 500

Likely causes:

- `SetStatus`, `CircuitBreaker` fallback, exception handler, or custom response filter rewrote status.
- Another test consumed the mock response queue.
- Gateway retried and got 200 on a later attempt.
- Test client auto-followed a redirect.
- Route pointed at a different backend.

**First step:** confirm the mock received that exact test's request, check FIFO responses, attempt counts, and active filters. Never assume backend status equals final client status when Gateway response policies apply.

### 22.6. Fails Only in CI, Passes Locally

Likely causes:

- Fixed port collision or differing DNS/proxy setups.
- Parallel test execution scrambling `MockWebServer` queues.
- Different app profile/namespace config.
- Overly tight timeouts on overloaded CI runners.
- Mock server shut down while Spring context still cached.
- Shared external Redis/k8s/test state.

**First step:** rerun the single failing test under an explicit profile, dynamic ports, and bounded timeouts; log redacted route ID, path, and status. Never "fix" it by inflating `Thread.sleep` blindly without root-cause analysis.

## 23. Capstone Exercise

**Context:** A Gateway exposes `/api/catalog/**` and `/api/orders/**`; catalog accepts GET, orders accepts POST. Each backend runs as its own mock server. The Gateway applies `StripPrefix`, `SetRequestHeader`, `RemoveRequestHeader`, `AddResponseHeader`, security, and optional GET `Retry`.

Requirements:

1. Create an isolated `gateway-contract` profile using your version's exact route namespace.
2. Run the Gateway on `RANDOM_PORT` with two dynamic-port mock upstreams.
3. Supply target URIs via `@DynamicPropertySource` or explicit test properties.
4. Test `GET /api/catalog/products/42` forwards as `/catalog/products/42`.
5. Test `POST /api/orders/create?source=mobile` forwards as `/orders/create?source=mobile`.
6. Send JSON and verify schema/raw body per contract without logging secrets.
7. Client sends `X-Gateway-Source: spoofed`; backend sees only the Gateway-enforced value.
8. Client sends `X-Debug-Only`; backend never sees it.
9. Backend returns 201/422/503; verify final statuses both with and without status-altering policies.
10. Backend sets `X-Upstream-Result`; Gateway sets `X-Edge-Test`; verify both on the client.
11. Test an unmatched path vs. a backend 404 to distinguish them via request counts.
12. Test `RewritePath` with nested segments and encoded paths per security policy.
13. Test `204 No Content`, malformed JSON, wrong `Content-Type`, and absent body.
14. Send a 1 MiB binary payload, verifying checksum and steady memory usage.
15. For GET `Retry`, mock returns 503 then 200; verify final status and exact attempt count.
16. For POST orders, simulate timeout after commit and verify idempotency / no blind retry.
17. Add Spring Security tests for missing tokens/scopes; prove upstream receives zero blocked calls.
18. With `lb://`, register test service instances and verify the chosen backend.
19. Observe trace IDs/route metrics without logging raw tokens or bodies.
20. Summarize a four-axis report (path/header/body/status) listing assertions run and any discrepancies found.

### Expected Lab Outcomes

~~~text
[PASS] Route predicates match accurately and unmatched requests never reach upstream
[PASS] Path/query after StripPrefix/RewritePath match contract
[PASS] Request headers added, set, and removed per policy
[PASS] Client-spoofed forwarded/identity headers are never trusted
[PASS] Upstream receives accurate JSON/body and Content-Type
[PASS] Final response headers/status/body match policy
[PASS] Backend 404 cleanly distinguished from Gateway no-route 404
[PASS] Retry/fallback/rate-limit/auth verified via upstream attempt counts
[PASS] Tests use deterministic mock upstreams and dynamic ports
[PASS] No credentials/PII leaked; event loop never blocked
~~~

These are **completion criteria**, not an execution log from the assigned workspace.

## 24. Pre-CI/CD Checklist

- [ ] **Full HTTP chain** tested from Gateway → mock upstream, not isolated predicates alone.
- [ ] Assertions inspect **both sides**: upstream recorded requests and client responses.
- [ ] Test configuration uses the exact starter and route namespace for your Server WebFlux version.
- [ ] Gateway uses `RANDOM_PORT` and mocks use dynamic ports, never calling the Internet or production.
- [ ] No duplicate route IDs or unintended overlapping predicates in YAML/Java DSL.
- [ ] Tested `StripPrefix`/`RewritePath`, query params, encoded slashes, and boundary paths.
- [ ] Verified HTTP methods alongside paths, not just default GETs.
- [ ] Tested `Add` vs. `Set` vs. `Remove` request headers; client-spoofed headers ignored.
- [ ] Tested response headers including add/remove/dedupe/CORS where used.
- [ ] Never assert `Connection`, `Transfer-Encoding`, or `Content-Length` against HTTP semantics.
- [ ] Tested JSON semantic equality, binary checksums, missing bodies, and `Content-Type`.
- [ ] Where body rewrites apply, verified schema, length, and `Content-Encoding` consistency.
- [ ] Tested 201/204/4xx/5xx/no-route/timeouts per status-mapping policy.
- [ ] Used upstream request counters to separate Gateway-generated from backend-generated statuses.
- [ ] Every `Retry` test defines an explicit response queue and asserts exact attempt counts.
- [ ] Never auto-retry critical POSTs without backend idempotency guarantees.
- [ ] Security 401/403, rate-limit 429, and circuit breaker fallbacks assert request counters.
- [ ] Outbound TLS and service discovery tested separately rather than assuming HTTP-only labs cover them.
- [ ] Never use `Thread.sleep` instead of bounded event waits.
- [ ] Never use custom `subscribe()`/`block()` inside Gateway filters to inspect bodies.
- [ ] Mock server response queues are isolated with no parallel execution contention.
- [ ] All tests enforce timeouts, clean up resources, and avoid external Redis/service state coupling.
- [ ] Logs and CI artifacts redact tokens, cookies, sensitive payloads, and PII-bearing URIs.
- [ ] Re-run route/filter/status-mapping contract tests whenever upgrading Gateway versions.
- [ ] Test **every replica** in staging when using dynamic routes or multi-node routing.
- [ ] Documentation clearly separates **expected** from **observed** and never marks PASS prematurely.

## 25. Summary and References

**Verifying forwarding in Spring Cloud Gateway** means checking the HTTP contract at **two distinct boundaries**:

1. **Client → Gateway → upstream:** Are method, path, query, request headers, and request body accurate after route predicates and the filter chain?
2. **Upstream → Gateway → client:** Are HTTP status, response headers, and response body accurate after response filters, retries, circuit breaking, and error handling?

Combine **`@SpringBootTest(RANDOM_PORT)` + `WebTestClient.bindToServer()` + a mock HTTP upstream** to traverse the live routing stack. The mock upstream reveals the final downstream request while `WebTestClient` inspects the final client response; asserting both catches misrouted paths, leaked headers, dropped bodies, unexpected status overrides, and extra retry attempts.

Deep suites must also test **unmatched routes**, **backend 404s**, **204/422/503 responses**, **pre-routing auth/rate limits**, **retries/fallbacks**, **TLS/service discovery**, and **streaming**, aligned with your deployment and release contracts. Never compromise security or observability: never trust client-spoofed headers, never log secrets, and never break reactive flow just to inspect bodies.

### References

- [Spring Framework — WebTestClient, bindToServer, and Request/Response Assertions](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html).
- [Spring Boot 3.5 — Testing with a Running Server, RANDOM_PORT](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html).
- [Spring Cloud Gateway Server WebFlux — GatewayFilter Factories](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/gatewayfilter-factories.html).
- [Spring Cloud Gateway Server WebFlux — AddRequestHeader](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/gatewayfilter-factories/addrequestheader-factory.html).
- [Spring Cloud Gateway Server WebFlux — RewritePath](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/gatewayfilter-factories/rewritepath-factory.html).
- [Spring Cloud Gateway Server WebFlux — ModifyRequestBody](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/gatewayfilter-factories/modifyrequestbody-factory.html).
- [Spring Cloud Gateway Server WebFlux — ModifyResponseBody](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/gatewayfilter-factories/modifyresponsebody-factory.html).
- [Spring Cloud Gateway Server WebFlux — SetStatus](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/gatewayfilter-factories/setstatus-factory.html).
- [Spring Cloud Gateway Server WebFlux — Retry](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/gatewayfilter-factories/retry-factory.html).
- [Spring Cloud Gateway Server WebFlux — HttpHeadersFilters](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/httpheadersfilters.html).
- [Spring Cloud Gateway — Version-Specific Configuration Properties](https://docs.spring.io/spring-cloud-gateway/reference/configprops.html).
