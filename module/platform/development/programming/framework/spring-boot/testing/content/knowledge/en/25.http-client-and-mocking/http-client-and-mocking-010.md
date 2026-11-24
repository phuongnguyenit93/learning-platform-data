# Starting Stubs on Dynamic Ports, Resetting Expectations, and Cleaning Up After Tests

## 1. Lesson objective

Within the **Spring Boot - testing** module, **HTTP Client and Mocking** group, testing an HTTP client should neither hit live partner APIs nor depend on a fixed server at `localhost:8080`. An HTTP stub server—such as **WireMock**—lets you simulate external API responses, verify URLs, methods, headers, bodies, and error handling while keeping tests independent of partner networks.

Yet a stub server only stays reliable when it solves three responsibilities cleanly:

1. **Starting on a dynamic port:** avoid colliding with developer/CI ports, retrieve the actual port after startup, and wire it into the HTTP client under test.
2. **Resetting expectations and request journals between tests:** every test declares its own responses and verifications—never inheriting mappings, call counts, or scenario states from an earlier test.
3. **Cleaning up at the right lifecycle boundary:** test methods reset state on exit; test classes/contexts stop the server on time to prevent socket leaks, stale URLs inside Spring's context cache, or background tasks sending late requests.

The main example uses **Java 17, Spring Boot 3.5.16, Spring `RestClient`, JUnit Jupiter, and WireMock 3.13.2**. All HTTP traffic runs over loopback against a `WireMockServer` configured with `dynamicPort()`; once dependencies are cached, no Docker, real API keys, or internet access are needed.

After this lesson, you will cleanly distinguish:

- **`WireMockServer`** running real HTTP on a local port;
- **`@WireMockTest` / `WireMockExtension`** managing lifecycle and JUnit auto-reset;
- **`@DynamicPropertySource` / `DynamicPropertyRegistrar`** wiring dynamic URLs into Spring;
- **`resetAll()`, `resetRequests()`, `resetMappings()`, `resetScenarios()`** and their different levels of state cleanup;
- **`MockRestServiceServer`**: mocking requests inside the Spring client without opening a listening HTTP port;
- **test isolation** when multiple tests or test classes share a server or context.

The goal is never "stub X and trivially assert X"; tests must prove the **client actually sends the right request** and handles successes, valid 404s, and 503 failures.

## 2. How does an HTTP stub server differ from mocking methods?

Suppose the application needs to call:

~~~http
GET /external/products/SKU-7 HTTP/1.1
Host: partner.example.invalid
X-Client: spring-demo
Accept: application/json
~~~

Three testing levels exist:

| Test approach | Real TCP/HTTP? | What can it verify? | What does it fail to prove? |
| --- | --- | --- | --- |
| Mockito mock of `PartnerGateway` interface | No | Whether business callers invoke the right method/args | HTTP encoding, headers, statuses, JSON transport |
| Spring `MockRestServiceServer` | Opens no network port | `RestClient`/`RestTemplate` request matchers, response decoding | Real TCP sockets, TLS, network delays/faults |
| Dynamic-port WireMock/MockWebServer | **Yes**, loopback HTTP | Request path, headers, method, JSON, statuses, some transport behavior | Real production backend contract, real auth/network topology |

**WireMock** is a test double for an upstream API, not a full clone of the partner's system. Write mappings deliberately, test key failure modes explicitly, and back up upstream contract assumptions with contract tests or staging integration tests where needed.

In Spring Boot 3.5, `@RestClientTest` supports `MockRestServiceServer` for client slices. Whenever you want to verify a client against a real dynamic-port HTTP server (especially headers, fault injection, and connections/timeouts), **WireMock or OkHttp `MockWebServer`** is the better fit.

## 3. Why must you use a dynamic port?

An error-prone example:

~~~java
// Counter-example: hardcoding port 8080 on CI machines.
WireMockServer stub =
        new WireMockServer(wireMockConfig().port(8080));
stub.start();
~~~

Port 8080 may already be occupied by another application. When running tests in parallel, two test processes race for the same bind, leaving one with `Address already in use`. Never work around it by guessing port 8081 or 9999 and hoping "nobody is using it."

WireMock lets the operating system assign a free port:

~~~java
WireMockServer stub =
        new WireMockServer(wireMockConfig().dynamicPort());

stub.start();
try {
    String baseUrl = stub.baseUrl();
    int port = stub.port();

    // baseUrl looks like http://localhost:<actual dynamic port>
    // Pass it into the HTTP client under test.
} finally {
    stub.stop();
}
~~~

This is an illustrative Java snippet requiring imports:

~~~java
import com.github.tomakehurst.wiremock.WireMockServer;
import static com.github.tomakehurst.wiremock.core.WireMockConfiguration.wireMockConfig;
~~~

Call `port()`/`baseUrl()` **only after `start()`** to read the assigned port. Never reserve a random port with `new ServerSocket(0)` and close it before WireMock binds: the gap between closing and rebinding introduces a port-stealing race (*TOCTOU*).

### Dynamic ports do not mean exposing the stub publicly

Stubs run locally during tests; bind/host settings should remain local rather than opening test APIs to the internet. WireMock's admin API can add or delete mappings, so never expose an unprotected WireMock admin endpoint on an untrusted network.

### Dynamic ports must enter application config on time

If an HTTP client is constructed during Spring context startup, **never build the client with `localhost:8080` and swap a static variable afterward**. `RestClient` has already captured the old base URL. The real URL must be ready **before the `PartnerCatalogClient` bean is built**. With Spring TestContext, use `@DynamicPropertySource` or `DynamicPropertyRegistrar`.

## 4. Three lifecycles that must align

~~~text
JUnit test class loads
     |
     +-- Start WireMockServer (port 0 -> random port)
     |
Spring TestContext prepares ApplicationContext
     |
     +-- @DynamicPropertySource publishes real URL
     +-- RestClient.Builder builds client targeting that URL
     |
@BeforeEach -> reset mappings + request journal
     |
@Test -> register stub -> call client -> assert/verify
     |
@AfterEach -> reset state (even if assertions fail normally)
     |
... remaining test methods ...
     |
@AfterAll -> stop WireMockServer
     |
Spring TestContext -> evict cached context when marked dirty
~~~

