# Testing HTTP Client URL, Method, Headers, Query, Body, and Call Counts

## 1. Goal: verifying the outbound request contract

In a Spring Boot application, an HTTP client class calling an external service can still return the expected Java object in a unit test while sending the **wrong URL**, **wrong HTTP method**, **missing headers**, **missing query parameters**, **mistyped JSON body**, or **more calls than designed**. None of those defects are caught if you only mock a business method such as `when(gateway.fetch()).thenReturn(...)`.

To verify the **outbound HTTP request**, you must run real client code while swapping out the external endpoint for a test double that **observes the request and returns a controlled response**. In Spring Boot 3.3, an effective choice for `RestClient` or `RestTemplate` is **`@RestClientTest` + `MockRestServiceServer`**. It intercepts HTTP commands issued by that client, matches them against expectations, and returns fake responses—**without opening a real HTTP socket**.

Conceptual example:

~~~java
server.expect(requestTo(
        "https://warehouse.example.test/api/stocks/SKU-1?warehouse=HCM&includeReserved=false"))
    .andExpect(method(HttpMethod.GET))
    .andExpect(header("X-Request-Id", "test-req-1"))
    .andExpect(queryParam("warehouse", "HCM"))
    .andExpect(queryParam("includeReserved", "false"))
    .andRespond(withSuccess(
        "{\"sku\":\"SKU-1\",\"warehouse\":\"HCM\",\"available\":12}",
        MediaType.APPLICATION_JSON));

StockSnapshot result = client.fetchStock(
        "SKU-1", "HCM", false, "test-req-1");

assertEquals(12, result.available());
server.verify();
~~~

This is an excerpt from a test class with the appropriate imports; the complete, compilable example appears in section 6. A good expectation verifies both the **request contract** and **response mapping**. If you only register `andRespond(withSuccess(...))` without calling `server.verify()`, an HTTP call that ought to happen yet never fires might go unnoticed without failing the test.

**Expected learning outcomes:**

1. Distinguish **testing an outbound HTTP client** from **testing an inbound REST controller** with MockMvc.
2. Grasp the scope of `@RestClientTest` and `MockRestServiceServer`, and configure `RestClient.Builder` properly.
3. Verify **scheme, host, port, path, and full URI** via `requestTo(...)`.
4. Verify **GET/POST/PUT/PATCH/DELETE** via `method(HttpMethod.XXX)`.
5. Verify required headers, forbidden headers, `Content-Type`, and `Accept` with request matchers.
6. Verify query parameters, boolean/numeric/repeated values, and how URI encoding affects assertions.
7. Verify JSON bodies **structurally**, using strict mode when the contract rejects extra fields.
8. Verify **exact 0, 1, N calls**, plus missing-call and unexpected-request cases.
9. Verify ordering across multiple requests, 4xx/5xx responses, and retry behavior when actually configured.
10. Build a complete Java 17 + Spring Boot **3.3.5** + Gradle + `RestClient` + JUnit Jupiter example.
11. Understand mock request factory limits and when to switch to WireMock/OkHttp MockWebServer for real HTTP networking.
12. Avoid brittle tests, missed critical fields, hardcoded secrets, and accidentally hitting live APIs in CI.

**"HTTP client and mocking" context:** This focuses on **client-side testing of outbound calls to external services**. We do not spin up an API controller to test `/stocks`, connect to a database, or use production credentials. The goal is proving client code **builds the right request** and **parses the right response** within the chosen boundary.

**Sample versions:** Java 17; Spring Boot **3.3.5**; Spring Framework **6.1.x**; Gradle and JUnit Jupiter. `RestClient` arrived in Spring Framework 6.1. On Spring Boot 2.x or Spring Framework 5.x, use `RestTemplate` or another HTTP client—do not copy the `RestClient` API from this lesson verbatim.

## 2. Choosing the right testing layer

| Test layer | What is real? | What is mocked? | Real HTTP socket? |
|---|---|---|---|
| Unit test mocking `WarehouseHttpClient` with Mockito | Service logic calling the gateway | Entire HTTP gateway | No |
| Unit test calling a URI helper function directly | Java URI building logic | No HTTP transport | No |
| **`@RestClientTest` + `MockRestServiceServer`** | **`RestClient`/`RestTemplate`, URI, HTTP method, headers, body serialization, response deserialization** | HTTP response and request factory | **No** |
| **MockWebServer / WireMock** with real client | Client, TCP/HTTP, real encoding/network request in test | External service on `localhost:randomPort` | **Yes** |
| Integration against real sandbox API | Client + external integration | Little or nothing | Yes, network-dependent |
| `MockMvc` / `@WebMvcTest` | Spring MVC inbound controller | Server request/response | No socket required |

**Most important distinction:** `MockMvc` tests **the server receiving requests**, whereas `MockRestServiceServer` tests **the client sending requests**. The word "server" in its name does not mean Spring Boot started an HTTP server; it is an internal replacement request factory inside the Spring Web client.

Per Spring Framework docs, real-socket mock web servers (WireMock, MockWebServer) are better when you need to test HTTP transport I/O details. `MockRestServiceServer` remains very effective for fast tests of URI, method, headers, queries, bodies, and call counts without ports or Docker.

### 2.1. Why not just use Mockito.verify(...)?

~~~java
verify(remoteGateway, times(2)).fetchStock("SKU-1", "HCM");
~~~

This Mockito snippet checks a **Java method call**; it does not prove whether the method sent `GET` or `POST`, appended query `includeReserved=false`, sent `Accept: application/json`, or what JSON body it serialized. Use Mockito when verifying that business logic invokes its collaborator properly; use the mock HTTP request layer when verifying the **HTTP contract**.

Likewise, avoid mocking each chained method of `RestClient`'s fluent API with Mockito when `MockRestServiceServer` is available. Mocking `.get().uri().header().retrieve().body()` creates fragile boilerplate tied to implementation details, whereas testing the actual request produced by `RestClient` is clearer and far more resilient.

## 3. Parts of an outbound HTTP request to verify

Example request:

~~~http
POST /api/reservations HTTP/1.1
Host: warehouse.example.test
Accept: application/json
Content-Type: application/json
X-Request-Id: req-100

{"sku":"SKU-1","quantity":3,"warehouse":"HCM"}
~~~

The dimensions to test break down into:

| Component | Common risk | Primary assertion |
|---|---|---|
| **URL** | Wrong scheme/host/base path, missing path variable, wrong environment | `requestTo("https://...")` |
| **Method** | `GET` accidentally changed to `POST`/`PUT`/`DELETE`, breaking idempotency | `method(HttpMethod.GET)` |
| **Header** | Missing auth/correlation id, wrong `Accept` or `Content-Type` | `header(...)`, `headerDoesNotExist(...)`, `content().contentTypeCompatibleWith(...)` |
| **Query** | Missing param, wrong boolean, broken encoding, duplicate/reordered keys | `queryParam(name, values...)`, exact URI/custom matcher |
| **Body** | Missing/extra JSON fields, wrong field name/type, empty payload | `content().json(expected, true)`, `content().string(...)` |
| **Call count** | Skipped call, extra call, unintended retry | `ExpectedCount.times(n)`, `server.verify()` |
| **Ordering** | Creating reservation before checking stock when business requires the reverse | Multiple `expect(...)` in sequence |
| **Response** | Unhandled 404/503, wrong JSON mapping | `withStatus(...)`, `withSuccess(...)`, assertions |

Define the **contract** before writing tests. A system may not care about query parameter ordering while requiring the exact key/value set. An HTTP server normally ignores JSON object key order. Never turn non-contractual ordering into a hard test requirement that breaks when the HTTP client is upgraded.

### 3.1. URL must verify base URL and path

