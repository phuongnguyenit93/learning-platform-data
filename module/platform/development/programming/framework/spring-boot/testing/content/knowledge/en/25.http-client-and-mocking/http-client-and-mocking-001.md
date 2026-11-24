# Choosing the Mocking Boundary When an Application Calls an External HTTP Service

## 1. The problem: where do you mock to actually test what needs testing?

A Spring Boot application typically does not only **receive** HTTP requests. Within the same business flow, it may also **make outbound calls**: shipping quote services, payments, authentication, geolocation, email, inventory management, or partner REST APIs. When writing tests, we must decide where to **place the test double boundary**.

Take the checkout flow, for example:

```text
                  Request from user
                          │
                          ▼
                 CheckoutController
                          │
                          ▼
                 CheckoutPriceService
                          │
                          ▼
                   ShippingQuotePort
                          │
                          ▼
                HttpShippingQuoteAdapter
                          │
                          ▼
                  Spring RestClient
                          │
                          ▼
                  TCP/TLS/HTTP transport
                          │
                          ▼
                  Carrier API
```

If you mock `ShippingQuotePort`, the checkout test is fast and has no network dependency. However, **it does not test** the URL, headers, JSON, status handling, HTTP client configuration, or whether a request is actually sent.

If you mock directly beneath `RestClient` using `MockRestServiceServer`, you test most of the HTTP request/response structure and adapter logic, but **you do not test** sockets, DNS, TLS handshakes, connection pooling, proxies, or the real HTTP stack's read timeout.

If you run an HTTP stub server on `127.0.0.1`, the code goes through the real HTTP client and real sockets, yet **it still does not prove** that the production partner actually serves the expected contract, that the production network routes properly, or that the real TLS certificate is valid.

If you connect to a partner's sandbox, you gain the ability to detect contract/deployment changes, but tests are slower, require credentials, struggle to reproduce faults like connection reset or 429, and should not run on every build.

**Core question of this lesson:** you must identify *the risk you need to detect and what you want to keep real*, and only then pick the appropriate seam/mock/stub. There is no single best mocking layer for every test.

### Learning objectives

After this lesson, you will be able to:

1. Distinguish **mocking at a domain port**, **mocking the HTTP request factory**, **an HTTP stub server**, **contract tests**, and **sandbox tests**.
2. Pick the smallest boundary that still **keeps the behavior that could break**.
3. Structure Spring code using **ports and adapters** so business tests do not need to know about HTTP.
4. Test `RestClient` on Spring Boot 3.x with `@RestClientTest` and `MockRestServiceServer`; understand exactly what they do not test.
5. Test outbound HTTP with a stub server over **real sockets** and `@DynamicPropertySource` providing a dynamic base URL/port.
6. Distinguish `MockMvc`/`WebTestClient` for **inbound endpoints** from how you stub **outbound providers**.
7. Handle 4xx/5xx statuses, null bodies, malformed JSON, headers, transport errors, retry/timeout/circuit breakers, authentication, and idempotency at the right scope.
8. Use Java 17+, Spring Boot 3.x, JUnit Jupiter, Mockito, and the JDK HTTP server to build a complete example with **13 test methods** across three levels.
9. Avoid "false green" tests caused by mocking too deeply, configuring the client differently from production, or accidentally hitting the internet.
10. Have a decision checklist when integrating a new partner or diagnosing a flaky integration test.

**Runnable example scope:** Java 17+, Spring Boot **3.2–3.5**, Spring Framework 6.1+, Spring MVC/starter-web, `RestClient`, and JUnit Jupiter. This guide distinguishes between Boot 3.0/3.1, Boot 4.x, `RestTemplate`, `WebClient`, and HTTP interfaces; other versions or clients must adjust APIs and test setups accordingly.

## 2. Clearly defining the "test double boundary"

Here, a **boundary** is the point where we replace a real component with an object or service controlled by the test. The **higher** the boundary in the architecture, the faster and more isolated the test—but the more infrastructure it skips; the **lower** the boundary, the more real behavior we retain, though tests consume more resources and are harder to control.

### 2.1. A five-level map

| Level | Component replaced | How much stays real? | What bugs does it mainly catch? | What does it fail to prove? |
|---|---|---|---|---|
| **A. Port mock** | `ShippingQuotePort` or gateway interface | Business/service/aggregation above the port | Business branches, validation, not calling the provider at the wrong time | URL, JSON, headers, HTTP statuses, timeouts |
| **B. Client mock** | Request factory/HTTP exchange inside `RestClient` or `RestTemplate` | Adapter + client request building + message conversion | Path/query/header/body, 2xx/4xx/5xx, response mapping | Real DNS/socket/TLS/redirect/connection behavior |
| **C. Local HTTP stub** | External endpoint on loopback/ephemeral port | Adapter + HTTP library + local TCP + HTTP wire | URI encoding, real headers, serialization, partial transport | Partner's production contract/certificates/network |
| **D. Contract verification** | Independent provider/consumer contract, via stub or verifier | Schema and semantic compatibility per contract | Field renames, required/optional fields, status/body drift | Full deployment path/real latency |
| **E. Provider sandbox/staging** | Little or no mocking on the provider side | Client + permitted network/sandbox + deployed provider | Real credentials integration, routing, version/behavior | That production matches sandbox identically or faults reproduce reliably |

**"Level B" and "Level C" are not two different names for the same tool.** In Spring, `MockRestServiceServer` installs a fake request factory; **it does not open a real HTTP server**. WireMock or OkHttp MockWebServer can open an HTTP server, receive requests over sockets, and return scripted responses.

### 2.2. Mock, stub, fake, spy, and contract are not synonyms

- **Stub:** provides controlled answers, such as `GET /quotes/70000` returning JSON 200.
- **Mock:** in addition to answering, verifies invocations/interactions, for example calling `ShippingQuotePort.quote("70000")` exactly once.
- **Fake:** a simplified working implementation used in tests, such as an in-memory catalogue computing shipping fees by formula.
- **Spy:** wraps or enables observing a real method or part of a real method; easily causes unintended side effects if you spy on a real HTTP client.
- **Contract test:** verifies a request/response agreement between consumer and provider; may combine with a stub, but is not merely a mocked JSON file.
- **Sandbox test:** calls a permitted provider deployment; not a pure test double.

Tool names matter less than **the code path still executed**. For instance, a `@MockBean`/`@MockitoBean` replacing the entire `HttpShippingQuoteAdapter` only tests logic above the adapter, even if the test class is named "HTTP integration test".

### 2.3. Golden rule

> **Mock right at the boundary of what the test is not responsible for, while keeping every risky component the test must detect real.**

If the goal is the checkout formula, mock the port. If the goal is how the adapter builds URLs and maps 503 to a domain exception, keep the adapter real and fake the HTTP layer. If the goal is client handling of connection resets, proxies/TLS, use an HTTP-level/transport stub or the corresponding infrastructure test; do not use Mockito to pretend you tested the network.

## 3. How to choose the boundary by test question

### 3.1. A pragmatic decision tree

```text
What do you need to prove?
│
├─ Business logic when the provider returns result X?
│    └─ Mock/fake domain port (A)
│
├─ Adapter sends the right method/URL/header/body, parses JSON, and maps statuses?
│    └─ @RestClientTest + MockRestServiceServer (B)
│
├─ How the real HTTP client handles networking/encoding/connections?
│    └─ Local HTTP stub (C)
│
├─ Do provider and consumer agree on the contract/schema?
│    └─ Consumer-driven/provider contract tests (D)
│
└─ Actually reaching an authorized provider sandbox with valid credentials?
     └─ Sandbox/staging smoke test separated from unit CI (E)
```

When multiple answers matter, **use multiple thin test layers** instead of forcing one giant test to do everything. For example, 20 unit tests for business scenarios, 5 slice tests for the adapter, 3 local HTTP tests for the wire, a few provider contract tests, and a scheduled smoke test.

### 3.2. Scenario matrix

| Scenario to prove | Better-suited boundary | Key assertion |
|---|---|---|
| 25,000 cents shipping fee is added to the cart | Port mock | Total price, port invocation count |
| Negative cart is rejected before calling the provider | Port mock | Exception + `verifyNoInteractions` |
| Endpoint is `/api/quotes/{postalCode}` | Client mock or local stub | HTTP method, full URI, path variable |
| Header `Accept: application/json` is present | Client mock; local stub confirms wire | Exact header |
| JSON field `feeCents` maps to Java `long` | Client mock with real Jackson | DTO values |
| HTTP 503 maps to a domain exception | Client mock and/or local stub | Status mapping, cause |
| Empty 200 body | Client mock | No null dereference or fallback per contract |
| Socket refused, connection reset, read timeout | HTTP stub/fault injection | Error classification, timeout/cancel budget |
| Retries the exact count, no 4xx retry per policy | Stateful stub + real retry | Request count and outcome |
| OAuth credential is attached properly | Client mock + auth config; sandbox if needed | Authorization header (without leaking secret) |
| TLS certificate, proxy, DNS fail | Transport/infrastructure test | Actual handshake, trust/proxy behavior |
| Provider renames a JSON field | Consumer/provider contract | Schema compatibility |
| Real Spring service uses the right base URL/profile | Full-context local stub | `@DynamicPropertySource` + bean wiring |
| Inbound Controller HTTP status and outbound fallback | `MockMvc` or real inbound HTTP with outbound stub | API contract and outbound call |
| Provider sandbox has deployed a new version | Sandbox smoke | Real version-specific behavior, cleanup |
| No network allowed in unit tests | Port/mock factory + network guard | Test fails on unexpected outbound connection |

