# Reactive Filters and Slice Dependency Configuration

## 1. Problem: Does a WebFlux Controller Test Traverse Filters Like the Real Application?

In Spring WebFlux, an HTTP request does not necessarily go straight to `@RestController`. Before the handler is invoked, the request can pass through **`WebFilter`s** used for correlation IDs, authorization, tenant checks, logging, access control, or adding HTTP headers. A filter can **block the request**, modify the `ServerWebExchange`, invoke the next filter, or react to completion signals of the reactive chain.

When writing `@WebFluxTest`, Spring Boot builds a **test slice** containing WebFlux infrastructure and permitted components rather than loading the entire application context. Consequently, a controller test can turn green while a crucial filter is missing, or the context can fail to start because a filter depends on a `@Service`/configuration-properties bean that was excluded from the slice.

For example, the application requires the `X-Client-Id` header and checks the client via `ClientAccessPolicy` before allowing `GET /api/quotes/Q-1`:

~~~text
HTTP GET /api/quotes/Q-1
  |
  | X-Client-Id: demo
  v
ClientGateWebFilter
  |
  +-- missing header -----> 400 Bad Request
  |
  +-- policy denies ------> 403 Forbidden
  |
  +-- policy allows ------> WebFilterChain.filter(exchange)
                              |
                              v
                          QuoteController
                              |
                              v
                          QuoteCatalog (mock)
                              |
                              v
                          200 + JSON, or 404
~~~

A meaningful test suite must prove the **exact boundary**: the filter blocks invalid inputs properly; valid requests reach the controller; controller/filter dependencies are the mocks you explicitly provided; and the response truly has the status/headers/body specified by the contract.

**This exercise uses Java 17, Spring Boot 3.5.x / Spring Framework 6.2, JUnit Jupiter, Reactor, and `WebTestClient`.** Spring Boot 4.x reorganized several test modules/packages; do not copy Boot 3.5 imports verbatim to Boot 4 without verifying matching dependencies.

## 2. WebFilter, WebFilterChain, and Mono<Void>

Spring WebFlux uses this contract:

~~~java
public interface WebFilter {
    Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain
    );
}
~~~

Key types:

| Type | Role |
| --- | --- |
| `WebFilter` | Intercepts a server-side HTTP exchange |
| `ServerWebExchange` | Request, response, attributes, and context information for one exchange |
| `WebFilterChain` | Represents subsequent filters and ultimately the `WebHandler` |
| `Mono<Void>` | Publisher representing asynchronous processing and completion/error/cancel signals |
| `WebTestClient` | Client for testing WebFlux via a mock server or real server |
| `@WebFluxTest` | Spring Boot web slice loading only web infrastructure and related components |

Unlike synchronous code:

~~~java
// NOT the right way to write a reactive filter:
chain.filter(exchange).subscribe();
return Mono.empty();
~~~

If you call `subscribe()` manually and return `Mono.empty()`, the filter loses the ability to propagate completion, error, and cancellation signals along the framework-managed chain; the request can finish at the wrong time. **Return the publisher from the processing chain itself**, e.g., `return chain.filter(exchange);`, or compose using Reactor operators.

A `WebFilter` has three main behaviors:

~~~java
// 1. Pass through:
return chain.filter(exchange);

// 2. Reject immediately (without calling chain):
exchange.getResponse().setStatusCode(HttpStatus.FORBIDDEN);
return exchange.getResponse().setComplete();

// 3. Check asynchronously before deciding:
return accessPolicy.isAllowed(clientId)
        .flatMap(allowed -> allowed
                ? chain.filter(exchange)
                : deny(exchange));
~~~

These are **illustrative logic snippets**, not a standalone Java class. The last snippet assumes `accessPolicy` returns `Mono<Boolean>` and a `deny` method exists. If the publisher can be empty, explicitly specify how `Mono.empty()` is handled; never let a request complete silently without calling the handler or setting a proper status.

### What Can a Filter Modify?

- Read `exchange.getRequest().getHeaders()` and URI.
- Write headers to `exchange.getResponse().getHeaders()` **before the response commits**.
- Store attributes via `exchange.getAttributes().put(...)`.
- Choose to call `chain.filter(exchange)` once, or return a response immediately.
- Use `doOnError`/`doFinally` to measure and record processing signals; note `doFinally` is invoked on cancellation too.
- For streaming request or response bodies, use `ServerHttpRequestDecorator`/`ServerHttpResponseDecorator` and understand `DataBuffer` reference counting/lifecycle; do not arbitrarily read bodies as a `String` unless required.

**Do not store per-request state in instance fields of a `WebFilter`** because the filter is a singleton bean typically shared across many concurrent requests. Use local variables, exchange attributes, or the Reactor Context to isolate state per request.

## 3. Which Beans Does @WebFluxTest Include, and Which Does It Exclude?

`@WebFluxTest(QuoteController.class)` focuses on **annotated reactive controllers** and WebFlux infrastructure. According to Spring Boot 3.5 documentation, the slice supports web-focused components such as `@Controller`, `@ControllerAdvice`, converters, and `WebFluxConfigurer`; the `@WebFluxTest` Javadoc also lists supported types including `WebFilter` and `WebExceptionHandler` within filtered component scanning.