If the code configures `RestClient.Builder.baseUrl("https://warehouse.example.test/api")`, URL expectations for `RestClient` in `@RestClientTest` must generally use the **full URI**. Spring Boot 3.3 docs state clearly:
- When the bean uses **`RestClient.Builder`**, `MockRestServiceServer` expectations must use the **full URI**.
- When the bean uses **`RestTemplateBuilder.rootUri(...)`**, expectations typically omit the root URI because of how the customizer handles it.
- When using `RestTemplateBuilder` without `rootUri`, expectations still use the full URI.

Therefore, do not blindly copy `requestTo("/stocks/SKU-1")` onto a `RestClient` configured with `baseUrl` and expect it to pass. If you hit `"Request URI expected ..., was ..."`, inspect the builder and URL contract rather than tweaking the mock to hide a dropped base path.

### 3.2. Method tied to semantics

HTTP GET reads data, POST creates resources, DELETE deletes/cancels; these are conventions, not replacements for a specific API doc. Tests should specify the exact `HttpMethod`:

~~~java
server.expect(requestTo("https://warehouse.example.test/api/reservations"))
    .andExpect(method(HttpMethod.POST))
    .andRespond(withSuccess(
        "{\"reservationId\":\"R-1\",\"status\":\"ACCEPTED\"}",
        MediaType.APPLICATION_JSON));
~~~

This snippet deliberately checks only URL/method; the full version checks headers and body too. A request hitting the right URL with the wrong method is caught by the matcher.

### 3.3. Headers: presence, value, and media type

`X-Request-Id`, `Authorization`, `Accept`, `Content-Type`, idempotency keys, or tenant IDs may belong to the contract. For standard request headers:

~~~java
.andExpect(header("X-Request-Id", "req-100"))
.andExpect(header("Accept", "application/json"))
~~~

`Accept` states the response media types the client accepts; `Content-Type` describes the request body format. Never swap them. For a JSON POST body, you can use:

~~~java
.andExpect(content().contentTypeCompatibleWith(
        MediaType.APPLICATION_JSON))
~~~

`contentTypeCompatibleWith` helps when `Content-Type` carries charset parameters and you do not want exact raw-string matching. For headers that must be **absent**, Spring provides `headerDoesNotExist("Authorization")`. Still, never assert that a client never sends `Authorization` if the production contract requires authentication; build fixtures with synthetic tokens and verify the real header at the appropriate layer.

**HTTP header names are case-insensitive** per protocol. Never write tests relying on exact casing like `"Content-Type"` vs. `"content-type"`, or on header ordering when the API does not require it.

### 3.4. Query parameters: verify both values and the parameter set

~~~java
.andExpect(queryParam("warehouse", "HCM"))
.andExpect(queryParam("includeReserved", "false"))
~~~

`queryParam(String, String...)` verifies the specified values, yet **does not automatically forbid extra values** for the same key or extra query keys. When the contract requires an exact request URI, pairing it with `requestTo("https://...?warehouse=HCM&includeReserved=false")` catches unexpected keys/values and serialized URI drift.

However, exact URI matchers are also sensitive to **query parameter ordering**. Over HTTP, `?a=1&b=2` and `?b=2&a=1` are typically equivalent for order-insensitive APIs. When the contract only cares about the parameter set, write a **custom `RequestMatcher`** parsing the URI query by key/value instead of hardcoding the whole query string. When a query uses repeated keys like `tag=java&tag=spring`, assert the **entire value list** if repetition and order matter.

**Encoding:** Avoid manual string concatenation such as `"?q=" + userInput`. Spaces, `&`, `?`, `#`, diacritics, or Unicode characters break URLs or change query meaning. Use `UriBuilder.queryParam(...)` and URI variables; write real tests with inputs containing spaces/`&` when the endpoint supports them. Whether you assert **decoded values** or **raw encoding** depends on the specific contract—do not assume every library writes `%20` vs. `+` identically.

### 3.5. JSON body: strict or lenient?

`MockRestRequestMatchers.content().json(...)` parses both expected and actual bodies as JSON, ignoring whitespace and object key order. Two modes:

~~~java
.andExpect(content().json(
        "{\"sku\":\"SKU-1\",\"quantity\":3,\"warehouse\":\"HCM\"}",
        true))
~~~

In Spring Framework 6.1, `json(String, boolean)` delegates to JSONassert:
- `strict=true`: JSON structure must match, **no extra object properties are allowed**, and array element ordering matters.
- `strict=false` or `json(String)`: lenient; ignores extra object fields and relaxes array ordering.
- Never compare raw JSON strings using `content().string(...)` unless raw formatting or payload signing is literally part of the contract.

Do not overuse lenient mode if the API forbids extra fields or security demands no secret leaks into the payload. Equally, avoid strict mode if the API permits optional fields and flexible array order. Choose the mode based on the contract, not whichever makes the test pass easily.

**JSON number vs. string:** In payloads, `{"quantity":3}` and `{"quantity":"3"}` have different types. `content().json` checks structure appropriately; add `jsonPath("$.quantity")` for field-specific rules, or parse the body with `ObjectMapper` for complex ordering/aggregation assertions.

## 4. Exact call counts: 0, 1, N, and unexpected requests

**`MockRestServiceServer` does more than stub responses.** Every registered expectation also specifies expected invocation counts.

### 4.1. Exactly once

~~~java
server.expect(requestTo("https://warehouse.example.test/api/stocks/SKU-1"))
    .andExpect(method(HttpMethod.GET))
    .andRespond(withSuccess(
        "{\"sku\":\"SKU-1\"}", MediaType.APPLICATION_JSON));

client.fetch(...);
server.verify();
~~~

Conceptual snippet; `client.fetch` must be defined in the relevant project. By default, a single `expect(requestTo(...))` requires **one request**. `ExpectedCount.once()` can also be written explicitly.

### 4.2. Exactly N times

~~~java
server.expect(
        ExpectedCount.times(2),
        requestTo("https://warehouse.example.test/api/stocks/SKU-1?warehouse=HCM&includeReserved=false"))
    .andExpect(method(HttpMethod.GET))
    .andRespond(withSuccess(
        "{\"sku\":\"SKU-1\",\"warehouse\":\"HCM\",\"available\":12}",
        MediaType.APPLICATION_JSON));

client.fetchStock("SKU-1", "HCM", false, "req-a");
client.fetchStock("SKU-1", "HCM", false, "req-b");

server.verify();
~~~

This snippet illustrates the full test logic; if the same expectation also matches a fixed request ID header, both calls must send the same ID—or use a flexible matcher/two separate expectations. Here only URL and method are matched, so two different request IDs pass.

`times(2)` enforces exactly 2 matching requests; **`verify()` catches missing requests**. Extra calls beyond the expected count cause the mock server to throw `AssertionError` immediately when the client attempts to execute them—do not wait until `verify()` for every failure check.

### 4.3. Must not call the API

If business logic rejects an input locally—such as `quantity <= 0`—it may return `Optional.empty()` without sending HTTP. In the test, **register no expectation**, invoke the method, and call `server.verify()`: any unexpected outbound request is caught the moment it is fired.

Some APIs support `ExpectedCount.never()`, though registering zero expectations on a freshly reset mock server already enforces **zero HTTP requests** through the bound client.

### 4.4. A missing call must turn the test red

~~~java
server.expect(
        ExpectedCount.times(2),
        requestTo("https://warehouse.example.test/api/stocks/SKU-1?warehouse=HCM&includeReserved=false"))
    .andRespond(withSuccess(
        "{\"sku\":\"SKU-1\",\"warehouse\":\"HCM\",\"available\":12}",
        MediaType.APPLICATION_JSON));

client.fetchStock("SKU-1", "HCM", false, "req-only-one");

