# @RestClientTest and Importing Client Configuration into the Slice

## 1. What does this lesson focus on?

A Spring Boot application may call external APIs to fetch products, check inventory, send emails, calculate shipping, or look up exchange rates. The application's HTTP client must build the right **URL, HTTP method, headers, and JSON**, while also handling 200, 204, 400, 404, 429, 503 responses and decoding errors per the contract. If you use Mockito to mock the HTTP client class itself, service-level tests will fail to catch wrong paths, forgotten API keys, misspelled JSON fields, or 404s mistaken for valid responses.

Spring Boot **3.3.5** provides **`@RestClientTest`**, a test slice tailored for **outbound REST clients**. It auto-configures JSON infrastructure (Jackson/Gson/Jsonb), `RestTemplateBuilder`, `RestClient.Builder`, and `MockRestServiceServer`; however, it **does not automatically scan all regular `@Component` and `@ConfigurationProperties` beans** like a full application context.

This lesson belongs to the **HTTP Client and Mocking** group and tackles **"@RestClientTest and importing client configuration into the slice"**:

1. Select the exact client adapter with `@RestClientTest(TargetClass.class)`.
2. Bring **production client configuration** into the slice via `@Import`, rather than rewriting a separate client just for tests.
3. Register typed properties via `@EnableConfigurationProperties` and supply test-only configuration values.
4. Use Spring Boot's auto-configured `RestClient.Builder` so the mock server intercepts HTTP calls.
5. Verify absolute URLs, request headers, JSON bodies, response mapping, and HTTP errors using `MockRestServiceServer`.
6. Distinguish `RestClient.Builder` from `RestTemplateBuilder.rootUri` regarding how expected request URIs are specified.
7. Understand the limits: the mock server **does not open a TCP socket**, so it does not verify DNS/TLS/connection timeouts or real network proxies.

Language: **Java 17+**. The sample project uses **Spring Boot 3.3.5**, **Spring Framework 6.1**, Gradle/JUnit Jupiter, and requires no network connection to a partner API during tests.

## 2. Architecture of the test slice

```text
JUnit Jupiter
    |
    +-- @RestClientTest(PartnerProductGateway.class)
           |
           +-- PartnerProductGateway (explicitly selected @Component)
           |
           +-- @Import(PartnerRestClientConfiguration.class)
           |       |
           |       +-- @EnableConfigurationProperties
           |       |       PartnerClientProperties
           |       |
           |       +-- @Bean("partnerRestClient")
           |               Boot's RestClient.Builder
           |               baseUrl + default headers
           |
           +-- MockRestServiceServer
                   |
                   +-- expected URI / method / headers / body
                   +-- returns configured JSON or HTTP error
```

`PartnerProductGateway` and `PartnerRestClientConfiguration` are **real application code**. Response data and the "server" are controlled by the test. When the Gateway calls `RestClient.retrieve().body(...)`, Spring routes the request through the mock request factory and hands the response to the HTTP message converter. No DNS lookup to `api.partner.test` happens in a passing test.

### How does it differ from @WebMvcTest?

| Option | HTTP direction | Test target | Tool |
| --- | --- | --- | --- |
| `@RestClientTest` | **Outbound**: app calls another service | REST client/adapter | `MockRestServiceServer` |
| `@WebMvcTest` | **Inbound**: client calls controller | Spring MVC controller | `MockMvc` |
| `@SpringBootTest` | Multi-layer application | Broad wiring/integration | Can pair with mock server |
| JUnit + Mockito | No real HTTP needed | Logic calling dependency | Mockito mocks |
| WireMock/MockWebServer | Outbound over local TCP | HTTP network boundary | Real local server |
| Contract tests | Producer ↔ consumer | API schema/compatibility | Provider/consumer verification |

Do not use `@WebMvcTest` with `MockMvc` to verify an outbound client: that is the opposite HTTP direction. Likewise, do not put `@MockBean` on the Gateway itself inside `@RestClientTest`, because then the real HTTP client never executes and the mock server receives no request.

## 3. Which beans does @RestClientTest provide automatically?

In Spring Boot 3.3, `@RestClientTest` enables a focused set of auto-configurations:

- `RestClient.Builder` for Spring Framework 6.1's blocking `RestClient`.
- `RestTemplateBuilder` for blocking `RestTemplate`.
- JSON/message converters matching the classpath.
- `MockRestServiceServer` bound to the managed builders.
- Spring TestContext and JUnit Jupiter integration.

It **does not automatically load every `@Service`, `@Component`, `@Repository`, `@ConfigurationProperties`, DataSource, or controller**. You must specify the class under test with `value`/`components`, then import only the dependencies truly needed.

For example:

```java
@RestClientTest(PartnerProductGateway.class)
@Import(PartnerRestClientConfiguration.class)
class PartnerProductGatewayTest {
}
```

If you only add `@RestClientTest` without selecting the adapter, a regular bean like `PartnerProductGateway` may not appear. If you select the adapter without importing the configuration that builds `RestClient`, the test may fail during bean creation due to a missing dependency.

### @Import and @ImportAutoConfiguration

- `@Import(MyConfiguration.class)`: adds an ordinary `@Configuration` or specific bean into the test context; ideal for application client configs.
- `@EnableConfigurationProperties(MyProperties.class)`: registers typed properties bound into beans; can be placed on the imported config.
- `@ImportAutoConfiguration(...)`: for **Spring Boot auto-configuration** classes needed in the slice; do not import auto-config classes indiscriminately using ordinary `@Import`.
- `@TestConfiguration`: used when you need a test-specific collaborator/config; do not replace the whole production client config if the goal is to test that config itself.

Importing configuration into the slice is deliberate—**not enabling component scanning for the entire application** just to dodge missing-bean errors.

## 4. RestClient, RestTemplate, and WebClient