However, **do not confuse an allowed type with "every bean of that type anywhere gets loaded"**:

- A `@Component` whose type is allowed by the scan filter can be discovered via component scanning when it resides in a valid scanned package.
- A `@Bean WebFilter` declared inside a **separate `@Configuration` class** is not automatically pulled into the slice just because its return type is `WebFilter`; configuration classes are normally excluded from slice scanning.
- Regular services/repositories and `@ConfigurationProperties` are typically excluded from the slice; a controller or filter depending on them can trigger `UnsatisfiedDependencyException`.
- A custom `SecurityWebFilterChain` bean from a `@Configuration` is also **not auto-detected by `@WebFluxTest`** per Boot documentation. When the goal is testing the real security chain, import the config or use `@SpringBootTest`.

Because of these differences by bean source and version, the example in this lesson **registers the filter using `@Import(ClientGateWebFilter.class)`**, and the filter intentionally **has no `@Component`**. This gives exact control over the test slice without guessing whether Spring discovered the filter.

### Three Common Ways to Supply Dependencies to a Slice

| What the Test Needs | How to Supply It | Meaning |
| --- | --- | --- |
| Real bean holding logic under test, e.g., filter | `@Import(ClientGateWebFilter.class)` | Runs the real filter and intercepts the exchange |
| Collaborator outside slice, e.g., `ClientAccessPolicy` | `@MockitoBean ClientAccessPolicy policy;` | Replaces/registers a Spring mock bean for deterministic decisions |
| Small config with `@Bean`s needing to run for real | `@Import(FilterTestConfiguration.class)` | Loads intentionally declared `@Bean` definitions |
| Configuration properties for a filter | `@EnableConfigurationProperties(GateProperties.class)` + test properties | Boot's binder constructs the exact properties bean |
| Running all beans, security config, and multi-layer wiring | `@SpringBootTest` | Broad integration test, no longer a narrow web slice |

`@MockitoBean` is a Spring Framework 6.2+ API present in Spring Boot 3.4/3.5; do not use plain `@Mock` expecting it to replace a bean in the Spring context. Boot's older `@MockBean` was deprecated in Boot 3.4 and is not a drop-in alias in every situation.

## 4. Complete Example: Testing a Filter, Controller, and Dependencies in One Slice

Let us design a simple API:

- `GET /api/quotes/{id}` looks up a quote via `QuoteCatalog` and returns JSON when found.
- `ClientGateWebFilter` requires `X-Client-Id` before accessing the route.
- If the header is missing/blank: **400**, calling neither policy nor catalog.
- If policy returns `false` or `Mono.empty()`: **403**, without calling catalog.
- If policy returns `true`: filter adds `X-Gate-Checked: true` and calls the chain.
- If the quote does not exist: controller returns **404**. The filter **must not turn 404 into 403** just because the service returned empty.

Tests run against the **mock WebFlux server**; no TCP port is opened, no network services are called, and no database is required.

### 4.1. Java 17 Project Configuration

In a Spring Boot **3.5.x** project using Gradle Groovy DSL, the relevant dependencies and test task in `build.gradle` are:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

This is **not the entire build file**. The project also needs the Spring Boot 3.5.x plugin, dependency management, repositories, and JDK/toolchain 17+. **Do not** add `spring-boot-starter-web` (Servlet MVC) to the demo so the web application type is unambiguous. `starter-test` provides JUnit Jupiter, Mockito, and Spring Boot Test; `starter-webflux` puts Reactor/WebFlux on the classpath.

File structure:

~~~text
src/main/java/com/example/fluxtest/
  FluxTestApplication.java
  QuoteView.java
  QuoteCatalog.java
  ClientAccessPolicy.java
  QuoteController.java
  ClientGateWebFilter.java
src/test/java/com/example/fluxtest/
  QuoteControllerFilterSliceTest.java
~~~

### 4.2. Application Class for Spring Boot Root Configuration

**`src/main/java/com/example/fluxtest/FluxTestApplication.java`:**

~~~java
package com.example.fluxtest;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class FluxTestApplication {
    public static void main(String[] args) {
        SpringApplication.run(FluxTestApplication.class, args);
    }
}
~~~

`@WebFluxTest` uses the root application configuration to initialize the slice, yet **does not invoke `main`** and does not load every bean like a full `@SpringBootTest`.

### 4.3. Model and Two Collaborators

**`src/main/java/com/example/fluxtest/QuoteView.java`:**

~~~java
package com.example.fluxtest;

public record QuoteView(String id, String text) {
}
~~~

**`src/main/java/com/example/fluxtest/QuoteCatalog.java`:**

~~~java
package com.example.fluxtest;

import reactor.core.publisher.Mono;

public interface QuoteCatalog {
    Mono<QuoteView> findById(String id);
}
~~~

**`src/main/java/com/example/fluxtest/ClientAccessPolicy.java`:**

~~~java
package com.example.fluxtest;

import reactor.core.publisher.Mono;

public interface ClientAccessPolicy {
    Mono<Boolean> isAllowed(String clientId);
}
~~~

Both collaborators are interfaces because in this lesson we want to test **WebFlux controller/filter wiring and behavior**, not how quotes are queried or clients are authenticated in a real system. In production, implementing beans might call Redis, a database, or non-blocking HTTP; in a slice test they are supplied via mocks.