assertThrows(AssertionError.class, server::verify);
~~~

This is a **negative test of the expectation engine itself**, so `assertThrows(AssertionError.class, ...)` is the expected passing behavior—not a test meant to fail on CI. Normal business tests must call `server.verify()` unwrapped to catch missing requests.

**Request order:** By default, `MockRestServiceServer` enforces the declaration order across distinct expectations. When an expectation has count > 1, its **first** call must arrive in order, while later repetitions may interleave per the expectation manager's rules. Only set `ignoreExpectOrder(true)` when the contract genuinely imposes no ordering; never enable it merely because a test fails on order.

## 5. Sample project structure

The project models an HTTP client calling an external Warehouse API via `RestClient`. Designed behaviors:

- `GET /api/stocks/{sku}?warehouse=HCM&includeReserved=false` returns stock JSON.
- `POST /api/reservations` sends JSON containing sku, quantity, warehouse, and receives receipt JSON.
- `DELETE /api/reservations/{id}` sends only method + header, **with no body**.
- `reserveIfPositive(...)` checks `quantity`; if non-positive, **sends no HTTP request**.
- `RestClient` is built from **Boot-provided `RestClient.Builder`** so `MockRestServiceServer` in `@RestClientTest` intercepts outbound requests.
- Tests verify **exact URL**, HTTP method, request headers, query parameters, strict JSON body, expected call counts, request ordering, and 404 handling.

### 5.1. File layout

~~~text
settings.gradle
build.gradle
src/main/java/demo/httpmock/HttpMockApplication.java
src/main/java/demo/httpmock/StockSnapshot.java
src/main/java/demo/httpmock/ReservationCommand.java
src/main/java/demo/httpmock/ReservationReceipt.java
src/main/java/demo/httpmock/WarehouseHttpClient.java
src/test/java/demo/httpmock/WarehouseHttpClientTest.java
~~~

**No** `application.properties` with production URLs, no PostgreSQL/Testcontainers, and no HTTP sockets are required. All test expectations bind to the mock request factory, so `warehouse.example.test` is purely a **fixture URL**. Zero DNS/network traffic happens when using the builder-managed `RestClient`.

### 5.2. settings.gradle

~~~groovy
rootProject.name = 'outbound-http-client-contract-test'
~~~

### 5.3. build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '1.0.0'

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test', Test) {
    useJUnitPlatform()
    testLogging {
        events 'passed', 'failed', 'skipped'
    }
}
~~~

Explanation:
- `spring-boot-starter-web` in Spring Boot 3.3 includes **Spring Web `RestClient`**, Spring HTTP converters, and Jackson for JSON records. Although `starter-web` brings an embedded servlet server, `@RestClientTest` **never starts an HTTP server**.
- `spring-boot-starter-test` provides Spring Boot Test, Spring Test `MockRestServiceServer`, JUnit Jupiter, AssertJ, JSONassert, and assertion libraries.
- The Spring Boot BOM manages compatible versions; do not pin separate Spring Framework 6.1 artifacts.
- Java 17 supports records and text blocks used throughout the tests.
- If an actual app only uses `spring-web`/`spring-boot-starter-json` with no server, dependencies can be trimmed separately; this example favors clarity and ease of running.

### 5.4. Application class

**src/main/java/demo/httpmock/HttpMockApplication.java**

~~~java
package demo.httpmock;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class HttpMockApplication {

    public static void main(String[] args) {
        SpringApplication.run(HttpMockApplication.class, args);
    }
}
~~~

Inside `@RestClientTest`, Spring Boot locates the primary application configuration via package hierarchy and loads only the HTTP client slice. Having `@SpringBootApplication` does not make the test boot all controllers/services/repositories or connect to live APIs.

### 5.5. DTOs: records for JSON input and output

**src/main/java/demo/httpmock/StockSnapshot.java**

~~~java
package demo.httpmock;

public record StockSnapshot(
        String sku,
        String warehouse,
        int available) {
}
~~~

**src/main/java/demo/httpmock/ReservationCommand.java**

~~~java
package demo.httpmock;

public record ReservationCommand(
        String sku,
        int quantity,
        String warehouse) {
}
~~~

**src/main/java/demo/httpmock/ReservationReceipt.java**

~~~java
package demo.httpmock;

public record ReservationReceipt(
        String reservationId,
        String status) {
}
~~~

All three records are Java 17 types. With Jackson configured, response JSON fields map onto record components, and request records serialize into JSON objects with keys `sku`, `quantity`, and `warehouse`. Tests make no assumptions about JSON object property order when using `content().json`.

If an external API uses different field names, add Jackson annotations/converters in the client per contract and write tests reflecting the exact wire format. Never change test expected JSON to match a buggy implementation just to turn tests green.

### 5.6. Production HTTP client code

**src/main/java/demo/httpmock/WarehouseHttpClient.java**

~~~java
package demo.httpmock;

import java.util.Optional;

import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

@Component
public class WarehouseHttpClient {

    public static final String BASE_URL =
            "https://warehouse.example.test/api";

    private final RestClient restClient;

    public WarehouseHttpClient(RestClient.Builder builder) {
        this.restClient = builder
                .baseUrl(BASE_URL)
                .build();
    }

    public StockSnapshot fetchStock(
            String sku,
            String warehouse,
            boolean includeReserved,
            String requestId) {

        return restClient.get()
                .uri(uriBuilder -> uriBuilder
                        .path("/stocks/{sku}")
                        .queryParam("warehouse", warehouse)
                        .queryParam("includeReserved", includeReserved)
                        .build(sku))
                .accept(MediaType.APPLICATION_JSON)
                .header("X-Request-Id", requestId)
                .retrieve()
                .body(StockSnapshot.class);
    }

    public ReservationReceipt reserve(
            ReservationCommand command,
            String requestId) {

        return restClient.post()
                .uri("/reservations")
                .accept(MediaType.APPLICATION_JSON)
                .contentType(MediaType.APPLICATION_JSON)
                .header("X-Request-Id", requestId)
                .body(command)
                .retrieve()
                .body(ReservationReceipt.class);
    }

    public Optional<ReservationReceipt> reserveIfPositive(
            ReservationCommand command,
            String requestId) {

        if (command.quantity() <= 0) {
            return Optional.empty();
        }

        return Optional.ofNullable(
                reserve(command, requestId));
    }

    public void cancel(String reservationId, String requestId) {
        restClient.delete()
                .uri("/reservations/{id}", reservationId)
                .header("X-Request-Id", requestId)
                .retrieve()
                .toBodilessEntity();
    }
}
~~~

**Deliberate design choices:**

1. The constructor receives **Spring Boot's `RestClient.Builder`** rather than calling `RestClient.create()` or `new RestTemplate()` directly. That allows Boot `@RestClientTest` to customize/bind the mock request factory onto the client.
2. `baseUrl` is a fixed fixture so readers can easily verify expected URIs. In real projects, inject the endpoint from `@ConfigurationProperties` and override it in test configuration; never hardcode production URLs.
3. `fetchStock` adds a path variable, two query params, an `Accept` header, and a request ID; it uses `uriBuilder` instead of concatenating user input into the URL.
4. `reserve` is a POST with a JSON body and explicit `Accept` and `Content-Type`. The example client adds no `Authorization`; an authenticated API must configure synthetic headers/tokens in tests.
5. `reserveIfPositive` introduces a **local business branch** blocking requests when `quantity <= 0`. This enables a meaningful **zero outbound calls** test.
6. `cancel` sends a bodyless DELETE and calls `toBodilessEntity()` to **trigger the request exchange** despite needing no response body. Writing `retrieve()` without a terminal operation never executes the exchange under the `RestClient` API.
7. No retries are configured in the client. On 404, `RestClient.retrieve()` throws an exception by default without retrying; the tests below verify a single request.
8. Spring/Jackson's JSON converter handles records; tests verify the actual JSON serialized into the HTTP request, not just the Java object before sending.

