# Limits of Web Slices When Verifying the Full Application

In Spring WebFlux, `@WebFluxTest` lets you test an HTTP endpoint fast without starting the entire application. It typically loads controllers, relevant WebFlux components, data converters, and a pre-configured `WebTestClient`; services, repositories, and collaborators outside the web layer are usually not scanned. This is a **benefit**, not a bug. A test request can return HTTP 200 and valid JSON yet **still not prove** that the repository queries properly, pricing policies calculate properly, transactions work, `WebClient` calls external services accurately, or the app starts with full production configuration.

Therefore, when the question shifts from "does the controller accept and return JSON properly?" to "does the entire application flow work properly?", you must recognize **the limits of a web slice and test at a broader boundary**. Solutions may include service unit tests, adapter integration tests, `@SpringBootTest` with a mock HTTP environment, `@SpringBootTest(webEnvironment = RANDOM_PORT)` with a real HTTP server, or a controlled end-to-end test.

This Knowledge article focuses on **Spring WebFlux** within the Spring Boot testing module, using **Java 17+, Spring Boot 3.5.x, Spring Framework 6.2.x, JUnit Jupiter 5, Reactor, and WebTestClient**. Examples load only controlled internal infrastructure without connecting to production payment providers or databases. APIs and packages may change in Spring Boot 4.x; always cross-check your version's documentation.

## 1. Learning Outcomes

After this lesson, you will be able to:

- Clearly explain that `@WebFluxTest` is a **slice test**, not a full-context test.
- Distinguish controllers, `@RestControllerAdvice`, `WebFilter`, `WebExceptionHandler`, services, repositories, configuration properties, and auto-configuration inside a WebFlux slice.
- Know precisely **what a green test proves** and what it cannot protect against.
- Use `@MockitoBean` at the service boundary in slice tests without mistaking mocks for real logic.
- Choose `WebTestClient` bound to a controller/context or connected to a real HTTP server.
- Write full-context `@SpringBootTest` tests using a mock web environment or `RANDOM_PORT` and understand the difference.
- Recognize limits when testing functional routes, security, filter ordering, JSON/validation, global errors, `WebClient`, R2DBC, transactions, and reactive streams.
- Use `StepVerifier` to verify `Mono`/`Flux` and distinguish publisher testing from HTTP testing.
- Design a test matrix from unit to integration, avoiding replacing real services with mocks and concluding business logic is correct.

## 2. Which Contract Should the Test Prove?

Before picking an annotation, write one sentence:

> "What **failure** in the system must cause this test to fail?"

For example, an endpoint `GET /api/quotes/BOOK?quantity=2&member=true` may have to satisfy several distinct contracts:

| Contract to Protect | Bug to Catch | Appropriate Test Level |
|---|---|---|
| URL, query params, JSON response shape | Wrong path mapping or wrong response field | `@WebFluxTest` |
| Handler uses right status/error advice | 404 turns into 500; wrong error body | `@WebFluxTest` if advice is in the slice |
| Catalog returns exact price for BOOK | Wrong price in catalog | Catalog or repository unit/integration test |
| Members get 10% off | Wrong discount calculation | Unit test of policy and real service |
| Service wires catalog and policy properly | Wrong coordination logic | Service unit test with real/appropriate fake collaborators |
| Spring injects all dependencies | Missing/ambiguous bean, wrong profile | Full-context `@SpringBootTest` |
| Request runs through real TCP server | Server config, filter/protocol, or runtime divergence | `@SpringBootTest(RANDOM_PORT)` |
| SQL/R2DBC queries and transactions work | Wrong query/mapping/commit/rollback | Integration test with appropriate DB |
| Outbound HTTP client matches protocol | Wrong header/body/timeout/retry mapping | Adapter test with mock HTTP server or sandbox |
| Multi-service end-to-end flow works | Integration failure across network, queue, persistence | Isolated end-to-end or system test |

**A passing test proves only the code paths that actually executed and the assertions actually checked.** If a mock service returns a canned `QuoteView`, valid HTTP JSON does not guarantee pricing math is right. If a full-context test only checks `contextLoads()`, it only states the context can start under **that test configuration**, not that business flows work.

## 3. What Does `@WebFluxTest` Load?

In Spring Boot 3.5, `@WebFluxTest` auto-configures WebFlux infrastructure for testing controllers and auto-configures `WebTestClient`. It restricts component scanning to web-layer components.

Component types that can be included, depending on classpath and configuration:

- `@Controller`, `@RestController`, and `@ControllerAdvice`/`@RestControllerAdvice`.
- `@JsonComponent` and JSON components supported by slice/auto-configuration.
- `Converter`, `GenericConverter`, Jackson `Module` when eligible.
- `WebFluxConfigurer`, `WebExceptionHandler`, and `WebFilter` when eligible per version type filters.
- Infrastructure required for annotation-based routing, HTTP message readers/writers, codecs, validation, and request handling.
- Beans **explicitly added by the test** via `@Import`, `@MockitoBean`, `@TestConfiguration`, or matching bean override mechanisms.

Usually **not automatically scanned**:

- `@Service` containing business workflows.
- `@Repository` querying data.
- `@Component`/adapters outside WebFlux slice types.
- All `@ConfigurationProperties` as in a full application context unless enabled explicitly.
- Full application auto-configuration or production infrastructure.

This does not mean all of those bean types are "strictly forbidden". A test can use `@Import` or override annotations to **intentionally** register a service, fake, or configuration. Consequently, seeing a bean in a slice is **not enough to conclude component scanning loaded the real bean**; verify whether it came from scanning, importing, or mocking.

In Spring Boot 3.5, the `WebFluxTest` API also lets you specify target controllers, add include/exclude filters, and disable default filters when needed. Never tweak those attributes indiscriminately just to fix missing-dependency errors: doing so can break slice boundaries.

## 4. Diagram: Two Ways to Test the Same Endpoint

```text
(A) WEB SLICE
JUnit test
  |
  +-- @WebFluxTest(QuoteController.class)
  |        |
  |        +-- WebFlux routing, codecs, advice, WebTestClient
  |        +-- REAL QuoteController
  |        +-- MOCK QuoteService via @MockitoBean
  |        |
  |        +-- Does not run real CatalogAdapter / DiscountPolicy automatically
  |
  +-- WebTestClient (mock request/response, no TCP)
  |        |
  |        v
  +------ HTTP 200 / mock-supplied JSON -> ASSERT

(B) FULL APPLICATION / REAL HTTP
JUnit test
  |
  +-- @SpringBootTest(webEnvironment = RANDOM_PORT)
  |        |
  |        +-- SpringApplication / full ApplicationContext
  |        +-- embedded HTTP server listening on random port
  |        +-- REAL QuoteController
  |        +-- REAL QuoteService
  |        +-- REAL DiscountPolicy
  |        +-- REAL FixedCatalogAdapter (internal fixture)
  |
  +-- WebTestClient (HTTP over localhost TCP)
           |
           v
         Reactive HTTP server -> controller -> service -> catalog/policy
           |
           v
         HTTP 200 / real computed JSON -> ASSERT
```

