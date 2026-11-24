# Distinguishing ApplicationContext Testing from Real-Server Testing — Spring Security WebFlux

## Learning Objectives

This lesson belongs to **Spring Security – reactive**, **HTTP Testing** group. After studying it, you will be able to:

1. Distinguish `WebTestClient.bindToApplicationContext(...)` and `WebTestClient.bindToServer()` by how requests reach the server, Spring bean scope, WebFilters, and HTTP transport.
2. Understand that `@SpringBootTest` defaults to `WebEnvironment.MOCK`, **without opening an HTTP server**, whereas `@SpringBootTest(webEnvironment = RANDOM_PORT)` starts a real embedded server.
3. Distinguish a full ApplicationContext from a `@WebFluxTest` web slice, `bindToController(...)`, and `bindToRouterFunction(...)`; avoid confusing "mock web" with "all services are mocked".
4. Test reactive Spring Security using `SecurityWebFilterChain`, `SecurityMockServerConfigurers.springSecurity()`, `mockUser()`, and Basic Authorization headers.
5. Distinguish testing **authorization with a mocked Authentication** from testing real **HTTP Basic passwords / JWT signatures / opaque token introspection**.
6. Build a Java 17+ / Spring Boot 3.5.16 project with three test groups: in-memory ApplicationContext, WebFlux slice, and real HTTP over Reactor Netty, using `WebTestClient` against the same controller.
7. Choose the right test style for authn/authz, JSON, status codes, error handling, streaming/SSE, ports, network, proxy/TLS, external IdP, and DB.
8. Avoid false confidence caused by skipped security chains, mistaking `@AutoConfigureWebTestClient` for a real server, replacing a service under test with `@MockitoBean`, or using `mockJwt()` and concluding the JWT signature was verified.

> **Baseline:** Java 17+, Spring Boot **3.5.16**, Spring Security **6.5.x**, Spring Framework 6.2.x, WebFlux, and Reactor Netty. Spring Boot 3.5.16 is the final release on the 3.5 OSS-supported branch; new production deployments should move to a supported line and stay patched. This lesson uses `{noop}` users/passwords only for local demo tests, **never in production**.

---

## 1. Same WebTestClient DSL, Two Request Paths

`WebTestClient` is a Spring Test client API. Most tests look similar:

```java
client.get().uri("/api/reports")
        .exchange()
        .expectStatus().isOk()
        .expectBody(String.class)
        .isEqualTo("report-for-reader");
```

However, **the request path cannot be inferred from the DSL alone**. It depends on how `client` was created.

### 1.1. Binding to ApplicationContext — mock HTTP exchange

```text
JUnit Test
   |
   | WebTestClient.bindToApplicationContext(context)
   v
Mock ServerHttpRequest / Mock ServerHttpResponse
   |
   v
Spring WebHttpHandlerBuilder
   |
   v
WebFilter chain (including Security if configured in context)
   |
   v
HandlerMapping / HandlerAdapter / Controller
   |
   v
Mono / Flux -> Mock response -> expectBody / expectStatus

No HTTP listener, no TCP socket to the server.
```

Spring Test creates mock requests/responses and feeds them directly into the **WebFlux WebHandler chain** within the same JVM. If the ApplicationContext contains real security filters, converters, handlers, and exception handlers, they still run; it is **not** a real HTTP request passing through Reactor Netty.

This is very useful for most HTTP application behavior tests because it avoids port-binding and network transport overhead.

### 1.2. Binding to a running server — HTTP network

```text
JUnit test
   |
   | WebTestClient.bindToServer()
   | baseUrl=http://127.0.0.1:<random-port>
   v
HTTP client -> TCP loopback -> Reactor Netty server
   |
   v
Spring WebFlux WebFilters / SecurityWebFilterChain
   |
   v
HandlerMapping -> Controller -> Service
   |
   v
Netty HTTP response -> WebTestClient assertions
```

This is an HTTP request/response over a real socket. With `@SpringBootTest(RANDOM_PORT)`, Spring Boot starts an embedded server and the OS picks an ephemeral port. The purpose is to verify the **network entrypoint**, alongside filter/controller behavior.

### 1.3. Axis-by-axis comparison

| Aspect | bindToApplicationContext | bindToServer |
| --- | --- | --- |
| Requires a real HTTP server? | No | Yes |
| Uses TCP/sockets? | No | Yes |
| Uses the real WebFlux controller? | Yes if loaded | Yes |
| Runs WebFilters and security chain? | Yes if loaded/applied properly | Yes per the running app |
| Tests port binding and HTTP parser? | No | Yes |
| Tests HTTP Basic filter via header? | Yes, if real security/user store is present | Yes |
| Tests JWT signature when using `mockJwt()`? | No | No `mockJwt()` over network; must send a real JWT |
| Tests production TLS/ingress? | No | Only if TLS/ingress is **actually** provisioned |
| Automatically mocks every service/DB? | No | No |
| Usually faster? | Yes | Slower due to server startup/I/O |
| Strengths | Controller, WebFilter, authz, status, response mapping | Real HTTP transport, server lifecycle, authn on the wire |