### 3.3. Choosing the boundary by regression type

Some regressions **cannot** be caught at too high a level:

- Changing `.uri("/quotes/{id}", id)` to `.uri("/quote/{id}", id)`: a port mock has no idea.
- Switching from a Boot pre-configured `RestClient.Builder` to `RestClient.create()`: a port-mock test has no idea; even a client-mock may not attach to the new instance.
- Changing the HTTP client implementation causing connection reuse/read timeout issues: a fake request factory does not test transport.
- The provider adds a required field or changes an enum: a stale manual stub keeps returning the old schema; contract verification is what can detect drift if updated/verified together.
- Accidentally calling a staging host with a production token: only config/security boundary checks catch this; never write a live test hitting production.

**Do not push every test to level C/E.** Large test counts and network dependencies make builds slow and flaky. Instead, pick a balanced "test pyramid" aligned with risk.

## 4. Designing outbound HTTP for a stable seam

### 4.1. Ports-and-adapters keeps business tests framework-free

You should separate:

```text
CheckoutPriceService
   └── ShippingQuotePort (domain interface)
           └── HttpShippingQuoteAdapter (production)
                   └── RestClient (transport)
                           └── external provider
```

Implications:

- Business logic receives a **domain abstraction** (`ShippingQuotePort`), not `RestClient` or a URL.
- The adapter owns **HTTP-specific concerns**: URL, HTTP headers, JSON mapping, statuses, and I/O exception translation.
- Configuration injects the base URL from Spring Environment; tests can swap it for a local stub.
- Business unit tests mock the port, while the adapter has its own tests at level B/C.
- You can swap `RestClient` for `WebClient` without changing the business interface, provided domain semantics remain unchanged.

**Avoid** splitting at an interface that merely wraps `RestClient.get()`. The interface should speak the domain's language: `quote(postalCode)`, `authorizePayment(...)`, `reserveStock(...)`.

### 4.2. Do not create a "hidden" HTTP client inside a method

Anti-pattern:

```java
public ShippingQuote quote(String postalCode) {
    RestClient client = RestClient.create();
    return client.get()
            .uri("https://provider.example/api/quotes/{code}", postalCode)
            .retrieve()
            .body(ShippingQuote.class);
}
```

This is an **anti-pattern snippet**, assuming imports and the `ShippingQuote` type exist. This approach hard-wires logic to a manually created instance and URL; `@RestClientTest` cannot guarantee the mock request factory is attached to that instance. Moreover, a freshly created client may bypass Boot customizers/SSL/auth/timeouts defined through the injected builder.

In Spring Boot 3.x, Boot configures a `RestClient.Builder`: **inject the builder** and build the client in the adapter constructor. That is how the sample in section 7 does it.

### 4.3. What configuration must cross the seam?

For outbound calls, at minimum there should be a configuration path for:

- Base URL/domain/port and path prefix.
- Connect/read/overall timeouts appropriate for the client library.
- TLS trust configuration, and mTLS if required.
- Authentication (API key/OAuth) and safe secret injection.
- Content-Type/Accept, JSON/ObjectMapper.
- Retry/backoff, idempotency, rate limits, circuit breakers.
- Correlation ID/tracing, logging redaction.
- Proxy/DNS/connection pool if the environment requires them.

Not every setting needs its own bean. The key point is that **tests can swap the endpoint without changing production business logic**, and critical settings are tested at the layer where they actually take effect.

## 5. What MockRestServiceServer actually tests

### 5.1. Spring Boot 3.x @RestClientTest

According to the Spring Boot 3.5 documentation, `@RestClientTest(MyClient.class)`:

- creates a **slice context** focused on the selected REST client component;
- auto-configures appropriate JSON mapping;
- configures `RestTemplateBuilder` and `RestClient.Builder`;
- provides `MockRestServiceServer` bound to the configured client builder;
- does not scan every `@Component` or `@ConfigurationProperties` like `@SpringBootTest`.

For `RestClient.Builder`, URI expectations should write the **full URI**, e.g. `https://shipping.example.invalid/api/quotes/70000`. `RestTemplateBuilder.rootUri(...)` follows a different expectation rule; **do not apply RestTemplate rootUri syntax to RestClient.Builder**.

### 5.2. A request factory mock fakes underneath the adapter

A test:

```java
server.expect(requestTo(
        "https://shipping.example.invalid/api/quotes/70000"))
        .andExpect(method(HttpMethod.GET))
        .andRespond(withSuccess(
                """
                {"service":"STANDARD","feeCents":25000}
                """,
                MediaType.APPLICATION_JSON));

ShippingQuote quote = adapter.quote("70000");
server.verify();
```

is interpreted as follows:

1. The real adapter invokes the real `RestClient` with the code's URI/template/headers.
2. The client's HTTP request is checked against the expectation.
3. The mock request factory returns a fake HTTP response with status, headers, and body.
4. The client's message converter maps JSON into `ShippingQuote`.
5. The adapter applies validation/exception translation.
6. `verify()` confirms the expectations were satisfied.

However, **no socket is opened to `shipping.example.invalid`**. Do not conclude from this test that DNS, TLS, proxies, TCP retries, or connection pooling have been verified.

### 5.3. When is @RestClientTest sufficient?

Typically it suffices for:

- URI template expansion and query parameters.
- HTTP method and body format.
- Expected headers and media types.
- JSON serialization/deserialization using the test slice's mapper.
- Status mapping for 404, 429, 500, 503 under normal handling.
- Missing/empty/invalid responses handled by the converter/adapter.
- Request invocation count and conditional calls when expectations reflect logic.

Still, JSON mapping in a slice can differ from production if the application has customizers/modules outside the slice. When JSON contracts are complex, import the needed production configuration or add a **full-context local HTTP test** to verify effective bean wiring.

### 5.4. What can MockRestServiceServer never replace?

- Real DNS and TCP handshakes.
- TLS certificate/hostname validation, mTLS, proxy routing.
- Accurate simulation of read/connect timeouts and socket resets across all HTTP client libraries.
- Chunked encoding, malformed HTTP headers, response compression, transfer framing.
- Pool saturation, keep-alive reuse, connection eviction.
- Tests for packet fragmentation and low-level protocol edge cases.
- The provider's sandbox/production deployment itself.

`MockRestResponseCreators.withException(IOException)` can **simulate an I/O exception at the request factory**, which is very helpful for error-handling logic. Just never claim that test checked real socket timeouts of Apache HttpClient/JDK HttpClient/Reactor Netty.

## 6. Demo scenario: checkout fetching a shipping quote

Suppose a provider exposes this API:

```http
GET /api/quotes/70000 HTTP/1.1
Host: shipping.example.invalid
Accept: application/json
```

Returning:

```json
{
  "service": "STANDARD",
  "feeCents": 25000
}
```

Business contract:

- Input `postalCode` must contain exactly 5 ASCII digits.
- Shipping fee (`feeCents`) must be non-negative.
- If the provider returns 200 + valid body, the adapter returns `ShippingQuote`.
- If 200 + empty body, the adapter throws `ShippingProviderException`, **never returning null to the service**.
- If 2xx + negative fee, the adapter throws an exception because the data violates the contract.
- If 4xx/5xx, the adapter translates the status into a domain exception, preserving the technical cause.
- If an I/O failure occurs, the adapter translates it into a domain exception without confusing it with 404.
- Checkout adds `subtotalCents + feeCents` using `Math.addExact` so it never silently overflows.
- Negative subtotals are rejected **before calling the provider**.

**This is an illustrative contract**, not a real carrier API. `70000` and codes `99999`, `88888`, `77777` in tests are fixtures. The `.invalid` domain makes it explicit that client-mock tests **must not make real outbound internet connections**.

## 7. Complete Java 17+ / Spring Boot 3.x example

### 7.1. Dependencies

The project uses Spring Boot 3.2–3.5 and Java 17+; `spring-boot-starter-web` provides Spring MVC, `RestClient` on Spring Framework 6.1+, Jackson, and the Boot-managed `RestClient.Builder`. `spring-boot-starter-test` provides Spring Test, JUnit Jupiter, AssertJ, and Mockito.

**Gradle Groovy DSL** (dependencies/test task snippet assuming the project already has the Spring Boot plugin, repositories, BOM/dependency management, and Java 17 toolchain):

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
```

**Maven** (dependencies snippet in a project with an appropriate Spring Boot parent/BOM and Surefire/JDK):

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
```

This is **not** a complete `build.gradle` or `pom.xml`. No external HTTP mock server library is needed for example C: JDK 17 provides `com.sun.net.httpserver.HttpServer` to demonstrate loopback HTTP. For real projects needing advanced fault injection, WireMock/OkHttp MockWebServer/MockServer may be a better fit; section 11 explains why.

### 7.2. File tree