| API | Characteristics | Testing |
| --- | --- | --- |
| `RestClient` | Blocking, fluent, introduced in Spring Framework 6.1 | `@RestClientTest` with `RestClient.Builder` |
| `RestTemplate` | Blocking, legacy API | `@RestClientTest` with `RestTemplateBuilder` |
| `WebClient` | Reactive, `Mono`/`Flux` | Strategy for reactive `WebClient`, not treated as `RestClient` by default |
| Declarative HTTP interface | Proxy delegating via `RestClient`/`WebClient` adapter | Requires configuring the proxy and appropriate underlying client |

In the main example, production config creates **a `RestClient` bean** using the auto-managed `RestClient.Builder`, and the adapter injects that `RestClient`. This helps when clients have distinct base URLs/API keys and an app has multiple outbound clients.

**Avoid `RestClient.create()` in the bean under test** when relying on slice auto-mocking: a client created via standalone factory may bypass Boot customizers or `MockRestServiceServer`. Use the managed builder or explicit mock binding as designed.

## 5. Full Java 17+ / Spring Boot 3.3.5 project

Structure:

```text
rest-client-slice/
├── settings.gradle
├── build.gradle
├── src/main/java/com/example/outbound/
│   ├── OutboundApplication.java
│   ├── PartnerClientProperties.java
│   ├── PartnerRestClientConfiguration.java
│   ├── PartnerItem.java
│   ├── CreateItemRequest.java
│   ├── PartnerProductGateway.java
│   └── LegacyHealthClient.java
└── src/test/java/com/example/outbound/
    ├── PartnerProductGatewayTest.java
    └── LegacyHealthClientTest.java
```

The project needs no controller, database, Docker, or real API key.

### settings.gradle

```groovy
rootProject.name = 'rest-client-slice'
```

### build.gradle

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
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
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()
    testLogging {
        events 'passed', 'failed', 'skipped'
    }
}
```

`spring-boot-starter-web` provides Spring Web, `RestClient`/`RestTemplate`, and Jackson. `spring-boot-starter-test` includes JUnit Jupiter, Spring Test, `MockRestServiceServer`, and Spring Boot test auto-configurations. You do not need to run `bootRun` to execute client slice tests; the `@SpringBootApplication` class only serves as the application root.

If the project lacks a Gradle Wrapper yet, use an installed compatible Gradle or generate the Wrapper before running `./gradlew`. Do not confuse a "missing gradlew file" with a unit test error.

### OutboundApplication.java

`src/main/java/com/example/outbound/OutboundApplication.java`:

```java
package com.example.outbound;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OutboundApplication {
    public static void main(String[] args) {
        SpringApplication.run(OutboundApplication.class, args);
    }
}
```

Root application package `com.example.outbound` is the parent package of the adapter, config, and tests. When running the **full application** outside tests, real client properties must come from the environment/secret manager; the demo supplies test-only values inside `@RestClientTest(properties=...)`.

## 6. Typed configuration: @ConfigurationProperties record

`src/main/java/com/example/outbound/PartnerClientProperties.java`:

```java
package com.example.outbound;

import java.net.URI;
import java.util.Objects;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "partner.catalog")
public record PartnerClientProperties(
        URI baseUrl,
        String apiKey
) {

    public PartnerClientProperties {
        Objects.requireNonNull(baseUrl, "baseUrl is required");

        if (!"https".equalsIgnoreCase(baseUrl.getScheme())) {
            throw new IllegalArgumentException(
                    "partner.catalog.base-url must be https");
        }

        if (apiKey == null || apiKey.isBlank()) {
            throw new IllegalArgumentException(
                    "partner.catalog.api-key is required");
        }
    }
}
```

Because this is a Java 17 record with one canonical constructor, Spring Boot 3.3 uses constructor binding naturally. `partner.catalog.base-url` is relaxed-bound to `baseUrl`, and `partner.catalog.api-key` to `apiKey`.

**Never hardcode real secrets.** Tests only use `test-key`, a synthetic string. Production should use a secret manager or environment properties—never commit API keys to Git or emit them in test logs.

### Why is this type not scanned automatically?

A `@ConfigurationProperties` class is not a `@Component` by default in a test slice. Production typically uses `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties`; the slice likewise needs a clear registration mechanism. The project puts `@EnableConfigurationProperties(PartnerClientProperties.class)` on the imported config, avoiding broad scanning.

The HTTPS rule in the compact constructor is only this example's policy. If a test environment uses real localhost HTTP, design the policy/endpoint cleanly rather than disabling TLS validation in production just to let tests run.

## 7. Real configuration: building the client from Boot RestClient.Builder

`src/main/java/com/example/outbound/PartnerRestClientConfiguration.java`:

```java
package com.example.outbound;

import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(PartnerClientProperties.class)
public class PartnerRestClientConfiguration {

    @Bean("partnerRestClient")
    RestClient partnerRestClient(
            RestClient.Builder builder,
            PartnerClientProperties properties) {

        return builder
                .baseUrl(properties.baseUrl().toString())
                .defaultHeader(
                        "X-Partner-Key", properties.apiKey())
                .defaultHeader(
                        "X-Client-Tag", "catalog-gateway")
                .build();
    }
}
```

This is **production source configuration**. In tests, `@Import(PartnerRestClientConfiguration.class)` brings this exact configuration into the slice. Since `RestClient.Builder` is provided by Boot and customized by mock integration, the expectation server can intercept requests.

Key points:

- `@Bean("partnerRestClient")`: explicit bean name prevents injecting the wrong client when multiple `RestClient` beans exist.
- `baseUrl(...)`: reads the endpoint from the configuration record instead of hardcoding it in the Gateway.
- `defaultHeader("X-Partner-Key", ...)`: attaches the test API key; production must safeguard the secret.
- `defaultHeader("X-Client-Tag", ...)`: adds an adapter header, acting as a check that the config was imported.
- `@EnableConfigurationProperties`: ensures the properties type is present in the slice.

**Do not instantiate `new RestClient` or `RestClient.create()` here.** Bypassing the Boot-managed builder may prevent the mock server from binding to the request factory, causing tests to accidentally call the external network.

### Verifying configuration through behavior

Merely asserting that `PartnerClientProperties.apiKey()` holds a value **is not enough**: the client might fail to put the property onto the request. The main tests assert **`X-Partner-Key` and `X-Client-Tag` in the HTTP request** along with the absolute URL from `baseUrl`. That is real proof the client configuration took effect.

## 8. Request/response DTOs

`src/main/java/com/example/outbound/PartnerItem.java`:

```java
package com.example.outbound;