**Two independent axes:** "full context vs web slice" describes which Spring beans are loaded; "mock HTTP vs real HTTP" describes the transport. Do not use "full integration" as a vague label when reporting coverage.

## 2. Spring Boot test annotations: what is the difference?

### 2.1. Default `@SpringBootTest`

```java
@SpringBootTest
@AutoConfigureWebTestClient
class FullContextWithoutSocketTests {
    // Default webEnvironment = MOCK.
}
```

Spring Boot loads the **full ApplicationContext**, but **does not open an HTTP listener**. For a WebFlux app, `@AutoConfigureWebTestClient` configures a client using mock HTTP exchanges. You can also write `WebTestClient.bindToApplicationContext(context)` manually to control the setup.

Beans such as Services, Repositories, and `SecurityWebFilterChain` may still be real beans. If a service connects to a DB/remote API, it can still perform **outbound** I/O; only *inbound HTTP transport* is mocked.

### 2.2. `@SpringBootTest(RANDOM_PORT)`

```java
@SpringBootTest(webEnvironment =
        SpringBootTest.WebEnvironment.RANDOM_PORT)
class EmbeddedHttpTests {
    @LocalServerPort int port;
}
```

Spring Boot loads the context and **starts an embedded HTTP server**. When only WebFlux dependencies are present, this is typically Reactor Netty. `@LocalServerPort` injects the actual port number; never hardcode 8080.

`DEFINED_PORT` also starts a real server but on the configured port, which easily collides in parallel CI runs. `NONE` starts no web environment; `MOCK` is the default.

### 2.3. `@WebFluxTest` — slice test

```java
@WebFluxTest(ReportController.class)
class ReportControllerSliceTests {
    // Controller + WebFlux infrastructure; no server started.
}
```

Spring Boot loads only web-related components per test-slice policy. Regular services are not auto-scanned; use `@MockitoBean` or `@Import` according to the test objective.

**Note on Security:** `@WebFluxTest` **does not automatically pick up the application's custom SecurityWebFilterChain bean**. To properly test security policies, `@Import(HttpSecurityConfiguration.class)` or use a full-context test. A slice test returning 200 does not prove the production security chain ran unless the corresponding chain config is confirmed present.

### 2.4. `bindToController` and `bindToRouterFunction`

```java
// Standalone controller fragment — no WebFlux app SecurityWebFilterChain.
WebTestClient standalone = WebTestClient
        .bindToController(new PublicController())
        .build();
```

`bindToController(...)` creates handler infrastructure for the specified controller. `bindToRouterFunction(router)` tests functional routing via mock requests. Neither includes the application's full bean/security configuration by default.

Use them to test URL binding, conversion, or payloads on an isolated controller, **not** to conclude that a protected endpoint is guarded by production security if `SecurityWebFilterChain` has not been wired in.

### 2.5. Quick selection matrix

| Test style | Spring context | Incoming HTTP | Best use case |
| --- | --- | --- | --- |
| bindToController | Full context not required | Mock | Isolated single handler |
| `@WebFluxTest` + WebTestClient | Slice | Mock | Controller/serialization + imported security |
| `@SpringBootTest(MOCK)` | Full app | Mock | Full-context in-process integration |
| `@SpringBootTest(RANDOM_PORT)` | Full app | Real over socket | Real HTTP integration |
| bindToServer to staging | Externally running app | Real over network | Environment contract/smoke/E2E |

**There is no need** to add `@ExtendWith(SpringExtension.class)` when a class already uses a Spring Boot test annotation in JUnit 5.

---

## 3. Security WebFilters and Mock Authentication

### 3.1. Spring Security WebFlux uses Reactor Context

In reactive applications, Spring Security builds `SecurityWebFilterChain` via `ServerHttpSecurity`, authenticates requests, and places the Authentication into the reactive `SecurityContext`. Handlers/services access the identity within the reactive pipeline.

If WebTestClient binds to the context, the filter chain executes if it is registered and test support is configured:

```java
WebTestClient client = WebTestClient
        .bindToApplicationContext(context)
        .apply(SecurityMockServerConfigurers.springSecurity())
        .configureClient()
        .build();
```

`.apply(springSecurity())` is especially important when using `SecurityMockServerConfigurers.mockUser()`, `mockJwt()`, or `mockOpaqueToken()`.

### 3.2. `mockUser()` is for authorization

```java
client.mutateWith(mockUser("reader").authorities(
        new SimpleGrantedAuthority("SCOPE_reports.read")))
    .get().uri("/api/reports")
    .exchange()
    .expectStatus().isOk();
```