```text
src/
├── main/
│   ├── java/com/example/outbound/
│   │   ├── OutboundDemoApplication.java
│   │   ├── ShippingQuote.java
│   │   ├── ShippingQuotePort.java
│   │   ├── ShippingProviderException.java
│   │   ├── HttpShippingQuoteAdapter.java
│   │   └── CheckoutPriceService.java
│   └── resources/
│       └── application.properties
└── test/java/com/example/outbound/
    ├── CheckoutPriceServiceTest.java
    ├── HttpShippingQuoteAdapterSliceTest.java
    └── HttpShippingQuoteAdapterLoopbackTest.java
```

All tests sit under the same root package so Spring Boot finds `@SpringBootApplication`. The sample has no database, HTTP inbound controller, secrets, or external dependencies beyond starter web/test.

### 7.3. Entry point

**File `src/main/java/com/example/outbound/OutboundDemoApplication.java`:**

```java
package com.example.outbound;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OutboundDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(OutboundDemoApplication.class, args);
    }
}
```

### 7.4. Domain DTO and port

**File `src/main/java/com/example/outbound/ShippingQuote.java`:**

```java
package com.example.outbound;

public record ShippingQuote(
        String service,
        long feeCents
) {}
```

**File `src/main/java/com/example/outbound/ShippingQuotePort.java`:**

```java
package com.example.outbound;

public interface ShippingQuotePort {

    ShippingQuote quote(String postalCode);
}
```

The port contains no HTTP status, `RestClient`, or framework-specific classes. Those details belong to the adapter; business logic only needs a quote with cents and service level.

### 7.5. Domain exception that can preserve its cause

**File `src/main/java/com/example/outbound/ShippingProviderException.java`:**

```java
package com.example.outbound;

public class ShippingProviderException extends RuntimeException {

    public ShippingProviderException(String message) {
        super(message);
    }

    public ShippingProviderException(
            String message,
            Throwable cause) {
        super(message, cause);
    }
}
```

The adapter will not log raw response bodies or credentials when creating the exception. Storing the status code in the message is fine for the demo; in real production code you can use typed error codes, sanitized metadata, and tracing IDs.

### 7.6. Production HTTP adapter using Boot-managed RestClient.Builder

**File `src/main/java/com/example/outbound/HttpShippingQuoteAdapter.java`:**

```java
package com.example.outbound;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.client.ResourceAccessException;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientResponseException;

@Component
public class HttpShippingQuoteAdapter implements ShippingQuotePort {

    private final RestClient client;

    public HttpShippingQuoteAdapter(
            RestClient.Builder builder,
            @Value("${shipping.base-url}") String baseUrl) {

        this.client = builder.baseUrl(baseUrl).build();
    }

    @Override
    public ShippingQuote quote(String postalCode) {

        if (postalCode == null
                || !postalCode.matches("[0-9]{5}")) {
            throw new IllegalArgumentException(
                    "postalCode must contain exactly five digits");
        }

        try {
            ShippingQuote result = client.get()
                    .uri("/api/quotes/{postalCode}", postalCode)
                    .accept(MediaType.APPLICATION_JSON)
                    .retrieve()
                    .body(ShippingQuote.class);

            if (result == null) {
                throw new ShippingProviderException(
                        "Empty shipping quote");
            }

            if (result.feeCents() < 0) {
                throw new ShippingProviderException(
                        "Negative shipping fee");
            }

            return result;
        }
        catch (RestClientResponseException ex) {
            throw new ShippingProviderException(
                    "Provider HTTP "
                    + ex.getStatusCode().value(),
                    ex);
        }
        catch (ResourceAccessException ex) {
            throw new ShippingProviderException(
                    "Provider I/O failure",
                    ex);
        }
    }
}
```

**Notes on API and exception semantics:**

- `RestClient.Builder` is pre-configured by Spring Boot; the adapter builds a reusable client once rather than creating a new one per request.
- `@Value("${shipping.base-url}")` pulls the base URL from Environment. Unit/slice/live tests can replace the property without modifying the adapter.
- `.uri("/api/quotes/{postalCode}", postalCode)` supplies the path variable via URI template; since the example input is only 5 digits, encoding is unambiguous.
- `.accept(APPLICATION_JSON)` sets the request header that both mocks and local stubs can inspect.
- `.retrieve().body(ShippingQuote.class)` uses message converters to deserialize JSON.
- For typical 4xx/5xx responses, Spring Framework's `RestClient.retrieve()` throws a `RestClientResponseException` subtype; the adapter translates it into a domain error while preserving the cause.
- I/O communication failures may surface as `ResourceAccessException`; the adapter distinguishes them from HTTP responses that returned a status.
- Empty-body and negative-fee policies are checked **after** deserialization.
- The client configures no automatic retry in this sample. Do not expect a 503 to automatically produce multiple HTTP attempts.
- Malformed JSON may throw a conversion-related `RestClientException` that is not separately mapped by the sample code; if you need a typed domain exception for all malformed bodies, add specific logic/catch blocks and dedicated tests. Do not claim the sample standardizes every decoder error.

**Never** put a real URL or production credentials in tests. The demo project sets the default URL to `.invalid`; local HTTP tests substitute a loopback port via `@DynamicPropertySource`.

### 7.7. Business service using the port, unaware of HTTP

**File `src/main/java/com/example/outbound/CheckoutPriceService.java`:**

```java
package com.example.outbound;

import org.springframework.stereotype.Service;

@Service
public class CheckoutPriceService {

    private final ShippingQuotePort shipping;

    public CheckoutPriceService(ShippingQuotePort shipping) {
        this.shipping = shipping;
    }

    public long totalCents(
            long subtotalCents,
            String postalCode) {

        if (subtotalCents < 0) {
            throw new IllegalArgumentException(
                    "subtotalCents must be non-negative");
        }

        ShippingQuote quote = shipping.quote(postalCode);
        return Math.addExact(
                subtotalCents,
                quote.feeCents());
    }
}
```

The service owns the total calculation and business input validation. It knows nothing about `GET`, base URLs, headers, or JSON. Mocking at the port is enough when the goal is just the summation formula, call count, and exception branches.

`Math.addExact` throws `ArithmeticException` on overflow; the sample does not hide errors by casting `long` to `int`. Real monetary domains may require different currency/precision/decimal policies, but this illustrates the cost-addition principle.

### 7.8. Production configuration with safe sample defaults

**File `src/main/resources/application.properties`:**

```properties
shipping.base-url=https://shipping.example.invalid
```

The `.invalid` domain prevents readers from mistaking it for a production API. In a real application, the base URL is an environment-specific setting like `shipping.base-url` or a typed `@ConfigurationProperties`. Tests provide fake URLs via property overrides or a dynamic port.

If production config includes connection pools/timeouts/TLS/auth, keep the same client builder/customizer for local HTTP tests; in request-factory mock tests, **do not conclude** that those transport settings actually took effect.

## 8. Level A: unit testing business logic with Mockito, without starting Spring

**File `src/test/java/com/example/outbound/CheckoutPriceServiceTest.java`:**

```java
package com.example.outbound;

import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

class CheckoutPriceServiceTest {

    @Test
    void addsShippingFeeToSubtotal() {
        ShippingQuotePort port = mock(ShippingQuotePort.class);

        when(port.quote("70000"))
                .thenReturn(new ShippingQuote("STANDARD", 25_000));

        CheckoutPriceService service =
                new CheckoutPriceService(port);

        long total = service.totalCents(100_000, "70000");

        assertThat(total).isEqualTo(125_000L);
        verify(port).quote("70000");
    }

    @Test
    void rejectsNegativeSubtotalBeforeCallingProvider() {
        ShippingQuotePort port = mock(ShippingQuotePort.class);

        CheckoutPriceService service =
                new CheckoutPriceService(port);

        assertThatThrownBy(() ->
                service.totalCents(-1, "70000"))
                .isInstanceOf(IllegalArgumentException.class);

        verifyNoInteractions(port);
    }

    @Test
    void propagatesDomainFailureFromGateway() {
        ShippingQuotePort port = mock(ShippingQuotePort.class);

        when(port.quote("70000"))
                .thenThrow(new ShippingProviderException(
                        "Provider unavailable"));

        CheckoutPriceService service =
                new CheckoutPriceService(port);

        assertThatThrownBy(() ->
                service.totalCents(100_000, "70000"))
                .isInstanceOf(ShippingProviderException.class)
                .hasMessage("Provider unavailable");

        verify(port).quote("70000");
    }
}
```

**These are 3 complete JUnit Jupiter tests with no Spring ApplicationContext.**

The tests prove:

- Checkout computes the right total for a given quote.
- Negative subtotal input is rejected, and the port **is not called**.
- Business logic behaves deterministically when the port throws an exception.

They **do not prove the HTTP adapter works**. If you only have these three tests and a developer changes `GET /api/quotes/70000` to the wrong endpoint, the build can still stay green. That is not a flaw in unit tests; it is a **gap if you lack tests at levels B/C**.

### 8.1. When to use a fake instead of a mock

If the logic has many scenarios and you do not need to assert interaction counts, you can build an `InMemoryShippingQuotePort` returning fees from a `Map<String, ShippingQuote>`. This decouples tests from exact method call counts.

**However:** that fake must be clear that it does not simulate HTTP; never turn it into a "replica of the provider's algorithm" and treat it as contract truth when the provider changes policy.

### 8.2. Do you need @MockitoBean/@MockBean in unit tests?