**Note on immutability:** Once built, `RestClient` is reusable and should not have a shared builder mutated concurrently from multiple threads expecting per-test isolation. Here one client bean is created once; `MockRestServiceServer` tests reset expectations between methods.

## 6. Complete test file: verifying all six contract dimensions

**src/test/java/demo/httpmock/WarehouseHttpClientTest.java**

~~~java
package demo.httpmock;

import java.util.Optional;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.client.RestClientTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.HttpClientErrorException;

import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.test.web.client.ExpectedCount.times;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.*;
import static org.springframework.test.web.client.response.MockRestResponseCreators.*;

@RestClientTest(WarehouseHttpClient.class)
class WarehouseHttpClientTest {

    @Autowired
    WarehouseHttpClient client;

    @Autowired
    MockRestServiceServer server;

    @BeforeEach
    void resetExpectations() {
        server.reset();
    }

    @Test
    void getChecksFullUrlMethodHeadersQueryAndResponse() {
        server.expect(requestTo(
                "https://warehouse.example.test/api/stocks/SKU-1?warehouse=HCM&includeReserved=false"))
            .andExpect(method(HttpMethod.GET))
            .andExpect(header("X-Request-Id", "req-1"))
            .andExpect(header(HttpHeaders.ACCEPT,
                    MediaType.APPLICATION_JSON_VALUE))
            .andExpect(headerDoesNotExist(
                    HttpHeaders.AUTHORIZATION))
            .andExpect(queryParam("warehouse", "HCM"))
            .andExpect(queryParam("includeReserved", "false"))
            .andRespond(withSuccess(
                    """
                    {"sku":"SKU-1","warehouse":"HCM","available":12}
                    """,
                    MediaType.APPLICATION_JSON));

        StockSnapshot stock = client.fetchStock(
                "SKU-1", "HCM", false, "req-1");

        assertNotNull(stock);
        assertEquals("SKU-1", stock.sku());
        assertEquals("HCM", stock.warehouse());
        assertEquals(12, stock.available());

        server.verify();
    }

    @Test
    void getWithOtherQueryValuesIsChecked() {
        server.expect(requestTo(
                "https://warehouse.example.test/api/stocks/SKU-2?warehouse=DN&includeReserved=true"))
            .andExpect(method(HttpMethod.GET))
            .andExpect(queryParam("warehouse", "DN"))
            .andExpect(queryParam("includeReserved", "true"))
            .andRespond(withSuccess(
                    """
                    {"sku":"SKU-2","warehouse":"DN","available":0}
                    """,
                    MediaType.APPLICATION_JSON));

        StockSnapshot stock = client.fetchStock(
                "SKU-2", "DN", true, "req-2");

        assertNotNull(stock);
        assertEquals(0, stock.available());
        assertEquals("DN", stock.warehouse());
        server.verify();
    }

    @Test
    void postChecksMethodHeadersAndStrictJsonBody() {
        server.expect(requestTo(
                "https://warehouse.example.test/api/reservations"))
            .andExpect(method(HttpMethod.POST))
            .andExpect(header("X-Request-Id", "req-3"))
            .andExpect(header(
                    HttpHeaders.ACCEPT,
                    MediaType.APPLICATION_JSON_VALUE))
            .andExpect(content().contentTypeCompatibleWith(
                    MediaType.APPLICATION_JSON))
            .andExpect(content().json(
                    """
                    {"sku":"SKU-1","quantity":3,"warehouse":"HCM"}
                    """,
                    true))
            .andRespond(withSuccess(
                    """
                    {"reservationId":"R-100","status":"ACCEPTED"}
                    """,
                    MediaType.APPLICATION_JSON));

        ReservationReceipt receipt = client.reserve(
                new ReservationCommand("SKU-1", 3, "HCM"),
                "req-3");

        assertNotNull(receipt);
        assertEquals("R-100", receipt.reservationId());
        assertEquals("ACCEPTED", receipt.status());
        server.verify();
    }

    @Test
    void getIsSentExactlyTwiceWhenExpected() {
        server.expect(
                times(2),
                requestTo(
                        "https://warehouse.example.test/api/stocks/SKU-1?warehouse=HCM&includeReserved=false"))
            .andExpect(method(HttpMethod.GET))
            .andRespond(withSuccess(
                    """
                    {"sku":"SKU-1","warehouse":"HCM","available":12}
                    """,
                    MediaType.APPLICATION_JSON));

        StockSnapshot first = client.fetchStock(
                "SKU-1", "HCM", false, "req-4a");
        StockSnapshot second = client.fetchStock(
                "SKU-1", "HCM", false, "req-4b");

        assertEquals(12, first.available());
        assertEquals(12, second.available());
        server.verify();
    }

    @Test
    void verifyDetectsWhenSecondExpectedRequestIsMissing() {
        server.expect(
                times(2),
                requestTo(
                        "https://warehouse.example.test/api/stocks/SKU-1?warehouse=HCM&includeReserved=false"))
            .andRespond(withSuccess(
                    """
                    {"sku":"SKU-1","warehouse":"HCM","available":12}
                    """,
                    MediaType.APPLICATION_JSON));

        client.fetchStock("SKU-1", "HCM", false, "req-5");

        // This is a negative test of the expectation engine itself:
        assertThrows(AssertionError.class, server::verify);
    }

    @Test
    void nonPositiveQuantitySendsNoHttpRequest() {
        // Mock server is already reset with zero expectations.
        Optional<ReservationReceipt> result =
                client.reserveIfPositive(
                        new ReservationCommand(
                                "SKU-1", 0, "HCM"),
                        "req-6");

        assertTrue(result.isEmpty());
        server.verify();
    }

    @Test
    void deleteChecksMethodHeaderAndEmptyBody() {
        server.expect(requestTo(
                "https://warehouse.example.test/api/reservations/R-100"))
            .andExpect(method(HttpMethod.DELETE))
            .andExpect(header("X-Request-Id", "req-7"))
            .andExpect(content().string(""))
            .andRespond(withStatus(HttpStatus.NO_CONTENT));

        client.cancel("R-100", "req-7");

        server.verify();
    }

    @Test
    void notFoundRaisesHttpClientErrorWithOneRequest() {
        server.expect(requestTo(
                "https://warehouse.example.test/api/stocks/ABSENT?warehouse=HCM&includeReserved=false"))
            .andExpect(method(HttpMethod.GET))
            .andRespond(withStatus(HttpStatus.NOT_FOUND)
                    .contentType(MediaType.APPLICATION_JSON)
                    .body("""
                          {"error":"stock not found"}
                          """));

        assertThrows(
                HttpClientErrorException.NotFound.class,
                () -> client.fetchStock(
                        "ABSENT", "HCM", false, "req-8"));

        server.verify();
    }

    @Test
    void separateExpectationsCheckRequestOrder() {
        server.expect(requestTo(
                "https://warehouse.example.test/api/stocks/SKU-3?warehouse=HCM&includeReserved=false"))
            .andExpect(method(HttpMethod.GET))
            .andRespond(withSuccess(
                    """
                    {"sku":"SKU-3","warehouse":"HCM","available":9}
                    """,
                    MediaType.APPLICATION_JSON));

        server.expect(requestTo(
                "https://warehouse.example.test/api/reservations"))
            .andExpect(method(HttpMethod.POST))
            .andExpect(content().json(
                    """
                    {"sku":"SKU-3","quantity":1,"warehouse":"HCM"}
                    """,
                    true))
            .andRespond(withSuccess(
                    """
                    {"reservationId":"R-103","status":"ACCEPTED"}
                    """,
                    MediaType.APPLICATION_JSON));

        StockSnapshot stock = client.fetchStock(
                "SKU-3", "HCM", false, "req-9a");
        ReservationReceipt receipt = client.reserve(
                new ReservationCommand("SKU-3", 1, "HCM"),
                "req-9b");

        assertEquals(9, stock.available());
        assertEquals("R-103", receipt.reservationId());

        server.verify();
    }
}
~~~

