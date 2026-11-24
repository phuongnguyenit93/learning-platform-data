# Mocking Success Responses, Invalid Data, and Error Codes in Spring Boot HTTP Client Tests

## 1. Objectives and scope

A Spring Boot application frequently calls external HTTP services to fetch products, prices, account information, or payment statuses. Testing only the "server returns 200" branch is not enough: the HTTP client must also handle **200 with invalid JSON**, **empty bodies**, **4xx/5xx**, transport failures, and rate-limited cases. A test that merely mocks a Java method—such as `when(catalog.find(...)).thenReturn(...)`—proves neither that the client builds the right URL and headers nor that it deserializes responses per contract.

This topic focuses on three groups:
1. **Valid success responses:** right HTTP status, schema-compliant headers/body, and meaningful business data.
2. **Invalid-data responses:** status may still be 200, yet JSON is malformed, missing fields, mismatched in types, nonsensical in values, or empty.
3. **Error-code responses:** 400/401/403/404/409/422/429/500/502/503/504, while distinguishing them from timeouts, DNS failures, or connection resets where no HTTP response arrived.

The lesson provides a **Java 17+, Spring Boot 3.5.x, JUnit 5** project with `RestClient` + `MockRestServiceServer` and `WebClient` + OkHttp `MockWebServer` + Reactor `StepVerifier`. It includes complete examples, test cases, and checklists, along with warnings about assumptions mock HTTP cannot prove.

### 1.1. Two independent verification layers

```text
Application calls CatalogClient
           |
           v
HTTP REQUEST CONTRACT
  GET /v1/products/{sku}
  Accept: application/json
  Right baseUrl, path, query, headers, call count?
           |
           v
HTTP RESPONSE CONTRACT
  status + Content-Type + body + error headers
           |
      +----+-----+----------------+
      |          |                |
  valid 200  200 bad body     4xx/5xx/I-O
      |          |                |
  ProductDto  explicitly reject  domain error /
                                 HTTP exception
```

**First takeaway:** `200 OK` only confirms the server sent an HTTP response with status 200; it **does not** guarantee the data is valid for business rules. Conversely, a lost connection before any response arrives must never be arbitrarily turned into a `503`—because no server confirmed that status.

## 2. Error classification must be exact

| Actual response | What the test should assert | Illustrative client outcome |
|---|---|---|
| 200 + complete JSON, valid values | Decode and validate fields | `Optional.of(ProductDto)` |
| 200 + `sku` mismatches request | Do not silently accept wrong record | `InvalidCatalogResponseException` |
| 200 + missing `name` or `id` | Do not trust primitive defaults/null | `InvalidCatalogResponseException` |
| 200 + `priceCents=-1` | Validate domain invariants | `InvalidCatalogResponseException` |
| 200 + truncated/malformed JSON | Message converter must fail | `RestClientException` or decoding exception |
| 200 + empty body | GET contract requires DTO | Data contract error |
| 204 No Content | Valid for DELETE, **invalid for GET with mandatory body** | Contract error in this example |
| 404 Not Found | Product lookup contract allows absent | `Optional.empty()` |
| 400/401/403/422 | Never lump into "not found" | Propagate or map exact HTTP error |
| 429 Too Many Requests | Check `Retry-After` and retry budget | Preserve status/header |
| 503 Service Unavailable | Transient upstream outage | Preserve status/body; separate policy |
| Socket timeout, DNS failure | No reliable HTTP status exists | Client transport exception |

The mappings in this table reflect **the design contract for this example**, not a mandatory policy for every API. For instance, 404 can be a protocol failure if an endpoint guarantees a resource always exists, while a DELETE endpoint may legitimately return 204.

### 2.1. Why not catch every exception?

Anti-pattern:

```java
try {
    return Optional.of(callUpstream());
} catch (Exception anyProblem) {
    return Optional.empty();
}
```

This is an illustrative snippet, not a standalone runnable method. It blurs `404`, `503`, malformed JSON, `401`, and timeouts into the single outcome "no data." The consequences can be severe: the app tells users a product "does not exist" when the catalog service is actually down.

The right policy usually **catches only the exception type carrying true domain meaning** (such as `HttpClientErrorException.NotFound`), letting other errors propagate or map explicitly.

## 3. Picking the right mocking tool

| Tool | Mechanism | Good for | Does not prove |
|---|---|---|---|
| Mockito mock `CatalogClient` | Bypasses HTTP layer, returns object/throws directly | Service logic consuming results | URI/headers/JSON conversion/timeouts |
| `MockRestServiceServer` | Swaps client HTTP request factory for a stub | `RestClient`/`RestTemplate` request matching, body/status branches | Real sockets/TLS/proxies |
| `@RestClientTest` | Spring Boot slice for HTTP clients | DI, properties, JSON converters, `RestClient` builder, mock requests | Whole application/real upstream |
| `MockWebServer` | Real HTTP server on random loopback port | Request/response over network stack, `WebClient`, delays/disconnects | Production server contract if fixtures are wrong |
| WireMock | HTTP stub server with mappings/scenarios/faults | Multiple endpoints, complex scenarios, retries | That real upstream did not change contract |
| Testcontainers backend | Boots real server/database | Protocol/dialect integration close to prod | Full production deployment guarantees |