No. Because the service is constructed manually via `new CheckoutPriceService(port)`, Mockito's `mock(ShippingQuotePort.class)` is enough. Avoiding Spring startup is faster and reduces context coupling.

When testing **Spring bean wiring** or a controller/service inside a Spring test context, you can override dependencies using `@MockitoBean` in Spring Framework 6.2 / Spring Boot 3.4+, or `@MockBean` in older Spring Boot 3 lines. These annotations differ in version and lifecycle; if you do not need a context, do not use bean overrides just to mock a Java interface.

## 9. Level B: @RestClientTest + MockRestServiceServer

This tests the **HTTP adapter**. We keep the production `HttpShippingQuoteAdapter`, Boot-managed `RestClient.Builder`, and JSON conversion real, while mocking the request factory. No socket is opened to the `.invalid` domain.

**File `src/test/java/com/example/outbound/HttpShippingQuoteAdapterSliceTest.java`:**

```java
package com.example.outbound;

import java.io.IOException;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.client.RestClientTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.test.web.client.MockRestServiceServer;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import static org.springframework.test.web.client.match.MockRestRequestMatchers.header;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.method;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;

import static org.springframework.test.web.client.response.MockRestResponseCreators.withException;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withServiceUnavailable;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;

@RestClientTest(
        value = HttpShippingQuoteAdapter.class,
        properties = "shipping.base-url=https://shipping.example.invalid"
)
class HttpShippingQuoteAdapterSliceTest {

    @Autowired
    HttpShippingQuoteAdapter adapter;

    @Autowired
    MockRestServiceServer server;

    @AfterEach
    void resetExpectationsForNextTest() {
        server.reset();
    }

    @Test
    void sendsCorrectMethodUrlAndAcceptAndReadsJson() {
        server.expect(requestTo(
                "https://shipping.example.invalid/api/quotes/70000"))
                .andExpect(method(HttpMethod.GET))
                .andExpect(header(
                        HttpHeaders.ACCEPT,
                        MediaType.APPLICATION_JSON_VALUE))
                .andRespond(withSuccess(
                        """
                        {
                          "service": "STANDARD",
                          "feeCents": 25000
                        }
                        """,
                        MediaType.APPLICATION_JSON));

        ShippingQuote quote = adapter.quote("70000");

        assertThat(quote).isEqualTo(
                new ShippingQuote("STANDARD", 25_000L));
        server.verify();
    }

    @Test
    void translatesHttp503IntoDomainException() {
        server.expect(requestTo(
                "https://shipping.example.invalid/api/quotes/99999"))
                .andRespond(withServiceUnavailable());

        assertThatThrownBy(() -> adapter.quote("99999"))
                .isInstanceOf(ShippingProviderException.class)
                .hasMessage("Provider HTTP 503");

        server.verify();
    }

    @Test
    void treatsEmptySuccessfulResponseAsContractError() {
        server.expect(requestTo(
                "https://shipping.example.invalid/api/quotes/88888"))
                .andRespond(withSuccess(
                        "",
                        MediaType.APPLICATION_JSON));

        assertThatThrownBy(() -> adapter.quote("88888"))
                .isInstanceOf(ShippingProviderException.class)
                .hasMessage("Empty shipping quote");

        server.verify();
    }

    @Test
    void rejectsNegativeFeeEvenWhenHttpStatusIs200() {
        server.expect(requestTo(
                "https://shipping.example.invalid/api/quotes/77777"))
                .andRespond(withSuccess(
                        """
                        {"service":"STANDARD","feeCents":-5}
                        """,
                        MediaType.APPLICATION_JSON));

        assertThatThrownBy(() -> adapter.quote("77777"))
                .isInstanceOf(ShippingProviderException.class)
                .hasMessage("Negative shipping fee");

        server.verify();
    }

    @Test
    void translatesMockedIoException() {
        server.expect(requestTo(
                "https://shipping.example.invalid/api/quotes/55555"))
                .andRespond(withException(
                        new IOException("simulated socket failure")));

        assertThatThrownBy(() -> adapter.quote("55555"))
                .isInstanceOf(ShippingProviderException.class)
                .hasMessage("Provider I/O failure")
                .hasCauseInstanceOf(
                        org.springframework.web.client
                                .ResourceAccessException.class);

        server.verify();
    }

    @Test
    void rejectsInvalidPostalCodeWithoutHttpRequest() {
        assertThatThrownBy(() ->
                adapter.quote("NOT-A-POSTAL-CODE"))
                .isInstanceOf(IllegalArgumentException.class);

        // No expectations registered;
        // test only passes if adapter sends no request.
        server.verify();
    }
}
```

**Expected:** 6 JUnit methods in this class pass on Spring Boot 3.2–3.5/Spring Framework matching the listed dependencies.

**Important check:** `RestClient.Builder` uses the full URI in `MockRestServiceServer.requestTo(...)`. If a test expectation only uses `"/api/quotes/70000"`, it may mismatch because the real request carries an absolute URL; the Spring Boot 3.5 documentation explicitly notes this difference between the `RestClient` builder and `RestTemplate` `rootUri`.

**Why `server.reset()` in `@AfterEach`?** The mock server stores expectations and request counts. Each test must be independent and not carry state into the next test. Each test calls `server.verify()` right after the operation under test, then `reset()` to prevent state leakage. When multiple `RestClient` instances/builders exist in one context, a single injected mock server may not cover all of them; check the corresponding customizer/bean.

### 9.1. Mocked IOException is not a transport test

The `translatesMockedIoException` test only produces an exception from the mock request factory; it tests the **exception translation branch**. It **does not** prove that the JDK/Apache client times out properly, closes sockets cleanly, or recovers pools after connection resets. To test those, use level C with a server capable of delaying/dropping connections, or dedicated network fault injection.

### 9.2. @RestClientTest loads only a slice

In the example, `CheckoutPriceService` is not under test in the slice, so it does not need to be scanned. `@RestClientTest(HttpShippingQuoteAdapter.class)` focuses on the adapter and REST client support. If the production adapter depends on a custom `@ConfigurationProperties` class, auth interceptor, or Jackson module outside the slice, bring that configuration into the test via the proper mechanism (such as `@EnableConfigurationProperties`/`@Import`). **Do not create a test-only client different from production** just to make the test pass.

## 10. Level C: real HTTP loopback with SpringBootTest and JDK HttpServer

This is an **HTTP integration test with a local provider stub**, not calling a production provider.

- The production client `HttpShippingQuoteAdapter` is not mocked.
- Spring Boot starts a **full non-web ApplicationContext** (no inbound server opened).
- A `com.sun.net.httpserver.HttpServer` listens on `127.0.0.1` and **port 0** so the OS picks a free port.
- `@DynamicPropertySource` supplies `shipping.base-url` with the stub's real address before the adapter is created.
- Calling the adapter goes through the real `RestClient` → real HTTP client request factory → loopback socket → stub.
- Tests verify happy path, HTTP 503, empty body, and HTTP 404.
- No extra WireMock/OkHttp dependency is required for this *minimal demonstration*. The JDK stub lacks the powerful fault-injection/pattern-matching utilities of dedicated tools.

**File `src/test/java/com/example/outbound/HttpShippingQuoteAdapterLoopbackTest.java`:**

```java
package com.example.outbound;

import java.io.IOException;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;

import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;

import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@SpringBootTest(
        classes = OutboundDemoApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE
)
class HttpShippingQuoteAdapterLoopbackTest {

    private static final HttpServer STUB = startStub();

    @DynamicPropertySource
    static void overrideOutboundBaseUrl(
            DynamicPropertyRegistry registry) {
        registry.add("shipping.base-url",
                () -> "http://127.0.0.1:"
                        + STUB.getAddress().getPort());
    }

    @Autowired
    HttpShippingQuoteAdapter adapter;

    private static HttpServer startStub() {
        try {
            HttpServer server = HttpServer.create(
                    new InetSocketAddress("127.0.0.1", 0), 0);

            server.createContext(
                    "/api/quotes/",
                    HttpShippingQuoteAdapterLoopbackTest::respond);

            server.start();
            return server;
        }
        catch (IOException ex) {
            throw new ExceptionInInitializerError(ex);
        }
    }

    private static void respond(HttpExchange exchange)
            throws IOException {

        String accept = exchange.getRequestHeaders()
                .getFirst("Accept");

        String path = exchange.getRequestURI().getPath();
        int status = 200;
        String body;

        if (!"GET".equals(exchange.getRequestMethod())) {
            status = 405;
            body = """
                    {"error":"method_not_allowed"}
                    """;
        }
        else if (accept == null
                || !accept.contains("application/json")) {
            status = 406;
            body = """
                    {"error":"not_acceptable"}
                    """;
        }
        else {
            switch (path) {
                case "/api/quotes/70000" ->
                    body = """
                            {
                              "service": "STANDARD",
                              "feeCents": 25000
                            }
                            """;

                case "/api/quotes/99999" -> {
                    status = 503;
                    body = """
                            {"error":"temporarily_unavailable"}
                            """;
                }

                case "/api/quotes/88888" ->
                    body = "";

                default -> {
                    status = 404;
                    body = """
                            {"error":"not_found"}
                            """;
                }
            }
        }

        exchange.getResponseHeaders().set(
                "Content-Type", "application/json");

        byte[] bytes = body.getBytes(StandardCharsets.UTF_8);

        if (bytes.length == 0) {
            exchange.sendResponseHeaders(status, -1);
            exchange.close();
            return;
        }

        exchange.sendResponseHeaders(status, bytes.length);

        try (OutputStream stream = exchange.getResponseBody()) {
            stream.write(bytes);
        }
    }

    @AfterAll
    static void stopStub() {
        STUB.stop(0);
    }

    @Test
    void usesActualHttpSocketForSuccessfulQuote() {
        ShippingQuote result = adapter.quote("70000");

        assertThat(result).isEqualTo(
                new ShippingQuote("STANDARD", 25_000L));
    }

    @Test
    void mapsRealHttp503Response() {
        assertThatThrownBy(() -> adapter.quote("99999"))
                .isInstanceOf(ShippingProviderException.class)
                .hasMessage("Provider HTTP 503");
    }

    @Test
    void handles200WithNoResponseBody() {
        assertThatThrownBy(() -> adapter.quote("88888"))
                .isInstanceOf(ShippingProviderException.class)
                .hasMessage("Empty shipping quote");
    }

    @Test
    void mapsRealHttp404Response() {
        assertThatThrownBy(() -> adapter.quote("12345"))
                .isInstanceOf(ShippingProviderException.class)
                .hasMessage("Provider HTTP 404");
    }
}
```