This checks "if the Authentication has `SCOPE_reports.read`, does the route allow access?". It does **not** check passwords, an IdP, JWT signatures, JWKS, or opaque token introspection.

**Conversely**, if you `bindToApplicationContext` with real security/user store and send:

```java
client.get().uri("/api/reports")
        .headers(h -> h.setBasicAuth("reader", "reader-pass"))
        .exchange()
        .expectStatus().isOk();
```

then **the HTTP Basic WebFilter and password check still run for real inside the mock exchange**, because they are part of the application chain. Only the HTTP transport/socket is mocked.

Therefore, do not say "ApplicationContext mock tests do not test authentication at all"; distinguish **mock Authentication** from **mock HTTP transport**.

### 3.3. `mockJwt()` and `mockOpaqueToken()`

In a WebFlux Resource Server with JWT:

```java
// FRAGMENT: used in test apps with oauth2ResourceServer().jwt().
client.mutateWith(mockJwt().authorities(
        new SimpleGrantedAuthority("SCOPE_reports.read")))
    .get().uri("/api/reports")
    .exchange()
    .expectStatus().isOk();
```

In a WebFlux Resource Server with Opaque tokens:

```java
// FRAGMENT: used in test apps with oauth2ResourceServer().opaqueToken().
client.mutateWith(mockOpaqueToken().authorities(
        new SimpleGrantedAuthority("SCOPE_reports.read")))
    .get().uri("/api/reports")
    .exchange()
    .expectStatus().isOk();
```

These two fragments illustrate **authorization tests** and do **not** belong to the HTTP Basic project in section 6. `mockJwt()` does not issue an RSA-signed token for a real `ReactiveJwtDecoder` to verify. `mockOpaqueToken()` does not POST to an introspection endpoint.

To test JWT signature/issuer/audience/time, generate a genuinely signed token from a test private key, configure a JWKS fixture public key, and send a Bearer header over real HTTP; add negative tests with wrong signature/iss/aud/exp/nbf. To test opaque tokens, use a real `ReactiveOpaqueTokenIntrospector` connecting to MockWebServer/WireMock returning `active=true/false`, and verify Basic introspection client credentials as well.

### 3.4. Authorization statuses must include failure cases

| Scenario | Typical HTTP status |
| --- | --- |
| Public GET | 200 |
| Protected GET, no credentials | 401 |
| Basic wrong password / invalid Bearer | 401 |
| Authenticated, missing authority | 403 |
| Authenticated, has required authority | 200 |
| Request matched by `denyAll()` while unauthenticated | May be 401 or 403 depending on exception entrypoint |
| Controller returns validation error | 4xx per `@ControllerAdvice` |
| Network/upstream failure | Depends on error handling, must not assume 401 |

A security regression can go unnoticed if tests only check the 200 happy path. Include at least 401 and 403 to distinguish authentication vs authorization.

---

## 4. When is an ApplicationContext test enough?

If the goal is solely to prove that `GET /api/reports` requires an authority, the controller returns the right JSON/text, and request validation/exception mapping works, in-memory `WebTestClient` is usually sufficient. When the context loads all needed filters/beans, it runs the real WebFlux handler chain without needing a port.

It is well suited for:

- URL/method mapping, path/query binding, validation.
- Authentication / authorization policies in WebFilters per loaded config.
- Body serialization/deserialization, status codes, headers, content negotiation.
- Controller Advice and exception handlers.
- Reactive `Mono`/`Flux` composition at the handler layer.
- Many input boundary cases and negative authz tests.
- Test contexts with mocked/in-memory services for faster execution.

**Not suitable for concluding** that Netty opened a port successfully, responses passed through a TCP parser, HTTPS handshakes succeeded, reverse proxies sanitized headers, HTTP/2 negotiation worked, or client disconnect/backpressure behaved properly over a real network.

**Pitfall:** `@WebFluxTest` may omit custom security chains or services. `@SpringBootTest(MOCK)` loads more beans and may still make real DB/HTTP upstream calls if not stubbed.

## 5. When is a real server needed?

Use `@SpringBootTest(RANDOM_PORT)` + `WebTestClient.bindToServer()` to verify:

1. The embedded Reactor Netty/Tomcat appropriate for the app type actually starts and binds a port.
2. HTTP requests/responses traverse TCP sockets, the network client, and the server request parser.
3. Basic/Bearer headers are transmitted over the wire and processed by the actual SecurityWebFilterChain.
4. Mapping/exception handling works with a real HTTP request.
5. Streaming, chunking, SSE, compressed payloads, timeouts, and cancellation when dedicated tests are written.
6. Code depending on remote address, base URL, forwarded headers, or server-specific options within test configuration scope.
7. Server response size limits, path encoding, Host header, status codes, and Content-Type per test.