**Exact count: 9 `@Test` methods**, plus one `@BeforeEach` that is not a test. In the fifth method, `assertThrows(AssertionError.class, server::verify)` **deliberately expects a verification failure** because only one call ran when two were required; the JUnit method still PASSES when the mock server works properly. All other tests call `server.verify()` directly and only PASS when expectations were satisfied.

**Why use `@RestClientTest(WarehouseHttpClient.class)`?** The slice selects this client bean and configures `RestClient.Builder`, JSON conversion, and a `MockRestServiceServer`. Other `@Service` or `@Repository` beans are not auto-scanned into the slice. Since the production class accepts the builder via constructor, the mock server binds to that exact client when the bean is constructed. If you create another client outside the context with `RestClient.create()` later, it may **bypass** the mock server and hit the real network.

**Why `server.reset()` in `@BeforeEach`?** To keep expectations/counters independent across tests—especially because the negative test intentionally leaves a two-call expectation short by one call. Spring Boot provides test-slice reset support for the mock server, while an explicit reset makes test boundaries crystal clear. Never call reset **after registering** expectations and before calling the client, or you wipe out the expectations you meant to verify.

### 6.1. Test 1 verifies full URL, method, headers, and query

`requestTo(...)` compares the full URI, catching wrong scheme, host, `/api` prefix, path variables, or serialized query strings. `method(GET)` protects the HTTP method. `header("X-Request-Id", "req-1")` protects the correlation header. `Accept: application/json` is checked explicitly; `Authorization` is verified **absent** because the sample client uses no authentication. The two `queryParam` matchers check each query parameter's individual meaning.

The JSON response has three fields (sku/warehouse/available), which `RestClient.retrieve().body(StockSnapshot.class)` decodes into the Java record. If the request matches while DTO mapping breaks, assertions on the Java record still catch the bug. This is why you verify **both directions**: outbound request and inbound response.

### 6.2. Test 2 verifies different query values

A test using only `includeReserved=false` misses code that hardcodes `false`. The second test uses **true** and warehouse `DN`; both the exact URL and `queryParam` check the new values. If the client omits the boolean or hardcodes `HCM`, expectations fail.

Query values should cover business boundaries: empty strings, null-parameter policies, repeated values, Unicode, and characters needing encoding. Still, avoid adding dozens of tests just for URL length; focus on real risks.

### 6.3. Test 3 verifies POST body with strict JSON

`content().json(expected, true)` checks fields and types after Jackson serializes `ReservationCommand`, ignoring whitespace and object key order. It catches:
- `quantity` serialized as String `"3"` instead of number `3`;
- misspelled key `warehouseId` instead of `warehouse`;
- missing `sku` or unexpected extra properties in the body;
- sending no body, or sending invalid JSON.

`content().contentTypeCompatibleWith(APPLICATION_JSON)` verifies the request format. `header(HttpHeaders.ACCEPT, APPLICATION_JSON_VALUE)` verifies the response format requested by the client. The response decodes into `ReservationReceipt` with `reservationId` and `status`.

### 6.4. Tests 4 and 5 verify exact call counts

Test 4 registers `times(2)`, performs 2 `fetchStock` calls, and invokes `server.verify()`. If code fires 1 or 3 calls, the test no longer satisfies the expected count. Test 5 deliberately registers 2 and calls 1; `server.verify()` throws `AssertionError` caught by **`assertThrows`**. That demonstrates why tests must not stop right after receiving a fake response and forget `verify()`.

**Never write `times(2)` and claim two HTTP requests occurred if the client is using a separate `RestClient` unbound to the mock server.** The fundamental precondition is that `MockRestServiceServer` actually intercepts that HTTP client instance. With Boot `@RestClientTest` and Spring-injected builder as shown here, that condition holds.

### 6.5. Test 6 verifies zero outbound calls

`reserveIfPositive` with `quantity=0` returns `Optional.empty()` before reaching `RestClient`. `MockRestServiceServer` has zero expectations registered; if code accidentally fires a request, the mock request factory flags an unexpected request. If you only Mockito-mocked `WarehouseHttpClient` itself, you could never prove no underlying HTTP request was issued.

This is a meaningful business test, not an empty test: it invokes a public method containing HTTP-guarding logic, then asserts both the return value **and** zero HTTP side effects.

### 6.6. Test 7 verifies DELETE and empty body

`cancel` calls `DELETE /api/reservations/R-100`, sends `X-Request-Id`, and sends no JSON body. Expectation `content().string("")` asserts the UTF-8-decoded content bytes are empty; the stub returns `204 No Content`. The client calls `.retrieve().toBodilessEntity()` so the exchange actually executes, preventing a bug where code constructs a request without sending it.

### 6.7. Test 8 verifies 404 and no hidden retry

`withStatus(HttpStatus.NOT_FOUND)` simulates an HTTP error status. `RestClient.retrieve()` throws `HttpClientErrorException.NotFound` by default, which the test asserts. A single expectation followed by `server.verify()` also proves the code **does not issue a second GET** in this scenario.

If an application explicitly configures retries, tests must update expected attempts and before/after responses; never assume every 404 should be retried. Most systems retry only transient failures like 503/429, not 400/404.

### 6.8. Test 9 verifies request ordering

Two expectations are declared: **GET stock first, POST reservation second**. The code executes in that order and verifies both response mappings. When business rules require "check stock before reserving," ordering is part of the contract. However, if two calls are independent and may run concurrently, tests must not enforce an artificial order; see the sections on order-independent expectations and mock web servers.

## 7. Running tests and expected outcomes

If the project has **Gradle Wrapper**:

~~~bash
./gradlew test
~~~

On Windows PowerShell:

~~~powershell
.\gradlew.bat test
~~~

If you only created `build.gradle`, `settings.gradle`, and the source files from this lesson without generating **Gradle Wrapper scripts/JAR**, `./gradlew` does not exist yet. Use a compatible Gradle installation to generate the Wrapper or run `gradle test` directly. Command to run only the test class:

~~~bash
./gradlew test --tests demo.httpmock.WarehouseHttpClientTest
~~~

The sample project has **exactly 9 JUnit Jupiter test methods**, expected to PASS when imports, dependencies, and sources are created accurately; none are `@Disabled`, and no Docker or HTTP server is needed. This is an **expectation derived from inspecting the source**, not a claim that the test suite was executed in the reading environment.

Gradle reports typically appear at:

~~~text
build/reports/tests/test/index.html
~~~

| Test method | Primary contract |
|---|---|
| `getChecksFullUrlMethodHeadersQueryAndResponse` | Full URL, GET, headers, query, and response |
| `getWithOtherQueryValuesIsChecked` | Avoids hardcoded query values |
| `postChecksMethodHeadersAndStrictJsonBody` | POST, `Accept`, `Content-Type`, strict JSON body |
| `getIsSentExactlyTwiceWhenExpected` | Exactly 2 outbound calls |
| `verifyDetectsWhenSecondExpectedRequestIsMissing` | Proves `verify` catches missing calls |
| `nonPositiveQuantitySendsNoHttpRequest` | Zero outbound calls |
| `deleteChecksMethodHeaderAndEmptyBody` | DELETE, request header, empty body |
| `notFoundRaisesHttpClientErrorWithOneRequest` | 404 exception, exactly 1 call |
| `separateExpectationsCheckRequestOrder` | GET before POST, two responses |