public record PartnerItem(
        String sku,
        String name,
        int priceCents
) {
}
```

`src/main/java/com/example/outbound/CreateItemRequest.java`:

```java
package com.example.outbound;

public record CreateItemRequest(
        String sku,
        String name,
        int priceCents
) {
}
```

Jackson in Boot 3.3 reads and writes Java records with these fields. `priceCents` uses integer minor units to avoid floating-point precision issues. Records do not automatically validate nulls or negative prices; for a real product contract, add Bean Validation, constructor invariants, and negative contract tests.

## 9. Real client adapter: PartnerProductGateway

`src/main/java/com/example/outbound/PartnerProductGateway.java`:

```java
package com.example.outbound;

import java.util.Objects;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

@Component
public class PartnerProductGateway {

    private final RestClient client;

    public PartnerProductGateway(
            @Qualifier("partnerRestClient") RestClient client) {
        this.client = client;
    }

    public PartnerItem findBySku(String sku) {
        if (sku == null || sku.isBlank()) {
            throw new IllegalArgumentException("sku is required");
        }

        PartnerItem response = client.get()
                .uri("/v1/items/{sku}", sku)
                .accept(MediaType.APPLICATION_JSON)
                .retrieve()
                .body(PartnerItem.class);

        if (response == null) {
            throw new IllegalStateException(
                    "partner returned empty item body");
        }
        return response;
    }

    public PartnerItem create(CreateItemRequest request) {
        Objects.requireNonNull(request, "request");

        PartnerItem response = client.post()
                .uri("/v1/items")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_JSON)
                .body(request)
                .retrieve()
                .body(PartnerItem.class);

        if (response == null) {
            throw new IllegalStateException(
                    "partner returned empty create body");
        }
        return response;
    }
}
```

`@Component` enables component scanning in the full application; `@RestClientTest(PartnerProductGateway.class)` explicitly selects this bean in the slice. The adapter has no literal URLs or credentials; all HTTP config arrives through the injected named `RestClient` bean.

### GET behavior

- Validates SKU to reject bad requests before HTTP.
- Builds GET `/v1/items/{sku}` using a URI template.
- Sends `Accept: application/json`.
- Spring automatically applies default headers and base URL from the bean.
- Deserializes JSON into `PartnerItem`.
- On `204 No Content`, `body(...)` may return null; the adapter throws a clear error.
- On HTTP 4xx/5xx, `retrieve()` throws HTTP client/server exceptions by default.

### POST behavior

- Rejects null requests with `Objects.requireNonNull`.
- Sends POST `/v1/items` with the JSON body of `CreateItemRequest`.
- Sets both `Content-Type` and `Accept` to JSON.
- Deserializes the response JSON.
- Verifies the response body is non-null.

A URI template is used instead of raw string concatenation on user-controlled paths. For inputs containing slashes, spaces, or Unicode, add encoding tests per contract and framework version; the example focuses on clean ASCII SKUs.

## 10. The @RestClientTest suite with @Import and MockRestServiceServer

Create `src/test/java/com/example/outbound/PartnerProductGatewayTest.java`:

```java
package com.example.outbound;

import java.net.URI;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.autoconfigure.web.client.RestClientTest;
import org.springframework.context.annotation.Import;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.HttpClientErrorException;
import org.springframework.web.client.HttpServerErrorException;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;

import static org.springframework.test.web.client.match.MockRestRequestMatchers.content;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.header;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.method;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;

import static org.springframework.test.web.client.response.MockRestResponseCreators.withNoContent;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withStatus;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;

@RestClientTest(
        value = PartnerProductGateway.class,
        properties = {
            "partner.catalog.base-url=https://api.partner.test",
            "partner.catalog.api-key=test-key"
        })
@Import(PartnerRestClientConfiguration.class)
class PartnerProductGatewayTest {

    @Autowired
    PartnerProductGateway gateway;

    @Autowired
    PartnerClientProperties properties;

    @Autowired
    @Qualifier("partnerRestClient")
    RestClient configuredClient;

    @Autowired
    MockRestServiceServer server;

    @BeforeEach
    void resetExpectations() {
        server.reset();
    }

    @Test
    void clientConfigurationIsLoadedIntoSlice() {
        assertNotNull(gateway);
        assertNotNull(configuredClient);
        assertEquals(
                URI.create("https://api.partner.test"),
                properties.baseUrl());
        assertEquals("test-key", properties.apiKey());
    }

    @Test
    void getUsesAbsoluteUriHeadersAndJson() {
        server.expect(requestTo(
                        "https://api.partner.test/v1/items/SKU-1"))
                .andExpect(method(HttpMethod.GET))
                .andExpect(header(
                        "X-Partner-Key", "test-key"))
                .andExpect(header(
                        "X-Client-Tag", "catalog-gateway"))
                .andExpect(header(
                        HttpHeaders.ACCEPT,
                        MediaType.APPLICATION_JSON_VALUE))
                .andRespond(withSuccess("""
                    {
                      "sku": "SKU-1",
                      "name": "Keyboard",
                      "priceCents": 4999
                    }
                    """, MediaType.APPLICATION_JSON));

        PartnerItem result = gateway.findBySku("SKU-1");
        assertEquals(
                new PartnerItem("SKU-1", "Keyboard", 4999),
                result);
        server.verify();
    }