**However**, a localhost HTTP test **does not automatically verify** production TLS, mTLS, proxy/load balancers, DNS, firewalls, a real IdP, OAuth2 auth-code grants, or clusters. Only the components you actually include in the test are verified.

### Transaction / data isolation

When a test calls a real server, requests are handled in a separate execution/reactive context on the server; a transaction on the test method does not guarantee rollback of database writes on the server side. Use explicit cleanup/ephemeral DBs, unique test IDs, or verified R2DBC transactional fixtures. Do not rely on `@Transactional` on a JUnit class to "guarantee" reverting all HTTP server-side changes.

---

## 6. Demo: Java 17+ Spring Boot 3.5.16

The project is intentionally kept simple to isolate differences caused by **transport** rather than DB or IdP:

- In-memory HTTP Basic users.
- `reader` has `SCOPE_reports.read` and password `reader-pass`.
- `viewer` has only `SCOPE_profile.read` and password `viewer-pass`.
- `GET /public/ping` is public.
- `GET /api/reports` requires `SCOPE_reports.read` and returns a body from `ReportService`.
- Group A uses full ApplicationContext mock; group B uses a web slice with a mock service; group C uses real HTTP.
- All test files share package `example.httpmodes` so Spring Boot finds the main configuration.

**Passwords and `{noop}` are strictly for the lab. Never use them in production.**

### 6.1. Directory structure

```text
webflux-http-test-modes/
  settings.gradle
  build.gradle
  src/main/java/example/httpmodes/
    HttpModesApplication.java
    HttpSecurityConfiguration.java
    ReportService.java
    ReportController.java
  src/test/java/example/httpmodes/
    MockApplicationContextTests.java
    WebFluxSliceTests.java
    RealHttpServerTests.java
```

### 6.2. Gradle Groovy

**`settings.gradle`:**

```groovy
rootProject.name = 'webflux-http-test-modes'
```

**`build.gradle`:**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'example'
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
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testImplementation 'io.projectreactor:reactor-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

- Spring WebFlux starter brings WebClient, WebTestClient-related classpath, and Reactor Netty.
- Security starter provides WebFlux HTTP Basic filters and reactive user services.
- Test starter brings JUnit 5/Spring Test/Mockito; `spring-security-test` brings `SecurityMockServerConfigurers`.
- Do not add `spring-boot-starter-web`: Spring Boot may prioritize MVC/Servlet if both stacks are present.

### 6.3. Main class

**`src/main/java/example/httpmodes/HttpModesApplication.java`:**

```java
package example.httpmodes;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class HttpModesApplication {
    public static void main(String[] args) {
        SpringApplication.run(HttpModesApplication.class, args);
    }
}
```

### 6.4. SecurityWebFilterChain + MapReactiveUserDetailsService

**`src/main/java/example/httpmodes/HttpSecurityConfiguration.java`:**

```java
package example.httpmodes;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration(proxyBeanMethods = false)
@EnableWebFluxSecurity
public class HttpSecurityConfiguration {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers(HttpMethod.GET, "/public/ping")
                            .permitAll()
                        .pathMatchers(HttpMethod.GET, "/api/reports")
                            .hasAuthority("SCOPE_reports.read")
                        .anyExchange().denyAll()
                )
                .httpBasic(Customizer.withDefaults())
                .formLogin(form -> form.disable())
                .build();
    }

    @Bean
    MapReactiveUserDetailsService reactiveUsers() {
        UserDetails reader = User.withUsername("reader")
                .password("{noop}reader-pass")
                .authorities("SCOPE_reports.read")
                .build();

        UserDetails viewer = User.withUsername("viewer")
                .password("{noop}viewer-pass")
                .authorities("SCOPE_profile.read")
                .build();

        return new MapReactiveUserDetailsService(reader, viewer);
    }
}
```

This code uses the reactive `ServerHttpSecurity` API, not Servlet `HttpSecurity`.

- `/api/reports` permits only Authentications with `SCOPE_reports.read`.
- `httpBasic(Customizer.withDefaults())` enables Basic authentication for the demo.
- `formLogin(form -> form.disable())` disables form login so API routes challenge with Basic.
- The user store uses `{noop}` only for tests; production requires BCrypt/Argon2 or an approved strategy.
- The demo has only GET endpoints, so CSRF does not block the illustrated requests. For POST/PUT/DELETE with cookie-based auth, CSRF must be analyzed separately.
- `anyExchange().denyAll()` blocks other routes.

### 6.5. Service

**`src/main/java/example/httpmodes/ReportService.java`:**

```java
package example.httpmodes;

import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class ReportService {

    public Mono<String> readFor(String username) {
        return Mono.just("report-for-" + username);
    }
}
```