### 4.4. Real Controller Using Mono

**`src/main/java/com/example/fluxtest/QuoteController.java`:**

~~~java
package com.example.fluxtest;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/quotes")
public class QuoteController {
    private final QuoteCatalog catalog;

    public QuoteController(QuoteCatalog catalog) {
        this.catalog = catalog;
    }

    @GetMapping(value = "/{id}", produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<QuoteView> find(@PathVariable String id) {
        return catalog.findById(id)
                .switchIfEmpty(Mono.error(
                        new ResponseStatusException(
                                HttpStatus.NOT_FOUND, "Quote not found"
                        )
                ));
    }
}
~~~

The controller knows nothing about `X-Client-Id`. That is the filter's **cross-cutting concern**. A 404 response only happens when the request reaches the controller, the catalog returns `Mono.empty()`, and `switchIfEmpty` turns it into an HTTP 404 error. Do not assume `Mono.empty()` in any handler automatically means HTTP 404: behavior must be explicitly defined.

### 4.5. Real WebFilter, Without Blocking or Subscribing

**`src/main/java/com/example/fluxtest/ClientGateWebFilter.java`:**

~~~java
package com.example.fluxtest;

import java.util.Objects;

import org.springframework.http.HttpStatus;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;

import reactor.core.publisher.Mono;

public final class ClientGateWebFilter implements WebFilter {
    private final ClientAccessPolicy policy;

    public ClientGateWebFilter(ClientAccessPolicy policy) {
        this.policy = Objects.requireNonNull(policy, "policy");
    }

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain
    ) {
        String clientId = exchange.getRequest()
                .getHeaders()
                .getFirst("X-Client-Id");

        if (clientId == null || clientId.isBlank()) {
            exchange.getResponse().setStatusCode(HttpStatus.BAD_REQUEST);
            return exchange.getResponse().setComplete();
        }

        return policy.isAllowed(clientId)
                .defaultIfEmpty(false)
                .flatMap(allowed -> {
                    if (!allowed) {
                        exchange.getResponse()
                                .setStatusCode(HttpStatus.FORBIDDEN);
                        return exchange.getResponse().setComplete();
                    }

                    exchange.getResponse()
                            .getHeaders()
                            .set("X-Gate-Checked", "true");

                    return chain.filter(exchange);
                });
    }
}
~~~

Explanation:

1. The filter reads the header without **modifying shared data**, using only the local `clientId` variable.
2. Missing/blank client ID → returns `setComplete()` with status 400, **without calling `chain.filter`**.
3. `policy.isAllowed(clientId)` returns `Mono<Boolean>`. `defaultIfEmpty(false)` prevents the case where the policy completes empty and the filter silently skips forwarding the request to the chain.
4. Policy denies → status 403, completes the exchange.
5. Policy allows → sets the header before downstream can commit the response, then **returns** `chain.filter(exchange)`.
6. Never calls `block()`, `subscribe()`, or `Thread.sleep()` inside the filter.

The code neither carries `@Component` nor declares a production `@Bean`. **This is an intentional demo choice:** the test registers the filter with `@Import`; in a real application, register the filter bean via `@Component` or a `@Configuration` with `@Bean`, depending on project structure. If you forget to register it at runtime, the filter will **not** be applied; a web slice test cannot prove production wiring when configurations differ.

### 4.6. WebFlux Slice Test: Mock Dependencies, Import Filter, and Assert the Whole Path

**`src/test/java/com/example/fluxtest/QuoteControllerFilterSliceTest.java`:**

~~~java
package com.example.fluxtest;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.WebFluxTest;
import org.springframework.context.annotation.Import;
import org.springframework.http.MediaType;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.reactive.server.WebTestClient;

import reactor.core.publisher.Mono;

import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

@WebFluxTest(QuoteController.class)
@Import(ClientGateWebFilter.class)
class QuoteControllerFilterSliceTest {
    @Autowired
    WebTestClient client;

    @MockitoBean
    QuoteCatalog catalog;

    @MockitoBean
    ClientAccessPolicy policy;

    @Test
    void allowedClient_whenQuoteExists_getsJsonAndFilterHeader() {
        when(policy.isAllowed("demo")).thenReturn(Mono.just(true));
        when(catalog.findById("Q-1"))
                .thenReturn(Mono.just(new QuoteView("Q-1", "Hello")));

        client.get()
                .uri("/api/quotes/{id}", "Q-1")
                .header("X-Client-Id", "demo")
                .accept(MediaType.APPLICATION_JSON)
                .exchange()
                .expectStatus().isOk()
                .expectHeader().valueEquals(
                        "X-Gate-Checked", "true"
                )
                .expectHeader().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON
                )
                .expectBody()
                .jsonPath("$.id").isEqualTo("Q-1")
                .jsonPath("$.text").isEqualTo("Hello");

