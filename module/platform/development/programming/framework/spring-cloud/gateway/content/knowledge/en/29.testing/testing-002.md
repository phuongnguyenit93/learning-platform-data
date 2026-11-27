# Testing Predicates with Matching and Non-Matching Requests

## 1. Why Can a "Working" Route Still Route Incorrectly?

In **Spring Cloud Gateway**, clients reach microservices through an API Gateway. The Gateway uses **route predicates** to decide which route owns a request before executing the **filter chain** for path/header transformation, authentication, rate limiting, retries, circuit breaking, service instance selection, and observability.

Suppose a system defines a partner-only route:

~~~yaml
predicates:
  - Path=/api/catalog/**
  - Method=GET
  - Host=catalog.test
  - Header=X-Channel,^partner$
  - Query=mode,^full$
~~~

Sending one "valid" request and seeing HTTP 200 **is not enough**. We must also prove:

- A request missing `X-Channel` does not enter the route.
- A `POST` cannot use a route restricted to `GET`.
- A different Host does not accidentally pick the partner backend.
- Missing or invalid query parameters are not accepted by mistake.
- When no route matches, the backend **receives no request**.
- If other routes can also match, the Gateway selects the **right route by precedence**, not merely returning 200 by coincidence.

This lesson, **"Testing Predicates with Matching and Non-Matching Requests"**, belongs to the **Testing** chapter of the **SPRING_CLOUD_GATEWAY** module. We will combine an **input matrix**, `curl` commands, an echo backend, and automated tests using **JUnit 5 + WebTestClient + MockWebServer**. This lays the foundation for later testing authentication, rate limiting, circuit breakers, retries, TLS, service discovery, and observability on the right route.

> **Primary scope:** Spring Cloud Gateway **Server WebFlux**. This covers the `RoutePredicateHandlerMapping`/`RouteLocator` pipeline. Server Web MVC uses WebMvc.fn with its own predicate/filter library; do not copy reactive imports or tests verbatim to Server MVC.

After this lesson, you will be able to:

1. Explain the **AND rule across predicates** and the **OR rule across values within a single predicate**.
2. Build a matching/non-matching matrix for path, method, host, header, and query.
3. Choose measurements that identify **which route was selected** instead of looking only at status codes.
4. Run an independent stub backend and verify **zero downstream calls** when a route does not match.
5. Write integration tests running the Gateway on a random port with `WebTestClient`.
6. Handle edge cases: slashes, regex, casing, route ordering, fallbacks, CORS preflight, proxy trust, and time.

## 2. At Which Phase Are Predicates Evaluated?

In Server WebFlux, the Gateway receives a `ServerWebExchange`. The route-matching component scans the runtime `Route` list, evaluates each route's predicates, and picks a matching route. Only after that do the associated `GlobalFilter` and `GatewayFilter` instances enter the request-processing pipeline.

~~~mermaid
flowchart TD
    C["Client HTTP request"] --> E["ServerWebExchange"]
    E --> R["RoutePredicateHandlerMapping"]
    R --> P{"Any Route with<br/>matching predicates?"}
    P -->|"No"| N["No Gateway route<br/>usually 404 if no other handler"]
    P -->|"Yes"| A["Runtime Route selected"]
    A --> F["Combined GlobalFilter + GatewayFilter"]
    F --> U["HTTP routing / LB → backend"]
    U --> O["Response returned to client"]
~~~

**Two questions must be kept separate:**

1. **Route selection:** Did the request match the predicates and pick the intended route?
2. **Request handling:** Once the route was selected, did the filters and backend succeed?

A request can **match the right route** yet return 401 from Spring Security, 429 from a rate limiter, 503 due to no backend instance, or 502 from a TLS/connection failure. Conversely, a request that fails the intended route can still return 200 because of a **fallback route**, a local controller, or a route with broader predicates.

### 2.1. Logical AND Across Predicates on a Route

For a route declaring:

~~~yaml
predicates:
  - Path=/api/catalog/**
  - Method=GET
  - Host=catalog.test
  - Header=X-Channel,^partner$
  - Query=mode,^full$
~~~

The combined logical condition is:

\[
\operatorname{match}(r,q)
=P_{\mathrm{path}}(q)
\land P_{\mathrm{method}}(q)
\land P_{\mathrm{host}}(q)
\land P_{\mathrm{header}}(q)
\land P_{\mathrm{query}}(q)
\]

If **even one condition evaluates to false**, the route is not selected. This is the general rule for predicate factories combined inside a `RouteDefinition`.

### 2.2. Logical OR Inside a Predicate Listing Multiple Values

For example:

~~~yaml
predicates:
  - Method=GET,HEAD
~~~

means the method belongs to the set GET **or** HEAD. Similarly:

~~~yaml
predicates:
  - Path=/api/catalog/**,/v2/catalog/**
~~~

accepts either path pattern. If a route has **two separate predicate lines**, both must hold simultaneously unless you use a custom predicate with different logic or write your own DSL composition.

### 2.3. An Example Where AND/OR Are Commonly Confused

~~~yaml
predicates:
  - Path=/api/orders/**
  - Path=/api/catalog/**
~~~

This does **not** mean "orders or catalog": both predicates apply to the same request, so a single path normally cannot match two distinct prefixes at once. Declare **one `Path` line with multiple patterns**, or define two separate route definitions as appropriate.

### 2.4. Route Order Differs from Filter Order

When **multiple routes** have true predicates, the Gateway checks runtime route ordering. A route with a **smaller** `order` takes higher priority (e.g., `-10` before `10`). Do not confuse this with `GatewayFilter` pre/post execution ordering; that is a separate mechanism.

In tests, **which route was selected** must be proven via a route ID, response marker, or backend target. Asserting HTTP 200 alone fails to catch a fallback route receiving traffic by mistake.

## 3. Three-Tier Testing Strategy

| Testing tier | Tools | What it proves | What it does not prove |
| --- | --- | --- | --- |
| **Predicate unit test** | `MockServerWebExchange` + factory or custom predicate | Logic of **one** predicate | Correct YAML route binding, Gateway routing, backend forwarding |
| **Route integration test** | `@SpringBootTest(RANDOM_PORT)`, `WebTestClient`, stub backend | Config binding, AND composition, route selection, filter markers, presence/absence of downstream call | Full production networking/TLS/proxies |
| **End-to-end/staging** | cURL/Postman, ingress, DNS, mTLS, real registry | Host/Forwarded/headers/CORS and realistic infrastructure | Every input combination or race condition |

A reliable design includes both **positive** and **negative tests**:

- **Positive:** keep all conditions true; verify the route marker and that the backend receives the exact request.
- **Negative:** flip **exactly one** condition to false while keeping all others valid, and verify the **backend is not called**.
- **Boundary:** test regex edges, slashes, casing, encoded paths, duplicate query params, and time windows.
- **Overlap:** add competing routes that could also match to prove precedence.

### 3.1. Why Negative Tests Must Change One Factor at a Time

If a "negative" test simultaneously uses POST, changes Host, omits Header, and changes Path, you do not know which predicate blocked it. If one predicate is accidentally deleted, the test may still pass due to the remaining false conditions.

A **decision table** isolates each rule:

| Case | Path | Method | Host | X-Channel | Query mode | Route expectation |
| --- | --- | --- | --- | --- | --- | --- |
| T0 | `/api/catalog/items/42` | GET | catalog.test | partner | full | **Match** |
| T1 | `/api/orders/items/42` | GET | catalog.test | partner | full | No match — Path |
| T2 | `/api/catalog/items/42` | POST | catalog.test | partner | full | No match — Method |
| T3 | `/api/catalog/items/42` | GET | wrong.test | partner | full | No match — Host |
| T4 | `/api/catalog/items/42` | GET | catalog.test | *missing* | full | No match — Header |
| T5 | `/api/catalog/items/42` | GET | catalog.test | Partner | full | No match — Header value |
| T6 | `/api/catalog/items/42` | GET | catalog.test | partner | *missing* | No match — Query |
| T7 | `/api/catalog/items/42` | GET | catalog.test | partner | short | No match — Query regex |
| T8 | `/api/catalog/items/42` | GET | catalog.test | partner | full | Match again to detect test pollution |

Notice T5: with regex `^partner$`, the **value** `Partner` differs from `partner` because Java regexes are case-sensitive by default. HTTP header names such as `X-Channel`, however, are **case-insensitive** per HTTP semantics—two distinct rules.

## 4. Creating a Test Route with Observable Markers

To keep the focus on predicates, the lab backend receives the **original path** from the client without `StripPrefix`. We add an explicit response marker via a Gateway filter:

~~~text
X-Matched-Route: catalog-partner
~~~

This marker is strictly for testing and diagnostics. Do not treat it as backend authentication/authorization proof; a client or proxy could send a header with the same name if no trust boundary exists.

### 4.1. Spring Cloud Gateway Server WebFlux 5.x

`src/main/resources/application.yml`:

~~~yaml
server:
  port: 8080

spring:
  application:
    name: predicate-gateway-lab
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: catalog-partner
              order: -10
              uri: http://127.0.0.1:9091
              predicates:
                - Path=/api/catalog/**
                - Method=GET
                - Host=catalog.test
                - Header=X-Channel,^partner$
                - Query=mode,^full$
              filters:
                - AddRequestHeader=X-Downstream-Probe,catalog-partner
                - AddResponseHeader=X-Matched-Route,catalog-partner
~~~

### 4.2. WebFlux 4.2.x / 4.3.x

In WebFlux 4.x releases, the corresponding route namespace is `spring.cloud.gateway.routes`:

~~~yaml
server:
  port: 8080

spring:
  cloud:
    gateway:
      routes:
        - id: catalog-partner
          order: -10
          uri: http://127.0.0.1:9091
          predicates:
            - Path=/api/catalog/**
            - Method=GET
            - Host=catalog.test
            - Header=X-Channel,^partner$
            - Query=mode,^full$
          filters:
            - AddRequestHeader=X-Downstream-Probe,catalog-partner
            - AddResponseHeader=X-Matched-Route,catalog-partner
~~~

Choose **one** namespace matching your actual version: Gateway WebFlux 5.x uses `spring.cloud.gateway.server.webflux.routes`, whereas WebFlux 4.2/4.3 uses `spring.cloud.gateway.routes`. The newer starter name `spring-cloud-starter-gateway-server-webflux` is documented in 4.3/5.x; older 4.x releases use `spring-cloud-starter-gateway`. Let the Spring Cloud BOM select versions compatible with Spring Boot and verify the application type is **reactive**.

### 4.3. Meaning of Each Route Property

| Property | Why included in the lab? |
| --- | --- |
| `id: catalog-partner` | Identifies the route in logs and Actuator |
| `order: -10` | Enables testing route priority later |
| `uri: http://127.0.0.1:9091` | Controlled backend target without Internet dependency |
| `Path=/api/catalog/**` | Tests prefix and segment boundaries |
| `Method=GET` | Separates GET from POST/OPTIONS |
| `Host=catalog.test` | Tests Host header/virtual host |
| `Header=X-Channel,^partner$` | Tests header name, value regex, and missing header |
| `Query=mode,^full$` | Tests query parameter name/value |
| `AddRequestHeader` | Backend receives marker proving filter ran |
| `AddResponseHeader` | Client receives marker proving which route's filter ran |

**Do not insert a `Path=/**` fallback route into the baseline.** With a fallback present, negative cases can return 200 from the other route and "404 on no-match" tests will fail even when the main predicate is right. We will test fallbacks separately later.

### 4.4. Full Args vs. Shortcut Notation

Predicates can use shortcut syntax such as `Header=X-Channel,^partner$`, or expanded field notation:

~~~yaml
- name: Header
  args:
    header: X-Channel
    regexp: "^partner$"

- name: Query
  args:
    param: mode
    regexp: "^full$"
~~~

For `Path` with multiple patterns in Gateway WebFlux 5.x, the docs also mention indexed `args` keys like `patterns.0`, `patterns.1` instead of a direct JSON array when posting routes through Actuator. Testing **real configuration binding** is just as important as unit testing individual predicates.

## 5. Echo Backend to Measure Actual Forwarding

In the manual lab, create **two independent Spring Boot applications**:

| Component | Port | Responsibility |
| --- | ---: | --- |
| Gateway Server WebFlux | `8080` | Selects route and attaches markers |
| Catalog backend | `9091` | Returns HTTP 200 and counts incoming backend requests |

The backend is a minimal Spring Boot WebFlux project with `spring-boot-starter-webflux`. Configuration:

~~~yaml
# Backend application.yml
server:
  port: 9091
~~~

Bootstrap class `src/main/java/demo/catalog/CatalogBackendApplication.java`:

~~~java
package demo.catalog;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CatalogBackendApplication {
    public static void main(String[] args) {
        SpringApplication.run(CatalogBackendApplication.class, args);
    }
}
~~~

Controller `src/main/java/demo/catalog/CatalogBackendController.java`:

~~~java
package demo.catalog;

import java.util.LinkedHashMap;
import java.util.Map;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.http.server.reactive.ServerHttpRequest;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class CatalogBackendController {

    private final AtomicInteger calls = new AtomicInteger();

    @GetMapping("/api/catalog/items/{id}")
    public Map<String, Object> item(
            @PathVariable String id,
            ServerHttpRequest request) {

        int count = calls.incrementAndGet();
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("backend", "catalog-9091");
        result.put("id", id);
        result.put("path", request.getPath().value());
        result.put("method", request.getMethod().name());
        result.put("channel", request.getHeaders()
                .getFirst("X-Channel"));
        result.put("probe", request.getHeaders()
                .getFirst("X-Downstream-Probe"));
        result.put("backendCalls", count);
        return result;
    }

    @GetMapping("/__test/calls")
    public Map<String, Integer> calls() {
        return Map.of("calls", calls.get());
    }
}
~~~

The `/__test/calls` endpoint is strictly for **lab use** and **must not be exposed in production**; exposing it allows traffic inference. In real systems, use metrics protected by authentication/RBAC rather than an unauthenticated test HTTP endpoint.

### 5.1. Why Does the Counter Matter More Than Status 404?

Suppose a request to the Gateway with the wrong Host returns 404. A 404 alone does not prove the Host predicate blocked it; the Gateway could still have forwarded to the backend and the backend returned 404.

If the backend counter stays unchanged **and** the route marker is absent, the evidence is far stronger:

~~~text
Before request: backendCalls = 8
Send wrong-Host request: Gateway returns 404
After request:  backendCalls = 8
=> test backend endpoint was not called
~~~

The counter above counts **only the `/api/catalog/items/{id}` handler**. To prove **zero** downstream requests of any kind, use a mock HTTP server/dispatcher counting every request (section 8) or backend access logs with correlation IDs.

### 5.2. Starting Up

In two terminals for the two projects:

~~~bash
# Terminal 1, backend
./mvnw spring-boot:run

# Terminal 2, Gateway
./mvnw spring-boot:run
~~~

On Windows, use `mvnw.cmd spring-boot:run`. The snippets in this lesson are **guided examples to practice**, not code already built or executed in this repository.

Check the backend first:

~~~bash
curl -i "http://127.0.0.1:9091/api/catalog/items/42"
curl -sS "http://127.0.0.1:9091/__test/calls"
~~~

The backend should return HTTP 200 and count one more request. When testing through the Gateway, do not change backend configuration between cases so routing bugs are not confused with backend outages.

## 6. Manual Testing with cURL: All Conditions Met vs. One Missing

### 6.1. Positive Case: All Predicates Match

~~~bash
curl -i \
  "http://127.0.0.1:8080/api/catalog/items/42?mode=full" \
  -H "Host: catalog.test" \
  -H "X-Channel: partner"
~~~

Expected:

~~~http
HTTP/1.1 200 OK
X-Matched-Route: catalog-partner
Content-Type: application/json

{
  "backend": "catalog-9091",
  "id": "42",
  "path": "/api/catalog/items/42",
  "method": "GET",
  "channel": "partner",
  "probe": "catalog-partner",
  "backendCalls": 2
}
~~~

`backendCalls` depends on prior requests; do not assert it equals 2 across every run. Check:

1. HTTP status **200** from the backend.
2. Response header `X-Matched-Route: catalog-partner` from the selected route.
3. Body fields `backend=catalog-9091` and `probe=catalog-partner` from the receiving backend.
4. Backend counter increments by **exactly one** for a single GET when no retry/extra filter applies.

An HTTP 200 from some other controller fails these four checks.

### 6.2. Negative: Different Path

~~~bash
curl -i \
  "http://127.0.0.1:8080/api/orders/items/42?mode=full" \
  -H "Host: catalog.test" \
  -H "X-Channel: partner"
~~~

If the lab **only has the `catalog-partner` route and no other handler**, the Gateway typically returns 404 with no `X-Matched-Route`. The backend counter must remain unchanged.

### 6.3. Negative: Different Method

~~~bash
curl -i -X POST \
  "http://127.0.0.1:8080/api/catalog/items/42?mode=full" \
  -H "Host: catalog.test" \
  -H "X-Channel: partner"
~~~

Even though `Path/Host/Header/Query` all match, `Method=GET` is false. In a lab with only this Gateway route, the result is normally 404. An application with other handlers might return 405 or another response; **do not treat a specific status code as a universal contract for predicate misses**.

### 6.4. Negative: Different Host

~~~bash
curl -i \
  "http://127.0.0.1:8080/api/catalog/items/42?mode=full" \
  -H "Host: wrong.test" \
  -H "X-Channel: partner"
~~~

In production HTTPS environments, Host also ties into TLS SNI and reverse proxy routing. A localhost HTTP lab intentionally uses the `Host` header to test the predicate and **does not fully simulate TLS hostname verification**.

### 6.5. Negative: Missing or Wrong Header

~~~bash
# Missing X-Channel
curl -i \
  "http://127.0.0.1:8080/api/catalog/items/42?mode=full" \
  -H "Host: catalog.test"

# X-Channel present, but regex rejects "Partner"
curl -i \
  "http://127.0.0.1:8080/api/catalog/items/42?mode=full" \
  -H "Host: catalog.test" \
  -H "X-Channel: Partner"
~~~

Also test a lowercase header name:

~~~bash
curl -i \
  "http://127.0.0.1:8080/api/catalog/items/42?mode=full" \
  -H "Host: catalog.test" \
  -H "x-channel: partner"
~~~

HTTP header names are case-insensitive, so the last case **must match**; its value is still `partner`, matching the regex. If the last case fails, inspect the HTTP client/proxy or custom predicates rather than blaming Spring regex matching.

### 6.6. Negative: Missing or Wrong Query

~~~bash
# Missing "mode"
curl -i \
  "http://127.0.0.1:8080/api/catalog/items/42" \
  -H "Host: catalog.test" \
  -H "X-Channel: partner"

# mode=short does not match ^full$
curl -i \
  "http://127.0.0.1:8080/api/catalog/items/42?mode=short" \
  -H "Host: catalog.test" \
  -H "X-Channel: partner"
~~~

Query keys and values are subject to URL encoding and parsing; when testing duplicate keys/values or different casing, verify **what the WebFlux request actually decodes**. Avoid building authorization solely on a query predicate that can be duplicated or misparsed.

### 6.7. Positive Again After Negative Cases

~~~bash
curl -i \
  "http://127.0.0.1:8080/api/catalog/items/42?mode=full" \
  -H "Host: catalog.test" \
  -H "X-Channel: partner"
~~~

Repeating the positive test catches test state pollution, accidental route/runtime changes, or an unresponsive backend after a negative case.

## 7. Writing Proper Assertions: Beyond `expectStatus().isOk()`

Include three layers of assertions when testing routes:

| Observation point | Positive case | Negative case |
| --- | --- | --- |
| **HTTP from Gateway** | Expected status and `X-Matched-Route` marker | No marker for that route; status matching isolated setup |
| **Backend HTTP stub** | Receives expected method/path/headers; call count increments properly | Receives zero calls for the probe request |
| **Route inventory / logs** | Expected route ID and configuration | Intended route not selected; if fallback exists, identify the other route |

**A marker header is not infallible proof.** A proxy might duplicate or strip headers; an error handler might respond before filters run; or the backend might emit the same header. Combining **Gateway marker + backend request count/recording + observed route ID** makes false positives much harder.

In a test-only stub backend, you can attach `X-Backend-Id: catalog-stub` to every response. Then:

~~~text
X-Matched-Route: catalog-partner  (Gateway route filter)
X-Backend-Id: catalog-stub       (Backend stub)
~~~

Two independent headers separate **route matched** from **backend called**. For a non-matching route in a baseline without fallbacks or other controllers, both must be absent.

## 8. Automated Integration Tests with WebTestClient and MockWebServer

This is the most valuable part of testing: **the Gateway runs live on a random port**, while the backend uses an HTTP stub started on a dynamic port. Tests need no hardcoded `8080`/`9091` ports and depend on no external server.

~~~mermaid
flowchart LR
    T["JUnit WebTestClient"] --> G["Gateway WebFlux<br/>RANDOM_PORT"]
    G -->|"only if predicates match"| M["MockWebServer<br/>random port"]
    M --> R["RecordedRequest + call counter"]
    G --> H["HTTP response + route marker"]
    H --> T
    R --> T
~~~

### 8.1. Test Dependencies

Maven example for a **Gateway Server WebFlux 4.3.x + Spring Boot 3.5.x** project using a compatible Spring Cloud BOM:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-gateway-server-webflux</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>

    <!-- MockWebServer 4.x API used in sample code -->
    <dependency>
        <groupId>com.squareup.okhttp3</groupId>
        <artifactId>mockwebserver</artifactId>
        <version>4.12.0</version>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Spring Cloud dependencies should be managed by the **Spring Cloud BOM**. MockWebServer 4.12.0 is pinned explicitly to align with the sample Java API; it is a **test-only dependency** and must not ship in production Gateway artifacts. If your organization uses MockWebServer 5.x or Spring Boot 4.x, check the API/packages and test starters for that version before applying the sample.

`spring-boot-starter-test` provides JUnit Jupiter, AssertJ, and Spring Test. `WebTestClient` comes from Spring Test/WebFlux on the classpath. When tests must verify real Netty HTTP handling, **RANDOM_PORT** is more trustworthy than unit tests calling a predicate factory directly.

### 8.2. Gateway Bootstrap Class

`src/main/java/demo/gateway/GatewayApplication.java`:

~~~java
package demo.gateway;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class GatewayApplication {

    public static void main(String[] args) {
        SpringApplication.run(GatewayApplication.class, args);
    }
}
~~~

Place the test class under package `demo.gateway` so it shares the component-scan root. Do not add a `@Controller` handling `/api/catalog/**` in this project, as it could answer negative tests from a non-Gateway handler.

### 8.3. application-predicate-test.yml

Place at `src/test/resources/application-predicate-test.yml` for **Gateway 4.3.x/Boot 3.5.x**, matching the Java test in section 8.4:

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: catalog-partner
          order: -10
          uri: http://127.0.0.1:${test.stub.port}
          predicates:
            - Path=/api/catalog/**
            - Method=GET
            - Host=catalog.test
            - Header=X-Channel,^partner$
            - Query=mode,^full$
          filters:
            - AddRequestHeader=X-Downstream-Probe,catalog-partner
            - AddResponseHeader=X-Matched-Route,catalog-partner
~~~

With `@ActiveProfiles("predicate-test")`, this profile supplies the test route list. The `${test.stub.port}` placeholder is registered via `@DynamicPropertySource` once MockWebServer binds its port.

**Important:** If main resources define routes in `application.yml`, ensure the test profile **replaces the route list properly**; do not let extra routes load from discovery or Java beans and accidentally handle negative cases. In this example, the profile-specific routes are the Gateway's only routes.

For **Gateway WebFlux 5.x/Spring Boot 4.x**, keep the route definition identical but switch the prefix:

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: catalog-partner
              order: -10
              uri: http://127.0.0.1:${test.stub.port}
              predicates:
                - Path=/api/catalog/**
                - Method=GET
                - Host=catalog.test
                - Header=X-Channel,^partner$
                - Query=mode,^full$
              filters:
                - AddRequestHeader=X-Downstream-Probe,catalog-partner
                - AddResponseHeader=X-Matched-Route,catalog-partner
~~~

These two snippets **must not coexist in the same test file**. The Java test in section 8.4 uses the `@AutoConfigureWebTestClient` import from **Spring Boot 3.5.x**; if migrating to Gateway 5.x/Boot 4.x, update test auto-configuration imports to match Boot 4.x as well. During upgrades, cover prefix migration with tests, because an outdated YAML namespace lets the app start up without the expected routes.

### 8.4. JUnit 5 Test: All Conditions Match

`src/test/java/demo/gateway/CatalogPredicateIT.java`:

~~~java
package demo.gateway;

import java.io.IOException;
import java.util.concurrent.TimeUnit;
import java.util.stream.Stream;

import okhttp3.mockwebserver.Dispatcher;
import okhttp3.mockwebserver.MockResponse;
import okhttp3.mockwebserver.MockWebServer;
import okhttp3.mockwebserver.RecordedRequest;

import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.parallel.Execution;
import org.junit.jupiter.api.parallel.ExecutionMode;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.Arguments;
import org.junit.jupiter.params.provider.MethodSource;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
        classes = GatewayApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
@ActiveProfiles("predicate-test")
@Execution(ExecutionMode.SAME_THREAD)
class CatalogPredicateIT {

    private static final MockWebServer BACKEND = startBackend();

    @Autowired
    private WebTestClient client;

    @DynamicPropertySource
    static void registerBackendPort(DynamicPropertyRegistry registry) {
        registry.add("test.stub.port", BACKEND::getPort);
    }

    private static MockWebServer startBackend() {
        MockWebServer server = new MockWebServer();
        server.setDispatcher(new Dispatcher() {
            @Override
            public MockResponse dispatch(RecordedRequest request) {
                return new MockResponse()
                        .setResponseCode(200)
                        .addHeader("Content-Type", "application/json")
                        .addHeader("X-Backend-Id", "catalog-stub")
                        .setBody("{\"backend\":\"catalog-stub\"}");
            }
        });

        try {
            server.start(); // Random port on localhost
        } catch (IOException e) {
            throw new ExceptionInInitializerError(e);
        }
        return server;
    }

    @AfterAll
    static void stopBackend() throws IOException {
        BACKEND.shutdown();
    }

    @Test
    void allPredicatesMatchAndForwardToBackend()
            throws InterruptedException {

        int before = BACKEND.getRequestCount();

        client.get()
                .uri("/api/catalog/items/42?mode=full")
                .header(HttpHeaders.HOST, "catalog.test")
                .header("X-Channel", "partner")
                .exchange()
                .expectStatus().isOk()
                .expectHeader().valueEquals(
                        "X-Matched-Route", "catalog-partner")
                .expectHeader().valueEquals(
                        "X-Backend-Id", "catalog-stub")
                .expectBody()
                .jsonPath("$.backend").isEqualTo("catalog-stub");

        assertThat(BACKEND.getRequestCount())
                .isEqualTo(before + 1);

        RecordedRequest request =
                BACKEND.takeRequest(1, TimeUnit.SECONDS);

        assertThat(request).isNotNull();
        assertThat(request.getMethod()).isEqualTo("GET");
        assertThat(request.getPath())
                .isEqualTo("/api/catalog/items/42?mode=full");
        assertThat(request.getHeader("X-Downstream-Probe"))
                .isEqualTo("catalog-partner");
    }

    @ParameterizedTest(name = "{0}")
    @MethodSource("negativeCases")
    void onePredicateFailsSoBackendIsNotCalled(
            String caseName,
            HttpMethod method,
            String pathAndQuery,
            String host,
            String channel) {

        int before = BACKEND.getRequestCount();

        WebTestClient.RequestHeadersSpec<?> request =
                client.method(method)
                        .uri(pathAndQuery)
                        .header(HttpHeaders.HOST, host);

        if (channel != null) {
            request.header("X-Channel", channel);
        }

        request.exchange()
                .expectStatus().isNotFound()
                .expectHeader().doesNotExist("X-Matched-Route")
                .expectHeader().doesNotExist("X-Backend-Id");

        assertThat(BACKEND.getRequestCount())
                .as(caseName + " must not hit the backend")
                .isEqualTo(before);
    }

    static Stream<Arguments> negativeCases() {
        return Stream.of(
                Arguments.of("wrong path", HttpMethod.GET,
                        "/api/orders/items/42?mode=full",
                        "catalog.test", "partner"),
                Arguments.of("wrong method", HttpMethod.POST,
                        "/api/catalog/items/42?mode=full",
                        "catalog.test", "partner"),
                Arguments.of("wrong host", HttpMethod.GET,
                        "/api/catalog/items/42?mode=full",
                        "wrong.test", "partner"),
                Arguments.of("missing header", HttpMethod.GET,
                        "/api/catalog/items/42?mode=full",
                        "catalog.test", null),
                Arguments.of("wrong header value", HttpMethod.GET,
                        "/api/catalog/items/42?mode=full",
                        "catalog.test", "Partner"),
                Arguments.of("missing query", HttpMethod.GET,
                        "/api/catalog/items/42",
                        "catalog.test", "partner"),
                Arguments.of("wrong query value", HttpMethod.GET,
                        "/api/catalog/items/42?mode=short",
                        "catalog.test", "partner")
        );
    }
}
~~~

### 8.5. Read the Test Carefully to Avoid False Positives

- `@SpringBootTest(RANDOM_PORT)` runs the Gateway on a **real HTTP server**, not just a mocked factory. In Spring Boot 3.x, `@AutoConfigureWebTestClient` resides in `org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient`; Boot 4.x reorganized several test auto-configuration packages.
- `@DynamicPropertySource` injects MockWebServer's port into the route URI **before the application context binds config**. Never hardcode port 9091 and cause CI port collisions.
- The stub uses a `Dispatcher` returning a consistent response for every downstream request and counts via `getRequestCount()`, so **negative tests need not enqueue responses**.
- The positive test checks the **route marker**, **backend marker**, **exact downstream path/method/header**, and that backend call count increments by one.
- Negative cases change one variable at a time, assert **markers are absent**, and assert **backend call count does not increment**.
- `@Execution(SAME_THREAD)` prevents methods in the class from running concurrently against the same counter. Other test classes must not share this static stub.
- `BACKEND.takeRequest(...)` is called only in the positive test, dequeuing one recorded request with a 1-second timeout so tests never hang indefinitely.
- HTTP 404 on negative cases is the expectation **for an isolated fixture with no fallback route or local handler**. If the environment has a fallback, update the assertion to verify the **selected route ID/target** instead of assuming 404 is a universal predicate rule.

### 8.6. Run Command and Reporting Scope

Maven example:

~~~bash
./mvnw -Dtest=CatalogPredicateIT test
~~~

Test classes ending in `IT` may be routed by plugin config to **Failsafe integration-test** rather than Surefire. If Maven Surefire in your project skips `*IT` by default, configure test includes or rename the class to `CatalogPredicateTest` and pass the updated name to the command. In CI, invoke the goal matching your configured plugin so a build never reports "green" while executing **0 tests**.

This example is **sample code for study and hands-on practice**; it has not been built or run in the current repository. When writing real tests, align exact versions of Spring Boot, Spring Cloud Gateway, Java/JUnit, and MockWebServer.

## 9. Unit Testing a Predicate Factory: Fast, Not a Replacement for Integration Tests

When developing a **custom `RoutePredicateFactory`** or checking regex behavior on a built-in one, you can construct a `MockServerWebExchange` without starting an HTTP server.

The following example tests `HeaderRoutePredicateFactory` on Gateway Server WebFlux:

~~~java
package demo.gateway;

import org.junit.jupiter.api.Test;
import org.springframework.cloud.gateway.handler.predicate
        .HeaderRoutePredicateFactory;
import org.springframework.mock.http.server.reactive
        .MockServerHttpRequest;
import org.springframework.mock.web.server.MockServerWebExchange;

import static org.assertj.core.api.Assertions.assertThat;

class HeaderPredicateUnitTest {

    @Test
    void matchesOnlyExpectedHeaderValue() {
        var config = new HeaderRoutePredicateFactory.Config();
        config.setHeader("X-Channel");
        config.setRegexp("^partner$");

        var predicate = new HeaderRoutePredicateFactory()
                .apply(config);

        var matching = MockServerWebExchange.from(
                MockServerHttpRequest
                        .get("/api/catalog/items/42")
                        .header("X-Channel", "partner"));

        var wrongValue = MockServerWebExchange.from(
                MockServerHttpRequest
                        .get("/api/catalog/items/42")
                        .header("X-Channel", "Partner"));

        var missingHeader = MockServerWebExchange.from(
                MockServerHttpRequest
                        .get("/api/catalog/items/42"));

        assertThat(predicate.test(matching)).isTrue();
        assertThat(predicate.test(wrongValue)).isFalse();
        assertThat(predicate.test(missingHeader)).isFalse();
    }
}
~~~

If constructor/setter signatures change across Gateway patches, consult the Javadoc for your exact artifact. **This factory test does not prove:**

- `Header=X-Channel,^partner$` binds properly from YAML.
- The route includes all four other predicates.
- The `catalog-partner` route has the intended priority.
- Requests traverse filters and reach the right backend.

That is why **fast unit tests + HTTP integration tests** complement rather than replace each other.

### 9.1. Testing Custom Predicates Follows Different Rules from Built-Ins

If a project writes a custom `TenantPlanRoutePredicateFactory`, you must test:

1. `Config` binding: field names, types, null/defaults, regex/ranges.
2. Positive/negative behavior with a mocked `ServerWebExchange`.
3. Behavior when a field or header is absent.
4. Exception/error behavior if config is invalid or a lookup dependency is unavailable.
5. Performance, thread safety, and side effects of reading the body or remote address.

**Do not equate predicates with authorization.** Predicates only pick a route; tenant/resource access control must rely on verified identity and security policies.

## 10. Edge Cases Your Test Suite Must Cover

### 10.1. Path: Prefixes, Slashes, and URL Encoding

Distinguish these path patterns:

~~~yaml
- Path=/api/catalog/**
- Path=/api/catalog/{id}
- Path=/api/catalog/items/{id}
~~~

They are **not equivalent**. Wildcard `**` allows a broad range of paths; `{id}` binds a URI template variable at that single segment. Cases to check:

| Request path | Question to answer |
| --- | --- |
| `/api/catalog/items/42` | Does the main case match? |
| `/api/catalog/items/42/` | Is a trailing slash accepted? |
| `/api/catalog` | Does the wildcard match the root segment? |
| `/api/catalog/` | How does root with a trailing slash behave? |
| `/api/catalogue/items/42` | Is a similar-looking prefix rejected? |
| `/API/catalog/items/42` | Does case sensitivity match the contract? |
| `/api/catalog/items/%34%32` | How are decoded paths and URI variables handled? |
| `/api/catalog/items/%2Fetc` | How does the proxy/container layer handle encoded slashes? |
| `/api/catalog/../admin` | Are dot segments normalized before predicate evaluation? |

Gateway WebFlux documentation describes the `matchTrailingSlash` option on `Path`; in the referenced releases, it **defaults to true**. For strict slash matching, use full args form:

~~~yaml
- name: Path
  args:
    patterns.0: /api/catalog/items/{id}
    matchTrailingSlash: false
~~~

For the lab's `Path=/api/catalog/**`, `matchTrailingSlash` may **not distinguish every path** because `**` is already broad. When an API requires an exact segment/format, pick a narrower pattern and write matching tests.

**Important:** If `spring.webflux.base-path` is configured, Gateway docs note it affects how path predicates are interpreted (the base path is prepended to patterns). Do not test only `/api/catalog/**` locally and overlook a non-empty base path in staging.

### 10.2. Path Rewrite Filters Do Not Run Before Route Selection

For a route:

~~~yaml
predicates:
  - Path=/external/**
filters:
  - StripPrefix=1
~~~

Predicates inspect the **client path arriving at the Gateway**. `StripPrefix` runs only after the route is chosen because it is a **`GatewayFilter`**. Therefore:

- `GET /external/items/42` matches the route, and the backend receives `/items/42`.
- `GET /items/42` does not match the route just because stripping the prefix produces the same path.

In tests, assert both the **client path** and the **backend path**. Looking only at backend responses can hide an overly broad route predicate or an unexpected rewrite.

### 10.3. Method: GET Differs from HEAD/OPTIONS/POST

For example:

~~~yaml
- Method=GET
~~~

does not mean every "GET-like" method matches by default. Test `HEAD`, `OPTIONS`, `POST`, `PUT`, `PATCH`, and `DELETE` individually when a route restricts methods.

To allow multiple methods:

~~~yaml
- Method=GET,HEAD
~~~

When browser CORS preflight is enabled, `OPTIONS` requests may be rejected by the Gateway route predicate or handled by a separate CORS layer before reaching the backend. An `OPTIONS 200` answered by CORS middleware **does not prove** the GET route was selected.

### 10.4. Header and Cookie: Presence Does Not Guarantee Value Match

Header predicate:

~~~yaml
- Header=X-Channel,^partner$
~~~

Test thoroughly:

- Header absent.
- Header present with empty value.
- `partner` matches.
- `Partner`, `partner-extra`, or `other` does not match.
- Lowercase header name `x-channel` must still be recognized by the HTTP stack.
- Multiple/duplicate header values, commas/whitespace, and large values.

Cookie predicate syntax:

~~~yaml
- Cookie=region,^(north|south)$
~~~

Cases:

~~~http
Cookie: region=north
Cookie: region=east
Cookie: session=abc
~~~

Correspondingly, distinguish **match, value mismatch, and missing cookie**. However, browser/client cookies are **not proof of authorization**; cookie authentication must validate signatures/sessions/CSRF and proper policies.

### 10.5. Query: Missing, Regex, Duplicate Keys

~~~yaml
- Query=mode,^full$
~~~

differs from:

~~~yaml
- Query=mode
~~~

The regex form requires the parameter value to match the pattern; the name-only form checks only parameter presence. Test:

~~~text
?mode=full
?mode=short
?mode=
?other=full
?mode=full&mode=short
?mode=full%20
?Mode=full
~~~

For duplicate keys, value ordering and how your Gateway/Spring version evaluates regexes must be **verified empirically**, never assumed to pick first or last. If downstream allows multi-value query params, test **what reaches the backend** to avoid parameter pollution.

### 10.6. Host: Virtual Host Does Not Mean Trusted Caller

~~~yaml
- Host=**.example.test
~~~

The Host predicate supports patterns and URI template variables like `{sub}.example.test`. Over plain HTTP locally, a client can forge Host:

~~~bash
curl -i "http://127.0.0.1:8080/api/catalog/items/42?mode=full" \
  -H "Host: catalog.test" \
  -H "X-Channel: partner"
~~~

This is fine for **testing route matching**, not for proving the caller is an "authenticated partner". Production checks must verify:

1. Public ingress accepts only allowed hosts.
2. TLS SNI/certificates and HTTP Host match cleanly.
3. Reverse proxies preserve or rewrite Host as designed.
4. No network path bypasses ingress so clients can spoof Host directly against the Gateway.
5. Host alone never replaces authentication/authorization.

### 10.7. RemoteAddr and XForwardedRemoteAddr

Predicate:

~~~yaml
- RemoteAddr=10.10.0.0/16
~~~

evaluates the remote address using the Gateway's resolver. Behind a reverse proxy, the remote socket address may be the **proxy's IP**, not the real client IP. Do not try to "test client IP" by merely adding:

~~~http
X-Forwarded-For: 10.10.1.55
~~~

and assuming `RemoteAddr` will automatically pick `10.10.1.55`. WebFlux Gateway also supports X-Forwarded-For-based resolvers/predicates in some versions; trust configuration must reflect the **number of trusted proxies**, never `trustAll` on untrusted traffic.

Test at two levels:

- **Unit/integration on simulated network:** supply the expected remote address via a mock exchange or a test reverse proxy.
- **Staging through real edge:** send requests from allowed and disallowed IPs, attempt spoofed XFF, and log the address chosen by the resolver.

Never rely on an untrusted client IP header to expose an admin route or bypass authentication.

### 10.8. After, Before, Between: Time Makes Tests Flaky

Gateway time-based predicates take `ZonedDateTime`:

~~~yaml
predicates:
  - After=2020-01-01T00:00:00Z
  - Before=2100-01-01T00:00:00Z
~~~

This example uses a wide window to illustrate syntax, **not a production policy**. `Between` requires both a start and end timestamp, with the second strictly after the first.

Flaky test pattern:

~~~text
now + 100 ms -> request starts
CI under load/GC/slow pipeline -> request reaches Gateway later than expected
=> assertion flips depending on machine clock
~~~

Principles:

1. Never use boundaries a few milliseconds from current time in HTTP integration tests.
2. Pick **far-past/far-future timestamps** when you only need to verify basic match/no-match branches.
3. To test exact boundary transitions, extract time logic into a **custom predicate taking an injectable `Clock`** or a directly testable class. Do not assume built-in After/Before/Between expose a mockable `Clock` in every version.
4. Use UTC or explicit zone offsets; avoid ambiguous timestamps during DST transitions.
5. Verify clock synchronization across Gateway replicas when policies depend on time.

### 10.9. Version Predicate Is Version-Specific

Gateway WebFlux 5.x offers a `Version` predicate integrated with Spring Framework API versioning. A route:

~~~yaml
predicates:
  - Path=/api/**
  - Version=1.3
~~~

is meaningful only when an **`ApiVersionStrategy`** is configured to resolve versions from headers, query parameters, media-type parameters, or paths. Gateway 5.x docs warn: **if no strategy is configured, the Version predicate can always pass** because requests without a resolved version are treated as matching.

Therefore, when using the Version predicate, test:

- Presence and absence of the version header/query param.
- Matching version, different version, and malformed version.
- That the application **actually registers a version resolver**.
- Which route ID is selected when multiple versions exist.
- Never treat the Version predicate as providing authentication or a compatibility contract by itself.

Do not copy 5.x `Version` into a Gateway 4.2 project without verifying feature/version support.

### 10.10. ReadBody and Predicates with Body Overhead

Gateway WebFlux supports the `ReadBody` predicate in Java DSL:

~~~java
// Java DSL snippet; lambdas cannot be written directly in YAML.
.route("body-route", r -> r
        .readBody(String.class, body -> body.contains("yes"))
        .uri("http://127.0.0.1:9091"))
~~~

Per referenced Gateway 4.3/5.x documentation, `ReadBody` requires a Java `Predicate<T>` and **cannot express its lambda directly in YAML configuration**. The predicate reads and caches the request body so downstream steps can replay it.

Negative tests here must check:

- Valid, non-matching, empty, and malformed bodies.
- Codecs, `Content-Type`, and charsets.
- Large payloads exceeding limits and memory usage.
- That the body replays intact to the backend after predicate evaluation.
- Concurrent requests and cancellations so buffers are not leaked.

Do not use a body-reading predicate on every request just to inspect what could be a simple header: it adds CPU/heap/direct-buffer overhead and interferes with streaming.

### 10.11. Weight Predicate Is Not Deterministic Per Single Request

A traffic split using weight groups, such as 80/20, yields a **statistical outcome**. Do not write a test like:

~~~text
Send one GET -> must hit route A because A's weight is 80
~~~

Any individual request can land on route B. Proper approach:

1. Unit test weight-group configuration/registration.
2. Integration test with enough sample requests to measure distribution within a reasonable tolerance.
3. Avoid asserting exact 80/20 splits because of randomness and concurrency.
4. For deterministic routing logic, isolate the selector or inject a controllable random source in unit tests.
5. Verify security/routing policies match across branches, not just traffic ratios.

Do not use weight to guarantee a tenant always hits the same instance; that requires sticky routing/session affinity.

## 11. Overlapping Routes, Fallbacks, and Precedence

This is the easiest way to get **false positives** in predicate testing. Consider two routes:

~~~yaml
# Route fragments only; place under the version-appropriate namespace.
- id: catalog-partner
  order: -10
  uri: http://127.0.0.1:9091
  predicates:
    - Path=/api/catalog/**
    - Method=GET
    - Host=catalog.test
    - Header=X-Channel,^partner$
    - Query=mode,^full$
  filters:
    - AddResponseHeader=X-Matched-Route,catalog-partner

- id: catalog-fallback
  order: 100
  uri: http://127.0.0.1:9091
  predicates:
    - Path=/api/catalog/**
    - Method=GET
  filters:
    - AddResponseHeader=X-Matched-Route,catalog-fallback
~~~

**The second route is an intentional fallback** for catalog GETs; it ignores Host/Header/Query. Enable it only in a **separate test suite**: adding it to the `predicate-test` profile from section 8 breaks expectations that partner-route negative cases return 404 or leave backend call counts unchanged.

### 11.1. Matrix When a Fallback Exists

| Request | Partner route matches? | Fallback route matches? | Expected selection |
| --- | --- | --- | --- |
| GET with valid Path/Host/Header/Query | Yes | Yes | `catalog-partner` because order -10 beats 100 |
| GET with valid Path, wrong Host | No | Yes | `catalog-fallback` |
| GET with valid Path, missing Header | No | Yes | `catalog-fallback` |
| GET with valid Path, wrong Query | No | Yes | `catalog-fallback` |
| POST with valid Path | No | No | No route in this fixture |
| GET with different Path | No | No | No route in this fixture |

For instance, a wrong-Host GET **can return HTTP 200** from the fallback. That is not a Host predicate bug: the partner route was skipped and another route matched. If the application assumes the partner route is the sole allowed entry point, such a broad fallback becomes an **authorization vulnerability**.

### 11.2. Testing Correct Selection When Both Match

With a valid request:

~~~bash
curl -i \
  "http://127.0.0.1:8080/api/catalog/items/42?mode=full" \
  -H "Host: catalog.test" \
  -H "X-Channel: partner"
~~~

Expected:

~~~text
HTTP 200
X-Matched-Route: catalog-partner
~~~

If the header is `catalog-fallback` even though both match, check:

- Did `order` actually bind as intended?
- Was the partner route skipped due to a missing predicate or failed materialization?
- Did an ingress rewrite Host, query, or headers before the Gateway saw them?
- Does a third route have even higher priority?
- Do cached route definitions share the same revision across Gateway replicas?

### 11.3. Testing That Fallbacks Do Not Capture Privileged Requests

A design choice may be to **forbid the fallback from matching partner paths**, rather than relying solely on ordering:

~~~yaml
predicates:
  - Path=/public/catalog/**
  - Method=GET
~~~

Separating public and partner namespaces lets you cross-test that `/api/catalog/**` requests never enter `/public/catalog/**`. Still, if security depends on tokens/roles, enforce Spring Security and backend authorization; **path/route predicate layout alone is not a complete security boundary**.

### 11.4. Avoid Duplicate Route IDs or Unintentional Order Ties

Two routes sharing the same ID across sources (YAML, Config Server, Redis, Java DSL) can produce unpredictable observability/refresh behavior and materialization errors. For two routes with identical predicates and equal `order`, tie-breaking behavior **must not be relied upon as a business contract** unless explicitly documented and verified on your version.

In test setups:

- Assign unique IDs.
- Assign explicit `order` whenever predicates can overlap.
- Test both positive and negative cases for every route in the group.
- Use route markers or distinct backend targets to observe which route actually ran.

## 12. Negative Route Tests Differ from Negative Security Tests

A predicate returning false keeps a request **out of that route**, but it does not automatically protect the whole Gateway or backend from malicious requests. For example:

~~~yaml
- Host=admin.example.test
- Header=X-Is-Admin,^true$
~~~

These two conditions only inspect a **client-controllable Host and header**. Never treat them as authentication. A client can send:

~~~bash
curl "http://127.0.0.1:8080/admin" \
  -H "Host: admin.example.test" \
  -H "X-Is-Admin: true"
~~~

Therefore, sensitive routes must test:

| Test category | Requirements |
| --- | --- |
| Predicate selection | Right route is/is not selected by path/method/host/header/query |
| Authentication | Anonymous, expired token, bad issuer/audience, valid signed token |
| Authorization | Valid principal lacking required role/scope/tenant permission |
| Backend trust | Client-spoofed identity headers stripped; backend verifies context |
| Rate limiting | Trusted quota keys, 429s, store outages, no bypass via fallback |
| CORS/CSRF | OPTIONS preflight, browser credentials, state-changing requests |
| Host/forwarded trust | Client-spoofed Host, X-Forwarded-For/Proto, proxy bypass |
| TLS | HTTPS, SNI/certificates, downstream TLS/mTLS, and downgrade policy |

**A passing predicate test does not prove complete security.** When adding a route, run the security matrix too and verify filters apply to the **actually selected route**, not just one entry in YAML.

### 12.1. CORS OPTIONS Paths Are a Special Case

Browsers can send:

~~~http
OPTIONS /api/catalog/items/42 HTTP/1.1
Origin: https://portal.example.test
Access-Control-Request-Method: GET
Access-Control-Request-Headers: X-Channel
~~~

Because the lab route specifies `Method=GET`, `OPTIONS` **does not match** by method. Yet the Gateway/Spring CORS handler can process preflight under its own config; a `200`/`204` preflight response does not mean the GET route forwarded to the backend.

Separate three assertions:

1. `OPTIONS` preflight returns CORS headers per policy (if CORS is enabled).
2. The backend **is not called** by preflight when handled at the Gateway.
3. Only the actual GET with valid Origin/headers hits the right route and receives valid CORS response headers.

Never use wildcard `Access-Control-Allow-Origin: *` with credentials, and never treat CORS as authentication.

### 12.2. Header Predicates Do Not Replace Header Filters

`Header=X-Channel,^partner$` uses the header only to **select a route**. It does not strip client headers, verify signatures, or attach trusted downstream identity. If the backend trusts an `X-Partner-ID` marker, you must:

- Authenticate the partner using a real mechanism.
- Strip headers that clients could spoof.
- Generate the fresh marker from the verified security context.
- Connect to the backend across an appropriate trust boundary.
- Verify the backend receives only the verified value.

Predicates and **`GatewayFilter`/WebFilter/Spring Security** serve distinct roles. Each layer requires its own tests.

## 13. Diagnosing Unexpected Test Failures

### 13.1. Ask: "Was Any Route Actually Loaded?"

A negative test returning 404 might happen because the **route did not match**, or because the YAML route **failed to load** due to a wrong prefix, missing starter, missing predicate factory bean, or binding errors.

Before debugging Path/Header/Host logic, verify the **runtime route exists**:

1. Gateway starts without configuration errors.
2. Route ID `catalog-partner` appears in the runtime route list.
3. Predicate strings match the intended configuration.
4. For a completely valid request, the Gateway actually forwards to the backend.
5. The stub backend is alive with no port conflict.

If the positive case fails, **do not trust passing negative cases** even if all of them return 404.

### 13.2. Actuator Inspects Route Config, Not Whether a Request Matched

When Spring Boot Actuator is enabled **on an isolated management plane**, Gateway WebFlux can expose:

~~~bash
# Run only on an authorized internal management port:
curl -sS "http://127.0.0.1:9090/actuator/gateway/routes"

curl -sS \
  "http://127.0.0.1:9090/actuator/gateway/routes/catalog-partner"
~~~

These endpoints inspect runtime routes: route ID, URI, predicates, filters, and order. However, **`GET /actuator/gateway/routes`** only shows what routes are **registered**, not whether a specific request traversed a route.

In the section 8 integration example, **Actuator need not be exposed** for testing: response markers and MockWebServer suffice. When using Actuator in staging:

- Restrict `management.endpoint.gateway.access=read-only`.
- Expose only needed endpoints with authentication/RBAC.
- Never expose `/actuator/gateway/routes` or write/refresh endpoints to the Internet.
- If routes refresh from a DB/Config Server, verify each replica received the expected revision.

### 13.3. Logging Helps, but Does Not Replace Assertions

When debugging in an isolated environment:

~~~yaml
logging:
  level:
    org.springframework.cloud.gateway: DEBUG
~~~

Logging can reveal route matching/factories/errors for your version. Do not leave DEBUG/TRACE enabled long-term in production; in particular, never log raw `Authorization`, `Cookie`, raw bodies, query credentials, or IP/tenant PII.

A useful trace distinguishes:

~~~text
requestId = test-123
selectedRouteId = catalog-partner
downstreamHost = 127.0.0.1:9091
responseStatus = 200
downstreamAttempts = 1
~~~

These field names are **custom observability examples**, not a claim that the Gateway emits all four fields by default. Keep correlation IDs safe so clients cannot inject control characters into logs.

### 13.4. Why 502/503 Differs from a Predicate Miss

Consider:

~~~text
Predicate match = true
  → right route selected
  → Gateway calls backend
  → backend port closed
  → HTTP 5xx due to transport / unavailable
~~~

This is **route selection succeeded, upstream call failed**. If a test only contains:

~~~java
client.get()
        .uri("/api/catalog/items/42?mode=full")
        .exchange()
        .expectStatus().isOk();
~~~

it does not tell you whether the failure was in the predicate or the backend. Add Host/Header, verify the route exists, check the backend stub, response markers, and logs. Some filters may skip adding markers when an error occurs before headers are written; **do not treat a missing marker as sole proof of a predicate miss**.

### 13.5. Keeping Tests from Passing via Unrelated Handlers

When running Gateway tests, avoid scanning unrelated controllers. You can:

- Use a **test application** holding only Gateway route config.
- Target `@SpringBootTest(classes = GatewayApplication.class)` in a clean package.
- Disable discovery locator and secondary route sources in the test profile if present.
- Assign unique route IDs and avoid overlapping paths across routes.
- Assert **backend recordings** in addition to HTTP status.

If the project auto-generates routes from service discovery, negative cases could be picked up by a discovery route. Disable the discovery locator in the fixture or assert the exact selected route within scope.

## 14. Designing CI for Stable, Debuggable Results

### 14.1. Do Not Depend on Internet Backends

A route integration test must not route to:

~~~yaml
uri: https://some-public-api.example
~~~

and assert 200. The Internet introduces DNS, TLS, rate limits, WAFs, traffic policies, and changing responses. **MockWebServer or WireMock on a random port** keeps tests independent of external networks and records requests.

### 14.2. Managing Test State

| Source of state | Risk | Mitigation |
| --- | --- | --- |
| Fixed Gateway port | Collisions during parallel runs | `RANDOM_PORT` |
| Fixed backend port | CI port conflicts | Mock backend on random port |
| Stub response queue | Stale response leaks into next test | Queue-free dispatcher or explicit reset |
| Shared request count | Parallel tests skew counts | Sequential execution per fixture or dedicated stub per test |
| Gateway route cache | Fixture keeps routes from prior test | Isolated context/profile/revision |
| Discovery registry | Instances change outside test | Stub registry or disable auto-discovery |
| Time predicates | Clock/timezone shifts | Far-boundary timestamps or controllable `Clock` |
| Retry/timeout | One request triggers multiple backend calls | Disable retries in predicate-only fixtures or assert per policy |
| Security middleware | 401/403 blocks before routing | Deliberate test security setup |

### 14.3. Fallback Tests Need Their Own Class/Profile

Adding a fallback route **changes the contract**: a negative case on the primary route no longer means "backend not called". Separate them:

- `PredicateStrictRouteIT`: single route; negative = zero downstream calls/404.
- `PredicateFallbackRouteIT`: two routes; negative on primary = **fallback selected**, matching route marker, expected backend hit.
- `PredicateSecurityIT`: tests auth, roles/scopes, tenant boundaries, and CORS.

Do not mechanically reuse an "expect 404" test method across every environment.

### 14.4. Mutation Checks and Regression-Catching Power

A strong way to evaluate your negative matrix is **temporarily removing each predicate in a test branch**:

~~~text
Remove Method=GET  -> POST test must fail
Remove Host=...    -> wrong Host test must fail
Remove Header=...  -> missing/wrong Header test must fail
Remove Query=...   -> missing/wrong Query test must fail
Remove Path=...    -> wrong Path test must fail
~~~

If removing a predicate leaves the suite green, **the test is not actually enforcing that condition**, something else is blocking it, or it is asserting the wrong behavior. You do not need a mutation-testing framework to perform this sanity check, and it belongs in reviews for sensitive routes.

### 14.5. Completion Criteria for a Test Pipeline

CI reports should state:

~~~text
Test suite: predicate-routing
Version: Spring Boot + Spring Cloud Gateway (exact BOM)
Profiles: predicate-test
Test backend: MockWebServer random port
Positive cases passed: 1 or more
Negative cases passed: 7 or more
Backend unexpected calls: 0
Unmatched route observations: expected
Test failures: 0
~~~

This is a **report template**, not executed output from this article. Never report "PASS" if Maven/Gradle actually ran **0 tests** or merely compiled without executing integration tests.

## 15. Troubleshooting Table

| Symptom | Possible cause | Where to check |
| --- | --- | --- |
| Every request returns 404, including positive | Route failed to load, wrong YAML prefix, missing starter | Route inventory/logs, profile, BOM, route ID |
| Positive returns 404, backend receives no calls | A predicate is false: Host/Header/Query/Path/Method | Compare raw request against T0 matrix |
| Positive returns 502/503 | Route matched, backend/transport failed | Stub port, DNS, TLS, timeout, error mapping |
| Positive 200 but wrong route marker | Another route has higher order or different filters | Route priority and overlapping predicates |
| Negative Host returns 200 | Fallback matched, Host header rewritten, predicate missing | Route/backend markers, ingress/proxy behavior |
| Negative Method returns 405 instead of 404 | Another Servlet/WebFlux handler or method handling | Inspect `HandlerMapping`/route list |
| Negative Header still matches | Header not configured, overly broad regex, duplicate headers | Full args vs shortcut, actual headers |
| Lowercase header name rejected | Custom code/proxy normalizes improperly | HTTP header semantics, captured request |
| Query `?mode=full&mode=short` acts strangely | Duplicate query values and parser behavior | Recorded request, resolver, route predicate implementation |
| Slash cases differ between local and staging | Base-path, ingress rewrite, URL decoding, matcher config | Raw incoming path at Gateway |
| `RemoteAddr` sees proxy IP instead of client | Peer is reverse proxy; XFF not used by resolver | Trusted proxy topology and resolver |
| Spoofed XFF accepted | Trust-all or ingress fails to sanitize | Spoofing negative tests |
| OPTIONS returns 200 yet GET does not forward | CORS preflight is independent of GET route | Actual GET request, backend call count |
| Test backend count increases by >1 | Retries/redirects/filters or parallel traffic | Recorded requests, retry config, isolation |
| Passes locally but flakes in CI | Port collisions, races, shared stub state, time windows | `RANDOM_PORT`, lifecycle, test parallelism |
| 404 test fails after adding fallback | Contract changed while test still expects no route | Assert fallback route ID/target |
| `Version` predicate does not filter versions | Missing `ApiVersionStrategy` in 5.x | Version resolver + positive/negative version tests |
| Wrong URI template variable | `Path` pattern/encoding mismatch | Check `URI_TEMPLATE_VARIABLES_ATTRIBUTE` and rewrites |

### 15.1. Workflow for Analyzing a Failed Test Case

1. **Confirm the test actually ran** with the intended profile/BOM.
2. **Confirm the runtime route exists** and matches the intended predicate definition.
3. **Inspect the incoming request at the Gateway**: method, raw path, Host, Headers, query, remote address.
4. **Inspect the selected route**: marker, route ID, order; is there a fallback?
5. **Inspect recorded backend requests**: was a call made, and were method/path/headers right?
6. **Inspect downstream errors**: 5xx from transport, DNS, LB, TLS, or backend.
7. **Inspect security/CORS**: did something handle the request before route matching?
8. **Rule out test pollution**: stub queue, shared counters, concurrency, config refresh.
9. **Fix code/config or update test expectations with evidence**—never relax 404 to "any 4xx".

An overly loose assertion like `is4xxClientError()` blurs 401 auth failures, 403 policy denials, 404 route misses, and 429 rate limits. Predicate tests must verify **routing outcomes and downstream forwarding**, not broad status categories.

## 16. Extension Exercises

### Exercise 1 — Add Another Method Option

Change:

~~~yaml
- Method=GET
~~~

to:

~~~yaml
- Method=GET,HEAD
~~~

Write two tests verifying GET and HEAD match while POST is still rejected. Remember that **HEAD responses have no body per HTTP semantics**, so you cannot reuse GET's JSON body assertions. Verify via route markers/backend attempts instead.

### Exercise 2 — Narrow the Path

Replace `Path=/api/catalog/**` with a single-item pattern such as `/api/catalog/items/{id}`. Test:

- `/api/catalog/items/42`: matches.
- `/api/catalog/items/42/details`: does not match.
- `/api/catalog/items/`: does not match an item pattern requiring an ID.
- `/api/catalog/items/42/`: depends on `matchTrailingSlash`.

Explain why the old positive test **did not prove** the wildcard was not overly broad.

### Exercise 3 — Add a Fallback and Update Assertions

Add `catalog-fallback` with `order: 100` and its own marker. Update the negative tests for Host/Header/Query to assert:

~~~text
Strict partner route: NO match
Fallback route: MATCH
HTTP response: may be 200
X-Matched-Route: catalog-fallback
Backend call: YES
~~~

If tests still expect 404, they are testing an **older architecture**, not the new behavior.

### Exercise 4 — Test `X-Forwarded-For` Spoofing

Set up a test reverse proxy (without Internet) to separate the **proxy's real IP** from **client-sent XFF**. Design two cases:

1. Trusted proxy sanitizes/appends XFF properly.
2. Client spoofs XFF trying to forge an allowed address.

Pass only when the resolver selects the **address dictated by trust topology**, not the client-supplied value.

### Exercise 5 — Regression Verification via Mutation

In a temporary test branch, remove `Header=X-Channel,^partner$` and run the "missing header" negative test. That test **must fail** because the backend gets called. Restore the config and repeat for every remaining predicate. This verifies matrix strength without needing a dedicated mutation-testing framework.

## 17. Pre-Release Predicate Testing Checklist

- [ ] At least one request **satisfies all conditions**, verifying route ID/marker and backend call.
- [ ] For **every predicate**, a negative case flips exactly one variable.
- [ ] Verify method/path/header/query/Host actually received by the Gateway, not assumed from client code.
- [ ] Verify **header names** are case-insensitive while **regex values** follow the declared pattern.
- [ ] Test trailing slashes, URL encoding, look-alike prefixes, and duplicate/empty/malformed queries.
- [ ] For Host and RemoteAddr, test ingress/reverse proxy topology and trust boundaries.
- [ ] Never use Host/`X-Forwarded-For`/client headers as proof of authentication.
- [ ] Distinguish a **predicate miss** from 401/403/429/502/503 generated by other layers.
- [ ] Assert **zero downstream calls** for negative cases in single-route fixtures.
- [ ] If a fallback exists, assert the **expected fallback route** rather than forcing no-hit/404.
- [ ] Route IDs are unique; `order` is explicit wherever predicates can overlap.
- [ ] Test configuration YAML binds to runtime routes under the Gateway version's exact namespace.
- [ ] Random application and stub ports; tests do not depend on the Internet or live backends.
- [ ] Stub returns clear markers and records method/path/headers plus backend request count.
- [ ] Test state is isolated; no stale queues/route caches or concurrent counter races.
- [ ] Tests are actually executed by the test runner; CI reports test counts and failures.
- [ ] CORS OPTIONS is tested separately from actual requests; security tests are not replaced by predicate tests.
- [ ] Time-based, Weight, Version, and ReadBody predicates use test methods matching their behavior.
- [ ] Actuator runs only on a secured management plane; write routes are never publicly exposed.
- [ ] For new or modified routes, run smoke tests through real TLS/Ingress and check Gateway replicas.
- [ ] Observability records route ID, response status, backend attempts, timeouts, latency, and categorized errors.

## 18. Self-Check Questions

**1. A route declares Path, Method, and Header. Will a request matching only Path and Method be selected?**

No. Predicates within the same `RouteDefinition` combine with logical **AND**; missing the Header causes the route not to match.

**2. Are `Method=GET,POST` and two lines `Method=GET`/`Method=POST` equivalent?**

No. A single Method predicate listing multiple methods is **OR**; two separate predicate lines on one route are **AND**, which cannot both be satisfied by an HTTP request having a single method.

**3. Is a 404 from a negative test enough to prove a route did not match?**

No. The backend could have returned 404 after receiving the request, or another handler returned 404. You need route markers and backend recordings/call counts.

**4. Why is testing `Host=catalog.test` not a partner-authentication test?**

Because clients can send arbitrary HTTP Host headers in many environments. The Host predicate is a routing condition, not a credential/permission check. Security chains and trust boundaries are required.

**5. After adding a catalog GET fallback route, must a wrong-query negative test return 404?**

No. The partner route does not match, but the fallback can match and return 200. Tests should assert `X-Matched-Route: catalog-fallback` and the corresponding backend target.

**6. Why is `@SpringBootTest(RANDOM_PORT)` with MockWebServer more valuable than testing a predicate factory alone?**

Because the integration test verifies **YAML binding, AND across predicates, Gateway route selection, filter markers, and downstream calls** over a real HTTP server; unit factory tests check only isolated logic.

**7. When a GET hits the right route but returns 503, is it reasonable to conclude the predicate is wrong?**

No. The request may have matched the right route while the backend, discovery, or connection failed. Inspect runtime routes/markers/downstream attempts and transport.

**8. When using `Version=1.3` on Gateway WebFlux 5.x, what must you verify first?**

Verify that an API version strategy/resolver is configured; if missing, the predicate may not filter versions as expected. Then test matching/wrong/missing versions.

**9. Why should an 80/20 Weight test not assert that the very first request hits the 80 route?**

Because weight-based routing is statistical; a single request proves nothing about distribution. Use large enough samples, tolerances, and verify matching policies across branches.

**10. When should a negative test be considered "not forwarded"?**

When there is evidence that the backend **received zero downstream calls** for the probe request in an isolated environment, not merely because the client saw 404 or a missing route marker.

## 19. Official References

1. [Spring Cloud Gateway Server WebFlux 5.0 — Route Predicate Factories](https://docs.spring.io/spring-cloud-gateway/reference/5.0/spring-cloud-gateway-server-webflux/request-predicates-factories.html): Path, Method, Host, Header, Query, Cookie, RemoteAddr, Version, ReadBody, and time predicates; AND across predicates.
2. [Spring Cloud Gateway WebFlux 4.3 — Request Predicates](https://docs.spring.io/spring-cloud-gateway/reference/4.3/spring-cloud-gateway-server-webflux/request-predicates-factories.html): syntax and behavior on 4.3.
3. [Spring Cloud Gateway WebFlux 4.2 — Route Predicate Factories](https://docs.spring.io/spring-cloud-gateway/reference/4.2/spring-cloud-gateway/request-predicates-factories.html): legacy route namespace and core semantics.
4. [Spring Cloud Gateway WebFlux 5.0 — Configuring Predicates and Filters](https://docs.spring.io/spring-cloud-gateway/reference/5.0/spring-cloud-gateway-server-webflux/configuring-route-predicate-factories-and-filter-factories.html): shortcut vs. full args and binding examples.
5. [Spring Cloud Gateway WebFlux 5.0 — How It Works](https://docs.spring.io/spring-cloud-gateway/reference/5.0/spring-cloud-gateway-server-webflux/how-it-works.html): `RoutePredicateHandlerMapping` and filter chain.
6. [Spring Cloud Gateway WebFlux 5.0 — Actuator API](https://docs.spring.io/spring-cloud-gateway/reference/5.0/spring-cloud-gateway-server-webflux/actuator-api.html): inspecting route IDs, predicates, filters, and order; securing management endpoints.
7. [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): `@SpringBootTest(RANDOM_PORT)`, WebTestClient, mock vs. running server.
8. [Spring Framework — WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html): `bindToServer`, response assertions, and end-to-end testing.
9. [OkHttp MockWebServer](https://square.github.io/okhttp/features/mockwebserver/): HTTP stub, recorded requests, dispatcher, and backend-call verification.
10. [Spring Security — Reactive Authorization](https://docs.spring.io/spring-security/reference/reactive/authorization/authorize-http-requests.html): WebFlux security policy is distinct from route predicates.

**Takeaway:** Testing route predicates is not "one valid request returns 200". A strong test suite proves **the right route is selected when all conditions match**, while proving **that route does not receive requests when any single condition fails**. Always combine **positive + negative + boundary cases**, route markers, recorded backend calls, and isolated test configs. With multiple routes, **a predicate miss does not mean the whole Gateway skips forwarding**: another route may still handle the request. Finally, remember that **predicates choose the path; authentication, authorization, rate limiting, retries, and TLS must be tested at their own responsibility layers**.