    @Test
    void postSerializesRequestAndReadsResponse() {
        server.expect(requestTo(
                        "https://api.partner.test/v1/items"))
                .andExpect(method(HttpMethod.POST))
                .andExpect(header(
                        "X-Partner-Key", "test-key"))
                .andExpect(header(
                        "X-Client-Tag", "catalog-gateway"))
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON))
                .andExpect(content().json("""
                    {
                      "sku": "SKU-2",
                      "name": "Monitor",
                      "priceCents": 12900
                    }
                    """, true))
                .andRespond(withSuccess("""
                    {
                      "sku": "SKU-2",
                      "name": "Monitor",
                      "priceCents": 12900
                    }
                    """, MediaType.APPLICATION_JSON));

        PartnerItem result = gateway.create(
                new CreateItemRequest(
                        "SKU-2", "Monitor", 12900));

        assertEquals(
                new PartnerItem("SKU-2", "Monitor", 12900),
                result);
        server.verify();
    }

    @Test
    void response404IsHttpClientError() {
        server.expect(requestTo(
                        "https://api.partner.test/v1/items/MISSING"))
                .andRespond(withStatus(HttpStatus.NOT_FOUND));

        HttpClientErrorException.NotFound error =
                assertThrows(
                    HttpClientErrorException.NotFound.class,
                    () -> gateway.findBySku("MISSING"));

        assertEquals(HttpStatus.NOT_FOUND,
                error.getStatusCode());
        server.verify();
    }

    @Test
    void response503IsHttpServerError() {
        server.expect(requestTo(
                        "https://api.partner.test/v1/items/SKU-3"))
                .andRespond(withStatus(
                        HttpStatus.SERVICE_UNAVAILABLE));

        HttpServerErrorException.ServiceUnavailable error =
                assertThrows(
                    HttpServerErrorException
                        .ServiceUnavailable.class,
                    () -> gateway.findBySku("SKU-3"));

        assertEquals(HttpStatus.SERVICE_UNAVAILABLE,
                error.getStatusCode());
        server.verify();
    }

    @Test
    void invalidSkuDoesNotCauseHttpRequest() {
        assertThrows(
                IllegalArgumentException.class,
                () -> gateway.findBySku("  "));
        server.verify();
    }

    @Test
    void nullCreateRequestFailsBeforeSending() {
        assertThrows(
                NullPointerException.class,
                () -> gateway.create(null));
        server.verify();
    }

    @Test
    void empty204ResponseIsRejected() {
        server.expect(requestTo(
                        "https://api.partner.test/v1/items/SKU-4"))
                .andRespond(withNoContent());

        IllegalStateException error = assertThrows(
                IllegalStateException.class,
                () -> gateway.findBySku("SKU-4"));

        assertEquals(
                "partner returned empty item body",
                error.getMessage());
        server.verify();
    }

    @Test
    void malformedJsonIsDecodingFailure() {
        server.expect(requestTo(
                        "https://api.partner.test/v1/items/BROKEN"))
                .andRespond(withSuccess(
                        "{\"sku\":",
                        MediaType.APPLICATION_JSON));

        assertThrows(
                RestClientException.class,
                () -> gateway.findBySku("BROKEN"));
        server.verify();
    }

    @Test
    void unprocessablePostRetains422Status() {
        server.expect(requestTo(
                        "https://api.partner.test/v1/items"))
                .andRespond(withStatus(
                        HttpStatus.UNPROCESSABLE_ENTITY));

        HttpClientErrorException error = assertThrows(
                HttpClientErrorException.class,
                () -> gateway.create(
                    new CreateItemRequest(
                            "SKU-5", "Invalid", 0)));

        assertEquals(HttpStatus.UNPROCESSABLE_ENTITY,
                error.getStatusCode());
        server.verify();
    }

    @Test
    void textPlainResponseCannotMapJsonDto() {
        server.expect(requestTo(
                        "https://api.partner.test/v1/items/SKU-6"))
                .andRespond(withSuccess(
                        "not json",
                        MediaType.TEXT_PLAIN));

        assertThrows(
                RestClientException.class,
                () -> gateway.findBySku("SKU-6"));
        server.verify();
    }

    @Test
    void twoSequentialCallsReadDifferentBodies() {
        server.expect(requestTo(
                        "https://api.partner.test/v1/items/SKU-A"))
                .andRespond(withSuccess("""
                    {
                      "sku": "SKU-A",
                      "name": "Alpha",
                      "priceCents": 100
                    }
                    """, MediaType.APPLICATION_JSON));

        server.expect(requestTo(
                        "https://api.partner.test/v1/items/SKU-B"))
                .andRespond(withSuccess("""
                    {
                      "sku": "SKU-B",
                      "name": "Beta",
                      "priceCents": 200
                    }
                    """, MediaType.APPLICATION_JSON));

        assertEquals(
                new PartnerItem("SKU-A", "Alpha", 100),
                gateway.findBySku("SKU-A"));
        assertEquals(
                new PartnerItem("SKU-B", "Beta", 200),
                gateway.findBySku("SKU-B"));

        server.verify();
    }
}
```

**There are 12 `@Test` methods** in this class. `@BeforeEach` is not a test; it only resets mock expectations before each method.

### Which test proves the configuration was imported?

`clientConfigurationIsLoadedIntoSlice` asserts that the properties bean and named `RestClient` bean exist. However, `getUsesAbsoluteUriHeadersAndJson` and `postSerializesRequestAndReadsResponse` are stronger: they confirm the configuration **affected the HTTP request** via the base URL and two headers.

If a developer accidentally removes `@Import`, the `partnerRestClient` bean disappears. If `@EnableConfigurationProperties` is removed from the config, `PartnerClientProperties` disappears. If the Gateway creates its own client via `RestClient.create()`, the mock server may fail to intercept.

## 11. Main assertion groups

### 11.1. URL and HTTP method

Spring `RestClient` constructs the absolute URL from `baseUrl("https://api.partner.test")` plus path `/v1/items/SKU-1`. With `RestClient.Builder` in Spring Boot 3.3, `MockRestServiceServer` expectations must use the **full URI**, for example:

```java
server.expect(requestTo(
        "https://api.partner.test/v1/items/SKU-1"))
      .andExpect(method(HttpMethod.GET));