`MockMvc` and `WebTestClient.bindToController` primarily test **the server/controller side** of your app. They do not test an HTTP client calling upstream. The similar library names target completely different sides of the wire.

**Pragmatic two-tier approach:** test most response scenarios with `MockRestServiceServer` for speed, and add `MockWebServer` tests where you need to verify the client network stack and reactive pipeline.

## 4. Illustrative product contract

HTTP request:

```http
GET /v1/products/SKU-101 HTTP/1.1
Accept: application/json
```

Success response:

```http
HTTP/1.1 200 OK
Content-Type: application/json

{"id":101,"sku":"SKU-101","name":"Keyboard","priceCents":250000}
```

Domain rules:
- `id > 0`.
- `sku` must match the requested SKU **exactly**.
- `name` cannot be null or blank.
- `priceCents >= 0` (free products allowed).
- 404 means the product does not exist.
- This GET **must always** return a body on success status.

This is an explicit contract; if a real product API uses `BigDecimal`, currency codes, or JSON schema versions, update DTOs/validation and tests consistently. Never use `double` for money when exact amounts are required.

## 5. Complete Java 17+ / Spring Boot 3.5 project

File structure:

```text
build.gradle
src/main/java/com/example/httpdemo/
    HttpDemoApplication.java
    ProductDto.java
    InvalidProductResponseException.java
    ProductContract.java
    CatalogClient.java
    ReactiveCatalogClient.java
src/test/java/com/example/httpdemo/
    CatalogClientMockTest.java
    CatalogClientSliceTest.java
    ReactiveCatalogClientTest.java
```

### 5.1. build.gradle

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.8'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-webflux'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
    testImplementation 'com.squareup.okhttp3:mockwebserver:4.12.0'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
```

`starter-web` provides Spring MVC, `RestClient`, and Jackson; `starter-webflux` provides `WebClient`/Reactor Netty. When both starters are present, Boot 3.x normally selects MVC as the **server-side application type**, while both HTTP clients remain usable. Here we only test the clients.

MockWebServer 4.12.0 is declared with an explicit version. Real projects should select a version vetted against their dependency tree and security policy. `MockRestServiceServer` lives in `spring-test`, brought in by `starter-test`. Neither Docker nor internet APIs are needed to run the mock tests.

### 5.2. Application class

File `src/main/java/com/example/httpdemo/HttpDemoApplication.java`:

```java
package com.example.httpdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class HttpDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(HttpDemoApplication.class, args);
    }
}
```

We do not need to run `main` to test the HTTP clients. When running the real app, supply property `catalog.base-url` (e.g., via environment variable `CATALOG_BASE_URL`); never use a production host in unit tests.

### 5.3. Separate DTO and exception

`src/main/java/com/example/httpdemo/ProductDto.java`:

```java
package com.example.httpdemo;

public record ProductDto(
        long id,
        String sku,
        String name,
        long priceCents) {
}
```

`src/main/java/com/example/httpdemo/InvalidProductResponseException.java`:

```java
package com.example.httpdemo;

public class InvalidProductResponseException
        extends RuntimeException {

    public InvalidProductResponseException(String message) {
        super(message);
    }
}
```

### 5.4. Validation after JSON parsing

`src/main/java/com/example/httpdemo/ProductContract.java`:

```java
package com.example.httpdemo;

import java.util.Objects;

public final class ProductContract {

    private ProductContract() {
    }

    public static ProductDto requireValid(
            String requestedSku, ProductDto product) {

        Objects.requireNonNull(requestedSku);

        if (product == null) {
            throw new InvalidProductResponseException(
                    "Expected response body");
        }
        if (product.id() <= 0) {
            throw new InvalidProductResponseException(
                    "Invalid product id");
        }
        if (!requestedSku.equals(product.sku())) {
            throw new InvalidProductResponseException(
                    "Response SKU differs from requested SKU");
        }
        if (product.name() == null ||
                product.name().isBlank()) {
            throw new InvalidProductResponseException(
                    "Missing or blank product name");
        }
        if (product.priceCents() < 0) {
            throw new InvalidProductResponseException(
                    "Negative price");
        }
        return product;
    }
}
```

**Key difference:** Syntactically valid JSON is not enough. Under common configurations, Jackson can deserialize a record with `name=null` or `id=0` when fields are missing. `ProductContract` enforces the business boundary whether the DTO was deserialized by `RestClient` or `WebClient`.

Do not assume every `ObjectMapper` allows missing fields: Jackson options like `FAIL_ON_MISSING_CREATOR_PROPERTIES` or strict coercion can fail decoding earlier. Test **against the application's actual `ObjectMapper`/HTTP client configuration** whenever contracts depend on those rules.

### 5.5. Real RestClient: 404 empty, other errors never swallowed

File `src/main/java/com/example/httpdemo/CatalogClient.java`:

```java
package com.example.httpdemo;

import java.util.Objects;
import java.util.Optional;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Service;
import org.springframework.web.client.HttpClientErrorException;
import org.springframework.web.client.RestClient;

@Service
public class CatalogClient {

    private final RestClient client;

    public CatalogClient(
            RestClient.Builder builder,
            @Value("${catalog.base-url}") String baseUrl) {
        this.client = builder.baseUrl(baseUrl).build();
    }