There is no DB/remote service, so differences between mock/full/real HTTP are not obscured by external dependencies. In real apps, repositories and record-level authorization need dedicated tests.

### 6.6. Controller

**`src/main/java/example/httpmodes/ReportController.java`:**

```java
package example.httpmodes;

import java.security.Principal;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class ReportController {

    private final ReportService reportService;

    public ReportController(ReportService reportService) {
        this.reportService = reportService;
    }

    @GetMapping("/public/ping")
    public Mono<String> ping() {
        return Mono.just("pong");
    }

    @GetMapping("/api/reports")
    public Mono<String> reports(Principal principal) {
        return reportService.readFor(principal.getName());
    }
}
```

WebFlux resolves `Principal` from the authenticated security context. Once `reader` passes Basic authentication, the expected response is:

```text
report-for-reader
```

If `viewer` is authenticated but lacks `SCOPE_reports.read`, Spring Security returns 403 **before the service is called**.

---

## 7. Group A — Full ApplicationContext, mock HTTP

**`src/test/java/example/httpmodes/MockApplicationContextTests.java`:**

```java
package example.httpmodes;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
class MockApplicationContextTests {

    @Autowired ApplicationContext context;

    private WebTestClient client;

    @BeforeEach
    void setUp() {
        client = WebTestClient.bindToApplicationContext(context)
                .apply(springSecurity())
                .configureClient()
                .baseUrl("http://localhost")
                .build();
    }

    @Test
    void publicPingDoesNotRequireCredentials() {
        client.get().uri("/public/ping").exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("pong");
    }

    @Test
    void protectedRouteWithoutCredentialsIs401() {
        client.get().uri("/api/reports").exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void mockUserWithReadAuthorityCanGetReport() {
        client.mutateWith(mockUser("reader").authorities(
                    new SimpleGrantedAuthority("SCOPE_reports.read")))
                .get().uri("/api/reports").exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("report-for-reader");
    }

    @Test
    void mockUserWithoutAuthorityIs403() {
        client.mutateWith(mockUser("viewer").authorities(
                    new SimpleGrantedAuthority("SCOPE_profile.read")))
                .get().uri("/api/reports").exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void realBasicCredentialsAlsoWorkThroughMockWebFilterChain() {
        client.get().uri("/api/reports")
                .headers(h -> h.setBasicAuth("reader", "reader-pass"))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("report-for-reader");
    }

    @Test
    void wrongBasicPasswordIsRejectedWithoutARealHttpServer() {
        client.get().uri("/api/reports")
                .headers(h -> h.setBasicAuth("reader", "wrong-password"))
                .exchange()
                .expectStatus().isUnauthorized();
    }
}
```

**Explanation:**

- The full Spring ApplicationContext is actually loaded, including controller, service, and SecurityWebFilterChain.
- `WebTestClient.bindToApplicationContext` creates mock requests/responses in the same JVM, without a port.
- `.apply(springSecurity())` enables `mockUser` test support.
- The two `mockUser(...)` tests verify **authorization** against simulated authorities; they do not verify passwords.
- The two Basic header tests traverse the **real HTTP Basic WebFilter and password check**, even though the transport is in-process.
- `.baseUrl("http://localhost")` is only a base URI for mock tests; it does **not** make it perform HTTP networking.
- If `.apply(springSecurity())` is omitted, tests relying on mock authentication may no longer behave as expected. This is test configuration, not production logic.

## 8. Group B — `@WebFluxTest` with `@MockitoBean`

**`src/test/java/example/httpmodes/WebFluxSliceTests.java`:**

```java
package example.httpmodes;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.WebFluxTest;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Import;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.reactive.server.WebTestClient;

import reactor.core.publisher.Mono;

import static org.mockito.BDDMockito.given;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

@WebFluxTest(ReportController.class)
@Import(HttpSecurityConfiguration.class)
class WebFluxSliceTests {

    @Autowired ApplicationContext context;

    @MockitoBean ReportService reportService;

    private WebTestClient client;

    @BeforeEach
    void setUp() {
        given(reportService.readFor("reader"))
                .willReturn(Mono.just("slice-report-for-reader"));

        client = WebTestClient.bindToApplicationContext(context)
                .apply(springSecurity())
                .configureClient()
                .build();
    }

    @Test
    void authorizedReaderUsesMockedService() {
        client.mutateWith(mockUser("reader").authorities(
                    new SimpleGrantedAuthority("SCOPE_reports.read")))
                .get().uri("/api/reports").exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("slice-report-for-reader");
    }

    @Test
    void viewerWithoutScopeIs403BeforeService() {
        client.mutateWith(mockUser("viewer").authorities(
                    new SimpleGrantedAuthority("SCOPE_profile.read")))
                .get().uri("/api/reports").exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void publicRouteWorksInWebSlice() {
        client.get().uri("/public/ping").exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("pong");
    }
}
```