This is a **role model**, not a detailed call-stack diagram. A full context does not imply every production dependency runs for real: `FixedCatalogAdapter` in the example is still an in-memory fixture adapter. Only the layers genuinely wired in are verified.

## 5. The Most Important Limit: Mock Services Mask Business Logic

Consider this example:

```java
@WebFluxTest(QuoteController.class)
class QuoteControllerSliceTest {

    @MockitoBean
    QuoteService service;

    // WebTestClient test calls the HTTP endpoint,
    // while service.quote(...) returns a Mono pre-configured by the test.
}
```

This is a **snippet** only to illustrate the boundary; the full test file appears in Section 11.

If the test writes:

```java
when(service.quote("BOOK", 2, true))
        .thenReturn(Mono.just(
                new QuoteView("BOOK", 2, 240_000L,
                        24_000L, 216_000L)));
```

then the numbers `240000`, `24000`, and `216000` were **invented by the test itself**, not computed by the real policy. The test verifies that the controller forwards arguments and serializes the response, yet **will not catch** production changing the discount from 10% to 5%.

To protect business logic:

- Unit test the real `DiscountPolicy` with boundary cases.
- Unit test the real `QuoteService` with a fake `CatalogGateway` or controlled real adapter.
- Run full-context/integration tests when Spring bean wiring and real collaboration paths need proof.

**Do not call this a flaw in `@WebFluxTest`.** It works exactly as a slice is designed to work. The mistake lies in **over-interpreting what a green test means**.

## 6. `WebTestClient` Has Multiple Operating Modes

`WebTestClient` is the request/response observation tool suited to WebFlux and can be used in several ways:

| Creation Mode | Real Spring Context? | Opens TCP HTTP Server? | What It Protects |
|---|---|---|---|
| `WebTestClient.bindToController(controller)` | Not required | No | Handler + minimal WebFlux infrastructure for selected controller |
| `WebTestClient.bindToRouterFunction(route)` | Not required | No | Functional route passed directly into test |
| `WebTestClient.bindToApplicationContext(context)` | Uses supplied context | No | `WebHandler` chain built from that context |
| `@WebFluxTest` with injected `WebTestClient` | MVC? **No**; WebFlux slice context | No | WebFlux slice, controller, loaded codecs/filters/advice |
| `@SpringBootTest` + `@AutoConfigureWebTestClient` with mock environment | Full Boot context | No | Bean wiring/config/application chain, without TCP server |
| `@SpringBootTest(RANDOM_PORT)` + injected `WebTestClient` | Full Boot context | Yes | Request/response through real embedded server |
| `WebTestClient.bindToServer().baseUrl(...)` | Depends on external server | Yes | Live HTTP endpoint listening at that URL |

Two statements must be kept distinct:

1. **Real client** does not mean **real server**. `WebTestClient` can use mock requests/responses even though its client API mirrors TCP connections.
2. **Full context** does not mean **real HTTP server**. `@SpringBootTest` with its default `MOCK` environment loads many beans without opening a network port.

You cannot claim to have verified sockets, port binding, network timeouts, reverse proxies, TLS, load balancers, or the real HTTP runtime when using only mock server binding.

### 6.1. WebFlux Is Not Spring MVC

`@WebFluxTest` is the slice for the reactive WebFlux stack. `@WebMvcTest` and `MockMvc` are the usual choices for the Spring MVC servlet stack. `WebTestClient` can work with both via appropriate adapters/configurations, yet **you cannot infer a test runs WebFlux solely because the client type is `WebTestClient`**.

If both `spring-boot-starter-web` and `spring-boot-starter-webflux` are on the classpath, Boot usually selects **the servlet MVC application type** by default. When writing tests restricted to WebFlux, verify whether starters and `spring.main.web-application-type` actually produce a reactive application. The runnable example below **adds only `starter-webflux`**, avoiding this ambiguity.

## 7. Three Questions Before Choosing Slice vs Full Context

1. **Is the target an HTTP contract or a business workflow?** For mapping, parameter binding, status, JSON, validation, and controller advice: a WebFlux slice suffices. For pricing/repositories/business coordination: run real logic in another test or full context.
2. **Is the target bean wiring or server/network behavior?** When DI/config/profiles are the goal, full context with mock web environment may suffice. When a real server is needed, use random port.
3. **Is the target isolated inside one JVM or multiple collaborating systems?** A `@SpringBootTest(RANDOM_PORT)` with fake DB/HTTP does not automatically prove event brokers, payment providers, or production databases operate properly. When real external boundaries matter, add dedicated integration/contract/E2E tests.

Pick the smallest level **sufficient to catch the bugs you care about**. No annotation can substitute for writing proper assertions on those contracts.

## 8. Components Frequently Missed in `@WebFluxTest`

### 8.1. `@Service` and `@Repository`

Slices usually do not scan `@Service` or `@Repository`. If a controller constructor requires `QuoteService`, the test must supply the collaborator via `@MockitoBean` or intentional imports/config. This does not prove the production repository works.

### 8.2. Configuration Properties and Profiles

`@ConfigurationProperties` are not automatically scanned like in a full Boot context. If a controller directly requires a properties bean, you can use `@EnableConfigurationProperties(TheProperties.class)` or import matching configuration. Still, one valid test property does not prove full production configuration works. Profiles, secrets, TLS, connection pools, or resource locations must be verified at the appropriate level.

### 8.3. Non-Web Infrastructure Configurations

R2DBC datasources, Redis clients, Kafka producers, scheduled jobs, or outbound `WebClient` adapters normally sit outside the slice. Force-importing them into a slice to "look more like production" sacrifices speed and isolation while still missing other application mechanisms.

### 8.4. Functional Routing

This is a **very concrete** limitation: in Spring Boot 3.5, `@WebFluxTest` does not automatically discover all routes declared with **functional WebFlux** (`RouterFunction`) the way it scans annotated controllers. To test router functions, use `WebTestClient.bindToRouterFunction(...)`, explicitly import the `RouterFunction`/handler, or use `@SpringBootTest`.

### 8.5. Security and WebFilter

`WebFilter`, `WebExceptionHandler`, and WebFlux security components may be part of the web slice depending on annotations, component scanning, auto-configuration, and classpath. Thus you must not say "slices always drop all filters/security".

What is not guaranteed is that **full production security configuration** exists in the test context along the exact deployment path. Verify which beans/filter chains were loaded and test authorization/authentication with appropriate security test setup. Never disable CSRF/auth just to turn tests green while claiming production endpoints are secure.

### 8.6. Reactive Data and Transaction Boundaries