    public Optional<ProductDto> findBySku(String sku) {
        Objects.requireNonNull(sku, "sku");
        try {
            ProductDto body = client.get()
                    .uri("/v1/products/{sku}", sku)
                    .accept(MediaType.APPLICATION_JSON)
                    .retrieve()
                    .body(ProductDto.class);

            return Optional.of(
                    ProductContract.requireValid(sku, body));
        } catch (HttpClientErrorException.NotFound ex) {
            return Optional.empty();
        }
    }
}
```

When using `retrieve()`, `RestClient` raises **exceptions for 4xx/5xx** by default. Only 404 is caught and turned into `Optional.empty()`. This **does not automatically apply** to every endpoint: if a contract says 404 is an error to surface, remove that mapping.

If you switch to `RestClient.exchange(...)`, `retrieve()`'s status handlers no longer apply automatically; your exchange callback must then inspect statuses explicitly.

## 6. RestClient + MockRestServiceServer: success, bad data, and error codes

`MockRestServiceServer` binds to `RestClient.Builder` so requests from `CatalogClient` are verified like HTTP requests **without opening sockets to the internet**. It checks URI, method, headers, body, and returns test-defined responses.

### 6.1. Complete JUnit class

File `src/test/java/com/example/httpdemo/CatalogClientMockTest.java`:

```java
package com.example.httpdemo;

import java.net.SocketTimeoutException;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.test.web.client.response.ResponseCreator;
import org.springframework.web.client.HttpClientErrorException;
import org.springframework.web.client.HttpServerErrorException;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import static org.springframework.test.web.client.match.MockRestRequestMatchers.header;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.method;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withException;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withNoContent;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withStatus;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;

class CatalogClientMockTest {

    private static final String BASE =
            "https://catalog.example.test";

    private MockRestServiceServer server;
    private CatalogClient catalog;

    @BeforeEach
    void setup() {
        RestClient.Builder builder = RestClient.builder();
        server = MockRestServiceServer.bindTo(builder).build();
        catalog = new CatalogClient(builder, BASE);
    }

    @AfterEach
    void verifyRequests() {
        server.verify();
    }

    private void expect(
            String sku, ResponseCreator response) {
        server.expect(
                    requestTo(BASE + "/v1/products/" + sku))
                .andExpect(method(HttpMethod.GET))
                .andExpect(header(
                        HttpHeaders.ACCEPT,
                        MediaType.APPLICATION_JSON_VALUE))
                .andRespond(response);
    }

    @Test
    void success200DecodesExpectedData() {
        expect("SKU-101", withSuccess("""
                {"id":101,"sku":"SKU-101",
                 "name":"Keyboard","priceCents":250000}
                """, MediaType.APPLICATION_JSON));

        ProductDto product = catalog.findBySku("SKU-101")
                .orElseThrow();

        assertEquals(101, product.id());
        assertEquals("SKU-101", product.sku());
        assertEquals("Keyboard", product.name());
        assertEquals(250000, product.priceCents());
    }

    @Test
    void zeroPriceIsAcceptedIfContractAllowsIt() {
        expect("FREE", withSuccess("""
                {"id":1,"sku":"FREE",
                 "name":"Gift","priceCents":0}
                """, MediaType.APPLICATION_JSON));

        assertEquals(
                0L,
                catalog.findBySku("FREE")
                        .orElseThrow()
                        .priceCents());
    }

    @Test
    void successfulJsonWithMismatchedSkuIsRejected() {
        expect("ASKED", withSuccess("""
                {"id":2,"sku":"OTHER",
                 "name":"Wrong record","priceCents":100}
                """, MediaType.APPLICATION_JSON));

        assertThrows(
                InvalidProductResponseException.class,
                () -> catalog.findBySku("ASKED"));
    }

    @Test
    void missingNameIn200ResponseIsRejected() {
        expect("MISS", withSuccess("""
                {"id":3,"sku":"MISS","priceCents":100}
                """, MediaType.APPLICATION_JSON));

        assertThrows(
                InvalidProductResponseException.class,
                () -> catalog.findBySku("MISS"));
    }

    @Test
    void missingIdIn200ResponseIsRejected() {
        expect("ID", withSuccess("""
                {"sku":"ID","name":"Item","priceCents":100}
                """, MediaType.APPLICATION_JSON));

        assertThrows(
                InvalidProductResponseException.class,
                () -> catalog.findBySku("ID"));
    }

    @Test
    void negativePriceIn200ResponseIsRejected() {
        expect("NEG", withSuccess("""
                {"id":4,"sku":"NEG",
                 "name":"Item","priceCents":-1}
                """, MediaType.APPLICATION_JSON));

        assertThrows(
                InvalidProductResponseException.class,
                () -> catalog.findBySku("NEG"));
    }

    @Test
    void emptyBodyIsInvalidForThisGetContract() {
        expect("EMPTY",
                withSuccess("", MediaType.APPLICATION_JSON));

        assertThrows(
                InvalidProductResponseException.class,
                () -> catalog.findBySku("EMPTY"));
    }

    @Test
    void malformedJsonGivesDecodeErrorNotNotFound() {
        expect("JSON", withSuccess("""
                {"id":5,"sku":
                """, MediaType.APPLICATION_JSON));

        assertThrows(
                RestClientException.class,
                () -> catalog.findBySku("JSON"));
    }

    @Test
    void status204IsInvalidWhenGetRequiresBody() {
        expect("NOCONTENT", withNoContent());

        assertThrows(
                InvalidProductResponseException.class,
                () -> catalog.findBySku("NOCONTENT"));
    }

