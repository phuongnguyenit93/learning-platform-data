# Verifying Filters, Profiles, Codecs, and Security Configuration

**Module:** Spring Framework – reactive  
**Parent topic:** WebFlux Testing

An endpoint returning HTTP 200 is not enough to prove a WebFlux application works properly. The request might have gone through a minimal test setup, bypassed a `WebFilter`, used the wrong profile, hit misconfigured codec limits, or run without Spring Security attached to the chain. Conversely, a unit test can show a controller works while real deployment returns 401/403, fails with 413, or leaks sensitive data.

This lesson builds a **real-configuration, clearly scoped testing strategy** for four components: **WebFilter**, **Spring profiles/properties**, **HTTP message codecs**, and **reactive security**. The focus is on `WebTestClient`, `@WebFluxTest`, `@SpringBootTest`, `@ActiveProfiles`, Spring Security test support, and integration testing with Spring Boot 3.5 / Spring Framework 6.2.

## 1. What tests need to prove

Every test should prove an observable contract rather than merely calling an endpoint and checking `200 OK`.

| Area | What needs verification | Insufficient test |
|---|---|---|
| `WebFilter` | Filter is registered, runs in the right order, applies to error/anonymous paths when needed | Calling the filter method directly |
| Profile | Beans of the active profile appear; beans of other profiles are absent; right properties bind | Reading `application-qa.properties` and assuming |
| Codec | Readers/writers, content types, encoding, size caps work on real HTTP requests | Checking only that an `ObjectMapper` bean exists |
| Security | Anonymous 401, authenticated right role 200, wrong role 403, CSRF, path/method rules, deny-by-default | Testing controller method only with a mock principal |
| Cross-cutting | Filters and security chain run together; error mapping and codecs are not bypassed by tests | Using `bindToController` for all configuration |
| Operational | Live server, proxies, TLS/HTTP headers, real timeouts | Mock exchange without sockets |

A good test case needs **input conditions**, **the actually wired middleware chain**, **expected outcomes**, and a **negative test** for unauthorized paths.

## 2. Which layers does WebFlux execute a request through?

```text
Browser / API client
       |
       v
Reactor Netty server / HTTP adapter
       |
       v
WebHttpHandlerBuilder
       |
       +--> WebFilter (order / context / auth / audit)
       |
       +--> Spring Security WebFilterChainProxy
       |
       v
DispatcherHandler
       |
       +--> HandlerMapping
       +--> HandlerAdapter
       +--> ResultHandler / HttpMessageWriter
       |
       v
Controller, RouterFunction or resource handler
       |
       v
HTTP response
```

`WebFilter` is **server-side** middleware; `ExchangeFilterFunction` is a filter for **outbound WebClient**. The two have different APIs, execution points, and testing methods. An outbound `WebClient` test does not prove an inbound `WebFilter` works.

Security for WebFlux uses `SecurityWebFilterChain`; this is the list of security filters coordinated by `WebFilterChainProxy`. `@EnableWebFluxSecurity` does not mean `@EnableWebFlux`. The second annotation enables manual WebFlux infrastructure and can cause Spring Boot WebFlux auto-configuration to back off, so do not add `@EnableWebFlux` just to test Security.

## 3. Choosing the right WebTestClient depth

`WebTestClient` can test anything from controller logic to a real server. Choose based on what needs proving:

| Setup | What loads? | Good for | Does not prove on its own |
|---|---|---|---|
| `WebTestClient.bindToController(...)` | Specified controller and lean WebFlux setup | Isolated binding, validation, serialization | Bean filters/profiles/Boot security outside context |
| `bindToRouterFunction(...)` | Specified RouterFunction and handler | Predicates, functional routes | Full ApplicationContext |
| `bindToApplicationContext(context)` | Real WebFlux context, mock request/response | Filter beans, profiles, codecs, security config | Real TCP/TLS/Netty |
| `@WebFluxTest` | WebFlux test slice | Controllers, validation, codecs, and imported configs | Every app service/filter/security bean |
| `@SpringBootTest(MOCK)` | Full Boot ApplicationContext, no server opened | Fast bean/profile/security/filter/codec integration | Real transport |
| `@SpringBootTest(RANDOM_PORT)` | Real embedded reactive server | HTTP wire behavior, headers, end-to-end | External dependencies if still mocked |

Spring Boot 3.5 documentation notes: `@WebFluxTest` scans only a limited set of beans, such as `@Controller`, `@ControllerAdvice`, `@JsonComponent`, converters, and `WebFluxConfigurer`; it does not scan arbitrary `@Component` beans. It also **does not auto-discover custom `SecurityWebFilterChain`** or functional `RouterFunction` beans. If those beans are needed, use `@Import(...)` or `@SpringBootTest`.

Key point: a test using `bindToController(new ApiController())` can return 200 even though production security would return 401. That is not a Spring bug; the test intentionally chose a mock level without the security/filter chain.

## 4. Testing WebFilter by HTTP behavior

`WebFilter` returns `Mono<Void>` and is invoked in the request pipeline:

```java
@Component
@Order(Ordered.HIGHEST_PRECEDENCE)
class MarkerFilter implements WebFilter {

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange, WebFilterChain chain) {

        exchange.getResponse()
                .getHeaders()
                .set("X-Filter-Trace", "visited");

        return chain.filter(exchange);
    }
}
```