**Do not invent arbitrary stdout snapshots.** Gradle may print additional Spring context logs, warnings, or test info; the deterministic outcome here is **the JUnit test method count and assertions satisfied**.

## 8. Negative tests: catching every category of contract violation

A powerful review technique is deliberately introducing a small "mutation" in the client code and checking which test fails. Never keep mutations in production; the goal is proving the test suite actually catches bugs.

| Hypothetical mutation | Test that must catch it |
|---|---|
| Change `BASE_URL` from HTTPS to HTTP | `requestTo` full URI |
| Drop `/api` prefix | `requestTo` full URI |
| Change `.get()` to `.post()` for stock | `method(GET)` |
| Drop `X-Request-Id` | `header(...)` |
| Drop `.accept(APPLICATION_JSON)` | `header(Accept, ...)` |
| Drop `includeReserved` or hardcode `false` | `queryParam`, exact URI, test with `true` |
| Change `quantity` from int to String via payload mapper | `content().json(..., true)` |
| Add unexpected property into JSON body | Strict JSON matcher |
| Call `fetchStock` twice when contract requires once | Extra request error / `times(1)` |
| Skip one request when test requires two | Caught by `server.verify()` |
| Move POST reservation before GET stock | Order-sensitive expectations |
| Auto-retry 404 without configuration | One-call expectation |
| Send DELETE with a non-empty body | `content().string("")` |
| Omit terminal `.body()`/`.toBodilessEntity()` call | `server.verify()` catches missing request |

**Note:** If the mutation corrupts **response handling** (e.g., `StockSnapshot.available` is always set to 0), verifying outbound requests alone is insufficient. Assertions on `StockSnapshot`/`ReservationReceipt` protect response mapping and the business adapter.

### 8.1. Do not turn tests into a copy of the implementation

If a test computes its expected URL using **the exact same helper function** that production code uses to build URLs, a bug in that helper breaks both expected and actual identically, making the test pass falsely. In the sample project, expected URLs are **literal contract values** in tests rather than calls back into the client's URI helper.

Similarly, never serialize `ReservationCommand` using **the client's own `ObjectMapper`** to build the expected JSON and compare against it when the goal is verifying wire field names/types against an external API contract. Independent expected JSON catches serializer bugs.

### 8.2. Mock responses do not replace error-mapping tests

`MockRestServiceServer` can simulate HTTP 400/401/404/409/429/500/503 and varied responses. Clients should define clear policies for:
- 400/422: validation errors, usually no retry.
- 401/403: auth errors, assert right error; never log tokens.
- 404: missing resource, decide whether to return `Optional.empty()` or throw.
- 409: conflict/idempotency semantics.
- 429/503: may retry when a retry/resilience policy is configured.
- malformed JSON: may throw `RestClientException`/message conversion exception; test matching behavior.
- empty 204/202 body: never call `.body(SomeRequiredDto.class)` and use the null object unchecked.

If the app uses Spring Retry/Resilience4j, test **exact real attempts** and the backoff policy rather than adding `times(3)` by guesswork. Avoid `Thread.sleep` in tests to check retries; use test clocks/schedulers or small deterministic backoff configurations.

## 9. RestClient, RestTemplate, and WebClient are not mocked the same way

### 9.1. Spring 6.1 RestClient (this lesson's sample)

`RestClient` is a synchronous HTTP client with a fluent API. `MockRestServiceServer` supports `MockRestServiceServer.bindTo(RestClient.Builder)` since Spring Framework 6.1; Spring Boot 3.3 `@RestClientTest` auto-configures the builder and mock server.

**Do not instantiate a client outside the Spring-managed builder in tests** if relying on the auto-configured mock. Wrong test setup example:

~~~java
// Inside the bean under test, avoid this initialization
// if you want Boot @RestClientTest to bind the mock server:
RestClient client = RestClient.create(
        "https://warehouse.example.test/api");
~~~

If production genuinely requires manual client creation, construct a builder yourself, bind `MockRestServiceServer` to **that exact builder**, and then build the client:

~~~java
RestClient.Builder builder = RestClient.builder();
MockRestServiceServer mock =
        MockRestServiceServer.bindTo(builder).build();

RestClient restClient = builder
        .baseUrl("https://warehouse.example.test/api")
        .build();
~~~

This is a wiring snippet, not a full test source. Ensure the code under test **uses that exact built `restClient`**; creating a separate mock server outside never intercepts requests from the production client.

### 9.2. RestTemplate

`RestTemplate` is the older synchronous HTTP client. You can use:

~~~java
RestTemplate restTemplate = new RestTemplate();
MockRestServiceServer server =
        MockRestServiceServer.bindTo(restTemplate).build();
~~~

With Spring Boot `@RestClientTest` and `RestTemplateBuilder`, inject the Spring-provided builder to construct `RestTemplate` so the customizer binds the mock automatically. When the builder sets `rootUri(String)`, Spring Boot docs generally guide placing **relative URIs** in expectations; do not copy `RestClient`'s full-URI literals if the `rootUri` customizer alters matching.

`RestTemplate` did not vanish simply because `RestClient` arrived, though new code on Spring 6.1+ can consider `RestClient` for synchronous APIs. Choose based on your version and project conventions.

### 9.3. WebClient (reactive) and MockWebServer/WireMock

Spring WebFlux's `WebClient` is reactive. **Do not use `@RestClientTest` + `MockRestServiceServer` as if it binds to `WebClient` automatically.** For `WebClient`, you can:
- Use an HTTP mock server (WireMock, OkHttp MockWebServer), point the client's base URL to `localhost:randomPort`, and check `RecordedRequest`/server verification.
- Unit-test a stubbed `ExchangeFunction` if only verifying mapping at the `WebClient` API layer, while recognizing reactive exchange mocks can skip HTTP encoding/transport.
- Use `StepVerifier` for publisher behavior when async/retry/backpressure exists, paired with a mock server to check real requests per client policy.

**`WebTestClient` is not a `WebClient` mock:** `WebTestClient` primarily **tests server-side endpoints** (either mocked or live HTTP); confusing the similar names easily puts tests at the wrong layer.

## 10. When do you need WireMock or OkHttp MockWebServer?

Per Spring Framework docs, a real-socket mock web server provides these benefits:
- Accepts requests over **TCP/HTTP** like a normal server.
- Exercises the real production HTTP client/connection pool/codecs instead of `MockRestServiceServer`'s special request factory.
- Simulates response delays, dropped connections, malformed headers/bodies, redirects, or network faults depending on the tool.
- Inspects **recorded requests** to verify method, path, headers, query, body, and call counts.
- Fits `WebClient`, Feign, Apache HttpClient, OkHttp, or other clients outside Spring `RestClient`/`RestTemplate`.

### 10.1. Sketching MockWebServer with RecordedRequest

With OkHttp MockWebServer, request verification looks like this conceptually:

~~~java
// Illustrative snippet; requires MockWebServer test dependency and imports.
// "httpClient" here is a RestClient configured to point to
// mockWebServer.url("/api").toString() instead of a production host.

mockWebServer.enqueue(new MockResponse()
        .setResponseCode(200)
        .addHeader("Content-Type", "application/json")
        .setBody("""
                 {"sku":"SKU-1","warehouse":"HCM","available":12}
                 """));

StockSnapshot stock = httpClient.fetchStock(
        "SKU-1", "HCM", false, "req-10");

RecordedRequest request = mockWebServer.takeRequest(
        2, TimeUnit.SECONDS);

assertNotNull(request);
assertEquals("GET", request.getMethod());
assertEquals(
        "/api/stocks/SKU-1?warehouse=HCM&includeReserved=false",
        request.getPath());