**Expected:** 4 test methods pass in a JDK 17+ full Spring Boot 3.x context per the sample. The total across the three classes in sections 8–10 is **3 + 6 + 4 = 13 JUnit test methods**.

### 10.1. Why pick port 0?

If you hardcode port 8089, 9999, or 9000, CI machines running parallel workers can hit `BindException: Address already in use`. Binding `new InetSocketAddress("127.0.0.1", 0)` lets the OS choose a free port, and `STUB.getAddress().getPort()` returns the actual port.

`@DynamicPropertySource` supplies that value to the Spring `Environment` **before Spring initializes the adapter**. It has high precedence in Spring TestContext, making it ideal for replacing the base URL declared in `application.properties`.

### 10.2. What is tested here?

- The code path of the production adapter and Spring-managed `RestClient.Builder`.
- The URI joined with the real base URL, method, and Accept header (the stub returns 405/406 if wrong).
- HTTP requests over a loopback socket.
- Response status, bytes, and `Content-Type` headers across the HTTP stack.
- Jackson conversion, status handling, and empty bodies.
- Full application bean wiring/active configuration (except the overridden base URL).

**Do not infer:**

- External domain DNS works; the test uses a loopback IP.
- The TLS trust chain is valid; the test uses unencrypted HTTP.
- Production proxy/VPN/firewall rules are correct.
- The provider contract has been confirmed by the provider.
- Connect/read timeouts, retries, or pool exhaustion behavior; the sample does not configure or exercise those scenarios.
- The application's inbound controller works; the context loads with `webEnvironment=NONE`.

### 10.3. Notes on mock HTTP server lifecycle

The sample initializes a static stub before TestContext resolves dynamic properties, then stops it in `@AfterAll`. In this test class, the stub serves sequential methods and holds no mutable expectations.

In large suites or parallel tests, manage the lifecycle carefully:

- Do not leave cached contexts pointing to a stopped server if multiple test classes share property configuration.
- Avoid sharing a mutable static stub across parallel tests.
- Use official JUnit extensions/lifecycle adapters from WireMock/MockWebServer when available.
- Do not write/modify global `System.setProperty("shipping.base-url", ...)` from multiple tests.
- Do not use fixed ports when multiple JVM/CI workers can run concurrently.
- If each test needs a fresh server, ensure the Spring context creates the client after the dynamic property is updated or uses a separate context; changing the server port after the `RestClient` bean is built **does not automatically update `RestClient`'s base URL**.

**Accurate statement:** a loopback HTTP stub is a real network **inside the test machine**; it is not the provider's real network and not an end-to-end production test.

## 11. When to use WireMock, MockWebServer, or MockServer instead of a JDK stub?

In real projects, a dedicated HTTP stub server is usually easier to use and more flexible than hand-writing a handler like in section 10.

### 11.1. WireMock

WireMock can:

- match HTTP method, URL/path/query, headers, and body;
- return 2xx/4xx/5xx codes and JSON payloads;
- record a request journal to verify call counts;
- return responses via stateful scenarios;
- simulate delays, faults, and templating depending on version/extensions;
- run as a standalone stub for component/integration tests.

It fits well when you want to test a complex provider API with many endpoints and scenarios without writing lots of `HttpServer.createContext` boilerplate.

**Warning:** WireMock stub files are not self-verified by the provider. If you hand-write JSON fixtures and fail to update them when the real API changes, tests can still pass falsely. Pair with contract verification or appropriate sandbox checks.

### 11.2. OkHttp MockWebServer

MockWebServer accepts real HTTP requests, lets you enqueue responses, inspect `RecordedRequest`, and supports many connection-behavior test cases. It often makes sense for testing a small HTTP client library or adapter.

Confirm artifact/package names for your version; OkHttp 4 and 5 differ in modules/APIs. **Do not copy imports from an old guide and assume they work on a new version**.

### 11.3. MockServer

MockServer provides expectation matching, request verification, and response customization; it can run as an embedded server or container. Pick it when the team has standardized on it or needs complex HTTP interaction logic.

### 11.4. Choosing by goal

| Need | Approach to consider |
|---|---|
| A simple JSON request, no socket needed | `MockRestServiceServer` |
| A few HTTP scenarios with sockets, no extra dependency | JDK `HttpServer` as in the sample |
| Many routes, headers, sequential responses, faults | WireMock/MockWebServer |
| Automatically verified consumer/provider contracts | Pact/Spring Cloud Contract per integration capability |
| Realistic TLS/proxy/latency/network fault simulation | Dedicated stub/proxy/network fault injection |
| Real verification against provider deployment | Sandbox smoke with credentials/quota/cleanup |
| Shared mocking across multiple teams using the same contract language | Versioned shared contract/stub artifact |

Choose the tool based on the **risk you must detect**, not the tool with the longest feature list.

## 12. WebClient, RestTemplate, HTTP interfaces, and WebTestClient

### 12.1. RestTemplate

`RestTemplate` is the traditional synchronous client. Spring Framework provides `MockRestServiceServer.bindTo(restTemplate)`; Spring Boot provides `RestTemplateBuilder`.

If the production client is built via `RestTemplateBuilder.rootUri(...)`, URI expectations in some Spring Boot slice tests may be written **relative** per the documentation; with `RestClient.Builder`, a full URI is required. Read the docs for your exact client/version and test `requestTo(...)` in practice rather than blindly copying expectations between the two APIs.

In particular, a `RestTemplate` created manually with `new RestTemplate()` may miss builder/customizer/SSL settings intended by the application. Inject the real production bean/builder at levels B/C.

### 12.2. WebClient

`WebClient` is Spring WebFlux's reactive/non-blocking client:

```java
Mono<ShippingQuote> quote = webClient.get()
        .uri("/api/quotes/{code}", "70000")
        .retrieve()
        .bodyToMono(ShippingQuote.class);
```

**Illustrative snippet**, requiring a `WebClient` bean and imports; not a standalone runnable file. Creating a `Mono` does not mean the HTTP request was sent: you must **subscribe** or use `StepVerifier`.

Spring Boot has `@WebClientTest` to slice-test WebClient-related components and inject `WebClient.Builder`. However, it is **not automatically equivalent** to a `MockRestServiceServer` for `RestClient`/`RestTemplate`. Options include:

- Mock `ExchangeFunction` or `ExchangeFilterFunction` to unit-test a small layer (recognizing it may skip network, codecs, or many filters).
- Use a MockWebServer/WireMock HTTP stub over sockets for outbound `WebClient`.
- Use `StepVerifier` with a fully composed Publisher; do not merely assert `Mono != null`.
- When testing timeout/cancellation/retry on Reactor Netty, use a network stub/fault injection close to the real mechanism.
- If code calls `subscribe()` ad-hoc inside a business method, tests struggle to observe completion or errors; return the Publisher and let the caller compose.

### 12.3. WebTestClient is easily confused

**`WebTestClient` is typically used to test a server application receiving requests** (Spring MVC/WebFlux), even though it is built on `WebClient`. It can bind to a controller, an application context, or a live server.

**Using `WebTestClient` to call an inbound controller does not automatically stub outbound HTTP calls made by that controller.** If the controller calls `WebClient`/`RestClient` to a partner, you still need a port mock (A) or an outbound provider stub (B/C).

For example:

```text
WebTestClient -> your application -> WebClient -> external provider
       ▲                                ▲
       │                                │
  inbound test                    outbound stub still needed
```

Similarly, `MockMvc` tests the inbound Servlet MVC chain; it does not automatically replace a remote REST API with a mock.

### 12.4. HTTP interfaces / @HttpExchange

Spring Framework supports declarative HTTP interfaces with `@HttpExchange` and proxies built from `RestClientAdapter` or `WebClientAdapter`. The boundary must still be chosen by the same principles:

- Mock the **domain interface** if only testing business logic.
- Verify the generated HTTP client's request mapping with an HTTP stub.
- Test status/serialization/transport according to the underlying adapter.
- Do not assume testing an interface method with Mockito proves the Spring HTTP proxy is right.