    @Test
    void notFound404BecomesEmptyOptional() {
        expect("ABSENT", withStatus(HttpStatus.NOT_FOUND));

        assertTrue(catalog.findBySku("ABSENT").isEmpty());
    }

    @Test
    void badRequest400IsNotMappedToEmpty() {
        expect("BAD", withStatus(HttpStatus.BAD_REQUEST));

        HttpClientErrorException.BadRequest error =
                assertThrows(
                        HttpClientErrorException.BadRequest.class,
                        () -> catalog.findBySku("BAD"));

        assertEquals(400, error.getStatusCode().value());
    }

    @Test
    void unauthorized401IsNotMappedToEmpty() {
        expect("AUTH", withStatus(HttpStatus.UNAUTHORIZED));

        HttpClientErrorException.Unauthorized error =
                assertThrows(
                        HttpClientErrorException.Unauthorized.class,
                        () -> catalog.findBySku("AUTH"));

        assertEquals(401, error.getStatusCode().value());
    }

    @Test
    void rateLimit429RetainsRetryAfter() {
        expect("RATE",
                withStatus(HttpStatus.TOO_MANY_REQUESTS)
                        .header(HttpHeaders.RETRY_AFTER, "15"));

        HttpClientErrorException.TooManyRequests error =
                assertThrows(
                        HttpClientErrorException.TooManyRequests.class,
                        () -> catalog.findBySku("RATE"));

        assertEquals(429, error.getStatusCode().value());
        assertEquals(
                "15", error.getResponseHeaders()
                        .getFirst(HttpHeaders.RETRY_AFTER));
    }

    @Test
    void serviceUnavailable503RetainsBodyAndStatus() {
        expect("DOWN",
                withStatus(HttpStatus.SERVICE_UNAVAILABLE)
                        .contentType(MediaType.APPLICATION_JSON)
                        .body("""
                                {"code":"UPSTREAM_DOWN"}
                                """));

        HttpServerErrorException.ServiceUnavailable error =
                assertThrows(
                        HttpServerErrorException.ServiceUnavailable.class,
                        () -> catalog.findBySku("DOWN"));

        assertEquals(503, error.getStatusCode().value());
        assertTrue(error.getResponseBodyAsString()
                .contains("UPSTREAM_DOWN"));
    }

    @Test
    void syntheticTransportFailureIsNotHttp503() {
        expect("IO", withException(
                new SocketTimeoutException(
                        "synthetic timeout")));

        RestClientException error = assertThrows(
                RestClientException.class,
                () -> catalog.findBySku("IO"));

        assertFalse(error instanceof HttpServerErrorException);
    }
}
```

This class contains **15 `@Test` methods**, covering valid 200, invalid-data 200, malformed JSON, empty/204, 400/401/404/429/503, and synthetic I/O errors.

**Reading test intent accurately:**

- `withSuccess(json, MediaType.APPLICATION_JSON)` supplies a JSON body **authored independently of the DTO serializer**, testing real Jackson deserialization.
- `ProductContract.requireValid` runs **after** JSON parsing. A syntactically valid payload with the wrong SKU triggers a domain error, not a syntax parser failure.
- `MockRestServiceServer.bindTo(builder)` affects only `RestClient`s built from **that builder**. If production code calls `RestClient.create()` inside a method, this mock server may miss the request.
- `server.verify()` enforces that registered expectations ran. If the client skips the request, the test fails; if it sends the wrong method/URL/header, matchers fail.
- `withException(new SocketTimeoutException(...))` fakes an I/O error at the request factory; it **does not** test real socket timeouts. Use `MockWebServer`/WireMock for real transport errors.
- The 429 test inspects `Retry-After`, yet **does not automatically retry**. Never claim `RestClient` has a default retry policy.
- `204` is an error solely because this GET contract mandates a body. For DELETE/PUT, `204` can be completely valid.

### 6.2. Why is asserting the request important?

A test configuring only:

```java
server.expect(requestTo("/v1/products/SKU-101"))
        .andRespond(withSuccess());
```

is insufficient if the app uses a full base URL and the contract requires method, `Accept` header, or authentication. For multiple calls, use `ExpectedCount.times(n)` and `content().json(...)` for POST bodies. Tests must describe **the request built by the real client**, not only the fake response.

## 7. @RestClientTest: verifying the Spring-managed client bean

The previous class built `RestClient.Builder` manually. That suits fast logic tests; to ensure **Spring Boot**'s property/DI wiring, JSON converters, and builder are right, use `@RestClientTest`.

File `src/test/java/com/example/httpdemo/CatalogClientSliceTest.java`:

```java
package com.example.httpdemo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.client.RestClientTest;
import org.springframework.http.MediaType;
import org.springframework.test.context.TestPropertySource;
import org.springframework.test.web.client.MockRestServiceServer;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;

@RestClientTest(CatalogClient.class)
@TestPropertySource(properties = {
        "catalog.base-url=https://catalog.example.test"
})
class CatalogClientSliceTest {

    @Autowired
    CatalogClient catalog;

    @Autowired
    MockRestServiceServer server;