        verify(policy).isAllowed("demo");
        verify(catalog).findById("Q-1");
    }

    @Test
    void missingClientHeader_isRejectedBeforeDependencies() {
        client.get()
                .uri("/api/quotes/Q-1")
                .exchange()
                .expectStatus().isBadRequest()
                .expectBody().isEmpty();

        verifyNoInteractions(policy, catalog);
    }

    @Test
    void deniedClient_isForbiddenBeforeController() {
        when(policy.isAllowed("blocked"))
                .thenReturn(Mono.just(false));

        client.get()
                .uri("/api/quotes/Q-1")
                .header("X-Client-Id", "blocked")
                .exchange()
                .expectStatus().isForbidden()
                .expectBody().isEmpty();

        verify(policy).isAllowed("blocked");
        verifyNoInteractions(catalog);
    }

    @Test
    void emptyPolicyDecision_isRejectedRatherThanBypassingFilter() {
        when(policy.isAllowed("unknown"))
                .thenReturn(Mono.empty());

        client.get()
                .uri("/api/quotes/Q-1")
                .header("X-Client-Id", "unknown")
                .exchange()
                .expectStatus().isForbidden();

        verify(policy).isAllowed("unknown");
        verifyNoInteractions(catalog);
    }

    @Test
    void allowedClient_whenQuoteMissing_stillGets404FromController() {
        when(policy.isAllowed("demo")).thenReturn(Mono.just(true));
        when(catalog.findById("missing")).thenReturn(Mono.empty());

        client.get()
                .uri("/api/quotes/missing")
                .header("X-Client-Id", "demo")
                .exchange()
                .expectStatus().isNotFound()
                .expectHeader().valueEquals(
                        "X-Gate-Checked", "true"
                );

        verify(policy).isAllowed("demo");
        verify(catalog).findById("missing");
    }
}
~~~

The five-test suite verifies **the real filter running inside the WebFlux chain**:

| Case | Filter | Mock Catalog | Response |
| --- | --- | --- | --- |
| Valid client, quote found | Calls policy → forwards → adds header | Called | 200, header and JSON match |
| Missing header | Blocks immediately | Not called | 400, empty body |
| Policy returns false | Blocks after check | Not called | 403, empty body |
| Policy returns `Mono.empty()` | Denies by default | Not called | 403 |
| Policy allows, quote missing | Forwards request | Called and returns empty | 404 decided by controller |

**Why is `verify` also needed?** Merely checking status 403 does not prove the filter blocked **before the controller**; `verifyNoInteractions(catalog)` enforces the short-circuit behavior. Conversely, 200 + JSON + filter header shows valid requests pass through the filter and reach the controller.

`@MockitoBean` creates mocks as **beans in the Spring context**, not merely standalone Mockito fields. `@Import(ClientGateWebFilter.class)` guarantees the real filter is present; its constructor receives the mock `ClientAccessPolicy`, while the controller receives the mock `QuoteCatalog`.

### 4.7. Running the Tests

From the project directory with the Gradle Wrapper:

~~~bash
./gradlew test --tests "com.example.fluxtest.QuoteControllerFilterSliceTest"
~~~

On Windows PowerShell:

~~~powershell
.\gradlew.bat test --tests "com.example.fluxtest.QuoteControllerFilterSliceTest"
~~~

The example has one test class with **five `@Test`s**. With Spring Boot 3.5.x, JUnit Jupiter/Mockito, and WebFlux dependencies as described, all five tests are expected to PASS. There is no `System.out.println`, so **application code produces no fixed stdout**; Gradle/JUnit/Spring logs depend on configuration. Do not compile/run the test file with plain `javac` without supplying the Spring/JUnit classpath.

**Limitation:** the example demonstrates importing the filter in the **test**. It proves filter behavior in the WebFlux slice, without automatically proving that the production app registered `ClientGateWebFilter`. To test production wiring, add an integration test at the appropriate layer or register the real bean in production configuration and test that configuration.

## 5. Two Ways to Register a WebFilter: Component vs @Bean

Spring WebFlux uses `WebFilter` beans present in the `ApplicationContext` to process requests. Thus, how the bean is created determines whether the filter is available in a slice.

### 5.1. @Component Filter

~~~java
@Component
public class ClientGateWebFilter implements WebFilter {
    // filter(...) and constructor as in Section 4.
}
~~~

This is only an **annotation illustration snippet**, not a complete class file; `@Component` must be imported from `org.springframework.stereotype.Component`. When the filter is a component inside the scan scope, `@WebFluxTest` can detect it via Boot's filters; the Boot 3.5 Javadoc lists `WebFilter` among the types that can be retained. **Do not assume every `@Component` in any package is loaded**; components are still subject to component scanning, type exclude filters, and specified include/exclude filters.

If you use `@Component` and the filter is actually scanned by the slice, **do not import the same filter again carelessly**, risking duplicate bean definitions/instances or confusing configuration state. Choose **one** explicit way to supply the bean.

### 5.2. @Configuration Containing @Bean

~~~java
@Configuration(proxyBeanMethods = false)
public class GateConfiguration {
    @Bean
    WebFilter clientGateWebFilter(ClientAccessPolicy policy) {
        return new ClientGateWebFilter(policy);
    }
}
~~~

This is an **illustrative class snippet**, requiring imports for `@Configuration`, `@Bean`, `WebFilter`, and same-package classes. A custom `@Configuration` class like `GateConfiguration` is usually not scanned by the slice by default. To test that bean configuration for real, use:

~~~java
@WebFluxTest(QuoteController.class)
@Import(GateConfiguration.class)
class QuoteWithGateConfigTest {
    // @MockitoBean for ClientAccessPolicy and QuoteCatalog.
}
~~~