The code above adds a safe marker to the response before calling the chain. Tests should not inspect `MarkerFilter.class.getAnnotation(...)` and treat that as proof. Send a request through the real context and assert:

```java
client.get()
        .uri("/api/public")
        .exchange()
        .expectStatus().isOk()
        .expectHeader()
        .valueEquals("X-Filter-Trace", "visited");
```

Because the filter runs before the handler and has high precedence, tests can check the marker on both successful and rejected responses. However, WebFilter ordering must be verified against your actual configuration; do not assume every filter runs before security.

### 4.1. Testing ordering

You can register two filters with different `@Order` values and record a trace in **a per-request exchange attribute**:

```java
Object current = exchange.getAttribute("filterTrace");
String previous = current == null ? "" : current.toString();
exchange.getAttributes().put(
        "filterTrace", previous + "A");
return chain.filter(exchange);
```

The second filter appends B; the handler or an outer filter can output the allowlisted trace to the test response. Assert `AB` when execution order is the goal. Never use a singleton `StringBuilder` because requests will race. Do not rely on Java file ordering, component scan order, or bean names when order matters.

### 4.2. Testing errors and cancellation

Filters can use `doOnError`, `doFinally`, or `onErrorResume`. Tests should cover:

- Handler returning success.
- Handler emitting an error.
- Security returning 401/403.
- Request canceled/disconnected.
- Filter already writing a response and then emitting an error.
- Context propagation across `publishOn` if the filter puts data into Reactor Context.

Avoid calling `subscribe()` yourself inside a filter: doing so detaches the subscription from the HTTP lifecycle and breaks error/cancel propagation.

### 4.3. Do not log bodies in filter tests

If a filter is for auditing, tests should ensure it **does not** log Authorization, Cookies, query strings, or bodies. Use normalized route templates/methods/statuses/durations. Never create tests that "log raw requests for comparison" and accidentally retain secrets in CI artifacts.

## 5. Profiles are real configuration conditions, not mere labels

Spring uses `@Profile` and `Environment` to decide which beans are created. Example:

```java
@Component
@Profile("qa")
class QaMarkerFilter implements WebFilter {
    // ...
}
```

Only when the active profile is `qa` does this bean appear. Tests must verify both:

1. **Positive:** the bean exists in the qa profile and the corresponding behavior appears.
2. **Negative:** the bean is not created in the prod profile.
3. **Property override:** the same application can have different codec/security/timeout values per profile; test actual values via HTTP or bean settings.

Use `@ActiveProfiles("qa")` on the test class to select the profile instead of setting a global profile in the IDE or mutating environment variables between tests.

### 5.1. Property precedence

Example:

```properties
# src/main/resources/application.properties
spring.http.codecs.max-in-memory-size=1KB
```

```properties
# src/main/resources/application-qa.properties
spring.http.codecs.max-in-memory-size=128B
```

When a test has `@ActiveProfiles("qa")`, Boot loads the qa config and the 128B property applies. If a test has `@ActiveProfiles("prod")` without an `application-prod.properties` file, the shared 1KB setting remains in effect.

`@TestPropertySource(properties = "feature.enabled=true")` or `@SpringBootTest(properties = "...")` can be used for a specific test. For dynamic ports/containers, use `@DynamicPropertySource`; do not hardcode shared external resources when running CI in parallel.

### 5.2. Never mutate System.setProperty between tests

`System.setProperty("spring.profiles.active","qa")` inside a test can affect other tests, while Spring TestContext caches the ApplicationContext by configuration. Changing the environment after the context is already created will not re-register `@Profile` beans.

Use annotations to select profiles before context initialization. When a context genuinely must refresh due to mutated configuration state, consider `@DirtiesContext`, but never use it to mask order-dependent tests.

### 5.3. Security must not be "looser" than production

Never use a test profile solely to `permitAll()` and claim the security configuration passed. For critical behaviors (roles/CSRF), keep security rules identical to production and replace only identities/test data. If production uses JWT/OAuth2, you can mock JWT when testing authorization policies, yet have another test verifying validator/issuer/audience and token signatures on real requests.

## 6. Codecs and HTTP content negotiation

Codecs convert `DataBuffer` to Java objects and vice versa. Common issues:

- Missing JSON encoder/decoder or custom Jackson module.
- Incompatible `Content-Type` → HTTP 415.
- `Accept` with no matching response representation → HTTP 406.
- Body violating schema or malformed JSON → HTTP 400.
- Buffer aggregation exceeding limits → size error; in Spring Framework 6.2, many `@RequestBody` paths translate `DataBufferLimitException` to HTTP 413.
- Wrong charset or mishandled Unicode.
- Streaming `Flux<T>` should not be buffered whole in memory.

Boot 3.5's `spring.http.codecs.max-in-memory-size` is the buffer limit when **a codec needs to aggregate**; it is not a hard limit on total bytes of every raw `Flux<DataBuffer>`. To test large uploads, test quotas at the gateway/handler or `DataBufferUtils.join(..., maxByteCount)`.

### 6.1. Codec tests must exercise the right request path

When testing a `@RequestBody Mono<String>`, the Spring String decoder actually runs, so requests with bodies below and above the buffer cap can be used. Do not just compare two Java strings in a unit test.

Example:

```java
@PostMapping(
        path = "/api/echo",
        consumes = MediaType.TEXT_PLAIN_VALUE,
        produces = MediaType.TEXT_PLAIN_VALUE)
public Mono<String> echo(@RequestBody Mono<String> body) {
    return body.map(value -> "length=" + value.length());
}
```

If the test profile caps the codec at 128B, a 32-ASCII-byte request must succeed while a 256-ASCII-byte line exceeds the String decoder cap. Response status is verified with `WebTestClient`. In Spring Framework 6.2, this body-reading path turns data exceeding the cap into an HTTP 413 error. With custom codecs or custom error handlers, outcomes may differ: test your own application's contract.

### 6.2. JSON, charsets, and custom mappers

JSON tests should assert content rather than key orderings not guaranteed by the contract:

```java
client.get().uri("/api/item")
        .accept(MediaType.APPLICATION_JSON)
        .exchange()
        .expectStatus().isOk()
        .expectHeader().contentTypeCompatibleWith(
                MediaType.APPLICATION_JSON)
        .expectBody()
        .jsonPath("$.name").isEqualTo("book");
```

If the application registers a custom Jackson `Module`, enum converter, or custom codec, test with a context that imports the proper customizer beans. `@WebFluxTest` does not automatically load every `@Component` or third-party library auto-configuration.

### 6.3. Buffer size is not a whole-pipeline byte count

A large JSON array, NDJSON, SSE, multipart, or raw file can pass through readers with different semantics. Aggregation limits typically apply to **a single item/fragment needing decoding**, rather than capping total throughput. "Payload too large" tests must specify the exact payload type and decoder in use.

Never raise the limit to `-1` just to make a test pass. If production must handle large files, design a streaming route and dedicated quota, then test on a real server.

## 7. Testing reactive Spring Security

WebFlux security uses `ServerHttpSecurity` and `SecurityWebFilterChain`. Key contracts:

| Condition | Expectation |
|---|---|
| Public GET without credentials | 200 |
| Protected GET, anonymous | 401 when HTTP Basic challenge is configured |
| GET with user but wrong role | 403 |
| GET with right role | 200 |
| POST with valid user but no CSRF token | 403 when CSRF is enabled and requires token |
| POST with valid user + valid CSRF token | 200 or business status |
| Path outside rules | 403 if `denyAll` |
| Invalid cookie/session or JWT | Rejected per the matching chain |

Never make tests pass easily with `csrf().disable()`, `permitAll()`, or `@WithMockUser` on every method. Those shortcuts can leave anonymous paths or CSRF uncovered.

### 7.1. Configuring WebTestClient security test support

With a mock ApplicationContext:

```java
WebTestClient client =
        WebTestClient.bindToApplicationContext(context)
                .apply(springSecurity())
                .configureClient()
                .build();
```

`springSecurity()` here is `org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity`. It integrates security test support into the mock server setup. The sample project uses this exact form.

Then:

```java
client.mutateWith(mockUser("alice").roles("READER"))
        .get()
        .uri("/api/private")
        .exchange()
        .expectStatus().isOk();
```

`mockUser` injects a mock Authentication into the **test request's** SecurityContext. It is useful for testing authorization, yet **does not** test password encoding, the HTTP Basic authentication filter, token parsing, or real JWT signatures.

### 7.2. Testing CSRF

```java
client.mutateWith(mockUser("alice").roles("READER"))
        .mutateWith(csrf())
        .post()
        .uri("/api/echo")
        .contentType(MediaType.TEXT_PLAIN)
        .bodyValue("ok")
        .exchange()
        .expectStatus().isOk();
```

`csrf()` belongs to `SecurityMockServerConfigurers`. It attaches an appropriate CSRF token to the mock request. If authentication is present yet the token is missing on a protected POST, expect 403.

Do not mechanically enforce CSRF on every public REST API. For pure stateless bearer-token APIs, the threat model and CSRF design differ from browser sessions/cookies. This lesson keeps CSRF enabled by default to clearly test the distinction.

### 7.3. Testing against a real server

`mockUser` works only when WebTestClient is bound to a mock server/security test context. When using `WebTestClient.bindToServer()` or `@SpringBootTest(RANDOM_PORT)`, requests travel over the network, so use real credentials/JWTs or an appropriate test identity provider. Do not expect a test-only SecurityContext to travel across an HTTP socket automatically.

## 8. Complete project: Java 17 + Spring Boot 3.5.16

This example uses 4 types of verification in the same project:

1. Two `WebFilter`s: a global filter and a filter active only in `qa`.
2. Profiles `qa` and `prod` with different codec limits.
3. Spring Security requiring role `READER` for private endpoints and CSRF for POST.
4. `WebTestClient` checking HTTP behavior from the full application context via mock server (no port needed).

**Directory structure:**

```text
webflux-configuration-tests/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/ConfigTestApplication.java
    │   ├── java/demo/ApiController.java
    │   ├── java/demo/GlobalMarkerFilter.java
    │   ├── java/demo/QaMarkerFilter.java
    │   ├── java/demo/SecurityConfiguration.java
    │   └── resources/
    │       ├── application.properties
    │       └── application-qa.properties
    └── test/java/demo/
        ├── QaConfigurationTest.java
        └── ProductionProfileTest.java
```

### 8.1. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>webflux-configuration-tests</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