**Note on Spring TestContext caching:** Spring can cache an `ApplicationContext` after JUnit finishes a test class. If that cached context's `RestClient` bean still points to a stopped WireMock port, the next test class reusing the context hits `Connection refused`. In the **manual static server sample** below, the test adds `@DirtiesContext(classMode = AFTER_CLASS)` to prevent reusing a client wired to a stopped class-scoped server. That guarantees correctness for a small example; large suites seeking better cache reuse can manage the **server bean inside the Spring context**, covered in section 14.

`@DirtiesContext` incurs Spring context rebuild cost. Avoid slapping it onto every test indiscriminately when a cleaner lifecycle design exists. The rule of thumb is that URLs and backends must live **at least as long as the beans/clients using them**.

## 5. Comparison of server management techniques

| Technique | Start/stop | Reset between methods | Tied to Spring context? | Risk |
| --- | --- | --- | --- | --- |
| `@WireMockTest` | WireMock JUnit extension, class-scoped by default | **Auto-resets before each test** | No | Spring cache may outlive the extension |
| Static `@RegisterExtension WireMockExtension` | JUnit extension, per class | **Auto-resets**, unless disabled | No | Still requires care with cache/parallel/state |
| Instance `@RegisterExtension` | JUnit extension, per method | Fresh server every method | No | Startup overhead; new URI must reach new client |
| Manual `WireMockServer` + `@BeforeAll/@AfterAll` | Test code | **Must call reset manually** | No | Forgetting stop/reset, stale URL in context cache |
| Spring-managed `@Bean(initMethod/destroyMethod)` | Spring `ApplicationContext` | **Must reset per test** | **Yes** | Needs properly ordered dynamic property registrar |
| Docker WireMock/Testcontainers | JUnit/Spring or custom code | Not universally auto-reset | Setup-dependent | Docker/port mapping and resource lifecycle |

Never combine `@WireMockTest` and manual `WireMockServer.start()` on **the same server instance**. Pick a single owner for start/stop.

## 6. Runnable example: Spring Boot RestClient + WireMock 3

Project structure:

~~~text
settings.gradle
build.gradle
src/main/java/com/example/stubhttp/
  StubHttpApplication.java
  RemoteProduct.java
  PartnerCatalogClient.java
src/main/resources/
  application.properties
src/test/java/com/example/stubhttp/
  PartnerCatalogClientIntegrationTest.java
  PartnerCatalogClientExtensionTest.java
~~~

The example **never calls a real partner**. Production connects to real URLs only via environment deployment config; `example.invalid` in properties is an illustrative placeholder domain, not a usable endpoint.

### settings.gradle

~~~groovy
rootProject.name = 'spring-http-stub-tests'
~~~

### build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
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

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.wiremock:wiremock-standalone:3.13.2'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
~~~

**Why `wiremock-standalone`?** WireMock 3.x distributes a shaded/bundled JAR to reduce dependency collisions (especially HTTP server/Jetty libraries) alongside Spring Boot; it works directly as a test dependency without launching a separate process. WireMock 3.13.2 is a documented 3.x release. Never mix WireMock 4.x beta APIs/imports with 3.x examples without migrating intentionally.

`spring-boot-starter-web` provides Spring MVC/Jackson and Boot 3.5 `RestClient.Builder` auto-config; `spring-boot-starter-test` brings JUnit Jupiter and AssertJ. No Docker and no listening app server are required because the app **only makes outbound HTTP calls**, tested with `@SpringBootTest(webEnvironment = NONE)`.

### src/main/resources/application.properties

~~~properties
partner.catalog.base-url=${PARTNER_CATALOG_BASE_URL:https://partner.example.invalid}
partner.catalog.client-name=spring-demo
~~~

`PARTNER_CATALOG_BASE_URL` is the environment configuration knob; in tests, `@DynamicPropertySource` **overrides** `partner.catalog.base-url` with the stub's live URL. `partner.example.invalid` should never receive a request when tests are wired properly; if a test attempts to contact it, treat that as a wiring defect.

## 7. Application class and DTO

**src/main/java/com/example/stubhttp/StubHttpApplication.java**

~~~java
package com.example.stubhttp;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class StubHttpApplication {

    public static void main(String[] args) {
        SpringApplication.run(StubHttpApplication.class, args);
    }
}
~~~

**src/main/java/com/example/stubhttp/RemoteProduct.java**

~~~java
package com.example.stubhttp;

public record RemoteProduct(
        String sku,
        String title,
        int quantity
) {
}
~~~

Spring Boot/Jackson deserializes JSON objects into matching Java 17 record components. Tests verify actual field values after crossing HTTP transport instead of returning pre-built Mockito stubs.

## 8. Real client using RestClient and distinguishing 404 from 503

**src/main/java/com/example/stubhttp/PartnerCatalogClient.java**

~~~java
package com.example.stubhttp;

import java.util.Optional;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpHeaders;
import org.springframework.stereotype.Service;
import org.springframework.web.client.HttpClientErrorException;
import org.springframework.web.client.RestClient;

@Service
public class PartnerCatalogClient {
    private final RestClient http;

    public PartnerCatalogClient(
            RestClient.Builder builder,
            @Value("${partner.catalog.base-url}") String baseUrl,
            @Value("${partner.catalog.client-name}") String clientName
    ) {
        this.http = builder
                .baseUrl(baseUrl)
                .defaultHeader("X-Client", clientName)
                .defaultHeader(
                        HttpHeaders.ACCEPT, "application/json"
                )
                .build();
    }

    public Optional<RemoteProduct> find(String sku) {
        try {
            RemoteProduct product = http.get()
                    .uri("/external/products/{sku}", sku)
                    .retrieve()
                    .body(RemoteProduct.class);

            return Optional.ofNullable(product);
        } catch (HttpClientErrorException.NotFound e) {
            // 404 is a business case: product does not exist.
            return Optional.empty();
        }
    }
}
~~~

Key choices:

- `RestClient.Builder` is configured by Spring Boot; the constructor accepts the base URL via configuration rather than hardcoding host/port.
- `.uri("/external/products/{sku}", sku)` substitutes the path variable; for complex identifiers, verify URI encoding.
- Header `X-Client` is sent by the real client; the stub matches and verifies it.
- `.retrieve()` throws exceptions for 4xx/5xx by default; code converts only **404** into `Optional.empty()`.
- **503** propagates rather than being swallowed like 404; tests verify this.
- Never allocate `new RestClient` per request or call static `WireMock.configureFor` inside business code.

HTTP `200` with valid JSON decodes into `RemoteProduct`. `404` is a valid business branch; `503` is an infrastructure failure left for callers to handle under separate retry/circuit-breaker contracts.

## 9. Main integration test: dynamic port, dynamic URL, explicit cleanup

**src/test/java/com/example/stubhttp/PartnerCatalogClientIntegrationTest.java**

~~~java
package com.example.stubhttp;

import com.github.tomakehurst.wiremock.WireMockServer;

import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.web.client.HttpServerErrorException;

import static com.github.tomakehurst.wiremock.client.WireMock.*;
import static com.github.tomakehurst.wiremock.core.WireMockConfiguration.wireMockConfig;
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.NONE
)
@DirtiesContext(
        classMode = DirtiesContext.ClassMode.AFTER_CLASS
)
class PartnerCatalogClientIntegrationTest {