```

Asserting only the response DTO while skipping URL/method does not guard against calling the wrong endpoint or sending POST instead of GET.

### 11.2. Headers

The GET test asserts `X-Partner-Key`, `X-Client-Tag`, and `Accept: application/json`; the POST test asserts the API key/tag and `Content-Type: application/json`. `Content-Type` primarily applies to requests with a body; GET does not need a JSON content-type just for appearances.

### 11.3. JSON body

`content().json(expected, true)` compares JSON structure. Whitespace and property order need not match literally, while strict mode restricts extra fields beyond expected per comparison semantics. These literal fixtures protect the API contract rather than letting the serializer and deserializer merely round-trip with each other.

### 11.4. Response mapping

Jackson reads the JSON string into Java record `PartnerItem`. The test checks every field (`sku`, `name`, `priceCents`), not just `assertNotNull`. A test that only checks no exception was thrown can miss a missing price mapping.

### 11.5. Negative HTTP statuses

`RestClient.retrieve()` throws errors for HTTP 4xx/5xx by default. Tests check 404 with `HttpClientErrorException.NotFound`, 503 with `HttpServerErrorException.ServiceUnavailable`, and POST 422 with `HttpClientErrorException` and the exact status. If the app uses custom `onStatus(...)`, expected exceptions must reflect the actual domain mapping.

### 11.6. Empty and malformed bodies

`withNoContent()` returns 204, so `body(PartnerItem.class)` can be null; the Gateway throws `IllegalStateException` with a clear message. A malformed JSON response triggers `RestClientException`/converter failure. Choose an assertion type specific enough for the contract; avoid `assertThrows(RuntimeException.class)` since an unexpected `NullPointerException` could make the test pass falsely.

### 11.7. Multiple requests and server.verify()

Each `expect` registers an expected request. After the client runs, `server.verify()` confirms all expected requests were satisfied. `server.reset()` in `@BeforeEach` clears state from the previous method so tests do not depend on JUnit execution order.

When a client makes concurrent requests, ordering semantics require the appropriate manager. The example makes two sequential GETs in declared order, so the default request expectation manager is appropriate.

## 12. Legacy RestTemplateBuilder.rootUri: an important difference

Spring Boot 3.3 docs note that when using `RestTemplateBuilder.rootUri(String)`, mock server expectations may **omit the root URI** and use only the relative path. This behavior is easily confused with `RestClient.Builder`.

### LegacyHealthClient.java

`src/main/java/com/example/outbound/LegacyHealthClient.java`:

```java
package com.example.outbound;

import org.springframework.boot.web.client.RestTemplateBuilder;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestTemplate;

@Component
public class LegacyHealthClient {

    private final RestTemplate template;

    public LegacyHealthClient(RestTemplateBuilder builder) {
        this.template = builder
                .rootUri("https://legacy.partner.test")
                .build();
    }

    public String ping() {
        return template.getForObject(
                "/health", String.class);
    }
}
```

### LegacyHealthClientTest.java

`src/test/java/com/example/outbound/LegacyHealthClientTest.java`:

```java
package com.example.outbound;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.client.RestClientTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.client.MockRestServiceServer;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;

@RestClientTest(LegacyHealthClient.class)
class LegacyHealthClientTest {

    @Autowired
    LegacyHealthClient client;

    @Autowired
    MockRestServiceServer server;

    @Test
    void rootUriIsOmittedFromRequestExpectation() {
        server.expect(requestTo("/health"))
                .andRespond(withSuccess(
                        "ok", MediaType.TEXT_PLAIN));

        assertEquals("ok", client.ping());
        server.verify();
    }
}
```

**There is 1 `@Test`** in the legacy class; total for the project is **13 `@Test` methods** (12 + 1).

### URI expectation comparison table

| Client | Setup | MockRestServiceServer expectation on Boot 3.3 |
| --- | --- | --- |
| `RestClient.Builder` | `baseUrl("https://api.partner.test")` | Full URL: `https://api.partner.test/v1/items/SKU-1` |
| `RestTemplateBuilder` | `rootUri("https://legacy.partner.test")` | Relative: `/health` |
| `RestTemplateBuilder` without `rootUri` | Calls absolute URI | Full URL |
| HTTP client creating its own request factory outside Boot's builder | Implementation-dependent | Requires separate mock binding or real HTTP server |

Do not blindly convert expectations from `RestTemplate` to `RestClient` without checking versioned documentation. `rootUri` is also a different API from `RestClient`'s `baseUrl`: same base-domain idea, different test binding path behavior.

## 13. How is @ConfigurationProperties brought into the slice?

The project uses:

```java
@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(PartnerClientProperties.class)
public class PartnerRestClientConfiguration {
    // @Bean partnerRestClient(...)
}
```

The test uses:

```java
@RestClientTest(
    value = PartnerProductGateway.class,
    properties = {
        "partner.catalog.base-url=https://api.partner.test",
        "partner.catalog.api-key=test-key"
    })
@Import(PartnerRestClientConfiguration.class)
class PartnerProductGatewayTest {
}
```

Here are the three responsibilities:

1. `properties` provides **values** from Spring Environment.
2. `@EnableConfigurationProperties` registers the **typed bean** and binds it from Environment.
3. `@Import` brings the configuration that builds the **real `RestClient` bean** into the test slice.

If you only set test properties without enabling/binding the type, classes depending on `PartnerClientProperties` will still miss the bean. If you enable the type but forget the config creating `RestClient`, the Gateway will miss its dependency as well. Startup test failures here signal incomplete wiring, not a DNS issue.