This is a **skeleton**, not a standalone runnable test. When choosing this approach, **remove `@Import(ClientGateWebFilter.class)`** from the main example; otherwise two filters may be registered. A configuration containing unrelated datasources/clients/queues can also pull in unwanted dependencies; **import small, tightly scoped configurations**.

### 5.3. Filter Using @ConfigurationProperties

If a filter needs configuration such as enable/disable flags or timeouts:

~~~java
@ConfigurationProperties(prefix = "app.gate")
public record GateProperties(boolean enabled) {
}
~~~

This record is a **separate file** importing `org.springframework.boot.context.properties.ConfigurationProperties`. By default, slices do not scan all `@ConfigurationProperties`. To make the bean exist in `@WebFluxTest`:

~~~java
@WebFluxTest(
        controllers = QuoteController.class,
        properties = "app.gate.enabled=true"
)
@EnableConfigurationProperties(GateProperties.class)
@Import(ClientGateWebFilter.class)
class QuoteWithPropertiesTest {
    // Mocks/fields/tests matching the actual constructor.
}
~~~

This example is intentionally a skeleton. Because `ClientGateWebFilter` in Section 4 does not yet accept `GateProperties`, this annotation only illustrates how to **register the properties bean**, without creating new toggle behavior. Only assert enabled/disabled behavior once the filter actually uses that property.

**Do not use `@TestPropertySource` or `@WebFluxTest(properties=...)` and assume the properties bean appears automatically**; having test property sources is different from having a `@ConfigurationProperties` bean registered.

## 6. Slice Dependency Configuration: Mock, Import, or Full Context?

Faced with an error like:

~~~text
UnsatisfiedDependencyException:
No qualifying bean of type 'ClientAccessPolicy' available
~~~

consider **the subject under test**:

- **Goal is the filter and reactive HTTP boundary:** Keep the filter/controller real; use `@MockitoBean ClientAccessPolicy` for out-of-slice policy. That is what the main example does.
- **Goal is the policy implementation:** Do not mock the policy; import the real implementation with its needed dependencies or write a dedicated unit test for the policy.
- **Goal is a config defining a `@Bean` filter:** Import that tightly scoped config. Do not import entire production packages/configs beyond what is needed.
- **Goal is real Spring Security wiring:** Import the custom security configuration and use `spring-security-test` to supply appropriate principals, JWTs/CSRF; or use full `@SpringBootTest`.
- **Goal is end-to-end controller → service → repository:** Consider `@SpringBootTest` instead of trying to turn `@WebFluxTest` into a full integration test with dozens of `@Import`s.

| Tool | Responsibility | Risk When Misused |
| --- | --- | --- |
| `@MockitoBean` | Creates/replaces a mock bean in Spring context | Mocking the filter under test prevents the real filter from running |
| `@Import(Foo.class)` | Imports a real bean/config into context | May pull in extra out-of-slice dependencies |
| `@EnableConfigurationProperties(FooProperties.class)` | Registers config properties type for binder | Does not replace service mocks/beans |
| `@WebFluxTest(includeFilters = ...)` | Selectively widens scanning rules | Hard to follow which source registered which beans |
| `@WebFluxTest(excludeFilters = ...)` | Excludes unwanted components from slice | Can accidentally drop filters/security needing to be tested |
| `@SpringBootTest` | Loads broad integration per app config | Slower, wider scope than an isolated filter test |

### Does @Import Mean the Filter Runs Automatically in Every Case?

No. `@Import` registers the bean with the context. The filter runs when it is a `WebFilter` bean belonging to the **actually constructed WebFlux server chain**. If you use a plain `WebTestClient.bindToController(new QuoteController(...))` without connecting a Spring application context, it will not discover filter beans imported into some other test context.

Therefore, to test Spring bean wiring, the main example injects the `WebTestClient` **auto-configured by `@WebFluxTest` from the context**. If building a client manually with `bindToController`, explicitly configure/bind filters through the matching builder API instead of assuming context beans are attached automatically.

## 7. Filter Ordering and Correctly Interpreting Spring Security's Position

When multiple `WebFilter`s exist, Spring WebFlux has a **filter order**. You can use `org.springframework.core.Ordered` or `@Order`:

~~~java
@Order(Ordered.HIGHEST_PRECEDENCE + 100)
public final class RequestTraceWebFilter implements WebFilter {
    @Override
    public Mono<Void> filter(ServerWebExchange exchange,
                             WebFilterChain chain) {
        exchange.getResponse().getHeaders()
                .add("X-Trace", "observed");
        return chain.filter(exchange);
    }
}
~~~

This is an **illustrative class**, requiring proper imports and bean registration; it is not meant to be added to the main example. **Lower** order values run earlier on the inbound phase; after `chain.filter(...)`, completion/termination operators can observe the outbound phase of the reactive sequence.

Spring Boot WebFlux defines several system filter orders. For instance, Spring Security's `WebFilterChainProxy` commonly has order `-100` in Boot configuration, yet **do not treat that number as an immutable constant across all versions and custom filters**. Choose order values from actual requirements and test interactions with security when present.

### Why Can a Filter Running Before Security Be a Problem?