    private static final WireMockServer STUB =
            new WireMockServer(wireMockConfig().dynamicPort());

    // Start on class initialization so the property supplier
    // always exposes a bound endpoint before Spring builds the client.
    static {
        STUB.start();
    }

    @DynamicPropertySource
    static void upstreamProperties(DynamicPropertyRegistry registry) {
        registry.add(
                "partner.catalog.base-url",
                STUB::baseUrl
        );
    }

    @Autowired
    PartnerCatalogClient client;

    @Value("${partner.catalog.base-url}")
    String injectedBaseUrl;

    @BeforeEach
    void resetBeforeMethod() {
        // Each method inherits zero stub mappings or requests.
        STUB.resetAll();
    }

    @AfterEach
    void clearAfterMethod() {
        // @AfterEach runs even when a @Test assertion fails normally.
        STUB.resetAll();
    }

    @AfterAll
    static void stopServer() {
        STUB.stop();
    }

    @Test
    void dynamicPortIsWiredIntoSpringClient() {
        assertThat(STUB.isRunning()).isTrue();
        assertThat(STUB.port()).isPositive();
        assertThat(injectedBaseUrl).isEqualTo(STUB.baseUrl());
    }

    @Test
    void matchingRequestReturnsRealJsonFromHttpStub() {
        STUB.stubFor(
                get(urlEqualTo("/external/products/SKU-7"))
                        .withHeader(
                                "X-Client", equalTo("spring-demo")
                        )
                        .willReturn(
                                aResponse()
                                        .withStatus(200)
                                        .withHeader(
                                                "Content-Type",
                                                "application/json"
                                        )
                                        .withBody(
                                                """
                                                {
                                                  "sku": "SKU-7",
                                                  "title": "Notebook",
                                                  "quantity": 4
                                                }
                                                """
                                        )
                        )
        );

        RemoteProduct product =
                client.find("SKU-7").orElseThrow();

        assertThat(product.sku()).isEqualTo("SKU-7");
        assertThat(product.title()).isEqualTo("Notebook");
        assertThat(product.quantity()).isEqualTo(4);

        STUB.verify(
                1,
                getRequestedFor(
                        urlEqualTo("/external/products/SKU-7")
                ).withHeader("X-Client", equalTo("spring-demo"))
        );
    }

    @Test
    void explicit404ResponseBecomesEmptyOptional() {
        STUB.stubFor(
                get(urlEqualTo("/external/products/MISSING"))
                        .willReturn(
                                aResponse().withStatus(404)
                        )
        );

        assertThat(client.find("MISSING")).isEmpty();

        STUB.verify(
                1,
                getRequestedFor(
                        urlEqualTo("/external/products/MISSING")
                )
        );
    }

    @Test
    void unavailablePartner503MustNotBeSilentlyConvertedTo404() {
        STUB.stubFor(
                get(urlEqualTo("/external/products/RETRY"))
                        .willReturn(
                                aResponse()
                                        .withStatus(503)
                                        .withBody("upstream unavailable")
                        )
        );

        assertThatThrownBy(
                () -> client.find("RETRY")
        ).isInstanceOf(
                HttpServerErrorException.ServiceUnavailable.class
        );

        STUB.verify(
                1,
                getRequestedFor(
                        urlEqualTo("/external/products/RETRY")
                )
        );
    }

    @Test
    void resetAllRemovesBothOldMappingAndRequestHistory() {
        STUB.stubFor(
                get(urlEqualTo("/external/products/OLD"))
                        .willReturn(
                                aResponse()
                                        .withStatus(200)
                                        .withHeader(
                                                "Content-Type",
                                                "application/json"
                                        )
                                        .withBody(
                                                """
                                                {
                                                  "sku": "OLD",
                                                  "title": "Old title",
                                                  "quantity": 1
                                                }
                                                """
                                        )
                        )
        );

        assertThat(client.find("OLD")).isPresent();

        STUB.verify(
                1,
                getRequestedFor(
                        urlEqualTo("/external/products/OLD")
                )
        );

        // Clear the 200 stub and recorded request history.
        STUB.resetAll();

        // No mapping remains -> WireMockServer returns default 404.
        // The client maps 404 to Optional.empty().
        assertThat(client.find("OLD")).isEmpty();

        // After reset, only the SECOND request appears in the journal.
        STUB.verify(
                1,
                getRequestedFor(
                        urlEqualTo("/external/products/OLD")
                )
        );
    }
}
~~~

### Five narrowly scoped test cases

| Test method | What is verified | Expected |
| --- | --- | --- |
| `dynamicPortIsWiredIntoSpringClient` | Server start + dynamic property | Positive port; URL in Spring equals WireMock's URL |
| `matchingRequestReturnsRealJsonFromHttpStub` | Header/path, Jackson response body mapping | `SKU-7`, `Notebook`, `quantity=4`, exactly 1 HTTP GET |
| `explicit404ResponseBecomesEmptyOptional` | 404 business branch | `Optional.empty()`, exactly 1 GET |
| `unavailablePartner503MustNotBeSilentlyConvertedTo404` | 503 not swallowed | `ServiceUnavailable` exception, exactly 1 GET |
| `resetAllRemovesBothOldMappingAndRequestHistory` | Clearing mappings and request journal | First call 200; after reset 404; fresh journal counts 1 |

**Zero test-order dependence.** `resetAll()` runs before each method and again after each method; no test cares which method ran earlier. `@AfterAll` stops the server once every method completes. `@DirtiesContext` stops Spring from reusing a client/cache bound to a server stopped at the end of this class.