### What if the app uses @ConfigurationPropertiesScan?

A production application may place `@ConfigurationPropertiesScan` on its main configuration to discover property types. `@RestClientTest` intentionally restricts scanning; the stable choice is importing the config and enabling the specific properties explicitly. Do not load the entire application config just to bind two test property values.

## 14. @Import vs @TestConfiguration

**`@Import` production config** is appropriate when you want to verify the exact config that ships: base URL binding, default headers, client builder, and codecs.

**`@TestConfiguration`** fits when you need a test-only collaborator:

```java
@TestConfiguration(proxyBeanMethods = false)
class TestOnlyClientFlagsConfig {

    @Bean
    ClientFlags clientFlags() {
        return new ClientFlags(false);
    }
}
```

This is an architectural snippet outside the runnable project: `ClientFlags` is a hypothetical type from another app and must be defined first. If a service in the slice truly needs flags, you can import a test config or mock the collaborator. Just never replace all of `PartnerRestClientConfiguration` with fake config and claim production headers were verified.

### When to use @ImportAutoConfiguration?

If you need to enable an additional Spring Boot auto-configuration class not included in the slice, use `@ImportAutoConfiguration` per Boot guidelines. Ordinary production `@Configuration` like `PartnerRestClientConfiguration` is a case for regular `@Import`. Never "import every auto-config" because it bloats the context and easily causes bean collisions.

## 15. Multi-client contexts need deliberate server binding

The main example creates only one `RestClient` bean and one Boot-provided builder. When an app has multiple outbound clients:

- A `RestClient.Builder` may be cloned or customized differently.
- `MockServerRestClientCustomizer` can maintain mock servers bound to each builder.
- A single auto-injected `MockRestServiceServer` may represent only one builder.
- One test class per outbound adapter is usually easier to control.
- If multiple adapters must run inside the same integration test, retrieve each builder's server via the customizer and set expectations independently, or use WireMock for host-specific routing.

Never assume one injected mock server intercepts **every HTTP client in the JVM**; it only intercepts clients properly built and bound.

### RestClientCustomizer and global configuration

Spring Boot provides `org.springframework.boot.web.client.RestClientCustomizer` to customize Boot-managed builders. Example snippet:

```java
@Bean
RestClientCustomizer addApplicationHeader() {
    return builder ->
            builder.defaultHeader(
                    "X-App-Version", "1");
}
```

This is a snippet outside the runnable project, requiring `Bean` and `RestClientCustomizer` imports. If production has a real customizer, tests must import the config providing that customizer and assert the request. However, never put a partner's API key into a **global customizer** or other clients might accidentally send the same credential.

**Specifically:** a customizer that sets a `ClientHttpRequestFactory` after the mock binder has attached can cause requests to bypass the mock server. If a test unexpectedly hits the network, check builder/customizer ordering and request factories rather than disabling assertions.

## 16. Timeouts, TLS, and retries: limits of the mock layer

`MockRestServiceServer` does not open a TCP socket. Therefore it does not prove:

- DNS lookups work.
- HTTPS certificates/truststores are valid.
- Proxy authentication or connection pooling works.
- Socket read/connect timeouts fire.
- TCP resets, partial responses, or network-stack redirects behave properly.
- Retries occur with real timing.

If a client must verify transport timeouts, use a **real local HTTP server** on a random port (WireMock or OkHttp MockWebServer), introduce controlled response delays, and set bounded test timeouts. Those libraries are omitted from the demo `build.gradle` because this lesson focuses on `@RestClientTest`.

A well-defined retry policy can test invocation counts with mock request expectations, while timing/backoff requires test clock/scheduler utilities or a suitable integration environment. Never blindly add retries to resource-creating POSTs: timeouts can occur after the server already processed the request, requiring an idempotency key and contract.

### Default retrieve() does not retry automatically

In the sample Gateway, `retrieve()` throws `HttpServerErrorException` on 503 by default; it **does not automatically retry**. Test `response503IsHttpServerError` protects this exact behavior. When adding retries, update tests to match the new behavior and assert attempt counts, not just eventual 200 success.

## 17. JSON and content negotiation

Three distinct concepts:

| Field | Who sends it | Meaning |
| --- | --- | --- |
| Request `Content-Type` | Client | Format of the **request body** |
| Request `Accept` | Client | Expected response format |
| Response `Content-Type` | Server/mock | Body format used by the decoder |

GET has no body in the example, so it only sets `Accept: application/json`. POST sends a record body, so it sets both `Content-Type: application/json` and `Accept: application/json`.

Test `textPlainResponseCannotMapJsonDto` returns `text/plain` instead of JSON, illustrating converter mismatch. The malformed JSON test verifies the codec does not silently ignore syntax errors. When the application needs custom Jackson `Module`s or `@JsonComponent`s, import the relevant config/converters into the slice and protect the exact JSON contract.

### Do not infer API correctness from a JSON round-trip

If you serialize a request and deserialize it back into the same object, both sides can share the same bug and the round-trip still passes. Use literal JSON fixtures with field names/types matching the partner contract, while asserting request `Content-Type`, response types, and invalid-input errors.

### Decimals and timestamps

For money, use integer minor units or `BigDecimal` per the API contract—never `double` when decimal precision matters. For timestamps, define zone/offset/format such as RFC 3339 and test deterministic values. Never rely on the CI machine's default timezone.

## 18. HTTP error mapping and domain semantics

In the current adapter, default `retrieve()` behavior:

| Status | Result |
| --- | --- |
| 200 valid JSON | Java `PartnerItem` |
| 204 | Null body, then `IllegalStateException` explicitly checked by Gateway |
| 404 | `HttpClientErrorException.NotFound` |
| 422 | `HttpClientErrorException` subtype, status 422 |
| 503 | `HttpServerErrorException.ServiceUnavailable` |
| 200 broken JSON | `RestClientException` from decoding |
| 200 `text/plain` for DTO | `RestClientException` from converter |