    @Test
    void springBeanUsesConfiguredBaseUrl() {
        server.expect(requestTo(
                "https://catalog.example.test/v1/products/BOOT"))
                .andRespond(withSuccess("""
                        {"id":50,"sku":"BOOT",
                         "name":"Spring Client","priceCents":5000}
                        """, MediaType.APPLICATION_JSON));

        ProductDto p = catalog.findBySku("BOOT")
                .orElseThrow();

        assertEquals(50L, p.id());
        assertEquals("Spring Client", p.name());
        server.verify();
    }
}
```

`@RestClientTest(CatalogClient.class)` is a **client-focused test slice**; it starts no real web server and usually omits controllers, other services, datasources, and the full application. It is ideal for verifying Spring DI, `@Value`, `RestClient.Builder`, JSON message converters, and Boot customizers.

`@TestPropertySource` supplies a fake base URL; no request goes out to that domain because `MockRestServiceServer` is bound. `MockRestServiceServer` is available automatically when the test slice uses Boot's managed builder.

## 8. WebClient: mocking HTTP over real sockets

`WebClient` returns lazy `Mono`/`Flux` publishers. Calling `assertNotNull(webClient.get()...)` alone tests nothing; a **subscription** is required. `MockWebServer` is a real local HTTP server that emits statuses/headers/bodies and records incoming requests. Pairing it with `StepVerifier` verifies `onNext`, `onError`, and `onComplete` accurately.

### 8.1. ReactiveCatalogClient

File `src/main/java/com/example/httpdemo/ReactiveCatalogClient.java`:

```java
package com.example.httpdemo;

import java.util.Objects;
import java.util.Optional;

import org.springframework.http.MediaType;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.reactive.function.client.WebClientResponseException;

import reactor.core.publisher.Mono;

public class ReactiveCatalogClient {

    private final WebClient web;

    public ReactiveCatalogClient(WebClient web) {
        this.web = Objects.requireNonNull(web);
    }

    public Mono<Optional<ProductDto>> findBySku(String sku) {
        Objects.requireNonNull(sku, "sku");

        return web.get()
                .uri("/v1/products/{sku}", sku)
                .accept(MediaType.APPLICATION_JSON)
                .retrieve()
                .bodyToMono(ProductDto.class)
                .switchIfEmpty(Mono.error(
                        new InvalidProductResponseException(
                                "Expected response body")))
                .map(dto -> Optional.of(
                        ProductContract.requireValid(sku, dto)))
                .onErrorResume(
                        WebClientResponseException.NotFound.class,
                        ex -> Mono.just(
                                Optional.<ProductDto>empty()));
    }
}
```

Here `retrieve()` turns HTTP 4xx/5xx into `WebClientResponseException`; only `NotFound` recovers. Malformed JSON raises a **decode error** (distinct from HTTP status errors); an empty 200 body raises a contract error via `switchIfEmpty`. Never call `.subscribe()` inside the adapter, so caller error propagation stays intact.

### 8.2. JUnit test using MockWebServer

File `src/test/java/com/example/httpdemo/ReactiveCatalogClientTest.java`:

```java
package com.example.httpdemo;

import java.io.IOException;
import java.util.Optional;
import java.util.concurrent.TimeUnit;