**Nothing runs on Docker**, because WireMock runs as an embedded Java server inside the test JVM. Real HTTP runs over loopback, yet it does not verify production DNS, TLS, or latency.

### An important trap in the reset test

After `resetAll()`, `WireMockServer` has no mapping for `/external/products/OLD`, so it returns a **default HTTP 404**. In the demo, the client maps any 404 to `Optional.empty()`. Therefore, asserting only "empty" would not prove the mapping was cleared; we first assert **200 on the first call**, then reset, and finally **verify the request journal holds only 1 new request**. If an app differentiates 404 bodies/error codes, stub and verify the 404 contract explicitly so an **unmatched request** is never mistaken for a passing business 404.

### Why not use @BeforeAll to call start()?

You could start the server in `@BeforeAll`, provided you verify lifecycle ordering against Spring's test extension—specifically when `@DynamicPropertySource` suppliers evaluate and when client beans are built. The sample uses **static initialization** to guarantee WireMock binds its port before any Spring bean touches the supplier.

This is a clean choice for a small demo, not optimal for every suite. Static initializers risk abrupt failures if class initialization breaks before JUnit starts; the Spring-bean-managed approach in section 14 is better when many test classes share a cached context.

## 10. Resetting expectations: what exactly gets cleared?

`WireMockServer` holds multiple state buckets:

1. **Stub mappings/expectations:** request matchers and response definitions (including priorities/delays).
2. **Request journal:** received HTTP requests and match statuses, used by `verify(...)`.
3. **Scenario states:** stateful machines for sequential responses like "call 1: pending, call 2: completed."
4. **Global settings** or file-backed default mappings when configured.

| `WireMockServer` API | Effect | When to use |
| --- | --- | --- |
| `resetAll()` | Clears mappings and request journal, restoring clean state; scenario states reset per reset semantics | **Between independent tests**, as in the main sample |
| `resetRequests()` | Clears only the request journal, **keeping mappings** | Multiple phases inside one test sharing contract stubs |
| `resetMappings()` | Resets/deletes stub mappings; does not prove request journal is clean | When only replacing stub sets |
| `resetScenarios()` | Resets configured scenario states back to start | Re-running a state machine while keeping mappings |
| `resetToDefaultMappings()` | Restores default mappings loaded from files when present | When preserving file-based fixtures |
| `stop()` | Shuts down server/listening socket | **End of lifecycle**, never as a substitute for per-method reset |

Method names can differ slightly between the server instance and the static client DSL: on `WireMockServer`, it is `resetRequests()`; on static `WireMock`, docs use `resetAllRequests()`. Never copy method names from one object type to another without checking your API version.

### Resetting does not automatically verify expected requests occurred

WireMock mappings declare **if a matching request arrives, return this response**—they do not enforce that the code *must* send the request. A test that registers a stub without calling the client still passes unless you verify. Always call:

~~~java
STUB.verify(
        1,
        getRequestedFor(urlEqualTo("/external/products/SKU-7"))
);
~~~

This snippet belongs in the main test class with `STUB` and imports. When verification fails, WireMock throws an exception failing the test.

### Stub mapping differs from Mockito verify

Mockito's `verify(gateway).find("SKU-7")` only proves a Java method call on a mock. WireMock's `verify(1, getRequestedFor(...))` proves the client emitted a **real HTTP GET to the stub server**. Still, both are test doubles—never label them as "verified live upstream contract."

## 11. Reset in @AfterEach or @BeforeEach?

| Placement | Advantage | Consideration |
| --- | --- | --- |
| `@BeforeEach` calling `resetAll()` | Every test starts from a known clean state | Does not clean up after the last test if the runner aborts right before the next |
| `@AfterEach` calling `resetAll()` | Cleans up after a method even when assertions fail normally | Does not fix dirty state lingering before the very first method |
| Both | Explicit boundaries guarding against leftover state from earlier methods | Slightly redundant, great for pedagogical clarity |
| JUnit WireMock extension default | Auto-resets before each method, cutting boilerplate | Must verify extension lifecycle aligns with Spring context |

In this lesson's example, using both `@BeforeEach` and `@AfterEach` intentionally emphasizes **clean setup + clean teardown**. In large production suites, pick **one** clear owner instead of scattering resets everywhere; avoid redundant manual resets when an extension already auto-resets and tests are properly isolated.

JUnit `@AfterEach` is not guaranteed process-level cleanup: on `SIGKILL`, killed JVMs, or machine crashes, teardown skips. For external Docker processes, shared files, or production-like data, maintain external resource owners/cleanup. With in-JVM Java WireMock, the OS reclaims sockets on normal process exit, though apps should still stop servers cleanly at lifecycle end.

## 12. WireMock JUnit 5: extension managing start/stop and auto-reset

When you do not need Spring's `@DynamicPropertySource` and want to test **the client as a plain Java object** taking a base URL constructor parameter, WireMock's JUnit Jupiter extension minimizes boilerplate.

**src/test/java/com/example/stubhttp/PartnerCatalogClientExtensionTest.java**

~~~java
package com.example.stubhttp;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.RegisterExtension;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.HttpServerErrorException;

import com.github.tomakehurst.wiremock.junit5.WireMockExtension;

import static com.github.tomakehurst.wiremock.client.WireMock.*;
import static com.github.tomakehurst.wiremock.core.WireMockConfiguration.wireMockConfig;
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class PartnerCatalogClientExtensionTest {

    @RegisterExtension
    static WireMockExtension STUB = WireMockExtension.newInstance()
            .options(wireMockConfig().dynamicPort())
            .build();

    private PartnerCatalogClient newClient() {
        return new PartnerCatalogClient(
                RestClient.builder(),
                STUB.baseUrl(),
                "spring-demo"
        );
    }

    @Test
    void extensionAllocatesPortAndResetsAutomatically() {
        assertThat(STUB.port()).isPositive();

        STUB.stubFor(
                get(urlEqualTo("/external/products/BOOK"))
                        .willReturn(
                                aResponse()
                                        .withStatus(200)
                                        .withHeader(
                                                "Content-Type",
                                                "application/json"
                                        )
                                        .withBody(
                                                """
                                                {
                                                  "sku": "BOOK",
                                                  "title": "Guide",
                                                  "quantity": 2
                                                }
                                                """
                                        )
                        )
        );

        assertThat(newClient().find("BOOK").orElseThrow()
                .title()).isEqualTo("Guide");

        STUB.verify(
                1,
                getRequestedFor(
                        urlEqualTo("/external/products/BOOK")
                )
        );
    }

    @Test
    void secondMethodDeclaresItsOwn503Mapping() {
        STUB.stubFor(
                get(urlEqualTo("/external/products/FAIL"))
                        .willReturn(
                                aResponse().withStatus(503)
                        )
        );

        assertThatThrownBy(
                () -> newClient().find("FAIL")
        ).isInstanceOf(
                HttpServerErrorException.ServiceUnavailable.class
        );

        STUB.verify(
                1,
                getRequestedFor(
                        urlEqualTo("/external/products/FAIL")
                )
        );
    }
}
~~~