If a filter checks tenant/correlation IDs and returns a different error before Spring Security runs, unauthenticated users may receive a different status than expected. Conversely, if authentication must be established before a filter reads the principal, place the filter **after** security or use an appropriate security filter mechanism. For authorization, prefer Spring Security's `SecurityWebFilterChain` rather than hand-rolling custom security logic inside a `WebFilter`.

Tests can verify execution flow through HTTP outcomes rather than necessarily asserting every internal call. When ordering is a critical contract, write filter tests that trace execution with proper concurrency management or test observable effects directly.

### Response Headers and Commit Timing

Headers must be set **before the response commits**. In the main example, `X-Gate-Checked` is set before `chain.filter(exchange)`. If you use `doFinally(...)` to set an HTTP header **after downstream finishes**, the response may already be committed so the header has no effect; `doFinally` suits metrics/tracing, not safely modifying response headers.

When a hook right before commit is needed, look at `exchange.getResponse().beforeCommit(...)`, keeping the callback reactive and non-blocking. Do not make synchronous assumptions for HTTP body streaming.

## 8. How Does SecurityWebFilterChain Differ from a Custom WebFilter?

Spring Security for WebFlux builds a `SecurityWebFilterChain` to enforce authentication, authorization, CSRF, sessions, OAuth2, and more per configuration. In WebFlux, Spring Security infrastructure operates via `WebFilterChainProxy` and specialized filters.

**Boot docs state clearly:** `@WebFluxTest` does not auto-discover a custom `@Bean SecurityWebFilterChain` located in a separate application configuration. To test **real custom security rules**, import the configuration defining that bean into the slice, or use a full `@SpringBootTest`.

Illustrative security configuration:

~~~java
@Configuration(proxyBeanMethods = false)
@EnableWebFluxSecurity
public class ApiSecurityConfiguration {

    @Bean
    SecurityWebFilterChain springSecurityFilterChain(
            ServerHttpSecurity http
    ) {
        return http
                .csrf(ServerHttpSecurity.CsrfSpec::disable)
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers("/public/**").permitAll()
                        .anyExchange().authenticated())
                .httpBasic(Customizer.withDefaults())
                .build();
    }
}
~~~

**This is a separate illustrative class**, requiring the `spring-boot-starter-security` dependency and imports: `@Configuration`, `@Bean`, `@EnableWebFluxSecurity`, `SecurityWebFilterChain`, `ServerHttpSecurity`, `Customizer`. `csrf(...disable)` only illustrates the API; **do not disable CSRF as a production default** if the app serves browsers/sessions or requires CSRF protection.

In a test with security:

~~~java
@WebFluxTest(QuoteController.class)
@Import(ApiSecurityConfiguration.class)
class QuoteSecuritySliceTest {
    // Mock dependencies and assertions for 401/403/auth per contract.
}
~~~

This is a skeleton; if an endpoint must run through both a custom filter and security, include both in the slice per test scope. Do not conclude "having `@WebFluxTest` means production's entire security config was tested".

### WebTestClient and spring-security-test

To test authenticated requests in WebFlux tests, Spring Security provides helpers like `SecurityMockServerConfigurers.mockUser(...)` and `mockJwt()`, with dependency:

~~~groovy
testImplementation 'org.springframework.security:spring-security-test'
~~~

You can mutate the client with Spring Security test support, e.g.:

~~~java
WebTestClient authenticated = client.mutateWith(
        SecurityMockServerConfigurers.mockUser("tester")
);
~~~

This is an **illustrative test snippet**, requiring imports for `WebTestClient` and `SecurityMockServerConfigurers`. It does not prove custom security configuration was imported; it only simulates an identity on the test request when matching infrastructure is present.

If a test expects `401` but receives `400` from a custom filter on a missing header, that may be a **consequence of ordering**. Tests must supply the right request headers, principal, and filter/security setup before diagnosing a bug.

## 9. WebFilter, ExchangeFilterFunction, and Servlet Filter Are Not the Same

These names are easily confused because all contain "Filter":

| Type | Where It Runs | When to Use |
| --- | --- | --- |
| `org.springframework.web.server.WebFilter` | **Server-side Spring WebFlux** HTTP exchanges | Inspect/transform requests or responses before/after `WebHandler` |
| `org.springframework.web.reactive.function.client.ExchangeFilterFunction` | **Client-side `WebClient`** outbound requests | Add tokens/logging/retries/tracing to requests sent by the app |
| `jakarta.servlet.Filter` | Servlet stack / Spring MVC | Intercept HTTP per Servlet API, not WebFlux server chain |
| `SecurityWebFilterChain` | Spring Security WebFlux | Reactive authentication/authorization chain |
| `HandlerFilterFunction` | WebFlux functional routing | Cross-cutting behavior attached to `RouterFunction`/`HandlerFunction` |

An `ExchangeFilterFunction` installed on `WebClient.builder().filter(...)` **does not intercept** inbound `WebTestClient.get().uri("/api/...")` requests to the server. Conversely, a `WebFilter` does not automatically apply to outbound `WebClient` HTTP requests.

**Common out-of-scope test mistake:** wanting to test a server-side header filter while only configuring a client-side filter; the controller's response body still passes and one assumes the server filter was tested. Assert headers added by the **server** and ensure the `WebFilter` bean is in the server chain.