A production adapter might want `findBySku` to return `Optional.empty()` on 404 instead of throwing, or map 429 to `RetryableRemoteException`. That requires `onStatus(...)` or custom error handling **along with corresponding tests**. Never catch all `RestClientException`s and return null: timeouts, 401, 404, and malformed JSON are entirely different problems.

**Do not assert exact full exception messages** if they depend on library/client implementations. Assert subtypes, HTTP statuses, and domain error codes when required by the contract. Only assert custom messages created by the Gateway itself (like empty body) when that behavior is intentionally under your control.

## 19. Protecting URI construction

Never casually concatenate `"https://api.partner.test/v1/items/" + sku` when user input may include whitespace, `/`, `?`, `#`, or Unicode. Use URI templates, `UriBuilder`, or `UriComponentsBuilder`; test special path-variable edge cases per contract.

Snippet (not yet in the sample client):

```java
client.get()
      .uri(builder -> builder
          .path("/v1/items")
          .queryParam("active", true)
          .queryParam("limit", 10)
          .build())
      .retrieve()
      .body(String.class);
```

Request URL expectations must specify exact query params/encoding. If you need a dynamic `orderBy` or hostname from user input, use an allowlist; never let a client dictate an arbitrary URL from a request payload, as that opens SSRF risk in real applications.

## 20. Common pitfalls

| Symptom | Cause | Resolution |
| --- | --- | --- |
| `No qualifying bean for PartnerProductGateway` | Target bean not selected | `@RestClientTest(PartnerProductGateway.class)` |
| `No bean named partnerRestClient` | Config excluded by slice | `@Import(PartnerRestClientConfiguration.class)` |
| `No bean of PartnerClientProperties` | Typed binding not enabled | `@EnableConfigurationProperties` |
| Base URL null/not HTTPS | Test props missing/wrong | Check keys and record constructor |
| Mock server sees no request | Client built outside Boot builder | Use managed `RestClient.Builder` or explicit binding |
| Wrong URI expectation with `RestClient` | Used relative `/v1/items` | Use full URL |
| Wrong URI expectation with `RestTemplate` `rootUri` | Used full URL while mock matches path | Use `requestTo("/health")` |
| `X-Partner-Key` header missing | Config not imported or different client | Assert bean and request headers |
| POST JSON violates contract | Wrong record/converter/mapper | `content().json(...)` |
| 404 handled wrongly | Overly broad catch or custom status handler | Assert domain policy + status |
| 503 does not retry | No retry policy | Test retry policy separately if needed |
| 204 returns null | Empty body valid in HTTP, disallowed by domain | Test explicit empty-body policy |
| Malformed JSON test fails differently than expected | Different codec or body | Assert appropriate `RestClientException` |
| Test only passes when run alone | Expectations not reset, shared state | `@BeforeEach server.reset()` |
| Multiple clients share injected server | Each builder has its own mock server | Split tests or bind servers properly |
| Slice tries to load DB/unrelated service | Imported config too broad | Narrow config/client dependencies |
| Tests pass, production TLS fails | Mock does not hit the network | Add real local network integration |
| Spring Boot 4 imports used in Boot 3 | Different packages | Use matching Boot 3.3 APIs |

### Debugging workflow

1. Confirm Java 17, Spring Boot 3.3.5, and dependencies.
2. Read the root cause from `ApplicationContext`, not just the outer wrapper message.
3. Verify `@RestClientTest` includes the target class.
4. Verify the real config is `@Import`ed and the properties type is enabled.
5. Inspect the test properties bean with assertions.
6. Confirm `RestClient` is built from the managed `RestClient.Builder`.
7. Add one mock expectation for the absolute GET URL returning small JSON.
8. Assert method/header/DTO and call `server.verify()`.
9. Add negative response tests: 404, 503, malformed JSON.
10. If the client unexpectedly hits real networking, inspect request factories/customizers.
11. If a failure only happens over real HTTPS/TLS, write a network integration test.
12. Run the full suite to catch expectation leakage or context issues.

## 21. Running and accurately reporting test counts

According to the sample code:

| Test class | `@Test` method count | Focus |
| --- | ---: | --- |
| `PartnerProductGatewayTest` | 12 | Config, `RestClient` GET/POST, headers, body, errors |
| `LegacyHealthClientTest` | 1 | `RestTemplateBuilder.rootUri` expectation |
| **Total** | **13** | HTTP client slice tests |

When the project has Gradle Wrapper:

```bash
./gradlew test --tests 'com.example.outbound.PartnerProductGatewayTest'
./gradlew test --tests 'com.example.outbound.LegacyHealthClientTest'
./gradlew test
```

Windows PowerShell:

```powershell
.\gradlew.bat test
```

Without a wrapper, if a compatible Gradle is installed on the machine:

```bash
gradle test
```

Gradle/JUnit reports are typically located at:

```text
build/reports/tests/test/index.html
build/test-results/test/
```

**13 is the number of methods in the source**, not a claim that 13 PASS results were observed. No real Gradle run took place while authoring this lesson. If a test fails, inspect the request matcher, actual URI/header/body, and root cause before modifying expected values.

## 22. When to expand to a real HTTP server?

An additional integration test suite can run WireMock or OkHttp MockWebServer on `localhost:randomPort` and inject the dynamic base URL into `PartnerClientProperties` via `@DynamicPropertySource`. Then the real client traverses the TCP/HTTP stack and can verify timeouts, proxies, TLS (if supported by the mock server), redirects, and streaming.

Never call a real partner API in default unit-style tests, as external services can rate-limit, go down, mutate data, or require secrets. When provider contract verification is needed, use a dedicated environment/suite with synthetic data.

### Test configuration must not overshadow production wiring

If a test simply creates a mock `RestClient` bean with hardcoded responses, it never executes `PartnerRestClientConfiguration` and misses breaking changes to the production builder. The strength of this lesson is **importing production config and mocking only the server response**.