This is a **second runnable test class** (2 methods) in the same project. It needs no Spring `ApplicationContext`; `RestClient.builder()` runs directly while `PartnerCatalogClient` uses its normal constructor.

Per WireMock 3.13.x docs:

- Static `@RegisterExtension`: starts before methods, stops after the test class.
- The extension **auto-resets stubs and requests before each test method**.
- Non-static field: per-method lifecycle, creating a new server per method.
- `.resetOnEachTest(false)` (since 3.13.0) disables auto-reset; use only when intentionally preserving state across methods with full awareness of the risk.
- The extension defaults to **fail-on-unmatched requests**; tests intentionally expecting 404 must register a 404 stub. You can set `.failOnUnmatchedRequests(false)` when needed, yet never make it the default to mask broken mappings.

In this extension test there are **no unmatched requests**, so keeping the default makes the tests stricter.

### Concise @WireMockTest annotation

~~~java
@WireMockTest
class SimpleWireMockTest {

    @Test
    void demo(WireMockRuntimeInfo info) {
        int port = info.getHttpPort();
        // port is dynamic; info also exposes WireMock DSL.
    }
}
~~~

This is a **skeleton** requiring `com.github.tomakehurst.wiremock.junit5.WireMockTest`, `WireMockRuntimeInfo`, JUnit, and assertions to become a standalone test. `@WireMockTest` defaults to a **random-port** WireMock HTTP server that auto-resets before each method. Never use a fixed port unless required by a specific constraint.

**Note:** `@RegisterExtension`/`@WireMockTest` owns the lifecycle. Do not add `@AfterAll STUB.stop()` when the extension already handles stopping, unless managing a separate server. Stopping the same resource twice obscures ownership errors.

## 13. JUnit extension + Spring @SpringBootTest: context-cache pitfall to avoid

Some guides combine them like this:

~~~java
@SpringBootTest
class CachedContextWithClassScopedServerTest {
    @RegisterExtension
    static WireMockExtension STUB = WireMockExtension.newInstance()
            .options(wireMockConfig().dynamicPort())
            .build();

    @DynamicPropertySource
    static void urls(DynamicPropertyRegistry registry) {
        registry.add("partner.catalog.base-url", STUB::baseUrl);
    }
}
~~~

**This is a skeleton to discuss risk**, not a runnable sample. It can work when lifecycle ordering lines up and the context builds after server startup, though you must verify that under your real test setup.

The danger: the static WireMock extension stops the server **when the test class finishes**; Spring's cache can keep `PartnerCatalogClient` built with the old URL alive longer. When another class reuses that cached context, the client keeps calling a closed port.

Solutions based on need:

- Mark the context non-reusable after the class: `@DirtiesContext(classMode=AFTER_CLASS)`; simple, though costly at startup.
- Register the stub as a **Spring-managed bean** so the server shares the context's lifetime; ideal when caching contexts across many classes.
- Construct the HTTP client inside the test after the extension starts, **without** a Spring context, like the runnable extension class in section 12.
- If multiple classes need different base URLs, ensure context cache keys differ or use dedicated configs; never assume `@DynamicPropertySource` differentiates runtime dynamic values from the same method signature.

**Never** declare `@DynamicPropertySource` on a non-static method or call `STUB.port()` before the server starts. Spring's registry accepts a `Supplier` evaluated only when the property is read; the server must already be running at that moment.

## 14. A better pattern for many test classes: Spring-managed stub

Spring Framework 6.2 introduces **`DynamicPropertyRegistrar`**; Spring Boot 3.5 builds on Spring Framework 6.2. You can define `WireMockServer` as a Spring bean and register its dynamic URL from that bean, keeping **both the server and `RestClient` inside the same Spring `ApplicationContext`**.

Illustrative test config (use as an alternative, **not** simultaneously with the static server/extension in earlier samples):

~~~java
package com.example.stubhttp;

import com.github.tomakehurst.wiremock.WireMockServer;

import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.test.context.DynamicPropertyRegistrar;

import static com.github.tomakehurst.wiremock.core.WireMockConfiguration.wireMockConfig;

@TestConfiguration(proxyBeanMethods = false)
class ManagedStubConfig {

    @Bean(initMethod = "start", destroyMethod = "stop")
    WireMockServer managedStub() {
        return new WireMockServer(wireMockConfig().dynamicPort());
    }

    @Bean
    DynamicPropertyRegistrar upstreamUrl(WireMockServer managedStub) {
        return registry -> registry.add(
                "partner.catalog.base-url",
                managedStub::baseUrl
        );
    }
}
~~~

This is **a Java file that compiles with the right dependencies**, though not a complete standalone integration test. The test class uses:

~~~java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.NONE)
@Import(ManagedStubConfig.class)
class CatalogClientWithManagedStubTest {

    @Autowired WireMockServer stub;
    @Autowired PartnerCatalogClient client;

    @BeforeEach void reset() {
        stub.resetAll();
    }

    @AfterEach void cleanup() {
        stub.resetAll();
    }

    // @Test: declare stub, call client, verify request.
}
~~~

The class above is a **skeleton** needing imports and `@Test` methods to run. Spring TestContext discovers and initializes `DynamicPropertyRegistrar` early before normal singleton pre-instantiation; injecting `managedStub` forces the stub bean to be created and `initMethod="start"` to run before the base URL supplier builds the client.

When the context is cached and reused across classes sharing **the same cache key**, the server stays alive with the context instead of stopping after one test class. When the context closes or is evicted, `destroyMethod="stop"` stops the server. Even then, **each test must still reset mappings and the request journal**; context caching does not reset WireMock state.

**Important:** nothing guarantees all test classes share a single context; `@ActiveProfiles`, `@TestPropertySource`, `@MockitoBean`, `@Import`, and other context customizers create separate cache keys. Standardize shared test configurations if context reuse is a goal.