## 10. Functional RouterFunction and Limits of the WebFlux Slice

`@WebFluxTest` is primarily designed for annotated controllers. Spring Boot explicitly notes it **does not automatically detect all routes registered via the functional WebFlux framework**. If an application uses `RouterFunction<ServerResponse>`:

- Use `WebTestClient.bindToRouterFunction(route).build()` for pure router/handler tests when Spring bean wiring is unnecessary.
- Or `@Import` the relevant router/handler configuration into the `@WebFluxTest` context when supported by scope.
- Or move to `@SpringBootTest` when routes and filters/security must operate under full application wiring.

Do not test `@RestController` and assume all functional routes are protected by the same filter. Tests must cover the **actual request path** used in production.

## 11. Measuring and Controlling Stability of Reactive Tests

### Never Call block Inside Processing Flows

`Mono.block()` inside a filter/controller contradicts non-blocking design and can cause errors or stall the event loop. For non-blocking dependencies, compose results using `flatMap`, `map`, and controlled `onErrorResume`.

**However, not every error should turn into status 200/403.** If `policy.isAllowed(...)` throws or returns `Mono.error(...)`, the contract must define fail-closed behavior, returning 5xx, or handling by a global exception handler. The main example maps `Mono.empty()` to denial, yet **does not silently swallow `Mono.error()`**. In production designs, add logging/metrics and an explicit error policy.

### Attach Headers While the Response Is Still Mutable

Never set response headers inside a publisher's `doFinally` callback if downstream may have already committed the response. Set them before the chain or use `beforeCommit` as needed.

### Never Use Static Variables to Record State Across Tests

A `WebFilter` is typically a Spring context singleton. Writing to a `static List<String> traces` from concurrent requests or parallel JUnit runs mixes request data and lets other tests/listeners pollute state. Use exchange attributes, Reactor Context, or thread-safe, properly scoped recorders.

### Stub Individually Per Test

Spring TestContext's `@MockitoBean` resets mocks according to the test lifecycle. **Do not rely** on calls or stubs left over from a previous test. The cases in the example always stub explicitly and verify exact interactions.

### Context Caching Does Not Mean Filters Are Shared Incorrectly

Two `@WebFluxTest` classes differing in `@Import`, `@MockitoBean`, profiles, or properties can have different cache keys. That is right because their WebFlux chains may differ. Never omit a filter needing testing just to raise cache hit rates.

### Check Status and Headers Before Diving Internal

When testing an allowed client, assert 200, the filter-added header, and JSON body; when testing denial, assert 400/403 and zero interactions with the catalog. Only assert internal details like subscription counts when that is genuinely part of the contract to protect.

## 12. Extended Scenarios: @Order, Exceptions, CORS, and Body Streaming

| Scenario | What Tests Should Check | Warning |
| --- | --- | --- |
| Multiple filters | Filter order and observable status/headers | Do not rely on arbitrary component-scan order |
| Security + custom filter | 401/403/200 per principal and header | Custom `SecurityWebFilterChain` must be imported to test real config |
| Exception from policy | Error propagated/mapped per contract | Never let error publishers be swallowed or hang requests |
| CORS preflight (`OPTIONS`) | `Access-Control-Allow-Origin`/methods/headers for valid origins | CORS in Spring Security/WebFlux requires proper ordering |
| Request/response body streaming | No dropped buffers, no leaks, no blocking | May need decorators and dedicated streaming/backpressure tests |
| Metrics-recording filter | One exchange corresponds to one metric after complete/error/cancel | `doFinally` also runs on cancellation |
| Data-dependent feature gate | Filter enabled/disabled based on config bound in slice | `@ConfigurationProperties` bean must be registered |
| Timeout | Requests bounded per specification | Use `StepVerifier.withVirtualTime` for pure publishers if appropriate; do not equate with full HTTP latency |

Streaming/backpressure and security cases extend beyond a typical controller slice. When failures involve full server connectors, TLS/proxies, or real network sockets, elevate test scope to integration/end-to-end tests with a real server.

## 13. Common Mistakes and How to Fix Them