A slice can return mocked `Mono<Dto>` without touching R2DBC repositories or transactions. In reactive Spring, transactions typically rely on **Reactor Context** rather than purely `ThreadLocal`. Real HTTP server tests normally process requests on a different thread/context than the JUnit test method; test-method transactions do not automatically roll back changes committed by the HTTP server.

## 9. Complete Example: Same Endpoint, Two Verification Levels

We build an application generating **price quotes** for products:

- BOOK has unit price 120,000 VND; PEN has unit price 20,000 VND.
- Quantity must be greater than 0.
- Members receive a 10% discount on the subtotal, rounded down via integer division in the example.
- Missing SKU returns HTTP 404 with JSON error.
- Invalid input returns HTTP 400 with JSON error.
- A web slice test uses mocked `QuoteService` to verify mapping/JSON.
- A full HTTP test invokes **real `QuoteService`, `FixedCatalogAdapter`, and `DiscountPolicy`** through a real server.

In real products, currency requires dedicated money types, currency codes, rounding policies, overflow protection, and idempotency. The example uses **integer `long` in VND** to focus on test architecture. The catalog adapter reads fixed in-memory values, **with no network, DB, or production accounts**.

### 9.1. Directory Tree

```text
src/main/java/com/example/webfluxscope/
    QuoteDemoApplication.java
    QuoteView.java
    ApiError.java
    CatalogGateway.java
    FixedCatalogAdapter.java
    DiscountPolicy.java
    QuoteNotFoundException.java
    QuoteService.java
    QuoteController.java
    QuoteErrors.java

src/test/java/com/example/webfluxscope/
    QuoteServiceUnitTest.java
    QuoteWebFluxSliceTest.java
    QuoteFullHttpTest.java
```

All files reside in package `com.example.webfluxscope`. The project requires Java 17+, Spring Boot 3.5.x, Reactor, and test dependencies as shown in Section 21.

### 9.2. WebFlux Application

**`src/main/java/com/example/webfluxscope/QuoteDemoApplication.java`**

```java
package com.example.webfluxscope;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class QuoteDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(QuoteDemoApplication.class, args);
    }
}
```

With only `spring-boot-starter-webflux`, Boot selects the reactive application type by convention. This app does not need `@EnableWebFlux`; manually adding `@EnableWebFlux` can alter Boot auto-configuration and change example behavior.

### 9.3. Records for Return Data and Errors

**`src/main/java/com/example/webfluxscope/QuoteView.java`**

```java
package com.example.webfluxscope;

public record QuoteView(
        String sku,
        int quantity,
        long subtotalVnd,
        long discountVnd,
        long totalVnd) {
}
```

**`src/main/java/com/example/webfluxscope/ApiError.java`**

```java
package com.example.webfluxscope;

public record ApiError(String code, String message) {
}
```

Java records suit simple immutable DTOs: accessors like `totalVnd()`, `equals`, and `hashCode` are generated by Java. Jackson in Spring Boot 3.5 serializes them to JSON objects.

### 9.4. Port and Stub Adapter with Real Logic

**`src/main/java/com/example/webfluxscope/CatalogGateway.java`**

```java
package com.example.webfluxscope;

import reactor.core.publisher.Mono;

public interface CatalogGateway {
    Mono<Long> findUnitPrice(String sku);
}
```

**`src/main/java/com/example/webfluxscope/FixedCatalogAdapter.java`**

```java
package com.example.webfluxscope;

import org.springframework.stereotype.Repository;
import reactor.core.publisher.Mono;

@Repository
public class FixedCatalogAdapter implements CatalogGateway {

    @Override
    public Mono<Long> findUnitPrice(String sku) {
        return switch (sku) {
            case "BOOK" -> Mono.just(120_000L);
            case "PEN" -> Mono.just(20_000L);
            default -> Mono.empty();
        };
    }
}
```

`FixedCatalogAdapter` is a **real adapter bean instantiated by Spring when the full context runs**, though it only reads two in-memory prices. This test verifies the call path to the adapter, **not SQL, R2DBC mapping, connection pools, or database transactions**. The `@Repository` annotation indicates architectural role, not that a real database is present.

### 9.5. Real Business Policy

**`src/main/java/com/example/webfluxscope/DiscountPolicy.java`**

```java
package com.example.webfluxscope;

import org.springframework.stereotype.Component;

@Component
public class DiscountPolicy {

    public long discountVnd(long subtotalVnd, boolean member) {
        if (subtotalVnd < 0L) {
            throw new IllegalArgumentException(
                    "subtotal must not be negative");
        }
        return member ? subtotalVnd / 10L : 0L;
    }
}
```

If someone changes the 10% discount to 5% in this code, the **full HTTP test** and **service unit test** below will fail, while the slice test can remain green because the mock's output does not change. That illustrates the central thesis of this article.

### 9.6. Exception for Unknown SKU

**`src/main/java/com/example/webfluxscope/QuoteNotFoundException.java`**

```java
package com.example.webfluxscope;

public class QuoteNotFoundException extends RuntimeException {
    public QuoteNotFoundException(String sku) {
        super("Unknown sku: " + sku);
    }
}
```

### 9.7. Reactive Service with Real Logic and Subscription Semantics

**`src/main/java/com/example/webfluxscope/QuoteService.java`**

```java
package com.example.webfluxscope;

import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class QuoteService {
    private final CatalogGateway catalog;
    private final DiscountPolicy policy;

    public QuoteService(CatalogGateway catalog, DiscountPolicy policy) {
        this.catalog = catalog;
        this.policy = policy;
    }

    public Mono<QuoteView> quote(
            String sku, int quantity, boolean member) {

        return Mono.defer(() -> {
            if (sku == null || sku.isBlank()) {
                return Mono.error(new IllegalArgumentException(
                        "sku must not be blank"));
            }
            if (quantity <= 0) {
                return Mono.error(new IllegalArgumentException(
                        "quantity must be positive"));
            }

            return catalog.findUnitPrice(sku)
                    .switchIfEmpty(Mono.error(
                            new QuoteNotFoundException(sku)))
                    .map(unitPrice -> {
                        long subtotal = Math.multiplyExact(
                                unitPrice, quantity);
                        long discount = policy.discountVnd(
                                subtotal, member);
                        long total = Math.subtractExact(
                                subtotal, discount);
                        return new QuoteView(sku, quantity,
                                subtotal, discount, total);
                    });
        });
    }
}
```

Reactive structure:

1. `Mono.defer` postpones input validation and catalog lookup until the publisher is **subscribed**.
2. `findUnitPrice` returns `Mono<Long>`, without blocking threads.
3. `switchIfEmpty` turns a missing SKU into `onError`.
4. `map` executes real price/discount math when a value arrives.
5. Arithmetic overflow is caught by `Math.multiplyExact` or `Math.subtractExact`; add dedicated error mapping if products can reach extreme values.

**Never call `block()` or `subscribe()` inside controllers/services** to "force `Mono` to run". WebFlux manages subscriptions during HTTP handling; calling `block` on the event loop can cause operational errors or degrade throughput. To test a publisher separately in unit tests, use `StepVerifier`.