## 23. Safety and security rules

- Never place production API keys in test sources.
- Never log credentials or full authorization headers on CI.
- Use fake base URL `https://api.partner.test` for mock-only tests.
- Never pass arbitrary user URLs directly into `RestClient` to prevent SSRF.
- Never turn a TLS error into a pass by disabling certificate validation.
- When testing real networking, run a test-managed local server with bounded timeouts.
- For POST retries, enforce idempotency rules so you do not create duplicate resources.
- Separate HTTP client configuration from database/messaging configs so test slices stay small with few side effects.
- With multiple REST clients, use clear named beans or qualifiers.
- Protect JSON contracts with fixtures free of PII.
- Document clearly what tests **have not** checked: sockets, TLS, and real production provider behavior.

## 24. Pre-merge QA checklist

1. Does `@RestClientTest` select the right client class?
2. Is the client under test real rather than mocked with Mockito?
3. Is the real client configuration `@Import`ed?
4. Is the `@ConfigurationProperties` bean properly enabled?
5. Do test properties use only fake credentials and deterministic URLs?
6. Does the client use the managed `RestClient.Builder` or `RestTemplateBuilder`?
7. Do named beans/`@Qualifier` prevent injecting the wrong client?
8. Is `MockRestServiceServer` bound to the right builder?
9. Do GET/POST tests assert URL, method, headers, and body?
10. Are `Accept` and `Content-Type` applied in the right direction?
11. Are JSON response fields checked thoroughly, not merely non-null?
12. Are 404/422/503, malformed JSON, and 204 tested per contract?
13. Is `server.verify()` called?
14. Are expectations reset between test methods?
15. For `RestClient.Builder`, are full URI expectations used?
16. For `RestTemplateBuilder.rootUri`, are relative URIs used where appropriate?
17. Are global customizers avoided for sending one partner's secret to every client?
18. Are mock servers not mistaken for TCP/TLS network integration tests?
19. Do tests avoid accidentally calling production endpoints or the internet?
20. Does the project use imports matching Spring Boot 3.3?
21. Did real CI/test reports confirm status rather than inferring from method count?
22. When custom converters or status mappings change, are contract tests updated properly?

## 25. Hands-on exercises

1. Run the Gateway tests and confirm no real `api.partner.test` HTTP server is needed.
2. Remove `@Import(PartnerRestClientConfiguration.class)` to observe the missing-bean error.
3. Remove `@EnableConfigurationProperties` and read the binding root cause.
4. Change default header `X-Client-Tag` and verify the request matcher catches the discrepancy.
5. Change the test base URL to another fake host and observe how expected URIs must update when the contract changes.
6. Try `RestClient.create()` in a sandbox and observe that the mock server is not bound automatically.
7. Remove `accept(MediaType.APPLICATION_JSON)` on GET and observe the header assertion.
8. Remove `contentType(APPLICATION_JSON)` on POST and inspect serialization/content-type contract behavior.
9. Rename `priceCents` to `price` in the request record so the literal JSON matcher catches the regression.
10. Return malformed JSON and distinguish decoding errors from HTTP status errors.
11. Return 401/403/429, design a mapping policy, and write tests for it.
12. Add `onStatus(...)` for 404 and test the domain exception under the new contract.
13. Add query parameters and assert URI encoding.
14. Run `LegacyHealthClientTest` and explain why `/health` is expected as a relative URI.
15. Create a second client and work out how to bind the right server per builder.
16. Use WireMock/MockWebServer for a separate connection-timeout integration test.
17. If production has a global `RestClientCustomizer`, import the corresponding config and test header/interceptor effects.
18. Run each test method independently and as a full suite to confirm order independence.
19. Inspect the Gradle report to verify method counts and failure reasons.
20. Verify fake secrets were never replaced with real tokens before committing.

## 26. Official documentation

- [Spring Boot 3.3 — Auto-configured REST Client Tests](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html): `@RestClientTest`, builders, `MockRestServiceServer`, slice scanning, absolute/relative expectations.
- [Spring Boot 3.3 — Externalized Configuration](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html): `@ConfigurationProperties`, binding, property sources.
- [Spring Boot 3.3 — RestClientTest API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/autoconfigure/web/client/RestClientTest.html): annotation attributes.
- [Spring Boot 3.3 — MockServerRestClientCustomizer](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/web/client/MockServerRestClientCustomizer.html): mock binding with `RestClient.Builder`.
- [Spring Framework — REST Clients](https://docs.spring.io/spring-framework/reference/integration/rest-clients.html): `RestClient`/`RestTemplate` APIs.
- [Spring Framework — MockRestServiceServer](https://docs.spring.io/spring-framework/reference/testing/spring-mvc-test-client.html): expectations, matchers, response creators, and verification.
- [JUnit Jupiter User Guide](https://junit.org/junit5/docs/current/user-guide/): `@Test`, `@BeforeEach`, and test lifecycle.

## 27. Summary

**`@RestClientTest`** is the slice dedicated to testing real outbound HTTP clients in Spring Boot, using `MockRestServiceServer` to fake the server side without TCP networking. In Boot 3.3, the slice configures `RestClient.Builder`, `RestTemplateBuilder`, and JSON support, but **does not automatically scan all ordinary configs/`@ConfigurationProperties`**.

To test **client configuration imported into the slice**, import `PartnerRestClientConfiguration` via `@Import`, register `PartnerClientProperties` via `@EnableConfigurationProperties`, and build `RestClient` from the **Spring-managed builder**. Verify final requests: absolute URL, method, API key/headers, JSON body, response DTO, status errors, and null/malformed bodies. Expect full URLs with `RestClient.Builder`; relative paths may be expected with `RestTemplateBuilder.rootUri` per Boot 3.3 documentation. Add real HTTP integration tests whenever you must prove DNS/TLS/socket behavior—never mistake mock-server tests for testing every network layer.