**Explanation:**

1. `@WebFluxTest(ReportController.class)` loads only the web slice, without automatically scanning regular services.
2. `@MockitoBean ReportService` registers a mock collaborator in the context and stubs it to return `slice-report-for-reader`. This differs intentionally from the real service's body.
3. `@Import(HttpSecurityConfiguration.class)` adds the project's real SecurityWebFilterChain and user store. Without importing it, tests can give false results about authz.
4. `mockUser(...)` tests the scope rule, not passwords.
5. Spring Boot 3.5 uses `@MockitoBean` from Spring Test 6.2; the older `@MockBean` is deprecated.
6. All requests in the slice still run through the **mock WebFlux handler chain**, with no HTTP socket.

Slices are suitable when business services/DBs are heavy and you only need to test HTTP/controller behavior. They do not prove the service/repository implementation works.

## 9. Group C — Real HTTP over embedded Reactor Netty

**`src/test/java/example/httpmodes/RealHttpServerTests.java`:**

```java
package example.httpmodes;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class RealHttpServerTests {

    @LocalServerPort int port;

    private WebTestClient client;

    @BeforeEach
    void setUp() {
        assertTrue(port > 0, "Embedded server must bind a port");
        client = WebTestClient.bindToServer()
                .baseUrl("http://127.0.0.1:" + port)
                .build();
    }

    @Test
    void realHttpPublicPing() {
        client.get().uri("/public/ping").exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("pong");
    }

    @Test
    void realHttpAnonymousIs401() {
        client.get().uri("/api/reports").exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void realHttpBasicReaderGetsReport() {
        client.get().uri("/api/reports")
                .headers(h -> h.setBasicAuth("reader", "reader-pass"))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("report-for-reader");
    }

    @Test
    void realHttpBasicViewerHas403() {
        client.get().uri("/api/reports")
                .headers(h -> h.setBasicAuth("viewer", "viewer-pass"))
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void realHttpWrongPasswordIs401() {
        client.get().uri("/api/reports")
                .headers(h -> h.setBasicAuth("reader", "wrong-password"))
                .exchange()
                .expectStatus().isUnauthorized();
    }
}
```

### Why is this real HTTP?

- `@SpringBootTest(RANDOM_PORT)` starts an actual embedded server when the project uses WebFlux.
- `@LocalServerPort` retrieves the OS-assigned port, with no hardcoded 8080.
- `bindToServer()` uses an HTTP client to send TCP requests to `127.0.0.1:port`.
- Basic headers pass through the HTTP parser, WebFlux Security filter, and MapReactiveUserDetailsService.
- No `mockUser` is used to create Authentication inside the server. Every authorization decision relies on an identity verified against real lab credentials.
- The server does not connect to an IdP or production database because the sample has no such dependencies.

### Why doesn't real HTTP automatically equal E2E?

The HTTP socket is real, yet TLS, reverse proxies, DNS, OAuth2, JWKS, session cookies, R2DBC, and service meshes are still **absent** from the demo. To test those boundaries, provision them explicitly in a suitable staging/test container environment.

---

## 10. Running tests

If the project has the Gradle Wrapper:

```bash
./gradlew test
```

Run only the ApplicationContext group:

```bash
./gradlew test --tests example.httpmodes.MockApplicationContextTests
```

Run the slice:

```bash
./gradlew test --tests example.httpmodes.WebFluxSliceTests
```

Run real HTTP:

```bash
./gradlew test --tests example.httpmodes.RealHttpServerTests
```

Windows PowerShell:

```powershell
.\gradlew.bat test --tests example.httpmodes.RealHttpServerTests
```

If you don't have the wrapper but have a compatible Gradle installed:

```bash
gradle test
```

**Expected result:** **14 test methods** PASS (6 mock full-context + 3 slice + 5 real HTTP) on JDK 17+ with compatible dependencies/runtime. This is **not the output of an actual Gradle execution**. After running, inspect:

```text
build/reports/tests/test/index.html
```

To test a simple publisher directly without HTTP, use `StepVerifier` (the `reactor-test` dependency is already added in Gradle):

```java
// FRAGMENT service unit test, does not test HTTP transport:
StepVerifier.create(new ReportService().readFor("reader"))
        .expectNext("report-for-reader")
        .verifyComplete();
```

`StepVerifier` is useful for `Mono`/`Flux`, virtual time, and reactive signals; it does not replace `WebTestClient` for testing Security WebFilters or real HTTP status codes.

---

## 11. What additional tests are needed for JWT/Opaque Resource Servers?

The HTTP Basic demo isolates ApplicationContext vs real-server differences, not the full OAuth2 model. When an app moves to JWT/opaque tokens, maintain **three layers of testing**:

| Question | Fast test | Integration test |
| --- | --- | --- |
| Which routes are public/protected? | Mock context + mockJwt / mockOpaqueToken | RANDOM_PORT + Bearer token |
| Are scope/role policies correct? | mockJwt/mockOpaqueToken authorities | Verified real token |
| JWT signature/issuer/audience/time? | Unit test validators/decoder | Signed RS256 JWT + JWKS fixture + real HTTP |
| Opaque token `active=false`? | Mock introspector unit test | WebTestClient real HTTP + MockWebServer introspection |
| HTTP Basic wrong password? | Mock web chain + Basic header | Real HTTP + Basic credentials |
| JSON/status/validation? | WebFlux slice/full context | Real HTTP smoke/contract |
| External IdP timeout? | Mock error responses | HTTP + network stub/IdP staging |
| TLS/mTLS/proxy forwarded headers? | Config review/unit tests | Staging test with real TLS/proxy |
| Cross-tenant reads? | Policy/service tests | HTTP + tenant-aware DB integration |
| Streaming response/SSE? | Flux StepVerifier/WebTestClient | Real HTTP streaming/backpressure test |

### Does MockWebServer make a test lose "real HTTP"?

If you run `@SpringBootTest(RANDOM_PORT)` and send requests to the app via `bindToServer()`, **incoming HTTP** is real. You can still have the app call a **mock downstream** over HTTP, such as MockWebServer/WireMock simulating an IdP. When reporting test coverage, state clearly: real inbound transport, mocked upstream.

Use `@DynamicPropertySource` to inject MockWebServer's random port endpoint **before** Spring builds the context. Do not hardcode `localhost:8080` or let tests depend on live Internet services.

**Fragment** for a Resource Server with introspection, not used in the Basic demo project:

```java
// Illustrative only; tests must define/start/close IDP themselves.
@DynamicPropertySource
static void configureIntrospection(DynamicPropertyRegistry registry) {
    registry.add(
            "spring.security.oauth2.resourceserver.opaquetoken.introspection-uri",
            () -> IDP.url("/introspect").toString());
}
```

End-to-end tests with a real IdP or real OAuth2 token endpoint require valid credentials, a data-reset policy, dedicated test tenants, rotation handling, and must never run destructive operations against production.

## 12. Mistakes causing false confidence

### 12.1. Using `@WebFluxTest` while forgetting `SecurityWebFilterChain`

A custom `SecurityWebFilterChain` may not be scanned. An endpoint returning 200 in a slice does not mean production protects it properly. Import the real config or use a full context; add 401/403 negative tests.

### 12.2. Using `mockUser` and concluding Basic passwords are valid

`mockUser` creates a pre-authenticated mock Authentication. Use a Basic header against the real user store to verify passwords, and real HTTP tests to verify the network entrypoint.

### 12.3. Using `mockJwt` and concluding signature/issuer are verified

Mock JWT bypasses cryptography. Only a signed token + real decoder + JWKS fixture verifies signature/issuer/audience/time. Negative tests with wrong key, wrong issuer, and expired tokens catch missing validators.

### 12.4. Using default `@SpringBootTest` and thinking the server is running

`@SpringBootTest` defaults to MOCK. If a test calls `http://localhost:8080`, it may be hitting **another process** or getting connection refused. For a real server, use `RANDOM_PORT` and `@LocalServerPort`.

### 12.5. `bindToApplicationContext` with an HTTP `baseUrl`

`baseUrl("http://localhost")` only resolves relative URIs when using `bindToApplicationContext`; it does not switch to network mode. You must call `bindToServer()` to use real transport.

### 12.6. Hardcoding ports in CI

Port 8080 easily collides with other applications. Use `RANDOM_PORT` and inject the actual port. Do not make tests depend on the startup order of an external server without lifecycle management.

### 12.7. Testing only 200 responses

Add no-credential 401, invalid-credential 401, insufficient-scope 403, forbidden method/path, and relevant exception cases. If security config is accidentally omitted, negative tests expose it.

### 12.8. `@MockitoBean` hiding a business bug

A slice test with `@MockitoBean ReportService` only verifies that the controller calls the right service API; it does not test the real service. You still need service unit tests, DB/R2DBC integration tests, and row-level permission tests.

### 12.9. Over-assuming `@Transactional` test rollback

A real HTTP server processes requests in a different execution context from the test method, so server-side changes may not be rolled back by the test's transaction. Use ephemeral DBs and explicit cleanup.

### 12.10. Real localhost HTTP != production TLS

Even if `bindToServer()` tests pass, you have not verified TLS, proxy headers, DNS, auth federation, or zero-trust boundaries unless you actually test them.

### 12.11. Context caching and parallel tests