Boot's dependency management selects compatible Spring Framework/Spring Security versions. Do not declare Spring Framework 7 for a Boot 3.5 project. `spring-security-test` is required for `mockUser`, `csrf`, and `springSecurity()`.

### 8.2. application.properties

```properties
spring.application.name=webflux-configuration-tests
spring.http.codecs.max-in-memory-size=1KB
spring.http.codecs.log-request-details=false
```

This is the base configuration. The 1 KiB codec cap merely illustrates the difference from the qa profile; real production must choose based on payload contracts.

### 8.3. application-qa.properties

```properties
spring.http.codecs.max-in-memory-size=128B
```

The active `qa` profile overrides max-in-memory-size to 128 bytes. Do not set `spring.profiles.active` in main configuration or in the Maven command when tests already declare `@ActiveProfiles`.

### 8.4. ConfigTestApplication.java

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ConfigTestApplication {

    public static void main(String[] args) {
        SpringApplication.run(ConfigTestApplication.class, args);
    }
}
```

### 8.5. ApiController.java

```java
package demo;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api")
public class ApiController {

    @GetMapping(
            path = "/public",
            produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> publicEndpoint() {
        return Mono.just("public");
    }

    @GetMapping(
            path = "/private",
            produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> privateEndpoint() {
        return Mono.just("private");
    }

    @PostMapping(
            path = "/echo",
            consumes = MediaType.TEXT_PLAIN_VALUE,
            produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> echo(
            @RequestBody Mono<String> body) {
        return body.map(value ->
                "length=" + value.length());
    }
}
```

The controller deliberately does not check roles or CSRF itself. That is `SecurityWebFilterChain`'s responsibility. The echo endpoint uses `Mono<String>` so Spring WebFlux actually decodes the request body before returning a response, enabling HTTP tests to verify the codec cap.

### 8.6. GlobalMarkerFilter.java

```java
package demo;

import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;

import reactor.core.publisher.Mono;

@Component
@Order(Ordered.HIGHEST_PRECEDENCE)
public class GlobalMarkerFilter implements WebFilter {

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain) {

        exchange.getResponse()
                .getHeaders()
                .set("X-Global-Filter", "visited");

        return chain.filter(exchange);
    }
}
```

This is a test-safe filter that logs no bodies. It has very high precedence so the marker can appear on responses rejected by security before reaching the controller. In production, never use an arbitrary response marker as proof of authentication; the goal here is testing registration/filter chaining.

### 8.7. QaMarkerFilter.java

```java
package demo;

import org.springframework.context.annotation.Profile;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;

import reactor.core.publisher.Mono;

@Component
@Profile("qa")
@Order(Ordered.HIGHEST_PRECEDENCE + 1)
public class QaMarkerFilter implements WebFilter {

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain) {

        exchange.getResponse()
                .getHeaders()
                .set("X-Profile-Filter", "qa");

        return chain.filter(exchange);
    }
}
```

When the qa profile is active, the filter adds response header `X-Profile-Filter: qa`. When the prod profile is active, the bean is not created. Checking both the header and the bean avoids cases where code checks a property yet the filter was never actually registered.

### 8.8. SecurityConfiguration.java

```java
package demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration(proxyBeanMethods = false)
@EnableWebFluxSecurity
public class SecurityConfiguration {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(
            ServerHttpSecurity http) {

        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers("/api/public").permitAll()
                        .pathMatchers("/api/**").hasRole("READER")
                        .anyExchange().denyAll())
                .httpBasic(Customizer.withDefaults())
                .formLogin(form -> form.disable())
                .csrf(Customizer.withDefaults())
                .build();
    }
}
```

Rules:

- `GET /api/public` allows anonymous access.
- All other `/api/**` paths require role `READER`.
- Paths outside rules are `denyAll`.
- HTTP Basic is enabled so anonymous requests receive a 401 challenge.
- CSRF is enabled; authenticated POSTs need a valid token.
- Do not use `@EnableWebFlux`; `@EnableWebFluxSecurity` is the annotation for security.

In production, register an appropriate authentication provider/user details/JWT resource server. Tests use `mockUser` to focus on authorization rules rather than verifying real credentials.

### 8.9. QaConfigurationTest.java

```java
package demo;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.http.MediaType;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.csrf;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@ActiveProfiles("qa")
class QaConfigurationTest {

    @Autowired
    ApplicationContext context;

    private WebTestClient client;

    @BeforeEach
    void setUp() {
        client = WebTestClient
                .bindToApplicationContext(context)
                .apply(springSecurity())
                .configureClient()
                .build();
    }

    @Test
    void activeProfileRegistersQaFilter() {
        assertThat(
                context.getBeansOfType(QaMarkerFilter.class))
                .hasSize(1);

        client.get()
                .uri("/api/public")
                .exchange()
                .expectStatus().isOk()
                .expectHeader()
                .valueEquals("X-Global-Filter", "visited")
                .expectHeader()
                .valueEquals("X-Profile-Filter", "qa")
                .expectBody(String.class)
                .isEqualTo("public");
    }

    @Test
    void securityIsAppliedToAnonymousRequest() {
        client.get()
                .uri("/api/private")
                .exchange()
                .expectStatus().isUnauthorized()
                .expectHeader()
                .valueEquals("X-Global-Filter", "visited");
    }

    @Test
    void wrongRoleIsForbidden() {
        client.mutateWith(
                        mockUser("guest").roles("GUEST"))
                .get()
                .uri("/api/private")
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void readerRoleCanAccessPrivateEndpoint() {
        client.mutateWith(
                        mockUser("alice").roles("READER"))
                .get()
                .uri("/api/private")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class)
                .isEqualTo("private");
    }

    @Test
    void postWithoutCsrfIsRejected() {
        client.mutateWith(
                        mockUser("alice").roles("READER"))
                .post()
                .uri("/api/echo")
                .contentType(MediaType.TEXT_PLAIN)
                .bodyValue("hello")
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void postWithCsrfIsAccepted() {
        client.mutateWith(
                        mockUser("alice").roles("READER"))
                .mutateWith(csrf())
                .post()
                .uri("/api/echo")
                .contentType(MediaType.TEXT_PLAIN)
                .bodyValue("hello")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class)
                .isEqualTo("length=5");
    }

    @Test
    void codecAcceptsBodyBelowQaLimit() {
        client.mutateWith(
                        mockUser("alice").roles("READER"))
                .mutateWith(csrf())
                .post()
                .uri("/api/echo")
                .contentType(MediaType.TEXT_PLAIN)
                .bodyValue("A".repeat(32))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class)
                .isEqualTo("length=32");
    }

    @Test
    void codecRejectsBodyAboveQaLimit() {
        client.mutateWith(
                        mockUser("alice").roles("READER"))
                .mutateWith(csrf())
                .post()
                .uri("/api/echo")
                .contentType(MediaType.TEXT_PLAIN)
                .bodyValue("A".repeat(256))
                .exchange()
                .expectStatus().isEqualTo(413);
    }
}
```

These eight tests prove the global filter and qa filter are genuinely registered, the HTTP security chain is active, roles and CSRF are enforced, and the 128B codec cap takes effect on decoded `text/plain` requests.

**Note:** `codecRejectsBodyAboveQaLimit` expects 413 per Spring Framework 6.2 default error handling for `DataBufferLimitException` in the `@RequestBody` path. If an application adds custom `@ControllerAdvice`/`WebExceptionHandler`, verify the actual status mapping; never change the test to 200/500 just to "pass."

### 8.10. ProductionProfileTest.java

```java
package demo;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.http.MediaType;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.csrf;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@ActiveProfiles("prod")
class ProductionProfileTest {

    @Autowired
    ApplicationContext context;

    private WebTestClient client;

    @BeforeEach
    void setUp() {
        client = WebTestClient
                .bindToApplicationContext(context)
                .apply(springSecurity())
                .configureClient()
                .build();
    }

    @Test
    void qaFilterIsAbsentInProdProfile() {
        assertThat(
                context.getBeansOfType(QaMarkerFilter.class))
                .isEmpty();

        client.get()
                .uri("/api/public")
                .exchange()
                .expectStatus().isOk()
                .expectHeader()
                .valueEquals("X-Global-Filter", "visited")
                .expectHeader()
                .doesNotExist("X-Profile-Filter");
    }

    @Test
    void baseCodecLimitAllows256ByteBody() {
        client.mutateWith(
                        mockUser("alice").roles("READER"))
                .mutateWith(csrf())
                .post()
                .uri("/api/echo")
                .contentType(MediaType.TEXT_PLAIN)
                .bodyValue("B".repeat(256))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class)
                .isEqualTo("length=256");
    }

    @Test
    void securityStillAppliesInProd() {
        client.get()
                .uri("/api/private")
                .exchange()
                .expectStatus().isUnauthorized();
    }
}
```

In the prod profile, `application.properties` grants 1 KiB for codecs; 256 bytes is valid. The qa filter is not created, while the global filter and security remain active. The tests prove the difference between the two profiles **through HTTP behavior**, not just Environment values.

### 8.11. Running tests and expected results

Install JDK 17+ and Maven, then run in the directory containing `pom.xml`:

```bash
mvn test
```

Expected logical outcome (independent of timestamps or JUnit order):

| Test group | Test count | Expectation |
|---|---:|---|
| QaConfigurationTest | 8 | PASS: qa filter, 401, 403, 200, CSRF, 128B codec |
| ProductionProfileTest | 3 | PASS: qa filter absent, 1KB codec, security still active |
| **Total** | **11** | **11 tests PASS**, Maven exit code `0` |

No real HTTP server is opened because `WebEnvironment.MOCK` is used. This is suitable for testing ApplicationContext, mappings, and Spring Security WebFilterChain. In production deployment, smoke tests over real ports, reverse proxies, TLS, gateways, and external IDPs are still needed.

To run individually:

```bash
mvn -Dtest=QaConfigurationTest test
mvn -Dtest=ProductionProfileTest test
```

Never write tests that depend on the execution order of the two classes. Spring TestContext creates/caches contexts by active profiles and properties; both profiles must yield consistent results whether run individually or in parallel.

## 9. Extending with @WebFluxTest slices

`@WebFluxTest` fits when you want to test controllers and codecs without starting the full application. Skeleton example:

```java
@WebFluxTest(controllers = ApiController.class)
@Import(SecurityConfiguration.class)
@ActiveProfiles("qa")
class ApiSliceTest {

    @Autowired
    WebTestClient webClient;

    // May need explicit import of WebFilter/configurer,
    // and bind/apply security test support depending on test setup.
}
```

**Do not treat this snippet as a standalone project.** By default the slice does not scan all `@Component`s and does not automatically load custom `SecurityWebFilterChain`. `@Import(SecurityConfiguration.class)` brings the rules into the context; if tests require `GlobalMarkerFilter` or `QaMarkerFilter`, import them explicitly and ensure security test support is present.

If a controller has service dependencies, use `@MockitoBean` from `org.springframework.test.context.bean.override.mockito.MockitoBean` in Spring Framework 6.2 instead of spinning up an entire database/broker just for controller tests. Spring Boot's `@MockBean` was deprecated in the Boot 3.4+ generation; new code should choose `@MockitoBean`.

For functional `RouterFunction` endpoints, `@WebFluxTest` does not auto-discover routes. Import the RouterFunction bean or use full `@SpringBootTest`.

### 9.1. When not to use slices?

Do not use slices to claim the following if the corresponding beans were not loaded:

- Profile-specific beans across the whole application work.
- Custom filters run properly with the security proxy.
- Codec customizers from auto-configuration depending on other beans are applied.
- Production error handlers, routing functions, and metrics filters are present.
- Authentication providers connected to databases/IDPs work for real.

Slice tests are useful because they are fast and isolated. When verifying integration across filters–profiles–codecs–security, full-context tests usually carry stronger proof.

## 10. Real HTTP server testing with RANDOM_PORT

If the goal is verifying the Reactor Netty adapter, header serialization, compression, HTTP protocol, and transport behavior together, use:

```java
@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
@ActiveProfiles("qa")
class LiveWebFluxSmokeTest {

    @Autowired
    WebTestClient client;

    @Test
    void publicEndpointWorksOverHttp() {
        client.get()
                .uri("/api/public")
                .exchange()
                .expectStatus().isOk()
                .expectHeader()
                .valueEquals("X-Global-Filter", "visited");
    }
}
```

This is a supplementary snippet needing JUnit/Spring imports. WebTestClient here communicates with the embedded server **over real HTTP**. Because the test only uses the anonymous public endpoint, no credentials are needed.

Do not call `client.mutateWith(mockUser())` on a live client and treat it as network authentication. Basic Authentication tests should configure a test user details service and send `Authorization: Basic ...` via `headers(headers -> headers.setBasicAuth(...))`; JWT tests should send tokens signed by a test issuer. Fake test secrets must never mix with production secrets.

Do not put `@Transactional` on client-side tests expecting real server-side DB transactions to roll back with the test. Real HTTP clients/servers are separate executions; test fixture cleanup needs its own strategy.

## 11. CSRF, authentication, and authorization are three test groups

- **Authentication:** the client proves identity via HTTP Basic, JWT, OAuth2, or session. `mockUser` skips credential verification.
- **Authorization:** is the established identity allowed to call the route/method? Test with `mockUser`, `mockJwt`, and roles/scopes/authorities.
- **CSRF:** with browser/session cookies, state-changing requests need a valid token; test POSTs both without and with the token.

Matrix example:

| Request | Test principal | CSRF | Expected outcome |
|---|---|---|---|
| GET /api/public | anonymous | Not needed | 200 |
| GET /api/private | anonymous | Not needed | 401 |
| GET /api/private | GUEST | Not needed | 403 |
| GET /api/private | READER | Not needed | 200 |
| POST /api/echo | READER | Missing | 403 |
| POST /api/echo | READER | Present | 200 |
| POST /api/echo | anonymous | Present | 401/403 depending on entry-point/rule ordering; must verify |
| GET /unknown | READER | Not needed | 403 per denyAll |

For requests passing through multiple blocking layers, **status depends on which layer rejects first**. Do not hardcode 401 for every anonymous POST when the CSRF filter may reject before the authentication entry point.

If the application uses a JWT resource server, add tests for: wrong issuer, wrong audience, expired, invalid signature, missing scope, and revoked tokens if introspection is used. Mock JWT tests only authorization rules; real signature testing requires sending signed tokens through a live server.

## 12. Testing filter ordering and safe error handling

Audit/rate-limit/auth filters must not leak information in responses:

- Requests rejected with 401/403 must still include required security headers.
- Never send user IDs, raw tokens, or internal stack traces in debug headers.
- CORS preflight is distinguished from anonymous business requests.
- Filters must not swallow `onError` and make business requests return 200.
- Filters adding Reactor Context must propagate it properly when handlers switch schedulers.
- Once a response is committed, status/headers can no longer be arbitrarily rewritten.

When testing ordering, assert both **safe side effects** and the absence of unwanted side effects. For example, an authentication filter must run before a handler creating business side effects, not just return a status code. For side-effecting POSTs, use a spy/test repository to assert the handler never ran when security rejected the request.

### 12.1. CORS and WebFilter

CORS can be configured in `WebFluxConfigurer` or Spring Security CORS integration. `OPTIONS` preflight requests must test `Origin`, `Access-Control-Request-Method`, and returned headers.

Test example:

```java
client.options()
        .uri("/api/private")
        .header("Origin", "https://frontend.example")
        .header("Access-Control-Request-Method", "GET")
        .exchange();
```

Expected status and headers must follow the real CORS policy. You cannot assert `Access-Control-Allow-Origin: *` when the policy allows credentials or whitelists specific origins.

A preflight handled by the CORS filter may not pass through business authorization like a real GET. Therefore test both preflight and real requests from allowed/disallowed origins.

## 13. Codec negotiation, JSON errors, and multipart

Beyond body size, add tests for:

1. POST with the wrong `Content-Type` must return 415 if the endpoint specifies `consumes`.
2. GET with an incompatible `Accept` must return 406 when Spring has no matching representation.
3. Validated JSON missing fields → 400; do not treat that as a 413 codec error.
4. Custom Jackson serialization produces properly formatted values.
5. Unicode data round-trips cleanly in UTF-8.
6. `spring.http.codecs.max-in-memory-size` affects the intended aggregating endpoints.
7. NDJSON or SSE streaming is not tested with unbounded `collectList()`.
8. Multipart enforces max parts, max memory, max disk usage, and cleanup.

415 test example:

```java
client.mutateWith(mockUser().roles("READER"))
        .mutateWith(csrf())
        .post()
        .uri("/api/echo")
        .contentType(MediaType.APPLICATION_JSON)
        .bodyValue("{\"x\":1}")
        .exchange()
        .expectStatus().isEqualTo(415);
```

Do not assume raw `Flux<DataBuffer>` endpoints are governed by codec limits the same way as aggregated DTOs. If total upload size limits are needed, test a byte counter or gateway policy separately.

## 14. Testing profile configuration and bean conditions

In addition to HTTP behavior, assert bean conditions:

```java
assertThat(context.getBeansOfType(QaMarkerFilter.class))
        .hasSize(1);
```

And under the other profile:

```java
assertThat(context.getBeansOfType(QaMarkerFilter.class))
        .isEmpty();
```

When an application has many `@ConditionalOnProperty` or `@Profile("!prod")` beans, test **both true and false conditions**; a positive-only test can miss a bean accidentally appearing in production too.

`ApplicationContextRunner` / `ReactiveWebApplicationContextRunner` are helpful for testing small auto-configurations across multiple property pairs, yet simple runners do not spin up the full Boot server, security chain, or application controllers. Use them for bean graphs/conditions, then use WebTestClient integration for behavior.

### 14.1. TestPropertySource, DynamicPropertySource, and precedence

- `@ActiveProfiles` selects profiles before the context is created.
- `@TestPropertySource` overrides test-specific properties; use version-accurate property keys.
- `@DynamicPropertySource` registers values generated at test runtime (container ports, endpoints).
- `@SpringBootTest(properties = "...")` suits a few fixed overrides.
- Environment variables and command-line args have their own precedence; do not assume an application-prod file is always the final source.

When running CI with an unclear profile, you can assert:

```java
assertThat(context.getEnvironment()
        .acceptsProfiles(Profiles.of("qa")))
        .isTrue();
```

This snippet needs `org.springframework.core.env.Profiles`. For the prod profile test, assert the opposite. However, checking Environment alone does not prove filters actually run; pair it with HTTP assertions.

## 15. Never automatically disable security in tests

The following "shortcuts" make tests turn green without covering configuration:

- `@WebFluxTest` omitting custom security configuration while testing private routes as if protected.
- `WebTestClient.bindToController` testing endpoints directly and assuming WebFilters ran.
- Configuring a test profile with `permitAll()` on every path.
- Disabling `csrf` in dedicated tests when production requires CSRF.
- Using `mockUser` and claiming JWT signatures/issuers were verified.
- Mocking all of `ServerHttpSecurity` instead of using the real bean chain.
- Asserting only 200 without asserting 401/403.
- Asserting only that a filter bean exists without sending an HTTP request.
- Mutating properties after the context is cached without creating a fresh context.

Fix: separate **unit**, **context integration**, and **live-server/security integration** goals. Give each test a name describing the exact boundary it proves.

## 16. Evaluating results and diagnosing test failures

### 16.1. When private GET unexpectedly returns 200

Check in order:

1. Is the test using `bindToController` instead of ApplicationContext?
2. Is `SecurityWebFilterChain` registered in the context?
3. Was `springSecurity()` applied to the mock WebTestClient?
4. Do security rules have an overly broad `permitAll` or wrong path matcher?
5. Did filter ordering bypass security, or is the test using a client with a mocked identity?
6. Is the app running WebFlux or did it pick Spring MVC due to the classpath?

### 16.2. When POST without a token still returns 200

Check whether CSRF was disabled in configuration/test profiles, whether the endpoint falls under an ignored matcher, whether the test client applies `mutateWith(csrf())` globally, and whether the request is actually a POST/PUT/PATCH/DELETE requiring a token.

For stateless bearer-only APIs, CSRF may be intentionally disabled per the threat model. In that case expected tests must derive from the security design rather than copying browser-session samples.

### 16.3. When a 256B body is still accepted in the qa profile

Check:

- Was `@ActiveProfiles("qa")` used?
- Is `application-qa.properties` in the right directory with the Boot 3.5 key?
- Is a custom `@EnableWebFlux` causing Boot WebFlux auto-config to back off?
- Is the endpoint using a raw streaming body instead of an aggregating codec?
- Was the codec customizer replaced by a custom bean?
- Did the client send the right media type and did the decoder actually read the body?
- Did the test mock the controller/service and skip input body decoding?

### 16.4. When a request returns 403 instead of 401

CSRF may reject POSTs before authentication runs. HTTP Basic entry points, form login, bearer-token resource servers, and custom access-denied handlers have different semantics. Identify the exact authentication/authorization failure type rather than changing expected responses arbitrarily.

### 16.5. When a test passes alone but fails in the suite

Inspect TestContext caching, global mutable state, `System.setProperty`, shared in-memory databases, test fixtures, order dependencies, random ports, security context cleanup, and `@DirtiesContext`. Avoid storing mutable state in singletons or static fields inside a WebFilter to count requests.

## 17. Minimal CI test table

| Test case | Mechanism | Expectation |
|---|---|---|
| Public request anonymous | Full context WebTestClient | 200 |
| Private request anonymous | Spring Security chain | 401 |
| Private request wrong role | `mockUser` | 403 |
| Private request right role | `mockUser` | 200 |
| POST right user, no CSRF | Security test support | 403 |
| POST right user + CSRF | `mutateWith(csrf())` | 200 |
| Global WebFilter | Response marker | Header present |
| QA-only filter | `@ActiveProfiles("qa")` | Header present |
| QA filter in prod | `@ActiveProfiles("prod")` | Bean/header absent |
| Codec 32B in qa | HTTP request decode | 200 |
| Codec 256B in qa | HTTP request decode | 413 |
| Codec 256B in prod | HTTP request decode | 200 |
| Wrong content type | `consumes` | 415 |
| Invalid JSON or validation | Codec/validation | 400 per contract |
| Real network smoke | RANDOM_PORT | Correct headers/status |
| Real auth provider/JWT | Real credentials/tokens | Rejects invalid tokens |
| CORS preflight | Origin/header/method | Matches policy |
| Timeouts, large uploads | Live server/proxy | Matches policy and cleanup |

**Note on coverage:** the 11 runnable tests in the project focus on filters, profiles, codecs, and roles/CSRF. Rows like "real network", token verifiers, CORS, and multipart require additional configuration and tests tailored to the real application; never claim they were proven by mock-context tests.

## 18. Code review checklist

Before merging WebFlux configuration changes, ask:

- Is `WebTestClient` bound to a controller, router, context, or real server?
- Does the test load the full `WebFilter` and `SecurityWebFilterChain` used in production?
- Is `@WebFluxTest` missing `@Import` for security/codecs/functional routes?
- Are profiles selected with `@ActiveProfiles` before context creation?
- Are both positive and negative profile tests present, rather than just asserting Environment?
- Are property keys accurate for the Spring Boot version and overridden in qa/prod?
- Are codecs tested with real bodies, including over-limit cases?
- Are 415/400/406 and content negotiation tested?
- Are anonymous, wrong role, right role, and CSRF tested independently?
- Was CSRF/security accidentally disabled in tests just to get 200?
- Is a mock identity being mistaken for testing the auth provider/JWT signature?
- Do filters keep state per request and respect errors/cancellation?
- If a filter modifies the response, are ordering and commit state tested?
- Are live-server tests present for adapters, TLS, proxies, and timeouts when needed?
- Are logging tests confirming no leaked headers/bodies/tokens and no high-cardinality metric labels?
- Do tests run independently without order dependence or mutable global profiles?
- Have Context caching, thread switches, and Reactor Context been considered?
- Does CI produce test reports and fail when exceptions/statuses diverge from the contract?

**Takeaway:** To verify WebFlux **filters–profiles–codecs–security**, you must use the right test boundary. `@WebFluxTest` is fast yet does not auto-load all beans/filters/custom security; `@SpringBootTest(MOCK)` and `WebTestClient.bindToApplicationContext(...).apply(springSecurity())` fit testing the full Spring chain without sockets. `@ActiveProfiles` verifies environment-specific beans/properties; real HTTP request bodies verify codecs; `mockUser` verifies authorization; `csrf()` verifies CSRF. For JWT/HTTP Basic transport, TCP, TLS, proxies, or gateways, add live-server integration tests. Always include both positive and negative assertions to avoid "green tests yet broken production."

## References

- Spring Boot 3.5.16 — [Testing Spring Boot Applications, Auto-configured Spring WebFlux Tests](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html).
- Spring Framework 6.2 — [WebTestClient setup: bindToController, bindToApplicationContext, bindToServer](https://docs.spring.io/spring-framework/reference/6.2/testing/webtestclient.html).
- Spring Security 6.5 — [Reactive Test Support: WebTestClient Security Setup](https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/setup.html).
- Spring Security 6.5 — [Reactive Testing Authentication with mockUser](https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/authentication.html).
- Spring Security 6.5 — [Testing with CSRF](https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/csrf.html).
- Spring Framework 6.2 — [WebFlux @RequestBody and reactive arguments](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-methods/requestbody.html).
- Spring Framework 6.2 — [Reactive Core: codec buffering limits](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/reactive-spring.html).
- Spring Boot 3.5 — [Common Application Properties: spring.http.codecs.max-in-memory-size](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/index.html).
- Spring Framework 6.2 — [@ActiveProfiles Javadoc](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/test/context/ActiveProfiles.html).
- Spring Framework 6.2 — [@MockitoBean Javadoc](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/test/context/bean/override/mockito/MockitoBean.html).
- Spring Framework — [PayloadTooLargeException Javadoc for Spring 6.2](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/web/server/PayloadTooLargeException.html).