assertEquals("req-10", request.getHeader("X-Request-Id"));
~~~

This is a **conceptual snippet**, not part of the complete Gradle project in sections 5–6; the mock server must be started/shut down and the client dynamically injected with its base URL. Never put mock server URLs into production config. `takeRequest(timeout, unit)` returns null if no request arrives within the deadline; `assertNotNull` makes the test fail clearly instead of throwing `NullPointerException`.

With MockWebServer, the **HTTP server itself records arriving requests**. You can verify counts via recorded requests or confirm no extra requests arrive within a bounded window; for async calls, use proper synchronization rather than arbitrary sleeps. Always shut down the mock server in `try/finally` or a JUnit lifecycle hook.

### 10.2. WireMock and verifying call counts

WireMock can stub and verify request patterns conceptually as:

~~~java
wireMockServer.stubFor(
        get(urlPathEqualTo("/api/stocks/SKU-1"))
            .withQueryParam("warehouse", equalTo("HCM"))
            .willReturn(okJson(
                "{\"sku\":\"SKU-1\",\"warehouse\":\"HCM\",\"available\":12}")));

// After calling the client, verify exactly 2 requests to the endpoint.
wireMockServer.verify(
        2,
        getRequestedFor(urlPathEqualTo("/api/stocks/SKU-1"))
            .withQueryParam("warehouse", equalTo("HCM")));
~~~

This snippet requires the WireMock dependency, static imports, and the client's base URL pointed at `wireMockServer.baseUrl()`. It is not part of the main runnable Gradle example; WireMock syntax can vary across major versions. With the JUnit 5 WireMock extension, configure `randomPort`/extension lifecycle properly so parallel tests never collide on ports.

**Core principle:** Whether using `MockRestServiceServer` or a mock web server, do not just stub responses; always **verify the request contract and call count**. A stub that merely returns 200 can let tests pass even when the client sends wrong headers or queries if the stub is too broad.

## 11. Checking URI and query independent of parameter order

In an API where query parameters form an unordered set, `requestTo(fullUri)` may be overly strict. Write a custom `RequestMatcher` with a URI parsing helper:

~~~java
server.expect(request -> {
    URI uri = request.getURI();

    assertEquals("https", uri.getScheme());
    assertEquals("warehouse.example.test", uri.getHost());
    assertEquals("/api/stocks/SKU-1", uri.getPath());

    MultiValueMap<String, String> params =
            UriComponentsBuilder.fromUri(uri)
                    .build()
                    .getQueryParams();

    assertEquals(2, params.size());
    assertEquals("HCM", params.getFirst("warehouse"));
    assertEquals("false", params.getFirst("includeReserved"));
}).andExpect(method(HttpMethod.GET))
  .andRespond(withSuccess(
      "{\"sku\":\"SKU-1\",\"warehouse\":\"HCM\",\"available\":12}",
      MediaType.APPLICATION_JSON));
~~~

This snippet requires imports for `java.net.URI`, `org.springframework.util.MultiValueMap`, `org.springframework.web.util.UriComponentsBuilder`, JUnit assertions, and Spring Test matchers. It is a **custom request matcher** for projects holding a `server` variable.

**Pros:** Insensitive to the ordering of `warehouse` and `includeReserved`. **Cons:** For already-encoded URIs, the builder may retain percent-encoded values inside query params; if testing values with diacritics or spaces, decode carefully per contract/driver. Moreover, `getFirst()` only checks the first value; to forbid duplicates like `warehouse=HCM&warehouse=DN`, assert `params.get("warehouse")` is a single-element list rather than calling only `getFirst`.

To enforce **no unexpected query parameters**, assert `params.keySet()` equals the exact expected key set or check `params.size() == expectedCount`. To enforce repeated params accurately, compare the full value list. Never collapse queries into a `contains("warehouse=HCM")` string check that could accidentally match another query containing that substring.

## 12. Common testing mistakes

| Symptom | Likely cause | Fix |
|---|---|---|
| Client test calls real network | Client created with `RestClient.create()`, bypassing mock-configured builder | Inject Boot's `RestClient.Builder` or bind the exact builder |
| `@RestClientTest` fails to load client bean | Missing target class, wrong `@Component`, dependency outside slice | Use `@RestClientTest(WarehouseHttpClient.class)` and minimal `@Import` if needed |
| `MockRestServiceServer` fails to autowire | Missing `starter-test`/slice config or custom builder not recognized | Check dependencies, annotations, and Boot 3.3 auto-config |
| Expected `/path` but got `https://host/api/path` | Confused `RestClient.Builder` and `RestTemplate` `rootUri` rules | Use full URI in expectations for `RestClient` |
| URL assertion fails when query order changes | Exact expected URI is too strict | Use `queryParam`/custom matcher per contract |
| Query value containing `&` corrupts params | Concatenated user input straight into URL | `UriBuilder.queryParam`, encoding tests |
| `queryParam` passes despite extra params | Matcher only checks subset values | Exact URI or custom matcher checking all params |
| Header match fails between `Accept`/`Content-Type` | Confused the two headers | GET/response `Accept`; POST body `Content-Type` |
| JSON body looks right yet strict matcher fails | Extra field, wrong type, or array order | Check wire contract; pick strict/lenient deliberately |
| Raw JSON string matcher fails on whitespace | Using `content().string` too strictly | Use `content().json` when contract is JSON structure |
| Test gets response even though outbound call never ran | Forgot `server.verify()` or missed terminal operation | Call `.body(...)`/`.toBodilessEntity()` and verify |
| `times(2)` fails even though one request succeeded | Remaining request never happened | Issue all expected calls or fix requirement; do not drop verify |
| Extra request throws `AssertionError` | Unexpected HTTP request with no expectation | Inspect retries/interceptors/extra calls |
| Ordering test fails | Expected order differs from actual | Enforce order only when the contract requires it |
| `server.verify()` fails when another test runs first | Expectations/counters not reset | Call `server.reset()` before each test; avoid shared mutable client state |
| 404 handled wrongly | `RestClient.retrieve()` throws 4xx exceptions by default | Assert the right exception or configure `onStatus` per policy |
| Test misses misspelled JSON field | Expected body generated by the same buggy serializer | Write independent literal JSON contract expectations |
| Verify runs before async call finishes | Assertion executes before request fires | Synchronize `Future`/`Publisher`, use `verify(Duration)` appropriately |
| `MockRestServiceServer` misses network bugs | Does not open real sockets | Use MockWebServer/WireMock with real client |
| `WebClient` test tries `MockRestServiceServer` | Not a client bound by this tool | Use MockWebServer/WireMock/`ExchangeFunction` |
| Mockito `times(2)` passes while HTTP method is wrong | Verified Java collaborator instead of HTTP request | Verify at the HTTP client boundary |
| Auth tokens appear in logs | Printing raw `Authorization`/PII | Use synthetic tokens in fixtures; redact logs |
| Passes locally, fails on CI due to external API | Client configured to call live endpoint | Isolate base URL and mock transport completely |

### 12.1. Ready-to-use diagnostic sequence

1. **Identify the actual client**: `RestClient`, `RestTemplate`, `WebClient`, Feign, or Apache/OkHttp.
2. **Identify the test layer**: mock `RequestFactory` or real mock web server; do you need network behavior?
3. **Check whether the client is bound to the mock**: does its constructor accept the Spring-context builder?
4. **Declare expected URL/method independently** of client code.
5. **Declare expected headers and queries** per contract, choosing exact URI vs. semantic query matcher.
6. **For request bodies**, choose `content().json(..., true)` if field/type/array structure is fixed.
7. **Register expected counts before calling the client**; invoke `verify()` after work finishes.
8. **Test 0, 1, and multiple calls** when business logic branches, retries, or batches.
9. **Test 4xx/5xx error responses**, deserialization, and non-retry or retry policies.
10. **Run tests independently**; reset expectations and avoid JUnit method order dependencies.
11. **If real HTTP transport is needed**, move to a random-port mock web server—never call live external APIs.
12. **Confirm logs never leak secrets** or requests/responses containing PII.