## 15. ResetAll vs. resetRequests: a practical example

A test with two consecutive phases:

~~~java
// Snippet inside a @Test with a running WireMockServer STUB.
STUB.stubFor(
        get(urlEqualTo("/heartbeat"))
                .willReturn(aResponse().withStatus(200))
);

// Phase A: sent 3 requests.
STUB.resetRequests();

// Phase B: /heartbeat mappings remain active;
// request verification counts only requests after resetRequests.
~~~

Use `resetRequests()` when keeping stub mappings across phases **of the same scenario** while counting requests within one phase. Whenever the goal is **ensuring test method B inherits no expectations from A**, `resetAll()` is the right choice.

### Resetting via the Admin API

WireMock exposes Admin endpoints:

| HTTP to WireMock Admin API | Behavior |
| --- | --- |
| `POST /__admin/reset` | Resets stub mappings + request journal |
| `DELETE /__admin/requests` | Clears request journal |
| `DELETE /__admin/mappings` | Deletes mappings |
| `POST /__admin/scenarios/reset` | Resets scenario states to initial state |
| `POST /__admin/mappings/reset` | Restores default file-based mappings |

Use these endpoints when the stub runs outside the JVM (e.g., Docker or a remote test stub). For in-JVM Java `WireMockServer`, calling instance methods directly is simpler and avoids admin port/path mistakes.

When resetting file-based mappings, distinguish `resetAll` (clears mappings) from `resetToDefaultMappings` (restores defaults) so you do not accidentally wipe shared fixture files used by the suite. Never reset a shared server while another parallel suite is actively using it.

## 16. Scenario state: "first call differs from second call" expectations

WireMock supports stateful behavior via `inScenario(...)`, `whenScenarioStateIs(...)`, and `willSetStateTo(...)`. Use it when mocking a progressing upstream workflow:

~~~text
GET /jobs/42 call 1 -> 202 Accepted, state=RUNNING
GET /jobs/42 call 2 -> 200 OK, state=COMPLETED
~~~

If you skip resetting **scenario state** between tests, test B could start in `COMPLETED` when expecting `STARTED`.

Illustrative DSL snippet:

~~~java
STUB.stubFor(
        get(urlEqualTo("/jobs/42"))
                .inScenario("job-flow")
                .whenScenarioStateIs("Started")
                .willSetStateTo("RUNNING")
                .willReturn(aResponse().withStatus(202))
);

STUB.stubFor(
        get(urlEqualTo("/jobs/42"))
                .inScenario("job-flow")
                .whenScenarioStateIs("RUNNING")
                .willReturn(aResponse().withStatus(200))
);
~~~

This is an **illustrative snippet** inside a test holding `STUB` and imports. Sequential requests to `/jobs/42` receive scenario responses when no concurrent races intervene. After the test, call `resetAll()` or explicitly reset scenarios. When testing retries/backoff, **never** rely on arbitrary `Thread.sleep`; inject a `Clock`/scheduler or use bounded Awaitility/test-specific timing strategies where appropriate.

**Never treat a stateful stub as the source of truth for real workflow semantics**: it merely drives the client through expected branches. Partner state machines must be verified via dedicated contract/integration tests.

## 17. Timeouts, slow responses, and network faults

Once the HTTP client opens real TCP sockets to WireMock, you can simulate:

- Returning `503` or `429` to verify retry policies.
- Returning invalid-schema JSON to verify deserialization failures.
- Delaying responses to verify read timeouts.
- Faults/connection resets to verify transport errors.
- Missing or altered headers to verify robust parsing.
- Query parameters/encoding with Unicode or special characters.

WireMock delay example:

~~~java
STUB.stubFor(
        get(urlEqualTo("/slow"))
                .willReturn(
                        aResponse()
                                .withStatus(200)
                                .withFixedDelay(500)
                )
);
~~~

This is an illustrative snippet. If the app configures a **100 ms read timeout**, requests to `/slow` should time out. Never copy this verbatim and claim timeout tests pass without configuring `RestClient`'s request factory and asserting the right exception type. Apache HttpClient, JDK HttpClient, and `SimpleClientHttpRequestFactory` differ in timeout/exception behavior.

Good timeout tests configure timeouts that are **explicit, short, and given stable margins**, assert the right exception, and avoid inflating CI latency. Delayed integration tests should not run for tens of seconds just to verify mapping logic.

### HTTPS and certificates

`dynamicHttpsPort()` merely opens an HTTPS endpoint; the Java HTTP client must trust the certificate. Never disable certificate verification globally in production just to turn tests green. Provision a dedicated test truststore/SSL config, or use HTTP loopback when TLS is not under test.

### Unmatched requests returning 404 can be dangerous

A `WireMockServer` returns 404 by default for unmapped paths. If the service also maps 404 to business "not found," a mistyped URL can return `Optional.empty()` and pass silently. Always **verify method, URL, headers, expected counts**, and use `WireMockExtension`'s unmatched-request detection where possible. With a manual server, inspect the unmatched request journal to catch missing mappings. Never write a 404 test without explicitly stubbing the 404.

## 18. Parallel execution and resets: race risks across tests

When two tests share one `WireMockServer` in parallel:

~~~text
Test A: stub GET /products/A -> 200
Test B: resetAll()
Test A: calls /products/A -> 404 (mapping wiped by B)
Test B: stub GET /products/B -> 503
Test A: verify(1, GET /products/A) -> journal reset, FAIL
~~~

**`resetAll()` is not thread-local.** It wipes **the entire server instance's state**. To run in parallel safely, choose one of these strategies:

1. **Give every test method its own `WireMockServer`**, using an instance extension or manual `@BeforeEach start` + `@AfterEach stop`, building clients with each server's base URL.
2. When sharing one server per class, keep JUnit methods in that class **sequential**.
3. Give each test class its own Spring `ApplicationContext`, or use a Spring-managed server bean with distinct data/endpoint namespaces and **never reset the whole server while another test uses it**.
4. Across multiple Gradle forks or CI shards, let each JVM/server bind a **dynamic port** and avoid shared remote stubs with global resets.
5. If servers cannot be isolated, serialize tests that invoke global resets; JUnit's `@ResourceLock` coordinates only inside one JVM/JUnit engine—**not across separate processes**.