Spring Boot caches test contexts across classes. Mutable state, static mocks, singleton services, and DB fixtures can leak data. Prefer state isolation/resetting mocks and avoid overusing `@DirtiesContext`.

### 12.12. Not awaiting Publisher completion

In WebFlux, avoid calling `subscribe()` manually in a controller and returning a response before processing completes. Return `Mono`/`Flux` from the handler; WebTestClient asserts the response within the managed request lifecycle.

---

## 13. Checklist and Exercises

### Checklist for a meaningful test suite

1. Test names/descriptions clearly specify Spring scope (slice vs full context) and HTTP transport (mock vs socket).
2. ApplicationContext tests load the proper SecurityWebFilterChain.
3. If mock auth is used, do not describe it as real password/JWT/opaque verification.
4. Use `springSecurity()` when `SecurityMockServerConfigurers` are needed on in-memory WebTestClient.
5. Include negative 401/403 tests.
6. Do not accidentally mix MVC and WebFlux on the classpath.
7. Real HTTP paths use RANDOM_PORT, not hardcoded ports.
8. DB/IdP/downstream dependencies are documented as real, in-memory, or mocked.
9. Test timeouts/streaming/network/TLS directly when those are risks to verify, rather than inferring from controller test results.
10. Use only fake lab secrets; never put production credentials in tests.
11. Reports/logs distinguish "expected" from "observed".
12. When method security is required, test both HTTP requests and reactive service invocations with SecurityContext.
13. Pay attention to data cleanup for server-side transactions.
14. Use `@MockitoBean` intentionally and avoid overmocking.
15. In multi-tenant apps, test wrong tenant/owner access to catch cross-tenant data leaks.

### Extension exercises

1. Run all 14 tests and identify which class opens an HTTP listener.
2. Try removing `springSecurity()` from the mock client and observe how `mockUser` behavior changes.
3. Keep `mockUser("reader")` but assign a different authority; why do authorities, not the username, determine 403?
4. Send a wrong Basic password in both mock context and real HTTP; distinguish which pipeline parts are tested.
5. Remove `@Import(HttpSecurityConfiguration.class)` from the slice and see how the context/security policy changes.
6. Try removing `@MockitoBean` from the slice; explain why ReportService is not loaded by component scanning.
7. Change RANDOM_PORT to MOCK while still calling `bindToServer()`; observe connection refused.
8. Use `@AutoConfigureWebTestClient` to inject the client into full-context MOCK and compare with manual binding.
9. Add a JSON DTO and test serialization/validation in both modes.
10. Add a POST endpoint with cookie authn, analyze CSRF rather than disabling it to make the test pass.
11. Replace Basic with a JWT Resource Server; generate an RSA token, JWKS fixture, and test wrong iss/aud.
12. Replace with opaque token introspection, testing `active=false` and wrong scope via MockWebServer.
13. Add R2DBC tenant-aware access and dedicated cleanup for real HTTP tests.
14. Test SSE/Flux both in-process and over real HTTP, observing timeouts/streaming.
15. Place a gateway behind a reverse proxy and verify trusted forwarding headers in staging.
16. Design a test pyramid based on application risk rather than forcing a fixed ratio.

## Conclusion

**`bindToApplicationContext`** dispatches mock requests through the WebFlux handler chain in the same JVM: it is fast and can test real security filters/authorization, but does **not** prove a TCP server or HTTP transport. **`bindToServer`** calls a running server with real HTTP requests, additionally verifying networking/container behavior.

**Default `@SpringBootTest` = full context + MOCK**, **`@SpringBootTest(RANDOM_PORT)` = full context + real HTTP server**, and **`@WebFluxTest` = web slice + mock exchange**. `mockUser()`/`mockJwt()`/`mockOpaqueToken()` test authorization but **do not test** credentials/signatures/introspection.

A strong test suite needs both **in-process tests for broad rule coverage** and **real HTTP integration tests for critical boundaries**, plus proxy/TLS/IdP/DB integration when those verification goals apply.

## References

- [Spring Framework 6.2 — WebTestClient](https://docs.spring.io/spring-framework/reference/6.2/testing/webtestclient.html)
- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html)
- [Spring Security 6.5 — WebTestClient Security Setup](https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/setup.html)
- [Spring Security 6.5 — Testing Authentication](https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/authentication.html)
- [Spring Security 6.5 — Testing OAuth2](https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/oauth2.html)
- [Spring Security 6.5 — Reactive WebFlux Security](https://docs.spring.io/spring-security/reference/6.5/reactive/configuration/webflux.html)
- [Spring Test — @MockitoBean](https://docs.spring.io/spring-framework/reference/6.2/testing/annotations/integration-spring/annotation-mockitobean.html)
- [Spring Boot 3.5.16 Release](https://spring.io/blog/2026/06/25/spring-boot-3-5-16-available-now/)