### 9.8. Annotated Reactive Controller

**`src/main/java/com/example/webfluxscope/QuoteController.java`**

```java
package com.example.webfluxscope;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/quotes")
public class QuoteController {
    private final QuoteService service;

    public QuoteController(QuoteService service) {
        this.service = service;
    }

    @GetMapping("/{sku}")
    public Mono<QuoteView> getQuote(
            @PathVariable String sku,
            @RequestParam(defaultValue = "1") int quantity,
            @RequestParam(defaultValue = "false") boolean member) {
        return service.quote(sku, quantity, member);
    }
}
```

The controller has one job: bind the request, call the service, and return `Mono<QuoteView>` to WebFlux. It **does not compute prices directly**. This creates a clean boundary to mock the service when testing WebFlux's MVC-style HTTP contract, and run the real service when testing the use case.

### 9.9. Shared Error Handler

**`src/main/java/com/example/webfluxscope/QuoteErrors.java`**

```java
package com.example.webfluxscope;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import reactor.core.publisher.Mono;

@RestControllerAdvice
public class QuoteErrors {

    @ExceptionHandler(QuoteNotFoundException.class)
    @ResponseStatus(HttpStatus.NOT_FOUND)
    public Mono<ApiError> notFound(QuoteNotFoundException failure) {
        return Mono.just(new ApiError(
                "SKU_NOT_FOUND", failure.getMessage()));
    }

    @ExceptionHandler(IllegalArgumentException.class)
    @ResponseStatus(HttpStatus.BAD_REQUEST)
    public Mono<ApiError> badRequest(IllegalArgumentException failure) {
        return Mono.just(new ApiError(
                "INVALID_REQUEST", failure.getMessage()));
    }
}
```

`@RestControllerAdvice` belongs to web-layer components, so `@WebFluxTest` can load this handler. Slice tests can verify errors turn into HTTP 404/400 with JSON. However, **not every exception in a production server passes through the same handler**; security exceptions, `WebFilter` errors, malformed bodies, and default global error handlers may need separate tests.

## 10. Service Unit Test: Protecting Logic Without a Spring Context

**`src/test/java/com/example/webfluxscope/QuoteServiceUnitTest.java`**

```java
package com.example.webfluxscope;

import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class QuoteServiceUnitTest {

    private final CatalogGateway catalog = sku -> switch (sku) {
        case "BOOK" -> Mono.just(120_000L);
        case "PEN" -> Mono.just(20_000L);
        default -> Mono.empty();
    };

    private final QuoteService service =
            new QuoteService(catalog, new DiscountPolicy());

    @Test
    void computesRealMemberDiscount() {
        StepVerifier.create(
                service.quote("BOOK", 2, true))
                .expectNext(new QuoteView(
                        "BOOK", 2, 240_000L,
                        24_000L, 216_000L))
                .verifyComplete();
    }

    @Test
    void computesFullPriceForNonMember() {
        StepVerifier.create(
                service.quote("PEN", 3, false))
                .expectNext(new QuoteView(
                        "PEN", 3, 60_000L, 0L, 60_000L))
                .verifyComplete();
    }

    @Test
    void rejectsUnknownSkuReactively() {
        StepVerifier.create(
                service.quote("UNKNOWN", 1, false))
                .expectErrorMatches(failure ->
                        failure instanceof QuoteNotFoundException
                        && failure.getMessage().equals(
                                "Unknown sku: UNKNOWN"))
                .verify();
    }

    @Test
    void rejectsInvalidQuantity() {
        StepVerifier.create(
                service.quote("BOOK", 0, true))
                .expectError(IllegalArgumentException.class)
                .verify();
    }
}
```

This is a **real domain + service unit test**: no Spring startup, no Mockito, no HTTP. Because `DiscountPolicy` is the real object, the test catches discount math bugs. `CatalogGateway` is a fixed fake, so it does not test database queries.

`StepVerifier` subscribes to the publisher and verifies **`onNext`, `onComplete`, or `onError`**. When the Publisher emits `Mono.empty()` while the test expects a `QuoteView`, the assertion turns red instead of silently passing. Reactive unit tests can also test retries, timeouts, cancellation, or `Flux`, provided those operators exist in concrete SUT logic.

## 11. Web Slice Test: Real Controller, Mock Service

**`src/test/java/com/example/webfluxscope/QuoteWebFluxSliceTest.java`**

```java
package com.example.webfluxscope;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.WebFluxTest;
import org.springframework.context.ApplicationContext;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.reactive.server.WebTestClient;
import reactor.core.publisher.Mono;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.Mockito.mockingDetails;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@WebFluxTest(QuoteController.class)
class QuoteWebFluxSliceTest {

    @Autowired
    WebTestClient client;

    @Autowired
    ApplicationContext context;

    @MockitoBean
    QuoteService service;

    @Test
    void mapsRequestAndSerializesStubbedQuote() {
        when(service.quote("BOOK", 2, true))
                .thenReturn(Mono.just(new QuoteView(
                        "BOOK", 2, 240_000L,
                        24_000L, 216_000L)));

        client.get()
                .uri(uri -> uri.path("/api/quotes/BOOK")
                        .queryParam("quantity", 2)
                        .queryParam("member", true)
                        .build())
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.sku").isEqualTo("BOOK")
                .jsonPath("$.quantity").isEqualTo(2)
                .jsonPath("$.subtotalVnd").isEqualTo(240_000)
                .jsonPath("$.discountVnd").isEqualTo(24_000)
                .jsonPath("$.totalVnd").isEqualTo(216_000);

        verify(service).quote("BOOK", 2, true);

        assertEquals(0, context.getBeanNamesForType(
                FixedCatalogAdapter.class).length);
        assertTrue(mockingDetails(service).isMock());
    }

    @Test
    void mapsServiceErrorThroughControllerAdvice() {
        when(service.quote("UNKNOWN", 1, false))
                .thenReturn(Mono.error(
                        new QuoteNotFoundException("UNKNOWN")));

        client.get()
                .uri("/api/quotes/UNKNOWN")
                .exchange()
                .expectStatus().isNotFound()
                .expectBody()
                .jsonPath("$.code").isEqualTo("SKU_NOT_FOUND")
                .jsonPath("$.message")
                .isEqualTo("Unknown sku: UNKNOWN");

        verify(service).quote("UNKNOWN", 1, false);
    }
}
```

### 11.1. What Does This Test Prove?

- `GET /api/quotes/BOOK?quantity=2&member=true` maps to the controller properly and forwards all three arguments accurately.
- WebFlux serializes the Java record to JSON with the exact fields/values **supplied by the mock**.
- `@RestControllerAdvice` was loaded in the slice and converted the publisher's `QuoteNotFoundException` into 404.
- `FixedCatalogAdapter` was not scanned; this is expected slice behavior, not a missing production bean.
- `QuoteService` in the context is a **Mockito mock**, not the real implementation.