`@Execution(SAME_THREAD)` or `junit.jupiter.execution.parallel.mode.default=same_thread` keeps methods sequential inside a class under certain configs; check class-level parallelism settings too. Never assume `@BeforeEach`/`@AfterEach` alone is safe when tests run concurrently against one server.

### Background requests polluting the journal

If a service uses retries or `@Async`, it can fire a request *after* the test body ends—right as `@AfterEach` resets the server. That makes verification flaky or pollutes the next test's journal. Tests must **await completion** of futures/tasks, stop schedulers cleanly, and clean up only once zero requests remain in flight.

For client retries/backoff, write expectations covering total request counts and bounded waiting; never rely on guesswork sleeps or test-class execution order.

## 19. Avoid global static WireMock.configureFor with multiple stub servers

WireMock has a static client DSL:

~~~java
configureFor("localhost", STUB.port());
stubFor(get("/ping").willReturn(ok()));
~~~

This snippet assumes `STUB` and WireMock static imports. It mutates the **static WireMock client** configuration used by static helpers, easily mixing up servers when two suites run concurrently.

In the main sample, we call:

~~~java
STUB.stubFor(
        get(urlEqualTo("/ping"))
                .willReturn(aResponse().withStatus(200))
);
STUB.verify(
        1,
        getRequestedFor(urlEqualTo("/ping"))
);
~~~

The second call is valid only after the request ran. Instance methods explicitly target the right server object and eliminate global state. With two upstreams, keep **two `WireMockServer` instances** and stub against each instance directly.

Never call static `WireMock.reset()` assuming it resets every server in the JVM; it only affects whichever instance the static DSL currently targets.

## 20. Comparison with MockRestServiceServer in @RestClientTest

If you **do not need a dynamic port or real TCP** and only want to verify Spring `RestClient` builds the right request and decodes statuses/bodies, `@RestClientTest` can be lighter:

~~~java
@RestClientTest(PartnerCatalogClient.class)
@TestPropertySource(properties = {
        "partner.catalog.base-url=http://partner.example.invalid",
        "partner.catalog.client-name=spring-demo"
})
class PartnerClientSliceExample {

    @Autowired
    PartnerCatalogClient client;

    @Autowired
    MockRestServiceServer mockServer;

    @BeforeEach
    void resetExpectations() {
        mockServer.reset();
    }

    @Test
    void callsExpectedEndpoint() {
        mockServer.expect(
                requestTo(
                        "http://partner.example.invalid/external/products/SKU-7"
                )
        ).andRespond(
                withSuccess(
                        """
                        {"sku":"SKU-7","title":"Notebook","quantity":4}
                        """,
                        MediaType.APPLICATION_JSON
                )
        );

        assertThat(client.find("SKU-7").orElseThrow().title())
                .isEqualTo("Notebook");
        mockServer.verify();
    }

    @AfterEach
    void cleanup() {
        mockServer.reset();
    }
}
~~~

This is an **illustrative class** named `PartnerClientSliceExample`; it requires Spring Boot test auto-config imports, `@TestPropertySource`, Spring `MockRestServiceServer`, `MediaType`, and JUnit/AssertJ, so **do not treat this snippet as a standalone file in the main project**. The example illustrates clearly:

- `mockServer.expect(...)` defines an **expectation**.
- `mockServer.verify()` confirms expectations were met.
- `mockServer.reset()` clears expectations and recorded requests.
- **No listening port**: the client's request factory is swapped for mock infrastructure.

On Boot 3.5, `@RestClientTest` is imported from `org.springframework.boot.test.autoconfigure.web.client.RestClientTest`; Boot 4.x moves test modules/packages, so check release docs. Do not confuse `MockRestServiceServer.reset()` with `WireMockServer.resetAll()`, even though both serve isolation.

Spring Framework recommends mock web servers when testing realistic transport-layer and network behavior, while `MockRestServiceServer` remains valuable for lightweight client slice unit/integration tests.

## 21. What if you use OkHttp MockWebServer instead of WireMock?

OkHttp `MockWebServer` also binds ephemeral ports automatically, enqueues responses, and exposes `RecordedRequest` to verify path, headers, and bodies.

Flow:

~~~text
MockWebServer.start() -> read server.url("/")
        |
        v
HTTP client uses new baseUrl
        |
        v
server.enqueue(MockResponse)
        |
        v
client calls -> server.takeRequest(timeout) -> assert
        |
        v
server.shutdown()
~~~

With OkHttp `MockWebServer`, responses are normally enqueued sequentially; to reset expectations cleanly, **create a fresh server per test** and shut it down rather than assuming a WireMock-style `resetAll()`. Pick the tool matching your needs: WireMock shines at request matching, scenarios, verification, and its Admin API; `MockWebServer` offers a simple response queue and recorded requests.

Never "port" a test between the two frameworks merely by renaming classes; their lifecycles, request recording, and reset semantics differ.

## 22. Common troubleshooting table

| Symptom | Likely cause | Check/fix |
| --- | --- | --- |
| `Address already in use` | Hardcoded `8080/9090` | `wireMockConfig().dynamicPort()` |
| `Connection refused` creating client | Read URL before server start, or server already stopped | Start before property resolution; align lifecycles |
| Client calls real production/staging | Forgot to override base URL in test | `@DynamicPropertySource` + assert injected URL |
| Stub registered yet request gets 404 | Wrong path/header/query, or client hit another server | Print unmatched requests; verify URL and headers |
| First test passes, next test fails | Mappings/journal not reset | `resetAll()` in lifecycle or `WireMockExtension` auto-reset |
| `verify(1, ...)` sees count 2 | Journal retained request from earlier test | Reset request journal before each method |
| Old default stub still matches after reset | File-based default mappings or `resetToDefault` semantics | Distinguish `resetAll` vs. default mappings |
| Scenario starts in stale state | Scenarios not reset | `resetScenarios()`/`resetAll()` via right owner |
| `@AfterAll` stopped server, next Spring class hits old URL | Cached `ApplicationContext` outlived server | `@DirtiesContext` or Spring-managed server bean |
| `@Value` gets literal placeholder | Dynamic property not registered or wrong key | Check property key and static registry method |
| `@DynamicPropertySource` on non-static method | Invalid Spring API contract | Must be `static` accepting `DynamicPropertyRegistry` |
| JUnit extension fails on unmatched request | Missing stub or wrong URL | Fix expectation; do not disable fail-on-unmatched prematurely |
| 404 test passes despite mistyped path | WireMock default 404 treated as business result | Register explicit 404 stub + verify request |
| Parallel tests lose mappings | One test calls `resetAll` on shared server | Isolate server/method, serialize, or namespace |
| Requests arrive after `@AfterEach` | Unfinished retry/async work | Await request completion before reset |
| Flaky timeout test | Unconfigured client timeout or tight delay margin | Pin request factory/timeouts with sufficient margin |
| SSL handshake fails | Test certificate untrusted | Configure truststore/test SSL |
| `MockRestServiceServer` has no port | Client-side mock request factory | Use WireMock/MockWebServer for TCP |
| JSON body deserialization fails | Wrong `Content-Type`/schema/record fields | Return proper JSON response/headers in test |
| JVM exits while Docker stub stays alive | External process lifecycle | Clean up via resource owner, not just `@AfterEach` |
| Port 0 logged in application logs | Config read before start | Query `port()` only after `start()` |