import okhttp3.mockwebserver.MockResponse;
import okhttp3.mockwebserver.MockWebServer;
import okhttp3.mockwebserver.RecordedRequest;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.core.codec.DecodingException;
import org.springframework.http.MediaType;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.reactive.function.client.WebClientResponseException;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ReactiveCatalogClientTest {

    private MockWebServer server;
    private ReactiveCatalogClient catalog;

    @BeforeEach
    void start() throws IOException {
        server = new MockWebServer();
        server.start();

        String root = server.url("/").toString();
        String baseUrl = root.substring(0, root.length() - 1);

        catalog = new ReactiveCatalogClient(
                WebClient.builder().baseUrl(baseUrl).build());
    }

    @AfterEach
    void stop() throws IOException {
        server.shutdown();
    }

    private void enqueue(int status, String body) {
        server.enqueue(new MockResponse()
                .setResponseCode(status)
                .addHeader(
                        "Content-Type",
                        MediaType.APPLICATION_JSON_VALUE)
                .setBody(body));
    }

    @Test
    void success200AndRequestContract()
            throws InterruptedException {
        enqueue(200, """
                {"id":80,"sku":"WEB",
                 "name":"Web Item","priceCents":8000}
                """);

        StepVerifier.create(catalog.findBySku("WEB"))
                .assertNext(result -> {
                    ProductDto p = result.orElseThrow();
                    assertEquals(80L, p.id());
                    assertEquals("WEB", p.sku());
                })
                .verifyComplete();

        RecordedRequest request =
                server.takeRequest(2, TimeUnit.SECONDS);

        assertNotNull(request);
        assertEquals("GET", request.getMethod());
        assertEquals("/v1/products/WEB", request.getPath());
        assertEquals(
                MediaType.APPLICATION_JSON_VALUE,
                request.getHeader("Accept"));
    }

    @Test
    void successWithWrongDataSignalsDomainError() {
        enqueue(200, """
                {"id":1,"sku":"OTHER",
                 "name":"Wrong","priceCents":100}
                """);

        StepVerifier.create(catalog.findBySku("ASKED"))
                .expectError(
                        InvalidProductResponseException.class)
                .verify();
    }

    @Test
    void malformedJsonSignalsDecodingError() {
        enqueue(200, """
                {"id":99,"sku":
                """);

        StepVerifier.create(catalog.findBySku("BADJSON"))
                .expectError(DecodingException.class)
                .verify();
    }

    @Test
    void emptySuccessBodyIsRejected() {
        enqueue(200, "");

        StepVerifier.create(catalog.findBySku("EMPTY"))
                .expectError(
                        InvalidProductResponseException.class)
                .verify();
    }

    @Test
    void notFound404BecomesEmptyOptional() {
        enqueue(404, """
                {"code":"NOT_FOUND"}
                """);

        StepVerifier.create(catalog.findBySku("NONE"))
                .expectNext(Optional.empty())
                .verifyComplete();
    }

    @Test
    void serviceUnavailable503RemainsHttpError() {
        enqueue(503, """
                {"code":"UPSTREAM_UNAVAILABLE"}
                """);

        StepVerifier.create(catalog.findBySku("DOWN"))
                .expectErrorSatisfies(error -> {
                    WebClientResponseException.ServiceUnavailable ex =
                            assertInstanceOf(
                                    WebClientResponseException
                                            .ServiceUnavailable.class,
                                    error);
                    assertEquals(503, ex.getStatusCode().value());
                    assertTrue(ex.getResponseBodyAsString()
                            .contains("UPSTREAM_UNAVAILABLE"));
                })
                .verify();
    }
}
```

This class has **6 test methods**. The success test also verifies `RecordedRequest` from a real TCP server, not just the response. `takeRequest(2, TimeUnit.SECONDS)` prevents hanging forever if the client never sends a request.

When testing multiple responses or retries, `MockWebServer` serves queued replies sequentially and records requests. Creating a fresh server per test, starting on a dynamic port, and calling `shutdown()` in `@AfterEach` eliminates test order dependence.

## 9. Testing "200 with invalid data" more thoroughly

A 200 status can carry:

```json
{
  "id": 101,
  "sku": "SKU-WRONG",
  "name": "Keyboard",
  "priceCents": -100
}
```

Jackson reads every field successfully, yet **both SKU and price violate the contract**. What needs asserting is the outcome at the adapter boundary, not merely equality between `ProductDto` and an expected object.

### 9.1. Missing, null, blank, and numeric defaults

```json
{"sku":"SKU-101","priceCents":250000}
```

Because the client DTO uses `long id`, some Jackson settings default `id=0` when missing and `name=null`. That is why the suite tests `missingId` and `missingName`. If you truly want Jackson to fail immediately on missing fields, enable strict deserialization and write tests **against production's `ObjectMapper`**.

```json
{"id":101,"sku":null,"name":"Keyboard","priceCents":250000}
```

Java `ProductDto.sku()` can be null; `requestedSku.equals(product.sku())` returns false without throwing an NPE, leading to the contract error. However, if `ProductDto` adds `Objects.requireNonNull` in its constructor or Bean Validation, the failure shifts earlier. Never hardcode test exception types beyond the rules actually implemented.

### 9.2. Syntax-invalid JSON vs. type-invalid JSON

```text
{"id":101,"sku":
```

This body cannot deserialize because the JSON is truncated. Another body:

```json
{"id":"not-a-number","sku":"SKU-101","name":"A","priceCents":100}
```

fails conversion because `id` is a `long`. In both cases, decoding errors **differ** from a 404 response. When clients log failures, log an error code like `UPSTREAM_BAD_JSON` and a redacted request correlation ID—never dump raw payloads containing PII.

### 9.3. Wrong Content-Type/charset

A JSON body may arrive with `Content-Type: text/plain`, preventing the JSON converter from being selected. Tests should use responses with **real wrong headers** rather than passing strings directly into mocked methods; use `withSuccess(json, MediaType.TEXT_PLAIN)` and assert the conversion error under real client setup.

With UTF-8, Vietnamese product names should have Unicode tests to catch encoding bugs. If tests generate bodies using the client's own DTO/`ObjectMapper`, both sides can share a renamed field and still pass; use **independent JSON fixtures** or provider contract samples.

## 10. Testing HTTP statuses by semantics—never lump 4xx/5xx together

| Status | Typical meaning | Policy to test |
|---|---|---|
| `201 Created` | Resource created | `Location`/body/ID per contract |
| `202 Accepted` | Accepted for async processing | Do not treat as completed workflow |
| `204 No Content` | Success with no body | Valid for appropriate endpoints |
| `400 Bad Request` | Invalid request | Never retry infinitely |
| `401 Unauthorized` | Authentication failure | Never log tokens; bounded refresh policy |
| `403 Forbidden` | Insufficient permissions | Never convert to 404 unless contract states |
| `404 Not Found` | Missing resource/endpoint | `Optional.empty()` only per lookup contract |
| `409 Conflict` | State/version conflict | Clear domain error, check idempotency |
| `422 Unprocessable Content` | Business rule violation | Clear validation/domain error |
| `429 Too Many Requests` | Rate limit | Check `Retry-After`, retry count |
| `500 Internal Server Error` | Upstream bug | Preserve status, redacted alert/log |
| `502 Bad Gateway` | Corrupted upstream/gateway response | Distinguish from client timeout |
| `503 Service Unavailable` | Service temporarily down | Retry/circuit breaker/fallback if policy permits |
| `504 Gateway Timeout` | Gateway timed out waiting upstream | Do not conflate with client `SocketTimeoutException` |

**Note:** `Retry-After` can be integer seconds or an HTTP-date, not always an integer. Any retry policy must cap attempt counts and total elapsed time; for non-idempotent payment/order POSTs, retrying an unknown outcome can cause duplicate side effects.

A 503 test with body:

```http
HTTP/1.1 503 Service Unavailable
Content-Type: application/json
Retry-After: 15

{"code":"UPSTREAM_UNAVAILABLE"}
```

should assert status, headers if read by policy, and error codes if the client parses the body. Never assume all error bodies are JSON; reverse proxies can return HTML or empty responses.

### 10.1. Application/problem+json

When upstream follows RFC 9457, errors may use `application/problem+json`:

```json
{
  "type": "https://errors.example.test/not-allowed",
  "title": "Request rejected",
  "status": 422,
  "detail": "SKU format is not supported"
}
```

Tests must verify how the client maps problem details when that is an **agreed contract**. Never let an exception mapper swallow every error into the same generic `ProblemDetail` if callers need to distinguish authorization, validation, and upstream failures.

## 11. How does mocking network/timeout faults differ from mocking 503?

**An HTTP status** is a response from the server. In these situations, there may be **no HTTP response at all**:
- DNS name fails to resolve.
- TCP connect timeout / connection refused.
- TLS handshake failure.
- Socket reset mid-request/response.
- Read timeout before reading the complete response.
- Reactive subscriber cancels the request.

`MockRestServiceServer.withException(new SocketTimeoutException("synthetic"))` is a fast, deterministic way to test how code handles an **`IOException` from the request factory**. However, it does not test whether socket read timeouts are configured properly.

To test the real network stack, run `MockWebServer`/WireMock on a loopback port and simulate delays, dropped connections, throttled bodies, or response streaming. When testing timeouts:
- Configure explicit timeouts on the HTTP client.
- Have the server delay longer than the expected timeout.
- Assert error type and verify time stays within budget, keeping generous margins to avoid flakiness.
- Close server/client resources even when assertions fail.
- Never assume a timeout error is always equivalent to HTTP 504.

With `RestClient`, network exceptions may be `ResourceAccessException` or another `RestClientException` subtype depending on the request factory. Keep tests anchored to stable contract types if code defines no custom mapping.

## 12. Retries, backoff, circuit breakers, and call counts

A strong client test checks more than the final response; if retries exist, verify **attempt counts** and policy.

For example, "GET retries at most twice after 503" means **at most three requests**: the initial attempt plus two retries. A mock server can enqueue `503, 503, 200`; the test must confirm the caller receives data and the mock server recorded **exactly three requests**. If the retry library sits behind an AOP proxy, calling `new CatalogClient(...)` directly in tests will not activate proxy advice; policy tests must use a **Spring-managed bean** or real retry wrapper.

Aspects to test:
- Retry eligible 429/503 statuses or permitted transport errors; never retry 400/401/403.
- Cap attempt counts and total timeout budget.
- Backoff/jitter to prevent synchronized retry storms (thundering herd).
- Parse `Retry-After` properly and cap it by SLA.
- Side-effecting methods require idempotency keys and deduplication.
- When attempts are exhausted, the final error preserves status and observable context.

**There is no default retry in this lesson's `CatalogClient` code.** The 429/503 tests issue a single request. Never claim the system retries safely until you actually configure and test it.

## 13. Requests must also be verified

A response might be completely valid while the client **sent the wrong request**:
- Wrong `HttpMethod` or `/v1` path.
- Missing `Accept: application/json` or `Authorization`.
- Double-encoded query params; spaces, slashes, or `?` in path params breaking URI encoding.
- POST JSON body missing a field.
- Retries dropping `Idempotency-Key`.
- A new client bypassing Boot's builder interceptors/timeouts/tracing.

With `MockRestServiceServer`, use `requestTo(...)`, `method(...)`, `header(...)`, and `content().json(...)` for body assertions, ending with `verify()`. With `MockWebServer`, inspect `RecordedRequest` after subscription and assert actual method/path/headers/body.

When testing authorization, never log real bearer tokens in assertions. Use synthetic test tokens and verify header format/presence only as needed.

## 14. Preventing false positives in fixtures and contracts

Common test design mistakes:

**Mocking the client too high:** using `@MockBean CatalogClient` or Mockito-mocking `RestClient` internals and asserting service logic; zero real HTTP request code runs. To test the adapter, use **the real adapter + a fake server**.

**Generating response JSON from the modified DTO:** if a developer renames `priceCents` to `amount` in the DTO and the test builds its mock response via `ObjectMapper.writeValueAsString(dto)`, both client and mock silently drift away from upstream together. Use independent JSON fixtures derived from OpenAPI/provider contracts.

**Asserting only `!= null`:** a DTO with `id=0` and `sku=null` passes that check. Assert the semantic contract.

**Forgetting to verify requests:** registered mocks when the code never calls the endpoint can still return local results. Call `MockRestServiceServer.verify()` or `MockWebServer.takeRequest`.

**Testing only 200:** 404/429/503 may be mapped wrongly or trigger uncontrolled retries. Create explicit assertions for each status.

**Testing timeouts with 503:** an HTTP status error is not a TCP timeout. Inject the right kind of fault.

**Mapping all errors to empty:** hides upstream outages and corrupts business meaning.

**Unsubscribed reactive tests:** a `Mono` is just a pipeline description. Use `StepVerifier` or an appropriate subscriber.

**Test config differing from production:** `RestClient.builder()` in a unit test can differ from Boot's configured builder. When testing SSL/interceptors/codecs, use `@RestClientTest` or real integration config.

## 15. Organizing fixtures, running tests, and verifying reports

Run via Gradle wrapper on Linux/macOS:

```bash
./gradlew test --tests "com.example.httpdemo.CatalogClientMockTest"
./gradlew test --tests "com.example.httpdemo.CatalogClientSliceTest"
./gradlew test --tests "com.example.httpdemo.ReactiveCatalogClientTest"
```

Windows PowerShell:

```powershell
.\gradlew.bat test --tests "com.example.httpdemo.CatalogClientMockTest"
.\gradlew.bat test --tests "com.example.httpdemo.CatalogClientSliceTest"
.\gradlew.bat test --tests "com.example.httpdemo.ReactiveCatalogClientTest"
```

If the project uses Maven wrapper with matching dependencies:

```bash
./mvnw -Dtest=CatalogClientMockTest test
./mvnw -Dtest=CatalogClientSliceTest test
./mvnw -Dtest=ReactiveCatalogClientTest test
```

The sample project contains **15 `MockRestServiceServer` cases, 1 Spring Boot `@RestClientTest` case, and 6 `MockWebServer`/`WebClient` cases**: **22 designed test cases** in total. These are source-code/expected behaviors, **not execution proof** on the current machine.

`build.gradle` does not generate a wrapper by itself; the project needs an existing Gradle wrapper or compatible Gradle binary. With Maven, you need a matching `pom.xml` and Maven Surefire setup. Inspect `build/reports/tests/test/index.html` (Gradle) or `target/surefire-reports/` (Maven) to confirm tests actually executed rather than hitting `NO-SOURCE`, skipping, or returning cached results.

If `@RestClientTest` throws `NoSuchBeanDefinitionException`, inspect Boot's `RestClient.Builder`, the slice scope, and `catalog.base-url`. If `WebClient` tests fail with `Connection refused`, confirm the mock server called `start()` and `baseUrl` was read **after** startup—never hardcode port 8080.

## 16. QA checklist before signing off on an HTTP client

- [ ] Request contract covered: method, URL/path/query, headers, and body if present.
- [ ] Valid 200 decoded and critical fields validated.
- [ ] Includes **semantically invalid** 200s: mismatched SKU, missing/blank name, negative price.
- [ ] Includes malformed or type-mismatched JSON, distinguishing decode errors from domain invalidity.
- [ ] Includes empty-body/204 tests per endpoint contract.
- [ ] Only 404 maps to `Optional.empty()` when permitted by business logic.
- [ ] 400/401/403/409/422/429 never collapsed into a not-found fallback.
- [ ] 429 retains `Retry-After`, and 5xx retains status/body as needed.
- [ ] I/O/timeout failures are not assigned imaginary HTTP statuses.
- [ ] Fake server verifies actual requests and call counts.
- [ ] For `WebClient`, `StepVerifier` subscribes and asserts signals.
- [ ] JSON fixtures are independent of the client's DTO serializer.
- [ ] When retries exist, assert attempts, backoff, idempotency, and budget.
- [ ] Timeout/TLS/redirect behavior tested via transport-level mocks when required.
- [ ] No real tokens, PII, or public production APIs inside tests.
- [ ] Executed the proper test runner and checked JUnit reports before declaring runtime PASS.

## 17. References

- [Spring Framework 6.2 — REST Clients](https://docs.spring.io/spring-framework/reference/6.2/integration/rest-clients.html): `RestClient`, `retrieve`, status handlers, and message conversion.
- [Spring Framework — Testing Client Applications](https://docs.spring.io/spring-framework/reference/testing/spring-mvc-test-client.html): `MockRestServiceServer`, request matchers, response creators, and `verify`.
- [Spring Framework — MockRestResponseCreators Javadoc](https://docs.spring.io/spring-framework/docs/6.2.11/javadoc-api/org/springframework/test/web/client/response/MockRestResponseCreators.html): `withSuccess`, `withStatus`, `withException`, `withNoContent`.
- [Spring Framework — Testing WebClient](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-testing.html): using `MockWebServer`/WireMock.
- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): `@RestClientTest` and client test setup.
- [OkHttp MockWebServer](https://github.com/square/okhttp/tree/master/mockwebserver): HTTP mock server and recorded requests.
- [Project Reactor — Testing](https://projectreactor.io/docs/core/release/reference/testing.html): `StepVerifier`.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110): HTTP status and method semantics.
- [RFC 9457 — Problem Details](https://www.rfc-editor.org/rfc/rfc9457): `application/problem+json` error bodies.

**Conclusion:** Effective HTTP client mocking does not stop at returning 200 JSON. You must test the **request contract**, parse and validate data, and cleanly separate **200 with invalid body**, **4xx/5xx**, and **transport failures**, alongside retry/fallback policies where configured. `MockRestServiceServer`/`@RestClientTest` excels for fast, accurate `RestClient` tests; `MockWebServer`/`StepVerifier` extends verification to `WebClient` over real HTTP sockets. A test is only trustworthy when it sends contract-compliant requests and proves the right outcome for every failure mode.