### 12.5. Important version differences

- Spring Boot **3.0/3.1**: `RestClient` (Spring Framework 6.1) does not exist yet or is not an option as in the sample. Use `RestTemplate` or `WebClient` per your stack/version; do not copy `@RestClientTest` + `RestClient.Builder` if the class is absent.
- Spring Boot **3.2–3.5**: `RestClient` and Boot-managed `RestClient.Builder` match the sample.
- Spring Framework **6.2** / Boot **3.4+** provides `@MockitoBean`; Boot's `@MockBean` in several Boot 3 lines has been deprecated and is being replaced. Pick the annotation matching your version and test override semantics.
- Spring Boot **4.x** reorganizes many test starters/modules/packages differently from Boot 3 and uses Spring Framework 7. Read Boot 4 reference docs/Javadocs to adjust imports and dependencies; **do not treat Boot 3 imports in the sample as immutable**.

## 13. Critical failure modes that must sit at the right boundary

### 13.1. HTTP statuses and response bodies

Do not only test 200. A provider can return:

- 201/202 when an operation is async or accepted, 204 with an empty body.
- 400 due to a malformed request schema.
- 401/403 due to credentials/scopes.
- 404 when a resource does not exist.
- 409 on conflict/duplicate idempotency key.
- 422 for business validation, per API contract.
- 429 with `Retry-After`.
- 500/502/503/504.
- 200 with invalid JSON/missing required fields, or an unexpected Content-Type.

**Place tests at level B** for status/body mapping and error classification. Place at **C** if what needs proving is how the real client handles response framing/headers/connections. Place at **D/E** if you want to confirm the real provider emits statuses per contract.

Never write a mock that always returns 200 and believe your adapter handles errors; unexecuted branches likely hide bugs.

### 13.2. Retry, backoff, and idempotency

Suppose the adapter adds retry on 503:

- Do not just assert eventual success; **count the HTTP attempts**.
- Test the provider returning 503 first, then 200.
- Do not retry 400/401 unless policy permits.
- Verify exponential backoff/jitter with a test clock/scheduler when possible.
- Never allow unbounded retries.
- For payment/reservation POSTs, retries require an **idempotency key** and tests for duplicate side effects; never assume POST is safe to replay.
- Avoid long `Thread.sleep(...)` calls to test backoff; prefer injectable policies or virtual schedulers when appropriate.
- With a real HTTP stub, you can inspect the request journal to verify real attempts, especially when retries live inside the HTTP library/interceptor.

**The sample adds no retry**, so a 503 fails after one attempt. If a test configures "first 503, second 200" while production has no retry, that test should not pass.

### 13.3. Timeouts are not 503 errors

- **HTTP 503:** the provider returned a response with a status.
- **Connect timeout:** the client failed to establish a connection within the limit.
- **Read/response timeout:** connected, but the response was too slow or stalled.
- **Total timeout/deadline:** overall budget across the whole operation or retry group.
- **Connection reset/EOF:** the connection closed abruptly mid-exchange.
- **Pool timeout:** failed to acquire a connection from the pool within the limit.

These categories have different exceptions and retry policies. `withException(new IOException(...))` at level B only tests **an `IOException` handling branch**; to prove actual client timeouts, you need a slow/connection-dropping server and real request-factory/client timeout configuration at level C.

Run timeout tests with bounded durations so the suite never hangs. Use a dedicated fault-injection environment; never simulate timeouts by calling an unreliable real API or production network.

### 13.4. Authentication, API keys, and token refresh

Port mocks do not test auth. Level B can assert:

```java
server.expect(requestTo(
        "https://shipping.example.invalid/api/quotes/70000"))
        .andExpect(header(
                "Authorization",
                "Bearer synthetic-test-token"));
```

This is an **extension snippet**; the demo adapter code does not attach `Authorization`, so **do not copy it directly into the sample and expect it to pass**. In real projects, inject a token provider/client interceptor/SSL config matching your application architecture.

Tests should use fake tokens and never dump `Authorization` headers into logs or recordings. If token refresh relies on expiry/clock, test with an injectable clock/token provider; if you must verify against an OAuth sandbox, separate a smoke test with secret management and quota limits.

### 13.5. URL encoding, query parameters, Unicode

If a provider accepts location names or Vietnamese strings instead of numeric postal codes, tests must cover:

- spaces and diacritical characters;
- `?`, `&`, `/`, `#` in path/query inputs;
- UTF-8, percent-encoding, form encoding;
- null/empty parameters;
- duplicate query keys, and ordering semantics if the provider requires them;
- base URLs with a path prefix;
- redirects and `Location` headers when relevant.

At level B, `MockRestServiceServer.requestTo(...)` can catch bad URIs. Level C verifies the actual request-target sent by the transport. **Never concatenate untrusted text into a URL via string addition** when URI templates/builders provide proper encoding; input could unintentionally alter the route or query.

### 13.6. JSON schema, unknown fields, and versioning

A hand-written JSON stub might only show the happy-path response. You should also cover:

- absent optional fields vs. explicit `null`;
- unknown/new fields added by the provider;
- new or deprecated enum values;
- large numbers/decimals, timezones;
- empty/large lists, nested structures;
- malformed JSON and wrong `Content-Type`;
- backward/forward compatibility per the published contract.

Level B tests the parser/adapter against those fixtures. Level D checks whether the stub/schema **matches the real provider version**. If your team uses OpenAPI, Pact, or Spring Cloud Contract, version the contract, run provider verification, and alert on drift.

### 13.7. SSL/TLS, proxies, and network policy

To prove TLS trust/mTLS/hostname validation, the plaintext local HTTP in section 10 **is not enough**. You need an HTTPS stub with test certificates, proper truststore/cert chain, production-like client config, and tests for certificate mismatch/expiry/wrong hostname where appropriate.

Proxy/VPN/firewall/DNS can only be verified at the relevant config/infrastructure layer. Do not use `MockRestServiceServer` to claim you tested proxy routing or "outbound internet policy" when the mock factory never opens a connection.

### 13.8. Observability and tracing

An outbound adapter is also responsible for headers/tracing/metrics. Level B can assert request headers and level C can inspect them at socket level; production observability requires verifying context propagation, filter/interceptor order, and span naming.

Avoid writing overly brittle tests tied to internal header ordering or auto-generated trace IDs. Assert structure and correlation linkage rather than asserting a random request ID against a fixed literal.

## 14. Combining inbound tests with outbound dependencies

If a controller accepts a checkout POST and then calls a shipping provider, there are two groups of questions:

1. **Inbound contract:** the controller accepts valid requests, returns the right status/body, validation, filters/security.
2. **Outbound interaction:** the application sends the right HTTP request, maps errors, and applies fallbacks properly.

Ways to combine them:

| Approach | Real controller? | Real outbound adapter? | Outbound sockets? |
|---|---|---|---|
| `@WebMvcTest` + port mock | Yes, in MVC slice | No | No |
| `@SpringBootTest(MOCK) + @AutoConfigureMockMvc` + port mock | Yes, full app context/MVC | Adapter replaced with mock | No |
| `@SpringBootTest(MOCK) + MockMvc + MockRestServiceServer` | Yes | Yes | No (mock request factory) |
| `@SpringBootTest(RANDOM_PORT)` + WireMock/MockWebServer | Yes, real inbound server | Yes | Yes, outbound localhost |
| Sandbox e2e | Yes, corresponding deployment | Yes | Yes, provider sandbox |

The deeper the level, the higher the cost. To test that a controller merely turns `ShippingProviderException` into a 503 for the client, `@WebMvcTest` + a mocked domain port is usually enough. To test the request built by the adapter, keep the adapter real and stub outbound lower down.

**Specifically:** `@AutoConfigureMockMvc` or `WebTestClient.bindToController(...)` **only sets up the inbound server side**. They do not automatically intercept `RestClient` calls to a provider. Whenever an inbound test makes outbound calls, always define the outbound seam explicitly.

### 14.1. Avoid mocking twice and leaving no real HTTP path

Anti-pattern:

- Mock `ShippingQuotePort` in the controller integration test.
- Also mock `HttpShippingQuoteAdapter` in an "HTTP client test".
- Finally assert the controller returns 200.

No test ever executes the real adapter method. You have tested business/controller logic, **but you have not tested HTTP integration**. You need at least one `@RestClientTest` or loopback test that keeps the adapter real.

### 14.2. Keep each test layer's responsibility clear

Test names should reflect their boundary:

- `checkoutAddsShippingFeeFromPort()`: unit.
- `adapterSendsGetAndParsesQuote()`: client slice.
- `adapterUsesSocketAndMaps503()`: local HTTP integration.
- `consumerContractMatchesProviderSpecification()`: contract verification.
- `providerSandboxAcceptsConfiguredCredential()`: opt-in smoke.

Naming a port-mocking method `endToEndTest()` misrepresents the scope of evidence.

## 15. Common mistakes when mocking outbound HTTP