## 13. Protecting tests from over-coupling to implementation details

Not every piece of request metadata is part of the contract. For an API requiring only `Accept: application/json`, do not test header ordering; for order-insensitive queries, do not enforce a full URI string if the client library can legally serialize query order differently. Conversely, for an API computing HMAC signatures over **raw path/query/body**, raw byte ordering and canonical encoding are contractual and must be tested **verbatim**.

To avoid tests that are either too weak or too brittle:
- Verify scheme/host/path explicitly when environment/routing is contractual.
- Always verify the HTTP method, as it governs semantics and idempotency.
- Verify required headers; skip incidental `User-Agent` or `Connection` headers unless required by the contract.
- For queries, verify all keys/values, repeated values, and encoding of special inputs.
- For JSON bodies, use strict mode if extra fields or wrong types are forbidden.
- For retries, verify exact attempt counts per application policy.
- For request ordering, assert order only when calls depend on one another.
- For async execution, synchronize on completion rather than sleeping arbitrarily.
- For tokens/secrets, use dummy credentials and avoid snapshotting raw `Authorization` headers in CI logs.
- For responses, always assert mapping and error handling rather than merely checking "HTTP was called."

**Never mistake `MockRestServiceServer` for a performance test.** It does not measure real TLS handshakes, DNS resolution, connection pooling, proxies, keep-alives, socket timeouts, or network latency. To test those, use a mock web server with real client transport and appropriate metrics, or a dedicated integration test.

## 14. Practice exercises

**Exercise 1 — Wrong method:** Change `fetchStock` from `.get()` to `.post()`, keeping the endpoint unchanged. Which test fails and why is checking only the URL insufficient?

**Exercise 2 — Header:** Add a required `X-Tenant-Id` using fixture `"tenant-a"`. Write a matcher checking the header and a negative test omitting it, without hardcoding production credentials.

**Exercise 3 — Query:** Add filter `locale=vi-VN` and repeated `tag=java&tag=spring`. Pick exact URI, `queryParamList`, or a custom matcher to check completeness without enforcing order across distinct keys.

**Exercise 4 — Encoding:** Send a warehouse containing spaces and Vietnamese diacritics. Test decoded query semantics or raw percent-encoding per the endpoint contract; explain why raw string concatenation is unsafe.

**Exercise 5 — Body:** Add optional `customerNote` to POST. When should you use strict JSON vs. lenient? Test that JSON number `3` differs from JSON string `"3"`.

**Exercise 6 — Zero calls:** When `quantity=0`, ensure zero requests fire; when `quantity=1`, expect exactly one POST. Do not Mockito-mock the whole client to replace wire-contract verification.

**Exercise 7 — Exactly two:** Simulate a retry policy retrying HTTP 503 once before succeeding. Define two responses (503→200) and verify exactly two requests without `Thread.sleep`.

**Exercise 8 — Unexpected request:** Intentionally invoke the client a third time when only two are expected. Observe the request factory raising an unexpected extra call error.

**Exercise 9 — Ordered calls:** Reservation logic must GET stock before POST reserve. Try reversing the order and watch the expectation order fail. If two calls are genuinely independent, propose a test design that stays order-independent.

**Exercise 10 — 404:** Instead of throwing, update the client to return `Optional.empty()` for missing stock (via `onStatus`/custom exception handling). Verify status, response policy, and exactly one outbound call.

**Exercise 11 — WebClient:** Convert `WarehouseHttpClient` to reactive `WebClient`. Why is `MockRestServiceServer` no longer a direct fit, and how do you use MockWebServer/WireMock on a random port?

**Exercise 12 — Transport:** Use OkHttp MockWebServer to inspect `RecordedRequest` path, headers, body, and network timeout. Compare what bugs it catches vs. in-process `@RestClientTest`.

**Exercise 13 — Multiple clients:** A service uses two `RestClient` builders targeting two upstream APIs. Design isolated mock server bindings and expectations for each client—never grab one `MockRestServiceServer` and assume it intercepts both.

**Exercise 14 — Security:** A client needs an OAuth bearer token. Mock the token provider or supply a dummy token; test the header is present and absent from logs. Distinguish testing the HTTP header from testing the real identity-provider token flow.

**Exercise 15 — Contract review:** Pick an external API in a real project, build a table of URL/method/headers/query/body/count/response across at least three scenarios, and decide which belong in fast slice tests vs. network integration tests.

## 15. Reference documentation

- [Spring Boot 3.3 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html): `@RestClientTest`, `RestClient.Builder`, `RestTemplateBuilder`, and full-vs-relative URI expectations.
- [Spring Framework 6.1 — Testing Client Applications](https://docs.spring.io/spring-framework/reference/testing/spring-mvc-test-client.html): `MockRestServiceServer` and comparison with HTTP-network mock web servers.
- [Spring Framework 6.1 — MockRestServiceServer API](https://docs.spring.io/spring-framework/docs/6.1.17/javadoc-api/org/springframework/test/web/client/MockRestServiceServer.html): `expect`, `verify`, `reset`, `bindTo(RestClient.Builder)`.
- [Spring Framework 6.1 — MockRestRequestMatchers API](https://docs.spring.io/spring-framework/docs/6.1.17/javadoc-api/org/springframework/test/web/client/match/MockRestRequestMatchers.html): `requestTo`, `method`, `header`, `queryParam`, `content`.
- [Spring Framework 6.1 — ContentRequestMatchers API](https://docs.spring.io/spring-framework/docs/6.1.17/javadoc-api/org/springframework/test/web/client/match/ContentRequestMatchers.html): `json(expected, strict)`, `contentTypeCompatibleWith`, `string`.
- [Spring Framework 6.1 — ExpectedCount API](https://docs.spring.io/spring-framework/docs/6.1.17/javadoc-api/org/springframework/test/web/client/ExpectedCount.html): `once`, `times`, `never`, `between`.
- [Spring Framework — REST Clients](https://docs.spring.io/spring-framework/reference/integration/rest-clients.html): `RestClient` builder, `retrieve`, `body`, `toBodilessEntity`, error handling.
- [Spring Framework 6.1 Release Notes](https://github.com/spring-projects/spring-framework/wiki/Spring-Framework-6.1-Release-Notes): Spring Test mock support for `RestClient`.
- [WireMock Documentation](https://wiremock.org/docs/): request matching, stubbing, verification, and HTTP server mocking.
- [OkHttp MockWebServer](https://square.github.io/okhttp/): recorded requests, scripted responses, and testing network clients.
- [JUnit Jupiter User Guide](https://docs.junit.org/5.11.4/user-guide/): assertions, test lifecycle, and `assertThrows`.

**Remember:** To test an HTTP client, verify **the actual request constructed by the client**: URL, method, headers, queries, body, and call counts. With **Spring Boot 3.3 + `RestClient`/`RestTemplate`**, `@RestClientTest` and `MockRestServiceServer` do this fast without opening HTTP sockets. Combine **`requestTo` + `method` + `header` + `queryParam` + `content().json` + `ExpectedCount` + `server.verify()`**, plus zero-call and 4xx/5xx cases. When real transport/network behavior matters or when using `WebClient`, switch to **WireMock/MockWebServer** and point the client to a random local port. Always derive assertions from the external API contract rather than copying a buggy implementation into expected values.