### 11.2. What Does This Test Not Yet Prove?

- Whether `QuoteService.quote` performs the right math.
- Whether `DiscountPolicy` really deducts 10%.
- Whether `FixedCatalogAdapter` reads SKUs properly.
- Whether the full Boot context wires up cleanly.
- Whether the embedded HTTP server can bind a port.
- Whether a database, transactions, production security, outbound HTTP clients, or a real integration flow work.

That is why the test name `mapsRequestAndSerializesStubbedQuote` is more honest than `checkoutWorksEndToEnd`. **A test name is a promise about verification scope**.

## 12. Full HTTP Test: App Actually Creates Context and Opens a Port

**`src/test/java/com/example/webfluxscope/QuoteFullHttpTest.java`**

```java
package com.example.webfluxscope;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.mockito.Mockito.mockingDetails;

@SpringBootTest(
        classes = QuoteDemoApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class QuoteFullHttpTest {

    @Autowired
    WebTestClient client;

    @Autowired
    QuoteService realService;

    @Autowired
    FixedCatalogAdapter realCatalog;

    @Test
    void realHttpServerRunsServiceCatalogAndPolicy() {
        client.get()
                .uri(uri -> uri.path("/api/quotes/BOOK")
                        .queryParam("quantity", 2)
                        .queryParam("member", true)
                        .build())
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.sku").isEqualTo("BOOK")
                .jsonPath("$.quantity").isEqualTo(2)
                .jsonPath("$.subtotalVnd").isEqualTo(240_000)
                .jsonPath("$.discountVnd").isEqualTo(24_000)
                .jsonPath("$.totalVnd").isEqualTo(216_000);

        assertFalse(mockingDetails(realService).isMock());
        assertFalse(mockingDetails(realCatalog).isMock());
    }

    @Test
    void unknownSkuMapsTo404FromRealService() {
        client.get()
                .uri("/api/quotes/UNKNOWN")
                .exchange()
                .expectStatus().isNotFound()
                .expectBody()
                .jsonPath("$.code").isEqualTo("SKU_NOT_FOUND");
    }

    @Test
    void invalidQuantityMapsTo400() {
        client.get()
                .uri(uri -> uri.path("/api/quotes/BOOK")
                        .queryParam("quantity", 0)
                        .build())
                .exchange()
                .expectStatus().isBadRequest()
                .expectBody()
                .jsonPath("$.code").isEqualTo("INVALID_REQUEST");
    }
}
```

With `RANDOM_PORT`, Spring Boot starts an embedded reactive HTTP server on an available port and configures `WebTestClient` to call that server. Because the demo project has only `spring-boot-starter-webflux`, requests traverse the application's WebFlux runtime.

**Verifiable differences:**

- The controller is not mocked.
- `@Service` and `@Repository` catalog beans are instantiated for real by Spring; `@Component` policy runs for real.
- Total JSON amounts are computed by adapter + service + policy, **not stubbed by the test**.
- A real HTTP server starts; statuses and serialization are observed over a real connection to localhost.

Because the catalog adapter uses fixed data, this is **not yet an integration test against a production database**. Precisely put: a full HTTP integration test of the **internal demo app**, not an end-to-end test of the entire ecosystem.

If a runtime test genuinely needs a database/queue, provide safe test infrastructure and assert corresponding side effects. Never let full-context tests corrupt real data.

## 13. Full Context Without Opening an HTTP Server

Sometimes you need to verify bean wiring, codecs, profiles, or the complete WebFlux handler chain without **needing real TCP networking**. Use:

```java
@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureWebTestClient
class FullContextMockWebTest {
    @Autowired WebTestClient client;
    // @Test methods...
}
```

This is a **snippet**: add imports for annotations/bean classes and real `@Test` methods. `@AutoConfigureWebTestClient` resides in `org.springframework.boot.test.autoconfigure.web.reactive` in Spring Boot 3.5.

Comparison:

| Criterion | `@WebFluxTest` | Full context + `@AutoConfigureWebTestClient` | Full context + `RANDOM_PORT` |
|---|---|---|---|
| Application beans | Limited slice | More real beans per config | More real beans per config |
| `WebTestClient` | Auto-configured | Configured via annotation | Boot can autowire server-bound client |
| Embedded server | No | No | Yes |
| Tests real service logic | No, if service is mocked | Yes if unmocked | Yes if unmocked |
| Tests Spring wiring | Slice wiring only | Full test-context wiring | Full test-context wiring |
| Tests TCP, ports, server runtime | No | No | Yes |
| Cost | Usually lowest | Higher than slice | Usually higher due to server |

**Do not equate "full-context" with "`RANDOM_PORT`".** Context scope and real networking are **two independent axes**. An integration test using a mock web environment can be valuable when verifying in-process Java/Spring end-to-end handling without needing transport verification.

## 14. Functional Routes: A Very Frequently Forgotten Limitation

Spring WebFlux supports two ways to define endpoints:

1. **Annotated controllers**: `@RestController`, `@GetMapping`, `@RequestMapping`.
2. **Functional endpoints**: `RouterFunction<ServerResponse>` paired with handlers.

`@WebFluxTest` focuses on annotated web components. Spring Boot 3.5 documentation explicitly states it **does not automatically discover routes registered with the functional web framework**. If an application uses functional routers, a green `@WebFluxTest` covering only other annotated controllers does not prove functional routes are registered.

Conceptual example:

```java
// Snippet: requires a real QuoteHandler and RouterFunctions imports.
@Bean
RouterFunction<ServerResponse> quoteRoutes(QuoteHandler handler) {
    return RouterFunctions.route(
            RequestPredicates.GET("/functional/quotes/{sku}"),
            handler::get);
}
```

This is not a standalone runnable file because `QuoteHandler` is undefined. Testing options:

- For isolated route logic, use `WebTestClient.bindToRouterFunction(routes)` to test the handler chain at the desired scope.
- To run the route inside a Spring context, intentionally import the `RouterFunction`/configuration and handler.
- To prove the production app registers the route fully, use `@SpringBootTest` and call the endpoint via a mock WebFlux environment or real server.

**Trap:** a `bindToRouterFunction` test with a router constructed via `new` does not prove the full Spring context contains that router bean. To verify **wiring**, the test must exercise the real context.

## 15. Reactive Publishers: HTTP Tests Do Not Replace `StepVerifier`

In WebFlux, an endpoint can return `Mono<T>` or `Flux<T>`. `WebTestClient` tests HTTP status/body and can consume a stream; `StepVerifier` tests **reactive signal sequences** (subscription, `onNext`, `onComplete`, `onError`, cancellation, virtual time).