**Never fix every failure with `Thread.sleep(1000)`.** Each symptom points to a specific cause: lifecycle/binding, property wiring, request matching, transactions/async, or network behavior. Fix the root cause and add an assertion proving it stays fixed.

## 23. QA checklist before calling tests isolated

- [ ] Does the production HTTP client accept base URL via config/constructor rather than hardcoding a host?
- [ ] Does the stub start on a **dynamic port** instead of fixed 8080/9090?
- [ ] Is `start()` called before the client resolves its base URL?
- [ ] In Spring tests, does the URL use `@DynamicPropertySource`/`DynamicPropertyRegistrar` at the right lifecycle phase?
- [ ] Is there an assertion confirming the client points to the test stub URL rather than production?
- [ ] Do per-test stubs specify **method/path/headers/body** accurately without overly broad wildcards?
- [ ] Is `verify(expectedCount, ...)` called after the request, not just response assertions?
- [ ] Are intended 404s stubbed explicitly to prevent tests passing via default unmatched 404s?
- [ ] Are 5xx, malformed JSON, and timeouts tested per business risk?
- [ ] Are mappings and the request journal reset before/between methods?
- [ ] If using scenarios, is state reset so the next test starts at `STARTED`?
- [ ] Does `@AfterEach` clean up even when assertions fail normally?
- [ ] Does the server stop in `@AfterAll` or via JUnit extension/Spring context without two owners stopping the same instance?
- [ ] Is WireMock static client state avoided when multiple stub servers exist?
- [ ] Do you prevent reusing cached Spring HTTP clients after a class-scoped stub server stops?
- [ ] Do parallel tests avoid resetting a server another test is actively calling?
- [ ] Do retries and async requests finish before verification, reset, or stop?
- [ ] Are port mappings, networking, and TLS scoped accurately without exposing admin APIs publicly?
- [ ] Is test data independent of JUnit method execution order?
- [ ] Does the build pin consistent WireMock/Spring Boot versions without mixing v4 beta APIs into v3.x?
- [ ] Have you distinguished `MockRestServiceServer` (no TCP) from WireMock/MockWebServer (real HTTP)?
- [ ] Are JUnit run commands and expected outcomes documented accurately without claiming execution when only reviewing code?

## 24. Running tests, expected outcome, and summary

With JDK 17+, Gradle Wrapper, and dependency download access:

~~~bash
./gradlew test --tests "com.example.stubhttp.PartnerCatalogClientIntegrationTest"
./gradlew test --tests "com.example.stubhttp.PartnerCatalogClientExtensionTest"
~~~

On Windows PowerShell:

~~~powershell
.\gradlew.bat test --tests "com.example.stubhttp.PartnerCatalogClientIntegrationTest"
.\gradlew.bat test --tests "com.example.stubhttp.PartnerCatalogClientExtensionTest"
~~~

The project has **5 JUnit methods** in the Spring integration test and **2 JUnit methods** in the WireMock Jupiter extension test—**7 total**. When Spring Boot 3.5 / JDK 17 / WireMock 3.13.2 match and no environment issue interferes, expected behavior is:

~~~text
Dynamic URL:     http://localhost:<OS-assigned port>
200 matched:     SKU-7 / Notebook / quantity=4; GET count=1
404 explicit:    Optional.empty(); GET count=1
503 explicit:    ServiceUnavailable; GET count=1
resetAll():      200 mapping cleared, old request log cleared
AfterEach:       zero expectations/request history remaining in stub
AfterAll:        WireMockServer stopped
~~~

These are **expected data/outcomes derived from the sample code**, **not live stdout**. There is no `System.out.println` in the code; actual ports, Gradle/JUnit logs, and stack traces vary by environment. The lesson was reviewed for syntax, APIs, and logic against documentation; running Gradle/JUnit for real still requires a Java/Gradle environment.

**Conclusion:** A stub server only makes tests reliable when **the dynamic URL reaches the client before construction**, **mappings/request journals/scenarios reset at the proper scope**, and **the server is stopped by a single lifecycle owner**. The WireMock Jupiter extension reduces boilerplate, though with Spring context caching you must align client and server lifetimes. Under parallel execution, calling `resetAll()` on a shared server breaks concurrent tests—making isolation a core requirement.

### Official references

- [WireMock 3.x — JUnit 5/Jupiter extension, dynamic port, automatic reset](https://wiremock.org/docs/junit-jupiter/)
- [WireMock 3.x — Java configuration and dynamicPort](https://wiremock.org/docs/configuration/)
- [WireMock 3.x — Plain Java WireMockServer start/stop](https://wiremock.org/docs/java-usage/)
- [WireMock 3.x — Stubbing, default 404, and reset](https://wiremock.org/docs/stubbing/)
- [WireMock 3.x — Verifying and request journal](https://wiremock.org/docs/verifying/)
- [WireMock 3.x — Scenario states and reset](https://wiremock.org/docs/stateful-behaviour/)
- [WireMock — Download/install, 3.13.2 dependencies](https://wiremock.org/docs/download-and-installation/)
- [Spring Framework — DynamicPropertySource and DynamicPropertyRegistrar](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/dynamic-property-sources.html)
- [Spring Framework — HTTP client testing / MockRestServiceServer](https://docs.spring.io/spring-framework/reference/testing/spring-mvc-test-client.html)
- [Spring Boot 3.5 — Testing Spring Boot Applications / RestClientTest](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html)
- [Spring Framework — Context caching / DirtiesContext](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/caching.html)