| Symptom | Common cause | How to check and fix |
|---|---|---|
| `@RestClientTest` tries to reach the internet | Client uses `RestClient.create()` or its own builder instead of the mock-customized builder | Inject the Boot-managed builder; verify which client instance is under test |
| `MockRestServiceServer` reports expected URL mismatch | Using relative URI with `RestClient.Builder` | Expect the **full URI**, verify base URL/path/query |
| JSON parsing test passes, production fails | JSON slice lacks custom Jackson configuration | Import production config or add a full-context loopback test |
| Mock bean makes controller pass while adapter has wrong path | Mocked too high; adapter never executes | Add B/C tests for the real adapter |
| HTTP 503 not handled properly | Tests only check 200 or catch the wrong exception type | Add status cases, assert domain error/cause |
| Client timeout still hangs in production | Mock request factory does not use real socket timeouts | Test level C with delay/fault injection and real timeouts |
| 429 test retries too many times | Unbounded retry config or ignoring `Retry-After` | Stateful stub, assert request count/backoff |
| Payment POST sent twice | Retry without idempotency policy | Contract/transport tests for idempotency key and retry |
| HTTP stub returns body with wrong media type | Wrong `Content-Type` header; converter not selected as expected | Stub explicit `Content-Type`; verify decoder behavior |
| Local stub port already in use | Hardcoded port | Bind `127.0.0.1:0` and inject dynamic property |
| Full-context test still hits production domain | Base URL override ineffective or client built too early | `@DynamicPropertySource`, assert configured URL, network guard |
| One test passes standalone but fails after another | Mock server expectations not reset | `server.verify()` and `server.reset()` per test |
| Multiple `RestClient` builders use the wrong mock server | Server only bound to one client/builder | Identify corresponding builder/customizer, separate tests |
| Localhost HTTP passes while staging TLS fails | Tests only run plaintext loopback | HTTPS test with truststore/mTLS or sandbox smoke |
| Sandbox test fails intermittently | Quota/rate limit, external outage, shared test data | Isolate opt-in job, clear retry policy, monitoring/cleanup |
| Ultra-fast tests miss pool exhaustion | No concurrent connections or large payloads | Controlled load/fault tests at level C/infrastructure |
| `@WebClientTest` builds a `Mono` but no request runs | Publisher never subscribed | `StepVerifier` or web client response subscription |
| Inbound `WebTestClient` passes while outbound fails | Outbound provider not stubbed/verified | Add port mock or HTTP stub at the right layer |
| Test exits before async request finishes | Didn't await terminal/future | Return composed `Publisher`/`CompletableFuture` with bounded await |
| Stale JSON fixture keeps tests forever green | Stub not verified against provider | Consumer/provider contract and scheduled sandbox checks |
| URL concatenated with raw user input | Broken encoding, route/query injection | Use URI builder/template, test boundary characters |
| Auth token leaks into CI artifacts | Recording raw headers/response logs | Fake tokens, redaction, secret management |

### 15.1. Ordered debugging checklist

1. **What is the test proving?** Business logic, request construction, transport, provider contract, or deployment?
2. **Is the adapter actually invoked?** Check mock beans, proxies, conditional wiring, and bean selection.
3. **How is the client created?** Boot-managed builder or manual `create()`/`builder()`?
4. **What is the actual base URL?** Profiles, `@Value`/`@ConfigurationProperties`, `@DynamicPropertySource`, overrides.
5. **Which instance is the mock server bound to?** `RestClient`/`RestTemplate` builder, multiple clients.
6. **Are HTTP expectations deep enough?** Method, full URL, query, headers, body, count.
7. **Does the stub response have the right `Content-Type`/status?**
8. **Error branches?** 4xx/5xx, empty, invalid JSON, timeout, IO.
9. **If `WebClient`:** is the Publisher subscribed/terminally verified?
10. **If the test needs sockets:** are you using a local HTTP stub or only `MockRestServiceServer`?
11. **If the provider changes schema:** who verifies the contract/fixtures?
12. **If flaky:** fixed port, shared mutable stub, context cache, parallel tests, external network, timeouts.
13. **If security:** fake tokens, HTTPS/mTLS/proxy tested at the right level, logs free of secrets.
14. **Reporting:** classify failures by the exact boundary instead of saying "HTTP test failed".

## 16. Running the example and reading the report

### 16.1. Linux/macOS

Pick your project's build tool:

```bash
# Gradle Wrapper:
./gradlew test --tests "com.example.outbound.CheckoutPriceServiceTest"
./gradlew test --tests "com.example.outbound.HttpShippingQuoteAdapterSliceTest"
./gradlew test --tests "com.example.outbound.HttpShippingQuoteAdapterLoopbackTest"

# Or Maven Wrapper:
./mvnw -Dtest=CheckoutPriceServiceTest test
./mvnw -Dtest=HttpShippingQuoteAdapterSliceTest test
./mvnw -Dtest=HttpShippingQuoteAdapterLoopbackTest test
```

### 16.2. Windows PowerShell

```powershell
.\gradlew.bat test --tests "com.example.outbound.CheckoutPriceServiceTest"
.\gradlew.bat test --tests "com.example.outbound.HttpShippingQuoteAdapterSliceTest"
.\gradlew.bat test --tests "com.example.outbound.HttpShippingQuoteAdapterLoopbackTest"

# If the project uses Maven:
.\mvnw.cmd "-Dtest=CheckoutPriceServiceTest" test
.\mvnw.cmd "-Dtest=HttpShippingQuoteAdapterSliceTest" test
.\mvnw.cmd "-Dtest=HttpShippingQuoteAdapterLoopbackTest" test
```

Use **one** build tool suited to the project. With up-to-date Gradle tasks, if you need to re-run for verification, use the test rerun option for your Gradle version. Never claim tests ran solely because the build log prints `BUILD SUCCESSFUL`; check the JUnit report, test count, and failures/skipped count.

### 16.3. Expected report

| Class | `@Test` count | Boundary | Spring context? | Outbound HTTP socket? |
|---|---:|---|---|---|
| `CheckoutPriceServiceTest` | 3 | Port mock | No | No |
| `HttpShippingQuoteAdapterSliceTest` | 6 | Mock request factory | Slice | No |
| `HttpShippingQuoteAdapterLoopbackTest` | 4 | Local HTTP server | Full non-web context | **Yes** |
| **Total** | **13** | Three levels | — | Only 4 local tests |

The sample code has no fixed application stdout output. Test runner output depends on tool versions and environment. **This lesson describes expected results based on the configuration** and does not claim to have compiled/run tests on your project.

**No external provider access:** the `shipping.example.invalid` domain only appears in app config and client-slice expectations. In loopback tests, `shipping.base-url` is overridden to localhost IP and a random port. Unit tests do not instantiate `RestClient`.

### 16.4. If the live HTTP test does not run on CI

Check:

- JDK 17 includes the `jdk.httpserver` module for `com.sun.net.httpserver.HttpServer`. In a **JPMS `module-info.java`** project, `requires jdk.httpserver;` may be needed.
- The runner permits binding loopback `127.0.0.1` and opening ephemeral ports.
- No firewall/security policy blocks local networking (some CI sandboxes restrict sockets).
- `@DynamicPropertySource` is discovered before the adapter builds `RestClient`.
- No other properties/profiles override or lock the base URL.
- Test classes can run individually without depending on startup order or context caching.
- No global parallel test settings cause a shared server to stop prematurely.
- Build test starters/versions are compatible with Spring Framework 6.1+.

If the CI environment forbids loopback sockets, **do not report level C as verified**; keep level B in that CI and run transport tests in a job that permits loopback networking.

## 17. Contract testing and sandbox: two questions distinct from local stubs

### 17.1. When a stub matches your test but mismatches the provider

You write a response fixture:

```json
{
  "service": "STANDARD",
  "feeCents": 25000
}
```

The provider deploys a new version renaming `feeCents` to `price.amountMinor`, or requiring an `X-Api-Version` header. All internal mock tests stay green if the fixture does not change.

To detect drift:

1. Clearly specify the provider's contract/version.
2. Maintain consumer contract tests or OpenAPI/schema validation.
3. Run appropriate provider verification (if you control the provider), or scheduled/agreed partner sandbox smoke tests.
4. Regenerate fixtures from approved contract sources; **never record live production PII directly**.
5. When the provider introduces a breaking change, update the adapter, contracts, migrations, and tests deliberately.

Pact/Spring Cloud Contract help organize contract verification in some architectures; they do not automatically guarantee a third-party provider runs your verifier if you lack integration access with them.

### 17.2. When to use a real sandbox?

Use a sandbox/test account when you need to:

- Verify credentials and auth flows (OAuth token exchange, refresh, scopes).
- Verify base URL, DNS/TLS/certs, and that the provider actually deploys the specific contract.
- Verify API-specific validation rules or headers that docs cannot fully describe.
- Test webhooks/callbacks across permitted infrastructure.
- Test a few end-to-end workflows with test accounts.

Do not make sandbox/production-like calls a dependency of every unit test due to latency, quotas, outages, and shared data. Use a separate CI job (scheduled/on-demand/pre-release) with explicit timeouts, budgets, and cleanup. Never call a production provider from tests without authorization and safe configuration.

### 17.3. Keeping contract tests independent of a live provider

A consumer-driven contract is valuable when provider verification **actually** runs. If you only generate Pact JSON without provider-side verification or equivalent checks, drift risk remains.

For third-party SaaS that does not support provider verification, combine:

- versioned schemas/specs;
- adapter tests using fixtures with clear provenance;
- sandbox smoke tests with isolated credentials;
- monitoring of production request failures;
- compatibility policies and rollback/feature flags when APIs change.

## 18. Boundary selection exercises and solutions

### Exercise A. Checkout total

A service fetches a quote and adds the fee to the subtotal. You must test that a negative subtotal does not call the carrier. Use `MockRestServiceServer` or a Mockito port mock?

**Answer:** Mockito at `ShippingQuotePort` or a fake port. This is a business rule **before the outbound boundary**. Assert the error and `verifyNoInteractions(port)`; no HTTP context or socket is needed.

### Exercise B. One character changed in the URL path

A developer edits `"/api/quotes/{postalCode}"` to `"/api/quote/{postalCode}"`. Port-mock unit tests still pass. Which boundary catches this?

**Answer:** client-slice `@RestClientTest + MockRestServiceServer.requestTo(full URI)` or a real HTTP stub with path matching. Port mocks do not run the adapter, so they miss it.

### Exercise C. 503 and 200

The provider returns 503; the adapter must throw a domain exception. Do you need to call a real sandbox to test the mapping?

**Answer:** no. `MockRestServiceServer.withServiceUnavailable()` tests adapter logic fast enough. A local HTTP stub can add confidence in real client response handling. A sandbox is only needed to confirm the real provider returns that response under the contract.

### Exercise D. Read timeout

A team uses `MockRestServiceServer.withException(IOException)`, the test passes, and they say "we tested Apache HttpClient timeouts." Is that claim accurate?

**No.** The test only fakes an I/O exception in the request factory. Real timeouts depend on the actual client request factory, sockets, network, and configuration. You need a transport-level stub with delays/connection faults and deadline assertions.

### Exercise E. Unsubscribed WebClient Publisher

A `@WebClientTest` builds a `Mono<Quote>` without calling `StepVerifier`/subscribe. The test is green. Does it prove a request was sent?

**No.** A `WebClient` Publisher is normally lazy; you must subscribe and check terminal/value/error signals. For outbound networking, use a real HTTP stub when you want to test transport.

### Exercise F. @WebMvcTest with an outbound provider

A `@WebMvcTest(CheckoutController.class)` injects a mocked `ShippingQuotePort`. The controller responds properly. Does this prove `HttpShippingQuoteAdapter` sends the `Authorization` header?

**No.** The adapter is excluded from the request path. To verify outbound auth headers, keep the adapter real and use a client-mock/local stub, or add dedicated tests for auth configuration/interceptors.

### Exercise G. Fixed port causing flaky CI

Two test jobs run WireMock on port 8089 at the same time. One job fails because the port is busy. How do you fix it?

**Answer:** use an ephemeral port (port 0 or the tool's dynamic port API), inject the URL via `@DynamicPropertySource`/test configuration, isolate instances per worker, and manage lifecycles cleanly.

### Exercise H. Provider JSON changes

`MockRestServiceServer` keeps returning old JSON and all tests pass. The provider sandbox changed its schema. Which tool/test is missing?

**Answer:** contract/provider verification or versioned sandbox smoke tests. Internal mocks cannot know on their own that the provider deployment changed. Update schemas/fixtures from authoritative sources and add drift alerts.

### Exercise I. Retrying a payment POST

A payment adapter retries after a connection reset. How do you know you will not double-charge?

**Answer:** you need an idempotency key contract/policy, tests for attempt counts, verification that two requests with the same key produce at most one side effect, and sandbox/contract checks on provider behavior when possible. Never assume POST retries are safe.

### Exercise J. Does "Full SpringBootTest" mean a full network test?

A test uses `@SpringBootTest` alongside `@MockBean ShippingQuotePort`. Does it test real outbound HTTP?

**No.** A full application context does not guarantee every dependency stays real. If the port is mocked, the adapter does not run; the boundary remains at the domain port. Always inspect dependency wiring rather than inferring from annotation names.

## 19. QA checklist when adding an outbound HTTP integration

- [ ] Mapped the code path from business service to provider endpoint.
- [ ] Clear interface/port or seam exists to mock the business dependency.
- [ ] Business tests do not depend on networking when unnecessary.
- [ ] At least one test runs the **real adapter** against a request/response contract.
- [ ] Do not instantiate the HTTP client via `RestClient.create()` if production relies on Boot builder customizers that tests would miss.
- [ ] Base URL injected via config, not hardcoded to a production URL in a method.
- [ ] No production secrets read or emitted in test fixtures/logs.
- [ ] Client-slice expectations check full URIs for `RestClient.Builder`.
- [ ] HTTP method, path/query, headers, and body verified at the right boundary.
- [ ] JSON mapping tests share the customizers/modules needed by the app.
- [ ] Cases exist for 2xx, 4xx, 5xx, empty/malformed data per contract.
- [ ] Clear error translation between HTTP statuses and I/O failures.
- [ ] Do not treat a fake `IOException` in `MockRestServiceServer` as an actual network test.
- [ ] When transport behavior matters, use a local HTTP stub over sockets.
- [ ] Stubs use ephemeral ports; dynamic properties are injected before client build.
- [ ] Clean stub lifecycle with no shared mutable state across parallel tests.
- [ ] If retries are used, test attempts/backoff/circuit breaker/idempotency.
- [ ] For `WebClient`, subscribe and verify Publisher terminal signals.
- [ ] Do not confuse `MockMvc`/`WebTestClient` inbound setups with outbound stubs.
- [ ] If TLS/proxy/DNS are required, test at a layer with real network/TLS/proxy.
- [ ] Contract fixtures have provenance and are checked against the provider when possible.
- [ ] Opt-in sandbox tests enforce timeouts/quotas/data cleanup and never block unit CI on internet access.
- [ ] With multiple HTTP clients, test each adapter using its real instance/builder.
- [ ] Tests run independently in random order; reset mock expectations.
- [ ] Never log `Authorization`, PII, or raw provider payloads containing sensitive data.
- [ ] Clearly report which tests are unit, client slice, loopback, contract, or sandbox.
- [ ] For Spring Boot 3.0/3.1/4.x, check version-specific APIs/imports.
- [ ] Never treat a "green test" as proof for layers not kept real in that test.

## 20. Summary

**The right test double boundary removes what the test does not own while keeping real anything that could break and must be caught.**

- **Mock the domain port** when testing business rules, fallbacks, and domain-level interactions.
- **`@RestClientTest + MockRestServiceServer`** when testing the real adapter building HTTP requests, parsing responses, and mapping errors—without needing sockets.
- **Local HTTP stub server** when you need real client/transport behavior and full Spring wiring, while still isolating external providers.
- **Consumer/provider contract tests** when ensuring request/response schemas do not drift between teams.
- **Provider sandbox smoke tests** when verifying real deployment/network/auth under controlled cost and access.

Use multiple targeted test layers instead of pushing everything to full e2e or mocking everything and losing HTTP coverage. In Spring Boot, **choosing the right client builder/bean, base URL injection point, and request trigger** determines whether a mock actually sits on the production code path.

The Java 17+/Spring Boot 3.x example uses the exact same `HttpShippingQuoteAdapter` in both client-slice and loopback tests, changing only the **provider boundary**. That makes test results meaningful and minimizes the risk of a mock testing a completely different code path than production.

## Official references

- [Spring Boot 3.5 — Testing Spring Boot Applications: Auto-configured REST Clients](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): `@RestClientTest`, `RestClient.Builder`, `MockRestServiceServer`, full URI expectations.
- [Spring Framework 6.2 — Testing Client Applications](https://docs.spring.io/spring-framework/reference/6.2/testing/spring-mvc-test-client.html): request-factory mock vs. mock HTTP server and transport-level distinctions.
- [Spring Framework 6.2 — REST Clients](https://docs.spring.io/spring-framework/reference/6.2/integration/rest-clients.html): `RestClient`, `RestTemplate`, `WebClient`, response status/error handling, and HTTP interfaces.
- [Spring Framework 6.2 — MockRestResponseCreators Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/test/web/client/response/MockRestResponseCreators.html): `withSuccess`, `withServiceUnavailable`, `withException(IOException)`.
- [Spring Boot 3.5 — Calling REST Services](https://docs.spring.io/spring-boot/3.5/reference/io/rest-client.html): Boot-managed `RestClient.Builder`, HTTP clients, customization.
- [Spring Framework — Dynamic Property Sources](https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/ctx-management/dynamic-property-sources.html): `@DynamicPropertySource` and precedence.
- [Spring Framework — WebTestClient](https://docs.spring.io/spring-framework/reference/6.2/testing/webtestclient.html): inbound controller/application/server tests, distinct from outbound provider stubbing.
- [Spring Framework — Context Caching](https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/ctx-management/caching.html): context reuse, dynamic property/lifecycle implications.
- [WireMock Documentation](https://wiremock.org/docs/): mock HTTP server, request matching, response faults, and standalone options.
- [OkHttp MockWebServer](https://github.com/square/okhttp/tree/master/mockwebserver): local HTTP server for client testing (verify API by version).
- [Spring Cloud Contract](https://docs.spring.io/spring-cloud-contract/reference/): consumer/provider contracts and verifier workflows.
- [Pact Specification / Pact JVM](https://docs.pact.io/): consumer-driven contract testing, provider verification.