| Question | Appropriate Tool |
|---|---|
| Is HTTP 200 JSON accurate? | `WebTestClient` |
| Does `Mono` emit one `QuoteView` and complete? | `StepVerifier` |
| Does `Mono` error with the right type when SKU is missing? | `StepVerifier` |
| Does an SSE stream deliver events over HTTP transport? | `WebTestClient` with matching stream test |
| Do retry/backoff timings behave right in virtual time? | `StepVerifier.withVirtualTime` on matching reactive logic |
| How does a real Netty server handle streaming/timeouts? | HTTP integration test with running server and client timeout |

Example inside a unit test:

```java
StepVerifier.create(service.quote("BOOK", 2, true))
        .expectNext(new QuoteView(
                "BOOK", 2, 240_000L, 24_000L, 216_000L))
        .verifyComplete();
```

If a method returns `Mono<Void>` representing only **completion**, HTTP 204 may not guard underlying side effects; assert matching repositories/event sinks at another level.

If a method returns a **non-terminating** `Flux`, never call unbounded `expectComplete()`. For SSE streams, use `take(n)`/`thenCancel()` and timeouts where appropriate, and include at least one HTTP integration test when protocol/flushing/network behavior is part of the contract.

### 15.1. Backpressure and Operators Are Not Protected by Mock Services

When `@WebFluxTest` stubs `when(service.events()).thenReturn(Flux.just(...))`, the test can prove the controller adapts a `Flux` into SSE as configured, yet does not test backpressure, concurrency, or buffering in the real service. Test stream logic with `StepVerifier` and transport with HTTP tests; never conclude "our reactive pipeline is sound" from a mock `Flux` of two items.

### 15.2. Avoid Blocking on the Event Loop

A slice test with a fast `Mono.just(...)` publisher will not catch production code calling blocking JDBC or `Thread.sleep` on the Netty event loop when the service is mocked. Unit tests can use BlockHound (when suitable and compatibly configured) or concurrency/performance integration tests to detect blocking; more importantly, rely on code review and clean adapter boundaries. Never add `block()` to a service just to satisfy a test.

## 16. WebFlux Security and Filter Chains

`@WebFluxTest` may load `WebFilter`s and security pieces depending on classpath/configuration. However, if the production app has:

- Custom `SecurityWebFilterChain`;
- Reactive authentication manager;
- JWT/OAuth2 resource server;
- Role/permission checks, CSRF;
- Profile- or tenant-specific `WebFilter`s;
- CORS configuration and exception translation;

then a slice test only verifies **whichever security config is actually present in the test context**. If a test uses `@WithMockUser`, it simulates a principal without executing the full gateway token-parsing/verification flow.

A sensible strategy:

1. Unit test permission-decision policies with explicit inputs.
2. WebFlux slice test route authorization/statuses using version-compatible security test support.
3. Full-context/HTTP tests for key security flows to verify the filter chain and Boot configuration.
4. Test with real tokens signed by a test key/sandbox provider when required to verify decoder/issuer/audience/CORS.

**Warning:** if HTTP tests fail with 401/403 due to missing credentials or CSRF, never disable security globally just to get 200. Identify the contract, set up proper security fixtures, and keep at least integration tests protecting critical policies.

The runnable examples in Sections 9–12 **do not declare a Spring Security dependency**. Hence requests are not blocked by security; adding that dependency in a real project can alter statuses/behavior.

## 17. Transactions, R2DBC, and Databases: Web Slices Are Not Enough

`@WebFluxTest` does not load reactive repositories or R2DBC connection pools by default. If an endpoint returns canned data from a mocked service, zero SQL, schemas, converters, or mappings have executed.

With Spring Data R2DBC or reactive DBs, verify:

- Is the SQL/query actually valid on the target DB?
- Are entity/table mappings, converters, and null handling accurate?
- Are reactive transactions applied via `TransactionalOperator` or `@Transactional` using the right reactive mechanism?
- Does real commit/rollback behavior work?
- Are concurrent requests, optimistic locking, or unique constraints protected?

That is why you need **repository integration tests** against a controlled database with migrations and proper fixtures. An in-memory fake repository proves only the logic calling that fake, not SQL.

### 17.1. `@Transactional` on a Test Method Does Not Guarantee HTTP Server Rollback

With `@SpringBootTest(RANDOM_PORT)`, the JUnit client and HTTP server typically execute in different thread/transaction contexts. A transaction attached to the test method **does not wrap** transactions opened by the server while handling requests. In WebFlux, reactive transactions also follow Reactor Context semantics.

Therefore, writing:

```java
// INFERENCE ANTI-EXAMPLE:
// @Transactional on a JUnit test does not automatically roll back
// writes committed by the HTTP server on a separate thread.
@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@Transactional
class DatabaseHttpTest {
}
```

is not sufficient to guarantee a clean database after each test. This is only a snippet without runnable repositories/config. Use an isolated test database, isolated data, explicit cleanup/fixture resets, or transaction setup at the right boundary, and verify commits/rollbacks where they actually occur.

## 18. WebClient, Brokers, Schedulers: Full Context Also Has Limits

Even `@SpringBootTest(RANDOM_PORT)` does not automatically become an E2E test of a distributed system.

| Boundary | Needed Test Outside Web Slice | Limit to Remember |
|---|---|---|
| Outbound HTTP via `WebClient` | Adapter test with mock HTTP server, testing timeout/status/header/retry | Mocking the adapter skips testing the real HTTP protocol |
| Kafka/RabbitMQ | Producer/consumer integration test with a test broker | `verify(publisher)` checks interaction only, not delivery |
| Redis/cache | Test cache keys/TTL/serialization against test Redis when needed | A fake map tests neither TTLs nor wire protocol |
| Schedulers/async events | Test job triggers, event handling, lifecycles separately | Slices skip jobs; full HTTP tests do not wait for async side effects by default |
| Remote auth/OAuth2 | Test token validation + HTTP security boundary | Mock principals do not verify remote providers |
| PostgreSQL/MySQL/R2DBC | Repository + migration + transaction integration tests | In-memory fakes prove neither SQL nor locking |
| Real API gateway/TLS/ingress | Staging E2E/contract/infrastructure tests | Localhost HTTP server bypasses the production gateway |

**Full context** means Spring loads application configuration for the test scope, **not that every remote production service was enabled or called**. Distinguish real logic, fakes/fixtures, and concrete external resources.

### 18.1. Never Call Production Services from Tests

Automated tests should avoid production credentials, real customer data, or external partners lacking a sandbox. Options include mock HTTP servers, Testcontainers, local fakes, and dedicated test tenants/databases. For tests that genuinely call a sandbox, control timeouts, retries, cleanup, and rate limits.

### 18.2. "More Real Beans" Is Not an End in Itself

If the goal is solely an endpoint's JSON contract, loading Kafka consumers, DB migrations, and scheduled jobs just to "make tests feel more real" slows suites down, adds flakiness, and raises risk. Increase integration scope **when the contract and failure modes demand it**, not because a heavier annotation feels superior.