1. **Adding `@WebFluxTest` and assuming every production bean is present.** Slices exclude most services/repositories/custom configs. **Fix:** mock out-of-slice dependencies or import exact configs intentionally.
2. **Declaring a filter via `@Bean` in a `@Configuration` class without importing it.** Controller tests run without traversing the custom filter. **Fix:** `@Import(GateConfiguration.class)` or verify the proper registration path.
3. **Importing the real filter into the test and then putting `@MockitoBean` on the filter itself.** Filter logic is no longer tested. **Fix:** mock only `ClientAccessPolicy`/out-of-scope dependencies.
4. **Using `@Mock` instead of `@MockitoBean` for a Spring bean's constructor dependency.** The Spring context lacks the mock bean. **Fix:** choose the proper bean override mechanism.
5. **Forgetting to call `chain.filter(exchange)` in the allow branch.** The controller never runs even when the policy allows. **Fix:** return the publisher from the chain.
6. **Calling `subscribe()` inside a filter.** The signal sequence detaches from the framework; response/error timing becomes inconsistent. **Fix:** compose and return `Mono<Void>`.
7. **Failing to define `Mono.empty()` handling from policy.** Requests may end unexpectedly or behave inconsistently. **Fix:** apply `defaultIfEmpty(false)` or an explicit error rule.
8. **Setting headers after `chain.filter` inside `doFinally`.** The response may already be committed. **Fix:** set before the chain or in `beforeCommit`.
9. **Checking 403 without verifying the controller never ran.** The status could come from a different filter/security rule. **Fix:** verify dependency interactions and test configuration.
10. **Confusing `@WebFluxTest` with `@WebMvcTest`.** Different dispatchers, filter types, and test infrastructure. **Fix:** pick the right stack and use `WebTestClient` for reactive slices.
11. **Assuming custom `SecurityWebFilterChain` is auto-scanned.** Boot docs state you need `@Import` or full context. **Fix:** include real security configuration in the test when needed.
12. **Disabling security just to make tests pass.** Masks critical behavior. **Fix:** use `spring-security-test` and assert exact role/CSRF/JWT rules.
13. **Keeping mutable state in a singleton filter.** Concurrent requests/tests cause races or cross-request leaks. **Fix:** local variables, exchange attributes, thread-safe recorders.
14. **Importing the entire production config into a slice.** Slows tests and triggers missing unrelated beans. **Fix:** import small configs or move up to `@SpringBootTest` when broad integration is needed.
15. **Testing only that the controller is called, ignoring the filter.** Misses rejection branches and headers. **Fix:** include at least one allow case, one deny case, and one missing-header case.
16. **Thinking a `WebTestClient` client-side filter is a server `WebFilter`.** Installed on the wrong side. **Fix:** put server filters in the Spring WebFlux server context or client filters on outbound clients per goal.
17. **Testing functional routes with an annotated-controller slice and thinking it suffices.** Functional `RouterFunction` has distinct registration rules. **Fix:** bind routes/import routers or use full context.
18. **Asserting reactive error messages that vary by version.** Stack traces, reason phrases, and JSON errors can differ. **Fix:** assert status/headers/body strictly per published contract.

## 14. Checklist for Building a WebFlux Slice Test with a WebFilter

Workflow:

1. **Define the goal:** test the `WebFilter`, controller, security rules, or full wiring?
2. **List required filters:** `@Component`, `@Bean` from config, or auto-config?
3. **Check registration point:** did the slice load the filter? To guarantee a specific filter is present, import the class/config intentionally.
4. **List filter dependencies:** policy, config properties, clients, repositories. Decide what must be mocked and what must be real.
5. **Pick one web stack:** WebFlux + `WebTestClient`; avoid adding the MVC starter unnecessarily.
6. **Arrange per test:** stub specific publishers and outcomes; do not share stubs across tests.
7. **Test allow:** status, response headers, and JSON body for valid requests.
8. **Test deny:** 400/403, empty body, and zero invocations of controller dependencies.
9. **Test downstream failure:** filter allows through, yet controller returns 404.
10. **Add security/CORS/concurrency when in scope:** import custom chains and configure appropriate test support.
11. **Run the whole suite:** tests must not depend on order, leak state, or unintentionally alter profiles/contexts.
12. **Measure and optimize:** load only the necessary scope; never optimize context caching by removing required filters or security.

Pre-finalization checklist:

- [ ] Distinguished server-side `WebFilter` from client-side `ExchangeFilterFunction`.
- [ ] Real filter is present in the **slice's WebFlux server chain**, not merely in production config elsewhere.
- [ ] `@MockitoBean` is placed on isolated dependencies, not mocking the filter logic under test.
- [ ] When `@Bean`s from a custom `@Configuration` are needed, `@Import`ed the rightly scoped config.
- [ ] For `@ConfigurationProperties`, registered the bean and provided test properties if needed.
- [ ] Never called `block()/subscribe()` inside a filter.
- [ ] Allow branch returns `chain.filter(exchange)`, deny branch returns a response-completing publisher.
- [ ] Covered missing header, policy deny, empty policy, and missing downstream data when part of the contract.
- [ ] Verified HTTP status, response headers, body, and key interactions.
- [ ] Considered `@Order`, Spring Security, CSRF, CORS, and response commit timing.
- [ ] Did not assume custom security configs or functional routes are auto-discovered by `@WebFluxTest`.
- [ ] Tests run independently in CI without relying on real databases/networks when those are not the target.

**Conclusion:** When testing Spring WebFlux with `@WebFluxTest`, check both **which filters are actually registered in the slice** and **whether the filter's dependencies are properly supplied**. A `WebFilter` is part of the **server-side reactive chain**, not just a Java helper; it must compose and return a publisher while keeping request state isolated. With a small suite, `@Import`ing the real filter + `@MockitoBean` collaborators + `WebTestClient` accurately proves both **allow/deny** branches and the path into the controller.

### References

- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html)
- [Spring Boot 3.5 — @WebFluxTest Javadoc](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/autoconfigure/web/reactive/WebFluxTest.html)
- [Spring Framework 6.2 — WebFilter API](https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/web/server/WebFilter.html)
- [Spring Framework — WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html)
- [Spring Boot — Reactive Web Applications](https://docs.spring.io/spring-boot/reference/web/reactive.html)
- [Spring Security — Testing WebFlux](https://docs.spring.io/spring-security/reference/reactive/test/index.html)