## 19. Bean Overrides in the Right Place: `@MockitoBean` Is Not a Cure-All

In Spring Boot 3.4+/Spring Framework 6.2+, `@MockitoBean` from `org.springframework.test.context.bean.override.mockito` lets you override or register a mock bean in the TestContext. In `@WebFluxTest`, this is the standard way to supply a service to a controller constructor.

Comparison:

| Technique | Impact on Context | When to Use |
|---|---|---|
| `Mockito.mock(QuoteService.class)` in unit test | None | Manually creating controllers/services and passing dependencies |
| `@Mock` with `MockitoExtension` | Does not replace Spring beans directly | Pure Mockito unit tests |
| `@MockitoBean QuoteService service` | Adds mock to context or replaces existing bean | Web slice tests needing a service collaborator |
| `@MockitoSpyBean` | Wraps real bean via TestContext | Partial mocking when genuinely needed; watch side effects and AOP |
| `@TestConfiguration` + `@Import` | Adds test beans to context | Fake implementations with stable behavior |
| `@SpringBootTest` | Loads broad application context | Testing wiring/config/integration |

**Risks of misusing overrides:**

1. If a test claims to test `QuoteService` while placing `@MockitoBean` on `QuoteService`, the test never runs the logic it claims to verify.
2. When you need to ensure a production bean exists and gets replaced, Spring Framework 6.2+ offers `@MockitoBean(enforceOverride = true)` to fail if the target bean is missing. In MVC/WebFlux slices, the real service is normally absent, so `enforceOverride=true` fails as designed.
3. Multiple beans of the same type may require an explicit qualifier/bean name; the framework cannot always guess which bean to replace.
4. Different mock configurations change the context cache key, causing the suite to spin up extra contexts.
5. Replacement mock beans may lack proxies/advice from the original bean; never use them to assert `@Transactional`, retry, security, or production caching behavior.

In Spring Boot 3.3 and earlier, `@MockBean` was the common API; in Boot 3.4 it was deprecated in favor of the new Spring TestContext API. Never mix versions/annotations without re-checking context behavior.

## 20. Performance, Context Caching, and Test Isolation

A properly layered test suite catches bugs effectively while keeping operational cost under control.

- **Unit tests + `StepVerifier`**: no context; typically fast with minimal environment dependencies.
- **WebFlux slice**: loads required web infrastructure, usually lighter than a full Boot context.
- **Full context mock HTTP**: checks wiring/auto-configuration and real Spring flows without TCP.
- **Full context random port**: additionally checks embedded server and transport; higher startup/runtime cost.
- **DB/broker/remote integration**: adds tools and cleanup; higher cost yet protects contracts mocks cannot replace.

Spring TestContext caches `ApplicationContext` by configuration. Two tests with identical bootstrap settings share one context within the JVM; tests differing in `@ActiveProfiles`, test properties, `@MockitoBean`, imports, or web environment typically require separate cache keys. Thus creating dozens of unnecessary `@SpringBootTest`/mock-bean combinations can slow CI even when each test is only a few lines long.

**Test isolation:** a full context contains singleton beans, connection pools, and data stores; one test mutating state can affect another. Context caching does not automatically reset every mutable singleton or external store. Use independent test data, cleanup/fake resets, and intentional test design. Never slap `@DirtiesContext` onto every method just to force tests green; it adds startup cost and still does not clean up external resources.

## 21. Gradle and Commands to Run the Example Suite

In a Gradle project already configuring the **Spring Boot 3.5.x plugin/BOM**, Java 17+, and repositories, you can use this dependencies block:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

This is an **additive configuration snippet for a build already containing plugins and version management**, not a standalone `build.gradle`. If `spring-boot-starter-test` already pulls in `reactor-test` in your version's dependency graph, no duplicate is needed; inspect with Gradle `dependencies`.

**Do not add `spring-boot-starter-web` to the example** because that can switch the application type to servlet by default and break consistency with the WebFlux goal.

The test directory needs three files:

```text
QuoteServiceUnitTest.java
QuoteWebFluxSliceTest.java
QuoteFullHttpTest.java
```

Run commands:

```bash
./gradlew test --tests com.example.webfluxscope.QuoteServiceUnitTest --tests com.example.webfluxscope.QuoteWebFluxSliceTest --tests com.example.webfluxscope.QuoteFullHttpTest
```

On Windows PowerShell:

```powershell
.\gradlew.bat test --tests com.example.webfluxscope.QuoteServiceUnitTest --tests com.example.webfluxscope.QuoteWebFluxSliceTest --tests com.example.webfluxscope.QuoteFullHttpTest
```

In multi-project Gradle builds, target `:your-module:test` per your actual module name.

**Designed outcomes in the example code:**

- `QuoteServiceUnitTest` has **4** tests protecting the real reactive policy/service.
- `QuoteWebFluxSliceTest` has **2** tests protecting the WebFlux slice's mapping/JSON/error advice with a mock service.
- `QuoteFullHttpTest` has **3** tests protecting HTTP requests over a real server, real service/policy/catalog, and 404/400.
- Total of **9 test methods**. With proper project configuration, all are expected green; Gradle reports `BUILD SUCCESSFUL`.
- The demo service prints no fixed business stdout. Server logs, random ports, and runtimes must not be treated as fixed expected output.

These are **expected outcomes from code analysis**, not a claim that Gradle was executed or a server started in the current repository. Sections labeled **snippet** elsewhere are not standalone Java files in the runnable list.

You can open Gradle's report at `build/reports/tests/test/index.html`, or XML in `build/test-results/test/` under the module's build directory.

## 22. Troubleshooting: Reading Errors by Layer

| Symptom | Possible Cause | Resolution |
|---|---|---|
| `NoSuchBeanDefinitionException: QuoteService` in slice | `@WebFluxTest` does not scan services | Use `@MockitoBean` at the boundary or import needed collaborators |
| Slice passes yet production miscalculates prices | Service is mocked in slice | Add unit/service tests running real logic and appropriate integration tests |
| Slice returns 404 for functional endpoint | `RouterFunction` not auto-discovered | `bindToRouterFunction`, `@Import`, or full Boot test |
| HTTP 200 in slice yet full context fails | Bean, property, profile, auto-config, or external dependency omitted by slice | Debug root cause in full context rather than patching with random mocks |
| `WebTestClient` null in full mock context | Missing `@AutoConfigureWebTestClient` or wrong web application type | Add annotation and check starters/type |
| Full random-port test fails to connect | Server startup failed, port/client wiring, or wrong web stack | Read startup logs, root exception, use random port, check dependencies |
| Unexpected 401/403 response | `SecurityWebFilterChain` differs from expectations or test credentials missing | Set up security test per contract, never disable security recklessly |
| HTTP test fails to roll back DB | Server request runs in a different transaction/context | Use isolated test DB and explicit cleanup; never rely on test-method transactions |
| `Flux` test hangs | Stream never completes while test awaits completion | Assert finite event counts, cancellation, and timeouts |
| Reactive code fails due to blocking call | Real service performs blocking I/O on event loop | Isolate blocking adapter, use proper scheduler or reactive driver; add integration/concurrency tests |
| Single test passes yet fails in suite | Shared singleton/DB/context-cache state | Independent data, cleanup, avoid test order assumptions |
| Enabling both web and webflux switches stack | Boot prioritizes Servlet/MVC application type | Choose starters/type explicitly and verify exact web stack |
| Mock server passes yet production TLS/gateway fails | Slice/full mock env lacks that network transport | Add staging/infrastructure HTTP tests through real boundary |
| Full context very slow | Loading excessive infrastructure or fragmented context cache | Push pure logic to unit tests, use slices/targeted integration, consolidate configs |

**Step-by-step debugging:**

1. Identify the test annotation and `webEnvironment`.
2. Identify whether `WebTestClient` binds to a controller/context or a TCP server.
3. Check which beans are Mockito mocks and which are real implementations.
4. Read the root cause of `Failed to load ApplicationContext`, distinguishing missing beans, auto-config, profiles, and connections.
5. Confirm whether test data comes from fakes/in-memory fixtures or external adapters.
6. Add tests at the missing boundary; never start the whole app just because one controller test failed.
7. After fixing, rerun both fast tests and matching integration tests so coverage is not lost at another layer.

## 23. Self-Check Exercises

### Exercise A — Does a Green Test Prove Business Logic Works?

`@WebFluxTest` uses `@MockitoBean QuoteService` returning `QuoteView(totalVnd=216000)`. The controller returns the exact JSON; the test passes. If production's `DiscountPolicy` changes from 10% to 5%, will this test fail?

**Answer:** Not necessarily, because the real service and policy never ran. Add `StepVerifier` tests on the real service, and an integration test exercising service/policy when needed.

### Exercise B — Pick One of the Three Environments

Requirements:

1. Check `@GetMapping` and JSON fields.
2. Check Spring context wiring of controller/service/repository without networking.
3. Check real HTTP server port binding.

**Suggested answers:** (1) `@WebFluxTest`, (2) `@SpringBootTest` + `@AutoConfigureWebTestClient` with mock web environment, (3) `@SpringBootTest(RANDOM_PORT)`.

### Exercise C — Functional Routing

An app declares endpoints via `RouterFunction<ServerResponse>`. A `@WebFluxTest` targeting another annotated controller passes, while the functional endpoint vanishes. Is the production route broken?

**Answer:** Insufficient evidence. `@WebFluxTest` does not automatically discover all functional routes. Test with `bindToRouterFunction` or import the router/handler intentionally; to verify production registration use a full Boot context.

### Exercise D — Reactive Database and HTTP

A JUnit method has `@Transactional`, the test calls HTTP via `RANDOM_PORT`, and afterward the record remains in the DB. Why did the test's rollback not clear it?

**Answer:** The HTTP server runs in a separate request/transaction context; reactive transactions use Reactor Context and have their own boundaries. Use explicit cleanup, an isolated test DB, or proper transaction/fixture design.

### Exercise E — Evaluating Test Doubles

In a web slice, mocking `QuoteService` makes sense because the controller is the target. In a service unit test, does mocking `QuoteService` itself and asserting the mocked return value mean anything?

**Answer:** Virtually no real code is tested; it only proves stubbing. Service unit tests should use the real service with a fake/mock outbound gateway and assert business outcomes.

### Exercise F — Security

A test with `@WithMockUser` passes through a WebFlux slice with HTTP 200. Can you conclude production's JWT parser and OAuth2 issuer work?

**Answer:** No. A mock user simulates a principal; you need security integration/HTTP tests for real decoders/issuers/authority mapping and the real filter chain using appropriate token fixtures.

### Exercise G — Streaming

An endpoint returns an infinite `Flux<ServerSentEvent<Event>>`. Why will `StepVerifier.expectComplete()` hang? State how to verify a finite event count with `thenCancel` or timeouts. If TCP flushing must be protected, what test must be added?

**Answer:** The stream never emits `onComplete` per contract; use finite expectations + cancellation and add a real-server HTTP stream integration test when needed.

### Exercise H — Defining "Full"

You have `@SpringBootTest(RANDOM_PORT)`, yet the repository is an in-memory fake and outbound `WebClient` is mocked. Can you call this an E2E test with a real DB and remote service?

**Answer:** No. It is a full application/server test within the scope of configured dependencies. Report coverage strictly per the components that actually ran.

## 24. Final WebFlux Testing Checklist

- [ ] I stated clearly which bug the test must catch.
- [ ] I know `@WebFluxTest` loads the web layer and usually excludes services/repositories.
- [ ] I do not mistake test-created mock beans for real scanned services.
- [ ] I verify HTTP contracts with `WebTestClient`, without claiming business policies are verified when policies never ran.
- [ ] I have unit/service tests using `StepVerifier` for core reactive logic.
- [ ] Functional routes are tested with appropriate router tests/imports/full context.
- [ ] I distinguish a mock web environment from a `RANDOM_PORT` HTTP server.
- [ ] When DI/profiles/auto-config need proof, I use a full context without accidentally mocking key beans.
- [ ] When network runtime needs proof, I start a real server and verify requests over TCP.
- [ ] When DB/transactions need proof, I use repository/DB tests at the right boundary rather than relying on fakes.
- [ ] I do not assume JUnit method transactions roll back server requests.
- [ ] Security, `WebFilter`s, error handlers, and configs are properly loaded for the contract under test.
- [ ] Reactive streams, errors, backpressure, and cancellation are tested at the appropriate level.
- [ ] External HTTP/brokers/queues have separate contract or integration tests; never call uncontrolled production systems.
- [ ] Singleton state, context caches, and test data are isolated.
- [ ] The test suite has small, understandable layers rather than using full contexts for cheap calculations.

**Conclusion:** `@WebFluxTest` is an excellent tool for verifying **the web slice**. It is fast and focused precisely because it skips running every service, repository, transaction, functional route, or external adapter in the system. For that very reason, a valid JSON response from a mocked service **is not proof that the entire application works**. For thorough protection, keep small tests covering real logic, and add `@SpringBootTest`, real HTTP server, database, and external-contract tests **at the exact boundaries where target failures occur**.

### Official References

- Spring Boot 3.5 — Testing Spring Boot Applications, *Auto-configured Spring WebFlux Tests*: https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html
- Spring Boot 3.5 JavaDoc — `@WebFluxTest` and component scanning limits: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/autoconfigure/web/reactive/WebFluxTest.html
- Spring Framework — `WebTestClient`, controller/context/router/server binding: https://docs.spring.io/spring-framework/reference/testing/webtestclient.html
- Spring Framework — Reactive Transactions: https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html
- Reactor — Testing & `StepVerifier`: https://projectreactor.io/docs/core/release/reference/testing.html
